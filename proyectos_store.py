#!/usr/bin/env python3
"""WORKSPACE · proyectos_store — almacén de la app «Proyectos» (stdlib 3.9+).

La app «Proyectos» (proyectos.py, puerto propio) guarda AQUÍ su mapa conceptual.
Almacenamiento PROPIO y separado del resto del harness — no comparte archivo con
ninguna otra superficie:

    ~/.claude/workspace/proyectos/proyectos.json

ARRANCA VACÍO: sin datos de ejemplo, sin migración/lectura de ningún otro
tablero. Lo que el usuario ve el primer día es un lienzo limpio.

Patrón (heredado de dash/dev/board.py, ya probado en producción):
  · per-máquina, NO versionado, INDEPENDIENTE de la rama del checkout;
  · escritura ATÓMICA (tmp con pid+token único → os.replace) — dos procesos
    jamás comparten el mismo .tmp, así una escritura solapada no puede promover
    JSON corrupto;
  · ciclo RMW (load → mutar → save) serializado bajo un lock de módulo: el
    server corre sobre ThreadingHTTPServer y dos POST solapados (autosave de
    notas + un click) harían last-writer-wins, perdiendo una edición;
  · FALLA-SUAVE: archivo ausente/corrupto/ilegible → estado vacío, nunca
    revienta.

Modelo (proyectos.json):
  { "projects": [ {id, name, color, created, updated,
                   nodes: [ <nodo> ], chat: [ <msg> ]} ],
    "selection": {project_id: <id>|None, node_id: <id>|None} }

  <nodo> = {id, t, x, y, st, root, p, notes, created, updated}
      p    = id del nodo PADRE (None en la raíz) — el árbol se arma por
             referencia, igual que el prototipo del mapa mental.
      st   ∈ STATUSES (todo · doing · done)
      root = True en el único nodo raíz del proyecto (no se borra).
  <msg>  = {role: user|assistant|system, text, agent, ts}
      role="system" = nota HONESTA de la app (p. ej. «sin motor conectado»);
      NUNCA se persiste una respuesta inventada como si fuera del agente.

Toda entrada de la API se VALIDA y ACOTA aquí (títulos, notas, colores,
coordenadas, estados): el front es un cliente más, no la autoridad.
"""
import functools
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone

# Estados de un nodo (mismos tres del prototipo aprobado: Pendiente/En curso/Hecho).
STATUSES = ("todo", "doing", "done")

# Identidad POR PROYECTO. Rampa MONOCROMA (blanco→carbón): la app es blanco y
# negro, así que la «paleta» son tonos de gris. El front igual los pasa por su
# mono() al pintar, así que un proyecto viejo con color real se ve gris sin tocar
# su dato — revertir a color es cambiar esta tupla y quitar ese mono().
COLORS = ("#e8e8e8", "#c0c0c0", "#9a9a9a", "#767676", "#565656", "#3c3c3c")

# Cotas (defensa barata contra un cliente roto o un payload malicioso: el JSON
# es del usuario, pero nada obliga a que quepa un libro en el título de un nodo).
NAME_MAX = 80
TITLE_MAX = 200
NOTES_MAX = 20000
CHAT_TEXT_MAX = 8000
CHAT_KEEP = 200                 # mensajes que conserva un proyecto (los últimos)
COORD_MAX = 100000.0            # el mundo del canvas es infinito, el float no
PROJECTS_MAX = 500
NODES_MAX = 2000                # por proyecto

_HEX_RX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _workspace_dir():
    """Estado per-máquina de WORKSPACE. Función (no constante) para respetar el
    HOME parchado en los tests herméticos."""
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def store_path():
    """Ruta del almacén de la app «Proyectos» (per-máquina, no versionado)."""
    return os.path.join(_workspace_dir(), "proyectos", "proyectos.json")


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id():
    return uuid.uuid4().hex[:12]


def _empty():
    return {"projects": [], "selection": {"project_id": None, "node_id": None}}


# ── saneo de entrada ────────────────────────────────────────────────────────
def _txt(v, cap, default=""):
    """Texto acotado y sin caracteres de control (salvo saltos de línea/tabs)."""
    if not isinstance(v, str):
        return default
    s = "".join(c for c in v if c in "\n\t" or ord(c) >= 32).strip()
    return s[:cap]


