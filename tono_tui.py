#!/usr/bin/env python3
"""WORKSPACE · tono_tui — pantalla propia del TONO de los agentes.

REDISEÑO 2026-10-14 (concepto Omarchy, pedido del dueño): lo esencial en UNA
caja centrada y vertical (section_box) —para quién, los diales y qué hace el
nivel del dial elegido— y lo didáctico detrás de `i`: el mapa de cómo viaja
el mensaje invisible, el texto EXACTO que se le envía hoy, la escalera de 5
niveles del dial elegido, las reglas (neutro = no se envía nada; el agente
pisa lo GLOBAL; solo estilo, jamás identidad/reglas) y las teclas de más.

Se abre con `workspace tono` o desde el MENÚ del hub («Tono»).

Teclas:  ↑↓ dial · ←→ nivel · Tab/⇧Tab agente · i cómo funciona · q volver
         (en `i`: 1-5 directo · p modo · r neutro)   cada cambio se GUARDA ya

El modelo (diales, textos, almacén) vive en `personalidad.py`; esto es solo
la superficie. Los dos drivers de teclado: termios+select en Unix, msvcrt en
Windows. Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import os
import sys
import time
from theme import screen as _theme_screen  # fondo/tinta del tema

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import personalidad as P                                       # noqa: E402
import hublayout as HL                                         # noqa: E402
import section_box as SB                                       # noqa: E402
# i18n (lado cliente): la pantalla TONO se ve en el idioma activo. Falla-suave
# — sin el módulo, `_t()` devuelve el español inline (ES byte-idéntico).
try:
    import i18n                                                 # noqa: E402
except Exception:
    i18n = None


def _t(key, es, **kw):
    if i18n is None:
        s = es
    else:
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

# Los diales agrupados por lo que gobiernan: fija el ORDEN visual de la lista
# (trato → forma → trabajo). Los encabezados de grupo ya no se pintan.
GRUPOS = (("trato", ("amabilidad", "franqueza", "sarcasmo", "humor")),
          ("forma", ("longitud", "formalidad", "tecnicismo", "emojis")),
          ("trabajo", ("didactica", "iniciativa")))
# Encabezados de grupo: se REUSAN de la Ola 1 (hub.tono.group.*), que es lo
# que ya traduce el mini-panel TONO del dashboard — misma historia, mismo texto.
_GRUPO_I18N = {"trato": "hub.tono.group.manner",
               "forma": "hub.tono.group.form",
               "trabajo": "hub.tono.group.work"}
# El orden VISUAL (por grupo) es independiente del idioma; las claves no
# cambian. Resolvemos los DATOS por idioma en cada uso (P.DIALS).
_ORDEN_KEYS = tuple(k for _, claves in GRUPOS for k in claves)

NEUTRO_TXT = "como siempre — este dial no envía nada"


def _orden():
    """Los diales en orden visual, con los textos en el idioma activo."""
    by = {d["key"]: d for d in P.DIALS}
    return tuple(by[k] for k in _ORDEN_KEYS)


def _pname(key):
    """Nombre VISIBLE del modo (preset); la clave interna no cambia."""
    return _t("tono.preset.%s" % key, key)


def _K():
    """La paleta del TEMA activo, igual que el hub. Sin tuitheme, el
    fallback de hublayout.cols() (nunca truena, solo pierde color)."""
    try:
        import tuitheme
        return HL.cols(tuitheme.palette())
    except Exception:
        return HL.cols(type("P", (), {"GLYPHS": {}})())


def _size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 100, 34


def _wrap(txt, w):
    pal, ln, out = str(txt).split(), "", []
    for p in pal:
        if len(ln) + len(p) + 1 > w:
            out.append(ln)
            ln = p
        else:
            ln = (ln + " " + p).strip()
    if ln:
        out.append(ln)
    return out or [""]


def _slider(K, v, i, ancho=5):
    """`━━━●─` — el MISMO slider del panel TONO del hub (_dia_slider): el
    recorrido en el gradiente del wordmark, la perilla ● encima. `i` elige
    el tono del gradiente, así la columna degrada como el título."""
    wc = K["WCOL"]
    col = wc[i % len(wc)] + K["BO"]
    v = max(1, min(ancho, int(v)))
    return "%s%s%s%s%s%s%s" % (col, "━" * (v - 1), "●", K["R"],
                               K["DK"], "─" * (ancho - v), K["R"])


def _divisor(K, txt, w, tono=-1):
    """`titulo ────` dentro de una caja — el gesto de los encabezados de
    grupo del panel TONO del `dia`: versalita + regla tenue, sin otro marco.
    `tono` ≥ 0 la pinta en ese paso del gradiente; -1 = apagada (DK)."""
    col = (K["WCOL"][tono % len(K["WCOL"])] + K["BO"]) if tono >= 0 \
        else K["DK"]
    regla = K["SEP"] * max(1, w - HL.vis(txt) - 2)
    return HL.clip("%s%s%s %s%s%s" % (col, str(txt), K["R"], K["DK"], regla,
                                      K["R"]), w)


def _destinos():
    """GLOBAL + los agentes registrados (misma fuente que el hub)."""
    return [None] + sorted(P.agentes_registrados())


def _sync_destinos(S):
    """Refresh profile destinations while retaining identity, never an index."""
    old = S.get('dests') or [None]
    selected = old[S.get('di', 0) % len(old)]
    fresh = _destinos()
    S['dests'] = fresh
    if selected in fresh:
        S['di'] = fresh.index(selected)
    else:
        S['di'] = 0
        S['preset'] = ''
        # A key already in flight must not now edit GLOBAL or another agent.
        S['destination_invalidated'] = True
        S['msg'] = _t('tono.msg.removed',
                      'El agente seleccionado ya no está registrado. Elige un destino antes de editar.')


def _nombre(dest):
    return "GLOBAL" if dest is None else dest.capitalize()


def _cuerpo_dial(S, K, dest, iw, full=2):
    """Caja derecha — la TRANSPARENCIA: qué ajusta el dial seleccionado
    (sus 5 niveles escritos, el actual marcado), el texto EXACTO que se le
    inyecta al agente y, con alto de sobra, cómo funciona todo.

    `full` es cuánto cabe: 2 = todo · 1 = sin la letra chica (cómo
    funciona) · 0 = solo el eje y la escalera de niveles."""
    d = _orden()[min(S["si"], len(_orden()) - 1)]
    niv = P.niveles(dest)
    v = niv[d["key"]]
    out = []
    # el eje en palabras, con el polo activo prendido
    pl, pr = d["eje"]
    cl = (K["WH"] + K["BO"]) if v < P.NEUTRO else K["DK"]
    cr = (K["WH"] + K["BO"]) if v > P.NEUTRO else K["DK"]
    out.append(HL.clip(" %s%s%s  %s  %s%s%s" % (
        cl, pl, K["R"], _slider(K, v, S["si"]), cr, pr, K["R"]), iw))
    out.append("")
    # la escalera 1→5: CADA nivel con su instrucción (el actual, completo)
    for n in (1, 2, 3, 4, 5):
        txt = d["niveles"].get(n) or _t("tono.neutral", NEUTRO_TXT)
        if n == v:
            cab = " %s%s %d%s  " % (K["C"] + K["BO"], K["PTR"], n, K["R"])
            lineas = _wrap(txt, max(8, iw - 7))[:2]
            out.append(HL.clip(cab + "%s%s%s" % (K["WH"] + K["BO"],
                                                 lineas[0], K["R"]), iw))
            for extra in lineas[1:]:
                out.append(HL.clip("      %s%s%s" % (K["WH"], extra, K["R"]),
                                   iw))
        else:
            out.append(HL.clip("   %s%d%s  %s%s%s" % (
                K["DK"], n, K["R"], K["DIM"], txt, K["R"]), iw))
    if full < 1:
        return out
    # ── lo que de verdad viaja al agente ──
    out.append("")
    out.append(_divisor(K, _t("tono.inject.divisor",
                              "se le inyecta a %s" % _nombre(dest).lower(),
                              name=_nombre(dest).lower()), iw, tono=3))
    act = P.activos(dest)
    if act:
        out.append(HL.clip(" %s%s%s"
                           % (K["DIM"],
                              _t("tono.inject.intro",
                                 "con cada mensaje tuyo viaja esta "
                                 "instrucción:"), K["R"]), iw))
        prefijo = _t("tono.inject.prefix", "[tono activo] ")
        vista = P.linea(dest).replace(prefijo, "")
        lineas = _wrap(vista, max(8, iw - 3))
        for ln in lineas[:2]:
            out.append(HL.clip(" %s%s%s" % (K["OK"], ln, K["R"]), iw))
        if len(lineas) > 2:
            out.append(HL.clip(" %s%s%s"
                               % (K["DK"],
                                  _t("tono.inject.truncated",
                                     "… (el agente la recibe completa)"),
                                  K["R"]), iw))
    else:
        out.append(HL.clip(" %s%s%s"
                           % (K["DK"],
                              _t("tono.inject.none",
                                 "nada — todo en neutro: %s responde como "
                                 "siempre" % _nombre(dest).lower(),
                                 name=_nombre(dest).lower()), K["R"]), iw))
    if full < 2:
        return out
    # ── cómo funciona (la letra chica, visible) ──
    out.append("")
    out.append(_divisor(K, _t("tono.how.title", "cómo funciona"), iw, tono=4))
    for ln in (_t("tono.how.1",
                  "cada cambio se guarda ya; aplica al siguiente mensaje"),
               _t("tono.how.2",
                  "3 = neutro: ese dial no envía nada (costo cero)"),
               _t("tono.how.3",
                  "GLOBAL aplica a todos; lo del agente pisa lo global"),
               _t("tono.how.4",
                  "solo estilo: jamás identidad, reglas ni honestidad")):
        for sub in _wrap(ln, max(8, iw - 4))[:2]:
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  sub, K["R"]), iw))
    return out


# ── REDISEÑO 2026-10-14 (concepto Omarchy): la cajita ─────────────────────
# Lo esencial a la vista —para quién, los diales y qué hace el nivel del dial
# elegido— en UNA caja centrada (section_box). Lo didáctico (cómo viaja el
# mensaje invisible, qué se le envía hoy, la escalera del dial, las reglas y
# las teclas de más) vive detrás de `i`. Los paneles lado a lado de antes se
# fueron; sus textos están en el cuadro de `i`, no se perdió ninguno.
#: Ancho de la columna de diales: lo que mide una fila (cursor, nombre, slider,
#: número y polo) más aire; la descripción del nivel se envuelve a este ancho.
DIALS_W = 36
#: Líneas máximas del texto del nivel: fija el alto de referencia de la caja
#: (así crece/encoge solo hacia abajo, sin moverse).
DESC_MAX = 4
#: Con menos ancho útil que esto (la columna «para» mínima + regla + diales),
#: los agentes van en una línea arriba de los diales en vez de en su columna.
SPLIT_MIN = 16 + SB.SPLIT_GAP + DIALS_W


def _chips(S=None):
    if S and S.get("continuar"):
        # desde el primer arranque: el botón «✦ continuar» (Enter) sigue el flujo
        return ((u"↑↓", _t("tono.hint.dial", "dial")),
                (u"←→", _t("tono.hint.level", "nivel")),
                ("Enter", _t("tono.hint.continue", "continúa")),
                ("i", _t("tono.hint.info", "cómo funciona")))
    return ((u"↑↓", _t("tono.hint.dial", "dial")),
            (u"←→", _t("tono.hint.level", "nivel")),
            ("Tab", _t("tono.hint.agent", "agente")),
            ("i", _t("tono.hint.info", "cómo funciona")),
            ("q", _t("tono.hint.back", "vuelve")))


def _fila(S, K, d, i, v, iw):
    sel = (i == S["si"])
    mov = v != P.NEUTRO
    cur = ("%s%s%s " % (K["C"] + K["BO"], K["PTR"], K["R"])) if sel else "  "
    lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel else (K["GREY"] if mov else K["DK"]),
                      HL.pad(d["label"], 12), K["R"])
    num = "%s%d%s" % ((K["WH"] + K["BO"]) if mov else K["DK"], v, K["R"])
    polo = (d["eje"][0] if v < P.NEUTRO else d["eje"][1] if v > P.NEUTRO else "—")
    pcol = K["GREY"] if mov else K["DK"]
    return HL.clip("%s%s %s  %s  %s%s%s" % (cur, lab, _slider(K, v, i), num, pcol,
                                            polo, K["R"]), iw)


def _diales(S, K, dest, iw):
    """Los 10 diales y, debajo, qué hace el nivel del dial elegido."""
    niv = P.niveles(dest)
    out = [_fila(S, K, d, i, niv[d["key"]], iw) for i, d in enumerate(_orden())]
    S["_cur"] = min(S["si"], len(out) - 1)
    en_boton = bool(S.get("continuar")) and S["si"] >= len(_orden())
    if not en_boton:
        d = _orden()[min(S["si"], len(_orden()) - 1)]
        v = niv[d["key"]]
        txt = d["niveles"].get(v) or _t("tono.neutral", NEUTRO_TXT)
        out.append("")
        # qué hace el nivel actual del dial elegido: título y, debajo, el texto
        # a ancho completo (sin sangría: la columna queda angosta)
        out.append(HL.clip("%s%s · %d%s" % (K["C"] + K["BO"], d["label"], v, K["R"]), iw))
        for ln in _wrap(txt, max(8, iw))[:DESC_MAX]:
            out.append(HL.clip("%s%s%s" % (K["WH"], ln, K["R"]), iw))
    if S.get("continuar"):
        # desde el primer arranque: un BOTÓN para seguir, al final (pedido del
        # dueño 2026-10-14); Enter en cualquier dial también sigue
        cur = ("%s%s%s " % (K["C"] + K["BO"], K["PTR"], K["R"])) if en_boton else "  "
        out += ["", HL.clip("%s%s%s%s" % (cur, (K["C"] + K["BO"]) if en_boton else (K["B2"] + K["BO"]),
                                          _t("tono.continuar", "✦ continuar"), K["R"]), iw)]
        if en_boton:
            S["_cur"] = len(out) - 1
    return out


def _propios():
    """Destinos con ajustes PROPIOS (no heredados de GLOBAL)."""
    store = P.load()
    out = set()
    if store.get("global"):
        out.add(None)
    for a, v in (store.get("agentes") or {}).items():
        if v:
            out.add(a)
    return out


def _lista_agentes(S, K, iw, alto):
    """GLOBAL + todos los agentes, en una lista que aguanta cualquier
    cantidad (scroll con el elegido a la vista). ● = tiene ajustes propios."""
    propios = _propios()
    items = [(_nombre(dn) if dn else _t("tono.box.dials_global", "GLOBAL (todos)"),
              "●" if dn in propios else "") for dn in S["dests"]]
    return SB.pick_list(K, items, S["di"] % len(S["dests"]), iw, alto,
                        title=_t("tono.list.title", "para"))


def _tira_agentes(S, K, iw):
    """Angosto: una sola línea `para ‹ Zenith › 2/7` arriba de los diales."""
    dests = S["dests"]
    i = S["di"] % len(dests)
    nom = _nombre(dests[i]) if dests[i] else _t("tono.box.dials_global", "GLOBAL (todos)")
    pos = "%d/%d" % (i + 1, len(dests))
    return HL.clip("%s%s%s  %s‹ %s ›%s  %s%s%s" % (
        K["DIM"], _t("tono.list.title", "para"), K["R"], K["C"] + K["BO"], nom, K["R"],
        K["DK"], pos, K["R"]), iw)


def _ancho_lista(S):
    """La columna «para» mide lo que su nombre más largo (+ cursor y ●),
    entre 16 y 24 columnas: ni sobra caja ni se cortan nombres comunes."""
    noms = [(_nombre(d) if d else _t("tono.box.dials_global", "GLOBAL (todos)"))
            for d in S["dests"]]
    return max(16, min(24, max(HL.vis(n) for n in noms) + 4))


def box_w(S):
    """Ancho de contenido de la caja: lista + regla + diales (se ajusta al
    contenido, no a la ventana)."""
    return _ancho_lista(S) + SB.SPLIT_GAP + DIALS_W


def _usa_columnas(S, w):
    """¿Cabe la columna «para» al lado de los diales en esta ventana?"""
    return SB.widths(w, box_w(S))[1] >= SPLIT_MIN


def _cuerpo(S, K, dest, iw):
    if iw >= SPLIT_MIN:
        lw = min(_ancho_lista(S), max(16, iw - SB.SPLIT_GAP - DIALS_W))
        der = _diales(S, K, dest, iw - lw - SB.SPLIT_GAP)
        izq = _lista_agentes(S, K, lw, len(der))
        return SB.split(K, izq, der, iw, lw)
    return [_tira_agentes(S, K, iw), ""] + _diales(S, K, dest, iw)


def _info_blocks(S, K, dest):
    """El cuadro de `i`, corto: el mapa, una explicación, lo que se le envía
    HOY a este destino, la escalera del dial elegido y las teclas de más."""
    nombre = _nombre(dest)
    d = _orden()[min(S["si"], len(_orden()) - 1)]
    if P.activos(dest):
        prefijo = _t("tono.inject.prefix", "[tono activo] ")
        envio = ("code", P.linea(dest).replace(prefijo, ""))
    else:
        envio = ("dim", _t("tono.inject.none",
                           "nada — todo en neutro: %s responde como siempre"
                           % nombre.lower(), name=nombre.lower()))
    return [
        ("flow", [(_t("tono.info.n1", "tus diales"),
                   _t("tono.info.c1", "en esta máquina")),
                  (_t("tono.info.n2", "nota invisible"),
                   _t("tono.info.c2", "viaja con cada mensaje")),
                  (_t("tono.info.n3", "tu agente"),
                   _t("tono.info.c3", "responde con ese estilo"))]),
        ("gap",),
        ("p", _t("tono.info.p2",
                 "Con cada mensaje tuyo, Workspace le agrega a tu agente una "
                 "instrucción que no ves, armada con estos diales. Solo cambia el "
                 "estilo, nunca quién es. El 3 es neutro (no envía nada) y lo de un "
                 "agente (●) pisa lo de GLOBAL.")),
        ("h", _t("tono.inject.divisor", "se le inyecta a %s" % nombre.lower(),
                 name=nombre.lower())),
        envio,
        ("h", d["label"]),
        ("lines", lambda iw: _cuerpo_dial(S, K, dest, iw, full=0)[2:]),
        ("gap",),
        ("dim", _t("tono.info.keys_line",
                   "1-5 nivel directo · p siguiente modo · r todo a neutro")),
    ]


def render(S, w, h):
    _sync_destinos(S)
    K = _K()
    dests = S["dests"]
    dest = dests[S["di"] % len(dests)]
    palabra = HL.section_word("tono")
    if S.get("info"):
        return SB.info_frame(K, w, h, palabra,
                             _t("tono.info.title", "CÓMO FUNCIONA EL TONO"),
                             _info_blocks(S, K, dest), state=S["info"], box_w=70)
    titulo = "%s · %s" % (_t("tono.box.title", "TONO"),
                          _nombre(dest).upper() if dest
                          else _t("tono.box.dials_global", "GLOBAL (todos)"))
    # (el cuadro de i, un poco más ancho: menos alto)
    columnas = _usa_columnas(S, w)
    return SB.frame(K, w, h, palabra, titulo,
                    lambda iw: _cuerpo(S, K, dest, iw), _chips(S),
                    msg=S.get("msg", ""),
                    cursor_line=lambda: S.get("_cur", S["si"]) + (0 if columnas else 2),
                    box_w=box_w(S),
                    stable_rows=len(_orden()) + 2 + DESC_MAX + (2 if not columnas else 0)
                    + (2 if S.get("continuar") else 0))


# ── acciones ───────────────────────────────────────────────────────────────
def _accion(S, key):
    """Devuelve False para salir. Cada cambio se guarda al instante. Con el
    cuadro de `i` abierto, las teclas son suyas (q/Esc lo cierran)."""
    _sync_destinos(S)
    if SB.info_key(S, key):
        return True
    if key in ('q', '\x1b', '\x03'):
        return False
    if S.pop('destination_invalidated', False):
        S['msg'] = _t('tono.msg.removed',
                      'El agente seleccionado ya no está registrado. Elige un destino antes de editar.')
        return True
    dests = S["dests"]
    dest = dests[S["di"] % len(dests)]
    orden = _orden()
    filas = len(orden) + (1 if S.get("continuar") else 0)   # + el botón «continuar»
    S["msg"] = ""
    if key in ("q", "\x1b", "\x03"):
        return False
    if S.get("continuar") and key in ("\r", "\n"):
        return False                         # el botón (o Enter): sigue el primer arranque
    if key == "up":
        S["si"] = (S["si"] - 1) % filas
        return True
    if key == "down":
        S["si"] = (S["si"] + 1) % filas
        return True
    if S["si"] >= len(orden):                # en el botón, las demás teclas no hacen nada
        return True
    d = orden[min(S["si"], len(orden) - 1)]
    if key in ("tab", "right_tab"):
        S["di"] = (S["di"] + (1 if key == "tab" else -1)) % len(dests)
        S["preset"] = ""
    elif key in ("left", "right"):
        v = P.niveles(dest)[d["key"]] + (1 if key == "right" else -1)
        v = max(1, min(5, v))
        P.set_nivel(d["key"], v, dest)
        S["msg"] = _t("tono.msg.saved",
                      "%s → %d/5 · guardado ✓ (aplica al siguiente mensaje)"
                      % (d["label"], v), label=d["label"], v=v)
    elif key in tuple("12345"):
        P.set_nivel(d["key"], int(key), dest)
        S["msg"] = _t("tono.msg.saved",
                      "%s → %s/5 · guardado ✓ (aplica al siguiente mensaje)"
                      % (d["label"], key), label=d["label"], v=key)
    elif key == "r":
        P.reset(dest)
        S["preset"] = ""
        S["msg"] = _t("tono.msg.reset",
                      "%s en neutro — no se le inyecta nada" % _nombre(dest),
                      name=_nombre(dest))
    elif key == "p":
        nombres = sorted(P.PRESETS)
        S["pi"] = (S.get("pi", -1) + 1) % len(nombres)
        S["preset"] = nombres[S["pi"]]
        P.aplicar_preset(S["preset"], dest)
        S["msg"] = _t("tono.msg.preset",
                      "modo «%s» aplicado a %s · p pasa al siguiente"
                      % (S["preset"], _nombre(dest)),
                      preset=_pname(S["preset"]), name=_nombre(dest))
    return True


import responsive_ui as _responsive
render = _responsive.renderer(render, 'TONO')
_accion = _responsive.action(_accion)

def _draw(tout, S, first=False):
    w, h = _size()
    try:
        _responsive.paint(tout, render(S, w, h), first=first)
    except Exception:
        pass


def _run_unix(S):
    import select
    import termios
    import tty
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        tout = open("/dev/tty", "w")
    except Exception:
        return P.imprimir()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h")
        _draw(tout, S, first=True)
        while True:
            if not select.select([fd], [], [], 0.5)[0]:
                _draw(tout, S)
                continue
            ch = os.read(fd, 1).decode("utf-8", "replace")
            key = ch
            if ch == "\x1b":
                if select.select([fd], [], [], 0.05)[0]:
                    seq = os.read(fd, 2).decode("utf-8", "replace")
                    key = {"[A": "up", "[B": "down", "[C": "right",
                           "[D": "left", "[Z": "right_tab"}.get(seq, "\x1b")
                else:
                    key = "\x1b"
            elif ch == "\t":
                key = "tab"
            if not _accion(S, key):
                break
            _draw(tout, S)
    finally:
        try:
            tout.write("\033[?1049l")
            tout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.close(fd)
        except Exception:
            pass
    return 0


def _run_windows(S):
    import msvcrt
    tout = sys.stdout
    tout.write("\033[?1049h")
    _draw(tout, S, first=True)
    try:
        while True:
            if not msvcrt.kbhit():
                time.sleep(0.1)
                _draw(tout, S)
                continue
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):               # flechas: prefijo + code
                a = msvcrt.getwch()
                key = {"H": "up", "P": "down", "M": "right",
                       "K": "left"}.get(a, "")
            elif ch == "\t":
                key = "tab"
            else:
                key = ch
            if not key:
                continue
            if not _accion(S, key):
                break
            _draw(tout, S)
    finally:
        try:
            tout.write("\033[?1049l")
            tout.flush()
        except Exception:
            pass
    return 0


@_theme_screen
def run():
    """Abre la pantalla. Sin terminal interactiva cae al listado de texto."""
    S = {"dests": _destinos(), "di": 0, "si": 0, "msg": "", "preset": ""}
    try:
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactivo = False
    if not interactivo:
        return P.imprimir()
    try:
        if os.name == "nt":
            return _run_windows(S)
        return _run_unix(S)
    except Exception as e:
        try:
            sys.stdout.write("\033[?1049l")
        except Exception:
            pass
        print("tono: %s" % e)
        return P.imprimir()


if __name__ == "__main__":
    sys.exit(run())
