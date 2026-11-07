"""WORKSPACE · metricas_motores.codex — parser de métricas de Codex.

Transcript: `$CODEX_HOME/sessions/AAAA/MM/DD/rollout-*.jsonl` (solo crece; al
retomar, Codex sigue escribiendo en el mismo archivo). Cursor = offset de
bytes + último total de tokens + último modelo.

Formato VERIFICADO (solo claves, sin contenido; codex-cli 0.164, 2026-10):
líneas {timestamp, type, payload}.
  · session_meta{id, cwd, cli_version} (1ª línea).
  · turn_context{model} (una por turno).
  · token_usage_record{response_id, usage{input_tokens (INCLUYE la caché),
    cached_input_tokens, cache_write_input_tokens, output_tokens (incluye el
    razonamiento), reasoning_output_tokens}} → uso EXACTO por respuesta
    (suma == último total del hilo, verificado). Sin estos registros
    (versiones viejas) se usa la diferencia de event_msg
    token_count.info.total_token_usage contra el tramo previo — token_count
    se repite a veces con el mismo total, así que jamás se suma.
  · event_msg task_complete/turn_aborted{turn_id, duration_ms};
    item_completed{item{id, type: UserMessage | CommandExecution{status,
    exit_code, parsed_cmd[{type: read, path}]} | FileChange{status,
    changes{ruta: …}}}}; token_count.rate_limits.{primary,secondary}
    .used_percent → cuota (Codex no da costo).
  · response_item custom_tool_call/function_call{call_id} → llamadas.
  · Versiones viejas: event_msg user_message / exec_command_end /
    patch_apply_end (se usan solo si no hay item_completed en el tramo).
"""
import json
import os

import metricas as M

MOTOR = "codex"
VERSION = "codex/2"
VERIFIED_VERSIONS = ("0.164.0",)
COBERTURA = {
    "motor_version": ("si", "session_meta.cli_version"),
    "modo_senales": ("si", "session_meta.originator / source"),
    "duracion_activa_s": ("si", "task_complete/turn_aborted.duration_ms"),
    "tiempo_humano_est_s": ("si", ""),
    "modelos": ("si", ""),
    "modelo_pedido": ("si", "turn_context.model (Codex no distingue el servido)"),
    "esfuerzo": ("parcial", "turn_context.effort: null cuando se usa el del modelo"),
    "permisos": ("si", "turn_context.approval_policy + sandbox_policy"),
    "tokens_motor": ("no", "solo Claude Code expone el total del motor por modelo"),
    "costo_usd": ("no", "Codex no da costo (cuenta de suscripción)"),
    "facturacion": ("parcial", "token_count.rate_limits.plan_type, si viene"),
    "cuota": ("si", "token_count.rate_limits al inicio y al final del tramo"),
    "herramientas.llamadas": ("si", ""),
    "herramientas.errores": ("si", "ítems fallidos; un comando con código ≠ 0 va aparte"),
    "herramientas.comandos_no_cero": ("si", "CommandExecution.exit_code ≠ 0"),
    "respuestas_error": ("parcial", "event_msg error/stream_error, cuando traen código"),
    "interrupciones": ("si", "turn_aborted"),
    "mensajes_usuario": ("si", ""),
    "skills": ("parcial", "solo SKILL.md leídos por lectores de shell (cat/sed/head…)"),
    "escritos.archivos": ("parcial", "solo apply_patch/FileChange; lo escrito por shell "
                                     "no se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("no", "Codex no deja subagentes en el rollout"),
    "turnos": ("si", ""),
}
CONTINUACION = {"retomar": "mismo_archivo", "continuar": "copia_historial"}
#: la fuente solo crece y cada fila guarda su corte en bytes (captura.hasta):
#: `reconstruir` puede volver a medirla cortándola igual
RECONSTRUIBLE = True
_TIPOS = frozenset(("session_meta", "turn_context", "token_usage_record", "event_msg",
                    "response_item", "world_state", "compacted"))


def _clave(prefijo, valor):
    return "%s:%s" % (prefijo, valor) if valor else ""


_LECTORES = ("cat", "head", "tail", "sed", "less", "more", "bat", "nl", "type", "get-content")


def _rutas_leidas(argumentos):
    """Rutas que un comando de shell LEE (cat/sed/head…): de los argumentos
    JSON de `shell` (versiones viejas) o del comando en texto de `exec`. Nada
    si no es una lectura (apply_patch y escrituras jamás pasan por aquí)."""
    try:
        a = json.loads(argumentos) if isinstance(argumentos, str) else argumentos
    except ValueError:
        a = {"command": argumentos}           # `exec`: el comando en texto plano
    cmd = (a or {}).get("command") if isinstance(a, dict) else None
    if isinstance(cmd, str):
        cmd = cmd.split()
    if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) for x in cmd):
        return []
    if cmd[0] in ("bash", "sh", "zsh") and len(cmd) >= 3 and cmd[1] in ("-lc", "-c"):
        cmd = cmd[2].split()
    if not cmd or os.path.basename(cmd[0]).lower() not in _LECTORES:
        return []
    return [x for x in cmd[1:] if not x.startswith("-")]


