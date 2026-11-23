"""WORKSPACE · control/acp.py — cliente ACP genérico (Agent Client Protocol
v1, JSON-RPC 2.0 por stdio): el motor oficial corre como subproceso SOLO
mientras el chat de la página está abierto (D5-a), con el login del socio.

Flujo: initialize → session/new (o session/load para retomar) →
session/prompt (responde al final del turno, con stopReason) mientras llegan
avisos session/update; el motor pide permisos con session/request_permission
y el cliente corta con la notificación session/cancel.

El cliente NO anuncia fs ni terminal (clientCapabilities en falso): el motor
usa sus propias herramientas y pide permiso por ACP.

Es otra conversación, no la de la terminal (ACP abre su propio proceso)."""
import itertools
import time

from control.base import Conector, DECISIONES, ErrorControl, archivo_de, campo, corto, que_permiso
from control.canal import CanalProceso
from control.jsonrpc import CERRADO, ErrorRPC, METODO_NO_EXISTE, Par

VERSION_ACP = 1
CLIENTE = {"name": "workspace", "title": "Workspace", "version": "control-1"}
#: Error de ACP «hace falta iniciar sesión».
AUTH_REQUERIDA = -32000

#: El comando oficial de cada motor (lanzador; nada de su config se toca).
FICHAS = {
    "copilot": {"cmd": ["copilot", "--acp"]},
    "cursor": {"cmd": ["cursor-agent", "acp"], "auth": "cursor_login"},
    "kiro": {"cmd": ["kiro-cli", "acp", "--agent-engine", "v3"]},
    "antigravity": {"cmd": ["agy", "acp"],
                    "aviso": "Antigravity con plan personal dentro de otra app: sus términos "
                             "(cláusula 6) lo prohíben; con cuenta de empresa, sí."},
    # El puente ACP oficial de OpenClaw al gateway del perfil de Workspace: el
    # binario se autentica solo (Workspace no toca el token del gateway).
    "openclaw-acp": {"cmd": ["openclaw", "--profile", "workspace", "acp"]},
    # ACP nativo de Hermes (stdio), en el perfil de Workspace: la vía documentada
    # que no depende del WebSocket de `hermes serve`. Otra conversación que la terminal.
    # cable-hermes: la página le pasa el de su agente (pagina_v2.nucleo_para → engines/hermes.cmd_acp); este es
    # el de respaldo. `motor`: el nombre del motor en el entorno (las notas de memoria decían «hermes-acp»,
    # reverificación 19-nov); `tope_abrir`: su primer arranque se cuelga de su gateway y puede pasar de 45 s.
    "hermes-acp": {"cmd": ["hermes", "--profile", "workspace", "acp"], "motor": "hermes", "tope_abrir": 120,
                   "perfil_de_agente": True},
}

def _detalle(e):
    """El porqué que el motor manda en `error.data` (JSON-RPC) junto a un mensaje genérico. cable-openclaw: el puente
    de OpenClaw contesta «Internal error» y el porqué real va en data.details («ACP bridge mode does not support
    per-session MCP servers…»); sin esto la página y la auditoría solo veían «Internal error». '' si no trae."""
    d = getattr(e, "datos", None)
    if isinstance(d, dict):
        d = d.get("details") or d.get("message") or d.get("detail") or ""
    d = str(d or "").strip()
    return (" (%s)" % d[:300]) if d and d not in str(getattr(e, "mensaje", "")) else ""


#: kind de una opción de permiso de ACP → decisión de Workspace.
_KIND = {"allow_once": "permitir", "allow_always": "permitir_siempre",
         "reject_once": "negar", "reject_always": "negar"}
#: Si la decisión no está entre las opciones, la siguiente que no da MÁS permiso.
_RESPALDO = {"permitir_siempre": ("permitir",), "permitir": (), "negar": ()}


