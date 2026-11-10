#!/usr/bin/env python3
"""WORKSPACE · ventanita — el modelo «celular» de las secciones en ventana chica.

Nació en Conversaciones (la ventanita que aprobó el socio) y vive aquí para
que todas las secciones que la usan hablen igual (Conversaciones, Decisores,
Tono, Calendario):

  · entra con < 70 columnas o < 24 filas (es_ventanita); con menos de 30×6,
    el aviso de tamaño;
  · un solo nivel a la vez y nunca mezclados (lista → detalle); la cabecera
    dice dónde estás y la última fila trae las teclas de ESE nivel (o el
    aviso de lo que acaba de pasar);
  · lo clicable es una zona (fila0, fila1, col0, col1, acción) y siempre
    tiene también su tecla: en Windows (sin mouse) el teclado basta.

Piezas:
  Col, c, ink, der              columnas de líneas con sus zonas de clic
  ventana(C, alto, scroll)      lo que se ve de una Col (cabecera y pie fijos)
  seguir(C, zona, st, alto)     el desplazamiento justo para ver `zona`
  zonas_en(C, a_pant, W)        las zonas de una Col, en filas de pantalla
  lista(K, w, bloques, …)       bloques ENTEROS (tarjetas, filas), con ▲ ▼
  pie(pares, W)                 la fila de teclas, cada una clicable
  ayuda(K, w, filas, …)         la hoja de teclas (`?`)
  componer(K, W, H, …)          el cuerpo + el pie: exactamente h-1 líneas
  con_ventanita(…) / con_ventanita_accion(…)
                                el camino nuevo, sin tocar el de siempre
  mouse(tout, S)                los clics, prendidos SOLO en la ventanita

Stdlib, Python 3.9+. Mac y Windows.
"""
import functools
import os

import hublayout as HL
import section_box as SB

try:
    import i18n
except Exception:
    i18n = None


def _t(key, es, **kw):
    s = es
    if i18n is not None:
        try:
            v = i18n.t(key)
            s = v if v != key else es
        except Exception:
            s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


#: Por debajo de cualquiera de los dos: la ventanita.
ANCHO, ALTO = 70, 24
#: Por debajo de cualquiera de los dos: el aviso de tamaño.
MIN_W, MIN_H = 30, 6


def es_ventanita(w, h, alto=ALTO):
    """¿Ventanita? `alto` = las filas que pide el layout grande de la sección
    (24 en general; el Calendario pide 26)."""
    return w < ANCHO or h < alto


# ═══════════════════════════════════════════════════════════════════════════
# Dibujo: columnas de líneas + zonas de clic [(fila0, fila1, col0, col1, acción)]
# ═══════════════════════════════════════════════════════════════════════════

class Col(object):
    def __init__(self, K, w):
        self.K, self.w, self.lineas, self.zonas = K, w, [], []
        self.fijas = self.pie = 0          # filas fijas arriba (cabecera) y abajo (botones)
        self.abajo = False                 # el medio va pegado abajo (el chat)
        self.alinear = True                # siguiendo lo último: sin medio mensaje arriba
        self.contar = ""                   # «▲/▼ N más» cuenta estas zonas (no líneas)

    def add(self, lineas, accion=None, c0=0, c1=None):
        a = len(self.lineas)
        self.lineas += [HL.clip(x, self.w) for x in lineas]
        if accion is not None:
            self.zonas.append((a, len(self.lineas) - 1, c0, self.w - 1 if c1 is None else c1, accion))


def c(K, k, s, bold=False):
    return "%s%s%s%s" % (K[k], K["BO"] if bold else "", s, K["R"])


def ink(col, s, K, bold=False):
    return "%s%s%s%s" % (col, K["BO"] if bold else "", s, K["R"])


def der(izq, der, w):
    return SB.pad(izq, max(1, w - HL.vis(der) - 1)) + " " + der


def _mas_arriba(n):
    return _t("ventanita.more_up", "▲ {n} más arriba", n=n)


