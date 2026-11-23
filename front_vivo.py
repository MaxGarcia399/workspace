#!/usr/bin/env python3
"""La fuente ÚNICA del estado de cada agente para la página (front nuevo).

Antes la página preguntaba cada 1,5–4 s por cinco rutas y el servidor releía todo en cada pregunta
(con 20 agentes, /api/ahora abría 2 300 archivos y tardaba 170 ms; con un transcript de 3 MB que
crece, /api/conversacion lo releía entero: 240 ms por lectura). Ahora:

- **Un hilo** (solo mientras alguna página escucha) mira cada 1–2 s lo barato: `herdr pane list`
  (UNA llamada para todos los paneles) y la firma (inodo/mtime/tamaño) de las ejecuciones y de la
  conversación de cada agente. Lo caro (la pantalla de ESE panel, sus ejecuciones) solo se lee si
  algo cambió. En reposo no abre archivos.
- **Una foto por agente** con la máquina de estados: dormido · libre · enviando → recibido →
  trabajando → terminó / esperándote / error / cambiando (de motor). Cada transición queda con su
  hora (`trans`), para medir latencias. La página la pinta; no la deduce.
- **Versiones.** Cada cambio de una foto sube la versión global. La página pide «lo que cambió desde
  la versión N» y recibe solo esas fotos.

Contrato (lo prueban tests/test_front_vivo.py):

  GET /api/front/vivo?v=<N>&e=<época>&espera=<s>[&act=<agente que ves>]
    → {"ok": true, "e": <época>, "v": <versión>, "t": <hora del servidor>, "completo": bool,
       "agentes": {<agente>: <foto>}}
    Long-poll: si no hay nada más nuevo que N, espera hasta `espera` s (tope 25; 0 = no espera: el
    respaldo por sondeo). `completo` = trae a TODOS (primera vez, o el servidor se reinició: otra
    época); si no, solo los que cambiaron. Nunca levanta excepción: ante un error, {"ok": false,
    "error": <clave>, "status": 500}.

  <foto> = {"v", "estado", "desde", "trans": [[estado, hora]…], "existe", "viva", "motor", "status",
            "trabajando", "pregunta", "uso", "subagentes", "error", "cambio", "envio", "conv", "cerrado",
            "cola": [lo que espera su caja, en orden: {id, texto, motivo, desde[, salida, caja]}, ver
                     localhost_web.cola_de], "pend": <firma de sus pendientes>,
            "ajustes": {"motor", "valores": {k: {"actual": {v, t, de} | None, "guardado"}}, "guardados"},
            "ejecuciones": [como /api/ejecuciones, solo las de la conversación de la página]}
    (`viva`, `trabajando`, `status`, `pregunta`, `uso`, `subagentes`, `error` y `motor` con la misma
    forma que /api/pantalla?estado=1.)

Envíos idempotentes: /api/pestana/escribir y /api/pestana/abrir aceptan `cid` (id del cliente). El
mismo `cid` dos veces (doble clic, dos pestañas del navegador, un reintento) no se teclea dos veces:
la segunda recibe la misma respuesta (`repetido`).
"""
import os
import secrets
import threading
import time

EPOCA = secrets.token_hex(4)       # cambia en cada arranque: la página sabe que debe pedir todo
ESPERA_MAX = 25.0                  # s que espera un long-poll
TICK_ACTIVO = 1.0                  # s entre vueltas mientras alguien trabaja o se envía algo
TICK_CALMA = 2.0                   # s entre vueltas en reposo
VIDA = 60.0                        # sin páginas escuchando por esto, el hilo se apaga
LEER_ACTIVO = 2.0                  # s: cada cuánto se relee la pantalla de un panel ocupado
LEER_CALMA = 30.0                  # s: y la de uno quieto (por si algo cambió sin que herdr lo diga)
LEER_VISTO = 3.0                   # s: la del agente que tienes abierto en la página (un diálogo no siempre mueve a herdr)
RECIBIDO_S = 30.0                  # tecleado y sin reacción por esto: se da por terminado
RESPONDIO_S = 3.0                  # antes de esto, que cambie su conversación es el renglón del socio
TRANS_MAX = 12
IDEM_S = 600.0                     # cuánto se recuerda un cid
ACTIVOS = ("enviando", "recibido", "trabajando", "cambiando")

