#!/usr/bin/env python3
"""WORKSPACE · settings.py — store + registro UNIFICADO de configuración (backend).

EL PROBLEMA: la config de WORKSPACE vivía DISPERSA — heartbeat.json (modo/cap/
grace), kill-switches por env (WORKSPACE_NO_*), paths.local.json (transport),
cleanupPeriodDays (settings de Claude Code), usage.json… Sin un lugar donde
VER qué es configurable ni un canal único para cambiarlo.

ESTE MÓDULO ES: (1) el STORE per-máquina (~/.claude/workspace/settings.json),
(2) el REGISTRO declarativo de todo lo configurable (SETTINGS_SCHEMA, por
grupos) y (3) el sub-registro de JOBS/crons conocidos (JOBS). Es la fuente
que el futuro front (paneles del banner + pantalla de config) renderizará.

QUÉ NO ES: ni un scheduler (eso es `workspace cron`/C6 — aquí solo viven los
flags enable/disable que ese scheduler LEERÁ), ni el dueño de los mecanismos
existentes — heartbeat.json, paths.local.json y ~/.claude/settings.json
siguen funcionando; este módulo los representa y, donde tiene sentido,
delega en ellos (campo `delegated` en el schema).

PRECEDENCIA (back-compat total — nada del comportamiento previo se rompe):
  · env vars (WORKSPACE_NO_*) GANAN siempre sobre el setting equivalente.
  · heartbeat.json, si existe, GANA sobre latido.* del store (el canal
    histórico se respeta; `set()` sobre latido.* sincroniza ambos).
  · consumidores importan este módulo FALLA-SUAVE: si settings.py no está
    o el store es ilegible, todo se comporta como antes (defaults).

API:  get(k) · get_stored(k) · set(k, v) · set_stored(k, v) · reset(k) ·
      all() · jobs_status() · is_job_enabled(id) · set_job_enabled(id, b) ·
      enabled(k) (variante jamás-levanta para hooks) · import_heartbeat().

CLI:  python3 settings.py list | get <k> | set <k> <v> | reset <k>
      python3 settings.py jobs [enable|disable <id>] | migrate | --json

Garantías: stdlib puro, cross-platform (3.9+); escritura ATÓMICA
(tmp + os.replace); falla-suave (store corrupto → defaults); PRESERVA claves
desconocidas del store (forward-compat); `set` inválido → ValueError SIN
escribir; jamás guarda credenciales (solo nombres/flags). Amputable (C10):
borrar este archivo deja todo como estaba (los consumidores lo importan
falla-suave).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

try:                                      # N8 — lock cross-platform (amputable)
    from olock import file_lock, LockTimeout
except Exception:                         # sin olock → degrada a sin-lock
    file_lock, LockTimeout = None, None


def _with_store_lock(fn):
    """G1: serializa el read-modify-write del store (load→mutate→save NO es
    atómico aunque _save_store sí lo sea). Sin olock / timeout → degrada a
    sin-lock (mejor escribir que perder el cambio; era el estado previo)."""
    if file_lock is None:
        return fn()
    try:
        with file_lock(store_path(), timeout=5):
            return fn()
    except LockTimeout:
        return fn()

GROUPS = ("latido", "jobs", "hooks", "modelos", "budget", "cerebro",
          "agentes", "ui", "otros")

_SENTINEL = object()


# ── rutas (funciones, no constantes: respetan HOME parchado en tests) ──────
def _workspace_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def store_path():
    return os.path.join(_workspace_dir(), "settings.json")


def _heartbeat_json():
    return os.path.join(_workspace_dir(), "heartbeat.json")


def _paths_local():
    return os.path.join(_workspace_dir(), "paths.local.json")


def _claude_settings():
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _json_corrupt(path):
    """True si `path` EXISTE pero no parsea como JSON (≠ 'no existe').
    Espejo de install.json_corrupt (R3-F1): _read_json colapsa ambos casos a
    {} — quien va a REESCRIBIR el archivo debe distinguirlos para no pisar un
    settings corrupto en silencio (SEC/Argus: `set()` clobbereaba un
    ~/.claude/settings.json ilegible con `{cleanupPeriodDays: …}` a secas).
    El caso 'no existe' NO es corrupto: crear desde cero sigue siendo normal."""
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            json.load(fh)
        return False
    except Exception:
        return True


def _write_json_atomic(path, data):
    """Escritura atómica: tmp en el MISMO dir + os.replace (cross-platform).
    Nunca deja el archivo a medias; limpia el tmp si algo truena."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# ── helpers de schema dinámico (falla-suave con listas estáticas) ──────────
def _engine_choices():
    """Motores instalados (engines/*.py, sin '_'). Falla-suave → lista fija."""
    try:
        d = os.path.join(ROOT, "engines")
        names = sorted(f[:-3].replace("_", "-") for f in os.listdir(d)
                       if f.endswith(".py") and not f.startswith("_"))
        return names or ["claude-code"]
    except Exception:
        return ["claude-code", "stub"]


def _agent_choices():
    """Agentes del registry (agents/registry.json). Falla-suave → lista fija."""
    try:
        reg = _read_json(os.path.join(ROOT, "agents", "registry.json"))
        names = [a.get("name", "") for a in reg.get("agents", [])
                 if a.get("name")]
        return names or ["zenith", "atlas"]
    except Exception:
        return ["zenith", "atlas"]


def _theme_choices():
    """Temas instalados (themes/<id>/theme.json — motor hubtheme.py).
    Falla-suave → el par conocido. 'olympo' (default) SIEMPRE presente."""
    try:
        d = os.path.join(ROOT, "themes")
        names = sorted(n for n in os.listdir(d)
                       if os.path.isfile(os.path.join(d, n, "theme.json")))
        if "olympo" not in names:
            names.insert(0, "olympo")
        return names
    except Exception:
        return ["olympo", "cyberpunk"]


def _theme_choices_live():
    """Temas instalados SEGÚN EL MOTOR (hubtheme.available(), consultado EN
    VIVO al validar) — la fuente para el DEV PANEL (ui.web_theme: todos los
    temas). Import lazy (hubtheme importa settings también lazy — sin ciclo).
    Falla-suave: cualquier problema → el snapshot de _theme_choices()."""
    import hubtheme
    return [t["id"] for t in hubtheme.available()]


# Temas TUI-ready para el HUB (recinto): el subconjunto CURADO que el hub
# OFRECE/valida (los temas de agente — zenith/atlas/… — y los sin bloque
# `tui` quedan fuera; siguen instalados para el dev panel vía ui.web_theme).
# 2026-10-02 (pedido del socio — poda + familia rosé): de los temas viejos
# quedan SOLO mono, cyberpunk (retuneado: neones a tono joya) y rose;
# olympo/papel/slate/bosque se borraron de themes/. Encima entra la familia
# rosé — durazno / lavanda / salvia / bruma — sutiles como rose, matices
# distintos. OJO: esta lista va SINCRONIZADA con hubtheme.TUI_PENDIENTES
# (lo que el picker del hub oculta); si divergen, el socio elige un tema que
# settings rechaza en silencio (bug documentado en test_settings).
_TUI_THEMES = ("rose", "mono", "cyberpunk",
               "durazno", "lavanda", "salvia", "bruma")


def _tui_theme_choices():
    """Temas del HUB (ui.theme): el subconjunto TUI-ready presente en themes/.
    'olympo' SIEMPRE (fallback embebido). Falla-suave."""
    try:
        inst = set(_theme_choices())
        return [t for t in _TUI_THEMES if t in inst] or ["olympo"]
    except Exception:
        return list(_TUI_THEMES)


