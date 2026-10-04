#!/usr/bin/env python3
# Status line de {{AGENT_DISPLAY}} para Claude Code — panel de 2 columnas que crece
# hacia abajo. Izquierda: barras (contexto, límite 5h, límite semanal). Derecha:
# información de texto (agente, modelo, brain, tiempo, costo, resets).
# TEMPLATE de WORKSPACE (templates/agent/): misma lógica que el statusline de los demás agentes
# del equipo; lo único parametrizado es AGENT_NAME y la paleta (COLOR → PALETTES). Sin sustituir,
# cae a la paleta gris neutra y sigue funcionando. Recibe el JSON de estado por stdin.
import sys, json, os, time

try:   # B2 · Windows: UTF-8 en stdout/err — la statusline la lanza Claude Code (no
       # controlamos su env) y dibuja box-drawing → bajo cp1252 reventaría con
       # UnicodeEncodeError y saldría vacía. No-op en Mac (UTF-8 ya es default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

R = "\033[0m"
def fg(n): return f"\033[38;5;{n}m"

AGENT_NAME = "{{AGENT_DISPLAY}}"
COLOR = "{{COLOR}}"
# Paleta (HEAD, MODEL, LBL, VAL, SEP, FILL, EMPT): se resuelve abajo desde el cerebro
# vía agent_brand.palette (paleta TUNED como DATO en .workspace/agent.json, o preset por
# color). Fuente única — ya no hay tabla de presets duplicada aquí. Estos defaults
# gris-neutros solo aplican si esa resolución falla (fail-soft).
HEAD = MODEL = LBL = VAL = SEP = FILL = EMPT = fg(244)
# Glifos de barra por plataforma. En Windows Terminal el full block █ sangra fuera de la
# celda y las filas se pegan → box-drawing horizontal (━/─). Mac/Unix mantiene █/░.
if os.name == "nt":
    BAR_FILL, BAR_TRACK = "━", "─"
else:
    BAR_FILL, BAR_TRACK = "█", "░"

try:
    d = json.load(sys.stdin)
except Exception:
    d = {}

def g(o, *ks, default=None):
    for k in ks:
        o = o.get(k) if isinstance(o, dict) else None
    return o if o is not None else default

def cw(ch):
    o = ord(ch)
    if o >= 0x1F000 or 0x2600 <= o <= 0x27BF or o in (0x231A, 0x231B, 0x2B50):
        return 2
    return 1

def add(cells, text, color):
    for ch in text:
        cells.append((ch, color, cw(ch)))

def visw(cells):
    return sum(w for _, _, w in cells)

def pad(cells, target):
    cells = list(cells)
    while visw(cells) < target:
        cells.append((" ", LBL, 1))
    return cells

def line(cells):
    return "".join(f"{c}{ch}" for ch, c, _ in cells) + R

def gauge(label, pct, lw=12, n=12):
    c = []
    add(c, label.ljust(lw), LBL)
    if isinstance(pct, (int, float)):
        p = max(0, min(100, int(pct)))
        f = max(0, min(n, round(p * n / 100.0)))
        add(c, "[", SEP); add(c, BAR_FILL * f, FILL); add(c, BAR_TRACK * (n - f), EMPT); add(c, "]", SEP)
        add(c, f" {p:>3}%", VAL)
    else:
        add(c, "[", SEP); add(c, "·" * n, EMPT); add(c, "]", SEP); add(c, "  --", LBL)
    return c

def fmt_reset(ts):
    if not ts:
        return None
    rem = int(ts - time.time())
    if rem <= 0:
        return "ya"
    dd, hh, mm = rem // 86400, (rem % 86400) // 3600, (rem % 3600) // 60
    if dd:
        return f"{dd}d {hh}h"
    if hh:
        return f"{hh}h {mm}m"
    return f"{mm}m"

# ── datos ──
model = g(d, "model", "display_name", default="Claude")
pct   = g(d, "context_window", "used_percentage")
toks  = g(d, "context_window", "total_input_tokens")
cost  = g(d, "cost", "total_cost_usd", default=0) or 0
durms = g(d, "cost", "total_duration_ms", default=0) or 0
rl5p  = g(d, "rate_limits", "five_hour", "used_percentage")
rl5r  = g(d, "rate_limits", "five_hour", "resets_at")
rl7p  = g(d, "rate_limits", "seven_day", "used_percentage")
rl7r  = g(d, "rate_limits", "seven_day", "resets_at")

# Tap de uso para el heartbeat de WORKSPACE: persiste el uso del plan (5h/7d) a disco
# en cada render, para que `workspace heartbeat` respete el colchón antes de lanzar
# trabajo autónomo. Falla-suave: jamás rompe la barra.
try:
    import time as _t
    _gauge = os.path.join(os.path.expanduser("~"), ".claude", "workspace", "usage.json")
    os.makedirs(os.path.dirname(_gauge), exist_ok=True)
    _tmp = _gauge + ".tmp"
    with open(_tmp, "w") as _f:
        json.dump({"five_hour_pct": rl5p, "five_hour_resets_at": rl5r,
                   "seven_day_pct": rl7p, "seven_day_resets_at": rl7r,
                   "context_pct": pct, "stamped": int(_t.time())}, _f)
    os.replace(_tmp, _gauge)
