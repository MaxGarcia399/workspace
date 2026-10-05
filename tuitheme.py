#!/usr/bin/env python3
"""WORKSPACE · tuitheme — tema del TUI (recinto de front.py, banner y config).

El MISMO concepto de tema que el motor web (hubtheme.py): un tema vive en
themes/<id>/ y su theme.json puede declarar un bloque "tui"; este módulo lo
convierte en una PALETA ANSI lista para pintar. La selección es idéntica al
web — env WORKSPACE_THEME > settings ui.theme > olympo — vía hubtheme.resolve_id()
(con la misma precedencia re-implementada aquí como falla-suave si hubtheme
no está). UN solo concepto de tema en todo el harness.

PARIDAD: olympo (default) pinta LOS MISMOS índices 256 de siempre (214/178/
221/230/136/94/242…). Un valor ENTERO en el spec = índice 256 EXACTO — jamás
se re-cuantiza (ni siquiera en truecolor). El look actual no cambia si nadie
elige tema.

DEGRADACIÓN: '#rrggbb' → truecolor (38;2) si la terminal lo anuncia
(COLORTERM=truecolor/24bit, Windows Terminal, iTerm2/WezTerm/ghostty/kitty)
→ si no, 256 (38;5, cuantizado al cubo xterm) → 16 colores (30-37/90-97) en
TERMs viejas → NO_COLOR o TERM=dumb → SIN ANSI (mono). Override de prueba:
WORKSPACE_COLOR=mono|16|256|truecolor.

Cero dependencias (stdlib). Falla-suave ABSOLUTA: cualquier problema en un
manifiesto (clave ausente, color malformado, JSON roto) → el valor de olympo
para ESA clave. El TUI jamás se rompe por un tema.
"""
import json
import os
import re
import types

ROOT = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(ROOT, "themes")
DEFAULT_ID = "olympo"
# contrato de ids de tema — la fuente es hubtheme (mismo regex en ambos
# motores; fallback identico si hubtheme esta amputado)
try:
    from hubtheme import _ID_RX
except Exception:                                    # pragma: no cover
    _ID_RX = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_HEX_RX = re.compile(r"^#[0-9a-fA-F]{6}$")

# ── olympo (embebido): el recinto DORADO de siempre, en índices 256 fijos.
#    Es el fallback por-clave de TODO tema — paridad por construcción. ──────
_OLYMPO = {
    "roles": {
        "text": 230,          # WH  · texto brillante
        "hi": 221,            # C   · dorado claro (selección/acentos)
        "accent": 214,        # B   · dorado principal
        "mid": 178,           # B2  · dorado medio (avisos)
        "dim": 136,           # DIM · ámbar tenue
        "dark": 94,           # DK  · dorado oscuro (separadores)
        "grey": 242,          # GREY
        "inactive": 136,      # HERRAMIENTAS/DIOSES apagados
        "inactive_alt": 238,  # LATIDO no seleccionado
        "err": 196,           # ✗ errores
        "ok": 108,            # verde (config)
        "bad": 174,           # rojo suave (config)
    },
    "stars": {"dim": [236, 237, 239, 240], "mid": [243, 246], "hi": 251},
    "fire": [52, 88, 124, 160, 196, 197, 203, 209, 210, 216, 217, 224],
    "ember": [58, 94, 130, 166],
    "off": 240,
    "wordmark": ["mid", "mid", "accent", "accent", "hi", "hi"],
    "glyphs": {"box": "╭╮╰╯│─", "pointer": "❯", "bracket_l": "❮",
               "bracket_r": "❯", "orn": "✦", "sep": "─", "base": "▁",
               # iconos de los widgets del hub (hublayout: rama git, working
               # tree limpio, latido, bus) — overrideables por tema (un tema
               # para Windows los baja a ASCII angosto-seguro).
               "branch": "⎇", "check": "✓", "heart": "♥", "mail": "✉",
               "star_d": None, "star_h": None},
    "osc": None,   # olympo usa el tema OSC 'workspace' de themes.json (legacy)
}


