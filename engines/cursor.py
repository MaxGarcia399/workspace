"""WORKSPACE · engines/cursor.py — motor Cursor (Anysphere · CLI `cursor-agent`).

Hace ejecutable un agente sobre el CLI oficial de Cursor (`cursor-agent`; el
instalador oficial crea además el alias `agent`). La cuenta es la de Cursor del
socio (`cursor-agent login`); el modelo lo elige el socio dentro del motor
(`/model` en su TUI o su config). Vendor-neutral, enchufable por nombre:
dispatch.py lo carga solo ("cursor" → engines/cursor.py; engines/CONTRACT.md).

🔴 INVARIANTE DE SEGURIDAD (mismo de codex/opencode): las credenciales las
gestiona el BINARIO OFICIAL (llavero del sistema en macOS, archivo en su carpeta
de config en Linux/Windows). WORKSPACE jamás lee, extrae ni reusa tokens: el
estado de la cuenta se consulta con `cursor-agent status --format json` y solo
se lee `isAuthenticated`/`status` (nunca el correo ni nada más).

HECHOS: de la doc oficial (URL al lado) o VERIFICADOS de caja negra, corriendo
el binario (jamás leyendo su código: los términos de Cursor, §1.5, lo
prohíben). Sin cuenta: tests/test_motores_cursor.py · CursorBinarioReal
(2026.10.22 y 2026.11.05). Con cuenta: el e2e v6 (2026-11-02: retoma, capturas
y barra dentro y fuera) y tests/e2e/cursor_caja_negra.py. Lo que aún no tiene
ninguna de las dos va marcado A-VERIFICAR (runbooks §8 cursor):
  · `--version` → «2026.10.22-27dcf5f».
  · `status --format json` → {"status": "unauthenticated"|"partially-
    authenticated"|"authenticated", "isAuthenticated": bool, …}, rc 0 siempre.
    Con sesión pregunta `getMe` al servidor (lectura). La primera vez crea la
    config por defecto del motor (`~/.cursor/cli-config.json`, fuera del
    cerebro).
  · Turno sin ventana: `-p --output-format json` → una línea {"type":"result",
    "subtype":"success","is_error":false,"result":"…","session_id":"…"} (doc:
    https://cursor.com/docs/cli/reference/output-format; al fallar, código
    distinto de 0, error en stderr y sin JSON). Sin cuenta: rc 1 y «Error:
    Authentication required…». Con la entrada estándar
    que no es terminal, el CLI entra solo en modo `-p`. `--` corta las opciones
    (VERIFICADO: `-- --version` no imprime la versión).
  · Carpeta sin confianza: en `-p` falla con «Workspace Trust Required» y en el
    TUI pregunta. `--trust` (doc: --help; changelog oficial: también en el
    TUI) escribe la marca `.workspace-trusted` en `~/.cursor/projects/<ruta>/`
    (estado del motor, FUERA del cerebro; visto con cuenta: e2e v6 y
    cursor_caja_negra.py). Sin cuenta (2026.11.05) no la escribe.
  · Sesiones: `~/.cursor/chats/<md5(carpeta)>/<uuid>/store.db` (SQLite de blobs
    propietario) y, escrita por el propio CLI en cada turno, una copia legible
    en `~/.cursor/projects/<ruta>/agent-transcripts/<uuid>/<uuid>.jsonl`
    ({"role","message":{"content":[{type:text|tool_use}]}} + {"type":
    "turn_ended"}). Sin doc de esas rutas (el changelog oficial solo dice que
    los transcripts quedan en disco, en `agent-transcripts/`): vistas con
    cuenta, la retoma y la captura del e2e v6 dependen de ellas, y
    cursor_caja_negra.py las vuelve a mirar. Retomar: `--resume <uuid>` (doc:
    --help). `create-chat` NO termina sin cuenta (2026.10.22 y 2026.11.05,
    CursorBinarioReal): no se usa.
  · Lee como reglas `AGENTS.md` y `CLAUDE.md` de la raíz y `.cursor/rules/*.mdc`
    (doc: https://cursor.com/docs/cli/using.md#rules y
    https://cursor.com/docs/rules). En un cerebro v2 el `CLAUDE.md` es solo
    un puntero («@BRAIN.md»): lo lea como lo lea, la identidad es una sola
    (identidad del e2e v6 en verde).
  · Corre los hooks de Claude Code de `<carpeta>/.claude/settings*.json` y de
    `~/.claude/settings.json` (doc: «Third Party Hooks»,
    https://cursor.com/docs/reference/third-party-hooks; encendido de
    fábrica). El de Workspace en el
    cerebro se apaga solo dentro de Cursor (workspace_hook.py: payload con
    `cursor_version`): el ciclo lo emite el wrapper, como en codex. En Windows
    los corre con PowerShell solo si no ve Git Bash (ver sin_git_bash).

BARRA: la statusLine NATIVA de Cursor (`statusLine` de `cli-config.json`, solo
la de usuario; VERIFICADO 2026.10.22 en una pty) apunta al shim estable
`~/.local/bin/workspace-cursor-statusline`. Cursor la pone EN LUGAR de la fila
nativa del pie, así que la barra de Workspace repone lo que esa fila traía
(modelo, %, carpeta · rama) además del agente y la pestaña; los «N archivos
editados» no vienen en su JSON y se pierden. Una statusLine del socio JAMÁS se
toca; opt-out WORKSPACE_CURSOR_NO_STATUSLINE=1 (la quita). Ver motor_statusline.

MEMORIA SIN PEDIR PERMISO: la herramienta MCP de Workspace (memoria_mcp:
`guardar_nota`, `guardar_resumen`, `ver_memoria`, sin terminal), con la config
documentada de PROYECTO en el cerebro: el servidor en `.cursor/mcp.json`, sus
herramientas en `permissions.allow` de `.cursor/cli.json`
(`Mcp(workspace-memoria:<herramienta>)`) y `cursor-agent mcp enable
workspace-memoria` («Add an MCP server to the local approved list»), que
aprueba SOLO ese servidor y queda atado a su config (VERIFICADO 2026.10.22:
si alguien cambia el comando, Cursor vuelve a pedir aprobación). No se usa
`--approve-mcps`: aprobaría también lo que un agente agregue al mcp.json del
cerebro. Antes iba por la RUTA de un comando (`Shell(<ruta>)` en la config de
usuario): en Windows se colaba otro comando (Cursor analiza con gramática de
bash y ejecuta PowerShell); esa regla se quita al abrir
(memoria_permiso.retirar_aprobaciones).

Cero dependencias (stdlib, 3.9+). Mac/Windows. Falla-suave.
"""
import hashlib
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
import arbol_procesos  # noqa: E402  (Windows: al vencer el tiempo muere el árbol entero)

