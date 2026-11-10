#!/usr/bin/env python3
"""WORKSPACE · modelos_tui — Motores → MODELOS DE DECISIÓN: dónde se CONSIGUEN los decisores.

Los motores trabajan · los decisores eligen. MISMO diseño y manejo que la
pantalla de motores de agentes (engines_tui): a la izquierda la lista de
modelos con su estado; a la derecha las opciones del elegido, que se aplican
AHÍ MISMO (sin pantallas de detalle):

  conectar llave    campo ENMASCARADO en la columna → bóveda de Workspace
                    (en la nube es lo ÚNICO que hay que configurar: cada uno
                    habla con su API con la stdlib, no hay nada que instalar)
  desconectar       con confirmación
  Ollama            un decisor LOCAL (en esta computadora, sin llave): su
                    estado real (no instalado · apagado · versión vieja · sin
                    modelo · listo) y el siguiente paso en una línea
                    («ollama pull nimble»); Enter vuelve a mirar
  modelo            el de cada decisor que trae varios, SOLO de decisión
                    (OpenRouter, Liquid, los de decisión descargados en Ollama:
                    los de chat ni se ofrecen, se cuentan). Enter (o un clic)
                    ABRE LA LISTA (section_box.pick_list, la de siempre), con el
                    actual marcado y una pista por fila (marca, precio o «en
                    esta computadora»); ↑↓ mueve, Enter elige y guarda
                    (`decisions.set_decider_model`), Esc cierra sin cambiar; con
                    10 o más, escribir filtra (como la búsqueda de la portada)
  probar            una llamada real chiquita: latencia, tokens y costo (uno
                    local, además, se precarga en segundo plano)
  contexto          el límite MEDIDO del modelo (META `context_tokens`);
                    Enter elige uno menor (`decisions.model_limits`: más
                    barato y rápido; nunca más de lo que el modelo admite)
  precio            aproximado (del META)

La lista sale de deciders/ y su META (los internos no se muestran). El
primer modelo que queda listo, si no hay uno activo, se activa solo en
Decisores (los usos siguen apagados).
DÓNDE actúa cada uno se elige en la sección Decisores. Stdlib.
"""
import os
import sys
import threading
import time
from theme import screen as _theme_screen  # fondo/tinta del tema

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import decisions as DC                                          # noqa: E402
import decisores_tui as DT                                      # noqa: E402
import engines_tui as ET                                        # noqa: E402
import hublayout as HL                                          # noqa: E402
import section_box as SB                                        # noqa: E402

_t = DT._t
#: Las columnas de engines_tui: las dos mitades de Motores se ven iguales.
LIST_W = ET.LIST_W
DETAIL_W = ET.DETAIL_W
#: Límites de contexto que se ofrecen con Enter en «contexto» (tokens).
#: Límites menores que se pueden elegir (más el del modelo, que es el tope).
LIMITS = (8000, 16000, 24000)
#: Prueba: una pregunta mínima (pocos tokens) con respuesta obvia.
PROBE_Q = "¿Cuál de estas palabras es un color?"
PROBE_OPTS = ["rojo", "martes"]
PROBE_TIMEOUT_MS = 10000
#: Filas que son ACCIÓN (›), como engines_tui._ACCIONES.
_ACCIONES = ("connect", "disconnect")


# ── datos (desde deciders/ y su META) ────────────────────────────────────────
def models():
    """Los decisores que ve el socio (los de la nube primero). Los internos
    (META `internal`) nunca aparecen."""
    return sorted(DC.offered(), key=lambda d: (bool(DC.meta(d).get("local", True)), d))


def selectable(did):
    return did in DC.deciders() and not DC.is_internal(did)


def name(did):
    return DC.meta(did).get("label") or str(did).capitalize()


def ready(did):
    return selectable(did) and bool(DC.decider_status(did).get("ready"))


def _detail_txt(detail):
    """El estado (no listo) en pocas palabras, según status()."""
    return {"no_key": _t("decisores.st.no_key", "sin llave"),
            "ollama_missing": _t("modelos.st.missing", "no instalado"),
            "ollama_off": _t("modelos.st.off", "apagado"),
            "ollama_old": _t("modelos.st.old", "versión vieja"),
            "no_model": _t("modelos.st.no_model", "sin modelo"),
            "checking": _t("modelos.st.checking", "comprobando…")}.get(
        detail, _t("modelos.st.not_ready", "no listo"))


def state(did):
    """(texto, color) del estado en la lista — como engines_tui.status_of. El
    estado REAL: el status() del decisor (sin llave, o el de Ollama)."""
    if not selectable(did):
        return _t("modelos.st.missing", "no instalado"), "DIM"
    st = DC.decider_status(did)
    if st.get("ready"):
        return _t("decisores.st.ready", "listo"), "OK"
    return _detail_txt(st.get("detail")), "ERR"


def is_local(did):
    """¿Corre en ESTA computadora? (META `local`: sin llave ni aviso de nube)."""
    return bool(DC.meta(did).get("local", False))


def next_step(did):
    """El siguiente paso de un decisor LOCAL que no está listo, en una línea
    («Descarga un modelo de decisión: ollama pull nimble»), o ''."""
    if not selectable(did):
        return ""
    st = DC.decider_status(did)
    if st.get("ready"):
        return ""
    d = st.get("detail")
    cmd = _pull_cmd(did)
    if d == "ollama_missing":
        return _t("modelos.next.missing", "Instala Ollama desde ollama.com y vuelve aquí")
    if d == "ollama_off":
        return _t("modelos.next.off", "Abre Ollama (o en una terminal: ollama serve) y vuelve "
                  "aquí")
    if d == "ollama_old":
        return _t("modelos.next.old", "Actualiza Ollama a 0.35.0 o más nueva (tienes {v})",
                  v=st.get("version") or "?")
    if d == "no_model":
        return _t("modelos.next.no_model", "Descarga un modelo de decisión: {cmd}", cmd=cmd)
    return ""


def _pull_cmd(did, model=None):
    try:
        fn = getattr(DC.load(did), "pull_cmd", None)
        return str(fn(model) or "") if callable(fn) else ""
    except Exception:
        return ""


def model_list(did):
    """[{"id", "decision"}] de un decisor con varios modelos ([] si trae uno)."""
    try:
        return DC.decider_models(did)
    except Exception:
        return []


def current_model(did):
    try:
        return DC.decider_model(did)
    except Exception:
        return ""


def _model_value(did):
    """«nimble:latest» (la lista solo trae modelos de decisión)."""
    return current_model(did) or _t("modelos.model.none", "ninguno descargado")


def local_notes(did):
    """Las líneas de un decisor local que ya está listo: el modelo guardado que
    no sirvió y cuál se usa en su lugar, y cuántos de chat hay (no se ofrecen:
    no sirven para decidir). [] si no hay nada que decir."""
    if not is_local(did):
        return []
    st = DC.decider_status(did)
    out = []
    fb = st.get("fallback") if isinstance(st.get("fallback"), dict) else None
    if st.get("ready") and fb and st.get("model"):
        key, es = (("modelos.note.fallback_chat", "Uso {m}: {x} no es un modelo de decisión")
                   if fb.get("why") == "not_decision" else
                   ("modelos.note.fallback_missing", "Uso {m}: {x} ya no está descargado"))
        out.append(_t(key, es, m=st["model"], x=fb.get("from") or "?"))
    try:
        n = int(st.get("chat_models") or 0)
    except (TypeError, ValueError):
        n = 0
    if n == 1:
        out.append(_t("modelos.note.chat_one", "1 modelo de chat descargado no sirve para decidir"))
    elif n > 1:
        out.append(_t("modelos.note.chat_many", "{n} modelos de chat descargados no sirven para "
                      "decidir", n=n))
    return out


def ctx_limit(did):
    import decision_context as C
    return C.limit(did)


def set_limit(did, n):
    import settings
    cur = dict(settings.get("decisions.model_limits") or {})
    base = int(DC.meta(did).get("context_tokens") or 0)
    if int(n) == base:
        cur.pop(did, None)
    else:
        cur[did] = int(n)
    settings.set("decisions.model_limits", cur)
    return int(n)


def _base_limit(did):
    try:
        return int(DC.meta(did).get("context_tokens") or 0)
    except (TypeError, ValueError):
        return 0


def _limits(did):
    """Los límites que Enter recorre: los menores de LIMITS y el del modelo."""
    base = _base_limit(did)
    if not base:
        return LIMITS
    return tuple(sorted({x for x in LIMITS if x < base} | {base}))


