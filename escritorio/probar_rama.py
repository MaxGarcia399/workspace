#!/usr/bin/env python3
"""WORKSPACE · escritorio/probar_rama — probar Workspace Compañero (la app de escritorio) de ESTA copia (una rama) con tus agentes de verdad, sin tocar la
página que ya tienes abierta ni su código.

    python3 escritorio/probar_rama.py            abre la página de esta copia (otro puerto) y el monito de esta copia
    python3 escritorio/probar_rama.py --actuar-ensayo   lo mismo, con `actuar` en ensayo (A0: la tarjeta de OK de la app;
                                                 nada se hace de verdad). De fábrica, apagado (S3-a)
    python3 escritorio/probar_rama.py cerrar     cierra los dos (y nada más)
    python3 escritorio/probar_rama.py estado     dice qué está abierto

Por qué así. La página local es UNA por máquina (localhost_fondo: <estado>/web/servidor.json); si se prendiera la de
esta copia por el camino de siempre, vería la tuya como «de otro código» y la APAGARÍA. Aquí no: la de esta copia se
prende aparte, en otro puerto, sin anotarse en servidor.json (tu página y tu hub siguen con la suya), y con tu estado
de verdad (tus agentes, sus cerebros, sus motores). El monito de esta copia habla SOLO con ella
(WORKSPACE_ESCRITORIO_PAGINA, en escritorio/cliente.conectar).

Lo que toca (para decidir antes de correrlo):
  · <estado>/escritorio/: el monito usa el mismo lugar que el de siempre (app.pid, manos.json, turno.json, lugar.json,
    miradas/, elegido.json). Por eso no abre si ya hay un monito abierto: ciérralo antes (o --cerrar-el-abierto).
  · <estado>/escritorio/rama/: su página (pagina.json, 600), su compilación y su app («Workspace Compañero de prueba.app», una sola
    para todas las copias: solo cambia si cambia su Swift; firmada con la firma estable de desarrollo si ya existe
    —escritorio/mac/firmar_local.sh—, si no ad hoc, y lo dice). Nunca la compilación de siempre
    (escritorio/build-…: una carpeta por copia del paquete). Su identificador es OTRO (com.workspace.companero.prueba): en Ajustes sale como «Workspace Compañero de
    prueba» y sus permisos son suyos (la primera vez te los pide; los del monito de siempre no se tocan). Si queda la
    app de antes con el identificador de siempre (rama/MonitoEscritorio.app), la quita: con dos paquetes con el mismo
    identificador, el permiso que dabas se iba al otro.
  · <estado>/arquitectura/paquete/: el paquete de esta copia, en su propia carpeta de versión (como cualquier versión).
  · En cada cerebro con el que hables desde el monito: su pestaña «escritorio» (STATE/sessions/<socio>/escritorio.md),
    su historial y las notas que guarde (marcadas «[desde el monito]»); con Kiro, .kiro/agents/workspace-escritorio.json.
    Tu página de siempre (la de main) todavía no esconde esa pestaña: la verás en la lista; no la abras en la terminal.
  · Las sesiones de sus motores (las de Claude Code, Codex…, en sus carpetas de siempre).
Stdlib."""
import json
import os
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
import paths  # noqa: E402
from escritorio import abrir as A  # noqa: E402

#: Lo que la app hereda para hablar solo con la página de esta copia.
VAR_PAGINA = "WORKSPACE_ESCRITORIO_PAGINA"


def carpeta():
    return os.path.join(paths.state_dir(), "escritorio", "rama")


def ruta_pagina():
    return os.path.join(carpeta(), "pagina.json")


