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


def _estado_motor(K, S, eid):
    """(texto, color, elegible) — el estado HONESTO de un motor: binario,
    y sesión solo cuando el probe ya respondió. Nada inventado."""
    d = S["harn"].get(eid) or {}
    if not d.get("installed"):
        return ("no disponible en esta instalación", K["DK"], False)
    if not d.get("binaries_ok"):
        falta = ", ".join("`%s`" % b for b in (d.get("needs") or [])) or "CLI"
        return ("no instalado — falta %s en PATH" % falta, K["DK"], False)
    p = S["probe"].get(eid)
    if p is None:
        return ("binario ✓ · checando sesión…", K["DIM"], True)
    if p.get("ready"):
        return ("binario ✓ · sesión activa ✓", K["OK"], True)
    det = p.get("detail") or "sin sesión"
    return ("binario ✓ · falta login — %s" % det, K["B"], True)


def _estado_corto(K, S, eid):
    """Versión compacta del estado (para el resumen): jamás se trunca."""
    d = S["harn"].get(eid) or {}
    if not d.get("binaries_ok"):
        return ("no instalado", K["DK"])
    p = S["probe"].get(eid)
    if p is None:
        return ("binario ✓", K["DIM"])
    if p.get("ready"):
        return ("sesión ✓", K["OK"])
    return ("falta login", K["B"])


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


