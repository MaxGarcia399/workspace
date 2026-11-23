"""WORKSPACE · control/codex.py — Codex por su app-server (`codex app-server`,
JSON-RPC por stdio, sin la cabecera "jsonrpc"), con el login del socio. Uso
personal: su doc dice que la autenticación del app-server «never permitted for
commercial or hosted services» (semáforo GRIS para uso propio, ROJO si se vende).

Hilo = conversación (thread/start o thread/resume), turno = turn/start; el
texto llega con item/agentMessage/delta, las herramientas como items
(commandExecution, fileChange, mcpToolCall…), las aprobaciones como pedidos
del servidor (item/*/requestApproval) y se corta con turn/interrupt.

Es otra conversación que la terminal, salvo que la terminal se cuelgue del
mismo app-server (`codex --remote`), que es para después."""
from control.base import Conector, ErrorControl, campo, corto, pregunta_nativa
from control.canal import CanalProceso
from control.jsonrpc import CERRADO, ErrorRPC, METODO_NO_EXISTE, Par

CLIENTE = {"name": "workspace", "title": "Workspace", "version": "control-1"}
#: Items que son herramientas (los demás —mensaje, razonamiento— no).
HERRAMIENTAS = {"commandExecution": "comando", "fileChange": "cambio de archivos",
                "mcpToolCall": "herramienta MCP", "webSearch": "búsqueda web"}
_DECISION = {"permitir": "accept", "permitir_siempre": "acceptForSession", "negar": "decline"}
_FIN = {"completed": "fin", "interrupted": "parado", "failed": "error"}


