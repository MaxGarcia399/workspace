#!/usr/bin/env python3
r"""WORKSPACE · hub_agentes_maquina — Agentes › «Esta máquina»: lo de cada agente que solo vive en ESTA máquina.

Lo que antes solo tenía la pantalla vieja de Agentes, en el hub de hoy (sus fichas, su foco y su mouse):
  · En el hub: si se ve en Inicio y en el riel (agent_manage.set_hidden). Ocultarlo no borra nada; los que están
    fuera se listan abajo («Fuera del hub») con «Volver al hub».
  · Revisión de skills (agent_manage.set_skill_review).
  · Ruta del cerebro: se escribe o se pega (con comillas, «\ » de la terminal, «~» o «file://»); se revisa que la
    carpeta exista antes de guardar (agent_manage.set_brain).
  · Reparar (un agente averiado): la carpeta que el discovery encontró, su carpeta a mano o el tablero de motores.
  · Archivar (agente_apartar.archivar): sale de las listas, de Inicio, del riel y de los selectores; su carpeta y sus
    sesiones se quedan. «Archivados» lo trae de vuelta con un clic.
  · Quitar de Workspace (agente_apartar.quitar, que reusa agent_manage.unregister): lo desregistra en esta
    computadora (registro, ruta local, su comando y su tema). Se confirma antes; su carpeta NUNCA se borra y se dice
    dónde se queda.
  · Las dos avisan en una línea, con «Deshacer». Lo que conviene saber antes (hablas con él ahora, es el único, tiene
    algo abierto, coordina a otros, su carpeta está a medio sincronizar) se dice al confirmar; nada bloquea.
El motor, los permisos, la cara y el nombre ya viven en otras partes del hub (Tablero, Ajustes › Permisos,
Apariencia): aquí no se repiten.

La página no tiene rutas para esto: se lee y se escribe aquí mismo (agent_state y agent_manage, que revalidan al
agente y su cerebro antes de tocar nada), en el fondo, y se avisa el resultado REAL (✓ su mensaje · ✗ su error).
Stdlib."""
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_bloque as B  # noqa: E402
import hub_paleta as P  # noqa: E402

C, ERR = P.C, P.ERR
W, corto = B.W, B.corto

#: La pestaña (Agentes › …), la clave de sus datos (Directo.datos) y el campo que se edita (seccion["editando"]).
TAB = "maquina"
CLAVE = "maquina"
EDITANDO = "ruta"
#: Lo que cabe en el campo de la ruta (una ruta larga de verdad, no el tope de 40 del nombre).
TOPE_RUTA = 1024
#: Cuánto se ofrece «Deshacer» después de archivar o quitar (s).
DESHACER_S = 45.0
#: La vista de la pestaña con solo los archivados (cuando no caben junto a las opciones).
VISTA_ARCHIVADOS = "archivados"
#: Averías de su cerebro (se reparan con su carpeta) y de su motor (con otro motor: el tablero).
_DE_CEREBRO = ("brain_missing", "definition_missing", "brain_unreadable")
_DE_MOTOR = ("engine_missing", "engine_unknown")


def _t(key, es, **kw):
    """La cadena `key` del catálogo (lang/*/hubmaquina.py) en el idioma del hub (hub_directo.idioma_hub, AG3-a: el
    tuyo si el hub ya está en él; si no, español, como todo el hub); sin catálogo, `es` tal cual."""
    s = es
    try:
        import hub_directo
        if hub_directo.idioma_hub() != "es":
            import i18n
            v = i18n.t(key)
            if v != key:
                s = v
    except Exception:
        s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def etiqueta():
    return _t("hubmaq.tab", "Esta máquina")


def tope(sec, otro):
    """Cuánto cabe en el campo de la sección: la ruta del cerebro aquí; si no, `otro` (el de siempre)."""
    return TOPE_RUTA if (sec or {}).get("editando") == EDITANDO else otro


# ── los datos (locales: agent_state y agent_manage) ───────────────────────────
_CAMPOS = ("id", "name", "display", "brain", "status", "cause", "repair", "suggested_brain", "engine", "loaded")


def leer():
    """Todos los agentes registrados en esta máquina (los del hub, los de fuera y los averiados) con su cerebro, su
    estado y su revisión de skills. Si no se puede leer, ErrorServidor (lo que Directo._pedir anota y se ve)."""
    import hub_directo as D
    try:
        import agent_state
        import agent_manage
        out = []
        for a in agent_state.snapshot().registered(include_hidden=True):
            d = {k: a.get(k) for k in _CAMPOS}
            d["brain"] = d.get("brain") or ""
            d["hidden"] = bool(a.get("hidden"))
            d["skill_review"], d["review_global"] = None, False
            if a.get("status") in ("ready", "hidden"):
                try:
                    pr = agent_manage.preferences(a.get("id") or a.get("name"), expected_brain=d["brain"])
                except Exception:
                    pr = {}
                if pr.get("ok"):
                    d["skill_review"], d["review_global"] = bool(pr.get("skill_review")), bool(pr.get("review_global"))
            out.append(d)
        try:
            import agente_apartar
            ap = agente_apartar.leer()
        except Exception:
            ap = {}
        return {"agentes": out, "archivados": ap.get("archivados") or [], "avisos": ap.get("avisos") or {}}
    except Exception as e:
        raise D.ErrorServidor(None, _t("hubmaq.no_lei", "No pude leer esta máquina: {e}", e=e))


