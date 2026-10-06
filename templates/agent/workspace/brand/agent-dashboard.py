#!/usr/bin/env python3
# {{AGENT_UPPER}} · menú de sesiones (lean). TEMPLATE de WORKSPACE (templates/agent/):
# misma lógica que el dashboard de los demás agentes del equipo; lo parametrizado es nombre, tagline,
# env var y paleta. Debe vivir en WORKSPACE/agents/<n>/brand/ (resuelve la raíz de
# WORKSPACE 4 niveles arriba). Sin sustituir, cae a paleta gris y sigue corriendo.
#   --pick    → saludo + menú interactivo; imprime "WS\t<wid>\t<name>" (lo parsea el motor)
#   --list    → lista las sesiones
#   --context → JSON para el hook SessionStart (memoria de la sesión activa, silencioso)
import os, sys, json, datetime, re
sys.dont_write_bytecode = True   # no generar __pycache__ (mantiene limpio el sync)

try:   # B2 · Windows: UTF-8 en stdout/err — evita UnicodeEncodeError con box-drawing
       # bajo cp1252 cuando el motor captura --pick. No-op en Mac (UTF-8 ya es default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# La carpeta de sesiones de Claude Code y la lista de sesiones SOURCED del cerebro
# se calculan en UN solo lugar: WORKSPACE/session_paths.py + WORKSPACE/agent_brand.py.
# OJO: este stub vive UN nivel más adentro que agents/<n>/brand/, así que el "4
# niveles arriba" fijo NO da la raíz de WORKSPACE — ascender hasta encontrar el
# módulo compartido (robusto a la profundidad).
def _workspace_root(start):
    # brand de agente NUEVO vive en {cerebro}/brand/ (Desktop): WORKSPACE es HERMANO,
    # no ancestro → 1) $WORKSPACE_ROOT, 2) ascender (agentes de equipo), 3) fallback.
    def _has(d):
        return d and os.path.exists(os.path.join(d, "agent_brand.py"))
    env = os.path.expanduser((os.environ.get("WORKSPACE_ROOT") or "").strip())
    if _has(env):
        return env
    d = os.path.dirname(os.path.abspath(start))
    for _ in range(8):
        if _has(d):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    fb = os.path.expanduser("~/Desktop/WORKSPACE")
    return fb if _has(fb) else None

_WORKSPACE = _workspace_root(__file__) or os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _WORKSPACE not in sys.path:
    sys.path.insert(0, _WORKSPACE)
from session_paths import session_dir as _claude_session_dir  # noqa: E402
import agent_brand  # noqa: E402

# ── i18n (falla-suave) — las cadenas ESTÁTICAS del picker/greeter siguen el
# idioma del socio (i18n.lang(): WORKSPACE_LANG > settings ui.lang > "es").
# i18n vive en la raíz de WORKSPACE, ya insertada en sys.path arriba (_WORKSPACE).
# Si no se resuelve, _t cae al ES inline → el picker JAMÁS truena. Ver lang/README.md.
try:
    import i18n as _i18n  # noqa: E402
except Exception:
    _i18n = None

def _t(key, es, **kw):
    if _i18n is None:
        return es.format(**kw) if kw else es
    try:
        s = _i18n.t(key, **kw)
        return s if s != key else (es.format(**kw) if kw else es)
    except Exception:
        return es.format(**kw) if kw else es

AGENT_NAME = "{{AGENT_NAME}}"          # slug (workspaces file, comandos)
AGENT_DISPLAY = "{{AGENT_DISPLAY}}"
AGENT_UPPER = "{{AGENT_UPPER}}"        # env var <UPPER>_WS
TAGLINE = "{{TAGLINE}}"
COLOR = "{{COLOR}}"

