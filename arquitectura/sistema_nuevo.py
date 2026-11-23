#!/usr/bin/env python3
"""WORKSPACE · arquitectura/sistema_nuevo — el paquete por sesión, encendido de fábrica también para quien actualiza.

El ajuste `arquitectura.paquete` viene en ON (settings.py). El store de ajustes guarda solo lo que el socio fijó, así
que quien nunca lo tocó queda en el sistema nuevo con la actualización, sin mover nada; quien lo apagó a mano queda
apagado. La migración `202611182300_sistema_nuevo` solo deja la marca del aviso de una línea (`aviso_pendiente`, que
sale al abrir un agente con una persona mirando) y su deshacer (`workspace migrate --undo <id>` lo apaga, como antes).

Encender y apagar es UN comando que existe (P2, puerta N5 19-nov: el aviso mandaba a `workspace settings set …`, que no
existe): `workspace sistema-nuevo` (dice cómo está), `… on`, `… off`. Nada se borra. Stdlib, falla-suave.
"""
import os
import subprocess
import sys
from contextlib import nullcontext

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

from arquitectura import estado_json
from olock import file_lock

MIGRACION_ID = "202611182300_sistema_nuevo"
AJUSTE = "arquitectura.paquete"
#: El comando (comandos.py · «sistema-nuevo»), con sus dos sentidos.
ENCENDER = "workspace sistema-nuevo on"
APAGAR = "workspace sistema-nuevo off"


def _t(key, es, en=None, **kw):
    try:
        import workspace_status
        return workspace_status.t(key, es, en, **kw)
    except Exception:
        return es.format(**kw) if kw else es


def _marca(state_dir=None):
    if not state_dir:
        import paths
        state_dir = paths.state_dir()
    return os.path.join(state_dir, "arquitectura", "sistema-nuevo.json")


def elegido():
    """Lo que el socio fijó a mano (True/False) o None si nunca lo tocó (manda lo de fábrica)."""
    import settings
    return settings.get_stored(AJUSTE)


def migrar(state_dir=None):
    """La migración: sin elección del socio, el aviso queda pendiente. → "aviso" | "elegido"."""
    ruta = _marca(state_dir)
    with file_lock(ruta):
        if elegido() is not None:
            return "elegido"
        d = estado_json.leer(ruta, apartar=True)
        if d.get("aviso") not in ("mostrado", "deshecho", "pendiente"):
            d["aviso"] = "pendiente"
            estado_json.escribir(ruta, d)
    return "aviso"


def _apagado_texto():
    return _t("arq.sistema_nuevo.deshecho",
              "los motores vuelven a abrir como antes, sin el paquete por sesión. Para volver al sistema nuevo: "
              + ENCENDER,
              "engines open as before again, without the per-session package. To go back to the new system: "
              + ENCENDER)


def deshacer(state_dir=None):
    """`workspace migrate --undo`: el paquete apagado (el ajuste a mano: no se vuelve a encender solo), el aviso
    retirado y el plugin de OpenClaw apagado con él (revisor 3). → (estado, mensaje) para migrate.undo."""
    _apagar(state_dir)
    texto = _apagado_texto()
    if not _sincronizar_openclaw(avisar=False):
        texto += " " + _SIN_SINCRONIZAR
    return ("undone", texto)


def _apagar(state_dir=None):
    """El ajuste en apagado y el aviso retirado, bajo el candado del aviso. Un aviso dañado ya no frena el apagado
    (revisor, bloqueo de integración): estado_json lo aparta y lo avisa, y aquí se sigue con uno nuevo."""
    import settings
    ruta = _marca(state_dir)
    with file_lock(ruta):
        settings.set(AJUSTE, False)
        try:
            d = estado_json.leer(ruta, apartar=True)
        except ValueError:
            d = {}
        d["aviso"] = "deshecho"
        estado_json.escribir(ruta, d)


