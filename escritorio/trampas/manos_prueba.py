#!/usr/bin/env python3
"""WORKSPACE · escritorio/trampas/manos_prueba — las manos DE VERDAD (escritorio/manos_mcp.py) para la prueba de
ataques, con una guarda: se niegan a arrancar con el HOME de verdad (así nunca hablan con el monito de nadie: solo con
la app de mentira de la prueba, que anota su ficha en el HOME de prueba). Importable sin arrancar (herramientas())."""
import os
import pwd
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
from escritorio import manos_mcp as M  # noqa: E402


def herramientas():
    return M.herramientas()


def home_de_verdad():
    return os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)


if __name__ == "__main__":
    if os.path.realpath(os.path.expanduser("~")) == home_de_verdad():
        sys.stderr.write("manos_prueba: no con el HOME de verdad\n")
        sys.exit(3)
    sys.exit(M.main(sys.argv[1:]))
