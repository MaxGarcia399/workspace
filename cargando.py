#!/usr/bin/env python3
"""WORKSPACE · cargando — «Cargando…» al centro mientras Workspace prepara un agente.

Versión simple (0.5.0): un cuadro fijo, sin animación ni pantalla alterna, en
dos momentos de la apertura:
  · al arrancar dispatch, hasta que el motor pinta su banner o el menú de
    pestañas (los dos limpian la pantalla al dibujarse);
  · en Hermes y OpenClaw, al elegir la pestaña, hasta que el adaptador limpia
    la pantalla justo antes de su chat (que es EN LÍNEA). En ese tramo se
    prepara la pestaña y, en OpenClaw, se espera al gateway.

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


def cuadro(cols, rows, sub="", colores=("", "", "", "")):
    """Lo que se escribe: limpiar y «Cargando…» (con `sub` tenue debajo) al
    centro de una pantalla de `cols`×`rows`. El cursor queda debajo."""
    acento, tenue, negrita, reset = colores
    texto = _t("dispatch.cargando", "Cargando…")
    sub = _recortar(" ".join(str(sub or "").split()), max(1, cols - 4))
    alto = 3 if sub else 1
    out = [LIMPIAR, "\n" * max(0, (rows - alto) // 2)]
    out.append(" " * max(0, (cols - _ancho(texto)) // 2) + negrita + acento + texto + reset + "\n")
    if sub:
        out.append("\n" + " " * max(0, (cols - _ancho(sub)) // 2) + tenue + sub + reset + "\n")
    out.append("\n")
    return "".join(out)


def mostrar(sub="", out=None):
    """Pinta el cuadro en la terminal. True si pintó; False sin terminal, con
    WORKSPACE_NO_CARGA o ante cualquier error (jamás levanta)."""
    out = out or sys.stdout
    if os.environ.get("WORKSPACE_NO_CARGA"):
        return False
    try:
        if not out.isatty():
            return False
        cols, rows = shutil.get_terminal_size((80, 24))
        out.write(cuadro(cols, rows, sub, _colores()))
        out.flush()
        return True
    except Exception:
        return False
