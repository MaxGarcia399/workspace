#!/usr/bin/env python3
r"""WORKSPACE · hub_conexiones — Conexiones en el hub: ¿Workspace está bien conectado por dentro en cada motor?

Conexiones en verde (F5, H3-b: un grupo de Ajustes, con su línea en Motores). Lee lo MISMO que la página (GET
/api/v2/chequeo → arquitectura/chequeo: el chequeo rápido, sin IA) y lo dibuja así (`lista`):

  · arriba, «↻ Revisar ahora» (R) y «Reportar» (p), y «Revisado al abrir hace 1 min» o «Revisando…»;
  · «✓ Workspace por dentro» en una línea, y el aviso del último arreglo con su «Deshacer» (d);
  · una pestaña por motor instalado (←→), cada una con su ✓ / ⚠ / ✗;
  · las filas de ese motor (↑↓): ✓ funciona · ⚠ algo que solo tú puedes hacer · ✗ roto, cada una con su porqué en
    una frase y, si no está bien, UNA acción (Enter): Arreglar (lo de Workspace), Abrir en el cliente oficial (iniciar
    sesión, confiar en Codex) o Reportar;
  · la tarjeta «se actualizó» de ese motor si cambió de versión (Seguir con otro motor · Reportar · Volver a revisar),
    y «Tus MCP en …» (solo lectura).

La matriz de antes (la prueba a fondo con el motor real, pieza × motor) queda como vista de LABORATORIO, solo en modo
desarrollador (L): `lista_lab`. Lo de abajo es de esa vista. Lee GET /api/v2/conexiones (arquitectura/verificacion.matriz:
la última verificación REAL, con sus fechas) y lo dibuja así:

  · arriba, «↻ Verificar todos» (V) y «↻ Verificar <motor>» (v), la fecha de la última verificación real o, mientras
    corre, su avance («Verificando Codex por la terminal… 3 de 16»);
  · las piezas comunes (servidor local, registro de eventos, MCP núcleo, paquete por sesión, la cola, el Vigía), cada
    una con ✓ / ✗ y su fecha;
  · la matriz: una fila por motor (con su vía de control de verdad: `claude -p`, app-server, serve o ACP) y una
    columna por pieza del plan; en cada celda, la terminal y la página: ✓ verde, ✗ rojo, – gris («no se usa», siempre
    con su porqué), ! ámbar («falta tu confianza» o tu sesión) y ? («sin verificar»);
  · abajo, la celda elegida: cómo está en cada camino, la evidencia (Enter la abre entera), qué hacer y «Reparar» (r),
    que lleva al arreglo por el camino oficial: iniciar sesión con su comando oficial, abrir Codex en la carpeta del
    agente para confiar en sus avisos (/hooks), el comando oficial de la cuenta de un perfil de Hermes o, si no, otra
    verificación real con su siguiente paso en una línea. Nunca se salta nada ni se escribe la config del motor.

Aquí se dibuja y se decide (puro, con la instantánea del hub); lo que hace cada tecla o clic está en
hub_directo.Directo. Stdlib."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_paleta as P  # noqa: E402
import hub_directo as D  # noqa: E402
import hub_bloque as B  # noqa: E402

C = P.C
W, corto = B.W, B.corto
ERR = "#e5534b"
#: Las columnas, en el orden de verificacion.SISTEMAS: (id, en la cabecera).
COLUMNAS = (("via", "Vía"), ("paquete", "Paquete"), ("avisos", "Avisos"), ("mcp", "MCP"), ("formularios", "Preguntas"),
            ("instrucciones", "Manual"), ("skills", "Skills"), ("permisos", "Permisos"), ("numero", "Número"),
            ("secretos", "Secretos"))
#: Piezas que solo existen en un camino (verificacion.SOLO): la vía es de la página; permisos, número y maleta, de
#: la terminal.
SOLO = {"via": ("pagina",), "permisos": ("terminal",), "numero": ("terminal",), "maleta": ("terminal",)}
CAMINOS = ("terminal", "pagina")
#: (signo, color, palabra) por estado.
GLIFO = {"ok": ("✓", B.OK, "funciona"), "falla": ("✗", ERR, "falló"), "no_se_usa": ("–", None, "no se usa"),
         "confianza": ("!", B.WARN, "falta tu confianza"), "sin_verificar": ("?", None, "sin verificar")}
COMUNES_CORTO = {"servidor": "Servidor local", "registro": "Registro de eventos", "mcp": "MCP núcleo",
                 "paquete": "Paquete por sesión"}


def glifo(estado):
    g, col, pal = GLIFO.get(estado or "sin_verificar", GLIFO["sin_verificar"])
    return g, col or C["tx3"], pal


def datos(s):
    """La matriz que llegó (la de la página o, si la página prendida no la trae, la misma calculada aquí), o None."""
    return (s.get("datos") or {}).get("conexiones_v")


def motores(s):
    return (datos(s) or {}).get("motores") or []


def filas(s):
    """Lo que se elige: en Conexiones, «cv:<motor>:<fila>» (el chequeo rápido); en el laboratorio, las celdas de la
    matriz fila por fila («cx:<motor>:<pieza>»)."""
    sec = s.get("seccion") or {}
    if not sec.get("lab"):
        todas = ["cv:%s:%s" % (m.get("motor"), f.get("id")) for m in motores_v(s) for f in m.get("filas") or ()]
        m, f = cursor_v(s, sec)                       # la elegida primero: ahí empieza el foco (la primera con algo)
        primera = "cv:%s:%s" % (m.get("motor"), (f or {}).get("id")) if m else ""
        return ([primera] if primera in todas else []) + [r for r in todas if r != primera]
    return ["cx:%s:%s" % (f["motor"], k) for f in motores(s) for k, _c in COLUMNAS]


# ── Conexiones en verde: el chequeo rápido (lo que ve el socio) ────────────────
#: (signo, color) de cada estado del chequeo.
VERDE = {"ok": ("✓", B.OK), "tuyo": ("⚠", B.WARN), "roto": ("✗", ERR)}


def verde(estado):
    return VERDE.get(estado or "ok", VERDE["ok"])


def chequeo(s):
    """Lo que manda GET /api/v2/chequeo (o None si todavía no llega)."""
    return (s.get("datos") or {}).get("chequeo")


def motores_v(s):
    return (chequeo(s) or {}).get("motores") or []


def hay_chequeo(s):
    d = chequeo(s)
    return bool(d and (d.get("motores") or d.get("workspace")))


def resumen(s):
    """(hay datos, [(motor, nombre, cuántas filas no están bien)] de los instalados, cuántos motores tienen algo):
    lo que dice la línea «Conexiones» de Motores y el grupo Conexiones de Ajustes (el chequeo rápido)."""
    if not hay_chequeo(s):
        return False, [], 0
    filas = [(m.get("motor"), m.get("nombre") or D.nombre_motor(m.get("motor")),
              sum(1 for f in m.get("filas") or () if f.get("estado") != "ok")) for m in motores_v(s)]
    return True, filas, sum(1 for _m, _n, k in filas if k)


def linea(s):
    """(estado, texto) de la línea de Motores: «✓ todo responde · hace 5 min» · «⚠ 1 cosa por hacer» ·
    «✗ 1 rota»."""
    from arquitectura import chequeo as CH
    if not hay_chequeo(s):
        return "", "viendo…"
    return CH.linea(chequeo(s))


def estado_de(s, motor):
    m = next((x for x in motores_v(s) if x.get("motor") == motor), None)
    return (m or {}).get("estado") or ""


def cursor_v(s, sec):
    """→ (motor, fila) elegidos («cv:<motor>:<fila>»; si no hay, el primer motor con algo y su primera fila)."""
    ms = motores_v(s)
    if not ms:
        return None, None
    sel = str((sec or {}).get("sel") or "")
    m = None
    if sel.startswith("cv:"):
        _cv, mid, fid = (sel.split(":", 2) + ["", ""])[:3]
        m = next((x for x in ms if x.get("motor") == mid), None)
        if m:
            filas_ = m.get("filas") or []
            f = next((x for x in filas_ if x.get("id") == fid), None) if fid else None
            return m, f or next((x for x in filas_ if x.get("estado") != "ok"), filas_[0] if filas_ else None)
    m = next((x for x in ms if x.get("estado") != "ok"), ms[0])
    f = next((x for x in m.get("filas") or () if x.get("estado") != "ok"), (m.get("filas") or [None])[0])
    return m, f


def mover_v(s, sec, dx=0, dy=0):
    """←→ otro motor (su primera fila con algo), ↑↓ otra fila (sin dar la vuelta)."""
    m, f = cursor_v(s, sec)
    if not m:
        return
    ms = motores_v(s)
    if dx:
        i = max(0, min(len(ms) - 1, ms.index(m) + dx))
        m = ms[i]
        filas_ = m.get("filas") or []
        f = next((x for x in filas_ if x.get("estado") != "ok"), filas_[0] if filas_ else None)
    elif dy and f:
        filas_ = m.get("filas") or []
        j = max(0, min(len(filas_) - 1, filas_.index(f) + dy))
        f = filas_[j]
    sec["sel"] = "cv:%s:%s" % (m.get("motor"), (f or {}).get("id") or "")


def aviso_reciente(s):
    """El último aviso de un arreglo (con su Deshacer), o None."""
    av = (chequeo(s) or {}).get("avisos") or []
    return av[-1] if av else None


def es_dev():
    """¿Modo desarrollador? (lo dice el chequeo; si no llegó, se pregunta aquí una vez)."""
    try:
        from arquitectura import chequeo as CH
        return CH.es_dev()
    except Exception:
        return False


def _tus_mcp_texto(m):
    tus = m.get("tus_mcp")
    nom = m.get("nombre") or m.get("motor")
    if tus is None:
        return "No pude leer su archivo de MCP; ábrelo en %s." % nom
    if not tus:
        return "Ninguno. Los agregas en %s; Workspace solo los lee." % nom
    return ", ".join(tus)


def lista(L, s, M, sec):
    """Conexiones (la vista del socio): el chequeo rápido. En modo desarrollador, L abre la matriz de laboratorio."""
    if sec.get("lab"):
        return lista_lab(L, s, M, sec)
    T = L.T
    a = B.agente(s)
    d = chequeo(s)
    x, w = M["xl"], _ancho(M)
    y = M["yt"] + 2
    L.reg(x, M["y0"], w, M["y1"] - M["y0"] + 1, "lista")
    corre = bool((d or {}).get("revisando"))
    xx = B.chip(L, x, y, " ↻ Revisar ahora  R ", "acc:revisar", base=B.P2) + 1
    xx = B.chip(L, xx, y, " Reportar  p ", "acc:reportar", base=B.P2) + 1
    if es_dev():
        xx = B.chip(L, xx, y, " Prueba a fondo (laboratorio)  L ", "acc:lab", base=B.P2) + 1
    cuando = ("Revisando…" if corre else
              ("Revisado al abrir %s" % (d.get("hace") or "") if d and d.get("fecha") else "Revisando…"))
    T.right(x + w, y, corto(cuando, max(8, x + w - xx - 1)), C["tx3"])
    y = M["y0"]
    if not hay_chequeo(s):
        err = (s.get("errores") or {}).get("chequeo")
        T.put(x, y + 1, corto(err or "Revisando cómo está Workspace en cada motor (sin IA, unos segundos)…", w),
              C["tx3"])
        return
    wsp = d.get("workspace") or {}
    g, col = verde(wsp.get("estado"))
    xx = T.put(x, y, g, col, True)
    xx = T.put(xx + 1, y, wsp.get("texto") or "Workspace por dentro", C["tx"], True)
    T.put(xx + 1, y, corto("· " + str(wsp.get("detalle") or ""), x + w - xx - 3), C["tx3"])
    y += 1
    if d.get("prueba_a_fondo"):                      # F6: el canario corriendo (solo en nuestras máquinas)
        T.put(x, y, corto("◌ " + d["prueba_a_fondo"], w), C["tx2"])
        y += 1
    av = aviso_reciente(s)
    if av:
        lab = " Deshacer  d " if av.get("deshacer") else ""
        xx = T.put(x, y, corto(("✓ " if av.get("ok") else "! ") + str(av.get("texto") or ""),
                               w - W(lab) - 3), B.OK if av.get("ok") else B.WARN)
        if lab:
            B.chip(L, xx + 2, y, lab, "acc:deshacer", base=B.P2)
        y += 1
    y += 1
    m_sel, f_sel = cursor_v(s, sec)
    # las pestañas de los motores: ❮ el elegido ❯, cada uno con su estado
    xx = x
    for m in motores_v(s):
        g, col = verde(m.get("estado"))
        nom = m.get("nombre") or m.get("motor")
        nom = nom.replace(" CLI", "").replace(" (V3)", "")
        lab = "%s %s" % (nom, g)
        on = m is m_sel
        ancho = W(lab) + (4 if on else 2)
        if xx + ancho > x + w:
            break
        hov = L.reg(xx, y, ancho, 1, "cvm:" + str(m.get("motor")))
        if on:
            xx = T.put(xx, y, "❮ ", a["c"], True)
            xx = T.put(xx, y, nom, C["tx"], True)
            xx = T.put(xx + 1, y, g, col, True)
            xx = T.put(xx, y, " ❯", a["c"], True) + 1
        else:
            xx = T.put(xx + 1, y, nom, C["tx"] if hov else C["tx2"])
            xx = T.put(xx + 1, y, g, col, True) + 2
    y += 2
    if not m_sel:
        T.put(x, y, "No hay motores instalados en esta computadora: instala uno en Motores.", C["tx3"])
        return
    nom = m_sel.get("nombre") or m_sel.get("motor")
    T.put(x, y, corto("LO DE ADENTRO DE %s" % nom.upper(), w - 30), C["tx3"], True)
    ver = m_sel.get("version") or ""
    if ver:
        T.right(x + w, y, "%s%s" % (ver, (" · " + m_sel["version_estado"]) if m_sel.get("version_estado") else ""),
                C["tx3"])
    y += 1
    foco = s.get("foco_area") == "lista"
    bw = 26
    for f in m_sel.get("filas") or ():
        if y > M["y1"] - 4:
            break
        on = f is f_sel
        g, col = verde(f.get("estado"))
        if on:
            T.fill(x, y, w, 1, B.P2)
        L.reg(x, y, w - bw - 2, 1, "sr:cv:%s:%s" % (m_sel.get("motor"), f.get("id")))
        fondo = B.P2 if on else B.BG
        T.put(x, y, "▌" if on else " ", a["c"] if (on and foco) else C["tx3"], False, fondo)
        xx = T.put(x + 2, y, g, col, True, fondo)
        T.put(xx + 1, y, corto(f.get("nombre") or "", 34), C["tx"] if on else C["tx2"], on, fondo)
        lim = x + w - (bw + 2 if f.get("accion") else 1)
        col_t = C["tx2"] if f.get("estado") == "ok" else C["tx"]
        ancho_t = max(10, lim - (x + 38))
        lineas_ = _partir(f.get("texto") or "", ancho_t)
        if on and len(lineas_) > 1:                   # la elegida, en dos renglones (el resto, acortado)
            T.put(x + 38, y, lineas_[0], col_t, False, fondo)
            T.put(x + 38, y + 1, corto(" ".join(lineas_[1:]), ancho_t), col_t, False, fondo)
        else:
            T.put(x + 38, y, corto(f.get("texto") or "", ancho_t), col_t, False, fondo)
        if f.get("accion"):
            ac = f["accion"]
            etq = corto(ac.get("etiqueta") or "", bw - 2)
            rid = "acc:fila:" + str(f.get("id"))
            hov = L.reg(x + w - bw, y, bw, 1, rid)
            T.put(x + w - bw, y, etq.center(bw), B.LUZTX if (on and foco) else (C["tx"] if hov else C["tx2"]),
                  bool(on), a["c"] if (on and foco) else (B.P4 if hov else B.P3))
        y += 2 if (on and len(lineas_) > 1) else 1
    y += 1
    cambio = m_sel.get("cambio")
    if cambio and y < M["y1"] - 3:
        g, col = ("↑", C["tx2"]) if cambio.get("estado") == "ok" else verde(cambio.get("estado"))
        for ln in (D.envolver([(g + " ", col, True), (cambio.get("texto") or "", C["tx"], False)], w - 2) or [])[:2]:
            D._linea(T, x, y, ln, x + w)
            y += 1
        xx = x + 2
        for b in cambio.get("botones") or ():
            alt = cambio.get("alternativa") or ""
            lab = {"otro": " Seguir con %s " % (D.nombre_motor(alt) if alt else "otro motor"),
                   "reportar": " Reportar ", "revisar": " Volver a revisar "}.get(b, b)
            xx = B.chip(L, xx, y, lab, "acc:card:" + b, base=B.P2) + 1
        if cambio.get("botones"):
            y += 1
        y += 1
    if m_sel.get("sin_pagina") and y < M["y1"] - 2:
        for ln in (D.envolver([("La página: ", C["tx3"], True), (m_sel["sin_pagina"], C["tx3"], False)], w) or [])[:2]:
            D._linea(T, x, y, ln, x + w)
            y += 1
        y += 1
    if y < M["y1"]:
        T.put(x, y, corto("TUS MCP EN %s" % nom.upper(), w), C["tx3"], True)
        y += 1
    if y <= M["y1"]:
        T.put(x + 2, y, corto(_tus_mcp_texto(m_sel), w - 2), C["tx2"])
    if M["y1"] - 1 > y:
        lab = " Motores →  m "
        B.chip(L, x + w - W(lab) - 3, M["y1"], lab, "acc:motores", base=B.P2)
        xx = x
        for e, pal in (("ok", "funciona"), ("tuyo", "algo que solo tú puedes hacer"), ("roto", "roto")):
            g, col = verde(e)
            if xx + W(pal) + 4 > x + w - W(lab) - 6:
                break
            xx = T.put(xx, M["y1"], g, col, True)
            xx = T.put(xx + 1, M["y1"], pal, C["tx3"]) + 3


def _partir(texto, ancho):
    """El texto en renglones de a lo más `ancho` columnas, por palabras."""
    out, ln = [], ""
    for p in str(texto or "").split():
        if ln and W(ln) + 1 + W(p) > ancho:
            out.append(ln)
            ln = p
        else:
            ln = (ln + " " + p) if ln else p
    if ln:
        out.append(ln)
    return out or [""]


def accion_fila(s, sec, fid=None):
    """(motor, fila) con la acción que toca Enter (o el clic en su botón)."""
    m, f = cursor_v(s, sec)
    if fid and m:
        f = next((x for x in m.get("filas") or () if x.get("id") == fid), f)
    return m, f


def cursor(s, sec):
    """→ (fila, pieza) de la celda elegida (la primera si no hay)."""
    ms = motores(s)
    if not ms:
        return None, None
    sel = str((sec or {}).get("sel") or "")
    if sel.startswith("cx:"):
        _cx, motor, pieza = sel.split(":", 2)
        f = next((x for x in ms if x["motor"] == motor), None)
        if f and pieza in dict(COLUMNAS):
            return f, pieza
    return ms[0], COLUMNAS[0][0]


def mover(s, sec, dx=0, dy=0):
    """←→ otra pieza, ↑↓ otro motor (sin dar la vuelta)."""
    f, pieza = cursor(s, sec)
    if not f:
        return
    ms = motores(s)
    ids = [k for k, _c in COLUMNAS]
    i = max(0, min(len(ms) - 1, ms.index(f) + dy))
    j = max(0, min(len(ids) - 1, ids.index(pieza) + dx))
    sec["sel"] = "cx:%s:%s" % (ms[i]["motor"], ids[j])


def nombre_pieza(s, pieza):
    return next((x["nombre"] for x in (datos(s) or {}).get("sistemas") or () if x.get("id") == pieza),
                dict(COLUMNAS).get(pieza, pieza))


def caminos_de(celda, pieza):
    """{camino: estado} de una celda: los dos caminos (o el único que tiene la pieza)."""
    out = {}
    for c in SOLO.get(pieza, CAMINOS):
        cc = (celda.get("caminos") or {}).get(c)
        out[c] = cc["estado"] if cc else (celda.get("estado") if celda.get("estado") in ("no_se_usa",
                                                                                       "sin_verificar") else
                                          "sin_verificar")
    return out


def hace(iso):
    try:
        from arquitectura import verificacion
        return verificacion._hace(iso) if iso else ""
    except Exception:
        return ""


# ── qué hace «Reparar» (puro) ─────────────────────────────────────────────────
def _motor_sistema(s, motor):
    return next((m for m in ((s.get("datos") or {}).get("motores") or {}).get("motores") or ()
                 if m.get("id") == motor), None)


def _dice(texto, *palabras):
    t = P._sin_acentos(str(texto or "")).lower()
    return any(p in t for p in palabras)


def agente_para(s, motor):
    """El agente en cuya carpeta se abre el motor: el elegido si lo usa; si no, el primero que lo usa; si no, el
    elegido."""
    ag = s.get("agentes") or []
    if not ag:
        return None
    sel = ag[s.get("sel") or 0]
    usa = [a for a in ag if (a.get("motor") or a.get("mid")) == motor]
    return sel if sel in usa else (usa[0] if usa else sel)


def reparacion(s, fila, pieza):
    """Lo que hace «Reparar» en esta celda: {tipo, etiqueta, guia, motor[, comando, agente]} o None (✓ o «no se usa»).
    tipo: login (su inicio de sesión oficial) · confiar (Codex en la carpeta del agente: /hooks) · abrir (su programa
    oficial, con lo que pide) · comando (el comando oficial de su cuenta) · verificar (otra verificación real)."""
    if not fila:
        return None
    celda = (fila.get("celdas") or {}).get(pieza) or {}
    est = celda.get("estado") or "sin_verificar"
    cams = caminos_de(celda, pieza)
    if all(e in ("ok", "no_se_usa") for e in cams.values()):
        return None
    if est in ("ok", "no_se_usa"):                    # un camino todavía sin verificar: verificarlo
        est = "sin_verificar"
    motor, nom = fila["motor"], fila.get("nombre") or fila["motor"]
    textos = " ".join([celda.get("por_que") or ""] + [str(c.get("detalle") or "")
                                                       for c in (celda.get("caminos") or {}).values()])
    m = _motor_sistema(s, motor) or {}
    base = {"motor": motor, "nombre": nom}
    if est == "confianza" and motor == "codex":
        a = agente_para(s, motor)
        return dict(base, tipo="confiar", etiqueta="Abrir Codex y confiar", agente=(a or {}).get("id"),
                    guia=["Se abre Codex, su programa oficial, en la carpeta de %s." % ((a or {}).get("n") or "tu agente"),
                          "1. Escribe /hooks y Enter.",
                          "2. Confía en los de Workspace (una sola vez) y sal con /exit.",
                          "Al volver, Workspace verifica Codex solo."])
    pend = fila.get("pendientes") or []
    if pend and (pieza == "paquete" or _dice(textos, "cuenta")):
        p = pend[0]
        return dict(base, tipo="comando", etiqueta="Conectar su cuenta", comando=list(p.get("comando") or []),
                    guia=[p.get("texto") or "Conecta la cuenta de %s con su comando oficial." % nom,
                          "Workspace no ve ni guarda tu llave: la pones en %s." % nom,
                          "Al volver, Workspace verifica %s solo." % nom])
    if m.get("estado") == "sin_sesion" or m.get("sesion") is False or _dice(textos, "sin sesion", "inicia sesion",
                                                                            "iniciado sesion"):
        return dict(base, tipo="login", etiqueta="Iniciar sesión",
                    guia=["Se abre el inicio de sesión oficial de %s en esta terminal." % nom,
                          "Sigue sus pasos; Workspace no ve tu contraseña.",
                          "Al volver, Workspace verifica %s solo." % nom])
    if _dice(textos, "sin cuenta", "no tiene cuenta", "sin_cuenta"):
        return dict(base, tipo="cuenta", etiqueta="Conectar su cuenta",
                    guia=["Se abre la cuenta y el proveedor de %s con su comando oficial." % nom,
                          "Workspace no ve ni guarda tu llave.", "Al volver, Workspace verifica %s solo." % nom])
    if est == "confianza":
        a = agente_para(s, motor)
        return dict(base, tipo="abrir", etiqueta="Abrir %s" % nom, agente=(a or {}).get("id"),
                    guia=[celda.get("que_hacer") or "Aprueba lo de Workspace en %s." % nom,
                          "Al volver, Workspace verifica %s solo." % nom])
    return dict(base, tipo="verificar", etiqueta="Verificar %s otra vez" % nom,
                guia=[celda.get("que_hacer") or "Otra verificación real de %s." % nom])


# ── el dibujo ─────────────────────────────────────────────────────────────────
def _ancho(M):
    return M["wl"] + ((M["wd"] + 2) if M.get("lado") else 0)


def _piezas(L, s, x, y, w, d):
    """Las piezas comunes: ✓/✗ con su fecha (o su porqué), en filas de tres."""
    T = L.T
    cs = d.get("comunes") or []
    por_fila = 3 if w >= 90 else 2
    cw = w // por_fila
    for k, p in enumerate(cs):
        f, c = divmod(k, por_fila)
        g, col, _pal = glifo(p.get("estado"))
        xx = x + c * cw
        yy = y + f
        xx = T.put(xx, yy, g, col, True)
        xx = T.put(xx + 1, yy, COMUNES_CORTO.get(p.get("id"), p.get("nombre") or ""), C["tx"], False)
        extra = ("· " + hace(p.get("fecha"))) if (p.get("estado") == "ok" and p.get("fecha")) else \
            ("· " + str(p.get("por_que") or p.get("texto") or ""))
        T.put(xx + 1, yy, corto(extra, x + (c + 1) * cw - xx - 3), C["tx3"] if p.get("estado") == "ok" else
              (col if p.get("estado") == "falla" else C["tx3"]))
    return (len(cs) + por_fila - 1) // por_fila


def _cabecera(L, s, M, d, f_sel):
    """«↻ Verificar todos» · «↻ Verificar <motor>» y, a la derecha, la última verificación real o su avance."""
    T = L.T
    a = B.agente(s)
    x, y = M["xl"], M["yt"] + 2
    corre = bool(d.get("corriendo"))
    xx = B.chip(L, x, y, " ↻ Verificar todos  V ", "acc:verificar_todos", base=B.P2) + 1
    if f_sel:
        xx = B.chip(L, xx, y, corto(" ↻ Verificar %s  v " % f_sel.get("nombre"), 30), "acc:verificar",
                    base=B.P2) + 2
    lim = x + _ancho(M)
    if corre:
        pr = d.get("progreso") or {}
        hecho, total = int(pr.get("hecho") or 0), int(pr.get("total") or 0)
        txt = "Verificando %s…" % (pr.get("actual") or "") if pr.get("actual") else "Verificando…"
        if total:
            txt += " %d de %d" % (min(hecho + 1, total), total)
        bw = 16
        T.put(lim - bw, y, "▰" * int(bw * hecho / float(total or 1)) + "▱" * (bw - int(bw * hecho / float(total or 1))),
              a["c"])
        T.right(lim - bw - 2, y, corto(txt, max(10, lim - bw - 2 - xx)), C["tx"], True)
    else:
        f = d.get("fecha")
        T.right(lim, y, corto(("Última verificación real: %s" % hace(f)) if f else
                              "Todavía no hay una verificación real: V la hace", max(10, lim - xx)), C["tx3"])


def lista_lab(L, s, M, sec):
    """La vista de laboratorio (modo desarrollador): las piezas, la matriz de la prueba a fondo y la celda elegida."""
    T = L.T
    a = B.agente(s)
    d = datos(s)
    x, w = M["xl"], _ancho(M)
    L.reg(x, M["y0"], w, M["y1"] - M["y0"] + 1, "lista")
    if not d:
        car = "conexiones_v" in (s.get("cargando") or ())
        err = (s.get("errores") or {}).get("conexiones_v")
        T.put(x, M["y0"] + 1, corto("Viendo cómo está cada motor…" if car or not err else err, w), C["tx3"])
        _cabecera(L, s, M, {}, None)
        return
    f_sel, p_sel = cursor(s, sec)
    _cabecera(L, s, M, d, f_sel)
    y = M["y0"] - 1
    y += _piezas(L, s, x, y, w, d) + 2
    # la matriz
    ms = motores(s)
    foco = s.get("foco_area") == "lista"
    lw = 26 if w >= 140 else (20 if w >= 110 else 16)
    ncol = len(COLUMNAS)
    colw = max(6, min(11, (w - lw) // ncol))
    cab = max(1, min(ncol, (w - lw - 4) // colw))
    ids = [k for k, _c in COLUMNAS]
    j_sel = ids.index(p_sel) if p_sel in ids else 0
    j0 = max(0, min(j_sel - cab // 2, ncol - cab))
    if y - 1 >= M["y0"] - 1 + 1:                      # la leyenda, arriba de la cabecera
        xx = T.put(x, y - 1, "En cada celda, la terminal y la página:", C["tx3"]) + 2
        for e in ("ok", "falla", "no_se_usa", "confianza", "sin_verificar"):
            g, col, pal = glifo(e)
            if xx + W(pal) + 4 > x + w:
                break
            xx = T.put(xx, y - 1, g, col, True)
            xx = T.put(xx + 1, y - 1, pal, C["tx3"]) + 3
    T.put(x + 1, y, "Motor", C["tx3"], True)
    for jj in range(j0, j0 + cab):
        k, lab = COLUMNAS[jj]
        xx = x + lw + (jj - j0) * colw
        hov = L.reg(xx, y, colw - 1, 1, "cxs:" + k)
        T.put(xx, y, corto(lab, colw - 1).center(colw - 1), a["c"] if jj == j_sel else
              (C["tx"] if hov else C["tx2"]), jj == j_sel)
    if j0 > 0:
        hov = L.reg(x + lw - 3, y, 3, 1, "cxc:atras")
        T.put(x + lw - 3, y, "‹%d" % j0, C["tx"] if hov else C["tx3"])
    if j0 + cab < ncol:
        hov = L.reg(x + lw + cab * colw, y, 3, 1, "cxc:mas")
        T.put(x + lw + cab * colw, y, "%d›" % (ncol - j0 - cab), C["tx"] if hov else C["tx3"])
    y += 1
    alto_banda = 9 if M["y1"] - y >= 9 + 2 * len(ms) else 7
    paso = 2 if (M["y1"] - alto_banda - y) >= 2 * len(ms) else 1
    hasta = y + len(ms) * paso
    for i, f in enumerate(ms):
        yy = y + i * paso
        if yy > M["y1"] - alto_banda:
            break
        on_f = f is f_sel
        if on_f:
            T.fill(x, yy, w, 1, B.P2)
        hov = L.reg(x, yy, lw - 1, 1, "cxm:" + f["motor"])
        nom = f.get("nombre") or f["motor"]
        via = ((f.get("celdas") or {}).get("via") or {}).get("via") or ""
        col_n = (C["tx"] if (on_f or hov) else C["tx2"]) if f.get("instalado") else C["tx3"]
        sub = via if f.get("instalado") else "no instalado"
        if paso == 2:                                 # su vía de verdad, debajo de su nombre
            T.put(x + 1, yy, corto(nom, lw - 3), col_n, on_f)
            T.put(x + 3, yy + 1, corto(sub, lw - 5), C["tx3"])
        else:
            xx = T.put(x + 1, yy, corto(nom, lw - 3), col_n, on_f)
            T.put(xx + 1, yy, corto(sub, max(0, x + lw - 2 - xx)), C["tx3"])
        for jj in range(j0, j0 + cab):
            k = ids[jj]
            celda = (f.get("celdas") or {}).get(k) or {}
            xx = x + lw + (jj - j0) * colw
            rid = "sr:cx:%s:%s" % (f["motor"], k)
            L.reg(xx, yy, colw - 1, 1, rid)
            on = on_f and jj == j_sel
            fondo = B.P3 if on else (B.P2 if on_f else B.BG)
            if on:
                T.fill(xx, yy, colw - 1, 1, fondo)
                T.put(xx, yy, "▐", a["c"] if foco else C["tx3"], False, fondo)
                T.put(xx + colw - 2, yy, "▌", a["c"] if foco else C["tx3"], False, fondo)
            cams = caminos_de(celda, k)
            marcas = []
            for c in CAMINOS:
                if c in cams:
                    g, col, _p = glifo(cams[c])
                    marcas.append((g, col if f.get("instalado") else C["tx3"]))
                else:
                    marcas.append((" ", C["tx3"]))
            xc = xx + (colw - 1 - 3) // 2
            T.put(xc, yy, marcas[0][0], marcas[0][1], True, fondo)
            T.put(xc + 2, yy, marcas[1][0], marcas[1][1], True, fondo)
    yb = min(hasta + 1, M["y1"] - alto_banda + 1)
    banda(L, s, x, yb, w, M["y1"] - yb + 1, sec, f_sel, p_sel)


def banda(L, s, x, y, w, alto, sec, f, pieza):
    """La celda elegida: su motor y su pieza, cómo está en cada camino (la evidencia), qué hacer y sus botones."""
    T = L.T
    if not f or alto < 4:
        return
    a = B.agente(s)
    B.bloque(T, x, y, w, alto, B.P2, B.BG)
    L.reg(x, y, w, alto, "detalle")
    celda = (f.get("celdas") or {}).get(pieza) or {}
    g, col, pal = glifo(celda.get("estado"))
    ix, iw = x + 2, w - 4
    xx = T.put(ix, y, f.get("nombre") or f["motor"], C["tx"], True, B.P2)
    xx = T.put(xx, y, " · " + nombre_pieza(s, pieza), C["tx2"], False, B.P2)
    xx = T.put(xx + 2, y, " %s %s " % (g, celda.get("texto") or pal), B.LUZTX if celda.get("estado") in (
        "ok", "falla", "confianza") else C["tx"], True, col if celda.get("estado") in ("ok", "falla", "confianza")
        else B.P3)
    if celda.get("fecha") and xx + 14 < ix + iw:
        xx = T.put(xx + 2, y, corto("verificado " + hace(celda["fecha"]), ix + iw - xx - 2), C["tx3"], False, B.P2)
    if pieza == "via" and celda.get("via") and xx + W(celda["via"]) + 12 < ix + iw:
        T.right(ix + iw, y, "su vía: %s" % celda["via"], C["tx3"])
    ancho_txt = iw - 40
    yy = y + 1
    ev = bool(sec.get("evidencia")) or alto >= 12      # con lugar, la evidencia entera
    cams = celda.get("caminos") or {}
    for c in CAMINOS:
        if c not in SOLO.get(pieza, CAMINOS):
            continue
        cc = cams.get(c)
        est_c = cc["estado"] if cc else caminos_de(celda, pieza).get(c)
        g2, col2, pal2 = glifo(est_c)
        if cc:
            det = cc.get("detalle") or ""
        elif est_c == "no_se_usa":
            det = celda.get("por_que") or ""
        else:
            det = "Todavía sin una verificación real por %s." % ("la terminal" if c == "terminal" else "la página")
        xx = T.put(ix, yy, ("Terminal" if c == "terminal" else "Página").ljust(9), C["tx3"], False, B.P2)
        xx = T.put(xx, yy, g2 + " ", col2, True, B.P2)
        lineas_ = D.envolver([(det or pal2, C["tx2"], False)], ancho_txt) or [[]]
        for ln in lineas_[:(3 if ev else 1)]:
            if yy >= y + alto - 3:
                break
            D._linea(T, xx, yy, ln, ix + ancho_txt + 8)
            yy += 1
    if not cams and celda.get("por_que") and celda.get("estado") == "no_se_usa":
        for ln in (D.envolver([("Por qué: " + celda["por_que"], C["tx3"], False)], ancho_txt) or [])[:2]:
            if yy >= y + alto - 3:
                break
            D._linea(T, ix, yy, ln, ix + ancho_txt + 12)
            yy += 1
    extra = []
    if celda.get("que_hacer") and celda.get("estado") not in ("ok", "no_se_usa"):
        extra.append([("Qué hacer: ", a["c"], True), (celda["que_hacer"], C["tx2"], False)])
    if pieza == "mcp":
        mcp = [c for c in ((s.get("datos") or {}).get("conexiones") or {}).get("conexiones") or ()
               if f["motor"] in (c.get("motores") or ())]
        if mcp:
            extra.append([("Tus MCP en %s: " % (f.get("nombre") or f["motor"]), C["tx3"], False),
                          (", ".join(c.get("nombre") for c in mcp), C["tx2"], False)])
    for segs_ in extra:
        for ln in (D.envolver(segs_, ancho_txt + 8) or [])[:(3 if ev else 1)]:
            if yy >= y + alto - 1:
                break
            D._linea(T, ix, yy, ln, ix + ancho_txt + 8)
            yy += 1
    # los botones, a la derecha
    rep = reparacion(s, f, pieza)
    bx = ix + iw - 26
    corre = bool((datos(s) or {}).get("corriendo"))
    if rep:
        B.boton(L, s, bx, y + 1, "%s  r" % rep["etiqueta"], "acc:reparar", B.P2, foco=True, ancho=26, a=a,
                apagado=corre and rep["tipo"] == "verificar")
    lab = "Menos evidencia ↵" if sec.get("evidencia") else "Toda la evidencia ↵"
    hv = L.reg(bx, y + alto - 1, 26, 1, "acc:evidencia")
    T.put(bx, y + alto - 1, lab.center(26), C["tx"] if hv else C["tx3"], False, B.P3 if hv else B.P2)
