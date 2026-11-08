#!/usr/bin/env python3
"""WORKSPACE · decisores_tui — sección DECISORES: qué modelo decide y dónde ayuda.

Un decisor elige entre opciones FIJAS y dice qué tan seguro está (no
programa ni conversa: eso es un motor). Tres pestañas, todo en cuadritos
navegables con flechas (foco = borde grueso en el acento; activo = ●):

  Preguntar  un agente real del registro, pregunta + opciones, y la
             respuesta con una barra por opción (contexto = el resumen
             guardado de su pestaña más reciente, si lo hay).
  Ajustes    el modelo general (tarjetas con su disponibilidad real) y los
             8 usos en rejillas 2×2 con su medidor ▮▯▯; espacio cambia el
             nivel, Enter abre el detalle (nivel · modelo · umbral) y en el
             detalle Enter guarda y vuelve.
  Historial  la bitácora local: resumen + lista; s/n califica.

`i`/`?` abre la ayuda de cada pestaña y del detalle, con «cómo lo hicimos».
El modelo de datos vive en decisions.py (fachada) y deciders/ (decisores);
esto es solo la superficie. Teclado: termios+select en Unix, msvcrt en
Windows. Stdlib, Python 3.9+.
"""
import os
import sys
import threading
import time
from theme import screen as _theme_screen  # fondo/tinta del tema

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import decisions as DC                                          # noqa: E402
import decision_visible as DV                                   # noqa: E402
import hublayout as HL                                          # noqa: E402
import section_box as SB                                        # noqa: E402

try:
    import i18n                                                 # noqa: E402
except Exception:
    i18n = None


def _t(key, es, **kw):
    s = es
    if i18n is not None:
        try:
            v = i18n.t(key)
            s = v if v != key else es
        except Exception:
            s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


TABS = ("preguntar", "ajustes", "historial")
#: (Las tarjetas de modelo salen de deciders/: los que ve el socio + Apagado.)
NCOL = {"off": "DK", "observe": "B2", "suggest": "B", "decide": "OK"}
LIGHT = "╭╮╰╯│─"
HEAVY = "┏┓┗┛┃━"
#: Tiempo límite de una pregunta a mano (la nube tarda más que un hook).
MANUAL_TIMEOUT_MS = 10000
#: El medidor se recalcula cuando dejas de teclear (nunca en cada tecla).
DEBOUNCE_S = 0.4
#: Ancho de la caja: la fila de Contexto lleva 5 cuadritos con su medidor.
BOX_W = 72


# ── textos ───────────────────────────────────────────────────────────────────
def _tab_label(t):
    return {"preguntar": _t("decisores.tab.ask", "Preguntar"),
            "ajustes": _t("decisores.tab.settings", "Ajustes"),
            "historial": _t("decisores.tab.history", "Historial")}[t]


def _group_label(g):
    return (_t("decisores.group.agents", "Tus agentes") if g == "agents"
            else _t("decisores.group.workspace", "Workspace"))


def _point_name(pid):
    return {
        "agents.choose": _t("decisores.point.choose.name", "Elegir entre opciones"),
        "agents.review": _t("decisores.point.review.name", "Revisar su trabajo"),
        "agents.prompt": _t("decisores.point.prompt.name", "Mejor prompt"),
        "agents.route": _t("decisores.point.route.name", "Repartir tareas"),
        "workspace.memory": _t("decisores.point.memory.name", "Memoria"),
        "workspace.evals": _t("decisores.point.evals.name", "Evals"),
        "workspace.skills": _t("decisores.point.skills.name", "Skills"),
        "workspace.security": _t("decisores.point.security.name", "Seguridad"),
    }.get(pid, _t("decisores.point.manual.name", "Pregunta"))


def _point_short(pid):
    return {
        "agents.choose": _t("decisores.point.choose.short", "Elegir"),
        "agents.review": _t("decisores.point.review.short", "Revisar"),
        "agents.prompt": _t("decisores.point.prompt.short", "Prompt"),
        "agents.route": _t("decisores.point.route.short", "Repartir"),
    }.get(pid, _point_name(pid))


def _point_what(pid):
    return {
        "agents.choose": _t("decisores.point.choose.what", "cuando un agente duda entre varias opciones"),
        "agents.review": _t("decisores.point.review.what", "si el entregable quedó completo"),
        "agents.prompt": _t("decisores.point.prompt.what", "cuál de varias instrucciones funciona mejor"),
        "agents.route": _t("decisores.point.route.what", "a qué agente le toca cada parte"),
        "workspace.memory": _t("decisores.point.memory.what", "qué tipo de nota es"),
        "workspace.evals": _t("decisores.point.evals.what", "si una sesión salió bien"),
        "workspace.skills": _t("decisores.point.skills.what", "si algo vale la pena aprenderlo"),
        "workspace.security": _t("decisores.point.security.what", "qué tan riesgosa es una acción"),
    }.get(pid, "")


def _level_name(lv):
    return {"off": _t("decisores.level.off", "apagado"),
            "observe": _t("decisores.level.observe", "observa"),
            "suggest": _t("decisores.level.suggest", "sugiere"),
            "decide": _t("decisores.level.decide", "decide"),
            "ask": _t("decisores.level.ask", "pregunta")}.get(lv, lv or "—")


def _level_txt(lv):
    return {"off": _t("decisores.level.off.txt", "no pregunta nada; todo sigue como hoy"),
            "observe": _t("decisores.level.observe.txt", "decide en silencio y lo anota"),
            "suggest": _t("decisores.level.suggest.txt", "te la muestra a ti o al agente; nadie la "
                          "aplica solo"),
            "decide": _t("decisores.level.decide.txt", "actúa solo cuando está muy seguro")}[lv]


def _model_name(m):
    if m == "off":
        return _t("decisores.model.off", "Apagado")
    if m == DC.GENERAL:
        return _t("decisores.model.general", "General")
    return (DC.meta(m).get("label") or m.capitalize())


def _shown(did):
    """El nombre de un decisor PARA MOSTRAR: '' para los internos (nunca se
    ven: pruebas y el chequeo en vivo)."""
    if not did or DC.is_internal(did):
        return ""
    return _model_name(did)


def _model_txt(m):
    return {"jev": _t("decisores.model.jev.txt", "en la nube · TypeSafe"),
            "off": _t("decisores.model.off.txt", "ningún uso pregunta nada")}.get(
        m, _t("decisores.model.other.txt", "decisor instalado"))


def _cards():
    """Los modelos reales de decisión (deciders/ sin los internos) + Apagado."""
    return list(DC.offered()) + ["off"]


def _model_state(m):
    """(seleccionable, texto de estado) — la disponibilidad REAL."""
    if m == "off":
        return True, _t("decisores.st.off", "apagado")
    st = DC.decider_status(m)
    if not st["installed"]:
        return False, _t("decisores.st.not_installed", "no está")
    if st["ready"]:
        return True, _t("decisores.st.ready", "listo")
    return True, _t("decisores.st.configure", "configúralo en Motores")


def _point_when(pid):
    """Cuándo pregunta cada uso (lo que de verdad lo dispara)."""
    return {
        "agents.choose": _t("decisores.when.agents", "cuando un agente se lo pregunta (workspace decidir)"),
        "agents.review": _t("decisores.when.agents", "cuando un agente se lo pregunta (workspace decidir)"),
        "agents.prompt": _t("decisores.when.agents", "cuando un agente se lo pregunta (workspace decidir)"),
        "agents.route": _t("decisores.when.agents", "cuando un agente se lo pregunta (workspace decidir)"),
        "workspace.memory": _t("decisores.when.memory", "al guardar una nota con el tipo genérico «nota»"),
        "workspace.evals": _t("decisores.when.evals", "al cerrar cada sesión, con su extracto"),
        "workspace.skills": _t("decisores.when.skills", "al cerrar, si la «Revisión de skills» está encendida"),
        "workspace.security": _t("decisores.when.security", "cuando el escaneo de seguridad encuentra algo"),
    }.get(pid, "")


def _mode_name(mode):
    """Qué pasó con una decisión (Historial)."""
    return {"observe": _t("decisores.mode.observe", "observó"),
            "suggest": _t("decisores.mode.suggest", "sugirió"),
            "apply": _t("decisores.mode.apply", "aplicó"),
            "ask": _t("decisores.mode.ask", "pregunta"),
            "error": _t("decisores.mode.error", "falló")}.get(mode or "", mode or "—")


def _not_ready(m):
    """¿Es un modelo real al que aún le falta algo? Se configura en Motores →
    Modelos de decisión (aquí nunca se pide llave ni se instala nada)."""
    return m in DC.deciders() and m != DC.OFF and not DC.decider_status(m).get("ready")


def _card_hint(m, modelo):
    """La pista bajo las tarjetas de modelo para la tarjeta enfocada."""
    if _not_ready(m):
        return _t("decisores.settings.enter_motores", "Enter abre Motores → Modelos de decisión")
    if DC.key_env(m) and DC.key_source(m) == "env":
        usar = "" if modelo == m else _t("decisores.settings.enter_use", "Enter para usarlo") + " · "
        return usar + _t("decisores.settings.key_env", "llave del entorno del sistema")
    return "" if modelo == m else _t("decisores.settings.enter_use", "Enter para usarlo")


def _error_txt(err, decider, **kw):
    """El fallo en palabras de persona (decision_errors): jamás la URL, el
    request_id ni el nombre de una clase — eso va a «d detalle»."""
    import decision_errors as DE
    return DE.human(err, decider, **kw)


# ── piezas de dibujo (cuadritos) ─────────────────────────────────────────────
def _K():
    return SB.K()


def pad(s, n):
    return HL.pad(HL.clip(s, n), n)


