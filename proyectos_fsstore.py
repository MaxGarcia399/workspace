#!/usr/bin/env python3
"""WORKSPACE · proyectos_fsstore — almacén per-NODO de «Proyectos» v2 (stdlib 3.9+).

Sucesor del `proyectos_store` monolítico. En vez de un solo `proyectos.json`,
cada proyecto y cada nodo es una CARPETA en disco, así el contenido pesado
(handoff, archivos, sesiones) vive junto al nodo y NO en un JSON gigante:

    ~/.claude/workspace/proyectos/               ← base (coexiste con proyectos.json)
      selection.json                           ← selección global (proyecto+nodo activos)
      <pid>/                                    ← un proyecto  (<pid> = 12 hex)
        project.json                           ← MEMBRESÍA + ORDEN + meta del proyecto
                                                 {id, name, color, created, updated,
                                                  node_order: [<nid>, ...]}
        <nid>/                                  ← un nodo/branch  (<nid> = 12 hex)
          node.json                            ← CANÓNICO del nodo: topología + coords
                                                 {id, t, x, y, st, root, p, notes,
                                                  created, updated}
          resumen.md                           ← handoff (contenido PESADO, F4)
          archivos/                            ← trabajo del nodo (F5)
          sesiones/                            ← hilos por agente/día (F3)
      .papelera/                               ← never-delete: borrar = archivar aquí

Decisiones adoptadas (socio/equipo):
  · D1 — `node.json` es la FUENTE de topología (parent `p`, coords, status).
    `project.json` solo guarda MEMBRESÍA + ORDEN (`node_order`) + meta del proyecto.
    Nada de `parent` duplicado entre los dos archivos → una sola verdad.
  · D2 — un solo `_LOCK` global (single-user, simple).
  · D5 — la carpeta sigue siendo `proyectos/`; COEXISTE con el `proyectos.json`
    viejo (la migración lo lee, jamás lo borra).

Invariantes de seguridad (anti-vibe):
  · IDs ESTRICTOS `^[0-9a-f]{12}$` — se validan ANTES de tocar el path. Un id con
    `..`, `/`, o absoluto se RECHAZA (anti path-traversal). Ningún path se arma con
    input sin validar.
  · Escritura ATÓMICA (tmp con pid+token → os.replace): un lector jamás ve un
    archivo a medio escribir.
  · FALLA-SUAVE POR ARCHIVO: un node.json/project.json ausente o corrupto se salta
    (default), nunca tumba la carga del resto.
  · RECONCILIA HUÉRFANOS al leer: una carpeta de nodo en disco que no está en
    `node_order` se incluye igual (no se pierde trabajo); un `p` colgado se
    re-cuelga de la raíz; se garantiza exactamente una raíz.
  · NEVER-DELETE: borrar mueve a `.papelera/`, no hace `rm` irrecuperable.

Reusa el saneo y las cotas de `proyectos_store` (misma validación, sin drift).
"""
import functools
import json
import os
import re
import shutil
import threading
import unicodedata
import uuid

import proyectos_store as store

# Reexport de cotas/paletas para que el front y la migración tengan una sola
# fuente de verdad (no re-declarar constantes que ya vive en proyectos_store).
STATUSES = store.STATUSES
COLORS = store.COLORS
NAME_MAX = store.NAME_MAX
TITLE_MAX = store.TITLE_MAX
NOTES_MAX = store.NOTES_MAX
COORD_MAX = store.COORD_MAX
PROJECTS_MAX = store.PROJECTS_MAX
NODES_MAX = store.NODES_MAX

#: id válido = EXACTAMENTE 12 hex minúsculas (lo que produce `store._new_id`).
#: Se valida ANTES de construir cualquier path → un id con `..`/`/`/absoluto o
#: cualquier otra cosa NO llega nunca a un os.path.join. Es la defensa central
#: contra path-traversal en este módulo.
_ID_RX = re.compile(r"^[0-9a-f]{12}$")


def valid_id(x):
    """True solo si `x` es un id 12-hex canónico. Rechaza traversal por diseño."""
    return isinstance(x, str) and _ID_RX.match(x) is not None


def _new_id():
    return uuid.uuid4().hex[:12]


def _now():
    return store._now()


