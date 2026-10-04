#!/usr/bin/env python3
"""WORKSPACE · pathguard — detección (SOLO) de rutas redirigidas a OneDrive / known-folders.

P0-4: OneDrive y la redirección de carpetas conocidas (Desktop, Documents) son una
fuente crónica de bugs en Windows — el harness y los cerebros terminan bajo una ruta
sincronizada por la nube → locks de archivos, latencia, estado per-máquina pisado, y
doble canal con Obsidian Sync (corrupción del vault). Este módulo SOLO DETECTA y
ETIQUETA: nunca mueve nada, nunca lanza. La reubicación es decisión y acción del socio
(doctor e install dan la instrucción; jamás auto-move).

API:
    redirected_root(path) -> str
        Etiqueta corta (p. ej. "%OneDrive%\\Desktop") si el realpath de `path` cae
        bajo una ubicación redirigida a OneDrive; "" si no. SOLO Windows: en Mac/Linux
        devuelve "" SIEMPRE (no-op). Nunca lanza — cada señal va envuelta.

Cero dependencias (stdlib pura, Python 3.9+).
"""
import os

IS_WIN = os.name == "nt"

# Variables de entorno que OneDrive define apuntando a su raíz sincronizada.
_ONEDRIVE_ENV = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")
# Componente de ruta que delata OneDrive en cualquier nivel (señal de fallback).
# Separador canónico '/' (no os.sep): _norm normaliza TODO a '/', así la detección
# es la misma corriendo en Windows real o forzando IS_WIN=True en Mac/CI.
_ONEDRIVE_MARK = "/onedrive"


def _real(path):
    """realpath defensivo: jamás lanza (rutas inválidas, permisos, drives muertos…)."""
    try:
        return os.path.realpath(path)
    except Exception:
        try:
            return os.path.abspath(path)
        except Exception:
            return path or ""


def _norm(p):
    """Normaliza para comparar: lowercase + separador '/' SIEMPRE, en cualquier SO.
    OJO: `os.path.normcase` lowercasea SOLO en Windows (en POSIX es no-op) — por
    eso la comparación case-insensitive fallaba al forzar IS_WIN=True en Mac. Aquí
    bajamos a minúscula explícito y unificamos `\\`→`/` para ser OS-agnósticos."""
    try:
        return os.path.normpath(p).replace("\\", "/").lower() if p else ""
    except Exception:
        return ""


def _under(child, parent):
    """True si `child` ES o está DENTRO de `parent` (comparación normalizada y por
    componente — C:\\OneDriveX no cuenta como dentro de C:\\OneDrive). `_norm` ya
    deja todo en '/', así que el borde de componente se chequea con '/'."""
    c, p = _norm(child), _norm(parent)
    if not c or not p:
        return False
    return c == p or c.startswith(p + "/")


def _label(token, root_real, path_real):
    """Etiqueta corta tipo `<token>\\<primer-componente>` (p. ej. "%OneDrive%\\Desktop").
    Si `path_real` ES la raíz, devuelve solo el token. Defensivo: nunca lanza."""
    try:
        rel = os.path.relpath(path_real, root_real)
    except Exception:
        return token
    if rel in ("", ".") or rel.startswith(".."):
        return token
    first = rel.split(os.sep)[0]
    return token + os.sep + first if first else token


def _env_label(path_real):
    """(a)+(b) · Anclaje directo a OneDrive vía env vars %OneDrive*% o el prefijo
    %USERPROFILE%\\OneDrive*. Devuelve etiqueta o "". Envuelto: nunca lanza."""
    try:
        # (a) %OneDrive% / %OneDriveConsumer% / %OneDriveCommercial%
        for var in _ONEDRIVE_ENV:
            root = os.environ.get(var, "")
            if root:
                rr = _real(root)
                if _under(path_real, rr):
                    return _label("%" + var + "%", rr, path_real)
        # (b) %USERPROFILE%\OneDrive* (algunos setups no exportan %OneDrive%)
        up = os.environ.get("USERPROFILE", "")
        if up:
            upr = _real(up)
            if _under(path_real, upr) and _norm(path_real) != _norm(upr):
                rel = os.path.relpath(path_real, upr)
                first = rel.split(os.sep)[0]
                if first.lower().startswith("onedrive"):
                    return "%USERPROFILE%" + os.sep + first
    except Exception:
        return ""
    return ""


def _is_onedrive(path_real):
    """True si `path_real` está anclado a OneDrive (por env o por el componente
    \\onedrive\\). Usado para clasificar el TARGET de un known-folder."""
    try:
        if _env_label(path_real):
            return True
        return _ONEDRIVE_MARK in _norm(path_real)
    except Exception:
        return False


def _known_folder_label(path_real):
    """(c) · Redirección de known-folder vía winreg (User Shell Folders, HKCU):
    si el TARGET de Desktop/Personal cae bajo OneDrive y `path_real` cae bajo ese
    target → hit. Todo winreg envuelto: en una máquina sin registro / sin permisos
    devuelve "" sin lanzar."""
    if not IS_WIN:
        return ""
    try:
        import winreg
    except Exception:
        return ""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
    except Exception:
        return ""
    try:
        # valor en el registro -> nombre legible de la carpeta conocida
        for valname, nice in (("Desktop", "Desktop"), ("Personal", "Documents")):
            try:
                raw, _ = winreg.QueryValueEx(key, valname)
                target = _real(os.path.expandvars(raw))
            except Exception:
                continue
            if _is_onedrive(target) and _under(path_real, target):
                # mejor etiqueta anclada a OneDrive; si no, una genérica clara
                return _env_label(path_real) or ("%OneDrive%" + os.sep + nice)
    except Exception:
        return ""
    finally:
        try:
            winreg.CloseKey(key)
        except Exception:
            pass
    return ""


def redirected_root(path):
    """Etiqueta corta si `path` vive bajo una ubicación redirigida a OneDrive, "" si no.

    SOLO Windows (Mac/Linux → "" siempre, no-op). DETECCIÓN, no acción: nunca mueve
    nada, nunca lanza. Señales, en orden, cada una envuelta para no propagar excepción:
      (a) env %OneDrive% / %OneDriveConsumer% / %OneDriveCommercial%
      (b) prefijo %USERPROFILE%\\OneDrive*
      (c) redirección de known-folder (Desktop/Personal) vía winreg
      (d) fallback barato: el componente \\onedrive\\ en el realpath
    """
    if not IS_WIN or not path:
        return ""
    try:
        path_real = _real(path)
        # (a) + (b)
        lbl = _env_label(path_real)
        if lbl:
            return lbl
        # (c)
        try:
            lbl = _known_folder_label(path_real)
        except Exception:
            lbl = ""
        if lbl:
            return lbl
        # (d) fallback substring (case-insensitive vía _norm; _norm usa '/')
        norm = _norm(path_real)
        if (_ONEDRIVE_MARK + "/") in norm or norm.endswith(_ONEDRIVE_MARK):
            return "OneDrive"
    except Exception:
        return ""
    return ""


if __name__ == "__main__":   # diagnóstico manual: `python pathguard.py [ruta...]`
    import sys
    for p in (sys.argv[1:] or [os.getcwd()]):
        lbl = redirected_root(p)
        print(f"{'REDIRIGIDA' if lbl else 'ok        '}  {p}" + (f"  → {lbl}" if lbl else ""))
