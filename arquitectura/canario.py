#!/usr/bin/env python3
"""WORKSPACE · arquitectura/canario — nuestro canario (Conexiones en verde, F6 · C6-a).

En NUESTRAS máquinas de desarrollo (dev_tui.is_dev: el repo de equipo, no una instalación de cliente) la misma
revisión al abrir que ve un motor con versión nueva (arquitectura/chequeo) corre aquí la prueba a fondo de ESE motor
con el motor real (arquitectura/verificacion.lanzar: su avance se ve en el hub, como «Verificar»). Es nuestra máquina:
gastar un turno ahí es a propósito. En la de un cliente esto no corre nunca (C1-a: sin IA sin ventana).

Al terminar (lo mira la siguiente revisión, solo código):
  · VERDE (ninguna pieza ✗): la versión queda probada en ESTA máquina (`probadas` de <estado>/arquitectura/
    canario.json, nunca un archivo del repo: dejaba el checkout de desarrollo con cambios sin commitear) y queda un
    aviso. Pasarla a `versiones_probadas` de su ficha (la lista única, engine_versions) es un comando explícito:
    `python3 -m arquitectura.canario a-las-fichas`; luego se integra como cualquier otro cambio.
  · ROJO: un encargo por la sala (messages.send) al agente de código que diga `<estado>/canario.local.json`
    ({"de": "<quien manda>", "para": "<quien arregla>"}, local de esta máquina, como maquinas.local.json), con la
    carpeta de la prueba (auditoria.md). Sin ese archivo, el encargo queda escrito en <estado>/arquitectura/canario/
    para mandarlo a mano, y el aviso lo dice.

`workspace release` avisa (`sin_probar_instaladas`) si en esta máquina hay un motor más nuevo que sus probadas sin una
prueba verde. Lo que llega por «Reportar» trae motor, versión e id del chequeo, para agruparlo. Stdlib, falla-suave.

canario.json lo cambian la revisión al abrir (hub, página) y el comando, a veces a la vez: cada cambio lee, cambia y
guarda bajo su candado entre procesos (olock), con el guardado común (estado_json → atomico). Uno dañado se aparta con
otro nombre y se avisa; nunca se guarda encima.
"""
import codecs
import contextlib
import datetime as _dt
import json
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

import atomico  # noqa: E402
from arquitectura import estado_json  # noqa: E402
from olock import file_lock  # noqa: E402

#: Lo más que se espera a que la prueba de un motor empiece (si otra corre, se reintenta en la siguiente revisión).
ESPERA_S = 6 * 3600
CONFIG = "canario.local.json"


def _estado(state_dir=None):
    if not state_dir:
        import paths
        state_dir = paths.state_dir()
    return state_dir


def ruta(state_dir=None):
    return os.path.join(_estado(state_dir), "arquitectura", "canario.json")


def _valido(d):
    """La forma de canario.json por dentro (revisor 5): un campo con otro tipo cuenta como dañado."""
    pend = d.get("pendientes", {})
    return (isinstance(pend, dict) and all(isinstance(p, dict) for p in pend.values())
            and isinstance(d.get("historial", []), list) and isinstance(d.get("probadas", {}), dict))


def _con_forma(d):
    d = d if isinstance(d, dict) else {}
    d.setdefault("pendientes", {})
    d.setdefault("historial", [])
    return d


def leer(state_dir=None):
    """canario.json para mirarlo. Uno ilegible se ve vacío, pero no se toca: lo aparta el que va a cambiarlo."""
    try:
        d = estado_json.leer(ruta(state_dir), valido=_valido)
    except OSError:
        d = {}
    return _con_forma(d)


@contextlib.contextmanager
def _cambiando(state_dir=None):
    """«Archivos compartidos»: canario.json para cambiarlo, bajo su candado entre procesos; se guarda al salir sin
    error (solo si cambió). Uno dañado se aparta (`canario.json.corrupt-…`, con su aviso) y se sigue con uno nuevo; si
    no se pudo apartar, sube el error y no se guarda nada encima. No es reentrante: uno a la vez."""
    p = ruta(state_dir)
    with file_lock(p):
        try:
            d = estado_json.leer(p, apartar=True, valido=_valido)
        except ValueError:                       # ya quedó aparte y avisado: lo de ahora, sin él
            d = estado_json.leer(p, apartar=True, valido=_valido)
        d = _con_forma(d)
        antes = json.dumps(d, sort_keys=True, default=str)
        yield d
        if json.dumps(d, sort_keys=True, default=str) != antes:
            estado_json.escribir(p, d)


def _guardar(d, state_dir=None):
    """canario.json entero, bajo su candado (para quien ya lo armó completo)."""
    p = ruta(state_dir)
    with file_lock(p):
        estado_json.escribir(p, d)


