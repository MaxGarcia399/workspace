#!/usr/bin/env python3
r"""WORKSPACE · hub_inicio — Inicio R-1 «Selección»: la portada del hub. SOLO PARA PROBAR: vive en la rama
zenith/hub-h1 y nunca entra a main.

El hub abre en Inicio (R-1, elegido el 19-nov, sin «Ahora»: «solo es información»), con la pasada minimalista H1-a
«Menos ruido» (21-nov): se quitó contenido, no la piel.
  · arriba, «❯ workspace» y cuatro fichas iguales: ⌕ Buscar / (escribe o /), Navegador ↗ (n), ? Guía (?) y ✕;
  · la tarjeta del elegido: su monito grande (←→ trae al de al lado, que llega deslizándose), su nombre y estado, y su
    motor en una caja con ▲▼ (↑↓ o un clic lo cambia; la caja destella). Si el motor elegido no está listo, no se
    cambia: Enter hace lo que necesita («Iniciar sesión ↵»…). Los de al lado, más chicos, con ‹ ›; todos en
    cuadritos sobre el borde de abajo («2 / 17»). Debajo van «Conversar ↵» y «Sesiones s»;
  · las secciones en UNA fila de fichas (Tab), con una sola señal: «!» en Motores si alguno no está listo (sus
    partes se abren desde cada sección, o buscándolas);
  · la línea de abajo con las teclas de lo que tiene el foco.
  Tres niveles: grande (desde 120×40), compacto (desde 96×30) y mini.
Desde la conversación, ⌂ Inicio (al pie del riel) o Esc regresan aquí; aquí, Esc en la tarjeta sale.

Aquí se dibuja (puro, con la instantánea del hub); qué hace cada tecla o clic está en hub_directo.Directo. Stdlib."""
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_paleta as P  # noqa: E402
import hub_directo as D  # noqa: E402
import hub_bloque as B  # noqa: E402
import hub_h1 as H  # noqa: E402
import hub_monitos as MON  # noqa: E402

C = P.C
W, corto = B.W, B.corto
BG, P1, P2, P3, P4 = B.BG, B.P1, B.P2, B.P3, B.P4
OK, WARN = B.OK, B.WARN
#: Desde estas medidas, las tarjetas grandes (el monito de S-1); abajo, las del riel.
ANCHO_GRANDE, ALTO_GRANDE = 120, 40
#: Las secciones de Inicio, en su fila de fichas: (id, nombre, glifo, la tiene el hub). Las que no, abren «en
#: camino».
SECCIONES = (("agentes", "Agentes", "◆", True), ("motores", "Motores", "◈", True), ("skills", "Skills", "▸", True),
             ("calendario", "Calendario", "□", True), ("ajustes", "Ajustes", "≡", True),
             ("ayuda", "Ayuda", "?", True))
EN_CAMINO = tuple(k for k, _n, _g, hay in SECCIONES if not hay)
#: Las sub-secciones de cada mosaico (se tocan, o ↓ y ←→ con el teclado): (id, etiqueta). Abren su sección en esa
#: pestaña o ese grupo.
SUBS = {"motores": (("lista", "Motores"),),
        "agentes": (("apariencia", "Apariencia"), ("tono", "Tono"), ("usuarios", "Quién lo usa"),
                    ("tablero", "Tablero"), ("agregar", "+ Agregar")),
        "ajustes": (("general", "General"), ("apariencia", "Apariencia"), ("permisos", "Permisos"),
                    ("usuarios", "Usuarios"), ("uso", "Uso"), ("actualizaciones", "Actualizaciones"),
                    ("conexiones", "Conexiones")),
        "ayuda": (("teclas", "Teclas"), ("comandos", "Comandos"), ("docs", "Documentación"), ("novedades", "Novedades"))}
LN2 = "#60606b"
#: Cuánto dura el destello del motor cuando cambia (s).
DESTELLO_S = 0.5
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def hoy(ahora=None):
    t = time.localtime(ahora)
    return "%s %d %s · %02d:%02d" % (DIAS[t.tm_wday], t.tm_mday, MESES[t.tm_mon - 1], t.tm_hour, t.tm_min)


def grande(w, h):
    return w >= ANCHO_GRANDE and h >= ALTO_GRANDE


# ── los datos de Inicio (puros) ───────────────────────────────────────────────
def _por_id(s, aid):
    return next((a for a in s.get("agentes") or [] if a["id"] == aid), None)