def _mas_abajo(n):
    return _t("ventanita.more_down", "▼ {n} más abajo", n=n)


def ventana(C, alto, scroll, mas_arriba=None, mas_abajo=None):
    """(líneas a la vista, fila→pantalla, desplazamiento, máximo, alto del
    medio). Cabecera y pie fijos; en medio, desde `scroll` (None = lo
    último), pegado abajo como un chat. `mas_arriba`/`mas_abajo` = el texto
    de «▲/▼ N más» (n → texto)."""
    mas_arriba = mas_arriba or _mas_arriba
    mas_abajo = mas_abajo or _mas_abajo
    n = len(C.lineas)
    arriba = min(C.fijas, alto)
    abajo = min(C.pie, max(0, alto - arriba))
    ini, fin = arriba, n - abajo
    alto_m = max(0, alto - arriba - abajo)
    medio = C.lineas[ini:fin]
    maxs = max(0, len(medio) - alto_m)
    st = maxs if scroll is None else max(0, min(scroll, maxs))
    if scroll is None and C.abajo and C.alinear and st:
        # siguiendo lo último: que arriba no quede media burbuja cortada (la
        # línea de antes de la primera entera lleva el «▲ más arriba»)
        tops = C.anclas if getattr(C, "anclas", None) is not None else [z[0] for z in C.zonas]
        inicios = sorted({t - ini for t in tops if ini <= t < fin})
        sig = [x for x in inicios if x - 1 >= st]       # sin perder lo último de abajo
        if sig:
            st = sig[0] - 1
    hueco = max(0, alto_m - len(medio[st:])) if C.abajo else 0
    vis_m = medio[st:st + alto_m]
    n_arriba, n_abajo = st, len(medio) - st - alto_m
    if C.contar:                       # la lista: cuántas conversaciones, no cuántas líneas
        # una tarjeta se ve si se ve su título (la fila bajo su borde); las
        # filas st y st+alto_m-1 son las de «▲/▼»
        tit = [z[0] - ini + 1 for z in C.zonas if z[4][0] == C.contar and ini <= z[0] < fin]
        n_arriba = sum(1 for t in tit if t <= st)
        n_abajo = sum(1 for t in tit if t >= st + alto_m - 1)
    if st > 0 and vis_m:
        vis_m[0] = SB.center(c(C.K, "DIM", mas_arriba(max(1, n_arriba))), C.w)
    if st + alto_m < len(medio) and vis_m:
        vis_m[-1] = SB.center(c(C.K, "DIM", mas_abajo(max(1, n_abajo))), C.w)
    vis_m = [""] * hueco + vis_m
    vis = C.lineas[:arriba] + vis_m + [""] * (alto_m - len(vis_m)) + C.lineas[fin:]

    def fila(r):
        if r < arriba:
            return r
        if r >= fin:
            return alto - (n - r)
        r2 = r - ini - st + hueco
        # las filas de arriba del hueco no son de contenido (lo de antes de st
        # caía ahí y se daba por visible) y la que tapa «▲ más arriba» es la
        # primera de contenido, no la primera de la pantalla
        if hueco <= r2 < alto_m and not ((r2 == hueco and st > 0)
                                     or (r2 == alto_m - 1 and st + alto_m < len(medio))):
            return arriba + r2
        return None
    return vis[:alto], fila, st, maxs, alto_m


def seguir(C, zona, st, alto):
    """El desplazamiento que deja `zona` (de C.zonas) a la vista moviendo LO
    JUSTO, con sitio para «▲ más arriba» / «▼ más abajo»."""
    alto_m = max(1, alto - C.fijas - C.pie)
    if zona:
        a, b = zona[0] - C.fijas, zona[1] - C.fijas
        if a < st:
            st = max(0, a - 1)                       # sitio para «▲ más arriba»
        elif b >= st + alto_m - 1:
            st = b - alto_m + 2
    return st