_cond = threading.Condition()
_E = {"v": 0, "v_lista": 0, "fotos": {}, "hilo": None, "pedido": 0.0, "marcas": {}, "lista": ()}
_DESPIERTA = threading.Event()
_ENVIOS = {}                       # agente → {"id", "estado", "t"}
_IDEM = {}                         # (agente, cid) → (hora, respuesta | None mientras se procesa)
_IDEM_LOCK = threading.Lock()
_CACHE = {}                        # clave → (firma, valor)


def _LW():
    import localhost_web
    return localhost_web


# ── cachés invalidadas por cambio (firma = inodo, mtime y tamaño de los archivos de los que sale) ──
def _stat(ruta):
    try:
        s = os.stat(ruta)
        return (s.st_ino, s.st_mtime_ns, s.st_size)
    except OSError:
        return None


def _por_firma(clave, rutas, fn):
    """fn() mientras ninguno de `rutas` cambie."""
    f = tuple(_stat(r) for r in rutas)
    c = _CACHE.get(clave)
    if c and c[0] == f:
        return c[1]
    v = fn()
    _CACHE[clave] = (f, v)
    return v


def _cerebros():
    import agentsreg
    import brain_resolver
    import dispatch
    rutas = (dispatch.registry_path(), agentsreg.local_path(), brain_resolver.paths_local(),
             os.path.join(dispatch.ROOT, "paths.local.json"))
    return _por_firma("cerebros", rutas, lambda: tuple(_LW()._cerebros()))


def _pestana_nav(agente, brain):
    """(bt, reg) de la conversación de la página: la pestaña cambia casi nunca (se busca de nuevo si
    cambia su carpeta de sesiones) y el panel se relee solo si su registro cambió."""
    import aviso_panel
    import sessions_registry as sr
    LW = _LW()
    import identidad
    soc = _por_firma(("socio", brain), (os.path.join(brain, ".claude", "socio.local"), identidad.ruta()),
                     lambda: sr.socio(brain))
    if not soc:
        return None, None
    carpeta = os.path.join(brain, "STATE", "sessions", soc)
    bt = _por_firma(("bt", agente, brain), (carpeta,),
                    lambda: next((t for t in LW._pestanas_web(brain, soc) if t.get("slug") == LW.NAVEGADOR), None))
    if not bt:
        return None, None
    clave = "%s--%s" % (agente, LW._wid_de(bt))
    return bt, _por_firma(("reg", clave), (aviso_panel.ruta_panel(clave),), lambda: aviso_panel.panel_de(clave))


def _ejecuciones(agente, brain):
    """Las de la conversación de la página. Se releen si cambió algo en su carpeta (un nombre, un
    inodo, un tamaño): pasos.guardar reemplaza el archivo entero."""
    import pasos
    LW = _LW()
    d = pasos.carpeta(brain)
    try:
        nombres = sorted((n for n in os.listdir(d) if n.endswith(".json")), reverse=True)[:20]
    except OSError:
        nombres = []
    firma = tuple((n, _stat(os.path.join(d, n))) for n in nombres)
    c = _CACHE.get(("ejec", agente))
    if c and c[0] == firma:
        return c[1]
    lista = [e for e in ((LW.datos_ejecuciones(agente) or {}).get("ejecuciones") or []) if e.get("pestana") == LW.NAVEGADOR]
    _CACHE[("ejec", agente)] = (firma, lista)
    return lista