# ── paths (todos validan el id ANTES de armar la ruta) ──────────────────────
def _workspace_dir():
    """Estado per-máquina. Función (no constante) para respetar el HOME parchado
    en los tests herméticos."""
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def base_dir():
    """Carpeta raíz del almacén v2 (coexiste con proyectos.json — D5)."""
    return os.path.join(_workspace_dir(), "proyectos")


def selection_path():
    return os.path.join(base_dir(), "selection.json")


def trash_dir():
    return os.path.join(base_dir(), ".papelera")


def project_dir(pid):
    """<base>/<pid>  o None si el id no es válido (anti-traversal)."""
    return os.path.join(base_dir(), pid) if valid_id(pid) else None


def project_json_path(pid):
    d = project_dir(pid)
    return os.path.join(d, "project.json") if d else None


def node_dir(pid, nid):
    """<base>/<pid>/<nid>  o None si algún id no es válido (anti-traversal)."""
    if not valid_id(pid) or not valid_id(nid):
        return None
    return os.path.join(base_dir(), pid, nid)


def node_json_path(pid, nid):
    d = node_dir(pid, nid)
    return os.path.join(d, "node.json") if d else None


def resumen_path(pid, nid):
    d = node_dir(pid, nid)
    return os.path.join(d, "resumen.md") if d else None


def archivos_dir(pid, nid):
    d = node_dir(pid, nid)
    return os.path.join(d, "archivos") if d else None


def sesiones_dir(pid, nid):
    d = node_dir(pid, nid)
    return os.path.join(d, "sesiones") if d else None


# ── escritura atómica (mismo patrón que store._save) ────────────────────────
def _atomic_write(path, writer):
    """Escribe vía tmp (pid+token único) → os.replace. False si falla.
    Dos procesos jamás comparten el mismo .tmp: nunca se promueve un archivo a
    medio escribir. `writer(fh)` hace el dump concreto."""
    if not path:
        return False
    tmp = "%s.tmp.%d.%s" % (path, os.getpid(), uuid.uuid4().hex[:8])
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            writer(fh)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def atomic_write_json(path, data):
    return _atomic_write(path, lambda fh: json.dump(data, fh, indent=2,
                                                     ensure_ascii=False))


def atomic_write_text(path, text):
    return _atomic_write(path, lambda fh: fh.write(text if isinstance(text, str)
                                                   else str(text)))


