#!/usr/bin/env python3
"""WORKSPACE · keybinds_tui — pantalla «Atajos»: tus teclas rápidas del hub.

La superficie del registro `keybinds.py` (defaults en código, overrides
per-máquina en ~/.claude/workspace/keybinds.json). Mismo lenguaje que el
rediseño del Tono (la pantalla modelo del Look WORKSPACE):

  1. **Fácil y simple**: una columna con TODAS las acciones y su tecla; se
     navega con ↑↓, Enter re-mapea (presionas la tecla nueva y queda
     GUARDADA al instante), r vuelve una al default, R (dos veces) todas.
  2. **Embona con WORKSPACE**: wordmark del hub, paleta del TEMA activo,
     cajas `full_box`, cursor `❯` — entrar aquí es cambiar de vista.
  3. **Transparencia**: el panel derecho dice qué HACE la acción elegida,
     su tecla actual y su default, si está personalizada, y las reglas
     completas (reservadas, colisiones, dónde se guarda). Una colisión no
     truena: te dice QUIÉN tiene la tecla.

Se abre desde el MENÚ del hub («Atajos», tecla default k) y regresa al
recinto — que al reconstruirse re-lee el registro: la tecla nueva aparece
pintada junto a su opción de inmediato.

Teclas:  ↑↓ acción · Enter re-mapear (luego: la tecla nueva · Esc cancela)
         r default de la acción · R (dos veces) todo a defaults · q vuelve

Mismo patrón de pantalla que tono_tui/calendario_tui (2J3JH al entrar,
H + \\033[K por línea después) y dos drivers: termios+select en Unix,
msvcrt en Windows. Cero dependencias (stdlib, Python 3.9+).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import keybinds as KB                                          # noqa: E402
import hublayout as HL                                         # noqa: E402

# orden VISUAL (por grupo) — el que recorre ↑↓. La sección «menú» del
# registro se deriva del menú REAL del hub (keybinds.refresh re-evalúa los
# gates): al abrir la pantalla se re-arma, por si cambió en este proceso.
ORDEN = tuple(aid for _t, ids in KB.GRUPOS for aid in ids)
_GRUPO_DE = {aid: t for t, ids in KB.GRUPOS for aid in ids}

# UNA fuente de verdad de los atajos (cabecera = clave + salir, pie = todo)
PARES = (("↑↓", "acción"), ("Enter", "re-mapear"), ("r", "default"),
         ("R", "todo a default"), ("q", "vuelve al menú"))
PARES_CAP = (("tecla nueva", "queda asignada ya"), ("Esc", "cancela"))

# i18n (lado cliente): traduce lo que ve el cliente. Falla-suave ABSOLUTA — sin
# el módulo, _t() devuelve el español inline (paridad exacta). Las labels/descs
# de DATOS (agente/acción/grupo) viven hardcodeadas en keybinds.py (fuente ES,
# fuera de mi alcance de edición): se surten vía _t(key, <valor KB>), así que en
# ES salen idénticas aunque el catálogo faltara. Las labels del MENÚ ya vienen
# traducidas de front.menu_entries (keybinds.label) → se referencian tal cual.
try:
    import i18n                                                 # noqa: E402
except Exception:
    i18n = None


def _t(key, es, **kw):
    """Traducción de `key` con el español inline `es` como red de seguridad:
    sin i18n o clave faltante → `es` (idéntico a hoy). Con **kw aplica
    .format(**kw) (falla-suave: si el format truena, cruda)."""
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


# grupo (keybinds.GRUPOS) → clave; el es inline es el propio título español.
_GRP_KEY = {"agentes": "atajos.group.agents",
            "menú": "atajos.group.menu",
            "acciones rápidas": "atajos.group.actions"}
# descripción re-mapeable por id (las del MENÚ salvo Dev —dev-only, se queda en
# español—; agente.N se arma aparte por su {n}).
_DESC_KEY = {"accion.motor": "atajos.desc.motor",
             "accion.info": "atajos.desc.info",
             "menu.__ramas__": "atajos.desc.menu_github",
             "menu.__cal__": "atajos.desc.menu_cal",
             "menu.__tono__": "atajos.desc.menu_tono",
             "menu.__keybinds__": "atajos.desc.menu_keys",
             "menu.__doctor__": "atajos.desc.menu_updates",
             "menu.__add_agent__": "atajos.desc.menu_addagent"}


def _tr_grupo(titulo):
    """Título de grupo traducido (es inline = el título español de keybinds)."""
    key = _GRP_KEY.get(titulo)
    return _t(key, titulo) if key else titulo


def _tr_label(aid):
    """Etiqueta traducida de una acción. Las del MENÚ ya vienen traducidas de
    menu_entries (keybinds.label) → se referencian tal cual."""
    if aid.startswith("agente."):
        return _t("atajos.label.agent", KB.label(aid), n=aid.split(".", 1)[1])
    if aid == "accion.motor":
        return _t("atajos.label.motor", KB.label(aid))
    if aid == "accion.info":
        return _t("atajos.label.info", KB.label(aid))
    return KB.label(aid)


def _tr_desc(aid):
    """Descripción traducida de una acción (es inline = la de keybinds.py)."""
    if aid.startswith("agente."):
        return _t("atajos.desc.agent", KB.desc(aid), n=aid.split(".", 1)[1])
    key = _DESC_KEY.get(aid)
    return _t(key, KB.desc(aid)) if key else KB.desc(aid)


def _pares():
    """La fila de atajos (cabecera + pie), traducida. Las teclas no cambian."""
    return ((PARES[0][0], _t("atajos.hint.action", "acción")),
            (PARES[1][0], _t("atajos.hint.remap", "re-mapear")),
            (PARES[2][0], _t("atajos.hint.default", "default")),
            (PARES[3][0], _t("atajos.hint.reset_all", "todo a default")),
            (PARES[4][0], _t("atajos.hint.back", "vuelve al menú")))


def _pares_cap():
    """La fila de atajos en modo CAPTURA, traducida."""
    return ((_t("atajos.cap.newkey", "tecla nueva"),
             _t("atajos.cap.assigned", "queda asignada ya")),
            (PARES_CAP[1][0], _t("atajos.cap.cancel", "cancela")))


def _rearmar_orden():
    global ORDEN, _GRUPO_DE
    try:
        KB.refresh()
    except Exception:
        pass                                      # registro de import intacto
    ORDEN = tuple(aid for _t, ids in KB.GRUPOS for aid in ids)
    _GRUPO_DE = {aid: t for t, ids in KB.GRUPOS for aid in ids}


def _K():
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


def _divisor(K, txt, w, tono=-1):
    col = (K["WCOL"][tono % len(K["WCOL"])] + K["BO"]) if tono >= 0 \
        else K["DK"]
    regla = K["SEP"] * max(1, w - HL.vis(str(txt)) - 2)
    return HL.clip("%s%s%s %s%s%s" % (col, str(txt), K["R"], K["DK"], regla,
                                      K["R"]), w)


def _tecla_txt(K, k, on=False):
    """La tecla como celda `⟨ x ⟩`-ish: visible, una sola señal. Vacía
    (tapada por colisión) → «—» con aviso de color."""
    if not k:
        return "%s—%s" % (K["ERR"] if on else K["DK"], K["R"])
    col = (K["C"] + K["BO"]) if on else K["B2"]
    return "%s%s%s" % (col, k, K["R"])


def _fila(S, K, eff, idx, iw):
    """Una acción del listado: cursor · etiqueta · (●=personalizada) ·
    TECLA a la derecha — el mismo gesto label/valor de los pins del hub."""
    aid = ORDEN[idx]
    sel = (idx == S["si"])
    k = eff.get(aid, "")
    cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
    lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel else K["GREY"],
                      _tr_label(aid), K["R"])
    dot = " %s●%s" % (K["B2"], K["R"]) if KB.es_custom(aid) else ""
    der = _tecla_txt(K, k, on=sel) + dot
    hueco = max(1, iw - 3 - HL.vis(lab) - HL.vis(der))
    return HL.clip(" %s %s%s%s" % (cur, lab, " " * hueco, der), iw)


def _cuerpo_lista(S, K, iw, alto, grupos=True):
    """Caja izquierda. Con alto de sobra, agrupada (divisores de grupo);
    apretada, plana; y si NI plana cabe, VENTANA con el cursor visible y
    marcadores honestos `▲ +n / ▼ +n` (jamás se recorta en silencio)."""
    eff = KB.effective()
    if grupos:
        out, i = [], 0
        for n, (titulo, ids) in enumerate(KB.GRUPOS):
            if n:
                out.append("")
            out.append(_divisor(K, _tr_grupo(titulo), iw, tono=n * 2))
            for _aid in ids:
                out.append(_fila(S, K, eff, i, iw))
                i += 1
        if len(out) <= alto:
            return out
    filas = [_fila(S, K, eff, i, iw) for i in range(len(ORDEN))]
    if len(filas) <= alto:
        return filas
    vis = max(3, alto - 2)                       # deja sitio a ▲/▼
    off = min(max(0, S["si"] - vis // 2), len(filas) - vis)
    out = []
    if off > 0:
        out.append(HL.clip(" %s▲ +%d%s" % (K["DK"], off, K["R"]), iw))
    out += filas[off:off + vis]
    resto = len(filas) - off - vis
    if resto > 0:
        out.append(HL.clip(" %s▼ +%d%s" % (K["DK"], resto, K["R"]), iw))
    return out


def _cuerpo_detalle(S, K, iw, full=2):
    """Caja derecha — la TRANSPARENCIA de la acción elegida: qué hace, su
    tecla actual/default, estado, y (full=2) las reglas completas. En modo
    CAPTURA la caja entera se vuelve el prompt: imposible no saber que la
    siguiente tecla es la que queda."""
    aid = ORDEN[S["si"]]
    eff = KB.effective()
    k, dflt = eff.get(aid, ""), KB.default_of(aid)
    out = []
    if S.get("cap"):
        out.append("")
        out.append(HL.clip("  %s%s▸ %s%s"
                           % (K["C"], K["BO"],
                              _t("atajos.cap.prompt", "presiona la tecla "
                                 "nueva…"), K["R"]), iw))
        out.append("")
        out.append(HL.clip("  %s%s%s"
                           % (K["DIM"], _t("atajos.cap.for",
                                           "para «{label}» (hoy: {k})",
                                           label=_tr_label(aid), k=k or "—"),
                              K["R"]), iw))
        out.append("")
        out.append(HL.clip("  %s%s%s"
                           % (K["DK"], _t("atajos.cap.foot", "Esc cancela · "
                              "se guarda al instante"), K["R"]), iw))
        return out
    # qué hace
    for ln in _wrap(_tr_desc(aid), max(8, iw - 3))[:4]:
        out.append(HL.clip(" %s%s%s" % (K["WH"], ln, K["R"]), iw))
    out.append("")
    # tecla actual / default / estado
    est = ("%s%s%s" % (K["B2"], _t("atajos.det.custom", "● personalizada"),
                       K["R"])) if KB.es_custom(aid) \
        else ("%s%s%s" % (K["DK"], _t("atajos.det.factory", "de fábrica"),
                          K["R"]))
    out.append(HL.clip(" %s%s%s  %s   %s%s%s  %s%s%s   %s" % (
        K["DIM"], _t("atajos.det.key", "tecla"), K["R"], _tecla_txt(K, k, on=True),
        K["DIM"], _t("atajos.det.default", "default"), K["R"],
        K["GREY"], dflt, K["R"], est), iw))
    if not k:
        out.append(HL.clip(" %s%s%s"
                           % (K["ERR"], _t("atajos.det.notecla",
                              "sin tecla — su default «{dflt}» lo tomó otra "
                              "acción; re-mapéala con Enter", dflt=dflt),
                              K["R"]), iw))
    if full < 1:
        return out
    out.append("")
    out.append(_divisor(K, _t("atajos.det.how", "cómo funciona"), iw, tono=4))
    for ln in (_t("atajos.det.rule1", "Enter re-mapea: la siguiente tecla "
                  "queda guardada YA (per-máquina, no toca a tu equipo)"),
               _t("atajos.det.rule2", "una tecla = una acción: si ya está "
                  "tomada te digo quién la tiene — nada truena"),
               _t("atajos.det.rule3", "reservadas: q · espacio · Enter · Esc "
                  "· flechas · Tab · t a e x f d n p (otras pantallas)"),
               _t("atajos.det.rule4", "r = default de esta acción · R dos "
                  "veces = todo de fábrica")):
        for nsub, sub in enumerate(_wrap(ln, max(8, iw - 4))[:3]):
            pref = "·" if nsub == 0 else " "
            out.append(HL.clip(" %s%s%s %s%s%s" % (K["DK"], pref, K["R"],
                                                   K["DIM"], sub, K["R"]),
                               iw))
    if full < 2:
        return out
    out.append("")
    ruta = KB._path().replace(os.path.expanduser("~"), "~")
    out.append(HL.clip(" %s%s%s" % (K["DK"], _t("atajos.det.saved_in",
                       "se guarda en {ruta}", ruta=ruta), K["R"]), iw))
    return out


def render(S, w, h):
    K = _K()
    S["si"] %= max(1, len(ORDEN))                # defensa: cursor en rango
    # cabecera COMPARTIDA (wordmark + subtítulo + atajos clave + regla);
    # en captura los atajos de arriba cambian con el modo — nunca mienten
    L = HL.screen_header(K, w, h,
                         _t("atajos.sub", "atajos — tus teclas rápidas del hub"),
                         hints=(_pares_cap() if S.get("cap") else _pares()))
    top = len(L)
    apilado = w < 100
    lw = (w - 1) if apilado else max(32, min(40, (w - 6) * 42 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    avail = max(8, (h - 1) - top - 3)
    bi = bd = None
    # apilado: las cajas van con pw = lw-1 y un espacio de sangría → el
    # cuerpo dispone de UNA columna menos que lado a lado
    bwl, bwr = (lw - 5, rw - 5) if apilado else (lw - 4, rw - 4)
    for grupos, full in ((True, 2), (True, 1), (False, 1), (False, 0)):
        ih_l = avail - 2 if not apilado else max(5, avail * 3 // 5 - 2)
        bi = _cuerpo_lista(S, K, bwl, ih_l, grupos=grupos)
        bd = _cuerpo_detalle(S, K, bwr, full=full)
        need = (len(bi) + len(bd) + 4) if apilado \
            else (max(len(bi), len(bd)) + 2)
        if need <= avail:
            break
    aid = ORDEN[S["si"]]
    t_izq = _t("atajos.box.left", "ATAJOS · {grp}",
               grp=_tr_grupo(_GRUPO_DE.get(aid, "")))
    t_der = _t("atajos.box.right", "LA TECLA · {label}", label=_tr_label(aid))
    if apilado:
        ih_d = max(3, min(len(bd), avail - (len(bi) + 2) - 2))
        for ln in HL.full_box(t_izq, bi, K, lw - 1, len(bi), not S.get("cap"),
                              border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
        for ln in HL.full_box(t_der, bd, K, rw - 1, ih_d, bool(S.get("cap")),
                              border=K["B2"], label=K["B"] + K["BO"]):
            L.append(HL.clip(" " + ln, w - 1))
    else:
        ch = min(avail, max(len(bi), len(bd)) + 2)
        izq = HL.full_box(t_izq, bi, K, lw, ch - 2, not S.get("cap"),
                          border=K["C"])
        der = HL.full_box(t_der, bd, K, rw, ch - 2, bool(S.get("cap")),
                          border=K["B2"], label=K["B"] + K["BO"])
        for i in range(ch):
            L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "", lw)
                             + "  " + (der[i] if i < len(der) else ""),
                             w - 1))
    L.append("")
    if S.get("msg"):
        L.append(" %s%s%s" % (K["B2"], S["msg"], K["R"]))
    else:
        L.append("")
    L.append(HL.foot_hints(K, _pares_cap() if S.get("cap") else _pares(), w))
    return [HL.clip(x, w - 1) for x in L[:h - 1]]


# ── acciones ───────────────────────────────────────────────────────────────
def _accion(S, key):
    """Devuelve False para salir. Cada cambio se guarda al instante."""
    aid = ORDEN[S["si"]]
    S["msg"] = ""
    if S.get("cap"):                              # modo CAPTURA: la tecla ES el dato
        S["cap"] = False
        if key in ("\x1b", "\x03"):
            S["msg"] = _t("atajos.msg.cancel",
                          "cancelado — {label} sigue en «{k}»",
                          label=_tr_label(aid),
                          k=KB.effective().get(aid) or "—")
        elif key in ("up", "down", "left", "right", "tab", "right_tab",
                     "\r", "\n") or not key:
            S["msg"] = _t("atajos.msg.badkey", "esa no me sirve — un "
                          "carácter imprimible (Enter reintenta)")
        else:
            _ok, S["msg"] = KB.set_key(aid, key)
        return True
    if key in ("q", "\x1b", "\x03"):
        return False
    if key == "R":                                # todo a defaults: 2 toques
        if S.get("confirm"):
            S["confirm"] = False
            _ok, S["msg"] = KB.reset_all()
        else:
            S["confirm"] = True
            S["msg"] = _t("atajos.msg.reset_confirm",
                          "R otra vez para restaurar TODO a defaults")
        return True
    S["confirm"] = False
    if key == "up":
        S["si"] = (S["si"] - 1) % len(ORDEN)
    elif key == "down":
        S["si"] = (S["si"] + 1) % len(ORDEN)
    elif key in ("\r", "\n"):
        S["cap"] = True
    elif key == "r":
        _ok, S["msg"] = KB.clear(aid)
    return True


import responsive_ui as _responsive
render = _responsive.renderer(render, 'ATAJOS')
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
        return KB.imprimir()
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
    """Abre la pantalla. Sin terminal interactiva cae al listado plano."""
    _rearmar_orden()
    S = {"si": 0, "msg": "", "cap": False, "confirm": False}
    try:
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactivo = False
    if not interactivo:
        return KB.imprimir()
    try:
        if os.name == "nt":
            return _run_windows(S)
        return _run_unix(S)
    except Exception as e:
        try:
            sys.stdout.write("\033[?1049l")
        except Exception:
            pass
        print("atajos: %s" % e)
        return KB.imprimir()


if __name__ == "__main__":
    sys.exit(run())