def lineas(s):
    """La línea de ahora de cada mosaico: {id: (texto, color)}. Solo de los datos que llegaron; mientras no, «…»."""
    d = s.get("datos") or {}
    car = set(s.get("cargando") or ())
    a = B.agente(s)
    out = {}
    sk = s.get("skills_todas_n")
    out["skills"] = (("%d skills de tus agentes" % sk) if sk else ("Buscando sus skills…" if sk is None else
                                                                   "Todavía no hay skills"), None)
    mot = (d.get("motores") or {}).get("motores")
    if mot is None:
        out["motores"] = ("Viendo cómo está cada motor…" if "motores" in car else "Cada motor y su conexión", None)
    else:
        usados = [m for m in mot if m.get("agentes")]
        malo = next((m for m in usados if m.get("estado") not in ("listo", None)), None)
        if malo:
            out["motores"] = ("! %s: %s" % (malo.get("nombre") or malo.get("id"),
                                            D.limpio(malo.get("estado_texto") or malo.get("estado"))), WARN)
        else:
            n = len(usados)
            out["motores"] = (("✓ 1 motor listo" if n == 1 else "✓ %d motores listos" % n) if n else
                              "Ningún motor en uso", OK if n else None)
    cal = (d.get("calendario") or {}).get("eventos")
    if cal is None:
        out["calendario"] = ("Tu agenda", None)
    else:
        hoy_ = time.strftime("%Y-%m-%d")
        n = sum(1 for e in cal if e.get("date") == hoy_ and not e.get("done"))
        out["calendario"] = (("%d evento%s hoy" % (n, "s" if n != 1 else "")) if n else "Nada hoy", None)
    out["agentes"] = ("%d agentes · su cara, su tono y quién los usa" % len([x for x in s.get("agentes") or []
                                                                              if not x.get("nuevo")]), None)
    out["ajustes"] = ("General, permisos, usuarios, uso…", None)
    out["ayuda"] = ("Teclas, comandos, manual y novedades", None)
    return out


def orden(s):
    """El orden de los agentes en Inicio (el del diseño R-1): primero lo que pide atención (te pregunta, trabaja,
    terminó), luego los libres y los que duermen; dentro de cada grupo, su orden de siempre."""
    peso = {"pregunta": 0, "trabaja": 1, "termino": 2, "libre": 3, "error": 3, "duerme": 4}
    ag = s.get("agentes") or []
    # el agente dormido de «Agregar agente» (hub_agregar.dormido) siempre al final de la fila
    return sorted(range(len(ag)), key=lambda i: (9 if ag[i].get("nuevo") else peso.get(ag[i].get("st"), 5), i))


def busca(s):
    """Lo que dice la búsqueda de Inicio: ("agente", i) · ("seccion", id) · None. Primero un agente (en el orden de
    Inicio); si ninguno, una sección o sub-sección."""
    q = P._sin_acentos(s.get("ini_busca") or "").strip()
    if not q:
        return None
    ag = s.get("agentes") or []
    for i in orden(s):
        if q in P._sin_acentos("%s %s" % (ag[i].get("n"), ag[i].get("id"))):
            return ("agente", i)
    for mid, nom, _g, _h in SECCIONES:
        if q in P._sin_acentos(nom):
            return ("seccion", mid)
    for mid, subs in SUBS.items():
        for sid, lab in subs:
            if q in P._sin_acentos(lab):
                return ("sub", "%s:%s" % (mid, sid))
    return ("nada", None)


# ── los motores del elegido ───────────────────────────────────────────────────
def motores(s):
    """Los motores de esta computadora (de /api/sistema/motores), o None mientras no llegan."""
    return ((s.get("datos") or {}).get("motores") or {}).get("motores")


def usable(m):
    return bool(m and m.get("listo")) and m.get("sesion") is not False and m.get("estado") != "sin_sesion"


def motor_de(s, a):
    """El motor elegido del agente en Inicio: el que eligió con ↑↓ y todavía no está listo, o el de su conversación."""
    return ((s.get("ini_motor") or {}).get(a["id"])) or a.get("motor") or a.get("mid")


def estado_motor(m):
    """→ (signo, texto, color) de un motor."""
    if not m:
        return "·", "sin datos", C["tx3"]
    if usable(m):
        return "✓", "listo", OK
    e = m.get("estado")
    if e == "sin_sesion" or m.get("sesion") is False:
        return "!", "sin sesión", WARN
    if e == "no_instalado" or m.get("instalado") is False:
        return "○", "no instalado", C["tx3"]
    return "!", corto(D.limpio(m.get("estado_texto") or e or "no está listo"), 18), WARN


def accion(s, a):
    """Lo que hace Enter con su motor: (etiqueta del botón, palabra de la línea de abajo, clave)."""
    if a.get("nuevo"):                                # el dormido: la tarjeta «Agregar agente»
        return _ta("agregar.dormido.boton", "+ Agregar"), _ta("agregar.k.despertar", "despertar"), "agregar"
    mid = motor_de(s, a)
    ms = motores(s)
    m = next((x for x in ms or () if x.get("id") == mid), None)
    if ms is None or m is None or usable(m):
        return "Conversar", "conversar", "conv"
    e = m.get("estado")
    if e == "sin_sesion" or m.get("sesion") is False:
        return "Iniciar sesión", "iniciar sesión", "login"
    if e == "no_instalado" or m.get("instalado") is False:
        return "Cómo instalarlo", "cómo instalarlo", "instalar"
    if sesion_sin_saber(m):
        return "Conversar", "conversar", "conv"
    return "Revisarlo", "revisarlo", "revisar"


