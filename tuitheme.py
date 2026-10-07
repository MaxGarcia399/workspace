#!/usr/bin/env python3
"""WORKSPACE · tuitheme — tema del TUI (recinto de front.py, banner y config).

El MISMO concepto de tema que el motor web (hubtheme.py): un tema vive en
themes/<id>/ y su theme.json puede declarar un bloque "tui"; este módulo lo
convierte en una PALETA ANSI lista para pintar. La selección es idéntica al
web — env WORKSPACE_THEME > settings ui.theme > bruma — vía hubtheme.resolve_id()
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
DEFAULT_ID = "bruma"
# `olympo` es la PALETA EMBEBIDA (_OLYMPO): el recinto dorado de paridad y el
# fallback por-clave de todo tema. NO vive en themes/ (fue borrado del disco),
# así que resolve_id debe reconocerlo como siempre-resolvible, igual que antes
# hacía el default. Se mantiene separado de DEFAULT_ID: el default (lo que
# arranca una instalación) es bruma; olympo solo se pinta si se pide explícito.
_EMBEDDED_ID = "olympo"
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


# ── BRILLO (ui.brightness): transformación HSL de los roles CROMÁTICOS ──────
# El socio percibe el TUI más APAGADO que el sitio web; la causa real es que el
# web es una pantalla RETROILUMINADA con gradientes — el MISMO hex se percibe
# más vivo ahí. Este control le deja subir (o bajar) luminosidad + saturación
# de la paleta a su gusto, para CUALQUIER tema. Sube solo los roles cromáticos
# (accent/hi/mid/ok/err/bad); jamás toca bg/surface/estructura. El TONO se
# preserva (el acento sigue siendo el acento). En nivel 0 NO se transforma nada
# (la paleta queda byte-idéntica — el memo distingue por nivel).
_BRIGHT_ROLES = ("accent", "hi", "mid", "ok", "err", "bad")
_BRIGHT_RANGE = (-3, 3)        # neutro en 0; negativos apagan, positivos avivan
_BRIGHT_DL = 0.05              # Δ luminosidad por paso (escala 0..1)
_BRIGHT_DS = 0.06              # Δ saturación  por paso (escala 0..1)
_BRIGHT_LMAX = 0.92           # tope duro de L (no reventar a blanco)
_BRIGHT_LMIN = 0.06           # piso duro de L (no colapsar a negro)
_BRIGHT_MIN_CONTRAST = 2.0    # ratio WCAG mínimo del rol contra el fondo


def _brightness_level():
    """ui.brightness: env WORKSPACE_BRIGHTNESS lo pisa (tests herméticos /
    overrides), si no el store. Clamp al rango. Falla-suave ABSOLUTA → 0
    (neutro: sin tuitheme nadie nota diferencia, la paleta no se toca)."""
    lo, hi = _BRIGHT_RANGE
    ov = os.environ.get("WORKSPACE_BRIGHTNESS", "").strip()
    if ov:
        try:
            return max(lo, min(hi, int(ov)))
        except Exception:
            return 0
    try:
        import settings
        v = int(settings.get("ui.brightness", 0))
    except Exception:
        return 0
    return max(lo, min(hi, v))


def _role_rgb(v):
    """RGB (0-255) de un valor de rol: índice 256 (int) o '#rrggbb'."""
    return _idx_rgb(v) if isinstance(v, int) else _hex_rgb(v)


def _rgb_to_hsl(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    d = mx - mn
    if d == 0:
        return 0.0, 0.0, l                     # gris: tono/saturación indefinidos
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d) % 6.0
    elif mx == g:
        h = (b - r) / d + 2.0
    else:
        h = (r - g) / d + 4.0
    return h / 6.0, s, l


def _hue2rgb(p, q, t):
    t %= 1.0
    if t < 1 / 6.0:
        return p + (q - p) * 6.0 * t
    if t < 1 / 2.0:
        return q
    if t < 2 / 3.0:
        return p + (q - p) * (2 / 3.0 - t) * 6.0
    return p


def _hsl_to_rgb(h, s, l):
    if s == 0:
        v = int(round(l * 255))
        return v, v, v
    q = l * (1.0 + s) if l < 0.5 else l + s - l * s
    p = 2.0 * l - q
    return (max(0, min(255, int(round(_hue2rgb(p, q, h + 1 / 3.0) * 255)))),
            max(0, min(255, int(round(_hue2rgb(p, q, h) * 255)))),
            max(0, min(255, int(round(_hue2rgb(p, q, h - 1 / 3.0) * 255)))))


def _rel_lum(rgb):
    """Luminancia relativa WCAG de un RGB (0-255)."""
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b):
    """Ratio de contraste WCAG entre dos RGB (1.0 = idénticos, 21 = máx)."""
    la, lb = _rel_lum(a), _rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _bright_hex(v, level, bg_rgb):
    """`v` (índice 256 o hex) ajustado `level` pasos de brillo → '#rrggbb'.
    level>0 sube L+S (más vivo); level<0 las baja (más apagado). CLAMPS duros
    (L en [LMIN, LMAX], S en [0,1]) y un PISO de contraste legible contra el
    fondo: si el rol cae por debajo del mínimo (típico al APAGAR sobre fondo
    oscuro) se empuja L en la dirección legible hasta cumplir. El TONO (h)
    nunca cambia. level==0 jamás llega aquí (palette lo corta antes)."""
    h, s, l = _rgb_to_hsl(*_role_rgb(v))
    l = min(_BRIGHT_LMAX, max(_BRIGHT_LMIN, l + level * _BRIGHT_DL))
    s = min(1.0, max(0.0, s + level * _BRIGHT_DS))
    rgb = _hsl_to_rgb(h, s, l)
    bg_l = _rel_lum(bg_rgb)
    direction = 1.0 if bg_l < 0.5 else -1.0    # fondo oscuro → aclarar; claro → oscurecer
    guard = 0
    while _contrast(rgb, bg_rgb) < _BRIGHT_MIN_CONTRAST and guard < 48:
        l = min(_BRIGHT_LMAX, max(_BRIGHT_LMIN, l + direction * 0.02))
        nrgb = _hsl_to_rgb(h, s, l)
        if nrgb == rgb:
            break                              # L topó el clamp — sin más margen
        rgb, guard = nrgb, guard + 1
    return "#%02x%02x%02x" % rgb


# ── DETALLE del WORDMARK bajo brillo (fix 2026-10): el gradiente del wordmark
# (spec["wordmark"], típicamente roles mid→accent→hi en bandas) PIERDE su
# contraste interno al subir el brillo — _bright_hex empuja las 3 bandas hacia
# el techo L≤LMAX y CONVERGEN; en 256 la cuantización las separa por accidente,
# en truecolor no hay reja que las separe y el wordmark se ve PLANO. Este helper
# re-expande la luminosidad del gradiente BRILLADO para conservar (al menos) el
# spread ORIGINAL entre bandas: ancla el punto más CLARO (el brillo se mantiene)
# y estira las bandas oscuras hacia abajo. Como el ancla es el tope, ninguna
# banda queda más oscura que su versión a nivel 0 (el spread solo baja desde el
# punto claro). Hue/saturación de cada banda = los de la versión brillada. ──────
def _wordmark_spread(vals, level, bg_rgb):
    """`vals`: valores de color ORIGINALES (sin brillo) de las bandas del
    wordmark (int idx o '#hex'). Devuelve la lista BRILLADA `level` pasos como
    '#rrggbb' conservando el SPREAD de luminosidad original entre bandas. Solo
    para level!=0 (a nivel 0 el wordmark queda byte-idéntico por otra rama)."""
    try:
        origL = [_rgb_to_hsl(*_role_rgb(v))[2] for v in vals]
        orig_spread = max(origL) - min(origL)
        bright = [_bright_hex(v, level, bg_rgb) for v in vals]
        if orig_spread <= 1e-6:
            return bright                      # gradiente plano → nada que estirar
        brightL = [_rgb_to_hsl(*_hex_rgb(h))[2] for h in bright]
        b_spread = max(brightL) - min(brightL)
        if b_spread >= orig_spread - 1e-6:
            return bright                      # el spread sobrevivió → sin tocar
        top = max(brightL)
        scale = orig_spread / b_spread         # >1: re-expande hacia abajo
        out = []
        for h in bright:
            hh, ss, bl = _rgb_to_hsl(*_hex_rgb(h))
            newl = top - (top - bl) * scale
            newl = min(_BRIGHT_LMAX, max(_BRIGHT_LMIN, newl))
            out.append("#%02x%02x%02x" % _hsl_to_rgb(hh, ss, newl))
        return out
    except Exception:
        # falla-suave: sin re-expansión, el gradiente brillado tal cual
        try:
            return [_bright_hex(v, level, bg_rgb) for v in vals]
        except Exception:
            return list(vals)


# ── MODO LUZ ROJA (ui.redlight): pantalla en rojo para madrugadas ───────────
# Confort visual nocturno: remapea TODA la paleta a un rojo/ámbar cálido. Se
# aplica DESPUÉS de tema+brillo (es la última transformación al resolver la
# paleta). Reduce fuerte azul/verde (hue forzado a la banda roja), baja la
# luminosidad general (comprimida a la mitad oscura) y conserva la JERARQUÍA:
# la luminosidad relativa de cada rol se preserva (bg→casi-negro-rojo, texto→
# rojo brillante), así el contraste texto/fondo y el orden de énfasis siguen.
# El acento sigue distinguible porque el ÁMBAR crece con la saturación de
# origen (roles cálidos/saturados = ámbar; neutros = rojo puro). En mono no se
# pinta color → no-op (degrada suave). OFF = la paleta de hoy, intocada.
_RL_HUE_RED = 0.015           # tono base (rojo) en la escala 0..1 del HSL
_RL_HUE_AMBER = 0.050         # lift de tono hacia ámbar, escalado por saturación
_RL_SAT = 0.85                # saturación fija alta (rojo vivo pero nocturno)
_RL_L_FLOOR = 0.05            # piso de luminosidad (negro-rojo, no negro puro)
_RL_L_SPAN = 0.55             # techo = floor + span → noche cómoda, sin blancos


def _redlight_on():
    """ui.redlight del store. Falla-suave ABSOLUTA → False (sin tuitheme nadie
    nota diferencia: la paleta no se toca)."""
    try:
        import settings
        return bool(settings.enabled("ui.redlight", default=False))
    except Exception:
        return False


def _redlight_rgb(rgb):
    """Un RGB (0-255) remapeado a la gama roja/ámbar nocturna. Preserva la
    luminosidad RELATIVA (jerarquía/contraste) y fuerza el tono a la banda
    roja; el ámbar crece con la saturación original (acento distinguible)."""
    h, s, l = _rgb_to_hsl(*rgb)
    hue = _RL_HUE_RED + _RL_HUE_AMBER * min(1.0, s)
    nl = _RL_L_FLOOR + _RL_L_SPAN * max(0.0, min(1.0, l))
    return _hsl_to_rgb(hue, _RL_SAT, nl)


def _redlight_hex(v):
    """Valor de color (int idx o '#hex') → '#rrggbb' en la gama roja nocturna."""
    try:
        return "#%02x%02x%02x" % _redlight_rgb(_role_rgb(v))
    except Exception:
        return v


# ── selección del tema (mismo mecanismo que el web) ─────────────────────────
def _settings_theme():
    """ui.theme del store. Un id GUARDADO que ya no está instalado (tema
    borrado de themes/ — p.ej. la poda 2026-10-02: olympo/papel/slate/bosque)
    cae a `bruma` (el branding del sitio web), no al dorado embebido: el tema
    guardado se quitó a propósito y bruma mantiene el branding consistente.
    env/explicit NO pasan por aquí (conservan la falla-suave clásica → olympo
    embebido)."""
    try:
        import settings
        v = settings.get("ui.theme", DEFAULT_ID)
        if not isinstance(v, str):
            return DEFAULT_ID
        vv = v.strip().lower()
        if (_ID_RX.match(vv)
                and not os.path.isfile(os.path.join(THEMES_DIR, vv, "theme.json"))
                and os.path.isfile(os.path.join(THEMES_DIR, "bruma", "theme.json"))):
            return "bruma"
        return v
    except Exception:
        return DEFAULT_ID


def resolve_id(explicit=None):
    """Id del tema del HUB/TUI: explicit > env WORKSPACE_THEME > ui.theme > bruma.
    LEE ui.theme (el tema del HUB), NO ui.web_theme (ese es del dev panel, vía
    hubtheme). Antes delegaba a hubtheme.resolve_id() → terminaba leyendo
    ui.web_theme y el hub salía con el tema del web (bug 'son los mismos'). Valida
    contra themes/<id>/theme.json (misma precedencia, resolución PROPIA)."""
    for cand in (explicit, os.environ.get("WORKSPACE_THEME"), _settings_theme()):
        cand = (cand or "").strip().lower()
        if not cand or not _ID_RX.match(cand):
            continue
        if cand == DEFAULT_ID or cand == _EMBEDDED_ID:
            return cand           # default + paleta embebida: siempre resolvibles
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
    level = _brightness_level()
    redlight = _redlight_on()
    key = (tid, mode, bg, level, redlight)
    if key in _memo:
        return _memo[key]
    spec = _merged(_tui_block(tid))
    mono = (mode == "mono")
    # mono EFECTIVO para las TRANSFORMACIONES cromáticas (brillo/wordmark/luz
    # roja): un tema B/N POR DECLARACIÓN (tui.mono=true) debe quedar en grises
    # aunque la terminal tenga color — subirle saturación (brillo) o remapearlo
    # a rojo (luz roja) mancharía un tema que PROMETE ser B/N (invariante del
    # tema `mono`, test_hub_layout). NO afecta a `mono` (R/OSC/MONO/_seq siguen
    # usándolo): un tema B/N en truecolor SÍ emite sus grises y resets.
    mono_eff = mono or bool(spec.get("mono"))
    if bg and not mono:
        spec["osc"] = dict(spec["osc"] or {}, bg=bg)
    bg_hex = bg or (spec.get("osc") or {}).get("bg") or "#000000"
    try:
        bg_rgb = _hex_rgb(bg_hex) if _HEX_RX.match(bg_hex or "") else (0, 0, 0)
    except Exception:
        bg_rgb = (0, 0, 0)
    # Valores ORIGINALES de los roles del wordmark (ANTES del brillo): el fix de
    # DETALLE re-expande el gradiente desde aquí, no desde los roles ya brillados
    # (que convergen). Snapshot barato (dict de ≤12 enteros/hex).
    orig_role_vals = dict(spec["roles"])
    # BRILLO (ui.brightness): sube/baja L+S de los roles CROMÁTICOS para que el
    # socio ajuste qué tan vivo se ve el TUI (ver _bright_hex). Nivel 0 = NO se
    # toca NADA (paleta byte-idéntica). En mono (terminal o tema B/N) no hay
    # color que avivar — y avivar grises les colaría saturación (bug anti-mono).
    if level != 0 and not mono_eff:
        for rk in _BRIGHT_ROLES:
            if rk in spec["roles"]:
                try:
                    spec["roles"][rk] = _bright_hex(spec["roles"][rk], level, bg_rgb)
                except Exception:
                    pass                        # falla-suave: ese rol sin ajustar

    # WORDMARK: resolver sus 6 bandas a valores concretos. A nivel 0 (o mono)
    # usa los roles tal cual → byte-idéntico a hoy. Con brillo, re-expande el
    # gradiente para que las bandas NO converjan (fix de detalle en truecolor).
    def _wm_val(w):                              # rol → valor; color literal → él mismo
        return spec["roles"][w] if w in spec["roles"] else w
    if level != 0 and not mono_eff:
        wm_src = [orig_role_vals[w] if w in orig_role_vals else w
                  for w in spec["wordmark"]]
        wcol_vals = _wordmark_spread(wm_src, level, bg_rgb)
    else:
        wcol_vals = [_wm_val(w) for w in spec["wordmark"]]

    # LUZ ROJA (ui.redlight): última transformación — remapea TODA la paleta a
    # la gama roja/ámbar nocturna (ver _redlight_rgb). En mono (terminal o tema
    # B/N declarado) no hay color que remapear (degrada suave → no-op): un tema
    # que promete ser B/N no se vuelve rojo. OFF = paleta intocada.
    if redlight and not mono_eff:
        for rk in list(spec["roles"]):
            spec["roles"][rk] = _redlight_hex(spec["roles"][rk])
        spec["stars"]["dim"] = [_redlight_hex(v) for v in spec["stars"]["dim"]]
        spec["stars"]["mid"] = [_redlight_hex(v) for v in spec["stars"]["mid"]]
        spec["stars"]["hi"] = _redlight_hex(spec["stars"]["hi"])
        spec["fire"] = [_redlight_hex(v) for v in spec["fire"]]
        spec["ember"] = [_redlight_hex(v) for v in spec["ember"]]
        spec["off"] = _redlight_hex(spec["off"])
        wcol_vals = [_redlight_hex(v) for v in wcol_vals]
        if spec.get("osc") and spec["osc"].get("bg"):
            spec["osc"] = dict(spec["osc"], bg=_redlight_hex(spec["osc"]["bg"]))

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
        WCOL=[s(v) for v in wcol_vals],
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
