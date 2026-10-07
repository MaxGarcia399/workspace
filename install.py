#!/usr/bin/env python3
# ════════════════════════════════════════════════════════════════════════════
#  WORKSPACE — instalador per-máquina del harness.
#  Cada socio lo corre UNA vez:   python3 install.py [max|fer|mau] [--dry-run]
#  Deja listos:
#    · `workspace`  → puerta del harness (banner + menú de agentes)
#    · un comando por agente (`zenith`, …) → abre ese agente directo
#    · hooks por cerebro: contexto al entrar (SessionStart) + captura al cerrar
#      (SessionEnd, red de seguridad de WORKSPACE) + marcador de inicio
#    · permisos sin fricción, status line, tema azul
#  Los scripts viven en los vaults sincronizados (WORKSPACE + cerebros); aquí solo
#  se escribe lo específico de la máquina. Mac y Windows. Cero dependencias.
# ════════════════════════════════════════════════════════════════════════════
import os, re, sys, json, shlex, platform, stat

WORKSPACE = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)
import events   # noqa: E402  (contrato de eventos N9 — build_hooks deriva de él)
import pathguard  # noqa: E402  (P0-4 — detección de rutas redirigidas a OneDrive)
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

ALLOW = ["Bash", "BashOutput", "KillShell", "Read", "Write", "Edit", "NotebookEdit",
         "Glob", "Grep", "WebFetch", "WebSearch", "Task", "TodoWrite", "Skill",
         "SlashCommand", "mcp__claude_ai_Shopify"]


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
    return os.path.join(HOME, ".claude", "workspace", "paths.local.json")


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


def find_brain(name, cfg):
    """Devuelve (ruta, persistir). persistir=True → guardar en paths.local.json."""
    ov = read_json(paths_local()).get("brains", {})
    if name in ov and os.path.isdir(os.path.expanduser(ov[name])):
        return os.path.abspath(os.path.expanduser(ov[name])), False
    raw = cfg.get("brain", "")
    if raw:
        cand = raw if os.path.isabs(raw) else os.path.abspath(os.path.join(WORKSPACE, raw))
        if os.path.isdir(cand):                      # hermanos (cualquier carpeta)
            return cand, False
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
    try:                                             # último recurso: preguntar
        ans = os.path.expanduser(input(f"  Pega la ruta de la carpeta '{target or name}': ").strip())
    except EOFError:
        ans = ""
    if ans and os.path.isdir(ans):
        return os.path.abspath(ans), True
    return "", False


def _within(path, *roots):
    """True si `path` (resuelto) está CONTENIDO en alguno de `roots`. Defensa de
    seguridad: los scripts de un agent.json se hornean como hooks/statusLine; un
    cerebro malicioso (auto-descubierto) NO debe poder apuntar a un script fuera de
    su propio cerebro o del harness (p.ej. /tmp/evil.py o {brain}/../../evil.py)."""
    rp = os.path.realpath(path)
    for r in roots:
        if not r:
            continue
        rr = os.path.realpath(r)
        if rp == rr or rp.startswith(rr + os.sep):
            return True
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


# Socio/dueño: el equipo son defaults conocidos, pero un agente puede tener un
# dueño EXTERNO (cualquier persona) — la validación acepta cualquier slug válido, no
# solo el trío. (D3 del protocolo de creación de agentes: dueños externos.)
TEAM = ("max", "fer", "mau")
SOCIO_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def ask_socio():
    args = sys.argv[1:]
    # dueño externo no-interactivo: flag EXPLÍCITO --socio <slug> / --socio=<slug>
    for i, a in enumerate(args):
        if a.startswith("--socio="):
            v = a.split("=", 1)[1].lower()
            if SOCIO_RE.match(v):
                return v
        if a == "--socio" and i + 1 < len(args) and SOCIO_RE.match(args[i + 1].lower()):
            return args[i + 1].lower()
    # match POSICIONAL solo del trío del equipo — NO capturar subcomandos (doctor/
    # eval/update…) como socio: todos pasan SOCIO_RE pero NO son dueños (bug D3).
    for a in args:
        if a.lower() in TEAM:
            return a.lower()
    guess = (os.environ.get("USER") or os.environ.get("USERNAME") or "").strip().lower()
    if not SOCIO_RE.match(guess):                     # usuario del SO como guess genérico (no horneado)
        guess = ""
    try:
        r = input(f"  ¿Quién eres? (tu nombre)"
                  f"{f' [{guess}]' if guess else ''}: ").strip().lower()
    except EOFError:
        r = ""
    r = r or guess
    return r if SOCIO_RE.match(r) else "owner"


