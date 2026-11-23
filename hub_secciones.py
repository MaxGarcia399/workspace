#!/usr/bin/env python3
r"""WORKSPACE · hub_secciones — las secciones del hub con la piel T-2 (la versión de Zenith). SOLO PARA PROBAR: vive
en la rama zenith/hub-bloque y nunca entra a main.

Cada sección es la de la página, en la terminal, con los mismos datos y las mismas rutas del servidor local (no se
inventa nada): una lista a la izquierda y el detalle de lo elegido a la derecha (con menos de ~94 columnas, primero
la lista y Enter abre el detalle). El riel compacto se queda: tocar un monito cambia la sección a ese agente.

  · Sesiones: las de cada agente, con su conversación directa primero; filtros Todas · Trabajando · Te esperan ·
    Cerradas; el detalle con «Retomar en su motor», «Archivar» y «Nueva sesión».

Aquí se dibuja y se arma la lista de cada sección (puro: lo mismo para pintar y para moverse con ↑↓); lo que hace
cada tecla o clic está en hub_directo.Directo. Stdlib."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_paleta as P  # noqa: E402
import hub_directo as D  # noqa: E402
import hub_bloque as B  # noqa: E402
import hub_monitos  # noqa: E402

C, ERR = P.C, P.ERR
W, corto = B.W, B.corto
TITULOS = {"sesiones": "Sesiones", "skills": "Skills", "motores": "Motores y conexiones", "ajustes": "Ajustes",
           "agentes": "Agentes", "ayuda": "Ayuda"}
#: Desde este ancho (sin el riel) la lista y el detalle van lado a lado; abajo, primero la lista y Enter abre el
#: detalle.
LADO_A_LADO = 96


# ── el marco de una sección ───────────────────────────────────────────────────
def marco(L, s, G, sec):
    """El encabezado (▛▀ TÍTULO y «✕ Volver a la conversación») y dónde va cada cosa. → dict con xl, wl (la lista),
    xd, wd (el detalle), yt (el título), y0..y1 (las filas de la lista) y si van lado a lado."""
    T = L.T
    x0 = G["x0"]
    avail = T.w - x0 - 4
    lado = avail >= LADO_A_LADO
    yt = G["bh"] + 1
    xl = x0 + 2
    if lado:
        wd = max(34, min(50, avail * 36 // 100))
        wl = avail - wd - 2
        xd = xl + wl + 2
    else:
        wl = wd = avail
        xd = xl
    a = B.agente(s)
    T.put(xl, yt, "▛▀", a["c"])
    T.put(xl + 3, yt, TITULOS[sec["kind"]].upper(), C["tx"], True)
    lab = " ✕ Volver a la conversación " if wl >= 52 else " ✕ Volver "
    xv = xl + wl - W(lab) - 2
    hov = L.reg(xv, yt, W(lab) + 2, 1, "sec:volver")
    B.ficha(T, xv, yt, lab, B.P4 if L.apr("sec:volver") else (B.P3 if hov else B.P2), B.BG,
            C["tx"] if hov else C["tx2"])
    T.lado = lado
    M = {"xl": xl, "wl": wl, "xd": xd, "wd": wd, "yt": yt, "yd": yt if lado else yt + 2, "y0": yt + 4,
         "y1": T.h - 3, "lado": lado,
         "detalle": lado or bool(sec.get("abierto"))}
    if not lado and sec.get("abierto"):              # angosta: el detalle en lugar de la lista
        lab = " ‹ Lista "
        xx = xv - W(lab) - 3
        hov = L.reg(xx, yt, W(lab) + 2, 1, "sec:lista")
        B.ficha(T, xx, yt, lab, B.P3 if hov else B.P2, B.BG, C["tx"] if hov else C["tx2"])
    return M


def ventana(altos, k, cabe):
    """Qué filas se ven (i0, i1) con la `k` (la elegida) a la vista: hasta donde quepan `cabe` filas de pantalla."""
    if sum(altos) <= cabe:
        return 0, len(altos)
    i0 = k
    usado = altos[k] if 0 <= k < len(altos) else 0
    while i0 > 0 and usado + altos[i0 - 1] <= cabe * 2 // 3:   # la elegida a un tercio de arriba
        i0 -= 1
        usado += altos[i0]
    i1 = k + 1
    while i1 < len(altos) and usado + altos[i1] <= cabe:
        usado += altos[i1]
        i1 += 1
    while i0 > 0 and usado + altos[i0 - 1] <= cabe:
        i0 -= 1
        usado += altos[i0]
    return i0, i1


def kv(T, x, y, k, v, vcol=None, kw=10, limite=None):
    T.put(x, y, k, C["tx3"])
    partes = v if isinstance(v, list) else [(v, vcol or C["tx"], False)]
    D._linea_corta(T, x + kw, y, partes, limite or T.w)


def parrafo(T, x, y, texto, ancho, fg=None, maximo=4):
    """Un texto envuelto en `ancho` columnas, desde (x, y). → la fila siguiente."""
    for ln in D.envolver([(texto, fg or C["tx3"], False)], ancho)[:maximo]:
        D._linea(T, x, y, ln, x + ancho)
        y += 1
    return y


def detalle_vacio(L, M, texto):
    T = L.T
    alto = T.h - 2 - M["yd"]
    B.bloque(T, M["xd"], M["yd"], M["wd"], alto, B.P2, B.BG)
    parrafo(T, M["xd"] + 3, M["yd"] + 2, texto, M["wd"] - 6)


# ── Sesiones ──────────────────────────────────────────────────────────────────
FILTROS = (("todas", "Todas"), ("trabajando", "Trabajando"), ("espera", "Te esperan"), ("cerradas", "Cerradas"))
_FILTRO_ESTADO = {"trabajando": ("trabajando",), "espera": ("te_espera",), "cerradas": ("cerrada",)}


def _pasa(filtro, r):
    return filtro == "todas" or r.get("estado") in _FILTRO_ESTADO.get(filtro, ())


def sesiones_filas(s):
    """La lista de Sesiones: (filtros [(id, etiqueta, cuántas)], filas, sin_sesiones). Cada fila es {tipo: grupo,
    aid} · {tipo: conv, rid, aid} · {tipo: sesion, rid, aid, r}. Puro: lo mismo para dibujarla y para ↑↓."""
    sec = s.get("seccion") or {}
    todas = s.get("ses_todas") or {}
    filtro = sec.get("filtro") or "todas"
    solo = sec.get("agente")
    ag = s.get("agentes") or []
    vistos = [a for a in ag if not solo or a["id"] == solo]
    cuenta = {k: 0 for k, _ in FILTROS}
    for a in vistos:
        for r in todas.get(a["id"]) or []:
            for k, _ in FILTROS:
                if _pasa(k, r):
                    cuenta[k] += 1
    filas, sin = [], []
    for a in vistos:
        if filas and filas[-1]["tipo"] != "hueco":
            filas.append({"tipo": "hueco"})
        lista = [r for r in todas.get(a["id"]) or [] if r.get("wid")]
        mostrar = [r for r in lista if _pasa(filtro, r) and coincide(sec, r.get("nombre"), a["n"])]
        if filtro == "todas":
            if not lista and not solo:
                sin.append(a)
                continue
        elif not mostrar:
            continue
        filas.append({"tipo": "grupo", "aid": a["id"], "n": len(lista)})
        if filtro == "todas":
            filas.append({"tipo": "conv", "rid": "ses:%s:conv" % a["id"], "aid": a["id"]})
        for r in mostrar:
            filas.append({"tipo": "sesion", "rid": "ses:%s:%s" % (a["id"], r["wid"]), "aid": a["id"], "r": r})
    while filas and filas[-1]["tipo"] == "hueco":
        filas.pop()
    return [(k, lab, cuenta[k]) for k, lab in FILTROS], filas, sin


def elegida(sec, filas):
    """La fila elegida de la sección (la que dice `sec["sel"]`, si sigue ahí; si no, la primera que se elige)."""
    rids = [f["rid"] for f in filas if f.get("rid")]
    return sec.get("sel") if sec.get("sel") in rids else (rids[0] if rids else "")


def _por_id(s, aid):
    for i, a in enumerate(s.get("agentes") or []):
        if a["id"] == aid:
            return i, a
    return None, None


def _est_ses(r, a):
    """(ícono, su color, la palabra, su color, negrita) del estado de una sesión."""
    ico, pal = D.ESTADO_SES.get(r.get("estado"), ("·", r.get("estado") or ""))
    if r.get("estado") == "trabajando":
        return ico, a["c"], pal, C["tx2"], False
    if r.get("estado") == "te_espera":
        return ico, a["c"], pal, a["c"], True
    if r.get("estado") == "abierta":
        return ico, C["tx2"], pal, C["tx2"], False
    return ico, C["tx3"], pal, C["tx3"], False


def _est_conv(a):
    st = a.get("st")
    if st == "trabaja":
        return "trabajando", C["tx2"], False
    if st == "pregunta":
        return "te espera", a["c"], True
    if st == "error":
        return "con un problema", ERR, True
    if st == "duerme":
        return "sin abrir", C["tx3"], False
    return "libre", C["tx3"], False


def _alto_fila(f):
    """Una fila de la lista: el grupo y el hueco, 1; una sesión o una conversación, 2 (con lo último que dijo) o 1
    (si no dijo nada)."""
    if f["tipo"] in ("grupo", "hueco"):
        return 1
    if f["tipo"] == "conv":
        return 2
    return 2 if ((f.get("r") or {}).get("ultimo") or {}).get("texto") else 1


def _motor_txt(m):
    """El nombre del motor, o '' si no se sabe (no «su motor»)."""
    return D.nombre_motor(m) if m else ""


def _hace_corto(ts, ahora):
    return D.hace(ts, ahora).replace("hace ", "")


def sesiones_lista(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    filtros, filas, sin = sesiones_filas(s)
    sel = elegida(sec, filas)
    xx = xl
    for k, lab, n in filtros:
        t = " %s %d " % (lab, n)
        if xx + W(t) + 2 > xl + wl:
            break
        xx = B.chip(L, xx, yt + 2, t, "fil:" + k, activo=(sec.get("filtro") or "todas") == k)
        xx += 1
    solo = sec.get("agente")
    if solo:
        _i, a = _por_id(s, solo)
        if a and xx + W(a["n"]) + 12 < xl + wl:
            B.chip(L, xx + 1, yt + 2, " solo %s ✕ " % a["n"], "fil:agente", base=B.P2)
    L.reg(xl, M["y0"], wl, M["y1"] - M["y0"] + 1, "lista")
    if s.get("ses_todas_error") and not s.get("ses_todas"):
        parrafo(T, xl + 2, M["y0"], s["ses_todas_error"], wl - 4, ERR, 3)
        filas, sin = [], []
    elif s.get("ses_todas_cargando") and not s.get("ses_todas"):
        T.put(xl + 2, M["y0"], "Buscando las sesiones de cada agente…", C["tx3"])
        filas, sin = [], []
    _lista_sesiones(L, s, M, filas, sel, sin)


def sesiones_detalle(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    filtros, filas, sin = sesiones_filas(s)
    sel = elegida(sec, filas)
    _detalle_sesion(L, s, M, filas, sel)

def _lista_sesiones(L, s, M, filas, sel, sin):
    T = L.T
    xl, wl = M["xl"], M["wl"]
    altos = [_alto_fila(f) for f in filas]
    k = next((n for n, f in enumerate(filas) if f.get("rid") == sel), 0)
    cabe = M["y1"] - M["y0"] + 1 - (2 if sin else 0)
    i0, i1 = ventana(altos, k, cabe)
    cc = xl + wl - 2
    ce = cc - 20
    cn = ce - 14 if wl >= 64 else ce
    yy = M["y0"]
    if i0 > 0:
        T.put(xl + wl - 1, yy, "▲", C["tx2"])
    ahora = s.get("ahora")
    for f in filas[i0:i1]:
        if f["tipo"] == "hueco":
            yy += 1
            continue
        i, a = _por_id(s, f["aid"])
        if f["tipo"] == "grupo":
            hov = L.reg(xl, yy, wl, 1, "sgr:" + f["aid"])
            B.bloque(T, xl, yy, wl, 1, B.P2 if hov else B.P1, B.BG)
            T.put(xl + 2, yy, "●", a["c"])
            T.put(xl + 4, yy, corto(a["n"], wl - 20), C["tx"], True)
            n = f["n"]
            T.right(cc, yy, "%d sesi%s" % (n, "ón" if n == 1 else "ones") if n else "solo su conversación",
                    C["tx3"])
            yy += 1
            continue
        rid = f["rid"]
        on = rid == sel
        hf = _alto_fila(f)
        hov = L.reg(xl, yy, wl, hf, "sr:" + rid)
        if on or hov or L.apr("sr:" + rid):
            T.fill(xl, yy, wl, hf, B.P4 if L.apr("sr:" + rid) else (B.P3 if on else B.P2))
        if on:
            for j in range(hf):
                T.put(xl, yy + j, "▌", a["c"])
        if f["tipo"] == "conv":
            pal, pc, pb = _est_conv(a)
            T.put(xl + 2, yy, "◆", a["c"], True)
            nombre, motor = "Conversación directa", a.get("motor") or a.get("mid")
            cuando = ("ahora" if a.get("st") == "trabaja" else "")
            ult = "Aquí y en la página" + (" · " + D.limpio(a["ultimo"]) if a.get("ultimo") else "")
        else:
            r = f["r"]
            ico, ic, pal, pc, pb = _est_ses(r, a)
            T.put(xl + 2, yy, ico, ic, True)
            nombre, motor = D.limpio(r.get("nombre")) or "Sin nombre", r.get("motor")
            cuando = _hace_corto(r.get("cuando"), ahora)
            ult = D.limpio((r.get("ultimo") or {}).get("texto"))
        T.put(xl + 4, yy, corto(nombre, cn - xl - 5), C["tx"] if (on or hov or f["tipo"] == "conv") else C["tx2"], on)
        if cn != ce and motor:
            T.put(cn, yy, corto(_motor_txt(motor), 13), C["tx3"])
        T.put(ce, yy, corto(pal, 12), pc, pb)
        if cuando:
            T.right(cc, yy, cuando, C["tx3"])
        if ult and hf > 1:
            T.put(xl + 4, yy + 1, corto(ult, cc - xl - 4), C["tx3"])
        yy += hf
    if i1 < len(filas):
        T.put(xl + wl - 1, yy - 1, "▼", C["tx2"])
    if sin and yy + 1 <= M["y1"]:
        nombres = [a["n"] for a in sin]
        txt = (", ".join(nombres[:-1]) + " y " + nombres[-1]) if len(nombres) > 1 else nombres[0]
        if len(nombres) > 4:
            txt = "%s y %d más" % (", ".join(nombres[:3]), len(nombres) - 3)
        T.put(xl + 2, yy + 1, corto("%s: sin sesiones, solo su conversación directa." % txt, wl - 4), C["tx3"])
    if not filas and not sin and not s.get("ses_todas_error") and not s.get("ses_todas_cargando"):
        T.put(xl + 2, M["y0"], "Ninguna sesión con este filtro.", C["tx3"])


def _detalle_sesion(L, s, M, filas, sel):
    T = L.T
    f = next((x for x in filas if x.get("rid") == sel), None)
    if not f:
        detalle_vacio(L, M, "Elige una sesión de la lista para ver qué hizo y retomarla.")
        return
    x, w, y = M["xd"], M["wd"], M["yd"]
    alto = T.h - 2 - y
    B.bloque(T, x, y, w, alto, B.P2, B.BG)
    L.reg(x, y, w, alto, "detalle")
    ix, iw = x + 3, w - 6
    _i, a = _por_id(s, f["aid"])
    ahora = s.get("ahora")
    if f["tipo"] == "conv":
        T.put(ix, y + 1, "Conversación directa", C["tx"], True)
        pal, pc, pb = _est_conv(a)
        D._linea_corta(T, ix, y + 2, [("◆ ", a["c"], True), (pal, pc, pb)], ix + iw)
        kv(T, ix, y + 4, "Agente", a["n"], limite=ix + iw)
        kv(T, ix, y + 5, "Motor", [(D.nombre_motor(a.get("motor") or a.get("mid")), C["tx"], False),
                                   (" · aquí y en la página", C["tx3"], False)], limite=ix + iw)
        yy = y + 7
        if a.get("ultimo"):
            T.put(ix, yy, "LO ÚLTIMO", C["tx3"], True)
            yy = parrafo(T, ix, yy + 1, "«%s»" % D.limpio(a["ultimo"]), iw, C["tx2"], 3)
        yb = max(yy + 1, y + 11)
        if yb + 7 < y + alto:
            B.boton(L, s, ix, yb, "Ir a la conversación", "acc:ir", B.P2, foco=True, wmin=iw, a=a)
            mitad = (iw - 1) // 2
            B.boton(L, s, ix, yb + 3, "Abrir en su motor ↗", "acc:abrir", B.P2, ancho=mitad, a=a)
            B.boton(L, s, ix + mitad + 1, yb + 3, "+ Nueva sesión", "acc:nueva", B.P2, ancho=iw - mitad - 1, a=a)
            yb += 7
        parrafo(T, ix, yb, "La conversación directa vive aquí y en la página. Cada sesión vive en el programa de "
                           "su motor.", iw, maximo=max(0, y + alto - 1 - yb))
        return
    r = f["r"]
    T.put(ix, y + 1, corto(D.limpio(r.get("nombre")) or "Sin nombre", iw), C["tx"], True)
    ico, ic, pal, pc, pb = _est_ses(r, a)
    cuando = D.hace(r.get("cuando"), ahora)
    D._linea_corta(T, ix, y + 2, [(ico + " ", ic, True), (pal, pc, pb)] +
                   ([(" · " + cuando, C["tx3"], False)] if cuando else []), ix + iw)
    kv(T, ix, y + 4, "Agente", a["n"], limite=ix + iw)
    if r.get("motor"):
        kv(T, ix, y + 5, "Motor", [(_motor_txt(r.get("motor")), C["tx"], False), (" · su programa", C["tx3"], False)],
           limite=ix + iw)
    else:
        kv(T, ix, y + 5, "Motor", "el de su pestaña", C["tx2"], limite=ix + iw)
    yy = y + 7
    ult = (r.get("ultimo") or {}).get("texto")
    if ult:
        T.put(ix, yy, "LO ÚLTIMO", C["tx3"], True)
        yy = parrafo(T, ix, yy + 1, "«%s»" % D.limpio(ult), iw, C["tx2"], 3)
    yb = max(yy + 1, y + 11)
    if yb + 7 < y + alto:
        B.boton(L, s, ix, yb, ("Retomar en %s ↗" % _motor_txt(r.get("motor"))) if r.get("motor") else "Retomar ↗",
                "acc:retomar", B.P2, foco=True, wmin=iw, a=a)
        mitad = (iw - 1) // 2
        B.boton(L, s, ix, yb + 3, "Archivar", "acc:archivar", B.P2, apagado=True, ancho=mitad, a=a)
        B.boton(L, s, ix + mitad + 1, yb + 3, "+ Nueva sesión", "acc:nueva", B.P2, ancho=iw - mitad - 1, a=a)
        yb += 6
        yb = parrafo(T, ix, yb, "Archivar todavía no está aquí: se archiva en el menú de sesiones de su motor "
                                "(tecla a).", iw, B.OFF, 3) + 1
    yb = parrafo(T, ix, yb, "◇ Cuando termine, su resultado llega a la conversación directa de %s." % a["n"], iw,
                 maximo=max(0, y + alto - 1 - yb))
    if r.get("estado") not in ("cerrada", None) and yb + 1 < y + alto - 1:
        parrafo(T, ix, yb + 1, "Sigue abierta en su terminal: retomarla aquí pide un segundo Enter (o clic).", iw,
                maximo=max(0, y + alto - 2 - yb))


# ── Skills ────────────────────────────────────────────────────────────────────
def skills_filas(s):
    """Las skills del elegido, por su categoría: [{tipo: grupo, cat} | {tipo: skill, rid, x}]."""
    filas, ult = [], None
    lista = sorted(s.get("skills") or [], key=lambda x: (str(x.get("categoria") or "").lower(),
                                                        str(x.get("nombre")).lower()))
    for x in lista:
        cat = str(x.get("categoria") or "")
        if cat != ult and any(y.get("categoria") for y in lista):
            filas.append({"tipo": "grupo", "cat": cat or "otras"})
            ult = cat
        filas.append({"tipo": "skill", "rid": "skill:" + x["nombre"], "x": x})
    sec = s.get("seccion") or {}
    if sec.get("busca"):
        filas = [f for f in filas if f["tipo"] == "skill" and coincide(sec, f["x"].get("nombre"),
                                                                        f["x"].get("descripcion"))]
    return filas


def skills_lista(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    a = B.agente(s)
    filas = skills_filas(s)
    sel = elegida(sec, filas)
    T.put(xl, yt + 2, corto("Las de %s: se arrancan en su conversación, como «/» en la caja." % a["n"], wl),
          C["tx3"])
    L.reg(xl, M["y0"], wl, M["y1"] - M["y0"] + 1, "lista")
    if not filas:
        T.put(xl + 2, M["y0"], "Buscando sus skills…" if s.get("skills_cargando") else
              "%s todavía no tiene skills." % a["n"], C["tx3"])
    altos = [1 if f["tipo"] == "grupo" else 2 for f in filas]
    k = next((n for n, f in enumerate(filas) if f.get("rid") == sel), 0)
    i0, i1 = ventana(altos, k, M["y1"] - M["y0"] + 1)
    yy = M["y0"]
    for f in filas[i0:i1]:
        if f["tipo"] == "grupo":
            B.bloque(T, xl, yy, wl, 1, B.P1, B.BG)
            T.put(xl + 2, yy, corto(f["cat"].upper(), wl - 4), C["tx3"], True)
            yy += 1
            continue
        x, rid = f["x"], f["rid"]
        on = rid == sel
        hov = L.reg(xl, yy, wl, 2, "sr:" + rid)
        if on or hov or L.apr("sr:" + rid):
            T.fill(xl, yy, wl, 2, B.P4 if L.apr("sr:" + rid) else (B.P3 if on else B.P2))
        if on:
            T.put(xl, yy, "▌", a["c"])
            T.put(xl, yy + 1, "▌", a["c"])
        T.put(xl + 2, yy, "▸", a["c"], True)
        T.put(xl + 4, yy, corto(D.nombre_skill(x["nombre"]), wl - 16), C["tx"] if (on or hov) else C["tx2"], on)
        if x.get("version"):
            T.right(xl + wl - 2, yy, corto("v" + str(x["version"]).lstrip("v"), 10), C["tx3"])
        T.put(xl + 4, yy + 1, corto(D.limpio(x.get("descripcion")), wl - 6), C["tx3"])
        yy += 2


def skills_detalle(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    a = B.agente(s)
    filas = skills_filas(s)
    sel = elegida(sec, filas)
    f = next((x for x in filas if x.get("rid") == sel), None)
    if not f:
        detalle_vacio(L, M, "Elige una skill para ver qué hace y usarla.")
        return
    x = f["x"]
    xd, wd, y = M["xd"], M["wd"], M["yd"]
    alto = T.h - 2 - y
    B.bloque(T, xd, y, wd, alto, B.P2, B.BG)
    L.reg(xd, y, wd, alto, "detalle")
    ix, iw = xd + 3, wd - 6
    T.put(ix, y + 1, corto(D.nombre_skill(x["nombre"]), iw), C["tx"], True)
    meta = " · ".join(t for t in (str(x.get("categoria") or ""), ("versión " + str(x["version"]))
                                  if x.get("version") else "") if t)
    if meta:
        T.put(ix, y + 2, corto(meta, iw), C["tx3"])
    yy = parrafo(T, ix, y + 4, D.limpio(x.get("descripcion")) or "Sin descripción.", iw, C["tx2"], 4) + 1
    pasos = [p for p in x.get("pasos") or [] if isinstance(p, str) and p.strip()]
    if pasos:
        T.put(ix, yy, "SUS PASOS", C["tx3"], True)
        yy += 1
        for n, p in enumerate(pasos[:6], 1):
            D._linea_corta(T, ix, yy, [("%d " % n, a["c"], True), (D.limpio(p), C["tx2"], False)], ix + iw)
            yy += 1
        if len(pasos) > 6:
            T.put(ix, yy, "y %d más" % (len(pasos) - 6), C["tx3"])
            yy += 1
        yy += 1
    corre = D.vigente_en(s)
    sin = "/api/v2/skill" in (s.get("sin_ruta") or ())
    yb = max(yy, y + alto - 9)
    if yb + 6 < y + alto:
        if corre:                                     # skills-cierre: la que corre se detiene aquí mismo
            B.boton(L, s, ix, yb, "Detener «%s»" % D.nombre_skill(corre.get("skill")), "acc:detener", B.P2,
                    foco=True, wmin=iw, a=a)
        else:
            B.boton(L, s, ix, yb, "Usar", "acc:usar", B.P2, foco=not sin, apagado=sin, wmin=iw, a=a)
        B.boton(L, s, ix, yb + 3, "En la página ↗", "acc:pagina", B.P2, wmin=iw, a=a)
        nota = ("Ya corre «%s»: espera a que termine o detenla." % D.nombre_skill(corre.get("skill"))
                if corre else (D.ACTUALIZANDO if sin else
                               "Arranca en su conversación: ahí ves sus pasos y lo que te pregunte."))
        parrafo(T, ix, yb + 6, nota, iw, B.OFF if (corre or sin) else C["tx3"], max(0, y + alto - yb - 7))

# ── Motores y conexiones ───────────────────────────────────────────────────────
_EST_MOTOR = {"listo": ("✓", "OK"), "experimental": ("✓", "WARN"), "sin_sesion": ("!", "WARN"),
              "falta_modelo": ("!", "WARN"), "bloqueado": ("!", "ERR"), "incompleta": ("!", "WARN"),
              "no_instalado": ("○", "tx3"), "instalado": ("·", "tx2"), "verificando": ("·", "tx2")}


def _col(k):
    return {"OK": B.OK, "WARN": B.WARN, "ERR": ERR}.get(k) or C.get(k, C["tx2"])


def motores_filas(s):
    d = (s.get("datos") or {})
    mot = (d.get("motores") or {}).get("motores") or []
    con = (d.get("conexiones") or {}).get("conexiones") or []
    filas = [{"tipo": "grupo", "cat": "Motores"}]
    filas += [{"tipo": "motor", "rid": "mot:" + str(m.get("id")), "m": m} for m in mot if m.get("id")]
    if con and D.piel() == "bloque":                  # (H-1: el MCP vive en Ajustes › Conexiones, H3-b)
        filas += [{"tipo": "hueco"}, {"tipo": "grupo", "cat": "Conexiones (MCP)"}]
        filas += [{"tipo": "con", "rid": "con:" + str(c.get("nombre")), "c": c} for c in con if c.get("nombre")]
    sec = s.get("seccion") or {}
    if sec.get("busca"):
        filas = [f for f in filas if f["tipo"] == "grupo" or
                 coincide(sec, (f.get("m") or f.get("c") or {}).get("nombre"), (f.get("m") or {}).get("id"))]
    return filas


def motores_lista(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    a = B.agente(s)
    filas = motores_filas(s)
    sel = elegida(sec, filas)
    cargando = "motores" in (s.get("cargando") or ())
    h1 = D.piel() != "bloque"
    T.put(xl, yt + 2, corto("Con qué piensa cada agente: su cuenta, su proveedor y su modelo." if h1 else
                            "Con qué piensa cada agente y si Workspace está bien conectado.", wl - 22), C["tx3"])
    if h1:
        linea_conexiones(L, s, xl, yt + 3, wl)
    lab = " ↻ Verificar todos "
    xv = xl + wl - W(lab) - 2
    hov = L.reg(xv, yt + 2, W(lab) + 2, 1, "acc:verificar_todos")
    B.ficha(T, xv, yt + 2, lab, B.P3 if hov else B.P2, B.BG, C["tx"] if hov else C["tx2"])
    L.reg(xl, M["y0"], wl, M["y1"] - M["y0"] + 1, "lista")
    if len(filas) <= 1:
        T.put(xl + 2, M["y0"] + 1, "Viendo cómo está cada motor…" if cargando else
              ((s.get("errores") or {}).get("motores") or "Sin motores."), C["tx3"])
    altos = [1 if f["tipo"] in ("grupo", "hueco") else 2 for f in filas]
    k = next((n for n, f in enumerate(filas) if f.get("rid") == sel), 0)
    i0, i1 = ventana(altos, k, M["y1"] - M["y0"] + 1)
    yy = M["y0"]
    motor_aqui = (s.get("foto") or {}).get("motor") or a.get("mid")
    for f in filas[i0:i1]:
        if f["tipo"] == "hueco":
            yy += 1
            continue
        if f["tipo"] == "grupo":
            B.bloque(T, xl, yy, wl, 1, B.P1, B.BG)
            T.put(xl + 2, yy, f["cat"].upper(), C["tx3"], True)
            yy += 1
            continue
        rid = f["rid"]
        on = rid == sel
        hov = L.reg(xl, yy, wl, 2, "sr:" + rid)
        if on or hov or L.apr("sr:" + rid):
            T.fill(xl, yy, wl, 2, B.P4 if L.apr("sr:" + rid) else (B.P3 if on else B.P2))
        if on:
            T.put(xl, yy, "▌", a["c"])
            T.put(xl, yy + 1, "▌", a["c"])
        if f["tipo"] == "motor":
            m = f["m"]
            ico, ck = _EST_MOTOR.get(m.get("estado"), ("·", "tx2"))
            T.put(xl + 2, yy, ico, _col(ck), True)
            T.put(xl + 4, yy, corto(m.get("nombre") or m.get("id"), 22), C["tx"] if (on or hov) else C["tx2"], on)
            T.put(xl + 28, yy, corto(m.get("estado_texto") or m.get("estado") or "", wl - 32),
                  _col(ck) if ck in ("WARN", "ERR") else C["tx2"])
            usan = ", ".join(m.get("agentes") or [])
            sub = m.get("bloqueo") or (("lo usa: " + usan) if usan else "nadie lo usa")
            if m.get("id") == motor_aqui:
                sub += " · esta conversación"
            T.put(xl + 4, yy + 1, corto(D.limpio(sub), wl - 6), C["tx3"])
        else:
            c = f["c"]
            T.put(xl + 2, yy, "◆", a["c"] if c.get("registrada") else C["tx3"], True)
            T.put(xl + 4, yy, corto(c["nombre"], wl - 8), C["tx"] if (on or hov) else C["tx2"], on)
            mot = ", ".join(D.nombre_motor(x) for x in c.get("motores") or [])
            T.put(xl + 4, yy + 1, corto(("en " + mot) if mot else "en ningún motor todavía", wl - 6), C["tx3"])
        yy += 2


def linea_conexiones(L, s, x, y, w):
    """H3-b + Conexiones en verde: una línea con cómo están las Conexiones de Workspace (el chequeo rápido: ✓ todo
    responde · hace 5 min · ⚠ N cosas por hacer · ✗ N rotas) y «Ajustes › Conexiones ›», que lleva a su grupo de Ajustes.
    Si no cabe todo, se va primero «· hace …», no el botón."""
    import hub_conexiones as CX
    T = L.T
    est, t = CX.linea(s)
    if " · " in t and x + W("Conexiones de Workspace  ") + W(t) + 2 + W(" Ajustes › Conexiones › ") > x + w:
        t = t.split(" · ", 1)[0]
    xx = T.put(x, y, "Conexiones de Workspace  ", C["tx2"], True)
    col = {"ok": B.OK, "tuyo": B.WARN, "roto": ERR}.get(est, C["tx3"])
    xx = T.put(xx, y, t, col, True)
    lab = " Ajustes › Conexiones › "
    xl = max(xx + 2, x + w - W(lab) - 1)
    if xl + W(lab) <= x + w:
        hov = L.reg(xl, y, W(lab), 1, "acc:conexiones")
        T.put(xl, y, lab, C["tx"] if hov else C["tx2"], False, B.P4 if L.apr("acc:conexiones") else
              (B.P3 if hov else B.P2))


def motores_detalle(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    a = B.agente(s)
    filas = motores_filas(s)
    sel = elegida(sec, filas)
    cargando = "motores" in (s.get("cargando") or ())
    f = next((x for x in filas if x.get("rid") == sel), None)
    if not f:
        detalle_vacio(L, M, "Elige un motor (o una conexión) para ver cómo está.")
    elif f["tipo"] == "motor":
        _detalle_motor(L, s, M, f["m"], a)
    else:
        _detalle_conexion(L, s, M, f["c"])

def _detalle_motor(L, s, M, m, a):
    T = L.T
    x, w, y = M["xd"], M["wd"], M["yd"]
    alto = T.h - 2 - y
    B.bloque(T, x, y, w, alto, B.P2, B.BG)
    L.reg(x, y, w, alto, "detalle")
    ix, iw = x + 3, w - 6
    nombre = m.get("nombre") or m.get("id")
    T.put(ix, y + 1, corto(nombre, iw), C["tx"], True)
    ico, ck = _EST_MOTOR.get(m.get("estado"), ("·", "tx2"))
    D._linea_corta(T, ix, y + 2, [(ico + " ", _col(ck), True), (m.get("estado_texto") or m.get("estado") or "",
                                                                 _col(ck), True)], ix + iw)
    h1 = D.piel() != "bloque"
    datos = [(o.get("etiqueta") or o.get("clave"), o.get("valor")) for o in m.get("opciones") or ()
             if o.get("tipo") == "dato" and o.get("valor") not in (None, "")]
    if h1 and datos:                                  # su cuenta, su proveedor, su modelo… (lo que dice su motor)
        y2 = y + 4
        for k_, v_ in datos[:4]:
            kv(T, ix, y2, corto(D.limpio(k_), 11), D.limpio(v_), kw=12, limite=ix + iw)
            y2 += 1
        y = y2 - 3
    T.put(ix, y + 4, "LO QUE REVISA WORKSPACE", C["tx3"], True)
    ver = (m.get("version") or {}).get("instalada") or ""
    integ = m.get("integracion") or {}
    # ✓ bien · ✗ falla · ! a medias · «·» no se sabe (su motor no lo declara: no es una falla)
    revisa = [("Instalado", True if m.get("instalado") else False, ver if m.get("instalado") else "no"),
              ("Sesión iniciada", True if m.get("sesion") is True else (False if m.get("sesion") is False else None),
               "" if m.get("sesion") is True else (m.get("sesion_texto") or "sin verificar")),
              ("Conexión con Workspace", (True if integ.get("nivel") != "experimental" else "!") if integ else None,
               integ.get("texto") or "su motor no la declara")]
    import hub_conexiones as CX                       # Conexiones en verde: lo de adentro, del chequeo rápido
    cx = next((x for x in CX.motores_v(s) if x.get("motor") == m.get("id")), None)
    if cx:
        revisa[-1] = ("Conexión con Workspace", {"ok": True, "tuyo": "!", "roto": False}.get(cx.get("estado"), None),
                      {"ok": "responde", "tuyo": "algo por hacer", "roto": "algo roto"}.get(cx.get("estado"), ""))
        if ver and cx.get("version_estado"):
            revisa[0] = ("Instalado", True, "%s · %s" % (ver, cx["version_estado"]))
    yy = y + 5
    for nom, bien, det in revisa:
        ico, col = {True: ("✓", B.OK), False: ("✗", ERR), "!": ("!", B.WARN)}.get(bien, ("·", C["tx3"]))
        T.put(ix, yy, ico, col, True)
        T.put(ix + 2, yy, nom, C["tx"] if bien is False else C["tx2"], bien is False)
        if det:
            T.right(ix + iw, yy, corto(D.limpio(det), iw - W(nom) - 5), ERR if bien is False else C["tx3"])
        yy += 1
    T.put(ix, yy, "·", C["tx3"])
    T.put(ix + 2, yy, "Avisos al terminar", C["tx3"])
    T.right(ix + iw, yy, "su revisión: pronto", C["tx3"])
    yy += 1
    if m.get("bloqueo"):
        yy = parrafo(T, ix, yy + 1, D.limpio(m["bloqueo"]), iw, ERR, 3)
    cambio = (cx or {}).get("cambio")
    if cambio:                                        # la revisión al abrir: se actualizó (y qué pasó)
        yy = parrafo(T, ix, yy + 1, ("↑ " if cambio.get("estado") == "ok" else "") + D.limpio(cambio.get("texto")),
                     iw, C["tx2"] if cambio.get("estado") == "ok" else ERR, 3)
    usan = ", ".join(m.get("agentes") or [])
    yy += 1
    kv(T, ix, yy, "Lo usan", usan or "nadie", kw=9, limite=ix + iw)
    yy += 2
    motor_aqui = (s.get("foto") or {}).get("motor") or a.get("mid")
    sin = s.get("sin_ruta") or ()
    defecto = ((s.get("datos") or {}).get("preferencias") or {}).get("motor")
    acciones = [
        ("cuenta", "Cuenta y proveedor", False),
        ("login", "Iniciar sesión", not m.get("instalado") or m.get("estado") == "bloqueado"),
        ("verificar", "↻ Verificar ahora", not m.get("instalado") or "/api/sistema/motor/verificar" in sin),
        ("modelo", "Modelo y esfuerzo", not m.get("instalado")),
        ("reparar", "Actualizar o reparar", not m.get("instalado")),
        ("instalar", "Instalar", bool(m.get("instalado"))),
        ("ofrecer", "Quitar del hub" if m.get("en_hub") else "Ofrecer en el hub",
         not m.get("instalado")),
        ("defecto", "✓ Por defecto" if m.get("id") == defecto else "Motor por defecto",
         not m.get("instalado") or m.get("id") == defecto),
        ("abrir", "Abrir su programa ↗", not m.get("listo")),
        ("usar", "Usar aquí", not m.get("listo") or m.get("id") == motor_aqui),
    ]
    y = M["yd"]
    if h1 and _botones_grandes(L, s, ix, iw, y, alto, yy, acciones, m, a):
        return
    yb = y + alto - 6
    ancho = (iw - 2) // 2
    if yb <= yy:
        # En bajo, la ficha conserva los controles y las primeras líneas de estado.
        T.fill(ix, yb, iw, 5, B.P2)
    for i, (accion, lab, apagado) in enumerate(acciones):
        xb, fila = ix + i % 2 * (ancho + 2), yb + i // 2
        lab = " " + corto(lab, ancho - 3) + " "
        foco = L.reg(xb, fila, W(lab) + 2, 1, "acc:" + accion) if not apagado else False
        B.ficha(T, xb, fila, lab, B.P4 if foco else B.P3, B.P2, C["tx3"] if apagado else C["tx2"])


#: H3-b: las acciones que van en botón grande (3 filas, para el mouse); las demás, en fichas debajo.
GRANDES = ("cuenta", "modelo", "login", "abrir")


def _botones_grandes(L, s, ix, iw, y, alto, yy, acciones, m, a):
    """Los botones grandes del motor (cuenta y proveedor, modelo, iniciar sesión, abrir su programa; sin instalar,
    «Instalar» en lugar de iniciar sesión) y las demás acciones en fichas debajo: ninguna se pierde. → False si no
    caben (entonces, todas en fichas, como antes)."""
    T = L.T
    grandes = [x for x in acciones if x[0] in GRANDES]
    if not m.get("instalado"):
        grandes = [x for x in acciones if x[0] in ("cuenta", "instalar", "abrir", "modelo")]
    resto = [x for x in acciones if x not in grandes]
    ancho = (iw - 1) // 2
    lugar, xx, filas_f = [], ix, 1                    # las fichas, de corrido (sin cortar su texto)
    for accion, lab, apagado in resto:
        lab = " " + corto(lab, iw - 4) + " "
        if xx > ix and xx + W(lab) + 2 > ix + iw:
            xx, filas_f = ix, filas_f + 1
        lugar.append((xx, filas_f - 1, accion, lab, apagado))
        xx += W(lab) + 3
    yb = y + alto - 2 - filas_f - 1 - 6
    if yb <= yy + 1:
        return False
    T.fill(ix - 1, yb - 1, iw + 2, alto - (yb - 1 - y) - 1, B.P2)
    for i, (accion, lab, apagado) in enumerate(grandes):
        B.boton(L, s, ix + (i % 2) * (ancho + 1), yb + (i // 2) * 3, lab, "acc:" + accion, B.P2,
                foco=(i == 0 and not apagado), apagado=apagado, ancho=ancho, a=a)
    yf = yb + 6 + 1
    for xb, k, accion, lab, apagado in lugar:
        foco = L.reg(xb, yf + k, W(lab) + 2, 1, "acc:" + accion) if not apagado else False
        B.ficha(T, xb, yf + k, lab, B.P4 if foco else B.P3, B.P2, C["tx3"] if apagado else C["tx2"])
    return True


def _detalle_conexion(L, s, M, c):
    T = L.T
    x, w, y = M["xd"], M["wd"], M["yd"]
    alto = T.h - 2 - y
    B.bloque(T, x, y, w, alto, B.P2, B.BG)
    L.reg(x, y, w, alto, "detalle")
    ix, iw = x + 3, w - 6
    T.put(ix, y + 1, corto(c["nombre"], iw), C["tx"], True)
    T.put(ix, y + 2, "conexión (MCP)", C["tx3"])
    mot = ", ".join(D.nombre_motor(m) for m in c.get("motores") or []) or "ninguno todavía"
    kv(T, ix, y + 4, "Motores", mot, kw=10, limite=ix + iw)
    kv(T, ix, y + 5, "Workspace", "registrada" if c.get("registrada") else "no la registra", kw=10, limite=ix + iw)
    parrafo(T, ix, y + 7, "Las conexiones se agregan y se quitan en la página (Conexiones); aquí se ve dónde "
                          "está cada una.", iw)


# ── Ajustes ───────────────────────────────────────────────────────────────────
PERMISOS = (("auto", "Automático", "Trabaja sin interrumpirte: su motor revisa cada paso y solo te pregunta lo "
                                   "arriesgado."),
            ("preguntar", "Preguntarme todo", "Te pide permiso antes de editar o de correr algo."))
_NIVEL_OTRO = {"editar": "Editar sin preguntar (elegido en la página)", "sin_permisos": "Sin permisos, en su sandbox"}


def ajustes_filas(s):
    """Lo que se ajusta: [{rid, titulo, opciones [(v, t)], actual, nota, dim}] (puro: también para ←→ y Enter)."""
    a = B.agente(s)
    d = s.get("datos") or {}
    info = d.get("info")
    perm = next((p for p in (info or {}).get("permisos") or [] if p.get("agente") == a.get("id")), None)
    filas = []
    nota = ""
    if perm:
        nota = next((t for v, _t, t in PERMISOS if v == perm.get("nivel")), "") or _NIVEL_OTRO.get(perm.get("nivel"),
                                                                                                   "")
        if perm.get("fijado"):
            nota += " " + perm["fijado"]
    filas.append({"rid": "aj:perm", "titulo": "Permisos de %s" % a["n"], "opciones": [(v, t) for v, t, _d in PERMISOS],
                  "actual": (perm or {}).get("nivel"), "nota": nota if perm else
                  ("Viendo sus permisos…" if "info" in (s.get("cargando") or ()) else
                   (s.get("errores") or {}).get("info") or ""), "dim": perm is None,
                  "ruta": "/api/v2/autonomia"})
    aj = (s.get("fotos_ajustes") or {}).get(a.get("id")) or (s.get("foto") or {}).get("ajustes") or {}
    tabla = next((t for t in aj.get("tabla") or [] if t.get("k") == "modelo"), None)
    actual = ((aj.get("valores") or {}).get("modelo") or {}).get("actual") or {}
    motor = D.nombre_motor((s.get("foto") or {}).get("motor") or a.get("mid"))
    if tabla:
        filas.append({"rid": "aj:modelo", "titulo": "Modelo de %s" % a["n"],
                      "opciones": [(o["v"], o["t"]) for o in tabla.get("opciones") or []], "actual": actual.get("v"),
                      "nota": "Se usa desde su siguiente mensaje.", "ruta": "/api/v2/ajuste"})
    else:
        filas.append({"rid": "aj:modelo", "titulo": "Modelo de %s" % a["n"], "opciones": [], "actual": None,
                      "nota": "%s no deja elegir el modelo desde aquí: lo elige su motor." % motor, "dim": True})
    esfuerzo = next((t for t in aj.get("tabla") or [] if t.get("k") == "esfuerzo"), None)
    if esfuerzo:
        valor = ((aj.get("valores") or {}).get("esfuerzo") or {}).get("actual") or {}
        filas.append({"rid": "aj:esfuerzo", "titulo": "Esfuerzo de %s" % a["n"],
                      "opciones": [(o["v"], o["t"]) for o in esfuerzo.get("opciones") or []],
                      "actual": valor.get("v"), "nota": "Se usa desde su siguiente mensaje.",
                      "ruta": "/api/v2/ajuste"})
    idiomas = s.get("idiomas") or []
    filas.append({"rid": "aj:idioma", "titulo": "Idioma de Workspace", "opciones": [(c, n) for c, n in idiomas],
                  "actual": s.get("idioma"), "nota": "La página y lo demás de Workspace (este hub sigue en español).",
                  "dim": not idiomas})
    filas.append({"rid": "aj:riel", "titulo": "El riel", "opciones": [("monitos", "Solo monitos"),
                                                                       ("nombres", "Con nombres")],
                  "actual": "nombres" if s.get("riel_nombres") else "monitos",
                  "nota": "También arrastrando su borde con el mouse."})
    if s.get("raton_posible"):
        filas.append({"rid": "aj:mouse", "titulo": "El mouse", "opciones": [("on", "Encendido"), ("off", "Apagado")],
                      "actual": "on" if s.get("raton") else "off",
                      "nota": "Apagado, la terminal selecciona texto al arrastrar."})
    for f in filas:
        if f.get("ruta") in (s.get("sin_ruta") or ()):
            f["dim"], f["nota"] = True, D.ACTUALIZANDO
    return filas


def ajustes_lista(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    a = B.agente(s)
    filas = ajustes_filas(s)
    sel = elegida(sec, filas)
    T.put(xl, yt + 2, corto("Los de %s y los de Workspace. Un monito: los de ese agente." % a["n"], wl), C["tx3"])
    L.reg(xl, M["y0"], wl, M["y1"] - M["y0"] + 1, "lista")
    yy = M["y0"]
    for f in filas:
        if yy + 2 > M["y1"] + 1:
            break
        rid = f["rid"]
        on = rid == sel
        hov = L.reg(xl, yy, wl, 2, "sr:" + rid)
        if on or hov or L.apr("sr:" + rid):
            T.fill(xl, yy, wl, 2, B.P4 if L.apr("sr:" + rid) else (B.P3 if on else B.P2))
        if on:
            T.put(xl, yy, "▌", a["c"])
            T.put(xl, yy + 1, "▌", a["c"])
        T.put(xl + 2, yy, corto(f["titulo"], wl - 30), C["tx"] if (on or hov) else C["tx2"], on)
        act = dict(f["opciones"]).get(f.get("actual")) or _NIVEL_OTRO.get(f.get("actual")) or \
            (f.get("actual") or ("el de siempre" if f["opciones"] else ""))
        T.right(xl + wl - 2, yy, corto(act, 28), C["tx3"] if f.get("dim") else a["c"], not f.get("dim"))
        T.put(xl + 2, yy + 1, corto(f.get("nota") or "", wl - 4), C["tx3"])
        yy += 2


def ajustes_detalle(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    a = B.agente(s)
    filas = ajustes_filas(s)
    sel = elegida(sec, filas)
    f = next((x for x in filas if x["rid"] == sel), None)
    x, w, y = M["xd"], M["wd"], M["yd"]
    alto = T.h - 2 - y
    B.bloque(T, x, y, w, alto, B.P2, B.BG)
    L.reg(x, y, w, alto, "detalle")
    if not f:
        return
    ix, iw = x + 3, w - 6
    T.put(ix, y + 1, corto(f["titulo"], iw), C["tx"], True)
    yy = parrafo(T, ix, y + 2, f.get("nota") or "", iw, C["tx3"], 3) + 1
    op = sec.get("op")
    for v, t in f["opciones"]:
        if yy + 3 > y + alto - 1:
            break
        actual = v == f.get("actual")
        B.boton(L, s, ix, yy, ("✓ " if actual else "") + t, "op:%s:%s" % (f["rid"][3:], v), B.P2,
                foco=actual and not f.get("dim"), apagado=bool(f.get("dim")), wmin=iw, a=a)
        if op == v and not actual and not f.get("dim"):
            T.put(ix - 2, yy + 1, "›", a["c"], True, B.P2)
        yy += 3

# ── Agentes ───────────────────────────────────────────────────────────────────
def agentes_filas(s):
    sec = s.get("seccion") or {}
    return [{"tipo": "agente", "rid": "ag:" + b["id"], "i": i} for i, b in enumerate(s.get("agentes") or [])
            if coincide(sec, b.get("n"), b.get("id"))]


def agentes_lista(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    filas = agentes_filas(s)
    sel = elegida(sec, filas)
    ag = s.get("agentes") or []
    T.put(xl, yt + 2, corto("Su cara, su color y cómo se llaman en esta computadora.", wl - 22), C["tx3"])
    lab = " + Agregar agente "
    xv = xl + wl - W(lab) - 2
    hov = L.reg(xv, yt + 2, W(lab) + 2, 1, "acc:agregar")
    B.ficha(T, xv, yt + 2, lab, B.P3 if hov else B.P2, B.BG, C["tx"] if hov else C["tx2"])
    L.reg(xl, M["y0"], wl, M["y1"] - M["y0"] + 1, "lista")
    k = next((n for n, f in enumerate(filas) if f["rid"] == sel), 0)
    i0, i1 = ventana([2] * len(filas), k, M["y1"] - M["y0"] + 1)
    yy = M["y0"]
    for f in filas[i0:i1]:
        b = ag[f["i"]]
        rid = f["rid"]
        on = rid == sel
        hov = L.reg(xl, yy, wl, 2, "sr:" + rid)
        if on or hov or L.apr("sr:" + rid):
            T.fill(xl, yy, wl, 2, B.P4 if L.apr("sr:" + rid) else (B.P3 if on else B.P2))
        if on:
            T.put(xl, yy, "▌", b["c"])
            T.put(xl, yy + 1, "▌", b["c"])
        T.put(xl + 2, yy, "●", b["c"])
        T.put(xl + 4, yy, corto(b["n"], wl - 30), C["tx"] if (on or hov) else C["tx2"], on)
        T.right(xl + wl - 2, yy, corto(D.motor_riel(s, f["i"], False), 22), C["tx3"])
        t, col, bb = D.estado_riel(b, s.get("ahora"))
        T.put(xl + 4, yy + 1, corto(t, wl - 6), col, bb)
        yy += 2


def agentes_detalle(L, s, M, sec):
    T = L.T
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    filas = agentes_filas(s)
    sel = elegida(sec, filas)
    ag = s.get("agentes") or []
    f = next((x for x in filas if x["rid"] == sel), None)
    if not f:
        detalle_vacio(L, M, "Elige un agente.")
        return
    _detalle_agente(L, s, M, sec, f["i"])

def _detalle_agente(L, s, M, sec, i):
    T = L.T
    b = s["agentes"][i]
    x, w, y = M["xd"], M["wd"], M["yd"]
    alto = T.h - 2 - y
    B.bloque(T, x, y, w, alto, B.P2, B.BG)
    L.reg(x, y, w, alto, "detalle")
    ix, iw = x + 3, w - 6
    ini = (s.get("datos") or {}).get("inicio") or {}
    formas = [f for f in ini.get("formas") or [] if f in P.PATH] or sorted(P.PATH)
    colores = ini.get("colores") or []
    sin = s.get("sin_ruta") or ()
    yy = y + 1
    if sec.get("editando") == "nombre":                 # el nombre: un campo
        T.put(ix, yy, "Nombre en esta computadora", C["tx3"])
        B.bloque(T, ix, yy + 1, iw, 1, B.P3, B.P2)
        xx = T.put(ix + 1, yy + 1, corto(sec.get("buf") or "", iw - 4), C["tx"], True, B.P3)
        T.put(xx, yy + 1, "▏", C["tx"], False, B.P3)
        yy += 3
    else:
        e = T.put(ix, yy, corto(b["n"], iw - 12), b["c"], True)
        if "/api/front/nombre" not in sin:
            lab = " ✎ Nombre "
            hov = L.reg(ix + iw - W(lab) - 2, yy, W(lab) + 2, 1, "acc:nombre")
            B.ficha(T, ix + iw - W(lab) - 2, yy, lab, B.P3 if hov else B.P2, B.P2, C["tx"] if hov else C["tx2"])
        T.put(ix, yy + 1, corto(D.motor_riel(s, i, False), iw), C["tx3"])
        yy += 3
    T.put(ix, yy, "CARA", C["tx3"], True)
    yy += 1
    ap = "/api/front/apariencia" in sin
    por_fila = max(1, (iw + 1) // 11)
    for n, fo in enumerate(formas):                     # un monito chico por cara (en filas): se toca
        xx, yf = ix + (n % por_fila) * 11, yy + (n // por_fila) * 6
        rid = "cara:" + fo
        on = fo == b.get("f")
        hov = (not ap) and L.reg(xx, yf, 10, 5, rid)
        if on or hov:
            B.bloque(T, xx, yf, 10, 5, B.P4 if hov else B.P3, B.P2)
        hub_monitos.dibujar(T, dict(b, f=fo), xx + 1, yf + 1, 8, st="libre", signo=False)
        if on:                                          # la de ahora: ✓ del color del agente
            T.put(xx + 8, yf, "✓", b["c"], True, B.P4 if hov else B.P3)
    yy += 6 * ((len(formas) + por_fila - 1) // por_fila)
    T.put(ix, yy, "COLOR", C["tx3"], True)
    yy += 1
    xx = ix
    for co in colores:                                  # una ficha de cada color: se toca
        if xx + 6 > ix + iw:
            break
        rid = "color:" + co
        on = co.lower() == str(b.get("c")).lower()
        hov = (not ap) and L.reg(xx, yy, 5, 2, rid)
        T.fill(xx, yy, 5, 2, co)
        if on or hov:
            T.put(xx + 1, yy, "✓" if on else " ", P.T_BG if co != "#ffffff" else "#141416", True, co)
        xx += 6
    yy += 3
    if ap:
        yy = parrafo(T, ix, yy, "Cambiar su cara o su color todavía no se puede desde aquí.", iw, B.OFF, 2) + 1
    yb = max(yy, y + alto - 7)
    if yb + 3 < y + alto:
        if sec.get("editando") == "nombre":
            mitad = (iw - 1) // 2
            B.boton(L, s, ix, yb, "Guardar", "acc:guardar", B.P2, foco=True, ancho=mitad, a=b)
            B.boton(L, s, ix + mitad + 1, yb, "Cancelar", "acc:cancelar", B.P2, ancho=iw - mitad - 1, a=b)
        else:
            B.boton(L, s, ix, yb, "Conversar con %s" % b["n"], "acc:conversar", B.P2, foco=True, wmin=iw, a=b)
        if yb + 4 < y + alto:
            parrafo(T, ix, yb + 3, "Solo en esta computadora: su identidad y su memoria no cambian.", iw,
                    maximo=max(0, y + alto - yb - 4))


# ── Ayuda ─────────────────────────────────────────────────────────────────────
TECLAS = (("Enter", "manda lo que escribiste, o contesta"),
          ("Esc", "borra lo escrito; sin texto, para al que trabaja; si no, sale (en una sección, vuelve)"),
          ("Tab", "otro agente (Shift-Tab: el de antes)"),
          ("^E", "el motor de esta conversación"),
          ("^S", "sus sesiones"),
          ("^O", "abrir en su motor, con lo escrito como primer mensaje"),
          ("^B", "el riel con nombres, o solo los monitos"),
          ("/", "sus skills (con la caja vacía: lo que escribes filtra)"),
          ("F1", "esta ayuda (otra vez: de vuelta)"),
          ("↑↓", "la conversación; en un menú o una sección, lo elegido"),
          ("AvPág", "la conversación, una página"),
          ("←→", "los botones de un permiso o una pregunta; los filtros"))


def ayuda_filas(s):
    out = ["acc:mouse"] if s.get("raton_posible") else []
    return out + ["acc:riel", "acc:agregar"]


def ayuda_lista(L, s, M, sec):
    T = L.T
    sel = elegida(sec, [{"rid": r} for r in ayuda_filas(s)])
    if M["lado"]:
        _ayuda_teclas(L, s, M["xl"], M["yt"] + 2, M["wl"], T.h - 2)
    else:
        alto = _ayuda_panel(L, s, M["xl"], M["yt"] + 2, M["wl"], None, sel)
        _ayuda_teclas(L, s, M["xl"], M["yt"] + 3 + alto, M["wl"], T.h - 2)


def ayuda_detalle(L, s, M, sec):
    if M["lado"]:
        T = L.T
        sel = elegida(sec, [{"rid": r} for r in ayuda_filas(s)])
        _ayuda_panel(L, s, M["xd"], M["yt"], M["wd"], T.h - 2 - M["yt"], sel)


def _ayuda_teclas(L, s, x, y, w, y1):
    T = L.T
    if y >= y1:
        return
    T.put(x, y, "LAS TECLAS", C["tx3"], True)
    y += 2
    for k, txt in TECLAS:
        if y >= y1 - 4:
            break
        T.key(x, y, k)
        D._linea_corta(T, x + 8, y, [(txt, C["tx2"], False)], x + w)
        y += 1
    y += 1
    if y < y1 - 2:
        T.put(x, y, "EL MOUSE", C["tx3"], True)
        parrafo(T, x, y + 1, "Todo se toca: la barra, los monitos, los botones y las filas. La rueda mueve la "
                             "conversación, el riel y lo de los menús. Arrastra el borde del riel (o tócalo) para ver "
                             "los nombres.", w, maximo=max(0, y1 - y - 1))


def _ayuda_panel(L, s, x, y, w, alto, sel):
    """Lo que no tiene tecla propia: el mouse, el riel y agregar un agente. → su alto."""
    T = L.T
    a = B.agente(s)
    raton, posible = bool(s.get("raton")), bool(s.get("raton_posible"))
    alto = alto or 20
    B.bloque(T, x, y, w, alto, B.P2, B.BG)
    L.reg(x, y, w, alto, "detalle")
    ix, iw = x + 3, w - 6
    T.put(ix, y + 1, "Lo que no tiene tecla", C["tx"], True)
    yy = y + 3
    lab = ("Apagar el mouse" if raton else "Prender el mouse") if posible else "Sin mouse en esta terminal"
    B.boton(L, s, ix, yy, lab, "acc:mouse", B.P2, foco=sel == "acc:mouse" and posible, apagado=not posible,
            wmin=iw, a=a)
    yy += 3
    B.boton(L, s, ix, yy, "Solo los monitos" if s.get("riel_nombres") else "Ver los nombres en el riel",
            "acc:riel", B.P2, foco=sel == "acc:riel", wmin=iw, a=a)
    yy += 3
    B.boton(L, s, ix, yy, "+ Agregar agente", "acc:agregar", B.P2, foco=sel == "acc:agregar", wmin=iw, a=a)
    yy += 4
    if yy < y + alto - 2:
        txt = ("¿Seleccionar texto? Apaga el mouse aquí: la terminal vuelve a seleccionar al arrastrar."
               if raton else "El mouse está apagado: la terminal selecciona al arrastrar. Préndelo aquí.")
        yy = parrafo(T, ix, yy, txt, iw, maximo=max(0, y + alto - 1 - yy)) + 1
    if yy < y + alto - 2:
        parrafo(T, ix, yy, "Las sesiones de cada agente viven en su sección: Sesiones ▾ → Todas las sesiones.", iw,
                maximo=max(0, y + alto - 1 - yy))
    return alto


# ── lo de todas ───────────────────────────────────────────────────────────────
def registro():
    """Las secciones de la piel: H-1 (hub_secciones_r2, con sus grupos, Calendario y las pestañas de Agentes) o
    T-2 (estas)."""
    try:
        if D.piel() != "bloque":
            import hub_secciones_r2
            return hub_secciones_r2.SECCIONES
    except Exception:
        pass
    return SECCIONES


def coincide(sec, *textos):
    """¿La fila dice lo que escribiste en la lista (type-to-search)? Sin búsqueda, todas."""
    q = P._sin_acentos((sec or {}).get("busca") or "").strip()
    return not q or q in P._sin_acentos(" ".join(str(t or "") for t in textos))


def filas(kind, s):
    """Las filas que se eligen con ↑↓ de la sección `kind` (sus rid) y la elegida."""
    sec = s.get("seccion") or {}
    hacer = registro().get(kind, (None,))[0]
    if hacer is None:
        return [], ""
    fs = hacer(s)
    fs = [f if isinstance(f, dict) else {"rid": f} for f in fs]
    return [f["rid"] for f in fs if f.get("rid")], elegida(sec, fs)


VERBO = {"sesiones": "abre", "ayuda": "usa", "skills": "la usa", "motores": "verifica", "ajustes": "aplica",
         "agentes": "conversa", "calendario": "hecho"}


def teclas(sec, s):
    k = sec.get("kind")
    if sec.get("editando"):
        return [("Enter", "guarda"), ("Esc", "cancela")]
    out = [("↑↓", "elige"), ("Enter", VERBO.get(k, "abre"))]
    if k == "sesiones":
        out.append(("←→", "filtro"))
    elif k == "ajustes":
        out.append(("←→", "opción"))
    elif k == "calendario":
        out = [("←→↑↓", "día"), ("AvPág", "mes"), ("Enter", "su agenda")]
    elif k == "conexiones" and sec.get("lab"):           # la vista de laboratorio (la prueba a fondo)
        out = [("←→↑↓", "celda"), ("Enter", "evidencia"), ("v", "verifica"), ("V", "todos"), ("r", "repara")]
    elif k == "conexiones":                              # Conexiones en verde
        out = [("←→", "motor"), ("↑↓", "fila"), ("Enter", "su acción"), ("R", "revisa"), ("p", "reporta")]
    elif k == "agentes" and sec.get("vista") == "tablero":
        out = [("←→", "agente"), ("↑↓", "motor"), ("Enter", "el cruce")]
    out += [("Esc", "vuelve"), ("F1", "ayuda")]
    return out


#: Cada sección: (sus filas, su lista, su detalle). Las piezas dibujan en el marco `M` que les den (xl, wl, y0..y1
#: para la lista; xd, wd, yd para el detalle): hoy la sección a pantalla completa (marco()); mañana, un panel o un
#: menú, con otro marco y las mismas piezas.
SECCIONES = {"sesiones": (lambda s: [f["rid"] for f in sesiones_filas(s)[1] if f.get("rid")], sesiones_lista,
                          sesiones_detalle),
             "skills": (skills_filas, skills_lista, skills_detalle),
             "motores": (motores_filas, motores_lista, motores_detalle),
             "ajustes": (ajustes_filas, ajustes_lista, ajustes_detalle),
             "agentes": (agentes_filas, agentes_lista, agentes_detalle),
             "ayuda": (ayuda_filas, ayuda_lista, ayuda_detalle)}


def seccion(L, s, M, sec):
    """La sección `sec` en el marco `M`: su lista (si se ve) y su detalle (si se ve)."""
    _f, lista, detalle = registro()[sec["kind"]]
    if M["lado"] or not sec.get("abierto"):
        lista(L, s, M, sec)
    if M["detalle"]:
        detalle(L, s, M, sec)


def pantalla(L, s, G, sec):
    """La sección a pantalla completa (en lugar de la conversación): su marco, la sección, el aviso y las teclas."""
    seccion(L, s, marco(L, s, G, sec), sec)
    if s.get("aviso"):                                # lo que pasó (en una línea), sobre las teclas
        T = L.T
        x0 = G["x0"] + 2
        T.put(x0, T.h - 2, " " * max(0, T.w - x0 - 2), None, False, B.BG)
        T.put(x0, T.h - 2, corto(s["aviso"], T.w - x0 - 2), C["tx2"])
    B.fila_teclas(L, s, G, G["x0"] + 2)
