"""WORKSPACE · control/openclaw.py — OpenClaw por su Gateway (WebSocket,
protocolo v4). El Gateway es dueño de las sesiones; la TUI, la Control UI y
este cliente «proyectan» el mismo estado: con la misma clave de sesión, la
página ve y escribe en la conversación de la terminal.

Tramas: {"type":"req","id","method","params"} → {"type":"res","id","ok",
"payload"|"error"}; el Gateway empuja {"type":"event","event","payload","seq"}.
Saludo: el Gateway manda `connect.challenge` (nonce) y el cliente responde
`connect` con role "operator", scopes y la capacidad "tool-events" (sin ella
no llegan los eventos de herramientas, y no avisa). Turno: chat.send →
eventos `agent` (stream assistant | tool | lifecycle) y `chat` (final,
aborted, error). Cortar: chat.abort. Aprobaciones: exec.approval.requested →
exec.approval.resolve.

Autenticación: el Gateway del perfil de Workspace usa token
(engines/openclaw.ensure_gateway_config). Este módulo NO lo lee: lo recibe
(`token`) o firma el reto con un dispositivo propio (`dispositivo(nonce)` →
dict), según decida quien lo integra. Sin eso, la vía sin token es el puente
oficial `openclaw acp` (OpenClawACP, motor "openclaw-acp").

El gateway del perfil solo está encendido mientras alguna pestaña lo usa
(openclaw_gateway: un guardián lo apaga sin clientes vivos). Por eso los dos
conectores lo encienden al abrir con el MISMO mecanismo que las pestañas
(preparar_gateway: anotarse como cliente, ensure_running, wait_ready) y lo
sueltan al cerrar. VERIFICADO con el probador real (17-nov): con el gateway
apagado, `openclaw acp` fallaba con «connect ECONNREFUSED 127.0.0.1:<puerto>»."""
import itertools
import json
import platform
import threading
import uuid

from control.acp import ACP
from control.base import INTERRUMPIDO, Conector, ErrorControl, campo, corto
from control.ws import ErrorWS, conectar

PROTOCOLO = 4
SCOPES = ["operator.read", "operator.write", "operator.approvals"]
#: client.id y client.mode del connect. VERIFICADO con la página (18-nov): con
#: "workspace-control"/"operator" el gateway contesta «invalid connect params: at
#: /client/id must be equal to one of the allowed values; at /client/mode …».
#: Su doc (docs/gateway/protocol/handshake.md del paquete instalado, 2026.10.7):
#: «Trusted local backend clients (client.id: "gateway-client", client.mode:
#: "backend") may omit device on direct loopback connections» — justo la página.
CLIENTE_ID = "gateway-client"
CLIENTE_MODO = "backend"
_DECISION = {"permitir": "allow-once", "permitir_siempre": "allow-always", "negar": "deny"}

#: Cuántos conectores de este proceso usan el gateway (se anota UNA vez por proceso).
_USUARIOS = {"n": 0}
_CANDADO_GW = threading.Lock()


def preparar_gateway(espera=None, aviso=None):
    """Enciende (si hace falta) el gateway del perfil de Workspace como lo hace
    una pestaña y anota a este proceso como cliente, para que el guardián no lo
    apague mientras se use. Devuelve (url, "") o (None, motivo)."""
    import engines.openclaw as oc
    import openclaw_gateway as G
    exe = oc._exe()
    if not exe:
        return None, "openclaw no está en PATH"
    ok, puerto, motivo = oc.ensure_gateway_config(exe)
    if not ok:
        return None, motivo or "no pude preparar el gateway de OpenClaw"
    if not puerto:
        return None, "el gateway de OpenClaw no lo administra Workspace (otro modo en su config)"
    perfil = oc._profile()
    with _CANDADO_GW:
        if _USUARIOS["n"] == 0:
            G.enter(perfil)
        _USUARIOS["n"] += 1
    G.ensure_running(exe, perfil, puerto)
    ok, motivo = G.wait_ready(exe, perfil, puerto, timeout=espera or G.START_TIMEOUT, notify=aviso)
    if not ok:
        soltar_gateway()
        return None, motivo
    return "ws://127.0.0.1:%d" % puerto, ""


def soltar_gateway():
    """El último conector de este proceso deja de ser cliente del gateway."""
    import engines.openclaw as oc
    import openclaw_gateway as G
    with _CANDADO_GW:
        if _USUARIOS["n"] == 0:
            return
        _USUARIOS["n"] -= 1
        if _USUARIOS["n"] == 0:
            G.leave(oc._profile())


