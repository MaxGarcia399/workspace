#!/usr/bin/env python3
"""WORKSPACE · olock — write-lock file-based cross-platform (N8).

Robo OpenClaw R4 + tick-lock de Hermes (convergencia ×2): un helper de
exclusión mutua entre PROCESOS para proteger escrituras a archivos compartidos
(sidecars de uso N12, consolidador N1/N3, cualquier estado que dos sesiones
puedan tocar a la vez). Stdlib puro (3.9+), Mac/Windows/Linux, amputable:
nadie lo importa hasta que un consumidor lo integra.

API:
    from olock import file_lock, LockTimeout

    with file_lock("/ruta/al/archivo.json", timeout=5):
        ...leer-modificar-escribir el archivo...

El lock vive en un archivo HERMANO `<path>.lock` — jamás se bloquea el archivo
de datos en sí (así los lectores nunca se topan con un handle bloqueado y el
.lock se puede gitignorar aparte del dato).

Dos estrategias, en orden:

1. **OS-level (preferida):** `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows)
   sobre un fd abierto del .lock. El kernel libera el lock SOLO cuando el
   proceso muere o lo suelta → un proceso muerto NUNCA deja un lock atorado.
   El archivo .lock persiste vacío/con holder info tras soltarse (borrarlo
   abriría la carrera clásica flock-sobre-inode-huérfano — NO lo borres).
2. **Fallback (atómico por existencia):** si el módulo de locking no existe en
   la plataforma, `os.open(O_CREAT|O_EXCL)` — existencia del .lock = lock
   tomado; contiene JSON `{pid, host, time}`. Locks muertos se detectan por
   PID (mismo host, proceso inexistente) o por edad (`stale` segundos sin
   refresco) y se rompen con un takeover race-safe (os.replace a nombre único:
   si dos detectan stale a la vez, solo uno gana el rename).

Reglas de uso:
- Secciones críticas CORTAS (incrementos JSON, appends): milisegundos. En modo
  fallback un lock vivo más viejo que `stale` se considera muerto.
- No es reentrante: el mismo proceso que pide dos veces el mismo lock se
  bloquea contra sí mismo (y agota el timeout). Un lock por operación.
- Best-effort honesto: si no se puede adquirir dentro de `timeout`, levanta
  `LockTimeout` (subclase de TimeoutError) — el llamador decide (saltar la
  escritura, reintentar, reportar). Jamás corrompe: o tienes el lock o no.
"""
import json
import os
import socket
import time

# ── estrategia OS-level: flock (POSIX) / msvcrt.locking (Windows) ──────────
# Tests pueden parchear _os_lock/_os_unlock a None para ejercitar el fallback.
try:
    import fcntl

    def _os_lock(fd):
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _os_unlock(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)
except ImportError:                                   # Windows
    try:
        import msvcrt

        # En Windows msvcrt.locking es MANDATORIO: bloquear el byte 0 (donde vive
        # el holder JSON) impediría a holder_info releer el .lock desde otro
        # handle. Bloqueamos un byte CENTINELA muy lejos del inicio (vale más
        # allá de EOF y no se materializa), así el lock y el holder no se pisan.
        _LOCK_OFFSET = 10 ** 9

        def _os_lock(fd):
            os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)    # byte centinela > cualquier holder

        def _os_unlock(fd):
            os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except ImportError:                               # plataforma exótica
        _os_lock = _os_unlock = None


class LockTimeout(TimeoutError):
    """No se pudo adquirir el lock dentro del timeout. El dato NO se tocó."""


DEFAULT_TIMEOUT = 10.0      # segundos esperando adquirir
DEFAULT_STALE = 15 * 60     # fallback: lock sin refresco por 15 min = muerto
DEFAULT_POLL = 0.1          # intervalo de reintento


def lock_path(path):
    """Ruta del archivo de lock hermano de `path` (`<path>.lock`)."""
    return str(path) + ".lock"


def _holder_blob():
    return json.dumps({"pid": os.getpid(), "host": _hostname(),
                       "time": time.time()}).encode("utf-8")


def _hostname():
    try:
        return socket.gethostname() or "?"
    except Exception:
        return "?"