META = {"name": "cursor", "needs": ["cursor-agent"], "auth": "subscription"}

#: Matriz de capacidades (contrato harness-os §3; la consume harnesses.py).
#: TODAS las claves de capabilities.ENGINE_KEYS (lo exige test_capabilities).
CAPABILITIES = {
    "launch": "wrapper",          # TUI oficial envuelto en el ciclo neutral
    "inject_context": "project-doc",  # AGENTS.md puntero → doc de identidad
    "mcp": True,                  # `cursor-agent mcp` (.cursor/mcp.json o ~/.cursor/mcp.json)
    "hooks": "wrapper",           # solo inicio/cierre del wrapper; los hooks propios
                                  # de Cursor (y los de Claude Code que importa) no
                                  # se cablean (doble disparo)
    "sessions": "workspace",      # pestañas del registro neutral: Cursor crea el
                                  # chat, se ata al cerrar y se retoma con --resume
    "status_live": False,         # sin now.json desde dentro (sin hooks por turno)
    "headless": True,             # run_turn (`-p --output-format json`; forma de
                                  # la doc: cursor.com/docs/cli/reference/output-format)
    "statusline": "native-config",  # su statusLine nativa (cli-config.json de
                                    # usuario) → shim de Workspace; la del
                                    # socio gana (motor_statusline)
}

BINARY = "cursor-agent"

#: Versiones del CLI oficial con las que se VERIFICARON las lecturas de este
#: adapter (engine_versions: doctor avisa si la instalada es de otra línea).
#: 2026.10.22-27dcf5f (macOS arm64): ayuda, `status --format json`, rutas de
#: chats y transcripts, `--trust`, `--` y el error sin cuenta.
VERIFIED_VERSIONS = ("2026.10.22",)

# 🔴 EL HARNESS NO FIJA MODELO (regla de producto, 2026-10-15). El modelo lo
# elige el socio dentro de Cursor — este adapter JAMÁS pasa `--model` en el
# launch, ni lee/copia la config del socio. En run_turn, `model` es solo un
# override OPCIONAL para smokes/eval (nunca un default).

#: Opt-out de la confianza automática del cerebro (`--trust` por corrida).
_NO_AUTOTRUST_ENV = "WORKSPACE_CURSOR_NO_AUTOTRUST"
#: Subcomandos del CLI (2026.10.22): si el socio pasa uno, va tal cual.
_SUBCOMMANDS = frozenset((
    "persist", "install-shell-integration", "uninstall-shell-integration",
    "login", "logout", "mcp", "plugin", "worker", "status", "whoami", "models",
    "team", "bedrock", "about", "update", "create-chat", "generate-rule", "rule",
    "agent", "ls", "resume", "help"))
_TRUST_FLAGS = ("--trust", "-f", "--force", "--yolo")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{12}")

#: Cache corto de session_active — no spamear `status` por tick.
_SESSION_TTL = 30.0
_session_cache = {"ts": 0.0, "val": None}

# La verificación de sesión corre el programa oficial DESPEGADO de la terminal
# (como codex): si hereda la terminal, al salir puede dejarla sin teclado.
_DETACHED = {"stdin": subprocess.DEVNULL}
if os.name != "nt":
    _DETACHED["start_new_session"] = True


def _exe(override=None):
    """Ruta al binario. override=None → PATH; override="" → no hay (tests);
    override="/ruta" → esa ruta. Solo `cursor-agent`: el alias `agent` es un
    nombre genérico que puede ser otro programa."""
    if override is None:
        return shutil.which(BINARY)
    return override or None


def _env_motor():
    """El env para correr el CLI del motor: sin NADA de la bóveda
    (secret_store.engine_env). Falla-suave: sin secret_store, el heredado."""
    try:
        import secret_store
        return secret_store.engine_env()
    except Exception:
        return None


def _windows():
    """¿Windows? (aparte para probar ese camino en Mac/Linux)."""
    return os.name == "nt"


def sin_git_bash(env):
    """`env` (dict u os.environ, se cambia ahí mismo y se devuelve) sin lo que
    hace a Cursor elegir Git Bash en Windows: MSYSTEM siempre y SHELL salvo
    que nombre PowerShell. Fuera de Windows no se toca nada.

    VERIFICADO 2026-11-05 en vivo, de caja negra (Windows 11, cursor-agent
    2026.11.05-86047df, con cuenta): Cursor muestra cada hook envuelto en
    PowerShell («$OutputEncoding = [System.Text.UTF8Encoding]::new(
    $false); … Get-Content -LiteralPath '…\\cursor-hooks-…\\payload.json' -Raw
    … | & { $input | <command> }»), y con MSYSTEM (abierto desde Git Bash) o
    un SHELL de Git Bash ese envoltorio lo evalúa bash: «--: eval: line 1:
    syntax error near unexpected token `('» y «Hook blocked with message: …»
    en CADA herramienta (los hooks de Workspace en el cerebro; el agente ni
    leía BRAIN.md). El error está en el envoltorio de Cursor, antes de nuestro
    comando (se ve en el mensaje), y su documentación no da cómo apagar esos
    hooks. Sin esas dos variables elige
    PowerShell, como al abrirlo desde PowerShell o Windows Terminal: el
    envoltorio corre y el hook de Workspace se apaga solo (`cursor_version`).
    Por corrida: no se escribe nada en la config del socio."""
    if env is None or not _windows():
        return env
    env.pop("MSYSTEM", None)
    sh = str(env.get("SHELL") or "").lower()
    if sh and "pwsh" not in sh and "powershell" not in sh:
        env.pop("SHELL", None)
    return env


