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
    e         editar idea + prompt        x / espacio  hecha ↔ pendiente
    l         lista ↔ borrador             v       cola de tareas listas
    f         prioridad alta ↔ normal     d       papelera (15 días)
    b         abre la papelera             r       restaura dentro de ella
    m         elige otro día con flechas; Enter mueve, Esc cancela
    Esc       cancelar / volver           q       volver al menú

Al escribir, una hora al principio se guarda como hora:
`18:00 Junta con Miguel` → 18:00 + «Junta con Miguel».

La rejilla muestra en cada día CUÁNTAS tareas faltan (número encendido;
rojo si el día ya pasó = atrasadas); un día con todo hecho lleva ✓.
Cada ficha tiene IDEA / DESCRIPCIÓN y PROMPT PARA EL AGENTE, de hasta
30 000 caracteres cada uno. Alta, edición y detalle mantienen
el mes siempre visible y dos campos compactos (apilados en vertical).
Ctrl+G alterna entre calendario y escritura. Tab cambia entre
título, idea y prompt; Enter crea saltos en texto; Ctrl+S guarda desde
cualquier campo. Ctrl+V adjunta una IMAGEN al campo actual (idea → detalle,
prompt → prompt): primero del portapapeles del SO y, si no hay, pide la ruta
de un archivo fuera del alt-screen. Ctrl+X quita la imagen enfocada. Las
imágenes se ven como chips bajo cada campo (y en el DETALLE) y sus rutas
absolutas viajan en el prompt al despachar la tarea al agente multimodal. Las nuevas ideas son BORRADOR: l las marca LISTA para
agentes. La prioridad alta es independiente del estado de preparación.

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
try:
    import clip_image                                          # noqa: E402
except Exception:                                              # falla-suave
    clip_image = None

# i18n (lado cliente). Import guardado + red de seguridad inline: sin i18n (o
# clave faltante) `_t()` devuelve el español `es` tal cual → paridad EXACTA con
# el calendario de siempre (patrón B de lang/README.md).
try:
    import i18n as _i18n
except Exception:
    _i18n = None


def _t(key, es, **kw):
    s = es
    if _i18n is not None:
        try:
            v = _i18n.t(key)
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


MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado",
        "domingo")
SEMANA = ("lu", "ma", "mi", "ju", "vi", "sá", "do")


# Accesores i18n de meses/días: fuente ES = los tuples de arriba, claves
# COMPARTIDAS en `common.cal.*` (las mismas que usa el mini-calendario del hub).
# No se redefinen aquí — solo se referencian.
def _mes_largo(m):
    return _t("common.cal.month_long.%d" % m, MESES[m - 1])


def _mes_corto(m):
    return _t("common.cal.month_short.%d" % m, MESES[m - 1][:3])


def _dia_largo(wd):
    return _t("common.cal.day_long.%d" % wd, DIAS[wd])


def _dow(i):
    return _t("common.cal.dow.%d" % i, SEMANA[i])


# UNA fuente de verdad de los atajos: la cabecera enseña los 3 clave + salir
# (HL.top_hints los recorta) y el pie la lista COMPLETA (HL.foot_hints). Se
# construye por render (función) para que el idioma flipee en vivo.
def _pares():
    return (("◄►↑↓", _t("cal.hint.day", "día")),
            ("Enter", _t("cal.hint.detail", "detalle")),
            ("a", _t("cal.hint.add", "agrega")),
            ("l", _t("cal.hint.list", "lista")),
            ("v", _t("cal.hint.queue", "cola")),
            ("g", _t("cal.hint.google", "Google")),
            ("n/p", _t("cal.hint.month", "mes")),
            ("t", _t("cal.hint.today", "hoy")),
            ("m", _t("common.hint.move", "mueve")),
            ("b", _t("cal.hint.trash", "papelera")),
            ("q", _t("common.hint.menu", "menú")))


def _status_labels():
    return {"draft": _t("cal.status.draft", "BORRADOR"),
            "ready": _t("cal.status.ready", "LISTA"),
            "in_progress": _t("cal.status.in_progress", "EN CURSO"),
            "blocked": _t("cal.status.blocked", "BLOQUEADA"),
            "done": _t("cal.status.done", "TERMINADA")}


def _task_tag(K, event):
    if event.get("google"):
        return ""
    status = P.task_status(event)
    role = {"draft": "DK", "ready": "OK", "in_progress": "C", "blocked": "BAD", "done": "DK"}[status]
    return "%s[%s]%s " % (K[role], _status_labels()[status], K["R"])


def _toggle_ready(S, event):
    if event.get("google"):
        S["msg"] = _t("cal.msg.g_readonly", "evento de Google — solo lectura")
        return
    current = next((e for e in P.events() if e["id"] == event["id"]), None)
    if current is None:
        S["msg"] = _t("cal.msg.task_gone", "la tarea ya no está disponible")
        return
    status = "draft" if P.task_status(current) == "ready" else "ready"
    if P.set_task_status(event["id"], status):
        S["msg"] = _t("cal.msg.now_ready", "LISTA para tomar por un agente") if status == "ready" \
            else _t("cal.msg.now_draft", "BORRADOR — fuera de la cola")
    else:
        S["msg"] = _t("cal.msg.ready_fail", "no se cambió: tarea en curso o error al guardar")


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
        _dow(i).rjust(celda - 1) + " ", K["R"]) for i, d in enumerate(SEMANA)), ""]
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
    leyenda = "%s2%s%s %s%s   %s2%s%s %s%s   %s✓%s%s %s%s" % (
        K["B"] + K["BO"], K["R"], K["DK"], _t("cal.legend.due", "faltan"), K["R"],
        (K["BAD"] + K["BO"]) if K["BAD"] else (K["B"] + K["BO"]), K["R"], K["DK"],
        _t("cal.legend.overdue", "atrasadas"), K["R"],
        K["DK"], K["R"], K["DK"], _t("cal.legend.done", "hechas"), K["R"])
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
    etq = " %s%s%s " % (rojo, _t("cal.box.overdue", "ATRASADAS · {n}", n=len(evs)), K["R"])
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
            rojo, d.day, _mes_corto(d.month), K["R"], _prio_tag(K, e),
            K["GREY"], e.get("title") or "", K["R"]), inner))
    if len(evs) > tope:
        out.append(HL.clip("%s   %s%s" % (
            K["DK"], _t("cal.overdue.more",
                        "+{n} más — ve al día con ◄► o táchalas con x",
                        n=len(evs) - tope), K["R"]), inner))
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
    etq = " %s%s%s " % (K["B2"] + K["BO"], _t("cal.box.upcoming", "PRÓXIMOS"), K["R"])
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
        dia = "%s%s%s %s%2d%s" % (K["DK"], _dow(d.weekday()), K["R"],
                                  K["WH"] + K["BO"], d.day, K["R"])
        if d.month != f.month:                 # cambio de mes: se dice
            dia += "%s %s%s" % (K["DIM"], _mes_corto(d.month), K["R"])
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
        out.extend(HL._wrap(par, w, max(99, len(par) + 1)) if par.strip() else [""])
    return out or [""]