def _pid_alive(pid):
    """True/False si se puede saber; None = desconocido (no romper por PID).

    En Windows NO usar os.kill(pid, 0): con sig≠CTRL_* llama TerminateProcess
    (mataría al holder). Ahí devolvemos None y la staleness decide por mtime.
    """
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == "nt":
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True             # existe, es de otro usuario
    except OSError:
        return None


def holder_info(path):
    """Contenido del .lock de `path` ({pid, host, time}) o None — diagnóstico.
    Solo es fuente de verdad en modo fallback; en modo OS es informativo."""
    try:
        with open(lock_path(path), "r", encoding="utf-8") as fh:
            data = json.loads(fh.read() or "{}")
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


# ── adquisición OS-level ────────────────────────────────────────────────────
def _acquire_os(lp, deadline, poll):
    while True:
        fd = os.open(lp, os.O_CREAT | os.O_RDWR)
        try:
            _os_lock(fd)
        except OSError:
            os.close(fd)
            if time.monotonic() >= deadline:
                raise LockTimeout("lock ocupado: %s" % lp)
            time.sleep(poll)
            continue
        try:                    # anotar holder (informativo; el lock es el fd)
            os.lseek(fd, 0, os.SEEK_SET)   # tras _os_lock el cursor quedó en el centinela
            os.ftruncate(fd, 0)
            os.write(fd, _holder_blob())
        except OSError:
            pass
        return fd


def _release_os(fd):
    try:
        _os_unlock(fd)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass
    # NO borrar el .lock: unlink + flock = carrera de inode huérfano.


# ── adquisición fallback (existencia = lock) ───────────────────────────────
def _is_stale(lp, stale):
    info = None
    try:
        with open(lp, "r", encoding="utf-8") as fh:
            info = json.loads(fh.read() or "{}")
    except (OSError, ValueError):
        info = None
    if isinstance(info, dict) and info.get("host") == _hostname():
        alive = _pid_alive(info.get("pid"))
        if alive is False:
            return True         # mismo host, proceso muerto → muerto seguro
        if alive is True:
            pass                # vivo: solo la edad lo puede declarar colgado
    try:
        age = time.time() - os.path.getmtime(lp)
    except OSError:
        return False            # desapareció: que el loop reintente O_EXCL
    return age > stale


def _break_stale(lp):
    """Takeover race-safe: rename a nombre único — si dos procesos detectan
    stale a la vez, solo uno gana el os.replace; el otro reintenta O_EXCL."""
    grave = "%s.stale-%d" % (lp, os.getpid())
    try:
        os.replace(lp, grave)
        os.unlink(grave)
    except OSError:
        pass


def _acquire_excl(lp, deadline, poll, stale):
    while True:
        try:
            fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _is_stale(lp, stale):
                _break_stale(lp)
                continue
            if time.monotonic() >= deadline:
                raise LockTimeout("lock ocupado: %s" % lp)
            time.sleep(poll)
            continue
        try:
            os.write(fd, _holder_blob())
        except OSError:
            pass
        finally:
            os.close(fd)
        return


def _release_excl(lp):
    try:
        os.unlink(lp)           # existencia = lock → soltar SÍ borra
    except OSError:
        pass


# ── API pública ─────────────────────────────────────────────────────────────
class file_lock(object):
    """Context manager: `with file_lock(path, timeout=...):` — lock exclusivo
    inter-proceso sobre `<path>.lock`. Levanta LockTimeout si no se adquiere.
    `stale` y `poll` solo aplican al modo fallback / espera respectivamente."""

    def __init__(self, path, timeout=DEFAULT_TIMEOUT, stale=DEFAULT_STALE,
                 poll=DEFAULT_POLL):
        self.path = str(path)
        self.timeout = max(float(timeout), 0.0)
        self.stale = float(stale)
        self.poll = max(float(poll), 0.01)
        self._fd = None
        self._mode = None

    def __enter__(self):
        lp = lock_path(self.path)
        parent = os.path.dirname(os.path.abspath(lp))
        os.makedirs(parent, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        if _os_lock is not None:
            self._mode = "os"
            self._fd = _acquire_os(lp, deadline, self.poll)
        else:
            self._mode = "excl"
            _acquire_excl(lp, deadline, self.poll, self.stale)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._mode == "os" and self._fd is not None:
            _release_os(self._fd)
        elif self._mode == "excl":
            _release_excl(lock_path(self.path))
        self._fd = None
        self._mode = None
        return False            # jamás tragar excepciones del bloque
