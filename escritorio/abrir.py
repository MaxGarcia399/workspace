#!/usr/bin/env python3
"""WORKSPACE · escritorio/abrir — compila Workspace Compañero (la app de escritorio, Swift) y la abre en la esquina.
Solo Mac, por ahora. («monito» es el personaje que ves en pantalla; la app se llama Workspace Compañero.)

    python3 escritorio/abrir.py              compila si hace falta y abre el monito (⌥ Espacio para llamarlo)
    python3 escritorio/abrir.py cerrar       cierra el monito
    python3 escritorio/abrir.py compilar     solo compila (para ver errores)
    python3 escritorio/abrir.py estado       qué app del monito hay y si su firma conserva los permisos
    python3 escritorio/abrir.py --primer-plano   abre y se queda en esta terminal (Ctrl+C lo cierra)
    python3 escritorio/abrir.py --demo       el monito te enseña cómo señala: vuela a tres lugares de tu pantalla
    python3 escritorio/abrir.py --demo permisos   la tarjeta con la que pide un permiso de la Mac
        (el demo solo se pide al abrirlo, por la línea de comando: su puerto local no tiene una ruta de demo)

Compila con `swift build` (las herramientas de línea de comandos de Apple; sin Xcode) en la carpeta de estado de
Workspace, no en el repo. La primera vez tarda un par de minutos; después, segundos.
La abre como app («Workspace Compañero.app», armada en esa misma carpeta, por LaunchServices): así los permisos de la Mac
que piden sus manos (Accesibilidad, Grabación de pantalla) quedan a nombre del monito y no de tu terminal.
Los permisos van atados a la firma de la app (escritorio/firmar.py). Por eso la app instalada de cada canal (una
carpeta fija: la de siempre y la de probar una rama) solo cambia de binario cuando cambian sus fuentes de Swift
(huella_fuentes: Sources/, Package.swift, Package.resolved). Con las mismas fuentes no se compila ni se toca: la misma
firma, y macOS reconoce los permisos que ya diste (también al cambiar de copia o de rama, si su Swift es igual).
Stdlib."""
import hashlib
import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
import paths  # noqa: E402
from escritorio import firmar as F  # noqa: E402

PAQUETE = os.path.join(AQUI, "mac")
HTML = os.path.join(AQUI, "web", "monito.html")
PUENTE = os.path.join(AQUI, "puente.py")
PRODUCTO = "MonitoEscritorio"
BUNDLE_ID = "com.workspace.companero"
NOMBRE_APP = "Workspace Compañero"
#: El nombre corto (CFBundleName: el de la barra de menú y los avisos de macOS).
NOMBRE_CORTO = "Compañero"
#: El ARCHIVO del paquete lleva el MISMO nombre que se ve (con su «ñ»). Medido el 22-nov en macOS 26.5: con un archivo
#: sin «ñ» («WorkspaceCompanero.app») Finder, Spotlight y FileManager.displayName enseñan el nombre del ARCHIVO, no el
#: CFBundleDisplayName (ni con InfoPlist.strings). Con «ñ» la ruta se guarda y se lee igual (NFC) en APFS, y codesign la
#: firma sin más. Solo existe en la Mac (Windows nunca arma este paquete). Si un día estorba, se cambia aquí.
ARCHIVO_APP = NOMBRE_APP + ".app"
#: Antes del renombre (22-nov-2026): lo que la migración 202611222200 quita y de donde trae los ajustes.
BUNDLE_ID_ANTES = "com.workspace.monito"
ARCHIVOS_APP_ANTES = ("MonitoEscritorio.app", os.path.join("dev", "Monito de desarrollo.app"),
                      os.path.join("rama", "Monito de prueba.app"))
#: La copia de probar una rama (escritorio/probar_rama.py): su propio identificador y su propio nombre. macOS guarda los
#: permisos (Accesibilidad, Grabación de pantalla) por identificador y firma: con dos paquetes con el mismo
#: identificador, el permiso que das en Ajustes se va a la otra copia. Nunca dos paquetes con el mismo.
BUNDLE_ID_PRUEBA = "com.workspace.companero.prueba"
NOMBRE_APP_PRUEBA = "Workspace Compañero de prueba"
#: Desde una copia de DESARROLLO (escritorio/firma_dev.py existe; no viaja a clientes), abrir.py arma esta otra: un
#: permiso de una nunca vale para la otra, y el identificador de los clientes nunca se firma con una llave de desarrollo.
BUNDLE_ID_DEV = "com.workspace.companero.dev"
NOMBRE_APP_DEV = "Workspace Compañero de desarrollo"
#: La identidad que crea escritorio/mac/firmar_local.sh (en el llavero de inicio de sesión; = firma_dev.LOCAL).
IDENTIDAD = "Workspace Monito local"
#: Lo que la app necesita de este entorno (LaunchServices no lo hereda): va en su paquete, también para reabrirse.
ENTORNO = ("HOME", "PATH", "LANG", "LC_ALL", "WORKSPACE_ROOT", "WORKSPACE_NO_AUTOUPDATE", "WORKSPACE_MANOS_SIN_PERMISOS",
           "WORKSPACE_ESCRITORIO_PAGINA")

