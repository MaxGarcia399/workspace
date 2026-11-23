"""WORKSPACE · control/jsonrpc.py — JSON-RPC 2.0 en las dos direcciones sobre
un canal (control.canal): el cliente llama métodos del motor y el motor le
pide cosas al cliente (permisos en ACP, aprobaciones en Codex y Hermes).

  · `llamar(metodo, params, timeout)` bloquea hasta la respuesta;
  · `llamar_luego(metodo, params, al_terminar)` no bloquea (session/prompt de
    ACP responde recién al final del turno);
  · `avisar(metodo, params)` = notificación;
  · `al_pedido(metodo, params) → result` atiende lo que pide el motor, en su
    propio hilo (puede esperar a que el socio conteste un permiso); levantar
    ErrorRPC responde con ese error;
  · `al_aviso(metodo, params)` atiende notificaciones, en orden, en el hilo
    lector;
  · `al_cerrar(motivo)` cuando el canal se cierra (todo lo pendiente falla).

`cabecera=False` omite "jsonrpc":"2.0" al enviar (el app-server de Codex lo
omite en su protocolo); al recibir se acepta con o sin ella."""
import itertools
import json
import threading


class ErrorRPC(Exception):
    def __init__(self, codigo, mensaje, datos=None):
        super().__init__("%s (%s)" % (mensaje, codigo))
        self.codigo = codigo
        self.mensaje = mensaje
        self.datos = datos


#: Código propio para «se cerró el canal» (no lo manda nadie por el cable).
CERRADO = -32099
METODO_NO_EXISTE = -32601


class Par:
    def __init__(self, canal, al_pedido=None, al_aviso=None, al_cerrar=None, cabecera=True):
        self.canal = canal
        self._al_pedido = al_pedido
        self._al_aviso = al_aviso
        self._al_cerrar = al_cerrar
        self._cabecera = cabecera
        self._ids = itertools.count(1)
        self._pend = {}                  # id → (Event, caja) | callback
        self._candado = threading.Lock()
        self.cerrado = False
        self._hilo = threading.Thread(target=self._leer, name="control-jsonrpc", daemon=True)
        self._hilo.start()

    # ── enviar ──────────────────────────────────────────────────────────────
    def _enviar(self, msg):
        if self._cabecera:
            msg = dict({"jsonrpc": "2.0"}, **msg)
        self.canal.enviar(json.dumps(msg, ensure_ascii=False, separators=(",", ":")))

    def llamar(self, metodo, params=None, timeout=60):
        hecho = threading.Event()
        caja = {}

        def fin(resultado, error):
            caja["r"], caja["e"] = resultado, error
            hecho.set()
        self.llamar_luego(metodo, params, fin)
        if not hecho.wait(timeout):
            with self._candado:
                for k, v in list(self._pend.items()):
                    if v is fin:
                        del self._pend[k]
            raise ErrorRPC(-32000, "%s: sin respuesta en %s s" % (metodo, timeout))
        if caja["e"] is not None:
            raise caja["e"]
        return caja["r"]

    def llamar_luego(self, metodo, params, al_terminar):
        mid = next(self._ids)
        with self._candado:
            if self.cerrado:
                al_terminar(None, ErrorRPC(CERRADO, "el canal está cerrado"))
                return mid
            self._pend[mid] = al_terminar
        msg = {"id": mid, "method": metodo}
        if params is not None:
            msg["params"] = params
        try:
            self._enviar(msg)
        except (OSError, ValueError) as e:
            with self._candado:
                self._pend.pop(mid, None)
            al_terminar(None, ErrorRPC(CERRADO, "no pude escribir: %s" % e))
        return mid

    def avisar(self, metodo, params=None):
        msg = {"method": metodo}
        if params is not None:
            msg["params"] = params
        try:
            self._enviar(msg)
        except (OSError, ValueError):
            pass

    # ── recibir ─────────────────────────────────────────────────────────────
    def _leer(self):
        motivo = "el motor cerró la conexión"
        try:
            while True:
                texto = self.canal.recibir()
                if texto is None:
                    break
                try:
                    msg = json.loads(texto)
                except ValueError:
                    continue                    # una línea que no es JSON (log): se ignora
                if isinstance(msg, dict):
                    self._despachar(msg)
        except Exception as e:                  # defensa: el hilo lector nunca revienta
            motivo = "%s: %s" % (type(e).__name__, e)
        with self._candado:
            self.cerrado = True
            pend, self._pend = self._pend, {}
        for fin in pend.values():
            fin(None, ErrorRPC(CERRADO, motivo))
        if self._al_cerrar:
            self._al_cerrar(motivo)

    def _despachar(self, msg):
        metodo = msg.get("method")
        if isinstance(metodo, str):
            if "id" in msg and msg["id"] is not None:
                threading.Thread(target=self._atender, args=(msg,), daemon=True,
                                 name="control-pedido").start()
            elif self._al_aviso:
                self._al_aviso(metodo, msg.get("params") or {})
            return
        with self._candado:
            fin = self._pend.pop(msg.get("id"), None)
        if fin is None:
            return
        if "error" in msg and msg["error"] is not None:
            err = msg["error"] if isinstance(msg["error"], dict) else {"message": str(msg["error"])}
            fin(None, ErrorRPC(err.get("code", -32000), err.get("message", "error"), err.get("data")))
        else:
            fin(msg.get("result"), None)

    def _atender(self, msg):
        mid = msg["id"]
        try:
            if not self._al_pedido:
                raise ErrorRPC(METODO_NO_EXISTE, "Method not found: %s" % msg["method"])
            resultado = self._al_pedido(msg["method"], msg.get("params") or {})
            resp = {"id": mid, "result": resultado}
        except ErrorRPC as e:
            resp = {"id": mid, "error": {"code": e.codigo, "message": e.mensaje}}
        except Exception as e:
            resp = {"id": mid, "error": {"code": -32603, "message": "%s: %s" % (type(e).__name__, e)}}
        try:
            self._enviar(resp)
        except (OSError, ValueError):
            pass
