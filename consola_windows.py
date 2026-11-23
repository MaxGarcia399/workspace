#!/usr/bin/env python3
"""WORKSPACE · consola_windows — las teclas y el mouse del hub en Windows (Windows Terminal y la consola de siempre).

Antes el hub leía en Windows con `msvcrt.getwch()`, que solo ve teclas: el clic llegaba como un registro de mouse
de la consola (MOUSE_EVENT) y se perdía, y el hub ni pedía el mouse (`raton_posible` decía que no en Windows).
Aquí se lee la consola de verdad (ReadConsoleInputW) y TODO se vuelve los mismos bytes que manda una terminal de
Mac, para que el hub los lea con el mismo lector (hub_paleta._Teclado):

  · con el modo VT de entrada (ENABLE_VIRTUAL_TERMINAL_INPUT) Windows Terminal y conhost ya mandan las teclas y el
    mouse como secuencias de terminal (ESC [ A, ESC [ < 0;12;7 M …): pasan tal cual;
  · lo que llega como registro (un MOUSE_EVENT, una flecha sin carácter si la consola no aceptó el modo VT) se
    traduce a esas mismas secuencias (SGR 1006 para el mouse).

El modo de la consola se guarda al abrir y se devuelve EXACTO al soltar (al salir del hub, al prestarle la
terminal a un motor, con Ctrl+C o si algo truena: el `finally` del hub y, por si acaso, atexit). Con el mouse
prendido se quita la «edición rápida» (si no, conhost usa el clic para seleccionar texto y el hub nunca lo ve);
al apagarlo vuelve como estaba. Ctrl+C sigue siendo Ctrl+C.

Lo puro (`modo`, `a_bytes`) se prueba sin Windows. Stdlib, Python 3.9+."""
import atexit
import os
import time

#: Los modos de la consola de ENTRADA (SetConsoleMode).
PROCESADA, LINEA, ECO, VENTANA, RATON, INSERTAR, EDICION_RAPIDA, EXTENDIDO, VT = (
    0x1, 0x2, 0x4, 0x8, 0x10, 0x20, 0x40, 0x80, 0x200)
#: Tipos de registro (INPUT_RECORD.EventType).
_TECLA, _MOUSE = 0x1, 0x2
#: dwControlKeyState.
_ALT_DER, _ALT_IZQ, _CTRL_DER, _CTRL_IZQ, _SHIFT = 0x1, 0x2, 0x4, 0x8, 0x10
#: dwEventFlags del mouse.
_MOVIO, _DOBLE, _RUEDA, _RUEDA_LADO = 0x1, 0x2, 0x4, 0x8
#: dwButtonState → el botón de SGR (0 izquierdo, 1 medio, 2 derecho).
_BOTONES = ((0x1, 0), (0x4, 1), (0x2, 2))
_VK_TAB, _VK_ALT = 0x09, 0x12
#: Teclas sin carácter → su secuencia de terminal (la misma que manda una Mac). (normal, con Ctrl)
_VK = {0x26: (b"\x1b[A", b"\x1b[1;5A"), 0x28: (b"\x1b[B", b"\x1b[1;5B"), 0x27: (b"\x1b[C", b"\x1b[1;5C"),
       0x25: (b"\x1b[D", b"\x1b[1;5D"), 0x21: (b"\x1b[5~", b"\x1b[5~"), 0x22: (b"\x1b[6~", b"\x1b[6~"),
       0x24: (b"\x1b[H", b"\x1b[H"), 0x23: (b"\x1b[F", b"\x1b[F"), 0x2E: (b"\x1b[3~", b"\x1b[3~"),
       0x2D: (b"\x1b[2~", b"\x1b[2~"), 0x70: (b"\x1bOP", b"\x1bOP")}


def modo(viejo, raton=False, vt=True):
    """El modo de la consola de entrada mientras el hub la tiene, a partir del que había. Pura.
      · VT: las teclas y el mouse llegan como secuencias de terminal (las lee el lector de siempre);
      · `raton`: los registros de mouse sí, y SIN edición rápida (con EXTENDIDO, que hace falta para cambiarla);
        sin mouse, la edición rápida queda como estaba (seleccionar texto con el mouse, como siempre).
    Lo demás (Ctrl+C como señal, eco y línea —que solo usan las lecturas «cocinadas»—) se queda como estaba."""
    m = viejo | (VT if vt else 0)
    if raton:
        return (m | RATON | EXTENDIDO) & ~EDICION_RAPIDA
    m &= ~RATON
    if viejo & EDICION_RAPIDA:
        m |= EXTENDIDO | EDICION_RAPIDA          # quitarla y devolverla pide EXTENDIDO
    return m