def _tui_theme_choices_live():
    """Live (mismo patrón que _tui_theme_choices, vía el motor)."""
    try:
        import hubtheme
        inst = {t["id"] for t in hubtheme.available()}
        return [t for t in _TUI_THEMES if t in inst] or ["olympo"]
    except Exception:
        return _tui_theme_choices()


# El DEV PANEL cura su SWITCHER en hubtheme.web_picker() (WEB_THEMES); la
# VALIDACIÓN de ui.web_theme queda PERMISIVA (todo tema instalado, como el
# ui.theme viejo) — el socio solo elige desde el switcher curado, pero un tema
# vía env/directo no se rechaza. Reusa _theme_choices/_theme_choices_live.


def _layout_choices():
    """Layouts del hub SEGÚN EL REGISTRO (hublayout.available() — NUNCA
    hardcodeados aquí). Falla-suave → solo el default."""
    try:
        import hublayout
        ids = [L["id"] for L in hublayout.available()]
        return ids or ["clasico"]
    except Exception:
        return ["clasico"]


def _layout_choices_live():
    """Layouts consultados EN VIVO al validar (mismo patrón que ui.theme:
    el registro manda, el snapshot `choices` es solo display). Import lazy
    (hublayout importa settings también lazy — sin ciclo)."""
    import hublayout
    return [L["id"] for L in hublayout.available()]


# Palabras que marcan un setting como INSEGURO para anclar al hub (nunca se
# muestran/ciclan desde el recinto: paths, tokens, credenciales).
_PIN_UNSAFE = ("path", "token", "secret", "cred", "key", "passwd", "pass",
               "auth", "url", "dir", "file")


def _hub_pin_ok(key):
    """¿Es SEGURO anclar `key` al hub? (ui.hub_pins). Solo settings del
    schema de tipo enum/bool (ciclables sin riesgo) cuyo nombre no huela a
    path/credencial. Falla-suave: cualquier duda → False (se omite el pin).
    Late-binding sobre _BY_KEY (se llama en runtime, no al import)."""
    try:
        spec = _BY_KEY.get(key)
        if not spec or spec.get("readonly"):
            return False
        if spec.get("type") not in ("enum", "bool"):
            return False
        low = key.lower()
        return not any(bad in low for bad in _PIN_UNSAFE)
    except Exception:
        return False