def activo():
    """¿Esta es una de nuestras máquinas de desarrollo? (nunca en la suite ni en la de un cliente)."""
    if os.environ.get("WORKSPACE_NO_SESSION_PROBE"):
        return False
    try:
        import dev_tui
        return bool(dev_tui.is_dev())
    except Exception:
        return False


def config(state_dir=None):
    """{"de", "para"} de <estado>/canario.local.json (local de esta máquina; la escribe quien desarrolla), o {}."""
    try:
        with open(os.path.join(_estado(state_dir), CONFIG), encoding="utf-8-sig") as fh:
            d = json.load(fh)
        return {k: str(d.get(k) or "").strip() for k in ("de", "para") if str(d.get(k) or "").strip()}
    except (OSError, ValueError, AttributeError):
        return {}


def probadas(motor, state_dir=None, d=None):
    """Las probadas de `motor` para el canario: las de su ficha y las que salieron verdes en esta máquina (las de `d`,
    el canario.json que ya se tiene, si se da)."""
    import engine_versions as EV
    vv = list(EV.probadas_de_la_ficha(motor) or [])
    return vv + [v for v in probadas_locales(state_dir, d=d).get(motor, []) if v not in vv]


def probadas_locales(state_dir=None, d=None):
    """{motor: [versiones]} que el canario de esta máquina probó en verde y aún no están en su ficha."""
    pr = (d if d is not None else leer(state_dir)).get("probadas")
    if not isinstance(pr, dict):
        return {}
    return {str(m): [str(v) for v in vv] for m, vv in pr.items() if isinstance(vv, list) and vv}


def _anotar_probada(d, motor, version):
    """Verde: la versión queda probada en esta máquina (en `d`, el canario.json). → True si es nueva."""
    import engine_versions as EV
    if any(_mismo(version, v) for v in (EV.probadas_de_la_ficha(motor) or [])):
        return False
    lista = d.setdefault("probadas", {}).setdefault(motor, [])
    if any(_mismo(version, v) for v in lista):
        return False
    lista.append(version)
    return True


#: El comando explícito que pasa lo probado en esta máquina a las fichas del repo.
A_LAS_FICHAS = "python3 -m arquitectura.canario a-las-fichas"


def a_las_fichas(state_dir=None, raiz=None, fallidas=None):
    """Pasa las versiones probadas en esta máquina a `versiones_probadas` de su ficha (solo ese renglón) y quita de lo
    local solo las que quedaron en su ficha (escritas ahora o que ya estaban). Las que no se pudieron escribir se quedan
    para reintentar y van a `fallidas` (una lista, si se da). → [(motor, versión)] que entraron a una ficha. Todo bajo
    el candado de canario.json: el único que escribe las fichas es este comando, así dos a la vez no se pisan."""
    hechas = []
    with _cambiando(state_dir) as d:
        for motor, vv in probadas_locales(d=d).items():
            quedan = []
            for v in vv:
                if agregar_a_la_ficha(motor, v, raiz=raiz):
                    hechas.append((motor, v))
                elif not any(_mismo(v, x) for x in (_de_la_ficha(motor, raiz) or ())):
                    quedan.append(v)
                    if fallidas is not None:
                        fallidas.append((motor, v))
            if quedan:
                d["probadas"][motor] = quedan
            else:
                d["probadas"].pop(motor, None)
    return hechas


def al_cambiar(cambios, state_dir=None, lanzar=None, es_dev=None):
    """La revisión al abrir vio versiones nuevas: {motor: {"antes", "ahora"}}. En nuestras máquinas, anota cada una
    que no esté probada y corre su prueba a fondo. → los motores que quedaron pendientes."""
    if not (activo() if es_dev is None else es_dev):
        return []
    nuevos = []
    with _cambiando(state_dir) as d:
        for motor, c in (cambios or {}).items():
            v = str(c.get("ahora") or "")
            if not v or any(_mismo(v, p) for p in probadas(motor, state_dir, d)):
                continue
            d["pendientes"][motor] = {"antes": c.get("antes") or "", "ahora": v, "inicio": None,
                                      "visto": _ahora()}
            nuevos.append(motor)
        if nuevos:
            _lanzar_pendientes(d, state_dir, lanzar)
    return nuevos


def _mismo(a, b):
    import engine_versions as EV
    return EV.parse(a) is not None and EV.parse(a) == EV.parse(b)


def _ahora():
    return _dt.datetime.now().isoformat(timespec="seconds")


