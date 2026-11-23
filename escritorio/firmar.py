#!/usr/bin/env python3
"""WORKSPACE · escritorio/firmar — con qué se firma Workspace Compañero, la app de escritorio (Mac). Nunca crea identidades ni toca el llavero:
solo mira cuáles hay (`security find-identity`) y firma con `codesign`.

Por qué importa (Apple, TN3127 «Inside Code Signing: Requirements»): macOS guarda cada permiso de la app (Accesibilidad,
Grabación de pantalla) con su «requisito designado» y revisa que cada versión lo cumpla. «Ad hoc signed code … has a DR
but it's tied to that specific version of the code»: el requisito es la huella del binario (`cdhash H"…"`), y otro
binario es otra app para macOS aunque Ajustes siga enseñando el renglón prendido. Con una identidad estable el
requisito es el identificador + el certificado, y los permisos se quedan entre versiones (Developer ID: el identificador
de equipo de Apple).

Qué se usa, en orden (la primera que aplique):
  1. WORKSPACE_MONITO_FIRMA: «adhoc», o el nombre exacto (o la huella SHA-1) de una identidad de tu llavero.
  2. Un certificado de Apple válido: «Developer ID Application: … (EQUIPO)» y si no «Apple Development: … (EQUIPO)».
     Con Developer ID: hardened runtime, sello de tiempo y solo los permisos que la app usa
     (mac/MonitoEscritorio.entitlements); el requisito queda «anchor apple generic … subject.OU = EQUIPO» + el
     identificador: igual en cada compilación. La primera vez macOS pregunta «codesign quiere usar la llave…»: conviene
     «Permitir» (no «Permitir siempre»: una llave de versiones no debe quedar usable sin preguntar en una Mac con agentes
     en automático). Como la app solo se vuelve a firmar cuando cambia su Swift, la pregunta sale solo entonces.
  3. Solo si no hay certificado de Apple, solo para los identificadores de desarrollo (…companero.dev, …companero.prueba) y
     solo desde una copia de desarrollo (escritorio/firma_dev.py, que no viaja): la identidad casera «Workspace Monito
     local» si YA existe (la crea escritorio/mac/firmar_local.sh, solo si tú lo corres).
  4. Ad hoc («-»): macOS vuelve a pedir los permisos cada vez que cambia el binario (se avisa fuerte).
Nunca crea ni cambia identidades. Notarizar (para clientes) es otro paso, a propósito: `firmar.py notarizar <app>` solo
dice los comandos.

    python3 escritorio/firmar.py [identificador]          dice con qué firmaría (no firma nada)
    python3 escritorio/firmar.py <app> <identificador>    firma esa app así
    python3 escritorio/firmar.py notarizar <app>          los comandos para notarizarla (no corre nada)
Stdlib."""
import os
import re
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
#: Lo que la app pide con hardened runtime (solo con Developer ID): manejar otra app por Apple Events (A0, con tu OK).
PERMISOS_APP = os.path.join(AQUI, "mac", "MonitoEscritorio.entitlements")
#: Para elegir a mano: «adhoc» o una identidad de tu llavero (nombre exacto o huella SHA-1).
VAR = "WORKSPACE_MONITO_FIRMA"
#: Los identificadores que se pueden firmar con una llave de desarrollo.
DE_DESARROLLO = (".dev", ".prueba")

ADHOC = {"tipo": "adhoc", "firma": "-", "nombre": "ad hoc", "equipo": ""}

_LINEA = re.compile(r'^\s*\d+\)\s+([0-9A-Fa-f]+)\s+"([^"]+)"\s*(.*)$')
_DEVID = re.compile(r"^Developer ID Application: .+ \(([A-Z0-9]{10})\)$")
_APPLEDEV = re.compile(r"^Apple Development: .+ \(([A-Z0-9]{10})\)$")


def puente_dev():
    """El módulo del puente de desarrollo (escritorio/firma_dev.py), o None: no viaja en el paquete de los clientes
    (make-dist lo quita), así que ahí este camino no existe."""
    try:
        from escritorio import firma_dev
    except ImportError:
        return None
    return firma_dev


def de_desarrollo(bundle_id):
    return bool(bundle_id) and bundle_id.endswith(DE_DESARROLLO)


