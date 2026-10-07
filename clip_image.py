#!/usr/bin/env python3
"""WORKSPACE · clip_image — capturar una IMAGEN para adjuntarla a una ficha.

Dos fuentes, misma salida `(bytes, ext)` o None (falla-suave SIEMPRE — nada
aquí puede tumbar el calendario):

  · PORTAPAPELES del sistema, con las CLIs nativas de cada SO (cero deps):
      - mac     → osascript  (`the clipboard as «class PNGf»` → PNG)
      - Windows → PowerShell  (`Get-Clipboard -Format Image` → PNG)
      - Linux   → xclip / wl-paste  (`-t image/png`)
  · un ARCHIVO en disco (fallback universal): el socio arrastra la imagen a la
    terminal, pega la ruta, y se copia a los assets. Se valida que sea una
    imagen de verdad por MAGIC BYTES (no por extensión — una .txt renombrada a
    .png se rechaza).

El `ext` que devolvemos SIEMPRE sale de los magic bytes, no del nombre.

Cero dependencias (stdlib, Python 3.9+). Mac, Windows y Linux.
"""
import os
import subprocess
import sys
import tempfile

#: formatos aceptados (magic bytes → extensión canónica)
SUPPORTED = ("png", "jpg", "gif", "webp", "bmp")
_CLIP_TIMEOUT = 8


def sniff(data):
    """La extensión REAL de `data` por sus primeros bytes, o None si no es
    una imagen soportada. Único árbitro del tipo — la extensión no cuenta."""
    if not data or len(data) < 12:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:2] == b"BM":
        return "bmp"
    return None


# ── fuente 1: archivo en disco ───────────────────────────────────────────────
def from_path(path):
    """`(bytes, ext)` leyendo el archivo `path`, o None si no existe, no se
    puede leer, es enorme o no es una imagen soportada (magic bytes)."""
    try:
        p = os.path.expanduser((path or "").strip().strip('"').strip("'"))
        if not p or not os.path.isfile(p):
            return None
        if os.path.getsize(p) > 25 * 1024 * 1024:     # 25 MB, sanidad
            return None
        with open(p, "rb") as f:
            data = f.read()
        ext = sniff(data)
        return (data, ext) if ext else None
    except Exception:
        return None


# ── fuente 2: portapapeles del sistema ───────────────────────────────────────
def _run(cmd, **kw):
    """subprocess.run acotado y falla-suave: devuelve el CompletedProcess o
    None si revienta (binario ausente, timeout, etc.)."""
    try:
        return subprocess.run(cmd, timeout=_CLIP_TIMEOUT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              **kw)
    except Exception:
        return None


def _mac_clipboard():
    """PNG del portapapeles de macOS vía osascript. None si no hay imagen."""
    tmp = tempfile.mktemp(suffix=".png")
    # «class PNGf» necesita los guillemets reales (« »); osascript los recibe
    # como argumento utf-8 sin problema.
    script = (
        'set theFile to (open for access (POSIX file "%s") with write permission)\n'
        'try\n'
        '\tset png to (the clipboard as «class PNGf»)\n'
        '\twrite png to theFile\n'
        '\tclose access theFile\n'
        'on error errMsg\n'
        '\ttry\n\t\tclose access theFile\n\tend try\n'
        '\terror errMsg\n'
        'end try\n' % tmp)
    r = _run(["osascript", "-e", script])
    try:
        if r is not None and r.returncode == 0 and os.path.isfile(tmp):
            with open(tmp, "rb") as f:
                data = f.read()
            ext = sniff(data)
            return (data, ext) if ext else None
        return None
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _windows_clipboard():
    """PNG del portapapeles de Windows vía PowerShell + System.Drawing."""
    tmp = tempfile.mktemp(suffix=".png")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$img=[System.Windows.Forms.Clipboard]::GetImage();"
        "if($img -eq $null){exit 1};"
        "$img.Save('%s',[System.Drawing.Imaging.ImageFormat]::Png)"
        % tmp.replace("\\", "\\\\"))
    r = _run(["powershell", "-NoProfile", "-STA", "-Command", ps])
    try:
        if r is not None and r.returncode == 0 and os.path.isfile(tmp):
            with open(tmp, "rb") as f:
                data = f.read()
            ext = sniff(data)
            return (data, ext) if ext else None
        return None
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def _linux_clipboard():
    """PNG del portapapeles de Linux: xclip (X11) o wl-paste (Wayland)."""
    for cmd in (["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                ["wl-paste", "--type", "image/png"]):
        r = _run(cmd)
        if r is not None and r.returncode == 0 and r.stdout:
            ext = sniff(r.stdout)
            if ext:
                return (r.stdout, ext)
    return None


def from_clipboard(platform=None):
    """`(bytes, ext)` de la imagen del portapapeles, o None si no hay ninguna
    (o el SO no tiene la CLI). SIEMPRE falla-suave."""
    plat = platform or sys.platform
    try:
        if plat == "darwin":
            return _mac_clipboard()
        if plat.startswith("win") or os.name == "nt":
            return _windows_clipboard()
        return _linux_clipboard()
    except Exception:
        return None


def capture(path=None):
    """La captura de alto nivel que usa el editor: si viene `path`, de ahí;
    si no, del portapapeles. `(bytes, ext)` o None."""
    if path and path.strip():
        return from_path(path)
    return from_clipboard()
