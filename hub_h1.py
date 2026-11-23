#!/usr/bin/env python3
r"""WORKSPACE · hub_h1 — H-1 «Marco relleno» y el hub que se acomoda al ancho (Terminal R2, la versión de Zenith).
SOLO PARA PROBAR: vive en la rama zenith/hub-h1 y nunca entra a main.

El material: los planos de Bloque (hub_bloque) con una línea de caja encima y el título en el borde
(╭─ Zenith  Codex ▾ ───── trabajando… ─╮). El área activa (la conversación o la sección) lleva su borde del color del
agente a media fuerza; lo elegido, una ┃ del agente sobre el borde.

Por ancho (los cortes del diseño):
  · ≥190 «Grande»: el riel con nombres, la conversación (hasta ~96 columnas, a la izquierda) y el panel ancho;
  · 150-189: el riel compacto (o con nombres si lo abriste), la conversación y el panel del agente: su motor ▾, su
    modelo (solo abre la config de su motor), su conexión, sus 3 últimas sesiones, 3 skills, lo que va haciendo y
    «Abrir en su motor ↗». Sin barra arriba: Ajustes, Ayuda y Salir van al pie del riel;
  · 101-149: el panel se vuelve una franja de íconos con cuentas y su globo; un clic abre el panel encima de la
    conversación (el cajón);
  · ≤100: la barra de arriba de hoy, con sus menús.
Las secciones (Sesiones, Skills, Motores…) siguen a pantalla completa (las piezas de hub_secciones en un marco H-1).

Aquí se dibuja; qué hace cada tecla o clic está en hub_directo.Directo. Los monitos, solo por hub_monitos. Stdlib."""
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_paleta as P  # noqa: E402
import hub_directo as D  # noqa: E402
import hub_bloque as B  # noqa: E402
import hub_monitos as MON  # noqa: E402

C, ERR = P.C, P.ERR
W, corto = B.W, B.corto
BG, P1, P2, P3, P4 = B.BG, B.P1, B.P2, B.P3, B.P4
LUZ, LUZTX, OFF, OK, WARN = B.LUZ, B.LUZTX, B.OFF, B.OK, B.WARN
LN = "#484853"          # la línea de las cajas
LN_SOBRE = "#60606b"    # la línea con el mouse encima (el borde del riel)

#: Los cortes por ancho: desde GRANDE el riel con nombres y el panel ancho; desde CON_PANEL el panel; desde
#: CON_FRANJA la franja de íconos; abajo, la barra de arriba.
GRANDE, CON_PANEL, CON_FRANJA = 190, 150, 101
RIEL_C, RIEL_N = 14, 34
PANEL_L, PANEL_XL, FRANJA, CAJON = 40, 48, 9, 42
CHAT_MAX = 96
#: En la pantalla angosta: con menos de ANCHO_RIEL columnas no hay riel; el riel con nombres, desde ANCHO_NOMBRES.
ANCHO_RIEL, ANCHO_NOMBRES = 80, 96
TITULOS = {"sesiones": "Sesiones", "skills": "Skills", "motores": "Motores", "ajustes": "Ajustes",
           "agentes": "Agentes", "ayuda": "Ayuda", "calendario": "Calendario", "conexiones": "Conexiones"}
BARRA_S = (("inicio", "⌂ Inicio"), ("agentes", "Agentes ▾"), ("motor", "Motor ▾"), ("skills", "Skills ▾"),
           ("abrir", "Abrir ↗"))
BARRA_S_DER = (("ajustes", "Ajustes"), ("ayuda", "?"), ("salir", "✕"))


def nivel(w):
    """«XL» (≥190), «L» (150-189), «M» (101-149) o «S» (≤100)."""
    return "XL" if w >= GRANDE else ("L" if w >= CON_PANEL else ("M" if w >= CON_FRANJA else "S"))


def foco_col(a, fondo):
    """El borde del área activa: el color del agente a media fuerza sobre su fondo."""
    return P.mix(a["c"], fondo, 0.42)


# ── las medidas ───────────────────────────────────────────────────────────────
def geometria(w, h, s=None):
    """Dónde va cada cosa en una terminal de w×h: {nivel, barra, riel, conv, panel, franja, cajon, seccion} (cada
    área, (x, y, ancho, alto) o None), si el riel lleva nombres y si lleva la marca y su pie (Ajustes, Ayuda,
    Salir). `s`: riel_nombres (None: el de su ancho), riel_w (mientras se arrastra), panel_cerrado, cajon."""
    s = s or {}
    nv = nivel(w)
    G = {"nivel": nv, "w": w, "h": h, "barra": None, "riel": None, "panel": None, "franja": None, "cajon": None}
    pref = s.get("riel_nombres")
    nombres = (nv == "XL") if pref is None else (bool(pref) and w >= ANCHO_NOMBRES)
    if s.get("sin_riel"):                             # una sección abierta desde Inicio: a todo lo ancho
        G.update(nombres=False, marca=False, conv=(1, 1, w - 2, h - 2), seccion=(1, 1, w - 2, h - 2),
                 bw=min(CHAT_MAX, w - 8), bx=4, y_caja=h - 6, y_teclas=h - 2, y_conv=3)
        return G
    if nv == "S":
        top = 4
        G["barra"] = (1, 0, w - 2, 3)
        con_riel = w >= ANCHO_RIEL
    else:
        top, con_riel = 1, True
    alto = h - top - 1
    RW = 0
    if con_riel:
        RW = RIEL_N if nombres else RIEL_C
        if s.get("riel_w") is not None:
            RW = max(RIEL_C, min(RIEL_N, int(s["riel_w"]) - 1, w - 60))
        G["riel"] = (1, top, RW, alto)
    G["nombres"] = RW >= 30
    G["marca"] = nv != "S"
    xc = RW + 2 if RW else 1
    xr = w - 1
    if nv in ("XL", "L") and not s.get("panel_cerrado"):
        pw = PANEL_XL if nv == "XL" else PANEL_L
        G["panel"] = (w - 1 - pw, top, pw, alto)
        xr = w - 1 - pw - 1
    elif nv != "S":
        G["franja"] = (w - 1 - FRANJA, top, FRANJA, alto)
        xr = w - 1 - FRANJA - 1
        if s.get("cajon"):
            G["cajon"] = (max(xc, xr - CAJON), top, min(CAJON, xr - xc), alto)
    G["conv"] = (xc, top, xr - xc, alto)
    G["seccion"] = (xc, top, w - 1 - xc, alto)
    x, y, cw, ch = G["conv"]
    iw = cw - 2
    G["bw"] = min(CHAT_MAX, iw - 4) if RW else iw - 2
    G["bx"] = x + 3 if RW else x + 2
    G["y_caja"], G["y_teclas"], G["y_conv"] = y + ch - 5, y + ch - 1, y + 2
    return G


# ── el material H-1 ───────────────────────────────────────────────────────────
def segs(L, x, y, partes, fondo, zonas=None, limite=None):
    """Pedazos de un título: (texto, color, negrita[, rid]). Con rid y color None es una ficha que se toca (el motor
    ▾); con rid y color, un enlace (su fondo se ilumina con el mouse). → la columna siguiente."""
    T = L.T
    for p in partes:
        t, fg, b = p[0], p[1], p[2]
        rid = p[3] if len(p) > 3 else None
        if limite is not None:
            if x >= limite:
                break
            if W(t) > limite - x:                     # corto() junta los espacios: solo si no cabe
                t = corto(t, limite - x)
        if rid:
            hov = L.reg(x, y, W(t), 1, rid)
            apr = L.apr(rid)
            if fg is None:
                bg = P4 if (apr or hov) else (P2 if fondo != P2 else P3)
                fg2 = C["tx"] if hov else C["tx2"]
            else:
                bg = P4 if apr else (P3 if hov else fondo)
                fg2 = C["tx"] if hov else fg
            if zonas is not None:
                zonas[rid] = (x, W(t))
            x = T.put(x, y, t, fg2, b, bg)
        else:
            x = T.put(x, y, t, fg, b, fondo)
    return x


