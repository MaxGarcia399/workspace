#!/usr/bin/env python3
r"""WORKSPACE · hub_monitos_m1 — los monitos M-1 «Rejilla afinada» (Monitos terminal R1) y sus ocho animaciones. SOLO
PARA PROBAR: vive en la rama zenith/hub-h1 y nunca entra a main.

Los sprites y las secuencias son los del diseñador (deliverables/workspace-marca/_gen_monitos_terminal_r1.py), tal
cual:
  · chico 6×6 y riel 8×8, dibujados pixel a pixel (cada forma se reconoce: el cuadrito cuadrado, el gatito con
    orejas, el fantasma con dientes, la nube con sus chichones), con ojos de 1×2;
  · grande 18×16 (la cabeza del menú de sesiones), del trazo de la página con ojos de pastilla de 2×4;
  · caras: normal, cerrado (rayita abajo), feliz (arriba), grande (un pixel más) y apretado (> <); mirar corre los
    ojos un pixel; dormido apaga el color un 42 %.

Las animaciones, en el reloj de 16 cuadros por segundo del hub (CUADRO_S); cada una avanza en múltiplos de él:
  Libre 8 cps (la micro-vida) · Brinco 16 (al elegirlo) · Piensa 4 · Pregunta 4 · Festeja 12 (al terminar, una vez)
  · Duerme 2 · Problema 12 · Gelatina 16 (solo al picarlo con el mouse).
Las reglas del diseñador:
  · en reposo cada uno a su ritmo: un parpadeo cada 3-6 s (a veces doble), a veces mira a un lado, un saltito cada
    ~8 s; nunca dos parpadeos a la vez (en todo el hub);
  · con «menos movimiento» (WORKSPACE_MENOS_MOVIMIENTO=1, o el del sistema en la Mac) el cuerpo se queda quieto y
    solo cambian los signos (•••, ?, ✓, z, !).
Cada cuadro de un monito toca a lo más 5 filas (~745 B en el pintor por tramos: lo midió el diseñador; las pruebas lo
miden aquí). Stdlib."""
import os
import subprocess
import sys
import zlib

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

#: El reloj del hub (16 cuadros por segundo) y la duración de los pasos de las secuencias (ms).
CUADRO_MS = 62.5
Q16, Q12, Q8, Q4, Q2 = 62, 83, 125, 250, 500
TINTA = "#231b2c"


# ── los sprites (los del diseñador, tal cual) ─────────────────────────────────
RIEL = {
    "bolita": """
..####..
.######.
########
########
########
########
.######.
..####..""",
    "pico": """
...##...
...##...
..####..
.######.
########
########
########
.######.""",
    "cuadrito": """
.######.
########
########
########
########
########
########
.######.""",
    "gatito": """
#......#
##....##
########
########
########
########
.######.
..####..""",
    "fantasma": """
..####..
.######.
########
########
########
########
########
##.##.##""",
    "nube": """
........
........
....##..
.##.###.
########
########
########
.######.""",
}
RIEL_OJOS = {"bolita": 3, "pico": 4, "cuadrito": 3, "gatito": 3, "fantasma": 3, "nube": 4}
CHICO = {
    "bolita": """
.####.
######
######
######
######
.####.""",
    "pico": """
..##..
.####.
######
######
######
.####.""",
    "cuadrito": """
######
######
######
######
######
######""",
    "gatito": """
#....#
##..##
######
######
######
.####.""",
    "fantasma": """
.####.
######
######
######
######
#.##.#""",
    "nube": """
......
...##.
.#####
######
######
.####.""",
}
CHICO_OJOS = {"bolita": 2, "pico": 3, "cuadrito": 2, "gatito": 3, "fantasma": 2, "nube": 3}
FORMAS = ("bolita", "pico", "cuadrito", "gatito", "fantasma", "nube")
#: Los tamaños: pixeles de alto (S) de cada uno; el ancho del grande es S + 2.
TAM = {"chico": 6, "riel": 8, "grande": 16}


def _de_texto(txt):
    return [[ch == "#" for ch in fila] for fila in txt.strip("\n").split("\n")]


_POL = {}


def _poligonos(f):
    if f not in _POL:
        import hub_paleta as P
        _POL[f] = P._poligonos(P.PATH[f])
    return _POL[f]


