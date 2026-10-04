#!/usr/bin/env python3
"""WORKSPACE · dash.centro.tareas — taskboard.json: misiones + máquina de fases.

El store que faltaba para el Centro de Control (ARQUITECTURA.md §2): cada
MISIÓN es una tarea delegable que atraviesa las 3 fases del protocolo:

    plan  →  exec  →  review  →  done
              ↑          │
              └──────────┘   (devolver)   review → plan (replantear)

ALMACENAMIENTO — per-máquina, NO versionado, independiente de la rama (mismo
patrón que dash/dev/board.py): ~/.claude/workspace/centro/taskboard.json
Escritura ATÓMICA (tmp con pid+token + os.replace), lock de módulo para
escritores en el MISMO proceso + olock para PROCESOS distintos (degrada a
sin-lock, jamás levanta), FALLA-SUAVE (ausente/corrupto → tablero vacío).
Never-delete: «borrar» = `archived: true`; no hay hard-delete aquí.

Modelo (taskboard.json):
  { "missions": [ {
      id, title, idea_ref, project, agent, model, branch,
      phase,                # plan | exec | review | done
      progress,             # 0-100 (solo avanza en exec; done ⇒ 100)
      done_cuando: [..],    # criterios de aceptación (editables en plan)
      msg_ids: [..],        # mensajes del bus atados (trazabilidad)
      history: [{t, ev, by, ...}],
      archived, created, updated } ] }

MÁQUINA DE FASES — el protocolo duro vive AQUÍ y solo aquí (ni el front ni el
CLI re-implementan reglas). Transiciones válidas y QUIÉN puede darlas:

    plan   → exec     capitán   (aprueba el plan — el agente NO se auto-aprueba)
    exec   → review   agente    (solo el agente asignado entrega)
    review → done     capitán   (acepta la entrega)
    review → exec     capitán   (devuelve con observaciones)
    review → plan     capitán   (replantear desde cero)

«capitán» hoy = cualquier actor que NO sea el agente asignado (un agente no
puede aprobar/aceptar su propia misión); «agente» = exactamente el asignado.
⚠ N3 PENDIENTE (DECISIONES.md §5): si delegar/aprobar es N1 o N2 y si la
identidad del capitán se endurece (solo socios) — la regla de roles se afina
en _actor_ok() sin tocar a los llamadores.

«Directo a ejecución» (DECISIONES.md §4, pendiente del socio): create() acepta
phase="exec" EXPLÍCITA (queda en history como "creada-directa-a-exec"); el
default siempre es "plan".
"""
import functools
import json
import os
import threading
import uuid
from datetime import datetime, timezone

PHASES = ("plan", "exec", "review", "done")
MODELS = ("heredar", "rapido", "profundo")
CREATE_PHASES = ("plan", "exec")          # exec = «directo a ejecución» explícito

# (from, to) → rol que puede darla: "capitan" | "agente". ÚNICA fuente de verdad.
TRANSITIONS = {
    ("plan", "exec"): "capitan",
    ("exec", "review"): "agente",
    ("review", "done"): "capitan",
    ("review", "exec"): "capitan",
    ("review", "plan"): "capitan",
}

try:                                      # N8 — lock cross-platform (amputable)
    from olock import file_lock, LockTimeout
except Exception:                         # sin olock → degrada a sin-lock
    file_lock, LockTimeout = None, None


# ── rutas (funciones, no constantes: respetan HOME parchado en tests) ───────
def _workspace_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def taskboard_path():
    """Ruta del taskboard (per-máquina, no versionado)."""
    return os.path.join(_workspace_dir(), "centro", "taskboard.json")


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id():
    return uuid.uuid4().hex[:12]


def _empty():
    return {"missions": []}


