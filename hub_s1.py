#!/usr/bin/env python3
r"""WORKSPACE · hub_s1 — S-1 «Lista con su monito»: el menú de sesiones de un agente al abrirlo en su programa
oficial, con la piel H-1 (la versión de Zenith). SOLO PARA PROBAR: vive en la rama zenith/hub-h1 y nunca entra a main.

Es el menú de sesiones de siempre (I11): agent_ui.menu_sesiones y agent_ui.live_picker (la entrada que llaman los
menús que viven en cada cerebro) lo usan, desde el hub o escribiendo el comando del agente; dispatch pone la marca
WORKSPACE_HUB_S1=1 para lo que abre. En Windows, con el lector de la consola del hub. Solo una copia de desarrollo
con WORKSPACE_HUB_S1=0 enseña el de antes.

La pantalla: una columna centrada; arriba el monito grande del agente y con qué programa se abre; en medio sus
sesiones (dos filas cada una: su tecla 1-9, su estado, su nombre, su motor y cuándo; abajo lo último que dijo; el
mouse encima enseña «a  archivar»); abajo los botones grandes «Abrir «…» ↵», «+ Nueva sesión» y «Archivadas · N». La
de las archivadas, con «Recuperar y abrir ↵» y «← Tus sesiones». Con menos de 36 filas (100×30), el monito chico y 4
sesiones a la vista.

Las teclas son las de siempre (↑↓, Enter, Esc, Ctrl+C, 1-9, a, u) y devuelven lo mismo que live_picker: el índice
elegido, BACK, (tecla, índice) o None sin terminal. El mouse es extra. Los datos de cada sesión (estado, motor, cuándo,
lo último) se leen del registro de la pestaña (pagina_sesiones.resumen, solo lectura); lo que no se sabe no se
inventa. Stdlib."""
import json
import os
import queue
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

BACK = "BACK"
#: Las filas que agrega agent_ui.menu_sesiones (no son sesiones): «Archivadas (N)» y «← Volver».
ARCH, VOLVER = "ARCH", "LIST"
CHICO_H = 36


def activo(env=None):
    """I11 · S-1 y sus pantallas de paso (la piel H-1) son las de siempre: también al escribir el comando del agente,
    sin el hub. Solo una copia de desarrollo con WORKSPACE_HUB_S1=0 enseña el menú de antes (para comparar)."""
    env = os.environ if env is None else env
    if str(env.get("WORKSPACE_HUB_S1") or "").strip() != "0":
        return True
    try:
        import puertas
        return not puertas.dev()
    except Exception:
        return True


# ── los datos (puros con lo que les den; el registro, solo para leer) ─────────
def _resumen(brain, wid, nombre):
    if not brain:
        return None
    try:
        import pagina_sesiones as PS
    except Exception:
        return None
    for k in (wid, nombre):
        if not k:
            continue
        try:
            r = PS.resumen(brain, k)
        except Exception:
            r = None
        if r:
            return r
    return None


def fila(item, brain=None, resumen=None):
    """Una fila del menú → {kind, nombre, sub, wid, estado, motor, cuando, ultimo} (lo que se sabe)."""
    lab, sub, kind = item[0], item[1], tuple(item[2])
    f = {"kind": kind[0], "nombre": str(lab or ""), "sub": str(sub or ""), "wid": kind[1] if len(kind) > 1 else None,
         "estado": "", "motor": "", "cuando": "", "ultimo": ""}
    if kind[0] != "WS":
        return f
    res = resumen(kind[1], kind[2] if len(kind) > 2 else lab) if resumen else _resumen(brain, kind[1], lab)
    if res:
        try:
            import pagina_sesiones as PS
            f["estado"] = PS.simple(res)
        except Exception:
            f["estado"] = ""
        fin = res.get("fin") or {}
        f["motor"] = fin.get("motor") or res.get("motor") or ""
        f["cuando"] = fin.get("ts") or res.get("desde") or ""
        f["ultimo"] = " ".join(str(fin.get("texto") or "").split())
    return f


def _precarga(agente):
    ruta = os.environ.get("WORKSPACE_HUB_S1_CACHE")
    if not ruta:
        return {}
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        if datos["agente"] == agente and time.time() < datos["vence"]:
            return {str(r["wid"]): r for r in datos["filas"] if r.get("wid")}
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        pass
    return {}