# ── REGISTRO declarativo ───────────────────────────────────────────────────
# Cada setting: key (grupo.nombre) · group · label · type (bool/enum/int/str/
# map) · default · choices? (enum) · range? (int, inclusivo) · help · applies
# (cómo/dónde se consume HOY) · scaffold (True = aún sin consumidor real; el
# flag queda listo para cuando exista) · delegated (el valor efectivo vive en
# otro mecanismo; get() lo lee de ahí) · readonly (set() → error, editar el
# mecanismo dueño).
SETTINGS_SCHEMA = (
    # ── latido (heartbeat — cola de trabajo autónomo) ──
    {"key": "latido.mode", "group": "latido", "label": "Modo del latido",
     "type": "enum", "default": "auto", "choices": ("auto", "manual", "off"),
     "help": "auto = el cron puede lanzar solo · manual = solo reporta · off = apagado.",
     "applies": "heartbeat.get_config(); heartbeat.json GANA si existe (set sincroniza ambos)."},
    {"key": "latido.budget_cap_pct", "group": "latido",
     "label": "Tope de presupuesto 5h (%)", "type": "int", "default": 85,
     "range": (50, 95),
     "help": "Colchón del plan 5h: con five_hour_pct >= tope, el latido pausa.",
     "applies": "heartbeat.budget_ok(); heartbeat.json GANA si existe (set sincroniza ambos)."},
    {"key": "latido.grace_min", "group": "latido",
     "label": "Gracia tras actividad (min)", "type": "int", "default": 12,
     "range": (0, 1440),
     "help": "Minutos de gracia tras actividad del socio antes de lanzar trabajo autónomo.",
     "applies": "heartbeat.state() → el cron; heartbeat.json GANA si existe."},
    {"key": "latido.quiet_hours", "group": "latido",
     "label": "Horas de silencio", "type": "str", "default": "",
     "help": "Rango HH:MM-HH:MM en que el latido no lanza (ej. 01:00-07:00; "
             "cruza medianoche sin problema, ej. 22:30-06:00).",
     "applies": "heartbeat.decide() devuelve action=quiet dentro del rango "
                "(in_quiet_hours); heartbeat.json GANA si existe."},
    {"key": "latido.autonomous_model", "group": "latido",
     "label": "Modelo del trabajo autónomo", "type": "str", "default": "",
     "scaffold": True,
     "help": "Modelo a usar en lanzamientos autónomos (vacío = el del agente).",
     "applies": "futuro: el cron lo pasará al lanzar la cola."},
    {"key": "latido.intensity", "group": "latido",
     "label": "Intensidad del latido", "type": "enum", "default": "normal",
     "choices": ("light", "normal", "deep", "max"),
     "help": "Qué tan potente es el trabajo por tick del heartbeat: light = 1 item "
             "chico, mínimos tokens · normal = 1 item con tests + commit · deep = "
             "varios items o 1 grande, puede usar subagentes · max = workflow "
             "multi-agente exhaustivo por tick (muchos tokens).",
     "applies": "heartbeat.intensity() / heartbeat.intensity_profile(); el protocolo "
                "del latido (protocols/heartbeat/) lo lee para dimensionar el trabajo."},
    {"key": "latido.max_tokens_per_tick", "group": "latido",
     "label": "Tope de tokens por tick (0 = sin tope explícito)", "type": "int",
     "default": 0, "range": (0, 2_000_000),
     "help": "Tope SUAVE de tokens de salida por tick del heartbeat. 0 = usar el "
             "perfil de `latido.intensity`. >0 lo overridea con un número exacto.",
     "applies": "heartbeat.intensity_profile()['max_tokens']."},

    # ── hooks (kill-switches — el env WORKSPACE_NO_* SIEMPRE gana) ──
    {"key": "hooks.skill_review", "group": "hooks",
     "label": "Skill review (SessionEnd)", "type": "bool", "default": True,
     "help": "Revisión ligera de skills al cerrar sesión (claude headless con throttle).",
     "applies": "hooks/skill_review.py; env WORKSPACE_NO_SKILL_REVIEW=1 gana."},
    {"key": "hooks.transcript_backup", "group": "hooks",
     "label": "Backup de transcripts (Y2b)", "type": "bool", "default": True,
     "help": "Respaldo del .jsonl crudo a ~/.claude/workspace/transcripts-backup/.",
     "applies": "hooks/transcript_backup.py; env WORKSPACE_NO_TRANSCRIPT_BACKUP=1 gana."},
    {"key": "hooks.memory_flush", "group": "hooks",
     "label": "Memory flush (PreCompact, N2)", "type": "bool", "default": True,
     "help": "Antes de compactar: snapshot del crudo + breadcrumb al journal + rastro JSONL.",
     "applies": "hooks/memory_flush.py; env WORKSPACE_NO_MEMORY_FLUSH=1 gana."},
    {"key": "hooks.security_guidance", "group": "hooks",
     "label": "Security guidance (PostToolUse, N15)", "type": "bool",
     "default": True,
     "help": "Advertencias no-bloqueantes al escribir código con patrones de riesgo.",
     "applies": "hooks/security_guidance.py; env WORKSPACE_NO_SECURITY_GUIDANCE=1 gana."},
    {"key": "hooks.telemetry", "group": "hooks",
     "label": "Telemetría en vivo (Pre/PostToolUse, N-telem)", "type": "bool",
     "default": True,
     "help": "Registra metadata de herramientas (tool_name, timing, ok) "
             "en ~/.claude/workspace/telemetry/ para Mission Control en vivo. "
             "NUNCA registra tool_input ni contenido.",
     "applies": "hooks/telemetry.py; env WORKSPACE_NO_TELEMETRY=1 gana."},

    # ── modelos ──
    {"key": "modelos.default_engine", "group": "modelos",
     "label": "Motor por default", "type": "enum", "default": "claude-code",
     "choices": tuple(_engine_choices()),
     "help": "Motor cuando un agente no declara el suyo (precedencia: cli > env > agent.json > esto).",
     "applies": "dispatch.py — fallback final de la selección de motor."},
    {"key": "modelos.task_routing", "group": "modelos",
     "label": "Routing por tarea", "type": "str", "default": "",
     "scaffold": True,
     "help": "Política de routing de modelos por tipo de tarea (diseño pendiente).",
     "applies": "futuro: model_resolver / dispatch."},

    # ── budget (límites de consumo — DOS canales distintos, no confundir) ──
    # (a) auth/SUSCRIPCIÓN (plan 5h): el colchón es latido.budget_cap_pct —
    #     el % del plan a partir del cual el latido pausa (arriba, en latido).
    # (b) API KEY: este tope de tokens por sesión para engines de API.
    {"key": "budget.api_token_limit", "group": "budget",
     "label": "Límite de tokens por sesión (API)", "type": "int",
     "default": 0, "range": (0, 1000000000),
     "help": "Tope de tokens por sesión para motores con API KEY "
             "(0 = sin límite). SOLO aplica a engines de API; para "
             "auth/suscripción el colchón es latido.budget_cap_pct "
             "(% del plan 5h a partir del cual el latido pausa).",
     "applies": "engines de API (cuando exista uno): cortan la sesión al "
                "llegar al tope ANTES del siguiente request (guard de "
                "sesión). El motor claude-code (suscripción) NO lo usa — "
                "su colchón es latido.budget_cap_pct."},

    # ── cerebro ──
    {"key": "cerebro.boot_profile", "group": "cerebro",
     "label": "Perfil de boot", "type": "enum", "default": "full",
     "choices": ("full", "lite"), "scaffold": True,
     "help": "full = BOOT/ canónico · lite = digest ≤4k de boot_lite.py (N17).",
     "applies": "futuro: session_start / motor #2 elegirán el perfil."},
    {"key": "cerebro.dreaming_auto", "group": "cerebro",
     "label": "Dreaming automático", "type": "bool", "default": False,
     "scaffold": True,
     "help": "Correr la destilación de memoria (dream.py/nightly.py) sin pedirla a mano.",
     "applies": "futuro: scheduler C6 (ver job consolidador-nocturno)."},
    {"key": "cerebro.cleanup_period_days", "group": "cerebro",
     "label": "Retención de transcripts (días)", "type": "int",
     "default": 3650, "range": (30, 36500), "delegated": True,
     "help": "cleanupPeriodDays de Claude Code — los crudos son materia prima de la memoria.",
     "applies": "~/.claude/settings.json (get lee de ahí; set escribe ahí — el doctor lo re-sube si baja de 3650)."},

    # ── agentes ──
    {"key": "agentes.default_agent", "group": "agentes",
     "label": "Agente por default", "type": "enum", "default": "zenith",
     "choices": tuple(_agent_choices()), "scaffold": True,
     "help": "Agente preseleccionado en el recinto/picker de WORKSPACE.",
     "applies": "futuro: front.py preseleccionará esta urna."},
    {"key": "agentes.auto_mode", "group": "agentes",
     "label": "Auto-mode en sesiones interactivas", "type": "bool",
     "default": True,
     "help": "POLÍTICA DEL EQUIPO: las sesiones interactivas lanzadas desde "
             "el menú/launchers (`workspace`, `zenith`, …) arrancan en "
             "auto-aceptar — `claude --permission-mode acceptEdits`, el "
             "mecanismo OFICIAL de Claude Code (el mismo 'accept edits on' "
             "del shift+tab; NUNCA bypassPermissions/--dangerously-skip-"
             "permissions). off = arrancan en el modo normal de Claude Code. "
             "Reversible en vivo: aplica al siguiente lanzamiento.",
     "applies": "engines/claude_code.launch() agrega el flag al comando; un "
                "--permission-mode explícito del socio siempre gana."},
    {"key": "agentes.transport", "group": "agentes",
     "label": "Transporte de sync por agente", "type": "map", "default": {},
     "delegated": True, "readonly": True,
     "help": "Mapa agente → 'obsidian-sync'|'git' (default: obsidian-sync para todos).",
     "applies": "paths.local.json → transport (dispatch.brain_transport); editar AHÍ, no aquí."},

    # ── ui ──
    {"key": "ui.stars", "group": "ui", "label": "Cielo estrellado",
     "type": "bool", "default": True,
     "help": "Campo de estrellas estático del recinto (front.py).",
     "applies": "front.py; env WORKSPACE_NO_STARS=1 gana."},
    {"key": "ui.anim", "group": "ui", "label": "Animaciones",
     "type": "bool", "default": True,
     "help": "Menú animado del recinto y banner animado (sin esto: estático + picker).",
     "applies": "front.py + banner/render.py; env WORKSPACE_NO_ANIM=1 gana."},
    {"key": "ui.lang", "group": "ui", "label": "Idioma",
     "type": "enum", "default": "es", "choices": ("es", "en"),
     "help": "Idioma de la interfaz que VE EL CLIENTE (menú del hub, "
             "onboarding, saludos de agente). Ausente = español (el default "
             "de siempre, sin cambios para instalaciones existentes). Las "
             "pantallas de desarrollo quedan en español por diseño. "
             "env WORKSPACE_LANG gana. Se cambia EN VIVO desde el menú "
             "(«Idioma») y es el paso 0 del onboarding.",
     "applies": "i18n.lang() lo lee e i18n.t() pinta cada cadena; el toggle "
                "«Idioma» del hub y el paso 0 del onboarding lo persisten "
                "vía i18n.set_lang()."},
    {"key": "ui.background", "group": "ui", "label": "Fondo independiente",
     "type": "enum", "default": "tema",
     "choices": ("tema", "negro", "grafito", "azul", "verde", "violeta", "personalizado"),
     "help": "Cambia solo el fondo; tema recupera el fondo del tema activo.",
     "applies": "tuitheme.palette() y theme.apply_colors()."},
    {"key": "ui.background_custom", "group": "ui", "label": "Color de fondo propio",
     "type": "str", "default": "#101018",
     "help": "Color #RRGGBB; elige personalizado en Fondo independiente.",
     "applies": "tuitheme.palette() y theme.apply_colors()."},
    {"key": "ui.theme", "group": "ui", "label": "Tema del hub",
     "type": "enum", "default": "bruma",   # 2026-10 (socio): la familia rosé es la insignia; bruma (hermana neblinosa de rose) = default de instalación nueva, CON color
     # SOLO temas TUI-ready (_TUI_THEMES: mono + cyberpunk + la familia rosé)
     # — selector curado por el socio 2026-10-02; los demás temas siguen instalados
     # para el DEV PANEL (ui.web_theme). choices = snapshot al import;
     # choices_fn valida en vivo.
     "choices": tuple(_tui_theme_choices()), "choices_fn": _tui_theme_choices_live,
     "help": "Tema visual del HUB/TUI del recinto (front.py/banner/config_tui). "
             "Acotado a los temas TUI-ready (mono, cyberpunk, rose, durazno, "
             "lavanda, salvia, bruma). El dev panel web tiene su propio tema "
             "(ui.web_theme, todos disponibles). env WORKSPACE_THEME gana siempre.",
     "applies": "tuitheme.palette() → front.py/banner/config_tui pintan el "
                "recinto. El pin de configs rápidas del hub lo cicla."},
    {"key": "ui.web_theme", "group": "ui", "label": "Tema del dev panel (web)",
     "type": "enum", "default": "olympo",
     # SWITCHER curado a WEB_THEMES (hubtheme.web_picker), validación PERMISIVA
     # (todo tema instalado — el socio elige desde el switcher, pero env/directo
     # no se rechaza). INDEPENDIENTE del hub (ui.theme).
     "choices": tuple(_theme_choices()), "choices_fn": _theme_choices_live,
     "help": "Tema visual del DEV PANEL web (dashboard). INDEPENDIENTE del hub "
             "(ui.theme): aquí van los temas de agente + cyberpunk (zenith, "
             "atlas, argus, cyberpunk). Cambiarlo NO toca el tema del hub. env "
             "WORKSPACE_THEME gana. Se persiste con el switcher del panel.",
     "applies": "hubtheme.resolve_id() lo lee para servir el skin del dev panel "
                "(dashboard.py --dev); POST /api/theme lo persiste (dash/dev/"
                "temas.py). El hub/TUI NO lo usa (usa ui.theme)."},
    {"key": "ui.layout", "group": "ui", "label": "Layout del hub",
     "type": "enum", "default": "dia",
     # mismo patrón que ui.theme: snapshot al import para display, validación
     # EN VIVO contra el registro (hublayout.available()) — nada hardcodeado.
     "choices": tuple(_layout_choices()), "choices_fn": _layout_choices_live,
     "help": "ESTRUCTURA del hub (front.py) — eje INDEPENDIENTE del tema: "
             "cualquier layout combina con cualquier tema. dia = calendario + "
             "pulso (default); clasico = el recinto centrado de siempre. "
             "env WORKSPACE_LAYOUT gana siempre (probar sin persistir).",
     "applies": "hublayout.resolve_id() → front.py dibuja el hub con la "
                "estructura del layout activo; el picker de Config (sección "
                "LAYOUT) persiste aquí."},
    {"key": "ui.split", "group": "ui", "label": "Terminal partida",
     "type": "bool", "default": False,
     "help": "Al elegir agente en el hub, el chat abre PARTIDO: chat a la "
             "izquierda + panel del pipeline en vivo a la derecha (mismo "
             "armado que `workspace split`; multiplexer según "
             "ui.split_backend). Apagado = arranque de siempre (default).",
     "applies": "front.launch → multiplexer.open_split, SOLO después de "
                "elegir agente (el hub/menú no pasan por el multiplexer). "
                "Sin multiplexer/TTY, anidado o Windows → arranque normal "
                "con aviso (mux.fallback)."},
    {"key": "ui.split_backend", "group": "ui",
     "label": "Backend de la terminal partida",
     "type": "enum", "default": "auto",
     "choices": ("auto", "tmux", "herdr"),
     "help": "Con qué multiplexer se arma la pantalla partida (con ui.split "
             "prendido). auto = herdr si está instalado y responde, si no "
             "tmux. herdr sin herdr disponible → tmux con aviso. env "
             "WORKSPACE_SPLIT_BACKEND gana (probar sin persistir).",
     "applies": "multiplexer.pick_backend() → front.launch / `workspace "
                "split`. El hub/menú no cambian (regla #1); con ui.split "
                "apagado este setting ni se consulta."},
    {"key": "ui.split_pane", "group": "ui",
     "label": "Contenido del pane derecho",
     "type": "enum", "default": "panel",
     "choices": ("board", "panel"),
     "help": "Qué corre en el pane derecho del split. panel (default) = el "
             "PANEL con menú (Sesiones / Workflows en vivo / Bus / Config / "
             "Delegar) + header de identidad del agente; navegable con "
             "1-9/←→/Tab al enfocar el pane. board = solo la pipeline pelona "
             "en vivo (el modo clásico, sin menú).",
     "applies": "mux.right_pane_cmd() elige board (wf board --persist) vs "
                "panel (front.py panel --agent). Extensible: se agregan "
                "vistas en panel.VIEWS."},
    {"key": "ui.emblem", "group": "ui", "label": "Emblema del banner",
     "type": "enum", "default": "default",
     "choices": ("default", "minimal", "none"), "scaffold": True,
     "help": "Variante del emblema/escudo del banner.",
     "applies": "futuro: banner/render.py."},
    {"key": "ui.info_rows", "group": "ui", "label": "Filas de info del banner",
     "type": "str", "default": "", "scaffold": True,
     "help": "CSV de filas a mostrar bajo el banner (vacío = todas).",
     "applies": "futuro: front.build_info_rows()."},
    {"key": "ui.hub_pins", "group": "ui", "label": "Configs ancladas al hub",
     # Default SOLO el tema (pedido del socio 2026-10-02): la sección del hub se
     # llama ahora PERSONALIZACIÓN y es para tema/colores/customizables.
     # Layout y latido siguen vivos (settings/config TUI/CLI) — quien los
     # quiera de vuelta en el hub puede re-anclarlos desde la Config.
     "type": "list", "default": ["ui.theme", "ui.background"],
     "max_items": 5, "member_ok": lambda k: _hub_pin_ok(k),
     "help": "Lista de settings (keys del schema) que el hub muestra en su "
             "sección PERSONALIZACIÓN para acceso rápido — label + valor "
             "actual, sin entrar a la Config completa. Solo enum/bool SEGUROS "
             "(nada de paths/credenciales); keys inexistentes o inseguras se "
             "omiten. Máx 5 (espacio del recinto).",
     "applies": "hublayout.hub_pins_lines() → el bloque de la sección "
                "PERSONALIZACIÓN en el recinto clásico (front.py) y en el "
                "layout centro."},

    # ── otros ──
    {"key": "otros.update_channel", "group": "otros",
     "label": "Canal de actualización", "type": "enum", "default": "stable",
     "choices": ("stable", "main"), "delegated": True,
     "help": "stable = equipo · main = desarrollo. Hoy el canal REAL es la rama git del repo WORKSPACE.",
     "applies": "get() refleja la rama git actual si es legible; set guarda la preferencia que `workspace update` leerá."},
    {"key": "otros.notify_on_done", "group": "otros",
     "label": "Notificar al terminar", "type": "bool", "default": False,
     "scaffold": True,
     "help": "Notificación del sistema cuando un trabajo largo termina.",
     "applies": "futuro: dash/channels."},
    {"key": "otros.retention_days", "group": "otros",
     "label": "Retención per-máquina (días)", "type": "int", "default": 90,
     "range": (7, 36500),
     "help": "Días que se conservan los .jsonl per-máquina (events/, "
             "telemetry/, transcripts-backup/) cuando el job `retention` "
             "está activo. OJO: los backups de transcripts son materia "
             "prima de la memoria — por eso el job viene OFF por default.",
     "applies": "nightly.run_retention() purga lo más viejo que esto al "
                "final de cada pasada (job `retention`)."},
)