def _sin_consola():
    """Windows: la captura al cerrar corre SIN consola (lección de opencode:
    tras Ctrl+C, un proceso nuevo colgado de esa consola falla al arrancar)."""
    return ({"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            if os.name == "nt" else {})


# ── macOS: no ejecutar un programa que Gatekeeper retiene ───────────────────

def gatekeeper_block(exe=None):
    """None si macOS deja correr `cursor-agent`; si no, {path, cask, files,
    why} (engine_gatekeeper.check, revisando también sus módulos `.node`). El
    cask `cursor-cli` dejó esos módulos en cuarentena: cada `cursor-agent
    status` (al abrir Motores o el hub) abría el diálogo de macOS y el CLI
    moría («library load disallowed by system policy»; VERIFICADO 2026-10-28).
    Workspace NO lo ejecuta y Motores ofrece reinstalar con la receta oficial."""
    exe = exe or _exe()
    if not exe:
        return None
    try:
        import engine_gatekeeper as _gk
        info = _gk.check(exe, native=True)
        return dict(info, why=_gk.message(info)) if info else None
    except Exception:
        return None


def account_menu(active=None, exe=None):
    """«cuenta y proveedor» en Motores (engines_tui._account), según la sesión.

    Cursor NO tiene selector de modelo fuera del chat (VERIFICADO 2026.10.22,
    `cursor-agent --help`): `models` solo LISTA los de la cuenta y el modelo se
    elige dentro del TUI con /model (o `--model` por corrida, que Workspace no
    pasa). La cuenta es la de Cursor; `status` la muestra (lo imprime Cursor:
    Workspace no lee el correo).
      · sin sesión (False) → None: Motores corre `cursor-agent login`;
      · con sesión o sin saber → ver la cuenta, ver los modelos, abrir Cursor
        (en una carpeta vacía) y cambiar de cuenta (`logout` + `login`, Motores
        lo confirma)."""
    if active is False:
        return None
    acts = [("whoami", [BINARY, "status"])]
    if active is None:
        acts.append(("login", [BINARY, "login"]))
    acts += [("models", [BINARY, "models"]), ("open", [BINARY]),
             ("switch", [[BINARY, "logout"], [BINARY, "login"]])]
    return {"model": "/model", "actions": acts}


# ── cuenta ──────────────────────────────────────────────────────────────────

def parse_status(text):
    """Salida de `status --format json` → True/False/None. Solo mira
    `isAuthenticated`/`status`; jamás devuelve ni guarda el resto (correo,
    equipo). «No reconocido» = None, nunca False (runbook §6b)."""
    out = text or ""
    i = out.find("{")
    if i < 0:
        return None
    try:
        data = json.loads(out[i:out.rfind("}") + 1])
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    auth = data.get("isAuthenticated")
    if auth is True:
        return True
    st = str(data.get("status") or "")
    if auth is False and st in ("unauthenticated", "partially-authenticated"):
        return False
    return None


def session_active(exe_override=None, runner=None):
    """¿Hay cuenta de Cursor con sesión? True/False, o None si no se pudo saber
    (la UI lo muestra como desconocido). Sin binario → False. Con
    CURSOR_API_KEY en el entorno del motor el CLI entra con la llave aunque
    `status` diga «sin sesión»: entonces None (no se bloquea a ciegas)."""
    now = time.time()
    if (runner is None and exe_override is None and _session_cache["val"] is not None
            and now - _session_cache["ts"] < _SESSION_TTL):
        return _session_cache["val"]
    exe = _exe(exe_override)
    if not exe:
        return False
    if gatekeeper_block(exe):              # `status` abriría el diálogo de macOS
        return None
    cmd = [exe, "status", "--format", "json"]
    try:
        if runner is not None:
            r = runner(cmd)
        else:
            r = arbol_procesos.run(cmd, capture_output=True, text=True, timeout=20,
                                   encoding="utf-8", errors="replace",
                                   env=_env_motor(), **_DETACHED)
        val = None if getattr(r, "returncode", 1) != 0 else \
            parse_status(getattr(r, "stdout", "") or "")
    except Exception:
        val = None
    if val is False:
        env = _env_motor() or os.environ
        if str(env.get("CURSOR_API_KEY") or "").strip():
            val = None
    if runner is None and exe_override is None:
        _session_cache.update(ts=now, val=val)
    return val


def available(exe_override=None):
    """LISTO para ejecutar agentes: binario en PATH (Cursor pide la cuenta)."""
    return bool(_exe(exe_override))


def status(exe_override=None, runner=None):
    """Estado honesto del motor (doctor / plan / harnesses.registry). Solo
    inspecciona: binario + `status --format json` (sin tokens)."""
    exe = _exe(exe_override)
    blk = gatekeeper_block(exe) if exe else None
    if blk:
        return {"engine": "cursor", "binary": BINARY, "binary_in_path": True,
                "session_active": None, "ready": False, "gatekeeper": blk,
                "detail": blk["why"],
                "auth": "cuenta de Cursor vía `cursor-agent login`; WORKSPACE nunca "
                        "ve el token"}
    # Con la caché de session_active (30 s), como los demás motores: `status`
    # pregunta `getMe` al servidor (hasta 20 s) y Motores/doctor lo piden seguido.
    active = session_active(exe_override=exe_override, runner=runner) if exe else False
    return {"engine": "cursor", "binary": BINARY, "binary_in_path": bool(exe),
            "session_active": active,
            # ready = binario + cuenta (o desconocido: no se bloquea por una
            # lectura fallida; sí cuando Cursor dice que no hay sesión).
            "ready": bool(exe) and active is not False,
            "auth": "cuenta de Cursor vía `cursor-agent login`; WORKSPACE nunca "
                    "ve el token"}


# ── rutas del motor (estado propio, fuera del cerebro) ──────────────────────

def config_dir(env=None):
    """Carpeta de config de Cursor: CURSOR_CONFIG_DIR → $XDG_CONFIG_HOME/cursor
    → ~/.cursor (doc: https://cursor.com/docs/cli/reference/configuration; la
    doc dice XDG «Linux/BSD», pero en macOS también la usa: VERIFICADO de caja
    negra 2026.11.05, CursorBinarioReal.test_carpeta_de_config; Windows
    A-VERIFICAR). Ahí viven los chats (`chats/`) y `cli-config.json`."""
    env = os.environ if env is None else env
    d = str(env.get("CURSOR_CONFIG_DIR") or "").strip()
    if d:
        return d
    x = str(env.get("XDG_CONFIG_HOME") or "").strip()
    return os.path.join(x, "cursor") if x else os.path.join(os.path.expanduser("~"), ".cursor")


def data_dir(env=None):
    """Carpeta de datos (~/.cursor): `projects/` con la marca de confianza y
    los transcripts legibles (vistos con cuenta, e2e v6). CURSOR_DATA_DIR no
    está en la doc: se respeta si el socio la pone, A-VERIFICAR de caja negra
    con cuenta (tests/e2e/cursor_caja_negra.py --aislado)."""
    env = os.environ if env is None else env
    d = str(env.get("CURSOR_DATA_DIR") or "").strip()
    return d or os.path.join(os.path.expanduser("~"), ".cursor")


def _cwd_forms(brain):
    """Las formas de la ruta del cerebro que Cursor puede haber visto como su
    carpeta: la real (sin enlaces) y la que se le dio. No hay doc de cuál usa:
    se buscan las dos (cursor_caja_negra.py abre por un enlace y dice cuál)."""
    out = []
    for p in (os.path.realpath(str(brain)), os.path.abspath(str(brain))):
        if p and p not in out:
            out.append(p)
    return out


def project_slug(path):
    """Nombre de la carpeta de un proyecto en `~/.cursor/projects/`: todo lo no
    alfanumérico → «-», sin repetidos ni en los bordes. Sin doc: es la forma
    que se ve en `projects/` (la captura del e2e v6 la usa) y
    cursor_caja_negra.py la prueba con espacios, corchetes y acento."""
    s = re.sub(r"[^a-zA-Z0-9]", "-", str(path or ""))
    return re.sub(r"-+", "-", s).strip("-")


def chats_dirs(brain, env=None):
    """`<config>/chats/<md5(carpeta)>` para cada forma de la ruta."""
    base = os.path.join(config_dir(env), "chats")
    return [os.path.join(base, hashlib.md5(p.encode("utf-8")).hexdigest())
            for p in _cwd_forms(brain)]


def project_dirs(brain, env=None):
    base = os.path.join(data_dir(env), "projects")
    return [os.path.join(base, project_slug(p)) for p in _cwd_forms(brain)]


def valid_chat_id(cid):
    return bool(_UUID.fullmatch(str(cid or "")))


def list_chats(brain, env=None):
    """{id: ruta de su store.db} de los chats de Cursor de ESTE cerebro."""
    out = {}
    for d in chats_dirs(brain, env):
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            db = os.path.join(d, n, "store.db")
            if valid_chat_id(n) and os.path.isfile(db):
                out.setdefault(n, db)
    return out


def chat_db(brain, cid, env=None):
    """Ruta del store.db del chat `cid` de este cerebro, o ''."""
    if not valid_chat_id(cid):
        return ""
    for d in chats_dirs(brain, env):
        db = os.path.join(d, cid, "store.db")
        if os.path.isfile(db):
            return db
    return ""


def transcript_path(brain, cid, env=None):
    """El transcript legible que escribe el CLI para el chat `cid`, o ''."""
    if not valid_chat_id(cid):
        return ""
    for d in project_dirs(brain, env):
        for rel in (os.path.join("agent-transcripts", cid, cid + ".jsonl"),
                    os.path.join("agent-transcripts", cid + ".jsonl")):
            p = os.path.join(d, rel)
            if os.path.isfile(p):
                return p
    return ""


TRUST_MARK = ".workspace-trusted"
#: Las marcas de confianza que dejó un `--trust` de Workspace (no las que el
#: socio aceptó en Cursor): el desinstalador quita solo esas.
_CONFIANZA_STATE = "cursor-confianza.json"


def trusted(brain, env=None):
    """¿Cursor ya tiene la marca de confianza de este cerebro? (solo lectura)"""
    return any(os.path.isfile(os.path.join(d, TRUST_MARK))
               for d in project_dirs(brain, env))


def es_cerebro(path):
    """¿`path` es el cerebro de un agente registrado en esta máquina? Solo ahí
    confía Workspace por el socio (un turno sin ventana en otra carpeta —una
    temporal, la copia efímera de una evaluación— no deja confianza)."""
    if not path:
        return False
    try:
        import agentsreg
        p = os.path.realpath(str(path))
        return any(os.path.realpath(a["brain"]) == p for a in agentsreg.agents())
    except Exception:
        return False


def _confianza_path(home=None):
    import paths
    return os.path.join(paths.state_dir(home), _CONFIANZA_STATE)


def confianzas_de_workspace(home=None):
    """Carpetas de `projects/` donde Workspace dejó la marca de confianza."""
    try:
        with open(_confianza_path(home), encoding="utf-8") as fh:
            data = json.load(fh)
        dirs = data.get("dirs") if isinstance(data, dict) else None
        return [str(d) for d in dirs if isinstance(d, str)] if isinstance(dirs, list) else []
    except (OSError, ValueError):
        return []


def anotar_confianza(brain, env=None):
    """Tras un `--trust` de Workspace en un cerebro que NO tenía la marca:
    anota dónde la dejó Cursor. Falla-suave."""
    try:
        nuevas = [d for d in project_dirs(brain, env) if os.path.isfile(os.path.join(d, TRUST_MARK))]
        cur = confianzas_de_workspace()
        falta = [d for d in nuevas if d not in cur]
        if not falta:
            return
        p = _confianza_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = "%s.%d.tmp" % (p, os.getpid())
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"dirs": cur + falta}, fh, indent=1)
        os.replace(tmp, p)
    except OSError:
        pass


