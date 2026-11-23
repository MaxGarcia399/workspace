"""WORKSPACE · control/hermes.py — Hermes por el JSON-RPC de su gateway
(protocolo `hermes-gateway-v1`), el que su doc recomienda para clientes
propios: WebSocket `/api/ws` (el backend local de `hermes serve`, puerto 9119)
o stdio (`cmd`). Varios clientes pueden unirse a una misma sesión: la página
ve la conversación de la terminal si las dos van por el mismo gateway.

Métodos: session.create / session.resume, prompt.submit, session.interrupt.
Eventos: message.delta, message.complete, tool.start, tool.complete, error.
Aprobaciones: el gateway las PIDE al cliente (`approval`) si este anuncia
`client.capabilities {server_requests: true}`.

Ojo: `hermes gateway attach --json` (el ticket para el WebSocket que cita la
doc) no existe en la v0.22.5 de esta Mac; aquí no se usa ticket. «Permitir
siempre» se contesta como «en esta sesión» (`session`): Workspace no deja una
aprobación guardada en la config del socio.

Quién enciende el servidor: VERIFICADO con el probador real (17-nov), en la
9119 no escuchaba nadie. `hermes serve --help` (0.22.5): «the JSON-RPC/
WebSocket gateway the desktop app and remote clients connect to», puerto por
defecto 9119 en 127.0.0.1; desde un perfil, `--isolated` abre un servidor
SOLO de ese perfil en vez del de toda la máquina, y `--skip-build` no
construye la web. `comando_servidor` lo arma; quién lo mantiene encendido en
la página es de F3/F4 (como el guardián del gateway de OpenClaw). Nunca
`hermes serve --stop`: apaga TODOS los servidores de Hermes de la máquina."""
import itertools

from control.base import Conector, ErrorControl, campo, corto
from control.canal import CanalProceso, CanalWS, resolver
from control.jsonrpc import CERRADO, ErrorRPC, METODO_NO_EXISTE, Par
from control.ws import ErrorWS, conectar

URL = "ws://127.0.0.1:9119/api/ws"
RUTA_WS = "/api/ws"
PERFIL = "workspace"
_ELECCION = {"permitir": "once", "permitir_siempre": "session", "negar": "deny"}


#: El subprotocolo que se ofrece en el saludo (el nombre del protocolo del gateway en su doc).
SUBPROTOCOLO = "hermes-gateway-v1"


def comando_servidor(puerto, perfil=PERFIL):
    """El servidor JSON-RPC/WebSocket de Hermes, solo del perfil de Workspace,
    en 127.0.0.1:<puerto>. Sin `--ssh-session-token-file`: VERIFICADO con el
    probador real (0.22.5, 18-nov) que exige el archivo «under the desktop-ssh
    directory», dentro del HOME de Hermes, donde Workspace no escribe."""
    return resolver(["hermes", "--profile", perfil, "serve", "--isolated", "--host", "127.0.0.1",
                     "--port", str(int(puerto)), "--skip-build"])


def url_servidor(puerto):
    return "ws://127.0.0.1:%d%s" % (int(puerto), RUTA_WS)


def entorno_servidor(base=None, pestana=None):
    """El entorno de `hermes serve`: sin las variables de identidad de otra
    pestaña y con las de `pestana` (punto F, control/entorno.py)."""
    from control import entorno
    return entorno.para_motor(base, pestana, "hermes")


def origen_de(url):
    """El Origin «del mismo sitio» (http://host:puerto del servidor), el que
    manda la propia página de Hermes servida en ese puerto."""
    from urllib.parse import urlsplit
    p = urlsplit(url or "")
    return "http://%s:%s" % (p.hostname or "127.0.0.1", p.port or 80)