def _effective_agent_names():
    """Nombres del registry EFECTIVO (committeado + agentes CARGADOS
    per-máquina, p. ej. turing/iris) — así TODOS tienen su key
    `agentes.<n>.model` y su override VALIDA/PERSISTE (antes solo el trío
    committeado la tenía y turing/iris caían al key crudo, sin poder
    guardarse). Falla-suave: sin dispatch legible → solo el committeado
    (_agent_choices). dispatch NO importa settings al top (solo lazy), así que
    esta llamada en tiempo de import es segura."""
    try:
        import dispatch
        seen, out = set(), []
        for a in dispatch.load_registry().get("agents", []):
            n = str(a.get("name", ""))
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        if out:
            return out
    except Exception:
        pass
    return list(_agent_choices())


def _agent_model_entries():
    """Settings DINÁMICOS `agentes.<nombre>.model` — un override de modelo
    por agente del registry EFECTIVO (las keys aparecen/desaparecen con el
    registry; un override huérfano en el store simplemente deja de validar y
    se ignora — falla-suave). Vacío = el modelo que el agente declare."""
    out = []
    for a in _effective_agent_names():
        nice = str(a).capitalize()
        out.append({
            "key": "agentes.%s.model" % a, "group": "agentes",
            "label": "Modelo de %s" % nice, "type": "str", "default": "",
            "help": "Override del modelo de %s: haiku/sonnet/opus/fable o un "
                    "id completo (vacío = el que declare el agente)." % nice,
            "applies": "engines/claude_code.launch() agrega `--model <esto>` "
                       "al lanzar; un --model explícito del socio o la env "
                       "ANTHROPIC_MODEL SIEMPRE ganan."})
    return tuple(out)