def _read_json(path, default):
    """Lee JSON con falla-suave: ausente/corrupto/ilegible → `default`."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, ValueError, OSError, TypeError):
        return default
    return data


# ── lock global (D2) ────────────────────────────────────────────────────────
_LOCK = threading.Lock()


def _mutates(fn):
    """Serializa el ciclo lee→muta→escribe de un endpoint (igual que el store)."""
    @functools.wraps(fn)
    def _serialized(data):
        with _LOCK:
            return fn(data if isinstance(data, dict) else {})
    return _serialized


# ── carga / reconciliación ──────────────────────────────────────────────────
def _list_ids(path):
    """Nombres de subcarpetas de `path` que son ids válidos (12-hex). El resto
    (`.papelera`, `archivos`, `sesiones`, archivos sueltos) se ignora solo por
    no matchear el regex."""
    try:
        entries = os.listdir(path)
    except OSError:
        return []
    return sorted(e for e in entries
                  if valid_id(e) and os.path.isdir(os.path.join(path, e)))


def _load_node(pid, nid):
    """node.json → nodo normalizado (misma forma que store). None si falta/corrupto."""
    raw = _read_json(node_json_path(pid, nid), None)
    if not isinstance(raw, dict):
        return None
    raw = dict(raw)
    raw.setdefault("id", nid)
    # el id del path MANDA (el del archivo podría venir editado a mano)
    raw["id"] = nid
    return store._norm_node(raw)


def _reconcile_tree(nodes):
    """Garantiza árbol sano en memoria (misma política que store._norm_project):
    exactamente una raíz; un `p` colgado o auto-referente se re-cuelga de la raíz.
    NO muta disco — es saneo de lectura."""
    if not nodes:
        return nodes
    ids = {n["id"] for n in nodes}
    root = next((n for n in nodes if n["root"]), nodes[0])
    # una sola raíz: si el JSON marcó varias, solo la primera queda como raíz
    for n in nodes:
        n["root"] = (n is root)
    for n in nodes:
        if n is root:
            n["p"] = None
        elif n["p"] not in ids or n["p"] == n["id"]:
            n["p"] = root["id"]
    return nodes


def _load_project(pid):
    """Reconstruye un proyecto desde disco (project.json + node.json de cada nodo).
    None si no hay project.json legible. Reconcilia huérfanos y el árbol.

    El dict devuelto es LIGERO: trae los nodos (node.json) pero NO abre
    resumen.md / archivos/ / sesiones/ (contenido pesado — fuera de api_state)."""
    meta = _read_json(project_json_path(pid), None)
    if not isinstance(meta, dict):
        return None
    order = [x for x in (meta.get("node_order") or []) if valid_id(x)]
    on_disk = _list_ids(project_dir(pid))
    # membresía = orden declarado + huérfanos en disco no listados (no se pierden)
    seen = set()
    membership = []
    for nid in order + [x for x in on_disk if x not in order]:
        if nid in seen:
            continue
        seen.add(nid)
        membership.append(nid)
    nodes = [n for n in (_load_node(pid, nid) for nid in membership)
             if n is not None][:NODES_MAX]
    nodes = _reconcile_tree(nodes)
    return {
        "id": pid,
        "name": store._txt(meta.get("name"), NAME_MAX, "Proyecto") or "Proyecto",
        "color": store._color(meta.get("color")),
        "created": meta.get("created") or _now(),
        "updated": meta.get("updated") or _now(),
        "nodes": nodes,
    }


def _load_selection(projects):
    """selection.json validada contra los proyectos vivos. Colgada → limpia."""
    sel = _read_json(selection_path(), {})
    sel = sel if isinstance(sel, dict) else {}
    pid = sel.get("project_id") if isinstance(sel.get("project_id"), str) else None
    nid = sel.get("node_id") if isinstance(sel.get("node_id"), str) else None
    by_id = {p["id"]: p for p in projects}
    if pid not in by_id:
        return {"project_id": None, "node_id": None}
    if nid not in {n["id"] for n in by_id[pid]["nodes"]}:
        nid = None
    return {"project_id": pid, "node_id": nid}


def load():
    """Estado completo v2 desde disco: {projects, selection}. Vacío si no hay nada.
    Orden por `created` (cronológico, estable) — cada project.json vive en su
    carpeta, así que el orden global se deriva de la fecha, no del listado del FS."""
    projects = [p for p in (_load_project(pid) for pid in _list_ids(base_dir()))
                if p is not None]
    projects.sort(key=lambda p: (p.get("created") or "", p["id"]))
    return {"projects": projects[:PROJECTS_MAX],
            "selection": _load_selection(projects[:PROJECTS_MAX])}


# ── helpers internos de mutación ────────────────────────────────────────────
def _write_project_meta(proj):
    """project.json = meta + node_order (membresía+orden). node.json es la
    verdad de la topología; aquí NO se duplica `p`/coords (D1)."""
    return atomic_write_json(project_json_path(proj["id"]), {
        "id": proj["id"],
        "name": proj["name"],
        "color": proj["color"],
        "created": proj["created"],
        "updated": proj["updated"],
        "node_order": [n["id"] for n in proj["nodes"]],
    })


def _write_node(pid, node):
    return atomic_write_json(node_json_path(pid, node["id"]), node)


def _seed_node_dir(pid, node, resumen=""):
    """Materializa la carpeta de un nodo: archivos/ + sesiones/ + resumen.md,
    y node.json AL FINAL (su presencia = 'nodo comprometido').

    Guarda contra ids inválidos: si `pid`/`node['id']` no pasan la validación,
    los path-helpers devuelven None → aquí se ABORTA sin tocar disco (defensa
    anti-traversal en el borde de escritura, no solo en el de la API)."""
    ad = archivos_dir(pid, node["id"])
    sd = sesiones_dir(pid, node["id"])
    if ad is None or sd is None:
        return False
    try:
        os.makedirs(ad, exist_ok=True)
        os.makedirs(sd, exist_ok=True)
    except OSError:
        return False
    atomic_write_text(resumen_path(pid, node["id"]), resumen or "")
    return _write_node(pid, node)


def _archive(path):
    """Mueve `path` a .papelera/<basename>-<ts> (never-delete). True si ok."""
    if not path or not os.path.exists(path):
        return False
    try:
        os.makedirs(trash_dir(), exist_ok=True)
        stamp = _now().replace(":", "").replace("-", "")
        dst = os.path.join(trash_dir(), "%s-%s-%s"
                           % (os.path.basename(path), stamp, uuid.uuid4().hex[:6]))
        shutil.move(path, dst)
        return True
    except OSError:
        return False


# ── API (misma firma dict→dict que proyectos_store, para el front) ──────────
def api_state(_query=None):
    """GET → estado completo + selección. LIGERO: los nodos traen su metadata
    (node.json) pero NUNCA el contenido pesado (resumen.md / archivos / sesiones).
    `_query` = dict de querystring del dispatcher (posicional); aquí no se usa,
    se acepta por PARIDAD con la firma de `proyectos_store.api_state`."""
    st = load()
    return {"ok": True, "projects": st["projects"], "selection": st["selection"],
            "colors": list(COLORS), "statuses": list(STATUSES)}


@_mutates
def api_add_project(data):
    """POST → crea proyecto CON su nodo raíz (una carpeta por cada uno)."""
    if len(_list_ids(base_dir())) >= PROJECTS_MAX:
        return {"ok": False, "error": "demasiados proyectos (máx %d)" % PROJECTS_MAX}
    name = store._txt(data.get("name"), NAME_MAX) or "Proyecto sin título"
    n_existing = len(_list_ids(base_dir()))
    color = store._color(data.get("color"), COLORS[n_existing % len(COLORS)])
    now = _now()
    pid, root_id = _new_id(), _new_id()
    root = {"id": root_id, "t": name, "x": 0.0, "y": 0.0, "st": "todo",
            "root": True, "p": None, "notes": "", "created": now, "updated": now}
    proj = {"id": pid, "name": name, "color": color,
            "created": now, "updated": now, "nodes": [root]}
    # nodo primero (dirs+node.json), luego project.json (= 'comprometido')
    if not _seed_node_dir(pid, root) or not _write_project_meta(proj):
        return {"ok": False, "error": "no pude guardar"}
    _set_selection(pid, None)
    return {"ok": True, "project": proj,
            "selection": {"project_id": pid, "node_id": None}}


@_mutates
def api_update_project(data):
    """POST → renombra / recolorea. El nombre se refleja en el nodo raíz."""
    proj = _load_project(data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    pid = proj["id"]
    if "name" in data:
        name = store._txt(data.get("name"), NAME_MAX)
        if name:
            proj["name"] = name
            root = next((n for n in proj["nodes"] if n["root"]), None)
            if root:
                root["t"] = name
                root["updated"] = _now()
                _write_node(pid, root)
    if "color" in data:
        proj["color"] = store._color(data.get("color"), proj["color"])
    proj["updated"] = _now()
    if not _write_project_meta(proj):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "project": proj}


@_mutates
def api_delete_project(data):
    """POST → archiva el proyecto entero en .papelera (never-delete)."""
    pid = data.get("project_id")
    if _load_project(pid) is None:
        return {"ok": False, "error": "proyecto inexistente"}
    if not _archive(project_dir(pid)):
        return {"ok": False, "error": "no pude archivar"}
    sel = _read_json(selection_path(), {})
    if isinstance(sel, dict) and sel.get("project_id") == pid:
        _set_selection(None, None)
    return {"ok": True, "selection": {"project_id": None, "node_id": None}}


@_mutates
def api_add_node(data):
    """POST → cuelga un nodo de parent_id (default: la raíz)."""
    proj = _load_project(data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    pid = proj["id"]
    if len(proj["nodes"]) >= NODES_MAX:
        return {"ok": False, "error": "demasiados nodos (máx %d)" % NODES_MAX}
    root = next((n for n in proj["nodes"] if n["root"]), None)
    parent = next((n for n in proj["nodes"]
                   if n["id"] == data.get("parent_id")), None) or root
    if parent is None:
        return {"ok": False, "error": "el proyecto no tiene raíz"}
    now = _now()
    node = {"id": _new_id(),
            "t": store._txt(data.get("t"), TITLE_MAX) or "Nueva idea",
            "x": store._coord(data.get("x"), parent["x"] + 200),
            "y": store._coord(data.get("y"), parent["y"] + 60),
            "st": store._status(data.get("st")), "root": False, "p": parent["id"],
            "notes": "", "created": now, "updated": now}
    proj["nodes"].append(node)
    proj["updated"] = now
    # node.json primero; si crashea antes de project.json, load() lo reconcilia
    if not _seed_node_dir(pid, node) or not _write_project_meta(proj):
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "node": node, "project": proj}


@_mutates
def api_update_node(data):
    """POST → mueve (x,y) · renombra (t) · estado (st) · notas · RECONECTA (p),
    validando anti-ciclo (un nodo no puede colgar de su propio subárbol)."""
    proj = _load_project(data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    pid = proj["id"]
    node = next((n for n in proj["nodes"] if n["id"] == data.get("node_id")), None)
    if node is None:
        return {"ok": False, "error": "nodo inexistente"}
    if "t" in data:
        node["t"] = store._txt(data.get("t"), TITLE_MAX) or "Sin título"
        if node["root"]:
            proj["name"] = node["t"]
    if "x" in data:
        node["x"] = store._coord(data.get("x"), node["x"])
    if "y" in data:
        node["y"] = store._coord(data.get("y"), node["y"])
    if "st" in data:
        node["st"] = store._status(data.get("st"), node["st"])
    if "notes" in data:
        node["notes"] = store._txt(data.get("notes"), NOTES_MAX)
    if "p" in data:
        if node["root"]:
            return {"ok": False, "error": "la raíz no se puede reconectar"}
        newp = data.get("p")
        if not isinstance(newp, str) or \
                not any(n["id"] == newp for n in proj["nodes"]):
            return {"ok": False, "error": "padre inexistente"}
        if newp in _subtree_ids(proj, node["id"]):
            return {"ok": False, "error": "eso haría un ciclo (es su propia rama)"}
        node["p"] = newp
    node["updated"] = _now()
    proj["updated"] = _now()
    # topología del nodo → node.json (canónico); si cambió el nombre del proyecto
    # (raíz renombrada) también persiste project.json
    ok = _write_node(pid, node)
    if node["root"] and "t" in data:
        ok = ok and _write_project_meta(proj)
    if not ok:
        return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "node": node, "project": proj}


@_mutates
def api_delete_node(data):
    """POST → archiva el nodo Y su rama (descendientes). La raíz no se borra."""
    proj = _load_project(data.get("project_id"))
    if proj is None:
        return {"ok": False, "error": "proyecto inexistente"}
    pid = proj["id"]
    node = next((n for n in proj["nodes"] if n["id"] == data.get("node_id")), None)
    if node is None:
        return {"ok": False, "error": "nodo inexistente"}
    if node["root"]:
        return {"ok": False, "error": "el nodo raíz no se borra (borra el proyecto)"}
    kill = _subtree_ids(proj, node["id"])
    for nid in kill:
        _archive(node_dir(pid, nid))
    proj["nodes"] = [n for n in proj["nodes"] if n["id"] not in kill]
    proj["updated"] = _now()
    if not _write_project_meta(proj):
        return {"ok": False, "error": "no pude guardar"}
    sel = _read_json(selection_path(), {})
    if isinstance(sel, dict) and sel.get("node_id") in kill:
        _set_selection(sel.get("project_id"), None)
    return {"ok": True, "removed": sorted(kill), "project": proj}


@_mutates
def api_select(data):
    """POST → persiste la selección (proyecto/nodo). Ids VALIDADOS contra disco."""
    pid = data.get("project_id")
    nid = data.get("node_id")
    proj = _load_project(pid) if isinstance(pid, str) else None
    if proj is None:
        _set_selection(None, None)
        return {"ok": True, "selection": {"project_id": None, "node_id": None}}
    valid_node = nid if (isinstance(nid, str) and
                         any(n["id"] == nid for n in proj["nodes"])) else None
    _set_selection(proj["id"], valid_node)
    return {"ok": True,
            "selection": {"project_id": proj["id"], "node_id": valid_node}}


def _set_selection(pid, nid):
    return atomic_write_json(selection_path(),
                             {"project_id": pid, "node_id": nid})


# ── helpers de árbol ────────────────────────────────────────────────────────
def _subtree_ids(proj, nid):
    """ids de `nid` y TODOS sus descendientes (cierre transitivo, árbol plano)."""
    kill = {nid}
    changed = True
    while changed:
        changed = False
        for n in proj["nodes"]:
            if n["p"] in kill and n["id"] not in kill:
                kill.add(n["id"])
                changed = True
    return kill


# ── lectura de contexto (paridad con store.context_of) ──────────────────────
def context_of(project_id, node_id):
    """(proyecto, nodo) — el CONTEXTO para el agente. (None, None) si no existe."""
    proj = _load_project(project_id) if isinstance(project_id, str) else None
    if proj is None:
        return None, None
    node = next((n for n in proj["nodes"] if n["id"] == node_id),
                None) if isinstance(node_id, str) else None
    return proj, node


# ═══════════════════════════════════════════════════════════════════════════
# F3 · sesiones por (nodo × agente × día)
#   sesiones/<agente>/<YYYY-MM-DD>.md — append markdown fechado, un archivo/día.
#   Cada vuelta se marca con un CENTINELA en comentario HTML (invisible al
#   renderizar, pero PARSEABLE): la sesión es a la vez legible por humanos y
#   fuente estructurada para armar el contexto del prompt.
# ═══════════════════════════════════════════════════════════════════════════
_AGENT_SLUG_RX = re.compile(r"[^a-z0-9_-]+")
_DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: centinela de vuelta. `role` es un enum cerrado y `ts` es nuestro timestamp
#: ISO (sin `-->`), así que la línea nunca la falsifica el contenido salvo que
#: el texto del usuario la copie literal → se neutraliza al escribir (ver abajo).
_TURN_RX = re.compile(r"<!--turn role=(user|assistant|system) ts=(\S*)-->")


def _agent_slug(agent):
    """Nombre de agente → componente de carpeta seguro ([a-z0-9_-], ≤40). None
    si queda vacío. Defensa anti-traversal para el segmento `<agente>`."""
    if not isinstance(agent, str):
        return None
    s = _AGENT_SLUG_RX.sub("-", agent.strip().lower()).strip("-")
    return s[:40] or None


def _today():
    return _now()[:10]


def sesiones_agent_dir(pid, nid, agent):
    sd = sesiones_dir(pid, nid)
    slug = _agent_slug(agent)
    return os.path.join(sd, slug) if (sd and slug) else None


def session_path(pid, nid, agent, dia=None):
    """sesiones/<agente>/<YYYY-MM-DD>.md — None si algún componente es inválido.
    `dia` default = hoy (UTC); un `dia` mal formado se ignora y cae a hoy."""
    d = sesiones_agent_dir(pid, nid, agent)
    if not d:
        return None
    dia = dia if (isinstance(dia, str) and _DATE_RX.match(dia)) else _today()
    return os.path.join(d, dia + ".md")


def append_session(pid, nid, agent, role, text, ts=None):
    """Añade una vuelta a la sesión del día (serializado + atómico). {ok}.
    Never-overwrite: relee el archivo del día y reescribe atómicamente con el
    bloque nuevo al final (no hay `open('a')` porque el replace atómico es la
    garantía de no dejar un archivo a medias)."""
    if role not in ("user", "assistant", "system"):
        return {"ok": False, "error": "role inválido"}
    p = session_path(pid, nid, agent)
    if not p:
        return {"ok": False, "error": "destino de sesión inválido"}
    text = store._txt(text, store.CHAT_TEXT_MAX)
    # neutraliza un centinela literal en el texto del usuario (no puede partir el
    # parser): «<!--turn» → «<!-- turn». Cosmético al leer, seguro al parsear.
    text = text.replace("<!--turn", "<!-- turn")
    ts = ts or _now()
    block = "<!--turn role=%s ts=%s-->\n%s\n\n" % (role, ts, text)
    with _LOCK:
        try:
            existing = ""
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    existing = fh.read()
            else:
                existing = "# Sesión — %s · %s\n\n" % (_agent_slug(agent),
                                                       p[-13:-3])
            ok = atomic_write_text(p, existing + block)
        except OSError:
            ok = False
    return {"ok": bool(ok)}


def _parse_turns(raw):
    """markdown de sesión → [{role, ts, text}] en orden cronológico."""
    parts = _TURN_RX.split(raw or "")
    it = iter(parts[1:])                  # parts[0] = cabecera antes del 1er turno
    out = []
    for role, ts, text in zip(it, it, it):
        out.append({"role": role, "ts": ts, "text": (text or "").strip()})
    return out


def read_session(pid, nid, agent, dia=None):
    """Vueltas de la sesión de un día (default hoy). [] si no existe/ilegible."""
    p = session_path(pid, nid, agent, dia)
    if not p or not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as fh:
            return _parse_turns(fh.read())
    except OSError:
        return []


def list_session_days(pid, nid, agent):
    """Fechas (YYYY-MM-DD) con sesión para ese agente, ascendente. Para navegar
    el historial por día (F6)."""
    d = sesiones_agent_dir(pid, nid, agent)
    if not d or not os.path.isdir(d):
        return []
    try:
        return sorted(f[:-3] for f in os.listdir(d)
                      if f.endswith(".md") and _DATE_RX.match(f[:-3]))
    except OSError:
        return []


def list_session_agents(pid, nid):
    """Agentes con sesión en el nodo (pestañas del chat, F6). Excluye `_migrado`
    (es el archivo del chat v1, no un agente)."""
    sd = sesiones_dir(pid, nid)
    if not sd or not os.path.isdir(sd):
        return []
    try:
        return sorted(e for e in os.listdir(sd)
                      if e != "_migrado" and os.path.isdir(os.path.join(sd, e)))
    except OSError:
        return []


def recent_turns(pid, nid, agent, limit=8):
    """Las últimas `limit` vueltas de ESE agente en ESE nodo, cruzando días
    (continuidad de la conversación por encima de la medianoche). Es lo que
    alimenta el historial del prompt en v2 — en vez del `chat_of(pid)` mezclado."""
    collected = []
    for dia in reversed(list_session_days(pid, nid, agent)):   # nuevo→viejo
        collected = read_session(pid, nid, agent, dia) + collected
        if len(collected) >= limit:
            break
    return collected[-limit:]


# ═══════════════════════════════════════════════════════════════════════════
# F4 · resumen.md handoff (get/set por nodo)
# ═══════════════════════════════════════════════════════════════════════════
RESUMEN_MAX = 40000


def get_resumen(pid, nid):
    """El handoff del nodo. "" si falta/ilegible/nodo inválido (falla-suave)."""
    p = resumen_path(pid, nid)
    if not p:
        return ""
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read(RESUMEN_MAX + 1)[:RESUMEN_MAX]
    except OSError:
        return ""


def set_resumen(pid, nid, text):
    """Reescribe el resumen.md del nodo (serializado + atómico). El nodo DEBE
    existir (node.json). {ok} / {ok:False,error}."""
    p = resumen_path(pid, nid)
    if not p:
        return {"ok": False, "error": "nodo inválido"}
    njp = node_json_path(pid, nid)
    if not njp or not os.path.isfile(njp):
        return {"ok": False, "error": "nodo inexistente"}
    text = store._txt(text, RESUMEN_MAX)
    with _LOCK:
        ok = atomic_write_text(p, text)
    return {"ok": bool(ok)} if ok else {"ok": False, "error": "no pude guardar"}


# ═══════════════════════════════════════════════════════════════════════════
# F5 · archivos/ por nodo — superficie de SEGURIDAD (subida/listado/descarga)
#   Defensas: sanear nombre (unicode NFC, sin separadores/`..`/absolutos/
#   reservados-Win), ALLOWLIST de extensiones (bloquea ejecutables), cap de
#   tamaño, y realpath CONFINADO a archivos/ del nodo (anti-traversal/symlink).
#   La descarga la sirve el handler como attachment (no se ejecuta) — F6.
# ═══════════════════════════════════════════════════════════════════════════
FILE_MAX = 25 * 1024 * 1024              # 25 MB por archivo
FILENAME_MAX = 120

#: ALLOWLIST — solo estas extensiones se aceptan. Documentos, imágenes, datos,
#: audio/video y archivos comprimidos. NADA ejecutable/scriptable
#: (.exe/.sh/.bat/.cmd/.com/.msi/.app/.py/.js/.rb/.php/.jar/.ps1/.scr/.dll…):
#: bloquear por allowlist es más seguro que por blocklist (un ejecutable con
#: extensión desconocida no cuela).
ALLOWED_EXT = frozenset({
    ".txt", ".md", ".markdown", ".rtf", ".csv", ".tsv", ".json", ".yaml",
    ".yml", ".xml", ".log", ".ini", ".toml",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".pages", ".numbers", ".key", ".epub",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".heic", ".svg",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac",
    ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v",
    ".zip", ".gz", ".tar", ".tgz", ".7z", ".bz2",
})
#: nombres reservados de Windows (con o sin extensión) — un archivo «CON.txt»
#: rompe en el Windows de un socio.
_WIN_RESERVED = ({"con", "prn", "aux", "nul"}
                 | {"com%d" % i for i in range(1, 10)}
                 | {"lpt%d" % i for i in range(1, 10)})


def safe_filename(name):
    """Nombre de archivo saneado y SEGURO, o None si no se puede/no se permite.

    Rechaza: separadores de ruta, `..`, absolutos, chars de control, reservados
    de Windows, y extensiones fuera del allowlist. Normaliza unicode (NFC) para
    que dos formas del mismo nombre no colisionen ni escapen validación."""
    if not isinstance(name, str):
        return None
    name = unicodedata.normalize("NFC", name)
    # chars de control / NUL → RECHAZAR (un \x00 trunca la ruta en C): no se
    # limpian en silencio, es señal de nombre malicioso.
    if any(ord(c) < 32 for c in name):
        return None
    # recortar puntos/espacios de los bordes (Windows no los tolera al final)
    name = name.strip().strip(". ")
    if not name or name in (".", ".."):
        return None
    # RECHAZAR (no reducir a basename): separadores y traversal. Explícito >
    # silencioso — reducir «a/b.txt» a «b.txt» esconde intención y colisiona.
    if "/" in name or "\\" in name or ".." in name:
        return None
    stem = name.split(".")[0].lower()
    if stem in _WIN_RESERVED:
        return None
    if len(name) > FILENAME_MAX:
        root, ext = os.path.splitext(name)
        name = root[:FILENAME_MAX - len(ext)] + ext
    if os.path.splitext(name)[1].lower() not in ALLOWED_EXT:
        return None
    return name


def _confined(base, name):
    """realpath de base/name CONFINADO a base (anti-traversal/symlink). None si
    escapa. `name` ya viene sin separadores (safe_filename), esto es 2ª defensa."""
    if not base:
        return None
    real_base = os.path.realpath(base)
    cand = os.path.realpath(os.path.join(real_base, name))
    if cand != real_base and not cand.startswith(real_base + os.sep):
        return None
    return cand


def save_file(pid, nid, filename, data):
    """Guarda `data` (bytes) como archivo del nodo. Valida nombre+extensión+cap
    +confinamiento. {ok, name, size} / {ok:False, error}. Never-overwrite del
    árbol: escritura atómica (tmp+replace) dentro de archivos/."""
    name = safe_filename(filename)
    if not name:
        return {"ok": False, "error": "nombre o extensión no permitidos"}
    if not isinstance(data, (bytes, bytearray)):
        return {"ok": False, "error": "datos inválidos"}
    if len(data) > FILE_MAX:
        return {"ok": False,
                "error": "archivo excede el máximo (%d MB)" % (FILE_MAX // 1048576)}
    ad = archivos_dir(pid, nid)
    njp = node_json_path(pid, nid)
    if not ad or not njp or not os.path.isfile(njp):
        return {"ok": False, "error": "nodo inexistente"}
    with _LOCK:
        try:
            os.makedirs(ad, exist_ok=True)
            target = _confined(ad, name)
            if not target:
                return {"ok": False, "error": "ruta no permitida"}
            tmp = "%s.tmp.%d.%s" % (target, os.getpid(), uuid.uuid4().hex[:8])
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, target)
        except OSError:
            return {"ok": False, "error": "no pude guardar"}
    return {"ok": True, "name": name, "size": len(data)}


def list_files(pid, nid):
    """[{name, size, modified}] de archivos/ del nodo, por nombre. [] si vacío."""
    ad = archivos_dir(pid, nid)
    if not ad or not os.path.isdir(ad):
        return []
    out = []
    try:
        entries = sorted(os.listdir(ad))
    except OSError:
        return []
    for e in entries:
        if ".tmp." in e:                 # tmp de una escritura en curso: se omite
            continue
        fp = os.path.join(ad, e)
        try:
            if not os.path.isfile(fp):
                continue
            out.append({"name": e, "size": os.path.getsize(fp),
                        "modified": int(os.path.getmtime(fp))})
        except OSError:
            continue
    return out


def read_file(pid, nid, filename):
    """(name, bytes) de un archivo del nodo para DESCARGA, o None. El handler lo
    sirve como attachment (Content-Disposition), nunca inline/ejecutado — F6."""
    name = safe_filename(filename)
    if not name:
        return None
    ad = archivos_dir(pid, nid)
    if not ad:
        return None
    target = _confined(ad, name)
    if not target or not os.path.isfile(target):
        return None
    try:
        with open(target, "rb") as fh:
            return name, fh.read(FILE_MAX + 1)[:FILE_MAX]
    except OSError:
        return None
