#!/usr/bin/env python3
"""WORKSPACE · onboarding_tui — el PRIMER ARRANQUE guiado (repo público).

La primera vez que alguien baja Workspace y lo abre, no hay config, no hay
agentes y no sabe qué es esto. Este flujo lo recibe al estilo WORKSPACE
(wordmark, cajas del tema, transparencia total) y lo deja operativo en
3 etapas (las de `_ETAPAS`) más pasos opcionales y un resumen honesto:

  idioma → bienvenida → 1 MOTORES → 2 APARIENCIA → (arranque) → 3 AGENTE
         → (tono) → (google calendar) → resumen

(idioma, arranque y google calendar son pasos opcionales, no etapas; ver _VISTAS.)

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

REANUDABLE (U07/Z07): el flag guarda el estado por ETAPA (completa/omitida/
pendiente) y la vista donde quedó; `workspace onboarding` CONTINÚA desde ahí
(no reinicia). «Listo» (completo=True) exige lo VERIFICABLE: un motor con
binario y un agente lanzable (agent_state). Omitir es válido (modo explorar):
queda `pendientes` en el flag — sin bucle forzado ni aviso en el hub (era
una foto de la salida que no se re-verificaba y mentía; quitado 2026-10-14).
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
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import hublayout as HL                                          # noqa: E402
import section_box as SB                                         # noqa: E402
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
#: (pide un #RRGGBB a mano — `python3 settings.py set ui.background_custom`,
#: aquí no cabe honesto).
_FONDOS = (("tema", "el del tema"), ("negro", "negro puro"),
           ("grafito", "grafito"), ("azul", "azul noche"),
           ("verde", "verde bosque"), ("violeta", "violeta"))

_ETAPAS = ("motores", "apariencia", "agente")

#: Opción extra del paso agente (las otras 3 se toman de add_agent_tui).
_SIN_AGENTE = ("ninguno", "terminar sin agente",
               ("También puedes agregarlo cuando quieras desde el hub "
                "(Menú › «Agregar agente») — crear, cargar o descubrir siguen "
                "ahí, idénticos.",))


# ── flag de primer uso ──────────────────────────────────────────────────────
def flag_path():
    """Dónde queda constancia de que el onboarding corrió. Env
    WORKSPACE_ONBOARDED la pisa (tests herméticos / overrides)."""
    p = os.environ.get("WORKSPACE_ONBOARDED", "").strip()
    if p:
        return os.path.expanduser(p)
    return os.path.join(_paths.state_dir(),
                        "onboarded.json")


def leer_flag():
    """El flag como dict ({} si no existe/ilegible)."""
    try:
        with open(flag_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def pendientes_verificables(motores=None):
    """Lo que FALTA para declarar la máquina lista, verificado contra el
    estado real (no contra lo que el flujo creyó): 'motor' si ningún motor
    soportado tiene binario; 'agente' si ningún agente es lanzable."""
    out = []
    try:
        harn = _descriptores()
        sel = motores if motores is not None else list(harn)
        if not any((harn.get(e) or {}).get("binaries_ok") for e in sel):
            out.append("motor")
    except Exception:
        out.append("motor")
    try:
        import agent_state
        if not agent_state.snapshot().launchable():
            out.append("agente")
    except Exception:
        out.append("agente")
    return out


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
                d["ready"], d["detail"] = False, _t("onboarding.probe_fail",
                                                "probe falló: {err}").format(
                                                    err=e)
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
    → el snapshot de choices de ui.theme → (default del hub,)."""
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
        return [(c, c) for c in spec.get("choices") or (_tema_default(),)]
    except Exception:
        return [(_tema_default(), _tema_default())]


def _tema_default():
    """El default ÚNICO del hub (tuitheme.DEFAULT_ID) — no un literal suelto."""
    try:
        import tuitheme
        return tuitheme.DEFAULT_ID
    except Exception:
        return "bruma"


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
        theme.apply_current()
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