def _firma_conv(brain, motor_vivo, st):
    """Cambia cuando cambia lo que /api/conversacion enseñaría: su historial, el transcript de sus
    motores o (motor sin transcript) lo que se ve en su pantalla. H3: también Claude Code o Codex mientras su
    transcript no se encuentra (se leen de su pantalla): su respuesta se veía hasta el sondeo de respaldo, ~30 s."""
    import sessions_registry as sr
    LW = _LW()
    import identidad
    slot = _por_firma(("slot", brain), (sr.local_store_path(),), lambda: LW._slot_navegador(brain))
    hist = _por_firma(("hist", brain), (os.path.join(brain, ".claude", "socio.local"), identidad.ruta()),
                      lambda: LW._eventos_path(brain))
    partes, con_transcript = [_stat(hist)], set()
    for m in LW._CONV_MOTORES:
        r = LW._transcripcion(m, slot.get(m))
        partes.append(_stat(r) if r else None)
        if r:
            con_transcript.add(m)
    if motor_vivo and motor_vivo not in con_transcript:
        partes.append((st or {}).get("firma"))
    return "%x" % (hash(tuple(partes)) & 0xFFFFFFFFFFFF)


def _firma_pend(brain):
    """Cambia si cambian sus pendientes: su STATE/PENDIENTES.md, su inbox o la memoria de su conversación (F15: un
    pendiente nuevo no aparecía sin reabrir el panel). Solo stat."""
    import identidad
    LW = _LW()

    def ficha():
        import memoria
        try:
            return memoria.ficha_path(brain, LW.NAVEGADOR_NOMBRE)
        except Exception:
            return ""
    f = _por_firma(("ficha", brain), (os.path.join(brain, ".claude", "socio.local"), identidad.ruta()), ficha)
    partes = (_stat(os.path.join(brain, "STATE", "PENDIENTES.md")), _stat(os.path.join(brain, "STATE", "inbox")),
              _stat(f) if f else None)
    return "%x" % (hash(partes) & 0xFFFFFFFFFFFF)


# ── el panel en vivo: una lectura de herdr para todos ──
def _paneles(regs):
    """{socket: {pane_id: (status, terminal, título)}} con UNA llamada por servidor de herdr; None en
    ese socket si herdr no contestó (entonces se pregunta panel por panel, como antes)."""
    import aviso_panel
    out = {}
    for sock in {r.get("socket", "") for r in regs}:
        res = aviso_panel._herdr(["pane", "list"], sock)
        if res is None:
            out[sock] = None
            continue
        out[sock] = {p.get("pane_id"): (str(p.get("agent_status") or ""), p.get("terminal_id"),
                                        p.get("terminal_title_stripped") or p.get("terminal_title"))
                     for p in (res.get("panes") or []) if isinstance(p, dict)}
    return out


def _vivo_de(agente, reg, paneles, previo, ahora):
    """Lo que el panel dice ahora (mismo formato que /api/pantalla?estado=1). Solo se lee su
    pantalla si herdr ve un cambio o toca revisarla."""
    LW = _LW()
    if not reg:
        return {"viva": False}
    lista = paneles.get(reg.get("socket", ""))
    motor = LW._recorta(reg.get("motor"), 30)
    sig = None
    if lista is not None:
        sig = lista.get(reg.get("panel"))
        if sig is None:
            return {"viva": False}                       # su panel ya no está
        if reg.get("terminal") and sig[1] != reg.get("terminal"):
            return {"viva": False}
    m = _E["marcas"].get(agente) or {}
    ocupado = (previo or {}).get("estado") in ACTIVOS + ("esperandote",) or (sig and sig[0] in ("", "unknown", "working"))
    cada = LEER_ACTIVO if ocupado else LEER_VISTO if agente == _E.get("activo") else LEER_CALMA
    if (m.get("reg") == reg.get("panel") and sig is not None and m.get("sig") == sig
            and ahora - m.get("t", 0) < cada):
        return m["vivo"]
    st = LW._estado_rapido(reg, fresco=True)
    if not st.get("ok"):
        # su panel sigue ahí pero su motor ya no corre (salió a la shell: F14): «cerrado», no «dormido»
        vivo = {"viva": False, "cerrado": sig is not None, "motor": motor if sig is not None else ""}
    else:
        vis = LW._leer_panel(reg, 60, "visible") or ""
        p = LW._pregunta_viva(reg, vis)
        vivo = {"viva": True, "motor": LW._recorta(reg.get("motor"), 30), "status": LW._recorta(st.get("status"), 20),
                "trabajando": LW._trabajando(st, bool(p)) and not p, "firma": st.get("firma")}
        if p:
            vivo["pregunta"] = p
        sub, uso = LW.subagentes_de(vis), LW.uso_de(vis)
        if sub:
            vivo["subagentes"] = sub
        if uso:
            vivo["uso"] = uso
        import ajustes_motor
        vivo["vistos"] = ajustes_motor.leer(reg.get("motor"), vis)     # su modelo y esfuerzo, si su pie los enseña
        vivo["panel"] = reg.get("panel")
        if not vivo["trabajando"] and not p:
            from pantalla_motor import error_de
            e = error_de(vis)
            if e:                                         # N5: de ESTE motor, no del de su conversación
                vivo["error"] = dict(e, motor=vivo["motor"])
    _E["marcas"][agente] = {"reg": reg.get("panel"), "sig": sig, "t": ahora, "vivo": vivo}
    return vivo


