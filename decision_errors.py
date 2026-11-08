#!/usr/bin/env python3
"""WORKSPACE · decision_errors — los fallos de Decisores, en palabras de persona.

Los decisores y la fachada (decisions.py) devuelven en `error` un CÓDIGO:

  context_too_large · auth · payment · rate_limit · timeout · connection ·
  proxy · server · not_found · bad_request · bad_response · out_of_options ·
  no_key · not_installed · need_options · off · use_off · error

y, aparte, `error_detail` (status HTTP, error_type del servidor, request_id;
o la clase del error de red y su fase). Aquí se vuelven:

  human(...)        el mensaje principal (Preguntar, Motores → Probar, la CLI
                    y la herramienta MCP `decidir`): qué pasó y QUÉ HACER
                    (cada código trae su siguiente paso) — jamás una URL,
                    un request_id ni el nombre de una clase;
  short(...)        la razón corta del Historial;
  detail_lines(...) lo que muestra «d detalle» (clase, status, tipo,
                    request_id) — también queda en la bitácora.

Las entradas viejas de la bitácora traían el texto crudo de la excepción en
`error`: normalize() lo reconoce y lo lleva a un código. ES/EN vía i18n
(claves `decisores.err.*` y `decisores.why.*`). Stdlib. Jamás levanta."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import i18n                                                 # noqa: E402
except Exception:
    i18n = None

CODES = ("context_too_large", "auth", "payment", "rate_limit", "timeout", "connection",
         "proxy", "insecure_url", "server", "not_found", "bad_request", "bad_response",
         "out_of_options", "no_key", "not_installed", "need_options", "bad_input", "off", "use_off",
         "model_missing", "unavailable", "error")

#: Texto crudo de la bitácora vieja (antes de los códigos) → código. En orden:
#: lo más específico primero.
_LEGACY = (
    (("max_tokens", "too large", "too long", "context length", "413"), "context_too_large"),
    (("authentication", "permissiondenied", "permission denied", "401", "403",
      "invalid api key", "unauthorized"), "auth"),
    (("402", "insufficient", "credit", "billing", "payment"), "payment"),
    (("ratelimit", "rate limit", "429", "too many requests"), "rate_limit"),
    (("timeout", "timed out", "tardó"), "timeout"),
    (("connection", "connecterror", "network"), "connection"),
    (("internalserver", "internal server", "500", "502", "503", "504"), "server"),
    (("notfound", "not found", "404"), "not_found"),
    (("_api_key", "llave", "api key"), "no_key"),
    (("badrequest", "bad request", "unprocessable", "400", "422"), "bad_request"),
    (("responsevalidation", "invalid response"), "bad_response"),
    (("al menos 2 opciones", "at least 2 options"), "need_options"),
)


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


def normalize(err):
    """Un código de CODES (los textos crudos viejos se reconocen por palabras;
    lo que no se reconoce = "error")."""
    s = str(err or "").strip()
    if s in CODES:
        return s
    if s in ("no_answer", "bad_point", "need_question"):
        return "error"
    low = s.lower()
    for words, code in _LEGACY:
        if any(w in low for w in words):
            return code
    return "error"


def _names(decider):
    """(nombre del modelo, proveedor, sitio del proveedor) para los mensajes."""
    did = str(decider or "").strip().lower()
    label, prov, site = "", "", ""
    try:
        import decisions as D
        m = D.meta(did) if did else {}
        label = m.get("label") or ""
        prov = m.get("provider") or ""
        site = m.get("site") or ""
    except Exception:
        pass
    label = label or (did.capitalize() if did and did != "off" else
                      _t("decisores.err.the_model", "el modelo"))
    return label, prov or label, site


def _limit_txt(decider):
    """«32k» — hacia ABAJO (lo que de verdad cabe). None si el modelo no declara
    su límite: no se inventa un número (Workspace usa uno prudente por dentro)."""
    try:
        import decision_context as C
        if not C.declared_limit(decider):
            return None
        return C.fmt_limit(C.limit(decider))
    except Exception:
        return None


def _secs(ms):
    s = max(0.0, float(ms or 0) / 1000.0)
    return ("%d" % s) if abs(s - round(s)) < 0.05 else ("%.1f" % s)


def human(err, decider=None, sent_tokens=None, timeout_ms=None, where="ask", detail=None,
          elapsed_ms=None):
    """El mensaje principal de un fallo. `where`: "ask" (Preguntar, el socio
    puede bajar el nivel de contexto) · "agent" (CLI/MCP: el agente manda
    menos) · "probe" (Motores → Probar). `elapsed_ms`: lo que de verdad se
    esperó (un decisor que se rinde solo al instante no «tardó más de 10 s»)."""
    code = normalize(err)
    m, p, site = _names(decider)
    status = (detail or {}).get("status") if isinstance(detail, dict) else None
    if isinstance(detail, dict) and detail.get("breaker"):
        # la pausa tras un fallo de red: ni se intentó (no «sin conexión» ni «tardó»)
        try:
            seg = max(1, int(detail.get("retry_s") or 0))
        except (TypeError, ValueError):
            seg = 60
        return _t("decisores.err.breaker", "{m} está en pausa ~{s} s tras un fallo de red · "
                  "reintenta en un momento", m=m, s=seg)
    if code == "context_too_large":
        lim = _limit_txt(decider)
        if lim is None:
            return _context_sin_limite(m, where, sent_tokens)
        if where == "agent":
            return _t("decisores.err.too_large_agent",
                      "{m} admite ≈{lim} tokens y esta pregunta no cupo · manda menos contexto",
                      m=m, lim=lim)
        # los niveles chicos, con el MISMO nombre que sus cuadritos en Preguntar
        a = _t("decisores.ctx.memoria", "Memoria")
        b = _t("decisores.ctx.pestana", "Pestaña")
        if sent_tokens:
            import decision_context as C
            return _t("decisores.err.too_large",
                      "{m} admite ≈{lim} tokens; esta pregunta llevaba ≈{n} · elige {a} o {b}",
                      m=m, lim=lim, n=C.fmt_tokens(sent_tokens), a=a, b=b)
        return _t("decisores.err.too_large_nonum",
                  "{m} admite ≈{lim} tokens y esta pregunta no cupo · elige {a} o {b}",
                  m=m, lim=lim, a=a, b=b)
    if code == "auth":
        return _t("decisores.err.auth", "La llave de {m} no es válida o se revocó · Motores → "
                  "Modelos de decisión → {m} → conectar llave", m=m)
    if code == "payment":
        if site:
            return _t("decisores.err.payment", "Tu cuenta de {p} se quedó sin crédito · recarga "
                      "crédito en {site}", p=p, site=site)
        return _t("decisores.err.payment_nosite", "Tu cuenta de {p} se quedó sin crédito · "
                  "recárgala en su sitio", p=p)
    if code == "rate_limit":
        return _t("decisores.err.rate_limit", "Demasiadas preguntas seguidas · espera unos segundos")
    if code == "timeout":
        if where == "probe":
            paso = _t("decisores.err.next_retry", "intenta de nuevo")
        elif where == "agent":
            paso = _t("decisores.err.next_retry_agent", "intenta de nuevo o manda menos contexto")
        else:
            paso = _t("decisores.err.next_retry_ask", "intenta de nuevo o usa menos contexto")
        try:
            antes = (timeout_ms and elapsed_ms is not None
                     and float(elapsed_ms) < 0.8 * float(timeout_ms))
        except (TypeError, ValueError):
            antes = False
        if antes:            # se rindió solo, antes del tiempo límite de Workspace
            return _t("decisores.err.timeout_early", "{m} no respondió a tiempo · {paso}", m=m,
                      paso=paso)
        if timeout_ms:
            return _t("decisores.err.timeout", "{m} tardó más de {s} s · {paso}", m=m,
                      s=_secs(timeout_ms), paso=paso)
        return _t("decisores.err.timeout_nonum", "{m} tardó demasiado · {paso}", m=m, paso=paso)
    if code == "connection":
        return _t("decisores.err.connection", "Sin conexión con {p} · revisa tu internet", p=p)
    if code == "proxy":
        var = (detail or {}).get("var") if isinstance(detail, dict) else None
        return _t("decisores.err.proxy", "El proxy configurado ({var}) no es válido · corrígelo o "
                  "quítalo", var=var or "HTTPS_PROXY")
    if code == "insecure_url":
        var = (detail or {}).get("var") if isinstance(detail, dict) else None
        return _t("decisores.err.insecure_url", "{var} no es una dirección segura · la llave no "
                  "sale así; corrígela o quítala", var=var or "TYPESAFE_BASE_URL")
    if code == "server":
        return _t("decisores.err.server", "{p} tuvo un error de su lado · intenta de nuevo", p=p)
    if code == "not_found" or status == 404:
        return _t("decisores.err.not_found", "{p} no reconoce la petición · actualiza Workspace "
                  "(workspace update)", p=p)
    if code == "bad_request":
        return _t("decisores.err.bad_request", "{p} rechazó la pregunta · revísala e intenta de "
                  "nuevo", p=p)
    if code == "bad_response":
        return _t("decisores.err.bad_response", "{p} mandó una respuesta que no se entiende · "
                  "intenta de nuevo", p=p)
    if code == "out_of_options":
        return _t("decisores.err.out_of_options", "{m} respondió algo que no está entre tus "
                  "opciones · intenta de nuevo", m=m)
    if code == "no_key":
        return _t("decisores.err.no_key", "{m} no está conectado · Motores → Modelos de "
                  "decisión → {m} → conectar llave", m=m)
    if code == "not_installed":
        return _t("decisores.err.not_installed", "No encuentro el modelo {m} · elige otro en "
                  "Motores → Modelos de decisión", m=m)
    if code == "need_options":
        return _t("decisores.err.options", "Pon al menos 2 opciones, separadas por coma")
    if code == "bad_input":
        if isinstance(detail, dict) and detail.get("reason") == "secret_option":
            return _t("decisores.err.secret_option", "Una opción parece una llave · quítala")
        return _t("decisores.err.bad_input", "La entrada no sirve · revísala e intenta de nuevo")
    if code == "off":
        return _t("decisores.err.off", "No hay modelo activo · configúralo en Motores → "
                  "Modelos de decisión")
    if code == "use_off":
        return _t("decisores.err.use_off", "Este uso está apagado en Decisores · actívalo en "
                  "Decisores → Ajustes")
    if code == "model_missing":
        return _t("decisores.err.model_missing", "El modelo configurado ({m}) no está · elige "
                  "otro en Motores → Modelos de decisión", m=m)
    if code == "unavailable":
        return _t("decisores.err.unavailable", "Decisores no está disponible en este Workspace · "
                  "actualízalo (workspace update)")
    return _t("decisores.err.error", "Algo falló al preguntarle a {m} · intenta de nuevo", m=m)


def _context_sin_limite(m, where, sent_tokens):
    """«No cupo» de un modelo que no declara su límite: sin inventar uno."""
    if where == "agent":
        return _t("decisores.err.too_large_agent_nolimit", "{m} no declara su límite y esta "
                  "pregunta no cupo · manda menos contexto", m=m)
    a = _t("decisores.ctx.memoria", "Memoria")
    b = _t("decisores.ctx.pestana", "Pestaña")
    if sent_tokens:
        import decision_context as C
        return _t("decisores.err.too_large_nolimit", "{m} no declara su límite; esta pregunta "
                  "llevaba ≈{n} · elige {a} o {b}", m=m, n=C.fmt_tokens(sent_tokens), a=a, b=b)
    return _t("decisores.err.too_large_nolimit_nonum", "{m} no declara su límite y esta pregunta "
              "no cupo · elige {a} o {b}", m=m, a=a, b=b)


def short(err):
    """La razón corta del Historial (≤ 22 caracteres)."""
    code = normalize(err)
    return {"context_too_large": _t("decisores.why.too_large", "no cupo el contexto"),
            "auth": _t("decisores.why.auth", "llave no válida"),
            "payment": _t("decisores.why.payment", "sin crédito"),
            "rate_limit": _t("decisores.why.rate_limit", "demasiadas seguidas"),
            "timeout": _t("decisores.why.timeout", "tardó de más"),
            "connection": _t("decisores.why.connection", "sin conexión"),
            "proxy": _t("decisores.why.proxy", "proxy no válido"),
            "insecure_url": _t("decisores.why.insecure_url", "dirección insegura"),
            "server": _t("decisores.why.server", "falla del servicio"),
            "not_found": _t("decisores.why.not_found", "petición desconocida"),
            "bad_request": _t("decisores.why.bad_request", "pregunta rechazada"),
            "bad_response": _t("decisores.why.bad_response", "respuesta ilegible"),
            "out_of_options": _t("decisores.why.out_of_options", "fuera de las opciones"),
            "no_key": _t("decisores.why.no_key", "sin llave"),
            "not_installed": _t("decisores.why.not_installed", "modelo no encontrado"),
            "need_options": _t("decisores.why.need_options", "faltan opciones"),
            "bad_input": _t("decisores.why.bad_input", "entrada no válida"),
            "off": _t("decisores.why.off", "sin modelo activo"),
            "use_off": _t("decisores.why.use_off", "uso apagado"),
            "model_missing": _t("decisores.why.model_missing", "el modelo no está"),
            "unavailable": _t("decisores.why.unavailable", "no disponible"),
            }.get(code, _t("decisores.why.error", "falla inesperada"))


def detail_lines(detail, err=None):
    """Lo de «d detalle»: [(etiqueta, valor)] — clase, status, tipo y
    request_id (lo técnico, para soporte). Vacío si no hay nada."""
    out = []
    d = detail if isinstance(detail, dict) else {}
    code = normalize(err) if err else ""
    if code:
        out.append((_t("decisores.det.code", "código"), code))
    fases = {"connect": _t("decisores.det.phase_connect", "al conectar"),
             "read": _t("decisores.det.phase_read", "esperando la respuesta"),
             "config": _t("decisores.det.phase_config", "al leer la configuración")}
    for k, lab in (("class", _t("decisores.det.class", "clase")),
                   ("phase", _t("decisores.det.phase", "fase")),
                   ("var", _t("decisores.det.var", "variable")),
                   ("status", _t("decisores.det.status", "status HTTP")),
                   ("type", _t("decisores.det.type", "tipo")),
                   ("request_id", "request_id"),
                   ("got", _t("decisores.det.got", "respondió"))):
        v = d.get(k)
        if v not in (None, ""):
            out.append((lab, fases.get(v, str(v)[:80]) if k == "phase" else str(v)[:80]))
    raw = str(err or "").strip()
    if raw and raw not in CODES and raw != code:            # texto crudo de la bitácora vieja
        out.append((_t("decisores.det.raw", "texto original"), raw[:160]))
    return out
