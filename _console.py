#!/usr/bin/env python3
"""WORKSPACE · _console — ¿hay una CONSOLA INTERACTIVA real? (contrato headless).

Una sola respuesta compartida para «¿puedo dibujar un menú y esperar teclado?».
`stream.isatty()` NO basta en Windows: el dispositivo NUL (stdin=DEVNULL,
`< NUL`, servicios, automatizaciones) es un *character device* y Python
reporta isatty()=True — el hub caía al altar animado y a `msvcrt.getwch()`,
que lee de la CONSOLA (no de stdin) y se quedaba esperando una tecla para
siempre, escribiendo la animación a un archivo (W-F04, Z19).

Regla:
  · POSIX   → os.isatty(fd) (una tty real; /dev/null NO es tty).
  · Windows → os.isatty(fd) Y GetConsoleMode(handle) tiene éxito. NUL pasa
              el isatty pero GetConsoleMode falla → NO es consola.
              Si ctypes no está disponible (rarísimo) se queda con isatty
              (preserva el uso interactivo real; documentado como límite).

Cero dependencias (stdlib). Falla-suave: cualquier error → False (no
interactivo = camino seguro, nunca cuelga)."""
import os
import sys


def _win_console_handle(fd):
    """True si el handle del fd es una consola Windows (GetConsoleMode OK).
    None si no se pudo comprobar (sin ctypes/msvcrt)."""
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes
    except Exception:
        return None
    try:
        h = msvcrt.get_osfhandle(fd)
        mode = wintypes.DWORD()
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetConsoleMode.argtypes = (wintypes.HANDLE,
                                       ctypes.POINTER(wintypes.DWORD))
        k32.GetConsoleMode.restype = wintypes.BOOL
        return bool(k32.GetConsoleMode(wintypes.HANDLE(h), ctypes.byref(mode)))
    except Exception:
        return False


def is_console(stream):
    """¿`stream` es una terminal/consola interactiva real? (ver docstring)."""
    try:
        fd = stream.fileno()
    except Exception:
        return False
    try:
        if not os.isatty(fd):
            return False
    except Exception:
        return False
    if os.name != "nt":
        return True
    ok = _win_console_handle(fd)
    return True if ok is None else ok


def interactive():
    """stdin Y stdout son consola interactiva real — la condición para abrir
    una TUI que lee teclado y repinta (hub, picker, pantallas completas).
    Si cualquiera está redirigido (pipe, archivo, NUL) → False."""
    return is_console(sys.stdin) and is_console(sys.stdout)
