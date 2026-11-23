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
    import _console; _console.ansi()  # ANSI en Windows 10+ (solo con consola: sin ella, os.system abría una ventana)
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


#: Comodines de gitignore que se escapan en la ruta del cerebro (doc de
#: permisos de Claude Code: las reglas Read/Edit usan la sintaxis de gitignore;
#: «Claude Code escapes gitignore pattern characters […] such as [, ], and *»).
_GITIGNORE_COMODINES = "\\[]*?"


def deny_protegidas(brain, windows=None):
    """Las reglas `deny` de Claude Code para la config de los motores, git y
    Obsidian del cerebro (rutas_protegidas). Doc oficial
    (https://code.claude.com/docs/en/permissions, «Read and Edit»): `Edit(…)`
    cubre Write y NotebookEdit; deny gana a cualquier allow. Dos formas:
      · relativa a la carpeta donde abre (Workspace abre en el cerebro): una
        carpeta de un solo nivel como deny cubre ese nombre a cualquier
        profundidad (`Edit(.kiro/**)`), y un archivo pelado también
        (`Edit(.mcp.json)`);
      · absoluta (`//` + la ruta, como brain_rules; Windows `//c/…`), con la
        ruta pedida y la real, por si la sesión abre en otra carpeta.
    Van en el settings.local.json del cerebro, JUNTO al allow de la autonomía
    (render_permissions), y en el `--settings` de cada pestaña
    (memoria.claude_settings_args) como respaldo: así también las respeta un
    `claude` abierto fuera del lanzador (VS Code, Desktop, `claude` a secas).
    Claude Code ya PREGUNTA por `.git`, `.claude`, `.vscode` y `.mcp.json`
    (doc «protected paths», https://code.claude.com/docs/en/permission-modes);
    el deny lo vuelve un no, como en los demás motores.
    MAYÚSCULAS: VERIFICADO 2026-11-06 en macOS (claude 2.1.319, proveedor
    Anthropic falso, HOME temporal; Write y Edit, modos default y
    acceptEdits): estas reglas tal cual niegan `.KIRO/agents/x.json`,
    `.Kiro/Agents/…`, `.OBSIDIAN/…` y `OpenCode.json`, relativas y absolutas
    (Claude Code compara sin distinguir mayúsculas en un disco que no las
    distingue). Las clases por letra (`.[kK][iI][rR][oO]/**`,
    rutas_protegidas.sin_mayusculas) también funcionan y quedan como
    respaldo si en Windows (A-VERIFICAR en la PC) no fuera así.
    LÍMITES documentados (sin verificar en caja negra): acceptEdits aprueba
    también `cp`/`mv`/`touch`… dentro de la carpeta (doc permission-modes) y
    no se sabe si esos comandos respetan los deny de `Edit`; un
    `bypassPermissions` puesto por settings recibe este deny igual (deny gana
    en todos los modos: falla del lado seguro)."""
    import rutas_protegidas as R
    try:
        cands = [brain] if windows else [os.path.abspath(brain), os.path.realpath(brain)]
        raices = []
        for p in cands:
            r = _rule_root(p, windows)
            if r not in raices:
                raices.append(r)
    except Exception:
        raices = []
    out = []
    for base in [""] + ["".join("\\" + c if c in _GITIGNORE_COMODINES else c for c in r) + "/"
                        for r in raices]:
        for d in R.CARPETAS:
            out.append("Edit(%s%s/**)" % (base, d))
        for f in R.ARCHIVOS + R.EXACTAS:
            out.append("Edit(%s%s)" % (base, f))
    return out


def deny_lectura(windows=None):
    """Las reglas `deny` de Claude Code que le niegan al agente LEER la bóveda
    de llaves de Workspace (rutas_protegidas.lectura_negada: `secrets.local`
    y sus temporales, la carpeta `boveda/`) y PEDIRLE un valor al llavero del
    sistema (rutas_protegidas.COMANDOS_LLAVERO). Doc oficial
    (https://code.claude.com/docs/en/permissions): `Read(//ruta)` es ABSOLUTA
    (`/ruta` con una sola barra es relativa a la config); Windows `//c/…`;
    `~/` también vale; deny gana en todos los modos, también
    bypassPermissions; un deny de Read aplica a Read/Grep/Glob y a los
    comandos de archivo que Claude Code reconoce en Bash (`cat`, `head`,
    `tail`, `sed`…), NO a un script cualquiera (eso solo lo frena su sandbox,
    que Workspace no prende). SIN VERIFICAR en caja negra (2026-11-08)."""
    import rutas_protegidas as R
    out = []

    def esc(r):
        return "".join("\\" + c if c in _GITIGNORE_COMODINES else c for c in r)
    for ruta, tipo in R.lectura_negada():
        cands = [ruta] if windows else [os.path.abspath(ruta), os.path.realpath(ruta)]
        for p in cands:
            r = esc(_rule_root(p, windows))
            reglas = (["Read(%s/**)" % r] if tipo == R.CARPETA
                      else ["Read(%s)" % r, "Read(%s.tmp-*)" % r])
            out += [x for x in reglas if x not in out]
    for rel, tipo in R.lectura_negada_relativa():
        x = "Read(~/%s/**)" % esc(rel) if tipo == R.CARPETA else "Read(~/%s)" % esc(rel)
        if x not in out:
            out.append(x)
    out += ["Bash(%s:*)" % c for c in R.COMANDOS_LLAVERO]     # el programa entero
    return out


