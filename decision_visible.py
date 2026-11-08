#!/usr/bin/env python3
"""WORKSPACE · decision_visible — lo que se VE de Decisores.

Las líneas «◆ <modelo>: …» que ve el socio (en el chat, en el aviso del hub, en
la barra de estado), lo que cambió cada decisión (Historial), la línea de la
última sesión (Evals, Skills) y el aviso al agente cuando Decisores cambia a
media sesión.

Todo pasa por `encendido()`: con Decisores APAGADO (sin modelo, o ningún uso
prendido) ninguna función de aquí agrega nada — ni líneas, ni contadores, ni
inyección, ni archivos — y lo de siempre sale byte-idéntico. Observe es en
silencio: solo suggest y apply se ven. Stdlib, falla-suave (jamás levanta
hacia quien llama). Mac y Windows.
"""
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SIMBOLO = "◆"
#: Errores de entrada (no se le preguntó a nadie): sin línea para el socio.
_SIN_LINEA = ("bad_point", "need_question", "need_options", "bad_input", "off", "use_off")
#: La línea de la última sesión caduca (una sesión de hace semanas ya no es «la última»).
ULTIMA_MAX_S = 14 * 86400
#: Las líneas de base por sesión (aviso a media sesión) se limpian solas.
SESION_MAX_S = 14 * 86400
#: Lo que se lee de la cola de la bitácora para contar «hoy» (barato: la barra
#: de estado lo pide en cada refresco, en un proceso nuevo cada vez).
HOY_COLA_BYTES = 256 * 1024


def _t(key, es, **kw):
    """Sigue ui.lang (lo que lee el socio y el agente)."""
    try:
        import decision_errors
        return decision_errors._t(key, es, **kw)
    except Exception:
        try:
            return es.format(**kw) if kw else es
        except Exception:
            return es


def _D():
    import decisions
    return decisions


def encendido():
    """¿Decisores está prendido? Un modelo activo y al menos un uso que no esté
    apagado. Sin eso, nada de lo de este módulo se ve ni se escribe."""
    try:
        D = _D()
        if D.global_model() == D.OFF:
            return False
        return any(D.point_conf(p)["level"] != "off" for p in D.POINT_IDS)
    except Exception:
        return False


def _nombre(did):
    """El nombre (META label) del modelo que respondió; sin dato, el general; sin
    modelo, «Decisores». Nunca un nombre fijo: cambia con cada modelo de decisión."""
    try:
        D = _D()
        did = did or D.global_model()
        return D.decider_label(did) if did and did != D.OFF else "Decisores"
    except Exception:
        return str(did or "Decisores").capitalize()


def _pct(p):
    try:
        if p is None:
            return None
        return int(round(float(p) * 100))
    except (TypeError, ValueError):
        return None


def _corto(texto, tope=48):
    s = " ".join(str(texto or "").split())
    return s if len(s) <= tope else s[:tope - 1].rstrip() + "…"


def _letra(i):
    try:
        i = int(i)
    except (TypeError, ValueError):
        return ""
    return chr(ord("A") + i) if 0 <= i < 26 else str(i + 1)


def _eleccion(choice, index=None, tope=40):
    """La opción como se le dice al socio: su texto, o «opción B» si es larga
    (una instrucción entera en Mejor prompt)."""
    s = " ".join(str(choice or "").split())
    if len(s) <= tope or index is None:
        return _corto(s, tope + 8)
    return _t("decisores.visible.option", "opción {l}", l=_letra(index))


# ── EL formato de toda intervención ─────────────────────────────────────────
def para_el_socio():
    """El recordatorio que va JUNTO a cada línea ◆ que le llega al agente: no
    depende de que recuerde la regla de su arranque (un motor envuelto la
    pierde al compactar)."""
    return _t("decisores.visible.para_el_socio", "Muéstrale esta línea al socio en tu bloque ◆ "
              "al final de tu respuesta.")


def _modo(modo):
    return (_t("decisores.visible.applied", "aplicado") if modo == "apply"
            else _t("decisores.visible.suggested", "sugerido"))


