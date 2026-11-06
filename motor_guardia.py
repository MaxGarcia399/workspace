"""WORKSPACE · motor_guardia — que un motor no quede HUÉRFANO cuando el
envoltorio muere sin cerrar (un crash, `kill -9`, el sistema lo mata).

Por qué (E2E en Mac, 2026-10-30 y 31): con SIGKILL al envoltorio nadie le
reenvía nada al motor. El shell recupera la terminal y el motor se queda en un
grupo de fondo, vivo y con la terminal colgada (la X ya no le llega: el shell
solo cuelga a sus trabajos y el del envoltorio ya terminó). Codex 0.166 guarda
cada hilo con UN solo escritor: el huérfano lo seguía teniendo y, al reabrir la
pestaña, `codex resume` salía sin retomar. Copilot y Cursor también quedaban
vivos (con sus `node`), aunque su retome sí funcionaba.

Dos capas:
  1. vigilar(): un proceso aparte (sesión propia, sin terminal) espera en un
     tubo cuyo otro extremo solo tiene el envoltorio. Si el tubo se cierra con
     el motor vivo, el envoltorio murió sin cerrar: el motor se cierra como con
     la X (detener()). En un cierre normal el envoltorio cierra el tubo cuando
     el motor ya salió y el guardia termina sin hacer nada.
  2. pending_runs.reconcile(): si el guardia tampoco alcanzó (lo mataron a él
     también), el siguiente arranque cierra al huérfano antes de capturar y
     retomar (la huella va en la corrida: pending_runs.engine_started()).
Solo Mac/Linux: en Windows la X ya cierra cada proceso de la consola; el crash
del envoltorio allá queda pendiente de probar.
La huella (pid + hora de arranque) evita tocar a otro proceso que recicló el
pid; sin hora de arranque no se toca nada."""
import json
import os
import signal
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

#: Segundos que el motor tiene para guardar antes de forzarlo (los mismos que
#: con la X: interactive._MOTOR_GRACE).
GRACIA = 3.0


def _identidad(pid):
    try:
        import openclaw_gateway as G
        return G._identity(pid)
    except Exception:
        return None, None


def _tocable(pid):
    """Jamás launchd/init ni este mismo proceso (un Popen simulado en pruebas da pid 1)."""
    return pid > 1 and pid != os.getpid()


def huella(pid):
    """{"pid", "ctime"}: con qué reconocer después a ESTE proceso."""
    pid = int(pid)
    return {"pid": pid, "ctime": _identidad(pid)[1] if _tocable(pid) else None}


def es_el_mismo(h):
    """¿Sigue vivo el proceso de la huella `h`? Un zombi cuenta como muerto;
    sin hora de arranque (guardada o de hoy) → False: no se arriesga."""
    try:
        pid, want = int(h["pid"]), h.get("ctime")
    except (TypeError, KeyError, ValueError):
        return False
    if not _tocable(pid):
        return False
    vivo, ctime = _identidad(pid)
    if not vivo or want is None or ctime is None:
        return False
    try:
        import openclaw_gateway as G
        return G._same_start(want, ctime)
    except Exception:
        return want == ctime


def _descendientes(pid):
    """Huellas de los procesos que lanzó `pid` (hijos, nietos…) en SU MISMO
    grupo, tomadas ANTES de tocarlo: al morir, sus hijos pasan a launchd/init
    y ya no se sabría cuáles eran (los `node` de Copilot y Cursor). Los que se
    fueron a su propio grupo o sesión se quedan: son demonios que sirven a
    otras ventanas (el `codex app-server` compartido de Codex 0.166)."""
    try:
        grupo = os.getpgid(int(pid))
    except Exception:
        return []
    hijos, grupos = {}, {}
    for k, padre, g in _procesos():
        hijos.setdefault(padre, []).append(k)
        grupos[k] = g
    vistos, cola = [], [int(pid)]
    while cola:
        for k in hijos.get(cola.pop(), ()):
            if k not in vistos and k != int(pid):
                vistos.append(k)
                cola.append(k)
    return [huella(k) for k in vistos if grupos.get(k) == grupo]