def deny_workspace(brain, windows=None):
    """Todo el deny de Workspace para Claude Code: no escribir la config
    protegida del cerebro (deny_protegidas) y no leer la bóveda de llaves
    (deny_lectura)."""
    return deny_protegidas(brain, windows) + deny_lectura(windows)


def claude_permissions(autonomy, brain):
    """El bloque `permissions` que WORKSPACE quiere para esa autonomía. El deny
    de Workspace (deny_workspace: la config protegida del cerebro y la bóveda)
    va con TODA autonomía y vive en el mismo archivo que el allow, no solo en
    la sesión del lanzador: «ask» («Preguntarme todo») pide permiso para lo
    demás, pero no abre lo protegido. Hasta la cacería del 19-nov (B04), «ask»
    lo borraba entero (54 reglas: .git, hooks, settings, .mcp.json…)."""
    if autonomy == "ask":
        return {"allow": [], "deny": deny_workspace(brain)}
    return {"allow": brain_rules(brain), "deny": deny_workspace(brain)}


def _render_deny(new, cur, prev, want_deny):
    """`new["deny"]` = nuestro deny (`want_deny`) + el del usuario (lo que no
    está anotado en el marcador `prev`). Sin ninguno, sin la clave. Un `deny`
    que no es lista es del usuario: no se toca (→ False)."""
    ours = set(prev.get("deny") or []) if isinstance(prev, dict) else set()
    cur_deny = cur.get("deny", [])
    if not isinstance(cur_deny, list):
        return False
    extra = [r for r in cur_deny if not (isinstance(r, str) and (r in ours or r in want_deny))]
    deny = list(want_deny) + extra
    if deny:
        new["deny"] = deny
    else:
        new.pop("deny", None)
    return True


def render_permissions(settings, cfg, brain):
    """Escribe en `settings` (dict de settings.local.json) los permisos de la
    autonomía del agente: el allow y, con toda autonomía, el deny de Workspace
    (deny_workspace). Conserva lo que el usuario agregó: reglas
    propias en allow y deny, ask/additionalDirectories y un defaultMode que no
    sea el nuestro. Lo que WORKSPACE escribió antes (marcador, o la lista
    amplia de 0.2.x si no hay marcador) se reemplaza. Devuelve `settings`."""
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
    deny_ok = _render_deny(new, cur, prev, want["deny"])
    settings["permissions"] = new
    settings[_PERM_MARKER] = {"autonomy": autonomy, "allow": list(want["allow"]),
                              "deny": list(want["deny"]) if deny_ok else []}
    return settings


def completar_deny(settings, brain, autonomias=("brain",)):
    """Si `settings` (settings.local.json) trae los permisos que escribió
    Workspace (su marcador) con una de `autonomias`, deja su deny al día
    (deny_workspace) sin tocar nada más: ni el allow, ni el modo, ni lo del
    usuario. De fábrica, solo «brain»: lo que hace la migración publicada
    202611062300_claude_deny_protegidas (los cerebros que recibieron el allow
    antes de que el deny viviera en el archivo), que no se cambia. Con «ask»
    también (AUTONOMY_LEVELS), los que lo perdieron al pasar a «ask» (B04,
    cacería 19-nov): la migración 202611190700_claude_deny_en_preguntar y
    configure_brain (reinstalar, cargar un agente). → True si cambió algo."""
    prev = settings.get(_PERM_MARKER) if isinstance(settings, dict) else None
    if not isinstance(prev, dict) or prev.get("autonomy") not in autonomias:
        return False
    cur = settings.get("permissions")
    if not isinstance(cur, dict):
        return False
    want = deny_workspace(brain)
    new = dict(cur)
    if not _render_deny(new, cur, prev, want):
        return False
    mark = dict(prev, deny=list(want))
    if new == cur and mark == prev:
        return False
    settings["permissions"] = new
    settings[_PERM_MARKER] = mark
    return True


