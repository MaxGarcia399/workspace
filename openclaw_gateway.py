"""WORKSPACE · openclaw_gateway.py — el gateway de OpenClaw del perfil
de Workspace: UN dueño del estado y cada pestaña como cliente.

Por qué (VERIFICADO 2026.9.33 en Windows, 2026-10-16): `tui --local` exige ser
el dueño EXCLUSIVO del estado del perfil («Local mode requires exclusive
ownership of the configured state directory», docs/cli/tui.md). Con una
pestaña abierta, cualquier otra (otro agente u otra pestaña del mismo) falla
con «state database is busy». La 2026.5.12 no tenía ese candado. El camino
oficial para varias ventanas es el gateway: un proceso por perfil, dueño del
estado, y cada `tui` (sin --local) conectado a él.

Ciclo de vida (en el estado de WORKSPACE, jamás en el de OpenClaw):
  · cada pestaña se anota (pid + hora de creación del proceso) al abrir y se
    borra al cerrar;
  · si no hay gateway, la pestaña lanza al GUARDIÁN (este archivo como script,
    desacoplado de la ventana), que enciende `openclaw gateway run` y lo vigila;
  · el guardián lo apaga cuando no queda ninguna pestaña VIVA durante GRACE s.
    Así no queda encendido aunque la ventana se cierre de golpe (en Windows,
    cerrar la ventana no deja correr el cierre de la pestaña).
Memoria medida en Windows: cada `tui --local` ≈ 1.6 GB; con gateway, ≈ 1.6 GB
una vez + ≈ 260 MB por pestaña.

Stdlib (3.9+), Mac/Windows/Linux, falla-suave: nada aquí lee credenciales."""
import json
import os
import re
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#: Segundos sin pestañas vivas antes de apagar (cerrar y reabrir es instantáneo).
GRACE = 45
#: Cada cuánto revisa el guardián.
POLL = 3
#: El gateway espera hasta 300 s a que otro proceso suelte el estado.
START_TIMEOUT = 330
#: Una anotación cuyo pid no se puede comprobar se conserva este tiempo.
_UNKNOWN_TTL = 12 * 3600
#: Un «estoy lanzando al guardián» sin guardián después de esto es un fallo.
_SPAWN_TTL = 25
#: Línea VERIFICADA (2026.9.33) del gateway cuando otra ventana `--local` tiene
#: el perfil: «waiting for Gateway state ownership held by another OpenClaw
#: process, up to 300 s».
OWNERSHIP_WAIT = "waiting for Gateway state ownership"
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# ── archivos de estado ──────────────────────────────────────────────────────
def _safe(profile):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(profile or "workspace"))


def state_path(profile):
    import paths
    return os.path.join(paths.state_dir(), "openclaw-gateway-%s.json" % _safe(profile))


def log_path(profile):
    import paths
    return os.path.join(paths.state_dir(), "openclaw-gateway-%s.log" % _safe(profile))


def _load(profile):
    try:
        with open(state_path(profile), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _update(profile, fn):
    """Leer-modificar-escribir bajo candado entre procesos. Devuelve lo que
    devuelva `fn(d)`."""
    from olock import file_lock
    path = state_path(profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with file_lock(path, timeout=10):
        d = _load(profile)
        before = json.dumps(d, sort_keys=True)
        out = fn(d)
        if json.dumps(d, sort_keys=True) != before:
            tmp = "%s.%d.tmp" % (path, os.getpid())
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False)
            os.replace(tmp, path)
    return out


# ── procesos: vivo + huella (para no confundir un pid reciclado) ────────────
#: Holgura (s) entre la hora de inicio de un proceso y la de su anotación.
_START_SLACK = 5.0
_LIBC = {}


def _darwin_libc():
    if "libc" not in _LIBC:
        import ctypes
        import ctypes.util
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.dylib", use_errno=True)
        libc.sysctl.argtypes = (ctypes.POINTER(ctypes.c_int), ctypes.c_uint, ctypes.c_void_p,
                                ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p, ctypes.c_size_t)
        libc.sysctlbyname.argtypes = (ctypes.c_char_p, ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.c_size_t), ctypes.c_void_p,
                                      ctypes.c_size_t)
        _LIBC["libc"] = libc
    return _LIBC["libc"]


