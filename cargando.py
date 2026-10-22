#!/usr/bin/env python3
"""WORKSPACE · cargando — «Cargando…» al centro mientras Workspace prepara un agente.

Versión simple (0.5.0): un cuadro fijo, sin animación ni pantalla alterna, en
dos momentos de la apertura:
  · al arrancar dispatch, hasta que el motor pinta su banner o el menú de
    pestañas (los dos limpian la pantalla al dibujarse);
  · en Hermes y OpenClaw, al elegir la pestaña, hasta que el adaptador limpia
    la pantalla justo antes de su chat (que es EN LÍNEA). En ese tramo se
    prepara la pestaña y, en OpenClaw, se espera al gateway.

Y «Guardando…» (0.5.1), con el mismo cuadro y sin subtítulo, al salir del chat
de OpenClaw (`/exit`): su respaldo tarda decenas de segundos y la consola se
quedaba quieta y en silencio (revisión de la 0.5.1, P2-5). Lo quita `quitar()`
al terminar: solo su línea, nunca el historial de la terminal, y nada si
algo se escribió debajo (el aviso de un respaldo que falló se queda a la
vista; segunda revisión de la candidata 0.5.1, N1).

No toca el teclado ni el modo de la terminal: lo que Workspace imprima después
(un aviso, una pregunta, un error) sale debajo, como siempre, así que no tapa
nada. Solo con terminal (stdout tty); WORKSPACE_NO_CARGA=1 lo apaga.
Falla-suave: jamás frena una apertura. Cero dependencias (stdlib, Python 3.9+).
"""
import os
import shutil
import sys
import unicodedata

LIMPIAR = "\033[2J\033[3J\033[H"
#: Lo mismo sin borrar el historial (\033[3J): «Guardando…» sale después del
#: chat y lo de antes se queda en la terminal.
LIMPIAR_VISTA = "\033[2J\033[H"


def _t(clave, es):
    """Texto de la UI (i18n, catálogo lang/<code>/dispatch.py) con el español
    como red."""
    try:
        import i18n
        s = i18n.t(clave)
        if isinstance(s, str) and s and s != clave:
            return s
    except Exception:
        pass
    return es


def _ancho(texto):
    """Ancho visual (CJK/Hangul cuentan 2)."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in texto)


def _recortar(texto, cols):
    """`texto` cortado para que quepa en `cols` columnas (con «…»)."""
    if _ancho(texto) <= cols:
        return texto
    out, w = "", 0
    for c in texto:
        cw = _ancho(c)
        if w + cw > max(0, cols - 1):
            break
        out, w = out + c, w + cw
    return out + "…"


def _colores():
    """(acento, tenue, negrita, reset) del tema del hub; sin color si falla."""
    try:
        import tuitheme
        P = tuitheme.palette()
        return P.C, P.DIM, P.BO, P.R
    except Exception:
        return "", "", "", ""


def cuadro(cols, rows, sub="", colores=("", "", "", ""), texto=None, limpiar=LIMPIAR):
    """Lo que se escribe: limpiar y «Cargando…» (u otro `texto`, con `sub`
    tenue debajo) al centro de una pantalla de `cols`×`rows`. El cursor queda
    debajo; sin `sub`, dos líneas debajo del texto."""
    acento, tenue, negrita, reset = colores
    texto = texto or _t("dispatch.cargando", "Cargando…")
    sub = _recortar(" ".join(str(sub or "").split()), max(1, cols - 4))
    alto = 3 if sub else 1
    out = [limpiar, "\n" * max(0, (rows - alto) // 2)]
    out.append(" " * max(0, (cols - _ancho(texto)) // 2) + negrita + acento + texto + reset + "\n")
    if sub:
        out.append("\n" + " " * max(0, (cols - _ancho(sub)) // 2) + tenue + sub + reset + "\n")
    out.append("\n")
    return "".join(out)


def mostrar(sub="", out=None, texto=None, limpiar=LIMPIAR):
    """Pinta el cuadro en la terminal. True si pintó; False sin terminal, con
    WORKSPACE_NO_CARGA o ante cualquier error (jamás levanta)."""
    out = out or sys.stdout
    if os.environ.get("WORKSPACE_NO_CARGA"):
        return False
    try:
        if not out.isatty():
            return False
        cols, rows = shutil.get_terminal_size((80, 24))
        out.write(cuadro(cols, rows, sub, _colores(), texto=texto, limpiar=limpiar))
        out.flush()
        return True
    except Exception:
        return False


#: ¿Está pintado «Guardando…»? (para que quitar() no limpie una pantalla ajena)
_GUARDANDO = []
#: ¿Se escribió algo debajo del cuadro? (lo anota _Vigia)
_DEBAJO = []
#: Las salidas que vigila _Vigia mientras está «Guardando…»: nombre → (vigía, real).
_VIGIAS = {}
#: Borra la línea de «Guardando…» (el cursor quedó dos líneas debajo, ver
#: cuadro) y deja el cursor arriba, como la pantalla limpia de antes.
_BORRAR_LINEA = "\033[2A\r\033[2K\033[H"


class _Vigia(object):
    """sys.stdout/sys.stderr mientras está «Guardando…»: escribe igual, pero
    anota que algo salió debajo del cuadro (p. ej. «respaldo OpenClaw
    falló»), para que quitar() no lo borre."""

    def __init__(self, real):
        self._real = real

    def write(self, texto):
        if texto:
            _DEBAJO[:] = [True]
        return self._real.write(texto)

    def writelines(self, lineas):
        for linea in lineas:
            self.write(linea)

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


def _vigilar():
    for nombre in ("stdout", "stderr"):
        real = getattr(sys, nombre, None)
        if real is None or isinstance(real, _Vigia):
            continue
        vigia = _Vigia(real)
        setattr(sys, nombre, vigia)
        _VIGIAS[nombre] = (vigia, real)


def _soltar():
    for nombre, (vigia, real) in list(_VIGIAS.items()):
        if getattr(sys, nombre, None) is vigia:   # nadie la cambió después
            setattr(sys, nombre, real)
    _VIGIAS.clear()


def guardando(out=None):
    """«Guardando…» al centro, una sola línea, mientras Workspace guarda la
    sesión al salir del chat. Limpia lo visible pero no el historial de la
    terminal. True si pintó (mismas reglas que mostrar)."""
    ok = mostrar(out=out, texto=_t("dispatch.guardando", "Guardando…"),
                 limpiar=LIMPIAR_VISTA)
    if ok:
        _GUARDANDO[:] = [True]
        del _DEBAJO[:]
        try:
            _vigilar()
        except Exception:
            pass
    return ok


def quitar(out=None):
    """Borra la línea de «Guardando…» si la pintó guardando() y nada se
    escribió debajo (la pantalla queda limpia, como la deja el chat al
    cerrar). Jamás borra el historial de la terminal ni lo que salió después
    del cuadro: un aviso ahí se queda a la vista. True si borró. Falla-suave."""
    if not _GUARDANDO:
        return False
    del _GUARDANDO[:]
    debajo = bool(_DEBAJO)
    del _DEBAJO[:]
    try:
        _soltar()
    except Exception:
        pass
    if debajo:
        return False
    out = out or sys.stdout
    try:
        out.write(_BORRAR_LINEA)
        out.flush()
        return True
    except Exception:
        return False
