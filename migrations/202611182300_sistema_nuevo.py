"""AUTOMÁTICA: tus motores abren con el sistema nuevo de Workspace (el paquete por sesión).

Hasta 2026-11-18 el ajuste `arquitectura.paquete` venía apagado de fábrica: cada motor abría sin los hooks, el MCP
núcleo ni las skills de Workspace por sesión, salvo que el socio lo encendiera a mano. Ahora viene encendido
(settings.py). El store de ajustes guarda solo lo que el socio fijó, así que:

- quien nunca lo tocó queda en el sistema nuevo con esta actualización, sin mover ningún archivo;
- quien lo apagó a mano queda apagado (su elección se respeta) y no recibe aviso.

Qué hace (KIND "auto", sin preguntar): deja pendiente el aviso de una línea que sale al abrir un agente
(arquitectura/sistema_nuevo.aviso_pendiente). No toca la config de ningún motor ni ningún cerebro.

Compatibilidad hacia atrás: una versión anterior lee el default de su propio settings.py (apagado) y abre como
antes; nada que deshacer al volver (sin UNDO_AL_VOLVER: deshacer al volver dejaría el ajuste apagado a mano y la
próxima versión ya no lo encendería).

Deshacer: undo() apaga el ajuste a mano (los motores abren como antes) y lo dice. Volver: `workspace settings set
arquitectura.paquete on`.
"""
import os

TITLE = {"es": "Tus motores abren con el sistema nuevo de Workspace (hooks, MCP y skills por sesión)",
         "en": "Your engines open with the new Workspace system (per-session hooks, MCP and skills)"}
KIND = "auto"
MID = "202611182300_sistema_nuevo"


def _misma_maquina(ctx):
    """Los ajustes de settings son los del estado de ESTA corrida (un HOME de prueba no toca otro)."""
    try:
        import settings
        a = os.path.normcase(os.path.realpath(ctx.state_dir))
        b = os.path.normcase(os.path.realpath(settings._workspace_dir()))
        return a == b
    except Exception:
        return False


def needed(ctx):
    if not _misma_maquina(ctx):
        return False
    from arquitectura import sistema_nuevo
    return sistema_nuevo.elegido() is None


def run(ctx):
    from arquitectura import sistema_nuevo
    if ctx.dry_run:
        ctx.log("sistema nuevo: quedaría el aviso de una línea")
        return
    ctx.log("sistema nuevo: %s" % sistema_nuevo.migrar(ctx.state_dir))


def undo(ctx):
    if not _misma_maquina(ctx):
        return []
    from arquitectura import sistema_nuevo
    estado, msg = sistema_nuevo.deshacer(ctx.state_dir)
    return [("sistema nuevo", estado, msg)]
