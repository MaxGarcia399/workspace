#!/usr/bin/env python3
"""WORKSPACE · pagina_pestanas — las pestañas de la conversación directa de cada agente (H4-a «pestañas en el borde»).

Cada agente tiene su conversación de siempre (⌂, la pestaña «navegador»: siempre primera, no se cierra) y, al lado,
otras pestañas: cada una es UNA de sus sesiones, las mismas que abres en su programa oficial (la lista de S-1). Una se
abre con «+»: una de sus sesiones o una conversación nueva (que también queda en esa lista).

Aquí se guarda SOLO cuáles están abiertas y en qué orden, por agente, en el estado local de esta máquina
(`<state_dir>/pagina/pestanas/<agente>.json`): lo mismo para el hub y la página, que son dos vistas del mismo servidor.
Cerrar una pestaña no borra nada: la sesión sigue en su lista y en su programa. La pestaña que se pasa del tope cierra
sola la que llevas más tiempo sin ver (con su «deshacer»).

Una pestaña es {slug, nombre, wid, motor, tipo, abierta, visto, sesiones?, de?, registro_desde?}:
  · slug: el de su sesión en el registro de sesiones (sessions_registry): la llave de la pestaña, como «navegador» lo
    es de la de siempre (y «escritorio», la del monito de escritorio, cuando llegue): así cualquier conversación de la
    página es (agente, slug), sin un esquema aparte;
  · tipo: «sesion» (una que ya existía en su programa) o «nueva» (la creó la página);
  · sesiones: {conector: número} de la conversación de su motor que la página abrió para ella (Codex: su hilo);
  · de: la pestaña de la que salió (cambiar el motor de una sesión oficial abre otra con la nota de contexto);
  · registro_desde: hasta dónde su historial ya trae lo de su programa (lo que siguió entra por su registro).
Varias vistas y procesos escriben el mismo archivo (el servidor de la página, el hub, la página vieja que todavía no se
apaga tras una actualización): leer, cambiar y guardar van bajo su candado entre procesos (olock) y el guardado es el
común (estado_json → atomico). Uno que no se entiende (dañado, o con otra forma) se aparta con otro nombre y se avisa:
nunca se guarda encima. Stdlib."""
import contextlib
import os
import re
import threading
import time

import paths as _paths
from arquitectura import estado_json
from olock import file_lock

NAV = "navegador"
#: La pestaña del monito de escritorio (otra rama): nunca va en la tira, y no se puede abrir como sesión.
ESC = "escritorio"
RESERVADAS = (NAV, ESC)
#: Cuántas pestañas a la vez por agente, ⌂ incluida: abrir la siguiente cierra sola la que llevas más tiempo sin ver.
TOPE = 8
#: Cuántas cerradas se recuerdan para «deshacer».
DESHACER_MAX = 5
TIPOS = ("sesion", "nueva")
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
_LOCK = threading.RLock()


def valido(slug):
    """¿`slug` puede ser una pestaña de sesión? (la forma de un slug y no una de las fijas)."""
    return bool(isinstance(slug, str) and _SLUG.match(slug) and slug not in RESERVADAS)


def ruta(agente):
    return os.path.join(_paths.state_dir(), "pagina", "pestanas", "%s.json" % agente)


def _vacio():
    return {"v": 1, "orden": [], "tabs": {}, "deshacer": [], "ultima": NAV}


def _limpio(d):
    """Lo leído, con su forma: solo pestañas válidas, cada una una vez y en `orden`."""
    out = _vacio()
    if not isinstance(d, dict):
        return out
    tabs = d.get("tabs") if isinstance(d.get("tabs"), dict) else {}
    for sl in d.get("orden") or []:
        rec = tabs.get(sl)
        if valido(sl) and isinstance(rec, dict) and sl not in out["tabs"]:
            out["orden"].append(sl)
            out["tabs"][sl] = dict(rec, slug=sl)
    out["deshacer"] = [x for x in (d.get("deshacer") or []) if isinstance(x, dict) and isinstance(x.get("tab"), dict)
                       and valido(x["tab"].get("slug"))][-DESHACER_MAX:]
    u = d.get("ultima")
    out["ultima"] = u if u == NAV or u in out["tabs"] else NAV
    return out