def _find_brain():
    # Este script vive en WORKSPACE (agents/<n>/brand/), NO en el cerebro — el cerebro
    # se resuelve explícitamente, nunca desde __file__:
    #   1. --brain <ruta>   2. $WORKSPACE_BRAIN (dispatch.py)
    #   3. $CLAUDE_PROJECT_DIR (hooks de Claude Code)   4. cwd (hooks corren ahí)
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--brain" and i + 1 < len(argv):
            return os.path.abspath(os.path.expanduser(argv[i + 1]))
    for k in ("WORKSPACE_BRAIN", "CLAUDE_PROJECT_DIR"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return os.path.abspath(os.path.expanduser(v))
    return os.getcwd()

BRAIN = _find_brain()
HOME = os.path.expanduser("~")

# Identidad SOURCED del cerebro: este stub se referencia SIN sustituir (agentes
# de equipo cargados en vivo → los {{...}} quedan literales), así que nombre/upper/
# tagline/paleta se resuelven de BOOT/01-IDENTITY.md + .workspace/agent.json. Si los
# placeholders SÍ vienen sustituidos (agente con brand propio renderizado), ganan.
try:
    _ident = agent_brand.resolve_identity(BRAIN, display=AGENT_DISPLAY,
                                          tagline=TAGLINE, color=COLOR)
    AGENT_NAME = _ident["name"]
    AGENT_DISPLAY = _ident["display"]
    AGENT_UPPER = _ident["upper"]
    TAGLINE = _ident["tagline"] or TAGLINE
    COLOR = _ident["palette"]
except Exception:
    pass

WS_FILE = os.path.join(BRAIN, ".claude", f"{AGENT_NAME}-workspaces.json")
SESS_DIR = _claude_session_dir(BRAIN)   # única fuente: WORKSPACE/session_paths.py

def fg(n): return f"\033[38;5;{n}m"
R = "\033[0m"; BO = "\033[1m"
# Paleta: HEAD, NAME, SUB, MUTE, CARET, DIM — ajusta el COLOR a tu agente.
PALETTES = {
    "dorado": (178, 222, 136, 101, 178, 94),
    "coral":  (203, 224, 167, 131, 203, 95),
    "verde":  (46, 194, 40, 65, 46, 28),
    "azul":   (75, 195, 32, 60, 75, 24),
    "morado": (135, 225, 97, 96, 135, 54),
    "cyan":   (51, 195, 37, 66, 51, 23),
    "gris":   (252, 255, 250, 242, 252, 238),
}
# COLOR llega como clave de paleta (agent_brand resolvió) o color CRUDO sustituido
# (agente nuevo, agent_brand no alcanzable) → normaliza inglés/español a una de las
# 7 claves (espejo de agent_brand._PALETTE_KEY) para no caer a gris por idioma.
_PALETTE_ALIAS = {
    "cian": "cyan", "cyan": "cyan", "celeste": "cyan", "azul": "azul", "blue": "azul",
    "verde": "verde", "green": "verde", "morado": "morado", "purple": "morado",
    "violeta": "morado", "violet": "morado", "rosa": "coral", "pink": "coral",
    "dorado": "dorado", "gold": "dorado", "oro": "dorado", "amarillo": "dorado",
    "coral": "coral", "rojo": "coral", "red": "coral", "wine": "coral", "vino": "coral",
    "gris": "gris", "gray": "gris", "grey": "gris",
}
def _pal_key(c):
    c = (c or "").strip().lower()
    c = c.split()[0] if c else ""
    c = re.sub(r"[^a-záéíóúñ]+", "", c)
    return _PALETTE_ALIAS.get(c, "gris")
_p = PALETTES[_pal_key(COLOR)]
HEAD, NAME, SUB, MUTE, CARET, DIM = (fg(n) for n in _p)

# ── el COLOR es del TEMA del hub, no del agente (el socio 2026-10-02) ─────────────
# El greeter/picker se pinta con la paleta del TEMA ACTIVO de WORKSPACE
# (tuitheme: env WORKSPACE_THEME > ui.theme > default) — igual que el banner y
# el recinto. Falla-suave: sin tuitheme resoluble → la paleta de marca de
# arriba; el picker JAMÁS truena por un tema. MISMO bloque en todos los
# dashboards de agentes (agents/*/brand/*-dashboard.py) — mantener EN
# SINCRONÍA (cada dashboard corre standalone).
def _workspace_root_theme(start):
    def _has(d):
        return d and os.path.exists(os.path.join(d, "tuitheme.py"))
    env = os.path.expanduser((os.environ.get("WORKSPACE_ROOT") or "").strip())
    if _has(env):
        return env
    d = os.path.dirname(os.path.abspath(start))
    for _ in range(8):
        if _has(d):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    fb = os.path.expanduser("~/Desktop/WORKSPACE")
    return fb if _has(fb) else None

try:
    _throot = _workspace_root_theme(__file__)
    if _throot and _throot not in sys.path:
        sys.path.insert(0, _throot)
    import tuitheme as _tuitheme
    _TH = _tuitheme.palette()
except Exception:
    _TH = None
if _TH is not None:
    R, BO = _TH.R, _TH.BO
    HEAD, CARET = _TH.C, _TH.C
    NAME = _TH.WH
    SUB = _TH.B2
    MUTE = DIM = _TH.DIM


def load_workspaces():
    try:
        return json.load(open(WS_FILE, encoding="utf-8"))
    except Exception:
        return []

# ── Y10 · 3 timestamps por sesión — espejo del dashboard de los demás agentes ──
#   created (una vez) · last_opened (SOLO apertura humana vía picker; ordena el
#   menú) · updated (cualquier escritura, incl. hooks — session_end.py la estampa).
# Back-compat: entradas viejas sin campos → fallback al mtime del .jsonl; los
# campos se agregan perezosamente al abrir. Nunca crashear por campo ausente.
def _now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")

def save_workspaces(ws):
    os.makedirs(os.path.dirname(WS_FILE), exist_ok=True)
    tmp = WS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ws, f, indent=2, ensure_ascii=False)
    os.replace(tmp, WS_FILE)   # atómico: el picker es camino crítico del arranque

