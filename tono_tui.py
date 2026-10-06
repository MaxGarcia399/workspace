#!/usr/bin/env python3
"""WORKSPACE · tono_tui — pantalla propia del TONO de los agentes.

REDISEÑO (pedido del socio 2026-10-01, PDF WORKSPACE): la pantalla anterior
tenía paleta propia (no era el tema del hub), el preview era críptico y no
decía QUÉ hace cada dial. Tres direcciones, en orden de importancia:

  1. **Fácil y simple**: una columna de diales con su perilla, un panel que
     siempre muestra EL DIAL seleccionado con sus 5 niveles escritos — subes
     o bajas viendo exactamente a qué te mueves. Cada cambio se guarda ya.
  2. **Embonar con WORKSPACE**: mismo esqueleto que `calendario_tui` — el
     wordmark del hub, la paleta del TEMA activo (tuitheme), las cajas
     `full_box` y los sliders `━━●──` con el gradiente del wordmark
     (idénticos al panel TONO del layout `dia`). Entrar aquí es cambiar de
     vista, no de app.
  3. **Transparencia**: el panel derecho dice qué ajusta el dial (los 5
     niveles, con el actual marcado), qué se le inyecta al agente (el texto
     EXACTO que viaja con cada mensaje) y CÓMO FUNCIONA (neutro = no se
     envía nada; agente pisa GLOBAL; solo estilo, jamás identidad/reglas).

Se abre con `workspace tono` o desde el MENÚ del hub («Tono»).

Teclas:  ↑↓ dial · ◄► nivel · 1-5 directo · Tab/⇧Tab agente
         p modo (preset) · r neutro · q volver   (cada cambio se GUARDA ya)

El modelo (diales, textos, almacén) vive en `personalidad.py`; esto es solo
la superficie. Mismo patrón de pantalla que calendario_tui/front (2J3JH al
entrar, H + \\033[K por línea después — nunca 2J a media sesión) y los dos
drivers de teclado: termios+select en Unix, msvcrt en Windows.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import personalidad as P                                       # noqa: E402
import hublayout as HL                                         # noqa: E402
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

# Los diales agrupados por lo que gobiernan — MISMOS grupos que el panel
# TONO del layout `dia` (hublayout._DIA_TONO_GRUPOS): la pantalla y el panel
# deben contar la misma historia. Si cambian allá, cambiar aquí.
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


def _pares():
    """UNA fuente de verdad de los atajos, en el idioma activo: la cabecera
    enseña los 3 clave + salir (HL recorta) y el pie la lista COMPLETA."""
    return ((u"↑↓", _t("tono.hint.dial", "dial")),
            (u"◄►", _t("tono.hint.level", "nivel")),
            ("Tab", _t("tono.hint.agent", "agente")),
            ("1-5", _t("tono.hint.direct", "directo")),
            ("p", _t("tono.hint.mode", "modo")),
            ("r", _t("tono.hint.neutral", "neutro")),
            ("q", _t("tono.hint.back", "vuelve al menú")))


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


def _nombre(dest):
    return "GLOBAL" if dest is None else dest.capitalize()


# ── cuerpos de las dos cajas ────────────────────────────────────────────────
def _cuerpo_diales(S, K, dest, iw, grupos=True):
    """Caja izquierda: los 10 diales con su slider + polo, agrupados, y los
    MODOS (presets) con nombre visible — nada de ciclar a ciegas."""
    niv = P.niveles(dest)
    orden = _orden()
    by = {d["key"]: d for d in orden}
    out, i = [], 0

    def fila(d, i):
        sel = (i == S["si"])
        v = niv[d["key"]]
        mov = v != P.NEUTRO
        cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
        lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel
                          else (K["GREY"] if mov else K["DK"]),
                          HL.pad(d["label"], 11), K["R"])
        num = "%s%d%s" % ((K["WH"] + K["BO"]) if mov else K["DK"], v, K["R"])
        polo = (d["eje"][0] if v < P.NEUTRO else
                d["eje"][1] if v > P.NEUTRO else "—")
        pcol = K["WH"] if mov else K["DK"]
        return HL.clip(" %s %s %s %s  %s%s%s" % (cur, lab, _slider(K, v, i),
                                                 num, pcol, polo, K["R"]), iw)

    if grupos:
        for n, (titulo, claves) in enumerate(GRUPOS):
            if n:
                out.append("")
            out.append(_divisor(K, _t(_GRUPO_I18N[titulo], titulo), iw))
            for k in claves:
                out.append(fila(by[k], i))
                i += 1
    else:
        for d in orden:
            out.append(fila(d, i))
            i += 1
    # ── modos (presets): visibles por nombre, p aplica el siguiente ──
    out.append("")
    out.append(_divisor(K, _t("tono.group.modes", "modos"), iw))
    nombres = sorted(P.PRESETS)
    trozos = []
    for n in nombres:
        on = (n == S.get("preset"))
        trozos.append("%s%s%s" % ((K["C"] + K["BO"]) if on else K["GREY"],
                                  _pname(n), K["R"]))
    out.append(HL.clip(" %sp%s  %s" % (K["C"] + K["BO"], K["R"],
                                       ("%s·%s" % (K["DK"], K["R"]))
                                       .join(trozos)), iw))
    out.append(HL.clip(" %s%s%s"
                       % (K["DIM"],
                          _t("tono.modes.hint",
                             "un modo mueve varios diales de golpe"),
                          K["R"]), iw))
    return out


def _cuerpo_dial(S, K, dest, iw, full=2):
    """Caja derecha — la TRANSPARENCIA: qué ajusta el dial seleccionado
    (sus 5 niveles escritos, el actual marcado), el texto EXACTO que se le
    inyecta al agente y, con alto de sobra, cómo funciona todo.

    `full` es cuánto cabe: 2 = todo · 1 = sin la letra chica (cómo
    funciona) · 0 = solo el eje y la escalera de niveles."""
    d = _orden()[S["si"]]
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


def _fila_destinos(S, K, w):
    """`❮ GLOBAL ❯  Zenith●  Atlas …` — a quién le estás moviendo el tono.
    El punto marca quién tiene ajustes PROPIOS (no heredados del global)."""
    dests = S["dests"]
    store = P.load()
    tabs = []
    for i, dn in enumerate(dests):
        on = (i == S["di"] % len(dests))
        propio = bool(store["global"] if dn is None
                      else (store["agentes"].get(dn) or {}))
        dot = "%s●%s" % (K["B2"], K["R"]) if propio else ""
        if on:
            tabs.append("%s%s %s %s%s%s" % (K["C"] + K["BO"], K["BL"],
                                            _nombre(dn), K["BR"], K["R"],
                                            dot))
        else:
            tabs.append("%s%s%s%s" % (K["GREY"], _nombre(dn), K["R"], dot))
    fila = " " + "   ".join(tabs)
    leg = "%s%s · %s●%s %s%s" % (K["DK"],
                                 _t("tono.dest.tab_changes", "Tab cambia"),
                                 K["B2"], K["DK"],
                                 _t("tono.dest.own_settings",
                                    "con ajustes propios"), K["R"])
    hueco = (w - 1) - HL.vis(fila) - HL.vis(leg) - 1
    if hueco > 1:
        fila += " " * hueco + leg
    return HL.clip(fila, w - 1)


def render(S, w, h):
    K = _K()
    dests = S["dests"]
    dest = dests[S["di"] % len(dests)]
    pares = _pares()
    # cabecera COMPARTIDA (wordmark + subtítulo + atajos clave + regla)
    L = HL.screen_header(K, w, h,
                         _t("tono.header.subtitle",
                            "tono — cómo te hablan tus agentes"),
                         hints=pares)
    L.append(_fila_destinos(S, K, w))
    L.append("")
    top = len(L)
    apilado = w < 100
    # dos cajas, mismas proporciones que el hub: DIALES a la izquierda,
    # EL DIAL (la transparencia) a la derecha. Si el alto no da, se ceden
    # los adornos en orden: grupos del listado → la letra chica del panel.
    lw = (w - 1) if apilado else max(34, min(42, (w - 6) * 44 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    avail = max(8, (h - 1) - top - 3)
    bi = bd = None
    # degradación: primero cede la letra chica (cómo funciona), luego los
    # encabezados de grupo, al final la sección de inyección — la escalera
    # de niveles y los diales navegables no se ceden jamás
    for grupos, full in ((True, 2), (True, 1), (False, 1), (False, 0)):
        bi = _cuerpo_diales(S, K, dest, lw - 4, grupos=grupos)
        bd = _cuerpo_dial(S, K, dest, rw - 4, full=full)
        need = (len(bi) + len(bd) + 4) if apilado \
            else (max(len(bi), len(bd)) + 2)
        if need <= avail:
            break
    d = _orden()[S["si"]]
    t_izq = "%s · %s" % (_t("tono.box.dials", "DIALES"),
                         _nombre(dest) if dest
                         else _t("tono.box.dials_global", "GLOBAL (todos)"))
    t_der = "%s · %s" % (_t("tono.box.dial", "EL DIAL"), d["label"])
    if apilado:                                  # ── angosto: APILADO ──
        # presupuesto honesto: DIALES entero; EL DIAL recibe lo que quede
        # (mínimo la escalera a 3 filas) — desbordar rompe el pie
        ih_d = max(3, min(len(bd), avail - (len(bi) + 2) - 2))
        for ln in HL.full_box(t_izq, bi, K, lw - 1, len(bi), True,
                              border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
        for ln in HL.full_box(t_der, bd, K, rw - 1, ih_d, False,
                              border=K["B2"], label=K["B"] + K["BO"]):
            L.append(HL.clip(" " + ln, w - 1))
    else:                                        # ── lado a lado ──
        ch = min(avail, max(len(bi), len(bd)) + 2)
        izq = HL.full_box(t_izq, bi, K, lw, ch - 2, True, border=K["C"])
        der = HL.full_box(t_der, bd, K, rw, ch - 2, False, border=K["B2"],
                          label=K["B"] + K["BO"])
        for i in range(ch):
            L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "", lw)
                             + "  " + (der[i] if i < len(der) else ""),
                             w - 1))
    L.append("")
    if S.get("msg"):
        L.append(" %s%s%s" % (K["B2"], S["msg"], K["R"]))
    else:
        L.append("")
    L.append(HL.foot_hints(K, pares, w))
    return [HL.clip(x, w - 1) for x in L[:h - 1]]


# ── acciones ───────────────────────────────────────────────────────────────
def _accion(S, key):
    """Devuelve False para salir. Cada cambio se guarda al instante."""
    dests = S["dests"]
    dest = dests[S["di"] % len(dests)]
    orden = _orden()
    d = orden[S["si"]]
    S["msg"] = ""
    if key in ("q", "\x1b", "\x03"):
        return False
    if key == "up":
        S["si"] = (S["si"] - 1) % len(orden)
    elif key == "down":
        S["si"] = (S["si"] + 1) % len(orden)
    elif key in ("tab", "right_tab"):
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
