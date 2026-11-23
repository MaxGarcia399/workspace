"""WORKSPACE · control/ausente.py — Monito ronda 2 · P2-b: «si no estás, no se pierde y el agente no se queda colgado».

Solo en la conversación del monito de escritorio (la página del navegador sigue como siempre).

  · Un permiso de su motor que nadie contesta en ESPERA_S (3 min): Workspace le contesta al agente «tu socio no está;
    deja esto pendiente y termina con un resumen» (TEXTO) para que cierre su turno, y guarda el pedido EXACTO (su
    herramienta y su entrada entera, por su huella) como DIFERIDO. La ficha del monito se queda: «Atlas quería buscar
    en internet · [Permitir y seguir]».
  · Ya ausente en ese turno, los siguientes pedidos no esperan otros 3 minutos cada uno: se difieren al llegar.
  · El clic del socio (`permitir_despues`): un PASE de UN SOLO USO para exactamente ese pedido (misma herramienta, misma
    entrada, byte por byte) y un mensaje nuevo al agente. Cuando su motor vuelve a pedir justo eso, pasa una vez
    (`pase`); cualquier otra cosa, o lo mismo por segunda vez, vuelve a preguntar. El pase vence a los PASE_S.
  · Nunca pasa lo prohibido de leer ni salta nada del motor: el pase solo contesta «permitir» a un pedido que el
    motor hizo por su vía de permisos, igual que el clic de la tarjeta.

Lo engancha control/base.py en cuatro renglones (texto_cancelado, mandar y dos en _anunciar_permiso) y la página en
dos (la foto y la ruta /api/v2/permiso_despues). Vive en memoria: si la página se reinicia, lo diferido se pierde y la
ficha lo dice («Ya pasó · Pedírselo otra vez»); lo interrumpido por el reinicio lo cubre control/base (E9).
Stdlib. Python 3.9."""
import hashlib
import json
import os
import threading
import time

#: Lo que se espera a que el socio conteste un permiso en el monito antes de dejarlo para después.
ESPERA_S = float(os.environ.get("WORKSPACE_AUSENTE_S") or 180)
#: Lo que vale el pase de un solo uso después del clic (el agente tiene que volver a pedirlo en ese rato).
PASE_S = 600.0
#: Tope de diferidos por conversación (lo más viejo se cae: nadie aprueba 40 fichas).
TOPE = 40
CORTE = "ausente"
TEXTO = ("Tu socio no está frente a su compu ahora: este permiso quedó PENDIENTE (no lo negó). No lo intentes por otro "
         "camino ni lo vuelvas a pedir. Termina tu turno ya, con un resumen corto de lo que hiciste y de lo que quedó "
         "esperando su permiso. Workspace le dejó una ficha: cuando vuelva y la apruebe, te llega un mensaje para que "
         "sigas.")

_CANDADO = threading.RLock()
_ESTADOS = {}


class _Estado(object):
    def __init__(self):
        self.diferidos = []           # [{id, huella, herramienta, detalle, que, archivo, pedido}]
        self.pases = {}               # huella → vence (reloj monotónico)
        self.ausente = False          # en este turno ya se supo que no está
        self.n = 0
        self.relojes = {}             # pid → Timer


def _clave(cwd, ws="escritorio"):
    try:
        cwd = os.path.realpath(cwd or "")
    except (OSError, ValueError):
        cwd = str(cwd or "")
    return (cwd, str(ws or ""))


def _de(con):
    return _clave(getattr(con, "cwd", ""), (getattr(con, "pestana", None) or {}).get("ws") or "")


def _estado(clave):
    with _CANDADO:
        e = _ESTADOS.get(clave)
        if e is None:
            e = _ESTADOS[clave] = _Estado()
        return e


def huella(herramienta, detalle):
    """La huella del pedido EXACTO: su herramienta y su entrada entera (no recortada), en forma canónica."""
    try:
        cuerpo = json.dumps([str(herramienta or ""), detalle], sort_keys=True, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):
        cuerpo = repr([str(herramienta or ""), detalle])
    return hashlib.sha256(cuerpo.encode("utf-8", "replace")).hexdigest()


def _en_monito(con):
    try:
        return bool(con.en_escritorio())
    except Exception:
        return False


def reiniciar():
    """Solo pruebas: todo de cero."""
    with _CANDADO:
        for e in _ESTADOS.values():
            for t in e.relojes.values():
                t.cancel()
        _ESTADOS.clear()


# ── lo que engancha control/base.py ──────────────────────────────────────────
def presente(con):
    """Llegó un mensaje nuevo a la conversación (el socio está, o empieza otro turno): se vuelve a esperar ESPERA_S."""
    if not _en_monito(con):
        return
    _estado(_de(con)).ausente = False


