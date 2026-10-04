#!/usr/bin/env python3
"""workflows.driver — contrato de ORQUESTACIÓN del paso `agent` (F2).

Patrón READ → EXECUTE → COMMIT (MAPA.md · contrato de 4 partes, estilo
ChatDev H2): el runner NO le entrega el mundo al agente — le entrega un
`brief` cerrado con lo que puede LEER, el agente EJECUTA fuera del runner,
y COMMITEA su salida como ARTEFACTO declarado. El `verify:` del spec corre
después contra ESE artefacto real — evidencia, jamás el claim del agente.

Contrato del driver (un callable):

    driver(brief) → {"ok": bool, "detail": str, "artifacts": {nombre: valor}}

  brief = {
    "run_id", "workflow", "step",        # identidad del paso en el run
    "role",                              # rol declarado en el spec (o None)
    "contract",                          # las 4 partes del spec (o None):
                                         #   objetivo · formato · tools · límites
    "reads":    {clave: valor|None},     # READ — SOLO lo que el paso declara
                                         #   en `reads:` (resuelto contra los
                                         #   artefactos del run; None = falta)
    "artifact": str|None,                # COMMIT — el artefacto que el spec
                                         #   espera de este paso
    "workdir":  ruta,                    # dir del run donde materializarlo
    "params", "repo", "attempt", "dry",
  }

  resultado["artifacts"] debe mapear el `artifact` declarado a su ruta real
  (o dejar el valor-dato, p. ej. la lista `findings`). El runner lo mergea al
  estado del run y LUEGO corre el verify del spec — si el driver dice ok pero
  el artefacto no está, el verify FALLA de verdad (nada de verde fingido).

Inyección (en orden de prioridad):
  1. parámetro `driver=` de `workflows.start()` / `resume()`;
  2. default del proceso vía `set_default(fn)`;
  3. sin driver → el paso agent queda STUB honesto (verify omitido con
     detalle explícito) — el comportamiento v1 de siempre, intacto.

El CALLABLE del driver no se persiste en el run — pero su IDENTIDAD sí
(v1.1): `identity_of(fn)` → dict de datos (nombre; y para el driver real,
backend/model/timeout) que el runner guarda en state["driver"], y
`rehydrate(ident)` lo reconstruye en el resume. Un run que corrió con driver
real JAMÁS degrada a stub en silencio: sin driver rehidratable ni
re-inyectado, sus pasos agent fallan con detalle (lo aplica el runner).
"""

_DEFAULT = None                # driver default del proceso (set_default)


def set_default(fn):
    """Registra `fn` como driver default del proceso (None = quitar).
    El parámetro `driver=` de start/resume siempre gana sobre esto."""
    global _DEFAULT
    if fn is not None and not callable(fn):
        raise TypeError("el driver debe ser callable (recibí %r)" % (fn,))
    _DEFAULT = fn
    return fn


def get_default():
    """El driver default registrado, o None (→ stub honesto)."""
    return _DEFAULT


def name_of(fn):
    """Nombre legible del driver para la traza N10 (`wf_step.driver`)."""
    return (getattr(fn, "driver_name", None)
            or getattr(fn, "__name__", None)
            or type(fn).__name__)


def identity_of(fn):
    """IDENTIDAD persistible del driver (v1.1): dict de datos puros, jamás
    el callable. Los drivers de la casa (real/make_real) declaran
    `driver_identity` y son rehidratables; un callable externo queda
    registrado por nombre con rehydratable=False (resume exige re-inyección)."""
    ident = getattr(fn, "driver_identity", None)
    if isinstance(ident, dict):
        out = dict(ident)
        out["name"] = name_of(fn)
        out["rehydratable"] = True
        return out
    return {"name": name_of(fn), "rehydratable": False}


def rehydrate(ident):
    """Reconstruye el driver desde su identidad persistida, o None si no se
    puede (identidad ausente / no rehidratable / kind desconocido). El único
    kind de la casa es `real` → make_real con los mismos knobs: conserva la
    postura de seguridad ÍNTEGRA (tools SIEMPRE off, opt-in ya dado al
    arrancar el run con driver)."""
    if not isinstance(ident, dict) or not ident.get("rehydratable"):
        return None
    if ident.get("kind") == "real":
        try:
            return make_real(backend=ident.get("backend"),
                             model=ident.get("model"),
                             timeout=ident.get("timeout"))
        except Exception:
            return None
    return None


