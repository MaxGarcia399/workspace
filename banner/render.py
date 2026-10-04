#!/usr/bin/env python3
"""WORKSPACE · render — banner rico del harness para la terminal.

Wordmark WORKSPACE + emblema (braille, dorado) + panel del harness, estilo del
banner de Zenith pero con paleta DORADA y contenido = info del harness.
Emblema actual: Templo C (esbelto). Las variantes (Templo A/B/C, esfera) quedan
guardadas en `preview.py` / `workspace-opciones.html` para seguir iterando.
Cero dependencias (stdlib). Reusa el motor braille de preview.py.
"""
import os, sys, re

try:   # B2 · Windows: UTF-8 en stdout/err — evita UnicodeEncodeError con el braille
       # dorado del banner bajo cp1252 cuando un pipe captura la salida.
       # No-op en Mac/Linux (UTF-8 ya es default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preview import make_temple, CX, CY, DOTS, BAYER, _seg, _tri, _spark, _leaf, _disk   # diseño 88×100


def fg(n):
    return f"\033[38;5;{n}m"


# ── PALETA por TEMA (tuitheme.py, raíz de WORKSPACE): mismo tema que el resto
#    del harness (env WORKSPACE_THEME > ui.theme > olympo). Default olympo =
#    los índices 256 dorados de SIEMPRE (paridad exacta). Falla-suave
#    ABSOLUTA: sin tuitheme → los literales de siempre. ─────────────────────
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
try:
    import tuitheme as _tuitheme
    _TH = _tuitheme.palette()
except Exception:
    _TH = None

if _TH:
    R, BO = _TH.R, _TH.BO
    DK, DIM, B2, B, C, WH = _TH.DK, _TH.DIM, _TH.B2, _TH.B, _TH.C, _TH.WH
    _INACTIVE = _TH.INACTIVE
    _GL = _TH.GLYPHS
else:
    R = "\033[0m"; BO = "\033[1m"
    # paleta dorada (oscuro → claro)
    DK, DIM, B2, B, C, WH = (fg(94), fg(136), fg(178), fg(214), fg(221), fg(230))
    # Contraste activo/inactivo: dios INACTIVO en ámbar (136) — dorado apagado,
    # mismo lenguaje visual que el menú de HERRAMIENTAS. Windows-safe: solo ANSI color.
    _INACTIVE = fg(136)
    _GL = {"box": "╭╮╰╯│─", "base": "▁"}
# glifos del tema: esquinas/bordes de la caja + base del altar
_BTL, _BTR, _BBL, _BBR, _BV, _BH = _GL.get("box", "╭╮╰╯│─")
_GBASE = _GL.get("base", "▁")

TEMPLE = make_temple(8, 32, 2.3, -40, -22, 34, 17)   # Templo C

AW, AH = 30, 17
DWr, DHr = AW * 2, AH * 4
CXr, CYr = (DWr - 1) / 2, (DHr - 1) / 2
SCALE = 0.72
SCAN_P, SCAN_G = 6, 1


def tone(v):
    return (WH if v >= .80 else C if v >= .60 else B if v >= .44
            else B2 if v >= .30 else DIM if v >= .17 else DK)


def render_art():
    rows = []
    for rr in range(AH):
        cells, run, rc = [], "", None
        for cc in range(AW):
            bits, peak = 0, 0.0
            for ix, iy, bit in DOTS:
                xx, yy = cc * 2 + ix, rr * 4 + iy
                ddx = (xx - CXr) / SCALE + CX
                ddy = (yy - CYr) / SCALE + CY
                vv = TEMPLE(ddx, ddy)
                if yy % SCAN_P >= SCAN_P - SCAN_G:
                    vv = 0.0
                peak = max(peak, vv)
                if vv ** 0.30 > (BAYER[yy % 4][xx % 4] + .5) / 16.0:
                    bits |= bit
            ch = " " if bits == 0 else chr(0x2800 + bits)
            col = None if bits == 0 else tone(peak)
            if col == rc:
                run += ch
            else:
                if run:
                    cells.append((run, rc))
                run, rc = ch, col
        if run:
            cells.append((run, rc))
        rows.append("".join(c if k is None else f"{k}{c}{R}" for c, k in cells))
    return rows


