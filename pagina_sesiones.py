#!/usr/bin/env python3
"""WORKSPACE · pagina_sesiones — las sesiones oficiales de un agente, vistas desde su conversación directa (H3 del
Plan_Hub_Directo; rama de prueba zenith/marca-lab).

Las pestañas del cliente oficial de cada motor (Claude Code, Codex… en su terminal) son un sistema aparte de la
conversación directa. Aquí salen dos cosas, de su registro de eventos del núcleo (arquitectura/registro), sin mirar
ninguna pantalla:
  · la lista «Sesiones»: cada pestaña con su motor, su estado y lo último que terminó;
  · la línea que recibe la conversación directa cuando una sesión termina algo: un evento «sistema · sesion» en su
    historial (solo se anexa; su id sale de la sesión y la hora, así no se repite). No es un turno: no parte los
    tramos de motor ni entra en la nota de contexto. La conversación lo devuelve aparte (`sesiones`), con el turno
    antes del que va.
Cada registro se lee de a poco (solo lo que creció) y se recuerda por pestaña. Stdlib."""
import hashlib
import os
import threading
import time

NAV = "navegador"
#: Cuántas sesiones se listan, y cuántas líneas de sesión devuelve la conversación.
TOPE_LISTA, TOPE_LINEAS = 12, 30
TEXTO_MAX = 240
_ESTADO = {"session_start": "abierto", "user_prompt": "pensando", "pre_tool": "usando", "post_tool": "pensando",
           "permission_request": "esperando_permiso", "turn_end": "listo", "session_end": "cerrado"}
_RES = {}                  # ruta del registro → {"fin", "ino", "res"}
_LOCK = threading.Lock()


def _vacio():
    return {"estado": "sin_datos", "desde": "", "motor": "", "abierta": False, "pregunta": False, "fin": None}


def _primera(texto):
    for ln in str(texto or "").splitlines():
        ln = " ".join(ln.split())
        if ln:
            return ln[:TEXTO_MAX]
    return ""


def _sumar(res, e):
    """Un evento más al resumen de la pestaña (lo mismo que registro.estado, de a uno)."""
    m, d = e.get("momento"), e.get("datos") or {}
    if d.get("via") == "pagina":
        return                                   # las corridas de la página son la conversación directa
    if m == "pregunta":
        res["pregunta"] = True
        return
    if m == "respuesta":
        res["pregunta"] = False
        return
    nuevo = _ESTADO.get(m)
    if not nuevo:
        return                                   # conversacion, error, tarea, compact: no cambian en qué está
    if m in ("session_start", "session_end", "user_prompt"):
        res["pregunta"] = False
    res["motor"] = e.get("motor") or res["motor"]
    if nuevo != res["estado"]:
        res["desde"] = e.get("ts") or ""
    res["estado"] = nuevo
    if m == "session_start":
        res["abierta"] = True
    elif m == "session_end":
        res["abierta"] = False
    elif m == "turn_end":
        res["fin"] = {"ts": e.get("ts") or "", "texto": _primera(d.get("last_assistant_message")),
                      "motor": e.get("motor") or res["motor"]}


def resumen(brain, wid):
    """Lo que dice el registro de la pestaña `wid`, leyendo solo lo nuevo desde la última vez. None si no tiene."""
    from arquitectura import registro
    r = registro.ruta(brain, wid)
    try:
        st = os.stat(r)
    except OSError:
        return None
    with _LOCK:
        c = _RES.get(r)
        if c is None or c["ino"] != st.st_ino or st.st_size < c["fin"]:
            c = {"fin": 0, "ino": st.st_ino, "res": _vacio()}
        if st.st_size > c["fin"]:
            evs, fin = registro.leer(brain, wid, c["fin"])
            for e in evs:
                _sumar(c["res"], e)
            c["fin"] = fin
        _RES[r] = c
        return dict(c["res"])


def simple(res):
    """trabajando · te_espera · abierta · cerrada: lo que se dice de una sesión."""
    if not res:
        return "cerrada"
    if res["estado"] == "esperando_permiso" or res.get("pregunta"):
        return "te_espera"
    if res["estado"] in ("pensando", "usando"):
        return "trabajando"
    return "abierta" if res.get("abierta") and res["estado"] != "cerrado" else "cerrada"