# ── driver REAL: despacho headless (opt-in, jamás default) ─────────────────
#
# Cablea el paso agent al contrato `headless.run_headless` del harness:
# brief → prompt → LLM one-shot → su TEXTO se captura como el artefacto.
#
# POSTURA DE SEGURIDAD (no negociable — guard N6, mismo modelo que dream.py):
#   · El despacho corre SIEMPRE con tools="none" (TOOLS_NONE): el LLM no
#     tiene manos — no toca filesystem ni red. No hay parámetro para
#     relajarlo desde aquí; el invariante de headless además RECHAZA
#     backends que no puedan deshabilitar tools (HeadlessSecurityError).
#   · Consecuencia honesta: con tools apagadas el ÚNICO canal de commit es
#     el texto de la respuesta. El driver lo escribe como DATO en
#     brief["workdir"] — jamás lo interpreta, evalúa ni ejecuta. El
#     `verify:` determinista del spec es quien juzga el artefacto.
#   · Los `reads` inlineados al prompt son contenido no confiable → van
#     envueltos con `untrusted.wrap` (anti-breakout) + scan N6 log-only, y
#     con líneas de secretos REDACTADAS (secret_scan). Sin el guard N6
#     disponible, el contenido NO se inlinea (solo se listan las claves).
#   · Fallo real = no-ok con detalle (HeadlessError, backend caído,
#     transcript vacío) — jamás verde fingido; el runner reintenta/escala.

DEFAULT_TIMEOUT_REAL = 600     # s por paso agent (más holgado que headless)
_MAX_READ_CHARS = 20_000       # cota por read inlineado al prompt
_ENV_BACKEND = "WORKSPACE_WF_BACKEND"
_ENV_MODEL = "WORKSPACE_WF_MODEL"
_ENV_TIMEOUT = "WORKSPACE_WF_TIMEOUT"


def _imports():
    """headless (OBLIGATORIO) + guards (amputables, con postura declarada),
    con la raíz del harness y hooks/ en el path — mismo patrón que dream.py."""
    import os as _o, sys as _s
    here = _o.path.dirname(_o.path.abspath(__file__))
    root = _o.path.dirname(here)
    for p in (root, _o.path.join(root, "hooks")):
        if p not in _s.path:
            _s.path.insert(0, p)
    import headless
    try:
        import untrusted           # guard N6 (wrap anti-breakout + scan)
    except Exception:
        untrusted = None
    try:
        import secret_scan         # N14: redacción de secretos en los reads
    except Exception:
        secret_scan = None
    return headless, untrusted, secret_scan


def _redact_secrets(text, secret_scan):
    """Líneas con secretos → redactadas (solo la clase, jamás el secreto).
    Sin secret_scan el texto pasa intacto (módulo amputable, como en dream)."""
    if secret_scan is None or not text:
        return text
    try:
        findings = secret_scan.scan_text(text)
    except Exception:
        return text
    if not findings:
        return text
    malas = {f["line"]: f["class"] for f in findings}
    out = []
    for i, ln in enumerate(text.split("\n"), 1):
        out.append("[REDACTADO: %s]" % malas[i] if i in malas else ln)
    return "\n".join(out)


def _read_view(key, value, untrusted, secret_scan, source):
    """Un read del brief → bloque de prompt. El contenido es NO confiable:
    va envuelto (wrap N6) y con secretos redactados. Sin guard N6 NO se
    inlinea contenido — fail-closed en la parte riesgosa."""
    import json as _j, os as _o
    if value is None:
        return "· `%s`: (falta — el run no produjo este artefacto)" % key
    if isinstance(value, str) and _o.path.isfile(value):
        try:
            with open(value, encoding="utf-8", errors="replace") as fh:
                content = fh.read(_MAX_READ_CHARS + 1)
        except OSError as e:
            return "· `%s`: (ilegible: %s)" % (key, e)
        label = "artefacto `%s` del run (%s)" % (key, value)
    else:
        content = value if isinstance(value, str) else _j.dumps(
            value, ensure_ascii=False)
        content = content[:_MAX_READ_CHARS + 1]
        label = "artefacto-dato `%s` del run" % key
    if len(content) > _MAX_READ_CHARS:
        content = content[:_MAX_READ_CHARS] + "\n[... truncado por cota]"
    content = _redact_secrets(content, secret_scan)
    if untrusted is None:
        # Fail-closed: sin wrap anti-breakout el contenido no confiable NO
        # entra al prompt — ni siquiera un extracto. Solo una referencia
        # inerte (el path si era archivo; los valores-dato se omiten).
        ref = value if (isinstance(value, str) and _o.path.isfile(value)) \
            else "(valor-dato omitido)"
        return ("· `%s`: (contenido NO inlineado — guard N6 no disponible; "
                "referencia: %s)" % (key, ref))
    try:
        untrusted.scan_and_log(content, source)      # N6 log-only, best-effort
    except Exception:
        pass
    return "· `%s`:\n%s" % (key, untrusted.wrap(content, label=label))


