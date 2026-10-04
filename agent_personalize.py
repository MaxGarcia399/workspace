#!/usr/bin/env python3
"""WORKSPACE · agent_personalize — pasada de MODELO que personaliza un cerebro.

«Crear agente» es scaffolding local (instantáneo, 0 tokens): copia el template
y rellena placeholders. Este módulo agrega el paso OPCIONAL de después: una
pasada con el harness elegido (claude-code / codex / stub / cualquier backend
de `headless.py`) que REDACTA los archivos de identidad a la medida de lo que
el socio escribió en el formulario — rol, propósito, alcance y sobre todo el
perfil del DUEÑO. El agente deja de sonar a template y suena hecho para él.

PRINCIPIOS (en orden):

  OPT-IN       solo corre si el formulario lo pidió (`params["personalize"]`)
               o el env lo fuerza (`WORKSPACE_CREATE_PERSONALIZE=1`; `=0` es el
               kill-switch que gana SIEMPRE). Sin pedirlo, crear sigue siendo
               0 tokens, idéntico a hoy.
  FAIL-SOFT    si el harness no está / no tiene headless / falla / responde
               basura → el agente queda creado CON LA PLANTILLA (como hoy) y
               el paso se marca warn «sin personalizar — córrelo luego». La
               aplicación es TODO-o-rollback: jamás un cerebro a medias.
  NO INVENTAR  el prompt solo lleva lo que el dueño escribió; campo vacío →
               el archivo conserva el placeholder/comentario-guía del
               template. El modelo redacta, no fabrica hechos.
  SIN MANOS    el modelo NO ejecuta tools: `headless.run_headless` con
               tools="gen" (claude-code/stub: --tools "" + sin settings del
               socio). codex no puede apagar tools → cae a "read-only"
               (sandbox de solo-lectura; puede leer, no escribir — las
               escrituras las hace ESTE módulo tras validar). El modelo
               devuelve bloques `<<<ARCHIVO: ruta>>> … <<<FIN>>>` y el
               applier valida whitelist + contención + marcadores antes de
               tocar disco.
  HONESTO      el costo SÍ existe y se reporta: tokens estimados por chars
               (≈4 chars/token, la misma convención de brain_vitals) — el
               modo headless no expone usage real, y se dice tal cual.
               Recibo auditable en `<brain>/.workspace/personalize.json`.

ARCHIVOS QUE AFINA (whitelist cerrada — nada más se escribe):
  CLAUDE.md                 solo título/frases de identidad (el contrato de
                            boot queda intacto; se valida que siga citando
                            BOOT/00-SOUL.md).
  BOOT/00-SOUL.md           las secciones para las que SÍ hay datos.
  BOOT/01-IDENTITY.md       la tarjeta (rol, scope, lema si hay datos).
  BOOT/03-RULES.md          SOLO la sección «## Scope …» — el applier exige
                            que todo lo anterior quede byte-idéntico.
  STATE/users/<dueño>.md    quién es el dueño y qué necesita (solo si hay
                            datos del dueño; archivo nuevo).

ENGANCHE: `agent_create_job` agrega `steps_skeleton()` al job cuando
`requested(params)` y llama `run(dest, params, progress=…)` tras el create.
Re-corrida manual (el «córrelo luego» del fail-soft):

    python3 agent_personalize.py <agente|carpeta> [--engine X] [--dry-run]
            [--campo clave=valor …] [--show-prompt]

TODO (superficie, lo integra el agente de add_agent_tui): toggle «personalizar
con el modelo» en el formulario → `params["personalize"] = True` (+ campos
multilínea `owner_profile` / `contexto` / `extra_campos` del catálogo de
preguntas — este módulo ya los consume si llegan).

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

#: ≈4 chars/token — la MISMA convención de brain_vitals/doctor (estimación
#: gruesa y declarada como tal; headless no reporta usage real).
CHARS_PER_TOKEN = 4
try:
    import brain_vitals as _bv
    CHARS_PER_TOKEN = int(getattr(_bv, "CHARS_PER_TOKEN", 4)) or 4
except Exception:
    pass

DEFAULT_TIMEOUT = 420          # seg; knob: WORKSPACE_PERSONALIZE_TIMEOUT
MAX_FILE_CHARS = 64_000        # un archivo de identidad jamás es más grande
MAX_PROMPT_CHARS = 150_000     # guard anti-prompt-monstruo (fail-soft)
MAX_FIELD_CHARS = 4_000        # cada campo del formulario, acotado

#: Los pasos EXTRA que esta pasada agrega al job de creación (mismo shape que
#: agent_admin.CREATE_STEPS; la vista EN VIVO los pinta sola — lee job["steps"]).
STEPS = (
    ("perso-prep", "personalizar: reunir identidad y datos"),
    ("perso-modelo", "personalizar: redactar con el modelo"),
    ("perso-aplicar", "personalizar: aplicar al cerebro"),
)

#: Whitelist CERRADA de archivos que la pasada puede escribir (rutas relativas
#: al cerebro, separador /). `STATE/users/<dueño>.md` se agrega en runtime.
BASE_TARGETS = ("CLAUDE.md", "BOOT/00-SOUL.md", "BOOT/01-IDENTITY.md",
                "BOOT/03-RULES.md")

#: Marcadores que el archivo personalizado DEBE conservar (sanity de que el
#: modelo afinó, no mutiló). Si falta alguno → ese archivo se rechaza (queda
#: el del template) y se reporta, jamás en silencio.
_REQUIRED_MARKS = {
    "CLAUDE.md": ("BOOT/00-SOUL.md", "STATE/"),
    "BOOT/00-SOUL.md": ("## ",),
    "BOOT/01-IDENTITY.md": ("Nombre",),
    # BOOT/03-RULES.md tiene su propia validación (prefijo byte-idéntico).
}
_RULES_SCOPE_RE = re.compile(r"^## Scope\b", re.MULTILINE)

#: Campos del formulario que viajan al prompt (clave en params → etiqueta en
#: español). Solo los NO vacíos; el prompt declara que son la única fuente de
#: verdad. Claves nuevas de la TUI (perfil del dueño, contexto) ya contempladas.
FIELD_LABELS = (
    ("display", "nombre visible del agente"),
    ("name", "nombre corto (slug)"),
    ("tagline", "rol / tagline"),
    ("proposito", "propósito"),
    ("scope", "alcance (scope)"),
    ("skills", "categorías de skills"),
    ("tono", "tono"),
    ("idioma", "idioma"),
    ("owner", "dueño (socio)"),
    ("owner_profile", "perfil del dueño — quién es y qué necesita"),
    ("dueno_perfil", "perfil del dueño — quién es y qué necesita"),
    ("contexto", "contexto del proyecto / equipo"),
    ("soul", "semilla de personalidad"),
)

#: Respuestas CRUDAS del formulario (params["intake"], dict clave→texto — las
#: llena add_agent_tui y viajan en .workspace/agent.json). Etiquetas en español
#: para el prompt; claves desconocidas pasan con su propia clave.
INTAKE_LABELS = {
    "nombre": None,                     # ya va como slug — no repetir
    "visible": None,                    # ya va como nombre visible
    "rol": "rol",
    "proposito": "propósito",
    "tono": "tono",
    "estilo": "estilo de voz (reglas concretas)",
    "idioma": "idioma",
    "alcance": "alcance — qué SÍ hace",
    "limites": "límites — qué NO hace / qué consulta antes",
    "ejemplos": "ejemplos de tareas típicas",
    "skills": "categorías de skills",
    "dueño": None,                      # ya va como dueño (socio)
    "dueño_quien": "el dueño — quién es",
    "dueño_como": "el dueño — cómo trabaja",
    "dueño_necesita": "el dueño — qué necesita del agente",
}

_BLOCK_RE = re.compile(
    r"<<<ARCHIVO:\s*(?P<path>[^>\n]+?)\s*>>>\n(?P<body>.*?)\n?<<<FIN>>>",
    re.DOTALL)


# ── opt-in ───────────────────────────────────────────────────────────────────
def requested(params):
    """¿El socio pidió la pasada? env WORKSPACE_CREATE_PERSONALIZE=0 es el
    kill-switch (gana SIEMPRE); =1 la fuerza; si no, manda el formulario
    (`params["personalize"]` truthy). Default: NO (crear = 0 tokens, como hoy)."""
    env = os.environ.get("WORKSPACE_CREATE_PERSONALIZE", "").strip().lower()
    if env in ("0", "false", "off", "no"):
        return False
    if env in ("1", "true", "on", "si", "sí", "yes"):
        return True
    v = (params or {}).get("personalize")
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "on", "si", "sí", "yes", "y")
    return bool(v)


def steps_skeleton():
    """Los pasos de la pasada, en el MISMO shape que agent_create_job usa
    ({key,label,st,note}) — la vista EN VIVO los pinta sin tocarla."""
    return [{"key": k, "label": lbl, "st": "pend", "note": ""}
            for k, lbl in STEPS]


def _prog(progress, key, st, note=""):
    """Reporta un paso. Falla-suave ABSOLUTA (un callback roto no tumba nada)."""
    if progress is None:
        return
    try:
        progress(key, st, note)
    except Exception:
        pass


# ── datos del formulario ─────────────────────────────────────────────────────
def collect_fields(params):
    """[(etiqueta, valor)] con los campos NO vacíos del formulario, acotados.
    `extra_campos`/`personalize_fields` (dict etiqueta→valor, el catálogo de
    preguntas de la TUI) se anexa tal cual. Dedup por etiqueta (gana el 1º)."""
    p = params or {}
    out, seen_lbl, seen_val = [], set(), set()

    def _add(label, val):
        s = str(val or "").strip()
        key = (s[:400].lower())            # dedup por valor (tagline==rol, etc.)
        if not s or label in seen_lbl or key in seen_val:
            return
        seen_lbl.add(label)
        seen_val.add(key)
        out.append((label, s[:MAX_FIELD_CHARS]))

    for key, label in FIELD_LABELS:
        _add(label, p.get(key))
    intake = p.get("intake")               # respuestas crudas del formulario
    if isinstance(intake, dict):
        for k, v in intake.items():
            label = INTAKE_LABELS.get(str(k), str(k).strip()[:120] or "campo")
            if label:                      # None = ya viaja por otro campo
                _add(label, v)
    for src in ("extra_campos", "personalize_fields"):
        extra = p.get(src)
        if isinstance(extra, dict):
            for k, v in extra.items():
                _add(str(k).strip()[:120] or "campo", v)
    return out


def targets(owner):
    """La whitelist de ESTA corrida: base + STATE/users/<dueño>.md si hay dueño
    válido (mismo patrón que valida agent_admin.create)."""
    tg = list(BASE_TARGETS)
    owner = (owner or "").strip().lower()
    if owner and re.match(r"^[a-z0-9_-]+$", owner):
        tg.append("STATE/users/%s.md" % owner)
    return tg


# ── prompt ───────────────────────────────────────────────────────────────────
def build_prompt(name, display, fields, files, owner):
    """UN prompt de generación (texto→texto, sin tools). `files` = dict ruta→
    contenido actual (None = no existe aún). Las reglas van ANTES que los
    datos: no inventar, conservar estructura, formato de salida exacto."""
    L = []
    L.append(
        "Eres el redactor de identidad de agentes del harness WORKSPACE. Un "
        "socio acaba de crear el agente «%s» (%s) desde el template estándar "
        "y llenó un formulario. Tu trabajo: afinar los archivos de identidad "
        "del cerebro para que suenen hechos a la medida de ese agente y de su "
        "dueño — usando los datos del formulario y NADA más." % (display, name))
    L.append("")
    L.append("REGLAS (inquebrantables):")
    L.append(
        "1. NO inventes hechos, nombres, proyectos, fechas ni preferencias. "
        "Tu única fuente de verdad son los DATOS DEL FORMULARIO de abajo. Si "
        "para una sección no hay datos, DÉJALA exactamente como está "
        "(incluidos los comentarios-guía <!-- … --> del template).")
    L.append(
        "2. Conserva la ESTRUCTURA de cada archivo: mismos encabezados, "
        "mismas rutas, mismas reglas operativas. Afinas redacción e "
        "identidad; el contrato operativo no se toca.")
    L.append(
        "3. En CLAUDE.md solo afina el título y las frases de identidad del "
        "arranque; las secciones de boot/operación quedan intactas.")
    L.append(
        "4. En BOOT/00-SOUL.md llena las secciones para las que SÍ hay datos. "
        "La nota de esqueleto del inicio: si llenaste la mayoría de las "
        "secciones, reemplázala por una línea honesta tipo «Primera pasada "
        "redactada desde el formulario de creación (%s) — afinar con el "
        "equipo»; si no, déjala." % time.strftime("%Y-%m-%d"))
    L.append(
        "5. En BOOT/03-RULES.md SOLO puedes reescribir la sección «## Scope "
        "…» (y solo si hay datos de alcance); TODO lo anterior a esa sección "
        "debe quedar byte por byte idéntico — se valida automáticamente.")
    users_rel = next((t for t in files if t.startswith("STATE/users/")), "")
    if users_rel:
        verbo = "créalo SOLO si hay datos del dueño en el formulario" \
            if files.get(users_rel) is None else \
            "afínalo con los datos del formulario (ya existe una semilla)"
        L.append(
            "6. %s: %s — quién es el dueño y qué necesita del agente, "
            "10-20 líneas, sin inventar nada." % (users_rel, verbo))
    L.append(
        "7. Escribe en español, salvo que los datos pidan otro idioma.")
    L.append(
        "8. Devuelve SOLO los archivos que cambiaste, cada uno COMPLETO, en "
        "este formato EXACTO y sin ningún texto fuera de los bloques:")
    L.append("")
    L.append("<<<ARCHIVO: ruta/relativa.md>>>")
    L.append("(contenido completo del archivo)")
    L.append("<<<FIN>>>")
    L.append("")
    L.append("DATOS DEL FORMULARIO (única fuente de verdad):")
    for label, val in fields:
        if "\n" in val:
            L.append("- %s:" % label)
            for ln in val.splitlines():
                L.append("    %s" % ln)
        else:
            L.append("- %s: %s" % (label, val))
    L.append("")
    L.append("ARCHIVOS ACTUALES DEL CEREBRO:")
    for rel in sorted(files):
        body = files[rel]
        L.append("")
        if body is None:
            L.append("%s: (no existe aún — créalo solo según la regla de "
                     "arriba)" % rel)
        else:
            L.append("<<<ARCHIVO: %s>>>" % rel)
            L.append(body.rstrip("\n"))
            L.append("<<<FIN>>>")
    return "\n".join(L)


# ── parsing + validación de la respuesta ─────────────────────────────────────
def parse_blocks(text, allowed):
    """Extrae los bloques `<<<ARCHIVO: …>>> … <<<FIN>>>`. Devuelve
    (dict ruta→contenido, [warns]). Solo rutas de la whitelist, relativas,
    sin `..`, con contenido sano — lo demás se DESCARTA con warn (jamás en
    silencio). No escribe nada."""
    out, warns = {}, []
    allowed = set(allowed)
    for m in _BLOCK_RE.finditer(text or ""):
        rel = m.group("path").strip().replace("\\", "/").lstrip("./")
        body = m.group("body")
        if rel not in allowed:
            warns.append("ruta fuera de whitelist ignorada: %s" % rel[:80])
            continue
        if ".." in rel.split("/") or os.path.isabs(rel):
            warns.append("ruta sospechosa ignorada: %s" % rel[:80])
            continue
        if not body.strip():
            warns.append("%s: contenido vacío — se conserva el template" % rel)
            continue
        if len(body) > MAX_FILE_CHARS:
            warns.append("%s: demasiado grande (%d chars) — se conserva el "
                         "template" % (rel, len(body)))
            continue
        if "<<<ARCHIVO:" in body:
            warns.append("%s: marcador anidado — se conserva el template" % rel)
            continue
        for mark in _REQUIRED_MARKS.get(rel, ()):
            if mark not in body:
                warns.append("%s: perdió «%s» — se conserva el template"
                             % (rel, mark))
                break
        else:
            out[rel] = body if body.endswith("\n") else body + "\n"
    return out, warns


def _rules_prefix_ok(original, nuevo):
    """BOOT/03-RULES.md: todo ANTES de «## Scope» debe quedar byte-idéntico
    (el modelo solo puede tocar el scope — las reglas de seguridad jamás)."""
    mo, mn = _RULES_SCOPE_RE.search(original or ""), \
        _RULES_SCOPE_RE.search(nuevo or "")
    if not mo:                       # el template no trae sección Scope → no tocar
        return False
    if not mn:
        return False
    return original[:mo.start()] == nuevo[:mn.start()]


# ── backend headless por harness ─────────────────────────────────────────────
def pick_backend(engine):
    """(backend, tools, nota) para el harness elegido, o (None, None, razón).
    claude-code/stub → tools='gen' (sin manos). Backends que NO pueden apagar
    tools (codex) → 'read-only' (leer sí, escribir jamás — escribimos nosotros
    tras validar). Harness sin backend headless → honesto: no se personaliza
    (sin fallback silencioso a otro modelo que el socio no eligió)."""
    import headless
    eng = (engine or "claude-code").strip().lower()
    try:
        b = headless.get_backend(eng)
    except headless.UnknownBackend:
        return None, None, "el harness %r no tiene modo headless" % eng
    except Exception as e:
        return None, None, "headless no disponible: %s" % e
    if b.get("can_disable_tools"):
        return eng, headless.TOOLS_GEN, ""
    return eng, headless.TOOLS_READ_ONLY, \
        "%s: sin knob tools-off — corre en sandbox read-only" % eng


def _tok(nchars):
    return max(1, int(nchars) // CHARS_PER_TOKEN)


def _fmt_tok(n):
    return "%.1fk" % (n / 1000.0) if n >= 1000 else str(n)


# ── la pasada ────────────────────────────────────────────────────────────────
def run(brain, params, progress=None, should_cancel=None, timeout=None,
        backend_override=None, model=None, dry_run=False):
    """Corre la pasada de personalización sobre `brain` (ya scaffoldeado).
    JAMÁS levanta y JAMÁS deja el cerebro a medias: la aplicación es todo-o-
    rollback (si una escritura falla, restaura lo ya escrito desde los
    originales en memoria). Cierra SIEMPRE sus 3 pasos vía `progress`.

    Devuelve dict honesto:
      {ran, ok, files, skipped, warns, tokens_est:{in,out,total}, backend,
       tools, note, dur_s}
    `ok=False` significa «quedó con la plantilla» — el agente sigue completo."""
    t0 = time.monotonic()
    res = {"ran": True, "ok": False, "files": [], "skipped": [], "warns": [],
           "tokens_est": {"in": 0, "out": 0, "total": 0}, "backend": "",
           "tools": "", "note": "", "dur_s": 0.0}
    p = dict(params or {})
    name = str(p.get("name", "")).strip().lower()
    display = str(p.get("display") or name.capitalize() or "agente")
    owner = str(p.get("owner", "")).strip().lower()
    rerun_hint = "córrelo luego: python3 agent_personalize.py %s" % (name or
                                                                     "<agente>")

    def _skip(key_from, st, note):
        """Cierra los pasos desde `key_from` en adelante con el mismo estado."""
        seen = False
        for k, _lbl in STEPS:
            if k == key_from:
                seen = True
            if seen:
                _prog(progress, k, st if k == key_from else "skip",
                      note if k == key_from else "")

    def _cxl():
        try:
            return bool(should_cancel and should_cancel())
        except Exception:
            return False

    try:
        # ── 1 · reunir identidad + datos ──
        _prog(progress, "perso-prep", "run")
        brain = os.path.abspath(os.path.expanduser(brain or ""))
        if not os.path.isdir(brain):
            res["note"] = "cerebro inexistente: %s" % brain
            _skip("perso-prep", "warn", "sin personalizar — " + res["note"])
            return res
        fields = collect_fields(p)
        # sin datos más allá del nombre no hay nada que personalizar — honesto
        if len([1 for lbl, _v in fields
                if lbl not in ("nombre corto (slug)",)]) < 2:
            res["note"] = "sin datos del formulario que personalizar"
            _skip("perso-prep", "skip", res["note"] + " — plantilla tal cual")
            return res
        tg = targets(owner)
        files = {}
        for rel in tg:
            path = os.path.join(brain, *rel.split("/"))
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as fh:
                        files[rel] = fh.read()
                except Exception:
                    res["warns"].append("%s: ilegible — fuera de la pasada"
                                        % rel)
            elif rel.startswith("STATE/users/"):
                files[rel] = None            # nuevo: el modelo puede crearlo
        if not files:
            res["note"] = "no encontré archivos de identidad en el cerebro"
            _skip("perso-prep", "warn", "sin personalizar — " + res["note"])
            return res
        backend, tools, bnote = pick_backend(backend_override
                                             or p.get("engine"))
        if backend is None:
            res["note"] = bnote
            _skip("perso-prep", "warn",
                  "sin personalizar — %s · %s" % (bnote, rerun_hint))
            return res
        res["backend"], res["tools"] = backend, tools
        if bnote:
            res["warns"].append(bnote)
        prompt = build_prompt(name, display, fields, files, owner)
        if len(prompt) > MAX_PROMPT_CHARS:
            res["note"] = "prompt demasiado grande (%d chars)" % len(prompt)
            _skip("perso-prep", "warn", "sin personalizar — " + res["note"])
            return res
        tin = _tok(len(prompt))
        res["tokens_est"]["in"] = tin
        _prog(progress, "perso-prep", "ok",
              "%d archivos · %d campos · ~%s tok in (est.)"
              % (len(files), len(fields), _fmt_tok(tin)))

        # ── 2 · redactar con el modelo ──
        if _cxl():
            res["note"] = "cancelado antes del modelo"
            _skip("perso-modelo", "skip", "cancelado — plantilla tal cual")
            return res
        if dry_run:
            res["ok"] = True
            res["note"] = "dry-run: prompt listo, modelo NO invocado (0 tokens)"
            res["_prompt"] = prompt
            _skip("perso-modelo", "skip", res["note"])
            return res
        _prog(progress, "perso-modelo", "run", "harness %s" % backend)
        import headless
        try:
            tmo = int(timeout or os.environ.get(
                "WORKSPACE_PERSONALIZE_TIMEOUT", DEFAULT_TIMEOUT))
        except Exception:
            tmo = DEFAULT_TIMEOUT
        try:
            ok, out = headless.run_headless(
                prompt, backend=backend, model=model or
                p.get("personalize_model"), tools=tools, cwd=brain,
                timeout=tmo)
        except Exception as e:                   # Security/Unknown/Value — config
            ok, out = False, "%s: %s" % (type(e).__name__, e)
        if not ok:
            res["note"] = str(out)[:200]
            _prog(progress, "perso-modelo", "warn",
                  "sin personalizar — %s" % rerun_hint)
            _prog(progress, "perso-aplicar", "skip", "plantilla tal cual")
            return res
        tout = _tok(len(out))
        res["tokens_est"]["out"] = tout
        res["tokens_est"]["total"] = tin + tout
        _prog(progress, "perso-modelo", "ok",
              "~%s tok (in+out, est. por chars)" % _fmt_tok(tin + tout))

        # ── 3 · validar + aplicar (todo-o-rollback) ──
        _prog(progress, "perso-aplicar", "run")
        if _cxl():
            res["note"] = "cancelado antes de aplicar"
            _prog(progress, "perso-aplicar", "skip",
                  "cancelado — plantilla tal cual")
            return res
        blocks, warns = parse_blocks(out, tg)
        res["warns"].extend(warns)
        # 03-RULES: prefijo (las reglas) byte-idéntico o se rechaza el archivo
        if "BOOT/03-RULES.md" in blocks:
            orig = files.get("BOOT/03-RULES.md") or ""
            if not _rules_prefix_ok(orig, blocks["BOOT/03-RULES.md"]):
                res["warns"].append("BOOT/03-RULES.md: tocó algo fuera del "
                                    "Scope — se conserva el template")
                del blocks["BOOT/03-RULES.md"]
        if not blocks:
            res["note"] = "la respuesta no trajo archivos válidos"
            _prog(progress, "perso-aplicar", "warn",
                  "sin personalizar — %s · %s" % (res["note"], rerun_hint))
            return res
        written, originals = [], {}
        try:
            for rel in sorted(blocks):
                path = os.path.join(brain, *rel.split("/"))
                rp = os.path.realpath(path)
                if not rp.startswith(os.path.realpath(brain) + os.sep):
                    raise IOError("ruta fuera del cerebro: %s" % rel)
                originals[rel] = files.get(rel)      # None = no existía
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + ".tmp-perso-%d" % os.getpid()
                with open(tmp, "w", encoding="utf-8") as fh:
                    fh.write(blocks[rel])
                os.replace(tmp, path)
                written.append(rel)
        except Exception as e:                       # ROLLBACK: nada a medias
            for rel in written:
                path = os.path.join(brain, *rel.split("/"))
                try:
                    if originals.get(rel) is None:
                        os.remove(path)
                    else:
                        with open(path, "w", encoding="utf-8") as fh:
                            fh.write(originals[rel])
                except Exception:
                    pass
            res["note"] = "falló al escribir (%s) — revertido, plantilla " \
                          "intacta" % e
            _prog(progress, "perso-aplicar", "warn",
                  "sin personalizar — revertido · %s" % rerun_hint)
            return res
        res["files"] = written
        res["skipped"] = [r for r in sorted(files) if r not in written]
        res["ok"] = True
        res["dur_s"] = round(time.monotonic() - t0, 1)
        _write_receipt(brain, res, fields, model or p.get("personalize_model"))
        extra = " · %d avisos" % len(res["warns"]) if res["warns"] else ""
        _prog(progress, "perso-aplicar", "ok",
              "%d archivo(s) · ~%s tok (est.)%s"
              % (len(written), _fmt_tok(res["tokens_est"]["total"]), extra))
        return res
    except Exception as e:                           # red de seguridad total
        res["note"] = "%s: %s" % (type(e).__name__, e)
        _skip("perso-prep", "warn", "sin personalizar — error interno")
        return res
    finally:
        res["dur_s"] = res["dur_s"] or round(time.monotonic() - t0, 1)


def _write_receipt(brain, res, fields, model):
    """Recibo auditable en <brain>/.workspace/personalize.json (falla-suave)."""
    try:
        path = os.path.join(brain, ".workspace", "personalize.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "backend": res["backend"], "tools": res["tools"],
            "model": model or "(default del harness)",
            "files": res["files"], "skipped": res["skipped"],
            "warns": res["warns"],
            "tokens_est": dict(res["tokens_est"],
                               nota="estimado por chars (~%d chars/token); "
                                    "el modo headless no reporta usage real"
                                    % CHARS_PER_TOKEN),
            "campos_usados": [lbl for lbl, _v in fields],
            "dur_s": res["dur_s"],
        }
        tmp = path + ".tmp-%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        pass


# ── estimación para la UI (antes de correr — honesta, marcada estimado) ──────
def estimate_for_template(template_root):
    """Tokens ESTIMADOS de una pasada sobre el template (para la caja de costo
    de la TUI, antes de crear). in = prompt (archivos destino + overhead);
    out ≈ los mismos archivos reescritos. None si no se puede medir."""
    try:
        total = 0
        for rel in BASE_TARGETS:
            path = os.path.join(template_root, *rel.split("/"))
            if os.path.isfile(path):
                total += os.path.getsize(path)
        if not total:
            return None
        tin = _tok(total + 3500)       # + reglas del prompt y campos típicos
        tout = _tok(total)             # reescribe ~los mismos archivos
        return {"in": tin, "out": tout, "total": tin + tout,
                "nota": "estimado por chars (~%d chars/token)"
                        % CHARS_PER_TOKEN}
    except Exception:
        return None


# ── CLI: la re-corrida del «córrelo luego» ──────────────────────────────────
def _resolve_brain(ident):
    """<agente registrado> o <carpeta> → (brain, params base desde la def)."""
    ident = (ident or "").strip()
    brain = None
    if os.path.isdir(os.path.expanduser(ident)):
        brain = os.path.abspath(os.path.expanduser(ident))
    else:
        try:
            import agentsreg
            reg = agentsreg.find(ident.lower())
            if reg:
                brain = reg["brain"]
        except Exception:
            pass
    if not brain:
        return None, {}
    params = {}
    try:
        import agentsreg
        d = agentsreg.load_definition(brain) or {}
        for k in ("name", "display", "tagline", "owner", "engine"):
            if d.get(k):
                params[k] = d[k]
    except Exception:
        pass
    return brain, params


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.split("\n\n")[0])
        print("\nuso: agent_personalize.py <agente|carpeta> [--engine X] "
              "[--model M]\n     [--dry-run] [--show-prompt] "
              "[--campo clave=valor ...]")
        return 2
    ident, engine, model = args[0], None, None
    dry, show = False, False
    extra = {}
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--engine" and i + 1 < len(args):
            engine = args[i + 1]; i += 2
        elif a == "--model" and i + 1 < len(args):
            model = args[i + 1]; i += 2
        elif a == "--dry-run":
            dry = True; i += 1
        elif a == "--show-prompt":
            show, dry = True, True; i += 1
        elif a == "--campo" and i + 1 < len(args) and "=" in args[i + 1]:
            k, v = args[i + 1].split("=", 1)
            extra[k.strip()] = v.strip(); i += 2
        else:
            print("argumento desconocido: %s" % a); return 2
    brain, params = _resolve_brain(ident)
    if not brain:
        print("no encontré el agente/carpeta: %s" % ident)
        return 1
    params.update(extra)
    params["personalize"] = True

    def _p(key, st, note=""):
        print("  %-14s %-5s %s" % (key, st, note))

    print("personalizar «%s» (%s)%s" % (params.get("display") or ident, brain,
                                        " — DRY-RUN" if dry else ""))
    res = run(brain, params, progress=_p, backend_override=engine,
              model=model, dry_run=dry)
    if show and res.get("_prompt"):
        print("\n── PROMPT ──\n%s" % res["_prompt"])
    print("\nresultado: %s" % ("ok" if res["ok"] else
                               "sin personalizar (%s)" % (res["note"] or "?")))
    if res["files"]:
        print("archivos: %s" % ", ".join(res["files"]))
    for w in res["warns"]:
        print("aviso: %s" % w)
    t = res["tokens_est"]
    if t["total"]:
        print("tokens: ~%s in + ~%s out = ~%s (estimado por chars)"
              % (_fmt_tok(t["in"]), _fmt_tok(t["out"]), _fmt_tok(t["total"])))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
