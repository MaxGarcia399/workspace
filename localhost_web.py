#!/usr/bin/env python3
"""WORKSPACE · localhost_web — la página local de Workspace (esqueleto, SOLO LECTURA).

Un servidor stdlib que sirve la página en tu propia máquina:

  · solo escucha en 127.0.0.1, en un puerto libre;
  · la llave es nueva en cada arranque: entra por el link (`/?k=<llave>`), el
    servidor la guarda en una cookie HttpOnly + SameSite=Strict y manda a `/`
    sin la llave en la URL (no queda en historial ni en logs);
  · reusa el guard del dashboard (Host contra DNS-rebinding, Origin en POST) y
    su CSP estricta; nunca emite cabeceras CORS;
  · cada endpoint entrega una LISTA BLANCA de campos (jamás un dict crudo: ni
    rutas del disco, ni notas privadas, ni secretos);
  · lo único que escribe es apagarse (`POST /api/apagar`).

Aún no está enganchada al hub: `serve()` lo arranca a mano. Ver
`web/localhost/` para la página (hoy con datos de ejemplo).
"""
import hmac
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import webbrowser
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import dashboard
import i18n
# los lectores de la pantalla de cada motor (preguntas, subagentes, uso, conversación) viven
# en pantalla_motor: también los usa aviso_panel para no teclear sobre un menú
from pantalla_motor import (MAX_TURNOS, _ANSI_RE, _de_pantalla, _sin_arranques,  # noqa: F401
                            _sin_pregunta, pregunta_de, seleccion_por_color, subagentes_de, uso_de)
# el texto hacia la página (recortar, ocultar llaves): no lee pantalla (F3)
from texto_pagina import _limpio, _recorta, _sin_secretos  # noqa: E402,F401

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web", "localhost")
FRONT = os.path.join(HERE, "web", "front")     # el front nuevo (un agente = una conversación); el de antes queda en /clasico

COOKIE = "ws_llave"
MAX_CUERPO = 4000          # tope de un mensaje de sala hacia la página
MAX_MENSAJES = 50          # por sala
MAX_DECISIONES = 100
MAX_PARTICIPANTES = 8      # a los que se les consulta su estado, por sala
MAX_PESTANAS = 30          # de memoria, por agente
MAX_VIGENTE = 20
MAX_ENVIO = 4000           # caracteres de un mensaje del socio
MAX_POST = 32 * 1024       # bytes del cuerpo de cualquier POST
MAX_POST_ARCHIVO = 1024 * 1024   # guardar un .md del cerebro desde el front nuevo (el texto mismo topa en 256 KB)

# Solo estos archivos se sirven: nada de rutas armadas con la URL.
_ESTATICOS = {
    "/": (FRONT, "index.html", "text/html; charset=utf-8"),
    "/index.html": (FRONT, "index.html", "text/html; charset=utf-8"),
    "/clasico": (WEB, "index.html", "text/html; charset=utf-8"),
    "/nuevo": (FRONT, "index.html", "text/html; charset=utf-8"),
    "/ws-pixel.woff2": (WEB, "ws-pixel.woff2", "font/woff2"),
    "/temas.js": (os.path.join(FRONT, "src"), "15_temas.js", "text/javascript; charset=utf-8"),
}
for _guia in ("primer-arranque", "hub", "motores", "actualizaciones", "privacidad"):
    _ESTATICOS[f"/manual/es/{_guia}.md"] = (
        os.path.join(HERE, "manual", "es"), _guia + ".md", "text/plain; charset=utf-8")


def _idiomas():
    return {c for c, _ in i18n.available()}


#: Idiomas en que ya está el front nuevo. En los demás (AG3-a) «/» es la página NUEVA en español, con un aviso de una
#: línea en tu idioma (la de antes ya no se sirve: I20/I21).
IDIOMAS_FRONT = ("es",)


def _front_en_mi_idioma():
    try:
        return i18n.lang() in IDIOMAS_FRONT
    except Exception:
        return True


def _clasico_a_la_vista():
    """¿Se sirve todavía la página de antes en /clasico? Solo en una copia de desarrollo (puertas.dev), para
    comparar; en la de un cliente, /clasico lleva a la nueva."""
    try:
        import puertas
        return puertas.dev()
    except Exception:
        return False


def _con_aviso_idioma(html, texto):
    """La página nueva con su aviso de una línea (AG3-a: todavía está solo en español), con la nota de la página
    (20_base.js `nota`) al cargar. `texto` va como JSON: nada de HTML del catálogo."""
    if not texto or not isinstance(html, bytes):
        return html
    js = ("<script>window.addEventListener('load',function(){try{nota(%s,false,9000)}catch(e){}});</script>"
          % json.dumps(str(texto)))
    i = html.rfind(b"</body>")
    return html[:i] + js.encode("utf-8") + html[i:] if i >= 0 else html + js.encode("utf-8")


def _catalogo(idioma):
    """Catálogo completo de `idioma`, con el español de base para lo que falte."""
    cat = dict(i18n._load_catalog("es"))
    if idioma != "es":
        cat.update(i18n._load_catalog(idioma))
    return cat


def _txt(idioma, clave, **kw):
    s = _catalogo(idioma).get(clave, clave)
    try:
        return s.format(**kw) if kw else s
    except Exception:
        return s


def _campos(d, permitidos):
    return {k: d.get(k) for k in permitidos if k in d}


# ── datos (cada uno devuelve SOLO lo que la página necesita) ─────────────────
def datos_estado():
    return {"ok": True, "solo_lectura": True}


def datos_agentes():
    import agent_state
    snap = agent_state.snapshot()
    out = [_campos(a, ("id", "display", "color", "tagline", "engine", "status", "hidden"))
           for a in snap.agents if not a.get("hidden")]
    return {"agentes": out}


ESTADOS = ("escuchando", "trabajando", "cerrada", "desconocido")


def _estado(salas, sala, key):
    try:
        e = salas.estado_participante(sala, key).get("estado")
    except Exception:
        e = None
    return e if e in ESTADOS else "desconocido"


def _de_otro_socio(salas, sala, cache):
    """Misma regla que el hub (conversaciones_tui._del_socio): en un cerebro
    compartido la sala de otro socio no se muestra ni se escribe."""
    if not sala.get("dueno"):
        return False
    h = sala.get("hogar")
    if h not in cache:
        cache[h] = salas._socio_de(h)
    return bool(cache[h]) and cache[h] != sala["dueno"]


def _destinos(sala):
    """Los destinos de la sala: sus participantes y los invitados que todavía no
    entraron («?agente»; el hub les escribe por el nombre del agente)."""
    out = [_campos(p, ("key", "agente", "pestana", "motor"))
           for p in (sala.get("participantes") or {}).values()]
    for a in sala.get("invitados") or []:
        if not any(p.get("agente") == a for p in out):
            out.append({"key": "?" + a, "agente": a, "invitado": True})
    return out[:MAX_PARTICIPANTES]


def _destino_defecto(salas, sala, claves):
    try:
        d = salas.mencion_defecto(sala)
    except Exception:
        return ""
    return d if d in claves else ("?" + d if "?" + d in claves else "")


def datos_salas():
    import salas
    out, cache = [], {}
    for s in salas.todas(archivadas=False):
        if _de_otro_socio(salas, s, cache):
            continue
        vivos = not s.get("cerrada")
        partes = [dict(p, pestana=_limpio(p["pestana"], 120) if p.get("pestana") else "",
                       estado=_estado(salas, s, p.get("key")) if vivos else "sala_cerrada")
                  for p in _destinos(s)]
        out.append({
            "id": s.get("id"), "titulo": _limpio(s.get("titulo"), 200),
            "objetivo": _limpio(s.get("objetivo"), 500),
            "cerrada": bool(s.get("cerrada")), "pausada": bool(s.get("pausada")),
            "turno_max": s.get("turno_max"),
            "destino": _destino_defecto(salas, s, {p["key"] for p in partes}),
            "participantes": partes,
            "mensajes": [
                dict(_campos(m, ("id", "de", "tipo", "ts")),
                     socio=salas.es_socio(m.get("de")), agente=salas.agente_de(m.get("de")),
                     resumen=_limpio(m.get("resumen"), 300),
                     cuerpo=_limpio(m.get("cuerpo"), MAX_CUERPO))
                for m in (s.get("mensajes") or [])[-MAX_MENSAJES:]],
        })
    return {"salas": out}


def datos_memoria():
    # solo el resumen de cada pestaña y lo abierto (decisiones y pendientes):
    # las notas sueltas, las rutas y la maleta no salen del disco
    import memoria
    import messages
    import session_continuity as sc
    import sessions_registry as reg
    out = []
    for agente, brain in sorted(messages.registered_brains().items()):
        try:
            tabs = sorted(reg._pestanas(brain), key=lambda b: b.get("actualizada") or "",
                          reverse=True)[:MAX_PESTANAS]
        except Exception:
            continue
        for bt in tabs:
            nombre = bt.get("name") or ""
            try:
                ficha = memoria.Ficha(memoria._leer_vista(memoria.ficha_path(brain, nombre)))
                cp = sc.read_checkpoint(brain, nombre)
                items = memoria.vigente(ficha)
                titulo = memoria._titulo(ficha, nombre)
            except Exception:
                continue
            out.append({
                "agente": agente, "titulo": _limpio(titulo, 120),
                "actualizada": _recorta(bt.get("actualizada"), 20),
                "resumen": ({k: _limpio(cp.get(k), 600) for k in sc.FIELDS} if cp else None),
                "revision": cp.get("revision") if cp else None,
                "vigente": [{"id": _recorta(v.get("id"), 12), "tipo": _recorta(v.get("tipo"), 12),
                             "fecha": _recorta(v.get("fecha"), 10),
                             "texto": _limpio(v.get("texto"), 400)} for v in items[:MAX_VIGENTE]],
            })
    return {"pestanas": out}


def datos_calendario():
    import personal
    # sin `notes`: son texto libre del socio
    return {"eventos": [_campos(e, ("id", "date", "time", "title", "cat", "done", "prio"))
                        for e in personal.events()]}


def datos_decisores():
    from decisions import decisores_activos
    if not decisores_activos():
        return {"en_pausa": True}
    import decisions
    try:
        import decision_visible
    except Exception:
        decision_visible = None
    filas = []
    for e in decisions.history(limit=MAX_DECISIONES, ok_only=True):
        paso = ("", "")
        try:
            paso = decision_visible.paso(e)
        except Exception:
            pass
        p = e.get("p")
        filas.append({
            "id": e.get("id"), "ts": _recorta(e.get("ts"), 20),
            "punto": e.get("point") if e.get("point") in decisions.POINT_IDS else "",
            "uso": decisions.point_label(e.get("point")),
            "decisor": _limpio(decisions.decider_label(e.get("decider")), 40),
            "pregunta": _limpio(e.get("q"), 160), "eligio": _limpio(e.get("choice"), 80),
            "seguridad": round(p * 100) if isinstance(p, (int, float)) else None,
            "acerto": e.get("truth") if e.get("truth") in (True, False) else None,
            "paso": _recorta(paso[0], 10), "paso_texto": _limpio(paso[1], 60),
        })
    return {"decisiones": filas,
            "usos": [{"punto": pid, "uso": decisions.point_label(pid), "total": decisions.point_total(pid)}
                     for pid in decisions.POINT_IDS]}


MAX_PESTANAS_TODAS = 400   # por agente, en la lista completa
MAX_SKILLS = 300           # por agente
MAX_CONEXIONES = 200
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")


def _cerebros():
    import messages
    return sorted(messages.registered_brains().items())


def _cerebro(agente):
    """El cerebro de `agente` sin resolver el de todos en cada lectura (`registered_brains()` abre ~4 archivos por
    agente, y la conversación se pide ~1 vez por segundo mientras trabaja): la lista con caché por firma de front_vivo.
    Si no está ahí o su carpeta ya no existe (lo acaban de crear, se movió), se resuelve de nuevo."""
    b = dict(_vivo()._cerebros()).get(agente)
    return b if b and os.path.isdir(b) else dict(_cerebros()).get(agente)


# ── la conversación de la página: UNA por agente, fija, fuera de los menús del hub y de la terminal ──
NAVEGADOR = "navegador"                 # su slug (y su `canal:`)
NAVEGADOR_NOMBRE = "Navegador"


def _pestanas_web(brain, soc):
    """Las pestañas que ve la página: todas (también archivadas) y la del navegador."""
    import agent_brand
    return agent_brand.pestanas(brain, soc, True, navegador=True) if soc else []


def _sembrar_navegador(agente):
    """La conversación de la página se crea sola la primera vez: su .md con `canal: navegador` y un id
    propio (el de Claude Code), como una pestaña nueva. True si ya quedó."""
    import uuid
    import agent_brand
    import sessions_registry
    brain = dict(_cerebros()).get(agente)
    return bool(brain) and sessions_registry._seed_md(brain, NAVEGADOR_NOMBRE, claude_wid=str(uuid.uuid4()),
                                                      canal=agent_brand.CANAL_NAVEGADOR)


# ── modo escritorio (D1-a): la conversación del monito de escritorio, aparte de la de la página ──
ESCRITORIO = "escritorio"               # su slug (y su `canal:`)
ESCRITORIO_NOMBRE = "Escritorio"


def _pestanas_escritorio(brain, soc):
    """Las pestañas donde se busca la del escritorio (la lista de la página no la trae)."""
    import agent_brand
    return agent_brand.pestanas(brain, soc, True, escritorio=True) if soc else []


def _sembrar_escritorio(agente):
    """La conversación del monito de escritorio se crea sola la primera vez, como la de la página: su .md con
    `canal: escritorio` y un id propio (el de Claude Code). True si ya quedó."""
    import uuid
    import agent_brand
    import sessions_registry
    brain = dict(_cerebros()).get(agente)
    return bool(brain) and sessions_registry._seed_md(brain, ESCRITORIO_NOMBRE, claude_wid=str(uuid.uuid4()),
                                                      canal=agent_brand.CANAL_ESCRITORIO)


def _motores_de_agentes():
    try:
        import agent_state
        return {a.get("id"): a.get("engine") or "" for a in agent_state.snapshot().agents}
    except Exception:
        return {}


def datos_pestanas():
    """TODAS las pestañas de cada agente (no solo las recientes), sin rutas: el
    nombre, cuándo se usó y si está archivada. Lo de adentro sale por /api/pestana."""
    import agent_brand
    import sessions_registry as reg
    motores, out = _motores_de_agentes(), []
    # «abierta» = su panel registrado AQUÍ y vivo de verdad (estado_panel: el panel
    # existe, es la misma terminal y ahí corre su motor). Un registro viejo de una
    # pestaña que ya se cerró no cuenta: la página no debe prometer que se le puede escribir.
    abiertas = {}                      # «agente--wid» → motor que corre en su panel
    try:
        import aviso_panel
        d = os.path.join(aviso_panel._estado(), "paneles")
        for n in os.listdir(d):
            if n.endswith(".json"):
                rp = aviso_panel._leer(os.path.join(d, n))
                if isinstance(rp, dict) and rp.get("panel") and _estado_rapido(rp).get("ok"):
                    abiertas[n[:-5]] = str(rp.get("motor") or "")
    except Exception:
        pass
    for agente, brain in _cerebros():
        try:
            soc = reg.socio(brain)
            tabs = _pestanas_web(brain, soc)
        except Exception:
            continue
        try:
            en_ventana = reg.abiertas_en_ventanas(brain)
        except Exception:
            en_ventana = set()
        tabs = sorted(tabs, key=lambda b: b.get("actualizada") or "", reverse=True)[:MAX_PESTANAS_TODAS]
        for bt in tabs:
            slug = bt.get("slug") or ""
            if not _SLUG_RE.match(slug):
                continue
            out.append({"agente": agente, "slug": slug, "nombre": _limpio(bt.get("name"), 120),
                        "actualizada": _recorta(bt.get("actualizada"), 20),
                        "usada": _recorta(bt.get("usada"), 20),
                        "archivada": bool(agent_brand.es_archivada(bt.get("estado"))),
                        "motor": _recorta(abiertas.get("%s--%s" % (agente, _wid_de(bt))) or motores.get(agente), 30),
                        "abierta": ("%s--%s" % (agente, _wid_de(bt))) in abiertas,
                        "en_ventana": slug in en_ventana})
    return {"pestanas": out}


def _reciente(iso, horas=12):
    import datetime as _dt
    try:
        return (_dt.datetime.now() - _dt.datetime.fromisoformat(str(iso)[:19])).total_seconds() < horas * 3600
    except Exception:
        return False


def datos_ahora():
    """Para Estado: cada sesión abierta aquí (¿trabaja?, ¿te pregunta algo en su terminal?, su uso) y las
    skills que te están pidiendo algo. Solo lo que se ve; nada de rutas ni pantallas."""
    vivas = []
    for t in (datos_pestanas() or {}).get("pestanas", []):
        if not t.get("abierta"):
            continue
        try:
            bt, reg = _pestana_y_panel(t["agente"], t["slug"])
            if not reg:
                continue
            st = _estado_rapido(reg)
            if not st.get("ok"):
                continue
            vis = _leer_panel(reg, 60, "visible") or ""
            p = pregunta_de(vis)                   # aunque herdr no la dé por quieta: el menú manda
            trab = _trabajando(st, bool(p))
            from pantalla_motor import error_de
            err = None if (trab or p) else error_de(vis)
            vivas.append({"agente": t["agente"], "slug": t["slug"], "nombre": t["nombre"], "motor": t.get("motor") or "",
                          "trabajando": trab, "pregunta": (p or {}).get("texto") or "",
                          "uso": uso_de(vis), "error": err})
        except Exception:
            continue
    piden = []
    for agente, _brain in _cerebros():
        try:
            ej = (datos_ejecuciones(agente) or {}).get("ejecuciones", [])
        except Exception:
            continue
        for e in ej:
            if e.get("estado") == "pide" and e.get("pide") and _reciente(e.get("actualizado") or e.get("creado")):
                piden.append({"agente": agente, "skill": e.get("skill"), "pestana": e.get("pestana"),
                              "texto": _limpio((e.get("pide") or {}).get("texto"), 240), "id": e.get("id")})
    return {"vivas": vivas[:40], "piden": piden[:20]}


def datos_pestana(agente, slug):
    """Una pestaña: su resumen y lo abierto (mismo recorte que /api/memoria). Las
    notas sueltas, las rutas y la maleta no salen del disco. None si no existe."""
    import agent_brand
    import memoria
    import session_continuity as sc
    import sessions_registry as reg
    brain = dict(_cerebros()).get(agente)
    if not brain:
        return None
    soc = reg.socio(brain)
    bt = next((t for t in _pestanas_web(brain, soc)
               if t.get("slug") == slug), None)
    if bt is None:
        return None
    nombre = bt.get("name") or ""
    ficha = memoria.Ficha(memoria._leer_vista(memoria.ficha_path(brain, nombre)))
    cp = sc.read_checkpoint(brain, nombre)
    return {
        "agente": agente, "slug": slug, "nombre": _limpio(nombre, 120),
        "titulo": _limpio(memoria._titulo(ficha, nombre), 120),
        "actualizada": _recorta(bt.get("actualizada"), 20),
        "archivada": bool(agent_brand.es_archivada(bt.get("estado"))),
        "motor": _recorta(_motores_de_agentes().get(agente), 30),
        "resumen": ({k: _limpio(cp.get(k), 600) for k in sc.FIELDS} if cp else None),
        "revision": cp.get("revision") if cp else None,
        "vigente": [{"id": _recorta(v.get("id"), 12), "tipo": _recorta(v.get("tipo"), 12),
                     "fecha": _recorta(v.get("fecha"), 10), "texto": _limpio(v.get("texto"), 400)}
                    for v in memoria.vigente(ficha)[:MAX_VIGENTE]],
    }


MAX_PANTALLA = 160         # renglones de la terminal de la pestaña
MAX_ESCRIBIR = 4000


_WID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _wid_de(bt):
    """El id con que se abre y se registra el panel de la pestaña. Las pestañas viejas
    sin id (o con espacios, «DEV DASHBOARD») no podían abrirse desde el navegador
    («no guardó su sesión»): usan su slug, que es estable y válido."""
    w = str((bt or {}).get("workspace") or "").strip()
    return w if _WID_RE.match(w) else str((bt or {}).get("slug") or "")


def _pestana_y_panel(agente, slug):
    """(bt, reg): la pestaña y su panel de herdr registrado EN ESTA máquina
    (aviso_panel: `<agente>--<wid>`). reg None si la pestaña no está abierta aquí."""
    import aviso_panel
    import sessions_registry as reg_
    brain = _cerebro(agente)
    if not brain:
        return None, None
    soc = reg_.socio(brain)
    bt = next((t for t in _pestanas_web(brain, soc)
               if t.get("slug") == slug), None)
    if bt is None:
        return None, None
    wid = _wid_de(bt)
    return bt, (aviso_panel.panel_de("%s--%s" % (agente, wid)) if wid else None)


_ESPERA_STATUS = ("blocked", "waiting", "input")   # herdr: detenido en la terminal, esperándote


def _trabajando(st, menu=False):
    """¿Trabaja? No si está quieto, ni si te espera (un menú en pantalla, o herdr lo ve
    detenido en su terminal). El estado ya trae lo que se ve (aviso_panel._con_pantalla)."""
    return not st.get("quieto") and not (menu or st.get("menu")) and str(st.get("status")) not in _ESPERA_STATUS


def _pregunta_viva(reg, vis):
    """La pregunta de la pantalla para la página. Si su menú marca la opción solo con color
    (OpenCode), se busca en la pantalla con colores; si ni así se ve, `sel` queda None."""
    p = pregunta_de(vis)
    if not p:
        return None
    p.pop("_corte", None)
    if p.get("sel") is None:
        try:
            p["sel"] = seleccion_por_color(_leer_ansi(reg), p)
        except Exception:
            p["sel"] = None
    return p


def datos_pantalla(agente, slug, ansi=False, solo_estado=False):
    """Lo que se ve en la terminal de la pestaña, y si se le puede escribir.
    None si la pestaña no existe."""
    import aviso_panel
    bt, reg = _pestana_y_panel(agente, slug)
    if bt is None:
        return None
    if not reg:
        return {"viva": False, "motivo": "no_abierta"}
    st = _estado_rapido(reg)
    if not st.get("ok"):
        return {"viva": False, "motivo": "panel", "detalle": _recorta(st.get("motivo"), 120)}
    base = {"viva": True, "trabajando": _trabajando(st), "status": _recorta(st.get("status"), 20),
            "motor": _recorta(reg.get("motor"), 30)}
    if solo_estado:
        vis = _leer_panel(reg, 60, "visible")
        p = _pregunta_viva(reg, vis)               # diga lo que diga herdr: el menú en pantalla manda
        if p:
            base["pregunta"] = p
            base["trabajando"] = False
        sub = subagentes_de(vis)
        if sub:
            base["subagentes"] = sub
        u = uso_de(vis)
        if u:
            base["uso"] = u
        if not base["trabajando"] and not p:
            from pantalla_motor import error_de
            e = error_de(vis)
            if e:
                base["error"] = e
        return base
    if ansi:
        base["ansi"] = _ansi_seguro(_leer_ansi(reg) or "")[-120000:]
        return base
    texto = aviso_panel.leer(dict(reg), lineas=MAX_PANTALLA)
    import salas
    texto = salas._CONTROL_RE.sub("", (texto or "").replace("\r", ""))
    base["pantalla"] = _sin_secretos(texto)[-60000:]
    return base


def elegir_opcion(agente, slug, n):
    """Contesta la pregunta de la terminal con la opción `n`: flechas desde la marcada y Enter
    (sirve igual en Claude Code, Codex y los demás menús de flechas, también los que no
    numeran sus opciones, como Kiro y Cursor: `n` es su lugar). Nunca un número tecleado.
    Si la marcada solo se ve por color (OpenCode), se busca en la pantalla con colores; si
    no se ve, no se teclea nada: "sin_seleccion". → "ok" | motivo."""
    import aviso_panel
    bt, reg = _pestana_y_panel(agente, slug)
    if bt is None:
        return "no_existe"
    if not reg:
        return "no_abierta"
    p = pregunta_de(_leer_panel(reg, 60, "visible"))
    if not p:
        return "sin_pregunta"
    o = next((o for o in p["opciones"] if o["n"] == n), None)
    if o is None:
        return "opcion"
    if o.get("teclas"):                           # H12: una opción con sus teclas (Enter vacío, Esc), no un menú
        ok = _en_el_panel(reg, lambda: aviso_panel._herdr(["pane", "send-keys", reg["panel"]] + list(o["teclas"]),
                                                           reg.get("socket", ""), json_out=False) is not None)
        return "ok" if ok else "panel"
    sel = p["sel"]
    if sel is None:
        try:
            sel = seleccion_por_color(_leer_ansi(reg), p)
        except Exception:
            sel = None
        if sel is None:
            return "sin_seleccion"                # sin saber dónde está el cursor, las flechas adivinarían
    d = n - sel
    teclas = (["down"] * d if d > 0 else ["up"] * (-d)) + ["enter"]
    ok = _en_el_panel(reg, lambda: aviso_panel._herdr(["pane", "send-keys", reg["panel"]] + teclas,
                                                       reg.get("socket", ""), json_out=False) is not None)
    return "ok" if ok else "panel"


# ── la terminal misma: leer con colores, mandar teclas, reabrir una cerrada ──
# las teclas que la página puede mandar: lo que usa un agente en su terminal; nada de combinaciones raras.
# H6 (17-nov): herdr 0.9.5 rechaza con «unsupported key» c-u, c-a, c-k, c-e, c-w, c-o, c-r, c-t, c-l, home,
# end, pageup, pagedown, delete y btab (probadas una por una), y acepta enter, esc, c-c, ctrl+u, ctrl+a y
# ctrl+k. Las `c-<letra>` de la página van a herdr como `ctrl+<letra>` (tecla_herdr); las que herdr no tiene
# salieron de la lista (antes daban un 409 falso: «ya no está o ahí no corre su motor»).
TECLAS = {"enter", "esc", "backspace", "tab", "up", "down", "left", "right", "space", "c-c", "c-o", "c-r",
          "c-t", "c-l", "c-u", "c-a", "c-e", "c-k", "c-w"}
MAX_TECLAS = 32


def tecla_herdr(k):
    import aviso_panel
    return aviso_panel.tecla_herdr(k)
_ABRIENDO = {}              # (agente, slug) → time: no abrir dos veces la misma en 30 s


_ESTADO_CACHE = {}
ESTADO_TTL = 2.5           # s: dentro de esta ventana no se re-verifica el panel en cada tecla


def _estado_rapido(reg, fresco=False):
    """aviso_panel.estado_panel con un caché corto por panel+terminal. `fresco` lo ignora."""
    import time as _t
    import aviso_panel
    k = (reg.get("panel"), reg.get("terminal"), reg.get("socket"))
    v = _ESTADO_CACHE.get(k)
    if not fresco and v and _t.time() - v[0] < ESTADO_TTL:
        return v[1]
    st = aviso_panel.estado_panel(reg)
    _ESTADO_CACHE[k] = (_t.time(), st)
    if len(_ESTADO_CACHE) > 200:
        _ESTADO_CACHE.clear()
    return st


