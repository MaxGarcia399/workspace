#!/usr/bin/env python3
"""WORKSPACE · proyectos_chat — el agente del panel derecho de la app «Proyectos».

El usuario elige CON QUÉ AGENTE hablar (los registrados en esta máquina) y le
escribe desde el panel derecho, tipo copiloto. El PROYECTO y el NODO seleccionados
viajan como CONTEXTO del mensaje: la conversación pasa a ser sobre algo concreto
del mapa, no un chat suelto que se pierde.

MODEL-AGNOSTIC (regla del harness): jamás se hardcodea un proveedor. Se invoca por
la abstracción NEUTRAL `headless.run_headless(..., backend=…)`; el backend sale de
`WORKSPACE_PROYECTOS_BACKEND` (default: el motor conectado del harness). Mismo patrón
que dash/dev/lavish.py.

SEGURIDAD
  · `tools="gen"`: el agente NO tiene manos (sin tools, sin MCP) — conversa, no
    ejecuta. A diferencia de tools="none" no fuerza plan-mode (que haría al modelo
    intentar explorar en vez de responder).
  · Cero-fuga: todo error pasa por `_scrub` (nada de rutas del host al navegador).
  · El texto del agente se pinta como TEXTO (el front usa textContent) — no HTML.

HONESTIDAD (regla dura): sin driver conectado NO se finge una respuesta. Se
devuelve {ok:False, stub:True} con el motivo real y se persiste una nota de
sistema en el hilo — nunca un mensaje `assistant` inventado.
"""
import os
import re

try:
    import headless
except Exception:                     # amputable: sin headless la app sigue viva
    headless = None

import proyectos_store as store

_MSG_MAX = 4000                       # cota del mensaje del usuario
_TIMEOUT = 180                        # s por vuelta (una respuesta, no una tarea)
_HIST = 8                             # vueltas de historial que viajan al prompt
_HOST_PATH_RX = re.compile(r"(/Users/[^/\s]+|/home/[^/\s]+|[A-Z]:\\[^\s]+)\S*")

_IDENT_MAX = 4000                     # cota del CLAUDE.md que viaja como identidad

_RULES = (
    "El usuario organiza sus proyectos en un MAPA CONCEPTUAL (nodos conectados) y "
    "te escribe desde el panel lateral de la app «Proyectos», con un proyecto (y a "
    "veces un nodo) seleccionados. Te paso ese CONTEXTO abajo. Responde a su "
    "petición sobre ese contexto: ayúdale a pensar, desglosar, priorizar y redactar.\n"
    "REGLAS DEL PANEL:\n"
    "- Responde en TEXTO PLANO conversacional (sin markdown pesado, sin HTML, sin "
    "bloques de código salvo que te los pidan). El panel es angosto: sé breve y "
    "concreto — pocas frases, listas cortas con guiones si hace falta.\n"
    "- No inventes datos del proyecto que no estén en el contexto. Si te falta "
    "información, dilo y pregunta.\n"
    "- AQUÍ no tienes herramientas: no puedes leer archivos ni ejecutar nada, aunque "
    "tu identidad diga que sí. No lo simules: si algo exige leer o correr algo, dilo."
)


def _identity(brain):
    """La identidad del agente, como TEXTO, leída de `<cerebro>/CLAUDE.md`.

    POR QUÉ a mano y no por el runtime: el harness invoca el motor con
    `--setting-sources ""` (endurecimiento de Argus: no heredar las allow-rules
    del socio en una invocación sin manos). Ese flag también apaga la carga
    automática del CLAUDE.md del cwd → el agente nacía SIN identidad y los cinco
    respondían igual («Soy Claude»), volviendo cosmético el selector de agente.
    Verificado con el CLI real: corriendo en el cerebro de un agente y preguntando
    «¿quién eres?», respondía Claude a secas.

    Se inyecta el mismo archivo que el runtime habría cargado, pero como texto del
    prompt que nosotros controlamos — sin reabrir la puerta que Argus cerró.
    Falla-suave: sin CLAUDE.md legible se devuelve "" y el agente sigue siendo útil
    (genérico), que es exactamente lo de hoy.
    """
    try:
        with open(os.path.join(brain, "CLAUDE.md"), encoding="utf-8") as fh:
            return fh.read(_IDENT_MAX).strip()
    except Exception:
        return ""