def _uno(s, aid):
    return next((a for a in ((s.get("datos") or {}).get(CLAVE) or {}).get("agentes") or [] if a.get("id") == aid),
                None)


def _averiado(a):
    return (a or {}).get("status") not in ("ready", "hidden")


def _etiqueta_estado(st):
    try:
        import agent_state
        return agent_state.label(st)
    except Exception:
        return st


def ruta_corta(p):
    home = os.path.expanduser("~")
    return ("~" + p[len(home):]) if p and home and p.startswith(home) and home != os.sep else (p or "")


def _por_la_izquierda(p, n):
    """Una ruta que no cabe se corta por la izquierda: el nombre de su carpeta (lo que la identifica) se ve."""
    return p if W(p) <= n else "…" + p[-max(1, n - 1):]


# ── la ruta: lo que escribiste o pegaste → la carpeta ─────────────────────────
def normalizar_ruta(texto, posix=None):
    r"""Lo que escribiste o pegaste → la ruta: sin espacios ni saltos alrededor, sin un par de comillas que la
    envuelvan, `file://…` (con sus %20) como ruta, los escapes de la terminal (`\ `, `\(`…) fuera en Mac y Linux (en
    Windows la \ es la de las carpetas: se queda) y `~` como tu carpeta. Vacío → ""."""
    posix = (os.sep == "/") if posix is None else bool(posix)
    t = str(texto or "").strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1].strip()
    if not t:
        return ""
    if t.lower().startswith("file://"):
        from urllib.parse import unquote, urlsplit
        u = urlsplit(t)
        ruta = unquote(u.path or "")
        if u.netloc and u.netloc.lower() != "localhost":
            ruta = "//" + u.netloc + ruta                      # file://servidor/carpeta: la carpeta de la red
        if not posix and re.match(r"^/[A-Za-z]:", ruta):
            ruta = ruta[1:]                                   # file:///C:/…  →  C:/…
        t = ruta
    elif posix:
        t = re.sub(r"\\(.)", r"\1", t)
    if t.startswith("~"):
        t = os.path.expanduser(t)
        if os.sep != "/":                                       # Windows: ~/x → C:\Users\…\x (una sola barra)
            t = os.path.normpath(t)
    return t


# ── lo que se dibuja ──────────────────────────────────────────────────────────
def pestanas(L, x, y, w, tabs, tab):
    """Las pestañas del agente, en una fila; si no caben en `w`, en dos. → la fila donde empieza la caja."""
    xx, yy = x, y
    for k, lab in tabs:
        lab = " %s " % (etiqueta() if k == TAB else lab)
        if xx > x and xx + W(lab) + 2 > x + w:
            xx, yy = x, yy + 1
        xx = B.chip(L, xx, yy, lab, "tab:" + k, activo=k == tab) + 1
    return yy + 2


def _ficha(L, T, x, y, lab, rid, a, encendida=False, peligro=False, hov=None):
    """Una ficha de una fila que se toca (o la de su fila, si `hov` ya lo dice). → la columna siguiente."""
    if hov is None:
        hov = L.reg(x, y, W(lab) + 2, 1, rid)
    if encendida:
        col, fg = (P.mix(a["c"], "#ffffff", 0.18) if hov else a["c"]), B.LUZTX
    elif peligro:
        col, fg = (P.mix(ERR, "#ffffff", 0.18) if hov else ERR), B.LUZTX
    else:
        col, fg = (B.P4 if hov or L.apr(rid) else B.P3), (C["tx"] if hov else C["tx2"])
    return B.ficha(T, x, y, lab, col, B.P2, fg, bool(encendida or peligro or hov))


def _envolver(texto, ancho, maximo):
    """`texto` en renglones de `ancho` columnas (por palabras), a lo más `maximo`; si no cabe todo, el último termina
    en «…»."""
    out, ln = [], ""
    for p in str(texto or "").split():
        cand = (ln + " " + p) if ln else p
        if W(cand) <= ancho:
            ln = cand
            continue
        if ln:
            out.append(ln)
        ln = p if W(p) <= ancho else corto(p, ancho)
    if ln:
        out.append(ln)
    if maximo <= 0:
        return []
    if len(out) > maximo:
        out = out[:maximo - 1] + [corto(" ".join(out[maximo - 1:]) + " …", ancho)]
    return out


def _titulo(titulo, ficha, iw):
    """Los renglones del nombre de una opción junto a su ficha: en uno, o en dos si la caja es angosta. Si ni así cabe
    (una ficha larga), la ficha baja a su propio renglón: el último de la lista es "" (ahí va la ficha)."""
    libre = iw - W(" %s " % ficha) - 3
    partes = _envolver(titulo, max(1, libre), 2)
    if libre >= max([W(p) for p in str(titulo).split()] + [1]) and partes and \
            " ".join(partes) == " ".join(str(titulo).split()):
        return partes
    return (_envolver(titulo, iw, 2) or [""]) + [""]