def _fila_continuar(K, sel, iw, txt=None, extra=""):
    """El BOTÓN para avanzar, igual en todos los pasos (pedido del dueño
    2026-10-14: «que sea el botón de continuar y no seleccionar para ir
    adelante»): ✦ en acento, encendido cuando el cursor está en él."""
    bar, cur = _foco(K, sel)
    col = (K["C"] + K["BO"]) if sel else (K["B2"] + K["BO"])
    return HL.clip("%s%s %s%s%s%s" % (bar, cur, col,
                                      txt or _t("onboarding.continuar", "✦ continuar"),
                                      K["R"], extra), iw)


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
        n = len(i18n.available() if i18n else [("es", ""), ("en", "")])
        txt = _t("onboarding.action.idioma", "Enter elige el idioma") \
            if S.get("li", 0) < n else \
            _t("onboarding.action.continuar", "Enter continúa al siguiente paso")
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
        if S.get("asi", 1) < len(opts):
            txt = _t("onboarding.action.autostart",
                     "Enter elige «{lbl}» · Esc salta").format(lbl=opts[S.get("asi", 1)][1])
        else:
            txt = _t("onboarding.action.continuar", "Enter continúa al siguiente paso")
    elif v == "agente":
        ops = _opciones_agente()
        tok, lbl, _d = ops[S["ai"] % len(ops)]
        txt = _t("onboarding.action.agente", "Enter abre «{lbl}»").format(
            lbl=_t("onboarding.agente.%s.label" % tok, lbl)) if tok != "ninguno" else \
            _t("onboarding.action.sin_agente", "Enter continúa sin agente (lo agregas después)")
    elif v == "gcal":
        txt = _t("onboarding.action.gcal_done", "Enter te lleva al resumen") \
            if _gcal_configured() else \
            _t("onboarding.action.gcal", "Esc salta · Enter conecta")
    elif v == "resumen":
        txt = _t("onboarding.action.resumen", "Enter abre el hub")
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
    eleccion = S.get("as_choice", 0 if cur_on else 1)
    izq = []
    izq.append(_divisor(K, _t("onboarding.autostart.div", "arranque"), iw,
                        tono=2))
    izq += _parrafo(K, (_t("onboarding.autostart.heading",
                           "¿Cuándo abre Workspace?"),), iw, color=K["WH"])
    izq.append("")
    for i, (_tok, lbl) in enumerate(opts):
        sel = (i == S.get("asi", 1))
        activo = (i == eleccion)
        bar, cur = _foco(K, sel)
        marca = ("%s●%s" % (K["C"], K["R"])) if activo else \
            ("%s○%s" % (K["GREY"], K["R"]))
        lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel
                          else (K["GREY"] if activo else K["DK"]), lbl, K["R"])
        izq.append(HL.clip("%s%s %s %s" % (bar, cur, marca, lab), iw))
        izq.append("")
    izq.append(_fila_continuar(K, S.get("asi", 1) >= len(opts), iw))

    der = []
    foco = opts[min(S.get("asi", 1), len(opts) - 1) if S.get("asi", 1) < len(opts) else eleccion][0]
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


def _gcal_on():
    """¿Se ofrece el paso de Google Calendar? En pausa por ahora (gcal.enabled)."""
    try:
        import gcal
        return gcal.enabled()
    except Exception:
        return False


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
    """Google Calendar: browser OAuth first, iCal fallback; local credentials."""
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
               'Pulsa Enter y elige «Conectar con Google en el navegador».'),
            _t("onboarding.gcal.step2",
               'Elige tu cuenta de Google y autoriza leer los eventos.'),
            _t("onboarding.gcal.step3", 'Vuelve a Workspace: la sesión se renueva automáticamente.'),
            _t("onboarding.gcal.step4",
               'También puedes conectar con una URL iCal.'),
            _t("onboarding.gcal.step5",
               'La primera conexión necesita el cliente OAuth de Workspace.'))
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
            'La sesión de Google o la URL iCal se guarda en tu máquina. Puedes quitar la conexión desde el calendario.'),),
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
    try:
        activo = i18n.lang() if i18n else "es"
    except Exception:
        activo = "es"
    for i, (code, name) in enumerate(opts):
        sel = (i == S.get("li", 0))
        bar, cur = _foco(K, sel)
        marca = ("%s●%s" % (K["C"], K["R"])) if code == activo else \
            ("%s○%s" % (K["GREY"], K["R"]))
        lab = "%s%s%s  %s(%s)%s" % ((K["WH"] + K["BO"]) if sel else K["GREY"],
                                    name, K["R"], K["DK"], code, K["R"])
        izq.append(HL.clip("%s%s %s %s" % (bar, cur, marca, lab), iw))
    izq += ["", _fila_continuar(K, S.get("li", 0) >= len(opts), iw)]
    der = []
    if full >= 1:
        der.append(_divisor(K, "workspace", iw, tono=1))
        der += _parrafo(K, (_t("onboarding.idioma.body",
                              "Puedes cambiarlo cuando quieras desde el hub "
                              "(«Idioma»). Las pantallas de desarrollo "
                              "quedan en español."),), iw)
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
    izq += ["", _fila_continuar(K, True, iw)]
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
    izq.append(_fila_continuar(K, selc, iw, _cont, "   %s%s%s" % (K["DK"], _mk, K["R"])))

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