SIN_MAC = "Workspace Compañero por ahora es solo para la Mac."
SIN_SWIFT = ("No encuentro Swift para compilar Workspace Compañero.\n"
             "Instala las herramientas de línea de comandos de Apple (no hace falta Xcode):\n"
             "    xcode-select --install\n"
             "y vuelve a correr este comando.")


def carpeta():
    return os.path.join(paths.state_dir(), "escritorio")


def ruta_pid():
    return os.path.join(carpeta(), "app.pid")


def swift(which=shutil.which):
    return which("swift")


def _vivo(pid):
    """¿Vive ese proceso? Por control/hijos.vivo: en Windows `os.kill(pid, 0)` no pregunta (la señal 0 es
    CTRL_C_EVENT: un Ctrl+C a la consola); ahí va por la API de Windows."""
    try:
        from control import hijos
    except ImportError:
        hijos = None
    if hijos is not None:
        return bool(hijos.vivo(pid))
    if os.name == "nt":
        return False                    # sin poder saberlo sin señales: no se afirma
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False


def pid_abierto():
    """El pid del monito que ya corre, o 0."""
    try:
        with open(ruta_pid(), encoding="utf-8") as fh:
            pid = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return 0
    return pid if pid > 0 and _vivo(pid) else 0


def scratch(base=None, paquete=None):
    """La carpeta de compilación de ESTA copia del paquete, una por ruta: <base>/build-<huella de su ruta>. SwiftPM
    guarda su manifiesto (release.yaml) en la carpeta de compilación y, con el mismo Package.swift, reusaba el de OTRA
    copia: compilaba las fuentes de la otra (lo que le pasó al «Monito de prueba» el 22-nov: una app vieja con la
    burbuja nueva, sin «encargar» ni los botones de la entrega)."""
    paquete = os.path.realpath(paquete or PAQUETE)
    return os.path.join(base or carpeta(), "build-" + hashlib.sha1(paquete.encode("utf-8")).hexdigest()[:10])


#: Las fuentes que nombra el manifiesto de SwiftPM (entre comillas, rutas enteras).
_FUENTE_EN_MANIFIESTO = re.compile(r'"(/[^"\n]*/Sources/MonitoEscritorio/[^"/\n]+\.swift)"')


def limpiar_ajeno(build, paquete=None, todo=False):
    """Si el manifiesto de SwiftPM de `build` nombra fuentes de otra copia (o `todo`), se quita: SwiftPM lo vuelve a
    armar con las de esta. → True si quitó alguno."""
    paquete = os.path.realpath(paquete or PAQUETE)
    quito = False
    for nombre in ("release.yaml", "debug.yaml"):
        ruta = os.path.join(build, nombre)
        try:
            with open(ruta, encoding="utf-8", errors="replace") as fh:
                texto = fh.read()
        except OSError:
            continue
        ajenas = [f for f in _FUENTE_EN_MANIFIESTO.findall(texto)
                  if not os.path.realpath(f).startswith(paquete + os.sep)]
        if todo or ajenas:
            try:
                os.remove(ruta)
                quito = True
            except OSError:
                pass
    return quito


def manifiesto_propio(build, paquete=None):
    """¿El manifiesto de SwiftPM de `build` nombra fuentes y todas son de ESTA copia?"""
    paquete = os.path.realpath(paquete or PAQUETE)
    try:
        with open(os.path.join(build, "release.yaml"), encoding="utf-8", errors="replace") as fh:
            fuentes = _FUENTE_EN_MANIFIESTO.findall(fh.read())
    except OSError:
        return False
    return bool(fuentes) and all(os.path.realpath(f).startswith(paquete + os.sep) for f in fuentes)


def mas_viejo_que_sus_fuentes(exe, paquete=None):
    """¿El programa quedó más viejo que alguna de SUS fuentes (Sources/ y Package.swift)? Tras un `swift build` que
    salió bien, eso solo pasa si compiló otra cosa (el manifiesto de otra copia)."""
    paquete = paquete or PAQUETE
    try:
        t = os.path.getmtime(exe)
    except OSError:
        return True
    fuentes = [os.path.join(paquete, "Package.swift")]
    for base, _d, archivos in os.walk(os.path.join(paquete, "Sources")):
        fuentes += [os.path.join(base, a) for a in archivos if a.endswith(".swift")]
    for f in fuentes:
        try:
            if os.path.getmtime(f) > t + 1:
                return True
        except OSError:
            continue
    return False


VIEJA = ("La compilación de Workspace Compañero quedó más vieja que sus fuentes (%s): no la abro, sería otra versión de la que "
         "ves. Borra esa carpeta y vuelve a correr esto.")


