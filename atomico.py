#!/usr/bin/env python3
"""WORKSPACE · atomico — reemplazo atómico con reintento (sesiones v2 · C).

Todo lo que Workspace escribe dentro de un cerebro lo escribe así: un temporal
en la MISMA carpeta y luego `os.replace` sobre el destino, para que nadie lea
jamás un archivo a medias (Obsidian, el otro motor, la otra máquina).

El problema de Windows (5-nov, el bus de la PC): `os.replace` falla con
WinError 5 («Acceso denegado») o 32 («el archivo está en uso») cuando el
antivirus, el indexador u Obsidian abren un instante el archivo recién
creado. Sin reintento, el mensaje no se escribía y quedaba un `.tmp` en
`msgs/` sin que nadie se enterara. Aquí:

  · `reemplazar(tmp, destino)` reintenta con esperas cortas ante
    `PermissionError` / WinError 5, 32 y 33 (lo mismo que ya hacía
    `memoria._reemplazar`, que ahora delega aquí). En Windows hasta 20 veces
    (~10 s en el peor caso); en Mac/Linux ese error no es pasajero, así que
    solo 3 (~0.15 s) para no frenar la apertura con un cerebro sin permisos.
  · Si se agotan los intentos (o el error no es de los pasajeros), el
    temporal SE BORRA y la excepción se relanza. Con `avisar=True` además se
    deja una línea en stderr: para quien la atrapa y sigue (falla suave), así
    nunca falla en silencio.
  · `escribir(ruta, datos)` hace el ciclo completo (crea la carpeta, escribe
    texto o bytes, fsync y reemplaza) con las mismas garantías.

Solo stdlib, Python 3.9+, Mac / Windows / Linux. No importa nada de Workspace:
cualquier módulo (también los hooks) lo usa sin riesgo de ciclo.
"""
import os
import sys
import tempfile
import time

#: ¿Windows? Las pruebas lo cambian para ejercitar el camino con reintentos.
_WINDOWS = os.name == "nt"
INTENTOS_WINDOWS = 20
INTENTOS_POSIX = 3
ESPERA = 0.05                  # s · la espera k-ésima es ESPERA * k
#: ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION
WINERROR_PASAJEROS = (5, 32, 33)


def intentos_por_defecto():
    return INTENTOS_WINDOWS if _WINDOWS else INTENTOS_POSIX


def pasajero(exc):
    """¿Vale la pena reintentar este error? PermissionError (en Windows, el
    archivo abierto por otro programa un instante) o un WinError 5/32/33."""
    if isinstance(exc, PermissionError):
        return True
    return getattr(exc, "winerror", None) in WINERROR_PASAJEROS


def _borrar(tmp):
    try:
        if tmp and os.path.lexists(tmp):
            os.unlink(tmp)
    except OSError:
        pass


def _aviso(destino, exc):
    """Una línea en stderr. Jamás levanta."""
    try:
        sys.stderr.write("WORKSPACE · no pude guardar %s (%s: %s); el archivo quedó "
                         "como estaba y no quedó ningún temporal\n"
                         % (destino, type(exc).__name__, exc))
        sys.stderr.flush()
    except Exception:
        pass


def reemplazar(tmp, destino, intentos=None, avisar=False):
    """`os.replace(tmp, destino)` con reintentos cortos ante los errores
    pasajeros de Windows. Si no se logra: borra `tmp`, avisa (si `avisar`) y
    relanza la excepción original."""
    n = max(1, int(intentos or intentos_por_defecto()))
    for k in range(n):
        try:
            os.replace(tmp, destino)
            return
        except OSError as e:
            if k < n - 1 and pasajero(e):
                time.sleep(ESPERA * (k + 1))
                continue
            _borrar(tmp)
            if avisar:
                _aviso(destino, e)
            raise


def escribir(ruta, datos, encoding="utf-8", newline="\n", fsync=True,
             intentos=None, avisar=False):
    """Escritura atómica completa de `datos` (str o bytes) en `ruta`: crea la
    carpeta, escribe un temporal hermano (`<nombre>.<azar>.tmp`), fsync y
    `reemplazar`. Si algo falla, el temporal se borra y la excepción sube."""
    carpeta = os.path.dirname(os.path.abspath(ruta))
    os.makedirs(carpeta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(ruta) + ".", suffix=".tmp",
                               dir=carpeta)
    try:
        try:
            if isinstance(datos, (bytes, bytearray)):
                fh = os.fdopen(fd, "wb")
            else:
                fh = os.fdopen(fd, "w", encoding=encoding, newline=newline)
        except BaseException:
            os.close(fd)            # en Windows un archivo abierto no se borra
            raise
        with fh:
            fh.write(datos)
            fh.flush()
            if fsync:
                os.fsync(fh.fileno())
    except BaseException as e:
        _borrar(tmp)
        if avisar and isinstance(e, Exception):
            _aviso(ruta, e)
        raise
    reemplazar(tmp, ruta, intentos=intentos, avisar=avisar)
