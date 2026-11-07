"""WORKSPACE · metricas_motores.claude_code — parser de métricas de Claude Code.

Transcript: `~/.claude/projects/<enc>/<sid>.jsonl` (solo crece) y los de sus
subagentes en `<sid>/subagents/*.jsonl`. Cursor = offset de bytes del
principal + offset por archivo de subagente.

Formato VERIFICADO (solo claves, sin contenido; Claude Code 2.x, 2026-10):
  · assistant: una línea POR BLOQUE de contenido (thinking/text/tool_use), con
    el MISMO message.id y la MISMA message.usage repetida (505 de 743 ids
    aparecen varias veces) → el uso se cuenta UNA vez por message.id.
    usage{input_tokens, output_tokens, cache_read_input_tokens,
    cache_creation_input_tokens, cache_creation.ephemeral_5m/1h_input_tokens,
    output_tokens_details.thinking_tokens}; message.model ("<synthetic>" = aviso
    de error, sin uso real); `version`; `isSidechain` (subagente en línea, en
    versiones viejas).
  · user: tool_result{tool_use_id, is_error}; toolUseResult.interrupted;
    texto «[Request interrupted by user…]» = interrupción; origin.kind ==
    "human" en lo tecleado (versiones nuevas); isMeta = lo pone el sistema.
  · system/turn_duration.durationMs → tiempo activo.
  · cost-state{totalCostUSD, startTime}: costo ACUMULADO del linaje (startTime
    = arranque del primer proceso). Se escribe antes de SessionEnd (el respaldo
    de cierre ya lo trae) y SE HEREDA: una sesión que continúa a otra arranca
    con el acumulado del padre (verificado: un hijo reportó 2.70 sobre un
    padre que iba en 0.55 al continuar). Costo del tramo = acumulado al final
    − acumulado al empezar, y el punto de partida solo se toma de algo
    seguro (ver _base_costo); si no lo hay → costo null con el motivo en
    `costo_detalle`. Jamás el acumulado heredado.
  · continued-in{continuedInSessionId}: lo escribe el PADRE al continuar en
    otra sesión; el hijo COPIA el historial del padre (mismos uuid,
    message.id, timestamp) → las huellas lo descartan, y el padre deja
    anotados su acumulado en ese punto y su pestaña para el hijo.
  · custom-title{customTitle}: Workspace crea cada sesión con
    `claude --name <pestaña>` → pista de pestaña para la historia (solo se usa
    si coincide con una pestaña que existe; el texto no se guarda).
"""
import os
import re

import metricas as M

