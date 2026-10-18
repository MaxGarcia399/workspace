"""Antigravity CLI adapter. Flags verified against installed agy --help (1.3.4).

Login and sessions belong to agy; WORKSPACE never reads credentials.
Native MCP is supported. agy 1.3 has native hooks (SessionStart, PreToolUse,
PostToolUse, Pre/PostInvocation, Stop — no SessionEnd); WORKSPACE does NOT
enable them: its wrapper already fires the neutral session start/end, and
native ones would double-fire.

PERMISOS por la AUTONOMÍA del agente (agent.json "autonomy", contrato común)
— VERIFICADO con agy 1.3.4 en un cerebro de prueba (HOME temporal):
  · brain (default): `--mode accept-edits` → lee/crea/edita dentro del cerebro
    sin preguntar; escribir fuera y la terminal piden permiso (sin ventana:
    se niegan). Regla global `write_file(<cerebro>)` (antes `read_file`).
  · full: lo mismo + `--project workspace-<agente>`, un proyecto de agy cuyo
    `permissionGrants` permite `command(*)` → la terminal corre sin preguntar
    y escribir fuera SIGUE pidiendo permiso. Va por proyecto y no por el
    `toolPermission` global porque ese ajuste es de TODO agy (llegaría a los
    demás agentes y al uso propio del socio); `always-proceed` además deja
    escribir fuera del cerebro. Al reanudar, agy usa el proyecto de la
    conversación: una conversación nacida en `brain` sigue preguntando.
  · ask (el usuario apagó el acceso automático en Agentes): SIN `--mode` →
    agy pregunta antes de crear o editar, también dentro del cerebro. Se quita
    la regla `write_file(<cerebro>)` y queda `read_file(<cerebro>)`.
  · Nunca `--add-dir` (ensancharía la escritura libre) ni
    `--dangerously-skip-permissions`. El `--mode`/`--project` del socio gana.

BARRA: la statusLine NATIVA de agy (settings.json) apunta a un shim estable
(`~/.local/bin/workspace-agy-statusline`, ver antigravity_usage); se apila
debajo de la de agy. TEMA: agy no tiene temas in-app propios (colorScheme
fijos); con "terminal" (su default) su UI usa colores ANSI básicos, que
Workspace recolorea por corrida (OSC 4) desde la paleta del hub y restaura al
salir (OSC 104). Si el socio eligió otro colorScheme, no se toca nada.

Pestañas NEUTRALES (sessions_registry · el socio 2026-10-03): el MISMO picker de
Claude Code corre antes del exec (subproceso agnóstico); el resume usa
`agy --conversation <id>` (validado contra el store local de agy antes de
usarlo) y el id del vendor se ata POST-HOC leyendo
`~/.gemini/antigravity-cli/cache/last_conversations.json` (VERIFICADO contra
la instalación real: mapa cwd → último conversation id; se compara el
snapshot ANTES/DESPUÉS de la corrida para no bindear un id stale).

INYECCIÓN INVISIBLE: la memoria de la pestaña activa va en el GEMINI.md
GENERADO (doc de proyecto que agy lee como contexto) — el socio NO ve el
bloque en el chat. El bloque se regenera por corrida y al cerrar el GEMINI.md
generado vuelve a su puntero en reposo, sin la ruta de esta máquina ni el
contexto de arranque (_restore_gemini). Si el GEMINI.md es PROPIO del socio, su CONTENIDO
no se toca: el bloque de sesión va ANEXADO al final, marcado y efímero
(strip al cerrar + strip-antes-de-anexar en cada launch — un huérfano por
crash se auto-limpia). Solo si ni el anexo se puede escribir, la memoria
cae al primer prompt (visible — último recurso honesto). Fix 2026-10-04.
Falla-suave absoluta: nada de esto impide el launch.
"""
import json
import os
import shutil
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import legacy  # noqa: E402  (literales de la instalación anterior)

META = {"name": "antigravity", "needs": ["agy"], "auth": "subscription"}
CAPABILITIES = {
    "launch": "wrapper", "inject_context": "project-doc", "mcp": True,
    # Avisos de sesión: solo inicio y cierre, emitidos por el wrapper neutral
    # (los hooks nativos de agy existen pero no se activan — doble disparo).
    "hooks": "wrapper",
    "sessions": "workspace",   # pestañas del registro neutral (sessions_registry)
                             # + resume con `agy --conversation <id>` (binding
                             # post-hoc vía cache/last_conversations.json)
    "status_live": False,
    "statusline": "native-config",   # statusLine de agy → shim de Workspace
    "headless": False,
}