def _caja_con_texto_de_verdad(reg):
    """¿Lo que hay en su caja está ESCRITO, o es la sugerencia gris del motor? Se vuelve a leer con colores y se quita lo
    atenuado (Claude Code sugiere el siguiente mensaje en gris dentro de su caja). Si no se puede leer con colores,
    se queda como antes: ocupada."""
    from pantalla_motor import caja_de_entrada, sin_tenue
    a = _leer_ansi(reg)
    if a is None:
        return True
    c = caja_de_entrada(sin_tenue(a))
    return bool(c and c.get("texto"))


def _leer_ansi(reg):
    """La pantalla visible del panel CON sus colores (herdr pane read --format ansi)."""
    import aviso_panel
    exe = aviso_panel._exe()
    if not exe:
        return None
    e = aviso_panel.entorno_herdr(reg.get("socket") or "")       # W0: su socket o la sesión del servidor
    try:
        import subprocess
        import arbol_procesos
        r = subprocess.run([exe, "pane", "read", reg["panel"], "--source", "visible", "--format", "ansi"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=aviso_panel.TIMEOUT_S, env=e, stdin=subprocess.DEVNULL,
                           **arbol_procesos.sin_ventana())          # Windows: la página no tiene consola
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def _ansi_seguro(texto):
    """Quita lo que no sea texto o color (SGR) y tapa el renglón que parece llave."""
    import secret_scan
    out = []
    for ln in str(texto or "").replace("\r", "").split("\n"):
        ln = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-ln-~]", "", ln)        # solo queda «…m» (color)
        ln = re.sub(r"\x1b(?!\[)[^\x1b]?", "", ln)
        ln = re.sub(r"[\x00-\x08\x0b-\x1a\x1c-\x1f\x7f]", "", ln)
        plano = _ANSI_RE.sub("", ln)
        try:
            out.append("[renglón oculto: parecía una llave]" if plano and secret_scan.scan_text(plano) else ln)
        except Exception:
            out.append("")
    return "\n".join(out)


def _en_el_panel(reg, fn):
    """Corre `fn` bajo el MISMO candado que los avisos de sala (aviso_panel.escribir)
    y solo si el panel sigue vivo con su motor: nunca se teclea en una shell."""
    import hashlib
    import aviso_panel
    import olock
    clave = hashlib.sha256(str(reg.get("panel")).encode("utf-8")).hexdigest()
    try:
        with olock.file_lock(os.path.join(aviso_panel._estado(), "escritura-panel", clave),
                             timeout=aviso_panel.PANEL_LOCK_S):
            if not _estado_rapido(reg).get("ok"):
                return False
            ok = fn()
            if not ok:
                _ESTADO_CACHE.pop((reg.get("panel"), reg.get("terminal"), reg.get("socket")), None)
            return ok
    except Exception:
        return False


def _motores_listos():
    import motores_logica
    return {d.get('id') for d in motores_logica._rows() if d.get('ready')}


def _en_windows():
    return os.name == "nt"


def _lanzar(agente, wid, nombre, motor="", extra=()):
    """Abre `dispatch <agente> [--engine m] --open <wid> --name <nombre> [extra]`: en una pestaña NUEVA de herdr, sin
    foco (como el menú de sesiones del hub). `extra`: lo guardado para su arranque (ajustes_motor.argumentos, ya
    validado), que dispatch pasa a su motor. → "ok" | "sin_herdr".
    Windows: el hub corre en su propia consola, no en herdr; una pestaña de herdr no se vería (el herdr que deja una
    conexión por SSH corre en otra sesión de Windows, elevado). Ahí se abre en una VENTANA nueva de la terminal
    (_abrir_ventana), salvo que la página haya nacido dentro de herdr (o el entorno lo pida) y herdr la abra."""
    if _en_windows():
        if _herdr_de_esta_pagina() and _lanzar_en_herdr(agente, wid, nombre, motor, extra) == "ok":
            _VENTANAS.pop((agente, wid), None)
            return "ok"
        return _abrir_ventana(agente, wid, nombre, motor, extra)
    return _lanzar_en_herdr(agente, wid, nombre, motor, extra)


def _comando_dispatch(agente, wid, nombre, motor="", extra=(), python=None):
    cmd = [python or sys.executable or "python3", os.path.join(HERE, "dispatch.py"), agente]
    if motor:
        cmd += ["--engine", motor]               # cambia el motor SOLO de esta corrida (como en el hub)
    return cmd + ["--open", wid, "--name", nombre] + list(extra)


#: Windows: una consola NUEVA y visible. Sin CREATE_NO_WINDOW ni DETACHED_PROCESS (no se vería) y sin
#: CREATE_NEW_PROCESS_GROUP (Ctrl+C no le llegaría al motor dentro de esa ventana).
CREATE_NEW_CONSOLE = 0x00000010
#: Lo que corre en esa ventana: su lanzador y, si sale con error, la ventana se queda con el aviso hasta Enter (como
#: el panel de herdr, que deja su shell): si no, se cerraría sin que vieras por qué. Un Ctrl+C es para el motor.
_VENTANA_ESPERA = ("import signal, subprocess, sys\n"
                   "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
                   "r = subprocess.call(sys.argv[2:])\n"
                   "if r:\n"
                   "    try:\n"
                   "        input('\\n' + sys.argv[1])\n"
                   "    except (EOFError, KeyboardInterrupt):\n"
                   "        pass\n"
                   "sys.exit(r)\n")
_VENTANAS = {}              # (agente, wid) → el proceso de la ventana de terminal que abrió la página (Windows)


def _herdr_de_esta_pagina():
    """¿La página nació dentro de herdr (el hub corría en un panel de herdr) o el entorno pide su sesión? Solo así una
    pestaña de herdr se ve en Windows."""
    return any(os.environ.get(k) for k in ("HERDR_PANE_ID", "HERDR_SOCKET_PATH", "HERDR_SESSION"))


def _ventana_viva(agente, wid):
    p = _VENTANAS.get((agente, wid))
    try:
        return p is not None and p.poll() is None
    except Exception:
        return False


def _python_de_consola():
    """El Python con el que se abre la ventana: si la página corre con pythonw.exe (sin consola), su python.exe."""
    exe = sys.executable or "python"
    if os.path.basename(exe).lower() == "pythonw.exe":
        con = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(con):
            return con
    return exe


def _abrir_ventana(agente, wid, nombre, motor="", extra=()):
    """Windows: la conversación en una ventana nueva de la terminal (la de Windows Terminal si es tu terminal por
    defecto), al frente, con su lanzador de siempre. Una sola por conversación: si la que abrió sigue abierta, no
    abre otra. Nada se teclea. → "ok" | "sin_herdr" (no se pudo abrir: la página da los pasos para hacerlo tú)."""
    if _ventana_viva(agente, wid):
        return "ok"
    if os.environ.get("WORKSPACE_NO_VENTANAS"):   # la suite: jamás una terminal de verdad (como WORKSPACE_NO_AVISO_PANEL)
        return "sin_herdr"
    from control import entorno
    # una terminal nueva, como la pestaña de herdr: sin la identidad de otra pestaña o sesión que la página heredó
    # (el --open de dispatch pone la suya)
    env = dict(entorno.limpio(), WORKSPACE_NO_GREETER="1", WORKSPACE_DESDE_WEB="1")
    py = _python_de_consola()
    try:
        p = subprocess.Popen([py, "-c", _VENTANA_ESPERA, i18n.t("localhost.ventana_fallo")]
                             + _comando_dispatch(agente, wid, nombre, motor, extra, py),
                             cwd=HERE, env=env, creationflags=CREATE_NEW_CONSOLE)
    except (OSError, ValueError):
        return "sin_herdr"
    _VENTANAS[(agente, wid)] = p
    _LANZADOS.pop((agente, wid), None)            # no es un panel de herdr: nada que cerrar por ahí
    return "ok"


def _lanzar_en_herdr(agente, wid, nombre, motor="", extra=()):
    """La pestaña nueva de herdr (lo de siempre en Mac y Linux). → "ok" | "sin_herdr"."""
    import shlex
    import aviso_panel
    if not aviso_panel._exe():
        return "sin_herdr"
    # WORKSPACE_NO_GREETER: sin esto, el arranque de la terminal abre el hub en la pestaña nueva y el
    # hub se traga el comando (la pestaña se quedaba en el menú: «no abre»). Mismo cuidado que skill_review_visible.
    # WORKSPACE_DESDE_WEB: la abrió la página; el motor arranca sin anunciarse (memoria.fin_arranque).
    env = ["--env", "WORKSPACE_NO_GREETER=1", "--env", "WORKSPACE_DESDE_WEB=1"]
    esp = _espacio_navegador(env)
    if esp.get("panel"):                          # el espacio se acaba de crear: su primera pestaña es esta
        creado = {"tab": {"tab_id": esp.get("tab")}, "root_pane": {"pane_id": esp["panel"]}}
        if esp.get("tab"):
            aviso_panel._herdr(["tab", "rename", esp["tab"], nombre[:40]], json_out=False)
    else:
        creado = aviso_panel._herdr(["tab", "create"] + (["--workspace", esp["id"]] if esp.get("id") else [])
                                    + ["--cwd", HERE, "--label", nombre[:40], "--no-focus"] + env)
    tab = (creado or {}).get("tab", creado or {})
    panel = ((creado or {}).get("root_pane") or {}).get("pane_id") or tab.get("pane_id") or ""
    if not panel and tab.get("tab_id"):
        lista = aviso_panel._herdr(["pane", "list"]) or {}
        panes = [p for p in lista.get("panes", []) if p.get("tab_id") == tab.get("tab_id")]
        panel = panes[0].get("pane_id") if len(panes) == 1 else ""
    if not panel:
        return "sin_herdr"
    cmd = _comando_dispatch(agente, wid, nombre, motor, extra)
    if os.name == "nt":
        import skill_review_visible
        linea = skill_review_visible.pane_command(cmd, windows=True)
    else:
        linea = shlex.join(cmd)
    if aviso_panel._herdr(["pane", "run", panel, linea], json_out=False) is None:
        return "sin_herdr"
    _LANZADOS[(agente, wid)] = panel              # si un cambio de motor se abandona, su pestaña se cierra
    return "ok"


_LANZADOS = {}              # (agente, wid) → el panel de herdr que se abrió por última vez para esa pestaña
ESPACIO_NAVEGADOR = "Navegador"     # el espacio de herdr de las pestañas de motor que abre la página
_ESPACIO = {}               # {"id": el espacio «Navegador» que creó este servidor}
_ESPACIO_LOCK = threading.Lock()


def _espacio_navegador(env):
    """El espacio de herdr «Navegador», donde van las pestañas de motor que abre la página (no el que tengas
    enfocado): {"id"} si ya está; si no, lo crea sin foco y da también su primera pestaña y su panel ({"id", "tab",
    "panel"}), que son los del motor (sin una shell vacía de más). {} si este herdr no tiene espacios: la pestaña se
    abre como antes. El que creó se reconoce por su id aunque su etiqueta no se lea. Con candado: dos aperturas a la
    vez no crean dos."""
    import aviso_panel
    with _ESPACIO_LOCK:
        lista = (aviso_panel._herdr(["workspace", "list"]) or {}).get("workspaces")
        if not isinstance(lista, list):
            return {}
        ids = [str(w.get("workspace_id") or w.get("id") or "") for w in lista if isinstance(w, dict)]
        if _ESPACIO.get("id") in ids:
            return {"id": _ESPACIO["id"]}
        for w, i in zip([w for w in lista if isinstance(w, dict)], ids):
            if i and (w.get("label") or w.get("name")) == ESPACIO_NAVEGADOR:
                return {"id": i}
        nuevo = aviso_panel._herdr(["workspace", "create", "--cwd", HERE, "--label", ESPACIO_NAVEGADOR, "--no-focus"]
                                   + env) or {}
        i = str((nuevo.get("workspace") or {}).get("workspace_id") or "")
        if not i:
            return {}
        _ESPACIO["id"] = i
        return {"id": i, "tab": (nuevo.get("tab") or {}).get("tab_id") or "",
                "panel": (nuevo.get("root_pane") or {}).get("pane_id") or ""}


_NOMBRE_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,60}$")


def nueva_pestana(agente, nombre, motor=""):
    """Una pestaña nueva del agente, abierta en el hub. → (estado, slug)."""
    import time as _t
    import uuid
    import dispatch
    import sessions_registry
    nombre = " ".join(str(nombre or "").split())
    if not _NOMBRE_RE.match(nombre) or nombre.startswith("-"):
        return "nombre", ""
    if agente not in {str(e.get("name") or "") for e in (dispatch.load_registry() or {}).get("agents") or []}:
        return "no_existe", ""
    if motor and motor not in _motores_listos():
        return "motor", ""
    slug = sessions_registry._slug(nombre)
    brain = dict(_cerebros()).get(agente)
    try:
        soc = sessions_registry.socio(brain) if brain else ""
        if soc and any(t.get("slug") == slug for t in _pestanas_web(brain, soc)):
            return "existe", slug
    except Exception:
        pass
    if _t.time() - _ABRIENDO.get((agente, slug), 0) < 30:
        return "abriendo", slug
    r = _lanzar(agente, str(uuid.uuid4()), nombre, motor)
    if r != "ok":
        return r, ""
    _ABRIENDO[(agente, slug)] = _t.time()
    return "abriendo", slug


def abrir_pestana(agente, slug, motor=""):
    """Reabre una pestaña cerrada en una pestaña NUEVA de herdr (sin foco), como
    elegirla en el menú de sesiones: dispatch <agente> --open <wid> --name <nombre>.
    → "ya" | "abriendo" | motivo de error."""
    import time as _t
    import aviso_panel
    bt, reg = _pestana_y_panel(agente, slug)
    if bt is None and slug == NAVEGADOR and _sembrar_navegador(agente):
        bt, reg = _pestana_y_panel(agente, slug)          # la de la página nace con su primer mensaje
    if bt is None:
        return "no_existe"
    if reg and aviso_panel.estado_panel(reg).get("ok"):
        return "ya"
    try:
        import sessions_registry
        if slug in sessions_registry.abiertas_en_ventanas(dict(_cerebros()).get(agente)):
            return "en_ventana"           # viva en otra ventana (o en segundo plano): abrirla la duplicaría
    except Exception:
        return "sin_herdr"
    wid, nombre = _wid_de(bt), str(bt.get("name") or "").strip()
    if not _WID_RE.match(wid) or not nombre or nombre.startswith("--"):
        return "sin_sesion"
    if motor and motor not in _motores_listos():
        return "motor"
    if _t.time() - _ABRIENDO.get((agente, slug), 0) < 30:
        return "abriendo"
    # la conversación de la página arranca con lo guardado en sus botones (§6: lo que solo existe al arrancar), los
    # del motor con que de verdad arranca: sin --engine, dispatch abre el del agente
    extra, van = _flags_de_arranque(agente, motor or _motores_de_agentes().get(agente) or "") if slug == NAVEGADOR \
        else ([], {})
    r = _lanzar(agente, wid, nombre, motor, extra)
    if r != "ok":
        return r
    _ABRIENDO[(agente, slug)] = _t.time()
    if slug == NAVEGADOR:
        _AJ_HECHOS[agente] = {"panel": _LANZADOS.get((agente, wid)), "valores": van}
    return "abriendo"


_CAMBIOS = {}               # (agente, slug) → {"id", "motor", "de", "paso", "error", "t", "inicio"}: el cambio en curso
CAMBIO_VISIBLE_S = 60       # cuánto se sigue enseñando un cambio que ya terminó (listo o con error)
CAMBIO_TOPE_S = 120         # cuánto se espera a que el motor nuevo quede abierto
CAMBIO_NORMAL_S = 30        # pasado esto, «está tardando más de lo normal»: se puede volver al de antes (forzar)


def cambiar_motor(agente, slug, motor, forzar=False, reabrir=False):
    """La función estrella: la MISMA pestaña con otro motor. Aquí solo se valida (rápido); lo
    lento va en segundo plano (_cambiar_en_fondo) y la página ve en qué va en `cambio` de
    /api/conversacion, sin dejar de ver la conversación. `reabrir`: con el MISMO motor («Reabrir
    ahora»: lo guardado para su arranque se aplica). → "abriendo" | motivo."""
    import time as _t
    import aviso_panel
    if motor not in _motores_listos():
        return "motor"
    import secrets as _s
    bt, reg = _pestana_y_panel(agente, slug)
    if bt is None:
        return "no_existe"
    if reg:
        st = aviso_panel.estado_panel(reg)
        if not st.get("ok"):
            reg = None                            # su panel ya no está: nada que cerrar
        elif reg.get("motor") == motor and not reabrir:
            return "mismo"
        elif not st.get("quieto") and not forzar:
            return "atorado" if st.get("menu") else "trabajando"     # H14: detenido en una pregunta de su terminal
    c, ahora = _CAMBIOS.get((agente, slug)), _t.time()
    if c and c["paso"] not in ("listo", "error") and ahora - c["t"] < CAMBIO_TOPE_S \
            and not (forzar and ahora - c.get("inicio", c["t"]) > CAMBIO_NORMAL_S):
        return "abriendo"                         # ya va uno: no se lanza otro encima (salvo «volver» si tarda)
    reemplaza = bool(c and c["paso"] not in ("listo", "error"))
    de = (reg or {}).get("motor") or (c["motor"] if reemplaza else "") or _motor_de_conversacion(agente, slug)
    cid = _s.token_hex(4)
    _CAMBIOS[(agente, slug)] = {"id": cid, "motor": motor, "de": de, "paso": "guardando", "error": "", "t": ahora,
                                "inicio": ahora, "reabre": bool(reabrir)}
    # el que se abandona pudo dejar su pestaña arrancando: se cierra antes de abrir el otro (no dos motores a la vez)
    abandonado = _LANZADOS.pop((agente, _wid_de(bt)), None) if reemplaza else None
    if abandonado and abandonado != (reg or {}).get("panel"):
        aviso_panel._herdr(["pane", "close", abandonado], json_out=False)
    _en_segundo_plano(_cambiar_en_fondo, agente, slug, motor, reg, cid, reabrir)
    return "abriendo"


def _en_pregunta(agente, slug):
    """H14: ¿su motor está detenido en una pregunta o un permiso de su terminal? Ahí «Detener» no lo saca (Cursor vuelve
    a pedir el mismo permiso) y «Cerrar y cambiar» es la salida, sin esperar la gracia de un «Detener»."""
    import aviso_panel
    try:
        _bt, reg = _pestana_y_panel(agente, slug)
        return bool(reg) and bool(aviso_panel.estado_panel(reg).get("menu"))
    except Exception:
        return False


def _motor_de_conversacion(agente, slug):
    """El motor con que iba la conversación de la página (su último tramo), o ""."""
    try:
        with _HIST_LOCK:
            tr = _tramos(_eventos(_cerebro(agente))) if slug == NAVEGADOR else []
    except Exception:
        tr = []
    return tr[-1][0] if tr else ""


def _cambiar_en_fondo(agente, slug, motor, reg, cid="", reabrir=False):
    """Hilo del cambio: ¿el motor nuevo tiene sesión? (si no, nada se cierra) → guardar lo
    hablado → cerrar su panel y esperar hasta 10 s a que su proceso termine → la maleta con
    el historial → abrirla con `--engine <motor>` → listo cuando su panel corre ese motor.
    Si otro cambio lo reemplazó («volver al de antes»), deja de escribir su avance. `reabrir`:
    el mismo motor; la maleta va igual (si no retoma su sesión, con ella sigue la conversación)."""
    import time as _t
    import aviso_panel
    import motores_logica
    import sessions_registry
    k = (agente, slug)
    anotado = []                                   # el cerebro cuyo registro ya tiene el evento de este motor

    def mio():
        return not cid or (_CAMBIOS.get(k) or {}).get("id") == cid

    def paso(p, error=""):
        if mio():
            _CAMBIOS[k] = dict(_CAMBIOS.get(k) or {"id": cid, "motor": motor, "de": "", "inicio": _t.time()},
                               paso=p, error=error, t=_t.time())
            if p == "error" and anotado:
                _cambio_fallido(anotado[0], motor)
    try:
        if motores_logica._probe(motor) not in (True, None):          # None = no se pudo saber: se intenta
            return paso("error", "localhost.err.motor_sin_sesion")
        brain = dict(_cerebros()).get(agente)
        viejo = _historial_al_cambiar(brain, reg, motor) if slug == NAVEGADOR and brain else ""
        if slug == NAVEGADOR and brain:
            anotado.append(brain)
        if reg and not _en_el_panel(reg, lambda: aviso_panel._herdr(["pane", "close", reg["panel"]], reg.get("socket", ""),
                                                                      json_out=False) is not None):
            return paso("error", "localhost.err.motor_panel")
        for _ in range(40):
            try:
                vivo = slug in sessions_registry.abiertas_en_ventanas(brain)
            except Exception:
                vivo = False
            if not vivo:
                break
            _t.sleep(0.25)
        else:
            return paso("error", "localhost.err.motor_en_ventana")
        if viejo or (reabrir and brain and slug == NAVEGADOR):
            _maleta_navegador(brain, viejo or motor)   # después del cierre: el del motor viejo ya no la pisa
        if not mio():
            return                                 # lo reemplazó otro cambio («volver»): ese abre el suyo
        paso("abriendo")
        _ABRIENDO.pop(k, None)
        r = abrir_pestana(agente, slug, motor)
        if r not in ("abriendo", "ya"):
            return paso("error", "localhost.err.abrir_" + r)
        t0, listas, firma, fallas = _t.time(), 0, None, 0
        while _t.time() - t0 < CAMBIO_TOPE_S and mio():
            # F8/F9: «Listo» solo cuando acepta mensajes (su caja lista dos lecturas seguidas), no cuando su panel
            # ya corre el motor; con un menú a la vista también (la página lo enseña y tú decides)
            _bt, nuevo = _pestana_y_panel(agente, slug)
            if nuevo and nuevo.get("motor") == motor and _estado_rapido(nuevo, fresco=True).get("ok"):
                lista, firma = _caja_lista(nuevo, firma)
                listas = listas + 1 if lista else 0
                if listas >= 2:
                    return paso("listo")
                vis = _leer_panel(nuevo, 60, "visible") or ""
                if pregunta_de(vis):
                    return paso("listo")
                falla = None if lista else _falla_al_abrir(nuevo, vis)
                fallas = fallas + 1 if falla else 0
                if fallas >= 2:
                    return paso("error", "localhost.err.motor_" + falla)
            _t.sleep(1.0)
        paso("error", "localhost.err.motor_tarde")
    except Exception:
        paso("error", "localhost.err.abrir_sin_herdr")


#: N5 (prueba de punta a punta v3, 17-nov): los errores del motor nuevo que esperar no arregla. Copilot sin cuota
#: lo dijo a los ~5 s y el cambio siguió «abriendo» hasta el tope (122 s): herdr no lo daba por quieto, así que su
#: caja nunca contaba como lista. Ahora el cambio termina ya, con su porqué y la salida de volver al de antes.
FALLA_AL_ABRIR = ("creditos", "limite", "login", "llave")


def _falla_al_abrir(reg, vis):
    """El tipo de error que enseña el motor nuevo al abrir, si no está trabajando (lo mismo que mira la foto para
    enseñar su tarjeta: front_vivo) y esperar no lo arregla; None si no. Mientras trabaja no cuenta: al retomar su
    sesión puede enseñar el error de una vuelta anterior mientras hace el arranque."""
    from pantalla_motor import error_de
    if _trabajando(_estado_rapido(reg, fresco=True)):
        return None
    e = error_de(vis)
    return e["tipo"] if e and e["tipo"] in FALLA_AL_ABRIR else None


def cambio_de(agente, slug):
    """El cambio de motor de esa pestaña para la página (con la CLAVE de su error), o None."""
    import time as _t
    c = _CAMBIOS.get((agente, slug))
    if not c or (c["paso"] in ("listo", "error") and _t.time() - c["t"] > CAMBIO_VISIBLE_S):
        return None
    return {"id": c.get("id", ""), "motor": c["motor"], "de": c.get("de", ""), "paso": c["paso"], "error": c["error"],
            "t": int(c["t"]), "inicio": int(c.get("inicio", c["t"])), "normal": CAMBIO_NORMAL_S,
            "reabre": bool(c.get("reabre"))}


# ── la conversación de una pestaña (no la terminal): de la transcripción de su motor ──
_CONV_CACHE = {}           # ruta → (mtime, tamaño, turnos)
_CONV_MOTORES = ("claude-code", "codex")


_RUTAS_T = {}               # (motor, sid, base) → (hora, ruta): buscarla recorre todas las carpetas del motor
RUTA_T_S = 10.0             # cada cuánto se vuelve a buscar (Codex puede abrir otro rollout para la misma sesión)


def _transcripcion(motor, sid):
    """Ruta del archivo de la sesión `sid` de `motor` en esta máquina, o None."""
    import glob
    import time as _t
    if not sid or not re.match(r"^[A-Za-z0-9._-]{4,80}$", str(sid)):
        return None
    home = os.path.expanduser("~")
    if motor == "claude-code":
        base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home, ".claude")
        patron = os.path.join(base, "projects", "*", sid + ".jsonl")
    elif motor == "codex":
        base = os.environ.get("CODEX_HOME") or os.path.join(home, ".codex")
        patron = os.path.join(base, "sessions", "*", "*", "*", "rollout-*%s.jsonl" % sid)
    else:
        return None
    c = _RUTAS_T.get((motor, sid, base))
    if c and _t.time() - c[0] < RUTA_T_S and os.path.isfile(c[1]):
        return c[1]
    hits = glob.glob(patron)
    ruta = max(hits, key=os.path.getmtime) if hits else None
    if ruta:
        if len(_RUTAS_T) > 200:
            _RUTAS_T.clear()
        _RUTAS_T[(motor, sid, base)] = (_t.time(), ruta)
    return ruta


# herramientas que lanzan un subagente (Claude Code «Task»/«Agent»; nombres afines de otros motores)
_SUB_HERR = {"task", "agent", "subagent", "sub_agent", "spawn_agent", "spawn_subagent", "delegate", "dispatch_agent"}


def _herramienta(tc):
    i = tc.get("input") or {}
    det = ""
    if str(tc.get("name") or "").lower() in _SUB_HERR:
        tipo = i.get("subagent_type") or i.get("agent") or i.get("type") or ""
        tarea = i.get("description") or (str(i.get("prompt") or "").strip().split("\n")[0])
        return {"n": _recorta(tc.get("name"), 40), "d": _limpio(tarea, 160), "sub": True,
                "tipo": _recorta(tipo if isinstance(tipo, str) else "", 40)}
    for k in ("file_path", "path", "command", "cmd", "pattern", "url", "query", "description", "skill"):
        v = i.get(k)
        if isinstance(v, list):
            v = " ".join(str(x) for x in v)
        if isinstance(v, str) and v.strip():
            det = v.strip().split("\n")[0]
            break
    return {"n": _recorta(tc.get("name"), 40), "d": _limpio(det, 160)}