class ACP(Conector):
    def __init__(self, motor, cwd=None, cmd=None, env=None, mcp_servers=None, grabar=None,
                 timeout=60, meta_sesion=None):
        super().__init__(cwd=cwd, grabar=grabar)
        #: Cierre de la auditoría (19-nov): el `_meta` de session/new (Kiro: `{"kiro": {"modeId": <agente>}}`, el agente
        #: de la página con sus reglas de lo prohibido; pagina_v2.opciones_kiro). Si el motor confirma ese agente en su
        #: respuesta, queda en bloqueo_secretos.
        self._meta_sesion = meta_sesion if isinstance(meta_sesion, dict) and meta_sesion else None
        if motor not in FICHAS and not cmd:
            raise ErrorControl("motor sin ficha ACP: %s" % motor)
        self.motor = motor
        ficha = FICHAS.get(motor, {})
        self.cmd = list(cmd or ficha["cmd"])
        self.aviso = ficha.get("aviso")
        self._metodo_auth = ficha.get("auth")
        self._env = env
        self._mcp = list(mcp_servers or [])
        self._timeout = timeout
        self._canal = None
        self._rpc = None
        self._cargando = False
        self._ultimo_aviso = 0.0                # B20: el último trozo que repitió al cargar (para esperar a que calle)
        self._capacidades = {}
        self._auth = []
        self._n = itertools.count(1)
        self._texto_turno = []                  # lo que dijo el motor en el turno en curso
        # B01: lo que el motor ya dijo de cada herramienta (toolCallId → kind, title, rawInput, locations). Kiro manda
        # en session/request_permission solo el título (el comando crudo o «Write File»); su clase y su entrada
        # llegaron antes, en el tool_call con el mismo toolCallId (cacería 19-nov, tráfico ACP del verificador)
        self._llamadas = {}
        if ficha.get("tope_abrir"):
            self.tope_abrir = float(ficha["tope_abrir"])
        self._pagina = ""                       # cable-hermes: su sesión en el registro de la página (Hermes)

    def _entorno(self, env=None):
        """El de la capa de control, con el nombre del MOTOR (no el de su conector) en WORKSPACE_ENGINE."""
        from control import entorno
        return entorno.para_motor(env, self.pestana, FICHAS.get(self.motor, {}).get("motor") or self.motor)

    # ── abrir ───────────────────────────────────────────────────────────────
    def _abrir(self, sesion):
        try:
            self._canal = CanalProceso(self.cmd, cwd=self.cwd, env=self._entorno(self._env),
                                       grabar=self._grabar)
            self._registrar_hijo(sesion)
        except OSError as e:
            raise ErrorControl("no pude abrir %s: %s" % (" ".join(self.cmd), e))
        self._rpc = Par(self._canal, al_pedido=self._pedido, al_aviso=self._aviso,
                        al_cerrar=self._al_cerrar)
        try:
            ini = self._rpc.llamar("initialize", {
                "protocolVersion": VERSION_ACP,
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False},
                                       "terminal": False},
                "clientInfo": CLIENTE}, self._timeout) or {}
            self._capacidades = ini.get("agentCapabilities") or {}
            self._auth = [campo(m, "id", "methodId") for m in ini.get("authMethods") or []
                          if isinstance(m, dict)]
            if sesion:
                if not self._capacidades.get("loadSession"):
                    raise ErrorControl("%s no retoma conversaciones por ACP (sin loadSession)"
                                       % self.motor)
                self.sesion = sesion            # el historial que repite se descarta
                self._cargando = True
                try:
                    cargada = self._con_auth("session/load", {"sessionId": sesion, "cwd": self.cwd,
                                                              "mcpServers": self._mcp}) or {}
                    self._drenar_historial()
                finally:
                    self._cargando = False
                self._modo_al_cargar(sesion, cargada)
                self._pagina_abrio(sesion)
                return sesion
            nueva = {"cwd": self.cwd, "mcpServers": self._mcp}
            if self._meta_sesion:
                nueva["_meta"] = self._meta_sesion
            r = self._con_auth("session/new", nueva) or {}
            sid = r.get("sessionId")
            if not sid:
                raise ErrorControl("%s no devolvió sessionId" % self.motor)
            self._modo_confirmado(r)
            self._pagina_abrio(sid)
            return sid
        except (ErrorRPC, ErrorControl) as e:
            self._canal.cerrar(espera=1.0)
            if isinstance(e, ErrorControl):
                raise
            raise ErrorControl("%s: %s%s%s" % (self.motor, e.mensaje, _detalle(e), self._stderr()))

    def _modo_confirmado(self, r):
        """Kiro (cierre de la auditoría): el agente que pidió la página (`_meta.kiro.modeId`) y el que dice su respuesta
        de session/new (`_meta.agentMode`, o `modes.currentModeId`). Si es el pedido, el bloqueo de lo prohibido de su
        perfil queda confirmado; si no, se avisa (la página leería sin esas reglas)."""
        pedido = str(((self._meta_sesion or {}).get("kiro") or {}).get("modeId") or "")
        if not pedido:
            return
        activo = str(campo(r.get("_meta") or {}, "agentMode", defecto="")
                     or campo(r.get("modes") or {}, "currentModeId", defecto="") or "")
        if activo == pedido:
            self.bloqueo_secretos = ("%s abrió la sesión con el agente «%s» de Workspace (sus reglas fs_read niegan "
                                     "leer llaves y secretos)" % (self.motor, pedido))
        else:
            self._emitir("error", mensaje="%s no abrió con el agente «%s» de Workspace (quedó «%s»): por la página "
                                          "no tiene el bloqueo de llaves y secretos" % (self.motor, pedido,
                                                                                         activo or "ninguno"),
                         fatal=False)

    def _modo_al_cargar(self, sesion, r):
        """Una conversación de antes (session/load) sigue con el agente con que se creó: si no es el que pide la página,
        se cambia con `session/set_mode` (ACP: «Switch agent mode»; Kiro lo anuncia en sus modos) y se confirma con lo
        que contestó. Así una conversación de la página creada antes de su agente también queda con sus reglas."""
        pedido = str(((self._meta_sesion or {}).get("kiro") or {}).get("modeId") or "")
        if not pedido:
            return
        r = r if isinstance(r, dict) else {}
        if campo(r.get("modes") or {}, "currentModeId", defecto="") != pedido:
            try:
                r = self._rpc.llamar("session/set_mode", {"sessionId": sesion, "modeId": pedido}, self._timeout) or {}
                r = {"_meta": {"agentMode": pedido}} if not (r.get("_meta") or r.get("modes")) else r
            except ErrorRPC as e:
                r = {"_meta": {"agentMode": "sin cambio: %s" % e.mensaje}}
        self._modo_confirmado(r)

    #: B20 (cacería 19-nov): Antigravity sigue repitiendo el historial DESPUÉS de contestar session/load, y esos trozos se
    #: pegaban a la primera respuesta (y quedaban en el historial, como contexto para otros motores). Tras cargar, se
    #: espera a que el motor se quede callado QUIETO_S (con tope DRENAR_S) antes de dar la sesión por abierta.
    QUIETO_S = 0.5
    DRENAR_S = 4.0

    def _drenar_historial(self):
        inicio = time.time()
        fin = inicio + self.DRENAR_S
        while time.time() < fin and time.time() - max(self._ultimo_aviso, inicio) < self.QUIETO_S:
            time.sleep(0.05)

    def _con_auth(self, metodo, params):
        """La llamada; si el motor pide iniciar sesión y anuncia el método de
        login propio del motor (su login de siempre, sin llaves), lo usa una vez."""
        try:
            return self._rpc.llamar(metodo, params, self._timeout)
        except ErrorRPC as e:
            if e.codigo != AUTH_REQUERIDA:
                raise
            m = self._metodo_auth if self._metodo_auth in self._auth else None
            if m is None and len(self._auth) == 1:
                m = self._auth[0]
            if not m:
                raise ErrorControl("%s pide iniciar sesión: hazlo en su terminal y vuelve a "
                                   "abrir el chat" % self.motor)
            self._rpc.llamar("authenticate", {"methodId": m}, self._timeout)
            return self._rpc.llamar(metodo, params, self._timeout)

    # ── cable-hermes: su sesión en el registro de la página ────────────────
    #: El MCP del perfil de un agente de Hermes lo comparten su terminal y su página (lo abre su gateway una vez):
    #: para saber de qué pestaña es cada llamada (engines/hermes.pestana_para_mcp), la página anota aquí su sesión,
    #: si está a media respuesta y la herramienta del MCP que empieza (su tool_call, por ACP).
    def _perfil_de_agente(self):
        if not FICHAS.get(self.motor, {}).get("perfil_de_agente") or "--profile" not in self.cmd:
            return ""
        i = self.cmd.index("--profile")
        p = self.cmd[i + 1] if i + 1 < len(self.cmd) else ""
        return p if p.startswith("workspace-") else ""

    def _pagina_abrio(self, sid):
        perfil = self._perfil_de_agente()
        if not perfil or self._pagina:
            return
        try:
            from engines import hermes as _hm
            p = self.pestana or {}
            self._pagina = _hm.pagina_abrio(perfil, p.get("cerebro") or self.cwd, p.get("ws") or "",
                                            p.get("wid") or "", p.get("agente") or "", sid)
        except Exception:
            self._pagina = ""

    def _pagina_marcar(self, **campos):
        if not self._pagina:
            return
        try:
            from engines import hermes as _hm
            _hm.pagina_marcar(self._pagina, **campos)
        except Exception:
            pass

    # ── turno ───────────────────────────────────────────────────────────────
    def _mandar(self, texto):
        self._pagina_marcar(turno=time.time())
        self._texto_turno, self._llamadas = [], {}
        self._rpc.llamar_luego("session/prompt", {
            "sessionId": self.sesion, "prompt": [{"type": "text", "text": texto}]}, self._fin_prompt)

    def _fin_prompt(self, resultado, error):
        self._pagina_marcar(turno=None)
        if error is not None:
            if error.codigo == CERRADO:
                return                          # lo cuenta _al_cerrar
            self._emitir("error", mensaje="%s: %s%s" % (self.motor, error.mensaje, _detalle(error)), fatal=False)
            self._terminar("error")
            return
        razon = campo(resultado or {}, "stopReason", defecto="end_turn")
        if razon == "cancelled":
            self._terminar("parado", razon=razon)
        elif razon in ("end_turn",):
            self._terminar("fin", razon=razon)
        else:                                    # max_tokens, max_turn_requests, refusal
            # El texto de ese turno (el motor pudo explicar ahí por qué) va como error: es la
            # única señal estructurada que da ACP. VERIFICADO con el probador real (17-nov):
            # el error de cuota de Copilot llega como texto CON stopReason end_turn; ese no se
            # adivina (sin regex sobre el texto del modelo): VIAS["copilot"] lo avisa.
            dicho = "".join(self._texto_turno).strip()
            self._emitir("error", mensaje="%s se detuvo (%s)%s" % (
                self.motor, razon, ": " + corto(dicho) if dicho else ""), fatal=False, razon=razon)
            self._terminar("fin", razon=razon)

    def _parar(self):
        self._rpc.avisar("session/cancel", {"sessionId": self.sesion})

    def _cerrar(self):
        self._pagina_marcar(cerrar=True)
        if self._canal:
            self._canal.cerrar()

    def _al_cerrar(self, motivo):
        self._pagina_marcar(cerrar=True)
        self._perdido("%s se cerró (%s)%s" % (self.motor, motivo, self._stderr()))

    def _stderr(self):
        e = self._canal.stderr() if self._canal else ""
        return (": " + e) if e else ""

    # ── lo que llega del motor ──────────────────────────────────────────────
    def _aviso(self, metodo, params):
        if metodo == "session/update" and self._cargando:
            self._ultimo_aviso = time.time()        # B20: lo que repite al cargar se descarta, y se mide
            return
        if metodo != "session/update":
            return
        if params.get("sessionId") not in (None, self.sesion):
            return
        u = params.get("update") or {}
        tipo = u.get("sessionUpdate")
        if tipo == "agent_message_chunk":
            c = u.get("content") or {}
            if c.get("type") == "text" and c.get("text"):
                self._texto_turno.append(c["text"])
                self._emitir("texto", texto=c["text"])
        elif tipo in ("tool_call", "tool_call_update"):
            tid = str(u.get("toolCallId") or "")
            estado = u.get("status")
            if tid:
                ya = self._llamadas.get(tid) or {}
                self._llamadas[tid] = dict(ya, **{k: u[k] for k in ("kind", "title", "rawInput", "locations")
                                                  if u.get(k)})
                if estado in ("completed", "failed"):
                    self._llamadas.pop(tid, None)
            if tipo == "tool_call" and str(u.get("title") or "").startswith("mcp__workspace__"):
                self._pagina_marcar(mcp=u["title"])
            if tipo == "tool_call":
                # su clase, de lo estructurado (B01): «Lo que va haciendo» no la adivina de su título
                self._emitir("herramienta", id=tid, nombre=u.get("title") or u.get("kind") or "?",
                             fase="empieza", detalle=corto(u.get("rawInput")), archivo=archivo_de(u.get("rawInput")),
                             clase=que_permiso(u.get("title"), u.get("rawInput"), u.get("kind"))["clase"])
            if estado in ("completed", "failed"):
                self._emitir("herramienta", id=tid, nombre=u.get("title") or "",
                             fase="termina" if estado == "completed" else "falla",
                             detalle=corto(u.get("rawOutput")))
        elif tipo == "usage_update":
            self._poner_uso(fuente="acp", crudo={k: v for k, v in u.items() if k != "sessionUpdate"})

    def _pedido(self, metodo, params):
        if metodo != "session/request_permission":
            # fs/* y terminal/* no se anunciaron; extensiones de cada motor, tampoco.
            raise ErrorRPC(METODO_NO_EXISTE, "Method not found: %s" % metodo)
        tc = params.get("toolCall") or {}
        # lo que trae el pedido gana; lo que falta, de su tool_call de antes (B01)
        tc = dict(self._llamadas.get(str(tc.get("toolCallId") or "")) or {}, **{k: v for k, v in tc.items() if v})
        rutas = [x.get("path") for x in (tc.get("locations") or []) + [c for c in tc.get("content") or []
                                                                       if isinstance(c, dict) and c.get("type") == "diff"]
                 if isinstance(x, dict)]
        opciones = {}
        for o in params.get("options") or []:
            d = _KIND.get(o.get("kind"))
            if d and d not in opciones:
                opciones[d] = o.get("optionId")
        pid = "%s#%d" % (tc.get("toolCallId") or "permiso", next(self._n))
        d = self._esperar_permiso(pid, tc.get("title") or tc.get("kind") or "herramienta",
                                  tc.get("rawInput") or tc.get("content"), list(opciones),
                                  kind=tc.get("kind"), rutas=rutas)
        for elegida in ((d,) + _RESPALDO.get(d, ())) if d else ():
            if elegida in opciones:
                return {"outcome": {"outcome": "selected", "optionId": opciones[elegida]}}
        return {"outcome": {"outcome": "cancelled"}}


assert set(_KIND.values()) <= set(DECISIONES)