# flicker (dy, dx, dh, ds): alto del ápice · deriva lateral · asimetría · "respiración"
_FLK = [
    (0.0, 0.0, 0.0, 0.0), (-0.4, 0.3, 0.3, 0.5), (-0.7, 0.5, 0.5, 0.9),
    (-0.4, 0.6, 0.2, 0.6), (0.2, 0.3, -0.2, 0.1), (0.5, -0.3, -0.4, -0.4),
    (0.3, -0.6, -0.2, -0.2), (-0.1, -0.5, 0.2, 0.3), (-0.5, -0.2, 0.4, 0.7),
    (-0.2, 0.1, 0.1, 0.4),
]

# FUEGO por dios: cada llama se queda DENTRO de su familia de color (borde oscuro →
# núcleo luminoso pero tintado), para que se distinga al instante de quién es.
FIRES = {
    "red":   [fg(c) for c in (52, 88, 124, 160, 196, 197, 203, 209, 210, 216, 217, 224)],   # Atlas
    "blue":  [fg(c) for c in (17, 18, 19, 20, 26, 27, 33, 39, 45, 51, 117, 159)],            # Zenith
    "green": [fg(c) for c in (22, 28, 34, 40, 46, 47, 48, 83, 84, 120, 157, 194)],           # Argus
}
FIRE = _TH.FIRE if _TH else FIRES["red"]   # llama del RECINTO: la define el tema
OFF = _TH.OFF if _TH else fg(240)           # urna apagada (metal frío)


def fire_tone(v, pal=None):
    pal = pal or FIRE
    t = (v - 0.42) / 0.58                     # estira el rango de la llama sobre toda la paleta
    return pal[int(max(0.0, min(0.999, t)) * len(pal))]


# brasa en reposo (urna apagada): tenue → ascua. Y ceniza que sube lento.
_EMBER_REST = _TH.EMBER if _TH else [fg(c) for c in (58, 94, 130, 166)]
_REST_COALS = [(-6.6, 18.4, 1.6), (-2.3, 19.0, 1.8), (2.3, 18.8, 1.7),
               (6.6, 18.4, 1.6), (0.0, 17.9, 1.5)]
_ASH = [(-3.0, 16, 11, 0.5), (2.5, 15, 13, -0.4), (-0.5, 17, 9, 0.3)]   # (dx, y_base, periodo, deriva)


def ember_tone(v):
    return _EMBER_REST[int(max(0.0, min(0.999, v)) * len(_EMBER_REST))]


def f_urn_rest(x, y, ph=0):
    """Urna APAGADA: brasas en reposo que respiran + ceniza que sube lento (sutil)."""
    cx = 15.0
    pulse = 0.78 + 0.22 * (_FLK[ph % len(_FLK)][3])        # respiración leve
    v = 0.0
    for sx, sy, sr in _REST_COALS:
        v = max(v, _disk(x, y, cx + sx, sy, sr) * 0.52 * pulse)
    for i, (px, py, per, dr) in enumerate(_ASH):
        k = (ph + i * 3) % per
        ey = py - k * 1.0                                  # sube lento
        ex = cx + px + dr * (k / per) * 1.4                # deriva
        if ey > 2.0:
            v = max(v, _disk(x, y, ex, ey, 0.7) * 0.32 * (1.0 - k / per))
    return v


# partículas/chispas: (dx_desde_cx, y_base, periodo, deriva). Las de deriva grande y
# arranque bajo (cerca del fuego) BRINCAN a los lados en arco; las demás suben flotando.
_PARTS = [
    # brasas que saltan a los lados (arranque bajo · deriva grande)
    (-1.0, 16, 9, -2.6), (1.0, 16, 10, 2.4), (-2.0, 15, 8, -3.0), (2.0, 15, 9, 2.8),
    (-0.5, 17, 11, -2.2), (0.5, 17, 10, 2.0), (-3.0, 16, 9, -3.4), (3.0, 16, 8, 3.2),
    (-1.5, 14, 7, -2.8), (1.5, 14, 7, 2.6), (-2.5, 17, 12, -3.2), (2.5, 17, 11, 3.0),
    # chispas que suben (deriva leve)
    (-5.5, 11, 7, -0.8), (-2.0, 9, 9, 0.5), (1.5, 12, 6, 0.7), (4.5, 10, 8, -0.6),
    (-3.5, 7, 5, 0.6), (3.5, 8, 10, -0.4), (0.0, 6, 7, 0.3), (-6.5, 13, 9, 0.9),
    (6.0, 13, 6, -0.8), (-1.0, 5, 4, 0.4), (1.2, 5, 5, -0.4), (-4.0, 6, 6, 0.7),
    (4.0, 6, 7, -0.6), (0.6, 4, 4, 0.2), (-2.6, 7, 8, -0.4), (2.6, 8, 9, 0.4),
]


