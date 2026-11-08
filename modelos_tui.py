#!/usr/bin/env python3
"""WORKSPACE · modelos_tui — Motores → MODELOS DE DECISIÓN: dónde se CONSIGUEN los decisores.

Los motores trabajan · los decisores eligen. MISMO diseño y manejo que la
pantalla de motores de agentes (engines_tui): a la izquierda la lista de
modelos con su estado; a la derecha las opciones del elegido, que se aplican
AHÍ MISMO (sin pantallas de detalle):

  conectar llave    campo ENMASCARADO en la columna → bóveda de Workspace
                    (es lo ÚNICO que hay que configurar: Jev habla con su API
                    con la stdlib, no hay SDK que instalar)
  desconectar       con confirmación
  probar            una llamada real chiquita: latencia, tokens y costo
  contexto          el límite MEDIDO del modelo (META `context_tokens`);
                    Enter elige uno menor (`decisions.model_limits`: más
                    barato y rápido; nunca más de lo que el modelo admite)
  precio            aproximado (del META)

La lista sale de deciders/ y su META (los internos no se muestran). El
primer modelo que queda listo, si no hay uno activo, se activa solo en
Decisores (los usos siguen apagados).
DÓNDE actúa cada uno se elige en la sección Decisores. Stdlib.
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
import decisores_tui as DT                                      # noqa: E402
import engines_tui as ET                                        # noqa: E402
import hublayout as HL                                          # noqa: E402
import section_box as SB                                        # noqa: E402

_t = DT._t
#: Las columnas de engines_tui: las dos mitades de Motores se ven iguales.
LIST_W = ET.LIST_W
DETAIL_W = ET.DETAIL_W
#: Límites de contexto que se ofrecen con Enter en «contexto» (tokens).
#: Límites menores que se pueden elegir (más el del modelo, que es el tope).
LIMITS = (8000, 16000, 24000)
#: Prueba: una pregunta mínima (pocos tokens) con respuesta obvia.
PROBE_Q = "¿Cuál de estas palabras es un color?"
PROBE_OPTS = ["rojo", "martes"]
PROBE_TIMEOUT_MS = 10000
#: Filas que son ACCIÓN (›), como engines_tui._ACCIONES.
_ACCIONES = ("connect", "disconnect")


# ── datos (desde deciders/ y su META) ────────────────────────────────────────
def models():
    """Los decisores que ve el socio (los de la nube primero). Los internos
    (META `internal`) nunca aparecen."""
    return sorted(DC.offered(), key=lambda d: (bool(DC.meta(d).get("local", True)), d))


def selectable(did):
    return did in DC.deciders() and not DC.is_internal(did)


def name(did):
    return DC.meta(did).get("label") or str(did).capitalize()


def ready(did):
    return selectable(did) and bool(DC.decider_status(did).get("ready"))


def state(did):
    """(texto, color) del estado en la lista — como engines_tui.status_of."""
    if not selectable(did):
        return _t("modelos.st.missing", "no instalado"), "DIM"
    if DC.meta(did).get("key_env") and not DC.key_source(did):
        return _t("decisores.st.no_key", "sin llave"), "ERR"
    return _t("decisores.st.ready", "listo"), "OK"


def ctx_limit(did):
    import decision_context as C
    return C.limit(did)


def set_limit(did, n):
    import settings
    cur = dict(settings.get("decisions.model_limits") or {})
    base = int(DC.meta(did).get("context_tokens") or 0)
    if int(n) == base:
        cur.pop(did, None)
    else:
        cur[did] = int(n)
    settings.set("decisions.model_limits", cur)
    return int(n)


def _base_limit(did):
    try:
        return int(DC.meta(did).get("context_tokens") or 0)
    except (TypeError, ValueError):
        return 0


def _limits(did):
    """Los límites que Enter recorre: los menores de LIMITS y el del modelo."""
    base = _base_limit(did)
    if not base:
        return LIMITS
    return tuple(sorted({x for x in LIMITS if x < base} | {base}))


def _next_limit(did):
    lim = ctx_limit(did)
    opciones = _limits(did)
    mayores = [x for x in opciones if x > lim]
    return mayores[0] if mayores else opciones[0]


def _ctx_value(did):
    """«32 768 tokens» (el del modelo) o «16 000 de 32 768 tokens» (uno menor)."""
    import decision_context as C
    lim, base = ctx_limit(did), _base_limit(did)
    if not C.declared_limit(did):      # no se inventa: el 8k de adentro no es suyo
        return _t("modelos.info.ctx_none", "sin límite declarado")
    if base and lim < base:
        return _t("modelos.info.ctx_of", "{n} de {b} tokens", n=C.fmt_exact(lim), b=C.fmt_exact(base))
    return _t("modelos.info.ctx_n", "{n} tokens", n=C.fmt_exact(lim))


def _approx(did):
    return (" · " + _t("modelos.info.approx", "aprox.")) if DC.meta(did).get("approx_price") else ""


def _price_rows(did):
    """Las filas de precio (aproximado, del META): entrada y salida."""
    m = DC.meta(did)
    if m.get("local", True):
        return [("price", _t("modelos.info.price", "precio"), _t("modelos.info.free", "sin costo"))]
    if m.get("price_in_per_m") is None:
        return [("price", _t("modelos.info.price", "precio"), _t("modelos.info.noprice", "precio n/d"))]
    out = [("price", _t("modelos.info.in", "entrada"),
            _t("modelos.info.per_m", "${p} por millón", p=m["price_in_per_m"]) + _approx(did))]
    if m.get("price_out_per_m") is not None:
        out.append(("price", _t("modelos.info.out", "salida"),
                    _t("modelos.info.out_free", "gratis") if m["price_out_per_m"] == 0 else
                    _t("modelos.info.per_m", "${p} por millón", p=m["price_out_per_m"])))
    return out


def options(S, did):
    """[(clave, etiqueta, valor)] del modelo — como engines_tui.options:
    valor = estado; "" = acción (›)."""
    out = []
    if DC.meta(did).get("key_env"):
        src = DC.key_source(did)
        if src == "store":
            out.append(("key", _t("modelos.k.key", "llave"), _t("modelos.key.store", "conectada")))
            out.append(("disconnect", _t("modelos.o.disconnect", "desconectar llave"), ""))
        elif src == "env":
            out.append(("key", _t("modelos.k.key", "llave"), _t("modelos.key.env", "del entorno")))
        else:
            out.append(("connect", _t("modelos.o.connect", "conectar llave"), ""))
    out.append(("probe", _t("modelos.o.probe", "probar"),
                "" if ready(did) else _t("modelos.probe.needs", "necesita la llave")))
    out.append(("ctx", _t("modelos.info.ctx", "contexto"), _ctx_value(did)))
    return out + _price_rows(did)


# ── estado ───────────────────────────────────────────────────────────────────
def initial(did=None):
    """`did` = abrir con ese modelo elegido y sus opciones enfocadas (así
    llega Decisores cuando a un modelo le falta algo)."""
    ids = models()
    sel = [i for i, d in enumerate(ids) if selectable(d)]
    i = ids.index(did) if did in ids and selectable(did) else (sel[0] if sel else 0)
    S = {"models": ids, "model": i, "focus": "detail" if did and selectable(did) else "list",
         "opt": 0, "msg": "", "confirm": None, "llave": None, "probe": None}
    if S["focus"] == "detail":
        keys = [o[0] for o in options(S, ids[i])]
        if "connect" in keys:
            S["opt"] = keys.index("connect")
    return S


def selected(S):
    """El modelo elegido, o None si deciders/ no trae ninguno para el socio."""
    ids = S["models"]
    return ids[S["model"] % len(ids)] if ids else None


def busy(S):
    return bool((S.get("probe") or {}).get("running"))


def _auto_activate(S, did):
    """El PRIMER modelo que queda listo, si en Decisores no hay uno activo,
    se activa solo (los usos siguen apagados: se eligen en Decisores)."""
    try:
        if ready(did) and DC.global_model() == DC.OFF:
            DC.set_global_model(did)
            S["msg"] = "✓ " + _t("modelos.msg.activated", "{m} listo y activo en Decisores · los usos "
                                 "siguen apagados: elígelos ahí", m=name(did))
            return True
    except Exception:
        pass
    return False


# ── dibujo (el de engines_tui) ───────────────────────────────────────────────
def word():
    return HL.section_word("motores")


def _K():
    return SB.K()


def _rows(S, K, did, iw):
    """Las opciones del elegido como las filas de engines_tui._detalle."""
    activo = S.get("focus") == "detail"
    ops = options(S, did)
    S["opt"] = max(0, min(S.get("opt", 0), len(ops) - 1))
    estados = [o for o in ops if o[0] not in _ACCIONES]
    lab_w = (max(HL.vis(o[1]) for o in estados) + 2) if estados else 0
    out, fila = [], 0
    for n, (key, lab, val) in enumerate(ops):
        on = activo and n == S["opt"]
        if on:
            fila = len(out)
        cur = ("%s%s %s" % (K["C"] + K["BO"], K["PTR"], K["R"])) if on else "  "
        tinta = (K["WH"] + K["BO"]) if on else K["GREY"]
        if key in _ACCIONES or (key == "probe" and not val):
            flecha = "%s›%s" % ((K["C"] + K["BO"]) if on else K["DK"], K["R"])
            out.append(HL.clip("%s%s%s%s%s%s" % (cur, tinta, lab, K["R"],
                                                 " " * max(1, iw - 3 - HL.vis(lab)), flecha), iw))
            continue
        vcol = {"key": K["OK"], "probe": K["DK"]}.get(key, K["DIM"])
        out.append(HL.clip("%s%s%s%s%s%s%s" % (cur, tinta, HL.pad(lab, lab_w), K["R"], vcol, val,
                                               K["R"]), iw))
    return out, fila


def _area(S, K, did, iw):
    """Debajo de las filas, en la MISMA columna: la confirmación, la llave
    enmascarada o el resultado de probar."""
    c = S.get("confirm")
    if c and c.get("did") == did:
        return _confirm_lines(S, K, iw, c)
    ll = S.get("llave")
    if ll and ll.get("did") == did:
        return _key_lines(K, iw, ll)
    out = []
    pr = S.get("probe")
    if pr and pr.get("did") == did:
        out += [""] + _probe_lines(K, iw, pr)
    if not out and S.get("focus") == "detail":
        ops = options(S, did)
        key = ops[min(S.get("opt", 0), len(ops) - 1)][0]
        txt = {"connect": _t("modelos.area.key", "Tu llave se guarda en esta computadora (bóveda de "
                             "Workspace): nunca se muestra ni llega a un motor."),
               "probe": _t("modelos.area.probe", "Una pregunta mínima de verdad: si responde, cuánto "
                           "tarda y cuántos tokens usa."),
               "ctx": _t("modelos.area.ctx", "Lo más que admite el modelo, medido con llamadas "
                         "reales. Enter elige un límite menor: más barato y más rápido."),
               "price": _t("modelos.area.price", "Por millón de tokens. Aproximado, de agregadores "
                           "de terceros.")}.get(key)
        if txt:
            out = [""] + ["%s%s%s" % (K["DIM"], ln, K["R"]) for ln in DT.wrap(txt, iw)[:3]]
    return out


def _confirm_lines(S, K, iw, c):
    did = c["did"]
    L = [""] + ["%s%s%s" % (K["C"] + K["BO"], ln, K["R"]) for ln in DT.wrap(
        _t("modelos.c.disconnect", "¿Desconectar {m}? Se borra su llave de esta computadora.",
           m=name(did)), iw)]
    si = _t("modelos.c.yes_disconnect", "Desconectar")
    no = _t("modelos.c.no", "No gracias")
    b = c.get("btn", 1)
    bw = max(10, min(18, (iw - 3) // 2))
    L += DT.hjoin([DT.boton(K, si, bw, b == 0, False), DT.boton(K, no, bw, b == 1, False)], gap=3)
    return [HL.clip(x, iw) for x in L]


def _key_lines(K, iw, ll):
    did = ll["did"]
    buf = ll["buf"]
    L = [""] + ["%s%s%s" % (K["GREY"], ln, K["R"]) for ln in DT.wrap(
        _t("modelos.key.paste", "Pega tu llave de {p}:", p=DC.meta(did).get("provider") or name(did)), iw)]
    puntos = ("•" * min(len(buf), max(1, iw - 12))) if buf else ""
    txt = ("%s%s%s %s(%d)%s" % (K["WH"] + K["BO"], puntos, K["R"], K["DK"], len(buf), K["R"]) if buf
           else "%s%s%s" % (K["DK"], _t("decisores.key.ph", "pega aquí tu llave"), K["R"]))
    L += DT.caja(K, [txt + "%s▏%s" % (K["C"] + K["BO"], K["R"])], iw, K["C"] + K["BO"], heavy=True)
    L += ["%s%s%s" % (K["DK"], ln, K["R"]) for ln in DT.wrap(_t(
        "modelos.key.where", "se guarda en esta computadora (bóveda de Workspace) · nunca se muestra "
        "ni llega a un motor"), iw)[:3]]
    return [HL.clip(x, iw) for x in L]


def _probe_lines(K, iw, pr):
    if pr.get("running"):
        sp = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.time() * 10) % 10]
        return ["%s%s %s%s" % (K["C"], sp, _t("modelos.probe.running", "probando…"), K["R"])]
    r = pr.get("res") or {}
    if r.get("ok"):
        import decision_context as C
        tk = r.get("tokens") or {}
        txt = _t("modelos.probe.ok", "✓ respondió «{c}» en {ms} ms · tokens: {i} de entrada, {o} de salida",
                 c=r.get("choice"), ms=int(r.get("ms") or 0), i=tk.get("in", "—"), o=tk.get("out", "—"))
        if r.get("cost_usd") is not None:
            txt += " · " + _t("modelos.probe.cost", "costo {c}", c=C.fmt_cost(r["cost_usd"]))
        return ["%s%s%s" % (K["OK"], ln, K["R"]) for ln in DT.wrap(txt, iw)]
    return ["%s%s%s" % (K["ERR"], ln, K["R"]) for ln in DT.wrap(
        "✗ " + DT._error_txt(r.get("error"), pr.get("did"), timeout_ms=PROBE_TIMEOUT_MS,
                             where="probe", detail=r.get("error_detail"),
                             elapsed_ms=r.get("ms")), iw)[:3]]


def _detalle(S, K, did, iw):
    filas, fila = _rows(S, K, did, iw)
    area = _area(S, K, did, iw)
    if S.get("llave") or S.get("confirm"):
        fila = len(filas) + max(0, len(area) - 2)
    return filas + area, fila


def _items(S):
    out = []
    for d in S["models"]:
        txt, col = state(d)
        out.append((name(d), txt, col) + (() if selectable(d) else ("DK",)))
    return out


def _cuerpo(S, K, iw):
    """Lista de modelos │ opciones del elegido — engines_tui._cuerpo."""
    did = selected(S)
    if did is None:                           # deciders/ sin modelos: lo dice y ya
        S["_cur"] = 0
        return ["", DT.center("%s%s%s" % (K["DIM"], _t("modelos.empty", "No hay modelos de decisión "
                                                        "instalados en este Workspace"), K["R"]), iw)]
    der = S.get("focus") == "detail" or bool(S.get("confirm")) or bool(S.get("llave"))
    items = _items(S)
    sel = S["model"] % len(S["models"])
    tail = "◂" if der else "▸"
    if iw < LIST_W + SB.SPLIT_GAP + 26:
        arriba = SB.pick_list(K, items, sel, iw, min(len(items), 8), sel_tail=tail)
        opciones, fila = _detalle(S, K, did, iw)
        S["_cur"] = len(arriba) + 2 + fila if der else min(sel, len(arriba) - 1)
        etiqueta = "%s · %s" % (name(did), ET._t("motores.opts", "opciones", "options"))
        return SB.stack(K, arriba, opciones, iw, label=etiqueta, active=der)
    opciones, fila = _detalle(S, K, did, iw - LIST_W - SB.SPLIT_GAP)
    izq = SB.pick_list(K, items, sel, LIST_W, max(len(opciones), min(len(items), 8)), sel_tail=tail)
    S["_cur"] = fila if der else min(sel, len(izq) - 1)
    return SB.split(K, izq, opciones, iw, LIST_W)


# ── la llave (campo enmascarado en la columna de opciones) ───────────────────
def key_act(S, key):
    """Escribiendo la llave: todo lo que se teclea es de la llave (también
    i, ? y q). Enter la guarda en la bóveda; Esc cancela. Nada se imprime."""
    ll = S["llave"]
    if key in ("\x1b", "\x03"):
        S["llave"] = None
        S["msg"] = _t("decisores.msg.key_cancel", "Conexión cancelada · no se guardó nada")
        return
    if key in ("\r", "\n"):
        r = DC.connect(ll["did"], ll["buf"])
        if not r.get("ok"):
            S["msg"] = (_t("decisores.msg.key_invalid", "Esa llave no parece válida (8 o más "
                           "caracteres, sin espacios)") if r.get("error") == "invalid_key"
                        else _t("decisores.msg.key_store", "No pude guardarla en la bóveda de Workspace"))
            return
        did = ll["did"]
        S["llave"] = None
        S["msg"] = "✓ " + _t("modelos.msg.key_ok", "{m} conectado · la llave quedó guardada en esta "
                             "computadora", m=name(did))
        _auto_activate(S, did)
        keys = [o[0] for o in options(S, did)]
        S["opt"] = keys.index("probe")
        return
    if key in ("\x7f", "\x08"):
        ll["buf"] = ll["buf"][:-1]
    elif key == "\x15":
        ll["buf"] = ""
    elif len(key) == 1 and key.isprintable():
        ll["buf"] = (ll["buf"] + key)[:512]


# ── probar (una llamada real chiquita) ───────────────────────────────────────
def start_probe(S, did):
    pr = {"did": did, "running": True, "res": None}
    S["probe"] = pr

    def run():
        pr["res"] = DC.consult(DC.MANUAL, "choice", PROBE_Q, PROBE_OPTS, "", decider=did,
                               timeout_ms=PROBE_TIMEOUT_MS, level="ask", log=False)
        pr["running"] = False
    th = threading.Thread(target=run, daemon=True, name="decider-probe")
    th.start()
    return th


# ── ayuda (i / ?) ────────────────────────────────────────────────────────────
def _info_txt():
    return (_t("modelos.info.list.p", "Los motores trabajan (programan, escriben, conversan); los "
               "modelos de decisión eligen entre opciones fijas y dicen qué tan seguros están. Aquí "
               "los dejas listos una sola vez: conectas tu llave y lo pruebas."),
            [_t("modelos.info.detail.l2", "Llave — enmascarada, en la bóveda"),
             _t("modelos.info.detail.l3", "Probar — latencia, tokens y costo reales"),
             _t("modelos.info.detail.l4", "Dónde decide: en la sección Decisores")])


def _flujo_que():
    return [(_t("modelos.info.f2", "lo conectas"), _t("modelos.info.f2n", "tu llave")),
            (_t("modelos.info.f3", "lo pruebas"), _t("modelos.info.f3n", "una llamada real")),
            (_t("modelos.info.f4", "decide"), _t("modelos.info.f4n", "en Decisores"))]


def _flujo_como():
    return [(_t("modelos.info.c1", "lee deciders/"), _t("modelos.info.c1n", "cada uno con su META")),
            (_t("modelos.info.c2", "su API, directo"), _t("modelos.info.c2n", "sin paquetes extra")),
            (_t("modelos.info.c3", "llave a la bóveda"), _t("modelos.info.c3n", "0600, ningún motor")),
            (_t("modelos.info.c4", "mismo contrato"), _t("modelos.info.c4n", "decide() para todos"))]


def _como_p():
    return _t("modelos.info.how.p", "Cada modelo es un archivo en deciders/ con su META (nombre, "
              "llave, límite, precio): esta pantalla se arma sola con eso, con el mismo diseño que "
              "la de motores de agentes. Jev habla con la API de TypeSafe con lo que ya trae "
              "Python, sin paquetes extra. El primero que queda listo se activa en Decisores, "
              "con los usos apagados.")


def info_blocks():
    texto, lista = _info_txt()
    return [("flow", _flujo_que()), ("gap",), ("p", texto), ("list", lista), ("gap",),
            ("h", _t("decisores.info.how", "cómo lo hicimos")), ("flow", _flujo_como()),
            ("p", _como_p()), ("dim", DT._como_dim())]


def info_body(K, iw):
    texto, lista = _info_txt()
    L = [DT.titulo(K, _t("decisores.info.what", "qué es"), iw, 0), ""] + DT.flujo(K, _flujo_que(), iw, 0) + [""]
    lw = (iw - 3) // 2
    izq = ["%s%s%s" % (K["WH"], ln, K["R"]) for ln in DT.wrap(texto, lw)]
    der = []
    for x in lista:
        for j, ln in enumerate(DT.wrap(x, lw - 2)):
            der.append("%s%s%s %s%s%s" % (K["C"], "·" if j == 0 else " ", K["R"], K["GREY"], ln, K["R"]))
    for i in range(max(len(izq), len(der))):
        a = izq[i] if i < len(izq) else ""
        b = der[i] if i < len(der) else ""
        L.append(HL.pad(a, lw) + " %s│%s " % (K["DK"], K["R"]) + b)
    L += ["", DT.titulo(K, _t("decisores.info.how", "cómo lo hicimos"), iw, 3), ""] \
        + DT.flujo(K, _flujo_como(), iw, 2) + [""]
    L += ["%s%s%s" % (K["GREY"], ln, K["R"]) for ln in DT.wrap(_como_p(), iw)]
    L += ["%s%s%s" % (K["DK"], ln, K["R"]) for ln in DT.wrap(DT._como_dim(), iw)]
    return [HL.clip(x, iw) for x in L]


def info_render(S, K, w, h, titulo_caja):
    bw = max(60, min(96, w - 10))
    if bw < 70:
        return SB.info_frame(K, w, h, word(), titulo_caja, info_blocks(), state=S["info"], box_w=60)
    st = S["info"] if isinstance(S["info"], dict) else {}
    out = SB.frame(K, w, h, word(), titulo_caja, lambda iw: info_body(K, iw),
                   ((u"↑↓", _t("decisores.k.move_info", "mover")), ("Esc", _t("decisores.k.close", "cerrar"))),
                   box_w=bw, scroll=st.get("scroll", 0))
    st["scroll"] = max(0, min(st.get("scroll", 0), SB.frame.last_max_scroll))
    return out


# ── marco (las fichas de engines_tui) ────────────────────────────────────────
def _chips(S):
    if S.get("llave") is not None:
        return (("Enter", _t("decisores.k.save", "guardar")), ("Ctrl+U", _t("decisores.k.clear", "borrar")),
                ("Esc", ET._t("motores.k.cancel", "cancela", "cancel")))
    if S.get("confirm"):
        return ((u"←→", ET._t("motores.k.pick", "elige", "pick")),
                ("Enter", ET._t("motores.k.confirm", "confirma", "confirm")),
                ("Esc", _t("modelos.k.no", "no gracias")))
    if S.get("focus") == "detail":
        return ((u"↑↓", ET._t("motores.k.option", "opción", "option")),
                ("Enter", ET._t("motores.k.do", "aplica", "apply")),
                (u"←", ET._t("motores.k.to_list", "a la lista", "to the list")),
                ("i", ET._t("motores.k.info", "cómo funciona", "how it works")))
    return ((u"↑↓", ET._t("motores.k.pick", "elige", "pick")),
            (u"→", ET._t("motores.k.to_opts", "sus opciones", "its options")),
            ("i", ET._t("motores.k.info", "cómo funciona", "how it works")),
            ("q", ET._t("motores.k.back", "vuelve", "back")))


def render(S, w, h):
    K = _K()
    titulo = _t("modelos.box", "MODELOS DE DECISIÓN")
    if S.get("info"):
        return info_render(S, K, w, h, "%s · %s" % (_t("decisores.info.title", "AYUDA"), titulo))
    return SB.frame(K, w, h, word(), titulo, lambda iw: _cuerpo(S, K, iw), _chips(S),
                    msg=S.get("msg", ""), cursor_line=lambda: S.get("_cur", 0),
                    box_w=LIST_W + SB.SPLIT_GAP + DETAIL_W,
                    stable_rows=max(min(len(S["models"]), 8), 10))


# ── acciones (las de engines_tui.act) ────────────────────────────────────────
def _confirm_act(S, key):
    c = S["confirm"]
    if key in ("left", "right", "tab"):
        c["btn"] = 1 - c.get("btn", 1)
        return
    if key in ("\r", "\n", " ") and c.get("btn", 1) == 0:
        S["confirm"] = None
        r = DC.disconnect(c["did"])
        S["msg"] = ("✓ " + _t("decisores.msg.key_removed", "{m} desconectado: la llave se borró de "
                              "esta computadora", m=name(c["did"]))) if r.get("ok") else \
            _t("decisores.msg.key_store", "No pude guardarla en la bóveda de Workspace")
        return
    S["confirm"] = None                     # No gracias / Esc / cualquier otra tecla
    S["msg"] = _t("modelos.msg.no_disconnect", "La llave sigue conectada")


def _aplica(S):
    """Enter sobre la opción elegida — ahí mismo."""
    did = selected(S)
    ops = options(S, did)
    key = ops[min(S.get("opt", 0), len(ops) - 1)][0]
    if busy(S):
        S["msg"] = _t("modelos.msg.busy", "Espera a que termine…")
    elif key == "connect":
        S["llave"] = {"did": did, "buf": ""}
    elif key == "disconnect":
        S["confirm"] = {"kind": "disconnect", "did": did, "btn": 1}
    elif key == "key" and DC.key_source(did) == "env":
        S["msg"] = _t("decisores.msg.key_env", "La llave viene del entorno del sistema ({var}): "
                      "quítala ahí", var=DC.key_env(did))
    elif key == "probe":
        if not ready(did):
            S["msg"] = _t("modelos.msg.probe_needs", "Para probarlo hace falta la llave")
        else:
            start_probe(S, did)
    elif key == "ctx":
        import decision_context as C
        n = set_limit(did, _next_limit(did))
        S["msg"] = _t("modelos.msg.limit", "Límite de contexto de {m}: {n} tokens · guardado",
                      m=name(did), n=C.fmt_exact(n))
    return True


def _move(S, d):
    """↑↓ en la lista: solo entre los modelos que se pueden elegir."""
    ids = S["models"]
    sel = [i for i, x in enumerate(ids) if selectable(x)]
    if not sel:
        return
    cur = S["model"] if S["model"] in sel else sel[0]
    S["model"] = sel[(sel.index(cur) + d) % len(sel)]
    S["opt"] = 0


def act(S, key):
    """True = sigue · False = sale (Esc/q desde la lista)."""
    if S.get("llave") is not None:
        key_act(S, key)
        return True
    if S.get("confirm"):
        _confirm_act(S, key)
        return True
    if SB.info_key(S, key):
        return True
    if key == "\x03":
        return False
    S["msg"] = "" if not busy(S) else S.get("msg", "")
    if selected(S) is None:
        return key not in ("q", "Q", "\x1b")
    if S.get("focus") == "detail":
        ops = options(S, selected(S))
        if key in ("\x1b", "left", "q", "Q"):
            S["focus"] = "list"
        elif key in ("up", "down"):
            S["opt"] = (S.get("opt", 0) + (-1 if key == "up" else 1)) % len(ops)
        elif key in ("\r", "\n", " "):
            return _aplica(S)
        return True
    if key in ("q", "Q", "\x1b"):
        return False
    if key in ("up", "down", "tab"):
        _move(S, -1 if key == "up" else 1)
    elif key in ("\r", "\n", "right", " "):
        if selectable(selected(S)):
            S["focus"] = "detail"
            S["opt"] = 0
    return True


import responsive_ui as _responsive  # noqa: E402
render = _responsive.renderer(render, 'MODELOS')
act = _responsive.action(act)


# ── drivers (genéricos: también los usa la puerta de Motores) ───────────────
def _size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 112, 44


def loop(S, render_fn, act_fn, busy_fn=busy):
    """El bucle de teclado de una pantalla (Unix y Windows)."""
    if os.name == "nt":
        return _loop_windows(S, render_fn, act_fn, busy_fn)
    return _loop_unix(S, render_fn, act_fn, busy_fn)


def _draw(tout, S, render_fn, first=False):
    w, h = _size()
    try:
        _responsive.paint(tout, render_fn(S, w, h), first=first)
    except Exception:
        pass


def _loop_unix(S, render_fn, act_fn, busy_fn):
    import termios
    import tty
    fd = os.open("/dev/tty", os.O_RDWR)
    tout = open("/dev/tty", "w")
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h\033[?25l")
        _draw(tout, S, render_fn, first=True)
        teclas = SB.KeyReader(fd)
        while True:
            key = teclas.get(0.15 if busy_fn(S) else 0.5)
            if key is None:
                _draw(tout, S, render_fn)
                continue
            if not key:                                # secuencia que no aplica
                continue
            if not act_fn(S, key):
                break
            if not teclas.pending():                   # una ráfaga (pegar) = un dibujo
                _draw(tout, S, render_fn)
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


def _loop_windows(S, render_fn, act_fn, busy_fn):
    tout = sys.stdout
    tout.write("\033[?1049h\033[?25l")
    _draw(tout, S, render_fn, first=True)
    # la consola de verdad (ReadConsoleInputW): ¿ ¡ « » € por SSH, Shift-Tab
    teclas = SB.WinKeyReader()
    try:
        while True:
            key = teclas.get(0.15 if busy_fn(S) else 0.5)
            if key is None:
                _draw(tout, S, render_fn)
                continue
            if key and not act_fn(S, key):
                break
            if not teclas.pending():                   # una ráfaga (pegar) = un dibujo
                _draw(tout, S, render_fn)
    except KeyboardInterrupt:                          # Ctrl+C en Windows es una señal: salir
        pass
    finally:
        try:
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
        except Exception:
            pass
    return 0


def _interactive():
    """¿Consola de verdad? (también la usa Motores). `isatty()` no basta en
    Windows: NUL pasa por terminal y la pantalla esperaba teclas para
    siempre; _console es la regla compartida de Workspace."""
    try:
        import _console
        return _console.interactive()
    except Exception:
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            return False


@_theme_screen
def run(did=None):
    S = initial(did=did)
    if not _interactive():
        print("\n".join(render(S, 112, 44)))
        return 0
    try:
        return loop(S, render, act)
    except KeyboardInterrupt:                          # Ctrl+C: salir (como «q»)
        return 0
    except Exception as e:
        try:
            sys.stdout.write("\033[?25h\033[?1049l")
        except Exception:
            pass
        print("modelos: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(run())