def _posix_proc(pid):
    """POSIX: {"start": hora de inicio (epoch), "zombie": bool}; {} si el pid
    no existe; None si este sistema no deja saberlo (se usa os.kill).
    Mac: sysctl KERN_PROC_PID (struct kinfo_proc: p_starttime en 0, p_stat
    en 36, p_pid en 40 — si el pid leído no cuadra, None). Linux: /proc."""
    import struct
    try:
        if sys.platform == "darwin":
            import ctypes
            libc = _darwin_libc()
            mib = (ctypes.c_int * 4)(1, 14, 1, pid)       # CTL_KERN, KERN_PROC, KERN_PROC_PID
            buf = ctypes.create_string_buffer(1024)
            size = ctypes.c_size_t(1024)
            if libc.sysctl(mib, 4, buf, ctypes.byref(size), None, 0) != 0:
                return None
            raw = buf.raw[:size.value]
            if not raw:
                return {}
            if len(raw) < 44 or struct.unpack_from("=i", raw, 40)[0] != pid:
                return None
            sec, usec = struct.unpack_from("=qi", raw, 0)
            return {"start": sec + usec / 1e6, "zombie": raw[36] == 5}   # SZOMB
        if sys.platform.startswith("linux"):
            try:
                with open("/proc/%d/stat" % pid, "rb") as fh:
                    raw = fh.read().decode("ascii", "replace")
            except FileNotFoundError:
                return {}
            rest = raw[raw.rindex(")") + 2:].split()
            boot = _boot_time()
            if boot is None:
                return None
            ticks = int(rest[19])                          # campo 22: starttime
            return {"start": round(boot + ticks / os.sysconf("SC_CLK_TCK"), 2),
                    "zombie": rest[0] in ("Z", "X")}
    except Exception:
        return None
    return None


def _boot_time():
    """Hora de arranque del sistema (epoch) o None."""
    import struct
    try:
        if sys.platform == "darwin":
            import ctypes
            buf = ctypes.create_string_buffer(16)
            size = ctypes.c_size_t(16)
            if _darwin_libc().sysctlbyname(b"kern.boottime", buf, ctypes.byref(size), None, 0):
                return None
            sec, usec = struct.unpack_from("=qi", buf.raw, 0)
            return sec + usec / 1e6
        if sys.platform.startswith("linux"):
            with open("/proc/stat", encoding="ascii", errors="replace") as fh:
                for line in fh:
                    if line.startswith("btime "):
                        return float(line.split()[1])
    except Exception:
        return None
    return None


