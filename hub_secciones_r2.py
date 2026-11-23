#!/usr/bin/env python3
r"""WORKSPACE · hub_secciones_r2 — las secciones del hub H-1 que faltaban, del mapa Secciones R1 (la versión de
Zenith). SOLO PARA PROBAR: vive en la rama zenith/hub-h1 y nunca entra a main.

Con la piel H-1 (hub_directo.piel() == "h1") el hub usa este registro; la T-2 sigue con el de hub_secciones.
  · Ajustes en grupos: General (idioma, riel, mouse), Apariencia (el tema de la terminal; la cara del agente),
    Permisos (las dos opciones y su modelo), Usuarios (quién usa cada agente), Uso (su cuenta, si su motor lo dice) y
    Actualizaciones (tu versión).
  · Ayuda en grupos: Teclas y mouse, Comandos (los de `workspace`, de comandos.py), Documentación (el manual,
    manual/es) y Novedades (CHANGELOG.md).
  · Agentes con pestañas: Apariencia (cara, color, nombre), Tono (sus diales, /api/front/tono) y Quién lo usa
    (/api/sistema/usuarios); «+ Agregar».
  · Calendario: tu agenda (la misma fuente que el calendario de siempre: personal.py, por la página en
    /api/calendario; y Google si está encendido, gcal.py, solo lectura). Hecho y agregar, con personal.py (la página
    no escribe la agenda; el calendario de siempre tampoco pasa por ella).
Lo que no tiene de dónde salir lo dice: «en camino» o dónde se cambia hoy. Cada pieza dibuja en el marco M que le den
(xl, wl, y0..y1 para la lista; xd, wd, yd para el detalle). Stdlib."""
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_paleta as P  # noqa: E402
import hub_directo as D  # noqa: E402
import hub_bloque as B  # noqa: E402
import hub_secciones as S  # noqa: E402

C, ERR = P.C, P.ERR
W, corto = B.W, B.corto
TITULOS = dict(S.TITULOS, calendario="Calendario", conexiones="Conexiones")
H_LN = "#2c2c33"