def _campo_etq(K, nombre, activo, inner):
    """Rótulo de campo del editor: `nombre ────`, encendido en el acento
    cuando el cursor está AHÍ — siempre se sabe en qué campo escribes."""
    return HL.clip("%s%s%s %s%s%s" % (
        (K["C"] + K["BO"]) if activo else K["DK"],
        ("%s %s" % (K["PTR"], nombre)) if activo else ("  " + nombre),
        K["R"], K["DK"],
        K["SEP"] * max(1, inner - HL.vis(nombre) - 4), K["R"]), inner)


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
    header = _t("cal.day.header", "{dow} {day} de {month}",
                dow=_dia_largo(f.weekday()), day=f.day, month=_mes_largo(f.month))
    out = ["%s%s%s%s%s" % (K["C"], K["BO"], header, K["R"],
                           "%s %s%s" % (K["DIM"], _t("cal.day.today", "· hoy"),
                                        K["R"]) if f == hoy else ""),
           "%s%s%s" % (K["DK"], K["SEP"] * max(3, inner - 2), K["R"])]
    if S["modo"] == "move":
        e = S["moving"]
        return out + [HL.clip(_t("cal.move.title", "Mover: {title}",
                                 title=e["title"]), inner), "",
                      HL.clip(_t("cal.move.dest", "Destino: {date}",
                                 date=f.isoformat()), inner), "",
                      HL.clip(_t("cal.move.arrows",
                                 "Flechas: día · n/p: mes · t: hoy"), inner),
                      HL.clip(_t("cal.move.confirm",
                                 "Enter mueve · Esc cancela"), inner)]
    if not evs:
        out.append("%s%s%s" % (K["DK"], _t("cal.day.none",
                                           "sin eventos este día"), K["R"]))
        out.append("%sa%s%s %s%s" % (K["C"] + K["BO"], K["R"], K["DIM"],
                                     _t("cal.day.add_hint", "agrega uno aquí"),
                                     K["R"]))
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
                _task_tag(K, e) + (e.get("title") or ""), K["R"])
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
                out.append(HL.clip(barra + "%s%s%s" % (
                    K["DIM"], _t("cal.day.notes_more",
                                 "… {n} más — Enter abre el detalle",
                                 n=len(nl) - 3), K["R"]), inner))
    if evs:
        out.append("")
        out += _hints(K, inner, (("Enter", _t("cal.hint.detail", "detalle")),
                                 ("Tab", _t("cal.hint.switch", "cambia")),
                                 ("e", _t("cal.hint.edit", "edita")),
                                 ("x", _t("cal.hint.done", "hecha")),
                                 ("l", _t("cal.hint.ready_draft", "lista/borrador")),
                                 ("m", _t("common.hint.move", "mueve")),
                                 ("d", _t("cal.hint.delete", "borra"))))
    quedan = (alto or 14) - len(out)
    atr = _atrasadas(S, K, inner, min(quedan, 6))
    out += atr
    out += _proximos(S, K, inner, quedan - len(atr))
    return out


def render(S, w, h):
    K = _K()
    if S["modo"] in ("add", "edit", "ver"):
        return _task_form_render(S, K, w, h)
    if S["modo"] == "queue":
        return _queue_render(S, K, w, h)
    if S["modo"] == "trash":
        return _trash_render(S, K, w, h)
    if S["modo"] == "gcal":
        return _gcal_render(S, K, w, h)
    pares = _pares()
    # cabecera COMPARTIDA (wordmark + subtítulo + atajos clave + regla)
    L = HL.screen_header(K, w, h, _t("cal.subtitle", "calendario"), hints=pares)
    top = len(L)
    mes_title = _t("cal.box.month_title", "MES · {month} {year}",
                   month=_mes_largo(S["sel"].month), year=S["sel"].year)
    # dos cajas, mismas proporciones que el hub: MES ancho, DÍA a la derecha
    if _responsive.vertical(w, h):
        pw = w - 3
        mes = _mes_body(S, K, pw - 4)
        first = HL.full_box(mes_title, mes, K, pw, len(mes), True)
        available = max(5, h - 1 - len(L) - len(first) - 5)
        dia = _dia_body(S, K, pw - 4, alto=available - 2)
        L += [' ' + x for x in first]
        L += [' ' + x for x in HL.full_box(_t("cal.box.day", "DÍA"), dia, K, pw, available - 2, False)]
        L += ['', HL.clip(HL.foot_hints(K, pares, w), w - 1)]
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
    izq = HL.full_box(mes_title,
                      mes, K, lw, ch - 2, True, border=K["C"])
    der = HL.full_box(_t("cal.box.day", "DÍA"), dia, K, rw, ch - 2, False, border=K["B2"],
                      label=K["B"] + K["BO"])
    for i in range(ch):
        L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "", lw)
                         + "  " + (der[i] if i < len(der) else ""), w - 1))
    L.append("")
    if S.get("msg"):
        L.append(" %s%s%s" % (K["B2"], S["msg"], K["R"]))
    else:
        L.append("")
    L.append(HL.foot_hints(K, pares, w))
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
        S["msg"] = _t("cal.msg.g_readonly_edit", "evento de Google — solo lectura (edítalo allá)")
        return
    S["modo"], S["editando"] = "edit", e["id"]
    S["buf"] = ("%s %s" % (e.get("time") or "",
                           e.get("title") or "")).strip()
    S["campo"], S["nbuf"] = campo, e.get("notes") or ""
    S["pbuf"], S["edit_event"] = e.get("prompt") or "", dict(e)
    S["text_cursor"], S["text_scroll"] = {}, {}
    S["form_date"] = datetime.date.fromisoformat(e["date"])
    S["form_event"], S["form_focus"] = e["id"], "editor"
    S["calendar_ev"] = next((i for i, event in enumerate(_calendar_events(S)) if event["id"] == e["id"]), 0)


def _toggle_hecha(S, e):
    if e.get("google"):
        S["msg"] = _t("cal.msg.g_no_done", "evento de Google — no se tacha (no es tarea local)")
        return
    st = P.toggle_done(e["id"])
    S["msg"] = (_t("cal.msg.save_fail", "no pude guardarlo") if st is None else
                _t("cal.msg.done_ok", "hecha ✓ — sigue ahí, tachada (x la revive)") if st
                else _t("cal.msg.pending_again", "pendiente otra vez"))


def _toggle_prioridad(S, e):
    if e.get("google"):
        S["msg"] = _t("cal.msg.g_readonly", "evento de Google — solo lectura")
        return
    pr = P.toggle_prio(e["id"])
    S["msg"] = (_t("cal.msg.save_fail", "no pude guardarlo") if pr is None else
                _t("cal.msg.prio_high", "prioridad ALTA — va primero") if pr
                else _t("cal.msg.prio_normal", "prioridad normal"))


def _borrar_sel(S, e):
    if e.get("google"):
        S["msg"] = _t("cal.msg.g_readonly_delete", "evento de Google — solo lectura (bórralo allá)")
        return
    S["msg"] = (_t("cal.msg.trashed", "en papelera 15 días: {title}",
                   title=e.get("title", "")[:40])
                if P.remove_event(e["id"]) else _t("cal.msg.delete_fail", "no pude borrarlo"))
    S["ev"] = 0


def _abrir_mover(S, e):
    if e.get("google"):
        S["msg"] = _t("cal.msg.g_readonly_move", "evento de Google — solo lectura (muévelo allá)")
        return
    S["moving"] = dict(e)
    S["move_origin"] = S["sel"]
    S["modo"] = "move"


