#!/usr/bin/env python3
"""WORKSPACE · paths — SSOT de rutas de estado per-máquina.

El directorio de estado per-máquina (hoy `~/.claude/workspace`) se re-derivaba
en ~80 sitios: copias privadas de `_workspace_dir()` + joins inline sueltos. Si
la regla de dónde vive el estado cambia (plan agnóstico de motor: raíz neutral
`~/.workspace/state`), había que tocar cada copia y cualquiera que se olvidara
driftaba en silencio. Este módulo es la fuente ÚNICA; sólo depende de stdlib
(`os`), así que cualquier módulo lo importa sin riesgo de ciclo.

Guarda automática: `tests/test_state_dir_guard.py` falla si un archivo fuera de
este módulo (y de su allowlist justificada) construye a mano la ruta de estado.

`expanduser` se resuelve EN CADA LLAMADA (no al import) para que los tests que
parchean HOME sigan funcionando.

TODO(agnóstico · Entrega 2): precedencia documentada en el plan §2.3:
    WORKSPACE_HOME (env) → ~/.workspace/state si existe → ~/.claude/workspace
    si existe (legado) → ~/.workspace/state (instalación nueva).
NO se cablea en la Entrega 1 (cero cambio visible): detectar
`~/.workspace/state` o leer un env nuevo cambiaría la carpeta de quien ya lo
tuviera, y los scripts que no pueden importar este módulo (statuslines copiadas
a los agentes, scripts de shell) seguirían en la ruta vieja → "dos verdades".
Además la semántica de WORKSPACE_HOME (¿raíz `~/.workspace` o el `state/`?)
debe fijarse junto con bus/voz. Llega con `migrar-estado` + enlace legado.
"""
import os

# Segmentos de la ruta legada, relativos a HOME. Únicos en todo el repo: la
# guarda prohíbe repetirlos en otro archivo.
_LEGACY_PARTS = (".claude", "workspace")


def state_dir(home=None):
    """Directorio de estado per-máquina de WORKSPACE.

    Entrega 1: SIEMPRE `<home>/.claude/workspace` (idéntico al histórico).
    `home` por defecto = `expanduser("~")` resuelto al llamarse (respeta un HOME
    parcheado). Los módulos con un `HOME` propio que los tests parchean
    (install, doctor, uninstall) lo pasan explícito para conservar ese punto."""
    if home is None:
        home = os.path.expanduser("~")
    return os.path.join(home, *_LEGACY_PARTS)


def workspace_dir():
    """Alias histórico de `state_dir()` (agentsreg, config_engine, …)."""
    return state_dir()