_USER_QUERY = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.S | re.I)


def user_text(text):
    """Texto VISIBLE de un mensaje del socio en el transcript de Cursor: el
    CLI ya quita sus bloques de sistema; si el pedido viene envuelto en
    `<user_query>`, queda solo lo de adentro."""
    t = str(text or "")
    hits = [m.group(1) for m in _USER_QUERY.finditer(t)]
    return ("\n\n".join(h for h in hits if h.strip()) if hits else t).strip()


def _first_user_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                try:
                    row = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("role") == "user":
                    parts = (row.get("message") or {}).get("content") or []
                    return user_text(" ".join(str(p.get("text") or "") for p in parts
                                              if isinstance(p, dict)
                                              and p.get("type") == "text"))
    except OSError:
        pass
    return ""


def session_marker(cfg, tab_name):
    """Marca de la pestaña en el mensaje de arranque: con dos pestañas abriendo
    a la vez en el mismo cerebro, distingue cuál chat es de cuál. En Windows el
    lanzador de Cursor es un `.cmd` (cmd.exe vuelve a leer cada argumento):
    va saneada (memoria.argv_seguro), igual que la búsqueda. La MISMA de
    opencode."""
    from engines.opencode import session_marker as _marca
    return _marca(cfg, tab_name)


def find_new_session(brain, find, env=None):
    """El chat que creó ESTA pestaña. `find` = {t0, before, marker}:
    candidatos = chats nuevos (no estaban antes de abrir) tocados después de
    t0; de ellos, el que lleva la marca de la pestaña en su primer mensaje
    (también si es uno solo: si esta pestaña no llegó a crear el suyo, no se
    apropia del de otra). Sin marca, solo un candidato único. Ambiguo o
    ninguno → '' (no se adivina)."""
    t0 = float((find or {}).get("t0") or 0)
    before = set((find or {}).get("before") or [])
    cands = []
    for cid, db in sorted(list_chats(brain, env).items()):
        if cid in before:
            continue
        try:
            if os.path.getmtime(os.path.dirname(db)) < t0 - 5 \
                    and os.path.getmtime(db) < t0 - 5:
                continue
        except OSError:
            continue
        cands.append(cid)
    if not cands:
        return ""
    marker = str((find or {}).get("marker") or "")
    if not marker:
        return cands[0] if len(cands) == 1 else ""
    hits = [c for c in cands if marker in _first_user_text(transcript_path(brain, c, env))]
    return hits[0] if len(hits) == 1 else ""