def _forma(d):
    """¿Lo leído tiene la forma de una lista de pestañas? (revisor 5: un campo con otro tipo cuenta como dañado)."""
    return (isinstance(d.get("tabs", {}), dict) and isinstance(d.get("orden", []), list)
            and isinstance(d.get("deshacer", []), list))


def leer(agente):
    """La lista del agente para mirarla. Una ilegible se ve vacía, pero no se toca: la aparta el que va a guardar."""
    try:
        return _limpio(estado_json.leer(ruta(agente), valido=_forma))
    except OSError:
        return _vacio()


@contextlib.contextmanager
def _cambiando(agente):
    """«Archivos compartidos»: la lista del agente para cambiarla, bajo el candado entre procesos de su archivo (y el
    de este proceso). Una dañada se aparta (`<nombre>.corrupt-…`, con su aviso) y se sigue con una nueva; si no se pudo
    apartar, sube el error y no se guarda nada encima. Quien cambia algo llama a _guardar dentro."""
    r = ruta(agente)
    with _LOCK, file_lock(r):
        try:
            d = estado_json.leer(r, apartar=True, valido=_forma)
        except ValueError:                       # ya quedó aparte y avisado: lo de ahora, sin ella
            d = estado_json.leer(r, apartar=True, valido=_forma)
        yield _limpio(d)


def _guardar(agente, d):
    """El guardado común (temporal único en la misma carpeta + os.replace con sus reintentos). Bajo _cambiando."""
    estado_json.escribir(ruta(agente), d)


def firma(agente):
    """Lo barato de mirar: si cambió el archivo, cambió la tira."""
    try:
        st = os.stat(ruta(agente))
        return "%d.%d" % (st.st_size, st.st_mtime_ns)
    except OSError:
        return "-"


def abiertas(agente):
    """Las pestañas abiertas del agente (sin ⌂), en su orden."""
    d = leer(agente)
    return [d["tabs"][sl] for sl in d["orden"]]


def de(agente, slug):
    """La pestaña abierta `slug`, o None."""
    return leer(agente)["tabs"].get(slug)


def _mas_vieja(d, menos=(), ocupadas=()):
    """La que llevas más tiempo sin ver (ni la nueva ni una que trabaja)."""
    cand = [d["tabs"][sl] for sl in d["orden"] if sl not in menos and sl not in ocupadas]
    if not cand:
        return None
    return min(cand, key=lambda t: (float(t.get("visto") or 0), float(t.get("abierta") or 0)))


def _quitar(d, slug, motivo, ahora):
    i = d["orden"].index(slug)
    rec = d["tabs"].pop(slug)
    d["orden"].remove(slug)
    d["deshacer"] = (d["deshacer"] + [{"tab": rec, "pos": i, "t": ahora, "motivo": motivo}])[-DESHACER_MAX:]
    if d.get("ultima") == slug:
        d["ultima"] = NAV
    return rec


def _al_tope(d, nueva, ahora, ocupadas):
    """Si hay más de TOPE (⌂ incluida), cierra la que llevas más tiempo sin ver. → la cerrada o None."""
    if len(d["orden"]) + 1 <= TOPE:
        return None
    vieja = _mas_vieja(d, (nueva,), ocupadas)
    return _quitar(d, vieja["slug"], "tope", ahora) if vieja else None