def f_torch_base(x, y):
    """Envase ANCHO y bajo (cuenco poco profundo + base) — metal dorado. Espacio 30×36, cx=15."""
    cx = 15.0
    v = _seg(x, y, cx - 10.0, 19.0, cx + 10.0, 19.0, 1.5)        # labio del cuenco (MUY ancho)
    v = max(v, _seg(x, y, cx - 9.3, 20.7, cx + 9.3, 20.7, 1.0))  # doble labio
    v = max(v, _seg(x, y, cx - 10.0, 19.8, cx - 4.8, 24.6, 1.3)) # pared izq (poco profunda)
    v = max(v, _seg(x, y, cx + 10.0, 19.8, cx + 4.8, 24.6, 1.3)) # pared der
    v = max(v, _seg(x, y, cx - 4.8, 24.6, cx + 4.8, 24.6, 1.3))  # fondo del cuenco
    v = max(v, _seg(x, y, cx - 3.2, 24.6, cx - 3.2, 28.2, 1.4))  # pie izq
    v = max(v, _seg(x, y, cx + 3.2, 24.6, cx + 3.2, 28.2, 1.4))  # pie der
    v = max(v, _seg(x, y, cx - 8.5, 29.6, cx + 8.5, 29.6, 1.7))  # base ancha
    return v


def f_torch_flame(x, y, ph=0):
    """Llamas (varias capas) + chispa + brasas — fuego luminoso. ph=fase. Espacio 30×36, cx=15."""
    cx = 15.0
    dy, dx, dh, ds = _FLK[ph % len(_FLK)]
    dy, dx, dh, ds = dy * 1.7, dx * 1.7, dh * 1.7, ds * 1.7      # escalar el flicker
    v = _tri(x, y, cx + dx * 0.6, 3.6 + dy - ds, 18.0, 6.3 + ds * 0.5, 2.0)     # llama central (punta más limpia)
    v = max(v, _tri(x, y, cx - 5.0 + dx, 7.5 - dh * 0.3, 18.0, 3.4 + dh, 1.5))  # llama izq
    v = max(v, _tri(x, y, cx + 5.0 + dx, 7.5 + dh * 0.3, 18.0, 3.4 - dh, 1.5))  # llama der
    v = max(v, _tri(x, y, cx - 2.4 + dx * 0.5, 5.4 - ds, 16.5, 2.2, 1.2))       # capa interior izq (núcleo)
    v = max(v, _tri(x, y, cx + 2.4 + dx * 0.5, 5.4 - ds, 16.5, 2.2, 1.2))       # capa interior der
    v = max(v, _spark(x, y, cx + dx * 0.5, 4.2 + dy * 0.5 - ds * 0.5, 2.0 + ds * 0.4, .9, 6))  # núcleo (más abajo, no toca el techo)
    for sx, sy, sr in [(cx - 6.6, 18.4, 2.0), (cx - 2.3, 19.0, 2.2), (cx + 2.3, 18.8, 2.1),
                       (cx + 6.6, 18.4, 2.0), (cx, 17.8, 1.8)]:  # piedras/brasas en la boca (color brasa)
        v = max(v, _disk(x, y, sx, sy, sr) * 0.66)
    # partículas/chispas: suben Y brincan en arco hacia los lados (brasas que saltan del fuego)
    for i, (px, py, per, dr) in enumerate(_PARTS):
        k = (ph + i * 2) % per
        f = k / per
        ey = py - k * 1.2                       # sube
        ex = cx + px + dr * (f ** 1.4) * 3.2    # arco: acelera hacia el lado al subir
        if ey > 0.4:                            # se apaga antes del techo (sin corte plano)
            v = max(v, _disk(x, y, ex, ey, 1.0) * (0.96 - 0.45 * f))
    return v


