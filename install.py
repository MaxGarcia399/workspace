#!/usr/bin/env python3
# ════════════════════════════════════════════════════════════════════════════
#  WORKSPACE — instalador per-máquina del harness.
#  Cada socio lo corre UNA vez:   python3 install.py [--socio <nombre>] [--dry-run]
#  Deja listos:
#    · `workspace`  → puerta del harness (banner + menú de agentes)
#    · un comando por agente (`zenith`, …) → abre ese agente directo
#    · hooks por cerebro: contexto al entrar (SessionStart) + captura al cerrar
#      (SessionEnd, red de seguridad de WORKSPACE) + marcador de inicio
#    · permisos según la autonomía del agente (libre dentro de su cerebro),
#      status line, tema
#  Los scripts viven en los vaults sincronizados (WORKSPACE + cerebros); aquí solo
#  se escribe lo específico de la máquina. Mac y Windows. Cero dependencias.
# ════════════════════════════════════════════════════════════════════════════
import os, re, sys, json, shlex, platform, shutil, stat
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)

WORKSPACE = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)
import events   # noqa: E402  (contrato de eventos N9 — build_hooks deriva de él)
import pathguard  # noqa: E402  (P0-4 — detección de rutas redirigidas a OneDrive)
import legacy  # noqa: E402  (literales de la instalación anterior — solo para reconocerla)
HOME = os.path.expanduser("~")
_REAL_HOME = HOME   # snapshot AL IMPORTAR: los tests parchan HOME, no esto
PY = sys.executable or ("python" if platform.system() == "Windows" else "python3")
IS_WIN = platform.system() == "Windows"
if IS_WIN:
    os.system("")  # habilita ANSI en Windows 10+ (no-op en consolas viejas) — igual que doctor.py
import _utf8; _utf8.harden()  # B2 · UTF-8 antes de imprimir el `✓` (cp1252 reventaría)


def _store_versioned(p):
    """True si `p` es el python VERSIONADO de la Microsoft Store
    (...\\WindowsApps\\PythonSoftwareFoundation.Python.3.13_...\\python.exe).
    Ese path muere con cada bump/reinstall de la Store — nunca hornearlo."""
    low = (p or "").lower()
    return "windowsapps" in low and "pythonsoftwarefoundation.python" in low


def win_python():
    """SOLO Windows: el intérprete más ESTABLE para hornear en launchers/hooks/
    statusLine. sys.executable bajo la Store es versionado y se rompe al
    actualizar Python; el alias %LOCALAPPDATA%\\Microsoft\\WindowsApps\\python.exe
    sobrevive los bumps. Instalaciones de python.org ya son estables → se quedan.
    Mac/Linux no pasan por aquí (siguen con sys.executable, igual que siempre)."""
    exe = sys.executable or "python"
    if not IS_WIN:
        return exe
    # Desde un entorno virtual (p. ej. el de una prueba en una carpeta temporal)
    # se hornea el intérprete BASE: el venv puede desaparecer y llevarse los
    # comandos del socio con él (2026-10-17).
    base = getattr(sys, "_base_executable", "") or ""
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix) and base and os.path.isfile(base):
        exe = base
    if _store_versioned(exe):
        alias = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                             "Microsoft", "WindowsApps", "python.exe")
        if os.environ.get("LOCALAPPDATA") and os.path.exists(alias):
            return alias
    return exe


if IS_WIN:
    PY = win_python()   # Windows: hornear el path ESTABLE (Mac/Linux: PY queda igual)
DRY = "--dry-run" in sys.argv
C, R, B, DIM = "\033[38;5;51m", "\033[0m", "\033[1m", "\033[38;5;67m"
try:    # acento/tenue del TEMA del hub (el mismo de cada pantalla); sin tema, los de arriba
    import tuitheme as _tuitheme
    _TP = _tuitheme.palette()
    C, R, B, DIM = _TP.C, _TP.R, _TP.BO, _TP.DIM
except Exception:
    pass

# ── permisos de Claude Code según la AUTONOMÍA del agente ────────────────────
# agent.json → "autonomy" (contrato común de los motores):
#   brain (default) — lee, crea y edita DENTRO de su cerebro sin preguntar; la
#     terminal, los archivos de fuera y la red piden permiso. En Claude Code:
#     reglas Read/Edit con la ruta ABSOLUTA del cerebro (`//<ruta>/**`) y SIN
#     defaultMode. (Edit cubre crear archivos; Claude Code ignora las reglas
#     con ruta de Write/Glob/Grep, por eso solo Read y Edit.)
#   ask — el usuario apagó el acceso automático (Agentes → Enter): sin reglas de
#     WORKSPACE; Claude Code pregunta antes de crear o editar, también en el
#     cerebro (leer dentro de la carpeta de trabajo nunca pide permiso).
# «Comandos sin preguntar» (antes "full": la lista amplia + dontAsk) YA NO
# EXISTE (decisión del dueño 2026-10-14): un "full" se lee como "brain" y la
# migración 202610141400_brain_permissions lo convierte al actualizar. La
# versión con full quedó en la rama feat/autonomia-completa.
AUTONOMY_LEVELS = ("ask", "brain")
DEFAULT_AUTONOMY = "brain"
ALLOW_FULL = ["Bash", "BashOutput", "KillShell", "Read", "Write", "Edit", "NotebookEdit",
              "Glob", "Grep", "WebFetch", "WebSearch", "Task", "TodoWrite", "Skill",
              "SlashCommand"]
# Lo que el instalador escribía hasta 0.2.x en TODO cerebro (incluía un MCP que
# no era del usuario). Solo sirve para reconocerlo (la migración lo quita) y
# para no arrastrarlo como «regla del usuario» al cambiar de autonomía.
LEGACY_ALLOW = ALLOW_FULL + ["mcp__claude_ai_Shopify"]
#: marcador (clave que Claude Code ignora) con lo que WORKSPACE escribió en
#: `permissions`: así un cambio de autonomía quita lo nuestro y conserva lo tuyo.
_PERM_MARKER = "__workspacePermissions"


def autonomy_of(cfg):
    """La autonomía declarada por el agente; cualquier otra cosa → 'brain'
    (el valor seguro)."""
    v = str((cfg or {}).get("autonomy") or "").strip().lower()
    return v if v in AUTONOMY_LEVELS else DEFAULT_AUTONOMY


def _rule_root(path, windows=None):
    """Ruta ABSOLUTA en la sintaxis de reglas de Claude Code: `//` + ruta POSIX
    (funciona con espacios). Windows: D:\\Cerebros\\Mi → //d/Cerebros/Mi (Claude Code
    normaliza las rutas de Windows a esa forma antes de comparar)."""
    windows = IS_WIN if windows is None else windows
    if windows:
        import ntpath
        p = ntpath.normpath(path)
        drive, rest = ntpath.splitdrive(p)
        rest = rest.replace("\\", "/").rstrip("/")
        if len(drive) == 2 and drive[1] == ":":
            return "//" + drive[0].lower() + rest
        return "//" + rest.lstrip("/")
    import posixpath
    p = posixpath.normpath(path if posixpath.isabs(path) else os.path.abspath(path))
    return "/" + p.rstrip("/")


def brain_rules(brain, windows=None):
    """Reglas Read/Edit que dejan al agente trabajar en SU cerebro. Si la ruta
    pasa por un enlace (p. ej. /tmp → /private/tmp), también la real."""
    roots = []
    cands = [brain] if windows else [os.path.abspath(brain), os.path.realpath(brain)]
    for p in cands:
        r = _rule_root(p, windows)
        if r not in roots:
            roots.append(r)
    out = []
    for r in roots:
        out += ["Read(%s/**)" % r, "Edit(%s/**)" % r]
    return out


def claude_permissions(autonomy, brain):
    """El bloque `permissions` que WORKSPACE quiere para esa autonomía."""
    if autonomy == "ask":
        return {"allow": []}
    return {"allow": brain_rules(brain)}


def render_permissions(settings, cfg, brain):
    """Escribe en `settings` (dict de settings.local.json) los permisos de la
    autonomía del agente. Conserva lo que el usuario agregó: reglas propias en
    allow, deny/ask/additionalDirectories y un defaultMode que no sea el
    nuestro. Lo que WORKSPACE escribió antes (marcador, o la lista amplia de
    0.2.x si no hay marcador) se reemplaza. Devuelve `settings`."""
    autonomy = autonomy_of(cfg)
    want = claude_permissions(autonomy, brain)
    cur = settings.get("permissions")
    cur = cur if isinstance(cur, dict) else {}
    prev = settings.get(_PERM_MARKER)
    ours = set(prev.get("allow") or []) if isinstance(prev, dict) else set(LEGACY_ALLOW)
    extra = [r for r in (cur.get("allow") or [])
             if isinstance(r, str) and r not in ours and r not in want["allow"]]
    new = {k: v for k, v in cur.items() if k not in ("allow", "defaultMode")}
    mode = cur.get("defaultMode")
    if "defaultMode" in want:
        new["defaultMode"] = want["defaultMode"]
    elif mode and mode != "dontAsk":        # un modo elegido por ti se respeta
        new["defaultMode"] = mode
    new["allow"] = list(want["allow"]) + extra
    settings["permissions"] = new
    settings[_PERM_MARKER] = {"autonomy": autonomy, "allow": list(want["allow"])}
    return settings


def apply_permissions(brain, cfg):
    """Reescribe SOLO el bloque `permissions` del settings.local.json del
    cerebro según `cfg["autonomy"]` (lo usa Agentes → Enter al cambiar los
    permisos). Lectura-modificación-escritura atómica: hooks, tema y lo que
    agregó el usuario quedan intactos. Un settings corrupto NO se toca.
    Devuelve (ok, motivo)."""
    spath = os.path.join(brain, ".claude", "settings.local.json")
    if json_corrupt(spath):
        return False, "settings.local.json corrupto"
    settings = read_json(spath) if os.path.exists(spath) else {}
    if not isinstance(settings, dict):
        return False, "settings.local.json no es un objeto"
    render_permissions(settings, cfg, brain)
    try:
        os.makedirs(os.path.dirname(spath), exist_ok=True)
        tmp = "%s.tmp-%d" % (spath, os.getpid())
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, spath)
    except OSError as e:
        return False, str(e)
    return True, ""


def say(m): print(f"  {m}")
def ok(m): print(f"  {C}✓{R} {m}")
def dry(m): print(f"  {DIM}[dry-run] {m}{R}")


def read_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def json_corrupt(p):
    """True si `p` EXISTE pero no parsea como JSON (≠ 'no existe'). R3-F1:
    read_json colapsa ambos casos a {} — quien va a REESCRIBIR un settings
    debe distinguirlos para no descartar un archivo corrupto en silencio
    (dejar rastro / abortar la reparación destructiva)."""
    if not os.path.exists(p):
        return False
    try:
        json.load(open(p, encoding="utf-8"))
        return False
    except Exception:
        return True


def registry():
    return read_json(os.path.join(WORKSPACE, "agents", "registry.json"))


def agent_cfg(d):
    return read_json(os.path.join(WORKSPACE, "agents", d, "agent.json"))


def paths_local():
    # per-máquina, FUERA del vault (no se sincroniza).
    return os.path.join(_paths.state_dir(HOME), "paths.local.json")