def _fondo_val(v):
    """VALOR de ui.background tal como se MUESTRA (el guardado no cambia):
    en es es el id mismo (paridad); en en, su nombre corto traducido."""
    v = str(v)
    return _t("onboarding.fondo_val.%s" % v, v) if v in _FONDO_IDS else v


_FONDO_IDS = ("tema", "negro", "grafito", "azul", "verde", "violeta",
              "personalizado")


def _items_apariencia(S):
    """[(tipo, id, label)] navegables + la fila continuar al final."""
    out = [("tema", tid, lbl) for tid, lbl in S["temas"]]
    out += [("fondo", fid, _t("onboarding.fondo.%s" % fid, lbl))
            for fid, lbl in _FONDOS]
    return out


def _b_apariencia(S, K, iw, full=2):
    items = _items_apariencia(S)
    tema_act = str(_setting("ui.theme", _tema_default()))
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
    izq.append(_fila_continuar(K, S["ti"] == len(items), iw))

    der = []
    der.append(_divisor(K, _t("onboarding.div.tu_eleccion", "tu elección"),
                        iw, tono=1))
    der.append(HL.clip(" %s%s%s  %s%s%s" % (
        K["DK"], _t("onboarding.apariencia.group.tema", "tema"), K["R"],
        K["WH"] + K["BO"], tema_act, K["R"]), iw))
    der.append(HL.clip(" %s%s%s %s%s%s" % (
        K["DK"], _t("onboarding.apariencia.group.fondo", "fondo"), K["R"],
        K["WH"] + K["BO"], _fondo_val(fondo_act), K["R"]), iw))
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
            "Brillo y luz roja: en «Personalización» del hub."),), iw)
    return izq, der


def _b_agente(S, K, iw, full=2):
    ops = _opciones_agente()
    izq = []
    for i, (tok, lbl, _desc) in enumerate(ops):
        sel = (i == S["ai"])
        if tok == "ninguno":                     # el botón para avanzar sin agente
            izq.append(_fila_continuar(K, sel, iw, _t("onboarding.continuar_sin_agente",
                                                     "✦ continuar sin agente")))
            continue
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


#: Las teclas que IMPORTAN al salir del onboarding (lección Omarchy: el toast
#: de bienvenida enseña Super+Space/Super+K): (tecla, clave i18n, texto ES).
#: Solo las que de verdad funcionan en el hub — ahí cada letra escribe en la
#: búsqueda; las cifras van a tus agentes y `q` sale.
_TECLAS_CLAVE = (
    ("workspace", "onboarding.resumen.tecla_abrir",
     "abre el hub desde cualquier terminal"),
    ("abc", "onboarding.resumen.tecla_buscar",
     "escribe para buscar un agente o una sección"),
    ("1-9", "onboarding.resumen.tecla_agentes",
     "apunta a tu agente; la misma tecla otra vez lo abre"),
    ("q", "onboarding.resumen.tecla_salir",
     "sale del hub a tu terminal"),
)


