"""WORKSPACE · control/ws.py — cliente WebSocket mínimo (RFC 6455), stdlib.

Solo lo que piden los gateways locales: el saludo HTTP, tramas de texto (el
cliente enmascara, el servidor no), fragmentos, ping/pong y cierre. Sin TLS
(los gateways escuchan en 127.0.0.1) y sin extensiones.

`conectar(url, cabeceras, sock=None)`: `sock` permite pasarle un socket ya
abierto (las pruebas usan un socketpair, porque el sandbox no deja escuchar
puertos). `ConexionWS(sock, enmascarar=False)` sirve también para el lado
servidor del motor falso."""
import base64
import hashlib
import os
import socket
import struct
import threading
from urllib.parse import urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MENSAJE = 32 * 1024 * 1024


class ErrorWS(Exception):
    pass


def aceptacion(clave):
    """El Sec-WebSocket-Accept que corresponde a una Sec-WebSocket-Key."""
    return base64.b64encode(hashlib.sha1((clave + GUID).encode("ascii")).digest()).decode("ascii")


def leer_cabeceras(sock, tope=65536):
    """Lee hasta el fin de las cabeceras HTTP. Devuelve (primera línea,
    {cabecera en minúsculas: valor}, lo que sobró después)."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        trozo = sock.recv(4096)
        if not trozo:
            raise ErrorWS("se cerró durante el saludo")
        buf += trozo
        if len(buf) > tope:
            raise ErrorWS("saludo demasiado grande")
    cab, resto = buf.split(b"\r\n\r\n", 1)
    lineas = cab.decode("latin-1").split("\r\n")
    hs = {}
    for ln in lineas[1:]:
        if ":" in ln:
            k, v = ln.split(":", 1)
            hs[k.strip().lower()] = v.strip()
    return lineas[0], hs, resto


class ConexionWS:
    def __init__(self, sock, enmascarar=True, sobrante=b""):
        self.sock = sock
        self._enmascarar = enmascarar
        self._buf = sobrante
        self._envio = threading.Lock()
        self.cerrada = False

    # ── tramas ──────────────────────────────────────────────────────────────
    def _trama(self, opcode, datos):
        cab = bytes([0x80 | opcode])
        n = len(datos)
        bit = 0x80 if self._enmascarar else 0
        if n < 126:
            cab += bytes([bit | n])
        elif n < 65536:
            cab += bytes([bit | 126]) + struct.pack("!H", n)
        else:
            cab += bytes([bit | 127]) + struct.pack("!Q", n)
        if self._enmascarar:
            mascara = os.urandom(4)
            datos = bytes(b ^ mascara[i % 4] for i, b in enumerate(datos))
            cab += mascara
        with self._envio:
            self.sock.sendall(cab + datos)

    def _leer(self, n):
        while len(self._buf) < n:
            trozo = self.sock.recv(65536)
            if not trozo:
                raise ErrorWS("conexión cerrada")
            self._buf += trozo
        datos, self._buf = self._buf[:n], self._buf[n:]
        return datos

    def _siguiente_trama(self):
        b0, b1 = self._leer(2)
        fin, opcode = bool(b0 & 0x80), b0 & 0x0F
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack("!H", self._leer(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", self._leer(8))[0]
        if n > MAX_MENSAJE:
            raise ErrorWS("trama demasiado grande")
        mascara = self._leer(4) if b1 & 0x80 else None
        datos = self._leer(n)
        if mascara:
            datos = bytes(b ^ mascara[i % 4] for i, b in enumerate(datos))
        return fin, opcode, datos

    # ── mensajes ────────────────────────────────────────────────────────────
    def enviar(self, texto):
        if self.cerrada:
            raise ErrorWS("conexión cerrada")
        self._trama(0x1, texto.encode("utf-8"))

    def recibir(self):
        """El próximo mensaje de texto, o None si se cerró."""
        partes = []
        try:
            while True:
                fin, opcode, datos = self._siguiente_trama()
                if opcode == 0x8:                      # cierre: se contesta y se acaba
                    self._cerrar_socket(responder=True)
                    return None
                if opcode == 0x9:                      # ping → pong
                    self._trama(0xA, datos)
                    continue
                if opcode == 0xA:
                    continue
                if opcode in (0x0, 0x1, 0x2):
                    partes.append(datos)
                    if sum(len(p) for p in partes) > MAX_MENSAJE:
                        raise ErrorWS("mensaje demasiado grande")
                    if fin:
                        return b"".join(partes).decode("utf-8", "replace")
        except (ErrorWS, OSError, ValueError):
            self.cerrada = True
            return None

    def _cerrar_socket(self, responder=False):
        if not self.cerrada and responder:
            try:
                self._trama(0x8, b"")
            except OSError:
                pass
        self.cerrada = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def cerrar(self):
        self._cerrar_socket(responder=True)


def conectar(url, cabeceras=None, sock=None, timeout=10, subprotocolos=None):
    """Abre `ws://host:puerto/ruta` (o usa `sock`) y hace el saludo.
    `subprotocolos`: los que se ofrecen en Sec-WebSocket-Protocol."""
    if subprotocolos:
        cabeceras = dict(cabeceras or {}, **{"Sec-WebSocket-Protocol": ", ".join(subprotocolos)})
    p = urlsplit(url)
    if p.scheme != "ws":
        raise ErrorWS("solo ws:// local (sin TLS): %s" % url)
    host = p.hostname or "127.0.0.1"
    puerto = p.port or 80
    ruta = (p.path or "/") + ("?" + p.query if p.query else "")
    if sock is None:
        sock = socket.create_connection((host, puerto), timeout=timeout)
    clave = base64.b64encode(os.urandom(16)).decode("ascii")
    lineas = ["GET %s HTTP/1.1" % ruta, "Host: %s:%s" % (host, puerto), "Upgrade: websocket",
              "Connection: Upgrade", "Sec-WebSocket-Key: " + clave, "Sec-WebSocket-Version: 13"]
    for k, v in (cabeceras or {}).items():
        lineas.append("%s: %s" % (k, v))
    sock.sendall(("\r\n".join(lineas) + "\r\n\r\n").encode("latin-1"))
    primera, hs, resto = leer_cabeceras(sock)
    if " 101 " not in primera + " ":
        # Lo que diga el servidor (estado, cómo autenticarse, el comienzo del cuerpo)
        # es lo que hace falta para ajustar el conector.
        auth = hs.get("www-authenticate")
        cuerpo = resto[:200].decode("utf-8", "replace").strip()
        raise ErrorWS("el servidor no aceptó el WebSocket: %s%s%s" % (
            primera, "; WWW-Authenticate: " + auth if auth else "", ": " + cuerpo if cuerpo else ""))
    if hs.get("sec-websocket-accept") != aceptacion(clave):
        raise ErrorWS("Sec-WebSocket-Accept no coincide")
    sock.settimeout(None)
    return ConexionWS(sock, enmascarar=True, sobrante=resto)
