#!/usr/bin/env python3
"""WORKSPACE · config_tui — pantalla de CONFIGURACIÓN del recinto (tier SIMPLE).

La entrada CONFIG del menú `workspace` (front.py) invoca `run()` de este módulo;
vive aparte para no inflar ni arriesgar front.py (cambio quirúrgico allá).
El grueso (latido/crons/budget/modelo/hooks/tema/layout/pins) se lee/escribe
por settings.py (get/set/jobs) — el store unificado per-máquina
(~/.claude/workspace/settings.json). Las secciones CUENTAS y ROUTING usan la
capa por TIERS aparte, SIN bypasear su seguridad:
  · CUENTAS: ASISTENTE GUIADO (mode "connect", estilo onboarding). La lista da
    un overview tipo doctor (agrupado Suscripción · API medida · Local, con
    "conectadas x/y"); Enter abre un panel ENFOCADO paso a paso: qué es la
    cuenta + costo, de dónde sacar la key (URL real), pegar OCULTO, y VALIDAR
    con un ping real ligero (connectors.ping_provider — GET de modelos, no
    gasta tokens; fail-soft, timeout corto, en vivo en un hilo). El valor va al
    secret_store (bóveda per-máquina 0600, gitignoreada; el config guarda
    NOMBRES de env-var, JAMÁS valores) SOLO si la validación no lo rechazó.
    Suscripción/CLI oficial (codex/claude): el asistente INSTALA el CLI (con
    confirmación) y lanza el login OFICIAL — nunca extrae el token (INVARIANTE
    de connectors); el exec lo hace el driver por S["shell_request"].
  · ROUTING POR TAREA + CUENTA/MOTOR por agente: config_engine (task_routing
    tier A · agent.json set_agent_field tier B personal / C consenso N3 — un
    agente del EQUIPO jamás se escribe desde aquí, solo se propone).

Layout (mismo lenguaje visual que chat_tui — Look WORKSPACE, dorado/oscuro):

    ╔═ CONFIG ═════════════════════════════════════════════════════╗
    ║  CONFIGURACIÓN      ┃   LATIDO — trabajo autónomo             ║
    ║                     ┃  ─────────────────────────────────────  ║
    ║  ▸ Latido           ┃  ▸ Modo del latido        auto    store ║
    ║      modo auto      ┃    Tope presupuesto 5h    85   default  ║
    ║    Crons activos    ┃    Gracia tras actividad  12   default  ║
    ║      5/7 activos    ┃    Horas de silencio   (vacío) default  ║
    ║    Budget de tokens ┃                                         ║
    ║    Modelo por agente┃  ─────────────────────────────────────  ║
    ║    Hooks            ┃  latido.mode = auto · default auto      ║
    ║    Avanzado         ┃  auto = el cron puede lanzar solo · …   ║
    ║  ‹ Salir al menú    ┃  Enter aplica · Espacio cicla           ║
    ╟─────────────────────┸─────────────────────────────────────────╢
    ║  ↑↓ moverse · ◄► sección · Enter editar · Espacio toggle      ║
    ║  Esc salir al menú · ‹ Salir al menú con Enter también sale   ║
    ╚═══════════════════════════════════════════════════════════════╝

SIETE secciones (tier SIMPLE) + el lugar de AVANZADO (scaffold, v2):
  1. LATIDO     — latido.mode / budget_cap_pct / grace_min / quiet_hours.
  2. CRONS      — settings.JOBS con toggle on/off (settings.set_job_enabled).
  3. BUDGET     — DOS canales que NO se mezclan: (a) colchón de SESIÓN para
                  auth/suscripción = latido.budget_cap_pct (el % del plan 5h
                  donde el latido pausa); (b) límite de TOKENS para API =
                  budget.api_token_limit (0 = sin límite, solo engines API).
  4. MODELOS    — UNA fila por agente (kind "agent": "Motor · modelo"); Enter
                  abre un PANEL enfocado (mode "agent") donde motor↔modelo se
                  ajustan COHERENTES. El picker de MOTOR/CUENTA se DERIVA de las
                  cuentas CONECTADAS (_motor_options ← connectors.all_provider_
                  status), NO de engines/*.py: así aparece lo que el socio
                  conectó (codex/…) y cualquier cuenta futura sale sola; stub/
                  _template nunca (>_hidden_name). Una cuenta sin adaptador de
                  ejecución aún se MUESTRA etiquetada "motor en construcción"
                  (jamás se oculta ni se simula que corre); claude-code es el
                  listo/default. El picker de MODELO depende del motor
                  (claude-code → haiku/sonnet/opus/fable; otros → ids reales del
                  provider). El PANEL (mode "agent") es NAVEGABLE con ↑↓+Enter
                  como el resto del TUI (filas: Motor · Modelo · Quitar; m/o/x
                  quedan de atajo). AMBOS overrides son PER-MÁQUINA (settings
                  tier A): modelo=`agentes.<n>.model`, motor=`agentes.<n>.engine`
                  — se APLICAN de verdad (dispatch respeta el motor: --engine ›
                  env › override per-máquina › agent.json) y NO tocan el
                  agent.json committeado (cambiar ESE default de equipo sí es
                  N3, aparte). Muestra el MODELO EFECTIVO + precedencia. ROUTING
                  también ofrece SOLO modelos de cuentas conectadas.
  5. HOOKS      — los 5 kill-switches (hooks.*). Si la env WORKSPACE_NO_* está
                  activa se indica "override por env": el env SIEMPRE gana y
                  el toggle no aplica hasta quitarla.
  6. TEMA       — apariencia del harness: ui.theme con PICKER dedicado
                  (Enter abre la lista CURADA de temas — nombre legible
                  + id, del MOTOR hubtheme.hub_picker(): solo los ya pulidos
                  para el TUI, NUNCA hardcodeados; los pendientes siguen
                  usables vía WORKSPACE_THEME/ui.theme directo — ↑↓ o número
                  1-9 eligen, Enter aplica y persiste, Esc cancela; Espacio
                  cicla como cualquier enum) + ui.stars / ui.anim (toggles).
                  Tema roto en themes/ → el motor ya lo filtra; sin motor →
                  snapshot del schema; jamás crashea.
  7. LAYOUT     — ESTRUCTURA del hub: ui.layout con el MISMO picker (kind
                  "layout" reusa el plumbing del de tema — Enter abre la
                  lista del REGISTRO hublayout.available(), ↑↓/1-9/Enter
                  aplica y persiste, Esc cancela). Eje INDEPENDIENTE del
                  tema: cualquier layout combina con cualquier tema.
  ·  AVANZADO   — placeholder del tier avanzado (v2) — solo el lugar.

UX por item: label claro + valor actual + origen (store/env/default/delegado);
el item SELECCIONADO además muestra su default, rango y help en el pie del
panel derecho. Editar: bool/job → Espacio o Enter (toggle); enum/model →
Espacio cicla; int/str/model → Enter abre input inline (valida contra el
schema vía settings.set — inválido = aviso y NO escribe; vacío = restaurar
default vía settings.reset). SALIDA SOLO DELIBERADA: Esc pelado en
navegación, Ctrl-C, o Enter sobre "‹ Salir al menú" — las flechas JAMÁS
salen, Esc en edición solo cancela la edición.

FEEDBACK DE GUARDADO (pedido del socio): cada cambio que SÍ persiste (toggle,
ciclar, input, reset) muestra "» guardado" en VERDE junto al item y en su
detalle — el socio sabe que quedó y que ya todo corre así. La marca dura
unos ticks (~6s) y se desvanece sola. Los enum/model además pintan TODAS
sus opciones estilo radio con la SELECCIONADA marcada — (●) en Mac/Linux,
(*) en Windows — no solo el valor suelto. Si hay override por env, el aviso
de env sigue ganando la columna de origen, pero el "guardado" al store se
confirma igual en el detalle (el env gana en efecto, no en persistencia).

Reglas que este módulo honra (las mismas del chat):
  · Windows-safe: NADA de glifos 0x2600–0x27BF ni ≥0x1F000 en el arte fijo
    (▸ ◈ ‹ ● ○ ─ ┃ ╔ ╝ ▌, todos <0x2600 y de ancho 1).
  · Fórmula de pantalla de front.py: clear inicial \\033[2J\\033[3J\\033[H,
    redraw \\033[H + \\033[K por línea — JAMÁS alt-screen ni 2J a media
    sesión. Tick ~0.5s relee settings (cambios externos aparecen solos).
  · Falla-suave ABSOLUTA: sin settings.py / store corrupto / registry roto →
    defaults, aviso amable, jamás crashea el menú.

Testeable sin tty: new_state() + refresh() + render_lines(S, w, h) +
handle_key()/handle_arrow() son puros sobre el estado (los drivers de
teclado solo orquestan). stdlib, Python 3.9+, Mac/Windows.
"""
import os
import sys

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import settings
except Exception:                                    # pragma: no cover - defensa
    settings = None

# Capa de CUENTAS / ROUTING — todos FALLA-SUAVE: si un módulo no está, su
# sección simplemente no aparece y el resto del TUI queda intacto. connectors
# = estado de conexión honesto (reusa vet_provider/_resolve_key/official_cli_
# status); secret_store = bóveda per-máquina (0600, jamás al repo); config_engine
# = writes por TIERS (task_routing tier A · agent.json tier B/C); model_resolver
# = ids de modelo REALES de providers/*.json (jamás inventados).
try:
    import connectors as _connectors
except Exception:                                    # pragma: no cover - defensa
    _connectors = None
try:
    import secret_store as _secret_store
except Exception:                                    # pragma: no cover - defensa
    _secret_store = None
try:
    import config_engine as _config_engine
except Exception:                                    # pragma: no cover - defensa
    _config_engine = None
try:
    import model_resolver as _model_resolver
except Exception:                                    # pragma: no cover - defensa
    _model_resolver = None

# Saneo + MEDICIÓN compartidos (_width.py — los mismos del hub): tab/controles
# → espacio, escapes ANSI y zero-width/VS15-16 fuera, NFC; eaw = ancho por
# carácter (un glifo de tema mide IGUAL aquí que en el hub). Ver cw()/_fit().
from _width import sane_plain as _sane_plain, eaw as _eaw     # noqa: E402

R = "\033[0m"; BO = "\033[1m"


def fg(n):
    return "\033[38;5;%dm" % n


# paleta dorada del recinto (consistente con front.py / chat_tui — Look WORKSPACE)
B = fg(214); B2 = fg(178); C = fg(221); WH = fg(230); DIM = fg(136)
DK = fg(94); GREY = fg(242)
GREEN = fg(108); RED = fg(174)
# … salvo que haya TEMA activo (tuitheme.py — el mismo tema que front.py y el
# panel web). olympo = exactamente los índices de arriba (paridad); falla-
# suave: sin tuitheme, los literales dorados quedan tal cual.
try:
    import tuitheme as _tuitheme
    _TH = _tuitheme.palette()
    B, B2, C, WH = _TH.B, _TH.B2, _TH.C, _TH.WH
    DIM, DK, GREY = _TH.DIM, _TH.DK, _TH.GREY
    R, BO = _TH.R, _TH.BO
    GREEN, RED = _TH.OK, _TH.BAD
except Exception:
    pass

# ── i18n (capa de traducción cliente) — red de seguridad inline: si i18n no
# está (config_tui puede correr sin la raíz en sys.path), _t cae al literal
# ESPAÑOL que recibe, idéntico al catálogo `es` ⇒ doble garantía de paridad.
# SOLO la pantalla de PERSONALIZACIÓN (tema/fondo) pasa por aquí; el resto del
# CONFIG sigue en español hasta su ola. Ver `lang/README.md`.
try:
    import i18n as _i18n
except Exception:                                    # pragma: no cover - defensa
    _i18n = None


def _t(key, es, **kw):
    """Traduce `key` al idioma activo; si i18n no está o falta la clave, cae
    al literal `es` (byte-idéntico al catálogo). Interpola con **kw."""
    if _i18n is not None:
        try:
            s = _i18n.t(key, **kw)
            if s != key:
                return s
        except Exception:
            pass
    try:
        return es.format(**kw) if kw else es
    except Exception:
        return es

MIN_W, MIN_H = 60, 14
EXIT_LABEL = "‹ Salir al menú"
EXIT = -1                            # índice de sección del pseudo-item salida

# Feedback de guardado: marca VERDE junto al item recién persistido.
# "»" (U+00BB) es Windows-safe (<0x2600, ancho 1) — el ✓ U+2713 está
# PROHIBIDO por la regla 0x2600–0x27BF.
SAVED_MARK = "» guardado"
SAVED_TTL = 12                       # ticks de ~0.5s ⇒ la marca vive ~6s


def _radio(sel):
    """Marca radio de opción enum/model: (●)/( ) en Mac/Linux, (*)/( ) en
    Windows (mismo criterio conservador que _onoff — cero doble ancho)."""
    if os.name == "nt":
        return "(*)" if sel else "( )"
    return "(●)" if sel else "( )"

# Modelos conocidos que Espacio cicla en MODELOS (Enter = input libre).
MODEL_CHOICES = ("haiku", "sonnet", "opus", "fable")

# CUENTAS · asistente guiado: providers ocultos (ruido interno — jamás en un
# picker de usuario) + orden y labels de los grupos del overview "doctor".
# stub = eco de prueba; cualquier nombre con "_" delante = plantilla/interno
# (p. ej. engines/_template.py) — se filtran en TODO picker (_hidden_name).
_ACCOUNT_HIDE = ("stub", "_template")


def _hidden_name(name):
    """True si un provider/motor es ruido interno que NO debe salir en un
    picker de usuario (stub, _template, cualquier nombre con '_' delante)."""
    n = str(name or "")
    return n in _ACCOUNT_HIDE or n.startswith("_")
_GROUP_ORDER = ("subscription", "metered", "local", "other")
_GROUP_LABEL = {"subscription": "Suscripción", "metered": "API medida",
                "local": "Local", "other": "Otros"}
# Validación por ping REAL: timeout corto (fail-soft) + flag de modo SÍNCRONO
# (los tests lo prenden para correr el ping inline, determinista y mockeado —
# en vivo corre en un hilo daemon para NO congelar el TUI).
PING_TIMEOUT = 6.0
_PING_SYNC = False