def _agent_engine_entries():
    """Settings DINÁMICOS `agentes.<nombre>.engine` — override de MOTOR
    PER-MÁQUINA por agente (tier A, gitignoreado). NO toca el agent.json
    committeado (eso es N3): el default de equipo sigue en el agent.json; esto
    es la elección local del socio, que dispatch respeta al arrancar. Vacío =
    el motor que el agente declare. Simétrico a `.model`. Un override huérfano
    deja de validar y se ignora — falla-suave."""
    out = []
    for a in _effective_agent_names():
        nice = str(a).capitalize()
        out.append({
            "key": "agentes.%s.engine" % a, "group": "agentes",
            "label": "Motor de %s" % nice, "type": "str", "default": "",
            "help": "Override del MOTOR de %s per-máquina (claude-code, codex, "
                    "…): dispatch lo respeta al arrancar (vacío = el motor del "
                    "agent.json). NO edita el agent.json committeado — el "
                    "default de equipo sigue igual; cambiar ESE es N3." % nice,
            "applies": "dispatch.py precedencia motor: --engine (cli) > env "
                       "WORKSPACE_ENGINE > agentes.<n>.engine (per-máquina) > "
                       "agent.json."})
    return tuple(out)


SETTINGS_SCHEMA = SETTINGS_SCHEMA + _agent_model_entries() + _agent_engine_entries()

_BY_KEY = {s["key"]: s for s in SETTINGS_SCHEMA}


# ── sub-registro de JOBS/crons conocidos ───────────────────────────────────
# NO es un scheduler — es el catálogo de trabajos programados que WORKSPACE
# conoce + el flag enable/disable que el scheduler real (`workspace cron`/C6)
# y los mecanismos existentes LEERÁN (settings.is_job_enabled(id)).
#   id · label · desc · default (enabled) · how (cómo se activa hoy) ·
#   scaffold (True = aún sin mecanismo corriendo) · setting? (alias: el flag
#   vive en ese setting de hooks — una sola fuente de verdad).
JOBS = (
    {"id": "heartbeat-cron", "label": "Latido autónomo (cron de Opus)",
     "default": True,
     "desc": "Despierta a Opus para lanzar la cola autónoma (research/"
             "auto-backlog.md) según heartbeat.decide() y el presupuesto 5h.",
     "how": "cron externo del plan de saturación 20X → heartbeat.py; heartbeat.decide() "
            "RESPETA este flag (off ⇒ action=off, jamás 'go') — el cron no "
            "necesita chequearlo aparte."},
    {"id": "brain-monitor", "label": "Monitor diario del brain",
     "default": False, "scaffold": True,
     "desc": "Revisa cambios al pipeline del cerebro y deja aviso en "
             "STATE/inbox/brain-monitor-*.md para la próxima sesión.",
     "how": "skill meta/reload-brain del cerebro; scheduler real = C6."},
    {"id": "consolidador-nocturno", "label": "Pasada nocturna (nightly)",
     "default": True,
     "desc": "Procesa el backlog de transcripts respaldados: una lectura → "
             "señales de memoria (N1) + skills + eventos (N3).",
     "how": "manual hoy (python3 nightly.py); nightly.run() RESPETA este "
            "flag (off ⇒ la pasada no corre; --force lo puentea a mano)."},
    {"id": "atlas-research", "label": "Cola de investigación de Atlas",
     "default": False, "scaffold": True,
     "desc": "Atlas drena su cola de investigación delegada en horas valle.",
     "how": "futuro: cron en Hermes/local; leerá este flag."},
    {"id": "transcript-backup", "label": "Backup de transcripts",
     "default": True, "setting": "hooks.transcript_backup",
     "desc": "Respaldo del .jsonl crudo en cada cierre de sesión y "
             "pre-compactación (Y2b).",
     "how": "hooks/transcript_backup.py (SessionEnd) + memory_flush "
            "(PreCompact); el flag es alias de hooks.transcript_backup."},
    {"id": "telemetry", "label": "Telemetría en vivo (N-telem)",
     "default": True, "setting": "hooks.telemetry",
     "desc": "Registra metadata de herramientas (tool_name, timing, ok) "
             "en ~/.claude/workspace/telemetry/ para Mission Control en vivo. "
             "NUNCA registra tool_input ni contenido.",
     "how": "hooks/telemetry.py (Pre/PostToolUse); "
            "el flag es alias de hooks.telemetry."},
    {"id": "brain-cleanup", "label": "Cuarentena de regenerables en cerebros",
     "default": False,
     "desc": "Mueve artefactos REGENERABLES del cerebro (allowlist exacta: "
             "node_modules, .next, dist, build, .turbo, .cache, *.tsbuildinfo) "
             "a cuarentena reversible en ~/.claude/workspace/trash/ "
             "(MANIFEST.json origen→destino; NUNCA rm). OFF por default: "
             "toca el cerebro (N3) — activarlo es decisión del socio DUEÑO "
             "(un demo de cliente no se mueve sin su dueño). Guardas: mtime "
             "<48h y lsof (árbol vivo no se toca).",
     "how": "nightly.run() al final de la pasada (o solo: python3 "
            "brain_cleanup.py --brain X [--apply]); respeta este flag."},
    {"id": "retention", "label": "Retención per-máquina (purga M6)",
     "default": False,
     "desc": "Purga los .jsonl per-máquina más viejos que "
             "otros.retention_days: events/, telemetry/ y "
             "transcripts-backup/. OFF por default: los backups son materia "
             "prima de la memoria — activarlo es decisión del socio.",
     "how": "nightly.run_retention() — corre al final de cada pasada "
            "nocturna (o solo: python3 nightly.py --retention); respeta "
            "este flag."},
)