def _prompt_from_brief(brief, untrusted, secret_scan):
    """Brief cerrado → prompt del paso: contrato de 4 partes del spec +
    reads (como DATOS no confiables) + la salida que el harness capturará."""
    import json as _j
    c = brief.get("contract") or {}
    art = brief.get("artifact")
    source = "wf:%s:%s" % (brief.get("workflow"), brief.get("step"))
    p = [
        "Eres el AGENTE DE PASO de un workflow WORKSPACE. Corres HEADLESS y "
        "SIN TOOLS: no puedes leer ni escribir archivos, ejecutar comandos "
        "ni tocar la red. Tu ÚNICA salida es el texto de esta respuesta — "
        "el harness lo captura y lo commitea como evidencia del paso.",
        "",
        "PASO `%s` · rol: %s · workflow `%s` · run %s · intento %s"
        % (brief.get("step"), brief.get("role") or "(sin rol)",
           brief.get("workflow"), brief.get("run_id"), brief.get("attempt")),
        "",
        "CONTRATO DEL PASO (spec congelado):",
        "- objetivo: %s" % (c.get("objetivo")
                            or "(no declarado — cumple el paso según id/rol)"),
        "- formato: %s" % (c.get("formato") or "(libre: texto claro y conciso)"),
        "- tools: %s — NOTA: en esta corrida NO tienes tools; si el contrato "
        "las pedía, produce el mejor artefacto posible SOLO con texto y "
        "declara dentro del artefacto qué quedó pendiente por esa limitación."
        % (c.get("tools") or "(ninguna declarada)"),
        "- límites: %s" % (c.get("limites")
                           or "solo este paso; nada fuera de su alcance"),
    ]
    params = brief.get("params") or {}
    if params:
        p += ["", "PARÁMETROS DEL RUN (confiables, los puso el socio): "
              + _j.dumps(params, ensure_ascii=False)]
    reads = brief.get("reads") or {}
    p += ["", "INSUMOS (reads declarados por el paso):"]
    if reads:
        p += [_read_view(k, v, untrusted, secret_scan, source)
              for k, v in reads.items()]
    else:
        p += ["· (ninguno)"]
    if art:
        p += ["", "SALIDA OBLIGATORIA: responde EXCLUSIVAMENTE con el "
              "contenido íntegro del artefacto `%s` — sin prosa antes ni "
              "después, sin fences alrededor. Tu respuesta COMPLETA se "
              "guarda tal cual como ese archivo." % art]
    else:
        p += ["", "SALIDA: responde con el resultado del paso, conciso y "
              "verificable. Tu respuesta queda como evidencia del run."]
    return "\n".join(p)


