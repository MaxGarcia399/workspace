#!/usr/bin/env python3
"""WORKSPACE · path_refresh — detectar CLIs instalados FUERA de este proceso (U01/Z01).

Problema: el socio instala un motor (claude/codex/agy) desde OTRA terminal o
con el instalador oficial mientras Workspace está abierto. El PATH de este
proceso es el que heredó al arrancar → «Recargar motores» no lo ve y la única
salida era cerrar y reabrir la terminal.

Solución por OS (adapter, sin ejecutar instaladores ni shells de login):
  · Windows: relee el PATH PERSISTIDO (HKCU\\Environment + HKLM\\...\\Session
    Manager\\Environment, expandiendo %VARS%) — es lo que vería una terminal
    nueva — y AGREGA al PATH del proceso las entradas que falten.
  · macOS/Linux: no hay registro; se agregan los directorios de instalación
    conocidos de los instaladores oficiales que existan en disco
    (~/.local/bin, ~/.npm-global/bin, /opt/homebrew/bin, /usr/local/bin, …).
Solo AGREGA al final (nunca reordena ni quita: no cambia qué binario ganaba
antes). Devuelve las entradas nuevas para que la UI lo diga.
Stdlib puro, falla-suave.
"""
import os
import sys

POSIX_KNOWN = (
    "~/.local/bin",            # claude (instalador nativo), pipx
    "~/.npm-global/bin",       # npm prefix de usuario
    "~/.bun/bin",
    "~/.volta/bin",
    "~/.antigravity/bin",
    "/opt/homebrew/bin",       # brew en Apple Silicon
    "/usr/local/bin",
)


def _norm(p):
    return os.path.normcase(os.path.normpath(p.strip().strip('"'))) if p and p.strip() else ""


def _windows_persisted_path():
    """PATH que vería una terminal nueva en Windows: máquina + usuario."""
    try:
        import winreg
    except ImportError:
        return []
    out = []
    keys = ((winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"))
    for hive, sub in keys:
        try:
            with winreg.OpenKey(hive, sub) as k:
                val, _typ = winreg.QueryValueEx(k, "Path")
        except OSError:
            continue
        for part in str(val).split(os.pathsep):
            part = os.path.expandvars(part.strip())
            if part:
                out.append(part)
    return out


def candidates(platform=None):
    """Entradas de PATH que una terminal NUEVA tendría (o directorios de
    instalación conocidos en POSIX)."""
    platform = platform or sys.platform
    if platform.startswith("win"):
        return _windows_persisted_path()
    return [os.path.normpath(os.path.expanduser(p)) for p in POSIX_KNOWN]


def refresh(platform=None, environ=None):
    """Agrega al PATH del proceso las entradas que falten y existan.
    Devuelve la lista de entradas agregadas ([] si nada cambió)."""
    env = os.environ if environ is None else environ
    cur = env.get("PATH", "")
    have = {_norm(p) for p in cur.split(os.pathsep) if p}
    added = []
    for p in candidates(platform):
        n = _norm(p)
        if not n or n in have or not os.path.isdir(p):
            continue
        have.add(n)
        added.append(p)
    if added:
        env["PATH"] = os.pathsep.join([cur] + added) if cur else os.pathsep.join(added)
    return added


if __name__ == "__main__":
    new = refresh()
    print("PATH: +%d entradas%s" % (len(new), (": " + ", ".join(new)) if new else ""))