def area(L, x, y, w, h, fondo=P1, titulo=None, der=None, foco_a=None, linea=None):
    """Un área H-1: el plano `fondo` con su línea de caja; el título va en el borde de arriba (a la izquierda) y
    `der`, a la derecha. `foco_a`: el área activa (su borde, del color del agente a media fuerza). → {rid: (x, ancho)}
    de lo que se toca en el borde (para que bajen de ahí sus menús)."""
    T = L.T
    zonas = {}
    if w < 2 or h < 2:
        return zonas
    col = linea or (foco_col(foco_a, fondo) if foco_a else LN)
    T.fill(x, y, w, h, fondo)
    T.put(x, y, "╭" + "─" * (w - 2) + "╮", col, False, fondo)
    for j in range(1, h - 1):
        T.put(x, y + j, "│", col, False, fondo)
        T.put(x + w - 1, y + j, "│", col, False, fondo)
    T.put(x, y + h - 1, "╰" + "─" * (w - 2) + "╯", col, False, fondo)
    fin = x + 2
    if titulo:
        xx = T.put(x + 2, y, " ", None, False, fondo)
        xx = segs(L, xx, y, titulo, fondo, zonas, limite=x + w - 3)
        fin = T.put(xx, y, " ", None, False, fondo)
    if der:
        ancho = sum(W(p[0]) for p in der) + 2
        x1 = x + w - 2 - ancho
        if x1 > fin:
            T.put(x1, y, " ", None, False, fondo)
            segs(L, x1 + 1, y, der, fondo, zonas)
            T.put(x1 + ancho - 1, y, " ", None, False, fondo)
    return zonas


def marca_sel(T, x, y, h, a, fondo):
    """Lo elegido: una ┃ del agente sobre la línea del borde."""
    for j in range(h):
        T.put(x, y + j, "┃", a["c"], False, fondo)


def sub_titulo(L, x0, x1, y, ix, iw, titulo, der=None, rid=None, fondo=P1):
    """Un título dentro de un área: una junta ├─ título ───── der ─┤ de borde a borde (x0..x1)."""
    T = L.T
    T.put(x0, y, "├" + "─" * (x1 - x0 - 1) + "┤", LN, False, fondo)
    xx = T.put(ix, y, " ", None, False, fondo)
    xx = T.put(xx, y, corto(titulo, iw - (W(der) + 4 if der else 0)), C["tx2"], True, fondo)
    T.put(xx, y, " ", None, False, fondo)
    if der:
        t = " %s " % der
        xd = ix + iw - W(t) + 1
        hov = L.reg(xd, y, W(t), 1, rid) if rid else False
        T.put(xd, y, t, C["tx"] if hov else C["tx3"], False, P4 if L.apr(rid) else (P3 if hov else fondo))


def teclas_borde(T, x, y, xmax, ks, fondo=BG):
    """Las teclas en el borde de abajo: « Enter manda · Esc para · F1 ayuda ». → la columna siguiente."""
    xx = T.put(x, y, " ", None, False, fondo)
    puestas = 0
    for k, lab in ks:
        need = W(k) + (1 + W(lab) if lab else 0) + (3 if puestas else 0) + 1
        if xx + need > xmax:
            break
        if puestas:
            xx = T.put(xx, y, " · ", C["tx3"], False, fondo)
        xx = T.put(xx, y, k, C["tx2"], True, fondo)
        if lab:
            xx = T.put(xx, y, " " + lab, C["tx3"], False, fondo)
        puestas += 1
    return T.put(xx, y, " ", None, False, fondo)


def agente(s):
    return B.agente(s)


def marcar_foco(T, s):
    """El foco se ve: lo enfocado ya se ilumina como con el mouse encima; aquí, además, sus corchetes ▐ ▌ del color
    del agente (salvo lo que ya lo dice: la caja de escribir, la fila elegida, el monito del riel, una tarjeta)."""
    f = s.get("foco") or ""
    if not f or f == "in:texto" or f.startswith(("sr:", "ini:card:", "ini:sec:")) or \
            (f.startswith("riel:") and f[5:].isdigit()):
        return
    z = next((z for z in T.zonas if z[4] == f), None)
    if z is None:
        return
    x, y, w, h, _r = z
    col = agente(s)["c"]
    for j in range(h):
        for xx, ch in ((x - 1, "▐"), (x + w, "▌")):
            if 0 <= xx < T.w and 0 <= y + j < T.h:
                c = T.at(xx, y + j)
                T.put(xx, y + j, ch, col, False, c.bg or BG)


def teclas_conv(s):
    """Las teclas del área enfocada de la conversación (lo mismo que Ayuda › Las teclas)."""
    area = s.get("foco_area") or "chat"
    if area == "riel":
        return [("↑↓", "agente"), ("←→", "su motor"), ("Enter", "escribir"), ("Tab", "otra área"), ("Esc", "Inicio"),
                ("q", "sale")]
    if area in ("panel", "franja", "barra"):
        return [("↑↓←→", "elige"), ("Enter", "hace"), ("Tab", "otra área"), ("Esc", "a la caja"), ("q", "sale")]
    if area == "chat" and s.get("foco") not in ("in:texto", "", None):
        return [("↑↓←→", "elige"), ("Enter", "hace"), ("Tab", "otra área"), ("Esc", "a la caja")]
    ks = [(k, "sale de la caja" if (k == "Esc" and lab == "sale") else lab) for k, lab in B.teclas(s)]
    return ks[:-1] + [("^E", "su motor"), ("^T", "pestaña"), ("Tab", "otra área")] + ks[-1:]


