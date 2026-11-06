#!/usr/bin/env python3
"""WORKSPACE · engine_gatekeeper — ¿macOS va a bloquear el programa de un motor?

Por qué existe (2026-10-29): con el cask de Homebrew de Cursor (`cursor-cli`) y
el de GitHub Copilot (`copilot-cli`), cada vez que Workspace corría el programa
del motor (`cursor-agent status` al abrir Motores o el hub, `copilot --version`)
macOS abría su diálogo «No se abrió …» / «Apple no pudo verificar…». Homebrew
descarga los casks con el atributo de cuarentena y Gatekeeper revisa en línea
cada pieza sin ticket engrapado (Cursor: sus módulos `.node`, que al cargar
daban «library load disallowed by system policy»). El diálogo vuelve en cada
ejecución. Workspace no debe ejecutar un programa así: lo detecta ANTES y
Motores ofrece reinstalar con la receta oficial (que no deja cuarentena).

Regla (solo macOS; en otro sistema nunca bloquea). Sin subprocesos:
  1. Archivos: el programa REAL (enlaces resueltos) y, si el motor lo pide
     (`native=True`, Cursor), los módulos nativos `*.node` de su carpeta.
  2. Cuarentena PENDIENTE = atributo `com.apple.quarantine` sin la marca de
     «aprobado por el usuario» (0x0040, la que deja «Abrir de todos modos»).
  3. No cuenta la cuarentena de un archivo dentro de una `.app` con el ticket
     de notarización ENGRAPADO (`Contents/CodeResources` que empieza con
     `s8ch`): Gatekeeper la acepta sin red. VERIFICADO 2026-10-29: el cask
     `kiro-cli` deja «Kiro CLI.app» con cuarentena 0381 y abre sin diálogo
     (`codesign -dvvv` → «Notarization Ticket=stapled»).
  4. Con cuarentena pendiente en cualquiera → bloqueado. Si el atributo no se
     pudo leer, decide la ruta: un cask conocido como roto
     (`/Caskroom/<cask>/`) → bloqueado; si no, no se bloquea (falla-suave).
  Sin cuarentena → se ejecuta, aunque venga de un cask: quitarla (`xattr`) es
  decisión del socio y Workspace no la toma por él.

Por qué no `spctl --assess`: para un binario suelto consulta en línea y no es
estable (VERIFICADO 2026-10-29: el mismo `pty.node` de Cursor dio «rejected ·
Unnotarized Developer ID» y minutos después «accepted · Notarized»).

Barato: unas llamadas a getxattr/stat, en caché por ruta+mtime (5 min, y
`forget()` al recargar Motores).

API: check(exe, native=False, casks=()) → None | {path, cask, files}
     message(info) → la línea para el socio (es/en)
Cero dependencias (stdlib, 3.9+). Falla-suave: nada aquí lanza.
"""
import errno
import glob
import os
import re
import sys
import time

QUARANTINE_ATTR = "com.apple.quarantine"
#: Marca de la cuarentena que pone macOS cuando el socio aprueba el programa.
QTN_USER_APPROVED = 0x0040
#: Casks de Homebrew VERIFICADOS como bloqueados por Gatekeeper (2026-10-28,
#: runbooks/agregar-motor.md «Trampas»). El de Kiro (`kiro-cli`) NO: su app
#: está notarizada y engrapada.
BROKEN_CASKS = ("copilot-cli", "cursor-cli")
#: Magia del ticket de notarización engrapado en `<app>/Contents/CodeResources`.
_TICKET_MAGIC = b"s8ch"
_ENOATTR = getattr(errno, "ENOATTR", 93)
_TTL = 300.0
_CACHE = {}
_LIBC = []


def forget():
    """Olvida los veredictos (Motores › recargar: el socio pudo reinstalar)."""
    _CACHE.clear()


def _libc():
    if not _LIBC:
        import ctypes
        import ctypes.util
        lib = ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)
        fn = lib.getxattr
        fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                       ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
        fn.restype = ctypes.c_ssize_t
        _LIBC.append(fn)
    return _LIBC[0]


def read_xattr(path, name=QUARANTINE_ATTR):
    """Valor del atributo extendido: bytes; b'' si el archivo no lo tiene;
    None si no se pudo leer. macOS: libc `getxattr` (Python no trae
    os.getxattr en macOS); en otros, os.getxattr si existe."""
    fn = getattr(os, "getxattr", None)
    if fn is not None:
        try:
            return fn(path, name)
        except OSError as e:
            return b"" if e.errno in (_ENOATTR, getattr(errno, "ENODATA", -1)) else None
        except Exception:
            return None
    try:
        import ctypes
        get = _libc()
        p, n = os.fsencode(path), name.encode("ascii")
        size = get(p, n, None, 0, 0, 0)
        if size < 0:
            return b"" if ctypes.get_errno() == _ENOATTR else None
        buf = ctypes.create_string_buffer(max(int(size), 1))
        size = get(p, n, buf, len(buf), 0, 0)
        if size < 0:
            return b"" if ctypes.get_errno() == _ENOATTR else None
        return buf.raw[:size]
    except Exception:
        return None


