#!/usr/bin/env python3
"""WORKSPACE · add_agent_tui — la pantalla «Agregar agente» del hub.

REDISEÑO 2 (pedido del socio 2026-10-02, estilo WORKSPACE + transparencia): el
flujo de crear dejó de ser black-box. Antes: formulario → Enter → la pantalla
se CONGELABA mientras agent_admin.create corría en el hilo de la UI, los ✓ de
install.py se imprimían ENCIMA de la pantalla raw (corrupción), y cualquier
WARN se tragaba en silencio. Ahora el flujo es: formulario → PLAN (ves el
cerebro que va a nacer, eliges el harness con sesión, costo honesto, pasos
explícitos) → CREANDO EN VIVO (worker en hilo + pasos ✓/●/✗ + slider del hub)
→ RESULTADO. Y es RESUMIBLE: el job persiste en ~/.claude/workspace/ — salir y
volver re-engancha la vista; si el proceso murió a medias, se ofrece limpiar
los restos o reintentar (jamás un cerebro a medias en silencio).

REDISEÑO 3 (2026-10-02): cargar y descubrir al MISMO nivel que crear.
Antes cargar/descubrir eran black-box: agent_admin.load corría SÍNCRONO en
el hilo de la UI (congelada), los prints de install.py caían ENCIMA del
alt-screen raw (corrupción), los WARN (placeholders del template, config a
medias → doctor) se TRAGABAN con out=_silencio, y discover() escaneaba el
disco en el hilo de la UI escribiendo avisos de colisión a stderr. Ahora:
cargar muestra la RADIOGRAFÍA de la carpeta (identidad, marcas de cerebro,
colisiones) conforme tecleas y conecta EN VIVO (hilo + pasos LOAD_STEPS);
descubrir escanea en 2º plano, distingue nuevo/ya conectado/colisión y
explica cada cerebro; el resultado muestra TODOS los avisos.

Vistas:  menu → crear (formulario) → plan (mapa del cerebro · harness ·
         costo · pasos) → run (EN VIVO) → done (resultado)
         · cargar (ruta + radiografía) · descubrir (scan en 2º plano)
         → lrun (conectando EN VIVO) → listo (resultado con avisos)
         · stale (creación interrumpida detectada al entrar)

El backend es agent_admin.create (pasos CREATE_STEPS reportados por callback)
orquestado por agent_create_job (hilo + persistencia + cancel cooperativo).
Lo invoca front.py como acción loop-back (vuelve al recinto al salir).
Falla-suave: sin TTY → aviso y regreso limpio.

Teclas:  ↑↓ campo/fila · escribir edita · ⌫ borra · Enter avanza
         plan: ↑↓ selecciona · Enter aplica · p IA · s skills · k revisa ·
               Esc vuelve  (el plan pinta costo estimado VS saldo real del
               provider donde es legible — codex vía rollouts, 0 tokens;
               claude vía snapshot de su statusline cuando está disponible)
         run:  q cancela (cooperativo) · Esc vuelve al recinto (sigue en 2º plano)
         cargar: escribe la ruta · Enter conecta · Esc vuelve
         descubrir: ↑↓ elige · Enter conecta · a los nuevos · r re-escanea

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import sys
import datetime
import math
import json
import skill_source_preferences
import agent_create_ui

import io
import os
import re
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import agent_admin                                              # noqa: E402
import agent_create_job                                         # noqa: E402
import agent_skill_sources
import agentsreg                                                # noqa: E402
import hublayout as HL                                          # noqa: E402

# i18n (lado cliente): esta pantalla la ve el cliente. Import guardado con red
# de seguridad inline — si i18n no se puede importar, _t() devuelve el español
# inline (paridad EXACTA con la pantalla de siempre). Ver lang/README.md.
try:
    import i18n                                                 # noqa: E402
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

# El COLOR de marca salió del asistente (el socio 2026-10-02): el color en el hub
# ahora significa ESTADO del agente, no identidad — con muchos agentes el
# arcoíris no escala. agent_admin.create conserva su default neutro («gris»)
# y el flag --color sigue vivo por CLI para quien lo quiera.

# ── el formulario de CREAR: (key, label, default, ayuda, ejemplo) ───────────
# Catálogo FUENTE: protocols/agent-creation/00-INTAKE.md (secciones B·C — el
# intake completo del protocolo de creación). Este formulario es su versión
# rápida: solo «nombre» es obligatorio; TODO lo demás es opcional pero hace
# al agente A SU MEDIDA. Dónde aterriza cada cosa: el dueño en
# STATE/users/<dueño>.md (HOT al boot), el carácter en la semilla del SOUL,
# alcance+límites en BOOT/03-RULES §Scope, y las respuestas crudas COMPLETAS
# en `.workspace/agent.json` → "intake" (portátiles con el cerebro).
GRUPOS_F = (("identidad", ("nombre", "visible")),
            ("carácter", ("rol", "proposito", "tono", "estilo", "idioma")),
            ("alcance", ("alcance", "limites", "ejemplos", "skills")),
            ("dueño", ("dueño", "dueño_quien", "dueño_como",
                       "dueño_necesita")))
FIELDS = {
    "nombre": ("nombre", "",
               "El slug del agente: minúsculas, dígitos, - o _. Es su "
               "comando (`hermes` en la terminal) y el nombre de su cerebro.",
               "ej.  alfa · beta · gamma"),
    "visible": ("visible", "",
                "Cómo se muestra en el hub y sus banners. Vacío = el nombre "
                "capitalizado.", "ej.  Hermes"),
    "rol": ("rol", "",
            "Su rol en una frase — el tagline bajo su nombre en el hub y "
            "el banner.",
            "ej.  copiloto legal de un despacho boutique"),
    "proposito": ("propósito", "",
                  "¿Para qué existe? El trabajo que hace y para quién. "
                  "Entre más concreto, mejor nace la semilla de su alma "
                  "(BOOT/00-SOUL.md).",
                  "ej.  investigar y redactar contratos de arrendamiento"),
    "tono": ("tono", "copiloto híbrido: riguroso y cálido",
             "Su carácter al hablar. Se puede afinar después con la "
             "pantalla Tono.", ""),
    "estilo": ("estilo", "",
               "Reglas concretas de voz: ¿conciso o detallado? ¿formal o "
               "cercano? ¿emojis? ¿va al grano o explica el porqué?",
               "ej.  directo y sin emojis; explica solo si se lo piden"),
    "idioma": ("idioma", "español",
               "El idioma principal en el que trabaja y responde.", ""),
    "alcance": ("alcance", "",
                "Qué SÍ hace — su campo de acción. Aterriza en "
                "BOOT/03-RULES §Scope.",
                "ej.  contratos y normativa MX; nada de litigio"),
    "limites": ("límites", "",
                "Qué NO hace o rechaza, y qué acciones consulta ANTES de "
                "actuar (enviar, borrar, firmar, publicar).",
                "ej.  nunca manda nada a terceros sin aprobación del dueño"),
    "ejemplos": ("ejemplos", "",
                 "2-3 tareas REALES de una semana típica. Anclan el diseño "
                 "a trabajo concreto, no a abstracciones.",
                 "ej.  revisar un contrato y marcar riesgos; redactar un NDA"),
    "skills": ("skills", "generales",
               "Categorías de skills con las que nace (separadas por coma).",
               "ej.  generales, legal, redacción"),
    "dueño": ("dueño", "",
              "Usuario corto del dueño (minúsculas) — crea su perfil y sus "
              "sesiones dentro del cerebro. Opcional.",
              "ej.  uno · dos · tres"),
    "dueño_quien": ("quién es", "",
                    "Quién es el dueño: nombre, a qué se dedica, su nivel "
                    "en el dominio (¿novato o experto?). El agente lo trata "
                    "a su medida desde la primera sesión.",
                    "ej.  abogado sr. — experto en civil, nuevo "
                    "en TI"),
    "dueño_como": ("cómo opera", "",
                   "Cómo trabaja hoy: herramientas, flujo real, y los "
                   "dolores que el agente le debe quitar.",
                   "ej.  todo en Word y mail; pierde horas buscando "
                   "precedentes"),
    "dueño_necesita": ("necesita", "",
                       "Qué espera del agente y qué debe saber de él/ella "
                       "desde el día 1 (contexto, preferencias, "
                       "no-negociables).",
                       "ej.  borradores listos para firma; jamás inventar "
                       "citas"),
}
ORDEN_F = tuple(k for _, ks in GRUPOS_F for k in ks)
ACCION_ROW = len(ORDEN_F)                     # índice virtual: ✦ continuar

#: Campos LARGOS: texto libre de varias líneas (Enter = nueva línea cuando ya
#: hay texto; ↓/Tab avanza). Los demás son cortos de una línea.
ML_FIELDS = frozenset(("skills", "rol", "proposito", "estilo", "alcance", "limites",
                       "ejemplos", "dueño_quien", "dueño_como",
                       "dueño_necesita"))
#: líneas visibles del editor embebido del campo largo ENFOCADO — contrato de
#: altura ACOTADA: por más que crezca el texto, el campo nunca pasa de esto
#: (cola visible: siempre ves dónde escribes; «…» marca que hay más arriba).
_ML_VIS = 3


def _maxlen(key):
    """Tope honesto por campo: los largos aguantan párrafos reales."""
    return 8000 if key == "skills" else (700 if key in ML_FIELDS else 72)

MENU_OPTS = (
    ("crear", "crear agente nuevo",
     ("Un agente desde cero: formulario corto → ves el CEREBRO que va a "
      "nacer y el harness con el que corre → se crea EN VIVO, paso por "
      "paso. Nace autocontenido en ~/Desktop/<NOMBRE> - BRAIN, usable al "
      "terminar.",)),
    ("cargar", "cargar agente existente",
     ("Conecta un cerebro que ya existe (una carpeta): ves QUÉ trae "
      "(identidad, marcas de cerebro, colisiones) antes de conectar, y el "
      "cableado (hooks · statusline · launcher · tema) corre EN VIVO, "
      "paso por paso.",)),
    ("descubrir", "descubrir cerebros en el disco",
     ("Escanea Desktop / Documents / vaults buscando carpetas con "
      ".workspace/agent.json y te deja conectarlas — ves cuáles son nuevas "
      "y cuáles ya están. Acción MANUAL — el harness jamás conecta nada "
      "solo.",)),
)

# ── transparencia: qué significa cada pieza del cerebro ─────────────────────
# El MAPA se deriva del TEMPLATE REAL (agent_admin.BRAIN_TEMPLATE) — los
# conteos son medidos, no inventados. Estas son solo las explicaciones.
_CONCEPTOS = {
    "CLAUDE.md": "punto de entrada: el orden en que arranca",
    "BOOT/": "quién ES — alma · identidad · equipo · reglas · mapa",
    "STATE/": "memoria viva — MEMORY · INDEX · sesiones · inbox",
    "wiki/": "conocimiento on-demand (index + [[wikilinks]])",
    "skills/": "procedimientos reutilizables, por categoría",
    "adapters/": "cómo opera en cada runtime (claude-code, …)",
    ".workspace/": "agent.json — identidad portátil que lee el harness",
    ".claude/": "runtime: hooks · statusline · socio.local",
}
_MAPA_ORDEN = ("CLAUDE.md", "BOOT/", "STATE/", "wiki/", "skills/",
               "adapters/")
_MAPA_CACHE = None

#: Límite de cuenta por harness — HONESTO: lo que de verdad se puede saber
#: desde aquí sin abrir una sesión (y sin gastar tokens). Nada inventado.
#: codex SÍ es legible: sus rollouts locales traen snapshots rate_limits
#: (engines/codex.rate_limit_snapshot) — la caja de costo pinta las barras.
_LIMITES = {
    "claude-code": "límite del plan: no legible fuera de sesión — dentro "
                   "lo muestra /status",
    "codex": "límites 5h y semanal: se leen de tus corridas locales "
             "(0 tokens) — barras abajo al personalizar",
    "gemini": "cuota de la cuenta: se ve al lanzar — no legible desde aquí",
}


def _mapa_cerebro():
    """[(etiqueta, n_docs|None, desc)] del cerebro que se va a crear, derivado
    del template REAL + lo que agrega la configuración (.workspace/.claude).
    Medido una vez por proceso (el template no cambia en caliente)."""
    global _MAPA_CACHE
    if _MAPA_CACHE is not None:
        return _MAPA_CACHE
    conteo = {}
    try:
        root = agent_admin.BRAIN_TEMPLATE
        for t in sorted(os.listdir(root)):
            p = os.path.join(root, t)
            if os.path.isdir(p):
                n = 0
                for _r, _d, fs in os.walk(p):
                    n += sum(1 for f in fs if not f.startswith("."))
                conteo[t + "/"] = n
            elif not t.startswith("."):
                conteo[t] = None
    except Exception:
        pass
    out = []
    for key in _MAPA_ORDEN:                        # conocidos, en orden
        if key in conteo:
            out.append((key, conteo.pop(key), _CONCEPTOS.get(key, "")))
    for key in sorted(conteo):                     # extras del template
        out.append((key, conteo[key], _CONCEPTOS.get(key, "")))
    # lo que agrega la CREACIÓN (no viene del template): identidad + runtime
    out.append((".workspace/", None, _CONCEPTOS[".workspace/"]))
    out.append((".claude/", None, _CONCEPTOS[".claude/"]))
    _MAPA_CACHE = out
    return out


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


def _wrap(txt, w):
    pal, ln, out = str(txt).split(), "", []
    for p in pal:
        if HL.vis(ln) + HL.vis(p) + 1 > w:
            out.append(ln)
            ln = p
        else:
            ln = (ln + " " + p).strip()
    if ln:
        out.append(ln)
    return out or [""]


def _divisor(K, txt, w, tono=-1):
    """`titulo ────` — el encabezado de sección del Tono."""
    col = (K["WCOL"][tono % len(K["WCOL"])] + K["BO"]) if tono >= 0 \
        else K["DK"]
    regla = K["SEP"] * max(1, w - HL.vis(txt) - 2)
    return HL.clip("%s%s%s %s%s%s" % (col, str(txt), K["R"], K["DK"], regla,
                                      K["R"]), w)


def _valida_nombre(v):
    """(estado, texto) del nombre EN VIVO: '' → neutro · ok → disponible ·
    bad → por qué no."""
    v = (v or "").strip().lower()
    if not v:
        return ("", _t("addagent.ui.name.empty", "escribe el nombre — es el único campo obligatorio"))
    if not agentsreg.is_valid_name(v):
        return ("bad", _t("addagent.ui.name.invalid", "inválido: solo minúsculas, dígitos, - o _"))
    try:
        if agentsreg.find(v) or agent_admin.dispatch.find_agent(v):
            return ("bad", _t("addagent.ui.name.taken", "ya existe un agente «%s» — elige otro") % v)
    except Exception:
        pass
    try:
        if os.path.exists(agent_admin.default_brain_dest(v)):
            return ("bad", _t("addagent.ui.name.folder_exists", "la carpeta ~/Desktop/%s - BRAIN ya existe")
                    % v.upper())
    except Exception:
        pass
    return ("ok", _t("addagent.ui.name.available", "disponible — su cerebro: ~/Desktop/%s - BRAIN") % v.upper())


def _mmss(secs):
    secs = max(0, int(secs))
    return "%d:%02d" % (secs // 60, secs % 60)


# ── harnesses: probe EN 2º PLANO (codex login status puede tardar) ──────────
def _lanza_probe(S):
    """Describe los harnesses CON sesión verificada (probe) en un hilo —
    la pantalla jamás se congela esperando un `codex login status`."""
    if (S.get("harn") or {}).get("state") in ("busy", "done"):
        return
    S["harn"] = {"state": "busy", "list": []}

    def _w():
        lst = []
        try:
            import harnesses
            import dispatch
            for i in harnesses.installed():
                if i == "stub":          # motor interno de pruebas — no es
                    continue             # una opción real para un agente
                d = harnesses.describe(i, probe=True)
                try:
                    mod = dispatch.load_engine(i)
                    d["probed"] = bool(hasattr(mod, "status")
                                       or hasattr(mod, "available"))
                except Exception:
                    d["probed"] = False
                lst.append(d)
        except Exception:
            pass
        S["harn"] = {"state": "done", "list": lst}
        # default honesto: el primer harness LISTO (claude-code va primero)
        if S.get("engine_id") is None:
            listos = [d["id"] for d in lst if d.get("ready")]
            S["engine_id"] = listos[0] if listos else "claude-code"

    threading.Thread(target=_w, daemon=True).start()


def _harn_elegibles(S):
    """Ids con sesión/binario LISTOS (elegibles con ◄►)."""
    return [d["id"] for d in (S.get("harn") or {}).get("list", [])
            if d.get("ready")]


def _harn_estado_txt(K, d):
    """(color, texto) honesto del estado de UN harness."""
    if not d.get("installed"):
        return K["DK"], _t("addagent.ui.engine.not_installed", "no instalado")
    if not d.get("binaries_ok"):
        return K["BAD"], "✗ " + (d.get("detail") or _t("addagent.ui.engine.missing_binary", "falta su binario"))
    if d.get("ready") and d.get("probed"):
        return K["OK"], _t("addagent.ui.engine.session_active", "sesión activa ✓")
    if d.get("ready"):
        return K["GREY"], _t("addagent.ui.engine.binary_ok", "binario ✓ · sesión se valida al lanzar")
    return K["BAD"], "✗ " + (d.get("detail") or _t("addagent.ui.engine.no_session", "sin sesión"))


# ── personalizar con el modelo (opt-in) — disponibilidad del backend ─────────
def _perso_disp(S):
    """(disponible, nota) de la pasada de personalización PARA el harness
    elegido en el plan. Cacheado por engine: pick_backend solo consulta el
    registro de headless.py (no lanza procesos — barato para cada render).
    `nota` = el porqué cuando NO hay backend (honesto, se muestra tal cual)
    o el matiz cuando SÍ (ej. codex corre en sandbox read-only)."""
    eng = (S.get("engine_id") or "claude-code").strip().lower()
    cache = S.setdefault("pbk", {})
    if eng not in cache:
        try:
            import agent_personalize
            b, _tools, nota = agent_personalize.pick_backend(eng)
            cache[eng] = (b is not None, nota or "")
        except Exception as e:           # módulo amputado → toggle apagado
            cache[eng] = (False, _t("addagent.ui.perso.unavailable", "pasada no disponible: %s") % e)
    return cache[eng]


def _fmt_ktok(n):
    """6300 → «6.3k» (mismo formato que agent_personalize)."""
    return ("%.1fk" % (n / 1000.0)) if n >= 1000 else str(n)


# ── saldo del provider (0 tokens) — costo estimado VS lo que tienes ──────────
#: Umbrales del semáforo, en % LIBRE de la ventana más apretada. La pasada es
#: diminuta (~6.3k tok) frente a una ventana de 5h/semana: verde casi siempre;
#: solo se bloquea cuando la ventana está de verdad AGOTADA (no un bloqueo
#: inventado — el dato es el used_percent real de la cuenta).
_SALDO_JUSTO = 10.0            # < 10% libre → amarillo: vas justo
_SALDO_SIN = 0.0               # solo agotamiento real permite bloqueo


def _lanza_saldo(S):
    """Lecturas locales de Codex, Claude y Antigravity, sin llamadas a modelos."""
    if (S.get("saldo") or {}).get("state") in ("busy", "done"):
        return
    S["saldo"] = {"state": "busy", "codex": None}

    def _w():
        snap = None
        try:
            import dispatch
            mod = dispatch.load_engine("codex")
            snap = mod.rate_limit_snapshot()
        except Exception:
            snap = None
        claude = None
        try:
            from pathlib import Path
            usage = json.loads((Path.home() / ".claude/workspace/usage.json").read_text())
            def reset(value):
                if isinstance(value, (int, float)):
                    return value
                return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() if value else None
            claude = {"at": usage.get("stamped"), "primary": {"used_percent": usage.get("five_hour_pct"), "resets_at": reset(usage.get("five_hour_resets_at"))},
                      "secondary": {"used_percent": usage.get("seven_day_pct"), "resets_at": reset(usage.get("seven_day_resets_at"))}}
        except (OSError, ValueError, TypeError):
            pass
        import antigravity_usage
        agy = antigravity_usage.read_snapshot()
        S["saldo"] = {"state": "done", "codex": snap, "claude-code": claude, "antigravity": agy}

    threading.Thread(target=_w, daemon=True).start()


def _edad_txt(secs):
    secs = max(0, int(secs))
    if secs < 90:
        return _t("common.ago.min", "hace {n}m").format(n=1)
    if secs < 3600:
        return _t("common.ago.min", "hace {n}m").format(n=secs // 60)
    if secs < 86400:
        return _t("common.ago.hour", "hace {n}h").format(n=secs // 3600)
    return _t("common.ago.day", "hace {n}d").format(n=secs // 86400)


def _saldo_eval(S):
    """Solo lecturas vigentes: un reset vencido exige lectura nueva.\n    Una lectura antigua informa pero no bloquea la creación."""
    sal = S.get("saldo") or {}
    snap = sal.get(S.get("engine_id") or "claude-code")
    if sal.get("state") != "done" or not snap:
        return None
    now = time.time()
    try:
        age = now - float(snap.get("at") or 0)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(age) or age < -60 or age > 86400:
        return None
    vent, peor, reset_peor = [], 100.0, ""
    windows = [(lbl, snap.get(key) or {}, fmt) for key,lbl,fmt in (("primary", _t("addagent.ui.saldo.window.5h", "5 horas"), "%H:%M"), ("secondary", _t("addagent.ui.saldo.window.week", "semana"), "%d/%m %H:%M"))]
    if S.get("engine_id") == "antigravity":
        windows = [(w.get("label", _t("addagent.ui.saldo.window.model", "modelo")), w, "%d/%m %H:%M") for w in snap.get("buckets", []) if isinstance(w,dict)]
    for lbl, window, fmt in windows:
        try:
            used = float(window.get("used_percent"))
            resets = float(window.get("resets_at") or 0)
        except (ValueError, TypeError):
            continue
        if not math.isfinite(used) or not 0 <= used <= 100 or not math.isfinite(resets) or resets < 0 or resets > 100_000_000_000:
            continue
        if resets and resets <= now:
            continue
        free = 100 - used
        reset_txt = time.strftime(fmt, time.localtime(resets)) if resets else ""
        vent.append((lbl, free, reset_txt, False))
        if free < peor:
            peor, reset_peor = free, reset_txt
    if not vent:
        return None
    stale = age > 900
    verdict = "sin" if peor == 0 and not stale and S.get("engine_id") != "antigravity" else ("justo" if peor < _SALDO_JUSTO else "ok")
    return {"vent": vent, "verdict": verdict, "edad": _edad_txt(age),
            "stale": stale, "plan": snap.get("plan_type") or "", "reset": reset_peor}


def _barra_saldo(K, libre, ancho, col):
    """`━━━●────` — lo LIBRE de la ventana en el lenguaje del slider del hub
    (recorrido coloreado = lo que te queda · ─ = lo ya consumido). No es una
    barra `█░`: es el MISMO vocabulario que el resto del recinto."""
    ancho = max(5, int(ancho))
    v = max(1, min(ancho, 1 + int((ancho - 1) * libre / 100.0)))
    return "%s%s%s●%s%s%s%s" % (col, K["BO"], "━" * (v - 1), K["R"],
                                K["DK"], "─" * (ancho - v), K["R"])


# ── job de CARGA (load) EN VIVO — cargar y descubrir comparten esto ──────────
# Mismo patrón que la creación (worker en hilo + pasos estructurados + stdio
# capturado), sin persistencia: load() es idempotente y no crea carpetas — si
# el proceso muere a medias, NO quedan restos (el registro es atómico y
# `workspace doctor` completa el cableado). Antes esto corría SÍNCRONO en el
# hilo de la UI: la pantalla se congelaba y los ✓/⚠ de install.py se
# imprimían ENCIMA del alt-screen raw (corrupción) — el mismo bug que la
# creación ya había matado.
#: UN capturador de stdio a la vez (scan y load serializados): dos workers
#: capturando/restaurando sys.stdout en paralelo pueden restaurar en el
#: orden equivocado y dejar un StringIO muerto como stdout del hub.
_STDIO_LOCK = threading.Lock()


def _ljob_steps_single():
    return [{"key": k, "label": lbl, "st": "pend", "note": ""}
            for k, lbl in agent_admin.LOAD_STEPS]


def _ljob_start(S, items, origen):
    """Arranca la carga en un hilo daemon. items = [(name, carpeta)]; 1 solo
    = pasos LOAD_STEPS reales; varios (descubrir · a) = un paso por cerebro.
    `origen` = vista a la que vuelve el resultado (menu/cargar/descubrir)."""
    if S.get("ljob") and not S["ljob"].get("done"):
        S["msg"] = _t("addagent.ui.msg.load_in_progress", "ya hay una carga en curso — un momento")
        return
    cj = agent_create_job.active()
    if cj and not cj.get("done"):        # ambos capturan stdio — uno a la vez
        S["msg"] = _t("addagent.ui.msg.create_in_progress", "hay una creación en curso — espera a que termine")
        return
    bulk = len(items) > 1
    if bulk:
        steps = [{"key": n, "label": "%s  %s" % (n, _ruta_corta(c)),
                  "st": "pend", "note": ""} for n, c in items]
    else:
        steps = _ljob_steps_single()
    job = {"items": list(items), "bulk": bulk, "steps": steps, "live": [],
           "warns": [], "res_map": {}, "done": False, "ok": False,
           "error": "", "res": "", "origen": origen,
           "t0": time.monotonic(), "t1": None}
    S["ljob"] = job
    S["view"], S["msg"] = "lrun", ""
    threading.Thread(target=_ljob_worker, args=(job,), daemon=True).start()


def _ljob_worker(job):
    """Corre agent_admin.load con pasos en vivo. Captura stdio GLOBAL
    (install.py imprime con say/ok → rompería la pantalla raw; discover ya
    no corre aquí pero load también escribe) y lo restaura SIEMPRE."""
    def _out(*a, **_k):
        txt = " ".join(str(x) for x in a)
        if "WARN" in txt:
            job["warns"].append(txt.split("WARN:", 1)[-1].strip())

    def _on_step(key, st, note=""):
        for s in job["steps"]:
            if s["key"] == key:
                s["st"], s["note"] = st, str(note or "")
                break
        if st in ("ok", "warn", "fail", "skip"):
            lbl = next((s["label"] for s in job["steps"]
                        if s["key"] == key), key)
            job["live"].append((st, lbl + ((" — " + str(note))
                                           if note else "")))
            del job["live"][:-60]

    _STDIO_LOCK.acquire()
    old = (sys.stdout, sys.stderr, sys.stdin)
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    sys.stdin = io.StringIO("")
    try:
        if job["bulk"]:
            oks = 0
            for s in job["steps"]:
                name, folder = s["key"], ""
                for n, c in job["items"]:
                    if n == name:
                        folder = c
                        break
                s["st"] = "run"
                try:
                    ok, res = agent_admin.load(folder, out=_out)
                except Exception as e:
                    ok, res = False, "%s: %s" % (type(e).__name__, e)
                s["st"] = "ok" if ok else "fail"
                s["note"] = "" if ok else str(res)
                job["res_map"][name] = "ok" if ok else ("err:%s" % res)
                job["live"].append((s["st"], name + ("" if ok
                                                     else " — %s" % res)))
                oks += 1 if ok else 0
            job["ok"] = (oks == len(job["steps"]))
            job["res"] = "%d/%d" % (oks, len(job["steps"]))
        else:
            name, folder = job["items"][0]
            try:
                ok, res = agent_admin.load(folder, out=_out,
                                           progress=_on_step)
            except Exception as e:
                ok, res = False, "%s: %s" % (type(e).__name__, e)
            job["ok"] = bool(ok)
            job["res"] = str(res)
            if not ok:
                job["error"] = str(res)
            job["res_map"][res if ok else name] = \
                "ok" if ok else ("err:%s" % res)
    finally:
        try:
            sys.stdout, sys.stderr, sys.stdin = old
        except Exception:
            pass
        _STDIO_LOCK.release()
        for s in job["steps"]:                    # nada se queda "corriendo"
            if s["st"] in ("pend", "run"):
                s["st"] = "skip"
        job["t1"] = time.monotonic()
        job["done"] = True


# ── radiografía EN VIVO de la carpeta tecleada (cargar) ──────────────────────
def _insp(S):
    """inspect_brain de la ruta actual, cacheado por texto (solo stat + un
    json — barato, pero no hay que repetirlo en cada tick idle)."""
    ruta = S["ruta"].strip()
    cache = S.get("insp") or {}
    if cache.get("ruta") == ruta and cache.get("info") is not None:
        return cache["info"]
    try:
        info = agent_admin.inspect_brain(ruta)
    except Exception:
        info = {"folder": ruta, "exists": False, "estado": "", "marcas": [],
                "has_def": False, "name": "", "display": "", "tagline": "",
                "engine": "", "owner": "", "cargado_de": ""}
    S["insp"] = {"ruta": ruta, "info": info}
    return info


def _ruta_corta(p):
    """~/… en vez de /Users/…/… (las rutas largas ahogan las cajas)."""
    try:
        home = os.path.expanduser("~")
        if p.startswith(home):
            return "~" + p[len(home):]
    except Exception:
        pass
    return p


# ── escaneo de DESCUBRIR en 2º plano ─────────────────────────────────────────
_SCAN_DONDE = ("vaults de Obsidian (obsidian.json)", "~/Desktop",
               "~/Documents", "~/Documents/Obsidian · ~/Obsidian")


def _lanza_scan(S):
    """agentsreg.discover() en un hilo: el listdir de Desktop/Documents puede
    tardar (discos de red) y además discover escribe AVISOS de colisión a
    stderr — capturados aquí y mostrados en la UI (antes se imprimían encima
    del alt-screen raw)."""
    if (S.get("scan") or {}).get("state") == "busy":
        return
    S["scan"] = {"state": "busy", "avisos": [], "reg": {}}
    S["found"], S["estados"], S["di"] = [], {}, 0

    def _w():
        avisos, found = [], []
        _STDIO_LOCK.acquire()
        old = (sys.stdout, sys.stderr, sys.stdin)
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        sys.stdin = io.StringIO("")
        try:
            found = agentsreg.discover() or []
        except Exception:
            found = []
        finally:
            try:
                errtxt = sys.stderr.getvalue()
            except Exception:
                errtxt = ""
            try:
                sys.stdout, sys.stderr, sys.stdin = old
            except Exception:
                pass
            _STDIO_LOCK.release()
        for ln in errtxt.splitlines():
            ln = ln.strip()
            if ln:
                avisos.append(ln.replace("WORKSPACE · aviso: ", ""))
        reg, estados = {}, {}
        try:
            reg = {a["name"]: a["brain"] for a in agentsreg.agents()}
        except Exception:
            pass
        for a in found:
            n = a["name"]
            if n not in reg:
                estados[n] = "nuevo"
            elif os.path.realpath(reg[n]) == os.path.realpath(a["brain"]):
                estados[n] = "cargado"
            else:
                estados[n] = "otro"
        S["found"], S["estados"] = found, estados
        S["scan"] = {"state": "done", "avisos": avisos, "reg": reg}
        S["buscado"] = True

    threading.Thread(target=_w, daemon=True).start()


# ── cuerpos por vista ───────────────────────────────────────────────────────
def _b_menu(S, K, iw):
    wc = K["WCOL"]
    out = []
    for i, (_tok, lbl, _d) in enumerate(MENU_OPTS):
        sel = (i == S["mi"])
        cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
        col = (wc[i % len(wc)] + K["BO"]) if sel else K["INACTIVE"]
        out.append(HL.clip(" %s %s%d%s %s%s%s" % (
            cur, (K["WH"] + K["BO"]) if sel else K["DK"], i + 1, K["R"],
            col, _t("addagent.ui.menuopt.%s.label" % _tok, lbl), K["R"]), iw))
    job = agent_create_job.active()
    if job and not job.get("done"):      # creación EN CURSO (2º plano)
        hechos = sum(1 for s in job["steps"]
                     if s["st"] not in ("pend", "run"))
        out.append("")
        out.append(HL.clip((" %s●%s %s" + _t("addagent.ui.menu.creating_bg", "creando «%s» — paso %d/%d · 1 la muestra") + "%s")
                           % (K["C"] + K["BO"], K["R"], K["GREY"],
                              job["name"], hechos, len(job["steps"]),
                              K["R"]), iw))
    lj = S.get("ljob")
    if lj and not lj.get("done"):        # conexión EN CURSO (2º plano)
        hechos = sum(1 for s in lj["steps"]
                     if s["st"] not in ("pend", "run"))
        out.append("")
        out.append(HL.clip((" %s●%s %s" + _t("addagent.ui.menu.connecting_bg", "conectando — paso %d/%d · avisa al terminar") + "%s")
                           % (K["C"] + K["BO"], K["R"], K["GREY"], hechos,
                              len(lj["steps"]), K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.menu.on_this_machine", "en esta máquina"), iw))
    ags = sorted(a["name"] for a in agentsreg.agents())
    if ags:
        out.append(HL.clip((" %s" + _t("addagent.ui.menu.agents_count", "%d agente(s):") + "%s %s%s%s") % (
            K["DIM"], len(ags), K["R"], K["GREY"], " · ".join(ags), K["R"]),
            iw))
    else:
        out.append(HL.clip(" %s%s%s"
                           % (K["DK"], _t("addagent.ui.menu.no_agents", "sin agentes aún — crea o carga el primero"), K["R"]), iw))
    return out


def _b_menu_det(S, K, iw):
    _tok, lbl, desc = MENU_OPTS[S["mi"]]
    out = []
    for ln in (_t("addagent.ui.menuopt.%s.desc" % _tok, d) for d in desc):
        for sub in _wrap(ln, max(8, iw - 3)):
            out.append(HL.clip(" %s%s%s" % (K["GREY"], sub, K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.howitworks", "cómo funciona"), iw, tono=4))
    for ln in (_t("addagent.ui.menu.how.1", "todo queda en TU máquina (registro per-máquina)"),
               _t("addagent.ui.menu.how.2", "nada se comparte ni se sube a ningún lado"),
               _t("addagent.ui.menu.how.3", "quitar un agente: workspace config · agentes")):
        for sub in _wrap(ln, max(8, iw - 4)):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  sub, K["R"]), iw))
    return out


def _val_lineas(val, w):
    """Líneas visibles de un valor largo: respeta los \\n del texto y
    envuelve cada párrafo a `w` (párrafo vacío = línea en blanco)."""
    out = []
    for par in (val or "").split("\n"):
        out.extend(_wrap(par, w) if par.strip() else [""])
    return out or [""]


def _fila_campo(S, K, iw, key, idx):
    """Las filas de UN campo (lista de líneas). Campo corto — o largo SIN
    foco — es una línea: cursor · label · valor (o placeholder; «⏎» marca
    saltos de línea que no se ven). El campo LARGO enfocado se expande a su
    editor embebido: ≤ _ML_VIS líneas con wrapping y COLA visible (siempre
    ves dónde escribes; «…» = hay más texto arriba). Altura acotada."""
    sel = (idx == S["fi"])
    label, default, _hint, ej = FIELDS[key]
    label = _t("addagent.ui.field.%s.label" % key, label)
    default = _t("addagent.ui.field.%s.default" % key, default) if default else default
    ej = _t("addagent.ui.field.%s.ej" % key, ej) if ej else ej
    val = S["vals"].get(key, "")
    cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
    lcol = (K["WH"] + K["BO"]) if sel else (K["GREY"] if val else K["DK"])
    lab = "%s%s%s" % (lcol, HL.pad(label, 10), K["R"])
    caret = ("%s█%s" % (K["C"] + K["BO"], K["R"])) if sel else ""
    vw = max(10, iw - 16)                        # ancho útil del valor
    # ── editor embebido: largo + enfocado + con texto ──
    if sel and key in ML_FIELDS and val:
        lineas = _val_lineas(val, vw)
        vis = lineas[-_ML_VIS:]
        if len(lineas) > _ML_VIS:
            vis[0] = "…" + vis[0][1:] if vis[0] else "…"
        out = []
        for i, ln in enumerate(vis):
            pre = (" %s %s " % (cur, lab)) if i == 0 else " " * 14
            tail = caret if i == len(vis) - 1 else ""
            out.append(HL.clip(pre + "%s%s%s%s" % (K["WH"], ln, K["R"],
                                                   tail), iw))
        return out
    # ── una línea ──
    if val:
        plano = val.replace("\n", " ⏎ ")
        if sel and len(plano) > vw:              # cola visible al editar
            plano = "…" + plano[-(vw - 1):]
        v = "%s%s%s%s" % (K["WH"] if sel else K["GREY"], plano, K["R"],
                          caret)
    elif default:
        v = "%s%s%s%s" % (K["DIM"], default, K["R"],
                          (" " + caret) if sel else "")
    else:
        v = "%s%s%s%s" % (K["DK"], ej or "—", K["R"],
                          (" " + caret) if sel else "")
    return [HL.clip(" %s %s %s" % (cur, lab, v), iw)]


def _b_crear(S, K, iw, grupos=True, max_h=None):
    """El formulario. `max_h` acota la caja: si los 15 campos del intake no
    caben, se abre una VENTANA deslizante centrada en el campo enfocado con
    marcadores «… n más arriba/abajo» — el pie y la acción jamás se pierden,
    y la altura del bloque queda ESTABLE mientras navegas."""
    filas, idx = [], 0     # [(tag, línea)] tag: nº de campo · -1 acción · None decor
    if grupos:
        for n, (titulo, claves) in enumerate(GRUPOS_F):
            if n:
                filas.append((None, ""))
            filas.append((None, _divisor(K, _t("addagent.ui.group.%s" % titulo, titulo), iw)))
            for k in claves:
                for ln in _fila_campo(S, K, iw, k, idx):
                    filas.append((idx, ln))
                idx += 1
    else:
        for k in ORDEN_F:
            for ln in _fila_campo(S, K, iw, k, idx):
                filas.append((idx, ln))
            idx += 1
    filas.append((None, ""))
    sel = (S["fi"] == ACCION_ROW)
    cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
    acol = (K["C"] + K["BO"]) if sel else K["B2"]
    filas.append((-1, HL.clip((" %s %s" + _t("addagent.ui.form.continue", "✦ continuar — revisar y crear") + "%s%s") % (
        cur, acol, K["R"],
        ("  %s" + _t("addagent.ui.form.enter_paren", "(Enter)") + "%s") % (K["DIM"], K["R"]) if sel else ""), iw)))
    if max_h is None or len(filas) <= max_h:
        return [ln for _t, ln in filas]
    # ── ventana deslizante (altura EXACTA max_h: marcador + vis + marcador) ──
    foco = S["fi"] if S["fi"] < ACCION_ROW else -1
    pos = [i for i, (t, _l) in enumerate(filas) if t == foco]
    centro = (pos[0] + pos[-1]) // 2 if pos else 0
    vis = max(4, max_h - 2)
    ini = max(0, min(centro - vis // 2, len(filas) - vis))
    fin = ini + vis
    arriba = len({t for t, _l in filas[:ini]
                  if isinstance(t, int) and t >= 0})
    abajo = len({t for t, _l in filas[fin:]
                 if isinstance(t, int) and t >= 0})
    out = [HL.clip((" %s" + _t("addagent.ui.form.more_above", "… %d campo(s) más arriba") + "%s")
                   % (K["DK"], arriba, K["R"]), iw) if ini > 0 else ""]
    out += [ln for _tg, ln in filas[ini:fin]]
    out.append(HL.clip((" %s" + _t("addagent.ui.form.more_below", "… %d campo(s) abajo · ✦ continuar al final") + "%s")
                       % (K["DK"], abajo, K["R"]), iw)
               if fin < len(filas) else "")
    return out


def _b_crear_det(S, K, iw, full=2):
    """Panel derecho del formulario: EL CAMPO enfocado explicado (y el
    nombre validado EN VIVO), o el resumen si el cursor está en CONTINUAR."""
    out = []
    if S["fi"] == ACCION_ROW:
        nombre = S["vals"].get("nombre", "").strip().lower()
        est, txt = _valida_nombre(nombre)
        out.append(HL.clip(" %s%s%s" % (K["DIM"], _t("addagent.ui.form.continue_preview", "al continuar verás el plan completo ANTES de crear:"), K["R"]), iw))
        out.append("")
        for k in ORDEN_F:
            label, default, _h, _e = FIELDS[k]
            label = _t("addagent.ui.field.%s.label" % k, label)
            default = _t("addagent.ui.field.%s.default" % k, default) if default else default
            v = S["vals"].get(k, "") or default or "—"
            lineas = _val_lineas(v, 200)         # preview = primera línea
            v1 = lineas[0] + (" ⋯" if len(lineas) > 1 else "")
            out.append(HL.clip("   %s%s%s %s%s%s" % (
                K["DK"], HL.pad(label, 10), K["R"],
                K["GREY"] if v != "—" else K["DK"], v1, K["R"]), iw))
        out.append("")
        col = K["OK"] if est == "ok" else (K["BAD"] if est == "bad"
                                           else K["DIM"])
        for sub in _wrap(txt, max(8, iw - 3)):
            out.append(HL.clip(" %s%s%s" % (col, sub, K["R"]), iw))
        return out
    key = ORDEN_F[S["fi"]]
    label, default, hint, ej = FIELDS[key]
    label = _t("addagent.ui.field.%s.label" % key, label)
    default = _t("addagent.ui.field.%s.default" % key, default) if default else default
    hint = _t("addagent.ui.field.%s.hint" % key, hint)
    ej = _t("addagent.ui.field.%s.ej" % key, ej) if ej else ej
    out.append(HL.clip((" %s%s%s%s") % (K["WH"] + K["BO"], label, K["R"],
                       ("  %s" + _t("addagent.ui.form.optional", "opcional") + "%s") % (K["DK"], K["R"])
                       if key != "nombre" else ""), iw))
    out.append("")
    for sub in _wrap(hint, max(8, iw - 3)):
        out.append(HL.clip(" %s%s%s" % (K["GREY"], sub, K["R"]), iw))
    if ej:
        for sub in _wrap(ej, max(8, iw - 3)):
            out.append(HL.clip(" %s%s%s" % (K["DK"], sub, K["R"]), iw))
    if key in ML_FIELDS:
        out.append(HL.clip(" %s%s%s" % (K["DIM"], _t("addagent.ui.form.freetext", "texto libre — Enter = nueva línea · ↓/Tab sigue"), K["R"]), iw))
    if key == "nombre":
        est, txt = _valida_nombre(S["vals"].get("nombre", ""))
        col = K["OK"] if est == "ok" else (K["BAD"] if est == "bad"
                                           else K["DIM"])
        out.append("")
        for sub in _wrap(txt, max(8, iw - 3)):
            out.append(HL.clip(" %s%s%s" % (col, sub, K["R"]), iw))
    elif default:
        out.append("")
        out.append(HL.clip((" %s" + _t("addagent.ui.form.empty_default", "vacío = «%s»") + "%s") % (K["DIM"], default, K["R"]),
                           iw))
    # ── lo que llevas: el texto COMPLETO del campo enfocado, envuelto —
    #    aquí se LEE entero aunque el editor embebido solo muestre la cola ──
    val = S["vals"].get(key, "")
    if val and full >= 1:
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.form.sofar", "lo que llevas"), iw, tono=2))
        lineas = _val_lineas(val, max(8, iw - 3))
        tope = 8 if full >= 2 else 4
        for ln in lineas[:tope]:
            out.append(HL.clip(" %s%s%s" % (K["GREY"], ln, K["R"]), iw))
        if len(lineas) > tope:
            out.append(HL.clip((" %s" + _t("addagent.ui.form.more_lines", "… %d línea(s) más") + "%s")
                               % (K["DK"], len(lineas) - tope, K["R"]), iw))
    if full < 1:
        return out
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.form.whatsnext", "qué sigue"), iw, tono=3))
    for ln in (_t("addagent.ui.form.next.1", "nada se crea aún: primero el PLAN (mapa del cerebro, harness, costo y pasos) y ahí confirmas"),
               _t("addagent.ui.form.next.2", "solo «nombre» es obligatorio — lo demás hace al agente a la medida y se puede afinar después")):
        for sub in _wrap(ln, max(8, iw - 4)):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  sub, K["R"]), iw))
    return out


# ── vista PLAN: el cerebro que nace · harness · costo · pasos ───────────────
def _b_plan_mapa(S, K, iw, full=2):
    """Caja izquierda del plan: EL CEREBRO QUE VA A NACER — mapa real
    derivado del template (conteos medidos) + qué es cada concepto."""
    nombre = S["vals"].get("nombre", "").strip().lower()
    out = [HL.clip((" %s" + _t("addagent.ui.plan.dest", "destino:") + "%s %s~/Desktop/%s - BRAIN%s")
                   % (K["DIM"], K["R"], K["WH"], nombre.upper(), K["R"]),
                   iw), ""]
    out.append(_divisor(K, _t("addagent.ui.plan.brain_format", "el formato del cerebro"), iw, tono=1))
    mapa = _mapa_cerebro()
    for i, (etiqueta, n, desc) in enumerate(mapa):
        desc = _t("addagent.ui.concept." + etiqueta.strip("/.").replace(".", "_").lower(), desc)
        agrega = etiqueta in (".workspace/", ".claude/")
        if agrega and full >= 1 and i and not mapa[i - 1][0].startswith("."):
            out.append(_divisor(K, _t("addagent.ui.plan.added_on_create", "se agrega al crear"), iw))
        ncol = K["GREY"] if not agrega else K["DIM"]
        cnt = ("·%d" % n) if n else ""
        pre = " %s%s%s %s%s%s " % (ncol, HL.pad(etiqueta, 10), K["R"],
                                   K["DK"], HL.pad(cnt, 3), K["R"])
        if full >= 1:
            dw = max(10, iw - 17)                 # col de descripción
            lineas = _wrap(desc, dw)[:2 if full >= 2 else 1]
            out.append(HL.clip(pre + "%s%s%s" % (K["DK"], lineas[0],
                                                 K["R"]), iw))
            for sub in lineas[1:]:                # sangría colgante
                out.append(HL.clip(" " * 16 + "%s%s%s"
                                   % (K["DK"], sub, K["R"]), iw))
        else:
            out.append(HL.clip(pre, iw))
    if full >= 2:
        out.append("")
        lineas = _wrap(_t("addagent.ui.plan.selfcontained", "autocontenido: identidad, memoria y skills viajan en la carpeta — portátil entre máquinas"),
                       max(8, iw - 4))
        out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                              lineas[0], K["R"]), iw))
        for sub in lineas[1:]:                    # sangría colgante
            out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    return out


def _b_plan_der(S, K, iw, full=2):
    """Caja derecha del plan: harness (elegible entre los CON sesión) +
    costo honesto + los pasos explícitos de la creación."""
    out = [_divisor(K, _t("addagent.ui.plan.harness_title", "harness — quién lo corre"), iw, tono=2)]
    harn = S.get("harn") or {}
    if harn.get("state") != "done":
        out.append(HL.clip((" %s●%s %s" + _t("addagent.ui.plan.verifying_sessions", "verificando sesiones de los harnesses…") + "%s")
                           % (K["WCOL"][int(time.monotonic() * 6) % 6],
                              K["R"], K["DIM"], K["R"]), iw))
    else:
        lst = harn.get("list", [])
        eleg = _harn_elegibles(S)
        for d in lst:
            sel = (d["id"] == S.get("engine_id"))
            cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) \
                if sel else " "
            mark = ("%s●%s" % (K["C"] + K["BO"], K["R"])) if sel \
                else ("%s○%s" % (K["DK"], K["R"]))
            ncol = (K["WH"] + K["BO"]) if sel \
                else (K["GREY"] if d["id"] in eleg else K["DK"])
            ecol, etxt = _harn_estado_txt(K, d)
            out.append(HL.clip(" %s %s %s%s%s %s%s%s" % (
                cur, mark, ncol, HL.pad(d["id"], 12), K["R"],
                ecol, etxt, K["R"]), iw))
        if not lst:
            out.append(HL.clip(" %s%s%s" % (K["DK"], _t("addagent.ui.plan.no_harnesses", "no pude leer los harnesses — se crea con claude-code"), K["R"]), iw))
        elif not eleg:
            for sub in _wrap(_t("addagent.ui.plan.no_session", "ninguno tiene sesión verificada — se crea igual y el login se hace al lanzar"), iw - 3):
                out.append(HL.clip(" %s%s%s" % (K["B"], sub, K["R"]), iw))
        if full >= 1 and eleg:
            out.append(HL.clip(" %s%s%s" % (K["DK"], _t("addagent.ui.plan.switch_engine", "◄► cambia · el agente nace con el marcado"), K["R"]), iw))
    source = S.get("sourcing") or {}
    enabled = S.get("source_skills", True)
    status = _t("addagent.ui.plan.searching", "buscando") if source.get("state") == "busy" else (_t("addagent.ui.plan.n_chosen", "%d elegidas") % len(S.get("skill_selected", [])))
    out.append(HL.clip((" %s" + _t("addagent.ui.plan.official_skills", "skills oficiales: %s · %s") + "%s") %
                       (K["C"], "ON" if enabled else "OFF", status, K["R"]), iw))
    out.append(HL.clip(" %s%s%s" % (K["DK"], _t("addagent.ui.plan.skills_keys", "s activa/apaga · k revisa · 0 tokens"), K["R"]), iw))
    # ── LA FEATURE: personalización con IA (toggle «p» · default OFF) ──
    # Pedido del socio 2026-10-02: el toggle pasaba desapercibido como una línea
    # gris más. Ahora es el bloque más fuerte de la caja: divisor con ✦ y
    # acento, estado grande, y el VALOR dicho de frente (a tu medida vs
    # plantilla genérica). Sigue OFF por default — pero imposible de no ver.
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.perso.title", "✦ personalización con IA"), iw, tono=1))
    disp, pnota = _perso_disp(S)
    p_on = bool(S.get("personalize")) and disp
    if disp:
        if p_on:
            out.append(HL.clip((" %s◉ ON %s %s" + _t("addagent.ui.perso.on", "el modelo redacta el cerebro A TU MEDIDA") + "%s")
                               % (K["OK"] + K["BO"], K["R"],
                                  K["WH"] + K["BO"], K["R"]), iw))
            detalle = _t("addagent.ui.perso.on_detail", "SOUL · scope · perfil del dueño, con TUS datos del formulario — p la apaga")
        else:
            out.append(HL.clip((" %s○ OFF%s %s" + _t("addagent.ui.perso.off", "agente a TU medida") + "%s %s" + _t("addagent.ui.perso.off_press", "— pulsa") + "%s %sp%s")
                               % (K["DK"], K["R"], K["WH"] + K["BO"],
                                  K["R"], K["GREY"], K["R"],
                                  K["C"] + K["BO"], K["R"]), iw))
            detalle = _t("addagent.ui.perso.off_detail", "OFF = plantilla genérica (0 tokens) · ON = el modelo redacta SOUL, scope y perfil del dueño con TUS datos")
        if full >= 1:
            for sub in _wrap(detalle, max(8, iw - 8)):
                out.append(HL.clip("       %s%s%s" % (K["DIM"], sub,
                                                      K["R"]), iw))
        if p_on and pnota:               # matiz honesto (ej. codex read-only)
            lineas = _wrap(pnota, max(8, iw - 4))
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  lineas[0], K["R"]), iw))
            for sub in lineas[1:]:                # sangría colgante
                out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    else:                                # sin backend headless → deshabilitado
        out.append(HL.clip((" %s○ OFF%s %s" + _t("addagent.ui.perso.off_disabled", "agente a tu medida con el modelo") + "%s %s" + _t("addagent.ui.perso.unavailable_short", "— no disponible") + "%s")
                           % (K["DK"], K["R"], K["GREY"], K["R"], K["DK"],
                              K["R"]), iw))
        lineas = _wrap(pnota or _t("addagent.ui.perso.no_headless", "el harness elegido no tiene modo headless"),
                       max(8, iw - 4))
        out.append(HL.clip(" %s✗%s %s%s%s" % (K["BAD"], K["R"], K["DIM"],
                                              lineas[0], K["R"]), iw))
        for sub in lineas[1:]:                    # sangría colgante
            out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    # ── costo estimado VS lo que tienes (saldo real donde es legible) ──
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.cost.title", "costo vs tu límite"), iw, tono=3))
    est = agent_create_job.estimate()
    eng = S.get("engine_id") or "claude-code"
    sal = _saldo_eval(S)                 # None = saldo no legible / no codex
    if p_on:
        pt = est.get("personalize_tokens")
        if pt:
            out.append(HL.clip((" %s" + _t("addagent.ui.cost.pass_estimate", "pasada: ~%s tokens") + "%s %s" + _t("addagent.ui.cost.estimated_eng", "— ESTIMADO · %s") + "%s")
                               % (K["WH"] + K["BO"], _fmt_ktok(pt), K["R"],
                                  K["DK"], eng, K["R"]), iw))
        else:
            out.append(HL.clip((" %s" + _t("addagent.ui.cost.pass_unmeasured", "pasada con %s — no medible aquí; se reporta al correr") + "%s") % (K["B"], eng, K["R"]),
                               iw))
        if sal:                          # ── codex: barras + semáforo ──
            vcol = {"ok": K["OK"], "justo": K["B"],
                    "sin": K["BAD"]}[sal["verdict"]]
            bw = max(6, iw - 30)         # las barras NO ceden: son LA info
            for lbl, libre, rtxt, reseteada in sal["vent"]:
                col = K["OK"] if libre >= _SALDO_JUSTO else \
                    (K["B"] if libre >= _SALDO_SIN else K["BAD"])
                extra = _t("addagent.ui.cost.already_reset", "ya se reinició") if reseteada else \
                    ((_t("addagent.ui.cost.reset_at", "reset %s") % rtxt) if rtxt else "")
                out.append(HL.clip(" %s%s%s %s %s%3d%%%s %s%s%s" % (
                    K["GREY"], HL.pad(lbl, 8), K["R"],
                    _barra_saldo(K, libre, bw, col),
                    col + K["BO"], int(libre), K["R"],
                    K["DK"], extra, K["R"]), iw))
            if sal["verdict"] == "ok":
                ver = _t("addagent.ui.cost.verdict_ok", "✓ saldo disponible — consumo real depende del modelo")
            elif sal["verdict"] == "justo":
                ver = _t("addagent.ui.cost.verdict_tight", "⚠ vas justo — debería alcanzar; si truena, el agente queda con plantilla (se recorre luego)")
            else:
                ver = (_t("addagent.ui.cost.verdict_none", "✗ no te alcanza para la pasada — créalo sin personalizar (p) o espera al reset%s")
                       % ((" %s" % sal["reset"]) if sal["reset"] else ""))
            lineas = _wrap(ver, max(8, iw - 3))
            out.append(HL.clip(" %s%s%s%s" % (vcol, K["BO"], lineas[0],
                                              K["R"]), iw))
            for sub in lineas[1:]:                # sangría colgante
                out.append(HL.clip("   %s%s%s%s" % (vcol, K["BO"], sub,
                                                    K["R"]), iw))
            if full >= 1:
                pl = ((" · " + _t("addagent.ui.cost.plan", "plan %s")) % sal["plan"]) if sal["plan"] else ""
                out.append(HL.clip((" %s" + _t("addagent.ui.cost.codex_read", "saldo leído de tu última corrida de codex (%s · 0 tokens)") + "%s%s")
                                   % (K["DK"], sal["edad"], pl, K["R"]), iw))
        elif eng == "codex":             # codex sin snapshot — honesto
            if (S.get("saldo") or {}).get("state") == "busy":
                out.append(HL.clip((" %s %s" + _t("addagent.ui.cost.reading_balance", "leyendo tu saldo (corridas locales · 0 tokens)…") + "%s")
                                   % (_icono(K, "run"), K["DIM"], K["R"]),
                                   iw))
            else:
                for sub in _wrap(_t("addagent.ui.cost.no_codex_runs", "sin corridas locales de codex que leer — tu saldo se pinta en su statusline al correr"), max(8, iw - 3)):
                    out.append(HL.clip(" %s%s%s" % (K["DIM"], sub, K["R"]),
                                       iw))
        else:                            # ── claude/otros: sin dato = sin bar ──
            donde = _t("addagent.ui.cost.where_claude", "/status dentro de la sesión lo muestra") \
                if eng == "claude-code" else _t("addagent.ui.cost.where_other", "se ve al lanzar el harness")
            for sub in _wrap(_t("addagent.ui.cost.cant_read", "no puedo leer tu saldo de %s desde aquí — no invento un número ni un bloqueo; %s · se crea bajo tu criterio") % (eng, donde),
                             max(8, iw - 3)):
                out.append(HL.clip(" %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    else:
        out.append(HL.clip((" %s" + _t("addagent.ui.cost.create_free", "crear: 0 tokens") + "%s %s" + _t("addagent.ui.cost.create_free_detail", "— plantilla local, sin modelo") + "%s")
                           % (K["OK"], K["R"], K["DK"], K["R"]), iw))
        if sal and full >= 1:            # saldo visible aun con el toggle OFF
            cortos = {_t("addagent.ui.saldo.window.5h", "5 horas"): _t("addagent.ui.saldo.short.5h", "5h"),
                      _t("addagent.ui.saldo.window.week", "semana"): _t("addagent.ui.saldo.short.week", "sem")}
            out.append(HL.clip((" %s" + _t("addagent.ui.cost.codex_balance", "saldo codex: %s libre (%s)") + "%s")
                               % (K["DK"],
                                  " · ".join("%s %d%%" % (cortos.get(lbl,
                                                                     lbl),
                                                          int(libre))
                                             for lbl, libre, _r, _x
                                             in sal["vent"]),
                                  sal["edad"], K["R"]), iw))
    if est.get("boot_tokens") and full >= 1:     # cede antes que la feature
        for sub in _wrap(_t("addagent.ui.cost.boot_each_session", "cada sesión futura carga ~%.1fk tokens de arranque (estimado: %d docs HOT del template, ~4 chars/token)")
                         % (est["boot_tokens"] / 1000.0, est["files"]),
                         max(8, iw - 3)):
            out.append(HL.clip(" %s%s%s" % (K["GREY"], sub, K["R"]), iw))
    lim = _LIMITES.get(eng, "")
    if lim and full >= 1 and sal is None:     # con barras, la línea sobra
        lineas = _wrap(_t("addagent.ui.limit.%s" % eng, lim), max(8, iw - 4))
        out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                              lineas[0], K["R"]), iw))
        for sub in lineas[1:]:                    # sangría colgante
            out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.plan.whatwillhappen", "qué va a pasar"), iw, tono=4))
    if full >= 2:
        for i, (_k, lbl) in enumerate(agent_admin.CREATE_STEPS):
            out.append(HL.clip(" %s%d%s %s%s%s"
                               % (K["DK"], i + 1, K["R"], K["GREY"], lbl,
                                  K["R"]), iw))
    else:
        out.append(HL.clip((" %s" + _t("addagent.ui.plan.n_steps_create", "%d pasos — se pintan EN VIVO al crear") + "%s")
                           % (K["GREY"], len(agent_admin.CREATE_STEPS),
                              K["R"]), iw))
    if full >= 2:
        for sub in _wrap(_t("addagent.ui.plan.rollback", "si algo crítico falla, TODO se revierte — jamás un cerebro a medias"), max(8, iw - 3)):
            out.append(HL.clip(" %s%s%s" % (K["DK"], sub, K["R"]), iw))
    return out


# ── vista RUN: creando EN VIVO (patrón actualizaciones_tui) ─────────────────
_ICO = {"pend": ("DK", "·"), "ok": ("OK", "✓"), "warn": ("B", "⚠"),
        "fail": ("BAD", "✗"), "skip": ("DK", "—")}


def _icono(K, st):
    if st == "run":    # perilla ● que pulsa por el gradiente del wordmark
        wc = K["WCOL"]
        return "%s%s●%s" % (wc[int(time.monotonic() * 6) % len(wc)],
                            K["BO"], K["R"])
    col, ch = _ICO.get(st, ("DK", "·"))
    return "%s%s%s" % (K[col], ch, K["R"])


def _progreso(K, hechos, total, ancho):
    """`━━━●────` — el slider del hub como barra de avance (recorrido en el
    gradiente del wordmark, perilla ● en el punto actual). No es una barra
    `█░` de carga: es el MISMO lenguaje del resto del hub."""
    ancho = max(5, ancho)
    v = 1 + int((ancho - 1) * (hechos / float(max(1, total))))
    v = max(1, min(ancho, v))
    wc = K["WCOL"]
    col = wc[2 % len(wc)] + K["BO"]
    return "%s%s%s%s%s%s%s" % (col, "━" * (v - 1), "●", K["R"],
                               K["DK"], "─" * (ancho - v), K["R"])


def _b_run_pasos(job, K, iw):
    """Pasos estructurados de UN job (creación o carga): ✓/●/⚠/✗ + nota."""
    out = []
    for s in job["steps"]:
        icon = _icono(K, s["st"])
        note = s.get("note") or ""
        lcol = (K["WH"] + K["BO"]) if s["st"] == "run" else \
            (K["DK"] if s["st"] in ("pend", "skip") else K["GREY"])
        if note:
            lab = HL.pad(s["label"], max(8, iw - 5 - HL.vis(note)))
            ncol = {"warn": K["B"], "fail": K["BAD"]}.get(s["st"], K["DK"])
            out.append(HL.clip(" %s %s%s%s %s%s%s"
                               % (icon, lcol, lab, K["R"], ncol, note,
                                  K["R"]), iw))
        else:
            out.append(HL.clip(" %s %s%s%s"
                               % (icon, lcol, s["label"], K["R"]), iw))
    return out


def _b_run_vivo(S, K, iw, ih):
    job = S["job"]
    total = len(job["steps"])
    hechos = sum(1 for s in job["steps"] if s["st"] not in ("pend", "run"))
    cur = next((s["label"] for s in job["steps"] if s["st"] == "run"), "")
    out = [_divisor(K, _t("addagent.ui.live.progress", "progreso"), iw, tono=2)]
    out.append(HL.clip(" %s  %s%d/%d%s" % (
        _progreso(K, hechos, total, max(6, iw - 12)),
        K["WH"] + K["BO"], hechos, total, K["R"]), iw))
    out.append(HL.clip(" %s %s%s%s" % (_icono(K, "run"), K["DIM"],
                                       cur or _t("addagent.ui.live.preparing", "preparando…"), K["R"]), iw))
    out.append("")
    out.append(HL.clip((" %s" + _t("addagent.ui.live.agent", "agente:") + "%s %s%s%s %s" + _t("addagent.ui.live.harness", "· harness %s") + "%s")
                       % (K["DK"], K["R"], K["GREY"], job["name"], K["R"],
                          K["DK"], job.get("engine", "?"), K["R"]), iw))
    return _cola_vivo(job, K, iw, ih, out)


def _cola_vivo(job, K, iw, ih, out):
    """Cierra un panel EN VIVO con el log `lo último` en el alto que sobre."""
    resto = ih - len(out)
    if resto >= 3:
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.live.latest", "lo último"), iw))
        quedan = ih - len(out)
    else:
        quedan = max(0, resto)
    vivos = job["live"][-quedan:] if quedan else []
    for st, txt in vivos:
        col, ch = _ICO.get(st, ("DK", "·"))
        for sub in _wrap(txt, max(8, iw - 4))[:1]:
            out.append(HL.clip(" %s%s%s %s%s%s"
                               % (K[col], ch, K["R"], K["DIM"], sub, K["R"]),
                               iw))
    if quedan and not vivos:
        out.append(HL.clip(" %s%s%s" % (K["DK"], _t("addagent.ui.live.starting", "arrancando…"), K["R"]), iw))
    return out


def _b_lrun_vivo(job, K, iw, ih):
    """Panel derecho de CONECTANDO (load en vivo): mismo lenguaje que crear
    — slider de avance + qué cerebro(s) + lo último que pasó."""
    total = len(job["steps"])
    hechos = sum(1 for s in job["steps"] if s["st"] not in ("pend", "run"))
    cur = next((s["label"] for s in job["steps"] if s["st"] == "run"), "")
    out = [_divisor(K, _t("addagent.ui.live.progress", "progreso"), iw, tono=2)]
    out.append(HL.clip(" %s  %s%d/%d%s" % (
        _progreso(K, hechos, total, max(6, iw - 12)),
        K["WH"] + K["BO"], hechos, total, K["R"]), iw))
    out.append(HL.clip(" %s %s%s%s" % (_icono(K, "run"), K["DIM"],
                                       cur or _t("addagent.ui.live.preparing", "preparando…"), K["R"]), iw))
    out.append("")
    if job["bulk"]:
        out.append(HL.clip((" %s" + _t("addagent.ui.live.connecting_n", "conectando %d cerebros — uno por uno") + "%s")
                           % (K["DK"], total, K["R"]), iw))
    else:
        name, folder = job["items"][0]
        out.append(HL.clip((" %s" + _t("addagent.ui.live.brain", "cerebro:") + "%s %s%s%s")
                           % (K["DK"], K["R"], K["GREY"],
                              _ruta_corta(folder), K["R"]), iw))
    out.append(HL.clip(" %s%s%s" % (K["DK"], _t("addagent.ui.live.no_copy", "no copia ni mueve nada — solo registra y cablea"), K["R"]), iw))
    return _cola_vivo(job, K, iw, ih, out)


# ── vista DONE: el resultado, sin tragarse nada ─────────────────────────────
def _b_done(S, K, iw):
    job = S["job"]
    out = []
    warns = [(s["label"], s["note"]) for s in job["steps"]
             if s["st"] in ("warn", "fail")]
    if job.get("ok"):
        out.append(HL.clip((" %s%s «%s» " + _t("addagent.ui.done.created", "creado") + "%s")
                           % (K["OK"] + K["BO"], K["CHECK"], job["name"],
                              K["R"]), iw))
        dur = _mmss((job.get("t1") or time.monotonic()) - job["t0"])
        out.append(HL.clip((" %s" + _t("addagent.ui.done.steps_dur", "%d pasos · %s · harness %s") + "%s")
                           % (K["DK"], len(job["steps"]), dur,
                              job.get("engine", "?"), K["R"]), iw))
        out.append("")
        out.append(HL.clip((" %s" + _t("addagent.ui.done.brain", "cerebro:") + "%s %s%s%s")
                           % (K["DIM"], K["R"], K["GREY"],
                              job.get("dest", ""), K["R"]), iw))
        sourced = job.get("skill_sourcing")
        if sourced:
            out.append(HL.clip((" %s" + _t("addagent.ui.done.skills_summary", "skills: %d instaladas · %d pendientes · 0 tokens") + "%s") %
                               (K["C"], len(sourced["installed"]), len(sourced["held"]), K["R"]), iw))
            for c in sourced["installed"][:5]:
                out.append(HL.clip("   %s · %s" % (c["name"], c["repo"]), iw))
            out.append(HL.clip("   " + _t("addagent.ui.done.skills_receipt", "↓ Ver revisión de skills · recibo .workspace/skill-sourcing.json"), iw))
        if warns:
            out.append("")
            out.append(_divisor(K, _t("addagent.ui.done.pending", "quedó pendiente"), iw))
            for lbl, note in warns[:4]:
                out.append(HL.clip(" %s⚠%s %s%s%s %s%s%s"
                                   % (K["B"], K["R"], K["GREY"], lbl,
                                      K["R"], K["DK"], note or "",
                                      K["R"]), iw))
            out.append(HL.clip(" %s%s%s"
                               % (K["DIM"], _t("addagent.ui.done.review_warns", "→ revisa los avisos antes de usar el agente"), K["R"]), iw))
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.done.nextsteps", "próximos pasos"), iw, tono=2))
        for ln in (_t("addagent.ui.done.next.1", "ábrelo: vuelve al recinto y selecciónalo en el altar"),
                   _t("addagent.ui.done.next.2", "o escribe  %s  en una terminal nueva") % job["name"],
                   _t("addagent.ui.done.next.3", "afina su voz en BOOT/00-SOUL.md · skills en skills/")):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  ln, K["R"]), iw))
    else:
        cancelado = job.get("cancel") and "cancelado" in \
            (job.get("error") or "").lower()
        tcol = K["B"] if cancelado else K["BAD"]
        tit = _t("addagent.ui.done.cancelled", "— creación cancelada") if cancelado \
            else _t("addagent.ui.done.failed", "✗ no se pudo crear «%s»") % job["name"]
        out.append(HL.clip(" %s%s%s%s" % (tcol, K["BO"], tit, K["R"]), iw))
        out.append("")
        for sub in _wrap(job.get("error") or _t("addagent.ui.err.unknown", "error desconocido"),
                         max(8, iw - 3)):
            out.append(HL.clip(" %s%s%s" % (K["GREY"], sub, K["R"]), iw))
        out.append("")
        err = (job.get("error") or "").lower()
        if "revertid" in err or "nada quedó" in err:
            out.append(HL.clip(" %s%s%s" % (K["OK"], _t("addagent.ui.done.rolled_back", "✓ nada quedó a medias — lo escrito se revirtió"), K["R"]), iw))
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.done.next_title", "siguiente"), iw))
        out.append(HL.clip((" %sr%s %s" + _t("addagent.ui.done.retry", "reintentar con los mismos datos") + "%s")
                           % (K["C"] + K["BO"], K["R"], K["DIM"], K["R"]),
                           iw))
        out.append(HL.clip((" %sEnter%s %s" + _t("addagent.ui.done.back_form", "volver al formulario (tus campos siguen ahí)") + "%s")
                           % (K["C"] + K["BO"], K["R"], K["DIM"], K["R"]),
                           iw))
    return out


# ── vista STALE: una creación quedó interrumpida (proceso murió) ────────────
def _b_stale(S, K, iw):
    snap = S.get("stale") or {}
    out = [HL.clip(" %s%s%s"
                   % (K["B"] + K["BO"], _t("addagent.ui.stale.title", "⚠ una creación quedó INTERRUMPIDA"), K["R"]), iw), ""]
    out.append(HL.clip((" %s" + _t("addagent.ui.stale.agent", "agente:") + "%s %s%s%s")
                       % (K["DIM"], K["R"], K["WH"], snap.get("name", "?"),
                          K["R"]), iw))
    out.append(HL.clip((" %s" + _t("addagent.ui.stale.folder", "carpeta:") + "%s %s%s%s")
                       % (K["DIM"], K["R"], K["GREY"], snap.get("dest", "?"),
                          K["R"]), iw))
    existe = os.path.isdir(snap.get("dest") or "")
    out.append(HL.clip((" %s" + _t("addagent.ui.stale.leftovers", "restos en disco:") + "%s %s%s%s")
                       % (K["DIM"], K["R"],
                          K["B"] if existe else K["OK"],
                          _t("addagent.ui.stale.leftovers_yes", "sí — la carpeta existe a medias") if existe
                          else _t("addagent.ui.stale.leftovers_no", "no — no quedó carpeta"), K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.stale.howfar", "hasta dónde llegó"), iw))
    for s in (snap.get("steps") or [])[:8]:
        st = s.get("st", "pend")
        icon = _icono(K, st if st != "run" else "warn")
        out.append(HL.clip(" %s %s%s%s" % (icon, K["GREY"],
                                           s.get("label", ""), K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.stale.whattodo", "qué hacer"), iw, tono=3))
    out.append(HL.clip((" %sl%s %s" + _t("addagent.ui.stale.clean", "limpiar los restos (borra carpeta y registro)") + "%s")
                       % (K["C"] + K["BO"], K["R"], K["DIM"], K["R"]), iw))
    out.append(HL.clip((" %sr%s %s" + _t("addagent.ui.stale.clean_retry", "limpiar y REINTENTAR la creación") + "%s")
                       % (K["C"] + K["BO"], K["R"], K["DIM"], K["R"]), iw))
    out.append(HL.clip((" %sEnter/q%s %s" + _t("addagent.ui.stale.later", "decidir después (se vuelve a avisar)") + "%s")
                       % (K["C"] + K["BO"], K["R"], K["DIM"], K["R"]), iw))
    return out


def _b_cargar(S, K, iw):
    out = [_divisor(K, _t("addagent.ui.load.path_title", "la ruta"), iw, tono=1)]
    out.append(HL.clip(" %s%s%s"
                       % (K["DIM"], _t("addagent.ui.load.point_to", "apunta a la carpeta del cerebro:"), K["R"]), iw))
    # input con COLA visible: una ruta más larga que la caja se recorta por
    # la IZQUIERDA (…/final) — antes se recortaba por la derecha y dejabas
    # de ver lo que tecleabas
    buf, maxb = S["ruta"], max(8, iw - 6)
    pre, shown = ("…", buf[-(maxb - 1):]) if len(buf) > maxb else ("", buf)
    out.append(HL.clip(" %s%s%s %s%s%s%s%s%s█%s" % (
        K["C"] + K["BO"], K["PTR"], K["R"], K["DK"], pre, K["R"],
        K["WH"], shown, K["C"] + K["BO"], K["R"]), iw))
    out.append(HL.clip(("   %s" + _t("addagent.ui.load.path_hint", "~ y espacios valen · ej. ~/Desktop/HERMES - BRAIN") + "%s") % (K["DK"], K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.load.loaded_here", "cargados en esta máquina"), iw))
    ags = agentsreg.agents()
    for a in ags[:6]:
        out.append(HL.clip(" %s%s%s  %s%s%s" % (
            K["GREY"], HL.pad(a["name"], 10), K["R"],
            K["DK"], _ruta_corta(a.get("brain", "")), K["R"]), iw))
    if len(ags) > 6:
        out.append(HL.clip((" %s" + _t("addagent.ui.load.and_more", "… y %d más") + "%s") % (K["DK"], len(ags) - 6,
                                                K["R"]), iw))
    if not ags:
        out.append(HL.clip(" %s%s%s" % (K["DK"], _t("addagent.ui.load.none_yet", "(ninguno aún)"), K["R"]), iw))
    return out


#: (color-key, icono, título, [líneas]) por estado de la radiografía —
#: la caja derecha de CARGAR dice EXACTAMENTE qué pasaría al conectar.
def _estado_carga(K, info):
    if info["estado"] == "colision":
        return (K["BAD"], "✗",
                _t("addagent.ui.loadstate.collision", "colisión — «%s» ya está cargado") % info["name"],
                [_t("addagent.ui.loadstate.collision_from", "desde: %s") % _ruta_corta(info["cargado_de"]),
                 _t("addagent.ui.loadstate.collision_hint", "no se puede conectar — renombra uno o cárgalo por CLI con otro nombre")])
    if info["estado"] == "cargado":
        return (K["OK"], "●", _t("addagent.ui.loadstate.loaded", "ya conectado desde esta carpeta"),
                [_t("addagent.ui.loadstate.loaded_hint", "conectar de nuevo solo re-verifica el cableado (idempotente — no rompe nada)")])
    return (K["C"], "○", _t("addagent.ui.loadstate.new", "nuevo en esta máquina"),
            [_t("addagent.ui.loadstate.new_hint", "conectar lo registra y lo deja usable al instante")])


def _b_cargar_det(S, K, iw, full=2):
    out = []
    if not S["ruta"].strip():
        for ln in (_t("addagent.ui.load.intro", "Conecta un cerebro que YA existe: su carpeta se queda donde está — solo se registra en esta máquina y se cablea (hooks · statusline · launcher · tema)."),):
            for sub in _wrap(ln, max(8, iw - 3)):
                out.append(HL.clip(" %s%s%s" % (K["GREY"], sub, K["R"]), iw))
        out.append("")
        out.append(HL.clip(" %s%s%s" % (K["DIM"], _t("addagent.ui.load.type_path", "escribe la ruta — aquí verás la radiografía de la carpeta"), K["R"]), iw))
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.howitworks", "cómo funciona"), iw, tono=4))
        for ln in (_t("addagent.ui.load.how.1", "si la carpeta no trae definición, se siembra una mínima"),
                   _t("addagent.ui.load.how.2", "no pisa agentes: mismo nombre en otra carpeta = aviso"),
                   _t("addagent.ui.load.how.3", "idempotente: recargar la misma carpeta no rompe nada"),
                   _t("addagent.ui.load.how.4", "¿no sabes la ruta? «descubrir» escanea el disco por ti")):
            for sub in _wrap(ln, max(8, iw - 4)):
                out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"],
                                                      K["DIM"], sub, K["R"]),
                                   iw))
        return out
    info = _insp(S)
    out.append(HL.clip(" %s%s%s" % (K["GREY"],
                                    _ruta_corta(info.get("folder") or
                                                S["ruta"].strip()),
                                    K["R"]), iw))
    if not info.get("exists"):
        out.append(HL.clip(" %s%s%s" % (K["BAD"], _t("addagent.ui.load.not_exist", "✗ la carpeta no existe (aún)"), K["R"]), iw))
        out.append("")
        out.append(HL.clip(" %s%s%s" % (K["DK"], _t("addagent.ui.load.keep_typing", "sigue escribiendo — valido conforme tecleas"), K["R"]), iw))
        return out
    marcas = info.get("marcas") or []
    tiene = sum(1 for _m, hay in marcas if hay)
    mcol = K["OK"] if tiene >= 3 else (K["B"] if tiene else K["BAD"])
    out.append(HL.clip((" %s" + _t("addagent.ui.load.exists", "✓ existe") + "%s %s" + _t("addagent.ui.load.brain_marks", "— marcas de cerebro %s%d/%d") + "%s")
                       % (K["OK"], K["R"], K["DK"], mcol, tiene,
                          max(1, len(marcas)), K["R"]), iw))
    out.append(HL.clip("   %s%s%s"
                       % (K["DK"], " · ".join(
                           "%s %s" % (m, "✓" if hay else "✗")
                           for m, hay in marcas), K["R"]), iw))
    if not tiene:
        lineas = _wrap(_t("addagent.ui.load.not_brain", "no parece un cerebro — se puede conectar igual, pero revisa la ruta"), max(8, iw - 5))
        out.append(HL.clip(" %s⚠%s %s%s%s" % (K["B"], K["R"], K["B"],
                                              lineas[0], K["R"]), iw))
        for sub in lineas[1:]:
            out.append(HL.clip("   %s%s%s" % (K["B"], sub, K["R"]), iw))
    # el ESTADO va antes que el detalle de identidad: es lo esencial (si hay
    # colisión, debe verse incluso en terminales bajitas donde el resto cede)
    out.append("")
    ecol, ico, tit, lineas = _estado_carga(K, info)
    out.append(HL.clip(" %s%s %s%s" % (ecol, ico, tit, K["R"]), iw))
    for ln in lineas:
        for sub in _wrap(ln, max(8, iw - 4)):
            out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.identity", "identidad"), iw, tono=2))
    if info.get("has_def"):
        out.append(HL.clip(" %s%s%s" % (K["OK"], _t("addagent.ui.load.has_def", "✓ trae .workspace/agent.json — se respeta"), K["R"]), iw))
        out.append(HL.clip("   %s%s%s %s· %s%s"
                           % (K["WH"], info.get("name", ""), K["R"],
                              K["DIM"], info.get("display")
                              or info.get("name", "?").capitalize(),
                              K["R"]), iw))
        det = " · ".join(x for x in (
            (_t("addagent.ui.detail.harness", "harness %s") % info["engine"]) if info.get("engine") else "",
            (_t("addagent.ui.detail.owner", "dueño %s") % info["owner"]) if info.get("owner") else "") if x)
        if det:
            out.append(HL.clip("   %s%s%s" % (K["DK"], det, K["R"]), iw))
        if info.get("tagline") and full >= 1:
            for sub in _wrap(info["tagline"], max(8, iw - 5))[:1]:
                out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    else:
        out.append(HL.clip(" %s%s%s" % (K["B"], _t("addagent.ui.load.no_def", "· sin definición — se SIEMBRA una mínima"), K["R"]), iw))
        out.append(HL.clip(("   %s" + _t("addagent.ui.load.inferred_name", "nombre inferido de la carpeta: ") + "%s%s%s")
                           % (K["DK"], K["WH"], info.get("name", "?"),
                              K["R"]), iw))
    if info.get("estado") == "colision":
        return out                # Enter está bloqueado — sin "qué va a pasar"
    out.append("")
    out.append(_divisor(K, _t("addagent.ui.load.whatwillhappen", "qué va a pasar (Enter)"), iw, tono=4))
    if full >= 2:
        for i, (_k, lbl) in enumerate(agent_admin.LOAD_STEPS):
            out.append(HL.clip(" %s%d%s %s%s%s"
                               % (K["DK"], i + 1, K["R"], K["GREY"], lbl,
                                  K["R"]), iw))
    else:
        out.append(HL.clip((" %s" + _t("addagent.ui.load.n_steps", "%d pasos — se pintan EN VIVO al conectar") + "%s")
                           % (K["GREY"], len(agent_admin.LOAD_STEPS),
                              K["R"]), iw))
    if full >= 1:
        lineas = _wrap(_t("addagent.ui.load.no_copy", "no copia ni mueve nada — el cerebro se queda donde está"), max(8, iw - 4))
        out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                              lineas[0], K["R"]), iw))
        for sub in lineas[1:]:                    # sangría colgante
            out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    return out


#: marca por estado de un cerebro descubierto — leyenda del panel derecho
_DESC_MARKS = {"nuevo": ("DK", "○", "nuevo — sin conectar"),
               "cargado": ("OK", "●", "ya conectado"),
               "otro": ("B", "⚠", "colisión de carpeta"),
               "ok": ("OK", None, "conectado ahora ✓")}   # None → K["CHECK"]


def _desc_mark(K, est):
    if est.startswith("err"):
        return "%s✗%s" % (K["BAD"], K["R"])
    ckey, ch, _lbl = _DESC_MARKS.get(est, ("DK", "·", ""))
    return "%s%s%s" % (K[ckey], ch if ch is not None else K["CHECK"], K["R"])


def _b_descubrir(S, K, iw):
    out = []
    scan = S.get("scan") or {}
    if scan.get("state") == "busy":
        out.append(HL.clip(" %s %s%s%s"
                           % (_icono(K, "run"), K["DIM"], _t("addagent.ui.discover.scanning", "escaneando el disco…"), K["R"]), iw))
        out.append("")
        for i, d in enumerate(_SCAN_DONDE):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DK"],
                                                  _t("addagent.ui.scan.where.%d" % i, d), K["R"]), iw))
        return out
    found = S["found"]
    if not found:
        out.append(HL.clip(" %s%s%s" % (K["DK"], _t("addagent.ui.discover.none", "no encontré cerebros con .workspace/agent.json"), K["R"]), iw))
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.discover.where_title", "dónde busqué"), iw))
        for i, d in enumerate(_SCAN_DONDE):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  _t("addagent.ui.scan.where.%d" % i, d), K["R"]), iw))
        out.append("")
        out.append(HL.clip(" %s%s%s" % (K["DIM"], _t("addagent.ui.discover.elsewhere", "¿está en otro lado? usa «cargar» y teclea la ruta"), K["R"]), iw))
        return out
    for i, a in enumerate(found):
        sel = (i == S["di"])
        cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
        est = S["estados"].get(a["name"], "")
        tag = (" %s◆olympus%s" % (K["B"], K["R"])) if a.get("legacy_olympus") else ""
        out.append(HL.clip(" %s %s %s%s%s  %s%s%s%s" % (
            cur, _desc_mark(K, est),
            (K["WH"] + K["BO"]) if sel else K["GREY"],
            HL.pad(a["name"], 10), K["R"],
            K["DK"], _ruta_corta(a.get("brain", "")), K["R"], tag), iw))
    nuevos = sum(1 for a in found
                 if S["estados"].get(a["name"]) == "nuevo")
    out.append("")
    out.append(HL.clip((" %s" + _t("addagent.ui.discover.count", "%d cerebro(s) · %d nuevo(s)") + "%s") % (
        K["DIM"], len(found), nuevos, K["R"]), iw))
    return out


#: explicación por estado para el panel EL CEREBRO de descubrir
_DESC_EXPL = {
    "nuevo": ("C", "○ nuevo — sin conectar en esta máquina",
              ("Enter lo conecta: registro per-máquina + cableado "
               "(hooks · statusline · launcher · tema).",)),
    "cargado": ("OK", "● ya conectado desde esta carpeta",
                ("conectarlo de nuevo solo re-verifica el cableado "
                 "(idempotente).",)),
    "otro": ("B", "⚠ su nombre ya está cargado desde OTRA carpeta",
             ("no se puede conectar desde aquí — renombra uno o "
              "cárgalo por CLI con otro nombre.",)),
    "ok": ("OK", "✓ conectado ahora mismo",
           ("listo — ábrelo desde el recinto o con su comando.",)),
}


def _b_descubrir_det(S, K, iw, full=2):
    out = []
    scan = S.get("scan") or {}
    if scan.get("state") == "busy":
        for ln in (_t("addagent.ui.discover.busy.1", "Buscando carpetas con .workspace/agent.json — el marcador inequívoco de un cerebro WORKSPACE."),
                   _t("addagent.ui.discover.busy.2", "Solo se LEE el disco: nada se conecta solo.")):
            for sub in _wrap(ln, max(8, iw - 3)):
                out.append(HL.clip(" %s%s%s" % (K["GREY"], sub, K["R"]), iw))
            out.append("")
        return out
    found = S["found"]
    if not found:
        for ln in (_t("addagent.ui.discover.shallow", "El escaneo es superficial a propósito: un nivel bajo Desktop/Documents + los vaults de Obsidian — no se recorre todo el disco."),):
            for sub in _wrap(ln, max(8, iw - 3)):
                out.append(HL.clip(" %s%s%s" % (K["GREY"], sub, K["R"]), iw))
        return out
    a = found[S["di"] % len(found)]
    est = S["estados"].get(a["name"], "")
    d = S.setdefault("defs", {}).get(a["brain"])
    if d is None:
        try:
            d = agentsreg.load_definition(a["brain"]) or {}
            if not d and a.get("legacy_olympus"):     # cerebro OLYMPUS legacy: lee su def real
                d = agentsreg._read_json(
                    agentsreg.olympus_json_path(a["brain"])) or {}
        except Exception:
            d = {}
        S["defs"][a["brain"]] = d
    out.append(HL.clip(" %s%s%s %s· %s%s"
                       % (K["WH"] + K["BO"], d.get("display")
                          or a["name"].capitalize(), K["R"],
                          K["DK"], a["name"], K["R"]), iw))
    if d.get("tagline"):
        for sub in _wrap(d["tagline"], max(8, iw - 3))[:2]:
            out.append(HL.clip(" %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    if a.get("legacy_olympus"):
        out.append(HL.clip(" %s%s%s" % (K["B"], _t("addagent.ui.discover.migrate", "◆ venía de OLYMPUS → se migra a .workspace/ al conectar"), K["R"]), iw))
    out.append("")
    out.append(HL.clip((" %s" + _t("addagent.ui.discover.folder", "carpeta:") + "%s %s%s%s")
                       % (K["DK"], K["R"], K["GREY"],
                          _ruta_corta(a.get("brain", "")), K["R"]), iw))
    det = " · ".join(x for x in (
        (_t("addagent.ui.detail.harness", "harness %s") % d["engine"]) if d.get("engine") else "",
        (_t("addagent.ui.detail.owner", "dueño %s") % d["owner"]) if d.get("owner") else "") if x)
    if det:
        out.append(HL.clip(" %s%s%s" % (K["DK"], det, K["R"]), iw))
    out.append("")
    if est.startswith("err"):
        out.append(HL.clip(" %s%s%s" % (K["BAD"], _t("addagent.ui.discover.conn_failed", "✗ no se pudo conectar"), K["R"]), iw))
        for sub in _wrap(est[4:] or _t("addagent.ui.err.unknown", "error desconocido"), max(8, iw - 4)):
            out.append(HL.clip("   %s%s%s" % (K["GREY"], sub, K["R"]), iw))
    else:
        ckey, tit, lineas = _DESC_EXPL.get(est, ("DK", _t("addagent.ui.descexpl.unknown.title", "· estado desconocido"), ()))
        if est in _DESC_EXPL:
            tit = _t("addagent.ui.descexpl.%s.title" % est, tit)
            lineas = tuple(_t("addagent.ui.descexpl.%s.body.%d" % (est, j), ln) for j, ln in enumerate(lineas))
        out.append(HL.clip(" %s%s%s" % (K[ckey], tit, K["R"]), iw))
        extra = ((" " + _t("addagent.ui.discover.the_other", "la otra: %s")) % _ruta_corta(
            (scan.get("reg") or {}).get(a["name"], ""))) \
            if est == "otro" else ""
        for ln in lineas + ((extra,) if extra else ()):
            for sub in _wrap(ln, max(8, iw - 4)):
                out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]),
                                   iw))
    if scan.get("avisos") and full >= 1:
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.discover.scan_warns", "avisos del escaneo"), iw))
        for av in scan["avisos"][:2]:
            lineas = _wrap(av, max(8, iw - 4))[:2]
            out.append(HL.clip(" %s⚠%s %s%s%s" % (K["B"], K["R"], K["DIM"],
                                                  lineas[0], K["R"]), iw))
            for sub in lineas[1:]:                # sangría colgante
                out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]),
                                   iw))
    if full >= 2:
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.howitworks", "cómo funciona"), iw, tono=4))
        for ln in (_t("addagent.ui.discover.how.1", "nada se conecta solo: tú eliges cuál (o a = los nuevos)"),
                   _t("addagent.ui.discover.how.2", "conectar = lo mismo que «cargar», sin teclear la ruta")):
            for sub in _wrap(ln, max(8, iw - 4)):
                out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"],
                                                      K["DIM"], sub, K["R"]),
                                   iw))
    return out


def _b_listo(S, K, iw):
    """Resultado de cargar/conectar — honesto: éxito, warns (placeholders ·
    config a medias → doctor) o el error completo. Lote = línea por cerebro."""
    d = S["done"]
    out = []
    if d.get("bulk") is not None:
        oks = sum(1 for _n, st, _x in d["bulk"] if st == "ok")
        tcol = K["OK"] if oks == len(d["bulk"]) else (
            K["B"] if oks else K["BAD"])
        out.append(HL.clip((" %s%s" + _t("addagent.ui.listo.connected_n", "conectados %d/%d") + "%s")
                           % (tcol, K["BO"], oks, len(d["bulk"]), K["R"]),
                           iw))
        out.append("")
        for n, st, note in d["bulk"][:8]:
            ico = ("%s%s%s" % (K["OK"], K["CHECK"], K["R"])) if st == "ok" \
                else ("%s✗%s" % (K["BAD"], K["R"]))
            out.append(HL.clip(" %s %s%s%s %s%s%s"
                               % (ico, K["GREY"], HL.pad(n, 12), K["R"],
                                  K["DK"], note or "", K["R"]), iw))
    elif d.get("ok", True):
        out.append(HL.clip(" %s%s «%s» %s%s"
                           % (K["OK"] + K["BO"], K["CHECK"],
                              d.get("name", ""), d.get("verbo", _t("addagent.ui.verb.created", "creado")),
                              K["R"]), iw))
        if d.get("dur"):
            out.append(HL.clip((" %s%s " + _t("addagent.ui.listo.registered", "· registrado y cableado") + "%s")
                               % (K["DK"], d["dur"], K["R"]), iw))
        out.append("")
        if d.get("ruta"):
            out.append(HL.clip((" %s" + _t("addagent.ui.listo.brain", "cerebro:") + "%s %s%s%s")
                               % (K["DIM"], K["R"], K["GREY"],
                                  _ruta_corta(d["ruta"]), K["R"]), iw))
    else:
        out.append(HL.clip((" %s%s" + _t("addagent.ui.listo.failed", "✗ no se pudo %s") + "%s")
                           % (K["BAD"], K["BO"],
                              d.get("verbo", _t("addagent.ui.verb.load", "cargar")), K["R"]), iw))
        out.append("")
        for sub in _wrap(d.get("error") or _t("addagent.ui.err.unknown", "error desconocido"),
                         max(8, iw - 3)):
            out.append(HL.clip(" %s%s%s" % (K["GREY"], sub, K["R"]), iw))
        out.append("")
        out.append(HL.clip(" %s%s%s" % (K["DK"], _t("addagent.ui.listo.nothing_left", "nada quedó a medias — cargar no copia ni borra"), K["R"]), iw))
        return out
    warns = d.get("warns") or []
    if warns:
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.listo.warns", "avisos — nada se tragó"), iw))
        for wtxt in warns[:3]:
            lineas = _wrap(wtxt, max(8, iw - 4))[:2]
            out.append(HL.clip(" %s⚠%s %s%s%s" % (K["B"], K["R"], K["DIM"],
                                                  lineas[0], K["R"]), iw))
            for sub in lineas[1:]:
                out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]),
                                   iw))
        out.append(HL.clip(" %s%s%s" % (K["DIM"], _t("addagent.ui.listo.doctor", "→ `workspace doctor` completa lo que falte"), K["R"]), iw))
    if d.get("bulk") is None:
        out.append("")
        out.append(_divisor(K, _t("addagent.ui.done.nextsteps", "próximos pasos"), iw, tono=2))
        for ln in (_t("addagent.ui.done.next.1", "ábrelo: vuelve al recinto y selecciónalo en el altar"),
                   _t("addagent.ui.done.next.2", "o escribe  %s  en una terminal nueva")
                   % d.get("name", ""),
                   _t("addagent.ui.done.next.3", "afina su voz en BOOT/00-SOUL.md · skills en skills/")):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  ln, K["R"]), iw))
    return out


_TITULOS = {"menu": ("AGREGAR AGENTE", "LA OPCIÓN"),
            "crear": ("CREAR AGENTE", "EL CAMPO"),
            "plan": ("TUS PREFERENCIAS", "ASÍ NACE TU AGENTE"),
            "skills": ("ELIGE TUS SKILLS", "ORIGEN Y REVISIÓN"),
            "run": ("CREANDO", "EN VIVO"),
            "done": ("RESULTADO", ""),
            "stale": ("CREACIÓN INTERRUMPIDA", ""),
            "cargar": ("CARGAR AGENTE", "LA CARPETA"),
            "descubrir": ("CEREBROS EN EL DISCO", "EL CEREBRO"),
            "lrun": ("CONECTANDO", "EN VIVO"),
            "listo": ("RESULTADO", "")}

_TITULOS.update({"motor": ("ELIGE EL MOTOR", "DISPONIBILIDAD"),
                 "sources": ("FUENTES PERMITIDAS", "TÚ DECIDES EL ORIGEN"),
                 "repo": ("AGREGAR REPOSITORIO", "GITHUB PÚBLICO"),
                 "community": ("CONSULTA DE COMUNIDAD", "QUÉ SE ENVÍA"),
                 "process": ("REVISIÓN AUTOMÁTICA", "PASO A PASO"),
                 "cost": ("CONSUMO Y LÍMITES", "LECTURAS Y ESTIMACIONES"),
                 "brain": ("TU CEREBRO", "ARCHIVOS QUE SE CREAN"),
                 "skill_receipt": ("RESULTADOS DE SKILLS", "MOTIVOS Y AVISOS")})

# Atajos POR VISTA como pares (tecla, acción): UNA fuente de verdad — la
# cabecera enseña los clave + salir (HL.top_hints recorta a 4) y el pie la
# lista COMPLETA (HL.foot_hints; en angosto cede pares, jamás recorta a
# media palabra).
_HINTS = {
    "menu": (("↑↓", "elige"), ("Enter", "entra"), ("1-3", "directo"),
             ("q", "vuelve al menú")),
    "crear": (("↑↓/Tab", "campo"), ("escribe", "edita"),
              ("Enter", "avanza (campo largo con texto: nueva línea)"),
              ("Esc", "vuelve")),
    "skills": (("↑↓", "selecciona"), ("Enter", "aplica"),
               ("Espacio", "marca"), ("Esc", "vuelve")),
    "plan": (("↑↓", "elige"), ("Enter", "aplica"), ("←→", "lee más"),
             ("p", "IA"), ("s", "skills"), ("k", "revisa"),
             ("Esc", "vuelve")),
    "run": (("q", "cancela (cooperativo)"),
            ("Esc", "vuelve al recinto — la creación sigue en 2º plano")),
    "done": (("↓", "revisión de skills"), ("Enter/q", "continúa")),
    "stale": (("l", "limpia"), ("r", "limpia y reintenta"),
              ("Enter/q", "después")),
    "cargar": (("escribe", "la ruta"), ("Enter", "conecta"),
               ("Esc", "vuelve")),
    "descubrir": (("↑↓", "elige"), ("Enter", "conecta"),
                  ("a", "los nuevos"), ("r", "re-escanea"),
                  ("Esc", "vuelve")),
    "lrun": (("Esc", "vuelve — la conexión sigue y avisa al terminar"),),
    "listo": (("Enter/q", "volver"),)}
_HINTS_DEF = (("↑↓", "elige"), ("Enter", "aplica"), ("←→", "lee más"),
              ("Esc", "vuelve"))

_SUBS = {"plan": "agregar agente — el plan, antes de tocar el disco",
         "run": "agregar agente — creando en vivo",
         "done": "agregar agente — resultado",
         "stale": "agregar agente — quedó algo a medias",
         "cargar": "agregar agente — conectar un cerebro que ya existe",
         "descubrir": "agregar agente — lo que el disco ya tiene",
         "lrun": "agregar agente — conectando en vivo",
         "listo": "agregar agente — resultado"}


# ── resolución i18n de las tablas (render-time → flip de idioma EN VIVO) ─────
def _titulos_t(view):
    """(izq, der) del título de la vista, traducidos al idioma activo."""
    if view in _TITULOS:
        l, r = _TITULOS[view]
        return (_t("addagent.ui.title.%s.l" % view, l),
                _t("addagent.ui.title.%s.r" % view, r))
    return (_t("addagent.ui.title.default.l", "TUS PREFERENCIAS"),
            _t("addagent.ui.title.default.r", "QUÉ HACE ESTA OPCIÓN"))


def _sub_t(view):
    """Subtítulo de la cabecera, traducido (misma lógica de fallback)."""
    base = _SUBS.get(view)
    if base is not None:
        return _t("addagent.ui.sub.%s" % view, base)
    if view in agent_create_ui.VIEWS:
        return _t("addagent.ui.sub.prefix", "agregar agente — ") + _titulos_t(view)[0].lower()
    return _t("addagent.ui.sub.default", "agregar agente — crear · cargar · descubrir")


def _hints_t(view):
    """Pares (tecla, acción) de la vista con la acción (y teclas-palabra)
    traducidas al idioma activo."""
    name = view if view in _HINTS else "def"
    pairs = _HINTS.get(view, _HINTS_DEF)
    out = []
    for j, (k, a) in enumerate(pairs):
        if k == "escribe":
            k = _t("addagent.ui.hintkey.type", "escribe")
        elif k == "Espacio":
            k = _t("addagent.ui.hintkey.space", "Espacio")
        out.append((k, _t("addagent.ui.hint.%s.%d" % (name, j), a)))
    return tuple(out)


def _solo_w(w, apilado):
    """Ancho de las vistas de UNA caja (done/stale/listo): el ancho útil
    completo (las rutas largas no se truncan), con techo para no regar la
    línea en monitores ultra anchos."""
    return (w - 2) if apilado else min(w - 2, 100)


def render(S, w, h):
    K = _K()
    sub = _sub_t(S["view"])
    # cabecera COMPARTIDA (wordmark + subtítulo + atajos clave + regla);
    # los atajos de arriba siguen la VISTA — nunca mienten
    L = HL.screen_header(K, w, h, sub,
                         hints=_hints_t(S["view"]))
    top = len(L)
    apilado = w < 100
    lw = (w - 1) if apilado else max(36, min(52, (w - 6) * 48 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    avail = max(8, (h - 1) - top - 3)
    v = S["view"]
    bi = bd = None
    if v in ("plan", "brain"):
        L += agent_create_ui.plan_screen(S, sys.modules[__name__], K, w, avail)
        return _finish_frame(S, K, L, w, h)
    if v == "menu":
        bi, bd = _b_menu(S, K, lw - 4), _b_menu_det(S, K, rw - 4)
    elif v == "crear":
        # presupuesto del formulario: si no cabe, _b_crear abre su ventana
        # deslizante (el campo enfocado SIEMPRE visible, altura estable)
        cap = (avail - 2) if not apilado \
            else max(6, (avail - 4) * 55 // 100)
        for grupos, full in ((True, 2), (True, 1), (False, 1), (False, 0)):
            bi = _b_crear(S, K, lw - 4, grupos=grupos, max_h=cap)
            bd = _b_crear_det(S, K, rw - 4, full=full)
            need = (len(bi) + len(bd) + 4) if apilado \
                else (max(len(bi), len(bd)) + 2)
            if need <= avail:
                break
    elif v in agent_create_ui.VIEWS:
        cap = max(3, (avail - 4) // 2 if apilado else avail - 2)
        bi, bd = agent_create_ui.panels(S, sys.modules[__name__], lw - 4, rw - 4, cap)
    elif v == "skills":
        bi, bd = _b_skills(S, K, lw - 4, rw - 4,
                            max(3, (avail - 4) // 2 if apilado else avail - 2))
    elif v == "run":
        bi = _b_run_pasos(S["job"], K, lw - 4)
        ih_d = max(4, (avail - len(bi) - 4) if apilado else (avail - 2))
        bd = _b_run_vivo(S, K, rw - 4, ih_d)
    elif v == "lrun":
        bi = _b_run_pasos(S["ljob"], K, lw - 4)
        ih_d = max(4, (avail - len(bi) - 4) if apilado else (avail - 2))
        bd = _b_lrun_vivo(S["ljob"], K, rw - 4, ih_d)
    elif v == "done":
        bi, bd = _b_done(S, K, _solo_w(w, apilado) - 4), []
    elif v == "stale":
        bi, bd = _b_stale(S, K, _solo_w(w, apilado) - 4), []
    elif v == "cargar":
        for full in (2, 1, 0):
            bi = _b_cargar(S, K, lw - 4)
            bd = _b_cargar_det(S, K, rw - 4, full=full)
            need = (len(bi) + len(bd) + 4) if apilado \
                else (max(len(bi), len(bd)) + 2)
            if need <= avail:
                break
    elif v == "descubrir":
        for full in (2, 1, 0):
            bi = _b_descubrir(S, K, lw - 4)
            bd = _b_descubrir_det(S, K, rw - 4, full=full)
            need = (len(bi) + len(bd) + 4) if apilado \
                else (max(len(bi), len(bd)) + 2)
            if need <= avail:
                break
    else:                                            # listo
        bi, bd = _b_listo(S, K, _solo_w(w, apilado) - 4), []
    t_izq, t_der = _titulos_t(v)
    solo = v in ("listo", "done", "stale")
    if solo or apilado:
        dos = bool(bd) and apilado and not solo
        # presupuesto APILADO: ambas cajas caben SIEMPRE (reparto ~55/45,
        # patrón actualizaciones); con una sola caja, todo el alto para ella
        ih = min(len(bi), max(3, ((avail - 4) * 55 // 100) if dos
                              else (avail - 2)))
        bw = _solo_w(w, apilado) if solo \
            else (lw - (0 if not apilado else 1))
        for ln in HL.full_box(t_izq, bi, K, bw,
                              max(3, ih), True, border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
        if dos:
            ih_d = max(3, min(len(bd), avail - (ih + 2) - 2))
            for ln in HL.full_box(t_der, bd, K, rw - 1, ih_d, False,
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
    # pie SIEMPRE visible (el cuerpo cede antes que el pie — regla dura) +
    # contrato de altura ESTABLE: SIEMPRE h-1 líneas (cambiar de vista con
    # `H` + `\033[K` no deja residuos de la vista anterior)
    return _finish_frame(S, K, L, w, h)


def _finish_frame(S, K, L, w, h):
    v = S["view"]
    L = L[:max(0, (h - 1) - 3)]
    L += [""] * max(0, (h - 1) - 3 - len(L))
    L.append("")
    L.append((" %s%s%s" % (K["B2"], S["msg"], K["R"]))
             if S.get("msg") else "")
    L.append(HL.foot_hints(K, _hints_t(v), w))
    L = L[:h - 1]
    L += [""] * max(0, (h - 1) - len(L))
    return [HL.clip(x, w - 1) for x in L]


def _lanza_skills(S, force=False):
    if not S.get("source_skills", True):
        return
    params = _params_de_form(S)
    fingerprint = agent_skill_sources.profile(params) + json.dumps(params.get("skill_source_config"), sort_keys=True) + params.get("community_query", "")
    prior = S.get("sourcing") or {}
    if not force and prior.get("profile") == fingerprint:
        return
    state = {"state": "busy", "profile": fingerprint, "candidates": [], "errors": []}
    S["sourcing"] = state
    S["skill_selected"] = set()
    S["skill_cursor"] = 0
    def worker():
        try:
            result = agent_skill_sources.discover(params, should_cancel=lambda: S.get("sourcing") is not state or not S.get("source_skills"))
        except Exception as e:
            result = {"candidates": [], "errors": [type(e).__name__]}
        if S.get("sourcing") is not state:
            return
        # Las primeras 5 coincidencias se proponen; el dueño puede quitarlas.
        S["skill_selected"] = {c["source_url"] for c in [c for c in result["candidates"] if c.get("discovered_via") != "skills.sh"][:5]}
        state.update(result)
        state["state"] = "done"
    threading.Thread(target=worker, daemon=True).start()


def _b_skills(S, K, iw, dw, cap):
    source = S.get("sourcing") or {}
    candidates = source.get("candidates", [])
    selected = S.get("skill_selected", set())
    left = [_t("addagent.ui.skills.selected_count", "%d seleccionadas / 5 · 0 tokens de modelo") % len(selected)]
    actions = [_t("addagent.ui.skills.search_again", "Buscar de nuevo"),
               _t("addagent.ui.skills.sources_repos", "Fuentes y repositorios"),
               _t("addagent.ui.skills.back_plan", "Volver al plan")]
    cursor = min(S.get("skill_cursor", 0), len(candidates) + 2)
    start = max(0, cursor - max(1, cap - 3) // 2)
    menu = [("[x] " if c["source_url"] in selected else "[ ] ") + c["name"] for c in candidates] + actions
    start = max(0, min(cursor - max(1, cap - 2) // 2, len(menu) - max(1, cap - 1)))
    for i in range(start, min(len(menu), start + max(1, cap - 1))):
        left.append(HL.clip(("› " if i == cursor else "  ") + menu[i], iw))
    right = []
    if candidates and cursor < len(candidates):
        c = candidates[cursor]
        parts = [_t("addagent.ui.skills.origin", "Origen: ") + c["repo"], _t("addagent.ui.skills.version", "Versión: ") + c["sha"][:12],
                 c["reason"], c["description"],
                 _t("addagent.ui.skills.will_review", "Se revisarán instrucciones, código, recursos y licencia."),
                 _t("addagent.ui.skills.alerts_pending", "Alertas o dependencias: pendiente, sin activar.")]
    else:
        parts = [source.get("note", _t("addagent.ui.skills.local_search", "Búsqueda local por capacidades del formulario.")),
                 _t("addagent.ui.skills.configure_sources", "Configura fuentes y repositorios desde el plan.")]
    parts += [_t("addagent.ui.skills.github_note", "GitHub recibe rutas de consulta; el perfil se compara localmente.")]
    parts += source.get("errors", [])[:2]
    for part in parts:
        right += _wrap(part, max(8, dw))
    return left[:cap], [HL.clip(x, dw) for x in right[:cap]]


# ── acciones ───────────────────────────────────────────────────────────────
def _ir_plan(S):
    """Del formulario al PLAN (todavía no se toca el disco)."""
    nombre = S["vals"].get("nombre", "").strip().lower()
    est, txt = _valida_nombre(nombre)
    if est != "ok":
        S["msg"] = txt
        S["fi"] = ORDEN_F.index("nombre")
        return
    S["view"], S["msg"] = "plan", ""
    _lanza_probe(S)
    _lanza_saldo(S)                      # saldo del provider (0 tokens)
    _lanza_skills(S)


def _params_de_form(S):
    """Los kwargs de agent_admin.create desde el formulario. Los campos de
    texto libre viajan COMPLETOS (con sus saltos de línea) en `intake` —
    create() los guarda en .workspace/agent.json y siembra users/<dueño>.md.
    La semilla del SOUL y el scope se aplanan a UNA línea aquí: van a
    contextos inline del template (CLAUDE.md / IDENTITY) donde un \\n crudo
    rompería el markdown."""
    g = lambda k: (S["vals"].get(k, "").strip() or FIELDS[k][1])  # noqa: E731

    def plano(txt):
        return " · ".join(p.strip() for p in (txt or "").split("\n")
                          if p.strip())

    nombre = S["vals"].get("nombre", "").strip().lower()
    owner = re.sub(r"[^a-z0-9_-]+", "-",
                   g("dueño").strip().lower()).strip("-")
    partes = (("Propósito", plano(g("proposito") or g("rol"))
               or (g("visible") or nombre.capitalize())),
              ("Tono", plano(g("tono"))), ("Estilo", plano(g("estilo"))),
              ("Idioma", plano(g("idioma"))),
              ("Tareas típicas", plano(g("ejemplos"))))
    soul = " ".join("%s: %s." % (t, v) for t, v in partes if v)
    scope = plano(g("alcance"))
    if plano(g("limites")):
        scope = ((scope + " — ") if scope else "") + \
            "Límites: " + plano(g("limites"))
    intake = {k: S["vals"].get(k, "").strip() for k in ORDEN_F
              if S["vals"].get(k, "").strip()}
    params = {"name": nombre, "display": g("visible") or nombre.capitalize(),
              "tagline": plano(g("rol")), "owner": owner, "scope": scope,
              "skills": plano(g("skills")), "soul": soul, "intake": intake,
              "engine": S.get("engine_id") or "claude-code"}
    # toggle del plan: solo viaja si está ON y el backend headless existe
    # (agent_create_job agrega los pasos de la pasada al ver el flag)
    if S.get("personalize") and _perso_disp(S)[0]:
        params["personalize"] = True
    params["skill_source_config"] = S.get("source_config") or skill_source_preferences.load()
    params["community_query"] = S.get("community_query", "")
    if S.get("source_skills"):
        params["source_skills"] = True
        source = S.get("sourcing") or {}
        params["skill_candidates"] = [c for c in source.get("candidates", [])
                                      if c["source_url"] in S.get("skill_selected", set())]
        params["approved_community_repos"] = sorted({c["repo"] for c in params["skill_candidates"] if c.get("discovered_via") == "skills.sh"})
    return params


def _crear_ya(S, params=None):
    """Arranca el JOB (hilo + persistencia) y muestra la vista EN VIVO."""
    lj = S.get("ljob")
    if lj and not lj.get("done"):        # ambos capturan stdio — uno a la vez
        S["msg"] = _t("addagent.ui.msg.conn_in_progress", "hay una conexión en curso — espera a que termine")
        return
    S["job"] = agent_create_job.start(params or _params_de_form(S))
    S["view"], S["msg"] = "run", ""


def _cargar_ya(S):
    """Valida con la radiografía y arranca el JOB de carga (EN VIVO). Los
    bloqueos duros (no existe · colisión) se avisan aquí mismo — sin viajar
    a una pantalla de error."""
    ruta = S["ruta"].strip()
    if not ruta:
        S["msg"] = _t("addagent.ui.msg.type_path", "escribe la ruta de la carpeta del cerebro")
        return
    info = _insp(S)
    if not info.get("exists"):
        S["msg"] = _t("addagent.ui.msg.folder_not_exist", "la carpeta no existe: %s") % _ruta_corta(
            info.get("folder") or ruta)
        return
    if info.get("estado") == "colision":
        S["msg"] = (_t("addagent.ui.msg.collision_cant", "«%s» ya está cargado desde otra carpeta — no se puede")
                    % info.get("name", "?"))
        return
    _ljob_start(S, [(info.get("name") or "", info["folder"])], "cargar")


def _accion(S, key):
    """True = sigue · False = salir al recinto."""
    v = S["view"]
    S["msg"] = ""
    if key == "\x03":
        return False
    # ── menú ──
    if v == "menu":
        if key in ("q", "Q", "\x1b"):
            return False
        if key == "up":
            S["mi"] = (S["mi"] - 1) % len(MENU_OPTS)
        elif key == "down":
            S["mi"] = (S["mi"] + 1) % len(MENU_OPTS)
        elif key in ("\r", "\n") or key in tuple("123"):
            if key in tuple("123"):
                S["mi"] = int(key) - 1
            tok = MENU_OPTS[S["mi"]][0]
            if tok == "crear":
                job = agent_create_job.active()
                if job is not None:          # hay creación viva/terminada:
                    S["job"] = job           # re-enganchar la vista, no
                    S["view"] = "run" if not job.get("done") else "done"
                    return True
                S["view"], S["fi"] = "crear", 0
            elif tok == "cargar":
                S["view"] = "cargar"
            else:
                S["view"], S["di"] = "descubrir", 0
                if not S["buscado"]:
                    _lanza_scan(S)
        return True
    # ── listo (de cargar/descubrir) ──
    if v == "listo":
        if key in ("q", "Q", "\x1b", "\r", "\n"):
            S["view"] = S.get("lret") or "menu"
        return True
    # ── lrun: conexión EN VIVO (load es rápido y sin restos posibles) ──
    if v == "lrun":
        if key in ("\x1b", "q", "Q"):     # atrás; el job sigue y avisa
            S["view"] = (S.get("ljob") or {}).get("origen") or "menu"
        return True
    # ── run: creación EN VIVO ──
    if v == "run":
        if key in ("q", "Q"):
            agent_create_job.cancel()
            S["msg"] = _t("addagent.ui.msg.cancelling", "cancelando — el paso en curso termina solo…")
        elif key == "\x1b":                  # Esc: al recinto; el job sigue
            return False
        return True
    if v == "done" and key in ("down", "tab") and (S.get("job") or {}).get("skill_sourcing"):
        S["view"], S["option_cursor"] = "skill_receipt", 0
        return True
    # ── done: resultado de la creación ──
    if v == "done":
        job = S.get("job") or {}
        if key in ("r", "R") and not job.get("ok"):
            params = dict(job.get("params") or {})
            params.setdefault("name", job.get("name", ""))
            params["engine"] = job.get("engine") or "claude-code"
            agent_create_job.ack()
            _crear_ya(S, params)
            return True
        if key in ("q", "Q", "\x1b", "\r", "\n"):
            ok = job.get("ok")
            agent_create_job.ack()
            S["job"] = None
            if ok:
                S["vals"] = {k: "" for k in ORDEN_F}     # formulario limpio
                S["view"] = "menu"
            else:
                S["view"], S["fi"] = "crear", 0          # campos intactos
        return True
    # ── stale: creación interrumpida detectada ──
    if v == "stale":
        snap = S.get("stale")
        if key in ("l", "L"):
            _ok, det = agent_create_job.cleanup(snap)
            S["stale"], S["view"] = None, "menu"
            S["msg"] = _t("addagent.ui.msg.leftovers_cleaned", "restos limpiados: %s") % det
        elif key in ("r", "R"):
            agent_create_job.cleanup(snap)
            params = dict((snap or {}).get("params") or {})
            params.setdefault("name", (snap or {}).get("name", ""))
            if params.get("name"):
                _crear_ya(S, params)
                S["stale"] = None
            else:
                S["view"], S["msg"] = "menu", _t("addagent.ui.msg.cant_retry", "no pude reintentar (sin datos)")
        elif key in ("q", "Q", "\x1b", "\r", "\n"):
            S["view"] = "menu"               # el snapshot queda — se re-avisa
        return True
    if agent_create_ui.action(S, key, sys.modules[__name__]):
        return True
    if v == "skills":
        candidates = (S.get("sourcing") or {}).get("candidates", [])
        if key in ("up", "down", "tab"):
            S["skill_cursor"] = (S.get("skill_cursor", 0) +
                                  (1 if key != "up" else -1)) % (len(candidates) + 3)
        elif key in ("\r", "\n", " ") and S.get("skill_cursor", 0) >= len(candidates):
            action = S.get("skill_cursor", 0) - len(candidates)
            if action == 0:
                _lanza_skills(S, force=True)
            else:
                S["view"], S["option_cursor"] = ("sources" if action == 1 else "plan"), 0
        elif key in (" ", "\r", "\n") and candidates:
            url = candidates[S.get("skill_cursor", 0)]["source_url"]
            selected = S.setdefault("skill_selected", set())
            if url in selected:
                selected.remove(url)
            elif len(selected) < agent_skill_sources.MAX_SELECTED:
                selected.add(url)
            else:
                S["msg"] = _t("addagent.ui.msg.max_skills", "máximo 5 skills; prioriza las tareas principales")
        elif key in ("r", "R"):
            _lanza_skills(S, force=True)
        elif key in ("s", "S"):
            S["source_skills"], S["view"] = False, "plan"
        elif key in ("\r", "\n", "\x1b", "q", "Q"):
            S["view"] = "plan"
        return True
    # ── Esc desde cualquier sub-vista → atrás ──
    if key == "\x1b":
        S["view"] = "crear" if v == "plan" else "menu"
        return True
    # ── crear (formulario) ──
    if v == "crear":
        if key == "up":
            S["fi"] = (S["fi"] - 1) % (ACCION_ROW + 1)
        elif key in ("down", "tab"):
            S["fi"] = (S["fi"] + 1) % (ACCION_ROW + 1)
        elif key in ("\r", "\n"):
            if S["fi"] == ACCION_ROW:
                _ir_plan(S)
            else:
                k = ORDEN_F[S["fi"]]
                # campo LARGO con texto: Enter = nueva línea (párrafos);
                # vacío = avanza (flujo natural). ↓/Tab siempre avanza.
                if k in ML_FIELDS and S["vals"].get(k, "").strip():
                    if len(S["vals"].get(k, "")) < _maxlen(k):
                        S["vals"][k] = S["vals"].get(k, "") + "\n"
                else:
                    S["fi"] += 1
        elif key in ("\x7f", "\b", "\x08") and S["fi"] < ACCION_ROW:
            k = ORDEN_F[S["fi"]]
            S["vals"][k] = S["vals"].get(k, "")[:-1]
        elif (key and len(key) == 1 and key.isprintable()
              and S["fi"] < ACCION_ROW):
            k = ORDEN_F[S["fi"]]
            if len(S["vals"].get(k, "")) < _maxlen(k):
                S["vals"][k] = S["vals"].get(k, "") + key
        return True
    # ── cargar (ruta) ──
    if v == "cargar":
        if key in ("\r", "\n"):
            _cargar_ya(S)
        elif key in ("\x7f", "\b", "\x08"):
            S["ruta"] = S["ruta"][:-1]
        elif key and len(key) == 1 and key.isprintable() \
                and len(S["ruta"]) < 180:
            S["ruta"] += key
        return True
    # ── descubrir ──
    if v == "descubrir":
        n = len(S["found"])
        ocupado = (S.get("scan") or {}).get("state") == "busy"
        if key == "up" and n:
            S["di"] = (S["di"] - 1) % n
        elif key == "down" and n:
            S["di"] = (S["di"] + 1) % n
        elif key in ("r", "R") and not ocupado:
            _lanza_scan(S)
        elif key in ("\r", "\n") and n and not ocupado:
            a = S["found"][S["di"]]
            est = S["estados"].get(a["name"], "")
            if est == "otro":
                S["msg"] = (_t("addagent.ui.msg.collision_cant_here", "«%s» ya está cargado desde otra carpeta — no se puede conectar desde aquí") % a["name"])
            else:
                _ljob_start(S, [(a["name"], a["brain"])], "descubrir")
        elif key in ("a", "A") and n and not ocupado:
            items = [(a["name"], a["brain"]) for a in S["found"]
                     if S["estados"].get(a["name"]) in ("nuevo", "")
                     or S["estados"].get(a["name"], "").startswith("err")]
            if items:
                _ljob_start(S, items, "descubrir")
            else:
                S["msg"] = _t("addagent.ui.msg.no_new_brains", "no hay cerebros nuevos que conectar")
        elif key in ("q", "Q"):
            S["view"] = "menu"
        return True
    return True


# ── ticks de 2º plano (job de creación · probe de harnesses) ────────────────
def _busy(S):
    """¿Hay algo vivo que amerite redibujar sin teclas?"""
    job = S.get("job")
    lj = S.get("ljob")
    return (S["view"] in ("run", "lrun")
            or (S.get("harn") or {}).get("state") == "busy"
            or (S.get("scan") or {}).get("state") == "busy"
            or (S.get("saldo") or {}).get("state") == "busy"
            or (S.get("sourcing") or {}).get("state") == "busy"
            or bool(lj and not lj.get("done"))
            or bool(job and not job.get("done") and S["view"] == "menu"))


def _tick(S):
    """Transiciones que no dependen del teclado. True = algo cambió."""
    job = S.get("job")
    if S["view"] == "run" and job is not None and job.get("done"):
        S["view"] = "done"
        S["msg"] = ""
        return True
    lj = S.get("ljob")
    if lj is not None and lj.get("done"):
        S["ljob"] = None
        S["insp"], S["defs"] = None, {}          # la radiografía ya cambió
        if lj.get("res_map"):
            S["estados"].update(lj["res_map"])
        S["lret"] = lj.get("origen") or "menu"
        vb_ok, vb_fail = ((_t("addagent.ui.verb.connected", "conectado"), _t("addagent.ui.verb.connect", "conectar"))
                          if lj.get("origen") == "descubrir"
                          else (_t("addagent.ui.verb.loaded", "cargado"), _t("addagent.ui.verb.load", "cargar")))
        if lj["bulk"]:
            d = {"bulk": [(s["key"], s["st"], s.get("note", ""))
                          for s in lj["steps"]],
                 "ok": lj["ok"], "verbo": vb_fail, "warns": lj["warns"]}
            resumen = _t("addagent.ui.tick.connected_summary", "conectados %s") % lj["res"]
        else:
            name = lj["res"] if lj["ok"] else (lj["items"][0][0] or "?")
            d = {"name": name, "ok": lj["ok"],
                 "error": lj.get("error", ""),
                 "verbo": vb_ok if lj["ok"] else vb_fail,
                 "ruta": lj["items"][0][1], "warns": lj["warns"],
                 "dur": _mmss((lj.get("t1") or time.monotonic())
                              - lj["t0"])}
            resumen = ("%s: %s" % (vb_ok, name)) if lj["ok"] \
                else _t("addagent.ui.tick.failed_summary", "no se pudo %s: %s") % (vb_fail, lj.get("error", ""))
        if lj["ok"] and lj.get("origen") == "cargar":
            S["ruta"] = ""                       # input limpio para otra
        if S["view"] == "lrun":
            S["done"], S["view"], S["msg"] = d, "listo", ""
        else:                                    # se salió con Esc — avisar
            S["msg"] = resumen
        return True
    harn = S.get("harn") or {}
    if harn.get("state") == "done" and not harn.get("_visto"):
        harn["_visto"] = True
        return True
    scan = S.get("scan") or {}
    if scan.get("state") == "done" and not scan.get("_visto"):
        scan["_visto"] = True
        return True
    sourcing = S.get("sourcing") or {}
    if sourcing.get("state") == "done" and not sourcing.get("_visto"):
        sourcing["_visto"] = True
        return True
    sal = S.get("saldo") or {}
    if sal.get("state") == "done" and not sal.get("_visto"):
        sal["_visto"] = True
        return True
    return False


# ── drivers (mismo patrón que actualizaciones_tui: cadencia busy) ───────────
import responsive_ui as _responsive
render = _responsive.renderer(render, _t("addagent.ui.title.menu.l", "AGREGAR AGENTE"))
_accion = _responsive.action(_accion)

def _draw(tout, S, first=False):
    w, h = _size()
    try:
        _responsive.paint(tout, render(S, w, h), first=first)
    except Exception:
        pass


def _read_key_unix(fd, select):
    """Una tecla: flechas (ESC [ X), Tab, y UTF-8 MULTIBYTE (á/ñ/é en los
    campos del formulario — leer 1 byte rompía los acentos)."""
    b = os.read(fd, 1)
    if not b:
        return ""
    c = b[0]
    if c == 0x1b:
        if select.select([fd], [], [], 0.05)[0]:
            seq = os.read(fd, 2).decode("utf-8", "replace")
            return {"[A": "up", "[B": "down", "[C": "right",
                    "[D": "left", "[Z": "up"}.get(seq, "\x1b")
        return "\x1b"
    if c == 0x09:
        return "tab"
    if c < 0x80:
        return chr(c)
    extra = 1 if c < 0xE0 else (2 if c < 0xF0 else 3)
    try:
        if select.select([fd], [], [], 0.02)[0]:
            b += os.read(fd, extra)
    except Exception:
        pass
    return b.decode("utf-8", "replace")


def _run_unix(S):
    import select
    import termios
    import tty
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        tout = open("/dev/tty", "w")
    except Exception:
        return _sin_tty()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h\033[?25l")
        _draw(tout, S, first=True)
        prev_busy = True
        while True:
            busy = _busy(S)
            ready = select.select([fd], [], [], 0.12 if busy else 0.5)[0]
            cambio = _tick(S)
            if not ready:
                _draw(tout, S)
                prev_busy = busy
                continue
            prev_busy = busy
            key = _read_key_unix(fd, select)
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
    return 0


def _run_windows(S):
    import msvcrt
    # referencia REAL a stdout ANTES de que el worker capture sys.stdout
    # (la UI escribe por tout; el worker cambia el binding global)
    tout = sys.stdout
    tout.write("\033[?1049h\033[?25l")
    try:
        _draw(tout, S, first=True)
        last = 0.0
        while True:
            cambio = _tick(S)
            now = time.monotonic()
            if (cambio or _busy(S)) and now - last > 0.12:
                _draw(tout, S)
                last = now
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
            last = time.monotonic()
    finally:
        try:
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
        except Exception:
            pass
    return 0


def _sin_tty():
    """Sin terminal interactiva: señala el camino CLI y no truena."""
    print(_t("addagent.ui.notty.need_tty", "agregar agente necesita una terminal interactiva."))
    print(_t("addagent.ui.notty.cli", "por CLI:  python3 agent_admin.py create <nombre> [--engine claude-code|codex] …  ·  python3 agent_admin.py load <carpeta>"))
    return 0


def _estado_inicial():
    S = {"view": "menu", "mi": 0, "fi": 0, "di": 0, "msg": "",
         "vals": {k: "" for k in ORDEN_F},
         "ruta": "", "found": [], "estados": {}, "buscado": False,
         "done": {}, "job": None, "harn": None, "engine_id": None,
         "stale": None, "insp": None, "ljob": None, "lret": "menu",
         "scan": None, "defs": {}, "personalize": False, "pbk": {},
         "saldo": None, "source_skills": True, "sourcing": None,
         "skill_selected": set(), "skill_cursor": 0,
         "source_config": skill_source_preferences.load(), "option_cursor": 0, "community_query": ""}
    # RESUMIBLE: ¿hay una creación viva (este proceso) o interrumpida (otro
    # proceso murió a medias)? Re-enganchar la vista — jamás en silencio.
    job = agent_create_job.active()
    if job is not None:
        S["job"] = job
        S["view"] = "run" if not job.get("done") else "done"
        return S
    snap = agent_create_job.stale()
    if snap:
        S["stale"], S["view"] = snap, "stale"
    return S


def run():
    """Punto de entrada desde el menú (loop-back: vuelve al recinto)."""
    S = _estado_inicial()
    try:
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactivo = False
    if not interactivo:
        return _sin_tty()
    try:
        if os.name == "nt":
            return _run_windows(S)
        return _run_unix(S)
    except Exception as e:
        try:
            sys.stdout.write("\033[?25h\033[?1049l")
        except Exception:
            pass
        print(_t("addagent.ui.error_generic", "agregar agente: %s") % e)
        return 0


if __name__ == "__main__":
    sys.exit(run())
