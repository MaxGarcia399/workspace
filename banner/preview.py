#!/usr/bin/env python3
"""WORKSPACE · opciones de emblema (estructuras) × paletas — render real en HTML.

ARCHIVO DE DISEÑO (guardado). Genera workspace-opciones.html con las estructuras
candidatas para el harness (Templo A/B/C, esfera armilar) y paletas, para iterar.
ELEGIDO POR AHORA: Templo C (esbelto, 8 columnas) en dorado — ya en producción en
`banner/render.py`. El socio seguirá puliendo el detalle del templo después; las
variantes quedan aquí para retomar. Técnica del skill banner-emblema-braille.
Cero dependencias (stdlib). Correr:  python3 preview.py  (abre el HTML).
"""
import math, os, sys

AW, AH = 44, 25
DW, DH = AW * 2, AH * 4
CX, CY = (DW - 1) / 2, (DH - 1) / 2
SCAN_P, SCAN_G = 6, 1   # igual a producción (render.py) — el scanline define la textura
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
DOTS = [(0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (0, 3, 0x40),
        (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (1, 3, 0x80)]

# ── primitivas (campo de intensidad 0..1) ──
def _disk(x, y, cx, cy, r):
    return max(0.0, 1 - math.hypot(x - cx, y - cy) / r)
def _seg(x, y, x0, y0, x1, y1, w):
    vx, vy = x1 - x0, y1 - y0; L2 = vx * vx + vy * vy or 1.0
    t = max(0.0, min(1.0, ((x - x0) * vx + (y - y0) * vy) / L2))
    return max(0.0, 1 - math.hypot(x - (x0 + t * vx), y - (y0 + t * vy)) / w)
def _ring(x, y, cx, cy, a, b, tw=0.10):
    return max(0.0, 1 - abs(math.hypot((x - cx) / a, (y - cy) / b) - 1.0) / tw)
def _spark(x, y, sx, sy, R, rays=0.0, rl=0.0):
    dx, dy = x - sx, y - sy
    v = max(0.0, 1 - math.hypot(dx, dy) / R)
    if rays:
        for ux, uy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            al = dx * ux + dy * uy
            if al > 0:
                v = max(v, max(0.0, 1 - abs(dx * -uy + dy * ux) / 1.0) * max(0.0, 1 - al / rl) * rays)
    return v
def _gline(x, y, cx, cy, ux, uy, length, w, start=0.0):
    px, py = x - cx, y - cy; al = px * ux + py * uy
    if al < start or al > length:
        return 0.0
    return max(0.0, 1 - abs(px * -uy + py * ux) / w)
def _leaf(x, y, cx, cy, ux, uy, lm, ln):
    px, py = x - cx, y - cy
    return max(0.0, 1 - ((px * ux + py * uy) / lm) ** 2 - ((px * -uy + py * ux) / ln) ** 2)
def _tri(x, y, ax, ay, by, halfw, soft=1.5):
    """Triángulo lleno (ápice arriba), con gradiente interior centro→borde para relieve."""
    if y < ay - soft or y > by + soft:
        return 0.0
    t = max(0.0, min(1.0, (y - ay) / (by - ay) if by != ay else 0.0))
    w = halfw * t
    d = abs(x - ax) - w
    if d > 0:
        return max(0.0, 1 - d / soft)
    edge = 1.0 - min(1.0, abs(x - ax) / (w + 0.001))
    return 0.55 + 0.45 * edge

# ════════════ ESTRUCTURAS ════════════
def f_temple(x, y):
    # ── pedimento (frontón triangular) ──
    v = _tri(x, y, CX, CY - 36, CY - 20, 32, 1.6)
    v = max(v, _ring(x, y, CX, CY - 28, 3.6, 3.2, 0.18))   # óculo del tímpano
    v = max(v, _disk(x, y, CX, CY - 28, 1.2))
    # ── entablamento: cornisa · friso · arquitrabe ──
    v = max(v, _seg(x, y, CX - 35, CY - 18, CX + 35, CY - 18, 1.6))
    v = max(v, _seg(x, y, CX - 32, CY - 14, CX + 32, CY - 14, 2.1))
    v = max(v, _seg(x, y, CX - 33, CY - 10, CX + 33, CY - 10, 1.6))
    # ── columnas (hexástilo) con capiteles y basas ──
    cols = 6
    xs = [CX + (k - (cols - 1) / 2) * 12.0 for k in range(cols)]
    for cx in xs:
        v = max(v, _seg(x, y, cx - 3.6, CY - 8.5, cx + 3.6, CY - 8.5, 1.4))   # capitel
        v = max(v, _seg(x, y, cx, CY - 7, cx, CY + 15, 3.0))                  # fuste
        v = max(v, _seg(x, y, cx - 3.8, CY + 16.5, cx + 3.8, CY + 16.5, 1.5)) # basa
    # ── crepidoma (escalones) ──
    for j, hw in ((19, 36), (22.5, 39), (26, 42)):
        v = max(v, _seg(x, y, CX - hw, CY + j, CX + hw, CY + j, 1.9))
    # ════ espacio negativo (surcos anchos ~0.8) ════
    cut = 0.0
    for cx in xs:                                       # estrías (2 por columna)
        cut = max(cut, _gline(x, y, cx - 1.3, CY + 4, 0, 1, 21, 0.8, -11))
        cut = max(cut, _gline(x, y, cx + 1.3, CY + 4, 0, 1, 21, 0.8, -11))
    trig = xs + [(xs[i] + xs[i + 1]) / 2 for i in range(len(xs) - 1)]
    for tx in trig:                                     # triglifos del friso
        cut = max(cut, _gline(x, y, tx, CY - 14.5, 0, 1, 4.0, 0.8, -2.0))
    cut = max(cut, _seg(x, y, CX - 28, CY - 19, CX, CY - 34, 0.7))   # cornisa inclinada
    cut = max(cut, _seg(x, y, CX + 28, CY - 19, CX, CY - 34, 0.7))
    for j, hw in ((20.7, 37.5), (24.2, 40.5)):          # sombra entre escalones
        cut = max(cut, _seg(x, y, CX - hw, CY + j, CX + hw, CY + j, 0.7))
    v *= (1 - 0.92 * min(1.0, cut))
    # acroterios (esquinas) + estrella en la cima
    v = max(v, _disk(x, y, CX - 32, CY - 19.5, 1.0))
    v = max(v, _disk(x, y, CX + 32, CY - 19.5, 1.0))
    v = max(v, _spark(x, y, CX, CY - 39, 2.0, .9, 5))
    return v

def make_temple(cols, span, col_w, roof_top, roof_base, halfw, shaft_bot):
    """Constructor de templo parametrizable → devuelve un campo fn(x,y)."""
    xs = [CX + (k - (cols - 1) / 2) * (2 * span / (cols - 1)) for k in range(cols)]
    ent_hw = min(span + 5, 43)
    cap_w = col_w + 0.9

    def fn(x, y):
        eb = CY + roof_base
        oy = CY + (roof_top + roof_base) / 2 - 1
        v = _tri(x, y, CX, CY + roof_top, eb, halfw, 1.6)
        v = max(v, _ring(x, y, CX, oy, 3.4, 3.0, 0.18))      # óculo
        v = max(v, _disk(x, y, CX, oy, 1.1))
        v = max(v, _seg(x, y, CX - ent_hw, eb + 2, CX + ent_hw, eb + 2, 1.6))         # cornisa
        v = max(v, _seg(x, y, CX - ent_hw + 2, eb + 6, CX + ent_hw - 2, eb + 6, 2.1))  # friso
        v = max(v, _seg(x, y, CX - ent_hw + 1, eb + 10, CX + ent_hw - 1, eb + 10, 1.6))  # arquitrabe
        cap_y = eb + 12
        sb = CY + shaft_bot
        for cx in xs:
            v = max(v, _seg(x, y, cx - cap_w, cap_y, cx + cap_w, cap_y, 1.4))          # capitel
            v = max(v, _seg(x, y, cx, cap_y + 1.5, cx, sb, col_w))                     # fuste
            v = max(v, _seg(x, y, cx - cap_w, sb + 1.5, cx + cap_w, sb + 1.5, 1.5))    # basa
        s0 = sb + 3.5
        for extra in (0, 3.5, 7):
            hw = min(span + 6 + extra, 43)
            v = max(v, _seg(x, y, CX - hw, s0 + extra, CX + hw, s0 + extra, 1.9))      # escalones
        cut = 0.0
        for cx in xs:
            cut = max(cut, _gline(x, y, cx - 1.3, cap_y + 3, 0, 1, sb - cap_y, 0.8, 0))
            cut = max(cut, _gline(x, y, cx + 1.3, cap_y + 3, 0, 1, sb - cap_y, 0.8, 0))
        trig = xs + [(xs[i] + xs[i + 1]) / 2 for i in range(len(xs) - 1)]
        for tx in trig:
            cut = max(cut, _gline(x, y, tx, eb + 6, 0, 1, 4.0, 0.8, -2.0))             # triglifos
        cut = max(cut, _seg(x, y, CX - halfw * 0.85, eb + 1, CX, CY + roof_top + 2, 0.7))
        cut = max(cut, _seg(x, y, CX + halfw * 0.85, eb + 1, CX, CY + roof_top + 2, 0.7))
        v *= (1 - 0.92 * min(1.0, cut))
        v = max(v, _disk(x, y, CX - halfw * 0.96, eb + 1, 1.0))                        # acroterios
        v = max(v, _disk(x, y, CX + halfw * 0.96, eb + 1, 1.0))
        v = max(v, _spark(x, y, CX, CY + roof_top - 3, 2.0, .9, 5))                    # estrella
        return v
    return fn


def f_armillary(x, y):
    v = _ring(x, y, CX, CY, 27, 35, .10)          # aro exterior
    v = max(v, _ring(x, y, CX, CY, 27, 12, .11))    # ecuador
    v = max(v, _ring(x, y, CX, CY, 19, 30, .10))    # banda interna
    v = max(v, _ring(x, y, CX, CY, 10, 34, .12))    # meridiano
    v = max(v, _seg(x, y, CX, CY - 41, CX, CY + 41, 1.2))   # eje polar
    for i in range(24):                            # graduaciones del aro exterior
        a = i / 24 * 2 * math.pi
        v = max(v, _disk(x, y, CX + 27 * math.cos(a), CY + 35 * math.sin(a), 0.9))
    v = max(v, _disk(x, y, CX, CY - 35, 1.6))       # casquetes polares
    v = max(v, _disk(x, y, CX, CY + 35, 1.6))
    v = max(v, _disk(x, y, CX, CY, 4.0))            # núcleo
    v = max(v, _spark(x, y, CX, CY - 43, 2.2, .9, 6))
    cut = _ring(x, y, CX, CY, 6, 8, .14)            # hueco anular alrededor del núcleo
    v *= (1 - 0.7 * min(1.0, cut))
    return v

def f_mountain(x, y):
    v = _tri(x, y, CX, CY - 32, CY + 26, 34, 1.7)         # pico principal
    v = max(v, _tri(x, y, CX - 19, CY - 12, CY + 26, 17, 1.5))  # pico izq
    v = max(v, _tri(x, y, CX + 21, CY - 6, CY + 26, 15, 1.5))   # pico der
    v = max(v, _seg(x, y, CX - 38, CY + 26, CX + 38, CY + 26, 1.8))  # suelo
    cut = 0.0
    cut = max(cut, _seg(x, y, CX, CY - 30, CX - 10, CY + 24, 0.6))   # aristas
    cut = max(cut, _seg(x, y, CX, CY - 30, CX + 12, CY + 24, 0.6))
    cut = max(cut, _seg(x, y, CX - 6, CY - 6, CX - 20, CY + 22, 0.5))
    cut = max(cut, _seg(x, y, CX + 8, CY, CX + 22, CY + 22, 0.5))
    v *= (1 - 0.85 * min(1.0, cut))
    v = max(v, _spark(x, y, CX + 13, CY - 26, 2.4, .8, 6))   # sol naciente
    return v

def f_zeus(x, y):
    """Zeus entronizado, musculoso, de frente — según referencia del socio:
    corona, barba grande, torso marcado, brazos a los apoyabrazos, tela en el regazo,
    trono con paneles laterales ornamentados. Sin rayo."""
    v = 0.0
    # ── trono: respaldo + paneles laterales ornamentados ──
    for s in (-1, 1):
        v = max(v, _seg(x, y, CX + s * 17, CY - 34, CX + s * 17, CY + 8, 2.0))     # postes traseros
        v = max(v, _disk(x, y, CX + s * 17, CY - 35, 2.2))                         # remates
        v = max(v, _leaf(x, y, CX + s * 22, CY + 9, 0, 1, 12, 3.4))                # panel lateral
    v = max(v, _seg(x, y, CX - 17, CY - 34, CX + 17, CY - 34, 2.0))               # riel superior
    # ── corona de picos ──
    for k in (-2, -1, 0, 1, 2):
        top = CY - 35 - (2.0 if k == 0 else 0.8)
        v = max(v, _seg(x, y, CX + k * 2.1, CY - 31, CX + k * 2.1, top, 0.7))
    # ── cabeza + barba grande ──
    v = max(v, _disk(x, y, CX, CY - 29, 4.0))
    v = max(v, _leaf(x, y, CX, CY - 22, 0, 1, 6.8, 5.2))                          # barba ancha
    # ── hombros anchos + torso musculoso ──
    v = max(v, _leaf(x, y, CX, CY - 14, 1, 0, 15, 4.5))                           # hombros
    v = max(v, _leaf(x, y, CX, CY - 4, 0, 1, 11, 12))                             # torso (pecho→cintura)
    # ── brazos a los apoyabrazos + puños ──
    for s in (-1, 1):
        v = max(v, _seg(x, y, CX + s * 12, CY - 13, CX + s * 20, CY + 5, 3.0))
        v = max(v, _disk(x, y, CX + s * 20, CY + 6, 2.6))
    # ── tela (drapeado) sobre el regazo ──
    v = max(v, _leaf(x, y, CX, CY + 9, 1, 0, 15, 4.0))
    # ── muslos separados ──
    for s in (-1, 1):
        v = max(v, _seg(x, y, CX + s * 5, CY + 6, CX + s * 11, CY + 22, 3.2))
    v = max(v, _seg(x, y, CX - 20, CY + 23, CX + 20, CY + 23, 2.4))               # asiento
    # ════ espacio negativo (músculos, barba, pliegues, grecas) ════
    cut = _gline(x, y, CX, CY - 8, 0, 1, 12, 0.8, -4)                             # línea central torso
    cut = max(cut, _seg(x, y, CX - 8, CY - 9, CX + 8, CY - 9, 0.7))               # línea pectoral
    for ab in (-3, 0, 3):
        cut = max(cut, _seg(x, y, CX - 5, CY + ab, CX + 5, CY + ab, 0.55))        # abdominales
    for s in (-1, 0, 1):
        cut = max(cut, _gline(x, y, CX + s * 2.3, CY - 20, 0, 1, 7, 0.6, 0))      # mechones barba
    for s in (-1, 1):
        cut = max(cut, _seg(x, y, CX + s * 3, CY + 7, CX + s * 13, CY + 11, 0.6)) # pliegues tela
        for yy in (CY + 2, CY + 8, CY + 14):
            cut = max(cut, _seg(x, y, CX + s * 19, yy, CX + s * 25, yy, 0.6))     # grecas del panel
    v *= (1 - 0.85 * min(1.0, cut))
    v = max(v, _spark(x, y, CX, CY - 38, 2.2, .8, 6))                             # aura divina
    return v


def _cypress(x, y, cx, base, top, halfw):
    v = _tri(x, y, cx, top, base, halfw, 1.1)                 # follaje cónico (ciprés)
    v = max(v, _seg(x, y, cx, base, cx, base + 4, 1.0))       # tronco
    return v


def _bird(x, y, bx, by, w=2.3):
    v = _seg(x, y, bx - w, by + 0.9, bx, by - 0.2, 0.55)      # ala izq
    v = max(v, _seg(x, y, bx, by - 0.2, bx + w, by + 0.9, 0.55))  # ala der
    return v


_TEMPLE_SCENE = make_temple(6, 18, 2.4, -31, -19, 22, 12)


def f_palace(x, y):
    """Escena: templo griego (centro) + cipreses flanqueando + aves en el cielo + suelo."""
    v = _TEMPLE_SCENE(x, y)
    for s in (-1, 1):                                         # cipreses
        v = max(v, _cypress(x, y, CX + s * 35, CY + 19, CY - 14, 3.4))
        v = max(v, _cypress(x, y, CX + s * 41, CY + 19, CY - 4, 2.5))
    for bx, by in [(CX - 13, CY - 40), (CX - 6, CY - 43), (CX + 5, CY - 42),
                   (CX + 13, CY - 39), (CX - 1, CY - 37)]:    # aves
        v = max(v, _bird(x, y, bx, by))
    v = max(v, _seg(x, y, CX - 43, CY + 23, CX + 43, CY + 23, 1.3))   # suelo
    v = max(v, _spark(x, y, CX + 31, CY - 33, 2.1, .7, 5))            # sol
    return v


# ════════════ ESTRUCTURAS ÚNICAS (estilo Zenith: 1 sujeto, detalle de grabado) ════════════
def f_workspace(x, y):
    """Monte Olympo: pico mayor + picos laterales, templo en la cima, nubes en la
    base, aristas/nieve talladas (void) y sol naciente. Estilo grabado."""
    v = _tri(x, y, CX, CY - 40, CY + 28, 33, 1.7)            # pico central
    v = max(v, _tri(x, y, CX - 22, CY - 12, CY + 28, 17, 1.5))  # pico izq
    v = max(v, _tri(x, y, CX + 24, CY - 6, CY + 28, 16, 1.5))   # pico der
    tcx, tby = CX, CY - 39                                   # templo en la cima (mini)
    v = max(v, _tri(x, y, tcx, tby - 5, tby, 5, 0.8))
    for k in (-3.2, 0, 3.2):
        v = max(v, _seg(x, y, tcx + k, tby, tcx + k, tby + 5, 0.8))
    v = max(v, _seg(x, y, tcx - 5, tby + 5.5, tcx + 5, tby + 5.5, 0.9))
    for cx0, cy0, rr in [(CX - 19, CY + 13, 7), (CX + 17, CY + 17, 8), (CX, CY + 21, 9),
                         (CX - 31, CY + 21, 6), (CX + 31, CY + 23, 6)]:   # nubes
        v = max(v, _leaf(x, y, cx0, cy0, 1, 0, rr, rr * 0.42))
    v = max(v, _seg(x, y, CX - 40, CY + 30, CX + 40, CY + 30, 1.6))       # suelo
    cut = 0.0
    cut = max(cut, _seg(x, y, CX, CY - 36, CX - 12, CY + 24, 0.7))        # aristas
    cut = max(cut, _seg(x, y, CX, CY - 36, CX + 13, CY + 24, 0.7))
    cut = max(cut, _seg(x, y, CX - 6, CY - 10, CX - 18, CY + 22, 0.55))
    cut = max(cut, _seg(x, y, CX + 7, CY - 6, CX + 19, CY + 22, 0.55))
    for yy in (CY - 18, CY - 6, CY + 6):                                  # estrías de nieve
        cut = max(cut, _gline(x, y, CX, yy, 1, 0, 9, 0.45))
    for cy0 in (CY + 16, CY + 22):                                        # separación de nubes
        cut = max(cut, _seg(x, y, CX - 33, cy0, CX + 33, cy0, 0.5))
    v *= (1 - 0.9 * min(1.0, cut))
    v = max(v, _spark(x, y, CX + 15, CY - 31, 2.6, .9, 8))                # sol naciente
    return v


def f_pantheon(x, y):
    """Panteón: cúpula artesonada (anillos + radiales tallados, óculo) sobre tambor,
    con pórtico al frente (frontón + columnas estriadas) y escalones."""
    domb = CY - 2
    rx, ry = 30, 26
    dxn = (x - CX) / rx
    v = 0.0
    if abs(dxn) <= 1 and y <= domb:
        yc = domb - ry * (max(0.0, 1 - dxn * dxn) ** 0.5)
        if y >= yc:
            v = 0.85
    if abs(x - CX) <= 30 and domb <= y <= domb + 7:           # tambor
        v = max(v, 0.85)
    v = max(v, _tri(x, y, CX, CY + 3, CY + 13, 21, 1.5))      # frontón del pórtico
    for k in range(6):
        cx0 = CX + (k - 2.5) * 7.6
        v = max(v, _seg(x, y, cx0, CY + 14, cx0, CY + 33, 2.0))      # columna
        v = max(v, _seg(x, y, cx0 - 2.4, CY + 13.5, cx0 + 2.4, CY + 13.5, 1.2))  # capitel
    for j, hw in ((34, 25), (37, 28)):
        v = max(v, _seg(x, y, CX - hw, CY + j, CX + hw, CY + j, 1.7))  # escalones
    cut = 0.0
    for rad in (9, 17, 25):                                   # artesonado: anillos
        cut = max(cut, _ring(x, y, CX, domb, rad, rad * 0.86, 0.06))
    for a in range(1, 8):                                     # artesonado: radiales
        th = a / 8 * math.pi
        cut = max(cut, _seg(x, y, CX, domb, CX + 27 * math.cos(th), domb - 23 * math.sin(th), 0.45))
    for k in range(6):                                        # estrías de columnas
        cx0 = CX + (k - 2.5) * 7.6
        cut = max(cut, _gline(x, y, cx0, CY + 17, 0, 1, 15, 0.6, 0))
    v *= (1 - 0.9 * min(1.0, cut))
    v = max(v, _disk(x, y, CX, domb - ry + 1, 1.6))           # óculo
    v = max(v, _spark(x, y, CX, domb - ry - 2, 2.0, .85, 5))
    return v


def f_wreath(x, y):
    """Corona de laurel (dos arcos de hojas con nervadura tallada) + estrella arriba +
    rayo de Zeus al centro + listón abajo. Emblema simétrico."""
    ax, ay, N = 22, 30, 13
    v = 0.0
    for s in (-1, 1):
        for k in range(N):
            t = k / (N - 1)
            th = math.radians(-105 + t * 180)
            ex, ey = CX + s * ax * math.cos(th), CY - ay * math.sin(th)
            tx, ty = -s * math.sin(th), -math.cos(th)
            ln = 4.8 - 1.6 * abs(t - 0.5)
            v = max(v, _leaf(x, y, ex, ey, tx, ty, ln, 1.5))
    bolt = [(CX - 3, CY - 12), (CX + 2, CY - 2), (CX - 2, CY - 1), (CX + 3, CY + 11)]   # rayo
    for i in range(3):
        v = max(v, _seg(x, y, *bolt[i], *bolt[i + 1], 1.3))
    for s in (-1, 1):                                         # listón abajo
        v = max(v, _seg(x, y, CX, CY + ay - 2, CX + s * 9, CY + ay + 6, 1.6))
        v = max(v, _seg(x, y, CX + s * 9, CY + ay + 6, CX + s * 6, CY + ay + 12, 1.4))
    cut = 0.0
    for s in (-1, 1):                                         # nervadura de cada hoja (void)
        for k in range(N):
            t = k / (N - 1)
            th = math.radians(-105 + t * 180)
            ex, ey = CX + s * ax * math.cos(th), CY - ay * math.sin(th)
            tx, ty = -s * math.sin(th), -math.cos(th)
            cut = max(cut, _gline(x, y, ex, ey, tx, ty, 4.0, 0.4, -1))
    v *= (1 - 0.85 * min(1.0, cut))
    v = max(v, _spark(x, y, CX, CY - ay - 2, 2.6, .95, 7))    # estrella superior
    return v


# ════════════ PALETAS (oscuro → claro, 6 capas) ════════════
PALETTES = {
    "Dorado":  ["#4d3500", "#806011", "#b8860b", "#e0a81e", "#ffcb45", "#fff3c4"],
    "Púrpura": ["#3a1052", "#5e2a86", "#8a4fb0", "#a96fd0", "#cf9bee", "#f0d9ff"],
    "Verde":   ["#0f3d1a", "#1d5e2a", "#2e8b40", "#4fae5e", "#76d488", "#c6f5cf"],
    "Aves":    ["#22384f", "#34546f", "#4f7fa5", "#79a9cf", "#a9d2ee", "#eaf6ff"],
    "Suelo":   ["#2a1d08", "#4d3500", "#6b4e10", "#8a6a18", "#a8842a", "#c9a85a"],
    "Sol":     ["#7a3d00", "#b5651d", "#e08a1e", "#ffae33", "#ffd060", "#fff0c0"],
    "Piedra":  ["#3a352c", "#5c5446", "#827763", "#a89a80", "#ccbfa0", "#efe6cc"],
}

# escena por capas: cada elemento con su paleta; gana el de mayor intensidad por punto
def _trees(x, y):
    return max(_cypress(x, y, CX - 35, CY + 19, CY - 14, 3.4), _cypress(x, y, CX - 41, CY + 19, CY - 4, 2.5),
               _cypress(x, y, CX + 35, CY + 19, CY - 14, 3.4), _cypress(x, y, CX + 41, CY + 19, CY - 4, 2.5))
def _birds(x, y):
    return max(_bird(x, y, CX - 13, CY - 40), _bird(x, y, CX - 6, CY - 43), _bird(x, y, CX + 5, CY - 42),
               _bird(x, y, CX + 13, CY - 39), _bird(x, y, CX - 1, CY - 37))
def _ground(x, y):
    return _seg(x, y, CX - 43, CY + 23, CX + 43, CY + 23, 1.3)
def _sun(x, y):
    return _spark(x, y, CX + 31, CY - 33, 2.1, .7, 5)

SCENE = [(_TEMPLE_SCENE, "Dorado"), (_trees, "Verde"), (_birds, "Aves"),
         (_ground, "Suelo"), (_sun, "Sol")]

# ════════════ ESCENA AMPLIA — "El Templo de los Dioses" (panorámica) ════════════
AWW, AHH = 150, 30         # ciudad panorámica (dot-space 300×120) — extendida a lo ancho
GY = 100                   # línea de suelo
GAMMA = 0.55               # contraste de huecos (a esta escala mini, un pelín más sólido lee mejor)


def w_temple(x, y, cx, by, w, h):
    hw = w / 2.0; rt = by - h; eb = by - h * 0.46
    v = _tri(x, y, cx, rt, eb, hw, 1.7)                                   # frontón
    v = max(v, _ring(x, y, cx, (rt + eb) / 2, hw * 0.14, hw * 0.14, 0.2))  # óculo
    v = max(v, _seg(x, y, cx - hw, eb + 1.5, cx + hw, eb + 1.5, 1.7))      # cornisa
    v = max(v, _seg(x, y, cx - hw * 0.95, eb + 5, cx + hw * 0.95, eb + 5, 1.5))  # friso
    cap = eb + 8.5; ncol = 8; cs = hw * 0.84
    xs = [cx - cs + (2 * cs / (ncol - 1)) * k for k in range(ncol)]
    for ccx in xs:
        v = max(v, _seg(x, y, ccx - 2.1, cap, ccx + 2.1, cap, 1.2))        # capitel
        v = max(v, _seg(x, y, ccx, cap + 1.5, ccx, by - 4, 2.1))           # fuste
        v = max(v, _seg(x, y, ccx - 2.3, by - 3, ccx + 2.3, by - 3, 1.2))  # basa
    for ex in (0, 3, 6):
        v = max(v, _seg(x, y, cx - hw - ex, by - 1 + ex, cx + hw + ex, by - 1 + ex, 1.6))  # escalones
    cut = 0.0
    for ccx in xs:
        cut = max(cut, _gline(x, y, ccx - 1.0, cap + 4, 0, 1, by - cap - 6, 0.8, 0))
        cut = max(cut, _gline(x, y, ccx + 1.0, cap + 4, 0, 1, by - cap - 6, 0.8, 0))
    trig = xs + [(xs[i] + xs[i + 1]) / 2 for i in range(len(xs) - 1)]
    for tx in trig:
        cut = max(cut, _gline(x, y, tx, eb + 5, 0, 1, 4, 0.8, -2))
    v *= (1 - 0.9 * min(1.0, cut))
    v = max(v, _spark(x, y, cx, rt - 2, 1.8, .8, 4))
    return v


def _arch(x, y, ax, topy, boty, hw):
    """Vano de arco: rectángulo + medio círculo arriba (para tallar como hueco)."""
    if abs(x - ax) <= hw and topy <= y <= boty:
        return 1.0
    if y < topy and (x - ax) ** 2 + (y - topy) ** 2 <= hw * hw:
        return 1.0
    return 0.0


def w_colosseum(x, y, cx, by, w, h):
    """Coliseo romano INTACTO en perspectiva: tambor elíptico (la forma ovalada es lo
    que lo hace legible) con 2 arcadas de arcos curvos + ático de ventanas, cornisas
    entre niveles y labio ovalado arriba. Sólido y simétrico — no se cae.
    cx=centro, by=línea de suelo, w=ancho, h=altura."""
    a = w / 2.0
    dx = (x - cx) / a
    if abs(dx) > 1.03:
        return 0.0
    arc = 1 - dx * dx
    if arc < 0:
        return 0.0
    sq = arc ** 0.5
    br = h * 0.17                       # squash vertical del óvalo (perspectiva)
    topc = by - h + br                  # centro del óvalo superior
    botc = by - br                      # centro del óvalo inferior (al ras del suelo)
    yt_front = topc + br * sq           # labio frontal superior (baja hacia el centro)
    yt_back = topc - br * sq            # labio trasero superior (la boca ovalada)
    yb_front = botc + br * sq           # base frontal
    bH = botc - topc                    # altura de la pared frontal (constante)
    # ── pared frontal sólida (banda curva) ──
    v = 0.80 if yt_front <= y <= yb_front else 0.0
    # ── labio del óvalo: borde frontal (fuerte) + trasero (tenue, da la boca) ──
    if abs(y - yt_front) <= 0.7:
        v = max(v, 0.97)
    if abs(y - yt_back) <= 0.7 and abs(dx) < 0.985:
        v = max(v, 0.5)
    # ── arcos por nivel, siguiendo la curva del frente ──
    cut = 0.0
    naf = 13
    pitch = w / naf
    aw = pitch * 0.30
    for k in range(naf):
        ax = cx - a + pitch * (k + 0.5)
        ddx = (ax - cx) / a
        ytf = topc + br * (max(0.0, 1 - ddx * ddx) ** 0.5)
        for f0, f1 in ((0.16, 0.40), (0.46, 0.70)):        # 2 arcadas de arcos
            cut = max(cut, _arch(x, y, ax, ytf + bH * f0, ytf + bH * f1, aw))
        if abs(x - ax) <= aw * 0.5 and ytf + bH * 0.78 <= y <= ytf + bH * 0.90:
            cut = max(cut, 1.0)                             # ático: ventana rectangular
    v *= (1 - min(1.0, cut))
    # ── cornisas entre niveles + base (siguen la curva) ──
    ytf = topc + br * sq
    for f in (0.44, 0.74, 0.96):
        if abs(y - (ytf + bH * f)) <= 0.55:
            v = max(v, 0.95)
    return v


# ── piezas extra de la ciudad antigua (para la panorámica) ──
def b_tholos(x, y, cx, by, w, h):
    """Templo circular (tholos): cúpula sobre tambor de columnas + entablamento."""
    hw = w / 2.0
    dome_b = by - h * 0.55
    rx, ry = hw * 0.95, h * 0.40
    dx = (x - cx) / rx
    v = 0.0
    if abs(dx) <= 1 and y <= dome_b:
        yc = dome_b - ry * (max(0.0, 1 - dx * dx) ** 0.5)
        if y >= yc:
            v = 0.85
    v = max(v, _spark(x, y, cx, by - h - 1, 1.5, .8, 4))                  # remate
    v = max(v, _seg(x, y, cx - hw, dome_b + 0.5, cx + hw, dome_b + 0.5, 1.3))  # arquitrabe
    ncol, cut = 6, 0.0
    for k in range(ncol):
        ccx = cx - hw * 0.82 + (1.64 * hw / (ncol - 1)) * k
        v = max(v, _seg(x, y, ccx, dome_b + 1, ccx, by - 3, 1.3))
        cut = max(cut, _gline(x, y, ccx, dome_b + 2, 0, 1, by - dome_b - 5, 0.6, 0))
    for ex in (0, 2.5):
        v = max(v, _seg(x, y, cx - hw - ex, by - 1 + ex, cx + hw + ex, by - 1 + ex, 1.4))
    return v * (1 - 0.8 * min(1.0, cut))


def b_arch(x, y, cx, by, w, h):
    """Arco triunfal (estilo Constantino): bloque con arco central + dos laterales + ático."""
    hw = w / 2.0
    v = 0.85 if (abs(x - cx) <= hw and by - h <= y <= by) else 0.0
    cut = _arch(x, y, cx, by - h * 0.58, by - 2, hw * 0.34)               # arco central
    for s in (-1, 1):
        cut = max(cut, _arch(x, y, cx + s * hw * 0.68, by - h * 0.30, by - 2, hw * 0.12))  # laterales
    v *= (1 - min(1.0, cut))
    if abs(x - cx) <= hw:
        for f in (0.70, 0.88, 0.99):                                      # cornisas del ático + base
            if abs(y - (by - h * f)) <= 0.55:
                v = max(v, 0.95)
    return v


def b_obelisk(x, y, cx, by, h):
    """Obelisco: fuste vertical estrecho + piramidión + pedestal."""
    v = 0.85 if (abs(x - cx) <= 1.8 and by - h * 0.9 <= y <= by) else 0.0
    v = max(v, _tri(x, y, cx, by - h, by - h * 0.9, 2.0, 0.8))            # piramidión
    v = max(v, _seg(x, y, cx - 3, by - 1, cx + 3, by - 1, 1.2))           # pedestal
    return v


def b_columns(x, y, cx, by, n, h, gap, broken=()):
    """Columnata en ruinas: n columnas exentas; las de `broken` salen partidas (más cortas)."""
    v, span = 0.0, (n - 1) / 2.0 * gap
    for k in range(n):
        ccx = cx + (k - (n - 1) / 2.0) * gap
        hk = h * (0.5 if k in broken else 1.0)
        v = max(v, _seg(x, y, ccx, by - hk, ccx, by - 2, 1.5))           # fuste
        if k not in broken:
            v = max(v, _seg(x, y, ccx - 1.8, by - hk, ccx + 1.8, by - hk, 1.1))  # capitel
    v = max(v, _seg(x, y, cx - span - 2, by - 1, cx + span + 2, by - 1, 1.3))    # estilóbato
    cut = 0.0
    for k in range(n):
        ccx = cx + (k - (n - 1) / 2.0) * gap
        hk = h * (0.5 if k in broken else 1.0)
        cut = max(cut, _gline(x, y, ccx, by - hk + 2, 0, 1, hk - 4, 0.6, 0))
    return v * (1 - 0.78 * min(1.0, cut))


def b_hill(x, y, cx, by, w, h):
    """Colina lejana: silueta baja y TENUE (valor bajo = recede al fondo)."""
    hw = w / 2.0
    dx = (x - cx) / hw
    if abs(dx) > 1:
        return 0.0
    top = by - h * (max(0.0, 1 - dx * dx) ** 0.7)
    return 0.28 if top <= y <= by else 0.0


# Templo EXACTO de producción (render.py): Templo C, sin modificar (solo trasladado/escalado).
TEMPLE_C = make_temple(8, 32, 2.3, -40, -22, 34, 17)
T_S, T_CX, T_CY = 0.33, 122, 91   # templo héroe pequeño (vista lejana), base en el suelo
def _wt(x, y):      return TEMPLE_C((x - T_CX) / T_S + CX, (y - T_CY) / T_S + CY)

# ── ciudad LEJANA: mini estructuras, ESPACIADAS PAREJO en todo el ancho, alturas variadas ──
def _city_dorado(x, y):    # templos griegos (héroe + secundario) + tholos
    return max(_wt(x, y),
               w_temple(x, y, 78, GY, 20, 20),
               b_tholos(x, y, 30, GY, 18, 22))
def _city_piedra(x, y):    # piedra: obelisco, arco, ruinas, Coliseo (todo mini)
    return max(b_obelisk(x, y, 162, GY, 32),
               b_arch(x, y, 198, GY, 16, 18),
               b_columns(x, y, 234, GY, 4, 14, 4.0, (3,)),
               w_colosseum(x, y, 274, GY, 32, 22))
def _city_hills(x, y):     # horizonte lejano, muy tenue
    return max(b_hill(x, y, 80, GY, 180, 8),
               b_hill(x, y, 230, GY, 170, 9))
def _city_trees(x, y):     # cipreses pequeños como acentos en los huecos
    return max(_cypress(x, y, cx, GY, GY - h, hw) for cx, h, hw in
               [(12, 16, 3.4), (54, 15, 3.2), (108, 15, 3.2),
                (182, 14, 3.0), (218, 15, 3.2), (252, 16, 3.3)])
def _city_birds(x, y):     # un par de bandadas altas y pequeñas
    return max(_bird(x, y, bx, byy, w) for bx, byy, w in
               [(112, 18, 2.4), (120, 14, 2.4), (128, 19, 2.1),
                (202, 16, 2.4), (210, 12, 2.4), (218, 17, 2.1)])
def _wground(x, y): return 0.42 * _seg(x, y, 8, GY, 292, GY, 1.2)   # suelo tenue, no une todo
def _wsun(x, y):    return _spark(x, y, 256, 17, 4.2, .7, 6)

WIDE_SCENE = [(_city_hills, "Suelo"), (_city_piedra, "Piedra"), (_city_dorado, "Dorado"),
              (_city_trees, "Verde"), (_city_birds, "Aves"), (_wground, "Suelo"), (_wsun, "Sol")]

def tone(v, pal):
    DK, DIM, B2, B, C, WH = pal
    return (WH if v >= .80 else C if v >= .60 else B if v >= .44
            else B2 if v >= .30 else DIM if v >= .17 else DK)

def render_html_layered(layers):
    """Escena multicolor: por cada punto gana la capa de mayor intensidad, con SU paleta."""
    rows = []
    for rr in range(AH):
        cells, run, rc = [], "", None
        for cc in range(AW):
            bits, peak, pal = 0, 0.0, None
            for ix, iy, bit in DOTS:
                xx, yy = cc * 2 + ix, rr * 4 + iy
                best, bpal = 0.0, None
                for fn, pname in layers:
                    val = fn(xx, yy)
                    if val > best:
                        best, bpal = val, PALETTES[pname]
                vv = best
                if yy % SCAN_P >= SCAN_P - SCAN_G:
                    vv = 0.0
                if vv > peak:
                    peak, pal = vv, bpal
                if vv ** 0.30 > (BAYER[yy % 4][xx % 4] + .5) / 16.0:
                    bits |= bit
            ch = chr(0x2800 + bits) if bits else " "
            col = tone(peak, pal or PALETTES["Dorado"]) if bits else None
            if col == rc:
                run += ch
            else:
                if run:
                    cells.append((run, rc))
                run, rc = ch, col
        if run:
            cells.append((run, rc))
        rows.append("".join(c if k is None else f'<span style="color:{k}">{c}</span>'
                            for c, k in cells))
    return "\n".join(rows)


def render_layers(layers, aw, ah):
    """Como render_html_layered pero con dimensiones (aw×ah) parametrizables (escena ancha)."""
    rows = []
    for rr in range(ah):
        cells, run, rc = [], "", None
        for cc in range(aw):
            bits, peak, pal = 0, 0.0, None
            for ix, iy, bit in DOTS:
                xx, yy = cc * 2 + ix, rr * 4 + iy
                best, bpal = 0.0, None
                for fn, pname in layers:
                    val = fn(xx, yy)
                    if val > best:
                        best, bpal = val, PALETTES[pname]
                vv = best
                if yy % SCAN_P >= SCAN_P - SCAN_G:
                    vv = 0.0
                if vv > peak:
                    peak, pal = vv, bpal
                if vv ** GAMMA > (BAYER[yy % 4][xx % 4] + .5) / 16.0:
                    bits |= bit
            ch = chr(0x2800 + bits) if bits else " "
            col = tone(peak, pal or PALETTES["Dorado"]) if bits else None
            if col == rc:
                run += ch
            else:
                if run:
                    cells.append((run, rc))
                run, rc = ch, col
        if run:
            cells.append((run, rc))
        rows.append("".join(c if k is None else f'<span style="color:{k}">{c}</span>'
                            for c, k in cells))
    return "\n".join(rows)


def render_html(fn, pal):
    rows = []
    for rr in range(AH):
        cells, run, rc = [], "", None
        for cc in range(AW):
            bits, peak = 0, 0.0
            for ix, iy, bit in DOTS:
                xx, yy = cc * 2 + ix, rr * 4 + iy
                vv = fn(xx, yy)
                if yy % SCAN_P >= SCAN_P - SCAN_G:
                    vv = 0.0
                peak = max(peak, vv)
                if vv ** 0.30 > (BAYER[yy % 4][xx % 4] + .5) / 16.0:
                    bits |= bit
            ch = chr(0x2800 + bits); col = None if bits == 0 else tone(peak, pal)
            if col == rc:
                run += ch
            else:
                if run:
                    cells.append((run, rc))
                run, rc = ch, col
        if run:
            cells.append((run, rc))
        rows.append("".join(c if k is None else f'<span style="color:{k}">{c}</span>'
                            for c, k in cells))
    return "\n".join(rows)

# ── render de UNA estructura, estilo grabado de Zenith (ventana de umbral crisp) ──
SAW, SAH, SSCALE = 42, 24, 0.80

def render_struct(fn, pal):
    DWr, DHr = SAW * 2, SAH * 4
    CXr, CYr = (DWr - 1) / 2, (DHr - 1) / 2
    rows = []
    for rr in range(SAH):
        cells, run, rc = [], "", None
        for cc in range(SAW):
            bits, peak = 0, 0.0
            for ix, iy, bit in DOTS:
                xx, yy = cc * 2 + ix, rr * 4 + iy
                ddx = (xx - CXr) / SSCALE + CX
                ddy = (yy - CYr) / SSCALE + CY
                vv = fn(ddx, ddy)
                if yy % SCAN_P >= SCAN_P - SCAN_G:
                    vv = 0.0
                peak = max(peak, vv)
                vf = (vv - 0.10) / (0.26 - 0.10)
                vf = 0.0 if vf < 0 else 1.0 if vf > 1 else vf
                if vf > (BAYER[yy % 4][xx % 4] + .5) / 16.0:
                    bits |= bit
            ch = chr(0x2800 + bits) if bits else " "
            col = tone(peak, pal) if bits else None
            if col == rc:
                run += ch
            else:
                if run:
                    cells.append((run, rc))
                run, rc = ch, col
        if run:
            cells.append((run, rc))
        rows.append("".join(c if k is None else f'<span style="color:{k}">{c}</span>'
                            for c, k in cells))
    return "\n".join(rows)


STRUCTURES = [
    (TEMPLE_C,   "Templo de los dioses (Partenón)", "el de producción, como héroe único"),
    (f_workspace,  "Monte Olympo",                    "pico + templo en la cima + nubes + sol — lo más literal al nombre"),
    (f_pantheon, "Panteón (rotonda)",               "cúpula artesonada + pórtico con columnas estriadas"),
    (f_wreath,   "Corona de laurel + rayo de Zeus", "emblema simétrico, victoria olímpica"),
]


def build():
    pal = PALETTES["Dorado"]
    cards = []
    for i, (fn, name, desc) in enumerate(STRUCTURES, 1):
        cards.append(f'''  <div class="card">
    <div class="num">{i}</div>
    <pre>{render_struct(fn, pal)}</pre>
    <div class="name">{name}</div>
    <div class="desc">{desc}</div>
  </div>''')
    html = f'''<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>WORKSPACE · estructuras únicas (estilo grabado)</title>
<style>
  body{{background:#06060a;color:#c9b481;font-family:-apple-system,Segoe UI,sans-serif;margin:0;padding:32px}}
  h1{{color:#ffcb45;font-weight:600;letter-spacing:.5px;font-size:20px;margin:0 0 4px}}
  .sub{{color:#9a8654;font-size:13px;margin:0 0 28px;max-width:820px}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
  .card{{background:#0c0a06;border:1px solid #2a2310;border-radius:12px;padding:18px;position:relative}}
  .num{{position:absolute;top:12px;right:14px;color:#5a4a1f;font-size:22px;font-weight:700}}
  pre{{font-family:"DejaVu Sans Mono","Menlo","Cascadia Mono",monospace;font-size:13px;line-height:1.05;letter-spacing:0;margin:0 0 12px;white-space:pre;overflow-x:auto;background:#040308;border-radius:8px;padding:18px}}
  .name{{color:#fff3c4;font-size:15px;font-weight:600}}
  .desc{{color:#9a8654;font-size:12.5px;margin-top:2px}}
</style></head><body>
  <h1>WORKSPACE · estructuras únicas — estilo grabado (inspirado en Zenith)</h1>
  <p class="sub">Un solo sujeto imponente y centrado, con detalle tallado (no escena dispersa).
  Esto es el harness = estructura, no criatura. Dorado. Dime qué número te late y la pulimos a fondo.</p>
  <div class="grid">
{chr(10).join(cards)}
  </div>
</body></html>'''
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace-opciones.html")
    with open(out, "w") as f:
        f.write(html)
    print("escrito:", out, "·", len(STRUCTURES), "estructuras")
    return out

if __name__ == "__main__":
    build()