class Codex(Conector):
    motor = "codex"

    def __init__(self, cwd=None, cmd=None, env=None, aprobacion="on-request", grabar=None,
                 timeout=60, sandbox=None, config=None):
        super().__init__(cwd=cwd, grabar=grabar)
        self.cmd = list(cmd or ["codex", "app-server"])
        self._env = env
        self._aprobacion = aprobacion
        #: B05 (cacería 19-nov): el sandbox del nivel del agente (read-only | workspace-write), el mismo que su terminal
        #: (`-s`). Sin él, Codex usaba lo de su config global: preguntaba o no según la confianza del proyecto.
        self._sandbox = sandbox if sandbox in ("read-only", "workspace-write") else None
        #: cable-codex: el `config` del hilo (engines/codex.config_del_hilo): la carpeta «untrusted» solo en este hilo,
        #: para que el app-server no guarde su confianza en la config global del socio.
        self._config = config if isinstance(config, dict) and config else None
        self._timeout = timeout
        self._canal = None
        self._rpc = None
        self._turno_id = None

    def _abrir(self, sesion):
        try:
            self._canal = CanalProceso(self.cmd, cwd=self.cwd, env=self._entorno(self._env),
                                       grabar=self._grabar)
            self._registrar_hijo(sesion)
        except OSError as e:
            raise ErrorControl("no pude abrir %s: %s" % (" ".join(self.cmd), e))
        self._rpc = Par(self._canal, al_pedido=self._pedido, al_aviso=self._aviso,
                        al_cerrar=self._al_cerrar, cabecera=False)
        try:
            self._rpc.llamar("initialize", {"clientInfo": CLIENTE}, self._timeout)
            self._rpc.avisar("initialized", {})
            # la política (y el sandbox del nivel) van también al retomar: sin ellos vale lo de su config global (con
            # approval_policy="never" la página corría comandos sin preguntar; sin sandbox, el de la conversación vieja)
            politica = {"approvalPolicy": self._aprobacion}
            if self._sandbox:
                politica["sandbox"] = self._sandbox
            if self._config:
                politica["config"] = self._config
            if sesion:
                r = self._rpc.llamar("thread/resume", dict(politica, threadId=sesion), self._timeout)
            else:
                r = self._rpc.llamar("thread/start", dict(politica, cwd=self.cwd), self._timeout)
            tid = campo(campo(r, "thread", defecto={}), "id") or sesion
            if not tid:
                raise ErrorControl("codex no devolvió el id del hilo")
            self._perfil_confirmado(r)
        except (ErrorRPC, ErrorControl) as e:
            self._canal.cerrar(espera=1.0)
            if isinstance(e, ErrorControl):
                raise
            raise ErrorControl("codex: %s" % e.mensaje)
        try:                                     # % del plan, si lo da (no es obligatorio)
            rl = self._rpc.llamar("account/rateLimits/read", None, 10)
            self._poner_uso(fuente="codex", limites=campo(rl, "rateLimits", defecto=rl))
        except ErrorRPC:
            pass
        return tid

    def _perfil_confirmado(self, r):
        """Cierre de la auditoría (19-nov): si el `config` del hilo trae un perfil de permisos (arquitectura/secretos:
        el que niega leer lo prohibido en la página), su app-server dice cuál quedó en `activePermissionProfile`
        (esquema 0.169.0). Si es el nuestro, el bloqueo queda confirmado; si no (una regla administrada, otra
        versión), se avisa: la página lee entonces con los ajustes de antes."""
        esperado = str((self._config or {}).get("default_permissions") or "")
        if not esperado:
            return
        activo = campo(campo(r, "activePermissionProfile", defecto={}) or {}, "id", defecto="")
        if activo == esperado:
            self.bloqueo_secretos = ("su app-server confirmó en el hilo el perfil de permisos «%s» de Workspace "
                                     "(su sandbox niega leer llaves y secretos)" % esperado)
        else:
            self._emitir("error", mensaje="codex no aplicó el perfil de permisos de Workspace (quedó «%s»): por la "
                                          "página no tiene el bloqueo de llaves y secretos" % (activo or "ninguno"),
                         fatal=False)

    def _mandar(self, texto):
        self._turno_id = None

        def fin(r, error):
            if error is not None and error.codigo != CERRADO:
                self._emitir("error", mensaje="codex: %s" % error.mensaje, fatal=False)
                self._terminar("error")
            elif r:
                self._turno_id = self._turno_id or campo(campo(r, "turn", defecto={}), "id")
        self._rpc.llamar_luego("turn/start", {"threadId": self.sesion,
                                              "input": [{"type": "text", "text": texto}]}, fin)

    def _parar(self):
        self._rpc.llamar_luego("turn/interrupt", {"threadId": self.sesion,
                                                  "turnId": self._turno_id}, lambda r, e: None)

    def _cerrar(self):
        if self._canal:
            self._canal.cerrar()

    def _al_cerrar(self, motivo):
        e = self._canal.stderr() if self._canal else ""
        self._perdido("codex se cerró (%s)%s" % (motivo, ": " + e if e else ""))

    def _aviso(self, metodo, p):
        if campo(p, "threadId") not in (None, self.sesion):
            return
        if metodo == "turn/started":
            self._turno_id = campo(campo(p, "turn", defecto={}), "id") or self._turno_id
            self._con_delta = set()
        elif metodo == "item/agentMessage/delta":
            if p.get("delta"):
                mid = campo(p, "itemId", "id")
                self._con_delta = getattr(self, "_con_delta", set()) | {mid}
                # con su id: dos mensajes suyos no se pegan («opciones.Espero», B14)
                self._emitir("texto", texto=p["delta"], mensaje=mid)
        elif metodo == "item/completed" and (p.get("item") or {}).get("type") == "agentMessage":
            self._mensaje_entero(p.get("item") or {})
        elif metodo in ("item/started", "item/completed"):
            item = p.get("item") or {}
            nombre = HERRAMIENTAS.get(item.get("type"))
            if not nombre:
                return
            if metodo == "item/started":
                self._emitir("herramienta", id=str(item.get("id")), nombre=nombre, fase="empieza",
                             detalle=corto(campo(item, "command", "changes", "tool", "query")))
            else:
                mal = item.get("status") in ("failed", "declined")
                self._emitir("herramienta", id=str(item.get("id")), nombre=nombre,
                             fase="falla" if mal else "termina",
                             detalle=corto(campo(item, "aggregatedOutput", "status")))
        elif metodo == "turn/completed":
            turno = p.get("turn") or {}
            motivo = _FIN.get(turno.get("status"), "fin")
            if motivo == "error":
                err = turno.get("error") or {}
                self._emitir("error", mensaje="codex: %s" % (campo(err, "message") or "el turno falló"),
                             fatal=False)
            self._terminar(motivo)
        elif metodo == "error":
            err = p.get("error") or p
            self._emitir("error", mensaje="codex: %s" % (campo(err, "message") or corto(err)),
                         fatal=False)
        elif metodo == "account/rateLimits/updated":
            self._poner_uso(fuente="codex", limites=campo(p, "rateLimits", defecto=p))
        elif metodo == "thread/tokenUsage/updated":
            self._poner_uso(fuente="codex", tokens=campo(p, "tokenUsage", defecto=p))

    def _mensaje_entero(self, item):
        """B14 (cacería 19-nov): un agentMessage que llega entero en item/completed, sin deltas (su pregunta nativa:
        id «call_…», delivery «async», phase final_answer, questions [{title, options}]). Su texto y su pregunta se
        perdían: el texto solo salía por delta y la pregunta no tenía camino. Su texto, si no salió por delta; su
        primera pregunta, como pregunta de la página (control.base: «pregunta»)."""
        mid = item.get("id")
        texto = item.get("text")
        if isinstance(texto, str) and texto.strip() and mid not in getattr(self, "_con_delta", set()):
            self._emitir("texto", texto=texto, mensaje=mid)
        for q in item.get("questions") or []:
            titulo, opciones = pregunta_nativa(q)
            if titulo:
                self._emitir("pregunta", id=str(mid or "codex"), texto=titulo, opciones=opciones)
                break

    def _pedido(self, metodo, p):
        if metodo == "mcpServer/elicitation/request":
            return self._elicitacion(p)
        if metodo not in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval"):
            raise ErrorRPC(METODO_NO_EXISTE, "Method not found: %s" % metodo)
        nombre = "comando" if "commandExecution" in metodo else "cambio de archivos"
        d = self._esperar_permiso(campo(p, "itemId", defecto="aprobacion"), nombre,
                                  campo(p, "command", "reason", "changes"))
        return {"decision": _DECISION.get(d, "cancel")}

    def _elicitacion(self, p):
        """cable-codex · `mcpServer/elicitation/request` (esquema del app-server 0.169.0): lo que un servidor MCP le pide
        al socio. La auditoría real del 19-nov vio «user rejected MCP tool call» en la página: esta petición caía en
        «Method not found» y Codex lo tomaba como un rechazo. Ahora:
          · la del servidor `workspace` (el núcleo, que la página le declara por -c y cuyas herramientas están
            preaprobadas por diseño, como en ACP con control.propias; en la página nunca pregunta por formulario:
            nucleo_mcp._con_formulario) → se acepta;
          · la de otro servidor → la decide el socio, como un permiso (su tarjeta en la página);
          · una de enlace (mode «url») o una que pide un dato que nadie dio (un campo obligatorio sin valor por
            defecto) → se rechaza: no se inventa la respuesta. Queda en el tráfico grabado (`grabar`)."""
        servidor = str(campo(p, "serverName", defecto="") or "")
        mensaje = str(campo(p, "message", defecto="") or "")
        contenido = None if p.get("mode") == "url" else contenido_por_defecto(p.get("requestedSchema"))
        if contenido is None:
            return {"action": "decline"}
        try:
            from control import propias
            if servidor == SERVIDOR_NUCLEO and (not self.en_escritorio() or propias.de_nucleo_libre_codex(mensaje)):
                return {"action": "accept", "content": contenido}
            if propias.de_manos(servidor, mensaje):     # modo escritorio: las manos de ver y señalar, libres
                return {"action": "accept", "content": contenido}
        except Exception:
            if servidor == SERVIDOR_NUCLEO and not self.en_escritorio():
                return {"action": "accept", "content": contenido}
        d = self._esperar_permiso(str(campo(p, "elicitationId", defecto="") or "mcp-" + servidor), "herramienta MCP",
                                  corto("%s: %s" % (servidor, mensaje)))
        return {"action": "accept", "content": contenido} if d in ("permitir", "permitir_siempre") \
            else {"action": "decline"}