def identidades(correr=subprocess.run):
    """Las identidades para firmar código del llavero → [{"huella", "nombre", "valida"}], sin repetir. (`security`
    las lista dos veces: todas, con su error si lo hay, y luego solo las válidas.)"""
    try:
        r = correr(["security", "find-identity", "-p", "codesigning"], capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return []
    if r.returncode != 0:
        return []
    vistas = {}
    for linea in (r.stdout or "").splitlines():
        m = _LINEA.match(linea)
        if not m:
            continue
        huella, nombre, resto = m.group(1).upper(), m.group(2), m.group(3).upper()
        valida = not any(k in resto for k in ("CSSMERR", "REVOKED", "EXPIRED"))
        if huella in vistas:
            vistas[huella]["valida"] = vistas[huella]["valida"] and valida
        else:
            vistas[huella] = {"huella": huella, "nombre": nombre, "valida": valida}
    return list(vistas.values())


def _tipo(nombre, local):
    if _DEVID.match(nombre):
        return "developer_id"
    if _APPLEDEV.match(nombre):
        return "apple_development"
    return "local" if nombre == local else "manual"


def _de(i, local):
    m = _DEVID.match(i["nombre"]) or _APPLEDEV.match(i["nombre"])
    # con un certificado de Apple, por su huella (si renuevas, hay dos con el mismo nombre)
    return {"tipo": _tipo(i["nombre"], local), "firma": i["huella"] if m else i["nombre"], "nombre": i["nombre"],
            "equipo": m.group(1) if m else ""}


def elegir(correr=subprocess.run, entorno=None, bundle_id=""):
    """Con qué firmar `bundle_id` ahora → {"tipo": developer_id | apple_development | local | manual | adhoc, "firma"
    (lo que va en --sign), "nombre", "equipo"} (+ "aviso" si pediste una que no está)."""
    env = os.environ if entorno is None else entorno
    dev = puente_dev()
    local = getattr(dev, "LOCAL", None)
    pedida = (env.get(VAR) or "").strip()
    if pedida.lower() in ("adhoc", "ad-hoc", "-"):
        return dict(ADHOC)
    ids = identidades(correr)
    if pedida:
        for i in ids:
            if pedida in (i["nombre"], i["huella"]):
                return _de(i, local)
        return dict(ADHOC, aviso="No encontré la identidad «%s» en tu llavero: firmé ad hoc." % pedida)
    for patron in (_DEVID, _APPLEDEV):                  # un certificado de Apple: el requisito no cambia nunca
        apple = [i for i in ids if i["valida"] and patron.match(i["nombre"])]
        if apple:
            return _de(apple[0], local)
    if dev is not None and de_desarrollo(bundle_id) and any(i["nombre"] == local for i in ids):
        return {"tipo": "local", "firma": local, "nombre": local, "equipo": ""}
    return dict(ADHOC)


def comando(e, app, bundle_id, sello=True):
    """El `codesign` de esa elección. Con Developer ID: hardened runtime, sus permisos y sello de tiempo (sin red, sin
    sello: sirve en esta Mac, no para notarizar)."""
    base = ["codesign", "--force", "--sign", e["firma"], "--identifier", bundle_id]
    if e["tipo"] == "developer_id":
        return base + ["--options", "runtime", "--entitlements", PERMISOS_APP,
                       "--timestamp" if sello else "--timestamp=none", app]
    return base + ["--timestamp=none", app]


SIN_SELLO = ("Sin conexión con Apple para el sello de tiempo: firmé sin sello (sirve en esta Mac; para notarizar hace "
             "falta con sello).")
NO_PUDE_CASERA = ("No pude firmar con «%s» (¿dijiste «Denegar» a la llave?): firmé con la firma propia de esta Mac "
                  "(también estable). La próxima vez que cambie su Swift te lo vuelvo a preguntar.")
NO_PUDE = ("⚠ No pude firmar con «%s» (¿dijiste «Denegar» a la llave?): quedó ad hoc. La próxima vez que cambie su Swift "
           "te lo vuelvo a preguntar.")


def _corre(cmd, correr):
    try:
        return correr(cmd, capture_output=True, text=True, encoding="utf-8")
    except OSError as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def firmar(app, bundle_id, correr=subprocess.run, entorno=None, eleccion=None):
    """Firma `app` con lo que diga `elegir` (o `eleccion`). Con Developer ID, si lo que falló es el sello de tiempo
    (sin red), otra vez sin sello; si falló la llave (dijiste «Denegar»), no se vuelve a preguntar: ad hoc, y lo dice.
    → la elección con que quedó (+ "sello", "aviso", "denegada"), o None."""
    e = eleccion or elegir(correr, entorno, bundle_id)
    r = _corre(comando(e, app, bundle_id), correr)
    if r.returncode == 0:
        return dict(e, sello=e["tipo"] == "developer_id")
    if e["tipo"] == "adhoc":
        return None
    if e["tipo"] == "developer_id" and "timestamp" in ((r.stderr or "") + (r.stdout or "")).lower():
        if _corre(comando(e, app, bundle_id, sello=False), correr).returncode == 0:
            return dict(e, sello=False, aviso=SIN_SELLO)
    # la llave de Apple no se pudo usar: la casera si toca (sigue estable), y si no, ad hoc
    dev = puente_dev()
    local = getattr(dev, "LOCAL", None)
    if e["tipo"] in ("developer_id", "apple_development") and dev is not None and de_desarrollo(bundle_id) \
            and any(i["nombre"] == local for i in identidades(correr)):
        casera = {"tipo": "local", "firma": local, "nombre": local, "equipo": ""}
        if _corre(comando(casera, app, bundle_id), correr).returncode == 0:
            return dict(casera, aviso=NO_PUDE_CASERA % e["nombre"], denegada=e["firma"])
    if _corre(comando(ADHOC, app, bundle_id), correr).returncode == 0:
        return dict(ADHOC, aviso=NO_PUDE % e["nombre"], denegada=e["firma"])
    return None


def pasos_notarizar(app, perfil="workspace-notario"):
    """Los comandos para notarizar la app (para la versión de clientes). Solo se dicen: notarizar necesita una
    contraseña de app o una llave de la API de Apple guardada con `notarytool store-credentials` (eso lo hace el dueño
    de la cuenta), y es un paso deliberado."""
    zipf = os.path.splitext(app)[0] + ".zip"
    return [
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", app],
        ["xcrun", "notarytool", "store-credentials", perfil, "--apple-id", "<tu Apple ID>", "--team-id", "<EQUIPO>"],
        ["ditto", "-c", "-k", "--keepParent", app, zipf],
        ["xcrun", "notarytool", "submit", zipf, "--keychain-profile", perfil, "--wait"],
        ["xcrun", "stapler", "staple", app],
        ["spctl", "--assess", "--type", "execute", "--verbose", app],
    ]


_EQUIPO = re.compile(r'subject\.OU\] = "?([A-Z0-9]{10})"?|\(([A-Z0-9]{10})\)"')


def en_simple(tipo, equipo="", nombre=""):
    """«Developer ID (EQUIPO)», «Apple Development (EQUIPO)», «propia de esta Mac», «ad hoc»…"""
    if tipo == "developer_id":
        return "Developer ID" + (" (%s)" % equipo if equipo else "")
    if tipo == "apple_development":
        return "Apple Development" + (" (%s)" % equipo if equipo else "")
    if tipo == "local":
        return "propia de esta Mac (%s)" % (nombre or "Workspace Monito local")
    if tipo == "manual":
        return nombre or "a mano"
    return "ad hoc"


def _codesign_d(app, extra, correr):
    try:
        r = correr(["codesign", "-d"] + extra + [app], capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return ""
    return (r.stdout or "") + "\n" + (r.stderr or "") if r.returncode == 0 else ""


def requisito(app, correr=subprocess.run):
    """El requisito designado de la app firmada (lo que macOS guarda con cada permiso), o ""."""
    m = re.search(r"designated => (.+)", _codesign_d(app, ["-r-"], correr))
    return m.group(1).strip() if m else ""


def cdhash(app, correr=subprocess.run):
    m = re.search(r"^CDHash=([0-9a-f]+)", _codesign_d(app, ["-vvv"], correr), re.M)
    return m.group(1) if m else ""


def es_estable(req):
    """¿Ese requisito sobrevive a otra compilación? (ad hoc no: es la huella del binario)."""
    return bool(req) and not req.startswith("cdhash ")


def aviso_adhoc(bundle_id):
    """Lo que se dice FUERTE cuando la app quedó ad hoc (una o dos líneas)."""
    t = "⚠ Firmada ad hoc: macOS te va a volver a pedir los permisos de Workspace Compañero cada vez que cambie su Swift."
    dev = puente_dev()
    if dev is not None and de_desarrollo(bundle_id):
        t += "\n  " + dev.como_crearla()
    return t


def main(argv):
    if sys.platform != "darwin":
        print("Esto es solo para la Mac.")
        return 2
    if argv[:1] == ["notarizar"] and len(argv) >= 2:
        print("Para notarizar %s (no corro nada; el segundo paso, una vez, con tu cuenta de Apple):" % argv[1])
        for c in pasos_notarizar(argv[1]):
            print("  " + " ".join(('"%s"' % x) if " " in x else x for x in c))
        return 0
    if len(argv) >= 2:
        hecha = firmar(argv[0], argv[1])
        if not hecha:
            print("No pude firmar %s." % argv[0])
            return 1
        print("Firmé %s · %s%s" % (argv[0], hecha["nombre"], (" · " + hecha["aviso"]) if hecha.get("aviso") else ""))
        req = requisito(argv[0])
        print("Requisito: %s (%s)" % (req or "?", "estable entre versiones" if es_estable(req) else
                                      "cambia con cada compilación"))
        return 0
    bid = argv[0] if argv else "com.workspace.companero.prueba"
    e = elegir(bundle_id=bid)
    print("%s se firmaría con: %s (%s)%s" % (bid, e["nombre"], e["tipo"], (" · " + e["aviso"]) if e.get("aviso") else ""))
    if e["tipo"] == "adhoc":
        print(aviso_adhoc(bid))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
