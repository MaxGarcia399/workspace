#!/usr/bin/env python3
"""WORKSPACE · onboarding_tui — el PRIMER ARRANQUE guiado (repo público).

La primera vez que alguien baja Workspace y lo abre, no hay config, no hay
agentes y no sabe qué es esto. Este flujo lo recibe al estilo WORKSPACE
(wordmark, cajas del tema) y lo deja operativo en 2 etapas (las de
`_ETAPAS`) y un resumen honesto:

  (idioma) → bienvenida → 1 MOTORES → 2 AGENTE → resumen

El idioma solo se pregunta si el del sistema no se pudo leer (o no está entre
los que hay): si se lee, se guarda y se empieza en la bienvenida.

F0 del onboarding nuevo (19-nov): tema y fondo, arranque (abrir al abrir la
terminal), tono y Google Calendar SALIERON del primer arranque. Quedan con su
valor de fábrica y se cambian después en el hub (Personalización, Tono); el
arranque nuevo lo deja encendido el instalador (decisión del dueño: greeter ON
de fábrica, sin preguntarlo aquí).

Qué REUSA (nada se duplica — este módulo solo orquesta):
  · motores     harnesses.describe(probe=True): detección real de binarios en
                PATH + la sesión que dice el comando OFICIAL de cada motor
                (session_active; el probe corre en un hilo daemon — la UI
                nunca se congela). La lista enseña los motores instalados; los
                que no están van en una sola línea. El primero marcado queda
                como `modelos.default_engine` (config_engine, tier A).
  · agente      add_agent_tui COMPLETO (crear / cargar / descubrir): aquí solo
                se elige el camino; el flujo real es la misma pantalla del hub,
                pre-sembrada en la vista elegida, y al terminar vuelve aquí.

No re-disparo: ~/.claude/workspace/onboarded.json (env WORKSPACE_ONBOARDED lo
pisa — tests herméticos). Se escribe en cuanto la bienvenida se PINTA sin el
aviso de tamaño (desde ahí un Ctrl-C a medias o cerrar la ventana no vuelven
a molestar) y se completa al final con el resumen real. Antes de verse no se
escribe nada, y salir desde el AVISO DE TAMAÑO (la ventana no llega al
mínimo) tampoco cuenta: el siguiente arranque lo ofrece otra vez.

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
#: harnesses.py puede listar más engines instalados; aquí solo estos nueve.
SOPORTADOS = ("claude-code", "codex", "antigravity", "opencode", "openclaw",
              "hermes", "kiro", "copilot", "cursor")

#: Copy por motor en palabras simples: qué es, cómo se entra, qué cambia.
_MOTOR_INFO = {
    "claude-code": (
        "Claude Code, de Anthropic.",
        "Entras con tu cuenta de Claude la primera vez que abres a tu agente.",
        "Es el motor que Workspace conoce mejor: te enseña en vivo lo que hace "
        "tu agente."),
    "codex": (
        "Codex, de OpenAI, con tu cuenta de ChatGPT.",
        "Para entrar: escribe «codex login» en tu terminal.",
        "Workspace nunca ve tu contraseña."),
    "antigravity": (
        "Antigravity, de Google (Gemini).",
        "Entras con tu cuenta de Google desde el propio Antigravity.",
        "Workspace lo usa igual que a los demás motores."),
    "opencode": (
        "OpenCode, de código abierto: funciona con el modelo que elijas.",
        "Para conectar tu cuenta: escribe «opencode auth login» en tu terminal.",
        "Usa el modelo que elijas en OpenCode; Workspace nunca ve tu llave."),
    "openclaw": (
        "OpenClaw, un agente personal de código abierto.",
        "Conecta tu cuenta y elige tu modelo desde Motores › cuenta y proveedor.",
        "Workspace le da su propio espacio: no fija modelo y nunca ve tu llave."),
    "hermes": (
        "Hermes, de Nous Research, de código abierto.",
        "Conecta tu cuenta y elige tu modelo desde Motores › cuenta y proveedor.",
        "Workspace usa su propia copia (tu Hermes no cambia) y nunca ve tu "
        "llave."),
    "kiro": (
        "Kiro, el agente de AWS (antes Amazon Q).",
        "Para entrar: escribe «kiro-cli login» en tu terminal.",
        "Usa el modelo que elijas en Kiro; Workspace nunca ve tu llave ni toca "
        "tu configuración de Kiro."),
    "copilot": (
        "GitHub Copilot, con tu cuenta de Copilot.",
        "Para entrar: escribe «copilot login» en tu terminal (o desde Motores › "
        "cuenta y proveedor).",
        "Usa el modelo de tu cuenta. Workspace solo agrega su barra en la "
        "configuración de Copilot y nunca ve tu contraseña."),
    "cursor": (
        "Cursor, con tu cuenta de Cursor.",
        "Para entrar: escribe «cursor-agent login» en tu terminal (o desde "
        "Motores › cuenta y proveedor).",
        "Usa el modelo que elijas en Cursor. Workspace agrega su barra "
        "y nunca ve tu contraseña."),
}

_ETAPAS = ("motores", "agente")

#: Opción extra del paso agente (las otras 3 se toman de add_agent_tui).
_SIN_AGENTE = ("ninguno", "terminar sin agente",
               ("También puedes agregarlo cuando quieras desde Workspace "
                "(Agentes › «+ agregar agente»).",))


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


def _flag_previo():
    """Los bytes del flag ANTES de una corrida (None = no existía). Uno que
    existe pero no se puede leer cuenta como existente (b""): no se toca."""
    try:
        p = flag_path()
        if not os.path.exists(p):
            return None
        with open(p, "rb") as fh:
            return fh.read()
    except Exception:
        return b""


def _visto(S):
    """La bienvenida YA se vio (se pintó sin el aviso de tamaño): desde aquí
    cuenta como corrida. Antes no se escribe nada (ver run)."""
    if not S.get("_visto"):
        S["_visto"] = True
        S["_flag_mio"] = _marcar({"modo": "onboarding", "completo": False})


def _restaurar_flag(previo):
    """Deja el flag como estaba antes de la corrida (lo de _flag_previo).
    Falla-suave: el peor caso es el de siempre (no re-ofrecer)."""
    try:
        p = flag_path()
        if previo is None:
            if os.path.exists(p):
                os.remove(p)
        elif previo:
            tmp = p + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(previo)
            os.replace(tmp, p)
    except Exception:
        pass


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
        return (_t("onboarding.motores.st.not_installed", "no instalado"),
                K["DK"], False)
    p = S["probe"].get(eid)
    if p is None:
        return (_t("onboarding.motores.st.checking",
                   "revisando si ya entraste…"), K["DIM"], True)
    if p.get("ready"):
        return (_t("onboarding.motores.st.session_ok",
                   "listo ✓ · ya entraste a tu cuenta"), K["OK"], True)
    if "session" in p and p["session"] is None:          # P1: no se pudo saber: se dice así, sin inventar
        return (_t("onboarding.motores.st.session_unknown",
                   "instalado · no pude comprobar si ya entraste"), K["DIM"], True)
    return (_t("onboarding.motores.st.login_needed",
               "instalado · falta entrar a tu cuenta"), K["B"], True)


def _estado_corto(K, S, eid):
    """Versión compacta del estado (para el resumen): jamás se trunca."""
    d = S["harn"].get(eid) or {}
    if not d.get("binaries_ok"):
        return (_t("onboarding.motores.short.not_installed", "no instalado"),
                K["DK"])
    p = S["probe"].get(eid)
    if p is None:
        return (_t("onboarding.motores.short.binary", "instalado"), K["DIM"])
    if p.get("ready"):
        return (_t("onboarding.motores.short.session", "listo ✓"), K["OK"])
    if "session" in p and p["session"] is None:
        return (_t("onboarding.motores.short.unknown", "sin comprobar"), K["DIM"])
    return (_t("onboarding.motores.short.login", "falta entrar"), K["B"])


def _visibles(S):
    """Los motores que la lista enseña (y que ↑↓ recorre): los instalados, en
    el orden de SOPORTADOS. Los que no están van juntos en una sola línea."""
    return [e for e in SOPORTADOS if (S["harn"].get(e) or {}).get("binaries_ok")]


def _no_instalados(S):
    return [e for e in SOPORTADOS if not (S["harn"].get(e) or {}).get("binaries_ok")]


#: El idioma del sistema → el de Workspace, para no preguntar lo que la
#: computadora ya sabe. Primero el de la interfaz de macOS (AppleLanguages),
#: luego LC_ALL / LC_MESSAGES / LANG. Solo cuenta si es uno de los que hay.
def _idioma_del_sistema():
    candidatos = []
    if sys.platform == "darwin":
        try:
            import subprocess
            r = subprocess.run(["/usr/bin/defaults", "read", "-g", "AppleLanguages"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=3)
            for tok in (r.stdout or "").replace("(", " ").replace(")", " ").replace(",", " ").split():
                tok = tok.strip().strip('"')
                if tok:
                    candidatos.append(tok)
                    break                          # el primero es el de la interfaz
        except Exception:
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = (os.environ.get(var) or "").strip()
        if v and v not in ("C", "POSIX") and not v.startswith("C."):
            candidatos.append(v)
            break
    try:
        hay = {c for c, _n in (i18n.available() if i18n else [("es", ""), ("en", "")])}
    except Exception:
        hay = {"es", "en"}
    for c in candidatos:
        code = c.replace("-", "_").split("_")[0].split(".")[0].lower()
        if code in hay:
            return code
    return ""


def _idioma_auto():
    """Si nadie eligió idioma (sin ui.lang guardado ni WORKSPACE_LANG) y el del
    sistema se lee, lo guarda y devuelve True: el paso «idioma» sobra. Si ya
    había uno elegido, también sobra. False = hay que preguntarlo."""
    if os.environ.get("WORKSPACE_LANG"):
        return True
    try:
        import settings
        if settings.get_stored("ui.lang"):
            return True
    except Exception:
        return False
    code = _idioma_del_sistema()
    if not code or i18n is None:
        return False
    try:
        i18n.set_lang(code)
        return True
    except Exception:
        return False


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
        # B6 (puerta N5): Enter CONTINÚA desde cualquier fila; espacio marca
        txt = _t("onboarding.action.motores_opt",
                 "espacio marca · Enter continúa") \
            if S["mi"] < len(_visibles(S)) else \
            _t("onboarding.action.continuar", "Enter continúa al siguiente paso")
    elif v == "agente":
        ops = _opciones_agente()
        tok, lbl, _d = ops[S["ai"] % len(ops)]
        txt = _t("onboarding.action.agente", "Enter abre «{lbl}»").format(
            lbl=_t("onboarding.agente.%s.label" % tok, lbl)) if tok != "ninguno" else \
            _t("onboarding.action.sin_agente", "Enter continúa sin agente (lo agregas después)")
    elif v == "resumen":
        txt = _t("onboarding.action.resumen", "Enter abre Workspace")
    else:
        txt = ""
    return HL.clip(" %s▸ %s%s" % (K["C"] + K["BO"], txt, K["R"]), w - 1)


# ── render ──────────────────────────────────────────────────────────────────
def _fila_etapas(S, K, w):
    """`1 motores ── 2 agente` — etapas REALES del proceso (hechas ✓ ·
    actual encendida · pendientes tenues), no el cursor."""
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
    """Paso 0 (solo si el idioma del sistema no se pudo leer): elegir el
    idioma de la interfaz. Las opciones se muestran con su nombre NATIVO
    (Español / English) sea cual sea el idioma activo; al elegir, set_lang
    persiste y el resto del flujo ya sale en ese idioma."""
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
           "Workspace junta a tus agentes de IA en un solo lugar. Cada agente "
           "guarda lo que aprende en una carpeta tuya y piensa con un motor "
           "de IA que ya tienes, como Claude Code o Codex."),
        _t("onboarding.welcome.p2",
           "Todo pasa en tu computadora: no hay cuentas nuevas y Workspace "
           "nunca ve tus contraseñas.")), iw)
    izq += ["", _fila_continuar(K, True, iw)]
    der = []
    der.append(_divisor(K, _t("onboarding.welcome.plan_title",
                              "qué viene ahora"), iw, tono=2))
    pasos = (
        (_t("onboarding.welcome.step1_t", "1 motores"),
         _t("onboarding.welcome.step1_d",
            "reviso qué motores de IA tienes y si ya entraste a tu cuenta")),
        (_t("onboarding.welcome.step2_t", "2 agente"),
         _t("onboarding.welcome.step2_d",
            "creas tu primer agente (o conectas uno que ya tengas)")))
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
               "Al final ves un resumen. Tema, arranque y tono quedan como "
               "vienen y los cambias cuando quieras en Workspace. Puedes "
               "saltarte esto con q y repetirlo con «workspace onboarding»."),),
            iw, bullet=False)
    return izq, der


def _b_motores(S, K, iw, full=2):
    vis = _visibles(S)
    izq = []
    if not vis:
        izq += _parrafo(K, (_t("onboarding.motores.ninguno_instalado",
                               "No encontré ningún motor de IA en esta "
                               "computadora. Puedes seguir e instalar uno "
                               "después."),), iw, color=K["B"])
        izq.append("")
    for i, eid in enumerate(vis):
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
        if not S.get("_compacto"):           # con poco alto, sin aire entre motores
            izq.append("")
    faltan = _no_instalados(S)
    if faltan:
        for sub in _wrap(_t("onboarding.motores.no_instalados",
                            "no instalados: {lista}").format(lista=" · ".join(faltan)),
                         max(8, iw - 3)):
            izq.append(HL.clip("   %s%s%s" % (K["DK"], sub, K["R"]), iw))
    izq.append(_divisor(K, _t("onboarding.motores.div_listo", "listo"), iw))
    selc = (S["mi"] >= len(vis))
    bar, cur = _foco(K, selc)
    _cont = _t("onboarding.continuar", "✦ continuar")
    _mk = _t("onboarding.motores.marcados",
             "{n} motor(es) marcados").format(n=len(S["sel"]))
    izq.append(_fila_continuar(K, selc, iw, _cont, "   %s%s%s" % (K["DK"], _mk, K["R"])))

    der = []
    if S["mi"] < len(vis):
        eid = vis[S["mi"]]
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
                "Tu primer agente usará «{motor}». Cada agente puede usar otro "
                "después."
            ).format(motor=primero),), iw)
        else:
            der += _parrafo(K, (_t(
                "onboarding.motores.none_p",
                "Sin un motor tus agentes no pueden pensar. Puedes seguir igual "
                "e instalar uno después."),), iw, color=K["B"])
    if full >= 2:
        der.append("")
        der.append(_divisor(K, _t("onboarding.motores.div_honesto", "honesto"),
                            iw))
        der += _parrafo(K, (_t(
            "onboarding.motores.honesto_p",
            "«Listo» solo sale cuando el propio motor confirma que ya entraste. "
            "Workspace nunca ve tus contraseñas."),), iw)
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
            "Se abre el formulario; al terminar vuelves aquí y ves el "
            "resumen."),), iw)
    return izq, der


#: Las teclas que IMPORTAN al salir del onboarding (lección Omarchy: el toast
#: de bienvenida enseña Super+Space/Super+K): (tecla, clave i18n, texto ES).
#: Solo las que de verdad funcionan en el hub — ahí cada letra escribe en la
#: búsqueda; las cifras van a tus agentes y `q` sale.
_TECLAS_CLAVE = (
    ("workspace", "onboarding.resumen.tecla_abrir",
     "abre Workspace en cualquier terminal"),
    ("1-9", "onboarding.resumen.tecla_agentes",
     "elige a tu agente; la misma tecla lo abre"),
    ("abc", "onboarding.resumen.tecla_buscar",
     "escribe para buscar un agente o una sección"),
    ("q", "onboarding.resumen.tecla_salir",
     "sale a tu terminal"),
)


def teclas_clave():
    """[(tecla, texto)] de las teclas que importan, en el idioma activo.
    Solo LEE (no toca keybinds.json ni el flag)."""
    return [(_t("onboarding.resumen.tecla.%s" % tecla, tecla), _t(key, es))
            for tecla, key, es in _TECLAS_CLAVE]


def _b_resumen(S, K, iw, full=2):
    izq = []
    izq.append(_divisor(K, _t("onboarding.resumen.div_motores", "motores"),
                        iw, tono=1))
    if S["sel"]:
        for eid in (e for e in SOPORTADOS if e in S["sel"]):
            txt, col = _estado_corto(K, S, eid)
            izq.append(HL.clip(" %s●%s %s  %s%s%s" % (
                K["C"], K["R"], HL.pad(eid, 12), col, txt, K["R"]), iw))
    else:
        izq.append(HL.clip(" %s%s%s" % (K["DIM"], _t(
            "onboarding.resumen.ninguno_marcado",
            "ninguno marcado — instala uno y repite con «workspace "
            "onboarding»"), K["R"]), iw))
    izq.append("")
    izq.append(_divisor(K, _t("onboarding.resumen.div_agentes", "agentes"),
                        iw, tono=3))
    ags = _agentes()
    if ags:
        for a in ags[:4]:
            nuevo = a["name"] in S["nuevos"]
            izq.append(HL.clip(" %s%s%s" % (
                K["WH"] + K["BO"] if nuevo else K["GREY"], a["name"], K["R"]), iw))
        if len(ags) > 4:
            izq.append(HL.clip(" %s%s%s" % (K["DK"], _t(
                "onboarding.resumen.y_mas", "… y {n} más").format(
                    n=len(ags) - 4), K["R"]), iw))
    else:
        izq.append(HL.clip(" %s%s%s" % (K["DIM"], _t(
            "onboarding.resumen.sin_agentes",
            "sin agentes aún — «Agregar agente» en Workspace cuando quieras"),
            K["R"]), iw))

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
    filas = ((_t("onboarding.resumen.fila_config", "tus ajustes"), sp),
             (_t("onboarding.resumen.fila_agentes", "tus agentes"), ap),
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
               "Enter te lleva a Workspace: ahí abres a tus agentes. El tema "
               "y el arranque están en Personalización, y el tono, en Tono."),
            _t("onboarding.resumen.adelante_p2",
               "Repetir este flujo: «workspace onboarding»."),), iw)
    return izq, der


_VISTAS = {"idioma": (_b_idioma, "IDIOMA · LANGUAGE", "WORKSPACE"),
           "bienvenida": (_b_bienvenida, "QUÉ ES WORKSPACE", "EL PLAN"),
           "motores": (_b_motores, "TUS MOTORES", "EL MOTOR"),
           "agente": (_b_agente, "TU PRIMER AGENTE", "EL CAMINO"),
           "resumen": (_b_resumen, "LO QUE QUEDÓ", "DÓNDE Y QUÉ SIGUE")}

#: Claves i18n del TÍTULO de cada caja, por vista (izq, der). `idioma` no
#: entra: su título es bilingüe fijo (el idioma aún no se elige).
_TITLE_KEYS = {
    "bienvenida": ("onboarding.welcome.title_l", "onboarding.welcome.title_r"),
    "motores": ("onboarding.motores.title_l", "onboarding.motores.title_r"),
    "agente": ("onboarding.agente.title_l", "onboarding.agente.title_r"),
    "resumen": ("onboarding.resumen.title_l", "onboarding.resumen.title_r"),
}

#: Claves i18n del HINT del pie, por vista. Mismo criterio que _TITLE_KEYS.
_HINT_KEYS = {
    "idioma": "onboarding.hints.idioma",
    "bienvenida": "onboarding.hints.welcome",
    "motores": "onboarding.hints.motores",
    "agente": "onboarding.hints.agente",
    "resumen": "onboarding.hints.resumen",
}

_HINTS = {
    "idioma": "↑↓ idioma · Enter elige · Esc/q salta",
    "bienvenida": "Enter empieza · q salta (vuelve con «workspace onboarding»)",
    "motores": "↑↓ motor · espacio marca/quita · Enter continúa · Esc atrás · q salta",
    "agente": "↑↓ camino · 1-4 directo · Enter abre · Esc atrás · q salta",
    "resumen": "Enter — a Workspace",
}


# ══ REDISEÑO 2026-10-14 (concepto Omarchy, como las secciones del hub) ══════
# Cada paso en UNA caja centrada: arriba el avance (motores → agente), en
# medio SOLO lo que hay que decidir y abajo la acción principal (▸). Lo
# didáctico de cada paso —qué cambia, dónde queda, el plan— vive detrás de
# `i` (antes era la caja de la derecha).
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
                       ("q", _t("onboarding.k.skip", "salta"))),
        "motores": (("↑↓", _t("onboarding.k.engine", "motor")),
                    (_t("onboarding.k.space", "espacio"), _t("onboarding.k.mark", "marca")),
                    ("Enter", _t("onboarding.k.next", "continúa")), info,
                    ("Esc", _t("onboarding.k.back", "atrás"))),
        "agente": (("↑↓", _t("onboarding.k.path", "camino")),
                   ("Enter", _t("onboarding.k.open", "abre")), info,
                   ("Esc", _t("onboarding.k.back", "atrás"))),
        "resumen": (("Enter", _t("onboarding.k.to_hub", "a Workspace")), info),
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
        cuerpo += ["", _fila_continuar(K, True, iw, _t("onboarding.ir_al_hub", "✦ ir a Workspace"))]
    # el cursor del paso (para que la caja lo siga si no cabe todo)
    S["_cur"] = len(out) + next((i for i, ln in enumerate(cuerpo)
                                 if K["PTR"] in ln), 0)
    out += cuerpo + ["", HL.clip(_accion_primaria(S, K, iw + 1), iw)]
    return [HL.clip(ln, iw) for ln in out]


#: Pasos de solo texto (una sola acción): con poco alto ↑↓ desplazan la caja.
#: Abre siguiendo al botón, como siempre; lo de arriba se alcanza con ↑ (antes
#: la caja solo seguía al botón y el principio quedaba fuera de alcance).
_SOLO_TEXTO = ("bienvenida", "resumen")


def render(S, w, h):
    K = _K()
    v = S["view"]
    palabra = HL.section_word('onboarding')
    t_izq, t_der = _titulos(v)
    if S.get("info"):
        return SB.info_frame(K, w, h, palabra, t_der,
                             [("lines", lambda iw: _VISTAS[v][0](S, K, iw, 2)[1])],
                             state=S["info"], box_w=66)
    sigue = S.get("_desplaza")
    desde = sigue[1] if v in _SOLO_TEXTO and sigue and sigue[0] == v else None
    def caja():
        return SB.frame(K, w, h, palabra, t_izq, lambda iw: _cuerpo_ob(S, K, iw), _chips_ob(S),
                        msg=S.get("msg", ""), cursor_line=lambda: S.get("_cur", 0),
                        scroll=desde, box_w=_OB_BOX_W)
    out = caja()
    if v == "motores" and (SB.frame.last_max_scroll or SB.frame.last_level[1] < 3):
        # la lista de motores no cabe con los botones enteros: se quita el aire
        # entre motores antes de desplazar la caja o de achicar los botones
        # (así la acción, «continuar» y los botones siguen a la vista)
        S["_compacto"] = True
        try:
            out = caja()
        finally:
            S.pop("_compacto", None)
    if v in _SOLO_TEXTO:                          # dónde quedó la caja y su tope
        S["_caja"] = (v, SB.frame.last_start, SB.frame.last_max_scroll)
    return out


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
                      "tu primer agente usará {motor} · guardado ✓").format(
                          motor=primero)
    else:
        S["msg"] = _t("onboarding.msg.default_fail",
                      "no pude guardar el motor ({err}) — sigue igual"
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
    if v in _SOLO_TEXTO and key in ("up", "down"):
        # pasos de solo texto: ↑↓ desplazan la caja, desde donde está
        caja = S.get("_caja") or (v, 0, 0)
        desde, tope = (caja[1], caja[2]) if caja[0] == v else (0, 0)
        S["_desplaza"] = (v, max(0, min(tope, desde + (1 if key == "down" else -1))))
        return True

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
        vis = _visibles(S)
        n = len(vis)
        if key == "up":
            S["mi"] = (S["mi"] - 1) % (n + 1)
        elif key in ("down", "tab"):
            S["mi"] = (S["mi"] + 1) % (n + 1)
        elif key == "\x1b":
            S["view"] = "bienvenida"
        elif key in tuple("123456789") and int(key) <= n:
            S["mi"] = int(key) - 1
            key = " "                            # cae al toggle
        if key in (" ",) and S["mi"] < n:
            eid = vis[S["mi"]]
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
            # B6 (puerta N5): la pista dice «Enter continúa» — y continúa,
            # desde cualquier fila (marcar es con espacio)
            _persistir_motores(S)
            S["hechos"].add("motores")
            S["view"] = "agente"
        return True

    if v == "agente":
        ops = _opciones_agente()
        if key == "up":
            S["ai"] = (S["ai"] - 1) % len(ops)
        elif key in ("down", "tab"):
            S["ai"] = (S["ai"] + 1) % len(ops)
        elif key == "\x1b":                       # atrás: a los motores
            S["view"] = "motores"
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
    # se pintó la bienvenida, no el aviso (si falló al pintarse, ante la duda
    # también cuenta: jamás re-ofrecer en cada arranque una pantalla rota)
    if not S.get("_size_blocked"):
        _visto(S)


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
            try:
                if not msvcrt.kbhit():
                    time.sleep(0.1)
                    _draw(tout, S)
                    continue
                ch = msvcrt.getwch()
            except KeyboardInterrupt:
                ch = "\x03"                       # Ctrl-C en Windows: excepción, no tecla
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


# ── reuso de los flujos existentes (add_agent) ───────────────────────
def _add_agent(opcion):
    """La pantalla REAL «Agregar agente», pre-sembrada en el camino elegido
    (1 crear · 2 cargar · 3 descubrir) — mismo estado, mismos drivers."""
    try:
        import add_agent_tui as A
        S = A._estado_inicial()
        # al terminar (creado, conectado) o con Esc, vuelve AQUÍ y no al menú
        # «Agregar agente» (callejón de la puerta N5: había que salir con q)
        S["volver_al_terminar"] = True
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


def _identidad_desde(nuevos):
    """El onboarding guarda quién eres (sesiones v2, identidad.py): si esta
    máquina todavía no lo sabe, el dueño del agente que acabas de crear o
    cargar (su socio.local, que escribió esa misma pantalla) pasa a ser tu
    identidad en esta máquina, para todos tus cerebros. El genérico «owner»
    no cuenta. Falla-suave: sin esto, la sección Usuarios lo pregunta."""
    try:
        import identidad
        if identidad.persona():
            return ""
        for a in _agentes():
            if a.get("name") not in (nuevos or ()):
                continue
            s = identidad._socio_local(a.get("brain") or "")
            if s and s != identidad._GENERICO:
                return identidad.fijar_persona(s, origen="onboarding")["nombre"]
    except Exception:
        pass
    return ""


# ── entrada ─────────────────────────────────────────────────────────────────
def _estado_inicial():
    harn = _descriptores()
    sel = {e for e in SOPORTADOS if (harn.get(e) or {}).get("binaries_ok")}
    return {"view": "idioma", "li": 0, "mi": 0, "ai": 0,
            "msg": "", "harn": harn, "probe": {}, "probing": False, "sel": sel,
            "hechos": set(), "nuevos": [], "def_engine": "", "salir": None}


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
            "agentes": [a["name"] for a in _agentes()]}


#: Cómo terminó la última corrida: "fin" (✦ ir al hub) · "quit" · "tamano"
#: (q/Esc en el aviso de tamaño: no cuenta, ver run) · "sin_ver" (nunca se
#: pintó: no corrió) · None. front._run_onboarding lo lee para abrir el hub.
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
    previo = _flag_previo()                       # para deshacerlo (ver finally)
    # el flag NO se escribe aquí: se escribe al pintarse la bienvenida sin el
    # aviso de tamaño (_draw → _visto). Quien solo vio el aviso —y salió con
    # q/Esc/Ctrl-C, o cerró la ventana— no deja nada escrito.
    S = _estado_inicial()
    if not _reanudar(S, prev) and _idioma_auto():
        S["view"] = "bienvenida"                  # el idioma ya se sabe: no se pregunta
    _probe_start(S)

    def marca(extra):                             # lo último que ESTA corrida escribió
        S["_flag_mio"] = _marcar(extra)

    try:
        while True:
            token = _pantalla(S)
            if S.get("_size_exit") or not S.get("_visto"):
                break                             # desde el aviso, o sin haberse visto
            marca(_progreso(S))                   # cada salida del driver guarda
            if token == "quit":
                marca(_resumen_flag(S, False))
                break
            if token == "fin":
                marca(_resumen_flag(S, True))
                break
            if token in ("crear", "cargar", "descubrir", "ninguno"):
                if token != "ninguno":
                    antes = {a["name"] for a in _agentes()}
                    _add_agent(token)
                    nuevos = sorted({a["name"] for a in _agentes()} - antes)
                    S["nuevos"] += nuevos
                    _identidad_desde(nuevos)     # quién eres en esta máquina
                if token == "ninguno" or S["nuevos"]:
                    S["hechos"].add("agente")
                else:                            # volvió sin agente: sigue en su paso
                    S["view"], S["salir"] = "agente", None
                    marca(_progreso(S))
                    continue
                if token == "ninguno":           # explorar: omitida, queda pendiente
                    S.setdefault("omitidas", set()).add("agente")
                else:
                    S.get("omitidas", set()).discard("agente")
                marca(_progreso(S))
                S["view"], S["salir"] = "resumen", None
                continue
            break                                 # token desconocido → fuera
    finally:
        if not S.get("_visto"):
            pass                                  # nunca se vio: no se escribe nada
        elif S.get("_size_exit"):
            # la vio, pero salió desde el aviso de tamaño (la ventana dejó de
            # alcanzar): no cuenta como saltada → el flag vuelve a como estaba,
            # salvo que otra corrida lo haya cambiado mientras (gana la otra)
            if leer_flag() == S.get("_flag_mio"):
                _restaurar_flag(previo)
        else:
            marca(_resumen_flag(S, S.get("salir") == "fin"))
        _aplicar_osc()                            # el hub entra ya pintado
        ULTIMA_SALIDA = ("tamano" if S.get("_size_exit") else
                         S.get("salir") if S.get("_visto") else "sin_ver")
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
    if S["view"] not in _VISTAS:                  # p. ej. un paso que ya no existe
        S["view"] = "resumen" if not pend else "bienvenida"
    S["msg"] = _t("onboarding.reanudado", "continuando donde lo dejaste")
    return True


def maybe_run():
    """Trigger de front.py: corre el onboarding SOLO en el primer uso real.
    Devuelve True si corrió (front re-lanza el hub con lo elegido); False
    también si se salió desde el aviso de tamaño o nunca se pintó (no corrió
    de verdad: front sigue al hub aquí mismo — re-lanzarlo la reabriría).
    Guardas: subcomando/--banner · sin TTY · env WORKSPACE_NO_ONBOARDING ·
    flag presente · máquina con agentes (se adopta en silencio)."""
    global ULTIMA_SALIDA
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
        ULTIMA_SALIDA = None
        run(force=True)
        return ULTIMA_SALIDA not in ("tamano", "sin_ver")
    except Exception:
        return False


if __name__ == "__main__":
    # ARCHIVO MÍNIMO por una versión (se borra en la versión 2): esta pantalla ya no se abre. Quien la corre
    # directo, o un hub que quedó abierto durante la actualización, llega a lo nuevo (puertas.redirigir).
    import puertas
    sys.exit(puertas.redirigir('primer_arranque', sys.argv[1:]))