def build_system(agent, identity):
    """El bloque de sistema: QUIÉN eres + cómo se responde en este panel."""
    who = ("Eres «%s», uno de los agentes de WORKSPACE. El usuario te eligió A TI de "
           "entre varios agentes: mantén TU identidad, tu voz y tu criterio.\n" % agent)
    if identity:
        who += ("\n=== TU IDENTIDAD (de tu propio cerebro) ===\n%s\n"
                "=== FIN DE TU IDENTIDAD ===\n\n" % identity)
    return who + _RULES


def _scrub(s):
    """Redacta rutas absolutas del host en texto libre. Jamás levanta."""
    try:
        return _HOST_PATH_RX.sub("‹ruta›", s or "")
    except Exception:
        return s or ""


def _brains():
    """{agente: ruta_del_cerebro} de los agentes registrados en esta máquina.
    Mismo discovery que el dispatcher (lo hace messages). Falla-suave: {}."""
    try:
        import messages
        return messages.registered_brains()
    except Exception:
        return {}


def agents():
    """Nombres de los agentes disponibles para chatear, ordenados. [] si no hay."""
    return sorted(_brains().keys())


def _backend():
    """Backend del copiloto: el motor conectado (override
    WORKSPACE_PROYECTOS_BACKEND). NUNCA hardcodea proveedor."""
    return (os.environ.get("WORKSPACE_PROYECTOS_BACKEND")
            or getattr(headless, "DEFAULT_BACKEND", "claude-code")).strip()


def _path_to(proj, node):
    """Ruta del nodo desde la raíz («Raíz › Rama › Nodo») — ubica al agente en el
    mapa. Anti-ciclo (un JSON tocado a mano no debe colgar el server)."""
    by_id = {n["id"]: n for n in proj["nodes"]}
    chain, seen, cur = [], set(), node
    while cur is not None and cur["id"] not in seen:
        seen.add(cur["id"])
        chain.append(cur["t"])
        cur = by_id.get(cur["p"]) if cur["p"] else None
    return " › ".join(reversed(chain))


def _kids(proj, nid):
    return [n for n in proj["nodes"] if n["p"] == nid]


_ST_LABEL = {"todo": "pendiente", "doing": "en curso", "done": "hecho"}


def build_context(proj, node):
    """El contexto que viaja con el mensaje: dónde está parado el usuario."""
    total = len(proj["nodes"])
    done = len([n for n in proj["nodes"] if n["st"] == "done"])
    L = ["PROYECTO: %s" % proj["name"],
         "MAPA: %d nodos · %d hechos" % (total, done)]
    if node is None:
        # Sin nodo: un índice corto del mapa (las ramas de primer nivel) para que
        # el agente sepa de qué se compone el proyecto sin volcarle todo el árbol.
        root = next((n for n in proj["nodes"] if n["root"]), None)
        if root:
            branches = _kids(proj, root["id"])[:12]
            if branches:
                L.append("RAMAS: " + " · ".join(
                    "%s (%s)" % (b["t"], _ST_LABEL.get(b["st"], b["st"]))
                    for b in branches))
        L.append("NODO SELECCIONADO: ninguno (el usuario pregunta sobre el "
                 "proyecto completo)")
        return "\n".join(L)
    L.append("NODO SELECCIONADO: %s" % _path_to(proj, node))
    L.append("ESTADO DEL NODO: %s" % _ST_LABEL.get(node["st"], node["st"]))
    if node["notes"]:
        L.append("NOTAS DEL NODO:\n%s" % node["notes"][:2000])
    kids = _kids(proj, node["id"])[:12]
    if kids:
        L.append("SUB-NODOS: " + " · ".join(
            "%s (%s)" % (k["t"], _ST_LABEL.get(k["st"], k["st"])) for k in kids))
    return "\n".join(L)