# ── el riel ───────────────────────────────────────────────────────────────────
def cabe_riel(G):
    """(primera fila de agentes, cuántos caben) en el riel de G."""
    x, y, RW, alto = G["riel"]
    y0 = y + (4 if G["marca"] else 2)
    lim = y + alto - (9 if G["marca"] else 2)
    return y0, max(1, (lim - 5 - y0) // 6 + 1)


def riel(L, s, G):
    """El riel en su caja: «❯ workspace» arriba, los monitos (el elegido en P3 con la ┃ del agente sobre el borde), y
    al pie «+ Agregar», Ajustes, ? Ayuda y ✕ Salir (en la angosta, solo lo de agregar: lo demás está en la barra).
    → {índice: fila} de los que se ven (para el globo)."""
    T, ag, sel = L.T, s["agentes"], s["sel"]
    x, y, RW, alto = G["riel"]
    marca = G["marca"]
    nombres = G["nombres"]
    a = agente(s)
    area(L, x, y, RW, alto, P1, foco_a=a if s.get("foco_area") == "riel" else None)
    L.reg(x, y, RW, alto, "riel")                    # la rueda sobre el riel (los agentes, encima, ganan)
    ix = x + 1
    if marca:                                         # la marca se toca: Inicio
        hm = L.reg(ix, y + 1, RW - 2, 1, "nav:inicio")
        if hm:
            B.bloque(T, ix, y + 1, RW - 2, 1, P2, P1)
        xx = T.put(ix + 1, y + 1, "❯", a["c"], True, P2 if hm else P1)
        T.put(xx + 1, y + 1, corto("workspace", x + RW - 2 - xx), C["tx"], True, P2 if hm else P1)
    y0, cabe = cabe_riel(G)
    n = len(ag)
    if n <= cabe:
        i0 = 0
    elif s.get("riel0") is None:
        i0 = max(0, min(sel - cabe // 2, n - cabe))
    else:
        i0 = max(0, min(int(s["riel0"]), n - cabe))
    vis = list(range(i0, min(n, i0 + cabe)))
    pos = {}
    for k, i in enumerate(vis):
        yk = y0 + 6 * k
        pos[i] = yk
        b = ag[i]
        on, rid = i == sel, "riel:%d" % i
        hov = L.reg(ix, yk, RW - 2, 5, rid)
        if on:
            B.bloque(T, ix, yk, RW - 2, 5, P3, P1)
            marca_sel(T, x, yk, 5, b, P1)
        elif hov or L.apr(rid):
            B.bloque(T, ix, yk, RW - 2, 5, P4 if L.apr(rid) else P2, P1)
        MON.dibujar(T, b, ix + 3, yk + 1, 8, s=s, st=b["st"])
        if nombres:
            tx, lim = ix + 13, x + RW - 2
            T.put(tx, yk + 1, corto(b["n"], lim - tx), C["tx"] if (on or hov) else C["tx2"], on)
            T.put(tx, yk + 2, corto("▲ %s ▼" % D.motor_riel(s, i, False), lim - tx), b["c"], True)
            t, col, bb = D.estado_riel(b, s.get("ahora"), corto=RW < 30)
            T.put(tx, yk + 3, corto(t, lim - tx), col, bb)
    if i0 > 0:
        hov = L.reg(ix, y0 - 1, RW - 2, 1, "riel:arriba")
        T.put(ix + 2, y0 - 1, corto("▲ %d más" % i0, RW - 4), C["tx"] if hov else C["tx3"], False, P1)
    resto = n - i0 - len(vis)
    primero = (("riel:abajo", "▼ %d más" % resto) if resto > 0 else
               ("riel:nuevo", "+ Agregar agente" if nombres else "+ Agregar"))
    sec = (s.get("seccion") or {}).get("kind")
    if marca:                                         # (? Guía: el recorrido de Inicio, H5-a)
        filas = [primero, None, ("nav:inicio", "⌂ Inicio"), ("bar:ajustes", "Ajustes"), ("bar:ayuda", "Ayuda  F1"),
                 ("bar:guia", "? Guía"), ("bar:salir", "✕ Salir")]
        yy = y + alto - 8
    else:
        filas, yy = [primero], y + alto - 2
    for f in filas:
        if f:
            rid, lab = f
            hov = L.reg(ix, yy, RW - 2, 1, rid)
            activo = rid.startswith("bar:") and rid[4:] == sec
            if hov or L.apr(rid) or activo:
                B.bloque(T, ix, yy, RW - 2, 1, P4 if L.apr(rid) else P3, P1)
            if activo:
                marca_sel(T, x, yy, 1, a, P1)
            fg = C["tx"] if (hov or activo) else (C["tx3"] if rid.startswith("riel:") else C["tx2"])
            T.put(ix + 2, yy, corto(lab, RW - 4), fg, activo)
        yy += 1
    T.riel = (i0, cabe, n)
    return pos


def borde(L, s, G):
    """El borde derecho del riel: se arrastra (o se toca) para abrir o cerrar el riel con nombres. Se apunta al final
    (gana sobre lo de al lado); con el mouse encima o arrastrándolo, su línea se ilumina con una agarradera."""
    T = L.T
    x, y, RW, alto = G["riel"]
    xb = x + RW - 1
    hov = L.reg(xb, y + 1, 2, alto - 2, "riel:borde")
    if hov or s.get("riel_w") is not None:
        col = C["tx3"] if (L.apr("riel:borde") or s.get("riel_w") is not None) else LN_SOBRE
        for j in range(1, alto - 1):
            T.put(xb, y + j, "│", col, False, P1)
        mid = y + alto // 2
        for j in (-1, 0, 1):
            T.put(xb, mid + j, "┃", C["tx"], False, P1)


# ── la barra de arriba (solo en la angosta) ───────────────────────────────────
def barra_botones(w, s=None):
    """Los botones de la barra angosta: ([(id, etiqueta, x, ancho)], con la palabra «workspace») o (None, True) si
    no caben ni con menos aire ni sin la palabra (un solo «≡ Menú ▾»)."""
    for con_marca, aire in ((True, 4), (True, 2), (False, 2)):
        x = 16 if con_marca else 6
        out = []
        for rid, lab in BARRA_S:
            wi = W(lab) + aire
            out.append((rid, lab, x, wi))
            x += wi + 1
        xr = w - 3
        dd = []
        for rid, lab in reversed(BARRA_S_DER):
            wi = W(lab) + aire
            xr -= wi
            dd.append((rid, lab, xr, wi))
            xr -= 1
        if xr >= x - 1:
            return out + dd[::-1], con_marca
    return None, True


def barra(L, s, G, a):
    """La barra de la pantalla angosta (≤100): «❯ workspace», Agentes ▾ Motor ▾ Sesiones ▾ Skills ▾ Abrir ↗ y a la
    derecha Ajustes ? ✕. El menú abierto, en video inverso; el mouse encima o su sección abierta, una ficha P3.
    → {menú: (x, ancho, a_la_derecha)}."""
    T = L.T
    x, y, w, h = G["barra"]
    area(L, x, y, w, h, P1)
    botones, con_marca = barra_botones(T.w, s)
    xx = T.put(3, 1, "❯", a["c"] if a else C["tx2"], True, P1)
    if con_marca:
        T.put(xx + 1, 1, "workspace", C["tx"], True, P1)
    ab = B.abierto(s)
    sec = (s.get("seccion") or {}).get("kind")
    anclas = {}
    if not a:
        botones = [("salir", "✕ Salir", T.w - 3 - 11, 11)]
    elif botones is None:
        lab = "≡ Menú ▾"
        botones = [("menu", lab, T.w - 3 - (W(lab) + 4), W(lab) + 4)]
    for rid, lab, xb, wi in botones:
        hov = L.reg(xb, 0, wi, 3, "bar:" + rid)
        apr = L.apr("bar:" + rid)
        pad = " " * max(0, (wi - W(lab) - 2) // 2)
        if ab == rid:
            B.ficha(T, xb, 1, pad + lab + pad, LUZ, P1, LUZTX, True)
        elif hov or apr or B.ACTIVO.get(sec) == rid:
            B.ficha(T, xb, 1, pad + lab + pad, P4 if apr else P3, P1, C["tx"], B.ACTIVO.get(sec) == rid)
        else:
            T.put(xb + 1 + len(pad), 1, lab, C["tx2"], False, P1)
        anclas[rid] = (xb, wi, rid in ("ajustes", "ayuda", "salir", "menu"))
    return anclas


# ── la conversación ───────────────────────────────────────────────────────────
def _estado_der(s, f):
    if s.get("hub_viejo"):
        return D.HUB_VIEJO, ERR
    if not s.get("conectado", True):
        return "sin conexión con la página", ERR
    if s.get("scroll"):
        return "viendo lo de antes · AvPág baja", C["tx3"]
    if s.get("pregunta") and not s.get("permiso"):
        return "te pregunta", C["tx3"]
    return D.ESTADO_T.get(f.get("estado"), ""), C["tx3"]


def caja(L, s, a, bx, bw, y):
    """La caja de escribir de Bloque con su línea de caja (del color del agente si contesta una pregunta)."""
    T = L.T
    B.caja_escribir(L, s, a, bx, bw, y)
    q = s.get("pregunta")
    enfocada = (s.get("foco") or "in:texto") == "in:texto"
    col = a["c"] if ((q and not q.get("en_terminal")) or (enfocada and s.get("foco"))) else LN
    if not enfocada and not s.get("texto"):          # sin el foco: cómo llegar a ella
        T.put(bx + 5, y + 1, corto("Tab: aquí se escribe", bw - 24), C["tx3"], False, P2)
    T.put(bx, y, "╭" + "─" * (bw - 2) + "╮", col, False, P2)
    T.put(bx, y + 1, "│", col, False, P2)
    T.put(bx + bw - 1, y + 1, "│", col, False, P2)
    T.put(bx, y + 2, "╰" + "─" * (bw - 2) + "╯", col, False, P2)


def _uso_conversacion(foto, motor):
    uso = foto.get("uso") or {}
    partes = []
    if uso.get("contexto") is not None:
        partes.append("Contexto %s%%" % uso["contexto"])
    ventana = uso.get("ventana")
    if ventana:
        minutos = ventana.get("minutos")
        duracion = "Ventana"
        if minutos:
            duracion = "%g h" % (minutos / 60) if minutos % 60 == 0 else "%g min" % minutos
        texto = "%s: %s%% libre" % (duracion, ventana["libre"])
        if ventana.get("reinicia") is not None:
            texto += time.strftime(" ↻ %d/%m %H:%M", time.localtime(ventana["reinicia"]))
        partes.append(texto)
    else:
        partes.append("%s no informa su límite" % D.nombre_motor(motor))
    if uso.get("semana_usada") is not None:
        partes.append("Semana %s%% usado" % uso["semana_usada"])
    for campo, etiqueta in (("tokens_turno", "turno"), ("tokens_sesion", "sesión")):
        if uso.get(campo) is not None:
            partes.append("%s tokens %s" % (uso[campo], etiqueta))
    return partes


# ── H4-a «pestañas en el borde» ───────────────────────────────────────────────
def glifo_tab(t, a):
    """El glifo de una pestaña y su color: ⌂ la de siempre; ● trabaja; ? te espera; ↗ abierta en su terminal; · lo
    demás."""
    if t.get("slug") == D.NAV:
        return "⌂", C["tx2"]
    est = t.get("estado")
    if est == "trabajando":
        return "●", a["c"]
    if est == "esperandote":
        return "?", a["c"]
    if t.get("terminal"):
        return "↗", C["tx3"]
    return "·", C["tx3"]


def _lab_tab(t, activa, n, a):
    nom = corto(t.get("nombre") or ("Conversación" if t.get("slug") == D.NAV else t.get("slug") or ""), n)
    g = glifo_tab(t, a)[0]
    return (" %s %s  × " if activa and t.get("slug") != D.NAV else " %s %s ") % (g, nom)


def tira(L, s, G, a, x0, x1):
    """Las pestañas de la conversación en el borde de arriba (donde iba «Zenith  Codex ▾»), de x0 a x1: la de siempre
    (⌂) y la que ves siempre se ven (la que ves, en su ficha con ×); las demás mientras quepan, el resto en «+N ▾», y
    al final «+». → {rid: (x, ancho)}."""
    T = L.T
    y = G["conv"][1]
    tabs = s.get("tira") or [{"slug": D.NAV, "nombre": "Conversación"}]
    act = s.get("tab") or D.NAV
    ia = next((i for i, t in enumerate(tabs) if t.get("slug") == act), 0)
    lim = x1 - 5                                       # «+»
    # los nombres: hasta 22 letras con lugar (16 en lo mediano, 11 en lo angosto), o más largos si así caben todas;
    # las que no caben van en «+N ▾»
    n0 = 22 if x1 - x0 >= 90 else (16 if x1 - x0 >= 56 else 11)
    n = next((m for m in (22, 16) if m > n0 and x0 + sum(W(_lab_tab(t, i == ia, m, a)) + (3 if i == ia else 1)
                                                         for i, t in enumerate(tabs)) <= lim), n0)

    def ancho(i):
        return W(_lab_tab(tabs[i], i == ia, n, a)) + (3 if i == ia else 1)
    vis = [0] + ([ia] if ia else [])
    usado = sum(ancho(i) for i in vis)
    resto = [i for i in range(1, len(tabs)) if i != ia]
    for k, i in enumerate(resto):
        quedan = len(resto) - k - 1
        reserva = W(" +%d ▾ " % quedan) + 3 if quedan else 0
        if x0 + usado + ancho(i) + reserva > lim:
            break
        vis.append(i)
        usado += ancho(i)
    fuera = [i for i in resto if i not in vis]
    while fuera and len(vis) > (2 if ia else 1) and x0 + usado + W(" +%d ▾ " % len(fuera)) + 3 > lim:
        quita = next(i for i in reversed(vis) if i not in (0, ia))
        vis.remove(quita)
        usado -= ancho(quita)
        fuera = [i for i in resto if i not in vis]
    zonas, xx = {}, x0
    for i, t in enumerate(tabs):
        if i not in vis:
            continue
        sl = t.get("slug") or D.NAV
        rid = "tb:t:" + sl
        g, gc = glifo_tab(t, a)
        lab = _lab_tab(t, i == ia, n, a)
        if i == ia:
            fo = L.reg(xx, y, W(lab) + 2, 1, rid)          # (con el foco del teclado encima, como el mouse)
            fin = B.ficha(T, xx, y, lab, P4 if fo else P2, BG, C["tx"], True)
            T.put(xx + 2, y, g, gc, True, P4 if fo else P2)
            if sl != D.NAV:
                rx = "tb:x:" + sl
                hx = L.reg(fin - 3, y, 1, 1, rx)
                T.put(fin - 3, y, "×", C["tx"] if hx else C["tx3"], hx, P4 if (hx or fo) else P2)
            zonas[rid] = (xx, fin - xx)
            xx = fin + 1
        else:
            hov = L.reg(xx, y, W(lab), 1, rid)
            T.put(xx, y, lab, C["tx"] if hov else C["tx2"], False, P3 if hov else BG)
            T.put(xx + 1, y, g, gc, True, P3 if hov else BG)
            zonas[rid] = (xx, W(lab))
            xx += W(lab) + 1
    if fuera:
        lab = " +%d ▾ " % len(fuera)
        hov = L.reg(xx, y, W(lab) + 2, 1, "tb:mas")
        fin = B.ficha(T, xx, y, lab, P3 if hov else P2, BG, C["tx"] if hov else C["tx2"])
        zonas["tb:mas"] = (xx, fin - xx)
        xx = fin + 1
    hov = L.reg(xx, y, 5, 1, "tb:nueva")
    fin = B.ficha(T, xx, y, " + ", P4 if (hov or L.apr("tb:nueva")) else P3, BG, C["tx"], True)
    zonas["tb:nueva"] = (xx, fin - xx)
    return zonas


def conversacion(L, s, G, a):
    """La conversación en su área: en el borde de arriba sus pestañas (H4-a: ⌂ la de siempre y sus sesiones abiertas)
    y su estado, del color del agente a media fuerza; el motor, en el panel (sin panel, al final del borde); los
    renglones a la izquierda (hasta ~96 columnas); lo del momento (aviso, permiso o pregunta, la skill que corre); la
    caja de escribir y las teclas en el borde de abajo. → {rid: (x, ancho)} del borde."""
    T, f = L.T, s.get("foto") or {}
    x, y, w, h = G["conv"]
    bx, bw, y_caja, y0 = G["bx"], G["bw"], G["y_caja"], G["y_conv"]
    der_t, der_c = _estado_der(s, f)
    der = [(der_t, der_c, False)] if der_t else []
    foco_a = a if (s.get("foco_area") or "chat") == "chat" else None
    if s.get("tira") is not None:
        zonas = area(L, x, y, w, h, BG, None, der or None, foco_a=foco_a)
        xr = x + w - 2 - ((sum(W(p[0]) for p in der) + 2) if der else 0)
        if not G.get("panel") and not G.get("barra"):    # sin panel: el motor al final del borde
            lab = " %s ▾ " % D.nombre_motor(f.get("motor") or a.get("mid"))
            cm = f.get("cambio")
            if cm and cm.get("paso") not in ("listo", "error") and cm.get("motor"):
                lab = " %s → %s ▾ " % (D.nombre_motor(f.get("motor") or a.get("mid")), D.nombre_motor(cm["motor"]))
            xm = xr - W(lab) - 1
            if xm > x + 30:
                segs(L, xm, y, [(lab, None, False, "hdr:motor")], BG, zonas)
                xr = xm - 1
        zonas.update(tira(L, s, G, a, x + 2, xr - 1))
    else:                                              # sin tira (la vista de antes): su nombre y su motor ▾
        titulo = [(corto(a["n"], 24), a["c"], True), (" ", C["tx3"], False),
                  (" %s ▾ " % D.nombre_motor(f.get("motor") or a.get("mid")), None, False, "hdr:motor")]
        cm = f.get("cambio")
        if cm and cm.get("paso") not in ("listo", "error") and cm.get("motor"):
            titulo.append((" → " + D.nombre_motor(cm["motor"]), C["tx2"], False))
        zonas = area(L, x, y, w, h, BG, titulo, der or None, foco_a=foco_a)
    L.reg(x + 1, y + 1, w - 2, max(0, y_caja - y - 1), "conv")
    abajo = []
    if s.get("aviso") and s.get("deshacer"):          # H4-a: «Cerré … No se borró» con su «Deshacer»
        def _aviso_deshacer(L_, s_, xx, yy):
            lab = " Deshacer "
            t = corto(s["aviso"], max(10, bw - W(lab) - 6))
            x1 = bx + max(1, (bw - W(t) - W(lab) - 4) // 2)
            fin = L_.T.put(x1, yy, t, C["tx2"])
            hov = L_.reg(fin + 2, yy, W(lab) + 2, 1, "tb:deshacer")
            B.ficha(L_.T, fin + 2, yy, lab, P4 if hov else P3, BG, C["tx"], True)
        abajo.append((1, _aviso_deshacer))
    elif s.get("aviso"):
        abajo.append((1, lambda L_, s_, xx, yy: L_.T.center(bx, bw, yy, corto(s["aviso"], bw - 2), C["tx2"])))
    otra_tab = (s.get("tab") or D.NAV) != D.NAV
    if (otra_tab and (f.get("solo_mirar") or f.get("terminal"))) or (not otra_tab and f.get("solo_mirar")):
        # H4-a: una sesión que aquí solo se mira, o que sigue abierta en su terminal: lo dice, con «Ir a la terminal».
        # También la de siempre si su motor no deja escribirle desde aquí (RC 0.10.0: Antigravity con cuenta personal)
        def _aviso_terminal(L_, s_, xx, yy):
            lab = " Ir a la terminal ↗ "
            t = f.get("solo_mirar") or "↗ También abierta en su terminal: escríbele ahí, o ciérrala para seguir aquí."
            xb = bx + bw - W(lab) - 3
            L_.T.put(bx + 1, yy, corto(t, max(10, xb - bx - 3)), C["tx2"])
            hov = L_.reg(xb, yy, W(lab) + 2, 1, "tb:terminal")
            B.ficha(L_.T, xb, yy, lab, P4 if hov else P3, BG, C["tx"], True)
        abajo.append((2, _aviso_terminal))
    if s.get("permiso"):
        alto_, dib = B.caja_permiso(s["permiso"], a, bw, s.get("elige") or 0)
        abajo.append((alto_ + 1, dib))
    elif s.get("pregunta"):
        alto_, dib = B.caja_pregunta(s["pregunta"], a, bw, s.get("elige") or 0)
        abajo.append((alto_ + 1, dib))
    e = D.vigente_en(s)
    pe = None if e else D.pendiente_en(s)            # skills-cierre: lo que quedó pendiente, aquí también con panel
    if (e and not G.get("panel")) or pe:             # con el panel a la vista, su proceso va ahí (P-1)
        alto_f, dib_f = D.franja_skill(e, a, bw) if e else D.franja_pendiente(pe, a, bw)
        abajo.append((alto_f, lambda L_, s_, xx, yy: dib_f(L_.T, xx, yy, L_)))
    partes = _uso_conversacion(f, f.get("motor") or a.get("mid"))
    yy = y_caja - 1
    T.put(bx + 1, yy, corto(" · ".join(partes), bw - 2), C["tx2"])
    for alto_, dibujar in abajo:
        if yy - alto_ < y0 + 2:
            break
        yy -= alto_
        dibujar(L, s, bx, yy)
    y1 = yy - 1
    cw = bw - 2
    lineas = D.lineas_chat(s, cw)
    alto = max(0, y1 - y0 + 1)
    T.scroll_max = max(0, len(lineas) - alto)
    sc = max(0, min(s.get("scroll") or 0, T.scroll_max))
    fin = len(lineas) - sc
    vis = lineas[max(0, fin - alto):fin]
    if not lineas:
        otra = (s.get("tab") or D.NAV) != D.NAV
        for i, txt in enumerate(("Escríbele a %s." % a["n"], "Es la misma sesión que abres en su programa oficial."
                                 if otra else "Es la misma conversación que en el navegador.")):
            T.center(bx, bw, y0 + max(0, alto // 2 - 1) + i, corto(txt, cw - 2), C["tx3"])
    for i, ln in enumerate(vis):
        D._linea(T, bx + 1, y0 + i, ln, bx + 1 + cw)
    caja(L, s, a, bx, bw, y_caja)
    teclas_borde(T, bx, y + h - 1, x + w - 2, teclas_conv(s), BG)
    return zonas


# ── el panel del agente: lo que es suyo (datos puros y su dibujo) ─────────────
def _hace_corto(t, ahora=None):
    """«ahora», «4 min», «2 h», «3 d» de un segundo epoch (lo que va haciendo)."""
    try:
        d = max(0, int((time.time() if ahora is None else ahora) - float(t)))
    except (TypeError, ValueError):
        return ""
    return "ahora" if d < 60 else ("%d min" % (d // 60) if d < 3600 else ("%d h" % (d // 3600) if d < 86400 else
                                                                            "%d d" % (d // 86400)))


def _cuando_corto(ts, ahora=None):
    t = D.hace(ts, ahora)
    return t[5:] if t.startswith("hace ") else t


#: Cuánto se queda a la vista «Terminó» en el panel antes de volver a sus skills (s).
TERMINO_S = 45.0


def proceso(s):
    """La skill que corre en esta conversación, como la ve el panel (el P-1 de la página): {nombre, pasos [(texto,
    estado)], hechos, n, ahora (lo de este momento), pregunta (lo que te pregunta) y termino}. Una que acaba de
    terminar se queda TERMINO_S con «Terminó»; después, None (vuelven sus skills)."""
    f = s.get("foto") or {}
    ejec = s.get("ejec") or f.get("ejecuciones") or []
    e = D.vigente(ejec, s.get("ahora"), s.get("skill_vigente", f.get("skill_vigente", D.SIN_REGLA)))
    termino = False
    if e is None:
        ahora = time.time() if s.get("ahora") is None else s["ahora"]
        for x in ejec:
            if x.get("estado") == "listo":
                tt = D._ts(x.get("actualizado") or x.get("creado"))
                if tt and 0 <= ahora - tt < TERMINO_S:
                    e, termino = x, True
                    break
    if e is None:
        return None
    pasos = [(D.limpio(p.get("texto")) or "Paso", "done" if termino else (p.get("estado") or "pending"))
             for p in e.get("pasos") or []]
    hechos = sum(1 for _t, st in pasos if st == "done")
    hace = f.get("hace") or {}
    if termino:
        ahora_txt = D.limpio(e.get("resultado") or e.get("resumen") or "") or "Terminó."
    elif hace:
        verbo = D.HERR_N.get(hace.get("n"), hace.get("n") or "")
        det = D.detalle_corto("", hace.get("d"), hace.get("f"))
        ahora_txt = (verbo[:1].upper() + verbo[1:] + (" · " + det if det else "")) if verbo else ""
    else:
        ahora_txt = "Armando el plan" if e.get("estado") == "arrancando" else (
            "Leyendo lo que le pediste" if not pasos else "")
    q = s.get("pregunta") if (s.get("pregunta") and not s.get("permiso")) else None
    return {"id": e.get("id") or "", "nombre": D.nombre_skill(e.get("skill")), "skill": e.get("skill"),
            "pasos": pasos, "hechos": hechos,
            "n": len(pasos), "ahora": D.limpio(ahora_txt), "termino": termino,
            "pregunta": D.limpio((q or {}).get("pregunta") or (q or {}).get("texto") or "") if q else ""}


def datos_panel(s):
    """Lo del panel (y de la franja), del agente elegido. Puro: lo mismo para el panel, el cajón, la franja y las
    pruebas. {motor, motor_n, modelo, conexion: (ícono, color, texto), sesiones: [..3], n_ses, espera, ses_nota,
    skills: [..3], n_sk, sk_nota, actividad: [(texto, cuándo, ahora)]}."""
    a = agente(s)
    f = s.get("foto") or {}
    mid = f.get("motor") or a.get("mid") or ""
    out = {"motor": mid, "motor_n": D.nombre_motor(mid)}
    # el modelo: lo que diga su motor; si no lo dice, el de su config (Workspace no elige modelos)
    aj = (s.get("fotos_ajustes") or {}).get(a.get("id")) or f.get("ajustes") or {}
    actual = ((aj.get("valores") or {}).get("modelo") or {}).get("actual") or {}
    tabla = next((t for t in aj.get("tabla") or [] if t.get("k") == "modelo"), None) or {}
    nom = next((o.get("t") for o in tabla.get("opciones") or [] if o.get("v") == actual.get("v")), None)
    out["modelo"] = (nom or actual.get("t") or "el de su config")
    # la conexión: cómo está su motor (lo mismo que Motores y conexiones)
    d = s.get("datos") or {}
    fila = next((m for m in (d.get("motores") or {}).get("motores") or [] if m.get("id") == mid), None)
    if fila is None:
        cargando = "motores" in (s.get("cargando") or ())
        err = (s.get("errores") or {}).get("motores")
        out["conexion"] = ("·", C["tx3"], "viendo…" if cargando else (err or "sin revisar"))
    else:
        integ = fila.get("integracion") or {}
        ico, ck = {"listo": ("✓", OK), "experimental": ("!", WARN), "sin_sesion": ("!", WARN),
                   "falta_modelo": ("!", WARN), "bloqueado": ("!", ERR), "incompleta": ("!", WARN),
                   "no_instalado": ("✗", ERR)}.get(fila.get("estado"), ("·", C["tx2"]))
        txt = D.limpio(fila.get("estado_texto") or fila.get("estado") or "")
        if fila.get("estado") == "listo" and integ.get("nivel") == "experimental":
            ico, ck, txt = "!", WARN, D.limpio(integ.get("texto") or "conexión experimental")
        out["conexion"] = (ico, ck, txt or "sin revisar")
    # sus skills: las más usadas en esta conversación primero (de sus ejecuciones), luego en su orden
    sk = s.get("panel_skills")
    usos = {}
    for e in f.get("ejecuciones") or []:
        usos[e.get("skill")] = usos.get(e.get("skill"), 0) + 1
    orden = sorted(list(sk or []), key=lambda x: (-usos.get(x.get("nombre"), 0), str(x.get("nombre")).lower()))
    out["skills"], out["n_sk"], out["usos"] = orden, len(sk or []), usos
    out["sk_nota"] = ("Buscando sus skills…" if sk is None else ("Todavía no tiene skills." if not sk else ""))
    out["proceso"] = proceso(s)
    # lo que va haciendo (sus últimas herramientas, la más nueva primero; mientras trabaja, la de ahora)
    act = []
    for k, x in enumerate(reversed(list(f.get("hizo") or []))):
        verbo = D.HERR_N.get(x.get("n"), x.get("n") or "?")
        det = D.detalle_corto("", x.get("d"), x.get("f"))
        if x.get("f") and (not det or det == x.get("f")):
            det = os.path.basename(str(x["f"]))
        txt = verbo[:1].upper() + verbo[1:] + (" · " + det if det else "")
        act.append((D.limpio(txt), _hace_corto(x.get("t"), s.get("ahora")), k == 0 and bool(f.get("trabajando"))))
    out["actividad"] = act[:8]
    return out


def _ses_color(r, a):
    ico, est = D.ESTADO_SES.get(r.get("estado"), ("·", ""))
    vivo = r.get("estado") in ("trabajando", "te_espera")
    espera = r.get("estado") == "te_espera"
    return (ico, a["c"] if vivo else C["tx3"], est, a["c"] if espera else (C["tx2"] if vivo else C["tx3"]), espera)


def _proceso(L, s, a, pr, x0, x1, ix, iw, yy, y_fin):
    """El proceso de la skill que corre (el P-1 de la página, en celdas): su nombre y en qué paso va, la barra, los
    pasos (✓ hechos, ● el de ahora en el color del agente, · los que faltan), lo de este momento y, si te pregunta
    algo, la pregunta en su color con «Esperando tu respuesta abajo ↓». Al terminar, «Terminó» y su resultado.
    → la fila siguiente."""
    T = L.T
    n, hechos = pr["n"], pr["hechos"]
    der = "Terminó" if pr["termino"] else ("paso %d de %d" % (min(n, hechos + 1), n) if n else "")
    sub_titulo(L, x0, x1, yy, ix - 1, iw + 1, "▸ " + pr["nombre"], der or None, None)
    T.put(ix, yy, "▸", a["c"], True, P1)
    yy += 1
    if n and yy < y_fin:
        lleno = iw * hechos // n
        T.put(ix, yy, "▰" * lleno, a["c"], False, P1)
        T.put(ix + lleno, yy, "▱" * (iw - lleno), C.get("line") or C["tx3"], False, P1)
        yy += 2
    vis = pr["pasos"]
    cabe = max(1, y_fin - yy - (5 if pr["pregunta"] else 3))
    if len(vis) > cabe:                               # alrededor del de ahora
        k = next((i for i, (_t, st) in enumerate(vis) if st == "now"), hechos)
        i0 = max(0, min(k - cabe // 2, len(vis) - cabe))
        vis = vis[i0:i0 + cabe]
    for txt_, st in vis:
        if yy >= y_fin:
            break
        ico, col, b = {"done": ("✓", C["tx3"], False), "now": ("●", a["c"], True)}.get(st, ("·", C["tx3"], False))
        T.put(ix, yy, ico, a["c"] if st == "done" else col, b)
        T.put(ix + 2, yy, corto(txt_, iw - 2), C["tx"] if st == "now" else (C["tx3"] if st == "done" else C["tx2"]),
              b)
        yy += 1
    if pr["ahora"] and yy < y_fin:
        yy += 1
        col = B.OK if pr["termino"] else C["tx2"]
        for ln in D.envolver([((("✓ " if pr["termino"] else "") + pr["ahora"]), col, False)], iw)[:2]:
            if yy >= y_fin:
                break
            D._linea(T, ix, yy, ln, ix + iw)
            yy += 1
    if pr["pregunta"] and yy + 2 < y_fin:            # te pregunta: en su color, y se contesta abajo
        yy += 1
        for ln in D.envolver([("? " + pr["pregunta"], a["c"], True)], iw)[:3]:
            D._linea(T, ix, yy, ln, ix + iw)
            yy += 1
        T.put(ix, yy, corto("Esperando tu respuesta abajo ↓", iw), a["c"])
        yy += 1
    if not pr["termino"] and pr.get("id") and yy + 1 < y_fin:     # skills-cierre: «Detener», también en el hub
        yy += 1
        hov = L.reg(ix, yy, len(D.DETENER), 1, "pan:detener:" + pr["id"])
        T.put(ix, yy, D.DETENER, C["tx"] if hov else C["tx2"], hov, P3 if hov else P1)
        yy += 1
    return yy + 1


def panel(L, s, G, x, y, w, h, cerrar="«"):
    """El panel del agente mientras conversas: motor ▾ y modelo (y la conexión, si algo le falta); sus skills (las
    más usadas, con «Usar») o, mientras corre una, su proceso; lo que va haciendo; y abajo «Abrir en su motor ↗».
    Las sesiones del programa oficial no van aquí (viven en Inicio → «Sesiones ↗»). `cerrar`: «« » lo cierra a la
    franja; «✕», el cajón. → {rid: (x, ancho)}."""
    T, a = L.T, agente(s)
    dp = datos_panel(s)
    L.reg(x, y, w, h, "pan:caja")                    # un clic en su fondo no cae a lo de abajo
    zonas = area(L, x, y, w, h, P1, titulo=[(corto(a["n"], 18), a["c"], True), (" · este agente", C["tx3"], False)],
                 der=[(cerrar, C["tx2"], False, "pan:cerrar")],
                 foco_a=a if s.get("foco_area") == "panel" else None)
    ix, iw = x + 3, w - 6
    x0, x1 = x, x + w - 1
    yb = y + h - 5                                    # el botón de abajo
    yy = y + 2
    # su motor, su modelo y su conexión
    T.put(ix, yy, "Motor", C["tx3"], False, P1)
    segs(L, ix + 10, yy, [(" %s ▾ " % dp["motor_n"], None, False, "pan:motor")], P1, zonas, limite=ix + iw)
    yy += 1
    T.put(ix, yy, "Modelo", C["tx3"], False, P1)
    segs(L, ix + 11, yy, [(corto(dp["modelo"], iw - 14) + " ↗", C["tx2"], False, "pan:modelo")], P1, zonas)
    yy += 1
    ico, col, txt = dp["conexion"]
    if ico in ("!", "✗"):                             # la conexión, solo si algo le falta
        T.put(ix, yy, "Conexión", C["tx3"], False, P1)
        hov = L.reg(ix + 11, yy, iw - 11, 1, "pan:conexion")
        if hov:
            T.fill(ix + 11, yy, iw - 11, 1, P3)
        xx = T.put(ix + 11, yy, ico + " ", col, True)
        T.put(xx, yy, corto(txt, ix + iw - xx), C["tx"] if hov else C["tx2"])
        yy += 1
    yy += 1
    pr = dp["proceso"]
    if pr:                                            # la skill que corre: su proceso toma el panel (P-1)
        yy = _proceso(L, s, a, pr, x0, x1, ix, iw, yy, yb - 1)
    elif yb - 1 - yy >= 3:                            # sus skills: las más usadas, con «Usar»
        sub_titulo(L, x0, x1, yy, ix - 1, iw + 1, "Skills · %d" % dp["n_sk"] if dp["n_sk"] else "Skills", "Todas →",
                   "pan:skills")
        yy += 1
        if dp["sk_nota"]:
            T.put(ix, yy, corto(dp["sk_nota"], iw), C["tx3"])
            yy += 1
        tope = max(1, min(6, (yb - 1 - yy) - 6))      # deja lugar para «Lo que va haciendo»
        for sk in dp["skills"][:tope]:
            if yy >= yb - 1:
                break
            n = sk["nombre"]
            rid = "pan:sk:" + n
            lab = " Usar "
            xu = ix + iw - W(lab) - 1
            hov = L.reg(x + 1, yy, xu - 1 - (x + 1), 1, rid)
            if hov or L.apr(rid):
                B.bloque(T, x + 1, yy, w - 2, 1, P3 if L.apr(rid) else P2, P1)
            T.put(ix, yy, "▸", a["c"])
            T.put(ix + 2, yy, corto(D.nombre_skill(n), xu - ix - 4), C["tx"] if hov else C["tx2"], hov)
            ru = "pan:usar:" + n
            hu = L.reg(xu, yy, W(lab) + 2, 1, ru)
            B.ficha(T, xu, yy, lab, P4 if (hu or L.apr(ru)) else P3, P2 if hov else P1,
                    C["tx"] if hu else C["tx2"])
            yy += 1
        yy += 1
    # lo que va haciendo
    if yb - 1 - yy >= 3:
        sub_titulo(L, x0, x1, yy, ix - 1, iw + 1, "Lo que va haciendo")
        yy += 1
        if not dp["actividad"]:
            T.put(ix, yy, corto("Todavía nada en esta conversación.", iw), C["tx3"])
        for txt_, cuando, ahora_ in dp["actividad"]:
            if yy >= yb - 1:
                break
            T.put(ix, yy, "●" if ahora_ else "·", a["c"] if ahora_ else C["tx3"], ahora_)
            T.put(ix + 2, yy, corto(txt_, iw - 2 - W(cuando) - 2), C["tx"] if ahora_ else C["tx2"])
            T.right(ix + iw, yy, "ahora" if ahora_ else cuando, C["tx3"])
            yy += 1
    if yb > y + 3:
        B.boton(L, s, ix, yb, "Abrir en %s ↗" % dp["motor_n"], "pan:abrir", P1, ancho=iw)
    return zonas


# ── la franja (el panel cerrado) y su globo ───────────────────────────────────
def iconos(s):
    """Los íconos de la franja: [(rid, glifo, etiqueta, color, globo)] (lo mismo que el panel: sin sesiones)."""
    a = agente(s)
    dp = datos_panel(s)
    ico, col, txt = dp["conexion"]
    corto_motor = dp["motor_n"].split()[0] if dp["motor_n"] else "motor"
    pr = dp["proceso"]
    out = [("motor", "◈", corto_motor, C["tx3"], "Motor · %s" % dp["motor_n"])]
    if pr:
        paso_ = "✓" if pr["termino"] else ("%d/%d" % (min(pr["n"], pr["hechos"] + 1), pr["n"]) if pr["n"] else "…")
        out.append(("skills", "▸", paso_, a["c"], "%s · %s" % (pr["nombre"], "terminó" if pr["termino"] else
                                                                    ("te pregunta" if pr["pregunta"] else "corre"))))
    else:
        out.append(("skills", "✦", str(dp["n_sk"]) if dp["n_sk"] else "·", C["tx3"], "Skills · %d" % dp["n_sk"]))
    out += [("conexion", "⇄", ico, col, "Conexión · %s" % txt),
            ("abrir", "↗", "abrir", C["tx3"], "Abrir en %s ↗" % dp["motor_n"])]
    return out


def franja(L, s, G, x, y, w, h):
    """El panel cerrado: «« panel» y una columna de íconos con su cuenta; cada uno abre el panel (el de «abrir»,
    su motor). → {rid: fila} de cada ícono (para su globo)."""
    T = L.T
    area(L, x, y, w, h, P1)
    L.reg(x, y, w, h, "fr:caja")
    hov = L.reg(x + 1, y + 1, w - 2, 1, "fr:panel")
    if hov:
        T.fill(x + 1, y + 1, w - 2, 1, P3)
    T.center(x, w, y + 1, "« panel", C["tx"] if hov else C["tx3"])
    filas = {}
    for i, (rid, g, lab, col, _globo) in enumerate(iconos(s)):
        yy = y + 3 + 4 * i
        if yy + 3 > y + h - 1:
            break
        filas[rid] = yy
        hov = L.reg(x + 1, yy, w - 2, 3, "fr:" + rid)
        if hov or L.apr("fr:" + rid):
            B.bloque(T, x + 1, yy, w - 2, 3, P4 if L.apr("fr:" + rid) else P3, P1)
        T.center(x, w, yy + 0, g, C["tx"] if hov else C["tx2"], True)
        T.center(x, w, yy + 1, corto(lab, w - 2), col, rid == "sesiones")
    return filas


def globo_icono(L, xr, y, txt):
    """El globo de un ícono de la franja, a su izquierda (encima de todo, con sombra)."""
    T = L.T
    w = min(W(txt) + 6, xr - 1)
    x = xr - w
    B.limpiar(T, x, y, w, 3, BG)
    B.bloque(T, x, y, w, 3, P3, BG)
    B.sombra(T, x, y, w, 3)
    T.put(x + 3, y + 1, corto(txt, w - 6), C["tx"], True, P3)


def cajon(L, s, G):
    """El panel encima de la conversación (pantalla media): a la izquierda de la franja, con ✕ y su sombra."""
    T = L.T
    x, y, w, h = G["cajon"]
    B.limpiar(T, x, y, w, h, BG)
    z = panel(L, s, G, x, y, w, h, cerrar="✕")
    B.sombra(T, x, y, w, h)
    return z


# ── las secciones en su marco H-1 ─────────────────────────────────────────────
def marco(L, s, G, sec):
    """La sección `sec` a pantalla completa (a la derecha del riel) en un área con su título en el borde y «✕ Volver»;
    su borde, del color del agente a media fuerza. → el marco M de hub_secciones (xl, wl, xd, wd, yt, yd, y0, y1)."""
    import hub_secciones as S
    T = L.T
    x, y, w, h = G["seccion"]
    a = agente(s)
    avail = w - 6
    lado = avail >= S.LADO_A_LADO
    der = []
    if not lado and sec.get("abierto"):
        der += [(" ‹ Lista ", C["tx2"], False, "sec:lista"), (" ", C["tx3"], False)]
    if s.get("sin_riel"):
        der.append((" ⌂ Inicio  Esc ", C["tx2"], False, "sec:volver"))
    else:
        der.append((" ✕ Volver a la conversación " if avail >= 52 else " ✕ Volver ", C["tx2"], False, "sec:volver"))
    titulo = [(TITULOS[sec["kind"]], C["tx"], True)]
    if sec.get("desde") == "ajustes":                 # Conexiones, abierta desde su grupo de Ajustes (H3-b)
        titulo = [("Ajustes › ", C["tx3"], False)] + titulo
    if sec["kind"] in ("skills", "ajustes"):
        titulo.append((" · %s" % a["n"], C["tx3"], False))
    area(L, x, y, w, h, BG, titulo, der, foco_a=a)
    xl = x + 3
    if lado:
        wd = max(34, min(50, avail * 36 // 100))
        wl = avail - wd - 2
        xd = xl + wl + 2
    else:
        wl = wd = avail
        xd = xl
    yt = y + 1
    T.lado = lado
    return {"xl": xl, "wl": wl, "xd": xd, "wd": wd, "yt": yt, "yd": yt if lado else yt + 2, "y0": yt + 4,
            "y1": y + h - 2, "lado": lado, "detalle": lado or bool(sec.get("abierto"))}


def pantalla_seccion(L, s, G, sec):
    import hub_secciones as S
    T = L.T
    if sec["kind"] == "encamino":                     # una sección que el hub todavía no tiene
        import hub_inicio
        x, y, w, h = G["seccion"]
        area(L, x, y, w, h, BG, foco_a=agente(s))
        hub_inicio.en_camino(L, s, x, y, w, h, sec.get("cual") or "")
        teclas_borde(T, x + 3, y + h - 1, x + w - 2, [("Enter", "abre la página"), ("Esc", "Inicio")], BG)
        if s.get("aviso"):
            T.put(x + 3, T.h - 1, corto(s["aviso"], T.w - x - 4), C["tx2"])
        return
    S.seccion(L, s, marco(L, s, G, sec), sec)
    x, y, w, h = G["seccion"]
    area_f = s.get("foco_area") or "lista"
    if area_f == "lista":
        ks = S.teclas(sec, s)
        ks = ks[:-1] + ([] if sec.get("kind") == "conexiones" else [("letras", "buscan")]) + \
            [("Tab", "otra área")] + ks[-1:]
    else:
        ks = [("↑↓←→", "elige"), ("Enter", "hace"), ("Tab", "otra área"), ("Esc", "a la lista")]
    xx = teclas_borde(T, x + 3, y + h - 1, x + w - 2, ks, BG)
    if s.get("aviso"):                                # lo que pasó (en una línea), en el borde de abajo
        t = " %s " % s["aviso"]
        if xx + 4 + W(t) <= x + w - 2:
            T.put(x + w - 2 - W(t), y + h - 1, t, C["tx2"], False, BG)
        else:
            T.put(x + 1, T.h - 1, corto(s["aviso"], T.w - x - 2), C["tx2"])


# ── los menús que bajan, con el material H-1 ──────────────────────────────────
def menu_caja(L, s, kind, x, y, derecha=False):
    """El menú `kind` en (x, y): un área P2 con su título en el borde y su tecla, sombra de medio pixel, y la elegida
    con la ┃ del agente sobre el borde. Las filas son las de hub_bloque.filas_menu (lo mismo para ↑↓)."""
    T = L.T
    a = agente(s)
    titulo, tecla, filas, ancho, elegida = B.filas_menu(kind, s, T.w)
    if kind != "sesiones":
        ancho = max([ancho, W(titulo) + W(tecla) + 10] + [B._ancho_fila(r) for r in filas])
    w = max(14, min(T.w - 2, ancho))
    if derecha:
        x = x - w + 1
    x = max(0, min(x, T.w - w - 1))
    vis, i0, i1, pie, n = B.menu_ventana(filas, elegida, max(1, T.h - y - 4))
    alto = 2 + sum(B._alto_fila(r) for r in vis)
    L.reg(x, y, w, alto, "menu:caja")
    B.limpiar(T, x, y, w, alto, P2)
    area(L, x, y, w, alto, P2, titulo=[(corto(titulo, w - W(tecla) - 10), C["tx"], True)],
         der=[(tecla, C["tx3"], False)] if tecla else None)
    B.sombra(T, x, y, w, alto)
    if i0 > 0:
        T.put(x + w - 2, y + 1, "▲", C["tx2"], False, P2)
    if i1 < n:
        T.put(x + w - 2, y + alto - 2 - sum(B._alto_fila(r) for r in pie), "▼", C["tx2"], False, P2)

    def marca(T_, yy, hf):
        marca_sel(T_, x, yy, hf, a, P2)

    def sep(T_, yy):
        T_.put(x, yy, "├" + "─" * (w - 2) + "┤", LN, False, P2)
    B.filas_caja(L, s, a, vis, elegida, x, y + 1, w, marca=marca, sep=sep)
    return x, y, w, alto


# ── la pantalla ───────────────────────────────────────────────────────────────
def pantalla(w, h, s, crudo=False):
    """El hub H-1 que se acomoda a su ancho. → Term, con `zonas`, `riel`, `scroll_max`, `lado` y `geo` (sus
    medidas: el nivel, para que el mouse sepa qué abre la franja). `crudo`: sin el color P-3 (la entrada a S-1)."""
    T = P.Term(w, h)
    T.scroll_max, T.riel, T.lado, T.geo = 0, None, True, None
    T.fill(0, 0, w, h, BG)
    if w < P.MIN_W or h < P.MIN_H:
        T.center(0, w, h // 2, "Agranda la ventana", C["tx2"])
        return P.afinar(T, ((s.get("datos") or {}).get("preferencias") or {}).get("fondo"))
    L = B.Lienzo(T, s)
    ag = s.get("agentes") or []
    G = geometria(w, h, s)
    T.geo = G
    if not ag:
        G = dict(G, barra=(1, 0, w - 2, 3))
        barra(L, s, G, None)
        T.center(0, w, h // 2, corto("Todavía no tienes agentes: agrega el primero con «+ Agregar».", w - 2),
                 C["tx2"])
        return P.afinar(T, ((s.get("datos") or {}).get("preferencias") or {}).get("fondo"))
    a = ag[s["sel"]]
    anclas = {}
    if G["barra"]:
        anclas.update(barra(L, s, G, a))
    pos = riel(L, s, G) if G["riel"] else {}
    sec = s.get("seccion")
    filas_fr = {}
    if sec:
        pantalla_seccion(L, s, G, sec)
    else:
        z = conversacion(L, s, G, a)
        if "hdr:motor" in z:
            anclas.setdefault("motor", (z["hdr:motor"][0], z["hdr:motor"][1], False))
        if "tb:nueva" in z:
            anclas.setdefault("tabs", (z["tb:nueva"][0], z["tb:nueva"][1], False))
        x, y, cw, ch = G["conv"]
        anclas.setdefault("sesiones", (x + cw - 3, 1, True))
        anclas.setdefault("skills", (G["bx"], 1, False))
        if G["panel"]:
            zp = panel(L, s, G, *G["panel"])
            if "pan:motor" in zp and "motor" not in anclas:       # H4-a: el motor está en el panel: baja de ahí
                px, py, pw, _ph = G["panel"]
                anclas["motor"] = (px + 2, pw - 4, True, py + 3)
        elif G["franja"]:
            filas_fr = franja(L, s, G, *G["franja"])
    if G["riel"]:
        anclas.setdefault("agentes", (G["riel"][0] + G["riel"][2] + 1, 1, False))
        borde(L, s, G)
    T.flat()
    sobre = s.get("sobre") or ""
    if not sobre.startswith("fr:") and str(s.get("foco") or "").startswith("fr:"):
        sobre = s["foco"]                             # el globo del ícono enfocado (también con el teclado)
    if G["cajon"] and not sec:
        cajon(L, s, G)
    elif sobre.startswith("fr:") and sobre[3:] in filas_fr:
        txt = next(g for rid, _g, _l, _c, g in iconos(s) if rid == sobre[3:])
        globo_icono(L, G["franja"][0] - 1, filas_fr[sobre[3:]], txt)
    if G["riel"] and not G["nombres"] and sobre.startswith("riel:") and sobre[5:].isdigit():
        i = int(sobre[5:])
        if i in pos:                                  # junto a su monito, sin tapar la caja de escribir
            xg = G["riel"][0] + G["riel"][2] + 1
            B.globo(L, s, i, xg, max(G["riel"][1], min(pos[i], G["y_caja"] - 5)))
    k = B.abierto(s)
    if not k:
        marcar_foco(T, s)
    if k:
        an = anclas.get(k) or (G["bx"], 0, False)
        xb, wb, der = an[:3]
        y_menu = an[3] if len(an) > 3 else 2
        if G["barra"]:                                # la angosta: baja de su botón (o de «≡ Menú»)
            y_menu = 3
            hit = next(((xx, ww) for rid, _l, xx, ww in (barra_botones(w, s)[0] or []) if rid == k), None)
            if hit:
                xb, wb, der = hit[0], hit[1], False
            elif "menu" in anclas:
                xb, wb, der = anclas["menu"][0], anclas["menu"][1], True
        menu_caja(L, s, k, xb + wb - 1 if der else xb, y_menu, derecha=der)
    return T if crudo else P.afinar(T, ((s.get("datos") or {}).get("preferencias") or {}).get("fondo"))
