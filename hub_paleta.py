#!/usr/bin/env python3
r"""WORKSPACE · hub_paleta — el hub «Paleta» (H-B del concepto de marca v1). SOLO PARA PROBAR: vive en la rama
zenith/marca-lab y nunca entra a main.

Una sola línea: escribes lo que quieres y el hub lo lleva al agente y a su motor oficial.
  · arriba, la barra de estado: ❯ workspace, tus agentes por número, el motor del elegido y su uso, y la hora;
  · la fila de monitos en medios bloques (▀ ▄ █), en el color de cada agente; brincan solo al elegir;
  · la entrada «Escribe lo que quieras…» y, debajo, las opciones: hablar con el agente elegido, lo que te preguntan
    los agentes y lo que terminaron (vacía), o a quién se lo mandas (con texto);
  · Enter manda · Tab cambia de agente · ↑↓ elige · Esc borra (sin texto, sale).

Enter le entrega tu pedido al motor oficial del agente por el lanzador de siempre (dispatch), con tu mensaje como
primer mensaje en los motores que lo aceptan al abrir (PRIMER_MENSAJE). En los demás lo abre vacío y tu texto queda
copiado, con un aviso de una línea. Al salir del motor vuelves aquí.

Desde el 18-nov el hub de la rama es hub_directo (la conversación directa, la misma de la página): usa de aquí la piel,
los monitos, el pintor y la entrega, que ahí es la tecla «Abrir en su motor» (^O). Esta pantalla queda para cuando la
página local no se puede prender, o con WORKSPACE_HUB_DIRECTO=0.

La pantalla es una grilla de celdas, como las maquetas del concepto (Concepto_Marca_v1 · _marca_js.py: barraSup,
monTUI, PANT['b-main'] y PANT['b-entrega']), con color real o 256 colores. Los monitos salen de los MISMOS trazos que la
página (web/front/src/10_monitos.js · PATH), rasterizados a 8, 12 o 16 pixeles: cada celda pinta 2 (▀ ▄).

Los datos son reales: los agentes del registro con su monito (localhost_front.inicio, lo mismo que la página), su
motor y su uso (la barra de Claude Code, los límites de Codex), y lo que te preguntan o terminaron, del registro de
eventos del núcleo (arquitectura/registro). Nada se inventa: lo que no se sabe, no se muestra.

Sin pantalla (para comparar con la maqueta):
    python3 hub_paleta.py --render 88x30 [--entrega] [--256] [--ejemplo] [--html salida.html]
Stdlib."""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from functools import lru_cache

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
PY = sys.executable
DISPATCH = os.path.join(AQUI, "dispatch.py")

# ── la piel: la de las maquetas ───────────────────────────────────────────────
T_BG, T_FG = "#121214", "#c9c9d1"
C = {"tx": "#ededf0", "tx2": "#a4a4ad", "tx3": "#6f6f78", "line": "#303036", "lit": "#232327", "key": "#2c2c32"}
BARRA_BG = "#1a1a1d"
#: El hub lateral (L-1): el mouse encima de un agente o de una sesión (solo el fondo), encima de un botón de la barra
#: (o su menú abierto), y encima de un botón de la caja de permiso o de pregunta. En 256 colores: 234, 236 y 239.
HOV, TILE_H, KEY_H = "#1e1e22", "#2a2a30", "#4a4a54"
LIT, KEY, LINE = C["lit"], C["key"], C["line"]
NUM_DORMIDO = "#46464d"
GRIS_DORMIDO = "#4a4a52"
#: Desde este ancho, la versión ancha (la maqueta: 88×30); por debajo, la angosta (46×36).
ANCHO_MIN = 60
#: Lo mínimo para dibujar algo con sentido.
MIN_W, MIN_H = 40, 22

#: Los motores que aceptan tu mensaje al abrir su sesión, por el lanzador de Workspace (verificado 18-nov):
#:   · claude-code: `claude [prompt]` (su --help: «Your prompt»); engines/claude_code.launch pone lo que le pasan al
#:     final del argv.
#:   · codex: `codex [PROMPT]` («Optional user prompt to start the session»); engines/codex._interactive_argv: «Explicit
#:     prompts… remain owned by the caller» (con tu mensaje no mete su «Inicia el cerebro»; su identidad y memoria
#:     siguen en el AGENTS.md del cerebro).
#: Los demás: su CLI lo acepta (agent [prompt], kiro-cli chat [INPUT], agy -i, openclaw tui --message, opencode
#: --prompt) pero su lanzador de Workspace usa ese lugar para el arranque, o no se verificó: se abren vacíos y tu
#: texto queda copiado.
PRIMER_MENSAJE = ("claude-code", "codex")
#: Lo que dispatch toma como suyo: un mensaje así no va como mensaje (se copia).
_RESERVADAS = ("ls", "list", "migrar", "migracion")

NOMBRE_MOTOR = {"claude-code": "Claude Code", "codex": "Codex", "copilot": "GitHub Copilot", "cursor": "Cursor",
                "kiro": "Kiro", "opencode": "OpenCode", "antigravity": "Antigravity", "hermes": "Hermes",
                "openclaw": "OpenClaw", "gemini": "Gemini"}


def jsround(x):
    """Math.round de JavaScript (las maquetas): .5 hacia arriba."""
    return int(math.floor(x + 0.5))


