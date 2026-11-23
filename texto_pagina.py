#!/usr/bin/env python3
"""WORKSPACE · texto_pagina — el texto que va a la página: recortado y sin llaves.

Vivían en pantalla_motor (que lee la pantalla de los motores) aunque no leen ninguna pantalla: los usan las rutas de
archivos de la página (skills, ejecuciones, pestañas…). Aquí quedan solos para que la página nueva (F3) no dependa de
pantalla_motor, y para que pantalla_motor pueda retirarse sin llevárselos. pantalla_motor los reexporta.
Stdlib, Python 3.9+.
"""


def _recorta(valor, n):
    s = "" if valor is None else str(valor)
    return s if len(s) <= n else s[:n]


def _limpio(texto, n):
    """Texto hacia la página: recortado y, si tiene forma de llave, ocultado. Se revisa
    el texto ENTERO y luego se recorta: una llave cortada a medias ya no se reconoce."""
    import secret_scan
    s = "" if texto is None else str(texto)
    try:
        return "[oculto]" if s and secret_scan.scan_text(s) else _recorta(s, n)
    except Exception:
        return ""


def _sin_secretos(texto):
    """Un texto puede traer una llave (un `env`, un log): ese renglón se tapa."""
    import secret_scan
    out = []
    for ln in str(texto or "").split("\n"):
        try:
            out.append("[renglón oculto: parecía una llave]" if ln and secret_scan.scan_text(ln) else ln)
        except Exception:
            out.append("")
    return "\n".join(out)
