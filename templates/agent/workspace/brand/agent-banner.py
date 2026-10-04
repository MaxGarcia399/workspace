#!/usr/bin/env python3
# Banner de {{AGENT_DISPLAY}} — TEMPLATE de WORKSPACE (templates/agent/): stub SOBRIO
# pero digno (título en bloques + caja con rol/skills, paleta de marca). El arte
# definitivo (p. ej. un emblema braille) es follow-up — ver el banner de otro agente
# del equipo como referencia de a dónde llevarlo.
# Sin sustituir los placeholders, cae a paleta gris y sigue corriendo.
import os, re, sys

try:   # B2 · Windows: UTF-8 en stdout/err — evita UnicodeEncodeError con box-drawing/
       # braille bajo cp1252 cuando el motor captura el banner. No-op en Mac (UTF-8 default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.dont_write_bytecode = True
if os.name == "nt":
    os.system("")  # habilita ANSI en Windows 10+

AGENT_DISPLAY = "{{AGENT_DISPLAY}}"
TAGLINE = "{{TAGLINE}}"
SKILL_CATS = "{{SKILL_CATS}}"
SCOPE = "{{SCOPE}}"
COLOR = "{{COLOR}}"

# ── identidad SOURCED del cerebro ────────────────────────────────────────────
# Este stub vive en WORKSPACE y se referencia SIN sustituir (agentes cargados como
# Turing): los {{...}} de arriba quedan literales. Por eso la identidad real se
# lee del cerebro (BOOT/01-IDENTITY.md + .workspace/agent.json) vía agent_brand —
# así el banner SIGUE al socio entre máquinas. El cerebro llega por
# $WORKSPACE_BRAIN (lo exporta el motor) o --brain. Falla-suave: si no se puede
# resolver, se queda con lo que haya (o el gris) y sigue corriendo.
def _workspace_root(start):
    # El brand de un agente NUEVO vive en {cerebro}/brand/ (en el Desktop del
    # socio), donde WORKSPACE es un HERMANO del cerebro, NO un ancestro → ascender
    # nunca lo encuentra. Por eso: 1) $WORKSPACE_ROOT que exporta el harness,
    # 2) ascender (agentes de EQUIPO: brand dentro de WORKSPACE/agents/<n>/brand/),
    # 3) fallback conocido ~/Desktop/WORKSPACE. Falla-suave: None → paleta por color.
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

