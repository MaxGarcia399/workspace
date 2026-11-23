"""AUTOMÁTICA: la app de escritorio ahora se llama «Workspace Compañero» (antes «Monito de Workspace»).

Con el nombre cambia su identificador de macOS (com.workspace.monito → com.workspace.companero; las copias de
desarrollo, ….dev y ….prueba, igual). macOS guarda los permisos (Accesibilidad, Grabación de pantalla, Automatización,
Micrófono, Reconocimiento de voz) por identificador y firma: la app nueva es OTRA app para macOS y los vuelve a pedir
una vez. Lo que NO puede pasar es que la app de antes se quede a medias (en Ajustes, en LaunchServices, abierta).

Qué hace, solo en la Mac y solo si hay rastro de la app de antes en ESTA carpeta de estado:

  1. Le pide a la app de antes que se cierre (SIGTERM a su pid anotado en <estado>/escritorio/app.pid, lo mismo que
     «abrir.py cerrar»). La nueva se arma y se abre la próxima vez que llames a Compañero (compilar no cabe aquí).
  2. Quita los paquetes de antes (escritorio/abrir.ARCHIVOS_APP_ANTES: «MonitoEscritorio.app», «dev/Monito de
     desarrollo.app», «rama/Monito de prueba.app») con sus registros de al lado (.instalada.json, .apps-…, .nueva.…,
     .vieja) y le dice a LaunchServices que los olvide. Son compilaciones: no llevan nada tuyo (por eso no hay
     respaldo; una versión anterior la vuelve a armar sola de sus fuentes).
  3. Borra SOLO los renglones de permisos del identificador de antes: `tccutil reset <servicio> com.workspace.monito`
     (y .dev / .prueba si existían), servicio por servicio. Nunca sin identificador, nunca otro identificador.
  4. Trae tus ajustes. Casi todo vive en <estado>/escritorio/ y NO se mueve (el lugar en pantalla: lugar.json y
     grande.json; lo que puede hacer cada agente y el sonido: ajustes.json; lo que hace sin preguntar:
     recordados.json; confianzas.json; vetados; elegido.json). Lo único que macOS guarda por identificador son dos
     interruptores del menú («Léeme las respuestas» y «Decir qué tengo enfrente»): se copian al identificador nuevo
     si ahí no están ya. Lo que macOS anotó de los permisos de antes (permiso.*) no se copia: eran de la otra app.
  5. Lo dice en UNA línea (TITLE; el hub la enseña al aplicar el ajuste) y deja <estado>/escritorio/renombre.json
     para que Compañero lo diga una vez al abrirse.

Idempotente: sin rastro de la app de antes no hace nada; correrla dos veces deja lo mismo. Los pasos 1, 3 y 4 hablan
con macOS (`tccutil` y `defaults` NO respetan $HOME): solo corren si el HOME de esta corrida es el del usuario de
verdad; con un HOME de prueba se saltan (las pruebas inyectan `CORRER`). En Windows y Linux no hay app: no hace falta.

Falla suave en lo de macOS (un `tccutil` que no está o dice que no): se anota y sigue; un renglón viejo en Ajustes
es feo pero no rompe nada, y detener la cola de ajustes por eso sería peor. Lo que sí lanza: no poder quitar un
paquete de antes (dos paquetes vivos es justo lo que no debe quedar).

Deshacer: no hay (la app de antes la arma sola una versión anterior; sus permisos se los vuelve a pedir macOS).
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time

TITLE = {"es": "Le cambié el nombre a Workspace Compañero; la Mac te va a pedir sus permisos una vez más",
         "en": "I renamed it to Workspace Companion; your Mac will ask for its permissions one more time"}
KIND = "auto"
MID = "202611222200_renombre_companero"

#: identificador de antes → el nuevo, con la carpeta (dentro de <estado>/escritorio) y el paquete de antes de ese canal.
CANALES = (
    ("com.workspace.monito", "com.workspace.companero", "", "MonitoEscritorio"),
    ("com.workspace.monito.dev", "com.workspace.companero.dev", "dev", "Monito de desarrollo"),
    ("com.workspace.monito.prueba", "com.workspace.companero.prueba", "rama", "Monito de prueba"),
)
#: La app de prueba MÁS vieja (rama/MonitoEscritorio.app) llevaba el identificador de siempre: también se va.
SUELTAS = ((os.path.join("rama", "MonitoEscritorio"), "com.workspace.monito"),)
#: Los servicios de permisos que la app usó (Permisos.swift, Voz.swift y sus entitlements). Nombres de `tccutil`.
SERVICIOS = ("Accessibility", "ScreenCapture", "AppleEvents", "Microphone", "SpeechRecognition")
#: Los interruptores que macOS guarda por identificador (UserDefaults.standard en Monito.swift y Voz.swift).
AJUSTES = ("leerRespuestas", "decirEnfrente")
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/"
              "lsregister")
#: Las pruebas lo cambian por uno de mentira: nunca corren `tccutil`, `defaults` ni `lsregister` de verdad.
CORRER = subprocess.run
#: Las pruebas lo fuerzan (True/False); None = se decide solo (¿es el HOME del usuario de verdad?).
ES_REAL = None
#: (las pruebas: uno de mentira)
MATAR = os.kill
ESPERA_CIERRE = 3.0


def _carpeta(ctx):
    return os.path.join(ctx.state_dir, "escritorio")


def _restos(ctx, rel, nombre):
    """Lo que dejó una app de antes en su carpeta: el paquete y sus registros de al lado."""
    base = os.path.join(_carpeta(ctx), rel) if rel else _carpeta(ctx)
    return [os.path.join(base, x) for x in (nombre + ".app", nombre + ".app.vieja", ".nueva." + nombre + ".app",
                                            nombre + ".instalada.json", ".apps-" + nombre)]


def _hallados(ctx):
    """[(identificador de antes, el nuevo o '', [rutas que existen])] de cada canal con rastro."""
    out = []
    for viejo, nuevo, rel, nombre in CANALES:
        hay = [r for r in _restos(ctx, rel, nombre) if os.path.lexists(r)]
        if hay:
            out.append((viejo, nuevo, hay))
    for rel, viejo in SUELTAS:
        d, n = os.path.split(rel)
        hay = [r for r in _restos(ctx, d, n) if os.path.lexists(r)]
        if hay:
            out.append((viejo, "", hay))
    return out


def _real(ctx):
    """¿Esta corrida es la del usuario de verdad en una Mac? `tccutil` y `defaults` no respetan $HOME: con un HOME de
    prueba tocarían lo del usuario real, así que ahí no se corren."""
    if ES_REAL is not None:
        return bool(ES_REAL)
    if sys.platform != "darwin":
        return False
    try:
        import pwd
        de_verdad = pwd.getpwuid(os.getuid()).pw_dir
    except Exception:
        return False
    return os.path.realpath(ctx.home) == os.path.realpath(de_verdad)


def needed(ctx):
    if sys.platform != "darwin" and ES_REAL is None:
        return False
    return bool(_hallados(ctx))


def _correr(cmd, tope=20):
    """(código, salida) de un comando del sistema; (None, por qué) si no se pudo ni lanzar."""
    try:
        r = CORRER(cmd, capture_output=True, text=True, timeout=tope)
        return r.returncode, (getattr(r, "stdout", "") or "")
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return None, str(e)


def _cerrar_la_de_antes(ctx):
    """SIGTERM al pid anotado, si su proceso es de un paquete de antes (nunca a otra cosa que reusó el número)."""
    ruta = os.path.join(_carpeta(ctx), "app.pid")
    try:
        with open(ruta, encoding="utf-8") as fh:
            pid = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return False
    if pid <= 1:
        return False
    codigo, salida = _correr(["/bin/ps", "-p", str(pid), "-o", "command="], tope=5)
    if codigo != 0 or not any(("/" + n + ".app/") in salida for _, _, _, n in CANALES):
        return False
    try:
        MATAR(pid, signal.SIGTERM)
    except OSError:
        return False
    fin = time.monotonic() + ESPERA_CIERRE
    while time.monotonic() < fin:
        try:
            MATAR(pid, 0)
        except OSError:
            break
        time.sleep(0.1)
    try:
        os.remove(ruta)
    except OSError:
        pass
    return True


def _quitar(ruta, real):
    if ruta.endswith(".app") and real:
        _correr([LSREGISTER, "-u", ruta])
    if os.path.isdir(ruta) and not os.path.islink(ruta):
        shutil.rmtree(ruta, ignore_errors=True)
    else:
        try:
            os.remove(ruta)
        except OSError:
            pass
    if os.path.lexists(ruta):
        raise RuntimeError("no pude quitar la app de antes (%s): ciérrala y vuelve a intentar" % ruta)


def _traer_ajustes(viejo, nuevo, log):
    """Los interruptores del identificador de antes → al nuevo, si el nuevo no los tiene ya. → cuántos trajo."""
    n = 0
    for k in AJUSTES:
        c, v = _correr(["/usr/bin/defaults", "read", viejo, k], tope=10)
        if c != 0 or v.strip() not in ("0", "1"):
            continue
        c2, _ = _correr(["/usr/bin/defaults", "read", nuevo, k], tope=10)
        if c2 == 0:
            continue                                # ya lo decidiste en la app nueva: no se pisa
        c3, _ = _correr(["/usr/bin/defaults", "write", nuevo, k, "-bool", "true" if v.strip() == "1" else "false"], tope=10)
        if c3 == 0:
            n += 1
        else:
            log("Compañero: no pude traer el ajuste «%s» (queda como de fábrica)." % k)
    return n


def run(ctx):
    hallados = _hallados(ctx)
    if not hallados:
        return
    if ctx.dry_run:
        for viejo, _nuevo, rutas in hallados:
            ctx.log("Compañero: se quitaría la app de antes (%s): %s" % (viejo, ", ".join(os.path.basename(r) for r in rutas)))
        return
    real = _real(ctx)
    if real:
        _cerrar_la_de_antes(ctx)
    ids = []
    for viejo, nuevo, rutas in hallados:
        for r in rutas:
            _quitar(r, real)
        if viejo not in [i for i, _ in ids]:
            ids.append((viejo, nuevo))
    traidos = 0
    if real:
        for viejo, nuevo in ids:
            if nuevo:
                traidos += _traer_ajustes(viejo, nuevo, ctx.log)
            for s in SERVICIOS:
                c, _ = _correr(["/usr/bin/tccutil", "reset", s, viejo], tope=15)
                if c != 0:
                    ctx.log("Compañero: macOS no borró el permiso de antes (%s · %s); puedes quitarlo en Ajustes." % (s, viejo))
    # para que Compañero lo diga UNA vez al abrirse (la app lo borra al decirlo); el hub ya enseña TITLE
    aviso = os.path.join(_carpeta(ctx), "renombre.json")
    try:
        os.makedirs(_carpeta(ctx), exist_ok=True)
        tmp = aviso + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "de": [i for i, _ in ids], "aviso": TITLE, "dicho": False,
                       "ajustes_traidos": traidos, "cuando": int(time.time())}, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, aviso)
    except OSError:
        pass
    ctx.log(TITLE["es"])