def machine_socio_path():
    """socio.local PER-MÁQUINA (~/.claude/workspace/socio.local) — identidad
    del chat cuando NO hay cerebro activo (la TUI se abre desde el menú
    `workspace` con cwd=$HOME, antes de elegir agente). chat.self_ids cae aquí
    tras el socio.local del cerebro activo y el del cerebro de equipo."""
    return os.path.join(HOME, ".claude", "workspace", "socio.local")


def write_machine_socio(socio):
    """Escribe la identidad per-máquina (cualquier slug válido — soporta dueños
    externos, no solo el trío). El doctor la repara con la misma función.
    Respeta --dry-run vía write_text."""
    if socio and SOCIO_RE.match(socio):
        write_text(machine_socio_path(), socio)


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


def ensure_gitignore(brain, lines):
    gi = os.path.join(brain, ".gitignore")
    cur = open(gi, encoding="utf-8").read() if os.path.exists(gi) else ""
    add = [ln for ln in lines if ln not in cur]
    if not add or DRY:
        if add:
            dry(f"agregaría a {gi}: {', '.join(add)}")
        return
    with open(gi, "a", encoding="utf-8") as f:
        if cur and not cur.endswith("\n"):
            f.write("\n")
        f.write("\n".join(add) + "\n")


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
                   "skills/**/.usage.json.lock*"]


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
def configure_brain(name, cfg, brain, socio):
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
    # permisos: solo en el PRIMER install (si faltan). En re-install NO se pisan
    # — el socio pudo ajustarlos (espejo de la regla dura del doctor).
    settings.setdefault("permissions", {"defaultMode": "dontAsk", "allow": ALLOW})
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
    write_text(os.path.join(brain, ".claude", "socio.local"), socio)
    ensure_gitignore(brain, GITIGNORE_LINES)

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
    cands = [os.path.join(WORKSPACE, "themes-cc", f"{name}.json"),
             os.path.join(brain, "assets", "brand", f"{name}-theme.json")]
    if name == "zenith":
        cands.append(os.path.join(brain, "assets", "brand", "zenith-theme.json"))
    src = next((c for c in cands if os.path.exists(c)), "")
    if not src:
        return ""
    write_text(os.path.join(HOME, ".claude", "themes", f"{name}.json"),
               open(src, encoding="utf-8").read())
    ok(f"tema '{name}' instalado (~/.claude/themes/{name}.json)")
    return name


# ── retención de transcripts (runbook windows-support §4.5 — aplica a TODA máquina) ──
CLEANUP_DAYS = 3650


def ensure_cleanup_days():
    """~/.claude/settings.json → cleanupPeriodDays ≥ 3650. Claude Code borra los
    transcripts crudos a los 30 días por default y son la materia prima de la
    memoria. Merge sin pisar otras keys; nunca BAJA un valor ya mayor.
    Cross-platform a propósito (el runbook lo manda por máquina, Mac incluido).
    Devuelve True si escribió algo."""
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
    # revierta — no dejamos retención de 10 años a perpetuidad tras desinstalar.
    pre_path = os.path.join(HOME, ".claude", "workspace", "pre-install.json")
    if not DRY and not os.path.exists(pre_path):
        os.makedirs(os.path.dirname(pre_path), exist_ok=True)
        json.dump({"cleanupPeriodDays": s.get("cleanupPeriodDays")},
                  open(pre_path, "w", encoding="utf-8"))
    cur = s.get("cleanupPeriodDays")
    if isinstance(cur, (int, float)) and not isinstance(cur, bool) and cur >= CLEANUP_DAYS:
        return False
    s["cleanupPeriodDays"] = CLEANUP_DAYS
    write_json(sp, s)
    ok(f"cleanupPeriodDays={CLEANUP_DAYS} en ~/.claude/settings.json "
       "(los transcripts crudos ya no se borran a los 30 días)")
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
def launcher_unix(name, script, lead=""):
    path = os.path.join(HOME, ".local", "bin", name)
    body = f'''#!/bin/bash
# WORKSPACE · comando `{name}`
PY="{PY}"
exec "$PY" "{script}" {lead}"$@"
'''
    write_text(path, body)
    if not DRY:
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    ok(f"comando `{name}` instalado ({path})")


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
    if os.path.normcase(HOME) != os.path.normcase(_REAL_HOME):
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

    write_text(os.path.join(bindir, "workspace.cmd"), shim(front))
    write_text(os.path.join(bindir, "workspace.cmd"), shim(front))      # alias
    for name in agents:
        write_text(os.path.join(bindir, f"{name}.cmd"), shim(disp, name))
    ok(f"shims .cmd para cmd.exe/VS Code/PowerShell: {bindir} "
       f"(workspace + workspace + {len(agents)} agente(s))")


