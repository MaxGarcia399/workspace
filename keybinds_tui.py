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

# orden VISUAL (por grupo) — el que recorre ↑↓
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
                      KB.label(aid), K["R"])
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
            out.append(_divisor(K, titulo, iw, tono=n * 2))
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
        out.append(HL.clip("  %s%s▸ presiona la tecla nueva…%s"
                           % (K["C"], K["BO"], K["R"]), iw))
        out.append("")
        out.append(HL.clip("  %spara «%s» (hoy: %s)%s"
                           % (K["DIM"], KB.label(aid), k or "—", K["R"]),
                           iw))
        out.append("")
        out.append(HL.clip("  %sEsc cancela · se guarda al instante%s"
                           % (K["DK"], K["R"]), iw))
        return out
    # qué hace
    for ln in _wrap(KB.desc(aid), max(8, iw - 3))[:4]:
        out.append(HL.clip(" %s%s%s" % (K["WH"], ln, K["R"]), iw))
    out.append("")
    # tecla actual / default / estado
    est = ("%s● personalizada%s" % (K["B2"], K["R"])) if KB.es_custom(aid) \
        else ("%sde fábrica%s" % (K["DK"], K["R"]))
    out.append(HL.clip(" %stecla%s  %s   %sdefault%s  %s%s%s   %s" % (
        K["DIM"], K["R"], _tecla_txt(K, k, on=True),
        K["DIM"], K["R"], K["GREY"], dflt, K["R"], est), iw))
    if not k:
        out.append(HL.clip(" %ssin tecla — su default «%s» lo tomó otra "
                           "acción; re-mapéala con Enter%s"
                           % (K["ERR"], dflt, K["R"]), iw))
    if full < 1:
        return out
    out.append("")
    out.append(_divisor(K, "cómo funciona", iw, tono=4))
    for ln in ("Enter re-mapea: la siguiente tecla queda guardada YA "
               "(per-máquina, no toca a tu equipo)",
               "una tecla = una acción: si ya está tomada te digo quién "
               "la tiene — nada truena",
               "reservadas: q · espacio · Enter · Esc · flechas · Tab · "
               "t a e x f d n p (otras pantallas)",
               "r = default de esta acción · R dos veces = todo de fábrica"):
        for nsub, sub in enumerate(_wrap(ln, max(8, iw - 4))[:3]):
            pref = "·" if nsub == 0 else " "
            out.append(HL.clip(" %s%s%s %s%s%s" % (K["DK"], pref, K["R"],
                                                   K["DIM"], sub, K["R"]),
                               iw))
    if full < 2:
        return out
    out.append("")
    ruta = KB._path().replace(os.path.expanduser("~"), "~")
    out.append(HL.clip(" %sse guarda en %s%s" % (K["DK"], ruta, K["R"]), iw))
    return out


def render(S, w, h):
    K = _K()
    S["si"] %= max(1, len(ORDEN))                # defensa: cursor en rango
    L = [""]
    bt = HL.big_title(K, w, h, indent=" ", compact=(h < 30), center=True)
    L += bt
    if len(bt) > 1:
        L += HL.title_reflection(K, w, indent=" ", center=True)
    sub = "atajos — tus teclas rápidas del hub"
    L.append(" " * max(0, ((w - 1) - HL.vis(sub)) // 2)
             + "%s%s%s" % (K["DIM"], sub, K["R"]))
    L.append("%s%s%s%s%s" % (K["B2"], K["BOX"][5] * 3, K["DK"],
                             K["BOX"][5] * max(1, w - 5), K["R"]))
    L.append("")
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
    t_izq = "ATAJOS · %s" % _GRUPO_DE.get(aid, "")
    t_der = "LA TECLA · %s" % KB.label(aid)
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
    hint = "presiona la tecla nueva · Esc cancela" if S.get("cap") else \
        ("↑↓ acción · Enter re-mapear · r default · R todo default · "
         "q vuelve al menú")
    L.append(" %s%s%s" % (K["DK"], hint, K["R"]))
    return [HL.clip(x, w - 1) for x in L[:h - 1]]


# ── acciones ───────────────────────────────────────────────────────────────
def _accion(S, key):
    """Devuelve False para salir. Cada cambio se guarda al instante."""
    aid = ORDEN[S["si"]]
    S["msg"] = ""
    if S.get("cap"):                              # modo CAPTURA: la tecla ES el dato
        S["cap"] = False
        if key in ("\x1b", "\x03"):
            S["msg"] = "cancelado — %s sigue en «%s»" \
                % (KB.label(aid), KB.effective().get(aid) or "—")
        elif key in ("up", "down", "left", "right", "tab", "right_tab",
                     "\r", "\n") or not key:
            S["msg"] = "esa no me sirve — un carácter imprimible " \
                       "(Enter reintenta)"
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
            S["msg"] = "R otra vez para restaurar TODO a defaults"
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
