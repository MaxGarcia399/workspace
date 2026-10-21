"""WORKSPACE · engines/openclaw.py — motor OpenClaw (CLI `openclaw`, gateway de
agente personal con modo terminal local).

Hace ejecutable un agente sobre el CLI oficial `openclaw`: cada pestaña es un
`openclaw tui` conectado al GATEWAY del perfil de Workspace (un proceso por
perfil, dueño del estado). Vendor-neutral, enchufable por nombre — dispatch.py
lo carga solo ("openclaw" → engines/openclaw.py); NO se toca el dispatcher
(engines/CONTRACT.md).

🔴 VARIAS PESTAÑAS = GATEWAY (VERIFICADO 2026.9.33, Windows, 2026-10-16): desde
la 2026.9, `tui --local` exige ser el dueño EXCLUSIVO del estado del perfil;
con Zenith abierta, Turing fallaba con «state database is busy». El gateway lo
enciende y apaga un guardián (openclaw_gateway.py) según las
pestañas vivas. Si el gateway no se puede preparar, se cae al modo local de
una sola ventana (lo de antes), con aviso.

🔴 INVARIANTE DE SEGURIDAD: las credenciales las gestiona el BINARIO OFICIAL
(`openclaw … configure` / `models auth`). WORKSPACE jamás lee, copia ni reusa
tokens: solo pregunta `models status --json` (qué proveedores hay, sin llaves).

🔴 EL HARNESS NO FIJA MODELO (regla de producto, 2026-10-15): el modelo es el
que el socio eligió en la config de OpenClaw. Ni el launch ni run_turn pasan
`--model` salvo override explícito de smokes/eval.

🔴 MISMA ESTRUCTURA DE CEREBRO PARA TODOS LOS MOTORES (regla de producto): el
"workspace" de OpenClaw ES el cerebro y la identidad llega por el MISMO
`AGENTS.md` puntero que codex/opencode. OpenClaw por defecto CREA en su
workspace SOUL.md/IDENTITY.md/USER.md/BOOTSTRAP.md/HEARTBEAT.md/TOOLS.md
(VERIFICADO 2026.5.12: aparecieron 6 archivos). Por eso Workspace usa un
PERFIL PROPIO (`--profile workspace`, estado en ~/.openclaw-workspace, aparte
del OpenClaw personal del socio) con `agents.defaults.skipBootstrap: true`
(VERIFICADO: con eso el cerebro queda intacto) y su memoria nativa APAGADA
(memoryFlush, dreaming y el hook session-memory: si no, escribiría MEMORY.md,
memory/ y DREAMS.md en el cerebro). Un agente OpenClaw por agente de
Workspace, con workspace = su cerebro. La memoria larga del cerebro
(STATE/MEMORY.md, la de todos los motores) le llega por su hook oficial
`bootstrap-extra-files`; su búsqueda por significado (`memorySearch`) queda
apagada: indexar el cerebro mandaría sus notas a un servicio de embeddings.

Hechos VERIFICADOS con el binario 2026.5.12 (2026-10-15, perfiles desechables,
sin credenciales reales):
  · `tui --local --session agent:<id>:<clave>` elige el agente; la clave se
    mapea a un sessionId en agents/<id>/sessions/sessions.json (con
    `sessionFile`) y reabrir la misma clave CONTINÚA la misma sesión.
  · `tui --message <texto>` ENVÍA el mensaje al abrir (queda como turno user).
  · Transcript por sesión: agents/<id>/sessions/<sessionId>.jsonl (líneas
    session / message{role,content[{type:text}]} …) → parser neutral.
  · La credencial de `main` del perfil la RESUELVEN los demás agentes del
    perfil (sin copiarla): el socio conecta su proveedor UNA vez.
  · `agent --local --json` = turno headless; rc≠0 si falla (salida de éxito
    A-VERIFICAR: sin modelo real no se pudo observar).

Cero dependencias (stdlib, 3.9+). Mac/Windows. Falla-suave.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

META = {"name": "openclaw", "needs": ["openclaw"], "auth": "api-key"}

#: Matriz de capacidades (contrato harness-os §3). TODAS las claves de
#: capabilities.ENGINE_KEYS (lo exige test_capabilities).
CAPABILITIES = {
    "launch": "wrapper",              # TUI oficial (cliente del gateway del perfil) envuelto en el ciclo neutral
    "inject_context": "project-doc",  # AGENTS.md puntero (el mismo de codex/opencode)
    "mcp": True,                      # OpenClaw gestiona MCP (`openclaw mcp`)
    "hooks": "wrapper",               # solo inicio/cierre del wrapper; sus hooks nativos no se cablean
    "sessions": "workspace",          # pestaña ↔ clave `agent:<id>:ws-…` asignada por Workspace
    "status_live": False,
    "headless": True,                 # `agent --json` por el gateway; sin gateway, `--local`
    "statusline": False,
}

BINARY = "openclaw"

#: Versiones del CLI oficial con las que se VERIFICARON las lecturas de este
#: adapter (engine_versions: doctor avisa si la instalada es de otra línea).
#: Al verificar una versión nueva, agrégala aquí (runbooks/agregar-motor.md).
#: 2026.5.12 (agents.list[i]) · 2026.9.33 y 2026.10.4 (agents.entries.<id>,
#: gateway; 10.4 VERIFICADA en Windows con gateway el 2026-10-16).
VERIFIED_VERSIONS = ("2026.5.12", "2026.9.33", "2026.10.4")
#: Política «la más nueva por defecto» (2026-10-16): Workspace instala `latest`
#: y se adapta; solo frena un bug COMPROBADO, en su modo y plataforma, con la
#: salida «abrir de todos modos» (engine_versions.allow_anyway).
#: VERIFICADO 2026-10-16 en Windows: 2026.10.3, 2026.10.4 y 2026.10.10-beta.1
#: en `tui --local` → «history failed: #<Object> could not be cloned» e
#: «initial message not sent» (DataCloneError por el env Proxy de Windows,
#: regresión de openclaw#164354). Con el GATEWAY la 10.4 funciona (conecta,
#: responde y carga el historial): el bug solo pega en el modo de respaldo de
#: una ventana. Al verificar una versión que lo arregle, acota `to`.
KNOWN_BROKEN = (
    {"platforms": ("win32",), "modes": ("local",), "from": "2026.10.0", "to": "2026.10.99",
     "why": "OpenClaw 2026.10 tiene un bug en Windows en el modo de una sola ventana "
            "(sin gateway): no carga el historial ni envía mensajes",
     "hint": "revisa por qué no se pudo encender el gateway (workspace doctor), o "
             "usa la 2026.9.33: npm install -g openclaw@2026.9.33"},
)
#: Perfil PROPIO de Workspace (aísla estado/config en ~/.openclaw-<perfil>).
#: Env de override SOLO para tests (perfiles desechables).
PROFILE = os.environ.get("WORKSPACE_OPENCLAW_PROFILE", "").strip() or "workspace"
_KEY_PREFIX = "ws-"


def _profile():
    return os.environ.get("WORKSPACE_OPENCLAW_PROFILE", "").strip() or PROFILE


def _exe(override=None):
    """Ruta al binario. None → PATH; "" → no hay (tests); "/ruta" → esa."""
    if override is None:
        return shutil.which(BINARY)
    return override or None


def _base(exe):
    return [exe, "--profile", _profile()]


def state_dir():
    """Directorio de estado del perfil de Workspace (~/.openclaw-<perfil>)."""
    return os.path.join(os.path.expanduser("~"), ".openclaw-" + _profile())


def _env_motor():
    """El env para correr openclaw: sin NADA de la bóveda (secret_store.
    engine_env) — su turno `agent --local` ES el agente. Falla-suave."""
    try:
        import secret_store
        return secret_store.engine_env()
    except Exception:
        return None


def _run(cmd, runner=None, timeout=60, cwd=None):
    if runner is not None:
        return runner(cmd, cwd=cwd, timeout=timeout)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace", cwd=cwd,
                          stdin=subprocess.DEVNULL, env=_env_motor())


def _json_out(text):
    text = text or ""
    for opener in ("{", "["):
        i = text.find(opener)
        if i >= 0:
            try:
                return json.loads(text[i:])
            except ValueError:
                continue
    return None


# ── login / estado (sin leer credenciales) ─────────────────────────────────
def models_status(exe=None, runner=None, agent=None):
    """`models status --json` del perfil de Workspace → dict, o None si no se
    pudo leer. Solo metadatos (qué proveedores hay); jamás tokens."""
    exe = exe or _exe()
    if not exe:
        return None
    cmd = _base(exe) + ["models", "status", "--json"]
    if agent:
        cmd += ["--agent", agent]
    try:
        r = _run(cmd, runner=runner, timeout=30)
        if getattr(r, "returncode", 1) != 0:
            return None
        d = _json_out(getattr(r, "stdout", ""))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _auth_view(st):
    """(proveedores conectados, proveedores que faltan para el modelo actual)."""
    auth = (st or {}).get("auth") or {}
    provs = []
    for p in auth.get("providers") or []:
        provs.append(p.get("provider") if isinstance(p, dict) else str(p))
    missing = [str(m) for m in (auth.get("missingProvidersInUse") or [])]
    return [p for p in provs if p], missing


def session_active(exe_override=None, runner=None):
    """¿Hay un proveedor conectado en el perfil de Workspace? True/False, o
    None si no se pudo saber. Sin binario → False. Que el MODELO elegido use
    un proveedor sin conectar NO es «sin sesión»: es «falta elegir modelo»
    (status()['detail'], aviso al lanzar) — el harness no lo fija."""
    exe = _exe(exe_override)
    if not exe:
        return False
    st = models_status(exe=exe, runner=runner)
    if st is None:
        return None
    provs, _missing = _auth_view(st)
    return bool(provs)


def version_problem(exe=None, runner=None):
    """('', '') si la versión instalada sirve; si no (tipo, mensaje para el socio):
    · 'broken'  — bug conocido en esta plataforma (KNOWN_BROKEN);
    · 'profile' — el perfil de Workspace lo escribió una versión MÁS NUEVA que
      la instalada (OpenClaw no abre datos de un esquema más nuevo: «This
      OpenClaw build cannot open your existing data»), p. ej. tras volver a la
      versión verificada. Falla-suave: sin versión legible no se bloquea."""
    exe = exe or _exe()
    if not exe:
        return "", ""
    try:
        import engine_versions as EV
        v = EV.installed_version(exe, runner=runner)
        b = EV.broken(sys.modules[__name__], v)
        if b:
            return "broken", "%s — %s" % (b["why"], b["hint"])
        have = EV.parse(v)
        d = _profile_config() or {}
        touched = EV.parse(((d.get("meta") or {}).get("lastTouchedVersion")) or "")
        if have and touched and touched[:2] > have[:2]:
            return "profile", (
                "el perfil «%s» de OpenClaw lo creó la versión %s y la instalada es "
                "%s, que no puede abrirlo" % (_profile(), EV._fmt(touched), EV._fmt(have)))
    except Exception:
        pass
    return "", ""


def rebuild_profile():
    """Respalda el perfil de Workspace (lo RENOMBRA, jamás lo borra) para que se
    cree uno nuevo con la versión instalada. Devuelve la ruta del respaldo o ''.
    El proveedor hay que volver a conectarlo (la llave vivía en ese perfil)."""
    import time
    src = state_dir()
    if not os.path.isdir(src):
        return ""
    try:
        import openclaw_gateway as G
        if G.summary(_profile()).get("running"):
            G.shutdown(_exe(), _profile())
    except Exception:
        pass
    dst = "%s.respaldo-%s" % (src, time.strftime("%Y%m%d-%H%M%S"))
    try:
        os.replace(src, dst)
    except OSError:
        return ""
    # Las conversaciones quedaron en el respaldo (la versión instalada no puede
    # abrirlas): las pestañas que las apuntaban empiezan una sesión NUEVA, con
    # el arranque del cerebro, en vez de «retomar» algo que ya no existe.
    try:
        import sessions_registry
        sessions_registry.forget_engine("openclaw")
    except Exception:
        pass
    return dst


def status(exe_override=None, runner=None):
    """Estado honesto para doctor / plan / harnesses.registry. Solo inspecciona."""
    exe = _exe(exe_override)
    out = {"engine": "openclaw", "binary": BINARY, "binary_in_path": bool(exe),
           "profile": _profile(), "session_active": False, "ready": False,
           "auth": "proveedor conectado en el perfil `%s` de OpenClaw (Motores › "
                   "iniciar sesión); WORKSPACE nunca ve la llave" % _profile()}
    if not exe:
        return out
    try:
        import openclaw_gateway as G
        out["gateway"] = G.summary(_profile())
    except Exception:
        pass
    if exe_override is None:
        kind, msg = version_problem(exe, runner=runner)
        if kind:
            out.update(session_active=None, ready=False, detail=msg, version_problem=kind)
            return out
    st = models_status(exe=exe, runner=runner)
    if st is None:
        out.update(session_active=None, ready=True,
                   detail="no pude leer `models status` (se intenta al lanzar)")
        return out
    provs, missing = _auth_view(st)
    out["providers"] = provs
    out["model"] = st.get("resolvedDefault") or st.get("defaultModel") or ""
    out["session_active"] = bool(provs)
    out["ready"] = bool(provs) and not missing
    if not provs:
        out["detail"] = "sin proveedor conectado"
    elif missing:
        out["model_ready"] = False
        out["detail"] = ("falta elegir modelo: el modelo por defecto (%s) usa un "
                         "proveedor sin conectar (%s) — Motores › cuenta y proveedor"
                         % (out["model"], ", ".join(missing)))
    return out


def available(exe_override=None):
    return bool(_exe(exe_override))


# ── memoria propia suelta en la raíz del cerebro ───────────────────────────
#: OpenClaw carga en CADA turno el MEMORY.md de la raíz de su workspace (= el
#: cerebro) y escribe ahí su memoria propia (MEMORY.md, memory/). Esa memoria
#: está apagada en el perfil y el cierre aparta lo que toque cada corrida
#: (memoria.mover_raiz_openclaw), pero un cerebro que ya usaba OpenClaw puede
#: tener los de antes: OpenClaw los sigue leyendo como si fueran la memoria del
#: agente. El doctor lo dice y ofrece apartarlos (esta oferta de migrate).
MEMORIA_SUELTA = ("MEMORY.md", "memory")
MEMORIA_SUELTA_OFERTA = "202610200100_openclaw_memoria_suelta"


def memoria_suelta(brain):
    """Lo de MEMORIA_SUELTA que hay en la raíz del cerebro (nombres)."""
    return [n for n in MEMORIA_SUELTA if brain and os.path.exists(os.path.join(brain, n))]


def used_by(brain, name="", engine=""):
    """¿Este cerebro usa OpenClaw en ESTA máquina? Su motor (el que dice quien
    pregunta o, por el nombre, el de dispatch: ajuste por máquina > agent.json
    > registro) o alguna pestaña suya atada a una sesión de OpenClaw. Solo
    lee; falla-suave → False."""
    eng = str(engine or "").strip().lower()
    if not eng and name:
        try:
            import dispatch
            eng = dispatch._settings_agent_engine(name) or ""
            if not eng:
                entry = dispatch.find_agent(name) or {}
                eng = (dispatch.load_agent_cfg(entry) or {}).get("engine") \
                    or entry.get("engine") or ""
        except Exception:
            eng = ""
    if str(eng).strip().lower() == BINARY:
        return True
    try:
        import sessions_registry
        return BINARY in sessions_registry.engines_used(brain)
    except Exception:
        return False


# ── perfil y agente de Workspace dentro de OpenClaw ────────────────────────
def agent_id(cfg):
    """Id del agente OpenClaw para un agente de Workspace: su nombre saneado
    ([a-z0-9-]). `main` es el agente por defecto del perfil: se evita."""
    k = re.sub(r"[^a-z0-9-]+", "-", str((cfg or {}).get("name") or "").lower()).strip("-")
    k = k[:48] or "agente"
    return k + "-ws" if k == "main" else k


# REGLA VANILLA (producto): el setup de OpenClaw es del CLIENTE y queda tal
# como lo diseñó el proveedor (gateway, canales, modelos… los cambia él desde
# Motores › cuenta y proveedor). Workspace SOLO re-asegura lo que necesita del
# CEREBRO para funcionar (_BRAIN_SETTINGS, y la memoria larga del cerebro por
# el hook oficial: EXTRA_FILES) y que el workspace de SU agente sea el cerebro.
# Nada más.
# Jamás `agents delete`: «prune workspace/state» borraría el cerebro.

#: Config del perfil de Workspace que el CEREBRO necesita (excepción a la regla
#: vanilla; regla de estructura: un motor no crea archivos paralelos en el
#: cerebro). Claves VERIFICADAS con 2026.5.12: `config set` las acepta y quedan
#: en openclaw.json.
#:   · skipBootstrap → no crea SOUL/IDENTITY/USER/BOOTSTRAP/HEARTBEAT/TOOLS.
#:   · memoryFlush / dreaming / hook session-memory → su memoria nativa no
#:     escribe MEMORY.md, memory/ ni DREAMS.md en el cerebro (la memoria del
#:     agente es la común: STATE/).
_BRAIN_SETTINGS = (
    ("agents.defaults.skipBootstrap", True,
     "no crear archivos de identidad en tu cerebro"),
    ("agents.defaults.compaction.memoryFlush.enabled", False,
     "que su memoria no escriba en tu cerebro"),
    ("plugins.entries.memory-core.config.dreaming.enabled", False,
     "que su memoria no escriba en tu cerebro"),
    ("hooks.internal.entries.session-memory.enabled", False,
     "que su memoria no escriba en tu cerebro"),
)
_MISSING = object()

#: Memoria larga del CEREBRO en OpenClaw (la misma STATE/MEMORY.md que leen los
#: demás motores), con su hook oficial `bootstrap-extra-files`: carga esas rutas
#: como archivos de arranque en cada turno (doc instalada: automation/hooks.md
#: en 2026.5.12, automation/hooks/bundled-hooks.md en 2026.9.33). Las rutas son
#: relativas al workspace del agente (= el cerebro) y solo entran nombres de
#: arranque reconocidos; MEMORY.md lo es. VERIFICADO en el código de 2026.5.12:
#: los hooks internos los carga el GATEWAY al arrancar (server-startup-post-
#: attach); el modo local de una sola ventana y un turno sin ventana sin
#: gateway no los cargan, y en esos casos OpenClaw abre sin esta memoria.
#: La búsqueda por significado de OpenClaw (`memorySearch`, `extraPaths`) NO se
#: prende: para indexar el cerebro mandaría sus notas a un servicio externo de
#: embeddings. Solo se prendería si el socio lo pide (de preferencia, local).
_EXTRA_FILES_HOOK = "hooks.internal.entries.bootstrap-extra-files"
EXTRA_FILES = ("STATE/MEMORY.md",)


def _t(key, es, en=None, **kw):
    """i18n falla-suave (catálogo lang/<code>/motorbar.py → ES/EN inline)."""
    try:
        import workspace_status
        return workspace_status.t(key, es, en, **kw)
    except Exception:
        return es.format(**kw) if kw else es


def _get_path(d, dotted):
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return _MISSING
        cur = cur[k]
    return cur


def _brain_settings_ok(d):
    """¿El archivo del perfil ya trae TODOS los ajustes del cerebro?"""
    return isinstance(d, dict) and all(_get_path(d, p) is want
                                       for p, want, _why in _BRAIN_SETTINGS) \
        and _extra_files_ok(d)


def _str_list(v):
    """Lista de textos de la config (una lista, o un texto suelto), o None."""
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return [x for x in v if x.strip()]
    return None


def _extra_files_ok(d):
    """¿El hook bootstrap-extra-files está prendido y carga STATE/MEMORY.md?"""
    paths = _str_list(_get_path(d, _EXTRA_FILES_HOOK + ".paths")) or []
    return (_get_path(d, _EXTRA_FILES_HOOK + ".enabled") is True
            and all(p in paths for p in EXTRA_FILES))


def _extra_files_want(entry):
    """La lista `paths` que el hook debe tener: la del socio + la memoria del
    cerebro. El hook usa `paths` y, si está vacía, `patterns` o `files` (son
    alternativas, no se suman): las rutas del socio que vivían en esas pasan
    a `paths` para que no dejen de cargarse."""
    entry = entry if isinstance(entry, dict) else {}
    base = []
    for k in ("paths", "patterns", "files"):
        base = _str_list(entry.get(k)) or []
        if base:
            break
    return base + [p for p in EXTRA_FILES if p not in base], base

def _profile_config():
    """Config del perfil de Workspace leída DIRECTO del archivo
    (`~/.openclaw-<perfil>/openclaw.json`, JSON plano en 2026.5.12). None si
    falta o tiene otro formato → el caller usa el CLI (camino exacto). Cada
    consulta al CLI de OpenClaw cuesta 2-3 s (arranque de node): leer el
    archivo deja el arranque feliz sin ninguna."""
    try:
        with open(os.path.join(state_dir(), "openclaw.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _quick_ok(cfg, d):
    """¿El archivo ya dice que todo está como Workspace lo necesita? (ajustes
    del cerebro: sin creación de archivos ni memoria nativa escribiendo en él;
    agente con workspace = cerebro; y el modelo por defecto usa un proveedor
    conectado). Solo metadatos: jamás lee llaves."""
    if not _brain_settings_ok(d):
        return False
    agents = d.get("agents") if isinstance(d.get("agents"), dict) else {}
    defaults = agents.get("defaults") if isinstance(agents.get("defaults"), dict) else {}
    real = os.path.realpath((cfg or {}).get("_brain", "") or "")
    aid = agent_id(cfg)
    # Las dos formas de la config (como ensure_agent): 2026.9+ agents.entries.<id>
    # (dict) · hasta 2026.5.x agents.list[i]. Sin esto cada arranque en las
    # versiones nuevas tomaba el camino lento (varias consultas de node).
    ent = agents.get("entries") if isinstance(agents.get("entries"), dict) else {}
    rows = [dict(v, id=k) for k, v in ent.items() if isinstance(v, dict)]
    rows += [r for r in (agents.get("list") or []) if isinstance(r, dict)]
    if not any(r.get("id") == aid and
               os.path.realpath(os.path.expanduser(str(r.get("workspace") or ""))) == real
               for r in rows):
        return False
    profiles = ((d.get("auth") or {}).get("profiles") or {})
    provs = {str(p.get("provider")) for p in profiles.values()
             if isinstance(p, dict) and p.get("provider")}
    model = defaults.get("model")
    primary = model.get("primary") if isinstance(model, dict) else model
    return bool(primary) and str(primary).split("/", 1)[0] in provs


def _cfg_get(exe, path, runner=None):
    """(rc, stdout) de `config get <path>` en el perfil de Workspace."""
    r = _run(_base(exe) + ["config", "get", path], runner=runner, timeout=30)
    out = ((getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")).strip()
    return getattr(r, "returncode", 1), out


def _current(exe, path, d, runner):
    """Valor actual de `path`: del archivo si se pudo leer (rápido); si no,
    por `config get` (exacto). True/False, _MISSING (sin definir) u otro."""
    if isinstance(d, dict):
        return _get_path(d, path)
    rc, out = _cfg_get(exe, path, runner)
    last = out.splitlines()[-1].strip().lower() if out else ""
    if rc != 0 or not last:
        return _MISSING
    return {"true": True, "false": False}.get(last, last)


def ensure_profile(exe=None, runner=None):
    """Re-asegura (idempotente, en cada launch) los ajustes del CEREBRO
    (_BRAIN_SETTINGS) en el perfil PROPIO de Workspace. Si el cliente cambió
    alguno desde el setup completo, se restaura y se avisa. Nada más se toca
    (vanilla). Devuelve (ok, aviso): aviso = '' o una línea para el socio."""
    exe = exe or _exe()
    if not exe:
        return False, "openclaw no está en PATH"
    try:
        d = _profile_config()
        avisos = []
        for path, want, why in _BRAIN_SETTINGS:
            cur = _current(exe, path, d, runner)
            if cur is want:
                continue
            r = _run(_base(exe) + ["config", "set", path, "true" if want else "false"],
                     runner=runner, timeout=30)
            if getattr(r, "returncode", 1) != 0:
                return False, "no pude asegurar %s en el perfil %s" % (path, _profile())
            if cur is not _MISSING:          # estaba definido distinto: lo cambió alguien
                short = path.rsplit(".", 2)[-2] if path.endswith(".enabled") else path.rsplit(".", 1)[-1]
                avisos.append("restauré %s=%s (Workspace lo necesita para %s)"
                              % (short, "true" if want else "false", why))
        aviso = _ensure_extra_files(exe, d, runner)
        if aviso:
            avisos.append(aviso)
        return True, ("OpenClaw: " + "; ".join(avisos)) if avisos else ""
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def _ensure_extra_files(exe, d, runner=None):
    """Prende el hook oficial bootstrap-extra-files con la memoria del cerebro
    (EXTRA_FILES); lo que el socio tenga en su lista se conserva. Un solo
    `config set --batch-file` (el oficial, como el del gateway). '' o una línea
    de aviso. No es de seguridad: si no se puede, OpenClaw abre igual, sin esa
    memoria."""
    if isinstance(d, dict):
        entry = _get_path(d, _EXTRA_FILES_HOOK)
    else:
        rc, out = _cfg_get(exe, _EXTRA_FILES_HOOK, runner)
        entry = _json_out(out) if rc == 0 else {}
    entry = entry if isinstance(entry, dict) else {}
    want, base = _extra_files_want(entry)
    ops = []
    if entry.get("enabled") is not True:
        ops.append({"path": _EXTRA_FILES_HOOK + ".enabled", "value": True})
    if _str_list(entry.get("paths")) != want:
        ops.append({"path": _EXTRA_FILES_HOOK + ".paths", "value": want})
    if not ops:
        return ""
    fd, tmp = tempfile.mkstemp(prefix="ws-openclaw-mem-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(ops, fh)
        r = _run(_base(exe) + ["config", "set", "--batch-file", tmp], runner=runner, timeout=60)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if getattr(r, "returncode", 1) != 0:
        return _t("motorbar.openclaw.memory_failed",
                  "no pude prender la carga de la memoria larga (STATE/MEMORY.md): "
                  "OpenClaw abre sin ella",
                  "couldn't turn on loading the long-term memory (STATE/MEMORY.md): "
                  "OpenClaw opens without it")
    if entry.get("enabled") is False:
        return _t("motorbar.openclaw.memory_restored",
                  "volví a prender la carga de STATE/MEMORY.md (hook bootstrap-extra-files): "
                  "es la memoria larga de tu cerebro",
                  "turned loading STATE/MEMORY.md back on (bootstrap-extra-files hook): "
                  "it's your brain's long-term memory")
    if base and any(p not in base for p in EXTRA_FILES):
        return _t("motorbar.openclaw.memory_added",
                  "agregué STATE/MEMORY.md a tus rutas del hook bootstrap-extra-files (las "
                  "tuyas se conservan)",
                  "added STATE/MEMORY.md to your bootstrap-extra-files hook paths (yours "
                  "are kept)")
    return ""


def ensure_agent(cfg, exe=None, runner=None):
    """Re-asegura (idempotente, en cada launch) el agente OpenClaw de este
    agente de Workspace con workspace = su cerebro: lo crea si falta y, si el
    cliente le cambió el workspace, lo restaura y avisa. Devuelve (ok,
    estado|aviso): 'kept', 'created' o la línea de aviso de restauración."""
    exe = exe or _exe()
    brain = (cfg or {}).get("_brain", "")
    if not exe or not brain or not os.path.isdir(brain):
        return False, "sin binario o sin cerebro"
    aid = agent_id(cfg)
    real = os.path.realpath(brain)
    try:
        # VERIFICADO 2026.10.4: los agentes viven en `agents.entries.<id>`
        # (dict); hasta 2026.5.x eran `agents.list[i]` (lista). Se leen los
        # dos: con solo el viejo, `agents add` corría en cada launch y fallaba
        # con «already exists».
        rows = []
        rc, out = _cfg_get(exe, "agents.entries", runner)
        ent = _json_out(out) if rc == 0 else None
        if isinstance(ent, dict):
            rows = [(dict(v, id=k) if isinstance(v, dict) else {"id": k},
                     "agents.entries.%s.workspace" % k) for k, v in ent.items()]
        else:
            rc, out = _cfg_get(exe, "agents.list", runner)
            lst = _json_out(out) if rc == 0 else []
            rows = [(row, "agents.list[%d].workspace" % i)
                    for i, row in enumerate(lst if isinstance(lst, list) else [])]
        for row, ws_path in rows:
            if not (isinstance(row, dict) and row.get("id") == aid):
                continue
            ws = os.path.realpath(os.path.expanduser(str(row.get("workspace") or "")))
            if ws == real:
                return True, "kept"
            r = _run(_base(exe) + ["config", "set", ws_path, brain],
                     runner=runner, timeout=30)
            if getattr(r, "returncode", 1) != 0:
                return False, "no pude restaurar el workspace del agente %s" % aid
            return True, ("OpenClaw: el agente %s apuntaba a %s; lo regresé a tu cerebro "
                          "(Workspace lo necesita)" % (aid, row.get("workspace") or "otro lugar"))
        r = _run(_base(exe) + ["agents", "add", aid, "--workspace", brain,
                               "--non-interactive", "--json"], runner=runner, timeout=60)
        if getattr(r, "returncode", 1) != 0:
            return False, "agents add falló: %s" % (
                (getattr(r, "stderr", "") or getattr(r, "stdout", "") or "").strip()[-200:])
        return True, "created"
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


# ── gateway del perfil (varias pestañas a la vez) ───────────────────────────
#: Puerto base del gateway del perfil de Workspace: lejos del 18789 del
#: OpenClaw personal del socio. OpenClaw usa puertos derivados hasta base+110
#: (docs/gateway/multiple-gateways.md: dejar ≥120 entre bases), así que si el
#: base está ocupado se prueba de 120 en 120.
GATEWAY_BASE_PORT = 19289
_GATEWAY_PORT_STEP = 120


def _port_free(port):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", int(port)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _pick_port(start=GATEWAY_BASE_PORT, step=_GATEWAY_PORT_STEP, tries=30):
    for i in range(tries):
        port = start + i * step
        if port + 110 <= 65535 and _port_free(port):
            return port
    return start


def gateway_port():
    """Puerto del gateway según el archivo del perfil (None si no hay)."""
    try:
        port = int(_get_path(_profile_config() or {}, "gateway.port"))
        return port if 1024 <= port <= 65535 else None
    except (TypeError, ValueError):
        return None


def ensure_gateway_config(exe=None, runner=None, notify=None, repick=False):
    """Lo que el gateway necesita en el perfil de Workspace, SOLO si falta
    (vanilla: lo que el socio puso se respeta): gateway.mode=local, un puerto
    propio y autenticación por token. VERIFICADO 2026.9.33: sin token guardado
    el gateway genera uno «solo de este arranque» y el `tui` NO conecta
    («Missing gateway auth token»); `doctor --generate-gateway-token` lo
    resuelve pero tarda ~2 min, así que se guarda uno nuevo con el `config set
    --batch-file` oficial (~25 s, una sola vez). El token va por un archivo
    temporal que se borra (nunca en la línea de comandos) y Workspace no lo
    guarda: vive en la config de OpenClaw, como lo deja su propio onboarding.
    Devuelve (ok, puerto|None, motivo); puerto None = el socio configuró otro
    modo (p. ej. remoto) y Workspace no administra el gateway."""
    exe = exe or _exe()
    if not exe:
        return False, None, "openclaw no está en PATH"
    try:
        d = _profile_config()
        if isinstance(d, dict):
            g = d.get("gateway") if isinstance(d.get("gateway"), dict) else {}
        else:
            rc, out = _cfg_get(exe, "gateway", runner)
            g = _json_out(out) if rc == 0 else {}
            g = g if isinstance(g, dict) else {}
        mode = g.get("mode")
        if mode not in (None, "", "local"):
            return True, None, ""
        ops = []
        if not mode:
            ops.append(("gateway.mode", "local"))
        try:
            port = int(g.get("port"))
        except (TypeError, ValueError):
            port = None
        if repick or not port or not 1024 <= port <= 65535:
            port = _pick_port(start=(port + _GATEWAY_PORT_STEP) if (repick and port) else GATEWAY_BASE_PORT)
            ops.append(("gateway.port", port))
        auth = g.get("auth") if isinstance(g.get("auth"), dict) else {}
        if not auth.get("mode") and not auth.get("token") and not auth.get("password"):
            ops += [("gateway.auth.mode", "token"),
                    ("gateway.auth.token", secrets.token_urlsafe(32))]
        elif auth.get("mode") == "token" and not auth.get("token"):
            ops.append(("gateway.auth.token", secrets.token_urlsafe(32)))
        if not ops:
            return True, port, ""
        if notify:
            notify("WORKSPACE: preparando OpenClaw para abrir varias pestañas a la vez "
                   "(solo esta vez; tarda ~30 s)…")
        fd, tmp = tempfile.mkstemp(prefix="ws-openclaw-gw-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump([{"path": k, "value": v} for k, v in ops], fh)
            r = _run(_base(exe) + ["config", "set", "--batch-file", tmp],
                     runner=runner, timeout=180)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        if getattr(r, "returncode", 1) != 0:
            return False, None, "no pude preparar el gateway del perfil %s de OpenClaw" % _profile()
        return True, port, "configured"
    except Exception as e:
        return False, None, "%s: %s" % (type(e).__name__, e)


def _gateway_begin(exe):
    """Antes de elegir pestaña: config del gateway + anotar esta pestaña + que
    se vaya encendiendo (sin esperar). (puerto, local): puerto = gateway que
    administra Workspace; local=True = no se pudo y la pestaña abre en el modo
    local de una sola ventana (lo de antes)."""
    import openclaw_gateway as G
    prof = _profile()
    ok, port, why = ensure_gateway_config(exe, notify=print)
    if not ok:
        print("WORKSPACE: %s; OpenClaw abre en modo de una sola ventana." % why)
        return None, True
    if not port:
        return None, False
    try:
        if not G.running(prof) and not _port_free(port) and not G.healthy(port, timeout=0.5):
            ok, port2, _w = ensure_gateway_config(exe, notify=print, repick=True)
            port = port2 if ok and port2 else port
        G.enter(prof)
        G.ensure_running(exe, prof, port)
        return port, False
    except Exception as e:
        print("WORKSPACE: no pude preparar el gateway de OpenClaw (%s: %s); abre en modo "
              "de una sola ventana." % (type(e).__name__, e))
        G.leave(prof)
        return None, True


def _gateway_end(port):
    if port:
        import openclaw_gateway as G
        G.leave(_profile())


# ── headless ───────────────────────────────────────────────────────────────
def _reply_text(data):
    """Texto de la respuesta en la salida JSON de `agent --json`. Forma de
    éxito VERIFICADA (2026.5.12 + OpenRouter): `{"payloads": [{"text": …,
    "mediaUrl": …}], "meta": {…}}`. Las demás claves quedan como respaldo."""
    if isinstance(data, dict):
        for k in ("reply", "text", "output", "message", "content"):
            v = data.get(k)
            if isinstance(v, str) and v.strip():
                return v
        for k in ("payloads", "messages", "result"):
            v = data.get(k)
            if isinstance(v, list):
                parts = [p.get("text") for p in v if isinstance(p, dict)
                         and isinstance(p.get("text"), str)]
                if parts:
                    return "\n".join(parts)
            if isinstance(v, dict):
                t = _reply_text(v)
                if t:
                    return t
    return ""


def _parece_cerebro(path):
    return any(os.path.isfile(os.path.join(path, *p))
               for p in (("BRAIN.md",), ("CLAUDE.md",), (".workspace", "agent.json")))


def headless_agent(agent="", cwd=None):
    """El agente de Workspace dueño de un turno sin ventana → {'name', '_brain'}
    o None. Por nombre (el que pasa quien llama o WORKSPACE_AGENT_NAME, el de
    la sesión que corre), con su cerebro del registro o, si aún no está
    registrado (p. ej. al personalizarlo recién creado), `cwd` cuando es un
    cerebro; sin nombre, el agente registrado cuyo cerebro es `cwd`."""
    name = str(agent or os.environ.get("WORKSPACE_AGENT_NAME") or "").strip()
    real = os.path.realpath(cwd) if cwd and os.path.isdir(str(cwd)) else ""
    brain = ""
    if name:
        try:
            import brain_resolver
            res = brain_resolver.resolve_agent(name)
            if res and res.get("exists"):
                brain = res.get("path") or ""
        except Exception:
            brain = ""
        if not brain and real and _parece_cerebro(real):
            brain = real
    elif real:
        try:
            import agentsreg
            for a in agentsreg.agents():
                if os.path.realpath(a["brain"]) == real:
                    name, brain = a["name"], a["brain"]
                    break
        except Exception:
            pass
    if not name or not brain or not os.path.isdir(brain):
        return None
    return {"name": name, "_brain": brain}


def prepare_agent(cfg, exe=None, runner=None):
    """Perfil + agente de OpenClaw de este agente de Workspace, como el arranque
    (camino rápido si el archivo del perfil ya dice que todo está bien): un
    turno sin ventana también corre con el cerebro protegido (skipBootstrap,
    memoria nativa apagada) y con SU agente. (ok, id del agente | motivo)."""
    exe = exe or _exe()
    if not exe:
        return False, "openclaw no está en PATH"
    if _quick_ok(cfg, _profile_config()):
        return True, agent_id(cfg)
    ok, why = ensure_profile(exe, runner=runner)
    if not ok:
        return False, why
    ok, why = ensure_agent(cfg, exe, runner=runner)
    if not ok:
        return False, why
    return True, agent_id(cfg)


def no_agent_msg():
    return _t("motorbar.openclaw.no_agent",
              "OpenClaw sin ventana necesita saber de qué agente es el turno: jamás usa su "
              "agente «main» de fábrica, que contesta con otra identidad",
              "a windowless OpenClaw turn needs to know which agent it belongs to: it never "
              "uses OpenClaw's built-in «main» agent, which answers with another identity")


def run_turn(prompt, *, model=None, cwd=None, timeout=300, agent=None,
             session_id=None, session_key=None, exe_override=None, runner=None):
    """UN turno HEADLESS: `openclaw --profile <perfil> agent --agent <id> -m
    <mensaje> --json`. Con el gateway del perfil encendido (hay pestañas
    abiertas) va por él (VERIFICADO 2026.9.33: la respuesta llega en
    `result.payloads`); sin gateway, `--local` como antes. El turno se anota
    como cliente para que el guardián no apague el gateway a medio turno.
    Devuelve (ok, texto). Sin `model` no se pasa `--model` (manda la config
    del socio). `agent` = el id de OpenClaw del agente de Workspace
    (agent_id/prepare_agent); sin él, o con el «main» de fábrica, no hay
    turno: contestaría otra identidad."""
    exe = _exe(exe_override)
    if not exe:
        return False, "openclaw no está en PATH"
    aid = str(agent or "").strip()
    if not aid or aid == "main":
        return False, no_agent_msg()
    import openclaw_gateway as G
    prof = _profile()
    port = gateway_port()
    via_gw = bool(port) and G.running(prof)

    def _cmd(local):
        cmd = _base(exe) + ["agent"] + (["--local"] if local else []) + [
            "--agent", aid, "-m", prompt or "", "--json"]
        if session_id:
            cmd += ["--session-id", str(session_id)]
        if session_key:                  # la clave de una pestaña: agent:<id>:ws-…
            cmd += ["--session-key", str(session_key)]
        if model:
            cmd += ["--model", model]
        return cmd
    try:
        if cwd:
            os.makedirs(cwd, exist_ok=True)
        if via_gw:
            G.enter(prof)
            if not G.healthy(port):          # aún encendiendo (primera pestaña)
                ok, why = G.wait_ready(exe, prof, port, timeout=180)
                if not ok:
                    return False, "openclaw agent: %s" % why
        r = _run(_cmd(not via_gw), runner=runner, timeout=timeout, cwd=cwd or None)
        rc = getattr(r, "returncode", 1)
        out = getattr(r, "stdout", "") or ""
        err = getattr(r, "stderr", "") or ""
        if rc != 0 and not via_gw and "without --local" in (err + out):
            # VERIFICADO: con un gateway dueño del estado, `--local` se niega
            # («Run without --local to use it»): el turno va por ese gateway.
            r = _run(_cmd(False), runner=runner, timeout=timeout, cwd=cwd or None)
            rc = getattr(r, "returncode", 1)
            out = getattr(r, "stdout", "") or ""
            err = getattr(r, "stderr", "") or ""
        if rc != 0:
            return False, "openclaw agent exit %d: %s" % (rc, (err or out).strip()[-300:])
        data = _json_out(out)
        return True, (_reply_text(data) or out.strip())
    except subprocess.TimeoutExpired:
        return False, "openclaw agent: timeout tras %ss" % timeout
    except Exception as e:
        return False, "openclaw agent: fallo al invocar: %s" % e
    finally:
        if via_gw:
            G.leave(prof)


# ── identidad: el MISMO AGENTS.md puntero que codex/opencode ────────────────
def inject_context(cfg, session_context=""):
    """AGENTS.md puntero → doc de identidad + bloque invisible de la pestaña.
    Misma marca y mismo corte que codex/opencode (archivo compartido)."""
    from engines.opencode import inject_agents_md
    return inject_agents_md(cfg, session_context=session_context, engine="openclaw")


def _identity_doc(cfg):
    from engines.opencode import _identity_doc as _doc
    return _doc(cfg)


# ── pestañas: clave de sesión ASIGNADA por Workspace ───────────────────────
def new_session_key(aid):
    """Clave nueva para una pestaña: `agent:<id>:ws-<hex>` (OpenClaw la mapea
    a un sessionId; reabrirla continúa la misma sesión — VERIFICADO)."""
    import uuid
    return "agent:%s:%s%s" % (aid, _KEY_PREFIX, uuid.uuid4().hex[:16])


def _valid_session_key(key, aid=None):
    m = re.fullmatch(r"agent:([a-z0-9-]{1,64}):[A-Za-z0-9_.-]{1,96}", str(key or ""))
    return bool(m) and (aid is None or m.group(1) == aid)


def _session_from_passthrough(passthrough):
    args = [str(a) for a in passthrough or []]
    for i, a in enumerate(args):
        if a.startswith("--session="):
            return a.split("=", 1)[1]
        if a == "--session" and i + 1 < len(args):
            return args[i + 1]
    return ""


def _interactive_argv(cfg, passthrough, session_key="", boot="", local=False):
    """argv DESPUÉS de `openclaw`: perfil propio + TUI (cliente del gateway del
    perfil; `local=True` = modo de una sola ventana, sin gateway) + clave de la
    pestaña (+ mensaje de arranque). Sin `--model` (manda la config del socio).
    Una `--session` o `--message` del socio va tal cual y gana."""
    args = [str(a) for a in passthrough or []]
    argv = ["--profile", _profile(), "tui"] + (["--local"] if local else [])
    if session_key and not _session_from_passthrough(args):
        argv += ["--session", session_key]
    if boot and "--message" not in args:
        argv += ["--message", boot]
    return argv + args


def _account_cmd(exe):
    import engine_install
    cmd = list(engine_install.recipe("openclaw")["account_cmd"])
    cmd[0] = exe
    return cmd


def _offer_account(exe):
    """En una terminal: ¿abrir el setup oficial (proveedor + modelo) ahora?
    True si se abrió. Sin terminal (o «no») → False, sin bloquear."""
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
        ans = input("  ¿Lo conectas ahora? Se abre el setup oficial de OpenClaw [S/n] ")
    except (EOFError, KeyboardInterrupt):
        return False
    if ans.strip().lower() in ("n", "no"):
        return False
    try:
        subprocess.call(_account_cmd(exe), env=_env_motor())
    except Exception:
        return False
    return True


def _missing_provider(st):
    return st.get("session_active") is False or st.get("model_ready") is False


def _provider_gate(exe, st):
    """Sin proveedor (o con un modelo de un proveedor sin conectar) el TUI abre
    pero no responde: «run error: No route-compatible authentication source is
    configured for openai» (escenarios oc-nuevo y oc-personal, 2026-10-16). Se
    ofrece conectar AHORA (setup oficial, directo a proveedor y modelo) y, si
    sigue faltando, NO se abre a ciegas salvo que el socio lo pida.
    True = abrir la pestaña."""
    if not _missing_provider(st):
        return True
    print("WORKSPACE: %s." % ("OpenClaw no tiene proveedor conectado"
                               if st.get("session_active") is False else st.get("detail")))
    if st.get("session_active") is False and os.path.isdir(
            os.path.join(os.path.expanduser("~"), ".openclaw")):
        # Quien ya usaba OpenClaw se pregunta por qué le piden conectar otra vez.
        print("  Workspace usa su propio perfil de OpenClaw (tu OpenClaw personal no cambia): "
              "el proveedor se conecta aquí una sola vez.")
    if _offer_account(exe):
        st = status()
        if not _missing_provider(st):
            return True
        print("WORKSPACE: aún falta: %s." % (st.get("detail") or "conectar un proveedor"))
    print("  Sin proveedor, el agente abre pero no puede responder. Conéctalo en Motores › "
          "OpenClaw › cuenta y proveedor (elige el proveedor y, después, el modelo).")
    try:
        import engine_versions as _EV
        return _EV.allow_anyway()
    except Exception:
        return True


def _offer_rebuild(exe):
    """En una terminal: ofrece respaldar el perfil y crear uno nuevo, y abre el
    setup oficial para volver a conectar el proveedor. True si quedó listo."""
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
        ans = input("  ¿Respaldo ese perfil y creo uno nuevo ahora? [s/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if ans not in ("s", "si", "sí", "y", "yes"):
        return False
    bak = rebuild_profile()
    if not bak:
        print("WORKSPACE: no pude respaldar el perfil (¿OpenClaw abierto en otra ventana?).")
        return False
    print("WORKSPACE: respaldo en %s" % bak)
    # el proveedor se conecta en el arranque normal (status → _offer_account)
    print("WORKSPACE: perfil nuevo listo; ahora conecta tu proveedor y elige tu modelo.")
    return True


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    """Arranca un agente EN OPENCLAW (TUI conectado al gateway del perfil)
    envuelto por el wrapper neutral (session_start → TUI → session_end).
    plan=True NO lanza."""
    brain = cfg.get("_brain", "")
    exe = _exe()
    aid = agent_id(cfg)

    if plan:
        line = "─" * 66
        print(line)
        print("  WORKSPACE · plan de arranque — motor OPENCLAW — agente: %s"
              % cfg.get("display", cfg.get("name")))
        print(line)
        print("  motor       : openclaw tui, cliente del gateway del perfil propio `%s` "
              "(aparte del OpenClaw personal; varias pestañas a la vez)" % _profile())
        print("  modelo      : lo fija el SOCIO en OpenClaw (el harness no pasa --model)")
        print("  cerebro     : %s  (workspace del agente OpenClaw `%s`)" % (brain, aid))
        print("  identidad   : AGENTS.md puntero → %s (el mismo de codex/opencode); "
              "skipBootstrap=true y memoria nativa apagada: OpenClaw no crea "
              "archivos en el cerebro"
              % _identity_doc(cfg))
        print(_t("motorbar.openclaw.plan_memory",
                 "  memoria     : STATE/MEMORY.md de tu cerebro en cada turno (hook oficial "
                 "bootstrap-extra-files, con el gateway); su búsqueda por significado, apagada",
                 "  memory      : your brain's STATE/MEMORY.md on every turn (official "
                 "bootstrap-extra-files hook, with the gateway); its semantic search, off"))
        print("  pestañas    : picker compartido — cada pestaña con su clave "
              "`agent:%s:ws-…` (OpenClaw la continúa al reabrir)" % aid)
        print("  cierre      : transcript de la sesión (agents/%s/sessions/<id>.jsonl) "
              "→ respaldo y revisión de skills (si está encendida)" % aid)
        print(line)
        print("  [%s] binario openclaw en PATH: %s"
              % ("✓" if exe else "✗ FALTA", exe or "(Motores › instalar)"))
        if exe:
            kind, msg = version_problem(exe)
            try:
                import engine_versions
                ver = engine_versions.installed_version(exe) or "?"
            except Exception:
                ver = "?"
            print("  [%s] versión: %s%s" % ("✗" if kind else "✓", ver,
                                            (" — " + msg) if msg else ""))
        print("  [%s] cerebro: %s"
              % ("✓" if brain and os.path.isdir(brain) else "✗ FALTA", brain))
        print(line)
        return

    if not exe:
        print("WORKSPACE: openclaw no está en PATH — instálalo desde Motores.")
        sys.exit(1)

    # Versión: un bug conocido o un perfil de una versión más nueva se dicen
    # claro ANTES de abrir nada (si no, el cliente ve un TUI roto o un error
    # crudo de OpenClaw).
    kind, msg = version_problem(exe)
    if kind == "broken":
        import engine_versions as _EV
        print("WORKSPACE: " + msg)
        if not _EV.allow_anyway():
            sys.exit(1)
    if kind == "profile":
        print("WORKSPACE: " + msg + ".")
        if not _offer_rebuild(exe):
            print("  Para seguir: Workspace respalda ese perfil (no borra nada) y crea "
                  "uno nuevo; luego vuelves a conectar tu proveedor en Motores › "
                  "OpenClaw › cuenta y proveedor.")
            sys.exit(1)

    # Perfil propio + agente con workspace = cerebro (antes de cualquier cosa
    # que pueda abrir una sesión): jamás se dejan crear archivos en el cerebro.
    # Camino rápido: si el archivo del perfil ya dice que todo está bien, no se
    # llama al CLI (cada llamada cuesta 2-3 s); si no, el camino exacto por CLI
    # corrige y avisa.
    if not _quick_ok(cfg, _profile_config()):
        ok, why = ensure_profile(exe)
        if not ok:
            print("WORKSPACE: no pude preparar el perfil de OpenClaw (%s)." % why)
            sys.exit(1)
        if why:
            print("WORKSPACE: %s." % why)
        ok, why = ensure_agent(cfg, exe)
        if not ok:
            print("WORKSPACE: no pude preparar el agente de OpenClaw (%s)." % why)
            sys.exit(1)
        if why not in ("kept", "created"):
            print("WORKSPACE: %s." % why)
        if not _provider_gate(exe, status()):
            sys.exit(0)

    # Gateway del perfil: se enciende mientras el socio elige pestaña; esta
    # pestaña queda anotada hasta que termina (también si sale con error).
    gw_port, local = _gateway_begin(exe)
    if local:
        try:
            import engine_versions as _EV
            b = _EV.broken(sys.modules[__name__], _EV.installed_version(exe), mode="local")
        except Exception:
            b = None
        if b:
            print("WORKSPACE: %s — %s" % (b["why"], b["hint"]))
            if not _EV.allow_anyway():
                sys.exit(1)
    try:
        _run_tab(cfg, passthrough, exe=exe, aid=aid, brain=brain, preselect=preselect,
                 show_banner=show_banner, gw_port=gw_port, local=local)
    finally:
        _gateway_end(gw_port)


def _run_tab(cfg, passthrough, *, exe, aid, brain, preselect, show_banner, gw_port, local):
    """La pestaña en sí (después del perfil y el gateway): elegir pestaña,
    identidad, esperar al gateway, TUI y cierre."""
    tab, session_key, session_blk = None, "", ""
    agent = str(cfg.get("name") or "")
    cfg.setdefault("_engine", "openclaw")
    os.environ["WORKSPACE_ENGINE_LABEL"] = "OpenClaw · modelo de tu config"
    try:
        from engines import _ui
        import sessions_registry as _reg
        if not (preselect and preselect.get("wid")):
            from engines import claude_code as _cc0
            _cc0.session_preflight(cfg, "openclaw")
        tab = _ui.pick_tab(cfg, preselect=preselect)
        if show_banner:                 # la limpieza de antes de la TUI lo quita
            _ui.cargando(cfg, tab)
        if not tab:
            from engines import claude_code as _cc
            _cc.warn_no_tab(_cc.LAST_PICK_ERROR)
        if tab:
            wid, wname = tab
            _ui.export_tab_env(cfg, wid, wname)
            _reg.ensure_tab(brain, agent, wname, claude_wid=wid)
            session_key = _reg.resume_id(brain, agent, wname, "openclaw") or ""
            if not _valid_session_key(session_key, aid):
                session_key = ""
            session_blk = _reg.session_doc_block(brain, wname, engine="openclaw",
                                                 resumed=bool(session_key))
    except Exception as e:
        tab, session_key, session_blk = None, "", ""
        try:
            from engines import claude_code as _cc
            err = "no pude preparar la pestaña (%s: %s)" % (type(e).__name__, e)
            _cc._session_log(cfg, "openclaw", err)
            _cc.warn_no_tab(err)
        except Exception:
            pass

    resumed = bool(session_key)
    user_key = _session_from_passthrough(passthrough)
    if user_key:
        session_key = ""                       # el socio eligió sesión a mano
    elif tab and not session_key:
        session_key = new_session_key(aid)
        try:
            import sessions_registry as _reg
            _reg.bind(brain, agent, tab[1], "openclaw", session_key)
        except Exception:
            pass

    first_prompt = ""
    inj = inject_context(cfg, session_context=session_blk)
    if not inj.get("ok") and inj.get("detail"):
        print("WORKSPACE: identidad NO inyectada (%s) — OpenClaw arrancará "
              "genérico." % inj["detail"])
    if tab and session_blk and inj.get("action") == "custom" \
            and not inj.get("session") and not resumed:
        try:
            import sessions_registry as _reg
            first_prompt = _reg.first_prompt_context(brain, tab[1], engine="openclaw")
        except Exception:
            first_prompt = ""

    # El gateway se fue encendiendo mientras se elegía la pestaña; aquí se
    # espera (antes de limpiar la pantalla, para que los avisos no queden
    # pegados arriba del TUI, que es EN LÍNEA).
    if gw_port:
        import openclaw_gateway as G
        ok, why = G.wait_ready(exe, _profile(), gw_port, notify=print)
        if not ok:
            print("WORKSPACE: " + why)
            sys.exit(1)

    # Sin banner del cerebro: la TUI de OpenClaw es EN LÍNEA (no pantalla
    # completa), así que el banner quedaba fijo arriba de la sesión, estático
    # (no se actualiza ni cambia de idioma). Solo se limpia la pantalla.
    if show_banner:
        try:
            sys.stdout.write("\033[2J\033[3J\033[H")
            sys.stdout.flush()
        except Exception:
            pass

    # Arranque del cerebro como los demás: sesión NUEVA sin argumentos → manda
    # el primer mensaje (VERIFICADO: --message envía al abrir). Retomar: nada.
    boot = first_prompt or ("" if (passthrough or resumed) else
                            "Lee %s e inicia el cerebro. Al terminar, confirma "
                            "en una línea breve." % _identity_doc(cfg))
    argv = _interactive_argv(cfg, passthrough, session_key=session_key, boot=boot,
                             local=local)

    # La captura al cierre resuelve clave → archivo de la sesión.
    real_key = session_key or user_key
    if real_key and _valid_session_key(real_key):
        os.environ["WORKSPACE_OPENCLAW_SESSION"] = real_key
    else:
        os.environ.pop("WORKSPACE_OPENCLAW_SESSION", None)

    _doc_dirty = []

    def _ctx_sink(ctx):
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

    watch = None
    if gw_port:
        # Si el gateway se cae con la pestaña abierta, esta pestaña lo revive
        # (el TUI se reconecta solo).
        import openclaw_gateway as G
        watch = G.start_watch(exe, _profile(), gw_port)
    try:
        import interactive
        rc = interactive.run_official_cli_interactive(
            "openclaw", brain=brain or None, argv=argv, context_sink=_ctx_sink,
            pending={"tab": tab[1] if tab else "", "agent": agent, "resumed": resumed})
    except Exception as e:
        print("WORKSPACE: no pude lanzar openclaw (%s: %s)" % (type(e).__name__, e))
        sys.exit(1)
    finally:
        if watch is not None:
            watch.set()
    if session_blk or _doc_dirty:
        try:
            inject_context(cfg)
        except Exception:
            pass
    # Hallazgo 16 (2026-10-16): la clave se ata ANTES de abrir; si la pestaña se
    # cerró sin un solo turno, OpenClaw nunca creó la sesión («Session not
    # found») y la siguiente apertura la trataba como retomada: sin mensaje de
    # arranque. Se suelta la clave → la próxima vez abre como nueva.
    if tab and session_key and session_key == real_key:
        try:
            import pending_runs
            if pending_runs.openclaw_never_created(getattr(interactive, "LAST_CLOSE", None)):
                import sessions_registry as _reg
                _reg.unbind(brain, agent, tab[1], "openclaw", session_key)
        except Exception:
            pass
    try:
        import pending_runs
        pending_runs.done()               # atado y limpieza hechos: ya no está pendiente
    except Exception:
        pass
    sys.exit(rc if isinstance(rc, int) else 0)


def pick(cfg):
    """Picker de pestañas COMPARTIDO (registro neutral). Falla-suave → ''."""
    try:
        from engines import _ui
        cfg.setdefault("_engine", "openclaw")
        return _ui.pick_keep_label(cfg, "OpenClaw · modelo de tu config")
    except Exception:
        return ""
