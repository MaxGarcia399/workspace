"""Del JSON de cada motor a los campos neutrales del contrato (arquitectura/momentos.json).

Los motores nombran distinto lo mismo (session_id, sessionId, conversation_id,
conversationId…). Aquí se buscan esos nombres; lo que el motor no manda queda
fuera. Nunca se copian los argumentos ni el resultado de una herramienta.
Formas sacadas de la documentación de cada motor; el probador las confirma."""
import os

_ID = ("session_id", "sessionId", "conversation_id", "conversationId", "chat_id", "chatId",
       "thread_id", "threadId")
_PROMPT = ("prompt", "user_prompt", "userPrompt", "lastUserInput", "message", "user_message")
_HERRAMIENTA = ("tool_name", "toolName", "tool")
_RESPUESTA = ("last_assistant_message", "lastAssistantMessage", "response", "text", "assistant_response")
#: Herramientas de escritura (para post_tool_write).
ESCRITURA = ("Write", "Edit", "NotebookEdit")


def _primero(d, claves):
    for k in claves:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def traducir(destino, momento, payload, env=None):
    """{"session_id", "cwd", …los campos del momento}. `payload` es el JSON del motor."""
    env = os.environ if env is None else env
    p = payload if isinstance(payload, dict) else {}
    if isinstance(p.get("extra"), dict):          # Hermes: lo propio de cada evento viene en `extra`
        p = dict(p["extra"], **{k: v for k, v in p.items() if k != "extra" and v not in (None, "")})
    out = {"session_id": _primero(p, _ID), "cwd": _primero(p, ("cwd",))}
    if not out["cwd"]:
        roots = p.get("workspace_roots") or p.get("workspacePaths") or []
        out["cwd"] = roots[0] if roots and isinstance(roots[0], str) else ""
    if momento == "session_start":
        out["source"] = _primero(p, ("source",)) or "startup"
    elif momento == "user_prompt":
        out["prompt"] = _primero(p, _PROMPT) or str(env.get("USER_PROMPT") or "")
    elif momento in ("pre_tool", "post_tool", "permission_request"):
        nombre = _primero(p, _HERRAMIENTA)
        llamada = p.get("toolCall") or p.get("tool_call")
        if not nombre and isinstance(llamada, dict):
            nombre = str(llamada.get("name") or "")
        out["tool_name"] = nombre
        if momento == "post_tool":
            out["ok"] = not (p.get("error") or p.get("hook_event_name") in ("PostToolUseFailure",
                                                                            "postToolUseFailure")
                             or str(p.get("status") or "").lower() in ("error", "failed"))
    elif momento == "turn_end":
        resp = _primero(p, _RESPUESTA)
        if resp:
            out["last_assistant_message"] = resp
        out["stop_hook_active"] = bool(p.get("stop_hook_active"))
    elif momento == "compact":
        evento = str(p.get("hook_event_name") or "")
        out["phase"] = "after" if "Post" in evento or "after" in evento else "before"
        out["trigger"] = _primero(p, ("trigger",))
    elif momento == "session_end":
        out["reason"] = _primero(p, ("reason", "terminationReason", "turn_exit_reason"))
    return out