# ── la máquina de estados ──
def transicion(previo, x, ahora):
    """El estado que sigue. `previo` = (estado, desde); `x` = lo que se ve ahora: viva, trabajando,
    pregunta (o una skill que pide), error, cambio en curso, el envío ({estado, t}) y si la
    conversación cambió desde que se tecleó (`respondio`). Pura: la prueban sin servidor."""
    est = previo[0]
    envio = x.get("envio") or {}
    if x.get("cambiando"):
        return "cambiando"
    if not x.get("viva"):
        return "cerrado" if x.get("cerrado") else "no_salio" if envio.get("estado") in NO_SALIO \
            else "enviando" if envio.get("estado") in ("enviando", "en_cola") else "dormido"
    if x.get("pregunta"):
        return "esperandote"
    if envio.get("estado") in NO_SALIO:
        return "no_salio"
    if x.get("trabajando"):
        return "trabajando"
    if x.get("error"):
        return "error"
    if envio.get("estado") in ("enviando", "en_cola") or x.get("en_cola"):
        return "enviando"
    if envio.get("estado") == "recibido":
        # tecleado y su motor aún no se ve trabajar. Contestó sin que lo viéramos trabajar si su
        # conversación cambió y ya pasaron RESPONDIO_S (antes, el cambio es el renglón del socio)
        listo = (x.get("respondio") and ahora - envio.get("t", ahora) >= RESPONDIO_S) or ahora - envio.get("t", ahora) >= RECIBIDO_S
        return "termino" if listo else "recibido"
    if envio.get("estado") == "quitado" and est == "enviando":
        return "libre"                                  # quitó de la cola lo que esperaba: no «terminó» nada
    if est in ("trabajando", "recibido", "enviando", "termino"):
        return "termino"
    return "libre"


def _vivo_registro(brain, bt, reg, paneles):
    """Arquitectura nueva (F1): con el paquete encendido, lo que el panel dice sale del
    registro de eventos de la pestaña (lo anotan los hooks del motor), sin leer su
    pantalla. De herdr solo se mira si su panel sigue ahí (el motor muerto sin
    «cierre» queda cerrado). None si el paquete está apagado o la pestaña no tiene
    eventos todavía: entonces, lo de siempre."""
    try:
        from arquitectura import registro, sesion
        if not bt or not sesion.activo():
            return None
        est = registro.estado(registro.leer(brain, _LW()._wid_de(bt))[0])
    except Exception:
        return None
    if est["estado"] == "sin_datos":
        return None
    motor = est.get("motor") or ""
    lista = paneles.get((reg or {}).get("socket", "")) if reg else None
    panel_fuera = reg is not None and lista is not None and lista.get(reg.get("panel")) is None
    if est["estado"] == "cerrado" or panel_fuera:
        return {"viva": False, "cerrado": True, "motor": motor, "fuente": "registro"}
    vivo = {"viva": True, "motor": motor, "status": est["estado"], "fuente": "registro",
            "trabajando": est["estado"] in ("pensando", "usando"), "session_id": est["session_id"]}
    if est["estado"] == "usando" and est.get("herramienta"):
        vivo["herramienta"] = est["herramienta"]
    if est["estado"] == "esperando_permiso":       # se contesta en la terminal: sin opciones aquí
        h = est.get("herramienta") or ""
        vivo["pregunta"] = {"texto": "Espera tu permiso en la terminal" + (" para «%s»" % h if h else "") + ".",
                            "opciones": [], "sel": None, "permiso": True}
    if reg:
        vivo["panel"] = reg.get("panel")
    return vivo


