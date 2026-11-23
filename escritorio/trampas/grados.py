#!/usr/bin/env python3
"""WORKSPACE · escritorio/trampas/grados — las trampas del PORTERO (ronda 2: lo leído con grados y «no me preguntes»).

Deterministas: sin modelo y sin tocar nada. Cada trampa de trampas_portero.json es un guion contra el portero de
verdad (el Swift de la app, por línea de comandos: escritorio/trampas/portero.py), en A1 y con el reloj fijo. Dice cómo
una página maliciosa (o un agente que obedece todo) intentaría aprovechar un grado de «lo que leyó» o un renglón de
«cero toques», y lo que el portero tiene que contestar. Dos reglas valen para TODAS, además de lo que espera cada paso:
  · un paso marcado «ataque» nunca sale sin ficha: ni `cero` ni una autorización (salvo los que dicen «permitido»);
  · al final, lo hecho sin preguntar no pasa de los pasos que se esperaban `cero`.

  python3 escritorio/trampas/grados.py [--trampas P01,P04] [--json]

Solo Mac (necesita swiftc); el archivo de trampas es el mismo que tendrá que pasar la app de Windows. Stdlib."""
import argparse
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
ARCHIVO = os.path.join(AQUI, "trampas_portero.json")
#: El reloj de cada trampa (18-nov-2026, 15:06 UTC), salvo que ella lo mueva.
RELOJ = 1795000000


def cargar(ids=None):
    with open(ARCHIVO, encoding="utf-8") as fh:
        d = json.load(fh)
    return d, [t for t in d["trampas"] if not ids or t["id"] in ids]


def destino(spec, casa):
    """El destino como lo diría el sistema, de su forma corta: una app, una página, un archivo o un elemento."""
    d = {"app": "Terminal", "bundle": "com.apple.Terminal", "pid": 501, "ventana": "zsh", "ventana_id": 7, "casa": casa}
    if "elemento" in spec:
        d = dict({"pid": 501, "ventana_id": 7, "casa": casa}, **spec["elemento"])
    if "app" in spec:
        d.update(abrir_app=spec["app"]["bundle"], abrir_nombre=spec["app"].get("nombre", spec["app"]["bundle"]))
    if "pagina" in spec:
        d.update(abrir_url=spec["pagina"], abrir_con=spec.get("con", "com.apple.Safari"), abrir_nombre="Safari", abrir_abierta=True)
    if "archivo" in spec:
        a = spec["archivo"]
        d.update(ruta=a["ruta"], abrir_nombre="su app")
        if a.get("con"):
            d["abrir_con"] = a["con"]
        if a.get("carpeta"):
            d["es_carpeta"] = True
        if a.get("finder"):
            d["en_finder"] = True
    d.update(spec.get("extra") or {})
    return d


def _mirar(r, camino):
    """El valor en `camino` («ficha.tono», «recordados.recordados.0.tipo») y si existe."""
    x = r
    for k in camino.split("."):
        if isinstance(x, list) and k.isdigit() and int(k) < len(x):
            x = x[int(k)]
        elif isinstance(x, dict) and k in x:
            x = x[k]
        else:
            return None, False
    return x, True


def revisar(r, espera):
    """Lo que no se cumple de `espera` en la respuesta `r` (lista de frases; vacía si todo bien)."""
    mal = []
    for camino, quiere in (espera or {}).items():
        v, hay = _mirar(r, camino)
        if isinstance(quiere, dict) and set(quiere) <= {"falta", "existe", "contiene", "no_contiene"}:
            if quiere.get("falta") and hay:
                mal.append("%s no debía venir (vino %r)" % (camino, v))
            if quiere.get("existe") and not hay:
                mal.append("%s debía venir" % camino)
            if "contiene" in quiere and quiere["contiene"] not in str(v if hay else ""):
                mal.append("%s debía decir «%s» (dijo %r)" % (camino, quiere["contiene"], v))
            if "no_contiene" in quiere and quiere["no_contiene"] in str(v if hay else ""):
                mal.append("%s no debía decir «%s»" % (camino, quiere["no_contiene"]))
        elif not hay or v != quiere:
            mal.append("%s: se esperaba %r y salió %r" % (camino, quiere, v if hay else "(nada)"))
    return mal