def launchers_windows(agents):
    lines = ["# WORKSPACE · comandos (dot-source desde tu $PROFILE)"]
    front = os.path.join(WORKSPACE, "front.py")
    disp = os.path.join(WORKSPACE, "dispatch.py")
    # `workspace` es el comando; `workspace` queda como ALIAS permanente (memoria
    # muscular del equipo + todo lo que ya lo invoca: greeter viejo, docs, hooks).
    lines.append(f'function workspace {{ & "{PY}" "{front}" @args }}')
    lines.append(f'function workspace {{ & "{PY}" "{front}" @args }}')
    for name in agents:
        lines.append(f'function {name} {{ & "{PY}" "{disp}" {name} @args }}')
    p = os.path.join(HOME, ".claude", "workspace-cmds.ps1")
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
    win_cmd_shims(agents)


PATH_MARK = "# WORKSPACE · PATH (~/.local/bin)"


def ensure_path_zshrc():
    """Asegura ~/.local/bin en el PATH vía ~/.zshrc, idempotente. Se llama ANTES de
    install_greeter() para que el bloque del PATH quede ARRIBA del greeter — si no, el
    greeter corre con `command -v workspace` fallando y el menú no sale (bug del deploy)."""
    rc = os.path.join(HOME, ".zshrc")
    cur = open(rc).read() if os.path.exists(rc) else ""
    if PATH_MARK in cur:
        return
    if DRY:
        dry(f"agregaría ~/.local/bin al PATH en {rc}")
        return
    with open(rc, "a") as f:
        f.write(f'\n{PATH_MARK}\nexport PATH="$HOME/.local/bin:$PATH"\n')
    ok("PATH: ~/.local/bin agregado a ~/.zshrc (reinicia la terminal o `source ~/.zshrc`)")


def install_launchers(agent_names):
    if global_writes_blocked("shims/launchers"):
        return
    if IS_WIN:
        launchers_windows(agent_names)
        return
    launcher_unix("workspace", os.path.join(WORKSPACE, "front.py"))
    launcher_unix("workspace", os.path.join(WORKSPACE, "front.py"))       # alias
    for name in agent_names:
        launcher_unix(name, os.path.join(WORKSPACE, "dispatch.py"), lead=f"{name} ")
    bindir = os.path.join(HOME, ".local", "bin")
    if bindir not in os.environ.get("PATH", "").split(os.pathsep):
        ensure_path_zshrc()


