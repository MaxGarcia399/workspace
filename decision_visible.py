#!/usr/bin/env python3
"""WORKSPACE · decision_visible — lo que se VE de Decisores.

Las líneas «◆ <modelo>: …» que ve el socio (en el chat, en el aviso del hub, en
la barra de estado), lo que cambió cada decisión (Historial), la línea de la
última sesión (Evals, Skills) y el aviso al agente cuando Decisores cambia a
media sesión.

Todo pasa por `encendido()`: con Decisores APAGADO (sin modelo, o ningún uso
prendido) ninguna función de aquí agrega nada — ni líneas, ni contadores, ni
inyección, ni archivos — y lo de siempre sale byte-idéntico. Observe es en
silencio: solo suggest y apply se ven. Stdlib, falla-suave (jamás levanta
hacia quien llama). Mac y Windows.
"""
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SIMBOLO = "◆"
#: Errores de entrada (no se le preguntó a nadie): sin línea para el socio.
_SIN_LINEA = ("bad_point", "need_question", "need_options", "bad_input", "off", "use_off")
#: La línea de la última sesión caduca (una sesión de hace semanas ya no es «la última»).
ULTIMA_MAX_S = 14 * 86400
#: Las líneas de base por sesión (aviso a media sesión) se limpian solas.
SESION_MAX_S = 14 * 86400
#: Lo que se lee de la cola de la bitácora para contar «hoy» (barato: la barra
#: de estado lo pide en cada refresco, en un proceso nuevo cada vez).
HOY_COLA_BYTES = 256 * 1024


def _t(key, es, **kw):
    """Sigue ui.lang (lo que lee el socio y el agente)."""
    try:
        import decision_errors
        return decision_errors._t(key, es, **kw)
    except Exception:
        try:
            return es.format(**kw) if kw else es
        except Exception:
            return es


def _D():
    import decisions
    return decisions


def encendido():
    """¿Decisores está prendido? Un modelo activo y al menos un uso que no esté
    apagado. Sin eso, nada de lo de este módulo se ve ni se escribe."""
    if not _D().decisores_activos():
        return False
    try:
        D = _D()
        if D.global_model() == D.OFF:
            return False
        return any(D.point_conf(p)["level"] != "off" for p in D.POINT_IDS)
    except Exception:
        return False


def _nombre(did):
    """El nombre (META label) del modelo que respondió; sin dato, el general; sin
    modelo, «Decisores». Nunca un nombre fijo: cambia con cada modelo de decisión."""
    try:
        D = _D()
        did = did or D.global_model()
        return D.decider_label(did) if did and did != D.OFF else "Decisores"
    except Exception:
        return str(did or "Decisores").capitalize()


def sin_conexion(did):
    """¿Este decisor en la nube se quedó SIN CONEXIÓN hace un momento? (la pausa
    tras un fallo de red con el código «connection»: decisions.breaker_open).
    Es el estado de la RED, no el del modelo: la llave sigue guardada y el
    modelo sigue listo; Workspace vuelve a probar solo al vencer la pausa.
    Falla-suave: False."""
    try:
        p = _D().breaker_open(did)
        return bool(p) and p[0] == "connection"
    except Exception:
        return False


def sin_conexion_txt():
    """«sin conexión · reintento solo» — lo mismo en el hub, Decisores y Motores."""
    return _t("decisores.st.offline", "sin conexión · reintento solo")


def _pct(p):
    try:
        if p is None:
            return None
        return int(round(float(p) * 100))
    except (TypeError, ValueError):
        return None


def _corto(texto, tope=48):
    s = " ".join(str(texto or "").split())
    return s if len(s) <= tope else s[:tope - 1].rstrip() + "…"


def _letra(i):
    try:
        i = int(i)
    except (TypeError, ValueError):
        return ""
    return chr(ord("A") + i) if 0 <= i < 26 else str(i + 1)


def _eleccion(choice, index=None, tope=40):
    """La opción como se le dice al socio: su texto, o «opción B» si es larga
    (una instrucción entera en Mejor prompt)."""
    s = " ".join(str(choice or "").split())
    if len(s) <= tope or index is None:
        return _corto(s, tope + 8)
    return _t("decisores.visible.option", "opción {l}", l=_letra(index))


# ── EL formato de toda intervención ─────────────────────────────────────────
def para_el_socio():
    """El recordatorio que va JUNTO a cada línea ◆ que le llega al agente: no
    depende de que recuerde la regla de su arranque (un motor envuelto la
    pierde al compactar)."""
    return _t("decisores.visible.para_el_socio", "Muéstrale esta línea al socio en tu bloque ◆ "
              "al final de tu respuesta.")


def _modo(modo):
    return (_t("decisores.visible.applied", "aplicado") if modo == "apply"
            else _t("decisores.visible.suggested", "sugerido"))


def formato(m, que, p, modo):
    """«◆ <modelo>: <qué hizo> · <NN %> · <aplicado|sugerido>» — el MISMO
    formato en el chat (display, Memoria, Seguridad, la última sesión, lo que
    el agente no vio). Sin el %, si el modelo no dio su probabilidad."""
    if not _D().decisores_activos():
        return ""
    if p is None:
        return _t("decisores.visible.line_nop", "{s} {m}: {que} · {q}", s=SIMBOLO, m=m, que=que,
                  q=_modo(modo))
    return _t("decisores.visible.line", "{s} {m}: {que} · {p} % · {q}", s=SIMBOLO, m=m, que=que,
              p=p, q=_modo(modo))


# ── (a) la línea `display` de una consulta de agente ────────────────────────
def linea_agente(out):
    """«◆ <modelo>: tabla · 87 % · sugerido» / «… · aplicado» para la respuesta de
    `workspace decidir` / `decidir` (el agente se la muestra al socio). '' en
    observe (solo se anota), con el uso apagado o si no se mandó nada."""
    if not _D().decisores_activos():
        return ""
    try:
        if not isinstance(out, dict):
            return ""
        m = _nombre(out.get("decider"))
        if not out.get("ok"):
            if out.get("mode") != "error" or out.get("error_code") in _SIN_LINEA:
                return ""
            sin_red = out.get("error_code") == "connection"
            if (out.get("error_detail") or {}).get("breaker"):     # ni se le preguntó
                if sin_red:
                    return _t("decisores.visible.agent_offline_paused", "{s} {m}: sin conexión · "
                              "reintento solo · decide el agente", s=SIMBOLO, m=m)
                return _t("decisores.visible.agent_paused", "{s} {m}: en pausa tras un fallo de "
                          "red · decide el agente", s=SIMBOLO, m=m)
            if sin_red:                  # la red, no el modelo (ni la llave)
                return _t("decisores.visible.agent_offline", "{s} {m}: sin conexión · decide el "
                          "agente", s=SIMBOLO, m=m)
            return _t("decisores.visible.agent_failed", "{s} {m}: no respondió · decide el agente",
                      s=SIMBOLO, m=m)
        modo = out.get("mode")
        if modo not in ("suggest", "apply"):
            return ""
        return formato(m, _eleccion(out.get("choice"), out.get("index")), _pct(out.get("p")), modo)
    except Exception:
        return ""