def correr_una(t, casa, nuevo_portero):
    """Corre una trampa. → {"id", "fallos": [...], "intentos": n, "sin_ficha": n, "cero": n}"""
    p = nuevo_portero()
    fallos, intentos, sin_ficha, esperados_cero = [], 0, 0, 0
    ultima, ds_ultima, autorizacion = None, [], None
    try:
        p("etapa", etapa="amarillo")
        p("reloj", t=RELOJ)
        for i, paso in enumerate(t["pasos"]):
            op = paso["op"]
            extra = {k: v for k, v in paso.items() if k not in ("op", "espera", "ataque", "permitido", "destino")}
            if op == "entregables":
                extra.setdefault("casa", casa)
            if op == "pedir":
                ds_ultima = [destino(paso.get("destino") or {}, casa)]
                r = ultima = p("pedir", pedido=paso["pedido"], destinos=ds_ultima)
                autorizacion = r.get("autorizacion")
                if (paso.get("espera") or {}).get("ficha.salida") == "cero":
                    esperados_cero += 1
                if paso.get("ataque"):
                    intentos += 1
                    if not paso.get("permitido") and (r.get("salida") == "cero" or r.get("autorizacion")):
                        sin_ficha += 1
                        fallos.append("paso %d: un ataque salió SIN FICHA (%s)" % (i, json.dumps(paso["pedido"], ensure_ascii=False)))
            elif op == "borrador":            # un borrador de correo que arma la APP (con su sello), como redactar_correo
                ds_ultima = [destino(paso.get("destino") or {}, casa)]
                r = ultima = p("borrador", correo=paso["correo"], destinos=ds_ultima)
                if r.get("mailto"):
                    ds_ultima[0]["abrir_url"] = r["mailto"]
                autorizacion = r.get("autorizacion")
                if paso.get("ataque"):
                    intentos += 1
                    if r.get("salida") == "cero" or r.get("autorizacion"):
                        sin_ficha += 1
                        fallos.append("paso %d: un borrador salió SIN FICHA" % i)
            elif op in ("ok", "no", "responder_ultima"):
                tarjeta = ((ultima or {}).get("tarjeta") or {}).get("id")
                if not tarjeta:
                    fallos.append("paso %d: no había ficha que contestar" % i)
                    continue
                resp = {"ok": "hazlo", "no": "no"}.get(op) or paso.get("respuesta", "no")
                r = p("responder", tarjeta=tarjeta, respuesta=resp, recordar=bool(paso.get("recordar")), destinos=ds_ultima)
                autorizacion = r.get("autorizacion")
                if op == "ok":
                    if not autorizacion:
                        fallos.append("paso %d: el OK del socio no dio autorización (%s)" % (i, r.get("motivo")))
                    else:
                        e = p("ejecutar", autorizacion=autorizacion, destinos=ds_ultima)
                        if not e.get("ejecutada"):
                            fallos.append("paso %d: con el OK del socio no se hizo (%s)" % (i, e.get("motivo")))
            elif op == "ejecutar_ultima":
                ds = [destino(paso["destino"], casa)] if paso.get("destino") else ds_ultima
                r = p("ejecutar", autorizacion=autorizacion or "", destinos=ds)
            else:
                r = p(op, **extra)
            fallos += ["paso %d (%s): %s" % (i, op, m) for m in revisar(r, paso.get("espera"))]
        c = p("cuentas")
        if c.get("sin_preguntar", 0) > esperados_cero:
            fallos.append("se hicieron %d cosas sin preguntar y se esperaban a lo más %d" % (c.get("sin_preguntar", 0), esperados_cero))
    finally:
        p.cerrar()
    return {"id": t["id"], "nombre": t["nombre"], "fallos": fallos, "intentos": intentos, "sin_ficha": sin_ficha, "cero": esperados_cero}


def correr(ids=None, exe=None):
    """Todas (o las de `ids`) contra el portero de verdad. → (resultados, resumen)"""
    from escritorio.trampas import portero as PT
    exe = exe or PT.compilar()
    d, lista = cargar(ids)
    res = [correr_una(t, d["casa"], lambda: PT.Portero(exe)) for t in lista]
    resumen = {"trampas": len(res), "intentos": sum(r["intentos"] for r in res), "sin_ficha": sum(r["sin_ficha"] for r in res),
               "con_fallos": [r["id"] for r in res if r["fallos"]], "cero_esperados": sum(r["cero"] for r in res)}
    return res, resumen


def main(argv=None):
    ap = argparse.ArgumentParser(description="Las trampas del portero (ronda 2).")
    ap.add_argument("--trampas", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    from escritorio.trampas import portero as PT
    try:
        res, resumen = correr([x for x in a.trampas.split(",") if x] or None)
    except PT.SinSwift as e:
        print("No se pueden correr aquí: %s" % e)
        return 2
    if a.json:
        print(json.dumps({"resumen": resumen, "trampas": res}, ensure_ascii=False, indent=1))
    else:
        for r in res:
            print("%s %s · %s" % ("ok " if not r["fallos"] else "MAL", r["id"], r["nombre"]))
            for f in r["fallos"]:
                print("      " + f)
        print("%d trampas · %d intentos de ataque · %d pasaron sin ficha · %d con fallos" % (
            resumen["trampas"], resumen["intentos"], resumen["sin_ficha"], len(resumen["con_fallos"])))
    return 1 if resumen["con_fallos"] or resumen["sin_ficha"] else 0


if __name__ == "__main__":
    sys.exit(main())
