"""WORKSPACE · control/sse.py — lector de eventos SSE robusto, stdlib, sin
http.client.

Por qué (VERIFICADO con el probador real, OpenCode v2.1.4, 18-nov): leyendo
/api/event con http.client, el cuerpo chunked se cortó y `readline()` reventó
DENTRO de http.client (`_read_next_chunk_size`: ValueError b'' y después
`fp.close()` sobre None, AttributeError). Esas excepciones no son de red, así
que mataban el hilo sin avisar. Este lector:
  · habla HTTP/1.1 directo sobre el socket y decodifica chunked a mano;
  · un corte, un chunk mal formado o cualquier excepción terminan ESA conexión,
    nunca el hilo;
  · reconecta solo (con pausa creciente) hasta `reintentos` fallos seguidos;
    un fallo cuenta solo si la conexión no alcanzó a traer ningún evento;
  · `cerrar()` lo detiene sin que cuente como fallo.
Si el servidor contesta otra cosa que 200 en la primera conexión, no reintenta:
`fallo` dice el estado, el WWW-Authenticate y el comienzo del cuerpo."""
import socket
import threading


def leer_cabeceras(f):
    """(estado, motivo, {cabecera en minúsculas: valor}) de una respuesta HTTP."""
    primera = f.readline().decode("latin-1").strip()
    partes = primera.split(" ", 2)
    if len(partes) < 2 or not partes[0].startswith("HTTP/"):
        raise ValueError("respuesta HTTP inválida: %r" % primera[:80])
    hs = {}
    while True:
        ln = f.readline()
        if not ln or ln in (b"\r\n", b"\n"):
            break
        k, _, v = ln.decode("latin-1").partition(":")
        hs[k.strip().lower()] = v.strip()
    return int(partes[1]), (partes[2] if len(partes) > 2 else ""), hs


def lineas(f, chunked):
    """Las líneas (bytes) del cuerpo. Con chunked, decodifica a mano; un tamaño
    vacío o ilegible, o el fin del socket, terminan el cuerpo sin excepción."""
    if not chunked:
        for crudo in iter(f.readline, b""):
            yield crudo
        return
    resto = b""
    while True:
        tam = f.readline()
        if not tam:
            break
        tam = tam.split(b";", 1)[0].strip()
        try:
            n = int(tam, 16)
        except ValueError:
            break
        if n == 0:
            break
        datos = f.read(n)
        resto += datos
        while b"\n" in resto:
            ln, resto = resto.split(b"\n", 1)
            yield ln + b"\n"
        if len(datos) < n:
            break
        f.readline()                                   # el CRLF que cierra el chunk
    if resto:
        yield resto


def eventos(lineas_crudas):
    """Los `data:` de cada evento SSE (texto), uno por evento. Como dice la
    especificación de SSE, lo que quede sin su línea en blanco al cortarse el
    stream se descarta (sería un evento a medias)."""
    datos = []
    for crudo in lineas_crudas:
        ln = crudo.decode("utf-8", "replace").rstrip("\r\n")
        if ln.startswith("data:"):
            datos.append(ln[5:].lstrip())
        elif not ln and datos:
            yield "\n".join(datos)
            datos = []


