#!/usr/bin/env python3
"""WORKSPACE · hublayout — el HUB (el LANZADOR) y las piezas de pantalla
compartidas por las secciones.

El hub tiene UN solo layout desde 2026-10-12: el LANZADOR (render_lanzador),
una lista de agentes y secciones que se filtra al escribir, en una caja de
tamaño fijo. Los layouts anteriores (clásico, centro, día, hud, cockpit,
split, status, grid) salieron del código; viven en la etiqueta git
`archivo/layouts-pre-lanzador`.

El TEMA (hubtheme/tuitheme, ui.theme) decide paleta y glifos: aquí se pinta
SOLO con la paleta/glifos del tema activo (cols(P)) — no se hardcodea ni un
color. Además de render_lanzador, este módulo da a las pantallas-sección sus
piezas comunes: título grande (big_title/title_reflection), cabecera
(screen_header), cajas (full_box), atajos (keyline/top_hints/foot_hints/
instruction_buttons) y medición de ancho (vis/clip/pad).

CONTRATO del render del hub:
    render_lanzador(data, view, P, w) -> list[str]
  · data (estable en la sesión): agents · opts · version · version_text ·
    motor · keys (ver front._menu_machinery).
  · view: lz_level / lz_q / lz_sel · msg / hb_msg · h (alto real).
  · Ninguna línea excede w-1 columnas visibles; el nº de líneas no depende
    de la selección (front redibuja con cursor-up).
  · Windows-safe: nada del rango U+2600–U+27BF ni emojis en arte fijo.

stdlib puro (3.9+), falla-suave absoluta.
"""
import os
import re

# Medición de ancho COMPARTIDA (_width.py): escapes ANSI completos (CSI/OSC/
# ESC de 2 bytes -- medir solo `\x1b[...m` dejaba pasar secuencias que CUENTAN
# como ancho y el borde derecho "bailaba" fila a fila), saneo NFC/zero-width/
# controles y ancho por caracter Hangul-safe. Los alias conservan los nombres
# historicos de este modulo (los usan sus tests y docstrings).
from _width import ANSI as _ANSI, sane as _sane, eaw as _cw   # noqa: E402

_RESET = "\x1b[0m"

# i18n (lado cliente): traduce el «chrome» compartido de los layouts dia/centro.
# Import guardado + red de seguridad inline — sin i18n (o clave faltante) _t()
# devuelve el español `es` tal cual (paridad EXACTA con el hub de siempre).
try:
    import i18n as _i18n
except Exception:
    _i18n = None


def _t(key, es, **kw):
    s = es
    if _i18n is not None:
        try:
            v = _i18n.t(key)
            if v != key:
                s = v
        except Exception:
            s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


# -- helpers de texto ANSI (ancho VISUAL, no len) ----------------------------
def _plain(s):
    return _ANSI.sub("", str(s))


def vis(s):
    """Ancho visual de una línea ANSI (ver _sane/_cw — mide lo que la
    terminal pinta, no len()). Los escapes se quitan ANTES de sanear (un
    BEL que termina un OSC no es un control del texto)."""
    return sum(_cw(c) for c in _sane(_plain(s)))


def clip(s, w):
    """Recorta una línea ANSI a ≤w columnas visibles preservando los códigos
    de color (y cerrando con reset si el recorte dejó códigos fuera — que el
    color no sangre al borde/padding). Sanea la línea (_sane) SIEMPRE: todo
    lo impreso pasa por clip/pad y sale medible."""
    if w <= 0:
        return ""
    s = _sane(s)
    if vis(s) <= w:
        return s
    out, used, i = [], 0, 0
    while i < len(s) and used < w - 1:
        m = _ANSI.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        c = s[i]
        cw = _cw(c)
        if used + cw > w - 1:
            break
        out.append(c)
        used += cw
        i += 1
    tail = "…" + (_RESET if _ANSI.search(s, i) else "")
    return "".join(out) + tail


def pad(s, w):
    """Rellena a EXACTAMENTE w columnas visibles (clip si excede)."""
    s = _sane(s)
    s = clip(s, w) if vis(s) > w else s
    return s + " " * max(0, w - vis(s))


def cols(P):
    """Paleta segura para un renderer: dict con las claves que TODO layout
    puede usar, con fallback benigno si el namespace no trae alguna.
    Idempotente: un dict ya normalizado pasa tal cual (los helpers públicos
    aceptan paleta o dict)."""
    if isinstance(P, dict):
        return P

    def g(a, d=""):
        return getattr(P, a, d) or ""
    gl = getattr(P, "GLYPHS", None) or {}
    box = gl.get("box") or "╭╮╰╯│─"
    return {"B": g("B"), "B2": g("B2"), "C": g("C"), "WH": g("WH"),
            "DIM": g("DIM"), "DK": g("DK"), "GREY": g("GREY"),
            "R": g("R"), "BO": g("BO"),
            "INACTIVE": g("INACTIVE", g("DIM")), "ERR": g("ERR", g("B")),
            # semánticos del tema (verde/rojo) para puntos de estado, ✓limpio
            # y el log de actividad — fallback benigno a los roles básicos
            "OK": g("OK", g("C")), "BAD": g("BAD", g("ERR", g("B"))),
            # acento APAGADO del tema (P.OFF — violeta/magenta tenue en
            # cyberpunk, oro apagado en olympo): bordes tenues con color de
            # tema, NO gris (feedback cockpit-v7 2026-07-04)
            "OFF": g("OFF", g("DK")),
            # tema MONOCROMO declarado (o terminal sin color): quien pinte
            # color propio fuera de los roles debe ceder — ver _agent_ink.
            "MONO": bool(getattr(P, "MONO", False)),
            "PTR": gl.get("pointer") or "❯",
            "BL": gl.get("bracket_l") or "❮",
            "BR": gl.get("bracket_r") or "❯",
            "SEP": gl.get("sep") or "─", "BOX": box,
            # iconos de los widgets (rama git, limpio, latido, bus) — vienen
            # del TEMA (tuitheme los declara y un tema Windows los overridea)
            "BRANCH": gl.get("branch") or "⎇", "CHECK": gl.get("check") or "✓",
            "HEART": gl.get("heart") or "♥", "MAIL": gl.get("mail") or "✉",
            "WCOL": _wcol6(P)}


def _wcol6(P):
    """Gradiente de 6 colores del wordmark del TEMA (P.WCOL); si el
    namespace no lo trae (fallback de front sin tuitheme) → gradiente con
    los roles básicos (B2→B→C). Siempre len 6."""
    try:
        wc = list(getattr(P, "WCOL", None) or [])
        if len(wc) == 6:
            return wc
    except Exception:
        pass
    def g(a):
        return getattr(P, a, "") or ""
    return [g("B2"), g("B2"), g("B"), g("B"), g("C"), g("C")]