def formato(m, que, p, modo):
    """«◆ <modelo>: <qué hizo> · <NN %> · <aplicado|sugerido>» — el MISMO
    formato en el chat (display, Memoria, Seguridad, la última sesión, lo que
    el agente no vio). Sin el %, si el modelo no dio su probabilidad."""
    if p is None:
        return _t("decisores.visible.line_nop", "{s} {m}: {que} · {q}", s=SIMBOLO, m=m, que=que,
                  q=_modo(modo))
    return _t("decisores.visible.line", "{s} {m}: {que} · {p} % · {q}", s=SIMBOLO, m=m, que=que,
              p=p, q=_modo(modo))


# ── (a) la línea `display` de una consulta de agente ────────────────────────
def linea_agente(out):
    """«◆ <modelo>: tabla · 87 % · sugerido» / «… · aplicado» para la respuesta de
    `workspace decidir` / `decidir` (el agente se la muestra al socio). '' en
    observe (decide en silencio), con el uso apagado o si no se mandó nada."""
    try:
        if not isinstance(out, dict):
            return ""
        m = _nombre(out.get("decider"))
        if not out.get("ok"):
            if out.get("mode") != "error" or out.get("error_code") in _SIN_LINEA:
                return ""
            if (out.get("error_detail") or {}).get("breaker"):     # ni se le preguntó
                return _t("decisores.visible.agent_paused", "{s} {m}: en pausa tras un fallo de "
                          "red · decide el agente", s=SIMBOLO, m=m)
            return _t("decisores.visible.agent_failed", "{s} {m}: no respondió · decide el agente",
                      s=SIMBOLO, m=m)
        modo = out.get("mode")
        if modo not in ("suggest", "apply"):
            return ""
        return formato(m, _eleccion(out.get("choice"), out.get("index")), _pct(out.get("p")), modo)
    except Exception:
        return ""


# ── (b) Seguridad: la línea que se suma al aviso ────────────────────────────
def linea_seguridad(v):
    """«◆ <modelo>: subió el aviso a riesgo alto · 92 % · aplicado» (decide, «alto»)
    o «◆ <modelo>: ve riesgo bajo; el aviso no cambia · 97 % · sugerido» (todo lo
    demás: el decisor puede subir el riesgo, nunca bajarlo). '' en observe o
    apagado."""
    try:
        if not v or v.get("mode") not in ("suggest", "apply"):
            return ""
        c = str(v.get("choice") or "").strip().lower()
        p = _pct(v.get("p")) if v.get("p_known", True) else None
        sube = v.get("mode") == "apply" and c == "alto"
        return formato(_nombre(v.get("decider")), _que("workspace.security", c, sube), p,
                       "apply" if sube else "suggest")
    except Exception:
        return ""


def _que(point, c, aplicado, nota=""):
    """El «qué hizo» de cada uso, en palabras del socio."""
    c = " ".join(str(c or "").split())
    if point == "workspace.memory":
        return (_t("decisores.visible.q_memory_apply", "guardé la nota como {c}", c=c) if aplicado
                else _t("decisores.visible.q_memory", "la nota parece {c}", c=c))
    if point == "workspace.security":
        return (_t("decisores.visible.q_security_apply", "subió el aviso a riesgo alto") if aplicado
                else _t("decisores.visible.q_security", "ve riesgo {c}; el aviso no cambia", c=c))
    if point == "workspace.evals":
        return (_t("decisores.visible.q_evals_apply", "tu última sesión quedó «{c}»", c=c) if aplicado
                else _t("decisores.visible.q_evals", "tu última sesión parece «{c}»", c=c))
    if point == "workspace.skills":
        que = (_t("decisores.visible.q_skills_yes", "tu última sesión amerita una skill")
               if c.lower() in ("sí", "si", "yes") else
               _t("decisores.visible.q_skills_no", "tu última sesión no amerita una skill"))
        if nota == "throttled":
            que += " (%s)" % _t("decisores.visible.skills_throttled", "sin revisión: hubo otra hace poco")
        elif nota == "delivered":
            que += " (%s)" % _t("decisores.visible.skills_delivered", "la revisión se entregó igual")
        return que
    return c