def _fila(L, T, ix, iw, yy, rid, titulo, ficha, subs, a, encendida=False, sub_col=None):
    """Una opción: su nombre a la izquierda (en uno o dos renglones), su ficha a la derecha (o abajo, si no cabe) y
    abajo su explicación (`subs`: sus renglones, ya envueltos; puede no haber). Toda la fila se toca. → la fila
    siguiente."""
    tit = _titulo(titulo, ficha, iw)
    alto = len(tit) + len(subs)
    hov = L.reg(ix - 1, yy, iw + 2, alto, rid)
    if hov or L.apr(rid):
        T.fill(ix - 1, yy, iw + 2, alto, B.P4 if L.apr(rid) else B.P3)
    lab = " %s " % ficha
    for j, ln in enumerate(tit):
        T.put(ix, yy + j, ln, C["tx"] if hov else C["tx2"], hov)
    _ficha(L, T, ix + iw - W(lab) - 2, yy + (len(tit) - 1 if tit[-1] == "" else 0), lab, rid, a,
           encendida=encendida, hov=hov)
    for j, ln in enumerate(subs):
        T.put(ix, yy + len(tit) + j, corto(ln, iw), sub_col or C["tx3"])
    return yy + alto


def _opciones(a, b):
    """Las opciones del agente `a` (sus datos de esta máquina): [(rid, título, ficha, explicación, encendida, color)].
    Un averiado empieza por «Reparar» y no ofrece lo que no le aplica (ocultarse, la revisión de skills)."""
    out = []
    if _averiado(a):
        st = a.get("status")
        quehace = (_t("hubmaq.rep.encontrada", "Usar la que encontré") if a.get("suggested_brain") else
                   _t("hubmaq.rep.carpeta", "Elegir su carpeta") if st in _DE_CEREBRO else
                   _t("hubmaq.rep.motor", "Elegir otro motor") if st in _DE_MOTOR else "")
        if quehace:
            sub = (_t("hubmaq.rep.en", "La encontré en {p}", p=ruta_corta(a["suggested_brain"]))
                   if a.get("suggested_brain") else (a.get("repair") or a.get("cause") or ""))
            out.append(("acc:maq:reparar", _t("hubmaq.rep.titulo", "Reparar"), quehace, sub, False, None))
    else:
        out.append(("acc:maq:hub", _t("hubmaq.hub.titulo", "En el hub"),
                    "● " + _t("hubmaq.si", "sí") if not a.get("hidden") else "○ " + _t("hubmaq.no", "no"),
                    _t("hubmaq.hub.sub", "Quitarlo no borra nada: vuelve desde «Fuera del hub»."),
                    not a.get("hidden"), None))
        rv = a.get("skill_review")
        if rv is not None:
            sub = _t("hubmaq.rev.sub", "Al abrir cada sesión revisa la anterior y mejora sus skills; usa un poco de "
                                       "tu suscripción.")
            if a.get("review_global"):
                sub = _t("hubmaq.rev.global", "Sigue el ajuste general.") + " " + sub
            out.append(("acc:maq:revision", _t("hubmaq.rev.titulo", "Revisión de skills"),
                        "● " + _t("hubmaq.si", "sí") if rv else "○ " + _t("hubmaq.no", "no"), sub, bool(rv), None))
    out.append(("acc:maq:ruta", _t("hubmaq.ruta.titulo", "Ruta del cerebro"), _t("hubmaq.ruta.ficha", "Cambiar"),
                _t("hubmaq.ruta.sub", "Si moviste su carpeta, aquí la apuntas de nuevo."), False, None))
    out.append(("acc:maq:archivar", _t("hubmaq.arch.titulo", "Archivar"), _t("hubmaq.arch.ficha", "Archivar"),
                _t("hubmaq.arch.sub", "Sale de las listas. Su carpeta y sus sesiones se quedan; vuelve con un clic "
                                      "desde «Archivados»."), False, None))
    return out


def archivados(d):
    return list((d or {}).get("archivados") or [])


#: La clave (Directo.datos) de los archivados que enseña Inicio en la tarjeta de «Agente nuevo».
CLAVE_INICIO = "archivados"


def leer_archivados():
    """Solo los archivados (barato: una ficha chica): Inicio los ofrece en la tarjeta de «Agente nuevo», también
    cuando no queda ningún agente."""
    try:
        import agente_apartar
        return {"archivados": agente_apartar.archivados()}
    except Exception:
        return {"archivados": []}


def avisos_de(s, d, a):
    """Lo que conviene saber antes de apartar a `a`: lo que leyó agente_apartar, más «tienes su conversación abierta»
    si aquí lo está (el hub lo sabe por su foto)."""
    av = [x for x in ((d or {}).get("avisos") or {}).get(a.get("name") or a.get("id")) or [] if x.get("texto")]
    if a.get("id") in (s.get("conversando") or ()) and not any(x.get("clave") == "actual" for x in av):
        av.insert(0, {"clave": "actual", "texto": _t(
            "hubmaq.aviso.actual", "Tienes una conversación abierta con {n}: sigue, pero deja de verse en las listas.",
            n=a.get("display") or a.get("id") or "")})
    return av


def deshacer_vigente(s):
    """El último archivar o quitar que todavía se puede deshacer desde su aviso, o None."""
    ap = s.get("apartado")
    return ap if ap and ap.get("nombre") and (s.get("t") or 0) - (ap.get("t") or 0) < DESHACER_S else None


