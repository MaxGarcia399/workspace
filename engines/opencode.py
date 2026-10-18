"""WORKSPACE · engines/opencode.py — motor OpenCode (SST · CLI `opencode`).

Hace ejecutable un agente sobre el CLI oficial `opencode` (opencode.ai), que es
AGNÓSTICO de modelo: el socio conecta un proveedor (OpenRouter, Anthropic,
OpenAI, su gateway Zen…) con `opencode auth login`. Vendor-neutral, enchufable
por nombre — dispatch.py lo carga solo ("opencode" → engines/opencode.py); NO se
toca el dispatcher (engines/CONTRACT.md).

🔴 INVARIANTE DE SEGURIDAD (mismo de connectors/codex): las credenciales del
socio las gestiona el BINARIO OFICIAL con su propio `opencode auth` — WORKSPACE
JAMÁS lee, extrae ni reusa tokens. El estado se consulta solo por presencia del
binario (el login lo resuelve opencode).

Tres formas de correr (contrato de WORKSPACE):
  · INTERACTIVO — `launch()`: banner + wrapper neutral
    (interactive.run_official_cli_interactive: session_start → TUI `opencode` en
    el cerebro → session_end). Es el `dispatch.py <agente> --engine opencode`.
  · HEADLESS one-shot — `run_turn()`: `opencode run -m <modelo> --format json`
    (salida JSONL de eventos; se concatenan los `type:"text"`). VERIFICADO con
    el binario real 2.0.29 (OpenRouter) — `OPENCODE_OK`/`PONG`.
  · INGESTA — sesiones crudas en ~/.local/share/opencode/opencode.db (SQLite,
    como Antigravity). La captura usa el export OFICIAL (`opencode session
    export <id>`, ver session_continuity.capture_opencode), sin leer el .db.

Contexto: opencode respeta la convención `AGENTS.md` (igual que codex) → el
adapter genera un AGENTS.md PUNTERO al doc de identidad, con la MISMA marca
WORKSPACE:GENERATED que codex (ambos la re-sincronizan idempotente; jamás
duplican la identidad — el cerebro es la única fuente de verdad).

Flags CONFIRMADOS contra `opencode run --help` (2.0.29): `-m/--model`
(provider/model), `--format {default,json}`. Modelo default del socio en
~/.config/opencode/opencode.json (no se toca aquí).

Cero dependencias (stdlib, 3.9+). Mac/Windows. Falla-suave.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

META = {"name": "opencode", "needs": ["opencode"], "auth": "api-key"}

#: Matriz de capacidades (contrato harness-os §3; la consume harnesses.py).
#: TODAS las claves de capabilities.ENGINE_KEYS (lo exige test_capabilities).
CAPABILITIES = {
    "launch": "wrapper",          # TUI oficial envuelto en el ciclo neutral
    "inject_context": "project-doc",  # AGENTS.md puntero → doc de identidad
    "mcp": True,                  # opencode soporta MCP (config `mcp` de opencode.json)
    "hooks": "wrapper",           # solo inicio/cierre del wrapper neutral; sus
                                  # hooks/plugins nativos NO se cablean (doble disparo)
    "sessions": "workspace",      # pestañas del registro neutral: opencode crea la
                                  # sesión, se ata al cerrar y se retoma con --session
                                  # (VERIFICADO 1.19.3 y 2.0.30)
    "status_live": False,         # sin now.json desde dentro (sin hooks por turno)
    "headless": True,             # run_turn (opencode run --format json, VERIFICADO)
    "statusline": False,          # v1: su barra nativa; WORKSPACE no la configura
}

BINARY = "opencode"

#: Versiones del CLI oficial con las que se VERIFICARON las lecturas de este
#: adapter (engine_versions: doctor avisa si la instalada es de otra línea).
#: Al verificar una versión nueva, agrégala aquí (runbooks/agregar-motor.md).
#: 2.0.29 (macOS) · 2.0.30 (Windows, npm @opencode/cli) · 1.19.3 (Windows,
#: npm `opencode-ai`, la que instala opencode.ai/install).
VERIFIED_VERSIONS = ("1.19.3", "2.0.29", "2.0.30")
#: opencode tiene DOS líneas vivas (2026-10-16): la 1 (`opencode-ai`,
#: opencode.ai/install, 1.19.x) y la 2 (`@opencode/cli`, opencode.ai/v2). Las
#: dos sirven con el MISMO método: la pestaña nueva abre sin id, opencode crea
#: su sesión y Workspace la ata al cerrar (find_new_session); al reabrir,
#: `--session <id>`. Antes de la 1.19 no hay `session list --format json` ni
#: `export` como se usan aquí.
MIN_SUPPORTED = "1.19.0"
UPGRADE_HINT = ("tu opencode es muy viejo para Workspace: actualízalo (npm install -g "
                "opencode-ai@latest, o la línea 2: npm install -g @opencode/cli "
                "--allow-scripts=@opencode/cli) o abre Motores › opencode › instalar")

# 🔴 EL HARNESS NO FIJA MODELO (regla de producto, 2026-10-15). El modelo lo elige
# el socio 100% vía la config NATIVA de opencode (~/.config/opencode) — este
# adapter JAMÁS pasa `-m` en el launch, ni lee/copia esa config. En run_turn,
# `model` es solo un override OPCIONAL para smokes/eval (nunca un default).


def _exe(override=None):
    """Ruta al binario. override=None → PATH; override="" → no hay (tests);
    override="/ruta" → esa ruta."""
    if override is None:
        return shutil.which(BINARY)
    return override or None


#: Una línea de `opencode auth list` con un proveedor conectado termina en su
#: tipo de credencial (VERIFICADO 2.0.29: «OpenRouter  OpenRouter   stored»).
_AUTH_LINE = re.compile(r"\b(stored|oauth|api(?:[ _-]?key)?|env|wellknown)\s*$", re.I)
#: Resumen de `auth list` (VERIFICADO 1.19.1: «└  1 credentials»).
_AUTH_COUNT = re.compile(r"\b(\d+)\s+credentials?\b", re.I)
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _auth_signal(runner=None, exe=None):
    """Señal de auth SIN tocar credenciales: `opencode auth list` lista un
    proveedor conectado. Jamás lee tokens. Devuelve la primera línea de
    proveedor, '' si no hay ninguno, o None si no se pudo saber.
    `runner`/`exe` son knobs de test."""
    exe = exe or _exe()
    if not exe:
        return ""
    try:
        cmd = [exe, "auth", "list"]
        if runner is not None:
            r = runner(cmd)
        else:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                               encoding="utf-8", errors="replace",
                               stdin=subprocess.DEVNULL, env=_env_motor())
        if getattr(r, "returncode", 0) != 0:
            return None
        lines = [_ANSI.sub("", ln).strip()
                 for ln in (getattr(r, "stdout", "") or "").splitlines()]
        hit = next((ln for ln in lines if ln and _AUTH_LINE.search(ln)), "")
        if hit:
            return hit[:80]
        m = next((_AUTH_COUNT.search(ln) for ln in lines
                  if _AUTH_COUNT.search(ln)), None)
        if m:                            # formato nuevo: «N credentials»
            return m.group(0) if int(m.group(1)) > 0 else ""
        # Salida con texto pero sin NINGUNA forma conocida: el CLI cambió su
        # formato. «No sé» (None) — jamás «sin sesión» a ciegas: eso escondía
        # un proveedor conectado (opencode 1.19.1, 2026-10-15).
        return None if any(lines) else ""
    except Exception:
        return None


def session_active(exe_override=None, runner=None):
    """¿Hay un proveedor conectado en opencode? True/False, o None si no se
    pudo saber (la UI lo muestra como desconocido, jamás «activa» a ciegas).
    Sin binario → False. Antes miraba solo el binario: Motores decía «sesión
    activa» sin login y ocultaba «iniciar sesión»."""
    exe = _exe(exe_override)
    if not exe:
        return False
    sig = _auth_signal(runner=runner, exe=exe)
    return None if sig is None else bool(sig)


def available(exe_override=None):
    """LISTO para ejecutar agentes: binario en PATH (opencode resuelve el login)."""
    return bool(_exe(exe_override))


def version_line(exe=None, runner=None):
    """Línea de opencode instalada (1 o 2), o None si no se pudo leer
    (entonces se asume la 2, la verificada con ids asignados)."""
    exe = exe or _exe()
    if not exe:
        return None
    try:
        import engine_versions
        v = engine_versions.parse(engine_versions.installed_version(exe, runner=runner))
        return v[0] if v else None
    except Exception:
        return None


def export_cmd(exe, sid, runner=None):
    """Export OFICIAL de una sesión: `opencode export <id>` en la 1 (1.19.3:
    `session` solo trae list/delete) y `opencode session export <id>` en la 2.
    El JSON es el mismo ({info, messages})."""
    # La versión es la del binario real (cacheada); `runner` es solo para el
    # export de quien llama (pruebas, Vigía).
    if version_line(exe) == 1:
        return [exe, "export", sid]
    return [exe, "session", "export", sid]


def _sin_consola():
    """Windows: la captura al cerrar corre SIN consola. Tras salir de opencode
    con Ctrl+C, un proceso nuevo colgado de esa consola falla al arrancar
    (0xC0000142): no se encontraba la sesión y no había respaldo ni maleta
    (prueba real 2026-10-17)."""
    return ({"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            if os.name == "nt" else {})


def _env_motor():
    """El env para correr el CLI del motor: sin NADA de la bóveda
    (secret_store.engine_env). Falla-suave: sin secret_store, el heredado."""
    try:
        import secret_store
        return secret_store.engine_env()
    except Exception:
        return None


def _list_sessions(exe, cwd=None, runner=None, n=30, strict=False):
    """`opencode session list --format json -n N` → [{id, created, …}] o [].
    strict=True: None si no se pudo saber (el CLI falló o no se entiende su
    salida), para no confundir «no hay» con «no sé»."""
    cmd = [exe, "session", "list", "--format", "json", "-n", str(n)]
    try:
        if runner is not None:
            r = runner(cmd, cwd=cwd)
        else:
            r = subprocess.run(cmd, cwd=cwd or None, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30,
                               stdin=subprocess.DEVNULL, env=_env_motor(), **_sin_consola())
        out = getattr(r, "stdout", "") or ""
        if strict and (getattr(r, "returncode", 1) != 0 or "[" not in out):
            return None
        data = json.loads(out[out.find("["):]) if "[" in out else []
        return [s for s in data if isinstance(s, dict) and _valid_session_id(s.get("id"))]
    except Exception:
        return None if strict else []


#: Ids que inventaba Workspace con opencode 2.0.29 (new_session_id).
_LEGACY_PREFIX = "ses_ws"


def _legacy_missing(exe, sid, cwd=None, runner=None):
    """Esquema viejo (2.0.29): Workspace inventaba el id `ses_ws…` y lo ataba
    a la pestaña ANTES de abrir; si se cerró sin un turno, esa sesión nunca
    existió y `--session` falla («Session not found» en la 1; en 2.0.30+ una
    sesión creada así ignora el modelo por defecto). True solo si opencode
    CONFIRMA que no la tiene; con cualquier duda, False (se retoma)."""
    if not str(sid or "").startswith(_LEGACY_PREFIX):
        return False
    lst = _list_sessions(exe, cwd=cwd, runner=runner, n=1000, strict=True)
    return lst is not None and sid not in {s["id"] for s in lst}


def session_marker(cfg, tab_name):
    """Marca de la pestaña en el mensaje de arranque (opencode 1): con dos
    pestañas abriendo a la vez, distingue cuál sesión es de cuál."""
    return "pestaña «%s» de %s" % (tab_name, cfg.get("display") or cfg.get("name") or "?")


def _first_user_text(export):
    """Primer mensaje del socio en el export oficial, en los DOS formatos que ya
    lee neutral_transcript.parse_opencode: opencode 1 ({info: {role}, parts:
    [{text}]}) y opencode 2 ({type: "user", text}; VERIFICADO 2.0.29 en Mac,
    2026-10-18). Antes solo leía el 1: con la 2 nunca encontraba la marca de la
    pestaña, la sesión no se ataba y el cierre quedaba sin maleta ni retome."""
    for m in (export or {}).get("messages") or []:
        if not isinstance(m, dict):
            continue
        info = m.get("info")
        if isinstance(info, dict):
            if info.get("role") == "user":
                return " ".join(str(p.get("text") or "") for p in m.get("parts") or []
                                if isinstance(p, dict))
            continue
        if m.get("type") == "user" and isinstance(m.get("text"), str):
            return m["text"]
    return ""


def find_new_session(exe, find, cwd=None, runner=None):
    """opencode 1: la sesión que creó ESTA pestaña. `find` = {t0, before,
    marker}: candidatas = ids nuevos (no estaban antes de abrir) creados
    después de t0; de ellas, la que tiene la marca de la pestaña en su primer
    mensaje (también si es una sola). Sin marca, solo una candidata única.
    Ambigua o ninguna → '' (no se adivina)."""
    t0 = float((find or {}).get("t0") or 0)
    before = set((find or {}).get("before") or [])
    cands = [s["id"] for s in _list_sessions(exe, cwd=cwd, runner=runner)
             if s["id"] not in before and float(s.get("created") or 0) / 1000.0 >= t0 - 5]
    if not cands:
        return ""
    marker = str((find or {}).get("marker") or "")
    if not marker:
        return cands[0] if len(cands) == 1 else ""
    # Con marca, se comprueba aunque haya UNA sola: si esta pestaña falló antes
    # de crear su conversación y otra pestaña creó una, no se la apropia
    # (Greptile, 2026-10-17).
    hits = []
    for sid in cands:
        try:
            cmd = export_cmd(exe, sid, runner=runner)
            if runner is not None:
                r = runner(cmd, cwd=cwd)
            else:
                r = subprocess.run(cmd, cwd=cwd or None, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=60,
                                   stdin=subprocess.DEVNULL, env=_env_motor(),
                                   **_sin_consola())
            out = getattr(r, "stdout", "") or ""
            data = json.loads(out[out.find("{"):]) if "{" in out else {}
            if marker in _first_user_text(data):
                hits.append(sid)
        except Exception:
            continue
    return hits[0] if len(hits) == 1 else ""


def unsupported(exe=None, runner=None):
    """'' si la versión instalada sirve; si no, el aviso para el socio
    (opencode 1 no abre sesiones de Workspace). Falla-suave: si no se puede
    leer la versión, no se bloquea."""
    exe = exe or _exe()
    if not exe:
        return ""
    try:
        import engine_versions
        if engine_versions.drift(sys.modules[__name__],
                                 engine_versions.installed_version(exe, runner=runner))[0] \
                == "unsupported":
            return UPGRADE_HINT
    except Exception:
        pass
    return ""


def status(exe_override=None, runner=None):
    """Estado honesto del motor (para doctor / plan / harnesses.registry). Solo
    inspecciona: binario en PATH + `opencode auth list` (sin tokens)."""
    exe = _exe(exe_override)
    viejo = unsupported(exe, runner=runner) if exe and exe_override is None else ""
    if viejo:
        return {"engine": "opencode", "binary": BINARY, "binary_in_path": True,
                "session_active": None, "ready": False, "auth": viejo, "detail": viejo}
    active = session_active(exe_override=exe or "", runner=runner) if exe else False
    return {"engine": "opencode", "binary": BINARY, "binary_in_path": bool(exe),
            "session_active": active,
            # ready = binario + proveedor (o desconocido: no se bloquea por
            # una lectura fallida; sí cuando opencode dice que no hay ninguno).
            "ready": bool(exe) and active is not False,
            "auth": "proveedor conectado vía `opencode auth` (OpenRouter/"
                    "Anthropic/…); WORKSPACE nunca ve el token"}


def _parse_run_json(text):
    """Extrae el texto del asistente del stream JSONL de `opencode run
    --format json`: concatena los eventos `type:"text"` (part.text). Si no hay
    JSON parseable, devuelve el texto crudo. Falla-suave."""
    parts = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or ln[0] != "{":
            continue
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if ev.get("type") == "text":
            t = ((ev.get("part") or {}).get("text") or "")
            if t:
                parts.append(t)
    return "".join(parts) if parts else (text or "")


def run_turn(prompt, *, model=None, cwd=None, timeout=120,
             exe_override=None, runner=None):
    """UN turno HEADLESS real: `opencode run -m <modelo> --format json
    <mensaje>`. La respuesta sale como JSONL de eventos; se concatena el texto
    (ver _parse_run_json). Devuelve (ok, texto). `runner`/`exe_override` son
    knobs de test (la suite jamás corre un opencode real ni toca la red)."""
    exe = _exe(exe_override)
    if not exe:
        return False, "opencode no está en PATH"
    cmd = [exe, "run", "--format", "json"]
    if model:
        cmd += ["-m", model]
    # El mensaje va como positional al final; `--` evita que un prompt que
    # empiece con `-` se cuele como flag.
    cmd += ["--", prompt or ""]
    try:
        if cwd:
            os.makedirs(cwd, exist_ok=True)
        import secret_store
        env = secret_store.engine_env()   # el motor no hereda la bóveda
        env["WORKSPACE_NO_AUTOUPDATE"] = "1"
        if runner is not None:
            r = runner(cmd, cwd=cwd or None, env=env, timeout=timeout)
        else:
            r = subprocess.run(cmd, cwd=cwd or None, env=env, timeout=timeout,
                               capture_output=True, stdin=subprocess.DEVNULL)
        rc = getattr(r, "returncode", 1)
        raw_out = getattr(r, "stdout", b"") or b""
        out = raw_out.decode("utf-8", "replace") if isinstance(raw_out, bytes) \
            else str(raw_out)
        if rc != 0:
            raw = getattr(r, "stderr", b"") or b""
            err = raw.decode("utf-8", "replace") if isinstance(raw, bytes) \
                else str(raw)
            return False, "opencode run exit %d: %s" % (rc, (err or out)[:300])
        return True, _parse_run_json(out)
    except subprocess.TimeoutExpired:
        return False, "opencode run: timeout tras %ss" % timeout
    except OSError as e:
        return False, "opencode run: no pude preparar la corrida: %s" % e
    except Exception as e:
        return False, "opencode run: fallo al invocar: %s" % e


# ═══════════════════════════════════════════════════════════════════════════
# inject_context — identidad del agente vía AGENTS.md (contrato harness-os §3)
# ═══════════════════════════════════════════════════════════════════════════
# opencode respeta AGENTS.md (misma convención que codex). El adapter genera en
# la raíz del cerebro un AGENTS.md PUNTERO al doc de identidad, con la MISMA
# marca WORKSPACE:GENERATED que codex (se importan sus detectores) → si el socio
# alterna codex↔opencode en el MISMO cerebro, cada launch re-sincroniza el
# puntero de forma idempotente, sin que un motor trate el archivo del otro como
# "del socio". JAMÁS reescribe la identidad (eso sería N3); un motor sin
# imports cuyo modelo puede no leer BRAIN.md (Hermes) pide además una COPIA
# GENERADA del núcleo (`embed`), regenerada en cada launch y nunca fuente.
# Bloque de SESIÓN de la pestaña activa: mismas marcas y mismo corte que codex
# (el AGENTS.md es compartido → un bloque que deja un motor lo limpia el otro).
# La lógica de anexar/limpiar replica codex.inject_context SIN tocar codex.py.

try:
    from engines.codex import (_GEN_MARK, _is_generated, _identity_doc,
                               DEFAULT_IDENTITY_DOC, _SESSION_START,
                               _SESSION_END, _split_session_block)
except Exception:        # pragma: no cover — defensa si codex cambia
    _GEN_MARK = "<!-- WORKSPACE:GENERATED inject_context v1 -->"
    DEFAULT_IDENTITY_DOC = "CLAUDE.md"
    _SESSION_START = ("<!-- WORKSPACE:SESSION start — contexto de la pestaña "
                      "activa; se regenera en cada launch -->")
    _SESSION_END = "<!-- WORKSPACE:SESSION end -->"

    def _identity_doc(cfg):
        d = str((cfg or {}).get("identity_doc") or "").strip()
        if not d or os.path.isabs(d) or "/" in d or "\\" in d or d.startswith(".."):
            return DEFAULT_IDENTITY_DOC
        return d

    def _is_generated(text):
        return (text or "").lstrip().startswith(_GEN_MARK)

    def _split_session_block(text):
        out, skip, found = [], False, False
        for ln in (text or "").splitlines(True):
            s = ln.strip()
            if not skip and s == _SESSION_START:
                skip, found = True, True
                continue
            if skip:
                if s == _SESSION_END:
                    skip = False
                continue
            out.append(ln)
        return "".join(out), found


def _atomic_write(path, text):
    tmp = path + ".workspace-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)                # escritura atómica


def _agents_doc_text(cfg, session_context="", engine="opencode", embed=""):
    """AGENTS.md generado: PUNTERO al doc de identidad. Dice el motor que corre
    (`engine`: opencode, openclaw…). `session_context` agrega el bloque
    GENERADO de la pestaña activa. `embed` (brain_identity.embed_core) =
    COPIA GENERADA del núcleo de identidad para motores sin imports cuyo
    modelo puede no leer BRAIN.md (Hermes): la fuente sigue siendo el cerebro."""
    doc = _identity_doc(cfg)
    name = str(cfg.get("display") or cfg.get("name") or "el agente")
    if embed:
        where = os.path.normpath(str(cfg.get("_brain") or "")) or "."
        return """%s