#: Modo de ejecución de agy para TODA sesión de un agente (brain y full).
AGY_MODE = "accept-edits"
#: Regla de agy que deja correr cualquier comando sin preguntar — solo en el
#: proyecto del agente, solo con autonomía full.
FULL_GRANT = "command(*)"
#: Reglas de agy para la memoria. agy solo deja pasar sin preguntar un
#: comando IDÉNTICO a su regla `command(…)` (VERIFICADO 2026-10-17 con su log:
#: `command(workspace.cmd memoria vigente)` corre solo; el mismo comando con un
#: argumento de más pide permiso). Una nota trae su texto, así que en agy el
#: agente la escribe en su bandeja del cerebro y corre un comando FIJO
#: (memoria.ENTRADA_ARCHIVO): esos fijos son los que se permiten, con y sin
#: `.cmd` (Windows).
_MEMORIA_FIJOS = ("nota --entrada", "checkpoint --entrada", "ver", "vigente", "maleta", "status")
MEMORIA_RULES = tuple("command(%s memoria %s)" % (b, s)
                      for b in ("workspace", "workspace.cmd") for s in _MEMORIA_FIJOS)
#: Las de versiones anteriores (no servían): se quitan al abrir.
_MEMORIA_RULES_VIEJAS = (("command(workspace memoria)", "command(workspace.cmd memoria)")
                         + tuple("command(%s memoria %s)" % (b, s) for b in ("workspace", "workspace.cmd")
                                 for s in ("nota", "checkpoint", "context")))
#: Prefijo de los proyectos de agy que crea Workspace (marca de propiedad).
PROJECT_PREFIX = "workspace-"

#: Primera línea EXACTA del GEMINI.md generado — detector de "es nuestro".
_GEMINI_MARK = "<!-- WORKSPACE:GENERATED antigravity-context v1 -->"
#: Marca de la instalación anterior (pre-rename 2026-10): los cerebros
#: existentes aún la traen; sin reconocerla el doc generado parecía "del socio"
#: y la memoria caía al primer prompt visible. Solo se LEE; se escribe siempre
#: la nueva.
_GEMINI_MARK_LEGACY = legacy.GEMINI_GEN_MARK
#: Marcas del bloque de SESIÓN (pestaña activa) dentro del GEMINI.md.
#: Se quitan por LÍNEA completa — contenido con `-->` adentro no las rompe.
_SESSION_START = "<!-- WORKSPACE:SESSION start — contexto de la pestaña activa; se regenera en cada launch -->"
_SESSION_END = "<!-- WORKSPACE:SESSION end -->"
#: Variantes pre-rename (solo LECTURA: huérfanos de corridas de la instalación
#: anterior también deben poder limpiarse — había reales en los cerebros).
_SESSION_STARTS = (_SESSION_START, legacy.SESSION_START)
_SESSION_ENDS = (_SESSION_END, legacy.SESSION_END)


def status():
    exe = shutil.which("agy")
    return {"ready": bool(exe), "binary": "agy", "binary_in_path": bool(exe),
            "auth": "managed by agy; login not probed"}


# La verificación de sesión corre el programa oficial DESPEGADO de la
# terminal: sin stdin y, en Mac/Linux, en su propia sesión (sin terminal de
# control). Si hereda la terminal, al salir la deja en modo normal y la
# pantalla que lo llamó (Motores, el hub) se queda sin teclado.
_DETACHED = {"stdin": subprocess.DEVNULL}
if os.name != "nt":
    _DETACHED["start_new_session"] = True


def _env_motor():
    """El env para correr el CLI del motor: sin NADA de la bóveda
    (secret_store.engine_env). Falla-suave: sin secret_store, el heredado."""
    try:
        import secret_store
        return secret_store.engine_env()
    except Exception:
        return None


