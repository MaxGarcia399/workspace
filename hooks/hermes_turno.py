#!/usr/bin/env python3
"""WORKSPACE hook de Hermes · pre_llm_call — una vez por TURNO del socio.

Hermes (v0.18.2) corre los shell hooks declarados en el `config.yaml` de SU
perfil; en `pre_llm_call` (una vez por turno, antes de llamar al modelo) un
stdout `{"context": "..."}` se ANEXA al mensaje del socio de ese turno (nunca
al system prompt; el mensaje limpio queda igual en su historial). Lo cablea
engines/hermes.py SOLO en el perfil propio de Workspace, jamás en el perfil
del socio. Hace cuatro cosas:

  · **Tono**: el mismo recordatorio que el hook de Claude Code
    (`personalidad.linea()`), para que mover un dial se sienta al siguiente
    mensaje sin reabrir la pestaña.
  · **Dueño de la sesión**: anota en el registro de corridas que la sesión
    `session_id` del payload es de ESTA pestaña (env WORKSPACE_HERMES_RUN, que
    exporta el launcher). Así, al cerrar, una pestaña jamás se queda con la
    conversación de otra pestaña abierta en el mismo cerebro.
  · **Memoria de la pestaña**: Hermes reusa el system prompt guardado al
    retomar una sesión, así que el bloque de la pestaña de AGENTS.md no le
    llega. Va aquí en el primer turno de una sesión que no lo trae y cuando la
    memoria cambió por fuera (otro motor, otra ventana); nunca en todos los
    turnos (engines/hermes.memoria_turno decide y guarda la marca). Empieza
    diciendo cuál es la pestaña de ESTA ventana y el comando exacto de
    memoria: el AGENTS.md es uno por cerebro y puede traer el bloque de otra
    (con el hook aprobado, el de esta ni pasa por ahí).
  · **Memoria larga del cerebro** (STATE/MEMORY.md): en el primer turno de
    una sesión nueva y, al retomarla, solo si cambió desde la última vez que
    se le mandó (Hermes la guarda en el historial: repetirla la acumulaba),
    dentro del tope del contexto del hook (engines/hermes.memoria_larga_turno).

En los turnos headless de Workspace (HERMES_SESSION_SOURCE=tool) no hace nada.

Se llama `hermes_turno` y NO `personalidad`: un script con el mismo nombre que
un módulo de la raíz se importaba a sí mismo (runbook agregar-motor §6).

FALLA-SUAVE ABSOLUTA: cualquier error → exit 0 sin escribir nada. Con todos
los diales en neutro y la memoria ya entregada no imprime nada (coste cero).

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import json
import os
import sys

try:   # Windows: un hook capturado en cp1252 reventaría con acentos.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not sys.path or sys.path[0] != ROOT:
    sys.path.insert(0, ROOT)


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}") or {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if str(data.get("hook_event_name") or "pre_llm_call") != "pre_llm_call":
        return 0
    if os.environ.get("HERMES_SESSION_SOURCE", "").strip().lower() == "tool":
        return 0
    run, sid = os.environ.get("WORKSPACE_HERMES_RUN", ""), str(data.get("session_id") or "")
    try:
        if run and sid:
            from engines import hermes as _h
            _h.run_claim(run, sid)
    except Exception:
        pass
    partes = []
    try:
        import personalidad
        txt = personalidad.linea(personalidad.agente_de(data.get("cwd")) or None)
        if txt:
            partes.append(txt)
    except Exception:
        pass
    try:
        if run and sid:
            from engines import hermes as _h
            extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
            mem = _h.memoria_turno(run, sid, primer_turno=extra.get("is_first_turn") is True)
            if mem:
                partes.append(mem)
    except Exception:
        pass
    try:
        if run and sid:
            from engines import hermes as _h
            larga = _h.memoria_larga_turno(run, sid, usado=len("\n\n".join(partes)))
            if larga:
                partes.append(larga)
    except Exception:
        pass
    if partes:
        sys.stdout.write(json.dumps({"context": "\n\n".join(partes)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