def sesion_sin_saber(m):
    """¿Instalado y sin saber todavía si tiene sesión (su comando oficial no respondió, o se está revisando)? Eso no
    bloquea: Enter conversa y, si de verdad falta la sesión, lo dice su motor al abrir (portón del primer mensaje, PC,
    23-nov: OpenCode con su servicio en segundo plano no responde `auth list`)."""
    return bool(m) and m.get("instalado") is not False and m.get("sesion") is None \
        and m.get("estado") in ("instalado", "verificando")


def _ta(clave, es):
    """Un texto del dormido de «Agregar agente», en el idioma del hub (agregar_logica.idioma: español en la v1)."""
    try:
        import agregar_logica
        v = agregar_logica._t(clave)
        return es if v == clave else v
    except Exception:
        return es


def _edad(s, a, clave):
    t0 = ((s.get("anim") or {}).get(a.get("id")) or {}).get(clave)
    return (s.get("t") or 0) - t0 if t0 is not None else 9.0


#: El deslizamiento del monito al cambiar de agente: columnas de más por cuadro (de 16 por segundo).
DESLIZA = (12, 7, 3)
CUADRO = 1 / 16.0


def destella(s):
    """¿Algún motor destella o un monito se desliza (para que el hub pinte sus cuadros)? → s hasta el siguiente o
    None."""
    t = s.get("t") or 0
    for an in (s.get("anim") or {}).values():
        t0 = an.get("motor")
        if t0 is not None and 0 <= t - t0 < DESTELLO_S:
            return CUADRO
        t0 = an.get("desliza")
        if t0 is not None and 0 <= t - t0 < CUADRO * len(DESLIZA):
            return CUADRO
    return None


# ── las piezas de R-1 «Selección» ─────────────────────────────────────────────
#: Las fichas de arriba, de derecha a izquierda: (id, etiqueta, corta, más corta).
FICHAS = (("bar:salir", " ✕ ", " ✕ ", " ✕ "), ("bar:guia", " ? Guía ", " ? Guía ", " ? "),
          ("ini:web", " Navegador ↗ ", " ↗ ", " ↗ "), ("ini:buscar", " ⌕ Buscar  / ", " ⌕ / ", " ⌕ "))


def cabecera(L, s, w, compacta=False):
    """H1-a: la marca y, a la derecha, cuatro fichas iguales (⌕ Buscar /, Navegador ↗, ? Guía, ✕); buscando, la de
    buscar se abre y enseña lo que llevas. Si no caben, sus etiquetas cortas."""
    T = L.T
    H.area(L, 1, 0, w - 2, 3, P1, foco_a=B.agente(s) if s.get("foco_area") == "barra" else None)
    a = B.agente(s)
    xx = T.put(3, 1, "❯", a["c"], True, P1)
    xl = T.put(xx + 1, 1, "workspace", C["tx"], True, P1) + 3
    q = s.get("ini_busca") or ""
    buscando = bool(q) or bool(s.get("ini_buscando"))
    nada = buscando and (busca(s) or ("",))[0] == "nada"
    for k in (1, 2, 3):
        labs = [f[k] for f in FICHAS]
        if buscando:                                  # buscar, abierta: lo que llevas (y «nada» si nada coincide)
            labs[3] = " ⌕ %s " % corto(q, 18) + "  " + ("nada " if nada else "")
            labs[3] = labs[3] + " " * max(0, 16 - W(labs[3]))
        if w - 3 - sum(W(x_) + 3 for x_ in labs) >= xl:
            break
    xr = w - 3
    for (rid, _l1, _l2, _l3), lab in zip(FICHAS, labs):
        xr -= W(lab) + 2
        hov = L.reg(xr, 0, W(lab) + 2, 3, rid)
        abierta = rid == "ini:buscar" and buscando
        fondo = P4 if L.apr(rid) else (P3 if (hov or abierta) else P2)
        B.ficha(T, xr, 1, lab, fondo, P1, C["tx"] if (hov or abierta) else C["tx2"], abierta)
        if abierta:
            T.put(xr + 2, 1, "⌕", a["c"], True, fondo)
            T.put(xr + 4 + W(corto(q, 18)), 1, "▏", a["c"], False, fondo)
            if nada:
                T.put(xr + 1 + W(lab) - 5, 1, "nada", WARN, False, fondo)
        xr -= 1


def flecha(L, x, y, lado):
    """‹ › a los lados, ligeras (H1-a): solo el glifo; su zona sigue grande para el mouse. Un clic trae al de al
    lado."""
    T = L.T
    rid = "ini:flecha:%d" % lado
    hov = L.reg(x, y, 5, 4, rid)
    if hov or L.apr(rid):
        B.bloque(T, x, y, 5, 3, P4 if L.apr(rid) else P2, BG)
    T.put(x + 2, y + 1, "‹" if lado < 0 else "›", C["tx"] if hov else C["tx3"], True)


def apagado(c, k):
    return P.mix(c, BG, k)