def _color(v, default=COLORS[0]):
    return v if isinstance(v, str) and _HEX_RX.match(v) else default


def _coord(v, default=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):     # NaN / ±inf
        return default
    return max(-COORD_MAX, min(COORD_MAX, round(f, 2)))


def _status(v, default="todo"):
    return v if v in STATUSES else default


# ── carga / guardado ────────────────────────────────────────────────────────
def _norm_node(n):
    """Normaliza un nodo del disco: un JSON editado a mano no debe tumbar la app."""
    if not isinstance(n, dict) or not isinstance(n.get("id"), str):
        return None
    return {
        "id": n["id"],
        "t": _txt(n.get("t"), TITLE_MAX, "Sin título") or "Sin título",
        "x": _coord(n.get("x")), "y": _coord(n.get("y")),
        "st": _status(n.get("st")),
        "root": bool(n.get("root")),
        "p": n["p"] if isinstance(n.get("p"), str) else None,
        "notes": _txt(n.get("notes"), NOTES_MAX),
        "created": n.get("created") or _now(),
        "updated": n.get("updated") or _now(),
    }


def _norm_msg(m):
    if not isinstance(m, dict):
        return None
    role = m.get("role")
    if role not in ("user", "assistant", "system"):
        return None
    return {"role": role, "text": _txt(m.get("text"), CHAT_TEXT_MAX),
            "agent": _txt(m.get("agent"), 40), "ts": m.get("ts") or _now()}


def _norm_project(p):
    if not isinstance(p, dict) or not isinstance(p.get("id"), str):
        return None
    nodes = [x for x in (_norm_node(n) for n in (p.get("nodes") or []))
             if x is not None][:NODES_MAX]
    chat = [x for x in (_norm_msg(m) for m in (p.get("chat") or []))
            if x is not None][-CHAT_KEEP:]
    # integridad del árbol: un `p` que apunta a un nodo inexistente colgaría al
    # nodo del vacío (invisible, irrecuperable) → se re-cuelga de la raíz.
    ids = {n["id"] for n in nodes}
    root = next((n for n in nodes if n["root"]), nodes[0] if nodes else None)
    for n in nodes:
        if n is root:
            n["p"] = None
            continue
        if n["p"] not in ids or n["p"] == n["id"]:
            n["p"] = root["id"] if root else None
    return {
        "id": p["id"],
        "name": _txt(p.get("name"), NAME_MAX, "Proyecto") or "Proyecto",
        "color": _color(p.get("color")),
        "created": p.get("created") or _now(),
        "updated": p.get("updated") or _now(),
        "nodes": nodes, "chat": chat,
    }