def _completar_precarga(menu, precarga):
    pendientes = []
    for i, fila_menu in enumerate(menu.filas):
        if fila_menu["kind"] != "WS":
            continue
        cacheada = precarga.get(str(fila_menu["wid"]))
        if cacheada is None:
            pendientes.append(i)
            continue
        ultimo = cacheada.get("ultimo") or {}
        fila_menu.update(estado=cacheada.get("estado") or "", motor=ultimo.get("motor") or cacheada.get("motor") or "",
                         cuando=ultimo.get("ts") or cacheada.get("cuando") or "",
                         ultimo=" ".join(str(ultimo.get("texto") or "").split()))
    return pendientes


_AGENTES = {}


def agente(agent, nombre=""):
    """El agente con su color y su forma (lo mismo que la página: localhost_front.inicio); si no se puede, su nombre
    con el color neutro."""
    if agent in _AGENTES:
        return _AGENTES[agent]
    a = {"id": agent, "n": nombre or agent, "c": "#c9c9d1", "f": "bolita", "mid": "", "st": "libre"}
    try:
        import localhost_front
        for x in localhost_front.inicio().get("agentes") or []:
            if x.get("id") == agent:
                a = {"id": agent, "n": x.get("nombre") or nombre or agent, "c": x.get("color") or a["c"],
                     "f": x.get("forma") or "bolita", "mid": x.get("motor") or "", "st": "libre"}
                break
    except Exception:
        pass
    _AGENTES[agent] = a
    return a


def motor_texto(env=None, a=None):
    """El programa con que se abre (WORKSPACE_ENGINE_LABEL, «Claude Code · fable» → «Claude Code»)."""
    env = os.environ if env is None else env
    t = str(env.get("WORKSPACE_ENGINE_LABEL") or "").split(" · ")[0].strip()
    if t:
        return t
    import hub_directo as D
    return D.nombre_motor((a or {}).get("mid")) if (a or {}).get("mid") else "su programa"


# ── la pantalla ───────────────────────────────────────────────────────────────
def _ses_color(f, a):
    import hub_directo as D
    import hub_paleta as P
    C = P.C
    ico, est = D.ESTADO_SES.get(f.get("estado"), ("·", ""))
    vivo = f.get("estado") in ("trabajando", "te_espera")
    espera = f.get("estado") == "te_espera"
    if not f.get("estado"):
        return "·", C["tx3"], f.get("sub") or "", C["tx3"], False
    return ico, a["c"] if vivo else C["tx3"], est, a["c"] if espera else (C["tx"] if vivo else C["tx3"]), espera