# Kill-switches de hooks → su env override (el env SIEMPRE gana al setting;
# espejo del apéndice de envs del catálogo en settings.SETTINGS_SCHEMA).
HOOK_ENV = (
    ("hooks.skill_review", "WORKSPACE_NO_SKILL_REVIEW"),
    ("hooks.transcript_backup", "WORKSPACE_NO_TRANSCRIPT_BACKUP"),
    ("hooks.memory_flush", "WORKSPACE_NO_MEMORY_FLUSH"),
    ("hooks.security_guidance", "WORKSPACE_NO_SECURITY_GUIDANCE"),
    ("hooks.telemetry", "WORKSPACE_NO_TELEMETRY"),
)
_HOOK_ENV_MAP = dict(HOOK_ENV)

# Barra de ayuda PROMINENTE (2 filas DENTRO del marco, teclas en acento
# dorado): [(tecla, descripción), ...] por fila, por modo — como el chat.
HELP = {
    "nav": (
        (("↑↓", "moverse"), ("◄►", "cambiar de sección"),
         ("Enter", "editar / aplicar"), ("Espacio", "toggle / ciclar")),
        (("Esc", "salir al menú"),
         (EXIT_LABEL, "con Enter también sale")),
    ),
    "edit": (
        (("escribe", "el nuevo valor"), ("Enter", "guardar"),
         ("vacío + Enter", "restaurar el default")),
        (("Esc", "cancelar — regresa sin guardar, no sale"),),
    ),
    "pick": (
        (("↑↓", "elegir"), ("1-9", "elegir directo"),
         ("Enter", "aplicar y guardar")),
        (("Esc", "cancelar — regresa sin cambiar, no sale"),),
    ),
    "connect": (
        (("Enter", "acción del paso"), ("Esc", "regresa un paso / cierra")),
        (("las teclas del paso", "van abajo, en el asistente"),),
    ),
    "agent": (
        (("↑↓", "elegir fila"), ("Enter", "abrir / aplicar"),
         ("Esc", "regresa / cierra")),
        (("atajos", "m motor · o modelo · x quitar"),),
    ),
}