def linea_entrada(e):
    """La línea de una decisión de la bitácora (lo que el agente no vio)."""
    try:
        c = e.get("choice")
        modo = e.get("mode")
        p = _pct(e.get("p"))
        point = str(e.get("point") or "")
        aplicado = modo == "apply"
        if point == "workspace.security":
            aplicado = aplicado and str(c or "").strip().lower() == "alto"
            modo = "apply" if aplicado else "suggest"
        que = (_que(point, c, aplicado) if point.startswith("workspace.")
               else _eleccion(c, _indice(e)))
        return formato(_nombre(e.get("decider")), que, p, modo)
    except Exception:
        return ""


# ── (d) Historial: qué cambió cada decisión ─────────────────────────────────
def efecto(e, corto=False):
    """Lo que hizo una decisión de la bitácora, en palabras cortas (cabe junto
    al «¿acertó?» del Historial): «aplicó: nota → hecho», «aplicó: aviso subió
    a alto», «el agente recibió opción B», «sugirió «hecho»», «observó · no
    cambió nada». `corto` = el cambio de una APLICADA, para la fila («nota →
    hecho», «aviso → alto», «al agente: opción B»); '' si no aplicó. '' si no
    aplica (un fallo, una pregunta a mano)."""
    try:
        if not isinstance(e, dict) or not e.get("ok"):
            return ""
        modo, point = e.get("mode"), str(e.get("point") or "")
        c = " ".join(str(e.get("choice") or "").split())
        si = c.lower() in ("sí", "si", "yes")
        if corto:
            if modo != "apply":
                return ""
            return {"workspace.memory": _t("decisores.visible.row_memory", "nota → {c}", c=c),
                    "workspace.security": _t("decisores.visible.row_security", "aviso → alto"),
                    "workspace.evals": _t("decisores.visible.row_evals", "sesión → {c}", c=c),
                    "workspace.skills": (_t("decisores.visible.row_skills_yes", "revisión entregada")
                                         if si else
                                         _t("decisores.visible.row_skills_no", "revisión omitida")),
                    }.get(point) or _t("decisores.visible.row_agent", "al agente: {c}",
                                       c=_eleccion(c, _indice(e), tope=9))
        if modo == "observe":
            return _t("decisores.visible.fx_observe", "observó · no cambió nada")
        if modo == "suggest":
            return _t("decisores.visible.fx_suggest", "sugirió «{c}»", c=_eleccion(c, _indice(e), tope=24))
        if modo != "apply":
            return ""
        if point == "workspace.memory":
            return _t("decisores.visible.fx_memory", "aplicó: nota → {c}", c=c)
        if point == "workspace.security":
            return _t("decisores.visible.fx_security", "aplicó: aviso subió a alto")
        if point == "workspace.evals":
            return _t("decisores.visible.fx_evals", "aplicó: sesión «{c}»", c=c)
        if point == "workspace.skills":
            return (_t("decisores.visible.fx_skills_yes", "aplicó: revisión entregada") if si else
                    _t("decisores.visible.fx_skills_no", "aplicó: revisión omitida"))
        return _t("decisores.visible.fx_agent", "el agente recibió {c}",
                  c=_eleccion(c, _indice(e), tope=24) if len(c) > 24 else "«%s»" % c)
    except Exception:
        return ""


def _indice(e):
    try:
        ops = [" ".join(str(o).split()) for o in (e.get("options") or [])]
        c = " ".join(str(e.get("choice") or "").split())
        return ops.index(c) if c in ops else None
    except Exception:
        return None


def ultimas_confianzas(point, n=5):
    """Las últimas `n` confianzas (%) de un uso, de la más vieja a la más
    nueva — la guía para el umbral (Ajustes → el uso). [] si no hay o apagado."""
    try:
        if not encendido():
            return []
        out = [_pct(e.get("p")) for e in _D()._entries()
               if e.get("ok") and e.get("point") == point and e.get("p") is not None]
        return [x for x in out if x is not None][-max(0, int(n)):]
    except Exception:
        return []


