#!/usr/bin/env python3
"""WORKSPACE · arquitectura/arreglos — «Arreglar» y «Reportar» de Conexiones (Conexiones en verde, F3).

Arreglar (C3-a): SOLO lo que es de Workspace — su lanzador fijo, su paquete por sesión, las skills que puso con su
sello en la carpeta de un agente, los avisos aprobados en SU perfil de Hermes de cada agente y SU perfil de OpenClaw.
Nunca la config de un motor ni nada tuyo (eso va por «Abrir en el cliente oficial»). Cada arreglo:

  1. respalda lo que va a tocar (<estado>/arquitectura/arreglos/<id>/, con su lista);
  2. lo arregla;
  3. vuelve a revisar esa fila (el chequeo rápido de los motores que la usan);
  4. deja un aviso de una línea con «Deshacer» (`deshacer(id)` devuelve lo respaldado, tal cual);
  5. si sigue mal, lo dice y ofrece «Reportar».

El chequeo al abrir (arquitectura/chequeo.revisar con `arreglar=True`) los corre solo: lo de Workspace que falla se
arregla sin manos, con su aviso y su Deshacer (C3-a); lo tuyo sale como ⚠ con su botón.

Reportar (C4-a): un zip redactado en ~/Workspace/Respaldos (`workspace doctor --bundle`) más la evidencia de la fila
(id del chequeo, motor, versión, sistema y el error redactado), mostrado en Finder / el Explorador y con un resumen de
cinco líneas para pegar. Nada sale de la máquina: lo mandas tú, si quieres. Stdlib, falla-suave.
"""
import datetime as _dt
import json
import os
import platform
import shutil
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

#: Lo que dice el aviso de una línea de cada arreglo (y qué motores revisa otra vez: None = todos).
TEXTOS = {
    "lanzador": "Workspace rearmó su lanzador (el que corren los avisos y las herramientas de cada motor).",
    "paquete": "Workspace volvió a armar su paquete por sesión.",
    "skills": "Workspace volvió a poner sus skills en la carpeta que lee {nombre}.",
    "hermes-avisos": "Workspace aprobó otra vez sus avisos en el perfil de Hermes de cada agente.",
    "openclaw-perfil": "Workspace reparó su perfil propio en OpenClaw.",
}
#: Cuántos respaldos de arreglos se guardan (los más viejos se borran).
GUARDAR = 20


def _dir(state_dir=None):
    if not state_dir:
        import paths
        state_dir = paths.state_dir()
    return os.path.join(state_dir, "arquitectura", "arreglos")


def _base(arreglo):
    return str(arreglo or "").split(":", 1)[0]


def conocido(arreglo):
    return _base(arreglo) in TEXTOS


# ── qué toca cada uno (para respaldarlo) y cómo lo arregla ─────────────────
def _agentes(motor):
    try:
        from arquitectura import chequeo
        return [(a[0], a[2]) for a in chequeo.Sondas().agentes() if a[1] == motor and a[2] and os.path.isdir(a[2])]
    except Exception:
        return []


def _skills_dst(motor, cerebro):
    from arquitectura import contrato
    via = ((contrato.ficha(motor).get("sesion") or {}).get("skills") or {})
    if via.get("via") != "proyecto":
        return ""
    return str(via.get("ruta") or "").replace("{cerebro}", str(cerebro))


def _paquetes_danados():
    """Los paquetes instalados (el de todos y el de cada cerebro de tus agentes) que no son los de esta versión."""
    try:
        from arquitectura import chequeo
        cerebros = sorted({a[2] for a in chequeo.Sondas().agentes() if a[2] and os.path.isdir(a[2])})
        return chequeo.paquetes_danados(cerebros)
    except Exception:
        return []


def _hermes_perfiles():
    from arquitectura import chequeo
    return [p for p, e in chequeo.hermes_avisos() if e == "falta"]


