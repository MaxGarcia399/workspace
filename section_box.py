"""WORKSPACE · section_box — la «cajita» de cada sección (rediseño 2026-10-14).

Concepto Omarchy, pedido del dueño: cada sección muestra SOLO lo esencial en
una caja centrada y vertical —el mismo lenguaje que el lanzador del hub:
wordmark arriba, caja centrada, aviso centrado y botones centrados al fondo—
y lo didáctico (textos y mapas) vive detrás de la tecla `i` (o `?`): un
cuadro con la misma geometría que ocupa el lugar de la caja mientras está
abierto. Nada de paneles lado a lado.

    frame(K, w, h, word, title, body, chips, msg, cursor_line, box_w)
        la sección. `body` = lista de líneas o función (iw) → líneas.
    info_frame(K, w, h, word, title, blocks, scroll)
        el cuadro de `i`. `blocks` = bloques didácticos (ver render_blocks).
    info_key(S, key) → True si la tecla era del cuadro de `i` (ábrelo,
        ciérralo o desplázalo); la sección no la procesa.

Todo devuelve EXACTAMENTE h-1 líneas, cada una ≤ w-1 columnas visibles, en
cualquier tamaño (cede wordmark → botones → filas, en ese orden). Stdlib.
"""
import re

import hublayout as HL

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

#: Teclas que abren/cierran el cuadro de explicación. `?` sirve donde `i`
#: escribe (un campo de texto).
INFO_KEYS = ("i", "?")
#: Ancho de CONTENIDO por defecto y límites de la caja.
BOX_W = 56
BOX_MIN = 36
PAD = 1                      # aire por lado dentro de la caja (+ «│ »)


def _t(key, es, en=None, **kw):
    try:
        import section_frame as SF
        return SF.t(key, es, en, **kw)
    except Exception:
        return es.format(**kw) if kw else es


def K():
    """La paleta del tema activo (la del hub)."""
    try:
        import tuitheme
        return HL.cols(tuitheme.palette())
    except Exception:
        return HL.cols(type("P", (), {"GLYPHS": {}})())


# ── geometría ────────────────────────────────────────────────────────────────
def widths(w, box_w=None):
    """(pw, iw): ancho total de la caja y ancho útil del contenido."""
    W = max(1, int(w) - 1)
    want = (box_w or BOX_W) + 4 + 2 * PAD
    pw = max(min(BOX_MIN + 4 + 2 * PAD, W), min(want, W))
    return pw, max(1, pw - 4 - 2 * PAD)


