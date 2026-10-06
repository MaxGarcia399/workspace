#!/usr/bin/env python3
"""WORKSPACE · onboarding_tui — el PRIMER ARRANQUE guiado (repo público).

La primera vez que alguien baja Workspace y lo abre, no hay config, no hay
agentes y no sabe qué es esto. Este flujo lo recibe al estilo WORKSPACE
(wordmark, cajas del tema, transparencia total) y lo deja operativo en
3 etapas + un resumen honesto de dónde quedó todo:

  bienvenida → 1 MOTORES → 2 APARIENCIA → 3 AGENTE → (tono) → resumen

Qué REUSA (nada se duplica — este módulo solo orquesta):
  · motores     harnesses.installed()/describe(probe=True): detección real de
                binarios en PATH + sesión/login de cada CLI (el probe corre en
                un hilo daemon — la UI nunca se congela). Solo se ofrecen los
                SOPORTADOS: claude-code · codex · antigravity. La elección se
                persiste como `modelos.default_engine` (config_engine, tier A).
  · apariencia  el sistema de temas existente: hubtheme.hub_picker() (lista
                curada), ui.theme + ui.background (settings), tuitheme.palette
                (la pantalla ya se pinta con lo elegido = preview real) y
                theme.apply_colors (el fondo OSC de la terminal, en vivo).
  · agente      add_agent_tui COMPLETO (crear / cargar / descubrir): aquí solo
                se elige el camino; el flujo real es la misma pantalla del hub,
                pre-sembrada en la vista elegida.
  · tono        tono_tui COMPLETO, pre-sembrado en el agente recién conectado
                (solo si apareció uno nuevo).

No re-disparo: ~/.claude/workspace/onboarded.json (env WORKSPACE_ONBOARDED lo
pisa — tests herméticos). Se escribe APENAS arranca el flujo (un Ctrl-C a
medias no vuelve a molestar) y se completa al final con el resumen real.
Una máquina que YA tiene agentes registrados se marca "adopcion" en silencio:
el onboarding es para el primer uso, no para quien ya opera. Re-correrlo a
mano: `workspace onboarding`.

Trigger: front.py llama maybe_run() ANTES del hub (solo sin subcomando, con
TTY, sin flag). Fail-soft total: cualquier excepción → al hub normal.

Mismo patrón de pantalla que tono_tui/add_agent_tui (2J3JH al entrar, H +
\\033[K después, altura estable, dos drivers de teclado). Cero dependencias
(stdlib, Python 3.9+). Mac y Windows.
"""
import datetime
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import hublayout as HL                                          # noqa: E402
# i18n (lado cliente): el onboarding lo ve el cliente. Falla-suave — sin el
# módulo, _t() devuelve el español inline (paridad exacta con el flujo de hoy).
try:
    import i18n                                                  # noqa: E402
except Exception:
    i18n = None


def _t(key, es):
    if i18n is None:
        return es
    try:
        s = i18n.t(key)
        return s if s != key else es
    except Exception:
        return es

#: Harnesses OFRECIDOS en el onboarding — los soportados de verdad hoy.
#: harnesses.py puede listar más engines instalados; aquí solo estos tres.
SOPORTADOS = ("claude-code", "codex", "antigravity")

#: Copy honesto por motor: qué es, de quién, cómo se entra. Nada inventado.
_MOTOR_INFO = {
    "claude-code": (
        "Claude Code — el CLI oficial de Anthropic (binario `claude`).",
        "Entra con tu suscripción: corre `claude` una vez y sigue el login.",
        "Es el motor con más integración en Workspace: hooks reales, memoria "
        "inyectada al agente y sesiones del harness."),
    "codex": (
        "Codex — el CLI de OpenAI (binario `codex`), con tu suscripción de "
        "ChatGPT.",
        "Entra con `codex login` en tu terminal.",
        "Workspace lo envuelve; nunca lee ni toca tu token (~/.codex/)."),
    "antigravity": (
        "Antigravity — el CLI `agy` de Google (Gemini).",
        "La sesión se abre con tu cuenta Google desde el propio CLI.",
        "Workspace lo envuelve igual que a los demás motores."),
}

#: Fondos del onboarding = las opciones de ui.background MENOS `personalizado`
#: (pide un #RRGGBB a mano — eso vive en Config, aquí no cabe honesto).
_FONDOS = (("tema", "el del tema activo"), ("negro", "negro puro"),
           ("grafito", "grafito"), ("azul", "azul noche"),
           ("verde", "verde bosque"), ("violeta", "violeta"))

_ETAPAS = ("motores", "apariencia", "agente")

#: Opción extra del paso agente (las otras 3 se toman de add_agent_tui).
_SIN_AGENTE = ("ninguno", "terminar sin agente",
               ("También puedes agregarlo cuando quieras desde el recinto "
                "(«Agregar agente») — crear, cargar o descubrir siguen ahí, "
                "idénticos.",))


# ── flag de primer uso ──────────────────────────────────────────────────────
def flag_path():
    """Dónde queda constancia de que el onboarding corrió. Env
    WORKSPACE_ONBOARDED la pisa (tests herméticos / overrides)."""
    p = os.environ.get("WORKSPACE_ONBOARDED", "").strip()
    if p:
        return os.path.expanduser(p)
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "onboarded.json")


def ya_corrio():
    """¿Ya corrió (o se adoptó) en esta máquina? Un flag ilegible cuenta
    como SÍ corrió: ante la duda, jamás re-molestar en cada arranque."""
    try:
        return os.path.exists(flag_path())
    except Exception:
        return True


