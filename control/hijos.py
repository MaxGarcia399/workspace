"""WORKSPACE · control/hijos.py — los procesos hijos de la capa de control, por
conversación, para no dejar huérfanos.

Por qué (punto G, prueba real, 18-nov): si el servidor de la página muere a
media vuelta, el proceso del motor (p. ej. `claude -p --resume <id>`) queda
vivo, y el siguiente `--resume` de esa conversación se atora.

  · Cada motor arranca en su PROPIO grupo de procesos (canal.CanalProceso);
    cerrar() y control.apagar() matan el grupo entero (el motor y lo que corrió).
  · Mientras vive, el hijo queda anotado aquí: {motor, sesion, pid, pgid,
    dueno} (dueno = el pid del servidor que lo abrió).
  · abrir() de una conversación, y cada corrida de Claude Code, miran primero
    si hay un hijo anotado de ESA conversación cuyo dueño ya murió: si sigue
    vivo y sigue siendo el líder de su grupo, lo cierran (grupo entero) antes
    de seguir. Un hijo de un servidor VIVO no se toca.

Stdlib; nada aquí lee credenciales."""
import hashlib
import json
import os
import signal
import threading
import time

#: Carpeta del registro (None = <estado de la máquina>/control/hijos; las pruebas la cambian).
CARPETA = None


def _dir():
    d = CARPETA or os.environ.get("WORKSPACE_CONTROL_HIJOS")
    if not d:
        import paths
        d = os.path.join(paths.state_dir(), "control", "hijos")
    os.makedirs(d, exist_ok=True)
    return d


def _ruta(motor, sesion):
    h = hashlib.sha1(("%s\0%s" % (motor, sesion)).encode("utf-8")).hexdigest()[:16]
    return os.path.join(_dir(), "%s-%s.json" % (motor, h))


def _es_windows():
    return os.name == "nt"