_JOB_BY_ID = {j["id"]: j for j in JOBS}


# ── store ──────────────────────────────────────────────────────────────────
def _load_store():
    """Store completo (dict). Falla-suave: ausente/corrupto → {}.
    Layout: {"version": 1, "settings": {key: val}, "jobs": {id: bool}, …} —
    cualquier otra clave (desconocida) se PRESERVA al escribir."""
    return _read_json(store_path())


def _load_store_for_write():
    """Como _load_store, pero para un RMW (el resultado se va a REESCRIBIR).

    SEC/Argus: `_load_store` colapsa 'corrupto' y 'no existe' a {} — un store
    ilegible se pisaba en silencio al siguiente `set`, descartando TODOS los
    settings/jobs del socio sin dejar rastro. Aquí se distingue: un store
    CORRUPTO se respalda como `settings.json.corrupt-<pid>` con aviso a
    stderr y se sigue con store fresco (mismo patrón que install.py aplica a
    settings.local.json: preservar evidencia, no abortar la acción explícita
    del socio). 'No existe' sigue creando normal, sin ruido."""
    sp = store_path()
    if _json_corrupt(sp):
        rastro = sp + ".corrupt-%d" % os.getpid()
        try:
            os.replace(sp, rastro)
        except OSError:
            rastro = "(no se pudo respaldar — se reescribe encima)"
        try:
            print("⚠ settings: %s era JSON corrupto — respaldado en %s; "
                  "se sigue con un store fresco (revisa el respaldo por "
                  "config manual)." % (sp, rastro), file=sys.stderr)
        except Exception:
            pass
    return _load_store()


def _save_store(store):
    store.setdefault("version", 1)
    _write_json_atomic(store_path(), store)


# ── validación / coerción ──────────────────────────────────────────────────
_TRUE = ("1", "true", "yes", "on", "si", "sí")
_FALSE = ("0", "false", "no", "off")

# Formato de latido.quiet_hours: "HH:MM-HH:MM" (24h; puede cruzar medianoche).
# El parser CANÓNICO vive en heartbeat.parse_quiet_hours (el consumidor);
# aquí solo se rechaza basura al ESCRIBIR (mejor UX en el config TUI) —
# espejo deliberado, igual que CAP_RANGE_FALLBACK allá.
_QUIET_RX = re.compile(
    r"^([01]?\d|2[0-3]):[0-5]\d-([01]?\d|2[0-3]):[0-5]\d$")


def _live_choices(spec):
    """Choices EFECTIVOS de un enum. Si el spec trae `choices_fn` se consulta
    EN VIVO (p. ej. ui.theme: un tema dropeado en themes/ DESPUÉS del import
    valida sin reiniciar — el tuple `choices` se congela al import). Falla-
    suave: fn rota o vacía → el snapshot estático de `choices`."""
    fn = spec.get("choices_fn")
    if fn is not None:
        try:
            live = tuple(fn())
            if live:
                return live
        except Exception:
            pass
    return tuple(spec.get("choices", ()))


def validate(key, value):
    """Valida y NORMALIZA `value` contra el schema de `key`.
    Devuelve el valor canónico o levanta ValueError (sin efectos)."""
    spec = _BY_KEY.get(key)
    if spec is None:
        raise ValueError("setting desconocido: %r (ver `settings.py list`)" % (key,))
    t = spec["type"]
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in _TRUE:
                return True
            if v in _FALSE:
                return False
        raise ValueError("%s espera bool (true/false), no %r" % (key, value))
    if t == "int":
        try:
            if isinstance(value, bool):
                raise ValueError
            iv = int(str(value).strip())
        except (TypeError, ValueError):
            raise ValueError("%s espera entero, no %r" % (key, value))
        lo, hi = spec.get("range", (None, None))
        if lo is not None and not (lo <= iv <= hi):
            raise ValueError("%s fuera de rango [%d, %d]: %d" % (key, lo, hi, iv))
        return iv
    if t == "enum":
        choices = _live_choices(spec)
        if isinstance(value, str):
            v = value.strip().lower()
            for c in choices:
                if v == c.lower():
                    return c
        raise ValueError("%s espera uno de %s, no %r"
                         % (key, "/".join(choices), value))
    if t == "str":
        if isinstance(value, str):
            if key == "ui.background_custom":
                v = value.strip().lower()
                if not re.fullmatch(r"#[0-9a-f]{6}", v):
                    raise ValueError("color inválido: usa #RRGGBB (ej. #101018)")
                return v
            if key == "latido.quiet_hours":
                v = value.strip()
                if v and not _QUIET_RX.match(v):
                    raise ValueError(
                        "%s espera HH:MM-HH:MM (ej. 01:00-07:00) o vacío, "
                        "no %r" % (key, value))
                return v
            return value
        raise ValueError("%s espera texto, no %r" % (key, value))
    if t == "map":
        if isinstance(value, dict):
            return value
        raise ValueError("%s espera objeto/mapa, no %r" % (key, value))
    if t == "list":
        # Acepta lista/tupla o CSV (entrada por CLI). Normaliza: strip, quita
        # vacíos, DEDUP preservando orden, filtra por `member_ok` (falla-suave:
        # miembro inseguro/inexistente → se OMITE, nunca levanta) y aplica el
        # tope `max_items`. Devuelve SIEMPRE una lista (canónica).
        if isinstance(value, str):
            value = [x.strip() for x in value.split(",")]
        if not isinstance(value, (list, tuple)):
            raise ValueError("%s espera lista (o CSV), no %r" % (key, value))
        ok = spec.get("member_ok")
        out = []            # NB: `set` (builtin) está sombreado por settings.set
        for it in value:
            s = str(it).strip()
            if not s or s in out:
                continue
            if ok is not None:
                try:
                    if not ok(s):
                        continue
                except Exception:
                    continue
            out.append(s)
        cap = spec.get("max_items")
        if isinstance(cap, int) and cap > 0:
            out = out[:cap]
        return out
    raise ValueError("tipo de schema desconocido: %r" % (t,))


# ── lecturas ───────────────────────────────────────────────────────────────
def get_stored(key):
    """SOLO el valor del store (validado), sin delegación ni default.
    None si no está o no valida. Para consumidores que ponen su propia
    precedencia encima (p. ej. heartbeat: heartbeat.json gana)."""
    if key not in _BY_KEY:
        return None
    raw = _load_store().get("settings", {})
    if not isinstance(raw, dict) or key not in raw:
        return None
    try:
        return validate(key, raw[key])
    except ValueError:
        return None   # valor podrido en el store → como si no estuviera
    except Exception:
        return None


def _delegated_read(key):
    """Valor efectivo de settings delegados (el mecanismo dueño gana).
    None = el mecanismo no tiene dato → caer a store/default."""
    try:
        if key in ("latido.mode", "latido.budget_cap_pct", "latido.grace_min"):
            hb = _read_json(_heartbeat_json())
            if not hb:
                return None
            field = key.split(".", 1)[1]
            if field in hb:
                return validate(key, hb[field])
            return None
        if key == "cerebro.cleanup_period_days":
            cur = _read_json(_claude_settings()).get("cleanupPeriodDays")
            if isinstance(cur, (int, float)) and not isinstance(cur, bool):
                return int(cur)
            return None
        if key == "agentes.transport":
            t = _read_json(_paths_local()).get("transport")
            return t if isinstance(t, dict) else None
        if key == "otros.update_channel":
            head = ""
            try:
                with open(os.path.join(ROOT, ".git", "HEAD"),
                          encoding="utf-8") as fh:
                    head = fh.read().strip()
            except Exception:
                return None
            if head.startswith("ref:"):
                branch = head.rsplit("/", 1)[-1]
                if branch in _BY_KEY[key]["choices"]:
                    return branch
            return None
    except Exception:
        return None
    return None