# ── load / save (atómico + falla-suave, patrón board.py) ────────────────────
def load_taskboard():
    """El taskboard completo. {missions: []} si no existe / corrupto / ilegible."""
    try:
        with open(taskboard_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    missions = data.get("missions")
    return {"missions": missions if isinstance(missions, list) else []}


def _save(board):
    """Escritura atómica (tmp con pid+token único + os.replace). False si falla."""
    path = taskboard_path()
    tmp = "%s.tmp.%d.%s" % (path, os.getpid(), uuid.uuid4().hex[:8])
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(board, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        try:                          # no dejar el tmp colgado si algo falló
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


# ── serialización de escritores (hilos del server + procesos CLI) ───────────
_TASKS_LOCK = threading.Lock()


def _mutates(fn):
    """Decorador: serializa el ciclo RMW (load → mutar → save) bajo el lock de
    módulo (hilos del ThreadingHTTPServer) Y el olock del archivo (procesos:
    CLI de un agente + server a la vez). Degrada a sin-lock; jamás levanta."""
    @functools.wraps(fn)
    def _serialized(*a, **kw):
        with _TASKS_LOCK:
            if file_lock is None:
                return fn(*a, **kw)
            try:
                with file_lock(taskboard_path(), timeout=5):
                    return fn(*a, **kw)
            except LockTimeout:
                return fn(*a, **kw)   # mejor last-writer-wins que perder el cambio
    return _serialized


# ── helpers ──────────────────────────────────────────────────────────────────
def _err(msg):
    return {"ok": False, "error": msg}


def _ok(board, **extra):
    if not _save(board):
        return _err("no pude guardar el taskboard (disco/permiso)")
    out = {"ok": True}
    out.update(extra)
    return out


def _find(board, mid):
    for m in board["missions"]:
        if isinstance(m, dict) and m.get("id") == mid:
            return m
    return None


def _sstr(v, default=""):
    return v.strip() if isinstance(v, str) else default


def _log(mission, ev, by, **extra):
    if not isinstance(mission.get("history"), list):
        mission["history"] = []
    entry = {"t": _now(), "ev": ev, "by": by or "?"}
    entry.update(extra)
    mission["history"].append(entry)


def _clean(m):
    """Vista serializable de una misión (shape completo, campos raros saneados)."""
    if not isinstance(m, dict):
        return None
    return {
        "id": m.get("id"),
        "title": m.get("title", ""),
        "idea_ref": m.get("idea_ref") if isinstance(m.get("idea_ref"), str) else None,
        "project": m.get("project", "") or "",
        "agent": m.get("agent", "") or "",
        "model": m.get("model") if m.get("model") in MODELS else "heredar",
        "branch": m.get("branch", "") or "",
        "phase": m.get("phase") if m.get("phase") in PHASES else "plan",
        "progress": m.get("progress") if isinstance(m.get("progress"), int) else 0,
        "done_cuando": [c for c in (m.get("done_cuando") or []) if isinstance(c, str)],
        "msg_ids": [i for i in (m.get("msg_ids") or []) if isinstance(i, str)],
        "history": m.get("history") if isinstance(m.get("history"), list) else [],
        "archived": bool(m.get("archived")),
        "created": m.get("created", ""),
        "updated": m.get("updated", ""),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Lectura (read-only, falla-suave)
# ═══════════════════════════════════════════════════════════════════════════
def list_missions(include_archived=False, phase=None, agent=None):
    """Misiones (vista limpia), más reciente primero. Filtros opcionales."""
    out = []
    for m in load_taskboard()["missions"]:
        c = _clean(m)
        if c is None:
            continue
        if c["archived"] and not include_archived:
            continue
        if phase and c["phase"] != phase:
            continue
        if agent and c["agent"] != agent:
            continue
        out.append(c)
    out.sort(key=lambda m: (m.get("updated") or "", m.get("id") or ""), reverse=True)
    return out


def get_mission(mission_id):
    """Vista limpia de UNA misión (incluye archivadas), o None."""
    m = _find(load_taskboard(), _sstr(mission_id))
    return _clean(m) if m else None


def summary():
    """Conteos por fase (misiones vivas) + total + archivadas. Falla-suave."""
    counts = {p: 0 for p in PHASES}
    archived = 0
    for m in load_taskboard()["missions"]:
        c = _clean(m)
        if c is None:
            continue
        if c["archived"]:
            archived += 1
            continue
        counts[c["phase"]] += 1
    counts["total"] = sum(counts[p] for p in PHASES)
    counts["archived"] = archived
    return counts


# ═══════════════════════════════════════════════════════════════════════════
# Mutación segura (CRUD + máquina de fases) — todo bajo _mutates
# ═══════════════════════════════════════════════════════════════════════════
@_mutates
def create(title, agent, project="", branch="", model="heredar", idea_ref=None,
           done_cuando=None, phase="plan", by="", progress=0):
    """Crea una misión. Fase inicial "plan" (default) o "exec" EXPLÍCITA
    («directo a ejecución» — queda en history). → {ok, id} o {ok:False, error}."""
    title = _sstr(title)
    agent = _sstr(agent).lower()
    if not title:
        return _err("falta el título de la misión")
    if not agent:
        return _err("falta el agente asignado")
    if phase not in CREATE_PHASES:
        return _err("fase inicial inválida: %r (válidas: %s)"
                    % (phase, "/".join(CREATE_PHASES)))
    if model not in MODELS:
        return _err("modelo inválido: %r (válidos: %s)" % (model, "/".join(MODELS)))
    crits = [c.strip() for c in (done_cuando or []) if isinstance(c, str) and c.strip()]
    now = _now()
    mission = {
        "id": _new_id(), "title": title,
        "idea_ref": _sstr(idea_ref) or None,
        "project": _sstr(project), "agent": agent, "model": model,
        "branch": _sstr(branch), "phase": phase, "progress": 0,
        "done_cuando": crits, "msg_ids": [], "history": [],
        "archived": False, "created": now, "updated": now,
    }
    _log(mission, "creada" if phase == "plan" else "creada-directa-a-exec",
         _sstr(by) or "?")
    board = load_taskboard()
    board["missions"].append(mission)
    return _ok(board, id=mission["id"])


def _actor_ok(role, by, mission):
    """¿Puede el actor `by` dar una transición reservada a `role`?
    agente  → by == el agente asignado (exacto).
    capitán → by != el agente asignado (nadie se auto-aprueba). ⚠ N3: endurecer
    a «solo socios» cuando el socio decida el tier (DECISIONES.md §5) — solo aquí."""
    by = _sstr(by).lower()
    if not by:
        return False, "falta `by` (quién da la transición)"
    agent = _sstr(mission.get("agent")).lower()
    if role == "agente":
        if by != agent:
            return False, ("solo el agente asignado (%s) puede entregar a review"
                           % (agent or "?"))
    else:                                  # capitán
        if by == agent:
            return False, ("el agente asignado no puede aprobar/aceptar su "
                           "propia misión (%s→ se requiere al capitán)" % by)
    return True, None


@_mutates
def transition(mission_id, to, by):
    """Transiciona la fase de una misión según la máquina (protocolo duro).
    → {ok, phase} o {ok:False, error} explicando POR QUÉ se bloqueó."""
    to = _sstr(to).lower()
    board = load_taskboard()
    mission = _find(board, _sstr(mission_id))
    if mission is None:
        return _err("misión desconocida")
    if mission.get("archived"):
        return _err("misión archivada (restaurar antes de moverla)")
    if to not in PHASES:
        return _err("fase inválida: %r (válidas: %s)" % (to, "/".join(PHASES)))
    cur = mission.get("phase") if mission.get("phase") in PHASES else "plan"
    if to == cur:
        return _err("la misión ya está en %s" % cur)
    role = TRANSITIONS.get((cur, to))
    if role is None:
        return _err("transición inválida %s→%s (válidas desde %s: %s)"
                    % (cur, to, cur,
                       ", ".join(t for f, t in TRANSITIONS if f == cur) or "ninguna"))
    ok, why = _actor_ok(role, by, mission)
    if not ok:
        return _err(why)
    mission["phase"] = to
    if to == "done":
        mission["progress"] = 100
    _log(mission, "fase:%s→%s" % (cur, to), _sstr(by))
    mission["updated"] = _now()
    return _ok(board, phase=to)


@_mutates
def set_progress(mission_id, pct, by=""):
    """Progreso de una misión EN EJECUCIÓN (`workspace centro progreso`). Solo en
    fase exec (el protocolo: no hay avance sin plan aprobado). 0-100 entero."""
    if isinstance(pct, bool) or not isinstance(pct, int) or not (0 <= pct <= 100):
        return _err("progreso inválido (entero 0-100)")
    board = load_taskboard()
    mission = _find(board, _sstr(mission_id))
    if mission is None:
        return _err("misión desconocida")
    if mission.get("archived"):
        return _err("misión archivada")
    if mission.get("phase") != "exec":
        return _err("el progreso solo se reporta en ejecución (fase actual: %s)"
                    % mission.get("phase"))
    mission["progress"] = pct
    _log(mission, "progreso:%d" % pct, _sstr(by))
    mission["updated"] = _now()
    return _ok(board, progress=pct)


@_mutates
def update(mission_id, by="", **fields):
    """RMW de campos editables: solo pisa lo enviado. Editables: title, project,
    branch, model, idea_ref, done_cuando (lista completa), agent. `phase` y
    `progress` NO se tocan por aquí (transition/set_progress son el camino).
    agent/done_cuando solo en fase plan (en exec/review la misión está tomada)."""
    board = load_taskboard()
    mission = _find(board, _sstr(mission_id))
    if mission is None:
        return _err("misión desconocida")
    if mission.get("archived"):
        return _err("misión archivada (restaurar antes de editarla)")
    for k in fields:
        if k not in ("title", "project", "branch", "model", "idea_ref",
                     "done_cuando", "agent"):
            return _err("campo no editable: %s" % k)
    if "title" in fields:
        t = _sstr(fields["title"])
        if not t:
            return _err("el título no puede quedar vacío")
        mission["title"] = t
    if "model" in fields:
        if fields["model"] not in MODELS:
            return _err("modelo inválido: %r" % (fields["model"],))
        mission["model"] = fields["model"]
    for k in ("project", "branch"):
        if k in fields:
            mission[k] = _sstr(fields[k])
    if "idea_ref" in fields:
        mission["idea_ref"] = _sstr(fields["idea_ref"]) or None
    if "agent" in fields or "done_cuando" in fields:
        if mission.get("phase") != "plan":
            return _err("agent/done_cuando solo se editan en planeación "
                        "(fase actual: %s)" % mission.get("phase"))
        if "agent" in fields:
            a = _sstr(fields["agent"]).lower()
            if not a:
                return _err("el agente no puede quedar vacío")
            mission["agent"] = a
        if "done_cuando" in fields:
            dc = fields["done_cuando"]
            if not isinstance(dc, list):
                return _err("done_cuando debe ser una lista de criterios")
            mission["done_cuando"] = [c.strip() for c in dc
                                      if isinstance(c, str) and c.strip()]
    _log(mission, "editada", _sstr(by),
         campos=sorted(fields))
    mission["updated"] = _now()
    return _ok(board)


@_mutates
def attach_msg(mission_id, msg_id, ev="msg", by=""):
    """Ata un mensaje del bus a la misión (trazabilidad msg_ids ↔ taskboard)."""
    msg_id = _sstr(msg_id)
    if not msg_id:
        return _err("falta el id del mensaje")
    board = load_taskboard()
    mission = _find(board, _sstr(mission_id))
    if mission is None:
        return _err("misión desconocida")
    if not isinstance(mission.get("msg_ids"), list):
        mission["msg_ids"] = []
    if msg_id not in mission["msg_ids"]:
        mission["msg_ids"].append(msg_id)
    _log(mission, ev, _sstr(by), msg=msg_id)
    mission["updated"] = _now()
    return _ok(board)


@_mutates
def archive(mission_id, by=""):
    """Never-delete: marca archived=true (reversible con restore)."""
    board = load_taskboard()
    mission = _find(board, _sstr(mission_id))
    if mission is None:
        return _err("misión desconocida")
    mission["archived"] = True
    _log(mission, "archivada", _sstr(by))
    mission["updated"] = _now()
    return _ok(board)


@_mutates
def restore(mission_id, by=""):
    """Des-archiva (flip archived→false, NO recrea nada)."""
    board = load_taskboard()
    mission = _find(board, _sstr(mission_id))
    if mission is None:
        return _err("misión desconocida")
    mission["archived"] = False
    _log(mission, "restaurada", _sstr(by))
    mission["updated"] = _now()
    return _ok(board)