def add_workspace(name):
    import uuid
    ws = load_workspaces()
    wid = str(uuid.uuid4())
    now = _now_iso()
    ws.append({"name": name, "id": wid,
               "created": now, "last_opened": now, "updated": now})
    save_workspaces(ws)
    return wid

def mark_opened(wid):
    """Apertura HUMANA (picker): estampa last_opened+updated. Best-effort."""
    try:
        ws = load_workspaces()
        now = _now_iso()
        for w in ws:
            if w.get("id") == wid:
                w.setdefault("created", now)
                w["last_opened"] = now
                w["updated"] = now
                break
        else:
            return
        save_workspaces(ws)
    except Exception:
        pass

def _last_human(w):
    """Epoch de la última interacción humana: last_opened → mtime .jsonl → created → 0."""
    for key in ("last_opened", "created"):
        v = w.get(key)
        if v:
            try:
                return datetime.datetime.fromisoformat(v).timestamp()
            except Exception:
                pass
        if key == "last_opened":
            try:
                f = os.path.join(SESS_DIR, f"{w.get('id', '')}.jsonl")
                if os.path.exists(f):
                    return os.path.getmtime(f)
            except Exception:
                pass
    return 0.0

def session_exists(wid):
    return os.path.exists(os.path.join(SESS_DIR, f"{wid}.jsonl"))

# ── memoria de sesión (STATE/sessions/<socio>/<slug>.md) — espejo del dashboard de los demás agentes ──
NOMBRE = {}  # mapeo socio→display, se llena por instalación

def socio():
    # El dueño sale de .claude/socio.local (lo escribe el harness) — cualquier slug,
    # no solo el trío del equipo: un agente vendido tiene su propio dueño. Sin guess horneado.
    try:
        s = open(os.path.join(BRAIN, ".claude", "socio.local")).read().strip().lower()
        if s:
            return s
    except Exception:
        pass
    return ""

def _slug(s):
    import re, unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def _sess_dir_socio():
    return os.path.join(BRAIN, "STATE", "sessions", socio())

def session_body(name):
    """Cuerpo (resumen + historial) de la memoria de una sesión, por nombre."""
    p = os.path.join(_sess_dir_socio(), f"{_slug(name)}.md")
    if not os.path.exists(p):
        return ""
    txt = open(p, encoding="utf-8").read()
    parts = txt.split("---", 2)
    return parts[2].strip() if len(parts) >= 3 else txt.strip()

