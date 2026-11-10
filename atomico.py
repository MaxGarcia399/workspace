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
  · `ruta_larga(ruta)`: la ruta tal como hay que dársela a Windows cuando
    pasa de MAX_PATH (260 caracteres, ver su docstring).
  · `anexar(ruta, datos)`: agrega al final en UNA escritura que no se pisa
    con la de otro proceso, también en Windows.

Solo stdlib, Python 3.9+, Mac / Windows / Linux. No importa nada de Workspace:
cualquier módulo (también los hooks) lo usa sin riesgo de ciclo.
"""
import ntpath
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
#: ¿Windows, para las RUTAS? Aparte de _WINDOWS: las pruebas de reintentos
#: simulan Windows en la Mac con rutas POSIX, que no llevan prefijo.
_RUTAS_NT = os.name == "nt"
#: Desde este largo (ruta absoluta) se usa el prefijo de ruta larga. Windows
#: corta en 259 caracteres para un archivo y en 247 para crear una carpeta
#: (MAX_PATH - 12); 240 deja margen a los temporales que se derivan de ella.
LARGO_MAX = 240


def ruta_larga(ruta):
    """`ruta` tal como hay que dársela al sistema para abrirla, crearla,
    reemplazarla o borrarla.

    En Windows sin LongPathsEnabled (el valor de fábrica, y no se toca la
    configuración del cliente), una ruta de 260 caracteres o más da
    FileNotFoundError aunque la carpeta exista. Le pasa a un cerebro con una
    ruta larga (`OneDrive\\Documentos\\…`): los respaldos viven en
    `transcripts-backup/<ruta del cerebro codificada>/`, y el temporal de un
    archivo hermano agrega otros 20 caracteres. Con el prefijo `\\\\?\\` sobre
    la ruta absoluta y normalizada, Windows acepta hasta ~32 000.

    Solo para la llamada al sistema: la ruta que se guarda, se compara o se
    muestra es la de siempre (el prefijo cambiaría las huellas de las
    fuentes). En Mac y Linux, o si la ruta es corta, la devuelve igual."""
    if not _RUTAS_NT or not ruta:
        return ruta
    r = os.fspath(ruta)
    if not isinstance(r, str) or r.startswith("\\\\?\\") or r.startswith("\\\\.\\"):
        return r
    a = ntpath.abspath(r)
    if len(a) < LARGO_MAX:
        return r
    if a.startswith("\\\\"):                          # UNC: \\servidor\recurso\…
        return "\\\\?\\UNC\\" + a[2:]
    return "\\\\?\\" + a


#: CreateFileW: FILE_GENERIC_WRITE sin FILE_WRITE_DATA (+ leer atributos): un
#: identificador SOLO para anexar. Windows pone cada escritura al final.
_ACCESO_ANEXAR = (0x00120116 & ~0x0002) | 0x0080
_COMPARTIR_TODO = 0x1 | 0x2 | 0x4                     # leer, escribir, borrar
_ABRIR_SIEMPRE = 4                                    # OPEN_ALWAYS
_ATRIBUTO_NORMAL = 0x80
_K32 = []


def _fd_para_anexar_nt(ruta):
    """fd de Windows abierto SOLO para anexar (FILE_APPEND_DATA sin
    FILE_WRITE_DATA): cada WriteFile va al final, atómico entre procesos."""
    import ctypes
    import msvcrt
    from ctypes import wintypes
    if not _K32:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.HANDLE)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        _K32.append(k32)
    k32 = _K32[0]
    h = k32.CreateFileW(ruta_larga(os.path.abspath(ruta)), _ACCESO_ANEXAR, _COMPARTIR_TODO,
                        None, _ABRIR_SIEMPRE, _ATRIBUTO_NORMAL, None)
    if h is None or h == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # O_BINARY: sin él la CRT cambia «\n» por «\r\n». Sin O_APPEND: la CRT
        # buscaría el final antes de escribir (justo la carrera que se evita).
        return msvcrt.open_osfhandle(h, os.O_WRONLY | os.O_BINARY)
    except BaseException:
        k32.CloseHandle(h)
        raise


def anexar(ruta, datos, encoding="utf-8"):
    """Agrega `datos` (str o bytes) al final de `ruta` en UNA escritura que no
    se pisa con la de otro proceso.

    En Mac y Linux, `open(…, "a")` ya lo garantiza (O_APPEND: cada write va al
    final). En Windows NO: Python busca el final y después escribe, y dos
    procesos a la vez escriben en el mismo lugar (una línea se pierde o queda
    partida; medido en la PC: 12 de 600 recibos con 4 cierres a la vez). Ahí
    se abre con permiso solo de anexar, y Windows pone cada escritura al final
    sin carrera. Si eso no está disponible, cae al `open` de siempre."""
    b = datos.encode(encoding) if isinstance(datos, str) else bytes(datos)
    fd = None
    if _RUTAS_NT:
        try:
            fd = _fd_para_anexar_nt(ruta)
        except (ImportError, AttributeError):
            fd = None                                  # sin ctypes: el camino de siempre
    if fd is None:
        with open(ruta_larga(ruta), "ab") as fh:
            fh.write(b)
        return
    try:
        vista = memoryview(b)
        while vista:
            vista = vista[os.write(fd, vista):]
    finally:
        os.close(fd)


def intentos_por_defecto():
    return INTENTOS_WINDOWS if _WINDOWS else INTENTOS_POSIX


def pasajero(exc):
    """¿Vale la pena reintentar este error? PermissionError (en Windows, el
    archivo abierto por otro programa un instante) o un WinError 5/32/33."""
    if isinstance(exc, PermissionError):
        return True
    return getattr(exc, "winerror", None) in WINERROR_PASAJEROS


def leer(ruta, encoding="utf-8", intentos=None):
    """El texto de `ruta`, reintentando con las mismas esperas que
    `reemplazar` ante cualquier OSError que no sea «no existe» (el antivirus
    o el indexador lo tienen abierto un instante: WinError 5/32/33). Si no
    se logra, relanza el último error; FileNotFoundError, sin reintento.
    Leer mal NO es «ilegible»: quien llama no debe apartar ni pisar nada."""
    n = max(1, int(intentos or intentos_por_defecto()))
    for k in range(n):
        try:
            with open(ruta, encoding=encoding) as fh:
                return fh.read()
        except FileNotFoundError:
            raise
        except OSError:
            if k < n - 1:
                time.sleep(ESPERA * (k + 1))
                continue
            raise


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