def apply_permissions(brain, cfg):
    """Reescribe SOLO el bloque `permissions` del settings.local.json del
    cerebro según `cfg["autonomy"]` (lo usa Agentes → Enter al cambiar los
    permisos). Lectura-modificación-escritura atómica y bajo el candado del
    archivo (candado_settings): hooks, tema y lo que agregó el usuario —o
    otra ventana un instante antes— quedan intactos. Un settings corrupto NO
    se toca. Devuelve (ok, motivo)."""
    spath = os.path.join(brain, ".claude", "settings.local.json")
    try:
        import olock
        with candado_settings(spath):
            if json_corrupt(spath):
                return False, "settings.local.json corrupto"
            settings = read_json(spath) if os.path.exists(spath) else {}
            if not isinstance(settings, dict):
                return False, "settings.local.json no es un objeto"
            render_permissions(settings, cfg, brain)
            os.makedirs(os.path.dirname(spath), exist_ok=True)
            tmp = "%s.tmp-%d" % (spath, os.getpid())
            try:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(settings, fh, ensure_ascii=False, indent=2)
                try:
                    import atomico          # reintenta si Windows tiene el archivo abierto
                    atomico.reemplazar(tmp, spath)
                except ImportError:
                    os.replace(tmp, spath)
            finally:
                if os.path.exists(tmp):     # nunca queda el temporal en el cerebro
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
    except olock.LockTimeout:
        return False, "otra ventana está cambiando settings.local.json; vuelve a intentar"
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
        # En Mac, sin entrar a Escritorio/Documentos/iCloud (salvo que Workspace
        # viva ahí): cada uno pide permiso a la app de terminal y esto corre
        # solo, al instalar/actualizar (aviso C1).
        try:
            import agentsreg
            bloqueada = agentsreg._bloqueo(WORKSPACE)
        except Exception:
            bloqueada = None
        for vp in obsidian_vaults():                 # registro de Obsidian (lo más fiable)
            if bloqueada is not None and bloqueada(vp):
                continue
            if os.path.basename(os.path.normpath(vp)) == target and os.path.isdir(vp):
                return os.path.abspath(vp), True
        # spots comunes
        for r in (os.path.dirname(WORKSPACE), HOME, _paths.brains_dir(HOME),
                  os.path.join(HOME, "Desktop"),
                  os.path.join(HOME, "Documents"), os.path.join(HOME, "Documents", "Obsidian"),
                  os.path.join(HOME, "Obsidian")):
            cand = os.path.join(r, target)
            if bloqueada is not None and bloqueada(cand):
                continue
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
    """¿Se le puede preguntar algo a la persona? Con la vista corta de la
    instalación (instalar_vista) no: lo que explica la pregunta va a la
    bitácora, así que se hace lo de no-interactivo (nada se borra ni se
    adivina) y `--detalle` deja preguntar con todo el texto a la vista."""
    if _VISTA is not None:
        return False
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
            say(f"{DIM}aviso seguridad: script '{k}' fuera del cerebro o de Workspace — ignorado: {p}{R}")
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


def write_identity(socio):
    """`--socio` también dice quién eres en ESTA máquina para todos tus
    cerebros (sesiones v2: identidad.json, identidad.py). Respeta --dry-run;
    falla-suave (un aviso, la instalación sigue)."""
    if not socio or not SOCIO_RE.match(socio):
        return
    if DRY:
        dry(f"guardaría quién eres en esta máquina ({socio}) en identidad.json")
        return
    try:
        import identidad
        identidad.fijar_persona(socio, origen="install --socio",
                                state_dir=_paths.state_dir(HOME))
    except Exception as e:
        say(f"{DIM}aviso: no pude guardar quién eres en esta máquina ({e}){R}")


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


class SettingsIlegible(Exception):
    """El settings.local.json existe pero no es JSON: quien repara no lo pisa."""


def candado_settings(spath, timeout=5):
    """EL candado de un settings.local.json: `olock.local_lock` sobre su
    `olock.ruta_candado` (`<cerebro>/.claude/locks/`, que Obsidian no sube).
    Todos los que ESCRIBEN ese archivo —install, doctor, repair, el motor de
    config, el tema por-motor, las migraciones— toman este mismo candado y
    hacen la lectura-cambio-guardado COMPLETA dentro: sin él, dos ventanas
    se pisaban la llave que la otra acababa de poner (permisos, mcpServers,
    hooks). Levanta olock.LockTimeout si otra ventana lo sostiene. En
    --dry-run no se toma (no se escribe)."""
    if DRY:
        import contextlib
        return contextlib.nullcontext()
    import olock
    return olock.local_lock(spath, timeout=timeout)


def _ilegible(spath):
    """¿El settings existe y NO se puede usar como objeto? Un archivo vacío (0
    bytes o solo espacios) no perdería nada al escribirlo; un JSON roto o que no
    es un objeto sí. «Ilegible no es vacío»."""
    if not os.path.exists(spath):
        return False
    try:
        with open(spath, encoding="utf-8") as fh:
            texto = fh.read()
    except Exception:
        return True
    if not texto.strip():
        return False
    if json_corrupt(spath):
        return True
    try:
        return not isinstance(json.loads(texto), dict)
    except Exception:
        return True


def apartar_ilegible(spath):
    """Mueve el settings ilegible a `<archivo>.ilegible-<fecha>` (se CONSERVA, no
    se borra) y devuelve la ruta del respaldo. Quien lo llama debe avisar."""
    import time as _time
    destino = "%s.ilegible-%s" % (spath, _time.strftime("%Y%m%d-%H%M%S"))
    n = 1
    while os.path.exists(destino):
        n += 1
        destino = "%s.ilegible-%s-%d" % (spath, _time.strftime("%Y%m%d-%H%M%S"), n)
    os.replace(spath, destino)
    return destino


