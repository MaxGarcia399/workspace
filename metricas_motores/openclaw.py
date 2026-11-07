"""WORKSPACE · metricas_motores.openclaw — parser de métricas de OpenClaw.

Fuentes (las dos las deja Workspace al cerrar, sin lanzar nada más):
  1. el respaldo `<estado>/transcripts-backup/<enc>/openclaw-<sessionId>.jsonl`
     (session_continuity.capture_openclaw): cabecera {type: "session", id,
     cwd} + filas {type: "message", timestamp, message{role, …}}. Trae los
     mensajes del usuario y del asistente con su uso, pero NO los resultados
     de herramienta (errores), el run abortado (interrupciones) ni la versión.
  2. un SIDECAR solo de números y nombres, `openclaw-<sessionId>.eventos.jsonl`,
     que capture escribe (guardar_eventos) a partir del `events.jsonl` del
     export oficial que YA corre al cerrar (`sessions export-trajectory`).
     Es aditivo: quien lee el respaldo no cambia.
Ambos se REESCRIBEN enteros en cada cierre → cursor por filas
(metricas.recorrer_reescrito) y huellas por (sesión, id): los ids de
herramienta y de run de OpenClaw son cortos y no son únicos entre sesiones.

Formato VERIFICADO (solo claves; OpenClaw 2026.10.7, 2026-10; mapa F1):
  · assistant: usage{input, output, cacheRead, cacheWrite, reasoningTokens,
    totalTokens, cost{total, totalOrigin}}; totalTokens = input + output +
    cacheRead + cacheWrite → `output` YA incluye el razonamiento.
    model (pedido, p. ej. openrouter/auto) y responseModel (el que respondió:
    se usa este); content[] {type: "toolCall", id, name, arguments{path}}.
  · user: content, timestamp, idempotencyKey.
  · toolResult (solo en el .jsonl nativo de 2026.5 y en session-branch del
    export): **isError es false incluso en «no existe»**; el error real está
    en details.status (not_found / error / failed).
  · events.jsonl del export: trace.metadata{data.harness.version},
    session.started / session.ended{data.status: success | interrupted} por
    runId, tool.result{data.success, data.message{toolCallId, isError,
    details.status}}, model.completed{data.aborted}.
"""
import json
import os
import re

import metricas as M