def _trash_render(S, K, w, h):
    rows = P.trash_events()
    S["trash_rows"] = rows
    idx = min(S.get("trash_idx", 0), max(0, len(rows) - 1))
    S["trash_idx"] = idx
    cap = max(1, h - 10)
    start = max(0, min(idx - cap // 2, len(rows) - cap))
    body = [_t("cal.trash.intro", "Los borrados se pueden recuperar durante 15 días."), ""]
    for i, e in enumerate(rows[start:start + cap], start):
        remaining = P.TRASH_DAYS
        try:
            deleted = datetime.datetime.fromisoformat(e["deleted_at"]).astimezone()
            seconds = (deleted + datetime.timedelta(days=P.TRASH_DAYS) - datetime.datetime.now().astimezone()).total_seconds()
            remaining = max(1, int((seconds + 86399) // 86400))
        except (KeyError, ValueError):
            pass
        text = _t("cal.trash.row", "{mark} {date} · {title} · {n}d",
                  mark=">" if i == idx else " ", date=e["date"],
                  title=e["title"], n=remaining)
        body.append(HL.clip((K["C"] + K["BO"] if i == idx else K["GREY"]) + text + K["R"], w - 8))
    if not rows:
        body.append(_t("cal.trash.empty", "Papelera vacía"))
    body += ["", S.get("msg") or "",
             HL.keyline(K, (("↑↓", _t("common.hint.pick", "elige")),
                            ("r / Enter", _t("cal.hint.restore", "restaura")),
                            ("Esc / q", _t("cal.hint.back", "vuelve"))), max(10, w - 8))]
    lines = [""] + [" " + x for x in HL.full_box(
        _t("cal.box.trash", "PAPELERA · {n} eventos", n=len(rows)),
        body, K, w - 3, len(body), True)]
    return [HL.clip(x, w - 1) for x in lines[:h - 1]] + [""] * max(0, h - 1 - len(lines))


def _text_panel(S, K, key, title, width, height, active, readonly=False,
                field=None):
    text = S.get(key) or ""
    iw = max(8, width - 4)
    cursor = S.setdefault("text_cursor", {}).get(key, len(text))
    lines = _lineas(text[:cursor], iw - 2)
    cursor_line = len(lines) - 1
    if active and not readonly:
        display = text[:cursor] + "▏" + text[cursor:]
    else:
        display = text
    rows = _lineas(display, iw - 2)
    capacity = max(1, height - 2)
    # CHIPS de imágenes adjuntas: una fila al pie del campo (dentro de la caja),
    # el enfocado en el acento. Roba UNA fila al texto para no cambiar el alto.
    chips = _event_images(S, field) if field else []
    chip = None
    if chips:
        focus_idx = S.get("img_focus", {}).get(field, len(chips) - 1)
        chip = _chip_line(K, chips, focus_idx, iw - 2)
    text_cap = max(1, capacity - (1 if chip is not None else 0))
    scroll = S.setdefault("text_scroll", {}).get(key, max(0, cursor_line - text_cap + 1) if active and not readonly else 0)
    scroll = min(max(0, scroll), max(0, len(rows) - text_cap))
    S["text_scroll"][key] = scroll
    body = [K["GREY"] + row + K["R"] for row in rows[scroll:scroll + text_cap]]
    if not text and not active:
        body = [K["DIM"] + (_t("cal.panel.idea_ph", "Describe qué quieres lograr y el contexto.")
                            if key == "nbuf" else
                            _t("cal.panel.prompt_ph", "Indica cómo debe trabajar el agente.")) + K["R"]]
    if chip is not None:
        body = body[:text_cap] + [chip]
    label = title + " · %d/%d" % (scroll + 1, len(rows))
    if chips:
        label += "  %s%s%s" % (K["B2"], _t("cal.img.label", "{n} img", n=len(chips)), K["R"])
    return HL.full_box(label, body, K, width, capacity, active, border=K["C"] if active else K["B2"])


def _calendar_events(S):
    return sorted(P.events_on(S["sel"].isoformat()) + _g_on(S["sel"].isoformat()),
                  key=lambda e: (bool(e.get("done")), e.get("prio") != "alta",
                                 e.get("time") or "99:99", e.get("title") or ""))


def _calendar_context(S, K, width, height, focused):
    inner = width - 4
    body = _mes_body(S, K, inner)
    rows = _calendar_events(S)
    idx = min(S.get("calendar_ev", 0), max(0, len(rows) - 1))
    S["calendar_ev"] = idx
    body += ["", K["B2"] + _t("cal.ctx.day", "DÍA · {date}", date=S["sel"].isoformat()) + K["R"]]
    capacity = max(1, min(4, height - 2 - len(body)))
    start = max(0, min(idx - capacity // 2, len(rows) - capacity))
    for i, e in enumerate(rows[start:start + capacity], start):
        label = (K["C"] + K["PTR"] + K["R"] + " " if i == idx else "  ")
        body.append(HL.clip(label + _task_tag(K, e) + e["title"], inner))
    if not rows:
        body.append(K["DIM"] + _t("cal.ctx.none", "Sin fichas; a crea una aquí") + K["R"])
    title = _t("cal.box.month_title", "MES · {month} {year}",
               month=_mes_largo(S["sel"].month), year=S["sel"].year)
    return HL.full_box(title, body, K, width, height - 2, focused,
                       border=K["C"] if focused else K["B2"])


def _new_form(S):
    S.update(modo="add", buf="", nbuf="", pbuf="", editando=None,
             edit_event=None, form_event=None, form_date=S["sel"], campo=0,
             form_focus="editor", calendar_ev=0, text_cursor={}, text_scroll={})


def _open_detail(S, event):
    S.update(modo="ver", evs=[event], ev=0, campo=1,
             form_event=event["id"], form_date=datetime.date.fromisoformat(event["date"]),
             form_focus="editor", text_cursor={}, text_scroll={})
    S["calendar_ev"] = next((i for i, e in enumerate(_calendar_events(S)) if e["id"] == event["id"]), 0)


def _persist_form(S, close=True):
    hora, title = _parse_hora(S.get("buf") or "")
    if not title:
        if not close and not (S.get("nbuf") or S.get("pbuf")) and not S.get("editando"):
            return True
        S["msg"] = _t("cal.msg.need_title", "escribe un título; el contenido sigue aquí")
        return False
    form_date = S.get("form_date") or S["sel"]
    notes, prompt = S.get("nbuf") or "", S.get("pbuf") or ""
    if S.get("editando"):
        eid = S["editando"]
        ok = P.update_event(eid, title=title, time_s=hora, notes=notes, prompt=prompt)
    else:
        eid = P.add_event(form_date.isoformat(), title, hora, notes=notes, prompt=prompt)
        ok = bool(eid)
    if not ok:
        S["msg"] = _t("cal.msg.save_lost", "no se guardó; tus campos siguen aquí")
        return False
    S["editando"], S["form_event"] = eid, eid
    S["edit_event"] = next((e for e in P.events() if e["id"] == eid), None)
    S["modo"] = "nav" if close else "edit"
    if close:
        S["sel"] = form_date
        S["ev"] = next((i for i, e in enumerate(_calendar_events(S)) if e["id"] == eid), 0)
        S["form_focus"] = "editor"
    S["msg"] = _t("cal.msg.saved", "guardado; l marca LISTA para un agente")
    return True


# ── imágenes adjuntas (schema 2) ─────────────────────────────────────────────
# El campo IDEA/DESCRIPCIÓN guarda en images["detail"]; PROMPT en images
# ["prompt"]. Adjuntar = Ctrl+V (portapapeles del SO; si no hay imagen, cae al
# prompt CLÁSICO fuera del alt-screen que resuelven los drivers via
# S["await_attach"]). Quitar la enfocada = Ctrl+X. Chips bajo cada campo.
def _active_eid(S):
    """El id del evento en edición/detalle (store), o None en un alta sin
    guardar todavía."""
    return S.get("editando") or S.get("form_event")


def _img_field(S):
    """El campo de imágenes según el cursor: PROMPT si está en el prompt
    (campo 2), DETALLE en título/idea (campo 0/1)."""
    return "prompt" if S.get("campo") == 2 else "detail"


def _event_images(S, field, eid=None):
    """Las imágenes de `field` del evento activo, leídas del store (la fuente
    de verdad tras adjuntar/quitar). [] si no hay evento o campo vacío."""
    eid = eid or _active_eid(S)
    if not eid:
        return []
    e = next((x for x in P.events() if x["id"] == eid), None)
    return list((e.get("images") or {}).get(field) or []) if e else []


def _refresh_edit_event(S):
    """Re-lee el evento en edición del store (para que el render muestre las
    imágenes recién adjuntadas/quitadas)."""
    eid = _active_eid(S)
    if eid:
        S["edit_event"] = next((e for e in P.events() if e["id"] == eid),
                               S.get("edit_event"))


def _img_chip_name(it):
    """Nombre visible del chip: la etiqueta del archivo original si la hay
    (adjunto por ruta), si no el archivo guardado (`<id>.ext`)."""
    return (it.get("caption") or it.get("file") or "").strip() or "imagen"


def _chip_line(K, chips, focus_idx, width):
    """Hilera de CHIPS `[img 1] nombre.png`, el enfocado en el acento. Si no
    cabe entera degrada a `[img i/n] nombre` y, en último caso, a `n imágenes`.
    None si no hay chips.

    PREVIEW inline de iTerm2 (protocolo 1337;File) DEFERIDO a propósito: el
    redraw de esta pantalla es H + \\033[K por línea con alto FIJO (contrato de
    hublayout); una imagen inline rompe la geometría estable y el posicionado
    del cursor. El chip es la representación honesta dentro del TUI; el agente
    sí ve la imagen real vía las rutas absolutas del despacho."""
    if not chips:
        return None
    partes = []
    for i, it in enumerate(chips):
        foc = (i == focus_idx)
        col = (K["C"] + K["BO"]) if foc else K["GREY"]
        partes.append("%s[%s %d]%s %s%s%s" % (
            K["DK"], _t("cal.img.chip", "img"), i + 1, K["R"],
            col, _img_chip_name(it), K["R"]))
    line = "   ".join(partes)
    if HL.vis(line) > width:
        fi = max(0, min(focus_idx, len(chips) - 1))
        line = "%s[%s %d/%d]%s %s%s%s" % (
            K["DK"], _t("cal.img.chip", "img"), fi + 1, len(chips), K["R"],
            K["C"] + K["BO"], _img_chip_name(chips[fi]), K["R"])
        if HL.vis(line) > width:
            line = "%s%s%s" % (K["DK"], _t("cal.img.count", "{n} imágenes",
                                           n=len(chips)), K["R"])
    return HL.clip(line, width)


def _attach_image(S):
    """Adjunta una imagen al campo activo. Primero el portapapeles del SO; si
    no hay imagen (o no hay módulo), marca S["await_attach"] para que el driver
    pida la RUTA de un archivo con el prompt clásico fuera del alt-screen."""
    if clip_image is None:
        S["msg"] = _t("cal.img.unavailable", "adjuntar imágenes no está disponible aquí")
        return
    eid = _active_eid(S)
    if not eid:                       # alta sin guardar → persistir para tener id
        if not _persist_form(S, close=False):
            S["msg"] = _t("cal.img.need_save", "escribe un título para adjuntar la imagen")
            return
        eid = _active_eid(S)
    if not eid:
        S["msg"] = _t("cal.img.save_fail", "no pude adjuntar la imagen")
        return
    field = _img_field(S)
    cap = None
    try:
        cap = clip_image.from_clipboard()
    except Exception:
        cap = None
    if cap:
        data, ext = cap
        rec = P.add_image(eid, field, data, ext)
        if rec:
            _refresh_edit_event(S)
            S.setdefault("img_focus", {})[field] = len(_event_images(S, field)) - 1
            S["msg"] = _t("cal.img.attached", "imagen adjuntada ✓ — el agente la verá")
        else:
            S["msg"] = _t("cal.img.save_fail", "no pude adjuntar la imagen")
        return
    S["await_attach"] = field          # el driver pide la ruta (prompt clásico)
    S["msg"] = _t("cal.img.none_clip",
                  "sin imagen en el portapapeles — pega la ruta del archivo")


def _finish_classic_attach(S, path):
    """Cierra el adjunto por RUTA tras el prompt clásico del driver: valida que
    sea una imagen (magic bytes) y la registra. Deja el resultado en S["msg"]."""
    field = S.pop("await_attach", None)
    if clip_image is None or not field:
        return
    path = (path or "").strip()
    if not path:
        S["msg"] = _t("cal.img.classic_cancel", "sin imagen adjuntada")
        return
    cap = clip_image.from_path(path)
    if not cap:
        S["msg"] = _t("cal.img.bad", "no es una imagen válida (png/jpg/gif/webp)")
        return
    eid = _active_eid(S)
    if not eid:
        S["msg"] = _t("cal.img.save_fail", "no pude adjuntar la imagen")
        return
    data, ext = cap
    rec = P.add_image(eid, field, data, ext, caption=os.path.basename(path))
    if rec:
        _refresh_edit_event(S)
        S.setdefault("img_focus", {})[field] = len(_event_images(S, field)) - 1
        S["msg"] = _t("cal.img.attached", "imagen adjuntada ✓ — el agente la verá")
    else:
        S["msg"] = _t("cal.img.save_fail", "no pude adjuntar la imagen")


def _remove_focused_image(S):
    """Quita la imagen ENFOCADA del campo activo (archivo incluido)."""
    field = _img_field(S)
    eid = _active_eid(S)
    chips = _event_images(S, field, eid)
    if not chips:
        S["msg"] = _t("cal.img.none", "no hay imágenes en este campo")
        return
    idx = S.get("img_focus", {}).get(field, len(chips) - 1)
    idx = max(0, min(idx, len(chips) - 1))
    if eid and P.remove_image(eid, field, chips[idx]["id"]):
        _refresh_edit_event(S)
        rem = _event_images(S, field, eid)
        S.setdefault("img_focus", {})[field] = max(0, min(idx, len(rem) - 1))
        S["msg"] = _t("cal.img.removed", "imagen quitada")
    else:
        S["msg"] = _t("cal.img.save_fail", "no pude adjuntar la imagen")


def _calendar_form_key(S, key):
    if key in ("\x1b", "\x07"):
        S["form_focus"] = "editor"
    elif key in ("left", "right", "up", "down"):
        S["sel"] += datetime.timedelta(days={"left": -1, "right": 1, "up": -7, "down": 7}[key])
        S["calendar_ev"] = 0
    elif key.lower() in ("n", "p"):
        S["sel"] = _mes_mov(S["sel"], 1 if key.lower() == "n" else -1)
        S["calendar_ev"] = 0
    elif key.lower() == "t":
        S["sel"], S["calendar_ev"] = datetime.date.today(), 0
    elif key in ("tab", "right_tab"):
        rows = _calendar_events(S)
        S["calendar_ev"] = (S.get("calendar_ev", 0) + (1 if key == "tab" else -1)) % max(1, len(rows))
    elif key in ("\r", "\n", "a", "A", "e", "E"):
        rows = _calendar_events(S)
        event = rows[S.get("calendar_ev", 0) % len(rows)] if rows else None
        if key in ("e", "E") and event and event.get("google"):
            S["msg"] = _t("cal.msg.g_readonly", "evento de Google — solo lectura")
            return True
        if S["modo"] != "ver" and not _persist_form(S, close=False):
            return True
        # The save may have updated the selected event: fetch its current fields.
        if event:
            event = next((e for e in _calendar_events(S) if e["id"] == event["id"]), None)
        if key in ("a", "A") or not event:
            _new_form(S)
        elif key in ("e", "E"):
            _abrir_edicion(S, event, campo=1)
        else:
            _open_detail(S, event)
    elif key in ("l", "L"):
        rows = _calendar_events(S)
        if rows:
            event = rows[S.get("calendar_ev", 0) % len(rows)]
            if event["id"] == S.get("editando") and S["modo"] != "ver":
                if not _persist_form(S, close=False):
                    return True
            _toggle_ready(S, event)
    elif key == "\x13" and S["modo"] != "ver":
        _persist_form(S, close=False)
    return True


def _task_form_render(S, K, w, h):
    readonly = S["modo"] == "ver"
    form_date = S.setdefault("form_date", S["sel"])
    focus = S.get("form_focus", "editor")
    if readonly:
        existing = _sel_ev(S)
        eid = S.get("form_event") or (existing or {}).get("id")
        evs = P.events_on(form_date.isoformat()) + _g_on(form_date.isoformat())
        e = next((e for e in evs if e["id"] == eid), None)
        if not e:
            S["modo"] = "nav"
            return render(S, w, h)
        S["form_event"] = e["id"]
        S["evs"], S["ev"] = [e], 0
        S["buf"], S["nbuf"], S["pbuf"] = e["title"], e.get("notes") or "", e.get("prompt") or ""
    else:
        e = next((e for e in P.events() if e["id"] == S.get("editando")), None) or S.get("edit_event") or {"task_status": "draft"}
    field = S.get("campo", 1 if readonly else 0)
    kind = (_t("cal.ficha.kind_detail", "detalle") if readonly else
            _t("cal.ficha.kind_new", "nueva") if S["modo"] == "add" else
            _t("cal.ficha.kind_edit", "edición"))
    title = _t("cal.box.ficha", "FICHA · {date} · {kind}",
               date=form_date.isoformat(), kind=kind)
    top = ["", " " + K["C"] + K["BO"] + title + K["R"],
           " " + _task_tag(K, e) + _t("cal.ficha.queue_count", "{n} listas para agentes", n=len(P.task_queue())),
           " " + _campo_etq(K, _t("cal.ficha.title_field", "título · hora opcional al inicio"), field == 0 and focus == "editor" and not readonly, w - 4),
           "   " + HL.clip((S.get("buf") or "") + ("▏" if field == 0 and focus == "editor" and not readonly else ""), w - 5), ""]
    if focus == "calendar":
        hints = (("Ctrl+G / Esc", _t("cal.hint.text", "texto")),
                 ("↑↓◄►", _t("cal.hint.day", "día")),
                 ("n/p", _t("cal.hint.month", "mes")),
                 ("Tab", _t("cal.hint.card", "ficha")),
                 ("Enter/e", _t("cal.hint.open", "abre")),
                 ("a", _t("cal.hint.new", "nueva")))
    else:
        hints = ((("Ctrl+G", _t("cal.hint.calendar", "calendario")),
                  ("Tab", _t("cal.hint.field", "campo")),
                  ("Ctrl+V", _t("cal.hint.attach", "imagen")),
                  ("Ctrl+X", _t("cal.hint.detach", "quita img")),
                  ("e", _t("cal.hint.edit", "edita")),
                  ("l", _t("cal.hint.list", "lista")),
                  ("Esc", _t("cal.hint.back", "vuelve"))) if readonly else
                 (("Ctrl+G", _t("cal.hint.calendar", "calendario")),
                  ("Tab", _t("cal.hint.field", "campo")),
                  ("Ctrl+S", _t("cal.hint.save", "guarda")),
                  ("Ctrl+V", _t("cal.hint.attach", "imagen")),
                  ("Ctrl+X", _t("cal.hint.detach", "quita img")),
                  ("Enter", _t("cal.hint.newline", "salto")),
                  ("Esc", _t("cal.hint.cancel", "cancela"))))
    footer = [" " + HL.clip(_t("cal.ficha.result", "Resultado: {text}", text=e["result"]), w - 3) if readonly and e.get("result") else "",
              " " + HL.clip(S.get("msg") or "", w - 3),
              HL.clip(" " + HL.keyline(K, hints, max(10, w - 4)), w - 1)]
    available = min(h - 1 - len(top) - len(footer), 28 if w >= 100 else 40)
    if w >= 100:
        lw = max(38, min(46, (w - 4) * 40 // 100))
        rw = w - 4 - lw
        left = _calendar_context(S, K, lw, available, focus == "calendar")
        first = available // 2
        right = _text_panel(S, K, "nbuf", _t("cal.box.idea", "IDEA / DESCRIPCIÓN"), rw, first, field == 1 and focus == "editor", readonly, field="detail")
        right += _text_panel(S, K, "pbuf", _t("cal.box.prompt", "PROMPT PARA EL AGENTE"), rw, available - first, field == 2 and focus == "editor", readonly, field="prompt")
        body = [" " + HL.pad(a, lw) + " " + b for a, b in zip(left, right)]
    else:
        calendar_h = min(len(_mes_body(S, K, w - 7)) + 6, available - 14)
        body = [" " + row for row in _calendar_context(S, K, w - 3, calendar_h, focus == "calendar")]
        text_h = available - calendar_h
        first = text_h // 2
        body += [" " + row for row in _text_panel(S, K, "nbuf", _t("cal.box.idea", "IDEA / DESCRIPCIÓN"), w - 3, first, field == 1 and focus == "editor", readonly, field="detail")]
        body += [" " + row for row in _text_panel(S, K, "pbuf", _t("cal.box.prompt", "PROMPT PARA EL AGENTE"), w - 3, text_h - first, field == 2 and focus == "editor", readonly, field="prompt")]
    result = top + body + footer
    return [HL.clip(row, w - 1) for row in result[:h - 1]] + [""] * max(0, h - 1 - len(result))


def _queue_render(S, K, w, h):
    rows = P.task_queue()
    S["queue_rows"] = rows
    idx = min(S.get("queue_idx", 0), max(0, len(rows) - 1))
    S["queue_idx"] = idx
    cap = max(1, h - 10)
    start = max(0, min(idx - cap // 2, len(rows) - cap))
    body = [_t("cal.queue.intro", "Solo tareas marcadas LISTA; prioridad alta, luego fecha."), ""]
    for i, e in enumerate(rows[start:start + cap], start):
        body.append(HL.clip((K["C"] + K["BO"] if i == idx else K["GREY"]) +
                           ("> " if i == idx else "  ") + e["date"] + " · " +
                           ("! " if e.get("prio") == "alta" else "") + e["title"] + K["R"], w - 8))
    if not rows:
        body.append(_t("cal.queue.empty", "Sin tareas listas; l cambia borrador a lista."))
    body += ["", S.get("msg") or "",
             HL.keyline(K, (("↑↓", _t("common.hint.pick", "elige")),
                            ("Enter", _t("cal.hint.detail", "detalle")),
                            ("l", _t("cal.hint.to_draft", "devuelve a borrador")),
                            ("Esc", _t("cal.hint.back", "vuelve"))), max(10, w - 8))]
    lines = [""] + [" " + row for row in HL.full_box(
        _t("cal.box.queue", "COLA DE AGENTES · {n} listas", n=len(rows)),
        body, K, w - 3, len(body), True)]
    return [HL.clip(row, w - 1) for row in lines[:h - 1]] + [""] * max(0, h - 1 - len(lines))


# ── cuentas de Google Calendar (vista multi-cuenta, SOLO lectura) ───────────
# Lee gcal.list_accounts()/add_account()/remove_account()/rename_account(),
# todo FALLA-SUAVE: sin gcal (o en error) la vista queda vacía, nada levanta.
# El modelo de cuenta tolera `kind` ("ical" hoy, "oauth" mañana) — seam limpio
# para una futura cuenta de dos vías, sin construir OAuth aquí.
def _gcal():
    try:
        import gcal
        return gcal
    except Exception:
        return None


def _gcal_accounts():
    g = _gcal()
    if g is None:
        return []
    try:
        return g.list_accounts() or []
    except Exception:
        return []


def _ago_str(ts):
    """Antigüedad relativa localizada (reusa common.ago.*). "" si no hay."""
    if not ts:
        return ""
    try:
        s = max(0, int(time.time() - float(ts)))
    except Exception:
        return ""
    if s < 60:
        return _t("common.ago.sec", "hace {n}s", n=s)
    if s < 3600:
        return _t("common.ago.min", "hace {n}m", n=s // 60)
    if s < 86400:
        return _t("common.ago.hour", "hace {n}h", n=s // 3600)
    return _t("common.ago.day", "hace {n}d", n=s // 86400)


def _gcal_pares(S):
    """Atajos de ESTA vista, según el sub-modo (cabecera recorta, pie completo)."""
    view = S.get("g_view", "list")
    if view == "add":
        return (("Tab", _t("cal.hint.field", "campo")),
                ("Enter", _t("cal.g.hint.connect", "conecta")),
                ("Esc", _t("cal.hint.cancel", "cancela")))
    if view == "rename":
        return (("Enter", _t("cal.g.hint.rename", "renombra")),
                ("Esc", _t("cal.hint.cancel", "cancela")))
    if view == "confirm_rm":
        return (("Enter", _t("cal.g.hint.confirm", "confirma")),
                ("Esc", _t("cal.hint.cancel", "cancela")))
    return (("↑↓", _t("common.hint.pick", "elige")),
            ("a", _t("cal.g.hint.add", "conecta")),
            ("e", _t("cal.g.hint.rename", "renombra")),
            ("x", _t("cal.g.hint.remove", "quita")),
            ("q", _t("common.hint.menu", "menú")))


def _g_state_label(st):
    return {"ok": _t("cal.g.state.ok", "conectado"),
            "error": _t("cal.g.state.error", "URL inválida"),
            "nofetch": _t("cal.g.state.nofetch", "sin bajar aún")}.get(st, st)


def _gcal_list_body(S, K, accts, inner):
    """Las cuentas vinculadas: nombre + punto de estado, y debajo host · estado ·
    nº eventos · última sync · (del sistema). «ninguna todavía» si vacío. Al pie,
    la nota del seam de dos-vías (OAuth) — honesta: aún no existe."""
    out = []
    if not accts:
        out.append("%s%s%s" % (K["DK"], _t(
            "cal.g.none", "ninguna todavía — conecta tu primer calendario con a"),
            K["R"]))
    else:
        sel = S.get("g_sel", 0) % len(accts)
        S["g_sel"] = sel
        dotc = {"ok": K["OK"], "error": (K["BAD"] or K["B"]),
                "nofetch": K["DIM"]}
        for i, a in enumerate(accts):
            cur = (K["C"] + K["BO"] + K["PTR"] + K["R"] + " ") if i == sel \
                else "  "
            dot = "%s●%s" % (dotc.get(a["state"], K["DIM"]), K["R"])
            name = "%s%s%s" % ((K["WH"] + K["BO"]) if i == sel else K["GREY"],
                               a["label"], K["R"])
            kind = _t("cal.g.kind.oauth", "dos vías") \
                if a.get("kind") == "oauth" else _t("cal.g.kind.ical",
                                                    "iCal · solo lectura")
            out.append(HL.clip("%s%s %s   %s%s%s" % (
                cur, dot, name, K["DK"], kind, K["R"]), inner))
            # sub-línea: host · estado · eventos · sync · (del sistema)
            bits = ["%s%s%s" % (K["DK"], a["host"], K["R"]),
                    "%s%s%s" % (dotc.get(a["state"], K["DIM"]),
                                _g_state_label(a["state"]), K["R"])]
            if a["state"] == "ok":
                bits.append("%s%s%s" % (K["GREY"], _t(
                    "cal.g.row.events", "{n} eventos", n=a["events"]), K["R"]))
                ago = _ago_str(a.get("last_sync"))
                if ago:
                    bits.append("%s%s%s" % (K["DIM"], _t(
                        "cal.g.row.sync", "sync {ago}", ago=ago), K["R"]))
            if a.get("env"):
                bits.append("%s%s%s" % (K["DIM"], _t(
                    "cal.g.row.env", "del sistema"), K["R"]))
            sep = " %s·%s " % (K["DK"], K["R"])
            out.append(HL.clip("     " + sep.join(bits), inner))
    out.append("")
    out.append("%s%s%s" % (K["DIM"], _t(
        "cal.g.future",
        "Pronto: cuentas de dos vías (OAuth) para editar desde aquí."), K["R"]))
    return out


def _gcal_add_body(S, K, inner):
    """El paso a paso para obtener la «Dirección secreta en formato iCal» +
    los dos campos (nombre visible, URL oculta). El cursor marca el campo."""
    field = S.get("g_field", 0)
    out = ["%s%s%s" % (K["DIM"], _t(
        "cal.g.add.steps_head",
        "Para obtener la dirección secreta en formato iCal:"), K["R"])]
    for i in range(1, 6):
        out.append(HL.clip("%s%s%s" % (K["GREY"], _t(
            "cal.g.add.step%d" % i, "%d." % i), K["R"]), inner))
    out.append("")
    # campo 0: nombre (visible)
    out.append(_campo_etq(K, _t("cal.g.add.name_field",
                                "nombre (p. ej. Trabajo)"), field == 0, inner))
    nombre = S.get("g_label") or ""
    out.append(HL.clip("   " + nombre + ("▏" if field == 0 else ""), inner))
    out.append("")
    # campo 1: URL (oculta — nunca en pantalla; solo el conteo)
    out.append(_campo_etq(K, _t("cal.g.add.url_field",
                                "dirección secreta iCal · se pega oculta"),
                          field == 1, inner))
    n = len(S.get("g_url") or "")
    if n:
        masked = "•" * min(n, max(8, inner - 24))
        shown = "%s%s%s  %s%s%s" % (
            K["B2"], masked, K["R"], K["DIM"],
            _t("cal.g.add.url_pasted", "{n} caracteres pegados", n=n), K["R"])
    else:
        shown = "%s%s%s" % (K["DIM"], _t(
            "cal.g.add.url_empty",
            "pega aquí la URL — no se muestra en pantalla"), K["R"])
    out.append(HL.clip("   " + shown + ("▏" if field == 1 and not n else ""),
                       inner))
    return out


def _gcal_rename_body(S, K, accts, inner):
    sel = S.get("g_sel", 0) % max(1, len(accts))
    label = accts[sel]["label"] if accts else ""
    out = [HL.clip("%s%s%s" % (K["DK"], label, K["R"]), inner), ""]
    out.append(_campo_etq(K, _t("cal.g.rename.field", "nuevo nombre"), True,
                          inner))
    out.append(HL.clip("   " + (S.get("g_label") or "") + "▏", inner))
    return out


def _gcal_confirm_body(S, K, accts, inner):
    sel = S.get("g_sel", 0) % max(1, len(accts))
    label = accts[sel]["label"] if accts else ""
    return [HL.clip("%s%s%s" % (K["GREY"], _t(
        "cal.g.confirm.body", "Se desvincula «{label}»; sus eventos dejan de "
        "verse.", label=label), K["R"]), inner),
        "",
        HL.clip("%s%s%s" % (K["DIM"], _t(
            "cal.g.confirm.note",
            "No borra nada en Google; puedes volver a conectarla."), K["R"]),
            inner)]


def _gcal_render(S, K, w, h):
    accts = _gcal_accounts()
    pares = _gcal_pares(S)
    L = HL.screen_header(K, w, h, _t("cal.g.subtitle",
                                     "cuentas de google calendar"), hints=pares)
    inner = w - 7
    view = S.get("g_view", "list")
    if view == "add":
        title = _t("cal.g.add.title", "CONECTAR UN CALENDARIO DE GOOGLE")
        body = _gcal_add_body(S, K, inner)
    elif view == "rename":
        title = _t("cal.g.rename.title", "RENOMBRAR CUENTA")
        body = _gcal_rename_body(S, K, accts, inner)
    elif view == "confirm_rm":
        title = _t("cal.g.confirm.title", "¿QUITAR ESTA CUENTA?")
        body = _gcal_confirm_body(S, K, accts, inner)
    else:
        title = _t("cal.g.box", "CUENTAS DE GOOGLE CALENDAR")
        body = _gcal_list_body(S, K, accts, inner)
    box = HL.full_box(title, body, K, w - 3, len(body), True, border=K["C"])
    L += [" " + x for x in box]
    L.append("")
    L.append((" %s%s%s" % (K["B2"], S.get("g_msg", ""), K["R"]))
             if S.get("g_msg") else "")
    L.append(HL.foot_hints(K, pares, w))
    L = [HL.clip(x, w - 1) for x in L[:h - 1]]
    return L + [""] * max(0, (h - 1) - len(L))


def _gcal_connect(S):
    """Valida+conecta la cuenta tecleada: fetch de prueba SÍNCRONO (como el CLI
    set-url). Al terminar vuelve a la lista con el resultado en g_msg."""
    g = _gcal()
    if g is None:
        S["g_msg"] = _t("cal.g.msg.save_failed", "no pude guardarla")
        return
    url_v = (S.get("g_url") or "").strip()
    if not url_v:
        S["g_msg"] = _t("cal.g.msg.need_url", "pega la dirección iCal primero")
        return
    try:
        r = g.add_account(S.get("g_label") or "", url_v)
    except Exception:
        r = {"ok": False, "error": "save_failed"}
    if r.get("ok"):
        S["g_msg"] = _t("cal.g.msg.connected", "conectado ✓ · {n} eventos",
                        n=r.get("events", 0))
        S["g_view"], S["g_url"], S["g_label"] = "list", "", ""
        S["g_sel"] = 0
    else:
        S["g_msg"] = {
            "not_https": _t("cal.g.msg.not_https",
                            "eso no es una URL https de Google"),
            "duplicate": _t("cal.g.msg.duplicate",
                            "esa cuenta ya está vinculada"),
            "fetch_failed": _t("cal.g.msg.fetch_failed",
                               "no pude bajar el calendario (¿red o URL "
                               "revocada?)"),
            "save_failed": _t("cal.g.msg.save_failed", "no pude guardarla"),
        }.get(r.get("error"), _t("cal.g.msg.save_failed", "no pude guardarla"))


def _gcal_key(S, key):
    view = S.get("g_view", "list")
    accts = _gcal_accounts()
    if view == "add":
        if key == "\x1b":
            S["g_view"], S["g_url"], S["g_label"], S["g_msg"] = \
                "list", "", "", ""
            return True
        if key in ("tab", "right_tab"):
            S["g_field"] = 1 - S.get("g_field", 0)
            return True
        if key in ("\r", "\n", "\x13"):
            _gcal_connect(S)
            return True
        name = "g_label" if S.get("g_field", 0) == 0 else "g_url"
        buf = S.get(name) or ""
        if key in ("\x7f", "\b", "\x08"):
            S[name] = buf[:-1]
        elif len(key) == 1 and key.isprintable():
            # un pegado llega carácter a carácter por el driver: se acumula.
            if len(buf) < 4096:
                S[name] = buf + key
        return True
    if view == "rename":
        if key == "\x1b":
            S["g_view"], S["g_label"], S["g_msg"] = "list", "", ""
            return True
        if key in ("\r", "\n", "\x13"):
            g = _gcal()
            label = (S.get("g_label") or "").strip()
            if not label:
                S["g_msg"] = _t("cal.g.msg.rename_empty",
                                "el nombre no puede ir vacío")
                return True
            sel = S.get("g_sel", 0) % max(1, len(accts))
            r = {}
            if g is not None and accts:
                try:
                    r = g.rename_account(accts[sel]["id"], label)
                except Exception:
                    r = {"ok": False, "error": "save_failed"}
            if r.get("ok"):
                S["g_msg"] = _t("cal.g.msg.renamed", "renombrada: {label}",
                                label=label)
            elif r.get("error") == "env":
                S["g_msg"] = _t("cal.g.msg.env", "cuenta del sistema (variable "
                                "{var}) — gestiónala allá", var="WORKSPACE_"
                                "GCAL_ICS_URL")
            else:
                S["g_msg"] = _t("cal.g.msg.save_failed", "no pude guardarla")
            S["g_view"], S["g_label"] = "list", ""
            return True
        buf = S.get("g_label") or ""
        if key in ("\x7f", "\b", "\x08"):
            S["g_label"] = buf[:-1]
        elif len(key) == 1 and key.isprintable() and len(buf) < 60:
            S["g_label"] = buf + key
        return True
    if view == "confirm_rm":
        if key in ("\r", "\n", "y", "Y"):
            g = _gcal()
            sel = S.get("g_sel", 0) % max(1, len(accts))
            r = {}
            if g is not None and accts:
                try:
                    r = g.remove_account(accts[sel]["id"])
                except Exception:
                    r = {"ok": False, "error": "save_failed"}
            if r.get("ok"):
                S["g_msg"] = _t("cal.g.msg.removed", "desvinculada: {label}",
                                label=accts[sel]["label"])
                S["g_sel"] = 0
            elif r.get("error") == "env":
                S["g_msg"] = _t("cal.g.msg.env", "cuenta del sistema (variable "
                                "{var}) — gestiónala allá",
                                var="WORKSPACE_GCAL_ICS_URL")
            else:
                S["g_msg"] = _t("cal.g.msg.save_failed", "no pude guardarla")
            S["g_view"] = "list"
            return True
        if key in ("\x1b", "n", "N", "q", "Q"):
            S["g_view"] = "list"
        return True
    # ── vista LISTA ──────────────────────────────────────────────────────
    if key in ("q", "Q", "\x1b"):
        S["modo"] = "nav"
        S["g_msg"] = ""
        return True
    if key in ("up", "down", "tab", "right_tab") and accts:
        step = -1 if key in ("up", "right_tab") else 1
        S["g_sel"] = (S.get("g_sel", 0) + step) % len(accts)
    elif key in ("a", "A"):
        S.update(g_view="add", g_field=0, g_url="", g_label="", g_msg="")
    elif key in ("e", "E", "r", "R") and accts:
        sel = S.get("g_sel", 0) % len(accts)
        S.update(g_view="rename", g_label=accts[sel]["label"], g_msg="")
    elif key in ("x", "X", "d", "D") and accts:
        S["g_view"], S["g_msg"] = "confirm_rm", ""
    elif key in ("a", "A", "e", "E", "x", "X", "d", "D"):
        S["g_msg"] = _t("cal.g.msg.none_sel", "no hay cuenta seleccionada")
    return True


def _edit_key(S, key):
    field = S.get("campo", 0)
    name = ("buf", "nbuf", "pbuf")[field]
    limit = (126, P.NOTES_MAX, P.PROMPT_MAX)[field]
    text = S.get(name) or ""
    cursors = S.setdefault("text_cursor", {})
    pos = min(cursors.get(name, len(text)), len(text))
    if key == "\x1b":
        S["modo"], S["msg"] = "nav", _t("cal.msg.cancelled", "cancelado")
        return True
    if key == "\x16":                       # Ctrl+V — adjuntar imagen al campo
        _attach_image(S)
        return True
    if key == "\x18":                       # Ctrl+X — quitar la imagen enfocada
        _remove_focused_image(S)
        return True
    if key in ("tab", "right_tab"):
        S["campo"] = (field + (1 if key == "tab" else -1)) % 3
        return True
    if key == "\x13" or (key in ("\r", "\n") and field == 0):
        _persist_form(S)
        return True
    if key in ("\x02", "\x06", "pageup", "pagedown"):
        offsets = S.setdefault("text_scroll", {})
        offsets[name] = max(0, offsets.get(name, 0) + (-5 if key in ("\x02", "pageup") else 5))
        return True
    if key in ("left", "right", "home", "end", "up", "down"):
        if key == "left": pos = max(0, pos - 1)
        elif key == "right": pos = min(len(text), pos + 1)
        elif key == "home": pos = text.rfind("\n", 0, pos) + 1
        elif key == "end":
            end = text.find("\n", pos)
            pos = len(text) if end < 0 else end
        elif key == "up":
            start = text.rfind("\n", 0, pos) + 1
            if start:
                before = text.rfind("\n", 0, start - 1) + 1
                pos = min(start - 1, before + pos - start)
        elif key == "down":
            start = text.rfind("\n", 0, pos) + 1
            end = text.find("\n", pos)
            if end >= 0:
                after = text.find("\n", end + 1)
                pos = min(len(text) if after < 0 else after, end + 1 + pos - start)
    elif key in ("\x7f", "\b", "\x08"):
        if pos:
            text, pos = text[:pos - 1] + text[pos:], pos - 1
    elif key == "delete":
        text = text[:pos] + text[pos + 1:]
    elif key in ("\r", "\n") or (len(key) == 1 and key.isprintable()):
        addition = "\n" if key in ("\r", "\n") else key
        if len(text) >= limit:
            S["msg"] = _t("cal.msg.char_limit", "límite de {n} caracteres; guarda o reduce el texto", n=limit)
            return True
        text, pos = text[:pos] + addition + text[pos:], pos + 1
    S[name], cursors[name] = text, pos
    S.setdefault("text_scroll", {}).pop(name, None)
    return True


def _accion(S, key):
    S["msg"] = ""
    if S["modo"] in ("add", "edit", "ver"):
        S.setdefault("form_date", S["sel"])
        if key == "\x07":
            S["form_focus"] = "editor" if S.get("form_focus") == "calendar" else "calendar"
            return True
        if S.get("form_focus") == "calendar":
            return _calendar_form_key(S, key)
    if S["modo"] == "queue":
        rows = P.task_queue()
        idx = min(S.get("queue_idx", 0), max(0, len(rows) - 1))
        if key in ("q", "\x1b", "v"):
            S["modo"] = "nav"
        elif key in ("up", "down", "tab"):
            S["queue_idx"] = (idx + (-1 if key == "up" else 1)) % max(1, len(rows))
        elif key in ("\r", "\n") and rows:
            e = rows[idx]
            S["sel"] = datetime.date.fromisoformat(e["date"])
            _open_detail(S, e)
        elif key in ("l", "L") and rows:
            _toggle_ready(S, rows[idx])
        return True
    if S["modo"] == "trash":
        rows = P.trash_events()
        idx = min(S.get("trash_idx", 0), max(0, len(rows) - 1))
        if key in ("q", "Q", "\x1b", "b", "B"):
            S["modo"] = "nav"
        elif key in ("up", "down", "tab"):
            S["trash_idx"] = (idx + (-1 if key == "up" else 1)) % max(1, len(rows))
        elif key in ("r", "R", "\r", "\n") and rows:
            e = rows[idx]
            S["msg"] = _t("cal.msg.restored", "restaurado: {title}", title=e["title"]) \
                if P.restore_event(e["id"]) else _t("cal.msg.restore_fail", "no pude restaurarlo")
            S["trash_idx"] = min(idx, max(0, len(P.trash_events()) - 1))
        return True
    if S["modo"] == "gcal":
        return _gcal_key(S, key)
    if S["modo"] == "move":
        if key in ("\x1b", "q", "Q"):
            S["sel"], S["modo"] = S["move_origin"], "nav"
            S["msg"] = _t("cal.msg.move_cancelled", "movimiento cancelado")
        elif key in ("\r", "\n"):
            e = S["moving"]
            if P.move_event(e["id"], S["sel"].isoformat()):
                S["modo"], S["ev"] = "nav", 0
                S["msg"] = _t("cal.msg.moved", "movido a {date}", date=S["sel"].isoformat())
            else:
                S["msg"] = _t("cal.msg.move_fail", "no pude moverlo; el evento conserva su fecha")
        elif key in ("left", "right", "up", "down"):
            S["sel"] += datetime.timedelta(days={"left": -1, "right": 1, "up": -7, "down": 7}[key])
        elif key.lower() in ("n", "p"):
            S["sel"] = _mes_mov(S["sel"], 1 if key.lower() == "n" else -1)
        elif key.lower() == "t":
            S["sel"] = datetime.date.today()
        return True
    if S["modo"] == "ver":
        # vista DETALLE: leer la descripción y actuar sobre ESE evento
        e = _sel_ev(S)
        if key in ("\x1b", "\r", "\n", "q", "Q") or e is None:
            S["modo"] = "nav"
            return True
        if key in ("l", "L"):
            _toggle_ready(S, e)
            return True
        if key == "\x16":                   # Ctrl+V — adjuntar imagen (local)
            if e.get("google"):
                S["msg"] = _t("cal.msg.g_readonly", "evento de Google — solo lectura")
            else:
                _attach_image(S)
            return True
        if key == "\x18":                   # Ctrl+X — quitar la imagen enfocada
            if not e.get("google"):
                _remove_focused_image(S)
            return True
        if key in ("\x02", "\x06", "pageup", "pagedown"):
            name = "pbuf" if S.get("campo") == 2 else "nbuf"
            offsets = S.setdefault("text_scroll", {})
            offsets[name] = max(0, offsets.get(name, 0) + (-5 if key in ("\x02", "pageup") else 5))
            return True
        if key in ("m", "M"):
            _abrir_mover(S, e)
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
        if key == "tab":
            S["campo"] = 1 if S.get("campo") == 2 else 2
        return True
    if S["modo"] in ("add", "edit"):
        return _edit_key(S, key)
    if key in ("q", "Q", "\x03"):
        return False
    if key in ("l", "L"):
        e = _sel_ev(S)
        if e:
            _toggle_ready(S, e)
        else:
            S["msg"] = _t("cal.msg.no_task_mark", "no hay tarea que marcar")
    elif key in ("v", "V"):
        S["modo"], S["queue_idx"] = "queue", 0
    elif key in ("g", "G"):
        S["modo"], S["g_view"], S["g_sel"], S["g_msg"] = "gcal", "list", 0, ""
    elif key in ("b", "B"):
        S["modo"], S["trash_idx"] = "trash", 0
        P.trash_events()
    elif key in ("m", "M"):
        e = _sel_ev(S)
        if e:
            _abrir_mover(S, e)
        else:
            S["msg"] = _t("cal.msg.no_move_here", "no hay evento que mover aquí")
    elif key == "left":
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
            _open_detail(S, _sel_ev(S))
        else:
            _new_form(S)
    elif key in ("a", "A"):
        _new_form(S)
    elif key in ("e", "E"):
        e = _sel_ev(S)
        if e:
            _abrir_edicion(S, e)
        else:
            S["msg"] = _t("cal.msg.no_edit_here", "no hay evento que editar en este día")
    elif key in ("x", "X", " "):
        e = _sel_ev(S)
        if e:
            _toggle_hecha(S, e)
        else:
            S["msg"] = _t("cal.msg.no_done_here", "no hay nada que tachar aquí")
    elif key in ("f", "F", "!"):
        e = _sel_ev(S)
        if e:
            _toggle_prioridad(S, e)
    elif key in ("d", "D"):
        e = _sel_ev(S)
        if e:
            _borrar_sel(S, e)
        else:
            S["msg"] = _t("cal.msg.no_delete_here", "no hay nada que borrar aquí")
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
    import codecs
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
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
            ch = decoder.decode(os.read(fd, 1))
            if not ch:
                continue
            key = ch
            if ch == "\x1b":
                if select.select([fd], [], [], 0.05)[0]:
                    seq = ""
                    while select.select([fd], [], [], 0.02)[0]:
                        seq += os.read(fd, 1).decode("ascii", "ignore")
                        if len(seq) >= 2 and (seq[-1].isalpha() or seq[-1] == "~"):
                            break
                        if len(seq) >= 16:
                            break
                    key = {"[A": "up", "[B": "down", "[C": "right",
                           "[D": "left", "[H": "home", "[F": "end", "[Z": "right_tab",
                           "[1~": "home", "[4~": "end", "[3~": "delete",
                           "[5~": "pageup", "[6~": "pagedown"}.get(seq, "")
                else:
                    key = "\x1b"
            elif ch == "\t":
                key = "tab"
            if not _accion(S, key):
                break
            if S.get("await_attach"):
                # sin imagen en portapapeles → prompt CLÁSICO fuera del
                # alt-screen (raw mode no pega rutas fiables); modo cocido,
                # pedir la ruta, re-entrar al alt-screen y redibujar.
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
                    tout.write("\033[?1049l\033[?25h")
                    tout.flush()
                    print("\n" + _t("cal.img.classic_head",
                                    "Arrastra la imagen a la terminal y pega su "
                                    "ruta (Enter vacío = cancelar):"))
                    try:
                        _path = input("  > ")
                    except (EOFError, KeyboardInterrupt):
                        _path = ""
                finally:
                    tty.setraw(fd)
                    tout.write("\033[?1049h")
                    tout.flush()
                _finish_classic_attach(S, _path)
                _draw(tout, S, first=True)
                continue
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
                       "K": "left", "G": "home", "O": "end",
                       "S": "delete", "I": "pageup", "Q": "pagedown"}.get(a, "")
            elif ch == "\t":
                key = "tab"
            else:
                key = ch
            if not key:
                continue
            if not _accion(S, key):
                break
            if S.get("await_attach"):
                # sin imagen en portapapeles → prompt clásico fuera del alt-screen
                tout.write("\033[?1049l\033[?25h")
                tout.flush()
                print("\n" + _t("cal.img.classic_head",
                                "Arrastra la imagen a la terminal y pega su "
                                "ruta (Enter vacío = cancelar):"))
                try:
                    _path = input("  > ")
                except (EOFError, KeyboardInterrupt):
                    _path = ""
                tout.write("\033[?1049h")
                tout.flush()
                _finish_classic_attach(S, _path)
                _draw(tout, S, first=True)
                continue
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