def pase(con, herramienta, detalle, ahora=None):
    """¿El socio ya permitió EXACTAMENTE este pedido con «Permitir y seguir»? Gasta el pase (un solo uso)."""
    if not _en_monito(con):
        return False
    ahora = time.monotonic() if ahora is None else ahora
    h = huella(herramienta, detalle)
    with _CANDADO:
        e = _estado(_de(con))
        for k in [k for k, v in e.pases.items() if v < ahora]:
            e.pases.pop(k, None)
        return e.pases.pop(h, None) is not None


def vigilar(con, pid, herramienta, detalle, que=None, archivo="", corto=None):
    """Un permiso que ya espera al socio (id corto `pid`): si en ESPERA_S nadie lo contesta, se difiere. Con el socio ya
    ausente en este turno, se difiere enseguida."""
    if not _en_monito(con):
        return
    datos = {"herramienta": str(herramienta or "?"), "huella": huella(herramienta, detalle),
             "detalle": corto(detalle) if corto else str(detalle)[:400], "que": que if isinstance(que, dict) else {},
             "archivo": str(archivo or ""), "pedido": time.time()}
    e = _estado(_de(con))
    espera = 0.05 if e.ausente else ESPERA_S
    t = threading.Timer(espera, _vence, args=(con, pid, datos))
    t.daemon = True
    with _CANDADO:
        e.relojes[pid] = t
    t.start()


def _vence(con, pid, datos):
    e = _estado(_de(con))
    with _CANDADO:
        e.relojes.pop(pid, None)
    try:
        with con._candado:
            responder = con._permisos.pop(pid, None)
            if responder is None:
                return                      # ya lo contestó (o se canceló): nada que diferir
            con._de_motor = {k: v for k, v in con._de_motor.items() if v != pid}
            if hasattr(con, "_pedidos"):
                con._pedidos.pop(pid, None)
            try:
                con._lic()[2].pop(pid, None)
            except Exception:
                pass
            if not con._permisos and con._estado == "esperando_permiso":
                con._estado = "trabajando"
            antes = getattr(con, "_motivo_corte", "")
            con._motivo_corte = CORTE       # texto_cancelado(«ausente») → TEXTO, por la vía de su motor
    except Exception:
        return
    with _CANDADO:
        e.ausente = True
        e.n += 1
        d = dict(datos, id="d%d" % e.n)
        e.diferidos.append(d)
        del e.diferidos[:-TOPE]
    try:
        hid = "ausente-%s" % d["id"]
        nombre = "Workspace dejó un permiso para después (su socio no está)"
        con._emitir("herramienta", id=hid, nombre=nombre, fase="empieza", detalle=datos["detalle"])
        con._emitir("herramienta", id=hid, nombre=nombre, fase="falla", detalle=TEXTO)
    except Exception:
        pass
    try:
        responder(None)
    finally:
        try:
            with con._candado:
                if getattr(con, "_motivo_corte", "") == CORTE:
                    con._motivo_corte = antes
        except Exception:
            pass


# ── lo que usa la página ─────────────────────────────────────────────────────
def diferidos(cwd, ws="escritorio"):
    """Lo que quedó para después en esa conversación: [{id, herramienta, detalle, que, archivo, pedido}] (sin huella)."""
    with _CANDADO:
        e = _ESTADOS.get(_clave(cwd, ws))
        return [{k: v for k, v in d.items() if k != "huella"} for d in (e.diferidos if e else [])]


def _cortado(d):
    """¿Ese diferido no se pudo enseñar entero en la ficha? (el comando venía más largo, o su detalle va recortado
    y la app no conoce la herramienta: lo mismo que decide escritorio/fichas_motor.clase_dato_cortado)"""
    que = d.get("que") if isinstance(d.get("que"), dict) else {}
    if que.get("cortado"):
        return True
    try:
        from escritorio import fichas_motor
        return bool(fichas_motor.clase_dato_cortado(d)[2])
    except Exception:
        return True                                   # falla-cerrado: sin poder saberlo, no hay pase


def permitir_despues(cwd, ids, ws="escritorio", ahora=None):
    """El clic del socio en «Permitir y seguir» para esos diferidos: un pase de un solo uso por cada pedido exacto.
    → {"n": cuántos, "pedidos": [los diferidos que se permitieron]} (n 0: ya no estaban)."""
    ahora = time.monotonic() if ahora is None else ahora
    ids = set(str(i) for i in (ids or []))
    with _CANDADO:
        e = _ESTADOS.get(_clave(cwd, ws))
        if e is None:
            return {"n": 0, "pedidos": []}
        pedidos = [d for d in e.diferidos if d["id"] in ids]
        # M-2: lo que no se vio ENTERO no recibe pase (el pase vale para el pedido entero, y la ficha solo enseñó un
        # trozo): se queda pendiente; se permite desde la página, donde se ve completo
        cortados = [d for d in pedidos if _cortado(d)]
        suyos = [d for d in pedidos if not _cortado(d)]
        dados = set(d["id"] for d in suyos)
        e.diferidos = [d for d in e.diferidos if d["id"] not in dados]
        for d in suyos:
            e.pases[d["huella"]] = ahora + PASE_S
        if suyos:
            e.ausente = False
        r = {"n": len(suyos), "pedidos": suyos}
        if cortados:
            r["cortados"] = [d["id"] for d in cortados]
        return r


