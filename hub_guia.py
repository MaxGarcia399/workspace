#!/usr/bin/env python3
r"""WORKSPACE · hub_guia — H5-a «Recorrido con foco»: la guía del hub.

Cinco pasos sobre Inicio: cada uno apaga todo menos una parte (la tarjeta del agente, su motor, sus dos acciones, las
secciones y lo de arriba), la rodea con el color del agente y la explica en una frase, con «Siguiente ↵», «← Atrás» y
«Esc sale». Se abre con «? Guía» (arriba a la derecha de Inicio y al pie del riel en la conversación), con la tecla ?
y, una sola vez, sola la primera vez que abres el hub (se recuerda en las preferencias del hub).

Aquí se dibuja (puro, con la instantánea del hub y la pantalla de Inicio ya pintada); qué hace cada tecla o clic está
en hub_directo.Directo. Si una pantalla cambia, PASOS cambia con ella: la prueba revisa que cada paso encuentre su
parte. Stdlib."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_paleta as P  # noqa: E402
import hub_bloque as B  # noqa: E402

C = P.C
W, corto = B.W, B.corto

#: Los pasos: (parte, título, lo que dice).
PASOS = (
    ("tarjeta", "Tus agentes", "Cada monito es un agente con su cerebro. ←→ o un clic trae al de al lado."),
    ("motor", "Su motor", "Con qué programa piensa (Claude Code, Codex…). ↑↓ o ▲▼ lo cambia; se guarda solo."),
    ("acciones", "Hablarle", "«Conversar» le escribe aquí mismo. «Sesiones» abre las de su programa oficial."),
    ("secciones", "Todo lo demás", "Agentes, motores, skills, calendario, ajustes y ayuda. Tab llega aquí."),
    ("arriba", "Siempre a la mano", "El navegador tiene lo mismo. Si te pierdes: ? Guía, cuando quieras."),
)
#: Cuánto se apaga lo que no es el paso (0 igual, 1 = el fondo).
APAGA = 0.72
ANCHO, ALTO = 46, 10


def _union(T, pref):
    zs = [z for z in T.zonas if any(z[4] == p or (p.endswith(":") and z[4].startswith(p)) for p in pref)]
    if not zs:
        return None
    x0, y0 = min(z[0] for z in zs), min(z[1] for z in zs)
    x1, y1 = max(z[0] + z[2] for z in zs), max(z[1] + z[3] for z in zs)
    return x0, y0, x1 - x0, y1 - y0


def partes(T, s):
    """{parte: (x, y, ancho, alto)} de lo que explica cada paso, en la pantalla de Inicio ya pintada (por sus zonas y
    su geometría). Una parte que no se ve queda en None."""
    a = B.agente(s)
    aid = a.get("id") or ""
    g = getattr(T, "geo", None) or {}
    tarjeta = g.get("tarjeta") if T.h >= 30 else None      # en la chica, solo su monito y su nombre (cabe la ficha)
    if tarjeta is None:
        z = _union(T, ("ini:card:" + aid,))
        tarjeta = (z[0] - 2, z[1], z[2] + 4, z[3] + 2) if z else g.get("tarjeta")
    return {"tarjeta": tarjeta,
            "motor": _union(T, ("ini:mot:actual", "ini:mot:arriba", "ini:mot:abajo")),
            "acciones": _union(T, ("ini:conv:" + aid, "ini:ses:" + aid)),
            "secciones": g.get("secciones") or _union(T, ("ini:sec:",)),
            "arriba": _union(T, ("ini:buscar", "ini:web", "bar:guia", "bar:salir"))}


def alto_ficha(h):
    return ALTO if h >= 30 else ALTO - 1


def _globo(L, x, y, n, tit, txt, a):
    """La ficha del paso: «n de 5 · título», lo que dice y sus botones. → su caja."""
    import hub_h1 as H
    import hub_directo as D
    T = L.T
    w, h = min(ANCHO, T.w - 2), alto_ficha(T.h)
    x = max(1, min(x, T.w - w - 1))
    y = max(1, min(y, T.h - h - 2))
    B.limpiar(T, x, y, w, h, B.P2)
    H.area(L, x, y, w, h, B.P2, titulo=[("%d de %d" % (n, len(PASOS)), a["c"], True), (" · " + tit, C["tx"], True)],
           der=[(" Esc sale ", C["tx3"], False, "guia:salir")], foco_a=a)
    B.sombra(T, x, y, w, h)
    yy = y + 2
    for ln in D.envolver([(txt, C["tx2"], False)], w - 6)[:h - 6]:
        D._linea(T, x + 3, yy, ln, x + w - 3)
        yy += 1
    yb = y + h - 3
    lab = " Listo ↵ " if n == len(PASOS) else " Siguiente ↵ "
    hs = L.reg(x + 3, yb, W(lab) + 2, 1, "guia:sig")
    xb = B.ficha(T, x + 3, yb, lab, P.mix(a["c"], "#ffffff", 0.18) if hs else a["c"], B.P2, B.LUZTX, True)
    if n > 1:
        ha = L.reg(xb + 1, yb, W(" ← Atrás ") + 2, 1, "guia:atras")
        B.ficha(T, xb + 1, yb, " ← Atrás ", B.P4 if ha else B.P3, B.P2, C["tx"] if ha else C["tx2"])
    xp = x + w - 3 - 2 * len(PASOS)
    for k in range(len(PASOS)):
        T.put(xp + 2 * k, yb, "■" if k + 1 == n else "▪", a["c"] if k + 1 <= n else B.OFF, True, B.P2)
    return x, y, w, h


def _lugar(r, w, h):
    """Dónde va la ficha del paso: a la derecha de la parte, si cabe; si no, a la izquierda, abajo o arriba (sin
    taparla)."""
    x, y, rw, rh = r
    al = alto_ficha(h)
    if x + rw + 3 + ANCHO < w:
        return x + rw + 3, y
    if x - 3 - ANCHO > 0:
        return x - 3 - ANCHO, y
    if y + rh + 1 + al <= h - 1:
        return x + (rw - ANCHO) // 2, y + rh + 1
    return x + (rw - ANCHO) // 2, max(0, y - al - 1)


def pantalla(w, h, s, inicio):
    """El paso `s["guia"]["paso"]` sobre `inicio` (la pantalla de Inicio ya afinada): todo apagado menos su parte, su
    marco del color del agente y la ficha del paso. → Term con solo las zonas de la ficha (lo demás no se toca)."""
    import hub_h1 as H
    T = inicio
    a = B.agente(s)
    n = max(0, min(int((s.get("guia") or {}).get("paso") or 0), len(PASOS) - 1))
    parte, tit, txt = PASOS[n]
    r = partes(T, s).get(parte)
    fondo = P._colores_afinados(None, B.BG, False, ((s.get("datos") or {}).get("preferencias") or {}).get("fondo"))[1]
    for y in range(T.h):
        for x in range(T.w):
            if r and r[0] - 1 <= x < r[0] + r[2] + 1 and r[1] <= y < r[1] + r[3]:
                continue
            k = T.cl[y * T.w + x]
            k.fg, k.bg = P.mix(k.fg or P.T_FG, fondo, APAGA), P.mix(k.bg or fondo, fondo, APAGA)
    U = P.Term(T.w, T.h)
    marca = "#010203"
    U.fill(0, 0, U.w, U.h, marca)
    L = B.Lienzo(U, s)
    if r:
        x, y, rw, rh = r[0] - 2, r[1] - 1, r[2] + 4, r[3] + 2
        x, y = max(0, x), max(0, y)
        rw, rh = min(rw, T.w - x), min(rh, T.h - 1 - y)
        U.put(x, y, "╭" + "─" * (rw - 2) + "╮", a["c"])
        for j in range(1, rh - 1):
            U.put(x, y + j, "│", a["c"])
            U.put(x + rw - 1, y + j, "│", a["c"])
        U.put(x, y + rh - 1, "╰" + "─" * (rw - 2) + "╯", a["c"])
        gx, gy = _lugar(r, T.w, T.h)
    else:
        gx, gy = (T.w - ANCHO) // 2, (T.h - ALTO) // 2
    _globo(L, gx, gy, n + 1, tit, txt, a)
    U.put(0, U.h - 1, " " * U.w, None, False, B.P1)
    xx = U.put(1, U.h - 1, "❯", a["c"], True, B.P1)
    xx = U.put(xx + 1, U.h - 1, "workspace", C["tx"], True, B.P1) + 3
    H.teclas_borde(U, xx, U.h - 1, U.w - 2, [("Enter", "siguiente"), ("←", "atrás"), ("Esc", "sale")], B.P1)
    sin_fondo = {i for i, k in enumerate(U.cl) if k.bg == marca and k.ch != " "}
    tocadas = [i for i, k in enumerate(U.cl) if k.bg != marca or k.ch != " "]
    P.afinar(U, ((s.get("datos") or {}).get("preferencias") or {}).get("fondo"))
    for i in tocadas:
        k, d = U.cl[i], T.cl[i]
        d.ch, d.fg, d.b, d.px = k.ch, k.fg, k.b, k.px
        if i not in sin_fondo:
            d.bg = k.bg
    T.zonas = list(U.zonas)
    T.focos = []
    return T