# ── capacidad de color de la terminal ───────────────────────────────────────
def color_mode():
    """'truecolor' | '256' | '16' | 'mono'. Env WORKSPACE_COLOR fuerza uno
    (probar degradación sin cambiar de terminal). NO_COLOR / TERM=dumb → mono.
    Default histórico del recinto: 256 (lo que front.py emitía siempre)."""
    ov = (os.environ.get("WORKSPACE_COLOR") or "").strip().lower()
    if ov in ("mono", "16", "256", "truecolor"):
        return ov
    if (os.environ.get("NO_COLOR") or "") != "":
        return "mono"
    term = (os.environ.get("TERM") or "").lower()
    if term == "dumb":
        return "mono"
    ct = (os.environ.get("COLORTERM") or "").lower()
    if "truecolor" in ct or "24bit" in ct:
        return "truecolor"
    if os.environ.get("WT_SESSION"):                     # Windows Terminal
        return "truecolor"
    if (os.environ.get("TERM_PROGRAM") or "") in ("iTerm.app", "WezTerm", "ghostty"):
        return "truecolor"
    if "kitty" in term or term.endswith("-direct"):
        return "truecolor"
    if term in ("linux", "vt100", "vt220", "ansi", "xterm-color", "xterm-16color"):
        return "16"
    return "256"


