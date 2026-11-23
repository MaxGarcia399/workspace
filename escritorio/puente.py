#!/usr/bin/env python3
"""WORKSPACE · escritorio/puente — el puente entre la app del monito (escritorio/mac) y la página local (/api/v2).

La app lo corre como proceso hijo y le habla por líneas de JSON:
  · stdin  ← lo que haces en el monito: {"op": "mandar"|"responder"|"permiso"|"elegir"|"terminal"|"parar"|"contexto"|
             "abrir"|"seguir"|"adjuntar", …}. `mandar` puede traer `contexto` (lo que tenías enfrente: la app de la Mac
             lo toma al abrir la barra) y `sin_contexto` (lo quitaste con la ✕ del chip).
  · stdout → lo que el monito pinta: {"t": "agentes"|"estado"|"parcial"|"respuesta"|"fin"|"pregunta"|"permiso"|"uso"|
             "aviso"|"contexto"|"seguido"|"adjunto", …}
Modo escritorio: todo va a la conversación del ESCRITORIO de cada agente (canal «escritorio»), no a la de la página.
La lógica vive en escritorio/cliente.Puente (probada con dobles); aquí solo los dos hilos: leer lo que llega y
escuchar /api/v2/vivo. Si la página se apaga o cambia de puerto, el monito se duerme y se reconecta solo.

    python3 escritorio/puente.py            (lo lanza la app)
    python3 escritorio/puente.py --probar   (sin app: imprime los eventos; escribe ops en JSON por la entrada)
Stdlib."""
import json
import os
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
from escritorio import cliente as C  # noqa: E402

_SALIDA = threading.Lock()
SIN_PAGINA = "No encuentro la página local de Workspace. La estoy prendiendo…"
DORMIDO = "Perdí la conexión con Workspace. Me reconecto solo en cuanto vuelva."


def al_reventar(tipo, valor, _tb=None, hilo=""):
    """E14: una excepción que nadie atrapó (en cualquier hilo) queda en app.log, en una línea."""
    C.anotar("reventó%s: %s: %s" % ((" el hilo «%s»" % hilo) if hilo else "", getattr(tipo, "__name__", tipo), valor))


def emitir(ev):
    if ev.get("t") == "aviso" and ev.get("grave") and ev.get("texto"):
        C.anotar("aviso: %s" % ev["texto"])            # E14: lo grave que ve el socio también queda escrito
    with _SALIDA:
        try:
            sys.stdout.write(json.dumps(ev, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except (BrokenPipeError, ValueError):
            os._exit(0)                               # la app se cerró


class Bucle:
    def __init__(self):
        self.lock = threading.RLock()
        self.p = None
        self.vivo = True

    def conectar(self, lanzar):
        srv = C.conectar(lanzar=lanzar)
        if srv is None:
            return False
        with self.lock:
            elegido = (self.p.elegido if self.p else "") or C.leer_elegido()
            self.p = C.Puente(srv, emitir, recordar=C.guardar_elegido)
            try:
                self.p.arrancar(elegido)
            except C.PaginaSinCanal as e:
                # una página de otra versión: no se mezcla con su conversación; lo dice y vuelve a mirar después
                self.p = None
                emitir({"t": "aviso", "grave": True, "duerme": True, "texto": e.texto})
                return None
            except C.ErrorServidor:
                self.p = None
                return False
        return True

    def escuchar(self):
        """El long-poll de /api/v2/vivo, como la página y el hub."""
        espera, fallos = 0, 0
        while self.vivo:
            if self.p is None:
                hecho = self.conectar(lanzar=fallos == 0)
                if not hecho:
                    if fallos == 0 and hecho is not None:      # None: hay página, pero de otra versión (ya lo dijo)
                        emitir({"t": "aviso", "grave": True, "duerme": True, "texto": SIN_PAGINA})
                    fallos += 1
                    time.sleep(min(10, 1 + fallos))
                    continue
                emitir({"t": "aviso", "texto": ""})
                fallos, espera = 0, 0
            try:
                d = self.p.vivo(espera)
            except C.ErrorServidor:
                emitir({"t": "aviso", "grave": True, "duerme": True, "texto": DORMIDO})
                with self.lock:
                    self.p = None
                fallos = 1
                time.sleep(2)
                continue
            with self.lock:
                espera = self.p.al_vivo(d) if self.p else 0

    def leer(self):
        for linea in sys.stdin:
            linea = linea.strip()
            if not linea:
                continue
            try:
                op = json.loads(linea)
            except ValueError:
                continue
            if not isinstance(op, dict):
                continue
            with self.lock:
                if self.p is not None:
                    self.p.comando(op)
                elif op.get("op") in ("mandar", "responder", "permiso"):
                    emitir({"t": "aviso", "grave": True, "duerme": True, "texto": DORMIDO})
        self.vivo = False
        os._exit(0)                                   # se cerró la entrada: la app ya no está


def main(argv=None):
    sys.excepthook = al_reventar
    threading.excepthook = lambda a: al_reventar(a.exc_type, a.exc_value, a.exc_traceback,
                                                  hilo=getattr(a.thread, "name", ""))
    C.anotar("puente arriba · pid %d · copia %s" % (os.getpid(), RAIZ))
    b = Bucle()
    threading.Thread(target=b.escuchar, name="vivo", daemon=True).start()
    b.leer()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