def teclas_clave():
    """[(tecla, texto)] de las teclas que importan, en el idioma activo.
    Solo LEE (no toca keybinds.json ni el flag)."""
    return [(tecla, _t(key, es)) for tecla, key, es in _TECLAS_CLAVE]


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
        K["WH"] + K["BO"], _setting("ui.theme", _tema_default()), K["R"],
        _t("onboarding.apariencia.group.fondo", "fondo"),
        K["WH"] + K["BO"], _fondo_val(_setting("ui.background", "tema")),
        K["R"]), iw))
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
            "sin agentes aún — «Agregar agente» en el hub cuando quieras"),
            K["R"]), iw))
    if S.get("tono"):
        izq.append(HL.clip(" %s%s%s" % (K["OK"], _t(
            "onboarding.resumen.tono_ok", "tono ajustado para {agente} ✓")
            .format(agente=S["tono"]), K["R"]), iw))

    der = []
    # Primero las teclas (esencial: no se degrada con `full`); luego dónde quedó.
    der.append(_divisor(K, _t("onboarding.resumen.div_teclas",
                              "las teclas que importan"), iw, tono=1))
    for tecla, txt in teclas_clave():
        der.append(HL.clip(" %s%s%s  %s%s%s" % (
            K["WH"] + K["BO"], HL.pad(tecla, 10), K["R"],
            K["GREY"], txt, K["R"]), iw))
    der.append("")
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
               "Enter te deja en el hub: ahí lanzas agentes y en el Menú "
               "tienes Tono, Agentes y «Agregar agente»."),
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
    "resumen": "Enter — al hub",
}


# ══ REDISEÑO 2026-10-14 (concepto Omarchy, como las secciones del hub) ══════
# Cada paso en UNA caja centrada: arriba el avance (motores → apariencia →
# agente), en medio SOLO lo que hay que decidir y abajo la acción principal
# (▸). Lo didáctico de cada paso —qué cambia, dónde queda, el plan— vive
# detrás de `i` (antes era la caja de la derecha). La lógica de cada paso no
# cambió: mismos builders, mismas teclas, más `i`.
_OB_BOX_W = 66


def _chips_ob(S):
    """Pie corto por paso: moverse · la acción · la explicación · salir."""
    v = S["view"]
    info = ("i", _t("onboarding.k.info", "cómo funciona"))
    tabla = {
        "idioma": (("↑↓", _t("onboarding.k.pick", "elige")),
                   ("Enter", _t("onboarding.k.choose", "elige")), info,
                   ("q", _t("onboarding.k.skip", "salta"))),
        "bienvenida": (("Enter", _t("onboarding.k.start", "empieza")), info,
                       ("q", _t("onboarding.k.to_hub", "al hub"))),
        "motores": (("↑↓", _t("onboarding.k.engine", "motor")),
                    (_t("onboarding.k.space", "espacio"), _t("onboarding.k.mark", "marca")),
                    ("Enter", _t("onboarding.k.next", "continúa")), info,
                    ("Esc", _t("onboarding.k.back", "atrás"))),
        "apariencia": (("↑↓", _t("onboarding.k.option", "opción")),
                       ("Enter", _t("onboarding.k.apply", "aplica")), info,
                       ("Esc", _t("onboarding.k.back", "atrás"))),
        "autostart": (("↑↓", _t("onboarding.k.option", "opción")),
                      ("Enter", _t("onboarding.k.choose", "elige")), info,
                      ("Esc", _t("onboarding.k.skip", "salta"))),
        "agente": (("↑↓", _t("onboarding.k.path", "camino")),
                   ("Enter", _t("onboarding.k.open", "abre")), info,
                   ("Esc", _t("onboarding.k.back", "atrás"))),
        "gcal": (("Enter", _t("onboarding.k.connect", "conecta")), info,
                 ("Esc", _t("onboarding.k.skip", "salta"))),
        "resumen": (("Enter", _t("onboarding.k.to_hub", "al hub")), info),
    }
    return tabla.get(v, (info,))


def _titulos(v):
    _b, t_izq, t_der = _VISTAS[v]
    tk = _TITLE_KEYS.get(v)                      # título traducido (fallback: literal)
    if tk:
        t_izq, t_der = _t(tk[0], t_izq), _t(tk[1], t_der)
    return t_izq, t_der


def _cuerpo_ob(S, K, iw):
    """El paso en la caja: avance · lo que se decide · la acción principal."""
    v = S["view"]
    izq, der = _VISTAS[v][0](S, K, iw, 2)
    out = [_fila_etapas(S, K, iw + 1), ""]
    cuerpo = list(izq)
    if v == "resumen":
        # las teclas que importan son lo esencial del cierre: van a la vista
        fin = next((i for i, ln in enumerate(der)
                    if i and not SB._ANSI.sub("", ln).strip()), len(der))
        cuerpo += [""] + list(der[:fin])
        cuerpo += ["", _fila_continuar(K, True, iw, _t("onboarding.ir_al_hub", "✦ ir al hub"))]
    # el cursor del paso (para que la caja lo siga si no cabe todo)
    S["_cur"] = len(out) + next((i for i, ln in enumerate(cuerpo)
                                 if K["PTR"] in ln), 0)
    out += cuerpo + ["", HL.clip(_accion_primaria(S, K, iw + 1), iw)]
    return [HL.clip(ln, iw) for ln in out]


