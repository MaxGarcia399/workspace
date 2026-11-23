#!/usr/bin/env python3
"""WORKSPACE · instalar_vista — lo que ves mientras se instala Workspace (O2-a «Una línea viva»).

Arriba la marca y tu monito dormido; cuatro pasos que se palomean en su lugar (Reviso · Descargo · Preparo el
comando · Abro Workspace); los errores, en una tarjeta que dice qué pasó y qué hago yo. Todo lo demás que hace el
instalador (rutas, archivos, ajustes de cada motor) va a `<estado>/instalar.log`; `--detalle` lo enseña en pantalla.

Quién pinta qué:
  · setup.sh / dist/setup.sh (bash 3.2, bloque `workspace-vista`): la cabeza sin el monito, los cuatro pasos y los
    pasos 1-2 (revisar y descargar: todavía no hay Python de Workspace).
  · install.py (con WORKSPACE_INSTALL_VISTA=vivo): el monito y la versión sobre las MISMAS filas, el paso 3 mientras
    instala y el final (abro Workspace aquí mismo).
  · setup.ps1 (Windows) y quien no tenga el bloque arriba: modo «lineal», una línea por paso, sin mover el cursor.

El contrato de filas, columnas y colores vive en este archivo; tests/test_instalar_vista.py comprueba que el bloque
de bash escribe byte por byte lo mismo que estas funciones. Sin fondos: la terminal de la persona puede ser clara u
oscura (la de fábrica de la Mac es blanca); solo tinta, y los pixeles del monito sobre el fondo de la terminal.
Stdlib, Python 3.9+."""
import os
import re
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

# ── el contrato del bloque (filas desde la primera que escribe setup.sh) ──────
FILA_Z = 0            # el «z» del monito
FILA_CABEZA = 1       # 1..4: el monito; la marca y dos líneas a su derecha (1..3)
FILA_PASO = 6         # 6..9: los cuatro pasos (paso n → FILA_PASO + n - 1)
FILA_ESTADO = 11      # la barra mientras instala; «Listo en N s.» al final; la tarjeta de un error empieza aquí
FILA_CASA = 12        # donde descansa el cursor mientras se instala
FILA_FINAL = 13       # 13..14: «Abriendo Workspace aquí mismo…» y lo que sigue
COL_MONO, COL_MARCA, COL_GLIFO, COL_TITULO, COL_DETALLE = 3, 14, 3, 6, 27
ANCHO_BARRA = 24
ANCHO_TARJETA = 76    # desde la columna 2: cabe en 80
MIN_COLS, MIN_FILAS = 80, 24

#: Tinta (sin fondo). Mismos números en el bloque de bash: 24 bits y su vecino de 256 colores (hub_paleta.q256).
OK, ACENTO, AVISO, TENUE = "#3fbf7f", "#ff4fa3", "#e7a43a", "#8a8a94"
GRIS = "#8a8a94"      # el monito que viene (todavía sin nombre ni color)
TRANSPARENTE = "#000001"   # marca interna de «el fondo de la terminal» (nunca se escribe)
ESC = "\x1b["
R = ESC + "0m"
NEGRITA = ESC + "1m"

GIROS = ("◐", "◓", "◑", "◒")

PASOS = {
    "mac": ("Reviso tu Mac", "Descargo Workspace", "Preparo el comando", "Abro Workspace"),
    "pc": ("Reviso tu PC", "Descargo Workspace", "Preparo el comando", "Abro Workspace"),
    "otra": ("Reviso tu computadora", "Descargo Workspace", "Preparo el comando", "Abro Workspace"),
}
HECHOS = {"Reviso": "Revisé", "Descargo": "Descargué", "Preparo": "Preparé"}


def sistema():
    if sys.platform == "darwin":
        return "mac"
    return "pc" if os.name == "nt" else "otra"


def pasado(titulo):
    """«Reviso tu Mac» → «Revisé tu Mac» (lo que ya se hizo)."""
    pal, _, resto = titulo.partition(" ")
    return HECHOS.get(pal, pal) + ((" " + resto) if resto else "")