#: El servidor MCP del núcleo (mcp_nucleo.json · servidor), el que la página le declara a Codex por -c.
SERVIDOR_NUCLEO = "workspace"


def contenido_por_defecto(esquema):
    """La respuesta de un formulario de elicitación con SOLO lo que su esquema trae por defecto: {} si no pide nada;
    None si un campo obligatorio no tiene valor por defecto (no se inventa)."""
    if not isinstance(esquema, dict):
        return {}
    props = esquema.get("properties") if isinstance(esquema.get("properties"), dict) else {}
    requeridos = set(esquema.get("required") or ())
    out = {}
    for k, v in props.items():
        if isinstance(v, dict) and "default" in v:
            out[k] = v["default"]
        elif k in requeridos:
            return None
    return out


def listar_hooks(cwd, cmd=None, env=None, timeout=20):
    """Los hooks que Codex cargaría en `cwd`, por `hooks/list` de su app-server (oficial: está en el esquema que da
    `codex app-server generate-json-schema`, 0.169.0). Cada uno trae `trustStatus` (untrusted | trusted | modified |
    managed), `source` (project, user…), `sourcePath`, `eventName`, `enabled` y `key`.

    VERIFICADO en caja negra (18-nov, HOME y CODEX_HOME temporales, sin login): sin turno ni hilo, en unos 0,15 s y sin
    escribir en config.toml. Los del proyecto salen «untrusted» hasta que se confían, «trusted» con el trusted_hash
    que /hooks guarda (su `currentHash`) y «modified» si después cambia su comando o su timeout. Con el proyecto sin
    confianza, Codex no carga los del proyecto: no salen. → lista; ErrorControl si no abre o no lo sabe."""
    from control import entorno
    try:
        canal = CanalProceso(list(cmd or ["codex", "app-server"]), cwd=cwd,
                             env=env if env is not None else entorno.con_basicas(entorno.limpio()))
    except OSError as e:
        raise ErrorControl("no pude abrir codex app-server: %s" % e)
    rpc = Par(canal, cabecera=False)
    try:
        rpc.llamar("initialize", {"clientInfo": CLIENTE}, timeout)
        rpc.avisar("initialized", {})
        r = rpc.llamar("hooks/list", {"cwds": [cwd]}, timeout)
    except ErrorRPC as e:
        raise ErrorControl("codex: %s" % e.mensaje)
    finally:
        canal.cerrar(espera=1.0)
    return [h for ent in campo(r, "data", defecto=[]) or [] for h in campo(ent, "hooks", defecto=[]) or []
            if isinstance(h, dict)]