# ── (b) Seguridad: la línea que se suma al aviso ────────────────────────────
def linea_seguridad(v):
    """«◆ <modelo>: subió el aviso a riesgo alto · 92 % · aplicado» (decide, «alto»)
    o «◆ <modelo>: ve riesgo bajo; el aviso no cambia · 97 % · sugerido» (todo lo
    demás: el decisor puede subir el riesgo, nunca bajarlo). '' en observe o
    apagado."""
    if not _D().decisores_activos():
        return ""
    try:
        if not v or v.get("mode") not in ("suggest", "apply"):
            return ""
        c = str(v.get("choice") or "").strip().lower()
        p = _pct(v.get("p")) if v.get("p_known", True) else None
        sube = v.get("mode") == "apply" and c == "alto"
        return formato(_nombre(v.get("decider")), _que("workspace.security", c, sube), p,
                       "apply" if sube else "suggest")
    except Exception:
        return ""


def _que(point, c, aplicado, nota=""):
    """El «qué hizo» de cada uso, en palabras del socio."""
    c = " ".join(str(c or "").split())
    if point == "workspace.memory":
        return (_t("decisores.visible.q_memory_apply", "guardé la nota como {c}", c=c) if aplicado
                else _t("decisores.visible.q_memory", "la nota parece {c}", c=c))
    if point == "workspace.security":
        return (_t("decisores.visible.q_security_apply", "subió el aviso a riesgo alto") if aplicado
                else _t("decisores.visible.q_security", "ve riesgo {c}; el aviso no cambia", c=c))
    if point == "workspace.evals":
        # nada cambia con la respuesta (solo se anota para la sección Evals):
        # «parece» en todos los niveles, nunca «quedó» (0.9.1)
        return _t("decisores.visible.q_evals", "tu última sesión parece «{c}»", c=c)
    if point == "workspace.conversations":
        if c == "solo informa":
            return (_t("decisores.visible.q_conv_info_apply", "lo tomé como aviso: no despertó a nadie")
                    if aplicado else _t("decisores.visible.q_conv_info", "este pedido parece que solo informa"))
        if c in ("en bucle", "se desvió"):
            return (_t("decisores.visible.q_conv_pause_apply", "pausé la sala: parece {c}", c=c)
                    if aplicado else _t("decisores.visible.q_conv_pause", "la sala parece {c}", c=c))
        if c == "sí":
            return _t("decisores.visible.q_conv_done", "parece cumplido: ciérrala con conversar cerrar")
        return _t("decisores.visible.q_conv", "«{c}»", c=c)
    if point == "workspace.skills":
        que = (_t("decisores.visible.q_skills_yes", "tu última sesión amerita una skill")
               if c.lower() in ("sí", "si", "yes") else
               _t("decisores.visible.q_skills_no", "tu última sesión no amerita una skill"))
        if nota == "throttled":
            que += " (%s)" % _t("decisores.visible.skills_throttled", "sin revisión: hubo otra hace poco")
        elif nota == "delivered":
            que += " (%s)" % _t("decisores.visible.skills_delivered", "la revisión se entregó igual")
        return que
    return c


def linea_entrada(e):
    """La línea de una decisión de la bitácora (lo que el agente no vio)."""
    if not _D().decisores_activos():
        return ""
    try:
        c = e.get("choice")
        modo = e.get("mode")
        p = _pct(e.get("p"))
        point = str(e.get("point") or "")
        aplicado = modo == "apply"
        if point == "workspace.security":
            aplicado = aplicado and str(c or "").strip().lower() == "alto"
            modo = "apply" if aplicado else "suggest"
        nota = ""
        if point == "workspace.skills":
            # lo que de verdad pasó con la revisión (resultado), no solo la
            # opinión: «no amerita» mientras la revisión se pidió igual era
            # una contradicción (W6, 8-nov)
            r = e.get("resultado")
            si = str(c or "").strip().lower() in ("sí", "si", "yes")
            if r == "frenada":
                nota = "throttled"
            elif r in ("pendiente", "entregada") and not si:
                nota = "delivered"
        que = (_que(point, c, aplicado, nota=nota) if point.startswith("workspace.")
               else _eleccion(c, _indice(e)))
        return formato(_nombre(e.get("decider")), que, p, modo)
    except Exception:
        return ""


# ── (d) «¿pasó?»: qué pasó DESPUÉS de cada decisión (0.9.1) ─────────────────
#: Cuánto se espera un resultado antes de darlo por no ocurrido (lo que se
#: comprueba solo) o por no reportado (lo que reporta el agente).
VENTANA_S = {"workspace.security": 30 * 60, "agents.route": 3600, "c3": 30 * 60,
             "agents": 24 * 3600}


#: Los textos de cada resultado, por idioma (se arman UNA vez: antes eran ~20
#: búsquedas de i18n por cada fila del Historial — revisor 0.9.1, costo).
_TEXTOS = {}


def _idioma():
    try:
        import i18n
        return i18n.lang()
    except Exception:
        return "es"


def texto_resultado(r, detalle=None):
    """El resultado en palabras del socio («skill mejorada», «nota → hecho»…)."""
    d = " ".join(str(detalle or "").split())
    if r == "sin_comprobar" and d == "sin_autoria":
        return _t("decisores.paso.sin_autoria", "sin comprobar: este motor no deja ver quién escribió")
    lg = _idioma()
    textos = _TEXTOS.get(lg)
    if textos is None:
        textos = _TEXTOS[lg] = _textos_resultado()
    t = textos.get(r)
    if t is None:
        t = str(r or "")
    t = t.replace("{d}", d or "?")
    if r in ("skill_creada", "skill_mejorada", "pendiente", "entregada", "no_se_hizo") and d:
        t += " (%s)" % d
    return t