# ── color ─────────────────────────────────────────────────────────────────────
def modo_color(env=None):
    """«24», «256» o «» (NO_COLOR). La misma regla del hub (hub_paleta._colores) y del bloque de bash."""
    e = os.environ if env is None else env
    if e.get("NO_COLOR"):
        return ""
    pedido = str(e.get("WORKSPACE_COLOR") or "").strip()
    if pedido in ("24", "256"):
        return pedido
    if str(e.get("TERM_PROGRAM") or "") == "Apple_Terminal":
        m = re.match(r"\s*(\d+)", str(e.get("TERM_PROGRAM_VERSION") or ""))
        return "24" if m and int(m.group(1)) >= 470 else "256"
    return "24" if str(e.get("COLORTERM") or "").lower() in ("truecolor", "24bit") else "256"


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _q256(h):
    try:
        import hub_paleta
        return hub_paleta.q256(h)
    except Exception:                                   # pragma: no cover — hub_paleta vive junto a este archivo
        return 245


def tinta(h, modo):
    """La secuencia de color de frente de `h` (sin fondo), desde un reset. '' sin color."""
    if not modo or not h:
        return ""
    if modo == "24":
        return ESC + "38;2;%d;%d;%dm" % _rgb(h)
    return ESC + "38;5;%dm" % _q256(h)


def _ancho(s):
    try:
        from _width import eaw
    except ImportError:                                 # pragma: no cover
        return len(s)
    return sum(eaw(c) for c in s)


def _cha(col):
    """Ir a la columna `col` (0 = la primera) de la fila del cursor."""
    return ESC + "%dG" % (col + 1)


# ── las líneas (las mismas que escribe el bloque de bash, byte por byte) ──────
def linea_paso(estado, titulo, detalle, modo):
    """Una fila de paso: el glifo en la columna 3, el título en la 6 y el detalle en la 27.
    estado: hecho (✓ verde, el título en pasado) · ahora (◐ acento, título en negrita) · error (✖ ámbar) · falta."""
    d = detalle or ""
    if estado == "hecho":
        g, t, dc = tinta(OK, modo) + NEGRITA + "✓" + R, pasado(titulo), tinta(TENUE, modo)
    elif estado == "ahora":
        g, t, dc = tinta(ACENTO, modo) + NEGRITA + "◐" + R, NEGRITA + titulo + R, tinta(TENUE, modo)
    elif estado == "error":
        g, t, dc = tinta(AVISO, modo) + NEGRITA + "✖" + R, NEGRITA + titulo + R, tinta(AVISO, modo)
    else:
        g, t, dc = tinta(TENUE, modo) + "·" + R, tinta(TENUE, modo) + titulo + R, tinta(TENUE, modo)
    return "   " + g + _cha(COL_TITULO) + t + _cha(COL_DETALLE) + dc + d + R


def linea_barra(k, modo):
    """La barra mientras se instala: `k` = el paso en curso (0..3) → (k + ½) / 4 llena, y «k+1 de 4»."""
    n = ANCHO_BARRA * (2 * k + 1) // 8
    return ("   " + tinta(ACENTO, modo) + "━" * n + tinta(TENUE, modo) + "─" * (ANCHO_BARRA - n) + R
            + "  " + tinta(TENUE, modo) + "%d de 4" % (k + 1) + R)


def linea_listo(segundos, modo):
    return "   " + tinta(OK, modo) + NEGRITA + "✓" + R + " " + NEGRITA + "Listo en %d s." % max(0, segundos) + R


def linea_abriendo(modo):
    return "   " + tinta(ACENTO, modo) + NEGRITA + "▸" + R + " " + tinta(ACENTO, modo) + NEGRITA + \
        "Abriendo Workspace aquí mismo…" + R


def linea_sin_abrir(modo):
    """Si el comando no quedó (un archivo ajeno con su nombre): dónde seguir, sin prometer que abre."""
    return "   " + tinta(ACENTO, modo) + NEGRITA + "▸" + R + " " + NEGRITA + \
        "Listo: abre una terminal nueva y escribe workspace." + R


