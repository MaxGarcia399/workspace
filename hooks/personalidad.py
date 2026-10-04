#!/usr/bin/env python3
"""WORKSPACE hook · SessionStart + UserPromptSubmit — inyecta el TONO del socio.

Dos eventos, dos dosis (personalidad.py decide el texto):

  · **SessionStart** → `personalidad.bloque()`: los diales movidos con su
    instrucción completa, una vez, al abrir la pestaña.
  · **UserPromptSubmit** → `personalidad.linea()`: el recordatorio compacto en
    CADA mensaje. Es lo que hace que mover un dial se sienta **al siguiente
    mensaje**, sin reabrir la sesión (pedido del socio 2026-09-24).

El evento se distingue por `hook_event_name` del payload; si no viniera, se
asume el bloque completo (degradación benigna: como mucho, se repite).

FALLA-SUAVE ABSOLUTA: cualquier error → exit 0 sin escribir nada. Un hook
jamás puede impedir que el socio abra una sesión ni que mande un mensaje.

COSTE CERO POR DEFECTO: con todos los diales en 3 el texto es "" y no se
imprime nada — ni un token de contexto, en ninguno de los dos eventos.

Per-agente: `WORKSPACE_AGENT_NAME` (lo exporta el launcher) o, si no está, se
resuelve por el `cwd` del payload contra el registry de cerebros.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import json
import os
import sys

try:   # Windows: un hook capturado en cp1252 reventaría con acentos.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _payload():
    try:
        return json.loads(sys.stdin.read() or "{}") or {}
    except Exception:
        return {}


def main():
    data = _payload()
    try:
        import personalidad
        evento = str(data.get("hook_event_name") or "")
        agente = personalidad.agente_de(data.get("cwd")) or None
        if "Prompt" in evento:
            txt = personalidad.linea(agente)
            nombre = "UserPromptSubmit"
        else:
            txt = personalidad.bloque(agente)
            nombre = "SessionStart"
        if not txt:
            return 0                     # neutro → silencio absoluto
        sys.stdout.write(json.dumps(
            {"hookSpecificOutput": {"hookEventName": nombre,
                                    "additionalContext": txt}},
            ensure_ascii=False))
    except Exception:
        pass                             # regla 6: nunca rompe nada
    return 0


if __name__ == "__main__":
    sys.exit(main())