def _next_limit(did):
    lim = ctx_limit(did)
    opciones = _limits(did)
    mayores = [x for x in opciones if x > lim]
    return mayores[0] if mayores else opciones[0]


def _ctx_value(did):
    """«32 768 tokens» (el del modelo) o «16 000 de 32 768 tokens» (uno menor)."""
    import decision_context as C
    lim, base = ctx_limit(did), _base_limit(did)
    if not C.declared_limit(did):      # no se inventa: el 8k de adentro no es suyo
        return _t("modelos.info.ctx_none", "sin límite declarado")
    if base and lim < base:
        return _t("modelos.info.ctx_of", "{n} de {b} tokens", n=C.fmt_exact(lim), b=C.fmt_exact(base))
    return _t("modelos.info.ctx_n", "{n} tokens", n=C.fmt_exact(lim))


def _approx(did):
    return (" · " + _t("modelos.info.approx", "aprox.")) if DC.meta(did).get("approx_price") else ""


def _price_rows(did):
    """Las filas de precio (aproximado, del META): entrada y salida."""
    m = DC.meta(did)
    if m.get("local", True):
        return [("price", _t("modelos.info.price", "precio"), _t("modelos.info.free", "sin costo"))]
    if m.get("price_in_per_m") is None and m.get("price_from_response"):
        return [("price", _t("modelos.info.price", "precio"),
                 _t("modelos.info.price_resp", "lo dice cada respuesta"))]
    if m.get("price_in_per_m") is None:
        return [("price", _t("modelos.info.price", "precio"), _t("modelos.info.noprice", "precio n/d"))]
    out = [("price", _t("modelos.info.in", "entrada"),
            _t("modelos.info.per_m", "${p} por millón", p=m["price_in_per_m"]) + _approx(did))]
    if m.get("price_out_per_m") is not None:
        out.append(("price", _t("modelos.info.out", "salida"),
                    _t("modelos.info.out_free", "gratis") if m["price_out_per_m"] == 0 else
                    _t("modelos.info.per_m", "${p} por millón", p=m["price_out_per_m"])))
    return out


def options(S, did):
    """[(clave, etiqueta, valor)] del modelo — como engines_tui.options:
    valor = estado; "" = acción (›)."""
    out = []
    if is_local(did) and not DC.meta(did).get("key_env"):
        st = DC.decider_status(did)
        if st.get("ready"):
            val = _t("modelos.local.here", "en esta computadora")
            if st.get("version"):
                val += " · " + str(st["version"])
        else:
            val = _detail_txt(st.get("detail"))
        out.append(("local", DC.meta(did).get("provider") or name(did), val))
    if DC.meta(did).get("key_env"):
        src = DC.key_source(did)
        if src == "store":
            out.append(("key", _t("modelos.k.key", "llave"), _t("modelos.key.store", "conectada")))
            out.append(("disconnect", _t("modelos.o.disconnect", "desconectar llave"), ""))
        elif src == "env":
            out.append(("key", _t("modelos.k.key", "llave"), _t("modelos.key.env", "del entorno")))
        else:
            out.append(("connect", _t("modelos.o.connect", "conectar llave"), ""))
    if model_list(did):
        out.append(("model", _t("modelos.k.model", "modelo"), _model_value(did)))
    out.append(("probe", _t("modelos.o.probe", "probar"), "" if ready(did) else _probe_needs(did)))
    out.append(("ctx", _t("modelos.info.ctx", "contexto"), _ctx_value(did)))
    return out + _price_rows(did)


def _probe_needs(did):
    """Lo que le falta para poder probarlo (la fila «probar» de uno no listo)."""
    if DC.meta(did).get("key_env") and not DC.key_source(did):
        return _t("modelos.probe.needs", "necesita la llave")
    return _t("modelos.probe.when_ready", "cuando esté listo")


# ── tu llave, en simple (Información y la pantalla de conectar) ──────────────
def _site(did):
    m = DC.meta(did)
    return m.get("site") or m.get("provider") or name(did)


def key_tip(did):
    """La recomendación al conectar: una llave solo para Workspace y, si el
    proveedor lo permite por llave (META `key_spend_limit`), con tope de gasto."""
    m = DC.meta(did)
    if m.get("key_spend_limit"):
        return _t("modelos.llave.tip_cap", "Mejor una llave solo para Workspace, con tope de gasto "
                  "({p} lo permite)", p=m.get("provider") or name(did))
    return _t("modelos.llave.tip", "Mejor una llave solo para Workspace")


def keys_line(did):
    """«Tus llaves en OpenRouter: https://openrouter.ai/keys» (META `keys_url`;
    solo texto, no se abre nada), o ''."""
    m = DC.meta(did)
    if not m.get("keys_url"):
        return ""
    return _t("modelos.llave.keys_url", "Tus llaves en {p}: {url}", p=m.get("provider") or name(did),
              url=m["keys_url"])


def revoke_line(did):
    """Cómo dejarla muerta de verdad tras desconectarla: revocarla en el proveedor."""
    m = DC.meta(did)
    return _t("modelos.llave.revoke", "revócala también en {p} ({url})",
              p=m.get("provider") or name(did), url=m.get("keys_url") or _site(did))


#: (dónde, modo, momento) de la bóveda, recién leído: la pantalla se pinta en
#: cada tecla y mirar el llavero lee archivos (sin llamar a nadie).
_DONDE = {"t": 0.0, "v": None}


def _boveda_ahora():
    """(sistema, modo) de la bóveda AHORA: dónde se guardaría una llave nueva
    (secret_store.sistema: llavero | dpapi | secret-tool | archivo) y el modo
    elegido (auto | keyring | file). Falla-suave → ("archivo", "auto")."""
    if _DONDE["v"] is not None and time.time() - _DONDE["t"] < 3:
        return _DONDE["v"]
    try:
        import secret_store
        v = (secret_store.sistema(), secret_store.modo_guardado())
    except Exception:
        v = ("archivo", "auto")
    _DONDE.update(t=time.time(), v=v)
    return v


def donde_vive(did):
    """De dónde sale la llave de `did` HOY: ("entorno", var) si viene de una
    variable de tu sistema; (llavero | dpapi | secret-tool | archivo, var) si
    está en la bóveda (su fuente real, secret_store.fuente); y, sin llave,
    adónde iría una nueva (secret_store.sistema)."""
    src, var = "", ""
    try:
        src, var = DC._key_origin(did)
    except Exception:
        pass
    if src == "env":
        return "entorno", var
    if src == "store":
        try:
            import secret_store
            f = secret_store.fuente(var, env={})
            if f:
                return f, var
        except Exception:
            pass
    return _boveda_ahora()[0], var


def _permiso_archivo():
    return (_t("modelos.llave.perm_win", "solo tu usuario") if os.name == "nt" else "0600")


def where_text(donde):
    """«Dónde vive», por sistema y según la fuente real (ver donde_vive)."""
    cola = _t("modelos.llave.where_tail", "fuera de tu cerebro: no se sincroniza ni se sube a "
              "ningún lado. Nosotros nunca la vemos.")
    if donde == "llavero":
        return _t("modelos.llave.where_llavero", "En el llavero de tu Mac (cifrado), ") + cola
    if donde == "dpapi":
        return _t("modelos.llave.where_dpapi", "En esta computadora, cifrada con tu cuenta de "
                  "Windows, ") + cola
    if donde == "secret-tool":
        return _t("modelos.llave.where_secret_tool", "En el llavero de tu sistema, ") + cola
    if _boveda_ahora()[1] == "file":
        return _t("modelos.llave.where_file_chosen", "En un archivo solo tuyo ({perm}), porque así "
                  "quedó configurado en esta computadora, ", perm=_permiso_archivo()) + cola
    return _t("modelos.llave.where_file", "En esta computadora, en un archivo solo tuyo ({perm}) "
              "— tu sistema no tiene llavero disponible —, ", perm=_permiso_archivo()) + cola


def _lista(nombres):
    if len(nombres) <= 1:
        return "".join(nombres)
    return ", ".join(nombres[:-1]) + _t("modelos.llave.and", " y ") + nombres[-1]