# ── turno sin ventana ───────────────────────────────────────────────────────

def _parse_result(text):
    """(ok, texto) de la salida de `-p --output-format json`: la línea
    {"type":"result",…}. Sin JSON reconocible → (None, crudo)."""
    for ln in reversed((text or "").splitlines()):
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "result":
            res = ev.get("result")
            res = res if isinstance(res, str) else ""
            return (not ev.get("is_error") and ev.get("subtype", "success") == "success"), res
    return None, text or ""


def run_turn(prompt, *, model=None, cwd=None, timeout=120,
             exe_override=None, runner=None):
    """UN turno HEADLESS: `cursor-agent -p --output-format json [--trust] --
    <mensaje>`. Devuelve (ok, texto). `runner`/`exe_override` son knobs de
    test (la suite jamás corre un Cursor real ni toca la red).

    `--trust` deja una marca PERSISTENTE (`~/.cursor/projects/<carpeta>/`):
    solo va si `cwd` es el cerebro de un agente registrado (es_cerebro) y el
    socio no apagó la confianza automática (WORKSPACE_CURSOR_NO_AUTOTRUST).
    En otra carpeta, Cursor responde «Workspace Trust Required» y el turno
    falla con ese motivo (auditoría 2026-10-30: confiaba en cualquier cwd).

    El mensaje va como argumento DESPUÉS de `--` (un mensaje que empiece con
    `-` no se cuela como opción; VERIFICADO). No hay modo verificado de
    pasarlo por la entrada estándar. En Windows el lanzador oficial es un
    `.cmd`: cmd.exe vuelve a leer el argumento y rompería un mensaje con
    saltos de línea, comillas o %VAR% (lección de opencode, 0.5.1), así que
    ahí ese mensaje se rechaza con el motivo en vez de mandarse roto.
    En `-p`, lo que pediría permiso se niega (no se pasa --force/--yolo)."""
    exe = _exe(exe_override)
    if not exe:
        return False, "cursor-agent no está en PATH"
    blk = gatekeeper_block(exe)
    if blk:
        return False, "cursor-agent: " + blk["why"]
    prompt = prompt or ""
    if str(exe).lower().endswith((".cmd", ".bat")):
        import memoria
        if "\n" in prompt or "\r" in prompt or memoria._ARGV_RARO.search(prompt):
            return False, ("cursor-agent: en Windows el mensaje pasaría por cmd.exe "
                           "(lanzador .cmd) y se rompería; turno sin ventana no "
                           "verificado ahí")
    trust = bool(cwd) and _autotrust() and es_cerebro(cwd)
    cmd = [exe, "-p", "--output-format", "json"] + (["--trust"] if trust else [])
    if model:
        cmd += ["--model", model]
    cmd += ["--", prompt]
    try:
        if cwd:
            os.makedirs(cwd, exist_ok=True)
        confiaba = trusted(cwd) if trust else True
        import secret_store
        env = secret_store.engine_env()   # el motor no hereda la bóveda
        sin_git_bash(env)                 # Windows: sus hooks, en PowerShell
        env["WORKSPACE_NO_AUTOUPDATE"] = "1"
        env["WORKSPACE_REVIEW_RUNNING"] = "1"    # anti-recursión, como codex/opencode/kiro
        if runner is not None:
            r = runner(cmd, cwd=cwd or None, env=env, timeout=timeout)
        else:
            r = arbol_procesos.run(cmd, cwd=cwd or None, env=env, timeout=timeout,
                                   stdin=subprocess.DEVNULL, capture_output=True)
        if not confiaba and trusted(cwd):
            anotar_confianza(cwd)
        rc = getattr(r, "returncode", 1)
        raw_out = getattr(r, "stdout", b"") or b""
        out = raw_out.decode("utf-8", "replace") if isinstance(raw_out, bytes) \
            else str(raw_out)
        if rc != 0:
            raw = getattr(r, "stderr", b"") or b""
            err = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            if not trust and "trust" in (err or out).lower():
                return False, ("cursor-agent: la carpeta %s no es de confianza (Workspace solo "
                               "confía en el cerebro de un agente)" % (cwd or os.getcwd()))
            return False, "cursor-agent exit %d: %s" % (rc, (err or out).strip()[:300])
        ok, text = _parse_result(out)
        if ok is None:
            return False, "cursor-agent: salida sin resultado reconocible: %s" % out[:200]
        return ok, text
    except subprocess.TimeoutExpired:
        return False, "cursor-agent: timeout tras %ss" % timeout
    except OSError as e:
        return False, "cursor-agent: no pude preparar la corrida: %s" % e
    except Exception as e:
        return False, "cursor-agent: fallo al invocar: %s" % e