class OpenClaw(Conector):
    motor = "openclaw"
    misma_conversacion = True

    def __init__(self, cwd=None, url=None, token=None, dispositivo=None, agente="main", sock=None,
                 grabar=None, timeout=30):
        super().__init__(cwd=cwd, grabar=grabar)
        self.url = url
        self._propio = url is None and sock is None       # el gateway del perfil de Workspace
        self._tomado = False
        self._token = token
        self._dispositivo = dispositivo
        self._agente = agente
        self._sock = sock
        self._timeout = timeout
        self._ws = None
        self._ids = itertools.count(1)
        self._pend = {}
        self._candado_rpc = threading.Lock()
        self._reto = threading.Event()
        self._nonce = None
        self._run = None
        self._previo = ""                       # texto acumulado (si llega sin delta)

    # ── tramas ──────────────────────────────────────────────────────────────
    def _enviar(self, trama):
        texto = json.dumps(trama, ensure_ascii=False, separators=(",", ":"))
        if self._grabar:
            self._grabar(">", texto)
        self._ws.enviar(texto)

    def _llamar_luego(self, metodo, params, fin):
        mid = str(next(self._ids))
        with self._candado_rpc:
            self._pend[mid] = fin
        try:
            self._enviar({"type": "req", "id": mid, "method": metodo, "params": params})
        except (OSError, ErrorWS) as e:
            with self._candado_rpc:
                self._pend.pop(mid, None)
            fin(False, {"message": str(e)})

    def _llamar(self, metodo, params):
        hecho, caja = threading.Event(), {}

        def fin(ok, datos):
            caja["ok"], caja["datos"] = ok, datos
            hecho.set()
        self._llamar_luego(metodo, params, fin)
        if not hecho.wait(self._timeout):
            raise ErrorControl("OpenClaw: %s sin respuesta en %s s" % (metodo, self._timeout))
        if not caja["ok"]:
            raise ErrorControl("OpenClaw: %s: %s" % (metodo, campo(caja["datos"] or {}, "message",
                                                                    "code", defecto="error")))
        return caja["datos"]

    def _leer(self):
        while True:
            texto = self._ws.recibir() if self._ws else None
            if texto is None:
                break
            if self._grabar:
                self._grabar("<", texto)
            try:
                t = json.loads(texto)
            except ValueError:
                continue
            if not isinstance(t, dict):
                continue
            if t.get("type") == "res":
                with self._candado_rpc:
                    fin = self._pend.pop(str(t.get("id")), None)
                if fin:
                    fin(bool(t.get("ok")), t.get("payload") if t.get("ok") else t.get("error"))
            elif t.get("type") == "event":
                try:
                    self._evento(t.get("event"), t.get("payload") or {})
                except Exception as e:                 # un evento raro no tumba al lector
                    self._emitir("error", mensaje="OpenClaw: evento ilegible: %s" % e, fatal=False)
        with self._candado_rpc:
            pend, self._pend = self._pend, {}
        for fin in pend.values():
            fin(False, {"message": "conexión cerrada"})
        self._reto.set()
        self._perdido("se cerró la conexión con el gateway de OpenClaw")

    # ── abrir ───────────────────────────────────────────────────────────────
    def _abrir_nueva(self, sesion):
        """La clave de sesión la pone el cliente: nueva o existente, es la misma."""
        return self._abrir(sesion)

    def _preparar(self):
        """Encender el gateway del perfil (la primera vez tarda): fuera del tope de abrir."""
        if self._propio and not self._tomado:
            url, motivo = preparar_gateway()
            if not url:
                raise ErrorControl("OpenClaw: %s" % motivo)
            self.url, self._tomado = url, True

    def _abrir(self, sesion):
        try:
            self._ws = conectar(self.url or "ws://127.0.0.1", sock=self._sock, timeout=self._timeout)
        except (OSError, ErrorWS) as e:
            self._soltar()
            raise ErrorControl("no pude conectar con el gateway de OpenClaw (%s): %s" % (self.url, e))
        self._reto.clear()
        threading.Thread(target=self._leer, name="control-openclaw", daemon=True).start()
        self._reto.wait(min(3.0, self._timeout))      # el reto llega primero (si lo hay)
        params = {"minProtocol": PROTOCOLO, "maxProtocol": PROTOCOLO,
                  "client": {"id": CLIENTE_ID, "version": "control-1",
                             "platform": platform.system().lower(), "mode": CLIENTE_MODO},
                  "role": "operator", "scopes": SCOPES, "caps": ["tool-events"]}
        if self._token:
            params["auth"] = {"token": self._token}
        if self._dispositivo and self._nonce:
            params["device"] = self._dispositivo(self._nonce)
        try:
            self._llamar("connect", params)
            clave = sesion or "agent:%s:workspace-%s" % (self._agente, uuid.uuid4().hex[:12])
            try:
                self._llamar("sessions.subscribe", {"sessionKey": clave})
            except ErrorControl:
                pass                                   # sin suscripción igual llegan los del turno
            return clave
        except ErrorControl:
            self._cerrar()
            raise

    # ── turno ───────────────────────────────────────────────────────────────
    def _mandar(self, texto):
        self._run, self._previo = None, ""

        def fin(ok, datos):
            if ok:
                self._run = campo(datos or {}, "runId") or self._run
            else:
                self._emitir("error", mensaje="OpenClaw no aceptó el mensaje: %s"
                             % campo(datos or {}, "message", defecto=corto(datos)), fatal=False)
                self._terminar("error")
        self._llamar_luego("chat.send", {"sessionKey": self.sesion, "message": texto,
                                         "idempotencyKey": uuid.uuid4().hex}, fin)

    def _parar(self):
        params = {"sessionKey": self.sesion}
        if self._run:
            params["runId"] = self._run
        self._llamar_luego("chat.abort", params, lambda ok, d: None)

    def _cerrar(self):
        ws, self._ws = self._ws, None
        if ws:
            ws.cerrar()
        self._soltar()

    def _soltar(self):
        if self._tomado:
            self._tomado = False
            soltar_gateway()

    # ── eventos ─────────────────────────────────────────────────────────────
    def _mio(self, p):
        clave = campo(p, "sessionKey")
        if clave is not None:
            return clave == self.sesion
        return self._run is not None and campo(p, "runId") == self._run

    def _evento(self, nombre, p):
        if nombre == "connect.challenge":
            self._nonce = campo(p, "nonce")
            self._reto.set()
            return
        if nombre == "exec.approval.resolved":
            self._olvidar_permiso(campo(p, "id", defecto=""))
            return
        if not self._mio(p):
            return
        if nombre == "agent":
            flujo, d = p.get("stream"), p.get("data") or {}
            if flujo == "assistant":
                t = campo(d, "delta")
                if t is None and isinstance(d.get("text"), str):      # acumulado → lo nuevo
                    t = d["text"][len(self._previo):] if d["text"].startswith(self._previo) else d["text"]
                    self._previo = d["text"]
                if t:
                    self._emitir("texto", texto=t)
            elif flujo == "tool":
                fase = {"start": "empieza", "result": "termina", "end": "termina"}.get(d.get("phase"))
                if fase:
                    if fase == "termina" and d.get("isError"):
                        fase = "falla"
                    self._emitir("herramienta", id=str(campo(d, "toolCallId", "id", defecto="")),
                                 nombre=campo(d, "name", "tool", defecto="?"), fase=fase,
                                 detalle=corto(campo(d, "args", "result", "meta")))
            elif flujo == "lifecycle":
                if d.get("phase") == "error":
                    self._emitir("error", mensaje="OpenClaw: %s" % (campo(d, "error", "message")
                                                                    or "el turno falló"), fatal=False)
                    self._terminar("error")
                elif d.get("phase") == "end":
                    self._terminar("parado" if d.get("aborted") else "fin")
        elif nombre == "chat":
            estado = p.get("state")
            if estado == "final":
                self._terminar("fin")
            elif estado == "aborted":
                self._terminar("parado")
            elif estado == "error":
                self._emitir("error", mensaje="OpenClaw: %s" % (campo(p, "errorMessage", "error")
                                                                or "el turno falló"), fatal=False)
                self._terminar("error")
        elif nombre == "exec.approval.requested":
            pid = str(campo(p, "id", defecto=""))
            pedido = p.get("request") or p

            def responder(decision, pid=pid):
                if decision is None and self.corte() in INTERRUMPIDO:
                    # E9: la página se apaga o se reinicia. Su gateway sigue vivo: el pedido se queda pendiente ahí
                    # (nunca un «deny» a nombre del socio). A VERIFICAR con el motor real.
                    return
                self._llamar_luego("exec.approval.resolve",
                                   {"id": pid, "decision": _DECISION.get(decision, "deny")},
                                   lambda ok, d: None)
            self._anunciar_permiso(pid, campo(pedido, "tool", defecto="comando"),
                                   campo(pedido, "command", "argv", "summary"),
                                   ("permitir", "permitir_siempre", "negar"), responder)