def pending(value):
    """¿La cuarentena sigue pendiente? (hay atributo y no trae la marca de
    aprobado por el usuario). Un valor ilegible cuenta como pendiente."""
    if not value:
        return False
    try:
        flags = int(bytes(value).split(b";", 1)[0], 16)
    except (ValueError, TypeError):
        return True
    return not (flags & QTN_USER_APPROVED)


def stapled_bundle(path):
    """¿`path` vive dentro de una `.app` con el ticket de notarización
    engrapado? Gatekeeper la acepta sin consultar la red."""
    p = os.path.abspath(path)
    while True:
        if p.endswith(".app"):
            try:
                with open(os.path.join(p, "Contents", "CodeResources"), "rb") as fh:
                    return fh.read(4) == _TICKET_MAGIC
            except OSError:
                return False
        up = os.path.dirname(p)
        if up == p:
            return False
        p = up


def native_modules(real):
    """Módulos nativos de Node (`*.node`) junto al programa y en sus
    node_modules: los carga el proceso y Gatekeeper también los revisa."""
    d = os.path.dirname(real)
    out = []
    for pat in ("*.node",
                os.path.join("node_modules", "*", "build", "Release", "*.node"),
                os.path.join("node_modules", "*", "*", "build", "Release", "*.node")):
        try:
            out += sorted(glob.glob(os.path.join(d, pat)))
        except Exception:
            pass
    return out


def homebrew_cask(path):
    """El cask de Homebrew bajo cuya carpeta (`…/Caskroom/<cask>/…`) vive
    `path`, o ''."""
    m = re.search(r"/Caskroom/([^/]+)/", str(path or "").replace("\\", "/"))
    return m.group(1) if m else ""


def check(exe, native=False, casks=BROKEN_CASKS, platform=None, xattr=None):
    """None si macOS deja ejecutar el programa del motor; si lo bloquearía →
    {"path": ruta real, "cask": cask de Homebrew o '', "files": [en cuarentena]}.
    `platform`/`xattr` son knobs de test (xattr = función ruta → bytes|b''|None)."""
    if (platform or sys.platform) != "darwin" or not exe:
        return None
    try:
        real = os.path.realpath(str(exe))
        mtime = os.stat(real).st_mtime
    except (OSError, ValueError):
        return None
    key = (real, mtime, bool(native), tuple(casks or ()))
    hit = _CACHE.get(key) if xattr is None else None
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    read = xattr or read_xattr
    files = [real] + (native_modules(real) if native else [])
    held, unreadable = [], False
    for f in files:
        v = read(f)
        if v is None:
            unreadable = True
        elif pending(v) and not stapled_bundle(f):
            held.append(f)
    cask = homebrew_cask(real) or homebrew_cask(exe)
    if held:
        res = {"path": real, "cask": cask, "files": held}
    elif unreadable and cask and cask in (casks or ()):
        res = {"path": real, "cask": cask, "files": []}
    else:
        res = None
    if xattr is None:
        _CACHE[key] = (time.time(), res)
    return res


def text(key, es, en, **kw):
    """i18n falla-suave (catálogo → inline es/en), igual que section_frame.t
    (los adapters lo usan para lo que muestra Motores)."""
    s = es
    try:
        import i18n
        v = i18n.t(key)
        if v != key:
            s = v
        elif i18n.lang() == "en":
            s = en
    except Exception:
        pass
    try:
        return s.format(**kw) if kw else s
    except Exception:
        return s


def message(info):
    """La línea para el socio: qué pasa y qué hacer (reinstalar con la receta
    oficial; Workspace no quita la cuarentena por él)."""
    if not info:
        return ""
    if info.get("cask"):
        return text("motores.gk.cask",
                  "instalado por Homebrew ({cask}), macOS lo bloquea; reinstala con la "
                  "receta oficial",
                  "installed by Homebrew ({cask}), macOS blocks it; reinstall with the "
                  "official recipe", cask=info["cask"])
    return text("motores.gk.quarantine",
              "macOS lo bloquea (cuarentena de Gatekeeper); reinstala con la receta oficial",
              "macOS blocks it (Gatekeeper quarantine); reinstall with the official recipe")