def agents_text(donde):
    """«Tus agentes», honesto (revisión 2026-11-08): ningún motor la RECIBE
    (engine_env); en los motores con la regla (rutas_protegidas.no_la_leen)
    sus herramientas de archivos no pueden abrir la bóveda y, con la llave en
    el llavero, su terminal no puede usar `security` / `secret-tool`; de los
    demás dice que no hay esa regla; y nunca promete más: un programa que
    corra con tu usuario aún podría pedirla. Jamás «no pueden leerla»."""
    import rutas_protegidas as R
    si = R.no_la_leen(donde)
    con = [n for m, n in R.MOTORES if m in si]
    sin = [n for m, n in R.MOTORES if m not in si]
    if donde in ("llavero", "secret-tool"):
        regla = _t("modelos.llave.agents_rule_kc2", "sus herramientas de archivos no pueden abrir "
                   "la bóveda y su terminal no puede usar `security` ni `secret-tool`")
        aun = _t("modelos.llave.agents_still_kc", "pedírsela al llavero")
    elif donde == "dpapi":
        regla = _t("modelos.llave.agents_rule2", "sus herramientas de archivos no pueden abrir la "
                   "bóveda")
        aun = _t("modelos.llave.agents_still_dpapi", "descifrarla")
    else:
        regla = _t("modelos.llave.agents_rule2", "sus herramientas de archivos no pueden abrir la "
                   "bóveda")
        aun = _t("modelos.llave.agents_still_file", "leer el archivo")
    return _t("modelos.llave.agents_p2", "Tus agentes no la reciben. En {con}, {regla}. En {sin} "
              "no hay esa regla. Un programa que corra con tu usuario aún podría {aun}.",
              con=_lista(con), regla=regla, sin=_lista(sin), aun=aun)


def _en_sesion_txt(did, var):
    """Con qué deciden los usos DENTRO de las sesiones de tus agentes cuando la
    llave viene de una variable exclusiva de Workspace (que ningún motor
    recibe), en el orden en que el decisor la busca ahí: la variable estándar
    del proveedor si la exportaste (y se cobra a esa llave), la guardada en
    Workspace, o ninguna (revisor sobre ed793cd8, D)."""
    std = ""
    try:
        std = str((DC.meta(did) or {}).get("key_env_std") or "")
        from deciders import _systemone as SO
        if std and (os.environ.get(std) or "").strip() and not SO._cargada_por_la_boveda(std):
            return _t("modelos.llave.where_env_solo_std", "Tus agentes no la reciben: dentro de sus "
                      "sesiones los usos deciden con {std}, la de tu sistema, y se cobra a esa "
                      "llave.", std=std)
        import secret_store
        if secret_store.has(var):
            return _t("modelos.llave.where_env_solo_saved", "Tus agentes no la reciben: dentro de sus "
                      "sesiones los usos deciden con la que guardaste en Workspace.")
    except Exception:
        pass
    return _t("modelos.llave.where_env_solo", "Tus agentes no la reciben, así que los usos dentro de "
              "sus sesiones no deciden con ella: guárdala aquí para que también decidan ahí.")


def key_facts(did):
    """«Tu llave, en simple»: [(qué, en palabras)] para un decisor con llave, o
    None si no usa (uno local). Cada frase describe lo que el código hace HOY
    (secret_store, rutas_protegidas, deciders/_systemone, decisions.redact,
    esta pantalla); «Dónde vive» y «Tus agentes», según dónde vive de verdad
    (donde_vive) — tests/test_modelos_llave.py prueba cada frase."""
    m = DC.meta(did)
    if not m.get("key_env"):
        return None
    if m.get("key_spend_limit"):
        consejo = _t("modelos.llave.advice_cap", "Crea en {site} una llave solo para Workspace, con "
                     "un tope de gasto.", site=_site(did))
    else:
        consejo = _t("modelos.llave.advice", "Crea en {site} una llave solo para Workspace.",
                     site=_site(did))
    consejo += " " + _t("modelos.llave.advice_revoke", "Si algún día dudas, desconéctala aquí y "
                        "revócala allá: con eso queda muerta en todos lados.")
    donde, var = donde_vive(did)
    # una variable ESTÁNDAR del proveedor exportada en tu sistema SÍ llega a
    # los motores (es para ellos); una exclusiva de Workspace, jamás
    # (secret_store.es_solo_workspace — Greptile 0.8.x, 1)
    estandar = False
    if donde == "entorno":
        try:
            import secret_store
            estandar = not secret_store.es_solo_workspace(var)
        except Exception:
            estandar = False
        dv = _t("modelos.llave.where_env", "La lee de una variable de tu sistema ({var}): "
                "Workspace no la guarda. Nosotros nunca la vemos.", var=var)
        dv += " " + (_t("modelos.llave.where_env_std", "Los motores que abras también la reciben: "
                        "es la variable estándar del proveedor.") if estandar else
                     _en_sesion_txt(did, var))
    else:
        dv = where_text(donde)
    quien = (_t("modelos.llave.who_env_std", "Al pegarla ves puntos. No aparece en el Historial y, "
                "si se cuela en un texto que mandas a un decisor, se borra antes de enviarlo.")
             if estandar else
             _t("modelos.llave.who_p2", "Al pegarla ves puntos. Ningún motor la recibe en su "
                "entorno, no aparece en el Historial y, si se cuela en un texto que mandas a un "
                "decisor, se borra antes de enviarlo."))
    agentes = (_t("modelos.llave.agents_env_std", "Tus agentes la reciben en su entorno, como "
                  "cualquier variable de tu sistema. Si no quieres eso, quítala de tu sistema y "
                  "guárdala aquí.") if estandar else
               agents_text(_boveda_ahora()[0] if donde == "entorno" else donde))
    return [(_t("modelos.llave.where_h", "Dónde vive"), dv),
            (_t("modelos.llave.travel_h", "A dónde viaja"),
             _t("modelos.llave.travel_p", "Solo al proveedor que elegiste ({site}), siempre cifrada "
                "(https) y a esa dirección exacta.", site=_site(did))),
            (_t("modelos.llave.who_h", "Quién la ve"), quien),
            (_t("modelos.llave.agents_h", "Tus agentes"), agentes),
            (_t("modelos.llave.advice_h", "Consejo"), consejo)]


def key_local_txt(did):
    return _t("modelos.llave.local", "{m} no usa llave: todo pasa en esta computadora.",
              m=name(did))


# ── estado ───────────────────────────────────────────────────────────────────
def initial(did=None):
    """`did` = abrir con ese modelo elegido y sus opciones enfocadas (así
    llega Decisores cuando a un modelo le falta algo)."""
    ids = models()
    sel = [i for i, d in enumerate(ids) if selectable(d)]
    i = ids.index(did) if did in ids and selectable(did) else (sel[0] if sel else 0)
    S = {"models": ids, "model": i, "focus": "detail" if did and selectable(did) else "list",
         "opt": 0, "msg": "", "confirm": None, "llave": None, "probe": None}
    if S["focus"] == "detail":
        keys = [o[0] for o in options(S, ids[i])]
        if "connect" in keys:
            S["opt"] = keys.index("connect")
    return S


def selected(S):
    """El modelo elegido, o None si deciders/ no trae ninguno para el socio."""
    ids = S["models"]
    return ids[S["model"] % len(ids)] if ids else None


def busy(S):
    return bool((S.get("probe") or {}).get("running"))


def _auto_activate(S, did):
    """El PRIMER modelo que queda listo, si en Decisores no hay uno activo,
    se activa solo (los usos siguen apagados: se eligen en Decisores)."""
    try:
        if ready(did) and DC.global_model() == DC.OFF:
            DC.set_global_model(did)
            S["msg"] = "✓ " + _t("modelos.msg.activated", "{m} listo y activo en Decisores · los usos "
                                 "siguen apagados: elígelos ahí", m=name(did))
            return True
    except Exception:
        pass
    return False


# ── dibujo (el de engines_tui) ───────────────────────────────────────────────
def word():
    return HL.section_word("motores")


def _K():
    return SB.K()


