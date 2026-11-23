#!/usr/bin/env python3
"""Lanzador del servidor MCP `workspace` dentro del paquete de cada motor.

Abre el MCP núcleo (arquitectura/nucleo_mcp.py, F6) del Workspace instalado con el mismo
stdin/stdout. Sin Workspace instalado, avisa por stderr y sale con 1: el motor muestra el error.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402

SERVIDOR = os.path.join("arquitectura", "nucleo_mcp.py")

if __name__ == "__main__":
    raiz = comun.raiz_workspace(SERVIDOR)
    if not raiz:
        sys.stderr.write("workspace: no encuentro Workspace instalado (WORKSPACE_ROOT)\n")
        sys.exit(1)
    argv = [sys.executable, "-I", os.path.join(raiz, SERVIDOR)]
    if os.name == "nt":
        # en Windows exec crea OTRO proceso y este sale: el motor vería morir su servidor MCP. Aquí se espera
        # al hijo con el mismo stdin/stdout y se sale con su código.
        import subprocess
        sys.exit(subprocess.call(argv))
    os.execv(sys.executable, argv)