def _lanzar_pendientes(d, state_dir=None, lanzar=None):
    """Corre la prueba a fondo de los pendientes que todavía no empezaron (una corrida para todos, visible). Cambia
    `d` (lo guarda quien lo tiene bajo _cambiando)."""
    faltan = [m for m, p in d["pendientes"].items() if not p.get("inicio")]
    if not faltan:
        return False
    from arquitectura import verificacion
    r = (lanzar or verificacion.lanzar)(faltan)
    if r.get("ok"):
        t = time.time()
        for m in faltan:
            d["pendientes"][m]["inicio"] = t
        return True
    return False


def revisar_pendientes(state_dir=None, lanzar=None, mandar=None, es_dev=None, matriz=None, estado=None):
    """Lo que mira cada revisión (solo código): si la prueba de un pendiente ya terminó, su veredicto → verde (a la
    ficha) o rojo (encargo). Si no había empezado (otra corría), se intenta otra vez. → [avisos de una línea]."""
    if not (activo() if es_dev is None else es_dev):
        return []
    if not leer(state_dir)["pendientes"]:
        return []                                # lo de casi siempre: sin candado
    from arquitectura import verificacion
    est = (estado or verificacion.estado)()
    if est.get("corriendo"):
        return []
    with _cambiando(state_dir) as d:
        return _revisar(d, state_dir, lanzar, mandar, matriz, verificacion)


def _revisar(d, state_dir, lanzar, mandar, matriz, verificacion):
    """revisar_pendientes, con canario.json ya bajo su candado (`d`: lo cambia; lo guarda _cambiando)."""
    if not d["pendientes"]:
        return []
    if any(not p.get("inicio") for p in d["pendientes"].values()):
        _lanzar_pendientes(d, state_dir, lanzar)
        return []
    m_ = (matriz or verificacion.matriz)()
    avisos = []
    for motor, p in list(d["pendientes"].items()):
        fila = next((f for f in m_.get("motores") or () if f.get("motor") == motor), None)
        fecha = _epoch((fila or {}).get("fecha"))
        if not fila or fecha + 5 < float(p.get("inicio") or 0):
            if time.time() - float(p.get("inicio") or 0) > ESPERA_S:
                d["pendientes"].pop(motor)          # nunca terminó: se suelta (la próxima versión lo vuelve a pedir)
            continue
        rotas = [k for k, c in (fila.get("celdas") or {}).items() if c.get("estado") == verificacion.FALLA]
        bien = [k for k, c in (fila.get("celdas") or {}).items() if c.get("estado") == verificacion.OK]
        nombre = fila.get("nombre") or motor
        if not rotas and not bien:                  # no se pudo probar (p. ej. el perfil de prueba sin cuenta)
            avisos.append("Canario: %s %s no se pudo probar a fondo en esta máquina; queda sin probar." % (
                nombre, p["ahora"]))
            resultado = "sin_probar"
        elif rotas:
            enviado, donde = _encargo(motor, nombre, p, rotas, fila, state_dir, mandar)
            avisos.append("Canario: %s %s salió con %d pieza(s) en ✗ (%s): %s." % (
                nombre, p["ahora"], len(rotas), ", ".join(rotas), "encargo enviado por la sala" if enviado else
                "el encargo quedó en " + donde))
            resultado = "rojo"
        else:
            agregada = _anotar_probada(d, motor, p["ahora"])
            avisos.append("Canario: %s %s salió verde%s." % (
                nombre, p["ahora"], ": quedó probada en esta máquina (a su ficha, con «%s»)" % A_LAS_FICHAS
                if agregada else ""))
            resultado = "verde"
        d["historial"] = (d["historial"] + [{"motor": motor, "version": p["ahora"], "resultado": resultado,
                                             "fecha": _ahora()}])[-50:]
        d["pendientes"].pop(motor)
    return avisos


def _epoch(iso):
    try:
        return time.mktime(_dt.datetime.fromisoformat(str(iso)).timetuple())
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _encargo(motor, nombre, p, rotas, fila, state_dir=None, mandar=None):
    """El encargo de un rojo: por la sala si canario.local.json dice a quién; si no, escrito para mandarlo. →
    (enviado, dónde quedó)."""
    from arquitectura import verificacion
    detalle = "\n".join("- %s: %s" % (k, (fila["celdas"][k].get("por_que") or "")[:300]) for k in rotas)
    cuerpo = ("El canario vio %s %s (antes %s) en esta máquina y la prueba a fondo salió con piezas en ✗.\n\n%s\n\n"
              "Informe completo: %s/auditoria.md\nNada se cambió en la config del motor." % (
                  nombre, p["ahora"], p.get("antes") or "?", detalle, verificacion.carpeta_salida(state_dir)))
    asunto = "Canario: %s %s rompió %s" % (nombre, p["ahora"], ", ".join(rotas))
    cfg = config(state_dir)
    if cfg.get("de") and cfg.get("para"):
        try:
            import messages
            ids = (mandar or messages.send)(cfg["de"], cfg["para"], "encargo", asunto, cuerpo)
            if ids:
                return True, ""
        except Exception:
            pass
    carpeta = os.path.join(_estado(state_dir), "arquitectura", "canario")
    os.makedirs(carpeta, exist_ok=True)
    archivo = os.path.join(carpeta, "encargo-%s-%s.md" % (motor, re.sub(r"[^0-9A-Za-z.]+", "_", p["ahora"])))
    with open(archivo, "w", encoding="utf-8") as fh:
        fh.write("# %s\n\n%s\n" % (asunto, cuerpo))
    return False, archivo