def _command(pid):
    """Línea de comandos del proceso (POSIX) o None si no se pudo leer. Para
    no matar nunca a un proceso ajeno."""
    try:
        pid = int(pid)
        if sys.platform.startswith("linux"):
            with open("/proc/%d/cmdline" % pid, "rb") as fh:
                out = fh.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            return out or None
        r = subprocess.run(["ps", "-ww", "-o", "command=", "-p", str(pid)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=5, stdin=subprocess.DEVNULL,
                           env={"PATH": "/bin:/usr/bin", "LC_ALL": "C"})
        out = (r.stdout or "").strip()
        return out if r.returncode == 0 and out else None
    except Exception:
        return None


#: Cómo se ve en `ps` cada proceso de Workspace (los lanza este archivo).
def _role_ok(cmd, role):
    if not cmd:
        return False
    if role == "keeper":
        return "openclaw_gateway.py keeper" in cmd
    if role == "gateway":
        return cmd.endswith(" gateway run") or " gateway run " in cmd
    return True


def _identity(pid):
    """(vivo, huella). vivo: True/False, o None si no se puede saber. huella:
    hora de creación/inicio del proceso (los pid se reciclan: tras reiniciar
    la Mac, otro proceso puede tener el pid anotado). Un zombi (murió y su
    padre no lo recogió: el guardián con la pestaña que lo lanzó abierta)
    cuenta como muerto. En Windows JAMÁS os.kill(pid, 0): sería
    TerminateProcess."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False, None
    if pid <= 0:
        return False, None
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            k32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
            k32.CloseHandle.argtypes = (wintypes.HANDLE,)
            h = k32.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return (True, None) if ctypes.get_last_error() == 5 else (False, None)
            try:
                code = wintypes.DWORD()
                if k32.GetExitCodeProcess(h, ctypes.byref(code)) and code.value != 259:
                    return False, None                  # 259 = STILL_ACTIVE
                times = [wintypes.FILETIME() for _ in range(4)]
                if k32.GetProcessTimes(h, *[ctypes.byref(t) for t in times]):
                    return True, (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
                return True, None
            finally:
                k32.CloseHandle(h)
        except Exception:
            return None, None
    info = _posix_proc(pid)
    if info is not None:
        if not info or info["zombie"]:
            return False, None
        return True, info["start"]
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False, None
    except PermissionError:
        return True, None
    except OSError:
        return None, None
    return True, None


def _mark(pid=None):
    pid = int(pid or os.getpid())
    return {"pid": pid, "ctime": _identity(pid)[1], "t0": time.time()}


def _same_start(want, have):
    if isinstance(want, float) or isinstance(have, float):
        return abs(float(want) - float(have)) <= 0.5
    return want == have


def _alive(entry, role=None):
    """¿Sigue vivo el proceso de la anotación? Con huella guardada, la del
    proceso de hoy tiene que coincidir. Sin huella (anotación de una versión
    anterior), en Mac/Linux: muerto si se anotó antes de arrancar el sistema
    o si el proceso de hoy arrancó DESPUÉS de anotarse (pid reciclado), y con
    `role` ('keeper'/'gateway'), si su comando no es el de ese papel."""
    if not isinstance(entry, dict):
        return False
    alive, ctime = _identity(entry.get("pid"))
    if alive is None:
        return time.time() - float(entry.get("t0") or 0) < _UNKNOWN_TTL
    if not alive:
        return False
    want = entry.get("ctime")
    if want and ctime:
        return _same_start(want, ctime)
    if os.name != "nt":
        t0 = float(entry.get("t0") or 0)
        boot = _boot_time()
        if t0 and boot and t0 < boot:
            return False
        if t0 and ctime and float(ctime) > t0 + _START_SLACK:
            return False
        if role and not _role_ok(_command(entry.get("pid")), role):
            return False
    return True


def _ours(entry, role):
    """¿Ese proceso es NUESTRO `role`, vivo? Antes de matarlo: en Mac/Linux
    también su comando (jamás un killpg sobre un proceso ajeno que heredó el
    pid; cada app de Mac es líder de su grupo). Windows: la huella basta."""
    if not _alive(entry, role):
        return False
    return os.name == "nt" or _role_ok(_command(entry.get("pid")), role)


def _keeper_alive(d):
    return _alive(d.get("keeper"), "keeper")


def _reap(entry):
    """Recoge al guardián ZOMBI (el de la anotación, por su huella) si es hijo
    de este proceso: la pestaña que lo lanzó. Con un pid ajeno waitpid no
    hace nada (ECHILD)."""
    try:
        if os.name == "nt" or not isinstance(entry, dict):
            return
        pid = int(entry.get("pid"))
        info = _posix_proc(pid)
        want = entry.get("ctime")
        if info and info["zombie"] and (not want or _same_start(want, info["start"])):
            os.waitpid(pid, os.WNOHANG)
    except (OSError, TypeError, ValueError):
        pass


# ── pestañas ────────────────────────────────────────────────────────────────
def enter(profile, pid=None):
    """Anota una pestaña (o un turno headless) como cliente del gateway."""
    m = _mark(pid)

    def fn(d):
        d.setdefault("tabs", {})[str(m["pid"])] = m
        d.pop("empty_since", None)
    _update(profile, fn)


def leave(profile, pid=None):
    """Borra la anotación. Falla-suave: si no se puede, el guardián la poda
    cuando el proceso ya no exista."""
    pid = str(int(pid or os.getpid()))
    try:
        _update(profile, lambda d: (d.get("tabs") or {}).pop(pid, None))
    except Exception:
        pass


def decide(d, now, grace=GRACE):
    """Poda las pestañas muertas y decide: 'keep' o 'stop' (sin pestañas vivas
    durante `grace` s). Modifica `d`."""
    live = {k: v for k, v in (d.get("tabs") or {}).items() if _alive(v)}
    d["tabs"] = live
    if live:
        d.pop("empty_since", None)
        return "keep"
    since = float(d.setdefault("empty_since", now))
    return "stop" if now - since >= grace else "keep"


def summary(profile):
    """Para status/doctor, solo del archivo (sin sondear el puerto)."""
    d = _load(profile)
    return {"running": _keeper_alive(d), "port": d.get("port"),
            "tabs": sum(1 for v in (d.get("tabs") or {}).values() if _alive(v))}


def running(profile):
    d = _load(profile)
    return _keeper_alive(d) and d.get("status") in ("starting", "running")


# ── gateway ─────────────────────────────────────────────────────────────────
def healthy(port, timeout=1.0):
    """GET /healthz del gateway (liveness oficial: {"ok":true,"status":"live"}).
    Sin proxy: 127.0.0.1 jamás debe pasar por el proxy del sistema."""
    import urllib.request
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open("http://127.0.0.1:%d/healthz" % int(port), timeout=timeout) as r:
            if r.status != 200:
                return False
            body = json.loads(r.read(512).decode("utf-8", "replace") or "{}")
            return bool(body.get("ok"))
    except Exception:
        return False


def _clean_env(env=None):
    """El gateway atiende a TODAS las pestañas: no hereda las variables de la
    pestaña que lo encendió (pestaña, agente, cerebro) ni nada de la bóveda
    (secret_store.engine_env: es el motor que corre los turnos)."""
    env = dict(os.environ if env is None else env)
    try:
        import secret_store
        env = secret_store.engine_env(env)
    except Exception:
        pass
    tab = {env.get("WORKSPACE_WS"), env.get("WORKSPACE_WID")} - {None, ""}
    for k in list(env):
        if k.startswith("WORKSPACE_") or (k.endswith(("_WS", "_WID")) and env.get(k) in tab):
            env.pop(k, None)
    return env


def _detached():
    """Proceso desacoplado de la ventana: cerrarla no lo mata."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill_tree(pid):
    try:
        pid = int(pid)
        if os.name == "nt":
            tk = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "taskkill.exe")
            subprocess.run([tk, "/PID", str(pid), "/T", "/F"], capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=30)
        else:
            import signal
            os.killpg(pid, signal.SIGKILL)
    except Exception:
        pass