def eventos(agente, desde=0):
    """/api/front/eventos: el registro de eventos de la pestaña de la página del agente
    desde el byte `desde`, con el estado que dicen. La página lee esto, no la pantalla."""
    from arquitectura import registro
    brain = next((b for n, b in _cerebros() if n == agente), None) if agente else None
    if not brain:
        return {"eventos": [], "fin": 0, "estado": registro.estado([])}
    bt, _reg = _pestana_nav(agente, brain)
    if not bt:
        return {"eventos": [], "fin": 0, "estado": registro.estado([])}
    wid = _LW()._wid_de(bt)
    try:
        desde = max(0, int(desde or 0))
    except (TypeError, ValueError):
        desde = 0
    evs, fin = registro.leer(brain, wid, desde)
    return {"eventos": evs, "fin": fin, "estado": registro.estado(registro.leer(brain, wid)[0])}


def _foto(agente, brain, paneles, ahora):
    previa = _E["fotos"].get(agente)
    bt, reg = _pestana_nav(agente, brain)
    vivo = _vivo_registro(brain, bt, reg, paneles) or _vivo_de(agente, reg, paneles, previa, ahora)
    LW = _LW()
    ej = _ejecuciones(agente, brain)
    c = LW.cambio_de(agente, LW.NAVEGADOR)
    if c and c["error"]:
        import i18n
        c = dict(c, error=LW._txt(i18n.lang(), c["error"]))
    envio = _ENVIOS.get(agente)
    conv = _firma_conv(brain, vivo.get("motor") if vivo.get("viva") else "", vivo)
    pide = any(e.get("estado") == "pide" and e.get("pide") and LW._reciente(e.get("actualizado") or e.get("creado"))
               for e in ej)
    respondio = bool(envio and envio.get("estado") == "recibido" and envio.get("conv") and envio["conv"] != conv)
    previo = (previa["estado"], previa["desde"]) if previa else ("dormido", ahora)
    x = dict(vivo, pregunta=vivo.get("pregunta") or pide, envio=envio, respondio=respondio, en_cola=bool(LW.cola_de(agente)),
             cambiando=bool(c and c["paso"] not in ("listo", "error")))
    estado = transicion(previo, x, ahora)
    _anotar_respuesta(agente, brain, reg, estado, previa, ahora)
    if envio and envio.get("estado") == "recibido" and estado in ("trabajando", "termino", "esperandote", "error"):
        _ENVIOS.pop(agente, None)                 # ya reaccionó: el envío quedó atrás
        envio = None
    trans = list(previa["trans"]) if previa else []
    desde = previa["desde"] if previa and previa["estado"] == estado else ahora
    if not previa or previa["estado"] != estado:
        trans = (trans + [[estado, round(ahora, 3)]])[-TRANS_MAX:]
    f = {"estado": estado, "desde": round(desde, 3), "trans": trans, "existe": bool(bt),
         "viva": bool(vivo.get("viva")), "motor": vivo.get("motor") or "", "status": vivo.get("status") or "",
         "trabajando": bool(vivo.get("trabajando")), "pregunta": vivo.get("pregunta"), "uso": vivo.get("uso"),
         "subagentes": vivo.get("subagentes"), "error": vivo.get("error"), "cambio": c,
         "envio": ({"id": envio["id"], "estado": envio["estado"], "t": round(envio["t"], 3), "motivo": envio.get("motivo", "")}
                   if envio else None), "cerrado": bool(vivo.get("cerrado")),
         "conv": conv, "ejecuciones": ej, "cola": LW.cola_de(agente), "pend": _firma_pend(brain),
         "ajustes": _ajustes(LW, agente, vivo)}
    return f


