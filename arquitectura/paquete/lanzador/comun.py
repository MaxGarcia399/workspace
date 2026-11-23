"""Lo que comparten los lanzadores del paquete: encontrar el Workspace instalado.

El paquete vive en la carpeta de plugins de cada motor, lejos del harness, así
que no puede importar sus módulos. Busca la raíz así:
  1. $WORKSPACE_ROOT (lo pone Workspace al abrir una pestaña);
  2. el comando `workspace` que deja install.py en ~/.local/bin (la misma regla
     que paths.installed_root; una prueba cuida que no se separen).
Sin raíz, '' y el lanzador no hace nada (falla abierto)."""
import os
import re

#: (archivo en ~/.local/bin, regex de la línea que apunta a front.py)
_COMANDOS = (("workspace", r'^exec "\$PY" "(.+)[\\/]front\.py"'),
             ("workspace.cmd", r'^"[^"]+" "(.+)[\\/]front\.py"'))


def _instalada(home):
    for fn, rx in _COMANDOS:
        try:
            with open(os.path.join(home, ".local", "bin", fn), encoding="utf-8",
                      errors="replace") as fh:
                head = fh.read(4096)
        except OSError:
            continue
        for ln in head.splitlines():
            m = re.match(rx, ln.strip())
            if m:
                return m.group(1)
    return ""


def raiz_workspace(marca, env=None, home=None):
    """Carpeta del harness que tiene el archivo `marca` (p. ej. workspace_hook.py), o ''."""
    env = os.environ if env is None else env
    home = home or os.path.expanduser("~")
    for cand in (env.get("WORKSPACE_ROOT", "").strip(), _instalada(home)):
        if cand and os.path.isfile(os.path.join(cand, marca)):
            return cand
    return ""
