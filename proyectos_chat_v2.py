#!/usr/bin/env python3
"""WORKSPACE · proyectos_chat_v2 — ensamblado de contexto del chat para el modelo v2.

COEXISTE con `proyectos_chat` (v1, EN VIVO). Este módulo NO está wireado a ninguna
ruta: `proyectos.py` sigue apuntando a `proyectos_chat.api_chat` (hilo único por
proyecto). Aquí está lista la variante v2 para el FLIP (F6, lo aprueba el socio):

    v1 (vivo):  historial = store.chat_of(pid)                  ← un hilo por proyecto
    v2 (aquí):  historial = fsstore.recent_turns(pid,nid,agent) ← hilo por (nodo×agente)
                          + fsstore.get_resumen(pid,nid)        ← handoff del nodo

INVARIANTES PRESERVADOS (se REUSAN de proyectos_chat, no se reimplementan):
  · MODEL-AGNOSTIC: la invocación pasa por `proyectos_chat._invoke` →
    `_backend()` → `headless.run_headless(tools="gen")`. Cero proveedor hardcodeado.
  · STUB HONESTO: sin motor conectado NO se inventa respuesta — se persiste una
    nota de sistema en la sesión y se devuelve {ok:False, stub:True}.
  · `_scrub`: todo texto del agente al navegador pasa por el redactor de rutas.
  · Identidad inyectada como texto (el harness corre con `--setting-sources ""`).

Diferencia de PERSISTENCIA: v1 hace `store.append_chat`; v2 hace
`fsstore.append_session` (por nodo×agente×día). El estado v2 vive en la carpeta
del harness, no en el `proyectos.json` monolítico.
"""
import proyectos_chat as chat
import proyectos_fsstore as fs

#: regla de HANDOFF que viaja en el contexto: el panel es sin-manos (tools="gen"),
#: así que el agente no escribe archivos; se le pide que, al cerrar, PRODUZCA un
#: handoff conciso que el usuario/app guarda vía `fsstore.set_resumen`. Honesto
#: con la capacidad real (no promete que el agente toque el disco solo).
_HANDOFF_RULE = (
    "- HANDOFF DEL NODO: si estás cerrando trabajo, ofrece al final un RESUMEN "
    "breve para retomar después (estado, avances, pendientes, punteros a los "
    "archivos del nodo). Conciso — es un handoff, no un volcado; el usuario lo "
    "guardará como el resumen del nodo.")


def build_context_v2(proj, node, resumen):
    """Contexto v1 (mapa/nodo) + el resumen.md del nodo + la regla de handoff.
    Reusa `chat.build_context` — misma forma, solo se le suma el handoff."""
    ctx = chat.build_context(proj, node)
    if resumen and resumen.strip():
        ctx += ("\n\n=== HANDOFF DEL NODO (resumen.md — léelo primero) ===\n%s"
                % resumen.strip()[:4000])
    ctx += "\n\n=== INSTRUCCIÓN DE CIERRE ===\n%s" % _HANDOFF_RULE
    return ctx


def _history_as_chat(turns, agent):
    """Vueltas de sesión (fsstore) → forma que espera `chat.build_prompt`
    ({role, agent, text}). En una sesión por-agente, el `assistant` es ESE agente."""
    return [{"role": t["role"],
             "agent": agent if t["role"] != "user" else "",
             "text": t["text"]} for t in turns]


def api_chat_v2(data):
    """POST v2 {project_id, node_id, agent, text} — MISMA API externa que
    `proyectos_chat.api_chat`, pero el hilo es por (nodo×agente) y persiste en
    sesiones/. Devuelve {ok, reply, chat} o el stub honesto. NO wireado aún."""
    try:
        pid = data.get("project_id")
        nid = data.get("node_id")
        text = data.get("text") or ""
        text = text.strip()[:chat._MSG_MAX] if isinstance(text, str) else ""
        if not text:
            return {"ok": False, "error": "mensaje vacío"}
        proj, node = fs.context_of(pid, nid)
        if proj is None:
            return {"ok": False, "error": "proyecto inexistente"}
        if node is None:                 # sin nodo → la sesión cuelga de la raíz
            node = next((n for n in proj["nodes"] if n["root"]), None)
        if node is None:
            return {"ok": False, "error": "nodo inexistente"}
        nid = node["id"]

        brains = chat._brains()
        agent = data.get("agent")
        if agent not in brains:
            why = ("no hay agentes registrados en esta máquina" if not brains
                   else "agente no registrado: elige uno de la lista")
            slug = agent if isinstance(agent, str) and agent else "sistema"
            fs.append_session(pid, nid, slug, "user", text)
            fs.append_session(pid, nid, slug, "system", why)
            return {"ok": False, "stub": True, "error": why,
                    "chat": fs.read_session(pid, nid, slug)}

        resumen = fs.get_resumen(pid, nid)
        history = _history_as_chat(fs.recent_turns(pid, nid, agent, chat._HIST),
                                   agent)
        prompt = chat.build_prompt(build_context_v2(proj, node, resumen),
                                   history, text, agent=agent,
                                   identity=chat._identity(brains[agent]))
        ok, raw = chat._invoke(prompt, brains[agent])
        reply = chat._scrub((raw or "").strip())
        if not ok or not reply:
            why = reply if not ok else "el agente respondió vacío"
            note = ("sin respuesta de %s — %s. (El chat necesita un motor "
                    "conectado; tu mensaje quedó guardado.)" % (agent, why))
            fs.append_session(pid, nid, agent, "user", text)
            fs.append_session(pid, nid, agent, "system", note)
            return {"ok": False, "stub": True, "error": note,
                    "chat": fs.read_session(pid, nid, agent)}
        fs.append_session(pid, nid, agent, "user", text)
        fs.append_session(pid, nid, agent, "assistant", reply)
        return {"ok": True, "reply": reply,
                "chat": fs.read_session(pid, nid, agent)}
    except Exception as e:               # falla-suave dura: el panel nunca revienta
        return {"ok": False, "error": "chat: %s" % type(e).__name__}