def render(S, w, h):
    K = _K()
    v = S["view"]
    palabra = HL.section_word('onboarding')
    t_izq, t_der = _titulos(v)
    if S.get("info"):
        return SB.info_frame(K, w, h, palabra, t_der,
                             [("lines", lambda iw: _VISTAS[v][0](S, K, iw, 2)[1])],
                             state=S["info"], box_w=66)
    return SB.frame(K, w, h, palabra, t_izq, lambda iw: _cuerpo_ob(S, K, iw), _chips_ob(S),
                    msg=S.get("msg", ""), cursor_line=lambda: S.get("_cur", 0),
                    box_w=_OB_BOX_W)


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
    if SB.info_key(S, key):                      # i / ? abre, desplaza y cierra la explicación
        return True
    if key in ("q", "Q") and v != "resumen":
        S["salir"] = "quit"
        return False

    if v == "idioma":
        opts = i18n.available() if i18n else [("es", "Español"),
                                              ("en", "English")]
        n = len(opts)
        if key == "up":
            S["li"] = (S.get("li", 0) - 1) % (n + 1)      # + el botón «continuar»
        elif key in ("down", "tab"):
            S["li"] = (S.get("li", 0) + 1) % (n + 1)
        elif key == "\x1b":                      # Esc en el paso 0 = salta
            S["salir"] = "quit"
            return False
        elif key in tuple("12")[:n]:
            S["li"] = int(key) - 1
            key = "\r"                            # cae a elegir
        if key in ("\r", "\n", " "):
            if S.get("li", 0) >= n:               # el botón: avanza
                if key != " ":
                    S["view"] = "bienvenida"      # el resto ya sale en ese idioma
                return True
            code, name = opts[S.get("li", 0)]
            if i18n:
                try:
                    i18n.set_lang(code)           # persiste ui.lang + invalida cache
                except Exception:
                    pass
            S["li"] = n                           # elegido: el cursor pasa al botón
            S["msg"] = "%s ✓" % name
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
            S["asi"] = (S.get("asi", 1) - 1) % (n + 1)    # + el botón «continuar»
        elif key in ("down", "tab"):
            S["asi"] = (S.get("asi", 1) + 1) % (n + 1)
        elif key == "\x1b":                       # Esc = salta (al agente)
            S["view"] = "agente"
        elif key in ("\r", "\n", " "):
            if S.get("asi", 1) < n:               # elegir: marca y el cursor pasa al botón
                S["as_choice"] = S["asi"]
                S["asi"] = n
                S["msg"] = _t("onboarding.msg.as_chosen",
                              "«{lbl}» elegido · ✦ continuar lo guarda").format(
                                  lbl=opts[S["as_choice"]][1])
            elif key != " ":                      # el botón: guarda lo elegido y avanza
                cur_on = bool(_setting("ui.autostart", False))
                on = (S.get("as_choice", 0 if cur_on else 1) == 0)   # 0 = al abrir terminal
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
             "preset": "", "continuar": True}      # con su botón «✦ continuar»
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
    """Choose browser OAuth or hidden iCal paste outside the alt-screen."""
    import google_connect_ui
    res = google_connect_ui.choose_connection()
    S["msg"] = google_connect_ui.result_message(res)


# ── entrada ─────────────────────────────────────────────────────────────────
def _estado_inicial():
    harn = _descriptores()
    sel = {e for e in SOPORTADOS if (harn.get(e) or {}).get("binaries_ok")}
    return {"view": "idioma", "li": 0, "mi": 0, "ti": 0, "ai": 0,
            "asi": 0 if bool(_setting("ui.autostart", False)) else 1,
            "msg": "", "harn": harn, "probe": {}, "probing": False, "sel": sel,
            "temas": _temas(), "hechos": set(), "nuevos": [], "tono": "",
            "def_engine": "", "salir": None}