def abrir(agente, rec, ahora=None, ocupadas=()):
    """Abre (o enfoca) la pestaña `rec` ({slug, nombre, wid, motor, tipo, …}). Ya abierta: solo se marca vista.
    → (la pestaña, la que se cerró sola por el tope o None). `ocupadas`: las que trabajan (nunca se cierran solas)."""
    ahora = time.time() if ahora is None else ahora
    sl = (rec or {}).get("slug")
    if not valido(sl):
        raise ValueError("pestaña inválida: %r" % (sl,))
    with _cambiando(agente) as d:
        if sl in d["tabs"]:
            t = d["tabs"][sl]
            t["visto"] = ahora
            for k in ("nombre", "wid"):
                if rec.get(k) and not t.get(k):
                    t[k] = rec[k]
            d["ultima"] = sl
            _guardar(agente, d)
            return dict(t), None
        # una que se cerró hace poco vuelve con lo que tenía (su tipo, los números de su motor, de dónde salió)
        previa = next((dict(x["tab"]) for x in reversed(d["deshacer"]) if x["tab"].get("slug") == sl), {})
        t = dict(previa, **{k: v for k, v in rec.items() if v not in (None, "")})
        if previa.get("tipo"):
            t["tipo"] = previa["tipo"]
        t.update(slug=sl, abierta=ahora, visto=ahora)
        if t.get("tipo") not in TIPOS:
            t["tipo"] = "sesion"
        d["tabs"][sl] = t
        d["orden"].append(sl)
        d["ultima"] = sl
        d["deshacer"] = [x for x in d["deshacer"] if x["tab"].get("slug") != sl]
        cerrada = _al_tope(d, sl, ahora, ocupadas)
        _guardar(agente, d)
        return dict(t), cerrada


def cerrar(agente, slug, ahora=None):
    """Cierra la pestaña (la sesión no se toca). → la cerrada, o None si no estaba abierta (⌂ no se cierra)."""
    ahora = time.time() if ahora is None else ahora
    with _cambiando(agente) as d:
        if slug not in d["tabs"]:
            return None
        rec = _quitar(d, slug, "cerrada", ahora)
        _guardar(agente, d)
        return rec


def deshacer(agente, ahora=None, ocupadas=()):
    """Vuelve a abrir la última que se cerró, en su lugar. → (la pestaña, la que se cerró sola por el tope) o
    (None, None) si no hay nada que deshacer."""
    ahora = time.time() if ahora is None else ahora
    with _cambiando(agente) as d:
        while d["deshacer"]:
            x = d["deshacer"].pop()
            rec = x["tab"]
            sl = rec.get("slug")
            if sl in d["tabs"]:
                continue
            rec = dict(rec, visto=ahora)
            d["tabs"][sl] = rec
            d["orden"].insert(max(0, min(int(x.get("pos") or 0), len(d["orden"]))), sl)
            d["ultima"] = sl
            cerrada = _al_tope(d, sl, ahora, ocupadas)
            _guardar(agente, d)
            return dict(rec), cerrada
        _guardar(agente, d)
        return None, None


def ver(agente, slug, ahora=None, cada=30.0):
    """La viste ahora (para saber cuál llevas más tiempo sin ver). Escribe a lo más una vez cada `cada` s."""
    ahora = time.time() if ahora is None else ahora
    t = leer(agente)["tabs"].get(slug)
    if t is None or ahora - float(t.get("visto") or 0) < cada:
        return False                             # lo de casi siempre (cada vez que se lee su conversación): sin candado
    with _cambiando(agente) as d:
        t = d["tabs"].get(slug)
        if t is None or ahora - float(t.get("visto") or 0) < cada:
            return False
        t["visto"] = ahora
        _guardar(agente, d)
        return True


def poner(agente, slug, **campos):
    """Cambia campos de una pestaña abierta (`sesiones` se junta con lo que tenía). → True si estaba abierta."""
    with _cambiando(agente) as d:
        t = d["tabs"].get(slug)
        if t is None:
            return False
        for k, v in campos.items():
            if k == "sesiones" and isinstance(v, dict):
                t["sesiones"] = dict(t.get("sesiones") or {}, **v)
            elif k != "slug":
                t[k] = v
        _guardar(agente, d)
        return True


def ultima_cerrada(agente):
    """La última que se cerró (para el aviso de «deshacer»), o None."""
    d = leer(agente)
    return dict(d["deshacer"][-1]) if d["deshacer"] else None