def _dentro(f, x, y):
    c = False
    for pol in _poligonos(f):
        n = len(pol)
        for i in range(n):
            x0, y0 = pol[i]
            x1, y1 = pol[(i + 1) % n]
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                c = not c
    return c


def _rast(f, S, W):
    """El trazo de la página en una rejilla de S filas × W columnas (4×4 muestras por pixel; lleno si cubre ½)."""
    k = S / 88.0
    tx, ty = W / 2.0 - 50 * k, S - 94 * k
    N = 4
    out = []
    for j in range(S):
        fila = []
        for i in range(W):
            n = 0
            for a in range(N):
                for b in range(N):
                    if _dentro(f, (i + (a + 0.5) / N - tx) / k, (j + (b + 0.5) / N - ty) / k):
                        n += 1
            fila.append(n / float(N * N) >= 0.5)
        out.append(fila)
    return out


def _sin_punta(m, f):
    if f not in ("bolita", "cuadrito", "fantasma"):
        return m
    m = [list(r) for r in m]
    filas = [j for j, r in enumerate(m) if any(r)]
    if len(filas) > 1:
        j = filas[0]
        if sum(m[j]) <= 0.35 * sum(m[j + 1]):
            m[j] = [False] * len(m[j])
    return m


def _sin_bulto(m, f):
    if f != "gatito":
        return m
    m = [list(r) for r in m]
    for j in range(min(4, len(m))):
        runs, i, W = [], 0, len(m[j])
        while i < W:
            if m[j][i]:
                k = i
                while k < W and m[j][k]:
                    k += 1
                runs.append((i, k))
                i = k
            else:
                i += 1
        if len(runs) >= 3:
            for a, b in runs[1:-1]:
                for i in range(a, b):
                    m[j][i] = False
    return m


def _dientes(m):
    m = [list(r) for r in m]
    j = len(m) - 1
    while j > 2 and not any(m[j]):
        j -= 1
    xs = [i for i, v in enumerate(m[j - 2]) if v]
    if not xs:
        return m
    a, b = xs[0], xs[-1]
    m[j - 1] = [a <= i <= b for i in range(len(m[j - 1]))]
    m[j] = [a <= i <= b and min(i - a, b - i) % 3 < 2 for i in range(len(m[j]))]
    return m


def _ojos_trazo(f, S, W, ew, eh):
    k = S / 88.0
    tx, ty = W / 2.0 - 50 * k, S - 94 * k
    oy = 60 if f in ("pico", "nube") else 52
    top = int(round(ty + k * (oy - 1.5) - eh / 2.0))
    cxs = [tx + k * xc for xc in (40.6, 61.9)]
    mid = W / 2.0
    d = round(((mid - cxs[0]) + (cxs[1] - mid)) / 2.0 - ew / 2.0)
    return top, [int(mid - d - ew), int(mid + d)], ew, eh


_SPR = {}