def _uso(u):
    """usage de Codex → campos neutrales (input_tokens INCLUYE la caché)."""
    if not isinstance(u, dict):
        return None
    ent, cache = M.entero(u.get("input_tokens")), M.entero(u.get("cached_input_tokens"))
    return {"entrada": None if ent is None else max(0, ent - (cache or 0)),
            "salida": M.entero(u.get("output_tokens")),
            "cache_lectura": cache,
            "cache_escritura": M.entero(u.get("cache_write_input_tokens")),
            "cache_escritura_1h": None,
            "razonamiento": M.entero(u.get("reasoning_output_tokens"))}


def _texto(c):
    """Texto de un mensaje del usuario (string o bloques), SOLO para medir su
    largo y su similitud: jamás se guarda."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        partes = [b.get("text") for b in c if isinstance(b, dict) and isinstance(b.get("text"), str)]
        return "\n".join(partes) if partes else None
    return None


def _clase_error(p):
    """event_msg error/stream_error → clase (4xx | 5xx | bloqueado) o None.
    codex_error_info es un enum (o {enum: {http_status_code}}); el mensaje
    libre no se usa."""
    info = p.get("codex_error_info")
    if isinstance(info, dict):
        for k, v in info.items():
            cod = M.entero((v or {}).get("http_status_code")) if isinstance(v, dict) else None
            return M.clase_error(cod) or M.clase_error(k)
        return None
    cod = M.entero(p.get("http_status_code"))
    return M.clase_error(cod) or M.clase_error(info)


def _cuota(rl):
    if not isinstance(rl, dict):
        return None
    out = {}
    for k, nombre in (("primary", "primaria"), ("secondary", "secundaria")):
        w = rl.get(k)
        if isinstance(w, dict) and M.numero(w.get("used_percent")) is not None:
            out[nombre] = {"usado_pct": M.numero(w.get("used_percent")),
                           "ventana_min": M.entero(w.get("window_minutes"))}
    return out or None


class _Minero(object):
    def __init__(self, tramo, modelo=None):
        self.t = tramo
        self.modelo = modelo
        self.registros = False       # hubo token_usage_record en el tramo
        self.items = False           # hubo item_completed (versiones nuevas)
        self.total = None            # último token_count.total_token_usage
        self.um_viejos = 0           # event_msg user_message (versiones viejas)
        self.err_viejos = 0          # exec_command_end/patch_apply_end fallidos

    def linea(self, d):
        t = d.get("type")
        if t not in _TIPOS:
            self.t.desconocer(t)
            return
        self.t.reconocer()
        p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        ts = M.epoch(d.get("timestamp"))
        if t == "session_meta":
            v = p.get("cli_version")
            if isinstance(v, str) and v:
                self.t.version = v[:40]
            if self.t.cwd is None and isinstance(p.get("cwd"), str):
                self.t.cwd = p["cwd"]
        elif t == "turn_context":
            if isinstance(p.get("model"), str) and p["model"]:
                self.modelo = p["model"]
                self.t.modelo_pedido = p["model"]
            if isinstance(p.get("effort"), str) and p["effort"]:
                self.t.esfuerzo = p["effort"]
            sb = p.get("sandbox_policy")
            sb = sb.get("type") if isinstance(sb, dict) else sb
            perm = "/".join(x for x in (p.get("approval_policy"), sb) if isinstance(x, str) and x)
            if perm:
                self.t.permisos = perm
        elif t == "compacted":
            self.t.compactacion()
        elif t == "token_usage_record":
            self.registros = True
            uso = _uso(p.get("usage"))
            if uso is None:
                self.t.ignoradas += 1
            elif self.t.nuevo(_clave("r", p.get("response_id")), ts):
                self.t.ts(ts)
                self.t.respuesta(ts)
                self.t.uso(self.modelo, uso)
        elif t == "event_msg":
            self._evento(p, ts)
        elif t == "response_item":
            if p.get("type") in ("custom_tool_call", "function_call", "local_shell_call"):
                if self.t.nuevo(_clave("c", p.get("call_id") or p.get("id")), ts):
                    self.t.ts(ts)
                    self.t.respuesta(ts)
                    self.t.llamadas += 1
                    # skills: solo de LECTURAS (versiones viejas sin parsed_cmd:
                    # `shell` con cat/sed/head…); jamás del input de apply_patch
                    if p.get("name") in ("shell", "local_shell", "exec_command", "exec"):
                        for ruta in _rutas_leidas(p.get("arguments") or p.get("input")):
                            self.t.skills_de_texto(ruta)

    def _evento(self, p, ts):
        et = p.get("type")
        if et == "token_count":
            info = p.get("info") if isinstance(p.get("info"), dict) else {}
            if isinstance(info.get("total_token_usage"), dict):
                self.total = info["total_token_usage"]
            rl = p.get("rate_limits") if isinstance(p.get("rate_limits"), dict) else {}
            self.t.ver_cuota(_cuota(rl))
            if isinstance(rl.get("plan_type"), str) and rl["plan_type"]:
                self.t.facturacion = "suscripcion:" + rl["plan_type"]
        elif et in ("task_complete", "turn_aborted"):
            if self.t.nuevo(_clave(et, p.get("turn_id")), ts):
                self.t.ts(ts)
                self.t.activa(p.get("duration_ms"))
                if et == "turn_aborted":
                    self.t.interrupciones += 1
        elif et == "item_completed":
            self._item(p.get("item"), ts, p.get("turn_id"), p.get("completed_at_ms"))
        elif et == "user_message":
            if self.t.nuevo(_clave("um", ts), ts):
                self.t.ts(ts)
                self.um_viejos += 1
                if not self.items:
                    self.t.turno(ts, _texto(p.get("message")), "humano")
        elif et in ("error", "stream_error"):
            if self.t.nuevo(_clave("err", "%s|%s" % (et, ts)), ts):
                self.t.ts(ts)
                clase = _clase_error(p)
                if clase:
                    self.t.respuesta_error(clase)
        elif et == "exec_command_end":
            if self.t.nuevo(_clave("x", p.get("call_id")), ts):
                if M.entero(p.get("exit_code")) not in (None, 0):
                    self.t.comandos_no_cero += 1
        elif et == "patch_apply_end":
            if self.t.nuevo(_clave("pa", p.get("call_id")), ts):
                if p.get("success") is False:
                    self.err_viejos += 1
                elif isinstance(p.get("changes"), dict):
                    for ruta in p["changes"]:
                        self.t.escrito(ruta)

    def _item(self, it, ts, turno=None, hecho=None):
        if not isinstance(it, dict):
            self.t.ignoradas += 1
            return
        self.items = True
        # id + turno + hora de fin: los ids reales son únicos, pero una copia
        # (fork) conserva los tres y un id repetido no se traga ítems
        iid = it.get("id")
        clave = "%s|%s|%s" % (iid, turno, hecho or ts) if iid else ""
        if not self.t.nuevo(_clave("i", clave), ts):
            return
        self.t.ts(ts)
        tipo, estado = it.get("type"), it.get("status")
        if tipo == "UserMessage":
            self.t.mensajes += 1
            self.t.turno(ts, _texto(it.get("content")), "humano")
            return
        self.t.respuesta(ts)
        if tipo == "CommandExecution":
            # un código ≠ 0 (grep sin coincidencias…) no es un error de la
            # herramienta: va aparte. Falló sin código = no se pudo ejecutar
            if M.entero(it.get("exit_code")) not in (None, 0):
                self.t.comandos_no_cero += 1
            elif estado == "failed":
                self.t.errores += 1
            for pc in it.get("parsed_cmd") or ():
                if isinstance(pc, dict) and pc.get("type") == "read":
                    self.t.skills_de_texto(pc.get("path"))
        elif tipo == "FileChange":
            if estado not in (None, "completed"):      # mapa F1: ≠ completed = falló
                self.t.errores += 1
            elif isinstance(it.get("changes"), dict):
                for ruta in it["changes"]:
                    self.t.escrito(ruta)
        elif estado == "failed":
            self.t.errores += 1

    def fin(self, total_previo, con_registros=False):
        """Sin token_usage_record (versiones viejas): tokens = diferencia del
        total ACUMULADO contra un punto de partida seguro — el total del tramo
        anterior de esta sesión, o cero si la sesión no continúa a otra. Una
        sesión que trae historial copiado sin total previo, o un total que
        bajó, no tiene punto de partida: sin tokens (aviso), jamás el
        acumulado heredado."""
        if not self.items:
            self.t.mensajes += self.um_viejos
            self.t.errores += self.err_viejos
        # una sesión que YA dio token_usage_record se mide solo por ellos: un
        # tramo que trae el total pero no su registro (cortado entre los dos)
        # no se mide otra vez por diferencia (prueba de cortes, F1.1)
        if self.registros or con_registros or not isinstance(self.total, dict):
            return
        if self.t.excluidas:        # acumulado con tramo apagado: no se parte
            self.t.avisos.add("periodo_apagado")
            return
        if isinstance(total_previo, dict):
            prev = total_previo
        elif self.t.copias:
            self.t.avisos.add("tokens_sin_punto_de_partida")
            return
        else:
            prev = {}
        if any((M.entero(self.total.get(k)) or 0) < (M.entero(prev.get(k)) or 0)
               for k in self.total):
            self.t.avisos.add("tokens_sin_punto_de_partida")
            return
        delta = {}
        for k, v in self.total.items():
            v = M.entero(v)
            if v is not None:
                delta[k] = v - (M.entero(prev.get(k)) or 0)
        uso = _uso(delta)
        if uso and any(uso.get(k) for k in ("entrada", "salida", "cache_lectura")):
            self.t.nuevos += 1
            self.t.uso(self.modelo, uso)


def _meta(path):
    """(id de sesión, cwd, versión, payload) de la 1ª línea (session_meta)."""
    d = M.primera_linea(path)
    p = d.get("payload")
    if isinstance(p, dict) and d.get("type") == "session_meta":
        return (str(p.get("id") or p.get("session_id") or ""),
                p.get("cwd") if isinstance(p.get("cwd"), str) else None,
                p.get("cli_version") if isinstance(p.get("cli_version"), str) else None, p)
    return "", None, None, {}


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    return _meta(path)[0]


def minar(path, cur, tramo, hasta_t=None, cola=False):
    offset = int(cur.get("offset") or 0)
    tam = os.path.getsize(M.ruta_larga(path))
    _sid, cwd, ver, meta = _meta(path)
    tramo.version, tramo.cwd = ver, cwd
    for k in ("originator", "source"):      # codex-tui / codex_exec · cli / exec
        tramo.senal(k, meta.get(k) if isinstance(meta.get(k), str) else None)
    mx = _Minero(tramo, modelo=cur.get("modelo"))
    nuevo = {"offset": offset}
    completo = True
    if tam > offset:
        nuevo["offset"], completo = M.recorrer(path, offset, mx.linea, tramo, hasta_t, cola)
    mx.fin(cur.get("total"), bool(cur.get("registros")))
    if mx.registros or cur.get("registros"):
        nuevo["registros"] = True
    if mx.total is not None:
        nuevo["total"] = mx.total
    if mx.modelo:
        nuevo["modelo"] = mx.modelo
    return {"cursor": nuevo, "completo": completo, "costo": None, "desde": offset, "hasta": nuevo["offset"]}


def al_dia(path, cur):
    return int(cur.get("offset") or 0) >= os.path.getsize(M.ruta_larga(path))


def _raiz():
    try:
        from engines import codex
        return codex._sessions_root()
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".codex", "sessions")


def raices():
    """$CODEX_HOME/sessions/AAAA/MM/DD/rollout-*.jsonl y las copias de cierre."""
    import paths
    return [(_raiz(), 3), (os.path.join(paths.state_dir(), "transcripts-backup"), 1)]


def es_fuente(nombre):
    return nombre.startswith("rollout-") and nombre.endswith(".jsonl")


def fuentes():
    """Rollouts de $CODEX_HOME/sessions y las copias de cierre en
    <estado>/transcripts-backup/<enc>/rollout-*.jsonl."""
    import paths
    out = []
    for b, _dirs, files in os.walk(_raiz()):
        for f in files:
            if f.startswith("rollout-") and f.endswith(".jsonl"):
                p = os.path.join(b, f)
                sid = sesion(p)
                if sid:
                    out.append((sid, p))
    respaldo = os.path.join(paths.state_dir(), "transcripts-backup")
    try:
        dirs = os.listdir(respaldo)
    except OSError:
        dirs = []
    for d in dirs:
        full = os.path.join(respaldo, d)
        try:
            files = os.listdir(full) if os.path.isdir(full) else ()
        except OSError:
            continue
        for f in files:
            if f.startswith("rollout-") and f.endswith(".jsonl"):
                p = os.path.join(full, f)
                sid = sesion(p)
                if sid:
                    out.append((sid, p))
    return out


def transcript_de_cierre(brain, payload):
    """Con el respaldo de transcripts apagado, close_payload no resuelve el
    rollout: se busca igual (cwd + mtime desde el arranque, sin ambigüedad)."""
    import session_continuity
    r = session_continuity.resolve_codex(brain, M.epoch(payload.get("started")) or 0)
    return r.get("transcript_path") or ""