def _de_maleta(brain, nombre):
    """La maleta de una pestaña cerrada (lo último que pidió el socio y la última
    respuesta) → turnos. [] si no hay."""
    import memoria
    try:
        secs = memoria.leer_maleta(memoria.maleta_path(brain, nombre))
    except Exception:
        return []
    if not secs:
        return []
    sec = max(secs, key=lambda x: x.get("cuando") or "")
    out, modo = [], ""
    for ln in sec.get("lineas") or []:
        t = ln.strip()
        if t.startswith("Lo último que pidió"):
            modo = "yo"
        elif t.startswith("La última respuesta"):
            modo = "agente"
        elif t.startswith("Archivos que tocó"):
            modo = ""
        elif modo == "yo" and t.startswith("- "):
            out.append({"rol": "yo", "texto": _sin_secretos(t[2:])[:2000], "ts": "", "herr": []})
        elif modo == "agente" and t:
            txt = t[2:] if t.startswith("> ") else t
            if out and out[-1]["rol"] == "agente":
                out[-1]["texto"] += "\n" + txt
            else:
                out.append({"rol": "agente", "texto": _sin_secretos(txt)[:6000], "ts": "", "herr": []})
    return out


CONV_TOPE = 4 * MAX_TURNOS     # turnos que se guardan por transcript (los últimos): la ventana nunca pide más


def _cabeza(ruta, n=512):
    try:
        with open(ruta, "rb") as f:
            return f.read(n)
    except OSError:
        return b""


def _turnos_transcripcion(motor, ruta):
    """Turnos de una transcripción de Claude Code o Codex. INCREMENTAL: un transcript de varios MB
    que crece se lee solo desde donde se quedó (antes se releía entero en cada sondeo: 240 ms con
    3 MB). Si se reescribió (otro inodo, más corto, o cambió su principio) se lee de nuevo. Se
    guardan los últimos CONV_TOPE turnos; los que se van cuentan en `podados` (el total sigue)."""
    import neutral_transcript as nt
    st = os.stat(ruta)
    c = _CONV_CACHE.get(ruta)
    if c and (c["ino"], c["mtime"], c["tam"]) == (st.st_ino, st.st_mtime_ns, st.st_size):
        return c["turnos"]
    cabeza = _cabeza(ruta)
    if not c or c["ino"] != st.st_ino or st.st_size < c["pos"]["offset"] or not cabeza.startswith(c["cabeza"][:len(cabeza)]):
        c = {"pos": {"offset": 0}, "turnos": [], "podados": 0}
    doc = (nt.parse_claude_code if motor == "claude-code" else nt.parse_codex)(ruta, pos=c["pos"])
    turnos = list(c["turnos"])                    # copia: quien ya tiene la lista anterior no la ve cambiar
    for t in doc.get("turns") or []:
        if t.get("noise"):
            continue
        texto = _sin_secretos(t.get("text") or "")[:12000]
        herr = [_herramienta(x) for x in (t.get("tool_calls") or [])][:20]
        if not texto.strip() and not herr:
            continue
        turnos.append({"rol": "yo" if t.get("role") == "user" else "agente", "texto": texto,
                       "ts": _recorta(t.get("ts"), 30), "herr": herr})
    sobran = max(0, len(turnos) - CONV_TOPE)
    c.update(ino=st.st_ino, mtime=st.st_mtime_ns, tam=st.st_size, cabeza=cabeza, turnos=turnos[sobran:],
             podados=c["podados"] + sobran)
    _CONV_CACHE.pop(ruta, None)
    _CONV_CACHE[ruta] = c
    if len(_CONV_CACHE) > 40:
        _CONV_CACHE.pop(next(iter(_CONV_CACHE)))
    return c["turnos"]


def _podados(ruta):
    """Los turnos de ese transcript que ya no se guardan (para que el total siga contando)."""
    return (_CONV_CACHE.get(ruta) or {}).get("podados", 0)


def _pantalla_de(reg, lineas=600):
    """El texto reciente del panel, o None. Normalmente sin los cortes de renglón del ancho
    («recent-unwrapped»); pero las apps de pantalla completa (OpenCode) llenan cada fila
    hasta el borde y herdr las pega en dos o tres renglones gigantes: ahí se leen las filas
    tal cual («recent»)."""
    if (reg or {}).get("motor") == "opencode":
        return _leer_panel(reg, lineas, "recent")
    t = _leer_panel(reg, lineas, "recent-unwrapped")
    if t and len(t) > 2000 and len(t) / max(1, t.count("\n") + 1) > 400:
        t = _leer_panel(reg, lineas, "recent") or t
    return t


def _leer_panel(reg, lineas, fuente):
    try:
        import subprocess
        import arbol_procesos
        import aviso_panel
        e = aviso_panel.entorno_herdr(reg.get("socket") or "")   # W0: su socket o la sesión del servidor
        r = subprocess.run([aviso_panel._exe(), "pane", "read", reg["panel"], "--source", fuente,
                            "--lines", str(lineas)], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=aviso_panel.TIMEOUT_S, env=e, stdin=subprocess.DEVNULL,
                           **arbol_procesos.sin_ventana())          # Windows: la página no tiene consola
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


MAX_PREVIOS = 24      # turnos de la historia con el motor anterior que se muestran tras un cambio


# ── el historial de la conversación de la página: un registro de eventos, solo de anexar (historial_eventos) ──
# STATE/sessions/<socio>/historial/navegador.eventos.jsonl: viaja con el cerebro y sobrevive a cambiar de motor (la
# página enseña todos sus tramos en orden, con «Siguió con X»). Antes se rearmaba fusionando ventanas de pantalla con lo
# guardado y cada heurística dejaba otro hueco (H9, N1). Ahora tu mensaje se anexa UNA vez, cuando sale (su envio_id);
# la respuesta del agente, UNA vez por turno, cuando su máquina de estados dice que terminó (cerrar_turno), de su
# transcripción o de lo nuevo en su pantalla después de tu mensaje. La pantalla viva solo enseña el turno en curso.
MALETA_TURNOS = 16          # turnos del historial que se lleva el motor nuevo
MALETA_EXTRACTO = 4500      # caracteres de ese extracto (la maleta entera topa en memoria.MALETA_MAX)
IMPORTAR_MAX = 160          # de lo que su motor ya tenía antes de la página, lo último que se importa (una vez)
CERRAR_REINTENTO_S = 15     # con tu último mensaje sin respuesta (un servidor que se reinició), cada cuánto se busca
CERRAR_VENTANA_S = 600      # y hasta cuándo, desde que lo mandaste
_HIST_LOCK = threading.RLock()
_TS_RE = re.compile(r"^(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d)(\.\d+)?(Z|[+-]\d\d:?\d\d)?$")


def _epoch_ts(ts):
    """El `timestamp` de una transcripción («2026-11-16T16:30:02.696Z») → epoch con sus decimales; 0.0 si no se lee."""
    import datetime as _dt
    m = _TS_RE.match(str(ts or "").strip())
    if not m:
        return 0.0
    tz = m.group(3) or ""
    tz = "+00:00" if tz == "Z" else (tz[:3] + ":" + tz[-2:] if tz else "")
    try:
        # la fracción va aparte: fromisoformat de Python 3.9 solo acepta 3 o 6 decimales
        return _dt.datetime.fromisoformat(m.group(1).replace(" ", "T") + tz).timestamp() + float("0" + (m.group(2) or ""))
    except ValueError:
        return 0.0


def _historial_path(brain):
    """El historial de antes (segmentos por motor): solo se lee para migrarlo."""
    import memoria
    return os.path.join(memoria._carpeta_socio(brain, NAVEGADOR_NOMBRE), "historial", NAVEGADOR + ".json")


def _eventos_path(brain, slug=NAVEGADOR, canal=NAVEGADOR):
    """El historial por eventos de una conversación de la página: la de siempre o (H4-a) la de otra pestaña, por su
    slug, junto a ella (STATE/sessions/<socio>/historial/<slug>.eventos.jsonl). Con `canal` «escritorio», el de la
    conversación del Compañero de escritorio: su propio archivo, aparte."""
    if canal == ESCRITORIO:
        import memoria
        return os.path.join(memoria._carpeta_socio(brain, ESCRITORIO_NOMBRE), "historial", ESCRITORIO + ".eventos.jsonl")
    return os.path.join(os.path.dirname(_historial_path(brain)), (slug or NAVEGADOR) + ".eventos.jsonl")


def _eventos(brain, reg=None, slug=NAVEGADOR, canal=NAVEGADOR):
    """(Con _HIST_LOCK.) Los eventos de su conversación. La primera vez se crea su registro: el historial de antes se
    convierte tal cual (con respaldo); si no había y su motor está a la vista (`reg`), lo que ese motor ya tenía se
    importa UNA vez, marcado. Sin nada de eso, [] y no se crea nada. La del escritorio (`canal`) nace vacía: no migra
    ni importa nada. La de otra pestaña (H4-a) solo se lee: la crea quien la abre (pagina_v2)."""
    import historial_eventos as HE
    if canal == ESCRITORIO:
        ruta = _eventos_path(brain, canal=ESCRITORIO)
        return HE.leer(ruta) if os.path.exists(ruta) else []
    if slug and slug != NAVEGADOR:
        ruta = _eventos_path(brain, slug)
        return HE.leer(ruta) if os.path.exists(ruta) else []
    ruta = _eventos_path(brain)
    if not os.path.exists(ruta):
        if os.path.exists(_historial_path(brain)):
            HE.migrar(_historial_path(brain), ruta)
        elif reg and reg.get("motor"):
            _importar(brain, ruta, reg)
    return HE.leer(ruta)


def _ahora_ev():
    import time as _t
    t = _t.time()
    return t, _t.strftime("%Y-%m-%dT%H:%M:%S", _t.gmtime(t)) + "Z"


def _ev_sistema(tipo, motor, **kw):
    t, ts = _ahora_ev()
    return dict({"id": "%s-%s" % (tipo, secrets.token_hex(6)), "rol": "sistema", "tipo": tipo, "texto": "", "motor": motor,
                 "t": t, "ts": ts}, **kw)


def _importar(brain, ruta, reg):
    """Lo anterior a la página: lo que su motor ya tenía (su transcripción o su pantalla), una vez y marcado."""
    import historial_eventos as HE
    m = reg.get("motor") or ""
    turnos = (_turnos_de_su_motor(m, _slot_navegador(brain), reg) or [])[-IMPORTAR_MAX:]
    evs = [_ev_sistema("motor", m), _ev_sistema("importado", m, n=len(turnos))]
    for x in turnos:
        e = {"id": "i-" + secrets.token_hex(8), "rol": x["rol"], "texto": x.get("texto") or "", "motor": m,
             "t": evs[0]["t"], "ts": x.get("ts") or "", "herr": x.get("herr") or [], "importado": True}
        for k in ("contexto", "arranque"):
            if x.get(k):
                e[k] = True
        evs.append(e)
    HE.crear(ruta, evs)


def _turnos_de_su_motor(m, slot, reg):
    """Lo que su motor tiene ahora: su transcripción en esta máquina, o su pantalla si su panel `reg` está a la vista;
    None si no se puede leer."""
    ruta = _transcripcion(m, slot.get(m)) if m in _CONV_MOTORES else None
    if ruta:
        return _sin_nota(_sin_arranques(_turnos_transcripcion(m, ruta)))
    if reg and reg.get("motor") == m:
        pantalla = _pantalla_de(reg)
        return _sin_nota(_sin_arranques(_de_pantalla(_sin_pregunta(pantalla), m, _tecleados(reg)))) if pantalla else None
    return None


def _tramos(evs):
    """[[motor, [lo que se enseña], ¿ya se le contó lo de los otros motores?, ¿su cambio falló?]] en orden: un tramo por
    motor, desde su evento «motor» (o desde un turno de otro motor). Una respuesta que se anotó después de cambiar de
    motor (de la transcripción del que se fue) se enseña con tu mensaje, en su tramo. 6 (E2E v4): el tramo de un cambio
    que falló («cambio_fallido») queda marcado mientras siga vacío (la página no dice «Siguió con …»); si luego se
    vuelve al motor de antes, sigue el tramo de ese."""
    out, de_quien = [], {}
    for e in evs:
        m = e.get("motor") or ""
        if e.get("rol") == "sistema":
            if e.get("tipo") == "motor" and out and out[-1][3] and len(out) > 1 and out[-2][0] == m:
                out.pop()                          # «Volver a X» tras un cambio que falló: sigue el tramo de X
            elif e.get("tipo") == "motor" and (not out or out[-1][0] != m):
                out.append([m, [], False, False])
            elif e.get("tipo") == "contexto" and out and out[-1][0] == m:
                out[-1][2] = True
            elif e.get("tipo") == "cambio_fallido" and out and out[-1][0] == m and not out[-1][1]:
                out[-1][3] = True
            continue
        suyo = de_quien.get(e.get("envio_id")) if e.get("rol") == "agente" else None
        if suyo is not None and out and suyo is not out[-1]:
            suyo[1].append(e)
            continue
        if not out or (m and m != out[-1][0]):
            out.append([m, [], False, False])
        out[-1][1].append(e)
        out[-1][3] = False                         # le hablaste: sí siguió con ese motor
        if e.get("rol") == "yo" and e.get("envio_id"):
            de_quien[e["envio_id"]] = out[-1]
    return out


def _motor_al_dia(brain, evs, motor, slug=NAVEGADOR):
    """(Con _HIST_LOCK.) Si la conversación sigue con otro motor que el de su último tramo, su evento «motor» (solo en un
    registro que ya existe: crearlo es de _eventos). → los eventos."""
    import historial_eventos as HE
    tr, ruta = _tramos(evs), (_eventos_path(brain) if slug == NAVEGADOR else _eventos_path(brain, slug))
    if motor and (not tr or tr[-1][0] != motor) and os.path.exists(ruta):
        HE.anexar(ruta, [_ev_sistema("motor", motor)])
        return HE.leer(ruta)
    return evs


def anotar_envio(agente, cid, texto, reg, contexto=False):
    """Tu mensaje, al historial de la página: UNA vez, cuando salió (su envio_id es el `cid` de la página). Antes, la
    respuesta a tu mensaje anterior si faltaba (su pantalla todavía la enseña). Nunca tumba el envío."""
    import historial_eventos as HE
    try:
        brain = _cerebro(agente)
        if not brain:
            return
        motor = (reg or {}).get("motor") or ""
        t, ts = _ahora_ev()
        cid = str(cid or "") or "s" + secrets.token_hex(6)
        e = {"id": "y-" + cid, "rol": "yo", "texto": _sin_secretos(str(texto or ""))[:12000], "motor": motor, "t": t,
             "ts": ts, "envio_id": cid}
        if contexto:
            e["contexto"] = True
        with _HIST_LOCK:
            evs = _eventos(brain, reg)
            cerrar_turno(brain, reg)
            _motor_al_dia(brain, evs, motor)
            HE.anexar(_eventos_path(brain), [e])
    except Exception as x:
        sys.stderr.write("historial: no anoté tu mensaje (%s)\n" % type(x).__name__)


def _ultimo_envio(evs):
    return next((e for e in reversed(evs) if e.get("rol") == "yo" and e.get("envio_id")), None)


def _sin_espacios(t):
    return re.sub(r"\s+", "", str(t or ""))


def _es_el_mio(visto, mio):
    """¿El mensaje tuyo que se ve (`visto`, sin espacios) es el que mandaste (`mio`)? Igual; con lo que ya tenía su caja
    delante («Mandar igual»); o, de 16+ caracteres, cortado arriba (la ventana) o abajo."""
    return bool(mio) and (visto == mio or visto.endswith(mio)
                          or (len(visto) >= 16 and (mio.endswith(visto) or mio.startswith(visto))))


def _lo_que_contesto(turnos, texto, desde=0.0):
    """Lo del agente después de tu mensaje `texto` (el último que se ve así) hasta tu siguiente mensaje: {"texto",
    "herr"}, o None si tu mensaje no se ve (no se adivina: lo de arriba puede ser de antes). Con hora (transcripción),
    solo cuenta un mensaje tuyo desde `desde`."""
    mio = _sin_espacios(texto)
    i = next((k for k in range(len(turnos) - 1, -1, -1) if turnos[k].get("rol") == "yo"
              and (not desde or not turnos[k].get("ts") or _epoch_ts(turnos[k]["ts"]) >= desde)
              and _es_el_mio(_sin_espacios(turnos[k].get("texto")), mio)), None)
    if i is None:
        return None
    suyos = []
    for x in turnos[i + 1:]:
        if x.get("rol") == "yo":
            break
        if not x.get("arranque"):
            suyos.append(x)
    textos = [_sin_relleno(x.get("texto")) for x in suyos]
    return {"texto": "\n\n".join(t for t in textos if t), "herr": [h for x in suyos for h in (x.get("herr") or [])][:60]}


# lo que el motor escribe o pinta tras tu mensaje y no es su respuesta (5 · E2E v4): el «No response requested.» con que
# Claude Code retoma su sesión, y el «Interrupted · What should … do instead?» de Antigravity cerrado a medio turno
# con su resumen de lo plegado («… 3 more actions (1 read, 2 tools) …»)
_RELLENO_RE = re.compile(r"^[ \t]*(?:No response requested\.|Interrupted(?:[ \t]*·[ \t]*What should .{1,60} do instead\?)?"
                         r"|(?:…|\.\.\.)[ \t]*\d+ more actions?\b.*)[ \t]*$", re.M)


def _sin_relleno(texto):
    return re.sub(r"\n{3,}", "\n\n", _RELLENO_RE.sub("", str(texto or ""))).strip()


def _respuesta(brain, y, reg):
    """Lo que el agente contestó a tu mensaje `y` (su evento), de la mejor fuente: su transcripción si su motor la
    tiene; si no, lo nuevo en su pantalla después de tu mensaje (solo con SU panel a la vista). None si no se sabe."""
    m = y.get("motor") or ""
    turnos = _turnos_de_su_motor(m, _slot_navegador(brain), reg if (reg or {}).get("motor") == m else None)
    return _lo_que_contesto(turnos, y.get("texto"), float(y.get("t") or 0) - 120) if turnos else None


def _resto(nuevo, viejo):
    """Lo que `nuevo` trae después de `viejo` (sin contar espacios ni saltos), o None si no empieza con él."""
    i = 0
    for ch in viejo:
        if ch.isspace():
            continue
        while i < len(nuevo) and nuevo[i].isspace():
            i += 1
        if i >= len(nuevo) or nuevo[i] != ch:
            return None
        i += 1
    return nuevo[i:]


def _lo_nuevo(r, hechos):
    """De la respuesta `r`, lo que todavía no está en los eventos `hechos` de ese turno: {"texto", "herr"} o None. Si lo
    guardado ya no es su principio (su pantalla lo redibujó distinto), nada: mejor de menos que dos veces."""
    resto = _resto(r["texto"], "\n\n".join(str(e.get("texto") or "") for e in hechos)) if hechos else r["texto"]
    if resto is None:
        return None
    herr = r["herr"][sum(len(e.get("herr") or []) for e in hechos):]
    return {"texto": resto.strip(), "herr": herr} if resto.strip() or herr else None


def cerrar_turno(brain, reg):
    """La respuesta del agente a tu último mensaje, al historial: UNA vez por turno (su id sale del envio_id). Si sigue
    escribiendo en ese mismo turno, lo que falte entra como su continuación, nunca lo mismo otra vez. La llaman la
    máquina de estados al pasar a «terminó» (front_vivo), tu siguiente mensaje y el cambio de motor antes de cerrar el
    que se va. Sin texto no se guarda (5 · E2E v4: quedaban respuestas y continuaciones vacías): sus herramientas
    entran con el texto que siga, y mientras tanto el turno en curso las enseña. → los eventos anexados ([] si nada)."""
    import historial_eventos as HE
    if not brain:
        return []
    ruta = _eventos_path(brain)
    with _HIST_LOCK:
        evs = HE.leer(ruta)
        y = _ultimo_envio(evs)
        if not y:
            return []
        hechos = [e for e in evs if e.get("rol") == "agente" and e.get("envio_id") == y["envio_id"]]
        r = _respuesta(brain, y, reg)
        nuevo = _lo_nuevo(r, hechos) if r else None
        if not nuevo or not nuevo["texto"]:
            return []
        t, ts = _ahora_ev()
        e = {"id": "a-%s%s" % (y["envio_id"], "-%d" % (len(hechos) + 1) if hechos else ""), "rol": "agente",
             "texto": _sin_secretos(nuevo["texto"])[:12000], "herr": nuevo["herr"], "motor": y.get("motor") or "",
             "t": t, "ts": ts, "envio_id": y["envio_id"]}
        return HE.anexar(ruta, [e])


def turno_sin_respuesta(brain):
    """¿Tu último mensaje (de hace menos de CERRAR_VENTANA_S) todavía no tiene respuesta en el historial?"""
    import time as _t
    import historial_eventos as HE
    evs = HE.leer(_eventos_path(brain)) if brain else []
    y = _ultimo_envio(evs)
    return bool(y) and _t.time() - float(y.get("t") or 0) < CERRAR_VENTANA_S \
        and not any(e.get("rol") == "agente" and e.get("envio_id") == y["envio_id"] for e in evs)


def _en_curso(brain, evs, reg):
    """El turno en curso: lo que el agente lleva escrito después de tu último mensaje y todavía no está en el historial
    (marcado `vivo`). Solo se enseña: nunca se guarda."""
    y = _ultimo_envio(evs)
    if not y or y.get("motor") != (reg or {}).get("motor"):
        return None
    r = _respuesta(brain, y, reg)
    nuevo = _lo_nuevo(r, [e for e in evs if e.get("rol") == "agente" and e.get("envio_id") == y["envio_id"]]) if r else None
    return {"rol": "agente", "texto": nuevo["texto"], "ts": "", "herr": nuevo["herr"], "vivo": True} if nuevo else None


#: Lo que se contestó a un permiso (pagina_v2 lo guarda con el turno): solo esto pasa a la página.
_DECISIONES_PERMISO = ("permitir", "permitir_siempre", "negar")


def _turno(e):
    t = {"rol": e["rol"], "texto": str(e.get("texto") or ""), "ts": str(e.get("ts") or ""), "herr": e.get("herr") or []}
    for k in ("contexto", "arranque", "cortado"):     # cortado (B11): la página se cerró a media respuesta
        if e.get(k):
            t[k] = True
    permisos = [{"herramienta": _limpio(p.get("herramienta"), 80), "detalle": _limpio(p.get("detalle"), 200),
                 "decision": p["decision"]}
                for p in (e.get("permisos") if isinstance(e.get("permisos"), list) else [])[:10]
                if isinstance(p, dict) and p.get("decision") in _DECISIONES_PERMISO]
    if permisos:
        t["permisos"] = permisos
    return t


def _slot_navegador(brain):
    import sessions_registry
    return (sessions_registry._local_load().get("map") or {}).get(sessions_registry._brain_key(brain), {}).get(NAVEGADOR) or {}


def _historial_al_cambiar(brain, reg, motor):
    """Antes de cerrar el motor que corre (su pantalla todavía se lee): la respuesta a tu último mensaje si faltaba, y el
    evento del motor nuevo. → el motor que se va ("" si no hubo ninguno, o ya iba con ese)."""
    import historial_eventos as HE
    viejo = (reg or {}).get("motor") or ""
    with _HIST_LOCK:
        evs = _eventos(brain, reg)
        if reg:
            try:
                cerrar_turno(brain, reg)
            except Exception:
                pass
            evs = _motor_al_dia(brain, HE.leer(_eventos_path(brain)), viejo)
        tr = _tramos(evs)
        viejo = viejo or (tr[-1][0] if tr else "")
        if viejo == motor:                         # cerrada y ya iba con ese motor: nada que abrir
            return ""
        HE.anexar(_eventos_path(brain), [_ev_sistema("motor", motor)])
    return viejo


def _cambio_fallido(brain, motor):
    """6 (E2E v4): el cambio a `motor` falló después de anotar su evento «motor» (el registro solo anexa: no se borra).
    Se anota que falló: mientras su tramo siga vacío, la página no dice «Siguió con …» (_tramos)."""
    import historial_eventos as HE
    try:
        with _HIST_LOCK:
            HE.anexar(_eventos_path(brain), [_ev_sistema("cambio_fallido", motor)])
    except Exception as x:
        sys.stderr.write("historial: no anoté el cambio fallido (%s)\n" % type(x).__name__)


def _maleta_navegador(brain, motor_viejo):
    """El motor nuevo sigue la MISMA conversación: la maleta de la página lleva los últimos turnos del historial
    único (de todos los motores, uno por renglón), no solo los últimos pedidos del motor que se fue."""
    import memoria
    with _HIST_LOCK:
        filas = [(e.get("motor") or "", e) for e in _eventos(brain) if e.get("rol") != "sistema"
                 and not e.get("arranque") and str(e.get("texto") or "").strip()]
    lineas, largo = [], 0
    for m, t in reversed(filas[-MALETA_TURNOS:]):
        ln = "- %s: %s" % ("Socio" if t.get("rol") == "yo" else m or "agente",
                           memoria._limpio_o_omitido(t.get("texto"), 400 if t.get("rol") == "yo" else 700))
        if largo + len(ln) > MALETA_EXTRACTO:
            break
        lineas.insert(0, ln)
        largo += len(ln) + 1
    if not lineas:
        return False
    lineas.insert(0, "La conversación de la página hasta ahora (todos sus motores; lo último al final):")
    return memoria.poner_seccion(brain, NAVEGADOR_NOMBRE, motor_viejo, lineas, len(filas))


# ── lo que pasó con otros motores, en el mismo renglón de tu mensaje (punto 1 del front pulido) ──
# La maleta solo viaja como contexto de ARRANQUE (el gancho de Claude Code, el AGENTS.md de los demás): un motor que
# retoma su propio hilo puede no recargarlo, y aunque lo tenga no es parte de la conversación. La nota sí: va antes de
# tu mensaje, igual en los 9 motores, una vez por vuelta. H1: ya no se teclea entera (2,4 KB desbordaban la caja de
# Hermes, Kiro, Cursor y OpenCode y se quedaban escritos sin Enter): va en un archivo junto al historial y lo que se
# teclea es UN renglón corto que lo nombra.
CONTEXTO_MAX = 12000        # bytes del archivo de contexto
_CTX_INI, _CTX_FIN = "[Workspace · contexto]", "[fin del contexto]"
_CTX_RE = re.compile(r"^\s*" + re.escape(_CTX_INI) + r".*?" + re.escape(_CTX_FIN) + r"\s*", re.S)


def _sin_nota(turnos):
    """Tu mensaje sin la nota que se le antepuso (queda marcado `contexto`): no se ve en su burbuja ni vuelve a
    entrar en la nota de otro motor."""
    out = []
    for t in turnos:
        if t.get("rol") == "yo" and _CTX_RE.match(str(t.get("texto") or "")):
            t = dict(t, texto=_CTX_RE.sub("", t["texto"], count=1), contexto=True)
        out.append(t)
    return out


def _contexto_path(brain, slug=NAVEGADOR):
    return os.path.join(os.path.dirname(_historial_path(brain)), (slug or NAVEGADOR) + ".contexto.md")


