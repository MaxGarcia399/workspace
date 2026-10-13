#!/usr/bin/env python3
"""WORKSPACE · section_frame — el MARCO común de las pantallas-sección.

Destilado de las secciones que mejor cumplen la misión (Atajos, Tono,
Calendario, el picker de sesiones): cabecera de marca, una fila opcional de
selección, DOS cajas — a la izquierda lo que puedes elegir, a la derecha lo
elegido: qué es, su estado y qué puedes hacer con él — y al pie los botones
con TODAS las teclas. Nada de mapas ni texto que no lleve a una acción.

Reglas de contenido (transparencia · simpleza · utilidad real):
  · cada fila de la izquierda = una cosa que existe y se puede tocar;
  · la derecha dice el estado REAL y la siguiente acción, en pocas líneas;
  · «cómo funciona» ≤ 4 viñetas cortas, solo si cabe;
  · el mensaje de la última acción aparece sobre el pie (lo que pasó, ya).

API (pura, testeable — devuelve líneas, no pinta):
  K()                                  paleta del tema activo
  divisor(K, txt, w, tono)             «grupo ─────»
  row(K, label, value, iw, sel, mark)  fila  ❯ etiqueta ··· valor
  kv(K, key, value, iw, hint)          clave  valor            tecla
  bullets(K, items, iw)                · viñetas tenues envueltas
  wrap(txt, w)
  frame(...)                           la pantalla completa
"""
import os

import hublayout as HL


def K():
    try:
        import tuitheme
        return HL.cols(tuitheme.palette())
    except Exception:
        return HL.cols(type("P", (), {"GLYPHS": {}})())


def size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 110, 40


def wrap(txt, w):
    pal, ln, out = str(txt).split(), "", []
    for p in pal:
        if ln and HL.vis(ln) + HL.vis(p) + 1 > w:
            out.append(ln)
            ln = p
        else:
            ln = (ln + " " + p).strip()
    if ln:
        out.append(ln)
    return out or [""]


def divisor(K, txt, w, tono=-1):
    col = (K["WCOL"][tono % len(K["WCOL"])] + K["BO"]) if tono >= 0 and K.get("WCOL") \
        else K["DK"]
    regla = K["SEP"] * max(1, w - HL.vis(str(txt)) - 2)
    return HL.clip("%s%s%s %s%s%s" % (col, str(txt), K["R"], K["DK"], regla, K["R"]), w)


def row(K, label, value, iw, sel=False, mark="", value_col=None):
    """` ❯ ● etiqueta ········ valor` — el gesto label/valor de Atajos."""
    cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
    lab = "%s%s%s%s" % (mark + " " if mark else "",
                        (K["WH"] + K["BO"]) if sel else K["GREY"], label, K["R"])
    der = "%s%s%s" % (value_col or (K["B2"] if sel else K["DIM"]), value, K["R"]) \
        if value else ""
    hueco = max(1, iw - 3 - HL.vis(lab) - HL.vis(der))
    return HL.clip(" %s %s%s%s" % (cur, lab, " " * hueco, der), iw)


def kv(K, key, value, iw, hint="", value_col=None, keyw=10):
    """` clave     valor                 tecla acción`."""
    k = "%s%s%s" % (K["DIM"], HL.pad(str(key), keyw), K["R"])
    v = "%s%s%s" % (value_col or K["WH"], value, K["R"])
    h = ("%s%s%s" % (K["DK"], hint, K["R"])) if hint else ""
    hueco = max(1, iw - 2 - HL.vis(k) - HL.vis(v) - HL.vis(h))
    if not h:
        return HL.clip(" %s %s" % (k, v), iw)
    return HL.clip(" %s %s%s%s" % (k, v, " " * hueco, h), iw)


def bullets(K, items, iw, max_lines=3):
    out = []
    for it in items:
        for n, sub in enumerate(wrap(it, max(8, iw - 4))[:max_lines]):
            out.append(HL.clip(" %s%s%s %s%s%s" % (K["DK"], "·" if n == 0 else " ", K["R"],
                                                   K["DIM"], sub, K["R"]), iw))
    return out


def text(K, txt, iw, col=None, max_lines=4):
    return [HL.clip(" %s%s%s" % (col or K["WH"], ln, K["R"]), iw)
            for ln in wrap(txt, max(8, iw - 3))[:max_lines]]