# ── HINTS DE TECLADO COMPARTIDOS (cabecera + pie de cada pantalla) ──────────
# Pedido del socio 2026-10-04: los atajos no pueden vivir SOLO en una línea
# tenue al pie. Arriba, junto al nombre de la pantalla, van los 3-4 CLAVE
# (tecla en acento, acción legible) y el pie conserva la lista completa con
# el mismo lenguaje visual. UNA fuente de verdad por pantalla: la MISMA
# tupla de pares ((tecla, acción), …) alimenta cabecera (recortada a lo
# esencial) y pie (completa) — una pantalla nueva hereda el patrón llamando
# screen_header()/foot_hints(), no copiando render.

def keyline(K, items, w, txt_col=None):
    """`tecla acción · tecla acción` en UNA línea que SIEMPRE cabe en w:
    tecla en acento+bold, acción en texto tenue, separador `·` apagado.
    Si no cabe entera cede pares del final conservando el PRIMERO (cómo
    moverse) y el ÚLTIMO (cómo salir) — un atajo recortado a media palabra
    no enseña nada. "" si ni un par cabe. `items` = ((tecla, acción), …)."""
    K = cols(K)
    tc = txt_col if txt_col is not None else K["DIM"]
    sep = "  "
    pares = [(str(a), str(b)) for a, b in items]
    while pares:
        line = sep.join("%s[ %s%s ]%s" % (K["C"] + K["BO"], a, (" " + b) if b else "", K["R"])
                        for a, b in pares)
        if vis(line) <= w:
            return line
        pares.pop(len(pares) - 2 if len(pares) > 1 else 0)
    return ""


def instruction_buttons(K, items, w):
    """Brand instruction keys in three-row boxes; compact keyline for tiny widths."""
    K=cols(K)
    labels=[' '+str(key)+' '+str(action)+' ' for key,action in items]
    items=list(items)
    while labels and sum(vis(label)+2 for label in labels)+3*max(0,len(labels)-1)>w:
        cut=len(labels)-2 if len(labels)>1 else 0
        labels.pop(cut)
    if not labels:return []
    result=[]
    for row in range(3):
        cells=[]
        for label in labels:
            edge='─'*vis(label)
            cell='╭'+edge+'╮' if row==0 else '╰'+edge+'╯' if row==2 else '│'+label+'│'
            cells.append(K['C']+K['BO']+cell+K['R'])
        result.append('   '.join(cells))
    return result


