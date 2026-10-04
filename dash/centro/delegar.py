#!/usr/bin/env python3
"""WORKSPACE · dash.centro.delegar — delegación ESTRUCTURADA por el bus.

El «delegar sin escribir un prompt» real (ARQUITECTURA.md §3): lo que hoy es
`messages.py send --body "texto libre"` se vuelve un ENCARGO con formato — el
bus no cambia (sigue siendo un .md con frontmatter en <cerebro>/msgs/), solo
el body se estructura como YAML-plano que cualquier agente (o humano) parsea:

    task_id: a1b2c3d
    fase: plan
    proyecto: harness-ui
    rama: feat/x
    modelo: heredar
    titulo: "…"
    done_cuando:
      - …
    idea: |
      …

Ciclo (v1 — sesiones vivas + heartbeat, DECISIONES.md §7): el capitán delega →
misión en taskboard + encargo por el bus → el agente drena su inbox al boot /
en su turno → si fase=plan responde con plan vía `reply --approval` → el
capitán aprueba (transition plan→exec) → el agente ejecuta y reporta progreso
(`workspace centro progreso`) → entrega (exec→review) → el capitán cierra.
⚠ El runner headless (v2) y el consumo automático NO viven aquí.

Trazabilidad: cada envío queda atado a la misión (msg_ids + history). Tests:
`brains` inyectable en todo el camino (messages.send lo acepta) — un dict a
cerebros temporales = CERO spam a cerebros reales.
"""
import sys

from dash.centro import tareas

_SUBJECT_PREFIX = "[centro:%s]"


def _top_messages():
    """Import del bus con ROOT en sys.path si hace falta. Puede levantar —
    los llamadores envuelven."""
    try:
        import messages
        return messages
    except ImportError:
        import os
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)
        import messages
        return messages


def _yaml_str(s):
    """Escalar YAML-plano seguro: comillas dobles con escapes mínimos. El body
    lo leen agentes/humanos — no hace falta un dumper completo, solo no romper."""
    s = str(s or "")
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def build_body(mission, idea=""):
    """El body YAML-plano del encargo, desde la vista limpia de una misión.
    `idea` = texto libre de contexto (va al final como bloque literal)."""
    lines = [
        "task_id: %s" % mission.get("id", ""),
        "fase: %s" % mission.get("phase", "plan"),
        "proyecto: %s" % (mission.get("project") or "-"),
        "rama: %s" % (mission.get("branch") or "-"),
        "modelo: %s" % (mission.get("model") or "heredar"),
        "titulo: %s" % _yaml_str(mission.get("title")),
    ]
    if mission.get("idea_ref"):
        lines.append("idea_ref: %s" % mission["idea_ref"])
    crits = mission.get("done_cuando") or []
    if crits:
        lines.append("done_cuando:")
        for c in crits:
            lines.append("  - %s" % " ".join(str(c).split()))
    idea = str(idea or "").strip()
    if idea:
        lines.append("idea: |")
        for ln in idea.splitlines():
            lines.append("  " + ln)
    lines.append("")
    lines.append("# Protocolo: fase plan → responde tu PLAN con "
                 "`messages.py reply <id> \"…\" ` (el capitán lo aprueba desde el Centro).")
    lines.append("# Progreso en exec: `workspace centro progreso %s <pct>` · "
                 "entrega: `workspace centro fase %s review --por %s`"
                 % (mission.get("id", ""), mission.get("id", ""),
                    mission.get("agent", "<agente>")))
    return "\n".join(lines)


def delegar(mission_id, by, idea="", requires_approval=False, brains=None):
    """Manda el encargo estructurado de una misión EXISTENTE a su agente por el
    bus, y ata los msg_ids a la misión. → {ok, msg_ids, mission} o {ok:False,
    error}. `brains` inyectable (tests / registries alternos) — con None usa el
    registry real: eso ENVÍA de verdad."""
    mission = tareas.get_mission(mission_id)
    if mission is None:
        return {"ok": False, "error": "misión desconocida"}
    if mission.get("archived"):
        return {"ok": False, "error": "misión archivada (restaurar antes de delegar)"}
    agent = mission.get("agent") or ""
    if not agent:
        return {"ok": False, "error": "la misión no tiene agente asignado"}
    actor = str(by or "").strip().lower()
    if not actor:
        return {"ok": False, "error": "falta `by` (quién delega)"}
    if actor == agent:
        return {"ok": False, "error": "un agente no se delega a sí mismo"}
    try:
        messages = _top_messages()
        subject = "%s %s" % (_SUBJECT_PREFIX % mission["id"], mission.get("title", ""))
        ids = messages.send(actor, agent, "encargo", subject,
                            body=build_body(mission, idea=idea),
                            requires_approval=bool(requires_approval),
                            brains=brains)
    except Exception as e:
        return {"ok": False, "error": "el bus no está disponible (%s)" % type(e).__name__}
    if not ids:
        return {"ok": False,
                "error": "no se pudo enviar (¿cerebro de %s resuelto en esta máquina?)"
                         % agent}
    for mid in ids:
        tareas.attach_msg(mission["id"], mid, ev="delegada", by=actor)
    return {"ok": True, "msg_ids": ids, "mission": tareas.get_mission(mission["id"])}


def delegar_nueva(title, agent, by, project="", branch="", model="heredar",
                  idea="", idea_ref=None, done_cuando=None, phase="plan",
                  requires_approval=False, brains=None):
    """El flujo completo de un click: CREA la misión en el taskboard y manda el
    encargo por el bus. → {ok, id, msg_ids, mission} o {ok:False, error} (si el
    envío falla, la misión CREADA se conserva — se puede re-delegar)."""
    res = tareas.create(title, agent, project=project, branch=branch,
                        model=model, idea_ref=idea_ref, done_cuando=done_cuando,
                        phase=phase, by=by)
    if not res.get("ok"):
        return res
    mid = res["id"]
    out = delegar(mid, by, idea=idea, requires_approval=requires_approval,
                  brains=brains)
    out["id"] = mid           # la misión existe aunque el envío haya fallado
    return out