class Hermes(Conector):
    """VERIFICADO con el probador real (0.22.5): el WebSocket de `hermes serve`
    contestó «403 Forbidden», sin WWW-Authenticate ni cuerpo, a un saludo sin
    nada (17-nov) y a uno con el Origin del mismo sitio (18-nov); su ayuda y su
    registro no dicen qué pide. El saludo ofrece además el subprotocolo
    `hermes-gateway-v1` (el nombre del protocolo en su doc). El probador prueba
    las combinaciones y dice cuál abrió. Mientras ninguna abra, en la página
    Hermes es «solo mirar» (control.VIAS) y la vía para escribirle es su ACP
    (`hermes-acp`)."""
    motor = "hermes"
    misma_conversacion = True

    def __init__(self, cwd=None, url=URL, cmd=None, cabeceras=None, origen=True,
                 subprotocolo=SUBPROTOCOLO, token=None, token_en_url=False, sock=None, env=None,
                 grabar=None, timeout=60):
        super().__init__(cwd=cwd, grabar=grabar)
        self.url = url
        self.cmd = list(cmd) if cmd else None
        self.subprotocolo = subprotocolo
        self._cabeceras = dict(cabeceras or {})
        if origen:
            self._cabeceras.setdefault("Origin", origen if isinstance(origen, str) else origen_de(url))
        if token and not token_en_url:
            self._cabeceras.setdefault("Authorization", "Bearer " + token)
        if token and token_en_url:
            from urllib.parse import quote
            self.url = "%s%stoken=%s" % (url, "&" if "?" in url else "?", quote(token, safe=""))
        self._sock = sock                      # un socket ya abierto (pruebas)
        self._env = env
        self._timeout = timeout
        self._canal = None
        self._rpc = None
        self._parando = False
        self._n = itertools.count(1)

    def _abrir(self, sesion):
        try:
            if self.cmd:
                self._canal = CanalProceso(self.cmd, cwd=self.cwd, env=self._entorno(self._env),
                                           grabar=self._grabar)
                self._registrar_hijo(sesion)
            else:
                ws = conectar(self.url, self._cabeceras, sock=self._sock, timeout=self._timeout,
                              subprotocolos=[self.subprotocolo] if self.subprotocolo else None)
                self._canal = CanalWS(ws, grabar=self._grabar)
        except (OSError, ErrorWS) as e:
            donde = " ".join(self.cmd) if self.cmd else self.url.split("?")[0]   # sin el token
            raise ErrorControl("no pude conectar con el gateway de Hermes (%s): %s" % (donde, e))
        self._rpc = Par(self._canal, al_pedido=self._pedido, al_aviso=self._aviso,
                        al_cerrar=self._al_cerrar)
        try:
            try:
                self._rpc.llamar("client.capabilities", {"server_requests": True}, self._timeout)
            except ErrorRPC as e:
                if e.codigo != METODO_NO_EXISTE:
                    raise
            if sesion:
                r = self._rpc.llamar("session.resume", {"session_id": sesion}, self._timeout)
            else:
                r = self._rpc.llamar("session.create", {"cwd": self.cwd}, self._timeout)
            sid = campo(r, "session_id", "sessionId", "id") or sesion
            if not sid:
                raise ErrorControl("hermes no devolvió el id de la sesión")
            return sid
        except (ErrorRPC, ErrorControl) as e:
            self._canal.cerrar(espera=1.0)
            if isinstance(e, ErrorControl):
                raise
            raise ErrorControl("hermes: %s" % e.mensaje)

    def _mandar(self, texto):
        self._parando = False

        def fin(r, error):
            if error is not None and error.codigo != CERRADO:
                self._emitir("error", mensaje="hermes: %s" % error.mensaje, fatal=False)
                self._terminar("error")
        self._rpc.llamar_luego("prompt.submit", {"session_id": self.sesion, "text": texto}, fin)

    def _parar(self):
        self._parando = True
        self._rpc.llamar_luego("session.interrupt", {"session_id": self.sesion}, lambda r, e: None)

    def _cerrar(self):
        if self._canal:
            self._canal.cerrar()

    def _al_cerrar(self, motivo):
        e = self._canal.stderr() if self._canal else ""
        self._perdido("el gateway de Hermes se cerró (%s)%s" % (motivo, ": " + e if e else ""))

    def _aviso(self, metodo, p):
        # Dos formas: {"method":"event","params":{"type":…,"session_id":…,"payload":…}} o el
        # nombre del evento como método.
        if metodo == "event":
            tipo, datos = p.get("type"), campo(p, "payload", defecto=p)
        else:
            tipo, datos = metodo, p
        if campo(p, "session_id", "sessionId") not in (None, self.sesion):
            return
        if tipo == "message.delta":
            t = campo(datos, "text", "delta")
            if t:
                self._emitir("texto", texto=t)
        elif tipo == "tool.start":
            self._emitir("herramienta", id=str(campo(datos, "tool_id", "id", "call_id", defecto="")),
                         nombre=campo(datos, "name", "tool", "tool_name", defecto="?"),
                         fase="empieza", detalle=corto(campo(datos, "args", "input", "preview")))
        elif tipo == "tool.complete":
            mal = bool(campo(datos, "error")) or campo(datos, "status") == "error"
            self._emitir("herramienta", id=str(campo(datos, "tool_id", "id", "call_id", defecto="")),
                         nombre=campo(datos, "name", "tool", "tool_name", defecto=""),
                         fase="falla" if mal else "termina",
                         detalle=corto(campo(datos, "error", "summary", "result")))
        elif tipo == "message.complete":
            u = campo(datos, "usage")
            if u:
                self._poner_uso(fuente="hermes", tokens=u)
            interrumpido = campo(datos, "status") in ("interrupted", "cancelled")
            self._terminar("parado" if (self._parando or interrumpido) else "fin")
        elif tipo == "error":
            self._emitir("error", mensaje="hermes: %s" % (campo(datos, "message", "error") or corto(datos)),
                         fatal=False)
            self._terminar("parado" if self._parando else "error")

    def _pedido(self, metodo, p):
        if metodo == "approval":
            pid = campo(p, "id", "request_id", defecto="aprobacion-%d" % next(self._n))
            d = self._esperar_permiso(pid, campo(p, "tool", "tool_name", defecto="comando"),
                                      campo(p, "command", "description", "summary"))
            return {"choice": _ELECCION.get(d, "deny")}
        if metodo == "clarify":
            # La capa de control no hace preguntas abiertas: se avisa y se contesta en la terminal.
            self._emitir("error", fatal=False,
                         mensaje="Hermes pregunta: %s (contéstalo en su terminal)"
                                 % corto(campo(p, "question", "text", defecto=p)))
        raise ErrorRPC(METODO_NO_EXISTE, "Method not found: %s" % metodo)