def session_active(runner=None):
    """¿Hay sesión de Antigravity? agy no tiene comando de estado de sesión;
    `agy models` sí la exige (sin sesión responde «Please sign in…» y rc 1 —
    VERIFICADO 2026-10-14 con un HOME vacío). Tarda unos segundos (consulta al
    proveedor): úsalo en segundo plano. Jamás lee credenciales. True/False;
    None si no se pudo saber."""
    exe = shutil.which("agy")
    if not exe:
        return None
    run = runner or subprocess.run
    extra = {} if runner else {"env": _env_motor()}
    try:
        r = run([exe, "models"], capture_output=True, text=True, timeout=40,
                encoding="utf-8", errors="replace", **_DETACHED, **extra)
        out = ((getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")).lower()
        if "sign in" in out or "log in" in out or "authentication" in out:
            return False
        return True if getattr(r, "returncode", 1) == 0 else None
    except Exception:
        return None


def _has_flag(args, *names):
    for a in args or ():
        a = str(a)
        if any(a == n or a.startswith(n + "=") for n in names):
            return True
    return False


def _policy_argv(cfg, args, project_id=""):
    """Flags de permisos según la autonomía (ver docstring del módulo):
    `--mode accept-edits` salvo en "ask"; `--project <id>` solo si hay
    proyecto del agente (full). Lo que el socio pase (--mode / --project) gana."""
    out = []
    if _autonomy(cfg) != "ask" and not _has_flag(args, "--mode"):
        out += ["--mode", AGY_MODE]
    if project_id and not _has_flag(args, "--project", "--new-project"):
        out += ["--project", project_id]
    return out


def _interactive_argv(cfg, passthrough, resume_cid="", first_prompt="",
                      project_id=""):
    """argv para `agy`: permisos (`--mode accept-edits` [+ `--project`]) y
    luego el arranque. Con pestaña:
      · `resume_cid` → `--conversation <id>` (VERIFICADO en agy --help) y SIN
        prompt inicial (el hilo ya tiene el contexto) — el `--mode` va
        también al reanudar;
      · `first_prompt` → SOLO el fallback visible (GEMINI.md propio del
        socio); el camino normal inyecta la memoria en el doc de proyecto.
    Prompts/resume explícitos del socio en el passthrough SIEMPRE ganan.
    Jamás `--add-dir`."""
    args = list(passthrough or [])
    pre = _policy_argv(cfg, args, project_id)
    # Bootstrap only a new interactive session; preserve explicit prompts/resume.
    owns_prompt = any(str(a).split("=", 1)[0] in (
        "-p", "--print", "--prompt", "-i", "--prompt-interactive",
        "-c", "--continue", "--conversation") for a in args)
    if args or owns_prompt:
        return pre + args
    resume_cid = str(resume_cid or "").strip()
    if resume_cid:
        return pre + ["--conversation", resume_cid]
    return pre + ["--prompt-interactive",
                  first_prompt or ("Lee %s e inicia el cerebro. Al terminar, confirma en "
                                   "una línea breve." % _identity_name(cfg))]


def _identity_name(cfg):
    """Doc de identidad del agente vía el resolver único (BRAIN.md en cerebros
    v2, CLAUDE.md en los anteriores, o el `identity_doc` del agente)."""
    try:
        import brain_identity
        return brain_identity.identity_doc((cfg or {}).get("_brain", ""), cfg)
    except Exception:
        return "CLAUDE.md"


# ── store local de agy (solo lectura — jamás credenciales) ──────────────────
def _agy_home():
    return os.environ.get("ANTIGRAVITY_CLI_HOME") or os.path.join(
        os.path.expanduser("~"), ".gemini", "antigravity-cli")


def _last_conversations_path():
    return os.path.join(_agy_home(), "cache", "last_conversations.json")


def _conversation_exists(cid, home=None):
    """¿La conversación sigue existiendo localmente? agy guarda una .db por
    conversación en `<home>/conversations/<id>.db` (verificado contra la
    instalación real). Valida el resume-id ANTES de `--conversation` —
    conversación borrada → arrancar fresco, no un error. Falla-suave→False."""
    cid = str(cid or "").strip()
    if not cid or any(c in cid for c in "/\\."):
        return False
    return os.path.isfile(os.path.join(home or _agy_home(),
                                       "conversations", cid + ".db"))


def _vendor_conversation_for(brain, cache_path=None):
    """El último conversation id de agy para ESTE cerebro, según su cache
    `last_conversations.json` ({cwd: conversation_id} — verificado contra
    ~/.gemini/antigravity-cli real). Se matchea el path crudo y el realpath.
    '' si no hay. Solo lectura; falla-suave."""
    try:
        with open(cache_path or _last_conversations_path(),
                  encoding="utf-8") as fh:
            m = json.load(fh)
        if not isinstance(m, dict):
            return ""
        real = os.path.realpath(brain or "")
        for k, v in m.items():
            if str(k) in (str(brain), real) or os.path.realpath(str(k)) == real:
                return str(v or "").strip()
    except Exception:
        pass
    return ""


def ensure_brain_access(brain, settings_path=None, write=True):
    """Confía este cerebro (trustedWorkspaces) y deja escribir en él sin
    preguntar: regla `write_file(<cerebro>)` — en agy permitir escribir
    implica leer, así que REEMPLAZA a la `read_file(<cerebro>)` de antes (se
    quita esa, la de este cerebro nada más). `write=False` (autonomía "ask")
    hace lo inverso: deja solo `read_file(<cerebro>)` y agy pregunta antes de
    escribir. Las demás reglas del socio (allow/deny/ask) quedan intactas;
    deny > ask > allow sigue mandando."""
    import json
    from pathlib import Path
    from antigravity_usage import _atomic
    root = os.path.realpath(os.path.abspath(os.path.expanduser(str(brain))))
    try:
        import brain_identity
        is_brain = brain_identity.looks_like_brain_root(root)   # BRAIN.md o CLAUDE.md
    except Exception:
        is_brain = os.path.isfile(os.path.join(root, 'CLAUDE.md'))
    if not brain or not os.path.isdir(root) or not is_brain:
        return False
    path = Path(settings_path or os.path.join(_agy_home(),'settings.json'))
    try:
        if path.is_symlink():
            return False
        if path.exists() and path.stat().st_size > 1024*1024:
            return False
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if not isinstance(data,dict):
            return False
        original = json.dumps(data,sort_keys=True)
        trusted = data.setdefault('trustedWorkspaces',[])
        permissions = data.setdefault('permissions',{})
        if not isinstance(trusted,list) or not isinstance(permissions,dict):
            return False
        allowed = permissions.setdefault('allow',[])
        if not isinstance(allowed,list):
            return False
        if root not in trusted:
            trusted.append(root)
        rule = 'write_file(%s)' % root
        legacy_rule = 'read_file(%s)' % root
        if not write:
            rule, legacy_rule = legacy_rule, rule
        if legacy_rule in allowed:
            allowed[:] = [r for r in allowed if r != legacy_rule]
        if rule not in allowed:
            allowed.append(rule)
        # memoria v1: el agente guarda con `workspace memoria …` sin que agy
        # pregunte en cada nota (como Claude Code con su --settings). Solo ese
        # subcomando: escribe con validación y solo en la memoria del cerebro.
        allowed[:] = [r for r in allowed if r not in _MEMORIA_RULES_VIEJAS]
        for r in MEMORIA_RULES:
            if r not in allowed:
                allowed.append(r)
        if original != json.dumps(data,sort_keys=True):
            if path.exists():
                backup = path.with_name('settings.workspace-brain-access-backup.json')
                if not backup.exists():
                    _atomic(backup,json.loads(path.read_text(encoding='utf-8')))
            _atomic(path,data)
        return True
    except (OSError,ValueError,TypeError):
        return False


# ── autonomía full: proyecto de agy POR AGENTE ──────────────────────────────
# El permiso de agy para correr comandos sin preguntar (`toolPermission` o una
# regla `command(*)` en settings.json) es GLOBAL. Por agente, lo único que
# agy respeta sin --dangerously-* es el PROYECTO: ~/.gemini/config/projects/
# <id>.json con `permissionGrants.permissionGrants.allow` — VERIFICADO (agy
# 1.3.4, HOME temporal): con `--project <id>` y `command(*)` ahí, la terminal
# corre sin preguntar y escribir fuera del cerebro sigue negado; sin el
# proyecto, pregunta. Al reanudar manda el proyecto de la CONVERSACIÓN.
# Workspace solo toca archivos `workspace-<agente>.json` cuyo `id` coincide
# (los suyos); y solo su propia regla: el resto del archivo se conserva.

def _projects_dir():
    return os.path.join(os.path.expanduser("~"), ".gemini", "config", "projects")


def project_id(agent):
    """`workspace-<agente>` saneado ([a-z0-9-]); '' si no queda nombre."""
    import re
    k = re.sub(r"[^a-z0-9-]+", "-", str(agent or "").strip().lower()).strip("-")
    return (PROJECT_PREFIX + k)[:64] if k else ""


def ensure_agent_project(agent, autonomy, display="", projects_dir=None):
    """Alinea el proyecto de agy del agente con su autonomía. full → crea o
    actualiza `<dir>/workspace-<agente>.json` con la regla `command(*)` y
    devuelve su id (para `--project`). brain → si el proyecto existe y es
    nuestro, le QUITA esa regla (sus conversaciones vuelven a preguntar) y
    devuelve ''. Un archivo con el mismo nombre que no sea nuestro (otro
    `id`, ilegible) no se toca. Falla-suave: ante cualquier error → ''."""
    from antigravity_usage import _atomic
    pid = project_id(agent)
    if not pid:
        return ""
    path = os.path.join(projects_dir or _projects_dir(), pid + ".json")
    try:
        cur = None
        if os.path.exists(path):
            if os.path.islink(path) or os.path.getsize(path) > 1024 * 1024:
                return ""
            with open(path, encoding="utf-8") as fh:
                cur = json.load(fh)
            if not isinstance(cur, dict) or cur.get("id") != pid:
                return ""
        if autonomy != "full":
            if cur is None:
                return ""
            grants = (cur.get("permissionGrants") or {}).get("permissionGrants") or {}
            allow = grants.get("allow") if isinstance(grants, dict) else None
            if isinstance(allow, list) and FULL_GRANT in allow:
                grants["allow"] = [r for r in allow if r != FULL_GRANT]
                _atomic(path, cur)
            return ""
        data = dict(cur or {"id": pid, "projectResources": {}})
        data["id"] = pid
        data.setdefault("name", "%s · Workspace" % (display or agent))
        data.setdefault("projectResources", {})
        pg = data.get("permissionGrants")
        if not isinstance(pg, dict):
            pg = {}
        inner = pg.get("permissionGrants")
        if not isinstance(inner, dict):
            inner = {}
        allow = inner.get("allow") if isinstance(inner.get("allow"), list) else []
        if FULL_GRANT not in allow:
            allow = allow + [FULL_GRANT]
        inner["allow"] = allow
        pg["permissionGrants"] = inner
        pg.setdefault("v2Migrated", True)
        data["permissionGrants"] = pg
        if data != cur:
            _atomic(path, data)
        return pid
    except (OSError, ValueError, TypeError, AttributeError):
        return ""


# ── tema: recolor de los colores ANSI que usa agy (OSC 4 / OSC 104) ─────────
PALETTE_RESET = "\033]104;2;4;8;12\007"


def _color_scheme(settings_path=None):
    """`colorScheme` de agy ("terminal" si no está fijado). Solo lectura."""
    try:
        with open(settings_path or os.path.join(_agy_home(), "settings.json"),
                  encoding="utf-8") as fh:
            data = json.load(fh)
        v = data.get("colorScheme") if isinstance(data, dict) else None
        return str(v).strip().lower() if v else "terminal"
    except (OSError, ValueError):
        return "terminal"


def palette_osc(settings_path=None):
    """OSC 4 para los slots ANSI que pinta agy (2, 4, 8, 12) desde la paleta
    del hub, o '' si no aplica: el socio eligió otro colorScheme (se respeta;
    nunca se escribe el suyo), terminal sin color, o paleta no resoluble."""
    if _color_scheme(settings_path) != "terminal":
        return ""
    try:
        import tuitheme
        if tuitheme.color_mode() == "mono":
            return ""
        import theme_render
        pal = theme_render.hub_engine_palette()
        if not pal:
            return ""
        out = ""
        for n, hx in theme_render.ansi_slots(pal):
            out += "\033]4;%d;rgb:%s/%s/%s\007" % (n, hx[1:3], hx[3:5], hx[5:7])
        return out
    except Exception:
        return ""


def _tty_write(seq):
    """Escribe una secuencia OSC a la terminal REAL (no a un stdout
    redirigido). Solo con tty. Falla-suave."""
    if not seq:
        return False
    try:
        if not sys.stdout.isatty():
            return False
        import theme
        w = theme._tty()
        w.write(seq)
        w.flush()
        return True
    except Exception:
        return False


# ── GEMINI.md generado (identidad + bloque de sesión INVISIBLE) ─────────────
def _gemini_path(brain):
    return os.path.join(brain, "GEMINI.md")


def _gemini_is_custom(brain):
    """¿El GEMINI.md existente es PROPIO del socio (sin nuestra marca, ni la
    actual ni la legacy pre-rename)? Su CONTENIDO jamás se pisa — gana el
    socio (el bloque de sesión solo se ANEXA/limpia, marcado)."""
    p = _gemini_path(brain)
    try:
        if not os.path.exists(p):
            return False
        with open(p, encoding="utf-8", errors="replace") as fh:
            head = fh.read().lstrip()
        return not (head.startswith(_GEMINI_MARK)
                    or head.startswith(_GEMINI_MARK_LEGACY))
    except Exception:
        return True          # ilegible → trátalo como del socio (no pisar)


def _write_gemini(brain, ctx, session_block=""):
    """Escribe el GEMINI.md GENERADO (arranque + contexto neutral + bloque de
    la pestaña activa). Atómico; jamás pisa un GEMINI.md del socio. Devuelve
    True si quedó escrito. NUNCA levanta (el launch no depende de esto)."""
    try:
        if _gemini_is_custom(brain):
            return False
        try:
            import brain_identity
            doc = brain_identity.identity_doc(brain)
        except Exception:
            doc = "CLAUDE.md"
        # A-VERIFICAR: pasar a rutas RELATIVAS (el GEMINI.md se sincroniza y hoy
        # lleva la ruta de esta máquina). No se cambia sin verificar que el
        # lector de archivos de agy las acepte.
        body = (_GEMINI_MARK + "\n# Arranque de WORKSPACE\n"
                "El cerebro de esta sesión está en " + os.path.realpath(brain) + ". "
                "Su identidad está en " + os.path.join(os.path.realpath(brain), doc) + ". "
                "Lee " + doc + " completo y sigue su protocolo de arranque. "
                "Los documentos de estado están en STATE/ (STATE/brain-version.md, "
                "STATE/MEMORY.md, STATE/PENDIENTES.md, STATE/MILESTONES.md). "
                "Durante el arranque usa las herramientas de lectura de archivos; "
                "evita comandos de shell para listar carpetas o comprobar rutas. "
                "El inbox ya está resumido abajo: no vuelvas a consultarlo al iniciar. "
                "No enumeres la configuración ni el protocolo al socio; al terminar "
                "confirma en una línea breve.\n\n" + (ctx or ""))
        if session_block:
            body += "\n\n%s\n%s\n%s\n" % (_SESSION_START, session_block,
                                          _SESSION_END)
        p = _gemini_path(brain)
        tmp = p + ".workspace-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def _split_session_block(text):
    """(texto_sin_bloque, había_bloque). Corta por LÍNEAS completas entre las
    marcas (actuales o legacy pre-rename) — contenido con `-->` adentro no
    rompe el corte; el resto del archivo queda byte-a-byte intacto."""
    out, skip, found = [], False, False
    for ln in (text or "").splitlines(True):
        s = ln.strip()
        if not skip and s in _SESSION_STARTS:
            skip, found = True, True
            continue
        if skip:
            if s in _SESSION_ENDS:
                skip = False
            continue
        out.append(ln)
    return "".join(out), found


def _strip_session_block(brain):
    """Quita el bloque de sesión del GEMINI.md — GENERADO o del socio (solo
    corta entre nuestras marcas; el contenido del socio queda intacto).
    Limpieza al cerrar: el contexto de la pestaña era de ESTA corrida; no
    dejar basura que el siguiente arranque u otro harness lea desfasada.
    Idempotente. Falla-suave."""
    try:
        p = _gemini_path(brain)
        if not os.path.exists(p):
            return False
        with open(p, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        base, found = _split_session_block(txt)
        if not found:
            return False
        tmp = p + ".workspace-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(base.rstrip() + "\n")
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def _gemini_pointer(brain):
    """GEMINI.md en REPOSO (fuera de sesión): puntero GENERADO al doc de
    identidad, sin rutas de esta máquina ni contexto de arranque — es lo que
    viaja con el cerebro cuando se sincroniza."""
    try:
        import brain_identity
        doc = brain_identity.identity_doc(brain)
    except Exception:
        doc = "CLAUDE.md"
    return (_GEMINI_MARK + "\n# Arranque de WORKSPACE\n"
            "Este directorio es el cerebro del agente. Su identidad está en "
            + doc + " (raíz de este directorio). Lee " + doc + " completo y "
            "sigue su protocolo de arranque.\n")


def _restore_gemini(brain):
    """Cierre: deja el GEMINI.md como antes de la sesión. GENERADO → vuelve
    al puntero en reposo (sin la ruta de esta máquina ni el contexto de
    arranque); PROPIO del socio → solo se quita lo que Workspace anexó.
    Idempotente. Falla-suave → False."""
    try:
        p = _gemini_path(brain)
        if not brain or not os.path.isfile(p):
            return False
        if _gemini_is_custom(brain):
            return _strip_session_block(brain)
        body = _gemini_pointer(brain)
        with open(p, encoding="utf-8", errors="replace") as fh:
            if fh.read() == body:
                return False
        tmp = p + ".workspace-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def _append_session_block(brain, block):
    """ANEXA el bloque de sesión MARCADO al final del GEMINI.md PROPIO del
    socio, sin tocar su contenido (fix 2026-10-04: antes la memoria caía al
    primer prompt VISIBLE). Idempotente: strip-antes-de-anexar (un bloque
    huérfano por crash se auto-limpia solo). El cierre lo quita
    (_strip_session_block). Falla-suave → False (el caller decide el
    fallback visible)."""
    try:
        block = (block or "").strip()
        p = _gemini_path(brain)
        if not block or not os.path.isfile(p):
            return False
        with open(p, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        base, _ = _split_session_block(txt)
        body = (base.rstrip() + "\n\n%s\n%s\n%s\n"
                % (_SESSION_START, block, _SESSION_END))
        tmp = p + ".workspace-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    brain = cfg.get("_brain", "")
    agent = str(cfg.get("name") or "")
    auto = _autonomy(cfg)
    if plan:
        pid = ""
        print("  motor: antigravity · CLI agy")
        print("  cerebro: " + brain)
        print("  binario: " + (shutil.which("agy") or "FALTA agy en PATH"))
        print("  %s: %s" % (_t("motorbar.plan.autonomy_short", "autonomía", "autonomy"),
                            _autonomy_text(auto)))
        print("  argumentos: " + repr(_interactive_argv(cfg, passthrough,
                                                        project_id=pid)))
        print("  pestañas: picker compartido + registro neutral — resume: "
              "--conversation <id> (validado); memoria de la pestaña va "
              "INVISIBLE en el GEMINI.md generado; id atado post-hoc "
              "(cache/last_conversations.json, snapshot antes/después)")
        print("  login/sesiones: credenciales las gestiona agy; hooks "
              "nativos sin activar (Workspace emite inicio/cierre)")
        return
    if not brain or not os.path.isdir(brain):
        raise SystemExit("WORKSPACE: cerebro inexistente para Antigravity")
    if not shutil.which("agy"):
        raise SystemExit("WORKSPACE: falta Antigravity CLI (agy) en PATH")

    if not ensure_brain_access(brain, write=auto != "ask"):
        print("WORKSPACE: " + _t(
            "motorbar.agy.access_failed",
            "no pude registrar el acceso del cerebro en Antigravity (pedirá permiso para editarlo).",
            "couldn't register the brain's access in Antigravity (it will ask before editing it)."))
    # «Comandos sin preguntar» ya no existe: si el agente tenía el proyecto de
    # agy con la regla command(*) (versión anterior), se le QUITA aquí. Nunca
    # bloquea el arranque; jamás se pasa --project.
    ensure_agent_project(agent, "brain", cfg.get("display") or agent)
    pid = ""

    # Motor+modelo REAL en el banner (dinámico — regla del socio). El modelo
    # sale del --model del socio si lo pasó; si no, lo elige agy.
    _mdl = ""
    _pt = [str(a) for a in (passthrough or [])]
    for _i, _a in enumerate(_pt):
        if _a == "--model" and _i + 1 < len(_pt):
            _mdl = _pt[_i + 1]; break
        if _a.startswith("--model="):
            _mdl = _a.split("=", 1)[1]; break
    os.environ["WORKSPACE_ENGINE_LABEL"] = (
        "Antigravity · " + (_mdl or "modelo de agy"))
    # Banner del CEREBRO (patrón buffered+width-check compartido con codex).
    if show_banner:
        try:
            from engines import _ui
            _ui.show_brain_banner(cfg)
        except Exception:
            print("  WORKSPACE · %s · Antigravity CLI"
                  % cfg.get("display", cfg.get("name", "")))

    # Pestañas neutrales: mismo picker, registro compartido entre motores.
    # El resume-id local se VALIDA contra el store de agy (conversación
    # borrada → fresco + re-bind, jamás un --conversation muerto en loop).
    tab, resume_cid, session_blk = None, "", ""
    try:
        from engines import _ui
        import sessions_registry as _reg
        from engines import claude_code as _cc
        cfg.setdefault("_engine", "antigravity")
        if not (preselect and preselect.get("wid")):
            _cc.session_preflight(cfg, "antigravity")
        tab = _ui.pick_tab(cfg, preselect=preselect)
        if not tab:
            _cc.warn_no_tab(_cc.LAST_PICK_ERROR)
        if tab:
            wid, wname = tab
            _ui.export_tab_env(cfg, wid, wname)
            _reg.ensure_tab(brain, agent, wname, claude_wid=wid)
            resume_cid = _reg.resume_id(brain, agent, wname, "antigravity")
            if resume_cid and not _conversation_exists(resume_cid):
                resume_cid = ""
            session_blk = _reg.session_doc_block(brain, wname, engine="antigravity",
                                                 resumed=bool(resume_cid))
    except Exception as e:
        # U04/Z04: la causa se ve y se traza (antes: chat sin pestaña en silencio)
        tab, resume_cid, session_blk = None, "", ""
        try:
            from engines import claude_code as _cc
            err = "no pude preparar la pestaña (%s: %s)" % (type(e).__name__, e)
            _cc._session_log(cfg, "antigravity", err)
            _cc.warn_no_tab(err)
        except Exception:
            pass

    # Inyección INVISIBLE por doc de proyecto. GEMINI.md PROPIO del socio →
    # su contenido no se pisa: el bloque de sesión va ANEXADO al final
    # (marcado, strip-antes-de-anexar, se limpia al cerrar). Solo si ni el
    # anexo se pudo escribir, la memoria cae al primer prompt (visible —
    # último recurso honesto).
    first_prompt = ""
    doc_ok = not _gemini_is_custom(brain)
    appended = bool(not doc_ok and session_blk
                    and _append_session_block(brain, session_blk))
    if tab and not doc_ok and not appended and not resume_cid:
        try:
            import sessions_registry as _reg
            first_prompt = _reg.first_prompt_context(brain, tab[1], engine="antigravity")
            print("WORKSPACE: GEMINI.md propio del socio y no pude anexar — "
                  "la memoria de la pestaña irá en el primer mensaje "
                  "(visible).")
        except Exception:
            first_prompt = ""

    args = _interactive_argv(cfg, passthrough, resume_cid=resume_cid,
                             first_prompt=first_prompt, project_id=pid)

    import interactive
    import antigravity_usage
    antigravity_usage.ensure_statusline()

    _appended_ctx = []     # ¿quedó un bloque anexado al doc del socio?

    def save_context(ctx):
        # NUNCA levanta: un GEMINI.md del socio o un disco lleno no deben
        # tumbar el launch (bug cazado en el doble-check: el RuntimeError
        # anterior escapaba por el wrapper y abortaba el arranque).
        # Doc del socio → el contexto va ANEXADO (bloque marcado, invisible,
        # junto con la memoria de la pestaña); solo si tampoco se pudo
        # escribir, se imprime (último canal honesto).
        if _write_gemini(brain, ctx, session_block=session_blk):
            return
        try:
            merged = "\n\n".join(p for p in (session_blk,
                                             (ctx or "").strip()) if p)
            if merged and _append_session_block(brain, merged):
                _appended_ctx.append(True)
                return
        except Exception:
            pass
        if (ctx or "").strip():
            try:
                print("[WORKSPACE · contexto de arranque]\n%s\n" % ctx.strip())
            except Exception:
                pass

    before_cid = _vendor_conversation_for(brain)
    # U10: línea previa + título de la terminal (agy no fija título propio);
    # los números viven en su statusLine nativa (shim de Workspace).
    try:
        from engines import _ui as _bar
        _mode = next((args[i + 1] for i, x in enumerate(args[:-1]) if x == "--mode"), "")
        _perms = ", ".join(p for p in (
            _mode,
            _t("motorbar.agy.commands_free", "comandos sin preguntar", "commands without asking")
            if (pid and "--project" in args) else "",
            "sandbox" if "--sandbox" in args else "") if p) or "los del CLI (agy)"
        _bar_fields = _bar.status_fields(
            cfg, tab, engine_label=os.environ.get("WORKSPACE_ENGINE_LABEL") or "Antigravity",
            perms=_perms,
            saving=("pestaña %s → STATE/sessions" % tab[1]) if tab else "sin pestaña (no se guarda memoria)",
            tokens=_t("motorbar.agy.tokens_in_bar", "en la barra de Antigravity",
                      "in Antigravity's bar"))
        _bar.show_status_bar(_bar_fields)
    except Exception:
        _bar = None
    # Tema: recolorea los colores ANSI que usa agy (solo colorScheme
    # "terminal") y los restaura al salir, pase lo que pase.
    _osc = _tty_write(palette_osc())
    try:
        rc = interactive.run_official_cli_interactive(
            "antigravity", brain=brain, argv=args, context_sink=save_context,
            pending={"tab": tab[1] if tab else "", "agent": agent,
                     "resume_id": resume_cid, "before_cid": before_cid})
    finally:
        if _osc:
            _tty_write(PALETTE_RESET)
    if _bar is not None:
        _bar.clear_title()

    # Limpieza (session_end): el arranque, el contexto y el bloque de sesión
    # eran de ESTA corrida. Doc generado → vuelve al puntero en reposo (sin
    # la ruta de esta máquina: el cerebro se sincroniza); doc del socio → se
    # quita solo lo anexado. Si otra corrida sigue viva en el cerebro, solo
    # sale el bloque de la pestaña. Un crash lo limpia pending_runs al reabrir.
    try:
        import pending_runs
        otra = pending_runs.live_in_brain(brain, exclude=pending_runs.current())
    except Exception:
        otra = False
    if not otra:
        _restore_gemini(brain)
    elif session_blk or appended or _appended_ctx:
        _strip_session_block(brain)
    # Binding POST-HOC: solo si el cache CAMBIÓ durante esta corrida (un id
    # stale de una corrida vieja del mismo cerebro NO se bindea a esta
    # pestaña — bug cazado en el doble-check) y no es el que ya teníamos.
    if tab:
        try:
            import sessions_registry as _reg
            cid = _vendor_conversation_for(brain)
            if cid and cid != before_cid and cid != resume_cid:
                _reg.bind(brain, agent, tab[1], "antigravity", cid)
        except Exception:
            pass
    try:
        import pending_runs
        pending_runs.done()               # atado y limpieza hechos: ya no está pendiente
    except Exception:
        pass
    sys.exit(rc if isinstance(rc, int) else 0)


def pick(cfg):
    """El picker de pestañas ahora es COMPARTIDO (registro neutral): misma
    elección cruda que claude_code.pick — para el hub tmux. Falla-suave."""
    try:
        from engines import _ui
        cfg.setdefault("_engine", "antigravity")
        return _ui.pick_keep_label(cfg, "Antigravity · modelo de agy")
    except Exception:
        return ""


def _autonomy(cfg):
    try:
        from engines import _ui
        return _ui.autonomy(cfg)
    except Exception:
        return "brain"


def _t(key, es, en=None, **kw):
    try:
        import workspace_status
        return workspace_status.t(key, es, en, **kw)
    except Exception:
        return es


def _autonomy_text(auto):
    """Qué significa la autonomía del agente EN ANTIGRAVITY, en una línea."""
    if auto == "ask":
        return _t("motorbar.agy.ask",
                  "ask — pregunta antes de crear o editar, también en el "
                  "cerebro; terminal y archivos fuera piden permiso",
                  "ask — asks before creating or editing, also in the brain; "
                  "terminal and outside files ask first")
    return _t("motorbar.agy.brain",
              "brain — edita en el cerebro sin preguntar; terminal y archivos "
              "fuera piden permiso",
              "brain — edits in the brain without asking; terminal and outside "
              "files ask first")