def _progreso(S):
    """Estado por etapa para reanudar (se guarda en cada transición)."""
    et = {}
    for e in _ETAPAS:
        if e in S["hechos"]:
            et[e] = "omitida" if e in S.get("omitidas", ()) else "completa"
        else:
            et[e] = "pendiente"
    return {"etapas": et, "vista": S.get("view") or "idioma",
            "motores_sel": sorted(S.get("sel") or ())}


def _resumen_flag(S, completo):
    pend = pendientes_verificables(sorted(S.get("sel") or ()) or None)
    return {"modo": "onboarding",
            # «listo» = el flujo terminó Y lo verificable se cumple (U07)
            "completo": bool(completo) and not pend,
            "pendientes": pend,
            **_progreso(S),
            "motores": sorted(S["sel"]),
            "default_engine": S.get("def_engine") or "",
            "tema": str(_setting("ui.theme", "")),
            "fondo": str(_setting("ui.background", "")),
            "agentes": [a["name"] for a in _agentes()],
            "tono": S.get("tono") or None}


#: Cómo terminó la última corrida: "fin" (✦ ir al hub) · "quit" · None.
#: front._run_onboarding lo lee para abrir el hub al terminar.
ULTIMA_SALIDA = None


def run(force=False):
    """El flujo completo. force=True lo corre aunque ya haya corrido
    (`workspace onboarding`). Sin TTY: señala el camino y no truena."""
    global ULTIMA_SALIDA
    ULTIMA_SALIDA = None
    if not force and ya_corrio():
        print(_t("onboarding.cli.ya_corrio",
                 "el onboarding ya corrió aquí — repetir: workspace onboarding"))
        return 0
    try:
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactivo = False
    if not interactivo:
        print(_t("onboarding.cli.no_tty",
                 "el onboarding necesita una terminal interactiva."))
        print(_t("onboarding.cli.no_tty2", "abre `workspace` en una terminal "
                 "y corre: workspace onboarding"))
        return 0
    prev = leer_flag()
    _marcar({"modo": "onboarding", "completo": False})   # jamás re-molestar
    S = _estado_inicial()
    _reanudar(S, prev)
    _probe_start(S)
    try:
        while True:
            token = _pantalla(S)
            _marcar(_progreso(S))                 # cada salida del driver guarda
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
                if token == "ninguno":           # explorar: omitida, queda pendiente
                    S.setdefault("omitidas", set()).add("agente")
                else:
                    S.get("omitidas", set()).discard("agente")
                _marcar(_progreso(S))
                # paso opcional antes del resumen (Google Calendar: en pausa)
                S["view"], S["salir"] = ("gcal" if _gcal_on() else "resumen"), None
                continue
            if token == "gcal_connect":           # prompt clásico fuera del alt-screen
                _gcal_connect_clasico(S)
                S["view"], S["salir"] = "gcal", None
                continue
            break                                 # token desconocido → fuera
    finally:
        _marcar(_resumen_flag(S, S.get("salir") == "fin"))
        _aplicar_osc()                            # el hub entra ya pintado
        ULTIMA_SALIDA = S.get("salir")
    return 0


def _reanudar(S, prev):
    """Si un onboarding anterior quedó a medias, continúa donde quedó:
    etapas completas se respetan, la vista arranca en la primera etapa
    pendiente (o en la que estaba). Un flag 'adopcion' o completo no reanuda."""
    if not isinstance(prev, dict) or prev.get("modo") != "onboarding" \
            or prev.get("completo"):
        return False
    et = prev.get("etapas") or {}
    if not et:
        return False
    for e, v in et.items():
        if e in _ETAPAS and v in ("completa", "omitida"):
            S["hechos"].add(e)
            if v == "omitida":
                S.setdefault("omitidas", set()).add(e)
    sel = prev.get("motores_sel")
    if isinstance(sel, list) and sel:
        S["sel"] = set(sel) & set(SOPORTADOS) or S["sel"]
    pend = [e for e in _ETAPAS if e not in S["hechos"]]
    S["view"] = pend[0] if pend else (prev.get("vista") or "resumen")
    if S["view"] == "gcal" and not _gcal_on():
        S["view"] = "resumen"
    if S["view"] not in _VISTAS:
        S["view"] = "bienvenida"
    S["msg"] = _t("onboarding.reanudado", "continuando donde lo dejaste")
    return True


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