def mutar_settings_local(spath, mutar, timeout=5, si_corrupto="abortar"):
    """Lee, cambia y guarda un settings.local.json bajo UN solo candado
    (candado_settings). `mutar(settings)` cambia el dict en su sitio; se llama
    con la lectura de DENTRO del candado, nunca con una copia vieja. Devuelve
    el dict guardado. `si_corrupto` (qué hacer si el archivo existe y no se
    puede leer como objeto JSON): "abortar" (POR DEFECTO: levanta
    SettingsIlegible y no escribe nada; permisos, variables y ajustes manuales
    siguen en el archivo) | "apartar" (lo mueve a `<archivo>.ilegible-<fecha>`,
    sin borrarlo, y parte de uno vacío; quien lo pide debe avisar al usuario).
    Levanta olock.LockTimeout si no consigue el candado."""
    if si_corrupto not in ("abortar", "apartar"):
        raise ValueError("si_corrupto: 'abortar' o 'apartar'")
    with candado_settings(spath, timeout):
        if _ilegible(spath):
            if si_corrupto == "abortar":
                raise SettingsIlegible(spath)
            if not DRY:
                apartar_ilegible(spath)
        settings = read_json(spath) if os.path.exists(spath) else {}
        if not isinstance(settings, dict):
            settings = {}
        mutar(settings)
        write_json(spath, settings)
    return settings


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
# → parsea idéntico en cmd.exe, git-bash o sh. PowerShell NO: ahí una cadena
# entre comillas al inicio es un valor, no un comando (ParserError «Token
# inesperado»); para él va la forma `powershell` (runner_cmd_powershell). Reemplaza al viejo
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


#: Caracteres que PowerShell toma como comilla simple (la recta y las
#: tipográficas): dentro de un literal '…' se escriben dobles.
_PS_QUOTES = "'\u2018\u2019\u201a\u201b"


def _ps_literal(s):
    """`s` como literal de PowerShell entre comillas simples: nada se expande
    (ni `$` ni la comilla invertida) y cada comilla simple va doble."""
    return "'" + "".join(c * 2 if c in _PS_QUOTES else c for c in str(s)) + "'"


def runner_cmd_powershell(event):
    """El MISMO comando del runner en sintaxis de PowerShell:
        & '<PY>' '<WORKSPACE>\\workspace_hook.py' <event>
    Va en la clave `powershell` de cada hook, SOLO en Windows (build_hooks).

    VERIFICADO 2026-11-05 (Windows 11, GitHub Copilot CLI 1.0.105 de WinGet,
    PowerShell 7.6.9): Copilot también corre los hooks de
    `.claude/settings*.json` del cerebro («repo settings»), en Windows con
    PowerShell: con solo `command` cada hook moría en «ParserError: Token
    inesperado» y, como `preToolUse` falla cerrado, TODA terminal salía
    «Denied by preToolUse hook from "repo settings" (hook errored)». Con esta
    clave Copilot la usa en lugar de `command` (la terminal corre y el hook
    recibe su JSON por stdin), y Claude Code 2.1.318 la ignora y sigue
    corriendo `command` con Git Bash (proveedores falsos locales, sin cuenta)."""
    return "& %s %s %s" % (_ps_literal(PY), _ps_literal(RUNNER), event)


GITIGNORE_LINES = [".claude/settings.local.json", ".claude/socio.local",
                   ".claude/zenith-workspaces.json",
                   # N12: el sidecar .usage.json SÍ se versiona (conteo de
                   # equipo); su lock N8 es estado per-máquina → fuera de git
                   "skills/**/.usage.json.lock*",
                   # revisión de skills (2026-10-16): la vista de la sesión
                   # que el agente revisa al abrir — per-máquina, fuera de git
                   ".claude/skill-review/",
                   # memoria v1: candados y bandeja de notas — per-máquina
                   ".claude/locks/", ".claude/memoria-entrada/",
                   # sesiones v2 (nivel 2): las conversaciones viajan por el
                   # sync del cerebro, NUNCA al espejo de git (pueden traer
                   # llaves pegadas). = conversaciones.GITIGNORE_LINE
                   "motores/*/conversaciones/",
                   # la herramienta MCP de memoria de Cursor, Kiro y Antigravity
                   # (memoria_mcp): Workspace pone ahí su entrada al abrir, con rutas de ESTA
                   # máquina (lo del socio en esos archivos queda tal cual)
                   ".cursor/mcp.json", ".cursor/cli.json", ".kiro/agents/workspace.json",
                   ".agents/mcp_config.json"]


