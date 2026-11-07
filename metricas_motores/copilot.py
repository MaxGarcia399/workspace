"""WORKSPACE · metricas_motores.copilot — parser de métricas de GitHub Copilot CLI.

Fuente: el respaldo que Workspace deja al cerrar
(`<estado>/transcripts-backup/<enc>/copilot-<uuid>.jsonl`; session_continuity.
capture_copilot): una cabecera `copilot_session` y cada evento del registro
oficial `<COPILOT_HOME>/session-state/<uuid>/events.jsonl` envuelto en
`copilot_event`. Se REESCRIBE entero en cada cierre → cursor por filas
(metricas.recorrer_reescrito) y huellas por id de evento. Lee también el
registro crudo (sin envoltura), por si el núcleo recibe ese.

Formato VERIFICADO con una sesión real del guion G1 (GitHub Copilot 1.0.105,
macOS, cuenta de Copilot, claude-haiku-5.5, 2026-11-06; golden en
tests/fixtures/metricas/copilot/1.0.105/) y otra de 1.0.106 (Copilot se actualiza
solo; mismas claves en lo que se lee aquí: tests/fixtures/metricas/copilot/1.0.106/).
Solo claves:
  · cada evento {type, data, id, timestamp, parentId}.
  · session.start     data.copilotVersion, data.selectedModel,
                      data.reasoningEffort, data.context.cwd, data.sessionId.
  · session.resume    data.selectedModel, data.reasoningEffort (sin versión).
  · session.model_change  data.newModel.
  · user.message      data.content (lo que escribió el socio), data.turnId.
  · assistant.turn_start / assistant.turn_end   data.turnId: UNA ventana por
                      llamada al modelo (el turnId sube en cada paso del agente
                      y vuelve a 0 al retomar).
  · session.usage_record  data.usage{model, inputTokens, outputTokens,
                      cacheReadTokens, cacheWriteTokens, reasoningTokens, cost,
                      isByok, provider.kind, initiator}: UNA por llamada.
                      inputTokens INCLUYE la caché: 23888 = 4 + 16177 + 7707
                      (lo confirma copilotUsage.tokenDetails, que separa input,
                      cache_read y cache_write); outputTokens incluye el
                      razonamiento (tokenDetails.output = outputTokens).
                      `cost` son premium requests, no USD, y NO se suma por
                      llamada (7 llamadas → 1 en session.shutdown).
  · assistant.message data.model, data.content, data.toolRequests[].
  · tool.execution_start   data.toolName (view, create, edit, bash…),
                      data.arguments{path|command}, data.toolCallId.
  · tool.execution_complete data.success, data.error.code («failure»,
                      «denied»), data.shellExecution.exitCode (bash: un comando
                      que sale con ≠ 0 es success = true + exitCode).
  · system.message, session.usage_checkpoint, session.shutdown (acumulados de la
    sesión), permission.requested/completed → se reconocen y no cuentan.
  · instruction.update / instruction.update_delivery (guía que Copilot inyecta,
    vistas al retomar en la segunda corrida viva, no en la golden) → se
    reconocen y no cuentan.
"""
import json
import os

import metricas as M