def _rows(S, K, did, iw):
    """Las opciones del elegido como las filas de engines_tui._detalle."""
    activo = S.get("focus") == "detail"
    ops = options(S, did)
    S["opt"] = max(0, min(S.get("opt", 0), len(ops) - 1))
    estados = [o for o in ops if o[0] not in _ACCIONES]
    lab_w = (max(HL.vis(o[1]) for o in estados) + 2) if estados else 0
    out, fila = [], 0
    for n, (key, lab, val) in enumerate(ops):
        on = activo and n == S["opt"]
        if on:
            fila = len(out)
        cur = ("%s%s %s" % (K["C"] + K["BO"], K["PTR"], K["R"])) if on else "  "
        tinta = (K["WH"] + K["BO"]) if on else K["GREY"]
        if key in _ACCIONES or (key == "probe" and not val):
            flecha = "%s›%s" % ((K["C"] + K["BO"]) if on else K["DK"], K["R"])
            out.append(HL.clip("%s%s%s%s%s%s" % (cur, tinta, lab, K["R"],
                                                 " " * max(1, iw - 3 - HL.vis(lab)), flecha), iw))
            continue
        vcol = {"key": K["OK"], "probe": K["DK"],
                "local": K["OK"] if ready(did) else K["ERR"]}.get(key, K["DIM"])
        out.append(HL.clip("%s%s%s%s%s%s%s" % (cur, tinta, HL.pad(lab, lab_w), K["R"], vcol, val,
                                               K["R"]), iw))
    return out, fila


def _area(S, K, did, iw):
    """Debajo de las filas, en la MISMA columna: la confirmación, la llave
    enmascarada o el resultado de probar."""
    c = S.get("confirm")
    if c and c.get("did") == did:
        return _confirm_lines(S, K, iw, c)
    ll = S.get("llave")
    if ll and ll.get("did") == did:
        return _key_lines(K, iw, ll)
    out = []
    if S.get("revocar") == did:
        out += [""] + ["%s%s%s" % (K["C"] + K["BO"], ln, K["R"]) for ln in DT.wrap(
            _t("modelos.llave.revoke_full", "Para dejarla muerta de verdad, {r}",
               r=revoke_line(did)), iw)[:3]]
    pr = S.get("probe")
    if pr and pr.get("did") == did:
        out += [""] + _probe_lines(K, iw, pr)
    paso = next_step(did) if not out else ""
    if paso:                                    # un local que no está listo: qué hacer
        out = [""] + ["%s%s%s" % (K["C"] + K["BO"], ln, K["R"]) for ln in DT.wrap(
            "→ " + paso, iw)[:2]]
    notas = local_notes(did) if not pr or pr.get("did") != did else []
    if notas:                                   # sin esperar a nadie: qué se usa y por qué
        out = (out or [""]) + ["%s%s%s" % (K["DIM"], ln, K["R"]) for n in notas
                               for ln in DT.wrap(n, iw)[:2]]
    if not out and S.get("focus") == "detail":
        ops = options(S, did)
        key = ops[min(S.get("opt", 0), len(ops) - 1)][0]
        txt = {"connect": _t("modelos.area.key", "Tu llave se guarda en esta computadora (bóveda de "
                             "Workspace): nunca se muestra ni llega a un motor."),
               "probe": _t("modelos.area.probe", "Una pregunta mínima de verdad: si responde, cuánto "
                           "tarda y cuántos tokens usa."),
               "ctx": (_t("modelos.area.ctx_local", "La ventana que este modelo carga en esta "
                          "computadora. Enter elige un límite menor: más rápido.") if is_local(did)
                       else _t("modelos.area.ctx", "Lo más que admite el modelo, medido con "
                               "llamadas reales. Enter elige un límite menor: más barato y más "
                               "rápido.")),
               "local": _t("modelos.area.local", "Corre en esta computadora: tu contexto no sale "
                           "de aquí y no hay llave ni costo. Enter vuelve a mirar su estado."),
               "model": _t("modelos.area.model", "Enter pasa al siguiente modelo y lo guarda. "
                           "Pruébalo antes de dejarlo decidir: cada modelo acierta distinto."),
               "price": None if is_local(did) else _t("modelos.area.price", "Por millón de "
                                                     "tokens. Aproximado, de agregadores de "
                                                     "terceros.")}.get(key)
        if txt:
            out = [""] + ["%s%s%s" % (K["DIM"], ln, K["R"]) for ln in DT.wrap(txt, iw)[:3]]
    return out


def _confirm_lines(S, K, iw, c):
    did = c["did"]
    L = [""] + ["%s%s%s" % (K["C"] + K["BO"], ln, K["R"]) for ln in DT.wrap(
        _t("modelos.c.disconnect", "¿Desconectar {m}? Se borra su llave de esta computadora.",
           m=name(did)), iw)]
    si = _t("modelos.c.yes_disconnect", "Desconectar")
    no = _t("modelos.c.no", "No gracias")
    b = c.get("btn", 1)
    bw = max(10, min(18, (iw - 3) // 2))
    L += DT.hjoin([DT.boton(K, si, bw, b == 0, False), DT.boton(K, no, bw, b == 1, False)], gap=3)
    return [HL.clip(x, iw) for x in L]


def key_where_line():
    """La línea bajo la caja de pegar: adónde va una llave NUEVA en este
    sistema ahora (secret_store.sistema y el modo), nunca en general."""
    donde, modo = _boveda_ahora()
    cola = _t("modelos.key.where_tail", " · nunca se muestra ni llega a un motor")
    if donde == "llavero":
        return _t("modelos.key.where_llavero", "se guarda en el llavero de tu Mac (cifrado)") + cola
    if donde == "dpapi":
        return _t("modelos.key.where_dpapi", "se guarda cifrada con tu cuenta de Windows") + cola
    if donde == "secret-tool":
        return _t("modelos.key.where_secret_tool", "se guarda en el llavero de tu sistema") + cola
    if modo == "keyring":
        return _t("modelos.key.where_keyring_none", "tu sistema no tiene llavero disponible y esta "
                  "computadora quedó configurada para usar solo el llavero: no se podrá guardar")
    if modo == "file":
        return _t("modelos.key.where_file_chosen", "se guarda en un archivo solo tuyo ({perm}), "
                  "porque así quedó configurado en esta computadora", perm=_permiso_archivo()) + cola
    return _t("modelos.key.where_file", "se guarda en un archivo solo tuyo ({perm}) — tu sistema "
              "no tiene llavero disponible", perm=_permiso_archivo()) + cola


def _key_lines(K, iw, ll):
    did = ll["did"]
    buf = ll["buf"]
    L = [""] + ["%s%s%s" % (K["GREY"], ln, K["R"]) for ln in DT.wrap(
        _t("modelos.key.paste", "Pega tu llave de {p}:", p=DC.meta(did).get("provider") or name(did)), iw)]
    puntos = ("•" * min(len(buf), max(1, iw - 12))) if buf else ""
    txt = ("%s%s%s %s(%d)%s" % (K["WH"] + K["BO"], puntos, K["R"], K["DK"], len(buf), K["R"]) if buf
           else "%s%s%s" % (K["DK"], _t("decisores.key.ph", "pega aquí tu llave"), K["R"]))
    L += DT.caja(K, [txt + "%s▏%s" % (K["C"] + K["BO"], K["R"])], iw, K["C"] + K["BO"], heavy=True)
    L += ["%s%s%s" % (K["DK"], ln, K["R"]) for ln in DT.wrap(key_where_line(), iw)[:3]]
    L += ["%s%s%s" % (K["C"], ln, K["R"]) for ln in DT.wrap(key_tip(did), iw)[:3]]
    if keys_line(did):
        L += ["%s%s%s" % (K["DIM"], ln, K["R"]) for ln in DT.wrap(keys_line(did), iw)[:2]]
    return [HL.clip(x, iw) for x in L]


def _probe_lines(K, iw, pr):
    if pr.get("running"):
        sp = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.time() * 10) % 10]
        return ["%s%s %s%s" % (K["C"], sp, _t("modelos.probe.running", "probando…"), K["R"])]
    r = pr.get("res") or {}
    if r.get("ok"):
        import decision_context as C
        tk = r.get("tokens") or {}
        txt = _t("modelos.probe.ok", "✓ respondió «{c}» en {ms} ms · tokens: {i} de entrada, {o} de salida",
                 c=r.get("choice"), ms=int(r.get("ms") or 0), i=tk.get("in", "—"), o=tk.get("out", "—"))
        if r.get("cost_usd") is not None:
            txt += " · " + _t("modelos.probe.cost", "costo {c}", c=C.fmt_cost(r["cost_usd"]))
        return ["%s%s%s" % (K["OK"], ln, K["R"]) for ln in DT.wrap(txt, iw)]
    return ["%s%s%s" % (K["ERR"], ln, K["R"]) for ln in DT.wrap(
        "✗ " + DT._error_txt(r.get("error"), pr.get("did"), timeout_ms=PROBE_TIMEOUT_MS,
                             where="probe", detail=r.get("error_detail"),
                             elapsed_ms=r.get("ms")), iw)[:3]]