def _procesos():
    """[(pid, ppid, pgid)] de la máquina: `ps`, o /proc en un Linux sin procps
    (contenedores mínimos)."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid="], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=5).stdout
        filas = []
        for ln in out.splitlines():
            partes = ln.split()
            if len(partes) == 3 and all(x.isdigit() for x in partes):
                filas.append(tuple(int(x) for x in partes))
        if filas:
            return filas
    except Exception:
        pass
    filas = []
    try:
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                with open("/proc/%s/stat" % d, "rb") as fh:
                    raw = fh.read().decode("ascii", "replace")
                resto = raw[raw.rindex(")") + 2:].split()   # estado, ppid, pgrp, …
                filas.append((int(d), int(resto[1]), int(resto[2])))
            except (OSError, ValueError, IndexError):
                continue
    except OSError:
        pass
    return filas


def _senales(h, sigs):
    for s in sigs:
        try:
            os.kill(int(h["pid"]), s)
        except OSError:
            pass


def _espera(h, segundos):
    """True si el proceso de la huella terminó antes de `segundos`."""
    fin = time.monotonic() + max(0.0, segundos)
    while time.monotonic() < fin:
        if not es_el_mismo(h):
            return True
        time.sleep(0.1)
    return not es_el_mismo(h)


def detener(h, gracia=None):
    """Cierra al motor de la huella `h` como lo cierra la X (SIGHUP + SIGCONT),
    le da `gracia` s para guardar y, si no sale, SIGKILL. Después, lo mismo con
    los procesos que había lanzado y siguen vivos. → True si había un motor
    vivo que cerrar. Jamás levanta."""
    gracia = GRACIA if gracia is None else gracia
    try:
        if os.name == "nt" or not es_el_mismo(h):
            return False
        hijos = _descendientes(h["pid"])
        _senales(h, (signal.SIGHUP, signal.SIGCONT))
        if not _espera(h, gracia) and es_el_mismo(h):
            _senales(h, (signal.SIGKILL,))
            _espera(h, 1.0)
        vivos = [k for k in hijos if es_el_mismo(k)]
        for k in vivos:
            _senales(k, (signal.SIGHUP, signal.SIGCONT))
        fin = time.monotonic() + 1.0       # UN plazo para todos, no 1 s por hijo
        while vivos and time.monotonic() < fin:
            vivos = [k for k in vivos if es_el_mismo(k)]
            time.sleep(0.1)
        for k in vivos:
            if es_el_mismo(k):
                _senales(k, (signal.SIGKILL,))
        return True
    except Exception:
        return False


def detener_varios(hs, gracia=None):
    """detener() para varias huellas con UN plazo de gracia compartido (no uno
    por motor): con varios huérfanos que no salen con SIGHUP, reabrir no gasta
    su tope esperando de uno en uno (revisión nocturna, B2). → las huellas que
    tenían un motor vivo. Jamás levanta."""
    gracia = GRACIA if gracia is None else gracia
    try:
        if os.name == "nt":
            return []
        vivas = [h for h in hs if es_el_mismo(h)]
        hijos = []
        for h in vivas:
            hijos += _descendientes(h["pid"])
            _senales(h, (signal.SIGHUP, signal.SIGCONT))
        pend, fin = list(vivas), time.monotonic() + gracia
        while pend and time.monotonic() < fin:
            pend = [h for h in pend if es_el_mismo(h)]
            if pend:
                time.sleep(0.1)
        for h in pend:
            if es_el_mismo(h):
                _senales(h, (signal.SIGKILL,))
        vivos = [k for k in hijos if es_el_mismo(k)]
        for k in vivos:
            _senales(k, (signal.SIGHUP, signal.SIGCONT))
        fin = time.monotonic() + 1.0
        while (vivos or pend) and time.monotonic() < fin:
            vivos = [k for k in vivos if es_el_mismo(k)]
            pend = [h for h in pend if es_el_mismo(h)]
            time.sleep(0.1)
        for k in vivos:
            if es_el_mismo(k):
                _senales(k, (signal.SIGKILL,))
        return vivas
    except Exception:
        return []


class _Guardia:
    def __init__(self, tubo, proc):
        self._tubo, self._proc = tubo, proc

    def soltar(self):
        """El motor ya salió: cierra el tubo (el guardia termina solo) y lo recoge."""
        tubo, self._tubo = self._tubo, None
        if tubo is not None:
            try:
                os.close(tubo)
            except OSError:
                pass
        try:
            self._proc.wait(timeout=2)
        except Exception:
            pass


def vigilar(pid, gracia=GRACIA, h=None):
    """Lanza el guardia del motor `pid` (ver el docstring del módulo). → un
    objeto con .soltar(), que el envoltorio llama cuando el motor ya salió; o
    None (Windows, sin huella, o si no se pudo lanzar: el motor corre igual)."""
    if os.name == "nt":
        return None
    h = h or huella(pid)
    if h["ctime"] is None:
        return None
    leer, escribir = os.pipe()
    try:
        proc = subprocess.Popen(
            [sys.executable, "-I", os.path.abspath(__file__), "--tubo", str(leer),
             "--huella", json.dumps(h), "--gracia", str(float(gracia))],
            pass_fds=(leer,), start_new_session=True, cwd="/",
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        os.close(escribir)
        return None
    finally:
        os.close(leer)
    return _Guardia(escribir, proc)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="motor_guardia.py")
    ap.add_argument("--tubo", type=int, required=True)
    ap.add_argument("--huella", required=True)
    ap.add_argument("--gracia", type=float, default=GRACIA)
    a = ap.parse_args(argv)
    for s in (signal.SIGHUP, signal.SIGINT):
        signal.signal(s, signal.SIG_IGN)
    try:                             # hereda la máscara de call_motor (SIGHUP/SIGTERM bloqueados)
        signal.pthread_sigmask(signal.SIG_SETMASK, set())
    except (AttributeError, ValueError, OSError):
        pass
    while True:                      # el envoltorio nunca escribe: solo EOF despierta
        try:
            if not os.read(a.tubo, 64):
                break
        except InterruptedError:
            continue
        except OSError:
            break
    detener(json.loads(a.huella), a.gracia)
    return 0


if __name__ == "__main__":
    if ROOT not in sys.path:         # -I: la carpeta del script no va en sys.path
        sys.path.insert(0, ROOT)
    sys.exit(main())