def vecinos(L, s, cx, yb, ids, k_sel, slots):
    """Los de al lado, más chicos y tenues (un clic los trae al centro). `slots`: [(paso, tam, dx, tenue)]."""
    T = L.T
    ag = s["agentes"]
    n = len(ids)
    usados = {ids[k_sel]}
    for paso, tam, dx, tenue in slots:
        if n < 2:
            break
        i = ids[(k_sel + paso) % n]
        if i in usados:                               # cada uno una sola vez (con 2 o 3, la vuelta lo repetía)
            continue
        usados.add(i)
        a = ag[i]
        mw, mh = MON.medidas(tam)
        xc = cx + dx
        x, y = xc - mw // 2, yb - mh + 1
        L.reg(x - 2, y - 1, mw + 4, mh + 3, "ini:ag:" + a["id"])
        MON.dibujar(T, dict(a, c=apagado(a["c"], tenue)), x, y, tam, s=s, st=a.get("st"))
        T.center(xc - 8, 16, yb + 2, corto(a["n"], 15), C["tx2"] if tenue < 0.5 else C["tx3"], False)


def puntos(L, s, cx, y, ids, k_sel, ancho):
    """Los agentes en cuadritos de su color sobre el borde de abajo: «2 / 17», dónde estás; un clic salta."""
    T = L.T
    ag = s["agentes"]
    n = len(ids)
    reales = sum(1 for i in ids if not ag[i].get("nuevo"))   # el dormido de «Agregar» no cuenta como agente
    t = (" + / %d " % reales) if ag[ids[k_sel]].get("nuevo") else " %d / %d " % (k_sel + 1, reales)
    cab = max(1, min(n, (ancho - W(t) - 4) // 2))
    k0 = max(0, min(k_sel - cab // 2, n - cab))
    x0 = cx - (W(t) + 2 * cab) // 2
    x = T.put(x0, y, t, C["tx3"], False, BG)
    for j in range(cab):
        k = k0 + j
        a = ag[ids[k]]
        on = k == k_sel
        hov = L.reg(x + 2 * j, y, 2, 1, "ini:punto:" + a["id"]) and not on
        T.put(x + 2 * j, y, "■" if on else "▪", a["c"] if on else apagado(a["c"], 0.15 if hov else 0.5), on, BG)
        T.put(x + 2 * j + 1, y, " ", None, False, BG)


def selector_motor(L, s, a, x, y, w, foco):
    """Su motor en UNA caja (H1-a): ◈ su nombre, su estado y ▲ ▼ a la derecha (↑↓, o un clic en ▲ o ▼, lo cambia;
    al cambiar, la caja destella). Sin los vecinos tenues."""
    T = L.T
    ms = motores(s) or []
    mid = motor_de(s, a)
    m = next((x_ for x_ in ms if x_.get("id") == mid), None)
    g, txt, col = estado_motor(m) if ms else ("·", "viendo…", C["tx3"])
    edad = _edad(s, a, "motor")
    fondo = P.mix(a["c"], BG, 0.55) if 0 <= edad < DESTELLO_S / 2 else (P4 if 0 <= edad < DESTELLO_S else P3)
    hov = L.reg(x, y + 1, w - 8, 3, "ini:mot:actual")
    ha = L.reg(x + w - 8, y + 1, 4, 3, "ini:mot:arriba")
    hb = L.reg(x + w - 4, y + 1, 4, 3, "ini:mot:abajo")
    H.area(L, x, y + 1, w, 3, fondo, linea=a["c"] if foco else (LN2 if (hov or ha or hb) else H.LN))
    T.put(x + 3, y + 2, "◈", a["c"], True, fondo)
    T.put(x + 5, y + 2, corto(D.nombre_motor(mid), w - 24), B.LUZ, True, fondo)
    T.right(x + w - 8, y + 2, "%s %s" % (g, txt), col, True)
    T.put(x + w - 6, y + 2, "▲", C["tx"] if ha else C["tx3"], ha, fondo)
    T.put(x + w - 4, y + 2, "▼", C["tx"] if hb else C["tx3"], hb, fondo)


def nota_motor(s, a):
    """Debajo del selector: qué hace Enter si su motor no está listo; o, recién cambiado, desde cuándo lo usa."""
    _lab, verbo, k = accion(s, a)
    nom = D.nombre_motor(motor_de(s, a))
    if k == "login":
        return "! ", WARN, "%s no tiene sesión · Enter abre su inicio oficial" % nom
    if k == "instalar":
        return "○ ", C["tx3"], "%s no está instalado · Enter: cómo instalarlo" % nom
    if k == "revisar":
        return "! ", WARN, "%s no está listo · Enter: revisarlo" % nom
    m = next((x for x in motores(s) or () if x.get("id") == motor_de(s, a)), None)
    if k == "conv" and m is not None and not usable(m) and sesion_sin_saber(m):
        return "! ", WARN, "%s: no pude revisar su sesión · Enter: conversar" % nom
    if 0 <= _edad(s, a, "motor") < 4.0:
        return "✓ ", OK, "%s usará %s desde su siguiente mensaje" % (a["n"], nom)
    return None


#: Las medidas de la tarjeta por nivel: (ancho, alto, monito, filas del monito a su base).
NIVELES = {"grande": (60, 25, 16, 11), "compacto": (46, 19, 16, 9), "mini": (46, 12, 8, 4)}


def nivel(w, h):
    """grande (desde 120×40), compacto (desde 96×30) o mini."""
    if grande(w, h):
        return "grande"
    return "compacto" if w >= 96 and h >= 30 else "mini"


def medidas(w, nv):
    """→ (cx, sx, ancho y alto de la tarjeta)."""
    cw_, ch, _tam, _yb = NIVELES[nv]
    cw_ = min(cw_, w - 4)
    cx = w // 2
    sx = cx - cw_ // 2
    return cx, sx, cw_, ch


def escenario(L, s, w, cy, nv):
    """La tarjeta del elegido (R-1): su monito grande (se desliza al cambiar), su nombre y estado, su motor como
    selector, los de al lado más chicos con ◀ ▶ y los agentes en cuadritos sobre el borde de abajo. Las acciones
    «Conversar ↵» (o lo que necesite su motor) y «Sesiones s» quedan debajo de la tarjeta.
    → la fila siguiente a lo dibujado."""
    T = L.T
    ag = s["agentes"]
    ids = orden(s)
    i = s.get("sel") or 0
    a = ag[i]
    k_sel = ids.index(i) if i in ids else 0
    foco = (s.get("foco_area") or "agentes") == "agentes" and not s.get("ini_busca")
    _cw, _ch, tam, dyb = NIVELES[nv]
    cx, sx, cw_, ch = medidas(w, nv)
    yb = cy + dyb
    if isinstance(getattr(T, "geo", None), dict):     # dónde quedó la tarjeta (la guía la ilumina)
        T.geo["tarjeta"] = (sx, cy, cw_, ch)
    H.area(L, sx, cy, cw_, ch, P1, linea=a["c"] if foco else H.LN)
    # los de al lado (si caben) y ◀ ▶
    if nv != "mini":
        slots = [(-1, 8, -(cw_ // 2 + 11), 0.35), (1, 8, cw_ // 2 + 11, 0.35)]
        if nv == "grande":
            slots += [(-2, 6, -62, 0.62), (2, 6, 62, 0.62)]
        vecinos(L, s, cx, yb, ids, k_sel, [sl for sl in slots if 8 < cx + sl[2] - 6 and cx + sl[2] + 6 < w - 8])
    flechas = len(ids) > 1 and sx >= 9
    if flechas:
        for lado_ in (-1, 1):
            flecha(L, 2 if lado_ < 0 else w - 7, max(cy + 1, yb - 3), lado_)
    # el elegido, grande (al cambiar, llega deslizándose desde el lado)
    mw, mh = MON.medidas(tam)
    an = (s.get("anim") or {}).get(a["id"]) or {}
    edad = _edad(s, a, "desliza")
    kf = int(edad / CUADRO) if edad >= 0 else 99
    dx = DESLIZA[kf] * (an.get("dir") or 1) if 0 <= kf < len(DESLIZA) else 0
    dx = max(-(cw_ // 2 - mw // 2 - 2), min(cw_ // 2 - mw // 2 - 2, dx))
    x0, y0 = cx - mw // 2 + dx, yb - mh + 1
    L.reg(cx - mw // 2, y0, mw, mh, "ini:card:" + a["id"])
    MON.dibujar(T, a, x0, y0, tam, s=s, st=a.get("st"))
    if dx:
        T.put(x0 + (mw + 1 if dx > 0 else -4), yb - mh // 2, "‹‹‹" if dx > 0 else "›››", C["tx3"], False, P1)
    yn = yb + (2 if nv != "mini" else 1)
    T.center(sx, cw_, yn, corto(a["n"], cw_ - 4), a["c"], True)
    nuevo = bool(a.get("nuevo"))
    if nv == "grande":
        t, col, b = D.estado_riel(a, s.get("ahora"))
        if nuevo:
            t, col, b = _ta("agregar.dormido.estado", "duerme · despiértalo"), C["tx3"], False
        T.center(sx, cw_, yb + 3, corto(t, cw_ - 4), col, b)
    sel_w = min(44 if nv == "grande" else 38, cw_ - 4)
    sel_y = yb + {"grande": 6, "compacto": 4, "mini": 2}[nv]
    if nuevo:                                         # el dormido no tiene motor todavía: lo elige al despertar
        T.center(sx, cw_, sel_y + 2, corto(_ta("agregar.dormido.estado", "duerme · despiértalo") if nv != "grande"
                                           else _ta("agregar.estado.sin_motor", "duerme · sin motor"), cw_ - 4),
                 C["tx3"])
    else:
        selector_motor(L, s, a, cx - sel_w // 2, sel_y, sel_w, foco)
    nota = nota_motor(s, a) if nv == "grande" and not nuevo else None
    if nota:
        t = nota[0] + nota[2]
        xn = sx + max(1, (cw_ - W(t)) // 2)
        T.put(xn, sel_y + 6, nota[0], nota[1], True, P1)
        T.put(xn + W(nota[0]), sel_y + 6, corto(nota[2], cw_ - 4 - W(nota[0])), C["tx2"], False, P1)
    puntos(L, s, cx, cy + ch - 1, ids, k_sel, cw_ - 4)
    lab, _v, _k = accion(s, a)
    # Las dos acciones quedan juntas, centradas debajo del selector.
    y = cy + ch + 1
    l1, l2 = " %s ↵ " % lab, (" %s s " % _ta("agregar.dormido.cargar", "Ya tengo uno")) if nuevo else " Sesiones s "
    l3 = "" if nuevo else " Archivar "
    if l3 and W(l1) + W(l2) + W(l3) + 10 > T.w - 2:   # no caben los tres: el de siempre
        l3 = ""
    x = cx - (W(l1) + W(l2) + 5 + ((W(l3) + 3) if l3 else 0)) // 2
    r1, r2 = "ini:conv:" + a["id"], "ini:ses:" + a["id"]
    h1 = L.reg(x, y, W(l1) + 2, 1, r1)
    xx = B.ficha(T, x, y, l1, P.mix(a["c"], "#ffffff", 0.18) if h1 else a["c"], BG, B.LUZTX, True) + 1
    h2 = L.reg(xx, y, W(l2) + 2, 1, r2)
    xx = B.ficha(T, xx, y, l2, P4 if h2 else P3, BG, C["tx"] if h2 else C["tx2"]) + 1
    if l3:                                            # «Archivar»: sale de las listas, nada se borra, se deshace
        h3 = L.reg(xx, y, W(l3) + 2, 1, "ini:arch:" + a["id"])
        B.ficha(T, xx, y, l3, P4 if h3 else P3, BG, C["tx"] if h3 else C["tx2"])
    if nuevo:
        fila_archivados(L, s, cx, y + 1)
    return y + 1


def fila_archivados(L, s, cx, y):
    """Debajo de «Agente nuevo»: los archivados, cada uno una ficha que lo trae de vuelta con un clic (también cuando
    no queda ningún agente). Los que no caben, tras «+N»."""
    T = L.T
    arch = ((s.get("datos") or {}).get("archivados") or {}).get("archivados") or []
    if not arch or y >= T.h - 1:
        return
    titulo = "Archivados · traer de vuelta:"
    if T.w < 100:
        titulo = "Traer de vuelta:"
    i0 = (s.get("ini_arch_i") or 0) % len(arch)
    orden = arch[i0:] + arch[:i0]
    fichas, ancho = [], W(titulo) + 1
    for z in orden:
        lab = " %s " % corto(z.get("display") or z.get("name") or "", 14)
        if ancho + W(lab) + 3 + (7 if len(fichas) + 1 < len(orden) else 0) > T.w - 4 and fichas:
            break
        fichas.append((lab, "ini:volver:" + str(z.get("name"))))
        ancho += W(lab) + 3
    faltan = len(orden) - len(fichas)
    if faltan:
        fichas.append((" +%d " % faltan, "ini:archmas"))
        ancho += W(fichas[-1][0]) + 3
    x = max(1, cx - ancho // 2)
    x = T.put(x, y, titulo, C["tx3"], False, BG) + 1
    for lab, rid in fichas:
        hov = L.reg(x, y, W(lab) + 2, 1, rid)
        x = B.ficha(T, x, y, lab, P4 if hov else P3, BG, C["tx"] if hov else C["tx2"]) + 1


def sub_foco(s):
    """La sección cuyo mosaico (o sub-sección) tiene el foco, o None."""
    f = str(s.get("foco") or "")
    if f.startswith(("ini:sec:", "ini:sub:")):
        return f.split(":")[2]
    return None


def senal_motores(s):
    """¿Algún motor que usan tus agentes no está listo? (la única señal de Inicio: «!» en Motores)."""
    return lineas(s).get("motores", ("", None))[1] == WARN


def chips_secciones(L, s, x, y, w, focos):
    """H1-a: las secciones en UNA fila de fichas iguales dentro de su marco (Tab llega aquí), con una sola señal: «!»
    en Motores si algún motor que usan no está listo. Si no caben con su glifo, solo su nombre."""
    T = L.T
    a = B.agente(s)
    foco = s.get("foco_area") == "secciones"
    f_sec = sub_foco(s)
    r = busca(s)
    hallada = r[1] if r and r[0] == "seccion" else (r[1].split(":")[0] if r and r[0] == "sub" else None)
    H.area(L, x, y, w, 3, P1, linea=a["c"] if foco else H.LN)
    if isinstance(getattr(T, "geo", None), dict):
        T.geo["secciones"] = (x, y, w, 3)
    senal = senal_motores(s)
    for con_glifo, aire, pad in ((True, 2, " "), (False, 2, " "), (False, 1, " "), (False, 1, "")):
        labs = [(mid, gl, "%s%s%s%s%s" % (pad, gl + " " if con_glifo else "", nom,
                                          " !" if (senal and mid == "motores") else "", pad))
                for mid, nom, gl, _h in SECCIONES]
        total = sum(W(lab) + 2 for _m, _g, lab in labs) + aire * (len(labs) - 1)
        if total <= w - 6:
            break
    xx = x + max(2, (w - total) // 2)
    for k, (mid, gl, lab) in enumerate(labs):
        rid = "ini:sec:" + mid
        on = (foco and f_sec == mid) or hallada == mid
        hov = L.reg(xx, y, W(lab) + 2, 3, rid)
        fondo = P4 if L.apr(rid) else (P3 if (hov or on) else P2)
        B.ficha(T, xx, y + 1, lab, fondo, P1, C["tx"] if (hov or on) else C["tx2"], on)
        if con_glifo:
            T.put(xx + 2, y + 1, gl, a["c"], True, fondo)
        if lab.rstrip().endswith("!"):
            T.put(xx + 1 + len(lab.rstrip()) - 1, y + 1, "!", WARN, True, fondo)
        if focos is not None:
            focos.append((rid, 1, k))
        xx += W(lab) + 2 + aire


def barra_secciones(L, s, x, y, w, alto, focos, compacto=False):
    """(antes de H1-a, la barra de compartimentos con su línea de ahora y sus partes) Hoy, la fila de fichas."""
    return chips_secciones(L, s, x, y, w, focos)


def _subs(L, s, mid, x, y, w, y_max, fondo, focos, col):
    T = L.T
    xx, yy = x, y
    for sid, lab in SUBS.get(mid) or ():
        r = "ini:sub:%s:%s" % (mid, sid)
        lab = corto(lab, w - 1)
        if xx + W(lab) + 1 > x + w and xx > x:        # no cabe: a la fila de abajo (si hay)
            if yy + 1 > y_max:
                break
            xx, yy = x, yy + 1
        hs = L.reg(xx - 1, yy, W(lab) + 2, 1, r)
        T.put(xx - 1, yy, " %s " % lab, C["tx"] if hs else C["tx3"], hs, P3 if hs else fondo)
        xx += W(lab) + 2
        if focos is not None:
            focos.append((r, 2, col))


def teclas_area(s):
    """Las teclas del área enfocada de Inicio (lo mismo que dice Ayuda › Las teclas). Enter dice lo que hará."""
    area = s.get("foco_area") or "agentes"
    if s.get("ini_busca") or s.get("ini_buscando"):
        r = busca(s)
        enter = {"seccion": "la abre", "sub": "la abre"}.get((r or ("",))[0], "—")
        if r and r[0] == "agente":                    # lo que hará con su motor: conversar, iniciar sesión…
            enter = accion(s, (s.get("agentes") or [])[r[1]])[1]
        return [("Enter", enter), ("⌫", "borra"), ("Esc", "deja de buscar")]
    if area == "secciones":
        return [("←→", "sección"), ("Enter", "abre"), ("Tab", "agentes"), ("Esc", "regresa"), ("?", "guía")]
    if area == "agentes":
        ag = s.get("agentes") or []
        a = ag[s.get("sel") or 0] if ag else None
        verbo = accion(s, a)[1] if a else "conversar"
        if a and a.get("nuevo"):
            return [("←→", "agente"), ("Enter", verbo), ("s", _ta("agregar.dormido.cargar", "Ya tengo uno").lower()),
                    ("Tab", "secciones"), ("?", "guía")]
        return [("←→", "agente"), ("↑↓", "motor"), ("Enter", verbo), ("s", "sesiones"), ("Tab", "secciones"),
                ("?", "guía"), ("^A", "archivar")]
    return [("←→", "elige"), ("Enter", "abre"), ("Tab", "otra área"), ("Esc", "regresa")]


def linea_abajo(L, s, y):
    """La línea de abajo, de lado a lado: dónde estás y las teclas de lo que tiene el foco (o el aviso)."""
    T = L.T
    w = T.w
    T.put(0, y, " " * w, None, False, P1)
    a = B.agente(s)
    x = T.put(1, y, "❯", a["c"], True, P1)
    x = T.put(x + 1, y, "workspace", C["tx"], True, P1) + 3
    ap = s.get("apartado")
    if ap and ap.get("nombre") and (s.get("t") or 0) - (ap.get("t") or 0) < 45.0 and \
            not str(s.get("aviso") or "").startswith("✗"):   # un error (no se pudo deshacer) se ve primero
        # lo último que archivaste o quitaste, con su «Deshacer» (hub_agentes_maquina.DESHACER_S)
        lab = " Deshacer ^U "
        xb = w - W(lab) - 4
        T.put(x, y, corto("✓ " + (ap.get("texto") or ""), max(8, xb - x - 2)), C["tx2"], False, P1)
        hov = L.reg(xb, y, W(lab) + 2, 1, "ini:deshacer")
        B.ficha(T, xb, y, lab, P4 if hov else P3, P1, C["tx"], True)
        return
    if s.get("aviso"):
        T.put(x, y, corto(s["aviso"], w - x - 2), C["tx2"], False, P1)
        return
    ks = teclas_area(s)
    if w < 120:                                       # angosta: las cortas
        ks = [("↵", lab) if k == "Enter" else (k, lab) for k, lab in ks]
    for k, lab in ks:
        if x + W(k) + 3 + W(lab) + 2 > w - 2:
            break
        x = T.key(x, y, k, lab)


def teclas(T, x, y, ks):
    for k, lab in ks:
        if x + W(k) + W(lab) + 4 > T.w:
            break
        x = T.key(x, y, k, lab)


# ── la pantalla ───────────────────────────────────────────────────────────────
def pantalla(w, h, s, crudo=False):
    """Inicio R-1 «Selección» en w×h. → Term con sus zonas, `focos` [(rid, fila, columna)] y `geo` (sin panel).
    `crudo`: sin el color P-3 (para la entrada a S-1, que la mezcla y la afina una vez)."""
    T = P.Term(w, h)
    T.fill(0, 0, w, h, BG)
    T.scroll_max, T.riel, T.lado, T.focos = 0, None, True, []
    T.geo = {"nivel": "inicio", "panel": None, "franja": None, "cajon": None}
    if w < P.MIN_W or h < P.MIN_H:
        T.center(0, w, h // 2, "Agranda la ventana", C["tx2"])
        return P.afinar(T, ((s.get("datos") or {}).get("preferencias") or {}).get("fondo"))
    L = B.Lienzo(T, s)
    ag = s.get("agentes") or []
    gr = grande(w, h)
    cabecera(L, s, w, not gr)
    if not ag:
        T.center(0, w, h // 2, corto("Todavía no tienes agentes.", w - 2), C["tx2"])
        hb = L.reg(w // 2 - 7, h // 2 + 2, 15, 1, "ini:nuevo")
        B.ficha(T, w // 2 - 7, h // 2 + 2, " + Agregar ", P3 if hb else P2, BG, C["tx"])
        return P.afinar(T, ((s.get("datos") or {}).get("preferencias") or {}).get("fondo"))
    focos = [("ini:card:" + ag[s.get("sel") or 0]["id"], 0, 0)]
    nv = nivel(w, h)
    _cx, _sx, _cw, ch = medidas(w, nv)
    libre = h - (3 + ch + 2 + 1 + 3 + 1)              # arriba, la tarjeta y sus acciones, aire, las fichas y abajo
    cy = 3 + max(0, libre // 2)
    fin = escenario(L, s, w, cy, nv)
    ys = min(fin + (2 if libre >= 2 else 1), h - 4)
    chips_secciones(L, s, 2, ys, w - 4, focos)
    T.flat()
    linea_abajo(L, s, h - 1)
    H.marcar_foco(T, s)
    T.focos = focos
    return T if crudo else P.afinar(T, ((s.get("datos") or {}).get("preferencias") or {}).get("fondo"))


# ── «en camino»: una sección que el hub todavía no tiene ──────────────────────
def en_camino(L, s, x, y, w, h, cual):
    """Una pantalla clara (y honesta) de una sección que la terminal todavía no tiene: su línea de ahora (de verdad),
    que viene en camino, y «Abrir la página ↗» (ahí sí está)."""
    T = L.T
    sec = next((x_ for x_ in SECCIONES if x_[0] == cual), (cual, cual.capitalize(), "·", False))
    a = B.agente(s)
    txt, col = lineas(s).get(cual, ("", None))
    cw = min(64, w - 6)
    cx = x + (w - cw) // 2
    cy = y + max(1, (h - 12) // 2)
    H.area(L, cx, cy, cw, 11, P1, titulo=[(sec[2] + " ", a["c"], True), (sec[1], C["tx"], True),
                                          (" · en camino", C["tx3"], False)])
    if txt:
        T.put(cx + 3, cy + 2, corto(txt, cw - 6), a["c"] if col == "agente" else (col or C["tx2"]), False, P1)
    yy = cy + 4
    for ln in D.envolver([("Esta sección todavía no está en el hub de la terminal. Mientras, la tienes completa en "
                           "la página.", C["tx2"], False)], cw - 6)[:3]:
        D._linea(T, cx + 3, yy, ln, cx + cw - 3)
        yy += 1
    B.boton(L, s, cx + 3, cy + 7, "Abrir la página ↗", "acc:pagina", P1, foco=True, wmin=24, a=a)
    lab = " ⌂ Inicio  Esc "
    hb = L.reg(cx + cw - 3 - W(lab) - 2, cy + 8, W(lab) + 2, 1, "sec:volver")
    B.ficha(T, cx + cw - 3 - W(lab) - 2, cy + 8, lab, P3 if hb else P2, P1, C["tx"] if hb else C["tx2"])