def comando_acp(clave=""):
    from engines import openclaw as oc
    from control.acp import FICHAS

    cmd = list(FICHAS["openclaw-acp"]["cmd"])
    if cmd == ["openclaw", "--profile", "workspace", "acp"]:
        cmd[2] = oc._profile()
    return cmd + (["--session", clave] if clave else [])


class OpenClawACP(ACP):
    """El puente oficial `openclaw --profile workspace acp` (ACP por stdio) al
    gateway del perfil: el binario se autentica solo con su config, así que
    Workspace no toca el token. Antes de lanzarlo, enciende el gateway como una
    pestaña (preparar_gateway) y lo suelta al cerrar."""

    def __init__(self, motor="openclaw-acp", gateway=True, **opciones):
        super().__init__(motor, **opciones)
        self._gateway = gateway
        self._tomado = False

    def _preparar(self):
        """Encender el gateway del perfil (la primera vez tarda): fuera del tope de abrir."""
        if self._gateway and not self._tomado:
            url, motivo = preparar_gateway()
            if not url:
                raise ErrorControl("OpenClaw: %s" % motivo)
            self._tomado = True

    def _abrir(self, sesion):
        try:
            return super()._abrir(sesion)
        except Exception:
            self._soltar()
            raise

    def _cerrar(self):
        try:
            super()._cerrar()
        finally:
            self._soltar()

    def _soltar(self):
        if self._tomado:
            self._tomado = False
            soltar_gateway()