def nota_de_contexto(brain, motor, slug=NAVEGADOR):
    """(renglón, marcar): lo que pasó en la conversación de la página desde el último turno de `motor` —los turnos de
    los OTROS motores después de su segmento anterior; si nunca estuvo, todo lo de antes— en el archivo de contexto
    (hasta CONTEXTO_MAX bytes; entra lo más reciente), y el renglón corto que se teclea antes de tu mensaje para que lo
    lea (su ruta desde el cerebro, donde corre el motor). ("", None) si no hay nada, ya se le contó en esta vuelta o
    el archivo no se pudo escribir. `marcar()` lo deja contado: se llama solo si de verdad se tecleó."""
    import atomico
    import motores_logica
    import memoria
    if not (brain and motor):
        return "", None
    with _HIST_LOCK:
        if slug == NAVEGADOR:
            tr = _tramos(_motor_al_dia(brain, _eventos(brain), motor))
        else:                                      # H4-a: la de otra pestaña (la que siguió de otra con otro motor)
            tr = _tramos(_motor_al_dia(brain, _eventos(brain, slug=slug), motor, slug))
        if not tr or tr[-1][0] != motor or tr[-1][2]:
            return "", None
        previo = max([i for i, s in enumerate(tr[:-1]) if s[0] == motor] or [-1])
        filas = [(s[0], t) for s in tr[previo + 1:-1] for t in s[1]
                 if not t.get("arranque") and str(t.get("texto") or "").strip()]
    cab = ("# Lo que pasó en esta conversación con otros motores\n\nMientras no estabas, la conversación de la página "
           "siguió con otros motores (lo más reciente al final). Es contexto de esta conversación: tenlo en cuenta al "
           "contestar.\n\n")
    resto = CONTEXTO_MAX - len(cab.encode("utf-8")) - 40          # 40: «(antes hubo N turnos más)»
    piezas, largo = [], 0
    for m, t in reversed(filas):
        yo = t.get("rol") == "yo"
        p = "- %s: «%s»" % ("Socio" if yo else motores_logica.engine_name(m),
                            memoria._limpio_o_omitido(str(t.get("texto")), 1200 if yo else 2400))
        n = len(p.encode("utf-8")) + 1
        if largo + n > resto:
            break
        piezas.insert(0, p)
        largo += n
    if not piezas:
        return "", None
    antes = len(filas) - len(piezas)
    ruta = _contexto_path(brain) if slug == NAVEGADOR else _contexto_path(brain, slug)
    try:
        atomico.escribir(ruta, cab + ("(antes hubo %d turnos más)\n\n" % antes if antes else "") + "\n".join(piezas) + "\n")
    except OSError:
        return "", None
    rel = os.path.relpath(ruta, str(brain)).replace(os.sep, "/")

    def marcar():
        import historial_eventos as HE
        with _HIST_LOCK:
            HE.anexar(_eventos_path(brain) if slug == NAVEGADOR else _eventos_path(brain, slug),
                      [_ev_sistema("contexto", motor)])
    return "%s Contexto de lo que pasó con otros motores: lee %s antes de contestar. %s" % (_CTX_INI, rel, _CTX_FIN), marcar


def _con_nota(agente, slug, reg, texto):
    """(lo que se teclea, marcar): en la conversación de la página, la nota de contexto antes de tu texto."""
    if slug != NAVEGADOR or not reg:
        return texto, None
    try:
        nota, marcar = nota_de_contexto(_cerebro(agente), reg.get("motor") or "")
    except Exception:
        return texto, None
    return (nota + " " + texto if nota else texto), marcar


TECLEADO = ("ok", "sin_eco", "atorado")       # lo que _escribir_en_caja da cuando el texto ya se tecleó en su panel


def _nota_dicha(r, marcar):
    """La nota de contexto queda contada si se tecleó, aunque tu mensaje no saliera (`sin_eco`, `atorado`): se quedó
    escrita en su caja y sale con «Darle Enter» o con lo siguiente. F5 (E2E v4): cada reintento volvía a llevarla y en
    su caja se juntaban dos. UNA vez por vuelta."""
    if marcar and r in TECLEADO:
        marcar()


def _conversacion_navegador(agente, brain, reg):
    """La conversación de la página: sus eventos en orden (lo guardado) y, al final, el turno en curso si su motor lleva
    algo escrito (`vivo`: solo se enseña). `motores` dice desde qué turno va cada motor; `total` cuenta también lo que
    pasó al archivo viejo (los índices no se corren)."""
    import historial_eventos as HE
    vivo = reg.get("motor") if reg and _estado_rapido(reg).get("ok") else ""
    c = _CAMBIOS.get((agente, NAVEGADOR))
    en_cambio = c and c["paso"] not in ("listo", "error") and vivo != c["motor"]
    a_la_vista = reg if vivo and not en_cambio else None    # a medio cambio, el motor que se va no abre otro tramo
    with _HIST_LOCK:
        evs = _eventos(brain, a_la_vista)
        if a_la_vista:
            evs = _motor_al_dia(brain, evs, vivo)
    if not evs:
        return {"soporta": False, "motor": "", "vivo": False}
    base = HE.antes_de(_eventos_path(brain))
    turnos, motores = [], []
    for m, es, _contado, fallido in _tramos(evs):
        if fallido:
            continue                               # 6: el cambio a ese motor falló y no se le habló: sin «Siguió con …»
        motores.append({"i": base + len(turnos), "motor": _recorta(m, 30)})
        turnos += [_turno(e) for e in es]
    en_curso = _en_curso(brain, evs, a_la_vista) if a_la_vista else None
    if en_curso:
        turnos.append(en_curso)
    return {"soporta": True, "fuente": "historial", "motor": vivo or (motores[-1]["motor"] if motores else ""),
            "vivo": bool(vivo), "total": base + len(turnos), "turnos": turnos[-MAX_TURNOS:], "motores": motores}


_CONV_V = {}                # (agente, slug) → [(v, total, firmas por turno)]: las últimas versiones que se mandaron
CONV_VERSIONES = 4