# ── (d)(e) hoy: cuántas consultas ───────────────────────────────────────────
def hoy(ahora=None):
    """{"n", "apply", "suggest", "mas"} de HOY (hora local), de la cola de la
    bitácora. `mas` = la cola no alcanzó (hubo más). Barato: sin caché, para
    un proceso nuevo en cada refresco de la barra."""
    res = {"n": 0, "apply": 0, "suggest": 0, "mas": False}
    try:
        dia = time.strftime("%Y-%m-%d", time.localtime(ahora) if ahora else time.localtime())
        path = _D().ledger_path()
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            tam = fh.tell()
            desde = max(0, tam - HOY_COLA_BYTES)
            fh.seek(desde)
            lineas = fh.read().decode("utf-8", "replace").split("\n")
        if desde > 0 and lineas:
            lineas = lineas[1:]
        primera = None
        for ln in lineas:
            if '"decision"' not in ln:
                continue
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(e, dict) or e.get("type") != "decision":
                continue
            ts = str(e.get("ts") or "")
            if primera is None:
                primera = ts
            if not ts.startswith(dia):
                continue
            res["n"] += 1
            if e.get("mode") == "apply":
                res["apply"] += 1
            elif e.get("mode") == "suggest":
                res["suggest"] += 1
        res["mas"] = bool(desde > 0 and primera and primera.startswith(dia))
    except Exception:
        pass
    return res


def _plural(n, uno, varios):
    return uno if n == 1 else varios


def linea_hoy(ahora=None):
    """Historial: «hoy: 7 consultas · 1 aplicada · 3 sugeridas». '' apagado."""
    try:
        if not encendido():
            return ""
        h = hoy(ahora)
        n = "%d%s" % (h["n"], "+" if h["mas"] else "")
        return _t("decisores.visible.today", "hoy: {n} {c} · {a} {ap} · {s} {sg}", n=n,
                  c=_plural(h["n"], _t("decisores.visible.query", "consulta"),
                            _t("decisores.visible.queries", "consultas")),
                  a=h["apply"], ap=_plural(h["apply"], _t("decisores.visible.applied_one", "aplicada"),
                                           _t("decisores.visible.applied_many", "aplicadas")),
                  s=h["suggest"], sg=_plural(h["suggest"],
                                             _t("decisores.visible.suggested_one", "sugerida"),
                                             _t("decisores.visible.suggested_many", "sugeridas")))
    except Exception:
        return ""


def segmento_hoy(ahora=None):
    """Barra de estado: «◆ Decisores: hoy 7 · 1 aplicada» — la cuenta junta a
    TODOS los modelos que respondieron hoy, así que va con la etiqueta neutra.
    '' con Decisores apagado."""
    try:
        if not encendido():
            return ""
        h = hoy(ahora)
        m = _t("decisores.visible.all_models", "Decisores")
        n = "%d%s" % (h["n"], "+" if h["mas"] else "")
        if h["apply"]:
            return _t("decisores.visible.bar_applied", "{s} {m}: hoy {n} · {a} {ap}", s=SIMBOLO, m=m,
                      n=n, a=h["apply"],
                      ap=_plural(h["apply"], _t("decisores.visible.applied_one", "aplicada"),
                                 _t("decisores.visible.applied_many", "aplicadas")))
        return _t("decisores.visible.bar", "{s} {m}: hoy {n}", s=SIMBOLO, m=m, n=n)
    except Exception:
        return ""


# ── archivos de estado (atómicos, falla-suave) ──────────────────────────────
def _dir(*partes):
    import paths
    return os.path.join(paths.state_dir(), "decisores", *partes)


def _leer_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _escribir(path, texto):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.%d.tmp" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
        os.replace(tmp, path)
        try:                                   # Windows: solo para tu usuario
            import acl_privada
            acl_privada.solo_mio(path)
        except Exception:
            pass
        return True
    except OSError:
        return False


