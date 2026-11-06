#!/usr/bin/env python3
"""WORKSPACE hook · turn_end — la maleta al terminar cada respuesta (memoria v1).

En Claude Code es el hook oficial `Stop` (corre cuando el agente termina de
responder; no corre si el socio interrumpe la respuesta). Doc:
https://code.claude.com/docs/en/hooks#stop

Por qué: la maleta se arma al cerrar (memoria_cierre.py, en SessionEnd). Si
Claude Code muere sin cerrar (kill -9, se cuelga la máquina, se va la luz),
SessionEnd no corre y la pestaña se quedaba sin maleta hasta el siguiente
cierre normal. Con este hook la maleta ya trae hasta la última respuesta.

Hace SOLO el paso 1 de memoria.al_cerrar (memoria.maleta_al_turno): sin IA, en
milisegundos e idempotente (si nada cambió, no reescribe). Lo demás del cierre
(subir a MEMORY.md, compactar, archivar) sigue en SessionEnd.

La respuesta final la toma de `last_assistant_message` del payload: la doc
avisa que el transcript puede no traerla todavía en el momento del Stop.

Se cablea POR ARRANQUE (events.POR_ARRANQUE): va en el `--settings` de la
pestaña que arma memoria.claude_settings_args, no en el settings.local.json
del cerebro. Lee el payload JSON de stdin. Silencioso y falla-suave: jamás
imprime ni bloquea (Stop con salida 2 haría seguir al agente; aquí siempre 0).
Kill-switch: WORKSPACE_NO_MEMORIA=1 (el mismo de memoria_cierre).
Cero dependencias (3.9+).
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)   # append: no cambia qué módulo homónimo de hooks/ gana


def main():
    if os.environ.get("WORKSPACE_NO_MEMORIA"):
        return False
    # el lanzador de hoy siempre exporta WORKSPACE_WS (este hook solo llega en
    # el --settings que arma ese mismo lanzador)
    tab = (os.environ.get("WORKSPACE_WS") or "").strip()
    if not tab:
        return False                   # sesión sin pestaña: no hay maleta
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    transcript = data.get("transcript_path") or ""
    brain = os.environ.get("WORKSPACE_BRAIN") or data.get("cwd") or ""
    if not (transcript and brain):
        return False
    ultima = data.get("last_assistant_message")
    import memoria
    return memoria.maleta_al_turno(brain, tab, motor="claude-code",
                                   transcript=os.path.expanduser(str(transcript)),
                                   ultima=ultima if isinstance(ultima, str) else "")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
