#!/usr/bin/env python3
"""WORKSPACE · proyectos_api_v2 — adaptadores HTTP del almacén v2 (stdlib 3.9+).

Traduce entre el contrato del handler (GET = dict de querystring `parse_qs`, con
valores en LISTA; POST = body JSON dict) y las funciones de `proyectos_fsstore`.
Delgado a propósito: la lógica y TODA la seguridad (saneo de nombre, allowlist,
cap, confinamiento) viven en fsstore — aquí solo se desempaqueta y se delega, sin
re-implementar nada.

La DESCARGA es el único caso que no devuelve JSON: `file_download` regresa
(name, bytes) para que el handler lo sirva como attachment (nunca inline), o None.
"""
import base64

import proyectos_fsstore as fs

#: tope del string base64 que aceptamos decodificar (evita gastar memoria en un
#: payload gigante antes de que el cap de bytes de fsstore lo rechace). 25 MB de
#: binario ≈ 33.4 MB en base64.
_B64_MAX = (fs.FILE_MAX * 4) // 3 + 1024


def _one(q, key):
    """Un valor string de un dict de querystring (`parse_qs` da listas). None si
    falta o no es string."""
    v = q.get(key) if isinstance(q, dict) else None
    if isinstance(v, list):
        v = v[0] if v else None
    return v if isinstance(v, str) else None


# ── GET (reciben el dict de parse_qs) ───────────────────────────────────────
def api_session_agents(q):
    """Agentes con hilo en el nodo (pestañas del chat)."""
    return {"ok": True,
            "agents": fs.list_session_agents(_one(q, "project_id"),
                                             _one(q, "node_id"))}


def api_session_days(q):
    """Días con sesión para (nodo × agente) — navegación del historial."""
    return {"ok": True,
            "days": fs.list_session_days(_one(q, "project_id"),
                                         _one(q, "node_id"), _one(q, "agent"))}


def api_session_read(q):
    """Vueltas de la sesión de (nodo × agente × día). `dia` opcional = hoy."""
    return {"ok": True,
            "turns": fs.read_session(_one(q, "project_id"), _one(q, "node_id"),
                                     _one(q, "agent"), _one(q, "dia"))}


def api_files(q):
    """Listado de archivos/ del nodo."""
    return {"ok": True,
            "files": fs.list_files(_one(q, "project_id"), _one(q, "node_id"))}


def api_resumen_get(q):
    """El resumen.md (handoff) del nodo."""
    return {"ok": True,
            "text": fs.get_resumen(_one(q, "project_id"), _one(q, "node_id"))}


# ── POST (reciben el body dict) ─────────────────────────────────────────────
def api_resumen_set(data):
    """Reescribe el resumen.md del nodo."""
    if not isinstance(data, dict):
        data = {}
    return fs.set_resumen(data.get("project_id"), data.get("node_id"),
                          data.get("text") or "")


def api_file_upload(data):
    """Sube un archivo al nodo. El binario viaja en base64 ({name, data_b64}) —
    así se aprovecha el POST-JSON existente sin parser multipart (cero deps). El
    saneo/allowlist/cap real lo hace fs.save_file."""
    if not isinstance(data, dict):
        return {"ok": False, "error": "payload inválido"}
    b64 = data.get("data_b64") or ""
    if not isinstance(b64, str) or len(b64) > _B64_MAX:
        return {"ok": False, "error": "archivo excede el máximo permitido"}
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:                      # base64 corrupto (binascii.Error) → rechazo
        return {"ok": False, "error": "datos inválidos (base64)"}
    return fs.save_file(data.get("project_id"), data.get("node_id"),
                        data.get("name"), raw)


# ── descarga (NO-JSON: el handler la sirve como attachment) ──────────────────
def file_download(q):
    """(name, bytes) del archivo, o None. El handler lo emite con
    Content-Disposition: attachment (nunca inline/ejecutado)."""
    return fs.read_file(_one(q, "project_id"), _one(q, "node_id"),
                        _one(q, "name"))


def api_file_data(q):
    """Descarga EMBEBIDA (base64 JSON): la usa la superficie de dev, cuyo
    framework sirve JSON y no binario. El cliente re-arma el Blob. Reusa
    `fs.read_file` (mismo saneo/confín/allowlist). {ok, name, data_b64}."""
    res = fs.read_file(_one(q, "project_id"), _one(q, "node_id"), _one(q, "name"))
    if not res:
        return {"ok": False, "error": "archivo no encontrado"}
    name, raw = res
    return {"ok": True, "name": name,
            "data_b64": base64.b64encode(raw).decode("ascii")}