def linea_despues(greeter, modo):
    txt = ("Desde ahora, cada terminal nueva abre Workspace." if greeter
           else "Después, escribe workspace en cualquier terminal.")
    return "     " + tinta(TENUE, modo) + txt + R


def lineas_marca(sistema_, version, modo):
    """Las tres líneas a la derecha del monito (sin el monito): la marca, qué hago y cómo se quita."""
    donde = {"mac": "tu Mac", "pc": "tu PC"}.get(sistema_, "tu computadora")
    marca = tinta(ACENTO, modo) + NEGRITA + "❯" + R + " " + NEGRITA + "workspace" + R
    if version:
        marca += " " + tinta(TENUE, modo) + version + R
    return [marca, "Lo instalo en %s. Toma un minuto." % donde,
            tinta(TENUE, modo) + "Sin cuentas nuevas · se quita con «workspace uninstall»" + R]


def tarjeta(titulo, lineas, modo, ancho=ANCHO_TARJETA):
    """Una tarjeta ámbar (borde redondo, sin fondo) desde la columna 2. Cada línea ya trae sus colores y cabe en
    `ancho - 6` columnas; el borde derecho va con salto de columna (no depende de contar letras)."""
    a, r = tinta(AVISO, modo), R
    out = ["  " + a + "╭" + "─" * (ancho - 2) + "╮" + r + _cha(4) + " " + a + NEGRITA + titulo + r + " "]
    for ln in [""] + list(lineas) + [""]:
        out.append("  " + a + "│" + r + "  " + ln + _cha(2 + ancho - 1) + a + "│" + r)
    out.append("  " + a + "╰" + "─" * (ancho - 2) + "╯" + r)
    return out


def envolver(texto, ancho):
    out, ln = [], ""
    for p in str(texto).split():
        if ln and _ancho(ln) + 1 + _ancho(p) > ancho:
            out.append(ln)
            ln = p
        else:
            ln = (ln + " " + p) if ln else p
    if ln:
        out.append(ln)
    return out or [""]


# ── la cabeza con el monito (las piezas del hub: hub_paleta.Term + hub_monitos_m1) ──
def cabeza(sistema_, version, modo, env=None):
    """Las filas 0..4 del bloque: el monito gris dormido (con su «z») y la marca. → 5 líneas con color, sin fondo.
    En Terminal.app nada toca el tope de la celda (H6-a): sus bloques dibujan con SU fuente y salían con rayas."""
    import hub_paleta as P
    import hub_monitos_m1 as M
    e = os.environ if env is None else env
    seguro = str(e.get("TERM_PROGRAM") or "") == "Apple_Terminal"
    T = P.Term(MIN_COLS, 5)
    T.fill(0, 0, T.w, T.h, TRANSPARENTE)
    M.dibujar(T, {"id": "instalar", "c": GRIS, "f": "bolita", "st": "duerme"}, COL_MONO, FILA_CABEZA, 8,
              st="duerme")
    filas = [_fila(T, y, modo, seguro) for y in range(T.h)]
    for i, txt in enumerate(lineas_marca(sistema_, version, modo)):
        y = FILA_CABEZA + i
        filas[y] = filas[y] + _cha(COL_MARCA) + txt + R if filas[y] else _cha(COL_MARCA) + txt + R
    return filas


def _sgr_celda(fg, bg, b, rev, modo):
    if not modo:
        return R + (NEGRITA if b else "") + (ESC + "7m" if rev else "")
    s = "0"
    if b:
        s += ";1"
    if rev:
        s += ";7"
    if fg:
        s += (";38;2;%d;%d;%d" % _rgb(fg)) if modo == "24" else ";38;5;%d" % _q256(fg)
    if bg:
        s += (";48;2;%d;%d;%d" % _rgb(bg)) if modo == "24" else ";48;5;%d" % _q256(bg)
    return ESC + s + "m"