# ═══════════════════════════════════════════════════════════════════════════
# inject_context — identidad del agente vía AGENTS.md (contrato harness-os §3)
# ═══════════════════════════════════════════════════════════════════════════
# Cursor lee AGENTS.md (misma convención que codex/opencode): el MISMO puntero
# generado, con la misma marca WORKSPACE:GENERATED (engines/opencode.py la
# comparte con codex) → alternar motores en el mismo cerebro re-sincroniza el
# archivo idempotente, sin duplicar la identidad. Cursor también lee CLAUDE.md
# (extensibilidad de terceros, activa por defecto): en un cerebro v2 es el
# puntero `@BRAIN.md` (Cursor no expande imports: llega como una línea); en un
# cerebro anterior, donde CLAUDE.md ES la identidad, Cursor la carga entera y el
# AGENTS.md manda leer ese mismo archivo (sin copia, una sola fuente).

def inject_context(cfg, session_context=""):
    """inject_context de Cursor (ver engines/opencode.inject_agents_md)."""
    from engines.opencode import inject_agents_md
    return inject_agents_md(cfg, session_context=session_context, engine="cursor")


def _identity_doc(cfg):
    from engines.opencode import _identity_doc as _doc
    return _doc(cfg)


def _banner(cfg):
    """Arranque visible mínimo (Windows-safe: sin glifos 0x2600–0x27BF)."""
    name = str(cfg.get("display") or cfg.get("name", "agente")).upper()
    tag = str(cfg.get("tagline", ""))
    C, D = "\033[38;5;111m", "\033[38;5;240m"
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
        print("    %s%s%s%s   %svía Cursor%s" % (B, C, name, R, D, R))
        if tag:
            print("    %s%s%s" % (D, tag, R))
        print("  %s\n" % bar)
        sys.stdout.flush()
    except Exception:
        pass


# ── pestañas: el chat lo CREA Cursor y Workspace lo ata al cerrar ───────────
# Cursor no tiene un modo documentado de crear un chat con un id nuestro
# (`create-chat` no termina sin cuenta: CursorBinarioReal).
# Patrón opencode/hermes: la pestaña nueva abre sin id, con la marca de la
# pestaña en su mensaje de arranque; la captura de cierre encuentra el chat
# nuevo de este cerebro (find_new_session) y se ata; al reabrir, `--resume <id>`
# (validado: si el chat ya no existe, se suelta y abre como nueva).

def _has_session_flag(passthrough):
    """¿El socio eligió sesión a mano (o corre un subcomando)? Gana lo suyo."""
    args = [str(a) for a in passthrough or []]
    if args and args[0] in _SUBCOMMANDS:
        return True
    for a in args:
        if a in ("--resume", "--continue", "--new-session-id") \
                or a.startswith(("--resume=", "--new-session-id=")):
            return True
    return False


def _session_from_passthrough(passthrough):
    """El id de `--resume X` / `--resume=X` que pasó el socio, o ''."""
    args = [str(a) for a in passthrough or []]
    for i, a in enumerate(args):
        if a.startswith("--resume="):
            sid = a.split("=", 1)[1]
        elif a == "--resume" and i + 1 < len(args):
            sid = args[i + 1]
        else:
            continue
        return sid if valid_chat_id(sid) else ""
    return ""


def _autotrust():
    return os.environ.get(_NO_AUTOTRUST_ENV, "").strip().lower() not in (
        "1", "true", "yes", "on", "si", "sí")