def zonas_en(C, a_pant, W, dy=0, dx=0):
    """Las zonas de C en filas de pantalla (las que se ven, recortadas)."""
    out = []
    for a, b, c0, c1, acc in C.zonas:
        ys = [y for y in (a_pant(r) for r in range(a, b + 1)) if y is not None]
        if ys:
            out.append((dy + min(ys), dy + max(ys), dx + c0, dx + min(c1, W - 1), acc))
    return out


def lista(K, w, bloques, sel, alto, top=0, accion="vt_item", pintar=None, ids=None):
    """Bloques ENTEROS (tarjetas o filas) en `alto` filas: el elegido siempre
    a la vista y ninguno cortado; «▲ N más arriba» / «▼ N más abajo» (cuántos
    bloques) van en su propia fila cuando sobran y se pueden clicar
    (("vt_mas", i): i = el primero que quedó oculto de ese lado). `top` = el
    primero que se veía: la lista no salta
    mientras el elegido siga a la vista. → (líneas, zonas, top), con
    exactamente `alto` líneas y una zona (accion, i) por bloque a la vista.
    Con `pintar`, cada bloque es solo su alto y pintar(i) da sus líneas: se
    pintan solo los que se ven (un historial largo no cuesta más). Con `ids`,
    las zonas llevan el id de lo que se dibujó (no su posición): si la lista
    cambia antes del clic, se actúa sobre lo que se vio."""
    def _id(i):
        return ids[i] if ids is not None else i
    n = len(bloques)
    alto = max(0, int(alto))
    if not n or not alto:
        return [""] * alto, [], 0
    hs = [max(1, b if isinstance(b, int) else len(b)) for b in bloques]
    sel = max(0, min(n - 1, sel))

    def ultimo(t):
        """(último que cabe desde t, ¿quedan más abajo?)."""
        libre = alto - (1 if t > 0 else 0)
        if sum(hs[t:]) <= libre:
            return n - 1, False
        libre -= 1                                   # la fila de «▼ más abajo»
        usado, j = 0, t
        while j < n and usado + hs[j] <= libre:
            usado += hs[j]
            j += 1
        return max(t, j - 1), True

    t = max(0, min(top, sel, n - 1))
    while t < sel and ultimo(t)[0] < sel:
        t += 1
    while t > 0 and ultimo(t - 1)[0] >= max(sel, ultimo(t)[0]):
        t -= 1                                       # sin hueco abajo si cabe uno más arriba
    u, mas = ultimo(t)
    sin_avisos = hs[t] > alto - (1 if t > 0 else 0) - (1 if mas else 0)
    if sin_avisos:                                   # muy bajo: todo el alto para el elegido
        mas = False
    out, zonas = [], []
    if t > 0 and not sin_avisos:
        out.append(SB.center(c(K, "DIM", _mas_arriba(t)), w))
        zonas.append((0, 0, 0, w - 1, ("vt_mas", _id(t - 1))))
    cuerpo = alto - (1 if mas else 0)
    for i in range(t, u + 1):
        a = len(out)
        if a >= cuerpo:
            break
        lineas = [HL.clip(x, w) for x in (pintar(i) if pintar else bloques[i])]
        if len(lineas) > cuerpo - a:
            while a == 0 and len(lineas) > 1 and not lineas[0].strip():
                lineas.pop(0)                        # arriba del todo, el aire sobra
            # ni uno cabe entero (muy bajo): lo de ABAJO del bloque, que es lo
            # que se elige (los títulos de grupo van arriba)
            lineas = lineas[len(lineas) - (cuerpo - a):]
        out += lineas
        zonas.append((a, len(out) - 1, 0, w - 1, (accion, _id(i))))
    out += [""] * max(0, cuerpo - len(out))
    if mas:
        out.append(SB.center(c(K, "DIM", _mas_abajo(n - 1 - u)), w))
        zonas.append((alto - 1, alto - 1, 0, w - 1, ("vt_mas", _id(u + 1))))
    return out[:alto], zonas, t