def _fila(T, y, modo, seguro):
    """Una fila del Term a texto con color, sin fondo donde la terminal pone el suyo. '' si la fila está vacía."""
    celdas = []
    for x in range(T.w):
        k = T.at(x, y)
        if k.ch == "":
            continue
        ch, fg, bg, b, rev = k.ch, k.fg, (None if k.bg == TRANSPARENTE else k.bg), k.b, False
        if seguro and k.px and ch in ("█", "▀"):
            if ch == "█":
                ch, fg, bg = " ", None, fg              # la celda entera, con su color de fondo
            elif bg is None:
                ch, rev = "▄", True                       # ▀ sobre la terminal: ▄ al revés (el fondo es su color)
            else:
                ch, fg, bg = "▄", bg, fg
        celdas.append((ch, fg, bg, b, rev))
    while celdas and celdas[-1][0] == " " and celdas[-1][2] is None and not celdas[-1][4]:
        celdas.pop()
    if not celdas:
        return ""
    out, ult = [], None
    for ch, fg, bg, b, rev in celdas:
        est = (fg if ch != " " else None, bg, b if ch != " " else False, rev)
        if est != ult:
            out.append(_sgr_celda(est[0], bg, est[2], rev, modo))
            ult = est
        out.append(ch)
    return "".join(out) + R