def _detalle(S, K, did, iw):
    """La columna de opciones → (líneas, fila del cursor, {línea: lo clicable})."""
    pk = S.get("pick")
    if pk and pk.get("did") == did:
        return _pick_lines(S, K, did, iw)
    filas, fila = _rows(S, K, did, iw)
    area = _area(S, K, did, iw)
    if S.get("llave") or S.get("confirm"):
        fila = len(filas) + max(0, len(area) - 2)
    return filas + area, fila, {n: ("opt", n) for n in range(len(filas))}


# ── la lista de modelos (Enter o clic sobre «modelo») ────────────────────────
#: Con tantos o más modelos, escribir filtra (como la búsqueda de la portada).
FILTER_MIN = 10
#: Filas a la vista de la lista (más: ▲/▼ n más, como en todo el hub).
PICK_ROWS = 8


#: Más lento que esto (el tiempo límite de los usos), la fila dice «lento».
SLOW_MS = 1500


def _medida_txt(m):
    """«95/97 · 0.3 s» (+ «· lento» si su p95 pasa el tiempo límite de los usos)."""
    txt = "%d/%d" % (int(m.get("acierto") or 0), int(m.get("total") or 0))
    p95 = m.get("p95_ms")
    if isinstance(p95, (int, float)):
        txt += " · %.1f s" % (p95 / 1000.0)
        if p95 > SLOW_MS:
            txt += " · " + _t("modelos.pick.slow", "lento")
    return txt


def pick_items(did):
    """[(id, pista)] de los modelos DE DECISIÓN del decisor (los de
    decisions.decider_models: lo que check_model acepta; jamás uno de chat).
    Con medición (decisions.measures, la escribe el chequeo en vivo), la pista
    es lo MEDIDO («95/97 · 0.3 s») y esos van primero, por acierto y luego p95;
    sin medición, la marca, el precio o «en esta computadora» — nada inventado."""
    medidos, resto = [], []
    mod = DC.load(did)
    info = getattr(mod, "model_info", None) if mod is not None else None
    local = is_local(did)
    try:
        medidas = DC.measures(did)
    except Exception:
        medidas = {}
    for x in model_list(did):
        if not x.get("decision", True):
            continue
        m = medidas.get(x["id"]) or medidas.get(DC.normalize_model(did, x["id"]))
        if m:
            medidos.append((x["id"], _medida_txt(m), m))
            continue
        d = {}
        if callable(info):
            try:
                d = info(x["id"]) or {}
            except Exception:
                d = {}
        pista = ""
        if local:
            pista = _t("modelos.local.here", "en esta computadora")
        elif d.get("price_in_per_m") is not None:
            pista = _t("modelos.pick.price", "${p} por M de entrada", p=d["price_in_per_m"])
        elif d.get("brand"):
            pista = str(d["brand"])
        if d.get("slow"):
            pista = (pista + " · " if pista else "") + _t("modelos.pick.slow", "lento")
        resto.append((x["id"], pista))

    def clave(t):
        m = t[2]
        tasa = (m.get("acierto") or 0) / float(m.get("total") or 1)
        p95 = m.get("p95_ms") if isinstance(m.get("p95_ms"), (int, float)) else float("inf")
        return (-tasa, p95)
    medidos.sort(key=clave)
    return [(i, p) for i, p, _m in medidos] + resto


def _filtro(S, items):
    pk = S.get("pick") or {}
    if len(items) < FILTER_MIN or not pk.get("q"):
        return items
    q = HL._lz_norm(pk["q"])
    return [it for it in items if q in HL._lz_norm(it[0] + " " + it[1])]


def open_pick(S, did):
    """Abre la lista del decisor (si trae 2 o más). → True si la abrió."""
    items = pick_items(did)
    if len(items) < 2:
        return False
    ids = [i for i, _p in items]
    cur = current_model(did)
    S["pick"] = {"did": did, "q": "", "sel": ids.index(cur) if cur in ids else 0}
    return True


def close_pick(S):
    S["pick"] = None
    did = selected(S)
    if did:
        keys = [o[0] for o in options(S, did)]
        if "model" in keys:
            S["opt"] = keys.index("model")


def _pick_lines(S, K, did, iw):
    """La columna con la lista: título, búsqueda (si son muchos), las filas
    (pick_list) y, en Ollama, cuántos de chat no sirven (al pie, no como filas)."""
    pk = S["pick"]
    todos = pick_items(did)
    items = _filtro(S, todos)
    pk["sel"] = max(0, min(pk.get("sel", 0), len(items) - 1)) if items else 0
    cur = current_model(did)
    tit = _t("modelos.pick.title", "modelo de {m}", m=name(did))
    out = [HL.clip("%s%s%s %s%s%s" % (K["B2"] + K["BO"], tit, K["R"], K["DK"],
                                      K["SEP"] * max(1, iw - HL.vis(tit) - 1), K["R"]), iw)]
    if len(todos) >= FILTER_MIN:
        q = pk.get("q") or ""
        if q:
            out.append(HL.clip("%s› %s%s%s%s▏%s" % (K["C"] + K["BO"], K["R"], K["WH"], q, K["C"],
                                                   K["R"]), iw))
        else:
            out.append(HL.clip("%s› %s%s" % (K["DK"], _t("hub.lanzador.search_ph", "buscar…"),
                                             K["R"]), iw))
    clic, fila = {}, len(out)
    if items:
        filas = []
        for mid, pista in items:
            txt = ("● " if mid == cur else "  ") + mid
            if HL.vis(txt) + HL.vis(pista) + 5 > iw:
                pista = ""                     # el nombre entero gana a la pista
            filas.append((txt, pista, "DIM"))
        lineas = SB.pick_list(K, filas, pk["sel"], iw, min(len(filas), PICK_ROWS))
        base = len(out)
        for j, idx in enumerate(SB.pick_list.last_rows):
            if idx is not None:
                clic[base + j] = ("pick", items[idx][0])
                if idx == pk["sel"]:
                    fila = base + j
        out += lineas
    else:
        out.append(HL.clip("%s%s%s" % (K["DIM"], _t("modelos.pick.no_match", "nada coincide con "
                                                     "«{q}»", q=pk.get("q") or ""), K["R"]), iw))
    chat = int(DC.decider_status(did).get("chat_models") or 0) if is_local(did) else 0
    if chat:
        out.append("")
        nota = (_t("modelos.note.chat_one", "1 modelo de chat descargado no sirve para decidir")
                if chat == 1 else _t("modelos.note.chat_many", "{n} modelos de chat descargados "
                                     "no sirven para decidir", n=chat))
        out += ["%s%s%s" % (K["DIM"], ln, K["R"]) for ln in DT.wrap(nota, iw)[:2]]
    return out, fila, clic


def _pick_choose(S, did, mid):
    """Elegir un modelo de la lista: se guarda, aviso de una línea y de vuelta
    a las opciones con el nuevo a la vista."""
    try:
        nuevo = DC.set_decider_model(did, mid)
    except ValueError as e:
        S["msg"] = str(e) or _t("modelos.msg.model_err", "No pude guardar ese modelo · intenta "
                                "de nuevo")
        return
    close_pick(S)
    S["focus"] = "detail"
    S["msg"] = "✓ " + _t("modelos.msg.model", "Modelo de {m}: {x} · guardado", m=name(did), x=nuevo)
    if is_local(did):
        DC.warm(did)
    if (S.get("probe") or {}).get("did") == did and not busy(S):
        S["probe"] = None                     # el resultado de antes era de otro modelo