MOTOR = "openclaw"
VERSION = "openclaw/3"
VERIFIED_VERSIONS = ("2026.10.7",)
COBERTURA = {
    "motor_version": ("parcial", "solo del sidecar de eventos (trace.metadata)"),
    "modo_senales": ("no", "el respaldo no dice cómo se lanzó la sesión"),
    "duracion_activa_s": ("parcial", "de session.started a session.ended por run, solo "
                                     "con el sidecar de eventos"),
    "tiempo_humano_est_s": ("si", ""),
    "modelos": ("si", "responseModel (el que respondió)"),
    "modelo_pedido": ("si", "message.model (lo pedido, p. ej. openrouter/auto)"),
    "esfuerzo": ("no", "el respaldo no lo trae"),
    "permisos": ("no", "el respaldo no lo trae"),
    "tokens_motor": ("no", "solo Claude Code expone el total del motor por modelo"),
    "costo_usd": ("si", "usage.cost.total; costo_tipo «facturado» si totalOrigin = "
                        "provider-billed, si no «estimado» (tabla de precios del motor)"),
    "facturacion": ("no", "el respaldo no lo trae"),
    "cuota": ("no", "el respaldo no lo trae"),
    "herramientas.llamadas": ("si", ""),
    "herramientas.errores": ("parcial", "solo con el sidecar de eventos (o el .jsonl "
                                        "nativo con toolResult); isError miente"),
    "herramientas.comandos_no_cero": ("no", "no se separa el código de salida"),
    "respuestas_error": ("no", "el respaldo no trae los errores del proveedor"),
    "interrupciones": ("parcial", "solo con el sidecar de eventos"),
    "mensajes_usuario": ("si", ""),
    "skills": ("si", "herramienta read"),
    "escritos.archivos": ("parcial", "write/edit/apply_patch; lo escrito por shell no se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("no", "el respaldo no los separa"),
    "turnos": ("si", ""),
}
CONTINUACION = {"retomar": "respaldo_reescrito", "continuar": "desconocido"}
_TIPOS = frozenset(("session", "message", "model_change", "thinking_level_change",
                    "custom", "custom_message", "compaction", "branch_summary", "label",
                    "session_info"))
_TIPOS_EVENTOS = frozenset(("trace.metadata", "session.started", "session.ended",
                            "tool.result", "model.completed",
                            "workspace.sidecar"))   # 1ª fila: la procedencia del sidecar

_ESCRITURA = ("write", "edit", "apply_patch", "multiedit")
_FALLO = ("not_found", "error", "failed", "denied", "timeout")
_OK = ("ok", "success", "succeeded", "completed", "done")
_CORTE = ("interrupted", "aborted", "killed", "cancelled", "canceled")


def _enum_resultado(v):
    """details.status → ok | error | otro (jamás texto libre en el sidecar)."""
    if not isinstance(v, str) or not v:
        return None
    v = v.lower()
    return "error" if v in _FALLO else ("ok" if v in _OK else "otro")


def _enum_run(v):
    """status de un run → ok | error | interrumpido | otro."""
    if not isinstance(v, str) or not v:
        return None
    v = v.lower()
    if v in _CORTE:
        return "interrumpido"
    return "error" if v in _FALLO else ("ok" if v in _OK else "otro")
SUFIJO_EVENTOS = ".eventos.jsonl"


# ── sidecar de eventos (lo escribe session_continuity al capturar) ──────────

def _evento_limpio(ev):
    """Una fila de events.jsonl → solo los campos que miden (sin texto)."""
    if not isinstance(ev, dict):
        return None
    tipo = ev.get("type")
    data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
    base = {"type": tipo, "ts": ev.get("ts"), "runId": ev.get("runId"), "seq": ev.get("seq")}
    if tipo == "trace.metadata":
        h = data.get("harness") if isinstance(data.get("harness"), dict) else {}
        base["version"] = h.get("version") if isinstance(h.get("version"), str) else None
    elif tipo in ("session.started", "session.ended"):
        base["status"] = _enum_run(data.get("status"))
        base["aborted"] = data.get("aborted") if isinstance(data.get("aborted"), bool) else None
    elif tipo == "tool.result":
        msg = data.get("message") if isinstance(data.get("message"), dict) else {}
        det = msg.get("details") if isinstance(msg.get("details"), dict) else {}
        base.update(name=M.nombre_limpio(data.get("name") or msg.get("toolName")),
                    success=data.get("success") if isinstance(data.get("success"), bool) else None,
                    toolCallId=msg.get("toolCallId") if isinstance(msg.get("toolCallId"), str) else None,
                    isError=msg.get("isError") if isinstance(msg.get("isError"), bool) else None,
                    detailsStatus=_enum_resultado(det.get("status")))
    elif tipo == "model.completed":
        base["aborted"] = data.get("aborted") if isinstance(data.get("aborted"), bool) else None
    else:
        return None
    return base


def guardar_eventos(events_path, destino):
    """Del events.jsonl del export oficial → `destino` (sidecar solo de
    números y nombres; atómico). Lo llama capture al cerrar. → nº de filas."""
    filas = []
    with open(M.ruta_larga(events_path), encoding="utf-8-sig", errors="replace") as fh:
        for ln in fh:
            try:
                e = _evento_limpio(json.loads(ln))
            except ValueError:
                continue
            if e:
                filas.append(e)
    lineas = [json.dumps(dict(M.procedencia(MOTOR), type="workspace.sidecar"))]
    lineas += [json.dumps(e, ensure_ascii=False) for e in filas]
    M.guardar(destino, "\n".join(lineas) + "\n")   # atómico, lector abierto y ruta larga
    return len(filas)


def ruta_eventos(path):
    return path[:-len(".jsonl")] + SUFIJO_EVENTOS if path.endswith(".jsonl") else path + SUFIJO_EVENTOS


# ── parser ──────────────────────────────────────────────────────────────────

def _texto(c):
    """Texto de un mensaje (string o bloques) SOLO para su largo y similitud."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        partes = [b.get("text") for b in c if isinstance(b, dict) and isinstance(b.get("text"), str)]
        return "\n".join(partes) if partes else None
    return None


def _fallo(det_status, is_error, success=None):
    return (is_error is True or success is False
            or (isinstance(det_status, str) and det_status.lower() in _FALLO))


class _Minero(object):
    def __init__(self, tramo, fallidas):
        self.t = tramo
        self.fallidas = fallidas     # toolCallId con resultado fallido (sidecar)
        self.escrituras = {}         # toolCallId → ruta
        self.costo = None
        self.vio_resultados = False  # filas toolResult en el propio respaldo
        self.origenes_costo = set()  # usage.cost.totalOrigin vistos

    def linea(self, d):
        if d.get("type") not in _TIPOS:
            self.t.desconocer(d.get("type"))
            return
        self.t.reconocer()
        if d.get("type") == "session":
            if self.t.cwd is None and isinstance(d.get("cwd"), str):
                self.t.cwd = d["cwd"]
            return
        m = d.get("message") if d.get("type") == "message" else None
        if not isinstance(m, dict):
            return
        ts = M.epoch(d.get("timestamp")) or M.epoch(m.get("timestamp"))
        rol = m.get("role")
        if rol == "user":
            clave = "%s|%s" % (m.get("idempotencyKey"), m.get("timestamp") or d.get("timestamp"))
            if self.t.nuevo("u:%s:%s" % (self.t.sid, clave), ts):
                self.t.mensajes += 1
                self.t.ts(ts)
                self.t.turno(ts, _texto(m.get("content")), "humano")
        elif rol == "assistant":
            clave = "%s|%s|%s" % (m.get("responseId"), m.get("timestamp") or d.get("timestamp"),
                                  (m.get("__openclaw") or {}).get("runId"))
            if self.t.nuevo("a:%s:%s" % (self.t.sid, clave), ts):
                self._asistente(m, ts)
        elif rol == "toolResult":      # .jsonl nativo (2026.5) / session-branch
            self.vio_resultados = True
            tid = m.get("toolCallId")
            if self.t.nuevo("r:%s:%s" % (self.t.sid, tid) if tid else "", ts):
                det = m.get("details") if isinstance(m.get("details"), dict) else {}
                if _fallo(det.get("status"), m.get("isError")):
                    self.fallidas.add(tid)
                    self.t.errores += 1

    def _asistente(self, m, ts):
        self.t.ts(ts)
        self.t.respuesta(ts)
        if isinstance(m.get("model"), str) and m["model"]:
            self.t.modelo_pedido = m["model"]       # lo pedido (p. ej. openrouter/auto)
        u = m.get("usage")
        if isinstance(u, dict):
            self.t.uso(m.get("responseModel") or m.get("model"), {
                "entrada": M.entero(u.get("input")),
                "salida": M.entero(u.get("output")),
                "cache_lectura": M.entero(u.get("cacheRead")),
                "cache_escritura": M.entero(u.get("cacheWrite")),
                "cache_escritura_1h": None,
                "razonamiento": M.entero(u.get("reasoningTokens")),
            })
            c = u.get("cost") if isinstance(u.get("cost"), dict) else {}
            if M.numero(c.get("total")) is not None:
                self.costo = (self.costo or 0.0) + M.numero(c["total"])
                self.origenes_costo.add(M.nombre_limpio(c.get("totalOrigin"), 40) or "?")
        for b in m.get("content") or ():
            if not (isinstance(b, dict) and b.get("type") == "toolCall"):
                continue
            if not self.t.nuevo("t:%s:%s" % (self.t.sid, b["id"]) if b.get("id") else "", ts):
                continue
            self.t.llamadas += 1
            args = b.get("arguments") if isinstance(b.get("arguments"), dict) else {}
            nombre = str(b.get("name") or "").lower()
            if nombre == "read":
                self.t.skills_de_texto(args.get("path"))
            elif nombre in _ESCRITURA and b.get("id"):
                self.escrituras[b["id"]] = args.get("path")

    def fin(self):
        for tid, ruta in self.escrituras.items():
            if tid not in self.fallidas:
                self.t.escrito(ruta)


def _eventos(path, cur, tramo, fallidas, hasta_t=None):
    """Lee el sidecar: errores de herramienta, interrupciones, tiempo activo
    por run y versión. Lo que se cuenta en un turno (errores,
    interrupciones) NO se aplica aquí: vuelve como acciones con su hora, y
    minar las aplica intercaladas con el respaldo, cada una dentro de su
    turno (K4). → (cursor del sidecar o el anterior, completo, acciones)."""
    side = ruta_eventos(path)
    acciones = []
    if not os.path.isfile(M.ruta_larga(side)):
        return cur.get("eventos"), True, acciones
    previo = cur.get("eventos") if isinstance(cur.get("eventos"), dict) else {}
    # runs que empezaron en un tramo anterior y terminan en este
    inicios = dict(previo.get("abiertos") or {})
    terminados = set()

    def linea(e):
        tipo, ts = e.get("type"), M.epoch(e.get("ts"))
        if tipo not in _TIPOS_EVENTOS:
            tramo.desconocer(tipo)
            return
        tramo.reconocer()
        run = e.get("runId")
        if tipo == "trace.metadata" and isinstance(e.get("version"), str):
            tramo.version = e["version"][:40]
        elif tipo == "session.started" and run:
            inicios[run] = ts
        elif tipo == "session.ended" and run:
            terminados.add(run)

            def fin_run(e=e, ts=ts, run=run):
                if tramo.nuevo("fin:%s:%s" % (tramo.sid, run), ts):
                    tramo.ts(ts)
                    if _enum_run(e.get("status")) == "interrumpido" or e.get("aborted") is True:
                        tramo.interrupciones += 1
                    ini = inicios.get(run)
                    if ini is not None and ts is not None and ts >= ini:
                        tramo.activa((ts - ini) * 1000.0)
            acciones.append((ts, fin_run))
        elif tipo == "tool.result":
            def resultado(e=e, ts=ts):
                tid = e.get("toolCallId")
                if tramo.nuevo("r:%s:%s" % (tramo.sid, tid) if tid else "", ts):
                    if _fallo(e.get("detailsStatus"), e.get("isError"), e.get("success")):
                        fallidas.add(tid)
                        tramo.errores += 1
            acciones.append((ts, resultado))
    # cursor por filas propio. Un run que empezó y no terminó en este tramo
    # (cierre a media corrida) guarda su inicio en el cursor: su tiempo activo
    # se cuenta cuando llegue su fin
    cur_ev, completo = M.recorrer_reescrito(side, previo, linea, tramo, hasta_t)
    abiertos = {r: t for r, t in inicios.items() if t is not None and r not in terminados}
    if abiertos:
        cur_ev["abiertos"] = dict(sorted(abiertos.items(), key=lambda x: x[1])[-20:])
    return cur_ev, completo, acciones


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    d = M.primera_linea(path)
    if d.get("type") == "session" and d.get("id"):
        return str(d["id"])
    m = re.match(r"openclaw-(.+)\.jsonl$", os.path.basename(path))
    return m.group(1) if m else ""


def cabecera(path):
    d = M.primera_linea(path)
    if d.get("type") == "session":
        return d.get("cwd"), M.epoch(d.get("timestamp"))
    return None, None


def minar(path, cur, tramo, hasta_t=None, cola=False):
    fallidas = set()
    ev, ev_completo, acciones = _eventos(path, cur, tramo, fallidas, hasta_t)
    mo = _Minero(tramo, fallidas)
    # las acciones del sidecar, en orden de hora, intercaladas con el respaldo:
    # cada error o interrupción cae en el turno que estaba abierto
    pend = sorted((a for a in acciones if a[0] is not None), key=lambda a: a[0])
    sin_hora = [a for a in acciones if a[0] is None]

    def linea(d):
        m = d.get("message") if isinstance(d.get("message"), dict) else {}
        t = M.epoch(d.get("timestamp")) or M.epoch(m.get("timestamp"))
        while pend and t is not None and pend[0][0] <= t:
            pend.pop(0)[1]()
        mo.linea(d)
    l0, r0 = tramo.leidas, tramo.reconocidas
    if ev_completo:
        nuevo, completo = M.recorrer_reescrito(path, cur, linea, tramo, hasta_t)
    else:       # sin tiempo ni para los eventos: el respaldo, en el próximo tramo
        nuevo, completo = {k: cur.get(k) for k in ("n", "ultima", "firma")}, False
    if tramo.leidas > l0 and tramo.reconocidas == r0:
        # el formato se decide sobre el RESPALDO (la fuente principal): que el
        # sidecar se entienda no tapa un respaldo que no (K3c/K2b)
        tramo.formato_desconocido = True
    for _ts, fn in pend + sin_hora:
        fn()
    mo.fin()
    if ev is not None:
        nuevo["eventos"] = ev
    else:
        # sin el export no hay resultados de herramienta ni runs abortados
        # (salvo en el .jsonl nativo de 2026.5, que trae toolResult)
        tramo.avisos.add("sin_eventos_del_export")
        tramo.degradada = True
        tramo.sin_dato.add("interrupciones")
        if not mo.vio_resultados:
            tramo.sin_dato.add("errores")
    costo = None
    if mo.costo is not None:
        costo = (round(mo.costo, 6), "openclaw:usage.cost.total", None)
        # usage.cost.totalOrigin: «provider-billed» = lo cobró el proveedor;
        # cualquier otro origen (o mezcla), lo calculó el motor con su tabla
        tramo.costo_tipo = ("facturado" if mo.origenes_costo == {"provider-billed"}
                            else "estimado")
    return {"cursor": nuevo, "completo": completo, "costo": costo}


def al_dia(path, cur):
    side = ruta_eventos(path)
    ev = cur.get("eventos") if isinstance(cur.get("eventos"), dict) else {}
    return (M.al_dia_por_firma(path, cur)
            and (not os.path.isfile(M.ruta_larga(side)) or M.al_dia_por_firma(side, ev)))


def raices():
    """Los respaldos de Workspace: <estado>/transcripts-backup/<enc>/."""
    import paths
    return [(os.path.join(paths.state_dir(), "transcripts-backup"), 1)]


def es_fuente(nombre):
    return nombre.startswith("openclaw-") and nombre.endswith(".jsonl") \
        and not nombre.endswith(SUFIJO_EVENTOS)


def fuentes():
    """Respaldos `openclaw-<id>.jsonl` (sin el sidecar) de transcripts-backup/."""
    import paths
    out = []
    base = os.path.join(paths.state_dir(), "transcripts-backup")
    try:
        dirs = os.listdir(base)
    except OSError:
        return out
    for d in dirs:
        full = os.path.join(base, d)
        try:
            files = os.listdir(full) if os.path.isdir(full) else ()
        except OSError:
            continue
        for f in files:
            if f.startswith("openclaw-") and f.endswith(".jsonl") \
                    and not f.endswith(SUFIJO_EVENTOS):
                p = os.path.join(full, f)
                sid = sesion(p)
                if sid:
                    out.append((sid, p))
    return out