def window(lines, cursor_line, height, K, iw, index_map=None):
    """Ventana con el cursor visible y marcadores honestos ▲/▼. Si se pasa
    `index_map` (lista), se llena con el índice original de cada línea
    visible (None en los marcadores) — para mapear clicks."""
    if len(lines) <= height:
        if index_map is not None:
            index_map[:] = list(range(len(lines)))
        return lines
    vis = max(3, height - 2)
    off = min(max(0, cursor_line - vis // 2), len(lines) - vis)
    out, idx = [], []
    if off > 0:
        out.append(HL.clip(" %s▲ +%d%s" % (K["DK"], off, K["R"]), iw))
        idx.append(None)
    out += lines[off:off + vis]
    idx += list(range(off, off + min(vis, len(lines) - off)))
    rest = len(lines) - off - vis
    if rest > 0:
        out.append(HL.clip(" %s▼ +%d%s" % (K["DK"], rest, K["R"]), iw))
        idx.append(None)
    if index_map is not None:
        index_map[:] = idx
    return out


def frame(K, w, h, sub, word, hints, left_title, left, right_title, right,
          msg="", top=None, focus_left=True, cursor_line=0, left_min=34,
          left_max=46, footer_hints=None, header_hints=True, layout=None):
    """La pantalla completa. `left`/`right` = funciones (iw, ih) → [líneas]
    o listas ya hechas. `top` = líneas opcionales bajo la cabecera (fila de
    selección o buscador). Lado a lado con ≥100 columnas; apilado debajo."""
    w, h = max(1, int(w)), max(2, int(h))
    # header_hints=False: los atajos viven UNA vez, al pie (sin repetirlos arriba)
    L = HL.screen_header(K, w, h, sub, hints=hints if header_hints else None,
                         word=word, compact_h=40)
    for ln in (top or []):
        L.append(HL.clip(ln, w - 1))
    if top:
        L.append("")
    avail = max(6, (h - 1) - len(L) - 5)
    side = w >= 100
    lw = max(left_min, min(left_max, (w - 6) * 40 // 100)) if side else w - 2
    rw = (w - 1) - lw - 3 if side else w - 2

    def body(fn, iw, ih):
        return fn(iw, ih) if callable(fn) else list(fn)

    lmap = []
    if side:
        bl = body(left, lw - 4, avail - 2)
        br = body(right, rw - 4, avail - 2)
        bl = window(bl, cursor_line, avail - 2, K, lw - 4, lmap)
        ch = min(avail, max(len(bl), len(br)) + 2)
        if layout is not None:          # filas absolutas del 1er renglón de cada caja
            layout.update(left_top=len(L) + 1, right_top=len(L) + 1, left_map=lmap,
                          right_rows=ch - 2)
        izq = HL.full_box(left_title, bl, K, lw, ch - 2, focus_left, border=K["C"])
        der = HL.full_box(right_title, br, K, rw, ch - 2, not focus_left,
                          border=K["B2"], label=K["B"] + K["BO"])
        for i in range(ch):
            L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "", lw)
                             + "  " + (der[i] if i < len(der) else ""), w - 1))
    else:
        ih_l = max(3, avail * 1 // 2 - 2)
        bl = window(body(left, lw - 5, ih_l), cursor_line, ih_l, K, lw - 5, lmap)
        br = body(right, rw - 5, max(3, avail - len(bl) - 4))
        ih_r = max(3, min(len(br), avail - (len(bl) + 2) - 2))
        if layout is not None:
            layout.update(left_top=len(L) + 1, right_top=len(L) + 1 + len(bl) + 2,
                          left_map=lmap, right_rows=ih_r)
        for ln in HL.full_box(left_title, bl, K, lw - 1, len(bl), focus_left, border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
        for ln in HL.full_box(right_title, br, K, rw - 1, ih_r, not focus_left,
                              border=K["B2"], label=K["B"] + K["BO"]):
            L.append(HL.clip(" " + ln, w - 1))
    L = L[:max(0, h - 1 - 4)]
    foot = HL.instruction_buttons(K, footer_hints or hints, w - 1)
    # ALTO ESTABLE: h-1 líneas exactas (el pie queda anclado abajo)
    L += [""] * max(0, (h - 1) - len(L) - 2 - len(foot))
    L.append("")
    L.append(" %s%s%s" % (K["B2"], msg, K["R"]) if msg else "")
    L.extend(foot)
    return [HL.clip(x, w - 1) for x in L[:h - 1]]


def t(key, es, en=None, **kw):
    """i18n lado cliente, falla-suave: catálogo (i18n) → inline ES/EN."""
    s = es
    try:
        import i18n
        v = i18n.t(key, **kw) if kw else i18n.t(key)
        if v != key:
            return v
        if en is not None and i18n.lang() == "en":
            s = en
    except Exception:
        pass
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s