def render_context():
    """JSON para el hook SessionStart: inyecta la memoria de la sesión activa.
    Misma mecánica que el render_context del dashboard de los demás agentes.
    Sin pestaña activa → '' (hook silencioso)."""
    ws = (os.environ.get("WORKSPACE_WS", "") or
          os.environ.get(f"{AGENT_UPPER}_WS", "")).strip()
    if not ws:
        return ""
    soc = socio()
    body = session_body(ws)
    parts = ["[Arranque de sesión — contexto inyectado automáticamente]",
             f"SESIÓN ACTIVA: «{ws}». Esta conversación es esa sesión persistente."]
    if body:
        parts.append("Memoria de esta sesión (STATE/sessions/" + (soc or "<socio>") + "/):")
        parts.append(body[:1200])
    parts.append("Al cerrar trabajo significativo, haz append fechado a ## Historial de esa "
                 "memoria y actualiza su frontmatter (actualizada/estado/trabajo). "
                 "Ver CLAUDE.md §2.5 (Memoria de sesión).")
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                              "additionalContext": "\n".join(p for p in parts if p)}})

def _sessions():
    # Lista de pestañas SOURCED del cerebro (sigue al socio entre máquinas) + el
    # enriquecimiento vivo del workspaces.json per-máquina. Fuente única.
    return agent_brand.merged_sessions(BRAIN, socio(), load_workspaces(),
                                       SESS_DIR, _last_human)

def menu_items():
    # Orden: última interacción HUMANA primero (Y10); "+ nueva" siempre al final.
    items = []
    for w in _sessions():
        wid, name = w.get("id"), w.get("name", "?")
        sub = _t("banner.dash.sub_continue", "continuar") if session_exists(wid) \
            else _t("banner.dash.sub_new", "nueva")
        items.append((name, sub, ("WS", wid, name)))
    items.append((_t("banner.dash.new_label", "+ Sesión nueva…"),
                  _t("banner.dash.new_sub", "crea una sesión con nombre"), ("NEW", None, None)))
    return items

def _tty():
    try:
        return open("/dev/tty", "r"), open("/dev/tty", "w")
    except Exception:
        if sys.platform == "win32":
            try:
                # CONOUT$ = consola directa (equivalente de /dev/tty): visible aunque el
                # padre capture stdout/stderr (como hace dispatch.py con capture_output).
                return sys.stdin, open("CONOUT$", "w", encoding="utf-8")
            except Exception:
                pass
        return sys.stdin, sys.stderr

def header_lines():
    n = sum(1 for _ in _sessions())
    return [
        f"{HEAD}{BO}  {AGENT_UPPER}{R}{DIM} · {TAGLINE}{R}",
        f"{MUTE}  {_t('banner.dash.sessions_count', '{n} sesión(es) · elige una para continuar o crea una nueva', n=n)}{R}",
        "",
        f"  {HEAD}◆ {_t('banner.dash.resume_q', '¿En qué seguimos?')}{R}   {MUTE}{_t('banner.dash.hint', '↑↓ para elegir · Enter para abrir')}{R}",
    ]

def _picker_simple(items):
    inp, out = _tty()
    out.write("\n")
    for i, (lbl, sub, _) in enumerate(items, 1):
        out.write(f"    {NAME}{i}{R}  {SUB}{lbl}{R}   {MUTE}{sub}{R}\n")
    out.write(f"\n  {MUTE}{_t('banner.dash.number_enter', 'Número y Enter: ')}{R}"); out.flush()
    try:
        k = int((inp.readline() or "").strip())
        if 1 <= k <= len(items):
            return k - 1
    except Exception:
        pass
    return len(items) - 1

def _picker_windows(items):
    # Windows: navegación con flechas vía msvcrt (paridad con la rama Unix de abajo).
    # El menú va a CONOUT$ (consola directa) para verse aunque el padre capture stdout/stderr.
    import msvcrt
    try:
        out = open("CONOUT$", "w", encoding="utf-8")
    except Exception:
        out = sys.stderr
    nameW = max(len(lbl) for lbl, _, _ in items) + 2
    n = len(items); idx = 0

    def draw(first):
        if not first:
            out.write(f"\033[{n}A")
        for i, (lbl, sub, _) in enumerate(items):
            out.write("\r\033[K")
            if i == idx:
                out.write(f"    {CARET}❯ {NAME}{lbl.ljust(nameW)}{R}{SUB}{sub}{R}")
            else:
                out.write(f"      {DIM}{lbl.ljust(nameW)}{R}{MUTE}{sub}{R}")
            out.write("\r\n")
        out.flush()

    draw(True)
    while True:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):          # prefijo de tecla especial (flechas)
            a = msvcrt.getwch()
            idx = (idx - 1) % n if a == "H" else (idx + 1) % n if a == "P" else idx
        elif ch in ("\r", "\n"):
            break
        elif ch == "\x03":
            idx = n - 1; break
        elif ch.isdigit() and 1 <= int(ch) <= n:
            idx = int(ch) - 1; break
        else:
            continue
        draw(False)
    return idx