def que_toca(arreglo):
    """Las rutas (archivos o carpetas) de Workspace que el arreglo va a cambiar."""
    base, _, motor = str(arreglo).partition(":")
    if base == "lanzador":
        from arquitectura import sesion
        return [sesion.carpeta_lanzador()]
    if base == "paquete":
        # el de esta versión se arma al lado (no se pisa nada); solo un paquete instalado DAÑADO se rehace en su
        # sitio, y ese se respalda tal cual
        return [final for _c, final, _f in _paquetes_danados()]
    if base == "skills":
        from arquitectura import skills_cerebro
        out = []
        for _n, c in _agentes(motor):
            d = _skills_dst(motor, c)
            if d and os.path.isdir(d):
                out += [os.path.join(d, x) for x in sorted(os.listdir(d))
                        if skills_cerebro.es_nuestra(os.path.join(d, x)) or
                        (os.path.islink(os.path.join(d, x)) and not os.path.exists(os.path.join(d, x)))]
        return out
    if base == "hermes-avisos":
        from engines import hermes as _h
        return [os.path.join(_h.carpeta_perfil(p), "shell-hooks-allowlist.json") for p in _hermes_perfiles()]
    if base == "openclaw-perfil":
        from engines import openclaw as oc
        return [os.path.join(oc.state_dir(), "openclaw.json")]
    return []


def _hacer(arreglo):
    """Arregla. → (True, '') o (False, por qué)."""
    base, _, motor = str(arreglo).partition(":")
    from arquitectura import sesion
    if base in ("lanzador", "paquete"):
        if base == "paquete":
            for c, _final, _f in _paquetes_danados():
                sesion.instalar(c, rehacer=True)  # uno «listo» que se dañó: se arma otra vez y se cambia de golpe
        fmts = sesion.instalar()
        if base == "lanzador":
            sesion.lanzador_fijo(next(iter(fmts.values())))
        return True, ""
    if base == "skills":
        from arquitectura import contrato
        ficha = contrato.ficha(motor)
        via = (ficha.get("sesion") or {}).get("skills") or {}
        for _n, c in _agentes(motor):
            pkg = sesion.instalar(c)
            valores = {"paquete": pkg[ficha["paquete"]["formato"]], "cerebro": str(c), "python": sesion.python()}
            sesion._skills_de_la_sesion(via, valores, c)
        return True, ""
    if base == "hermes-avisos":
        from engines import hermes as _h
        otros = []
        for p in _hermes_perfiles():
            avisos = _avisos_de(p)
            if not any(ev != _h._HOOK_EVENT or cmd != _h._hook_command() for ev, cmd in avisos):
                otros.append(p)                 # ninguno exacto (otro Python lo escribió): no se toca lo aprobado
                continue
            _h.aprobar_avisos(p, avisos)
        if otros:
            return False, ("los avisos de %s no son los de este Workspace (otro Python los escribió); se rehacen y "
                           "se aprueban solos al abrir el agente" % ", ".join(otros))
        return True, ""
    if base == "openclaw-perfil":
        from engines import openclaw as oc
        return (bool(oc.reparar_plugin()), "")
    return False, "no sé arreglar «%s»" % arreglo


def _avisos_de(perfil):
    """[(evento, comando)] de los avisos de Workspace en el config.yaml del perfil que se aprueban sin preguntar: solo
    los EXACTOS (su Python y su lanzador, nada más en el comando) y su aviso de tono; uno que solo contiene la ruta
    del lanzador, no (engines/hermes.avisos_de_workspace)."""
    from engines import hermes as _h
    return _h.avisos_de_workspace(perfil)


def _motores_de(arreglo):
    base, _, motor = str(arreglo).partition(":")
    if base == "skills":
        return [motor]
    if base == "hermes-avisos":
        return ["hermes"]
    if base == "openclaw-perfil":
        return ["openclaw"]
    return None                                     # lanzador y paquete: los usan todos


# ── respaldo y deshacer ────────────────────────────────────────────────────
def _copiar(origen, destino):
    if os.path.isdir(origen) and not os.path.islink(origen):
        shutil.copytree(origen, destino, symlinks=True)
    elif os.path.lexists(origen):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copy2(origen, destino, follow_symlinks=False)


def _quitar(ruta):
    if os.path.isdir(ruta) and not os.path.islink(ruta):
        shutil.rmtree(ruta, ignore_errors=True)
    elif os.path.lexists(ruta):
        os.remove(ruta)


def respaldar(arreglo, rutas, state_dir=None):
    """Copia `rutas` a un respaldo nuevo. → su id."""
    d = _dir(state_dir)
    rid = "%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), _base(arreglo))
    carpeta = os.path.join(d, rid)
    n = 1
    while os.path.exists(carpeta):
        n += 1
        carpeta = os.path.join(d, "%s-%d" % (rid, n))
    rid = os.path.basename(carpeta)
    os.makedirs(carpeta)
    lista = []
    for i, r in enumerate(rutas):
        copia = os.path.join(carpeta, "%02d-%s" % (i, os.path.basename(r.rstrip("/\\")) or "x"))
        existia = os.path.lexists(r)
        if existia:
            _copiar(r, copia)
        lista.append({"origen": r, "copia": copia, "existia": existia})
    with open(os.path.join(carpeta, "respaldo.json"), "w", encoding="utf-8") as fh:
        json.dump({"arreglo": arreglo, "fecha": _dt.datetime.now().isoformat(timespec="seconds"), "rutas": lista},
                  fh, ensure_ascii=False, indent=1)
    _podar(d)
    return rid