<!-- Archivo GENERADO por WORKSPACE (engines/%s.py · inject_context).
     NO editarlo a mano: el adapter lo re-sincroniza en cada launch.
     Si este cerebro deja de usarse con %s, puede borrarse sin efecto.
     La fuente de la identidad es %s y los archivos que copia abajo. -->

# Identidad de este workspace

Este directorio (`%s`) es el CEREBRO de **%s**: ese es tu cerebro. Las
carpetas del motor (su perfil y su configuración) no lo son. Su identidad,
reglas, memoria y protocolo de arranque viven en `%s` (raíz de este
directorio) y en los documentos que ese archivo indica.

AL INICIAR LA SESIÓN:

1. El núcleo de tu identidad (`%s` y sus documentos de arranque) ya está
   COPIADO abajo: adóptalo desde tu primera respuesta, con su carácter, su
   equipo y su tono. No te presentes como "%s" ni como un asistente
   genérico: eres %s corriendo sobre el motor %s.
2. Lo que `%s` manda leer y NO está copiado (estado vivo, memoria, wiki,
   skills) léelo con tus herramientas cuando toque.
3. Ante cualquier conflicto entre este archivo y `%s`, gana `%s`.

%s""" % (_GEN_MARK, engine, engine, doc, where, name, doc, doc, engine, name,
         engine, doc, doc, doc, embed.rstrip() + "\n") + (
            "" if not session_context else
            "\n%s\n%s\n%s\n" % (_SESSION_START, session_context, _SESSION_END))
    return """%s