def _interactive_argv(cfg, passthrough, session_id="", trust=None):
    """argv DESPUÉS de `cursor-agent`: `--trust` (el cerebro es la carpeta del
    agente: sin esto Cursor pregunta en cada cerebro nuevo; opt-out por env) +
    `--resume <id>` de la pestaña + el passthrough del socio. El harness NO
    fija modelo — Cursor usa el que el socio eligió (regla de producto); un
    `--model` o `--resume` que el socio pase a mano va tal cual y gana. Un
    subcomando del socio (`ls`, `login`…) va solo, sin nada nuestro."""
    args = [str(a) for a in passthrough or []]
    if args and args[0] in _SUBCOMMANDS:
        return args
    out = []
    if (_autotrust() if trust is None else trust) and not any(a in _TRUST_FLAGS for a in args):
        out.append("--trust")
    if session_id and not _has_session_flag(args):
        out += ["--resume", session_id]
    return out + args


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    """Arranca un agente EN CURSOR (interactivo). Delega al wrapper neutral de
    interactive.py (session_start → TUI `cursor-agent` en el cerebro →
    session_end). plan=True NO lanza: imprime el wiring + chequeos."""
    brain = cfg.get("_brain", "")
    exe = _exe()

    if plan:
        line = "─" * 66
        print(line)
        print("  WORKSPACE · plan de arranque — motor CURSOR — agente: %s"
              % cfg.get("display", cfg.get("name")))
        print(line)
        print("  motor       : cursor  (CLI oficial `cursor-agent` · cuenta de Cursor "
              "del socio; WORKSPACE nunca ve el token)")
        print("  modelo      : lo elige el SOCIO dentro de Cursor (Workspace no pasa "
              "--model)")
        print("  cerebro     : %s" % brain)
        print("  identidad   : AGENTS.md puntero → %s (inject_context; marca "
              "WORKSPACE:GENERATED compartida con codex/opencode)" % _identity_doc(cfg))
        print("  pestañas    : picker compartido + registro neutral — Cursor crea el "
              "chat, se ata al cerrar y se retoma con `--resume`; memoria de la "
              "pestaña INVISIBLE en el AGENTS.md")
        print("  confianza   : `--trust` por corrida (marca en ~/.cursor/projects/, "
              "fuera del cerebro; opt-out %s=1)" % _NO_AUTOTRUST_ENV)
        print("  captura     : transcript legible que escribe Cursor "
              "(agent-transcripts/<id>.jsonl); sin él, copia del store.db "
              "(formato sin decodificar)")
        try:
            import motor_statusline as _msl
            print("  barra       : " + _msl.plan_line("cursor"))
        except Exception:
            pass
        try:
            import memoria_mcp
            print("  memoria     : " + memoria_mcp.plan_line("cursor", brain))
        except Exception:
            pass
        print(line)
        print("  [%s] binario cursor-agent en PATH: %s"
              % ("✓" if exe else "✗ FALTA", exe or
                 "(no está — Motores › cursor › instalar)"))
        blk = gatekeeper_block(exe) if exe else None
        if blk:
            print("  [✗] macOS: %s (no se ejecuta: Motores › Cursor › reinstalar)"
                  % blk["why"])
        elif exe:
            try:
                import engine_versions
                ver = engine_versions.installed_version(exe) or "?"
            except Exception:
                ver = "?"
            print("  [✓] versión: %s" % ver)
        print("  [%s] cerebro: %s"
              % ("✓" if brain and os.path.isdir(brain) else "✗ FALTA", brain))
        print(line)
        return

    if not exe:
        print("WORKSPACE: cursor-agent no está en PATH — instálalo "
              "(Motores › cursor › instalar) y entra con `cursor-agent login`.")
        sys.exit(1)
    blk = gatekeeper_block(exe)
    if blk:
        # Ejecutarlo abriría el diálogo de macOS (y volvería en cada llamada).
        print("WORKSPACE: Cursor — %s. Motores › Cursor › reinstalar." % blk["why"])
        sys.exit(1)

    # Memoria sin pedir permiso: la herramienta MCP de Workspace, registrada y
    # aprobada en la config de proyecto del cerebro (`.cursor/`), antes del
    # bloque de la pestaña (sus instrucciones nombran la herramienta solo si
    # quedó lista). Falla-suave: `workspace memoria` pidiendo permiso.
    try:
        import memoria_mcp
        memoria_mcp.preparar("cursor", brain=brain, exe=exe, passthrough=passthrough)
    except Exception:
        pass

    tab, session_id, session_blk = None, "", ""
    agent = str(cfg.get("name") or "")
    cfg.setdefault("_engine", "cursor")
    # Etiqueta honesta ANTES del picker: sin esto el picker compartido (el de
    # Claude Code) y el banner decían «Claude Code». Sin modelo: lo elige el socio.
    os.environ["WORKSPACE_ENGINE_LABEL"] = "Cursor · modelo de tu cuenta"
    try:
        from engines import _ui
        import sessions_registry as _reg
        if not (preselect and preselect.get("wid")):
            from engines import claude_code as _cc0
            _cc0.session_preflight(cfg, "cursor")
        tab = _ui.pick_tab(cfg, preselect=preselect)
        if not tab:
            from engines import claude_code as _cc
            _cc.warn_no_tab(_cc.LAST_PICK_ERROR)
        if tab:
            wid, wname = tab
            _ui.export_tab_env(cfg, wid, wname)
            _reg.ensure_tab(brain, agent, wname, claude_wid=wid)
            session_id = _reg.resume_id(brain, agent, wname, "cursor") or ""
            if not valid_chat_id(session_id):
                session_id = ""
            elif not chat_db(brain, session_id):
                # el chat atado ya no existe (borrado, otra máquina): se suelta
                # y la pestaña abre como nueva (la captura ata el que cree Cursor)
                _reg.unbind(brain, agent, wname, "cursor", session_id)
                session_id = ""
            session_blk = _reg.session_doc_block(brain, wname, engine="cursor",
                                                 resumed=bool(session_id))
    except Exception as e:
        tab, session_id, session_blk = None, "", ""
        try:
            from engines import claude_code as _cc
            err = "no pude preparar la pestaña (%s: %s)" % (type(e).__name__, e)
            _cc._session_log(cfg, "cursor", err)
            _cc.warn_no_tab(err)
        except Exception:
            pass

    resumed = bool(session_id)
    find = None
    if _has_session_flag(passthrough):
        session_id = ""                    # el socio eligió sesión a mano
    elif tab and not session_id:
        find = {"t0": time.time(), "before": sorted(list_chats(brain)),
                "marker": session_marker(cfg, tab[1])}

    # inject_context (contrato §3): identidad + bloque de la PESTAÑA ACTIVA,
    # INVISIBLE (project doc). Solo si ni el anexo a un AGENTS.md del socio se
    # pudo escribir, la memoria cae al primer mensaje (visible — último recurso).
    first_prompt = ""
    inj = inject_context(cfg, session_context=session_blk)
    if not inj.get("ok") and inj.get("detail"):
        print("WORKSPACE: identidad NO inyectada (%s) — Cursor arrancará "
              "genérico." % inj["detail"])
    if tab and session_blk and inj.get("action") == "custom" \
            and not inj.get("session") and not resumed:
        try:
            import sessions_registry as _reg
            first_prompt = _reg.first_prompt_context(brain, tab[1], engine="cursor")
            if os.name == "nt":       # viaja como argumento por el lanzador .cmd
                import memoria
                first_prompt = memoria.argv_seguro(first_prompt)
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
    # Lo que la herramienta de memoria restauró o no pudo tocar en el cerebro
    # (config de proyecto): una línea cada uno, DESPUÉS del banner (que limpia
    # la pantalla).
    try:
        import memoria_mcp
        for aviso in memoria_mcp.avisos():
            print(aviso)
    except Exception:
        pass

    argv = _interactive_argv(cfg, passthrough, session_id=session_id)
    # ¿La marca de confianza la deja ESTE --trust (no uno del socio)? Se anota
    # al cerrar para que el desinstalador quite solo las de Workspace.
    confiaba = True
    if brain and "--trust" in argv and "--trust" not in [str(a) for a in passthrough or ()]:
        confiaba = trusted(brain)
    # Arranque del cerebro como codex/opencode: un launch PELADO de una sesión
    # NUEVA arranca solo con el mensaje inicial (argumento posicional del CLI:
    # «Initial prompt for the agent»); al retomar no se inyecta nada. A-VERIFICAR
    # con cuenta que el TUI lo ENVÍA (y no solo lo precarga).
    boot = first_prompt or ("" if (passthrough or resumed) else
                            "Lee %s e inicia el cerebro. Al terminar, confirma "
                            "en una línea breve." % _identity_doc(cfg))
    if boot and os.name == "nt":
        import memoria
        boot = memoria.argv_seguro(boot)
    if boot and find:
        boot += " (%s)" % find["marker"]
    if boot and not (argv and argv[0] in _SUBCOMMANDS):
        argv = argv + ["--", boot]

    # La captura al cierre (session_continuity.capture_cursor) respalda ESTE
    # chat: necesita su id real. `--continue` no lo dice → captura «missing».
    real_sid = session_id or _session_from_passthrough(passthrough)
    if real_sid:
        os.environ["WORKSPACE_CURSOR_SESSION"] = real_sid
    else:
        os.environ.pop("WORKSPACE_CURSOR_SESSION", None)
    if find:
        os.environ["WORKSPACE_CURSOR_FIND"] = json.dumps(find)
    else:
        os.environ.pop("WORKSPACE_CURSOR_FIND", None)

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

    # La barra de Workspace en la statusLine nativa de Cursor (la del socio
    # gana; falla-suave: jamás tumba el arranque).
    try:
        import motor_statusline
        motor_statusline.ensure_statusline("cursor")
    except Exception:
        pass

    # Windows: sin Git Bash a la vista, Cursor corre sus hooks con PowerShell
    # (sin_git_bash). Aquí mismo, como dispatch con la bóveda: este proceso
    # solo abre Cursor y el wrapper copia este entorno.
    sin_git_bash(os.environ)

    try:
        import interactive
        rc = interactive.run_official_cli_interactive(
            "cursor", brain=brain or None, argv=argv, context_sink=_ctx_sink,
            pending={"tab": tab[1] if tab else "", "agent": agent, "resume_id": session_id})
    except Exception as e:
        print("WORKSPACE: no pude lanzar Cursor interactivo (%s: %s)"
              % (type(e).__name__, e))
        sys.exit(1)
    if not confiaba and trusted(brain):
        anotar_confianza(brain)
    # La captura encontró el chat de esta pestaña → se ata, y al reabrir la
    # pestaña se retoma con `--resume <id>`.
    found = os.environ.get("WORKSPACE_CURSOR_SESSION", "")
    if find and tab and valid_chat_id(found):
        try:
            import sessions_registry as _reg
            if not _reg.owner(brain, "cursor", found, exclude=tab[1]):
                _reg.bind(brain, agent, tab[1], "cursor", found)
        except Exception:
            pass
    # Limpieza: el bloque de la pestaña era de ESTA corrida → se restaura el
    # puntero base (o se quita el anexo del doc del socio). AGENTS.md es UNO
    # por cerebro: si otra pestaña sigue viva en él (de cualquier motor), el
    # bloque es el suyo y no se toca; lo limpia la última que cierre.
    try:
        import pending_runs
        otra = bool(brain) and pending_runs.live_in_brain(brain, exclude=pending_runs.current())
    except Exception:
        otra = False
    if (session_blk or _doc_dirty) and not otra:
        try:
            inject_context(cfg)
        except Exception:
            pass
    if not otra and brain:
        try:
            import pending_runs
            pending_runs.clean_docs("cursor", brain)
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
        cfg.setdefault("_engine", "cursor")
        return _ui.pick_keep_label(cfg, "Cursor · modelo de tu cuenta")
    except Exception:
        return ""
