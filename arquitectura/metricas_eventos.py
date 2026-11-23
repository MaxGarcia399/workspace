#!/usr/bin/env python3
"""WORKSPACE · arquitectura/metricas_eventos — las métricas desde el registro de eventos (F5).

    python3 -m arquitectura.metricas_eventos [--dias N] [--json] [--comparar]

Por agente y por motor: sesiones (y cuántas se cortaron sin cerrar), turnos, herramientas (y cuáles fallaron),
duración y errores, leídos del registro de eventos de cada pestaña (arquitectura/registro: lo que anotan los hooks
del paquete y la página). Nada de transcripts. El uso oficial (`costo_usd`) solo donde la capa de control lo da:
las corridas de la página lo anotan en su fin de turno.

LADO A LADO con las de hoy (metricas.py + metricas_motores/, que leen los transcripts de cada motor): no las
reemplaza todavía. `--comparar` pone, por agente y motor, lo de aquí junto a lo de sus filas (corridas-AAAA-MM),
para la semana de comparación que pide el plan. Lo que se podrá retirar cuando los 9 motores anoten el registro:
metricas_motores/ (los parsers de transcript) y la lectura de transcripts de metricas.py. Stdlib; solo lee."""
import datetime as _dt
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

CAMPOS = ("sesiones", "cortadas", "turnos", "herramientas", "fallidas", "errores", "duracion_s")
#: Renglones del registro que no son del motor ni abren una sesión.
_NO_SON_DEL_MOTOR = ("conversacion", "tarea", "pregunta", "respuesta")


def _t(ts):
    try:
        s = str(ts)
        return _dt.datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s).timestamp()
    except (ValueError, TypeError):
        return None


def _vacio():
    return dict({k: 0 for k in CAMPOS}, por_herramienta={}, costo_usd=None, pagina=0)


def _sumar(a, b):
    for k in CAMPOS + ("pagina",):
        a[k] += b[k]
    for n, c in b["por_herramienta"].items():
        a["por_herramienta"][n] = a["por_herramienta"].get(n, 0) + c
    if b["costo_usd"] is not None:
        a["costo_usd"] = round((a["costo_usd"] or 0.0) + b["costo_usd"], 6)
    return a


def medir(eventos, desde=None):
    """{motor: medidas} de los eventos de UNA pestaña (en orden). Una sesión empieza en su session_start (lo de
    antes del primero cuenta como una) y se corta si termina sin session_end."""
    por = {}
    abiertas = {}                                   # motor → [t_ini, t_ult, cerrada]
    for e in eventos:
        if e["momento"] in _NO_SON_DEL_MOTOR:       # lo que anota Workspace (el número al abrir, la tarea…)
            continue
        t = _t(e.get("ts"))
        if desde is not None and (t is None or t < desde):
            continue
        motor = e.get("motor") or "?"
        m = por.setdefault(motor, _vacio())
        d = e.get("datos") or {}
        mo = e["momento"]
        ses = abiertas.get(motor)
        if mo == "session_start" or ses is None:
            if ses is not None:
                m["cortadas"] += 0 if ses[2] else 1
                m["duracion_s"] += max(0.0, (ses[1] or 0) - (ses[0] or 0))
            ses = abiertas[motor] = [t, t, False]
            m["sesiones"] += 1
        if t is not None:
            ses[0] = ses[0] if ses[0] is not None else t
            ses[1] = t
        if mo == "turn_end":
            m["turnos"] += 1
            if d.get("via") == "pagina":
                m["pagina"] += 1
            if d.get("motivo") == "error":
                m["errores"] += 1
            if isinstance(d.get("costo_usd"), (int, float)):
                m["costo_usd"] = round((m["costo_usd"] or 0.0) + float(d["costo_usd"]), 6)
        elif mo == "pre_tool":
            n = str(d.get("tool_name") or "?")
            m["herramientas"] += 1
            m["por_herramienta"][n] = m["por_herramienta"].get(n, 0) + 1
        elif mo == "post_tool" and d.get("ok") is False:
            m["fallidas"] += 1
        elif mo == "error":
            m["errores"] += 1
        elif mo == "session_end":
            ses[2] = True
    for motor, ses in abiertas.items():             # la última sesión de cada motor
        m = por[motor]
        m["duracion_s"] += max(0.0, (ses[1] or 0) - (ses[0] or 0))
        m["cortadas"] += 0 if ses[2] else 1
    for m in por.values():
        m["duracion_s"] = round(m["duracion_s"], 1)
    return por


def cerebros_conocidos():
    """[(agente, carpeta)] de los cerebros que conoce Workspace."""
    try:
        import uninstall
        return list(uninstall.brains())
    except Exception:
        return []


def medir_todo(cerebros=None, dias=None, ahora=None):
    """{"agentes": {agente: {motor: medidas}}, "motores": {motor: medidas}, "desde": iso|None}."""
    from arquitectura import registro
    desde = None
    if dias:
        desde = (ahora or _dt.datetime.now(_dt.timezone.utc).timestamp()) - float(dias) * 86400
    agentes, motores = {}, {}
    for agente, brain in (cerebros if cerebros is not None else cerebros_conocidos()):
        d = registro.carpeta(brain)
        try:
            archivos = sorted(f for f in os.listdir(d) if f.endswith(".jsonl"))
        except OSError:
            continue
        mio = agentes.setdefault(agente, {})
        for f in archivos:
            for motor, m in medir(registro.leer(brain, f[:-len(".jsonl")])[0], desde).items():
                _sumar(mio.setdefault(motor, _vacio()), m)
                _sumar(motores.setdefault(motor, _vacio()), m)
    return {"agentes": agentes, "motores": motores,
            "desde": _dt.datetime.fromtimestamp(desde, _dt.timezone.utc).isoformat() if desde else None}