def _win_proceso(pid):                                # pragma: no cover (solo Windows)
    """(vive, creado) de un pid en Windows, SIN señales: OpenProcess + GetExitCodeProcess (STILL_ACTIVE) y su hora
    de creación (GetProcessTimes), para no confundirlo con otro que reusó el número. (False, None) si no existe."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    h = k.OpenProcess(0x1000, False, int(pid))        # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return (ctypes.get_last_error() == 5), None   # sin acceso: existe, de otro usuario
    try:
        codigo = wintypes.DWORD()
        vive = bool(k.GetExitCodeProcess(h, ctypes.byref(codigo))) and codigo.value == 259
        tiempos = [wintypes.FILETIME() for _ in range(4)]
        creado = None
        if k.GetProcessTimes(h, *[ctypes.byref(t) for t in tiempos]):
            creado = (tiempos[0].dwHighDateTime << 32) | tiempos[0].dwLowDateTime
        return vive, creado
    finally:
        k.CloseHandle(h)


def creado(pid):
    """La hora de creación del proceso (Windows), o None: con ella un pid reciclado no se toma por el anotado."""
    if not _es_windows():
        return None
    try:
        return _win_proceso(pid)[1]
    except Exception:
        return None


def vivo(pid):
    """¿Vive ese proceso? En Windows NUNCA con os.kill(pid, 0): ahí la señal 0 es CTRL_C_EVENT y se manda un
    Ctrl+C a la consola (podía tumbar el servidor de la página) o se da por vivo cualquier pid."""
    if _es_windows():
        try:
            return bool(_win_proceso(pid)[0])
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True                                   # existe, aunque no sea nuestro
    except (OSError, ValueError, TypeError):
        return False


def _grupo(pid):
    if os.name == "nt":                               # pragma: no cover
        return int(pid)
    try:
        return os.getpgid(int(pid))
    except (OSError, ValueError, TypeError):
        return None


def matar_grupo(pid, pgid=None, gracia=2.0):
    """SIGTERM al grupo; si no se va en `gracia` s, SIGKILL. En Windows, el árbol."""
    pid = int(pid)
    if os.name == "nt":                               # pragma: no cover
        try:                                          # el árbol, como arbol_procesos.matar_arbol
            import subprocess
            import arbol_procesos
            subprocess.run([arbol_procesos._taskkill(), "/T", "/F", "/PID", str(pid)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10, **arbol_procesos._sin_ventana())
        except Exception:
            pass
        return
    pgid = pgid or _grupo(pid)
    if not pgid:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        return                                        # el grupo ya no existe
    limite = time.monotonic() + gracia
    while time.monotonic() < limite and vivo(pid):
        time.sleep(0.05)
    time.sleep(0.1)                                   # lo que el SIGTERM alcanzó a cerrar
    try:
        os.killpg(pgid, signal.SIGKILL)               # y lo que quede del grupo (no espera más)
    except OSError:
        pass


# ── Windows: el motor y lo que lance, en un Job Object ──────────────────────
# En Windows no hay grupos que matar enteros: taskkill /T recorre el árbol desde un padre VIVO, así que si el motor
# ya salió (lo hace al cerrarle la entrada) sus nietos quedaban vivos y, con la salida del motor todavía abierta en
# ellos, cerrar() se quedaba esperando a que murieran (visto en la PC: 120 s con el motor falso que deja un nieto).
# Con el motor en un trabajo propio, lo que lance queda adentro y se cierra entero, haya salido el motor o no.
#: LimitFlags del trabajo: un proceso que PIDE salirse puede (sin esto su CreateProcess fallaría) y, si este servidor
#: se cae de golpe, Windows cierra lo de adentro al soltarse el último handle (no se hereda: solo lo tiene él).
_JOB_BREAKAWAY_OK = 0x00000800
_JOB_KILL_ON_JOB_CLOSE = 0x00002000


def _win_kernel():                                    # pragma: no cover (solo Windows)
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k.SetInformationJobObject.restype = wintypes.BOOL
    k.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    k.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    k.TerminateJobObject.restype = wintypes.BOOL
    k.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k.CloseHandle.restype = wintypes.BOOL
    k.CloseHandle.argtypes = (wintypes.HANDLE,)
    return k


def _win_trabajo(proceso):                            # pragma: no cover (solo Windows)
    import ctypes
    from ctypes import wintypes

    class Basico(ctypes.Structure):                   # JOBOBJECT_BASIC_LIMIT_INFORMATION
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class Extendido(ctypes.Structure):                # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        _fields_ = [("BasicLimitInformation", Basico), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k = _win_kernel()
    job = k.CreateJobObjectW(None, None)
    if not job:
        return None
    ok = False
    try:
        info = Extendido()
        info.BasicLimitInformation.LimitFlags = _JOB_BREAKAWAY_OK | _JOB_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):   # ExtendedLimit
            return None
        ok = bool(k.AssignProcessToJobObject(job, proceso))
        return job if ok else None
    finally:
        if not ok:
            k.CloseHandle(job)


def trabajo_nuevo(proc):
    """Windows: mete a `proc` (el Popen de un motor recién lanzado por este servidor) en un Job Object propio y
    devuelve su handle; lo que lance después queda en el mismo trabajo. None en otro sistema o si no se pudo (queda
    el árbol de siempre). Se mete apenas arranca: lo que alcanzara a lanzar en ese instante queda fuera, y para eso
    sigue el árbol (canal.CanalProceso.cerrar). Solo con el handle PROPIO de un Popen de verdad, nunca por número de
    proceso: un doble de prueba con un pid cualquiera jamás mete a un proceso ajeno en el trabajo (al cerrarse lo
    mataría)."""
    if not _es_windows():
        return None
    try:
        import subprocess
        h = vars(proc).get("_handle")
        if not isinstance(h, getattr(subprocess, "Handle", ())):
            return None
        return _win_trabajo(int(h))
    except Exception:
        return None


def cerrar_trabajo(job):
    """Cierra todo lo que siga en el trabajo (el motor si no salió y lo que corrió) y suelta su handle."""
    if not job or not _es_windows():
        return
    try:                                              # pragma: no cover (solo Windows)
        k = _win_kernel()
        k.TerminateJobObject(job, 1)
        k.CloseHandle(job)
    except Exception:
        pass


def registrar(motor, sesion, pid):
    if not sesion or not pid:
        return
    ruta = _ruta(motor, sesion)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"motor": motor, "sesion": str(sesion), "pid": int(pid), "pgid": _grupo(pid),
                   "dueno": os.getpid(), "desde": time.time(), "creado": creado(pid)}, fh)
    os.replace(tmp, ruta)


def leer(motor, sesion):
    try:
        with open(_ruta(motor, sesion), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


#: Soltar desde dos hilos a la vez (el que cierra el conector y el que lee al motor, que terminan juntos) no debe
#: chocar consigo mismo: en Windows, borrar un archivo que otro tiene abierto falla por uso compartido.
_SOLTANDO = threading.Lock()
#: En Windows el borrado se reintenta un momento si alguien más (otro proceso, el antivirus) tiene abierta la
#: anotación justo entonces; si no, se quedaba anotada una corrida que ya terminó.
_REINTENTOS_WINDOWS = 20
_PAUSA_REINTENTO = 0.025


def _borrar(ruta, sigue=None):
    """Borra `ruta`. En Windows, si está abierta en ese instante, reintenta (mientras `sigue()`, si se da, diga que
    todavía es la misma anotación). → True si la borró."""
    for _ in range(_REINTENTOS_WINDOWS if _es_windows() else 1):
        if sigue is not None and not sigue():
            return False
        try:
            os.remove(ruta)
            return True
        except FileNotFoundError:
            return False
        except PermissionError:
            if not _es_windows():
                return False
            time.sleep(_PAUSA_REINTENTO)
        except OSError:
            return False
    return False


def soltar(motor, sesion, pid=None):
    """Borra la anotación (si es de ese pid, cuando se da)."""
    if not sesion:
        return

    def es_la_misma():
        d = leer(motor, sesion)
        return d is not None and (pid is None or d.get("pid") == pid)
    with _SOLTANDO:
        _borrar(_ruta(motor, sesion), es_la_misma)


def limpiar_huerfano(motor, sesion, gracia=2.0):
    """Si hay un hijo anotado de esta conversación cuyo dueño murió, lo cierra
    (grupo entero) y borra la anotación. Devuelve True si cerró uno."""
    if not sesion:
        return False
    d = leer(motor, sesion)
    if d is None:
        return False
    dueno = d.get("dueno")
    if dueno == os.getpid() or (dueno and vivo(dueno)):
        return False                                  # lo tiene un servidor vivo (o este)
    pid, pgid = d.get("pid"), d.get("pgid")
    cerrado = False
    # solo si sigue vivo Y sigue siendo el líder del grupo anotado (un pid reciclado, no). En Windows el grupo es
    # el mismo pid: ahí lo distingue su hora de creación (sin ella, no se toca: un taskkill /T /F a un ajeno, jamás)
    mismo = (not _es_windows()) or (d.get("creado") is not None and creado(pid) == d.get("creado"))
    if pid and vivo(pid) and pgid and _grupo(pid) == pgid == pid and mismo:
        matar_grupo(pid, pgid, gracia)
        cerrado = True
    with _SOLTANDO:
        _borrar(_ruta(motor, sesion))
    return cerrado
