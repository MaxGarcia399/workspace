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
  · **Dueño de la sesión**: anota en el registro de corridas de qué pestaña
    es la sesión `session_id` del payload (engines/hermes.run_de_sesion). Así,
    al cerrar, una pestaña jamás se queda con la conversación de otra pestaña
    abierta en el mismo cerebro.
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

**La pestaña sale de la SESIÓN, nunca del entorno.** Desde v0.22.5 el hook
corre dentro del gateway compartido de Hermes, con el entorno (WORKSPACE_*)
de la pestaña que lo arrancó, que puede ser otra o ya estar cerrada: con él,
una pestaña recibía la memoria, la pestaña y el tono de otra (prueba real
2026-10-26). Por eso el hook borra de su proceso las variables de pestaña y
saca cerebro, pestaña, corrida y agente de la corrida dueña de la sesión
(engines/hermes.dueno_de_sesion: la miga de la terminal, la sesión anotada o
su registro oficial, con evidencia). Sin corrida viva que la reconozca no
manda memoria de ninguna pestaña: a lo más el tono del agente de su cerebro,
si se sabe. Mejor nada que lo ajeno.

En los turnos headless de Workspace (HERMES_SESSION_SOURCE=tool, o un registro
de origen `tool`) no hace nada.

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


#: Variables de PESTAÑA: en un gateway (v0.22.5) son las de la pestaña que lo
#: arrancó. Se borran de este proceso antes de todo, para que ninguna función
#: de abajo las tome como de esta sesión (memoria, socio, pestaña, motor).
_DE_PESTANA = ("WORKSPACE_HERMES_RUN", "WORKSPACE_HERMES_SESSION", "WORKSPACE_BRAIN",
               "WORKSPACE_WS", "ZENITH_WS", "WORKSPACE_WID", "WORKSPACE_AGENT_NAME",
               "WORKSPACE_ENGINE", "WORKSPACE_SESSION_ENGINE", "WORKSPACE_ENGINE_LABEL",
               "WORKSPACE_SESSION_ID", "WORKSPACE_SESSION_PID")


def main():
    try:
        import _utf8          # BYTES → UTF-8: en Windows stdin es cp1252
        data = _utf8.json_de_stdin()
    except Exception:
        data = {}
    if str(data.get("hook_event_name") or "pre_llm_call") != "pre_llm_call":
        return 0
    if os.environ.get("HERMES_SESSION_SOURCE", "").strip().lower() == "tool":
        return 0
    try:
        from engines import hermes as _h
        gateway = _h.en_gateway()
    except Exception:
        return 0
    # Fuera de un gateway (hasta v0.22.2) el entorno es el de esta pestaña: su
    # corrida es la pista; en un gateway es el de otra pestaña y no cuenta.
    pista = "" if gateway else os.environ.get("WORKSPACE_HERMES_RUN", "").strip()
    for k in _DE_PESTANA:
        os.environ.pop(k, None)
    perfil = str(data.get("profile") or "").strip()
    if perfil and perfil != "default":
        os.environ["WORKSPACE_HERMES_PROFILE"] = perfil   # el perfil que disparó el hook
    sid = str(data.get("session_id") or "")
    if not sid:
        return 0
    try:
        dueno = _h.dueno_de_sesion(sid, pista=pista, gateway=gateway,
                                   cwd="" if gateway else str(data.get("cwd") or ""))
        run = dueno.get("run") or ""
        rec = _h.run_info(run) if run else {}
        cerebro = rec.get("brain") or dueno.get("brain") or ""
    except Exception:
        return 0
    partes = []
    try:
        import personalidad
        # el agente de la corrida; en una corrida de antes (sin `agent`) o en
        # una sesión sin dueña de un cerebro conocido, el de ese cerebro
        agente = str(rec.get("agent") or "").strip().lower()
        if not agente and cerebro:
            agente = personalidad.agente_de(cerebro)
        if agente or run:
            txt = personalidad.linea(agente or None)
            if txt:
                partes.append(txt)
    except Exception:
        pass
    if not run:
        # sin corrida viva que la reconozca: a lo más el tono, nunca la
        # memoria de una pestaña (mejor nada que lo ajeno)
        if partes:
            sys.stdout.write(json.dumps({"context": "\n\n".join(partes)}, ensure_ascii=False))
        return 0
    try:
        extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
        mem = _h.memoria_turno(run, sid, primer_turno=extra.get("is_first_turn") is True)
        if mem:
            partes.append(mem)
    except Exception:
        pass
    try:
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
