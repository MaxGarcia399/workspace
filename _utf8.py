#!/usr/bin/env python3
"""B2 · Endurecimiento UTF-8 — cero dependencias (stdlib, Python 3.7+).

`harden()` fuerza stdout/stderr a UTF-8/replace al arrancar. En Windows un
proceso capturado por un pipe usa cp1252 y revienta al imprimir `✓`/box-drawing;
esto lo evita. No-op en Mac/Linux (UTF-8 ya es default). Nunca lanza — cada
stream va en su propio try/except — e idempotente (reconfigure repetido es safe).

`json_de_stdin()` es lo mismo del lado de la ENTRADA: el lector único del
payload JSON de los hooks (hooks/*.py y el runner workspace_hook.py). Lee BYTES
y decodifica UTF-8: en Windows, sin PYTHONUTF8 en el entorno (los motores
envueltos no lo exportan), `sys.stdin` decodifica con cp1252 y una ruta con
«José» en el usuario llegaba rota (el transcript o el cerebro «no existían»).
"""
import json
import sys


def harden():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def json_de_bytes(raw):
    """El payload JSON de un hook → dict. Bytes en UTF-8 con `utf-8-sig` (tolera
    el BOM); texto, tal cual y sin BOM. Vacío, basura o algo que no es un objeto
    → {}. Nunca lanza."""
    try:
        if isinstance(raw, (bytes, bytearray)):
            txt = bytes(raw).decode("utf-8-sig", "replace")
        else:
            txt = str(raw or "")
            if txt.startswith("﻿"):
                txt = txt[1:]
        d = json.loads(txt or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def json_de_stdin(stream=None, limite=None):
    """Lee el payload JSON de stdin como BYTES (`sys.stdin.buffer`) y lo parsea
    con json_de_bytes. Lo que mandan los motores es UTF-8 (Claude Code, Copilot
    y neutral_hooks.run_event, con ensure_ascii=False); leído como texto salía
    con la codificación de la consola (cp1252 en Windows). Un stdin sin
    `.buffer` (un StringIO en las pruebas) se lee como texto. Sin stdin → {}.
    `limite` (bytes): las barras de estado no leen más que eso; si el payload
    lo pasa, {} (no se interpreta a medias)."""
    s = sys.stdin if stream is None else stream
    try:
        fuente = getattr(s, "buffer", None) or s
        raw = fuente.read() if limite is None else fuente.read(limite + 1)
    except Exception:
        return {}
    if limite is not None and len(raw) > limite:
        return {}
    return json_de_bytes(raw)