def compilar_en(build, sw, correr=subprocess.run, salida=sys.stdout, aviso=None, paquete=None):
    """`swift build -c release` de ESTA copia en `build` (una carpeta suya: scratch). Sin el manifiesto de otra copia;
    si tras compilar el programa sigue más viejo que sus fuentes, una vez más sin manifiesto; si aun así, no se abre.
    → ruta del ejecutable, o None (y el error ya se dijo)."""
    paquete = paquete or PAQUETE
    os.makedirs(build, exist_ok=True)
    base = [sw, "build", "-c", "release", "--package-path", paquete, "--scratch-path", build]
    limpiar_ajeno(build, paquete)
    if aviso:
        salida.write(aviso)
        salida.flush()
    exe = ""
    for intento in (1, 2):
        r = correr(base, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            salida.write("No se pudo compilar Workspace Compañero:\n%s\n" % ((r.stderr or r.stdout or "").strip()[-3000:]))
            return None
        b = correr(base + ["--show-bin-path"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        exe = os.path.join((b.stdout or "").strip(), PRODUCTO) if b.returncode == 0 else ""
        if not exe or not os.path.exists(exe):
            return None
        if not mas_viejo_que_sus_fuentes(exe, paquete) or manifiesto_propio(build, paquete):
            # (más viejo pero con el manifiesto de ESTA copia: SwiftPM no reenlaza si el binario no cambió, p. ej. un
            # cambio solo de comentarios; lo de verdad peligroso es el manifiesto de otra copia)
            return exe
        if intento == 1:
            limpiar_ajeno(build, paquete, todo=True)            # lo que compiló no era esta copia: el manifiesto, de nuevo
    salida.write(VIEJA % build + "\n")
    return None


def _viejo(exe):
    """¿Alguna fuente es más nueva que el ejecutable? (para decir «compilando…»; swift decide de verdad)."""
    return mas_viejo_que_sus_fuentes(exe)


def compilar(sw, correr=subprocess.run, salida=sys.stdout):
    """`swift build -c release` en la carpeta de estado (la de ESTA copia: scratch). → ruta del ejecutable, o None."""
    build = scratch(carpeta())
    aviso = "Compilando Workspace Compañero (la primera vez tarda un par de minutos)…\n"
    b = correr([sw, "build", "-c", "release", "--package-path", PAQUETE, "--scratch-path", build, "--show-bin-path"],
               capture_output=True, text=True, encoding="utf-8", errors="replace") if os.path.isdir(build) else None
    exe = os.path.join((b.stdout or "").strip(), PRODUCTO) if b is not None and b.returncode == 0 else ""
    if exe and os.path.exists(exe) and not _viejo(exe):
        aviso = None
    return compilar_en(build, sw, correr=correr, salida=salida, aviso=aviso)


def argumentos(exe, extra=()):
    return [exe, "--html", HTML, "--python", sys.executable or "python3", "--puente", PUENTE, "--raiz", RAIZ,
            "--estado", carpeta()] + list(extra)


# ── la app de verdad (para que los permisos de la Mac sean del monito) ──────
def de_desarrollo():
    """¿Esta copia es de desarrollo? (trae el puente de firma de desarrollo, que make-dist quita)."""
    return F.puente_dev() is not None


def canal():
    """(identificador, nombre en Ajustes, ruta de la app) del monito de siempre de ESTA copia: el de los clientes, o
    el de desarrollo (su propia carpeta: nunca dos identificadores en el mismo paquete)."""
    if de_desarrollo():
        return BUNDLE_ID_DEV, NOMBRE_APP_DEV, os.path.join(carpeta(), "dev", NOMBRE_APP_DEV + ".app")
    return BUNDLE_ID, NOMBRE_APP, os.path.join(carpeta(), ARCHIVO_APP)


def ruta_app():
    return canal()[2]


def _bytes(ruta):
    try:
        with open(ruta, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def identidad(correr=subprocess.run, bundle_id=BUNDLE_ID_PRUEBA):
    """Con qué se firmaría ese identificador (escritorio/firmar.elegir): «-» es ad hoc."""
    return F.elegir(correr, bundle_id=bundle_id)["firma"]


def firmar(app, correr=subprocess.run, bundle_id=BUNDLE_ID, hecha=None):
    """Firma el paquete (escritorio/firmar: Developer ID > identidad local > ad hoc). → lo que va en --sign, o None.
    `hecha` (un dict), si se da, se llena con la elección con que quedó."""
    e = F.firmar(app, bundle_id, correr=correr)
    if e is None:
        return None
    if hecha is not None:
        hecha.update(e)
    return e["firma"]


def ruta_opciones(app):
    """Las opciones de arranque de una app: AL LADO del paquete (MonitoEscritorio.opciones.json), nunca dentro. Con
    firma ad hoc, cualquier byte que cambie dentro del paquete lo vuelve «otra app» para macOS y te vuelve a pedir los
    permisos; así el paquete firmado queda idéntico entre arranques (solo cambia al compilar)."""
    return os.path.join(os.path.dirname(os.path.abspath(app)), PRODUCTO + ".opciones.json")


#: Voz (escritorio/mac/Sources/MonitoEscritorio/Voz.swift): lo que dice macOS en sus dos avisos. Sin estas frases, macOS
#: cierra la app en cuanto pide el permiso. Dicen solo lo que pasa: se dicta en tu Mac y nada se manda solo.
FRASE_MICROFONO = ("Para dictarle a tu agente en vez de escribir. Tu voz se vuelve texto en tu Mac y no sale de ella; "
                   "solo se oye mientras tienes prendido el micrófono de Compañero.")
FRASE_RECONOCIMIENTO = ("Para convertir en texto lo que dictas, aquí en tu Mac. Tu voz no se manda a Apple ni a nadie, "
                        "y el texto cae en la caja para que tú lo revises y lo mandes.")


def info_plist(bundle_id=BUNDLE_ID, nombre=NOMBRE_APP):
    """El Info.plist del paquete (bytes): solo lo de este canal, nada de la máquina (va sellado con la firma)."""
    plist = {"CFBundleIdentifier": bundle_id, "CFBundleName": NOMBRE_CORTO if nombre == NOMBRE_APP else nombre,
             "CFBundleDisplayName": nombre,
             "CFBundleExecutable": PRODUCTO, "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "1.0",
             "CFBundleVersion": "1", "LSUIElement": True, "LSMinimumSystemVersion": "14.0",
             "NSHighResolutionCapable": True,
             # A0: lo que macOS enseña en su aviso de Automatización (una vez por app, solo si una acción lo necesita)
             "NSAppleEventsUsageDescription": "Para manejar esa app por ti cuando se lo pidas a tu agente, y siempre "
                                              "con tu OK en su ficha.",
             # Voz: lo que macOS enseña al pedir el Micrófono (solo la primera vez que tocas el micrófono del monito)
             "NSMicrophoneUsageDescription": FRASE_MICROFONO,
             # Solo en macOS 14 y 15 (en macOS 26 no se pide): el reconocedor de la Mac, obligado a transcribir en ella
             "NSSpeechRecognitionUsageDescription": FRASE_RECONOCIMIENTO}
    return plistlib.dumps(plist)


def escribir_opciones(app, args, entorno=None):
    """Los argumentos y el entorno de la app, AL LADO del paquete (600): cambian sin tocar el paquete firmado."""
    env = entorno if entorno is not None else {k: os.environ[k] for k in ENTORNO if os.environ.get(k)}
    datos = json.dumps({"args": list(args), "env": env}, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8")
    os.makedirs(os.path.dirname(os.path.abspath(app)), exist_ok=True)
    ruta = ruta_opciones(app)
    if _bytes(ruta) != datos:
        tmp = ruta + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(datos)
        os.replace(tmp, ruta)


def armar_app(exe, args, destino=None, correr=subprocess.run, bundle_id=BUNDLE_ID, entorno=None, nombre=NOMBRE_APP,
              hecha=None):
    """Arma (o pone al día) «Workspace Compañero.app»: el ejecutable y su Info.plist, nada más (lo mismo en cualquier
    máquina). Sus opciones (los argumentos y el entorno, para que también se pueda reabrir sola desde Ajustes) van al
    lado del paquete (ruta_opciones). Solo firma si el paquete cambió (`hecha`: con qué, si firmó). → la ruta, o None."""
    app = destino or ruta_app()
    cont = os.path.join(app, "Contents")
    piezas = [(os.path.join(cont, "MacOS", PRODUCTO), _bytes(exe)),
              (os.path.join(cont, "Info.plist"), info_plist(bundle_id, nombre))]
    if piezas[0][1] is None:
        return None
    escribir_opciones(app, args, entorno)
    cambio = False
    vieja = os.path.join(cont, "Resources", "opciones.json")         # las de antes, dentro: se van (una vez)
    if os.path.exists(vieja):
        os.remove(vieja)
        cambio = True
    for ruta, datos in piezas:
        if _bytes(ruta) != datos:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            with open(ruta, "wb") as fh:
                fh.write(datos)
            cambio = True
    os.chmod(piezas[0][0], 0o755)
    if cambio or not _firma_valida(app, correr):
        if not firmar(app, correr, bundle_id, hecha=hecha):
            return None
    return app


def _firma_valida(app, correr=subprocess.run):
    try:
        return correr(["codesign", "--verify", app], capture_output=True, text=True, encoding="utf-8").returncode == 0
    except OSError:
        return False


# ── la app instalada de cada canal: una carpeta fija; su binario solo cambia si cambia lo que lo arma ──────────────
# Ojo: esto ahorra compilaciones y conserva la firma cuando el Swift es el mismo (reabrir, cambiar de copia o de rama
# con el mismo Swift, actualizar la burbuja o Python). Con firma ad hoc, un Swift distinto SIEMPRE es otra app para
# macOS: lo que de verdad conserva los permisos es una firma estable (escritorio/firmar.py).
#: Cómo se arma el binario. Si cambia la receta (no las fuentes), sube esto: se vuelve a compilar una vez.
RECETA = "swift build -c release · 1"
#: Cuántas apps ya firmadas se guardan por huella (volver a una rama de antes no recompila).
GUARDADAS = 3


def huella_fuentes(paquete=None, plist=b""):
    """La huella de lo que decide el paquete: Sources/ (todo), Package.swift, Package.resolved y su Info.plist, por
    contenido (no por fecha ni por ruta: dos copias con el mismo Swift dan la misma). Lo demás (la burbuja, Python, las
    pruebas, las reglas) cambia sin tocar la app."""
    paquete = paquete or PAQUETE
    h = hashlib.sha256(RECETA.encode("utf-8"))
    h.update(b"Info.plist\0" + hashlib.sha256(plist).digest())
    # lo que la app pide al firmarse con Developer ID (el micrófono, Apple Events): si cambia, se firma de nuevo
    h.update(b"entitlements\0" + hashlib.sha256(_bytes(F.PERMISOS_APP) or b"").digest())
    archivos = [os.path.join(paquete, n) for n in ("Package.swift", "Package.resolved")]
    for base, dirs, fs in os.walk(os.path.join(paquete, "Sources")):
        dirs.sort()
        archivos += [os.path.join(base, f) for f in sorted(fs) if not f.startswith(".")]
    for f in archivos:
        datos = _bytes(f)
        h.update(os.path.relpath(f, paquete).replace(os.sep, "/").encode("utf-8") + b"\0"
                 + (b"-" if datos is None else hashlib.sha256(datos).digest()))
    return h.hexdigest()


def version_swift(sw, correr=subprocess.run):
    """`swift --version` (la primera línea), o "" si no hay. Con otro compilador, otro binario."""
    if not sw:
        return ""
    try:
        r = correr([sw, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    lineas = ((r.stdout or "") + (r.stderr or "")).strip().splitlines() if r.returncode == 0 else []
    return lineas[0].strip() if lineas else ""


def ruta_instalada(app):
    """Lo que se sabe de la app instalada (de qué fuentes salió, su binario y su firma): AL LADO del paquete."""
    return os.path.splitext(os.path.abspath(app))[0] + ".instalada.json"


def _sha(ruta):
    d = _bytes(ruta)
    return hashlib.sha256(d).hexdigest() if d is not None else ""


def _leer_json(ruta):
    try:
        with open(ruta, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir_json(ruta, d):
    fd = os.open(ruta + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(ruta + ".tmp", ruta)


def leer_instalada(app):
    return _leer_json(ruta_instalada(app))


def _al_dia(rec, contenido, huella, swift_v):
    """¿Ese paquete (`contenido`: la carpeta Contents) salió de ESTAS fuentes, con este compilador, y nadie le cambió
    el binario? (otra copia con código de antes sí lo cambia: entonces no se le cree a su registro)."""
    exe = os.path.join(contenido, "MacOS", PRODUCTO)
    return bool(rec) and rec.get("huella") == huella and rec.get("exe") == _sha(exe) != "" \
        and (not swift_v or rec.get("swift") == swift_v)


def _carpeta_guardadas(app):
    return os.path.join(os.path.dirname(os.path.abspath(app)), ".apps-" + os.path.splitext(os.path.basename(app))[0])


def _guardar(app, rec):
    """Guarda una copia del paquete ya firmado por su huella (solo su carpeta Contents: sin «.app», LaunchServices no
    la toma por otra app con el mismo identificador). Las de más se van."""
    base = _carpeta_guardadas(app)
    dest = os.path.join(base, rec["huella"][:16])
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    shutil.copytree(os.path.join(app, "Contents"), os.path.join(dest, "Contents"), symlinks=True)
    _escribir_json(os.path.join(dest, "instalada.json"), rec)
    viejas = sorted((os.path.join(base, n) for n in os.listdir(base)), key=os.path.getmtime, reverse=True)
    for v in viejas[GUARDADAS:]:
        shutil.rmtree(v, ignore_errors=True)


def _de_guardadas(app, huella, swift_v):
    """Una app ya firmada de estas mismas fuentes (de una vez anterior) → (carpeta con Contents, su registro) o None."""
    dest = os.path.join(_carpeta_guardadas(app), huella[:16])
    rec = _leer_json(os.path.join(dest, "instalada.json"))
    return (dest, rec) if _al_dia(rec, os.path.join(dest, "Contents"), huella, swift_v) else None


def _aparte(app):
    """Dónde se arma la app nueva: junto a la instalada (para cambiarlas de un golpe), escondida."""
    return os.path.join(os.path.dirname(os.path.abspath(app)), ".nueva." + os.path.basename(app))


def _cambiar(nueva, app):
    """La app nueva entra de un golpe: la de antes se aparta y la nueva toma su lugar (dos renombres en la misma
    carpeta); nunca se reescribe el binario de una app que puede estar abierta (la que corre sigue con el suyo)."""
    vieja = os.path.abspath(app) + ".vieja"
    shutil.rmtree(vieja, ignore_errors=True)
    if os.path.lexists(app):
        os.rename(app, vieja)
    os.rename(nueva, app)
    shutil.rmtree(vieja, ignore_errors=True)


def _anotar_instalada(app, huella, swift_v, hecha, correr, paquete):
    import datetime
    d = {"huella": huella, "swift": swift_v, "exe": _sha(os.path.join(app, "Contents", "MacOS", PRODUCTO)),
         "firma": hecha.get("firma", ""), "tipo": hecha.get("tipo", ""), "nombre_firma": hecha.get("nombre", ""),
         "equipo": hecha.get("equipo", ""), "requisito": F.requisito(app, correr), "cdhash": F.cdhash(app, correr),
         "denegada": hecha.get("denegada", ""), "sello": bool(hecha.get("sello")),
         "desde": os.path.realpath(paquete), "cuando": datetime.datetime.now().isoformat(timespec="seconds")}
    _escribir_json(ruta_instalada(app), d)
    return d


#: Lo que se dice al preparar la app (una línea; la de ad hoc, fuerte).
IGUAL = "Uso el mismo Workspace Compañero que ya tenías (su Swift no cambió): no lo toqué, así macOS lo sigue reconociendo.\n"
DE_ANTES = "Uso el Workspace Compañero que ya había armado con este mismo Swift (no recompilé).\n"
ESTABLE = ("Firmé Workspace Compañero con %s (una firma estable): si macOS te pide su permiso, es la última vez; se queda aunque "
           "cambie su Swift.\n")
#: Antes de firmar con un certificado de Apple: lo que va a preguntar macOS.
LLAVE = ("Voy a firmar Workspace Compañero con tu %s. Si macOS pregunta «codesign quiere usar la llave…», elige «Permitir» (no "
         "«Permitir siempre»).\n")
#: De peor a mejor para conservar los permisos: ad hoc cambia con cada binario; las demás, no.
RANGO = {"adhoc": 0, "manual": 1, "local": 1, "apple_development": 2, "developer_id": 3}


def _rango(rec):
    return RANGO.get(rec.get("tipo") or ("adhoc" if rec.get("firma") in ("-", "") else "local"), 0)


def _mejor(e, rec):
    """¿Vale la pena volver a firmar un paquete al día con la elección `e`? Solo si es mejor que la suya (por ejemplo,
    llegó la firma propia o un certificado de Apple) o si la pediste a mano (WORKSPACE_MONITO_FIRMA). Nunca a una peor:
    una firma ya hecha sigue valiendo aunque su identidad ya no esté en el llavero, y bajarla a ad hoc te volvería a
    pedir los permisos."""
    if e["firma"] == rec.get("firma") or e["firma"] == rec.get("denegada"):     # (dijiste «Denegar» a esa llave)
        return False
    if os.environ.get(F.VAR):
        return True
    return RANGO.get(e["tipo"], 0) > _rango(rec)


def _antes_de_firmar(salida, e):
    if e["tipo"] in ("developer_id", "apple_development"):
        salida.write(LLAVE % F.en_simple(e["tipo"], e.get("equipo", "")))
        salida.flush()


def _decir_firma(salida, hecha, bundle_id):
    if hecha.get("aviso"):
        salida.write(hecha["aviso"] + "\n")
    if hecha.get("tipo") == "adhoc":
        if not hecha.get("denegada"):
            salida.write(F.aviso_adhoc(bundle_id) + "\n")
    else:
        salida.write(ESTABLE % F.en_simple(hecha["tipo"], hecha.get("equipo", ""), hecha.get("nombre", "")))


def preparar(args, destino=None, build=None, sw=None, bundle_id=BUNDLE_ID, nombre=NOMBRE_APP, entorno=None,
             correr=subprocess.run, salida=sys.stdout, aviso=None, paquete=None):
    """La app instalada de este canal (`destino`, una carpeta fija), al día con las fuentes de ESTA copia, sin
    cambiarle la identidad si no hace falta:
      · las mismas fuentes que la instalada → no compila ni toca el paquete (la misma firma);
      · las mismas, pero ahora hay con qué firmar mejor (la firma propia, un certificado de Apple) → otra firma, una vez;
      · unas fuentes que ya se armaron antes (otra rama, de vuelta) → esa app ya firmada, sin compilar;
      · otras fuentes → compila en la carpeta de esta copia (`build`).
    Lo nuevo se arma APARTE y se cambia de un golpe. Sus opciones (args, entorno) van siempre al lado del paquete.
    → (app, qué pasó: igual | refirmada | guardada | nueva), o (None, "")."""
    app = destino or ruta_app()
    paquete = paquete or PAQUETE
    sw = sw or swift()
    plist = info_plist(bundle_id, nombre)
    huella, swift_v = huella_fuentes(paquete, plist), version_swift(sw, correr)
    escribir_opciones(app, args, entorno)
    nueva = _aparte(app)
    shutil.rmtree(nueva, ignore_errors=True)
    e = F.elegir(correr, bundle_id=bundle_id)
    rec = leer_instalada(app)
    guardada = None
    if _al_dia(rec, os.path.join(app, "Contents"), huella, swift_v) \
            and _bytes(os.path.join(app, "Contents", "Info.plist")) == plist:
        if _firma_valida(app, correr) and not _mejor(e, rec):
            salida.write(IGUAL)
            return app, "igual"
        shutil.copytree(app, nueva, symlinks=True)
        que = "refirmada"
    elif _de_guardadas(app, huella, swift_v):
        lista, guardada = _de_guardadas(app, huella, swift_v)
        os.makedirs(nueva)
        shutil.copytree(os.path.join(lista, "Contents"), os.path.join(nueva, "Contents"), symlinks=True)
        if _firma_valida(nueva, correr) and not _mejor(e, guardada):
            import datetime
            _cambiar(nueva, app)
            _escribir_json(ruta_instalada(app), dict(guardada, desde=os.path.realpath(paquete),
                                                     cuando=datetime.datetime.now().isoformat(timespec="seconds")))
            salida.write(DE_ANTES)
            if guardada.get("tipo") == "adhoc":            # ad hoc: otra app para macOS que la que estaba
                salida.write(F.aviso_adhoc(bundle_id) + "\n")
            return app, "guardada"
        que = "refirmada"
    else:
        if not sw:
            salida.write(SIN_SWIFT + "\n")
            return None, ""
        exe = compilar_en(build or scratch(os.path.dirname(os.path.abspath(app)), paquete), sw, correr=correr,
                          salida=salida, aviso=aviso, paquete=paquete)
        if not exe:
            return None, ""
        hecha = {}
        _antes_de_firmar(salida, e)
        if not armar_app(exe, args, destino=nueva, correr=correr, bundle_id=bundle_id, entorno=entorno, nombre=nombre,
                         hecha=hecha):
            shutil.rmtree(nueva, ignore_errors=True)
            return None, ""
        _cambiar(nueva, app)
        rec = _anotar_instalada(app, huella, swift_v, hecha, correr, paquete)
        _guardar(app, rec)
        _decir_firma(salida, hecha, bundle_id)
        return app, "nueva"
    hecha = {}
    _antes_de_firmar(salida, e)
    previa = guardada or rec
    if not firmar(nueva, correr, bundle_id, hecha=hecha):
        shutil.rmtree(nueva, ignore_errors=True)
        return None, ""
    if RANGO.get(hecha.get("tipo"), 0) <= _rango(previa) and guardada is None and not os.environ.get(F.VAR):
        # no salió mejor (dijiste «Denegar»): se queda la que estaba, con su firma (nunca bajarla), y no se vuelve a
        # preguntar con estas mismas fuentes
        shutil.rmtree(nueva, ignore_errors=True)
        _escribir_json(ruta_instalada(app), dict(rec, denegada=hecha.get("denegada", e["firma"])))
        if hecha.get("aviso"):
            salida.write(hecha["aviso"] + "\n")
        return app, "igual"
    _cambiar(nueva, app)
    rec = _anotar_instalada(app, huella, swift_v, hecha, correr, paquete)
    _guardar(app, rec)
    _decir_firma(salida, hecha, bundle_id)
    return app, que


def estado_firma(app):
    """Lo que el doctor y `abrir.py estado` dicen de la app instalada: {"hay", "estable", "tipo", "nombre_firma",
    "requisito", "desde", "cuando"}."""
    rec = leer_instalada(app)
    if not os.path.isdir(app) or not rec:
        return {"hay": os.path.isdir(app), "estable": False, "tipo": ""}
    return {"hay": True, "estable": F.es_estable(rec.get("requisito", "")), "tipo": rec.get("tipo", ""),
            "equipo": rec.get("equipo", ""),
            "nombre_firma": rec.get("nombre_firma", ""), "requisito": rec.get("requisito", ""),
            "desde": rec.get("desde", ""), "cuando": rec.get("cuando", "")}


def linea_firma(nombre, app):
    """«Workspace Compañero de prueba: firma estable (Workspace Monito local)» o «… ad hoc (macOS vuelve a pedir…)»."""
    e = estado_firma(app)
    if not e["hay"]:
        return ""
    if not e.get("requisito"):
        return "%s: firma sin revisar (ábrelo una vez con esta versión)" % nombre
    if e["estable"]:
        return "%s: firma %s · estable" % (nombre, F.en_simple(e["tipo"], e.get("equipo", ""), e.get("nombre_firma", "")))
    return "%s: firma ad hoc (macOS vuelve a pedir sus permisos cada vez que cambia su Swift)" % nombre


def esperar_pid(antes=0, tope=8.0):
    """El pid que anota la app al arrancar (distinto de `antes`), o 0."""
    fin = time.monotonic() + tope
    while time.monotonic() < fin:
        pid = pid_abierto()
        if pid and pid != antes:
            return pid
        time.sleep(0.1)
    return 0


def abrir(primer_plano=False, extra=(), sw=None, popen=subprocess.Popen, salida=sys.stdout, correr=subprocess.run,
          al_abrir=()):
    """`extra`: argumentos que se guardan al lado del paquete (valen también si Ajustes la reabre). `al_abrir`: solo
    para esta vez (el demo), por `open --args`: no se guardan."""
    if sys.platform != "darwin":
        salida.write(SIN_MAC + "\n")
        return 2
    sw = sw or swift()
    if not sw:
        salida.write(SIN_SWIFT + "\n")
        return 2
    pid = pid_abierto()
    if pid and not primer_plano:
        salida.write("Tu monito ya está en la esquina. Llámalo con ⌥ Espacio.\n")
        return 0
    if not os.path.isfile(HTML):
        salida.write("Falta escritorio/web/monito.html: corre python3 escritorio/web/build.py\n")
        return 1
    os.makedirs(carpeta(), exist_ok=True)
    if primer_plano:
        exe = compilar(sw, salida=salida)
        if not exe:
            return 1
        # aquí los permisos de la Mac (si sus manos los piden) quedan a nombre de esta terminal
        salida.write("Listo: tu monito está en la esquina. ⌥ Espacio para llamarlo · Ctrl+C lo cierra.\n")
        salida.flush()
        from escritorio import cliente as C
        try:
            return subprocess.call(argumentos(exe, extra) + list(al_abrir), env=C.entorno_limpio())
        except KeyboardInterrupt:
            return 0
    bundle_id, nombre, destino = canal()
    app, _que = preparar(argumentos("", extra)[1:], destino=destino, build=scratch(carpeta()), sw=sw,
                         bundle_id=bundle_id, nombre=nombre, correr=correr, salida=salida,
                         aviso="Compilando Workspace Compañero (la primera vez tarda un par de minutos)…\n")
    if not app:
        salida.write("No pude armar Workspace Compañero.\n")
        return 1
    log_ruta = os.path.join(carpeta(), "app.log")
    r = correr(["open", "-n", "-g", "--stdout", log_ruta, "--stderr", log_ruta, app]
               + (["--args"] + list(al_abrir) if al_abrir else []),
               capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 or not esperar_pid():
        salida.write("No pude abrir Workspace Compañero.%s\n" % ((" " + (r.stderr or "").strip()) if r.returncode else ""))
        return 1
    salida.write("Listo: tu monito está en la esquina de abajo a la derecha.\n"
                 "  ⌥ Espacio lo llama y lo guarda · también un clic en él · se cierra desde su carita en la barra de menú\n"
                 "  o con: python3 %s cerrar\n" % os.path.abspath(__file__))
    return 0


def estado(salida=sys.stdout):
    """Qué app del monito hay en cada canal y si su firma conserva los permisos (lo mismo que dice el doctor)."""
    from escritorio import probar_rama as PR
    lineas = [linea_firma(canal()[1], ruta_app()), linea_firma(NOMBRE_APP_PRUEBA, PR.ruta_app())]
    lineas = [x for x in lineas if x] or ["Todavía no hay un Workspace Compañero armado en esta Mac."]
    salida.write("\n".join(lineas) + "\n")
    return 0


def cerrar(salida=sys.stdout, esperar=3.0):
    pid = pid_abierto()
    if not pid:
        salida.write("Workspace Compañero no estaba abierto.\n")
        return 0
    os.kill(pid, signal.SIGTERM)
    fin = time.monotonic() + esperar
    while time.monotonic() < fin and _vivo(pid):
        time.sleep(0.1)
    try:
        os.remove(ruta_pid())
    except OSError:
        pass
    salida.write("Listo: cerré Workspace Compañero.\n")
    return 0


ABIERTO = ("Tu monito ya está abierto. El demo solo se pide al abrirlo: ciérralo con «python3 %s cerrar» y vuelve a "
           "correr --demo." % os.path.abspath(__file__))


def demo(tipo="senalar", salida=sys.stdout, abrir_fn=None):
    """El monito enseña cómo señala (o su tarjeta de permiso), al abrirlo: por la línea de comando de la app
    (`--demo`), nunca por su puerto local (ahí no hay una ruta de demo que otro programa pueda llamar)."""
    if sys.platform != "darwin":
        salida.write(SIN_MAC + "\n")
        return 2
    if pid_abierto():
        salida.write(ABIERTO + "\n")
        return 1
    salida.write("Mira tu pantalla en un momento…\n" if tipo != "permisos" else "Mira el monito en un momento…\n")
    return (abrir_fn or abrir)(salida=salida, al_abrir=["--demo", "permisos" if tipo == "permisos" else "senalar"])


def main(argv):
    argv = list(argv)
    if "--demo" in argv:
        i = argv.index("--demo")
        return demo("permisos" if argv[i + 1:i + 2] == ["permisos"] else "senalar")
    if argv[:1] in (["-h"], ["--help"], ["ayuda"]):
        print(__doc__.split("\n\n")[1])
        return 0
    if argv[:1] == ["cerrar"]:
        return cerrar()
    if argv[:1] == ["estado"]:
        return estado()
    if argv[:1] == ["compilar"]:
        sw = swift()
        if sys.platform != "darwin" or not sw:
            print(SIN_MAC if sys.platform != "darwin" else SIN_SWIFT)
            return 2
        exe = compilar(sw)
        if exe:
            print("Compilado:", exe)
        return 0 if exe else 1
    primer = "--primer-plano" in argv
    extra = [a for a in argv if a != "--primer-plano"]
    return abrir(primer_plano=primer, extra=extra)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