def detalle(L, s, M, sec, aid):
    """La pestaña «Esta máquina» del agente `aid`, en la caja del detalle del marco `M` (xd, wd, yd … y1)."""
    T = L.T
    x, y, w = M["xd"], M["yd"], M["wd"]
    alto = M["y1"] + 1 - y
    if alto < 3:
        return
    B.bloque(T, x, y, w, alto, B.P2, B.BG)
    L.reg(x, y, w, alto, "detalle")
    ix, iw, y_fin = x + 3, w - 6, y + alto - 1
    b = next((z for z in s.get("agentes") or [] if z.get("id") == aid), None)
    d = (s.get("datos") or {}).get(CLAVE)
    if d is None:
        txt = (_t("hubmaq.viendo", "Viendo esta máquina…") if CLAVE in (s.get("cargando") or ()) else
               (s.get("errores") or {}).get(CLAVE) or _t("hubmaq.sin_datos", "Sin datos."))
        _parrafo(T, ix, y + 1, txt, iw, C["tx3"], max(1, alto - 2))
        return
    a = _uno(s, aid) if aid else None
    yy = _aviso_deshacer(L, s, T, ix, iw, y + 1, y_fin, B.agente(s) if b is None else b)
    if sec.get("maq_vista") == VISTA_ARCHIVADOS:
        _vista_archivados(L, s, T, ix, iw, yy, y_fin, d, B.agente(s) if b is None else b)
        return
    if b is None or a is None:
        if b is not None:
            yy = _parrafo(T, ix, yy, _t("hubmaq.no_esta", "No encuentro a {n} en esta máquina: puede que lo hayan "
                                                          "quitado desde otra ventana.", n=b["n"]), iw, C["tx3"], 3)
        elif not aid:
            T.put(ix, yy, corto(_t("hubmaq.elige", "Elige un agente."), iw), C["tx3"])
            yy += 1
        yy = _archivados(L, s, T, ix, iw, yy + 1, y_fin, d, B.agente(s))
        _fuera(L, s, T, ix, iw, yy + 1, y_fin, d, B.agente(s))
        return
    if sec.get("editando") == EDITANDO and sec.get("maq_agente") == aid:
        _campo(L, s, T, ix, iw, yy, y_fin, sec, a, b)
        return
    conf = sec.get("maq_confirma") or {}
    if conf.get("id") == aid and conf.get("que") in ("archivar", "quitar"):
        _confirmar(L, s, T, ix, iw, yy, y_fin, conf["que"], a, b, d)
        return
    nombre = b["n"]
    T.put(ix, yy, corto(_t("hubmaq.titulo", "{n} en esta máquina", n=nombre), iw), C["tx"], True)
    st = a.get("status") or "ready"
    if _averiado(a):
        estado, col = "✗ " + " · ".join(x_ for x_ in (_etiqueta_estado(st), a.get("cause") or "") if x_), ERR
    else:
        import hub_directo as D
        estado = ("● " + _etiqueta_estado("ready") + " · " + D.nombre_motor(b.get("motor") or b.get("mid") or
                                                                           a.get("engine") or ""))
        col = B.OK
    for ln in _envolver(estado, iw, 2 if _averiado(a) else 1):    # la avería entera, si cabe en dos renglones
        yy += 1
        T.put(ix, yy, ln, col)
    kw = W(_t("hubmaq.cerebro", "Cerebro")) + 2
    T.put(ix, yy + 1, _t("hubmaq.cerebro", "Cerebro"), C["tx3"])
    T.put(ix + kw, yy + 1, _por_la_izquierda(ruta_corta(a.get("brain") or "") or _t("hubmaq.sin_ruta", "sin ruta"),
                                             max(4, iw - kw)), C["tx2"])
    ops = _opciones(a, b)
    arch = archivados(d)
    ocultos = [z for z in d.get("agentes") or [] if z.get("hidden")]
    q_tit, q_ficha = _t("hubmaq.quitar.titulo", "Quitar de Workspace"), _t("hubmaq.quitar.ficha", "Quitar")
    nada_l = _queda(a, iw)                            # dónde se queda su carpeta: siempre, y entero
    # lo más holgado que quepa: explicaciones de hasta 3 renglones y aire entre opciones → 2 → 1 → sin aire → sin
    # ellas → sin el renglón en blanco de arriba. «Su carpeta no se borra» se dice siempre; los archivados, en su
    # lista si cabe y, si no, en un renglón que la abre
    for n_sub, aire, hueco in ((3, 1, 3), (2, 1, 3), (1, 1, 3), (1, 0, 3), (0, 0, 3), (0, 0, 2)):
        libre = y_fin - (yy + hueco) + 1
        subs = [_envolver(o[3], iw, n_sub) for o in ops]
        alto_q = len(_titulo(q_tit, q_ficha, iw)) + len(nada_l)
        lista = (2 + _alto_archivados(arch, iw)) if arch else 0
        fuera_h = (2 + len(ocultos)) if ocultos else 0
        base = sum(len(_titulo(o[1], o[2], iw)) + len(x_) + aire for o, x_ in zip(ops, subs)) + alto_q
        if base + lista + fuera_h <= libre:
            break
        if arch and base + 1 <= libre:               # los archivados en un renglón (lo demás, completo)
            lista = -1
            break
    else:
        lista = -1 if arch else 0
    yy += hueco
    for (rid, titulo, ficha, _sub, on, sub_col), sb in zip(ops, subs):
        if yy + len(_titulo(titulo, ficha, iw)) + len(sb) - 1 > y_fin:
            return
        yy = _fila(L, T, ix, iw, yy, rid, titulo, ficha, sb, b, encendida=on, sub_col=sub_col) + aire
    if yy + alto_q - 1 > y_fin:
        return
    yy = _fila(L, T, ix, iw, yy, "acc:maq:quitar", q_tit, q_ficha, nada_l, b)
    if lista < 0:
        if yy <= y_fin:
            _fila(L, T, ix, iw, yy + 1 if yy + 1 <= y_fin else yy, "acc:maq:archivados",
                  _t("hubmaq.arch.lista_n", "Archivados ({n})", n=len(arch)), _t("hubmaq.arch.ver", "Ver"), [], b)
        return
    yy = _archivados(L, s, T, ix, iw, yy + 1, y_fin, d, b)
    _fuera(L, s, T, ix, iw, yy + 1, y_fin, d, b)