def h2r(h):
    n = int(h[1:], 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def r2h(r):
    return "#" + "".join("%02x" % max(0, min(255, jsround(v))) for v in r)


def mix(a, b, k):
    A, B = h2r(a), h2r(b)
    return r2h([A[i] * (1 - k) + B[i] * k for i in range(3)])


_LV = (0, 95, 135, 175, 215, 255)


def q256(hexa):
    """El número de 256 colores más cercano (el cubo xterm 6×6×6 o la escala de grises), como q256n de la maqueta."""
    c = h2r(hexa)

    def ix(v):
        return min(range(6), key=lambda i: abs(_LV[i] - v))
    ri, gi, bi = ix(c[0]), ix(c[1]), ix(c[2])
    cc = (_LV[ri], _LV[gi], _LV[bi])
    dc = sum((cc[i] - c[i]) ** 2 for i in range(3))
    g = max(0, min(23, jsround((sum(c) / 3 - 8) / 10)))
    gv = 8 + g * 10
    dg = sum((gv - c[i]) ** 2 for i in range(3))
    return 232 + g if dg < dc else 16 + 36 * ri + 6 * gi + bi


# ── la grilla de celdas (el Term de la maqueta) ────────────────────────────────
class Celda:
    """Una celda: su letra, su color, su fondo y si va en negrita. `px`: es un pixel de un monito (lo pintó flat());
    `fm`: su tinta con el fondo P-3 (la pone afinar en los bloques), para la salida de Terminal.app."""
    __slots__ = ("ch", "fg", "bg", "b", "px", "fm")

    def __init__(self):
        self.ch, self.fg, self.bg, self.b = " ", None, None, False
        self.px, self.fm = False, None


try:
    from _width import eaw as _eaw
except ImportError:                                  # pragma: no cover — _width vive junto a este archivo
    def _eaw(c):
        if unicodedata.category(c) in ("Mn", "Me", "Cf"):
            return 0
        return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def _ancho(s):
    """Columnas que ocupa `s` en la terminal (un emoji o un CJK, 2; un acento suelto, 0)."""
    return sum(_eaw(c) for c in str(s))


def _sgr(fg, bg, b, colores):
    fg, bg = fg or T_FG, bg or T_BG
    if colores == "256":
        return "\x1b[0;%s38;5;%d;48;5;%dm" % ("1;" if b else "", q256(fg), q256(bg))
    return "\x1b[0;%s38;2;%d;%d;%d;48;2;%d;%d;%dm" % ((("1;" if b else ""),) + h2r(fg) + h2r(bg))


@lru_cache(maxsize=1024)
def _tinta_afinada(fg, fondo_tema):
    """La tinta de un bloque con el mismo fondo P-3 que los planos: en Terminal.app una orilla de ficha o de botón se
    vuelve celda llena, y así queda del mismo color que el plano de al lado (los monitos guardan su color)."""
    return mix(fg or T_FG, fondo_tema or "#102029", 0.40 if fondo_tema else 0.16)


@lru_cache(maxsize=1024)
def _colores_afinados(fg, bg, texto, fondo_tema):
    from theme_render import legible, TEXT_MIN

    fondo = mix(bg or T_BG, fondo_tema or "#102029", 0.40 if fondo_tema else 0.16)
    return (legible(fg or T_FG, fondo, TEXT_MIN) if texto else fg), fondo


def afinar(term, fondo_tema=None):
    """P-3: fondo frío y contraste AA en texto, conservando glifos y acentos de los monitos."""
    for celda in term.cl:
        ch = celda.ch
        texto = bool(ch and not ch.isspace() and not ("\u2500" <= ch <= "\u259f"))
        celda.fm = _tinta_afinada(celda.fg, fondo_tema) if ch and "\u2580" <= ch <= "\u259f" else None
        celda.fg, celda.bg = _colores_afinados(celda.fg, celda.bg, texto, fondo_tema)
    return term


# ── Terminal.app: los bloques que no llegan arriba (H6-a) ─────────────────────
#: Terminal.app (TERM_PROGRAM=Apple_Terminal) dibuja los bloques con SU fuente (SF Mono Terminal 12 pt, medido con
#: CoreText): █ va de −2.72 a 9.28 pt desde la base en una fila de 14.32 pt → le faltan 2.15 pt ARRIBA (≈15 %) en cada
#: celda, y los monitos, las fichas y los botones salían con rayas. iTerm2 y Windows Terminal dibujan ellos los bloques
#: (llenan la celda): ahí nada cambia. En Terminal.app la SALIDA cambia lo que toca el tope de la celda por algo anclado
#: abajo o por un fondo (el fondo sí llena la celda), como el ícono de Terminal.app del hub de antes (v16):
#:   █ → espacio con su color de fondo · ▀ ▘ ▝ → ▄ con los colores al revés · ▌ ▐ ▙ ▛ ▜ ▟ ▚ ▞ ▏ ▕ (los cuartos, las
#:   orillas de las fichas y el cursor) → la celda llena · ▗ ▖ → ▄ (el botón queda en cuadrito) · ▔ → ─
#: Las celdas (lo que se compara entre cuadros y lo que ven las pruebas) no cambian: solo lo que se escribe.
_LLENA = frozenset("█▌▐▙▛▜▟▚▞▏▕")
_ALREVES = frozenset("▀▘▝")
_ABAJO = frozenset("▗▖")
_TOPE = _LLENA | _ALREVES | _ABAJO | frozenset("▔")


def terminal_app(env=None):
    """¿Esta salida va a Terminal.app de Mac?"""
    e = os.environ if env is None else env
    return str(e.get("TERM_PROGRAM") or "") == "Apple_Terminal"


def anclada(ch, fg, bg):
    """La celda (letra, frente, fondo) que Terminal.app dibuja entera: nada toca el tope de la celda."""
    if ch in _LLENA:
        return " ", fg, fg
    if ch in _ALREVES:
        return "▄", bg, fg
    if ch in _ABAJO:
        return "▄", fg, bg
    if ch == "▔":
        return "─", fg, bg
    return ch, fg, bg


class Term:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cl = [Celda() for _ in range(w * h)]
        self.P = [[None] * w for _ in range(2 * h)]
        #: Lo que se toca con el mouse, en el orden en que se dibujó: (x, y, ancho, alto, id). Se busca de la última a
        #: la primera (lo dibujado encima gana).
        self.zonas = []

    def at(self, x, y):
        return self.cl[y * self.w + x] if 0 <= x < self.w and 0 <= y < self.h else None

    def _suelta(self, x, y):
        """Antes de escribir en (x, y): si ahí vivía la mitad de un carácter ancho, la otra mitad queda en blanco."""
        k = self.at(x, y)
        if k is None:
            return
        if k.ch == "":
            antes = self.at(x - 1, y)
            if antes is not None:
                antes.ch = " "
        elif _eaw(k.ch) == 2:
            despues = self.at(x + 1, y)
            if despues is not None and despues.ch == "":
                despues.ch = " "

    def put(self, x, y, s, fg=None, b=False, bg=None):
        """Escribe `s` desde la columna `x`. Un carácter ancho (emoji, CJK) ocupa 2 celdas: la segunda queda vacía
        («») y las salidas la saltan. Lo invisible (acentos sueltos, selectores) no ocupa nada; un control (un ESC
        que manda un motor) es un espacio. → la columna siguiente."""
        for ch in str(s):
            if ch < " " or "\x7f" <= ch <= "\x9f":
                ch = " "                                 # nunca un control (ni un ESC de un motor) a la terminal
            n = _eaw(ch)
            if n == 0:
                continue
            if n == 2 and x + 1 >= self.w:
                ch, n = " ", 1                           # no cabe entero en la última columna
            for i in range(n):
                self._suelta(x + i, y)
            k = self.at(x, y)
            if k is not None:
                k.ch, k.fg, k.b, k.px = ch, fg, bool(b), False
                if bg:
                    k.bg = bg
                if n == 2:
                    k2 = self.at(x + 1, y)
                    k2.ch, k2.fg, k2.b, k2.px = "", fg, bool(b), False
                    if bg:
                        k2.bg = bg
            x += n
        return x

    def fill(self, x, y, w, h, bg):
        for j in range(y, y + h):
            for i in range(x, x + w):
                k = self.at(i, j)
                if k is not None:
                    k.bg = bg

    def hl(self, x, y, n, fg, ch="─"):
        if n > 0:
            self.put(x, y, ch * n, fg)

    def box(self, x, y, w, h, fg):
        self.put(x, y, "╭" + "─" * (w - 2) + "╮", fg)
        for j in range(1, h - 1):
            self.put(x, y + j, "│", fg)
            self.put(x + w - 1, y + j, "│", fg)
        self.put(x, y + h - 1, "╰" + "─" * (w - 2) + "╯", fg)

    def right(self, xr, y, s, fg=None, b=False):
        return self.put(xr - _ancho(str(s)), y, s, fg, b)

    def center(self, x, w, y, s, fg=None, b=False):
        return self.put(x + (w - _ancho(str(s))) // 2, y, s, fg, b)

    def key(self, x, y, k, lab=""):
        x = self.put(x, y, " " + k + " ", C["tx"], True, C["key"])
        if lab:
            x = self.put(x + 1, y, lab, C["tx3"])
        return x + 2

    def spr(self, x, py, m):
        for j, fila in enumerate(m):
            for i, c in enumerate(fila):
                if not c:
                    continue
                yy, xx = py + j, x + i
                if 0 <= yy < 2 * self.h and 0 <= xx < self.w:
                    self.P[yy][xx] = c

    def flat(self):
        """Los pixeles a medios bloques: cada celda pinta 2 (arriba y abajo)."""
        for y in range(self.h):
            for x in range(self.w):
                t, b = self.P[2 * y][x], self.P[2 * y + 1][x]
                if not t and not b:
                    continue
                self._suelta(x, y)
                k = self.at(x, y)
                k.b, k.px = False, True
                if t and b:
                    if t == b:
                        k.ch, k.fg = "█", t
                    else:
                        k.ch, k.fg, k.bg = "▀", t, b
                elif t:
                    k.ch, k.fg = "▀", t
                else:
                    k.ch, k.fg = "▄", b

    # ── salidas ──
    def plano(self):
        return ["".join(self.at(x, y).ch for x in range(self.w)).rstrip() for y in range(self.h)]

    def ansi(self, colores="24"):
        """Las filas con color: «24» (color real) o «256». El fondo de la terminal se pinta con T_BG. En Terminal.app,
        con los bloques anclados abajo (anclada)."""
        seguro = terminal_app()
        return [self._tramo(y, 0, self.w, colores, seguro) for y in range(self.h)]

    def _tramo(self, y, x0, x1, colores, seguro=False):
        s, ult = [], None
        for x in range(x0, x1):
            k = self.cl[y * self.w + x]
            ch, fg, bg, b = k.ch, k.fg, k.bg, k.b
            if ch == "":                                 # la segunda mitad de un carácter ancho
                continue
            if seguro and (ch in _TOPE or (ch == "▄" and not k.px)):   # Terminal.app: nada toca el tope
                tinta = fg if k.px else (k.fm or fg)     # (las orillas de fichas y botones, del color de su plano)
                ch, fg, bg = anclada(ch, tinta or T_FG, bg or T_BG)
            est = (fg, bg, b)
            if est != ult and not (ult and ((ch == "█" and (fg, b) == (ult[0], ult[2])) or
                                            (ch == " " and bg == ult[1]))):
                s.append(_sgr(fg, bg, b, colores))      # (█ solo enseña su color y « » su fondo: si lo que se ve ya
                ult = est                                 # está puesto, no se repite el color: los monitos pesan menos)
            s.append(ch)
        return "".join(s) + "\x1b[0m"

    def tramo(self, y, x0, x1, colores="24"):
        """Las celdas x0..x1-1 de la fila `y`, con color, desde un \\x1b[0m (lo que el Pintor escribe de una fila que
        cambió a medias)."""
        return "\x1b[0m" + self._tramo(y, x0, x1, colores, terminal_app())

    def firma(self):
        """Cada fila como sus celdas (letra, color, fondo, negrita): lo que el Pintor compara entre dos cuadros."""
        w, cl = self.w, self.cl
        return [[(k.ch, k.fg, k.bg, k.b, k.px) for k in cl[y * w:(y + 1) * w]] for y in range(self.h)]

    def html(self, colores="24", titulo=""):
        def col(h):
            if colores != "256":
                return h
            n = q256(h)
            if n >= 232:
                v = 8 + (n - 232) * 10
                return r2h((v, v, v))
            n -= 16
            return r2h((_LV[n // 36], _LV[(n // 6) % 6], _LV[n % 6]))
        filas = []
        for y in range(self.h):
            celdas = []
            for x in range(self.w):
                k = self.at(x, y)
                if k.ch == "":
                    continue
                ch = {"<": "&lt;", ">": "&gt;", "&": "&amp;"}.get(k.ch, k.ch)
                celdas.append('<span style="color:%s;background:%s%s">%s</span>' % (
                    col(k.fg or T_FG), col(k.bg or T_BG), ";font-weight:700" if k.b else "", ch))
            filas.append("".join(celdas))
        return ("<!doctype html><meta charset=utf-8><title>%s</title><style>body{margin:24px;background:#0b0b0c;"
                "color:#ccc;font:13px system-ui}pre{display:inline-block;margin:8px 0;font:14px/1 Menlo,'SF Mono',"
                "monospace;background:%s}</style><p>%s</p><pre>%s</pre>" % (titulo, T_BG, titulo, "\n".join(filas)))


# ── los monitos: los trazos de la página, a pixeles ───────────────────────────
#: Copia de web/front/src/10_monitos.js (PATH). Se lee de ahí si está (una sola piel); si no, esta.
_PATH = {
    "bolita": "M50 12C74 12 90 30 90 54S74 92 50 92 10 78 10 54 26 12 50 12Z",
    "pico": "M50 10C58 10 64 20 72 34 82 52 92 66 92 78 92 90 82 94 50 94S8 90 8 78C8 66 18 52 28 34 36 20 42 10 50 10Z",
    "cuadrito": "M28 14H72C84 14 90 20 90 32V74C90 86 84 92 72 92H28C16 92 10 86 10 74V32C10 20 16 14 28 14Z",
    "gatito": "M18 30 16 8 38 22C42 21 46 20 50 20S58 21 62 22L84 8 82 30C88 38 91 46 91 56 91 78 74 92 50 92S9 78 9 56C9 "
              "46 12 38 18 30Z",
    "fantasma": "M50 10C72 10 88 26 88 50V90L78 82 68 90 58 82 50 90 42 82 32 90 22 82 12 90V50C12 26 28 10 50 10Z",
    "nube": "M30 92C16 92 8 84 8 72 8 60 16 52 26 52 26 36 38 24 54 24 68 24 78 34 80 46 90 48 94 58 94 66 94 82 84 92 "
            "70 92Z",
}


def _trazos():
    try:
        with open(os.path.join(AQUI, "web", "front", "src", "10_monitos.js"), encoding="utf-8") as fh:
            src = fh.read()
        bloque = src[src.index("var PATH = {"):]
        bloque = bloque[:bloque.index("};")]
        leidos = dict(re.findall(r"(\w+): '([^']+)'", bloque))
        if set(_PATH) <= set(leidos):
            return {k: leidos[k] for k in _PATH}
    except (OSError, ValueError):
        pass
    return dict(_PATH)


PATH = _trazos()


def _poligonos(d):
    """Los subcaminos de un trazo SVG (M L H V C S Z, absolutos), con las curvas aplanadas."""
    tok = re.findall(r"[MLHVCSZ]|-?\d*\.?\d+", d)
    polis, cur, i, cmd = [], [], 0, None
    x = y = 0.0
    c2 = None                                       # el segundo control de la curva anterior (para S)

    def num():
        nonlocal i
        v = float(tok[i])
        i += 1
        return v

    def bez(p0, p1, p2, p3, n=16):
        for k in range(1, n + 1):
            t = k / n
            u = 1 - t
            cur.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                        u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    while i < len(tok):
        if tok[i] in "MLHVCSZ":
            cmd = tok[i]
            i += 1
            if cmd == "Z":
                if cur:
                    polis.append(cur)
                cur, c2 = [], None
                continue
        if cmd == "M":
            if cur:
                polis.append(cur)
            x, y = num(), num()
            cur, c2, cmd = [(x, y)], None, "L"      # más pares después de M = líneas
        elif cmd == "L":
            x, y = num(), num()
            cur.append((x, y))
            c2 = None
        elif cmd == "H":
            x = num()
            cur.append((x, y))
            c2 = None
        elif cmd == "V":
            y = num()
            cur.append((x, y))
            c2 = None
        elif cmd == "C":
            p1, p2, p3 = (num(), num()), (num(), num()), (num(), num())
            bez((x, y), p1, p2, p3)
            x, y = p3
            c2 = p2
        elif cmd == "S":
            p1 = (2 * x - c2[0], 2 * y - c2[1]) if c2 else (x, y)
            p2, p3 = (num(), num()), (num(), num())
            bez((x, y), p1, p2, p3)
            x, y = p3
            c2 = p2
        else:
            raise ValueError("comando de trazo no soportado: %r" % cmd)
    if cur:
        polis.append(cur)
    return polis


_MASK = {}


def mascara(forma, S, sx=1.0, sy=1.0):
    """S filas × (S+2) columnas de 0/1, como mascara() de la maqueta: el trazo (caja de 88 de alto, pie en 94) escalado
    a S pixeles; un pixel va si su celda queda cubierta al menos a la mitad (8 líneas de muestra por pixel, cobertura
    horizontal exacta). Los dientes del fantasma salen de su trazo; la regla de la maqueta que los recorta en la última
    fila no cambia nada a 8, 12 ni 16 pixeles (esa fila queda vacía) y no se copió."""
    clave = (forma, S, sx, sy)
    if clave in _MASK:
        return _MASK[clave]
    W, k = S + 2, S / 88.0
    tx, ty = W / 2.0 - 50 * k * sx, S - 94 * k * sy
    lados = []
    for p in _poligonos(PATH[forma]):
        q = [(tx + k * sx * a, ty + k * sy * b) for a, b in p]
        lados += [(q[n], q[(n + 1) % len(q)]) for n in range(len(q))]
    cob = [[0.0] * W for _ in range(S)]
    N = 8
    for j in range(S):
        for r in range(N):
            yy = j + (r + 0.5) / N
            cruces = []
            for (x0, y0), (x1, y1) in lados:
                if (y0 <= yy < y1) or (y1 <= yy < y0):
                    cruces.append((x0 + (yy - y0) * (x1 - x0) / (y1 - y0), 1 if y1 > y0 else -1))
            cruces.sort()
            vuelta, desde = 0, None
            for cx, d in cruces:                     # regla de vueltas (la de canvas): dentro si ≠ 0
                antes = vuelta
                vuelta += d
                if antes == 0 and vuelta != 0:
                    desde = cx
                elif antes != 0 and vuelta == 0 and desde is not None:
                    a, b = max(0.0, desde), min(float(W), cx)
                    for i in range(int(math.floor(a)), int(math.ceil(b))):
                        if 0 <= i < W:
                            cob[j][i] += (min(b, i + 1) - max(a, i)) / N
    m = [[1 if cob[j][i] >= 0.5 else 0 for i in range(W)] for j in range(S)]
    _MASK[clave] = m
    return m


EYE = {6: (2, 5, 1), 8: (3, 6, 2), 10: (4, 7, 2), 12: (5, 8, 2), 16: (7, 10, 3)}


def ojo(color):
    return "#ffffff" if color in ("#3b82f6", "#8b5cf6") else "#231b2c"


def sprite(color, forma, S, eye, sx=1.0, sy=1.0, cerrados=False, mira=0, mira_chico=False):
    """El monito a pixeles. `mira`: hacia dónde ven sus ojos (-1, 0, 1); en los chicos (S < 10) la maqueta los deja
    al centro, salvo `mira_chico` (el que piensa mira a un lado y al otro)."""
    m = mascara(forma, S, sx, sy)
    px = [[color if v else None for v in fila] for fila in m]
    e = EYE[S]
    h, oy = e[2], (60 if forma in ("pico", "nube") else 52)
    cy = S - (94 - (oy - 1.5)) * S / 88.0 * sy
    top, dx = jsround(cy - h / 2.0), (mira if S >= 10 or mira_chico else 0)
    for ex in (e[0] + dx, e[1] + dx):
        filas = [top + h - 1] if cerrados else [top + j for j in range(h)]
        for yy in filas:
            if 0 <= yy < len(px) and 0 <= ex < len(px[yy]) and px[yy][ex]:
                px[yy][ex] = eye
    return px


#: El brinco de la maqueta (monTUI): aplastón, arriba 1 pixel, aplastón. Solo al elegir.
BRINCO_S = 0.62
#: Cada cuánto aparece un paso de la entrega (s).
PASO_ENTREGA_S = 0.18


def _brinco(fase):
    if fase is None or fase >= BRINCO_S:
        return 0, 1.0, 1.0
    if fase < 0.12:
        return 0, 1.12, 0.9
    if fase < 0.5:
        return 1, 1.0, 1.0
    return 0, 1.14, 0.86


#: El signo de un problema (la página: la tarjeta de error).
ERR = "#e5534b"


def signo(T, a, x, y, st, puntos=2):
    """Lo que dice el monito arriba a su derecha. `puntos`: cuál de los tres puntos del que trabaja va encendido
    (el que piensa los recorre)."""
    if st == "trabaja":
        for i in range(3):
            T.put(x + i, y, "•", a["c"] if i == puntos else C["tx3"])
    elif st == "pregunta":
        T.put(x, y, "?", a["c"], True)
    elif st == "termino":
        T.put(x, y, "✓", a["c"], True)
    elif st == "duerme":
        T.put(x, y, "Z", C["tx3"])
    elif st == "error":
        T.put(x, y, "!", ERR, True)


def monito(T, a, x, y, S, fase=None, st=None, sin_signo=False, mira=0, puntos=2):
    st = st or a.get("st") or "libre"
    lift, sx, sy = _brinco(fase)
    col = mix(a["c"], GRIS_DORMIDO, 0.42) if st == "duerme" else a["c"]
    T.spr(x - 1, y * 2 - lift, sprite(col, a["f"], S, ojo(a["c"]), sx, sy, cerrados=(st == "duerme"), mira=mira,
                                      mira_chico=(st == "trabaja")))
    if not sin_signo:
        signo(T, a, x + S - (2 if st == "trabaja" else 0), y - 1, st, puntos)


# ── la lógica de la entrada (pura) ─────────────────────────────────────────────
def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(c) != "Mn")


def destino(texto, agentes, sel):
    """A quién va tu pedido: el agente que nombras («pídele a turing…», «Doc, …»); si no nombras a ninguno, el
    elegido con Tab (`sel`, un índice)."""
    t = " %s " % re.sub(r"[^a-z0-9]+", " ", _sin_acentos(texto))
    for i, a in enumerate(agentes):
        for nombre in {a.get("id") or "", a.get("n") or ""}:
            n = re.sub(r"[^a-z0-9]+", " ", _sin_acentos(nombre)).strip()
            if n and " %s " % n in t:
                return i
    return sel if agentes else None


def motor_de(a):
    return NOMBRE_MOTOR.get(a.get("mid") or "", a.get("m") or a.get("mid") or "su motor")


def acepta_mensaje(a, texto):
    """¿Ese motor abre con tu mensaje? Solo los de PRIMER_MENSAJE, y un texto que dispatch no tome como suyo."""
    t = str(texto or "").strip()
    return (a.get("mid") in PRIMER_MENSAJE and bool(t) and not t.startswith("-")
            and t.split()[0].lower() not in _RESERVADAS)


def opciones(texto, agentes, sel, preguntas=(), terminados=()):
    """Lo que sale debajo de la entrada, en orden. Cada una: {tipo, titulo, detalle, agente (índice), texto?}.
      · sin texto: hablar con el elegido, lo que te preguntan y lo que terminaron;
      · con texto: mandárselo a quien va (el que nombras o el elegido), a los demás, o abrir su motor sin mensaje."""
    if not agentes:
        return []
    t = str(texto or "").strip()
    out = []
    if not t:
        a = agentes[sel]
        out.append({"tipo": "abrir", "titulo": "Hablar con %s" % a["n"], "detalle": "abre %s" % motor_de(a),
                    "agente": sel})
        for p in preguntas:
            out.append({"tipo": "pregunta", "titulo": "%s te pregunta" % agentes[p["agente"]]["n"],
                        "detalle": "«%s»" % p["texto"] if p.get("texto") else "espera tu permiso en su terminal",
                        "agente": p["agente"]})
        for f in terminados:
            out.append({"tipo": "terminado", "titulo": "%s terminó" % agentes[f["agente"]]["n"],
                        "detalle": f.get("texto") or "", "agente": f["agente"]})
        return out
    d = destino(t, agentes, sel)
    orden = [d] + [i for i in range(len(agentes)) if i != d]
    for i in orden[:3]:
        a = agentes[i]
        out.append({"tipo": "enviar", "titulo": "Enviar a %s" % a["n"], "agente": i, "texto": t,
                    "detalle": ("abre %s con tu mensaje" if acepta_mensaje(a, t) else "abre %s · tu texto, copiado")
                    % motor_de(a)})
    out.append({"tipo": "abrir", "titulo": "Abrir %s sin mensaje" % agentes[d]["n"], "detalle": "solo el motor",
                "agente": d})
    return out


def plan(op, agentes, motor=None):
    """Cómo se lanza una opción: {"argv", "copiar", "aviso", "agente", "texto", "motor"}. Siempre por dispatch (el
    lanzador de siempre). Con mensaje solo si su motor lo acepta al abrir; si no, se copia y se dice en una línea.
    `motor`: el de la conversación directa, si no es el del agente (`--engine`, solo esta corrida)."""
    a = agentes[op["agente"]]
    argv = [PY, DISPATCH, a["id"]]
    if motor and motor != a.get("mid"):
        a = dict(a, mid=motor)
        argv += ["--engine", motor]
    texto = op.get("texto") or ""
    copiar = aviso = None
    if op["tipo"] == "enviar":
        if acepta_mensaje(a, texto):
            argv.append(texto)
        else:
            copiar = texto
            aviso = ("%s no recibe un primer mensaje al abrir: tu texto quedó copiado, pégalo ahí." % motor_de(a))
    return {"argv": argv, "copiar": copiar, "aviso": aviso, "agente": op["agente"], "texto": texto,
            "motor": a.get("mid") or ""}


# ── los datos (reales; las pruebas y las capturas los cambian) ─────────────────
EJEMPLO = [
    {"id": "zenith", "n": "Zenith", "c": "#ff4fa3", "f": "nube", "mid": "claude-code", "st": "trabaja", "uso": 41},
    {"id": "turing", "n": "Turing", "c": "#3fbf7f", "f": "pico", "mid": "codex", "st": "termino"},
    {"id": "argus", "n": "Argus", "c": "#3b82f6", "f": "cuadrito", "mid": "kiro", "st": "libre"},
    {"id": "alba", "n": "Alba", "c": "#e7a43a", "f": "gatito", "mid": "hermes", "st": "duerme"},
    {"id": "doc", "n": "Doc", "c": "#8b5cf6", "f": "fantasma", "mid": "opencode", "st": "pregunta"},
]


def datos_ejemplo():
    """Los agentes de la maqueta (las capturas los usan para compararse con ella). No son datos reales."""
    ag = [dict(a) for a in EJEMPLO]
    return {"agentes": ag, "preguntas": [{"agente": 4, "texto": "¿Publico la guía nueva?"}],
            "terminados": [{"agente": 1, "texto": "arregló el instalador"}],
            "entrega": {"memoria": 12, "skills": 8, "sesion": True}}


#: Lo que cuenta como «acaba de terminar» y como «sigue abierto» en el registro (s).
TERMINO_S = 15 * 60
VIVO_S = 12 * 3600


def _ts(e):
    try:
        import datetime as _dt
        return _dt.datetime.strptime(str(e.get("ts")), "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=_dt.timezone.utc).timestamp()
    except ValueError:
        return 0.0


def _corto(s, n=40):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def estado_de(brain, ahora=None):
    """El estado del agente por su registro de eventos (todas sus pestañas recientes): «pregunta» (con la pregunta de
    una skill o un permiso en su terminal), «trabaja», «termino» (con lo último que dijo), «libre» o «duerme».
    → (st, texto)."""
    from arquitectura import registro
    ahora = time.time() if ahora is None else ahora
    vistos = []
    for ruta in glob.glob(os.path.join(registro.carpeta(brain), "*.jsonl")):
        try:
            if ahora - os.path.getmtime(ruta) > VIVO_S:
                continue
        except OSError:
            continue
        ev = registro.leer(brain, os.path.basename(ruta)[:-len(".jsonl")])[0]
        if ev:
            vistos.append((registro.estado(ev), ev))
    for est, _ev in vistos:                          # la pregunta de una skill dice algo: va primero
        if est.get("pregunta"):
            return "pregunta", _corto(est["pregunta"].get("pregunta"), 44)
    if any(est.get("estado") == "esperando_permiso" for est, _ev in vistos):
        return "pregunta", ""
    if any(est.get("estado") in ("pensando", "usando") for est, _ev in vistos):
        return "trabaja", ""
    fin = [(_ts(e), (e.get("datos") or {}).get("last_assistant_message") or "")
           for _est, ev in vistos for e in ev if e.get("momento") == "turn_end"]
    if fin:
        t, txt = max(fin)
        if ahora - t < TERMINO_S:
            return "termino", _corto(txt.strip().splitlines()[0] if txt.strip() else "", 40)
    if any(est.get("estado") in ("abierto", "listo") for est, _ev in vistos):
        return "libre", ""
    return "duerme", ""


def _uso(agente, motor):
    """El % de la ventana de 5 h que lleva su motor, si su motor lo deja ver; None si no."""
    try:
        if motor == "claude-code":
            import localhost_front
            u = (localhost_front.uso(agente) or {}).get("uso") or {}
            return u.get("sesion")
        if motor == "codex":
            from engines import codex
            snap = codex.rate_limit_snapshot() or {}
            p = snap.get("primary") or {}
            if p.get("resets_at") and float(p["resets_at"]) <= time.time():
                return None                            # ya se renovó: ese % ya no es de ahora
            v = p.get("used_percent")
            return jsround(float(v)) if v is not None else None
    except Exception:
        return None
    return None


def _memoria(brain):
    try:
        with open(os.path.join(brain, "STATE", "MEMORY.md"), encoding="utf-8") as fh:
            return sum(1 for ln in fh if ln.lstrip().startswith("- "))
    except OSError:
        return None


def _skills(brain):
    try:
        from arquitectura import skills_cerebro
        return len(skills_cerebro.indice(brain) or ())
    except Exception:
        return None


def _sesion(motor):
    try:
        import motores_logica as ET
        hit = ET._SESSION_CACHE.get(motor)
        return bool(hit and hit[1] is True)
    except Exception:
        return False


def datos_reales():
    """Los agentes del registro con su monito (localhost_front.inicio: lo mismo que la página), su motor, su uso y su
    estado; lo que te preguntan y lo que terminaron."""
    import localhost_front
    ini = localhost_front.inicio()
    cerebros = localhost_front._cerebros()
    agentes, preguntas, terminados = [], [], []
    for x in ini.get("agentes") or []:
        brain = cerebros.get(x.get("id")) or ""
        st, txt = estado_de(brain) if brain else ("duerme", "")
        a = {"id": x["id"], "n": x.get("nombre") or x["id"], "c": x.get("color") or "#ffffff",
             "f": x.get("forma") or "bolita", "mid": x.get("motor") or "", "st": st, "brain": brain}
        a["uso"] = _uso(a["id"], a["mid"])
        i = len(agentes)
        agentes.append(a)
        if st == "pregunta":
            preguntas.append({"agente": i, "texto": txt})
        elif st == "termino":
            terminados.append({"agente": i, "texto": txt})
    return {"agentes": agentes, "preguntas": preguntas, "terminados": terminados}


def datos_entrega(a):
    """Lo que se ve mientras se abre su motor: su memoria, sus skills y si su sesión ya se sabe iniciada."""
    brain = a.get("brain") or ""
    return {"memoria": _memoria(brain) if brain else None, "skills": _skills(brain) if brain else None,
            "sesion": _sesion(a.get("mid") or "")}


# ── las pantallas ──────────────────────────────────────────────────────────────
def barra(T, agentes, sel, hora, derecha=None):
    """La barra de estado. `derecha`: lo que va antes de la hora (por omisión, el motor del agente y su uso)."""
    N = T.w < ANCHO_MIN
    T.fill(0, 0, T.w, 1, BARRA_BG)
    a = agentes[sel] if agentes else None
    x = T.put(1, 0, "❯", a["c"] if a else C["tx2"], True)
    x = T.put(x + 1, 0, "workspace", C["tx"], True) + 2
    for i, b in enumerate(agentes):
        on = i == sel
        x = T.put(x + 1, 0, str(i + 1), b["c"] if on else (NUM_DORMIDO if b.get("st") == "duerme" else C["tx3"]), on)
    if N or not a:
        derecha = hora
    elif derecha is not None:
        derecha = derecha + "   " + hora
    else:
        derecha = motor_de(a) + (" · %d%%" % a["uso"] if a.get("uso") is not None else "") + "   " + hora
    T.right(T.w - 2, 0, derecha, C["tx3"])


def teclas(T, y, keys):
    x = 1 if T.w < ANCHO_MIN else 2
    for k, lab in keys:
        x = T.key(x, y, k, lab)


def _ventana(n, sel, cabe):
    """Qué agentes caben en la fila (los de alrededor del elegido)."""
    if n <= cabe:
        return list(range(n))
    i0 = max(0, min(sel - cabe // 2, n - cabe))
    return list(range(i0, i0 + cabe))


def pantalla_principal(w, h, d, texto="", sel=0, op=0, fase=None, hora="00:00", aviso=""):
    """La pantalla principal (PANT['b-main'] de la maqueta) con datos `d`. `fase`: segundos desde que se eligió al
    agente `sel` (su brinco), o None. `aviso`: una línea arriba de las teclas (p. ej., por qué no hay conversación
    directa)."""
    T = Term(w, h)
    T.fill(0, 0, w, h, T_BG)
    if w < MIN_W or h < MIN_H:
        T.center(0, w, h // 2, "Agranda la ventana", C["tx2"])
        return T
    N, ag = w < ANCHO_MIN, d["agentes"]
    if not ag:
        barra(T, ag, 0, hora)
        T.center(0, w, h // 2, "Todavía no tienes agentes: agrégalos desde `workspace agentes`.", C["tx2"])
        return T
    t = str(texto or "")
    dest = destino(t, ag, sel) if t.strip() else sel
    barra(T, ag, dest, hora)
    S, sp = 8, (9 if N else 13)
    vis = _ventana(len(ag), dest, (w - 1) // sp)
    x0 = (w - sp * len(vis)) // 2 + (sp - S) // 2 + (1 if N else 0)
    y = 3 if N else 4
    for k, i in enumerate(vis):
        a, x = ag[i], x0 + k * sp
        on = i == dest
        monito(T, a, x, y, S, fase=fase if on else None, st="libre" if on else None,
               sin_signo=on or a.get("st") != "pregunta")
        T.center(x - 2, S + 4, y + S // 2 + 1, a["n"], C["tx"] if on else C["tx3"], on)
        if on:
            T.center(x - 2, S + 4, y + S // 2 + 2, "━━━━" if N else "━━━━━━", a["c"])
    if vis[0] > 0:
        T.put(0, y + 2, "‹", C["tx3"])
    if vis[-1] < len(ag) - 1:
        T.put(w - 1, y + 2, "›", C["tx3"])
    bw = w - 2 if N else min(70, w - 4)
    bx, by = (w - bw) // 2, (10 if N else 12)
    T.box(bx, by, bw, 3, C["tx3"] if t else C["line"])
    col = ag[dest]["c"]
    e = T.put(bx + 2, by + 1, "❯", col, True)
    mx = bw - 6
    vista = t if len(t) <= mx else "…" + t[-(mx - 1):]
    if t:
        e = T.put(e + 1, by + 1, vista, C["tx"])
        T.put(e, by + 1, "▏", C["tx"])
    else:
        T.put(e + 1, by + 1, "Escribe lo que quieras…", C["tx3"])
    lista = opciones(t, ag, sel, d.get("preguntas") or (), d.get("terminados") or ())
    ry, fin = by + 4, h - 3
    paso = 3 if N else 2
    op = max(0, min(op, len(lista) - 1)) if lista else 0
    for n, r in enumerate(lista):
        yy = ry + n * paso
        if yy + (1 if N else 0) > fin:
            break
        on, c2 = n == op, ag[r["agente"]]["c"]
        if not N:
            if on:
                T.fill(bx, yy, bw, 1, C["lit"])
                T.put(bx, yy, "▌", c2)
            T.put(bx + 3, yy, r["titulo"], C["tx"] if on else C["tx2"], on)
            T.put(bx + 32, yy, _corto(r["detalle"], bw - 32 - (10 if on else 2)), C["tx3"])
            if on:
                T.right(bx + bw - 4, yy, "Enter", C["tx3"])
                T.put(bx + bw - 2, yy, "›", c2, True)
        else:
            if on:
                T.fill(bx, yy, bw, 2, C["lit"])
                T.put(bx, yy, "▌", c2)
                T.put(bx, yy + 1, "▌", c2)
            T.put(bx + 2, yy, _corto(r["titulo"], bw - 5), C["tx"] if on else C["tx2"], on)
            T.put(bx + 2, yy + 1, _corto(r["detalle"], bw - 4), C["tx3"])
            if on:
                T.put(bx + bw - 2, yy, "›", c2, True)
    if aviso:
        T.center(0, w, h - 3, _corto(aviso, w - 4), C["tx2"])
    borra = "borra" if t else "sale"
    if not N:
        teclas(T, h - 2, [("Enter", "manda"), ("Tab", "otro agente"), ("↑↓", "elige"), ("Esc", borra)])
    else:
        teclas(T, h - 2, [("Enter", "manda"), ("Tab", "agente"), ("Esc", borra)])
    T.flat()
    return T


def pantalla_entrega(w, h, d, p, ent=None, avance=9.0, hora="00:00"):
    """La pantalla secundaria (PANT['b-entrega']): el hub arma la entrega y abre el motor oficial. `p`: el plan;
    `ent`: datos_entrega; `avance`: segundos desde que empezó (los pasos aparecen uno a uno)."""
    T = Term(w, h)
    T.fill(0, 0, w, h, T_BG)
    ag = d["agentes"]
    a = ag[p["agente"]]
    if p.get("motor"):
        a = dict(a, mid=p["motor"])                  # el motor con el que se abre (el de la conversación directa)
    m = motor_de(a)
    barra(T, ag, p["agente"], hora, derecha=m if a.get("mid") != ag[p["agente"]].get("mid") else None)
    if w < MIN_W or h < MIN_H:
        T.center(0, w, h // 2, "Abriendo %s…" % m, C["tx2"])
        return T
    N = w < ANCHO_MIN
    S = 12 if N else 16
    monito(T, a, (w - S) // 2, 4, S, st="trabaja", mira=1)
    y = 12 if N else 14
    if p.get("sesion"):
        sub = " retoma «%s» en %s" % (_corto(p["sesion"], 30), m)      # hub_directo: una de sus sesiones (^S)
    elif p.get("texto") and not p.get("copiar"):
        sub = " abre %s con tu mensaje" % m
    elif p.get("copiar"):
        sub = " abre %s · tu texto, copiado" % m
    else:
        sub = " abre %s" % m
    total = len(a["n"]) + len(sub)
    x = (w - total) // 2
    x = T.put(x, y, a["n"], C["tx"], True)
    T.put(x, y, sub, C["tx2"])
    if p.get("texto"):
        T.center(0, w, y + 1, "«%s»" % _corto(p["texto"], w - 8), C["tx3"])
    ent = ent or {}
    L = []
    if ent.get("memoria") is not None:
        L.append(("Su memoria", "%d notas" % ent["memoria"]))
    if ent.get("skills") is not None:
        L.append(("Sus skills", str(ent["skills"])))
    if ent.get("sesion"):
        L.append((m, "sesión iniciada"))
    L.append(("Abriendo " + m, ""))
    bx = 6 if N else 30
    for i, (lab, det) in enumerate(L):
        yy = y + 3 + i
        if avance <= PASO_ENTREGA_S * (i + 0.5):          # uno a uno; el último antes de que se abra (ENTREGA_S)
            continue
        if i == len(L) - 1:
            T.put(bx, yy, "›", a["c"], True)
            T.put(bx + 2, yy, lab + "...", C["tx"], True)
        else:
            T.put(bx, yy, "✓", C["tx3"])
            e = T.put(bx + 2, yy, lab, C["tx2"])
            T.put(e + 1, yy, "· " + det, C["tx3"])
    if p.get("aviso"):
        T.center(0, w, y + 8, _corto(p["aviso"], w - 4), C["tx2"])
    if not N:
        T.center(0, w, y + 9, m + " se abre aquí, a pantalla completa. Al salir, vuelves al hub.", C["tx3"])
    else:
        T.center(0, w, y + 9, m + " se abre aquí, a pantalla completa.", C["tx3"])
        T.center(0, w, y + 10, "Al salir, vuelves al hub.", C["tx3"])
    teclas(T, h - 2, [("Esc", "cancelar")])
    T.flat()
    return T


# ── la app: teclas, entrega y vuelta ───────────────────────────────────────────
class Hub:
    """El estado de la pantalla y lo que hace cada tecla (sin terminal: las pruebas lo manejan con teclas)."""

    def __init__(self, datos, lanzar=None, reloj=time.monotonic):
        self.d = datos
        self.texto, self.sel, self.op = "", 0, 0
        self.brinco_t = None
        self.lanzar = lanzar
        self.reloj = reloj

    def _elegir(self, i):
        n = len(self.d["agentes"])
        if n:
            self.sel = i % n
            self.op = 0
            self.brinco_t = self.reloj()

    def fase(self):
        if self.brinco_t is None:
            return None
        f = self.reloj() - self.brinco_t
        return f if f < BRINCO_S else None

    def lista(self):
        return opciones(self.texto, self.d["agentes"], self.sel, self.d.get("preguntas") or (),
                        self.d.get("terminados") or ())

    def tecla(self, k):
        """→ None (sigue), «salir», o el plan de una opción (para entregarlo al motor)."""
        if isinstance(k, Raton) or k == "f1":         # esta Paleta no usa el mouse ni la ayuda
            return None
        if isinstance(k, Pegado):                     # antes que nada: pegar «esc» no es la tecla Esc
            self.texto, self.op = self.texto + " ".join(k.split()), 0
            return None
        if k == "esc":
            if not self.texto:
                return "salir"
            self.texto, self.op = "", 0
        elif k == "ctrl-c":
            return "salir"
        elif k == "tab":
            self._elegir(self.sel + 1)
        elif k == "shift-tab":
            self._elegir(self.sel - 1)
        elif k == "arriba":
            self.op = max(0, self.op - 1)
        elif k == "abajo":
            self.op = min(max(0, len(self.lista()) - 1), self.op + 1)
        elif k == "borrar":
            self.texto, self.op = self.texto[:-1], 0
        elif k == "ctrl-u":
            self.texto, self.op = "", 0
        elif k == "enter":
            lista = self.lista()
            if lista:
                return plan(lista[min(self.op, len(lista) - 1)], self.d["agentes"])
        elif len(k) == 1 and (k.isprintable()):
            antes = destino(self.texto, self.d["agentes"], self.sel) if self.texto.strip() else self.sel
            self.texto += k
            self.op = 0
            ahora = destino(self.texto, self.d["agentes"], self.sel)
            if ahora != antes:                        # nombraste a otro agente: brinca el que lo va a recibir
                self.brinco_t = self.reloj()
        return None


def copiar(texto):
    """Al portapapeles del sistema (pbcopy, clip, wl-copy o xclip). → True si quedó."""
    for cmd in (["pbcopy"], ["clip"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        exe = shutil.which(cmd[0])
        if not exe:
            continue
        try:
            kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
            r = subprocess.run([exe] + cmd[1:], input=texto.encode("utf-16-le" if cmd[0] == "clip" else "utf-8"),
                               timeout=5, **kw)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def _lanzar_de_verdad(p):
    """El lanzador de siempre (dispatch), en esta terminal; al salir del motor se vuelve al hub. Sin
    WORKSPACE_FROM_HUB: esa marca es del hub de siempre (que se REEMPLAZA por dispatch), y con ella cancelar el menú
    de sesiones de su motor abría un hub nuevo DENTRO de este (claude_code.back_to_hub); aquí este hub sigue vivo y
    se vuelve a él solo."""
    env = dict(os.environ)
    env.pop("WORKSPACE_FROM_HUB", None)
    env.pop("WORKSPACE_HUB_S1_AVISO_VISIBLE", None)
    env["WORKSPACE_HUB_S1"] = "1"           # su menú de sesiones: S-1 (hub_s1; el hub de siempre no lo pide)
    if p.get("s1_hub"):                     # eligió en S-1 del hub: «Abriendo…» ya se ve (sin «Cargando…» ni letrero)
        env["WORKSPACE_HUB_S1_AVISO_VISIBLE"] = "1"
    env.pop("WORKSPACE_HUB_S1_CACHE", None)
    precarga = p.get("sesiones_precargadas")
    if not precarga:
        return subprocess.run(p["argv"], env=env).returncode
    try:
        temporal = tempfile.TemporaryDirectory(prefix="workspace-s1-")
    except OSError:
        return subprocess.run(p["argv"], env=env).returncode
    with temporal as directorio:
        # La lista puede contener citas. Al hijo solo se le pasa la ruta del archivo privado.
        ruta = os.path.join(directorio, "sesiones.json")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(precarga, f, ensure_ascii=False)
            env["WORKSPACE_HUB_S1_CACHE"] = ruta
        except OSError:
            pass
        return subprocess.run(p["argv"], env=env).returncode


#: Las teclas de control que el hub usa, por su byte (Ctrl+O = abrir en su motor, Ctrl+E = el motor de la
#: conversación, Ctrl+S = sus sesiones). En Mac, Ctrl+O es «descartar salida» de la terminal (IEXTEN) y Ctrl+S, en
#: todas, «detener la salida» (IXON): _crudo() los apaga.
_CONTROL = {"\r": "enter", "\n": "enter", "\t": "tab", "\x7f": "borrar", "\x08": "borrar", "\x03": "ctrl-c",
            "\x15": "ctrl-u", "\x0f": "ctrl-o", "\x05": "ctrl-e", "\x13": "ctrl-s", "\x02": "ctrl-b",
            # H4-a: las pestañas de la conversación (Ctrl+T abre «+», Ctrl+W cierra la que ves)
            "\x14": "ctrl-t", "\x17": "ctrl-w", "\x01": "ctrl-a"}
#: Las secuencias de escape que se entienden (las demás se ignoran).
_SECUENCIAS = ((b"\x1b[A", "arriba"), (b"\x1bOA", "arriba"), (b"\x1b[B", "abajo"), (b"\x1bOB", "abajo"),
               (b"\x1b[C", "derecha"), (b"\x1bOC", "derecha"), (b"\x1b[D", "izquierda"), (b"\x1bOD", "izquierda"),
               (b"\x1b[5~", "repag"), (b"\x1b[6~", "avpag"), (b"\x1b[Z", "shift-tab"),
               # H4-a: Ctrl+←/→ cambian de pestaña
               (b"\x1b[1;5C", "ctrl-derecha"), (b"\x1b[1;5D", "ctrl-izquierda"),
               (b"\x1bOP", "f1"), (b"\x1b[11~", "f1"),
               # la terminal avisa si está al frente (hub_directo la pide con «\x1b[?1004h»: su reposo)
               (b"\x1b[I", "foco+"), (b"\x1b[O", "foco-"))


class Pegado(str):
    """Lo que pegaste de una vez (el «bracketed paste» de la terminal): su texto entero, con sus saltos."""


class Raton(object):
    """Un evento del mouse (SGR 1006), aparte de las teclas para que nunca se confunda con una. `tipo`: «baja»,
    «sube», «mueve», «arrastra», «rueda_arriba» o «rueda_abajo»; `x`, `y` desde 0; `boton`: 0 izquierdo, 1 medio,
    2 derecho; `mods`: shift 4, alt 8, ctrl 16."""
    __slots__ = ("tipo", "x", "y", "mods", "boton")

    def __init__(self, tipo, x, y, mods=0, boton=0):
        self.tipo, self.x, self.y, self.mods, self.boton = tipo, x, y, mods, boton

    def _t(self):
        return (self.tipo, self.x, self.y, self.mods, self.boton)

    def __eq__(self, otro):
        return isinstance(otro, Raton) and self._t() == otro._t()

    def __ne__(self, otro):
        return not self == otro

    def __hash__(self):
        return hash(self._t())

    def __repr__(self):
        return "Raton(%r, %d, %d%s)" % (self.tipo, self.x, self.y, ", boton=%d" % self.boton if self.boton else "")


#: Prender el mouse: clic, arrastre, movimiento y la codificación SGR (la que no se rompe con más de 223 columnas).
#: Apagarlo: al revés. Un motor que abre con el mouse prendido recibe basura al mover el mouse: se apaga SIEMPRE
#: antes de entregarle la terminal y al salir.
RATON_ON = "\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1006h"
RATON_OFF = "\x1b[?1006l\x1b[?1003l\x1b[?1002l\x1b[?1000l"
_SGR_RATON = re.compile(rb"\x1b\[<(\d{1,4});(\d{1,4});(\d{1,4})([Mm])")
#: Una secuencia CSI entera (con «<», la del mouse SGR); si el búfer empieza con «\x1b[» y esto no casa, llegó cortada.
_CSI_ENTERA = re.compile(rb"\x1b\[[0-9;?<]*[ -/]*[@-~]")


def raton_posible(env=None):
    """¿Se prende el mouse? No con WORKSPACE_MOUSE=0, con TERM dumb o linux (la consola de texto) ni sin tty. En
    Windows, si la entrada y la salida son una consola de verdad (Windows Terminal o conhost): el teclado del hub la
    lee con consola_windows, que entiende el clic (y además el teclado dice si la consola aceptó el modo:
    `_Teclado.raton_ok`)."""
    env = os.environ if env is None else env
    if str(env.get("WORKSPACE_MOUSE") or "").strip() == "0":
        return False
    if str(env.get("TERM") or "").strip().lower() in ("dumb", "linux"):
        return False
    if os.name == "nt":
        try:
            import _console
            return _console.is_console(sys.stdin) and _console.is_console(sys.stdout)
        except Exception:
            return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def _evento_raton(m):
    b, x, y = int(m.group(1)), max(0, int(m.group(2)) - 1), max(0, int(m.group(3)) - 1)
    mods = b & (4 | 8 | 16)
    if b & 64:
        if b & 3 >= 2:
            return None                                  # la rueda de lado: se ignora
        return Raton("rueda_abajo" if b & 1 else "rueda_arriba", x, y, mods)
    if b & 32:                                       # movimiento: sin botón («mueve») o con uno apretado
        return Raton("mueve", x, y, mods) if b & 3 == 3 else Raton("arrastra", x, y, mods, b & 3)
    return Raton("baja" if m.group(4) == b"M" else "sube", x, y, mods, b & 3)


_PEGAR_INI, _PEGAR_FIN = b"\x1b[200~", b"\x1b[201~"


def _crudo(fd):
    """cbreak (sin eco, tecla por tecla), sin IEXTEN (Ctrl+O y Ctrl+V llegan al hub) y sin IXON (Ctrl+S llega, en vez
    de congelar la terminal). Al soltar se devuelve todo como estaba."""
    import termios
    import tty
    tty.setcbreak(fd)
    try:
        at = termios.tcgetattr(fd)
        at[0] &= ~termios.IXON
        at[3] &= ~termios.IEXTEN
        termios.tcsetattr(fd, termios.TCSADRAIN, at)
    except (termios.error, AttributeError):
        pass


class _Teclado:
    """Las teclas de la terminal, en crudo (POSIX: termios; Windows: la consola con consola_windows, que manda los
    mismos bytes que una terminal de Mac, también el mouse; si esa consola no se deja, msvcrt como antes, sin mouse).
    """
    win = False
    buf = b""
    fd = None
    consola = None                                   # Windows: consola_windows.Consola (None: msvcrt)

    def __init__(self):
        self.win = os.name == "nt"
        self.buf = b""
        if self.win:
            try:
                import consola_windows
                self.consola = consola_windows.Consola.abrir()
            except Exception:
                self.consola = None
        else:
            import termios
            self.fd = sys.stdin.fileno()
            self.viejo = termios.tcgetattr(self.fd)
            _crudo(self.fd)

    @property
    def raton_ok(self):
        """¿Puede llegar el mouse? En Windows, solo si la consola aceptó el modo (con msvcrt no hay mouse)."""
        return not self.win or self.consola is not None

    def raton(self, prender):
        """El hub prende o apaga el mouse (además de las secuencias que escribe): en Windows, los registros de mouse
        de la consola y la edición rápida al revés. → True si quedó así."""
        if self.consola is None:
            return not self.win
        return self.consola.poner(prender)

    def soltar(self):
        if self.consola is not None:
            self.consola.soltar()                    # el modo de la consola de antes, exacto
        elif not self.win:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.viejo)

    def tomar(self):
        if self.consola is not None:
            self.consola.tomar()
        elif not self.win:
            _crudo(self.fd)

    def _llenar(self, espera, n=1024):
        """Lo que llegue en hasta `espera` s (None: nada; espera=None: espera a que llegue). POSIX: el fd; Windows:
        los bytes que arma consola_windows con lo que llegó a la consola."""
        if self.consola is not None:
            return self.consola.leer(espera)
        if espera is not None:
            import select
            r, _, _ = select.select([self.fd], [], [], espera)
            if not r:
                return None
        return os.read(self.fd, n)

    def leer(self, espera):
        """La siguiente tecla («enter», «tab», «arriba»… o un carácter), o None si no hubo en `espera` s."""
        if self.win and self.consola is None:
            import msvcrt
            fin = time.monotonic() + espera
            while not msvcrt.kbhit():
                if time.monotonic() >= fin:
                    return None
                time.sleep(0.02)
            c = msvcrt.getwch()
            if c in ("\x00", "\xe0"):
                # H4-a: Ctrl+←/→ («s», «t») y Alt+1…9 (sus códigos 120-128) cambian de pestaña
                return dict({"H": "arriba", "P": "abajo", "M": "derecha", "K": "izquierda", "I": "repag",
                             "Q": "avpag", ";": "f1", "s": "ctrl-izquierda", "t": "ctrl-derecha"},
                            **{chr(120 + i): "alt-%d" % (i + 1) for i in range(9)}).get(msvcrt.getwch(), "")
            return dict(_CONTROL, **{"\x1b": "esc"}).get(c, c)
        if not self.buf:
            m = self._llenar(espera)
            if m is None:
                return None
            self.buf += m
        if self.buf.startswith(b"\x1b"):
            if len(self.buf) == 1:                   # ¿Esc solo, o el principio de una secuencia?
                self.buf += self._llenar(0.03) or b""
            if self.buf.startswith(b"\x1b[") and not _CSI_ENTERA.match(self.buf):
                self._completar(lambda b: bool(_CSI_ENTERA.match(b)))     # llegó cortada: 30 ms más
            if self.buf.startswith(_PEGAR_INI):      # el pegado primero: un «\x1b[<» adentro es texto
                fin = time.monotonic() + 2.0
                while _PEGAR_FIN not in self.buf and time.monotonic() < fin:
                    self.buf += self._llenar(0.2, 65536) or b""
                cuerpo, _sep, self.buf = self.buf[len(_PEGAR_INI):].partition(_PEGAR_FIN)
                return Pegado(cuerpo.decode("utf-8", "replace"))
            if self.buf.startswith(b"\x1b[<"):       # el mouse ANTES que la regex genérica (que no acepta «<»)
                return self._raton()
            if self.buf.startswith(b"\x1b[M"):       # X10 viejo: 6 bytes, consumidos ANTES de decodificar
                self._completar(lambda b: len(b) >= 6)
                self.buf = self.buf[6:]
                return ""
            for sec, k in _SECUENCIAS:
                if self.buf.startswith(sec):
                    self.buf = self.buf[len(sec):]
                    return k
            m = re.match(rb"\x1b([1-9])", self.buf)
            if m:                                    # H4-a: Alt+1…9 (Esc y su número) va a esa pestaña
                self.buf = self.buf[2:]
                return "alt-" + m.group(1).decode("ascii")
            m = re.match(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1bO.", self.buf)
            if m:                                    # otra secuencia (flechas laterales, F1…): se ignora
                self.buf = self.buf[m.end():]
                return ""
            self.buf = self.buf[1:]
            return "esc"
        b0 = self.buf[0]
        n = 1 if b0 < 0x80 else 2 if b0 >> 5 == 6 else 3 if b0 >> 4 == 14 else 4
        while len(self.buf) < n:
            m = self._llenar(None if self.consola is None else 0.05)
            if not m and self.consola is not None:
                break                                # Windows manda el carácter entero: nunca se queda a medias
            self.buf += m
        c, self.buf = self.buf[:n].decode("utf-8", "replace"), self.buf[n:]
        return _CONTROL.get(c, c)

    def _completar(self, listo, tope=0.03, maximo=32):
        """Lee lo que falta de una secuencia que llegó cortada: hasta `tope` s y `maximo` bytes."""
        fin = time.monotonic() + tope
        while not listo(self.buf) and len(self.buf) < maximo:
            m = self._llenar(max(0.0, fin - time.monotonic()))
            if not m:
                return
            self.buf += m

    def _raton(self):
        """Un reporte SGR del mouse → Raton. Si no está entero, se tira. Varios «mueve» seguidos: solo el último."""
        m = _SGR_RATON.match(self.buf)
        if not m:
            self.buf = self.buf[re.match(rb"\x1b\[<[0-9;]*[Mm]?", self.buf).end():]
            return ""
        ev, self.buf = _evento_raton(m), self.buf[m.end():]
        while ev is not None and ev.tipo == "mueve":
            m2 = _SGR_RATON.match(self.buf)
            ev2 = _evento_raton(m2) if m2 else None
            if ev2 is None or ev2.tipo != "mueve":
                break
            ev, self.buf = ev2, self.buf[m2.end():]
        return ev if ev is not None else ""

    def vaciar(self, quieto=0.05, tope=0.3):
        """Tira lo que quedó por leer (los reportes del mouse que la terminal mandó antes de apagarlo): lo de antes de
        entregarle la terminal a un motor no es para él."""
        self.buf = b""
        if self.consola is not None:
            self.consola.vaciar()
            return
        if self.win:
            return
        import select
        fin = time.monotonic() + tope
        while time.monotonic() < fin:
            r, _, _ = select.select([self.fd], [], [], quieto)
            if not r:
                break
            try:
                os.read(self.fd, 65536)
            except OSError:
                break
        try:
            import termios
            termios.tcflush(self.fd, termios.TCIFLUSH)
        except Exception:
            pass


#: Terminal.app pinta color real (24 bits) desde la 2.15 (build 470, macOS 26); antes, solo 256 colores (y en una
#: Terminal.app vieja, lo de 24 bits salía en colores equivocados).
TERMINAL_APP_COLOR_REAL = (470,)


def _build(texto):
    try:
        return tuple(int(x) for x in str(texto or "").strip().split(".")[:1])
    except ValueError:
        return ()


def _colores():
    """«24» con color real (COLORTERM truecolor/24bit, o WORKSPACE_COLOR=24); si no, «256». Terminal.app: color real
    desde su build 470 (TERM_PROGRAM_VERSION); la de antes, 256."""
    pedido = str(os.environ.get("WORKSPACE_COLOR") or "").strip()
    if pedido in ("24", "256"):
        return pedido
    if terminal_app():
        b = _build(os.environ.get("TERM_PROGRAM_VERSION"))
        return "24" if b and b >= TERMINAL_APP_COLOR_REAL else "256"
    return "24" if str(os.environ.get("COLORTERM") or "").lower() in ("truecolor", "24bit") else "256"


class Pintor:
    """Pinta una pantalla en la terminal reescribiendo SOLO lo que cambió desde la anterior: de cada fila que cambió,
    el tramo entre su primera y su última celda distinta. Un cuadro de un monito toca solo su recuadro (en la Terminal
    de Mac, repintar todo a varios cuadros por segundo parpadeaba), y en el hub lateral, donde el riel y la
    conversación comparten filas, un monito que piensa no reescribe la conversación de al lado. La primera vez, o si
    cambió el tamaño, todo. `bytes`: lo que escribió el último cuadro."""

    def __init__(self, salida=None):
        self.salida = salida or sys.stdout
        self.ant, self.tam, self.col = None, None, None
        self.bytes = 0

    def olvidar(self):
        """La próxima vez, todo (al volver de un motor, la terminal ya no tiene lo de antes)."""
        self.ant = None

    def pintar(self, T, colores):
        """→ cuántas filas se escribieron."""
        filas = T.firma()
        todo = self.ant is None or self.tam != (T.w, T.h) or self.col != colores
        partes, n = ["\x1b[0m\x1b[2J"] if todo else [], 0
        for y, f in enumerate(filas):
            if todo:
                partes.append("\x1b[%d;1H%s" % (y + 1, T.tramo(y, 0, T.w, colores)))
                n += 1
                continue
            a = self.ant[y]
            if f == a:
                continue
            x0, x1 = 0, T.w - 1
            while f[x0] == a[x0]:
                x0 += 1
            while f[x1] == a[x1]:
                x1 -= 1
            if f[x0][0] == "" and x0 > 0:               # en la mitad de un carácter ancho: desde su principio
                x0 -= 1
            if x1 + 1 < T.w and f[x1 + 1][0] == "":     # termina en un carácter ancho: con su segunda mitad
                x1 += 1
            partes.append("\x1b[%d;%dH%s" % (y + 1, x0 + 1, T.tramo(y, x0, x1 + 1, colores)))
            n += 1
        sale = "".join(partes)
        if sale:
            self.salida.write(sale)
            self.salida.flush()
        self.bytes = len(sale.encode("utf-8"))
        self.ant, self.tam, self.col = filas, (T.w, T.h), colores
        return n


def _pintar(T, colores, pintor=None):
    (pintor or Pintor()).pintar(T, colores)


#: Cada cuánto se releen los datos sin que toques nada (s), y los cuadros por segundo del brinco.
DATOS_S = 3.0
CUADRO_S = 1 / 16.0
#: Cuánto se ve la entrega antes de abrir el motor (con aviso, un poco más para leerlo), y cada cuánto aparece uno
#: de sus pasos (4 pasos: el último a los 0,63 s).
ENTREGA_S, ENTREGA_AVISO_S = 0.9, 2.2


def correr(datos=datos_reales, lanzar=_lanzar_de_verdad, teclado=None, aviso=""):
    """El hub en esta terminal hasta que sales (Esc sin texto, o Ctrl+C). → 0. None si no hay terminal.
    `teclado`: de dónde salen las teclas (por omisión, la terminal en crudo; las pruebas dan uno falso).
    `aviso`: una línea que se ve hasta la primera tecla (hub_directo: por qué no hay conversación directa)."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None
    if os.name == "nt":
        os.system("")
    colores = _colores()
    hub = Hub(datos())
    tec = teclado or _Teclado()
    pintor = Pintor()
    leidos = time.monotonic()
    sys.stdout.write("\x1b[?1049h\x1b[?25l")
    try:
        while True:
            w, h = shutil.get_terminal_size((88, 30))
            pintor.pintar(pantalla_principal(w, h, hub.d, hub.texto, hub.sel, hub.op, hub.fase(),
                                             time.strftime("%H:%M"), aviso), colores)
            k = tec.leer(CUADRO_S if hub.fase() is not None else 1.0)
            if k is None:
                if time.monotonic() - leidos > DATOS_S:
                    try:
                        nuevos = datos()
                        if [a["id"] for a in nuevos["agentes"]] != [a["id"] for a in hub.d["agentes"]]:
                            hub.sel = 0
                        hub.d = nuevos
                    except Exception:
                        pass
                    leidos = time.monotonic()
                continue
            if not k:
                continue
            aviso = ""
            r = hub.tecla(k)
            if r == "salir":
                return 0
            if isinstance(r, dict):
                if not _entregar(hub.d, r, tec, colores, lanzar, pintor):
                    continue
                hub.texto, hub.op = "", 0
                try:
                    hub.d = datos()
                except Exception:
                    pass
                leidos = time.monotonic()
    except KeyboardInterrupt:
        return 0
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        tec.soltar()


def _entregar(d, p, tec, colores, lanzar, pintor=None, raton=False, h1=False):
    """La pantalla de entrega (con Esc para cancelar) y el motor oficial, en esta terminal. `d`: los datos con sus
    agentes. `raton`: el hub tiene el mouse prendido (se apaga antes de entregar y se prende al volver).
    → True si se abrió."""
    pintor = pintor or Pintor()
    a = d["agentes"][p["agente"]]
    if p.get("motor"):
        a = dict(a, mid=p["motor"])
    if p.get("copiar") and not copiar(p["copiar"]):
        p["aviso"] = "%s no recibe un primer mensaje al abrir y no pude copiar tu texto: escríbelo ahí." % motor_de(a)
    if h1 and p.get("s1_hub"):             # S-1 en el hub (H2-a): su «Abriendo…» ya se ve; sin tarjeta de entrega
        espejo = p.pop("_espejo", None)
        _ceder(tec, lambda: lanzar(p), pintor, raton=raton, limpiar=False, espejo=espejo, colores=colores)
        return True
    if h1 and p.get("picker_s1"):
        _ceder(tec, lambda: lanzar(p), pintor, raton=raton, aviso=p.get("aviso"), limpiar=False)
        return True
    ent = datos_entrega(a)
    t0, tope = time.monotonic(), (ENTREGA_AVISO_S if p.get("aviso") else ENTREGA_S)
    while time.monotonic() - t0 < tope:
        w, h = shutil.get_terminal_size((88, 30))
        if h1:                             # el hub H-1: su tarjeta con el monito M-1 (hub_carga)
            import hub_carga
            pintor.pintar(hub_carga.entrega(w, h, a, motor_de(a), p.get("aviso") or "", time.monotonic() - t0),
                          colores)
        else:
            pintor.pintar(pantalla_entrega(w, h, d, p, ent, time.monotonic() - t0, time.strftime("%H:%M")),
                          colores)
        if tec.leer(0.1) == "esc":
            return False
    _ceder(tec, lambda: lanzar(p), pintor, raton, p.get("aviso"))
    return True


def _ceder(tec, fn, pintor, raton=False, aviso=None, limpiar=True, espejo=None, colores="256"):
    """Le presta la terminal a otro programa (un motor, el formulario «Agregar agente»): el mouse se apaga ANTES de
    salir de la pantalla alterna (y se tira lo que la terminal ya mandó), y se prende al volver. Pase lo que pase
    adentro, al volver todo queda como estaba.
    Mientras el otro tiene la terminal, un Ctrl+C es suyo: la terminal se lo manda a todo el grupo (también a este
    proceso, que espera), y sin esto el hub se cerraba con el Ctrl+C que cancelaba el menú de sesiones de su motor.
    Se usa un manejador que no hace nada (no SIG_IGN): al hacer exec, el hijo vuelve al de siempre.
    `espejo` (S-1 en el hub): la misma imagen se pinta en la pantalla principal al soltar la alterna, en la misma
    escritura: no se ve la terminal de antes y su programa toma la terminal sobre esa imagen (un solo borrado)."""
    out = sys.stdout
    if raton:
        out.write(RATON_OFF)
        out.flush()
        vaciar = getattr(tec, "vaciar", None)
        if vaciar:
            vaciar()
    if espejo is not None:
        filas = espejo.ansi(colores)
        out.write("\x1b[?2026h\x1b[0m\x1b[?1049l\x1b[2J\x1b[H" + "\r\n".join(filas[:-1]) +
                  "\x1b[0m\x1b[%d;1H\x1b[?25h\x1b[?2026l" % len(filas))   # (2026: de una vez donde se puede)
    else:
        out.write("\x1b[0m" + ("\x1b[2J\x1b[H" if limpiar else "") + "\x1b[?25h\x1b[?1049l")
    if aviso:
        out.write("WORKSPACE: %s\n" % aviso)
    out.flush()
    tec.soltar()
    viejo = _sigint(lambda _s, _f: None)
    try:
        return fn()
    finally:
        _sigint(viejo)
        tec.tomar()
        pintor.olvidar()
        out.write("\x1b[?1049h\x1b[?25l" + (RATON_ON if raton else ""))
        out.flush()


def _sigint(manejador):
    """Pone el manejador de SIGINT (solo en el hilo principal). → el de antes, o None si no se pudo."""
    import signal
    import threading
    if manejador is None or threading.current_thread() is not threading.main_thread():
        return None
    try:
        return signal.signal(signal.SIGINT, manejador)
    except (ValueError, OSError, TypeError):
        return None


# ── sin pantalla: las capturas para comparar con la maqueta ───────────────────
def render(w, h, pantalla="principal", colores="24", datos=None, texto="", sel=0, op=0):
    """La pantalla sin terminal (con los datos de ejemplo, si no se dan). → Term."""
    d = datos or datos_ejemplo()
    if pantalla == "entrega":
        agentes = d["agentes"]
        op1 = next(o for o in opciones("arregla el instalador", agentes, 1) if o["tipo"] == "enviar")
        return pantalla_entrega(w, h, d, plan(op1, agentes), d.get("entrega"), 9.0, "14:32")
    return pantalla_principal(w, h, d, texto, sel, op, None, "14:32")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="hub_paleta.py", description="El hub «Paleta» (solo para probar).")
    ap.add_argument("--render", metavar="ANCHOxALTO", help="dibuja sin terminal (p. ej. 88x30) y sale")
    ap.add_argument("--entrega", action="store_true", help="la pantalla de entrega")
    ap.add_argument("--256", dest="c256", action="store_true", help="256 colores")
    ap.add_argument("--reales", action="store_true", help="con los datos reales (si no, los de la maqueta)")
    ap.add_argument("--texto", default="", help="lo escrito en la entrada")
    ap.add_argument("--html", help="guarda la captura en HTML")
    a = ap.parse_args(argv)
    if not a.render:
        return correr() or 0
    w, h = (int(v) for v in a.render.lower().split("x"))
    T = render(w, h, "entrega" if a.entrega else "principal", "256" if a.c256 else "24",
               datos_reales() if a.reales else None, a.texto)
    if a.html:
        with open(a.html, "w", encoding="utf-8") as fh:
            fh.write(T.html("256" if a.c256 else "24", "Paleta · %dx%d%s" % (w, h, " · entrega" if a.entrega else "")))
    print("\n".join(T.ansi("256" if a.c256 else "24")))
    return 0


if __name__ == "__main__":
    # La Paleta de antes se corre directo solo en una copia de desarrollo (puertas_dev, que no viaja); en un cliente,
    # la línea de dónde está el hub (puertas.redirigir).
    import puertas
    sys.exit(__import__("puertas_dev").hub_paleta_main() if puertas.dev() else puertas.redirigir("hub"))