def run_picker(items):
    import agent_ui
    choice = agent_ui.live_picker(items, __file__)
    if choice is not None:
        return choice
    # Devuelve el índice elegido. Unix: flechas (termios). Windows: flechas (msvcrt).
    # Sin TTY: numerado (_picker_simple).
    if sys.platform == "win32":
        try:
            return _picker_windows(items)
        except Exception:
            return _picker_simple(items)
    try:
        import termios, tty
        tin = open("/dev/tty", "r"); tout = open("/dev/tty", "w")
    except Exception:
        return _picker_simple(items)
    nameW = max(len(lbl) for lbl, _, _ in items) + 2
    n = len(items); idx = 0

    def draw(first):
        if not first:
            tout.write(f"\033[{n}A")
        for i, (lbl, sub, _) in enumerate(items):
            tout.write("\r\033[K")
            if i == idx:
                tout.write(f"    {CARET}❯ {NAME}{lbl.ljust(nameW)}{R}{SUB}{sub}{R}")
            else:
                tout.write(f"      {DIM}{lbl.ljust(nameW)}{R}{MUTE}{sub}{R}")
            tout.write("\r\n")
        tout.flush()

    draw(True)
    fd = tin.fileno(); old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = tin.read(1)
            if ch == "\x1b":
                if tin.read(1) == "[":
                    a = tin.read(1)
                    idx = (idx - 1) % n if a == "A" else (idx + 1) % n if a == "B" else idx
            elif ch in ("\r", "\n"):
                break
            elif ch == "\x03":
                idx = n - 1; break
            elif ch.isdigit() and 1 <= int(ch) <= n:
                idx = int(ch) - 1; break
            else:
                continue
            termios.tcsetattr(fd, termios.TCSADRAIN, old); draw(False); tty.setraw(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return idx

def list_sessions():
    out = []
    for w in _sessions():
        wid, name = w.get("id"), w.get("name", "?")
        mark = "●" if session_exists(wid) else "○"
        out.append(f"  {mark} {name}")
    return "\n".join(out) or ("  " + _t("banner.dash.no_sessions", "(sin sesiones)"))


def main():
    if "--context" in sys.argv:
        out = render_context()
        if out:
            sys.stdout.write(out)
        return
    if "--list" in sys.argv:
        print("\n" + list_sessions() + "\n"); return
    if "--pick" in sys.argv:
        tin, tout = _tty()
        try:    # greeter canónico: live_picker pinta TODO (banner + caja)
                # en un solo frame YA centrado — escribir el header aquí
                # causaba el parpadeo izquierda→centro al entrar. El header
                # queda solo para el FALLBACK sin agent_ui (sin harness).
            import agent_ui as _agent_ui_probe   # noqa: F401
        except Exception:
            tout.write("\n" + "\n".join(header_lines()) + "\n"); tout.flush()
        items = menu_items()
        idx = run_picker(items)
        kind = items[idx][2]
        if kind[0] == "NEW":
            tout.write(f"\r\n  {MUTE}{_t('banner.dash.name_prompt', 'Nombre de la sesión: ')}{R}"); tout.flush()
            try:
                name = (tin.readline() or "").strip()
            except Exception:
                name = ""
            name = name or "General"     # el nombre devuelto al motor debe ser el guardado
            wid = add_workspace(name)    # ya estampa created/last_opened/updated
        else:
            _, wid, name = kind
            if not wid:                  # sesión del cerebro sin pestaña local
                wid = add_workspace(name)   # → crear el workspace per-máquina
            else:
                mark_opened(wid)         # interacción humana real (Y10)
        tout.write(f"\r\n  {CARET}▸{R} {NAME}{name}{R}  {MUTE}— {_t('banner.dash.loading', 'cargando…')}{R}\r\n\r\n"); tout.flush()
        sys.stdout.write(f"WS\t{wid}\t{name}")     # el motor lo parsea
        return
    print("\n".join(header_lines()))

if __name__ == "__main__":
    main()