def _borrar(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _clave(texto):
    return hashlib.sha1(str(texto or "").encode("utf-8", "replace")).hexdigest()[:16]


# ── (c) la última sesión: Evals y Skills al cerrar → una línea al abrir ─────
def _ultima_path(brain):
    return _dir("ultima-sesion", _clave(os.path.realpath(os.path.expanduser(brain))) + ".json")


def anotar_cierre(brain, point, v, sesion="", tab="", nota=""):
    """AL CERRAR (Evals, Skills): guarda el veredicto para mostrarlo UNA vez al
    abrir la siguiente sesión de ese cerebro (al agente y en el hub). Solo
    suggest/apply (observe es en silencio). Los usos de un mismo cierre se
    juntan por `sesion`. → True si quedó anotado."""
    try:
        if not brain or not isinstance(v, dict) or v.get("mode") not in ("suggest", "apply"):
            return False
        path = _ultima_path(brain)
        d = _leer_json(path) or {}
        ahora = time.time()
        mismo = (sesion and d.get("sesion") == sesion) or (
            not sesion and not d.get("sesion") and ahora - float(d.get("t") or 0) < 600)
        if not mismo:
            d = {"brain": os.path.realpath(os.path.expanduser(brain)), "sesion": sesion or "",
                 "tab": tab or "", "usos": {}}
        d["t"], d["visto"] = ahora, []
        d.setdefault("usos", {})[point] = {
            "choice": v.get("choice"), "mode": v.get("mode"), "decider": v.get("decider"),
            "p": round(float(v.get("p") or 0.0), 4) if v.get("p_known", True) else None,
            "nota": nota or ""}
        return _escribir(path, json.dumps(d, ensure_ascii=False))
    except Exception:
        return False


def _uso_ultima(point, u):
    modo = u.get("mode") if u.get("mode") in ("suggest", "apply") else "suggest"
    return formato(_nombre(u.get("decider")),
                   _que(point, u.get("choice"), modo == "apply", nota=u.get("nota") or ""),
                   _pct(u.get("p")), modo)


def linea_ultima(brain, canal):
    """AL ABRIR, una línea por uso (con el modelo que respondió en cada uno):
    «◆ <modelo>: tu última sesión quedó «resuelta»
    · 88 % · aplicado» — UNA vez por canal («agente»: el contexto de arranque,
    con el pedido de mostrarlo en su primera respuesta; «hub»: el aviso del
    hub). '' si no hay, ya se vio o Decisores está apagado."""
    try:
        if not brain or not encendido():
            return ""
        path = _ultima_path(brain)
        d = _leer_json(path)
        if not d:
            return ""
        visto = list(d.get("visto") or [])
        if canal in visto:
            return ""
        if time.time() - float(d.get("t") or 0) > ULTIMA_MAX_S:
            _borrar(path)
            return ""
        orden = ("workspace.evals", "workspace.skills")
        usos = d.get("usos") or {}
        partes = [_uso_ultima(p, usos[p]) for p in orden if isinstance(usos.get(p), dict)]
        if not partes:
            return ""
        visto.append(canal)
        if set(visto) >= {"agente", "hub"}:
            _borrar(path)
        else:
            d["visto"] = visto
            _escribir(path, json.dumps(d, ensure_ascii=False))
        if canal == "agente":
            partes.insert(0, _t("decisores.visible.last_session_agent", "Decisores en tu última "
                                "sesión (muéstraselo al socio en tu primera respuesta, en un "
                                "bloque ◆):"))
        return "\n".join(partes)
    except Exception:
        return ""


# ── (f) a media sesión: si Decisores cambió, el agente se entera UNA vez ────
def _sesion_path(sesion):
    return _dir("sesiones", _clave(sesion))


def _instruccion(motor):
    """La MISMA instrucción que recibe el agente al abrir (memoria.instruccion_decisores),
    sin importar memoria en cada mensaje."""
    try:
        import memoria_mcp
        via = bool(memoria_mcp.activo(motor))
    except Exception:
        via = False
    return _D().agent_instruction(via_mcp=via)


def _limpiar_sesiones():
    try:
        d = _dir("sesiones")
        corte = time.time() - SESION_MAX_S
        for f in os.listdir(d):
            p = os.path.join(d, f)
            try:
                if os.path.getmtime(p) < corte:
                    os.remove(p)
            except OSError:
                continue
    except OSError:
        pass


def al_abrir_sesion(sesion, motor="claude-code"):
    """AL ABRIR (cada arranque, también al retomar o tras compactar: el agente
    recibe ahí la instrucción): la línea de base = la huella de lo que se le
    dio. Apagado y sin base previa: no escribe nada."""
    try:
        if not sesion:
            return
        path = _sesion_path(sesion)
        txt = _instruccion(motor) if encendido() else ""
        if txt:
            _limpiar_sesiones()
            _escribir(path, _clave(txt))
        elif os.path.exists(path):
            _borrar(path)
        if encendido():                          # desde aquí cuenta «lo que no viste»
            _escribir(_cursor_path(sesion), "%.3f" % time.time())
    except Exception:
        pass


def cambio_en_sesion(sesion, motor="claude-code"):
    """EN CADA MENSAJE: si los usos de agentes cambiaron desde el arranque (la
    huella de la instrucción ya no es la de la base), el texto para inyectar
    UNA vez — la instrucción nueva, o que ya no consulte si se apagaron — y
    queda como nueva base. '' si nada cambió (apagado de punta a punta: ni un
    archivo)."""
    try:
        if not sesion:
            return ""
        path = _sesion_path(sesion)
        try:
            with open(path, encoding="utf-8") as fh:
                base = fh.read().strip()
        except OSError:
            base = ""
        if not base and not encendido():
            return ""
        txt = _instruccion(motor) if encendido() else ""
        actual = _clave(txt) if txt else ""
        if actual == base:
            return ""
        if txt:
            _escribir(path, actual)
            return _t("decisores.visible.changed", "Decisores cambió en esta sesión (lo movió el "
                      "socio); esto reemplaza lo que decía al abrir:") + "\n" + txt
        _borrar(path)
        return _t("decisores.visible.turned_off", "Decisores: el socio lo apagó en esta sesión; ya "
                  "no le preguntes al decisor ni cierres con el bloque ◆.")
    except Exception:
        return ""


# ── lo que el agente no vio: en el siguiente mensaje, UNA vez ───────────────
#: Lo más que se lista; el resto, «y N más».
NO_VISTAS_MAX = 3


def _cursor_path(sesion):
    return _dir("cursor", _clave(sesion))


def _entradas_desde(t0):
    """Las decisiones de la cola de la bitácora con `t` > t0 (las nuevas traen
    su hora precisa), de la más vieja a la más nueva."""
    out = []
    try:
        path = _D().ledger_path()
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            tam = fh.tell()
            desde = max(0, tam - HOY_COLA_BYTES)
            fh.seek(desde)
            lineas = fh.read().decode("utf-8", "replace").split("\n")
        if desde > 0 and lineas:
            lineas = lineas[1:]
        for ln in reversed(lineas):
            if '"decision"' not in ln:
                continue
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(e, dict) or e.get("type") != "decision":
                continue
            try:
                t = float(e.get("t"))
            except (TypeError, ValueError):
                break                             # una de antes: ya no hay nuevas
            if t <= t0:
                break
            out.append(e)
    except Exception:
        return []
    return list(reversed(out))


def lugar_actual():
    """(pestaña, cerebro) de este proceso, como se anotan en la bitácora."""
    tab = os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS") or ""
    brain = os.environ.get("WORKSPACE_BRAIN") or ""
    return tab, (_clave(os.path.realpath(os.path.expanduser(brain))) if brain else "")


def desde_tu_ultimo_mensaje(sesion):
    """EN CADA MENSAJE (Claude Code): las intervenciones de esta pestaña que el
    agente NO vio por su canal (una que solo anotó un hook) desde el mensaje
    anterior: «Desde tu último mensaje, Decisores hizo: …», hasta 3 líneas y
    «y N más». UNA vez (el cursor avanza). '' si no hubo, o apagado (ni un
    archivo)."""
    try:
        if not sesion or not encendido():
            return ""
        path = _cursor_path(sesion)
        try:
            with open(path, encoding="utf-8") as fh:
                t0 = float(fh.read().strip())
        except (OSError, ValueError):
            t0 = None
        _escribir(path, "%.3f" % time.time())
        if t0 is None:
            return ""                             # recién encendido: cuenta desde ahora
        tab, cerebro = lugar_actual()
        nuevas = [e for e in _entradas_desde(t0)
                  if e.get("ok") and e.get("mode") in ("suggest", "apply") and not e.get("agente")
                  and (e.get("tab") or "") == tab and (e.get("cerebro") or "") == cerebro]
        lineas = [x for x in (linea_entrada(e) for e in nuevas) if x]
        if not lineas:
            return ""
        out = [_t("decisores.visible.since_last", "Desde tu último mensaje, Decisores hizo (ponlo "
                  "en tu bloque ◆):")] + lineas[:NO_VISTAS_MAX]
        if len(lineas) > NO_VISTAS_MAX:
            out.append(_t("decisores.visible.and_more", "y {n} más (en Decisores → Historial)",
                          n=len(lineas) - NO_VISTAS_MAX))
        return "\n".join(out)
    except Exception:
        return ""
