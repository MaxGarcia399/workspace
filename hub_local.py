#!/usr/bin/env python3
r"""WORKSPACE · hub_local — lecturas de la página sin la página. SOLO PARA PROBAR: vive en la rama zenith/hub-bloque y
nunca entra a main.

Si la página local que está prendida es de otra versión y no trae una ruta de LECTURA que el hub necesita (hoy:
/api/v2/sesiones, que solo traen las ramas de prueba), el hub la calcula aquí: el Handler de ESTA versión, en el
mismo proceso, sin socket, solo GET y solo de las rutas de LEER, con pagina_v2.SOLO_LEER puesto mientras lee. Nada
se escribe así: la página prendida sigue siendo la única dueña de todo lo que se escribe (las escrituras del hub
van siempre a ella; si no trae una, el hub la muestra apagada).

LEER son rutas que solo leen (revisado): /api/front/inicio NO está (siembra la apariencia de cada agente) ni
/api/sistema/motores (verifica los motores). Stdlib."""
import http.client
import io
import secrets
import threading

#: Las rutas que se pueden calcular aquí (solo leen).
LEER = ("/api/v2/sesiones", "/api/skills", "/api/conexiones", "/api/v2/info", "/api/calendario",
        "/api/sistema/usuarios", "/api/v2/conexiones")
_LOCK = threading.Lock()


class _Servidor:
    """Lo que el Handler usa de su servidor: una llave de este proceso, su dirección y su apagado."""

    def __init__(self):
        self.server_address = ("127.0.0.1", 9)
        self.llave = secrets.token_urlsafe(24)
        self.apagado = threading.Event()
        self.public = False

    def shutdown(self):
        pass


_SRV = None


def puede(ruta):
    """¿Se puede leer `ruta` (sin su ?query) aquí?"""
    return ruta.split("?", 1)[0] in LEER


def get(ruta):
    """GET `ruta` (con su ?query) en el Handler de esta versión, en el mismo proceso. → (status, bytes). Solo las
    de LEER; lo demás, ValueError (nunca se escribe por aquí)."""
    global _SRV
    if not puede(ruta):
        raise ValueError("hub_local solo lee: %s" % ruta.split("?", 1)[0])
    import localhost_web as LW
    import pagina_v2
    with _LOCK:
        if _SRV is None:
            _SRV = _Servidor()
        viejo = pagina_v2.SOLO_LEER
        pagina_v2.SOLO_LEER = True                       # mientras lee: nada de lo que escribe la página
        try:
            h = LW.Handler.__new__(LW.Handler)
            msg = http.client.HTTPMessage()
            base = "127.0.0.1:%d" % _SRV.server_address[1]
            msg["Host"] = base
            msg["Cookie"] = "ws_llave=%s" % _SRV.llave
            h.server, h.client_address, h.command, h.path = _SRV, ("127.0.0.1", 50000), "GET", ruta
            h.request_version, h.requestline, h.headers = "HTTP/1.1", "GET %s HTTP/1.1" % ruta, msg
            h.rfile, h.wfile, h._extra, h.close_connection = io.BytesIO(b""), io.BytesIO(), (), True
            h.log_message = lambda *a, **k: None
            h.do_GET()
        finally:
            pagina_v2.SOLO_LEER = viejo
    cabeza, _sep, resto = h.wfile.getvalue().partition(b"\r\n\r\n")
    return int(cabeza.split(b" ")[1]), resto
