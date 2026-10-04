#!/usr/bin/env python3
"""WORKSPACE · calendario_tui — el CALENDARIO a pantalla completa.

No es otra app: es el MISMO hub con otras secciones (pedido del socio
2026-09-24). Reusa el wordmark, la paleta del tema activo, las cajas
`full_box` y la statusline de `hublayout`, así que entrar aquí se siente
como cambiar de vista, no como salir del menú.

Secciones: **MES** (rejilla navegable) · **DÍA** (lo que hay en el día
seleccionado, con alta/edición/baja).

Teclas
    ◄ ► ↑ ↓   moverse por los días        n / p   mes siguiente / anterior
    t         volver a hoy                Tab     cambiar de evento del día
    Enter     DETALLE del evento marcado  a       agregar en ese día
    e         editar (título + descr.)    x / espacio  hecha ↔ pendiente
    f         prioridad alta ↔ normal     d       borrarlo (archiva)
    Esc       cancelar / volver           q       volver al menú

Al escribir, una hora al principio se guarda como hora:
`18:00 Junta con Miguel` → 18:00 + «Junta con Miguel».

La rejilla muestra en cada día CUÁNTAS tareas faltan (número encendido;
rojo si el día ya pasó = atrasadas); un día con todo hecho lleva ✓.
Cada evento tiene una DESCRIPCIÓN larga: Enter la abre entera (vista
detalle), el panel DÍA la asoma bajo el evento marcado, y `e` la edita
en un campo multilínea rotulado (Tab cambia de campo, Enter en la
descripción = nueva línea). Las hechas se tachan con `x` y se destachan
igual — `d` sigue siendo borrar, aparte.

El modelo (store atómico, validación) vive en `personal.py`. Los drivers de
teclado son los mismos dos patrones de siempre (termios+select · msvcrt).

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import calendar as _cal
import datetime
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import personal as P                                           # noqa: E402
import hublayout as HL                                         # noqa: E402

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado",
        "domingo")
SEMANA = ("lu", "ma", "mi", "ju", "vi", "sá", "do")


def _g_events():
    """Eventos de GOOGLE (gcal.py, fase 1 solo-lectura). Falla-suave → []:
    sin URL, sin red o sin módulo el calendario local queda idéntico."""
    try:
        import gcal
        return gcal.events()
    except Exception:
        return []


def _g_on(date_s):
    """Los de Google de UN día. Falla-suave → []."""
    try:
        import gcal
        return gcal.events_on(date_s)
    except Exception:
        return []


def _K():
    """La paleta del TEMA activo, igual que el hub. Sin tuitheme, el
    fallback de hublayout.cols() (nunca truena, solo pierde color)."""
    try:
        import tuitheme
        return HL.cols(tuitheme.palette())
    except Exception:
        return HL.cols(type("P", (), {"GLYPHS": {}})())


def _size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 100, 34


def _parse_hora(txt):
    """`18:00 Junta` → ("18:00", "Junta"). Sin hora → ("", txt)."""
    partes = txt.strip().split(" ", 1)
    if len(partes) == 2 and ":" in partes[0]:
        import re
        if re.match(r"^\d{1,2}:\d{2}$", partes[0]):
            return partes[0], partes[1].strip()
    return "", txt.strip()


# ── secciones ──────────────────────────────────────────────────────────────
def _conteo(K, pend, done, budget, vencido=False):
    """La marca de UN día: el NÚMERO de tareas que FALTAN (pedido del socio
    2026-10-02 — los puntitos no decían cuántas), en oro encendido; si el
    día ya pasó con pendientes, en el rojo del tema (atrasadas). Un día con
    todo hecho lleva ✓ tenue. Degrada con honestidad: «9+» si el número no
    cabe en la celda, nada si ni eso cabe. ("", 0) sin eventos."""
    if budget < 1:
        return "", 0
    if pend > 0:
        txt = str(pend) if len(str(pend)) <= budget else "9+"
        if len(txt) > budget:
            txt = "+"
        col = (K["BAD"] or K["B"]) if vencido else K["B"]
        return "%s%s%s%s" % (col, K["BO"], txt, K["R"]), len(txt)
    if done > 0:
        return "%s✓%s" % (K["DK"], K["R"]), 1
    return "", 0


def _mes_body(S, K, inner):
    """Rejilla del mes. El día con tareas lleva su número ENCENDIDO (blanco
    bold) y debajo el CONTEO de las que faltan — se lee de un vistazo cuánto
    queda cada día (pedido del socio 2026-10-02; antes eran pips genéricos).
    Las hechas no inflan el conteo: un día cumplido lleva ✓. Hoy en inverso,
    cursor entre corchetes, fin de semana apagado, la columna del día de hoy
    marcada en la cabecera, y al pie la leyenda que explica las marcas."""
    f = S["sel"]
    hoy = datetime.date.today()
    mes_hoy = (f.year, f.month) == (hoy.year, hoy.month)
    evs = {}                               # día → (pendientes, hechas)
    for e in list(P.events()) + _g_events():
        if e["date"][:7] == f.strftime("%Y-%m"):
            d = int(e["date"][8:10])
            pend, done = evs.get(d, (0, 0))
            if e.get("done"):              # google nunca trae done
                done += 1
            else:
                pend += 1
            evs[d] = (pend, done)
    celda = max(4, min(6, inner // 7))
    anchos = [celda] * 7
    ancho = celda * 7
    pad_l = " " * max(0, (inner - ancho) // 2)
    out = [pad_l + "".join("%s%s%s" % (
        K["B2"] + K["BO"] if (mes_hoy and i == hoy.weekday()) else K["DK"],
        d.rjust(celda - 1) + " ", K["R"]) for i, d in enumerate(SEMANA)), ""]
    for semana in _cal.Calendar(firstweekday=0).monthdayscalendar(f.year,
                                                                 f.month):
        fila, marcas = [], []
        for i, d in enumerate(semana):
            if not d:
                fila.append(" " * anchos[i])
                marcas.append(" " * anchos[i])
                continue
            cuerpo = str(d).rjust(celda - 1) + " "
            if d == f.day:
                cuerpo = ("[%d]" % d).rjust(celda - 1) + " "
                fila.append("%s%s%s%s" % (K["C"], K["BO"], cuerpo, K["R"]))
            elif (d, f.month, f.year) == (hoy.day, hoy.month, hoy.year):
                # MONO: sin ANSI crudo (contrato "mono = cero ANSI" / NO_COLOR)
                i0, i1 = ("", "") if K.get("MONO") else ("\033[7m", "\033[27m")
                fila.append("%s%s%s%s%s%s"
                            % (i0, K["C"], K["BO"], cuerpo, i1, K["R"]))
            elif d in evs:
                fila.append("%s%s%s%s" % (K["WH"], K["BO"], cuerpo, K["R"]))
            else:
                fila.append("%s%s%s" % (K["DK"] if i >= 5 else K["GREY"],
                                        cuerpo, K["R"]))
            pend, done = evs.get(d, (0, 0))
            vencido = (datetime.date(f.year, f.month, d) < hoy)
            txt, n = _conteo(K, pend, done, celda - 1, vencido)
            marcas.append(" " * (celda - 1 - n) + txt + " " if n
                          else " " * anchos[i])
        out.append(pad_l + "".join(fila))
        out.append(pad_l + "".join(marcas))
    # leyenda: las marcas explicadas en una línea tenue — el mapa se lee solo
    leyenda = "%s2%s%s faltan%s   %s2%s%s atrasadas%s   %s✓%s%s hechas%s" % (
        K["B"] + K["BO"], K["R"], K["DK"], K["R"],
        (K["BAD"] or K["B"]) + K["BO"], K["R"], K["DK"], K["R"],
        K["DK"], K["R"], K["DK"], K["R"])
    out.append("")
    out.append(" " * max(0, (inner - HL.vis(leyenda)) // 2) + leyenda)
    return out


def _g_tag(K):
    """` ◦g` — la marca de ORIGEN de un evento de Google: el mismo pip hueco
    de la rejilla y la leyenda, con la g en tenue (el ·g de antes, en el tono
    más apagado del tema, era prácticamente invisible)."""
    return " %s◦%s%sg%s" % (K["B2"], K["R"], K["DIM"], K["R"])


def _prio_tag(K, e):
    """`! ` — la marca de prioridad ALTA, en el acento del tema. '' normal."""
    return "%s%s!%s " % (K["C"], K["BO"], K["R"]) \
        if e.get("prio") == "alta" else ""


def _atrasadas(S, K, inner, maxl):
    """Las ATRASADAS: pendientes de días pasados que la rejilla ya dejó
    atrás. Se juntan aquí para que no se le escapen al socio — una tarea sin
    hacer no desaparece porque el mes avanzó. Hasta 3 + «n más»; [] si no
    hay nada o no hay alto. Hecha (`x`) o borrada (`d`) sale sola."""
    if maxl < 3:
        return []
    evs = P.overdue()
    if not evs:
        return []
    rojo = (K["BAD"] or K["B"]) + K["BO"]
    etq = " %s%s%s " % (rojo, "ATRASADAS · %d" % len(evs), K["R"])
    resto = max(0, inner - HL.vis(etq))
    out = ["", "%s%s%s%s%s%s" % (K["DK"], K["SEP"] * (resto // 2), etq,
                                 K["DK"], K["SEP"] * (resto - resto // 2),
                                 K["R"])]
    tope = min(len(evs), max(1, maxl - 2 - (1 if len(evs) > maxl - 2 else 0)),
               3)
    for e in evs[:tope]:
        try:
            d = datetime.datetime.strptime(e["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        out.append(HL.clip("%s%2d %s%s %s%s%s%s" % (
            rojo, d.day, MESES[d.month - 1][:3], K["R"], _prio_tag(K, e),
            K["GREY"], e.get("title") or "", K["R"]), inner))
    if len(evs) > tope:
        out.append(HL.clip("%s   +%d más — ve al día con ◄► o táchalas "
                           "con x%s" % (K["DK"], len(evs) - tope, K["R"]),
                           inner))
    return out[:maxl]


def _proximos(S, K, inner, maxl):
    """Lo que VIENE después del día seleccionado (local + Google fusionados),
    para leer la agenda de un vistazo sin pasear el cursor día por día.
    Cada fila: día de la semana (tenue) + número (encendido) + hora + título.
    Las hechas no salen (ya no «vienen»). [] si no hay nada o no hay alto."""
    if maxl < 3:
        return []
    f = S["sel"]
    tope = f + datetime.timedelta(days=60)
    evs = [e for e in list(P.events()) + _g_events()
           if f.isoformat() < e["date"] <= tope.isoformat()
           and not e.get("done")]
    evs.sort(key=lambda e: (e["date"], e.get("time") or "99:99",
                            e.get("title") or ""))
    if not evs:
        return []
    # misma versalita sobre regla que las columnas del layout `dia` del hub
    etq = " %s%s%s " % (K["B2"] + K["BO"], "PRÓXIMOS", K["R"])
    resto = max(0, inner - HL.vis(etq))
    out = ["", "%s%s%s%s%s%s" % (K["DK"], K["SEP"] * (resto // 2), etq,
                                 K["DK"], K["SEP"] * (resto - resto // 2),
                                 K["R"])]
    prev = None
    for e in evs[:maxl - 2]:
        try:
            d = datetime.datetime.strptime(e["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        dia = "%s%s%s %s%2d%s" % (K["DK"], SEMANA[d.weekday()], K["R"],
                                  K["WH"] + K["BO"], d.day, K["R"])
        if d.month != f.month:                 # cambio de mes: se dice
            dia += "%s %s%s" % (K["DIM"], MESES[d.month - 1][:3], K["R"])
        if d == prev:                          # mismo día: la fecha no se
            dia = " " * HL.vis(dia)            # repite — se lee agrupado
        prev = d
        out.append(HL.clip("%s  %s%s%s %s%s%s%s%s" % (
            dia, K["B2"] + K["BO"], (e.get("time") or "·").rjust(5), K["R"],
            _prio_tag(K, e),
            K["GREY"], e.get("title") or "", K["R"],
            _g_tag(K) if e.get("google") else ""), inner))
    return out


def _lineas(val, w):
    """Texto multilínea → líneas envueltas a `w` RESPETANDO los saltos
    (mismo gesto que `_val_lineas` de add_agent_tui). [""] si está vacío."""
    out = []
    for par in str(val or "").split("\n"):
        out.extend(HL._wrap(par, w, 99) if par.strip() else [""])
    return out or [""]


#: líneas visibles del editor de notas — contrato de altura ACOTADA: por más
#: que crezca el texto el campo no pasa de esto (cola visible: siempre ves
#: dónde escribes; «…» marca que hay más arriba). Patrón de add_agent_tui.
_NOTAS_VIS = 4


def _campo_etq(K, nombre, activo, inner):
    """Rótulo de campo del editor: `nombre ────`, encendido en el acento
    cuando el cursor está AHÍ — siempre se sabe en qué campo escribes."""
    return HL.clip("%s%s%s %s%s%s" % (
        (K["C"] + K["BO"]) if activo else K["DK"],
        ("%s %s" % (K["PTR"], nombre)) if activo else ("  " + nombre),
        K["R"], K["DK"],
        K["SEP"] * max(1, inner - HL.vis(nombre) - 4), K["R"]), inner)


def _editor(S, K, inner):
    """El alta/edición dentro de la caja DÍA: UN solo editor de DOS campos
    ROTULADOS — «título» y «descripción» (multilínea, texto largo de
    verdad para tareas y proyectos) — tanto para `a` (nuevo) como para `e`
    (editar); antes el alta no dejaba poner descripción (bug del socio
    2026-10-02). Cursor ❯ en el campo activo y placeholder cuando la
    descripción está vacía: nada queda invisible. Tab cambia de campo;
    Enter en la descripción = nueva línea; Enter en el título guarda TODO."""
    alta = (S["modo"] == "add")
    out = ["%s%s%s" % (K["DIM"], "nuevo evento" if alta else "editando",
                       K["R"])]
    caret = "%s█%s" % (K["C"] + K["BO"], K["R"])
    en_desc = (S.get("campo") == 1)
    # cola visible al escribir: con un título largo siempre ves dónde vas
    vtxt, vw = S["buf"], max(10, inner - 6)
    if not en_desc and len(vtxt) > vw:
        vtxt = "…" + vtxt[-(vw - 1):]
    # ── campo TÍTULO (una línea, rotulado) ──
    out.append(_campo_etq(K, "título", not en_desc, inner))
    if not vtxt and not en_desc and alta:
        # placeholder del alta: el formato se dice solo
        out.append(HL.clip("   %s18:00 Junta con Miguel%s%s" % (
            K["DK"], K["R"], caret), inner))
    else:
        out.append(HL.clip("   %s%s%s%s" % (
            K["WH"] if not en_desc else K["GREY"], vtxt, K["R"],
            "" if en_desc else caret), inner))
    # ── campo DESCRIPCIÓN (multilínea, cola visible, altura acotada) ──
    out.append(_campo_etq(K, "descripción", en_desc, inner))
    nbuf = S.get("nbuf") or ""
    if not nbuf and not en_desc:
        # placeholder: el campo vacío SE VE y dice cómo entrarle
        out.append(HL.clip("   %svacía — Tab para escribir el detalle%s"
                           % (K["DIM"], K["R"]), inner))
    else:
        lineas = _lineas(nbuf, max(10, inner - 4))
        vis = lineas[-_NOTAS_VIS:]
        if len(lineas) > _NOTAS_VIS:
            vis[0] = "…" + (vis[0][1:] if vis[0] else "")
        for i, ln in enumerate(vis):
            tail = caret if (en_desc and i == len(vis) - 1) else ""
            col = K["WH"] if en_desc else K["GREY"]
            out.append(HL.clip("   %s%s%s%s" % (col, ln, K["R"], tail),
                               inner))
    out.append("")
    if en_desc:
        out += _hints(K, inner, (("Enter", "nueva línea"),
                                 ("Tab", "al título (ahí se guarda)"),
                                 ("Esc", "cancela")))
    else:
        out += _hints(K, inner, (("Enter", "guarda todo"),
                                 ("Tab", "a la descripción"),
                                 ("Esc", "cancela")))
        if alta:
            out.append(HL.clip("%s18:00 al inicio pone la hora%s"
                               % (K["DK"], K["R"]), inner))
    return out


def _tachada(K, txt):
    """HECHA: tachada y atenuada — sigue ahí (no se borró), pero ya no pide
    atención. En terminales sin strikethrough queda solo atenuada: degrada
    sin romperse."""
    return "\033[9m%s%s%s\033[29m" % (K["DK"], txt, K["R"])


def _hints(K, inner, items):
    """Hilera de atajos `tecla acción · …`. Si no cabe entera se parte en
    DOS líneas en vez de recortarse — un atajo cortado no enseña nada
    (transparencia antes que recorte)."""
    partes = ["%s%s%s%s %s%s" % (K["C"], K["BO"], k, K["R"] + K["DIM"], t,
                                 K["R"]) for k, t in items]
    sep = " %s·%s " % (K["DK"], K["R"])
    out, fila = [], []
    for p in partes:
        cand = fila + [p]
        if fila and HL.vis(sep.join(cand)) > inner:
            out.append(sep.join(fila))
            fila = [p]
        else:
            fila = cand
    if fila:
        out.append(sep.join(fila))
    return [HL.clip(x, inner) for x in out[:3]]


def _detalle(S, K, inner, alto):
    """La vista DETALLE del evento marcado (se abre con Enter): título
    completo, estado y la DESCRIPCIÓN entera, legible — lo que hace OBVIA
    la descripción larga (feedback del socio 2026-10-02: escondida tras
    e+Tab «parecía que ni estaba»). Desde aquí `e` cae DIRECTO al campo
    de descripción del editor."""
    evs = S.get("evs") or []
    e = evs[S["ev"] % len(evs)]
    tl = _lineas(e.get("title") or "", max(10, inner - 9))
    out = [HL.clip(" %s%s%s  %s%s%s%s%s" % (
        K["B2"] + K["BO"], e.get("time") or "todo el día", K["R"],
        _prio_tag(K, e), K["WH"] + K["BO"], tl[0], K["R"],
        _g_tag(K) if e.get("google") else ""), inner)]
    for ln in tl[1:3]:
        out.append(HL.clip("        %s%s%s%s" % (K["WH"], K["BO"], ln,
                                                 K["R"]), inner))
    est = ("%s✓ hecha%s" % (K["DK"], K["R"]) if e.get("done")
           else "%s○ pendiente%s" % (K["DIM"], K["R"]))
    if e.get("prio") == "alta":
        est += "   %s%s! prioridad alta%s" % (K["C"], K["BO"], K["R"])
    out.append(" " + est)
    out.append("")
    etq = "descripción"
    out.append(HL.clip("%s%s%s%s %s%s%s" % (
        K["B"], K["BO"], etq, K["R"], K["DK"],
        K["SEP"] * max(1, inner - HL.vis(etq) - 2), K["R"]), inner))
    notas = (e.get("notes") or "").strip()
    # el pie (aire + hints) se presupuesta ANTES: la descripción recibe lo
    # que queda y los atajos JAMÁS se recortan por una nota larga
    pie = [""] + _hints(K, inner, (("e", "editar descripción"),
                                   ("x", "hecha"), ("f", "prio"),
                                   ("Esc", "volver")))
    cupo = max(1, alto - len(out) - len(pie) - 1)
    if notas:
        nl = _lineas(notas, max(10, inner - 3))
        for ln in nl[:cupo]:
            out.append(HL.clip("  %s%s%s" % (K["GREY"], ln, K["R"]), inner))
        if len(nl) > cupo:
            out.append(HL.clip("  %s… %d línea(s) más — e para leerla "
                               "entera y editarla%s"
                               % (K["DK"], len(nl) - cupo, K["R"]), inner))
    elif e.get("google"):
        out.append(HL.clip("  %ssin descripción (evento de Google, solo "
                           "lectura)%s" % (K["DK"], K["R"]), inner))
    else:
        out.append(HL.clip("  %ssin descripción — pulsa %s%se%s%s para "
                           "escribirla%s" % (K["DIM"], K["R"],
                                             K["C"] + K["BO"], K["R"],
                                             K["DIM"], K["R"]), inner))
    return out + pie


def _dia_body(S, K, inner, alto=0):
    """Lo que hay en el día seleccionado + el campo de alta/edición. Con alto
    de sobra (que casi siempre lo hay: la rejilla manda), el resto de la caja
    se llena con ATRASADAS (pendientes de días pasados que no deben perderse)
    y PRÓXIMOS — los eventos que vienen, de un vistazo."""
    f = S["sel"]
    hoy = datetime.date.today()
    # local + Google en UNA lista: prioridad alta primero, luego por hora;
    # las HECHAS al final (tachadas). Los de Google llevan {"google": True}
    # y el editor los protege (solo lectura, fase 1).
    evs = sorted(P.events_on(f.isoformat()) + _g_on(f.isoformat()),
                 key=lambda e: (1 if e.get("done") else 0,
                                0 if e.get("prio") == "alta" else 1,
                                e.get("time") or "99:99",
                                e.get("title") or ""))
    S["evs"] = evs
    out = ["%s%s%s %d de %s%s%s" % (K["C"], K["BO"], DIAS[f.weekday()],
                                    f.day, MESES[f.month - 1], K["R"],
                                    "%s · hoy%s" % (K["DIM"], K["R"])
                                    if f == hoy else ""),
           "%s%s%s" % (K["DK"], K["SEP"] * max(3, inner - 2), K["R"])]
    if S["modo"] in ("add", "edit"):
        return out + _editor(S, K, inner)
    if S["modo"] == "ver" and evs:
        return out + _detalle(S, K, inner, (alto or 14) - len(out))
    if not evs:
        out.append("%ssin eventos este día%s" % (K["DK"], K["R"]))
        out.append("%sa%s%s agrega uno aquí%s" % (K["C"] + K["BO"], K["R"],
                                                  K["DIM"], K["R"]))
    for i, e in enumerate(evs):
        sel = (i == S["ev"] % len(evs))
        hora = (e.get("time") or "·").rjust(5)
        if e.get("done"):
            cuerpo = "%s%s%s  %s" % (K["DK"], hora, K["R"],
                                     _tachada(K, e.get("title") or ""))
        else:
            cuerpo = "%s%s%s  %s%s%s%s" % (
                K["B2"] + K["BO"], hora, K["R"], _prio_tag(K, e),
                (K["WH"] + K["BO"]) if sel else K["GREY"],
                e.get("title") or "", K["R"])
        out.append(HL.clip("%s %s%s" % (
            (K["C"] + K["BO"] + K["PTR"] + K["R"]) if sel else " ", cuerpo,
            _g_tag(K) if e.get("google") else ""), inner))
        # la DESCRIPCIÓN del evento marcado, asomada debajo con una barra
        # lateral — legible (GREY, no el tenue que se perdía) y con la
        # puerta dicha: Enter la abre entera
        if sel and (e.get("notes") or "").strip():
            nl = _lineas(e["notes"], max(10, inner - 11))
            barra = " " * 8 + "%s▏%s " % (K["B2"], K["R"])
            for ln in nl[:3]:
                out.append(HL.clip(barra + "%s%s%s" % (K["GREY"], ln,
                                                       K["R"]), inner))
            if len(nl) > 3:
                out.append(HL.clip(barra + "%s… %d más — Enter abre el "
                                   "detalle%s" % (K["DIM"], len(nl) - 3,
                                                  K["R"]), inner))
    if evs:
        out.append("")
        out += _hints(K, inner, (("Enter", "detalle"), ("Tab", "cambia"),
                                 ("e", "edita"), ("x", "hecha"),
                                 ("f", "prio"), ("d", "borra")))
    quedan = (alto or 14) - len(out)
    atr = _atrasadas(S, K, inner, min(quedan, 6))
    out += atr
    out += _proximos(S, K, inner, quedan - len(atr))
    return out


def render(S, w, h):
    K = _K()
    L = [""]
    # mismo wordmark del hub (centrado), para que esto NO se sienta otra app
    bt = HL.big_title(K, w, h, indent=" ", compact=(h < 30), center=True)
    L += bt
    if len(bt) > 1:
        L += HL.title_reflection(K, w, indent=" ", center=True)
    sub = "calendario"
    L.append(" " * max(0, ((w - 1) - HL.vis(sub)) // 2)
             + "%s%s%s" % (K["DIM"], sub, K["R"]))
    L.append("%s%s%s%s%s" % (K["B2"], K["BOX"][5] * 3, K["DK"],
                             K["BOX"][5] * max(1, w - 5), K["R"]))
    L.append("")
    top = len(L)
    # dos cajas, mismas proporciones que el hub: MES ancho, DÍA a la derecha
    if _responsive.vertical(w, h):
        pw = w - 3
        mes = _mes_body(S, K, pw - 4)
        first = HL.full_box('MES · %s %d' % (MESES[S['sel'].month - 1], S['sel'].year), mes, K, pw, len(mes), True)
        available = max(5, h - 1 - len(L) - len(first) - 5)
        dia = _dia_body(S, K, pw - 4, alto=available - 2)
        L += [' ' + x for x in first]
        L += [' ' + x for x in HL.full_box('DÍA', dia, K, pw, available - 2, False)]
        L += ['', HL.clip(' ◄►↑↓ día · n/p mes · Enter detalle · a agrega · e edita · q vuelve', w - 1)]
        return [HL.clip(x, w - 1) for x in L[:h - 1]] + [''] * max(0, h - 1 - len(L))
    lw = max(32, min(48, (w - 6) * 55 // 100))
    # la fila es " " + izq(lw) + "  " + der  ->  3 columnas fijas de marco
    rw = (w - 1) - lw - 3
    mes = _mes_body(S, K, lw - 4)
    # el DÍA recibe el alto REAL que tendrá la caja (el que fija la rejilla,
    # topado por la terminal) para que PRÓXIMOS llene el hueco sin cortarse
    dia = _dia_body(S, K, rw - 4,
                    alto=min(max((h - 1) - top - 3, 8), len(mes) + 4) - 2)
    # alto: lo que pidan las cajas + dos filas de aire, sin estirarse hasta
    # el borde (un hueco de quince renglones no es diseño, es sobra)
    ch = min(max((h - 1) - top - 3, 8),
             max(len(mes), len(dia)) + 4)
    izq = HL.full_box("MES · %s %d" % (MESES[S["sel"].month - 1],
                                       S["sel"].year),
                      mes, K, lw, ch - 2, True, border=K["C"])
    der = HL.full_box("DÍA", dia, K, rw, ch - 2, False, border=K["B2"],
                      label=K["B"] + K["BO"])
    for i in range(ch):
        L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "", lw)
                         + "  " + (der[i] if i < len(der) else ""), w - 1))
    L.append("")
    if S.get("msg"):
        L.append(" %s%s%s" % (K["B2"], S["msg"], K["R"]))
    else:
        L.append("")
    hint = ("◄►↑↓ día · n/p mes · t hoy · Enter detalle · a agrega · "
            "e edita · x hecha · f prio · d borra · q menú")
    L.append(" %s%s%s" % (K["DK"], hint, K["R"]))
    # contrato de altura: SIEMPRE h-1 líneas exactas (pad con ""). Las
    # vistas (mes/día/detalle/editor/alta) cambian de alto entre sí y el
    # redraw es H + \033[K por línea: sin el pad, el pie de una vista alta
    # sobrevivía bajo una vista corta — pie duplicado y cajas a medias
    # (bug del socio 2026-10-02).
    L = [HL.clip(x, w - 1) for x in L[:h - 1]]
    return L + [""] * max(0, (h - 1) - len(L))


# ── acciones ───────────────────────────────────────────────────────────────
def _mes_mov(f, paso):
    y, m = f.year, f.month + paso
    if m < 1:
        y, m = y - 1, 12
    elif m > 12:
        y, m = y + 1, 1
    return datetime.date(y, m, min(f.day, _cal.monthrange(y, m)[1]))


def _sel_ev(S):
    """El evento bajo el cursor, o None si el día está vacío."""
    evs = S.get("evs") or []
    return evs[S["ev"] % len(evs)] if evs else None


def _abrir_edicion(S, e, campo=0):
    """Abre el editor sobre `e` — `campo` 1 cae directo a la descripción
    (así `e` desde el detalle edita lo que estás viendo)."""
    if e.get("google"):
        S["msg"] = "evento de Google — solo lectura (edítalo allá)"
        return
    S["modo"], S["editando"] = "edit", e["id"]
    S["buf"] = ("%s %s" % (e.get("time") or "",
                           e.get("title") or "")).strip()
    S["campo"], S["nbuf"] = campo, e.get("notes") or ""


def _toggle_hecha(S, e):
    if e.get("google"):
        S["msg"] = "evento de Google — no se tacha (no es tarea local)"
        return
    st = P.toggle_done(e["id"])
    S["msg"] = ("no pude guardarlo" if st is None else
                "hecha ✓ — sigue ahí, tachada (x la revive)" if st
                else "pendiente otra vez")


def _toggle_prioridad(S, e):
    if e.get("google"):
        S["msg"] = "evento de Google — solo lectura"
        return
    pr = P.toggle_prio(e["id"])
    S["msg"] = ("no pude guardarlo" if pr is None else
                "prioridad ALTA — va primero" if pr else "prioridad normal")


def _borrar_sel(S, e):
    if e.get("google"):
        S["msg"] = "evento de Google — solo lectura (bórralo allá)"
        return
    S["msg"] = ("borrado: %s" % e.get("title", "")[:40]
                if P.remove_event(e["id"]) else "no pude borrarlo")
    S["ev"] = 0


def _accion(S, key):
    S["msg"] = ""
    if S["modo"] == "ver":
        # vista DETALLE: leer la descripción y actuar sobre ESE evento
        e = _sel_ev(S)
        if key in ("\x1b", "\r", "\n", "q", "Q") or e is None:
            S["modo"] = "nav"
            return True
        if key in ("e", "E"):
            _abrir_edicion(S, e, campo=1)      # directo a la descripción
            return True
        if key in ("x", "X", " "):
            _toggle_hecha(S, e)
            return True
        if key in ("f", "F", "!"):
            _toggle_prioridad(S, e)
            return True
        if key in ("d", "D"):
            _borrar_sel(S, e)
            S["modo"] = "nav"
            return True
        if key == "tab" and S.get("evs"):      # siguiente evento, sin salir
            S["ev"] = (S["ev"] + 1) % len(S["evs"])
        return True
    if S["modo"] in ("add", "edit"):
        # un solo editor de dos campos para alta Y edición (el alta sin
        # descripción era el bug): campo 0 = título, campo 1 = descripción
        en_notas = (S.get("campo") == 1)
        if key == "\x1b":
            S["modo"], S["buf"], S["msg"] = "nav", "", "cancelado"
            S["campo"], S["nbuf"] = 0, ""
            return True
        if key == "tab":
            S["campo"] = 0 if en_notas else 1
            return True
        if key in ("\r", "\n"):
            if en_notas:                   # Enter en notas = nueva línea
                if len(S.get("nbuf") or "") < P.NOTES_MAX:
                    S["nbuf"] = (S.get("nbuf") or "") + "\n"
                return True
            hora, titulo = _parse_hora(S["buf"])
            S["modo"], S["buf"] = "nav", ""
            notas, S["campo"], S["nbuf"] = S.get("nbuf") or "", 0, ""
            if not titulo:
                return True
            if S.get("editando"):
                ok = P.update_event(S["editando"], S["sel"].isoformat(),
                                    titulo, hora, notes=notas.strip("\n"))
                S["editando"] = None
                S["msg"] = "editado" if ok else "no pude guardarlo"
            else:
                ok = P.add_event(S["sel"].isoformat(), titulo, hora,
                                 notes=notas.strip("\n"))
                S["msg"] = "guardado" if ok else "no pude guardarlo"
            return True
        if key in ("\x7f", "\b", "\x08"):
            campo = "nbuf" if en_notas else "buf"
            S[campo] = (S.get(campo) or "")[:-1]
            return True
        if key and len(key) == 1 and key.isprintable():
            if en_notas:
                if len(S.get("nbuf") or "") < P.NOTES_MAX:
                    S["nbuf"] = (S.get("nbuf") or "") + key
            elif len(S["buf"]) < 80:
                S["buf"] += key
        return True
    if key in ("q", "Q", "\x03"):
        return False
    if key == "left":
        S["sel"] -= datetime.timedelta(days=1)
    elif key == "right":
        S["sel"] += datetime.timedelta(days=1)
    elif key == "up":
        S["sel"] -= datetime.timedelta(days=7)
    elif key == "down":
        S["sel"] += datetime.timedelta(days=7)
    elif key in ("n", "N"):
        S["sel"] = _mes_mov(S["sel"], 1)
    elif key in ("p", "P"):
        S["sel"] = _mes_mov(S["sel"], -1)
    elif key in ("t", "T"):
        S["sel"] = datetime.date.today()
    elif key == "tab":
        if S.get("evs"):
            S["ev"] = (S["ev"] + 1) % len(S["evs"])
    elif key in ("\r", "\n"):
        # Enter: con eventos en el día abre el DETALLE del marcado (la
        # descripción entera, legible); en un día vacío, el alta directa
        if S.get("evs"):
            S["modo"] = "ver"
        else:
            S["modo"], S["buf"], S["editando"] = "add", "", None
            S["campo"], S["nbuf"] = 0, ""
    elif key in ("a", "A"):
        S["modo"], S["buf"], S["editando"] = "add", "", None
        S["campo"], S["nbuf"] = 0, ""
    elif key in ("e", "E"):
        e = _sel_ev(S)
        if e:
            _abrir_edicion(S, e)
        else:
            S["msg"] = "no hay evento que editar en este día"
    elif key in ("x", "X", " "):
        e = _sel_ev(S)
        if e:
            _toggle_hecha(S, e)
        else:
            S["msg"] = "no hay nada que tachar aquí"
    elif key in ("f", "F", "!"):
        e = _sel_ev(S)
        if e:
            _toggle_prioridad(S, e)
    elif key in ("d", "D"):
        e = _sel_ev(S)
        if e:
            _borrar_sel(S, e)
        else:
            S["msg"] = "no hay nada que borrar aquí"
    return True


# ── drivers (mismo patrón que el hub y tono_tui) ──────────────────────────
import responsive_ui as _responsive
render = _responsive.renderer(render, 'CALENDARIO')
_accion = _responsive.action(_accion)

def _draw(tout, S, first=False):
    w, h = _size()
    try:
        _responsive.paint(tout, render(S, w, h), first=first)
    except Exception:
        pass


def _run_unix(S):
    import select
    import termios
    import tty
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        tout = open("/dev/tty", "w")
    except Exception:
        return _listado()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h")
        _draw(tout, S, first=True)
        while True:
            if not select.select([fd], [], [], 0.5)[0]:
                _draw(tout, S)
                continue
            ch = os.read(fd, 1).decode("utf-8", "replace")
            key = ch
            if ch == "\x1b":
                if select.select([fd], [], [], 0.05)[0]:
                    seq = os.read(fd, 2).decode("utf-8", "replace")
                    key = {"[A": "up", "[B": "down", "[C": "right",
                           "[D": "left"}.get(seq, "\x1b")
                else:
                    key = "\x1b"
            elif ch == "\t":
                key = "tab"
            if not _accion(S, key):
                break
            _draw(tout, S)
    finally:
        try:
            tout.write("\033[?1049l")
            tout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.close(fd)
        except Exception:
            pass
    return 0


def _run_windows(S):
    import msvcrt
    tout = sys.stdout
    tout.write("\033[?1049h")
    _draw(tout, S, first=True)
    try:
        while True:
            if not msvcrt.kbhit():
                time.sleep(0.1)
                _draw(tout, S)
                continue
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                a = msvcrt.getwch()
                key = {"H": "up", "P": "down", "M": "right",
                       "K": "left"}.get(a, "")
            elif ch == "\t":
                key = "tab"
            else:
                key = ch
            if not key:
                continue
            if not _accion(S, key):
                break
            _draw(tout, S)
    finally:
        try:
            tout.write("\033[?1049l")
            tout.flush()
        except Exception:
            pass
    return 0


def _listado():
    """Sin terminal interactiva: al menos imprime la agenda."""
    return P.main(["agenda"])


def run():
    S = {"sel": datetime.date.today(), "modo": "nav", "buf": "", "ev": 0,
         "msg": "", "editando": None, "evs": [], "campo": 0, "nbuf": ""}
    try:
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactivo = False
    if not interactivo:
        return _listado()
    try:
        if os.name == "nt":
            return _run_windows(S)
        return _run_unix(S)
    except Exception as e:
        try:
            sys.stdout.write("\033[?1049l")
        except Exception:
            pass
        print("calendario: %s" % e)
        return _listado()


if __name__ == "__main__":
    sys.exit(run())
