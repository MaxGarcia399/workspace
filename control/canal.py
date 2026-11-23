"""WORKSPACE · control/canal.py — canales de mensajes de texto: uno por línea
sobre stdin/stdout de un proceso (ACP, app-server de Codex, stream-json de
Claude Code) o uno por trama de WebSocket (gateways). Misma forma para los dos:

    enviar(texto) · recibir() → texto | None (se cerró) · cerrar() · vivo()

`grabar(direccion, texto)` recibe el tráfico crudo (">" sale, "<" entra): el
probador lo guarda para ajustar los conectores con el motor real."""
import collections
import os
import shutil
import signal
import subprocess
import threading
import weakref

#: Una línea más grande que esto se descarta (un motor roto no llena la memoria).
MAX_LINEA = 16 * 1024 * 1024
#: Los procesos de motor abiertos por este servidor (control.apagar los cierra todos).
_VIVOS = weakref.WeakSet()


def cerrar_todos(espera=1.0):
    """Cierra (grupo entero) todo proceso de motor que siga abierto."""
    for c in list(_VIVOS):
        try:
            c.cerrar(espera=espera)
        except Exception:
            pass


def resolver(cmd):
    """El argv con el binario por su RUTA (shutil.which): en Windows los CLIs
    de npm son .cmd y el nombre suelto da FileNotFoundError. Si no está en
    PATH queda el nombre, y Popen explica el fallo."""
    cmd = list(cmd)
    if cmd and not os.path.dirname(cmd[0]):
        cmd[0] = shutil.which(cmd[0]) or cmd[0]
    return cmd


#: Windows (los valores de su API: en otro sistema `subprocess` no los trae).
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def opciones_proceso(windows=None):
    """Las opciones de Popen de un motor: su propio grupo (punto G: cerrar() lo mata entero, con lo que el motor
    corrió) y, en Windows, sin ventana: el servidor de la página corre sin consola y cada `claude -p`, cada chat
    ACP o cada servidor abría la suya, visible."""
    if os.name == "nt" if windows is None else windows:
        return {"creationflags": CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW}
    return {"start_new_session": True}


class CanalProceso:
    """Un proceso hijo con un mensaje por línea. stderr se guarda (lo último)
    para explicar un fallo, nunca se interpreta."""

    def __init__(self, cmd, cwd=None, env=None, grabar=None, stdin_abierto=True):
        self.cmd = resolver(cmd)
        self._grabar = grabar
        self._err = collections.deque(maxlen=60)
        self._envio = threading.Lock()
        kw = opciones_proceso()
        self.proc = subprocess.Popen(
            self.cmd, cwd=cwd, env=env, bufsize=0,
            stdin=subprocess.PIPE if stdin_abierto else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
        from control import hijos
        self._trabajo = hijos.trabajo_nuevo(self.proc)        # Windows: el motor y lo que lance (punto G)
        _VIVOS.add(self)
        t = threading.Thread(target=self._leer_err, name="control-stderr", daemon=True)
        t.start()

    def _leer_err(self):
        try:
            for linea in iter(self.proc.stderr.readline, b""):
                self._err.append(linea.decode("utf-8", "replace").rstrip())
        except (OSError, ValueError):
            pass

    def enviar(self, texto):
        if self._grabar:
            self._grabar(">", texto)
        with self._envio:
            self.proc.stdin.write(texto.encode("utf-8") + b"\n")
            self.proc.stdin.flush()

    def cerrar_entrada(self):
        try:
            self.proc.stdin.close()
        except (OSError, ValueError, AttributeError):
            pass

    def recibir(self):
        while True:
            try:
                linea = self.proc.stdout.readline(MAX_LINEA + 1)
            except (OSError, ValueError):
                return None
            if not linea:
                return None
            if len(linea) > MAX_LINEA:
                continue
            texto = linea.decode("utf-8", "replace").strip()
            if texto:
                if self._grabar:
                    self._grabar("<", texto)
                return texto

    def vivo(self):
        return self.proc.poll() is None

    def stderr(self, n=8):
        return " | ".join(list(self._err)[-n:])

    def senal_interrumpir(self):
        """SIGINT (Ctrl+C): el corte «de usuario» que los motores documentan."""
        if not self.vivo():
            return
        try:
            if os.name == "nt":                                # pragma: no cover
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(self.proc.pid, signal.SIGINT)       # al grupo, como Ctrl+C en una terminal
        except OSError:
            pass

    def cerrar(self, espera=3.0):
        """Deja que el motor termine solo (`espera` s, con stdin cerrado) y
        después cierra su GRUPO entero, aunque el motor ya haya salido y deje
        hijos colgados (punto G)."""
        self.cerrar_entrada()
        if self.vivo():
            try:
                self.proc.wait(timeout=espera)
            except subprocess.TimeoutExpired:
                pass
        from control import hijos
        if os.name == "nt":                                    # pragma: no cover
            trabajo, self._trabajo = self._trabajo, None
            hijos.cerrar_trabajo(trabajo)                      # todo lo del motor, aunque él ya haya salido
            if self.vivo():                                    # sin trabajo (no se pudo): el árbol, como antes
                import arbol_procesos
                arbol_procesos.matar_arbol(self.proc)
        else:
            hijos.matar_grupo(self.proc.pid, self.proc.pid, gracia=espera)
        try:
            self.proc.wait(timeout=espera)
        except subprocess.TimeoutExpired:                      # pragma: no cover
            pass
        _VIVOS.discard(self)
        self._cerrar_salidas(espera)

    def _cerrar_salidas(self, espera):
        """Cierra stdout y stderr. En Windows, en otro hilo y con tope: cerrarlas espera a que su hilo lector
        suelte la lectura, y esa no termina mientras algo fuera del alcance de cerrar() (un proceso que pidió
        salirse del trabajo) siga con ellas abiertas; la página no se queda colgada por eso."""
        def cerrar():
            for f in (self.proc.stdout, self.proc.stderr):
                try:
                    f.close()
                except (OSError, ValueError, AttributeError):
                    pass
        if os.name != "nt":
            cerrar()
            return
        h = threading.Thread(target=cerrar, name="control-cerrar-salidas", daemon=True)   # pragma: no cover
        h.start()
        h.join(max(1.0, espera))


class CanalWS:
    """Un WebSocket ya conectado (control.ws.ConexionWS): un mensaje por trama."""

    def __init__(self, conexion, grabar=None):
        self.ws = conexion
        self._grabar = grabar

    def enviar(self, texto):
        if self._grabar:
            self._grabar(">", texto)
        self.ws.enviar(texto)

    def recibir(self):
        texto = self.ws.recibir()
        if texto is not None and self._grabar:
            self._grabar("<", texto)
        return texto

    def vivo(self):
        return not self.ws.cerrada

    def stderr(self, n=8):
        return ""

    def cerrar(self, espera=3.0):
        self.ws.cerrar()