def _obsidian_json():
    cands = []
    if IS_WIN:
        cands.append(os.path.join(os.environ.get("APPDATA", ""), "obsidian", "obsidian.json"))
    cands += [os.path.join(HOME, "Library", "Application Support", "obsidian", "obsidian.json"),
              os.path.join(HOME, ".config", "obsidian", "obsidian.json")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def obsidian_vaults():
    p = _obsidian_json()
    d = read_json(p) if p else {}
    return [v.get("path") for v in (d.get("vaults", {}) or {}).values() if v.get("path")]


def find_brain(name, cfg, ask=True):
    """Devuelve (ruta, persistir). persistir=True → guardar en paths.local.json.
    Solo pregunta la ruta como último recurso si `ask` y hay una terminal de
    verdad: sin TTY (pipe, CI, el doctor de `workspace update`) nunca espera."""
    # Resolución declarada: el resolver CANÓNICO (Z20), el mismo del launcher —
    # override por máquina > registro por máquina > def committeada (rel. ROOT).
    import brain_resolver
    res = brain_resolver.resolve(name, cfg, root=WORKSPACE)
    if res.get("exists"):
        return res.path, False
    raw = cfg.get("brain", "")
    target = os.path.basename(os.path.normpath(raw)) if raw else ""
    if target:
        for vp in obsidian_vaults():                 # registro de Obsidian (lo más fiable)
            if os.path.basename(os.path.normpath(vp)) == target and os.path.isdir(vp):
                return os.path.abspath(vp), True
        for r in (os.path.dirname(WORKSPACE), HOME, os.path.join(HOME, "Desktop"),
                  os.path.join(HOME, "Documents"), os.path.join(HOME, "Documents", "Obsidian"),
                  os.path.join(HOME, "Obsidian")):    # spots comunes
            cand = os.path.join(r, target)
            if os.path.isdir(cand):
                return os.path.abspath(cand), True
    if not ask or not _stdin_tty():
        return "", False
    try:                                             # último recurso: preguntar
        ans = os.path.expanduser(input(f"  Pega la ruta de la carpeta '{target or name}': ").strip())
    except (EOFError, KeyboardInterrupt):
        ans = ""
    if ans and os.path.isdir(ans):
        return os.path.abspath(ans), True
    return "", False


def _stdin_tty():
    try:
        return bool(sys.stdin) and sys.stdin.isatty()
    except Exception:
        return False


def _within(path, *roots):
    """¿`path` (resuelto) está CONTENIDO en alguno de `roots`? Defensa de
    seguridad: los scripts de un agent.json se hornean como hooks/statusLine; un
    cerebro malicioso NO debe poder apuntar a un script fuera de su cerebro o del
    harness. SSOT: delega en dispatch._within (antes era una copia idéntica que
    podía driftar de la del runtime → instalador y dispatch aceptando conjuntos
    distintos de scripts). FALLA-CERRADO: si dispatch no importa, rechaza (nunca
    se hornea un script sin verificar su contención)."""
    try:
        import dispatch
        return dispatch._within(path, *roots)
    except Exception:
        return False


def expand(scripts, brain):
    # {brain} = cerebro del agente · {root} = raíz de WORKSPACE (los scripts de UI
    # viven aquí desde la migración brand→WORKSPACE). Espejo de dispatch.expand_scripts.
    # SEC: descarta cualquier script que resuelva FUERA del cerebro o del harness
    # (no se hornea como hook) — evita ejecución de código por un agent.json malicioso.
    out = {}
    for k, v in (scripts or {}).items():
        p = os.path.normpath(v.replace("{brain}", brain).replace("{root}", WORKSPACE))
        if _within(p, brain, WORKSPACE):
            out[k] = p
        else:
            say(f"{DIM}aviso seguridad: script '{k}' fuera del cerebro/harness — ignorado: {p}{R}")
    return out


# Socio/dueño (.claude/socio.local): Workspace es de UNA persona por máquina —
# el instalador ya no pregunta "¿quién eres?". Solo se escribe si se pasa
# EXPLÍCITO `--socio <slug>` (cualquier slug válido; útil para quien firma sus
# journals de sesión con un nombre). Sin el flag: nada que preguntar ni escribir.
SOCIO_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def ask_socio():
    """El slug de `--socio <slug>` / `--socio=<slug>`, o "" si no se pasó (o no
    es válido). JAMÁS pregunta ni adivina (ni por posición ni por $USER)."""
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a.startswith("--socio="):
            v = a.split("=", 1)[1].lower()
            if SOCIO_RE.match(v):
                return v
        if a == "--socio" and i + 1 < len(args) and SOCIO_RE.match(args[i + 1].lower()):
            return args[i + 1].lower()
    return ""


def machine_socio_path():
    """socio.local PER-MÁQUINA (~/.claude/workspace/socio.local) — identidad
    del chat cuando NO hay cerebro activo (la TUI se abre desde el menú
    `workspace` con cwd=$HOME, antes de elegir agente). chat.self_ids cae aquí
    tras el socio.local del cerebro activo y el del cerebro de equipo."""
    return os.path.join(_paths.state_dir(HOME), "socio.local")


def write_machine_socio(socio):
    """Escribe la identidad per-máquina (cualquier slug válido — soporta dueños
    externos, no solo el trío). El doctor la repara con la misma función.
    Respeta --dry-run vía write_text."""
    if socio and SOCIO_RE.match(socio):
        write_text(machine_socio_path(), socio)


#: El socio genérico que se pone cuando nadie dijo uno («Crear agente» sin
#: dueño, o «Cargar» un cerebro sin ningún dato). Sin ninguna sesión es un
#: marcador, no un dueño: un socio declarado lo reemplaza — así se reparan los
#: cerebros que el bug de agentes-N2 dejó en «owner».
GENERIC_SOCIO = "owner"


def socio_has_sessions(brain, socio):
    """True si `STATE/sessions/<socio>/` tiene alguna sesión (un .md que no
    sea README.md)."""
    d = os.path.join(brain, "STATE", "sessions", socio)
    try:
        return any(n.endswith(".md") and n != "README.md"
                   and os.path.isfile(os.path.join(d, n)) for n in os.listdir(d))
    except OSError:
        return False


def brain_socio(brain):
    """El socio que el cerebro YA declara (`.claude/socio.local`, sin espacios).
    '' si no declara ninguno: no existe, está vacío o es el «owner» genérico sin
    ninguna sesión (marcador reemplazable). None si existe pero no se puede
    leer — ante la duda, tampoco se pisa (agentes-N2)."""
    p = os.path.join(brain, ".claude", "socio.local")
    if not os.path.lexists(p):
        return ""
    try:
        with open(p, encoding="utf-8") as fh:
            s = fh.read().strip()
    except Exception:
        return None
    if s == GENERIC_SOCIO and not socio_has_sessions(brain, s):
        return ""
    return s


def socio_remedy_cmd():
    """El comando EXACTO para decirle a esta máquina quién eres: este Python y
    este install.py con rutas completas (sirve desde cualquier carpeta). En
    Windows lleva `& ` delante: PowerShell no ejecuta una ruta entre comillas
    sin él. Solo llena el socio de los cerebros que no tienen uno."""
    cmd = '"%s" "%s" --socio TU-NOMBRE' % (PY, os.path.join(WORKSPACE, "install.py"))
    return ("& " + cmd) if IS_WIN else cmd


# ── escritura (respeta --dry-run) ──
def write_text(path, content):
    """Escritura ATÓMICA: tmp en el MISMO dir + os.replace (R3-F1). El viejo
    `open(path, "w")` truncaba primero — un crash/disco-lleno a media escritura
    de settings(.local).json dejaba JSON truncado que la siguiente pasada leía
    como {} y 'reparaba' descartando permissions/env/mcpServers en silencio.
    Mismo patrón que agent_admin._atomic_write_json / usage / settings."""
    if DRY:
        dry(f"escribiría {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_json(path, obj):
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


def _gitignore_state(brain, lines):
    """(ruta, contenido actual, líneas que faltan). Un .gitignore ilegible
    LANZA (UnicodeDecodeError/OSError): quien llama decide, nunca se pisa."""
    gi = os.path.join(brain, ".gitignore")
    cur = open(gi, encoding="utf-8").read() if os.path.exists(gi) else ""
    return gi, cur, [ln for ln in lines if ln not in cur]


def gitignore_missing(brain, lines):
    """Líneas de `lines` que el .gitignore del cerebro aún no trae (la misma
    regla que aplica ensure_gitignore; la usa la migración de cerebros)."""
    return _gitignore_state(brain, lines)[2]


def ensure_gitignore(brain, lines):
    gi, cur, add = _gitignore_state(brain, lines)
    if not add or DRY:
        if add:
            dry(f"agregaría a {gi}: {', '.join(add)}")
        return
    # mismo fin de línea que el archivo (en Windows el modo texto metía CRLF en
    # un .gitignore LF que viaja por sync a Mac); uno nuevo, LF
    try:
        with open(gi, "rb") as fh:
            eol = "\r\n" if b"\r\n" in fh.read() else "\n"
    except OSError:
        eol = "\n"
    with open(gi, "a", encoding="utf-8", newline="") as f:
        if cur and not cur.endswith("\n"):
            f.write(eol)
        f.write(eol.join(add) + eol)


# ── bloque `hooks` de un cerebro (lo comparte el doctor: escribe SOLO esto) ──
def hook_cmd(*parts):
    return " ".join(f'"{p}"' if (" " in p or "/" in p or "\\" in p) else p for p in parts)


# ── runner shell-agnóstico (P0-1) ──
# RUNNER = el único entrypoint de hooks. Cada hook nativo se cabla a UNA
# invocación de ejecutable (`"PY" "RUNNER" <evento>`), sin control-flow de shell
# → parsea idéntico en cmd.exe, git-bash, PowerShell o sh. Reemplaza al viejo
# soft_hook_cmd (que elegía sintaxis por OS — `if exist`/`test -f` — y tronaba
# cuando el shell de hooks de Windows no era el asumido). Existencia del script,
# falla-suave, gate `requires`, fan-out y merge de stdout viven AHORA en el
# runner (workspace_hook.py), en Python.
RUNNER = os.path.join(WORKSPACE, "workspace_hook.py")
_DASHBOARD_TIMEOUT = 10   # cota del `--context` del dashboard (lo corre el runner)
_DEFAULT_TIMEOUT = 10     # cota por listener si el contrato no declara `timeout`


def runner_cmd(event):
    """Comando shell-agnóstico del hook nativo que dispara `event`:
        "<PY>" "<WORKSPACE>/workspace_hook.py" <event>
    Una sola invocación de ejecutable, cero metacaracteres de shell. El token del
    evento WORKSPACE va al final (sin comillas) — es lo que el runner recibe en
    argv[1] y por lo que el doctor detecta el wiring. El path del brain NO se
    hornea (el runner lo resuelve en runtime)."""
    return hook_cmd(PY, RUNNER, event)


GITIGNORE_LINES = [".claude/settings.local.json", ".claude/socio.local",
                   ".claude/zenith-workspaces.json",
                   # N12: el sidecar .usage.json SÍ se versiona (conteo de
                   # equipo); su lock N8 es estado per-máquina → fuera de git
                   "skills/**/.usage.json.lock*",
                   # revisión de skills (2026-10-16): la vista de la sesión
                   # que el agente revisa al abrir — per-máquina, fuera de git
                   ".claude/skill-review/",
                   # memoria v1: candados y bandeja de notas — per-máquina
                   ".claude/locks/", ".claude/memoria-entrada/"]


def build_hooks(cfg, brain):
    """Construye el bloque `hooks` de settings.local.json para un cerebro,
    DERIVADO del contrato de eventos (N9 · events.py / engines/EVENTS.md).

    P0-1 (shell-agnóstico): cada (evento WORKSPACE, matcher) se cabla a UNA
    invocación del runner `runner_cmd(ev)`. El runner hace el fan-out a TODOS
    los `listeners_for(ev)` y el merge de stdout aditivo — settings.json ya no
    nombra scripts ni hornea el path del brain. El matcher se conserva en la
    ESTRUCTURA de settings.json (lo necesita Claude Code para filtrar por tool).

    Gate `requires` (Tema D, mismo que doctor): build_hooks decide QUÉ eventos
    cablear (si un evento se queda sin listener activo y sin dashboard, no se
    cabla); el runner REAPLICA el gate en runtime (self-healing de settings
    viejos). El dashboard de session_start lo inyecta el runner, no un comando
    aparte. Separado de configure_brain para que `workspace doctor` repare SOLO
    los hooks sin tocar permissions/theme."""
    setup = events.setup_of(cfg)
    has_dashboard = bool(expand(cfg.get("scripts"), brain).get("dashboard"))
    out = {}
    for ev in events.wired_events("claude-code"):
        native = events.native_event(ev)
        active = [l for l in events.listeners_for(ev) if not events.gated(l, setup)]
        # session_start se cabla también si el agente declara dashboard, aunque
        # su listener (session_start.py) esté gated por setup ligero — el runner
        # inyecta el --context del dashboard de todos modos.
        dash_here = ev == "session_start" and has_dashboard
        if not active and not dash_here:
            continue            # nada que correr en este evento → no cablear
        # cota del hook nativo: el runner corre los hijos en SECUENCIA, así que
        # debe cubrir la SUMA de sus timeouts (+ dashboard en session_start) — si
        # no, Claude Code mataría al runner a media tanda.
        budget = sum(int(l.get("timeout") or _DEFAULT_TIMEOUT) for l in active)
        if dash_here:
            budget += _DASHBOARD_TIMEOUT
        budget += 5             # buffer de arranque del intérprete
        # un grupo por matcher DISTINTO del evento (los listeners de un mismo
        # evento WORKSPACE comparten matcher; el comando es el mismo runner_cmd(ev)).
        matchers = []
        for l in active:
            m = l.get("matcher")
            if m not in matchers:
                matchers.append(m)
        if dash_here and None not in matchers:
            matchers.append(None)   # session_start (dashboard) va sin matcher
        for m in matchers:
            group = {"hooks": [{"type": "command",
                                "command": runner_cmd(ev),
                                "timeout": budget}]}
            if m:
                group = {"matcher": m, "hooks": group["hooks"]}
            out.setdefault(native, []).append(group)
    return out


# ── render del bloque `hooks` (FUENTE ÚNICA · P0-3) ──
def render_hooks_only(cfg, brain, settings=None):
    """RMW idempotente del bloque `hooks` de un cerebro — la ÚNICA fuente del
    cableado, compartida por install.configure_brain, doctor.phase_hooks y el
    verbo `workspace repair`. Los tres derivan el wiring del MISMO build_hooks
    (contrato de eventos N9) sin duplicar el read-modify-write.

    Gestiona SOLO `hooks`; el resto del archivo se PRESERVA (permissions, theme,
    env, mcpServers, statusLine… intactos — RMW, no rebuild). Cierra el hueco
    P0-3: un `git pull`/branch-switch que renombra un hook o suma un listener en
    events.py deja settings.local.json stale y hoy NADA lo re-renderiza; esta
    función es lo que repair y el auto-render-on-pull vuelven a correr para
    recablear cada cerebro.

    statusLine queda FUERA a propósito: su condición de reescritura difiere por
    caller (install lo hornea siempre; doctor solo si la ruta/intérprete
    envejecieron; repair no lo toca) — el bloque que de verdad se duplica y
    deriva en stale tras un pull es `hooks`, y ese es el objetivo DRY de P0-3.

    · settings None  → lee settings.local.json del cerebro, lo muta y lo ESCRIBE
      (lo usan repair y cualquier uso por-archivo).
    · settings dict  → lo muta y lo devuelve SIN escribir (lo usa configure_brain,
      que añade sus propias claves y hace un único write al final).
    Devuelve el dict settings resultante."""
    write = settings is None
    spath = os.path.join(brain, ".claude", "settings.local.json")
    if write:
        settings = read_json(spath) if os.path.exists(spath) else {}
        if not isinstance(settings, dict):
            settings = {}
    settings["hooks"] = build_hooks(cfg, brain)                 # gestionado (derivado de N9)
    if write:
        # guard anti-envenenamiento: el runner_cmd hornea la ruta de ESTE
        # checkout — desde un worktree NO se persiste (el cerebro conserva sus
        # hooks canónicos); el dict mutado se devuelve igual para inspección.
        if global_writes_blocked("hooks de cerebros"):
            return settings
        write_json(spath, settings)
    return settings


# ── materialización de MCPs (FUENTE ÚNICA · dispatch por motor) ──────────────
# El store gestionado (config_engine/mcps.json) declara los MCP una sola vez,
# motor-agnóstico. Aquí se PROYECTAN al canal nativo del motor de cada agente.
# Principio rector (el socio): el sistema nace ABIERTO — la materialización es un
# DISPATCH POR TIPO DE CONEXIÓN (connectors.PORTABILITY), no una función
# claude-only. claude-code es el PRIMER canal real; codex/gemini y local/API
# son asientos que SALTAN con razón visible (no fingen que enchufaron).

#: nombres de MCP que WORKSPACE materializó (clave namespaced en
#: settings.local.json). Es el "set derivado del store" que permite REMOVER un
#: server que salió del store sin tocar los MCP que el socio metió a mano.
#: claude-code ignora claves desconocidas ⇒ amputable (C10): borra este código
#: y el archivo sigue válido (solo queda un marcador inerte que nadie lee).
_MCP_MARKER = "__workspaceMcps"


def _mcp_projection(cfg):
    """(channel, connection_type, reason) para el motor del agente `cfg`.

    channel != "" ⇒ hay proyector REAL (hoy solo 'claude-code'). channel == ""
    ⇒ se SALTA y `reason` explica por qué (visible — jamás se finge el enchufe).
    El dispatch se resuelve por connectors.PORTABILITY / OFFICIAL_CLIS, no por
    un hardcode de claude-code (el seam para codex/gemini/local queda abierto)."""
    engine = (cfg.get("engine") or "claude-code").strip()
    try:
        import connectors
    except Exception:
        # amputable: sin connectors solo conocemos el builtin claude-code
        if engine == "claude-code":
            return "claude-code", "official_cli", ""
        return "", "", "connectors no disponible — motor %r sin resolver" % engine
    info = connectors.OFFICIAL_CLIS.get(engine)
    if info is not None:                             # CLI oficial (tools = MCP)
        if engine == "claude-code":
            return "claude-code", "official_cli", ""
        return "", "official_cli", (
            "motor official_cli '%s': materialización MCP A-VERIFICAR "
            "(flags/config nativa del CLI aún sin confirmar contra el binario "
            "real) — no se materializa" % engine)
    # motor directo (provider openai_compatible / native_api) o desconocido
    ct = ""
    try:
        import model_resolver
        prov, _errs = model_resolver.load_provider(engine)
        if prov:
            ct = connectors.connection_type(prov)
    except Exception:
        ct = ""
    if ct in ("openai_compatible", "native_api"):
        return "", ct, (
            "motor '%s' (%s): sin canal de tools/MCP hasta que WORKSPACE sea "
            "dueño del loop + puente MCP (motor #2) — no se materializa"
            % (engine, ct))
    return "", ct, ("motor '%s' sin canal MCP conocido — no se materializa"
                    % engine)


def _mcps_for_agent(agent_name):
    """{name: entrada-del-store} de los MCP cuyo scope aplica a `agent_name`
    ('global' o el nombre en la lista). Común a TODOS los motores (el filtro de
    scope antecede al dispatch por canal). Falla-suave: sin config_engine → {}."""
    try:
        import config_engine
        servers = config_engine._load_mcps().get("servers", {})
    except Exception:
        return {}
    name = (agent_name or "").strip().lower()
    out = {}
    for sname, s in (servers or {}).items():
        scope = (s or {}).get("scope", "global")
        if scope == "global" or (isinstance(scope, (list, tuple))
                                 and name in scope):
            out[sname] = s
    return out


def _claude_mcp_entry(server):
    """Entrada de `mcpServers` en el shape de claude-code desde una entrada del
    store (`{cmd, scope, env}`).

    REGLA DE ORO: `env` sale de los NOMBRES → {"FOO": "${FOO}"}. El VALOR jamás
    se lee ni se escribe — claude-code expande `${FOO}` del env del proceso al
    lanzar el server. El materializador NUNCA toca os.environ[nombre]."""
    cmd = (server or {}).get("cmd")
    if isinstance(cmd, str):
        parts = shlex.split(cmd)
    elif isinstance(cmd, (list, tuple)):
        parts = [str(c) for c in cmd]
    else:
        parts = []
    entry = {"command": parts[0] if parts else "", "args": list(parts[1:])}
    env_names = (server or {}).get("env") or []
    if env_names:                                    # solo NOMBRES → ${NOMBRE}
        entry["env"] = {n: "${%s}" % n for n in env_names}
    return entry


def _project_mcps_claude_code(settings, desired):
    """Proyector CLAUDE-CODE (rama real de esta fase): muta
    `settings['mcpServers']` con los MCP gestionados `desired`
    ({name: entrada-del-store}).

    Reconciliación DESTRUCTIVA-SEGURA: remueve los que WORKSPACE materializó antes
    y ya no están en el store (vía `_MCP_MARKER`), pero RESPETA los MCP que el
    socio metió a mano (no llevan marcador). Idempotente byte-a-byte."""
    current = settings.get("mcpServers")
    if not isinstance(current, dict):
        current = {}
    prev = settings.get(_MCP_MARKER)
    prev = set(prev) if isinstance(prev, list) else set()
    # 1. remover los NUESTROS que salieron del store (los manuales no llevan
    #    marcador ⇒ jamás entran a `prev` ⇒ quedan intactos)
    for sname in prev:
        if sname not in desired and sname in current:
            del current[sname]
    # 2. upsert de los gestionados (el store gana sobre un homónimo previo)
    for sname, server in desired.items():
        current[sname] = _claude_mcp_entry(server)
    # 3. persistir el bloque + el marcador; limpio si vacío (amputable)
    if current:
        settings["mcpServers"] = current
    elif "mcpServers" in settings:
        del settings["mcpServers"]
    if desired:
        settings[_MCP_MARKER] = sorted(desired)
    elif _MCP_MARKER in settings:
        del settings[_MCP_MARKER]
    return settings


def render_mcps_only(cfg, brain, *, settings=None):
    """RMW idempotente del bloque `mcpServers` de un cerebro — espejo de
    render_hooks_only y FUENTE ÚNICA de la materialización de MCPs (la comparten
    doctor.phase_mcps y el CLI `workspace config mcp materialize`).

    Gestiona SOLO `mcpServers` (+ su marcador `_MCP_MARKER`); el resto del
    archivo se PRESERVA (permissions, hooks, statusLine, env, model y los MCP
    MANUALES del socio — RMW, no rebuild).

    DISPATCH POR MOTOR (no claude-only): resuelve el tipo de conexión del agente
    (`_mcp_projection`) y delega a un proyector por canal. claude-code = real;
    codex/gemini y local/API = asientos que SALTAN con razón visible (no tocan
    settings — honestidad por canal). El llamador NO asume `mcpServers` como
    único canal posible.

    · settings None → lee settings.local.json del cerebro, lo muta y lo ESCRIBE.
    · settings dict → lo muta y lo devuelve SIN escribir (el caller hace un
      único write al final).
    Devuelve el dict settings resultante."""
    write = settings is None
    spath = os.path.join(brain, ".claude", "settings.local.json")
    if write:
        settings = read_json(spath) if os.path.exists(spath) else {}
        if not isinstance(settings, dict):
            settings = {}
    channel, _ct, _reason = _mcp_projection(cfg)
    if channel == "claude-code":
        desired = _mcps_for_agent(cfg.get("name", ""))
        _project_mcps_claude_code(settings, desired)
    # else: canal sin proyector real → settings intacto (no se finge el enchufe)
    if write:
        # mismo guard anti-envenenamiento que los hooks: desde un worktree no se
        # persiste (el cerebro conserva su settings canónico)
        if global_writes_blocked("mcpServers de cerebros"):
            return settings
        write_json(spath, settings)
    return settings


# ── configurar el cerebro de un agente ──
def configure_brain(name, cfg, brain, socio, apply_autonomy=False):
    """Deja listo el settings.local.json del cerebro. `apply_autonomy=True`
    (el usuario ACABA de elegir la autonomía al crear/cargar) reescribe los
    permisos según `cfg["autonomy"]`; sin eso, los permisos solo se escriben
    si faltan (un re-install no pisa lo que ajustaste)."""
    # guard anti-envenenamiento: los hooks hornean rutas a ESTE checkout — desde
    # un worktree quedarían apuntando a un árbol temporal (ver global_writes_blocked)
    if global_writes_blocked(f"hooks/config del cerebro '{name}'"):
        return
    scripts = expand(cfg.get("scripts"), brain)
    statusline = scripts.get("statusline", "")

    # RMW (must-fix #4): NO reconstruir de cero. install.py es re-ejecutable
    # (cada agente, cada auto-update); pisar el dict destruía lo que el socio
    # agregó a mano (env, model, mcpServers, permisos custom). WORKSPACE GESTIONA
    # solo `hooks` (+ `statusLine`/`theme`); el resto se PRESERVA. Espejo de la
    # regla del doctor (que ya hace RMW y tiene PROHIBIDO pisar `permissions`).
    spath = os.path.join(brain, ".claude", "settings.local.json")
    # R3-F1 (read-guard): un settings CORRUPTO no se descarta en silencio —
    # se preserva como rastro (`.corrupt-<pid>`) y se avisa. El install es
    # acción explícita del socio y debe dejar un setup funcional, así que
    # sigue con un settings fresco; el rastro permite recuperar lo perdido.
    # (El doctor, que es reparación AUTOMÁTICA, directamente aborta — ver
    # doctor.phase_hooks.) Idempotencia intacta: un settings sano ni entra aquí.
    if json_corrupt(spath):
        rastro = spath + ".corrupt-%d" % os.getpid()
        if DRY:
            dry(f"respaldaría el settings corrupto en {rastro}")
        else:
            try:
                os.replace(spath, rastro)
            except OSError:
                rastro = "(no se pudo respaldar)"
        say(f"⚠ [{name}] settings.local.json era JSON corrupto — respaldado en "
            f"{rastro}; se genera uno nuevo (revisa el respaldo por config manual)")
    existing = read_json(spath) if os.path.exists(spath) else {}
    if not isinstance(existing, dict):
        existing = {}
    settings = dict(existing)
    render_hooks_only(cfg, brain, settings=settings)           # gestionado · fuente única (P0-3)
    settings.setdefault("spinnerTipsEnabled", False)
    settings.setdefault("companyAnnouncements", [])
    # permisos según la autonomía del agente: en el PRIMER install (si faltan)
    # o cuando el usuario la acaba de elegir (crear/cargar). En re-install NO
    # se pisan — el socio pudo ajustarlos (espejo de la regla dura del doctor).
    if apply_autonomy or not isinstance(settings.get("permissions"), dict):
        render_permissions(settings, cfg, brain)
    # Tema in-app POR-AGENTE (DEPLOY-1): cada agente usa SU tema, no uno
    # horneado para todos. Si no hay tema instalable, no forzamos ninguno →
    # Claude usa su default (sin fuga de marca de ningún agente).
    tname = install_theme(brain, cfg.get("theme") or name)
    if tname:
        settings["theme"] = f"custom:{tname}"
    if statusline:
        # --brain explícito: la statusline vive en WORKSPACE (ver build_hooks).
        settings["statusLine"] = {"type": "command",
                                  "command": hook_cmd(PY, statusline, "--brain", brain),
                                  "padding": 0, "refreshInterval": 60}

    write_json(spath, settings)
    ensure_gitignore(brain, GITIGNORE_LINES)
    # solo con --socio explícito (ver ask_socio). El socio que el cerebro YA
    # declara manda (agentes-N2): --socio fija el de la MÁQUINA y solo llena el
    # de cerebros sin uno — pisarlo escondía sus sesiones (p. ej. el agente de
    # otra persona). El mismo socio se reescribe igual que siempre (inocuo) y
    # el «owner» genérico sin sesiones se reemplaza (ver brain_socio).
    prev = brain_socio(brain) if socio else ""
    if socio and prev not in ("", socio):
        say(f"{DIM}[{name}] el cerebro ya tiene su propio socio — se respeta "
            f"(--socio solo fija el de esta máquina){R}")
    elif socio:
        write_text(os.path.join(brain, ".claude", "socio.local"), socio)
        # carpetas de sesión + migración
        for d in (os.path.join(brain, "STATE", "sessions", socio),
                  os.path.join(brain, "STATE", "sessions", "_migracion", socio, "_procesados")):
            if DRY:
                dry(f"crearía {d}")
            else:
                os.makedirs(d, exist_ok=True)

    # pestañas iniciales (si no existen). El archivo es per-agente: cada dashboard
    # lee .claude/<agente>-workspaces.json. Solo Zenith trae pestañas de fábrica;
    # los demás (Atlas, …) las crean desde su menú ("+ nueva").
    wf = os.path.join(brain, ".claude", f"{name}-workspaces.json")
    # Las pestañas iniciales las declara el PROPIO agente en su manifest
    # (`workspaces: [...]` en agent.json) — antes estaban horneadas en el instalador
    # con datos de cliente del equipo (DEPLOY-9). Así cada cerebro define las suyas y
    # el instalador queda genérico/vendible.
    seed_tabs = cfg.get("workspaces") if isinstance(cfg.get("workspaces"), list) else None
    if os.path.exists(wf):
        ok(f"[{name}] pestañas ya configuradas (se respetan)")
    elif seed_tabs:
        import uuid
        ws = [{"name": n, "id": str(uuid.uuid4())} for n in seed_tabs if isinstance(n, str)]
        write_json(wf, ws)
        ok(f"[{name}] pestañas iniciales sembradas ({len(ws)})")
    ok(f"[{name}] cerebro configurado: {brain}")


def install_theme(brain, name):
    """Instala el tema in-app de Claude Code del agente `name` en ~/.claude/themes/.
    Fuente (en orden): el tema POR-AGENTE del harness (themes-cc/<name>.json — viaja
    con el harness, llega a toda máquina sin tocar el cerebro), luego el del cerebro
    (assets/brand/<name>-theme.json), back-compat zenith. Devuelve el nombre instalado
    o '' si no hay tema → el caller NO fuerza ninguno (sin fuga de 'zenith'). DEPLOY-1."""
    cands = [os.path.join(_paths.state_dir(HOME), "themes-cc", f"{name}.json"),  # tus agentes
             os.path.join(WORKSPACE, "themes-cc", f"{name}.json"),
             os.path.join(brain, "assets", "brand", f"{name}-theme.json")]
    if name == "zenith":
        cands.append(os.path.join(brain, "assets", "brand", "zenith-theme.json"))
    src = next((c for c in cands if os.path.exists(c)), "")
    # El tema in-app sale del TEMA DEL HUB (el socio 2026-10-12: el tema y el
    # fondo del hub pintan todo); el themes-cc por agente queda de respaldo.
    content = None
    try:
        import theme_render as _tr
        _pal = _tr.hub_engine_palette()
        _data = _tr.engine_theme("claude-code", _pal, name.capitalize()) if _pal else None
        if _data is not None:
            content = _tr.json_text(_data)
    except Exception:
        content = None
    if not src and content is None:
        return ""
    dst = os.path.join(HOME, ".claude", "themes", f"{name}.json")
    if content is None:
        content = open(src, encoding="utf-8").read()
    # Lo HECHO A MANO GANA (theme_render): si editaste ~/.claude/themes/<name>.json
    # después de que lo instalamos, no se pisa. Un archivo sin registro (de una
    # versión anterior) se presume nuestro y se reescribe como siempre.
    try:
        import theme_render
    except Exception:                                # pragma: no cover
        theme_render = None
    if theme_render is not None and theme_render.is_handmade(dst, HOME):
        ok(f"tema '{name}' editado a mano — se conserva (~/.claude/themes/{name}.json)")
        return name
    # Lo AJENO no se pisa jamás: un tema TUYO que se llama igual que el agente
    # (no lo generamos ni es copia de una fuente nuestra) se queda como está y
    # el agente usa el tema por defecto de Claude.
    if (theme_render.is_foreign(dst, HOME, [content] + theme_render.legacy_sources(
            name, brain, HOME)) if theme_render is not None else os.path.lexists(dst)):
        say(f"⚠ ya hay un tema '{name}' en ~/.claude/themes que no es de WORKSPACE "
            f"— se conserva (el agente usa el tema por defecto)")
        return ""
    write_text(dst, content)
    if theme_render is not None and not DRY:
        theme_render.mark_generated([(dst, content)], HOME)
    ok(f"tema '{name}' instalado (~/.claude/themes/{name}.json)")
    return name


# ── retención de transcripts (aplica a TODA máquina) ──
# Claude Code borra los transcripts a los 30 días si no hay valor; son la
# materia prima de la memoria y del menú de sesiones. 365 días para todos: un
# año de sesiones sin crecer sin tope (es el ajuste GLOBAL de Claude Code del
# usuario). Antes se ponía 3650; la migración retention_365 lo baja.
CLEANUP_DAYS = 365
LEGACY_CLEANUP_DAYS = 3650      # lo que dejaba el instalador hasta 0.2.0


def ensure_cleanup_days():
    """~/.claude/settings.json → cleanupPeriodDays = 365 SOLO si no hay valor.
    Un valor existente (sea cual sea) es elección del usuario y no se toca.
    Merge sin pisar otras keys. Devuelve True si escribió algo."""
    sp = os.path.join(HOME, ".claude", "settings.json")
    # R3-F1 (read-guard): si el settings GLOBAL está corrupto, NO lo pisamos
    # con `{cleanupPeriodDays: …}` a secas — eso descartaría model/env/hooks
    # del socio en silencio. Se avisa y se salta (el doctor/socio lo arregla).
    if json_corrupt(sp):
        say(f"⚠ ~/.claude/settings.json es JSON corrupto — NO se toca "
            f"(cleanupPeriodDays pendiente; repara el archivo y re-corre)")
        return False
    s = read_json(sp) if os.path.exists(sp) else {}
    # SEC-05: registrar (una vez) el valor PREVIO para que `workspace uninstall` lo
    # revierta — no dejamos nuestra retención a perpetuidad tras desinstalar.
    pre_path = os.path.join(_paths.state_dir(HOME), "pre-install.json")
    if not DRY and not os.path.exists(pre_path):
        os.makedirs(os.path.dirname(pre_path), exist_ok=True)
        json.dump({"cleanupPeriodDays": s.get("cleanupPeriodDays")},
                  open(pre_path, "w", encoding="utf-8"))
    if s.get("cleanupPeriodDays") is not None:
        return False                     # valor propio del usuario: se respeta
    s["cleanupPeriodDays"] = CLEANUP_DAYS
    write_json(sp, s)
    ok(f"cleanupPeriodDays={CLEANUP_DAYS} en ~/.claude/settings.json "
       "(tus sesiones se conservan un año, no 30 días)")
    return True


# ── guard anti-envenenamiento (checkout canónico vs git worktree) ───────────
# Los shims de ~/.local/bin y los hooks de cerebros hornean RUTAS ABSOLUTAS a
# ESTE checkout. Si este código corre desde un git WORKTREE secundario (tests,
# agentes en árboles temporales, CI), esas rutas apuntan a un árbol que luego
# se borra → los shims REALES del socio quedan rotos (hub muerto). Regla dura:
# artefactos GLOBALES solo se escriben desde el checkout principal; desde un
# worktree se NIEGA y se avisa. Override explícito: WORKSPACE_FORCE_LAUNCHERS=1.
FORCE_ENV = "WORKSPACE_FORCE_LAUNCHERS"


def running_from_worktree(root=None):
    """True si `root` (default: este WORKSPACE) es un git worktree SECUNDARIO:
    ahí `.git` es un ARCHIVO (`gitdir: …`); en el checkout principal es un
    directorio, y en una copia dist (sin git) no existe. Equivale a
    `git rev-parse --git-dir` ≠ `--git-common-dir`, sin subprocess.
    Falla-suave: en duda → False (no bloquear una instalación legítima)."""
    try:
        return os.path.isfile(os.path.join(root or WORKSPACE, ".git"))
    except Exception:
        return False


def global_writes_blocked(what="launchers"):
    """Guard central de escritura GLOBAL (shims en ~/.local/bin, hooks de
    cerebros). True (+ warn a stderr) si corremos desde un worktree no-canónico
    y no hay override. Lo consultan install_launchers / configure_brain /
    render_hooks_only — mata la clase entera de envenenamiento (la suite de
    tests, agentes que corren desde su worktree, CI)."""
    if not running_from_worktree():
        return False
    if os.environ.get(FORCE_ENV) == "1":
        return False
    sys.stderr.write(
        f"  ⚠ WORKSPACE corre desde un git WORKTREE ({WORKSPACE}) — NO escribo {what} "
        f"globales: hornearían rutas a un árbol temporal y al borrarse dejarían el "
        f"hub muerto. Corre esto desde el checkout principal "
        f"(override consciente: {FORCE_ENV}=1).\n")
    return True


# ── launchers ──
#: Marca de los lanzadores de Workspace (2ª línea del script en ~/.local/bin).
#: Lo que NO la lleva es de otro programa y el instalador jamás lo reemplaza: un
#: agente llamado `claude` pisaba el symlink del instalador nativo de Claude Code
#: (y `hermes` el del motor). La de la instalación anterior también es nuestra.
LAUNCHER_MARK = "# WORKSPACE · comando"
_LAUNCHER_MARKS = (LAUNCHER_MARK, "# %s · comando" % legacy.NAME)
#: Los shims .cmd de Windows (win_cmd_shims) nunca llevaron marca: se reconocen
#: por su forma exacta — `@echo off` + python sobre front.py/dispatch.py.
_CMD_SHIM_RE = re.compile(r'@echo off\r?\n"[^"\r\n]+" "[^"\r\n]*[\\/](?:front|dispatch)\.py"'
                          r'[^\r\n]*%\*\s*\Z')
#: launcher_conflict(): el nombre es el comando del hub o el CLI de un motor.
RESERVED = "reservado"
#: launcher_conflict() en Windows: el nombre es un comando de PowerShell.
POWERSHELL = "powershell"
#: PowerShell da prioridad a una FUNCIÓN sobre sus cmdlets y sus funciones: la
#: `function <nombre>` de un agente taparía Get-Date o, peor, `prompt` (se llama
#: en cada renglón). shutil.which no los ve: no son archivos. Lista EXACTA de
#: los cmdlets y funciones que traen PowerShell 5.1 y 7 en sus módulos base
#: (sin consultar a PowerShell: sería lento). Un nombre que solo se PARECE
#: (test-bot, resume-coach) no está: no tapa nada y conserva su comando. Los
#: alias (ls, cd…) no cuentan: PowerShell los resuelve antes que una función.
_PS_COMMANDS = frozenset((
    # funciones de la sesión
    "clear-host get-verb help importsystemmodules mkdir more oss pause prompt "
    "psconsolehostreadline tabexpansion2 "
    # Microsoft.PowerShell.Core
    "add-history clear-history connect-pssession debug-job "
    "disable-experimentalfeature disable-psremoting disable-pssessionconfiguration "
    "disconnect-pssession enable-experimentalfeature enable-psremoting "
    "enable-pssessionconfiguration enter-pshostprocess enter-pssession "
    "exit-pshostprocess exit-pssession export-modulemember foreach-object "
    "get-command get-experimentalfeature get-help get-history get-job get-module "
    "get-pshostprocessinfo get-pssession get-pssessioncapability "
    "get-pssessionconfiguration get-pssubsystem import-module invoke-command "
    "invoke-history new-module new-modulemanifest new-psrolecapabilityfile "
    "new-pssession new-pssessionconfigurationfile new-pssessionoption "
    "new-pstransportoption out-default out-host out-null receive-job "
    "receive-pssession register-argumentcompleter register-pssessionconfiguration "
    "remove-job remove-module remove-pssession resume-job save-help set-psdebug "
    "set-pssessionconfiguration set-strictmode start-job stop-job suspend-job "
    "test-modulemanifest test-pssessionconfigurationfile "
    "unregister-pssessionconfiguration update-help wait-job where-object "
    # Microsoft.PowerShell.Utility
    "add-member add-type clear-variable compare-object convert-string "
    "convertfrom-csv convertfrom-json convertfrom-markdown convertfrom-sddlstring "
    "convertfrom-string convertfrom-stringdata convertto-csv convertto-html "
    "convertto-json convertto-xml debug-runspace disable-psbreakpoint "
    "disable-runspacedebug enable-psbreakpoint enable-runspacedebug export-alias "
    "export-clixml export-csv export-formatdata export-pssession format-custom "
    "format-hex format-list format-table format-wide get-alias get-culture "
    "get-date get-error get-event get-eventsubscriber get-filehash get-formatdata "
    "get-host get-markdownoption get-member get-psbreakpoint get-pscallstack "
    "get-random get-runspace get-runspacedebug get-securerandom get-tracesource "
    "get-typedata get-uiculture get-unique get-uptime get-variable group-object "
    "import-alias import-clixml import-csv import-localizeddata "
    "import-powershelldatafile import-pssession invoke-expression "
    "invoke-restmethod invoke-webrequest join-string measure-command "
    "measure-object new-alias new-event new-guid new-object new-temporaryfile "
    "new-timespan new-variable out-file out-gridview out-printer out-string "
    "read-host register-engineevent register-objectevent remove-alias "
    "remove-event remove-psbreakpoint remove-typedata remove-variable "
    "select-object select-string select-xml send-mailmessage set-alias set-date "
    "set-markdownoption set-psbreakpoint set-tracesource set-variable show-command "
    "show-markdown sort-object start-sleep tee-object test-json trace-command "
    "unblock-file unregister-event update-formatdata update-list update-typedata "
    "wait-debugger wait-event write-debug write-error write-host write-information "
    "write-output write-progress write-verbose write-warning "
    # Microsoft.PowerShell.Management
    "add-computer add-content checkpoint-computer clear-content clear-eventlog "
    "clear-item clear-itemproperty clear-recyclebin complete-transaction "
    "convert-path copy-item copy-itemproperty debug-process "
    "disable-computerrestore enable-computerrestore get-childitem get-clipboard "
    "get-computerinfo get-computerrestorepoint get-content get-controlpanelitem "
    "get-eventlog get-hotfix get-item get-itemproperty get-itempropertyvalue "
    "get-location get-process get-psdrive get-psprovider get-service "
    "get-timezone get-transaction get-wmiobject invoke-item invoke-wmimethod "
    "join-path limit-eventlog move-item move-itemproperty new-eventlog new-item "
    "new-itemproperty new-psdrive new-service new-webserviceproxy pop-location "
    "push-location register-wmievent remove-computer remove-eventlog remove-item "
    "remove-itemproperty remove-psdrive remove-service remove-wmiobject "
    "rename-computer rename-item rename-itemproperty "
    "reset-computermachinepassword resolve-path restart-computer restart-service "
    "restore-computer resume-service set-clipboard set-content set-item "
    "set-itemproperty set-location set-service set-timezone set-wmiinstance "
    "show-controlpanelitem show-eventlog split-path start-process start-service "
    "start-transaction stop-computer stop-process stop-service suspend-service "
    "test-computersecurechannel test-connection test-path undo-transaction "
    "use-transaction wait-process write-eventlog "
    # Security · Host · Diagnostics · Archive · PSReadLine · CimCmdlets
    "convertfrom-securestring convertto-securestring get-acl "
    "get-authenticodesignature get-cmsmessage get-credential get-executionpolicy "
    "get-pfxcertificate new-filecatalog protect-cmsmessage set-acl "
    "set-authenticodesignature set-executionpolicy test-filecatalog "
    "unprotect-cmsmessage start-transcript stop-transcript export-counter "
    "get-counter get-winevent import-counter new-winevent compress-archive "
    "expand-archive get-psreadlinekeyhandler get-psreadlineoption "
    "remove-psreadlinekeyhandler set-psreadlinekeyhandler set-psreadlineoption "
    "get-cimassociatedinstance get-cimclass get-ciminstance get-cimsession "
    "invoke-cimmethod new-ciminstance new-cimsession new-cimsessionoption "
    "register-cimindicationevent remove-ciminstance remove-cimsession "
    "set-ciminstance "
    # PowerShellGet · PackageManagement
    "find-module find-package find-packageprovider find-script get-installedmodule "
    "get-package get-packageprovider get-packagesource get-psrepository "
    "import-packageprovider install-module install-package install-packageprovider "
    "install-script publish-module register-packagesource register-psrepository "
    "save-module save-package set-packagesource set-psrepository uninstall-module "
    "uninstall-package unregister-packagesource unregister-psrepository "
    "update-module").split())


def is_workspace_launcher(path):
    """True si `path` es un lanzador que escribió Workspace (o la instalación
    anterior). Solo lee el principio del archivo; un symlink jamás es nuestro
    (el instalador nativo de Claude Code deja uno en ~/.local/bin)."""
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            return False
        with open(path, "rb") as fh:
            head = fh.read(4096).decode("utf-8", "replace")
    except OSError:
        return False
    if any(ln.startswith(_LAUNCHER_MARKS) for ln in head.splitlines()[:3]):
        return True
    return bool(_CMD_SHIM_RE.match(head))


def launcher_conflict(name):
    """'' si `name` puede ser el comando de un agente (escribir o refrescar su
    lanzador). Si no, qué lo ocupa: RESERVED (el comando del hub o el CLI de un
    motor, instalado o no — su instalador lo pondría donde el lanzador lo tapa),
    POWERSHELL (Windows: un comando de PowerShell, que la función del agente
    taparía), un archivo AJENO en su lugar de ~/.local/bin, u otro programa del
    PATH con ese nombre (git, python…) que el lanzador taparía: ~/.local/bin va
    primero. Un lanzador NUESTRO que ya está en su lugar se puede refrescar."""
    n = (name or "").strip().lower()
    if n in ("workspace",) + ENGINE_CLIS:
        return RESERVED
    if IS_WIN and n in _PS_COMMANDS:
        return POWERSHELL
    own = os.path.join(HOME, ".local", "bin", n + (".cmd" if IS_WIN else ""))
    if os.path.lexists(own):
        return "" if is_workspace_launcher(own) else own
    hit = shutil.which(n)
    return hit if hit and not is_workspace_launcher(hit) else ""


def conflict_text(name, hit):
    """El choque de launcher_conflict en palabras (instalador y carga)."""
    if hit == RESERVED:
        return f"«{name}» es el comando de WORKSPACE o de un motor"
    if hit == POWERSHELL:
        return f"«{name}» es un comando de PowerShell"
    return f"«{name}» ya es otro programa ({hit})"


def stale_launcher(name):
    """Lo que queda del comando que una versión ANTERIOR le puso a `name` y que
    hoy tapa a un motor o a PowerShell (RESERVED/POWERSHELL): su lanzador
    NUESTRO en ~/.local/bin (el .cmd en Windows) y, en Windows, su función en
    workspace-cmds.ps1. [] si no queda nada nuestro. Jamás el hub."""
    n = (name or "").strip().lower()
    if n == "workspace" or launcher_conflict(n) not in (RESERVED, POWERSHELL):
        return []
    out = []
    own = os.path.join(HOME, ".local", "bin", n + (".cmd" if IS_WIN else ""))
    if is_workspace_launcher(own):
        out.append(own)
    if IS_WIN:
        ps1 = os.path.join(HOME, ".claude", "workspace-cmds.ps1")
        try:
            with open(ps1, encoding="utf-8") as fh:
                if any(ln.startswith(f"function {n} ") for ln in fh):
                    out.append(ps1)
        except OSError:
            pass
    return out


def retire_launcher(name):
    """Retira lo de stale_launcher(name): borra el lanzador viejo (solo si es
    NUESTRO) y saca su función del archivo de PowerShell de Workspace, para que
    el motor o el comando de PowerShell vuelvan a responder. El agente sigue
    abriéndose desde `workspace`. Respeta --dry-run; falla-suave (lo que no se
    pudo retirar se avisa y queda para el doctor). Devuelve lo retirado."""
    n = (name or "").strip().lower()
    hechos = []
    for p in stale_launcher(n):
        if DRY:
            dry(f"retiraría el comando viejo `{n}` ({p})")
            continue
        try:
            if p.endswith(".ps1"):
                with open(p, encoding="utf-8") as fh:
                    lineas = fh.read().splitlines()
                write_text(p, "".join(ln + "\n" for ln in lineas
                                      if not ln.startswith(f"function {n} ")))
            else:
                os.remove(p)
            hechos.append(p)
        except OSError as e:
            say(f"⚠ no pude retirar el comando viejo `{n}` ({p}): {e}")
    if hechos:
        ok(f"comando viejo `{n}` retirado: tapaba a otro programa ({', '.join(hechos)})")
    return hechos


def _launcher_names(agent_names):
    """(nombres que SÍ llevan comando, [(nombre, qué lo ocupa)]). Un agente cuyo
    nombre choca (launcher_conflict) se queda sin lanzador —se abre desde
    `workspace`— en vez de tapar ese programa en la terminal. Avisa cada uno y
    retira el lanzador viejo que una versión anterior le había puesto. También
    el de un agente que YA NO está registrado con nombre de motor: quitar un
    agente no borra su comando, y ese seguiría tapando al motor para siempre."""
    keep, skipped = [], []
    for name in agent_names:
        hit = launcher_conflict(name)
        if hit:
            skipped.append((name, hit))
            say(f"⚠ `{name}` queda sin comando en la terminal: {conflict_text(name, hit)} "
                f"— ábrelo desde `workspace`")
            retire_launcher(name)
        else:
            keep.append(name)
    for name in ENGINE_CLIS:                  # huérfanos (solo si son NUESTROS)
        if name not in agent_names:
            retire_launcher(name)
    return keep, skipped


def launcher_unix(name, script, lead=""):
    path = os.path.join(HOME, ".local", "bin", name)
    # lo AJENO no se pisa jamás (p. ej. el symlink `claude` del instalador nativo)
    if os.path.lexists(path) and not is_workspace_launcher(path):
        say(f"⚠ no instalo el comando `{name}`: {path} ya existe y no es de "
            f"WORKSPACE — se conserva")
        return False
    body = f'''#!/bin/bash
{LAUNCHER_MARK} `{name}`
PY="{PY}"
exec "$PY" "{script}" {lead}"$@"
'''
    write_text(path, body)
    if not DRY:
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    ok(f"comando `{name}` instalado ({path})")
    return True


def _os_profile_dir():
    """Carpeta de usuario REAL según Windows (FOLDERID_Profile), sin mirar
    HOME/USERPROFILE. '' fuera de Windows o si la API falla."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                        ("d", ctypes.c_ubyte * 8)]
        # FOLDERID_Profile {5E6C858F-0E22-4760-9AFE-EA3317B67173}
        fid = _GUID(0x5E6C858F, 0x0E22, 0x4760,
                    (ctypes.c_ubyte * 8)(0x9A, 0xFE, 0xEA, 0x33, 0x17, 0xB6, 0x71, 0x73))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None,
                                                      ctypes.byref(out)) != 0:
            return ""
        try:
            return out.value or ""
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except Exception:
        return ""


def _home_de_prueba():
    """True si HOME no es la carpeta REAL del socio: lo parchó un test, o TODO el
    proceso arrancó con HOME/USERPROFILE temporales (tests/e2e). Ahí no se le
    pregunta nada a PowerShell: su $PROFILE y su ExecutionPolicy son los reales."""
    return (os.path.normcase(HOME) != os.path.normcase(_REAL_HOME)
            or os.path.normcase(os.path.realpath(HOME))
            != os.path.normcase(os.path.realpath(_os_profile_dir() or HOME)))


def _ps_profile():
    """Ruta del $PROFILE de PowerShell (la pregunta a PowerShell). '' si no se puede.
    M4: prueba `pwsh` (PowerShell 7+) y luego `powershell` (Windows PowerShell 5.1) —
    en máquinas con solo PS7 instalado `powershell.exe` no existe y antes degradaba en
    silencio. Devuelve el primer $PROFILE no vacío."""
    # GUARD DE HERMETICIDAD (2026-09-21): si HOME esta redirigido (la suite corre
    # en un HOME temporal), el $PROFILE REAL del socio NO es el destino. Sin esto
    # `$PROFILE` se resuelve preguntandole a PowerShell — que ignora por completo
    # el HOME parcheado — y CUALQUIER test que instalara launchers escribia en el
    # PowerShell del socio la linea `. "<temp>/workspace-cmds.ps1"`. Al borrarse el
    # temporal, CADA pestaña nueva de su terminal arrancaba con un error y sin
    # menu. Paso de verdad el 2026-09-21.
    # 2026-10-16: tambien si TODO el proceso arranco con HOME/USERPROFILE
    # temporales (tests/e2e/escenarios_motores.py): ahi HOME == _REAL_HOME y el
    # guard de arriba no veia nada, pero PowerShell resuelve $PROFILE por la
    # carpeta Documentos REAL → la linea `. "<temp>/workspace-cmds.ps1"` quedo
    # en el perfil real del socio y cada PowerShell nuevo arrancaba con error. Se compara
    # contra la carpeta de usuario que reporta Windows, que no lee variables.
    if _home_de_prueba():
        return os.path.join(HOME, "Documents", "WindowsPowerShell",
                            "Microsoft.PowerShell_profile.ps1")
    import subprocess as _sp
    for exe in ("pwsh", "powershell"):
        try:
            r = _sp.run([exe, "-NoProfile", "-Command", "$PROFILE"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=10)
            out = (r.stdout or "").strip()
            if out:
                return out
        except Exception:
            continue
    return ""


def _ps_set_block(marker, block, legacy):
    """Deja en el $PROFILE exactamente UNA copia de `block` (al final). Antes
    borra TODA línea que contenga alguno de los substrings `legacy` — eso deduplica
    dot-sources sin marcar y reemplaza bloques de versiones viejas. Idempotente:
    si el profile ya quedó limpio y con el bloque, no reescribe. Devuelve la ruta
    del profile o ''. (`marker` identifica el bloque en mensajes/chequeos.)"""
    prof = _ps_profile()
    if not prof:
        say(f"{DIM}No ubiqué tu $PROFILE de PowerShell. Agrégalo a mano:{R}\n{block}")
        return ""
    cur = ""
    if os.path.exists(prof):
        try:
            # $PROFILE preexistente puede venir en ANSI/cp1252 (no-UTF-8):
            # errors="replace" preserva sus líneas (el write de abajo ya
            # normaliza a UTF-8) en vez de tronar el instalador a media
            # corrida con UnicodeDecodeError. (doctor.py fase 6 ya guarda
            # este mismo read con try/except — consistencia.)
            cur = open(prof, encoding="utf-8", errors="replace").read()
        except Exception as e:
            # ilegible (permisos/lock): NO reescribimos a ciegas un profile
            # que no pudimos leer — instrucción manual, como cuando no hay prof.
            say(f"{DIM}No pude leer {prof} ({e}). Agrégalo a mano:{R}\n{block}")
            return ""
    kept = [ln for ln in cur.splitlines() if not any(s in ln for s in legacy)]
    # colapsar los huecos que dejan las líneas borradas (mantiene el resultado estable)
    base = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip("\n")
    new = (base + "\n\n" if base else "") + block + "\n"
    if new == cur:
        return prof
    if DRY:
        dry(f"actualizaría {prof} ({marker})")
        return prof
    try:
        os.makedirs(os.path.dirname(prof), exist_ok=True)
        with open(prof, "w", encoding="utf-8") as f:
            f.write(new)
    except Exception as e:
        say(f"{DIM}No pude escribir a {prof} ({e}). Agrégalo a mano:{R}\n{block}")
        return ""
    return prof


# ── ExecutionPolicy de PowerShell (solo Windows) ─────────────────────────────
# Windows trae ExecutionPolicy=Restricted → PowerShell NO carga el $PROFILE, y ahí
# viven el dot-source de workspace-cmds y el greeter (auto-open del menú). Síntoma
# del cliente: 'UnauthorizedAccess' en CADA terminal y el menú nunca abre (los shims
# .cmd sí corren: no pasan por el profile). Mac/Linux no tienen esta traba.
#
# Dos trampas que esto esquiva (las dos rompían la primera versión del fix):
#  1. BYPASS HEREDADO. El instalador del cliente corre `powershell -ExecutionPolicy
#     Bypass -File setup.ps1`; ese Bypass viaja a los procesos hijos en la env var
#     PSExecutionPolicyPreference. Un PowerShell hijo reporta effective=Bypass ("todo
#     bien"), pero ese Bypass muere con el instalador: la terminal siguiente vuelve a
#     Restricted. Por eso el hijo arranca SIN esa var y se decide por los scopes
#     PERSISTENTES (Process se ignora).
#  2. DOS MOTORES. Windows PowerShell 5.1 y PowerShell 7 (pwsh) guardan su policy
#     CurrentUser por separado → se revisa/ajusta cada motor instalado.
_PS_ENGINES = (("powershell", "Windows PowerShell"), ("pwsh", "PowerShell 7"))
_EP_ALLOW = {"remotesigned", "unrestricted", "bypass"}   # corren scripts locales sin firma


def _ps_eval(exe, cmd):
    """Corre `cmd` en el motor `exe`; stdout stripped, '' si falla o no está
    instalado. El hijo arranca SIN PSExecutionPolicyPreference → ve la policy
    PERSISTENTE (la de una terminal nueva), no un Bypass heredado del instalador.
    HERMÉTICO: bajo un HOME de test no spawnea nada (mismo guard que _ps_profile,
    también si el proceso entero arrancó con un HOME temporal — Greptile 2026-10-17)."""
    if _home_de_prueba():
        return ""
    import subprocess as _sp
    env = {k: v for k, v in os.environ.items()
           if k.upper() != "PSEXECUTIONPOLICYPREFERENCE"}
    try:
        r = _sp.run([exe, "-NoProfile", "-Command", cmd], capture_output=True,
                    text=True, encoding="utf-8", errors="replace", timeout=15,
                    env=env)
    except Exception:
        return ""
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def _ps_policy_list(exe):
    """{scope: policy} de `Get-ExecutionPolicy -List` en el motor `exe`. {} si el
    motor no está instalado (o bajo HOME de test)."""
    out = _ps_eval(exe, "Get-ExecutionPolicy -List | ForEach-Object "
                        "{ \"$($_.Scope)=$($_.ExecutionPolicy)\" }")
    res = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            res[k.strip()] = v.strip()
    return res


def _execution_policy_action(scopes):
    """PURO (sin I/O → testeable). Decide con los scopes PERSISTENTES; Process se
    ignora a propósito (es efímero: muere con el proceso que lo puso).
      ('ok', pol)       ya corre scripts locales → nada que hacer.
      ('blocked', pol)  una GPO (MachinePolicy/UserPolicy) manda y es restrictiva →
                        CurrentUser NO puede ganar; necesita TI/admin.
      ('respect', pol)  AllSigned puesto a propósito → no se debilita en silencio.
      ('set', pol)      default de fábrica (Restricted/Undefined) → CurrentUser a
                        RemoteSigned."""
    def first(*names):
        for n in names:
            v = (scopes.get(n) or "").strip().lower()
            if v and v != "undefined":
                return v
        return ""
    gpo = first("MachinePolicy", "UserPolicy")
    if gpo:
        return ("ok", gpo) if gpo in _EP_ALLOW else ("blocked", gpo)
    pol = first("CurrentUser", "LocalMachine") or "restricted"   # default Windows cliente
    if pol in _EP_ALLOW:
        return ("ok", pol)
    if pol == "allsigned":
        return ("respect", pol)
    return ("set", pol)


def _set_execution_policy_currentuser(exe, policy="RemoteSigned"):
    """Set-ExecutionPolicy -Scope CurrentUser (admin-free) en el motor `exe` y lo
    VERIFICA releyendo ese scope: decide el estado real, no el código de salida."""
    out = _ps_eval(exe, f"Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy "
                        f"{policy} -Force -ErrorAction SilentlyContinue; "
                        f"Get-ExecutionPolicy -Scope CurrentUser")
    return bool(out) and out.splitlines()[-1].strip().lower() == policy.lower()


def execution_policy_findings():
    """[(exe, label, action, pol)] de cada PowerShell instalado cuya policy NO deja
    cargar el $PROFILE (action != 'ok'). SOLO LECTURA: lo usan ensure (para actuar)
    y el doctor (para diagnosticar — el update repara vía el doctor, así que si solo
    lo viera install, `workspace update` nunca lo arreglaría). [] fuera de Windows,
    sin PowerShell o bajo HOME de test."""
    if not IS_WIN:
        return []
    out = []
    for exe, label in _PS_ENGINES:
        scopes = _ps_policy_list(exe)
        if not scopes:
            continue                      # motor no instalado (o HOME de test)
        action, pol = _execution_policy_action(scopes)
        if action != "ok":
            out.append((exe, label, action, pol))
    return out


def ensure_execution_policy_windows():
    """Deja que el $PROFILE (comandos + greeter) cargue en cada PowerShell instalado:
    sube SOLO el scope CurrentUser a RemoteSigned (admin-free; el balance que
    recomienda Microsoft: corre scripts locales, exige firma a los descargados).
    JAMÁS toca LocalMachine. GPO restrictiva → lo dice (TI). AllSigned puesto a
    propósito → lo respeta y lo dice. Idempotente, falla-suave."""
    for exe, label, action, pol in execution_policy_findings():
        if action == "blocked":
            say(f"{DIM}{label}: la política de ejecución la fija tu organización "
                f"(GPO = {pol}) y el menú no puede autoarrancar. Pídele a TI que la "
                f"ponga en RemoteSigned.{R}")
        elif action == "respect":
            say(f"{DIM}{label}: tienes ExecutionPolicy=AllSigned (puesta a propósito); "
                f"no la cambio. Para que el menú autoarranque:  "
                f"Set-ExecutionPolicy -Scope CurrentUser RemoteSigned{R}")
        elif DRY:
            dry(f"{label}: subiría ExecutionPolicy (CurrentUser) de {pol} a RemoteSigned")
        elif _set_execution_policy_currentuser(exe):
            ok(f"{label}: ExecutionPolicy (CurrentUser) {pol} → RemoteSigned — tu "
               f"$PROFILE ya carga; abre una terminal nueva")
        else:
            say(f"{DIM}{label}: no pude ajustar la ExecutionPolicy. Córrelo tú (sin "
                f"admin):  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned{R}")


def win_cmd_shims(agents):
    """B3 · shims `.cmd` en ~/.local/bin (donde ya vive claude.exe, ya en PATH) para
    que `workspace` y `<agente>` funcionen en CUALQUIER shell (cmd.exe, terminal de VS
    Code, PowerShell) SIN depender del $PROFILE ni de la execution policy — que es lo
    que dejaba a los comandos como "no se reconoce". Invocan el MISMO target que las
    funciones PowerShell, con el intérprete ESTABLE de win_python() (PY). Idempotente:
    write_text sobrescribe limpio y crea ~/.local/bin si falta. Salida con \\n: en
    Windows el modo texto la traduce a \\r\\n (en Mac queda \\n; los tests corren ahí)."""
    bindir = os.path.join(HOME, ".local", "bin")
    front = os.path.join(WORKSPACE, "front.py")
    disp = os.path.join(WORKSPACE, "dispatch.py")

    def shim(target, *args):
        tail = "".join(f' "{a}"' if (" " in a) else f" {a}" for a in args)
        return f'@echo off\n"{PY}" "{target}"{tail} %*\n'

    refused = []

    def put(path, body):
        # lo AJENO no se pisa jamás (mismo criterio que launcher_unix) y se
        # devuelve: quien llama no puede dar el comando por instalado
        if os.path.lexists(path) and not is_workspace_launcher(path):
            say(f"⚠ no instalo {path}: ya existe y no es de WORKSPACE — se conserva")
            if path not in refused:
                refused.append(path)
            return
        write_text(path, body)

    put(os.path.join(bindir, "workspace.cmd"), shim(front))
    put(os.path.join(bindir, "workspace.cmd"), shim(front))      # alias
    for name in agents:
        put(os.path.join(bindir, f"{name}.cmd"), shim(disp, name))
    ok(f"shims .cmd para cmd.exe/VS Code/PowerShell: {bindir} "
       f"(workspace + workspace + {len(agents)} agente(s))")
    # memoria v1 (2026-10-17): los agentes guardan memoria con `workspace
    # memoria nota …` desde SU terminal; la de Claude Code en Windows es Git
    # Bash, que no ejecuta `.cmd` sin la extensión → shim sh sin extensión.
    if not DRY:
        posix = lambda p: p.replace("\\", "/")
        sh = os.path.join(bindir, "workspace")
        try:
            if os.path.lexists(sh) and not is_workspace_launcher(sh):
                # lo AJENO no se pisa jamás (mismo criterio que put)
                raise OSError("ya existe y no es de WORKSPACE — se conserva")
            os.makedirs(bindir, exist_ok=True)
            with open(sh, "w", encoding="utf-8", newline="\n") as fh:
                fh.write('#!/bin/sh\n# WORKSPACE · comando workspace para Git Bash\n'
                         'exec "%s" "%s" "$@"\n' % (posix(PY), posix(front)))
            ok(f"shim sh para Git Bash: {sh}")
        except OSError as e:
            say(f"{DIM}No pude escribir {sh} ({e}); en Git Bash usa workspace.cmd{R}")
    return refused


def _ps_cmds_existentes(p):
    """Nombres de agente con función en el workspace-cmds.ps1 actual (sin
    `workspace`), solo si su agente sigue existiendo (registrado o del repo)."""
    try:
        with open(p, encoding="utf-8") as fh:
            nombres = re.findall(r"^function ([a-z0-9][a-z0-9_-]*) \{", fh.read(), re.M)
    except OSError:
        return []
    vivos = set()
    try:
        import agentsreg
        vivos = {a["name"] for a in agentsreg.agents() if os.path.isdir(a.get("brain") or "")}
    except Exception:
        pass
    repo = os.path.join(WORKSPACE, "agents")
    return [n for n in nombres if n != "workspace"
            and (n in vivos or os.path.isfile(os.path.join(repo, n, "agent.json")))]


def launchers_windows(agents):
    # El $PROFILE no carga con policy Restricted (default de Windows) → sin esto el
    # dot-source y el greeter que escribimos abajo darían 'UnauthorizedAccess' y el
    # menú nunca abriría. Subir CurrentUser a RemoteSigned es la precondición.
    ensure_execution_policy_windows()
    agents, skipped = _launcher_names(agents)    # una función PS taparía ese programa
    lines = ["# WORKSPACE · comandos (dot-source desde tu $PROFILE)"]
    front = os.path.join(WORKSPACE, "front.py")
    disp = os.path.join(WORKSPACE, "dispatch.py")
    # `workspace` es el comando; `workspace` queda como ALIAS permanente (memoria
    # muscular del equipo + todo lo que ya lo invoca: greeter viejo, docs, hooks).
    lines.append(f'function workspace {{ & "{PY}" "{front}" @args }}')
    p = os.path.join(HOME, ".claude", "workspace-cmds.ps1")
    # Cargar o crear UN agente llama aquí solo con ese nombre: los comandos de
    # los demás agentes que ya estaban se conservan (antes se borraban), salvo
    # los que hoy taparían otro programa (launcher_conflict).
    existentes = [n for n in _ps_cmds_existentes(p) if not launcher_conflict(n)]
    for name in list(dict.fromkeys(list(agents) + existentes)):
        lines.append(f'function {name} {{ & "{PY}" "{disp}" {name} @args }}')
    write_text(p, "\n".join(lines) + "\n")
    ok(f"comandos PowerShell escritos: {p}")
    # auto dot-source en el $PROFILE (idempotente; dedupe de líneas viejas sin marcar)
    prof = _ps_set_block("# WORKSPACE-cmds", f'# WORKSPACE-cmds\n. "{p}"',
                         legacy=("workspace-cmds.ps1", "# WORKSPACE-cmds"))
    if prof:
        ok(f"comandos cargados en tu $PROFILE: {prof}")
    else:
        say(f"{DIM}Si no, agrega a tu $PROFILE:  . \"{p}\"{R}")
    # B3 · ADEMÁS de las funciones PS: shims `.cmd` en PATH (independientes del
    # $PROFILE y de la execution policy → funcionan en TODA shell).
    for p in win_cmd_shims(agents) or []:     # .cmd ajeno que se conservó
        skipped.append((os.path.basename(p)[:-len(".cmd")], p))
    return skipped


PATH_MARK = "# WORKSPACE · PATH (~/.local/bin)"


def ensure_path_zshrc():
    """Asegura ~/.local/bin en el PATH vía ~/.zshrc, idempotente. Se llama ANTES de
    install_greeter() para que el bloque del PATH quede ARRIBA del greeter — si no, el
    greeter corre con `command -v workspace` fallando y el menú no sale (bug del deploy)."""
    rc = os.path.join(HOME, ".zshrc")
    cur = open(rc, encoding="utf-8").read() if os.path.exists(rc) else ""
    if PATH_MARK in cur:
        return
    if DRY:
        dry(f"agregaría ~/.local/bin al PATH en {rc}")
        return
    with open(rc, "a", encoding="utf-8") as f:
        f.write(f'\n{PATH_MARK}\nexport PATH="$HOME/.local/bin:$PATH"\n')
    ok("PATH: ~/.local/bin agregado a ~/.zshrc (reinicia la terminal o `source ~/.zshrc`)")


def install_launchers(agent_names):
    """`workspace` + un comando por agente. Devuelve [(nombre, qué lo ocupa)]
    de los comandos que NO quedaron instalados: el agente cuyo nombre choca con
    otro programa (ver _launcher_names) y el que encontró un archivo ajeno en
    su lugar — también el del hub (`workspace`)."""
    if global_writes_blocked("shims/launchers"):
        return []
    if IS_WIN:
        return launchers_windows(agent_names)
    bindir = os.path.join(HOME, ".local", "bin")
    skipped = []
    if not launcher_unix("workspace", os.path.join(WORKSPACE, "front.py")):
        skipped.append(("workspace", os.path.join(bindir, "workspace")))
    names, otros = _launcher_names(agent_names)
    skipped += otros
    for name in names:
        if not launcher_unix(name, os.path.join(WORKSPACE, "dispatch.py"), lead=f"{name} "):
            skipped.append((name, os.path.join(bindir, name)))
    if bindir not in os.environ.get("PATH", "").split(os.pathsep):
        ensure_path_zshrc()
    return skipped


# Greeter de Windows (versionado: subir vN cuando cambie el bloque → install/doctor
# reemplazan el viejo). Guard ROBUSTO: solo sesión interactiva ([Environment]::
# UserInteractive) — funciona en CUALQUIER consola (Windows Terminal, consola clásica,
# VS Code, pwsh), no solo Windows Terminal; un $PROFILE cargado por un script/pipe no
# es UserInteractive y no lanza el menú. Al volver del menú se mandan los OSC 110/111/112
# para que la terminal no quede teñida por el tema del agente.
#: v4 (2026-10-17): UserInteractive es True en CUALQUIER proceso de escritorio,
#: también en el PowerShell oculto con el que un motor corre un comando
#: (Antigravity: `powershell -Command …` carga el $PROFILE). Ahí el menú se
#: quedaba esperando una tecla y cada `workspace memoria nota` tardaba minutos.
#: Ahora no abre si la entrada o la salida están redirigidas o si PowerShell
#: vino a correr un comando o un archivo (-Command/-File/-EncodedCommand/-NonInteractive).
_WIN_GREETER_GUARD = (
    'if ([Environment]::UserInteractive '
    '-and -not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected '
    "-and -not ([Environment]::GetCommandLineArgs() | Where-Object { $_ -match "
    "'^[-/](c|co|com|comm|comma|comman|command|f|fi|fil|file|ec|encodedcommand|noni|noninteractive)$' }) "
    '-and -not $env:WORKSPACE_GREETER -and -not $env:WORKSPACE_NO_GREETER '
    '-and (Get-Command workspace -ErrorAction SilentlyContinue)) ')
WIN_GREETER_MARK = "# WORKSPACE-greeter v4"
WIN_GREETER_BLOCK = (
    '# WORKSPACE-greeter v4 — menú al abrir terminal, cualquier consola interactiva '
    '(opt-out: $env:WORKSPACE_NO_GREETER=1; el guard WORKSPACE_GREETER se setea solo '
    'mientras corre workspace y se QUITA en finally, para NO heredarlo a terminales '
    'abiertas desde una sesion de Workspace — si no, su greeter nunca dispararia; '
    'no abre en un PowerShell que solo corre un comando)\n'
    + _WIN_GREETER_GUARD +
    '{ try { $env:WORKSPACE_GREETER="1"; workspace } '
    'finally { Remove-Item Env:WORKSPACE_GREETER -ErrorAction SilentlyContinue }; '
    'Write-Host -NoNewline "$([char]27)]110$([char]7)$([char]27)]111$([char]7)$([char]27)]112$([char]7)" }')

GREETER_MARK = "WORKSPACE · menú al abrir terminal"
GREETER_MARK_V1 = "WORKSPACE · menú al abrir terminal (v1)"   # bloque pre-rename (se reemplaza)
GREETER_BLOCK = """
# ── WORKSPACE · menú al abrir terminal (elige agente o terminal normal) ────────
# Desactivar: borra este bloque, o corre  export WORKSPACE_NO_GREETER=1
# Condición ROBUSTA: cualquier shell INTERACTIVA (no solo login) → funciona en
# iTerm2, VS Code, tmux, etc. — NO gatear a `-o login` (iTerm2 no siempre lo es).
# WORKSPACE_GREETER va one-shot (prefijo de comando), NO `export`: así la var NO
# queda en el environment del shell → las terminales lanzadas DESDE una sesión de
# Workspace (agentes, iTerm abierto desde el hub) no la heredan y su propio greeter
# SÍ dispara. workspace y sus subshells igual la ven (guard anti-recursión intacto).
if [[ $- == *i* && -z "$WORKSPACE_GREETER" && -z "$WORKSPACE_NO_GREETER" ]] && command -v workspace >/dev/null 2>&1; then
  WORKSPACE_GREETER=1 workspace
  printf '\\033]111\\007\\033]110\\007\\033]112\\007'   # restaura colores de la terminal al volver al shell
fi
"""


def _autostart_wanted(full_now):
    """¿El greeter que deja install abre el menú? La preferencia GUARDADA
    (ui.autostart) manda; sin preferencia se conserva lo que ya hay (un
    greeter que abre el menú sigue abriéndolo) y una instalación nueva sigue
    el default del ajuste: solo con el comando."""
    try:
        import settings
        v = settings.get_stored("ui.autostart")
        if isinstance(v, bool):
            return v
    except Exception:
        pass
    return bool(full_now)


def _win_greeter_full(cur):
    """¿El $PROFILE trae hoy un greeter que abre el menú (no el recordatorio
    de «autostart OFF»)? Cualquier versión del bloque cuenta."""
    heads = [ln for ln in (cur or "").splitlines()
             if "WORKSPACE-greeter" in ln and ln.lstrip().startswith("#")]
    return bool(heads) and not any("autostart OFF" in ln for ln in heads)


def _zsh_greeter_full(cur):
    """¿El ~/.zshrc trae hoy un greeter que abre el menú (no el recordatorio de
    «autostart OFF»)? Espejo de _win_greeter_full; cualquier versión cuenta."""
    heads = [ln for ln in (cur or "").splitlines()
             if GREETER_MARK in ln and ln.lstrip().startswith("#")]
    return bool(heads) and not any("autostart OFF" in ln for ln in heads)


def install_greeter():
    """Al abrir una terminal, muestra el menú de WORKSPACE (agentes o terminal normal).
    Idempotente; se desactiva con WORKSPACE_NO_GREETER=1 o borrando el bloque.
    Respeta ui.autostart: reinstalar o actualizar jamás vuelve a encender el
    autoabrir que el usuario apagó (con OFF deja solo el recordatorio)."""
    if IS_WIN:
        cur = ""
        try:
            prof0 = _ps_profile()
            if prof0 and os.path.exists(prof0):
                cur = open(prof0, encoding="utf-8", errors="replace").read()
        except Exception:
            cur = ""
        on = _autostart_wanted(_win_greeter_full(cur))
        # reemplaza cualquier versión vieja del bloque (sin guard de interactividad)
        prof = _ps_set_block(WIN_GREETER_MARK,
                             WIN_GREETER_BLOCK if on else WIN_GREETER_HINT_BLOCK,
                             legacy=("WORKSPACE-greeter", "WORKSPACE-greeter",
                                     "WORKSPACE_GREETER"))
        if prof:
            ok(f"greeter al día (Windows): "
               f"{'menú al abrir Windows Terminal' if on else 'solo con el comando workspace'}"
               f" ({prof})")
        return
    rc = os.path.join(HOME, ".zshrc")
    cur = open(rc, encoding="utf-8").read() if os.path.exists(rc) else ""
    if GREETER_MARK in cur:
        # normal u «autostart OFF» (comparten la marca): sin preferencia
        # guardada se respeta tal cual; si ui.autostart dice otra cosa, se
        # aplica (igual que en Windows) con el corte quirúrgico de siempre.
        full = _zsh_greeter_full(cur)
        on = _autostart_wanted(full)
        if on != full:
            set_terminal_autostart(on)          # dice él mismo qué hizo (o por qué no)
            return
        ok("greeter ya configurado: " + ("menú al abrir terminal" if full
                                         else "solo con el comando workspace (ui.autostart off)"))
        return
    legacy = GREETER_MARK_V1 in cur
    block = GREETER_BLOCK if _autostart_wanted(legacy) else GREETER_HINT_BLOCK
    if DRY:
        dry(f"{'reemplazaría el greeter viejo' if legacy else 'agregaría el greeter'} "
            f"(menú al abrir terminal) en {rc}")
        return
    if legacy:
        # Bloque pre-rename: se borra ENTERO (de su comentario de cabecera al `fi`
        # que lo cierra) y se reescribe. Si el socio lo editó a mano no reconocemos
        # el cierre: en ese caso NO tocamos nada y lo decimos — mejor un greeter
        # viejo funcionando (`workspace` sigue siendo alias) que un .zshrc roto.
        lines, out, i, cortado = cur.splitlines(True), [], 0, False
        while i < len(lines):
            if GREETER_MARK_V1 in lines[i] and lines[i].lstrip().startswith("#"):
                j = i
                while j < len(lines) and lines[j].strip() != "fi":
                    j += 1
                if j < len(lines):                      # cierre encontrado
                    i, cortado = j + 1, True
                    continue
            out.append(lines[i]); i += 1
        if not cortado:
            say(f"{DIM}Tu greeter de ~/.zshrc está editado a mano: lo dejo como está. "
                f"`workspace` sigue funcionando como alias de `workspace`.{R}")
            return
        with open(rc, "w", encoding="utf-8") as f:
            NL = chr(10)
            f.write("".join(out).rstrip(NL) + NL + block)
        ok("greeter actualizado: " + ("el menú WORKSPACE sale al abrir terminal "
           "(q = terminal normal)" if block is GREETER_BLOCK
           else "solo con el comando workspace (ui.autostart off)"))
        return
    with open(rc, "a", encoding="utf-8") as f:
        f.write(block)
    ok("greeter agregado: " + ("el menú WORKSPACE sale al abrir terminal "
       "(q = terminal normal)" if block is GREETER_BLOCK
       else "solo con el comando workspace (ui.autostart off)"))


# Variante HINT del greeter (autostart OFF): NO lanza el menú, solo recuerda el
# comando. Comparte el GREETER_MARK (así install_greeter lo ve como "ya
# configurado" y respeta la elección) y la misma estructura `if … fi` que el
# bloque normal (así set_terminal_autostart lo corta con el mismo splice).
GREETER_HINT_BLOCK = """
# ── WORKSPACE · menú al abrir terminal (autostart OFF — solo con el comando) ───
# La terminal NO abre el hub sola; escribe `workspace`. Reactivar: ui.autostart
# o  workspace onboarding  (o borra el 'OFF' y deja el greeter normal).
# Misma condición ROBUSTA que el greeter normal (interactiva, sin `-o login`).
# No `export` de WORKSPACE_GREETER: solo imprime el hint (no lanza subshell que
# necesite el guard), y así no contamina el environment ni lo heredan las
# terminales abiertas desde una sesión de Workspace.
if [[ $- == *i* && -z "$WORKSPACE_GREETER" && -z "$WORKSPACE_NO_GREETER" ]] && command -v workspace >/dev/null 2>&1; then
  printf '\\033[2mWorkspace listo · escribe \\033[0m\\033[1mworkspace\\033[0m\\033[2m para abrir el hub\\033[0m\\n'
fi
"""

WIN_GREETER_HINT_BLOCK = (
    '# WORKSPACE-greeter v4 (autostart OFF — solo con el comando workspace)\n'
    + _WIN_GREETER_GUARD +
    '{ Write-Host "Workspace listo - escribe: workspace" }')


def set_terminal_autostart(on):
    """QUIRÚRGICO: reescribe SOLO el bloque del greeter en el rc según la
    preferencia del socio — on = la terminal abre el menú (GREETER_BLOCK);
    off = solo un recordatorio del comando (GREETER_HINT_BLOCK). Idempotente;
    NO toca el resto del archivo ni la lógica de install_greeter/legacy.

    Devuelve la ruta del rc si lo (re)escribió o ya estaba como se pidió; ''
    si degradó (no ubicó el rc, o un bloque editado a mano cuyo cierre no
    reconocí — en ese caso NO tocamos nada). El onboarding usa el valor de
    retorno para decidir el mensaje (aplicado vs solo-preferencia)."""
    if IS_WIN:
        block = WIN_GREETER_BLOCK if on else WIN_GREETER_HINT_BLOCK
        return _ps_set_block(WIN_GREETER_MARK, block,
                             legacy=("WORKSPACE-greeter", "WORKSPACE_GREETER"))
    block = GREETER_BLOCK if on else GREETER_HINT_BLOCK
    rc = os.path.join(HOME, ".zshrc")
    cur = open(rc, encoding="utf-8").read() if os.path.exists(rc) else ""
    # 1) quitar el bloque existente (normal, hint o legacy v1): de la línea del
    #    marcador hasta su `fi` de cierre. Todos los bloques reales terminan en
    #    `fi`; si no lo encuentro, el socio lo editó a mano → no toco nada.
    lines = cur.splitlines(True)
    out, i, dirty = [], 0, False
    while i < len(lines):
        line = lines[i]
        if (GREETER_MARK in line or GREETER_MARK_V1 in line) \
                and line.lstrip().startswith("#"):
            j = i
            while j < len(lines) and lines[j].strip() != "fi":
                j += 1
            if j < len(lines):                       # cierre reconocido
                i = j + 1
                continue
            dirty = True                             # editado a mano → preservar
        out.append(line)
        i += 1
    if dirty:
        say(f"{DIM}Tu greeter de ~/.zshrc está editado a mano: lo dejo como "
            f"está. Ajusta ui.autostart por tu cuenta si quieres.{R}")
        return ""
    base = "".join(out).rstrip(chr(10))
    new = (base + chr(10) if base else "") + block
    if new == cur:                                   # ya estaba así
        return rc
    if DRY:
        dry(f"ajustaría el greeter (autostart {'on' if on else 'off'}) en {rc}")
        return rc
    try:
        with open(rc, "w", encoding="utf-8") as f:
            f.write(new)
    except Exception as e:
        say(f"{DIM}No pude escribir a {rc} ({e}). Ajusta el greeter a mano.{R}")
        return ""
    ok(f"autostart {'ON' if on else 'OFF'}: la terminal "
       f"{'abre el menú WORKSPACE' if on else 'solo recuerda el comando'} ({rc})")
    return rc


def desktop_app_path():
    return os.path.join(HOME, "Desktop", "WORKSPACE.app")


def install_desktop_app():
    """Mac: crea ~/Desktop/WORKSPACE.app — doble-click abre la Terminal y lanza
    `workspace`. SOLO bajo pedido explícito (`python3 install.py --desktop-app`):
    el flujo default de install/update es terminal-only y no crea ninguna .app.
    Idempotente (recompila). Icono de marca (brand/workspace.icns) si está. No-op
    fuera de Mac (Windows: pendiente, un .lnk/.bat)."""
    if sys.platform != "darwin":
        return
    import subprocess, tempfile, shutil as _sh
    app = desktop_app_path()
    launcher = os.path.join(HOME, ".local", "bin", "workspace")
    # Abre Terminal y la DIMENSIONA ≥ el ancho del banner de agente (~114 col) para que
    # NI el hub (96) NI el banner (114) se envuelvan en una ventana chica (default 80).
    osa = ('on run\n'
           '  tell application "Terminal"\n'
           '    activate\n'
           '    do script "clear && exec \\"' + launcher + '\\""\n'
           '    delay 0.2\n'
           '    try\n'
           '      set number of columns of front window to 118\n'
           '      set number of rows of front window to 46\n'
           '    end try\n'
           '  end tell\n'
           'end run\n')
    if DRY:
        dry(f"crearía la app de escritorio {app}")
        return
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(osa); src = fh.name
        subprocess.run(["rm", "-rf", app], check=False)
        r = subprocess.run(["osacompile", "-o", app, src], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        os.remove(src)
        if r.returncode != 0:
            say(f"{DIM}no pude crear la app de escritorio ({(r.stderr or '').strip()[:80]}){R}")
            return
        icns = os.path.join(WORKSPACE, "brand", "workspace.icns")
        if os.path.exists(icns):
            try:
                _sh.copy(icns, os.path.join(app, "Contents", "Resources", "applet.icns"))
                subprocess.run(["touch", app], check=False)   # refresca el icono en Finder
            except Exception:
                pass
        ok(f"app de escritorio: {app}  (doble-click → abre WORKSPACE)")
    except Exception as e:
        say(f"{DIM}app de escritorio: {e}{R}")


# CLIs de los motores soportados (claude-code, codex, antigravity, gemini).
ENGINE_CLIS = ("claude", "codex", "agy", "gemini", "opencode", "openclaw", "hermes")


def check_prereqs():
    """DEPLOY-7: avisa (no aborta) si faltan prerequisitos antes de configurar nada.
    Mejor un mensaje claro que un fallo más adelante. Python ya corre (este script)."""
    import shutil
    miss = []
    if not shutil.which("git"):
        miss.append("git (clónalo/instálalo: en Mac, las Command Line Tools)")
    # Motor: cualquiera de los que Workspace soporta (no siempre Claude Code).
    if not any(shutil.which(b) for b in ENGINE_CLIS):
        miss.append("el CLI del motor que vayas a usar (Claude Code, Codex, "
                    "Antigravity, OpenCode, OpenClaw o Hermes), con sesión iniciada")
    for m in miss:
        say(f"{C}!{R} falta: {m}")
    if miss:
        say(f"{DIM}Puedes seguir, pero algunas piezas no funcionarán hasta resolverlo.{R}\n")


# ── detección de instalación previa / reinstalación (QoL · idempotencia) ─────
def workspace_version():
    """Versión CORTA del harness para los mensajes ('v1a2b3c') o '' si este checkout
    no es un repo git / git no está. Sin RED (solo lee HEAD local). Fail-soft."""
    try:
        import subprocess
        r = subprocess.run(["git", "-C", WORKSPACE, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=5)
        sha = (r.stdout or "").strip()
        return ("v" + sha) if r.returncode == 0 and sha else ""
    except Exception:
        return ""


def prior_install_markers():
    """Rastros PER-MÁQUINA de una instalación previa de WORKSPACE (NO el checkout —
    el estado que deja install.py). Devuelve [(label, path)] de los que existen.
    Sirve para ANUNCIAR 're-install' vs 'primer install': re-correr el instalador es
    SEGURO e idempotente (actualiza lo que cambió, no duplica)."""
    launcher = os.path.join(HOME, ".local", "bin",
                            "workspace.cmd" if IS_WIN else "workspace")
    cands = [("estado per-máquina", _paths.state_dir(HOME)),
             ("comando `workspace`", launcher)]
    return [(lbl, p) for lbl, p in cands if os.path.exists(p)]


# ── INSTALACIÓN ANTERIOR (harness con el nombre viejo, pre-rename) ───────────
# Antes del rename (2026-10) el harness tenía otro nombre (literales en
# legacy.py). En una máquina que lo tuvo pueden quedar: la carpeta del harness
# viejo (en el escritorio o la de su variable de entorno), su estado per-máquina
# bajo ~/.claude y su comando en ~/.local/bin. Se OFRECE retirarlos para seguir
# solo con WORKSPACE. SEGURIDAD N1: jamás se borra sin confirmación EXPLÍCITA, y
# jamás un cerebro/datos del usuario — solo artefactos que SON el harness viejo.
def _legacy_root_candidates():
    cands = []
    env = os.environ.get(legacy.ENV_ROOT)
    if env:
        cands.append(os.path.expanduser(env))
    cands.append(os.path.join(HOME, "Desktop", legacy.HARNESS_DIRNAME))
    seen, out = set(), []
    for c in cands:
        try:
            rc = os.path.realpath(c)
        except Exception:
            rc = c
        if rc not in seen:
            seen.add(rc)
            out.append(c)
    return out


def _looks_like_harness(d):
    """Firma de un harness (NO de un cerebro): front.py + dispatch.py en la raíz.
    Un cerebro tiene BOOT/ + STATE/ + BRAIN.md (o CLAUDE.md) y NO estos scripts → nunca se
    confunde con uno (misma prueba que uninstall._is_harness)."""
    return all(os.path.isfile(os.path.join(d, f))
               for f in ("front.py", "dispatch.py"))


def detect_legacy_harness():
    """Detecta la instalación anterior (harness viejo) en ESTA máquina. Solo lectura.
    Devuelve dict:
      · 'folders'   : [rutas] que SON un harness (front.py+dispatch.py) → retirables
      · 'state'     : su estado per-máquina bajo ~/.claude si existe ('' si no)
      · 'launchers' : [rutas] de su comando en ~/.local/bin
      · 'ambiguous' : [rutas] que existen pero NO parecen harness → SOLO avisar
    'ambiguous' JAMÁS se borra (podría ser datos del usuario): ante la duda, avisar."""
    folders, ambiguous = [], []
    for c in _legacy_root_candidates():
        if os.path.isdir(c):
            (folders if _looks_like_harness(c) else ambiguous).append(os.path.abspath(c))
    state = os.path.join(HOME, ".claude", legacy.STATE_SUBDIR)
    state = state if os.path.isdir(state) else ""
    launchers = []
    bindir = os.path.join(HOME, ".local", "bin")
    for fn in legacy.LAUNCHERS[:2]:                   # comando + .cmd
        p = os.path.join(bindir, fn)
        if os.path.isfile(p):
            launchers.append(p)
    return {"folders": folders, "state": state, "launchers": launchers,
            "ambiguous": ambiguous}


def legacy_present(info):
    return bool(info["folders"] or info["state"] or info["launchers"]
                or info["ambiguous"])


def offer_retire_legacy(info=None, *, assume_yes=False):
    """Ofrece RETIRAR la instalación anterior. SEGURIDAD N1: no borra NADA sin
    confirmación EXPLÍCITA. Lista EXACTAMENTE qué se quita y de dónde; si el socio no
    confirma (o no es interactivo), NO toca nada. Los 'ambiguous' solo se avisan
    (nunca se borran). `assume_yes` (flag --retire-legacy) permite el camino no
    interactivo consciente. Respeta --dry-run. Devuelve True si retiró algo."""
    info = info or detect_legacy_harness()
    if not legacy_present(info):
        return False
    say("")
    say(f"{B}Encontré restos de la instalación anterior (el harness con el nombre viejo).{R}")
    removable = []
    for d in info["folders"]:
        say(f"    · carpeta del harness viejo:  {d}")
        removable.append(("carpeta del harness viejo", d))
    if info["state"]:
        say(f"    · estado per-máquina viejo:   {info['state']}")
        removable.append(("estado per-máquina viejo", info["state"]))
    for p in info["launchers"]:
        say(f"    · comando anterior:           {p}")
        removable.append(("comando anterior", p))
    for d in info["ambiguous"]:
        say(f"    · {DIM}(no parece un harness — NO lo toco, solo aviso): {d}{R}")
    if not removable:
        say(f"{DIM}  Nada seguro que retirar automáticamente. Revísalo a mano si quieres.{R}")
        return False
    say(f"{DIM}  WORKSPACE ya lo reemplaza. Puedo RETIRARLO: borro SOLO esos artefactos del "
        f"harness viejo.{R}")
    say(f"{DIM}  Tus CEREBROS (carpetas de agentes) y tus transcripts NO se tocan.{R}")
    if DRY:
        for lbl, p in removable:
            dry(f"retiraría {lbl}: {p}")
        return False
    if not assume_yes:
        try:
            interactive = sys.stdin.isatty()
        except Exception:
            interactive = False
        if not interactive:
            say(f"{DIM}  (no-interactivo: NO retiro nada. Corre el instalador en una terminal, "
                f"o pásale --retire-legacy para retirarlo.){R}")
            return False
        try:
            r = input("  Escribe 'retirar' para quitarlo, o Enter para dejarlo como está: ").strip().lower()
        except EOFError:
            r = ""
        if r not in ("retirar", "si", "sí", "s", "yes", "y"):
            say("  Lo dejo como está — no toqué nada.")
            return False
    # U06: retirar = MOVER a un respaldo recuperable (manifest + sha256) vía
    # migrate_legacy.retire_paths — nunca borrado directo. Las rutas protegidas
    # (cerebros, HOME, estado de Workspace, transcripts) se saltan ahí mismo.
    import migrate_legacy
    labels = {p: lbl for lbl, p in removable}
    bdir, done_paths, skipped = migrate_legacy.retire_paths([p for _l, p in removable],
                                                            op="install-retire")
    for p in done_paths:
        ok(f"retirado {labels.get(p, '')}: {p}")
    for p, why in skipped:
        say(f"{DIM}no retiré {p} ({why}) — revísalo a mano{R}")
    if done_paths:
        ok("instalación anterior retirada. Sigues solo con WORKSPACE.")
        say(f"{DIM}  respaldo recuperable: {bdir}  (deshacer: {migrate_legacy.CLI} "
            f"--rollback \"{bdir}\"){R}")
    return bool(done_paths)


def main():
    print(f"\n  {B}{C}Instalador de WORKSPACE{R}  {DIM}· {platform.system()} · {WORKSPACE}{R}"
          + (f"  {DIM}(DRY-RUN){R}" if DRY else "") + "\n")
    check_prereqs()

    # Guard anti-envenenamiento (mismo espíritu que el hard-block de OneDrive):
    # este checkout es un git WORKTREE secundario → los launchers/hooks hornearían
    # rutas absolutas a un árbol temporal que luego se borra (hub muerto). No se
    # instala desde aquí; el instalador corre desde el checkout principal.
    if running_from_worktree() and os.environ.get(FORCE_ENV) != "1":
        print(f"\n  {C}✗{R} Este WORKSPACE es un git WORKTREE (checkout secundario):")
        print(f"    {WORKSPACE}")
        print(f"  Los launchers/hooks hornean RUTAS ABSOLUTAS — instalados desde un "
              f"worktree quedarían")
        print(f"  apuntando a un árbol temporal. Corre el instalador desde el checkout "
              f"principal.")
        print(f"  {DIM}(override consciente: {FORCE_ENV}=1){R}\n")
        sys.exit(2)

    # Re-install inteligente (QoL · idempotencia): si ya había una instalación en
    # esta máquina, decirlo — re-correr el instalador NO duplica ni re-clona, solo
    # actualiza lo que cambió (RMW en configure_brain + launchers/greeter idempotentes).
    _ver = workspace_version()
    _prior = prior_install_markers()
    # «Nueva» = sin estado de Workspace NI de la instalación anterior: quien trae
    # restos viejos necesita que sus ajustes (p. ej. traer agentes) SÍ corran.
    _fresh = (not _prior and not os.path.isdir(_paths.state_dir(HOME))
              and not os.path.isdir(os.path.join(HOME, ".claude", legacy.STATE_SUBDIR)))
    if _prior:
        say(f"Ya tenías WORKSPACE instalado{f' ({_ver})' if _ver else ''} "
            f"en esta máquina.")
        say(f"{DIM}Re-ejecutar es seguro: actualizo lo que cambió, nada se duplica "
            f"({', '.join(l for l, _ in _prior)}).{R}\n")
    elif _ver:
        say(f"{DIM}Instalando WORKSPACE {_ver}.{R}\n")

    reg = registry()
    agents = reg.get("agents", [])
    if not agents:
        # Harness VACÍO (recién descargado/separado) = estado VÁLIDO. NO abortar:
        # igual instalamos el SETUP BASE (comando `workspace`, greeter, socio) — es
        # justo lo que se necesita para luego "Agregar agente". Solo se salta el
        # loop per-agente (no hay agentes committeados; los cargados van por
        # agents.local.json). Antes esto retornaba temprano y dejaba a un harness
        # nuevo SIN el comando workspace (bug de deploy).
        try:
            import dispatch
            loaded = [a for a in dispatch.load_registry().get("agents", [])
                      if a.get("_loaded")]
        except Exception:
            loaded = []
        print("  Harness vacío — instalo la base (comando `workspace`, greeter)."
              + (" %d agente(s) cargado(s) ya operativo(s)." % len(loaded) if loaded
                 else " Después: abre `workspace` → Agregar agente."))
    socio = ask_socio()          # "" salvo `--socio <slug>` explícito
    if socio:
        ok(f"socio: {socio}")
        write_machine_socio(socio)   # identidad per-máquina (chat desde el menú)

    # P0-4 · guard de OneDrive/known-folders (SOLO detección, jamás auto-move).
    # El harness bajo una ruta sincronizada a la nube = locks/latencia/estado
    # per-máquina pisado → fallos intermitentes. Hard-block ruidoso: no instalamos
    # sobre una base inestable. (Mac/Linux: redirected_root devuelve "" → no-op.)
    root_redir = pathguard.redirected_root(WORKSPACE)
    if root_redir:
        print(f"\n  {C}✗{R} WORKSPACE vive en una ruta redirigida a la nube ({root_redir}):")
        print(f"    {WORKSPACE}")
        print(f"  Muévelo FUERA de OneDrive — a %LOCALAPPDATA%\\Workspace o C:\\Workspace — "
              f"y vuelve a correr el instalador.")
        print(f"  {DIM}OneDrive sincroniza y BLOQUEA los archivos del harness (locks, "
              f"latencia, estado per-máquina) → fallos intermitentes.{R}\n")
        sys.exit(2)

    # INSTALACIÓN ANTERIOR (harness con el nombre viejo, pre-rename): si quedó en la
    # máquina, ofrecer retirarlo y seguir solo con WORKSPACE. SEGURIDAD N1: jamás
    # borra sin un 'retirar' explícito (o --retire-legacy consciente), jamás cerebros.
    # Opt-out total con --no-retire-legacy (automatización/tests).
    if "--no-retire-legacy" not in sys.argv:
        offer_retire_legacy(assume_yes="--retire-legacy" in sys.argv)

    agent_names, zenith_brain, discovered = [], None, {}
    for a in agents:
        name = a["name"]
        cfg = agent_cfg(a.get("dir", name))
        brain, persist = find_brain(name, cfg)
        if not brain or not os.path.isdir(brain):
            print(f"  {C}!{R} no encontré el cerebro de '{name}'. Sáltalo y defínelo luego en")
            print(f"    {paths_local()}  → {{\"brains\": {{\"{name}\": \"/ruta\"}}}}")
            continue
        # P0-4 · cerebro en ruta redirigida a la nube → SKIP (no abortar toda la
        # corrida: un cerebro malo no debe tumbar a los demás). Detección, jamás move.
        brain_redir = pathguard.redirected_root(brain)
        if brain_redir:
            up = name.upper()
            print(f"  {C}!{R} '{name}' vive en una ruta redirigida a la nube "
                  f"({brain_redir}): lo SALTO (no lo configuro).")
            print(f"    {brain}")
            print(f"    Muévelo a C:\\{up} - BRAIN (fuera de OneDrive) y vuelve a correr el "
                  f"instalador, o decláralo en {paths_local()}.")
            continue
        if persist:
            discovered[name] = brain
            ok(f"[{name}] cerebro detectado: {brain}")
        configure_brain(name, cfg, brain, socio)   # instala el tema por-agente internamente
        agent_names += [name] + [x for x in a.get("aliases", []) if x != name]
        # Guía de migración desde Cowork: la decide el CEREBRO (trae su
        # MIGRACION.md), no el nombre del agente (U12: sin roster del equipo).
        if not zenith_brain and os.path.isfile(
                os.path.join(brain, "assets", "brand", "MIGRACION.md")):
            zenith_brain = (name, brain)

    if discovered:                                  # guarda rutas per-máquina (fuera del vault)
        pl = paths_local()
        cur = read_json(pl) if os.path.exists(pl) else {}
        cur.setdefault("brains", {}).update(discovered)
        write_json(pl, cur)
        ok(f"rutas de cerebros guardadas (per-máquina): {pl}")

    # Agentes ya CARGADOS per-máquina (cerebros autocontenidos con
    # `<brain>/.workspace/agent.json` que el usuario conectó explícitamente antes).
    # Los re-configuramos por si el harness se reinstaló. NO auto-descubrimos del
    # disco: el harness se distribuye a clientes y debe quedar VACÍO salvo lo que el
    # usuario haya conectado a propósito (Agregar agente). Falla-suave.
    if not DRY:
        try:
            import agentsreg
            committed_names = {a["name"] for a in agents}
            for la in agentsreg.agents():
                if la["name"] in committed_names:
                    continue                         # ya configurado por el loop committeado
                brain = la["brain"]
                if not os.path.isdir(brain):
                    continue
                lcfg = agentsreg.load_definition(brain) or {"name": la["name"]}
                configure_brain(la["name"], lcfg, brain, socio)   # tema por-agente incluido
                agent_names += [la["name"]] + [x for x in lcfg.get("aliases", [])
                                               if x != la["name"]]
        except Exception as e:
            say(f"{DIM}aviso: no pude configurar agentes cargados ({e}){R}")

    install_launchers(list(dict.fromkeys(agent_names)))
    install_greeter()
    # Terminal-only (decisión de producto, 2026-10): instalar/actualizar NO crea
    # ninguna .app (ni en ~/Desktop ni en /Applications). WORKSPACE vive como
    # comando de terminal (`workspace`/`workspace`) apuntando al fuente del repo.
    # Quien quiera la app de escritorio la pide EXPLÍCITO:
    #   python3 install.py --desktop-app        (applet Terminal en ~/Desktop)
    #   bash dist/make-app.sh                   (wrapper del dev panel, queda en dist/)
    if "--desktop-app" in sys.argv:
        install_desktop_app()
    ensure_cleanup_days()
    # Instalación NUEVA en esta máquina: el instalador ya dejó todo en el
    # formato actual → se sellan las migraciones existentes como aplicadas
    # (si no, correrían historia que no hace falta). Una máquina que YA tenía
    # Workspace no se sella: sus ajustes pendientes deben correr (migrate.py).
    if _fresh and not DRY:
        try:
            import migrate
            migrate.mark_all("first-install", home=HOME)
        except Exception:
            pass

    _names = list(dict.fromkeys(agent_names))
    _direct = f" (o {B}{_names[0]}{R} para ir directo)" if _names else ""
    print(f"\n  {C}Listo.{R} Abre una terminal nueva y escribe {B}workspace{R}{_direct}.")
    if not _names:
        print(f"  {DIM}El menú sale vacío → 'Agregar agente' (crear o cargar un cerebro).{R}")
    print(f"  {DIM}Requiere: Python 3 y el CLI del motor que vayas a usar (Claude Code, "
          f"Codex, Antigravity, OpenCode, OpenClaw o Hermes) con sesión iniciada.{R}")
    if zenith_brain:
        print(f"\n  {DIM}¿Vienes de Cowork? Corre {R}{B}{zenith_brain[0]} migrar{R}{DIM} y luego di "
              f'"listo, procesa mi migración". Guía: assets/brand/MIGRACION.md en tu cerebro{R}')
    if DRY:
        print(f"\n  {DIM}(DRY-RUN: no se escribió nada. Quita --dry-run para instalar.){R}")
    print()


# ── CLI: `--help` jamás instala; un argumento desconocido tampoco ─────────────
_USO = ("uso: python3 install.py [--socio <nombre>] [--dry-run] [--desktop-app]\n"
        "                         [--retire-legacy | --no-retire-legacy]\n"
        "  Instala Workspace en esta máquina: el comando `workspace`, un comando por\n"
        "  agente, hooks, permisos y tema. Re-correrlo es seguro: solo actualiza.\n"
        "  --socio <nombre>   quién usa esta máquina (llena los cerebros sin dueño)\n"
        "  --dry-run          muestra qué haría, sin escribir nada\n"
        "  --desktop-app      además, la app de escritorio (Mac)\n"
        "  --retire-legacy    retira la instalación anterior sin preguntar\n"
        "  --no-retire-legacy no la toca")
_FLAGS = ("--dry-run", "--desktop-app", "--retire-legacy", "--no-retire-legacy")


def _args_desconocidos(argv):
    """Argumentos que el instalador no conoce ([] si todos valen). `--socio`
    lleva su valor aparte o con `=`."""
    malos, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--socio" and i + 1 < len(argv):
            i += 1
        elif a not in _FLAGS and not a.startswith("--socio="):
            malos.append(a)
        i += 1
    return malos


def cli(argv=None):
    """Entrada de `python3 install.py …`. `--help`/`-h`: el uso y salir 0 SIN
    escribir nada (antes ignoraba el flag e instalaba completo, también sobre
    el HOME real de quien solo pedía ayuda). Un argumento desconocido (p. ej. el
    socio por posición de versiones viejas) sale con error y no instala."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print(_USO)
        return 0
    malos = _args_desconocidos(argv)
    if malos:
        sys.stderr.write("install.py: argumento desconocido: %s — no se instaló nada.\n%s\n"
                         % (" ".join(malos), _USO))
        return 2
    main()
    return 0


if __name__ == "__main__":
    sys.exit(cli())