<!-- Archivo GENERADO por WORKSPACE (engines/%s.py · inject_context).
     NO editarlo a mano: el adapter lo re-sincroniza en cada launch.
     Si este cerebro deja de usarse con %s, puede borrarse sin efecto.
     La identidad NO vive aquí: vive en %s (única fuente de verdad). -->

# Identidad de este workspace

Este directorio es el CEREBRO de **%s**. Su identidad, reglas, memoria y
protocolo de arranque viven en `%s` (raíz de este directorio) y en los
documentos que ese archivo indica.

AL INICIAR LA SESIÓN, ANTES DE CUALQUIER OTRA COSA:

1. Lee `%s` COMPLETO.
2. Sigue su secuencia de arranque (los documentos que manda leer, en orden)
   y adopta ESA identidad, reglas y tono. No te presentes como "%s" ni
   como un asistente genérico: eres %s corriendo sobre el motor %s.
3. Ante cualquier conflicto entre este archivo y `%s`, gana `%s`.
""" % (_GEN_MARK, engine, engine, doc, name, doc, doc, engine, name, engine,
       doc, doc) + (
        "" if not session_context else
        "\n%s\n%s\n%s\n" % (_SESSION_START, session_context, _SESSION_END))


def inject_context(cfg, session_context=""):
    """inject_context de opencode (ver inject_agents_md)."""
    return inject_agents_md(cfg, session_context=session_context, engine="opencode")


def _scan(check, text):
    try:
        return list(check(text) or [])
    except Exception:
        return []


def _first_clean(cfg, session_context, engine, embed, check, out):
    """Primera variante del AGENTS.md generado cuyo texto FINAL pasa `check`
    (ver inject_agents_md). Anota en `out` lo que se quitó."""
    variants = [(embed, session_context)]
    if session_context:
        variants.append((embed, ""))
    if embed:
        variants += [("", session_context)] + ([("", "")] if session_context else [])
    first = None
    for emb, ses in variants:
        text = _agents_doc_text(cfg, session_context=ses, engine=engine, embed=emb)
        found = _scan(check, text)
        if first is None:
            first = found
        if not found:
            if first:
                if session_context and not ses:
                    out["session_dropped"] = first
                if embed and not emb:
                    out["embed_dropped"] = first
            return text
    out["blocked"] = found
    return text


def inject_agents_md(cfg, session_context="", engine="opencode", embed="",
                     check=None):
    """Materializa la identidad del agente (contrato §3): AGENTS.md puntero en
    la raíz del cerebro + bloque INVISIBLE de la pestaña activa. Un AGENTS.md
    PROPIO del socio conserva su contenido: el bloque va ANEXADO (marcado,
    strip-antes-de-anexar, se limpia al cerrar). Devuelve {'ok','action':
    created|synced|kept|custom|skipped,'path','detail'} + 'session':'appended'
    cuando el bloque quedó en un doc del socio. Falla-suave: jamás levanta.

    `embed`: copia del núcleo de identidad (ver _agents_doc_text). `check(texto)
    -> [hallazgos]` del motor (Hermes bloquea el archivo ENTERO con un solo
    hallazgo): se escribe la PRIMERA variante cuyo texto final no tenga
    hallazgos — completa → sin el bloque de la pestaña (lo escriben el socio y
    el agente: checkpoints, títulos) → sin la copia → solo el puntero. Lo que se
    quitó va en `session_dropped` / `embed_dropped` (con los hallazgos); si ni
    el puntero solo pasa, se escribe igual y `blocked` lleva los hallazgos."""
    brain = (cfg or {}).get("_brain", "")
    out = {"ok": False, "action": "skipped", "path": "", "detail": ""}
    try:
        if not brain or not os.path.isdir(brain):
            out["detail"] = "sin cerebro resuelto"
            return out
        doc = _identity_doc(cfg)
        if not os.path.isfile(os.path.join(brain, doc)):
            out["detail"] = "no existe %s en el cerebro — nada que apuntar" % doc
            return out
        path = os.path.join(brain, "AGENTS.md")
        out["path"] = path
        want = _agents_doc_text(cfg, session_context=session_context, engine=engine,
                                embed=embed)
        if check is not None:
            want = _first_clean(cfg, session_context, engine, embed, check, out)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    cur = fh.read()
            except OSError as e:
                out["detail"] = "AGENTS.md ilegible: %s" % e
                return out
            if not _is_generated(cur):
                # Doc PROPIO del socio: su contenido se respeta; el bloque de
                # la pestaña va ANEXADO (marcado, efímero). strip-antes-de-
                # anexar: un bloque huérfano de un crash se limpia aquí.
                try:
                    base, had = _split_session_block(cur)
                    if session_context and check is not None:
                        joined = base.rstrip() + "\n\n%s\n%s\n%s\n" % (
                            _SESSION_START, session_context, _SESSION_END)
                        found = _scan(check, joined)
                        if found and not _scan(check, base):
                            # El bloque haría que el motor bloquee el doc
                            # del socio entero: va sin él.
                            out["session_dropped"] = found
                            session_context = ""
                    if session_context:
                        _atomic_write(path, base.rstrip() + "\n\n%s\n%s\n%s\n"
                                      % (_SESSION_START, session_context,
                                         _SESSION_END))
                        out.update(ok=True, action="custom", session="appended",
                                   detail="AGENTS.md del socio — bloque de sesión "
                                          "anexado (se limpia al cerrar)")
                    elif had:
                        _atomic_write(path, base.rstrip() + "\n")
                        out.update(ok=True, action="custom",
                                   detail="AGENTS.md del socio — bloque de "
                                          "sesión viejo limpiado")
                    else:
                        out.update(ok=True, action="custom",
                                   detail="AGENTS.md del socio — intacto")
                except Exception as e:
                    out.update(ok=True, action="custom",
                               detail="AGENTS.md del socio — anexo falló "
                                      "(%s: %s)" % (type(e).__name__, e))
                return out
            if cur == want:
                out.update(ok=True, action="kept")
                return out
            action = "synced"
        else:
            action = "created"
        _atomic_write(path, want)
        out.update(ok=True, action=action)
        return out
    except Exception as e:
        out["detail"] = "%s: %s" % (type(e).__name__, e)
        return out


def _banner(cfg):
    """Arranque visible mínimo (Windows-safe: sin glifos 0x2600–0x27BF)."""
    name = str(cfg.get("display") or cfg.get("name", "agente")).upper()
    tag = str(cfg.get("tagline", ""))
    C, D = "\033[38;5;170m", "\033[38;5;240m"
    try:                                   # tema del hub
        from engines import _ui
        C, D = _ui.theme_cols(C, D)
    except Exception:
        pass
    R = "\033[0m"; B = "\033[1m"
    bar = C + "═" * 52 + R
    try:
        sys.stdout.write("\033[2J\033[3J\033[H")
        print("\n  %s" % bar)
        print("    %s%s%s%s   %svía OpenCode%s" % (B, C, name, R, D, R))
        if tag:
            print("    %s%s%s" % (D, tag, R))
        print("  %s\n" % bar)
        sys.stdout.flush()
    except Exception:
        pass


# ── pestañas: la sesión la CREA opencode y Workspace la ata al cerrar ───────
# Antes (2.0.29) Workspace generaba el id y abría con `--session <id nuevo>`.
# Ya no: la 1 no acepta un id puesto desde fuera («Session not found»), y en la
# 2.0.30 una sesión creada así ignora el modelo por defecto y el plan gratuito
# falla («OpenCode's free tier can only be used from within OpenCode»,
# VERIFICADO en consola real). Abrir sin id es lo que hace opencode solo: la
# captura de cierre encuentra la sesión nueva (find_new_session, con la marca
# de la pestaña si hay varias) y se ata; al reabrir, `--session <id>` (las dos
# líneas retoman un id existente). new_session_id queda para pruebas y smokes.
_SESSION_FLAGS = ("-s", "--session", "-c", "--continue")


def _has_session_flag(passthrough):
    """¿El socio eligió sesión a mano? Su elección explícita gana."""
    for a in passthrough or []:
        a = str(a)
        if a in _SESSION_FLAGS or a.startswith("--session="):
            return True
    return False


def new_session_id():
    """Id nuevo para una pestaña: `ses_ws` + 24 hex (prefijo exigido)."""
    import uuid
    return "ses_ws" + uuid.uuid4().hex[:24]


def _session_from_passthrough(passthrough):
    """El id de `-s X` / `--session X` / `--session=X` que pasó el socio, o ''."""
    args = [str(a) for a in passthrough or []]
    for i, a in enumerate(args):
        if a.startswith("--session="):
            sid = a.split("=", 1)[1]
        elif a in ("-s", "--session") and i + 1 < len(args):
            sid = args[i + 1]
        else:
            continue
        return sid if _valid_session_id(sid) else ""
    return ""


def _valid_session_id(sid):
    import re
    return bool(re.fullmatch(r"ses[A-Za-z0-9_-]{4,96}", str(sid or "")))


def _interactive_argv(cfg, passthrough, session_id=""):
    """argv DESPUÉS de `opencode`: `--session <id>` de la pestaña + el
    passthrough del socio. El harness NO fija modelo — opencode usa el de la
    config nativa del socio (regla de producto 2026-10-15); un `-m` o `--session`
    que el socio pase a mano va tal cual y gana."""
    args = list(passthrough or [])
    if session_id and not _has_session_flag(args):
        return ["--session", session_id] + args
    return args


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    """Arranca un agente EN OPENCODE (interactivo). Delega al wrapper neutral de
    interactive.py (session_start → TUI `opencode` → session_end). plan=True NO
    lanza: imprime el wiring + chequeos."""
    brain = cfg.get("_brain", "")
    exe = _exe()
    viejo = "" if plan else unsupported(exe)
    if viejo:                      # mejor un aviso claro que un error crudo
        import engine_versions
        print("WORKSPACE: " + viejo)
        if not engine_versions.allow_anyway():
            sys.exit(1)            # dispatch ignora el return: rc≠0 visible

    if plan:
        line = "─" * 66
        print(line)
        print("  WORKSPACE · plan de arranque — motor OPENCODE — agente: %s"
              % cfg.get("display", cfg.get("name")))
        print(line)
        print("  motor       : opencode  (CLI oficial · agnóstico de modelo; "
              "login del socio por `opencode auth`; WORKSPACE nunca ve el token)")
        print("  modelo      : lo fija el SOCIO en su config de opencode "
              "(el harness no pasa -m)")
        print("  cerebro     : %s" % brain)
        print("  identidad   : AGENTS.md puntero → %s (inject_context; marca "
              "WORKSPACE:GENERATED compartida con codex)" % _identity_doc(cfg))
        print("  pestañas    : picker compartido + registro neutral — opencode crea "
              "la sesión, se ata al cerrar y se retoma con `--session`; memoria de la "
              "pestaña INVISIBLE en el AGENTS.md")
        print("  sesiones    : SQLite de opencode. Captura: snapshot del .db "
              "global (continuidad); esquema sin decodificar aún")
        print("  flujo       : pestaña → inject_context → banner → "
              "interactive.run_official_cli_interactive('opencode') → opencode "
              "(TUI en el cerebro, con el modelo de la config del socio)")
        print(line)
        print("  [%s] binario opencode en PATH: %s"
              % ("✓" if exe else "✗ FALTA", exe or
                 "(no está — Motores › opencode › instalar)"))
        if exe:
            viejo = unsupported(exe)
            try:
                import engine_versions
                ver = engine_versions.installed_version(exe) or "?"
            except Exception:
                ver = "?"
            print("  [%s] versión: %s%s" % ("✗" if viejo else "✓", ver,
                                            (" — " + viejo) if viejo else ""))
        print("  [%s] cerebro: %s"
              % ("✓" if brain and os.path.isdir(brain) else "✗ FALTA", brain))
        print(line)
        return

    if not exe:
        print("WORKSPACE: opencode no está en PATH — instálalo "
              "(Motores › opencode › instalar) y conecta un proveedor con "
              "`opencode auth login`.")
        sys.exit(1)

    # Pestañas NEUTRALES (sessions_registry): el MISMO picker que los demás
    # motores → misma lista de pestañas. El id de opencode de la pestaña sale
    # del registro; si no hay (pestaña nueva) se genera y se ata YA.
    tab, session_id, session_blk = None, "", ""
    agent = str(cfg.get("name") or "")
    cfg.setdefault("_engine", "opencode")
    # Etiqueta honesta ANTES del picker: sin esto el picker compartido (el de
    # Claude Code) y el banner decían «Claude Code». Sin modelo: lo elige el socio.
    os.environ["WORKSPACE_ENGINE_LABEL"] = "OpenCode · modelo de tu config"
    try:
        from engines import _ui
        import sessions_registry as _reg
        if not (preselect and preselect.get("wid")):
            from engines import claude_code as _cc0
            _cc0.session_preflight(cfg, "opencode")
        tab = _ui.pick_tab(cfg, preselect=preselect)
        if not tab:
            from engines import claude_code as _cc
            _cc.warn_no_tab(_cc.LAST_PICK_ERROR)
        if tab:
            wid, wname = tab
            _ui.export_tab_env(cfg, wid, wname)
            _reg.ensure_tab(brain, agent, wname, claude_wid=wid)
            session_id = _reg.resume_id(brain, agent, wname, "opencode") or ""
            if not _valid_session_id(session_id):
                session_id = ""
            elif _legacy_missing(exe, session_id, cwd=brain):
                # atada con el esquema viejo y nunca creada: se suelta y la
                # pestaña abre como nueva (la captura ata la que cree opencode)
                _reg.unbind(brain, agent, wname, "opencode", session_id)
                session_id = ""
            session_blk = _reg.session_doc_block(brain, wname, engine="opencode",
                                                 resumed=bool(session_id))
    except Exception as e:
        tab, session_id, session_blk = None, "", ""
        try:
            from engines import claude_code as _cc
            err = "no pude preparar la pestaña (%s: %s)" % (type(e).__name__, e)
            _cc._session_log(cfg, "opencode", err)
            _cc.warn_no_tab(err)
        except Exception:
            pass

    resumed = bool(session_id)
    find = None
    if _has_session_flag(passthrough):
        session_id = ""                    # el socio eligió sesión a mano
    elif tab and not session_id:
        # Pestaña nueva: abre sin id; la captura de cierre encuentra la sesión
        # que creó opencode (find_new_session) y se ata a la pestaña.
        find = {"t0": time.time(), "before": [s["id"] for s in _list_sessions(exe, cwd=brain)],
                "marker": session_marker(cfg, tab[1])}

    # inject_context (contrato §3): identidad + bloque de la PESTAÑA ACTIVA,
    # INVISIBLE (project doc). Solo si ni el anexo a un AGENTS.md del socio se
    # pudo escribir, la memoria cae al primer prompt (visible — último recurso).
    first_prompt = ""
    inj = inject_context(cfg, session_context=session_blk)
    if not inj.get("ok") and inj.get("detail"):
        print("WORKSPACE: identidad NO inyectada (%s) — opencode arrancará "
              "genérico." % inj["detail"])
    if tab and session_blk and inj.get("action") == "custom" \
            and not inj.get("session") and not resumed:
        try:
            import sessions_registry as _reg
            first_prompt = _reg.first_prompt_context(brain, tab[1], engine="opencode")
            print("WORKSPACE: no pude anexar la memoria al AGENTS.md del "
                  "socio — irá en el primer mensaje (visible).")
        except Exception:
            first_prompt = ""

    if show_banner:
        try:
            from engines import _ui
            _ui.show_brain_banner(cfg)
        except Exception:
            _banner(cfg)

    argv = _interactive_argv(cfg, passthrough, session_id=session_id)
    # Arranque del cerebro como codex/agy: un launch PELADO de una sesión
    # NUEVA arranca solo; al retomar no se inyecta nada (el hilo ya está). Un
    # prompt/flag del socio manda. VERIFICADO 2.0.29 (TUI real en un pty):
    # `--prompt` ENVÍA el mensaje al abrir (la sesión recibe turno + respuesta).
    if "--prompt" not in [str(a) for a in argv]:
        boot = first_prompt or ("" if (passthrough or resumed) else
                                "Lee %s e inicia el cerebro. Al terminar, confirma "
                                "en una línea breve." % _identity_doc(cfg))
        if boot and find:
            boot += " (%s)" % find["marker"]
        if boot:
            argv = argv + ["--prompt", boot]

    # La captura al cierre (session_continuity.capture_opencode) exporta ESTA
    # sesión: necesita su id real. `-c` (continuar la última) no lo dice →
    # captura honesta «missing».
    real_sid = session_id or _session_from_passthrough(passthrough)
    if real_sid:
        os.environ["WORKSPACE_OPENCODE_SESSION"] = real_sid
    else:
        os.environ.pop("WORKSPACE_OPENCODE_SESSION", None)
    if find:
        os.environ["WORKSPACE_OPENCODE_FIND"] = json.dumps(find)
    else:
        os.environ.pop("WORKSPACE_OPENCODE_FIND", None)

    _doc_dirty = []

    def _ctx_sink(ctx):
        # Contexto neutral de arranque → INVISIBLE al AGENTS.md junto con el
        # bloque de la pestaña; solo si no se pudo escribir, se imprime.
        try:
            merged = "\n\n".join(p for p in (session_blk, (ctx or "").strip()) if p)
            if not merged:
                return
            r = inject_context(cfg, session_context=merged)
            if r.get("ok") and (r.get("action") != "custom"
                                or r.get("session") == "appended"):
                _doc_dirty.append(True)
            elif (ctx or "").strip():
                print("[WORKSPACE · contexto de arranque]\n%s\n" % ctx.strip())
        except Exception:
            pass

    try:
        import interactive
        rc = interactive.run_official_cli_interactive(
            "opencode", brain=brain or None, argv=argv, context_sink=_ctx_sink,
            pending={"tab": tab[1] if tab else "", "agent": agent, "resume_id": session_id})
    except Exception as e:
        print("WORKSPACE: no pude lanzar opencode interactivo (%s: %s)"
              % (type(e).__name__, e))
        sys.exit(1)
    # La captura encontró la sesión de esta pestaña → se ata, y al reabrir la
    # pestaña se retoma con `--session <id>`.
    found = os.environ.get("WORKSPACE_OPENCODE_SESSION", "")
    if find and tab and _valid_session_id(found):
        try:
            import sessions_registry as _reg
            _reg.bind(brain, agent, tab[1], "opencode", found)
        except Exception:
            pass
    # Limpieza: el bloque de la pestaña era de ESTA corrida → se restaura el
    # puntero base (o se quita el anexo del doc del socio). Best-effort; un
    # crash deja un bloque que el siguiente launch limpia.
    if session_blk or _doc_dirty:
        try:
            inject_context(cfg)
        except Exception:
            pass
    try:
        import pending_runs
        pending_runs.done()               # atado y limpieza hechos: ya no está pendiente
    except Exception:
        pass
    sys.exit(rc if isinstance(rc, int) else 0)


def pick(cfg):
    """El picker de pestañas COMPARTIDO (registro neutral): la misma elección
    cruda ('WS\\t<wid>\\t<name>') que claude_code.pick — lo usa el hub tmux
    (mux.py). Falla-suave → ''."""
    try:
        from engines import _ui
        cfg.setdefault("_engine", "opencode")
        return _ui.pick_keep_label(cfg, "OpenCode · modelo de tu config")
    except Exception:
        return ""