def _utc(ts):
    try:
        from arquitectura import registro
        return registro.ts_utc(ts) or ""
    except Exception:
        return ""


def lista(brain, tabs, nav_wid, wid_de, archivada=lambda bt: False):
    """Las sesiones oficiales del cerebro: sus pestañas (sin la de la conversación directa ni las archivadas), lo
    más reciente primero. `wid_de(bt)`: el id con que se registra (localhost_web._wid_de)."""
    out = []
    for bt in tabs or []:
        wid = wid_de(bt)
        if not wid or wid == nav_wid or bt.get("slug") == NAV or archivada(bt):
            continue
        res = resumen(brain, wid)
        cuando = max(_utc((res or {}).get("desde")), _utc(bt.get("actualizada")))
        out.append({"wid": wid, "slug": str(bt.get("slug") or "")[:120], "nombre": str(bt.get("name") or "")[:120],
                    "motor": (res or {}).get("motor") or "", "estado": simple(res), "cuando": cuando,
                    "ultimo": (res or {}).get("fin")})
    vivas = ("trabajando", "te_espera")
    out.sort(key=lambda s: (s["estado"] in vivas, s["cuando"]), reverse=True)
    return out[:TOPE_LISTA]


def _id(wid, ts):
    return "ses-" + hashlib.sha1(("%s|%s" % (wid, ts)).encode("utf-8")).hexdigest()[:16]


def _hora_de(e):
    """La hora de un evento de la conversación, en UTC con milisegundos: su `t` exacto si lo tiene (su `ts` va al
    segundo: lo de medio segundo antes quedaría «después»)."""
    t = e.get("t")
    if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0:
        import datetime as _dt
        d = _dt.datetime.fromtimestamp(t, _dt.timezone.utc)
        return d.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (d.microsecond // 1000)
    return _utc(e.get("ts"))


def lineas_nuevas(sesiones, hist):
    """Los eventos «sistema · sesion» que le faltan a la conversación directa: por sesión, lo ÚLTIMO que terminó si
    pasó después de que la conversación existía y después de su última línea. Uno por sesión: si estuvo apagada la
    página, al volver llega solo lo más nuevo de cada una. Pura."""
    inicio = next((h for h in (_hora_de(e) for e in hist) if h), "")
    if not inicio:
        return []
    puestas = {}
    for e in hist:
        if e.get("rol") == "sistema" and e.get("tipo") == "sesion":
            puestas[e.get("sesion")] = max(puestas.get(e.get("sesion"), ""), _utc(e.get("ts")))
    out = []
    for s in sesiones:
        u = s.get("ultimo") or {}
        ts = _utc(u.get("ts"))
        if not ts or ts <= inicio or ts <= puestas.get(s["wid"], ""):
            continue
        out.append({"id": _id(s["wid"], ts), "rol": "sistema", "tipo": "sesion", "texto": u.get("texto") or "",
                    "motor": "", "sesion": s["wid"], "nombre": s.get("nombre") or "",
                    "sesion_motor": u.get("motor") or s.get("motor") or "", "ts": ts, "t": time.time()})
    return out


def en_la_conversacion(evs, turnos, base):
    """Las líneas de sesión de los eventos (ya en orden de hora) con el turno ANTES del que van (índice absoluto, como
    los de `motores`): el primer turno de la ventana más nuevo que la línea; si no hay, al final."""
    out = []
    for e in evs:
        if e.get("rol") != "sistema" or e.get("tipo") != "sesion":
            continue
        ts = _utc(e.get("ts"))
        i = next((j for j, t in enumerate(turnos) if _utc(t.get("ts")) > ts), len(turnos))
        out.append({"i": base + i, "ts": ts, "texto": str(e.get("texto") or "")[:TEXTO_MAX],
                    "motor": str(e.get("sesion_motor") or "")[:30], "nombre": str(e.get("nombre") or "")[:120]})
    return out[-TOPE_LINEAS:]


def cuenta(sesiones):
    """{n, trabajando, te_espera}: lo que la foto dice de sus sesiones."""
    return {"n": len(sesiones), "trabajando": sum(s["estado"] == "trabajando" for s in sesiones),
            "te_espera": sum(s["estado"] == "te_espera" for s in sesiones)}