# ── cuantización: hex → 256 → 16 ────────────────────────────────────────────
_CUBE = (0, 95, 135, 175, 215, 255)
# xterm defaults de los 16 básicos (para elegir el más cercano por distancia)
_ANSI16 = [(0, 0, 0), (205, 0, 0), (0, 205, 0), (205, 205, 0),
           (0, 0, 238), (205, 0, 205), (0, 205, 205), (229, 229, 229),
           (127, 127, 127), (255, 0, 0), (0, 255, 0), (255, 255, 0),
           (92, 92, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]


def _idx_rgb(n):
    """RGB de un índice xterm-256."""
    if n < 16:
        return _ANSI16[n]
    if n >= 232:
        g = 8 + (n - 232) * 10
        return (g, g, g)
    n -= 16
    return (_CUBE[n // 36], _CUBE[(n // 6) % 6], _CUBE[n % 6])


def _hex_rgb(s):
    return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))


def _dist(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def nearest256(rgb):
    """Índice 16-255 más cercano (los 0-15 se evitan: los redefine cada
    terminal y el resultado sería impredecible)."""
    best, bd = 16, 1 << 30
    for n in range(16, 256):
        d = _dist(rgb, _idx_rgb(n))
        if d < bd:
            best, bd = n, d
    return best


def nearest16(rgb):
    """Código SGR 30-37/90-97 del básico más cercano."""
    best, bd = 0, 1 << 30
    for i, c in enumerate(_ANSI16):
        d = _dist(rgb, c)
        if d < bd:
            best, bd = i, d
    return (30 + best) if best < 8 else (90 + best - 8)


def _valid_color(v):
    """int 0-255 (índice 256 fijo) o '#rrggbb'."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return 0 <= v <= 255
    return isinstance(v, str) and bool(_HEX_RX.match(v))


def _seq(v, mode):
    """Secuencia ANSI de foreground para el color `v` en el modo dado.
    int → 38;5;n EXACTO en 256/truecolor (paridad olympo); hex → 38;2 en
    truecolor, cuantizado en 256/16. mono → ''."""
    if mode == "mono" or not _valid_color(v):
        return ""
    if isinstance(v, int):
        if mode == "16":
            return "\033[%dm" % nearest16(_idx_rgb(v))
        return "\033[38;5;%dm" % v
    rgb = _hex_rgb(v)
    if mode == "truecolor":
        return "\033[38;2;%d;%d;%dm" % rgb
    if mode == "16":
        return "\033[%dm" % nearest16(rgb)
    return "\033[38;5;%dm" % nearest256(rgb)


# ── selección del tema (mismo mecanismo que el web) ─────────────────────────
def _settings_theme():
    """ui.theme del store. Un id GUARDADO que ya no está instalado (tema
    borrado de themes/ — p.ej. la poda 2026-10-02: olympo/papel/slate/bosque)
    cae a `rose` (el default del hub), no al dorado embebido: el socio quitó
    ese tema a propósito. env/explicit NO pasan por aquí (conservan la
    falla-suave clásica → olympo embebido)."""
    try:
        import settings
        v = settings.get("ui.theme", DEFAULT_ID)
        if not isinstance(v, str):
            return DEFAULT_ID
        vv = v.strip().lower()
        if (_ID_RX.match(vv)
                and not os.path.isfile(os.path.join(THEMES_DIR, vv, "theme.json"))
                and os.path.isfile(os.path.join(THEMES_DIR, "rose", "theme.json"))):
            return "rose"
        return v
    except Exception:
        return DEFAULT_ID


def resolve_id(explicit=None):
    """Id del tema del HUB/TUI: explicit > env WORKSPACE_THEME > ui.theme > olympo.
    LEE ui.theme (el tema del HUB), NO ui.web_theme (ese es del dev panel, vía
    hubtheme). Antes delegaba a hubtheme.resolve_id() → terminaba leyendo
    ui.web_theme y el hub salía con el tema del web (bug 'son los mismos'). Valida
    contra themes/<id>/theme.json (misma precedencia, resolución PROPIA)."""
    for cand in (explicit, os.environ.get("WORKSPACE_THEME"), _settings_theme()):
        cand = (cand or "").strip().lower()
        if not cand or not _ID_RX.match(cand):
            continue
        if cand == DEFAULT_ID:
            return cand
        if os.path.isfile(os.path.join(THEMES_DIR, cand, "theme.json")):
            return cand
    return DEFAULT_ID


def _tui_block(tid):
    """Bloque "tui" del manifiesto del tema. {} si falta / roto / id inválido."""
    if not (isinstance(tid, str) and _ID_RX.match(tid)):
        return {}
    try:
        with open(os.path.join(THEMES_DIR, tid, "theme.json"),
                  encoding="utf-8") as fh:
            m = json.load(fh)
        t = m.get("tui") if isinstance(m, dict) else None
        return t if isinstance(t, dict) else {}
    except Exception:
        return {}


# ── merge spec ← olympo (falla-suave POR CLAVE) ─────────────────────────────
def _color_list(v, fallback, lo=1, hi=32):
    if (isinstance(v, list) and lo <= len(v) <= hi
            and all(_valid_color(x) for x in v)):
        return list(v)
    return list(fallback)


def _merged(tui):
    """Spec completo del tema: cada clave inválida/ausente → la de olympo."""
    out = {"roles": dict(_OLYMPO["roles"]),
           "stars": {"dim": list(_OLYMPO["stars"]["dim"]),
                     "mid": list(_OLYMPO["stars"]["mid"]),
                     "hi": _OLYMPO["stars"]["hi"]},
           "fire": list(_OLYMPO["fire"]), "ember": list(_OLYMPO["ember"]),
           "off": _OLYMPO["off"], "wordmark": list(_OLYMPO["wordmark"]),
           "glyphs": dict(_OLYMPO["glyphs"]), "osc": None,
           # `mono: true` = tema MONOCROMO por declaración (no por límite de
           # la terminal). Los consumidores que pintan color PROPIO fuera de
           # los roles — p.ej. la marca por agente de hublayout._agent_ink,
           # que hardcodea 256 — deben ceder a los roles del tema. Sin esto un
           # tema B/N se ve manchado (2026-07-15). Default: False.
           "mono": False}
    roles = tui.get("roles") if isinstance(tui.get("roles"), dict) else {}
    for k in out["roles"]:
        if _valid_color(roles.get(k)):
            out["roles"][k] = roles[k]
    stars = tui.get("stars") if isinstance(tui.get("stars"), dict) else {}
    out["stars"]["dim"] = _color_list(stars.get("dim"), out["stars"]["dim"], 1, 8)
    out["stars"]["mid"] = _color_list(stars.get("mid"), out["stars"]["mid"], 1, 8)
    if _valid_color(stars.get("hi")):
        out["stars"]["hi"] = stars["hi"]
    out["fire"] = _color_list(tui.get("fire"), out["fire"], 4, 24)
    out["ember"] = _color_list(tui.get("ember"), out["ember"], 2, 8)
    if isinstance(tui.get("mono"), bool):
        out["mono"] = tui["mono"]
    if _valid_color(tui.get("off")):
        out["off"] = tui["off"]
    wm = tui.get("wordmark")
    if (isinstance(wm, list) and len(wm) == 6
            and all((w in out["roles"]) or _valid_color(w) for w in wm)):
        out["wordmark"] = list(wm)
    g = tui.get("glyphs") if isinstance(tui.get("glyphs"), dict) else {}
    for k in ("pointer", "bracket_l", "bracket_r", "orn", "sep", "base",
              "branch", "check", "heart", "mail"):
        v = g.get(k)
        if isinstance(v, str) and 1 <= len(v) <= 2:
            out["glyphs"][k] = v
    if isinstance(g.get("box"), str) and len(g["box"]) == 6:
        out["glyphs"]["box"] = g["box"]
    for k in ("star_d", "star_h"):     # glifos del cielo (listas de 1-char)
        v = g.get(k)
        if (isinstance(v, list) and 1 <= len(v) <= 8
                and all(isinstance(x, str) and len(x) == 1 for x in v)):
            out["glyphs"][k] = list(v)
    osc = tui.get("osc") if isinstance(tui.get("osc"), dict) else {}
    osc = {k: osc[k] for k in ("bg", "fg", "cursor")
           if isinstance(osc.get(k), str) and _HEX_RX.match(osc[k])}
    out["osc"] = osc or None
    return out


# ── paleta pública ──────────────────────────────────────────────────────────
_memo = {}


def palette(theme_id=None):
    """Paleta ANSI del tema activo (o del explícito), lista para pintar.
    Nombres = los históricos del recinto (B/B2/C/WH/DIM/DK/…) para que el
    consumo sea un assignment. Jamás levanta: todo problema → olympo."""
    try:
        tid = resolve_id(theme_id)
    except Exception:
        tid = DEFAULT_ID
    mode = color_mode()
    import theme
    bg = theme.background_color()
    key = (tid, mode, bg)
    if key in _memo:
        return _memo[key]
    spec = _merged(_tui_block(tid))
    mono = (mode == "mono")
    if bg and not mono:
        spec["osc"] = dict(spec["osc"] or {}, bg=bg)

    def s(v):
        return _seq(v, mode)

    roles = {k: s(v) for k, v in spec["roles"].items()}
    P = types.SimpleNamespace(
        id=tid, mode=mode,
        # MONOCROMO: por declaración del tema (spec["mono"]) O por límite de
        # la terminal. Los consumidores que pintan color propio fuera de los
        # roles deben ceder a los roles cuando esto es True.
        MONO=bool(spec.get("mono")) or mono,
        R="" if mono else "\033[0m", BO="" if mono else "\033[1m",
        WH=roles["text"], C=roles["hi"], B=roles["accent"], B2=roles["mid"],
        DIM=roles["dim"], DK=roles["dark"], GREY=roles["grey"],
        INACTIVE=roles["inactive"], INACTIVE_HB=roles["inactive_alt"],
        ERR=roles["err"], OK=roles["ok"], BAD=roles["bad"],
        STAR_DIM=[s(v) for v in spec["stars"]["dim"]],
        STAR_MID=[s(v) for v in spec["stars"]["mid"]],
        STAR_HI=s(spec["stars"]["hi"]),
        FIRE=[s(v) for v in spec["fire"]],
        EMBER=[s(v) for v in spec["ember"]],
        OFF=s(spec["off"]),
        WCOL=[roles[w] if w in roles else s(w) for w in spec["wordmark"]],
        GLYPHS=dict(spec["glyphs"]),
        OSC=(None if mono else spec["osc"]),
    )
    _memo[key] = P
    return P


if __name__ == "__main__":
    # demo: `python3 tuitheme.py [tema]` — muestra la paleta del tema
    import sys
    P = palette(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"tema {P.id} · modo {P.mode}")
    for k in ("WH", "C", "B", "B2", "DIM", "DK", "GREY", "ERR", "OK"):
        v = getattr(P, k)
        print(f"  {v}{k:12s} ██████ muestra{P.R}")
    print("  FIRE  " + "".join(f"{c}█{P.R}" for c in P.FIRE))
    print("  STARS " + "".join(f"{c}✦{P.R}" for c in P.STAR_DIM + P.STAR_MID + [P.STAR_HI]))
