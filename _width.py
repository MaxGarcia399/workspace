#!/usr/bin/env python3
"""WORKSPACE · _width — medición de ancho VISUAL de terminal, COMPARTIDA.

Única fuente de la aritmética de columnas que mantiene rectos los marcos de
los TUIs (hublayout = hub/layouts · config_tui = pantalla de CONFIG). Nació
del fix de medición de hublayout (9b0a5f1): medir solo `\\x1b[…m` y contar
tab/ESC/zero-width como ancho 1 descuadraba los bordes fila a fila. Antes el
fix vivía solo en hublayout; aquí queda destilado para que NINGÚN TUI vuelva
a duplicar (y desincronizar) esta lógica.

Qué cubre:
  · ANSI   — cualquier escape que la terminal consume sin pintar: CSI
             completo (colores 38;2/38:2, cursor…), OSC (título/colores de
             terminal) y ESC de 2 bytes.
  · sane() — NFC (los acentos NFD que da macOS medirían de más), sin
             zero-width/selectores de variación (emoji-presentation
             descuadra el borde), controles (tab/newline) → espacio. Los
             ESC de color pasan intactos. Idempotente.
  · sane_plain() — para TEXTO PLANO de celdas (valores/labels que jamás
             traen color propio legítimo): quita TODO escape ANSI, sanea,
             y un ESC suelto que sobreviva → espacio.
  · eaw()  — ancho de UN carácter como lo pinta la terminal: combinantes e
             invisibles (Mn/Me/Cf) = 0 · CJK/Hangul (W/F) = 2 — Hangul-safe,
             para agentes con display en coreano/CJK · resto = 1.

stdlib puro, sin estado, Python 3.9+, Mac/Windows.
"""
import re
import unicodedata

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]"
                  r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"
                  r"|\x1b[@-Z\\-_]")
CTRL = re.compile(r"[\x00-\x1a\x1c-\x1f\x7f]")   # C0 (tab/newline…) salvo ESC
INVIS = re.compile("[\u200b-\u200d\u2060\ufe0e\ufe0f\ufeff]")   # zero-width + VS15/16 + BOM


def sane(s):
    """Línea SEGURA para columnas de terminal (ver docstring del módulo).
    Los ESC de color pasan intactos. Idempotente."""
    s = str(s)
    if not s.isascii():
        s = unicodedata.normalize("NFC", s)
        s = INVIS.sub("", s)
    return CTRL.sub(" ", s)


def strip_ansi(s):
    """Quita TODO escape ANSI (CSI/OSC/ESC de 2 bytes)."""
    return ANSI.sub("", str(s))


def sane_plain(s):
    """Sane para texto PLANO de celdas: sin escapes ANSI, saneado, y un ESC
    huérfano (secuencia rota/cortada) → espacio. Idempotente."""
    return sane(strip_ansi(s)).replace("\x1b", " ")


def eaw(c):
    """Ancho de UN carácter como lo pinta la terminal (ver docstring)."""
    if unicodedata.category(c) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