def _mods(estado):
    return ((4 if estado & _SHIFT else 0) | (8 if estado & (_ALT_DER | _ALT_IZQ) else 0)
            | (16 if estado & (_CTRL_DER | _CTRL_IZQ) else 0))


def _sgr(codigo, x, y, suelta=False):
    return b"\x1b[<%d;%d;%d%s" % (codigo, max(1, x), max(1, y), b"m" if suelta else b"M")


def a_bytes(registros, botones=0, origen=(0, 0), raton=True, alto=None):
    """Registros de la consola → los bytes que mandaría una terminal. Pura (la prueban los tests sin Windows).
    `registros`: tuplas («k», abajo, repeticiones, vk, carácter, estado) o («m», x, y, botones, estado, banderas)
    (x, y del búfer: se les resta `origen`, la esquina de la ventana, y van desde 1). `botones`: los que estaban
    apretados antes (para saber qué se soltó); `raton=False`: el mouse se ignora; `alto`: la mitad alta de un emoji
    que quedó pendiente. → (bytes, botones, alto)."""
    out = bytearray()
    for r in registros:
        if r[0] == "k":
            _k, abajo, rep, vk, ch, estado = r
            ch = ch if ch and ch != "\x00" else ""
            n = max(1, int(rep or 1))
            if not abajo:
                if vk == _VK_ALT and ch:                 # Alt + teclado numérico (¿ ¡ « » € por SSH): al soltar Alt
                    out += ch.encode("utf-8", "replace")
                continue
            if vk == _VK_TAB and estado & _SHIFT:
                out += b"\x1b[Z" * n
                continue
            if not ch:
                sec = _VK.get(vk)
                if sec:
                    out += sec[1 if estado & (_CTRL_DER | _CTRL_IZQ) else 0] * n
                continue
            o = ord(ch)
            if 0xD800 <= o <= 0xDBFF:                    # emoji: la mitad alta espera a la baja
                alto = ch
                continue
            if 0xDC00 <= o <= 0xDFFF:
                if not alto:
                    continue
                ch, alto = (alto + ch).encode("utf-16", "surrogatepass").decode("utf-16"), None
            b = ch.encode("utf-8", "replace")
            # Alt+1…9 de una tecla de verdad (vk ≠ 0): Esc y su número, como en la Mac. AltGr (= Ctrl+Alt: la «@» de
            # un teclado español) es un carácter, no un Alt.
            if vk and ch in "123456789" and estado & (_ALT_DER | _ALT_IZQ) and not estado & (_CTRL_DER | _CTRL_IZQ):
                b = b"\x1b" + b
            out += b * n
        elif r[0] == "m":
            _m, x, y, bot, estado, banderas = r
            if not raton:
                continue
            x, y = x - origen[0] + 1, y - origen[1] + 1
            mods = _mods(estado)
            if banderas & _RUEDA:
                delta = (bot >> 16) & 0xFFFF
                delta = delta - 0x10000 if delta & 0x8000 else delta
                if delta:
                    out += _sgr((64 if delta > 0 else 65) | mods, x, y)
                continue
            if banderas & _RUEDA_LADO:
                continue
            bot &= 0x7
            if banderas & _MOVIO:
                apretado = next((c for bit, c in _BOTONES if bot & bit), None)
                out += _sgr((32 + apretado if apretado is not None else 35) | mods, x, y)
            else:                                        # 0 o doble clic: qué se apretó y qué se soltó
                for bit, c in _BOTONES:
                    if bot & bit and not botones & bit:
                        out += _sgr(c | mods, x, y)
                    elif botones & bit and not bot & bit:
                        out += _sgr(c | mods, x, y, suelta=True)
            botones = bot
    return bytes(out), botones, alto


