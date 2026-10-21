#!/usr/bin/env python3
"""WORKSPACE · theme_render — UNA paleta semántica, todas las superficies.

Lección de Omarchy (acción 8 del reporte): un tema declara una paleta
SEMÁNTICA (accent, background, foreground, muted…) y cada consumidor sale de
ella por PLANTILLA. Aquí las plantillas viven en `templates/theme/`:

    osc.json.tpl                   fondo/tinta/cursor de la terminal (OSC 10/11/12)
    tui.json.tpl                   bloque `tui` (roles ANSI del recinto)
    web.json.tpl                   `web.tokens` del dev panel
    engine-<motor>.json.tpl        tema DENTRO del motor (claude-code, codex)

Agregar un motor = dropear `engine-<motor>.json.tpl` (y anotarlo en ENGINES).
  · claude-code → ~/.claude/themes/<n>.json (`custom:<n>` en settings).
  · codex → $CODEX_HOME/themes/workspace-<agente>.tmTheme (plist de
    TextMate; la plantilla describe sus `settings` en JSON y aquí se
    serializa con plistlib). VERIFICADO con codex 0.162: un .tmTheme ahí se
    elige con `-c tui.theme="<nombre>"` y pinta la barra nativa — modelo =
    `entity.name.type`, contexto = `constant.numeric`, límites =
    `keyword.operator`, permisos = `storage.modifier`, proyecto = `string` —
    además del resaltado de código y diffs. Un archivo inválido → codex avisa
    y usa su default.
  · antigravity → SIN plantilla in-app: sus `colorScheme` son fijos
    (terminal/dark/light/…). Con "terminal" (default) su UI usa los colores
    ANSI básicos, que Workspace recolorea por corrida con OSC 4 (ver
    ansi_slots) — no se escribe nada en su configuración.

De dónde sale la paleta de un tema (`palette_from_manifest`):
  1. el bloque `palette` de `themes/<id>/theme.json` (ADITIVO, opcional);
  2. si falta una clave, se DERIVA de lo que el tema ya declara (`web.tokens`,
     `tui.osc`, `tui.roles`, `swatches`) — los 14 temas existentes ya tienen
     paleta sin tocarlos;
  3. `complete()` rellena el resto con mezclas (`mix`) y neutros oscuros.

LEGIBLE en el motor (2026-10-20, «textos en negro»): lo que ven los motores
(`engine_palette`) sale del fondo que Workspace PINTA en la terminal (tui.osc
+ fondo elegido aparte + luz roja), no del web, y cada color de lectura queda
con contraste ≥3:1 (la tinta ≥4.5:1) sobre ese fondo (`legible`). El tema de
Claude Code fija TODOS sus tokens de texto desde la paleta (su base traía un
`subtle` gris 80 casi invisible sobre fondo oscuro), legibles también como
los pinta en 256 colores (Terminal.app, `cc256`), y su `base` dark/light usa
la fórmula de Claude Code (`is_light`). Prueba: tests/test_contraste_motores.

Regla de compatibilidad: lo HECHO A MANO GANA. Un bloque `tui`/`web.tokens`
explícito pisa al renderizado (clave por clave), y `stage_write` jamás pisa un
archivo que el usuario editó tras generarlo. Sin `palette` en el manifiesto,
tuitheme/hubtheme pintan EXACTAMENTE lo de siempre (nada cambia en pantalla).

ESCRITURA ATÓMICA (staging): `stage_write` renderiza todo a temporales y
reemplaza de un golpe; si algo falla, lo anterior queda intacto ("el TUI jamás
se rompe por un tema"). Hook opcional `theme-set` (estilo Omarchy): un script
del usuario en `<estado>/hooks/` que corre tras cambiar ui.theme, con timeout
y falla-suave (`run_theme_set_hook`).

stdlib puro (3.9+). Ninguna función pública levanta salvo `render()` (que es
la que DEBE fallar antes de escribir nada).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading

import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)

ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(ROOT, "templates", "theme")   # los tests lo parchan

_HEX_RX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ID_RX = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

# ── la paleta semántica ─────────────────────────────────────────────────────
SEMANTIC_KEYS = ("background", "foreground", "cursor", "accent", "accent_2",
                 "accent_hi", "muted", "faint", "surface", "border",
                 "success", "warning", "danger", "info")

# Derivación desde lo que un manifiesto YA declara (primera fuente válida gana).
# (bloque, clave) — bloque: tokens = web.tokens · osc = tui.osc · roles = tui.roles
# Fondo y tinta salen primero de `tui.osc`: es lo que se PINTA en la terminal
# donde corre el motor (oficina-8bit tiene un web claro y una terminal oscura;
# derivar del web le daba al motor tinta casi negra sobre azul noche).
_DERIVE = {
    "background": (("osc", "bg"), ("tokens", "bg")),
    "foreground": (("osc", "fg"), ("tokens", "text"), ("roles", "text")),
    "cursor":     (("osc", "cursor"),),
    "accent":     (("tokens", "accent"), ("roles", "accent"), ("swatch", 0)),
    "accent_2":   (("tokens", "accent-2"), ("roles", "mid"), ("swatch", 1)),
    "accent_hi":  (("tokens", "accent-hi"), ("roles", "hi")),
    "muted":      (("tokens", "dim"), ("roles", "dim")),
    "faint":      (("tokens", "faint"), ("roles", "grey")),
    "surface":    (("tokens", "surface"),),
    "border":     (("tokens", "border"), ("roles", "inactive_alt")),
    "success":    (("tokens", "green"), ("roles", "ok")),
    "warning":    (("tokens", "amber"),),
    "danger":     (("tokens", "red"), ("roles", "err")),
    "info":       (("tokens", "blue"),),
}

# Neutros de último recurso (oscuro, legible). El gris de background/foreground
# es el mismo del preset 'gray' de los agentes (agent_admin.COLOR_THEMES).
_BASE = {"background": "#121316", "foreground": "#e6e8ee", "accent": "#d2a64b",
         "success": "#8fc3a8", "warning": "#dcba84", "danger": "#dd7d88",
         "info": "#8fb8d8"}

# Motores: plantilla in-app conocida, o None = hook documentado SIN plantilla
# (formato no verificable → no se inventa; el motor solo recibe la paleta OSC
# de terminal, que sirve con cualquier CLI). Agregar un motor = poner aquí su
# archivo y dropear la plantilla en templates/theme/.
ENGINES = {
    "claude-code": "engine-claude-code.json.tpl",   # ~/.claude/themes/<n>.json (custom:<n>)
    "codex": None,          # sin JSON de Claude Code: su tema va por NATIVE_THEMES
    "antigravity": None,    # colorScheme fijos → recoloreo ANSI por OSC 4 (ansi_slots)
}
#: Motores con tema in-app en SU propio formato (no el JSON de Claude Code
#: que agent_admin guarda en themes-cc/ — por eso NO van en ENGINES, cuyo
#: engine_supported() significa justo eso). sync_engine_theme los escribe
#: donde el motor los lee.
NATIVE_THEMES = {
    "codex": "engine-codex.json.tpl",   # → $CODEX_HOME/themes/workspace-<n>.tmTheme
}


def _hex(v):
    return v.lower() if isinstance(v, str) and _HEX_RX.match(v) else None


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def mix(a, b, pct):
    """Mezcla lineal en RGB: `pct` (0..1) hacia `b`. mix(bg, fg, .15) = el bg
    un 15% hacia el texto (superficies, bordes). Hex → hex."""
    pct = max(0.0, min(1.0, float(pct)))
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * pct)) for x, y in zip(ra, rb))


def _lum(h):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


# ── contraste (lo que el motor pinta sobre el fondo que Workspace dejó) ─────
TEXT_MIN = 4.5      # texto principal (WCAG AA)
UI_MIN = 3.0        # texto secundario, bordes y marcas (WCAG 1.4.11)
_MARGIN = 0.05      # colchón contra el redondeo a 8 bits por canal


def is_light(h):
    """¿Fondo claro? La MISMA fórmula de Claude Code (decide dark/light con la
    respuesta de OSC 11) y de theme._is_light: luma Rec.709 sobre el sRGB SIN
    linealizar > 0.5. Con otra fórmula Workspace y el motor discrepan justo en
    los fondos medios."""
    r, g, b = _rgb(h)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0 > 0.5


def contrast(a, b):
    """Razón de contraste WCAG entre dos hex (1 = iguales, 21 = negro/blanco)."""
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def cc256(h):
    """Cómo pinta Claude Code un color en 256 colores (Terminal.app: lo fuerza
    a nivel 2): la conversión de chalk/ansi-styles — grises a la rampa
    232-255, el resto REDONDEANDO cada canal al cubo 6×6×6 (no al más
    cercano: 40 → 95, 80 → 135). Devuelve el hex que de verdad se ve."""
    import math

    def jsround(x):                     # Math.round de JS (.5 hacia arriba)
        return int(math.floor(x + 0.5))
    r, g, b = _rgb(h)
    if r == g == b:
        if r < 8:
            return "#000000"
        if r > 248:
            return "#ffffff"
        v = 8 + 10 * jsround((r - 8) / 247.0 * 24)
        return "#%02x%02x%02x" % (v, v, v)
    lv = (0, 95, 135, 175, 215, 255)
    return "#%02x%02x%02x" % tuple(lv[jsround(c / 255.0 * 5)] for c in (r, g, b))


def legible(color, bg, ratio=UI_MIN, quant=None):
    """`color` con al menos `ratio` de contraste contra `bg`, sin cambiar su
    tono: se aclara (fondo oscuro) u oscurece (fondo claro) lo justo. Si ni el
    blanco ni el negro llegan (un fondo medio), queda el extremo que más da.
    `quant` (hex → hex) simula cómo lo pinta el motor (cc256: Claude Code en
    256 colores); el resultado debe cumplir también así. Jamás levanta."""
    import colorsys
    c, b = _hex(color), _hex(bg)
    if not b:
        return c or color
    if not c:
        c = "#ffffff" if contrast("#ffffff", b) >= contrast("#000000", b) else "#000000"
    need = ratio + _MARGIN

    def ok(x):
        return (contrast(x, b) >= need
                and (quant is None or contrast(quant(x), b) >= need))
    if ok(c):
        return c
    up = contrast("#ffffff", b) >= contrast("#000000", b)
    r, g, bl = _rgb(c)
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, bl / 255.0)
    steps = int(((1.0 - l) if up else l) * 100) + 1
    for i in range(1, steps + 1):
        nl = min(1.0, l + i / 100.0) if up else max(0.0, l - i / 100.0)
        x = "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in colorsys.hls_to_rgb(h, nl, s))
        if ok(x):
            return x
    return "#ffffff" if up else "#000000"


#: Claves de la paleta que alguien LEE sobre el fondo (texto, marcas, bordes)
#: y el mínimo que deben dar contra él. surface/border son fondos: no van.
_LEGIBLE = (("foreground", TEXT_MIN), ("cursor", UI_MIN), ("muted", UI_MIN),
            ("faint", UI_MIN), ("accent", UI_MIN), ("accent_2", UI_MIN),
            ("accent_hi", UI_MIN), ("success", UI_MIN), ("warning", UI_MIN),
            ("danger", UI_MIN), ("info", UI_MIN))


def legible_palette(p):
    """Paleta completa con cada color de lectura legible sobre su `background`
    (_LEGIBLE). Un tema que ya cumple sale idéntico."""
    out = complete(p)
    bg = out["background"]
    for k, ratio in _LEGIBLE:
        out[k] = legible(out[k], bg, ratio)
    return out


# ── los 16 colores ANSI (OSC 4) desde la paleta ─────────────────────────────
#: (casilla, clave de la paleta que la inspira, tono canónico en grados). El
#: color del tema se usa tal cual si cae a ≤20° de su tono; si no, se gira a
#: ese tono con su misma luz y saturación: el «rojo» de un programa sigue
#: siendo rojo y el azul y el cian no salen iguales.
_ANSI_HUES = ((1, "danger", 355), (2, "success", 145), (3, "warning", 40),
              (4, "info", 215), (5, "accent_2", 315), (6, "info", 180))


def _hls(h):
    import colorsys
    r, g, b = _rgb(h)
    return colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)


def _from_hls(h, l, s):
    import colorsys
    return "#%02x%02x%02x" % tuple(int(round(v * 255))
                                   for v in colorsys.hls_to_rgb(h % 1.0, l, s))


def _hue_gap(c, deg):
    d = abs(_hls(c)[0] * 360.0 - deg) % 360.0
    return min(d, 360.0 - d)


def _toward_hue(c, deg, keep=True):
    """`c` si ya es de ese tono (≤20°, y `keep`) o es un gris (temas B/N); si
    no, girado a `deg` conservando luz y saturación."""
    h, l, s = _hls(c)
    if s < 0.08 or (keep and _hue_gap(c, deg) <= 20.0):
        return c
    return _from_hls(deg / 360.0, l, s)


def ansi16(palette):
    """Los 16 colores ANSI (0-15) para fijar con OSC 4, desde la paleta
    (completada y legible) — todos medidos contra su `background`:
      · 1-6 rojo, verde, amarillo, azul, magenta, cian (_ANSI_HUES), ≥3:1;
        9-14 sus brillantes, un paso más lejos del fondo, ≥3:1.
      · 7 y 15 (blancos) ≥4.5:1 — en un tema claro, tinta oscura.
      · 8 (gris) el tenue del tema, ≥3:1.
      · 0 (negro): sobre fondo oscuro un gris oscuro que se distingue del
        fondo (es el fondo de barras y resaltados); sobre fondo claro, tinta.
    Un tema B/N (mono, blanco) da una paleta B/N."""
    p = legible_palette(palette)
    bg, fg = p["background"], p["foreground"]
    dark = not is_light(bg)
    out = [""] * 16
    # azul (4) y cian (6) salen del mismo `info`: lo conserva el tono más
    # cercano y el otro se gira (si no, en lavanda y salvia salían iguales)
    cyan_keeps = _hue_gap(p["info"], 180) < _hue_gap(p["info"], 215)
    for i, key, deg in _ANSI_HUES:
        keep = {4: not cyan_keeps, 6: cyan_keeps}.get(i, True)
        out[i] = legible(_toward_hue(p[key], deg, keep), bg, UI_MIN)
        h, l, s = _hls(out[i])
        bright = _from_hls(h, min(1.0, l + .10) if dark else max(0.0, l - .08),
                           min(1.0, s + .05))
        out[i + 8] = legible(bright, bg, UI_MIN)
    out[7] = legible(mix(fg, bg, .15), bg, TEXT_MIN)
    out[15] = legible(fg, bg, TEXT_MIN)
    out[8] = legible(p["faint"], bg, UI_MIN)
    out[0] = mix(bg, fg, .25) if dark else legible(fg, bg, TEXT_MIN)
    return out


def palette_from_manifest(m):
    """Paleta semántica PARCIAL de un manifiesto (solo hex válidos). El bloque
    `palette` manda; lo que falte se deriva de web.tokens / tui.osc / tui.roles
    / swatches. Acepta `accent-2` o `accent_2`. Jamás levanta → {}.
    Si el web y la terminal del tema van de lados opuestos (uno claro, el otro
    oscuro), los colores del web están pensados para OTRO fondo: entonces
    `tui.roles` va antes que `web.tokens` en cada clave."""
    try:
        if not isinstance(m, dict):
            return {}
        web = m.get("web") if isinstance(m.get("web"), dict) else {}
        tui = m.get("tui") if isinstance(m.get("tui"), dict) else {}
        src = {"tokens": web.get("tokens") if isinstance(web.get("tokens"), dict) else {},
               "osc": tui.get("osc") if isinstance(tui.get("osc"), dict) else {},
               "roles": tui.get("roles") if isinstance(tui.get("roles"), dict) else {}}
        sw = m.get("swatches") if isinstance(m.get("swatches"), list) else []
        wbg, obg = _hex(src["tokens"].get("bg")), _hex(src["osc"].get("bg"))
        roles_first = bool(wbg and obg and is_light(wbg) != is_light(obg))
        out = {}
        for key, chain in _DERIVE.items():
            if roles_first:
                chain = sorted(chain, key=lambda e: 0 if e[0] in ("osc", "roles") else 1)
            for blk, k in chain:
                if blk == "swatch":
                    v = _hex(sw[k]) if len(sw) > k else None
                else:
                    v = _hex(src[blk].get(k))
                if v:
                    out[key] = v
                    break
        pal = m.get("palette") if isinstance(m.get("palette"), dict) else {}
        for k, v in pal.items():
            kk = str(k).replace("-", "_")
            if kk in SEMANTIC_KEYS and _hex(v):
                out[kk] = _hex(v)
        return out
    except Exception:
        return {}


def complete(p):
    """Paleta COMPLETA (todas las SEMANTIC_KEYS + `base`) a partir de una
    parcial: lo declarado se respeta; lo ausente se deriva por mezcla."""
    p = {k: _hex(v) for k, v in dict(p or {}).items() if _hex(v)}
    bg = p.get("background") or _BASE["background"]
    fg = p.get("foreground") or _BASE["foreground"]
    acc = p.get("accent") or _BASE["accent"]
    out = {"background": bg, "foreground": fg, "accent": acc,
           "cursor": p.get("cursor") or acc,
           "accent_2": p.get("accent_2") or mix(acc, fg, .35),
           "accent_hi": p.get("accent_hi") or mix(acc, fg, .40),
           "muted": p.get("muted") or mix(fg, bg, .35),
           "faint": p.get("faint") or mix(fg, bg, .55),
           "surface": p.get("surface") or mix(bg, fg, .04),
           "border": p.get("border") or mix(bg, fg, .15)}
    for k in ("success", "warning", "danger", "info"):
        out[k] = p.get(k) or _BASE[k]
    out["base"] = "light" if is_light(bg) else "dark"   # la fórmula de Claude Code
    return out


def hub_palette(theme_id, themes_dir=None):
    """Paleta COMPLETA del tema del hub `theme_id` (themes/<id>/theme.json).
    None si el id es inválido o el manifiesto no existe/está roto."""
    if not (isinstance(theme_id, str) and _ID_RX.match(theme_id)):
        return None
    if themes_dir is None:
        try:
            import hubtheme
            themes_dir = hubtheme.THEMES_DIR
        except Exception:
            themes_dir = os.path.join(ROOT, "themes")
    try:
        with open(os.path.join(themes_dir, theme_id, "theme.json"), encoding="utf-8") as fh:
            m = json.load(fh)
    except Exception:
        return None
    if not isinstance(m, dict):
        return None
    return complete(palette_from_manifest(m))


# ── el motor de plantillas ──────────────────────────────────────────────────
# Sintaxis (mínima, sin lógica — una plantilla no ejecuta nada):
#   {{ clave }}                    valor de la paleta (o de `extra`, p.ej. name)
#   {{ mix a b 15% }}              a mezclado 15% hacia b (a/b = claves o #hex)
#   {{ alpha clave 0.12 }}         rgba(r,g,b,0.12) — para tokens web
_EXPR_RX = re.compile(r"\{\{\s*(.*?)\s*\}\}")


def _val(tok, ctx):
    if _HEX_RX.match(tok):
        return tok.lower()
    if tok in ctx:
        return ctx[tok]
    raise KeyError("clave desconocida en plantilla: %r" % tok)


def _eval(expr, ctx):
    parts = expr.split()
    if not parts:
        raise ValueError("expresión vacía")
    if parts[0] == "mix" and len(parts) == 4:
        pct = parts[3].rstrip("%")
        return mix(_val(parts[1], ctx), _val(parts[2], ctx), float(pct) / 100.0)
    if parts[0] == "alpha" and len(parts) == 3:
        a = float(parts[2])
        if not 0.0 <= a <= 1.0:
            raise ValueError("alpha fuera de rango: %r" % parts[2])
        r, g, b = _rgb(_val(parts[1], ctx))
        return "rgba(%d,%d,%d,%s)" % (r, g, b, parts[2])
    if len(parts) == 1:
        return _val(parts[0], ctx)
    raise ValueError("expresión desconocida: %r" % expr)


def template_path(target):
    """Ruta de la plantilla de `target` ('osc'|'tui'|'web'|'engine-<motor>')."""
    return os.path.join(TEMPLATES_DIR, "%s.json.tpl" % target)


def render(target, palette, **extra):
    """Renderiza la plantilla `target` con la paleta (completada) → dict.
    LEVANTA si la plantilla falta, usa una clave desconocida o no produce JSON
    válido: es a propósito — el error ocurre ANTES de escribir nada.
    `extra` agrega variables de texto (p.ej. name) — se escapan para JSON."""
    ctx = complete(palette)
    for k, v in extra.items():
        ctx[k] = json.dumps(str(v), ensure_ascii=False)[1:-1]
    with open(template_path(target), encoding="utf-8") as fh:
        text = fh.read()
    out = _EXPR_RX.sub(lambda mt: _eval(mt.group(1), ctx), text)
    data = json.loads(out)
    if not isinstance(data, dict):
        raise ValueError("la plantilla %s no produce un objeto JSON" % target)
    return data


def _safe(target, palette, **extra):
    try:
        return render(target, palette, **extra)
    except Exception:
        return None


def osc(palette):
    """{bg, fg, cursor} para theme.apply_colors. None si falla."""
    return _safe("osc", palette)


def tui(palette):
    """Bloque `tui` completo (roles/stars/fire/ember/off/osc). None si falla."""
    return _safe("tui", palette)


def web_tokens(palette):
    """`web.tokens` del dev panel. None si falla."""
    return _safe("web", palette)


def engine_supported(engine):
    """¿El motor tiene plantilla de tema in-app al estilo Claude Code (el JSON
    que va a themes-cc/), y existe en disco? Codex NO cuenta aquí: su tema es
    un .tmTheme (ver native_theme_supported)."""
    tpl = ENGINES.get(engine or "")
    return bool(tpl) and os.path.isfile(os.path.join(TEMPLATES_DIR, tpl))


def native_theme_supported(engine):
    """¿El motor tiene tema in-app en SU formato (NATIVE_THEMES) en disco?"""
    tpl = NATIVE_THEMES.get(engine or "")
    return bool(tpl) and os.path.isfile(os.path.join(TEMPLATES_DIR, tpl))


def engine_theme(engine, palette, name):
    """Tema in-app del `engine` para la paleta → dict, o None si el motor no
    tiene plantilla (antigravity) o el render falla. Para codex es el dict
    del .tmTheme (tmtheme_text lo serializa). En el de Claude Code cada
    override es un color de TEXTO: se deja legible sobre el fondo de la
    paleta también como lo pinta en 256 colores (Terminal.app, cc256)."""
    if not (engine_supported(engine) or native_theme_supported(engine)):
        return None
    data = _safe("engine-%s" % engine, palette, name=name)
    if engine == "claude-code" and isinstance(data, dict) \
            and isinstance(data.get("overrides"), dict):
        bg = complete(palette)["background"]
        data["overrides"] = {
            k: (legible(v, bg, TEXT_MIN if k == "text" else UI_MIN, quant=cc256)
                if _hex(v) else v)
            for k, v in data["overrides"].items()}
    return data


def engine_palette(theme_id=None, osc=None):
    """La paleta que ven los MOTORES: la del tema del hub con el fondo, la
    tinta y el cursor que Workspace PINTA en la terminal (`osc`; por defecto
    tuitheme.palette().OSC, que ya trae el fondo elegido aparte y la luz
    roja) y cada color de lectura legible sobre ese fondo (legible_palette).
    Sin nada pintado (terminal sin color, tema sin tui.osc) queda el fondo
    propio del tema. None si el tema no tiene paleta (olympo embebido)."""
    try:
        import tuitheme
        tid = tuitheme.resolve_id(theme_id)
        pal = hub_palette(tid)
        if not pal:
            return None
        if osc is None:
            osc = getattr(tuitheme.palette(tid), "OSC", None)
    except Exception:
        return None
    pal = dict(pal)
    o = osc if isinstance(osc, dict) else {}
    bg, fg = _hex(o.get("bg")), _hex(o.get("fg"))
    if fg:
        pal["foreground"] = fg
    if _hex(o.get("cursor")):
        pal["cursor"] = _hex(o.get("cursor"))
    if bg and bg != pal["background"]:
        # otro fondo (elegido aparte, luz roja): superficie y borde salen de él
        pal["background"] = bg
        pal["surface"] = mix(bg, pal["foreground"], .04)
        pal["border"] = mix(bg, pal["foreground"], .15)
    return legible_palette(pal)


def hub_engine_palette():
    """Paleta del tema ELEGIDO en el hub tal como la ven los motores
    (engine_palette: fondo pintado + colores legibles). None si no se
    resuelve."""
    try:
        return engine_palette()
    except Exception:
        return None


def codex_theme_name(key):
    """Nombre del tema de codex de un agente: `workspace-<agente>` (saneado
    a [a-z0-9_-]). None si no queda un nombre válido."""
    k = re.sub(r"[^a-z0-9_-]+", "-", str(key or "").strip().lower()).strip("-_")
    name = ("workspace-" + k)[:40] if k else ""
    return name if _ID_RX.match(name) else None


def codex_home(home=None):
    """Carpeta de codex: con `home` explícito (tests/herramientas) →
    <home>/.codex; si no, $CODEX_HOME si está fijado (lo que codex usa) o
    ~/.codex."""
    if home:
        return os.path.join(home, ".codex")
    env = (os.environ.get("CODEX_HOME") or "").strip()
    return env or os.path.join(os.path.expanduser("~"), ".codex")


def codex_theme_path(name, home=None):
    """$CODEX_HOME/themes/<name>.tmTheme (donde codex busca un tema custom)."""
    if not name or not _ID_RX.match(str(name)):
        return None
    return os.path.join(codex_home(home), "themes", "%s.tmTheme" % name)


def tmtheme_text(data):
    """Tema renderizado (dict con name/settings) → texto .tmTheme (plist XML,
    el formato de TextMate que lee codex). LEVANTA si el dict no sirve."""
    import plistlib
    if not isinstance(data, dict) or not isinstance(data.get("settings"), list):
        raise ValueError("tema de codex sin 'settings'")
    return plistlib.dumps(data, sort_keys=False).decode("utf-8")


def engine_theme_path(engine, name, home=None):
    """Dónde lee el motor su tema in-app, o None (motor sin tema in-app)."""
    if engine == "codex":
        return codex_theme_path(codex_theme_name(name), home)
    if engine != "claude-code" or not _ID_RX.match(str(name or "")):
        return None
    return os.path.join(home or os.path.expanduser("~"), ".claude", "themes",
                        "%s.json" % name)


#: Antigravity con colorScheme "terminal" (su default) pinta con los colores
#: ANSI básicos de la terminal: 2 (verde: «+» de diffs, modo accept-edits),
#: 4/12 (azul: acento, «> you», atajos), 8 (gris: bordes, texto tenue) —
#: VERIFICADO capturando su UI en una pty (agy 1.3.4). Workspace los
#: recolorea por corrida (OSC 4) y los restaura al salir (OSC 104).
ANSI_SLOTS = ((2, "success"), (4, "accent"), (8, "muted"), (12, "accent_hi"))


def ansi_slots(palette):
    """[(slot, #hex)] para OSC 4 desde la paleta semántica (completada)."""
    p = complete(palette or {})
    return [(n, p[k]) for n, k in ANSI_SLOTS if _hex(p.get(k))]


def sync_engine_theme(engine, name, display=None, brain=None, home=None):
    """El tema DENTRO del motor sigue al tema del hub (el socio 2026-10-12: el
    tema y el fondo del hub pintan TODO, también la sesión de cada agente).
    Regenera <home>/.claude/themes/<name>.json desde hub_engine_palette() y,
    si el settings.local.json del cerebro no nombra ningún tema, le pone
    custom:<name>. Lo HECHO A MANO GANA: un tema editado a mano no se pisa
    (stage_write) y un `theme` que el socio ya puso en settings no se toca.
    Codex: escribe $CODEX_HOME/themes/workspace-<agente>.tmTheme (el adapter
    lo elige con -c tui.theme solo si el socio no fijó el suyo).
    Devuelve el resultado de stage_write, o None si no aplica. Jamás levanta."""
    try:
        dst = engine_theme_path(engine, name, home)
        if not dst or not (engine_supported(engine) or native_theme_supported(engine)):
            return None
        pal = hub_engine_palette()
        label = display or str(name).capitalize()
        if engine == "codex":
            label = "Workspace · %s" % label
        data = engine_theme(engine, pal, label) if pal else None
        if data is None:
            return None
        text = tmtheme_text(data) if engine == "codex" else json_text(data)
        # un tema AJENO con ese nombre (del usuario, no nuestro) no se pisa ni
        # se elige para el agente — mismo criterio que install.install_theme
        if engine == "claude-code" and is_foreign(
                dst, home, [text] + legacy_sources(name, brain, home)):
            return {"ok": True, "written": [], "kept": [dst], "error": ""}
        res = stage_write([(dst, text, True)], home)
        if engine != "claude-code":
            return res
        if brain:
            sp = os.path.join(brain, ".claude", "settings.local.json")
            try:
                with open(sp, encoding="utf-8") as fh:
                    st = json.load(fh)
                if isinstance(st, dict) and not st.get("theme"):
                    st["theme"] = "custom:%s" % name
                    stage_write([(sp, json_text(st), False)], home)
            except Exception:
                pass                                 # sin settings: el install lo crea
        return res
    except Exception:
        return None


def overlay(rendered, explicit):
    """`explicit` (hecho a mano) sobre `rendered`, un nivel de dicts anidados
    (roles/stars/glyphs/osc se mezclan clave a clave). Lo explícito gana."""
    out = dict(rendered or {})
    for k, v in (explicit or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        else:
            out[k] = v
    return out


# ── escritura atómica + "lo hecho a mano gana" ──────────────────────────────
# Registro de lo que GENERAMOS: <estado>/theme-render.json = {ruta: sha256}.
# Un archivo existente cuyo hash ya no coincide con el registrado = el usuario
# lo editó → no se pisa. Sin registro (archivo de una versión anterior, que lo
# escribía siempre) = se presume generado: se reescribe como antes y desde ahí
# queda registrado. Excepción: el tema de un agente en ~/.claude/themes sin
# registro NI copia de una fuente nuestra es del usuario (is_foreign) → no se
# toca. El registro vive en el perfil, NUNCA junto al archivo
# (~/.claude/themes/ es de Claude Code: no le dejamos basura que pueda leer).
def _record_path(home=None):
    return os.path.join(_paths.state_dir(home), "theme-render.json")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_record(home=None):
    try:
        with open(_record_path(home), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _key(path):
    return os.path.normcase(os.path.abspath(path))


def is_handmade(path, home=None):
    """True si `path` existe y fue editado después de que lo generamos."""
    try:
        with open(path, encoding="utf-8") as fh:
            cur = fh.read()
    except Exception:
        return False
    rec = _read_record(home).get(_key(path))
    return bool(rec) and rec != _sha(cur)


def is_generated(path, home=None):
    """True solo si `path` es TAL CUAL lo generamos: está en el registro y su
    contenido no cambió. Sin registro (hecho a mano, o de otra instalación)
    o ilegible → False: borrar algo exige esta prueba, no la falta de otra."""
    if os.path.islink(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            cur = fh.read()
    except Exception:
        return False
    rec = _read_record(home).get(_key(path))
    return bool(rec) and rec == _sha(cur)


def is_foreign(path, home=None, known=()):
    """True si `path` existe y NO es nuestro → jamás se pisa: ni está en el
    registro de lo que generamos ni es idéntico a algo que Workspace escribe
    (`known`: lo que toca escribir ahora y lo que una versión sin registro
    copiaba tal cual, ver legacy_sources). Así un tema PROPIO del usuario que
    se llama igual que un agente (~/.claude/themes/nord.json y el agente
    `nord`) se conserva. Un symlink o un archivo ilegible es ajeno."""
    if os.path.islink(path):
        return True
    try:
        with open(path, encoding="utf-8") as fh:
            cur = fh.read()
    except FileNotFoundError:
        return False
    except Exception:
        return True
    return _key(path) not in _read_record(home) and cur not in set(known)


def legacy_sources(name, brain=None, home=None):
    """Textos que una versión SIN registro (antes del 2026-10-12) copiaba tal
    cual a ~/.claude/themes/<name>.json — las fuentes de install.install_theme.
    Un archivo idéntico a uno de ellos es nuestro aunque no esté registrado."""
    cands = [os.path.join(_paths.state_dir(home), "themes-cc", "%s.json" % name),
             os.path.join(ROOT, "themes-cc", "%s.json" % name)]
    if brain:
        cands.append(os.path.join(brain, "assets", "brand", "%s-theme.json" % name))
    out = []
    for c in cands:
        try:
            with open(c, encoding="utf-8") as fh:
                out.append(fh.read())
        except Exception:
            pass
    return out


def json_text(data):
    """Serialización canónica (la misma de agent_admin._atomic_write_json)."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def stage_write(files, home=None):
    """Escribe `files` = [(ruta, texto, respetar_hecho_a_mano), …] en bloque:
      1. descarta los hechos a mano (si respetar=True) y los idénticos;
      2. escribe TODOS a temporales en su mismo dir (staging);
      3. si alguno falló → borra temporales, nada cambia;
      4. os.replace de cada uno; si un replace falla, restaura los ya
         reemplazados desde su contenido previo.
    Devuelve {"ok", "written", "kept" (hecho a mano), "error"}. Jamás levanta."""
    res = {"ok": True, "written": [], "kept": [], "error": ""}
    plan = []
    for path, text, respect in files:
        try:
            if respect and is_handmade(path, home):
                res["kept"].append(path)
                continue
            prev = None
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    prev = fh.read()
                if prev == text:
                    plan.append((path, text, prev, None, respect))   # idéntico: solo registrar
                    continue
            plan.append((path, text, prev, path + ".tmp-theme-%d" % os.getpid(), respect))
        except Exception as e:
            res.update(ok=False, error="%s: %s" % (path, e))
            return res
    staged = []
    try:
        for path, text, prev, tmp, _r in plan:
            if tmp is None:
                continue
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            staged.append(tmp)
    except Exception as e:
        for t in staged:
            try:
                os.remove(t)
            except OSError:
                pass
        res.update(ok=False, error="staging: %s" % e)
        return res
    done = []
    try:
        for path, text, prev, tmp, _r in plan:
            if tmp is None:
                continue
            os.replace(tmp, path)
            done.append((path, prev))
    except Exception as e:
        for path, prev in reversed(done):            # rollback: lo anterior vuelve
            try:
                if prev is None:
                    os.remove(path)
                else:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(prev)
            except Exception:
                pass
        for _p, _t, _pr, tmp, _r in plan:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        res.update(ok=False, error="replace: %s" % e)
        return res
    res["written"] = [p for p, _t, _pr, tmp, _r in plan if tmp]
    mark_generated([(p, t) for p, t, _pr, _tmp, r in plan if r], home)
    return res


def mark_generated(entries, home=None):
    """Registra [(ruta, texto)] como GENERADOS por nosotros (para que una
    edición posterior del usuario se detecte y se respete). Falla-suave: sin
    registro, el archivo simplemente se presume generado (lo de siempre)."""
    if not entries:
        return
    try:
        rec = _read_record(home)
        for path, text in entries:
            rec[_key(path)] = _sha(text)
        rp = _record_path(home)
        os.makedirs(os.path.dirname(rp), exist_ok=True)
        tmp = rp + ".tmp-%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, rp)
    except Exception:
        pass


# ── hook theme-set (opcional, del usuario) ──────────────────────────────────
HOOK_TIMEOUT = 10   # s — el hook jamás retiene al hub más que esto


def hook_path(home=None):
    """Script del usuario que corre tras cambiar ui.theme, o None. Busca en
    <estado>/hooks/: theme-set.py (cualquier OS, con este Python) o
    theme-set (POSIX, ejecutable) / theme-set.cmd|.bat (Windows)."""
    d = os.path.join(_paths.state_dir(home), "hooks")
    names = ["theme-set.py"] + (["theme-set.cmd", "theme-set.bat"]
                                if os.name == "nt" else ["theme-set"])
    for n in names:
        p = os.path.join(d, n)
        if os.path.isfile(p) and (n.endswith((".py", ".cmd", ".bat"))
                                  or os.access(p, os.X_OK)):
            return p
    return None


def run_theme_set_hook(theme_id, home=None):
    """Lanza el hook theme-set con el id nuevo como argumento, SIN bloquear:
    un hilo daemon lo mata al vencer HOOK_TIMEOUT. Falla-suave absoluta;
    kill-switch: env WORKSPACE_NO_THEME_HOOK=1. Devuelve el Popen o None."""
    try:
        if os.environ.get("WORKSPACE_NO_THEME_HOOK"):
            return None
        hp = hook_path(home)
        if not hp:
            return None
        cmd = ([sys.executable, hp] if hp.endswith(".py") else [hp]) + [str(theme_id)]
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)

        def _reap():
            try:
                proc.wait(timeout=HOOK_TIMEOUT)
            except Exception:
                try:
                    if os.name == "nt":      # un .cmd lanza hijos: matar el árbol entero
                        subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        proc.kill()
                except Exception:
                    pass
        threading.Thread(target=_reap, daemon=True).start()
        return proc
    except Exception:
        return None


# ── compat: presets de prueba que ya no viajan en themes.json ───────────────
# "prueba", "midas", "midas2" eran agentes de prueba del equipo que se colaron
# al themes.json del repo antes de que los temas de agente fueran per-máquina
# (6ad4e74). Salieron del repo; si una máquina tiene un agente con ese nombre,
# la migración (ver themes/README.md) copia su paleta a themes.local.json.
LEGACY_PRESETS = {
    "prueba": {"bg": "#121316", "fg": "#e6e8ee"},
    "midas": {"bg": "#121316", "fg": "#e6e8ee"},
    "midas2": {"bg": "#121316", "fg": "#e6e8ee"},
}


def legacy_presets_needed(agent_names, home=None):
    """Nombres de LEGACY_PRESETS que son agentes de esta máquina y aún no
    tienen entrada en themes.local.json (lo que la migración debe adoptar)."""
    try:
        with open(os.path.join(_paths.state_dir(home), "themes.local.json"),
                  encoding="utf-8") as fh:
            local = json.load(fh)
        if not isinstance(local, dict):
            local = {}
    except Exception:
        local = {}
    names = {str(n).strip().lower() for n in (agent_names or ())}
    return sorted(n for n in LEGACY_PRESETS if n in names and n not in local)


def adopt_legacy_presets(agent_names, home=None):
    """Idempotente: añade a themes.local.json la paleta legada de cada agente
    devuelto por legacy_presets_needed (sin tocar ninguna otra entrada).
    Devuelve la lista adoptada ([] si no había nada que hacer)."""
    need = legacy_presets_needed(agent_names, home)
    if not need:
        return []
    path = os.path.join(_paths.state_dir(home), "themes.local.json")
    try:
        with open(path, encoding="utf-8") as fh:
            local = json.load(fh)
        if not isinstance(local, dict):
            return []                                # corrupto/raro: no se pisa
    except FileNotFoundError:
        local = {}
    except Exception:
        return []
    for n in need:
        local[n] = dict(LEGACY_PRESETS[n])
    r = stage_write([(path, json_text(local), False)], home)
    return need if r["ok"] else []


if __name__ == "__main__":
    # demo: `python3 theme_render.py <tema> [osc|tui|web|engine-claude-code]`
    tid = sys.argv[1] if len(sys.argv) > 1 else "bruma"
    tgt = sys.argv[2] if len(sys.argv) > 2 else None
    pal = hub_palette(tid)
    if pal is None:
        print("tema desconocido: %s" % tid)
        sys.exit(1)
    data = render(tgt, pal, name=tid.capitalize()) if tgt else pal
    print(json.dumps(data, ensure_ascii=False, indent=2))