def get(key, default=_SENTINEL):
    """Valor EFECTIVO de un setting: mecanismo delegado (si aplica y tiene
    dato) → store → default del schema. Clave desconocida → `default` si se
    dio, si no ValueError. Jamás toca disco para escribir."""
    spec = _BY_KEY.get(key)
    if spec is None:
        if default is not _SENTINEL:
            return default
        raise ValueError("setting desconocido: %r" % (key,))
    if spec.get("delegated"):
        v = _delegated_read(key)
        if v is not None:
            return v
    v = get_stored(key)
    if v is not None:
        return v
    return spec["default"]


def enabled(key, default=True):
    """Variante JAMÁS-LEVANTA para hooks/consumidores falla-suave:
    bool del setting o `default` ante cualquier problema."""
    try:
        v = get(key)
        return bool(v) if isinstance(v, bool) else default
    except Exception:
        return default


def all():   # noqa: A001 — nombre pedido por la API pública
    """{key: valor efectivo} de TODO el registro + estado de jobs."""
    out = {s["key"]: get(s["key"]) for s in SETTINGS_SCHEMA}
    out["jobs"] = {j["id"]: is_job_enabled(j["id"]) for j in JOBS}
    return out


def _pin_display(spec, val):
    """Valor de un pin listo para pintar: bool → on/off (más legible en el
    recinto que True/False), lo demás → str. Nunca levanta."""
    try:
        if spec.get("type") == "bool" or isinstance(val, bool):
            return "on" if val else "off"
        return str(val)
    except Exception:
        return ""


def hub_pins_resolved():
    """Las CONFIGS ancladas al hub (ui.hub_pins) resueltas a
    [{key, label, value}] — value ya formateado para pintar. Vive AQUÍ (no en
    hublayout) para que el recinto clásico las muestre SIN depender de
    hublayout (paridad del default). Falla-suave TOTAL: sin store / pin
    inexistente / valor ilegible → se OMITE (jamás levanta). El schema ya
    garantizó que la lista es segura (enum/bool, nada de paths)."""
    out = []
    try:
        keys = get("ui.hub_pins", [])
        if not isinstance(keys, (list, tuple)):
            return []
        keys = list(keys)
        if keys and "ui.background" not in keys:
            keys.append("ui.background")
        for k in keys:
            spec = _BY_KEY.get(k)
            if not spec:
                continue
            try:
                val = get(k)
            except Exception:
                continue
            out.append({"key": k, "label": spec.get("label") or k,
                        "value": _pin_display(spec, val)})
    except Exception:
        return []
    return out


def hub_pin_ok(key):
    """¿`key` es un pin SEGURO (enum/bool, sin path/credencial)? Alias
    público de _hub_pin_ok — lo usan el config TUI (selector de pins) y el
    recinto (ciclado in-situ). Falla-suave → False."""
    return _hub_pin_ok(key)


def hub_pins_cap():
    """Tope de pins anclables al hub (ui.hub_pins.max_items — el espacio del
    recinto). Falla-suave → 5."""
    try:
        return int(_BY_KEY["ui.hub_pins"].get("max_items", 5))
    except Exception:
        return 5


def pinnable_keys():
    """Keys del schema SEGURAS para anclar al hub (enum/bool sin path/cred),
    en el orden del registro — el catálogo del selector de pins del config
    TUI. Falla-suave → []."""
    try:
        return [s["key"] for s in SETTINGS_SCHEMA if _hub_pin_ok(s["key"])]
    except Exception:
        return []


def next_pin_value(key):
    """Siguiente valor CICLADO de un pin editable (para el ciclado in-situ
    del recinto): enum → siguiente choice circular · bool → toggle. Valida,
    persiste (set → store + sync de latido.json si aplica) y devuelve el
    valor nuevo normalizado. Levanta ValueError si `key` no es un pin
    seguro/ciclable — el caller decide la falla-suave (aviso, sin romper)."""
    if not _hub_pin_ok(key):
        raise ValueError("%s no es un pin editable (solo enum/bool seguros)"
                         % (key,))
    spec = _BY_KEY.get(key) or {}
    t = spec.get("type")
    cur = get(key)
    if t == "bool":
        newv = not bool(cur)
    elif t == "enum":
        choices = list(_live_choices(spec))
        if not choices:
            raise ValueError("%s sin choices para ciclar" % (key,))
        try:
            i = choices.index(cur)
        except ValueError:
            i = -1                       # valor fuera de choices → arranca en el 1º
        newv = choices[(i + 1) % len(choices)]
    else:
        raise ValueError("%s no es ciclable (tipo %r)" % (key, t))
    return set(key, newv)                # valida + persiste + sync


# ── escrituras ─────────────────────────────────────────────────────────────
def _sync_heartbeat_json(key, value):
    """Si heartbeat.json EXISTE, reflejar ahí el cambio de latido.* (ese
    archivo gana en la precedencia — sin sync quedaría divergente).
    Best-effort: si no se puede, el store ya quedó escrito."""
    path = _heartbeat_json()
    if not os.path.exists(path):
        return
    try:
        # SEC: un heartbeat.json CORRUPTO no se pisa con `{<campo>: v}` a secas
        # (perdería el resto del estado del latido en silencio). El sync es
        # best-effort: se salta con aviso; el store ya quedó escrito.
        if _json_corrupt(path):
            print("⚠ settings: %s es JSON corrupto — no se sincroniza "
                  "latido.* ahí (repáralo o bórralo)." % path, file=sys.stderr)
            return
        hb = _read_json(path)
        hb[key.split(".", 1)[1]] = value
        _write_json_atomic(path, hb)
    except Exception:
        pass


def set_stored(key, value):
    """Valida y persiste SOLO en el store (sin delegaciones ni syncs).
    Para mecanismos que ya escribieron su canal propio (p. ej.
    heartbeat.set_mode espejea aquí). Devuelve el valor normalizado."""
    v = validate(key, value)            # valida FUERA del lock (puede levantar)

    def _rmw():
        store = _load_store_for_write()   # SEC: no pisar un store corrupto mudo
        store.setdefault("settings", {})[key] = v
        _save_store(store)
    _with_store_lock(_rmw)              # G1: RMW serializado
    return v


def set(key, value):   # noqa: A001 — nombre pedido por la API pública
    """Valida y persiste un setting. Inválido → ValueError SIN escribir.
    readonly → ValueError apuntando al mecanismo dueño. Delegados:
      · latido.*  → store + sync a heartbeat.json si existe (ese archivo gana).
      · cerebro.cleanup_period_days → escribe ~/.claude/settings.json
        (mecanismo existente de install/doctor), no el store.
    Devuelve el valor normalizado."""
    spec = _BY_KEY.get(key)
    if spec is None:
        raise ValueError("setting desconocido: %r (ver `settings.py list`)" % (key,))
    if spec.get("readonly"):
        raise ValueError("%s es de solo-lectura aquí — %s" % (key, spec["applies"]))
    v = validate(key, value)
    if key == "cerebro.cleanup_period_days":
        sp = _claude_settings()
        # SEC/Argus (espejo del read-guard R3-F1 de install.ensure_cleanup_days):
        # si el settings GLOBAL del socio está CORRUPTO, NO lo pisamos con
        # `{cleanupPeriodDays: …}` a secas — eso descartaría model/env/hooks/
        # permissions en silencio. Abortar con aviso; el archivo queda intacto
        # (es del socio: repararlo es suyo, no nuestro). 'No existe' sigue
        # creando normal.
        if _json_corrupt(sp):
            raise ValueError(
                "%s es JSON corrupto — NO se reescribe (pisarlo descartaría "
                "tu config: model/env/hooks/permissions). Repara o respalda "
                "el archivo y reintenta." % sp)
        s = _read_json(sp)
        s["cleanupPeriodDays"] = v
        _write_json_atomic(sp, s)
        return v
    set_stored(key, v)
    if key.startswith("latido."):
        _sync_heartbeat_json(key, v)
    return v