class Consola:
    """La consola de entrada de este proceso, en el modo del hub. `abrir()` → una Consola, o None si no hay consola
    o no se pudo cambiar su modo (entonces el hub lee como antes, con msvcrt, sin mouse)."""

    @classmethod
    def abrir(cls):
        if os.name != "nt":
            return None
        try:
            return cls()
        except Exception:
            return None

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wt = ctypes, wintypes

        class KEY(ctypes.Structure):
            _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
                        ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
                        ("uChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]

        class MOUSE(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT), ("dwButtonState", wintypes.DWORD),
                        ("dwControlKeyState", wintypes.DWORD), ("dwEventFlags", wintypes.DWORD)]

        class EVENT(ctypes.Union):
            _fields_ = [("KeyEvent", KEY), ("MouseEvent", MOUSE), ("_pad", ctypes.c_byte * 16)]

        class RECORD(ctypes.Structure):
            _fields_ = [("EventType", wintypes.WORD), ("Event", EVENT)]

        class INFO(ctypes.Structure):
            _fields_ = [("dwSize", wintypes._COORD), ("dwCursorPosition", wintypes._COORD),
                        ("wAttributes", wintypes.WORD), ("srWindow", wintypes.SMALL_RECT),
                        ("dwMaximumWindowSize", wintypes._COORD)]
        self.RECORD, self.KEY, self.MOUSE, self.INFO = RECORD, KEY, MOUSE, INFO
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetStdHandle.restype = wintypes.HANDLE
        self.k32 = k32
        self.h = k32.GetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF))
        self.ho = k32.GetStdHandle(wintypes.DWORD(-11 & 0xFFFFFFFF))
        m = wintypes.DWORD()
        if not k32.GetConsoleMode(wintypes.HANDLE(self.h), ctypes.byref(m)):
            raise OSError("la entrada no es una consola")
        self.viejo = m.value
        self.vt = True
        self.raton = False
        self.raton_ok = False
        self.botones = 0
        self.alto = None
        self.suelta = False
        if not self._poner(modo(self.viejo, raton=False, vt=True)):
            self.vt = False                              # una consola vieja sin modo VT: los registros se traducen
            if not self._poner(modo(self.viejo, raton=False, vt=False)):
                raise OSError("la consola no acepta el modo")
        atexit.register(self.soltar)

    def _poner(self, m):
        return bool(self.k32.SetConsoleMode(self.wt.HANDLE(self.h), self.wt.DWORD(m)))

    def poner(self, raton):
        """Prende o apaga el mouse (y la edición rápida al revés). → True si la consola lo aceptó."""
        self.suelta = False
        ok = self._poner(modo(self.viejo, raton=raton, vt=self.vt))
        self.raton = bool(raton) and ok
        if raton:
            self.raton_ok = ok
        return ok

    def soltar(self):
        """El modo de antes, exacto (al salir del hub o al prestarle la terminal a un motor)."""
        if not self.suelta:
            self.suelta = True
            self._poner(self.viejo)

    def tomar(self):
        self.poner(self.raton)

    def vaciar(self):
        try:
            self.k32.FlushConsoleInputBuffer(self.wt.HANDLE(self.h))
        except Exception:
            pass
        self.botones, self.alto = 0, None

    def _origen(self):
        info = self.INFO()
        if self.k32.GetConsoleScreenBufferInfo(self.wt.HANDLE(self.ho), self.ctypes.byref(info)):
            return info.srWindow.Left, info.srWindow.Top
        return 0, 0

    def _pendientes(self):
        n = self.wt.DWORD()
        if not self.k32.GetNumberOfConsoleInputEvents(self.wt.HANDLE(self.h), self.ctypes.byref(n)):
            return 0
        return n.value

    def leer(self, espera, maximo=128):
        """Los bytes de lo que llegue en hasta `espera` s (None si no llegó nada que sea tecla o mouse; espera=None:
        hasta que llegue)."""
        fin = None if espera is None else time.monotonic() + max(0.0, espera)
        while True:
            ms = 0xFFFFFFFF if fin is None else int(max(0.0, fin - time.monotonic()) * 1000)
            if self.k32.WaitForSingleObject(self.wt.HANDLE(self.h), self.wt.DWORD(ms)) != 0:
                return None
            regs = []
            while True:
                n = min(maximo, self._pendientes())
                if n <= 0:
                    break
                buf = (self.RECORD * n)()
                leidos = self.wt.DWORD()
                if not self.k32.ReadConsoleInputW(self.wt.HANDLE(self.h), buf, n, self.ctypes.byref(leidos)):
                    break
                for r in buf[:leidos.value]:
                    if r.EventType == _TECLA:
                        k = r.Event.KeyEvent
                        regs.append(("k", bool(k.bKeyDown), int(k.wRepeatCount), int(k.wVirtualKeyCode), k.uChar,
                                     int(k.dwControlKeyState)))
                    elif r.EventType == _MOUSE:
                        m = r.Event.MouseEvent
                        regs.append(("m", int(m.X), int(m.Y), int(m.dwButtonState), int(m.dwControlKeyState),
                                     int(m.dwEventFlags)))
                if leidos.value < n:
                    break
            origen = self._origen() if any(r[0] == "m" for r in regs) else (0, 0)
            datos, self.botones, self.alto = a_bytes(regs, self.botones, origen, self.raton, self.alto)
            if datos:
                return datos
            if fin is not None and time.monotonic() >= fin:
                return None