def _podar(d):
    try:
        viejos = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))[:-GUARDAR]
        for x in viejos:
            shutil.rmtree(os.path.join(d, x), ignore_errors=True)
    except OSError:
        pass


#: El Deshacer de un arreglo que no cambió nada que se pueda devolver (p. ej. «paquete»: arma el de esta versión al
#: lado, sin pisar nada). No dice «quedó como antes»: no había nada que devolver.
NADA_QUE_DEVOLVER = "No había nada que devolver: ese arreglo no cambió nada de lo que ya estaba."


def _leer_respaldo(carpeta):
    with open(os.path.join(carpeta, "respaldo.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _sumar_lo_nuevo(rid, antes, despues, state_dir=None):
    """Lo que el arreglo puso de nuevo (estaba en `despues` y no en `antes`) entra a su respaldo como «no existía»:
    Deshacer también lo quita. → cuántas rutas tiene el respaldo ahora."""
    carpeta = os.path.join(_dir(state_dir), rid)
    r = _leer_respaldo(carpeta)
    vistas = {x["origen"] for x in r.get("rutas") or ()}
    for ruta in despues:
        if ruta not in vistas and ruta not in antes:
            r.setdefault("rutas", []).append({"origen": ruta, "copia": "", "existia": False})
            vistas.add(ruta)
    with open(os.path.join(carpeta, "respaldo.json"), "w", encoding="utf-8") as fh:
        json.dump(r, fh, ensure_ascii=False, indent=1)
    return len(r.get("rutas") or ())


def deshacer(rid, state_dir=None, revisar=True):
    """Devuelve lo que tocó el arreglo `rid`, tal cual estaba (lo que no existía se quita). → {ok, texto}. Si su
    respaldo no tiene nada (no cambió nada que se pueda devolver), lo dice así: no promete «quedó como antes»."""
    if not rid or "/" in rid or "\\" in rid or rid.startswith("."):
        return {"ok": False, "texto": "No encontré ese arreglo."}
    carpeta = os.path.join(_dir(state_dir), rid)
    try:
        r = _leer_respaldo(carpeta)
    except (OSError, ValueError):
        return {"ok": False, "texto": "No encontré ese arreglo."}
    rutas = r.get("rutas") or ()
    for x in rutas:
        _quitar(x["origen"])
        if x.get("existia"):
            _copiar(x["copia"], x["origen"])
    shutil.rmtree(carpeta, ignore_errors=True)
    if not rutas:
        return {"ok": True, "texto": NADA_QUE_DEVOLVER}
    if revisar:
        _revisar(_motores_de(r.get("arreglo")))
    return {"ok": True, "texto": "Listo: quedó como antes del arreglo."}


def _revisar(motores):
    try:
        from arquitectura import chequeo
        return chequeo.revisar(motores=motores, saludar=motores if motores else None, arreglar=False)
    except Exception:
        return None


def _sigue_mal(d, arreglo):
    return any((f.get("accion") or {}).get("arreglo") == arreglo
               for m in (d or {}).get("motores") or () for f in m.get("filas") or ()) or \
        ((d or {}).get("workspace") or {}).get("accion", {}) == {"tipo": "arreglar", "etiqueta": "Arreglar",
                                                                 "arreglo": arreglo}


def arreglar(arreglo, state_dir=None, revisar=True):
    """Respaldo → arreglo → otra revisión → {ok, texto, deshacer, sigue_mal}. Solo lo de Workspace (TEXTOS)."""
    if not conocido(arreglo):
        return {"ok": False, "texto": "Eso no lo arregla Workspace: ábrelo en su programa oficial.", "deshacer": "",
                "sigue_mal": True}
    try:
        antes = que_toca(arreglo)
        rid = respaldar(arreglo, antes, state_dir)
    except Exception as e:
        return {"ok": False, "texto": "No pude respaldar antes de arreglar (no toqué nada): %s" % e, "deshacer": "",
                "sigue_mal": True}
    try:
        hecho, por = _hacer(arreglo)
    except Exception as e:
        hecho, por = False, "%s: %s" % (type(e).__name__, e)
    try:                                        # lo que puso de nuevo también se quita al deshacer
        n = _sumar_lo_nuevo(rid, antes, que_toca(arreglo), state_dir)
    except Exception:
        n = len(antes) or 1
    if not n:                                   # no cambió nada que se pueda devolver: sin «Deshacer» que no hace nada
        shutil.rmtree(os.path.join(_dir(state_dir), rid), ignore_errors=True)
        rid = ""
    nombre = _base(arreglo)
    motor = str(arreglo).partition(":")[2]
    texto = TEXTOS[nombre].format(nombre=_nombre_motor(motor))
    d = _revisar(_motores_de(arreglo)) if revisar else None
    sigue = (not hecho) or (revisar and _sigue_mal(d, arreglo))
    if sigue:
        texto = "Lo intenté y sigue igual%s. Puedes reportarlo." % ((": " + por) if por else "")
    return {"ok": not sigue, "texto": texto, "deshacer": rid, "sigue_mal": sigue}


def _nombre_motor(motor):
    try:
        from arquitectura import contrato
        return contrato.ficha(motor).get("nombre") or motor
    except Exception:
        return motor or "el motor"


# ── reportar ───────────────────────────────────────────────────────────────
def evidencia(motor="", fila="", d=None):
    """Lo de la fila para el reporte: id del chequeo, motor, versión, sistema y el error (ya redactado)."""
    from arquitectura import chequeo
    d = d or chequeo.leer()
    m = next((x for x in d.get("motores") or () if x.get("motor") == motor), {}) if motor else {}
    f = next((x for x in m.get("filas") or () if x.get("id") == fila), {}) if fila else {}
    w = d.get("workspace") or {}
    return {"motor": motor, "fila": fila, "chequeo": (f.get("evidencia") or {}).get("chequeo") or fila,
            "estado": f.get("estado") or m.get("estado") or w.get("estado") or "",
            "texto": chequeo.redactar(f.get("texto") or w.get("texto") or "", 400),
            "detalle": chequeo.redactar((f.get("evidencia") or {}).get("detalle") or w.get("detalle") or "", 600),
            "version_motor": m.get("version") or "", "workspace": chequeo._version_workspace(),
            "sistema": "%s %s · %s" % (platform.system(), platform.release(), platform.machine()),
            "fecha": d.get("fecha") or ""}


def resumen(ev):
    """Las cinco líneas para pegar en un mensaje (sin rutas ni llaves)."""
    return "\n".join([
        "Workspace %s · %s" % (ev.get("workspace") or "?", ev.get("sistema") or ""),
        "Motor: %s %s" % (ev.get("motor") or "Workspace por dentro", ev.get("version_motor") or ""),
        "Chequeo: %s · %s" % (ev.get("chequeo") or "-", ev.get("estado") or "-"),
        "Qué pasa: %s" % (ev.get("texto") or "-"),
        "Detalle: %s" % ((ev.get("detalle") or "-")[:200]),
    ])


def portapapeles(texto):
    """Deja `texto` en el portapapeles de esta máquina (pbcopy · clip · wl-copy/xclip). True si quedó."""
    import arbol_procesos
    for cmd in (["pbcopy"], ["clip"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, input=texto.encode("utf-16le" if cmd[0] == "clip" else "utf-8"), timeout=5,
                               **arbol_procesos.sin_ventana())                 # Windows: desde la página, sin consola
            return r.returncode == 0
        except Exception:
            continue
    return False


def reportar(motor="", fila="", revelar=True, copiar=True, construir=None):
    """Arma el zip redactado (`workspace doctor --bundle`) con la evidencia de la fila, lo muestra en su carpeta y
    copia el resumen. Nada se envía. → {ok, ruta, resumen, texto}."""
    import diag_bundle
    ev = evidencia(motor, fila)
    try:
        ruta, _red = (construir or diag_bundle.build)(extra=[("conexion.json", ev)])
    except Exception as e:
        return {"ok": False, "ruta": "", "resumen": "", "texto": "No pude armar el reporte (nada se envió): %s" % e}
    res = resumen(ev)
    if revelar and not os.environ.get("WORKSPACE_NO_REVEAL"):
        diag_bundle.revelar(ruta)
    copiado = portapapeles(res) if copiar else False
    return {"ok": True, "ruta": ruta, "resumen": res,
            "texto": "Listo: el reporte quedó en %s%s. Nada salió de tu máquina: mándalo tú si quieres." % (
                os.path.basename(ruta), " y el resumen, copiado" if copiado else "")}