MOTOR = "copilot"
VERSION = "copilot/2"
#: Versiones EXACTAS verificadas con su golden (tests/fixtures/metricas/copilot/<versión>/).
VERIFIED_VERSIONS = ("1.0.105", "1.0.106")
COBERTURA = {
    "motor_version": ("parcial", "session.start.data.copilotVersion en el tramo que abre la "
                                 "sesión; al retomar (session.resume no la trae), la caché de "
                                 "engine_versions al cerrar en vivo; null en la historia"),
    "modo_senales": ("no", "el registro no dice cómo se lanzó la sesión (1.0.105 y 1.0.106)"),
    "duracion_activa_s": ("parcial", "suma de las ventanas assistant.turn_start → turn_end; un "
                                     "paso cortado no trae turn_end"),
    "tiempo_humano_est_s": ("si", ""),
    "modelos": ("si", "session.usage_record.usage; entrada = inputTokens − cacheRead − "
                      "cacheWrite"),
    "modelo_pedido": ("si", "selectedModel de session.start / session.resume; "
                            "session.model_change.newModel"),
    "esfuerzo": ("si", "reasoningEffort de session.start / session.resume"),
    "permisos": ("no", "solo permission.* por herramienta, no el modo de la sesión "
                       "(1.0.105 y 1.0.106)"),
    "tokens_motor": ("no", "session.shutdown trae el acumulado de la sesión (modelMetrics), "
                           "no el del tramo"),
    "costo_usd": ("no", "usage.cost son premium requests de Copilot, no USD (1.0.105 y 1.0.106)"),
    "facturacion": ("si", "usage.isByok + usage.provider.kind (suscripcion:copilot "
                          "verificado; byok:<proveedor> sin golden)"),
    "cuota": ("no", "el registro no la trae (1.0.105 y 1.0.106)"),
    "herramientas.llamadas": ("si", "tool.execution_start"),
    "herramientas.errores": ("si", "tool.execution_complete.success = false"),
    "herramientas.comandos_no_cero": ("si", "tool.execution_complete.shellExecution.exitCode"),
    "respuestas_error": ("no", "sin verificar cómo registra un error del proveedor "
                               "(1.0.105 y 1.0.106)"),
    "interrupciones": ("no", "sin verificar el evento de interrupción: la G1 mínima no "
                             "interrumpe (1.0.105 y 1.0.106)"),
    "mensajes_usuario": ("si", "user.message"),
    "skills": ("si", "herramienta view sobre …/skills/<nombre>/SKILL.md"),
    "escritos.archivos": ("parcial", "create/edit que salieron bien; lo escrito por bash no "
                                     "se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("no", "no los separa (sin verificar task/agentes)"),
    "turnos": ("si", "cada user.message abre uno"),
}
CONTINUACION = {"retomar": "respaldo_reescrito", "continuar": "desconocido"}

_HEADER = "copilot_session"
_WRAP = "copilot_event"
_TIPOS = frozenset((
    "session.start", "session.resume", "session.model_change", "session.shutdown",
    "session.usage_record", "session.usage_checkpoint", "session.compaction_complete",
    "user.message", "system.message", "assistant.turn_start", "assistant.turn_end",
    "assistant.message", "tool.execution_start", "tool.execution_complete",
    "permission.requested", "permission.completed", "instruction.update",
    "instruction.update_delivery"))
#: se reconocen y no cuentan (sistema, acumulados de la sesión, permisos, guía
#: que Copilot inyecta al retomar)
_SIN_CONTAR = frozenset(("system.message", "session.shutdown", "session.usage_checkpoint",
                         "session.compaction_complete", "permission.requested",
                         "permission.completed", "instruction.update",
                         "instruction.update_delivery"))
_ESCRIBE = frozenset(("create", "edit"))


def _evento(d):
    """La línea → (tipo, evento) desenvolviendo `copilot_event`."""
    if d.get("type") == _WRAP and isinstance(d.get("event"), dict):
        d = d["event"]
    return d.get("type"), d


def _entrada(u):
    """Entrada SIN caché: inputTokens trae la caché adentro (ver docstring)."""
    total = M.entero(u.get("inputTokens"))
    if total is None:
        return None
    resto = total - (M.entero(u.get("cacheReadTokens")) or 0) \
        - (M.entero(u.get("cacheWriteTokens")) or 0)
    return resto if resto >= 0 else None


class _Minero(object):
    """Lee las líneas NUEVAS de un tramo. Una instancia por tramo."""

    def __init__(self, tramo, abiertos=None):
        self.t = tramo
        #: turnId → ts de assistant.turn_start (sigue en el cursor si el tramo
        #: se corta entre el inicio y el fin de un paso)
        self.inicio = dict(abiertos) if isinstance(abiertos, dict) else {}
        self.escrituras = {}          # toolCallId → ruta (cuenta si no falla)

    def _sesion(self, data):
        """session.start / session.resume: lo que pidió el socio."""
        if isinstance(data.get("selectedModel"), str):
            self.t.modelo_pedido = M.nombre_modelo(data["selectedModel"])
        if isinstance(data.get("reasoningEffort"), str):
            self.t.esfuerzo = data["reasoningEffort"]

    def linea(self, d):
        if d.get("type") == _HEADER:
            self.t.reconocer()
            if self.t.cwd is None and isinstance(d.get("cwd"), str):
                self.t.cwd = d["cwd"]
            return
        tipo, e = _evento(d)
        if tipo not in _TIPOS:
            self.t.desconocer(tipo)   # solo el NOMBRE del tipo, jamás contenido
            return
        self.t.reconocer()
        data = e.get("data") if isinstance(e.get("data"), dict) else {}
        ts = M.epoch(e.get("timestamp"))
        if tipo == "session.start":
            if isinstance(data.get("copilotVersion"), str):
                self.t.version = data["copilotVersion"][:40]
            ctx = data.get("context") if isinstance(data.get("context"), dict) else {}
            if self.t.cwd is None and isinstance(ctx.get("cwd"), str):
                self.t.cwd = ctx["cwd"]
            self._sesion(data)
            return
        if tipo == "session.resume":
            self._sesion(data)
            return
        if tipo == "session.model_change":
            if isinstance(data.get("newModel"), str):
                self.t.modelo_pedido = M.nombre_modelo(data["newModel"])
            return
        if tipo in _SIN_CONTAR:
            return
        if tipo == "assistant.turn_start":
            if ts is not None and data.get("turnId") is not None:
                self.inicio[str(data["turnId"])] = ts
            return
        clave = "%s:%s" % (tipo, e.get("id")) if e.get("id") else ""
        if not self.t.nuevo(clave, ts):
            return                    # ya contado (retomar, respaldo reescrito)
        if tipo == "user.message":
            self.t.mensajes += 1
            self.t.ts(ts)
            c = data.get("content")
            # el texto se usa SOLO para clasificar el turno; se tira
            self.t.turno(ts, c if isinstance(c, str) else None, "humano")
        elif tipo == "assistant.turn_end":
            self.t.ts(ts)
            t0 = self.inicio.pop(str(data.get("turnId")), None)
            if t0 is not None and ts is not None and ts >= t0:
                self.t.activa((ts - t0) * 1000.0)
        elif tipo == "session.usage_record":
            self.t.ts(ts)
            self.t.respuesta(ts)
            u = data.get("usage") if isinstance(data.get("usage"), dict) else None
            if u is None:
                return
            toks = {"entrada": _entrada(u),
                    "salida": M.entero(u.get("outputTokens")),
                    "cache_lectura": M.entero(u.get("cacheReadTokens")),
                    "cache_escritura": M.entero(u.get("cacheWriteTokens")),
                    "cache_escritura_1h": None,
                    "razonamiento": M.entero(u.get("reasoningTokens"))}
            if all(v is None for v in toks.values()):
                # el registro de uso cambió de forma: sin tokens, null (jamás 0)
                self.t.sin_dato.add("modelos")
                self.t.avisos.add("sin_tokens")
            else:
                self.t.uso(u.get("model"), toks)
            prov = u.get("provider") if isinstance(u.get("provider"), dict) else {}
            if u.get("isByok") is False and prov.get("kind") == "copilot":
                self.t.facturacion = "suscripcion:copilot"
            elif u.get("isByok") is True:
                self.t.facturacion = "byok:%s" % (prov.get("kind") or "?")
        elif tipo == "assistant.message":
            self.t.ts(ts)
            self.t.respuesta(ts)
        elif tipo == "tool.execution_start":
            self.t.ts(ts)
            self.t.respuesta(ts)
            self.t.llamadas += 1
            nombre = str(data.get("toolName") or "")
            args = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
            ruta = args.get("path")
            if nombre == "view" and isinstance(ruta, str):
                self.t.skills_de_texto(ruta)
            elif nombre in _ESCRIBE and isinstance(ruta, str) and data.get("toolCallId"):
                self.escrituras[data["toolCallId"]] = ruta
        elif tipo == "tool.execution_complete":
            self.t.ts(ts)
            self.t.respuesta(ts)
            ruta = self.escrituras.pop(data.get("toolCallId"), None)
            if data.get("success") is False:
                self.t.errores += 1
            elif ruta:
                self.t.escrito(ruta)
            sh = data.get("shellExecution") if isinstance(data.get("shellExecution"), dict) else {}
            code = M.entero(sh.get("exitCode"))
            if code is not None and code != 0:
                self.t.comandos_no_cero += 1


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    """Id de sesión de Copilot para ese archivo ('' si no se sabe): la cabecera
    del respaldo o, en el registro crudo, session.start.data.sessionId."""
    d = M.primera_linea(path)
    if d.get("type") == _HEADER:
        return str(d.get("id") or "")
    tipo, e = _evento(d)
    if tipo == "session.start" and isinstance(e.get("data"), dict):
        return str(e["data"].get("sessionId") or "")
    return ""


def cabecera(path):
    """(cwd, primer instante): el cwd de la cabecera y la hora del primer
    evento (session.start, la segunda línea del respaldo)."""
    cwd, ts = None, None
    try:
        with open(M.ruta_larga(path), "rb") as fh:
            for i, raw in enumerate(fh):
                if i >= 5 or (cwd and ts):
                    break
                try:
                    d = json.loads(raw.decode("utf-8-sig", "replace"))
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                if d.get("type") == _HEADER:
                    if isinstance(d.get("cwd"), str):
                        cwd = cwd or d["cwd"]
                    continue
                _t, e = _evento(d)
                ts = ts or M.epoch(e.get("timestamp"))
    except OSError:
        pass
    return cwd, ts


def minar(path, cur, tramo, hasta_t=None, cola=False):
    """Mide lo NUEVO desde el cursor. El respaldo se reescribe entero en cada
    cierre → M.recorrer_reescrito + huellas por id de evento. Un paso del
    agente que quedó abierto (turn_start sin turn_end) sigue en el cursor."""
    mo = _Minero(tramo, cur.get("pasos_abiertos"))
    nuevo, completo = M.recorrer_reescrito(path, cur, mo.linea, tramo, hasta_t)
    nuevo["pasos_abiertos"] = mo.inicio
    return {"cursor": nuevo, "completo": completo, "costo": None}


def al_dia(path, cur):
    """importar: ¿nada nuevo? (misma firma del respaldo)."""
    return M.al_dia_por_firma(path, cur)


def transcript_de_cierre(brain, payload):
    """Sin transcript legible (esquema no reconocido) el cierre igual deja el
    respaldo envuelto: se mide ese."""
    p = str((payload or {}).get("backup") or "")
    return p if p and os.path.isfile(M.ruta_larga(p)) else ""


def raices():
    """Los respaldos de Workspace: <estado>/transcripts-backup/<enc>/."""
    import paths
    return [(os.path.join(paths.state_dir(), "transcripts-backup"), 1)]


def es_fuente(nombre):
    return nombre.startswith("copilot-") and nombre.endswith(".jsonl")


def fuentes():
    """Respaldos `copilot-<uuid>.jsonl` de <estado>/transcripts-backup/<enc>/."""
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
            if es_fuente(f):
                p = os.path.join(full, f)
                sid = sesion(p)
                if sid:
                    out.append((sid, p))
    return out