def _ruta_ficha(motor, raiz=None):
    return os.path.join(raiz or RAIZ_REPO, "arquitectura", "fichas", motor + ".json")


def _de_la_ficha(motor, raiz=None):
    """`versiones_probadas` de la ficha del motor en este checkout, o None si no se pudo leer."""
    try:
        lista = json.loads(atomico.leer(_ruta_ficha(motor, raiz), encoding="utf-8-sig")).get("versiones_probadas")
    except (OSError, ValueError, AttributeError):
        return None
    return lista if isinstance(lista, list) else None


def agregar_a_la_ficha(motor, version, raiz=None):
    """Suma `version` a `versiones_probadas` de la ficha del motor en este checkout (la lista única). Solo el renglón
    de esa clave cambia: se lee tal cual (su BOM y sus saltos de línea se quedan) y se guarda con el guardado común
    (temporal único en la misma carpeta y os.replace con reintentos). → True si la agregó. Solo la llama el comando
    explícito (a_las_fichas, bajo el candado de canario.json), nunca la revisión."""
    p = _ruta_ficha(motor, raiz)
    try:
        with open(p, "rb") as fh:
            crudo = fh.read()
        bom = codecs.BOM_UTF8 if crudo.startswith(codecs.BOM_UTF8) else b""
        texto = crudo[len(bom):].decode("utf-8")
        lista = json.loads(texto).get("versiones_probadas")
        if not isinstance(lista, list) or any(_mismo(version, v) for v in lista):
            return False
        m = re.search(r'"versiones_probadas"\s*:\s*\[[^\]]*\]', texto)
        if not m:
            return False
        nuevo = texto[:m.start()] + '"versiones_probadas": ' + json.dumps(lista + [version]) + texto[m.end():]
        json.loads(nuevo)                             # sigue siendo la misma ficha, con una versión más
        atomico.escribir(p, bom + nuevo.encode("utf-8"))
        return True
    except (OSError, ValueError, AttributeError):
        return False


def sin_probar_instaladas(which=None, version=None):
    """[(motor, versión instalada, último veredicto del canario o '')] de los motores de ESTA máquina más nuevos que
    sus probadas (para `workspace release`). En la suite (sin sondeos) no corre ningún programa: []."""
    if (which is None or version is None) and os.environ.get("WORKSPACE_NO_SESSION_PROBE"):
        return []
    import shutil
    import dispatch
    import engine_versions as EV
    from arquitectura import contrato
    hist = {(h.get("motor"), h.get("version")): h.get("resultado") for h in leer().get("historial") or ()}
    out = []
    for m in contrato.MOTORES:
        try:
            exe = (which or shutil.which)(contrato.ficha(m).get("binario") or m)
            if not exe:
                continue
            v = (version or (lambda mm, e: EV.installed_version(e)))(m, exe)
            st, have, _r = EV.drift(dispatch.load_engine(m), v)
        except Exception:
            continue
        if st in ("newer", "untested"):
            out.append((m, have, hist.get((m, have), "")))
    return out


def main(argv=None, raiz=None):
    """`python3 -m arquitectura.canario a-las-fichas`: lo probado en verde en esta máquina, a las fichas del repo."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] != ["a-las-fichas"]:
        print("uso: %s" % A_LAS_FICHAS)
        return 2
    fallidas = []
    hechas = a_las_fichas(raiz=raiz, fallidas=fallidas)
    for motor, v in hechas:
        print("· %s %s → arquitectura/fichas/%s.json" % (motor, v, motor))
    for motor, v in fallidas:
        print("· %s %s: no pude escribirla en arquitectura/fichas/%s.json; sigue probada en esta máquina para "
              "intentarlo otra vez." % (motor, v, motor))
    if fallidas:
        return 1
    if not hechas:
        print("Nada que pasar: no hay versiones probadas en esta máquina fuera de sus fichas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