def con_version(agente, slug, d, v_pagina=""):
    """La conversación con su versión `v` y `desde` (índice absoluto de su primer turno). Si la página ya
    tiene la versión `v_pagina`: sin cambios, solo {"v", "igual": true}; con cambios, solo los turnos
    desde el primero que cambió (antes se mandaba entera cada 1,5 s: ~300 KB). La página pega lo nuevo
    sobre lo que tenía y se queda con los últimos `n`."""
    import hashlib

    def h(x):
        return hashlib.sha1(json.dumps(x, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    turnos = d.get("turnos") or []
    firmas = [h(t) for t in turnos]
    total = d.get("total", len(turnos))
    v = h([{k: x for k, x in d.items() if k != "turnos"}, firmas])
    base = total - len(turnos)
    hist = _CONV_V.setdefault((agente, slug), [])
    previa = next((x for x in hist if x[0] == v_pagina), None) if v_pagina else None
    if not hist or hist[-1][0] != v:
        hist.append((v, total, firmas))
        del hist[:-CONV_VERSIONES]
    if len(_CONV_V) > 200:
        _CONV_V.clear()
    if v_pagina == v:
        return {"v": v, "igual": True}
    out = dict(d, v=v, desde=base, n=len(turnos))
    if previa and previa[1] - len(previa[2]) <= base:          # la página tiene todo lo de antes de `base`
        base_p = previa[1] - len(previa[2])
        i = base
        while i < previa[1] and i - base < len(firmas) and previa[2][i - base_p] == firmas[i - base]:
            i += 1
        out["desde"], out["turnos"] = i, turnos[i - base:]
    return out


def datos_conversacion(agente, slug):
    """Los turnos de la pestaña (los últimos MAX_TURNOS).
    Manda el motor que corre AHORA: su transcripción si la hay; si no (motor sin
    transcripción legible, o recién cambiado), lo que muestra su pantalla, y la
    historia con el motor anterior va antes, marcada (`previo`). Nunca se presenta la
    transcripción de otro motor como si fuera la actual.
    {"soporta": False} si no hay nada que mostrar."""
    import sessions_registry
    bt, reg = _pestana_y_panel(agente, slug)
    if bt is None:
        return None
    brain = _cerebro(agente)
    if slug == NAVEGADOR:
        return _conversacion_navegador(agente, brain, reg)
    slot = (sessions_registry._local_load().get("map") or {}).get(sessions_registry._brain_key(brain), {}).get(slug) or {}
    vivo = reg.get("motor") if reg and _estado_rapido(reg).get("ok") else ""
    rutas = {}
    for m in _CONV_MOTORES:
        r = _transcripcion(m, slot.get(m))
        if r:
            rutas[m] = r
    if vivo and rutas.get(vivo):
        turnos = _sin_arranques(_turnos_transcripcion(vivo, rutas[vivo]))
        return {"soporta": True, "fuente": "transcripcion", "motor": vivo, "vivo": True,
                "total": _podados(rutas[vivo]) + len(turnos), "turnos": turnos[-MAX_TURNOS:]}
    # la historia más reciente de otro motor (contexto, no «lo actual»)
    previo_m = max(rutas, key=lambda m: os.path.getmtime(rutas[m])) if rutas else ""
    if vivo:
        pantalla = _pantalla_de(reg)
        turnos = _sin_arranques(_de_pantalla(_sin_pregunta(pantalla), vivo, _tecleados(reg)) if pantalla else [])
        previos = _sin_arranques(_turnos_transcripcion(previo_m, rutas[previo_m]))[-MAX_PREVIOS:] if previo_m else []
        out = {"soporta": True, "fuente": "pantalla", "motor": vivo, "vivo": True,
               "total": len(turnos), "turnos": turnos}
        if previos:
            out["previo"] = {"motor": previo_m, "turnos": previos}
        return out
    if previo_m:
        turnos = _sin_arranques(_turnos_transcripcion(previo_m, rutas[previo_m]))
        return {"soporta": True, "fuente": "transcripcion", "motor": previo_m, "vivo": False,
                "total": _podados(rutas[previo_m]) + len(turnos), "turnos": turnos[-MAX_TURNOS:]}
    turnos = _de_maleta(brain, bt.get("name") or "")
    if turnos:
        return {"soporta": True, "fuente": "maleta", "motor": "", "vivo": False,
                "total": len(turnos), "turnos": turnos}
    return {"soporta": False, "motor": "", "vivo": False}


# ── usar una skill: el agente la toma sola y su avance se ve en vivo (pasos.py) ──
MAX_ARCHIVO = 20 * 1024 * 1024       # bytes de un archivo que el socio sube para una skill
_ARCH_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def _skill_de(agente, nombre):
    """(ruta relativa del SKILL.md desde el cerebro, nombre) o (None, None)."""
    import skill_meta
    brain = dict(_cerebros()).get(agente)
    if not brain:
        return None, None
    raiz = os.path.join(str(brain), "skills")
    for d in skill_meta.iter_skill_dirs(raiz) if os.path.isdir(raiz) else []:
        fm = _frontmatter_skill(os.path.join(d, "SKILL.md"))
        if (fm.get("name") or os.path.basename(d)) == nombre:
            return os.path.relpath(os.path.join(d, "SKILL.md"), str(brain)).replace(os.sep, "/"), nombre
    return None, None


#: skills-cierre · decisión del 22-nov: lo mismo en la instrucción, en usar_skill (interfaz_agente.como_seguir) y en
#: la guía de chat (modo_chat.guia). pasos.aplicar no deja reabrir lo pendiente aunque el modelo lo intente.
NO_REPREGUNTES = ("cada turno dentro de la skill termina con pide o con fin; si mientras esperas te escribe otra cosa, "
                  "contéstale solo eso, sin volver a preguntar: queda en pausa hasta que pulse «Seguir».")


def _lead_seguir(nombre, rel, ejecucion, seguir):
    """skills-cierre · «Seguir» de una skill que se detuvo: la primera frase de su instrucción."""
    paso = int((seguir or {}).get("paso") or 0)
    pend = " ".join(str((seguir or {}).get("pendiente") or "").split())[:80]   # «Seguir» va por la capa de control
    return ("Sigue con tu skill «%s» (%s), ya está activada: se detuvo%s%s; retómala ahí." % (
        nombre, rel, (" en el paso %d" % paso) if paso else "", (" y quedó pendiente: «%s»" % pend) if pend else ""))


#: Hasta aquí la instrucción del comando va entera (Codex pega como adjunto lo de ~1000 caracteres o más).
_INSTRUCCION_TOPE = 900


def _instruccion(ejecucion, nombre, rel, texto, motor="", seguir=None, con_nucleo=None):
    """Lo que se le manda al agente para usar una skill: un solo renglón. El avance va con `workspace pasos <id> …`
    (Windows: `workspace.cmd pasos`), un comando de Workspace preaprobado como `workspace memoria`
    (memoria.permisos_pasos_claude). N2 (prueba de punta a punta v3, 17-nov): con «P = python3 "<ruta>/pasos.py" <id>
    (donde diga P, usa ese comando completo)» Claude Code armó `P() { python3 … }; P plan …`, y esa forma pide permiso
    siempre. Por eso el comando entero en cada paso, y la regla de usarlo solo, en una línea.
    skills-cierre (Fix 4): `con_nucleo` = ¿la sesión que la recibe trae el núcleo (MCP workspace)? Lo dice la página
    con SU sesión (pagina_v2.herramientas_de): con él, la herramienta reportar_avance (no pide permiso; antes OpenCode
    pedía permiso en cada paso del comando) y el comando de respaldo; sin él, el comando. Sin saberlo (None: la
    instrucción tecleada en un panel), la regla de antes: la herramienta en los que preguntan por cada comando de su
    terminal (memoria_mcp.MOTORES), aprobada por nombre (H13). Las mismas reglas que la guía y que usar_skill: ya está
    activada (no otra vez: Cursor la duplicaba), una llamada a la vez (Copilot y OpenCode en paralelo), dentro de la
    skill se pregunta solo con su «pide» y ahí termina el turno, y cada turno dentro de ella termina con pide o fin.
    `seguir` ({paso, pendiente}): «Seguir» de una que se detuvo."""
    cmd = "%s pasos %s" % ("workspace.cmd" if sys.platform == "win32" else "workspace", ejecucion)
    solo = ("usa SIEMPRE el comando completo %s … en una sola línea, sin variables ni funciones ni encadenarlo."
            % cmd)
    pedido = (" para esto: %s." % texto) if texto else "."
    if con_nucleo is None:
        try:
            import memoria
            import memoria_mcp
            con_nucleo = memoria.normalizar_motor(motor) in memoria_mcp.MOTORES
        except Exception:
            con_nucleo = False
    if con_nucleo:
        lead = (_lead_seguir(nombre, rel, ejecucion, seguir) + " No llames usar_skill." if seguir is not None else
                "Usa tu skill «%s» (%s)%s Ya está activada (ejecucion \"%s\"): no llames usar_skill." % (
                    nombre, rel, pedido, ejecucion))
        return ("%s Reporta con tu herramienta de Workspace reportar_avance (no pide permiso), una llamada a la vez, "
                "ejecucion \"%s\": al empezar, accion plan con pasos [\"paso 1\", \"paso 2\"…]; en cada paso, ahora "
                "con n y al terminarlo, hecho con n; para preguntarle algo al socio, solo accion pide con texto y "
                "opciones (archivo true si es un archivo) y termina tu turno ahí; al final, fin con el resumen en una "
                "línea: %s Sin esa herramienta, el comando completo %s … (solo y en una línea)."
                % (lead, ejecucion, NO_REPREGUNTES, cmd))
    lead = (_lead_seguir(nombre, rel, ejecucion, seguir) if seguir is not None else
            "Usa tu skill «%s» (%s)%s Ya está activada: no la actives otra vez." % (nombre, rel, pedido))
    # corta a propósito: con ~1000 caracteres, Codex lo pegaba como «[Pasted Content]» y el Enter no lo mandaba
    def armar(regla):
        return ("%s Reporta, un comando a la vez: %s Al empezar, %s plan \"paso 1\" \"paso 2\"…; en cada paso, %s "
                "ahora N y luego %s hecho N; para preguntarle algo, solo %s pide \"¿…?\" --opcion \"A\" --opcion "
                "\"B\" (--archivo para un archivo) y termina tu turno ahí; al final, %s fin \"resumen\": %s"
                % (lead, regla, cmd, cmd, cmd, cmd, cmd, NO_REPREGUNTES))
    linea = armar(solo)
    if len(linea) >= _INSTRUCCION_TOPE:
        # Windows (`workspace.cmd`, 4 letras más cada vez) o una skill/pedido largos: la regla no repite el comando;
        # cada paso de abajo lo sigue llevando entero.
        linea = armar("usa SIEMPRE el comando completo, en una sola línea, sin variables ni funciones ni encadenarlo.")
    return linea


def usar_skill(agente, nombre, texto="", slug="", motor=""):
    """Prepara la ejecución y, si la pestaña ya está viva, le escribe la instrucción.
    Si está cerrada, se abre (con `motor`, o el del agente si va vacío) y la instrucción
    sale al arrancar. Sin `slug`, en la conversación de la página: nunca en una pestaña
    aparte que nadie ve. En una pestaña viva manda su motor."""
    import datetime as _dt
    import secrets as _s
    import pasos
    rel, nombre = _skill_de(agente, nombre)
    if not rel:
        return "no_existe", None
    texto = " ".join(str(texto or "").split())[:600]
    brain = dict(_cerebros()).get(agente)
    ejecucion = "s-%s-%s" % (_dt.datetime.now().strftime("%Y%m%d%H%M%S"), _s.token_hex(2))
    slug = slug or NAVEGADOR
    bt, reg = _pestana_y_panel(agente, slug)
    if bt is None and slug != NAVEGADOR:                 # la del navegador se crea al abrirla
        return "no_existe", None
    vivo = bool(reg) and bool(_estado_rapido(reg, fresco=True).get("ok"))
    if not vivo:
        r = abrir_pestana(agente, slug, motor)          # cerrada: se abre aquí y la skill sale al arrancar
        if r not in ("abriendo", "ya"):
            return r, None
    import memoria
    # el motor con que se pidió (el de su panel vivo, o el elegido al abrirla; vacío = el que abra): la
    # instrucción es para ESE (H13: una de Codex le llegó a Cursor 15 min después)
    motor_pedido = memoria.normalizar_motor(reg.get("motor") if vivo else motor)
    pasos.guardar(ejecucion, {"id": ejecucion, "skill": nombre, "ruta": rel, "agente": agente, "pestana": slug,
                              "motor": motor_pedido,
                              "texto": texto, "estado": "arrancando", "pasos": [], "pide": None,
                              "creado": _dt.datetime.now().isoformat(timespec="seconds")}, brain)
    if _escribir_ejecucion(agente, ejecucion) == "ok":
        return "ok", {"id": ejecucion, "slug": slug, "arrancada": True}
    # sesión nueva: el servidor espera a que arranque y le da la instrucción él mismo
    # (no depende de que la página siga abierta); la página puede intentarlo también: no se duplica
    _en_segundo_plano(_arrancar_cuando_quieta, agente, ejecucion)
    return "ok", {"id": ejecucion, "slug": slug, "arrancada": False}


ARRANQUE_TOPE_S = 1800      # cuánto espera el servidor a que la sesión quede lista (puede estar
                            # preguntándote algo: «¿confías en esta carpeta?», un permiso…)


def _en_segundo_plano(fn, *args, **kwargs):
    """Un hilo de fondo (los que esperan a que una pestaña quede lista)."""
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()
_ARRANQUE_LOCK = threading.Lock()


def _caja_lista(reg, previa=None, info=None):
    """Una vuelta de los hilos que esperan para teclear: (¿lista?, firma de la pantalla).
    Lista = el panel vivo y quieto, sin un menú en pantalla (diga lo que diga herdr: el menú
    manda) y con su CAJA DE CHAT al pie (F14: un motor que arranca está quieto y sin menú, pero
    todavía no en su caja). Si herdr no reconoce al motor (OpenClaw, Hermes: quieto
    `por_pantalla`), además su pantalla debe ser la misma que en la vuelta anterior (`previa`).
    En `info` deja por qué no está lista («pregunta», «trabajando», «sin_caja»; "" si no se sabe) y su pantalla."""
    from pantalla_motor import caja_de_entrada, dialogo_al_pie
    info = {} if info is None else info
    info["por"] = ""
    ep = _estado_rapido(reg, fresco=True) if reg else {}
    if not (ep.get("ok") and ep.get("quieto") and not ep.get("menu")):
        info["por"] = "" if not ep.get("ok") else "pregunta" if ep.get("menu") else "trabajando"
        return False, ep.get("firma")
    vis = info["vis"] = _leer_panel(reg, 60, "visible")
    if vis is None or pregunta_de(vis) or caja_de_entrada(vis) is None:
        info["por"] = "" if vis is None else "pregunta" if pregunta_de(vis) or dialogo_al_pie(vis) else "sin_caja"
        return False, ep.get("firma")
    if ep.get("por_pantalla"):
        return bool(ep.get("firma")) and ep.get("firma") == previa, ep.get("firma")
    return True, ep.get("firma")


_PEGADO_RE = re.compile(r"\[Pasted (?:Content|text)[^\]]*\]", re.I)


def _se_ve(caja, texto):
    """¿Lo tecleado está en la caja? Su principio o su cola (sin espacios: el motor parte el renglón; en una caja
    que no cabe, el principio se corre arriba), o la marca «[Pasted Content N chars]» con que Codex junta un texto
    largo. Se mira el bloque entero de la caja, no solo su primer renglón. Una caja vacía no tiene eco: un texto
    partido deja su primer trozo en el renglón del prompt, y «[Pasted…]» también es texto."""
    if not (caja or {}).get("texto"):
        return False
    t = caja.get("bloque") or caja["texto"]
    plano, junto = re.sub(r"\s+", "", texto), re.sub(r"\s+", "", t)
    return bool(t) and bool(plano) and (plano[:24] in junto or plano[-24:] in junto or bool(_PEGADO_RE.search(t)))


def _su_motor_corre(reg):
    """¿Al frente de su panel corre su motor? herdr puede seguir etiquetando el panel con un motor que ya salió a la
    shell, y la pantalla no lo distingue (el `❯ ` de Starship/Pure/Powerlevel10k o el `> ` de continuación parecen
    su caja): manda el proceso. En Windows `process-info` solo ve la shell: ahí queda lo que herdr reconoce."""
    import aviso_panel
    if os.name == "nt":
        # shortcut: en Windows manda la etiqueta de herdr (process-info solo ve la shell), revisar cuando herdr exponga el proceso del panel
        return True
    pi = aviso_panel._herdr(["pane", "process-info", "--pane", reg["panel"]], reg.get("socket", ""))
    return aviso_panel.motor_corre((pi or {}).get("process_info"), reg.get("motor", ""))


def _escribir_en_caja(reg, texto, forzar=False, juntar=False):
    """Teclea `texto` + Enter SOLO en la caja de chat del motor (F14: el Enter de la página eligió «Update now» de
    Codex). Bajo el candado del panel (el mismo de los avisos de sala): (0) al frente corre su motor, no la shell;
    (1) al pie tiene que verse su caja, sin menú ni diálogo, y quieto (salvo `forzar`: el motor lo encola); (2)
    tecleado el texto, tiene que verse en la caja o no se da Enter; (3) tras el Enter, tiene que haber salido de la
    caja (F9: OpenClaw lo dejaba escrito).
    `juntar` es «Mandar igual» de la cola (lo pidió el socio viendo lo que hay): con otro texto en su caja se teclea
    detrás y salen juntos; sin una caja que se reconozca, se teclea en lo que enseña (sin diálogo ni menú) y solo hay
    Enter si aparece al pie (_enter_sin_caja).
    → "ok" | "pregunta" | "trabajando" | "sin_caja" | "caja_ocupada" (ya tiene texto) | "sin_eco" (tecleado, sin
    Enter) | "atorado" | "cerrado" | "panel"."""
    import time as _t
    import aviso_panel
    from pantalla_motor import caja_de_entrada, dialogo_al_pie
    r = {}

    def teclear(t, despues):
        if aviso_panel.teclear(reg["panel"], t, reg.get("socket", "")) is None:
            return "panel"
        # un texto largo llega como «pegado»: si el Enter cae dentro de esa ráfaga, no lo manda (aviso_panel.escribir)
        _t.sleep(aviso_panel.PAUSA_ENTER_S + min(0.85, len(t) / 2000.0))
        return despues()

    def hacer():
        ep = aviso_panel.estado_panel(reg)
        vis = _leer_panel(reg, 60, "visible") if ep.get("ok") else None
        if vis is None:
            r["r"] = "panel"
        elif ep.get("menu") or pregunta_de(vis):
            r["r"] = "pregunta"
        elif not ep.get("quieto") and not forzar:
            r["r"] = "trabajando"
        elif not _su_motor_corre(reg):
            r["r"] = "cerrado"
        elif caja_de_entrada(vis) is None:
            if not juntar:
                r["r"] = "sin_caja"
            elif dialogo_al_pie(vis):
                r["r"] = "pregunta"
            elif _se_ve(_pie_como_caja(vis), texto):
                r["r"] = "sin_caja"                    # ya se ve al pie: no se sabría si lo tecleado llegó
            else:
                r["r"] = teclear(texto, lambda: _enter_sin_caja(reg, texto))
        elif caja_de_entrada(vis)["texto"] and not juntar and _caja_con_texto_de_verdad(reg):
            r["r"] = "caja_ocupada"                    # F9: lo de antes + esto saldrían juntos en un Enter
        else:
            junto = juntar and bool(caja_de_entrada(vis)["texto"])
            r["r"] = teclear(" " + texto if junto else texto, lambda: _enter_si_se_ve(reg, texto))
        if r["r"] in ("ok", "atorado"):
            _recordar_tecleado(reg, texto)
        return True
    if not _en_el_panel(reg, hacer):
        return r.get("r") or "panel"
    return r["r"]


_TECLEADOS = {}             # panel → los últimos textos que la página le mandó (H11: anclan tus mensajes en su pantalla)
TECLEADOS_MAX = 40


def _recordar_tecleado(reg, texto):
    lista = _TECLEADOS.setdefault((reg or {}).get("panel") or "", [])
    lista.append(texto)
    del lista[:-TECLEADOS_MAX]
    if len(_TECLEADOS) > 200:
        _TECLEADOS.pop(next(iter(_TECLEADOS)))


def _tecleados(reg):
    return tuple(_TECLEADOS.get((reg or {}).get("panel") or "", ()))


def _eco(pantalla, texto):
    """¿Se ve `texto` en su caja? Partido en renglones sube el prompt: se busca un renglón más arriba por cada 30
    caracteres (holgado para un panel angosto), sin pasar de la regla de arriba de su caja."""
    from pantalla_motor import caja_de_entrada
    return _se_ve(caja_de_entrada(pantalla or "", alto=len(texto) // 30 + 1), texto)


ENTER_SALE_S = 1.5          # lo que se espera a que un texto corto salga de su caja tras el Enter
ECO_ESPERA_S = 3.0          # lo que se espera a ver lo tecleado en su caja antes del Enter (se mira cada ECO_PASO_S)
ECO_PASO_S = 0.25


def _enter_si_se_ve(reg, texto):
    """Pasos (2) y (3) de _escribir_en_caja, ya bajo el candado: Enter SOLO si `texto` se ve en su caja (sin menú ni
    diálogo: caja_de_entrada da None con ellos), y luego, ¿salió de la caja? → "ok" | "sin_eco" | "atorado" | "panel".
    H8: Antigravity y Copilot tardan más de 1,5 s en vaciar su caja con un texto largo; lo recibían y trabajaban, pero
    la página decía «atorado» (y su «Darle Enter» habría mandado un Enter de más). La espera crece con el largo (+1 s
    por cada 500 caracteres, hasta 6 s en total) y, si su motor ya se ve trabajando, salió.
    F5 (E2E v4): lo tecleado tampoco se pinta al instante: tras un cambio, OpenCode lo enseñó en su caja después de la
    única mirada (a los 0,25 s) y cada mensaje quedaba `sin_eco`, escrito y sin Enter. Se mira hasta ECO_ESPERA_S."""
    import time as _t
    import aviso_panel

    def se_ve():
        return _eco(_leer_panel(reg, 60, "visible"), texto)
    hasta = _t.time() + ECO_ESPERA_S
    while not se_ve():
        if _t.time() >= hasta:
            return "sin_eco"                           # no está en su caja (salió un menú, otra pantalla): sin Enter
        _t.sleep(ECO_PASO_S)
    if aviso_panel._herdr(["pane", "send-keys", reg["panel"], "Enter"], reg.get("socket", ""), json_out=False) is None:
        return "panel"
    for i in range(int((ENTER_SALE_S + min(4.5, len(texto) / 500.0)) / 0.25)):
        _t.sleep(0.25)
        if not se_ve():
            return "ok"
        if i % 4 == 3 and aviso_panel.estado_panel(reg).get("quieto") is False:
            return "ok"                                # su motor ya trabaja: lo recibió
    return "atorado"


def _pie_como_caja(pantalla):
    """Sus últimos renglones como si fueran su caja (para _se_ve), cuando no hay una caja que se reconozca."""
    from pantalla_motor import al_pie
    t = " ".join(al_pie(pantalla or "", 6))
    return {"texto": t, "bloque": t}


def _enter_sin_caja(reg, texto):
    """«Mandar igual» sin una caja que se reconozca, ya bajo el candado y tecleado (antes no se veía al pie): Enter solo
    si lo tecleado aparece al pie y no salió un menú, un diálogo ni una pregunta. Sin caja no se puede ver si salió de
    ella: se da por mandado si su pantalla cambió tras el Enter. → "ok" | "sin_eco" | "atorado" | "panel"."""
    import time as _t
    import aviso_panel
    from pantalla_motor import dialogo_al_pie
    vis = _leer_panel(reg, 60, "visible")
    if vis is None or pregunta_de(vis) or dialogo_al_pie(vis) or not _se_ve(_pie_como_caja(vis), texto):
        return "sin_eco"
    if aviso_panel._herdr(["pane", "send-keys", reg["panel"], "Enter"], reg.get("socket", ""), json_out=False) is None:
        return "panel"
    for _ in range(6):
        _t.sleep(0.25)
        if _leer_panel(reg, 60, "visible") not in (None, vis):
            return "ok"
    return "atorado"


def _lo_que_tiene_su_caja(reg):
    """Lo escrito de verdad en su caja (sin la sugerencia gris del motor), entero aunque ocupe varios renglones: lo que
    la burbuja en cola enseña («Su caja tiene: …»)."""
    from pantalla_motor import caja_de_entrada, sin_tenue
    a = _leer_ansi(reg)
    c = caja_de_entrada(sin_tenue(a)) if a is not None else caja_de_entrada(_leer_panel(reg, 60, "visible") or "")
    return (c.get("bloque") or c["texto"]) if c and c.get("texto") else ""


_ATORADO = {}               # agente → (cid, lo tecleado, tu texto): lo que se quedó escrito en su caja sin salir («Darle Enter»)


def _enter_en_caja(reg, texto):
    """«Darle Enter» a lo que se quedó escrito en su caja (`atorado`), nunca un Enter crudo: bajo el candado del panel,
    su motor corre, no hay menú ni diálogo y en su caja se ve ESE texto; solo entonces Enter (F14: entre el «atorado» y
    el clic el motor pudo pintar un menú). → "ok" | "pregunta" | "sin_eco" | "atorado" | "cerrado" | "panel"."""
    import aviso_panel
    r = {}

    def hacer():
        ep = aviso_panel.estado_panel(reg)
        vis = _leer_panel(reg, 60, "visible") if ep.get("ok") else None
        if vis is None:
            r["r"] = "panel"
        elif ep.get("menu") or pregunta_de(vis):
            r["r"] = "pregunta"
        elif not _su_motor_corre(reg):
            r["r"] = "cerrado"
        else:
            r["r"] = _enter_si_se_ve(reg, texto)
        return True
    if not _en_el_panel(reg, hacer):
        return r.get("r") or "panel"
    return r["r"]


def _detenida_en_la_pagina(agente, ejecucion):
    """¿El socio tocó «Detener» en la página para esta ejecución? (sus preferencias de esta computadora:
    localhost_front, «detenidas»). Falla-suave: False."""
    try:
        import localhost_front as LF
        return ejecucion in (LF._prefs_de(LF.leer_prefs(), agente).get("detenidas") or [])
    except Exception:
        return False


def _arrancar_cuando_quieta(agente, ejecucion, tope=ARRANQUE_TOPE_S, pausa=3.0, espera_inicial=8.0):
    """Hilo: espera a que la pestaña nueva termine de arrancar (dos lecturas quietas
    seguidas, para no teclear encima del arranque del cerebro) y escribe la instrucción."""
    import time as _t
    import pasos
    t0, quietas, firma = _t.time(), 0, None
    _t.sleep(espera_inicial)
    while _t.time() - t0 < tope:
        try:
            d = pasos.leer(ejecucion, dict(_cerebros()).get(agente))
            if not d or d.get("estado") != "arrancando" or _detenida_en_la_pagina(agente, ejecucion):
                return
            bt, reg = _pestana_y_panel(agente, d.get("pestana") or "")
            libre, firma = _caja_lista(reg, firma)
            quietas = quietas + 1 if libre else 0
            # H4/H13: si su panel ya corre otro motor, esta instrucción no es para él: se deja de esperar
            if quietas >= 2 and _escribir_ejecucion(agente, ejecucion) in ("ok", "otro_motor"):
                return
        except Exception:
            pass
        _t.sleep(pausa)


_COLA = {}                  # (agente, slug) → [{"cid", "texto", "t", "motivo", "motivo_t"[, "salida", "caja", "forzar"]}]:
                            # lo que espera su caja, EN ORDEN
_COLA_HILO = set()          # (agente, slug) con su hilo vaciando la cola (uno por conversación: sale en orden)
_COLA_LOCK = threading.Lock()
ABRIR_GRACIA_S = 90         # tras abrirla, cuánto puede tardar el motor en aparecer en su panel antes de «no se mandó»
COLA_SALIDA_S = 20          # en cola por su caja (con otro texto, o sin caja a la vista) más de esto: la burbuja enseña
                            # lo que hay y ofrece «Mandar igual» (nada se queda en cola sin salida)
CAJA_RELEER_S = 5           # lo que enseña de su caja se renueva a lo más cada esto (un reloj al pie no la repinta)


def cola_de(agente, slug=None):
    """Lo que espera en la cola de su conversación (para su foto), en orden: [{"id", "texto", "motivo", "desde"
    [, "salida": True, "caja"]}]. `desde`: cuándo entró (la página dice cuánto lleva). Detrás del primero, el motivo es
    que va después de los anteriores. `salida`: «Mandar igual» se puede (ver COLA_SALIDA_S); `caja`, lo que hay en su
    caja o, sin caja a la vista, al pie de su pantalla."""
    with _COLA_LOCK:
        out = []
        for i, e in enumerate(_COLA.get((agente, slug or NAVEGADOR)) or []):
            x = {"id": e["cid"], "texto": _limpio(e["texto"], 300), "motivo": "detras" if i else e.get("motivo", ""),
                 "desde": round(e["t"], 3)}
            if e.get("salida") and not i:
                x.update(salida=True, caja=_limpio(e.get("caja"), 300))
            out.append(x)
        return out


def forzar_en_cola(agente, slug, cid):
    """«Mandar igual» el mensaje que espera por su caja (ofrecido en `salida`): en la siguiente vuelta de su hilo se
    teclea aunque su caja tenga otro texto (salen juntos) o no se vea (_escribir_en_caja con `juntar`). Una vez: si no
    sale, la cola lo dice. → "ok" | "no_esta" | "tecleando" | "no_toca" (ya no espera por su caja)."""
    with _COLA_LOCK:
        cola = _COLA.get((agente, slug)) or []
        e = next((x for x in cola if x["cid"] == cid and not x.get("cancelado")), None)
        if e is None:
            return "no_esta"
        if e.get("tecleando"):
            return "tecleando"
        if e is not cola[0] or not e.get("salida"):
            return "no_toca"
        e["forzar"] = True
    return "ok"


def quitar_de_cola(agente, slug, cid):
    """«Quitar» un mensaje que espera en la cola: el de en medio sale ya; el primero, en la siguiente vuelta de su
    hilo. → "ok" | "tecleando" (ya se está mandando: no se quita, y lo que pase se dice) | "no_esta"."""
    with _COLA_LOCK:
        cola = _COLA.get((agente, slug)) or []
        e = next((x for x in cola if x["cid"] == cid), None)
        if e is None:
            return "no_esta"
        if e.get("tecleando"):
            return "tecleando"
        e["cancelado"] = True
        if e is not cola[0]:
            cola.remove(e)
    _vivo().envio(agente, cid, "quitado")
    return "ok"


def _no_salio(agente, slug, cid, como):
    """Lo que no se pudo mandar: la página lo dice (no se queda «Pensando…», F16)."""
    if cid:
        _vivo().envio(agente, cid, como)
    return False


def _escribir_cuando_quieta(agente, slug, texto, tope=ARRANQUE_TOPE_S, pausa=1.0, espera_inicial=0.0, cid="", motivo=""):
    """La cola: lo que el socio mandó y todavía no se puede teclear (la pestaña se abre, el motor arranca o trabaja,
    te pregunta algo) se teclea SOLO en su caja de chat, cuando dos lecturas seguidas la ven lista, en orden y una
    vez (un hilo por conversación). La página ve en qué va cada uno (`motivo`, de entrada el que lo dejó en cola);
    nada rebota ni desaparece (F8). No depende de que la página siga abierta. Si su motor se cierra o pasa el tope:
    «no se mandó» (F16). Con `cid` se forma en la cola de la página; sin él (otras pestañas) es un envío suelto."""
    import time as _t
    k = (agente, slug)
    if cid:
        with _COLA_LOCK:
            ahora, m = _t.time(), _motivo_en_cola(k, motivo) if not _COLA.get(k) else ""    # detrás de otros, aún nada
            _COLA.setdefault(k, []).append({"cid": cid, "texto": texto, "t": ahora, "motivo": m, "motivo_t": ahora})
            if k in _COLA_HILO:
                return True                             # ya hay un hilo vaciándola: sale después de los de antes
            _COLA_HILO.add(k)
        _vivo().envio(agente, cid, "en_cola", motivo=m)
        todos = True
        try:
            _t.sleep(espera_inicial)
            while True:
                with _COLA_LOCK:
                    if not _COLA.get(k):
                        _COLA.pop(k, None)
                        return todos
                    e = _COLA[k][0]
                ok = _mandar_uno(agente, slug, e["texto"], e["cid"], tope, pausa, e)
                todos = todos and ok
                with _COLA_LOCK:
                    if _COLA.get(k) and _COLA[k][0] is e:
                        _COLA[k].pop(0)
                    if not ok:                          # no salió: los que esperaban detrás tampoco (la página lo dice)
                        for resto in _COLA.pop(k, None) or []:
                            _no_salio(agente, slug, resto["cid"], "no_se_mando")
        finally:
            with _COLA_LOCK:
                _COLA_HILO.discard(k)
    _t.sleep(espera_inicial)
    return _mandar_uno(agente, slug, texto, "", tope, pausa, {})


ARRANQUE_CALMA_S = 3        # W2: vueltas seguidas con su caja lista y su pantalla igual antes del 1er mensaje tras un cambio
ARRANQUE_VENTANA_S = 90     # cuánto dura esa espera desde que el cambio quedó listo


def _en_arranque(k):
    """W2: ¿su conversación acaba de cambiar de motor y su primer mensaje todavía no sale? Su turno de arranque puede
    seguir aunque su caja ya se vea lista (Cursor en Windows: el mensaje se tecleó dentro de ese turno y la página lo
    escondió con él)."""
    import time as _t
    c = _CAMBIOS.get(k)
    return bool(c and c.get("paso") == "listo" and not c.get("mandado") and _t.time() - c["t"] < ARRANQUE_VENTANA_S)


def _ya_mando(k):
    c = _CAMBIOS.get(k)
    if c and c.get("paso") == "listo":
        c["mandado"] = True


def _motivo_en_cola(k, por):
    """Sin caja a la vista con su conversación recién abierta, es que arranca; pasada la gracia, no se ve su caja."""
    import time as _t
    if por == "sin_caja" and _t.time() - _ABRIENDO.get(k, 0) < ABRIR_GRACIA_S:
        return "arrancando"
    return por


def _firma_conversacion(vis, motor):
    """Lo que se lee de su conversación en esa pantalla, en una firma corta: sin su pie, su caja ni sus barras (un reloj
    o un contador al pie, como el «activa 1m 7s» de Claude Code o el «⏲ 2s» de Hermes, no la cambian)."""
    import hashlib
    if vis is None:
        return None
    t = [(x["rol"], x["texto"], len(x.get("herr") or [])) for x in _de_pantalla(_sin_pregunta(vis), motor)]
    return hashlib.sha1(json.dumps(t, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _mandar_uno(agente, slug, texto, cid, tope, pausa, entrada):
    import time as _t
    k = (agente, slug)
    t0, quietas, firma, calma = _t.time(), 0, None, None

    def avisar(m):
        """El motivo cambió: desde ahora cuenta su tiempo, y lo que se ofrecía (o se pidió) por el anterior ya no."""
        if m and m != entrada.get("motivo"):
            with _COLA_LOCK:
                entrada.update(motivo=m, motivo_t=_t.time(), salida=False, caja="", forzar=False)
            if cid:
                _vivo().envio(agente, cid, "en_cola", motivo=m)

    def ofrecer(leer):
        """COLA_SALIDA_S esperando por su caja: lo que hay en ella (o al pie, `leer`) y «Mandar igual»."""
        ahora = _t.time()
        if entrada.get("motivo") not in ("caja_ocupada", "sin_caja") \
                or ahora - entrada.get("motivo_t", ahora) < COLA_SALIDA_S:
            return
        if entrada.get("salida") and ahora - entrada.get("caja_t", 0) < CAJA_RELEER_S:
            return
        c = leer()
        with _COLA_LOCK:
            entrada.update(salida=True, caja=c, caja_t=ahora)
    while _t.time() - t0 < tope:
        with _COLA_LOCK:
            entrada["tecleando"] = False                    # de vuelta aquí, nada se está tecleando: se puede quitar
            quitado = bool(cid and entrada.get("cancelado"))
        if quitado:
            _vivo().envio(agente, cid, "quitado")           # lo quitó el socio: los de detrás siguen
            return True
        try:
            bt, reg = _pestana_y_panel(agente, slug)
            ep = _estado_rapido(reg, fresco=True) if reg else {}
            if not ep.get("ok"):
                quietas = 0
                if _t.time() - max(_ABRIENDO.get(k, 0), t0) > ABRIR_GRACIA_S:
                    # con panel, su motor se cerró; sin él, nunca se abrió (el lanzador falló): con nombre y salida
                    return _no_salio(agente, slug, cid, "no_se_mando" if reg else "no_abrio")
                avisar("abriendo")
            else:
                info, arranque = {}, _en_arranque(k)
                lista, firma = _caja_lista(reg, firma, info)
                # W2: tras un cambio, además su conversación quieta (su turno de arranque ya no escribe nada); se mira
                # lo que se lee de ella, no la pantalla entera: un reloj al pie la cambia cada segundo
                antes, calma = calma, _firma_conversacion(info.get("vis"), (reg or {}).get("motor")) if arranque else None
                quietas = quietas + 1 if lista and (not arranque or calma == antes) else 0
                forzar = bool(entrada.get("forzar")) and (lista or info.get("por") == "sin_caja")
                r = None
                if quietas >= (ARRANQUE_CALMA_S if arranque else 2) or forzar:
                    with _COLA_LOCK:                        # desde aquí se teclea: Quitar ya no llega a tiempo
                        quitado = bool(cid and entrada.get("cancelado"))
                        if not quitado:
                            entrada["tecleando"] = True
                        entrada["forzar"] = False           # «Mandar igual» vale una vez
                    if quitado:
                        continue                            # la vuelta de arriba lo da por quitado
                    linea, marcar = _con_nota(agente, slug, reg, texto)
                    r = _escribir_en_caja(reg, linea, juntar=True) if forzar else _escribir_en_caja(reg, linea)
                    _nota_dicha(r, marcar)
                    if r != "ok":
                        with _COLA_LOCK:                    # no se tecleó: entre vueltas se puede quitar o mandar igual
                            entrada["tecleando"] = False
                    if r == "ok":
                        _ya_mando(k)
                        if slug == NAVEGADOR:
                            anotar_envio(agente, cid, texto, reg, bool(marcar))
                        if cid:
                            _vivo().envio(agente, cid, "recibido")
                        return True
                    if r in ("sin_eco", "atorado"):
                        if r == "atorado" and cid:
                            _ATORADO[agente] = (cid, linea, texto)
                        return _no_salio(agente, slug, cid, r)
                    if r == "cerrado":                                       # salió a la shell
                        return _no_salio(agente, slug, cid, "no_se_mando")
                    quietas = 0
                # el motivo, de lo que se vio; lista y esperando su segunda lectura, sigue el que había (no parpadea)
                avisar(_motivo_en_cola(k, r if r in ("caja_ocupada", "sin_caja", "pregunta", "trabajando")
                                       else info.get("por")))
                if r == "caja_ocupada":
                    ofrecer(lambda: _lo_que_tiene_su_caja(reg))
                elif entrada.get("motivo") == "sin_caja" and info.get("por") == "sin_caja":
                    from pantalla_motor import al_pie
                    ofrecer(lambda: "\n".join(al_pie(info.get("vis") or "")))
        except Exception:
            pass
        _t.sleep(pausa)
    return _no_salio(agente, slug, cid, "no_se_mando")


def _escribir_ejecucion(agente, ejecucion, texto=None, forzar=False):
    """Teclea en la pestaña de la ejecución (la instrucción de arranque, o `texto`).
    La instrucción de arranque se escribe UNA vez aunque la pidan la página y el hilo."""
    import aviso_panel
    import pasos
    brain = dict(_cerebros()).get(agente)
    with _ARRANQUE_LOCK:
        d = pasos.leer(ejecucion, brain)
        if not d:
            return "no_existe"
        if not texto and d.get("estado") != "arrancando":
            return "ok"                                   # ya la tiene
        bt, reg = _pestana_y_panel(agente, d.get("pestana") or "")
        if not reg or not _estado_rapido(reg, fresco=True).get("ok"):
            return "no_abierta"
        if not texto:
            import memoria
            m = memoria.normalizar_motor(reg.get("motor") or "")
            if m and not d.get("motor"):                  # se abrió con el de fábrica: queda ese
                d["motor"] = m
                pasos.guardar(ejecucion, d, brain)
            elif m and m != d.get("motor"):
                return "otro_motor"                       # H13: la instrucción es para el motor con que se pidió
        if not texto and pregunta_de(_leer_panel(reg, 60, "visible")):
            return "ocupada"                              # primero que contesten lo que pregunta
        dice = texto or _instruccion(ejecucion, d.get("skill"), d.get("ruta"), d.get("texto"), motor=reg.get("motor") or "")
        linea, marcar = _con_nota(agente, d.get("pestana") or "", reg, dice)
        r = _escribir_en_caja(reg, linea, forzar)
        _nota_dicha(r, marcar)
        if r != "ok":
            return "ocupada"
        if (d.get("pestana") or "") == NAVEGADOR:
            # «skill-», no «sk-»: el escáner de secretos tomaba el id por una llave de OpenAI (alarma al arrancar)
            anotar_envio(agente, "skill-%s-%s" % (ejecucion, secrets.token_hex(3)), dice, reg, bool(marcar))
        if not texto:
            d["estado"] = "corriendo"
            pasos.guardar(ejecucion, d, brain)
        return "ok"


def datos_ejecuciones(agente):
    """Las ejecuciones de skills de `agente` (las 20 más recientes), solo lo que pinta la página."""
    import pasos
    brain = dict(_cerebros()).get(agente)
    if not brain:
        return None
    d = pasos.carpeta(brain)
    try:
        nombres = sorted((n for n in os.listdir(d) if n.endswith(".json")), reverse=True)[:20]
    except OSError:
        nombres = []
    out = []
    for n in nombres:
        e = pasos.leer(n[:-5], brain)
        if not e:
            continue
        out.append({"id": _recorta(e.get("id"), 64), "skill": _limpio(e.get("skill"), 80),
                    "pestana": _recorta(e.get("pestana"), 120), "estado": _recorta(e.get("estado"), 16),
                    "texto": _limpio(e.get("texto"), 600), "resumen": _limpio(e.get("resumen"), 800),
                    "creado": _recorta(e.get("creado"), 20), "actualizado": _recorta(e.get("actualizado"), 20),
                    "pide": ({"texto": _limpio((e.get("pide") or {}).get("texto"), 2000),
                              "archivo": bool((e.get("pide") or {}).get("archivo")),
                              # sus opciones (agente-interfaz: botones en la caja) y desde cuándo (su id de pregunta)
                              "opciones": [_limpio(o, 200) for o in ((e.get("pide") or {}).get("opciones") or [])
                                           if isinstance(o, str)][:12],
                              "desde": _recorta((e.get("pide") or {}).get("desde"), 20)} if e.get("pide") else None),
                    "pasos": [{"texto": _limpio(p.get("texto"), 200), "estado": _recorta(p.get("estado"), 8),
                               "nota": _limpio(p.get("nota"), 200)} for p in (e.get("pasos") or [])[:30]],
                    # skills-cierre: por qué se detuvo (si se detuvo) y quién la activó (la página, el agente o, sin
                    # usar_skill, su motor con su propia herramienta)
                    "pausa": _pausa_vista(e.get("pausa")), "por": _recorta(e.get("por") or "pagina", 12),
                    "cierre": _recorta(e.get("cierre"), 12)})
    d = {"ejecuciones": out}
    try:
        import pagina_v2
        v = pagina_v2._vigente(agente, [e for e in out if (e.get("pestana") or NAVEGADOR) == NAVEGADOR])
        d["vigente"] = v.get("id") if v else None      # la regla del servidor, la misma de la foto (skill_vigente)
    except Exception:
        pass
    return d


def _pausa_vista(p):
    """Lo que pinta la página de una pausa: motivo, paso, lo que quedó pendiente, desde cuándo y si la cerraste."""
    if not isinstance(p, dict):
        return None
    return {"motivo": _recorta(p.get("motivo"), 16), "paso": int(p.get("paso") or 0) if str(
        p.get("paso") or "0").isdigit() else 0, "pendiente": _limpio(p.get("pendiente"), 600),
            "desde": _recorta(p.get("desde"), 20), "cerrada": bool(p.get("cerrada"))}


def guardar_archivo(agente, ejecucion, nombre, datos_b64):
    """Guarda lo que el socio sube para la skill junto a su ejecución y le avisa al agente."""
    import base64
    import pasos
    brain = dict(_cerebros()).get(agente)
    if not brain or not pasos.leer(ejecucion, brain):
        return "no_existe", None
    nombre = _ARCH_RE.sub("_", os.path.basename(str(nombre or "")))[:80].strip(" .") or "archivo"
    try:
        crudo = base64.b64decode(datos_b64 or "", validate=True)
    except Exception:
        return "formato", None
    if not crudo or len(crudo) > MAX_ARCHIVO:
        return "largo", None
    carpeta_a = os.path.join(pasos.carpeta(brain), ejecucion, "archivos")
    os.makedirs(carpeta_a, exist_ok=True)
    destino = os.path.join(carpeta_a, nombre)
    raiz, ext = os.path.splitext(destino)
    k = 2
    while os.path.exists(destino):
        destino, k = "%s-%d%s" % (raiz, k, ext), k + 1
    with open(destino, "wb") as f:
        f.write(crudo)
    rel = os.path.relpath(destino, str(brain)).replace(os.sep, "/")
    r = _escribir_ejecucion(agente, ejecucion, "El socio te dejó el archivo que pediste en %s (dentro de tu cerebro). Sigue con la skill." % rel, forzar=True)
    return ("ok" if r == "ok" else "guardado_sin_aviso"), rel


def guardar_adjunto(agente, nombre, datos_b64):
    """Un archivo que el socio adjunta en el chat → `<cerebro>/STATE/adjuntos/<fecha>/<nombre>`.
    → (estado, ruta relativa al cerebro). El agente lo lee desde su cerebro."""
    import base64
    import datetime as _dt
    brain = dict(_cerebros()).get(agente)
    if not brain:
        return "no_existe", None
    nombre = _ARCH_RE.sub("_", os.path.basename(str(nombre or "")))[:80].strip(" .") or "archivo"
    try:
        crudo = base64.b64decode(datos_b64 or "", validate=True)
    except Exception:
        return "formato", None
    if not crudo or len(crudo) > MAX_ARCHIVO:
        return "largo", None
    carpeta_a = os.path.join(str(brain), "STATE", "adjuntos", _dt.date.today().isoformat())
    os.makedirs(carpeta_a, exist_ok=True)
    destino = os.path.join(carpeta_a, nombre)
    raiz, ext = os.path.splitext(destino)
    k = 2
    while os.path.exists(destino):
        destino, k = "%s-%d%s" % (raiz, k, ext), k + 1
    with open(destino, "wb") as f:
        f.write(crudo)
    return "ok", os.path.relpath(destino, str(brain)).replace(os.sep, "/")


_FM_RE = re.compile(r"^\s*(name|description|version)\s*:\s*(.*?)\s*$")


def _frontmatter_skill(md):
    """name / description / version del encabezado de un SKILL.md (los primeros
    8 KB; nada más del archivo sale)."""
    out = {}
    try:
        with open(md, encoding="utf-8", errors="replace") as f:
            texto = f.read(8192)
    except OSError:
        return out
    if not texto.startswith("---"):
        return out
    for ln in texto.split("\n")[1:80]:
        if ln.strip() == "---":
            break
        m = _FM_RE.match(ln)
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip().strip("'\"")
    return out


#: Skills v11: el título bajo el que una skill pone sus pasos (lo demás del SKILL.md no sale).
_PASOS_TITULO = re.compile(r"^(#{2,4})\s+.*\b(pasos|proceso|flujo|procedimiento|workflow|steps|c[oó]mo se hace)\b", re.I)
_PASOS_ITEM = re.compile(r"^\s{0,3}\d{1,2}[.)]\s+(\S.*)$")
MAX_PASOS = 8


def _pasos_skill(md):
    """Los pasos de una skill para el panel: la lista numerada bajo su título de pasos (o de proceso, flujo…),
    en una línea cada uno y sin markdown. Sin ese título, [] (no se inventan)."""
    try:
        with open(md, encoding="utf-8", errors="replace") as f:
            lineas = f.read(32768).split("\n")
    except OSError:
        return []
    out, nivel = [], 0
    for ln in lineas:
        t = _PASOS_TITULO.match(ln)
        if not nivel:
            if t:
                nivel = len(t.group(1))
            continue
        h = re.match(r"^(#{1,6})\s", ln)
        if h and len(h.group(1)) <= nivel:
            if out:
                break
            nivel = len(t.group(1)) if t else 0       # otro título: si también es de pasos, sigue buscando ahí
            continue
        m = _PASOS_ITEM.match(ln)
        if m:
            txt = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", m.group(1))
            txt = re.sub(r"[*_`]+", "", txt).strip()
            out.append(_limpio(txt, 90))
            if len(out) >= MAX_PASOS:
                break
    return [p for p in out if p]


def datos_skills():
    import skill_meta
    out = []
    for agente, brain in _cerebros():
        raiz = os.path.join(str(brain), "skills")
        if not os.path.isdir(raiz):
            continue
        n = 0
        for d in skill_meta.iter_skill_dirs(raiz):
            partes = os.path.relpath(d, raiz).replace(os.sep, "/").split("/")
            fm = _frontmatter_skill(os.path.join(d, "SKILL.md"))
            out.append({"agente": agente, "categoria": _limpio(partes[0] if len(partes) > 1 else "", 40),
                        "nombre": _limpio(fm.get("name") or partes[-1], 80),
                        "descripcion": _limpio(fm.get("description"), 280),
                        "version": _recorta(fm.get("version"), 16),
                        "pasos": _pasos_skill(os.path.join(d, "SKILL.md"))})
            n += 1
            if n >= MAX_SKILLS:
                break
    return {"skills": out}


def datos_motores():
    import motores_logica
    filas = []
    for d in motores_logica._rows():
        eid = d.get("id")
        filas.append({"id": _recorta(eid, 30), "nombre": _recorta(motores_logica.engine_name(d), 40),
                      "listo": bool(d.get("ready")),
                      "agentes": [_limpio(a, 40) for a in motores_logica.users_of(eid)][:20]})
    return {"motores": filas}


def datos_conexiones():
    """Los MCP que Workspace ve, por nombre y en qué motores están. Sin rutas,
    sin comandos, sin variables (ni sus nombres). Conexiones en verde (F1): los
    de los archivos PROPIOS de Workspace (su perfil en cada motor: el MCP de
    Copilot en su carpeta de estado, su agente de Kiro, sus perfiles de Hermes
    y OpenClaw) son de Workspace, no tuyos: `tuyos` dice en qué motores lo
    pusiste tú y `de_workspace`, si solo lo puso Workspace."""
    import mcp_inventory
    vistas = {}
    for r in mcp_inventory.scan().get("records", []):
        nombre = r.get("name")
        if not nombre:
            continue
        e = vistas.setdefault(nombre, {"nombre": _limpio(nombre, 80), "motores": [], "tuyos": [],
                                       "registrada": False})
        if r.get("engine") == "workspace":
            e["registrada"] = True
            continue
        motor = _recorta(r.get("engine"), 30)
        if motor and motor not in e["motores"]:
            e["motores"].append(motor)
        if motor and r.get("scope") != "profile" and motor not in e["tuyos"]:
            e["tuyos"].append(motor)
    for e in vistas.values():
        e["de_workspace"] = bool(e["motores"]) and not e["tuyos"]
    return {"conexiones": sorted(vistas.values(), key=lambda x: x["nombre"].lower())[:MAX_CONEXIONES]}


def datos_usuarios():
    import usuarios
    vistos = {}
    for _agente, brain in _cerebros():
        try:
            for c in usuarios.cedulas(brain):
                n = c.get("nombre")
                if n and n not in vistos:
                    vistos[n] = {"nombre": _limpio(n, 60), "alias": [_limpio(a, 40) for a in (c.get("alias") or [])][:8]}
        except Exception:
            continue
    return {"usuarios": list(vistos.values())}


_API = {
    "/api/estado": datos_estado,
    "/api/agentes": datos_agentes,
    "/api/salas": datos_salas,
    "/api/calendario": datos_calendario,
    "/api/decisores": datos_decisores,
    "/api/memoria": datos_memoria,
    "/api/pestanas": datos_pestanas,
    "/api/pestana": lambda: {"pestana": None},   # la de verdad lleva ?agente=&slug= (do_GET)
    "/api/pantalla": lambda: {"viva": False},    # idem: ?agente=&slug= (do_GET)
    "/api/skills": datos_skills,
    "/api/ahora": datos_ahora,
    "/api/motores": datos_motores,
    "/api/conexiones": datos_conexiones,
    "/api/usuarios": datos_usuarios,
    "/api/ejecuciones": lambda: {"ejecuciones": []},   # la de verdad lleva ?agente= (do_GET)
    "/api/conversacion": lambda: {"soporta": False},    # idem: ?agente=&slug= (do_GET)
}

# ── Motores y Usuarios: las MISMAS funciones de la terminal (localhost_sistema) ──
def _sis():
    import localhost_sistema
    return localhost_sistema


#: GET: ruta → función(q), con q(campo) = el valor de ?campo= (texto; vacío si falta).
_SIS_GET = {
    "/api/sistema/motores": lambda q: _sis().motores(verificar=q("verificar") == "1"),
    "/api/sistema/motor/preparar": lambda q: _sis().motor_preparar(q("motor"), q("accion"), q("opcion")),
    "/api/sistema/motor/cuenta": lambda q: _sis().motor_cuenta(q("motor")),
    "/api/sistema/motor/tarea": lambda q: _sis().motor_tarea(q("tarea"), resumen=q("resumen") == "1"),
    "/api/sistema/motores/ayuda": lambda q: _sis().ayuda_motores(q("motor") or None),
    "/api/sistema/decisores": lambda q: _sis().decisores(),
    "/api/sistema/decisores/ayuda": lambda q: _sis().ayuda_decisores(q("decisor") or None),
    "/api/sistema/usuarios": lambda q: _sis().usuarios(),
    "/api/sistema/usuarios/ayuda": lambda q: _sis().ayuda_usuarios(),
}
#: POST: ruta → (función de localhost_sistema, {campo: (tipo, obligatorio)}). Solo
#: esos campos y de ese tipo llegan a la función; lo demás del cuerpo se ignora.
_SIS_POST = {
    "/api/sistema/motores/recargar": ("motores_recargar", {}),
    "/api/sistema/motor/verificar": ("motor_verificar", {"motor": (str, True)}),
    "/api/sistema/motor/hub": ("motor_en_hub", {"motor": (str, True), "encendido": (bool, True)}),
    "/api/sistema/motor/correr": ("motor_correr", {"motor": (str, True), "accion": (str, True),
                                                   "opcion": (str, False), "confirmado": (bool, False)}),
    "/api/sistema/motor/tarea/teclas": ("motor_tarea_teclas", {"tarea": (str, True), "texto": (str, False),
                                                              "teclas": (list, False)}),
    "/api/sistema/motor/tarea/cerrar": ("motor_tarea_cerrar", {"tarea": (str, True)}),
    "/api/sistema/agente/motor": ("agente_motor", {"agente": (str, True), "motor": (str, True)}),
    "/api/sistema/decisor/llave": ("decisor_conectar", {"decisor": (str, True), "llave": (str, True)}),
    "/api/sistema/decisor/desconectar": ("decisor_desconectar", {"decisor": (str, True)}),
    "/api/sistema/decisor/modelo": ("decisor_modelo", {"decisor": (str, True), "modelo": (str, True)}),
    "/api/sistema/decisor/contexto": ("decisor_contexto", {"decisor": (str, True), "tokens": (int, True)}),
    "/api/sistema/decisor/probar": ("decisor_probar", {"decisor": (str, True)}),
    "/api/sistema/decisor/revisar": ("decisor_revisar", {"decisor": (str, True)}),
    "/api/sistema/usuarios/asegurar": ("usuarios_asegurar", {"agente": (str, True)}),
    "/api/sistema/usuario/crear": ("usuario_crear", {"agente": (str, True), "nombre": (str, True)}),
    "/api/sistema/usuario/renombrar": ("usuario_renombrar", {"agente": (str, True), "usuario": (str, True),
                                                            "nuevo": (str, True), "revision": (int, False)}),
    "/api/sistema/usuario/unir": ("usuario_unir", {"agente": (str, True), "origen": (str, True),
                                                  "destino": (str, True)}),
    "/api/sistema/usuario/soy": ("usuario_soy_yo", {"agente": (str, True), "usuario": (str, True)}),
}


# ── front nuevo: apariencia, tono, archivos del cerebro y preferencias (localhost_front) ──
def _front():
    import localhost_front
    return localhost_front


def _vivo():
    import front_vivo
    return front_vivo


_FRONT_GET = {
    "/api/front/vivo": lambda q: _vivo().cambios(q("v"), q("e"), q("espera"), q("act")),
    "/api/front/eventos": lambda q: _vivo().eventos(q("agente"), q("desde")),
    "/api/front/inicio": lambda q: _front().inicio(),
    "/api/front/tono": lambda q: _front().tono(q("agente")),
    "/api/front/archivos": lambda q: _front().archivos(q("agente")),
    "/api/front/archivo": lambda q: _front().archivo(q("agente"), q("ruta")),
    "/api/front/uso": lambda q: _front().uso(q("agente")),
    "/api/front/pendientes": lambda q: _front().pendientes(q("agente")),
    "/api/front/crear": lambda q: _front().crear_estado(),
    "/api/front/buscar": lambda q: _front().buscar_agentes(q("protegidas") == "1"),
    "/api/front/carpeta": lambda q: _front().carpeta(q("ruta")),
    "/api/front/cargar": lambda q: _front().cargar_estado(),
    "/api/front/apartados": lambda q: _front().apartados(q("agente") or "", q("hablando") or ""),
    "/api/front/textos": lambda q: _front().textos_agregar(),
    "/api/front/pendientes/todos": lambda q: _front().pendientes_todos(),
}
# ── la página v2 (arquitectura nueva, F3): una vista del núcleo que escribe por la capa de control ──
# Lee el registro de eventos y el historial por eventos; escribe con control/ (abrir, mandar, permisos,
# parar). Ninguna de estas rutas lee la pantalla de un motor ni teclea en su terminal (prueba: test_arq_f3).
def _v2():
    import pagina_v2
    return pagina_v2


def _verificacion():
    from arquitectura import verificacion
    return verificacion


def _v2_canal(q):
    """El canal de una ruta v2 (`canal`): el de la página si no viene (la página y el hub no lo mandan) o el del
    monito de escritorio (modo escritorio, D1-a)."""
    return ESCRITORIO if q("canal") == ESCRITORIO else NAVEGADOR


def _chequeo():
    from arquitectura import chequeo
    return chequeo


_V2_GET = {
    "/api/v2/vivo": lambda q: _v2().vivo(q("v"), q("e"), q("espera"), q("act"))
    if _v2_canal(q) == NAVEGADOR else _v2().vivo(q("v"), q("e"), q("espera"), q("act"), canal=ESCRITORIO),
    # H4-a: `slug` es la pestaña (la de siempre, «navegador», o una de sus sesiones abierta como pestaña)
    "/api/v2/conversacion": lambda q: _v2().conversacion(q("agente"), q("slug") or NAVEGADOR, q("v"))
    if _v2_canal(q) == NAVEGADOR else _v2().conversacion(q("agente"), ESCRITORIO, q("v"), canal=ESCRITORIO),
    "/api/v2/uso": lambda q: _v2().uso(q("agente")) if _v2_canal(q) == NAVEGADOR
    else _v2().uso(q("agente"), canal=ESCRITORIO),
    "/api/v2/info": lambda q: _v2().info(),
    "/api/v2/pestanas": lambda q: _v2().pestanas(),
    # H3 (rama de prueba marca-lab): las sesiones oficiales del agente, de su registro de eventos (sin pantallas)
    "/api/v2/sesiones": lambda q: _v2().sesiones(q("agente")),
    # Conexiones: la última verificación REAL de Workspace en cada motor (piezas comunes y matriz pieza × motor).
    # Desde Conexiones en verde es la vista de laboratorio (modo desarrollador); lo que ve el socio es el chequeo.
    "/api/v2/conexiones": lambda q: _verificacion().matriz(),
    # modo escritorio · E1: lo entregado del agente (el panel grande del monito)
    "/api/v2/entregas": lambda q: _v2().entregas(q("agente")),
    # Conexiones en verde (F2): el chequeo rápido, sin IA (arquitectura/chequeo): el último, y uno nuevo en segundo
    # plano si es viejo; cinco filas por motor, tres estados y una acción por fila
    "/api/v2/chequeo": lambda q: _chequeo().vista(),
}
_V2_POST = {
    # modo escritorio (D1-a): `canal` «escritorio» va a la conversación del monito (sin él, la de la página, como
    # siempre) y `contexto` es lo que tenía enfrente (D3-a: app, ventana, url, selección).
    # H4-a: `tab` es la pestaña de la conversación de la página (una de sus sesiones, por su slug); sin él, la de siempre
    "/api/v2/mandar": ("mandar", {"agente": (str, True), "texto": (str, True), "cid": (str, False),
                                  "canal": (str, False), "contexto": (dict, False), "tab": (str, False)}),
    "/api/v2/permiso": ("permiso", {"agente": (str, True), "id": (str, True), "decision": (str, True),
                                    "canal": (str, False), "tab": (str, False)}),
    # Monito ronda 2 · P2-b: «Permitir y seguir» de una ficha que quedó para después (un pase de un solo uso)
    "/api/v2/permiso_despues": ("permiso_despues", {"agente": (str, True), "ids": (list, True), "decision": (str, True)}),
    "/api/v2/parar": ("parar", {"agente": (str, True), "canal": (str, False), "tab": (str, False)}),
    "/api/v2/quitar": ("quitar", {"agente": (str, True), "cid": (str, True), "canal": (str, False), "tab": (str, False)}),
    # modo escritorio · «Seguir en la página»: el hilo del monito pasa a la conversación de la página
    "/api/v2/seguir": ("seguir_en_la_pagina", {"agente": (str, True)}),
    "/api/v2/motor": ("cambiar_motor", {"agente": (str, True), "motor": (str, True), "tab": (str, False)}),
    "/api/v2/ajuste": ("ajuste", {"agente": (str, True), "ajuste": (str, True), "valor": (str, True)}),
    "/api/v2/terminal": ("ir_a_la_terminal", {"agente": (str, True), "tab": (str, False)}),
    "/api/v2/terminal/cerrar": ("cerrar_terminal", {"agente": (str, True), "tab": (str, False)}),
    # H4-a «pestañas en el borde»: abrir una de sus sesiones (o una conversación nueva, con su motor), cerrarla (no
    # borra nada) y deshacer lo último que se cerró
    "/api/v2/tab/abrir": ("tab_abrir", {"agente": (str, True), "slug": (str, False), "nueva": (bool, False),
                                        "motor": (str, False), "nombre": (str, False)}),
    "/api/v2/tab/cerrar": ("tab_cerrar", {"agente": (str, True), "tab": (str, True)}),
    "/api/v2/tab/deshacer": ("tab_deshacer", {"agente": (str, True)}),
    # Amigable: lo que pide la tarjeta de un motor con problemas (iniciar sesión, actualizar, seguir con otro…)
    "/api/v2/arreglar": ("arreglar", {"agente": (str, True), "accion": (str, True)}),
    "/api/v2/skill": ("skill", {"agente": (str, True), "skill": (str, True), "texto": (str, False)}),
    # skills-cierre: «Detener» (página y hub) y «Seguir» / «Cerrar» de una skill que se detuvo sola
    "/api/v2/skill/accion": ("skill_accion", {"agente": (str, True), "id": (str, True), "accion": (str, True)}),
    "/api/v2/archivo": ("archivo", {"agente": (str, True), "id": (str, True), "nombre": (str, True),
                                    "datos": (str, True)}),
    # Configuración → General: el ajuste arquitectura.paquete (lo mismo que `settings.py set`)
    "/api/v2/paquete": ("paquete", {"encendido": (bool, True)}),
    # Configuración → Permisos: el nivel de un agente (auto | preguntar | editar), decisión del dueño 18-nov
    "/api/v2/autonomia": ("autonomia", {"agente": (str, True), "nivel": (str, True)}),
    # F6: lo que una skill preguntó en el chat y «Hacer ahora» (por la capa de control, sin teclear)
    "/api/v2/responder": ("responder", {"agente": (str, True), "id": (str, True), "texto": (str, True),
                                        "canal": (str, False), "tab": (str, False)}),
    "/api/v2/revision": ("hacer_ahora", {"agente": (str, True)}),
    # Conexiones → «Verificar ahora»: la auditoría con el motor real, en segundo plano (sin campos)
    "/api/v2/verificar": ("verificar_ahora", {"motor": (str, False)}),
    # modo escritorio · E1 (encargos.py): un encargo a su conversación de trabajo con tu clic (lo arma la app: lo que
    # pediste, el archivo de verdad en base64 y la plantilla), visto/parar/reintentar, «Pásaselo a…» y la tarjeta de una
    # entrega (su ruta real, solo dentro de su cerebro)
    "/api/v2/encargar": ("encargar", {"agente": (str, True), "pedido": (str, True), "titulo": (str, False),
                                      "plantilla": (str, False), "archivo": (str, False), "base": (str, False),
                                      "archivo_nombre": (str, False), "archivo_datos": (str, False),
                                      # Fable v2: el nivel de ESTE encargo (las casillas de su tarjeta)
                                      "comandos": (bool, False), "internet": (bool, False), "como_pagina": (bool, False)}),
    "/api/v2/encargo": ("encargo", {"agente": (str, True), "id": (str, True), "accion": (str, True)}),
    "/api/v2/pasar": ("pasar", {"de": (str, True), "a": (str, True), "ruta": (str, False), "nota": (str, False),
                                "archivo_nombre": (str, False), "archivo_datos": (str, False),
                                "comandos": (bool, False), "internet": (bool, False), "como_pagina": (bool, False)}),
    "/api/v2/entrega": ("entrega", {"agente": (str, True), "ruta": (str, True)}),
    # Conexiones en verde: «Revisar ahora» (el chequeo rápido, con el saludo de cada canal: sin IA)
    "/api/v2/chequeo/revisar": ("revisar_conexiones", {"motor": (str, False)}),
    # F3: «Arreglar» (solo lo de Workspace, con respaldo), su «Deshacer» y «Reportar» (un zip local, nada se envía)
    "/api/v2/chequeo/arreglar": ("arreglar_conexion", {"arreglo": (str, True)}),
    "/api/v2/chequeo/deshacer": ("deshacer_arreglo", {"id": (str, True)}),
    "/api/v2/chequeo/reportar": ("reportar_conexion", {"motor": (str, False), "fila": (str, False)}),
}
#: Las rutas v2 que traen un archivo entero (base64): su tope es el del archivo, no el de un POST normal.
_V2_CON_ARCHIVO = ("/api/v2/archivo", "/api/v2/encargar", "/api/v2/pasar")
#: Los campos que van tal cual a un nombre de archivo o a un id: con forma de slug (el id de un
#: permiso lo pone su motor: lleva «#» en ACP).
_V2_SLUG = ("agente", "cid", "motor", "ajuste", "valor", "nivel", "de", "a", "accion", "plantilla", "tab", "slug")
_V2_PERMISO_RE = re.compile(r"^[A-Za-z0-9._:#-]{1,200}$")
#: Conexiones en verde: el id de un arreglo («skills:codex»), de su respaldo o de una fila.
_CHEQUEO_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,80}$")
#: …y la del socio en el monito: «Sí, y lo demás en esta carpeta (solo este trabajo)» (control/base.PERMITIR_TURNO)
_V2_DECISIONES = ("permitir", "permitir_siempre", "negar", "permitir_turno")


def _v2_valido(ruta, kw):
    """Los argumentos de una ruta v2 con su forma, o None."""
    if kw.get("plantilla") == "":
        kw.pop("plantilla")                    # sin plantilla (un encargo libre)
    for k in ("tab", "slug"):
        if kw.get(k) in ("", NAVEGADOR):
            kw.pop(k)                          # H4-a: la de siempre: la llamada de siempre
    if "nombre" in kw and ruta == "/api/v2/tab/abrir" and len(kw["nombre"]) > 80:
        return None
    if any(k in kw and not _SLUG_RE.match(kw[k]) for k in _V2_SLUG):
        return None
    if any(k in kw and not isinstance(kw[k], bool) for k in ("comandos", "internet", "como_pagina")):
        return None                            # Fable v2: el nivel de un encargo, solo sí/no
    if "canal" in kw:
        if kw["canal"] not in ("", NAVEGADOR, ESCRITORIO):
            return None
        if kw["canal"] in ("", NAVEGADOR):
            kw.pop("canal")                    # la de la página: la llamada de siempre
    # la conversación del Compañero de escritorio solo se nombra con `canal` (nunca como una pestaña de la página)
    if kw.get("tab") == ESCRITORIO or kw.get("slug") == ESCRITORIO:
        return None
    if kw.get("canal") == ESCRITORIO:
        kw.pop("tab", None)
    if "contexto" in kw and (kw.get("canal") != ESCRITORIO or len(json.dumps(kw["contexto"])) > 8000):
        kw.pop("contexto")                     # solo el monito manda lo que tenía enfrente, y en chico
    if ruta == "/api/v2/permiso" and (not _V2_PERMISO_RE.match(kw["id"]) or kw["decision"] not in _V2_DECISIONES):
        return None
    if ruta == "/api/v2/permiso_despues" and (kw["decision"] not in ("permitir", "negar") or not 0 < len(kw["ids"]) <= 40
                                              or any(not isinstance(i, str) or not _V2_PERMISO_RE.match(i)
                                                     for i in kw["ids"])):
        return None
    if ruta == "/api/v2/responder" and (not _V2_PERMISO_RE.match(kw["id"]) or not kw["texto"].strip()):
        return None
    if ruta in ("/api/v2/archivo", "/api/v2/encargo") and not _SLUG_RE.match(kw["id"]):
        return None
    if ruta == "/api/v2/skill/accion" and (not _SLUG_RE.match(kw["id"]) or kw["accion"] not in (
            "detener", "seguir", "cerrar")):
        return None
    if ruta.startswith("/api/v2/chequeo/") and any(
            k in kw and not _CHEQUEO_RE.match(kw[k]) for k in ("arreglo", "id", "fila")):
        return None
    if "texto" in kw:
        t = kw["texto"]
        if len(t) > MAX_ESCRIBIR or (ruta == "/api/v2/mandar" and not t.strip()):
            return None
    return kw


def _v2_texto_seguro(t):
    """Lo que sale por la capa de control: sin caracteres de control (salvo saltos y tabs)
    ni llaves (la misma regla que al teclear). → clave del error, o ''."""
    import salas
    import secret_scan
    if salas._CONTROL_RE.search(t.replace("\n", " ").replace("\t", " ")):
        return "localhost.err.control"
    try:
        return "localhost.err.llave" if secret_scan.scan_text(t) else ""
    except Exception:
        return "localhost.err.interno"


_FRONT_POST = {
    "/api/front/apariencia": ("apariencia", {"agente": (str, True), "forma": (str, False), "color": (str, False)}),
    "/api/front/nombre": ("nombre", {"agente": (str, True), "nombre": (str, True)}),
    "/api/front/prefs": ("prefs", {"agente": (str, True), "fijas": (list, False), "detenidas": (list, False)}),
    "/api/front/guia": ("guia", {"vista": (bool, True)}),
    "/api/front/pagina": ("pagina", {"cambios": (dict, True)}),
    "/api/front/tono": ("tono_guardar", {"agente": (str, True), "niveles": (dict, True)}),
    "/api/front/abrir": ("abrir", {"agente": (str, True), "ruta": (str, True), "modo": (str, False)}),
    "/api/front/skill/nombre": ("skill_renombrar", {"agente": (str, True), "skill": (str, True), "nuevo": (str, True)}),
    "/api/front/pendiente": ("pendiente", {"agente": (str, True), "accion": (str, True), "id": (str, False),
                                           "hecho": (bool, False), "texto": (str, False)}),
    "/api/front/archivo": ("archivo_guardar", {"agente": (str, True), "ruta": (str, True), "texto": (str, True),
                                               "firma": (str, False)}),
    "/api/front/crear": ("crear_agente", {"nombre": (str, True), "ayuda": (str, False), "forma": (str, False),
                                          "color": (str, False), "motor": (str, False), "visible": (str, False),
                                          "como_habla": (str, False), "que_si_no": (str, False),
                                          "sobre_ti": (str, False), "autonomia": (bool, False),
                                          "revisar_skills": (bool, False)}),
    "/api/front/crear/cancelar": ("crear_cancelar", {}),
    "/api/front/crear/visto": ("crear_visto", {}),
    "/api/front/cargar": ("cargar_agente", {"indices": (list, False), "ruta": (str, False), "carpetas": (list, False),
                                            "nombres": (list, False), "autonomia": (bool, False),
                                            "revisar_skills": (bool, False)}),
    "/api/front/cargar/visto": ("cargar_visto", {}),
    # archivar un agente, quitarlo de Workspace y traerlo de vuelta (agente_apartar: nada se borra, todo se deshace)
    "/api/front/archivar": ("archivar_agente", {"agente": (str, True)}),
    "/api/front/quitar": ("quitar_agente", {"agente": (str, True)}),
    "/api/front/volver": ("volver_agente", {"nombre": (str, True)}),
}


def _sis_campos(d, esquema):
    """Los argumentos de la función: solo los campos del esquema y de su tipo
    (un bool no pasa por int). None si falta uno obligatorio o el tipo no cuadra."""
    kw = {}
    for campo, (tipo, obligatorio) in esquema.items():
        if campo not in d or d[campo] is None:
            if obligatorio:
                return None
            continue
        v = d[campo]
        if type(v) is not tipo:
            return None
        kw[campo] = v
    return kw


# ── §6: modelo, esfuerzo y modo como botones (la tabla por motor y su fuente: ajustes_motor) ──
# Nunca se abre su selector ni se enseña en el chat: un comando CON argumento se teclea en su caja (sin turno en la
# página) y se confirma en su pie; lo que solo existe al arrancar se guarda y va al reabrir su conversación.
_AJ_LOCK = threading.Lock()
_AJ_GUARDADOS = {}          # {"d": {agente: {motor: {k: v}}}}: lo elegido para su arranque (memoria del archivo)
_AJ_HECHOS = {}             # agente → {"panel", "valores": {k: v}}: lo que se aplicó en ESA sesión (su panel)
AJUSTE_CONFIRMA_S = 4.0     # cuánto se espera a que su pie diga lo elegido


def _ajustes_path():
    import aviso_panel
    return os.path.join(aviso_panel._estado(), "ajustes-navegador.json")


def ajustes_guardados(agente):
    """{motor: {k: v}} que van en el arranque de la conversación de la página de `agente`."""
    with _AJ_LOCK:
        if "d" not in _AJ_GUARDADOS:
            try:
                with open(_ajustes_path(), encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                d = {}
            _AJ_GUARDADOS["d"] = d if isinstance(d, dict) else {}
        g = _AJ_GUARDADOS["d"].get(agente)
        return {m: dict(x) for m, x in g.items() if isinstance(x, dict)} if isinstance(g, dict) else {}


def _guardar_ajuste(agente, motor, k, v):
    import atomico
    ajustes_guardados(agente)                      # lo carga si aún no
    with _AJ_LOCK:
        d = _AJ_GUARDADOS["d"]
        if not isinstance(d.get(agente), dict):
            d[agente] = {}
        d[agente].setdefault(motor, {})[k] = v
        atomico.escribir(_ajustes_path(), json.dumps(d, ensure_ascii=False))


def _flags_de_arranque(agente, motor):
    """(argv, {k: v}) de lo guardado para `motor`, revalidado contra su tabla (el archivo no decide qué llega a su
    línea de arranque). Lo que solo va al retomar su sesión (Codex) va si la pestaña ya tiene una de ese motor."""
    import ajustes_motor as AM
    try:
        reanuda = bool(_slot_navegador(_cerebro(agente)).get(motor))
    except Exception:
        reanuda = False
    return AM.argumentos(motor, ajustes_guardados(agente).get(motor), reanuda)


def _motor_de_pagina(agente, reg):
    """El motor de la conversación de la página: el que corre, el de su último segmento o el del agente."""
    return (reg or {}).get("motor") or _motor_de_conversacion(agente, NAVEGADOR) or _motores_de_agentes().get(agente) or ""


def ajustes_de(agente, motor, vistos, panel=""):
    """Lo actual de cada ajuste de `motor`, de verdad: lo que enseña su pantalla (`vistos`, ajustes_motor.leer); si
    no, lo último que se aplicó en ESA sesión (su `panel`); si tampoco, None («no se sabe»). Más lo guardado para el
    arranque de cada motor. → {"motor", "valores": {k: {"actual", "guardado"}}, "guardados": {motor: {k: v}}}."""
    import ajustes_motor as AM
    hechos = _AJ_HECHOS.get(agente) or {}
    hechos = hechos.get("valores", {}) if panel and hechos.get("panel") == panel else {}
    guardados = ajustes_guardados(agente)
    valores = {}
    for f in AM.filas(motor):
        k = f["k"]
        visto = (vistos or {}).get(k)
        act = dict(visto, de="pantalla") if visto else \
            {"v": hechos[k], "t": AM.etiqueta(motor, k, hechos[k]), "de": "aplicado"} if k in hechos else None
        valores[k] = {"actual": act, "guardado": (guardados.get(motor) or {}).get(k)}
    return {"motor": motor, "valores": valores, "guardados": guardados}


def _confirmar_ajuste(reg, motor, k, v, espera=None):
    """Tras teclear su comando: ¿su pie ya dice `v`? Si en vez de eso abrió su selector (un menú), se cierra con esc
    (la página no lo enseña ni lo contesta) y se dice. → "confirmado" | "selector" | "sin_confirmar".
    (H15 contestaba aquí el «Switch model?» de `/model` en Claude Code; desde F3 de la v4 su modelo va con
    `--model` al arrancar y nada se teclea.)"""
    import time as _t
    import aviso_panel
    import ajustes_motor as AM
    fin = _t.time() + (AJUSTE_CONFIRMA_S if espera is None else espera)
    while True:
        vis = _leer_panel(reg, 60, "visible") or ""
        if pregunta_de(vis):
            _en_el_panel(reg, lambda: aviso_panel._herdr(["pane", "send-keys", reg["panel"], "esc"], reg.get("socket", ""),
                                                          json_out=False) is not None)
            return "selector"
        if (AM.leer(motor, vis).get(k) or {}).get("v") == v:
            return "confirmado"
        if _t.time() >= fin:
            return "sin_confirmar"
        _t.sleep(0.4)


def aplicar_ajuste(agente, k, v):
    """Un botón de modelo, esfuerzo o modo. Ocupado no se toca (cambiarlo lo interrumpiría). Por su comando en
    sesión: se teclea en su caja con _escribir_en_caja (sin abrir su selector) y se confirma en su pie. Solo al
    arrancar: se guarda para el siguiente arranque. → ("ok", datos) | ("ocupado", oc) | ("error", clave)."""
    import ajustes_motor as AM
    oc = _vivo().ocupado(agente)
    if oc:
        return "ocupado", oc
    try:
        _bt, reg = _pestana_y_panel(agente, NAVEGADOR)
    except Exception:
        reg = None
    motor = _motor_de_pagina(agente, reg)
    f = AM.fila(motor, k)
    if not f or not AM.valido(motor, k, v):
        return "error", "localhost.err.ajuste"
    if f["via"] == "arranque":
        _guardar_ajuste(agente, motor, k, v)
        _vivo().releer(agente)
        return "ok", {"via": "arranque", "abierta": bool(reg),
                      "al_reanudar": bool(f.get("al_reanudar")) and not _flags_de_arranque(agente, motor)[1].get(k)}
    if not reg:
        return "error", "localhost.err.no_abierta"
    r = _escribir_en_caja(reg, AM.comando(motor, k, v))
    if r not in ("ok", "atorado"):
        return "error", {"pregunta": "localhost.err.pregunta", "trabajando": "localhost.err.trabajando",
                         "sin_caja": "localhost.err.sin_caja", "caja_ocupada": "localhost.err.caja_ocupada",
                         "sin_eco": "localhost.err.ajuste_sin_eco"}.get(r, "localhost.err.panel")
    c = _confirmar_ajuste(reg, motor, k, v)
    if r == "atorado" and c != "confirmado":
        return "error", "localhost.err.no_salio"      # H15: su confirmación pudo tardar en salir; si tampoco, no salió
    if c == "confirmado":
        h = _AJ_HECHOS.get(agente) or {}
        _AJ_HECHOS[agente] = {"panel": reg.get("panel"),
                              "valores": dict(h.get("valores", {}) if h.get("panel") == reg.get("panel") else {}, **{k: v})}
    _vivo().releer(agente)
    return "ok", {"via": "sesion", "confirmado": c == "confirmado", "selector": c == "selector"}


def _teclas_parar(motor):
    """Con qué se detiene ese motor: la tecla que da su adapter (`TECLAS_PARAR`, nombres de herdr; carril
    motores-al-dia, F12: Cursor ignora esc). Si su adapter no la da, esc, la de siempre."""
    try:
        import dispatch
        t = getattr(dispatch.load_engine(motor), "TECLAS_PARAR", None)
        if isinstance(t, (list, tuple)) and t and all(isinstance(k, str) and k.lower() in TECLAS for k in t):
            return [k.lower() for k in t]
    except Exception:
        pass
    return ["esc"]


_RUTA_MENSAJE = re.compile(r"^/api/salas/([A-Za-z0-9][A-Za-z0-9._-]{0,79})/mensaje$")


def _ruta_vista_publica(ruta):
    if ruta in ("/api/memoria", "/api/salas") or ruta.startswith(("/api/salas/", "/api/memoria/")):
        return False
    if ruta == "/api/decisores" or ruta.startswith("/api/sistema/decisor"):
        from decisions import decisores_activos
        return decisores_activos()
    return True


class Handler(dashboard.Handler):
    """Hereda de dashboard.Handler el chequeo de Host, el Origin de los POST, el
    descarte del cuerpo rechazado, `_json` y la CSP; cambia la autenticación
    (cookie de sesión en vez del token del dashboard) y las rutas."""

    _extra = ()

    def end_headers(self):
        for k, v in self._extra:
            self.send_header(k, v)
        super().end_headers()

    def _con(self, *cabeceras):
        self._extra = cabeceras

    def _idioma(self):
        """El que pide la página (cabecera X-WS-Lang); si no, el de Workspace."""
        pedido = (self.headers.get("X-WS-Lang") or "").strip().lower()
        return pedido if pedido in _idiomas() else i18n.lang()

    def _t(self, clave, **kw):
        return _txt(self._idioma(), clave, **kw)

    def _textos(self):
        from decisions import decisores_activos
        activos = decisores_activos()
        # Only the dormant decision views use these strings. Keep shared
        # memory/engine text and the complete source catalogs for coverage.
        prefijos = ("localhost.ui.dec.", "localhost.ui.v2.dec.",
                    "localhost.ui.sistema.decisor.", "localhost.ui.v2.sis.dec.")
        ocultas = {"localhost.ui.nav.decisores", "localhost.ui.sec.decisores",
                   "localhost.ui.feed.dec", "localhost.ui.v2.sec.dec",
                   "localhost.ui.v2.vacio.dec", "localhost.ui.v2.sis.decision",
                   "localhost.ui.v2.rv.dec", "localhost.ui.v2.rv.nodec",
                   "localhost.ui.v2.rv.acerto", "localhost.ui.v2.rv.fallo",
                   "localhost.ui.v2.rv.sinconf", "localhost.ui.v2.rv.vertodas"}
        idioma = self._idioma()
        return {"idioma": idioma,
                "idiomas": [{"codigo": c, "nombre": n} for c, n in i18n.available()],
                "textos": {k: v for k, v in _catalogo(idioma).items()
                           if k.startswith("localhost.ui.")
                           and (activos or not (k.startswith(prefijos) or k in ocultas))}}

    def _cookie_ok(self):
        try:
            c = SimpleCookie(self.headers.get("Cookie") or "")
            llave = c[COOKIE].value if COOKIE in c else ""
        except Exception:
            return False
        return hmac.compare_digest(llave, self.server.llave)

    def _guard_local(self, entrada=False):
        # capas A (Host) y C (Origin) del guard heredado; la B es la llave
        if not self._guard(need_token=False):
            return False
        if entrada:
            return True
        if not self._cookie_ok():
            return self._deny("bad key")
        return True

    def _entrar(self):
        q = parse_qs(urlparse(self.path).query)
        if not hmac.compare_digest((q.get("k") or [""])[0], self.server.llave):
            return self._deny("bad key")
        self._con(("Set-Cookie", "%s=%s; Path=/; HttpOnly; SameSite=Strict"
                   % (COOKIE, self.server.llave)),
                  ("Location", "/"), ("Cache-Control", "no-store"))
        self._send(302, b"", "text/plain; charset=utf-8")

    def do_GET(self):
        ruta = urlparse(self.path).path
        if ruta not in RUTAS_LARGAS:
            return self._do_get(ruta)
        if not self._guard_local():
            return
        clave = self._tomar_espera()
        if clave is False:
            return self._sin_lugar()
        try:
            return self._do_get(ruta, guardado=True)
        finally:
            self._soltar_espera(clave)

    # ── los long-polls, con tope (60 hubs viejos escuchando tumbaban la página) ──
    def _tomar_espera(self):
        """Un lugar para un long-poll (`espera` > 0): en total, por cliente que se identifica (`c`: cada hub y cada
        pestaña de hoy) y para los que no (los de antes, juntos por su programa). → la clave tomada, None si no espera
        (no ocupa lugar) o False si no hay lugar."""
        q = parse_qs(urlparse(self.path).query)
        try:
            espera = float((q.get("espera") or ["0"])[0] or 0)
        except ValueError:
            espera = 0.0
        lugares = getattr(self.server, "esperas", None)
        candado = getattr(self.server, "esperas_lock", None)
        if espera <= 0 or lugares is None or candado is None:
            return None
        c = (q.get("c") or [""])[0]
        if _CLIENTE_RE.match(c):
            clave, tope = "c:" + c, ESPERAS_POR_CLIENTE
        else:
            clave, tope = "sin:" + (self.headers.get("User-Agent") or "")[:80], ESPERAS_SIN_ID
        with candado:
            if sum(lugares.values()) >= ESPERAS_TOTAL or lugares.get(clave, 0) >= tope:
                return False
            lugares[clave] = lugares.get(clave, 0) + 1
        return clave

    def _soltar_espera(self, clave):
        if not clave:
            return
        with self.server.esperas_lock:
            n = self.server.esperas.get(clave, 0) - 1
            if n > 0:
                self.server.esperas[clave] = n
            else:
                self.server.esperas.pop(clave, None)

    def _sin_lugar(self):
        """503 al instante, con «Retry-After»: el que escucha espera y vuelve (un hub de antes, con su respiro)."""
        self._con(("Cache-Control", "no-store"), ("Retry-After", str(REINTENTA_S)))
        cuerpo = {"__err": self._t("localhost.err.muchos"), "ocupado": True, "reintenta": REINTENTA_S}
        self._send(503, json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _do_get(self, ruta, guardado=False):
        if ruta == "/" and "k" in parse_qs(urlparse(self.path).query):
            if not self._guard_local(entrada=True):
                return
            return self._entrar()
        if not guardado and not self._guard_local():
            return
        self._con(("Cache-Control", "no-store"))
        if not _ruta_vista_publica(ruta):
            return self._error(404, "localhost.err.vista_retirada")
        if ruta == "/api/textos":
            return self._json(self._textos())
        if ruta == "/api/ejecuciones":
            q = parse_qs(urlparse(self.path).query)
            agente = (q.get("agente") or [""])[0]
            if not _SLUG_RE.match(agente):
                return self._error(400, "localhost.err.formato")
            d = datos_ejecuciones(agente)
            return self._json(d) if d is not None else self._error(404, "localhost.err.pestana")
        if ruta == "/api/conversacion":
            q = parse_qs(urlparse(self.path).query)
            agente, slug = (q.get("agente") or [""])[0], (q.get("slug") or [""])[0]
            if not _SLUG_RE.match(agente) or not _SLUG_RE.match(slug):
                return self._error(400, "localhost.err.formato")
            try:
                d = datos_conversacion(agente, slug)
            except Exception:
                d = {"soporta": False, "motor": "", "vivo": False}
            if d is None:
                return self._error(404, "localhost.err.pestana")
            if d.get("soporta") is not False:
                d = con_version(agente, slug, d, (q.get("v") or [""])[0])
            c = cambio_de(agente, slug)                # el cambio de motor en curso, con su error en su idioma
            if c:
                d["cambio"] = dict(c, error=self._t(c["error"]) if c["error"] else "")
            return self._json(d)
        if ruta in ("/api/pestana", "/api/pantalla"):
            q = parse_qs(urlparse(self.path).query)
            agente, slug = (q.get("agente") or [""])[0], (q.get("slug") or [""])[0]
            if not _SLUG_RE.match(agente) or not _SLUG_RE.match(slug):
                return self._error(400, "localhost.err.formato")
            try:
                d = (datos_pestana(agente, slug) if ruta == "/api/pestana"
                     else datos_pantalla(agente, slug, ansi=(q.get("ansi") or [""])[0] == "1",
                                         solo_estado=(q.get("estado") or [""])[0] == "1"))
            except Exception:
                d = None
            if d is None:
                return self._error(404, "localhost.err.pestana")
            return self._json(d)
        if ruta in _SIS_GET:
            q = parse_qs(urlparse(self.path).query)
            try:
                r = _SIS_GET[ruta](lambda k: (q.get(k) or [""])[0])
            except Exception:
                return self._error(500, "localhost.err.leer")
            return self._sis_responder(r)
        if ruta in _API:
            try:
                return self._json(_API[ruta]())
            except Exception:
                return self._send(500, json.dumps({"__err": "error"}).encode("utf-8"),
                                  "application/json; charset=utf-8")
        if ruta in _FRONT_GET:
            q = parse_qs(urlparse(self.path).query)
            try:
                r = _FRONT_GET[ruta](lambda k: (q.get(k) or [""])[0])
            except Exception:
                return self._error(500, "localhost.err.leer")
            return self._sis_responder(r)
        if ruta in _V2_GET:
            q = parse_qs(urlparse(self.path).query)
            agente = (q.get("agente") or [""])[0]
            if agente and not _SLUG_RE.match(agente):
                return self._error(400, "localhost.err.formato")
            try:
                r = _V2_GET[ruta](lambda k: (q.get(k) or [""])[0])
            except Exception:
                return self._error(500, "localhost.err.leer")
            return self._sis_responder(r)
        if ruta == "/clasico" and not _clasico_a_la_vista():
            # I21 · la página de antes ya no se sirve (AG3-a): un marcador viejo llega a la nueva. Solo una copia de
            # desarrollo la conserva, para comparar.
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        est = _ESTATICOS.get(ruta)
        if est:
            try:
                with open(os.path.join(est[0], est[1]), "rb") as f:
                    contenido = f.read()
                    if est[1] == "index.html":
                        from decisions import decisores_activos
                        contenido = contenido.replace(b"/* WORKSPACE_DECISORES */ false", b"true" if decisores_activos() else b"false")
                        if est[0] == FRONT and not _front_en_mi_idioma():
                            try:
                                aviso = self._t("puertas.pagina.solo_es")
                            except Exception:            # sin cabeceras (una prueba, un cliente raro): el de Workspace
                                aviso = _txt(i18n.lang(), "puertas.pagina.solo_es")
                            contenido = _con_aviso_idioma(contenido, aviso)
                    return self._send(200, contenido, est[2])
            except OSError:
                pass
        return self._notfound(ruta)

    def _error(self, codigo, clave, **kw):
        self._send(codigo, json.dumps({"__err": self._t(clave, **kw)}, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_POST(self):
        if not self._guard_local():
            return
        # un POST de la página siempre trae Origin: sin él no es de la página
        if not self.headers.get("Origin"):
            return self._deny("no origin")
        ruta = urlparse(self.path).path
        self._con(("Cache-Control", "no-store"))
        if not _ruta_vista_publica(ruta):
            self._drain_rejected_body()
            return self._error(404, "localhost.err.vista_retirada")
        if ruta == "/api/apagar":
            try:                                    # los motores que abrió la página v2, cerrados
                if "pagina_v2" in sys.modules:
                    sys.modules["pagina_v2"].apagar_todo()
            except Exception:
                pass
            self._json({"ok": True})
            self.server.apagado.set()
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        m = _RUTA_MENSAJE.match(ruta)
        if m:
            return self._enviar_mensaje(m.group(1))
        if ruta == "/api/pestana/escribir":
            return self._escribir_pestana()
        if ruta == "/api/pestana/teclas":
            return self._teclas_pestana()
        if ruta == "/api/pestana/enter":
            return self._enter_pestana()
        if ruta == "/api/pestana/quitar":
            return self._quitar_de_cola()
        if ruta == "/api/pestana/forzar":
            return self._forzar_en_cola()
        if ruta == "/api/pestana/abrir":
            return self._abrir_pestana()
        if ruta == "/api/pestana/elegir":
            return self._elegir_opcion()
        if ruta == "/api/skill/usar":
            return self._usar_skill()
        if ruta == "/api/skill/arrancar":
            return self._arrancar_skill()
        if ruta == "/api/ejecucion/archivo":
            return self._subir_archivo()
        if ruta == "/api/adjunto":
            return self._adjunto()
        if ruta == "/api/pestana/nueva":
            return self._nueva_pestana()
        if ruta == "/api/pestana/motor":
            return self._motor_pestana()
        if ruta == "/api/pestana/ajuste":
            return self._ajuste_motor()
        if ruta == "/api/pestana/reabrir":
            return self._reabrir_pestana()
        if ruta == "/api/agente/motor":
            return self._motor_agente()
        if ruta in _SIS_POST:
            return self._sistema_post(ruta)
        if ruta in _FRONT_POST:
            return self._front_post(ruta)
        if ruta in _V2_POST:
            return self._v2_post(ruta)
        return self._notfound(ruta)

    def _v2_post(self, ruta):
        """La página v2: forma y tipos aquí; pagina_v2 escribe por la capa de control."""
        d, err = self._leer_json(limite=MAX_ARCHIVO * 4 // 3 + 4096 if ruta in _V2_CON_ARCHIVO else None)
        if err:
            return self._error(*err)
        fn, esquema = _V2_POST[ruta]
        kw = _sis_campos(d if isinstance(d, dict) else {}, esquema)
        kw = _v2_valido(ruta, kw) if kw is not None else None
        if kw is None:
            return self._error(400, "localhost.err.formato")
        for k in ("texto", "pedido", "nota"):           # lo que llega a un motor: sin control ni llaves
            if kw.get(k):
                e = _v2_texto_seguro(kw[k])
                if e:
                    return self._error(400, e, c="?")
        try:
            r = getattr(_v2(), fn)(**kw)
        except Exception:
            return self._error(500, "localhost.err.leer")
        return self._sis_responder(r)

    def _front_post(self, ruta):
        """Front nuevo (apariencia, tono, archivos del cerebro, preferencias): mismo contrato que
        Sistema; localhost_front vuelve a validar contra lo que hay."""
        # un .md del cerebro puede pasar de los 32 KB de un POST normal (tope propio en localhost_front)
        d, err = self._leer_json(limite=MAX_POST_ARCHIVO if ruta == "/api/front/archivo" else None)
        if err:
            return self._error(*err)
        fn, esquema = _FRONT_POST[ruta]
        kw = _sis_campos(d if isinstance(d, dict) else {}, esquema)
        if kw is None:
            return self._error(400, "localhost.err.formato")
        try:
            r = getattr(_front(), fn)(**kw)
        except Exception:
            return self._error(500, "localhost.err.leer")
        return self._sis_responder(r)

    def _sistema_post(self, ruta):
        """Motores y Usuarios: valida forma y tipos y llama a localhost_sistema,
        que vuelve a validar contra lo que hay (motores, agentes, usuarios)."""
        d, err = self._leer_json()
        if err:
            return self._error(*err)
        fn, esquema = _SIS_POST[ruta]
        kw = _sis_campos(d if isinstance(d, dict) else {}, esquema)
        if kw is None:
            return self._error(400, "localhost.err.formato")
        try:
            r = getattr(_sis(), fn)(**kw)
        except Exception:
            return self._error(500, "localhost.err.leer")
        return self._sis_responder(r)

    def _ocupado(self, oc):
        """409 de «ocupado»: la razón en una línea (su llave amable) y en qué está, para la página."""
        return self._send(409, json.dumps({"__err": self._t(oc["error"], **oc.get("datos", {})), "ocupado": oc["ocupado"]},
                                          ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _sis_responder(self, r):
        """{"ok": false, "error", "status", "datos"} → el error en el idioma de la
        página (con los comandos si los hay: sin herdr se hace en el hub); lo demás tal cual."""
        if isinstance(r, dict) and r.get("ok") is False:
            cuerpo = {"__err": self._t(r.get("error") or "localhost.err.formato", **(r.get("datos") or {})),
                      # la clave y sus datos: la tarjeta del hub elige con ellos el botón que lo arregla
                      "clave": r.get("error") or "localhost.err.formato", "datos": r.get("datos") or {}}
            if r.get("comandos"):
                cuerpo["comandos"] = r["comandos"]
            for marca in ("terminal", "cerrable", "solo_mirar", "abriendo"):     # página v2: qué salida ofrecer
                if r.get(marca):
                    cuerpo[marca] = True
            codigo = r.get("status") if isinstance(r.get("status"), int) and 400 <= r.get("status") < 600 else 400
            return self._send(codigo, json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
                              "application/json; charset=utf-8")
        return self._json(r)

    def _pestana_pedida(self):
        d, err = self._leer_json()
        if err:
            return None, None, err
        agente, slug = d.get("agente"), d.get("slug")
        if not (isinstance(agente, str) and _SLUG_RE.match(agente) and isinstance(slug, str) and _SLUG_RE.match(slug)):
            return None, None, (400, "localhost.err.formato")
        return d, (agente, slug), None

    def _teclas_pestana(self):
        """La terminal misma: lo que el socio teclea en la página llega a su panel,
        texto (send-text) o teclas de la lista blanca (send-keys)."""
        import aviso_panel
        import salas
        d, ids, err = self._pestana_pedida()
        if err:
            return self._error(*err)
        texto, teclas, parar = d.get("texto") or "", d.get("teclas") or [], d.get("parar") is True
        if not isinstance(texto, str) or not isinstance(teclas, list) or len(teclas) > MAX_TECLAS \
                or not all(isinstance(k, str) and k.lower() in TECLAS for k in teclas) or (parar and (texto or teclas)):
            return self._error(400, "localhost.err.formato")
        if len(texto) > MAX_ESCRIBIR:
            return self._error(413, "localhost.err.largo")
        texto = salas._CONTROL_RE.sub("", texto.replace("\r", "").replace("\n", " "))
        if not texto and not teclas and not parar:
            return self._error(400, "localhost.err.vacio")
        try:
            bt, reg = _pestana_y_panel(*ids)
        except Exception:
            bt, reg = None, None
        if bt is None:
            return self._error(404, "localhost.err.pestana")
        if not reg:
            return self._error(409, "localhost.err.no_abierta")
        if parar:                                       # Detener: la tecla la da el adapter de su motor, no la página
            teclas = _teclas_parar(reg.get("motor"))
            _vivo().detener_pedido(ids[0])             # (y el primer paso de «Detener y cambiar»); un esc suelto no

        def mandar():
            if texto and aviso_panel.teclear(reg["panel"], texto, reg.get("socket", "")) is None:
                return False
            if teclas and aviso_panel._herdr(["pane", "send-keys", reg["panel"]] + [tecla_herdr(k) for k in teclas],
                                             reg.get("socket", ""), json_out=False) is None:
                return False
            return True
        if not _en_el_panel(reg, mandar):
            return self._error(409, "localhost.err.panel")
        self._json({"ok": True})

    def _quitar_de_cola(self):
        """«Quitar» tu mensaje `cid` de la cola de su conversación (quitar_de_cola)."""
        d, ids, err = self._pestana_pedida()
        if err:
            return self._error(*err)
        cid = d.get("cid")
        if not (isinstance(cid, str) and _SLUG_RE.match(cid)):
            return self._error(400, "localhost.err.formato")
        r = quitar_de_cola(ids[0], ids[1], cid)
        if r != "ok":
            return self._error(409, "localhost.err.ya_se_manda" if r == "tecleando" else "localhost.err.ya_no_en_cola")
        return self._json({"ok": True})

    def _forzar_en_cola(self):
        """«Mandar igual» tu mensaje `cid`, que espera en la cola por su caja (forzar_en_cola)."""
        d, ids, err = self._pestana_pedida()
        if err:
            return self._error(*err)
        cid = d.get("cid")
        if not (isinstance(cid, str) and _SLUG_RE.match(cid)):
            return self._error(400, "localhost.err.formato")
        r = forzar_en_cola(ids[0], ids[1], cid)
        if r != "ok":
            return self._error(409, {"tecleando": "localhost.err.ya_se_teclea",
                                     "no_toca": "localhost.err.ya_no_espera_caja"}.get(r, "localhost.err.ya_no_en_cola"))
        return self._json({"ok": True})

    def _enter_pestana(self):
        """«Darle Enter» a tu mensaje `cid`, que se quedó escrito en su caja (`atorado`): _enter_en_caja."""
        d, ids, err = self._pestana_pedida()
        if err:
            return self._error(*err)
        cid, (agente, slug) = d.get("cid"), ids
        pend = _ATORADO.get(agente)
        if not (isinstance(cid, str) and slug == NAVEGADOR and pend and pend[0] == cid):
            return self._error(409, "localhost.err.no_salio")       # ya salió, o no es el que se quedó en su caja
        try:
            bt, reg = _pestana_y_panel(agente, slug)
        except Exception:
            bt, reg = None, None
        if not reg:
            return self._error(409, "localhost.err.no_abierta")
        r = _enter_en_caja(reg, pend[1])
        if r == "ok":
            _ATORADO.pop(agente, None)
            anotar_envio(agente, cid, pend[2], reg, pend[1] != pend[2])
            _vivo().envio(agente, cid, "recibido")
            return self._json({"ok": True})
        if r == "cerrado":
            _ATORADO.pop(agente, None)
            _vivo().envio(agente, cid, "no_se_mando")
        cuerpo = {"__err": self._t({"pregunta": "localhost.err.pregunta", "sin_eco": "localhost.err.no_salio",
                                    "atorado": "localhost.err.no_salio"}.get(r, "localhost.err.panel"))}
        if r == "pregunta":
            cuerpo["pregunta"] = True                   # la página enseña el menú como tarjeta (F14)
        return self._send(409, json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _elegir_opcion(self):
        d, ids, err = self._pestana_pedida()
        if err:
            return self._error(*err)
        n = d.get("n")
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 9:
            return self._error(400, "localhost.err.formato")
        try:
            r = elegir_opcion(ids[0], ids[1], n)
        except Exception:
            r = "panel"
        if r == "ok":
            return self._json({"ok": True})
        if r == "no_existe":
            return self._error(404, "localhost.err.pestana")
        return self._error(409, {"no_abierta": "localhost.err.no_abierta", "sin_seleccion": "localhost.err.sin_seleccion"}
                           .get(r, "localhost.err.panel"))

    def _abrir_pestana(self):
        d, ids, err = self._pestana_pedida()
        if err:
            return self._error(*err)
        motor = d.get("motor") or ""
        if not isinstance(motor, str) or (motor and not _SLUG_RE.match(motor)):
            return self._error(400, "localhost.err.formato")
        texto = None
        if d.get("texto") is not None:                  # abrir Y escribirle en cuanto esté lista
            texto, e = self._texto_valido(d.get("texto"))
            if e:
                return self._error(e[0], e[1], **(e[2] if len(e) > 2 else {}))
        cid = self._cid(d) if texto else ""
        if cid is None:
            return self._error(400, "localhost.err.formato")
        nuevo, antes = _vivo().idem_tomar(ids[0], cid)
        if not nuevo:                                   # el mismo envío otra vez: no se abre ni se teclea dos veces
            return self._json(antes)
        try:
            r = abrir_pestana(*ids, motor=motor)
        except Exception:
            r = "sin_herdr"
        if r in ("ya", "abriendo"):
            res = {"ok": True, "estado": r, "pendiente": bool(texto)}
            if texto:
                if ids[1] == NAVEGADOR and cid:
                    _vivo().envio(ids[0], cid, "enviando")
                _en_segundo_plano(_escribir_cuando_quieta, ids[0], ids[1], texto,
                                  cid=cid if ids[1] == NAVEGADOR else "")
            _vivo().idem_guardar(ids[0], cid, res)
            return self._json(res)
        _vivo().idem_guardar(ids[0], cid, None)
        if r == "no_existe":
            return self._error(404, "localhost.err.pestana")
        return self._error(409, "localhost.err.abrir_" + r)

    @staticmethod
    def _cid(d):
        """El id que la página le pone a un envío ("" si no trae; None si no es válido)."""
        cid = d.get("cid") or ""
        return cid if isinstance(cid, str) and (not cid or _SLUG_RE.match(cid)) else None

    def _motor_pestana(self):
        d, ids, err = self._pestana_pedida()
        if err:
            return self._error(*err)
        motor = d.get("motor")
        if not isinstance(motor, str) or not _SLUG_RE.match(motor):
            return self._error(400, "localhost.err.formato")
        forzar = bool(d.get("forzar"))
        oc = _vivo().ocupado(ids[0]) if ids[1] == NAVEGADOR else None
        # ocupado: no se cambia (pedido del socio). Salidas: «Volver» de un cambio atorado (cambiar_motor decide si ya
        # pasó su tiempo normal) y «Cerrar y cambiar» después de pedirle que se detenga, o ya, si su motor está detenido
        # en una pregunta o un permiso de su terminal (H14: ahí «Detener» no lo saca).
        if oc and not (forzar and (oc["ocupado"] == "cambiando" or _vivo().detuvo_hace(ids[0]) >= _vivo().DETENER_GRACIA_S
                                   or _en_pregunta(*ids))):
            return self._ocupado(oc)
        try:
            r = cambiar_motor(*ids, motor, forzar=forzar)
        except Exception:
            r = "sin_herdr"
        if r in ("abriendo", "ya"):
            return self._json({"ok": True, "estado": "abriendo"})
        if r == "no_existe":
            return self._error(404, "localhost.err.pestana")
        if r in ("trabajando", "atorado"):
            clave = "localhost.err.trabajando" if r == "trabajando" else "localhost.err.atorado_cambio"
            return self._send(409, json.dumps({"__err": self._t(clave), r: True}, ensure_ascii=False).encode("utf-8"),
                              "application/json; charset=utf-8")
        return self._error(409, "localhost.err.motor_" + r if r in ("motor", "mismo", "en_ventana", "panel") else "localhost.err.abrir_" + r)

    def _ajuste_motor(self):
        """§6: un botón de modelo, esfuerzo o modo de la conversación de la página (aplicar_ajuste)."""
        d, err = self._leer_json()
        if err:
            return self._error(*err)
        agente, ajuste, valor = d.get("agente"), d.get("ajuste"), d.get("valor")
        if not (isinstance(agente, str) and _SLUG_RE.match(agente) and isinstance(ajuste, str) and isinstance(valor, str)):
            return self._error(400, "localhost.err.formato")
        try:
            r, datos = aplicar_ajuste(agente, ajuste, valor)
        except Exception:
            r, datos = "error", "localhost.err.panel"
        if r == "ocupado":
            return self._ocupado(datos)
        if r == "error":
            return self._error(409, datos)
        return self._json(dict(datos, ok=True))

    def _reabrir_pestana(self):
        """«Reabrir ahora»: la misma conversación con su mismo motor (lo guardado para su arranque se aplica), como un
        cambio de motor: guarda lo hablado, la maleta, y la abre de nuevo. Solo si está libre."""
        d, err = self._leer_json()
        if err:
            return self._error(*err)
        agente = d.get("agente")
        if not (isinstance(agente, str) and _SLUG_RE.match(agente)):
            return self._error(400, "localhost.err.formato")
        oc = _vivo().ocupado(agente)
        if oc:
            return self._ocupado(oc)
        try:
            _bt, reg = _pestana_y_panel(agente, NAVEGADOR)
            r = cambiar_motor(agente, NAVEGADOR, reg.get("motor"), reabrir=True) if reg else "no_abierta"
        except Exception:
            r = "sin_herdr"
        if r in ("abriendo", "ya"):
            return self._json({"ok": True, "estado": "abriendo"})
        if r in ("no_abierta", "no_existe"):
            return self._error(409, "localhost.err.no_abierta")
        if r == "trabajando":
            return self._error(409, "localhost.err.trabajando")
        return self._error(409, "localhost.err.motor_" + r if r in ("motor", "en_ventana", "panel") else "localhost.err.abrir_" + r)

    def _nueva_pestana(self):
        d, err = self._leer_json()
        if err:
            return self._error(*err)
        agente, nombre, motor = d.get("agente"), d.get("nombre"), d.get("motor") or ""
        if not (isinstance(agente, str) and _SLUG_RE.match(agente) and isinstance(nombre, str)
                and isinstance(motor, str) and (not motor or _SLUG_RE.match(motor))):
            return self._error(400, "localhost.err.formato")
        texto = None
        if d.get("texto") is not None:                  # el primer mensaje: se le da cuando termine de arrancar
            texto, e = self._texto_valido(d.get("texto"))
            if e:
                return self._error(e[0], e[1], **(e[2] if len(e) > 2 else {}))
        try:
            r, slug = nueva_pestana(agente, nombre, motor)
            k = 2
            while r == "existe" and texto and k < 30:   # empezar desde cero no debe chocar con un nombre usado
                r, slug = nueva_pestana(agente, "%s %d" % (nombre, k), motor)
                k += 1
        except Exception:
            r, slug = "sin_herdr", ""
        if r == "abriendo":
            if texto:
                _en_segundo_plano(_escribir_cuando_quieta, agente, slug, texto)
            return self._json({"ok": True, "estado": r, "slug": slug, "pendiente": bool(texto)})
        if r == "no_existe":
            return self._error(404, "localhost.err.pestana")
        return self._error(409, "localhost.err.nueva_" + r if r in ("nombre", "existe") else "localhost.err.abrir_" + r)

    def _usar_skill(self):
        d, err = self._leer_json()
        if err:
            return self._error(*err)
        agente, skill, texto, slug = d.get("agente"), d.get("skill"), d.get("texto") or "", d.get("slug") or ""
        motor = d.get("motor") or ""
        if not (isinstance(agente, str) and _SLUG_RE.match(agente) and isinstance(skill, str) and skill.strip()
                and isinstance(texto, str) and isinstance(slug, str) and (not slug or _SLUG_RE.match(slug))
                and isinstance(motor, str) and (not motor or _SLUG_RE.match(motor))):
            return self._error(400, "localhost.err.formato")
        import salas
        if salas._CONTROL_RE.search(texto):
            return self._error(400, "localhost.err.formato")
        if (slug or NAVEGADOR) == NAVEGADOR:            # una skill por agente, y no encima de lo que hace
            oc = _vivo().ocupado(agente) or _vivo().ocupado_skill(agente)
            if oc:
                return self._ocupado(oc)
        try:
            r, info = usar_skill(agente, skill, texto, slug, motor)
        except Exception:
            r, info = "sin_herdr", None
        if r == "ok":
            return self._json(dict(info, ok=True))
        if r == "no_existe":
            return self._error(404, "localhost.err.pestana")
        return self._error(409, "localhost.err.abrir_" + r if r in ("sin_herdr", "motor") else "localhost.err.no_abierta")

    def _arrancar_skill(self):
        d, err = self._leer_json()
        if err:
            return self._error(*err)
        agente, ejecucion = d.get("agente"), d.get("id")
        if not (isinstance(agente, str) and _SLUG_RE.match(agente) and isinstance(ejecucion, str) and _SLUG_RE.match(ejecucion)):
            return self._error(400, "localhost.err.formato")
        try:
            r = _escribir_ejecucion(agente, ejecucion)
        except Exception:
            r = "no_abierta"
        if r == "ok":
            return self._json({"ok": True})
        return self._error(404 if r == "no_existe" else 409, "localhost.err.pestana" if r == "no_existe" else "localhost.err.no_abierta")

    def _subir_archivo(self):
        """JSON {agente, id, nombre, datos(base64)}: hasta MAX_ARCHIVO (solo esta ruta pasa de MAX_POST)."""
        d, err = self._leer_json(limite=MAX_ARCHIVO * 4 // 3 + 4096)
        if err:
            return self._error(*err)
        agente, ejecucion, nombre, datos = d.get("agente"), d.get("id"), d.get("nombre"), d.get("datos")
        if not (isinstance(agente, str) and _SLUG_RE.match(agente) and isinstance(ejecucion, str) and _SLUG_RE.match(ejecucion)
                and isinstance(nombre, str) and isinstance(datos, str)):
            return self._error(400, "localhost.err.formato")
        try:
            r, rel = guardar_archivo(agente, ejecucion, nombre, datos)
        except Exception:
            r, rel = "interno", None
        if r in ("ok", "guardado_sin_aviso"):
            return self._json({"ok": True, "ruta": rel, "avisado": r == "ok"})
        if r == "no_existe":
            return self._error(404, "localhost.err.pestana")
        return self._error(413 if r == "largo" else 400, "localhost.err.largo" if r == "largo" else "localhost.err.formato")

    def _adjunto(self):
        """JSON {agente, nombre, datos(base64)}: hasta MAX_ARCHIVO, al cerebro del agente."""
        d, err = self._leer_json(limite=MAX_ARCHIVO * 4 // 3 + 4096)
        if err:
            return self._error(*err)
        agente, nombre, datos = d.get("agente"), d.get("nombre"), d.get("datos")
        if not (isinstance(agente, str) and _SLUG_RE.match(agente) and isinstance(nombre, str) and isinstance(datos, str)):
            return self._error(400, "localhost.err.formato")
        try:
            r, rel = guardar_adjunto(agente, nombre, datos)
        except Exception:
            r, rel = "interno", None
        if r == "ok":
            return self._json({"ok": True, "ruta": rel})
        if r == "no_existe":
            return self._error(404, "localhost.err.pestana")
        return self._error(413 if r == "largo" else 400, "localhost.err.largo" if r == "largo" else "localhost.err.formato")

    def _motor_agente(self):
        """El motor por defecto de un agente en ESTA máquina (agent_manage.set_engine, como
        la sección Agentes del hub)."""
        d, err = self._leer_json()
        if err:
            return self._error(*err)
        agente, motor = d.get("agente"), d.get("motor")
        if not (isinstance(agente, str) and _SLUG_RE.match(agente) and isinstance(motor, str) and _SLUG_RE.match(motor)):
            return self._error(400, "localhost.err.formato")
        if motor not in _motores_listos():
            return self._error(409, "localhost.err.motor_motor")
        try:
            import agent_manage
            r = agent_manage.set_engine(agente, motor)
        except Exception:
            r = {"ok": False}
        if not r.get("ok"):
            return self._error(409, "localhost.err.interno")
        self._json({"ok": True})

    def _texto_valido(self, texto):
        """El texto que se teclea en un panel: un renglón, sin control ni llaves. → (texto, err)."""
        import salas
        import secret_scan
        if not isinstance(texto, str) or not texto.strip():
            return None, (400, "localhost.err.vacio")
        texto = " ".join(texto.replace("\r", "\n").split("\n")).strip()
        if len(texto) > MAX_ESCRIBIR:
            return None, (413, "localhost.err.largo")
        c = salas._CONTROL_RE.search(texto)
        if c:
            return None, (400, "localhost.err.control", {"c": "%04X" % ord(c.group(0))})
        try:
            if secret_scan.scan_text(texto):
                return None, (400, "localhost.err.llave")
        except Exception:
            return None, (500, "localhost.err.interno")
        return texto, None

    def _escribir_pestana(self):
        """Le escribe a la pestaña en su panel de herdr, como si el socio lo tecleara
        en su ventana: un renglón y Enter. Mismo camino que el aviso de salas
        (aviso_panel.escribir): verifica bajo candado que el panel siga vivo y que
        ahí corra su motor, nunca una shell. Si está trabajando, solo con
        `forzar` (el motor lo encola). Con `cid` (id de la página) no se teclea dos veces lo mismo."""
        import salas
        import secret_scan
        d, err = self._leer_json()
        if err:
            return self._error(*err)
        agente, slug, texto = d.get("agente"), d.get("slug"), d.get("texto")
        if not (isinstance(agente, str) and _SLUG_RE.match(agente) and isinstance(slug, str) and _SLUG_RE.match(slug)):
            return self._error(400, "localhost.err.formato")
        if not isinstance(texto, str) or not texto.strip():
            return self._error(400, "localhost.err.vacio")
        texto = " ".join(texto.replace("\r", "\n").split("\n")).strip()
        if len(texto) > MAX_ESCRIBIR:
            return self._error(413, "localhost.err.largo")
        c = salas._CONTROL_RE.search(texto)
        if c:
            return self._error(400, "localhost.err.control", c="%04X" % ord(c.group(0)))
        try:
            if secret_scan.scan_text(texto):
                return self._error(400, "localhost.err.llave")
        except Exception:
            return self._error(500, "localhost.err.interno")
        cid = self._cid(d)
        if cid is None:
            return self._error(400, "localhost.err.formato")
        nuevo, antes = _vivo().idem_tomar(agente, cid)
        if not nuevo:                           # el mismo envío otra vez (doble clic, otra pestaña): no se teclea dos veces
            return self._json(antes)
        r = self._escribir_en_panel(agente, slug, texto, bool(d.get("forzar")), cid)
        _vivo().idem_guardar(agente, cid, r if r.get("ok") else None)
        if r.get("ok"):
            return self._json(r)
        cuerpo = {"__err": self._t(r["error"])}
        cuerpo.update({k: True for k in ("pregunta", "trabajando", "en_cola") if r.get(k)})
        return self._send(r["status"], json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
                          "application/json; charset=utf-8")

    def _escribir_en_panel(self, agente, slug, texto, forzar, cid):
        """→ {"ok": True[, "en_cola"]} o {"ok": False, "error", "status"[, "pregunta"|"trabajando"|"en_cola"]}."""
        try:
            bt, reg = _pestana_y_panel(agente, slug)
        except Exception:
            bt, reg = None, None
        if bt is None:
            return {"ok": False, "error": "localhost.err.pestana", "status": 404}
        if not reg:
            return {"ok": False, "error": "localhost.err.no_abierta", "status": 409}
        nav = slug == NAVEGADOR and cid
        if nav and _COLA.get((agente, slug)):   # ya hay mensajes esperando: este va detrás, en orden
            _en_segundo_plano(_escribir_cuando_quieta, agente, slug, texto, cid=cid)
            return {"ok": True, "en_cola": True, "motivo": "detras"}
        if nav and _en_arranque((agente, slug)) and not forzar:
            # W2: el primero tras un cambio espera en la cola a que su arranque termine (no se teclea dentro de él)
            _en_segundo_plano(_escribir_cuando_quieta, agente, slug, texto, cid=cid, motivo="arrancando")
            return {"ok": True, "en_cola": True, "motivo": "arrancando"}
        if nav:
            _vivo().envio(agente, cid, "enviando")
        linea, marcar = _con_nota(agente, slug, reg, texto)
        r = _escribir_en_caja(reg, linea, forzar)
        _nota_dicha(r, marcar)
        if r == "ok":
            _ya_mando((agente, slug))
            if slug == NAVEGADOR:
                anotar_envio(agente, cid, texto, reg, bool(marcar))
            if nav:
                _vivo().envio(agente, cid, "recibido")
            return {"ok": True, "recibido": True, "contexto": bool(marcar)}
        if nav and r in ("trabajando", "sin_caja", "pregunta", "caja_ocupada"):
            # F8: no rebota ni desaparece: queda en cola visible (con su motivo) y sale solo cuando su caja esté lista
            _en_segundo_plano(_escribir_cuando_quieta, agente, slug, texto, cid=cid, motivo=r)
            return {"ok": True, "en_cola": True, "motivo": r}
        if nav:
            if r == "atorado":
                _ATORADO[agente] = (cid, linea, texto)
            _vivo().envio(agente, cid, r if r in ("sin_eco", "atorado") else "no_se_mando" if r == "cerrado" else "fallo")
        return {"ok": False, "status": 409, "error": {"pregunta": "localhost.err.pregunta", "trabajando": "localhost.err.trabajando",
                                                      "sin_caja": "localhost.err.sin_caja", "sin_eco": "localhost.err.no_salio",
                                                      "caja_ocupada": "localhost.err.caja_ocupada",
                                                      "atorado": "localhost.err.no_salio"}.get(r, "localhost.err.panel"),
                **({r: True} if r in ("pregunta", "trabajando") else {})}

    def _leer_json(self, limite=None):
        """(dict, None) o (None, (código, clave de error)). Nunca lee más de `limite`
        (MAX_POST salvo la subida de archivos de una skill)."""
        err = None
        if "application/json" not in (self.headers.get("Content-Type") or "").lower():
            err = (415, "localhost.err.formato")
        else:
            try:
                n = int(self.headers.get("Content-Length") or "")
            except ValueError:
                n = -1
            if n < 0:
                err = (400, "localhost.err.formato")
            elif n > (limite or MAX_POST):
                err = (413, "localhost.err.largo")
        if err:
            self._drain_rejected_body()      # sin leerlo, Windows corta con RST
            return None, err
        try:
            d = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, OSError):
            return None, (400, "localhost.err.formato")
        return (d, None) if isinstance(d, dict) else (None, (400, "localhost.err.formato"))

    def _enviar_mensaje(self, sala_id):
        import salas
        d, err = self._leer_json()
        if err:
            return self._error(*err)
        texto, para = d.get("texto"), d.get("para")
        if not isinstance(texto, str) or not texto.strip():
            return self._error(400, "localhost.err.vacio")
        texto = texto.strip()
        if len(texto) > MAX_ENVIO:
            return self._error(413, "localhost.err.largo")
        if para is not None and not isinstance(para, str):
            return self._error(400, "localhost.err.formato")
        c = salas._CONTROL_RE.search(texto)
        if c:       # publicar_socio no lo revisa: se guardaría corrompido
            return self._error(400, "localhost.err.control", c="%04X" % ord(c.group(0)))
        try:
            sala = salas.encontrar(sala_id)
        except Exception:
            sala = None
        if sala is None or _de_otro_socio(salas, sala, {}):
            return self._error(404, "localhost.err.sala")
        claves = {p["key"] for p in _destinos(sala)}
        if para is None:
            para = _destino_defecto(salas, sala, claves)
        elif para not in claves:
            return self._error(400, "localhost.err.destino")
        try:
            # al invitado que aún no entró el hub le escribe por el nombre del agente
            mid = salas.publicar_socio(sala["id"], texto,
                                       para=[salas.agente_de(para) if para.startswith("?") else para])
        except salas.Error as e:
            return self._send(409, json.dumps({"__err": str(e)}, ensure_ascii=False).encode("utf-8"),
                              "application/json; charset=utf-8")
        except Exception:
            return self._error(500, "localhost.err.interno")
        est = _estado(salas, sala, para)
        nombre = salas.nombre_de(sala, para)
        self._json({"ok": True, "id": mid, "estado": est, "para": para,
                    "aviso": self._t("localhost.msg." + est, a=nombre)})

    def _no_permitido(self):
        if self._guard_local():
            self._send(405, b"", "text/plain; charset=utf-8")

    do_OPTIONS = do_PUT = do_DELETE = do_PATCH = _no_permitido


#: Los long-polls (vuelven en cuanto algo cambia o a los 25 s) y cuántos atiende la página a la vez: en total, por
#: cliente que se identifica (`c`: cada hub y cada pestaña del navegador de hoy) y por los que no (los de antes, juntos
#: por su programa). Los de más reciben un 503 al instante con «Retry-After». Antes, 65 hubs abiertos en paneles de
#: la terminal tenían ~3 conexiones cada uno: 185 hilos y la página a 130 % de CPU, sin contestarle a nadie más.
RUTAS_LARGAS = ("/api/v2/vivo", "/api/front/vivo")
ESPERAS_TOTAL = 16
ESPERAS_POR_CLIENTE = 2
ESPERAS_SIN_ID = 4
#: Hilos que atienden a la vez (uno por conexión): por encima, un 503 rápido sin abrir otro.
HILOS_MAX = 64
REINTENTA_S = 5
_CLIENTE_RE = re.compile(r"^[A-Za-z0-9_-]{4,40}$")


class _Servidor(ThreadingHTTPServer):
    """Servidor con el puerto EXCLUSIVO: la llave viaja en el primer GET al
    puerto, y si otro proceso pudiera atar el mismo 127.0.0.1:puerto la
    recibiría antes que el navegador. HTTPServer trae allow_reuse_address=1
    (SO_REUSEADDR); en Windows eso permite ese doble bind."""

    allow_reuse_address = False
    daemon_threads = True
    #: la cola de conexiones por aceptar: con 5 (la de socketserver), 60 hubs reconectándose a la vez a una página
    #: recién nacida se quedaban sin lugar (Windows contesta «rechazada» y un hub de antes buscaba otra página)
    request_queue_size = 128

    def __init__(self, *a, **kw):
        self._hilos, self._hilos_lock = 0, threading.Lock()
        super().__init__(*a, **kw)
    #: los hilos que atienden a la vez (uno por conexión): por encima, un 503 rápido sin abrir otro
    hilos_max = HILOS_MAX

    def server_bind(self):
        # antes del bind, o no vale
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def process_request(self, request, client_address):
        """Un hilo por conexión, con tope: si ya hay `hilos_max` atendiendo, se le contesta 503 aquí mismo (se lee su
        petición primero: un cierre sin leer llega como «conexión rota» y un hub de antes buscaría otra página)."""
        with self._hilos_lock:
            lleno = self._hilos >= self.hilos_max
            if not lleno:
                self._hilos += 1
        if lleno:
            _contestar_lleno(request)
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            with self._hilos_lock:
                self._hilos -= 1
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._hilos_lock:
                self._hilos -= 1


def _contestar_lleno(request, tope=0.25):
    """El 503 de «demasiados a la vez», sin hilo: lee la cabecera (hasta `tope` s) y contesta en corto."""
    try:
        request.settimeout(tope)
        visto = b""
        while b"\r\n\r\n" not in visto and len(visto) < 65536:
            trozo = request.recv(4096)
            if not trozo:
                break
            visto += trozo
    except OSError:
        pass
    cuerpo = json.dumps({"__err": "ocupado", "ocupado": True, "reintenta": REINTENTA_S}).encode("utf-8")
    try:
        request.sendall(b"HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json; charset=utf-8\r\n"
                        b"Retry-After: %d\r\nCache-Control: no-store\r\nContent-Length: %d\r\n"
                        b"Connection: close\r\n\r\n" % (REINTENTA_S, len(cuerpo)) + cuerpo)
    except OSError:
        pass


def crear_servidor(puerto=0):
    """Servidor en 127.0.0.1 con una llave nueva (no arrancado)."""
    srv = _Servidor(("127.0.0.1", puerto), Handler)
    srv.public = False
    srv.llave = secrets.token_urlsafe(24)
    srv.apagado = threading.Event()
    srv.esperas, srv.esperas_lock = {}, threading.Lock()        # los long-polls en curso (Handler._tomar_espera)
    return srv


def enlace(srv):
    return "http://127.0.0.1:%d/?k=%s" % (srv.server_address[1], srv.llave)


def serve(puerto=0, abrir=True):
    srv = crear_servidor(puerto)
    url = enlace(srv)
    abierto = False
    if abrir and os.environ.get("WORKSPACE_SIN_NAVEGADOR") != "1":        # las pruebas nunca (tests/_testutil)
        try:
            abierto = bool(webbrowser.open(url))
        except Exception:
            abierto = False
    # el link lleva la llave: solo se imprime si el navegador no pudo abrirlo
    if abierto:
        print(i18n.t("localhost.abierto"))
    else:
        print(i18n.t("localhost.abrir", url=url))
        print(i18n.t("localhost.no_compartir"))
    print(i18n.t("localhost.apagar"))
    _salir_con_las_senales()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


def _salir_con_las_senales():
    """SIGTERM y SIGHUP (cerrar la ventana de la página) salen como un Ctrl+C: así corre lo que está en atexit (los
    servidores que encendió la página v2 y los motores de la capa de control). Sin esto, el proceso moría ahí mismo
    y dejaba huérfano su `opencode serve`. Solo desde el hilo principal; falla-suave."""
    import signal

    def salir(_sig, _frame):
        raise KeyboardInterrupt
    for nombre in ("SIGTERM", "SIGHUP"):
        s = getattr(signal, nombre, None)
        if s is None:
            continue
        try:
            signal.signal(s, salir)
        except (ValueError, OSError):
            pass


if __name__ == "__main__":
    sys.exit(serve())