def _official_stop(exe, profile):
    """`gateway stop --force` (oficial; VERIFICADO 2026.9.33: con un gateway
    lanzado por `gateway run` dice «stop signal sent to unmanaged process»)."""
    try:
        subprocess.run([exe, "--profile", profile, "gateway", "stop", "--force"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, timeout=90, env=_clean_env())
    except Exception:
        pass


def log_tail(profile, size=6000):
    try:
        with open(log_path(profile), "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - size))
            return _ANSI.sub("", fh.read().decode("utf-8", "replace"))
    except OSError:
        return ""


def _spawn_keeper(exe, profile, port):
    path = log_path(profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb"):                      # un registro por encendido
        pass
    cmd = [sys.executable, os.path.abspath(__file__), "keeper", "--exe", exe,
           "--profile", profile, "--port", str(int(port))]
    with open(path, "ab") as log:
        kw = dict(stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                  cwd=os.path.expanduser("~"), env=_clean_env(), close_fds=True)
        kw.update(_detached())
        if os.name == "nt":
            try:     # fuera del «job» de la terminal, si lo permite (si no, igual sirve)
                return subprocess.Popen(cmd, **dict(kw, creationflags=kw["creationflags"] | 0x01000000))
            except OSError:
                pass
        return subprocess.Popen(cmd, **kw)


def ensure_running(exe, profile, port, spawn=None):
    """Deja un gateway encendiéndose o vivo; NO espera (enciende mientras el
    socio elige pestaña). 'running' | 'starting' | 'stopping' | 'spawned'."""
    out = {}

    def fn(d):
        st = d.get("status")
        if _keeper_alive(d) and st in ("starting", "running", "stopping"):
            out["v"] = st
            return
        sp = d.get("spawner")
        if st == "spawning" and _alive(sp) and time.time() - float((sp or {}).get("t0") or 0) < _SPAWN_TTL:
            out["v"] = "starting"
            return
        d.update(status="spawning", spawner=_mark(), port=int(port), profile=profile)
        d.pop("keeper", None)            # «gateway» se queda: si sigue vivo, se adopta
        out["v"] = "spawn"
    _update(profile, fn)
    if out.get("v") != "spawn":
        return out.get("v")
    try:
        (spawn or _spawn_keeper)(exe, profile, port)
    except Exception as e:
        _update(profile, lambda d: d.update(status="exited", last={
            "t": time.time(), "kind": "error", "why": "no pude lanzar el guardián: %s" % e}))
    return "spawned"


def wait_ready(exe, profile, port, timeout=START_TIMEOUT, notify=None, health=None, spawn=None):
    """Espera al gateway. (True, '') o (False, motivo para el socio). Avisa una
    vez si tarda y, si otra ventana `--local` (de antes de esta versión) tiene
    el perfil, dice cuál es la salida: cerrarla."""
    health = health or healthy
    notify = notify or (lambda s: None)
    t0 = time.time()
    said = set()
    while time.time() - t0 < timeout:
        if health(port):
            return True, ""
        d = _load(profile)
        st = d.get("status")
        last = d.get("last") or {}
        if not _keeper_alive(d):
            if st == "exited" and last.get("kind") == "error" and float(last.get("t") or 0) >= t0 - 1:
                why = last.get("why") or "el gateway se detuvo"
                return False, "OpenClaw no pudo encender su gateway (%s). Registro: %s" % (
                    why, log_path(profile))
            sp = d.get("spawner") or {}
            if st == "spawning" and time.time() - float(sp.get("t0") or 0) > _SPAWN_TTL:
                return False, "no arrancó el proceso que enciende OpenClaw. Registro: %s" % (
                    log_path(profile))
            if st != "spawning":
                ensure_running(exe, profile, port, spawn=spawn)    # p. ej. lo estaban apagando
        if time.time() - t0 > 1.5 and "start" not in said:
            said.add("start")
            notify("WORKSPACE: encendiendo OpenClaw (la primera pestaña tarda unos segundos)…")
        if "owner" not in said and OWNERSHIP_WAIT in log_tail(profile):
            said.add("owner")
            notify("WORKSPACE: otra ventana de OpenClaw tiene el perfil abierto en el modo "
                   "anterior (local). Ciérrala y esta pestaña sigue sola.")
        time.sleep(0.5)
    return False, "OpenClaw no encendió en %d s. Registro: %s" % (timeout, log_path(profile))


def watch_tick(exe, profile, port, restarts=0, max_restarts=3, pid=None):
    """Una vuelta del vigilante de una pestaña abierta. Si el guardián murió
    (VERIFICADO: «terminar el árbol de procesos» de la pestaña que lo lanzó se
    lo lleva, y con él al gateway), lo vuelve a lanzar: el `tui` se reconecta
    solo («gateway reconnected after transport loss», 2026.9.33). Si su propia
    anotación se perdió, la repone. Devuelve los reintentos acumulados (tope
    `max_restarts` por pestaña: un gateway que muere solo no se relanza sin fin)."""
    me = int(pid or os.getpid())
    d = _load(profile)
    if str(me) not in (d.get("tabs") or {}):
        enter(profile, pid=me)
    if _keeper_alive(d) or restarts >= max_restarts:
        return restarts
    _reap(d.get("keeper"))               # el guardián zombi (hijo de esta pestaña)
    if ensure_running(exe, profile, port) == "spawned":
        restarts += 1
    return restarts


def start_watch(exe, profile, port, every=10):
    """Hilo del vigilante mientras la pestaña está abierta. Devuelve el Event
    que lo detiene."""
    import threading
    stop = threading.Event()

    def loop():
        restarts = 0
        while not stop.wait(every):
            try:
                restarts = watch_tick(exe, profile, port, restarts)
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True, name="openclaw-gateway-watch").start()
    return stop


def shutdown(exe, profile):
    """Apaga el gateway y su guardián YA (para recrear el perfil: en Windows no
    se puede mover una carpeta con archivos abiertos)."""
    d = _load(profile)
    if exe:
        _official_stop(exe, profile)
    for k in ("gateway", "keeper"):
        if _ours(d.get(k), k):           # jamás un proceso ajeno con su pid
            _kill_tree(d[k]["pid"])
    try:
        _update(profile, lambda x: _finish(x, None, "apagado para recrear el perfil", "idle"))
    except Exception:
        pass


def _finish(d, me, why, kind="error"):
    """Cierra el turno del guardián `me` (None = cualquiera). kind: 'idle'
    (apagado normal: la próxima pestaña lo reenciende) o 'error'."""
    if me is None or (d.get("keeper") or {}).get("pid") == me.get("pid"):
        d.pop("keeper", None)
        d.pop("gateway", None)
        d.pop("empty_since", None)
        d["status"] = "exited"
        d["last"] = {"t": time.time(), "kind": kind, "why": why}


# ── el guardián (proceso aparte) ────────────────────────────────────────────
class _KeeperStop(Exception):
    """SIGTERM/SIGHUP al guardián (cerrar sesión o apagar la Mac, `kill`)."""


def keeper_main(exe, profile, port, grace=GRACE, poll=POLL):
    """El guardián: enciende el gateway (o ADOPTA el de un guardián anterior
    que murió sin apagarlo: otro `gateway run` solo esperaría el estado) y lo
    apaga cuando no queda ninguna pestaña viva durante `grace` s. Si lo
    detienen con una señal (_KeeperStop, ver _main), apaga su gateway y
    cierra su turno: la próxima pestaña arranca limpia."""
    me = _mark()
    st = {"child": None, "gw": None}
    try:
        return _keeper_loop(exe, profile, port, grace, poll, me, st)
    except _KeeperStop as e:
        signum = int(e.args[0]) if e.args else 15
        _ignore_stop_signals()
        _stop_gateway(st["child"], st["gw"])
        try:
            _update(profile, lambda d: _finish(
                d, me, "el guardián se detuvo (señal %d)" % signum, "idle"))
        except Exception:
            pass
        return 128 + signum


def _stop_gateway(child, gw, wait=5.0):
    """Apaga YA el gateway del guardián: SIGTERM a su grupo, `wait` s y
    SIGKILL. El adoptado, solo si sigue siendo nuestro (huella y comando)."""
    import signal
    if child is not None:
        pid = child.pid
    elif _ours(gw, "gateway"):
        pid = int(gw["pid"])
    else:
        return
    try:
        if os.name == "nt":
            _kill_tree(pid)
            return
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
    t0 = time.time()
    while time.time() - t0 < wait:
        if (child.poll() is not None) if child is not None else not _alive(gw, "gateway"):
            return
        time.sleep(0.1)
    if child is not None or _ours(gw, "gateway"):
        _kill_tree(pid)
    if child is not None:
        try:
            child.wait(timeout=5)
        except Exception:
            pass


def _ignore_stop_signals():
    import signal
    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, signal.SIG_IGN)
            except (ValueError, OSError):
                pass


def _keeper_loop(exe, profile, port, grace, poll, me, st):
    info = {}

    def claim(d):
        k = d.get("keeper")
        if k and k.get("pid") != me["pid"] and _alive(k, "keeper"):
            info["dup"] = True
            return
        g = d.get("gateway")
        info["orphan"] = g if _alive(g, "gateway") else None
        d.update(keeper=me, status="starting", port=int(port), profile=profile)
        d.pop("spawner", None)
        d.pop("empty_since", None)
    _update(profile, claim)
    if info.get("dup"):
        return 0
    # Solo se adopta un gateway que RESPONDE: un pid reciclado o un gateway
    # atorado no cuentan (se lanza uno nuevo).
    child, gw = None, info.get("orphan")
    if gw and not healthy(port):
        gw = None
    if not gw:
        try:
            kw = dict(stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=subprocess.STDOUT,
                      cwd=os.path.expanduser("~"), env=_clean_env(), close_fds=True)
            kw.update(_detached())
            child = subprocess.Popen([exe, "--profile", profile, "gateway", "run"], **kw)
        except Exception as e:
            _update(profile, lambda d: _finish(d, me, "no pude lanzar `openclaw gateway run`: %s" % e))
            return 1
        st["child"] = child
        gw = _mark(child.pid)
    st["gw"] = gw
    _update(profile, lambda d: d.__setitem__("gateway", gw))
    marked = False
    while True:
        rc = child.poll() if child is not None else (None if _alive(gw, "gateway") else -1)
        if rc is not None:
            why = "el gateway terminó (código %s)" % rc
            if OWNERSHIP_WAIT in log_tail(profile):
                why = "otra ventana de OpenClaw no soltó el perfil a tiempo"
            _update(profile, lambda d: _finish(d, me, why))
            return rc
        up = marked or healthy(port)
        verdict = {}

        def tick(d):
            if (d.get("keeper") or {}).get("pid") != me["pid"]:
                verdict["v"] = "orphan"
                return
            if up and d.get("status") == "starting":
                d["status"] = "running"
            verdict["v"] = decide(d, time.time(), grace)
            if verdict["v"] == "stop":
                d["status"] = "stopping"
        try:
            _update(profile, tick)
            marked = marked or up
        except Exception:
            verdict["v"] = "keep"
        if verdict.get("v") in ("stop", "orphan"):
            _official_stop(exe, profile)
            if child is not None:
                try:
                    child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    _kill_tree(child.pid)
            else:
                t_stop = time.time()
                while time.time() - t_stop < 20 and _alive(gw, "gateway"):
                    time.sleep(1)
                if _ours(gw, "gateway"):
                    _kill_tree(gw["pid"])
            _update(profile, lambda d: _finish(d, me, "sin pestañas abiertas", "idle"))
            return 0
        time.sleep(poll)


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="openclaw_gateway")
    ap.add_argument("cmd", choices=["keeper"])
    ap.add_argument("--exe", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--port", type=int, required=True)
    a = ap.parse_args(argv)
    if os.name != "nt":
        # Cerrar sesión o apagar la Mac manda SIGTERM a todo: sin esto el
        # guardián moría sin apagar su gateway ni cerrar su turno (el archivo
        # quedaba en «starting» con pids viejos). Windows no cambia.
        import signal

        def _stop(signum, frame):
            raise _KeeperStop(signum)
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, _stop)
    return keeper_main(a.exe, a.profile, a.port)


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]) or 0)