def _marcar(extra=None):
    """Escribe/actualiza el flag (merge sobre lo que haya). Falla-suave:
    sin permisos/disco raro → no truena (el peor caso es re-ofrecer)."""
    p = flag_path()
    data = {"version": 1}
    try:
        with open(p, encoding="utf-8") as fh:
            prev = json.load(fh)
        if isinstance(prev, dict):
            data.update(prev)
    except Exception:
        pass
    data["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    data.update(extra or {})
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        pass
    return data


# ── helpers de pantalla (mismo lenguaje que tono_tui) ───────────────────────
def _K():
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


def _wrap(txt, w):
    pal, ln, out = str(txt).split(), "", []
    for p in pal:
        if len(ln) + len(p) + 1 > w:
            out.append(ln)
            ln = p
        else:
            ln = (ln + " " + p).strip()
    if ln:
        out.append(ln)
    return out or [""]


def _divisor(K, txt, w, tono=-1):
    col = (K["WCOL"][tono % len(K["WCOL"])] + K["BO"]) if tono >= 0 \
        else K["DK"]
    regla = K["SEP"] * max(1, w - HL.vis(txt) - 2)
    return HL.clip("%s%s%s %s%s%s" % (col, str(txt), K["R"], K["DK"], regla,
                                      K["R"]), w)


def _parrafo(K, lineas, iw, color=None, bullet=False):
    """Texto envuelto a `iw`, listo para una caja. Una lista = varios
    párrafos con aire entre ellos."""
    out = []
    for n, txt in enumerate(lineas):
        if n:
            out.append("")
        for i, sub in enumerate(_wrap(txt, max(8, iw - (3 if bullet else 1)))):
            pre = (" %s·%s " % (K["DK"], K["R"])) if (bullet and i == 0) \
                else ("   " if bullet else " ")
            out.append(HL.clip(pre + "%s%s%s" % (color or K["DIM"], sub,
                                                 K["R"]), iw))
    return out


# ── datos: motores · temas · agentes ────────────────────────────────────────
def _descriptores():
    """{id: descriptor} de los SOPORTADOS — detección barata (binarios en
    PATH) vía harnesses.describe(probe=False). Falla-suave → vacíos."""
    out = {}
    for eid in SOPORTADOS:
        try:
            import harnesses
            out[eid] = harnesses.describe(eid, probe=False)
        except Exception as e:
            out[eid] = {"id": eid, "name": eid, "installed": False,
                        "binaries_ok": False, "ready": False, "needs": [],
                        "detail": "registro no disponible: %s" % e}
    return out


def _probe_start(S):
    """Hilo daemon que refina el estado con el probe REAL de cada engine
    (sesión/login — puede correr `codex login status`). La UI solo lee."""
    def worker():
        for eid in SOPORTADOS:
            if not (S["harn"].get(eid) or {}).get("binaries_ok"):
                S["probe"][eid] = dict(S["harn"].get(eid) or {})
                continue
            try:
                import harnesses
                S["probe"][eid] = harnesses.describe(eid, probe=True)
            except Exception as e:
                d = dict(S["harn"].get(eid) or {})
                d["ready"], d["detail"] = False, "probe falló: %s" % e
                S["probe"][eid] = d
        S["probing"] = False

    S["probing"] = True
    try:
        threading.Thread(target=worker, daemon=True).start()
    except Exception:
        S["probing"] = False


def _motor_info(eid):
    """Copy traducible por motor: (qué es, cómo se entra, qué cambia). El
    fallback es el literal español de _MOTOR_INFO (paridad exacta)."""
    base = _MOTOR_INFO.get(eid, ("", "", ""))
    return (_t("onboarding.motor.%s.what" % eid, base[0]),
            _t("onboarding.motor.%s.login" % eid, base[1]),
            _t("onboarding.motor.%s.changes" % eid, base[2]))


def _estado_motor(K, S, eid):
    """(texto, color, elegible) — el estado HONESTO de un motor: binario,
    y sesión solo cuando el probe ya respondió. Nada inventado."""
    d = S["harn"].get(eid) or {}
    if not d.get("installed"):
        return (_t("onboarding.motores.st.unavailable",
                   "no disponible en esta instalación"), K["DK"], False)
    if not d.get("binaries_ok"):
        falta = ", ".join("`%s`" % b for b in (d.get("needs") or [])) \
            or _t("onboarding.motores.st.cli", "CLI")
        return (_t("onboarding.motores.st.not_installed",
                   "no instalado — falta {falta} en PATH").format(falta=falta),
                K["DK"], False)
    p = S["probe"].get(eid)
    if p is None:
        return (_t("onboarding.motores.st.checking",
                   "binario ✓ · checando sesión…"), K["DIM"], True)
    if p.get("ready"):
        return (_t("onboarding.motores.st.session_ok",
                   "binario ✓ · sesión activa ✓"), K["OK"], True)
    det = p.get("detail") or _t("onboarding.motores.st.no_session",
                                "sin sesión")
    return (_t("onboarding.motores.st.login_needed",
               "binario ✓ · falta login — {det}").format(det=det), K["B"], True)


def _estado_corto(K, S, eid):
    """Versión compacta del estado (para el resumen): jamás se trunca."""
    d = S["harn"].get(eid) or {}
    if not d.get("binaries_ok"):
        return (_t("onboarding.motores.short.not_installed", "no instalado"),
                K["DK"])
    p = S["probe"].get(eid)
    if p is None:
        return (_t("onboarding.motores.short.binary", "binario ✓"), K["DIM"])
    if p.get("ready"):
        return (_t("onboarding.motores.short.session", "sesión ✓"), K["OK"])
    return (_t("onboarding.motores.short.login", "falta login"), K["B"])


def _temas():
    """[(id, label)] curados para el hub — hubtheme.hub_picker(). Falla-suave
    → el snapshot de choices de ui.theme → ('rose',)."""
    try:
        import hubtheme
        out = [(t.get("id"), t.get("label") or t.get("id"))
               for t in hubtheme.hub_picker() if t.get("id")]
        if out:
            return out
    except Exception:
        pass
    try:
        import settings
        spec = next(s for s in settings.SETTINGS_SCHEMA
                    if s["key"] == "ui.theme")
        return [(c, c) for c in spec.get("choices") or ("rose",)]
    except Exception:
        return [("rose", "rose")]


def _setting(key, default):
    try:
        import settings
        return settings.get(key, default)
    except Exception:
        return default


def _guardar(key, val):
    """Persistir un setting al instante (config_engine: gate + changelog);
    fallback a settings.set pelado. Devuelve (ok, error)."""
    try:
        import config_engine
        r = config_engine.set_setting(key, val, actor="onboarding")
        return bool(r.get("ok")), r.get("error", "")
    except Exception:
        pass
    try:
        import settings
        settings.set(key, val)
        return True, ""
    except Exception as e:
        return False, str(e)


def _aplicar_osc():
    """Pinta fondo/tinta de la terminal con el tema recién elegido (OSC).
    Solo salida interactiva; theme.apply_colors ya es no-op sin tty."""
    try:
        import theme
        import tuitheme
        osc = getattr(tuitheme.palette(), "OSC", None)
        if osc:
            theme.apply_colors(osc)
        else:
            theme.apply("workspace")
    except Exception:
        pass


def _agentes():
    try:
        import agentsreg
        return agentsreg.agents()
    except Exception:
        return []


def _opciones_agente():
    """Las 3 vías REALES de add_agent_tui (mismos textos — una sola fuente)
    + «terminar sin agente»."""
    try:
        import add_agent_tui
        base = list(add_agent_tui.MENU_OPTS)
    except Exception:
        base = [("crear", "crear agente nuevo",
                 ("Un agente desde cero, con formulario guiado.",)),
                ("cargar", "cargar agente existente",
                 ("Conecta un cerebro que ya existe (una carpeta).",)),
                ("descubrir", "descubrir cerebros en el disco",
                 ("Escanea el disco buscando cerebros de agente.",))]
    return base + [_SIN_AGENTE]


# ── claridad del rediseño: foco · atajos · acción primaria ───────────────────
def _foco(K, sel):
    """P0-C: barra de acento `▐` en la 1ª columna de la fila ENFOCADA (esa
    celda ya era un espacio → coste CERO de ancho) + cursor `❯`. Las demás
    filas van en blanco. Devuelve (barra, cursor) ya coloreados."""
    if sel:
        return ("%s▐%s" % (K["C"] + K["BO"], K["R"]),
                "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]))
    return " ", " "


def _pares(view):
    """P0-A: ÚNICA fuente de atajos por paso. Parte la cadena de
    `onboarding.hints.<view>` (ES byte-idéntico, nada inventado) en pares
    (tecla, acción) — la cabecera (HL.screen_header) enseña los clave y el
    pie (HL.foot_hints) la lista completa; HL.keyline garantiza que caben."""
    hk = _HINT_KEYS.get(view)
    s = _t(hk, _HINTS.get(view, "")) if hk else _HINTS.get(view, "")
    out = []
    for seg in str(s).split(" · "):
        seg = seg.strip()
        if not seg:
            continue
        parts = seg.split(" ", 1)
        out.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return tuple(out)


def _accion_primaria(S, K, w):
    """P0-B: la LÍNEA DE ACCIÓN PRIMARIA — full-width, acento + glifo `▸`,
    distinta del pie, corta y brillante, según el FOCO. Es esencial: nunca se
    cede por altura."""
    v = S["view"]
    if v == "idioma":
        txt = _t("onboarding.action.idioma", "Enter elige el idioma")
    elif v == "bienvenida":
        txt = _t("onboarding.action.bienvenida", "Enter para empezar")
    elif v == "motores":
        txt = _t("onboarding.action.motores_opt",
                 "espacio marca · Enter continúa") \
            if S["mi"] < len(SOPORTADOS) else \
            _t("onboarding.action.continuar", "Enter continúa al siguiente paso")
    elif v == "apariencia":
        items = _items_apariencia(S)
        if S["ti"] < len(items):
            txt = _t("onboarding.action.apariencia_opt",
                     "Enter aplica «{lbl}»").format(lbl=items[S["ti"]][2])
        else:
            txt = _t("onboarding.action.continuar",
                     "Enter continúa al siguiente paso")
    elif v == "autostart":
        opts = _autostart_opts()
        txt = _t("onboarding.action.autostart",
                 "Enter elige «{lbl}» · Esc salta").format(
                     lbl=opts[S.get("asi", 1) % len(opts)][1])
    elif v == "agente":
        ops = _opciones_agente()
        tok, lbl, _d = ops[S["ai"] % len(ops)]
        txt = _t("onboarding.action.agente", "Enter abre «{lbl}»").format(
            lbl=_t("onboarding.agente.%s.label" % tok, lbl))
    elif v == "gcal":
        txt = _t("onboarding.action.gcal_done", "Enter te lleva al resumen") \
            if _gcal_configured() else \
            _t("onboarding.action.gcal", "Esc salta · Enter conecta")
    elif v == "resumen":
        txt = _t("onboarding.action.resumen", "Enter te deja en el recinto")
    else:
        txt = ""
    return HL.clip(" %s▸ %s%s" % (K["C"] + K["BO"], txt, K["R"]), w - 1)


# ── pasos nuevos (opcionales, no etapas): autostart · Google Calendar ─────────
def _autostart_opts():
    """Los dos radios del paso autostart (menos invasivo al final)."""
    return (("abrir", _t("onboarding.autostart.opt_on",
                         "al abrir la terminal")),
            ("comando", _t("onboarding.autostart.opt_off",
                           "solo con el comando workspace")))


def _b_autostart(S, K, iw, full=2):
    """Paso autostart: ¿la terminal abre Workspace sola, o solo con el
    comando? La caja der explica qué cambia y dónde. Saltable con Esc."""
    opts = _autostart_opts()
    cur_on = bool(_setting("ui.autostart", False))
    izq = []
    izq.append(_divisor(K, _t("onboarding.autostart.div", "arranque"), iw,
                        tono=2))
    izq += _parrafo(K, (_t("onboarding.autostart.heading",
                           "¿Cuándo abre Workspace?"),), iw, color=K["WH"])
    izq.append("")
    for i, (_tok, lbl) in enumerate(opts):
        sel = (i == S.get("asi", 1) % len(opts))
        activo = ((i == 0) == cur_on)
        bar, cur = _foco(K, sel)
        marca = ("%s●%s" % (K["C"], K["R"])) if activo else \
            ("%s○%s" % (K["GREY"], K["R"]))
        lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel
                          else (K["GREY"] if activo else K["DK"]), lbl, K["R"])
        izq.append(HL.clip("%s%s %s %s" % (bar, cur, marca, lab), iw))
        izq.append("")

    der = []
    foco = opts[S.get("asi", 1) % len(opts)][0]
    der.append(_divisor(K, _t("onboarding.div.que_cambia", "qué cambia"), iw,
                        tono=3))
    if foco == "abrir":
        der += _parrafo(K, (_t(
            "onboarding.autostart.on_p",
            "Cada terminal nueva abre el menú de Workspace: eliges un agente o "
            "sigues con una terminal normal (q). Cómodo para entrar directo al "
            "hub."),), iw)
    else:
        der += _parrafo(K, (_t(
            "onboarding.autostart.off_p",
            "La terminal arranca como siempre; escribes `workspace` cuando "
            "quieras el hub. Menos invasivo — ideal si compartes la máquina o "
            "corres scripts en ella."),), iw)
    if full >= 1:
        der.append("")
        der.append(_divisor(K, _t("onboarding.autostart.div_donde",
                                  "dónde queda"), iw))
        der += _parrafo(K, (_t(
            "onboarding.autostart.donde_p",
            "ui.autostart en settings.json + un bloque en ~/.zshrc (o tu "
            "$PROFILE de PowerShell). Cambiarlo luego: repite "
            "`workspace onboarding` o edita ese bloque."),), iw)
    return izq, der


def _gcal_configured():
    try:
        import gcal
        return bool(gcal.configured())
    except Exception:
        return False


def _gcal_accounts():
    try:
        import gcal
        return gcal.list_accounts()
    except Exception:
        return []


def _b_gcal(S, K, iw, full=2):
    """Paso Google Calendar (opcional): paso-a-paso para sacar la URL iCal.
    Conectar cae a un prompt CLÁSICO fuera del alt-screen (ver run()); la URL
    JAMÁS se imprime. Si ya hay cuenta: «conectado ✓»."""
    conf = _gcal_configured()
    izq = []
    izq.append(_divisor(K, _t("onboarding.gcal.div_pasos", "cómo"), iw,
                        tono=2))
    if conf:
        izq += _parrafo(K, (_t("onboarding.gcal.already",
                               "Ya tienes Google Calendar conectado ✓"),), iw,
                        color=K["OK"])
        for a in _gcal_accounts()[:3]:
            izq.append(HL.clip(" %s●%s %s%s%s" % (
                K["C"], K["R"], K["GREY"], a.get("label", ""), K["R"]), iw))
    else:
        pasos = (
            _t("onboarding.gcal.step1",
               "Abre Google Calendar en la web (calendar.google.com)."),
            _t("onboarding.gcal.step2",
               "En el calendario que quieras: Configuración y uso compartido."),
            _t("onboarding.gcal.step3", "Baja a «Integrar calendario»."),
            _t("onboarding.gcal.step4",
               "Copia la «Dirección secreta en formato iCal» (termina en "
               ".ics)."),
            _t("onboarding.gcal.step5",
               "Vuelve aquí y pulsa Enter: la pegas en una línea normal."))
        for n, txt in enumerate(pasos, 1):
            for i, sub in enumerate(_wrap(txt, max(8, iw - 5))):
                pre = (" %s%d%s " % (K["C"] + K["BO"], n, K["R"])) if i == 0 \
                    else "    "
                izq.append(HL.clip(pre + "%s%s%s" % (K["DIM"], sub, K["R"]),
                                   iw))

    der = []
    der.append(_divisor(K, _t("onboarding.div.que_cambia", "qué cambia"), iw,
                        tono=1))
    der += _parrafo(K, (_t(
        "onboarding.gcal.changes_p",
        "Workspace LEE tus eventos (solo lectura) y los muestra en el "
        "calendario del hub. Nunca escribe en tu agenda."),), iw)
    if full >= 1:
        der.append("")
        der.append(_divisor(K, _t("onboarding.gcal.div_seguro", "seguro"), iw))
        der += _parrafo(K, (_t(
            "onboarding.gcal.seguro_p",
            "Solo se guarda esa URL iCal, en tu máquina; jamás se imprime en "
            "pantalla. Puedes quitarla cuando quieras desde el calendario."),),
            iw)
    return izq, der


# ── render ──────────────────────────────────────────────────────────────────
def _fila_etapas(S, K, w):
    """`1 motores ── 2 apariencia ── 3 agente` — etapas REALES del proceso
    (hechas ✓ · actual encendida · pendientes tenues), no el cursor."""
    partes = []
    for n, et in enumerate(_ETAPAS):
        lbl = _t("onboarding.etapa.%s" % et, et)
        if et in S["hechos"]:
            partes.append("%s✓ %s%s" % (K["OK"], lbl, K["R"]))
        elif S["view"] == et:
            partes.append("%s%s %d %s%s" % (K["C"] + K["BO"], K["PTR"],
                                            n + 1, lbl, K["R"]))
        else:
            partes.append("%s%d %s%s" % (K["DK"], n + 1, lbl, K["R"]))
    fila = (" %s%s%s " % (K["DK"], K["SEP"] * 2, K["R"])).join(partes)
    pad = max(0, ((w - 1) - HL.vis(fila)) // 2)
    return HL.clip(" " * pad + fila, w - 1)


def _b_idioma(S, K, iw, full=2):
    """Paso 0: elegir el idioma de la interfaz del cliente. Las opciones se
    muestran con su nombre NATIVO (Español / English) sea cual sea el idioma
    activo; al elegir, set_lang persiste y el resto del flujo ya sale en ese
    idioma."""
    opts = i18n.available() if i18n else [("es", "Español"), ("en", "English")]
    izq = []
    izq.append(_divisor(K, _t("onboarding.idioma.divisor", "idioma"), iw,
                        tono=2))
    izq += _parrafo(K, (_t("onboarding.idioma.heading",
                           "Elige el idioma de Workspace."),), iw,
                    color=K["WH"])
    izq.append("")
    for i, (code, name) in enumerate(opts):
        sel = (i == S.get("li", 0))
        bar, cur = _foco(K, sel)
        marca = ("%s●%s" % (K["C"], K["R"])) if sel else \
            ("%s○%s" % (K["GREY"], K["R"]))
        lab = "%s%s%s  %s(%s)%s" % ((K["WH"] + K["BO"]) if sel else K["GREY"],
                                    name, K["R"], K["DK"], code, K["R"])
        izq.append(HL.clip("%s%s %s %s" % (bar, cur, marca, lab), iw))
    der = []
    if full >= 1:
        der.append(_divisor(K, "workspace", iw, tono=1))
        der += _parrafo(K, (_t("onboarding.idioma.body",
                              "Puedes cambiarlo cuando quieras desde el menú "
                              "del recinto («Idioma») o en Config."),), iw)
    return izq, der


def _b_bienvenida(S, K, iw, full=2):
    izq = _parrafo(K, (
        _t("onboarding.welcome.p1",
           "Workspace es un hub local para tus agentes de IA: cada agente vive "
           "en su propio cerebro (una carpeta de archivos tuya) y corre sobre "
           "un motor CLI que ya tengas instalado — Claude Code, Codex o "
           "Antigravity."),
        _t("onboarding.welcome.p2",
           "Todo pasa en tu máquina: cero dependencias, sin cuentas nuevas, y "
           "Workspace nunca ve ni guarda tus credenciales (el login es de cada "
           "CLI).")), iw)
    der = []
    der.append(_divisor(K, _t("onboarding.welcome.plan_title",
                              "qué viene ahora"), iw, tono=2))
    pasos = (
        (_t("onboarding.welcome.step1_t", "1 motores"),
         _t("onboarding.welcome.step1_d",
            "detecto qué CLIs tienes y eliges cuáles usar")),
        (_t("onboarding.welcome.step2_t", "2 apariencia"),
         _t("onboarding.welcome.step2_d",
            "tema y fondo del hub — se ven al instante")),
        (_t("onboarding.welcome.step3_t", "3 agente"),
         _t("onboarding.welcome.step3_d",
            "crear uno nuevo, cargar uno existente o buscar "
            "en tu disco (y afinar su tono)")))
    for tit, txt in pasos:
        der.append(HL.clip(" %s%s%s" % (K["WH"] + K["BO"], tit, K["R"]), iw))
        for sub in _wrap(txt, max(8, iw - 4)):
            der.append(HL.clip("    %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    if full >= 1:
        der.append("")
        der.append(_divisor(K, _t("onboarding.welcome.transparency_title",
                                  "transparencia"), iw))
        der += _parrafo(K, (
            _t("onboarding.welcome.transparency_p",
               "Al final: un resumen de lo elegido y dónde quedó guardado. "
               "Puedes saltarte esto con q y repetirlo cuando quieras con "
               "`workspace onboarding`."),), iw, bullet=False)
    return izq, der


def _b_motores(S, K, iw, full=2):
    izq = []
    for i, eid in enumerate(SOPORTADOS):
        sel = (i == S["mi"])
        txt, col, elegible = _estado_motor(K, S, eid)
        usa = eid in S["sel"]
        bar, cur = _foco(K, sel)
        marca = ("%s●%s" % (K["C"], K["R"])) if usa else \
            ("%s○%s" % ((K["GREY"] if elegible else K["DK"]), K["R"]))
        lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel
                          else (K["GREY"] if elegible else K["DK"]),
                          eid, K["R"])
        izq.append(HL.clip("%s%s %s %s" % (bar, cur, marca, lab), iw))
        # el ESTADO en su propia línea: completo, jamás truncado
        for sub in _wrap(txt, max(8, iw - 6)):
            izq.append(HL.clip("      %s%s%s" % (col, sub, K["R"]), iw))
        izq.append("")
    izq.append(_divisor(K, _t("onboarding.motores.div_listo", "listo"), iw))
    selc = (S["mi"] == len(SOPORTADOS))
    bar, cur = _foco(K, selc)
    _cont = _t("onboarding.continuar", "✦ continuar")
    _mk = _t("onboarding.motores.marcados",
             "{n} motor(es) marcados").format(n=len(S["sel"]))
    izq.append(HL.clip("%s%s %s%s%s   %s%s%s"
                       % (bar, cur, (K["C"] + K["BO"]) if selc else K["GREY"],
                          _cont, K["R"], K["DK"], _mk, K["R"]), iw))

    der = []
    if S["mi"] < len(SOPORTADOS):
        eid = SOPORTADOS[S["mi"]]
        info = _motor_info(eid)
        der.append(_divisor(K, _t("onboarding.div.tu_eleccion", "tu elección"),
                            iw, tono=1))
        der += _parrafo(K, (info[0],), iw, color=K["WH"])
        txt, col, _e = _estado_motor(K, S, eid)
        der.append(HL.clip(" %s%s: %s%s%s" % (
            K["DK"], _t("onboarding.motores.estado", "estado"), col, txt,
            K["R"]), iw))
        if full >= 1:
            der.append("")
            der.append(_divisor(K, _t("onboarding.div.que_cambia",
                                      "qué cambia"), iw, tono=3))
            der += _parrafo(K, (info[2], info[1]), iw)
    else:
        der.append(_divisor(K, _t("onboarding.div.que_cambia", "qué cambia"),
                            iw, tono=3))
        if S["sel"]:
            primero = next(e for e in SOPORTADOS if e in S["sel"])
            der += _parrafo(K, (_t(
                "onboarding.motores.default_p",
                "Los motores marcados son tu set de trabajo. «{motor}» queda "
                "como default (modelos.default_engine) para los agentes que no "
                "declaren el suyo — cada agente puede fijar otro después."
            ).format(motor=primero),), iw)
        else:
            der += _parrafo(K, (_t(
                "onboarding.motores.none_p",
                "Sin ningún motor marcado no se puede lanzar agentes. Puedes "
                "continuar igual, instalar un CLI después y repetir esto con "
                "`workspace onboarding`."),), iw, color=K["B"])
    if full >= 2:
        der.append("")
        der.append(_divisor(K, _t("onboarding.motores.div_honesto", "honesto"),
                            iw))
        der += _parrafo(K, (_t(
            "onboarding.motores.honesto_p",
            "El estado de sesión se lee del propio CLI de cada motor; "
            "Workspace no guarda ni ve credenciales."),), iw)
    return izq, der


def _items_apariencia(S):
    """[(tipo, id, label)] navegables + la fila continuar al final."""
    out = [("tema", tid, lbl) for tid, lbl in S["temas"]]
    out += [("fondo", fid, _t("onboarding.fondo.%s" % fid, lbl))
            for fid, lbl in _FONDOS]
    return out


def _b_apariencia(S, K, iw, full=2):
    items = _items_apariencia(S)
    tema_act = str(_setting("ui.theme", "rose"))
    fondo_act = str(_setting("ui.background", "tema"))
    izq, grupo = [], None
    for i, (tipo, iid, lbl) in enumerate(items):
        if tipo != grupo:
            if grupo is not None:
                izq.append("")
            izq.append(_divisor(K, _t("onboarding.apariencia.group.%s" % tipo,
                                      tipo), iw))
            grupo = tipo
        sel = (i == S["ti"])
        act = (iid == (tema_act if tipo == "tema" else fondo_act))
        bar, cur = _foco(K, sel)
        marca = ("%s●%s" % (K["C"], K["R"])) if act else \
            ("%s·%s" % (K["DK"], K["R"]))
        lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel
                          else (K["GREY"] if act else K["DIM"]),
                          HL.pad(lbl, 18), K["R"])
        extra = ("%s%s%s" % (K["OK"],
                             _t("onboarding.apariencia.activo", "activo"),
                             K["R"])) if act else ""
        izq.append(HL.clip("%s%s %s %s %s" % (bar, cur, marca, lab, extra), iw))
    izq.append("")
    selc = (S["ti"] == len(items))
    bar, cur = _foco(K, selc)
    izq.append(HL.clip("%s%s %s%s%s" % (
        bar, cur, (K["C"] + K["BO"]) if selc else K["GREY"],
        _t("onboarding.continuar", "✦ continuar"), K["R"]), iw))

    der = []
    der.append(_divisor(K, _t("onboarding.div.tu_eleccion", "tu elección"),
                        iw, tono=1))
    der.append(HL.clip(" %s%s%s  %s%s%s" % (
        K["DK"], _t("onboarding.apariencia.group.tema", "tema"), K["R"],
        K["WH"] + K["BO"], tema_act, K["R"]), iw))
    der.append(HL.clip(" %s%s%s %s%s%s" % (
        K["DK"], _t("onboarding.apariencia.group.fondo", "fondo"), K["R"],
        K["WH"] + K["BO"], fondo_act, K["R"]), iw))
    if full >= 1:
        der.append("")
        der.append(_divisor(K, _t("onboarding.div.que_cambia", "qué cambia"),
                            iw, tono=3))
        der += _parrafo(K, (
            _t("onboarding.apariencia.changes_p1",
               "El tema pinta todo el hub — wordmark, cajas, sliders — y se "
               "guarda al instante: esta pantalla YA está pintada con él; eso "
               "es la vista previa."),
            _t("onboarding.apariencia.changes_p2",
               "El fondo es un eje independiente: cambia solo el color de "
               "fondo de la terminal y combina con cualquier tema."),), iw)
    if full >= 2:
        der.append("")
        der.append(_divisor(K, _t("onboarding.apariencia.div_donde",
                                  "dónde queda"), iw))
        der += _parrafo(K, (_t(
            "onboarding.apariencia.donde_p",
            "ui.theme y ui.background en ~/.claude/workspace/settings.json. "
            "Más opciones (color propio #RRGGBB, animaciones, estrellas) en "
            "Config → TEMA."),), iw)
    return izq, der


def _b_agente(S, K, iw, full=2):
    ops = _opciones_agente()
    izq = []
    for i, (tok, lbl, _desc) in enumerate(ops):
        sel = (i == S["ai"])
        bar, cur = _foco(K, sel)
        lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel else K["GREY"],
                          _t("onboarding.agente.%s.label" % tok, lbl), K["R"])
        izq.append(HL.clip("%s%s %s%d%s  %s" % (bar, cur, K["DK"], i + 1,
                                                K["R"], lab), iw))
        izq.append("")
    der = []
    tok, lbl, desc = ops[S["ai"] % len(ops)]
    der.append(_divisor(K, _t("onboarding.div.tu_eleccion", "tu elección"),
                        iw, tono=1))
    der += _parrafo(K, (_t("onboarding.agente.%s.label" % tok, lbl),), iw,
                    color=K["WH"] + K["BO"])
    if full >= 1:
        der.append("")
        der.append(_divisor(K, _t("onboarding.agente.div_que_pasa", "qué pasa"),
                            iw, tono=3))
        der += _parrafo(K, tuple(
            _t("onboarding.agente.%s.desc" % tok, d) for d in desc), iw)
    if full >= 2 and tok != "ninguno":
        der.append("")
        der.append(_divisor(K, _t("onboarding.agente.div_siguiente",
                                  "siguiente paso"), iw))
        der += _parrafo(K, (_t(
            "onboarding.agente.siguiente_p",
            "Se abre la pantalla real del hub («Agregar agente») en ese "
            "camino. Si queda un agente nuevo conectado, al volver podrás "
            "afinar su TONO; después, el resumen."),), iw)
    return izq, der


def _b_resumen(S, K, iw, full=2):
    izq = []
    izq.append(_divisor(K, _t("onboarding.resumen.div_motores", "motores"),
                        iw, tono=1))
    if S["sel"]:
        for eid in (e for e in SOPORTADOS if e in S["sel"]):
            txt, col = _estado_corto(K, S, eid)
            izq.append(HL.clip(" %s●%s %s  %s%s%s" % (
                K["C"], K["R"], HL.pad(eid, 12), col, txt, K["R"]), iw))
        izq.append(HL.clip(" %s%s%s" % (
            K["DK"], _t("onboarding.resumen.default", "default: {engine}")
            .format(engine=S.get("def_engine") or _t(
                "onboarding.resumen.sin_cambio", "sin cambio")), K["R"]), iw))
    else:
        izq.append(HL.clip(" %s%s%s" % (K["DIM"], _t(
            "onboarding.resumen.ninguno_marcado",
            "ninguno marcado — instala un CLI y repite con "
            "`workspace onboarding`"), K["R"]), iw))
    izq.append("")
    izq.append(_divisor(K, _t("onboarding.resumen.div_apariencia",
                              "apariencia"), iw, tono=2))
    izq.append(HL.clip(" %s %s%s%s · %s %s%s%s" % (
        _t("onboarding.apariencia.group.tema", "tema"),
        K["WH"] + K["BO"], _setting("ui.theme", "rose"), K["R"],
        _t("onboarding.apariencia.group.fondo", "fondo"),
        K["WH"] + K["BO"], _setting("ui.background", "tema"), K["R"]), iw))
    izq.append("")
    izq.append(_divisor(K, _t("onboarding.resumen.div_agentes", "agentes"),
                        iw, tono=3))
    ags = _agentes()
    if ags:
        for a in ags[:4]:
            nuevo = a["name"] in S["nuevos"]
            izq.append(HL.clip(" %s%s%s  %s%s%s" % (
                K["WH"] + K["BO"] if nuevo else K["GREY"], a["name"], K["R"],
                K["DK"], a.get("brain", ""), K["R"]), iw))
        if len(ags) > 4:
            izq.append(HL.clip(" %s%s%s" % (K["DK"], _t(
                "onboarding.resumen.y_mas", "… y {n} más").format(
                    n=len(ags) - 4), K["R"]), iw))
    else:
        izq.append(HL.clip(" %s%s%s" % (K["DIM"], _t(
            "onboarding.resumen.sin_agentes",
            "sin agentes aún — «Agregar agente» en el recinto cuando quieras"),
            K["R"]), iw))
    if S.get("tono"):
        izq.append(HL.clip(" %s%s%s" % (K["OK"], _t(
            "onboarding.resumen.tono_ok", "tono ajustado para {agente} ✓")
            .format(agente=S["tono"]), K["R"]), iw))

    der = []
    der.append(_divisor(K, _t("onboarding.resumen.div_donde", "dónde quedó"),
                        iw, tono=4))
    try:
        import settings as _st
        sp = _st.store_path()
    except Exception:
        sp = "~/.claude/workspace/settings.json"
    try:
        import agentsreg as _ar
        ap = _ar.local_path()
    except Exception:
        ap = "~/.claude/workspace/agents.local.json"
    filas = ((_t("onboarding.resumen.fila_config",
                 "config (tema, fondo, motor)"), sp),
             (_t("onboarding.resumen.fila_agentes", "agentes registrados"),
              ap),
             (_t("onboarding.resumen.fila_onboarding", "este onboarding"),
              flag_path()))
    for lbl, ruta in filas:
        der.append(HL.clip(" %s%s%s" % (K["GREY"], lbl, K["R"]), iw))
        der.append(HL.clip("   %s%s%s" % (K["DK"], ruta, K["R"]), iw))
    if full >= 1:
        der.append("")
        der.append(_divisor(K, _t("onboarding.resumen.div_adelante",
                                  "de aquí en adelante"), iw))
        der += _parrafo(K, (
            _t("onboarding.resumen.adelante_p1",
               "Enter te deja en el recinto: ahí lanzas agentes, entras a "
               "Config, Tono y «Agregar agente»."),
            _t("onboarding.resumen.adelante_p2",
               "Repetir este flujo: `workspace onboarding`."),), iw)
    return izq, der


_VISTAS = {"idioma": (_b_idioma, "IDIOMA · LANGUAGE", "WORKSPACE"),
           "bienvenida": (_b_bienvenida, "QUÉ ES WORKSPACE", "EL PLAN"),
           "motores": (_b_motores, "MOTORES DETECTADOS", "EL MOTOR"),
           "apariencia": (_b_apariencia, "TEMA Y FONDO", "LA APARIENCIA"),
           "autostart": (_b_autostart, "ARRANQUE", "CÓMO ABRE"),
           "agente": (_b_agente, "TU PRIMER AGENTE", "EL CAMINO"),
           "gcal": (_b_gcal, "GOOGLE CALENDAR", "OPCIONAL"),
           "resumen": (_b_resumen, "LO QUE QUEDÓ", "DÓNDE Y QUÉ SIGUE")}

#: Claves i18n del TÍTULO de cada caja, por vista (izq, der). Solo las vistas
#: ya traducidas aparecen aquí; las demás usan el literal de _VISTAS (español,
#: paridad). Las fases 1+ agregan su vista = una línea aquí. `idioma` no entra:
#: su título es bilingüe fijo (el idioma aún no se elige).
_TITLE_KEYS = {
    "bienvenida": ("onboarding.welcome.title_l", "onboarding.welcome.title_r"),
    "motores": ("onboarding.motores.title_l", "onboarding.motores.title_r"),
    "apariencia": ("onboarding.apariencia.title_l",
                   "onboarding.apariencia.title_r"),
    "autostart": ("onboarding.autostart.title_l",
                  "onboarding.autostart.title_r"),
    "agente": ("onboarding.agente.title_l", "onboarding.agente.title_r"),
    "gcal": ("onboarding.gcal.title_l", "onboarding.gcal.title_r"),
    "resumen": ("onboarding.resumen.title_l", "onboarding.resumen.title_r"),
}

#: Claves i18n del HINT del pie, por vista. Mismo criterio que _TITLE_KEYS.
_HINT_KEYS = {
    "idioma": "onboarding.hints.idioma",
    "bienvenida": "onboarding.hints.welcome",
    "motores": "onboarding.hints.motores",
    "apariencia": "onboarding.hints.apariencia",
    "autostart": "onboarding.hints.autostart",
    "agente": "onboarding.hints.agente",
    "gcal": "onboarding.hints.gcal",
    "resumen": "onboarding.hints.resumen",
}

_HINTS = {
    "idioma": "↑↓ idioma · Enter elige · Esc/q salta",
    "bienvenida": "Enter empieza · q al hub (vuelve con `workspace onboarding`)",
    "motores": "↑↓ motor · espacio marca/quita · Enter continúa · Esc atrás · q salta",
    "apariencia": "↑↓ opción · Enter/espacio aplica (guarda ya) · Esc atrás · q salta",
    "autostart": "↑↓ opción · Enter elige · Esc salta · q sale",
    "agente": "↑↓ camino · 1-4 directo · Enter abre · Esc atrás · q salta",
    "gcal": "Enter conecta · Esc salta · q sale",
    "resumen": "Enter — al recinto",
}


def render(S, w, h):
    K = _K()
    pares = _pares(S["view"])                    # P0-A: una sola fuente de atajos
    sub = _t("onboarding.subtitle",
             "primer arranque — deja tu Workspace listo en 3 pasos")
    # cabecera COMPARTIDA (wordmark + reflejo + subtítulo + atajos arriba + regla)
    L = HL.screen_header(K, w, h, sub, hints=pares)
    L.append(_fila_etapas(S, K, w))
    L.append("")
    top = len(L)
    builder, t_izq, t_der = _VISTAS[S["view"]]
    tk = _TITLE_KEYS.get(S["view"])              # título traducido (fallback: literal)
    if tk:
        t_izq = _t(tk[0], t_izq)
        t_der = _t(tk[1], t_der)
    apilado = w < 100
    lw = (w - 1) if apilado else max(36, min(46, (w - 6) * 46 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    # -4 (no -3): además del blanco+msg+pie, la fila de ACCIÓN PRIMARIA (P0-B)
    # es esencial y suma una línea — si no se cuenta, el pie se sale.
    avail = max(8, (h - 1) - top - 4)
    bi = bd = None
    for full in (2, 1, 0):                       # degradación honesta
        if apilado:                              # cada caja a su ancho real
            bi = builder(S, K, w - 6, full)[0]
            bd = builder(S, K, w - 6, full)[1]
            need = len(bi) + len(bd) + 4
        else:
            bi = builder(S, K, lw - 4, full)[0]
            bd = builder(S, K, rw - 4, full)[1]
            need = max(len(bi), len(bd)) + 2
        if need <= avail:
            break
    if apilado:
        ih_d = max(3, min(len(bd), avail - (len(bi) + 2) - 2))
        for ln in HL.full_box(t_izq, bi, K, w - 2, len(bi), True,
                              border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
        for ln in HL.full_box(t_der, bd, K, w - 2, ih_d, False,
                              border=K["B2"], label=K["B"] + K["BO"]):
            L.append(HL.clip(" " + ln, w - 1))
    else:
        ch = min(avail, max(len(bi), len(bd)) + 2)
        izq = HL.full_box(t_izq, bi, K, lw, ch - 2, True, border=K["C"])
        der = HL.full_box(t_der, bd, K, rw, ch - 2, False, border=K["B2"],
                          label=K["B"] + K["BO"])
        for i in range(ch):
            L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "", lw)
                             + "  " + (der[i] if i < len(der) else ""),
                             w - 1))
    L.append("")
    L.append(_accion_primaria(S, K, w))          # P0-B: acción primaria (esencial)
    L.append((" %s%s%s" % (K["B2"], S["msg"], K["R"])) if S.get("msg")
             else "")
    L.append(HL.foot_hints(K, pares, w))         # P0-A: pie de atajos completo
    L = [HL.clip(x, w - 1) for x in L[:h - 1]]
    return L + [""] * max(0, (h - 1) - len(L))    # altura SIEMPRE estable


# ── acciones ────────────────────────────────────────────────────────────────
def _persistir_motores(S):
    """Al continuar del paso motores: el primero marcado queda como default
    del harness (modelos.default_engine). Sin marca → sin escribir."""
    if not S["sel"]:
        return
    primero = next((e for e in SOPORTADOS if e in S["sel"]), None)
    if not primero:
        return
    ok, err = _guardar("modelos.default_engine", primero)
    if ok:
        S["def_engine"] = primero
        S["msg"] = _t("onboarding.msg.default_saved",
                      "motor default: {motor} · guardado ✓").format(
                          motor=primero)
    else:
        S["msg"] = _t("onboarding.msg.default_fail",
                      "no pude guardar el default ({err}) — sigue igual"
                      ).format(err=err)


def _accion(S, key):
    """True = sigue · False = cierra el driver (S['salir'] dice por qué)."""
    v = S["view"]
    S["msg"] = ""
    if key == "\x03":
        S["salir"] = "quit"
        return False
    if key in ("q", "Q") and v != "resumen":
        S["salir"] = "quit"
        return False

    if v == "idioma":
        opts = i18n.available() if i18n else [("es", "Español"),
                                              ("en", "English")]
        n = len(opts)
        if key == "up":
            S["li"] = (S.get("li", 0) - 1) % n
        elif key in ("down", "tab"):
            S["li"] = (S.get("li", 0) + 1) % n
        elif key == "\x1b":                      # Esc en el paso 0 = salta
            S["salir"] = "quit"
            return False
        elif key in tuple("12")[:n]:
            S["li"] = int(key) - 1
            key = "\r"                            # cae a elegir
        if key in ("\r", "\n"):
            code = opts[S.get("li", 0)][0]
            if i18n:
                try:
                    i18n.set_lang(code)           # persiste ui.lang + invalida cache
                except Exception:
                    pass
            S["view"] = "bienvenida"              # el resto ya sale en ese idioma
        return True

    if v == "bienvenida":
        if key in ("\r", "\n"):
            S["view"] = "motores"
        elif key == "\x1b":                      # Esc = atrás al paso 0 (idioma)
            S["view"] = "idioma"
        return True

    if v == "motores":
        n = len(SOPORTADOS)
        if key == "up":
            S["mi"] = (S["mi"] - 1) % (n + 1)
        elif key in ("down", "tab"):
            S["mi"] = (S["mi"] + 1) % (n + 1)
        elif key == "\x1b":
            S["view"] = "bienvenida"
        elif key in tuple("123"):
            S["mi"] = int(key) - 1
            key = " "                            # cae al toggle
        if key in (" ",) and S["mi"] < n:
            eid = SOPORTADOS[S["mi"]]
            _txt, _c, elegible = _estado_motor(_K(), S, eid)
            if not elegible:
                S["msg"] = _t("onboarding.msg.not_installable",
                              "{eid} no está instalado — no se puede marcar"
                              ).format(eid=eid)
            elif eid in S["sel"]:
                S["sel"].discard(eid)
            else:
                S["sel"].add(eid)
        elif key in ("\r", "\n"):
            if S["mi"] < n:                      # Enter sobre un motor = toggle
                return _accion(S, " ")
            _persistir_motores(S)
            S["hechos"].add("motores")
            S["view"] = "apariencia"
        return True

    if v == "apariencia":
        items = _items_apariencia(S)
        n = len(items)
        if key == "up":
            S["ti"] = (S["ti"] - 1) % (n + 1)
        elif key in ("down", "tab"):
            S["ti"] = (S["ti"] + 1) % (n + 1)
        elif key == "\x1b":
            S["view"] = "motores"
        elif key in ("\r", "\n", " "):
            if S["ti"] >= n:
                if key == " ":
                    return True
                S["hechos"].add("apariencia")
                S["view"] = "autostart"          # paso nuevo (opcional)
                return True
            tipo, iid, lbl = items[S["ti"]]
            skey = "ui.theme" if tipo == "tema" else "ui.background"
            ok, err = _guardar(skey, iid)
            _tipo = _t("onboarding.apariencia.group.%s" % tipo, tipo)
            if ok:
                _aplicar_osc()                   # preview real, al instante
                S["msg"] = _t("onboarding.msg.applied",
                              "{tipo} «{lbl}» · guardado ✓").format(
                                  tipo=_tipo, lbl=lbl)
            else:
                S["msg"] = _t("onboarding.msg.apply_fail",
                              "no se pudo aplicar {tipo} ({err})").format(
                                  tipo=_tipo, err=err)
        return True

    if v == "autostart":                         # paso NUEVO (opcional)
        opts = _autostart_opts()
        n = len(opts)
        if key == "up":
            S["asi"] = (S.get("asi", 1) - 1) % n
        elif key in ("down", "tab"):
            S["asi"] = (S.get("asi", 1) + 1) % n
        elif key == "\x1b":                       # Esc = salta (al agente)
            S["view"] = "agente"
        elif key in ("\r", "\n"):
            on = (S.get("asi", 1) % n == 0)       # opción 0 = al abrir terminal
            _aplicar_autostart(S, on)
            S["view"] = "agente"
        return True

    if v == "agente":
        ops = _opciones_agente()
        if key == "up":
            S["ai"] = (S["ai"] - 1) % len(ops)
        elif key in ("down", "tab"):
            S["ai"] = (S["ai"] + 1) % len(ops)
        elif key == "\x1b":                       # atrás: salta el opcional
            S["view"] = "apariencia"
        elif key in tuple("1234"):
            S["ai"] = min(int(key) - 1, len(ops) - 1)
        elif key in ("\r", "\n"):
            S["salir"] = ops[S["ai"]][0]         # crear/cargar/descubrir/ninguno
            return False
        return True

    if v == "gcal":                              # paso NUEVO (opcional)
        if key == "\x1b":                         # Esc = salta → resumen
            S["view"] = "resumen"
        elif key in ("\r", "\n"):
            if _gcal_configured():                # ya conectado → al resumen
                S["view"] = "resumen"
            else:                                 # prompt CLÁSICO fuera del alt
                S["salir"] = "gcal_connect"
                return False
        return True

    if v == "resumen":
        if key in ("\r", "\n", "q", "Q", "\x1b"):
            S["salir"] = "fin"
            return False
        return True
    return True


def _aplicar_autostart(S, on):
    """Persiste ui.autostart y reescribe el bloque del greeter en el rc
    (install.set_terminal_autostart). Degrada a solo-preferencia si no se
    puede reescribir limpio (y lo dice)."""
    _guardar("ui.autostart", bool(on))
    rc = None
    try:
        import install
        fn = getattr(install, "set_terminal_autostart", None)
        if fn:
            rc = fn(bool(on))
    except Exception:
        rc = None
    if rc:
        S["msg"] = (_t("onboarding.msg.autostart_on",
                       "Workspace abrirá al abrir la terminal · guardado ✓")
                    if on else
                    _t("onboarding.msg.autostart_off",
                       "Workspace abrirá solo con el comando · guardado ✓"))
    else:
        S["msg"] = _t("onboarding.msg.autostart_saved",
                      "preferencia guardada (ajusta el rc a mano si hace falta)")


# ── drivers (mismo patrón que tono_tui; cadencia viva mientras hay probe) ──
import responsive_ui as _responsive                             # noqa: E402
render = _responsive.renderer(render, "ONBOARDING")
_accion = _responsive.action(_accion)


def _draw(tout, S, first=False):
    w, h = _size()
    try:
        _responsive.paint(tout, render(S, w, h), first=first)
    except Exception:
        pass


def _pantalla_unix(S):
    import select
    import termios
    import tty
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        tout = open("/dev/tty", "w")
    except Exception:
        S["salir"] = "quit"
        return
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h\033[?25l")
        _draw(tout, S, first=True)
        while True:
            busy = bool(S.get("probing"))
            if not select.select([fd], [], [], 0.12 if busy else 0.5)[0]:
                _draw(tout, S)
                continue
            ch = os.read(fd, 1).decode("utf-8", "replace")
            key = ch
            if ch == "\x1b":
                if select.select([fd], [], [], 0.05)[0]:
                    seq = os.read(fd, 2).decode("utf-8", "replace")
                    key = {"[A": "up", "[B": "down", "[C": "right",
                           "[D": "left", "[Z": "up"}.get(seq, "\x1b")
            elif ch == "\t":
                key = "tab"
            if not _accion(S, key):
                break
            _draw(tout, S)
    finally:
        try:
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.close(fd)
        except Exception:
            pass


def _pantalla_windows(S):
    import msvcrt
    tout = sys.stdout
    tout.write("\033[?1049h\033[?25l")
    try:
        _draw(tout, S, first=True)
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
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
        except Exception:
            pass


def _pantalla(S):
    """Corre el driver hasta que la vista pida salir. Devuelve el token."""
    S["salir"] = None
    try:
        if os.name == "nt":
            _pantalla_windows(S)
        else:
            _pantalla_unix(S)
    except Exception:
        S["salir"] = S.get("salir") or "quit"
    return S.get("salir") or "quit"


# ── reuso de los flujos existentes (add_agent · tono) ───────────────────────
def _add_agent(opcion):
    """La pantalla REAL «Agregar agente», pre-sembrada en el camino elegido
    (1 crear · 2 cargar · 3 descubrir) — mismo estado, mismos drivers."""
    try:
        import add_agent_tui as A
        S = A._estado_inicial()
        if S.get("view") == "menu":              # sin creación viva re-enganchada
            A._accion(S, {"crear": "1", "cargar": "2",
                          "descubrir": "3"}.get(opcion, "1"))
        if os.name == "nt":
            return A._run_windows(S)
        return A._run_unix(S)
    except Exception:
        try:
            import add_agent_tui
            return add_agent_tui.run()           # el flujo entero, sin sembrar
        except Exception:
            return 0


def _tono_para(agente):
    """La pantalla REAL del Tono, pre-sembrada en el agente recién nacido."""
    try:
        import tono_tui as T
        S = {"dests": T._destinos(), "di": 0, "si": 0, "msg": "",
             "preset": ""}
        if agente in S["dests"]:
            S["di"] = S["dests"].index(agente)
        if os.name == "nt":
            return T._run_windows(S)
        return T._run_unix(S)
    except Exception:
        try:
            import tono_tui
            return tono_tui.run()
        except Exception:
            return 0


def _gcal_connect_clasico(S):
    """Prompt CLÁSICO fuera del alt-screen (raw mode no deja pegar una URL
    larga de forma fiable): pide la «Dirección secreta iCal», la vincula con
    gcal.add_account y deja el resultado en S["msg"]. NUNCA imprime la URL."""
    try:
        import gcal
    except Exception:
        S["msg"] = _t("onboarding.gcal.unavailable",
                      "Google Calendar no está disponible aquí")
        return
    try:
        print()
        print(_t("onboarding.gcal.prompt_url",
                 "Pega la «Dirección secreta en formato iCal» "
                 "(Enter vacío = cancelar):"))
        url = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not url:
        S["msg"] = _t("onboarding.gcal.cancelled", "conexión cancelada")
        return
    try:
        label = input("  %s" % _t("onboarding.gcal.prompt_label",
                                  "Etiqueta (opcional, Enter = auto): ")
                      ).strip()
    except (EOFError, KeyboardInterrupt):
        label = ""
    try:
        res = gcal.add_account(label, url)
    except Exception as e:
        res = {"ok": False, "error": str(e)}
    if res.get("ok"):
        S["msg"] = _t("onboarding.gcal.connected",
                      "conectado ✓ · {n} eventos").format(
                          n=res.get("events", 0))
    else:
        S["msg"] = _t("onboarding.gcal.failed",
                      "no se pudo conectar ({err})").format(
                          err=res.get("error", ""))


# ── entrada ─────────────────────────────────────────────────────────────────
def _estado_inicial():
    harn = _descriptores()
    sel = {e for e in SOPORTADOS if (harn.get(e) or {}).get("binaries_ok")}
    return {"view": "idioma", "li": 0, "mi": 0, "ti": 0, "ai": 0,
            "asi": 0 if bool(_setting("ui.autostart", False)) else 1,
            "msg": "", "harn": harn, "probe": {}, "probing": False, "sel": sel,
            "temas": _temas(), "hechos": set(), "nuevos": [], "tono": "",
            "def_engine": "", "salir": None}


def _resumen_flag(S, completo):
    return {"modo": "onboarding", "completo": bool(completo),
            "motores": sorted(S["sel"]),
            "default_engine": S.get("def_engine") or "",
            "tema": str(_setting("ui.theme", "")),
            "fondo": str(_setting("ui.background", "")),
            "agentes": [a["name"] for a in _agentes()],
            "tono": S.get("tono") or None}


def run(force=False):
    """El flujo completo. force=True lo corre aunque ya haya corrido
    (`workspace onboarding`). Sin TTY: señala el camino y no truena."""
    if not force and ya_corrio():
        print("el onboarding ya corrió aquí — repetir: workspace onboarding")
        return 0
    try:
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactivo = False
    if not interactivo:
        print("el onboarding necesita una terminal interactiva.")
        print("abre `workspace` en una terminal y corre: workspace onboarding")
        return 0
    _marcar({"modo": "onboarding", "completo": False})   # jamás re-molestar
    S = _estado_inicial()
    _probe_start(S)
    try:
        while True:
            token = _pantalla(S)
            if token == "quit":
                _marcar(_resumen_flag(S, False))
                break
            if token == "fin":
                _marcar(_resumen_flag(S, True))
                break
            if token in ("crear", "cargar", "descubrir", "ninguno"):
                if token != "ninguno":
                    antes = {a["name"] for a in _agentes()}
                    _add_agent(token)
                    nuevos = sorted({a["name"] for a in _agentes()} - antes)
                    S["nuevos"] += nuevos
                    if nuevos:                   # nació/conectó uno → su TONO
                        _tono_para(nuevos[0])
                        S["tono"] = nuevos[0]
                S["hechos"].add("agente")
                S["view"], S["salir"] = "gcal", None   # paso opcional antes del resumen
                continue
            if token == "gcal_connect":           # prompt clásico fuera del alt-screen
                _gcal_connect_clasico(S)
                S["view"], S["salir"] = "gcal", None
                continue
            break                                 # token desconocido → fuera
    finally:
        _marcar(_resumen_flag(S, S.get("salir") == "fin"))
        _aplicar_osc()                            # el hub entra ya pintado
    return 0


def maybe_run():
    """Trigger de front.py: corre el onboarding SOLO en el primer uso real.
    Devuelve True si corrió (front re-lanza el hub con lo elegido).
    Guardas: subcomando/--banner · sin TTY · env WORKSPACE_NO_ONBOARDING ·
    flag presente · máquina con agentes (se adopta en silencio)."""
    try:
        if os.environ.get("WORKSPACE_NO_ONBOARDING"):
            return False
        if len(sys.argv) > 1:                     # subcomando o --banner
            return False
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
        if ya_corrio():
            return False
        if _agentes():                            # máquina ya operando
            _marcar({"modo": "adopcion", "completo": True})
            return False
        run(force=True)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(run(force="--force" in sys.argv or "-f" in sys.argv
                 or len(sys.argv) == 1))