def _render_torch(ph=0, cols=13, rows_n=9, gamma=0.35):
    """Urna+fuego (cols×rows_n celdas): llamas en FUEGO + urna en metal/dorado, en fase `ph`."""
    rows = []
    for rr in range(rows_n):
        cells, run, rc = [], "", None
        for cc in range(cols):
            bits, pf, pb = 0, 0.0, 0.0
            for ix, iy, bit in DOTS:
                xx, yy = cc * 2 + ix, rr * 4 + iy
                vf = f_torch_flame(xx, yy, ph)
                vb = f_torch_base(xx, yy)
                pf = max(pf, vf); pb = max(pb, vb)
                if max(vf, vb) ** gamma > (BAYER[yy % 4][xx % 4] + .5) / 16.0:
                    bits |= bit
            if not bits:
                ch, col = " ", None
            else:
                ch = chr(0x2800 + bits)
                col = fire_tone(pf) if pf >= pb else tone(pb)
            if col == rc:
                run += ch
            else:
                if run:
                    cells.append((run, rc))
                run, rc = ch, col
        if run:
            cells.append((run, rc))
        rows.append("".join(c if k is None else f"{k}{c}{R}" for c, k in cells))
    return rows


def _render_urn(ph=0, pal=None, cols=15, rows_n=9, gamma=0.35, ig=1.0):
    """Urna para el altar. pal=None → APAGADA (metal frío, sin fuego). pal=lista de
    fuego → ENCENDIDA con ese color + llamas/chispas animadas (fase ph). `ig` (0..1) =
    encendido GRADUAL: la llama crece (×ig) mientras las brasas ceden (×1-ig)."""
    lit = pal is not None
    rows = []
    for rr in range(rows_n):
        cells, run, rc = [], "", None
        for cc in range(cols):
            bits, pf, pb, pe = 0, 0.0, 0.0, 0.0
            for ix, iy, bit in DOTS:
                xx, yy = cc * 2 + ix, rr * 4 + iy
                if lit:
                    flame = f_torch_flame(xx, yy, ph)
                    core = _disk(xx, yy, 15.0, 20.0, 2.8) * 1.05  # núcleo: círculo brillante en la base
                    vf = max(flame, core) * ig                    # llama + núcleo crecen al encender
                    ve = f_urn_rest(xx, yy, ph) * (1.0 - ig)      # las brasas ceden a la llama
                else:
                    vf = 0.0
                    ve = f_urn_rest(xx, yy, ph)                   # apagada: brasas en reposo
                vb = f_torch_base(xx, yy)
                pf = max(pf, vf); pb = max(pb, vb); pe = max(pe, ve)
                if max(vf, vb, ve) ** gamma > (BAYER[yy % 4][xx % 4] + .5) / 16.0:
                    bits |= bit
            if not bits:
                ch, col = " ", None
            elif pf >= pb and pf > 0.0:
                ch, col = chr(0x2800 + bits), fire_tone(pf, pal)   # llama (crece con ig)
            elif pe > pb and pe > 0.0:
                ch, col = chr(0x2800 + bits), ember_tone(pe)       # brasa/ceniza tenue
            else:
                ch, col = chr(0x2800 + bits), tone(pb)             # base normal (metal dorado)
            if col == rc:
                run += ch
            else:
                if run:
                    cells.append((run, rc))
                run, rc = ch, col
        if run:
            cells.append((run, rc))
        rows.append("".join(c if k is None else f"{k}{c}{R}" for c, k in cells))
    return rows