def build_hooks(cfg, brain, launch=False):
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
    los hooks sin tocar permissions/theme.

    `launch=True`: el bloque de los eventos que se cablean POR ARRANQUE
    (events.POR_ARRANQUE: el Stop de la maleta), con el mismo runner, cotas y
    gate; lo mete memoria.claude_settings_args en el `--settings` de la
    pestaña. Por defecto (el cerebro) esos eventos no entran."""
    setup = events.setup_of(cfg)
    has_dashboard = bool(expand((cfg or {}).get("scripts"), brain).get("dashboard"))
    out = {}
    eventos = events.launch_events if launch else events.wired_events
    for ev in eventos("claude-code"):
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
            hook = {"type": "command", "command": runner_cmd(ev), "timeout": budget}
            if IS_WIN:      # Copilot corre estos hooks con PowerShell (runner_cmd_powershell)
                hook["powershell"] = runner_cmd_powershell(ev)
            group = {"hooks": [hook]}
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
    hooks = build_hooks(cfg, brain)                             # gestionado (derivado de N9)
    if not write:
        settings["hooks"] = hooks
        return settings
    # guard anti-envenenamiento: el runner_cmd hornea la ruta de ESTE
    # checkout — desde un worktree NO se persiste (el cerebro conserva sus
    # hooks canónicos); el dict mutado se devuelve igual para inspección.
    if global_writes_blocked("hooks de cerebros"):
        settings = read_json(spath) if os.path.exists(spath) else {}
        settings = settings if isinstance(settings, dict) else {}
        settings["hooks"] = hooks
        return settings
    return mutar_settings_local(spath, lambda st: st.__setitem__("hooks", hooks))


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
    """Legacy shape for Claude; unavailable connections have localized notes."""
    engine = (cfg.get("engine") or "claude-code").strip()
    if engine == "claude-code":
        return "claude-code", "official_cli", ""
    import config_engine
    note = config_engine.mcp_registration_note(generic=True)
    try:
        import connectors
        if engine in connectors.OFFICIAL_CLIS:
            return "", "official_cli", note
        import model_resolver
        provider, _errors = model_resolver.load_provider(engine)
        kind = connectors.connection_type(provider) if provider else ""
    except Exception:
        kind = ""
    return "", kind, note


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


def _mcp_manual_conflicts(settings, desired):
    """Names already present but not marked as owned; never adopt by name."""
    current = settings.get("mcpServers")
    if not isinstance(current, dict):
        return []
    marker = settings.get(_MCP_MARKER)
    owned = {name for name in marker if isinstance(name, str)} \
        if isinstance(marker, list) else set()
    return sorted(name for name in desired if name in current and name not in owned)


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
    # 2. A manual homonym is a conflict, even when its content is identical.
    conflicts = set(_mcp_manual_conflicts(settings, desired))
    for sname, server in desired.items():
        if sname not in conflicts:
            current[sname] = _claude_mcp_entry(server)
    # 3. persistir el bloque + el marcador; limpio si vacío (amputable)
    if current:
        settings["mcpServers"] = current
    elif "mcpServers" in settings:
        del settings["mcpServers"]
    owned_desired = sorted(name for name in desired if name not in conflicts)
    if owned_desired:
        settings[_MCP_MARKER] = owned_desired
    elif _MCP_MARKER in settings:
        del settings[_MCP_MARKER]
    return settings


def render_mcps_only(cfg, brain, *, settings=None):
    """Read the legacy settings only; do not create, update or remove MCPs.

    Claude Code does not discover MCPs in this target. The public entry point
    remains compatible while a new target awaits a product decision. The
    pure legacy projection helpers stay available for regression coverage.
    """
    if settings is not None:
        return settings
    spath = os.path.join(brain, ".claude", "settings.local.json")
    return read_json(spath) if os.path.exists(spath) else {}


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
    # un solo candado para toda la lectura-cambio-guardado (candado_settings):
    # otra ventana (doctor, repair, el tema, otro install) no se pisa con esta
    import olock
    try:
        with candado_settings(spath):
            # R3-F1 (read-guard): un settings CORRUPTO no se descarta en silencio —
            # se preserva como rastro (`.corrupt-<pid>`) y se avisa. El install es
            # acción explícita del socio y debe dejar un setup funcional, así que
            # sigue con un settings fresco; el rastro permite recuperar lo perdido.
            # (El doctor, que es reparación AUTOMÁTICA, directamente aborta — ver
            # doctor.phase_hooks.) Idempotencia intacta: un settings sano ni entra aquí.
            if _ilegible(spath):               # roto O no-objeto, el mismo criterio que mutar
                rastro = spath + ".corrupt-%d" % os.getpid()
                if DRY:
                    dry(f"respaldaría el settings corrupto en {rastro}")
                else:
                    try:
                        os.replace(spath, rastro)
                    except OSError:
                        rastro = "(no se pudo respaldar)"
                say(f"⚠ [{name}] settings.local.json era JSON corrupto o no era un objeto — respaldado en "
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
            else:
                # el allow «brain» de una versión anterior sin su deny, o un «ask» que
                # lo perdió (B04): se completa (solo el deny de Workspace; lo demás
                # queda como lo ajustaste)
                completar_deny(settings, brain, AUTONOMY_LEVELS)
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
    except olock.LockTimeout:
        say(f"⚠ [{name}] otra ventana está cambiando settings.local.json; no lo "
            f"toqué — vuelve a correr la instalación")
        return
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
        # sesiones v2: la lista de pestañas son los .md del cerebro (el json
        # local ya no agrega filas) → cada pestaña inicial lleva su .md
        if socio and not DRY:
            try:
                import sessions_registry
                for w in ws:
                    sessions_registry._seed_md(brain, w["name"], claude_wid=w["id"], soc=socio)
            except Exception:
                pass
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
    ok("Claude Code guarda tus conversaciones un año, no 30 días "
       "(en ~/.claude/settings.json)")
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
    ok("agregué una línea a ~/.zshrc para que tus terminales nuevas encuentren "
       "`workspace` (todo se quita con: workspace uninstall)")


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
    ok("cada terminal nueva abre Workspace (q = terminal normal; se apaga en "
       "Workspace › Personalización)" if block is GREETER_BLOCK
       else "Workspace abre solo con el comando workspace")


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


#: Motores soportados: (nombre que ve el socio, su CLI). Los avisos de
#: prerrequisitos y el cierre del instalador los nombran de aquí.
ENGINES = (("Claude Code", "claude"), ("Codex", "codex"), ("Antigravity", "agy"),
           ("OpenCode", "opencode"), ("OpenClaw", "openclaw"), ("Hermes", "hermes"),
           ("Kiro", "kiro-cli"), ("GitHub Copilot", "copilot"), ("Cursor", "cursor-agent"))
# CLIs de los motores (+ gemini, que ya no es motor: su lanzador viejo se reconoce).
ENGINE_CLIS = tuple(cli for _n, cli in ENGINES) + ("gemini",)


def engine_names():
    """«Claude Code, Codex, …, GitHub Copilot o Cursor» (los de ENGINES)."""
    nombres = [n for n, _cli in ENGINES]
    return ", ".join(nombres[:-1]) + " o " + nombres[-1]


def check_prereqs():
    """DEPLOY-7: avisa (no aborta) si faltan prerequisitos antes de configurar nada.
    Mejor un mensaje claro que un fallo más adelante. Python ya corre (este script)."""
    import shutil
    miss = []
    if not shutil.which("git"):
        miss.append("git (clónalo/instálalo: en Mac, las Command Line Tools)")
    # Motor: cualquiera de los que Workspace soporta (no siempre Claude Code).
    if not any(shutil.which(b) for b in ENGINE_CLIS):
        miss.append(f"el CLI del motor que vayas a usar ({engine_names()}), con sesión iniciada")
    for m in miss:
        say(f"{C}!{R} falta: {m}")
    if miss:
        say(f"{DIM}Puedes seguir, pero algunas piezas no funcionarán hasta resolverlo.{R}\n")


# ── detección de instalación previa / reinstalación (QoL · idempotencia) ─────
def version_visible():
    """La versión que ve la persona: la del archivo VERSION (p. ej. «0.9.2»).
    Sin VERSION, el sha corto de siempre; '' si no hay ninguna. Fail-soft."""
    try:
        with open(os.path.join(WORKSPACE, "VERSION"), encoding="utf-8") as fh:
            v = fh.read().strip()
        if v:
            return v
    except Exception:
        pass
    return workspace_version()


def greeter_de_fabrica(nueva):
    """Instalación NUEVA (Mac y Linux): el arranque queda ENCENDIDO de fábrica
    —cada terminal nueva abre Workspace— sin preguntarlo en el primer arranque
    (decisión del dueño: greeter ON por defecto; F0 del onboarding nuevo lo sacó
    de la bienvenida). Solo si nadie eligió antes (sin ui.autostart guardado);
    se cambia después en Personalización. Devuelve True si lo dejó encendido.
    Windows sigue con el de siempre hasta su paso de paridad."""
    if not nueva or IS_WIN or DRY:
        return False
    try:
        import settings
        if settings.get_stored("ui.autostart") is not None:
            return False
        settings.set("ui.autostart", True)
        return True
    except Exception:
        return False


def greeter_abre():
    """¿El ~/.zshrc trae hoy el greeter que abre Workspace? (Mac y Linux)."""
    if IS_WIN:
        return False
    try:
        with open(os.path.join(HOME, ".zshrc"), encoding="utf-8") as fh:
            cur = fh.read()
        return GREETER_MARK in cur and _zsh_greeter_full(cur)
    except Exception:
        return False


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
    say(f"{B}Encontré restos de la instalación anterior (Workspace con el nombre viejo).{R}")
    removable = []
    for d in info["folders"]:
        say(f"    · carpeta anterior:           {d}")
        removable.append(("carpeta de la instalación anterior", d))
    if info["state"]:
        say(f"    · estado per-máquina viejo:   {info['state']}")
        removable.append(("estado per-máquina viejo", info["state"]))
    for p in info["launchers"]:
        say(f"    · comando anterior:           {p}")
        removable.append(("comando anterior", p))
    for d in info["ambiguous"]:
        say(f"    · {DIM}(no parece una instalación de Workspace — NO lo toco, solo aviso): {d}{R}")
    if not removable:
        say(f"{DIM}  Nada seguro que retirar automáticamente. Revísalo a mano si quieres.{R}")
        return False
    say(f"{DIM}  WORKSPACE ya lo reemplaza. Puedo RETIRARLO: borro SOLO esos artefactos de la "
        f"instalación anterior.{R}")
    say(f"{DIM}  Tus CEREBROS (carpetas de agentes) y tus transcripts NO se tocan.{R}")
    if DRY:
        for lbl, p in removable:
            dry(f"retiraría {lbl}: {p}")
        return False
    if not assume_yes:
        interactive = _stdin_tty()
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


def _main():
    print(f"\n  {B}{C}Instalador de Workspace{R}  {DIM}· {platform.system()} · {WORKSPACE}{R}"
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
    _ver = version_visible()
    _prior = prior_install_markers()
    # «Nueva» = sin estado de Workspace NI de la instalación anterior: quien trae
    # restos viejos necesita que sus ajustes (p. ej. traer agentes) SÍ corran.
    _fresh = (not _prior and not os.path.isdir(_paths.state_dir(HOME))
              and not os.path.isdir(os.path.join(HOME, ".claude", legacy.STATE_SUBDIR)))
    if _prior:
        say(f"Ya tenías Workspace instalado{f' ({_ver})' if _ver else ''} "
            f"en esta máquina.")
        say(f"{DIM}Re-ejecutar es seguro: actualizo lo que cambió, nada se duplica "
            f"({', '.join(l for l, _ in _prior)}).{R}\n")
    elif _ver:
        say(f"{DIM}Instalando Workspace {_ver}.{R}\n")

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
        print("  Workspace todavía no tiene agentes"
              + (": %d agente(s) que ya conectaste siguen listos." % len(loaded) if loaded
                 else ": el primero lo creas al abrirlo."))
    socio = ask_socio()          # "" salvo `--socio <slug>` explícito
    if socio:
        ok(f"socio: {socio}")
        write_machine_socio(socio)   # identidad per-máquina (chat desde el menú)
        write_identity(socio)        # quién eres en todos tus cerebros (sesiones v2)

    # P0-4 · guard de OneDrive/known-folders (SOLO detección, jamás auto-move).
    # El harness bajo una ruta sincronizada a la nube = locks/latencia/estado
    # per-máquina pisado → fallos intermitentes. Hard-block ruidoso: no instalamos
    # sobre una base inestable. (Mac/Linux: redirected_root devuelve "" → no-op.)
    root_redir = pathguard.redirected_root(WORKSPACE)
    if root_redir:
        print(f"\n  {C}✗{R} Workspace vive en una ruta redirigida a la nube ({root_redir}):")
        print(f"    {WORKSPACE}")
        print(f"  Muévelo FUERA de OneDrive — a %LOCALAPPDATA%\\Workspace o C:\\Workspace — "
              f"y vuelve a correr el instalador.")
        print(f"  {DIM}OneDrive sincroniza y BLOQUEA los archivos de Workspace (locks, "
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
    greeter_de_fabrica(_fresh)               # nueva: arranque ON de fábrica (no se pregunta)
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
    if os.environ.get("WORKSPACE_INSTALL_ABRE") == "1" and not DRY:
        # I-a: el instalador (setup.sh) abre Workspace en ESTA terminal enseguida
        print(f"\n  {C}Listo.{R}")
        if greeter_abre():
            print(f"  {DIM}Desde ahora, cada terminal nueva abre Workspace "
                  f"(o escribe {R}{B}workspace{R}{DIM}).{R}")
        else:
            print(f"  {DIM}La próxima vez, escribe {R}{B}workspace{R}{DIM} en una terminal nueva.{R}")
    else:
        print(f"\n  {C}Listo.{R} Abre una terminal nueva y escribe {B}workspace{R}{_direct}.")
        if not _names:
            print(f"  {DIM}Ahí creas tu primer agente.{R}")
    print(f"  {DIM}Para hablar con tus agentes necesitas un motor de IA con tu cuenta "
          f"({engine_names()}); Workspace te dice cuáles tienes.{R}")
    if zenith_brain:
        print(f"\n  {DIM}¿Vienes de Cowork? Corre {R}{B}{zenith_brain[0]} migrar{R}{DIM} y luego di "
              f'"listo, procesa mi migración". Guía: assets/brand/MIGRACION.md en tu cerebro{R}')
    if DRY:
        print(f"\n  {DIM}(DRY-RUN: no se escribió nada. Quita --dry-run para instalar.){R}")
    print()


# ── O2-a · la instalación en una línea viva (instalar_vista) ──────────────────
#: La vista corta que pidió el bootstrap (None = el texto completo de siempre).
_VISTA = None


def _vista_pedida():
    """«vivo» o «lineal» si el bootstrap pidió la vista corta: setup.sh con una
    terminal de verdad (vivo: sobre su bloque) o setup.ps1 (lineal), siempre con
    WORKSPACE_INSTALL_ABRE=1. '' = el texto completo de siempre: sin terminal,
    con --detalle (o WORKSPACE_INSTALL_DETALLE=1) y con --dry-run."""
    v = os.environ.get("WORKSPACE_INSTALL_VISTA", "")
    if (v not in ("vivo", "lineal") or os.environ.get("WORKSPACE_INSTALL_ABRE") != "1"
            or "--detalle" in sys.argv or os.environ.get("WORKSPACE_INSTALL_DETALLE") == "1" or DRY):
        return ""
    return v


def _corto_home(p):
    return ("~" + p[len(HOME):]) if HOME and p.startswith(HOME + os.sep) else p


def main():
    modo = _vista_pedida()
    if not modo:
        return _main()
    return _main_corto(modo)


def _main_corto(modo):
    """La instalación con la vista corta: lo que _main dice (✓ de cada archivo,
    rutas, ajustes de cada motor) va a <estado>/instalar.log y en la pantalla
    quedan el paso 3 y el final; lo que no se pudo hacer (✗ ! ⚠) se enseña igual.
    Si _main no termina, una tarjeta dice qué fue lo último y dónde está todo.
    POSIX: la salida se redirige en el fd (también la de los programas que
    corre); Windows: en sys.stdout/sys.stderr (su consola no se toca)."""
    global _VISTA
    import tempfile
    import time
    import instalar_vista as IV
    sd = _paths.state_dir(HOME)
    bit = IV.bitacora_path(sd)
    # Una instalación NUEVA no tiene <estado> todavía, y _main la reconoce así (el
    # arranque de fábrica, las migraciones selladas): crearla antes para la
    # bitácora la volvía «reinstalación». Mientras corre va a un temporal y al
    # final se pasa a <estado>/instalar.log.
    nueva = not os.path.isdir(sd)
    try:
        if nueva:
            fd_t, ruta = tempfile.mkstemp(prefix="workspace-instalar-", suffix=".log")
            os.close(fd_t)
        else:
            ruta = bit
            if os.path.exists(bit) and os.path.getsize(bit) > 512 * 1024:
                os.replace(bit, bit + ".1")  # la anterior queda una vez; nunca crece sin tope
        log = open(ruta, "a", encoding="utf-8", errors="replace")
    except OSError:
        return _main()                       # sin dónde escribir la bitácora: el texto de siempre
    inicio = log.tell()
    log.write("\n── %s · instalar Workspace %s ──\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), version_visible()))
    log.flush()
    sys.stdout.flush()
    sys.stderr.flush()
    guardados = None
    if IS_WIN:
        terminal = sys.stdout
        guardados = (sys.stdout, sys.stderr)
        sys.stdout = sys.stderr = log
    else:
        fd1, fd2 = os.dup(1), os.dup(2)
        terminal = os.fdopen(os.dup(fd1), "w", encoding="utf-8", errors="replace")
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
    vista = IV.Vista(modo, salida=terminal, version=version_visible())
    _VISTA = vista
    rc = 0
    try:
        vista.empezar()
        _main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except KeyboardInterrupt:
        rc = 130
    except Exception:
        import traceback
        traceback.print_exc()
        rc = 1
    finally:
        vista.parar()
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        if guardados:
            sys.stdout, sys.stderr = guardados
        else:
            os.dup2(fd1, 1)
            os.dup2(fd2, 2)
            os.close(fd1)
            os.close(fd2)
        log.close()
        _VISTA = None
    try:
        with open(ruta, encoding="utf-8", errors="replace") as fh:
            fh.seek(inicio)
            texto = fh.read()
    except OSError:
        texto = ""
    if nueva and os.path.isdir(sd):
        try:
            with open(bit, "a", encoding="utf-8", errors="replace") as fh:
                fh.write(texto)
            os.unlink(ruta)
            ruta = bit
        except OSError:
            pass
    if rc == 0:
        avisos = [IV.limpio(ln) for ln in texto.splitlines() if IV.es_aviso(ln)]
        lanz = os.path.join(HOME, ".local", "bin", "workspace.cmd" if IS_WIN else "workspace")
        abre = os.path.isfile(lanz) and (IS_WIN or os.access(lanz, os.X_OK))   # lo mismo que mira el bootstrap
        vista.terminar(greeter_abre(), avisos, abre=abre)
    else:
        ultimas = [IV.limpio(ln) for ln in texto.splitlines() if IV.limpio(ln) and not ln.startswith("── ")]
        vista.fallo(ultimas[-3:], _corto_home(ruta))
    try:
        terminal.flush()
        if not guardados:
            terminal.close()
    except Exception:
        pass
    if rc:
        sys.exit(rc)


# ── CLI: `--help` jamás instala; un argumento desconocido tampoco ─────────────
_USO = ("uso: python3 install.py [--socio <nombre>] [--dry-run] [--desktop-app]\n"
        "                         [--retire-legacy | --no-retire-legacy] [--detalle]\n"
        "  Instala Workspace en esta máquina: el comando `workspace`, un comando por\n"
        "  agente, hooks, permisos y tema. Re-correrlo es seguro: solo actualiza.\n"
        "  --socio <nombre>   quién usa esta máquina (llena los cerebros sin dueño)\n"
        "  --dry-run          muestra qué haría, sin escribir nada\n"
        "  --desktop-app      además, la app de escritorio (Mac)\n"
        "  --retire-legacy    retira la instalación anterior sin preguntar\n"
        "  --no-retire-legacy no la toca\n"
        "  --detalle          con el instalador de un comando, todo lo que hace en pantalla")
_FLAGS = ("--dry-run", "--desktop-app", "--retire-legacy", "--no-retire-legacy", "--detalle")


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
