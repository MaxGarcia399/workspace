#!/usr/bin/env python3
"""WORKSPACE · avisos_sistema — avisos de UNA línea, tranquilos, ANTES de una
acción opcional que dispara un diálogo del sistema que Workspace no puede
evitar (UAC de un instalador oficial, permisos de carpeta de macOS, la
pantalla de Google para apps sin verificar, los permisos de la voz).

Regla: el socio lee qué va a salir, por qué y qué contestar ANTES de que
salga; nunca un diálogo por sorpresa. La lista completa (qué puede salir, por
qué, qué contestar y qué pasa si dices No) está en manual/es/avisos.md y
manual/en/system-notices.md; el catálogo y la auditoría de origen, en
deliverables/workspace-avisos.

Textos: catálogo i18n `avisos.*` (fuente ES en lang/es/avisos.py, EN en
lang/en/avisos.py). Sin i18n o con la clave faltante → el español de la
fuente, nunca la clave cruda. Stdlib, falla-suave.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

#: (motor, sistema) → clave del aviso previo a instalarlo (o a su 1er uso).
#: sistema: "win32" | "darwin" | "linux".
MOTORES = {("codex", "win32"): "motor.codex_win",      # B1 · UAC de su caja
           ("kiro", "win32"): "motor.kiro_win",        # B2 · UAC del MSI
           ("kiro", "darwin"): "motor.kiro_mac"}       # B5 · ítem en segundo plano


def _fuente():
    try:
        from lang.es import avisos as es
        return es.STRINGS
    except Exception:
        return {}


def claves():
    """Todas las claves del catálogo (sin el prefijo `avisos.`)."""
    return sorted(k[len("avisos."):] for k in _fuente())


def texto(clave, **kw):
    """El aviso `clave` en el idioma activo (fallback: español de la fuente)."""
    key = "avisos." + clave
    try:
        import i18n
        v = i18n.t(key, **kw)
        if v != key:
            return v
    except Exception:
        pass
    s = _fuente().get(key, "")
    if s and kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def sistema(plataforma=None):
    p = plataforma or sys.platform
    if p.startswith("win"):
        return "win32"
    return "darwin" if p == "darwin" else "linux"


def motor(engine, plataforma=None):
    """El aviso previo de instalar `engine` en este sistema, o ''."""
    clave = MOTORES.get((engine, sistema(plataforma)))
    return texto(clave) if clave else ""