def _de_hoy(desde=None):
    """{(agente, motor): {turnos, herramientas, errores, duracion_s, costo_usd}} de las filas de las métricas de hoy
    (corridas-AAAA-MM.jsonl), para ponerlas al lado. Solo lee; {} si no hay."""
    out = {}
    try:
        import metricas
        base = metricas.carpeta()
        archivos = []
        for raiz, _ds, fs in os.walk(base):
            archivos += [os.path.join(raiz, f) for f in fs if f.startswith("corridas-") and f.endswith(".jsonl")]
    except Exception:
        return out
    for ruta in sorted(archivos):
        try:
            with open(ruta, encoding="utf-8") as fh:
                filas = [json.loads(ln) for ln in fh if ln.strip()]
        except (OSError, ValueError):
            continue
        for f in filas:
            if not isinstance(f, dict):
                continue
            t = _t(f.get("fin") or f.get("inicio"))
            if desde is not None and (t is None or t < desde):
                continue
            k = (str(f.get("agente") or "?"), str(f.get("motor") or "?"))
            a = out.setdefault(k, {"turnos": 0, "herramientas": 0, "errores": 0, "duracion_s": 0.0,
                                   "costo_usd": None})
            a["turnos"] += _numero(f.get("mensajes_usuario"))
            a["herramientas"] += _numero(f.get("herramientas"))
            a["errores"] += _numero(f.get("respuestas_error"))
            a["duracion_s"] += float(_numero(f.get("duracion_activa_s")))
            if isinstance(f.get("costo_usd"), (int, float)):
                a["costo_usd"] = (a["costo_usd"] or 0.0) + float(f["costo_usd"])
    return out


def _numero(v):
    """Un número de una fila de hoy: el número, la suma de un dict de conteos o el largo de una lista."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, dict):
        return sum(_numero(x) for x in v.values() if not isinstance(x, (dict, list)))
    if isinstance(v, list):
        return len(v)
    return 0


def comparar(medidas, dias=None, ahora=None):
    """[{agente, motor, eventos: {...}, hoy: {...}}]: lo de aquí junto a lo de las métricas de hoy."""
    desde = None
    if dias:
        desde = (ahora or _dt.datetime.now(_dt.timezone.utc).timestamp()) - float(dias) * 86400
    hoy = _de_hoy(desde)
    filas, vistos = [], set()
    for agente, por_motor in medidas["agentes"].items():
        for motor, m in por_motor.items():
            vistos.add((agente, motor))
            filas.append({"agente": agente, "motor": motor,
                          "eventos": {k: m[k] for k in ("turnos", "herramientas", "errores", "duracion_s")},
                          "hoy": hoy.get((agente, motor))})
    for (agente, motor), h in sorted(hoy.items()):
        if (agente, motor) not in vistos:
            filas.append({"agente": agente, "motor": motor, "eventos": None, "hoy": h})
    return filas


def texto(medidas, filas=None):
    lineas = ["Métricas desde los eventos%s (sin transcripts):" % (" desde %s" % medidas["desde"][:10]
                                                                    if medidas["desde"] else "")]
    for agente, por_motor in sorted(medidas["agentes"].items()):
        for motor, m in sorted(por_motor.items()):
            top = ", ".join("%s ×%d" % kv for kv in sorted(m["por_herramienta"].items(), key=lambda kv: -kv[1])[:5])
            lineas.append("  %s · %s: %d sesiones (%d sin cerrar) · %d turnos · %d herramientas%s · %d errores · %s"
                          % (agente, motor, m["sesiones"], m["cortadas"], m["turnos"], m["herramientas"],
                             " (%s)" % top if top else "", m["errores"], _duracion(m["duracion_s"]))
                          + (" · $%.2f" % m["costo_usd"] if m["costo_usd"] is not None else ""))
    if filas is not None:
        lineas.append("Lado a lado con las de hoy (turnos · herramientas · errores):")
        for f in filas:
            e, h = f["eventos"], f["hoy"]
            lineas.append("  %s · %s: eventos %s · hoy %s" % (
                f["agente"], f["motor"],
                "%d · %d · %d" % (e["turnos"], e["herramientas"], e["errores"]) if e else "—",
                "%d · %d · %d" % (h["turnos"], h["herramientas"], h["errores"]) if h else "—"))
    return "\n".join(lineas)


def _duracion(s):
    s = int(s or 0)
    return "%dh %02dm" % (s // 3600, s % 3600 // 60) if s >= 3600 else "%dm %02ds" % (s // 60, s % 60)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    dias = None
    if "--dias" in argv:
        try:
            dias = float(argv[argv.index("--dias") + 1])
        except (IndexError, ValueError):
            print("uso: python3 -m arquitectura.metricas_eventos [--dias N] [--json] [--comparar]")
            return 2
    medidas = medir_todo(dias=dias)
    filas = comparar(medidas, dias) if "--comparar" in argv else None
    if "--json" in argv:
        print(json.dumps(dict(medidas, comparar=filas) if filas is not None else medidas, ensure_ascii=False,
                         indent=2))
    else:
        print(texto(medidas, filas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