def center(s, n):
    s = HL.clip(s, n)
    left = max(0, (n - HL.vis(s)) // 2)
    return HL.pad(" " * left + s, n)


def caja(K, body, w, col, title="", heavy=False, tcol=None, centrar=False):
    """Un cuadrito de ancho `w` (con bordes). Título incrustado arriba."""
    w = max(6, w)
    tl, tr, bl, br, v, h = HEAVY if heavy else LIGHT
    R = K["R"]
    if title:
        t = " %s " % HL.clip(title, max(1, w - 5))
        top = "%s%s%s%s%s%s%s%s" % (col, tl, h, R, tcol or col, t, R + col,
                                    h * max(0, w - 3 - HL.vis(t)) + tr + R)
    else:
        top = "%s%s%s%s%s" % (col, tl, h * (w - 2), tr, R)
    out = [top]
    for ln in body:
        inner = center(ln, w - 4) if centrar else pad(ln, w - 4)
        out.append("%s%s%s %s %s%s%s" % (col, v, R, inner, col, v, R))
    out.append("%s%s%s%s%s" % (col, bl, h * (w - 2), br, R))
    return out


def hjoin(bloques, gap=2):
    alto = max(len(b) for b in bloques)
    anchos = [max(HL.vis(x) for x in b) for b in bloques]
    return [(" " * gap).join(HL.pad(b[i] if i < len(b) else "", a)
                             for b, a in zip(bloques, anchos)) for i in range(alto)]


def anchos(iw, n, gap=2):
    n = max(1, n)
    return [max(6, (iw - gap * (n - 1)) // n)] * n


def tabs(K, on, iw):
    out = []
    for t in TABS:
        lab = _tab_label(t)
        out.append("%s%s %s %s%s" % (K["C"] + K["BO"], K["BL"], lab, K["BR"], K["R"]) if t == on
                   else "%s  %s  %s" % (K["DK"], lab, K["R"]))
    return center("   ".join(out), iw)


def titulo(K, txt, iw, tono=0):
    t = txt.upper()
    wc = K["WCOL"]
    return HL.clip("%s%s%s %s%s%s" % (wc[tono % len(wc)] + K["BO"], t, K["R"], K["DK"],
                                     K["SEP"] * max(1, iw - HL.vis(t) - 1), K["R"]), iw)


def medidor(K, lv):
    i = DC.LEVELS.index(lv)
    if i == 0:
        return "%s▯▯▯ %s%s" % (K["DK"], _level_name("off"), K["R"])
    col = K[NCOL[lv]] + K["BO"]
    return "%s%s%s%s%s%s %s%s%s" % (col, "▮" * i, K["R"], K["DK"], "▯" * (3 - i), K["R"],
                                    col, _level_name(lv), K["R"])


def bar(K, p, n=22, tono=1):
    n = max(1, n)
    k = max(0, min(n, int(round(p * n))))
    wc = K["WCOL"]
    return "%s%s%s%s%s%s" % (wc[tono % len(wc)] + K["BO"], "█" * k, K["R"], K["DK"], "░" * (n - k), K["R"])


def wrap(txt, w):
    return SB._wrap(txt, max(4, w))


def boton(K, label, w, foco, activo=False, acol="C", tinte=None):
    """Botón-cuadrito: foco = borde grueso en acento; activo = texto con ●."""
    col = (K["C"] + K["BO"]) if foco else (K[acol] if activo else K["DK"])
    txt = ("%s● %s%s" % (K[acol] + K["BO"], label, K["R"]) if activo
           else "%s%s%s" % ((K["WH"] + K["BO"]) if foco else (K[tinte] if tinte else K["GREY"]),
                            label, K["R"]))
    return caja(K, [txt], w, col, heavy=foco, centrar=True)


def cur(K, sel):
    return ("%s%s%s " % (K["C"] + K["BO"], K["PTR"], K["R"])) if sel else "  "


# ── estado ───────────────────────────────────────────────────────────────────
def _agents():
    """Agentes del registro: [(id, nombre visible)]."""
    try:
        import agentsreg
        return [(a["name"], str(a.get("display") or a["name"]).capitalize())
                for a in agentsreg.agents()]
    except Exception:
        return []


def initial():
    S = {"tab": 1, "zona": "usos", "mi": 0, "ui": 0, "det": None, "di": 0,
         "cf": 0, "ag": 0, "preg": "", "ops": "", "hi": 0, "msg": "",
         "res": None, "pensando": None, "ctx": {}, "lvl": {}, "tabs_sel": {}, "est": {},
         "est_busy": False, "last_ctx": None}
    S["agents"] = _agents()
    return S


def _context(S):
    """{"tab","text"} del agente elegido (cacheado por agente)."""
    if not S.get("agents"):
        return {"tab": "", "text": ""}
    name = S["agents"][S["ag"] % len(S["agents"])][0]
    if name not in S["ctx"]:
        S["ctx"][name] = DC.agent_context(name)
    return S["ctx"][name]


# ── contexto de Preguntar (decision_context) ─────────────────────────────────
def _ctx_label(lv):
    return {"nada": _t("decisores.ctx.nada", "Nada"),
            "pestana": _t("decisores.ctx.pestana", "Pestaña"),
            "sesiones": _t("decisores.ctx.sesiones", "Sesiones"),
            "memoria": _t("decisores.ctx.memoria", "Memoria"),
            "cerebro": _t("decisores.ctx.cerebro", "Cerebro")}.get(lv, lv)


def _ctx_levels():
    import decision_context as C
    return C.LEVELS


def _agent_id(S):
    ags = S.get("agents") or []
    return ags[S["ag"] % len(ags)][0] if ags else ""


def _ctx_level(S):
    import decision_context as C
    return S["lvl"].get(_agent_id(S), C.DEFAULT_LEVEL)


def _ctx_tabs(S):
    return set(S["tabs_sel"].get(_agent_id(S), ()))


def _ask_decider():
    """El decisor de Preguntar (el modelo general) o None si no hay uno activo."""
    m = DC.global_model()
    return None if m == DC.OFF else m


def _budget_decider():
    """Con qué límite se calcula el medidor: el modelo activo o, sin uno, el
    primer modelo real (solo para contar tokens: no se muestra costo)."""
    m = _ask_decider()
    if m:
        return m
    ofr = DC.offered()
    return ofr[0] if ofr else "rules"


def _est_key(S):
    # con la pregunta y las opciones: el medidor hace la MISMA cuenta que `v` y
    # que el envío (lo relevante depende de lo que preguntas)
    return (_agent_id(S), _budget_decider(), tuple(sorted(_ctx_tabs(S))), S.get("preg") or "",
            tuple(_ops(S)))


def _ensure_estimates(S, sync=False):
    """El medidor de cada nivel, en un hilo y NUNCA en el camino de una tecla:
    mientras escribes la pregunta espera DEBOUNCE_S sin teclear (el medidor
    deja el valor anterior con «calculando…»)."""
    key = _est_key(S)
    if not key[0] or key in S["est"] or S.get("est_busy"):
        return
    if not sync and time.time() - S.get("est_t", 0.0) < DEBOUNCE_S:
        return
    S["est_busy"] = True

    def run():
        import decision_context as C
        out = {}
        for lv in C.LEVELS:
            try:
                out[lv] = C.estimate(lv, key[0], key[1], key[2], key[3], key[4])
            except Exception:
                out[lv] = {"tokens": 0, "mode": "vacío", "total": 0, "budget": 0, "fixed": 0}
        S["est"][key] = out
        S.setdefault("est_last", {})[key[:3]] = out
        S["est_busy"] = False
    if sync:
        run()
    else:
        threading.Thread(target=run, daemon=True, name="ctx-estimate").start()


def _est_pending(S):
    """¿El medidor de AHORA (agente, pregunta, opciones) aún no está?"""
    if TABS[S.get("tab", 0)] != "preguntar":
        return False
    key = _est_key(S)
    return bool(key[0]) and key not in S["est"]


def _est(S, lv):
    """El medidor de un nivel; mientras se recalcula (escribiste otra letra)
    se queda el último de ese agente (sin parpadeo)."""
    key = _est_key(S)
    e = (S["est"].get(key) or {}).get(lv)
    if e is None:
        e = ((S.get("est_last") or {}).get(key[:3]) or {}).get(lv)
    return e


def _enviado(e):
    """Lo que de verdad se manda (y se cobra) en ese nivel: el contexto + lo
    fijo de cada pregunta (la sobrecarga del decisor, la pregunta y sus
    opciones) — también en «Nada»."""
    return int((e or {}).get("tokens") or 0) + int((e or {}).get("fixed") or 0)


def _meter(e, did):
    """«≈ 28k tokens · $0.0012» del medidor (sin modelo activo, sin costo)."""
    import decision_context as C
    if not e:
        return "…"
    tok = "≈ %s %s" % (C.fmt_tokens(_enviado(e)), _t("decisores.ctx.tokens", "tokens"))
    if not did:
        return tok
    return "%s · %s" % (tok, C.fmt_cost(C.cost_usd(_enviado(e), did)))


def _ctx_mode_txt(mode):
    return {"todo": _t("decisores.ctx.todo", "todo"),
            "relevante": _t("decisores.ctx.relevante", "lo más relevante"),
            "reciente": _t("decisores.ctx.reciente", "lo más reciente"),
            "vacío": _t("decisores.ctx.vacio", "nada que mandar")}.get(mode, mode or "")


def _sent_line(R):
    """Qué contexto llevó la respuesta (nivel · selección · tokens)."""
    import decision_context as C
    lv = R.get("ctx_level")
    if not lv:
        return ""
    if lv == "nada":
        return _t("decisores.ask.sent_none", "sin contexto: solo la pregunta y sus opciones")
    if not R.get("ctx_tokens"):
        return _t("decisores.ask.sent_empty", "{lv}: no había nada que mandar · fue solo la pregunta",
                  lv=_ctx_label(lv))
    return _t("decisores.ask.sent", "contexto: {lv} · {modo} · ≈{n} tokens", lv=_ctx_label(lv),
              modo=_ctx_mode_txt(R.get("ctx_mode")), n=C.fmt_tokens(R["ctx_tokens"]))


# ── pestaña Ajustes ──────────────────────────────────────────────────────────
def ajustes_body(S, K, iw):
    if S.get("det") is not None:
        return detalle_body(S, K, iw)
    L = [tabs(K, "ajustes", iw), ""]
    modelo = DC.global_model()
    apagado = modelo == DC.OFF
    foco_m = S["zona"] == "modelo"
    cards = _cards()
    S["mi"] = S["mi"] % len(cards)
    L.append(titulo(K, _t("decisores.settings.which_model", "¿qué modelo decide?"), iw, 0))
    row = []
    for i, (m, w) in enumerate(zip(cards, anchos(iw, len(cards)))):
        foco = foco_m and S["mi"] == i
        activo = modelo == m
        ok, est = _model_state(m)
        col = (K["C"] + K["BO"]) if foco else ((K["OK"] if m != "off" else K["BAD"]) if activo else K["DK"])
        nom = "%s%s%s%s" % ((K["OK"] + K["BO"]) if activo and m != "off" else
                            ((K["BAD"] + K["BO"]) if activo else ((K["WH"] + K["BO"]) if foco else K["GREY"])),
                            "● " if activo else "", _model_name(m), K["R"])
        ready = ok and (m == "off" or DC.decider_status(m)["ready"])
        estc = K["DIM"] if ready or m == "off" else K["BAD"]
        row.append(caja(K, [nom, "%s%s%s" % (estc, est, K["R"])], w, col, heavy=foco, centrar=True))
    if foco_m:
        S["_cur"] = len(L) + 1
    L += hjoin(row)
    # el modelo configurado que no está (su archivo se borró, un id a mano):
    # antes quedaba en Apagado sin decir nada — va en el renglón vacío de abajo
    falta = DC.missing_model() if apagado else None
    for gi, grupo in enumerate(("agents", "workspace")):
        if gi == 0 and falta:
            L.append(center("%s%s%s" % (K["BAD"], _t("decisores.settings.model_missing", "El modelo "
                                                     "configurado ({m}) no está · elige otro en "
                                                     "Motores", m=_model_name(falta)), K["R"]), iw))
        else:
            L.append("")
        L.append(titulo(K, _t("decisores.settings.where", "dónde ayuda") + " · " + _group_label(grupo),
                        iw, 2 + 2 * gi))
        usos = [(i, p) for i, p in enumerate(DC.POINTS) if p[1] == grupo]
        for fila in (usos[:2], usos[2:]):
            row = []
            for (i, (pid, _g, _k)), w in zip(fila, anchos(iw, 2)):
                foco = (not foco_m) and S["ui"] == i
                conf = DC.point_conf(pid)
                nv = conf["level"]
                on = nv != "off" and not apagado
                col = (K["C"] + K["BO"]) if foco else (K[NCOL[nv]] if on else K["DK"])
                tcol = (K["WH"] + K["BO"]) if (foco or on) else K["GREY"]
                a, n = DC.accuracy(pid)
                extra = []
                if on and conf["model"] != DC.GENERAL:
                    extra.append(_model_name(conf["model"]))
                if on and n:
                    extra.append("%d/%d" % (a, n))
                med = medidor(K, nv if not apagado else "off")
                if extra:
                    cabe = max(0, w - 6 - HL.vis(med))
                    der = HL.clip("%s%s%s" % (K["DIM"], " · ".join(extra), K["R"]), cabe)
                    med = HL.pad(med, max(0, w - 5 - HL.vis(der))) + der
                row.append(caja(K, [med], w, col, title=_point_name(pid), heavy=foco, tcol=tcol))
                if foco:
                    S["_cur"] = len(L) + 1
            L += hjoin(row)
    L.append("")
    if foco_m:
        m = cards[S["mi"]]
        h = _card_hint(m, modelo)
        pista = "   %s%s%s" % (K["C"] + K["BO"], h, K["R"]) if h else ""
        L.append(center("%s%s%s%s" % (K["GREY"], _model_txt(m), K["R"], pista), iw))
        L.append("")
    else:
        pid = DC.POINT_IDS[S["ui"]]
        nv = DC.point_conf(pid)["level"]
        L.append(center("%s%s%s %s%s %s%s" % (K["WH"] + K["BO"], _point_name(pid), K["R"], K["GREY"],
                                             _t("decisores.settings.decides", "decide"),
                                             _point_what(pid), K["R"]), iw))
        txt = (_t("decisores.settings.master_off", "el modelo está en Apagado: ningún uso pregunta")
               if apagado else "%s: %s" % (_level_name(nv), _level_txt(nv)))
        L.append(center("%s%s%s" % (K[NCOL[nv if not apagado else "off"]] + K["BO"], txt, K["R"]), iw))
    return [HL.clip(x, iw) for x in L]


def _detail_models():
    return [DC.GENERAL] + DC.offered()


def detalle_body(S, K, iw):
    pid = DC.POINT_IDS[S["det"]]
    grupo = DC.POINTS[S["det"]][1]
    u = DC.point_conf(pid)
    d = S["di"]
    L = [center("%s%s%s  %s· %s%s" % (K["WH"] + K["BO"], _point_name(pid), K["R"], K["DK"],
                                     _group_label(grupo), K["R"]), iw),
         center("%s%s %s%s" % (K["GREY"], _t("decisores.settings.decides", "decide"),
                               _point_what(pid), K["R"]), iw),
         center("%s%s %s%s" % (K["DK"], _t("decisores.detail.when", "pregunta"),
                               _point_when(pid), K["R"]), iw), ""]
    L.append(titulo(K, _t("decisores.detail.how_much", "¿cuánto lo dejas hacer?"), iw, 0))
    if d == 0:
        S["_cur"] = len(L) + 1
    L += hjoin([boton(K, _level_name(nv).capitalize(), w, d == 0 and u["level"] == nv, u["level"] == nv,
                      NCOL[nv] if nv != "off" else "GREY", tinte="DK" if nv == "off" else "DIM")
                for nv, w in zip(DC.LEVELS, anchos(iw, 4))])
    if u["level"] != "decide":
        txt = _level_txt(u["level"])
    elif pid == "workspace.security":
        # puede SUBIR el riesgo, nunca bajarlo: en «Decide» solo aplica «alto»
        txt = _t("decisores.detail.acts_if_security", "solo sube el aviso a alto si está ≥ {n} % "
                 "seguro · nunca lo baja", n=u["threshold"])
    else:
        txt = _t("decisores.detail.acts_if", "actúa solo si está ≥ {n} % seguro", n=u["threshold"])
    L.append(center("%s%s%s" % (K["DIM"], txt, K["R"]), iw))
    L.append("")
    L.append(titulo(K, _t("decisores.detail.model", "modelo"), iw, 2))
    ops = _detail_models()
    if d == 1:
        S["_cur"] = len(L) + 1
    L += hjoin([boton(K, _model_name(m), w, d == 1 and u["model"] == m, u["model"] == m)
                for m, w in zip(ops, anchos(iw, len(ops)))])
    gm = DC.global_model()
    L.append(center("%s%s%s" % (K["DIM"], _t("decisores.detail.uses_general", "usa el de Ajustes ({m})",
                                             m=_model_name(gm)) if u["model"] == DC.GENERAL
                                else _t("decisores.detail.uses_own", "solo este uso usa {m}",
                                        m=_model_name(u["model"])), K["R"]), iw))
    L.append("")
    L.append(titulo(K, _t("decisores.detail.threshold", "seguridad mínima para decidir solo"), iw, 4))
    if d == 2:
        S["_cur"] = len(L) + 1
    th = u["threshold"]
    k = max(1, min(20, round((th - 50) / 2.5)))
    wc = K["WCOL"]
    sl = "%s%s●%s%s%s%s   %s%d %%%s" % (wc[2 % len(wc)] + K["BO"], "━" * (k - 1), K["R"], K["DK"],
                                       "─" * (20 - k), K["R"], K["WH"] + K["BO"], th, K["R"])
    if u["level"] != "decide":
        sl = "%s━━━━━━━━━━ %d %%   %s%s" % (K["DK"], th, _t("decisores.detail.only_decide",
                                                           "solo cuenta en «Decide»"), K["R"])
    # la guía para el umbral: qué tan seguro estuvo las últimas veces (encendido)
    ult = DV.ultimas_confianzas(pid)
    if ult:
        sl += "   %s%s%s" % (K["DIM"], _t("decisores.detail.latest", "últimas: {v}",
                                          v=" · ".join(str(x) for x in ult)), K["R"])
    L += caja(K, [sl], iw, (K["C"] + K["BO"]) if d == 2 else K["DK"], heavy=d == 2, centrar=True)
    L += [center(x, iw) for x in caja(K, ["%s%s  ⏎%s" % (K["C"] + K["BO"], _t("decisores.detail.done", "Listo"),
                                                       K["R"])], 16, K["B2"], centrar=True)]
    a, n = DC.accuracy(pid)
    total = DC.point_total(pid)
    cuantas = _t("decisores.detail.count", "{n} decisiones", n=total)
    L.append(center(("%s%s · %s %s %s%s%s" % (K["DIM"], cuantas, _t("decisores.detail.accuracy", "acierto"),
                                              bar(K, a / n, 14, 3), K["WH"],
                                              _t("decisores.detail.of", "{a} de {n}", a=a, n=n), K["R"])) if n
                    else "%s%s · %s%s" % (K["DK"], cuantas, _t("decisores.detail.ungraded",
                                                                "aún sin calificar · califica en Historial"),
                                          K["R"]), iw))
    return [HL.clip(x, iw) for x in L]


# ── pestaña Preguntar ────────────────────────────────────────────────────────
def _ops(S):
    return [o.strip() for o in S["ops"].split(",") if o.strip()]


def preguntar_body(S, K, iw):
    L = [tabs(K, "preguntar", iw), ""]
    f = S["cf"]
    L.append(titulo(K, _t("decisores.ask.which_agent", "¿a qué agente le preguntas?"), iw, 0))
    ags = S.get("agents") or []
    if f == 0:
        S["_cur"] = len(L) + 1
    if ags:
        S["ag"] %= len(ags)
        n = min(4, len(ags))
        start = max(0, min(S["ag"] - n + 1, len(ags) - n)) if S["ag"] >= n else 0
        vis = list(range(start, start + n))
        L += hjoin([boton(K, ags[i][1], w, f == 0 and S["ag"] == i, S["ag"] == i, "OK")
                    for i, w in zip(vis, anchos(iw, n))])
        L += _ctx_row(S, K, iw, f == 1)
    else:
        L += caja(K, ["%s%s%s" % (K["DK"], _t("decisores.ask.no_agents",
                                               "no hay agentes registrados · pregunta sin contexto"), K["R"])],
                  iw, (K["C"] + K["BO"]) if f == 0 else K["DK"], heavy=f == 0, centrar=True)
    caret = "%s▏%s" % (K["C"] + K["BO"], K["R"])
    for idx, key, lab, vacio in ((2, "preg", _t("decisores.ask.question", "Pregunta"),
                                  _t("decisores.ask.question_ph", "escribe tu pregunta")),
                                 (3, "ops", _t("decisores.ask.options", "Opciones · separadas por coma"),
                                  _t("decisores.ask.options_ph", "sí, no, tal vez"))):
        foco = f == idx
        val = S[key]
        txt = ("%s%s%s" % ((K["WH"] + K["BO"]) if foco else K["WH"], val, K["R"]) if val
               else "%s%s%s" % (K["DK"], vacio, K["R"])) + (caret if foco else "")
        if foco:
            S["_cur"] = len(L) + 1
        L += caja(K, [txt], iw, (K["C"] + K["BO"]) if foco else K["DK"], title=lab, heavy=foco,
                  tcol=(K["C"] + K["BO"]) if foco else K["DIM"])
    ops = _ops(S)
    R0 = S.get("res") or {}
    if ops:
        elegido = R0.get("choice") if R0.get("ok") else None
        L.append(center("  ".join(("%s[ ● %s ]%s" % (K["OK"] + K["BO"], o, K["R"])) if o == elegido
                                  else "%s[ %s ]%s" % (K["GREY"], o, K["R"]) for o in ops), iw))
    else:
        L.append("")
    if f == 4:
        S["_cur"] = len(L) + 1
    listo = len(ops) >= 2
    tinta = ((K["C"] + K["BO"]) if f == 4 else K["B2"] + K["BO"]) if listo else K["DK"]
    lab = (_t("decisores.ask.button", "Preguntar") + "  ⏎") if listo else _t("decisores.ask.missing",
                                                                            "faltan opciones")
    L += [center(x, iw) for x in caja(K, ["%s%s%s" % (tinta, lab, K["R"])], 22,
                                      ((K["C"] + K["BO"]) if f == 4 else K["B2"]) if listo else K["DK"],
                                      heavy=f == 4 and listo, centrar=True)]
    R = S.get("res")
    if S.get("pensando"):
        sp = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.time() * 10) % 10]
        L += caja(K, ["%s%s %s%s" % (K["C"], sp, _t("decisores.ask.thinking", "pensando con {m}…",
                                                     m=_model_name(S["pensando"])), K["R"])],
                  iw, K["B2"], title=_t("decisores.ask.answer", "Respuesta"), tcol=K["DIM"])
    elif R and not R.get("ok"):
        L += caja(K, _fallo_lines(S, K, R, iw - 4) + _aviso_nube_linea(S, K, R, iw - 4), iw,
                  K["BAD"], title=_t("decisores.ask.failed", "No se pudo"), tcol=K["BAD"] + K["BO"])
    elif R:
        import decision_context as C
        real = ""
        tk = R.get("tokens") or {}
        if tk.get("in") is not None:
            real = " · " + _t("decisores.ask.real", "real {n} tokens", n=C.fmt_tokens(tk["in"]))
        if R.get("cost_usd") is not None:
            real += " · " + C.fmt_cost(R["cost_usd"])
        quien = _shown(R["decider"])
        if R.get("p_known", True) is False:            # no dio su probabilidad: no se inventa
            seguro = (_t("decisores.ask.sure_unknown", "sin probabilidad · {m}", m=quien) if quien
                      else _t("decisores.ask.sure_unknown_only", "sin probabilidad"))
        else:
            seguro = (_t("decisores.ask.sure", "{p} % seguro · {m}", p=round(R["p"] * 100), m=quien)
                      if quien else _t("decisores.ask.sure_only", "{p} % seguro",
                                       p=round(R["p"] * 100)))
        cuerpo = ["%s%s %s%s   %s%s%s%s" % (K["OK"] + K["BO"], K["PTR"], R["choice"], K["R"], K["DIM"],
                                           seguro, real, K["R"])]
        if _sent_line(R):
            cuerpo.append("%s%s%s" % (K["DIM"], _sent_line(R), K["R"]))
        if R.get("shrunk_to"):
            cuerpo.append("%s%s%s" % (K["DIM"], _t(
                "decisores.ask.shrunk", "recorté el contexto a ≈{n} tokens para que cupiera",
                n=C.fmt_tokens(R["shrunk_to"])), K["R"]))
        cuerpo.append("")
        for o, p in sorted(R["probs"].items(), key=lambda kv: -kv[1])[:3]:
            cuerpo.append("%s%s%s %s %s%3d %%%s" % (K["WH"] if o == R["choice"] else K["GREY"], pad(o, 18),
                                                    K["R"], bar(K, p, max(4, iw - 34)), K["DIM"],
                                                    round(p * 100), K["R"]))
        cuerpo += _aviso_nube_linea(S, K, R, iw - 4)
        L += caja(K, cuerpo, iw, K["OK"], title=_t("decisores.ask.answer", "Respuesta"), tcol=K["OK"] + K["BO"])
    else:
        L.append(center("%s%s%s" % (K["DK"], _t("decisores.ask.hint",
                                                 "no sabe datos ni la fecha: elige entre tus opciones"),
                                    K["R"]), iw))
    return [HL.clip(x, iw) for x in L]


def _fallo_lines(S, K, R, w):
    """El cuerpo de la caja «No se pudo»: el mensaje para personas y, con «d»,
    el detalle técnico (código, clase, status, tipo, request_id)."""
    import decision_errors as DE
    msg = _error_txt(R.get("error"), R.get("decider"), sent_tokens=R.get("sent_tokens"),
                     timeout_ms=MANUAL_TIMEOUT_MS, where="ask", detail=R.get("error_detail"),
                     elapsed_ms=R.get("ms"))
    out = ["%s%s%s" % (K["BAD"], ln, K["R"]) for ln in wrap(msg, w)]
    det = DE.detail_lines(R.get("error_detail"), R.get("error"))
    if S.get("detalle") and det and S.get("cf") not in (2, 3):
        out.append("")
        ancho = max(HL.vis(lab) for lab, _v in det) + 2
        out += ["%s%s%s%s" % (K["DIM"], pad(lab, ancho), K["GREY"] + val, K["R"]) for lab, val in det]
    if det and S.get("cf") not in (2, 3):        # escribiendo, «d» es una letra
        out.append("%sd · %s%s" % (K["DIM"], _t("decisores.ask.hide_detail", "ocultar detalle")
                                    if S.get("detalle") else _t("decisores.ask.show_detail",
                                                                "ver detalle"), K["R"]))
    return out


def _ctx_row(S, K, iw, foco):
    """Contexto: 5 cuadritos con su medidor (≈ tokens) y, debajo, el costo y si
    va «todo» o «lo más relevante» del elegido."""
    _ensure_estimates(S)
    did = _ask_decider()
    sel = _ctx_level(S)
    L = [titulo(K, _t("decisores.ctx.title", "contexto"), iw, 2)]
    row = []
    for lv, w in zip(_ctx_levels(), anchos(iw, len(_ctx_levels()))):
        on = lv == sel
        e = _est(S, lv)
        import decision_context as C
        n = ("≈" + C.fmt_tokens(_enviado(e))) if e else "…"
        if lv == "sesiones" and not _ctx_tabs(S):
            n = _t("decisores.ctx.pick", "elige")
        borde = (K["C"] + K["BO"]) if (foco and on) else (K["OK"] if on else K["DK"])
        nom = "%s%s%s%s" % ((K["OK"] + K["BO"]) if on else ((K["WH"] + K["BO"]) if foco else K["GREY"]),
                            "● " if on and w >= 14 else "", _ctx_label(lv), K["R"])
        row.append(caja(K, [nom, "%s%s%s" % (K["DIM"] if e else K["DK"], n, K["R"])], w, borde,
                        heavy=foco and on, centrar=True))
    if foco:
        S["_cur"] = len(L) + 1
    L += [center(x, iw) for x in hjoin(row)]
    e = _est(S, sel)
    if sel == "nada":
        txt = _t("decisores.ctx.only_q", "solo la pregunta y sus opciones")
        if e:
            txt = "%s · %s" % (_meter(e, did), txt)
    elif sel == "sesiones" and not _ctx_tabs(S):
        txt = _t("decisores.ctx.pick_sessions", "Enter elige las sesiones que van")
    elif not e:
        txt = _t("decisores.ctx.calc", "calculando…")
    elif e["mode"] == "vacío":
        txt = _t("decisores.ctx.empty", "no hay nada que mandar en este nivel")
    elif not did:
        txt = "%s · %s" % (_meter(e, None), _t("decisores.ctx.no_model", "sin modelo activo: "
                                                "configúralo en Motores"))
    elif _est_pending(S):
        txt = "%s · %s" % (_meter(e, did), _ctx_mode_txt(e["mode"]))
    else:
        txt = "%s · %s · %s" % (_meter(e, did), _ctx_mode_txt(e["mode"]),
                                _t("decisores.ctx.v_hint", "v fuentes"))
    if e and sel != "nada" and _est_pending(S):  # el valor de antes, mientras llega el nuevo
        txt += " · %s%s" % (K["DK"], _t("decisores.ctx.calc", "calculando…"))
    L.append(center("%s%s%s" % (K["GREY"], txt, K["R"]), iw))
    return L


def sesiones_body(S, K, iw):
    """Elegir qué sesiones (pestañas) del agente van como contexto."""
    ss = S["selsess"]
    items = ss["items"]
    L = [center("%s%s%s" % (K["WH"] + K["BO"], _t("decisores.ss.title", "¿Qué sesiones van?"), K["R"]), iw), ""]
    if not items:
        L.append(center("%s%s%s" % (K["DK"], _t("decisores.ss.none", "este agente no tiene pestañas"),
                                    K["R"]), iw))
        return L
    import decision_context as C
    ss["i"] %= len(items)
    alto = 10
    start = max(0, min(ss["i"] - alto // 2, len(items) - alto))
    filas = []
    for k in range(start, min(len(items), start + alto)):
        it = items[k]
        on = it["slug"] in ss["chosen"]
        s = k == ss["i"]
        marca = "%s[%s]%s" % (K["OK"] + K["BO"] if on else K["DK"], "x" if on else " ", K["R"])
        izq = "%s%s %s%s%s" % (cur(K, s), marca, (K["WH"] + K["BO"]) if s else K["GREY"], it["name"], K["R"])
        der = "%s≈%s%s" % (K["DIM"], C.fmt_tokens(it["tokens"]), K["R"]) if it["text"] else \
            "%s%s%s" % (K["DK"], _t("decisores.ss.no_summary", "sin resumen"), K["R"])
        filas.append(HL.pad(HL.clip(izq, iw - 14), iw - 12) + der)
        if s:
            S["_cur"] = len(L) + 1 + len(filas) - 1
    L += caja(K, filas, iw, K["DK"], title=_t("decisores.ss.list", "pestañas de {a}", a=ss["agent"]),
              tcol=K["DIM"])
    tot = sum(it["tokens"] for it in items if it["slug"] in ss["chosen"])
    L.append(center("%s%s%s" % (K["GREY"], _t("decisores.ss.total", "{n} elegidas · ≈{t} tokens",
                                              n=len(ss["chosen"]), t=C.fmt_tokens(tot)), K["R"]), iw))
    return [HL.clip(x, iw) for x in L]


def preview_body(S, K, iw):
    """`v`: QUÉ fuentes van y cuánto pesa cada una — nunca el contenido."""
    import decision_context as C
    pv = S["preview"]
    ctx = pv["ctx"]
    did = pv["did"]
    lv = ctx["level"] if ctx else pv.get("level") or _ctx_level(S)
    L = [center("%s%s%s" % (K["WH"] + K["BO"], _t("decisores.pv.title", "Se mandaría · {lv}",
                                                   lv=_ctx_label(lv)), K["R"]), iw)]
    if ctx is None:
        L += ["", center("%s%s%s" % (K["DK"], _t("decisores.ctx.calc", "calculando…"), K["R"]), iw)]
        return L
    if ctx["mode"] == "vacío" or not ctx["sources"]:
        L += ["", center("%s%s%s" % (K["DK"], _t("decisores.ctx.empty", "no hay nada que mandar en este nivel"),
                                     K["R"]), iw)]
        if ctx.get("excluded"):
            L.append(center("%s%s%s" % (K["GREY"], _t("decisores.pv.excluded", "excluidos: {n} (de "
                                                      "otros socios, conversaciones o privados)",
                                                      n=ctx["excluded"]),
                                        K["R"]), iw))
        return L
    # el costo es el de la pregunta ENTERA: el contexto + lo fijo de cada pregunta
    fijo = C.fixed_tokens(did, S.get("preg") or "", _ops(S)) if did else 0
    costo = (" · " + C.fmt_cost(C.cost_usd(ctx["tokens"] + fijo, did))) if did else ""
    L.append(center("%s%s · ≈%s %s%s%s" % (
        K["GREY"], _ctx_mode_txt(ctx["mode"]), C.fmt_tokens(ctx["tokens"]),
        _t("decisores.pv.of", "de {b} tokens", b=C.fmt_tokens(ctx["budget"])), costo, K["R"]), iw))
    L.append("")
    srcs = sorted(ctx["sources"], key=lambda x: -x[1])
    tot = max(1, sum(t for _l, t in srcs))
    alto = 12
    pv["scroll"] = max(0, min(pv.get("scroll", 0), max(0, len(srcs) - alto)))
    filas = []
    for lb, tk in srcs[pv["scroll"]:pv["scroll"] + alto]:
        der = "%s≈%s · %d%%%s" % (K["DIM"], C.fmt_tokens(tk), round(100.0 * tk / tot), K["R"])
        filas.append(HL.pad(HL.clip("%s%s%s" % (K["GREY"], lb, K["R"]), iw - 18), iw - 16) + der)
    mas = len(srcs) - pv["scroll"] - len(filas)
    if mas > 0:
        filas.append("%s%s%s" % (K["DK"], _t("decisores.pv.more", "… y {n} más (↓)", n=mas), K["R"]))
    L += caja(K, filas, iw, K["DK"], title=_t("decisores.pv.sources", "fuentes ({n})", n=len(srcs)),
              tcol=K["DIM"])
    if ctx.get("excluded"):
        L.append(center("%s%s%s" % (K["GREY"], _t("decisores.pv.excluded", "excluidos: {n} (de otros "
                                                  "socios, conversaciones o privados)",
                                                  n=ctx["excluded"]), K["R"]), iw))
    L.append(center("%s%s%s" % (K["DK"], _t("decisores.pv.note", "el contenido no se muestra · sin "
                                             "secretos, sin lo privado ni lo de otros socios"),
                                K["R"]), iw))
    return [HL.clip(x, iw) for x in L]


# ── pestaña Historial ────────────────────────────────────────────────────────
def historial_body(S, K, iw):
    L = [tabs(K, "historial", iw), ""]
    H = DC.history(200, ok_only=False)
    st = DC.stats()
    pct = "%d %%" % round(100 * st["correct"] / st["graded"]) if st["graded"] else "—"
    stats = [(_t("decisores.hist.decisions", "decisiones"), str(st["total"]), "WH"),
             (_t("decisores.hist.accuracy", "acierto"), pct, "OK"),
             (_t("decisores.hist.active", "usos activos"),
              _t("decisores.hist.of", "{a} de {n}", a=st["active"], n=st["points"]), "B")]
    L += hjoin([caja(K, ["%s%s%s" % (K[c] + K["BO"], v, K["R"]), "%s%s%s" % (K["DIM"], t, K["R"])], w,
                     K["DK"], centrar=True) for (t, v, c), w in zip(stats, anchos(iw, 3))])
    # encendido: «hoy: 7 consultas · 1 aplicada · 3 sugeridas» en el renglón que
    # separa (apagado, el renglón vacío de siempre); y qué cambió cada una
    vis = DV.encendido()
    hoy = DV.linea_hoy() if vis else ""
    L.append(center("%s%s%s" % (K["DIM"], hoy, K["R"]), iw) if hoy else "")
    alto = 9
    if not H:
        L.append(center("%s%s%s" % (K["DK"], _t("decisores.hist.empty",
                                                 "Nada todavía · prende un uso en Ajustes o pregunta algo"),
                                    K["R"]), iw))
        L += [""] * (alto - 1)
        S["_cur"] = len(L) - 1
        return [HL.clip(x, iw) for x in L]
    S["hi"] = max(0, min(S["hi"], len(H) - 1))
    start = max(0, min(S["hi"] - alto // 2, len(H) - alto))
    filas = []
    for i in range(start, min(len(H), start + alto)):
        h = H[i]
        s = i == S["hi"]
        t = h.get("truth")
        falla = not h.get("ok")
        ok = ("%s✓%s" % (K["OK"], K["R"]) if t is True else "%s✗%s" % (K["BAD"], K["R"]) if t is False else " ")
        hora = str(h.get("ts", ""))[11:16]
        tinta = K["DK"] if falla else ((K["WH"] + K["BO"]) if s else K["WH"])
        # encendido, una aplicada dice QUÉ cambió («nota → hecho») en vez de la elección
        cambio = DV.efecto(h, corto=True) if vis and not falla else ""
        izq = "%s%s%s%s %s%s%s %s%s %s%s%s%s%s%s" % (
            cur(K, s), K["DK"], hora, K["R"],
            (K["C"] + K["BO"]) if s else K["GREY"], pad(_point_short(h.get("point")), 10), K["R"],
            K["WH"] if s and not falla else K["GREY"], pad(h.get("q") or "—", 10), K["DK"],
            "  " if cambio else "→ ", K["R"] if cambio else "", tinta,
            ("—" if falla else (cambio or h.get("choice") or "")), K["R"])
        modo = _mode_name(h.get("mode") if h.get("ok") else "error")
        mcol = K["BAD"] if falla else {"apply": K["OK"], "suggest": K["B"], "observe": K["B2"]}.get(
            h.get("mode"), K["DIM"])
        pc = "    " if falla else ("   ?" if h.get("p") is None
                                     else "%3d%%" % round(float(h.get("p") or 0) * 100))
        der = "%s%s%s %s%s%s %s" % (mcol, pad(modo, 8), K["R"], K["DIM"], pc, K["R"], ok)
        dw = HL.vis(der)
        filas.append(HL.pad(HL.clip(izq + K["R"], iw - dw - 5), iw - dw - 4) + der)
        if s:
            S["_cur"] = len(L) + 1 + len(filas) - 1
    filas += [""] * (alto - len(filas))
    L += caja(K, filas, iw, K["DK"], title=_t("decisores.hist.latest", "últimas decisiones"), tcol=K["DIM"])
    h = H[S["hi"]]
    quien = _shown(h.get("decider"))
    con = (" · " + _t("decisores.hist.with", "con {m}", m=quien)) if quien else ""
    if not h.get("ok"):
        import decision_errors as DE
        L.append(center("%s%s%s · %s%s" % (
            K["GREY"], _point_name(h.get("point")), con, DE.short(h.get("error")), K["R"]), iw))
        return [HL.clip(x, iw) for x in L]
    L.append(center("%s%s%s · %s   %s%s%s  %s%s%s %s  %sn%s %s" % (
        K["GREY"], _point_name(h.get("point")), con,
        (DV.efecto(h) if vis else "") or _mode_name(h.get("mode")), K["WH"] + K["BO"],
        _t("decisores.hist.right", "¿acertó?"), K["R"],
        K["OK"] + K["BO"], _t("decisores.hist.yes_key", "s"), K["R"], _t("decisores.hist.yes", "sí"),
        K["BAD"] + K["BO"], K["R"], _t("decisores.hist.no", "no")), iw))
    return [HL.clip(x, iw) for x in L]


# ── ayuda (i / ?) ────────────────────────────────────────────────────────────
def _info_txt(vista):
    if vista == "detalle":
        return (_t("decisores.info.detail.p", "Aquí afinas un solo uso: cuánto lo dejas hacer, con qué "
                   "modelo y qué tan seguro debe estar para decidir solo. Enter guarda y vuelve."),
                [_t("decisores.info.detail.l1", "Apagado — no pregunta nada"),
                 _t("decisores.info.detail.l2", "Observa — mide sin cambiar nada"),
                 _t("decisores.info.detail.l3", "Sugiere — la muestra; no la aplica"),
                 _t("decisores.info.detail.l4", "Decide — actúa solo sobre el umbral")])
    if vista == "ajustes":
        return (_t("decisores.info.settings.p", "Elige qué modelo decide y en qué partes ayuda. Cada "
                   "cuadrito es independiente: puedes prender Memoria y dejar Skills apagado."),
                [_t("decisores.info.settings.l1", "Observa — decide en silencio y lo anota"),
                 _t("decisores.info.settings.l2", "Sugiere — la muestra; no la aplica"),
                 _t("decisores.info.settings.l3", "Decide — actúa solo si está muy seguro")])
    if vista == "preguntar":
        return (_t("decisores.info.ask.p", "Pregúntale algo rápido y elige cuánto contexto lleva: "
                   "nada, su última pestaña, las sesiones que elijas, su memoria o todo el cerebro "
                   "(si no cabe, lo más relevante). Cada nivel dice antes cuántos tokens y cuánto "
                   "cuesta; v muestra qué fuentes van."),
                [_t("decisores.info.ask.l1", "Sin secretos: se quitan antes de salir"),
                 _t("decisores.info.ask.l2", "Nunca va un .md con «privado: true» ni la carpeta privado/"),
                 _t("decisores.info.ask.l3", "Solo elige entre tus opciones")])
    return (_t("decisores.info.hist.p", "Todo lo que decidió, guardado solo en esta computadora. Dile si "
               "acertó (s/n): así se mide cada uso antes de dejarlo hacer más."),
            [_t("decisores.info.hist.l1", "s — acertó"), _t("decisores.info.hist.l2", "n — falló"),
             _t("decisores.info.hist.l3", "el acierto te dice cuándo subir de nivel")])


def _flujo_que():
    return [(_t("decisores.info.f1", "algo duda"), _t("decisores.info.f1n", "memoria, un agente…")),
            (_t("decisores.info.f2", "el decisor elige"), _t("decisores.info.f2n", "entre opciones fijas")),
            (_t("decisores.info.f3", "según su nivel"), _t("decisores.info.f3n", "observa · sugiere · decide"))]


def _flujo_como():
    return [(_t("decisores.info.c1", "el punto pregunta"), _t("decisores.info.c1n", "opciones fijas")),
            (_t("decisores.info.c2", "quita secretos"), _t("decisores.info.c2n", "antes de salir")),
            (_t("decisores.info.c3", "responde"), _t("decisores.info.c3n", "con tiempo límite")),
            (_t("decisores.info.c4", "se anota"), _t("decisores.info.c4n", "bitácora local"))]


def _como_p():
    return _t("decisores.info.how.p", "Todos los modelos hablan el mismo idioma (un contrato): cambiar "
              "de modelo no toca nada más. Si falla o tarda, todo sigue como si no existiera.")


def _como_dim():
    return _t("decisores.info.how.dim", "Apagado: no sale nada · cada uso encendido manda su "
              "pregunta y un contexto mínimo; Preguntar con Memoria o Cerebro, tu cerebro sin "
              "secretos, lo privado ni lo de otros · la bitácora es local.")


def _models_p():
    """La ayuda de Ajustes sobre los modelos."""
    return _t("decisores.info.models.p", "Los modelos de decisión se consiguen en Motores → Modelos "
              "de decisión: ahí conectas su llave y lo pruebas, una sola vez. Aquí eliges cuál "
              "decide y en qué usos ayuda; si a uno le falta algo, Enter en su tarjeta te lleva ahí.")


def info_blocks(vista):
    """Bloques del cuadro vertical (ventanas angostas)."""
    texto, lista = _info_txt(vista)
    out = [("flow", _flujo_que()), ("gap",), ("p", texto), ("list", lista)]
    if vista == "ajustes":
        out += [("h", _t("decisores.info.models", "modelos")), ("p", _models_p())]
    return out + [("gap",), ("h", _t("decisores.info.how", "cómo lo hicimos")), ("flow", _flujo_como()),
                  ("p", _como_p()), ("dim", _como_dim())]


def flujo(K, pasos, iw, tono):
    n = len(pasos)
    w = max(10, (iw - 3 * (n - 1)) // n)
    wc = K["WCOL"]
    bloques = []
    for i, (t, nota) in enumerate(pasos):
        col = wc[(tono + i) % len(wc)]
        b = caja(K, ["%s%s%s" % (col + K["BO"], t, K["R"])], w, col, centrar=True)
        b.append(center("%s%s%s" % (K["DIM"], nota, K["R"]), w))
        bloques.append(b)
        if i < n - 1:
            bloques.append(["   ", "%s → %s" % (K["C"] + K["BO"], K["R"]), "   ", "   "])
    return [center(x, iw) for x in hjoin(bloques, gap=0)]


def info_body(K, vista, iw):
    """La ayuda horizontal: qué es (flujo) · texto | viñetas · cómo lo hicimos."""
    texto, lista = _info_txt(vista)
    L = [titulo(K, _t("decisores.info.what", "qué es"), iw, 0), ""] + flujo(K, _flujo_que(), iw, 0) + [""]
    lw = (iw - 3) // 2
    izq = ["%s%s%s" % (K["WH"], ln, K["R"]) for ln in wrap(texto, lw)]
    der = []
    for x in lista:
        for j, ln in enumerate(wrap(x, lw - 2)):
            der.append("%s%s%s %s%s%s" % (K["C"], "·" if j == 0 else " ", K["R"], K["GREY"], ln, K["R"]))
    for i in range(max(len(izq), len(der))):
        a = izq[i] if i < len(izq) else ""
        b = der[i] if i < len(der) else ""
        L.append(HL.pad(a, lw) + " %s│%s " % (K["DK"], K["R"]) + b)
    if vista == "ajustes":
        # corto a propósito: la ayuda entera cabe con el wordmark grande
        L += ["", titulo(K, _t("decisores.info.models", "modelos"), iw, 1)]
        L += ["%s%s%s" % (K["GREY"], ln, K["R"]) for ln in wrap(_models_p(), iw)]
    L += ["", titulo(K, _t("decisores.info.how", "cómo lo hicimos"), iw, 3), ""] \
        + flujo(K, _flujo_como(), iw, 2) + [""]
    L += ["%s%s%s" % (K["GREY"], ln, K["R"]) for ln in wrap(_como_p(), iw)]
    L += ["%s%s%s" % (K["DK"], ln, K["R"]) for ln in wrap(_como_dim(), iw)]
    return [HL.clip(x, iw) for x in L]


def info_render(S, K, w, h, word, vista, titulo_caja):
    bw = max(60, min(96, w - 10))
    if bw < 70:                              # angosto: el cuadro vertical de siempre
        return SB.info_frame(K, w, h, word, titulo_caja, info_blocks(vista), state=S["info"], box_w=60)
    st = S["info"] if isinstance(S["info"], dict) else {}
    out = SB.frame(K, w, h, word, titulo_caja, lambda iw: info_body(K, vista, iw),
                   ((u"↑↓", _t("decisores.k.move_info", "mover")),
                    ("Esc", _t("decisores.k.close", "cerrar"))),
                   box_w=bw, scroll=st.get("scroll", 0))
    st["scroll"] = max(0, min(st.get("scroll", 0), SB.frame.last_max_scroll))
    return out


# ── marco ────────────────────────────────────────────────────────────────────
def _chips(vista):
    k = {"ajustes": ((_t("decisores.k.arrows", "flechas"), _t("decisores.k.move", "moverse")),
                     (_t("decisores.k.space", "espacio"), _t("decisores.k.change", "cambiar")),
                     ("Enter", _t("decisores.k.open", "abrir")), ("Tab", _t("decisores.k.tab", "pestaña")),
                     ("?", _t("decisores.k.help", "ayuda")), ("q", _t("decisores.k.quit", "salir"))),
         "detalle": ((u"↑↓", _t("decisores.k.row", "fila")), (u"←→", _t("decisores.k.pick", "elegir")),
                     ("Enter", _t("decisores.k.done", "listo")), ("?", _t("decisores.k.help", "ayuda"))),
         "preguntar": ((u"↑↓", _t("decisores.k.move", "moverse")), (u"←→", _t("decisores.k.pick", "elegir")),
                       ("Enter", _t("decisores.k.ask", "preguntar")), ("v", _t("decisores.k.sources", "fuentes")),
                       ("Tab", _t("decisores.k.tab", "pestaña")), ("?", _t("decisores.k.help", "ayuda")),
                       ("Esc", _t("decisores.k.quit", "salir"))),
         "escribiendo": ((u"↑↓", _t("decisores.k.move", "moverse")),
                         ("Enter", _t("decisores.k.ask", "preguntar")),
                         ("Tab", _t("decisores.k.tab", "pestaña")),
                         ("Esc", _t("decisores.k.done", "listo"))),
         "sesiones": ((u"↑↓", _t("decisores.k.move", "moverse")),
                      (_t("decisores.k.space", "espacio"), _t("decisores.k.mark", "marca")),
                      ("a", _t("decisores.k.all", "todas")), ("Enter", _t("decisores.k.done", "listo")),
                      ("Esc", _t("decisores.k.cancel", "cancelar"))),
         "fuentes": ((u"↑↓", _t("decisores.k.move_info", "mover")),
                     ("v · Esc", _t("decisores.k.close", "cerrar"))),
         "historial": ((u"↑↓", _t("decisores.k.move", "moverse")), (_t("decisores.k.yn", "s/n"), _t("decisores.k.grade", "calificar")),
                       ("Tab", _t("decisores.k.tab", "pestaña")), ("?", _t("decisores.k.help", "ayuda")),
                       ("q", _t("decisores.k.quit", "salir")))}
    return k[vista]


def _vista(S):
    tab = TABS[S["tab"]]
    if S.get("selsess"):
        return "sesiones"
    if S.get("preview"):
        return "fuentes"
    if tab == "ajustes" and S.get("det") is not None:
        return "detalle"
    if tab == "preguntar" and S["cf"] in (2, 3):
        return "escribiendo"
    return tab


def render(S, w, h):
    K = _K()
    word = HL.section_word("decisores")
    tab = TABS[S["tab"]]
    vista = _vista(S)
    det = vista == "detalle"
    if S.get("info"):
        cab = (_point_name(DC.POINT_IDS[S["det"]]) if det else _tab_label(tab)).upper()
        return info_render(S, K, w, h, word, "detalle" if det else tab,
                           "%s · %s" % (_t("decisores.info.title", "AYUDA"), cab))
    if vista in ("sesiones", "fuentes"):
        body_fn = sesiones_body if vista == "sesiones" else preview_body
        return SB.frame(K, w, h, word, "%s · %s" % (_tab_label("preguntar").upper(),
                                                     _t("decisores.ctx.title", "contexto").upper()),
                        lambda iw: body_fn(S, K, iw), _chips(vista), msg=S.get("msg", ""),
                        cursor_line=lambda: S.get("_cur", 0), box_w=BOX_W, stable_rows=18)
    body = {"ajustes": ajustes_body, "preguntar": preguntar_body, "historial": historial_body}[tab]
    title = ("%s · %s" % (_tab_label("ajustes").upper(), _point_name(DC.POINT_IDS[S["det"]]).upper())
             if det else word)
    return SB.frame(K, w, h, word, title, lambda iw: body(S, K, iw), _chips(vista),
                    msg=S.get("msg", ""), cursor_line=lambda: S.get("_cur", 0),
                    box_w=BOX_W, stable_rows=26)


# ── acciones ─────────────────────────────────────────────────────────────────
#: Fallos en los que NADA salió del equipo (no hay aviso de la nube que dar).
_NADA_SALIO = frozenset(("off", "not_installed", "need_options", "no_key", "proxy",
                         "invalid_key", "insecure_url", "breaker", "bad_input"))


def _salio(r):
    """¿La pregunta (con su contexto) llegó a salir hacia el decisor?"""
    if (r or {}).get("ok"):
        return True
    code = (r or {}).get("error")
    if code in _NADA_SALIO:
        return False
    det = (r or {}).get("error_detail") or {}
    return not (code == "connection" and det.get("phase") in ("connect", "config"))


def _proveedor(did):
    return DC.meta(did).get("provider") or _model_name(did)


def _aviso_nube_linea(S, K, R, w):
    """La línea del aviso (una sola vez por decisor) en la caja del resultado;
    queda pendiente de marcarse hasta que se dibuja."""
    a = (R or {}).get("aviso_nube")
    if not a:
        return []
    S["_aviso_dibujado"] = a["did"]
    txt = _t("decisores.ctx.notice_sent", "Esto mandó contenido de tu cerebro a {p} (sin "
             "secretos, sin archivos privados ni de otros socios). Solo se avisa esta vez.",
             p=_proveedor(a["did"]))
    return [""] + ["%s%s%s" % (K["C"], ln, K["R"]) for ln in wrap(txt, w)]


def _preguntar(S, sync=False):
    ops = _ops(S)
    if len(ops) < 2:
        S["msg"] = _t("decisores.err.options", "Pon al menos 2 opciones, separadas por coma")
        return
    modelo = DC.global_model()
    if modelo == DC.OFF:
        S["res"] = {"ok": False, "error": "off", "decider": "off"}
        return
    preg = S["preg"]
    nivel, agente, tabs = _ctx_level(S), _agent_id(S), _ctx_tabs(S)
    S["pensando"], S["res"], S["detalle"] = modelo, None, False
    import decision_context as C
    # el aviso de la nube se decide AL MANDAR (no al elegir el nivel: ahí puede
    # que todavía no hubiera modelo) y se marca visto solo tras dibujarlo
    aviso = C.needs_cloud_notice(nivel, modelo)

    def run():
        # si no cupo: recorta y reintenta (≤3) — se anota una sola vez
        r, ctx = C.ask(nivel, agente, preg, ops, modelo, tabs, timeout_ms=MANUAL_TIMEOUT_MS)
        S["last_ctx"] = C.ledger_meta(ctx)
        if aviso and ctx.get("text") and _salio(r):
            r["aviso_nube"] = {"did": modelo, "lv": nivel}
        S["res"], S["pensando"] = r, None

    if sync:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()


def _saved(name, value):
    return "✓ " + _t("decisores.msg.saved", "{name}: {value} · guardado", name=name, value=value)


def _accion_detalle(S, key):
    pid = DC.POINT_IDS[S["det"]]
    u = DC.point_conf(pid)
    nom = _point_name(pid)
    if key in ("\x1b", "q", "\r", "\n"):
        S["det"] = None
        S["msg"] = _saved(nom, _level_name(u["level"]))
        return
    d = -1 if key == "left" else 1
    if key == "up":
        S["di"] = (S["di"] - 1) % 3
    elif key == "down":
        S["di"] = (S["di"] + 1) % 3
    elif key in ("left", "right", " "):
        try:
            if S["di"] == 0:
                nv = DC.LEVELS[(DC.LEVELS.index(u["level"]) + d) % len(DC.LEVELS)]
                DC.set_point(pid, level=nv)
                S["msg"] = _saved(nom, _level_name(nv))
            elif S["di"] == 1:
                ops = _detail_models()
                m = ops[((ops.index(u["model"]) if u["model"] in ops else 0) + d) % len(ops)]
                DC.set_point(pid, model=m)
                S["msg"] = _saved(nom, _model_name(m))
            else:
                th = max(DC.THRESHOLD_RANGE[0], min(DC.THRESHOLD_RANGE[1], u["threshold"] + 5 * d))
                DC.set_point(pid, threshold=th)
                S["msg"] = _saved(nom, "%d %%" % th)
        except ValueError as e:
            S["msg"] = str(e)


def _mover_usos(S, key):
    """Rejilla 2×2 por grupo: Tus agentes (0-3) arriba, Workspace (4-7) abajo."""
    g, k = divmod(S["ui"], 4)
    fila, col = divmod(k, 2)
    if key in ("left", "right"):
        S["ui"] = g * 4 + fila * 2 + (1 - col)
    elif key == "up":
        if fila == 1:
            S["ui"] -= 2
        elif g == 1:
            S["ui"] = 2 + col
        else:
            S["zona"] = "modelo"
            cards = _cards()
            gm = DC.global_model()
            S["mi"] = cards.index(gm) if gm in cards else 0
    elif key == "down":
        if fila == 0:
            S["ui"] += 2
        elif g == 0:
            S["ui"] = 4 + col


def _accion_ajustes(S, key):
    if S["zona"] == "modelo":
        cards = _cards()
        m = cards[S["mi"] % len(cards)]
        if key in ("left", "right"):
            S["mi"] = (S["mi"] + (-1 if key == "left" else 1)) % len(cards)
        elif key in (" ", "\r", "\n") and _not_ready(m):
            # se configura UNA vez, en Motores: allá vamos, con ese modelo elegido
            S["request"] = ("modelos", m)
        elif key in (" ", "\r", "\n"):
            ok, est = _model_state(m)
            if not ok:
                S["msg"] = _t("decisores.msg.unavailable", "{m}: {st} — aún no se puede usar",
                              m=_model_name(m), st=est)
                return
            try:
                DC.set_global_model(m)
            except ValueError as e:
                S["msg"] = str(e)
                return
            S["msg"] = _saved(_t("decisores.msg.model", "Modelo"), _model_name(m))
            if m != DC.OFF and not DC.decider_status(m)["ready"]:
                S["msg"] += " · " + _t("decisores.msg.not_ready", "{st}: los usos no preguntarán hasta que esté listo",
                                       st=est)
        elif key == "down":
            S["zona"] = "usos"
            S["ui"] = min(1, S["mi"] // 2)
        return
    pid = DC.POINT_IDS[S["ui"]]
    if key in ("left", "right", "up", "down"):
        _mover_usos(S, key)
    elif key == " ":
        u = DC.point_conf(pid)
        nv = DC.LEVELS[(DC.LEVELS.index(u["level"]) + 1) % len(DC.LEVELS)]
        DC.set_point(pid, level=nv)
        S["msg"] = _saved(_point_name(pid), _level_name(nv))
    elif key in ("\r", "\n"):
        S["det"], S["di"] = S["ui"], 0


def _accion_sesiones(S, key):
    ss = S["selsess"]
    n = len(ss["items"])
    if key in ("\x1b", "q", "\x03"):
        S["selsess"] = None
        return
    if key in ("\r", "\n"):
        S["tabs_sel"][ss["agent_id"]] = set(ss["chosen"])
        S["lvl"][ss["agent_id"]] = "sesiones"
        S["selsess"] = None
        return
    if not n:
        return
    if key in ("up", "down"):
        ss["i"] = (ss["i"] + (-1 if key == "up" else 1)) % n
    elif key == " ":
        slug = ss["items"][ss["i"] % n]["slug"]
        ss["chosen"] ^= {slug}
    elif key == "a":
        todas = {it["slug"] for it in ss["items"]}
        ss["chosen"] = set() if ss["chosen"] == todas else todas


def _accion_fuentes(S, key):
    pv = S["preview"]
    if key in ("\x1b", "v", "q", "\x03"):
        S["preview"] = None
    elif key == "up":
        pv["scroll"] = max(0, pv.get("scroll", 0) - 1)
    elif key == "down":
        pv["scroll"] = pv.get("scroll", 0) + 1


def _abrir_sesiones(S):
    import decision_context as C
    a = _agent_id(S)
    nombre = dict(S.get("agents") or []).get(a, a)
    S["selsess"] = {"agent_id": a, "agent": nombre, "items": C.tab_list(a),
                    "chosen": set(_ctx_tabs(S)), "i": 0}


def _abrir_fuentes(S, sync=False):
    """Arma el contexto de verdad (con la pregunta y opciones de ahora) y
    muestra solo qué fuentes van — en un hilo: abrir `v` nunca congela la
    pantalla (mientras, «calculando…»)."""
    import decision_context as C
    did = _ask_decider()
    pv = {"ctx": None, "did": did, "scroll": 0, "level": _ctx_level(S)}
    S["preview"] = pv
    args = (_ctx_level(S), _agent_id(S), S["preg"], _ops(S), _budget_decider(), _ctx_tabs(S))

    def run():
        try:
            pv["ctx"] = C.build(*args)
        except Exception:
            pv["ctx"] = {"level": args[0], "mode": "vacío", "text": "", "sources": [], "tokens": 0,
                         "budget": 0}
    if sync:
        run()
    else:
        threading.Thread(target=run, daemon=True, name="ctx-preview").start()


def _cambiar_nivel(S, d):
    import decision_context as C
    lvls = C.LEVELS
    nv = lvls[(lvls.index(_ctx_level(S)) + d) % len(lvls)]
    S["lvl"][_agent_id(S)] = nv
    did = _ask_decider()
    if did and C.needs_cloud_notice(nv, did):          # un adelanto; se marca al mandar
        S["msg"] = _t("decisores.ctx.notice_pick", "Ojo: «{lv}» manda contenido de tu cerebro a "
                      "{p} (sin secretos, sin lo privado ni lo de otros socios).",
                      lv=_ctx_label(nv), p=_proveedor(did))


def _tecleando(S):
    """Una tecla en la pregunta u opciones: el medidor espera (debounce) y el
    armado del índice del cerebro cede el paso."""
    S["est_t"] = time.time()
    try:
        import decision_context as C
        C.typing()
    except Exception:
        pass


def _accion(S, key):
    """Devuelve False para salir. Cada cambio se guarda al instante."""
    if S.get("selsess"):
        _accion_sesiones(S, key)
        return True
    if S.get("preview"):
        _accion_fuentes(S, key)
        return True
    tab = TABS[S["tab"]]
    escribiendo = tab == "preguntar" and S["cf"] in (2, 3)
    if (S.get("info") or not escribiendo) and SB.info_key(S, key):
        return True
    S["msg"] = ""
    if key == "\x03":
        return False
    if key in ("tab", "right_tab"):
        S["tab"] = (S["tab"] + (1 if key == "tab" else -1)) % len(TABS)
        S["det"] = None
        if TABS[S["tab"]] == "preguntar":
            S["agents"] = _agents()
            S["ctx"] = {}
            S["est"] = {}
        return True
    if tab == "ajustes" and S.get("det") is not None:
        _accion_detalle(S, key)
        return True
    if escribiendo:
        campo = "preg" if S["cf"] == 2 else "ops"
        if key in ("\x7f", "\x08", "\x15") or (len(key) == 1 and key.isprintable()):
            _tecleando(S)
        if key == "\x1b":
            S["cf"] = 4
        elif key in ("\x7f", "\x08"):
            S[campo] = S[campo][:-1]
        elif key == "\x15":
            S[campo] = ""
        elif key == "up":
            S["cf"] -= 1
        elif key == "down":
            S["cf"] += 1
        elif key in ("\r", "\n"):
            if len(_ops(S)) < 2:
                S["cf"] = 3
                S["msg"] = _t("decisores.err.options", "Pon al menos 2 opciones, separadas por coma")
            elif not S.get("pensando"):
                S["cf"] = 4
                _preguntar(S)
        elif len(key) == 1 and key.isprintable():
            S[campo] = (S[campo] + key)[:200]
        return True
    if key in ("q", "\x1b"):
        return False
    if tab == "ajustes":
        try:
            _accion_ajustes(S, key)
        except ValueError as e:
            S["msg"] = str(e)
        return not S.get("request")              # ir a Motores: sale del bucle y vuelve
    if tab == "preguntar":
        n = len(S.get("agents") or [])
        filas = (0, 1, 2, 3, 4) if n else (0, 2, 3, 4)       # sin agentes no hay contexto
        if S["cf"] not in filas:
            S["cf"] = filas[0]
        if key == "up":
            S["cf"] = filas[(filas.index(S["cf"]) - 1) % len(filas)]
        elif key == "down":
            S["cf"] = filas[(filas.index(S["cf"]) + 1) % len(filas)]
        elif S["cf"] == 0 and key in ("left", "right") and n:
            S["ag"] = (S["ag"] + (-1 if key == "left" else 1)) % n
            S["res"] = None
        elif S["cf"] == 1 and key in ("left", "right"):
            _cambiar_nivel(S, -1 if key == "left" else 1)
        elif key == "v" and n:
            _abrir_fuentes(S)
        elif key == "d" and S.get("res") and not S["res"].get("ok"):
            S["detalle"] = not S.get("detalle")
        elif key in ("\r", "\n") and not S.get("pensando"):
            if S["cf"] == 0:
                S["cf"] = 1
            elif S["cf"] == 1:
                if _ctx_level(S) == "sesiones":
                    _abrir_sesiones(S)
                else:
                    S["cf"] = 2
            else:
                _preguntar(S)
        return True
    H = DC.history(200, ok_only=False)
    if key == "up":
        S["hi"] = max(0, S["hi"] - 1)
    elif key == "down":
        S["hi"] = min(max(0, len(H) - 1), S["hi"] + 1)
    elif key in ("s", "y", "n") and H:
        e = H[min(S["hi"], len(H) - 1)]
        if not e.get("ok"):
            S["msg"] = _t("decisores.msg.grade_fail", "Esa no respondió: no hay nada que calificar")
        elif DC.mark(e["id"], key != "n"):
            S["msg"] = "✓ " + (_t("decisores.msg.right", "Gracias: acertó") if key != "n"
                               else _t("decisores.msg.wrong", "Gracias: falló"))
    return True


import responsive_ui as _responsive  # noqa: E402
render = _responsive.renderer(render, 'DECISORES')
_accion = _responsive.action(_accion)


# ── drivers ──────────────────────────────────────────────────────────────────
def _size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 112, 44


def _ocupado(S):
    """¿Hay algo en camino? (el bucle redibuja seguido para mostrarlo)."""
    pv = S.get("preview")
    return bool(S.get("pensando") or S.get("est_busy") or (pv and pv.get("ctx") is None)
                or _est_pending(S))


def _draw(tout, S, first=False):
    w, h = _size()
    try:
        _responsive.paint(tout, render(S, w, h), first=first)
    except Exception:
        return
    _tras_dibujar(S)


def _tras_dibujar(S):
    """El aviso de la nube se marca visto SOLO después de dibujarlo."""
    pend = S.pop("_aviso_dibujado", None)
    if pend:
        try:
            import decision_context as C
            C.mark_cloud_notice(pend)
        except Exception:
            pass


def _run_unix(S):
    import termios
    import tty
    fd = os.open("/dev/tty", os.O_RDWR)
    tout = open("/dev/tty", "w")
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h\033[?25l")
        _draw(tout, S, first=True)
        teclas = SB.KeyReader(fd)
        while True:
            key = teclas.get(0.15 if _ocupado(S) else 0.5)
            if key is None:
                _draw(tout, S)
                continue
            if not key:                                # secuencia que no aplica
                continue
            if not _accion(S, key):
                break
            if not teclas.pending():                   # una ráfaga (pegar) = un dibujo
                _draw(tout, S)
    except KeyboardInterrupt:                          # una señal de fuera: salir limpio
        pass
    finally:
        try:
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.close(fd)
        except Exception:
            pass
    return 0


def _run_windows(S):
    tout = sys.stdout
    tout.write("\033[?1049h\033[?25l")
    _draw(tout, S, first=True)
    # la consola de verdad (ReadConsoleInputW): ¿ ¡ « » € por SSH, Shift-Tab
    teclas = SB.WinKeyReader()
    try:
        while True:
            key = teclas.get(0.15 if _ocupado(S) else 0.5)
            if key is None:
                _draw(tout, S)
                continue
            if key and not _accion(S, key):
                break
            if not teclas.pending():                   # una ráfaga (pegar) = un dibujo
                _draw(tout, S)
    except KeyboardInterrupt:                          # Ctrl+C en Windows es una señal: salir
        pass
    finally:
        try:
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
        except Exception:
            pass
    return 0


def _texto():
    """Sin terminal interactiva: el estado en texto plano."""
    print("%s: %s" % (_t("decisores.txt.model", "modelo"), _model_name(DC.global_model())))
    for pid in DC.POINT_IDS:
        c = DC.point_conf(pid)
        print("  %-22s %-8s %s" % (_point_name(pid), _level_name(c["level"]), _model_name(c["model"])))
    return 0


def open_motores(S, did):
    """Motores → Modelos de decisión con ese modelo elegido (como Agentes abre
    «Agregar agente»): al volver, Decisores refleja lo nuevo."""
    antes = DC.global_model()
    try:
        import modelos_tui as MT
        MT.run.__wrapped__(did=did)            # sin volver a aplicar el tema: ya está
    except Exception as e:
        S["msg"] = "Motores: %s" % type(e).__name__
        return
    S["est"] = {}                              # el modelo pudo cambiar (límite, llave)
    ahora = DC.global_model()
    if ahora != antes and ahora != DC.OFF:
        S["msg"] = "✓ " + _t("decisores.msg.activated", "{m} quedó como modelo de Decisores",
                             m=_model_name(ahora))
    elif not _not_ready(did):
        S["msg"] = "✓ " + _t("decisores.msg.ready_back", "{m} está listo · Enter para usarlo",
                             m=_model_name(did))


def _interactivo():
    """¿Consola de verdad? `isatty()` no basta en Windows: NUL es un
    dispositivo de caracteres (isatty True) y la pantalla esperaba teclas
    para siempre. _console es la regla compartida de Workspace."""
    try:
        import _console
        return _console.interactive()
    except Exception:
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            return False


@_theme_screen
def run():
    try:
        return _run(initial())
    finally:
        _soltar_cache()


def _soltar_cache():
    """Al salir de la sección: lo que Decisores tenía en memoria (el índice de
    los cerebros) se suelta — el hub vive mucho y no debe cargarlo."""
    try:
        import decision_context as C
        C.free()
    except Exception:
        pass


def _run(S):
    if not _interactivo():
        return _texto()
    try:
        while True:
            S["request"] = None
            rc = _run_windows(S) if os.name == "nt" else _run_unix(S)
            req = S.get("request")
            if not req:
                return rc
            open_motores(S, req[1])
    except KeyboardInterrupt:                          # Ctrl+C: salir (como «q»)
        try:
            sys.stdout.write("\033[?25h\033[?1049l")
            sys.stdout.flush()
        except Exception:
            pass
        return 0
    except Exception as e:
        try:
            sys.stdout.write("\033[?25h\033[?1049l")
        except Exception:
            pass
        print("decisores: %s" % e)
        return _texto()


if __name__ == "__main__":
    sys.exit(run())