#: Lo que manda un clic en la fila de teclas (lo que se ve → la tecla).
_TECLA = {"Enter": "\r", "Tab": "tab", "Esc": "\x1b", "⇧Tab": "right_tab"}


def pie(pares, W):
    """La fila de teclas `[(tecla, qué hace)]` («↑↓ elegir · Enter abrir · …»)
    que cabe en W: si no caben todas cede las del medio, nunca la primera, la
    última, `?` ni `Esc` (cómo volver). → (texto, [(col0, col1, tecla)]): cada una se puede clicar
    (las de flechas no: no hay una sola tecla que mandar)."""
    pares = list(pares)

    def ancho(ps):
        return 1 + sum(HL.vis(k) + 1 + HL.vis(v) for k, v in ps) + 3 * max(0, len(ps) - 1)
    while len(pares) > 2 and ancho(pares) > W:
        cand = [j for j in range(len(pares) - 2, 0, -1) if pares[j][0] not in ("?", "Esc")]
        if not cand:
            break
        pares.pop(cand[0])
    partes, zonas, x = [], [], 1
    for k, v in pares:
        txt = "%s %s" % (k, v)
        tecla = _TECLA.get(k, k if len(k) == 1 else None)
        if tecla:
            zonas.append((x, x + HL.vis(txt) - 1, tecla))
        partes.append(txt)
        x += HL.vis(txt) + 3
    return " · ".join(partes), zonas


def ayuda(K, w, filas, titulo=None, cierra=None):
    """La hoja de teclas: el título y una fila por tecla."""
    titulo = _t("ventanita.keys", " TECLAS") if titulo is None else titulo
    cierra = _t("ventanita.keys_any", "  (cualquier tecla cierra)") if cierra is None else cierra
    return [c(K, "WH", titulo, True) + c(K, "DIM", cierra)] + [
        HL.clip(" " + c(K, "C", SB.pad(k, 8), True) + c(K, "GREY", v), w) for k, v in filas]


def caber(partes, alto):
    """partes = [(prioridad, [líneas])] en el orden en que se pintan; con poco
    alto se quitan enteras las de prioridad más alta (0 = lo último que se
    va). Lo que aun así no cabe lo corta componer (y lo anota)."""
    quedan = list(partes)
    while sum(len(l) for _p, l in quedan) > alto and len(quedan) > 1:
        quedan.pop(max(range(len(quedan)), key=lambda k: (quedan[k][0], k)))
    return [x for _p, l in quedan for x in l]


def componer(K, W, H, cuerpo, alto, pie_txt, aviso="", extra=()):
    """El cuerpo (`alto` filas), lo fijo de abajo (`extra`) y el pie: las
    teclas o, si acaba de pasar algo, el aviso. Exactamente H líneas ≤ W.
    Lo que no cupo (y no estaba en blanco) queda en componer.perdidas: así
    las pruebas ven si algo se cortó."""
    componer.perdidas = [x for x in list(cuerpo)[max(0, alto):] if HL.vis(x) and x.strip()]
    cuerpo = (list(cuerpo) + [""] * alto)[:alto]
    L = [HL.clip(x, W) for x in cuerpo] + list(extra)
    linea = c(K, "B2", " " + aviso) if aviso else c(K, "GREY", " " + pie_txt)
    L.append(HL.clip(linea, W))
    L += [""] * max(0, H - len(L))
    return [HL.clip(x, W) for x in L[:H]]


componer.perdidas = []


def zona_en(S, x, y):
    """La acción bajo el punto (x, y) 1-based del mouse, o None."""
    for a, b, c0, c1, acc in S.get("_zonas", []):
        if a + 1 <= y <= b + 1 and c0 + 1 <= x <= c1 + 1:
            return acc
    return None


# ═══════════════════════════════════════════════════════════════════════════
# El camino nuevo: la sección de siempre a ≥ 70×24, la ventanita debajo
# ═══════════════════════════════════════════════════════════════════════════