def sprite(f, tam):
    """(máscara, ojos) de la forma `f` en «chico», «riel» o «grande». ojos = (fila, [x izq, x der], ancho, alto)."""
    f = f if f in FORMAS else "bolita"
    clave = (f, tam)
    if clave not in _SPR:
        if tam in ("riel", "chico"):
            m = _de_texto((RIEL if tam == "riel" else CHICO)[f])
            W = len(m[0])
            _SPR[clave] = (m, ((RIEL_OJOS if tam == "riel" else CHICO_OJOS)[f], [W // 2 - 2, W // 2 + 1], 1, 2))
        else:
            S = TAM["grande"]
            W = S + 2
            m = _sin_bulto(_sin_punta(_rast(f, S, W), f), f)
            if f == "fantasma":
                m = _dientes(m)
            _SPR[clave] = (m, _ojos_trazo(f, S, W, 2, 4))
    return _SPR[clave]


def tam_de(px):
    """El tamaño por el ancho que piden las pantallas (el `tam` de hub_monitos): 16 → grande, 8 → riel, 6 → chico."""
    return "grande" if px >= 12 else ("riel" if px >= 8 else "chico")


def medidas(px):
    m, _o = sprite("bolita", tam_de(px))
    return len(m[0]), (len(m) + 1) // 2


# ── dibujar un sprite con su gesto (medios bloques) ───────────────────────────
def _escalar(m, dw, dh):
    H, Wd = len(m), len(m[0])
    H2, W2 = max(1, H + dh), max(1, Wd + dw)
    out = []
    for j in range(H2):
        sj = min(H - 1, int((j + 0.5) * H / H2))
        out.append([m[sj][min(Wd - 1, int((i + 0.5) * Wd / W2))] for i in range(W2)])
    return out


def pixeles(m, ojos, col, gesto, ojo_col=TINTA):
    """La rejilla de colores (None = transparente) con la cara según el gesto."""
    g = gesto or {}
    dw, dh = g.get("dw", 0), g.get("dh", 0)
    H, Wd = len(m), len(m[0])
    mm = _escalar(m, dw, dh) if (dw or dh) else m
    H2, W2 = len(mm), len(mm[0])
    px = [[col if v else None for v in fila] for fila in mm]
    fila, xs, ew, eh = ojos
    fila2 = fila + (H2 - H)
    ox = W2 / 2.0
    xs2 = [int(round(ox + (x + ew / 2.0 - Wd / 2.0) * (W2 / float(Wd)) - ew / 2.0)) for x in xs]
    modo, mira = g.get("ojos", "normal"), g.get("mira", 0)
    puntos = []
    for k, x0 in enumerate(xs2):
        x0 += mira
        lado = -1 if k == 0 else 1
        if modo == "normal":
            puntos += [(x0 + a, fila2 + b) for a in range(ew) for b in range(eh)]
        elif modo == "grande":
            puntos += [(x0 + a, fila2 - 1 + b) for a in range(ew) for b in range(eh + 1)]
        elif modo == "cerrado":
            y = fila2 + eh - 1
            xx = range(x0 - 1, x0 + ew) if lado < 0 else range(x0, x0 + ew + 1)
            puntos += [(a, y) for a in xx]
        elif modo == "feliz":
            xa = x0 + lado * (1 if ew <= 2 else 0) * max(1, ew // 2 if ew > 1 else 1)
            puntos += [(xa + a, fila2) for a in range(ew)]
            puntos += [(xa - 1, fila2 + 1), (xa + ew, fila2 + 1)]
        elif modo == "apretado":
            if eh >= 3:
                xa = x0 if lado < 0 else x0 + ew - 1
                xb = xa + (1 if lado < 0 else -1)
                puntos += [(xa, fila2), (xb, fila2 + 1), (xa, fila2 + 2)]
            else:
                puntos += [(x0 + a, fila2 + eh - 1) for a in range(ew)]
    for x, y in puntos:
        if 0 <= y < H2 and 0 <= x < W2 and px[y][x]:
            px[y][x] = ojo_col
    return px


def pintar(T, x, py0, px, dx=0):
    """Pone la rejilla en la terminal (medios bloques): su columna 0 en la celda x, su fila 0 en el pixel py0 (2 por
    fila); el fondo de cada celda es el que ya tenía. Cada celda queda marcada como pixel (Celda.px)."""
    import hub_bloque as B
    H, Wd = len(px), len(px[0])
    for cy in range(py0 // 2, (py0 + H + 1) // 2 + 1):
        for cx in range(x - 1, x + Wd + abs(dx) + 2):
            if not (0 <= cx < T.w and 0 <= cy < T.h):
                continue
            k = T.at(cx, cy)
            gx = cx - x - dx
            t = px[2 * cy - py0][gx] if (0 <= 2 * cy - py0 < H and 0 <= gx < Wd) else None
            bo = px[2 * cy + 1 - py0][gx] if (0 <= 2 * cy + 1 - py0 < H and 0 <= gx < Wd) else None
            if not (t or bo):
                continue
            fondo = k.bg or B.BG
            k.b = False
            if hasattr(k, "px"):
                k.px = True                            # un pixel del monito (Terminal.app guarda su color)
            if t and bo:
                if t == bo:
                    k.ch, k.fg = "█", t
                else:
                    k.ch, k.fg, k.bg = "▀", t, bo
            elif t:
                k.ch, k.fg, k.bg = "▀", t, fondo
            else:
                k.ch, k.fg, k.bg = "▄", bo, fondo


def ojo_col(c):
    return "#ffffff" if c in ("#3b82f6", "#8b5cf6") else TINTA


def dormido(c):
    import hub_paleta as P
    return P.mix(c, P.GRIS_DORMIDO, 0.42)


def monito(T, f, col, tam, x, y, gesto=None, st="libre"):
    """El monito de pie sobre la fila y + alto, con su columna 0 en x. → (ancho, alto) en celdas."""
    g = dict(gesto or {})
    c = dormido(col) if st == "duerme" else col
    m, o = sprite(f, tam)
    px = pixeles(m, o, c, g, g.get("ojo_col") or ojo_col(col))
    hh = (len(m) + 1) // 2
    py0 = 2 * (y + hh) - len(px) - g.get("lift", 0)
    extra = len(px[0]) - len(m[0])
    pintar(T, x, py0, px, g.get("dx", 0) - extra // 2)
    return len(m[0]), hh


def signo(T, x, y, st, col, fase=0):
    """El signo arriba a su derecha (los de hoy, con un poco de vida): ••• piensa, ? pregunta, ✓ terminó, z duerme,
    ! un problema."""
    import hub_paleta as P
    C, ERR = P.C, P.ERR
    if not (0 <= y < T.h):
        return
    if st == "trabaja":
        for i in range(3):
            if 0 <= x - 2 + i < T.w:
                T.put(x - 2 + i, y, "•", col if i == fase % 3 else C["tx3"])
    elif st == "pregunta":
        T.put(min(T.w - 1, x + (fase % 2)), y, "?", col if fase % 2 == 0 else P.mix(col, "#ffffff", 0.35), True)
    elif st == "termino":
        T.put(min(T.w - 1, x), y, "✓", col, True)
    elif st == "duerme":
        T.put(min(T.w - 1, x + (fase % 2)), y, "z" if fase % 2 == 0 else "Z", C["tx3"])
    elif st == "error":
        if fase % 2 == 0:
            T.put(min(T.w - 1, x), y, "!", ERR, True)


# ── las secuencias del diseñador: [(ms, gesto, signo, fase)] ──────────────────
def salto(ojos="normal", alto=2):
    return [(Q16 * 2, {"dw": 2, "dh": -1, "ojos": ojos}), (Q16, {"ojos": ojos}),
            (Q16 * 2, {"lift": 1, "dw": -2 if alto > 1 else 0, "dh": 1 if alto > 1 else 0, "ojos": ojos}),
            (Q16 * 2, {"lift": alto, "ojos": ojos}), (Q16 * 2, {"lift": 1, "ojos": ojos}),
            (Q16 * 2, {"dw": 2, "dh": -1, "ojos": ojos}), (Q16, {"ojos": ojos})]


def anim_brinco():
    return [(ms, g, None, 0) for ms, g in salto()] + [(1400, {}, None, 0)]


def anim_piensa():
    return [(Q4, {"mira": mira, "lift": 1 if k in (2, 6) else 0}, "trabaja", k)
            for k, mira in enumerate((0, 1, 0, -1, 0, 1, 0, -1))]


def anim_pregunta():
    out = [(Q4, {"ojos": "grande"}, "pregunta", k) for k in range(6)]
    out += [(ms, dict(g, ojos="grande"), "pregunta", 0) for ms, g in salto("grande", 1)]
    out += [(Q4, {"ojos": "grande" if k != 2 else "cerrado"}, "pregunta", k) for k in range(4)]
    return out


def anim_termino():
    out = []
    chispas = [None, None, "a", "a", "b", "b", None]
    for _r in range(2):
        for k, (ms, g) in enumerate(salto("feliz", 2)):
            out.append((ms, g, "chispa", chispas[k]))
    out += [(1200, {"ojos": "feliz"}, "termino", 0), (1500, {}, "termino", 0)]
    return out


def anim_duerme():
    return [(Q2, {}, "duerme", 0), (Q2, {"dw": 2, "dh": -1}, "duerme", 0), (Q2, {"dw": 2, "dh": -1}, "duerme", 1),
            (Q2, {}, "duerme", 1)]


def anim_error():
    out = [(Q12, {"dx": dx, "ojos": "apretado"}, "error", 0) for dx in (-1, 1, -1, 1, -1, 1, 0)]
    out += [(Q2, {"ojos": "apretado"}, "error", 0), (Q2, {"ojos": "apretado"}, "error", 1),
            (Q2, {"ojos": "apretado"}, "error", 0), (Q2, {"ojos": "normal"}, "error", 1)]
    return out


def anim_gelatina():
    return [(Q16 * 2, {"dw": 2, "dh": -1, "ojos": "cerrado"}, None, 0),
            (Q16 * 2, {"dw": -2, "dh": 1, "ojos": "feliz"}, None, 0),
            (Q16 * 2, {"dw": 2, "dh": -1, "ojos": "feliz"}, None, 0),
            (Q16 * 2, {"dw": -2, "dh": 0, "ojos": "feliz"}, None, 0), (Q16 * 2, {"ojos": "feliz"}, None, 0),
            (1600, {}, None, 0)]


#: Las ocho: nombre → (secuencia, cuadros por segundo, se repite). «libre» es la micro-vida (ver Vida); su secuencia
#: es la del diseñador, para medirla y verla entera.
def anim_libre():
    n = {"ojos": "normal"}
    return [(2500, n, None, 0), (Q8, {"ojos": "cerrado"}, None, 0), (1000, n, None, 0),
            (750, {"mira": -1}, None, 0), (750, {"mira": 1}, None, 0), (375, n, None, 0),
            (Q8, {"ojos": "cerrado"}, None, 0), (Q8, n, None, 0), (Q8, {"ojos": "cerrado"}, None, 0),
            (1000, n, None, 0), (Q8, {"lift": 1}, None, 0), (Q8, {"lift": 1, "dw": 0}, None, 0),
            (1500, n, None, 0)]


ANIMS = {"libre": (anim_libre, 8, True), "brinco": (anim_brinco, 16, False), "piensa": (anim_piensa, 4, True),
         "pregunta": (anim_pregunta, 4, True), "festeja": (anim_termino, 12, False),
         "duerme": (anim_duerme, 2, True), "problema": (anim_error, 12, True), "gelatina": (anim_gelatina, 16, False)}
_SEQ = {}


def secuencia(nombre):
    if nombre not in _SEQ:
        _SEQ[nombre] = ANIMS[nombre][0]()
    return _SEQ[nombre]


def duracion(nombre):
    return sum(p[0] for p in secuencia(nombre))


def _cuadro(t):
    """Los segundos `t` llevados al reloj de 16 cps (en ms)."""
    return int(max(0.0, t) * 1000.0 // CUADRO_MS) * CUADRO_MS


def paso(nombre, ms, vuelta=False):
    """(gesto, signo, fase, ms hasta el siguiente paso) de la secuencia `nombre` a los `ms` de empezada; None si ya
    acabó (y no se repite)."""
    seq = secuencia(nombre)
    total = duracion(nombre)
    if vuelta:
        ms = ms % total
    elif ms >= total:
        return None
    acc = 0
    for dur, g, sig, fase in seq:
        if ms < acc + dur:
            return g, sig, fase, acc + dur - ms
        acc += dur
    return None


# ── la micro-vida en reposo: un horario por agente, sin dos parpadeos a la vez ─
PARPADEO = [(Q8, {"ojos": "cerrado"})]
DOBLE = [(Q8, {"ojos": "cerrado"}), (Q8, {}), (Q8, {"ojos": "cerrado"})]
MIRAR = [(750, {"mira": -1}), (750, {"mira": 1}), (375, {})]
SALTITO = [(Q8, {"lift": 1}), (Q8, {"lift": 1})]


class Vida:
    """El horario de la micro-vida: por agente, sus parpadeos (cada 3-6 s, a veces dobles), a veces mirar a un lado y
    un saltito cada ~8 s. Los parpadeos se apartan en todo el hub: dos nunca se enciman. Se genera según avanza el
    reloj (determinista por agente: su semilla sale de su id)."""

    def __init__(self):
        self.ag = {}                                 # aid → {"rng", "ev": [(t0, t1, pasos, es_parpadeo)], ...}
        self.parpadeos = []                          # (t0, t1) de todos, para que no se encimen

    def _libre_de_parpadeo(self, t0, dur):
        mueve = True
        while mueve:
            mueve = False
            for a, b in self.parpadeos:
                if t0 < b + 0.07 and a < t0 + dur + 0.07:  # al menos un cuadro de aire entre dos
                    t0, mueve = b + 0.07, True
        return t0

    def _ag(self, aid, t):
        x = self.ag.get(aid)
        if x is None:
            import random
            rng = random.Random(zlib.crc32(str(aid).encode("utf-8")))
            x = {"rng": rng, "ev": [], "p": t + rng.uniform(0.6, 3.5), "s": t + rng.uniform(4.0, 9.0)}
            self.ag[aid] = x
        return x

    def _generar(self, aid, hasta):
        x = self.ag[aid]
        rng = x["rng"]
        while x["p"] < hasta:                         # parpadeos (y a veces mirar entre uno y el siguiente)
            pasos = DOBLE if rng.random() < 0.25 else PARPADEO
            dur = sum(ms for ms, _g in pasos) / 1000.0
            t0 = self._libre_de_parpadeo(x["p"], dur)
            self.parpadeos.append((t0, t0 + dur))
            x["ev"].append((t0, t0 + dur, pasos))
            sig = t0 + rng.uniform(3.0, 6.0)
            if rng.random() < 0.3:
                tm = t0 + dur + 0.6
                dm = sum(ms for ms, _g in MIRAR) / 1000.0
                if tm + dm < sig - 0.3:
                    x["ev"].append((tm, tm + dm, MIRAR))
            x["p"] = sig
        while x["s"] < hasta:                         # el saltito, cada ~8 s (si cae en un parpadeo, se juntan)
            t0 = x["s"]
            dur = sum(ms for ms, _g in SALTITO) / 1000.0
            x["ev"].append((t0, t0 + dur, SALTITO))
            x["s"] = t0 + rng.uniform(7.0, 9.0)
        x["ev"].sort(key=lambda e: e[0])

    def gesto(self, aid, t):
        """(gesto, segundos hasta que cambie) del agente `aid` en reposo al tiempo `t` (en el reloj de 16 cps)."""
        x = self._ag(aid, t)
        self._generar(aid, t + 12.0)
        corte = t - 15.0
        x["ev"] = [e for e in x["ev"] if e[1] >= corte]
        if len(self.parpadeos) > 400:
            self.parpadeos = [p for p in self.parpadeos if p[1] >= corte]
        g_, prox = {}, None
        for t0, t1, pasos in x["ev"]:                 # si se enciman (un saltito y un parpadeo), se juntan
            if t0 <= t < t1:
                acc = t0
                for ms, g in pasos:
                    if t < acc + ms / 1000.0:
                        g_.update(g)
                        falta = acc + ms / 1000.0 - t
                        prox = falta if prox is None else min(prox, falta)
                        break
                    acc += ms / 1000.0
            elif t0 > t:
                prox = t0 - t if prox is None else min(prox, t0 - t)
        return g_, prox


VIDA = Vida()
_MENOS = []


def menos_movimiento(env=None):
    """¿El cuerpo quieto (solo cambian los signos)? WORKSPACE_MENOS_MOVIMIENTO=1/0 manda; si no, en la Mac, «Reducir
    movimiento» del sistema (se lee una vez)."""
    env = os.environ if env is None else env
    v = str(env.get("WORKSPACE_MENOS_MOVIMIENTO") or "").strip().lower()
    if v in ("1", "si", "sí", "true", "on"):
        return True
    if v in ("0", "no", "false", "off"):
        return False
    if env is not os.environ:
        return False
    if not _MENOS:
        r = False
        if sys.platform == "darwin":
            try:
                p = subprocess.run(["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=1.0)
                r = p.returncode == 0 and p.stdout.strip() == "1"
            except Exception:
                r = False
        _MENOS.append(r)
    return _MENOS[0]


# ── qué hace cada monito en el cuadro `s["t"]` ────────────────────────────────
_LOOP = {"trabaja": "piensa", "pregunta": "pregunta", "duerme": "duerme", "error": "problema"}
_CARA = {"duerme": {"ojos": "cerrado"}, "pregunta": {"ojos": "grande"}, "error": {"ojos": "apretado"}}


def _desfase(aid, total):
    return zlib.crc32(("loop:" + str(aid)).encode("utf-8")) % max(1, total)


def estado(s, a, st=None):
    """→ (gesto, signo, fase, segundos hasta el siguiente cambio o None). Lo de una vez (gelatina al picarlo,
    brinco al elegirlo, festejar al terminar) gana sobre lo de su estado (piensa, pregunta, duerme, problema), y eso
    sobre la micro-vida."""
    st = st or a.get("st") or "libre"
    aid = a.get("id") or ""
    t = (s or {}).get("t") or 0.0
    an = ((s or {}).get("anim") or {}).get(aid) or {}
    quieto = menos_movimiento()
    sig_st = st if st in ("trabaja", "pregunta", "termino", "duerme", "error") else None
    if not quieto:
        for nombre, clave in (("gelatina", "gel"), ("brinco", "brinco"), ("festeja", "fiesta")):
            t0 = an.get(clave)
            if t0 is None or t < t0:
                continue
            r = paso(nombre, _cuadro(t - t0))
            if r:
                g, sig, fase, falta = r
                if sig is None and sig_st:
                    sig, fase = sig_st, 0
                return dict(_CARA.get(st, {}), **g) if nombre != "festeja" else g, sig, fase, falta / 1000.0
    loop = _LOOP.get(st)
    if loop:
        ms = _cuadro(t) + _desfase(aid, duracion(loop))
        g, sig, fase, falta = paso(loop, ms, vuelta=True)
        if quieto:                                    # solo cambian los signos
            return dict(_CARA.get(st, {})), sig, fase, falta / 1000.0
        return g, sig, fase, falta / 1000.0
    if quieto or s is None:
        return {}, sig_st, 0, None
    g, falta = VIDA.gesto(aid, _cuadro(t) / 1000.0)
    return g, sig_st, 0, falta


def dibujar(T, a, x, y, tam, s=None, st=None, signo_=True):
    """El contrato de hub_monitos: el monito de `a` donde hoy va el de la Paleta (su columna x-1 a x+tam; de pie en
    la fila y + alto) con la animación de su cuadro."""
    st = st or a.get("st") or "libre"
    t = tam_de(tam)
    m, _o = sprite(a.get("f") or "bolita", t)
    wc = len(m[0])
    x0 = x - 1 + max(0, (tam + 2 - wc) // 2)
    if s is None:
        g, sig, fase = dict(_CARA.get(st, {})), (st if st in ("trabaja", "pregunta", "termino", "duerme", "error")
                                                 else None), 0
    else:
        g, sig, fase, _falta = estado(s, a, st)
    g = dict(g)
    if st == "duerme":
        g.setdefault("ojos", "cerrado")
    if t == "grande":                                 # el grande se mueve el doble (en sus pixeles)
        for k in ("lift", "dw", "dh", "dx"):
            if k in g:
                g[k] = g[k] * 2
    monito(T, a.get("f") or "bolita", a.get("c") or "#ffffff", t, x0, y, g, st)
    if not signo_:
        return
    xs = x0 + wc
    col = a.get("c") or "#ffffff"
    if sig == "chispa":                               # festeja: chispas (en el riel, solo a la derecha: así cada
        if fase in ("a", "b"):                        # cuadro reescribe un tramo corto, como lo midió el diseñador)
            if xs < T.w and y >= 1:
                T.put(xs, y - 1, "✦" if fase == "a" else "·", col, True)
            if t == "grande" and x0 - 2 >= 0:
                T.put(x0 - 2, y if fase == "a" else y - 1, "·" if fase == "a" else "✦", col, True)
    elif sig:
        signo(T, xs, y - 1, sig, col, fase if isinstance(fase, int) else 0)


def espera(s):
    """Segundos hasta que algún monito de `s` cambie (en el reloj de 16 cps); None si todos están quietos."""
    mejor = None
    for a in (s or {}).get("agentes") or ():
        _g, _sig, _f, falta = estado(s, a, a.get("st"))
        if falta is not None:
            mejor = falta if mejor is None else min(mejor, falta)
    if mejor is None:
        return None
    return max(CUADRO_MS / 1000.0, mejor)