def load():
    """El estado completo. Vacío si no existe / corrupto / ilegible."""
    try:
        with open(store_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    projects = [x for x in (_norm_project(p) for p in (data.get("projects") or []))
                if x is not None][:PROJECTS_MAX]
    sel = data.get("selection")
    sel = sel if isinstance(sel, dict) else {}
    pid = sel.get("project_id") if isinstance(sel.get("project_id"), str) else None
    nid = sel.get("node_id") if isinstance(sel.get("node_id"), str) else None
    ids = {p["id"] for p in projects}
    if pid not in ids:                    # selección colgada → limpia
        pid, nid = None, None
    else:
        proj = next(p for p in projects if p["id"] == pid)
        if nid not in {n["id"] for n in proj["nodes"]}:
            nid = None
    return {"projects": projects, "selection": {"project_id": pid, "node_id": nid}}


def _save(data):
    """Escribe el estado de forma atómica (tmp + replace). False si falla.
    El tmp lleva pid + token único: dos escritores en procesos distintos jamás
    comparten el mismo .tmp (nunca se promueve un JSON a medio escribir)."""
    path = store_path()
    tmp = "%s.tmp.%d.%s" % (path, os.getpid(), uuid.uuid4().hex[:8])
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        try:                              # no dejar el tmp colgado
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


_LOCK = threading.Lock()


def _mutates(fn):
    """Serializa el ciclo RMW (load → mutar → _save) de un endpoint mutador.
    ThreadingHTTPServer sirve POSTs en paralelo: sin esto, el autosave de notas
    y un click simultáneo se pisan (last-writer-wins pierde una edición)."""
    @functools.wraps(fn)
    def _serialized(data):
        with _LOCK:
            return fn(data if isinstance(data, dict) else {})
    return _serialized


# ── helpers de árbol ────────────────────────────────────────────────────────
def _find_project(st, pid):
    for p in st["projects"]:
        if p["id"] == pid:
            return p
    return None


def _find_node(proj, nid):
    for n in proj["nodes"]:
        if n["id"] == nid:
            return n
    return None


def _root_of(proj):
    return next((n for n in proj["nodes"] if n["root"]),
                proj["nodes"][0] if proj["nodes"] else None)


def _subtree_ids(proj, nid):
    """ids de `nid` y TODOS sus descendientes (para borrar una rama entera)."""
    kill = {nid}
    changed = True
    while changed:                       # cierre transitivo (el árbol es plano)
        changed = False
        for n in proj["nodes"]:
            if n["p"] in kill and n["id"] not in kill:
                kill.add(n["id"])
                changed = True
    return kill


def _touch(proj):
    proj["updated"] = _now()


# ── API (la consume proyectos.py; firma dict → dict, JSON-serializable) ─────
def api_state(query=None):
    """GET /api/proyectos/state → el estado completo + la selección viva."""
    st = load()
    return {"ok": True, "projects": st["projects"], "selection": st["selection"],
            "colors": list(COLORS), "statuses": list(STATUSES)}


@_mutates
def api_add_project(data):
    """POST → crea un proyecto CON su nodo raíz (un mapa nunca nace sin centro)."""
    st = load()
    if len(st["projects"]) >= PROJECTS_MAX:
        return {"ok": False, "error": "demasiados proyectos (máx %d)" % PROJECTS_MAX}
    name = _txt(data.get("name"), NAME_MAX) or "Proyecto sin título"
    color = _color(data.get("color"), COLORS[len(st["projects"]) % len(COLORS)])
    now = _now()
    proj = {"id": _new_id(), "name": name, "color": color,
            "created": now, "updated": now, "chat": [],
            "nodes": [{"id": _new_id(), "t": name, "x": 0.0, "y": 0.0,
                       "st": "todo", "root": True, "p": None, "notes": "",
                       "created": now, "updated": now}]}
    st["projects"].append(proj)
    st["selection"] = {"project_id": proj["id"], "node_id": None}
    if not _save(st):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "project": proj, "selection": st["selection"]}


@_mutates
def api_update_project(data):
    """POST → renombra / recolorea. El nombre se refleja en el nodo raíz."""
    st = load()
    proj = _find_project(st, data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    if "name" in data:
        name = _txt(data.get("name"), NAME_MAX)
        if name:
            proj["name"] = name
            root = _root_of(proj)
            if root:                     # raíz y proyecto comparten nombre
                root["t"] = name
                root["updated"] = _now()
    if "color" in data:
        proj["color"] = _color(data.get("color"), proj["color"])
    _touch(proj)
    if not _save(st):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "project": proj}


@_mutates
def api_delete_project(data):
    """POST → borra el proyecto y su mapa. Lo confirma la UI antes de llamar."""
    st = load()
    proj = _find_project(st, data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    st["projects"] = [p for p in st["projects"] if p["id"] != proj["id"]]
    if st["selection"]["project_id"] == proj["id"]:
        st["selection"] = {"project_id": None, "node_id": None}
    if not _save(st):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "selection": st["selection"]}


@_mutates
def api_add_node(data):
    """POST → cuelga un nodo de `parent_id` (default: la raíz)."""
    st = load()
    proj = _find_project(st, data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    if len(proj["nodes"]) >= NODES_MAX:
        return {"ok": False, "error": "demasiados nodos (máx %d)" % NODES_MAX}
    parent = _find_node(proj, data.get("parent_id")) or _root_of(proj)
    if parent is None:
        return {"ok": False, "error": "el proyecto no tiene raíz"}
    now = _now()
    node = {"id": _new_id(), "t": _txt(data.get("t"), TITLE_MAX) or "Nueva idea",
            "x": _coord(data.get("x"), parent["x"] + 200),
            "y": _coord(data.get("y"), parent["y"] + 60),
            "st": _status(data.get("st")), "root": False, "p": parent["id"],
            "notes": "", "created": now, "updated": now}
    proj["nodes"].append(node)
    _touch(proj)
    if not _save(st):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "node": node, "project": proj}