def top_hints(K, items, w, h=0, max_pairs=4, min_h=30):
    """La zona de atajos CLAVE de la CABECERA — centrada bajo el subtítulo
    de la pantalla, tecla en acento y acción en gris LEGIBLE (no DIM: esta
    línea nació para VERSE al instante). Recorta a los primeros pares + el
    último (salir). [] cuando debe ceder (alto < min_h o ancho sin sitio):
    es redundancia del pie — cede ANTES que el contenido esencial; el pie
    completo queda siempre."""
    K = cols(K)
    if h and h < min_h:
        return []
    pares = list(items)
    if max_pairs and len(pares) > max_pairs:
        pares = pares[:max_pairs - 1] + [pares[-1]]
    line = keyline(K, pares, max(10, w - 3), txt_col=K["GREY"])
    if not line:
        return []
    return [" " * max(0, ((w - 1) - vis(line)) // 2) + line]


def foot_hints(K, items, w):
    """El pie de atajos COMPLETO — UNA línea (altura estable, el pie jamás
    crece), mismo lenguaje que la cabecera pero con la lista entera y la
    acción tenue. Reemplaza a la vieja línea DK plana."""
    return " " + keyline(cols(K), items, max(10, w - 3))


def screen_header(K, w, h, sub, hints=None, compact_h=30, refl_min_h=0,
                  hints_min_h=None, word="WORKSPACE"):
    """Cabecera COMPARTIDA de las pantallas-sección del hub (tono /
    calendario / github / dev / …): wordmark centrado + subtítulo + atajos
    clave (top_hints) + regla + aire. `hints_min_h` = alto bajo el cual
    cede la fila de atajos (default: el mismo umbral del wordmark
    compacto). `word` titula la sección en el wordmark (default WORKSPACE).
    Devuelve las líneas iniciales del render."""
    K = cols(K)
    L = [""]
    bt = big_title(K, w, h, indent=" ", compact=(h < compact_h), center=True,
                   word=word)
    L += bt
    # sin reflejo ░ bajo el título (como el wordmark del hub; 2026-10-14).
    # `refl_min_h` se acepta por compatibilidad.
    L.append(" " * max(0, ((w - 1) - vis(sub)) // 2)
             + "%s%s%s" % (K["DIM"], sub, K["R"]))
    if hints:
        L += top_hints(K, hints, w, h,
                       min_h=(hints_min_h if hints_min_h is not None
                              else compact_h))
    L.append("%s%s%s%s%s" % (K["B2"], K["BOX"][5] * 3, K["DK"],
                             K["BOX"][5] * max(1, w - 5), K["R"]))
    L.append("")
    return L


# ── LENGUAJE DE DISEÑO COMPARTIDO (feedback aprobado 2026-07-03) ────────────
# Los 5 layouts alternativos comparten estos widgets; cada layout conserva su
# ESTRUCTURA propia. Todo con dato REAL (git/heartbeat/now.json/bus) — si la
# fuente no está, el widget se OMITE limpio.

# Fuente ASCII "ANSI Shadow" por letra (6 filas): bloques █ con sombra ╗╔║═╝╚
# — box-drawing/bloques estándar < U+2600 (Windows-safe). EMPOTRADA (sin
# figlet): solo las letras del título; agregar aquí si el título cambia.
# Tabla canónica de la fuente (A-Z · 0-9): templates/agent/workspace/brand/agent-banner.py
_SHADOW = {
    "W": ("██╗    ██╗", "██║    ██║", "██║ █╗ ██║", "██║███╗██║",
          "╚███╔███╔╝", " ╚══╝╚══╝ "),
    "R": ("██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗",
          "██║  ██║", "╚═╝  ╚═╝"),
    "K": ("██╗  ██╗", "██║ ██╔╝", "█████╔╝ ", "██╔═██╗ ",
          "██║  ██╗", "╚═╝  ╚═╝"),
    "A": (" █████╗ ", "██╔══██╗", "███████║", "██╔══██║",
          "██║  ██║", "╚═╝  ╚═╝"),
    "C": (" ██████╗", "██╔════╝", "██║     ", "██║     ",
          "╚██████╗", " ╚═════╝"),
    "E": ("███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ",
          "███████╗", "╚══════╝"),
    "O": (" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║",
          "╚██████╔╝", " ╚═════╝ "),
    "L": ("██╗     ", "██║     ", "██║     ", "██║     ",
          "███████╗", "╚══════╝"),
    "Y": ("██╗   ██╗", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚██╔╝  ",
          "   ██║   ", "   ╚═╝   "),
    "M": ("███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║",
          "██║ ╚═╝ ██║", "╚═╝     ╚═╝"),
    "P": ("██████╗ ", "██╔══██╗", "██████╔╝", "██╔═══╝ ",
          "██║     ", "╚═╝     "),
    "U": ("██╗   ██╗", "██║   ██║", "██║   ██║", "██║   ██║",
          "╚██████╔╝", " ╚═════╝ "),
    "S": ("███████╗", "██╔════╝", "███████╗", "╚════██║",
          "███████║", "╚══════╝"),
    # G/N/T: títulos de sección (AGENTES/AGENTS) — copiadas de la tabla
    # canónica (agent-banner.py), mismo estilo y alto.
    "G": (" ██████╗ ", "██╔════╝ ", "██║  ███╗", "██║   ██║",
          "╚██████╔╝", " ╚═════╝ "),
    "N": ("███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║",
          "██║ ╚████║", "╚═╝  ╚═══╝"),
    "T": ("████████╗", "╚══██╔══╝", "   ██║   ", "   ██║   ",
          "   ██║   ", "   ╚═╝   "),
}


_SHADOW.update({' ': ('   ', '   ', '   ', '   ', '   ', '   '),
 '-': ('       ', '       ', ' █████╗', ' ╚════╝', '       ', '       '),
 '0': (' ██████╗ ', '██╔═████╗', '██║██╔██║', '████╔╝██║', '╚██████╔╝', ' ╚═════╝ '),
 '1': (' ██╗', '███║', '╚██║', ' ██║', ' ██║', ' ╚═╝'),
 '2': ('██████╗ ', '╚════██╗', ' █████╔╝', '██╔═══╝ ', '███████╗', '╚══════╝'),
 '3': ('██████╗ ', '╚════██╗', ' █████╔╝', ' ╚═══██╗', '██████╔╝', '╚═════╝ '),
 '4': ('██╗  ██╗', '██║  ██║', '███████║', '╚════██║', '     ██║', '     ╚═╝'),
 '5': ('███████╗', '██╔════╝', '███████╗', '╚════██║', '███████║', '╚══════╝'),
 '6': (' ██████╗ ', '██╔════╝ ', '███████╗ ', '██╔═══██╗', '╚██████╔╝', ' ╚═════╝ '),
 '7': ('███████╗', '╚════██║', '    ██╔╝', '   ██╔╝ ', '   ██║  ', '   ╚═╝  '),
 '8': (' █████╗ ', '██╔══██╗', '╚█████╔╝', '██╔══██╗', '╚█████╔╝', ' ╚════╝ '),
 '9': (' █████╗ ', '██╔══██╗', '╚██████║', ' ╚═══██║', ' █████╔╝', ' ╚════╝ '),
 'A': (' █████╗ ', '██╔══██╗', '███████║', '██╔══██║', '██║  ██║', '╚═╝  ╚═╝'),
 'B': ('██████╗ ', '██╔══██╗', '██████╔╝', '██╔══██╗', '██████╔╝', '╚═════╝ '),
 'C': (' ██████╗', '██╔════╝', '██║     ', '██║     ', '╚██████╗', ' ╚═════╝'),
 'D': ('██████╗ ', '██╔══██╗', '██║  ██║', '██║  ██║', '██████╔╝', '╚═════╝ '),
 'E': ('███████╗', '██╔════╝', '█████╗  ', '██╔══╝  ', '███████╗', '╚══════╝'),
 'F': ('███████╗', '██╔════╝', '█████╗  ', '██╔══╝  ', '██║     ', '╚═╝     '),
 'G': (' ██████╗ ', '██╔════╝ ', '██║  ███╗', '██║   ██║', '╚██████╔╝', ' ╚═════╝ '),
 'H': ('██╗  ██╗', '██║  ██║', '███████║', '██╔══██║', '██║  ██║', '╚═╝  ╚═╝'),
 'I': ('██╗', '██║', '██║', '██║', '██║', '╚═╝'),
 'J': ('     ██╗', '     ██║', '     ██║', '██   ██║', '╚█████╔╝', ' ╚════╝ '),
 'K': ('██╗  ██╗', '██║ ██╔╝', '█████╔╝ ', '██╔═██╗ ', '██║  ██╗', '╚═╝  ╚═╝'),
 'L': ('██╗     ', '██║     ', '██║     ', '██║     ', '███████╗', '╚══════╝'),
 'M': ('███╗   ███╗', '████╗ ████║', '██╔████╔██║', '██║╚██╔╝██║', '██║ ╚═╝ ██║', '╚═╝     ╚═╝'),
 'N': ('███╗   ██╗', '████╗  ██║', '██╔██╗ ██║', '██║╚██╗██║', '██║ ╚████║', '╚═╝  ╚═══╝'),
 'O': (' ██████╗ ', '██╔═══██╗', '██║   ██║', '██║   ██║', '╚██████╔╝', ' ╚═════╝ '),
 'P': ('██████╗ ', '██╔══██╗', '██████╔╝', '██╔═══╝ ', '██║     ', '╚═╝     '),
 'Q': (' ██████╗ ', '██╔═══██╗', '██║   ██║', '██║▄▄ ██║', '╚██████╔╝', ' ╚══▀▀═╝ '),
 'R': ('██████╗ ', '██╔══██╗', '██████╔╝', '██╔══██╗', '██║  ██║', '╚═╝  ╚═╝'),
 'S': ('███████╗', '██╔════╝', '███████╗', '╚════██║', '███████║', '╚══════╝'),
 'T': ('████████╗', '╚══██╔══╝', '   ██║   ', '   ██║   ', '   ██║   ', '   ╚═╝   '),
 'U': ('██╗   ██╗', '██║   ██║', '██║   ██║', '██║   ██║', '╚██████╔╝', ' ╚═════╝ '),
 'V': ('██╗   ██╗', '██║   ██║', '██║   ██║', '╚██╗ ██╔╝', ' ╚████╔╝ ', '  ╚═══╝  '),
 'W': ('██╗    ██╗', '██║    ██║', '██║ █╗ ██║', '██║███╗██║', '╚███╔███╔╝', ' ╚══╝╚══╝ '),
 'X': ('██╗  ██╗', '╚██╗██╔╝', ' ╚███╔╝ ', ' ██╔██╗ ', '██╔╝ ██╗', '╚═╝  ╚═╝'),
 'Y': ('██╗   ██╗', '╚██╗ ██╔╝', ' ╚████╔╝ ', '  ╚██╔╝  ', '   ██║   ', '   ╚═╝   '),
 'Z': ('███████╗', '╚══███╔╝', '  ███╔╝ ', ' ███╔╝  ', '███████╗', '╚══════╝')})

def _shadow_rows(word="WORKSPACE"):
    """Las 6 filas ANSI Shadow de `word` (sin color). WORKSPACE = 75 cols."""
    import unicodedata
    rows = ["", "", "", "", "", ""]
    for ch in word:
        # una letra con acento usa el glifo de su letra base (DOCUMENTACIÓN → O)
        g = _SHADOW.get(ch.upper()) or _SHADOW.get(
            unicodedata.normalize("NFD", ch)[:1].upper())
        if not g:
            continue
        for r in range(6):
            rows[r] += g[r]
    return rows


_SHADOW_GLYPHS = frozenset("╔╗╚╝║═")     # el "tubo" de la fuente ANSI Shadow


def _neon_row(row, core, shade, R):
    """Una fila del título en NEÓN (feedback cockpit-v7 2026-07-04): el
    núcleo █ de las letras en `core` (gradiente brillante bold) y la SOMBRA
    de la fuente (╔╗╚╝║═) en `shade` (tono tenue del acento, no gris) — la
    letra se lee como tubo de luz con profundidad. Solo color: mismos
    caracteres, mismo ancho visual."""
    parts, prev = [], None
    for ch in row:
        kind = ("c" if ch == "█"
                else ("s" if ch in _SHADOW_GLYPHS else " "))
        if kind != prev:
            parts.append(R + (core if kind == "c"
                              else (shade if kind == "s" else "")))
            prev = kind
        parts.append(ch)
    parts.append(R)
    return "".join(parts)


def titles_on():
    """ui.titles (default ON). OFF = ninguna pantalla pinta el título grande
    (prueba del socio 2026-10-12). Falla-suave → ON."""
    try:
        import settings
        return settings.get("ui.titles", True) is not False
    except Exception:
        return True


def big_title(K, w, h=0, indent=" ", right="", compact=False,
              center=False, word="WORKSPACE"):
    """Título WORKSPACE GRANDE en ANSI Shadow, look NEÓN: núcleo █ con el
    GRADIENTE del tema activo (WCOL fila a fila: magenta→violeta→cian en
    cyberpunk, dorado en olympo) en bold + la sombra de la fuente (╔╗╚╝║═)
    en el acento medio TENUE (no gris — profundidad de tubo neón) + un
    widget opcional arriba a la derecha (`right`, p.ej. la rama git).
    RESPONSIVO: si el ancho no da (o el alto h viene y es chico, o el caller
    pide compact — ver _fit) cae al wordmark compacto de UNA línea — jamás
    desborda. K = paleta o cols().

    `center` (opt-in por layout — pedido del socio 2026-09-23): el wordmark se
    centra en el ancho REAL. El indent se recalcula por CAMINO (el bloque
    grande centra sus 75 columnas; el wordmark compacto centra SU línea, que
    es mucho más corta — centrar ambos con el mismo indent dejaba el
    compacto tirado a la derecha). Si el widget `right` ya no cabe junto al
    bloque centrado se OMITE: la rama sigue en la statusline del pie.

    `word` (default WORKSPACE): la palabra del wordmark — una sección puede
    titularse con su nombre (p.ej. AGENTES) en el MISMO estilo; letras sin
    glifo en _SHADOW se omiten (agregarlas allí).

    Con ui.titles OFF devuelve [] (sin título, ni grande ni compacto)."""
    if not titles_on():
        return []
    K = cols(K)
    rows = _shadow_rows(word)
    tw = max(len(r) for r in rows)
    grande = (not compact) and (w - 1) >= (vis(indent) + tw) \
        and (not h or h >= 24)
    if center and grande:
        indent = " " * max(0, ((w - 1) - tw) // 2)
    ind = vis(indent)
    if grande and w - 1 >= ind + tw:
        wc = K["WCOL"]
        out = []
        for r, row in enumerate(rows):
            ln = indent + _neon_row(row, wc[r % len(wc)] + K["BO"],
                                    K["B2"], K["R"])
            if r == 0 and right and w - 1 >= ind + tw + 2 + vis(right):
                ln += " " * (w - 1 - ind - tw - vis(right)) + right
            out.append(clip(ln, w - 1))
        return out
    if center:                                   # el compacto centra SU ancho
        indent = " " * max(0, ((w - 1) - vis("▛▀ " + word)) // 2)
    ln = "%s%s▛▀ %s%s%s" % (indent, K["B"] + K["BO"], K["C"], word, K["R"])
    if right:
        gapw = w - 1 - vis(ln) - vis(right)
        if gapw >= 2:
            ln += " " * gapw + right
    return [clip(ln, w - 1)]


def title_reflection(K, w, indent=" ", center=False, word="WORKSPACE"):
    """Fila-REFLEJO bajo el título neón (feedback cockpit-v7 2026-07-04):
    la silueta ░ de las 2 últimas filas del ANSI Shadow en orden ESPEJO
    (la base primero) y tonos apagados del acento que se desvanecen —
    luz de letrero sobre piso oscuro. Degrada suave: en mono (sin color)
    no hay reflejo ([]) — ░ gris sería ruido, no luz. Solo geometría
    < U+2600 (Windows-safe)."""
    if not titles_on():
        return []
    K = cols(K)
    if not (K["B2"] or K["DK"]):                 # mono → sin reflejo
        return []
    rows = _shadow_rows(word)
    if center:                                   # mismo eje que el título
        indent = " " * max(0, ((w - 1) - max(len(r) for r in rows)) // 2)
    out = []
    for tint, row in ((K["B2"], rows[-1]), (K["DK"], rows[-2])):
        sil = "".join(" " if ch == " " else "░" for ch in row)
        out.append(clip("%s%s%s%s" % (indent, tint, sil, K["R"]), w - 1))
    return out


def full_box(title, body, K, pw, ih, focused=False, border=None, label=None):
    """Caja COMPLETA `╭─ TITULO ───╮` + `│ … │` × ih + `╰────╯` (glifos box
    del tema) con la etiqueta FLOTANDO sobre el borde superior. body se
    recorta/rellena a EXACTAMENTE ih filas; cada línea EXACTA a pw columnas
    visibles — el borde derecho queda en UNA columna recta (componer lado a
    lado / llenar el alto).

    `border` (feedback cockpit-v7 2026-07-04): color de ACENTO del borde —
    la caja entera se pinta en ese tono del tema (cian AGENTES, violeta
    SISTEMA, magenta tenue ACTIVIDAD), las 4 esquinas en su versión BRIGHT
    (bold) — menú de programa complejo; enfocada = borde entero bright.
    `label` pisa el color de la etiqueta. Sin `border` → el look clásico
    (enfocada tinta hi / tenue), intacto para status/grid."""
    K = cols(K)
    box = K["BOX"]
    tl, tr, bl, br, v, hh = box[0], box[1], box[2], box[3], box[4], box[5]
    if border:
        hcol = border + K["BO"]                      # esquinas con acento
        bcol = hcol if focused else border
        tcol = label or (border + K["BO"])
        if focused and not label:
            tcol = K["WH"] + K["BO"]                 # la etiqueta PRENDE
    else:
        # look clásico: enfocada = tinta hi bold · sin foco = acento medio
        # (labels de sección con color de tema, no gris — feedback 2026-07-04)
        tcol = label or ((K["C"] + K["BO"]) if focused else K["B2"])
        bcol = K["DIM"] if focused else K["DK"]
        hcol = bcol
    inner = pw - 4                                   # '│ ' + ' │'
    t = clip(title, max(1, pw - 7))                  # título jamás desborda
    fill = max(1, pw - vis(t) - 5)                   # ╭─ t ──…──╮ = pw exacto
    out = [clip("%s%s%s %s%s%s %s%s%s%s%s%s" % (
        hcol, tl + hh, K["R"], tcol, t, K["R"], bcol, hh * fill, K["R"],
        hcol, tr, K["R"]), pw)]
    rows = list(body[:ih]) + [""] * max(0, ih - len(body))
    for ln in rows:
        out.append("%s%s%s %s %s%s%s" % (bcol, v, K["R"], pad(ln, inner),
                                         bcol, v, K["R"]))
    out.append("%s%s%s%s%s%s%s%s" % (hcol, bl, K["R"], bcol, hh * (pw - 2),
                                     K["R"], hcol, br + K["R"]))
    return out


def _wrap(txt, w, maxl):
    """Corta texto plano en ≤maxl líneas de ≤w columnas (por palabras; una
    palabra imposible se recorta con clip). [] si no hay texto."""
    txt = " ".join(str(txt or "").split())
    if not txt or w <= 0 or maxl <= 0:
        return []
    out, cur = [], ""
    for word in txt.split(" "):
        cand = (cur + " " + word) if cur else word
        if vis(cand) <= w:
            cur = cand
        else:
            if cur:
                out.append(cur)
            if len(out) >= maxl:
                return [clip(x, w) for x in out]
            cur = word
    if cur:
        out.append(cur)
    return [clip(x, w) for x in out[:maxl]]


# Etiquetas CORTAS de los pins del lanzador: el label del schema («Tema del
# hub», «Modo del latido») es largo para una fila de la caja.
_PIN_CORTO = {"ui.background": "fondo", "ui.theme": "tema",
              "ui.brightness": "brillo", "ui.redlight": "luz roja",
              "ui.autostart": "auto-abrir",
              "latido.mode": "latido",
              "ui.split": "split", "ui.anim": "animación"}
# clave i18n paralela por setting (misma palabra, traducible)
_PIN_I18N = {"ui.background": "hub.pin.background", "ui.theme": "hub.pin.theme",
             "ui.brightness": "hub.pin.brightness",
             "ui.redlight": "hub.pin.redlight",
             "ui.autostart": "hub.pin.autostart",
             "latido.mode": "hub.pin.heartbeat",
             "ui.split": "hub.pin.split", "ui.anim": "hub.pin.anim"}


# ── LAYOUT: lanzador — el hub MÍNIMO (estilo lanzador de apps) ──────────────
# Pedido del socio 2026-10-12, inspirado en el lanzador de Omarchy (walker):
# UNA sola lista que fluye — escribe para filtrar, Enter entra, Esc regresa.
#
#         ╭─ WORKSPACE ─────────────╮
#         │ › buscar…                │
#         │                          │
#         │ ❯ Zenith   claude-code   │      raíz: los agentes (nombre + motor),
#         │   Atlas    codex         │      un separador y las tres secciones
#         │ ──────────────────────── │      como filas de la MISMA lista
#         │   Menú              ›    │
#         │   Personalización   ›    │
#         │   Idioma            ›    │
#         ╰──────────────────────────╯
#            Enter entra · Esc regresa · escribe para buscar
#
# Enter en un agente lo lanza (lo de siempre); en una fila `›` entra: la MISMA
# caja muestra ese submenú (las entradas de siempre del menú, los pins de
# personalización o los idiomas) y el título se vuelve migas de pan
# (WORKSPACE › MENÚ). Esc regresa un nivel (con búsqueda, primero la limpia).
#
# Búsqueda «escribe primero» (regla de teclas, front.lz_key): toda letra y
# todo carácter imprimible ESCRIBE en la búsqueda — los atajos de una letra
# (menú, m, i, l) ceden; lo que queda: `q` sale SOLO con la búsqueda vacía,
# los dígitos 1-9 apuntan/lanzan agentes SOLO con la búsqueda vacía, ⌫ borra,
# Esc limpia. Motor e información del agente seleccionado pasan a → y Tab.
# En la raíz la búsqueda es GLOBAL: encuentra también lo de dentro de los
# submenús (p. ej. «tema» → Personalización › tema), con la miga tenue.
# Filtrado sin mayúsculas ni acentos.
#
# Geometría: una BARRA de TAMAÑO FIJO en todos los niveles y en cualquier
# ventana (pedido del socio 2026-10-12) — ancho = la fila más ancha de
# cualquier nivel + aire modesto (ni el título ni la búsqueda la ensanchan),
# alto = línea de búsqueda + LZ_ROWS filas (una lista corta deja aire dentro;
# una larga hace scroll con posición en el título y ▲/▼). La barra va
# centrada, un poco arriba del medio del aire entre el wordmark y los chips,
# que van al fondo en una fila según el contexto (raíz · submenú · buscando).
# Con poco alto se cede en orden: chips en una línea → wordmark compacto →
# sin cabecera. La ventana se puede achicar hasta el tamaño de la caja
# (lanzador_min_size); por debajo, front usa la vista angosta.

import unicodedata as _ud

LZ_ROWS = 12          # filas de lista FIJAS (además de la línea de búsqueda)
LZ_PAD = 2            # aire por lado dentro de la barra (+1 del borde = 3)
_LZ_SUBS = ("tools", "latido", "idioma")      # secciones → grupos de front
_LZ_SELECTABLE = ("agent", "sub", "opt", "pin", "lang")


def lanzador_pins():
    """Pins de PERSONALIZACIÓN del lanzador: los anclados (ui.hub_pins), tal
    cual. Sin `ui.layout`: el selector de layouts NO se expone al cliente
    (pedido del socio 2026-10-12 — los layouts viejos son de antes del
    rebranding). Mismo shape que settings.hub_pins_resolved(); front.py usa
    ESTA lista con el lanzador activo, así el índice de cfg_focus coincide
    con lo pintado. Falla-suave TOTAL → []."""
    try:
        import settings as _st
        return list(_st.hub_pins_resolved() or [])
    except Exception:
        return []


def _lz_pin_label(p):
    """Etiqueta CORTA de un pin (traducible)."""
    k = p.get("key", "")
    corto = _PIN_CORTO.get(k, "")
    if corto:
        return _t(_PIN_I18N.get(k, k), corto)
    return (p.get("label") or k).split(" ")[0].lower()


def _lz_norm(s):
    """Texto para comparar: sin acentos, sin mayúsculas, espacios simples."""
    s = _ud.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not _ud.combining(c))
    return " ".join(s.casefold().split())


def lanzador_sub_label(g):
    """Nombre de una sección como fila de la lista («Menú»…)."""
    return {"tools": _t("hub.lanzador.tab.menu", "Menú"),
            "latido": _t("hub.lanzador.tab.personalization",
                         "Personalización"),
            "idioma": _t("hub.lanzador.tab.lang", "Idioma")}.get(g, g)


def lanzador_sub_title(g):
    """Nombre de una sección en el título (migas de pan)."""
    return {"tools": _t("hub.section.menu", "MENÚ"),
            "latido": _t("hub.section.personalization", "PERSONALIZACIÓN"),
            "idioma": _t("hub.section.lang", "IDIOMA · LANGUAGE")}.get(g, g)


def _lz_sub_items(data, g):
    """Filas de un submenú — las MISMAS fuentes que los demás layouts."""
    if g == "tools":
        # sin la letra de salto: en el lanzador las letras ESCRIBEN en la
        # búsqueda (regla «escribe primero») — pintarla engañaría
        return [{"kind": "opt", "idx": j, "label": lbl, "dato": ""}
                for j, (_tok, lbl) in enumerate(data.get("opts") or ())]
    if g == "latido":
        return [{"kind": "pin", "idx": i, "label": _lz_pin_label(p),
                 "dato": str(p.get("value", ""))}
                for i, p in enumerate(lanzador_pins())]
    if g == "idioma":
        try:
            import i18n
            langs, act = list(i18n.available()), i18n.lang()
        except Exception:
            langs, act = [], ""
        return [{"kind": "lang", "idx": i, "label": name,
                 "dato": "●" if code == act else ""}
                for i, (code, name) in enumerate(langs)]
    return []


def lanzador_subs():
    """Secciones presentes — el MISMO criterio que arma los grupos de
    front.py: Menú e Idioma siempre, Personalización solo con pins."""
    return [g for g in _LZ_SUBS if g != "latido" or lanzador_pins()]


def lanzador_items(data, level=None, q=""):
    """La lista del lanzador para (nivel, búsqueda) → [{kind, idx, label,
    dato, crumb, off}]. kind ∈ agent/sub/opt/pin/lang (seleccionables) ·
    sep/info/none (solo se pintan). front.py y el renderer usan ESTA función
    — lo que se ve y lo que Enter ejecuta son la misma lista."""
    ags = []
    for i, a in enumerate(data.get("agents") or ()):
        ags.append({"kind": "agent", "idx": i,
                    "label": a.get("display") or a.get("name") or "?",
                    "dato": (a.get("engine_eff") or a.get("engine")
                             or "?").strip() or "?",
                    "off": not a.get("active")})
    subs = [{"kind": "sub", "idx": g, "label": lanzador_sub_label(g),
             "dato": "›"} for g in lanzador_subs()]
    qn = _lz_norm(q)
    if level in _LZ_SUBS:
        its = _lz_sub_items(data, level)
        if qn:
            its = [it for it in its if qn in _lz_norm(it["label"])]
            if not its:
                its = [{"kind": "none", "label": _t(
                    "hub.lanzador.no_results", "sin resultados")}]
        return its
    if not qn:
        if not ags:
            ags = [{"kind": "info", "label": _t(
                "hub.lanzador.empty", "sin agentes — Menú › Agentes")}]
        return ags + [{"kind": "sep"}] + subs
    out = [a for a in ags if qn in _lz_norm(a["label"])]
    out += [s for s in subs if qn in _lz_norm(s["label"])]
    for g in lanzador_subs():                    # búsqueda GLOBAL
        for it in _lz_sub_items(data, g):
            if qn in _lz_norm(it["label"]):
                it["crumb"] = lanzador_sub_label(g)
                out.append(it)
    if not out:
        out = [{"kind": "none", "label": _t("hub.lanzador.no_results",
                                            "sin resultados")}]
    return out


def lanzador_first(items):
    """Índice del primer seleccionable (0 si no hay)."""
    for i, it in enumerate(items):
        if it.get("kind") in _LZ_SELECTABLE:
            return i
    return 0


def lanzador_step(items, sel, step):
    """Siguiente seleccionable en anillo desde `sel` (salta separadores)."""
    n = len(items)
    if not n:
        return 0
    i = sel
    for _ in range(n):
        i = (i + step) % n
        if items[i].get("kind") in _LZ_SELECTABLE:
            return i
    return sel


def _lz_arrows(it):
    """True si la fila lleva ‹ › alrededor del motor (agente activo, sin miga
    de búsqueda): ←→ lo cambian."""
    return (it.get("kind") == "agent" and not it.get("off")
            and not it.get("crumb"))


def _lz_row_width(it):
    if it.get("kind") == "info":                 # «sin agentes — Menú › …»: se
        return vis(_sane(str(it.get("label") or "")))   # lee ENTERO (1er uso)
    if it.get("kind") not in _LZ_SELECTABLE:
        return 0
    d = vis(_sane(str(it.get("dato") or "")))
    if d and _lz_arrows(it):
        d += 4                                   # «‹ » + « ›», apuntado o no
    return 2 + vis(_sane(str(it["label"]))) + ((2 + d) if d else 0)


def _lz_row(it, on, ancho, K):
    """Una fila de la barra: cursor, etiqueta a la izquierda y el dato
    (motor · tecla · valor · ● · ›) — o la miga tenue de un resultado de
    búsqueda global — pegado a la DERECHA del ancho común."""
    kind = it.get("kind")
    if kind == "sep":
        return "%s%s%s" % (K["DK"], K["SEP"] * ancho, K["R"])
    if kind in ("info", "none"):
        return "%s%s%s" % (K["DIM"], clip(_sane(it["label"]), ancho), K["R"])
    lab = _sane(str(it["label"]))
    off = it.get("off")
    cur = ("%s%s%s " % (K["C"] + K["BO"], K["PTR"], K["R"]) if on else "  ")
    tinta = (K["C"] + K["BO"]) if on else (K["DK"] if off else K["INACTIVE"])
    crumb = it.get("crumb")
    dato = _sane(str(crumb if crumb else (it.get("dato") or "")))
    # reserva para el dato: lo justo para un dato corto («›», «●»: 3 col) y
    # 4 para los largos, como siempre (la etiqueta manda). Un 4 fijo
    # recortaba «Personalización» en la caja más angosta (sin agentes).
    reserva = min(4, 2 + vis(dato)) if dato else 0
    lab = clip(lab, max(1, ancho - 2 - reserva))
    ln = "%s%s%s%s" % (cur, tinta, lab, K["R"])
    if dato:
        flechas = _lz_arrows(it)
        libre = ancho - 2 - vis(lab) - 2 - (4 if flechas else 0)
        dato = clip(dato, max(1, libre))
        dcol = K["DK"] if (crumb or off) else (K["B2"] if on else K["DIM"])
        pinta = "%s%s%s" % (dcol, dato, K["R"])
        if flechas:
            # ‹ motor › solo en el apuntado (ahí ←→ lo cambian); los demás
            # guardan el mismo hueco para que la columna no baile
            pinta = ("%s‹%s %s %s›%s" % (K["C"] + K["BO"], K["R"], pinta,
                                         K["C"] + K["BO"], K["R"])
                     if on else "  %s  " % pinta)
        ln += " " * max(2, ancho - 2 - vis(lab) - vis(dato)
                        - (4 if flechas else 0)) + pinta
    return ln


def _lz_chips(data, level, q):
    """Pares (tecla, acción) del pie SEGÚN el contexto — raíz · submenú ·
    buscando. Orden = prioridad (el colapso conserva los primeros y q)."""
    mueve = ("↑↓", _t("common.hint.move", "mueve"))
    entra = ("Enter", _t("common.hint.enter", "entra"))
    escribe = (_t("hub.lanzador.hint.type_key", "abc"),
               _t("hub.lanzador.hint.search", "busca"))
    sale = ("q", _t("common.hint.quit", "sale"))
    if q:
        return [mueve, entra, ("⌫", _t("hub.lanzador.hint.erase", "borra")),
                ("Esc", _t("hub.lanzador.hint.clear", "limpia"))]
    if level in _LZ_SUBS:
        return [mueve, entra, ("Esc", _t("hub.lanzador.hint.back2",
                                         "regresa")), escribe, sale]
    return [mueve, entra, escribe,
            ("←→", _t("common.hint.engine", "motor")),
            ("Tab", _t("common.hint.info", "información")), sale]


def lanzador_box_width(data):
    """Ancho FIJO de la caja: la fila más ancha de CUALQUIER nivel (raíz +
    los submenús) + LZ_PAD por lado + bordes. No depende de la ventana."""
    anchos = [_lz_row_width(it) for it in lanzador_items(data or {}, None, "")]
    for g in _LZ_SUBS:
        anchos += [_lz_row_width(it) for it in _lz_sub_items(data or {}, g)]
    return max(anchos + [16]) + 2 * LZ_PAD + 4


# alto mínimo: caja (bordes 2 + búsqueda 2 + LZ_ROWS) + aviso 1 + chips en
# una línea 1 + la fila libre del fondo (front dibuja h-1 líneas)
LZ_MIN_H = LZ_ROWS + 4 + 1 + 1 + 1


def lanzador_min_size(data=None):
    """(ancho, alto) mínimos de ventana para dibujar el hub completo: el
    tamaño de la caja fija + aviso + una fila de chips. Por debajo, front
    cae a la vista angosta/vertical. Sin `data` (sin agentes que medir) el
    ancho es el de la caja vacía."""
    try:
        return lanzador_box_width(data) + 1, LZ_MIN_H
    except Exception:
        return 40, LZ_MIN_H


def render_lanzador(data, view, K, w):
    """`lanzador` — ver el bloque de arriba. Con view.h mide EXACTAMENTE h-1
    líneas; sin h, una altura natural que tampoco depende de la selección ni
    del nivel (el BH del redraw). Lee de view: lz_level (None = raíz),
    lz_q (búsqueda), lz_sel (índice en lanzador_items), msg/hb_msg."""
    K = cols(K)
    h = view.get("h") or 0
    W = w - 1
    level = view.get("lz_level")
    level = level if level in _LZ_SUBS else None
    q = str(view.get("lz_q") or "")
    items = lanzador_items(data, level, q)
    sel = view.get("lz_sel")
    if not isinstance(sel, int) or not (0 <= sel < len(items)) or \
            items[sel].get("kind") not in _LZ_SELECTABLE:
        sel = lanzador_first(items)
    hchar = K["BOX"][5]

    # ── cabecera: wordmark + versión (lo único que queda arriba) ──
    build = " · ".join(p for p in (
        ("v" + data["version"]) if data.get("version") else "",
        data.get("version_text") or "") if p)

    def _sub():
        return [clip(" " * max(0, (W - vis(build)) // 2) + "%s%s%s" % (
            K["DIM"], build, K["R"]), W)] if build else []

    def cabecera(nivel):
        if nivel == "full":
            return [""] + big_title(K, w, 0, indent=" ", center=True) + _sub()
        if nivel == "compact":
            return big_title(K, w, 0, compact=True, center=True) + _sub()
        if nivel == "tiny":
            return big_title(K, w, 0, compact=True, center=True)
        return []

    # ── chips del pie: UNA fila centrada al fondo, según el contexto ──
    pares = _lz_chips(data, level, q)

    def chips(nivel):
        if nivel == 3:
            need = (sum(vis(" %s %s " % pr) + 2 for pr in pares)
                    + 3 * (len(pares) - 1))
            rows = instruction_buttons(K, pares, W) if need <= W else []
            if rows:
                lp0 = " " * max(0, (W - vis(rows[0])) // 2)
                return [clip(lp0 + r, W) for r in rows]
            nivel = 1
        if nivel == 1:
            ln = keyline(K, pares, W)
            return ([clip(" " * max(0, (W - vis(ln)) // 2) + ln, W)]
                    if ln else [])
        return []

    # ── ANCHO FIJO: la fila más ancha de CUALQUIER nivel (raíz + los tres
    #    submenús) + LZ_PAD por lado + bordes. Ni el título, ni la búsqueda,
    #    ni las migas de un resultado la ensanchan (se recortan). ──
    pw = min(W, lanzador_box_width(data))
    ancho_op = max(1, pw - 4 - 2 * LZ_PAD)
    inner = pw - 4
    lp_n = max(0, (W - pw) // 2)
    lp = " " * lp_n

    # ── presupuesto vertical: cabecera + caja (bordes 2 + búsqueda 2 + filas)
    #    + aviso (1) + chips. La caja es de alto FIJO (LZ_ROWS filas): lo que
    #    cede con poco alto es la cabecera (grande → compacta → nada) y los
    #    chips (botones → una línea). front no dibuja por debajo de
    #    lanzador_min_size(); la lista solo se recorta como red de seguridad. ──
    H = h - 1 if h else 0
    niveles = (("full", 3), ("full", 1), ("compact", 3), ("compact", 1),
               ("tiny", 1), ("none", 1), ("none", 0))

    def fijo(nv):
        return len(cabecera(nv[0])) + len(chips(nv[1])) + 2 + 2 + 1

    elegido, ih = None, LZ_ROWS
    if H:
        for nv in niveles[:-1]:
            if H - fijo(nv) >= LZ_ROWS:
                elegido = nv
                break
        if elegido is None:
            # ventana más baja que la caja: la lista cede filas ANTES que la
            # línea de atajos (sin ella nadie sabe cómo moverse); sin sitio
            # ni para eso, solo la caja
            elegido = niveles[-2] if H - fijo(niveles[-2]) >= 4 else niveles[-1]
        ih = max(1, min(LZ_ROWS, H - fijo(elegido)))
    else:
        # sin alto (banner): altura NATURAL fija — no depende del nivel
        elegido = niveles[0]
        H = len(cabecera("full")) + 1 + (ih + 4) + 1 + 2 + 3
    top = cabecera(elegido[0])
    pie = chips(elegido[1])

    # ── la lista: scroll con la selección SIEMPRE visible ──
    n = len(items)
    start = max(0, min(sel - ih // 2, n - ih)) if n > ih else 0
    arriba_mas, abajo_mas = start > 0, start + ih < n
    selec = [i for i, it in enumerate(items)
             if it.get("kind") in _LZ_SELECTABLE]
    marca = ""
    if n > ih and sel in selec:
        marca = "%d/%d %s%s" % (selec.index(sel) + 1, len(selec),
                                "▲" if arriba_mas else "",
                                "▼" if abajo_mas else "")
        marca = marca.strip()
    # título = migas de pan; se ACORTA (jamás ensancha la barra)
    raiz = _t("hub.lanzador.root", "WORKSPACE")
    cands = ([raiz] if level is None else
             ["%s › %s" % (raiz, lanzador_sub_title(level)),
              "‹ %s" % lanzador_sub_title(level)])
    tt = None
    for c in cands:
        cc = ("%s · %s" % (c, marca)) if marca else c
        if vis(cc) <= pw - 7:
            tt = cc
            break
    if tt is None:
        tt = marca or cands[-1]
    # línea de búsqueda + respiro
    if q:
        busq = "%s› %s%s%s%s▏%s" % (K["C"] + K["BO"], K["R"], K["WH"],
                                    clip(_sane(q), max(1, ancho_op - 3)),
                                    K["C"], K["R"])
    else:
        busq = "%s› %s%s" % (K["DK"], _t("hub.lanzador.search_ph",
                                         "buscar…"), K["R"])
    cuerpo = [pad(" " * LZ_PAD + busq, inner), ""]
    for i in range(start, min(n, start + ih)):
        ln = pad(" " * LZ_PAD + _lz_row(items[i], i == sel, ancho_op, K),
                 inner - 1)
        if i == start and arriba_mas:
            ln += "%s▲%s" % (K["DIM"], K["R"])
        elif i == start + ih - 1 and abajo_mas:
            ln += "%s▼%s" % (K["DIM"], K["R"])
        cuerpo.append(ln)
    caja = full_box(tt, cuerpo, K, pw, ih + 2, True, border=K["C"],
                    label=K["C"] + K["BO"])
    caja = [clip(lp + ln, W) for ln in caja]

    aviso = view.get("hb_msg") or view.get("msg") or ""
    aviso = _sane(aviso)
    fila_aviso = (clip(" " * max(0, (W - vis(aviso)) // 2) + "%s%s%s" % (
        K["DIM"], aviso, K["R"]), W) if aviso else "")

    # ── composición vertical: la barra (alto FIJO) en el aire entre el
    #    wordmark y los chips, un poco ARRIBA del centro (1/3 arriba) ──
    grupo = (ih + 4) + 1
    libre = H - len(top) - grupo - len(pie)
    arriba = max(0, libre // 3)
    L = list(top) + [""] * arriba
    base_caja = len(L)
    L += caja + [fila_aviso]
    L += [""] * max(0, libre - arriba)
    L += pie
    if len(L) > H:                    # jamás desborda; el pie se queda abajo
        L = (L[:H - len(pie)] + pie) if len(pie) < H else L[:H]
    L += [""] * max(0, H - len(L))

    # ── hit-map (filas 0-based del bloque): filas de la lista + migas ──
    hit = []
    x0 = lp_n + 2
    for r, i in enumerate(range(start, min(n, start + ih))):
        row = base_caja + 3 + r
        if row < len(L) and items[i].get("kind") in _LZ_SELECTABLE:
            hit.append((row, x0, x0 + inner, "lz", i))
    if level is not None and base_caja < len(L):
        hit.append((base_caja, lp_n, lp_n + pw, "crumb", 0))
    view["hit"] = hit
    return L


# ── REGISTRO ────────────────────────────────────────────────────────────────
# El LANZADOR es el hub oficial y el ÚNICO layout (2026-10-12): los demás
# (clásico, centro, día, hud, cockpit…) salieron del código y viven en la
# etiqueta git `archivo/layouts-pre-lanzador`. min_w/min_h = el tamaño de
# la caja fija + su pie: por debajo, front cae a la vista angosta/vertical.
LANZADOR = {"id": "lanzador", "render": None, "min_w": 0, "min_h": 0}


def active(explicit=None):
    """La entrada del layout del hub (siempre el lanzador). `explicit` se
    acepta por compatibilidad de firma y se ignora. Jamás levanta."""
    L = dict(LANZADOR)
    L["render"] = render_lanzador
    L["label"] = _t("hub.layout.lanzador", "Lanzador — agentes al centro, mínimo")
    L["min_w"], L["min_h"] = lanzador_min_size()
    return L


def section_word(section):
    return _t("section.title." + section, section.upper())