# ── la vista que corre install.py ─────────────────────────────────────────────
class Vista:
    """Lo que install.py enseña mientras instala. `modo`: «vivo» (sobre el bloque de setup.sh) o «lineal»."""

    def __init__(self, modo="vivo", salida=None, env=None, version="", t0=None):
        self.env = os.environ if env is None else env
        self.modo = modo
        self.out = salida or sys.stdout
        self.col = modo_color(self.env)
        self.sis = sistema()
        self.version = version
        try:
            self.t0 = float(t0 if t0 is not None else self.env.get("WORKSPACE_INSTALL_T0") or time.time())
        except ValueError:
            self.t0 = time.time()
        self.fila = FILA_CASA                     # el cursor, en filas del bloque (contrato con setup.sh)
        self._giro = None
        self._alto = threading.Event()
        self._lock = threading.Lock()

    # bajo nivel
    def _w(self, s):
        try:
            self.out.write(s)
            self.out.flush()
        except (OSError, ValueError):
            pass

    def _ir(self, fila):
        d = fila - self.fila
        s = (ESC + "%dA" % -d) if d < 0 else ((ESC + "%dB" % d) if d > 0 else "")
        self.fila = fila
        return s + "\r"

    def _escribir(self, fila, texto):
        with self._lock:
            self._w(self._ir(fila) + ESC + "K" + texto)

    def _abajo(self, lineas):
        """Lineas nuevas debajo de la última fila del bloque (las crea: el cursor baja con saltos de línea)."""
        with self._lock:
            s = ""
            for ln in lineas:
                s += "\n\r" + ESC + "K" + ln
                self.fila += 1
            self._w(s)

    def titulo(self, n):
        return PASOS[self.sis][n - 1]

    # lo que se ve
    def empezar(self):
        if self.modo != "vivo":                     # lineal: el paso en curso, sin salto (terminar lo reescribe)
            self._w("\r" + ESC + "K" + linea_paso("ahora", self.titulo(3), "workspace", self.col))
            return
        try:
            filas = cabeza(self.sis, self.version, self.col, self.env)
        except Exception:                           # sin las piezas del hub: queda la cabeza de setup.sh
            filas = []
        for y, ln in enumerate(filas):
            self._escribir(FILA_Z + y, ln)
        self._escribir(FILA_PASO + 2, linea_paso("ahora", self.titulo(3), "workspace", self.col))
        self._escribir(FILA_ESTADO, linea_barra(2, self.col))
        self._w(self._ir(FILA_CASA))
        self._girar(FILA_PASO + 2)

    def _girar(self, fila):
        def correr():
            i = 0
            while not self._alto.wait(0.15):
                i += 1
                with self._lock:
                    vuelta = self.fila
                    self._w(self._ir(fila) + _cha(COL_GLIFO) + tinta(ACENTO, self.col) + NEGRITA
                            + GIROS[i % 4] + R + self._ir(vuelta))
        self._alto.clear()
        self._giro = threading.Thread(target=correr, daemon=True)
        self._giro.start()

    def parar(self):
        self._alto.set()
        if self._giro is not None:
            self._giro.join(1.0)
            self._giro = None

    def terminar(self, greeter, avisos=(), abre=True):
        self.parar()
        seg = int(time.time() - self.t0 + 0.5)
        fin = [linea_abriendo(self.col), linea_despues(greeter, self.col)] if abre else [linea_sin_abrir(self.col)]
        if self.modo == "vivo":
            self._escribir(FILA_PASO + 2, linea_paso("hecho", self.titulo(3), "workspace ya funciona", self.col))
            if abre:
                self._escribir(FILA_PASO + 3, linea_paso("ahora", self.titulo(4), "aquí mismo", self.col))
            self._escribir(FILA_ESTADO, linea_listo(seg, self.col))
            self._w(self._ir(FILA_CASA) + ESC + "J")
            self._abajo(fin)
        else:
            self._w("\r" + ESC + "K" + "\n".join([
                linea_paso("hecho", self.titulo(3), "workspace ya funciona", self.col), "",
                linea_listo(seg, self.col), ""] + fin))
        if avisos:
            self._avisos(avisos)
        self._w("\n")

    def _avisos(self, avisos):
        lns = [""] + ["   " + tinta(AVISO, self.col) + NEGRITA + "!" + R + " " + str(a).lstrip("!⚠✗ ").strip()
                      for a in list(avisos)[:3]]
        if self.modo == "vivo":
            self._abajo(lns)
        else:
            self._w("\n" + "\n".join(lns))

    def fallo(self, ultimas, bitacora):
        """install.py no terminó: el paso 3 con ✖ y una tarjeta con lo último que pasó y dónde está todo."""
        self.parar()
        lineas = ["No hiciste nada mal. Esto es lo último que pasó:"]
        for u in list(ultimas)[-3:]:
            for ln in envolver(u, ANCHO_TARJETA - 10):
                lineas.append("  " + tinta(TENUE, self.col) + ln + R)
        lineas += ["", tinta(ACENTO, self.col) + NEGRITA + "▸" + R + " " + NEGRITA
                   + "Vuelve a pegar el mismo comando: es seguro, no duplica nada." + R]
        if bitacora:
            for ln in envolver("Todo lo que hice está en " + bitacora, ANCHO_TARJETA - 10):
                lineas.append("  " + tinta(TENUE, self.col) + ln + R)
        card = tarjeta("No pude terminar de prepararlo", lineas, self.col)
        if self.modo == "vivo":
            self._escribir(FILA_PASO + 2, linea_paso("error", self.titulo(3), "no pude terminar", self.col))
            self._w(self._ir(FILA_ESTADO) + ESC + "J")
            self._w(ESC + "K" + card[0])
            self._abajo(card[1:])
            self._w("\n")
        else:
            self._w("\r" + ESC + "K" + "\n".join(
                [linea_paso("error", self.titulo(3), "no pude terminar", self.col), ""] + card) + "\n")

    def preguntar(self, texto):
        """Una pregunta del instalador (raro: solo con una instalación vieja que retirar) sin romper el bloque."""
        self.parar()
        with self._lock:
            self._w(self._ir(FILA_CASA) + ESC + "J" + texto)
        try:
            r = sys.stdin.readline()
        finally:
            self.fila = FILA_CASA + 1               # Enter bajó una fila
        if r == "":
            raise EOFError
        return r.rstrip("\n")


# ── la bitácora (lo que install.py dice, fuera de la pantalla) ────────────────
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def bitacora_path(state_dir):
    return os.path.join(state_dir, "instalar.log")


def es_aviso(linea):
    """¿Una línea de install.py que la persona debe ver aunque no pida el detalle? Lo que no se pudo hacer (✗/!/⚠),
    salvo «falta: el motor…» del aviso de piezas: de los motores se encarga Workspace al abrir."""
    t = _ANSI.sub("", linea).strip()
    if not t or "falta:" in t or "Puedes seguir" in t:
        return False
    return t[:1] in ("✗", "!", "⚠")


def limpio(linea):
    return _ANSI.sub("", linea).strip()