@_mutates
def api_update_node(data):
    """POST → mueve (x,y) · renombra (t) · estado (st) · notas · RECONECTA (p).

    Reconectar valida el ciclo: un nodo no puede colgar de su propio subárbol
    (dejaría una rama huérfana flotando fuera del mapa, invisible)."""
    st = load()
    proj = _find_project(st, data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    node = _find_node(proj, data.get("node_id"))
    if node is None:
        return {"ok": False, "error": "nodo inexistente"}
    if "t" in data:
        t = _txt(data.get("t"), TITLE_MAX)
        node["t"] = t or "Sin título"
        if node["root"]:                 # la raíz ES el nombre del proyecto
            proj["name"] = node["t"]
    if "x" in data:
        node["x"] = _coord(data.get("x"), node["x"])
    if "y" in data:
        node["y"] = _coord(data.get("y"), node["y"])
    if "st" in data:
        node["st"] = _status(data.get("st"), node["st"])
    if "notes" in data:
        node["notes"] = _txt(data.get("notes"), NOTES_MAX)
    if "p" in data:
        if node["root"]:
            return {"ok": False, "error": "la raíz no se puede reconectar"}
        newp = data.get("p")
        if not isinstance(newp, str) or _find_node(proj, newp) is None:
            return {"ok": False, "error": "padre inexistente"}
        if newp in _subtree_ids(proj, node["id"]):
            return {"ok": False, "error": "eso haría un ciclo (es su propia rama)"}
        node["p"] = newp
    node["updated"] = _now()
    _touch(proj)
    if not _save(st):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "node": node, "project": proj}


@_mutates
def api_delete_node(data):
    """POST → borra el nodo Y su rama (descendientes). La raíz no se borra."""
    st = load()
    proj = _find_project(st, data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    node = _find_node(proj, data.get("node_id"))
    if node is None:
        return {"ok": False, "error": "nodo inexistente"}
    if node["root"]:
        return {"ok": False, "error": "el nodo raíz no se borra (borra el proyecto)"}
    kill = _subtree_ids(proj, node["id"])
    proj["nodes"] = [n for n in proj["nodes"] if n["id"] not in kill]
    _touch(proj)
    if st["selection"]["node_id"] in kill:
        st["selection"]["node_id"] = None
    if not _save(st):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "removed": sorted(kill), "project": proj}


@_mutates
def api_select(data):
    """POST → persiste la selección de UI (proyecto/nodo actual). Ids VALIDADOS
    contra el estado; null limpia. Al reabrir la app el usuario cae donde estaba
    (el mapa no rebota al primer proyecto)."""
    st = load()
    pid = data.get("project_id")
    nid = data.get("node_id")
    proj = _find_project(st, pid) if isinstance(pid, str) else None
    if proj is None:
        st["selection"] = {"project_id": None, "node_id": None}
    else:
        node = _find_node(proj, nid) if isinstance(nid, str) else None
        st["selection"] = {"project_id": proj["id"],
                           "node_id": node["id"] if node else None}
    if not _save(st):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "selection": st["selection"]}


# ── chat (lo alimenta proyectos_chat; vive aquí porque es estado del proyecto) ──
def context_of(project_id, node_id):
    """(proyecto, nodo) del estado — el CONTEXTO que se le manda al agente.
    (None, None) si no existe. Lectura pura (sin lock: no muta)."""
    st = load()
    proj = _find_project(st, project_id)
    if proj is None:
        return None, None
    node = _find_node(proj, node_id) if isinstance(node_id, str) else None
    return proj, node


def chat_of(project_id):
    st = load()
    proj = _find_project(st, project_id)
    return list(proj["chat"]) if proj else []


@_mutates
def _append_chat(data):
    st = load()
    proj = _find_project(st, data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    for m in data.get("msgs") or []:
        nm = _norm_msg(m)
        if nm:
            proj["chat"].append(nm)
    proj["chat"] = proj["chat"][-CHAT_KEEP:]
    _touch(proj)
    if not _save(st):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "chat": proj["chat"]}


def append_chat(project_id, msgs):
    """Añade mensajes al hilo del proyecto (serializado + atómico). {ok, chat}."""
    return _append_chat({"project_id": project_id, "msgs": msgs})