_CIERRES = {}                      # agente → la última vez que se buscó la respuesta a su último mensaje


def _anotar_respuesta(agente, brain, reg, estado, previa, ahora):
    """El historial de la página anota la respuesta del agente al pasar a «terminó» (o «error»): UNA vez por turno
    (localhost_web.cerrar_turno). Con tu último mensaje sin respuesta (un servidor que se reinició a medio turno), se
    vuelve a buscar cada CERRAR_REINTENTO_S mientras está libre. Nunca tumba la foto."""
    LW = _LW()
    try:
        entra = estado in ("termino", "error") and (not previa or previa["estado"] != estado)
        if not entra and estado in ("libre", "termino") and ahora - _CIERRES.get(agente, 0) >= LW.CERRAR_REINTENTO_S:
            _CIERRES[agente] = ahora
            entra = LW.turno_sin_respuesta(brain)
        if entra:
            _CIERRES[agente] = ahora
            LW.cerrar_turno(brain, reg)
    except Exception:
        pass


def _ajustes(LW, agente, vivo):
    """Modelo, esfuerzo y modo de su motor para los botones (localhost_web.ajustes_de): el que corre; cerrada, solo lo
    guardado de cada motor (la página elige el suyo)."""
    try:
        if vivo.get("viva"):
            return LW.ajustes_de(agente, vivo.get("motor") or "", vivo.get("vistos"), vivo.get("panel") or "")
        return {"motor": "", "valores": {}, "guardados": LW.ajustes_guardados(agente)}
    except Exception:
        return None


def tick():
    """Una vuelta: rehace la foto de cada agente y sube la versión de las que cambiaron."""
    ahora = time.time()
    cerebros = _cerebros()
    regs = []
    for agente, brain in cerebros:
        _bt, reg = _pestana_nav(agente, brain)
        if reg:
            regs.append(reg)
    paneles = _paneles(regs) if regs else {}
    fotos = {}
    for agente, brain in cerebros:
        try:
            fotos[agente] = _foto(agente, brain, paneles, ahora)
        except Exception:
            if agente in _E["fotos"]:
                fotos[agente] = dict(_E["fotos"][agente])
    with _cond:
        nueva, cambio = _E["v"] + 1, False
        lista = tuple(sorted(fotos))
        if lista != _E["lista"]:                  # entró o salió un agente: todos reciben la lista entera
            _E["v_lista"], _E["lista"], cambio = nueva, lista, True
        for agente, f in fotos.items():
            vieja = _E["fotos"].get(agente)
            if vieja and {k: v for k, v in vieja.items() if k != "v"} == f:
                continue
            f["v"], _E["fotos"][agente], cambio = nueva, f, True
        for agente in [a for a in _E["fotos"] if a not in fotos]:
            del _E["fotos"][agente]
        if cambio:
            _E["v"] = nueva
            _cond.notify_all()
        _E["visto"] = ahora
    return _E["v"]


# ── ocupado: lo que interrumpe al agente se bloquea en el SERVIDOR (pedido del socio, ronda 2) ──
# Trabajando, cambiando de motor o esperando que su motor acepte: cambiar de motor, empezar otra skill, renombrar la
# que corre (y §6) responden 409 con su llave amable. Escribir no (va a la cola), ni Detener, el panel, el tono o
# sus archivos. «Detener y cambiar» espera a que de verdad se detenga; si no se detiene, «Cerrar y cambiar» solo
# pasa DETENER_GRACIA_S después de pedirle que se detenga.
OCUPADO = {"trabajando": "localhost.err.ocupado", "cambiando": "localhost.err.ocupado_cambiando",
           "enviando": "localhost.err.ocupado_esperando", "recibido": "localhost.err.ocupado_esperando"}