def _center(s, W):
    return HL.clip(" " * max(0, (W - HL.vis(s)) // 2) + s, W)


def _ancho_botones(pares):
    return sum(HL.vis(" %s %s " % pr) + 2 for pr in pares) + 3 * max(0, len(pares) - 1)


def _ancho_linea(pares):
    return sum(HL.vis("[ %s %s ]" % pr) for pr in pares) + 2 * max(0, len(pares) - 1)


def _caben(pares, W, medida):
    """Los pares que caben en W: si no caben todos, cede los del medio de
    atrás hacia adelante, pero JAMÁS el primero (cómo moverse), el último
    (cómo salir) ni el de `i` (la puerta a la explicación)."""
    pares = list(pares)
    while pares and medida(pares) > W:
        cand = [j for j in range(len(pares) - 2, 0, -1)
                if pares[j][0] not in INFO_KEYS]
        if not cand:
            break
        pares.pop(cand[0])
    return pares if medida(pares) <= W else []


def _chips(Kp, pares, W, nivel):
    if not pares or nivel == 0:
        return []
    if nivel == 3 and _ancho_botones(pares) <= W:
        rows = HL.instruction_buttons(Kp, pares, W)
        if rows:
            return [_center(r, W) for r in rows]
    if nivel == 3:
        pares_b = _caben(pares, W, _ancho_botones)
        if len(pares_b) == len(pares) or _ancho_linea(pares) > W:
            rows = HL.instruction_buttons(Kp, pares_b, W) if pares_b else []
            if rows:
                return [_center(r, W) for r in rows]
    ln = HL.keyline(Kp, _caben(pares, W, _ancho_linea), W)
    return [_center(ln, W)] if ln else []


def _header(Kp, w, word, nivel):
    if nivel == "full":
        # sin el reflejo ░ bajo el título: el wordmark del hub no lo lleva y
        # las secciones tampoco (pedido del dueño 2026-10-14: «mantener ese
        # detalle constante»)
        return [""] + HL.big_title(Kp, w, 0, indent=" ", center=True, word=word)
    if nivel == "compact":
        return HL.big_title(Kp, w, 0, compact=True, center=True, word=word)
    return []


def window(lines, cursor, ih):
    """(desde, ▲, ▼): ventana de `ih` filas con el cursor SIEMPRE visible."""
    n = len(lines)
    if n <= ih:
        return 0, False, False
    cursor = max(0, min(n - 1, cursor or 0))
    start = max(0, min(cursor - ih // 2, n - ih))
    return start, start > 0, start + ih < n


#: Separación entre la caja y su cuadro lateral.
SIDE_GAP = 2


def pair_fits(w, box_w, side_w):
    """¿Caben la caja (contenido `box_w`) y un cuadro lateral (`side_w`) lado
    a lado en una terminal de `w` columnas?"""
    return (box_w + 4 + 2 * PAD) + SIDE_GAP + (side_w + 4 + 2 * PAD) <= max(1, int(w) - 1)


def frame(Kp, w, h, word, title, body, chips, msg="", cursor_line=None,
          box_w=None, scroll=None, stable_rows=None, side=None):
    """La sección: wordmark de la sección, la caja centrada, el aviso y los
    botones. Si el body no cabe entero: `cursor_line` = fila que debe quedar
    a la vista (listas; puede ser una función, que se evalúa DESPUÉS de armar
    el body), o `scroll` = primera fila visible (textos largos,
    como el cuadro de `i`); se marca con ▲▼. Devuelve también, en
    frame.last_max_scroll, el máximo desplazamiento posible, en
    frame.last_start, la primera fila que quedó a la vista, y en
    frame.last_level, el nivel elegido (wordmark, filas de los botones).

    `stable_rows` = el alto MÁXIMO que puede tener el body (p. ej. con el
    texto más largo de una opción). La posición de la caja se calcula con ese
    máximo: su borde de arriba no se mueve y la caja solo crece o se encoge
    hacia ABAJO cuando cambia el contenido (pedido del dueño: que no «se
    sacuda» todo el cuadro).

    `side` = (título, body, ancho de contenido): un SEGUNDO cuadro a la
    derecha, del mismo alto (p. ej. la explicación que acompaña a la lista
    mientras te mueves). El par va centrado; el caller decide con
    `pair_fits` si cabe (si no, no lo pide)."""
    Kp = HL.cols(Kp)
    W, H = max(1, w - 1), max(1, h - 1)
    pw, iw = widths(w, box_w)
    lines = body(iw) if callable(body) else list(body)
    lines = [HL.clip(" " * PAD + ln, iw + PAD) for ln in lines]
    lines2 = None
    if side:
        t2, b2, sw = side
        pw2, iw2 = sw + 4 + 2 * PAD, sw
        lines2 = b2(iw2) if callable(b2) else list(b2)
        lines2 = [HL.clip(" " * PAD + ln, iw2 + PAD) for ln in lines2]
    if callable(cursor_line):
        cursor_line = cursor_line()
    aviso = _center("%s%s%s" % (Kp["B2"], msg, Kp["R"]), W) if msg else ""
    # lo que se cede con poco alto, en orden: wordmark grande → botones de 3
    # filas → wordmark compacto → la fila de aire → botones; la caja, nunca
    niveles = (("full", 3), ("compact", 3), ("full", 1), ("compact", 1),
               ("none", 1), ("none", 0))
    alto_ref = max(len(lines), int(stable_rows or 0), len(lines2 or []))
    need_box = alto_ref + 4                      # bordes + aire arriba/abajo

    def fijo(nv):
        return len(_header(Kp, w, word, nv[0])) + len(_chips(Kp, chips, W, nv[1])) + 2

    elegido = None
    for nv in niveles:
        if fijo(nv) + need_box <= H:
            elegido = nv
            break
    if elegido is None:
        # no cabe entero: scroll, pero los botones se quedan (sin ellos nadie
        # sabe cómo moverse ni cerrar); cede primero el wordmark
        for nv in (("compact", 1), ("none", 1), ("none", 0)):
            if H - fijo(nv) - 4 >= min(alto_ref, 6):
                elegido = nv
                break
        elegido = elegido or ("none", 0)
    frame.last_level = elegido
    top = _header(Kp, w, word, elegido[0])
    pie = _chips(Kp, chips, W, elegido[1])
    ih = max(1, min(max(len(lines), len(lines2 or [])) + 2,
                    H - len(top) - len(pie) - 2 - 2))
    cuerpo = [""] + lines + [""]
    frame.last_max_scroll = max(0, len(cuerpo) - ih)
    if scroll is not None:
        start = max(0, min(int(scroll), len(cuerpo) - ih)) if len(cuerpo) > ih else 0
        up, down = start > 0, start + ih < len(cuerpo)
    else:
        cur = (cursor_line + 1) if cursor_line is not None else 0
        start, up, down = window(cuerpo, cur, ih)
    frame.last_start = start
    vista = cuerpo[start:start + ih]
    if up and vista:
        vista[0] = HL.pad(vista[0], pw - 5) + "%s▲%s" % (Kp["DIM"], Kp["R"])
    if down and vista:
        vista[-1] = HL.pad(vista[-1], pw - 5) + "%s▼%s" % (Kp["DIM"], Kp["R"])
    caja = HL.full_box(title, vista, Kp, pw, ih, True, border=Kp["C"],
                       label=Kp["C"] + Kp["BO"])
    if lines2 is not None:
        cuerpo2 = [""] + lines2 + [""]
        vista2 = cuerpo2[:ih]
        if len(cuerpo2) > ih and vista2:
            vista2[-1] = HL.pad(vista2[-1], pw2 - 5) + "%s▼%s" % (Kp["DIM"], Kp["R"])
        caja2 = HL.full_box(t2, vista2, Kp, pw2, ih, True, border=Kp["B2"],
                            label=Kp["B"] + Kp["BO"])
        lp = " " * max(0, (W - pw - SIDE_GAP - pw2) // 2)
        caja = [HL.clip(lp + a + " " * SIDE_GAP + b, W) for a, b in zip(caja, caja2)]
    else:
        lp = " " * max(0, (W - pw) // 2)
        caja = [HL.clip(lp + ln, W) for ln in caja]
    # composición vertical: la caja un poco ARRIBA del centro (como el hub),
    # calculada con el alto de REFERENCIA (estable): el borde de arriba no se
    # mueve aunque cambie el contenido
    ih_ref = max(ih, min(alto_ref + 2, H - len(top) - len(pie) - 2 - 2))
    grupo = ih_ref + 2 + 1
    libre = H - len(top) - grupo - len(pie)
    arriba = max(0, libre // 3)
    L = list(top) + [""] * arriba + caja + [aviso]
    L += [""] * max(0, H - len(L) - len(pie)) + pie
    if len(L) > H:
        L = (L[:H - len(pie)] + pie) if len(pie) < H else L[:H]
    L += [""] * max(0, H - len(L))
    return [HL.clip(x, W) for x in L[:H]]


# ── lista + detalle dentro de la MISMA caja ──────────────────────────────────
def pick_list(Kp, items, sel, iw, height, title="", sel_tail=""):
    """Una lista que aguanta CUALQUIER cantidad de elementos: muestra una
    ventana de `height` filas con el elegido siempre a la vista y «▲ n más /
    ▼ n más» cuando hay de sobra. `items` = [(texto, marca)] (marca = "" o
    un símbolo corto pintado al final; un 3er elemento opcional = la clave de
    color de la marca: "OK", "ERR", "DIM"…). El elegido va en acento con «›».
    `sel_tail` = glifo al FINAL de la fila elegida (p. ej. «▸»: Enter/→ abre
    sus opciones); se reservan 2 columnas en todas las filas. Un 4º elemento
    opcional = la clave de color del TEXTO cuando no está elegido (p. ej. la
    fila «+ agregar» en acento)."""
    Kp = HL.cols(Kp)
    out = []
    if title:
        out.append(HL.clip("%s%s%s %s%s%s" % (Kp["B2"] + Kp["BO"], title, Kp["R"], Kp["DK"],
                                              Kp["SEP"] * max(1, iw - HL.vis(title) - 1),
                                              Kp["R"]), iw))
        height -= 1
    n = len(items)
    height = max(1, height)
    if n <= height:
        start, arriba, abajo = 0, 0, 0
    else:
        filas = max(1, height - 2)                # deja sitio a los dos avisos
        start = max(0, min(sel - filas // 2, n - filas))
        arriba, abajo = start, n - (start + filas)
        height = filas
    if arriba:
        out.append("%s▲ %s%s" % (Kp["DIM"], _t("sbox.more", "{n} más", "{n} more", n=arriba),
                                 Kp["R"]))
    cola = 2 if sel_tail else 0
    iw_l = max(4, iw - cola)
    for i in range(start, min(n, start + height)):
        txt, marca = items[i][0], items[i][1]
        mcol = Kp.get(items[i][2], Kp["B2"]) if len(items[i]) > 2 and items[i][2] else Kp["B2"]
        on = (i == sel)
        cur = ("%s›%s " % (Kp["C"] + Kp["BO"], Kp["R"])) if on else "  "
        tinta = (Kp["C"] + Kp["BO"]) if on else (
            Kp.get(items[i][3], Kp["GREY"]) if len(items[i]) > 3 and items[i][3] else Kp["GREY"])
        m = (" %s%s%s" % (mcol, marca, Kp["R"])) if marca else ""
        lab = HL.clip(str(txt), max(1, iw_l - 2 - HL.vis(m)))
        if HL.vis(marca) > 1:
            # una palabra de estado («listo», «sin sesión») va a la DERECHA
            hueco = max(1, iw_l - 2 - HL.vis(lab) - HL.vis(marca))
            m = " " * hueco + "%s%s%s" % (mcol, marca, Kp["R"])
        fila = "%s%s%s%s%s" % (cur, tinta, lab, Kp["R"], m)
        if on and sel_tail:
            fila = HL.pad(fila, iw_l) + " %s%s%s" % (Kp["C"] + Kp["BO"], sel_tail, Kp["R"])
        out.append(HL.clip(fila, iw))
    if abajo:
        out.append("%s▼ %s%s" % (Kp["DIM"], _t("sbox.more", "{n} más", "{n} more", n=abajo),
                                 Kp["R"]))
    return out


#: Ancho de la separación entre columnas: aire + regla + aire («  │  »).
SPLIT_GAP = 5


def split(Kp, left, right, iw, lw, marks=None):
    """Dos columnas dentro de la caja: `left` (lw columnas) │ `right`. El
    alto es el de la más larga; la regla vertical va tenue. `marks` =
    {fila: glifo}: en esa fila la regla se cambia por el glifo en acento (p.
    ej. «▸» = → pasa a la derecha, «◂» = ← regresa a la izquierda)."""
    Kp = HL.cols(Kp)
    rw = max(1, iw - lw - SPLIT_GAP)
    marks = marks or {}
    out = []
    for i in range(max(len(left), len(right))):
        a = HL.pad(HL.clip(left[i] if i < len(left) else "", lw), lw)
        b = HL.clip(right[i] if i < len(right) else "", rw)
        sep = ("%s%s%s" % (Kp["C"] + Kp["BO"], marks[i], Kp["R"]) if i in marks
               else "%s│%s" % (Kp["B2"], Kp["R"]))
        out.append("%s  %s  %s" % (a, sep, b))
    return out


def stack(Kp, top, bottom, iw, label="", active=False):
    """Formato VERTICAL (pedido del dueño): `top` (la lista), una regla con
    `label` (brillante si la parte de abajo tiene el foco) y `bottom` (las
    opciones del elegido). Caja angosta, sin columnas lado a lado."""
    Kp = HL.cols(Kp)
    if label:
        col = (Kp["C"] + Kp["BO"]) if active else Kp["DIM"]
        regla = "%s── %s%s%s %s%s%s" % (Kp["DK"], col, label, Kp["R"], Kp["DK"],
                                       Kp["SEP"] * max(1, iw - HL.vis(label) - 4), Kp["R"])
    else:
        regla = "%s%s%s" % (Kp["DK"], Kp["SEP"] * iw, Kp["R"])
    return list(top) + ["", HL.clip(regla, iw)] + list(bottom)


def switch(Kp, on):
    """Interruptor visual: `━━●` encendido (en acento) · `○━━` apagado."""
    Kp = HL.cols(Kp)
    if on:
        return "%s━━●%s" % (Kp["OK"] + Kp["BO"], Kp["R"])
    return "%s○━━%s" % (Kp["DK"], Kp["R"])


# ── el cuadro de `i` ─────────────────────────────────────────────────────────
def info_chips():
    return [("↑↓", _t("sbox.k.scroll", "desplaza", "scroll")),
            ("i · Esc", _t("sbox.k.close", "cierra", "close"))]


def info_frame(Kp, w, h, word, title, blocks, state=None, box_w=None):
    """El cuadro de explicación: misma caja, contenido didáctico. `state` =
    S["info"] de la sección; su "scroll" (primera fila visible) se ajusta al
    rango real aquí, así ↑ responde al instante aunque se haya bajado de más."""
    Kp = HL.cols(Kp)
    state = state if isinstance(state, dict) else {}
    _pw, iw = widths(w, box_w or 62)
    lines = render_blocks(Kp, blocks, iw)
    out = frame(Kp, w, h, word, title, lines, info_chips(),
                box_w=box_w or 62, scroll=state.get("scroll", 0))
    state["scroll"] = max(0, min(state.get("scroll", 0), frame.last_max_scroll))
    return out


def info_key(S, key):
    """Maneja `i`/`?` (abrir/cerrar) y, con el cuadro abierto, ↑↓/Esc/q.
    True = la tecla era del cuadro (la sección no debe procesarla)."""
    inf = S.get("info")
    if inf:
        if key in INFO_KEYS or key in ("\x1b", "q", "Q", "\x03"):
            S.pop("info", None)
        elif key in ("up", "k"):
            inf["scroll"] = max(0, inf.get("scroll", 0) - 1)
        elif key in ("down", "j", " "):
            inf["scroll"] = inf.get("scroll", 0) + 1
        return True
    if key in INFO_KEYS:
        S["info"] = {"scroll": 0}
        S["msg"] = ""
        return True
    return False


# ── bloques didácticos ───────────────────────────────────────────────────────
def _wrap(txt, w):
    pal, ln, out = str(txt).split(), "", []
    for p in pal:
        if ln and HL.vis(ln) + 1 + HL.vis(p) > w:
            out.append(ln)
            ln = p
        else:
            ln = (ln + " " + p) if ln else p
    if ln:
        out.append(ln)
    return out or [""]


def flow(Kp, nodes, iw):
    """Mapa de flujo: nodos en cajitas unidos por flechas, cada uno con su
    nota debajo. Horizontal si cabe; si no, vertical con ▼. `nodes` =
    [(nodo, nota), …]."""
    Kp = HL.cols(Kp)
    box = Kp["BOX"]
    tl, tr, bl, br, v, hh = box[0], box[1], box[2], box[3], box[4], box[5]
    flecha = " ──► "
    anchos = [HL.vis(n) + 2 for n, _c in nodes]
    total = sum(a + 2 for a in anchos) + HL.vis(flecha) * (len(nodes) - 1)
    col = [Kp["WCOL"][i % len(Kp["WCOL"])] + Kp["BO"] for i in range(len(nodes))]
    if total <= iw:
        r0, r1, r2 = [], [], []
        for i, ((n, _c), a) in enumerate(zip(nodes, anchos)):
            sep = flecha if i else ""
            gap = " " * HL.vis(flecha) if i else ""
            r0.append(gap + "%s%s%s%s%s" % (Kp["B2"], tl, hh * a, tr, Kp["R"]))
            r1.append("%s%s%s%s%s %s %s%s%s" % (Kp["DIM"], sep, Kp["R"], Kp["B2"], v,
                                               col[i] + n, Kp["R"] + Kp["B2"], v,
                                               Kp["R"]))
            r2.append(gap + "%s%s%s%s%s" % (Kp["B2"], bl, hh * a, br, Kp["R"]))
        out = ["".join(r0), "".join(r1), "".join(r2)]
        # notas: cada una centrada bajo su nodo (3 filas como mucho)
        # cada nota se envuelve al ancho de SU cajita: no invade la siguiente
        notas = [_wrap(c, a + 2)[:3] for (_n, c), a in zip(nodes, anchos)]
        for fila in range(max(len(x) for x in notas)):
            ln = ""
            for i, a in enumerate(anchos):
                slot = a + 2 + (HL.vis(flecha) if i < len(anchos) - 1 else 0)
                txt = notas[i][fila] if fila < len(notas[i]) else ""
                celda = " " * max(0, (a + 2 - HL.vis(txt)) // 2) + txt
                ln += HL.pad("%s%s%s" % (Kp["DIM"], celda, Kp["R"]), slot)
            out.append(ln.rstrip())
        lp = " " * max(0, (iw - total) // 2)
        return [HL.clip(lp + ln, iw) for ln in out]
    out = []
    for i, ((n, c), a) in enumerate(zip(nodes, anchos)):
        lp = " " * max(0, (iw - a - 2) // 2)
        out.append(lp + "%s%s%s%s%s" % (Kp["B2"], tl, hh * a, tr, Kp["R"]))
        out.append(lp + "%s%s%s %s%s %s%s%s" % (Kp["B2"], v, Kp["R"], col[i], n,
                                               Kp["R"], Kp["B2"] + v, Kp["R"]))
        out.append(lp + "%s%s%s%s%s" % (Kp["B2"], bl, hh * a, br, Kp["R"]))
        for sub in _wrap(c, iw)[:3]:
            out.append(_center("%s%s%s" % (Kp["DIM"], sub, Kp["R"]), iw))
        if i < len(nodes) - 1:
            out.append(_center("%s▼%s" % (Kp["C"] + Kp["BO"], Kp["R"]), iw))
    return [HL.clip(x, iw) for x in out]


def render_blocks(Kp, blocks, iw):
    """Bloques → líneas. Tipos:
      ("h", texto)            subtítulo con regla (en el color del tema)
      ("p", texto)            párrafo
      ("dim", texto)          párrafo tenue (letra chica)
      ("code", texto)         texto EXACTO (lo que viaja / lo que se escribe)
      ("list", [textos])      viñetas
      ("kv", [(tecla, qué)])  pares tecla → qué hace
      ("flow", [(nodo, nota)]) mapa de flujo
      ("lines", fn(iw))       líneas ya pintadas por la sección
      ("gap",)                una línea en blanco"""
    Kp = HL.cols(Kp)
    out = []
    ntit = 0
    for b in blocks:
        kind = b[0]
        if kind == "gap":
            out.append("")
        elif kind == "h":
            if out and out[-1] != "":
                out.append("")
            col = Kp["WCOL"][ntit % len(Kp["WCOL"])] + Kp["BO"]
            ntit += 1
            regla = Kp["SEP"] * max(1, iw - HL.vis(b[1]) - 1)
            out.append(HL.clip("%s%s%s %s%s%s" % (col, b[1], Kp["R"], Kp["DK"], regla,
                                                   Kp["R"]), iw))
        elif kind in ("p", "dim"):
            tinta = Kp["DIM"] if kind == "dim" else Kp["GREY"]
            out += ["%s%s%s" % (tinta, ln, Kp["R"]) for ln in _wrap(b[1], iw)]
        elif kind == "code":
            out += ["%s%s%s" % (Kp["OK"], ln, Kp["R"]) for ln in _wrap(b[1], iw - 2)]
        elif kind == "list":
            for it in b[1]:
                for n, ln in enumerate(_wrap(it, iw - 2)):
                    out.append("%s%s%s %s%s%s" % (Kp["DK"], "·" if n == 0 else " ",
                                                   Kp["R"], Kp["GREY"], ln, Kp["R"]))
        elif kind == "kv":
            kw = max([HL.vis(k) for k, _v in b[1]] + [1]) + 2
            for k, val in b[1]:
                sub = _wrap(val, max(8, iw - kw))
                out.append("%s%s%s%s%s%s" % (Kp["C"] + Kp["BO"], HL.pad(k, kw), Kp["R"],
                                             Kp["GREY"], sub[0], Kp["R"]))
                for s in sub[1:]:
                    out.append(" " * kw + "%s%s%s" % (Kp["GREY"], s, Kp["R"]))
        elif kind == "flow":
            if out and out[-1] != "":
                out.append("")
            out += flow(Kp, b[1], iw)
        elif kind == "lines":
            out += list(b[1](iw))
    return [HL.clip(x, iw) for x in out]


# ── teclas (los bucles de Decisores, Modelos de decisión y Motores) ─────────
#: Secuencias CSI / SS3 que entienden estas pantallas.
_SECUENCIAS = {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left", b"[Z": "right_tab",
               b"OA": "up", b"OB": "down", b"OC": "right", b"OD": "left"}


class KeyReader:
    """Lee teclas de una terminal en modo crudo, con su propio búfer:

      · UTF-8 completo (acentos, ñ, ¿) aunque llegue partido;
      · flechas y Shift-Tab (CSI «ESC [ …» y SS3 «ESC O …»); una secuencia
        que no se entiende (p. ej. el pegado «ESC [200~») se descarta ENTERA;
      · un Esc SOLO seguido de otra tecla en la misma lectura (Esc y luego
        «v», tecleados rápido o mientras la pantalla iba atrasada) son DOS
        teclas: "\\x1b" y luego la otra — nunca una secuencia perdida;
      · pending(): ¿quedan teclas por leer? (para no redibujar a media
        ráfaga: pegar 60 letras es UN dibujo, no 60).
    `read` y `ready` se pueden cambiar (pruebas)."""

    def __init__(self, fd, read=None, ready=None):
        import os as _os
        import select as _select
        self.fd = fd
        self.buf = b""
        self._read = read or (lambda n: _os.read(fd, n))
        self._ready = ready or (lambda t: bool(_select.select([fd], [], [], t)[0]))

    def _fill(self, timeout):
        if self._ready(timeout):
            data = self._read(1024)
            if data:
                self.buf += data
                return True
        return False

    def pending(self):
        return bool(self.buf) or self._ready(0)

    def get(self, timeout):
        """La siguiente tecla, "" (secuencia que no aplica) o None (nada en
        `timeout` segundos)."""
        if not self.buf and not self._fill(timeout):
            return None
        b0 = self.buf[0]
        if b0 == 0x1B:
            if len(self.buf) == 1:
                self._fill(0.04)                       # ¿viene el resto de una secuencia?
            if len(self.buf) >= 2 and self.buf[1:2] in (b"[", b"O"):
                i = 2
                while True:
                    if i >= len(self.buf) and not self._fill(0.04):
                        break
                    if i >= len(self.buf):
                        break
                    c = self.buf[i]
                    if 0x40 <= c <= 0x7E and not (self.buf[1:2] == b"[" and c == 0x5B and i == 2):
                        break
                    i += 1
                seq, self.buf = self.buf[1:i + 1], self.buf[i + 1:]
                return _SECUENCIAS.get(bytes(seq), "")
            self.buf = self.buf[1:]                    # Esc solo: su propia tecla
            return "\x1b"
        n = 1 if b0 < 0xC0 else 2 if b0 < 0xE0 else 3 if b0 < 0xF0 else 4
        while len(self.buf) < n and self._fill(0.04):
            pass
        ch, self.buf = self.buf[:n].decode("utf-8", "replace"), self.buf[n:]
        return "tab" if ch == "\t" else ch


# ── teclas en Windows (consola o ConPTY por SSH) ─────────────────────────────
#: Teclas virtuales que entienden estas pantallas.
_VK = {0x26: "up", 0x28: "down", 0x25: "left", 0x27: "right"}
_VK_TAB, _VK_MENU = 0x09, 0x12
_SHIFT_PRESSED = 0x0010
_KEY_EVENT = 0x0001


def win_key_events(records):
    """Las teclas de una lista de registros de consola (KEY_EVENT_RECORD como
    tuplas (abajo, repeticiones, vk, carácter, estado)). Pura: la prueban
    los tests sin Windows. Lo que msvcrt.getwch() pierde:

      · ¿ ¡ « » € por SSH (ConPTY) llegan como Alt + teclado numérico y el
        carácter viene SOLO al SOLTAR Alt (getwch ignora las teclas soltadas);
      · Shift-Tab es Tab con SHIFT en el estado (getwch da «\\t» y ya);
      · «à» es «\\xe0», el mismo prefijo de las flechas en getwch.
    """
    out, alto = [], None
    for abajo, rep, vk, ch, estado in records:
        ch = ch if ch and ch != "\x00" else ""
        if abajo:
            if vk in _VK:
                out += [_VK[vk]] * max(1, rep)
                continue
            if vk == _VK_TAB:
                out += ["right_tab" if estado & _SHIFT_PRESSED else "tab"] * max(1, rep)
                continue
            if not ch:
                continue
        elif not (vk == _VK_MENU and ch):           # soltar Alt con carácter: Alt+numpad
            continue
        o = ord(ch)
        if 0xD800 <= o <= 0xDBFF:                    # emoji: mitad alta, espera la baja
            alto = ch
            continue
        if 0xDC00 <= o <= 0xDFFF and alto:
            ch, alto = (alto + ch).encode("utf-16", "surrogatepass").decode("utf-16"), None
        out += [ch] * (max(1, rep) if abajo else 1)
    return out


class WinKeyReader:
    """Lee la consola de Windows con ReadConsoleInputW (ver win_key_events);
    si no se puede (sin ctypes o sin consola), cae a msvcrt.getwch() con el
    caso «à» ≠ prefijo de flecha resuelto. get(timeout) → tecla, "" o None;
    pending() → ¿hay más teclas ya esperando? (un dibujo por ráfaga)."""

    def __init__(self):
        self.queue = []
        self.k32 = None
        try:
            import ctypes
            from ctypes import wintypes

            class KEY(ctypes.Structure):
                _fields_ = [("bKeyDown", wintypes.BOOL), ("wRepeatCount", wintypes.WORD),
                            ("wVirtualKeyCode", wintypes.WORD), ("wVirtualScanCode", wintypes.WORD),
                            ("uChar", wintypes.WCHAR), ("dwControlKeyState", wintypes.DWORD)]

            class EVENT(ctypes.Union):
                _fields_ = [("KeyEvent", KEY), ("_pad", ctypes.c_byte * 16)]

            class RECORD(ctypes.Structure):
                _fields_ = [("EventType", wintypes.WORD), ("Event", EVENT)]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            h = k32.GetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF))
            n = wintypes.DWORD()
            if not k32.GetNumberOfConsoleInputEvents(h, ctypes.byref(n)):
                raise OSError("no es una consola")
            self.ctypes, self.wintypes, self.RECORD, self.k32, self.h = ctypes, wintypes, RECORD, k32, h
        except Exception:
            self.k32 = None

    def _eventos(self):
        if self.k32 is None:
            return 0
        n = self.wintypes.DWORD()
        if not self.k32.GetNumberOfConsoleInputEvents(self.h, self.ctypes.byref(n)):
            return 0
        return n.value

    def pending(self):
        if self.queue:
            return True
        if self.k32 is None:
            try:
                import msvcrt
                return bool(msvcrt.kbhit())
            except Exception:
                return False
        return self._eventos() > 0

    def _leer(self, timeout):
        """Registros de la consola (espera hasta `timeout`)."""
        if self.k32.WaitForSingleObject(self.h, int(max(0.0, timeout) * 1000)) != 0:
            return None
        n = max(1, min(64, self._eventos()))
        buf = (self.RECORD * n)()
        leidos = self.wintypes.DWORD()
        if not self.k32.ReadConsoleInputW(self.h, buf, n, self.ctypes.byref(leidos)):
            return []
        regs = []
        for r in buf[:leidos.value]:
            if r.EventType == _KEY_EVENT:
                k = r.Event.KeyEvent
                regs.append((bool(k.bKeyDown), int(k.wRepeatCount), int(k.wVirtualKeyCode),
                             k.uChar, int(k.dwControlKeyState)))
        return regs

    def _getwch(self, timeout):
        import msvcrt
        import time as _time
        t0 = _time.time()
        while not msvcrt.kbhit():
            if _time.time() - t0 >= timeout:
                return None
            _time.sleep(0.02)
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            if ch == "\xe0" and not msvcrt.kbhit():
                return "\xe0"                          # «à» de verdad, no un prefijo
            a = msvcrt.getwch()
            return {"H": "up", "P": "down", "M": "right", "K": "left"}.get(a, "")
        return "tab" if ch == "\t" else ch

    def get(self, timeout):
        if self.queue:
            return self.queue.pop(0)
        if self.k32 is None:
            return self._getwch(timeout)
        regs = self._leer(timeout)
        if regs is None:
            return None
        self.queue = win_key_events(regs)
        return self.queue.pop(0) if self.queue else ""
