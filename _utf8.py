#!/usr/bin/env python3
"""B2 · Endurecimiento UTF-8 — cero dependencias (stdlib, Python 3.7+).

`harden()` fuerza stdout/stderr a UTF-8/replace al arrancar. En Windows un
proceso capturado por un pipe usa cp1252 y revienta al imprimir `✓`/box-drawing;
esto lo evita. No-op en Mac/Linux (UTF-8 ya es default). Nunca lanza — cada
stream va en su propio try/except — e idempotente (reconfigure repetido es safe).
"""
import sys


def harden():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
