"""WORKSPACE · docs_mapa — EL MAPA DE LA MEMORIA (sección Documentación: su
primer renglón o la tecla m; desde la 0.5.1 ya no está en la portada del hub).

El árbol REAL del cerebro del agente elegido, como la vista del cerebro de
«Agregar agente»: el agente → sus carpetas → sus archivos, y abajo lo que vive
fuera del cerebro (esta PC y la conversación de su motor). Cada paso —todo el
recorrido, abrir, trabajar, cerrar, retomar, personas, motores, aprender—
ilumina los archivos que toca:

                 ╭──────────╮
             ┌───┤ STATE/   ├─┬ ④ ⑩ MEMORY.md · lo lee al arrancar · suben datos…
  ╭───────╮  │   ╰──────────╯ ├ ⑤ users/ana.md · cómo tratarte
  │ Lumen ├──┤                └ ⑥ ⑦ sessions/ana/ventas.md · Workspace la resume…
  ╰───────╯  │   ╭──────────╮
             └───┤ skills/  ├── INDEX-LITE.md · el catálogo de skills

con su orden (①②…), su color (azul = se lee, verde = se escribe, rosa = de
cada persona, gris = compartido) y qué le pasa a cada uno; lo real del agente
(tu usuario, tu pestaña, la sesión de su motor) va en rosa. ← → (o 0-7, los
números de las pestañas) cambia de paso; ↑↓ desplaza si no cabe; Tab, de
agente (en docs_tui); Enter abre lo que lo demuestra. Con poco alto, las cajas
van juntas; en terminales angostas, el mismo árbol en texto (├─).

El contenido vive en docs_hub (MAPA_ARBOL, MAPA_FUERA, MAPA_PASOS,
MOTOR_RUTAS, MAPA_MOTORES, mapa_valores); aquí solo se pinta. Esta pantalla
jamás escribe nada: mapa_valores solo lee.
"""
import re

import docs_hub as D
import hublayout as HL
import section_box as SB
import section_frame as SF

_t = SF.t
#: El ancho de contenido que pide la caja del mapa (manda la terminal si es menor).
BOX_W = 140
#: Desde este ancho, el árbol va con cajas; más angosto, en texto.
_MIN_CAJAS = 96
_LLAVE = re.compile(r"\{(\w+)\}")


# ── estado ───────────────────────────────────────────────────────────────────
def initial():
    return {"paso": 0}


def items(M):
    return D.MAPA_PASOS


def actual(M):
    return D.MAPA_PASOS[M["paso"] % len(D.MAPA_PASOS)]


def _tx(p):
    return D.mapa_texto(p)


def _lienzo(K, w, h):
    import agents_tui
    return agents_tui._mk(K, w, h)


def valores(M):
    """Lo real del agente elegido, una vez por agente e idioma."""
    ctx = M.get("ctx") or {}
    clave = (ctx.get("brain"), ctx.get("engine"), D.lang())
    if M.get("_val", (None,))[0] != clave:
        M["_val"] = (clave, D.mapa_valores(ctx, D.lang()))
    return M["_val"][1]


def _motor(M):
    """El motor del agente elegido; sin agente, el ejemplo es Claude Code."""
    return (M.get("ctx") or {}).get("engine") or "claude-code"


def _pasa(filtro, eng):
    if not filtro:
        return True
    if filtro.startswith("!"):
        return eng != filtro[1:]
    return eng == filtro


def _tinta(K, accion):
    return {"lee": K["C"], "escribe": K["OK"], "persona": K["B2"],
            "compartido": K["GREY"]}.get(accion, K["WH"])


def _titulo(p):
    if p["id"] == "todo":
        return "%s %s" % (p["num"], _tx(p)["titulo"].upper())
    return "%s %s · %s" % (_t("docs.mapa.paso", "paso", "step").upper(), p["num"],
                           _tx(p)["titulo"].upper())