def _aviso_deshacer(L, s, T, ix, iw, yy, y_fin, b):
    """El aviso de una línea del último archivar o quitar, con su «Deshacer» (mientras se pueda). → la fila donde
    sigue lo demás."""
    ap = deshacer_vigente(s)
    if not ap or yy + 2 > y_fin:
        return yy
    lab = " %s " % _t("hubmaq.deshacer", "Deshacer")
    xb = ix + iw - W(lab) - 2
    lineas = _envolver("✓ " + (ap.get("texto") or ""), max(8, xb - ix - 1), 4 if y_fin - yy >= 12 else 3)
    for j, ln in enumerate(lineas):
        T.put(ix, yy + j, ln, B.OK if j == 0 else C["tx2"])
    _ficha(L, T, xb, yy, lab, "acc:maq:deshacer", b, encendida=True)
    return yy + len(lineas) + 1


def _confirmar(L, s, T, ix, iw, yy, y_fin, que, a, b, d):
    """La confirmación de archivar o de quitar, en toda la caja: la pregunta, lo que pasa, lo que conviene saber
    antes (cada aviso con su ⚠), dónde se queda su carpeta y dos botones grandes."""
    nombre = b["n"]
    if que == "quitar":
        pregunta = _t("hubmaq.quitar.pregunta", "¿Quitar a {n} de Workspace?", n=nombre)
        pasa = _t("hubmaq.quitar.pasa", "Deja de estar en Workspace en esta computadora: su registro, su comando de "
                                        "la terminal y su tema.")
        si = _t("hubmaq.quitar.si", "Sí, quitar")
    else:
        pregunta = _t("hubmaq.arch.pregunta", "¿Archivar a {n}?", n=nombre)
        pasa = _t("hubmaq.arch.pasa", "Sale de las listas, de Inicio y del riel. Vuelve con un clic desde "
                                      "«Archivados».")
        si = _t("hubmaq.arch.si", "Sí, archivar")
    av = avisos_de(s, d, a)
    cancelar = _t("hubmaq.cancelar", "Cancelar")
    mitad = (iw - 1) // 2
    apilados = mitad < max(W(si), W(cancelar)) + 4    # angosta: un botón sobre el otro, cada uno con su texto entero
    alto = y_fin - yy + 1
    queda_l = _queda(a, iw)
    # lo que cabe, de lo más holgado a lo más apretado: con «qué pasa» y los avisos enteros → avisos de 2 renglones
    # → sin «qué pasa» → avisos de 1 renglón; los botones grandes mientras quepan
    for con_pasa, por_aviso, alto_b, aire in ((True, 6, 6 if apilados else 3, 1), (True, 2, 6 if apilados else 3, 1),
                                              (True, 2, 3, 0), (False, 2, 3, 0), (False, 1, 3, 0), (False, 1, 1, 0)):
        preg_l = _envolver(pregunta, iw, 2)
        pasa_l = _envolver(pasa, iw, 4) if con_pasa else []
        av_l = [_envolver("⚠ " + x_["texto"], iw, por_aviso) for x_ in av]
        cuerpo = len(preg_l) + len(pasa_l) + sum(len(x_) for x_ in av_l) + len(queda_l)
        if cuerpo + aire * (1 + (1 if av_l else 0)) + (1 if alto_b > 1 else 0) + alto_b <= alto:
            break
    for ln in preg_l:
        T.put(ix, yy, ln, C["tx"], True)
        yy += 1
    for ln in pasa_l:
        T.put(ix, yy, ln, C["tx2"])
        yy += 1
    yy += aire
    for bloque_ in av_l:
        for ln in bloque_:
            if yy <= y_fin - alto_b:
                T.put(ix, yy, ln, B.WARN)
                yy += 1
    yy += aire if av_l else 0
    for ln in queda_l:
        if yy <= y_fin - alto_b:
            T.put(ix, yy, corto(ln, iw), C["tx3"])
            yy += 1
    if alto_b == 1:                                   # sin lugar: dos fichas
        yb = min(yy, y_fin)
        xx = _ficha(L, T, ix, yb, " %s " % si, "acc:maq:si", b, peligro=que == "quitar", encendida=que != "quitar")
        _ficha(L, T, xx + 1, yb, " %s " % cancelar, "acc:maq:no", b)
        return
    yb = min(max(yy + 1, y_fin - alto_b - 2), y_fin - alto_b + 1)
    if alto_b == 6 or (apilados and alto_b == 3 and False):
        B.boton(L, s, ix, yb, si, "acc:maq:si", B.P2, foco=True, ancho=iw, a=b)
        B.boton(L, s, ix, yb + 3, cancelar, "acc:maq:no", B.P2, ancho=iw, a=b)
    else:                                             # dos botones grandes, lado a lado (como el campo de la ruta)
        B.boton(L, s, ix, yb, si, "acc:maq:si", B.P2, foco=True, ancho=mitad, a=b)
        B.boton(L, s, ix + mitad + 1, yb, cancelar, "acc:maq:no", B.P2, ancho=iw - mitad - 1, a=b)