except Exception:
    pass

def _find_brain():
    # Este script vive en WORKSPACE (agents/<n>/brand/), NO en el cerebro — el cerebro
    # se resuelve explícitamente, nunca desde __file__:
    #   1. --brain <ruta> (statusLine generado por install.py) · 2. $WORKSPACE_BRAIN
    #   3. workspace del JSON de Claude Code · 4. $CLAUDE_PROJECT_DIR · 5. cwd
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--brain" and i + 1 < len(argv):
            return os.path.abspath(os.path.expanduser(argv[i + 1]))
    cands = [os.environ.get("WORKSPACE_BRAIN"),
             g(d, "workspace", "project_dir"), g(d, "workspace", "current_dir"),
             os.environ.get("CLAUDE_PROJECT_DIR")]
    for v in cands:
        if v and str(v).strip():
            return os.path.abspath(os.path.expanduser(str(v).strip()))
    return os.getcwd()

# ── identidad de marca SOURCED del cerebro (mismo patrón que banner/dashboard) ──
# Sin esto, la statusline mostraría los placeholders {{AGENT_DISPLAY}}/{{COLOR}}
# crudos y caería a la paleta gris. El cerebro llega por $WORKSPACE_BRAIN/--brain;
# la identidad vive en BOOT/01-IDENTITY.md + .workspace/agent.json → SIGUE al socio
# entre máquinas. Falla-suave: si no se resuelve, quedan los defaults de arriba.
# DUP(bootstrap-root): copia idéntica en banner·dashboard·statusline.
# Deuda explícita → consolidar en un renderer compartido (brand = datos, no código).
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

try:
    _root = _workspace_root(__file__)
    if _root and _root not in sys.path:
        sys.path.insert(0, _root)
    import agent_brand  # noqa: E402
    _brain = _find_brain()
    _ident = agent_brand.resolve_identity(_brain, display=AGENT_NAME, color=COLOR)
    AGENT_NAME = _ident["display"]
    COLOR = _ident["palette"]                 # clave de paleta normalizada (cian→cyan)
    _p = agent_brand.palette(_brain, _ident["color"])   # paleta como DATO del cerebro
    HEAD, MODEL, LBL, VAL, SEP, FILL, EMPT = (fg(n) for n in _p)
except Exception:
    pass

ver = None
try:
    import re as _re
    vp = os.path.join(_find_brain(), "STATE", "brain-version.md")
    with open(vp) as f:
        for ln in f:
            if ln.lower().startswith("version:"):
                raw = ln.split(":", 1)[1].strip()
                # Sanitizar: solo caracteres seguros, acotar longitud (anti inyección ANSI/OSC)
                ver = _re.sub(r"[^A-Za-z0-9._\- ]", "", raw)[:40] or None
                break
except Exception:
    pass

s = int(durms) // 1000
sess = f"{s//60}m {s%60}s" if s >= 60 else f"{s}s"
r5, r7 = fmt_reset(rl5r), fmt_reset(rl7r)

# ── columna izquierda: barras (etiquetas descriptivas, alineadas) ──
LBLW = 12
left = [
    gauge("contexto", pct, LBLW),
    gauge("uso sesión", rl5p, LBLW),
    gauge("uso semanal", rl7p, LBLW),
    [],                               # fila en blanco (pareja del pie de texto)
]
LW = max(visw(c) for c in left)

# ── columna derecha: texto (cada reset emparejado con su barra) ──
def dot(c): add(c, "   ·   ", SEP)

r_zen = []
add(r_zen, "◆ ", HEAD); add(r_zen, AGENT_NAME, HEAD); dot(r_zen); add(r_zen, model, MODEL)

def reset_row(rs):
    c = []
    if rs:
        add(c, "se reinicia en ", LBL); add(c, rs, VAL)
    else:
        add(c, "— dato tras el 1er mensaje", EMPT)
    return c

r_foot = []
add(r_foot, "activa ", LBL); add(r_foot, sess, VAL)
if ver:
    dot(r_foot); add(r_foot, "brain ", LBL); add(r_foot, f"v{ver}", VAL)
if cost and cost > 0:
    dot(r_foot); add(r_foot, f"${cost:.2f}", VAL)

right = [r_zen, reset_row(r5), reset_row(r7), r_foot]

# ── ensamblar filas ──
DIV = []
add(DIV, "   ", LBL); add(DIV, "│", SEP); add(DIV, "   ", LBL)
out = []
for i in range(4):
    row = pad(left[i], LW) + DIV + right[i]
    out.append(" " + line(row))
sys.stdout.write("\n".join(out))
