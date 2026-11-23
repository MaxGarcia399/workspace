#!/usr/bin/env python3
r"""WORKSPACE · hub_bloque — la piel T-2 «Bloque» del hub (la versión de Zenith). SOLO PARA PROBAR: vive en la rama
zenith/hub-bloque y nunca entra a main.

Sin líneas: la profundidad sale de cuatro grises de celda (P1 el cromo, P2 lo levantado, P3 lo de encima y los
botones, P4 lo apretado) y de medios bloques, el mismo pixel de los monitos:
  · las esquinas son cuartos de celda (▟ ▙ ▜ ▛) y los botones, medios bloques (▗▄▖ ▐ ▌ ▝▀▘);
  · el agente elegido se recorta del riel y se une a su conversación, como una pestaña;
  · el menú abierto se ve en video inverso (su botón claro, letra oscura) y su caja lleva medio pixel de sombra.
En 256 colores los grises caen en 233-237: se siguen separando.

El riel es COMPACTO por omisión (solo los monitos; nombre, motor y estado en un globo al pasar el mouse). Se abre
al riel con nombres arrastrando su borde con el mouse, con ^B o desde el menú de Agentes, y se recuerda.

Aquí está la pantalla principal (barra, riel, conversación, cajas, menús que bajan). Las secciones (Sesiones,
Skills, Motores y conexiones, Ajustes, Agentes, Ayuda) están en hub_secciones. El estado y lo que hace cada tecla o
clic, en hub_directo.Directo. Stdlib."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_paleta as P  # noqa: E402
import hub_directo as D  # noqa: E402
import hub_monitos as M  # noqa: E402

C, ERR = P.C, P.ERR

# ── la paleta T-2 ─────────────────────────────────────────────────────────────
BG = "#0f0f11"          # el fondo (la conversación)
P1 = "#17171b"          # el cromo: la barra y el riel
P2 = "#212127"          # lo levantado: paneles, la caja de escribir, el mouse encima
P3 = "#2c2c33"          # lo de encima: botones, lo elegido
P4 = "#3b3b43"          # lo apretado, el mouse encima de un botón, los separadores
LUZ, LUZTX = "#e6e6eb", "#141416"   # video inverso: el menú abierto, el filtro elegido
SOMBRA = "#050506"      # medio pixel de sombra bajo lo que se abre encima
OFF = "#4a4a52"         # lo apagado
OK, WARN = "#3fbf7f", "#e7a43a"

#: Los anchos del riel: compacto (solo monitos) y con nombres. Con menos de ANCHO_NOMBRES columnas, siempre
#: compacto; con menos de ANCHO_RIEL, no hay riel (la fila de monitos de hoy).
RIEL_COMPACTO, RIEL_NOMBRES = 14, 34
ANCHO_NOMBRES, ANCHO_RIEL = 96, 80
#: Desde este alto, la barra mide 3 filas (sus botones son pastillas de medio bloque); abajo, 1.
ALTO_BARRA = 30
BARRA_IZQ = (("agentes", "Agentes ▾", "Agentes ▾"), ("motor", "Motor ▾", "Motor ▾"),
             ("sesiones", "Sesiones ▾", "Sesiones ▾"), ("skills", "Skills ▾", "Skills ▾"),
             ("abrir", "Abrir en su motor ↗", "Abrir ↗"))
BARRA_DER = (("ajustes", "Ajustes", "Ajustes"), ("ayuda", "? Ayuda", "?"), ("salir", "✕ Salir", "✕"))
#: Lo que en la barra abre una sección directamente (sin menú que baje).
DIRECTAS = ("ajustes", "ayuda")
#: El botón de la barra que se ve activo con cada sección abierta.
ACTIVO = {"sesiones": "sesiones", "motores": "motor", "skills": "skills", "agentes": "agentes",
          "ajustes": "ajustes", "ayuda": "ayuda"}


def W(s):
    return P._ancho(s)


def corto(s, n):
    return P._corto(s, max(1, n))


class Lienzo:
    """La grilla y lo que se sabe del mouse al dibujarla: `reg()` apunta una zona que se toca (y dice si el mouse
    está encima); `apr()`, si está apretada (el botón izquierdo bajó ahí y sigue ahí)."""

    def __init__(self, T, s):
        self.T = T
        self.sobre = s.get("sobre") or ""
        self.foco = s.get("foco") or ""              # H-1: lo enfocado se ve como el mouse encima (y Enter lo hace)
        ap = s.get("apretado")
        self.apretado = ap if ap and ap == self.sobre else ""

    def reg(self, x, y, w, h, rid):
        T = self.T
        x0, y0, x1, y1 = max(0, x), max(0, y), min(T.w, x + w), min(T.h, y + h)
        if x1 > x0 and y1 > y0:
            T.zonas.append((x0, y0, x1 - x0, y1 - y0, rid))
        return bool(rid) and (rid == self.sobre or rid == self.foco)

    def apr(self, rid):
        return bool(rid) and rid == self.apretado


# ── el material: planos, pastillas y fichas de medio bloque ───────────────────
def limpiar(T, x, y, w, h, bg=BG):
    """Borra un rectángulo (letras y fondo): lo que se abre encima no deja ver lo de abajo."""
    w = max(0, min(w, T.w - x))
    for j in range(max(0, y), min(T.h, y + h)):
        T.put(max(0, x), j, " " * w, None, False, bg)


def bloque(T, x, y, w, h, col, fuera):
    """Un plano de color `col` con las esquinas redondeadas a cuartos de celda (▟ ▙ ▜ ▛) sobre `fuera`."""
    if w <= 0 or h <= 0:
        return
    T.fill(x, y, w, h, col)
    if w < 2:
        return
    if h == 1:
        T.put(x, y, "▐", col, False, fuera)
        T.put(x + w - 1, y, "▌", col, False, fuera)
        return
    T.put(x, y, "▟", col, False, fuera)
    T.put(x + w - 1, y, "▙", col, False, fuera)
    T.put(x, y + h - 1, "▜", col, False, fuera)
    T.put(x + w - 1, y + h - 1, "▛", col, False, fuera)


def pildora(T, x, y, w, col, fuera):
    """Un botón de 3 filas que se ve de 2: medio bloque arriba, la fila del texto y medio bloque abajo."""
    T.put(x, y, "▗" + "▄" * (w - 2) + "▖", col, False, fuera)
    T.put(x, y + 1, "▐", col, False, fuera)
    T.fill(x + 1, y + 1, w - 2, 1, col)
    T.put(x + w - 1, y + 1, "▌", col, False, fuera)
    T.put(x, y + 2, "▝" + "▀" * (w - 2) + "▘", col, False, fuera)


def ficha(T, x, y, lab, col, fuera, fg, b=False):
    """Una pastilla de 1 fila: ▐ texto ▌. → la columna siguiente."""
    T.put(x, y, "▐", col, False, fuera)
    xx = T.put(x + 1, y, lab, fg, b, col)
    T.put(xx, y, "▌", col, False, fuera)
    return xx + 1


def sombra(T, x, y, w, h):
    """Medio pixel de sombra a la derecha y abajo de un rectángulo (▌ y ▀ casi negros sobre lo que haya)."""
    for j in range(y + 1, min(T.h, y + h)):
        if x + w < T.w:
            T.put(x + w, j, "▌", SOMBRA)
    if y + h < T.h:
        T.put(x + 1, y + h, "▀" * max(0, min(w, T.w - x - 1)), SOMBRA)


def boton(L, s, x, y, lab, rid, fuera, foco=False, apagado=False, wmin=0, a=None, ancho=None):
    """Un botón de 3 filas (pastilla): el del foco va del color del agente; el mouse encima lo sube un gris; apagado
    no se toca. `ancho`: exacto (la etiqueta se acorta si no cabe). → la columna siguiente."""
    T = L.T
    a = a or agente(s)
    wi = ancho if ancho else max(wmin, W(lab) + 6)
    hov = False if apagado else L.reg(x, y, wi, 3, rid)
    apr = L.apr(rid) and not apagado
    if foco:
        col = P.mix(a["c"], "#000000", 0.2) if apr else (P.mix(a["c"], "#ffffff", 0.18) if hov else a["c"])
        fg = LUZTX
    elif apagado:
        col, fg = (P1 if fuera == P2 else P2), OFF
    else:
        col, fg = (P4 if (hov or apr) else P3), (C["tx"] if hov else C["tx2"])
    pildora(T, x, y, wi, col, fuera)
    T.center(x, wi, y + 1, corto(lab, wi - 2), fg, foco)
    return x + wi


def chip(L, x, y, lab, rid, fuera=BG, activo=False, base=None):
    """Una ficha que se toca (una fila): activa en video inverso; el mouse encima, un gris más. → la columna
    siguiente."""
    T = L.T
    hov = L.reg(x, y, W(lab) + 2, 1, rid)
    if activo:
        return ficha(T, x, y, lab, LUZ, fuera, LUZTX, True)
    if hov or L.apr(rid):
        return ficha(T, x, y, lab, P4 if L.apr(rid) else P3, fuera, C["tx"])
    if base:
        return ficha(T, x, y, lab, base, fuera, C["tx2"])
    return T.put(x + 1, y, lab, C["tx2"]) + 1


def agente(s):
    ag = s.get("agentes") or []
    return ag[s.get("sel") or 0] if ag else {"c": C["tx2"], "n": "", "id": "", "f": "bolita"}


# ── las medidas ───────────────────────────────────────────────────────────────
def geometria(w, h, nombres=False, riel_w=None):
    """Las medidas del hub para una terminal de w×h. `nombres`: la preferencia del riel con nombres (si cabe);
    `riel_w`: el ancho mientras se arrastra su borde."""
    modo = "fila" if w < ANCHO_RIEL else "riel"
    bh = 3 if h >= ALTO_BARRA else 1
    G = {"modo": modo, "bh": bh, "yl": 1 if bh == 3 else 0, "y_caja": h - 5, "y_teclas": h - 1}
    if modo == "fila":
        N, bw, bx = D._geom(w)
        G.update(RW=0, N=N, bw=bw, bx=bx, x0=0, y_mon=bh + 1, yh=bh + 8, nombres=False)
    else:
        if riel_w is not None:
            RW = max(RIEL_COMPACTO, min(RIEL_NOMBRES, int(riel_w), w - 60))
        else:
            RW = RIEL_NOMBRES if (nombres and w >= ANCHO_NOMBRES) else RIEL_COMPACTO
        con_nombres = RW >= 30
        pw = w - RW
        bw = min(96, pw - 4)
        G.update(RW=RW, N=False, bw=bw, bx=RW + (pw - bw) // 2, x0=RW, yh=bh + 1, y_titulo=bh + 1,
                 y_riel=bh + (3 if con_nombres else 2), nombres=con_nombres)
    G["y_conv"] = G["yh"] + 2
    return G


def cabe_riel(h, y0):
    """Cuántos agentes caben en el riel desde la fila `y0`: 6 filas cada uno; abajo queda su última fila (agregar
    o «▼ más»)."""
    return max(1, (h - 7 - y0) // 6 + 1)


def barra_botones(w, G):
    """Los botones de la barra: [(id, etiqueta, x, ancho)] y si van con su etiqueta larga; (None, _) si no caben ni
    con menos aire ni sin la palabra «workspace» (entonces va un solo «≡ Menú»). Sin la palabra, los botones
    empiezan en la columna 5 (G["marca"] = False)."""
    largo = w >= 140
    izq = [(r, la if largo else co) for r, la, co in BARRA_IZQ]
    der = [(r, la if largo else co) for r, la, co in BARRA_DER]
    fin_der = w - 1 - (7 if largo else 0)
    G["marca"] = True
    for aire, x_ini in ((4, max(15, G["RW"] + 1)), (2, max(15, G["RW"] + 1)), (2, 5)):
        G["marca"] = x_ini > 5
        out, x = [], x_ini
        for rid, lab in izq:
            ww = W(lab) + aire
            out.append((rid, lab, x, ww))
            x += ww + 1
        xr, dd = fin_der, []
        for rid, lab in reversed(der):
            ww = W(lab) + aire
            xr -= ww
            dd.append((rid, lab, xr, ww))
            xr -= 1
        if xr >= x - 1:
            return out + dd[::-1], largo
    G["marca"] = True
    return None, largo


def abierto(s):
    """El menú que baja abierto: «motor» (^E), «sesiones» (^S) o el de la barra (agentes, skills, menu)."""
    if s.get("menu"):
        return "motor"
    if s.get("sesiones"):
        return "sesiones"
    if s.get("tabmenu"):
        return "tabs"
    return (s.get("barra") or {}).get("kind")


# ── la barra de menú ──────────────────────────────────────────────────────────
def _item(L, s, G, x, wi, lab, rid, abierto_, activo, a):
    """Un botón de la barra (se toca en toda su altura): abierto = video inverso; su sección abierta = un gris y la
    raya del agente; el mouse encima = un gris."""
    T, bh = L.T, G["bh"]
    hov = L.reg(x, 0, wi, bh, "bar:" + rid)
    apr = L.apr("bar:" + rid)
    if bh == 3:
        if abierto_:
            pildora(T, x, 0, wi, LUZ, P1)
            T.center(x, wi, 1, lab, LUZTX, True)
        elif activo or hov or apr:
            pildora(T, x, 0, wi, P4 if apr else P3, P1)
            T.center(x, wi, 1, lab, C["tx"], activo)
            if activo:
                T.put(x + 1, 2, "▀" * (wi - 2), a["c"], False, P1)
        else:
            T.center(x, wi, 1, lab, C["tx2"])
        return
    if abierto_:
        T.fill(x, 0, wi, 1, LUZ)
        T.center(x, wi, 0, lab, LUZTX, True)
    elif activo or hov or apr:
        T.fill(x, 0, wi, 1, P4 if apr else P3)
        T.center(x, wi, 0, lab, C["tx"], activo)
    else:
        T.center(x, wi, 0, lab, C["tx2"])


def barra(L, s, G, a):
    """La barra de menú. → {menú: (x, ancho, a_la_derecha)}: dónde baja cada menú."""
    T = L.T
    w, bh, yl = T.w, G["bh"], G["yl"]
    T.fill(0, 0, w, bh, P1)
    botones, largo = (None, False) if (G["modo"] == "fila" or not a) else barra_botones(w, G)
    x = T.put(2, yl, "❯", a["c"] if a else C["tx2"], True)
    if G.get("marca", True):
        T.put(x + 1, yl, "workspace", C["tx"], True)
    ab = abierto(s)
    sec = (s.get("seccion") or {}).get("kind")
    if not a:                                         # sin agentes: solo salir
        lab = "✕ Salir"
        ww = W(lab) + 4
        _item(L, s, G, w - 1 - ww, ww, lab, "salir", False, False, {"c": C["tx2"]})
        return {}
    if botones is None:                               # angosta: un solo botón con todo
        lab = "≡ Menú ▾"
        ww = W(lab) + 4
        xb = w - 1 - ww
        _item(L, s, G, xb, ww, lab, "menu", bool(ab), False, a)
        return {"menu": (xb, ww, True)}
    if largo:
        T.put(w - 7, yl, s.get("hora") or "", C["tx3"])
    anclas = {}
    for rid, lab, xb, ww in botones:
        _item(L, s, G, xb, ww, lab, rid, ab == rid, ACTIVO.get(sec) == rid, a)
        anclas[rid] = (xb, ww, rid in ("ayuda", "ajustes"))
    return anclas


# ── el riel ───────────────────────────────────────────────────────────────────
def estado_riel(a, ahora=None, corto_=False):
    return D.estado_riel(a, ahora, corto_)


def entrada_riel(L, s, i, yk, RW, nombres):
    """Un agente en el riel: 5 filas (su signo arriba y su monito de 4). El elegido se recorta del riel y se une a la
    conversación (una pestaña de pixeles); el mouse encima, un plano P2. Con nombres: nombre, motor y estado."""
    T, a = L.T, s["agentes"][i]
    on, rid = i == s["sel"], "riel:%d" % i
    hov = L.reg(0, yk, RW - 1, 5, rid)
    if on:
        T.fill(1, yk, RW - 1, 5, BG)
        T.put(1, yk, "▟", BG, False, P1)
        T.put(1, yk + 4, "▜", BG, False, P1)
        T.put(RW - 1, yk - 1, "▗", BG, False, P1)
        T.put(RW - 1, yk + 5, "▝", BG, False, P1)
    elif hov or L.apr(rid):
        bloque(T, 1, yk, RW - 2, 5, P3 if L.apr(rid) else P2, P1)
    M.dibujar(T, a, 4, yk + 1, 8, s=s, st=a["st"])
    if not nombres:
        return
    tx, lim = 14, RW - 2
    T.put(tx, yk + 1, corto(a["n"], lim - tx), C["tx"] if (on or hov) else C["tx2"], on)
    T.put(tx, yk + 2, corto(D.motor_riel(s, i), lim - tx), C["tx3"])
    t, col, b = D.estado_riel(a, s.get("ahora"), corto=RW < 30)
    T.put(tx, yk + 3, corto(t, lim - tx), col, b)


def riel(L, s, G):
    """El riel de agentes (planos P1). → {índice: fila} de los que se ven (para el globo)."""
    T, ag, sel = L.T, s["agentes"], s["sel"]
    RW, bh, h = G["RW"], G["bh"], T.h
    nombres = G["nombres"]
    T.fill(0, bh, RW, h - bh, P1)
    L.reg(0, bh, RW, h - bh, "riel")                 # la rueda sobre el riel (los agentes, encima, ganan)
    n = len(ag)
    if nombres:
        yt = G["y_titulo"]
        T.put(2, yt, "Agentes", C["tx3"], True)
        T.right(RW - 2, yt, str(n), C["tx3"])
    y0 = G["y_riel"]
    cabe = cabe_riel(h, y0)
    if n <= cabe:
        i0 = 0
    elif s.get("riel0") is None:
        i0 = max(0, min(sel - cabe // 2, n - cabe))
    else:
        i0 = max(0, min(int(s["riel0"]), n - cabe))
    vis = list(range(i0, min(n, i0 + cabe)))
    pos = {}
    for k, i in enumerate(vis):
        pos[i] = y0 + 6 * k
        entrada_riel(L, s, i, pos[i], RW, nombres)
    if i0 > 0:
        hov = L.reg(0, y0 - 1, RW - 1, 1, "riel:arriba")
        T.put(3, y0 - 1, "▲ %d más" % i0, C["tx"] if hov else C["tx3"])
    resto = n - i0 - len(vis)
    lab, rid = (("▼ %d más" % resto, "riel:abajo") if resto > 0 else
                (("+ Agregar agente" if nombres else "+ Agregar"), "riel:nuevo"))
    hov = L.reg(1, h - 2, RW - 2, 1, rid)
    if hov or L.apr(rid):
        bloque(T, 1, h - 2, min(RW - 2, W(lab) + 4), 1, P4 if L.apr(rid) else P3, P1)
    T.put(3, h - 2, corto(lab, RW - 4), C["tx"] if hov else C["tx3"])
    T.riel = (i0, cabe, n)
    return pos


def borde(L, s, G):
    """El borde del riel: se arrastra (o se toca) para abrir o cerrar el riel con nombres. Se apunta al final, para
    que gane sobre lo de al lado; con el mouse encima (o arrastrándolo) se ve una orilla ▐."""
    T, RW, bh = L.T, G["RW"], G["bh"]
    hov = L.reg(RW - 1, bh, 2, T.h - bh, "riel:borde")
    if hov or s.get("riel_w") is not None:
        col = C["tx3"] if (L.apr("riel:borde") or s.get("riel_w") is not None) else P4
        for yy in range(bh, T.h):
            T.put(RW - 1, yy, "▐", col, False, T.at(RW - 1, yy).bg or P1)
        mid = bh + (T.h - bh) // 2
        T.put(RW - 1, mid, "▐", C["tx"], False, T.at(RW - 1, mid).bg or P1)


def globo(L, s, i, x, y):
    """Lo que dice el monito del riel compacto al pasarle el mouse: su nombre, su motor y su estado (encima de
    todo, un plano P3 con su sombra)."""
    T, a = L.T, s["agentes"][i]
    t, col, b = D.estado_riel(a, s.get("ahora"))
    mot = D.motor_riel(s, i, False)
    w = min(T.w - x - 1, max(W(a["n"]) + 3 + W(mot), W(t)) + 6)
    y = max(0, min(y, T.h - 5))
    limpiar(T, x, y, w, 4, BG)
    bloque(T, x, y, w, 4, P3, BG)
    sombra(T, x, y, w, 4)
    e = T.put(x + 3, y + 1, corto(a["n"], w - 6), C["tx"], True)
    if e + 3 < x + w - 3:
        D._linea_corta(T, e, y + 1, [(" · " + mot, C["tx3"], False)], x + w - 3)
    T.put(x + 3, y + 2, corto(t, w - 6), col, b)


# ── la conversación ───────────────────────────────────────────────────────────
def cabecera(L, s, G, a):
    """«Zenith  ▐ Codex ▾ ▌            trabajando…  ▐ 3 sesiones · 1 te espera ▾ ▌»: el motor y las sesiones se
    tocan (abren su menú)."""
    T, f = L.T, s.get("foto") or {}
    bx, bw, y = G["bx"], G["bw"], G["yh"]
    xx = T.put(bx, y, corto(a["n"], 24), a["c"], True) + 2
    lab = " %s ▾ " % D.nombre_motor(f.get("motor") or a.get("mid"))
    hov = L.reg(xx, y, W(lab) + 2, 1, "hdr:motor")
    xx = ficha(T, xx, y, lab, P4 if L.apr("hdr:motor") else (P3 if hov else P2), BG,
               C["tx"] if hov else C["tx2"])
    cm = f.get("cambio")
    if cm and cm.get("paso") not in ("listo", "error") and cm.get("motor"):
        xx = T.put(xx + 1, y, "→ " + D.nombre_motor(cm["motor"]), C["tx2"])
    xr = bx + bw
    ses = D.texto_sesiones(f.get("sesiones"))
    if ses and W(ses) + 6 < xr - xx - 4:
        lab = " %s ▾ " % ses
        x1 = xr - W(lab) - 2
        hov = L.reg(x1, y, W(lab) + 2, 1, "hdr:sesiones")
        ficha(T, x1, y, lab, P4 if L.apr("hdr:sesiones") else (P3 if hov else P2), BG,
              C["tx"] if hov else C["tx2"])
        xr = x1 - 2
    if s.get("hub_viejo"):
        der, col = D.HUB_VIEJO, ERR
    elif not s.get("conectado", True):
        der, col = "sin conexión con la página", ERR
    elif s.get("scroll"):
        der, col = "viendo lo de antes · AvPág baja", C["tx3"]
    elif s.get("pregunta") and not s.get("permiso"):
        der, col = "te pregunta", C["tx3"]
    else:
        der, col = D.ESTADO_T.get(f.get("estado"), ""), C["tx3"]
    if der and W(der) < xr - xx - 2:
        T.right(xr, y, der, col)


def _acento(T, x, y, h, a, fuera):
    """La orilla izquierda del color del agente (caja de permiso, de pregunta, o la de escribir que contesta)."""
    T.put(x, y, "▗", a["c"], False, fuera)
    for j in range(1, h - 1):
        T.put(x, y + j, "▐", a["c"], False, fuera)
    T.put(x, y + h - 1, "▝", a["c"], False, fuera)


def caja_permiso(pm, a, w, elige):
    """(alto, dibujar(L, s, x, y)): el permiso que pide su motor, en un plano con la orilla del agente y botones
    grandes."""
    txt = D.envolver([(D.permiso_simple(pm), C["tx"], False)], w - 8)[:2]
    det = D.detalle_corto(pm.get("herramienta"), pm.get("detalle"), pm.get("archivo"))
    ops = [] if pm.get("en_terminal") else list(pm.get("opciones") or [])
    alto = 1 + 1 + len(txt) + (1 if det else 0) + (5 if ops else 2)

    def dibujar(L, s, x, y):
        T = L.T
        bloque(T, x, y, w, alto, P2, BG)
        _acento(T, x, y, alto, a, BG)
        T.put(x + 3, y + 1, "%s te pide permiso%s" % (a["n"], " en su terminal" if pm.get("en_terminal") else ""),
              a["c"], True)
        yy = y + 2
        for ln in txt:
            D._linea(T, x + 3, yy, ln, x + w - 3)
            yy += 1
        if det:
            cmd = D.limpio(det).split(" · ", 1)
            T.put(x + 3, yy, corto(("$ " + cmd[1]) if len(cmd) > 1 else cmd[0], w - 8), C["tx3"])
            yy += 1
        if ops:
            yy += 1
            xb = x + 3
            for k, o in enumerate(ops):
                if xb + 14 > x + w - 3:
                    break
                xb = boton(L, s, xb, yy, D.PERMISO_T.get(o, o), "perm:%d" % k, P2, foco=k == elige % len(ops),
                           wmin=14, a=a) + 1
            nota = "←→ elige · Enter contesta"
            if xb + W(nota) + 2 < x + w - 3:
                T.right(x + w - 3, yy + 1, nota, C["tx3"])
        else:
            T.put(x + 3, yy, "Contéstalo en su terminal.", C["tx2"])
    return alto, dibujar


def caja_pregunta(q, a, w, elige):
    """(alto, dibujar(L, s, x, y)): lo que te pregunta una skill, con botones grandes (o la respuesta escrita
    abajo)."""
    txt = D.envolver([(D.limpio(q.get("pregunta")), C["tx"], True)], w - 8)[:3]
    ops = [] if q.get("en_terminal") else D.opciones_pregunta(q)
    alto = 1 + 1 + len(txt) + (5 if ops else 2)

    def dibujar(L, s, x, y):
        T = L.T
        bloque(T, x, y, w, alto, P2, BG)
        _acento(T, x, y, alto, a, BG)
        T.put(x + 3, y + 1, "%s te pregunta" % a["n"], a["c"], True)
        yy = y + 2
        for ln in txt:
            D._linea(T, x + 3, yy, ln, x + w - 3)
            yy += 1
        if q.get("en_terminal"):
            T.put(x + 3, yy, "Tiene formulario: contéstala en su terminal.", C["tx2"])
        elif ops:
            yy += 1
            xb = x + 3
            for k, o in enumerate(ops):
                if xb + max(10, W(o) + 6) > x + w - 3:
                    break
                xb = boton(L, s, xb, yy, o, "preg:%d" % k, P2, foco=k == elige % len(ops), wmin=10, a=a) + 1
            nota = "o escríbela abajo"
            if xb + W(nota) + 2 < x + w - 3:
                T.right(x + w - 3, yy + 1, nota, C["tx3"])
        else:
            T.put(x + 3, yy, "Escribe tu respuesta abajo.", C["tx3"])
    return alto, dibujar


def caja_escribir(L, s, a, bx, bw, y):
    """La caja de escribir: un plano P2 de 3 filas con su botón adentro, «Enviar ↵» (activo con texto) o «■ Parar»
    (mientras trabaja). Si contesta una pregunta, lleva la orilla del agente."""
    T, f = L.T, s.get("foto") or {}
    q = s.get("pregunta")
    abierta = bool(q and not q.get("en_terminal"))
    t = s.get("texto") or ""
    bloque(T, bx, y, bw, 3, P2, BG)
    if abierta:
        _acento(T, bx, y, 3, a, BG)
    trabaja = bool(f.get("trabajando"))
    lab = " ■ Parar " if trabaja else " Enviar ↵ "
    xb = bx + bw - 3 - W(lab) - 2
    L.reg(bx, y, xb - bx - 1, 3, "in:texto")
    activo = trabaja or bool(t.strip())
    hov = L.reg(xb, y, W(lab) + 2, 3, "in:boton") and activo
    col = (P4 if (hov or L.apr("in:boton")) else P3) if activo else P2
    ficha(T, xb, y + 1, lab, col, P2, (C["tx"] if hov else C["tx2"]) if activo else OFF)
    x = T.put(bx + 3, y + 1, "❯", a["c"], True)
    cabe = xb - 2 - (x + 1)
    if t:
        x = T.put(x + 1, y + 1, D._cola_vista(t, max(4, cabe - 1)), C["tx"])
        T.put(x, y + 1, "▏", C["tx"])
    else:
        T.put(x + 1, y + 1, corto("Escribe tu respuesta…" if abierta else "Escríbele a %s…" % a["n"], cabe),
              C["tx3"])


VERBO_MENU = {"motor": "cambia", "sesiones": "abre", "agentes": "cambia", "skills": "arranca", "menu": "abre"}


def teclas(s):
    """La fila de teclas, corta: lo de ahora (Enter, Esc) y F1 para lo demás."""
    f, t = s.get("foto") or {}, s.get("texto") or ""
    esc = "borra" if t else ("para" if f.get("trabajando") else "sale")
    k = abierto(s)
    if k:
        return [("↑↓", "elige"), ("Enter", VERBO_MENU.get(k, "elige")), ("Esc", "cierra"), ("F1", "ayuda")]
    sec = s.get("seccion")
    if sec:
        import hub_secciones as S
        return S.teclas(sec, s)
    if D.opciones_de(s.get("permiso"), s.get("pregunta")) and not t:
        return [("←→", "elige"), ("Enter", "contesta"), ("Esc", esc), ("F1", "ayuda")]
    return [("Enter", "manda"), ("Esc", esc), ("F1", "ayuda")]


def fila_teclas(L, s, G, x):
    T = L.T
    for k, lab in teclas(s):
        if x + W(k) + 3 + (W(lab) + 1 if lab else 0) > T.w:
            break
        x = T.key(x, G["y_teclas"], k, lab)


def conversacion(L, s, G, a):
    """La columna de la conversación: la cabecera, los renglones, lo del momento (aviso, permiso o pregunta, la
    skill que corre), la caja de escribir y las teclas."""
    T = L.T
    bx, bw, yh, y_caja = G["bx"], G["bw"], G["yh"], G["y_caja"]
    L.reg(G["x0"], yh + 1, T.w - G["x0"], max(0, y_caja - yh - 1), "conv")
    cabecera(L, s, G, a)
    abajo = []
    if s.get("aviso"):
        abajo.append((1, lambda L_, s_, x, y: L_.T.center(bx, bw, y, corto(s["aviso"], bw - 2), C["tx2"])))
    if s.get("permiso"):
        alto_, dib = caja_permiso(s["permiso"], a, bw, s.get("elige") or 0)
        abajo.append((alto_ + 1, dib))
    elif s.get("pregunta"):
        alto_, dib = caja_pregunta(s["pregunta"], a, bw, s.get("elige") or 0)
        abajo.append((alto_ + 1, dib))
    e = D.vigente_en(s)
    pe = None if e else D.pendiente_en(s)
    if e or pe:
        alto_f, dib_f = D.franja_skill(e, a, bw) if e else D.franja_pendiente(pe, a, bw)
        abajo.append((alto_f, lambda L_, s_, x, y: dib_f(L_.T, x, y, L_)))
    y, y0 = y_caja, G["y_conv"]
    for alto_, dibujar in abajo:
        if y - alto_ < y0 + 2:
            break                                     # sin lugar: lo de más arriba no cabe
        y -= alto_
        dibujar(L, s, bx, y)
    y1 = y - 1
    cw = bw - 2
    lineas = D.lineas_chat(s, cw)
    alto = max(0, y1 - y0 + 1)
    T.scroll_max = max(0, len(lineas) - alto)
    sc = max(0, min(s.get("scroll") or 0, T.scroll_max))
    fin = len(lineas) - sc
    vis = lineas[max(0, fin - alto):fin]
    if not lineas:
        for i, txt in enumerate(("Escríbele a %s." % a["n"], "Es la misma conversación que en el navegador.")):
            T.center(bx, bw, y0 + max(0, alto // 2 - 1) + i, corto(txt, cw - 2), C["tx3"])
    for i, ln in enumerate(vis):
        D._linea(T, bx + 1, y0 + i, ln, bx + 1 + cw)
    caja_escribir(L, s, a, bx, bw, y_caja)
    fila_teclas(L, s, G, bx if not G.get("N") else 1)


# ── los menús que bajan de la barra ───────────────────────────────────────────
def _alto_fila(r):
    return 2 if r.get("sub") else 1


def _ancho_fila(r):
    if r.get("sep"):
        return 0
    if r.get("nota"):
        return 6 + sum(W(t) for t, _f, _b in r["nota"])
    if r.get("teclas"):
        return 6 + sum(W(k) + 4 + W(lab) for k, lab in r["teclas"])
    der = r.get("der") or ""
    return 9 + sum(W(t) for t, _f, _b in r["segs"]) + (W(der) + 2 if der else 0)


def menu_caja(L, s, kind, x, y, derecha=False):
    """El menú `kind` en (x, y): un plano P2 con medio pixel de sombra, su título en mayúsculas y su tecla, y sus
    filas (la elegida, un gris más y la orilla del agente). Primero se apunta su caja entera (menu:caja), para que
    un clic en su borde no llegue a lo de abajo. → (x, y, ancho, alto)."""
    T = L.T
    a = agente(s)
    titulo, tecla, filas, ancho, elegida = filas_menu(kind, s, T.w)
    if kind != "sesiones":
        ancho = max([ancho, W(titulo) + W(tecla) + 10] + [_ancho_fila(r) for r in filas])
    w = max(14, min(T.w - 1, ancho))
    if derecha:
        x = x - w + 1
    x = max(0, min(x, T.w - w - 1))
    vis, i0, i1, pie, n = menu_ventana(filas, elegida, max(1, T.h - y - 6))
    alto = 4 + sum(_alto_fila(r) for r in vis)
    L.reg(x, y, w, alto, "menu:caja")
    limpiar(T, x, y, w, alto, P2)
    bloque(T, x, y, w, alto, P2, BG)
    sombra(T, x, y, w, alto)
    T.put(x + 3, y + 1, corto(titulo.upper(), w - W(tecla) - 8), C["tx3"], True)
    if tecla:
        T.right(x + w - 3, y + 1, tecla, C["tx3"])
    if i0 > 0:
        T.put(x + w - 2, y + 3, "▲", C["tx2"], False, P2)
    if i1 < n:
        T.put(x + w - 2, y + alto - 2 - sum(_alto_fila(r) for r in pie), "▼", C["tx2"], False, P2)
    filas_caja(L, s, a, vis, elegida, x, y + 3, w)
    return x, y, w, alto


def menu_ventana(filas, elegida, cabe):
    """Qué filas de un menú se ven en `cabe` filas de pantalla: (vis, i0, i1, pie, cuántas). Lo de después del último
    separador (el pie) se queda siempre a la vista; lo demás crece alrededor de la elegida."""
    seps = [n for n, r in enumerate(filas) if r.get("sep")]
    pie = []                                          # lo de después del último separador se queda siempre a la vista
    if seps and len(filas) - seps[-1] <= 4 and sum(_alto_fila(r) for r in filas) > cabe:
        pie, filas = filas[seps[-1]:], filas[:seps[-1]]
        cabe = max(1, cabe - sum(_alto_fila(r) for r in pie))
    altos = [_alto_fila(r) for r in filas]
    i0, i1 = 0, len(filas)
    if sum(altos) > cabe:
        k = next((n for n, r in enumerate(filas) if r.get("rid") == elegida), 0)
        i0 = k
        usado = altos[k] if filas else 0
        i1 = k + 1
        while True:                                   # crece hacia los dos lados alrededor de la elegida
            crecio = False
            if i0 > 0 and usado + altos[i0 - 1] <= cabe:
                i0 -= 1
                usado += altos[i0]
                crecio = True
            if i1 < len(filas) and usado + altos[i1] <= cabe:
                usado += altos[i1]
                i1 += 1
                crecio = True
            if not crecio:
                break
    return filas[i0:i1] + pie, i0, i1, pie, len(filas)


def filas_caja(L, s, a, vis, elegida, x, yy, w, marca=None, sep=None):
    """Las filas `vis` de un menú desde la fila `yy` en una caja de `w` (x..x+w-1). `marca(T, y, alto)`: cómo se
    marca la elegida (por omisión, la orilla ▌ del agente en x+1); `sep(T, y)`: cómo va un separador."""
    T = L.T
    for r in vis:
        if r.get("sep") and sep:
            sep(T, yy)
        elif r.get("sep"):
            T.put(x + 3, yy, "▔" * (w - 6), P4, False, P2)
        elif r.get("nota"):
            D._linea_corta(T, x + 3, yy, r["nota"], x + w - 3)
        elif r.get("teclas"):
            xx = x + 3
            for k, lab in r["teclas"]:
                if xx + W(k) + 3 + W(lab) > x + w - 2:
                    break
                xx = T.key(xx, yy, k, lab)
        else:
            rid, dim = r["rid"], r.get("dim")
            on = rid == elegida and not dim
            hf = _alto_fila(r)
            if not dim:
                L.reg(x + 1, yy, w - 2, hf, rid)
            if on or L.apr(rid):
                T.fill(x + 1, yy, w - 2, hf, P4 if L.apr(rid) else P3)
            if on and marca:
                marca(T, yy, hf)
            elif on:
                for j in range(hf):
                    T.put(x + 1, yy + j, "▌", a["c"])
            if r.get("check"):
                T.put(x + 3, yy, "✓", a["c"], True)
            segs = [(t, C["tx"] if on and fg == C["tx2"] else fg, b or (on and fg == C["tx2"]))
                    for t, fg, b in r["segs"]]
            der = r.get("der") or ""
            libre, nw = w - 9, sum(W(t) for t, _f, _b in segs)
            if der and nw + W(der) + 2 > libre:      # no cabe: lo de la derecha se acorta antes que el nombre
                deja = libre - min(nw, libre * 2 // 3) - 2
                der = corto(der, deja) if deja >= 6 else ""
            sobra = libre - nw - (W(der) + 2 if der else 0)
            if r.get("extra") and sobra >= 8:
                segs = segs + r["extra"]
            D._linea_corta(T, x + 5, yy, segs, x + w - 3 - (W(der) + 2 if der else 0))
            if der:
                T.right(x + w - 3, yy, der, C["tx3"])
            if r.get("sub"):
                D._linea_corta(T, x + 5, yy + 1, r["sub"], x + w - 3)
        yy += _alto_fila(r)


def filas_menu(kind, s, w=200):
    """Lo que tiene cada menú que baja: (título, su tecla, filas, ancho, la fila elegida). Cada fila es {rid, segs,
    check, dim, der, sub, extra}, {sep}, {nota: segs} o {teclas: [(tecla, qué)]}. Lo mismo para dibujarlo y para
    moverse con ↑↓."""
    ag, sel = s.get("agentes") or [], s.get("sel") or 0
    a = agente(s)
    f = s.get("foto") or {}
    actual = f.get("motor") or a.get("mid")
    filas = []
    if kind == "motor":
        m = s.get("menu") or {"filas": [], "i": 0}
        if f.get("trabajando"):
            filas.append({"nota": [("Está trabajando: ■ Parar antes de cambiar.", C["tx2"], False)]})
        for r in m["filas"]:
            segs = [(r["nombre"], C["tx2"] if r["ok"] else C["tx3"], False)]
            if not r["ok"] and r.get("sub"):
                segs.append((" · " + r["sub"], C["tx3"], False))
            filas.append({"rid": "mo:" + r["id"], "segs": segs, "check": r["id"] == actual, "dim": not r["ok"],
                          "der": "ahora" if r["id"] == actual else ""})
        filas.append({"sep": True})
        filas.append({"rid": "mo:seccion", "segs": [("Motores y conexiones", C["tx2"], False)], "der": "→"})
        i, n = m.get("i", 0), m.get("n", len(m["filas"]))
        elegida = "mo:" + m["filas"][i]["id"] if 0 <= i < min(n, len(m["filas"])) else "mo:seccion"
        return "Motor de esta conversación", "^E", filas, 46, elegida
    if kind == "sesiones":
        m = s.get("sesiones") or {"filas": [], "i": 0}
        ids = []
        for r in m["filas"]:
            t = r.get("tipo")
            if t == "conv":
                ids.append("se:conv")
                filas.append({"rid": "se:conv", "segs": [("◆ ", a["c"], True), ("Conversación directa", C["tx"],
                                                                                 False)],
                              "der": "%s · aquí" % D.nombre_motor(actual)})
            elif t == "nueva":
                ids.append("se:nueva")
                filas.append({"sep": True})
                filas.append({"rid": "se:nueva", "segs": [("+ ", a["c"], True),
                                                          ("Nueva sesión en %s" % D.nombre_motor(actual), C["tx2"],
                                                           False)]})
            elif t == "seccion":
                ids.append("se:seccion")
                filas.append({"rid": "se:seccion", "segs": [("  Todas las sesiones", C["tx2"], False)], "der": "→"})
            else:
                ico, est = D.ESTADO_SES.get(r.get("estado"), ("·", ""))
                vivo = r.get("estado") in ("trabajando", "te_espera")
                espera = r.get("estado") == "te_espera"
                cuando = D.hace(r.get("cuando"), s.get("ahora"))
                sub = [(est + (" · " + cuando if cuando else ""), a["c"] if espera else C["tx3"], espera)]
                ids.append("se:" + str(r.get("wid")))
                filas.append({"rid": ids[-1], "segs": [(ico + " ", a["c"] if vivo else C["tx3"], vivo),
                                                       (D.limpio(r.get("nombre")) or "Sin nombre", C["tx2"], False)],
                              "der": D.nombre_motor(r.get("motor")), "sub": sub})
        if m.get("cargando"):
            filas.insert(1, {"nota": [("Buscando sus sesiones…", C["tx3"], False)]})
        elif not any(r.get("tipo") == "sesion" for r in m["filas"]):
            filas.insert(1, {"nota": [("Todavía no tiene sesiones en su motor.", C["tx3"], False)]})
        elegida = ids[m["i"]] if 0 <= m.get("i", 0) < len(ids) else ""
        return "Sesiones de %s" % a["n"], "^S", filas, 62, elegida
    if kind == "tabs":                                 # H4-a: «+» de las pestañas (^T)
        m = s.get("tabmenu") or {"filas": [], "i": 0}
        hubo = False
        for r in m["filas"]:
            t, rid = r.get("tipo"), D.rid_tab(r)
            if t == "deshacer":
                filas.append({"rid": rid, "segs": [("↶ ", a["c"], True), ("Volver a abrir «%s»" % D.limpio(
                    r.get("nombre")), C["tx2"], False)]})
                filas.append({"sep": True})
            elif t == "nueva" and not r.get("otra"):
                filas.append({"rid": rid, "segs": [("+ ", a["c"], True), ("Conversación nueva", C["tx"], False)],
                              "der": "en " + D.nombre_motor(r.get("motor"))})
            elif t == "nueva":
                filas.append({"rid": rid, "segs": [("  Nueva con %s" % D.nombre_motor(r.get("motor")), C["tx2"],
                                                    False)]})
            elif t == "sesion":
                if not hubo:
                    filas.append({"sep": True})
                    filas.append({"nota": [("SUS SESIONES", C["tx3"], True),
                                           (" · las mismas que abres en su programa oficial", C["tx3"], False)]})
                    hubo = True
                ico, est = D.ESTADO_SES.get(r.get("estado"), ("·", ""))
                vivo = r.get("estado") in ("trabajando", "te_espera")
                cuando = D.hace(r.get("cuando"), s.get("ahora"))
                filas.append({"rid": rid, "segs": [(ico + " ", a["c"] if vivo else C["tx3"], vivo),
                                                   (D.limpio(r.get("nombre")) or "Sin nombre", C["tx2"], False)],
                              "der": "ya abierta" if r.get("ya") else D.nombre_motor(r.get("motor")),
                              "sub": [((D.nombre_motor(r.get("motor")) + " · " if r.get("ya") else "") +
                                       (cuando or est), C["tx3"], False)]})
            elif t == "todas":
                if m.get("cargando") and not hubo:
                    filas.append({"nota": [("Buscando sus sesiones…", C["tx3"], False)]})
                filas.append({"sep": True})
                filas.append({"rid": rid, "segs": [("  Todas sus sesiones…", C["tx2"], False)], "der": "S"})
        i = m.get("i", 0)
        elegida = D.rid_tab(m["filas"][i]) if 0 <= i < len(m["filas"]) else ""
        return "Abrir en una pestaña", "^T", filas, 64, elegida
    b = s.get("barra") or {}
    if kind == "agentes":
        for i, x in enumerate(ag):
            filas.append({"rid": "ag:%d" % i, "segs": [("● ", x["c"], False), (x["n"], C["tx2"], False)],
                          "check": i == sel, "der": D.motor_riel(s, i, False)})
        filas.append({"sep": True})
        filas.append({"rid": "ag:nuevo", "segs": [("+ ", a["c"], True), ("Agregar agente", C["tx2"], False)]})
        if w >= ANCHO_NOMBRES:
            filas.append({"rid": "ag:riel", "segs": [("Riel con nombres", C["tx2"], False)],
                          "check": bool(s.get("riel_nombres")), "der": "o arrastra su borde"})
        filas.append({"rid": "ag:seccion", "segs": [("  Ver y editar agentes", C["tx2"], False)], "der": "→"})
        titulo, tecla, ancho = "Agentes", "Tab", 44
    elif kind == "skills":
        lista = s.get("skills") or []
        filtro = (s.get("texto") or "")[1:].strip() if b.get("slash") else ""
        if not lista:
            filas.append({"nota": [("Buscando sus skills…" if s.get("skills_cargando") else
                                    ("Ninguna dice «%s»." % corto(filtro, 24) if filtro else
                                     "Todavía no tiene skills."), C["tx3"], False)]})
        for x in lista:
            filas.append({"rid": "sk:" + x["nombre"], "segs": [("▸ ", a["c"], False),
                                                               (D.nombre_skill(x["nombre"]), C["tx2"], False)],
                          "der": corto(D.limpio(x.get("descripcion")), 30)})
        filas.append({"sep": True})
        filas.append({"rid": "sk:seccion", "segs": [("  Todas sus skills", C["tx2"], False)], "der": "→"})
        filas.append({"rid": "sk:pagina", "segs": [("  En la página", C["tx2"], False)], "der": "↗"})
        titulo, tecla, ancho = "Skills de %s" % a["n"], "/", 58
    elif kind == "menu":
        for rid, lab, der in (("mn:agentes", "Agentes", ""), ("mn:motor", "Motor", ""),
                              ("mn:sesiones", "Sesiones", ""), ("mn:skills", "Skills", ""),
                              ("mn:abrir", "Abrir en su motor ↗", ""), ("mn:ajustes", "Ajustes", ""),
                              ("mn:ayuda", "Ayuda", ""), ("mn:salir", "Salir", "")):
            filas.append({"rid": rid, "segs": [(lab, C["tx2"], False)], "der": der})
        titulo, tecla, ancho = "Menú", "", 34
    else:
        raise ValueError(kind)
    rids = [r["rid"] for r in filas if r.get("rid") and not r.get("dim")]
    elegida = b.get("rid") if b.get("rid") in rids else (rids[0] if rids else "")
    return titulo, tecla, filas, ancho, elegida


# ── la pantalla ───────────────────────────────────────────────────────────────
def pantalla(w, h, s):
    """La pantalla del hub con la piel T-2: la barra, el riel y la conversación del elegido o la sección abierta, y
    encima el globo y el menú que baja. → Term, con `zonas`, `riel` y `scroll_max`."""
    T = P.Term(w, h)
    T.scroll_max, T.riel = 0, None
    T.fill(0, 0, w, h, BG)
    if w < P.MIN_W or h < P.MIN_H:
        T.center(0, w, h // 2, "Agranda la ventana", C["tx2"])
        return T
    L = Lienzo(T, s)
    ag = s.get("agentes") or []
    G = geometria(w, h, s.get("riel_nombres"), s.get("riel_w"))
    if not ag:
        barra(L, s, G, None)
        T.center(0, w, h // 2, corto("Todavía no tienes agentes: agrégalos desde `workspace agentes`.", w - 2),
                 C["tx2"])
        return T
    a = ag[s["sel"]]
    anclas = barra(L, s, G, a)
    pos = {}
    sec = s.get("seccion")
    if G["modo"] == "riel":
        pos = riel(L, s, G)
    if sec:
        import hub_secciones as S
        S.pantalla(L, s, G, sec)
    else:
        if G["modo"] == "fila":
            D._monitos(T, s, w, G["N"], G["y_mon"], L)
        conversacion(L, s, G, a)
    if G["modo"] == "riel":
        borde(L, s, G)
    T.flat()
    sobre = s.get("sobre") or ""
    if G["modo"] == "riel" and not G["nombres"] and sobre.startswith("riel:") and sobre[5:].isdigit():
        i = int(sobre[5:])
        if i in pos:                                  # junto a su monito, sin tapar la caja de escribir
            globo(L, s, i, G["RW"] + 1, max(G["bh"], min(pos[i], G["y_caja"] - 5)))
    k = abierto(s)
    if k:
        xb, wb, der = anclas.get(k) or anclas.get("menu") or (0, 0, False)
        menu_caja(L, s, k, xb + wb - 1 if der else xb, G["bh"], derecha=der)
    return T