def _textos_resultado():
    return {
        "skill_creada": _t("decisores.paso.skill_creada", "skill creada"),
        "skill_mejorada": _t("decisores.paso.skill_mejorada", "skill mejorada"),
        "nada_que_aprender": _t("decisores.paso.nada_que_aprender", "nada que aprender"),
        "pendiente": _t("decisores.paso.pendiente2", "pendiente"),
        "entregada": _t("decisores.paso.entregada2", "entregada"),
        "no_se_hizo": _t("decisores.paso.no_se_hizo", "no se hizo"),
        "perdida": _t("decisores.paso.perdida", "se perdió"),
        "frenada": _t("decisores.paso.frenada", "frenada: hubo otra hace poco"),
        "saltada": _t("decisores.paso.saltada", "revisión saltada"),
        "vencida": _t("decisores.paso.vencida", "venció sin revisarse"),
        "sin_comprobar": _t("decisores.paso.sin_comprobar", "sin comprobar"),
        "frenada_regla": _t("decisores.paso.frenada_regla", "la frenó la regla de 2 h"),
        "tipo_cambiado": _t("decisores.paso.tipo_cambiado", "nota → {d}"),
        "archivo_retocado": _t("decisores.paso.archivo_retocado", "archivo retocado"),
        "pedido_soltado": _t("decisores.paso.pedido_soltado", "no despertó a nadie"),
        "sala_pausada": _t("decisores.paso.sala_pausada", "sala en pausa"),
        "sala_cerrada": _t("decisores.paso.sala_cerrada", "sala cerrada"),
        "usada": _t("decisores.paso.usada", "la usó"),
        "descartada": _t("decisores.paso.descartada", "la descartó"),
        "mandado": _t("decisores.paso.mandado", "mandado a {d}"),
        "se_anota": _t("decisores.paso.se_anota", "se anota"),
        "opinion": _t("decisores.paso.opinion", "solo una opinión"),
    }