def pick_act(S, key):
    """Teclas con la lista abierta: ↑↓ mueve · Enter elige · Esc / ← cierra sin
    cambiar · con 10 o más, escribir filtra (Retroceso borra, Ctrl+U limpia).
    Con algo escrito, el primer Esc solo limpia el filtro (la lista sigue
    abierta, en el mismo modelo); el siguiente cierra."""
    pk = S["pick"]
    did = pk["did"]
    todos = pick_items(did)
    filtra = len(todos) >= FILTER_MIN
    items = _filtro(S, todos)
    if key == "\x1b" and filtra and pk.get("q"):
        sel = items[max(0, min(pk.get("sel", 0), len(items) - 1))][0] if items else None
        ids = [i for i, _p in todos]
        pk["q"], pk["sel"] = "", ids.index(sel) if sel in ids else 0
        return
    if key in ("\x1b", "left") or (key in ("q", "Q") and not filtra):
        close_pick(S)
        return
    if key in ("up", "down", "tab"):
        if items:
            pk["sel"] = (pk.get("sel", 0) + (-1 if key == "up" else 1)) % len(items)
        return
    if key in ("\r", "\n") or (key == " " and not filtra):
        if items:
            _pick_choose(S, did, items[max(0, min(pk.get("sel", 0), len(items) - 1))][0])
        return
    if not filtra:
        return
    if key in ("\x7f", "\x08"):
        pk["q"], pk["sel"] = (pk.get("q") or "")[:-1], 0
    elif key == "\x15":
        pk["q"], pk["sel"] = "", 0
    elif len(key) == 1 and key.isprintable() and key != " ":
        pk["q"], pk["sel"] = ((pk.get("q") or "") + key)[:40], 0


# ── clics (mouse primero: cada fila de la lista y de las opciones) ───────────
def click(S, x, y):
    """Un clic en (x, y) (1-based, como la terminal): una fila de la lista de
    modelos elige ese modelo; una opción la aplica (como Enter: «modelo» abre
    la lista); un decisor de la izquierda lo elige."""
    hit = S.get("_hit") or {}
    if not hit or S.get("info") or S.get("llave") or S.get("confirm"):
        return
    fila = (y - 1) - SB.frame.last_body_row
    col = (x - 1) - SB.frame.last_body_col
    j = fila - hit.get("det_off", 0)
    if col >= hit.get("det_col", 0) and j in hit.get("det", {}):
        tipo, v = hit["det"][j]
        if tipo == "pick":
            _pick_choose(S, selected(S), v)
            return
        S["focus"], S["opt"] = "detail", v
        _aplica(S)
        return
    i = fila - hit.get("list_off", 0)
    if col < hit.get("list_w", 0) and i in hit.get("list", {}):
        S["pick"] = None
        S["model"], S["focus"], S["opt"] = hit["list"][i], "list", 0


def _items(S):
    out = []
    for d in S["models"]:
        txt, col = state(d)
        out.append((name(d), txt, col) + (() if selectable(d) else ("DK",)))
    return out


def _cuerpo(S, K, iw):
    """Lista de modelos │ opciones del elegido — engines_tui._cuerpo."""
    did = selected(S)
    if did is None:                           # deciders/ sin modelos: lo dice y ya
        S["_cur"] = 0
        return ["", DT.center("%s%s%s" % (K["DIM"], _t("modelos.empty", "No hay modelos de decisión "
                                                        "instalados en este Workspace"), K["R"]), iw)]
    der = S.get("focus") == "detail" or bool(S.get("confirm")) or bool(S.get("llave"))
    items = _items(S)
    sel = S["model"] % len(S["models"])
    tail = "◂" if der else "▸"
    if S.get("pick"):
        # la lista de modelos usa la caja ENTERA: el nombre largo y lo medido
        # («95/97 · 0.3 s · lento») caben juntos; Esc vuelve a las dos columnas
        lineas, fila, clic = _detalle(S, K, did, iw)
        S["_cur"] = fila
        S["_hit"] = {"det_off": 0, "det_col": 0, "det": clic, "list_off": 0, "list_w": 0,
                     "list": {}}
        return lineas
    if iw < LIST_W + SB.SPLIT_GAP + 26:
        arriba = SB.pick_list(K, items, sel, iw, min(len(items), 8), sel_tail=tail)
        lista = {j: i for j, i in enumerate(SB.pick_list.last_rows) if i is not None}
        opciones, fila, clic = _detalle(S, K, did, iw)
        S["_cur"] = len(arriba) + 2 + fila if der else min(sel, len(arriba) - 1)
        S["_hit"] = {"det_off": len(arriba) + 2, "det_col": 0, "det": clic,
                     "list_off": 0, "list_w": iw, "list": lista}
        etiqueta = "%s · %s" % (name(did), ET._t("motores.opts", "opciones", "options"))
        return SB.stack(K, arriba, opciones, iw, label=etiqueta, active=der)
    opciones, fila, clic = _detalle(S, K, did, iw - LIST_W - SB.SPLIT_GAP)
    izq = SB.pick_list(K, items, sel, LIST_W, max(len(opciones), min(len(items), 8)), sel_tail=tail)
    S["_hit"] = {"det_off": 0, "det_col": LIST_W + SB.SPLIT_GAP, "det": clic, "list_off": 0,
                 "list_w": LIST_W,
                 "list": {j: i for j, i in enumerate(SB.pick_list.last_rows) if i is not None}}
    S["_cur"] = fila if der else min(sel, len(izq) - 1)
    return SB.split(K, izq, opciones, iw, LIST_W)


# ── la llave (campo enmascarado en la columna de opciones) ───────────────────
def key_act(S, key):
    """Escribiendo la llave: todo lo que se teclea es de la llave (también
    i, ? y q). Enter la guarda en la bóveda; Esc cancela. Nada se imprime."""
    ll = S["llave"]
    if key in ("\x1b", "\x03"):
        S["llave"] = None
        S["msg"] = _t("decisores.msg.key_cancel", "Conexión cancelada · no se guardó nada")
        return
    if key in ("\r", "\n"):
        r = DC.connect(ll["did"], ll["buf"])
        if not r.get("ok"):
            S["msg"] = (_t("decisores.msg.key_invalid", "Esa llave no parece válida (8 o más "
                           "caracteres, sin espacios)") if r.get("error") == "invalid_key"
                        else _t("decisores.msg.key_store", "No pude guardarla en la bóveda de Workspace"))
            return
        did = ll["did"]
        S["llave"] = None
        S["msg"] = "✓ " + _t("modelos.msg.key_ok", "{m} conectado · la llave quedó guardada en esta "
                             "computadora", m=name(did))
        if r.get("aviso"):                # sin llavero del sistema: se dice, nunca en silencio
            S["msg"] = r["aviso"]
        if _auto_activate(S, did) and r.get("aviso"):
            # «listo y activo» no tapa el aviso de la bóveda: va primero, por si
            # la línea se corta (Greptile 0.9.0, 8)
            S["msg"] = r["aviso"] + " · " + S["msg"]
        keys = [o[0] for o in options(S, did)]
        S["opt"] = keys.index("probe")
        return
    if key in ("\x7f", "\x08"):
        ll["buf"] = ll["buf"][:-1]
    elif key == "\x15":
        ll["buf"] = ""
    elif len(key) == 1 and key.isprintable():
        ll["buf"] = (ll["buf"] + key)[:512]


# ── probar (una llamada real chiquita) ───────────────────────────────────────
def start_probe(S, did):
    pr = {"did": did, "running": True, "res": None}
    S["probe"] = pr

    def run():
        pr["res"] = DC.consult(DC.MANUAL, "choice", PROBE_Q, PROBE_OPTS, "", decider=did,
                               timeout_ms=PROBE_TIMEOUT_MS, level="ask", log=False)
        pr["running"] = False
        if (pr["res"] or {}).get("ok"):
            _auto_activate(S, did)
    th = threading.Thread(target=run, daemon=True, name="decider-probe")
    th.start()
    return th


# ── ayuda (i / ?) ────────────────────────────────────────────────────────────
def _info_txt():
    return (_t("modelos.info.list.p", "Los motores trabajan (programan, escriben, conversan); los "
               "modelos de decisión eligen entre opciones fijas y dicen qué tan seguros están. Aquí "
               "los dejas listos una sola vez: conectas tu llave (o abres Ollama) y lo pruebas."),
            [_t("modelos.info.detail.l2", "Llave — enmascarada, en la bóveda"),
             _t("modelos.info.detail.l3", "Probar — latencia, tokens y costo reales"),
             _t("modelos.info.detail.l4", "Dónde decide: en la sección Decisores")])


def _flujo_que():
    return [(_t("modelos.info.f2", "lo conectas"), _t("modelos.info.f2n", "tu llave")),
            (_t("modelos.info.f3", "lo pruebas"), _t("modelos.info.f3n", "una llamada real")),
            (_t("modelos.info.f4", "decide"), _t("modelos.info.f4n", "en Decisores"))]