# Greeter de Windows (versionado: subir vN cuando cambie el bloque → install/doctor
# reemplazan el viejo). Guard ROBUSTO: solo sesión interactiva ([Environment]::
# UserInteractive) — funciona en CUALQUIER consola (Windows Terminal, consola clásica,
# VS Code, pwsh), no solo Windows Terminal; un $PROFILE cargado por un script/pipe no
# es UserInteractive y no lanza el menú. Al volver del menú se mandan los OSC 110/111/112
# para que la terminal no quede teñida por el tema del agente.
WIN_GREETER_MARK = "# WORKSPACE-greeter v3"
WIN_GREETER_BLOCK = (
    '# WORKSPACE-greeter v3 — menú al abrir terminal, cualquier consola interactiva '
    '(opt-out: $env:WORKSPACE_NO_GREETER=1; el guard WORKSPACE_GREETER se setea solo '
    'mientras corre workspace y se QUITA en finally, para NO heredarlo a terminales '
    'abiertas desde una sesion de Workspace — si no, su greeter nunca dispararia)\n'
    'if ([Environment]::UserInteractive '
    '-and -not $env:WORKSPACE_GREETER -and -not $env:WORKSPACE_NO_GREETER '
    '-and (Get-Command workspace -ErrorAction SilentlyContinue)) '
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


def install_greeter():
    """Al abrir una terminal, muestra el menú de WORKSPACE (agentes o terminal normal).
    Idempotente; se desactiva con WORKSPACE_NO_GREETER=1 o borrando el bloque."""
    if IS_WIN:
        # reemplaza cualquier versión vieja del bloque (sin guard de interactividad)
        prof = _ps_set_block(WIN_GREETER_MARK, WIN_GREETER_BLOCK,
                             legacy=("WORKSPACE-greeter", "WORKSPACE-greeter",
                                     "WORKSPACE_GREETER"))
        if prof:
            ok(f"greeter al día (Windows): menú al abrir Windows Terminal ({prof})")
        return
    rc = os.path.join(HOME, ".zshrc")
    cur = open(rc).read() if os.path.exists(rc) else ""
    if GREETER_MARK in cur:
        ok("greeter ya configurado (menú al abrir terminal)")
        return
    legacy = GREETER_MARK_V1 in cur
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
        with open(rc, "w") as f:
            NL = chr(10)
            f.write("".join(out).rstrip(NL) + NL + GREETER_BLOCK)
        ok("greeter actualizado: el menú WORKSPACE sale al abrir terminal "
           "(q = terminal normal)")
        return
    with open(rc, "a") as f:
        f.write(GREETER_BLOCK)
    ok("greeter agregado: el menú WORKSPACE sale al abrir terminal (q = terminal normal)")


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
    '# WORKSPACE-greeter v3 (autostart OFF — solo con el comando workspace)\n'
    'if ([Environment]::UserInteractive '
    '-and -not $env:WORKSPACE_GREETER -and -not $env:WORKSPACE_NO_GREETER '
    '-and (Get-Command workspace -ErrorAction SilentlyContinue)) '
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
    cur = open(rc).read() if os.path.exists(rc) else ""
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
        with open(rc, "w") as f:
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


def check_prereqs():
    """DEPLOY-7: avisa (no aborta) si faltan prerequisitos antes de configurar nada.
    Mejor un mensaje claro que un fallo más adelante. Python ya corre (este script)."""
    import shutil
    miss = []
    if not shutil.which("git"):
        miss.append("git (clónalo/instálalo: en Mac, las Command Line Tools)")
    if not shutil.which("claude"):
        miss.append("Claude Code CLI con sesión iniciada (claude.ai/code)")
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
    cands = [("estado per-máquina", os.path.join(HOME, ".claude", "workspace")),
             ("comando `workspace`", launcher)]
    return [(lbl, p) for lbl, p in cands if os.path.exists(p)]


# ── harness VIEJO del equipo (OLYMPUS / repo privada pre-rename) ─────────────
# Antes del rename OLYMPUS→WORKSPACE el harness del equipo se llamaba OLYMPUS.
# En una máquina del equipo pueden quedar: la carpeta del harness viejo
# (~/Desktop/OLYMPUS o $OLYMPUS_ROOT), su estado per-máquina (~/.claude/olympus) y
# el comando `olympus` en ~/.local/bin. Se OFRECE retirarlos para seguir solo con
# WORKSPACE. SEGURIDAD N1: jamás se borra sin confirmación EXPLÍCITA, y jamás un
# cerebro/datos del usuario — solo artefactos que SON el harness viejo.
def _olympus_root_candidates():
    cands = []
    env = os.environ.get("OLYMPUS_ROOT")
    if env:
        cands.append(os.path.expanduser(env))
    cands.append(os.path.join(HOME, "Desktop", "OLYMPUS"))
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
    Un cerebro tiene BOOT/ + STATE/ + CLAUDE.md y NO estos scripts → nunca se
    confunde con uno (misma prueba que uninstall._is_harness)."""
    return all(os.path.isfile(os.path.join(d, f))
               for f in ("front.py", "dispatch.py"))


def detect_legacy_harness():
    """Detecta el harness VIEJO del equipo (OLYMPUS) en ESTA máquina. Solo lectura.
    Devuelve dict:
      · 'folders'   : [rutas] que SON un harness (front.py+dispatch.py) → retirables
      · 'state'     : ~/.claude/olympus si existe ('' si no)
      · 'launchers' : [rutas] de comandos `olympus` en ~/.local/bin
      · 'ambiguous' : [rutas] que existen pero NO parecen harness → SOLO avisar
    'ambiguous' JAMÁS se borra (podría ser datos del usuario): ante la duda, avisar."""
    folders, ambiguous = [], []
    for c in _olympus_root_candidates():
        if os.path.isdir(c):
            (folders if _looks_like_harness(c) else ambiguous).append(os.path.abspath(c))
    state = os.path.join(HOME, ".claude", "olympus")
    state = state if os.path.isdir(state) else ""
    launchers = []
    bindir = os.path.join(HOME, ".local", "bin")
    for fn in ("olympus", "olympus.cmd"):
        p = os.path.join(bindir, fn)
        if os.path.isfile(p):
            launchers.append(p)
    return {"folders": folders, "state": state, "launchers": launchers,
            "ambiguous": ambiguous}


def legacy_present(info):
    return bool(info["folders"] or info["state"] or info["launchers"]
                or info["ambiguous"])


def offer_retire_legacy(info=None, *, assume_yes=False):
    """Ofrece RETIRAR el harness viejo (OLYMPUS). SEGURIDAD N1: no borra NADA sin
    confirmación EXPLÍCITA. Lista EXACTAMENTE qué se quita y de dónde; si el socio no
    confirma (o no es interactivo), NO toca nada. Los 'ambiguous' solo se avisan
    (nunca se borran). `assume_yes` (flag --retire-legacy) permite el camino no
    interactivo consciente. Respeta --dry-run. Devuelve True si retiró algo."""
    info = info or detect_legacy_harness()
    if not legacy_present(info):
        return False
    say("")
    say(f"{B}Encontré una instalación vieja del harness del equipo (OLYMPUS).{R}")
    removable = []
    for d in info["folders"]:
        say(f"    · carpeta del harness viejo:  {d}")
        removable.append(("carpeta del harness viejo", d))
    if info["state"]:
        say(f"    · estado per-máquina viejo:   {info['state']}")
        removable.append(("estado per-máquina viejo", info["state"]))
    for p in info["launchers"]:
        say(f"    · comando `olympus`:          {p}")
        removable.append(("comando `olympus`", p))
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
    import shutil
    done = 0
    for lbl, p in removable:
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
            ok(f"retirado {lbl}: {p}")
            done += 1
        except OSError as e:
            say(f"{DIM}no pude retirar {p} ({e}) — quítalo a mano{R}")
    if done:
        ok("harness viejo (OLYMPUS) retirado. Sigues solo con WORKSPACE.")
    return done > 0


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
    socio = ask_socio()
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

    # Harness VIEJO del equipo (OLYMPUS / repo privada pre-rename): si quedó en la
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
        if name == "zenith":
            zenith_brain = brain

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

    _names = list(dict.fromkeys(agent_names))
    _direct = f" (o {B}{_names[0]}{R} para ir directo)" if _names else ""
    print(f"\n  {C}Listo.{R} Abre una terminal nueva y escribe {B}workspace{R}{_direct}.")
    if not _names:
        print(f"  {DIM}El menú sale vacío → 'Agregar agente' (crear o cargar un cerebro).{R}")
    print(f"  {DIM}Requiere: Claude Code instalado y con sesión iniciada, y Python 3.{R}")
    if zenith_brain:
        print(f"\n  {DIM}¿Vienes de Cowork? Corre {R}{B}zenith migrar{R}{DIM} y luego di "
              f'"listo, procesa mi migración". Guía: assets/brand/MIGRACION.md en tu cerebro{R}')
    if DRY:
        print(f"\n  {DIM}(DRY-RUN: no se escribió nada. Quita --dry-run para instalar.){R}")
    print()


if __name__ == "__main__":
    main()