def _lw(w):
    """Ancho del panel izquierdo: ~1/3 de la pantalla, 24–34 cols."""
    return max(24, min(34, int(w) // 3))


def cw(ch):
    """Ancho de celda del glifo — la medición COMPARTIDA del harness
    (_width.eaw, la MISMA del hub): combinantes/zero-width = 0, CJK/Hangul y
    emoji East-Asian-Wide = 2, resto = 1. Antes config_tui tenía su propia
    tabla con rangos emoji extra (0x2600-0x27BF = 2) → los glifos de tema
    (✓ ✦ ♥ ✉) medían 2 aquí y 1 en el hub, y el preview se descuadraba.
    El SANEO del texto (tab/ANSI/zero-width, que aquí medirían mal) NO es
    tarea de cw: _fit/_cell/_wrap pasan todo texto plano por
    _width.sane_plain ANTES de medir."""
    return _eaw(ch)


def _pw(plain):
    return sum(cw(ch) for ch in plain)


def _fit(plain, w):
    """Recorta texto plano a ≤w columnas visibles (… al final si truncó).
    SANEA primero (_width.sane_plain): un valor con tab/escape ANSI/zero-
    width mediría distinto de lo que la terminal pinta y descuadraría el
    marco. Idempotente — da igual cuántas veces pase por aquí."""
    if w <= 0:
        return ""
    plain = _sane_plain(plain)
    if _pw(plain) <= w:
        return plain
    out, used = "", 0
    for ch in plain:
        c = cw(ch)
        if used + c > w - 1:
            break
        out += ch
        used += c
    return out + "…"


def _cell(segs, w, align="left"):
    """[(texto_plano, color)] → string ANSI de EXACTAMENTE w columnas
    visibles (clip + pad). El ancho fijo es lo que mantiene el marco recto."""
    out, used = [], 0
    for plain, col in segs:
        if used >= w:
            break
        plain = _fit(str(plain), w - used)
        if not plain:
            continue
        out.append((col or "") + plain + (R if col else ""))
        used += _pw(plain)
    pad = " " * max(0, w - used)
    s = "".join(out)
    return (pad + s) if align == "right" else (s + pad)


def _wrap(text, w):
    """Envuelve texto plano SANEADO a líneas de ≤w columnas (corta palabras
    largas). Mismo saneo que _fit — lo envuelto se mide como se pinta."""
    w = max(8, w)
    out, cur, curw = [], "", 0
    for word in _sane_plain(text).split(" "):
        ww = _pw(word)
        if curw and curw + 1 + ww <= w:
            cur += " " + word
            curw += 1 + ww
        elif ww <= w:
            if cur:
                out.append(cur)
            cur, curw = word, ww
        else:
            if cur:
                out.append(cur)
            seg, segw = "", 0
            for chx in word:
                cx = cw(chx)
                if segw + cx > w:
                    out.append(seg)
                    seg, segw = chx, cx
                else:
                    seg += chx
                    segw += cx
            cur, curw = seg, segw
    if cur:
        out.append(cur)
    return out or [""]


def _onoff(v):
    """Marca de toggle Windows-safe: ● / ○ (<0x2600) en Mac/Linux, [x]/[ ]
    en Windows (runbooks/windows-support.md — cero riesgo de doble ancho)."""
    if os.name == "nt":
        return "[x] on" if v else "[ ] off"
    return "● on" if v else "○ off"


# ═══════════════════════════════════════════════════════════════════════════
# Modelo de datos (todo vía settings.py — falla-suave absoluta)
# ═══════════════════════════════════════════════════════════════════════════

def _specs():
    """{key: spec} del registro declarativo. Falla-suave → {}."""
    try:
        return {s["key"]: s for s in settings.SETTINGS_SCHEMA}
    except Exception:
        return {}


def _agents():
    """Agentes del registry (mismo orden). Falla-suave → trío conocido."""
    try:
        import dispatch
        names = [str(a.get("name", "")) for a in
                 dispatch.load_registry().get("agents", []) if a.get("name")]
        return names or ["zenith", "atlas", "argus"]
    except Exception:
        return ["zenith", "atlas", "argus"]


def _routing_tasks():
    """Tareas del routing por tarea (formato CONGELADO). Fuente: config_engine
    / model_resolver; falla-suave al vocabulario conocido."""
    for src in (getattr(_config_engine, "_ROUTING_TASKS", None),
                getattr(_model_resolver, "TASKS", None)):
        if src:
            return tuple(src)
    return ("research", "task", "utility", "default")


def _provider_models(cap=32, connected_only=True):
    """IDs de modelo REALES de providers/*.json (JAMÁS inventados): unión
    ordenada, deduplicada, con tope. `connected_only` (default) SOLO incluye
    los de cuentas CONECTADAS — así ROUTING ofrece modelos USABLES, no ids
    sueltos que no se pueden correr (config consciente de lo conectado). Oculta
    stub/_template. Falla-suave → ()."""
    if _model_resolver is None:
        return ()
    seen, out = set(), []
    try:
        for name in _model_resolver.list_providers():
            if _hidden_name(name):
                continue
            p, errs = _model_resolver.load_provider(name)
            if errs or not p:
                continue
            if connected_only and _connectors is not None:
                try:
                    if not _connectors.provider_status(p).get("ok"):
                        continue
                except Exception:
                    continue
            for m in (p.get("models") or []):
                if isinstance(m, str) and m and m not in seen:
                    seen.add(m)
                    out.append(m)
                    if len(out) >= cap:
                        return tuple(out)
    except Exception:
        return ()
    return tuple(out)


def _engines():
    """Motores instalados (engines/*.py) para ciclar la CUENTA/MOTOR por
    agente. Falla-suave → ()."""
    try:
        import dispatch
        return tuple(dispatch.available_engines())
    except Exception:
        return ()


def _agent_engine_map():
    """{agente: fila de describe_agents} — motor actual + tier de escritura +
    display. Falla-suave → {}."""
    if _config_engine is None:
        return {}
    try:
        return {r["name"]: r for r in _config_engine.describe_agents()}
    except Exception:
        return {}


# ── coherencia MOTOR ↔ MODELO ↔ CUENTA (panel por agente) ───────────────────
#: motor (engine instalado) → provider cuya lista de modelos ofrece el picker.
#: claude-code usa los ALIAS del launcher (MODEL_CHOICES); los demás, los
#: `models` REALES del provider mapeado (nada inventado). Un motor sin mapeo
#: usa el provider homónimo si existe.
_ENGINE_MODEL_PROVIDER = {}
#: Motores donde la CUENTA elige el modelo (WORKSPACE no debe ofrecer/forzar uno):
#: codex-ChatGPT auto-elige el modelo que la cuenta soporta (gpt-5.6-sol) y
#: RECHAZA con 400 cualquier `-m` ajeno (gpt-5 → error). Su picker solo ofrece
#: "(por defecto — lo elige tu cuenta)". Ver engines/codex._resolve_model.
_ENGINE_MODEL_AUTO = ("codex",)
#: motor → cuenta (provider) para el chequeo "¿está conectada?". stub/local no
#: tienen cuenta (siempre alcanzable).
_ENGINE_ACCOUNT = {"claude-code": "anthropic", "codex": "codex"}


def _engine_label(engine):
    """Nombre legible de un motor para la lista (falla-suave → el id)."""
    return {"claude-code": "Claude Code", "codex": "Codex", "stub": "Stub",
            "": "(sin motor)"}.get(engine, engine)


def _engine_model_choices(engine):
    """IDs de modelo COHERENTES con el motor (jamás ajenos): claude-code →
    haiku/sonnet/opus/fable (alias del launcher); motores 'auto' (codex) → solo
    "(por defecto)" porque la CUENTA elige el modelo y forzar uno rompe (400);
    otro motor → los `models` reales de su provider, sin hidden_models.
    Falla-suave → MODEL_CHOICES. Todos con '' al frente = usa el default."""
    if engine in _ENGINE_MODEL_AUTO:                 # la cuenta elige (codex)
        return ("",)
    if engine in ("claude-code", ""):
        return ("",) + MODEL_CHOICES
    prov = _ENGINE_MODEL_PROVIDER.get(engine, engine)
    try:
        p, errs = _model_resolver.load_provider(prov)
        if not errs and p:
            hidden = set(p.get("hidden_models") or ())
            ids = [m for m in (p.get("models") or [])
                   if isinstance(m, str) and m and m not in hidden]
            if ids:
                return ("",) + tuple(ids)
    except Exception:
        pass
    return ("",) + MODEL_CHOICES


def _engine_account_ok(engine):
    """(ok, account_name): ¿la cuenta que respalda al motor está conectada?
    stub/local sin cuenta → (True, ''). Falla-suave → (True, '') (no bloquea
    si no se puede verificar)."""
    prov = _ENGINE_ACCOUNT.get(engine)
    if not prov or _connectors is None or _model_resolver is None:
        return True, ""
    try:
        p, errs = _model_resolver.load_provider(prov)
        if errs or not p:
            return True, prov
        st = _connectors.provider_status(p)
        return bool(st.get("ok")), prov
    except Exception:
        return True, prov


def _engine_ready(engine):
    """¿El motor puede EJECUTAR agentes HOY? Instalado (engines/*.py) Y —si el
    motor expone available()— que ÉL lo confirme (p. ej. codex necesita `codex
    login` activo). Así codex pasa a 'listo' solo con sesión activa, no solo
    por existir el archivo. Falla-suave. Se llama al abrir el picker (no por
    tick); el propio motor cachea su chequeo de sesión."""
    if not engine:
        return False
    try:
        import dispatch
        if engine not in dispatch.available_engines():
            return False
        mod = dispatch.load_engine(engine)
        if mod is None:
            return False
        av = getattr(mod, "available", None)
        if callable(av):
            try:
                return bool(av())
            except Exception:
                return False
        return True                                  # sin available() = listo si instalado
    except Exception:
        return engine in _engines()


def _motor_options():
    """Opciones de MOTOR/CUENTA del panel por agente — DERIVADAS de las cuentas
    CONECTADAS (connectors.all_provider_status), NO de engines/*.py. Así el
    socio ve lo que conectó (claude-code, codex, …) y cualquier cuenta futura
    aparece SOLA. Cada opción:
      {provider, display, engine, ready, detail, group}
    · engine = el adaptador de ejecución instalado que corre esa cuenta (o '').
    · ready  = _engine_ready(engine): el engine existe Y está listo para
      ejecutar (codex ⇒ con sesión `codex login` activa). Las no-listas se
      MUESTRAN igual, etiquetadas honesto ('motor en construcción'), jamás se
      ocultan ni se simulan. stub/_template nunca aparecen. claude-code default.
    Falla-suave → [] (el panel cae al motor actual)."""
    out = []
    try:
        statuses = _connectors.all_provider_status() if _connectors else []
    except Exception:
        statuses = []
    avail = set(_engines())
    acct2eng = {v: k for k, v in _ENGINE_ACCOUNT.items()}   # provider → engine
    for st in statuses:
        name = st.get("name", "")
        if _hidden_name(name) or not st.get("ok"):          # solo CONECTADAS
            continue
        engine = acct2eng.get(name) or (name if name in avail else "")
        ready = _engine_ready(engine)
        if ready:
            detail = "motor listo — se aplica"
        elif engine and engine in avail:
            detail = "motor instalado pero sin sesión activa — corre `codex login`"
        elif st.get("connection") == "official_cli":
            detail = "conectada; motor CLI en construcción (aún no ejecuta agentes)"
        else:
            detail = "conectada; adaptador de ejecución en construcción"
        out.append({"provider": name,
                    "display": st.get("display") or name,
                    "engine": engine, "ready": ready, "detail": detail,
                    "group": st.get("group", "")})
    # orden: primero los LISTOS, luego por grupo (suscripción→API→local)
    out.sort(key=lambda o: (0 if o["ready"] else 1,
                            _GROUP_ORDER.index(o["group"])
                            if o["group"] in _GROUP_ORDER else 9,
                            o["display"]))
    return out


def _themes():
    """[(id, label)] de los temas del PICKER según el MOTOR
    (hubtheme.hub_picker() — la lista CURADA para el TUI: solo temas ya
    pulidos, olympo primero; los pendientes siguen accesibles vía
    WORKSPACE_THEME / ui.theme directo y los manifiestos rotos ya vienen
    filtrados). NUNCA se hardcodean ids aquí. Falla-suave triple: sin
    hub_picker (motor viejo) → available(); sin hubtheme → snapshot
    `choices` del schema de ui.theme; sin schema → ("olympo",) pelado.
    El picker jamás crashea por un tema roto."""
    try:
        import hubtheme
        src = getattr(hubtheme, "hub_picker", hubtheme.available)
        out = [(str(t["id"]),
                str(t.get("label") or "") or str(t["id"]).capitalize())
               for t in src() if t.get("id")]
        if out:
            return out
    except Exception:
        pass
    spec = _specs().get("ui.theme") or {}
    ids = [str(c) for c in (spec.get("choices") or ()) if c] or ["olympo"]
    return [(i, i.capitalize()) for i in ids]


def _layouts():
    """[(id, label)] de los layouts del hub SEGÚN EL REGISTRO
    (hublayout.available() — en vivo, clasico primero; NUNCA hardcodeados).
    Mismo patrón que _themes(): falla-suave doble — sin hublayout →
    snapshot `choices` del schema de ui.layout; sin schema → ('clasico',)."""
    try:
        import hublayout
        out = [(str(L["id"]), str(L.get("label") or "") or
                str(L["id"]).capitalize())
               for L in hublayout.available() if L.get("id")]
        if out:
            return out
    except Exception:
        pass
    spec = _specs().get("ui.layout") or {}
    ids = [str(c) for c in (spec.get("choices") or ()) if c] or ["clasico"]
    return [(i, i.capitalize()) for i in ids]


def _theme_label(themes, tid):
    """Nombre legible de un id (falla-suave: el id tal cual)."""
    for i, lbl in themes:
        if i == tid:
            return lbl
    return str(tid)


def _sget(key, fallback=None):
    """settings.get falla-suave (sin settings / key rara → fallback)."""
    try:
        return settings.get(key)
    except Exception:
        return fallback


def _source(key, env=""):
    """De dónde sale el valor EFECTIVO: env (override WORKSPACE_NO_*) →
    store (override del socio) → delegado (heartbeat.json / mecanismo
    dueño) → default. Falla-suave → 'default'."""
    try:
        if env and os.environ.get(env):
            return "env"
        if settings.get_stored(key) is not None:
            return "store"
        spec = _specs().get(key)
        if spec is not None and settings.get(key) != spec["default"]:
            return "delegado"
    except Exception:
        pass
    return "default"


def _item_for(key, kind=None, label=None, extra_help="", env="",
              choices=None, help_override=None):
    """Item editable a partir de un setting del schema (lectura efectiva +
    procedencia). `kind` fuerza el tipo de edición (p. ej. 'model').
    `help_override` reemplaza la ayuda del schema (lo usa PERSONALIZACIÓN para
    servir el texto desde el catálogo i18n sin tocar settings.py)."""
    spec = _specs().get(key) or {}
    val = _sget(key, spec.get("default"))
    env_on = bool(env and os.environ.get(env))
    helptx = str(help_override if help_override is not None
                 else spec.get("help", ""))
    if extra_help:
        helptx = (extra_help + " " + helptx).strip()
    return {"key": key, "kind": kind or spec.get("type", "str"),
            "label": label or spec.get("label", key),
            "value": val, "default": spec.get("default"),
            "range": spec.get("range"),
            "choices": tuple(choices or spec.get("choices") or ()),
            "help": helptx, "env": env, "env_on": env_on,
            "source": _source(key, env)}


def _hub_pin_items():
    """Items del selector de pins del hub (sección CONFIGS DEL HUB): un
    toggle por setting SEGURO (enum/bool, el filtro de settings.pinnable_keys)
    marcado si está anclado en ui.hub_pins. El toggle edita la lista con tope;
    el recinto los muestra editables en su sección CONFIGS rápidas.
    Falla-suave TOTAL → []."""
    try:
        pinnable = settings.pinnable_keys()
        pinned = list(settings.get("ui.hub_pins", []))
    except Exception:
        return []
    specs = _specs()
    items = []
    for k in pinnable:
        sp = specs.get(k) or {}
        lbl = sp.get("label", k)
        on = k in pinned
        items.append({"key": "pin:" + k, "kind": "pin", "pin_key": k,
                      "label": lbl, "value": on, "default": False,
                      "range": None, "choices": (),
                      "help": ("Anclar «%s» (%s) al recinto para cambiarlo "
                               "sin abrir la Config. " % (lbl, k))
                              + str(sp.get("help", "")),
                      "env": "", "env_on": False,
                      "source": "store" if on else "default"})
    return items


def build_sections():
    """Las 7 secciones del tier SIMPLE + AVANZADO (scaffold). Cada una:
    {id, title, desc, sub, items}. Falla-suave: sin settings.py devuelve
    una sección de aviso (la pantalla no crashea, solo informa)."""
    if settings is None:
        return [{"id": "err", "title": "CONFIG", "sub": "no disponible",
                 "desc": "settings.py no está junto a config_tui.py — "
                         "corre `workspace doctor`", "items": []}]
    secs = []
    # ── 1 · LATIDO ──
    lat = [_item_for("latido.mode"),
           _item_for("latido.intensity"),
           _item_for("latido.max_tokens_per_tick"),
           _item_for("latido.budget_cap_pct"),
           _item_for("latido.grace_min"),
           _item_for("latido.quiet_hours")]
    secs.append({"id": "latido", "title": "LATIDO",
                 "desc": "trabajo autónomo (heartbeat)",
                 "sub": "modo %s" % lat[0]["value"], "items": lat})
    # ── 2 · CRONS ACTIVOS (settings.JOBS — toggles del scheduler) ──
    jobs = []
    try:
        catalog = settings.JOBS
    except Exception:
        catalog = ()
    for j in catalog:
        alias = str(j.get("setting") or "")
        env = _HOOK_ENV_MAP.get(alias, "")
        try:
            en = settings.is_job_enabled(j["id"])
        except Exception:
            en = bool(j.get("default", True))
        jobs.append({"key": "job:" + j["id"], "kind": "job",
                     "job_id": j["id"], "label": j["label"], "value": en,
                     "default": bool(j.get("default", True)),
                     "range": None, "choices": (),
                     "help": str(j.get("desc", "")) +
                             (" (scaffold: aún sin scheduler corriendo — el "
                              "flag queda listo)" if j.get("scaffold") else ""),
                     "env": env, "env_on": bool(env and os.environ.get(env)),
                     "source": _source(alias, env) if alias else
                               ("store" if en != bool(j.get("default", True))
                                else "default")})
    on = sum(1 for x in jobs if x["value"])
    secs.append({"id": "crons", "title": "CRONS ACTIVOS",
                 "desc": "trabajos programados del harness",
                 "sub": "%d/%d activos" % (on, len(jobs)), "items": jobs})
    # ── 3 · BUDGET DE TOKENS (dos canales DISTINTOS — pedido del socio) ──
    bud = [_item_for("latido.budget_cap_pct",
                     label="Colchón de sesión — suscripción (%)",
                     extra_help="(a) AUTH/SUSCRIPCIÓN: es el MISMO "
                                "latido.budget_cap_pct de LATIDO — el "
                                "colchón de seguridad del plan 5h."),
           _item_for("budget.api_token_limit",
                     label="Límite de tokens — API")]
    cap = bud[0]["value"]
    api = bud[1]["value"]
    secs.append({"id": "budget", "title": "BUDGET DE TOKENS",
                 "desc": "suscripción (colchón 5h) vs API (tope de tokens)",
                 "sub": "colchón %s%% · API %s" % (
                     cap, "sin límite" if not api else api),
                 "items": bud})
    # ── 4 · MODELO POR AGENTE (UNA fila por agente → panel enfocado) ──
    try:
        agents = _agents()
    except Exception:                                # doble cinturón: jamás
        agents = ["zenith", "atlas", "argus"]        # tumba la pantalla
    eng_map = _agent_engine_map()
    mods = []
    n_over = 0
    for a in agents:
        row = eng_map.get(a) or {}
        disp = str(row.get("display") or a.capitalize())
        default_engine = str(row.get("engine") or "")       # el del agent.json
        eng_override = _sget("agentes.%s.engine" % a, "")    # per-máquina (tier A)
        engine = eng_override or default_engine              # EFECTIVO
        tier = str(row.get("tier") or "")
        override = _sget("agentes.%s.model" % a, "")
        if override or eng_override:
            n_over += 1
        # en motores 'auto' (codex) la cuenta elige el modelo — el override no
        # aplica: se muestra "(auto)" para no confundir (aunque haya un valor).
        model_disp = ("(auto)" if engine in _ENGINE_MODEL_AUTO
                      else (override or "(por defecto)"))
        mods.append({
            "key": "agent:%s" % a, "kind": "agent", "agent": a,
            "label": disp, "engine": engine, "tier": tier,
            "default_engine": default_engine, "engine_override": eng_override,
            "override": override or "",
            "value": "%s · %s" % (_engine_label(engine), model_disp),
            "default": None, "range": None, "choices": (),
            "help": ("Motor/cuenta y modelo de %s. Enter abre el panel: elige "
                     "motor (entre cuentas conectadas) y modelo (ids del "
                     "motor). Precedencia del modelo: override por agente › "
                     "routing por tarea › default del motor." % disp),
            "env": "", "env_on": False,
            "source": "store" if override else "default"})
    secs.append({"id": "modelos", "title": "MODELO POR AGENTE",
                 "desc": "una fila por agente — Enter ajusta motor y modelo "
                         "(override por agente › routing por tarea › default)",
                 "sub": "%d con override%s" % (n_over, "" if n_over == 1 else "s"),
                 "items": mods})
    # ── CUENTAS / CONEXIONES (asistente guiado + overview tipo doctor) ──
    accounts = []
    try:
        statuses = _connectors.all_provider_status() if _connectors else []
    except Exception:
        statuses = []
    statuses = [s for s in statuses if not _hidden_name(s.get("name"))]
    statuses.sort(key=lambda s: (                    # agrupado: suscripción →
        _GROUP_ORDER.index(s.get("group", "other"))  # API medida → local → …
        if s.get("group") in _GROUP_ORDER else 9, s.get("name", "")))
    for stx in statuses:
        accounts.append({
            "key": "account:%s" % stx.get("name", "?"), "kind": "account",
            "provider": stx.get("name", "?"), "status": stx,
            "label": stx.get("display") or stx.get("name", "?"),
            "value": stx.get("state", "unknown"),
            "default": None, "range": None, "choices": (),
            "help": stx.get("detail", ""), "env": "", "env_on": False,
            "group": stx.get("group", "other"),
            "source": stx.get("state", "unknown")})
    n_conn = sum(1 for a in accounts if (a["status"] or {}).get("ok"))
    # overview por grupo (sabor doctor): "Suscripción 1/2 · API medida 1/4 · …"
    gc = {}
    for a in accounts:
        d = gc.setdefault(a["group"], [0, 0])
        d[1] += 1
        if (a["status"] or {}).get("ok"):
            d[0] += 1
    parts = ["%s %d/%d" % (_GROUP_LABEL.get(g, g), gc[g][0], gc[g][1])
             for g in _GROUP_ORDER if g in gc]
    sub = " · ".join(parts) if parts else "%d/%d conectadas" % (n_conn,
                                                                len(accounts))
    desc = ("conectar cuentas — Enter abre el asistente guiado"
            if n_conn else "aún no conectas ninguna — elige una y Enter para "
                           "el asistente de conexión")
    secs.append({"id": "cuentas", "title": "CUENTAS", "desc": desc,
                 "sub": sub, "items": accounts})
    # ── ROUTING POR TAREA (formato CONGELADO — config_engine tier A) ──
    if _config_engine is not None:
        routes = []
        try:
            rmap = _config_engine.get_task_routing()
        except Exception:
            rmap = {}
        rchoices = ("",) + _provider_models()
        for task in _routing_tasks():
            cur = str(rmap.get(task) or "")
            routes.append({
                "key": "route:%s" % task, "kind": "route", "route_task": task,
                "label": "Modelo para %s" % task, "value": cur,
                "default": "", "range": None, "choices": rchoices,
                "help": ("Qué modelo/cuenta usa la tarea '%s' (formato "
                         "CONGELADO modelos.task_routing). IDs reales de "
                         "providers/*.json; vacío = sin regla (model_resolver "
                         "cae a utility/default). Persiste por config_engine "
                         "(tier A: valida + gate de secretos + changelog)."
                         % task),
                "env": "", "env_on": False,
                "source": "store" if cur else "default"})
        n_routes = sum(1 for r in routes if r["value"])
        secs.append({"id": "routing", "title": "ROUTING POR TAREA",
                     "desc": "qué cuenta/modelo por tipo de tarea "
                             "(research/task/utility/default) — congelado",
                     "sub": "%d/%d con regla" % (n_routes, len(routes)),
                     "items": routes})
    # ── 5 · HOOKS (kill-switches — el env WORKSPACE_NO_* SIEMPRE gana) ──
    hks = [_item_for(k, env=e) for k, e in HOOK_ENV]
    n_on = sum(1 for h in hks if (h["value"] and not h["env_on"]))
    secs.append({"id": "hooks", "title": "HOOKS",
                 "desc": "kill-switches (el env WORKSPACE_NO_* siempre gana)",
                 "sub": "%d/%d prendidos" % (n_on, len(hks)), "items": hks})
    # ── 6 · TEMA (apariencia del HUB — ui.theme con PICKER + stars/anim; el
    #    tema del dev panel web es ui.web_theme, aparte) ──
    themes = _themes()
    th_it = _item_for(
        "ui.theme", kind="theme",
        label=_t("personalizacion.theme.label", "Tema del hub"),
        env="WORKSPACE_THEME", choices=[t[0] for t in themes],
        help_override=_t(
            "personalizacion.theme.help",
            "Tema visual del HUB/TUI del recinto (front.py/banner/config_tui). "
            "Acotado a los temas TUI-ready (mono, cyberpunk, rose, durazno, "
            "lavanda, salvia, bruma). El dev panel web tiene su propio tema "
            "(ui.web_theme, todos disponibles). env WORKSPACE_THEME gana siempre."))
    th_it["themes"] = tuple(themes)
    ui_items = [th_it,
                _item_for(
                    "ui.background",
                    label=_t("personalizacion.background.label",
                             "Fondo independiente"),
                    help_override=_t(
                        "personalizacion.background.help",
                        "Cambia solo el fondo; tema recupera el fondo del tema "
                        "activo.")),
                _item_for(
                    "ui.background_custom",
                    label=_t("personalizacion.background_custom.label",
                             "Color de fondo propio"),
                    help_override=_t(
                        "personalizacion.background_custom.help",
                        "Color #RRGGBB; elige personalizado en Fondo "
                        "independiente.")),
                _item_for(
                    "ui.stars", env="WORKSPACE_NO_STARS",
                    label=_t("personalizacion.stars.label", "Cielo estrellado"),
                    help_override=_t(
                        "personalizacion.stars.help",
                        "Campo de estrellas estático del recinto (front.py).")),
                _item_for(
                    "ui.anim", env="WORKSPACE_NO_ANIM",
                    label=_t("personalizacion.anim.label", "Animaciones"),
                    help_override=_t(
                        "personalizacion.anim.help",
                        "Menú animado del recinto y banner animado (sin esto: "
                        "estático + picker)."))]
    # el sub muestra el tema EFECTIVO (env WORKSPACE_THEME > store > olympo)
    eff = th_it["value"]
    try:
        import hubtheme
        eff = hubtheme.resolve_id()
    except Exception:
        pass
    eff_label = _theme_label(themes, eff)
    secs.append({"id": "tema",
                 "title": _t("personalizacion.section.title", "TEMA"),
                 "desc": _t("personalizacion.section.desc",
                            "apariencia del hub (el dev panel web usa "
                            "ui.web_theme)"),
                 "sub": _t("personalizacion.section.sub_active",
                           "activo {name}", name=eff_label),
                 "items": ui_items})
    # ── 7 · LAYOUT (estructura del hub — ui.layout con PICKER, eje
    #    INDEPENDIENTE del tema: cualquier layout combina con cualquier
    #    tema). Reusa el plumbing del picker de tema (kind + campo "themes"
    #    con las opciones (id, label) — mismo modo "pick"). ──
    layouts = _layouts()
    ly_it = _item_for("ui.layout", kind="layout", label="Layout del hub",
                      env="WORKSPACE_LAYOUT",
                      choices=[l[0] for l in layouts])
    ly_it["themes"] = tuple(layouts)
    eff_l = ly_it["value"]
    try:
        import hublayout
        eff_l = hublayout.resolve_id()
    except Exception:
        pass
    # ui.split — toggle para el SOCIO (sin `settings set`): mismo patrón
    # bool que ui.stars/ui.anim, persiste vía settings como cualquier
    # toggle. El gate vive SOLO en front.launch (post-menú) — el hub/menú
    # JAMÁS cambian por esto (regla #1; golden test en test_split_hub.py).
    sp_it = _item_for("ui.split",
                      label="Pantalla partida al abrir un chat — "
                            "chat | pipeline",
                      extra_help="Necesita un multiplexer (tmux o herdr); "
                                 "en Windows o sin ninguno se ignora "
                                 "(arranque normal). El hub y el menú no "
                                 "cambian.")
    # ui.split_backend — enum hermano del toggle (mismo patrón que cualquier
    # enum: Espacio/Enter cicla auto → tmux → herdr). Solo aplica con
    # ui.split prendido; la selección real vive en multiplexer.pick_backend.
    bk_it = _item_for("ui.split_backend",
                      label="Backend de la pantalla partida",
                      env="WORKSPACE_SPLIT_BACKEND",
                      extra_help="auto = herdr si está instalado y "
                                 "responde, si no tmux.")
    secs.append({"id": "layout", "title": "LAYOUT",
                 "desc": "estructura del hub y del chat "
                         "(independiente del tema)",
                 "sub": "activo %s%s" % (
                     _theme_label(layouts, eff_l),
                     " · chat partido" if sp_it["value"] else ""),
                 "items": [ly_it, sp_it, bk_it]})
    # ── 8 · CONFIGS DEL HUB (selector de pins: qué anclar al recinto para
    #    cambio rápido — edita ui.hub_pins; solo settings SEGUROS enum/bool,
    #    tope máx 5). El recinto (front.py/hublayout) los muestra EDITABLES
    #    en su sección CONFIGS rápidas. ──
    pin_items = _hub_pin_items()
    try:
        cap = settings.hub_pins_cap()
    except Exception:
        cap = 5
    n_pinned = sum(1 for it in pin_items if it["value"])
    secs.append({"id": "hubpins", "title": "CONFIGS DEL HUB",
                 "desc": "qué ajustes anclar al recinto para cambio rápido "
                         "(Espacio ancla/quita · máx %d)" % cap,
                 "sub": "%d/%d anclados" % (n_pinned, cap),
                 "items": pin_items})
    # ── AVANZADO (scaffold v2 — solo el lugar, sin opciones aún) ──
    secs.append({"id": "avanzado", "title": "AVANZADO",
                 "desc": "tier avanzado — reservado para v2",
                 "sub": "próximamente", "items": [
                     {"key": "avanzado", "kind": "scaffold",
                      "label": "Tier avanzado", "value": False,
                      "default": False, "range": None, "choices": (),
                      "help": "Reservado para v2: routing por tarea, "
                              "providers/failover, retención de transcripts, "
                              "transporte por agente. Aún sin opciones — el "
                              "tier SIMPLE cubre la operación diaria.",
                      "env": "", "env_on": False, "source": "default"}]})
    return secs


# ═══════════════════════════════════════════════════════════════════════════
# Estado (puro, testeable sin tty)
# ═══════════════════════════════════════════════════════════════════════════

def new_state():
    """Estado inicial de la pantalla. `cur` indexa la lista plana de items
    (todas las secciones en orden + la salida al final)."""
    S = {"sections": [], "cur": 0, "mode": "nav", "buf": "",
         "edit_key": "", "status": "", "saved_key": "", "saved_ttl": 0,
         "pick_idx": 0, "connect": {}, "agent": {}, "shell_request": None}
    refresh(S)
    return S


def refresh(S):
    """Relee settings/jobs del disco (cambios externos aparecen solos) y
    re-clampa el cursor. Falla-suave: deja el estado anterior si truena.
    También desvanece la marca "» guardado" (un tick menos de vida)."""
    try:
        S["sections"] = build_sections()
    except Exception:
        pass
    S["cur"] = max(0, min(len(_flat(S)) - 1, int(S.get("cur", 0))))
    try:
        ttl = int(S.get("saved_ttl", 0) or 0)
    except Exception:
        ttl = 0
    if ttl > 0:
        S["saved_ttl"] = ttl - 1
        if S["saved_ttl"] <= 0:
            S["saved_key"] = ""


def _mark_saved(S, key):
    """El cambio QUEDÓ en el store: marca el item con "» guardado" por unos
    ticks. Llamar DESPUÉS de refresh() para que el decay no se coma el
    primer frame de la marca."""
    S["saved_key"] = key
    S["saved_ttl"] = SAVED_TTL


def _flat(S):
    """Lista plana navegable: [(sec_idx, item_idx)…] + la salida al final."""
    out = []
    for si, sec in enumerate(S.get("sections") or []):
        for ii in range(len(sec.get("items") or ())):
            out.append((si, ii))
    out.append((EXIT, 0))
    return out


def current_item(S):
    """Item bajo el cursor; None = la entrada ‹ Salir al menú."""
    flat = _flat(S)
    si, ii = flat[max(0, min(len(flat) - 1, S.get("cur", 0)))]
    if si == EXIT:
        return None
    try:
        return S["sections"][si]["items"][ii]
    except Exception:
        return None


def _cur_sec(S):
    """Índice de la sección bajo el cursor (EXIT si está en la salida)."""
    flat = _flat(S)
    return flat[max(0, min(len(flat) - 1, S.get("cur", 0)))][0]


def handle_arrow(S, d):
    """↑↓ recorre TODOS los items (sección tras sección) hasta ‹ Salir al
    menú, con tope; ◄► salta directo de sección. En edición las flechas se
    ignoran; en el PICKER de tema ↑↓ mueven la opción resaltada (◄► se
    ignoran). NUNCA devuelve "exit" — una flecha jamás saca de la pantalla."""
    if S.get('_size_blocked'):
        return
    S.pop('_viewport_offset', None)
    if S.get("mode") in ("edit", "connect"):
        return                                       # el asistente no navega la lista
    if S.get("mode") == "agent":                     # panel por agente
        a = S.get("agent") or {}
        if d in ("up", "down"):
            delta = -1 if d == "up" else 1
            if a.get("step", "overview") == "overview":   # ↑↓ eligen la FILA
                a["row_idx"] = max(0, min(len(_AGENT_ROWS) - 1,
                                          int(a.get("row_idx", 0)) + delta))
            else:                                         # sub-picker: la opción
                n = len(a.get("opts") or [])
                a["pick_idx"] = max(0, min(max(0, n - 1),
                                           int(a.get("pick_idx", 0)) + delta))
        return
    if S.get("mode") == "pick":
        if d in ("up", "down"):
            n = len(_pick_themes(S))
            step = -1 if d == "up" else 1
            S["pick_idx"] = max(0, min(max(0, n - 1),
                                       int(S.get("pick_idx", 0)) + step))
        return
    flat = _flat(S)
    if d in ("up", "down"):
        step = -1 if d == "up" else 1
        S["cur"] = max(0, min(len(flat) - 1, S.get("cur", 0) + step))
        return
    if d in ("left", "right"):
        step = -1 if d == "left" else 1
        si = _cur_sec(S)
        n = len(S.get("sections") or [])
        if si == EXIT:
            tgt = (n - 1) if step < 0 else EXIT
        else:
            tgt = si + step
            if tgt < 0:
                tgt = 0
            elif tgt >= n:
                tgt = EXIT
        for j, (s, i) in enumerate(flat):
            if s == tgt and (tgt == EXIT or i == 0):
                S["cur"] = j
                return


def handle_key(S, ch):
    """Una tecla (los drivers ya tradujeron flechas/Esc). Devuelve "exit" o
    None. Salidas DELIBERADAS y nada más: Esc en navegación, Ctrl-C, o Enter
    sobre ‹ Salir al menú. Esc en edición SOLO cancela la edición."""
    if ch == "\x03":                                 # Ctrl-C
        return "exit"
    if S.get("mode") == "connect":                   # ASISTENTE de conexión
        return _connect_key(S, ch)
    if S.get("mode") == "agent":                     # PANEL por agente
        return _agent_panel_key(S, ch)
    if S.get("mode") == "pick":                      # PICKER de tema abierto
        if ch == "\x1b":                             # Esc SOLO cierra el picker
            S["mode"], S["edit_key"] = "nav", ""
            S["status"] = "picker cerrado — sin cambios"
            return None
        if ch in ("\r", "\n"):
            _commit_pick(S)
            return None
        if ch.isdigit() and ch != "0":               # 1-9 = elegir directo
            idx = int(ch) - 1
            if idx < len(_pick_themes(S)):
                S["pick_idx"] = idx
                _commit_pick(S)
            return None
        return None
    if S.get("mode") == "edit":
        if ch == "\x1b":
            S["mode"], S["buf"], S["edit_key"] = "nav", "", ""
            S["status"] = "edición cancelada — sin cambios"
            return None
        if ch in ("\r", "\n"):
            _commit_edit(S)
            return None
        if ch in ("\x7f", "\x08"):                   # ⌫ borra del buffer
            S["buf"] = S["buf"][:-1]
            return None
        if ch >= " ":
            S["buf"] += ch
        return None
    # ── navegación ──
    if ch == "\x1b":                                 # Esc REAL → al recinto
        return "exit"
    it = current_item(S)
    if ch in ("\r", "\n"):
        if it is None:                               # ‹ Salir al menú
            return "exit"
        kind = it["kind"]
        if kind in ("bool", "job", "enum"):
            _toggle(S, it)
        elif kind == "pin":
            _toggle_pin(S, it)                       # ancla/quita del hub
        elif kind in ("theme", "layout"):
            _open_pick(S, it)                        # Enter abre el PICKER
        elif kind == "account":
            _open_connect(S, it)                     # asistente guiado
        elif kind == "agent":
            _open_agent(S, it)                       # panel motor↔modelo
        elif kind in ("int", "str", "route"):
            _open_edit(S, it)
        elif kind == "scaffold":
            S["status"] = "Avanzado: reservado para v2 — sin opciones todavía"
        return None
    if ch == " ":
        if it is None:
            return None
        kind = it["kind"]
        if kind in ("bool", "job", "enum", "model", "theme", "layout",
                    "route", "engine"):
            _toggle(S, it)
        elif kind == "pin":
            _toggle_pin(S, it)
        elif kind == "account":
            _open_connect(S, it)                     # Espacio también abre el asistente
        elif kind == "agent":
            _open_agent(S, it)
        elif kind == "scaffold":
            S["status"] = "Avanzado: reservado para v2 — sin opciones todavía"
        return None
    return None


def _open_edit(S, it):
    """Enter en int/str/model → input inline prellenado con el valor actual
    (en MODELOS, Espacio cicla los conocidos; Enter aquí es el input libre)."""
    S["mode"], S["edit_key"] = "edit", it["key"]
    S["buf"] = "" if it["value"] is None else str(it["value"])
    S["status"] = ""


def _apply_set(S, key, value):
    """settings.set con manejo de errores: inválido → aviso SIN escribir
    (ValueError del schema); cualquier otra falla → aviso falla-suave."""
    try:
        return True, settings.set(key, value)
    except ValueError as e:
        S["status"] = "%s" % e
    except Exception as e:
        S["status"] = "no pude guardar (%s: %s)" % (type(e).__name__, e)
    return False, None


def _env_note(it):
    return (" — OJO: %s está activa y SIEMPRE gana; el cambio no aplica "
            "hasta quitar la env" % it["env"]) if it.get("env_on") else ""


def _toggle_pin(S, it):
    """Espacio/Enter sobre un item del selector de pins: ancla/desancla
    it['pin_key'] en ui.hub_pins. Respeta el TOPE (settings.hub_pins_cap):
    al superar, avisa SIN escribir. Todo vía settings.set (que revalida y
    filtra) — falla-suave: cualquier problema → aviso, jamás rompe."""
    key = it["pin_key"]
    try:
        cur = list(settings.get("ui.hub_pins", []))
        cap = settings.hub_pins_cap()
    except Exception:
        S["status"] = "no pude leer las configs del hub"
        return
    if it["value"]:                                  # ya anclado → quitar
        nxt, verb = [k for k in cur if k != key], "desanclado del hub"
    else:                                            # anclar (si cabe)
        if len([k for k in cur if k != key]) >= cap:
            S["status"] = ("tope de %d configs alcanzado — quita una antes "
                           "de anclar «%s»" % (cap, it["label"]))
            return
        nxt = cur + ([key] if key not in cur else [])
        verb = "anclado al hub"
    ok, _ = _apply_set(S, "ui.hub_pins", nxt)
    if ok:
        S["status"] = "guardado: %s %s" % (it["label"], verb)
        refresh(S)
        _mark_saved(S, it["key"])


def _toggle(S, it):
    """Espacio/Enter sobre bool/job (toggle) o enum/model (ciclar opción).
    Todo via settings.set / settings.set_job_enabled; refresca al guardar."""
    kind = it["kind"]
    if kind == "job":
        try:
            nv = not bool(it["value"])
            settings.set_job_enabled(it["job_id"], nv)
            S["status"] = ("guardado: cron %s → %s — ya corre así" % (
                it["job_id"], "on" if nv else "off")) + _env_note(it)
            refresh(S)
            _mark_saved(S, it["key"])
        except Exception as e:
            S["status"] = "no pude guardar (%s: %s)" % (type(e).__name__, e)
            refresh(S)
        return
    if kind == "bool":
        nv = not bool(it["value"])
        ok, _ = _apply_set(S, it["key"], nv)
        if ok:
            S["status"] = ("guardado: %s → %s — ya corre así" % (it["key"],
                           "on" if nv else "off")) + _env_note(it)
            refresh(S)
            _mark_saved(S, it["key"])
        return
    if kind in ("enum", "model", "theme", "layout", "route"):
        ch = list(it["choices"] or ())
        if not ch:
            return
        cur = it["value"]
        nxt = ch[(ch.index(cur) + 1) % len(ch)] if cur in ch else ch[0]
        if kind in ("theme", "layout"):
            _set_theme(S, it, nxt)
            return
        if kind == "route":                          # config_engine tier A
            _set_route(S, it, nxt)
            return
        ok, v = _apply_set(S, it["key"], nxt)
        if ok:
            S["status"] = ("guardado: %s → %s — ya corre así" % (
                it["key"], v if v != "" else "(el del agente)")) + \
                _env_note(it)
            refresh(S)
            _mark_saved(S, it["key"])


# ── PICKER de tema (kind "theme": Enter abre lista · ↑↓/1-9 · Enter aplica) ─

def _pick_themes(S):
    """[(id, label)] del item pickeable BAJO EL CURSOR (tema O layout — el
    picker solo se abre ahí; ambos kinds guardan sus opciones en el campo
    "themes"). Falla-suave: item raro/sin lista → lista viva del motor."""
    it = current_item(S)
    if it is not None and it.get("kind") in ("theme", "layout") \
            and it.get("themes"):
        return list(it["themes"])
    if it is not None and it.get("kind") == "layout":
        return _layouts()
    return _themes()


def _open_pick(S, it):
    """Enter sobre el tema → modo pick: lista de temas instalados (nombre +
    id) resaltando el ACTIVO; ↑↓ mueven, 1-9 eligen directo, Enter aplica y
    persiste, Esc cancela sin tocar nada."""
    themes = list(it.get("themes") or _themes())
    ids = [t[0] for t in themes]
    S["mode"], S["edit_key"] = "pick", it["key"]
    S["pick_idx"] = ids.index(it["value"]) if it["value"] in ids else 0
    S["status"] = ""


def _set_theme(S, it, tid):
    """Aplica y persiste ui.theme / ui.layout (settings.set valida contra el
    registro VIVO del motor — un id recién desaparecido avisa SIN escribir).
    Feedback honesto de CUÁNDO se ve el cambio, por kind."""
    ok, v = _apply_set(S, it["key"], tid)
    if ok:
        opts = list(it.get("themes") or ())
        lbl = _theme_label(opts or (_layouts() if it.get("kind") == "layout"
                                    else _themes()), v)
        if it.get("kind") == "layout":
            S["status"] = _t(
                "personalizacion.saved.layout",
                "guardado: layout → {label} ({id}) — el hub se dibuja así al "
                "reabrirse (workspace)", label=lbl, id=v) + _env_note(it)
        else:
            S["status"] = _t(
                "personalizacion.saved.theme",
                "guardado: tema → {label} ({id}) — el recinto lo pinta al "
                "reabrirse; el panel web al refrescar", label=lbl, id=v) \
                + _env_note(it)
        refresh(S)
        _mark_saved(S, it["key"])


def _commit_pick(S):
    """Enter (o dígito) en el picker: persiste el tema resaltado y regresa
    a navegación. El item pudo moverse bajo un refresh() del tick — se
    re-resuelve por key, falla-suave si desapareció."""
    themes = _pick_themes(S)
    idx = max(0, min(len(themes) - 1, int(S.get("pick_idx", 0))))
    S["mode"], S["edit_key"] = "nav", ""
    if not themes:
        S["status"] = "no hay temas instalados (themes/ vacío)"
        return
    it = current_item(S)
    if it is None or it.get("kind") not in ("theme", "layout"):
        S["status"] = "picker cerrado — sin cambios"
        return
    _set_theme(S, it, themes[idx][0])


def _commit_edit(S):
    """Enter en edición: valida y persiste vía settings.set. Vacío =
    restaurar default (settings.reset). Inválido → aviso y SIGUE en edición
    (corrige o Esc); válido → guardado, de regreso a navegación."""
    key, raw = S.get("edit_key", ""), S.get("buf", "").strip()
    if not key or settings is None:
        S["mode"], S["buf"], S["edit_key"] = "nav", "", ""
        return
    # Routing por tarea → config_engine (tier A).
    if key.startswith("route:"):
        S["mode"], S["buf"], S["edit_key"] = "nav", "", ""
        _write_route(S, key[len("route:"):], raw, key)
        return
    saved = False
    if raw == "":
        try:
            settings.reset(key)
            S["status"] = "guardado: %s → default (%s) — ya corre así" % (
                key, _sget(key, ""))
            saved = True
        except Exception as e:
            S["status"] = "no pude restaurar (%s: %s)" % (type(e).__name__, e)
    else:
        ok, v = _apply_set(S, key, raw)
        if not ok:
            return                                   # aviso puesto; sigue editando
        S["status"] = "guardado: %s → %s — ya corre así" % (key, v)
        saved = True
    S["mode"], S["buf"], S["edit_key"] = "nav", "", ""
    refresh(S)
    if saved:
        _mark_saved(S, key)


# ═══════════════════════════════════════════════════════════════════════════
# ASISTENTE de conexión (mode "connect") — flujo GUIADO paso a paso, estilo
# onboarding: explica la cuenta, de dónde sacar la credencial, pega (oculta),
# VALIDA con un ping real, y para suscripciones instala/loguea el CLI oficial
# (con confirmación, sin extraer jamás el token). Puro/testeable: el ping se
# corre síncrono con _PING_SYNC; el exec del CLI lo delega al driver por
# S["shell_request"] (aquí solo se AGENDA, jamás se ejecuta).
# ═══════════════════════════════════════════════════════════════════════════

def _cstatus(provider):
    """provider_status fresco de un provider por nombre (falla-suave → {})."""
    try:
        p, errs = _model_resolver.load_provider(provider)
        if errs:
            return {"name": provider, "state": "blocked", "blocked": errs,
                    "detail": errs[0]}
        return _connectors.provider_status(p)
    except Exception:
        return {}


def _open_connect(S, it):
    """Abre el ASISTENTE para una cuenta. official_cli → paso 'cli' (instalar/
    login); api_key/local → paso 'intro'."""
    stx = _cstatus(it["provider"]) or it.get("status") or {}
    step = "cli" if stx.get("connection") == "official_cli" else "intro"
    S["mode"] = "connect"
    S["connect"] = {"provider": it["provider"], "status": stx, "step": step,
                    "buf": "", "result": None, "confirm": ""}
    S["status"] = ""


def _close_connect(S):
    S["mode"], S["connect"] = "nav", {}


def _connect_key(S, ch):
    """Teclado del asistente (mode connect). Esc retrocede un paso o cierra —
    JAMÁS sale del TUI. Devuelve None (o 'exit' con Ctrl-C, ya filtrado)."""
    c = S.get("connect") or {}
    step = c.get("step")
    if ch == "\x1b":                                 # Esc: un paso atrás / cerrar
        if step == "paste":
            c["step"], c["buf"] = "intro", ""
        elif step == "cli_confirm":
            c["step"], c["confirm"] = "cli", ""
        else:
            _close_connect(S)
        return None
    if step == "paste":
        if ch in ("\r", "\n"):
            _start_validation(S)
        elif ch in ("\x7f", "\x08"):
            c["buf"] = c["buf"][:-1]
        elif ch >= " ":
            c["buf"] += ch
        return None
    if step == "validating":
        return None                                  # espera el ping (Esc cierra)
    if step == "result":
        if ch in ("\r", "\n"):
            if (c.get("result") or {}).get("kind") == "auth":
                c["step"], c["buf"] = "paste", ""    # reintentar con otra key
            else:
                _close_connect(S)
        return None
    if step == "intro":
        stx = c.get("status") or {}
        connected = bool(stx.get("state") == "connected")
        if ch in ("\r", "\n"):
            if connected:
                _start_validation(S)                 # revalidar (key del env)
            else:
                c["step"], c["buf"] = "paste", ""
        elif ch.lower() == "r":
            c["step"], c["buf"] = "paste", ""         # reemplazar la key
        elif ch.lower() == "d":
            _connect_disconnect(S)
        return None
    if step == "cli":
        stx = c.get("status") or {}
        low = ch.lower()
        if low == "i" and not stx.get("cli_present") and stx.get("install_cmd"):
            c["step"] = "cli_confirm"
        elif low == "l" and stx.get("login_cmd"):
            _request_shell(S, "login", stx.get("login_cmd"),
                           "Iniciar sesión en %s" % c.get("provider"))
        return None
    if step == "cli_confirm":
        if ch in ("\r", "\n"):
            stx = c.get("status") or {}
            _request_shell(S, "install", stx.get("install_cmd"),
                           "Instalar el CLI de %s" % c.get("provider"))
            c["step"], c["confirm"] = "cli", ""
        return None
    return None


def _connect_disconnect(S):
    """Desconectar desde el asistente: borra la key SI vive en NUESTRO
    secret_store (una env del sistema no es nuestra — no se toca)."""
    c = S.get("connect") or {}
    stx = c.get("status") or {}
    prov = c.get("provider")
    if _secret_store is None:
        S["status"] = "no hay secret_store disponible"
        return
    owned = [n for n in (stx.get("env_vars") or []) if _secret_store.has(n)]
    if not owned:
        if stx.get("env_present"):
            S["status"] = ("%s viene del env del sistema — quítala de tu "
                           "shell/perfil" % prov)
        else:
            S["status"] = "%s no está conectada" % prov
        return
    for n in owned:
        _secret_store.remove(n)
        os.environ.pop(n, None)
    _close_connect(S)
    refresh(S)
    S["status"] = "desconectada: %s (key borrada del store per-máquina)" % prov
    _mark_saved(S, "account:%s" % prov)


def _request_shell(S, kind, cmd, label):
    """AGENDA un comando externo (instalar CLI / login) para que el DRIVER lo
    corra con el TUI suspendido. Aquí JAMÁS se ejecuta (mantiene handle_key
    puro/testeable)."""
    if not cmd:
        S["status"] = "sin comando disponible para %s" % kind
        return
    S["shell_request"] = {"kind": kind, "cmd": list(cmd), "label": label,
                          "provider": (S.get("connect") or {}).get("provider", "")}


# ── validación por PING real (fail-soft, timeout corto, key redactada) ──────

def _start_validation(S):
    """Dispara el ping. En vivo: hilo daemon (no congela el TUI). En tests:
    inline (_PING_SYNC). El estado pasa a 'validating' y luego 'result'."""
    c = S.get("connect") or {}
    c["step"], c["result"] = "validating", None
    provider = c.get("provider")
    key = c.get("buf") or None                       # None = revalidar con el env
    if _PING_SYNC:
        _do_validation(S, provider, key)
    else:
        try:
            import threading
            threading.Thread(target=_do_validation, args=(S, provider, key),
                             daemon=True).start()
        except Exception:
            _do_validation(S, provider, key)


def _do_validation(S, provider, key):
    """Corre el ping, PERSISTE según el resultado (Regla de Oro) y deja el
    resultado en el asistente. Corre en hilo o inline — solo toca S['connect']
    y el secret_store."""
    res = {"ok": False, "kind": "network", "detail": "sin conectores"}
    try:
        if _connectors is not None and _model_resolver is not None:
            p, errs = _model_resolver.load_provider(provider)
            if errs:
                res = {"ok": False, "kind": "blocked", "detail": errs[0]}
            else:
                res = _connectors.ping_provider(p, key=key, timeout=PING_TIMEOUT)
    except Exception as e:
        res = {"ok": False, "kind": "network",
               "detail": "la validación falló: %s" % e}
    saved = _persist_validation(S, res, key)
    c = S.get("connect") or {}
    c["result"], c["step"] = res, "result"
    if saved:
        c["status"] = _cstatus(provider)             # refresca el estado mostrado
        _mark_saved(S, "account:%s" % provider)
        if _PING_SYNC:                                # en vivo lo hace el tick
            refresh(S)


def _persist_validation(S, res, key):
    """Guarda la key SEGÚN el veredicto: auth-fail ⇒ NO se guarda; verificada
    o inconclusa (red/endpoint) ⇒ se guarda al secret_store per-máquina +
    os.environ (para reflejar 'conectada' ya). Sin key (revalidación) ⇒ nada.
    El valor JAMÁS a settings ni al log."""
    c = S.get("connect") or {}
    stx = c.get("status") or {}
    names = stx.get("env_vars") or []
    if not key or not names or _secret_store is None:
        return False
    if res.get("kind") == "auth":                    # credencial rechazada
        return False
    name = names[0]
    r = _secret_store.set_secret(name, key)
    if not r.get("ok"):
        return False
    os.environ[name] = key
    return True


# ── ROUTING por tarea (config_engine tier A: valida + gate + changelog) ─────

def _set_route(S, it, value):
    _write_route(S, it["route_task"], value, it["key"])


def _write_route(S, task, value, mark_key):
    """Escribe una regla del routing por tarea vía config_engine.set_task_routing
    (formato CONGELADO, tier A). '' = quita la regla. Falla-suave."""
    if _config_engine is None:
        S["status"] = "routing no disponible (sin config_engine)"
        return
    try:
        cur = dict(_config_engine.get_task_routing())
    except Exception:
        cur = {}
    if value in ("", None):
        cur.pop(task, None)
    else:
        cur[task] = value
    try:
        res = _config_engine.set_task_routing(cur, actor="config-tui")
    except Exception as e:
        S["status"] = "no pude guardar el routing (%s: %s)" % (
            type(e).__name__, e)
        return
    if not res.get("ok"):
        S["status"] = "routing inválido: %s" % res.get("error", "?")
        return
    S["status"] = ("guardado: routing %s → %s — ya corre así"
                   % (task, value if value else "(sin regla)"))
    refresh(S)
    _mark_saved(S, mark_key)


# ═══════════════════════════════════════════════════════════════════════════
# PANEL POR AGENTE (mode "agent") — motor↔modelo COHERENTES, una entrada por
# agente. El MODELO (override) se aplica per-máquina (settings tier A); el
# MOTOR se escribe por config_engine.set_agent_field (TIERS): agente del EQUIPO
# ⇒ N3 (se PROPONE, no se aplica aquí — se dice UNA vez, claro). Puro/testeable.
# ═══════════════════════════════════════════════════════════════════════════

def _agent_effective_model(agent, engine, override):
    """(modelo_efectivo, origen) del agente. En motores 'auto' (codex) la CUENTA
    elige el modelo — el override NO aplica (se ignora, no rompe). Si no,
    precedencia: override por agente › routing por tarea (regla 'default') ›
    default del motor."""
    if engine in _ENGINE_MODEL_AUTO:                 # codex-ChatGPT: la cuenta
        return "(lo elige tu cuenta ChatGPT)", "auto (codex)"
    if override:
        return override, "override del agente"
    try:
        rt = _config_engine.get_task_routing() if _config_engine else {}
        if rt.get("default"):
            return rt["default"], "routing por tarea (default)"
    except Exception:
        pass
    return "(el del motor)", "default del motor"


#: Filas navegables del overview del panel (orden fijo). ↑↓ elige la fila,
#: Enter la activa — igual que el resto del config TUI (nada de adivinar letras).
_AGENT_ROWS = ("motor", "modelo", "clear")


def _open_agent(S, it):
    """Abre el PANEL enfocado de un agente (mode 'agent', paso 'overview')."""
    S["mode"] = "agent"
    S["agent"] = {"name": it["agent"], "display": it["label"],
                  "engine": it.get("engine", ""),
                  "default_engine": it.get("default_engine", ""),
                  "tier": it.get("tier", ""),
                  "step": "overview", "opts": [], "pick_idx": 0, "row_idx": 0}
    S["status"] = ""


def _close_agent(S):
    S["mode"], S["agent"] = "nav", {}


def _agent_panel_key(S, ch):
    """Teclado del panel por agente. overview: ↑↓ eligen la FILA, Enter la
    ABRE (m/o/x quedan de atajo secundario) · Esc cierra. motor/modelo: ↑↓ +
    1-9 + Enter aplica · Esc regresa. Nunca sale del TUI."""
    a = S.get("agent") or {}
    step = a.get("step", "overview")
    if ch == "\x1b":
        if step in ("motor", "modelo"):
            a["step"] = "overview"
        else:
            _close_agent(S)
        return None
    if step == "overview":
        if ch in ("\r", "\n"):                        # Enter = abrir la fila
            sel = _AGENT_ROWS[max(0, min(len(_AGENT_ROWS) - 1,
                                         int(a.get("row_idx", 0))))]
            _agent_activate_row(S, sel)
            return None
        low = ch.lower()                              # atajos secundarios
        if low == "m":
            _agent_open_motor(S)
        elif low == "o":
            _agent_open_modelo(S)
        elif low == "x":
            _agent_clear(S)
        return None
    if step in ("motor", "modelo"):
        opts = a.get("opts") or []
        if ch.isdigit() and ch != "0":
            i = int(ch) - 1
            if i < len(opts):
                a["pick_idx"] = i
                _agent_commit_pick(S)
            return None
        if ch in ("\r", "\n"):
            _agent_commit_pick(S)
        return None
    return None


def _agent_activate_row(S, sel):
    if sel == "motor":
        _agent_open_motor(S)
    elif sel == "modelo":
        _agent_open_modelo(S)
    elif sel == "clear":
        _agent_clear(S)


def _agent_open_motor(S):
    """Abre el sub-picker de MOTOR/CUENTA: opción "(por defecto)" para limpiar
    el override + las cuentas CONECTADAS. Se navega con ↑↓/1-9/Enter."""
    a = S.get("agent") or {}
    clear = {"provider": "", "clear": True, "ready": True, "detail": "",
             "display": "(por defecto del agente: %s)"
                        % _engine_label(a.get("default_engine", ""))}
    a["opts"] = [clear] + _motor_options()
    cur = a.get("engine")
    a["step"] = "motor"
    a["pick_idx"] = next((i for i, o in enumerate(a["opts"])
                          if o.get("engine") == cur and not o.get("clear")), 0)


def _agent_open_modelo(S):
    a = S.get("agent") or {}
    a["opts"] = _engine_model_choices(a.get("engine"))
    a["step"], a["pick_idx"] = "modelo", _idx_of(
        a["opts"], _sget("agentes.%s.model" % a["name"], ""))


def _agent_clear(S):
    """Quita AMBOS overrides per-máquina (modelo + motor) → default del agente."""
    a = S.get("agent") or {}
    name = a.get("name")
    changed = []
    for key, lbl in (("agentes.%s.model" % name, "modelo"),
                     ("agentes.%s.engine" % name, "motor")):
        try:
            if settings.get_stored(key) not in (None, ""):
                settings.reset(key)
                changed.append(lbl)
        except Exception:
            pass
    if changed:
        S["status"] = ("guardado: %s de %s → por defecto (per-máquina)"
                       % (" y ".join(changed), name))
        refresh(S)
        a["engine"] = a.get("default_engine", "")
        _mark_saved(S, "agent:%s" % name)
    else:
        S["status"] = "%s ya usa sus defaults (sin overrides)" % name


def _idx_of(seq, val):
    try:
        return list(seq).index(val)
    except (ValueError, TypeError):
        return 0


def _agent_commit_pick(S):
    """Aplica la opción resaltada del picker (motor o modelo) y vuelve a
    overview."""
    a = S.get("agent") or {}
    opts = list(a.get("opts") or [])
    if not opts:
        a["step"] = "overview"
        return
    val = opts[max(0, min(len(opts) - 1, int(a.get("pick_idx", 0))))]
    step = a.get("step")
    a["step"] = "overview"
    if step == "motor":
        _agent_set_engine(S, val)
    elif step == "modelo":
        _agent_set_model(S, val)


def _agent_set_model(S, value):
    """Modelo override del agente (settings tier A — se aplica per-máquina).
    '' = quitar (settings.reset → default). Falla-suave."""
    a = S.get("agent") or {}
    name = a.get("name")
    key = "agentes.%s.model" % name
    try:
        if value in ("", None):
            settings.reset(key)
            S["status"] = "guardado: modelo de %s → default del motor" % name
        else:
            settings.set(key, value)
            S["status"] = "guardado: modelo de %s → %s" % (name, value)
    except ValueError as e:
        S["status"] = "%s" % e
        return
    except Exception as e:
        S["status"] = "no pude guardar (%s: %s)" % (type(e).__name__, e)
        return
    refresh(S)
    _mark_saved(S, "agent:%s" % name)


def _agent_set_engine(S, opt):
    """Aplica una opción de MOTOR/CUENTA (dict). El override es PER-MÁQUINA
    (settings `agentes.<n>.engine`, tier A) — dispatch lo respeta al arrancar,
    y NO toca el agent.json committeado (preserva N3: el default de equipo
    sigue igual). Una cuenta 'en construcción' (ready=False) se informa honesto
    y no escribe (jamás se simula que corre). "(por defecto)" limpia el
    override."""
    a = S.get("agent") or {}
    name = a.get("name")
    if not isinstance(opt, dict):
        S["status"] = "opción de motor inválida"
        return
    key = "agentes.%s.engine" % name
    if opt.get("clear"):                              # volver al default del agente
        try:
            settings.reset(key)
        except Exception as e:
            S["status"] = "no pude limpiar (%s: %s)" % (type(e).__name__, e)
            return
        S["status"] = ("guardado: motor de %s → por defecto del agente "
                       "(per-máquina)" % name)
        refresh(S)
        a["engine"] = a.get("default_engine", "")
        _mark_saved(S, "agent:%s" % name)
        return
    disp = opt.get("display", "?")
    if not opt.get("ready"):
        S["status"] = ("%s: %s. Se ve como opción; se podrá usar cuando su "
                       "motor esté listo." % (disp, opt.get("detail",
                                                            "en construcción")))
        return
    engine = opt.get("engine", "")
    if not engine:
        S["status"] = "esa cuenta no tiene motor asociado todavía"
        return
    try:
        settings.set(key, engine)                     # tier A, per-máquina
    except ValueError as e:
        S["status"] = "%s" % e
        return
    except Exception as e:
        S["status"] = "no pude guardar (%s: %s)" % (type(e).__name__, e)
        return
    S["status"] = "guardado: motor de %s → %s (per-máquina)" % (name, disp)
    refresh(S)
    a["engine"] = engine
    _mark_saved(S, "agent:%s" % name)


# ═══════════════════════════════════════════════════════════════════════════
# Render (puro: estado + (w,h) → líneas; lo comparten Mac y Windows)
# ═══════════════════════════════════════════════════════════════════════════

def _enum_opt_label(it, c):
    """Etiqueta MOSTRADA de una opción enum — el valor GUARDADO sigue siendo el
    id crudo (`c`), solo cambia lo que se pinta. PERSONALIZACIÓN traduce las
    opciones de ui.background (tema/negro/grafito/…); el resto se muestra con su
    id tal cual, y '' = «el del agente» (los model enums). En `es` cada opción
    cae a su id ⇒ byte-idéntico a antes."""
    if c == "":
        return "el del agente"
    if it.get("key") == "ui.background":
        return _t("personalizacion.background.opt." + str(c), str(c))
    return c


def _fmt_val(it):
    """(texto, color) del valor actual de un item, ya con el override por
    env aplicado a la vista (env_on en hooks/jobs ⇒ off efectivo)."""
    v = it["value"]
    if it["kind"] == "pin":                          # anclado al hub sí/no
        return ("anclado", GREEN) if v else ("—", DIM)
    if it["kind"] in ("bool", "job"):
        eff = False if it.get("env_on") else bool(v)
        return _onoff(eff), (GREEN if eff else DIM)
    if it["kind"] == "model":
        return (str(v) if v else "(el del agente)"), (WH if v else DIM)
    if it["kind"] == "agent":                        # "Claude Code · opus"
        return str(v), (WH if it.get("override") else DIM)
    if it["kind"] == "route":
        return (str(v) if v else "(sin regla)"), (WH if v else DIM)
    if it["kind"] == "account":
        stx = it.get("status") or {}
        labels = {"connected": ("conectada", GREEN),
                  "reachable": ("alcanzable", C),
                  "needs_key": ("falta key", B),
                  "cli_missing": ("CLI ausente", RED),
                  "blocked": ("rechazada", RED),
                  "unknown": ("—", DIM)}
        return labels.get(stx.get("state", "unknown"), (str(v), DIM))
    if it["kind"] in ("theme", "layout"):            # nombre legible + id
        lbl = _theme_label(list(it.get("themes") or ()), v)
        return (("%s · %s" % (lbl, v)) if lbl != str(v) else str(v)), WH
    if it["key"] == "ui.background":                 # opción traducida (PERSONAL.)
        return _enum_opt_label(it, str(v)), WH
    if it["key"] == "budget.api_token_limit":
        return ("sin límite" if not v else str(v)), (DIM if not v else WH)
    if v == "" or v is None:
        return "(vacío)", DIM
    return str(v), WH


def _left_lines(S, rows, lw):
    """Panel izquierdo: cabecera + lista de secciones (título + resumen
    tenue) + ‹ Salir al menú anclado al fondo. ADAPTATIVO en alto: 3 líneas
    por sección (título+sub+aire) si caben; si no, 2 (sin aire); si ni así,
    1 (solo título) — TODAS las secciones se ven siempre (con el eje LAYOUT
    ya son 8 y en 30 filas el aire es lo primero que sobra)."""
    cur_si = _cur_sec(S)
    secs = S.get("sections") or []
    body = rows - 4                       # cabecera(2) + colchón de salida(2)
    per = 3
    if len(secs) * 3 > body:
        per = 2
    if len(secs) * 2 > body:
        per = 1
    L = [_cell([("  CONFIGURACIÓN", B2 + BO)], lw), " " * lw]
    for si, sec in enumerate(secs):
        on = (si == cur_si)
        L.append(_cell([("  ▸ " if on else "    ", C + BO),
                        (sec["title"].capitalize(),
                         (WH + BO) if on else B2)], lw))
        sub = sec.get("sub", "")
        if sub and per >= 2:
            L.append(_cell([("      " + _fit(sub, lw - 7),
                             GREY if on else DIM)], lw))
        if per >= 3:
            L.append(" " * lw)
    while len(L) < rows - 2:
        L.append(" " * lw)
    L = L[:rows - 2]
    on_exit = (cur_si == EXIT)
    L.append(" " * lw)
    L.append(_cell([("  ▸ " if on_exit else "    ", C + BO),
                    (EXIT_LABEL, (C + BO) if on_exit else GREY)], lw))
    return L[:rows]


def _detail_lines(S, it, rw):
    """Pie del panel derecho para el item SELECCIONADO: key = valor ·
    default · origen · rango, y su help envuelta (con la nota de override
    por env cuando aplica). Ancho fijo rw."""
    if it is None:
        return [_cell([("  Enter sale al recinto de los dioses", DIM)], rw)]
    out = []
    is_job = str(it["key"]).startswith("job:")
    name = ("cron " + it["key"][4:]) if is_job else it["key"]
    head = [("  " + name, C)]
    if it["kind"] != "scaffold":
        vtx, _ = _fmt_val(it)
        head += [(" = ", DK), (vtx, WH)]
        if it["key"] == S.get("saved_key"):            # recién persistido:
            head += [("  " + _t("personalizacion.saved.mark", SAVED_MARK),
                      GREEN + BO)]                      # junto al valor, no
        if it["kind"] not in ("account", "agent"):     # estado propio: sin
            dflt = it["default"]                        # default/origen aquí
            if isinstance(dflt, bool):
                dflt = "on" if dflt else "off"
            elif dflt in ("", None):
                dflt = "(vacío)"
            head += [("  ·  default ", DK), (str(dflt), GREY)]
            head += [("  ·  origen ", DK), (it["source"],
                      C if it["source"] in ("store", "env") else GREY)]
            if it.get("range"):
                head += [("  ·  rango %s–%s" % it["range"], DK)]
    out.append(_cell(head, rw))
    # AGENTE: modelo efectivo + precedencia + cómo abrir el panel.
    if it["kind"] == "agent":
        eff, src = _agent_effective_model(it["agent"], it.get("engine", ""),
                                          it.get("override", ""))
        out.append(_cell([("  Motor %s · modelo efectivo " % _engine_label(
            it.get("engine", "")), DIM), (eff, WH), ("  (%s)" % src, DIM)], rw))
        out.append(_cell([("  Enter: panel del agente — motor (cuentas "
                           "conectadas) y modelo (ids del motor)", C)], rw))
    # CUENTA: conexión/auth/env + la acción de conectar (invariante visible).
    if it["kind"] == "account":
        stx = it.get("status") or {}
        meta = "  conexión %s · auth %s" % (stx.get("connection") or "?",
                                            stx.get("auth_type") or "?")
        if stx.get("env_vars"):
            meta += " · env %s" % "/".join(stx["env_vars"])
        if stx.get("cli"):
            meta += " · cli %s" % stx["cli"]
        out.append(_cell([(meta, DIM)], rw))
        out.append(_cell([("  Enter: abrir el asistente guiado de conexión "
                           "(pega/valida la key o instala el CLI)", C)], rw))
        for e in (stx.get("blocked") or [])[:1]:
            out.append(_cell([("  INVARIANTE: " + _fit(e, rw - 15), RED)], rw))
    # routing: cómo se edita (los ids se ciclan/escriben; lista muy larga
    # para radios — el picker de tema no aplica).
    if it["kind"] == "route":
        out.append(_cell([("  Espacio cicla ids reales de providers · Enter "
                           "escribe uno · vacío = quita la regla", DIM)], rw))
    # enum/model: TODAS las opciones estilo radio, la SELECCIONADA marcada
    # explícitamente (pedido del socio) — verde si recién guardada.
    if it["kind"] in ("enum", "model") and it.get("choices"):
        just = (it["key"] == S.get("saved_key"))
        segs = [("  ", None)]
        for k, c in enumerate(it["choices"]):
            sel = (c == it["value"])
            lbl = _enum_opt_label(it, c)
            if k:
                segs.append(("  ", None))
            segs.append((_radio(sel) + " " + lbl,
                         ((GREEN + BO) if just else (WH + BO)) if sel
                         else DIM))
        out.append(_cell(segs, rw))
    # tema/layout: PICKER — una línea por opción (nombre legible + id),
    # numerado. En pick el ▸ resalta el candidato; el radio, el PERSISTIDO.
    if it["kind"] in ("theme", "layout"):
        themes = list(it.get("themes") or ())
        picking = (S.get("mode") == "pick")
        just = (it["key"] == S.get("saved_key"))
        pidx = max(0, min(max(0, len(themes) - 1),
                          int(S.get("pick_idx", 0))))
        for k, (tid, lbl) in enumerate(themes):
            sel = (tid == it["value"])
            hot = (picking and k == pidx)
            col = ((GREEN + BO) if (sel and just) else
                   (WH + BO) if (hot or sel) else DIM)
            out.append(_cell(
                [("  " + ("▸ " if hot else "  "), C + BO),
                 ("%d " % (k + 1) if k < 9 else "  ", C if picking else DK),
                 (_radio(sel) + " ", col),
                 (lbl, col), ("  · " + tid, GREY if (hot or sel) else DK)],
                rw))
    if it.get("env_on"):
        note = ("  override por env (%s=%s) — el toggle no aplica hasta "
                "quitar la env" % (it["env"],
                                   os.environ.get(it["env"], "1")))
        if it["key"] == S.get("saved_key"):
            note += " (guardado en el store igual)"
        out.append(_cell([(note, RED)], rw))
    for seg in _wrap(it.get("help", ""), rw - 4)[:2]:
        out.append(_cell([("  " + seg, DIM)], rw))
    return out


def _right_lines(S, rw, rows):
    """Panel derecho: cabecera de la sección + sus items (label · valor ·
    origen) + pie con el detalle del item seleccionado + línea de status o
    el input inline de edición. En mode 'connect'/'agent' el PANEL toma el
    lado derecho."""
    if S.get("mode") == "connect":
        return _connect_lines(S, rw, rows)
    if S.get("mode") == "agent":
        return _agent_lines(S, rw, rows)
    cur_si = _cur_sec(S)
    flat = _flat(S)
    cur = max(0, min(len(flat) - 1, S.get("cur", 0)))
    sel_it = current_item(S)
    L = [" " * rw]
    if cur_si == EXIT:
        L.append(_cell([("  " + EXIT_LABEL, C + BO),
                        ("  — Enter sale al recinto", DIM)], rw))
        sec = None
    else:
        sec = (S.get("sections") or [])[cur_si]
        L.append(_cell([("  " + sec["title"], C + BO),
                        ("  — " + sec.get("desc", ""), DIM)], rw))
    L.append(_cell([("  " + "─" * (rw - 4), DK)], rw))
    # items de la sección actual (scroll simple: el seleccionado siempre a la vista)
    detail = _detail_lines(S, sel_it, rw)
    body = rows - 3 - len(detail) - 2                # cab(3) + detalle + sep + input
    rows_items = []
    sel_row = 0
    if sec is not None:
        for ii, it in enumerate(sec.get("items") or ()):
            on = (flat[cur] == (cur_si, ii))
            if on:
                sel_row = len(rows_items)
            vtx, vcol = _fmt_val(it)
            src = ("env" if it.get("env_on") else it.get("source", ""))
            # flash de guardado: la columna de origen pasa a "» guardado"
            # VERDE unos ticks (el env, si está, sigue ganando la columna).
            saved = (it["key"] == S.get("saved_key")
                     and not it.get("env_on"))
            stx = _t("personalizacion.saved.mark", SAVED_MARK) if saved else src
            scol = (GREEN + BO) if saved else (
                RED if src == "env" else (C if src == "store" else DK))
            srcw = max(_pw(stx) + 2, 10)
            valw = 18
            labw = max(10, rw - 4 - valw - srcw)
            rows_items.append(_cell(
                [("  ▸ " if on else "    ", C + BO),
                 (_fit(it["label"], labw - 1),
                  (WH + BO) if on else B2)], 4 + labw)
                + _cell([(vtx, (vcol + BO) if on else vcol)], valw)
                + _cell([(stx + " ", scol)], srcw, align="right"))
    start = 0
    if body > 0 and sel_row >= body:
        start = sel_row - body + 1
    for ln in rows_items[start:start + max(0, body)]:
        L.append(ln)
    while len(L) < rows - len(detail) - 2:
        L.append(" " * rw)
    L = L[:rows - len(detail) - 2]
    L.append(_cell([("  " + "─" * (rw - 4), DK)], rw))
    L.extend(detail)
    # última fila: input de edición o status/hint
    if S.get("mode") == "edit":
        hint = ""
        if sel_it is not None:
            if sel_it.get("range"):
                hint = "  (rango %s–%s · vacío = default)" % sel_it["range"]
            elif sel_it["kind"] in ("model", "engine"):
                hint = "  (%s o un id libre · vacío = default)" % \
                       "/".join(MODEL_CHOICES)
            elif sel_it["kind"] == "route":
                hint = "  (id de provider o libre · vacío = quita la regla)"
            else:
                hint = "  (vacío = default)"
        L.append(_cell([("  nuevo valor ›  ", B2), (S.get("buf", ""), WH),
                        ("▌", C), (hint, GREY)], rw))
    elif S.get("mode") == "pick":
        what = (_t("personalizacion.pick.what_layout", "layout")
                if (sel_it or {}).get("kind") == "layout"
                else _t("personalizacion.pick.what_theme", "tema"))
        L.append(_cell([(_t("personalizacion.pick.prompt",
                            "  elegir {what} ›  ", what=what), B2),
                        (_t("personalizacion.pick.hint",
                            "↑↓ o 1-9 eligen · Enter aplica y guarda · "
                            "Esc cancela"), GREY)], rw))
    elif S.get("status"):
        # la marca de guardado abre con «guardado» (es) o «saved» (en)
        ok = str(S["status"]).startswith(("guardado", "saved"))
        L.append(_cell([("  " + S["status"], GREEN if ok else B)], rw))
    else:
        L.append(_cell([("  Enter edita · Espacio toggle / cicla opciones",
                         GREY)], rw))
    return L[:rows] if len(L) >= rows else L + [" " * rw] * (rows - len(L))


def _connect_lines(S, rw, rows):
    """El ASISTENTE de conexión ocupa el panel derecho: título + contenido del
    paso (qué es / dónde sacar la key / pegar oculto / validando / resultado /
    CLI) + una fila de acciones. Exactamente `rows` líneas, marco recto."""
    c = S.get("connect") or {}
    stx = c.get("status") or {}
    step = c.get("step", "intro")
    disp = stx.get("display") or c.get("provider", "?")
    L = [" " * rw]
    L.append(_cell([("  CONECTAR · ", C + BO), (disp, WH + BO),
                    ("   " + (stx.get("cost_label") or ""), DIM)], rw))
    L.append(_cell([("  " + "─" * (rw - 4), DK)], rw))

    def body(txt, col=WH):
        for seg in _wrap(txt, rw - 4):
            L.append(_cell([("  " + seg, col)], rw))

    def gap():
        L.append(" " * rw)

    actions = "Esc cierra"
    if step == "intro":
        connected = (stx.get("state") == "connected")
        body("Qué es: %s. %s." % (disp, stx.get("cost_label") or "cuenta"))
        url = stx.get("credential_url")
        if url:
            body("De dónde sacar la key:", DIM)
            body(url, C)
        if stx.get("env_vars"):
            body("Se guarda como %s (guardo el NOMBRE, jamás el valor; "
                 "per-máquina, 0600)." % "/".join(stx["env_vars"]), DIM)
        gap()
        body("Estado: " + (stx.get("detail") or ""),
             GREEN if connected else B2)
        actions = ("Enter revalidar · r reemplazar key · d desconectar · "
                   "Esc cerrar") if connected else \
                  "Enter pegar la API key · Esc cerrar"
    elif step == "paste":
        body("Pega tu API key para %s:" % disp)
        masked = "•" * _pw(c.get("buf", ""))
        L.append(_cell([("     ", None), (masked, WH), ("▌", C)], rw))
        gap()
        body("La key vive per-máquina (0600) — nunca al repo ni a settings. "
             "Se valida con un ping real (no gasta tokens).", DIM)
        url = stx.get("credential_url")
        if url:
            body("De dónde: %s" % url, DIM)
        actions = "Enter valida y guarda · Esc regresa"
    elif step == "validating":
        body("Validando la conexión con %s…" % disp, C)
        body("probando una llamada ligera (listado de modelos, sin gastar "
             "tokens) — timeout corto.", DIM)
        actions = "Esc cierra (la validación sigue en segundo plano)"
    elif step == "result":
        res = c.get("result") or {}
        kind = res.get("kind")
        okc = GREEN if res.get("ok") else (RED if kind == "auth" else B)
        mark = "●" if res.get("ok") else ("○" if kind == "auth" else "◐")
        body("%s %s" % (mark, res.get("detail") or ""), okc)
        gap()
        if res.get("ok") and kind == "ok":
            body("La cuenta quedó CONECTADA y verificada.", GREEN)
        elif kind == "auth":
            body("La credencial fue rechazada — NO se guardó. Revisa la key "
                 "y reintenta.", RED)
        else:
            body("La key se guardó per-máquina, pero no pude verificarla "
                 "(sin endpoint de verificación o sin red). Debería servir.",
                 B2)
        actions = ("Enter reintentar · Esc cerrar" if kind == "auth"
                   else "Enter listo")
    elif step in ("cli", "cli_confirm"):
        body("Cuenta: %s" % (_official_account(stx) or disp))
        body("Se conecta con el CLI oficial — WORKSPACE nunca ve ni toca tu "
             "token; el CLI gestiona su propia sesión.", DIM)
        present = stx.get("cli_present")
        body("Estado: CLI %s %s" % (stx.get("cli") or "?",
                                    "instalado" if present else "NO instalado"),
             GREEN if present else B)
        if step == "cli":
            if not present and stx.get("install_cmd"):
                body("Instalar:  %s" % " ".join(stx["install_cmd"]), C)
            if stx.get("login_cmd"):
                body("Login:     %s" % " ".join(stx["login_cmd"]), C)
            if present:
                actions = "l iniciar sesión · Esc cerrar"
            elif stx.get("install_cmd"):
                actions = "i instalar el CLI (pide confirmar) · l login · Esc"
            else:
                actions = "l iniciar sesión · Esc cerrar"
        else:                                        # cli_confirm
            gap()
            body("¿Instalar el CLI de %s?" % c.get("provider"), WH + BO)
            body("Voy a correr:  %s" % " ".join(stx.get("install_cmd") or []),
                 C)
            body("(se ejecuta en tu terminal, requiere npm — con tu "
                 "confirmación explícita)", DIM)
            actions = "Enter sí, instalar · Esc no"

    # pad + fila de acciones al fondo (dentro del marco)
    while len(L) < rows - 1:
        L.append(" " * rw)
    L = L[:rows - 1]
    L.append(_cell([("  " + actions, C + BO)], rw))
    return L[:rows]


def _official_account(stx):
    """Etiqueta de cuenta del CLI oficial (p. ej. 'suscripción ChatGPT') desde
    connectors.OFFICIAL_CLIS. Falla-suave → ''."""
    try:
        info = _connectors.OFFICIAL_CLIS.get(stx.get("cli")) or {}
        return info.get("account", "")
    except Exception:
        return ""


def _agent_lines(S, rw, rows):
    """PANEL por agente: motor↔modelo COHERENTES, con modelo efectivo +
    precedencia + N3 limpio (una vez). overview o picker (motor/modelo).
    Exactamente `rows` líneas, marco recto."""
    a = S.get("agent") or {}
    name = a.get("name", "?")
    disp = a.get("display") or name.capitalize()
    engine = a.get("engine", "")
    tier = a.get("tier", "")
    step = a.get("step", "overview")
    override = _sget("agentes.%s.model" % name, "")
    L = [" " * rw]
    L.append(_cell([("  AGENTE · ", C + BO), (disp, WH + BO),
                    ("   motor %s" % _engine_label(engine), DIM)], rw))
    L.append(_cell([("  " + "─" * (rw - 4), DK)], rw))

    def body(txt, col=WH):
        for seg in _wrap(txt, rw - 4):
            L.append(_cell([("  " + seg, col)], rw))

    if step in ("motor", "modelo"):
        opts = list(a.get("opts") or [])
        pidx = max(0, min(max(0, len(opts) - 1), int(a.get("pick_idx", 0))))
        if step == "motor":
            body("Elige motor / cuenta para %s "
                 "(de tus cuentas conectadas):" % disp, C)
        else:
            body("Elige modelo para %s (ids del motor):" % disp, C)
        for k, o in enumerate(opts):
            hot = (k == pidx)
            if step == "motor":                      # o = dict de _motor_options
                rd = o.get("ready")
                lbl = o.get("display", "?") + (
                    "  · listo" if rd else "  · motor en construcción")
                col = (WH + BO) if hot else (DIM if rd else B)
            else:                                    # o = id de modelo (str)
                lbl = o if o != "" else "(por defecto — el del motor)"
                col = (WH + BO) if hot else DIM
            L.append(_cell([("  " + ("▸ " if hot else "  "), C + BO),
                            ("%d " % (k + 1) if k < 9 else "  ",
                             C if hot else DK), (_radio(hot) + " ", col),
                            (lbl, col)], rw))
        if step == "motor":
            body("Las 'en construcción' se ven pero aún no ejecutan agentes "
                 "(adaptadores multiengine en curso).", DIM)
        actions = "↑↓ elegir · 1-9 directo · Enter aplica · Esc regresa"
    else:                                            # overview — FILAS navegables
        eff, src = _agent_effective_model(name, engine, override)
        ridx = max(0, min(len(_AGENT_ROWS) - 1, int(a.get("row_idx", 0))))
        rowvals = {
            "motor": ("Motor / cuenta", _engine_label(engine)),
            "modelo": ("Modelo override", override or "(sin override)"),
            "clear": ("Quitar overrides (volver al default)", ""),
        }
        for k, rid in enumerate(_AGENT_ROWS):
            hot = (k == ridx)
            lbl, val = rowvals[rid]
            segs = [("  " + ("▸ " if hot else "  "), C + BO),
                    (lbl, (WH + BO) if hot else B2)]
            if val:
                segs += [(":  ", DK), (val, (WH + BO) if hot else WH)]
            L.append(_cell(segs, rw))
        L.append(" " * rw)
        L.append(_cell([("  Modelo efectivo:  ", DIM), (eff, WH),
                        ("  (%s)" % src, DIM)], rw))
        body("Precedencia modelo: override por agente › routing por tarea › "
             "default. Motor: --engine › override per-máquina › agent.json.",
             DIM)
        if tier == "C":                              # N3 limpio, UNA vez
            body("El motor y el modelo se aplican PER-MÁQUINA (no tocan el "
                 "agent.json de equipo). Cambiar el default COMMITTEADO de %s "
                 "sí es N3 (consenso) — aparte." % disp, B2)
        actions = "↑↓ elegir · Enter abrir · Esc cerrar"

    while len(L) < rows - 1:
        L.append(" " * rw)
    L = L[:rows - 1]
    L.append(_cell([("  " + actions, C + BO)], rw))
    return L[:rows]


def _help_rows(S, w):
    """Barra de ayuda PROMINENTE: 2 filas dentro del marco, teclas en acento
    dorado (C) con peso — contextual por modo (como el chat)."""
    mode = S.get("mode")
    rows = HELP.get(mode if mode in ("edit", "pick", "connect", "agent")
                    else "nav", HELP["nav"])
    out = []
    for pairs in rows:
        segs = [("  ", None)]
        for k, (key, label) in enumerate(pairs):
            if k:
                segs.append(("  ·  ", DK))
            segs.append((key, C + BO))
            segs.append((" " + label, B2))
        out.append(_cell(segs, w))
    while len(out) < 2:
        out.append(" " * w)
    return out[:2]


import responsive_ui as _responsive
handle_key = _responsive.action(handle_key, exit_result=None)

def render_lines(S, w, h):
    """Frame completo → lista de h-1 líneas ANSI: marco dorado + 2 paneles
    + barra de ayuda de 2 filas DENTRO del marco. Anchos EXACTOS por celda
    — el marco queda recto en cualquier terminal que mida como cw()."""
    real_w, real_h = max(1, int(w or 1)), max(1, int(h or 1))
    S['_viewport_active'] = False
    S['_size_blocked'] = not _responsive.supported(real_w, real_h)
    if S['_size_blocked']:
        return _responsive.size_notice('CONFIGURACIÓN', real_w, real_h)
    if _responsive.vertical(real_w, real_h):
        pw = real_w - 3
        sections = S.get('sections') or []
        selected = _cur_sec(S)
        labels = [('> ' if i == selected else '  ') + sec['title'].capitalize()
                  for i, sec in enumerate(sections)]
        labels += [('> ' if selected == EXIT else '  ') + EXIT_LABEL]
        upper = _responsive.box('CONFIGURACIÓN · SECCIONES', labels, pw, True)
        cap = max(5, real_h - len(upper) - 7)
        lower = _right_lines(S, pw - 4, cap)
        lines = [' ' + x for x in upper] + [''] + [' ' + x for x in _responsive.box('OPCIONES Y DETALLE', lower, pw)]
        lines += [''] + [HL for HL in _help_rows(S, real_w - 2)]
        return lines[:real_h - 1] + [''] * max(0, real_h - 1 - len(lines))
    S.pop('_viewport_offset', None)
    w = max(MIN_W, int(w or MIN_W))
    h = max(MIN_H, int(h or MIN_H))
    lw = _lw(w)
    rw = w - lw - 3                                  # ║ + lw + ┃ + rw + ║
    rows = h - 6                                     # top+hsep+2 ayuda+bottom
    title = "═ CONFIG "
    # Atajos CLAVE en el borde superior, junto al nombre de la pantalla
    # (pedido del socio 2026-10-04): la primera fila del HELP del modo
    # actual, tecla en acento+bold y acción en B2, cediendo pares del final
    # si no caben. La barra COMPLETA de 2 filas sigue abajo, en el marco.
    mode = S.get("mode")
    pairs = list(HELP.get(mode if mode in ("edit", "pick", "connect",
                                           "agent") else "nav",
                          HELP["nav"])[0])
    inner = w - 2
    hint, hint_w = "", 0
    while pairs:
        plain = " " + " · ".join("%s %s" % kv for kv in pairs) + " "
        if _pw(plain) <= inner - len(title) - 8:
            segs = []
            for k, (key, label) in enumerate(pairs):
                if k:
                    segs.append(DK + " · " + R)
                segs.append(C + BO + key + R + " " + B2 + label + R)
            hint, hint_w = " " + "".join(segs) + " ", _pw(plain)
            break
        pairs.pop()
    if hint:
        top = (B + "╔" + title + "═" * 4 + R + hint + B
               + "═" * max(0, inner - len(title) - 4 - hint_w) + "╗" + R)
    else:
        top = (B + "╔" + title + "═" * max(0, inner - len(title)) + "╗" + R)
    left = _left_lines(S, rows, lw)
    right = _right_lines(S, rw, rows)
    lines = [top]
    for i in range(rows):
        lines.append(B + "║" + R + left[i] + B2 + "┃" + R + right[i]
                     + B + "║" + R)
    lines.append(B + "╟" + "─" * lw + "┸" + "─" * rw + "╢" + R)
    for hr in _help_rows(S, w - 2):
        lines.append(B + "║" + R + hr + B + "║" + R)
    lines.append(B + "╚" + "═" * (w - 2) + "╝" + R)
    return lines


def render_text(S, w=100, h=28):
    """Render plano de una pasada (smoke tests / capturas)."""
    return "\n".join(render_lines(S, w, h))


# ═══════════════════════════════════════════════════════════════════════════
# Drivers de teclado (Unix: termios+select · Windows: msvcrt+sleep) — el
# MISMO patrón endurecido de chat_tui: leer CRUDO, peek doble ante un \x1b
# aparentemente solo (una flecha fragmentada JAMÁS sale), secuencias raras
# se ignoran. En Windows las flechas llegan con prefijo \x00/\xe0.
# ═══════════════════════════════════════════════════════════════════════════

def _draw(tout, S, first=False):
    """Fórmula de pantalla de front.py: 2J3JH al entrar, H + K-por-línea
    después (NUNCA 2J a media sesión). Sin newline final → no scroll."""
    try:
        try:
            ts = os.get_terminal_size(tout.fileno())
            w, hh = ts.columns, ts.lines
        except Exception:
            w, hh = 100, 30
        out = "\033[2J\033[3J\033[H" if first else "\033[H"
        out += "\r\n".join("\r\033[K" + ln for ln in render_lines(S, w, hh))
        tout.write(out + "\033[J")
        tout.flush()
    except Exception:
        pass


def _reenter_connect_after_shell(S, req):
    """Tras correr un comando del asistente (instalar/login), re-chequea el
    provider y vuelve al paso 'cli' con el estado FRESCO (el status cambia
    solo). Falla-suave."""
    prov = req.get("provider", "")
    refresh(S)
    if not prov:
        _close_connect(S)
        return
    stx = _cstatus(prov)
    S["mode"] = "connect"
    S["connect"] = {"provider": prov, "status": stx,
                    "step": "cli" if stx.get("connection") == "official_cli"
                    else "intro", "buf": "", "result": None, "confirm": ""}
    S["status"] = "listo — re-chequeado"


def _shell_run_and_reenter(S, req, tout):
    """Corre el comando externo (instalar CLI / login) con la terminal NORMAL
    (el driver ya suspendió el modo raw) y luego re-chequea. El comando lo
    ELIGIÓ el socio (confirmación explícita); WORKSPACE solo lo lanza — jamás
    lee ni extrae el token de la suscripción."""
    import subprocess
    cmd = req.get("cmd") or []
    try:
        tout.write("\033[2J\033[3J\033[H")
        tout.flush()
    except Exception:
        pass
    try:
        print("\n\033[1m» %s\033[0m" % req.get("label", ""))
        print("  $ %s\n" % " ".join(cmd))
        subprocess.run(cmd)
    except FileNotFoundError as e:
        print("\n  no pude ejecutar (%s). ¿Falta npm / el runtime?" % e)
    except KeyboardInterrupt:
        pass
    except Exception as e:                            # pragma: no cover
        print("\n  error: %s" % e)
    try:
        input("\n  [Enter para volver a WORKSPACE] ")
    except (EOFError, KeyboardInterrupt):
        pass
    _reenter_connect_after_shell(S, req)


def _run_unix():
    import select
    import termios
    import tty
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        tout = open("/dev/tty", "w")
    except Exception:
        print("config: necesito una terminal interactiva (sin /dev/tty)")
        return
    S = new_state()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        _draw(tout, S, first=True)
        while True:
            r, _, _ = select.select([fd], [], [], 0.5)
            if not r:                                # tick: releer settings
                refresh(S)
                _draw(tout, S)
                continue
            try:
                data = os.read(fd, 64)
            except OSError:
                data = b""
            if not data:
                continue
            if data[:1] == b"\x1b":                  # ¿secuencia de escape?
                seq = data
                tries = 0                            # peek DOBLE: una flecha
                while seq == b"\x1b" and tries < 2:  # fragmentada jamás sale
                    tries += 1
                    r2, _, _ = select.select([fd], [], [], 0.05)
                    if not r2:
                        break
                    try:
                        seq += os.read(fd, 8)
                    except OSError:
                        break
                if seq[:2] in (b"\x1b[", b"\x1bO"):  # CSI o SS3 (flechas)
                    a = seq[2:3]
                    if a == b"A":
                        handle_arrow(S, "up")
                    elif a == b"B":
                        handle_arrow(S, "down")
                    elif a == b"D":
                        handle_arrow(S, "left")
                    elif a == b"C":
                        handle_arrow(S, "right")
                    # PgUp/otras: se ignoran — JAMÁS caen a Esc/salir
                elif seq == b"\x1b":                 # Esc REAL y pelado
                    if handle_key(S, "\x1b") == "exit":
                        return
                # otra secuencia rara (Alt-tecla, etc.) → ignorar
            else:
                for c in data.decode("utf-8", "ignore"):
                    if handle_key(S, c) == "exit":
                        return
            if S.get("shell_request"):                # instalar CLI / login:
                req = S.pop("shell_request")          # suspender raw, correr,
                try:                                  # restaurar raw, re-chequear
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
                except Exception:
                    pass
                _shell_run_and_reenter(S, req, tout)
                try:
                    tty.setraw(fd)
                except Exception:
                    pass
                _draw(tout, S, first=True)
                continue
            _draw(tout, S)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        tout.write(R)
        tout.flush()
        try:
            os.close(fd)
        except OSError:
            pass


def _run_windows(max_ticks=None):
    import msvcrt
    import time
    if not sys.stdin.isatty():
        return                                       # pipe/automation: no girar
    tout = sys.stdout
    S = new_state()
    _draw(tout, S, first=True)
    ticks = 0
    try:
        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):           # prefijo de tecla extendida
                    a = msvcrt.getwch()
                    if a == "H":
                        handle_arrow(S, "up")
                    elif a == "P":
                        handle_arrow(S, "down")
                    elif a == "K":
                        handle_arrow(S, "left")
                    elif a == "M":
                        handle_arrow(S, "right")
                    # Av/Re/F-keys: se consumen y se ignoran
                elif handle_key(S, ch) == "exit":
                    return
                if S.get("shell_request"):            # instalar CLI / login
                    req = S.pop("shell_request")
                    _shell_run_and_reenter(S, req, tout)
                    _draw(tout, S, first=True)
                    continue
                _draw(tout, S)
            else:
                time.sleep(0.05)
                ticks += 1
                if ticks % 10 == 0:                  # ~0.5s: releer settings
                    refresh(S)
                    _draw(tout, S)
                if max_ticks is not None and ticks >= max_ticks:
                    return
    finally:
        tout.write(R)
        tout.flush()


def run():
    """Punto de entrada desde front.py (entrada CONFIG del menú). Falla-suave
    ABSOLUTA: cualquier problema → mensaje amable, jamás rompe el menú."""
    if settings is None:
        print("config: settings.py no está junto a config_tui.py — "
              "corre `workspace doctor`")
        return
    try:
        if sys.platform == "win32":
            _run_windows()
        else:
            _run_unix()
    except Exception as e:
        try:
            sys.stdout.write(R)
            print("config: la pantalla falló (%s: %s) — el menú sigue normal"
                  % (type(e).__name__, e))
        except Exception:
            pass


if __name__ == "__main__":
    run()
