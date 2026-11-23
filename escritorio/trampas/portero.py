#!/usr/bin/env python3
"""WORKSPACE · escritorio/trampas/portero — el portero de la seguridad para actuar, desde Python.

Compila (una vez, en una carpeta temporal) el MISMO código Swift que usa la app del monito
(escritorio/mac/Sources/MonitoEscritorio/Logica.swift + Seguridad.swift) con su cara de línea de comandos
(escritorio/mac/Herramientas/portero.swift), y habla con él por líneas de JSON. Así las pruebas de ataques y las de
Python pasan por el clasificador y la tarjeta de verdad: no hay una segunda copia de las reglas en Python. Solo Mac
(swiftc). Stdlib."""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
MAC = os.path.join(os.path.dirname(AQUI), "mac")
#: Las reglas del portero (datos): las mismas que carga la app al abrir.
REGLAS = os.path.join(os.path.dirname(AQUI), "reglas", "portero.json")
FUENTES = [os.path.join(MAC, "Sources", "MonitoEscritorio", "Logica.swift"),
           os.path.join(MAC, "Sources", "MonitoEscritorio", "Seguridad.swift"),
           os.path.join(MAC, "Herramientas", "portero.swift")]


class SinSwift(Exception):
    """No hay swiftc (o no es una Mac): el portero de verdad no se puede compilar aquí."""


def compilar(carpeta=None):
    """La ruta del ejecutable del portero, compilado de las fuentes de ahora (se reusa si no cambiaron)."""
    sw = shutil.which("swiftc")
    if sys.platform != "darwin" or not sw:
        raise SinSwift("el portero necesita swiftc en una Mac")
    h = hashlib.sha256()
    for f in FUENTES:
        with open(f, "rb") as fh:
            h.update(fh.read())
    carpeta = carpeta or os.path.join(tempfile.gettempdir(), "workspace-portero")
    os.makedirs(carpeta, exist_ok=True)
    exe = os.path.join(carpeta, "portero-" + h.hexdigest()[:16])
    if os.path.isfile(exe):
        return exe
    destino = ("arm64" if platform.machine() == "arm64" else "x86_64") + "-apple-macosx14.0"
    tmp = exe + ".%d.tmp" % os.getpid()
    r = subprocess.run([sw, "-parse-as-library", "-target", destino] + FUENTES + ["-o", tmp],
                       capture_output=True, text=True, encoding="utf-8", timeout=600)
    if r.returncode != 0:
        raise RuntimeError("no compiló el portero:\n" + (r.stderr or r.stdout)[-3000:])
    os.replace(tmp, exe)
    return exe


class Portero:
    """Un portero vivo (su proceso). Cada llamada: un dict → un dict (con "registro": la bitácora nueva)."""

    def __init__(self, exe=None, reglas=None):
        self.exe = exe or compilar()
        self.p = subprocess.Popen([self.exe, "--reglas", reglas or REGLAS], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", bufsize=1)
        self.candado = threading.Lock()
        self.bitacora = []

    def __call__(self, op, **k):
        d = dict(k, op=op)
        with self.candado:
            self.p.stdin.write(json.dumps(d, ensure_ascii=False) + "\n")
            self.p.stdin.flush()
            linea = self.p.stdout.readline()
        if not linea:
            raise RuntimeError("el portero se cerró: " + (self.p.stderr.read() or "")[-500:])
        r = json.loads(linea)
        self.bitacora.extend(r.get("registro") or [])
        return r

    def cerrar(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()
        for f in (self.p.stdout, self.p.stderr):
            try:
                f.close()
            except Exception:
                pass