class LectorSSE:
    def __init__(self, abrir_socket, host, ruta, cabeceras=None, reintentos=5, pausa=0.5,
                 grabar=None):
        self._abrir_socket = abrir_socket
        hs = dict({"Host": host, "Accept": "text/event-stream", "Cache-Control": "no-cache"},
                  **(cabeceras or {}))
        self._peticion = ("GET %s HTTP/1.1\r\n" % ruta + "".join(
            "%s: %s\r\n" % kv for kv in hs.items()) + "\r\n").encode("latin-1")
        self.reintentos = reintentos
        self.pausa = pausa
        self._grabar = grabar
        self._detener = threading.Event()
        self._sock = None
        self._f = None                            # el makefile de la conexión de ahora (ver _cerrar_socket)
        self.conectado = threading.Event()        # la primera conexión ya contestó (bien o mal)
        self.aceptado = False                     # …y con 200
        self.fallo = ""
        self.reconexiones = 0
        self.conexiones = 0                       # las que contestaron 200
        self._espera_extra = 0.0                  # cortar(espera): lo que espera la próxima reconexión

    def correr(self, al_evento, al_reconectar=None, al_conectar=None):
        """Bloquea (en su hilo). Devuelve por qué terminó: «cerrado» (cerrar()),
        «rechazado» (la primera conexión no dio 200) o «perdido» (se agotaron los
        reintentos). `al_conectar(n)`: cada conexión aceptada, antes de leer sus
        eventos (n = 0 la primera, 1… las que vuelven tras un corte: lo que pasó en el
        hueco no llega, porque no hay Last-Event-ID)."""
        fallos = 0
        while not self._detener.is_set():
            vistos = 0
            try:
                sock = self._abrir_socket()
                self._sock = sock
                if self._detener.is_set():
                    break
                sock.sendall(self._peticion)
                f = self._f = sock.makefile("rb")
                estado, motivo, hs = leer_cabeceras(f)
                if self._grabar:
                    self._grabar("<", "%s %s (eventos)" % (estado, motivo))
                if estado != 200:
                    cuerpo = b""
                    try:
                        cuerpo = f.read1(300) if hasattr(f, "read1") else b""
                    except (OSError, ValueError):
                        pass
                    auth = hs.get("www-authenticate")
                    self.fallo = "HTTP %s %s%s%s" % (
                        estado, motivo, "; WWW-Authenticate: " + auth if auth else "",
                        ": " + cuerpo.decode("utf-8", "replace").strip() if cuerpo.strip() else "")
                    if not self.aceptado:
                        self.conectado.set()
                        return "rechazado"
                    raise OSError(self.fallo)
                self.aceptado = True
                self.conectado.set()
                self.conexiones += 1
                if al_conectar:
                    try:
                        al_conectar(self.conexiones - 1)
                    except Exception:
                        pass
                chunked = "chunked" in hs.get("transfer-encoding", "").lower()
                for texto in eventos(lineas(f, chunked)):
                    vistos += 1
                    if self._grabar:
                        self._grabar("<", texto)
                    try:
                        al_evento(texto)
                    except Exception:                  # un evento raro no tumba al lector
                        pass
                self.fallo = "el servidor cerró los eventos"
            except Exception as e:                     # red, chunked roto, lo que sea
                self.fallo = "%s: %s" % (type(e).__name__, e)
            finally:
                self._cerrar_socket()
            if self._detener.is_set():
                break
            if not self.aceptado:
                self.conectado.set()
                return "rechazado"
            fallos = 0 if vistos else fallos + 1
            if fallos > self.reintentos:
                return "perdido"
            self.reconexiones += 1
            if al_reconectar:
                try:
                    al_reconectar(self.reconexiones, self.fallo)
                except Exception:
                    pass
            extra, self._espera_extra = self._espera_extra, 0.0
            self._detener.wait(self.pausa * max(1, fallos) + extra)
        return "cerrado"

    def cortar(self, espera=0.0):
        """Corta la conexión de ahora como un corte de red; la siguiente se intenta tras
        `espera` s más. Para el probador real: abre un hueco en los eventos."""
        self._espera_extra = max(0.0, float(espera))
        self._cerrar_socket()

    def _cerrar_socket(self):
        """Corta la conexión de ahora y despierta al hilo que lee. En POSIX basta shutdown(); en Windows no: un recv
        bloqueado en otro hilo solo vuelve cuando el socket se cierra DE VERDAD, y con su makefile abierto
        sock.close() no lo cierra (Python espera a que se cierre el makefile). Por eso también se cierra el crudo
        del makefile: así cortar() y cerrar() valen al momento y no hasta el siguiente evento del servidor."""
        sock, self._sock = self._sock, None
        f, self._f = self._f, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if f is not None:
            try:
                f.raw.close()
            except (OSError, ValueError, AttributeError):
                pass

    def cerrar(self):
        self._detener.set()
        self._cerrar_socket()


def abrir_tcp(host, puerto, timeout=10):
    """El socket por defecto: TCP a host:puerto, sin límite de lectura (un
    stream SSE puede callar mucho rato)."""
    def abrir():
        s = socket.create_connection((host, puerto), timeout=timeout)
        s.settimeout(None)
        return s
    return abrir