def f_dove(x, y):
    """Paloma de la paz en vuelo (dot-space 24×28), mirando a la derecha.
    Silueta clara: cuerpo + cuello + cabeza separada, ala barrida arriba, cola en abanico."""
    cx, cy = 10.0, 16.0
    v = _leaf(x, y, cx, cy, 1, 0.10, 5.8, 2.7)                           # cuerpo (gota)
    v = max(v, _seg(x, y, cx + 4.3, cy - 1.4, cx + 6.0, cy - 4.0, 1.3))  # cuello
    v = max(v, _disk(x, y, cx + 6.6, cy - 4.8, 2.1))                     # cabeza (separada)
    v = max(v, _seg(x, y, cx + 8.4, cy - 5.0, cx + 10.0, cy - 4.6, 0.7))  # pico
    v = max(v, _leaf(x, y, cx - 1.5, cy - 5.8, -0.45, -1, 8.0, 2.7))     # ala grande arriba
    v = max(v, _leaf(x, y, cx - 6.0, cy + 1.4, -1, 0.3, 5.0, 2.6))       # cola en abanico
    cut = _disk(x, y, cx + 7.0, cy - 5.0, 0.5)                           # ojo
    for k in (-1, 0, 1):                                                 # puntas de pluma del ala
        cut = max(cut, _seg(x, y, cx - 4 + k * 1.7, cy - 11.5, cx - 3 + k * 1.7, cy - 8.5, 0.45))
    for k in (-1.7, 0, 1.7):                                             # plumas de la cola
        cut = max(cut, _seg(x, y, cx - 9.5, cy + 1.4 + k, cx - 5, cy + 1 + k * 0.5, 0.45))
    v *= (1 - 0.8 * min(1.0, cut))
    v = max(v, _seg(x, y, cx + 9.8, cy - 4.6, cx + 12.0, cy - 3.4, 0.5))  # ramita de olivo
    for ox, oy in [(cx + 11.0, cy - 4.2), (cx + 11.8, cy - 3.5), (cx + 12.2, cy - 2.7)]:
        v = max(v, _disk(x, y, ox, oy, 0.7))                            # hojitas
    return v


def _render_fig(fn, awx, ahx, gamma=0.35):
    """Renderiza un campo fn en dot-space (0..awx*2, 0..ahx*4) → ahx filas ANSI."""
    rows = []
    for rr in range(ahx):
        cells, run, rc = [], "", None
        for cc in range(awx):
            bits, peak = 0, 0.0
            for ix, iy, bit in DOTS:
                xx, yy = cc * 2 + ix, rr * 4 + iy
                vv = fn(xx, yy)
                peak = max(peak, vv)
                if vv ** gamma > (BAYER[yy % 4][xx % 4] + .5) / 16.0:
                    bits |= bit
            ch = " " if bits == 0 else chr(0x2800 + bits)
            col = None if bits == 0 else tone(peak)
            if col == rc:
                run += ch
            else:
                if run:
                    cells.append((run, rc))
                run, rc = ch, col
        if run:
            cells.append((run, rc))
        rows.append("".join(c if k is None else f"{k}{c}{R}" for c, k in cells))
    return rows


WORD = [
    "██╗    ██╗ ██████╗ ██████╗ ██╗  ██╗███████╗██████╗  █████╗  ██████╗███████╗",
    "██║    ██║██╔═══██╗██╔══██╗██║ ██╔╝██╔════╝██╔══██╗██╔══██╗██╔════╝██╔════╝",
    "██║ █╗ ██║██║   ██║██████╔╝█████╔╝ ███████╗██████╔╝███████║██║     █████╗  ",
    "██║███╗██║██║   ██║██╔══██╗██╔═██╗ ╚════██║██╔═══╝ ██╔══██║██║     ██╔══╝  ",
    "╚███╔███╔╝╚██████╔╝██║  ██║██║  ██╗███████║██║     ██║  ██║╚██████╗███████╗",
    " ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝",
]
WCOL = _TH.WCOL if _TH else [B2, B2, B, B, C, C]   # gradiente del wordmark (por tema)

ACOL, ICOL, LW = AW, 58, 13
W = ACOL + ICOL + 4


def _vis(s):
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def _pad(s, w):
    return s + " " * max(0, w - _vis(s))