# ── render ──────────────────────────────────────────────────────────────────
def _fila_etapas(S, K, w):
    """`1 motores ── 2 apariencia ── 3 agente` — etapas REALES del proceso
    (hechas ✓ · actual encendida · pendientes tenues), no el cursor."""
    partes = []
    for n, et in enumerate(_ETAPAS):
        if et in S["hechos"]:
            partes.append("%s✓ %s%s" % (K["OK"], et, K["R"]))
        elif S["view"] == et:
            partes.append("%s%s %d %s%s" % (K["C"] + K["BO"], K["PTR"],
                                            n + 1, et, K["R"]))
        else:
            partes.append("%s%d %s%s" % (K["DK"], n + 1, et, K["R"]))
    fila = (" %s%s%s " % (K["DK"], K["SEP"] * 2, K["R"])).join(partes)
    pad = max(0, ((w - 1) - HL.vis(fila)) // 2)
    return HL.clip(" " * pad + fila, w - 1)


def _b_bienvenida(S, K, iw, full=2):
    izq = _parrafo(K, (
        "Workspace es un hub local para tus agentes de IA: cada agente vive "
        "en su propio cerebro (una carpeta de archivos tuya) y corre sobre "
        "un motor CLI que ya tengas instalado — Claude Code, Codex o "
        "Antigravity.",
        "Todo pasa en tu máquina: cero dependencias, sin cuentas nuevas, y "
        "Workspace nunca ve ni guarda tus credenciales (el login es de cada "
        "CLI)."), iw)
    der = []
    der.append(_divisor(K, "qué viene ahora", iw, tono=2))
    pasos = (("1 motores", "detecto qué CLIs tienes y eliges cuáles usar"),
             ("2 apariencia", "tema y fondo del hub — se ven al instante"),
             ("3 agente", "crear uno nuevo, cargar uno existente o buscar "
                          "en tu disco (y afinar su tono)"))
    for tit, txt in pasos:
        der.append(HL.clip(" %s%s%s" % (K["WH"] + K["BO"], tit, K["R"]), iw))
        for sub in _wrap(txt, max(8, iw - 4)):
            der.append(HL.clip("    %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    if full >= 1:
        der.append("")
        der.append(_divisor(K, "transparencia", iw))
        der += _parrafo(K, (
            "Al final: un resumen de lo elegido y dónde quedó guardado. "
            "Puedes saltarte esto con q y repetirlo cuando quieras con "
            "`workspace onboarding`.",), iw, bullet=False)
    return izq, der


def _b_motores(S, K, iw, full=2):
    izq = []
    for i, eid in enumerate(SOPORTADOS):
        sel = (i == S["mi"])
        txt, col, elegible = _estado_motor(K, S, eid)
        usa = eid in S["sel"]
        cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
        marca = ("%s●%s" % (K["C"], K["R"])) if usa else \
            ("%s○%s" % ((K["GREY"] if elegible else K["DK"]), K["R"]))
        lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel
                          else (K["GREY"] if elegible else K["DK"]),
                          eid, K["R"])
        izq.append(HL.clip(" %s %s %s" % (cur, marca, lab), iw))
        # el ESTADO en su propia línea: completo, jamás truncado
        for sub in _wrap(txt, max(8, iw - 6)):
            izq.append(HL.clip("      %s%s%s" % (col, sub, K["R"]), iw))
        izq.append("")
    izq.append(_divisor(K, "listo", iw))
    selc = (S["mi"] == len(SOPORTADOS))
    cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if selc else " "
    izq.append(HL.clip(" %s %s✦ continuar%s   %s%d motor(es) marcados%s"
                       % (cur, (K["C"] + K["BO"]) if selc else K["GREY"],
                          K["R"], K["DK"], len(S["sel"]), K["R"]), iw))

    der = []
    if S["mi"] < len(SOPORTADOS):
        eid = SOPORTADOS[S["mi"]]
        info = _MOTOR_INFO.get(eid, ("", "", ""))
        der.append(_divisor(K, "tu elección", iw, tono=1))
        der += _parrafo(K, (info[0],), iw, color=K["WH"])
        txt, col, _e = _estado_motor(K, S, eid)
        der.append(HL.clip(" %sestado: %s%s%s" % (K["DK"], col, txt,
                                                  K["R"]), iw))
        if full >= 1:
            der.append("")
            der.append(_divisor(K, "qué cambia", iw, tono=3))
            der += _parrafo(K, (info[2], info[1]), iw)
    else:
        der.append(_divisor(K, "qué cambia", iw, tono=3))
        if S["sel"]:
            primero = next(e for e in SOPORTADOS if e in S["sel"])
            der += _parrafo(K, (
                "Los motores marcados son tu set de trabajo. «%s» queda como "
                "default (modelos.default_engine) para los agentes que no "
                "declaren el suyo — cada agente puede fijar otro después."
                % primero,), iw)
        else:
            der += _parrafo(K, (
                "Sin ningún motor marcado no se puede lanzar agentes. Puedes "
                "continuar igual, instalar un CLI después y repetir esto con "
                "`workspace onboarding`.",), iw, color=K["B"])
    if full >= 2:
        der.append("")
        der.append(_divisor(K, "honesto", iw))
        der += _parrafo(K, (
            "El estado de sesión se lee del propio CLI de cada motor; "
            "Workspace no guarda ni ve credenciales.",), iw)
    return izq, der


def _items_apariencia(S):
    """[(tipo, id, label)] navegables + la fila continuar al final."""
    out = [("tema", tid, lbl) for tid, lbl in S["temas"]]
    out += [("fondo", fid, lbl) for fid, lbl in _FONDOS]
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
            izq.append(_divisor(K, tipo, iw))
            grupo = tipo
        sel = (i == S["ti"])
        act = (iid == (tema_act if tipo == "tema" else fondo_act))
        cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
        marca = ("%s●%s" % (K["C"], K["R"])) if act else \
            ("%s·%s" % (K["DK"], K["R"]))
        lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel
                          else (K["GREY"] if act else K["DIM"]),
                          HL.pad(lbl, 18), K["R"])
        extra = ("%sactivo%s" % (K["OK"], K["R"])) if act else ""
        izq.append(HL.clip(" %s %s %s %s" % (cur, marca, lab, extra), iw))
    izq.append("")
    selc = (S["ti"] == len(items))
    cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if selc else " "
    izq.append(HL.clip(" %s %s✦ continuar%s" % (
        cur, (K["C"] + K["BO"]) if selc else K["GREY"], K["R"]), iw))

    der = []
    der.append(_divisor(K, "tu elección", iw, tono=1))
    der.append(HL.clip(" %stema%s  %s%s%s" % (K["DK"], K["R"],
                                              K["WH"] + K["BO"],
                                              tema_act, K["R"]), iw))
    der.append(HL.clip(" %sfondo%s %s%s%s" % (K["DK"], K["R"],
                                              K["WH"] + K["BO"],
                                              fondo_act, K["R"]), iw))
    if full >= 1:
        der.append("")
        der.append(_divisor(K, "qué cambia", iw, tono=3))
        der += _parrafo(K, (
            "El tema pinta todo el hub — wordmark, cajas, sliders — y se "
            "guarda al instante: esta pantalla YA está pintada con él; eso "
            "es la vista previa.",
            "El fondo es un eje independiente: cambia solo el color de fondo "
            "de la terminal y combina con cualquier tema.",), iw)
    if full >= 2:
        der.append("")
        der.append(_divisor(K, "dónde queda", iw))
        der += _parrafo(K, (
            "ui.theme y ui.background en ~/.claude/workspace/settings.json. "
            "Más opciones (color propio #RRGGBB, animaciones, estrellas) en "
            "Config → TEMA.",), iw)
    return izq, der


def _b_agente(S, K, iw, full=2):
    ops = _opciones_agente()
    izq = []
    for i, (tok, lbl, _desc) in enumerate(ops):
        sel = (i == S["ai"])
        cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
        lab = "%s%s%s" % ((K["WH"] + K["BO"]) if sel else K["GREY"], lbl,
                          K["R"])
        izq.append(HL.clip(" %s %s%d%s  %s" % (cur, K["DK"], i + 1, K["R"],
                                               lab), iw))
        izq.append("")
    der = []
    tok, lbl, desc = ops[S["ai"] % len(ops)]
    der.append(_divisor(K, "tu elección", iw, tono=1))
    der += _parrafo(K, (lbl,), iw, color=K["WH"] + K["BO"])
    if full >= 1:
        der.append("")
        der.append(_divisor(K, "qué pasa", iw, tono=3))
        der += _parrafo(K, tuple(desc), iw)
    if full >= 2 and tok != "ninguno":
        der.append("")
        der.append(_divisor(K, "siguiente paso", iw))
        der += _parrafo(K, (
            "Se abre la pantalla real del hub («Agregar agente») en ese "
            "camino. Si queda un agente nuevo conectado, al volver podrás "
            "afinar su TONO; después, el resumen.",), iw)
    return izq, der


def _b_resumen(S, K, iw, full=2):
    izq = []
    izq.append(_divisor(K, "motores", iw, tono=1))
    if S["sel"]:
        for eid in (e for e in SOPORTADOS if e in S["sel"]):
            txt, col = _estado_corto(K, S, eid)
            izq.append(HL.clip(" %s●%s %s  %s%s%s" % (
                K["C"], K["R"], HL.pad(eid, 12), col, txt, K["R"]), iw))
        izq.append(HL.clip(" %sdefault: %s%s" % (
            K["DK"], S.get("def_engine") or "sin cambio", K["R"]), iw))
    else:
        izq.append(HL.clip(" %sninguno marcado — instala un CLI y repite "
                           "con `workspace onboarding`%s" % (K["DIM"],
                                                             K["R"]), iw))
    izq.append("")
    izq.append(_divisor(K, "apariencia", iw, tono=2))
    izq.append(HL.clip(" tema %s%s%s · fondo %s%s%s" % (
        K["WH"] + K["BO"], _setting("ui.theme", "rose"), K["R"],
        K["WH"] + K["BO"], _setting("ui.background", "tema"), K["R"]), iw))
    izq.append("")
    izq.append(_divisor(K, "agentes", iw, tono=3))
    ags = _agentes()
    if ags:
        for a in ags[:4]:
            nuevo = a["name"] in S["nuevos"]
            izq.append(HL.clip(" %s%s%s  %s%s%s" % (
                K["WH"] + K["BO"] if nuevo else K["GREY"], a["name"], K["R"],
                K["DK"], a.get("brain", ""), K["R"]), iw))
        if len(ags) > 4:
            izq.append(HL.clip(" %s… y %d más%s" % (K["DK"], len(ags) - 4,
                                                    K["R"]), iw))
    else:
        izq.append(HL.clip(" %ssin agentes aún — «Agregar agente» en el "
                           "recinto cuando quieras%s" % (K["DIM"], K["R"]),
                           iw))
    if S.get("tono"):
        izq.append(HL.clip(" %stono ajustado para %s ✓%s" % (
            K["OK"], S["tono"], K["R"]), iw))

    der = []
    der.append(_divisor(K, "dónde quedó", iw, tono=4))
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
    filas = (("config (tema, fondo, motor)", sp),
             ("agentes registrados", ap),
             ("este onboarding", flag_path()))
    for lbl, ruta in filas:
        der.append(HL.clip(" %s%s%s" % (K["GREY"], lbl, K["R"]), iw))
        der.append(HL.clip("   %s%s%s" % (K["DK"], ruta, K["R"]), iw))
    if full >= 1:
        der.append("")
        der.append(_divisor(K, "de aquí en adelante", iw))
        der += _parrafo(K, (
            "Enter te deja en el recinto: ahí lanzas agentes, entras a "
            "Config, Tono y «Agregar agente».",
            "Repetir este flujo: `workspace onboarding`.",), iw)
    return izq, der


_VISTAS = {"bienvenida": (_b_bienvenida, "QUÉ ES WORKSPACE", "EL PLAN"),
           "motores": (_b_motores, "MOTORES DETECTADOS", "EL MOTOR"),
           "apariencia": (_b_apariencia, "TEMA Y FONDO", "LA APARIENCIA"),
           "agente": (_b_agente, "TU PRIMER AGENTE", "EL CAMINO"),
           "resumen": (_b_resumen, "LO QUE QUEDÓ", "DÓNDE Y QUÉ SIGUE")}

_HINTS = {
    "bienvenida": "Enter empieza · q al hub (vuelve con `workspace onboarding`)",
    "motores": "↑↓ motor · espacio marca/quita · Enter continúa · Esc atrás · q salta",
    "apariencia": "↑↓ opción · Enter/espacio aplica (guarda ya) · Esc atrás · q salta",
    "agente": "↑↓ camino · 1-4 directo · Enter abre · Esc atrás · q salta",
    "resumen": "Enter — al recinto",
}


def render(S, w, h):
    K = _K()
    L = [""]
    bt = HL.big_title(K, w, h, indent=" ", compact=(h < 30), center=True)
    L += bt
    if len(bt) > 1:
        L += HL.title_reflection(K, w, indent=" ", center=True)
    sub = "primer arranque — deja tu Workspace listo en 3 pasos"
    L.append(" " * max(0, ((w - 1) - HL.vis(sub)) // 2)
             + "%s%s%s" % (K["DIM"], sub, K["R"]))
    L.append("%s%s%s%s%s" % (K["B2"], K["BOX"][5] * 3, K["DK"],
                             K["BOX"][5] * max(1, w - 5), K["R"]))
    L.append("")
    L.append(_fila_etapas(S, K, w))
    L.append("")
    top = len(L)
    builder, t_izq, t_der = _VISTAS[S["view"]]
    apilado = w < 100
    lw = (w - 1) if apilado else max(36, min(46, (w - 6) * 46 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    avail = max(8, (h - 1) - top - 3)
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
    L.append((" %s%s%s" % (K["B2"], S["msg"], K["R"])) if S.get("msg")
             else "")
    L.append(" %s%s%s" % (K["DK"], _HINTS[S["view"]], K["R"]))
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
        S["msg"] = "motor default: %s · guardado ✓" % primero
    else:
        S["msg"] = "no pude guardar el default (%s) — sigue igual" % err


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

    if v == "bienvenida":
        if key in ("\r", "\n"):
            S["view"] = "motores"
        elif key == "\x1b":
            S["salir"] = "quit"
            return False
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
                S["msg"] = "%s no está instalado — no se puede marcar" % eid
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
                S["view"] = "agente"
                return True
            tipo, iid, lbl = items[S["ti"]]
            skey = "ui.theme" if tipo == "tema" else "ui.background"
            ok, err = _guardar(skey, iid)
            if ok:
                _aplicar_osc()                   # preview real, al instante
                S["msg"] = "%s «%s» · guardado ✓" % (tipo, lbl)
            else:
                S["msg"] = "no se pudo aplicar %s (%s)" % (tipo, err)
        return True

    if v == "agente":
        ops = _opciones_agente()
        if key == "up":
            S["ai"] = (S["ai"] - 1) % len(ops)
        elif key in ("down", "tab"):
            S["ai"] = (S["ai"] + 1) % len(ops)
        elif key == "\x1b":
            S["view"] = "apariencia"
        elif key in tuple("1234"):
            S["ai"] = min(int(key) - 1, len(ops) - 1)
        elif key in ("\r", "\n"):
            S["salir"] = ops[S["ai"]][0]         # crear/cargar/descubrir/ninguno
            return False
        return True

    if v == "resumen":
        if key in ("\r", "\n", "q", "Q", "\x1b"):
            S["salir"] = "fin"
            return False
        return True
    return True


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


# ── entrada ─────────────────────────────────────────────────────────────────
def _estado_inicial():
    harn = _descriptores()
    sel = {e for e in SOPORTADOS if (harn.get(e) or {}).get("binaries_ok")}
    return {"view": "bienvenida", "mi": 0, "ti": 0, "ai": 0, "msg": "",
            "harn": harn, "probe": {}, "probing": False, "sel": sel,
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
                S["view"], S["salir"] = "resumen", None
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