DETENER_GRACIA_S = 15.0
_DETENER = {}


def _al_dia():
    """La decisión sale del estado del servidor: si su foto no es de hace un momento, se rehace ahora."""
    try:
        if time.time() - _E.get("visto", 0) > 2 * TICK_ACTIVO + 0.5:
            tick()
    except Exception:
        pass


def _nombre(agente):
    try:
        import localhost_front as F
        p = F._prefs_de(F.leer_prefs(), agente)
        return p.get("nombre") or next((a.get("display") for a in F._snapshot() if a.get("id") == agente), "") \
            or agente.capitalize()
    except Exception:
        return agente


def ocupado(agente):
    """None, o el 409 ({ok: false, error, status, datos, ocupado}) si está trabajando, cambiando de motor o
    esperando que su motor acepte."""
    _al_dia()
    est = (_E["fotos"].get(agente) or {}).get("estado")
    return ({"ok": False, "error": OCUPADO[est], "status": 409, "datos": {"n": _nombre(agente)}, "ocupado": est}
            if est in OCUPADO else None)


def skill_en_curso(agente):
    """El nombre de la skill que corre en su conversación ("" si ninguna): una por agente."""
    import datetime as _dt
    _al_dia()
    try:
        import localhost_front as F
        detenidas = set(F._prefs_de(F.leer_prefs(), agente).get("detenidas") or [])
    except Exception:
        detenidas = set()
    for e in (_E["fotos"].get(agente) or {}).get("ejecuciones") or []:
        if e.get("estado") == "listo" or e.get("id") in detenidas:
            continue
        try:
            edad = (_dt.datetime.now() - _dt.datetime.fromisoformat(str(e.get("actualizado") or e.get("creado"))[:19])).total_seconds()
        except ValueError:
            edad = 0
        if edad < (600 if e.get("estado") == "arrancando" else 6 * 3600):    # la que nunca arrancó no bloquea
            return e.get("skill") or ""
    return ""


def ocupado_skill(agente, skill=None):
    """El 409 si ya corre una skill (`skill`: solo si es esa)."""
    s = skill_en_curso(agente)
    if s and (skill is None or s == skill):
        return {"ok": False, "error": "localhost.err.ocupado_skill", "status": 409, "datos": {"n": _nombre(agente), "s": s},
                "ocupado": "skill"}
    return None


def detener_pedido(agente, hace=0.0):
    """Le pidieron que se detenga (Detener, o el primer paso de «Detener y cambiar»)."""
    _DETENER[agente] = time.time() - hace


def detuvo_hace(agente):
    """Hace cuánto se le pidió que se detenga EN LO QUE HACE AHORA (-1 si no): el pedido vale para el turno en curso
    (su racha enviando → recibido → trabajando); uno de antes de que empezara, o con el agente ya libre, no cuenta."""
    t, f = _DETENER.get(agente), _E["fotos"].get(agente) or {}
    if not t or f.get("estado") not in ACTIVOS:
        _DETENER.pop(agente, None)
        return -1.0
    empezo = f.get("desde", 0)
    for est, cuando in reversed(f.get("trans") or []):
        if est not in ACTIVOS:
            break
        empezo = cuando
    return time.time() - t if t >= empezo else -1.0


def _activo():
    return any(f["estado"] in ACTIVOS for f in _E["fotos"].values()) or bool(_ENVIOS)


def _bucle():
    while True:
        with _cond:
            if time.time() - _E["pedido"] >= VIDA:
                _E["hilo"] = None
                return
        t0 = time.time()
        try:
            tick()
        except Exception:
            pass
        _DESPIERTA.wait(max(0.05, (TICK_ACTIVO if _activo() else TICK_CALMA) - (time.time() - t0)))
        _DESPIERTA.clear()