def _dispatch(brief, *, backend, model, timeout):
    """Núcleo del driver real: brief → prompt → run_headless(tools=OFF) →
    transcript capturado como DATO → {ok, detail, artifacts}."""
    import os as _o
    if brief.get("dry"):        # cinturón: el runner ya no despacha en dry
        return {"ok": False, "artifacts": {},
                "detail": "driver real: dry-run — no se despacha nada"}
    try:
        headless, untrusted, secret_scan = _imports()
    except Exception as e:
        return {"ok": False, "artifacts": {}, "retriable": False,
                "detail": "driver real: headless no disponible (%s: %s)"
                          % (type(e).__name__, e)}
    backend = backend or _o.environ.get(_ENV_BACKEND) or headless.DEFAULT_BACKEND
    model = model or _o.environ.get(_ENV_MODEL) or None
    if timeout is None:
        # prioridad: knob fijado en make_real > `timeout:` del paso (brief,
        # v1.1) > env > default del driver
        try:
            timeout = int(brief.get("timeout")
                          or _o.environ.get(_ENV_TIMEOUT)
                          or DEFAULT_TIMEOUT_REAL)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT_REAL
    prompt = _prompt_from_brief(brief, untrusted, secret_scan)
    try:
        # tools=TOOLS_NONE SIEMPRE: el LLM del paso corre sin manos. El
        # invariante de headless rechaza backends que no puedan garantizarlo.
        ok, out = headless.run_headless(
            prompt, backend=backend, model=model, cwd=brief.get("workdir"),
            tools=headless.TOOLS_NONE, timeout=timeout)
    except headless.HeadlessError as e:
        # error de CONFIGURACIÓN (UnknownBackend/SecurityError/…): headless
        # ya lo declara no-transitorio — se propaga retriable=False para que
        # el runner NO queme max_iter reintentando lo imposible.
        return {"ok": False, "artifacts": {}, "retriable": False,
                "detail": "driver real: headless rechazó el despacho "
                          "(%s: %s)" % (type(e).__name__, e)}
    if not ok:
        return {"ok": False, "artifacts": {},
                "detail": "driver real: backend %r falló: %s"
                          % (backend, str(out)[:300])}
    text = out or ""
    if not text.strip():
        return {"ok": False, "artifacts": {},
                "detail": "driver real: transcript vacío — no hay artefacto "
                          "que commitear (backend %r)" % backend}
    if untrusted is not None:
        try:                    # N6 log-only sobre la salida — observabilidad
            untrusted.scan_and_log(text, "wf:%s:%s:out"
                                   % (brief.get("workflow"), brief.get("step")))
        except Exception:
            pass
    art = brief.get("artifact")
    if not art:
        return {"ok": True, "artifacts": {},
                "detail": "driver real: paso `%s` ejecutado (%d chars de "
                          "salida, backend %s; sin artifact declarado)"
                          % (brief.get("step"), len(text), backend)}
    # COMMIT: el texto ES el artefacto — se escribe como DATO, jamás se
    # interpreta ni ejecuta. El verify del spec lo juzga después.
    path = _o.path.join(brief["workdir"], "%s-%s"
                        % (brief.get("step"), _o.path.basename(art)))
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as e:
        return {"ok": False, "artifacts": {},
                "detail": "driver real: no pude commitear el artefacto "
                          "`%s`: %s" % (art, e)}
    return {"ok": True, "artifacts": {art: path},
            "detail": "driver real: paso `%s` → artefacto `%s` commiteado "
                      "(%d chars, backend %s)"
                      % (brief.get("step"), art, len(text), backend)}


def make_real(backend=None, model=None, timeout=None):
    """Factory del driver real con backend/model/timeout fijados. Sin
    argumentos hereda los knobs de entorno (WORKSPACE_WF_BACKEND/_MODEL/
    _TIMEOUT) y el default seguro claude-code. tools NO es configurable:
    siempre OFF (postura de seguridad, ver bloque de arriba)."""
    def _real(brief):
        return _dispatch(brief, backend=backend, model=model, timeout=timeout)
    _real.driver_name = "real" if not backend else "real(%s)" % backend
    # identidad persistible (v1.1): con esto `resume` rehidrata ESTE driver
    _real.driver_identity = {"kind": "real", "backend": backend,
                             "model": model, "timeout": timeout}
    return _real


def real(brief):
    """Adaptador REAL — despacho headless del paso agent (opt-in).

    brief → prompt (contrato de 4 partes + reads envueltos como contenido NO
    confiable) → `headless.run_headless(tools="none")` → el texto de la
    respuesta se commitea como DATO en brief["workdir"] bajo el nombre del
    artefacto declarado. Fallo (HeadlessError, backend caído, transcript
    vacío) = no-ok con detalle — jamás verde fingido; el `verify:` del spec
    corre después contra el artefacto real."""
    return _dispatch(brief, backend=None, model=None, timeout=None)


real.driver_name = "real"
real.driver_identity = {"kind": "real", "backend": None, "model": None,
                        "timeout": None}


def resolve(name, *, backend=None, model=None, timeout=None):
    """Driver por nombre para el CLI (`workspace wf run --driver real`).
    Vacío/none/stub → None (el stub honesto de siempre — el DEFAULT).
    `real` es el ÚNICO despacho y es opt-in explícito."""
    key = (name or "").strip().lower()
    if key in ("", "none", "stub", "default"):
        return None
    if key == "real":
        if backend or model or timeout is not None:
            return make_real(backend=backend, model=model, timeout=timeout)
        return real
    raise ValueError("driver desconocido: %r (soportados: real · stub)"
                     % (name,))