def aviso_pendiente(marcar=True, state_dir=None):
    """La línea de «ya estás en el sistema nuevo», UNA vez tras actualizar (si el socio no lo apagó antes), o None."""
    try:
        ruta = _marca(state_dir)
        with (file_lock(ruta) if marcar else nullcontext()):
            d = estado_json.leer(ruta, apartar=marcar)
            if d.get("aviso") != "pendiente":
                return None
            apagado = elegido() is False
            if marcar:
                d["aviso"] = "mostrado"
                estado_json.escribir(ruta, d)
        if apagado:
            return None
        return _t("arq.sistema_nuevo.aviso",
                  "✓ Workspace ya abre tus motores con el sistema nuevo: sus hooks, el MCP y las skills de Workspace "
                  "por sesión, sin tocar su config. Para apagarlo: " + APAGAR,
                  "✓ Workspace now opens your engines with the new system: Workspace hooks, MCP and skills per "
                  "session, without touching their config. To turn it off: " + APAGAR)
    except Exception:
        return None


_SIN_SINCRONIZAR = "No pude sincronizar el plugin de OpenClaw. Se reintentará en la próxima apertura."


def _sincronizar_openclaw(avisar=True):
    """El plugin de OpenClaw como dice el ajuste (openclaw lo lee bajo su candado). → True si quedó así."""
    from engines import openclaw

    try:
        if openclaw.sincronizar_plugin():
            return True
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        pass
    if avisar:
        print(_SIN_SINCRONIZAR)
    return False


def cli(args=None):
    """`workspace sistema-nuevo [on | off]`: sin nada, cómo está; `on` lo enciende y `off` lo apaga (un ajuste de esta
    máquina; los motores lo toman al abrir su próxima sesión). → código de salida."""
    import settings
    args = [a for a in (args or []) if a]
    accion = (args[0] if args else "").strip().lower()
    if accion in ("", "estado", "status"):
        valor = settings.get(AJUSTE)
        de_fabrica = elegido() is None
        if valor:
            print(_t("arq.sistema_nuevo.cli.encendido",
                     "El sistema nuevo está encendido{f}: tus motores abren con los hooks, el MCP y las skills de "
                     "Workspace por sesión. Para apagarlo: " + APAGAR,
                     "The new system is on{f}: your engines open with Workspace hooks, MCP and skills per session. "
                     "To turn it off: " + APAGAR, f=" (de fábrica)" if de_fabrica else ""))
        else:
            print(_t("arq.sistema_nuevo.cli.apagado",
                     "El sistema nuevo está apagado: tus motores abren como antes. Para encenderlo: " + ENCENDER,
                     "The new system is off: your engines open as before. To turn it on: " + ENCENDER))
        return 0
    if accion in ("on", "encender", "prender", "si", "sí"):
        settings.set(AJUSTE, True)
        if not _sincronizar_openclaw():
            return 1
        print(_t("arq.sistema_nuevo.cli.on",
                 "✓ Encendido: tus motores abren con el sistema nuevo desde su próxima sesión. Para apagarlo: "
                 + APAGAR,
                 "✓ On: your engines open with the new system from their next session. To turn it off: " + APAGAR))
        return 0
    if accion in ("off", "apagar", "no"):
        fallo = None
        try:
            _apagar()                              # ajuste y aviso bajo candado (Greptile 4-6)
        except (OSError, ValueError) as e:
            fallo = e
        if elegido() is not False:                 # el ajuste no cambió: no hay nada que sincronizar
            print("No pude completar el apagado: %s" % fallo, file=sys.stderr)
            return 1
        if fallo is not None:                      # el ajuste sí: solo faltó la marca del aviso, que ya no sale
            print("WORKSPACE · no pude guardar la marca del aviso (%s); el apagado sí quedó." % fallo, file=sys.stderr)
        if not _sincronizar_openclaw():            # y el plugin de OpenClaw se apaga con él (Greptile 3)
            return 1
        print("✓ " + _apagado_texto()[:1].upper() + _apagado_texto()[1:])
        return 0
    print(_t("arq.sistema_nuevo.cli.uso", "Uso: workspace sistema-nuevo [on | off]",
             "Usage: workspace sistema-nuevo [on | off]"))
    return 2