def revocar(cwd, pedidos, ws="escritorio"):
    """El mensaje no salió: los pases se quitan y los pedidos vuelven a quedar diferidos."""
    with _CANDADO:
        e = _estado(_clave(cwd, ws))
        for d in pedidos or []:
            e.pases.pop(d.get("huella"), None)
            e.diferidos.append(d)


def descartar(cwd, ids, ws="escritorio"):
    """«No» en una ficha diferida: se olvida (sin pase)."""
    ids = set(str(i) for i in (ids or []))
    with _CANDADO:
        e = _ESTADOS.get(_clave(cwd, ws))
        if e is None:
            return 0
        n = len(e.diferidos)
        e.diferidos = [d for d in e.diferidos if d["id"] not in ids]
        return n - len(e.diferidos)


#: Lo que se le dice al agente con el clic (lo arma Workspace con la clase del pedido; nunca texto del agente).
_CLASES = {"comando": "correr un comando", "crear": "crear un archivo", "cambiar": "cambiar un archivo",
           "borrar": "borrar un archivo", "leer": "leer un archivo", "buscar": "buscar en sus archivos",
           "web": "usar internet", "otra": "usar una de tus herramientas"}


def mensaje(pedidos):
    """El mensaje nuevo que lleva el permiso de un solo uso."""
    cosas = []
    for d in pedidos:
        c = _CLASES.get(str((d.get("que") or {}).get("clase") or "otra"), _CLASES["otra"])
        cosas.append("%s (%s)" % (c, d.get("herramienta") or "?"))
    lista = "; ".join(cosas)
    uno = len(pedidos) == 1
    return ("Tu socio ya volvió y permitió lo que quedó pendiente: %s. El permiso es de UN SOLO USO y vale para "
            "exactamente %s (misma herramienta, mismos datos): vuelve a pedirlo igual, ahora, y sigue con lo que "
            "estabas haciendo. Cualquier otra cosa se le vuelve a preguntar."
            % (lista, "ese pedido" if uno else "esos pedidos"))


def para_la_foto(sesion, con):
    """Lo que el monito necesita para sus fichas, con datos de Workspace: todos los permisos que su motor sigue
    esperando (no solo el primero) y lo que quedó para después. Nunca levanta."""
    try:
        todos = ([sesion.permiso] if sesion.permiso else []) + list(sesion.en_espera)
        try:
            vivos = set(con.permisos_pendientes()) if con is not None else None
        except Exception:
            vivos = None
        esperan = [{"id": p.get("id"), "herramienta": p.get("herramienta") or "", "detalle": p.get("detalle") or "",
                    "archivo": p.get("archivo") or "", "que": p.get("que") or {}, "opciones": p.get("opciones") or [],
                    "grupo": bool(p.get("grupo"))}
                   for p in todos if p.get("id") and (vivos is None or p["id"] in vivos)]
        return {"esperan": esperan, "despues": diferidos(sesion.brain), "espera_s": ESPERA_S,
                "interrumpidos": interrumpidos(sesion)}
    except Exception:
        return {"esperan": [], "despues": [], "espera_s": ESPERA_S, "interrumpidos": 0}


def interrumpidos(sesion):
    """Cuántos permisos de esa conversación quedaron SIN contestar por un reinicio de la página (E9, carril 5:
    pagina_v2.guardar_interrumpidos) y todavía no se le recuerdan al agente. Solo el número: la ficha la arma la app."""
    try:
        import pagina_v2 as v2
        with open(v2._ruta_interrumpidos(sesion.brain, sesion.wid), encoding="utf-8") as fh:
            d = json.load(fh)
        if time.time() - float(d.get("t") or 0) > v2.INTERRUMPIDOS_VENCE_S:
            return 0
        return len([x for x in (d.get("permisos") or []) if isinstance(x, str)])
    except Exception:
        return 0


def de_la_pagina(v2, agente, ids, decision):
    """POST /api/v2/permiso_despues {agente, ids, decision: permitir|negar} (solo el monito). Con «permitir»: los pases
    y el mensaje nuevo a su conversación del monito."""
    s = v2.sesion(agente, crear=True, canal=v2.ESC)
    if s is None:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    if decision == "negar":
        return {"ok": True, "n": descartar(s.brain, ids)}
    if decision != "permitir":
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    r = permitir_despues(s.brain, ids)
    if not r["n"]:
        return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_permiso"}
    try:
        m = v2.mandar(agente, mensaje(r["pedidos"]), canal=v2.ESC)
    except Exception:
        m = {"ok": False, "status": 500, "error": "localhost.err.interno"}
    if not (isinstance(m, dict) and m.get("ok")):
        revocar(s.brain, r["pedidos"])
        return m if isinstance(m, dict) else {"ok": False, "status": 500, "error": "localhost.err.interno"}
    return {"ok": True, "n": r["n"]}