def leer_pagina():
    try:
        with open(ruta_pagina(), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if A._vivo(int(d.get("pid") or 0)) else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def pagina_por_su_registro():
    """Sin pagina.json: la última página que se anotó en pagina.log («página de esta copia: puerto N · pid P»), si
    ese proceso sigue vivo y es una página de esta copia. → {"puerto", "pid"} o None. (Solo para decir qué está
    prendido y para apagarla: sin su llave, el monito no le puede hablar; ella misma vuelve a escribir su archivo.)"""
    import re
    try:
        with open(os.path.join(carpeta(), "pagina.log"), "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 65536))
            texto = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    for m in reversed(list(re.finditer(r"página de esta copia: puerto (\d+) · pid (\d+)", texto))):
        puerto, pid = int(m.group(1)), int(m.group(2))
        if A._vivo(pid) and _es_pagina_rama(pid):
            return {"puerto": puerto, "pid": pid}
        return None
    return None


def _es_pagina_rama(pid):
    try:
        r = subprocess.run(["ps", "-o", "command=", "-p", str(int(pid))], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=5)
        return "pagina_rama.py" in (r.stdout or "")
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def prender_pagina(popen=subprocess.Popen, tope=30.0):
    """La página de esta copia, aparte (escritorio/pagina_rama.py): otro puerto, tu estado, sin servidor.json."""
    d = leer_pagina()
    if d:
        return d
    os.makedirs(carpeta(), exist_ok=True)
    os.chmod(carpeta(), 0o700)
    # lo que pasa en cada turno (escritorio/pagina_rama.anotar_turnos), solo para ti (600)
    ruta_log = os.path.join(carpeta(), "pagina.log")
    log = os.fdopen(os.open(ruta_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "ab")
    os.chmod(ruta_log, 0o600)                                 # también el de antes (se creó 644)
    from escritorio import cliente as C
    # sin la identidad de la terminal que lo corre (su panel de herdr, su pestaña, su sesión): con ella, la primera
    # corrida del monito registraba ese panel como su terminal y la página se negaba a escribir
    popen([sys.executable, os.path.join(AQUI, "pagina_rama.py"), ruta_pagina()], cwd=RAIZ, stdin=subprocess.DEVNULL,
          stdout=log, stderr=log, start_new_session=True, env=dict(C.entorno_limpio(), WORKSPACE_ROOT=RAIZ))
    fin = time.monotonic() + tope
    while time.monotonic() < fin:
        d = leer_pagina()
        if d:
            return d
        time.sleep(0.25)
    return None


def abrir(cerrar_el_abierto=False, salida=sys.stdout, actuar=""):
    if sys.platform != "darwin":
        salida.write(A.SIN_MAC + "\n")
        return 2
    pid = A.pid_abierto()
    if pid and not cerrar_el_abierto:
        salida.write("Ya hay un Workspace Compañero abierto (pid %d). Ciérralo antes («python3 %s cerrar» o desde su carita), o corre "
                     "esto con --cerrar-el-abierto.\n" % (pid, os.path.join(AQUI, "abrir.py")))
        return 1
    if pid:
        A.cerrar(salida=salida)
    d = prender_pagina()
    if not d:
        salida.write("No pude prender la página de esta copia (mira %s).\n" % os.path.join(carpeta(), "pagina.log"))
        return 1
    # A0 · actuar: apagado de fábrica (S3-a); en ensayo solo si lo pides (--actuar-ensayo)
    args = A.argumentos("", ["--actuar", "ensayo"] if actuar == "ensayo" else [])[1:]
    entorno = {k: os.environ[k] for k in A.ENTORNO if os.environ.get(k)}
    entorno[VAR_PAGINA] = ruta_pagina()
    entorno["WORKSPACE_ROOT"] = RAIZ
    quitar_la_de_antes(salida)
    # la app de prueba vive siempre en la misma carpeta y solo cambia si cambia su Swift (A.preparar); su firma: la
    # estable de desarrollo si ya existe (escritorio/firmar.py), si no ad hoc, y lo dice fuerte
    app, _que = A.preparar(args, destino=ruta_app(), build=A.scratch(carpeta()), entorno=entorno,
                           bundle_id=A.BUNDLE_ID_PRUEBA, nombre=A.NOMBRE_APP_PRUEBA, salida=salida,
                           aviso="Compilando el Compañero de esta copia (la primera vez, un par de minutos)…\n")
    if not app:
        salida.write("No pude armar el Compañero de esta copia.\n")
        return 1
    log = os.path.join(carpeta(), "app.log")
    r = subprocess.run(["open", "-n", "-g", "--stdout", log, "--stderr", log, app], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not A.esperar_pid():
        salida.write("No pude abrir el Compañero de esta copia.\n")
        return 1
    salida.write("Listo: el Compañero de esta copia («%s») está abierto, hablando con su página (puerto %d).\n"
                 "  Sus permisos son suyos: en Ajustes sale como «%s».\n"
                 "  ⌥ Espacio lo llama · para volver al de siempre: python3 %s cerrar && python3 %s\n"
                 % (A.NOMBRE_APP_PRUEBA, int(d["puerto"]), A.NOMBRE_APP_PRUEBA, os.path.abspath(__file__),
                    os.path.join(AQUI, "abrir.py")))
    return 0


def ruta_app():
    """La app de la copia de prueba: su nombre propio (el de Ajustes) y su identificador propio."""
    return os.path.join(carpeta(), A.NOMBRE_APP_PRUEBA + ".app")


def quitar_la_de_antes(salida=sys.stdout):
    """La app de prueba de antes (rama/MonitoEscritorio.app) llevaba el identificador del monito de siempre: dos
    paquetes con el mismo identificador y el permiso que das en Ajustes se va al otro. Se quita (es solo una
    compilación de esta carpeta) y se le dice a LaunchServices que la olvide. → True si había una."""
    import plistlib
    import shutil
    vieja = os.path.join(carpeta(), A.PRODUCTO + ".app")
    try:
        with open(os.path.join(vieja, "Contents", "Info.plist"), "rb") as fh:
            ident = plistlib.load(fh).get("CFBundleIdentifier")
    except (OSError, ValueError, plistlib.InvalidFileException):
        return False
    if ident not in (A.BUNDLE_ID, A.BUNDLE_ID_ANTES) or os.path.abspath(vieja) == os.path.abspath(A.ruta_app()):
        return False
    try:
        subprocess.run([LSREGISTER, "-u", vieja], capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass
    shutil.rmtree(vieja, ignore_errors=True)
    salida.write("Quité la app de prueba de antes (llevaba el identificador del Compañero de siempre).\n")
    return True


LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/"
              "lsregister")


def compilar(sw, salida, correr=subprocess.run):
    """Como abrir.compilar, pero en <estado>/escritorio/rama/build-<huella de ESTA copia> (nunca en la compilación de
    siempre, ni en la de otra copia: con el mismo Package.swift, SwiftPM reusaba el manifiesto de la otra y abría su app
    vieja con la burbuja nueva)."""
    return A.compilar_en(A.scratch(carpeta()), sw, correr=correr, salida=salida,
                         aviso="Compilando el Compañero de esta copia (la primera vez, un par de minutos)…\n")


def cerrar(salida=sys.stdout, tope=15.0):
    A.cerrar(salida=salida)
    d = leer_pagina() or pagina_por_su_registro()
    if d:
        pid = int(d["pid"])
        try:
            os.killpg(pid, signal.SIGTERM)
        except (OSError, ValueError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (OSError, ValueError):
                pass
        # que termine de apagarse (cierra sus motores) antes de volver: si no, abrir otra enseguida competía con ella
        fin = time.monotonic() + tope
        while A._vivo(pid) and time.monotonic() < fin:
            time.sleep(0.2)
        salida.write("Apagué la página de esta copia.\n")
        try:
            with open(ruta_pagina(), encoding="utf-8") as fh:
                suyo = int((json.load(fh) or {}).get("pid") or 0) in (pid, 0)
        except (OSError, ValueError, TypeError, AttributeError):
            suyo = True
        if suyo:
            try:
                os.remove(ruta_pagina())
            except OSError:
                pass
    return 0


def estado(salida=sys.stdout):
    d = leer_pagina()
    if d:
        pagina = "puerto %d (pid %d)" % (int(d["puerto"]), int(d["pid"]))
    else:
        r = pagina_por_su_registro()
        pagina = ("puerto %d (pid %d), sin su pagina.json (la vuelve a escribir sola en unos segundos; si no, "
                  "«cerrar» y abrir otra vez)" % (r["puerto"], r["pid"])) if r else "apagada"
    salida.write("Compañero: %s · página de esta copia: %s\n" % (
        ("abierto (pid %d)" % A.pid_abierto()) if A.pid_abierto() else "cerrado", pagina))
    return 0


def main(argv):
    if argv[:1] == ["cerrar"]:
        return cerrar()
    if argv[:1] == ["estado"]:
        return estado()
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    return abrir(cerrar_el_abierto="--cerrar-el-abierto" in argv, actuar="ensayo" if "--actuar-ensayo" in argv else "")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