# ── la lista genérica: grupos (encabezados) y filas que se eligen ─────────────
def _lista(L, s, M, sec, filas, linea2=True):
    """Filas {tipo: grupo, cat} | {rid, titulo, der, sub, dim}. Cada fila ocupa 2 renglones (1 sin sub)."""
    T = L.T
    a = B.agente(s)
    xl, wl = M["xl"], M["wl"]
    sel = S.elegida(sec, filas)
    L.reg(xl, M["y0"], wl, M["y1"] - M["y0"] + 1, "lista")
    altos = [1 if f.get("tipo") == "grupo" else (2 if (linea2 and f.get("sub")) else 1) for f in filas]
    k = next((n for n, f in enumerate(filas) if f.get("rid") == sel), 0)
    i0, i1 = S.ventana(altos, k, M["y1"] - M["y0"] + 1)
    yy = M["y0"]
    for f, h in zip(filas[i0:i1], altos[i0:i1]):
        if f.get("tipo") == "grupo":
            T.put(xl, yy, corto(f["cat"].upper(), wl), C["tx3"], True)
            yy += 1
            continue
        rid = f["rid"]
        on = rid == sel
        hov = L.reg(xl, yy, wl, h, "sr:" + rid)
        if on or hov or L.apr("sr:" + rid):
            T.fill(xl, yy, wl, h, B.P4 if L.apr("sr:" + rid) else (B.P3 if on else B.P2))
        if on:
            for j in range(h):
                T.put(xl, yy + j, "▌", a["c"])
        der = f.get("der") or ""
        T.put(xl + 2, yy, corto(f["titulo"], wl - 4 - (W(der) + 2 if der else 0)),
              C["tx3"] if f.get("dim") and not on else (C["tx"] if (on or hov) else C["tx2"]), on)
        if der:
            T.right(xl + wl - 2, yy, corto(der, max(4, wl // 2)), f.get("der_c") or C["tx3"])
        if h > 1:
            T.put(xl + 2, yy + 1, corto(f["sub"], wl - 4), C["tx3"])
        yy += h
    if i0 > 0:
        T.put(xl + wl - 1, M["y0"], "▲", C["tx2"])
    if i1 < len(filas):
        T.put(xl + wl - 1, M["y1"], "▼", C["tx2"])
    return sel


def _caja(L, M):
    """El detalle: un plano P2 a la derecha (o en lugar de la lista). → (T, x, y, w, alto, ix, iw)."""
    T = L.T
    x, w, y = M["xd"], M["wd"], M["yd"]
    alto = M["y1"] + 1 - y
    B.bloque(T, x, y, w, alto, B.P2, B.BG)
    L.reg(x, y, w, alto, "detalle")
    return T, x, y, w, alto, x + 3, w - 6


def _busca(sec, filas):
    """Lo que escribiste en la lista la filtra (type-to-search): las filas cuyo título o texto lo dicen."""
    q = P._sin_acentos((sec or {}).get("busca") or "").strip()
    if not q:
        return filas
    out, grupo, cat = [], None, ""
    for f in filas:
        if f.get("tipo") == "grupo":
            grupo, cat = f, P._sin_acentos(f.get("cat") or "")
            continue
        txt = P._sin_acentos(" ".join(str(f.get(k) or "") for k in ("titulo", "sub", "der"))) + " " + cat
        if q in txt:
            if grupo is not None:
                out.append(grupo)
                grupo = None
            out.append(f)
    return out


# ── Ajustes, en grupos ────────────────────────────────────────────────────────
def preferencias_locales():
    """El mismo inventario de Personalización del lanzador, leído fuera del dibujo."""
    import settings
    import tuitheme

    claves = [f["key"] for f in settings.hub_pins_resolved()]
    claves = dict.fromkeys(("ui.theme", "ui.background", "ui.brightness", "ui.redlight",
                           "ui.autostart", "ui.navegador_al_iniciar", "ui.un_color", *claves))
    filas = []
    for clave in claves:
        spec = settings._BY_KEY[clave]
        if spec["group"] in ("decisions", "decisores"):
            continue
        tipo = spec.get("type")
        if tipo == "enum":
            valores = settings._live_choices(spec)
        elif tipo == "bool":
            valores = (True, False)
        elif tipo == "int" and spec.get("range"):
            minimo, maximo = spec["range"]
            valores = range(minimo, maximo + 1)
        else:
            continue
        filas.append({"rid": "aj:" + clave, "titulo": settings.pin_label(clave),
                      "opciones": [(str(v), settings.pin_value_display(clave, v)) for v in valores],
                      "valores": {str(v): v for v in valores}, "actual": str(settings.get(clave)),
                      "nota": settings.help_text(clave), "preferencia": clave})
    tema = tuitheme.palette()
    return {"filas": filas, "fondo": (tema.OSC or {}).get("bg"),
            "motor": settings.get("modelos.default_engine")}


def ajustes_filas(s):
    """Los ajustes en sus grupos: [{tipo: grupo, cat} | {rid, titulo, opciones, actual, nota, dim, der}]."""
    a = B.agente(s)
    d = s.get("datos") or {}
    base = {f["rid"]: f for f in S.ajustes_filas(s)}
    out = []

    def g(cat):
        out.append({"tipo": "grupo", "cat": cat})

    def fila(f, der=None):
        f = dict(f)
        if der is None:
            der = dict(f.get("opciones") or []).get(f.get("actual")) or \
                (f.get("actual") or ("el de siempre" if f.get("opciones") else ""))
        f["der"], f["der_c"] = der, (C["tx3"] if f.get("dim") else a["c"])
        out.append(f)
    g("General")
    for r in ("aj:idioma", "aj:riel", "aj:mouse"):
        if r in base:
            fila(base[r])
    preferencias = (d.get("preferencias") or {}).get("filas") or []
    apariencia = {"ui.theme", "ui.background", "ui.brightness", "ui.redlight", "ui.un_color", "ui.tema_herdr"}
    for f in preferencias:
        if f["preferencia"] not in apariencia:
            fila(f)
    g("Apariencia")
    for f in preferencias:
        if f["preferencia"] in apariencia:
            fila(f)
    fila({"rid": "aj:cara", "titulo": "La cara y el color de %s" % a["n"], "opciones": [], "actual": "",
          "nota": "Se cambian en Agentes › Apariencia: Enter te lleva.", "ir": "agentes"}, der="Agentes ›")
    g("Permisos")
    for r in ("aj:perm", "aj:modelo", "aj:esfuerzo"):
        if r in base:
            fila(base[r])
    g("Usuarios")
    us = (d.get("usuarios") or {}).get("agentes")
    if us is None:
        out.append({"rid": "aj:us:" + str(a.get("id") or ""), "titulo": "Quién usa cada agente",
                    "opciones": [], "actual": "",
                    "nota": "Viendo los usuarios…" if "usuarios" in (s.get("cargando") or ()) else
                    ((s.get("errores") or {}).get("usuarios") or ""), "dim": True, "der": ""})
    for x in us or []:
        nombres = [u.get("nombre") for u in x.get("usuarios") or [] if u.get("nombre")]
        fila({"rid": "aj:us:" + str(x.get("agente")), "titulo": x.get("nombre") or x.get("agente"), "opciones": [],
              "actual": ", ".join(nombres) or "nadie todavía",
              "nota": "Gestionar los usuarios del agente.", "accion": "usuarios", "agente": x.get("agente"),
              "usuarios": x.get("usuarios") or []}, der=", ".join(nombres) or "nadie")
    g("Uso")
    u = d.get("uso:" + str(a.get("id")))
    if u is None:
        txt = "Viendo…" if ("uso:" + str(a.get("id"))) in (s.get("cargando") or ()) else ""
    elif not u.get("uso"):
        txt = "Su motor no lo dice" if u.get("motor") != "claude-code" else "Todavía sin datos"
    else:
        txt = _uso_txt(u["uso"])
    foto = s.get("foto") or {}
    if foto.get("uso"):
        cuenta = [txt] if (u or {}).get("uso") else []
        import hub_h1        # el uso de la conversación vive ahí (no en hub_bloque: Ajustes no abría, PC 23-nov)
        txt = " · ".join(cuenta + hub_h1._uso_conversacion(foto, foto.get("motor") or a.get("mid")))
    fila({"rid": "aj:uso", "titulo": "Uso de %s" % a["n"], "opciones": [], "actual": txt,
          "nota": "Cuenta y sesión, según lo que informa el motor.",
          "dim": True}, der=txt)
    g("Actualizaciones")
    info = d.get("info") or {}
    v = info.get("version") or ""
    fila({"rid": "aj:version", "titulo": "Workspace %s" % v if v else "Tu versión", "opciones": [], "actual": v,
          "nota": "Abre Actualizaciones para revisar, reparar o actualizar Workspace.",
          "accion": "actualizar"}, der=v or "…")
    g("Conexiones")                                   # H3-b: lo de adentro de cada motor (antes, junto a Motores)
    import hub_conexiones as CX
    est, txt = CX.linea(s)
    fila({"rid": "aj:cx", "titulo": "Estado por motor", "opciones": [], "actual": "",
          "nota": "Lo que Workspace conecta por dentro en cada motor (sus herramientas, sus avisos, sus skills, el "
                  "canal de la página y la protección). Se revisa sola al abrir, sin IA; aquí se ve y se arregla.",
          "accion": "rejilla"},
         der=txt.split(" ", 1)[0] if est else "…")
    if (s.get("seccion") or {}).get("kind") == "ajustes" and est in ("tuyo", "roto"):
        out[-1]["der_c"] = B.WARN if est == "tuyo" else CX.ERR
    for c in ((d.get("conexiones") or {}).get("conexiones") or []):
        if not c.get("nombre"):
            continue
        de_ws = bool(c.get("de_workspace"))
        mot = ", ".join(D.nombre_motor(x) for x in (c.get("motores") if de_ws else
                                                    (c.get("tuyos") or c.get("motores"))) or [])
        fila({"rid": "aj:mcp:" + str(c["nombre"]), "titulo": "MCP · %s%s" % (c["nombre"], " (de Workspace)" if de_ws
                                                                           else ""), "opciones": [],
              "actual": ("en " + mot) if mot else "en ningún motor todavía",
              "nota": ("Es de Workspace: lo pone en su propio perfil de ese motor." if de_ws else
                       ("Workspace la registra." if c.get("registrada") else "Workspace no la registra.") +
                       " Las conexiones se agregan y se quitan en la página (Conexiones)."),
              "dim": True, "mcp": c}, der=mot or "—")
    return _busca(s.get("seccion"), out)


GRUPOS_AJ = {"general": "General", "apariencia": "Apariencia", "permisos": "Permisos", "usuarios": "Usuarios",
             "uso": "Uso", "actualizaciones": "Actualizaciones", "conexiones": "Conexiones"}


def primera_del_grupo(s, grupo):
    """La primera fila del grupo de Ajustes (para abrirlo desde Inicio)."""
    cat, dentro = GRUPOS_AJ.get(grupo, ""), False
    for f in ajustes_filas(s):
        if f.get("tipo") == "grupo":
            dentro = f["cat"] == cat
        elif dentro and f.get("rid"):
            return f["rid"]
    return None


def primera_de_ayuda(sub):
    if sub == "teclas":
        return "ay:teclas"
    if sub == "comandos":
        return "ay:comandos"
    if sub == "docs":
        m = _manual()
        return "ay:doc:" + m[0][0] if m else None
    return "ay:nov:0"


def _uso_txt(u):
    partes = []
    for k, n in (("cinco", "5 h"), ("semana", "semana"), ("ventana_5h", "5 h"), ("semanal", "semana")):
        x = u.get(k)
        if isinstance(x, dict) and x.get("pct") is not None:
            partes.append("%s: %d%%" % (n, int(x["pct"])))
        elif isinstance(x, (int, float)):
            partes.append("%s: %d%%" % (n, int(x)))
    return " · ".join(partes) or "con datos"


def ajustes_lista(L, s, M, sec):
    T = L.T
    a = B.agente(s)
    q = sec.get("busca") or ""
    T.put(M["xl"], M["yt"] + 2, corto(("Buscando «%s» · Esc la borra" % q) if q else
                                       "Los de %s y los de Workspace. Escribe para buscar." % a["n"], M["wl"]),
          a["c"] if q else C["tx3"])
    _lista(L, s, M, sec, ajustes_filas(s), linea2=False)


def ajustes_detalle(L, s, M, sec):
    filas = ajustes_filas(s)
    sel = S.elegida(sec, filas)
    f = next((x for x in filas if x.get("rid") == sel), None)
    T, x, y, w, alto, ix, iw = _caja(L, M)
    if not f:
        S.parrafo(T, ix, y + 2, "Nada con «%s»." % (sec.get("busca") or ""), iw)
        return
    a = B.agente(s)
    T.put(ix, y + 1, corto(f["titulo"], iw), C["tx"], True)
    yy = y + 2
    if f.get("actual") and not f.get("opciones"):
        yy = S.parrafo(T, ix, yy, str(f["actual"]), iw,
                       a["c"] if not f.get("dim") else C["tx2"], 3) + 1
    yy = S.parrafo(T, ix, yy + 1, f.get("nota") or "", iw, C["tx3"], 4) + 1
    if f.get("accion") == "usuarios":
        usuarios_detalle(L, s, sec, T, ix, yy, iw, a, f.get("usuarios") or [])
        return
    if f.get("accion") == "rejilla":                  # Conexiones: cómo está cada motor y la rejilla a un clic
        conexiones_detalle(L, s, T, ix, yy, iw, y + alto, a)
        return
    if f.get("ir"):
        B.boton(L, s, ix, yy + 1, "Abrir Agentes ›", "acc:ir:" + f["ir"], B.P2, foco=True, wmin=iw, a=a)
        return
    if f.get("accion"):
        lab = "Abrir Actualizaciones ↗"
        B.boton(L, s, ix, min(yy + 1, y + alto - 4), lab, "acc:" + f["accion"], B.P2, foco=True, wmin=iw, a=a)
        return
    op = sec.get("op")
    opciones = f.get("opciones") or []
    paginar = len(opciones) > (y + alto - 1 - yy) // 3
    limite = y + alto - (4 if paginar else 1)
    visibles = max(1, (limite - yy) // 3)
    if paginar:
        B.boton(L, s, ix, limite, "‹ Anterior", "acc:op-ant", B.P2, a=a)
        B.boton(L, s, ix + 14, limite, "Siguiente ›", "acc:op-sig", B.P2, a=a)
    indice = next((i for i, (v, _t) in enumerate(opciones) if v == (op or f.get("actual"))), 0)
    inicio = min(max(0, indice - visibles + 1), max(0, len(opciones) - visibles))
    for v, t in opciones[inicio:]:
        if yy + 3 > limite:
            break
        actual = v == f.get("actual")
        B.boton(L, s, ix, yy, ("✓ " if actual else "") + t, "op:%s:%s" % (f["rid"][3:], v), B.P2,
                foco=actual and not f.get("dim"), apagado=bool(f.get("dim")), wmin=iw, a=a)
        if op == v and not actual and not f.get("dim"):
            T.put(ix - 2, yy + 1, "›", a["c"], True, B.P2)
        yy += 3


def conexiones_detalle(L, s, T, ix, yy, iw, y_fin, a):
    """Ajustes › Conexiones › Estado por motor (el chequeo rápido): una línea por motor (✓ · ⚠ · ✗ con cuántas cosas),
    cuándo se revisó, «Ver por dentro ›» (la sección Conexiones completa) y «↻ Revisar ahora» (sin IA)."""
    import hub_conexiones as CX
    hay, por_motor, n = CX.resumen(s)
    if not hay:
        T.put(ix, yy, "Revisando cómo está Workspace en cada motor (sin IA)…", C["tx3"])
        yy += 2
    else:
        est, txt = CX.linea(s)
        T.put(ix, yy, txt + ("" if est == "ok" else " · lo demás bien"),
              {"ok": B.OK, "tuyo": B.WARN, "roto": CX.ERR}.get(est, C["tx3"]), True)
        yy += 2
        for mid, nom, k in por_motor:
            if yy >= y_fin - 8:
                break
            g, col = CX.verde(CX.estado_de(s, mid))
            T.put(ix, yy, g, col, True)
            T.put(ix + 2, yy, corto(nom, iw - 22), C["tx"] if k else C["tx2"])
            T.right(ix + iw, yy, ("%d por hacer" % k if CX.estado_de(s, mid) == "tuyo" else
                                  ("%d rota" if k == 1 else "%d rotas") % k) if k else "bien", col if k else C["tx3"])
            yy += 1
        d = CX.chequeo(s) or {}
        cuando = "Revisando ahora…" if d.get("revisando") else (("Revisado al abrir " + d["hace"]) if d.get("hace")
                                                                 else "")
        if cuando:
            T.put(ix, yy + 1, corto(cuando, iw), C["tx3"])
    yb = max(yy + 3, y_fin - 4)
    xb = B.boton(L, s, ix, yb, "Ver por dentro ›", "acc:rejilla", B.P2, foco=True, wmin=(iw - 1) // 2, a=a)
    B.boton(L, s, xb + 1, yb, "↻ Revisar ahora", "acc:verificar_cx", B.P2, wmin=iw - (xb + 1 - ix), a=a)


def usuarios_detalle(L, s, sec, T, ix, yy, iw, a, filas):
    edit = sec.get("usuario_edicion")
    if edit:
        T.put(ix, yy, edit["titulo"], C["tx"], True)
        T.put(ix, yy + 1, corto(("❯ " + sec.get("buf", "") + "▏") if sec.get("editando")
                                else edit["nota"], iw), C["tx2"])
        if sec.get("error"):
            T.put(ix, yy + 2, corto(sec["error"], iw), ERR)
        B.boton(L, s, ix, yy + 3, "Confirmar", "acc:usuario:guardar", B.P2, a=a)
        B.boton(L, s, ix + 14, yy + 3, "Cancelar", "acc:usuario:cancelar", B.P2, a=a)
        return

    indice = min(sec.get("usuario_i", 0), max(0, len(filas) - 1))
    u = filas[indice] if filas else None
    if u:
        T.put(ix, yy, corto("%s%s · %d/%d" % (u["nombre"], " · tú" if u.get("yo") else "",
                                            indice + 1, len(filas)), iw), C["tx"], True)
        if len(filas) > 1:
            B.boton(L, s, ix, yy + 1, "‹ Anterior", "acc:usuario:anterior", B.P2, a=a)
            B.boton(L, s, ix + 14, yy + 1, "Siguiente ›", "acc:usuario:siguiente", B.P2, a=a)
        B.boton(L, s, ix, yy + 4, "Renombrar", "acc:usuario:renombrar", B.P2, a=a)
        B.boton(L, s, ix + 14, yy + 4, "Soy yo", "acc:usuario:soy", B.P2, a=a)
        if len(filas) > 1:
            B.boton(L, s, ix + 14, yy + 7, "Unir", "acc:usuario:unir", B.P2, a=a)
    B.boton(L, s, ix, yy + 7 if u else yy, "Crear", "acc:usuario:crear", B.P2, a=a)


# ── Ayuda, en grupos ──────────────────────────────────────────────────────────
#: Las teclas, por dónde estás (el modelo de foco: Tab cambia de área, las flechas se mueven adentro, Enter hace lo
#: enfocado, Esc regresa un nivel). Lo mismo que dice el borde de abajo de cada área.
TECLAS = (
    ("En todas partes", (("Tab", "otra área (Shift-Tab: la de antes)"), ("↑↓←→", "dentro del área"),
                         ("Enter", "lo enfocado (lo que tiene ▐ ▌)"), ("Esc", "regresa un nivel"),
                         ("q", "sale (fuera de la caja de escribir)"), ("F1", "esta ayuda"), ("^C", "sale"))),
    ("Inicio", (("←→", "otro agente (llega deslizándose)"), ("↑↓", "su motor (el selector ▲▼ de su tarjeta)"),
                ("Enter", "conversar, o lo que necesite su motor (p. ej. iniciar sesión)"),
                ("s", "sus sesiones (su programa oficial)"), ("n", "la versión del navegador"),
                ("Tab", "las secciones (Esc: de vuelta a la tarjeta)"), ("letras", "buscan un agente o una sección"),
                ("/", "buscar (aunque sea s, n o q)"), ("1-9", "ese agente, directo"))),
    ("Las secciones de Inicio", (("←→", "otra sección"), ("↓", "sus partes (General, Tono…)"), ("↑", "de vuelta"),
                                 ("Enter", "la abre"))),
    ("Agentes › Tablero", (("←→", "el agente (la columna)"), ("↑↓", "el motor (la fila)"),
                           ("Enter", "lo del cruce: conversar, usarlo o iniciar sesión"))),
    ("Conexiones", (("←→↑↓", "la celda (la pieza y el motor)"), ("Enter", "toda su evidencia"),
                    ("v", "verifica ese motor de verdad"), ("V", "verifica todos"),
                    ("r", "lo repara por el camino oficial (su guía antes)"))),
    ("La caja de escribir", (("letras", "todo es texto: ningún atajo"), ("Enter", "manda (o contesta)"),
                             ("Esc", "borra; sin texto para al que trabaja; si no, sale de la caja"),
                             ("/", "sus skills (con la caja vacía)"), ("AvPág", "la conversación"))),
    ("La conversación", (("↑↓", "la conversación (lo de antes)"), ("^E", "su motor"), ("^S", "sus sesiones (S-1)"),
                         ("^O", "abrir en su motor"),
                         ("^B", "el riel con nombres"), ("1-9", "otro agente (fuera de la caja)"))),
    ("Sus pestañas", (("^T", "otra: nueva o una de sus sesiones"), ("^W", "cierra la que ves (no se borra)"),
                      ("^←→", "la de al lado"), ("Alt 1-9", "esa pestaña, directo"))),
    ("El riel", (("↑↓", "otro agente"), ("←→", "su motor"), ("Enter", "a su caja de escribir"),
                 ("letras", "saltan al agente que empieza así"))),
    ("Listas y secciones", (("letras", "filtran la lista"), ("↑↓", "lo elegido"),
                            ("←→", "filtros u opciones"), ("Enter", "lo hace"))),
)


def _manual():
    """[(archivo, título, primer párrafo)] del manual en español (manual/es)."""
    out = []
    raiz = os.path.join(AQUI, "manual", "es")
    try:
        nombres = sorted(n for n in os.listdir(raiz) if n.endswith(".md") and n != "README.md")
    except OSError:
        return out
    for n in nombres:
        try:
            with open(os.path.join(raiz, n), encoding="utf-8") as fh:
                txt = fh.read(4000)
        except OSError:
            continue
        titulo = next((ln.lstrip("# ").strip() for ln in txt.splitlines() if ln.startswith("#")), n[:-3])
        parrafo = next((ln.strip() for ln in txt.split("\n\n")[1:] if ln.strip() and not ln.startswith("#")), "")
        out.append((n, titulo, re.sub(r"[`*_\[\]]", "", " ".join(parrafo.split()))[:400]))
    return out


def _novedades(n=6):
    """[(versión y fecha, [lo nuevo])] de CHANGELOG.md."""
    out = []
    try:
        with open(os.path.join(AQUI, "CHANGELOG.md"), encoding="utf-8") as fh:
            txt = fh.read(60000)
    except OSError:
        return out
    for bloque in re.split(r"\n## ", "\n" + txt)[1:n + 1]:
        cab, _s, cuerpo = bloque.partition("\n")
        puntos = [re.sub(r"[`*_]", "", m).strip() for m in re.findall(r"^- \*\*(.+?)\*\*", cuerpo, re.M)]
        out.append((cab.strip(), puntos[:8]))
    return out


def _comandos():
    try:
        import comandos as CM
        return [(CM.display_name(c), CM.usage_of(c) if hasattr(CM, "usage_of") else "", CM.summary_of(c))
                for c in CM.visible(dev=False)]
    except Exception:
        return []


def ayuda_filas(s):
    out = [{"tipo": "grupo", "cat": "Teclas y mouse"},
           {"rid": "ay:teclas", "titulo": "Las teclas", "sub": "por dónde estás"}]
    if s.get("raton_posible"):
        out.append({"rid": "acc:mouse", "titulo": "Apagar el mouse" if s.get("raton") else "Prender el mouse",
                    "sub": "apagado, la terminal selecciona texto"})
    out += [{"rid": "acc:riel", "titulo": "Solo los monitos" if s.get("riel_nombres") else "Los nombres en el riel",
             "sub": "también ^B o arrastrando su borde"},
            {"tipo": "grupo", "cat": "Comandos"},
            {"rid": "ay:comandos", "titulo": "Lo que escribes en la terminal", "sub": "los de `workspace`"},
            {"tipo": "grupo", "cat": "Documentación"}]
    out += [{"rid": "ay:doc:" + n, "titulo": t, "sub": ""} for n, t, _p in _manual()]
    out += [{"tipo": "grupo", "cat": "Novedades"}]
    out += [{"rid": "ay:nov:%d" % k, "titulo": cab, "sub": ""} for k, (cab, _p) in enumerate(_novedades())]
    return _busca(s.get("seccion"), out)


def ayuda_lista(L, s, M, sec):
    T = L.T
    q = sec.get("busca") or ""
    T.put(M["xl"], M["yt"] + 2, corto(("Buscando «%s» · Esc la borra" % q) if q else
                                       "Teclas, comandos, el manual y lo nuevo. Escribe para buscar.", M["wl"]),
          B.agente(s)["c"] if q else C["tx3"])
    _lista(L, s, M, sec, ayuda_filas(s), linea2=False)


def ayuda_detalle(L, s, M, sec):
    filas = ayuda_filas(s)
    sel = S.elegida(sec, filas)
    T, x, y, w, alto, ix, iw = _caja(L, M)
    a = B.agente(s)
    y_fin = y + alto - 1
    if sel == "ay:teclas":
        T.put(ix, y + 1, "Las teclas", C["tx"], True)
        yy = y + 3
        for grupo, ks in TECLAS:
            if yy >= y_fin - 1:
                break
            T.put(ix, yy, grupo.upper(), C["tx3"], True)
            yy += 1
            for k, txt in ks:
                if yy >= y_fin:
                    break
                T.key(ix, yy, k)
                D._linea_corta(T, ix + 9, yy, [(txt, C["tx2"], False)], ix + iw)
                yy += 1
            yy += 1
    elif sel in ("acc:mouse", "acc:riel"):
        f = next(f for f in filas if f.get("rid") == sel)
        T.put(ix, y + 1, f["titulo"], C["tx"], True)
        S.parrafo(T, ix, y + 3, f["sub"].capitalize() + ".", iw)
        B.boton(L, s, ix, y + 6, f["titulo"], sel, B.P2, foco=True, wmin=iw, a=a)
    elif sel == "ay:comandos":
        T.put(ix, y + 1, "Lo que escribes en la terminal", C["tx"], True)
        yy = y + 3
        for nom, uso, txt in _comandos():
            if yy >= y_fin:
                break
            T.put(ix, yy, corto(uso or nom, iw // 2), a["c"], True)
            D._linea_corta(T, ix + iw // 2 + 1, yy, [(txt, C["tx2"], False)], ix + iw)
            yy += 1
        if yy == y + 3:
            T.put(ix, yy, "No pude leer la lista de comandos.", C["tx3"])
    elif sel.startswith("ay:doc:"):
        n = sel[7:]
        doc = next((d for d in _manual() if d[0] == n), (n, n, ""))
        T.put(ix, y + 1, corto(doc[1], iw), C["tx"], True)
        S.parrafo(T, ix, y + 3, doc[2] or "", iw, C["tx2"], 8)
        B.boton(L, s, ix, y_fin - 3, "Leerla en la página ↗", "acc:pagina", B.P2, foco=True, wmin=iw, a=a)
    elif sel.startswith("ay:nov:"):
        k = int(sel[7:])
        nov = _novedades()
        cab, puntos = nov[k] if k < len(nov) else ("", [])
        T.put(ix, y + 1, corto(cab, iw), C["tx"], True)
        yy = y + 3
        for p_ in puntos:
            for ln in D.envolver([("· " + p_, C["tx2"], False)], iw)[:2]:
                if yy >= y_fin:
                    break
                D._linea(T, ix, yy, ln, ix + iw)
                yy += 1


# ── Agentes, con sus pestañas ─────────────────────────────────────────────────
PESTANAS = (("apariencia", "Apariencia"), ("tono", "Tono"), ("usuarios", "Quién lo usa"),
            ("maquina", "Esta máquina"))


def agentes_detalle(L, s, M, sec):
    """La pestaña elegida del agente elegido: Apariencia (la de antes), Tono, Quién lo usa o Esta máquina (en el hub,
    la ruta de su cerebro, quitarlo: hub_agentes_maquina)."""
    import hub_agentes_maquina as HM
    T = L.T
    tab = sec.get("tab") or "apariencia"
    filas = S.agentes_filas(s)
    sel = S.elegida(sec, filas)
    x, w, y = M["xd"], M["wd"], M["yd"]
    M2 = dict(M, yd=HM.pestanas(L, x, y, w, PESTANAS, tab))     # si no caben en una fila, en dos
    if tab == HM.TAB:
        HM.detalle(L, s, M2, sec, sel[3:] if sel.startswith("ag:") else "")
        return
    if tab == "apariencia" or not sel.startswith("ag:"):
        S.agentes_detalle(L, s, M2, sec)
        return
    aid = sel[3:]
    _i, b = S._por_id(s, aid)
    b = b or B.agente(s)
    T, x, y2, w, alto, ix, iw = _caja(L, M2)
    if tab == "tono":
        d = (s.get("datos") or {}).get("tono:" + aid)
        T.put(ix, y2 + 1, "El tono de %s" % b["n"], C["tx"], True)
        if not d:
            T.put(ix, y2 + 3, "Viendo su tono…" if ("tono:" + aid) in (s.get("cargando") or ()) else
                  ((s.get("errores") or {}).get("tono:" + aid) or "Sin datos."), C["tx3"])
            return
        if "/api/front/tono" in (s.get("sin_ruta") or ()):
            T.put(ix, y2 + 2, "Cambiarlo desde aquí: esta página no lo deja todavía.", C["tx3"])
        yy = y2 + 3
        niveles = d.get("niveles") or {}
        for dial in d.get("diales") or []:
            if yy >= y2 + alto - 2:
                break
            k = dial.get("key")
            n = int(niveles.get(k) or 3)
            T.put(ix, yy, corto(dial.get("label") or k, 14), C["tx2"])
            xc = ix + 15
            for v in range(1, 6):
                rid = "tono:%s:%d" % (k, v)
                hov = L.reg(xc, yy, 2, 1, rid)
                T.put(xc, yy, "●" if v <= n else "○", b["c"] if v <= n else (C["tx"] if hov else C["tx3"]), v == n,
                      B.P4 if hov else B.P2)
                xc += 2
            eje = dial.get("eje") or []
            if len(eje) == 2 and xc + 3 < ix + iw:
                D._linea_corta(T, xc + 2, yy, [("%s ↔ %s" % (eje[0], eje[1]), C["tx3"], False)], ix + iw)
            yy += 1
        if d.get("estilo") and yy + 1 < y2 + alto - 1:
            T.put(ix, yy + 1, corto("Estilo: " + d["estilo"], iw), C["tx3"])
    else:
        us = next((x_ for x_ in ((s.get("datos") or {}).get("usuarios") or {}).get("agentes") or []
                   if x_.get("agente") == aid), None)
        T.put(ix, y2 + 1, "Quién usa a %s" % b["n"], C["tx"], True)
        if us is None:
            T.put(ix, y2 + 3, "Viendo los usuarios…" if "usuarios" in (s.get("cargando") or ()) else "Sin datos.",
                  C["tx3"])
            return
        yy = y2 + 3
        for u in us.get("usuarios") or []:
            T.put(ix, yy, "· " + corto(u.get("nombre") or "", iw - 16), C["tx"])
            T.right(ix + iw, yy, corto(u.get("id") or "", 14), C["tx3"])
            yy += 1
        B.boton(L, s, ix, y2 + alto - 4, "Gestionar usuarios ›", "acc:usuarios", B.P2, a=b)


# ── Calendario ────────────────────────────────────────────────────────────────
VISTAS_CAL = (("mes", "Mes"), ("semana", "Semana"))
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
DIAS_C = ("lu", "ma", "mi", "ju", "vi", "sá", "do")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")
HORAS = range(8, 21)


def _fecha(dstr):
    try:
        return time.strptime(dstr, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _d(dstr):
    import datetime as dt
    try:
        return dt.date(*time.strptime(dstr, "%Y-%m-%d")[:3])
    except (TypeError, ValueError):
        return dt.date.today()


def dia_elegido(sec):
    """El día elegido del calendario (sec["sel"] = «dia:AAAA-MM-DD»; si no, hoy)."""
    import datetime as dt
    sel = str((sec or {}).get("sel") or "")
    return _d(sel[4:]) if sel.startswith("dia:") else dt.date.today()


def mover_dia(sec, dias=0, meses=0):
    import datetime as dt
    d = dia_elegido(sec)
    if meses:
        m = d.month - 1 + meses
        y, m = d.year + m // 12, m % 12 + 1
        ult = (dt.date(y + (m // 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day
        d = dt.date(y, m, min(d.day, ult))
    sec["sel"] = "dia:" + (d + dt.timedelta(days=dias)).isoformat()


def calendario_eventos(s):
    """Los eventos (de la página: /api/calendario; y los de Google si está encendido), ordenados."""
    d = s.get("datos") or {}
    evs = [dict(e, fuente="local") for e in (d.get("calendario") or {}).get("eventos") or []]
    evs += [dict(e, fuente="google", id="g:%s" % e.get("id", ""), done=False)
            for e in (d.get("calendario_g") or [])]
    q = P._sin_acentos((s.get("seccion") or {}).get("busca") or "").strip()
    if q:
        evs = [e for e in evs if q in P._sin_acentos("%s %s" % (e.get("title"), e.get("cat")))]
    return sorted(evs, key=lambda e: (str(e.get("date") or ""), str(e.get("time") or "99"), str(e.get("title"))))


def _por_dia(s):
    out = {}
    for e in calendario_eventos(s):
        out.setdefault(str(e.get("date") or ""), []).append(e)
    return out


def _semanas(d):
    """Las semanas (lunes a domingo) del mes de `d`: [[date × 7]]."""
    import datetime as dt
    uno = d.replace(day=1)
    ini = uno - dt.timedelta(days=uno.weekday())
    out = []
    while True:
        sem = [ini + dt.timedelta(days=k) for k in range(7)]
        out.append(sem)
        ini += dt.timedelta(days=7)
        if ini.month != d.month or len(out) >= 6:
            break
    return out


def calendario_rids(s):
    """Los días que se eligen (el elegido primero): «dia:AAAA-MM-DD»."""
    d = dia_elegido(s.get("seccion"))
    dias = [x for sem in _semanas(d) for x in sem]
    return ["dia:" + d.isoformat()] + ["dia:" + x.isoformat() for x in dias if x != d]


def calendario_lista(L, s, M, sec):
    """El mes en una cuadrícula (o la semana en bloques de hora): hoy en el color del agente, los días con algo con
    sus puntos, el elegido en P3 con la ┃ del agente. Se elige con ←→↑↓ (o el mouse); Enter va a su agenda."""
    import datetime as dt
    T = L.T
    a = B.agente(s)
    vista = sec.get("filtro") if sec.get("filtro") in dict(VISTAS_CAL) else "mes"
    d = dia_elegido(sec)
    hoy = dt.date.today()
    xl, wl, yt = M["xl"], M["wl"], M["yt"]
    xx = xl
    for k, lab in VISTAS_CAL:
        xx = B.chip(L, xx, yt + 2, " %s " % lab, "fil:" + k, activo=vista == k) + 1
    xx += 2
    xx = B.chip(L, xx, yt + 2, " ‹ ", "fil:ant") + 1
    titulo = ("%s %d" % (MESES[d.month - 1], d.year)) if vista == "mes" else (
        "semana del %d de %s" % ((d - dt.timedelta(days=d.weekday())).day, MESES[d.month - 1]))
    xx = T.put(xx + 1, yt + 2, titulo, C["tx"], True) + 1
    xx = B.chip(L, xx, yt + 2, " › ", "fil:sig") + 2
    B.chip(L, xx, yt + 2, " Hoy ", "fil:hoy")
    if sec.get("busca"):
        T.right(xl + wl, yt + 2, corto("«%s»" % sec["busca"], 20), a["c"])
    L.reg(xl, M["y0"], wl, M["y1"] - M["y0"] + 1, "lista")
    por_dia = _por_dia(s)
    y0, y1 = M["y0"], M["y1"]
    cw = max(5, min(16, wl // 7))
    if vista == "mes":
        for k, dn in enumerate(DIAS_C):
            T.put(xl + k * cw + 1, y0, dn, C["tx3"], True)
        sems = _semanas(d)
        chh = max(2, min(4, (y1 - y0) // len(sems)))
        for f, sem in enumerate(sems):
            for c, dia in enumerate(sem):
                x, y = xl + c * cw, y0 + 1 + f * chh
                if y + chh - 1 > y1:
                    break
                rid = "sr:dia:" + dia.isoformat()
                hov = L.reg(x, y, cw - 1, chh, rid)
                on = dia == d
                fondo = B.P3 if on else (B.P2 if hov else B.BG)
                if on or hov:
                    T.fill(x, y, cw - 1, chh, fondo)
                if on:
                    for j in range(chh):
                        T.put(x, y + j, "▌", a["c"], False, fondo)
                fuera = dia.month != d.month
                num = "%2d" % dia.day
                if dia == hoy:
                    T.put(x + 1, y, " %s " % num.strip(), B.LUZTX, True, a["c"])
                else:
                    T.put(x + 1, y, num, C["tx3"] if fuera else (C["tx"] if on else C["tx2"]), on)
                evs = por_dia.get(dia.isoformat()) or []
                if evs:
                    pend = [e for e in evs if not e.get("done")]
                    marcas = "•" * min(3, len(pend)) + ("✓" if len(pend) < len(evs) else "")
                    T.put(x + 1, y + 1 if chh > 1 else y, marcas, a["c"] if pend else C["tx3"], True, fondo)
                    if chh > 2 and pend and cw > 8:
                        T.put(x + 1, y + 2, corto(str(pend[0].get("title") or ""), cw - 3), C["tx3"], False, fondo)
                if chh > 3 and not on:                # la raya de la semana (la cuadrícula se lee como calendario)
                    T.put(x, y + chh - 1, "─" * (cw - 1), H_LN, False, fondo)
    else:                                             # la semana, en bloques de hora
        ini = d - dt.timedelta(days=d.weekday())
        horas = [hh for hh in HORAS][:max(1, y1 - y0 - 2)]
        T.put(xl, y0 + 1, "todo el día", C["tx3"])
        cx0 = xl + 6
        cw = max(5, (wl - 6) // 7)
        for c in range(7):
            dia = ini + dt.timedelta(days=c)
            x = cx0 + c * cw
            rid = "sr:dia:" + dia.isoformat()
            hov = L.reg(x, y0, cw - 1, y1 - y0 + 1, rid)
            on = dia == d
            if on or hov:
                T.fill(x, y0, cw - 1, y1 - y0 + 1, B.P3 if on else B.P2)
            cab = "%s %d" % (DIAS_C[c], dia.day)
            if dia == hoy:
                T.put(x, y0, " %s " % cab, B.LUZTX, True, a["c"])
            else:
                T.put(x + 1, y0, cab, C["tx"] if on else C["tx2"], on)
            evs = por_dia.get(dia.isoformat()) or []
            sin_hora = [e for e in evs if not e.get("time")]
            if sin_hora:
                T.put(x + 1, y0 + 1, corto("▪ " + str(sin_hora[0].get("title")), cw - 2), a["c"], False)
            for e in evs:
                if not e.get("time"):
                    continue
                try:
                    hh = int(str(e["time"]).split(":")[0])
                except ValueError:
                    continue
                if hh in horas:
                    y = y0 + 2 + horas.index(hh)
                    bg = C["tx3"] if e.get("done") else P.mix(a["c"], B.BG, 0.45)
                    T.put(x, y, corto(" %s %s" % (e["time"], e.get("title") or ""), cw - 1).ljust(cw - 1),
                          B.LUZTX if not e.get("done") else C["tx2"], False, bg)
        for k, hh in enumerate(horas):
            if y0 + 2 + k <= y1:
                T.put(xl, y0 + 2 + k, "%02d:00" % hh, C["tx3"])


def calendario_detalle(L, s, M, sec):
    """La agenda del día elegido: sus cosas (Enter o clic: ✓ hecho / otra vez pendiente) y «+ Agregar» a ese día."""
    import datetime as dt
    a = B.agente(s)
    T, x, y, w, alto, ix, iw = _caja(L, M)
    d = dia_elegido(sec)
    if sec.get("editando") in ("nuevo", "editar"):
        titulo = "Editar evento" if sec["editando"] == "editar" else "Agregar al %s %d" % (DIAS[d.weekday()], d.day)
        T.put(ix, y + 1, titulo, C["tx"], True)
        S.parrafo(T, ix, y + 2, "Escribe: «10:00 Llamar al contador», «Pagar la luz», o con su día: «mañana 9:30 "
                                "Revisión», «2026-11-24 Demo». Enter la guarda; Esc cancela.", iw, C["tx3"], 3)
        B.bloque(T, ix, y + 6, iw, 3, B.P3, B.P2)
        xx = T.put(ix + 2, y + 7, "❯", a["c"], True, B.P3)
        xx = T.put(xx + 1, y + 7, corto(sec.get("buf") or "", iw - 6), C["tx"], False, B.P3)
        T.put(xx, y + 7, "▏", C["tx"], False, B.P3)
        if sec.get("error"):
            T.put(ix, y + 10, corto(sec["error"], iw), ERR)
        B.boton(L, s, ix, min(y + 11, y + alto - 4), "Guardar", "acc:guardar", B.P2, a=a)
        B.boton(L, s, ix + 13, min(y + 11, y + alto - 4), "Cancelar", "acc:cancelar-edicion", B.P2, a=a)
        return
    if sec.get("borrar"):
        e = sec["borrar"]
        T.put(ix, y + 1, corto("¿Borrar «%s»?" % e["title"], iw), C["tx"], True)
        B.boton(L, s, ix, y + 3, "Cancelar", "acc:cancelar-borrado", B.P2, a=a)
        B.boton(L, s, ix, y + 6, "Borrar", "acc:confirmar-borrado:%s" % e["id"], B.P2, a=a)
        return
    hoy = dt.date.today()
    T.put(ix, y + 1, corto("%s %d de %s" % (DIAS[d.weekday()].capitalize(), d.day, MESES[d.month - 1]), iw - 6),
          C["tx"], True)
    if d == hoy:
        T.put(ix + iw - 5, y + 1, " Hoy ", B.LUZTX, True, a["c"])
    evs = _por_dia(s).get(d.isoformat()) or []
    yy = y + 3
    if not evs:
        car = "calendario" in (s.get("cargando") or ())
        T.put(ix, yy, "Viendo tu agenda…" if car else "Nada este día.", C["tx3"])
    sin = "personal" in (s.get("sin_agenda") or ())
    for e in evs:
        if yy >= y + alto - 5:
            break
        hecho = bool(e.get("done"))
        google = e.get("fuente") == "google"
        rid = None if google or sin else "acc:hecho:%s" % e.get("id")
        zona = max(8, iw - 15) if rid else iw
        hov = L.reg(ix - 1, yy, zona + 1, 1, rid) if rid else False
        if hov:
            T.fill(ix - 1, yy, iw + 2, 1, B.P3)
        T.put(ix, yy, "✓" if hecho else ("·" if google else "○"), a["c"] if not hecho else C["tx3"], True)
        xx = T.put(ix + 2, yy, (e.get("time") or "").ljust(6), C["tx3"])
        T.put(xx, yy, corto(str(e.get("title") or ""), max(0, ix + zona - xx - (9 if google else 0))),
              C["tx3"] if hecho else (C["tx"] if hov else C["tx2"]), False)
        if google:
            T.right(ix + iw, yy, "Google", C["tx3"])
        elif rid:
            for dx, etiqueta, accion in ((14, "Editar", "editar"), (7, "Borrar", "borrar")):
                bx = ix + iw - dx
                foco = L.reg(bx, yy, len(etiqueta), 1, "acc:%s:%s" % (accion, e["id"]))
                T.put(bx, yy, etiqueta, a["c"] if foco else C["tx2"], foco, B.P3 if foco else B.P2)

        yy += 1
    if evs and yy < y + alto - 5:
        T.put(ix, yy + 1, corto("Enter o clic: ✓ hecho (otra vez: pendiente).", iw), C["tx3"])
    B.boton(L, s, ix, y + alto - 4, "+ Agregar a este día", "acc:agregar", B.P2, apagado=sin, wmin=iw, a=a)


# ── el registro de H-1 ────────────────────────────────────────────────────────
SECCIONES = dict(S.SECCIONES)
# ── Agentes › Tablero (R-3): una columna por agente y una fila por motor; el cursor es un cruce ────────────
VISTAS_AG = (("lista", "Lista"), ("tablero", "Tablero"))


def _motores(s):
    return ((s.get("datos") or {}).get("motores") or {}).get("motores")


def tablero_cursor(s, sec):
    """→ (agente, motor elegido en el tablero) o (None, None). El motor, si no lo eligió con ↑↓: el que usa."""
    filas = S.agentes_filas(s)
    sel = S.elegida(sec, filas)
    _i, b = S._por_id(s, sel[3:]) if str(sel).startswith("ag:") else (None, None)
    if not b:
        return None, None
    ms = _motores(s) or []
    mid = sec.get("mot") if any(m.get("id") == sec.get("mot") for m in ms) else (b.get("motor") or b.get("mid"))
    return b, mid


def tablero_accion(s, b, mid):
    """Lo que hace Enter en el cruce: (etiqueta, clave). conversar · usar · login · instalar · revisar."""
    import hub_inicio as I
    m = next((x for x in _motores(s) or () if x.get("id") == mid), None)
    actual = b.get("motor") or b.get("mid")
    if m is None or (mid == actual and I.usable(m)):
        return "Conversar con %s  ↵" % b["n"], "conversar"
    if I.usable(m):
        return "Usar %s con %s  ↵" % (D.nombre_motor(mid), b["n"]), "usar"
    k = I.accion(dict(s, ini_motor={b["id"]: mid}), b)[2]
    return {"login": ("Iniciar sesión  ↵", "login"), "instalar": ("Cómo instalarlo  ↵", "instalar")}.get(
        k, ("Revisarlo  ↵", "revisar"))


def tablero(L, s, M, sec):
    """El tablero en el lugar de la lista: los monitos arriba (←→ el agente), los motores en filas (↑↓), un ● donde
    cada uno trabaja y el cruce elegido con ▐ ▌ del color del agente."""
    import hub_inicio as I
    T = L.T
    xl, wl, y0, y1 = M["xl"], M["wl"], M["y0"], M["y1"]
    filas = S.agentes_filas(s)
    ag = s.get("agentes") or []
    ms = _motores(s)
    L.reg(xl, y0, wl, y1 - y0 + 1, "lista")
    if not filas:
        T.put(xl + 2, y0 + 1, "Ningún agente dice «%s»." % (sec.get("busca") or ""), C["tx3"])
        return
    if ms is None:
        T.put(xl + 2, y0 + 1, "Viendo cómo está cada motor…", C["tx3"])
        return
    b_sel, mid_sel = tablero_cursor(s, sec)
    ids = [f["i"] for f in filas]
    k_sel = next((n for n, f in enumerate(filas) if ag[f["i"]]["id"] == (b_sel or {}).get("id")), 0)
    foco = s.get("foco_area") == "lista"
    lw, colw, der = 18, 7, 15
    cab = max(1, min(len(ids), (wl - lw - der - 4) // colw))
    i0 = max(0, min(k_sel - cab // 2, len(ids) - cab))
    cx0 = xl + lw
    y_mot = y0 + 5
    paso = 2 if (y1 - y_mot + 1) >= 2 * len(ms) else 1
    j_sel = next((j for j, m in enumerate(ms) if m.get("id") == mid_sel), 0)
    col_x = cx0 + (k_sel - i0) * colw
    alto_col = min(y1, y_mot + paso * (len(ms) - 1)) - y0 + 1
    T.fill(col_x, y0, colw, alto_col, B.P2)
    yc = y_mot + j_sel * paso
    if yc <= y1:
        T.fill(xl, yc, wl, 1, B.P2)
        T.fill(col_x, yc, colw, 1, B.P3)
    if i0 > 0:
        hov = L.reg(cx0 - 4, y0 + 1, 4, 3, "tcol:atras")
        T.put(cx0 - 3, y0 + 2, "‹%d" % i0, C["tx"] if hov else C["tx3"])
    if i0 + cab < len(ids):
        hov = L.reg(cx0 + cab * colw, y0 + 1, 4, 3, "tcol:mas")
        T.put(cx0 + cab * colw, y0 + 2, "%d›" % (len(ids) - i0 - cab), C["tx"] if hov else C["tx3"])
    for k in range(i0, i0 + cab):
        a = ag[ids[k]]
        on = k == k_sel
        xx = cx0 + (k - i0) * colw
        L.reg(xx, y0, colw, 4, "sr:ag:" + a["id"])
        import hub_monitos as MON
        MON.dibujar(T, a, xx + (colw - 6) // 2, y0, 6, s=s, st=a.get("st"))
        T.center(xx, colw, y0 + 3, corto(a["n"], colw - 1), a["c"] if on else C["tx2"], on)
        mia = a.get("motor") or a.get("mid")
        for j, m in enumerate(ms):
            ry = y_mot + j * paso
            if ry > y1:
                break
            L.reg(xx, ry, colw, 1, "celda:%s:%s" % (a["id"], m.get("id")))
            fondo = T.at(xx + 3, ry).bg
            if m.get("id") == mia:
                T.put(xx + 3, ry, "●", a["c"], True, fondo)
            else:
                T.put(xx + 3, ry, "·", C["tx3"] if I.usable(m) else "#34343c", False, fondo)
            if on and j == j_sel:
                T.put(xx + 1, ry, "▐", a["c"] if foco else LN2_, False, B.P3)
                T.put(xx + colw - 2, ry, "▌", a["c"] if foco else LN2_, False, B.P3)
    for j, m in enumerate(ms):
        ry = y_mot + j * paso
        if ry > y1:
            break
        g, txt, col = I.estado_motor(m)
        on = j == j_sel
        fondo = T.at(xl + 2, ry).bg
        hov = L.reg(xl, ry, lw - 1, 1, "trow:" + str(m.get("id")))
        T.put(xl + 2, ry, corto(m.get("nombre") or D.nombre_motor(m.get("id")), lw - 4),
              B.LUZ if on else (C["tx"] if hov else (C["tx2"] if I.usable(m) else C["tx3"])), on, fondo)
        tt = "%s %s" % (g, txt)
        T.put(xl + wl - 2 - W(tt), ry, tt, col if (on or not I.usable(m)) else P.mix(col, B.BG, 0.3), on,
              T.at(xl + wl - 3, ry).bg)


def tablero_detalle(L, s, M, sec):
    """El cruce elegido: el agente con ese motor, cómo está y lo que hace Enter (conversar, usarlo, iniciar sesión…)."""
    import hub_inicio as I
    b, mid = tablero_cursor(s, sec)
    T, x, y, w, alto, ix, iw = _caja(L, M)
    if not b:
        T.put(ix, y + 1, "Elige un agente.", C["tx3"])
        return
    m = next((z for z in _motores(s) or () if z.get("id") == mid), None)
    xx = T.put(ix, y + 1, b["n"], b["c"], True)
    xx = T.put(xx + 1, y + 1, "con", C["tx3"])
    T.put(xx + 1, y + 1, corto(D.nombre_motor(mid), ix + iw - xx - 1), C["tx"], True)
    g, txt, col = I.estado_motor(m)
    T.put(ix, y + 2, "%s %s" % (g, txt), col, True)
    actual = b.get("motor") or b.get("mid")
    S.kv(T, ix, y + 4, "Ahora usa", D.nombre_motor(actual), kw=11, limite=ix + iw)
    usan = ", ".join((m or {}).get("agentes") or []) or "nadie"
    S.kv(T, ix, y + 5, "Lo usan", usan, kw=11, limite=ix + iw)
    lab, k = tablero_accion(s, b, mid)
    yb = max(y + 8, y + alto - 7)
    B.boton(L, s, ix, yb, lab, "acc:tablero", B.P2, foco=True, wmin=iw, a=b)
    nota = {"conversar": "Su conversación, con el motor que ya usa.",
            "usar": "Su conversación sigue con %s desde su siguiente mensaje." % D.nombre_motor(mid),
            "login": "Abre el inicio de sesión oficial de %s; al volver, Workspace lo revisa." % D.nombre_motor(mid),
            "instalar": "Motores y conexiones te dice cómo instalarlo.",
            "revisar": (m or {}).get("estado_texto") or "Motores y conexiones te dice qué le falta."}[k]
    S.parrafo(T, ix, yb + 3, nota, iw, C["tx3"], 3)


def agentes_lista(L, s, M, sec):
    """Agentes: la lista de siempre o el tablero (agentes × motores), con «Lista · Tablero» arriba."""
    T = L.T
    vista = sec.get("vista") if sec.get("vista") in dict(VISTAS_AG) else "lista"
    if vista == "tablero":
        tablero(L, s, M, sec)
        lab = " + Agregar agente "
        xv = M["xl"] + M["wl"] - W(lab) - 2
        hov = L.reg(xv, M["yt"] + 2, W(lab) + 2, 1, "acc:agregar")
        B.ficha(T, xv, M["yt"] + 2, lab, B.P3 if hov else B.P2, B.BG, C["tx"] if hov else C["tx2"])
    else:
        S.SECCIONES["agentes"][1](L, s, M, sec)
    xl, yt = M["xl"], M["yt"]
    if xl + 22 > xl + M["wl"] - W(" + Agregar agente ") - 3:    # angosta: sin «Lista · Tablero» (no cabe)
        return
    T.put(xl, yt + 2, " " * max(0, M["wl"] - 22), None, False, B.BG)
    xx = xl
    for k, lab in VISTAS_AG:
        xx = B.chip(L, xx, yt + 2, " %s " % lab, "fil:" + k, activo=k == vista) + 1
    T.put(xx + 1, yt + 2, corto("←→ agente · ↑↓ motor" if vista == "tablero" else
                                "Su cara, su tono y quién los usa.", max(0, xl + M["wl"] - 24 - xx)), C["tx3"])


def agentes_detalle_r2(L, s, M, sec):
    if (sec.get("vista") or "lista") == "tablero":
        tablero_detalle(L, s, M, sec)
        return
    agentes_detalle(L, s, M, sec)


LN2_ = "#60606b"


SECCIONES.update({
    "ajustes": (lambda s: [f["rid"] for f in ajustes_filas(s) if f.get("rid")], ajustes_lista, ajustes_detalle),
    "ayuda": (lambda s: [f["rid"] for f in ayuda_filas(s) if f.get("rid")], ayuda_lista, ayuda_detalle),
    "agentes": (S.SECCIONES["agentes"][0], agentes_lista, agentes_detalle_r2),
    "calendario": (calendario_rids, calendario_lista, calendario_detalle),
    "conexiones": (lambda s: __import__("hub_conexiones").filas(s),
                   lambda L, s, M, sec: __import__("hub_conexiones").lista(L, s, M, sec),
                   lambda L, s, M, sec: None),
})


# ── «hoy 10:00 Título» → (fecha, hora, título) ─────────────────────────────────
def leer_evento(texto, ahora=None, dia=None):
    """La línea de «+ Agregar» → (AAAA-MM-DD, HH:MM o "", título) o un error en palabras. Sin día: `dia` (el elegido)
    o hoy."""
    t = " ".join(str(texto or "").split())
    if not t:
        return None, "Escribe algo."
    hoy = time.localtime(ahora)
    base = time.mktime(hoy)
    partes = t.split(" ")
    fecha = None
    p0 = P._sin_acentos(partes[0])
    if p0 == "hoy":
        fecha, partes = time.strftime("%Y-%m-%d", hoy), partes[1:]
    elif p0 == "manana":
        fecha, partes = time.strftime("%Y-%m-%d", time.localtime(base + 86400)), partes[1:]
    elif re.match(r"^\d{4}-\d{2}-\d{2}$", partes[0]):
        if _fecha(partes[0]) is None:
            return None, "Esa fecha no existe."
        fecha, partes = partes[0], partes[1:]
    else:
        fecha = dia or time.strftime("%Y-%m-%d", hoy)
    hora = ""
    if partes and re.match(r"^\d{1,2}:\d{2}$", partes[0]):
        h, m = partes[0].split(":")
        if int(h) > 23 or int(m) > 59:
            return None, "Esa hora no existe."
        hora, partes = "%02d:%s" % (int(h), m), partes[1:]
    titulo = " ".join(partes).strip()
    if not titulo:
        return None, "Falta qué es."
    return (fecha, hora, titulo[:200]), ""