def _wordmark_lines(ph=0):
    """El bloque del wordmark flanqueado por las URNAS grandes (13×9), wordmark centrado."""
    TW, HH = 15, 9
    torch = _render_torch(ph, TW, HH)
    WW, BOXW = max(len(w) for w in WORD), W + 4
    # Con un wordmark ancho (WORKSPACE = 75 cols) el conjunto urna+palabra+urna
    # ya no cabe en la caja: en ese caso se sueltan las urnas y la palabra va
    # sola, centrada. Jamás desbordar la caja — el banner estático se lee en
    # terminales de 100 columnas.
    flank = (TW + 2 + WW + 2 + TW) <= BOXW
    assembly = (TW + 2 + WW + 2 + TW) if flank else WW
    pad = max(0, (BOXW - assembly) // 2)
    off = (HH - len(WORD)) // 2                       # centrar el wordmark (6) en el bloque (9)
    lines = []
    for i in range(HH):
        lt = _pad(torch[i], TW)
        wi = i - off
        mid = f"{WCOL[wi]}{WORD[wi]}{R}" if 0 <= wi < len(WORD) else " " * WW
        lines.append(" " * pad + (lt + "  " + mid + "  " + lt if flank else mid))
    return lines


def _box_lines(rows):
    """La caja: head + arte (templo) izquierda + panel info derecha + pie."""
    art = render_art()
    out = []
    head = " WORKSPACE · OS de agentes · harness propio del equipo "
    side = (W - len(head)) // 2
    out.append(f"  {B}{_BTL}{_BH*side}{R}{BO}{C}{head}{R}{B}{_BH*(W-side-len(head))}{_BTR}{R}")
    for i in range(AH):
        aseg = _pad(art[i] if i < len(art) else "", ACOL)
        lab, desc = rows[i] if i < len(rows) else ("", "")
        if lab == "##":
            iseg = _pad(f"{BO}{C}{desc}{R}", ICOL)
        elif lab:
            iseg = _pad(f"{WH}{lab.ljust(LW)}{R} {DIM}{desc}{R}", ICOL)
        else:
            iseg = " " * ICOL
        out.append(f"  {B}{_BV}{R} {aseg}  {iseg} {B}{_BV}{R}")
    foot = " escribe el nombre de un agente para entrar directo · workspace para este menú "
    fside = (W - len(foot)) // 2
    out.append(f"  {B}{_BBL}{_BH*fside}{R}{DIM}{foot}{R}{B}{_BH*(W-fside-len(foot))}{_BBR}{R}")
    return out


def banner_str(rows):
    return "\n".join(["\n"] + _wordmark_lines(0) + [""] + _box_lines(rows))


def _ui_anim_on():
    """Setting ui.anim del store unificado (settings.py, raíz de WORKSPACE —
    padre de banner/). Falla-suave → True (anima como siempre). El env
    WORKSPACE_NO_ANIM se chequea aparte y SIEMPRE gana."""
    try:
        import sys as _sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in _sys.path:
            _sys.path.insert(0, root)
        import settings as _settings
        return _settings.enabled("ui.anim", default=True)
    except Exception:
        return True


def animate_intro(tout, rows, frames=8, delay=0.10):
    """Imprime el banner con las ANTORCHAS ANIMADAS (las llamas bailan ~0.7s) y luego
    la caja. Desactivable con WORKSPACE_NO_ANIM=1 (el env SIEMPRE gana) o
    `settings set ui.anim off`. Cae al banner estático ante cualquier error."""
    if os.environ.get("WORKSPACE_NO_ANIM") or not _ui_anim_on():
        tout.write(banner_str(rows) + "\n"); tout.flush(); return
    import time
    try:
        wl = _wordmark_lines(0)
        n = len(wl)
        tout.write("\n" + "\n".join(wl) + "\n"); tout.flush()
        for f in range(1, frames):
            tout.write(f"\033[{n}A")
            for ln in _wordmark_lines(f):
                tout.write("\r\033[K" + ln + "\n")
            tout.flush()
            time.sleep(delay)
        tout.write(f"\033[{n}A")                       # asentar en el frame estático
        for ln in _wordmark_lines(0):
            tout.write("\r\033[K" + ln + "\n")
        tout.write("\n" + "\n".join(_box_lines(rows)) + "\n"); tout.flush()
    except Exception:
        tout.write(banner_str(rows) + "\n"); tout.flush()


# ════════ NUEVO LAYOUT: wordmark limpio + caja de texto + altar de urnas ════════
def wordmark_plain():
    """El wordmark WORKSPACE centrado, sin urnas a los lados."""
    WW = max(len(w) for w in WORD)
    pad = max(0, ((W + 4) - WW) // 2)
    return [" " * pad + f"{WCOL[i]}{WORD[i]}{R}" for i in range(len(WORD))]


def info_box(rows):
    """Caja de info SOLO texto (sin el arte del templo)."""
    out = []
    head = " WORKSPACE · OS de agentes · harness del equipo "
    side = (W - len(head)) // 2
    out.append(f"  {B}{_BTL}{_BH*side}{R}{BO}{C}{head}{R}{B}{_BH*(W-side-len(head))}{_BTR}{R}")
    for lab, desc in rows:
        if lab == "##":
            seg = _pad(f"{BO}{C}{desc}{R}", W)
        elif lab:
            seg = _pad(f"{WH}{lab.ljust(LW)}{R} {DIM}{desc}{R}", W)
        else:
            seg = " " * W
        out.append(f"  {B}{_BV}{R} {seg} {B}{_BV}{R}")
    out.append(f"  {B}{_BBL}{_BH*W}{_BBR}{R}")
    return out


def _vw(s):
    """Ancho visual: glifos CJK/Hangul (East-Asian W/F) cuentan 2 — para centrar
    etiquetas con nombres en coreano (ej. 누리) sin desalinear el altar."""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _center_vis(s, w):
    """Centra `s` en `w` columnas VISUALES (no len()) — Hangul-safe."""
    extra = max(0, w - _vw(s))
    left = extra // 2
    return " " * left + s + " " * (extra - left)


def altar(agents, lit_idx, ph, ig=1.0, keys=None):
    """Fila de urnas (una por agente/dios) sobre un altar. La de índice `lit_idx`
    arde en el FUEGO NORMAL del recinto (el mismo de las antorchas del banner) —
    igual para todos los dioses, para no confundir la llama con la marca del agente;
    el dios seleccionado se distingue por su etiqueta dorada. Las demás urnas apagadas.
    `ig` (0..1) = encendido gradual de la urna seleccionada.
    agents: lista de dicts {display, color, active}.
    `keys` {i: '1'…} (opcional): tecla de SALTO directo del hub — se antepone
    a la etiqueta («1 Zenith»), la tecla vive junto a su opción. Sin `keys`
    la etiqueta queda como siempre (compat total con callers/tests viejos)."""
    # Adaptativo: el altar debe caber en el ancho del recinto (W+4) o la fila se
    # ENVUELVE y el redibujo se descuadra (drift). Con muchos dioses, primero
    # aprieto el gap (3→1); solo si ni con gap=1 cabe, reduzco cell (la urna se
    # recorta un poco — fallback para 7+ agentes). ≤4 dioses → look de siempre (cell15/gap3).
    n = len(agents); avail = W + 4
    cell, gap_n = 15, 3
    while cell * n + gap_n * (n - 1) > avail and gap_n > 1:
        gap_n -= 1
    while cell * n + gap_n * (n - 1) > avail and cell > 9:
        cell -= 1
    gap = " " * gap_n
    urns = []
    for i, ag in enumerate(agents):
        pal = FIRE if i == lit_idx else None       # fuego uniforme, no por color de marca
        urns.append(_render_urn(ph, pal, cell, 9, ig=ig if i == lit_idx else 1.0))
    total = len(agents) * cell + (len(agents) - 1) * len(gap)
    pad = " " * max(0, ((W + 4) - total) // 2)                         # centrar como el wordmark
    lines = [pad + gap.join(u[r] for u in urns) for r in range(9)]
    lines.append(pad + f"{DK}{_GBASE * total}{R}")                     # base / mesa del altar
    labs = []
    for i, ag in enumerate(agents):
        nm = ag["display"]
        k = (keys or {}).get(i, "")
        if k:
            nm = f"{k} {nm}"                       # «1 Zenith» — tecla visible
        if i == lit_idx:
            # ACTIVO/seleccionado: dorado brillante + negrita — inconfundible
            labs.append(f"{C}{BO}{_center_vis(nm, cell)}{R}")
        elif ag.get("active"):
            # INACTIVO (dios real, no seleccionado): gris oscuro — muy separado del activo
            labs.append(f"{_INACTIVE}{_center_vis(nm, cell)}{R}")
        else:
            # PLANEADO (próximamente): aún más oscuro (DK)
            labs.append(f"{DK}{_center_vis(nm + ' ·pronto', cell)}{R}")
    lines.append(pad + gap.join(labs))
    return lines


if __name__ == "__main__":
    print(banner_str([("##", "demo")]))
