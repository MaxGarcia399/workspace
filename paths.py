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


# ── carpetas del socio (Mac/Linux: instalaciones NUEVAS) ─────────────────────
# macOS pide permiso por cada app de terminal para entrar a Escritorio,
# Documentos y Descargas (TCC). Por eso una instalación nueva va a ~/Workspace
# (setup.sh) y los cerebros nuevos a ~/Workspace/Cerebros/<NOMBRE>. Lo que ya
# existe en otro lado (p. ej. ~/Desktop/Workspace) NO se mueve: se detecta
# (installed_root) y sigue funcionando donde está. Windows no cambia: el harness
# va a %LOCALAPPDATA%\Workspace (setup.ps1).
#: Nombre de la carpeta de Workspace en HOME (instalación nueva de Mac/Linux).
HOME_DIRNAME = "Workspace"
#: Dentro de ella, las carpetas que son DEL SOCIO (no del harness): ni git las
#: versiona (.gitignore) ni el desinstalador las borra.
BRAINS_DIRNAME = "Cerebros"
EXPORTS_DIRNAME = "Respaldos"
USER_DIRNAMES = (BRAINS_DIRNAME, EXPORTS_DIRNAME)


def workspace_home(home=None):
    """`<home>/Workspace`: donde setup.sh instala en Mac/Linux si no había nada."""
    return os.path.join(home or os.path.expanduser("~"), HOME_DIRNAME)


def brains_dir(home=None):
    """`<home>/Workspace/Cerebros`: donde nacen los cerebros nuevos (Mac/Linux)."""
    return os.path.join(workspace_home(home), BRAINS_DIRNAME)


def exports_dir(home=None):
    """`<home>/Workspace/Respaldos`: zips que Workspace te deja (diagnóstico,
    respaldo del desinstalador). Fuera del Escritorio en todo sistema: en Mac
    no pide permiso de carpeta y en Windows un Escritorio de OneDrive no los
    sube a la nube."""
    return os.path.join(workspace_home(home), EXPORTS_DIRNAME)


def installed_root(home=None):
    """Raíz del harness al que apunta el comando `workspace` que dejó
    install.py (`~/.local/bin/workspace`, o el `.cmd` en Windows), o '' si no
    hay. Solo LEE ese archivo: no entra a la carpeta (que puede estar en el
    Escritorio) ni supone dónde está."""
    import re
    home = home or os.path.expanduser("~")
    for fn, rx in (("workspace", r'^exec "\$PY" "(.+)[\\/]front\.py"'),
                   ("workspace.cmd", r'^"[^"]+" "(.+)[\\/]front\.py"')):
        try:
            with open(os.path.join(home, ".local", "bin", fn), encoding="utf-8",
                      errors="replace") as fh:
                head = fh.read(4096)
        except OSError:
            continue
        for ln in head.splitlines():
            m = re.match(rx, ln.strip())
            if m:
                return m.group(1)
    return ""