def _escuchando():
    """Una página escucha: el hilo corre (lo arranca si estaba dormido, con una primera vuelta)."""
    with _cond:
        _E["pedido"] = time.time()
        if _E["hilo"] is not None:
            return
        _E["hilo"] = threading.Thread(target=_bucle, daemon=True, name="front-vivo")
    if not _E["fotos"]:
        try:
            tick()
        except Exception:
            pass
    _E["hilo"].start()


def cambios(v=0, epoca="", espera=0.0, activo=""):
    """La ruta /api/front/vivo (ver el contrato arriba). `activo`: el agente que la página tiene abierto (su pantalla
    se relee más seguido)."""
    try:
        v = int(v or 0)
        espera = max(0.0, min(ESPERA_MAX, float(espera or 0)))
    except (TypeError, ValueError):
        return {"ok": False, "error": "localhost.err.formato", "status": 400}
    if activo:
        _E["activo"] = str(activo)[:80]
    try:
        _escuchando()
        fin = time.time() + espera
        with _cond:
            completo = epoca != EPOCA or v <= 0 or v > _E["v"] or v < _E["v_lista"]
            while not completo and _E["v"] <= v and time.time() < fin:
                _cond.wait(fin - time.time())
            fotos = {a: f for a, f in _E["fotos"].items() if completo or f["v"] > v}
            return {"ok": True, "e": EPOCA, "v": _E["v"], "t": round(time.time(), 3), "completo": completo,
                    "agentes": fotos}
    except Exception:
        return {"ok": False, "error": "localhost.err.leer", "status": 500}


# ── envíos: lo que la página mandó, con su id ──
def envio(agente, cid, estado, conv=None, motivo=""):
    """Registra el paso del envío `cid` y despierta al hilo: la página lo ve en la siguiente respuesta, sin esperar
    la vuelta. «enviando» → «recibido»; «en_cola» (con su `motivo`: abriendo, arrancando, trabajando, pregunta,
    caja_ocupada, sin_caja) mientras su caja no está lista; si no salió: «no_se_mando», «sin_eco» o «atorado»;
    «fallo» lo olvida (la página ya recibió el error)."""
    if estado == "fallo":
        if (_ENVIOS.get(agente) or {}).get("id") == cid:
            _ENVIOS.pop(agente, None)
    else:
        f, antes = _E["fotos"].get(agente) or {}, _ENVIOS.get(agente) or {}
        _ENVIOS[agente] = {"id": str(cid or ""), "estado": estado, "t": time.time(), "motivo": motivo,
                           "conv": conv if conv is not None else antes.get("conv") if antes.get("id") == cid else f.get("conv")}
    _DESPIERTA.set()


NO_SALIO = ("no_se_mando", "sin_eco", "atorado", "no_abrio")


def releer(agente):
    """Que la siguiente vuelta lea otra vez su pantalla y despierte al hilo (un botón de modelo o esfuerzo recién
    aplicado: su pie ya cambió y la página no espera a la vuelta de calma)."""
    m = _E["marcas"].get(agente)
    if m:
        m["t"] = 0
    _DESPIERTA.set()


def idem_tomar(agente, cid):
    """(¿es nuevo?, respuesta guardada). Un `cid` repetido no se procesa otra vez: mientras el primero
    corre, el segundo recibe {"ok": True, "repetido": True}; después, la misma respuesta."""
    if not cid:
        return True, None
    ahora = time.time()
    with _IDEM_LOCK:
        for k in [k for k, (t, _r) in _IDEM.items() if ahora - t > IDEM_S]:
            del _IDEM[k]
        hay = _IDEM.get((agente, cid))
        if hay:
            return False, dict(hay[1] or {"ok": True}, repetido=True)
        _IDEM[(agente, cid)] = (ahora, None)
        return True, None


def idem_guardar(agente, cid, respuesta):
    """Lo que se le contestó a `cid`; una respuesta de error lo olvida (reintentar sí debe intentarlo)."""
    if not cid:
        return
    with _IDEM_LOCK:
        if respuesta is None:
            _IDEM.pop((agente, cid), None)
        else:
            _IDEM[(agente, cid)] = (time.time(), respuesta)