def _queda(a, iw):
    """«Su carpeta no se borra: se queda en <ruta>», en los renglones que haga falta: la ruta va entera (en su propio
    renglón si no cabe junto al texto; por su final si ni así cabe: el nombre de su carpeta siempre se ve)."""
    texto = _t("hubmaq.quitar.sub", "Su carpeta no se borra: se queda en")
    donde = ruta_corta(a.get("brain") or "") or _t("hubmaq.sin_ruta", "sin ruta")
    if W(texto) + 1 + W(donde) <= iw:
        return [texto + " " + donde]
    return _envolver(texto, iw, 2) + [_por_la_izquierda(donde, iw)]


def _nombre_archivado(z):
    nombre = z.get("display") or z.get("name") or ""
    if not z.get("existe"):
        nombre += " · " + _t("hubmaq.arch.sin_carpeta", "su carpeta no está aquí")
    return nombre


def _alto_archivados(arch, iw):
    ficha = _t("hubmaq.arch.volver", "Traer de vuelta")
    return sum(len(_titulo(_nombre_archivado(z), ficha, iw)) for z in arch)


def _archivados(L, s, T, ix, iw, yy, y_fin, d, b):
    """«Archivados»: cada uno con «Traer de vuelta» (un clic). → la fila siguiente."""
    arch = archivados(d)
    if not arch or yy + 1 > y_fin:
        return yy - 1 if not arch else yy
    T.put(ix, yy, corto(_t("hubmaq.arch.lista", "Archivados").upper(), iw), C["tx3"], True)
    yy += 1
    ficha = _t("hubmaq.arch.volver", "Traer de vuelta")
    for z in arch:
        nombre = _nombre_archivado(z)
        if yy + len(_titulo(nombre, ficha, iw)) - 1 > y_fin:
            T.put(ix + iw - 1, y_fin, "▼", C["tx2"])
            return y_fin + 1
        yy = _fila(L, T, ix, iw, yy, "acc:maq:volver:" + str(z.get("name")), nombre, ficha, [], b)
    return yy


def _vista_archivados(L, s, T, ix, iw, yy, y_fin, d, b):
    """Solo los archivados (y los de fuera del hub), con «‹ Atrás»: para cuando no caben junto a las opciones."""
    lab = " %s " % _t("hubmaq.atras", "‹ Atrás")
    _ficha(L, T, ix, yy, lab, "acc:maq:atras", b)
    yy += 2
    if not archivados(d):
        T.put(ix, yy, corto(_t("hubmaq.arch.vacio", "No hay agentes archivados."), iw), C["tx3"])
        return
    yy = _archivados(L, s, T, ix, iw, yy, y_fin, d, b)
    _fuera(L, s, T, ix, iw, yy + 1, y_fin, d, b)


def _fuera(L, s, T, ix, iw, yy, y_fin, d, b):
    """«Fuera del hub»: los agentes ocultos de esta máquina, cada uno con «Volver al hub»."""
    ocultos = [z for z in (d or {}).get("agentes") or [] if z.get("hidden")]
    if not ocultos or yy + 1 > y_fin:
        return
    T.put(ix, yy, corto(_t("hubmaq.fuera.titulo", "Fuera del hub").upper(), iw), C["tx3"], True)
    yy += 1
    for z in ocultos:
        if yy > y_fin:
            T.put(ix + iw - 1, y_fin, "▼", C["tx2"])
            return
        yy = _fila(L, T, ix, iw, yy, "acc:maq:mostrar:" + str(z.get("id")), z.get("display") or z.get("id") or "",
                   _t("hubmaq.fuera.ficha", "Volver al hub"), [], b)


