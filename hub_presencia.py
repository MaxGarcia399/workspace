#!/usr/bin/env python3
"""WORKSPACE · hub_presencia — ¿hay OTRO hub abierto en esta máquina?

Cada hub abierto (front.py con su menú en pantalla) sostiene un candado del
sistema sobre su propio archivo `<estado>/hubs/<pid>.lock` — fcntl.flock en
Mac/Linux, msvcrt.locking en Windows: las mismas primitivas de olock. Otro
hub sabe que ese sigue abierto porque NO puede tomar ese candado:

  · el sistema lo suelta solo cuando el proceso muere (se cierra la ventana,
    kill -9, se apaga la máquina): un archivo que quedó sin dueño no cuenta y
    se barre;
  · al lanzar un agente el hub se reemplaza (os.execvp en Mac/Linux): el
    descriptor no es heredable y se cierra en el exec, así que deja de contar
    como hub aunque el pid siga vivo. Además `soltar()` lo suelta antes, en
    todas las plataformas (en Windows el hub espera al agente con
    subprocess.run y seguiría «abierto»);
  · un pid reciclado no engaña: lo que cuenta es el candado, no el número.

`al_abrir()` anota ESTE hub y cuenta los OTROS en el mismo paso, bajo un
candado corto de elección (olock sobre `<estado>/hubs.lock`): si dos hubs
abren a la vez, el primero ve cero y el segundo ve uno — nunca los dos cero.

Todo es per-máquina (paths.state_dir); nada viaja a un cerebro. Stdlib, falla
suave: sin candados del sistema (plataforma exótica) → None, «no se sabe».
"""
import atexit
import os
import re
import time

import paths

try:                                     # mismas primitivas que olock (Mac/Linux/Windows)
    from olock import _os_lock, _os_unlock, file_lock
except Exception:                        # sin olock: no se puede saber
    _os_lock = _os_unlock = file_lock = None

#: Un archivo de hub sin dueño y más viejo que esto se barre (entre crear el
#: archivo y tomar su candado pasan microsegundos: uno recién nacido no se toca).
VIEJO_S = 10.0
#: Cuánto se espera el candado de elección (dos hubs abriendo a la vez).
ELECCION_S = 1.0
_NOMBRE_RE = re.compile(r"^\d+\.lock$")
_ESTE = []                               # [(fd, ruta)] del candado de ESTE proceso
_ATEXIT = []


def carpeta():
    """`<estado>/hubs/`: un `<pid>.lock` por hub abierto."""
    return os.path.join(paths.state_dir(), "hubs")


def registrado():
    """¿Este proceso está anotado como hub abierto?"""
    return bool(_ESTE)


def registrar():
    """Anota ESTE proceso como hub abierto (idempotente). → True si quedó."""
    if _ESTE:
        return True
    if _os_lock is None:
        return False
    try:
        d = carpeta()
        os.makedirs(d, exist_ok=True)
        ruta = os.path.join(d, "%d.lock" % os.getpid())
        fd = os.open(ruta, os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0), 0o600)
    except OSError:
        return False
    try:
        _os_lock(fd)
    except OSError:
        os.close(fd)
        return False
    _ESTE.append((fd, ruta))
    if not _ATEXIT:
        _ATEXIT.append(True)
        atexit.register(soltar)
    return True


def soltar():
    """Este proceso deja de contar como hub abierto (al lanzar un agente, al
    reabrirse o al salir). Idempotente, jamás levanta."""
    while _ESTE:
        fd, ruta = _ESTE.pop()
        try:
            _os_unlock(fd)
        except Exception:
            pass
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.remove(ruta)              # en Windows, ya cerrado (abierto no se borra)
        except OSError:
            pass


def _barrer(ruta):
    """Borra el archivo de un hub que ya no está, si no es recién nacido."""
    try:
        if time.time() - os.path.getmtime(ruta) >= VIEJO_S:
            os.remove(ruta)
    except OSError:
        pass


def otros():
    """Cuántos OTROS hubs están abiertos ahora en esta máquina (int), o None
    si no se puede saber. Barre de paso los archivos que quedaron sin dueño."""
    if _os_lock is None:
        return None
    d = carpeta()
    try:
        nombres = os.listdir(d)
    except FileNotFoundError:
        return 0
    except OSError:
        return None
    propio = "%d.lock" % os.getpid()
    n = 0
    for nombre in nombres:
        if not _NOMBRE_RE.match(nombre) or nombre == propio:
            continue
        ruta = os.path.join(d, nombre)
        try:
            fd = os.open(ruta, os.O_RDWR | getattr(os, "O_BINARY", 0))
        except FileNotFoundError:
            continue                     # se cerró mientras mirábamos
        except OSError:
            n += 1                       # no se deja ni abrir: se cuenta (mejor no abrir de más)
            continue
        libre = False
        try:
            try:
                _os_lock(fd)
                libre = True             # nadie lo sostiene: ese hub ya no está
            except OSError:
                n += 1                   # alguien lo sostiene: ese hub sigue abierto
            if libre:
                try:
                    _os_unlock(fd)
                except OSError:
                    pass
        finally:
            os.close(fd)
        if libre:
            _barrer(ruta)
    return n


def al_abrir():
    """Al abrir el hub: cuenta los OTROS hubs abiertos y anota este, en un solo
    paso bajo el candado de elección. → int (otros abiertos) o None (no se
    sabe). Jamás levanta: en el peor caso, sin elección."""
    def paso():
        n = otros()
        registrar()
        return n
    if file_lock is None:
        return paso()
    try:
        os.makedirs(carpeta(), exist_ok=True)
        with file_lock(carpeta(), timeout=ELECCION_S):     # → <estado>/hubs.lock
            return paso()
    except Exception:
        try:
            return paso()
        except Exception:
            return None