def _find_brain():
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--brain" and i + 1 < len(argv):
            return os.path.abspath(os.path.expanduser(argv[i + 1]))
    for k in ("WORKSPACE_BRAIN", "CLAUDE_PROJECT_DIR"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return os.path.abspath(os.path.expanduser(v))
    return os.getcwd()

try:
    _root = _workspace_root(__file__)
    if _root and _root not in sys.path:
        sys.path.insert(0, _root)
    import agent_brand  # noqa: E402
    _ident = agent_brand.resolve_identity(
        _find_brain(), display=AGENT_DISPLAY, tagline=TAGLINE,
        color=COLOR, scope=SCOPE, skills=SKILL_CATS)
    AGENT_DISPLAY = _ident["display"]
    TAGLINE = _ident["tagline"] or TAGLINE
    SKILL_CATS = _ident["skills"] or SKILL_CATS
    SCOPE = _ident["scope"] or SCOPE
    COLOR = _ident["palette"]            # clave de paleta normalizada (cian→cyan)
    _EMOJI = _ident["emoji"]
except Exception:
    _EMOJI = ""

def fg(n): return f"\033[38;5;{n}m"
R = "\033[0m"; BO = "\033[1m"
# Paleta FALLBACK por color de marca: B (brillante), B2 (medio), DK (oscuro),
# DIM (apagado), C (acento), WH (claro). Solo se usa si el tema del hub no es
# resoluble (cerebro sin harness) — ver el bloque del TEMA más abajo.
PALETTES = {
    "dorado": (178, 136, 58, 101, 220, 230),
    "coral":  (203, 167, 95, 131, 210, 224),
    "verde":  (46, 40, 22, 65, 48, 194),
    "azul":   (75, 32, 24, 60, 81, 195),
    "morado": (135, 97, 54, 96, 177, 225),
    "cyan":   (51, 37, 23, 66, 87, 195),
    "gris":   (252, 245, 237, 242, 255, 231),
}
# COLOR llega como clave de paleta (si agent_brand resolvió) o como el color
# CRUDO sustituido en {{COLOR}} (si el import no alcanzó WORKSPACE — agente nuevo).
# Normalizamos INGLÉS y ESPAÑOL → una de las 7 claves, para no caer a gris por un
# simple mismatch de idioma. Espejo de agent_brand._PALETTE_KEY (copia deliberada:
# el banner DEBE colorear standalone, sin depender de importar agent_brand).
_PALETTE_ALIAS = {
    "cian": "cyan", "cyan": "cyan", "celeste": "cyan",
    "azul": "azul", "blue": "azul",
    "verde": "verde", "green": "verde",
    "morado": "morado", "purple": "morado", "violeta": "morado", "violet": "morado",
    "rosa": "coral", "pink": "coral",
    "dorado": "dorado", "gold": "dorado", "oro": "dorado", "amarillo": "dorado",
    "coral": "coral", "rojo": "coral", "red": "coral", "wine": "coral", "vino": "coral",
    "gris": "gris", "gray": "gris", "grey": "gris",
}
def _pal_key(c):
    c = (c or "").strip().lower()
    c = c.split()[0] if c else ""
    c = re.sub(r"[^a-záéíóúñ]+", "", c)
    return _PALETTE_ALIAS.get(c, "gris")

# ── el COLOR es del TEMA del hub, no del agente (el socio 2026-10-02) ──────────────
# El banner se pinta con la paleta del TEMA ACTIVO de WORKSPACE (tuitheme:
# env WORKSPACE_THEME > ui.theme > default) — igual que el recinto, el Tono y
# el resto del hub. Con muchos agentes el color-por-agente no escala (arcoíris);
# la identidad del agente queda en su NOMBRE, emblema y tagline. El gradiente
# del título usa el WCOL del tema (el mismo del wordmark WORKSPACE).
# Falla-suave: sin tuitheme resoluble (cerebro sin harness) → la paleta por
# color de marca de siempre; el banner JAMÁS truena por un tema.
_TH = None
try:
    if _root:                       # el root de WORKSPACE ya está en sys.path
        import tuitheme
        _TH = tuitheme.palette()
except Exception:
    _TH = None
if _TH is not None:
    R, BO = _TH.R, _TH.BO
    B, B2, DK, DIM, C, WH = _TH.B, _TH.B2, _TH.DK, _TH.DIM, _TH.C, _TH.WH
    ROWCOL = list(_TH.WCOL)         # degradado del título = wordmark del tema
else:
    _p = PALETTES[_pal_key(COLOR)]
    B, B2, DK, DIM, C, WH = (fg(n) for n in _p)
    ROWCOL = None                   # se arma abajo, con la paleta ya resuelta

# ── fuente ANSI-Shadow (6 filas/glifo) — el MISMO estilo grabado 3D de los
# banners de equipo (argus/zenith/atlas/turing), pero renderizando CUALQUIER
# nombre dinámicamente. Antes era una 5x5 plana → un agente nuevo nacía con un
# título pobre. Ahora iguala al equipo por default. A-Z · 0-9 · guion · espacio.
FONT = {
    " ": ["   ", "   ", "   ", "   ", "   ", "   "],
    "-": ["       ", "       ", " █████╗", " ╚════╝", "       ", "       "],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "B": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██████╔╝", "╚═════╝ "],
    "C": [" ██████╗", "██╔════╝", "██║     ", "██║     ", "╚██████╗", " ╚═════╝"],
    "D": ["██████╗ ", "██╔══██╗", "██║  ██║", "██║  ██║", "██████╔╝", "╚═════╝ "],
    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    "F": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "██║     ", "╚═╝     "],
    "G": [" ██████╗ ", "██╔════╝ ", "██║  ███╗", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "H": ["██╗  ██╗", "██║  ██║", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "I": ["██╗", "██║", "██║", "██║", "██║", "╚═╝"],
    "J": ["     ██╗", "     ██║", "     ██║", "██   ██║", "╚█████╔╝", " ╚════╝ "],
    "K": ["██╗  ██╗", "██║ ██╔╝", "█████╔╝ ", "██╔═██╗ ", "██║  ██╗", "╚═╝  ╚═╝"],
    "L": ["██╗     ", "██║     ", "██║     ", "██║     ", "███████╗", "╚══════╝"],
    "M": ["███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║", "██║ ╚═╝ ██║", "╚═╝     ╚═╝"],
    "N": ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"],
    "O": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "P": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔═══╝ ", "██║     ", "╚═╝     "],
    "Q": [" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║▄▄ ██║", "╚██████╔╝", " ╚══▀▀═╝ "],
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    "S": ["███████╗", "██╔════╝", "███████╗", "╚════██║", "███████║", "╚══════╝"],
    "T": ["████████╗", "╚══██╔══╝", "   ██║   ", "   ██║   ", "   ██║   ", "   ╚═╝   "],
    "U": ["██╗   ██╗", "██║   ██║", "██║   ██║", "██║   ██║", "╚██████╔╝", " ╚═════╝ "],
    "V": ["██╗   ██╗", "██║   ██║", "██║   ██║", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚═══╝  "],
    "W": ["██╗    ██╗", "██║    ██║", "██║ █╗ ██║", "██║███╗██║", "╚███╔███╔╝", " ╚══╝╚══╝ "],
    "X": ["██╗  ██╗", "╚██╗██╔╝", " ╚███╔╝ ", " ██╔██╗ ", "██╔╝ ██╗", "╚═╝  ╚═╝"],
    "Y": ["██╗   ██╗", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚██╔╝  ", "   ██║   ", "   ╚═╝   "],
    "Z": ["███████╗", "╚══███╔╝", "  ███╔╝ ", " ███╔╝  ", "███████╗", "╚══════╝"],
    "0": [" ██████╗ ", "██╔═████╗", "██║██╔██║", "████╔╝██║", "╚██████╔╝", " ╚═════╝ "],
    "1": [" ██╗", "███║", "╚██║", " ██║", " ██║", " ╚═╝"],
    "2": ["██████╗ ", "╚════██╗", " █████╔╝", "██╔═══╝ ", "███████╗", "╚══════╝"],
    "3": ["██████╗ ", "╚════██╗", " █████╔╝", " ╚═══██╗", "██████╔╝", "╚═════╝ "],
    "4": ["██╗  ██╗", "██║  ██║", "███████║", "╚════██║", "     ██║", "     ╚═╝"],
    "5": ["███████╗", "██╔════╝", "███████╗", "╚════██║", "███████║", "╚══════╝"],
    "6": [" ██████╗ ", "██╔════╝ ", "███████╗ ", "██╔═══██╗", "╚██████╔╝", " ╚═════╝ "],
    "7": ["███████╗", "╚════██║", "    ██╔╝", "   ██╔╝ ", "   ██║  ", "   ╚═╝  "],
    "8": [" █████╗ ", "██╔══██╗", "╚█████╔╝", "██╔══██╗", "╚█████╔╝", " ╚════╝ "],
    "9": [" █████╗ ", "██╔══██╗", "╚██████║", " ╚═══██║", " █████╔╝", " ╚════╝ "],
}
if not ROWCOL or len(ROWCOL) != 6:
    ROWCOL = [B, B, B2, B2, C, C]   # degradado fallback del título (6 filas)

def title_lines(text):
    # el título es "<NOMBRE> AGENT" (el sufijo distingue al agente, como el equipo)
    glyphs = [FONT.get(ch, FONT[" "]) for ch in ((text or "").upper() + " AGENT")]
    return [" ".join(gl[r] for gl in glyphs) for r in range(6)]

def vis(s):
    return len(re.sub(r"\033\[[0-9;]*m", "", s))

def wrap(text, width):
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]

def pad(s, w):
    return s + " " * max(0, w - vis(s))

# ── dimensiones de la caja: emblema (izq) + info (der), estilo equipo ──
ACOL = 34       # columna del emblema (= AW de los banners de equipo → calzan)
ICOL = 66       # columna de info
LW = 12         # ancho del campo etiqueta
W = 1 + ACOL + 2 + ICOL     # ancho interno de la caja

def emblem_lines():
    """Arte del emblema (monocromo, ACOL de ancho). 1) GALERÍA: el paso brand
    copia el emblema elegido a `{brain}/brand/emblem.txt`. 2) DEFAULT: monograma
    — la inicial del agente en la fuente shadow, enmarcada (auto, distintivo,
    nunca vacío; el doctor sugiere elegir uno de la galería). Falla-suave."""
    try:
        p = os.path.join(_find_brain(), "brand", "emblem.txt")
        with open(p, encoding="utf-8") as fh:
            raw = [ln.rstrip("\n")[:ACOL] for ln in fh]
        if any(s.strip() for s in raw):
            return raw
    except OSError:
        pass
    init = ((AGENT_DISPLAY or "?").strip()[:1] or "?").upper()
    glyph = FONT.get(init, FONT[" "])
    inner = ACOL - 2
    body = ["", ""] + [g.center(inner) for g in glyph] + ["", ""]
    top = "╭" + "─" * (ACOL - 2) + "╮"
    bot = "╰" + "─" * (ACOL - 2) + "╯"
    return [top] + ["│" + b.center(inner) + "│" for b in body] + [bot]

def _field(label, desc):
    """Una fila (label, desc) → 1+ filas envueltas a la columna (el desc que no
    entra en ICOL se parte; la etiqueta va solo en la primera). Evita el
    desborde del borde derecho."""
    lines = wrap(desc, ICOL - LW - 2) if desc else [""]
    return [(label if i == 0 else "", ln) for i, ln in enumerate(lines)]

def info_rows():
    """Filas de la columna de info (der): Skills · Sistema · Dominio — de la
    config del agente. ('##', titulo) = subtítulo; (label, desc) = fila."""
    cats, seen = [], set()
    for c in f"{SKILL_CATS} · investigación · meta".split(" · "):
        c = c.strip()
        if c and c.lower() not in seen:
            seen.add(c.lower()); cats.append(c)
    rows = [("##", "Skills")]
    rows += _field("categorías", " · ".join(cats))
    rows += _field("base", "skill-creator · skill-improver · skill-curator · reload-brain")
    rows += _field("", "deep-research · research-session")
    rows += [("", ""), ("##", "Sistema")]
    rows += _field("memoria", "tiers caliente/tibia/fría · core blocks · Dreaming→DESTILADO")
    rows += _field("loop", "skill loop SIEMPRE activo · bloque 🧠 obligatorio")
    if (SCOPE or "").strip():
        rows += [("", ""), ("##", "Dominio")]
        rows += _field("alcance", SCOPE)
    return rows

def main():
    ICOL = W - 2   # panel de texto a TODO el ancho — SIN columna de
                   # arte (branding en transición: emblema fuera por ahora)
    info = info_rows()
    out = ["\n"]
    _ttl = title_lines(AGENT_DISPLAY)
    _tpad = " " * max(0, (W + 2 - max((len(_t) for _t in _ttl), default=0)) // 2)
    for i, ln in enumerate(_ttl):
        out.append(f"  {_tpad}{ROWCOL[i]}{ln}{R}")
    out.append("")

    _eng = (os.environ.get("WORKSPACE_ENGINE_LABEL") or "").strip()
    head = f" {AGENT_DISPLAY.upper()}-AGENT · {TAGLINE}" + (f" · {_eng}" if _eng else "") + " "   # motor+modelo REAL (dinámico)
    if len(head) > W - 4:
        head = head[:W - 7] + "… "
    side = max(0, (W - len(head)) // 2)
    out.append(f"  {B}╭{'─'*side}{R}{BO}{C}{head}{R}{B}{'─'*(W-side-len(head))}╮{R}")

    for i in range(len(info)):
        if i < len(info):
            label, desc = info[i]
            if label == "##":
                iseg = pad(f"{BO}{C}{desc}{R}", ICOL)
            elif label or desc:
                iseg = pad(f"{WH}{label.ljust(LW)}{R} {DIM}{desc}{R}", ICOL)
            else:
                iseg = " " * ICOL
        else:
            iseg = " " * ICOL
        out.append(f"  {B}│{R} {iseg} {B}│{R}")

    foot = " nacido del template de WORKSPACE "
    fside = max(0, (W - len(foot)) // 2)
    out.append(f"  {B}╰{'─'*fside}{R}{DIM}{foot}{R}{B}{'─'*(W-fside-len(foot))}╯{R}")
    out.append("")
    print("\n".join(out))

if __name__ == "__main__":
    main()