def _flujo_como():
    return [(_t("modelos.info.c1", "lee deciders/"), _t("modelos.info.c1n", "cada uno con su META")),
            (_t("modelos.info.c2", "su API, directo"), _t("modelos.info.c2n", "sin paquetes extra")),
            (_t("modelos.info.c3", "llave a la bóveda"), _c3n()),
            (_t("modelos.info.c4", "mismo contrato"), _t("modelos.info.c4n", "decide() para todos"))]


def _c3n():
    donde = _boveda_ahora()[0]
    if donde in ("llavero", "secret-tool"):
        return _t("modelos.info.c3n_kc", "en el llavero, ningún motor")
    if donde == "dpapi":
        return _t("modelos.info.c3n_dpapi", "cifrada, ningún motor")
    return _t("modelos.info.c3n", "0600, ningún motor")


def _como_p():
    return _t("modelos.info.how.p", "Cada modelo es un archivo en deciders/ con su META (nombre, "
              "llave, límite, precio): esta pantalla se arma sola con eso, con el mismo diseño que "
              "la de motores de agentes. Todos hablan System One con lo que ya trae Python, sin "
              "paquetes extra; Ollama, en esta computadora. El primero que queda listo se activa "
              "en Decisores, con los usos apagados.")


def _llave_titulo():
    return _t("modelos.llave.title", "Tu llave, en simple")


def key_blocks(did):
    """La página «Tu llave, en simple» del decisor elegido (en bloques)."""
    hechos = key_facts(did) if did else None
    if hechos is None:
        return [("h", _llave_titulo()), ("p", key_local_txt(did) if did else "")]
    out = [("h", _llave_titulo() + " · " + (DC.meta(did).get("provider") or name(did))),
           ("kv", hechos)]
    if keys_line(did):
        out += [("gap",), ("dim", keys_line(did))]
    return out


def _otra_pagina(page):
    return (_t("modelos.info.page_que", "qué es") if page == "llave"
            else _t("modelos.info.page_llave", "tu llave"))


def info_blocks(did=None, page="que"):
    if page == "llave":
        return [("dim", "Tab · " + _otra_pagina(page)), ("gap",)] + key_blocks(did)
    texto, lista = _info_txt()
    return [("dim", "Tab · " + _otra_pagina(page)), ("flow", _flujo_que()), ("gap",), ("p", texto),
            ("list", lista), ("gap",), ("h", _t("decisores.info.how", "cómo lo hicimos")),
            ("flow", _flujo_como()), ("p", _como_p()), ("dim", DT._como_dim())]


def info_body(K, iw, did=None, page="que"):
    if page == "llave":
        return [HL.clip(x, iw) for x in SB.render_blocks(K, key_blocks(did), iw)]
    texto, lista = _info_txt()
    L = [DT.titulo(K, _t("decisores.info.what", "qué es"), iw, 0), ""] + DT.flujo(K, _flujo_que(), iw, 0) + [""]
    lw = (iw - 3) // 2
    izq = ["%s%s%s" % (K["WH"], ln, K["R"]) for ln in DT.wrap(texto, lw)]
    der = []
    for x in lista:
        for j, ln in enumerate(DT.wrap(x, lw - 2)):
            der.append("%s%s%s %s%s%s" % (K["C"], "·" if j == 0 else " ", K["R"], K["GREY"], ln, K["R"]))
    for i in range(max(len(izq), len(der))):
        a = izq[i] if i < len(izq) else ""
        b = der[i] if i < len(der) else ""
        L.append(HL.pad(a, lw) + " %s│%s " % (K["DK"], K["R"]) + b)
    L += ["", DT.titulo(K, _t("decisores.info.how", "cómo lo hicimos"), iw, 3), ""] \
        + DT.flujo(K, _flujo_como(), iw, 2) + [""]
    L += ["%s%s%s" % (K["GREY"], ln, K["R"]) for ln in DT.wrap(_como_p(), iw)]
    L += ["%s%s%s" % (K["DK"], ln, K["R"]) for ln in DT.wrap(DT._como_dim(), iw)]
    return [HL.clip(x, iw) for x in L]


def info_render(S, K, w, h, titulo_caja):
    """La ayuda (i): dos páginas — «qué es» y «tu llave» (Tab pasa de una a
    otra; así ninguna pierde el wordmark grande)."""
    bw = max(60, min(96, w - 10))
    st = S["info"] if isinstance(S["info"], dict) else {}
    page = st.get("page", "que")
    did = selected(S)
    if bw < 70:
        return SB.info_frame(K, w, h, word(), titulo_caja, info_blocks(did, page), state=S["info"],
                             box_w=60)
    out = SB.frame(K, w, h, word(), titulo_caja, lambda iw: info_body(K, iw, did, page),
                   ((u"↑↓", _t("decisores.k.move_info", "mover")), ("Tab", _otra_pagina(page)),
                    ("Esc", _t("decisores.k.close", "cerrar"))),
                   box_w=bw, scroll=st.get("scroll", 0))
    st["scroll"] = max(0, min(st.get("scroll", 0), SB.frame.last_max_scroll))
    return out


# ── marco (las fichas de engines_tui) ────────────────────────────────────────
def _chips(S):
    pk = S.get("pick")
    if pk:
        esc = (_t("modelos.k.clear_filter", "limpia") if pk.get("q")
               and len(pick_items(pk["did"])) >= FILTER_MIN else _t("modelos.k.close", "cierra"))
        out = ((u"↑↓", _t("modelos.k.move", "mueve")), ("Enter", _t("modelos.k.choose", "elige")),
               ("Esc", esc))
        if len(pick_items(pk["did"])) >= FILTER_MIN:
            out += (("abc", _t("hub.lanzador.hint.search", "busca")),)
        return out
    if S.get("llave") is not None:
        return (("Enter", _t("decisores.k.save", "guardar")), ("Ctrl+U", _t("decisores.k.clear", "borrar")),
                ("Esc", ET._t("motores.k.cancel", "cancela", "cancel")))
    if S.get("confirm"):
        return ((u"←→", ET._t("motores.k.pick", "elige", "pick")),
                ("Enter", ET._t("motores.k.confirm", "confirma", "confirm")),
                ("Esc", _t("modelos.k.no", "no gracias")))
    if S.get("focus") == "detail":
        return ((u"↑↓", ET._t("motores.k.option", "opción", "option")),
                ("Enter", ET._t("motores.k.do", "aplica", "apply")),
                (u"←", ET._t("motores.k.to_list", "a la lista", "to the list")),
                ("i", ET._t("motores.k.info", "cómo funciona", "how it works")))
    return ((u"↑↓", ET._t("motores.k.pick", "elige", "pick")),
            (u"→", ET._t("motores.k.to_opts", "sus opciones", "its options")),
            ("i", ET._t("motores.k.info", "cómo funciona", "how it works")),
            ("q", ET._t("motores.k.back", "vuelve", "back")))


def render(S, w, h):
    K = _K()
    titulo = _t("modelos.box", "MODELOS DE DECISIÓN")
    if S.get("info"):
        return info_render(S, K, w, h, "%s · %s" % (_t("decisores.info.title", "AYUDA"), titulo))
    return SB.frame(K, w, h, word(), titulo, lambda iw: _cuerpo(S, K, iw), _chips(S),
                    msg=S.get("msg", ""), cursor_line=lambda: S.get("_cur", 0),
                    box_w=LIST_W + SB.SPLIT_GAP + DETAIL_W,
                    stable_rows=max(min(len(S["models"]), 8), 10))


# ── acciones (las de engines_tui.act) ────────────────────────────────────────
def _confirm_act(S, key):
    c = S["confirm"]
    if key in ("left", "right", "tab"):
        c["btn"] = 1 - c.get("btn", 1)
        return
    if key in ("\r", "\n", " ") and c.get("btn", 1) == 0:
        S["confirm"] = None
        r = DC.disconnect(c["did"])
        S["msg"] = ("✓ " + _t("decisores.msg.key_removed", "{m} desconectado: la llave se borró de "
                              "esta computadora", m=name(c["did"])) + " · " +
                    revoke_line(c["did"])) if r.get("ok") else \
            _t("decisores.msg.key_store", "No pude guardarla en la bóveda de Workspace")
        if r.get("ok"):
            S["revocar"] = c["did"]            # y abajo, entero (el aviso se corta en 80 columnas)
        return
    S["confirm"] = None                     # No gracias / Esc / cualquier otra tecla
    S["msg"] = _t("modelos.msg.no_disconnect", "La llave sigue conectada")