def con_ventanita(render, render_vt, seccion, alto=ALTO):
    """El render de la sección con su ventanita: a ≥ 70×`alto`, `render` (lo
    de siempre, con su guarda de tamaño); debajo, `render_vt` — o el aviso de
    tamaño bajo 30×6. Deja S["_ventanita"] para las teclas y el mouse; el
    umbral de alto queda en render.alto_ventanita."""
    @functools.wraps(render)
    def wrapped(S, w, h):
        w, h = max(1, int(w)), max(1, int(h))
        if not es_ventanita(w, h, alto):
            S["_ventanita"] = False
            return render(S, w, h)
        S["_ventanita"] = True
        S["_viewport_active"] = False
        S["_size_blocked"] = w < MIN_W or h < MIN_H
        S["_zonas"] = []
        if S["_size_blocked"]:
            import responsive_ui as RU
            return RU.size_notice(HL.section_word(seccion), w, h, MIN_W, MIN_H)
        return render_vt(S, w, h)
    wrapped.alto_ventanita = alto
    return wrapped


def con_ventanita_accion(accion, accion_vt):
    """Las teclas: en la ventanita, las suyas; si no, las de siempre (un clic
    que llega a la vista grande no hace nada: allí no hay zonas)."""
    @functools.wraps(accion)
    def wrapped(S, key, *args, **kwargs):
        if not S.get("_ventanita"):
            if isinstance(key, tuple):
                return True
            return accion(S, key, *args, **kwargs)
        if isinstance(key, str) and not key:
            return True                      # soltar el botón (o una secuencia que no aplica): nada
        if S.get("_size_blocked"):
            if key in ("q", "\x1b", "\x03"):
                S["_size_exit"] = True
                return False
            return True
        return accion_vt(S, key)
    return wrapped


def clic(S, key):
    """(acción bajo el clic, o None, y si era la rueda: ±1). Lo de la fila de
    teclas llega como ("tecla", k)."""
    if not isinstance(key, tuple):
        return None, 0
    if key[0] == "rueda":
        return None, key[1]
    if key[0] == "mouse":
        return zona_en(S, key[1], key[2]), 0
    return None, 0


# ── el mouse, solo en la ventanita (Mac/Linux; en Windows, el teclado) ──────
#: Clics y rueda en SGR-1006, sin movimiento: el mismo combo del hub.
MOUSE_ON = "\033[?1000h\033[?1006h"
MOUSE_OFF = "\033[?1000l\033[?1006l"


def quiere_mouse(S):
    return bool(S.get("_ventanita")) and os.name != "nt" and not os.environ.get("WORKSPACE_NO_MOUSE")


def mouse(tout, S):
    """Prende los clics al entrar a la ventanita y los apaga al salir de ella
    (en la vista grande se sigue seleccionando texto como siempre)."""
    quiere = quiere_mouse(S)
    if quiere == bool(S.get("_mouse")):
        return
    try:
        tout.write(MOUSE_ON if quiere else MOUSE_OFF)
        tout.flush()
    except Exception:
        return
    S["_mouse"] = quiere


def mouse_off(tout, S):
    """Al salir de la sección: los clics, apagados siempre."""
    if S.get("_mouse"):
        try:
            tout.write(MOUSE_OFF)
            tout.flush()
        except Exception:
            pass
        S["_mouse"] = False


def resto_mouse(fd, leer=None, listo=None):
    """Para los lectores crudos (un byte a la vez): tras «ESC [ <», el resto
    del evento SGR hasta «M»/«m» → lo que da section_box.mouse_event, o ""."""
    if leer is None:
        leer = lambda n: os.read(fd, n)                         # noqa: E731
    if listo is None:
        import select
        listo = lambda t: bool(select.select([fd], [], [], t)[0])   # noqa: E731
    buf = b"[<"
    while len(buf) < 24 and listo(0.05):
        b = leer(1)
        if not b:
            break
        buf += b
        if b in (b"M", b"m"):
            return SB.mouse_event(buf) or ""
    return ""