MOTOR = "claude-code"
VERSION = "claude-code/4"     # /4: del shell, solo cuentan las skills que se LEEN
#: Programas que LEEN un archivo. Desde el shell, un SKILL.md solo cuenta como
#: skill usada si uno de estos lo lee (igual que en Codex). Un prompt para otro
#: agente, un script o una escritura que solo MENCIONA la ruta no es usarla.
_LECTORES = ("cat", "head", "tail", "sed", "less", "more", "bat", "nl")
_SEPARADORES = re.compile(r"\|\||&&|[|;\n]")
#: Versiones exactas verificadas con golden (tests/fixtures/metricas/claude-code/<v>/).
VERIFIED_VERSIONS = ("2.1.310", "2.1.311")
#: Claude Code publica casi a diario: una versión no listada se vigila por
#: canarios (`metricas salud`) en vez de marcarse «no verificada».
CANARIOS = True
COBERTURA = {
    "motor_version": ("si", ""),
    "modo_senales": ("si", "entrypoint de cada línea (cli | sdk-cli…)"),
    "duracion_activa_s": ("parcial", "system/turn_duration solo existe en sesiones "
                                     "interactivas; headless no lo escribe"),
    "tiempo_humano_est_s": ("si", ""),
    "modelos": ("si", ""),
    "modelo_pedido": ("si", "assistant.requestedModel"),
    "esfuerzo": ("parcial", "assistant.effort: solo en versiones que lo escriben"),
    "permisos": ("si", "permission-mode / user.permissionMode"),
    "tokens_motor": ("parcial", "cost-state.modelUsage: acumulado del linaje, con el "
                                "mismo punto de partida que el costo"),
    "costo_usd": ("parcial", "cost-state es acumulado del linaje: null al continuar una "
                             "sesión sin punto de partida seguro"),
    "facturacion": ("no", "el transcript no dice si la cuenta es suscripción o API"),
    "cuota": ("no", "Claude Code no escribe la cuota en el transcript"),
    "herramientas.llamadas": ("si", ""),
    "herramientas.errores": ("si", "tool_result.is_error, sin los comandos que solo "
                                   "terminaron con código ≠ 0"),
    "herramientas.comandos_no_cero": ("parcial", "Bash con is_error y salida «Exit "
                                                 "code N»; otras herramientas no"),
    "respuestas_error": ("si", "assistant.isApiErrorMessage + error"),
    "interrupciones": ("si", ""),
    "mensajes_usuario": ("si", ""),
    "skills": ("si", ""),
    "escritos.archivos": ("parcial", "Write/Edit/MultiEdit/NotebookEdit; lo escrito por "
                                     "Bash no se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("si", ""),
    "turnos": ("si", ""),
}
CONTINUACION = {"retomar": "mismo_archivo", "continuar": "copia_historial"}
#: la fuente solo crece y cada fila guarda su corte en bytes (captura.hasta):
#: `reconstruir` puede volver a medirla cortándola igual
RECONSTRUIBLE = True

#: Tipos de línea que el parser conoce (cuente algo o no). Otro tipo se
#: cuenta en captura.desconocidas por su nombre.
_TIPOS = frozenset((
    "assistant", "user", "system", "cost-state", "continued-in", "custom-title",
    "attachment", "api-request", "api-request-blob", "api-request-shape",
    "last-prompt", "agent-name", "mode", "permission-mode", "atis-latch",
    "file-history-snapshot", "file-history-delta", "queue-operation", "ai-title",
    "summary", "progress", "tag",
    "tools-used"))     # 2.1.311: qué herramientas había (se reconoce, no se guarda)

_ESCRITURA = ("Write", "Edit", "MultiEdit", "NotebookEdit")
#: Mensajes del usuario que empiezan con una etiqueta y SÍ son del usuario
#: (comando /x tecleado, `!` de bash, `#` de memoria). El resto de etiquetas
#: (salidas de comandos, avisos de tareas, recordatorios) los pone el sistema.
_ETIQUETAS_USUARIO = ("command-name", "command-message", "bash-input",
                      "user-memory-input")
_INTERRUPCION = "[Request interrupted by user"
#: origin.kind / turnOrigin → origen del turno (lo que no es humano tampoco
#: cuenta como mensaje del usuario)
_ORIGEN = {"human": "humano", "task-notification": "notificacion",
           "task_notification": "notificacion", "peer": "automatico",
           "scheduled": "automatico", "sdk": "automatico", "coordinator": "automatico"}
_CAMPOS_USO = (("entrada", "inputTokens"), ("salida", "outputTokens"),
               ("cache_lectura", "cacheReadInputTokens"),
               ("cache_escritura", "cacheCreationInputTokens"),
               ("razonamiento", "thinkingTokens"))
_ETIQUETA_RE = re.compile(r"<([a-z][a-z0-9-]*)")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _clave(prefijo, valor):
    return "%s:%s" % (prefijo, valor) if valor else ""


#: herramientas sin resultado que pasan al tramo siguiente (cursor), como tope
_TOPE_PENDIENTES = 50



def _rutas_leidas(comando):
    """Rutas que un comando de shell LEE con un lector (cat/head/sed…), por
    tramo de la tubería. Sin rutas con $VARIABLE ni `…` (no se pueden
    resolver: son de scripts) ni lo que va tras > (se escribe, no se lee)."""
    if not isinstance(comando, str) or "skill.md" not in comando.lower():
        return []
    import shlex
    out = []
    for tramo in _SEPARADORES.split(comando):
        try:
            pal = shlex.split(tramo)
        except ValueError:
            pal = tramo.split()
        if not pal or os.path.basename(pal[0]).lower() not in _LECTORES:
            continue
        saltar = False
        for x in pal[1:]:
            if saltar:
                saltar = False
                continue
            if x in (">", ">>", "1>", "2>"):
                saltar = True
                continue
            if x.startswith((">", "-")) or "$" in x or "`" in x:
                continue
            out.append(x)
    return out

class _Minero(object):
    def __init__(self, tramo, costo_previo=None, cur=None):
        cur = cur or {}
        self.t = tramo
        self.principal = True
        # lo que quedó abierto en el tramo anterior (el cierre cayó entre una
        # herramienta y su resultado): sigue aquí, para que N cortes den lo
        # mismo que una pasada
        self.escrituras = dict(cur.get("pend_escr") or {})   # tool_use_id → ruta
        self.int_pendiente = False   # toolUseResult.interrupted sin su aviso
        #: la interrupción pendiente ya se contó al cerrar el tramo anterior:
        #: si su aviso llega ahora, no se cuenta otra vez
        self.int_contada = bool(cur.get("int_contada"))
        self.costo_fin = None        # último acumulado NUEVO del tramo
        self.costo_linaje = None
        self.costo_copia = None      # último acumulado COPIADO del padre
        self.costo_corriente = costo_previo   # acumulado conocido a esta altura
        # tokens del MOTOR (cost-state.modelUsage), con la misma regla de base
        self.uso_fin = None
        self.uso_copia = None
        self.uso_corriente = None
        self.herr = dict(cur.get("pend_herr") or {})   # tool_use_id → nombre
        self.encolado = False        # el próximo pedido esperó en la cola
        self.encolado_t = None       # hora del último enqueue sin dequeue
        self.ausente = False         # away_summary desde el último turno

    def _cerrar_interrupcion(self):
        self.int_contada = False
        if self.int_pendiente:
            self.t.interrupciones += 1
            self.int_pendiente = False

    def linea(self, d):
        t = d.get("type")
        if t not in _TIPOS:
            self.t.desconocer(t)
            return
        self.t.reconocer()
        v = d.get("version")
        if isinstance(v, str) and v:
            self.t.version = v[:40]
        if self.principal and isinstance(d.get("entrypoint"), str):
            self.t.senal("entrypoint", d["entrypoint"])
        if self.t.cwd is None and isinstance(d.get("cwd"), str) and d["cwd"]:
            self.t.cwd = d["cwd"]
        if t == "assistant":
            self._asistente(d)
        elif t == "user":
            self._usuario(d)
        elif t == "system":
            sub = d.get("subtype")
            if sub == "turn_duration" and self.principal and not d.get("isSidechain"):
                ts = M.epoch(d.get("timestamp"))
                if self.t.nuevo(_clave("u", d.get("uuid")), ts):
                    self.t.activa(d.get("durationMs"))
                    self.t.ts(ts)
            elif sub == "compact_boundary" and self.principal:
                if self.t.ver(_clave("u", d.get("uuid")), M.epoch(d.get("timestamp")),
                              actividad=False) is None:
                    self.t.compactacion()
            elif sub == "away_summary" and self.principal:
                self.ausente = True
        elif t == "permission-mode" and self.principal:
            if isinstance(d.get("permissionMode"), str):
                self.t.permisos = d["permissionMode"]
        elif t == "queue-operation" and self.principal:
            # un pedido que ESPERÓ en la cola (se tecleó con el agente ocupado):
            # enqueue … dequeue más de 1 s después. enqueue+dequeue al instante
            # (headless, o el agente libre) es un pedido normal; remove = se
            # absorbió dentro del turno en curso
            op, ts = d.get("operation"), M.epoch(d.get("timestamp"))
            if op == "enqueue":
                self.encolado_t = ts
            elif op == "dequeue":
                self.encolado = bool(self.encolado_t is not None and ts is not None
                                     and ts - self.encolado_t > 1.0)
                self.encolado_t = None
            elif op == "remove":
                self.encolado, self.encolado_t = False, None
        elif t == "cost-state" and self.principal:
            self._costo(d)
        elif t == "continued-in" and self.principal:
            hijo = d.get("continuedInSessionId")
            if isinstance(hijo, str) and hijo:
                self.t.hijos.append(hijo)
                if self.costo_corriente is not None:
                    self.t.anotar("costo_al_continuar", hijo, self.costo_corriente,
                                  solo_si_falta=True)
                if self.uso_corriente is not None:
                    self.t.anotar("uso_al_continuar", hijo, self.uso_corriente,
                                  solo_si_falta=True)
        elif t == "custom-title" and self.principal:
            if isinstance(d.get("customTitle"), str) and d["customTitle"].strip():
                self.t.pista_pestana = d["customTitle"][:200]

    def _asistente(self, d):
        m = d.get("message")
        if not isinstance(m, dict):
            self.t.ignoradas += 1
            return
        ts = M.epoch(d.get("timestamp"))
        sub = (not self.principal) or bool(d.get("isSidechain"))
        mid = m.get("id") or d.get("requestId") or d.get("uuid")
        u = m.get("usage")
        modelo = m.get("model")
        if not sub:
            self.t.respuesta(ts)
            if isinstance(d.get("requestedModel"), str) and d["requestedModel"]:
                self.t.modelo_pedido = d["requestedModel"]
            esf = d.get("effort") or d.get("perTurnEffort")
            if isinstance(esf, str) and esf:
                self.t.esfuerzo = esf
        if d.get("isApiErrorMessage") is True or m.get("stop_reason") == "refusal":
            # respuesta de error del PROVEEDOR (no de una herramienta)
            if self.t.nuevo(_clave("e", d.get("uuid")), ts):
                self.t.ts(ts)
                clase = "bloqueado" if m.get("stop_reason") == "refusal" else d.get("error")
                if M.clase_error(clase) or clase in M.CLASES_ERROR:
                    self.t.respuesta_error(clase)
                else:
                    self.t.avisos.add("error_del_proveedor_sin_clase")
        if isinstance(u, dict) and mid and modelo != "<synthetic>":
            visto = self.t.ver(_clave("m", mid), ts)
            if visto == "propia":
                # otro bloque del MISMO mensaje (llega después): no se cuenta
                # otra vez, pero la sesión sí duró hasta ahí
                self.t.ts(ts)
            if visto is None:
                self._cerrar_interrupcion()
                self.t.ts(ts)
                cc = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
                det = (u.get("output_tokens_details")
                       if isinstance(u.get("output_tokens_details"), dict) else {})
                self.t.uso(modelo, {
                    "entrada": M.entero(u.get("input_tokens")),
                    "salida": M.entero(u.get("output_tokens")),
                    "cache_lectura": M.entero(u.get("cache_read_input_tokens")),
                    "cache_escritura": M.entero(u.get("cache_creation_input_tokens")),
                    "cache_escritura_1h": M.entero(cc.get("ephemeral_1h_input_tokens")),
                    "razonamiento": M.entero(det.get("thinking_tokens")),
                }, sub=sub)
        content = m.get("content")
        if not isinstance(content, list):
            return
        for b in content:
            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                continue
            tid = b.get("id")
            if not self.t.nuevo(_clave("t", tid), ts):
                continue
            self.t.ts(ts)
            self.t.llamadas += 1
            if tid:
                self.herr[tid] = b.get("name")
            self._herramienta(b.get("name"), b.get("input"), tid)

    def _herramienta(self, nombre, inp, tid):
        inp = inp if isinstance(inp, dict) else {}
        if nombre in _ESCRITURA:
            p = inp.get("file_path") or inp.get("notebook_path")
            if isinstance(p, str) and p and tid:
                self.escrituras[tid] = p
        elif nombre == "Read":
            self.t.skills_de_texto(inp.get("file_path"))
        elif nombre == "Bash":
            for ruta in _rutas_leidas(inp.get("command")):
                self.t.skills_de_texto(ruta)
        elif nombre == "Skill":
            self.t.skill(inp.get("skill") or inp.get("name"))

    def _usuario(self, d):
        m = d.get("message")
        if not isinstance(m, dict):
            self.t.ignoradas += 1
            return
        ts = M.epoch(d.get("timestamp"))
        c = m.get("content")
        principal = self.principal and not d.get("isSidechain")
        if isinstance(c, list):
            for b in c:
                if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                    continue
                tid = b.get("tool_use_id")
                if not self.t.nuevo(_clave("r", tid), ts):
                    continue
                self.t.ts(ts)
                if principal:
                    self.t.respuesta(ts)
                err = b.get("is_error") is True
                if err and self.herr.get(tid) == "Bash" and _salida_no_cero(b.get("content")):
                    # un comando que terminó con código ≠ 0 (grep sin
                    # coincidencias…) no es un error de la herramienta
                    self.t.comandos_no_cero += 1
                elif err:
                    self.t.errores += 1
                ruta = self.escrituras.pop(tid, None)
                if ruta and not err:
                    self.t.escrito(ruta)
                self.herr.pop(tid, None)
                tur = d.get("toolUseResult")
                if principal and isinstance(tur, dict) and tur.get("interrupted") is True:
                    self.int_pendiente = True
        if not principal or d.get("isMeta"):
            return
        texto, imagen = _texto_usuario(c)
        if texto is None and not imagen:
            return
        uid = d.get("uuid")
        if (texto or "").lstrip().startswith(_INTERRUPCION):
            if self.t.nuevo(_clave("u", uid), ts):
                self.int_pendiente = False
                if self.int_contada:
                    self.int_contada = False     # ya contada al cortar el tramo anterior
                else:
                    self.t.interrupciones += 1
                self.t.ts(ts)
            return
        if isinstance(d.get("permissionMode"), str) and d["permissionMode"]:
            self.t.permisos = d["permissionMode"]
        if _es_mensaje_real(d, texto or "", imagen):
            if self.t.nuevo(_clave("u", uid), ts):
                self._cerrar_interrupcion()
                self.t.mensajes += 1
                self.t.ts(ts)
                self.t.turno(ts, texto, "cola" if self.encolado else "humano",
                             ausente=self.ausente)
                self.encolado = self.ausente = False
            return
        origen = _ORIGEN.get(_origen_de(d))
        if origen and origen != "humano" and self.t.nuevo(_clave("u", uid), ts):
            # pedido que no tecleó el usuario (aviso de una tarea, otro agente,
            # programado): es un turno, pero no un mensaje del usuario
            self._cerrar_interrupcion()
            self.t.ts(ts)
            self.t.turno(ts, texto, origen)

    def _costo(self, d):
        v = M.numero(d.get("totalCostUSD"))
        if v is None:
            self.t.ignoradas += 1
            return
        uso = _uso_motor(d.get("modelUsage"))
        clave = "c:%s:%s:%s" % (d.get("startTime"), v, d.get("totalDuration"))
        # un acumulado no es actividad por sí solo (retomar y salir sin hacer
        # nada lo reescribe igual): cuenta solo si el costo del tramo sube
        tipo = self.t.ver(clave, M.epoch(d.get("startTime")), actividad=False)
        if tipo == "copia":
            self.costo_copia = v
            self.uso_copia = uso
        elif tipo is None:
            self.costo_fin = v
            self.uso_fin = uso
            self.costo_linaje = d.get("startTime")
        self.costo_corriente = v
        self.uso_corriente = uso

    def fin(self, nuevo):
        """Cierra el tramo. Una interrupción sin su aviso se cuenta YA (puede
        no llegar nunca) y queda marcada en el cursor; las herramientas sin
        resultado pasan al tramo siguiente. Las claves se escriben SIEMPRE
        (None/False al quedar vacías): el cursor se actualiza con update()."""
        if self.int_pendiente:
            self.t.interrupciones += 1
            self.int_pendiente = False
            self.int_contada = True
        nuevo["int_contada"] = self.int_contada or None
        for clave, tabla in (("pend_escr", self.escrituras), ("pend_herr", self.herr)):
            nuevo[clave] = dict(list(tabla.items())[-_TOPE_PENDIENTES:]) or None


def _salida_no_cero(content):
    """¿El resultado de Bash dice «Exit code N»? (solo para clasificar)."""
    if isinstance(content, list):
        content = next((b.get("text") for b in content
                        if isinstance(b, dict) and isinstance(b.get("text"), str)), "")
    return isinstance(content, str) and content.lstrip().startswith("Exit code ")


def _origen_de(d):
    o = d.get("origin")
    if isinstance(o, dict) and isinstance(o.get("kind"), str):
        return o["kind"]
    return d.get("turnOrigin") if isinstance(d.get("turnOrigin"), str) else None


def _uso_motor(mu):
    """cost-state.modelUsage → {modelo: campos neutrales} (acumulado)."""
    if not isinstance(mu, dict):
        return None
    out = {}
    for modelo, u in mu.items():
        if isinstance(u, dict):
            out[M.nombre_modelo(modelo) or "desconocido"] = {
                k: M.entero(u.get(src)) for k, src in _CAMPOS_USO}
    return out or None


def _resta_uso(fin, base):
    """fin − base por modelo y campo; None si algo retrocede (no hay base)."""
    out = {}
    for modelo, u in fin.items():
        b = (base or {}).get(modelo) or {}
        d = {}
        for k, v in u.items():
            if v is None:
                d[k] = None
                continue
            bv = b.get(k) or 0
            if v < bv:
                return None
            d[k] = v - bv
        if any(d.values()):
            out[modelo] = dict(d, cache_escritura_1h=None)
    return out


def _texto_usuario(c):
    """(texto del primer bloque de texto | None, ¿trae imagen?). Solo para
    CLASIFICAR la línea: el texto jamás se guarda."""
    if isinstance(c, str):
        return c, False
    if not isinstance(c, list):
        return None, False
    texto, imagen = None, False
    for b in c:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_result":
            return None, False                 # resultado de herramienta, no mensaje
        if b.get("type") == "text" and texto is None and isinstance(b.get("text"), str):
            texto = b["text"]
        elif b.get("type") == "image":
            imagen = True
    return texto, imagen


def _es_mensaje_real(d, texto, imagen):
    """¿Lo escribió el usuario? Versiones nuevas: origin.kind == "human". Las
    viejas: texto sin etiqueta del sistema (o una etiqueta de comando que el
    usuario tecleó)."""
    o = d.get("origin")
    if isinstance(o, dict) and o.get("kind"):
        return o.get("kind") == "human"
    t = texto.lstrip()
    if t.startswith("<"):
        m = _ETIQUETA_RE.match(t)
        return bool(m) and m.group(1) in _ETIQUETAS_USUARIO
    return bool(t) or imagen


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem if _UUID_RE.match(stem) else stem or ""


def _base_costo(cur, mc, tramo):
    """(acumulado de partida | None, motivo). Solo fuentes seguras, en orden:
    el tramo anterior de esta misma sesión, un acumulado del padre copiado en
    este archivo, o el punto de continuación que dejó anotado el padre. Sin
    nada de eso, una sesión que NO continúa a otra parte de cero; si continúa
    (trae copias del padre, o su linaje ya lo reportó otra sesión) → None."""
    if M.numero(cur.get("costo_acum")) is not None:
        return float(cur["costo_acum"]), "tramo_anterior"
    if mc.costo_copia is not None:
        return mc.costo_copia, "copia_del_padre"
    base = tramo.leer("costo_al_continuar", tramo.sid)
    if M.numero(base) is not None:
        return float(base), "punto_de_continuacion"
    dueno = tramo.leer("linajes", str(mc.costo_linaje))
    if tramo.copias or (dueno and dueno != tramo.sid):
        return None, "continuacion_sin_punto_de_partida"
    return 0.0, "inicio_de_sesion"


def minar(path, cur, tramo, hasta_t=None, cola=False):
    offset = int(cur.get("offset") or 0)
    tam = os.path.getsize(M.ruta_larga(path))
    nuevo = {"offset": offset}
    completo = True
    mc = _Minero(tramo, costo_previo=M.numero(cur.get("costo_acum")), cur=cur)
    if tam > offset:
        offset2, completo = M.recorrer(path, offset, mc.linea, tramo, hasta_t, cola)
        nuevo["offset"] = offset2
    # subagentes: después del principal y con lo que quede de tiempo. Lo que
    # no alcance queda en su cursor y se lee en el próximo tramo AUNQUE el
    # principal ya no crezca (si no, se perdía: revisión 2026-10-26)
    subs = dict(cur.get("sub") or {})
    pendientes = _subagentes_pendientes(path, subs)
    tramo.cerrar_turno()      # lo de los subagentes no es de un turno del principal
    if completo and pendientes:
        mc.principal = False
        for f, p in pendientes:
            o = int(subs.get(f) or 0)
            try:
                antes = tramo.nuevos
                o2, ok = M.recorrer(p, o, mc.linea, tramo, hasta_t, cola)
            except OSError:
                tramo.ignoradas += 1
                continue
            subs[f] = o2
            if tramo.nuevos > antes:
                tramo.sub_archivos.add(f)
            if not ok:
                completo = False
                break
        mc.principal = True
    if subs:
        nuevo["sub"] = subs
    mc.fin(nuevo)
    costo = None
    if mc.costo_fin is not None:
        base, motivo = _base_costo(cur, mc, tramo)
        if tramo.excluidas:
            # hubo actividad con las métricas apagadas: un acumulado no se
            # puede partir por hora → sin costo en este tramo
            base, motivo = None, "periodo_apagado"
        usd = None
        if base is not None and mc.costo_fin >= base:
            usd = round(mc.costo_fin - base, 6)
        elif base is not None:
            motivo = "acumulado_menor_que_el_previo"
        if usd is None:
            tramo.avisos.add("costo_sin_punto_de_partida")
        elif usd > 0:
            tramo.nuevos += 1               # el costo que sube sí es actividad
        costo = (usd, "claude-code:cost-state",
                 {"motivo": motivo,
                  "acumulado_inicio": round(base, 6) if base is not None else None,
                  "acumulado_fin": round(mc.costo_fin, 6), "linaje": mc.costo_linaje})
        nuevo["costo_acum"] = mc.costo_fin
        if mc.uso_fin is not None:
            nuevo["uso_acum"] = mc.uso_fin
            base_uso = {"tramo_anterior": cur.get("uso_acum"),
                        "copia_del_padre": mc.uso_copia,
                        "punto_de_continuacion": tramo.leer("uso_al_continuar", tramo.sid),
                        "inicio_de_sesion": {}}.get(motivo)
            if base_uso is not None and usd is not None:
                tramo.tokens_motor = _resta_uso(mc.uso_fin, base_uso)
        if mc.costo_linaje is not None:
            tramo.anotar("linajes", str(mc.costo_linaje), tramo.sid, solo_si_falta=True)
    return {"cursor": nuevo, "completo": completo, "costo": costo, "desde": offset, "hasta": nuevo["offset"]}


def _subagentes_pendientes(path, subs):
    """[(archivo, ruta)] de subagentes con bytes sin medir."""
    d_sub = os.path.join(os.path.splitext(path)[0], "subagents")
    out = []
    try:
        nombres = sorted(os.listdir(d_sub))
    except OSError:
        return out
    for f in nombres:
        if not f.endswith(".jsonl"):
            continue
        p = os.path.join(d_sub, f)
        try:
            if os.path.getsize(M.ruta_larga(p)) > int(subs.get(f) or 0):
                out.append((f, p))
        except OSError:
            continue
    return out


def al_dia(path, cur):
    return (int(cur.get("offset") or 0) >= os.path.getsize(M.ruta_larga(path))
            and not _subagentes_pendientes(path, dict(cur.get("sub") or {})))


def raices():
    """[(carpeta, profundidad)] donde viven las fuentes (el núcleo las indexa
    con caché por mtime de carpeta): <raíz>/<enc>/<uuid>.jsonl."""
    import paths
    return [(os.path.join(os.path.expanduser("~"), ".claude", "projects"), 1),
            (os.path.join(paths.state_dir(), "transcripts-backup"), 1)]


def es_fuente(nombre):
    return nombre.endswith(".jsonl") and bool(_UUID_RE.match(nombre[:-6]))


def fuentes():
    """Sesiones de ~/.claude/projects/<enc>/ y de su respaldo de cierre
    (<estado>/transcripts-backup/<enc>/): solo archivos <uuid>.jsonl."""
    import paths
    out = []
    for base in (os.path.join(os.path.expanduser("~"), ".claude", "projects"),
                 os.path.join(paths.state_dir(), "transcripts-backup")):
        try:
            dirs = os.listdir(base)
        except OSError:
            continue
        for d in dirs:
            full = os.path.join(base, d)
            try:
                files = os.listdir(full) if os.path.isdir(full) else ()
            except OSError:
                continue
            for f in files:
                if f.endswith(".jsonl") and _UUID_RE.match(f[:-6]):
                    out.append((f[:-6], os.path.join(full, f)))
    return out