def reset(key):
    """Quita el override del store (vuelve al default / al mecanismo
    delegado). Clave desconocida → ValueError. Idempotente."""
    if key not in _BY_KEY:
        raise ValueError("setting desconocido: %r" % (key,))

    def _rmw():
        store = _load_store_for_write()   # SEC: no pisar un store corrupto mudo
        if isinstance(store.get("settings"), dict) and key in store["settings"]:
            del store["settings"][key]
            _save_store(store)
    _with_store_lock(_rmw)              # G1: RMW serializado



# ── jobs ───────────────────────────────────────────────────────────────────
def is_job_enabled(job_id):
    """Flag efectivo de un job: setting alias (si el job lo declara) →
    store["jobs"] → default del registro. Job desconocido → True
    (falla-suave: un consumidor con id viejo no se apaga solo)."""
    j = _JOB_BY_ID.get(job_id)
    if j is None:
        return True
    if j.get("setting"):
        return enabled(j["setting"], default=bool(j.get("default", True)))
    jobs = _load_store().get("jobs", {})
    v = jobs.get(job_id) if isinstance(jobs, dict) else None
    if isinstance(v, bool):
        return v
    return bool(j.get("default", True))


def set_job_enabled(job_id, on):
    """Persiste el enable/disable de un job. Id desconocido / valor no-bool
    → ValueError sin escribir. Jobs con `setting` alias escriben ESE setting
    (una sola fuente de verdad)."""
    j = _JOB_BY_ID.get(job_id)
    if j is None:
        raise ValueError("job desconocido: %r (ver `settings.py jobs`)" % (job_id,))
    if isinstance(on, str):
        v = on.strip().lower()
        if v in _TRUE:
            on = True
        elif v in _FALSE:
            on = False
    if not isinstance(on, bool):
        raise ValueError("set_job_enabled espera bool, no %r" % (on,))
    if j.get("setting"):
        set(j["setting"], on)
        return on
    store = _load_store_for_write()       # SEC: no pisar un store corrupto mudo
    store.setdefault("jobs", {})[job_id] = on
    _save_store(store)
    return on


def jobs_status():
    """Catálogo de jobs + estado efectivo (para UIs y el futuro scheduler):
    [{id, label, desc, how, scaffold, default, enabled}…]."""
    out = []
    for j in JOBS:
        out.append({"id": j["id"], "label": j["label"], "desc": j["desc"],
                    "how": j["how"], "scaffold": bool(j.get("scaffold")),
                    "default": bool(j.get("default", True)),
                    "enabled": is_job_enabled(j["id"])})
    return out


# ── migración heartbeat.json → store ───────────────────────────────────────
def import_heartbeat():
    """Importa los valores de heartbeat.json (si existe) al store unificado
    (latido.*). NO borra heartbeat.json — ese archivo sigue ganando mientras
    exista (back-compat); esto solo asegura que el día que se retire, el
    store ya tenga los valores. Devuelve dict con lo importado."""
    hb = _read_json(_heartbeat_json())
    if not hb:
        return {}
    imported = {}
    for field, key in (("mode", "latido.mode"),
                       ("budget_cap_pct", "latido.budget_cap_pct"),
                       ("grace_min", "latido.grace_min")):
        if field in hb:
            try:
                imported[key] = set_stored(key, hb[field])
            except ValueError:
                pass   # valor podrido en heartbeat.json → no importarlo
    return imported


# ── CLI ────────────────────────────────────────────────────────────────────
def _fmt_val(v):
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False) if v else "(vacío)"
    return str(v) if str(v) else "(vacío)"


def _cli_list():
    stored = _load_store().get("settings", {})
    if not isinstance(stored, dict):
        stored = {}
    for g in GROUPS:
        if g == "jobs":
            print("\n[jobs]  (settings.py jobs)")
            for j in jobs_status():
                mark = "·" if not j["scaffold"] else "○"
                print("  %s %-22s %-4s %s" % (mark, j["id"],
                                              _fmt_val(j["enabled"]), j["label"]))
            continue
        rows = [s for s in SETTINGS_SCHEMA if s["group"] == g]
        if not rows:
            continue
        print("\n[%s]" % g)
        for s in rows:
            key = s["key"]
            tags = []
            if key in stored:
                tags.append("custom")
            if s.get("delegated"):
                tags.append("delegado")
            if s.get("readonly"):
                tags.append("solo-lectura")
            if s.get("scaffold"):
                tags.append("scaffold")
            tag = (" (" + ", ".join(tags) + ")") if tags else ""
            print("  %-30s %-14s %s%s" % (key, _fmt_val(get(key)),
                                          s["label"], tag))
    print()
    return 0


def _cli_jobs(args):
    if args and args[0] in ("enable", "disable"):
        if len(args) < 2:
            print("uso: settings.py jobs enable|disable <id>", file=sys.stderr)
            return 2
        try:
            set_job_enabled(args[1], args[0] == "enable")
        except ValueError as e:
            print("settings: %s" % e, file=sys.stderr)
            return 2
        print("job %s → %s" % (args[1], args[0]))
        return 0
    for j in jobs_status():
        state = "on " if j["enabled"] else "off"
        extra = " · scaffold (sin scheduler aún)" if j["scaffold"] else ""
        print("%-22s %s  %s%s" % (j["id"], state, j["label"], extra))
        print("%22s      %s" % ("", j["how"]))
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "list"
    try:
        if cmd in ("list", "--list"):
            return _cli_list()
        if cmd in ("--json", "json"):
            print(json.dumps(all(), ensure_ascii=False, indent=2,
                             sort_keys=True))
            return 0
        if cmd == "get" and len(args) >= 2:
            print(_fmt_val(get(args[1])))
            return 0
        if cmd == "set" and len(args) >= 3:
            v = set(args[1], args[2])
            print("%s → %s" % (args[1], _fmt_val(v)))
            return 0
        if cmd == "reset" and len(args) >= 2:
            reset(args[1])
            print("%s → default (%s)" % (args[1], _fmt_val(get(args[1]))))
            return 0
        if cmd == "jobs":
            return _cli_jobs(args[1:])
        if cmd == "migrate":
            imp = import_heartbeat()
            if imp:
                for k, v in sorted(imp.items()):
                    print("importado %s = %s" % (k, _fmt_val(v)))
            else:
                print("nada que migrar (heartbeat.json ausente o vacío)")
            return 0
    except ValueError as e:
        print("settings: %s" % e, file=sys.stderr)
        return 2
    print("uso: settings.py list | get <k> | set <k> <v> | reset <k> | "
          "jobs [enable|disable <id>] | migrate | --json", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