def _t_de(e):
    try:
        return float(e.get("t"))
    except (TypeError, ValueError):
        try:
            return time.mktime(time.strptime(str(e.get("ts") or "")[:19], "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, OverflowError):
            return None


def paso(e, ahora=None):
    """«¿Pasó?» de una decisión de la bitácora → (clase, texto). clase: «si»
    (pasó y se comprobó) · «no» (tenía que pasar y no pasó) · «espera»
    (todavía no se puede saber) · «na» (no había nada que comprobar). ('',
    '') si no aplica (un fallo, una pregunta a mano). Un resultado anotado
    manda; si no hay, se deduce SOLO en las decisiones de la 0.9.1 en
    adelante (`rv`): las de antes dicen «sin dato», nunca «aplicó»."""
    try:
        if not isinstance(e, dict) or not e.get("ok"):
            return "", ""
        D = _D()
        point, modo = str(e.get("point") or ""), e.get("mode")
        if point == D.MANUAL or modo not in ("observe", "suggest", "apply"):
            return "", ""
        r = e.get("resultado")
        if r in D.RESULTADOS:
            return D.RESULTADOS[r], texto_resultado(r, e.get("resultado_detalle"))
        if modo == "observe":
            return "na", _t("decisores.paso.observado", "solo se anotó")
        if point == "workspace.evals":
            return "na", texto_resultado("se_anota")
        if not e.get("rv"):
            return "na", _t("decisores.paso.sin_dato", "sin dato")
        ahora = time.time() if ahora is None else float(ahora)
        t0 = _t_de(e)
        edad = (ahora - t0) if t0 is not None else 1e12
        c = " ".join(str(e.get("choice") or "").split()).lower()
        if point == "workspace.security":
            if edad < VENTANA_S[point]:
                return "espera", _t("decisores.paso.espera_archivo", "¿lo retoca?")
            return "no", _t("decisores.paso.sin_cambios", "sin cambios")
        if point in D.AGENT_POINTS:
            vent = VENTANA_S.get(point, VENTANA_S["agents"])
            if edad < vent:
                return "espera", _t("decisores.paso.espera_agente", "espera aviso")
            return "na", _t("decisores.paso.sin_aviso", "sin aviso")
        if point == "workspace.skills" or (point == "workspace.memory" and modo == "apply"):
            # su resultado lo anota quien actúa (el hook de la revisión, la
            # nota guardada); sin él no se adivina
            return "na", _t("decisores.paso.sin_dato", "sin dato")
        if point == "workspace.conversations" and c == "sí":
            if edad < VENTANA_S["c3"]:
                return "espera", _t("decisores.paso.espera_cierre", "¿la cierra?")
            return "no", _t("decisores.paso.sigue_abierta", "sigue abierta")
        return "na", texto_resultado("opinion")
    except Exception:
        return "", ""


# ── lo que se comprueba después (archivo de estado local, no viaja) ─────────
#: Una decisión cuyo resultado se ve más tarde: la sala que «parece cumplida»
#: (¿quien la abrió la cierra?) y el archivo con aviso de Seguridad (¿el
#: agente lo vuelve a tocar?). Solo huellas: el id de la sala y la huella de
#: la ruta del archivo, nunca su contenido.
COMPROBAR_MAX = 200


def _comprobar_path():
    return _dir("por-comprobar.json")


def por_comprobar(eid, tipo, clave):
    """Anota que la decisión `eid` se comprueba después (tipo «c3» con el id
    de la sala, «seguridad» con la ruta del archivo). Solo con Decisores
    encendido y un id. Falla-suave."""
    try:
        if not eid or not encendido():
            return False
        k = _clave(os.path.normcase(str(clave))) if tipo == "seguridad" else str(clave)[:80]

        def anotar(d):
            d = d if isinstance(d, dict) else {}
            d[str(eid)] = {"tipo": tipo, "clave": k, "t": round(time.time(), 3)}
            if len(d) > COMPROBAR_MAX:
                for x, _v in sorted(d.items(), key=lambda kv: kv[1].get("t", 0))[:len(d) - COMPROBAR_MAX]:
                    d.pop(x, None)
            return d
        return _D()._actualizar_estado(_comprobar_path(), anotar)
    except Exception:
        return False


def _comprobado(tipo, clave, resultado, ventana):
    """Anota `resultado` en las decisiones de `tipo` con esa `clave` que aún
    estaban dentro de su ventana, y las quita. Sin el archivo (Decisores
    apagado, o nada por comprobar): no lee ni escribe nada más."""
    path = _comprobar_path()
    if not os.path.exists(path):
        return []
    hechos = []

    def ver(d):
        if not isinstance(d, dict):
            return None
        ahora = time.time()
        cambio = False
        for eid, v in list(d.items()):
            if not isinstance(v, dict):
                d.pop(eid, None)
                cambio = True
                continue
            edad = ahora - float(v.get("t") or 0)
            if edad > ventana:
                d.pop(eid, None)                # su ventana pasó: «¿pasó?» lo deduce
                cambio = True
            elif v.get("tipo") == tipo and v.get("clave") == clave and edad > 1:
                hechos.append(eid)
                d.pop(eid, None)
                cambio = True
        return d if cambio else None
    try:
        _D()._actualizar_estado(path, ver)
        for eid in hechos:
            _D().record_result(eid, resultado)
    except Exception:
        return []
    return hechos


def archivo_editado(file_path):
    """Seguridad: el agente volvió a escribir `file_path`. Si tenía un aviso
    en los últimos 30 min, su decisión queda «archivo retocado». Barato:
    sin nada por comprobar, solo un `exists`."""
    try:
        if not file_path:
            return []
        return _comprobado("seguridad", _clave(os.path.normcase(str(file_path))),
                           "archivo_retocado", VENTANA_S["workspace.security"])
    except Exception:
        return []


def sala_cerrada(sala_id):
    """Conversaciones: quien abrió la sala la cerró. Las «parece cumplido» de
    esa sala en los últimos 30 min quedan «sala cerrada»."""
    try:
        return _comprobado("c3", str(sala_id)[:80], "sala_cerrada", VENTANA_S["c3"])
    except Exception:
        return []


def _destino_reparto(destino):
    """Referencia local estable: nunca el índice opaco agente·N del modelo."""
    agente, sep, pestana = str(destino).strip().partition(":")
    agente = agente.lower()
    if not sep:
        return agente
    try:
        import agentsreg
        import messages
        brain = next((a.get("brain") for a in agentsreg.agents()
                      if str(a.get("name") or "").lower() == agente), "")
        estable, _nombre, _aviso = messages.resolver_pestana(brain, agente, pestana)
        if estable:
            pestana = estable
    except Exception:
        pass
    return agente + ":" + " ".join(pestana.split()).lower()


def guardar_destino_reparto(eid, destino):
    """Guarda solo la huella del destino elegido, fuera de la bitácora."""
    try:
        if not eid or not encendido():
            return False
        huella = _clave(_destino_reparto(destino))
        def guardar(d):
            d = d if isinstance(d, dict) else {}
            d[eid] = {"destino": huella, "t": time.time()}
            for k in sorted(d, key=lambda k: float(d[k].get("t") or 0))[:-COMPROBAR_MAX]:
                d.pop(k, None)
            return d
        return _D()._actualizar_estado(_dir("repartos.json"), guardar)
    except Exception:
        return False


def tras_mandar(destinos):
    """Repartir: esta pestaña le mandó algo (un mensaje del bus, una sala) a
    `destinos` (agentes o «agente:pestaña»). Las decisiones de «Repartir» de
    la última hora, de ESTA pestaña, sin resultado y cuyo elegido es uno de
    ellos quedan «mandado a <elegido>». Apagado: nada."""
    try:
        if not destinos or not encendido():
            return []
        D = _D()
        quien = {str(x).strip().lower() for x in destinos if str(x).strip()}
        referencias = {_clave(_destino_reparto(x)) for x in quien}
        agentes = {x.split(":", 1)[0] for x in quien}
        elegidos = _leer_json(_dir("repartos.json")) or {}
        tab, cerebro = lugar_actual()
        ahora = time.time()
        hechos = []
        for e in D._entries():
            if (e.get("point") != "agents.route" or not e.get("ok") or e.get("resultado")
                    or e.get("mode") not in ("suggest", "apply")
                    or (e.get("tab") or "") != tab or (e.get("cerebro") or "") != cerebro):
                continue
            t0 = _t_de(e)
            if t0 is None or ahora - t0 > VENTANA_S["agents.route"]:
                continue
            c = " ".join(str(e.get("choice") or "").split()).lower()
            referencia = (elegidos.get(e["id"]) or {}).get("destino")
            # Las decisiones antiguas sin referencia de pestaña no demuestran
            # un envío a ella. Un agente sin pestaña sí permite cualquier tab.
            coincide = (referencia in referencias if ":" in c or "·" in c else c in agentes)
            if coincide:
                if D.record_result(e["id"], "mandado", detalle=c.split("·", 1)[0]):
                    hechos.append(e["id"])
        return hechos
    except Exception:
        return []


# ── el resumen honesto de hoy (Historial, ventanita y la portada) ───────────
#: Las cifras que se cuentan como «pasó», en este orden: (resultado, uno, varios).
_RESUMEN = (
    ("skill_creada", "decisores.hoy.skill_creada", "{n} skill creada", "{n} skills creadas"),
    ("skill_mejorada", "decisores.hoy.skill_mejorada", "{n} skill mejorada", "{n} skills mejoradas"),
    ("nada_que_aprender", "decisores.hoy.nada_que_aprender", "{n} revisión sin cambios",
     "{n} revisiones sin cambios"),
    ("saltada", "decisores.hoy.saltada", "{n} revisión saltada", "{n} revisiones saltadas"),
    ("tipo_cambiado", "decisores.hoy.tipo_cambiado", "{n} nota con su tipo", "{n} notas con su tipo"),
    ("archivo_retocado", "decisores.hoy.archivo_retocado", "{n} aviso atendido",
     "{n} avisos atendidos"),
    ("mandado", "decisores.hoy.mandado", "{n} tarea repartida", "{n} tareas repartidas"),
    ("usada", "decisores.hoy.usada", "{n} respuesta usada", "{n} respuestas usadas"),
    ("pedido_soltado", "decisores.hoy.pedido_soltado", "{n} despertar evitado",
     "{n} despertares evitados"),
    ("sala_pausada", "decisores.hoy.sala_pausada", "{n} sala en pausa", "{n} salas en pausa"),
    ("sala_cerrada", "decisores.hoy.sala_cerrada", "{n} sala cerrada", "{n} salas cerradas"),
)


def cifra(r, n):
    """«1 nota con su tipo», «2 skills mejoradas»…: n resultados `r` en palabras."""
    for res, key, uno, varios in _RESUMEN:
        if res == r:
            return _t(key + (".one" if n == 1 else ".many"), uno if n == 1 else varios, n=n)
    return "%d %s" % (n, texto_resultado(r))


def etiqueta_resultado(r):
    """El nombre de una cifra del resumen, sin el número («notas con su tipo»)
    — lo que dice el filtro del Historial."""
    for res, key, _uno, varios in _RESUMEN:
        if res == r:
            return " ".join(_t(key + ".many", varios, n="").split())
    return texto_resultado(r)


def _de_hoy(e, dia):
    """¿Cuenta para hoy? Un resultado, por el día en que se comprobó; lo
    demás, por el día de la decisión."""
    t = e.get("resultado_t") if e.get("resultado") else None
    if t:
        try:
            return time.strftime("%Y-%m-%d", time.localtime(float(t))) == dia
        except (TypeError, ValueError, OverflowError):
            pass
    return str(e.get("ts") or "").startswith(dia)


_RESUMEN_CACHE = {"k": None, "v": None}


def resumen_hoy(ahora=None):
    """(cacheado) ver _resumen_hoy: misma firma de la bitácora, mismo minuto y
    mismo idioma → la misma respuesta (el hub lo pide cada 5 s)."""
    try:
        if not encendido():
            return []
        D = _D()
        D._entries()                                  # refresca la firma si cambió
        t = time.time() if ahora is None else float(ahora)
        k = (D._CACHE.get("key"), int(t // 60), _idioma())
        if ahora is None and _RESUMEN_CACHE["k"] == k and _RESUMEN_CACHE["v"] is not None:
            return [dict(x) for x in _RESUMEN_CACHE["v"]]
        v = _resumen_hoy(ahora)
        if ahora is None:
            _RESUMEN_CACHE.update(k=k, v=v)
        return [dict(x) for x in v]
    except Exception:
        return []


def _resumen_hoy(ahora=None):
    """Las cifras de HOY, hechas SOLO con «¿pasó?» (nunca con decisiones
    sueltas) → [{"texto", "clase", "filtro"}]: primero lo que pasó (clase
    «si»), luego lo que espera, lo que no pasó y las opiniones. Sin nada que
    haya pasado: «nada aplicado (N opiniones)». [] con Decisores apagado (la
    portada queda igual)."""
    try:
        if not encendido():
            return []
        ahora = time.time() if ahora is None else float(ahora)
        dia = time.strftime("%Y-%m-%d", time.localtime(ahora))
        D = _D()
        cuenta, clases = {}, {"espera": 0, "no": 0, "na": 0}
        total = 0
        for e in D._entries():
            if not e.get("ok") or e.get("point") == D.MANUAL or not _de_hoy(e, dia):
                continue
            clase, _txt = paso(e, ahora)
            if not clase:
                continue
            total += 1
            if clase == "si":
                cuenta[e.get("resultado")] = cuenta.get(e.get("resultado"), 0) + 1
            else:
                clases[clase] += 1
        out = []
        for r, key, uno, varios in _RESUMEN:
            n = cuenta.get(r, 0)
            if n:
                out.append({"texto": _t(key + (".one" if n == 1 else ".many"),
                                        uno if n == 1 else varios, n=n),
                            "clase": "si", "filtro": {"resultado": r, "hoy": True}})
        if not out:
            if not total:
                return [{"texto": _t("decisores.hoy.nada_todavia", "nada todavía"), "clase": "na",
                         "filtro": None}]
            return [{"texto": _t("decisores.hoy.nada_aplicado", "nada aplicado ({n} {o})",
                                 n=clases["na"] + clases["espera"] + clases["no"],
                                 o=_plural(clases["na"] + clases["espera"] + clases["no"],
                                           _t("decisores.hoy.opinion", "opinión"),
                                           _t("decisores.hoy.opiniones", "opiniones"))),
                     "clase": "na", "filtro": {"hoy": True}}]
        for clase, key, uno, varios in (
                ("espera", "decisores.hoy.espera", "{n} por comprobar", "{n} por comprobar"),
                ("no", "decisores.hoy.no", "{n} no pasó", "{n} no pasaron"),
                ("na", "decisores.hoy.na", "{n} opinión", "{n} opiniones")):
            n = clases[clase]
            if n:
                out.append({"texto": _t(key + (".one" if n == 1 else ".many"),
                                        uno if n == 1 else varios, n=n),
                            "clase": clase, "filtro": {"paso": clase, "hoy": True}})
        return out
    except Exception:
        return []


def linea_resumen(items=None, etiqueta=True):
    """«◆ Decisores hoy: 1 skill mejorada · 1 nota con su tipo» (texto plano). ''
    si no hay cifras (Decisores apagado)."""
    items = resumen_hoy() if items is None else items
    if not items:
        return ""
    cuerpo = " · ".join(x["texto"] for x in items)
    if not etiqueta:
        return cuerpo
    return _t("decisores.hoy.linea", "{s} Decisores hoy: {c}", s=SIMBOLO, c=cuerpo)


def filtrar(entradas, filtro, ahora=None):
    """Las decisiones que caben en `filtro` ({"resultado"|"paso"|"point", "hoy"})."""
    if not filtro:
        return list(entradas)
    ahora = time.time() if ahora is None else float(ahora)
    dia = time.strftime("%Y-%m-%d", time.localtime(ahora))
    out = []
    for e in entradas:
        if filtro.get("hoy") and not _de_hoy(e, dia):
            continue
        if filtro.get("point") and e.get("point") != filtro["point"]:
            continue
        if filtro.get("resultado") and e.get("resultado") != filtro["resultado"]:
            continue
        if filtro.get("paso") and paso(e, ahora)[0] != filtro["paso"]:
            continue
        out.append(e)
    return out


# ── (d) Historial: qué cambió cada decisión ─────────────────────────────────
def efecto(e, corto=False):
    """Lo que hizo una decisión de la bitácora Y lo que pasó después, en
    palabras cortas (cabe junto al «¿acertó?» del Historial): «decidió «sí» ·
    pasó: skill mejorada», «sugirió «hecho»», «observó · no cambia nada».
    Nunca «aplicó» sin un resultado comprobado (0.9.1: el Historial decía
    «revisión entregada» cuando el piso la frenaba). `corto` = lo que PASÓ de
    verdad, para la fila («nota → hecho»); '' si no hay nada comprobado. ''
    si no aplica (un fallo, una pregunta a mano)."""
    try:
        if not isinstance(e, dict) or not e.get("ok"):
            return ""
        modo = e.get("mode")
        clase, txt = paso(e)
        if corto:
            return txt if clase == "si" else ""
        c = " ".join(str(e.get("choice") or "").split())
        if modo == "observe":
            que = _t("decisores.visible.fx_observe", "observó · no cambia nada")
        elif modo == "suggest":
            que = _t("decisores.visible.fx_suggest", "sugirió «{c}»", c=_eleccion(c, _indice(e), tope=24))
        elif modo == "apply":
            que = _t("decisores.visible.fx_apply", "decidió «{c}»", c=_eleccion(c, _indice(e), tope=24))
        else:
            return ""
        if clase == "si":
            que += " · " + _t("decisores.visible.fx_paso_si", "pasó: {t}", t=txt)
        elif clase == "no":
            que += " · " + _t("decisores.visible.fx_paso_no", "no pasó: {t}", t=txt)
        elif clase == "espera":
            que += " · " + _t("decisores.visible.fx_paso_espera", "espera: {t}", t=txt)
        elif clase == "na" and modo != "observe" and txt != texto_resultado("opinion"):
            que += " · " + txt
        return que
    except Exception:
        return ""


def _indice(e):
    try:
        ops = [" ".join(str(o).split()) for o in (e.get("options") or [])]
        c = " ".join(str(e.get("choice") or "").split())
        return ops.index(c) if c in ops else None
    except Exception:
        return None


def ultimas_confianzas(point, n=5):
    """Las últimas `n` confianzas (%) de un uso, de la más vieja a la más
    nueva — la guía para el umbral (Ajustes → el uso). [] si no hay o apagado."""
    try:
        if not encendido():
            return []
        out = [_pct(e.get("p")) for e in _D()._entries()
               if e.get("ok") and e.get("point") == point and e.get("p") is not None]
        return [x for x in out if x is not None][-max(0, int(n)):]
    except Exception:
        return []


# ── (d)(e) hoy: cuántas consultas ───────────────────────────────────────────
def hoy(ahora=None):
    """{"n", "apply", "suggest", "mas"} de HOY (hora local), de la cola de la
    bitácora. `mas` = la cola no alcanzó (hubo más). Barato: sin caché, para
    un proceso nuevo en cada refresco de la barra."""
    res = {"n": 0, "apply": 0, "suggest": 0, "pasaron": 0, "mas": False}
    try:
        dia = time.strftime("%Y-%m-%d", time.localtime(ahora) if ahora else time.localtime())
        path = _D().ledger_path()
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            tam = fh.tell()
            desde = max(0, tam - HOY_COLA_BYTES)
            fh.seek(desde)
            lineas = fh.read().decode("utf-8", "replace").split("\n")
        if desde > 0 and lineas:
            lineas = lineas[1:]
        primera = None
        si = {k for k, v in _D().RESULTADOS.items() if v == "si"}
        pasaron, ids = set(), set()
        for ln in lineas:
            if '"resultado"' in ln and '"decision"' not in ln:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if (isinstance(r, dict) and r.get("type") == "resultado"
                        and str(r.get("ts") or "").startswith(dia)):
                    if r.get("resultado") in si:
                        pasaron.add(r.get("ref"))
                    else:
                        pasaron.discard(r.get("ref"))      # el último resultado gana
                continue
            if '"decision"' not in ln:
                continue
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(e, dict) or e.get("type") != "decision":
                continue
            ts = str(e.get("ts") or "")
            if primera is None:
                primera = ts
            if not ts.startswith(dia):
                continue
            res["n"] += 1
            ids.add(e.get("id"))
            if e.get("mode") == "apply":
                res["apply"] += 1
            elif e.get("mode") == "suggest":
                res["suggest"] += 1
        res["pasaron"] = len(pasaron & ids)
        res["mas"] = bool(desde > 0 and primera and primera.startswith(dia))
    except Exception:
        pass
    return res


def _plural(n, uno, varios):
    return uno if n == 1 else varios


def linea_hoy(ahora=None):
    """«hoy: 7 consultas · 2 pasaron» (lo que PASÓ, comprobado; nunca «aplicadas»
    por el nivel). '' apagado."""
    try:
        if not encendido():
            return ""
        h = hoy(ahora)
        n = "%d%s" % (h["n"], "+" if h["mas"] else "")
        return _t("decisores.visible.today2", "hoy: {n} {c} · {a} {ap}", n=n,
                  c=_plural(h["n"], _t("decisores.visible.query", "consulta"),
                            _t("decisores.visible.queries", "consultas")),
                  a=h["pasaron"], ap=_plural(h["pasaron"], _t("decisores.visible.passed_one", "pasó"),
                                             _t("decisores.visible.passed_many", "pasaron")))
    except Exception:
        return ""


def segmento_hoy(ahora=None):
    """Barra de estado: «◆ Decisores: hoy 7 · 1 aplicada» — la cuenta junta a
    TODOS los modelos que respondieron hoy, así que va con la etiqueta neutra.
    '' con Decisores apagado."""
    try:
        if not encendido():
            return ""
        h = hoy(ahora)
        m = _t("decisores.visible.all_models", "Decisores")
        n = "%d%s" % (h["n"], "+" if h["mas"] else "")
        if h["pasaron"]:
            # solo lo que PASÓ de verdad (un resultado comprobado), nunca el
            # nivel: «aplicada» contaba decisiones que no cambiaron nada (0.9.1)
            return _t("decisores.visible.bar_passed", "{s} {m}: hoy {n} · {a} {ap}", s=SIMBOLO, m=m,
                      n=n, a=h["pasaron"],
                      ap=_plural(h["pasaron"], _t("decisores.visible.passed_one", "pasó"),
                                 _t("decisores.visible.passed_many", "pasaron")))
        return _t("decisores.visible.bar", "{s} {m}: hoy {n}", s=SIMBOLO, m=m, n=n)
    except Exception:
        return ""


# ── archivos de estado (atómicos, falla-suave) ──────────────────────────────
def _dir(*partes):
    import paths
    return os.path.join(paths.state_dir(), "decisores", *partes)


def _leer_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _escribir(path, texto):
    try:
        import atomico                         # temporal ÚNICO (no solo el pid)
        atomico.escribir(path, texto, fsync=False)
        try:                                   # Windows: solo para tu usuario
            import acl_privada
            acl_privada.solo_mio(path)
        except Exception:
            pass
        return True
    except OSError:
        return False


def _borrar(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _clave(texto):
    return hashlib.sha1(str(texto or "").encode("utf-8", "replace")).hexdigest()[:16]


# ── (c) la última sesión: Evals y Skills al cerrar → una línea al abrir ─────
def _ultima_path(brain):
    return _dir("ultima-sesion", _clave(os.path.realpath(os.path.expanduser(brain))) + ".json")


def anotar_cierre(brain, point, v, sesion="", tab="", nota=""):
    """AL CERRAR (Evals, Skills): guarda el veredicto para mostrarlo UNA vez al
    abrir la siguiente sesión de ese cerebro (al agente y en el hub). Solo
    suggest/apply (observe es en silencio). Los usos de un mismo cierre se
    juntan por `sesion`. → True si quedó anotado."""
    if not _D().decisores_activos():
        return False
    try:
        if not brain or not isinstance(v, dict) or v.get("mode") not in ("suggest", "apply"):
            return False
        def anotar(d):
            # bajo el candado: Evals y Skills del MISMO cierre (dos procesos)
            # ya no se borran uno al otro (Greptile 0.8.x, 6)
            ahora = time.time()
            mismo = (sesion and d.get("sesion") == sesion) or (
                not sesion and not d.get("sesion") and ahora - float(d.get("t") or 0) < 600)
            if not mismo:
                d = {"brain": os.path.realpath(os.path.expanduser(brain)), "sesion": sesion or "",
                     "tab": tab or "", "usos": {}}
            d["t"], d["visto"] = ahora, []
            d.setdefault("usos", {})[point] = {
                "choice": v.get("choice"), "mode": v.get("mode"), "decider": v.get("decider"),
                "p": round(float(v.get("p") or 0.0), 4) if v.get("p_known", True) else None,
                "nota": nota or ""}
            return d
        return _D()._actualizar_estado(_ultima_path(brain), anotar)
    except Exception:
        return False


def _uso_ultima(point, u):
    modo = u.get("mode") if u.get("mode") in ("suggest", "apply") else "suggest"
    return formato(_nombre(u.get("decider")),
                   _que(point, u.get("choice"), modo == "apply", nota=u.get("nota") or ""),
                   _pct(u.get("p")), modo)


def linea_ultima(brain, canal):
    """AL ABRIR, una línea por uso (con el modelo que respondió en cada uno):
    «◆ <modelo>: tu última sesión parece «resuelta»
    · 88 % · aplicado» — UNA vez por canal («agente»: el contexto de arranque,
    con el pedido de mostrarlo en su primera respuesta; «hub»: el aviso del
    hub). '' si no hay, ya se vio o Decisores está apagado."""
    try:
        if not brain or not encendido():
            return ""
        path = _ultima_path(brain)
        if not os.path.exists(path):
            return ""
        D = _D()
        out = {"partes": []}

        def ver(d):
            # bajo el candado: marcar «visto» no pisa un uso que otro cierre anota
            if not d:
                return None
            visto = list(d.get("visto") or [])
            if canal in visto:
                return None
            if time.time() - float(d.get("t") or 0) > ULTIMA_MAX_S:
                return D.BORRAR
            orden = ("workspace.evals", "workspace.skills")
            usos = d.get("usos") or {}
            out["partes"] = [_uso_ultima(p, usos[p]) for p in orden if isinstance(usos.get(p), dict)]
            if not out["partes"]:
                return None
            visto.append(canal)
            if set(visto) >= {"agente", "hub"}:
                return D.BORRAR
            d["visto"] = visto
            return d
        D._actualizar_estado(path, ver)
        partes = out["partes"]
        if not partes:
            return ""
        if canal == "agente":
            partes.insert(0, _t("decisores.visible.last_session_agent", "Decisores en tu última "
                                "sesión (muéstraselo al socio en tu primera respuesta, en un "
                                "bloque ◆):"))
        return "\n".join(partes)
    except Exception:
        return ""


# ── (f) a media sesión: si Decisores cambió, el agente se entera UNA vez ────
def _sesion_path(sesion):
    return _dir("sesiones", _clave(sesion))


def _instruccion(motor):
    """La MISMA instrucción que recibe el agente al abrir (memoria.instruccion_decisores),
    sin importar memoria en cada mensaje."""
    try:
        import memoria_mcp
        via = bool(memoria_mcp.activo(motor))
    except Exception:
        via = False
    return _D().agent_instruction(via_mcp=via)


def _limpiar_sesiones():
    try:
        d = _dir("sesiones")
        corte = time.time() - SESION_MAX_S
        for f in os.listdir(d):
            p = os.path.join(d, f)
            try:
                if os.path.getmtime(p) < corte:
                    os.remove(p)
            except OSError:
                continue
    except OSError:
        pass


def al_abrir_sesion(sesion, motor="claude-code"):
    """AL ABRIR (cada arranque, también al retomar o tras compactar: el agente
    recibe ahí la instrucción): la línea de base = la huella de lo que se le
    dio. Apagado y sin base previa: no escribe nada."""
    try:
        if not sesion:
            return
        path = _sesion_path(sesion)
        txt = _instruccion(motor) if encendido() else ""
        if txt:
            _limpiar_sesiones()
            _escribir(path, _clave(txt))
        elif os.path.exists(path):
            _borrar(path)
        if encendido():                          # desde aquí cuenta «lo que no viste»
            _escribir(_cursor_path(sesion), "%.3f" % time.time())
    except Exception:
        pass


def cambio_en_sesion(sesion, motor="claude-code"):
    """EN CADA MENSAJE: si los usos de agentes cambiaron desde el arranque (la
    huella de la instrucción ya no es la de la base), el texto para inyectar
    UNA vez — la instrucción nueva, o que ya no consulte si se apagaron — y
    queda como nueva base. '' si nada cambió (apagado de punta a punta: ni un
    archivo)."""
    if not _D().decisores_activos():
        return ""
    try:
        if not sesion:
            return ""
        path = _sesion_path(sesion)
        try:
            with open(path, encoding="utf-8") as fh:
                base = fh.read().strip()
        except OSError:
            base = ""
        if not base and not encendido():
            return ""
        txt = _instruccion(motor) if encendido() else ""
        actual = _clave(txt) if txt else ""
        if actual == base:
            return ""
        if txt:
            _escribir(path, actual)
            return _t("decisores.visible.changed", "Decisores cambió en esta sesión (lo movió el "
                      "socio); esto reemplaza lo que decía al abrir:") + "\n" + txt
        _borrar(path)
        return _t("decisores.visible.turned_off", "Decisores: el socio lo apagó en esta sesión; ya "
                  "no le preguntes al decisor ni cierres con el bloque ◆.")
    except Exception:
        return ""


# ── lo que el agente no vio: en el siguiente mensaje, UNA vez ───────────────
#: Lo más que se lista; el resto, «y N más».
NO_VISTAS_MAX = 3


def _cursor_path(sesion):
    return _dir("cursor", _clave(sesion))


def _entradas_desde(t0):
    """Las decisiones de la cola de la bitácora con `t` > t0 (las nuevas traen
    su hora precisa), de la más vieja a la más nueva."""
    out = []
    try:
        path = _D().ledger_path()
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            tam = fh.tell()
            desde = max(0, tam - HOY_COLA_BYTES)
            fh.seek(desde)
            lineas = fh.read().decode("utf-8", "replace").split("\n")
        if desde > 0 and lineas:
            lineas = lineas[1:]
        for ln in reversed(lineas):
            if '"decision"' not in ln:
                continue
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(e, dict) or e.get("type") != "decision":
                continue
            try:
                t = float(e.get("t"))
            except (TypeError, ValueError):
                break                             # una de antes: ya no hay nuevas
            if t <= t0:
                break
            out.append(e)
    except Exception:
        return []
    return list(reversed(out))


def lugar_actual():
    """(pestaña, cerebro) de este proceso, como se anotan en la bitácora."""
    tab = os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS") or ""
    brain = os.environ.get("WORKSPACE_BRAIN") or ""
    return tab, (_clave(os.path.realpath(os.path.expanduser(brain))) if brain else "")


def desde_tu_ultimo_mensaje(sesion):
    """EN CADA MENSAJE (Claude Code): las intervenciones de esta pestaña que el
    agente NO vio por su canal (una que solo anotó un hook) desde el mensaje
    anterior: «Desde tu último mensaje, Decisores hizo: …», hasta 3 líneas y
    «y N más». UNA vez (el cursor avanza). '' si no hubo, o apagado (ni un
    archivo)."""
    try:
        if not sesion or not encendido():
            return ""
        path = _cursor_path(sesion)
        try:
            with open(path, encoding="utf-8") as fh:
                t0 = float(fh.read().strip())
        except (OSError, ValueError):
            t0 = None
        _escribir(path, "%.3f" % time.time())
        if t0 is None:
            return ""                             # recién encendido: cuenta desde ahora
        tab, cerebro = lugar_actual()
        nuevas = [e for e in _entradas_desde(t0)
                  if e.get("ok") and e.get("mode") in ("suggest", "apply") and not e.get("agente")
                  and (e.get("tab") or "") == tab and (e.get("cerebro") or "") == cerebro]
        lineas = [x for x in (linea_entrada(e) for e in nuevas) if x]
        if not lineas:
            return ""
        out = [_t("decisores.visible.since_last", "Desde tu último mensaje, Decisores hizo (ponlo "
                  "en tu bloque ◆):")] + lineas[:NO_VISTAS_MAX]
        if len(lineas) > NO_VISTAS_MAX:
            out.append(_t("decisores.visible.and_more", "y {n} más (en Decisores → Historial)",
                          n=len(lineas) - NO_VISTAS_MAX))
        return "\n".join(out)
    except Exception:
        return ""


# ── la fila de Decisores en la portada del hub (en el área de los agentes) ──
# Lo ÚNICO de este módulo que existe con Decisores apagado: sin modelo, la fila
# invita a configurarlo («nuevo» durante NUEVO_DIAS desde la primera vez que
# este hub lo mostró; después «configurar», sin preguntar). La fecha se anota
# fuera de `decisores/` (no es estado de Decisores: es lo que el hub ya le
# enseñó al socio). Quien ya usó Decisores nunca ve el «nuevo».
NUEVO_DIAS = 7


def _novedades_path():
    import paths
    return os.path.join(paths.state_dir(), "hub-novedades.json")


def _ya_los_conoce():
    """¿El socio ya usó Decisores? Lo que dejó al usarlos: la bitácora o un
    ajuste suyo de Decisores."""
    try:
        if os.path.exists(_D().ledger_path()):
            return True
    except Exception:
        pass
    try:
        import settings
        crudo = settings._load_store().get("settings") or {}
        return any(str(k).startswith("decisions.") for k in crudo)
    except Exception:
        return False


def _nuevo_vigente(ahora):
    """¿Va el «nuevo»? NUEVO_DIAS desde la PRIMERA vez que este hub lo mostró
    (la primera llamada anota la hora; un reloj que volvió atrás la reinicia).
    Falla-suave → False."""
    try:
        if _ya_los_conoce():
            return False
        path = _novedades_path()
        out = {}

        def desde_cuando(d):
            # bajo el candado: hub-novedades.json puede traer otras claves
            try:
                out["desde"] = float(d.get("decisores_desde"))
            except (TypeError, ValueError):
                out["desde"] = None
            if out["desde"] is None or out["desde"] > ahora:
                d["decisores_desde"] = out["desde"] = round(ahora, 3)
                return d
            return None
        d = _leer_json(path) or {}
        try:
            desde = float(d.get("decisores_desde"))
        except (TypeError, ValueError):
            desde = None
        if desde is None or desde > ahora:
            _D()._actualizar_estado(path, desde_cuando)
            desde = out.get("desde", ahora)
        return (ahora - desde) < NUEVO_DIAS * 86400
    except Exception:
        return False


def modelo_que_decide():
    """El nombre del modelo que DE VERDAD decide en los usos encendidos (#3:
    arriba decía el general y cada uso tenía fijado otro): «Jev»; con
    varios, el de más usos y «+N»; sin usos encendidos, el general."""
    try:
        D = _D()
        deciden = D.modelos_que_deciden()
        if not deciden:
            g = D.global_model()
            return D.decider_label(g) if g != D.OFF else ""
        orden = sorted(deciden.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        nom = D.decider_label(orden[0][0])
        return nom + (" +%d" % (len(orden) - 1) if len(orden) > 1 else "")
    except Exception:
        return ""


def boton_hub(ahora=None):
    """Los datos de la fila de Decisores de la portada:
        {"activo": id del modelo general u «off», "modelo": su nombre (META
         label, jamás uno fijo), "estado": listo · sin_llave · no_listo · sin_red · pausa ('' sin
         modelo), "listos": [(id, nombre)] de los modelos LISTOS que se ven
         (←→ cicla entre ellos y «apagado»), "configurado": hay modelo activo
         o alguno listo, "nuevo": el «nuevo» va (sin nada configurado), "usos"}
    `ahora` (epoch) es para las pruebas. None si Decisores no carga (sin fila)."""
    if not _D().decisores_activos():
        return None
    try:
        D = _D()
        ahora = time.time() if ahora is None else float(ahora)
        g = D.global_model()
        usos = sum(1 for p in D.POINT_IDS if D.point_conf(p)["level"] != "off")
        listos = []
        for did in D.offered():
            try:
                if D.decider_status(did).get("ready"):
                    listos.append((did, D.decider_label(did)))
            except Exception:
                pass
        if g == D.OFF:
            return {"activo": D.OFF, "modelo": "", "estado": "", "listos": listos,
                    "configurado": bool(listos), "usos": usos,
                    "nuevo": (not listos) and _nuevo_vigente(ahora)}
        if D.key_env(g) and not D.key_source(g):
            estado = "sin_llave"
        elif not D.decider_status(g).get("ready"):
            estado = "no_listo"           # uno local: Ollama apagado, sin modelo…
        elif sin_conexion(g):
            estado = "sin_red"            # sin internet: la llave y el modelo siguen bien
        elif D.breaker_open(g):
            estado = "pausa"
        else:
            estado = "listo"
        return {"activo": g, "modelo": modelo_que_decide(), "estado": estado, "listos": listos,
                "configurado": True, "nuevo": False, "usos": usos,
                "propios": len(D.usos_con_modelo_propio())}
    except Exception:
        return None