def _aplica(S):
    """Enter sobre la opción elegida — ahí mismo."""
    did = selected(S)
    ops = options(S, did)
    key = ops[min(S.get("opt", 0), len(ops) - 1)][0]
    if busy(S):
        S["msg"] = _t("modelos.msg.busy", "Espera a que termine…")
    elif key == "connect":
        S["llave"] = {"did": did, "buf": ""}
    elif key == "disconnect":
        S["confirm"] = {"kind": "disconnect", "did": did, "btn": 1}
    elif key == "key" and DC.key_source(did) == "env":
        S["msg"] = _t("decisores.msg.key_env", "La llave viene del entorno del sistema ({var}): "
                      "quítala ahí", var=DC.key_var(did) or DC.key_env(did))
    elif key == "local":
        _recheck(S, did)
    elif key == "model":
        if not open_pick(S, did):              # uno solo (o ninguno): no hay qué elegir
            lista = model_list(did)
            S["msg"] = (_t("modelos.msg.one_model", "{m} tiene un solo modelo de decisión: {x}",
                           m=name(did), x=lista[0]["id"]) if lista else
                        (next_step(did) or _t("modelos.model.none", "ninguno descargado")))
    elif key == "probe":
        if not ready(did):
            S["msg"] = (next_step(did) if is_local(did) and next_step(did) else
                        _t("modelos.msg.probe_needs", "Para probarlo hace falta la llave"))
        else:
            if is_local(did):
                DC.warm(did)              # cargar el modelo en frío no cabe en la prueba
            start_probe(S, did)
    elif key == "ctx":
        import decision_context as C
        n = set_limit(did, _next_limit(did))
        S["msg"] = _t("modelos.msg.limit", "Límite de contexto de {m}: {n} tokens · guardado",
                      m=name(did), n=C.fmt_exact(n))
    return True


def _recheck(S, did):
    """Enter en el estado de un decisor local: vuelve a mirar (sin caché)."""
    try:
        fn = getattr(DC.load(did), "invalidate", None)
        if callable(fn):
            fn()
    except Exception:
        pass
    txt, _col = state(did)
    S["msg"] = _t("modelos.msg.recheck", "{m}: {st}", m=name(did), st=txt)
    if ready(did):
        _auto_activate(S, did)


def _en_la_llave(S):
    """¿El socio está sobre una opción de la llave? (la ayuda abre en «tu llave»)."""
    did = selected(S)
    if not did or S.get("focus") != "detail":
        return False
    ops = options(S, did)
    return bool(ops) and ops[min(S.get("opt", 0), len(ops) - 1)][0] in ("connect", "key", "disconnect")


def _move(S, d):
    """↑↓ en la lista: solo entre los modelos que se pueden elegir."""
    ids = S["models"]
    sel = [i for i, x in enumerate(ids) if selectable(x)]
    if not sel:
        return
    cur = S["model"] if S["model"] in sel else sel[0]
    S["model"] = sel[(sel.index(cur) + d) % len(sel)]
    S["opt"] = 0


def act(S, key):
    """True = sigue · False = sale (Esc/q desde la lista)."""
    xy = SB.parse_mouse(key)
    if xy is not None:                         # un clic: nunca sale de la pantalla
        if not busy(S):
            S["msg"] = ""
        click(S, *xy)
        return True
    if S.get("pick") and key != "\x03":
        S["msg"] = ""
        pick_act(S, key)
        return True
    if S.get("llave") is not None:
        key_act(S, key)
        return True
    if S.get("confirm"):
        _confirm_act(S, key)
        return True
    S.pop("revocar", None)
    if S.get("info") and key in ("tab", "right_tab", "right", "left"):
        inf = S["info"]
        inf["page"] = "que" if inf.get("page", "que") == "llave" else "llave"
        inf["scroll"] = 0
        return True
    abre = not S.get("info") and key in SB.INFO_KEYS
    if SB.info_key(S, key):
        if abre and isinstance(S.get("info"), dict) and _en_la_llave(S):
            S["info"]["page"] = "llave"
        return True
    if key == "\x03":
        return False
    S["msg"] = "" if not busy(S) else S.get("msg", "")
    if selected(S) is None:
        return key not in ("q", "Q", "\x1b")
    if S.get("focus") == "detail":
        ops = options(S, selected(S))
        if key in ("\x1b", "left", "q", "Q"):
            S["focus"] = "list"
        elif key in ("up", "down"):
            S["opt"] = (S.get("opt", 0) + (-1 if key == "up" else 1)) % len(ops)
        elif key in ("\r", "\n", " "):
            return _aplica(S)
        return True
    if key in ("q", "Q", "\x1b"):
        return False
    if key in ("up", "down", "tab"):
        _move(S, -1 if key == "up" else 1)
    elif key in ("\r", "\n", "right", " "):
        if selectable(selected(S)):
            S["focus"] = "detail"
            S["opt"] = 0
    return True


import responsive_ui as _responsive  # noqa: E402
render = _responsive.renderer(render, 'MODELOS')
act = _responsive.action(act)


# ── drivers (genéricos: también los usa la puerta de Motores) ───────────────
def _size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 112, 44


def loop(S, render_fn, act_fn, busy_fn=busy, mouse=False):
    """El bucle de teclado de una pantalla (Unix y Windows). `mouse` = prende los
    clics (SGR-1006, como la portada) mientras la pantalla está abierta; en
    Windows, por ahora, solo teclado (completo)."""
    if os.name == "nt":
        return _loop_windows(S, render_fn, act_fn, busy_fn)
    return _loop_unix(S, render_fn, act_fn, busy_fn, mouse)


def _draw(tout, S, render_fn, first=False):
    w, h = _size()
    try:
        _responsive.paint(tout, render_fn(S, w, h), first=first)
    except Exception:
        pass


def _loop_unix(S, render_fn, act_fn, busy_fn, mouse=False):
    import termios
    import tty
    fd = os.open("/dev/tty", os.O_RDWR)
    tout = open("/dev/tty", "w")
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h\033[?25l" + ("\033[?1000h\033[?1006h" if mouse else ""))
        _draw(tout, S, render_fn, first=True)
        teclas = SB.KeyReader(fd)
        teclas.mouse = mouse                           # los clics, como la portada
        while True:
            key = teclas.get(0.15 if busy_fn(S) else 0.5)
            if key is None:
                _draw(tout, S, render_fn)
                continue
            if not key:                                # secuencia que no aplica
                continue
            if not act_fn(S, key):
                break
            if not teclas.pending():                   # una ráfaga (pegar) = un dibujo
                _draw(tout, S, render_fn)
    except KeyboardInterrupt:                          # una señal de fuera: salir limpio
        pass
    finally:
        try:
            tout.write(("\033[?1000l\033[?1006l" if mouse else "") + "\033[?25h\033[?1049l")
            tout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.close(fd)
        except Exception:
            pass
    return 0


def _loop_windows(S, render_fn, act_fn, busy_fn):
    tout = sys.stdout
    tout.write("\033[?1049h\033[?25l")
    _draw(tout, S, render_fn, first=True)
    # la consola de verdad (ReadConsoleInputW): ¿ ¡ « » € por SSH, Shift-Tab
    teclas = SB.WinKeyReader()
    try:
        while True:
            key = teclas.get(0.15 if busy_fn(S) else 0.5)
            if key is None:
                _draw(tout, S, render_fn)
                continue
            if key and not act_fn(S, key):
                break
            if not teclas.pending():                   # una ráfaga (pegar) = un dibujo
                _draw(tout, S, render_fn)
    except KeyboardInterrupt:                          # Ctrl+C en Windows es una señal: salir
        pass
    finally:
        try:
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
        except Exception:
            pass
    return 0


def _interactive():
    """¿Consola de verdad? (también la usa Motores). `isatty()` no basta en
    Windows: NUL pasa por terminal y la pantalla esperaba teclas para
    siempre; _console es la regla compartida de Workspace."""
    try:
        import _console
        return _console.interactive()
    except Exception:
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            return False


@_theme_screen
def run(did=None):
    S = initial(did=did)
    if not _interactive():
        print("\n".join(render(S, 112, 44)))
        return 0
    try:
        return loop(S, render, act, mouse=True)
    except KeyboardInterrupt:                          # Ctrl+C: salir (como «q»)
        return 0
    except Exception as e:
        try:
            sys.stdout.write("\033[?25h\033[?1049l")
        except Exception:
            pass
        print("modelos: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(run())