def _campo(L, s, T, ix, iw, yy, y_fin, sec, a, b):
    """El campo de la ruta (escrita o pegada): la de ahora, lo que llevas (por su final si no cabe), su error y
    «Guardar» / «Cancelar»."""
    T.put(ix, yy, corto(_t("hubmaq.ruta.nueva", "Nueva ruta del cerebro de {n}", n=b["n"]), iw), C["tx"], True)
    yy = _parrafo(T, ix, yy + 1, _t("hubmaq.ruta.ayuda", "Pega o escribe su carpeta (o arrástrala aquí). Enter "
                                                         "guarda · Esc cancela."), iw, C["tx3"], 2)
    if a.get("brain") and yy < y_fin - 7:
        T.put(ix, yy, _por_la_izquierda(_t("hubmaq.ruta.ahora", "Ahora: {p}", p=ruta_corta(a["brain"])), iw),
              C["tx3"])
        yy += 1
    yy += 1
    B.bloque(T, ix, yy, iw, 3, B.P3, B.P2)
    xx = T.put(ix + 2, yy + 1, "❯", b["c"], True, B.P3)
    buf = sec.get("buf") or ""
    xx = T.put(xx + 1, yy + 1, _por_la_izquierda(buf, max(1, iw - 6)), C["tx"], False, B.P3)
    T.put(xx, yy + 1, "▏", C["tx"], False, B.P3)
    yy += 3
    if sec.get("error"):
        yy = _parrafo(T, ix, yy, sec["error"], iw, ERR, 2)
    yy += 1
    if yy + 2 <= y_fin:                               # dos botones (como Calendario y el nombre)
        mitad = (iw - 1) // 2
        B.boton(L, s, ix, yy, _t("hubmaq.guardar", "Guardar"), "acc:maq:guardar", B.P2, foco=True, ancho=mitad, a=b)
        B.boton(L, s, ix + mitad + 1, yy, _t("hubmaq.cancelar", "Cancelar"), "acc:maq:cancelar", B.P2,
                ancho=iw - mitad - 1, a=b)
    elif yy <= y_fin:                                 # sin lugar: dos fichas
        xx = _ficha(L, T, ix, yy, " %s " % _t("hubmaq.guardar", "Guardar"), "acc:maq:guardar", b, encendida=True)
        _ficha(L, T, xx + 1, yy, " %s " % _t("hubmaq.cancelar", "Cancelar"), "acc:maq:cancelar", b)


def _parrafo(T, x, y, texto, ancho, fg, maximo):
    import hub_directo as D
    for ln in D.envolver([(texto, fg, False)], ancho)[:maximo]:
        D._linea(T, x, y, ln, x + ancho)
        y += 1
    return y


# ── lo que hace cada ficha (Directo._accion_seccion → aquí) ───────────────────
def accion(app, acc):
    """`acc`: «maq:<qué>[:<id>]» (o «guardar»/«cancelar» del campo de la ruta). Las escrituras van a agent_manage y a
    agente_apartar en el fondo; después se releen los agentes y esta máquina y se avisa lo que pasó de verdad."""
    sec = app.seccion
    que, _s, resto = (acc[4:] if acc.startswith("maq:") else acc).partition(":")
    conf = sec.pop("maq_confirma", None) or {}
    if que == "cancelar":
        sec.update(editando=None, error="")
        app._avisar(_t("hubmaq.cancelado", "Cancelado · nada se guardó."))
        return None
    if que == "no":
        app._avisar(_t("hubmaq.cancelado", "Cancelado · nada se guardó."))
        return None
    if que == "deshacer":
        return deshacer(app)
    if que == "archivados":
        sec["maq_vista"] = VISTA_ARCHIVADOS
        return None
    if que == "atras":
        sec.pop("maq_vista", None)
        return None
    if que == "volver":                               # «Traer de vuelta» a un archivado
        return _apartar(app, "volver", resto, "")
    if que == "guardar" and sec.get("editando") == EDITANDO:
        aid = sec.get("maq_agente") or ""
    elif que == "mostrar":
        aid = resto
    elif que == "si":
        aid = conf.get("id") or ""
    else:
        _rids, cur = app._filas_seccion()
        aid = cur[3:] if str(cur).startswith("ag:") else ""
    a = _uno(app.instantanea(), aid) if aid else None
    if a is None:
        app._avisar(_t("hubmaq.sin_agente", "Todavía no veo a ese agente en esta máquina: vuelve a intentar."))
        app._recargar(CLAVE, leer)
        return None
    if que == "hub":
        oculto = not a.get("hidden")
        return _hacer(app, a, "set_hidden", oculto,
                      pista=_t("hubmaq.oculto.pista", " · vuelve desde Agentes › Esta máquina › Fuera del hub")
                      if oculto else "")
    if que == "mostrar":
        return _hacer(app, a, "set_hidden", False)
    if que == "revision" and a.get("skill_review") is not None:
        return _hacer(app, a, "set_skill_review", not a.get("skill_review"))
    if que == "ruta":
        sec.update(editando=EDITANDO, buf="", error="", maq_agente=a["id"])
        return None
    if que == "reparar":
        st = a.get("status")
        if a.get("suggested_brain"):
            return _hacer(app, a, "set_brain", a["suggested_brain"])
        if st in _DE_CEREBRO:
            sec.update(editando=EDITANDO, buf="", error="", maq_agente=a["id"])
        elif st in _DE_MOTOR:                         # otro motor: el tablero (agentes × motores) lo cambia
            sec["vista"] = "tablero"
            app._pedir_r2("agentes")
        return None
    if que == "guardar":
        ruta = normalizar_ruta(sec.get("buf"))
        if not ruta:
            sec["error"] = _t("hubmaq.ruta.vacia", "Escribe o pega la carpeta.")
            return None
        try:
            import agent_manage
            ok, ruta_o_porque = agent_manage.validate_brain(ruta)
        except Exception as e:
            ok, ruta_o_porque = False, str(e)
        if not ok:                                    # se queda en el campo, con lo que escribiste y su error
            sec["error"] = ruta_o_porque
            return None
        sec.update(editando=None, error="")
        return _hacer(app, a, "set_brain", ruta)
    if que == "archivar":                             # sin nada que avisar, de una vez (se deshace); si no, confirma
        st = app.instantanea()
        if avisos_de(st, (st.get("datos") or {}).get(CLAVE), a):
            sec["maq_confirma"] = {"id": a["id"], "que": "archivar"}
            return None
        return _apartar(app, "archivar", a.get("id") or a.get("name"), a.get("brain") or "")
    if que == "quitar":                               # siempre se confirma
        sec["maq_confirma"] = {"id": a["id"], "que": "quitar"}
        return None
    if que == "si" and conf.get("que") in ("archivar", "quitar"):
        return _apartar(app, conf["que"], a.get("id") or a.get("name"), a.get("brain") or "")
    return None