def _ventana(n, sel, cabe):
    if n <= cabe:
        return 0, n
    i0 = max(0, min(sel - cabe // 2, n - cabe))
    return i0, i0 + cabe


def pantalla(w, h, d, sobre="", apretado=None, crudo=False):
    """S-1 en w×h. `d`: {a, motor, vista («lista» o «archivadas»), filas [fila()], sel (índice en filas), aviso,
    ahora, cargando}. → Term con sus zonas (pk:fila:<i>, pk:arch:<i>, pk:abrir, pk:nueva, pk:archivadas, pk:volver,
    pk:recuperar, pk:lista) y `monito` (x, y, tam: dónde va el monito, para la entrada del hub). `crudo`: sin el color
    P-3 (el hub la mezcla con Inicio en su entrada y la afina una sola vez)."""
    import hub_paleta as P
    import hub_bloque as B
    import hub_h1 as H
    import hub_directo as D
    import hub_monitos as MON
    C = P.C
    W, corto = B.W, B.corto
    T = P.Term(w, h)
    T.fill(0, 0, w, h, B.BG)
    T.monito = None
    if w < P.MIN_W or h < P.MIN_H:
        T.center(0, w, h // 2, "Agranda la ventana", C["tx2"])
        return T if crudo else P.afinar(T)
    L = B.Lienzo(T, {"sobre": sobre, "apretado": apretado})
    a = d["a"]
    filas = d["filas"]
    sel = d.get("sel") or 0
    arch_vista = d.get("vista") == "archivadas"
    ses = [i for i, f in enumerate(filas) if f["kind"] == "WS"]
    i_nueva = next((i for i, f in enumerate(filas) if f["kind"] == "NEW"), None)
    i_arch = next((i for i, f in enumerate(filas) if f["kind"] == ARCH), None)
    i_volver = next((i for i, f in enumerate(filas) if f["kind"] == VOLVER), None)
    n_arch = d.get("n_arch")
    if n_arch is None and i_arch is not None:
        n_arch = int("".join(c for c in filas[i_arch]["nombre"] if c.isdigit()) or 0)
    ws_sel = sel if sel in ses else d.get("ultimo_ws", ses[0] if ses else None)
    cw = min(110, w - 4)
    x0 = (w - cw) // 2
    chico = h < CHICO_H
    tam = 8 if chico else 16
    mw, mh = MON.medidas(tam)
    alto_cab = mh + 2
    fila_h = 1 if arch_vista else 2
    # cuántas sesiones caben: lo de arriba, el área, los botones (3), las teclas y el aviso
    libre = h - 2 - alto_cab - 1 - 2 - 1 - 3 - 1 - 2
    cabe = max(1, min(len(ses) or 1, libre // fila_h, 4 if (chico and fila_h == 2) else 9))
    i0, i1 = _ventana(len(ses), ses.index(ws_sel) if ws_sel in ses else 0, cabe)
    n_vis = max(1, i1 - i0)
    ha = 2 + fila_h * n_vis
    alto = alto_cab + 1 + ha + 1 + 3 + 2
    y0 = max(1, (h - alto) // 2)
    # el agente: su monito grande y con qué se abre
    s_m = {"t": d["t"], "anim": d.get("anim") or {}, "agentes": [dict(a, st="libre")]} if d.get("t") is not None \
        else None
    MON.dibujar(T, a, x0 + 1, y0 + 1, tam, s=s_m, st="libre")
    T.monito = (x0 + 1, y0 + 1, tam)
    tx = x0 + mw + 4
    T.put(tx, y0 + 2 - (1 if chico else 0), corto(a["n"], cw - mw - 6), a["c"], True)
    H.segs(L, tx, y0 + 3 - (1 if chico else 0), [("Se abre en ", C["tx2"], False), (d.get("motor") or "", C["tx"], True),
                                                (", su programa oficial.", C["tx2"], False)], B.BG,
           limite=x0 + cw)
    pista = ("Lo que quitaste del menú. Nada se borró: recupera la que quieras." if arch_vista else
             ("Elige una sesión o empieza una nueva." if chico else
              "Elige con qué sesión seguir o empieza una nueva. Cada una recuerda lo suyo."))
    T.put(tx, y0 + 4 - (1 if chico else 0), corto(pista, x0 + cw - tx), C["tx3"])
    if not arch_vista:                                # en las archivadas, «← Tus sesiones» va en su área y abajo
        lab = " ← Volver al hub  Esc "
        xv = x0 + cw - W(lab) - 2
        hov = L.reg(xv, y0, W(lab) + 2, 1, "pk:volver")
        B.ficha(T, xv, y0, lab, B.P4 if L.apr("pk:volver") else (B.P3 if hov else B.P2), B.BG,
                C["tx"] if hov else C["tx2"])
    # sus sesiones
    ya = y0 + alto_cab + 1
    if arch_vista:
        tit = [("Archivadas", C["tx2"], True), (" · %d" % len(ses), C["tx3"], False)]
        der = [("← Tus sesiones", C["tx3"], False, "pk:lista")]
    else:
        tit = [("Sesiones", C["tx2"], True), (" · %d" % len(ses), C["tx3"], False)]
        der = [("Archivadas · %d" % n_arch, C["tx3"], False, "pk:archivadas")] if i_arch is not None else None
    H.area(L, x0, ya, cw, ha, B.P1, tit, der)
    yy = ya + 1
    if not ses:
        T.put(x0 + 4, yy, "Leyendo sus sesiones…" if d.get("cargando") else
              ("Todavía no hay ninguna." if arch_vista else "Todavía no tiene sesiones: empieza una nueva."),
              C["tx3"], False, B.P1)
    if i0 > 0:
        T.put(x0 + cw - 2, ya + 1, "▲", C["tx2"], False, B.P1)
    if i1 < len(ses):
        T.put(x0 + cw - 2, ya + ha - 2, "▼", C["tx2"], False, B.P1)
    x, wf = x0 + 1, cw - 2
    for k in ses[i0:i1]:
        f = filas[k]
        rid = "pk:fila:%d" % k
        on = k == sel
        encima = L.reg(x, yy, wf, fila_h, rid)
        hov = encima and not on
        if on or hov:
            B.bloque(T, x, yy, wf, fila_h, B.P3 if on else B.P2, B.P1)
        if on:
            H.marca_sel(T, x0, yy, fila_h, a, B.P1)
        nombre = D.limpio(f["nombre"]) or "Sin nombre"
        if arch_vista:
            T.put(x + 3, yy, corto(nombre, wf - 30), C["tx"] if (on or hov) else C["tx2"], on)
            T.right(x + wf - 3, yy, corto(f["sub"], 26), C["tx3"])
            yy += 1
            continue
        num = ses.index(k) + 1
        if num <= 9:
            T.put(x + 2, yy, " %d " % num, C["tx"] if (on or hov) else C["tx2"], True,
                  B.P4 if (on or hov) else B.P3)
        ico, ic, pal, pc, pb = _ses_color(f, a)
        T.put(x + 6, yy, ico, ic, True)
        cuando = D.hace(f["cuando"], d.get("ahora"))
        cuando = cuando[5:] if cuando.startswith("hace ") else cuando
        cols = not chico and wf >= 90
        der_w = 40 if cols else 24
        T.put(x + 8, yy, corto(nombre, wf - 8 - der_w), C["tx"] if (on or hov) else C["tx2"], on)
        if cols:
            if f["motor"]:
                T.put(x + wf - 40, yy, corto(D.nombre_motor(f["motor"]), 15), C["tx3"])
            T.put(x + wf - 24, yy, corto(pal, 14), pc, pb)
        else:
            T.put(x + wf - 23, yy, corto(pal, 12), pc, pb)
        if cuando:
            T.right(x + wf - 3, yy, cuando, C["tx3"])
        ult = f["ultimo"] or ("" if f["estado"] else "")
        lim = x + wf - 3 - (15 if encima else 0)
        if ult:
            T.put(x + 8, yy + 1, corto(ult, lim - x - 8), C["tx3"])
        if encima and "a" in (d.get("keys") or "a"):      # el mouse encima (también de la elegida)
            H.segs(L, x + wf - 15, yy + 1, [(" a  archivar ", C["tx2"], False, "pk:arch:%d" % k)], B.P2)
        yy += 2
    # los botones grandes (o, con «+ Nueva sesión», su nombre)
    yb = ya + ha + 1
    if d.get("nombre") is not None:
        H.area(L, x0, yb, cw, 3, B.P2, titulo=[("Nombre de la sesión nueva", C["tx2"], True)],
               der=[(" Esc vuelve ", C["tx2"], False, "pk:cancelar")], foco_a=a)
        texto = d["nombre"]
        xx = T.put(x0 + 3, yb + 1, "❯", a["c"], True, B.P2)
        lab = " Crear y abrir ↵ "
        xb = x0 + cw - 3 - W(lab) - 2
        if texto:
            xx = T.put(xx + 1, yb + 1, corto(texto, xb - xx - 3), C["tx"], False, B.P2)
            T.put(xx, yb + 1, "▏", C["tx"], False, B.P2)
        else:
            T.put(xx + 1, yb + 1, corto("Ponle nombre (si no, «General»)", xb - xx - 3), C["tx3"], False, B.P2)
        hc = L.reg(xb, yb + 1, W(lab) + 2, 1, "pk:crear")
        B.ficha(T, xb, yb + 1, lab, a["c"] if not hc else P.mix(a["c"], "#ffffff", 0.18), B.P2, B.LUZTX, True)
        ks = [("Enter", "crea y abre"), ("Esc", "vuelve")]
    elif arch_vista:
        foco_rec = sel in ses
        xb = B.boton(L, {}, x0, yb, "Recuperar y abrir  ↵", "pk:recuperar", B.BG, foco=foco_rec,
                     apagado=not ses, wmin=28, a=a)
        B.boton(L, {}, xb + 1, yb, "← Tus sesiones", "pk:lista", B.BG, foco=sel == i_volver, wmin=20, a=a)
        ks = [("↑↓", "elige"), ("Enter", "recupera y abre"), ("u", "deshace"), ("Esc", "vuelve")]
    else:
        nom = filas[ws_sel]["nombre"] if ws_sel is not None else ""
        lab_ab = "Abrir «%s»  ↵" % corto(D.limpio(nom), max(8, cw // 3 - 12)) if nom else "Abrir  ↵"
        xb = B.boton(L, {}, x0, yb, lab_ab, "pk:abrir", B.BG, foco=sel in ses, apagado=ws_sel is None, wmin=34, a=a)
        if i_nueva is not None:
            xb = B.boton(L, {}, xb + 1, yb, "+ Nueva sesión" + ("  ↵" if sel == i_nueva else ""), "pk:nueva", B.BG,
                         foco=sel == i_nueva, wmin=20, a=a)
        if i_arch is not None and xb + 20 < x0 + cw + 2:
            B.boton(L, {}, xb + 1, yb, "Archivadas · %d" % n_arch + ("  ↵" if sel == i_arch else ""),
                    "pk:archivadas2", B.BG, foco=sel == i_arch, wmin=18, a=a)
        ks = [("↑↓", "elige"), ("Enter", "abre"), ("a", "archiva"), ("u", "deshace"), ("1-9", "directo"),
              ("Esc", "regresa")]
    xk = x0
    for k, labk in ks:
        if xk + W(k) + W(labk) + 4 > x0 + cw:
            break
        xk = T.key(xk, yb + 4, k, labk)
    if d.get("aviso") and yb + 5 < h:
        T.put(x0, yb + 5, corto(d["aviso"], cw), C["tx2"])
    T.flat()
    return T if crudo else P.afinar(T)


# ── la entrada desde el hub (H2-a «La lista vive en el hub») ──────────────────
#: Inicio (o lo que se veía) se apaga mientras el monito viaja a su lugar en S-1 (VIAJE_S, 4 cuadros); luego las filas
#: de S-1 entran de arriba abajo (CASCADA_S). Una sola transición, sin pantallas de carga.
VIAJE_S, CASCADA_S = 0.25, 0.17
ENTRADA_S = VIAJE_S + CASCADA_S


def _copia(dst, src_, y0=0, y1=None):
    """Las celdas de `src_` (filas y0..y1-1) en `dst`, tal cual."""
    y1 = src_.h if y1 is None else min(y1, src_.h)
    for y in range(max(0, y0), y1):
        for x in range(min(dst.w, src_.w)):
            c, d = src_.cl[y * src_.w + x], dst.cl[y * dst.w + x]
            d.ch, d.fg, d.bg, d.b, d.px = c.ch, c.fg, c.bg, c.b, c.px


def _monito_encima(U, a, x, y, tam, s, fondo_tema):
    """El monito en (x, y) sobre `U` ya afinado: se dibuja aparte, se afina solo él y se pega (lo de abajo no se
    vuelve a afinar: cada pasada corre los fondos hacia el azul)."""
    import hub_paleta as P
    import hub_monitos as MON
    V = P.Term(U.w, U.h)
    marca = "#010203"
    V.fill(0, 0, V.w, V.h, marca)
    MON.dibujar(V, a, x, y, tam, s=s, st="libre", signo=False)
    V.flat()
    sin_fondo = {i for i, k in enumerate(V.cl) if k.px and k.bg == marca}
    P.afinar(V, fondo_tema)
    for i, k in enumerate(V.cl):
        if k.px:
            d = U.cl[i]
            d.ch, d.fg, d.b, d.px = k.ch, k.fg, k.b, True
            if i not in sin_fondo:
                d.bg = k.bg


def entrada(Ti, Tf, a, edad, desde=None, fondo_tema=None, s=None):
    """Un cuadro de la entrada a S-1, a `edad` s de apretar «Sesiones». `Ti`: lo que se veía y `Tf`: S-1, los dos
    crudos (sin P-3); `desde`: (x, y, tam) del monito en `Ti` (None: aparece en su lugar). → Term afinado una sola
    vez, con las zonas de S-1 (un clic a media entrada ya es de S-1)."""
    import hub_paleta as P
    import hub_bloque as B
    import hub_monitos as MON
    w, h = Tf.w, Tf.h
    U = P.Term(w, h)
    U.fill(0, 0, w, h, B.BG)
    hasta = getattr(Tf, "monito", None)
    if hasta is None or edad >= ENTRADA_S or Ti is None or (Ti.w, Ti.h) != (w, h):
        _copia(U, Tf)
        P.afinar(U, fondo_tema)
    elif edad < VIAJE_S:
        p = max(0.0, edad / VIAJE_S)
        _copia(U, Ti)
        xf, yf, tam = hasta
        if desde:
            xi, yi, ti = desde
            mw, mh = MON.medidas(ti)
            for j in range(max(0, yi - 3), min(h, yi + mh + 1)):     # su lugar de antes (y su signo), vacío
                fondo_j = U.cl[j * w + max(0, xi - 3)].bg
                for i in range(max(0, xi - 2), min(w, xi + mw + 2)):
                    k = U.cl[j * w + i]
                    k.ch, k.px, k.bg = " ", False, fondo_j
        else:
            xi, yi = xf, yf
        P.afinar(U, fondo_tema)
        apaga = min(1.0, 0.3 + 0.7 * p)                  # lo de antes se apaga (después de afinar: el contraste del
        fondo = P._colores_afinados(None, B.BG, False, fondo_tema)[1]   # texto no lo vuelve a encender)
        for k in U.cl:
            k.fg, k.bg = P.mix(k.fg or P.T_FG, fondo, apaga), P.mix(k.bg or fondo, fondo, apaga)
        e = 1 - (1 - p) ** 2
        _monito_encima(U, a, int(round(xi + (xf - xi) * e)), int(round(yi + (yf - yi) * e)), tam, s, fondo_tema)
    else:
        q = min(1.0, (edad - VIAJE_S) / CASCADA_S)
        ya = hasta[1] + MON.medidas(hasta[2])[1] + 2                 # la cabeza de S-1 (el monito y su texto)
        _copia(U, Tf, 0, ya + int(round((h - ya) * q)))
        P.afinar(U, fondo_tema)
    U.zonas = list(Tf.zonas)
    U.monito = hasta
    return U


# ── la pantalla viva (en /dev/tty, con su mouse) ──────────────────────────────
def _tty():
    """(fd para leer, archivo para escribir) de la terminal; None sin terminal. En Windows, (None, CONOUT$): la salida
    va a la consola de verdad aunque quien lo lanzó capture stdout (el motor captura el --pick del menú), y las teclas
    (y el mouse) se leen de la consola de entrada con el lector del hub (hub_paleta._Teclado: consola_windows; si la
    consola no se deja, msvcrt)."""
    if sys.platform == "win32":
        try:
            return None, open("CONOUT$", "w", encoding="utf-8", errors="replace")
        except OSError:
            return None
    try:
        fd = os.open("/dev/tty", os.O_RDWR | getattr(os, "O_NOCTTY", 0))
    except OSError:
        return None
    try:
        out = os.fdopen(os.dup(fd), "w", encoding="utf-8", errors="replace")
    except OSError:
        os.close(fd)
        return None
    return fd, out


def _raton_posible(env=None):
    env = os.environ if env is None else env
    if str(env.get("WORKSPACE_MOUSE") or "").strip() == "0":
        return False
    return str(env.get("TERM") or "").strip().lower() not in ("dumb", "linux")


class Menu:
    """El estado de S-1 y lo que hace cada tecla o clic (sin terminal: las pruebas lo manejan). `tecla()` y
    `raton()` devuelven None (sigue) o lo que regresa el picker."""

    def __init__(self, items, keys="", selected=0, titulo=None, brain=None, resumen=None):
        self.items = list(items)
        self.keys = keys or ""
        self.vista = "archivadas" if (titulo or "").strip().upper().startswith("ARCHIV") or \
            any(tuple(it[2])[0] == VOLVER for it in self.items) else "lista"
        self.filas = [fila(it, brain, resumen) for it in self.items]
        self.sel = max(0, min(int(selected or 0), len(self.items) - 1)) if self.items else 0
        ses = [i for i, f in enumerate(self.filas) if f["kind"] == "WS"]
        self.ultimo_ws = self.sel if self.sel in ses else (ses[0] if ses else None)
        self.sobre, self.apretado = "", None
        self.nombre = None                      # «+ Nueva sesión»: su nombre mientras se escribe (None: la lista)

    def datos(self, a, motor, aviso="", ahora=None, t=None):
        """`t`: el reloj de la animación del monito (time.monotonic); sin él, quieto."""
        return {"a": a, "motor": motor, "vista": self.vista, "filas": self.filas, "sel": self.sel,
                "ultimo_ws": self.ultimo_ws, "aviso": aviso, "ahora": ahora, "keys": self.keys, "t": t,
                "nombre": self.nombre}

    def _elige(self, i):
        self.sel = i
        if 0 <= i < len(self.filas) and self.filas[i]["kind"] == "WS":
            self.ultimo_ws = i

    def _nueva(self):
        """«+ Nueva sesión»: primero su nombre, aquí mismo (antes lo pedía el menú de abajo, del estilo de antes)."""
        self.nombre = ""
        return None

    def _es_nueva(self, i):
        return 0 <= i < len(self.filas) and self.filas[i]["kind"] == "NEW"

    def tecla(self, k):
        n = len(self.items)
        if self.nombre is not None:             # escribiendo el nombre de la sesión nueva
            if k == "enter":
                return ("NUEVO", " ".join(self.nombre.split()) or "General")
            if k in ("esc", "ctrl-c"):
                self.nombre = None
            elif k == "borrar":
                self.nombre = self.nombre[:-1]
            elif k == "ctrl-u":
                self.nombre = ""
            elif isinstance(k, str) and len(k) == 1 and k.isprintable() and len(self.nombre) < 60:
                self.nombre += k
            return None
        if k in ("enter",):
            return self._nueva() if self._es_nueva(self.sel) else self.sel
        if k in ("esc", "ctrl-c"):
            return BACK
        if k in ("arriba", "abajo"):
            self._elige((self.sel + (1 if k == "abajo" else -1)) % n)
            return None
        if isinstance(k, str) and len(k) == 1 and k in "123456789" and int(k) <= n:
            return self._nueva() if self._es_nueva(int(k) - 1) else int(k) - 1
        if isinstance(k, str) and len(k) == 1 and self.keys and k.lower() in self.keys:
            return (k.lower(), self.sel)
        return None

    def _indice(self, kind):
        return next((i for i, f in enumerate(self.filas) if f["kind"] == kind), None)

    def clic(self, zid):
        p, _s, resto = zid.partition(":")
        if p != "pk":
            return None
        if resto == "volver":
            return BACK
        if resto.startswith("fila:"):
            i = int(resto[5:])
            self._elige(i)
            return i
        if resto.startswith("arch:"):
            i = int(resto[5:])
            self._elige(i)
            return ("a", i) if "a" in self.keys else None
        if resto == "abrir":
            return self.ultimo_ws
        if resto == "nueva":
            i = self._indice("NEW")
            if i is not None:
                self._elige(i)
                return self._nueva()
            return None
        if resto == "crear" and self.nombre is not None:
            return ("NUEVO", " ".join(self.nombre.split()) or "General")
        if resto == "cancelar":
            self.nombre = None
            return None
        if resto in ("archivadas", "archivadas2"):
            return self._indice(ARCH)
        if resto == "recuperar":
            return self.sel if self.filas and self.filas[self.sel]["kind"] == "WS" else self.ultimo_ws
        if resto == "lista":
            return BACK                                # en las archivadas, Esc vuelve a la lista
        return None

    def rueda(self, arriba):
        ses = [i for i, f in enumerate(self.filas) if f["kind"] == "WS"]
        if ses:
            k = ses.index(self.sel) if self.sel in ses else (ses.index(self.ultimo_ws) if self.ultimo_ws in ses
                                                              else 0)
            self._elige(ses[max(0, min(len(ses) - 1, k + (-1 if arriba else 1)))])


def picker_para(brain, agent):
    """Un picker con la firma de agent_ui.live_picker que dibuja S-1 para `agent` (de `brain`)."""
    def picker(items, script, keys="", notice="", selected=0, title=None, hints=None):
        try:
            return correr(items, brain, agent, keys=keys, notice=notice, selected=selected, title=title)
        except Exception:                            # nunca un callejón: el menú sencillo del dashboard (None)
            return None
    return picker


def correr(items, brain, agent, keys="", notice="", selected=0, title=None, tty=None, reloj=time.monotonic):
    """S-1 en la terminal hasta que eliges. → índice, BACK, (tecla, índice) o None sin terminal."""
    if not items:
        return None
    t = tty or _tty()
    if t is None:
        return None
    fd, out = t
    import hub_paleta as P
    try:
        ctx = json.loads(os.environ.get("WORKSPACE_AGENT_UI") or "{}")
    except ValueError:
        ctx = {}
    a = agente(agent, ctx.get("name") or "")
    motor = motor_texto(a=a)
    m = Menu(items, keys, selected, title, resumen=lambda *_: None)
    resueltas = queue.SimpleQueue()
    pendientes = _completar_precarga(m, _precarga(agent))
    actualizar = bool(brain and pendientes)

    def leer_resumenes():
        resueltas.put([(i, fila(m.items[i], brain)) for i in pendientes])
    if fd is None:                                   # Windows: el lector del hub (consola_windows o msvcrt)
        tec = P._Teclado()
        raton = _raton_posible() and tec.raton_ok
        if raton:
            tec.raton(True)
    else:
        tec = P._Teclado.__new__(P._Teclado)
        tec.win, tec.buf, tec.fd = False, b"", fd
        import termios
        tec.viejo = termios.tcgetattr(fd)
        P._crudo(fd)
        raton = _raton_posible()
    pintor = P.Pintor(out)
    colores = P._colores()
    out.write("\x1b[?1049h\x1b[?25l" + (P.RATON_ON if raton else ""))
    out.flush()
    aviso = notice or ""
    apertura = ""
    lector = threading.Thread(target=leer_resumenes, daemon=True) if actualizar else None

    def _final(r):
        """Lo que regresa S-1; si abre una sesión (o crea una), lo anota y lo dice al salir («Abriendo…»)."""
        nonlocal apertura
        nombre = None
        if isinstance(r, tuple) and len(r) == 2 and r[0] == "NUEVO":
            nombre = r[1]
        elif isinstance(r, int) and 0 <= r < len(m.filas) and m.filas[r]["kind"] == "WS":
            nombre = m.filas[r]["nombre"]
        if nombre is not None:
            apertura = "Abriendo en %s…" % motor if motor else "Abriendo su programa oficial…"
            m.nombre = None
            vista = pantalla(w, h, m.datos(a, motor, apertura, time.time(), reloj()), m.sobre, m.apretado)
            pintor.pintar(vista, colores)
        return r

    try:
        while True:
            try:
                w, h = os.get_terminal_size(fd if fd is not None else out.fileno())
            except (OSError, ValueError):
                w, h = 100, 30
            if actualizar:
                try:
                    for i, datos in resueltas.get_nowait():
                        m.filas[i] = datos
                    actualizar = False
                except queue.Empty:
                    pass
            t_mon = reloj()
            estado = aviso or ("Leyendo el estado de las sesiones…" if actualizar else "")
            T = pantalla(w, h, m.datos(a, motor, estado, time.time(), t_mon), m.sobre, m.apretado)
            pintor.pintar(T, colores)
            if lector is not None:
                lector.start()
                lector = None
            import hub_monitos as MON
            esp = MON.espera({"t": t_mon, "anim": {}, "agentes": [dict(a, st="libre")]})
            k = tec.leer(min(0.2, esp) if esp else 0.2)
            if k is None or k == "":
                continue
            if isinstance(k, P.Raton):
                zid = next((z[4] for z in reversed(T.zonas) if z[0] <= k.x < z[0] + z[2] and z[1] <= k.y < z[1] + z[3]),
                           "")
                if k.tipo == "mueve":
                    m.sobre = zid
                elif k.tipo in ("rueda_arriba", "rueda_abajo"):
                    m.rueda(k.tipo == "rueda_arriba")
                elif k.tipo == "baja" and k.boton == 0:
                    m.apretado, m.sobre = zid, zid
                elif k.tipo == "sube" and k.boton == 0:
                    ap, m.apretado = m.apretado, None
                    if ap and ap == zid:
                        r = m.clic(zid)
                        if r is not None:
                            return _final(r)
                continue
            if isinstance(k, P.Pegado):
                if m.nombre is not None:
                    m.nombre = (m.nombre + " ".join(str(k).split()))[:60]
                continue
            r = m.tecla(k)
            if r is not None:
                return _final(r)
            aviso = ""
    finally:
        try:
            out.write((P.RATON_OFF if raton else "") + "\x1b[0m\x1b[?25h\x1b[?1049l")
            out.flush()
        except (OSError, ValueError):
            pass
        if apertura:
            try:
                out.write(apertura + "\r\n")
                out.flush()
                os.environ["WORKSPACE_HUB_S1_AVISO_VISIBLE"] = "1"
            except (OSError, ValueError):
                pass
        try:
            tec.vaciar()
        except Exception:
            pass
        if fd is None:
            try:
                tec.soltar()                         # Windows: la consola como estaba
            except Exception:
                pass
        else:
            try:
                import termios
                termios.tcsetattr(fd, termios.TCSADRAIN, tec.viejo)
            except Exception:
                pass
        if tty is None:
            try:
                out.close()
            finally:
                try:
                    if fd is not None:
                        os.close(fd)
                except OSError:
                    pass