# ── rutas que no caben ───────────────────────────────────────────────────────
def corta_ruta(s, w):
    """La ruta en `w` columnas sin perder el final, que es lo que dice qué
    archivo es: primero saca carpetas del medio («sessions/…/maleta/x.md»); si
    no alcanza, «…» cerca del principio. Una frase se corta al final."""
    s = str(s)
    if HL.vis(s) <= w:
        return s
    if w <= 1:
        return "…"[:max(0, w)]
    if "/" not in s:
        return HL.clip(s, w)
    final = "/" if s.endswith("/") else ""
    partes = s.rstrip("/").split("/")
    if len(partes) > 2:
        for atras in range(len(partes) - 2, 0, -1):
            cand = "/".join(partes[:1] + ["…"] + partes[-atras:]) + final
            if HL.vis(cand) <= w:
                return cand
    cabeza = max(1, (w - 1) // 3)
    return s[:cabeza] + "…" + s[len(s) - (w - 1 - cabeza):]


def _forma_minima(s):
    """Lo más corta que puede quedar una ruta sin dejar de decir qué archivo
    es: la primera carpeta, «…» y el archivo («sessions/…/ventas.md»)."""
    if "/" not in s:
        return s
    final = "/" if s.endswith("/") else ""
    partes = s.rstrip("/").split("/")
    if len(partes) <= 2:
        return s
    return "/".join([partes[0], "…", partes[-1]]) + final


def reparto(ruta, notas, ancho):
    """(columnas para la ruta, nota) en `ancho`. En orden: la ruta entera con
    todas las notas, con la primera, la ruta acortada con todas, con la
    primera; si nada cabe, solo la ruta. Una nota va entera o no va (nunca
    «tu ag…»): la ruta es lo que se busca en el disco."""
    opciones = []
    for n in (" · ".join(notas), notas[0] if notas else ""):
        if n and n not in opciones:
            opciones.append(n)
    largo, minimo = HL.vis(ruta), HL.vis(_forma_minima(ruta))
    for nota in opciones:
        if largo + 3 + HL.vis(nota) <= ancho:
            return largo, nota
    for nota in opciones:
        if ancho - 3 - HL.vis(nota) >= minimo:
            return ancho - 3 - HL.vis(nota), nota
    return min(largo, ancho), ""


def _rico(c, K, x, y, plantilla, val, col, limite, vivo=True):
    """Escribe la plantilla con lo real en rosa (en un renglón apagado, también
    apagado: el rosa jalaría la vista a lo que no se usa); si no cabe entera,
    la ruta acortada en un solo color (se pierde el realce, nunca el sentido).
    → columnas usadas."""
    lleno = D.mapa_rellenar(plantilla, val)
    if HL.vis(lleno) > limite:
        corto = corta_ruta(lleno, limite)
        c.put(x, y, corto, col, limite)
        return HL.vis(corto)
    usado = 0
    for k, trozo in enumerate(_LLAVE.split(str(plantilla))):
        if not trozo:
            continue
        txt = str(val.get(trozo, "{%s}" % trozo)) if k % 2 else trozo
        tinta = (K["B2"] + K["BO"]) if (k % 2 and vivo) else col
        sangria = len(txt) - len(txt.lstrip(" "))      # el lienzo quita los espacios de las puntas
        if txt.strip():
            c.put(x + usado + sangria, y, txt.strip(), tinta, max(0, limite - usado - sangria))
        usado += HL.vis(txt)
    return usado


# ── qué toca cada paso ───────────────────────────────────────────────────────
def marcas(M):
    """{hoja: [(orden, acción, nota)]} del paso elegido, con lo real puesto y
    solo lo que vale para el motor del agente."""
    eng = _motor(M)
    val = valores(M)
    out = {}
    for e in _tx(actual(M))["ruta"]:
        hoja, orden, accion, nota = e[:4]
        if _pasa(e[4] if len(e) > 4 else "", eng):
            out.setdefault(hoja, []).append((orden, accion, D.mapa_rellenar(nota, val)))
    return out


_NUMEROS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"


def _orden(marca):
    return _NUMEROS.index(marca) if marca in _NUMEROS else len(_NUMEROS)


def _grupos(M):
    """[(carpeta, [hojas visibles], fuera)] en el orden del árbol: si la carpeta
    tiene hojas tocadas en este paso, esas; si no, su primera hoja (en gris)."""
    eng = _motor(M)
    mk = marcas(M)
    en_ruta = list(mk)
    out = []
    for fuera, grupo in ((False, D.MAPA_ARBOL), (True, D.MAPA_FUERA)):
        for _cid, carpeta, hojas in grupo:
            vivas = [h for h in hojas if _pasa(h[4] if len(h) > 4 else "", eng)]
            # las tocadas, en el orden del recorrido (①②…; empate: como las
            # cuenta el paso; lo compartido al final)
            tocadas = sorted((h for h in vivas if h[0] in mk),
                             key=lambda h: (_orden(mk[h[0]][0][0]), en_ruta.index(h[0])))
            out.append((carpeta, tocadas or vivas[:1], fuera))
    return out


def _hoja_partes(K, M, hoja):
    """(insignias [(texto, tinta)], plantilla, tinta de la ruta, [notas],
    tinta de la nota) de una hoja en el paso elegido."""
    mk = marcas(M).get(hoja[0])
    lg = D.lang()
    if not mk:
        resumen = hoja[3] if lg == "en" else hoja[2]
        return [], D.mapa_plantilla(hoja), K["DK"], [resumen], K["DK"]
    insignias = [(o, _tinta(K, a) + K["BO"]) for o, a, _n in mk]
    notas = [n for _o, _a, n in mk if n]
    return insignias, D.mapa_plantilla(hoja), _tinta(K, mk[0][1]) + K["BO"], notas, K["WH"]


def _tinta_carpeta(K, M, hojas):
    mk = marcas(M)
    for h in hojas:
        if h[0] in mk:
            return _tinta(K, mk[h[0]][0][1])
    return K["DK"]


# ── el árbol con cajas (como la vista del cerebro de «Agregar agente») ──────
def arbol(K, M, iw, aire=1):
    """(líneas, fila de arriba) del árbol con cajas; None si no cabe. `aire`
    = filas en blanco entre carpetas (0 con poco alto: las cajas juntas)."""
    if iw < _MIN_CAJAS:
        return None
    val = valores(M)
    ctx = M.get("ctx") or {}
    raiz = ctx.get("display") or ctx.get("name") or _t("docs.mapa.tu_agente", "tu agente", "your agent")
    grupos = _grupos(M)
    rw = min(18, max(10, HL.vis(raiz) + 4))
    etiquetas = [corta_ruta(D.mapa_rellenar(carpeta, val), 20) for carpeta, _h, _f in grupos]
    fw = min(24, max(HL.vis(e) for e in etiquetas) + 4)
    ox = 1
    tx = ox + rw + 2                      # el tronco
    fx = tx + 3                           # las cajas de carpeta
    lx = fx + fw + 2                      # el riel de las hojas
    ancho_hoja = iw - lx - 2
    if ancho_hoja < 40:
        return None
    # filas: una banda por carpeta (3 o más) y una fila para «fuera del cerebro»
    ys, y = [], 0
    divisor = None
    for k, (_carpeta, hojas, fuera) in enumerate(grupos):
        if fuera and divisor is None:
            divisor = y
            y += 1 + aire
        ys.append(y)
        y += max(3, len(hojas)) + aire
    alto = y - aire
    c = _lienzo(K, iw, alto)
    mids = [yy + 1 for yy in ys]
    dentro = [m for m, g in zip(mids, grupos) if not g[2]]
    # la raíz, centrada en el tronco del cerebro
    rm = (dentro[0] + dentro[-1]) // 2
    c.put(ox, rm - 1, "╭" + "─" * (rw - 2) + "╮", K["C"])
    c.put(ox, rm, "│", K["C"])
    c.put(ox + rw - 1, rm, "│", K["C"])
    c.put(ox + 2, rm, raiz, K["C"] + K["BO"], rw - 4)
    c.put(ox, rm + 1, "╰" + "─" * (rw - 2) + "╯", K["C"])
    c.put(ox + rw - 1, rm, "├", K["C"])
    c.put(ox + rw, rm, "─", K["C"])
    c.put(ox + rw + 1, rm, "─", K["C"])
    # el tronco: continuo en el cerebro, punteado hacia lo de fuera
    for yy in range(dentro[0], dentro[-1] + 1):
        c.put(tx, yy, "│", K["GREY"])
    for yy in range(dentro[-1] + 1, mids[-1] + 1):
        c.put(tx, yy, "┆", K["DK"])
    c.put(tx, rm, "┤" if rm not in mids else "┼", K["GREY"])
    if divisor is not None:
        txt = _t("docs.mapa.fuera", "FUERA DEL CEREBRO · no viaja", "OUTSIDE THE BRAIN · stays here")
        c.put(fx, divisor, txt, K["DIM"] + K["BO"], iw - fx)
    for k, ((carpeta, hojas, fuera), etq, y0) in enumerate(zip(grupos, etiquetas, ys)):
        tinta = _tinta_carpeta(K, M, hojas)
        mid = y0 + 1
        # rama del tronco a la caja
        primero, ultimo = k == 0, k == len(grupos) - 1
        glifo = "┌" if primero else ("└" if ultimo else "├")
        c.put(tx, mid, glifo, tinta if tinta != K["DK"] else K["GREY"])
        c.put(tx + 1, mid, "─", tinta)
        c.put(tx + 2, mid, "─", tinta)
        # la caja de la carpeta
        c.put(fx, y0, "╭" + "─" * (fw - 2) + "╮", tinta)
        c.put(fx, mid, "┤", tinta)
        c.put(fx + fw - 1, mid, "├", tinta)
        c.put(fx, y0 + 2, "╰" + "─" * (fw - 2) + "╯", tinta)
        c.put(fx + 2, mid, etq, (K["WH"] + K["BO"]) if tinta != K["DK"] else K["GREY"], fw - 4)
        # las hojas, unidas por un riel que sale del borde de la caja
        n = len(hojas)
        top = y0 if n >= 3 else y0 + (3 - n) // 2
        c.put(fx + fw, mid, "─", tinta)
        c.put(fx + fw + 1, mid, "─", tinta)
        for j, hoja in enumerate(hojas):
            yy = top + j
            insignias, plantilla, tr, notas, tn = _hoja_partes(K, M, hoja)
            if n == 1:
                g = "─"
            elif j == 0:
                g = "┬" if yy == mid else "┌"
            elif j == n - 1:
                g = "┴" if yy == mid else "└"
            else:
                g = "┼" if yy == mid else "├"
            c.put(lx, yy, g, tr if insignias else K["DK"])
            x = lx + 2
            for o, ti in insignias:
                c.put(x, yy, o, ti)
                x += HL.vis(o) + 1
            resto = lx + 2 + ancho_hoja - x
            para_ruta, nota = reparto(D.mapa_rellenar(plantilla, val), notas, resto)
            x += _rico(c, K, x, yy, plantilla, val, tr, para_ruta, vivo=bool(insignias))
            if nota:
                c.put(x + 1, yy, "· " + nota, tn, lx + 2 + ancho_hoja - x - 1)
    return [ln.rstrip() for ln in c.lines()], 0


# ── el mismo árbol en texto (terminales angostas) ───────────────────────────
def arbol_texto(K, M, iw):
    val = valores(M)
    ctx = M.get("ctx") or {}
    raiz = ctx.get("display") or ctx.get("name") or _t("docs.mapa.tu_agente", "tu agente", "your agent")
    out = ["%s%s%s" % (K["C"] + K["BO"], raiz, K["R"])]
    grupos = _grupos(M)
    for k, (carpeta, hojas, fuera) in enumerate(grupos):
        if fuera and (k == 0 or not grupos[k - 1][2]):
            out.append("%s%s%s" % (K["DIM"] + K["BO"], _t("docs.mapa.fuera", "FUERA DEL CEREBRO · no viaja",
                                                         "OUTSIDE THE BRAIN · stays here"), K["R"]))
        tinta = _tinta_carpeta(K, M, hojas)
        ultimo = k == len(grupos) - 1 or (not fuera and grupos[k + 1][2])
        rama, sigue = ("└─ ", "   ") if ultimo else ("├─ ", "│  ")
        etq = corta_ruta(D.mapa_rellenar(carpeta, val), max(8, iw - 4))
        out.append(HL.clip("%s%s%s%s%s%s" % (K["GREY"], rama, K["R"],
                                             (K["WH"] + K["BO"]) if tinta != K["DK"] else K["GREY"],
                                             etq, K["R"]), iw))
        for j, hoja in enumerate(hojas):
            insignias, plantilla, tr, notas, tn = _hoja_partes(K, M, hoja)
            nota = " · ".join(notas)
            sub = "└─ " if j == len(hojas) - 1 else "├─ "
            ins = "".join("%s%s%s " % (ti, o, K["R"]) for o, ti in insignias)
            ruta = corta_ruta(D.mapa_rellenar(plantilla, val), max(8, iw - 8 - 3 * len(insignias)))
            out.append(HL.clip("%s%s%s%s%s%s%s" % (K["GREY"], sigue + sub, K["R"], ins, tr, ruta, K["R"]), iw))
            if nota:
                pre = sigue + ("   " if j == len(hojas) - 1 else "│  ")
                for ln in SB._wrap(nota, max(8, iw - len(pre) - 2)):
                    out.append(HL.clip("%s%s%s%s%s%s" % (K["GREY"], pre, K["R"], tn, ln, K["R"]), iw))
    return out, 0


# ── lo de alrededor ─────────────────────────────────────────────────────────
def contexto(K, M, iw):
    """De qué agente, motor, usuario y pestaña son las rutas (o que es un
    ejemplo, si no hay agente)."""
    val = valores(M)
    ctx = M.get("ctx") or {}
    if not ctx.get("brain"):
        txt = _t("docs.mapa.ejemplo", "sin agentes todavía: el recorrido con nombres de ejemplo",
                 "no agents yet: the path with example names")
        return [HL.clip("%s%s%s" % (K["DIM"], txt, K["R"]), iw)]
    datos = [(_t("docs.agent", "agente", "agent"), ctx.get("display") or ctx.get("name") or ""),
             (_t("docs.mapa.motor", "motor", "engine"), val["motor"]),
             (_t("docs.mapa.usuario", "usuario", "user"), val["usuario"]),
             (_t("docs.mapa.pestana", "pestaña", "tab"), val["pestana"]),
             (_t("docs.mapa.cerebro", "cerebro", "brain"), val["cerebro"])]
    out, ln = [], ""
    for k, v in datos:
        if not v:
            continue
        trozo = "%s%s%s %s%s%s" % (K["DIM"], k, K["R"], K["B2"] + K["BO"], v, K["R"])
        if ln and HL.vis(ln) + 3 + HL.vis(trozo) > iw:
            out.append(HL.clip(ln, iw))
            ln = trozo
        else:
            ln = (ln + "   " + trozo) if ln else trozo
    return out + [HL.clip(ln, iw)]


def pasos(K, M, iw):
    """Las pestañas de los pasos, como las vistas del cerebro: la elegida
    con ❯ y en el acento; si no caben con nombre, solo los números."""
    sel = M["paso"] % len(D.MAPA_PASOS)
    linea = ""
    for con_nombre in (True, False):
        trozos = []
        for k, paso in enumerate(D.MAPA_PASOS):
            nombre = "%s %s" % (paso["num"], _tx(paso)["corto"]) if (con_nombre or k == sel) else paso["num"]
            if k == sel:
                trozos.append("%s%s [ %s ]%s" % (K["C"] + K["BO"], K["PTR"], nombre, K["R"]))
            else:
                trozos.append("%s[ %s ]%s" % (K["GREY"], nombre, K["R"]))
        linea = " ".join(trozos)
        if HL.vis(linea) <= iw:
            return [linea]
    return [HL.clip(linea, iw)]


def leyenda(K, M, iw):
    partes = [(K["C"], "■", _t("docs.mapa.legend.reads", "se lee", "is read")),
              (K["OK"], "■", _t("docs.mapa.legend.writes", "se escribe", "is written")),
              (K["B2"], "■", _t("docs.mapa.legend.person", "de cada persona · lo real de tu agente",
                                "each person's · your agent's real values")),
              (K["GREY"], "■", _t("docs.mapa.legend.shared", "compartido", "shared")),
              (K["DK"], "■", _t("docs.mapa.legend.idle", "no se usa en este paso", "not used in this step"))]
    out, ln = [], ""
    for col, glifo, txt in partes:
        trozo = "%s%s%s %s%s%s" % (col + K["BO"], glifo, K["R"], K["DIM"], txt, K["R"])
        if ln and HL.vis(ln) + 4 + HL.vis(trozo) > iw:
            out.append(ln)
            ln = trozo
        else:
            ln = (ln + "    " + trozo) if ln else trozo
    return out + [ln]


def _tabla_motores(K, M, iw):
    """Los seis motores: por dónde entra el resumen, dónde guarda su
    conversación y cómo retoma; el de este agente, marcado."""
    val = valores(M)
    eng = (M.get("ctx") or {}).get("engine") or ""
    cols = (_t("docs.mapa.m.engine", "MOTOR", "ENGINE"),
            _t("docs.mapa.m.open", "AL ABRIR RECIBE", "ON OPEN GETS"),
            _t("docs.mapa.m.close", "SU CONVERSACIÓN", "ITS CONVERSATION"),
            _t("docs.mapa.m.resume", "RETOMA", "RESUMES"))
    filas = []
    for m in D.MAPA_MOTORES:
        tx = D.mapa_texto(m)
        r = D.MOTOR_RUTAS.get(m["id"]) or {}
        conv = (r.get("conversacion_dir") or "") + (r.get("conversacion") or "")
        if m["id"] == eng and eng == "claude-code":
            conv = val["conversacion_dir"] + val["conversacion"]
        retoma = val["retoma"] if m["id"] == eng else (r.get("retoma") or "")
        filas.append((m["id"] == eng, [m["nombre"], str(tx["abre"]).partition("|")[0], conv, retoma]))
    # primero se acorta la columna de las conversaciones (corta_ruta deja el
    # archivo); solo si ni así cabe, se quitan columnas desde la derecha
    n = len(cols)
    while True:
        anchos = [max(HL.vis(cols[j]), max(HL.vis(f[j]) for _e, f in filas)) for j in range(n)]
        exceso = sum(anchos) + 3 * (n - 1) + 4 - iw
        if exceso > 0 and n >= 3:
            anchos[2] = max(min(anchos[2], 24), anchos[2] - exceso)
            exceso = sum(anchos) + 3 * (n - 1) + 4 - iw
        if exceso <= 0 or n <= 2:
            break
        n -= 1
        filas = [(e, f[:n]) for e, f in filas]
    if exceso > 0 and n >= 3:
        anchos[2] = max(12, anchos[2] - exceso)
    out = [HL.clip("    " + "   ".join("%s%s%s" % (K["DIM"] + K["BO"], HL.pad(cols[j], a), K["R"])
                                        for j, a in enumerate(anchos)), iw)]
    for es, f in filas:
        marca = "%s%s%s " % (K["C"] + K["BO"], K["PTR"], K["R"]) if es else "  "
        celdas = []
        for j, (t, a) in enumerate(zip(f, anchos)):
            col = (K["WH"] + K["BO"]) if j == 0 else (K["WH"] if es else K["GREY"])
            celdas.append("%s%s%s" % (col, HL.pad(corta_ruta(t, a), a), K["R"]))
        out.append(HL.clip("  " + marca + "   ".join(celdas), iw))
    return out


def explicacion(K, M, iw, lineas=4):
    """El título del paso y qué pasa, en palabras (como «COMPOSICIÓN» en la
    vista del cerebro)."""
    p = actual(M)
    out = [HL.clip("%s%s%s" % (K["C"] + K["BO"], _titulo(p), K["R"]), iw)]
    sub = SB._wrap(D.mapa_rellenar(_tx(p)["explica"], valores(M)), max(8, iw))
    if len(sub) > lineas:
        sub = sub[:lineas]
        sub[-1] = HL.clip(sub[-1] + " …", iw)
    return out + [HL.clip("%s%s%s" % (K["GREY"], ln, K["R"]), iw) for ln in sub]


def cuerpo(K, M, iw, alto):
    """Contexto, pestañas de los pasos, qué pasa (arriba, como la vista del
    cerebro), el árbol, la leyenda y lo que lo demuestra. → (líneas, fila del
    árbol)."""
    p = actual(M)
    arriba = contexto(K, M, iw) + pasos(K, M, iw) + [""]
    n_exp = len(SB._wrap(D.mapa_rellenar(_tx(p)["explica"], valores(M)), max(8, iw)))
    expl = explicacion(K, M, iw, n_exp) + [""]
    dib, _cur = arbol(K, M, iw, M.get("_aire", 1)) or (None, 0)
    if dib is None:
        dib, _cur = arbol_texto(K, M, iw)
    pie = [""] + leyenda(K, M, iw)
    if p["id"] == "motores":
        pie += [""] + _tabla_motores(K, M, iw)
    prueba = D.mostrar(p, M.get("ctx") or None)
    pie.append(HL.clip("%s%s%s %s%s%s" % (K["DIM"], _t("docs.mapa.check", "compruébalo:", "check it:"),
                                           K["R"], K["C"], prueba, K["R"]), iw))
    return arriba + expl + dib + pie, len(arriba) + len(expl)


def _chips(desplaza=False):
    return (("←→", _t("docs.mapa.k.step", "paso", "step")),) + (
        (("↑↓", _t("docs.mapa.k.scroll", "desplaza", "scroll")),) if desplaza else ()) + (
        ("Tab", _t("docs.k.agent", "otro agente", "other agent")),
        ("Enter", _t("docs.k.open", "abre", "opens")),
        ("q", _t("docs.mapa.k.back", "capítulos", "chapters")))


def render(M, w, h, word):
    K = SF.K()
    titulo = _t("docs.mapa.title", "EL MAPA DE LA MEMORIA", "THE MEMORY MAP")
    alto = max(8, h - 10)

    def _cuerpo(iw):
        lineas, cur = cuerpo(K, M, iw, alto)
        M["_cur"] = cur
        return lineas
    _pw, iw = SB.widths(w, BOX_W)
    ctx = M.get("ctx") or {}
    clave = (iw, h, D.lang(), ctx.get("brain"), ctx.get("engine"))
    if not M.get("_est") or M["_est"][0] != clave:
        # el alto del paso más largo (la caja no salta al cambiar de paso);
        # si con aire entre carpetas no cabe, las cajas van juntas
        guardado = M["paso"]
        for aire in (1, 0):
            M["_aire"] = aire
            mx = 0
            for k in range(len(D.MAPA_PASOS)):
                M["paso"] = k
                mx = max(mx, len(cuerpo(K, M, iw, alto)[0]))
            if mx <= alto:
                break
        M["paso"] = guardado
        M["_est"] = (clave, mx)
    def _marco():
        lineas = SB.frame(K, w, h, word, titulo, _cuerpo, _chips(M.get("_desplaza", False)),
                          msg=M.get("msg", ""), scroll=M.get("scroll", 0), box_w=BOX_W,
                          stable_rows=M["_est"][1])
        M["scroll"] = max(0, min(M.get("scroll", 0), SB.frame.last_max_scroll))
        return lineas
    out = _marco()
    if (SB.frame.last_max_scroll > 0) != M.get("_desplaza", False):
        M["_desplaza"] = SB.frame.last_max_scroll > 0      # el botón ↑↓ solo si hay qué desplazar
        out = _marco()
    return out


def act(M, key):
    """True = sigue en el mapa · False = vuelve a los capítulos · 'abrir' =
    abre lo que demuestra el paso elegido (lo hace el caller)."""
    M["msg"] = ""
    n = len(D.MAPA_PASOS)
    if key in ("q", "Q", "\x1b", "\x03"):
        return False
    if key == "left":
        M["paso"] = (M["paso"] - 1) % n
    elif key in ("right", " "):
        M["paso"] = (M["paso"] + 1) % n
    elif key in tuple("01234567"):
        M["paso"] = min(n - 1, int(key))          # los números de las pestañas (0 = todo)
    elif key in ("up", "k", "pageup"):
        M["scroll"] = max(0, M.get("scroll", 0) - (10 if key == "pageup" else 2))
    elif key in ("down", "j", "pagedown"):
        M["scroll"] = M.get("scroll", 0) + (10 if key == "pagedown" else 2)   # render lo ajusta
    elif key in ("\r", "\n"):
        return "abrir"
    return True