def _apartar(app, que, quien, cerebro):
    """agente_apartar.`que` (archivar · quitar · volver) en el fondo → el aviso con su resultado real; archivar y
    quitar dejan su «Deshacer» (app.apartado) mientras dure DESHACER_S."""
    def hacer():
        try:
            import agente_apartar
            if que == "volver":
                r = agente_apartar.volver(quien)
            else:
                r = getattr(agente_apartar, que)(quien, expected_brain=cerebro or None)
        except Exception as e:
            r = {"ok": False, "error": _t("hubmaq.fallo", "no se pudo: {e}", e="%s: %s" % (type(e).__name__, e))}
        if not isinstance(r, dict):
            r = {"ok": False, "error": str(r)}
        if r.get("ok") and r.get("deshacer"):
            app.apartado = {"nombre": r["deshacer"], "texto": r.get("msg") or "", "t": app.reloj()}
        elif r.get("ok"):
            app.apartado = None
        _despues(app)
        app._avisar(("✓ %s" % (r.get("msg") or "")) if r.get("ok") else
                    ("✗ %s" % (r.get("error") or _t("hubmaq.fallo", "no se pudo: {e}", e="?"))))
    app.en_fondo(hacer)
    return None


def _despues(app):
    """Después de archivar, quitar o traer de vuelta: los agentes y los archivados otra vez. Si no quedó ningún
    agente, a Inicio: ahí están el aviso con su «Deshacer» y los archivados para traerlos de vuelta."""
    app.releer_agentes()
    app._recargar(CLAVE_INICIO, leer_archivados)
    if app.seccion is not None and (app.seccion or {}).get("tab") == TAB:
        app._recargar(CLAVE, leer)
    if not app.d["agentes"]:
        app._ir_inicio()


def deshacer(app):
    """«Deshacer» del último archivar o quitar (desde su aviso: en Agentes o en Inicio)."""
    ap = getattr(app, "apartado", None)
    if not ap or not ap.get("nombre"):
        app._avisar(_t("hubmaq.deshacer.nada", "No hay nada que deshacer."))
        return None
    return _apartar(app, "volver", ap["nombre"], "")


def desde_inicio(app, aid):
    """«Archivar» en la tarjeta del agente (Inicio): sin nada que avisar, lo archiva de una vez (con su «Deshacer»);
    si hay algo que conviene saber antes, abre Agentes › Esta máquina con la confirmación ya puesta."""
    def hacer():
        try:
            d = leer()
        except Exception:
            d = {"agentes": [], "avisos": {}, "archivados": []}
        a = next((z for z in d.get("agentes") or [] if z.get("id") == aid), None)
        if a is None:
            app._avisar(_t("hubmaq.sin_agente", "Todavía no veo a ese agente en esta máquina: vuelve a intentar."))
            return
        if avisos_de(app.instantanea(), d, a):
            app._abrir_seccion("agentes")
            app.seccion.update(sel="ag:" + aid, tab=TAB, abierto=True, maq_confirma={"id": aid, "que": "archivar"})
            app._pedir(CLAVE, leer)
            return
        _apartar_ya(app, a)
    app.en_fondo(hacer)
    return None


def _apartar_ya(app, a):
    try:
        import agente_apartar
        r = agente_apartar.archivar(a.get("id") or a.get("name"), expected_brain=a.get("brain") or None)
    except Exception as e:
        r = {"ok": False, "error": _t("hubmaq.fallo", "no se pudo: {e}", e="%s: %s" % (type(e).__name__, e))}
    if r.get("ok") and r.get("deshacer"):
        app.apartado = {"nombre": r["deshacer"], "texto": r.get("msg") or "", "t": app.reloj()}
    _despues(app)
    app._avisar(("✓ %s" % (r.get("msg") or "")) if r.get("ok") else ("✗ %s" % (r.get("error") or "")))


def _hacer(app, a, fn, *args, pista=""):
    """agent_manage.`fn`(su id, *args, expected_brain=su cerebro) en el fondo → el aviso con su resultado real."""
    aid, cerebro = a.get("id") or a.get("name"), a.get("brain") or ""

    def hacer():
        try:
            import agent_manage
            r = getattr(agent_manage, fn)(aid, *args, expected_brain=cerebro)
        except Exception as e:
            r = {"ok": False, "error": _t("hubmaq.fallo", "no se pudo: {e}", e="%s: %s" % (type(e).__name__, e))}
        if not isinstance(r, dict):
            r = {"ok": False, "error": str(r)}
        txt = ("✓ %s%s" % (r.get("msg") or "", pista)) if r.get("ok") else \
            ("✗ %s" % (r.get("error") or _t("hubmaq.fallo", "no se pudo: {e}", e="?")))
        app.releer_agentes()
        app._recargar(CLAVE, leer)
        app._avisar(txt)
    app.en_fondo(hacer)
    return None