def build_prompt(context, chat, user_msg, agent="", identity=""):
    """sistema (identidad + reglas) + contexto del mapa + historial + petición.

    El historial nombra a CADA agente que contestó: el hilo es compartido —
    el usuario cambia de agente con las flechas y sigue la misma conversación —
    así que «Agente:» a secas le hacía creer al que entra que él dijo lo que dijo
    otro."""
    hist = ""
    for m in (chat or [])[-_HIST:]:
        if m.get("role") == "system":
            continue                  # notas de la app, no conversación
        who = "Usuario" if m.get("role") == "user" else (m.get("agent") or "Agente")
        hist += "%s: %s\n" % (who, (m.get("text") or "")[:600])
    return ("%s\n\n=== CONTEXTO DEL MAPA ===\n%s\n\n=== CONVERSACIÓN PREVIA ===\n%s\n"
            "=== MENSAJE DEL USUARIO ===\n%s\n" %
            (build_system(agent, identity), context, hist or "(primera vuelta)",
             user_msg))


def _invoke(prompt, cwd):
    """Invoca al agente por la abstracción neutral. (ok, salida)."""
    if headless is None:
        return False, "headless.py ausente — no puedo invocar al agente"
    try:
        return headless.run_headless(prompt, backend=_backend(), tools="gen",
                                     cwd=cwd, timeout=_TIMEOUT)
    except headless.HeadlessError as e:
        return False, "backend: %s" % e
    except Exception as e:            # falla-suave dura: el panel nunca revienta
        return False, "%s: %s" % (type(e).__name__, e)


def api_chat(data):
    """POST /api/proyectos/chat {project_id, node_id?, agent, text}

    → {ok, chat, reply}                      respuesta real del agente
    → {ok:False, stub:True, error, chat}     sin motor: honesto, no inventa nada
    """
    try:
        pid = data.get("project_id")
        text = (data.get("text") or "")
        text = text.strip()[:_MSG_MAX] if isinstance(text, str) else ""
        if not text:
            return {"ok": False, "error": "mensaje vacío"}
        proj, node = store.context_of(pid, data.get("node_id"))
        if proj is None:
            return {"ok": False, "error": "proyecto inexistente"}
        brains = _brains()
        agent = data.get("agent")
        if agent not in brains:
            # Sin agente válido no hay a quién preguntarle: se guarda el mensaje
            # del usuario (no se pierde) + la nota honesta.
            why = ("no hay agentes registrados en esta máquina"
                   if not brains else "agente no registrado: elige uno de la lista")
            r = store.append_chat(pid, [
                {"role": "user", "text": text, "agent": ""},
                {"role": "system", "text": why}])
            return {"ok": False, "stub": True, "error": why,
                    "chat": r.get("chat", [])}

        history = store.chat_of(pid)
        prompt = build_prompt(build_context(proj, node), history, text,
                              agent=agent, identity=_identity(brains[agent]))
        ok, raw = _invoke(prompt, brains[agent])
        reply = _scrub((raw or "").strip())
        if not ok or not reply:
            # STUB HONESTO: el motor no está conectado (o no respondió). NO se
            # fabrica una respuesta del agente — se deja constancia de por qué.
            why = reply if not ok else "el agente respondió vacío"
            note = ("sin respuesta de %s — %s. (El chat necesita un motor "
                    "conectado; tu mensaje quedó guardado.)" % (agent, why))
            r = store.append_chat(pid, [
                {"role": "user", "text": text, "agent": agent},
                {"role": "system", "text": note}])
            return {"ok": False, "stub": True, "error": note,
                    "chat": r.get("chat", [])}
        r = store.append_chat(pid, [
            {"role": "user", "text": text, "agent": agent},
            {"role": "assistant", "text": reply, "agent": agent}])
        return {"ok": True, "reply": reply, "chat": r.get("chat", [])}
    except Exception as e:
        return {"ok": False, "error": "chat: %s" % type(e).__name__}


def api_agents(query=None):
    """GET /api/proyectos/agents → {ok, agents, aviso?}"""
    ags = agents()
    out = {"ok": True, "agents": ags}
    if not ags:
        out["aviso"] = ("sin agentes registrados — agrega uno desde el hub para "
                        "poder chatear")
    return out
