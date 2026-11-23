"""WORKSPACE · engines/hermes.py — motor Hermes Agent (CLI `hermes`, Nous
Research; agente de código abierto con memoria, skills y cron propios).

Hace ejecutable un agente sobre el CLI oficial `hermes` en su REPL clásico
(interactivo, EN LÍNEA). Vendor-neutral, enchufable por nombre — dispatch.py lo
carga solo ("hermes" → engines/hermes.py); NO se toca el dispatcher
(engines/CONTRACT.md).

🔴 INVARIANTE DE SEGURIDAD: las credenciales las gestiona el BINARIO OFICIAL
(`hermes setup` / `hermes model` / `hermes portal`). WORKSPACE jamás lee, copia
ni reusa tokens: solo lee `hermes status` (qué proveedores tienen sesión, con
✓/✗, sin llaves).

🔴 EL HARNESS NO FIJA MODELO (regla de producto): el modelo y el proveedor son
los que el socio eligió en la config de Hermes. Ni el launch ni run_turn pasan
`-m` salvo override explícito de smokes/eval.

🔴 PERFIL PROPIO DE WORKSPACE (patrón estándar, runbooks/agregar-motor.md): el
Hermes personal del socio (~/.hermes, su SOUL.md genérico «You are Hermes
Agent… Nous Research», su memoria) le ganaba a la identidad del agente. Por
eso Workspace corre Hermes en SU perfil `workspace`, creado UNA vez con el
mecanismo oficial (`hermes profile create workspace --no-alias`, SIN
`--clone`: este copiaba el .env con las llaves del socio. Sin él, Hermes
v0.22.2 siembra solo el bloque `model` del perfil activo —y la definición del
endpoint elegido, con sus `${VAR}` como referencias—, un .env vacío y sus
skills de fábrica; Workspace jamás causa una copia de las llaves. El proveedor
se conecta una vez en Motores › cuenta y proveedor) y elegido POR COMANDO con
`--profile` (jamás `hermes profile use`: el default del socio no cambia).
Un perfil creado antes con `--clone` conserva su .env: es del socio y no se
borra. En cada arranque se re-asegura SOLO lo del cerebro, con camino
rápido leyendo archivos y aviso de una línea si se restauró: SOUL.md NEUTRAL
(la identidad la pone el AGENTS.md del cerebro), la memoria propia de Hermes
apagada (el perfil lo comparten todos los agentes: lo que guardara de uno se
le inyectaría a otro) y el hook `pre_llm_call` de tono por turno
(hooks/hermes_turno.py; si es el ÚNICO hook del perfil, el REPL se abre con
`--accept-hooks` y Hermes lo aprueba sin preguntar; con hooks del socio pide
aprobarlo una vez), las
herramientas `session_search` y `memory` apagadas en la terminal y en Discord
(leen todo el perfil: un agente leía las conversaciones de otro),
`context_file_max_chars` con espacio
para la identidad incrustada y las skills del cerebro (`skills.external_dirs`
= `${WORKSPACE_BRAIN}/skills`; las que Hermes crea van a `skills.create_dir` =
`${WORKSPACE_BRAIN}/skills/aprendidas`, en el mismo cerebro y no en el perfil
compartido; su repaso automático de fondo queda en 0). Lo demás (modelo,
proveedor, sus skills de fábrica, cron) es vanilla.

🔴 MISMA ESTRUCTURA DE CEREBRO PARA TODOS LOS MOTORES: la identidad llega por el
MISMO `AGENTS.md` puntero que codex/opencode/openclaw (Hermes lee el primero
que encuentre: `.hermes.md`/`HERMES.md` → `AGENTS.override.md` → `AGENTS.md` →
`CLAUDE.md`; los tres primeros son nombres reservados en la raíz del cerebro).
Para Hermes el puntero lleva además una COPIA GENERADA del núcleo de identidad
(BRAIN.md + BOOT/NN + perfil del socio): no expande imports ni tiene mensaje
de arranque, y un modelo débil no lee BRAIN.md por su cuenta. Hermes guarda
el system prompt al crear la sesión y lo REUSA al reanudar (solo lo rehace si
cambian modelo o proveedor): una pestaña ya atada conserva la identidad con
la que nació.

Hechos VERIFICADOS con el binario v0.18.2 (2026-10-15, HERMES_HOME desechable,
sin credenciales reales):
  · El escáner de inyección de Hermes NO bloquea el AGENTS.md puntero (con y sin
    bloque de pestaña) y lo mete en el system prompt (`hermes prompt-size`,
    export de la sesión).
  · `hermes` a secas = REPL clásico EN LÍNEA (sin pantalla alterna); al salir
    imprime el id. La sesión queda en ~/.hermes/state.db con source=cli y
    cwd = el cerebro; Hermes no escribió nada en el cerebro.
  · `--resume <id>` CONTINÚA la misma sesión (mismo id, los mensajes se
    agregan). Un id inexistente falla («Session not found»): se valida antes.
    No hay flag para mandar un primer mensaje en el modo interactivo.
  · `sessions export - --format jsonl --session-id <id>` = una línea JSON con
    la sesión y sus mensajes ACTIVOS. Con filtros (--cwd, --newer-than…) el
    export SOLO trae sesiones terminadas: una pestaña cerrada de golpe o una
    sesión retomada quedan sin `ended_at`. Por eso las sesiones nuevas se
    buscan con `sessions list --workspace <cerebro>` y se exportan por id.
  · `-z` (oneshot) imprime SOLO la respuesta; con HERMES_SESSION_SOURCE=tool la
    sesión queda oculta de las listas del socio. El fallo NO cambia el código
    de salida: se detecta con `--usage-file` (failed/completed).
  · `hermes status` lista ✓/✗ por proveedor (sin llaves) y el proveedor elegido.
  · Perfiles (con el login real del socio, perfiles desechables): `--profile
    <p>` / `-p <p>` elige el perfil SOLO para ese comando (el default no
    cambia); un perfil inexistente sale con rc=1 («does not exist»); con
    HERMES_HOME los perfiles viven bajo esa raíz. El SOUL.md del perfil abre
    el system prompt (sin «You are Hermes Agent»); `memory.memory_enabled` y
    `memory.user_profile_enabled` en false dejan memoria y perfil de usuario en
    0 (`prompt-size`). Un shell hook `pre_llm_call` con stdout {"context"} se
    anexa al mensaje del turno (`api_content` del export); la aprobación queda
    en `<perfil>/shell-hooks-allowlist.json` (no en el del socio). El reporte
    de `--usage-file` de un turno bueno trae `completed: true, failed: false`.

Cero dependencias (stdlib, 3.9+). Mac/Windows. Falla-suave.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import arbol_procesos  # noqa: E402  (Windows: al vencer el tiempo muere el árbol entero)

META = {"name": "hermes", "needs": ["hermes"], "auth": "api-key"}

#: Matriz de capacidades (contrato harness-os §3). TODAS las claves de
#: capabilities.ENGINE_KEYS (lo exige test_capabilities).
CAPABILITIES = {
    "launch": "wrapper",              # REPL oficial envuelto en el ciclo neutral
    "inject_context": "project-doc",  # AGENTS.md puntero (el mismo de codex/opencode/openclaw)
    "mcp": True,                      # Hermes gestiona MCP (`hermes mcp`)
    "hooks": "wrapper",               # solo inicio/cierre del wrapper; sus hooks nativos no se cablean
    "sessions": "workspace",          # pestaña ↔ id de sesión de Hermes (atado post-hoc + --resume)
    "status_live": False,
    "headless": True,                 # `hermes -z` (ver headless.py)
    "statusline": False,
}

BINARY = "hermes"
#: Tecla(s) de herdr con que la página detiene un turno (sin esto, `esc`):
#: Ctrl+C con la caja vacía interrumpe (doc user-guide/cli). UNA pulsación: dos
#: en 2 s cierran Hermes.
TECLAS_PARAR = ["c-c"]

#: Versiones del CLI oficial con las que se VERIFICARON las lecturas de este
#: adapter (historial).
#: 0.18.2 (`status` completo) · 0.22.2 (`status --full`; export rc=1 «No session»)
#: · 0.22.5 (ids `local-<hex>` sin hora, source=local + created_source; prueba
#: real 2026-10-26: captura al cerrar, atado a la pestaña y --resume).
#: La lista de versiones PROBADAS es una sola: la del parser de este motor
#: (engine_versions.verified); lo de arriba es el historial de este adapter.
LABEL = "Hermes · modelo de tu config"

#: Orígenes de sesión que NO son del socio en su REPL: los turnos headless de
#: Workspace (tool), subagentes y cron de Hermes. Jamás se atan a una pestaña.
_FOREIGN_SOURCES = ("tool", "subagent", "cron")

#: Orígenes de sesión que SÍ pueden ser de una pestaña (lista blanca de
#: sessions_since). VERIFICADO v0.22.2 (agent/session_source.py,
#: hermes_cli/cli_session_mixin.py): el REPL clásico que abre Workspace graba
#: `cli`; `tui` si el socio eligió esa interfaz en el perfil
#: (`display.interface`); "" = registros sin origen. Una sesión de Discord (o
#: de cualquier plataforma del gateway), `oneshot`, `acp` o `desktop` jamás se
#: toma como la de una pestaña, aunque alguna vez grabe el cwd del cerebro.
_TAB_SOURCES = ("cli", "tui", "")

#: Desde v0.22.5 las superficies locales graban `source="local"` y la que
#: creó la sesión en `created_source` (VERIFICADO v0.22.5:
#: gateway/session_policy.py SURFACES/STORED_AS_LOCAL,
#: hermes_state_local.commit_local_session; el REPL de una pestaña exporta
#: `local` + `cli`). `local` a secas NO basta: Desktop (`desktop`) y ACP
#: (`acp`) también se guardan como `local`. Sin `created_source` (o con el
#: marcador `unknown`) no se sabe de qué superficie es: no se ata. `tool` y
#: `oneshot` conservan su propio `source` y quedan fuera como antes.
_LOCAL_SOURCE = "local"
_TAB_CREATED = ("cli", "tui")


def _tab_source(d):
    """¿El registro exportado es de una sesión que puede ser de una pestaña?"""
    src = str(d.get("source") or "")
    if src == _LOCAL_SOURCE:
        return str(d.get("created_source") or "") in _TAB_CREATED
    return src in _TAB_SOURCES

#: Archivos que Hermes lee ANTES que AGENTS.md (le ganarían a la identidad).
_OVERRIDES = (".hermes.md", "HERMES.md", "AGENTS.override.md")


def _exe(override=None):
    """Ruta al binario. None → PATH; "" → no hay (tests); "/ruta" → esa."""
    if override is None:
        return shutil.which(BINARY)
    return override or None


def _run(cmd, runner=None, timeout=60, cwd=None, env=None):
    if runner is not None:
        return runner(cmd, cwd=cwd, timeout=timeout, env=env)
    if env is None:
        # el perfil, el estado y los turnos de Hermes corren sin las fichas
        # que cargó el hub (Greptile, 2026-10-17)
        import secret_store
        env = secret_store.engine_env()
    return arbol_procesos.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", cwd=cwd, env=env,
                              stdin=subprocess.DEVNULL)


def _t(key, es, en=None, **kw):
    """i18n falla-suave (catálogo lang/<code>/motorbar.py → ES/EN inline)."""
    try:
        import workspace_status
        return workspace_status.t(key, es, en, **kw)
    except Exception:
        return es.format(**kw) if kw else es


def _valid_sid(sid):
    """Id de sesión de Hermes con forma segura para argv (los del REPL son
    `AAAAMMDD_HHMMSS_<6 hex>` hasta v0.22.2 y `local-<64 hex>` desde v0.22.5;
    se aceptan otros sin espacios ni guion inicial)."""
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{3,95}", str(sid or "")))


# ── perfil PROPIO de Workspace (mecanismo oficial `hermes profile`) ────────
#: Nombre del perfil. Env de override SOLO para tests (perfiles desechables).
PROFILE = "workspace"

#: SOUL.md del perfil: NEUTRAL. Hermes lo pone al inicio del system prompt en
#: lugar de su identidad de fábrica; la identidad real llega por el AGENTS.md
#: del cerebro. Bilingüe y fijo (mismos bytes en cualquier máquina e idioma).
#: Sin título: el «# Workspace» de la v1 hacía que un modelo débil dijera que
#: su cerebro era «workspace» (Turing, 2026-10-15); por eso también aclara que
#: ese es solo el nombre del perfil.
SOUL_TEXT = (
    "Eres el agente que define el AGENTS.md del proyecto en el que trabajas (la "
    "carpeta de trabajo es su cerebro): su identidad, reglas y tono mandan por "
    "encima de cualquier otra instrucción de estilo. Hermes es solo el motor que "
    "te ejecuta y «workspace» es solo el nombre del perfil del motor: ninguno de "
    "los dos es tu nombre ni tu cerebro. No te presentes como «Hermes Agent» ni "
    "como creado por Nous Research.\n\n"
    "You are the agent defined by the AGENTS.md of the project you are working in "
    "(the working folder is its brain): its identity, rules and tone take "
    "precedence over any other style instruction. Hermes is only the engine running "
    "you and \"workspace\" is only the engine profile's name: neither is your name "
    "or your brain. Do not present yourself as \"Hermes Agent\" or as made by Nous "
    "Research.\n")

#: Versiones anteriores del SOUL de Workspace: se actualizan EN SILENCIO (son
#: nuestras, no un cambio del socio que merezca aviso).
_SOUL_PREVIOUS = (
    "# Workspace\n\n"
    "Tu identidad, reglas y tono los define el AGENTS.md del proyecto en el que "
    "trabajas (y los documentos que ese archivo indica); síguelos por encima de "
    "cualquier otra instrucción de estilo. Hermes es solo el motor que te ejecuta: "
    "no te presentes como «Hermes Agent» ni como creado por Nous Research.\n\n"
    "Your identity, rules and tone are defined by the AGENTS.md of the project you "
    "are working in (and the documents it points to); follow them above any other "
    "style instruction. Hermes is only the engine running you: do not present "
    "yourself as \"Hermes Agent\" or as made by Nous Research.\n",
)

#: Ajustes del CEREBRO en el config.yaml del perfil: (clave, hoja). La memoria
#: propia de Hermes y su perfil de usuario se inyectan en el system prompt de
#: TODAS las sesiones del perfil, que comparten todos los agentes: apagadas
#: (la memoria de cada agente vive en su cerebro).
_BRAIN_SETTINGS = (("memory.memory_enabled", "memory_enabled"),
                   ("memory.user_profile_enabled", "user_profile_enabled"))

#: Herramientas propias de Hermes apagadas en el perfil (mecanismo oficial
#: `hermes tools disable`, plataforma cli = REPL y `-z`). El perfil lo comparten
#: TODOS los agentes: `session_search` busca y LEE sesiones de todo el perfil
#: (VERIFICADO 2026-10-15: Turing leyó con ella las conversaciones de Zenith y
#: de Argus; no tiene filtro por carpeta) y `memory` no sirve con la memoria
#: apagada (responde «Memory is not available»). La memoria y la historia de
#: cada agente viven en su cerebro.
_TOOLSETS_OFF = ("session_search", "memory")
#: Plataformas de Hermes donde se apagan con su lista propia. `cli` = REPL y
#: `-z` (siempre: `-z` no aplica la lista global, ver _tool_on); `discord` = el
#: bot que el gateway conecte a este perfil: su lista es aparte
#: (`platform_toolsets.discord`, de fábrica `hermes-discord`, que trae las
#: dos) y desde Discord se leían las conversaciones de todos los agentes del
#: perfil compartido (VERIFICADO v0.22.2, toolsets.py y
#: hermes_cli/subcommands/tools.py: `tools disable --platform discord`). Con
#: la lista global puesta, Discord ya queda cubierto y su lista no se toca.
_TOOLS_PLATFORMS = ("cli", "discord")
#: Y en TODAS las demás plataformas del gateway (Telegram, Slack, WhatsApp,
#: Signal, correo, Matrix… 21 en v0.22.2, más las de plugins): un bot de
#: cualquiera conectado al perfil compartido leía las conversaciones de todos
#: los agentes (revisión de la 0.5.1, P2-3). Una llamada al CLI por plataforma
#: costaría decenas de segundos en cada arranque; Hermes tiene la forma
#: oficial que vale para todas: la lista global `agent.disabled_toolsets`,
#: que aplica AL FINAL en cada plataforma, por encima de su lista propia
#: (hermes_cli/tools_config.py `_get_platform_tools`: «global suppression list
#: (#86661)… runs LAST so it overrides everything»; el gateway la pasa a cada
#: turno, gateway/run_turn.py `_resolve_turn_toolsets`; el REPL la lee en
#: hermes_cli/cli_init_mixin.py). VERIFICADO en el historial de Hermes
#: (segunda revisión de la candidata 0.5.1, N2): el gateway la lee y se la
#: pasa al agente de cada turno de cualquier plataforma desde la v0.13.0
#: (2026-05-07), y el agente quita una por una las herramientas de esos
#: toolsets (model_tools.py, #17309); en la v0.18.2 (9de9c25f62) está en
#: gateway/run.py y en `_get_platform_tools`. Las dos versiones que Workspace
#: soporta (VERIFIED_VERSIONS) la aplican en Discord: no hace falta además su
#: lista propia. Es un renglón del config.yaml: se edita a mano y en su lugar,
#: como `skills:`; la lista del socio se conserva (solo gana las que falten).
_GLOBAL_OFF_KEY = "disabled_toolsets"
#: La que FUGA: si sigue encendida, Hermes no se abre (fail-closed; abrirlo
#: dejaría a un agente leer las conversaciones de otro, y un cliente no técnico
#: no lo notaría). `memory` encendida solo avisa: sin memoria no guarda nada.
_LEAK_TOOL = "session_search"
#: Toolsets que encienden session_search sin nombrarla (compuestos de Hermes
#: v0.18.2: `coding` y todos los `hermes-*`). La prueba de deriva los recalcula
#: desde el toolsets.py instalado.
_LEAKY_TOOLSETS = ("session_search", "coding")

#: Tope de Hermes para su archivo de contexto (`context_file_max_chars`). Sin
#: él, Hermes lo escala con la ventana del modelo con piso de 20 000 caracteres
#: y RECORTA el centro de lo que pase; el AGENTS.md con el núcleo incrustado
#: mide ~35-45k. Explícito gana siempre en Hermes; se sube a este valor si es
#: menor (un valor mayor del socio se respeta).
CONTEXT_FILE_CHARS = 48_000

#: Variables de la PESTAÑA con las que `workspace memoria …` (y la corrida)
#: deciden cerebro, pestaña, motor y socio. Desde la 0.22.5, Hermes corre cada
#: sesión en un gateway compartido que hereda el entorno de la pestaña que lo
#: ARRANCÓ (y vive minutos después de cerrarla): sin esto, la nota de la
#: pestaña B caía en la ficha de A (u otro cerebro) o se rechazaba mandando a
#: guardar en A (revisión de la candidata, 2026-11-02). La clave oficial
#: `terminal.client_env_passthrough` (agent/session_client_env.py) hace viajar
#: estos nombres del cliente de CADA sesión a su terminal y quita los que ese
#: cliente no exporta. Nada secreto. Los nombres del socio se conservan.
_CLIENT_ENV_KEY = "client_env_passthrough"
_CLIENT_ENV = ("WORKSPACE_BRAIN", "WORKSPACE_WS", "ZENITH_WS", "WORKSPACE_ENGINE",
               "WORKSPACE_SESSION_ID", "WORKSPACE_SOCIO", "WORKSPACE_AGENT_NAME",
               "WORKSPACE_WID", "WORKSPACE_HERMES_RUN", "WORKSPACE_HERMES_SESSION")


def _client_env(text):
    """Los nombres de `terminal.client_env_passthrough` del config.yaml; [] si
    no está o tiene una forma que no se entiende."""
    p = _global_off_parse(text, "terminal", _CLIENT_ENV_KEY)
    return list(p["items"] or []) if p["state"] == "block" else []


def _client_env_ok(text):
    return set(_CLIENT_ENV) <= set(_client_env(text))


def _with_client_env(text):
    """config.yaml con los nombres de _CLIENT_ENV en
    `terminal.client_env_passthrough` (los del socio se conservan), o None si
    no hace falta o `terminal:` tiene una forma que no se edita a mano."""
    return _with_global_off(text, "terminal", _CLIENT_ENV_KEY, _CLIENT_ENV, _client_env_ok)

#: Skills del CEREBRO en Hermes: las lee del cerebro de la pestaña y las que
#: crea o parcha las escribe ahí, donde las ven los demás motores. Hermes
#: conserva su manejo nativo en la sesión visible (`skill_manage`, `/learn`,
#: `/refine` a pedido). VERIFICADO en el código de Hermes v0.22.2
#: (agent/skill_utils.py, tools/skill_manager_tool.py), 2026-10-21:
#:   · `external_dirs` acepta lista o texto y expande ${VAR} con el entorno de
#:     CADA proceso (cada pestaña ve su cerebro; sin la variable, la ruta no
#:     existe y se ignora). Una skill que ya existe se parcha donde vive: la
#:     del cerebro, en el cerebro.
#:   · `create_dir` (desde v0.21.6) es donde caen las skills NUEVAS. Se expande
#:     igual y Hermes crea la carpeta solo. Es una bandeja propia
#:     (`skills/aprendidas/`): Hermes solo acepta categorías ASCII
#:     (`[a-z0-9._-]`, rechaza «investigación») y la que invente queda dentro
#:     de la bandeja, nunca como categoría paralela del cerebro. Como cae
#:     dentro de `external_dirs`, la lista una sola vez (el mismo archivo por
#:     las dos raíces). Su curador no la toca (solo cura skills del perfil) y
#:     su mantenimiento de fondo no puede borrarla. Sin WORKSPACE_BRAIN (Hermes
#:     abierto a mano, el bot de Discord o un turno sin ventana, que run_turn
#:     corre sin cerebro) la toma literal bajo el perfil
#:     (`<perfil>/${WORKSPACE_BRAIN}/…`): queda ahí, y ninguna pestaña la ve.
#:     Si el socio ya tiene un `create_dir` propio, se respeta.
#:   · `creation_nudge_interval` en 0 apaga SOLO el repaso automático de fondo
#:     (una segunda corrida del modelo que relee la sesión y crea o parcha
#:     skills). No evita crear skills: las de la sesión visible caían en el
#:     perfil compartido hasta que llegó `create_dir`, y un agente veía las
#:     de otro.
#: Ninguna versión valida claves desconocidas al cargar: una versión anterior
#: a create_dir la ignora y crea en el perfil, como antes. Las skills de
#: fábrica del perfil siguen (vanilla) y, si una del cerebro se llama igual,
#: gana la de fábrica. Al cerrar, skills_aprendidas.py anota en el catálogo
#: del cerebro las que llegaron a la bandeja.
SKILLS_DIR = "${WORKSPACE_BRAIN}/skills"
SKILLS_CREATE = "${WORKSPACE_BRAIN}/skills/aprendidas"
SKILLS_NUDGE = 0

#: Hook por turno (tono + dueño de la sesión). Nombre distinto de cualquier
#: módulo de la raíz (runbook §6).
_HOOK_EVENT = "pre_llm_call"
_HOOK_SCRIPT = os.path.join(_ROOT, "hooks", "hermes_turno.py")
_HOOK_TIMEOUT = 10
#: Tope de Hermes para el contexto de UN hook (`hooks.output_spill.max_chars`,
#: de fábrica 10 000; tools/hook_output_spill.py en v0.18.2 y v0.22.2): lo
#: que pase se «derrama» a un archivo y el modelo solo ve 500 caracteres de
#: cada punta y la ruta. En el primer turno de una sesión el hook de Workspace
#: manda el tono, la memoria de la pestaña (≤ MEMORIA_TURNO_MAX) y la memoria
#: larga del cerebro (≤ MEMORIA_LARGA_MAX): con el tope de fábrica,
#: STATE/MEMORY.md llegaba como un archivo que el modelo tenía que decidir
#: leer. Va en el bloque `hooks:` de Workspace (Hermes salta `output_spill` al
#: leer los eventos, agent/shell_hooks.py) y solo si ese bloque es el único
#: hook del perfil; con hooks del socio no se toca y el hook se ajusta al tope
#: que haya. Workspace solo es dueño de ese renglón (`max_chars`, y solo si
#: falta: uno del socio se respeta); lo demás de `hooks:` (sus webhooks
#: `outbound`, el resto de su `output_spill`) es del socio y se edita en su
#: lugar sin tocarlo (_with_hook, _spill_fix).
HOOK_SPILL_CHARS = 32_000
_HOOK_SPILL_DEFAULT = 10_000
_HOOK_RESERVED = ("output_spill", "outbound")


# ── escáner de inyección de Hermes (copia de sus patrones) ─────────────────
#: Hermes escanea su archivo de contexto ANTES de meterlo al system prompt y,
#: con UN solo hallazgo, bloquea el archivo ENTERO («[BLOCKED: …]»): la
#: identidad desaparecería. Copia exacta de los patrones de alcance «all» y
#: «context» de `tools/threat_patterns.py` (v0.22.5), para no incrustar un
#: documento que dispare el bloqueo, más las formas más amplias de las
#: versiones anteriores que se siguen soportando (_SCAN_PATTERNS_PREV): un
#: documento se incrusta solo si NINGUNA versión verificada lo bloquearía.
#: test_motores_hermes compara esta copia con la del Hermes instalado cuando
#: existe (avisa si Hermes la cambia).
_SCAN_FILLER = r"(?:\w+\s+){0,8}"
#: v0.22.5: variable de entorno que TERMINA en un sufijo de secreto (\b).
_SCAN_SECRET_VAR = r"\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)S?\b"
_SCAN_PATTERNS = (
    (r'ignore\s+%s(previous|all|above|prior)\s+%sinstructions' % (_SCAN_FILLER, _SCAN_FILLER), "prompt_injection"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'disregard\s+%s(your|all|any)\s+%s(instructions|rules|guidelines)' % (_SCAN_FILLER, _SCAN_FILLER), "disregard_rules"),
    (r'act\s+as\s+(if|though)\s+%syou\s+%s(have\s+no|don\'t\s+have)\s+%s(restrictions|limits|rules)' % (_SCAN_FILLER, _SCAN_FILLER, _SCAN_FILLER), "bypass_restrictions"),
    (r'<!--[^>]{0,512}(?:ignore|override|system|secret|hidden)[^>]{0,512}-->', "html_comment_injection"),
    (r'<\s*div\s+style\s*=\s*["\'][^>]{0,2048}display\s*:\s*none', "hidden_div"),
    (r'translate\s+[^\n]{0,512}\s+into\s+\w+(?:[\s-]+\w+){0,2}\s+and\s+(execute|run|eval)\b', "translate_execute"),
    (r'do\s+not\s+%stell\s+%sthe\s+user' % (_SCAN_FILLER, _SCAN_FILLER), "deception_hide"),
    (r'you\s+are\s+%snow\s+(?:a|an|the)\s+' % _SCAN_FILLER, "role_hijack"),
    (r'pretend\s+%s(you\s+are|to\s+be)\s+' % _SCAN_FILLER, "role_pretend"),
    (r'output\s+%s(system|initial)\s+prompt' % _SCAN_FILLER, "leak_system_prompt"),
    (r'(respond|answer|reply)\s+without\s+%s(restrictions|limitations|filters|safety)' % _SCAN_FILLER, "remove_filters"),
    (r'you\s+have\s+been\s+%s(updated|upgraded|patched)\s+to' % _SCAN_FILLER, "fake_update"),
    (r'\bname\s+yourself\s+\w+', "identity_override"),
    (r'register\s+(as\s+)?a?\s*node', "c2_node_registration"),
    (r'(heartbeat|beacon|check[\s\-]?in)\s+(to|with)\s+', "c2_heartbeat"),
    (r'pull\s+(down\s+)?(?:new\s+)?task(?:ing|s)?\b', "c2_task_pull"),
    (r'connect\s+to\s+the\s+network\b', "c2_network_connect"),
    (r'you\s+must\s+(?:\w+\s+){0,3}(register|connect|report|beacon)\b', "forced_action"),
    (r'only\s+use\s+one[\s\-]?liners?\b', "anti_forensic_oneliner"),
    (r'never\s+%s(?:create|write)\s+%s(?:script|file)\s+%sdisk' % (_SCAN_FILLER, _SCAN_FILLER, _SCAN_FILLER), "anti_forensic_disk"),
    (r'unset\s+\w*(?:CLAUDE|CODEX|HERMES|AGENT|OPENAI|ANTHROPIC)\w*', "env_var_unset_agent"),
    (r'\b(?:cobalt\s*strike|sliver|havoc|mythic|metasploit|brainworm)\b', "known_c2_framework"),
    (r'\bc2\s+(?:server|channel|infrastructure|beacon)\b', "c2_explicit"),
    (r'\bcommand\s+and\s+control\b', "c2_explicit_long"),
    (r'curl\s+[^\n]{0,2048}' + _SCAN_SECRET_VAR, "exfil_curl"),
    (r'wget\s+[^\n]{0,2048}' + _SCAN_SECRET_VAR, "exfil_wget"),
    (r'cat\s+[^\n]{0,2048}(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)', "read_secrets"),
)
#: Formas de v0.18.2 y v0.22.2 que v0.22.5 angostó (exfil: cualquier variable
#: que CONTENGA el sufijo, «API» incluido; translate: cualquier texto entre
#: «into» y «and»). Se quitan cuando esas versiones salgan de VERIFIED_VERSIONS.
_SCAN_PATTERNS_PREV = (
    (r'translate\s+[^\n]{0,512}\s+into\s+[^\n]{0,512}\s+and\s+(execute|run|eval)', "translate_execute"),
    (r'curl\s+[^\n]{0,2048}\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl"),
    (r'wget\s+[^\n]{0,2048}\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget"),
)
_SCAN_INVISIBLE = frozenset("​‌‍⁠⁢⁣⁤﻿"
                            "‪‫‬‭‮⁦⁧⁨⁩")
_SCAN_MAX = 65_536
_SCAN_COMPILED = tuple((re.compile(p, re.IGNORECASE), pid)
                       for p, pid in _SCAN_PATTERNS + _SCAN_PATTERNS_PREV)


def scan_context(text):
    """Hallazgos que el escáner de contexto de Hermes daría para `text` (misma
    normalización: BOM inicial fuera, invisibles sobre el texto crudo, NFKC,
    sin mayúsculas), en cualquiera de las versiones soportadas; cada id una
    vez. [] = Hermes lo carga."""
    import unicodedata
    text = str(text or "")
    if text.startswith("﻿"):
        text = text[1:]
    text = text[:_SCAN_MAX]
    found = ["invisible_unicode_U+%04X" % ord(c)
             for c in sorted(set(text) & _SCAN_INVISIBLE)]
    norm = unicodedata.normalize("NFKC", text)
    for rx, pid in _SCAN_COMPILED:
        if pid not in found and rx.search(norm):
            found.append(pid)
    return found


#: cable-hermes: el perfil PROPIO del agente de esta corrida (sistema nuevo, ver «perfil por agente»). Lo pone
#: el lanzador al abrir; gana sobre el de Workspace en todo lo de esta sesión (su REPL, su número, su cierre).
_PERFIL_AGENTE_ENV = "WORKSPACE_HERMES_PERFIL_AGENTE"


def _profile():
    return (os.environ.get(_PERFIL_AGENTE_ENV, "").strip()
            or os.environ.get("WORKSPACE_HERMES_PROFILE", "").strip() or PROFILE)


def _perfil_base():
    """El perfil de Workspace (`workspace`): el de siempre y la base de la que se clona el de cada agente."""
    return os.environ.get("WORKSPACE_HERMES_PROFILE", "").strip() or PROFILE


def _base(exe):
    """Todo comando de Hermes de Workspace va con el perfil propio."""
    return [exe, "--profile", _profile()]


def _hermes_root():
    """Raíz de perfiles como la resuelve Hermes v0.18.2
    (`get_default_hermes_root`): ~/.hermes (Windows: %LOCALAPPDATA%\\hermes);
    un HERMES_HOME fuera de ella ES la raíz (o su `<raíz>/profiles/<p>`)."""
    if os.name == "nt":
        native = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                              "hermes")
    else:
        native = os.path.join(os.path.expanduser("~"), ".hermes")
    env = os.environ.get("HERMES_HOME", "").strip()
    if not env:
        return native
    real, rnat = os.path.realpath(env), os.path.realpath(native)
    if real == rnat or real.startswith(rnat + os.sep):
        return native
    if os.path.basename(os.path.dirname(real)) == "profiles":
        return os.path.dirname(os.path.dirname(real))
    return env


def profile_dir():
    """Carpeta del perfil de Workspace (la que Hermes usa con --profile)."""
    return os.path.join(_hermes_root(), "profiles", _profile())


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, ValueError):
        return None


def _write_atomic(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".ws-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _hook_command():
    """Comando del hook tal como Hermes lo parte (`shlex.split`, sin shell).
    En Windows con barras normales: shlex se comería las invertidas."""
    py, hk = sys.executable or "python3", _HOOK_SCRIPT
    if os.name == "nt":
        py, hk = py.replace("\\", "/"), hk.replace("\\", "/")
    return " ".join(shlex.quote(p) for p in (py, hk))


def _hook_block():
    return ("hooks:\n  %s:\n  - command: %s\n    timeout: %d\n"
            % (_HOOK_EVENT, json.dumps(_hook_command()), _HOOK_TIMEOUT))


def _spill_block():
    """La sub-sección `output_spill` que va dentro del bloque `hooks:` de
    Workspace, después del hook (ver HOOK_SPILL_CHARS)."""
    return "  output_spill:\n    max_chars: %d\n" % HOOK_SPILL_CHARS


def _spill_chars(text):
    """Tope del contexto de un hook según el config.yaml del perfil
    (`hooks.output_spill`): max_chars, el de fábrica si no está, o None si el
    derrame está apagado (`enabled: false`)."""
    lines = (text or "").splitlines(True)
    span = _hooks_span(lines)
    if span is None or span[2]:
        return _HOOK_SPILL_DEFAULT
    cap, dentro, sangria = _HOOK_SPILL_DEFAULT, False, 0
    for ln in lines[span[0] + 1:span[1]]:
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        ind = len(ln) - len(ln.lstrip(" \t"))
        m = re.match(r"[ \t]*([A-Za-z_]+):[ \t]*(.*?)[ \t]*(?:#.*)?$", ln.rstrip("\r\n"))
        if m and m.group(1) == "output_spill" and not m.group(2):
            dentro, sangria = True, ind
            continue
        if dentro and ind <= sangria:
            dentro = False
        if dentro and m:
            if m.group(1) == "enabled" and m.group(2).lower() in ("false", "no", "off"):
                return None
            if m.group(1) == "max_chars":
                try:
                    cap = int(m.group(2).strip("'\""))
                except ValueError:
                    pass
    return cap


def _setting_off(text, leaf):
    return bool(re.search(r"(?m)^[ \t]+%s:[ \t]*false[ \t]*$" % re.escape(leaf), text or ""))


def _hooks_span(lines):
    """(inicio, fin, ¿valor en línea?) de la clave `hooks:` de primer nivel, o
    None. «En línea» = un valor no vacío en la misma línea (`hooks: {…}`):
    YAML válido que no se re-escribe a mano."""
    return _top_span(lines, "hooks")


def _top_span(lines, key):
    """(inicio, fin, ¿valor en línea?) de la clave `key:` de primer nivel del
    config.yaml, o None (ver _hooks_span)."""
    for i, ln in enumerate(lines):
        m = re.match(r"%s:(.*)$" % re.escape(key), ln.rstrip("\r\n"))
        if not m:
            continue
        val = m.group(1).strip()
        if val and not val.startswith("#") and not re.match(
                r"(\{\s*\}|\[\s*\]|null|~)\s*(#.*)?$", val):
            return i, i + 1, True
        j = i + 1
        while j < len(lines):
            if not lines[j].strip() or lines[j][:1] in (" ", "\t", "-"):
                j += 1
                continue
            if lines[j].startswith("#"):
                # Un comentario en la columna 0 no corta el bloque si después
                # sigue contenido sangrado (antes el bloque «terminaba» ahí y
                # el hook de Workspace se agregaba duplicado, HM-HK); si lo que
                # sigue es otra clave o el final, es de lo que viene y se queda.
                k = j
                while k < len(lines) and (not lines[k].strip() or lines[k].startswith("#")):
                    k += 1
                if k < len(lines) and lines[k][:1] in (" ", "\t", "-"):
                    j = k
                    continue
            break
        return i, j, False
    return None


def _hooks_state(text):
    """absent (sin hooks) · ours (el bloque exacto de Workspace) · stale (solo
    el hook de Workspace, con otra ruta/forma) · foreign (hay hooks ajenos o
    en una forma que no se re-escribe a mano: no se tocan)."""
    text = text or ""
    if _hook_block() in text:
        return "ours"
    lines = text.splitlines(True)
    span = _hooks_span(lines)
    if span is None:
        return "absent"
    if span[2]:
        return "foreign"
    block = "".join(lines[span[0] + 1:span[1]])
    cmds = len(re.findall(r"\bcommand:", block))
    if not cmds:
        return "absent"
    events = set(re.findall(r"(?m)^[ \t]+([A-Za-z_]+):[ \t]*$", block)) - set(_HOOK_RESERVED)
    if events <= {_HOOK_EVENT} and cmds == block.count(os.path.basename(_HOOK_SCRIPT)):
        return "stale"
    return "foreign"


def _hooks_only_ours(text):
    """¿El bloque `hooks:` del perfil es SOLO el de Workspace (estado «ours» y
    un solo `command:` en el bloque)? Solo entonces el REPL se abre con
    `--accept-hooks`: así jamás se aprueba un hook del socio."""
    text = text or ""
    if _hooks_state(text) != "ours" or len(re.findall(r"(?m)^hooks:", text)) != 1:
        return False
    lines = text.splitlines(True)
    span = _hooks_span(lines)
    if span is None or span[2]:
        return False
    block = "".join(lines[span[0]:span[1]])
    return _hook_block() in block and len(re.findall(r"\bcommand:", block)) == 1


def _hooks_children(lines, span):
    """Las sub-claves del bloque `hooks:` (sin valor en línea) → (sangría,
    [(clave, inicio, fin)]), `fin` = una línea después de su último renglón
    con contenido; o None si el bloque tiene una forma que no se edita a mano
    (una lista, sangrías mezcladas, algo que no es `clave:`)."""
    ci, out = None, []
    for k in range(span[0] + 1, span[1]):
        raw = lines[k].rstrip("\r\n")
        st = raw.strip()
        if not st or st.startswith("#"):
            continue
        lead = raw[:len(raw) - len(raw.lstrip(" \t"))]
        if ci is None:
            if not lead or st.startswith("-"):
                return None
            ci = lead
        if len(lead) > len(ci) or (lead == ci and st.startswith("-")):
            if out:
                out[-1][2] = k + 1                    # valor de la sub-clave de arriba
            continue
        m = re.match(r"([A-Za-z0-9_.-]+):(.*)$", st)
        if lead != ci or not m:
            return None
        out.append([m.group(1), k, k + 1])
    return ci, [tuple(c) for c in out]


def _with_hook(text):
    """config.yaml con el hook de Workspace, o None si `hooks:` tiene una forma
    que no se edita a mano. Sin `hooks:`, el bloque de Workspace (hook + tope
    de su contexto) va al final. Con `hooks:`, se edita EN SU LUGAR: solo se
    quita la entrada vieja de Workspace (estado «stale») o un `pre_llm_call`
    sin comandos, el hook va primero y, si el bloque no trae `output_spill`,
    el tope va después; lo demás (webhooks `outbound`, el `output_spill` del
    socio, comentarios) queda byte a byte. Antes se reescribía el bloque
    entero y los webhooks del socio desaparecían en cada arranque (revisión
    de la 0.5.1, P1-2)."""
    lines = (text or "").splitlines(True)
    span = _hooks_span(lines)
    if span is None:
        body = "".join(lines)
        if body and not body.endswith("\n"):
            body += "\n"
        return body + _hook_block() + _spill_block()
    if span[2]:
        return None
    kids = _hooks_children(lines, span)
    if kids is None:
        return None
    ci, children = kids
    if children and ci != "  ":
        return None                    # otra sangría: el hook no cabe al mismo nivel
    s0 = span[0]
    new = list(lines)
    for key, a, b in sorted(children, key=lambda c: c[1], reverse=True):
        if key == _HOOK_EVENT:         # «stale»: solo comandos de Workspace (o ninguno)
            del new[a:b]
    resto = new[s0].rstrip("\r\n")[len("hooks:"):].strip()
    previo = [resto + "\n"] if resto.startswith("#") else []   # su comentario, arriba
    spill = any(key == "output_spill" for key, _a, _b in children)
    ours = _hook_block()[len("hooks:\n"):] + ("" if spill else _spill_block())
    new[s0:s0 + 1] = previo + ["hooks:\n", ours]
    out = "".join(new)
    return out if _hooks_state(out) == "ours" else None


def _spill_fix(text):
    """config.yaml con el tope del contexto del hook (`max_chars` en su
    `output_spill`), o None si no hace falta o no se toca. Solo cuando el
    bloque `hooks:` es SOLO el de Workspace (con hooks del socio no se toca) y
    a su `output_spill` le falta `max_chars`: se agrega ESE renglón (o la
    sub-sección, después del hook) y lo demás queda byte a byte. Un
    `max_chars` que ya está (el del socio) se respeta; el derrame apagado
    (`enabled: false`) no necesita tope; una forma que no se reconoce no se
    toca (revisión de la 0.5.1, P1-2)."""
    text = text or ""
    if not _hooks_only_ours(text):
        return None
    lines = text.splitlines(True)
    span = _hooks_span(lines)
    kids = _hooks_children(lines, span) if span and not span[2] else None
    if kids is None:
        return None
    ci, children = kids
    spills = [c for c in children if c[0] == "output_spill"]
    if len(spills) > 1:
        return None
    if not spills:
        hook = [c for c in children if c[0] == _HOOK_EVENT]
        if len(hook) != 1:
            return None
        at = hook[0][2]
        new = lines[:at] + [_spill_block()] + lines[at:]
    else:
        _key, a, b = spills[0]
        if _yaml_value(lines[a].rstrip("\r\n").split(":", 1)[1]):
            return None                # `output_spill: {…}` en línea
        cl = None
        for k in range(a + 1, b):
            raw = lines[k].rstrip("\r\n")
            st = raw.strip()
            if not st or st.startswith("#"):
                continue
            lead = raw[:len(raw) - len(raw.lstrip(" \t"))]
            if cl is None:
                if len(lead) <= len(ci):
                    return None
                cl = lead
            if len(lead) > len(cl):
                continue               # valor de otra clave
            m = re.match(r"([A-Za-z0-9_.-]+):(.*)$", st)
            if lead != cl or not m:
                return None
            if m.group(1) == "max_chars":
                return None            # ya hay tope: se respeta
            if m.group(1) == "enabled" and _yaml_value(m.group(2)).lower() in ("false", "no", "off"):
                return None
        new = list(lines)
        if not new[a].endswith("\n"):
            new[a] += "\n"
        new[a + 1:a + 1] = ["%smax_chars: %d\n" % (cl or ci + "  ", HOOK_SPILL_CHARS)]
    out = "".join(new)
    return out if (_hooks_state(out) == "ours"
                   and _spill_chars(out) == HOOK_SPILL_CHARS) else None


def _spill_ok(text):
    """¿El contexto del hook cabe sin derramarse, o su tope no es de Workspace
    (hooks del socio, su `max_chars`, el derrame apagado, una forma que no se
    edita)? Ver _spill_fix."""
    return _spill_fix(text) is None


# ── skills del cerebro: la clave `skills:` del config.yaml del perfil ──────
# Se edita a mano y en su lugar, como el bloque de hooks: `hermes config set`
# no crea listas y re-vuelca el YAML. Lo que el socio tenga en `skills:` se
# conserva (su lista de external_dirs solo gana una entrada; su create_dir se
# respeta; solo se llena si falta o está vacío); una forma que este lector no
# entiende no se toca.
def _yaml_scalar(s):
    """Escalar YAML de una línea (con o sin comillas, sin el comentario
    final) → texto, o None si no es un escalar simple (lista, mapa, ancla…)."""
    s = (s or "").strip()
    if s[:1] == "'":
        m = re.match(r"'((?:[^']|'')*)'[ \t]*(#.*)?$", s)
        return m.group(1).replace("''", "'") if m else None
    if s[:1] == '"':
        m = re.match(r'("(?:[^"\\]|\\.)*")[ \t]*(#.*)?$', s)
        try:
            v = json.loads(m.group(1)) if m else None
        except ValueError:
            return None
        return v if isinstance(v, str) else None
    s = re.sub(r"[ \t]+#.*$", "", s).strip()
    if not s or s[0] in "[]{}&*!|>%@`#,?" or s == "-" or s.startswith("- "):
        return None
    return s


def _yaml_value(rest):
    """Lo que hay después de `clave:` sin el comentario final ('' = vacío)."""
    rest = (rest or "").strip()
    if rest.startswith("#"):
        return ""
    if rest[:1] in ("'", '"', "["):
        return rest
    return re.sub(r"[ \t]+#.*$", "", rest).strip()


def _flow_items(s):
    """`[a, "b"]` en una línea → ['a', 'b'], o None si no es una lista simple
    de escalares (anidada, sin cierre, con algo raro después)."""
    s = (s or "").strip()
    if not s.startswith("["):
        return None
    items, cur, q, i = [], "", None, 1
    while i < len(s):
        c = s[i]
        if q:
            cur += c
            if q == '"' and c == "\\" and i + 1 < len(s):
                cur += s[i + 1]
                i += 2
                continue
            if c == q:
                if q == "'" and s[i + 1:i + 2] == "'":
                    cur += "'"
                    i += 2
                    continue
                q = None
        elif c in "'\"":
            q = c
            cur += c
        elif c == ",":
            items.append(cur)
            cur = ""
        elif c == "]":
            after = s[i + 1:].strip()
            if after and not after.startswith("#"):
                return None
            items.append(cur)
            vals = [_yaml_scalar(x) for x in items if x.strip()]
            return None if None in vals else vals
        elif c in "[{":
            return None
        else:
            cur += c
        i += 1
    return None


def _skills_parse(text):
    """`skills:` de primer nivel → {state: absent|block|foreign, dirs (lista de
    external_dirs o None si no está), create (create_dir como texto o None),
    nudge (creation_nudge_interval como texto o None), y dónde está cada cosa
    para editar sin tocar lo demás}. Lee la lista sangrada (como la vuelca
    Hermes), al nivel de la clave, en una línea (`[a, b]`) o un texto suelto
    (Hermes lo acepta como una sola ruta). «foreign» = una forma que no se
    edita a mano."""
    lines = (text or "").splitlines(True)
    out = {"lines": lines, "state": "absent", "dirs": None, "nudge": None,
           "span": None, "ci": "  ", "dirs_at": None, "dirs_end": None,
           "dirs_form": None, "item_lead": None, "nudge_at": None,
           "create": None, "create_at": None}
    span = _top_span(lines, "skills")
    if span is None:
        return out
    out["span"] = span
    if span[2]:
        return dict(out, state="foreign")
    s0, s1 = span[0], span[1]
    ci = None
    k = s0 + 1
    while k < s1:
        raw = lines[k].rstrip("\r\n")
        st = raw.strip()
        if not st or st.startswith("#"):
            k += 1
            continue
        lead = raw[:len(raw) - len(raw.lstrip(" \t"))]
        if ci is None:
            if not lead or st.startswith("-"):
                return dict(out, state="foreign")       # `skills:` como lista
            ci = lead
        if len(lead) > len(ci) or (lead == ci and st.startswith("-")):
            k += 1                                       # valor de otra clave
            continue
        m = re.match(r"([A-Za-z0-9_.-]+):(.*)$", st)
        if lead != ci or not m:
            return dict(out, state="foreign")
        key, val = m.group(1), _yaml_value(m.group(2))
        if key == "external_dirs":
            if out["dirs_at"] is not None:
                return dict(out, state="foreign")       # clave repetida
            out["dirs_at"] = k
            if val in ("", "[]", "null", "~"):
                items, last, item_lead, j = [], None, None, k + 1
                while val == "" and j < s1:
                    r2 = lines[j].rstrip("\r\n")
                    s2 = r2.strip()
                    if not s2 or s2.startswith("#"):
                        j += 1
                        continue
                    l2 = r2[:len(r2) - len(r2.lstrip(" \t"))]
                    if s2[:2] in ("- ", "-\t") and len(l2) >= len(ci):
                        v = _yaml_scalar(s2[2:])
                        if v is None:
                            return dict(out, state="foreign")
                        items.append(v)
                        item_lead = item_lead if item_lead is not None else l2
                        last = j
                        j += 1
                        continue
                    if len(l2) > len(ci):
                        return dict(out, state="foreign")   # valor en otra línea
                    break
                out.update(dirs=items, dirs_form="block" if items else "empty",
                           dirs_end=(last if items else k) + 1, item_lead=item_lead)
                k = out["dirs_end"]
                continue
            if val.startswith("["):
                items = _flow_items(val)
            else:
                v = _yaml_scalar(val)
                items = None if v is None else [v]
            if items is None:
                return dict(out, state="foreign")
            out.update(dirs=items, dirs_form="inline", dirs_end=k + 1)
        elif key == "create_dir":
            if out["create_at"] is not None:
                return dict(out, state="foreign")       # clave repetida
            v = _yaml_scalar(val) if val else ""
            if v is None:
                return dict(out, state="foreign")       # lista, mapa, ancla…
            j = k + 1
            while not val and j < s1:                   # ¿el valor sigue abajo?
                r2 = lines[j].rstrip("\r\n")
                s2 = r2.strip()
                if s2 and not s2.startswith("#"):
                    l2 = r2[:len(r2) - len(r2.lstrip(" \t"))]
                    if len(l2) > len(ci) or (l2 == ci and s2.startswith("-")):
                        return dict(out, state="foreign")
                    break
                j += 1
            # vacío, null o ~ = Hermes lo toma como no puesto (perfil local)
            out.update(create_at=k, create="" if val in ("null", "Null", "NULL", "~") else v)
        elif key == "creation_nudge_interval":
            if out["nudge_at"] is not None:
                return dict(out, state="foreign")
            out.update(nudge_at=k, nudge=_yaml_scalar(val) if val else "")
        k += 1
    out.update(state="block", ci=ci or "  ")
    return out


def _skills_ok(text):
    """¿El config.yaml ya conecta las skills del cerebro, manda las nuevas a
    un create_dir (el de Workspace o el del socio) y apaga el repaso
    automático de fondo?"""
    p = _skills_parse(text)
    return (p["state"] == "block" and SKILLS_DIR in (p["dirs"] or [])
            and bool(p["create"])
            and (p["nudge"] or "").strip() == str(SKILLS_NUDGE))


def _yaml_quote(v):
    """Una entrada de la lista del socio, tal cual si es un escalar simple; si
    no, entre comillas dobles (JSON es YAML válido)."""
    v = str(v)
    if _yaml_scalar(v) == v and ": " not in v and " #" not in v:
        return v
    return json.dumps(v, ensure_ascii=False)


def _with_skills(text):
    """config.yaml con las claves de skills del cerebro, o None si `skills:`
    tiene una forma que no se edita a mano. Lo demás, intacto."""
    p = _skills_parse(text)
    if p["state"] == "foreign":
        return None
    lines = list(p["lines"])
    if p["state"] == "absent":
        body = "".join(lines)
        if body and not body.endswith("\n"):
            body += "\n"
        return body + ("skills:\n  external_dirs:\n    - %s\n  create_dir: %s\n"
                       "  creation_nudge_interval: %d\n"
                       % (SKILLS_DIR, SKILLS_CREATE, SKILLS_NUDGE))
    s0, s1 = p["span"][0], p["span"][1]
    ci = p["ci"]
    if lines[s1 - 1:s1] and not lines[s1 - 1].endswith("\n"):
        lines[s1 - 1] += "\n"
    if _yaml_value(lines[s0].rstrip("\r\n")[len("skills:"):]):
        lines[s0] = "skills:\n"                      # `skills: {}` / null → bloque
    ours = "%s  - %s\n" % (ci, SKILLS_DIR)
    create = "%screate_dir: %s\n" % (ci, SKILLS_CREATE)
    # (índice, cuántas, líneas nuevas). Los reemplazos van antes que las
    # inserciones: en el mismo índice, el reemplazo se aplica primero.
    edits, head = [], []
    if p["nudge_at"] is not None and (p["nudge"] or "").strip() != str(SKILLS_NUDGE):
        edits.append((p["nudge_at"], 1, ["%screation_nudge_interval: %d\n" % (ci, SKILLS_NUDGE)]))
    if p["create_at"] is not None and not p["create"]:
        edits.append((p["create_at"], 1, [create]))  # vacío: Hermes lo toma como no puesto
    if p["dirs_at"] is None:
        head += ["%sexternal_dirs:\n" % ci, ours]
    elif SKILLS_DIR not in p["dirs"]:
        if p["dirs_form"] == "block":
            edits.append((p["dirs_end"], 0, ["%s- %s\n" % (p["item_lead"], SKILLS_DIR)]))
        else:
            edits.append((p["dirs_at"], 1, ["%sexternal_dirs:\n" % ci]
                          + ["%s  - %s\n" % (ci, _yaml_quote(d)) for d in p["dirs"]]
                          + [ours]))
    if p["create_at"] is None:
        head.append(create)
    if p["nudge_at"] is None:
        head.append("%screation_nudge_interval: %d\n" % (ci, SKILLS_NUDGE))
    if head:
        edits.append((s0 + 1, 0, head))
    for at, n, new in sorted(edits, key=lambda e: e[0], reverse=True):
        lines[at:at + n] = new
    return "".join(lines)


# ── herramientas apagadas en todas las plataformas: `agent.disabled_toolsets`
def _global_off_parse(text, section="agent", key=None):
    """`agent.disabled_toolsets` del config.yaml (o `<section>.<key>`, otra
    lista de nombres del mismo estilo) → {state: absent|block|foreign,
    items (la lista, o None si la clave no está), y dónde está cada cosa para
    editar sin tocar lo demás}. Lee la lista sangrada (como la vuelca Hermes),
    en una línea (`[a, b]`), vacía/null, un nombre suelto o el texto de una
    lista (`"['memory']"`, como lo lee Hermes: parse_config_string_list).
    Conservador: de `agent:` solo mira esa clave; «foreign» = `agent:` o la
    clave en una forma que no se edita a mano."""
    key = key or _GLOBAL_OFF_KEY
    lines = (text or "").splitlines(True)
    out = {"lines": lines, "state": "absent", "items": None, "span": None, "ci": "  ",
           "at": None, "end": None, "form": None, "item_lead": None}
    span = _top_span(lines, section)
    if span is None:
        return out
    out["span"] = span
    if span[2]:
        return dict(out, state="foreign")
    ci, k = None, span[0] + 1
    while k < span[1]:
        raw = lines[k].rstrip("\r\n")
        st = raw.strip()
        if not st or st.startswith("#"):
            k += 1
            continue
        lead = raw[:len(raw) - len(raw.lstrip(" \t"))]
        if ci is None:
            if not lead or st.startswith("-"):
                return dict(out, state="foreign")
            ci = lead
        if len(lead) > len(ci) or (lead == ci and st.startswith("-")):
            k += 1                                       # valor de otra clave
            continue
        m = re.match(r"([A-Za-z0-9_.-]+):(.*)$", st)
        if lead != ci or not m:
            return dict(out, state="foreign")
        if m.group(1) != key:
            k += 1
            continue
        if out["at"] is not None:
            return dict(out, state="foreign")           # clave repetida
        val = _yaml_value(m.group(2))
        out["at"] = k
        if val in ("", "[]", "null", "Null", "NULL", "~"):
            items, last, item_lead, j = [], None, None, k + 1
            while val == "" and j < span[1]:
                r2 = lines[j].rstrip("\r\n")
                s2 = r2.strip()
                if not s2 or s2.startswith("#"):
                    j += 1
                    continue
                l2 = r2[:len(r2) - len(r2.lstrip(" \t"))]
                if s2[:2] in ("- ", "-\t") and len(l2) >= len(ci):
                    v = _yaml_scalar(s2[2:])
                    if v is None:
                        return dict(out, state="foreign")
                    items.append(v)
                    item_lead = item_lead if item_lead is not None else l2
                    last = j
                    j += 1
                    continue
                if len(l2) > len(ci):
                    return dict(out, state="foreign")   # valor en otra línea
                break
            out.update(items=items, form="block" if items else "empty",
                       end=(last if items else k) + 1, item_lead=item_lead)
            k = out["end"]
            continue
        if val.startswith("["):
            items = _flow_items(val)
        else:
            v = _yaml_scalar(val)
            items = None if v is None else [v]
            if v is not None and v.strip().startswith("["):
                try:
                    import ast
                    lst = ast.literal_eval(v.strip())
                except (ValueError, SyntaxError):
                    lst = None
                items = ([str(x) for x in lst] if isinstance(lst, list)
                         and all(isinstance(x, str) for x in lst) else None)
        if items is None:
            return dict(out, state="foreign")
        out.update(items=items, form="inline", end=k + 1)
        k += 1
    out.update(state="block", ci=ci or "  ")
    return out


def _global_off(text):
    """Las herramientas que el perfil apaga en TODAS las plataformas
    (`agent.disabled_toolsets`, ver _GLOBAL_OFF_KEY); [] si no hay o no se
    entiende la forma."""
    p = _global_off_parse(text)
    return list(p["items"] or []) if p["state"] == "block" else []


def _global_off_ok(text):
    """¿session_search y memory ya están apagadas en todas las plataformas?"""
    off = _global_off(text)
    return all(t in off for t in _TOOLSETS_OFF)


def _with_global_off(text, section="agent", key=None, names=None, ok=None):
    """config.yaml con session_search y memory en `agent.disabled_toolsets` (o
    `names` en `<section>.<key>`), o None si no hace falta o la sección tiene
    una forma que no se edita a mano. La lista del socio se conserva (solo
    gana las que falten); lo demás de la sección y del archivo queda byte a
    byte."""
    key, names, ok = key or _GLOBAL_OFF_KEY, names or _TOOLSETS_OFF, ok or _global_off_ok
    p = _global_off_parse(text, section, key)
    if p["state"] == "foreign":
        return None
    if p["state"] == "absent" and re.search(r"""(?m)^\ufeff?["']?%s["']?[ \t]*:""" % re.escape(section),
                                            text or ""):
        # `"terminal":`, `terminal :` o un BOM delante: agregar otra sección
        # dejaría una clave repetida y Hermes no leería el config entero
        # (revisión nocturna, B1): se avisa sin escribir
        return None
    falta = [t for t in names if t not in (p["items"] or [])]
    if not falta:
        return None
    lines = list(p["lines"])
    if p["state"] == "absent":
        body = "".join(lines)
        if body and not body.endswith("\n"):
            body += "\n"
        return body + "%s:\n  %s:\n" % (section, key) + "".join(
            "  - %s\n" % t for t in names)
    s0, s1, ci = p["span"][0], p["span"][1], p["ci"]
    if lines[s1 - 1:s1] and not lines[s1 - 1].endswith("\n"):
        lines[s1 - 1] += "\n"
    if _yaml_value(lines[s0].rstrip("\r\n")[len(section) + 1:]):
        lines[s0] = "%s:\n" % section               # `agent: {}` / null → bloque

    def items(lead, names):
        return ["%s- %s\n" % (lead, _yaml_quote(t)) for t in names]
    if p["at"] is None:
        lines[s0 + 1:s0 + 1] = ["%s%s:\n" % (ci, key)] + items(ci, falta)
    elif p["form"] == "block":
        lines[p["end"]:p["end"]] = items(p["item_lead"], falta)
    else:                                            # vacía o en una línea
        lines[p["at"]:p["at"] + 1] = (["%s%s:\n" % (ci, key)]
                                      + items(ci, list(p["items"] or []) + falta))
    new = "".join(lines)
    return new if ok(new) else None


def _context_chars(text):
    """`context_file_max_chars` de primer nivel del config.yaml (0 = no hay)."""
    m = re.search(r"(?m)^context_file_max_chars:[ \t]*['\"]?(\d+)['\"]?[ \t]*(#.*)?$",
                  text or "")
    return int(m.group(1)) if m else 0


def _cli_toolsets(text):
    """Lista `platform_toolsets.cli` del config.yaml (ver _platform_toolsets)."""
    return _platform_toolsets(text, "cli")


def _platform_toolsets(text, platform):
    """Lista `platform_toolsets.<platform>` del config.yaml, o None si no está
    (Hermes usa entonces su super-toolset de la plataforma, `hermes-cli` /
    `hermes-discord`, que lo incluye todo). Lee las dos formas en que Hermes
    vuelca listas (`- x` al nivel de la clave o sangrado) y la forma en línea
    `[a, b]`.

    Conservadora: una forma que no reconoce (lista en varias líneas, valores
    raros) devuelve None, que cuenta como «todo encendido» y fuerza el
    `tools disable` oficial. Los comentarios YAML no son parte del nombre."""
    def uncomment(s):
        return re.sub(r"(^|[ \t])#.*$", "", s).strip()

    def name(s):
        s = uncomment(s).strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
            s = s[1:-1]
        return s if re.fullmatch(r"[A-Za-z0-9_.:@/-]+", s) else None

    lines = (text or "").splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if re.match(r"platform_toolsets:[ \t]*(#.*)?$", ln)), None)
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        ln = lines[j]
        if not ln.strip() or ln.strip().startswith("#"):
            continue
        if ln[:1] not in (" ", "\t"):
            return None                       # siguiente clave de primer nivel
        m = re.match(r"([ \t]+)%s:(.*)$" % re.escape(platform), ln)
        if not m:
            continue
        indent, rest = len(m.group(1)), uncomment(m.group(2))
        if rest:
            if not (rest.startswith("[") and rest.endswith("]")):
                return None                   # forma no reconocida
            parts = [p for p in rest[1:-1].split(",") if p.strip()]
            names = [name(p) for p in parts]
            return None if None in names else names
        items = []
        for ln2 in lines[j + 1:]:
            if not ln2.strip() or ln2.strip().startswith("#"):
                continue
            lead = len(ln2) - len(ln2.lstrip(" \t"))
            mm = re.match(r"([ \t]*)-[ \t]*(.*)$", ln2)
            if mm and lead >= indent:
                n = name(mm.group(2))
                if n is None:
                    return None               # valor no reconocido
                items.append(n)
                continue
            if lead > indent:
                return None                   # valor en otra línea (`[x]`…)
            break
        # `cli:` sin elementos es null en YAML: Hermes usa su default
        # (`hermes-cli`, todo encendido). Solo `cli: []` es una lista vacía.
        return items or None
    return None


def _tool_on(text, name, platform="cli"):
    """¿La herramienta `name` queda encendida en la plataforma del perfil
    (cli = REPL/`-z`)? Sin lista, o con un compuesto `hermes-*`, está
    encendida; session_search también la enciende el compuesto `coding`. En
    las plataformas del gateway gana la lista global `agent.disabled_toolsets`
    (el gateway se la pasa al agente de cada turno, que quita sus herramientas
    una por una, también las de un compuesto; ver _GLOBAL_OFF_KEY). En `cli`
    se exige además la lista propia, como siempre: `hermes -z` (los turnos
    sin ventana) arma sus herramientas con `_get_platform_tools`, que sí
    aplica la global (hermes_cli/oneshot.py, v0.22.2), pero así no depende de
    cómo la aplique cada versión en el REPL y en `-z`."""
    if platform != "cli" and name in _global_off(text):
        return False
    ts = _platform_toolsets(text, platform)
    if ts is None or any(t.startswith("hermes-") for t in ts):
        return True
    if name == _LEAK_TOOL and any(t in _LEAKY_TOOLSETS for t in ts):
        return True
    return name in ts


def _toolsets_off(text, platform="cli"):
    """¿Las herramientas de _TOOLSETS_OFF están apagadas en la lista de la
    plataforma?"""
    return not any(_tool_on(text, t, platform) for t in _TOOLSETS_OFF)


def _platform_args(platform):
    """`--platform <p>` para `tools list|disable` (cli es el default de Hermes:
    el comando de la terminal queda como siempre)."""
    return [] if platform == "cli" else ["--platform", platform]


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_TOOLS_LIST_LINE = re.compile(r"^\s*(?:[✓✗]\s*)?(enabled|disabled)\s+([A-Za-z0-9_.:@/-]+)")


def _cli_tools_state(exe, runner=None, platform="cli"):
    """{toolset: encendido?} según la FUENTE OFICIAL, `hermes --profile <p>
    tools list [--platform <plataforma>]` (v0.18.2: «✓ enabled  web …» /
    «✗ disabled  memory …», ya resuelto con compuestos y
    `agent.disabled_toolsets`; sin traducir). {} si el CLI falla o su salida
    no se reconoce: quien lo use lo toma como «encendido» (fail-closed). Solo
    fuera del camino feliz."""
    try:
        r = _run(_base(exe) + ["tools", "list"] + _platform_args(platform),
                 runner=runner, timeout=60)
    except Exception:
        return {}
    if getattr(r, "returncode", 1) != 0:
        return {}
    out = {}
    for ln in _ANSI.sub("", getattr(r, "stdout", "") or "").splitlines():
        m = _TOOLS_LIST_LINE.match(ln)
        if m:
            out.setdefault(m.group(2), m.group(1) == "enabled")
    return out


def _quick_ok(d):
    """¿Los archivos del perfil ya dicen que todo lo del cerebro está bien?
    (SOUL neutral, memoria y herramientas compartidas apagadas, tope del
    archivo de contexto, hook de Workspace). Solo lee archivos: cero llamadas
    al CLI en el arranque feliz. Jamás lee el .env."""
    cfg = _read_text(os.path.join(d, "config.yaml"))
    return (cfg is not None and _read_text(os.path.join(d, "SOUL.md")) == SOUL_TEXT
            and all(_setting_off(cfg, leaf) for _k, leaf in _BRAIN_SETTINGS)
            and all(_toolsets_off(cfg, p) for p in _TOOLS_PLATFORMS)
            and _global_off_ok(cfg)
            and _context_chars(cfg) >= CONTEXT_FILE_CHARS
            and _hooks_state(cfg) == "ours"
            and _spill_ok(cfg)
            and _skills_ok(cfg)
            and _client_env_ok(cfg))


def _shown_path(exe, runner=None):
    """Carpeta del perfil según `hermes profile show <p>` (exacto), o None si
    el perfil no existe."""
    r = _run([exe, "profile", "show", _profile()], runner=runner, timeout=60)
    if getattr(r, "returncode", 1) != 0:
        return None
    for line in (getattr(r, "stdout", "") or "").splitlines():
        if line.strip().startswith("Path:"):
            p = line.split(":", 1)[1].strip()
            return p if os.path.isdir(p) else None
    return None


def ensure_profile(exe=None, runner=None):
    """Crea el perfil propio UNA vez (oficial: `profile create <p> --no-alias`,
    sin --clone: nada de las llaves del socio; nunca lo recrea ni toca el
    default) y re-asegura SOLO lo del cerebro, idempotente. Devuelve (ok,
    aviso): aviso = '' o una línea."""
    exe = exe or _exe()
    if not exe:
        return False, "hermes no está en PATH"
    try:
        if _quick_ok(profile_dir()):
            return True, ""
        # Varias pestañas pueden arrancar a la vez: crear/re-asegurar el perfil
        # compartido va con candado entre procesos, y se re-mira adentro.
        import olock
        with olock.file_lock(_profile_lock(), timeout=180):
            return _ensure_locked(exe, runner)
    except subprocess.TimeoutExpired as e:
        # Escenario hm-nuevo (2026-10-16): en una raíz de datos nueva, el primer
        # `hermes` prepara su entorno durante minutos; el socio veía el
        # TimeoutExpired crudo con la ruta del .cmd. P-7 (v0.22.2): `--version`
        # es un metadato que no prepara nada (hermes_cli/venv_sync.py); `status`
        # sí.
        return False, ("Hermes no respondió en %d s (`hermes %s`). La primera vez que corre en "
                       "esta carpeta de datos prepara sus dependencias y puede tardar unos "
                       "minutos: corre `hermes status` en otra terminal, espera a que termine "
                       "y vuelve a abrir el agente" % (int(e.timeout or 0), " ".join(
                           str(c) for c in list(e.cmd or [])[1:3])))
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def _profile_lock():
    d = os.path.dirname(_runs_path()) or "."
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "hermes-profile")


def _ensure_locked(exe, runner):
    """El camino exacto de ensure_profile, ya con el candado tomado."""
    d = profile_dir()
    if _quick_ok(d):
        return True, ""
    avisos, created = [], False
    if not os.path.isdir(d):
        shown = _shown_path(exe, runner)
        if shown:
            d = shown
        else:
            # SIN --clone (copiaría el .env con las llaves del socio): Hermes
            # siembra solo su modelo y un .env vacío (VERIFICADO v0.22.2,
            # hermes_cli/profiles.py: _seed_model_config + _finish_profile_layout).
            r = _run([exe, "profile", "create", _profile(), "--no-alias"],
                     runner=runner, timeout=180)
            created = getattr(r, "returncode", 1) == 0
            shown = _shown_path(exe, runner)
            if not created and not shown:
                err = ((getattr(r, "stderr", "") or "") + (getattr(r, "stdout", "") or ""))
                return False, "no pude crear el perfil %s de Hermes: %s" % (
                    _profile(), err.strip()[-200:] or "rc=%s" % getattr(r, "returncode", "?"))
            # Si el create falló porque otro proceso (fuera del candado: una
            # máquina con otro Workspace, el socio a mano) ya lo creó, se usa.
            d = shown or d
            if not os.path.isdir(d):
                return False, "creé el perfil %s pero no encuentro su carpeta" % _profile()
            if created:
                avisos.append(_t("motorbar.hermes.created",
                                 "creé su perfil «{p}» (con tu modelo, sin copiar tus "
                                 "llaves; tu Hermes personal no cambia)",
                                 "created its «{p}» profile (with your model, without "
                                 "copying your keys; your personal Hermes doesn't "
                                 "change)", p=_profile()))
    soul = os.path.join(d, "SOUL.md")
    cur = _read_text(soul)
    if cur != SOUL_TEXT:
        _write_atomic(soul, SOUL_TEXT)
        if not created and cur is not None and cur not in _SOUL_PREVIOUS:
            avisos.append("restauré el SOUL.md neutral del perfil (la identidad la "
                          "pone el cerebro)")
    cfgp = os.path.join(d, "config.yaml")
    for key, leaf in _BRAIN_SETTINGS:
        if _setting_off(_read_text(cfgp), leaf):
            continue
        r = _run(_base(exe) + ["config", "set", key, "false"], runner=runner, timeout=60)
        if getattr(r, "returncode", 1) != 0:
            return False, "no pude asegurar %s=false en el perfil %s" % (key, _profile())
        if not created:
            avisos.append("restauré %s=false (la memoria del agente vive en su "
                          "cerebro)" % leaf)
    if not _client_env_ok(_read_text(cfgp)):
        # un renglón del config.yaml, a mano y en su lugar (como la lista
        # global): los `config set` de después re-vuelcan el YAML y la conservan
        new = _with_client_env(_read_text(cfgp) or "")
        if new is not None:
            _write_atomic(cfgp, new)
        if not _client_env_ok(_read_text(cfgp)):
            # No bloquea: sin esto, una nota puede caer en otra pestaña; se
            # reintenta en cada arranque (el camino rápido no pasa).
            avisos.append(_t("motorbar.hermes.client_env",
                             "no pude darle a cada pestaña de Hermes su propia memoria "
                             "(terminal.{k} en el perfil «{p}»): con varias pestañas abiertas, "
                             "una nota podría guardarse en otra",
                             "couldn't give each Hermes tab its own memory (terminal.{k} in "
                             "the «{p}» profile): with several tabs open, a note could be "
                             "saved in another one", k=_CLIENT_ENV_KEY, p=_profile()))
    def _apagar_en_todas():
        """Discord y las demás plataformas del gateway (Telegram, Slack,
        WhatsApp…): la lista global, un renglón del config.yaml, sin llamar al
        CLI. Va DESPUÉS de la lista de la terminal (con la global puesta,
        `tools list` ya dice «apagada» y la de la terminal, que `-z` necesita,
        no se escribiría) y ANTES de la de Discord, que con ella ya no hace
        falta. Los `config set`/`tools disable` de después re-vuelcan el YAML y
        la conservan (es una clave explícita para Hermes)."""
        text = _read_text(cfgp) or ""
        if _global_off_ok(text):
            return
        new = _with_global_off(text)
        if new is None:
            avisos.append(_t("motorbar.hermes.platforms_leak",
                             "no pude apagar {tool} en las plataformas de mensajería de Hermes "
                             "(la sección agent: del perfil tiene una forma que no edito): un "
                             "bot de Telegram, Slack u otra conectado al perfil «{p}» podría "
                             "leer las conversaciones de tus otros agentes; agrega {tool} y "
                             "memory a agent.disabled_toolsets en {cfg}",
                             "couldn't turn off {tool} on Hermes' messaging platforms (the "
                             "profile's agent: section has a shape I don't edit): a Telegram, "
                             "Slack or other bot connected to the «{p}» profile could read your "
                             "other agents' conversations; add {tool} and memory to "
                             "agent.disabled_toolsets in {cfg}",
                             tool=_LEAK_TOOL, p=_profile(), cfg=cfgp))
        else:
            _write_atomic(cfgp, new)
            if not created:
                avisos.append(_t("motorbar.hermes.platforms_off",
                                 "apagué {tools} de Hermes en Discord, Telegram, Slack, "
                                 "WhatsApp y sus demás plataformas (un bot conectado al perfil "
                                 "compartido podía leer las conversaciones de todos tus "
                                 "agentes)",
                                 "turned off Hermes' {tools} on Discord, Telegram, Slack, "
                                 "WhatsApp and its other platforms (a bot connected to the "
                                 "shared profile could read all your agents' conversations)",
                                 tools=", ".join(_TOOLSETS_OFF)))
    global_hecho = []
    for plat in _TOOLS_PLATFORMS:
        if plat != "cli" and not global_hecho:
            global_hecho.append(True)          # una vez, antes de la primera del gateway
            _apagar_en_todas()
        if _toolsets_off(_read_text(cfgp), plat):
            continue
        # Nuestro lector del YAML es conservador (lo que no reconoce cuenta como
        # encendido); la FUENTE OFICIAL decide: `tools list` da el estado ya
        # resuelto por Hermes. Solo se apaga lo que Hermes dice encendido, y se
        # verifica por el estado (config, luego CLI), nunca por el código de
        # salida. Sin respuesta reconocible del CLI, todo cuenta como encendido.
        # Cada plataforma se re-asegura igual en cada arranque: un perfil ya
        # preparado gana la de Discord la próxima vez que se abre un agente.
        extra = _platform_args(plat)
        st = _cli_tools_state(exe, runner, plat)
        pending = [t for t in _TOOLSETS_OFF if st.get(t) is not False]
        if not pending:
            continue
        _run(_base(exe) + ["tools", "disable"] + pending + extra, runner=runner, timeout=60)
        if _LEAK_TOOL in pending and _tool_on(_read_text(cfgp), _LEAK_TOOL, plat):
            # Si las dos juntas fallan (p. ej. Hermes renombró `memory`).
            _run(_base(exe) + ["tools", "disable", _LEAK_TOOL] + extra,
                 runner=runner, timeout=60)
        still = [t for t in pending if _tool_on(_read_text(cfgp), t, plat)]
        if still:
            st = _cli_tools_state(exe, runner, plat)
            still = [t for t in still if st.get(t) is not False]
        if plat != "cli":
            # Discord: la fuga es del bot que el gateway conecte al perfil, no
            # de esta terminal (no abrirla no la cerraría): aviso de una línea
            # con el comando a mano, y se reintenta en el próximo arranque.
            if _LEAK_TOOL in still:
                avisos.append(_t("motorbar.hermes.discord_leak",
                                 "no pude apagar {tool} en Discord: un bot de Discord "
                                 "conectado al perfil «{p}» podría leer las conversaciones "
                                 "de tus otros agentes; córrelo a mano: hermes --profile {p} "
                                 "tools disable --platform {plat} {tool}",
                                 "couldn't turn off {tool} in Discord: a Discord bot "
                                 "connected to the «{p}» profile could read your other "
                                 "agents' conversations; run it by hand: hermes --profile "
                                 "{p} tools disable --platform {plat} {tool}",
                                 tool=_LEAK_TOOL, p=_profile(), plat=plat))
            elif still:
                avisos.append(_t("motorbar.hermes.discord_still",
                                 "no pude apagar {tools} en Discord (no guarda nada: la "
                                 "memoria de Hermes está apagada)",
                                 "couldn't turn off {tools} in Discord (it saves nothing: "
                                 "Hermes' memory is off)", tools=", ".join(still)))
            elif not created:
                avisos.append(_t("motorbar.hermes.discord_off",
                                 "apagué en Discord {tools} de Hermes (un bot conectado al "
                                 "perfil compartido podía leer las conversaciones de todos "
                                 "tus agentes)",
                                 "turned off Hermes' {tools} in Discord (a bot connected to "
                                 "the shared profile could read all your agents' "
                                 "conversations)", tools=", ".join(pending)))
            continue
        if _LEAK_TOOL in still:
            return False, ("no pude apagar %s en el perfil «%s» de Hermes y con ella "
                           "un agente leería las conversaciones de otro; córrelo a "
                           "mano: hermes --profile %s tools disable %s"
                           % (_LEAK_TOOL, _profile(), _profile(), _LEAK_TOOL))
        if still:
            avisos.append("no pude apagar %s en el perfil (no guarda nada: la "
                          "memoria de Hermes está apagada)" % ", ".join(still))
        elif not created:
            avisos.append("apagué %s de Hermes en el perfil (lo comparten todos "
                          "los agentes; la historia de cada uno vive en su "
                          "cerebro)" % " y ".join(pending))
    if not global_hecho:
        _apagar_en_todas()
    if _context_chars(_read_text(cfgp)) < CONTEXT_FILE_CHARS:
        r = _run(_base(exe) + ["config", "set", "context_file_max_chars",
                               str(CONTEXT_FILE_CHARS)], runner=runner, timeout=60)
        if getattr(r, "returncode", 1) != 0:
            avisos.append("no pude fijar context_file_max_chars=%d: Hermes puede "
                          "recortar la identidad incrustada" % CONTEXT_FILE_CHARS)
        elif not created:
            avisos.append("fijé context_file_max_chars=%d (para que la identidad "
                          "incrustada llegue completa)" % CONTEXT_FILE_CHARS)
    text = _read_text(cfgp) or ""
    state = _hooks_state(text)
    if state == "foreign":
        avisos.append("el perfil tiene hooks propios: el tono por turno no se cablea "
                      "(llega al arrancar)")
    elif state != "ours":
        # «stale» = el mismo hook re-escrito por Hermes (su `config set`
        # re-vuelca el YAML) o con otra ruta de Workspace: se repone sin
        # aviso (no es un ajuste del socio; la aprobación va por comando).
        # En su lugar: lo del socio en `hooks:` (webhooks, su output_spill)
        # se queda.
        new = _with_hook(text)
        if new is None:
            avisos.append("el perfil tiene una sección hooks: que no edito: el tono por "
                          "turno no se cablea (llega al arrancar)")
        else:
            _write_atomic(cfgp, new)
    # Al bloque de Workspace le falta el tope de su contexto (perfiles de
    # antes de la 0.5.1, o un output_spill del socio sin max_chars): solo ese
    # renglón, sin aviso.
    new = _spill_fix(_read_text(cfgp) or "")
    if new is not None:
        _write_atomic(cfgp, new)
    # Skills del cerebro: al final, después de todo `config set` (re-vuelca el
    # YAML). La forma en que Hermes la vuelve a escribir se reconoce sola.
    text = _read_text(cfgp) or ""
    if not _skills_ok(text):
        new = _with_skills(text)
        if new is None:
            avisos.append(_t("motorbar.hermes.skills_foreign",
                             "el perfil tiene una sección skills: que no edito: las skills de "
                             "tu cerebro no se conectan",
                             "the profile has a skills: section I don't edit: your brain's "
                             "skills aren't connected"))
        else:
            antes = _skills_parse(text)
            # un perfil de la 0.5.0 solo no tenía dónde guardar las nuevas
            solo_create = (SKILLS_DIR in (antes["dirs"] or [])
                           and (antes["nudge"] or "").strip() == str(SKILLS_NUDGE))
            _write_atomic(cfgp, new)
            if not created and solo_create:
                avisos.append(_t("motorbar.hermes.skills_create",
                                 "las skills que Hermes aprenda ahora se guardan en tu cerebro "
                                 "(skills/aprendidas/), donde las ven tus otros motores",
                                 "the skills Hermes learns are now saved in your brain "
                                 "(skills/aprendidas/), where your other engines see them"))
            elif not created:
                avisos.append(_t("motorbar.hermes.skills",
                                 "conecté las skills de tu cerebro; las que Hermes aprenda se "
                                 "guardan en él (skills/aprendidas/), no en su perfil compartido",
                                 "connected your brain's skills; the ones Hermes learns are "
                                 "saved in it (skills/aprendidas/), not in its shared profile"))
    return True, ("Hermes: " + "; ".join(avisos)) if avisos else ""


def hook_state():
    """(¿cableado?, ¿aprobado por el socio?) del hook de Workspace en el
    perfil. Solo lee archivos del perfil propio (su allowlist de hooks)."""
    d = profile_dir()
    wired = _hooks_state(_read_text(os.path.join(d, "config.yaml"))) == "ours"
    try:
        data = json.loads(_read_text(os.path.join(d, "shell-hooks-allowlist.json")) or "{}")
        cmd = _hook_command()
        ok = any(isinstance(e, dict) and e.get("event") == _HOOK_EVENT
                 and e.get("command") == cmd for e in data.get("approvals") or [])
    except (ValueError, AttributeError):
        ok = False
    return wired, ok


def prepare_account():
    """Antes del botón «cuenta y proveedor»: el setup oficial corre DENTRO del
    perfil propio, que tiene que existir. (ok, aviso)."""
    return ensure_profile()


# ── perfil PROPIO por agente (sistema nuevo · cable-hermes, 19-nov) ────────
#: Hermes guarda sus avisos (`hooks:`), sus servidores MCP (`mcp_servers:`) y sus carpetas de skills
#: (`skills:`) en el config.yaml del PERFIL (HERMES_HOME): no hay bandera ni archivo del proyecto para una
#: sola sesión (su doc de configuración y de perfiles). Y desde la 0.22.5 todas sus sesiones (el REPL, `chat
#: -q` y su ACP) corren en el gateway multiplexado (`hermes gateway status`: «running via the default-profile
#: multiplexer»): ahí corren los avisos y el MCP del perfil, con el entorno de quien arrancó ese gateway (caja
#: negra 19-nov: llevaba WORKSPACE_BRAIN/WS de OTRA pestaña) y expandiendo ${VAR} contra el .env del perfil,
#: no contra la pestaña (por eso el `${WORKSPACE_BRAIN}/skills` del perfil compartido no llegaba a la página).
#:
#: La vía oficial para separar es un perfil: Workspace usa uno PROPIO por agente (`workspace-<agente>`),
#: creado con `hermes profile create … --clone-from workspace --no-alias` (hereda el proveedor que el socio
#: conectó en el perfil de Workspace: Hermes copia su .env, Workspace jamás lo lee), con rutas ABSOLUTAS de su
#: cerebro. Aditivo: los perfiles del socio (default y los suyos) no se tocan, y el de Workspace solo se lee
#: como base. Se quita al desinstalar (uninstall: copia aparte + `hermes profile delete`). De paso, cada
#: agente tiene su propia historia: la búsqueda de sesiones ya no ve las de otro agente.
#:
#: Lo único que Workspace escribe en él: `hooks:` (los del paquete + el de tono de hoy), `skills:`,
#: `mcp_servers.workspace` y su carpeta `workspace-paquete/` (el lanzador de los avisos y del MCP, FIJO por
#: perfil: Hermes guarda la aprobación por comando, así que actualizar Workspace no la vuelve a pedir, y
#: perfil.json: el cerebro y la raíz de Workspace, que el aviso lee en vez del entorno del gateway).
#:
#: Los avisos esperan la aprobación del socio: Hermes solo la pide en `hermes chat` en primer plano (su
#: ACP, `-q` y el gateway nunca preguntan). Workspace no la salta: sin --accept-hooks, HERMES_ACCEPT_HOOKS
#: ni hooks_auto_accept en este camino.
PERFIL_AGENTE = "workspace-"
CARPETA_PAQUETE = "workspace-paquete"
_PERFIL_JSON = "perfil.json"
#: Las variables de pestaña que el gateway arrastra de quien lo arrancó: un aviso o el MCP del perfil
#: nunca las toman como suyas.
_DE_PESTANA_GATEWAY = ("WORKSPACE_BRAIN", "WORKSPACE_WS", "WORKSPACE_WID", "ZENITH_WS", "WORKSPACE_ENGINE",
                       "WORKSPACE_SESSION_ENGINE", "WORKSPACE_AGENT_NAME", "WORKSPACE_VIA", "WORKSPACE_SESSION_ID",
                       "WORKSPACE_SESSION_PID", "WORKSPACE_HERMES_RUN", "WORKSPACE_HERMES_SESSION",
                       "WORKSPACE_NUCLEO_AL_ABRIR", "WORKSPACE_TONO_SISTEMA", "WORKSPACE_PAQUETE_HOOKS",
                       _PERFIL_AGENTE_ENV)
#: Una corrida del perfil sin sesión todavía la reclama el primer aviso de una sesión nueva de ese perfil
#: durante este tiempo (la corrida sin pantalla de la auditoría; el REPL ya se reconoce por su miga).
_RECLAMO_S = 30 * 60
#: El aviso de antes de una herramienta del MCP dice de qué pestaña es la llamada que sigue.
_MCP_RECIENTE_S = 120


def _slug_agente(nombre):
    s = re.sub(r"[^a-z0-9]+", "-", str(nombre or "").strip().lower()).strip("-")[:40].strip("-")
    return s or "agente"


def _marca_perfil(perfil):
    try:
        datos = json.loads(_read_text(os.path.join(_paquete_de(perfil), _PERFIL_JSON)) or "{}")
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def _es_dueno_perfil(perfil, agente, marca):
    return (marca.get("de") == "workspace" and marca.get("motor") == "hermes"
            and marca.get("perfil") == perfil and marca.get("agente") == agente)


def perfil_de_agente(agente):
    """El perfil de Hermes del agente. Manda el que ya es SUYO por su marca (el de huella, el de su nombre o el
    anterior, con el nombre convertido); una carpeta sin marca válida nunca gana sobre él (revisor 1: una creación a
    medias tapaba el perfil anterior). Si ninguno es suyo: su nombre, si es válido y no choca con el anterior de otro
    agente; si no, uno con la huella de su nombre."""
    import hashlib

    nombre = str(agente or "")
    slug = _slug_agente(nombre)
    anterior = PERFIL_AGENTE + slug
    huella = hashlib.sha256(nombre.encode("utf-8")).hexdigest()[:16]
    alterno = PERFIL_AGENTE + "_" + huella + "-" + slug[:22]
    valido = re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", nombre)
    directo = PERFIL_AGENTE + nombre if valido else ""
    for perfil in dict.fromkeys(p for p in (alterno, directo, anterior) if p):
        if _es_dueno_perfil(perfil, agente, _marca_perfil(perfil)):
            return perfil
    marca = _marca_perfil(anterior)
    otro = marca.get("agente")
    legado_ajeno = (isinstance(otro, str) and otro != agente and _slug_agente(otro) == slug
                    and _es_dueno_perfil(anterior, otro, marca))
    return directo if directo and not (legado_ajeno and nombre == slug) else alterno


def nombre_agente(cerebro, env=None):
    """El agente de `cerebro`: el que dice la pestaña (WORKSPACE_AGENT_NAME de `env`), el del registro de
    agentes con ese cerebro, o el nombre de su carpeta."""
    n = str((env or {}).get("WORKSPACE_AGENT_NAME") or "").strip()
    if n:
        return n.lower()
    real = os.path.realpath(str(cerebro or ""))
    try:
        import dispatch
        for a in (dispatch.load_registry() or {}).get("agents") or ():
            b = a.get("brain") or ""
            if b and a.get("name") and os.path.realpath(b) == real:
                return str(a["name"]).lower()
    except Exception:
        pass
    return os.path.basename(real).lower()


def carpeta_perfil(perfil):
    return os.path.join(_hermes_root(), "profiles", perfil)


def _paquete_de(perfil):
    return os.path.join(carpeta_perfil(perfil), CARPETA_PAQUETE)


def es_perfil_de_agente(perfil):
    """¿`perfil` es un perfil de agente de Workspace (lo creó Workspace: trae su carpeta y su perfil.json)?"""
    return (str(perfil or "").startswith(PERFIL_AGENTE)
            and os.path.isfile(os.path.join(_paquete_de(perfil), _PERFIL_JSON)))


def perfiles_de_agente():
    """Los perfiles de agente de Workspace en esta máquina (solo los que llevan su marca)."""
    d = os.path.join(_hermes_root(), "profiles")
    try:
        return sorted(n for n in os.listdir(d) if es_perfil_de_agente(n))
    except OSError:
        return []


@__import__("contextlib").contextmanager
def _en_perfil(perfil):
    """Lo de dentro corre con `_profile()` = `perfil` ('' = el de Workspace)."""
    antes = os.environ.get(_PERFIL_AGENTE_ENV)
    if perfil:
        os.environ[_PERFIL_AGENTE_ENV] = perfil
    else:
        os.environ.pop(_PERFIL_AGENTE_ENV, None)
    try:
        yield
    finally:
        if antes is None:
            os.environ.pop(_PERFIL_AGENTE_ENV, None)
        else:
            os.environ[_PERFIL_AGENTE_ENV] = antes


def _cmd(*partes):
    """Un comando como Hermes lo parte (shlex, sin shell), con «/» (en Windows shlex se come las «\\»)."""
    return " ".join(shlex.quote(str(p).replace("\\", "/")) for p in partes)


#: El momento de un aviso de Workspace («… hook.py hermes <momento>»): una palabra.
_MOMENTO = re.compile(r"^[a-z][a-z_]{0,40}$")


def _mismo_python(py):
    """¿`py` es el Python de Workspace (el de este proceso, el que escribe los avisos)? La misma ruta, o un enlace a
    él."""
    a, b = str(py or "").replace("\\", "/"), (sys.executable or "").replace("\\", "/")
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except (OSError, ValueError):
        return False


def es_aviso_de_workspace(cmd, lanzador):
    """¿`cmd` es EXACTAMENTE un aviso de Workspace hacia el lanzador fijo `lanzador` de un perfil? Solo
    «<python de Workspace> <lanzador>/hook.py hermes <momento>», como lo escribe `_avisos_del_paquete` (`_cmd`):
    cuatro partes (shlex, como lo parte Hermes), el intérprete y el script exactos, nada antes ni después. Lo que
    solo CONTIENE la ruta del lanzador no cuenta: con esto se decide qué se aprueba sin preguntar."""
    c = str(cmd or "")
    try:
        partes = shlex.split(c)
    except ValueError:
        return False
    if len(partes) != 4:
        return False
    py, script, destino, momento = partes
    hook = str(lanzador or "").replace("\\", "/").rstrip("/") + "/hook.py"
    return (script == hook and destino == "hermes" and bool(_MOMENTO.match(momento)) and _mismo_python(py)
            and c == _cmd(py, script, destino, momento))


def avisos_de_workspace(perfil):
    """[(evento, comando)] de los avisos de Workspace en el config.yaml de `perfil` que se pueden aprobar sin
    preguntar: los exactos hacia su lanzador fijo (es_aviso_de_workspace) y su aviso de tono (`_hook_command`)."""
    cfg = _read_text(os.path.join(carpeta_perfil(perfil), "config.yaml")) or ""
    lanz = os.path.join(_paquete_de(perfil), "lanzador")
    tono = _hook_command()
    avisos, ev = [], None
    for ln in cfg.splitlines():
        m = re.match(r"^  ([A-Za-z_]+):\s*$", ln)
        if m:
            ev = m.group(1)
            continue
        m = re.match(r'^  - command: (".*")\s*$', ln)
        if not (m and ev):
            continue
        try:
            cmd = json.loads(m.group(1))
        except ValueError:
            continue
        if es_aviso_de_workspace(cmd, lanz) or (ev == _HOOK_EVENT and cmd == tono):
            avisos.append((ev, cmd))
    return avisos


def _avisos_del_paquete(paquete_dir, lanzador):
    """[(evento, comando, tope)] del hooks.yaml que generó el paquete (arquitectura/generar: los eventos de la
    ficha), con el lanzador FIJO del perfil en lugar de la carpeta de la versión."""
    texto = _read_text(os.path.join(paquete_dir, "hermes", "hooks.yaml")) or ""
    out, ev = [], None
    for ln in texto.splitlines():
        m = re.match(r'^  "([^"]+)":\s*$', ln)
        if m:
            ev = m.group(1)
            continue
        m = re.match(r'^    - command: (".*")\s*$', ln)
        if m and ev:
            cmd = json.loads(m.group(1))
            momento = cmd.rsplit(" ", 1)[-1]
            out.append([ev, _cmd(sys.executable or "python3", os.path.join(lanzador, "hook.py"), "hermes", momento),
                        10])
            continue
        m = re.match(r'^      timeout: (\d+)\s*$', ln)
        if m and out:
            out[-1][2] = min(int(m.group(1)), 300)          # Hermes topa en 300 s
    return [tuple(x) for x in out]


def _bloque_avisos(avisos, spill=HOOK_SPILL_CHARS):
    """El `hooks:` del perfil del agente: el de tono de hoy (hermes_turno, antes que los del paquete en su
    pre_llm_call) y los del paquete, con el tope de contexto del hook (output_spill)."""
    por = {}
    por.setdefault(_HOOK_EVENT, []).append((_hook_command(), _HOOK_TIMEOUT))
    for ev, cmd, tope in avisos:
        por.setdefault(ev, []).append((cmd, tope))
    filas = ["hooks:"]
    for ev, lst in por.items():
        filas.append("  %s:" % ev)
        for cmd, tope in lst:
            filas += ["  - command: %s" % json.dumps(cmd), "    timeout: %d" % tope]
    filas += ["  output_spill:", "    max_chars: %d" % spill]
    return "\n".join(filas) + "\n"


def _bloque_skills(paquete_dir, cerebro):
    return ("skills:\n  external_dirs:\n    - %s\n  create_dir: %s\n  creation_nudge_interval: %d\n"
            % (json.dumps(os.path.join(paquete_dir, "skills").replace("\\", "/")),
               json.dumps(os.path.join(os.path.realpath(cerebro), "skills", "aprendidas").replace("\\", "/")),
               SKILLS_NUDGE))


def _hijo_mcp(perfil, lanzador, raiz):
    """mcp_servers.workspace del perfil: el MCP núcleo por el lanzador fijo del perfil. Sin cerebro ni pestaña
    en su entorno (el gateway lo abre UNA vez por perfil): cada llamada los saca de la corrida viva del perfil
    (pestana_para_mcp). trust: full = su servidor propio, preaprobado como en los demás motores."""
    return ("  workspace:\n    command: %s\n    args:\n      - %s\n    env:\n      WORKSPACE_ROOT: %s\n"
            "      WORKSPACE_ENGINE: \"hermes\"\n      WORKSPACE_HERMES_PERFIL: %s\n    trust: full\n"
            % (json.dumps((sys.executable or "python3").replace("\\", "/")),
               json.dumps(os.path.join(lanzador, "mcp.py").replace("\\", "/")),
               json.dumps(raiz.replace("\\", "/")), json.dumps(perfil)))


def _poner_raiz(texto, clave, bloque):
    """config.yaml con la clave de primer nivel `clave` = `bloque` (la de antes, fuera; si no estaba, al final)."""
    lines = texto.splitlines(True)
    span = _top_span(lines, clave)
    if span is None:
        base = texto if not texto or texto.endswith("\n") else texto + "\n"
        return base + bloque
    i, j, _en_linea = span
    return "".join(lines[:i]) + bloque + "".join(lines[j:])


def _poner_mcp(texto, hijo):
    """config.yaml con `mcp_servers.workspace` = `hijo`; los demás servidores del perfil se quedan."""
    lines = texto.splitlines(True)
    span = _top_span(lines, "mcp_servers")
    if span is None or span[2]:
        return _poner_raiz(texto, "mcp_servers", "mcp_servers:\n" + hijo) if span is None else None
    i, j, _x = span
    cuerpo, k = [], i + 1
    while k < j:
        if re.match(r"^  workspace:\s*$", lines[k].rstrip("\r\n")):
            k += 1
            while k < j and (not lines[k].strip() or lines[k].startswith("    ")):
                k += 1
            continue
        cuerpo.append(lines[k])
        k += 1
    while cuerpo and not cuerpo[-1].strip():
        cuerpo.pop()
    return "".join(lines[:i]) + "mcp_servers:\n" + "".join(cuerpo) + hijo + "".join(lines[j:])


def _copiar_lanzador(paquete_dir, destino):
    """El lanzador de esta versión del paquete a la carpeta FIJA del perfil (archivo por archivo, atómico y solo
    si cambió: un aviso que arranca justo entonces nunca encuentra un hueco)."""
    src = os.path.join(paquete_dir, "lanzador")
    os.makedirs(destino, exist_ok=True)
    for f in sorted(os.listdir(src)):
        if not f.endswith(".py"):
            continue
        with open(os.path.join(src, f), "rb") as fh:
            nuevo = fh.read()
        fin = os.path.join(destino, f)
        try:
            with open(fin, "rb") as fh:
                if fh.read() == nuevo:
                    continue
        except OSError:
            pass
        tmp = "%s.%d.tmp" % (fin, os.getpid())
        with open(tmp, "wb") as fh:
            fh.write(nuevo)
        os.replace(tmp, fin)


def confianza_perfil(perfil, avisos=None):
    """'lista' si Hermes ya tiene aprobados TODOS los avisos de Workspace del perfil (su lista de aprobados,
    <perfil>/shell-hooks-allowlist.json: un archivo de estado del perfil propio, sin llaves), 'falta' si no.
    `avisos`: [(evento, comando)]; por defecto, los que hoy tiene su config.yaml hacia el lanzador fijo."""
    d = carpeta_perfil(perfil)
    if avisos is None:
        cfg = _read_text(os.path.join(d, "config.yaml")) or ""
        lanz = os.path.join(_paquete_de(perfil), "lanzador").replace("\\", "/")
        avisos, ev = [], None
        for ln in cfg.splitlines():
            m = re.match(r"^  ([A-Za-z_]+):\s*$", ln)
            if m:
                ev = m.group(1)
                continue
            m = re.match(r'^  - command: (".*")\s*$', ln)
            if m and ev and lanz in m.group(1).replace("\\\\", "/"):
                avisos.append((ev, json.loads(m.group(1))))
    try:
        data = json.loads(_read_text(os.path.join(d, "shell-hooks-allowlist.json")) or "{}")
        ok = {(e.get("event"), e.get("command")) for e in data.get("approvals") or [] if isinstance(e, dict)}
    except (ValueError, AttributeError):
        ok = set()
    falta = [a for a in avisos if tuple(a) not in ok]
    return ("falta" if falta or not avisos else "lista"), len(falta)


#: Claves del bloque `model:` que se pueden copiar del perfil de Workspace al de un agente (sin secretos: una línea
#: con llave, token, secreto, contraseña o auth jamás se copia).
_SECRETO = re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|auth|credential)")


def _bloque_modelo(texto):
    """El bloque `model:` de un config.yaml SIN ninguna línea que pueda llevar un secreto, o '' si no hay."""
    lines = (texto or "").splitlines(True)
    span = _top_span(lines, "model")
    if span is None or span[2]:
        return ""
    i, j, _x = span
    cuerpo = [ln for ln in lines[i + 1:j] if ln.strip() and not _SECRETO.search(ln)]
    return ("model:\n" + "".join(cuerpo)) if cuerpo else ""


def _iso(ts):
    import datetime as _dt
    return _dt.datetime.fromtimestamp(float(ts), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _script_de(cmd):
    """El script de un comando de aviso («<python> <script> …»), para la fecha que Hermes guarda al aprobar."""
    try:
        partes = shlex.split(cmd)
    except ValueError:
        return ""
    return partes[1] if len(partes) > 1 else ""


def _es_nuestro_aprobado(cmd, lanzador):
    """¿Una entrada de la lista de aprobados es de Workspace (su lanzador en ESTE perfil o su aviso de tono)?"""
    c = str(cmd or "").replace("\\", "/")
    return lanzador.replace("\\", "/") in c or c.rstrip().endswith("hooks/hermes_turno.py")


def aprobar_avisos(perfil, avisos):
    """Workspace aprueba SUS avisos en SU perfil de agente, por la vía oficial más estrecha de Hermes: «Manual
    allowlisting» (su doc de hooks: entradas {event, command} en el arreglo `approvals` de
    <perfil>/shell-hooks-allowlist.json, «useful for non-TTY or service-account deployments»; «The command string
    must match the configured hook command exactly»). Solo en un perfil con la marca de Workspace; solo las entradas
    de `avisos` [(evento, comando)]; las suyas de antes (otro Python, otra ruta) se reemplazan y lo demás de la lista
    se queda. Nunca --accept-hooks, HERMES_ACCEPT_HOOKS ni hooks_auto_accept (aceptan todo lo del perfil). Decisión del
    dueño (19-nov): Workspace puede aprobar solo lo suyo en su propio perfil por agente. → cuántas escribió."""
    if not es_perfil_de_agente(perfil):
        return 0
    d = carpeta_perfil(perfil)
    lanz = os.path.join(_paquete_de(perfil), "lanzador")
    ruta = os.path.join(d, "shell-hooks-allowlist.json")
    texto = _read_text(ruta)
    try:
        data = json.loads(texto) if texto and texto.strip() else {}
    except ValueError:
        return 0                                  # una lista que no se entiende no se pisa
    if not isinstance(data, dict) or not isinstance(data.get("approvals", []), list):
        return 0
    actuales = [e for e in data.get("approvals", []) if isinstance(e, dict)]
    quieren = [(str(ev), str(cmd)) for ev, cmd in avisos]
    if {(e.get("event"), e.get("command")) for e in actuales if _es_nuestro_aprobado(e.get("command"), lanz)} \
            == set(quieren):
        return 0                                  # ya están, y solo esas
    otros = [e for e in actuales if not _es_nuestro_aprobado(e.get("command"), lanz)]
    ahora = _iso(time.time())
    nuevos = []
    for ev, cmd in quieren:
        e = {"approved_at": ahora, "command": cmd, "event": ev}
        script = _script_de(cmd)
        try:
            e["script_mtime_at_approval"] = _iso(os.path.getmtime(script))
        except (OSError, ValueError):
            pass
        nuevos.append(e)
    data["approvals"] = otros + nuevos
    _write_atomic(ruta, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass
    return len(nuevos)


def _marca(perfil, datos):
    jp = os.path.join(_paquete_de(perfil), _PERFIL_JSON)
    os.makedirs(os.path.dirname(jp), exist_ok=True)
    if _read_text(jp) != json.dumps(datos, ensure_ascii=False, indent=1):
        _write_atomic(jp, json.dumps(datos, ensure_ascii=False, indent=1))


# ── la creación de un perfil de agente, de punta a punta (revisor 1) ─────────
# `hermes profile create` y la marca (perfil.json) son dos pasos: si la creación se corta entre ellos (tope, ventana
# cerrada, reinicio), queda una carpeta sin marca que nadie distingue de un perfil ajeno. Antes de crear, Workspace
# anota en SU estado qué perfil va a crear y para qué agente; con esa nota, la carpeta a medias es suya: se aparta (no
# se borra) y se vuelve a crear con el mecanismo oficial. Sin la nota, una carpeta sin marca sigue sin tocarse.
def _creacion_pendiente_ruta(perfil):
    return os.path.join(os.path.dirname(_runs_path()) or ".", "hermes-creando", perfil + ".json")


def _carpeta_incompletos():
    """Donde quedan apartados los perfiles que Workspace empezó a crear y no terminó."""
    return os.path.join(os.path.dirname(_runs_path()) or ".", "hermes-perfiles-incompletos")


def _anotar_creacion(perfil, agente):
    ruta = _creacion_pendiente_ruta(perfil)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    _write_atomic(ruta, json.dumps({"perfil": perfil, "agente": agente, "t": time.time()}, ensure_ascii=False))


def _creacion_pendiente(perfil, agente):
    try:
        d = json.loads(_read_text(_creacion_pendiente_ruta(perfil)) or "{}")
    except ValueError:
        return False
    return isinstance(d, dict) and d.get("perfil") == perfil and d.get("agente") == agente


def _quitar_creacion(perfil):
    try:
        os.remove(_creacion_pendiente_ruta(perfil))
    except FileNotFoundError:
        pass


def _apartar_incompleto(perfil):
    """Mueve la carpeta a medias de `perfil` al estado de Workspace (sin borrar nada). → dónde quedó."""
    import shutil
    os.makedirs(_carpeta_incompletos(), exist_ok=True)
    destino = os.path.join(_carpeta_incompletos(), "%s-%d-%s" % (perfil, int(time.time()), uuid.uuid4().hex[:6]))
    shutil.move(carpeta_perfil(perfil), destino)
    return destino


def asegurar_perfil_agente(cerebro, agente, paquete_dir, exe=None, runner=None, esperar=True):
    """(perfil, info): el perfil PROPIO del agente, al día. `esperar=False`: no espera a que su gateway abra un MCP
    nuevo; queda en info["mcp_desde"] para quien llama (cmd_acp: solo si el perfil tiene cuenta).
    Si falta, se crea con el mecanismo oficial SIN clonar
    (`hermes profile create <p> --no-alias`: no copia llaves; decisión del dueño, 19-nov: Workspace no copia ni guarda
    llaves) y se le pone una vez lo del cerebro que lleva el perfil de Workspace (SOUL neutral, memoria y búsqueda de
    sesiones apagadas, tope del archivo de contexto: el mismo ensure_profile) y el bloque `model:` del perfil de
    Workspace sin una sola línea con secreto (el proveedor que el socio eligió para Workspace; su cuenta, la pone él
    con la guía: cuenta_de_perfil). En cada apertura: su lanzador fijo, perfil.json, en su config.yaml `hooks:`,
    `skills:` y `mcp_servers.workspace` (solo si cambian: el gateway relee el archivo) y la aprobación de SUS avisos
    (aprobar_avisos). El perfil de Workspace se crea antes solo si no existe; el que ya está no se toca. Levanta si
    no se puede (quien llama abre como hoy) o si ya hay un perfil con ese nombre que no es de Workspace."""
    exe = exe or _exe()
    if not exe:
        raise RuntimeError("hermes no está en PATH")
    perfil = perfil_de_agente(agente)
    d = carpeta_perfil(perfil)
    info = {"perfil": perfil, "agente": agente, "creado": False}
    raiz = _ROOT
    datos = {"de": "workspace", "motor": "hermes", "perfil": perfil, "agente": agente,
             "cerebro": os.path.realpath(str(cerebro)), "raiz": raiz.replace("\\", "/"),
             "python": (sys.executable or "python3").replace("\\", "/")}
    import olock
    with olock.file_lock(_profile_lock() + "-" + perfil, timeout=180):
        previo = {}
        if es_perfil_de_agente(perfil):
            previo = _marca_perfil(perfil)
            if not _es_dueno_perfil(perfil, agente, previo):
                raise RuntimeError("el perfil de Hermes «%s» pertenece a otro agente o su marca es inválida" % perfil)
            _quitar_creacion(perfil)              # la nota de una creación que sí terminó
        else:
            if os.path.isdir(d) and os.listdir(d):
                if not _creacion_pendiente(perfil, agente):
                    raise RuntimeError("ya hay un perfil de Hermes «%s» que no es de Workspace: no se toca" % perfil)
                info["apartado"] = _apartar_incompleto(perfil)     # lo dejó a medias Workspace: se rehace
            _anotar_creacion(perfil, agente)
            r = _run([exe, "profile", "create", perfil, "--no-alias"], runner=runner, timeout=240)
            if getattr(r, "returncode", 1) != 0 or not os.path.isdir(d):
                err = ((getattr(r, "stderr", "") or "") + (getattr(r, "stdout", "") or "")).strip()
                raise RuntimeError("no pude crear el perfil %s de Hermes: %s" % (perfil, err[-200:] or "rc=%s"
                                                                                % getattr(r, "returncode", "?")))
            _marca(perfil, datos)                 # suyo desde ya: si lo de abajo falla, se reintenta
            _quitar_creacion(perfil)
            info["creado"] = True
        if not previo.get("listo"):
            # lo del cerebro, una vez (después, los ajustes de este perfil son del socio)
            base = _read_text(os.path.join(carpeta_perfil(_perfil_base()), "config.yaml")) or ""
            modelo = _bloque_modelo(base)
            if modelo:
                cfg_p0 = os.path.join(d, "config.yaml")
                _write_atomic(cfg_p0, _poner_raiz(_read_text(cfg_p0) or "", "model", modelo))
            with _en_perfil(perfil):
                ok, why = _ensure_locked(exe, runner)
            if not ok:
                raise RuntimeError(why or "no pude preparar el perfil %s" % perfil)
        paq = _paquete_de(perfil)
        lanz = os.path.join(paq, "lanzador")
        _copiar_lanzador(paquete_dir, lanz)
        _marca(perfil, dict(datos, listo=True))
        cfg_p = os.path.join(d, "config.yaml")
        antes = _read_text(cfg_p) or ""
        avisos = _avisos_del_paquete(paquete_dir, lanz)
        cfg = _poner_raiz(antes, "hooks", _bloque_avisos(avisos, max(_spill_chars(antes), HOOK_SPILL_CHARS)))
        cfg = _poner_raiz(cfg, "skills", _bloque_skills(paquete_dir, cerebro))
        hijo = _hijo_mcp(perfil, lanz, raiz)
        cfg = _poner_mcp(cfg, hijo) or cfg
        if cfg != antes:
            _write_atomic(cfg_p, cfg)
        escrito = time.time() - 1 if hijo not in antes else None
        todos = [(ev, cmd) for ev, cmd, _t in avisos] + [(_HOOK_EVENT, _hook_command())]
        info["aprobados"] = aprobar_avisos(perfil, todos)
        info["confianza"], info["faltan"] = confianza_perfil(perfil, todos)
    if escrito is not None and not esperar:
        info["mcp_desde"] = escrito
    elif escrito is not None:                # su MCP es nuevo o cambió: que su gateway lo abra antes de la sesión
        info["mcp_listo"] = _esperar_mcp(perfil, escrito)
    return perfil, info


#: Lo que se espera a que el gateway abra el MCP de un perfil recién escrito (lo hace solo al ver el config.yaml, en
#: menos de un minuto según su doc y la caja negra del 19-nov; una sesión que empieza antes no lo trae: auditoría
#: real, «ningún servidor MCP workspace conectado»; lo abrió ~1 min después). Solo pasa al crear el perfil o al
#: cambiar su MCP.
_ESPERA_MCP_S = 75


def _esperar_mcp(perfil, desde, tope=None, leer=None):
    """¿El gateway ya abrió el MCP de `perfil` (su `initialize` en el diagnóstico del núcleo desde `desde`)? Espera
    hasta `tope` s; falla-suave (False)."""
    tope = _ESPERA_MCP_S if tope is None else tope
    try:
        if leer is None:
            from arquitectura import salud
            leer = salud.leer_diagnostico
        fin = time.time() + tope
        while True:
            if any(d.get("evento") == "initialize" and d.get("perfil") == perfil for d in leer(desde) or ()):
                return True
            if time.time() >= fin:
                return False
            time.sleep(0.5)
    except Exception:
        return False


def _con_perfil_en_argv(argv, perfil):
    """El argv con `--profile <perfil>` justo tras el binario: sin otro perfil ni --accept-hooks (en este camino la
    aprobación de los avisos es del socio, en su terminal)."""
    out, saltar = [], False
    for i, a in enumerate(argv):
        if saltar:
            saltar = False
            continue
        if i and a in ("--profile", "-p") and i + 1 < len(argv):
            saltar = True
            continue
        if i and (a.startswith("--profile=") or a == "--accept-hooks"):
            continue
        out.append(a)
    return out[:1] + ["--profile", perfil] + out[1:]


def sesion_perfil(cerebro, pestana, argv, env, valores, ficha=None):
    """La vía del sistema nuevo (ficha · sesion.preparar): el perfil del agente al día y el argv con él; la
    corrida de la pestaña anotada con su perfil (la abre el lanzador de hoy; si no, una aquí: la auditoría). →
    (argv, env, info). Levanta si el perfil no se puede (sesion.para_lanzar abre como hoy)."""
    env = dict(env)
    agente = nombre_agente(cerebro, env)
    exe = argv[0] if argv and os.path.isabs(str(argv[0])) else _exe()
    perfil, info = asegurar_perfil_agente(cerebro, agente, valores["paquete"], exe=exe)
    argv = _con_perfil_en_argv(list(argv), perfil)
    env[_PERFIL_AGENTE_ENV] = perfil
    for k in ("HERMES_ACCEPT_HOOKS", "HERMES_HOME"):
        env.pop(k, None)
    ws = str(env.get("WORKSPACE_WS") or pestana or "")
    wid = str(env.get("WORKSPACE_WID") or pestana or "")
    run = str(env.get("WORKSPACE_HERMES_RUN") or "")
    if run and run_info(run):
        _run_poner(run, perfil=perfil, wid=wid)
    elif pestana:
        retoma = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a in ("--resume", "-r")]
        _cerrar_corridas_mias(perfil)
        run = run_open(cerebro, tab=ws, agent=agente, known=retoma, exe=exe or "", perfil=perfil, wid=wid)
        if run:
            env["WORKSPACE_HERMES_RUN"] = run
    info["corrida"] = bool(run)
    return argv, env, info


def _run_poner(token, **campos):
    def fn(runs):
        for r in runs:
            if r.get("id") == token:
                r.update({k: str(v) for k, v in campos.items() if v})
    try:
        _runs_update(fn)
    except Exception:
        pass


def _cerrar_corridas_mias(perfil):
    """Las corridas de ESTE proceso en ese perfil que siguen abiertas (una corrida sin pantalla anterior: la
    auditoría abre varias en el mismo proceso) se cierran: la nueva es la única viva del proceso."""
    now = time.time()

    def fn(runs):
        for r in runs:
            if r.get("perfil") == perfil and r.get("pid") == os.getpid() and r.get("t1") is None:
                r["t1"] = now
    try:
        _runs_update(fn)
    except Exception:
        pass


def _vivas_del_perfil(perfil, now=None):
    now = now or time.time()
    return [r for r in _runs_load() if r.get("perfil") == perfil and _run_viva(r, now)]


def _de_corrida(r):
    return {"brain": r.get("brain") or "", "ws": r.get("tab") or "", "wid": r.get("wid") or r.get("tab") or "",
            "agente": r.get("agent") or "", "run": r.get("id") or ""}


def pestana_de_sesion(sid, perfil, reclamar=False, now=None):
    """{brain, ws, wid, agente, run} de la pestaña dueña de la sesión `sid` del perfil del agente, o None. Sin
    mirar el entorno (en el gateway es el de otra pestaña). En orden: la corrida viva del perfil que ya la
    tiene; la evidencia de la terminal (dueno_de_sesion: su miga, su registro oficial); y, con `reclamar` (el
    primer aviso de una sesión nueva), la ÚNICA corrida viva del perfil que todavía no tiene sesión y abrió
    hace menos de _RECLAMO_S (la corrida sin pantalla). Nunca adivina entre dos."""
    if not _valid_sid(sid) or not perfil:
        return None
    now = now or time.time()
    vivas = _vivas_del_perfil(perfil, now)
    con = [r for r in vivas if sid in (r.get("sessions") or [])]
    if len(con) == 1:
        return _de_corrida(con[0])
    if not vivas:
        return None
    try:
        with _en_perfil(perfil):
            run = dueno_de_sesion(sid, gateway=True).get("run") or ""
    except Exception:
        run = ""
    r = next((x for x in vivas if x.get("id") == run), None)
    if r is not None:
        return _de_corrida(r)
    if reclamar:
        libres = [x for x in vivas if not (x.get("sessions") or [])
                  and now - float(x.get("t0") or 0) <= _RECLAMO_S]
        if len(libres) == 1:
            run_claim(libres[0]["id"], sid)
            return _de_corrida(libres[0])
    return None


def entorno_de_aviso(payload, perfil_json, momento, env=None):
    """(entorno, anotar) para el lanzador de un aviso del perfil del agente (arquitectura/paquete/lanzador/hook.py):
    el entorno SIN la pestaña que arrastra el gateway, con la raíz de Workspace y el cerebro de perfil.json y, si
    se sabe, la pestaña dueña de la sesión. anotar=False: la página (su ACP: los eventos ya los anota la capa de
    control) o una sesión sin dueña (mejor nada que lo ajeno)."""
    base = {k: v for k, v in (os.environ if env is None else env).items() if k not in _DE_PESTANA_GATEWAY}
    p = payload if isinstance(payload, dict) else {}
    extra = p.get("extra") if isinstance(p.get("extra"), dict) else {}
    perfil = str(p.get("profile") or perfil_json.get("perfil") or "")
    base.update(WORKSPACE_ROOT=str(perfil_json.get("raiz") or ""), WORKSPACE_ENGINE="hermes",
                WORKSPACE_BRAIN=str(perfil_json.get("cerebro") or ""), WORKSPACE_HERMES_PROFILE=perfil)
    sid = str(p.get("session_id") or extra.get("task_id") or "")
    # la página (su ACP): por la plataforma del evento o, en los de herramienta (no la traen; caja negra 19-nov), por
    # su sesión, que la página anotó al abrirla
    if str(extra.get("platform") or "").lower() == "acp" or _de_pagina(perfil, sid):
        base["WORKSPACE_VIA"] = "pagina"
        _aviso_de_pagina(perfil, sid, momento)
        return base, False
    dueno = pestana_de_sesion(sid, perfil, reclamar=momento in ("session_start", "user_prompt"))
    if not dueno:
        return base, False
    herramienta = str(p.get("tool_name") or "")
    if momento == "pre_tool" and herramienta.startswith("mcp__workspace__") and dueno.get("run"):
        _marcar_mcp_terminal(dueno["run"], herramienta)
    base.update(WORKSPACE_BRAIN=dueno["brain"], WORKSPACE_WS=dueno["ws"], WORKSPACE_WID=dueno["wid"])
    if dueno.get("agente"):
        base["WORKSPACE_AGENT_NAME"] = dueno["agente"]
    return base, True


#: Lo que el MCP del perfil espera la prueba de una llamada de la página (su ACP la avisa por su lado, casi a la vez).
_MCP_ESPERA_PAGINA_S = 3.0
#: Un turno de la página que lleva más que esto «a media respuesta» es de una sesión que se cortó sin avisar: no cuenta.
_PAGINA_TURNO_MAX_S = 15 * 60


def _paginas_path():
    import paths as _paths
    return os.path.join(_paths.state_dir(os.path.expanduser("~")), "hermes-paginas.json")


def _paginas_update(fn):
    """El registro de las sesiones de la PÁGINA en perfiles de agente (aparte del de las corridas de la terminal:
    su atado y su respaldo no las ven)."""
    from olock import file_lock
    path = _paginas_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with file_lock(path, timeout=5):
        regs = _runs_load(path)
        out = fn(regs)
        _write_atomic(path, json.dumps({"version": 1, "runs": regs}, ensure_ascii=False))
        return out


def pagina_abrio(perfil, cerebro, ws, wid, agente="", sid=""):
    """cable-hermes: la página abrió una sesión ACP en el perfil del agente → token (o ''). La usa el MCP del perfil
    para saber de qué pestaña es una llamada que viene de la página."""
    token, now = uuid.uuid4().hex, time.time()
    try:
        import pending_runs
        marca = pending_runs._proc_mark()
    except Exception:
        marca = None

    def fn(regs):
        keep = []
        for r in regs:
            if r.get("t1") is None and not _run_viva(r, now):
                r["t1"] = now                  # la página que la abrió ya no está
            if r.get("t1") is not None and now - float(r["t1"]) > 3600:
                continue
            keep.append(r)
        regs[:] = keep
        rec = {"id": token, "via": "pagina", "perfil": str(perfil), "brain": os.path.realpath(str(cerebro)),
               "tab": str(ws or ""), "wid": str(wid or ws or ""), "agent": str(agente or ""), "pid": os.getpid(),
               "t0": now, "t1": None, "sessions": [str(sid)] if sid else [], "turno": None, "mcp": "", "mcp_t": 0}
        if isinstance(marca, dict):
            rec["proc"] = marca
        regs.append(rec)
    try:
        _paginas_update(fn)
        return token
    except Exception:
        return ""


def pagina_marcar(token, **campos):
    """Lo que la página va sabiendo de su sesión: `turno` (epoch o None), `mcp` (la herramienta del MCP que empieza),
    `sid`, `cerrar=True`. Nunca levanta."""
    if not token:
        return

    def fn(regs):
        for r in regs:
            if r.get("id") != token:
                continue
            if campos.get("cerrar"):
                r["t1"] = time.time()
            if "turno" in campos:
                r["turno"] = campos["turno"]
            if campos.get("mcp"):
                r["mcp"], r["mcp_t"] = str(campos["mcp"]), time.time()
            if campos.get("sid") and campos["sid"] not in (r.get("sessions") or []):
                r.setdefault("sessions", []).append(str(campos["sid"]))
    try:
        _paginas_update(fn)
    except Exception:
        pass


def _aviso_de_pagina(perfil, sid, momento):
    """Un aviso del perfil que corrió en una sesión de la PÁGINA (su ACP): no se anota en el registro (la página ya
    anota ese momento desde ACP), solo se cuenta en su sesión (la prueba de que, por ejemplo, el de antes de cada
    herramienta corrió ahí y negaría lo prohibido). Nunca levanta."""
    if not sid or not perfil:
        return

    def fn(regs):
        for r in regs:
            if r.get("perfil") == perfil and sid in (r.get("sessions") or []) and r.get("t1") is None:
                cuenta = r.setdefault("avisos", {})
                cuenta[momento] = int(cuenta.get(momento) or 0) + 1
    try:
        _paginas_update(fn)
    except Exception:
        pass


def _de_pagina(perfil, sid):
    """¿`sid` es de una sesión de la página en ese perfil (la anotó su conector ACP al abrirla)?"""
    if not sid or not perfil:
        return False
    return any(r.get("perfil") == perfil and sid in (r.get("sessions") or []) for r in _runs_load(_paginas_path()))


def avisos_de_pagina(token):
    """{momento: veces} que los avisos del perfil corrieron en esa sesión de la página (o {})."""
    for r in _runs_load(_paginas_path()) if token else ():
        if r.get("id") == token:
            return dict(r.get("avisos") or {})
    return {}


def _marcar_mcp_terminal(token, herramienta):
    """El aviso de antes de la herramienta (aprobado por el socio) dice que la llamada al MCP que sigue es de ESTA
    corrida de la terminal."""
    def fn(runs):
        for r in runs:
            if r.get("id") == token:
                r["mcp"], r["mcp_t"] = str(herramienta), time.time()
    try:
        _runs_update(fn)
    except Exception:
        pass


def _decidir_mcp(perfil, nombre, ahora, puede_esperar):
    """Una vuelta de pestana_para_mcp, con los DOS registros tomados (corridas de la terminal y sesiones de la página):
    se lee, se decide y se gastan las marcas sin que otra llegue en medio (revisor 2). → (corrida elegida o None,
    ¿esperar otra vuelta?)."""
    from olock import file_lock
    rp, pp = _runs_path(), _paginas_path()
    for p in (rp, pp):
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with file_lock(rp, timeout=5), file_lock(pp, timeout=5):
        runs, pags = _runs_load(rp), _runs_load(pp)
        terminal = [r for r in runs if r.get("perfil") == perfil and _run_viva(r, ahora)]
        paginas = [r for r in pags if r.get("perfil") == perfil and r.get("t1") is None and _run_viva(r, ahora)]

        def con_prueba(r):
            return r.get("mcp") == nombre and ahora - float(r.get("mcp_t") or 0) <= _MCP_RECIENTE_S

        pruebas = [r for r in terminal + paginas if con_prueba(r)]
        en_turno = [r for r in paginas if r.get("turno") and ahora - float(r["turno"]) <= _PAGINA_TURNO_MAX_S]
        # la marca de la página llega por su ACP, por su lado: la de otra corrida no decide mientras una página a
        # media respuesta todavía puede traer la suya
        decide = len(pruebas) > 1 or (pruebas and not (puede_esperar and any(not con_prueba(r) for r in en_turno)))
        if decide:
            # cada prueba se usa una vez; las de una llamada ambigua también (si no, dejaban sin pestaña a las
            # llamadas siguientes de esas corridas hasta _MCP_RECIENTE_S)
            gastadas = {id(r) for r in pruebas}
            for r in pruebas:
                r["mcp"], r["mcp_t"] = "", 0
            for path, regs in ((rp, runs), (pp, pags)):
                if any(id(r) in gastadas for r in regs):
                    _write_atomic(path, json.dumps({"version": 1, "runs": regs}, ensure_ascii=False))
            return (pruebas[0] if len(pruebas) == 1 else None), False
        if en_turno and puede_esperar:
            return None, True
        cand = terminal + en_turno
        return (cand[0] if len(cand) == 1 else None), False


def pestana_para_mcp(perfil, herramienta, now=None, espera=None):
    """{WORKSPACE_BRAIN, WORKSPACE_WS, WORKSPACE_WID, WORKSPACE_ENGINE, WORKSPACE_VIA?…} de la pestaña que llama a
    `herramienta` del MCP del perfil del agente, o {}. Ese MCP lo abre el gateway UNA vez por perfil y lo comparten su
    terminal y su página (su ACP), sin pestaña en su entorno. En orden, sin adivinar nunca:
      1. la prueba de ESTA llamada: el aviso de antes de la herramienta en la terminal (si el socio lo aprobó) o el
         tool_call de la página (su ACP), con esa herramienta y de hace menos de _MCP_RECIENTE_S. Con una página a
         media respuesta sin su marca, se espera hasta `espera` a que llegue antes de decidir. Si hay más de una
         marca la llamada es ambigua (ninguna, y las marcas se gastan);
      2. si no hay prueba: la ÚNICA corrida viva del perfil (una terminal, o una página a media respuesta).
    Si no se pueden tomar los registros: ninguna."""
    nombre = "mcp__workspace__" + str(herramienta or "")
    espera = _MCP_ESPERA_PAGINA_S if espera is None else espera
    fin = time.time() + espera
    while True:
        try:
            elegida, seguir = _decidir_mcp(perfil, nombre, now or time.time(), now is None and time.time() < fin)
        except Exception:
            return {}
        if not seguir:
            break
        time.sleep(0.15)
    if elegida is None:
        return {}
    d = _de_corrida(elegida)
    out = {"WORKSPACE_BRAIN": d["brain"], "WORKSPACE_WS": d["ws"], "WORKSPACE_WID": d["wid"],
           "WORKSPACE_ENGINE": "hermes"}
    if d["agente"]:
        out["WORKSPACE_AGENT_NAME"] = d["agente"]
    if elegida.get("via") == "pagina":
        out["WORKSPACE_VIA"] = "pagina"
    return out


def comando_cuenta(perfil, exe=None):
    """El selector OFICIAL de proveedor, llave y modelo de Hermes para ESE perfil (`hermes --profile <p> model`, el
    mismo de Motores › cuenta y proveedor): Workspace no copia ni guarda llaves, guía a la persona."""
    return [exe or BINARY, "--profile", perfil, "model"]


#: Lo que se recuerda de `hermes -p <perfil> status` (el estado de su cuenta, sin llaves), hasta que cambie su .env o su
#: auth.json (solo su fecha y tamaño: jamás su contenido).
_CUENTAS = {}
_CUENTA_TTL = 600


def _huella_cuenta(perfil):
    d = carpeta_perfil(perfil)
    out = []
    for f in (".env", "auth.json", "config.yaml"):
        try:
            st = os.stat(os.path.join(d, f))
            out.append((f, st.st_size, st.st_mtime_ns))
        except OSError:
            out.append((f, None, None))
    return tuple(out)


def cuenta_de_perfil(perfil, exe=None, runner=None, now=None):
    """{perfil, lista: True/False/None, detalle, comando}: ¿el perfil del agente tiene cuenta con su proveedor? Por
    `hermes -p <perfil> status` (✓/✗ por proveedor, sin llaves), recordado hasta que cambie su cuenta. None = no se
    pudo saber. `comando` = la guía oficial para conectarla."""
    now = now or time.time()
    h = _huella_cuenta(perfil)
    ya = _CUENTAS.get(perfil)
    if ya and ya[0] == h and now - ya[1] <= _CUENTA_TTL:
        return dict(ya[2])
    with _en_perfil(perfil):
        st = status(exe_override=exe, runner=runner)
        lista = None if st.get("session_active") is None else not _missing_provider(st)
        if lista is None:
            # su `status` dice «custom» cuando el modelo trae base_url (caja negra 19-nov: el de OpenRouter de
            # Workspace): se mira el proveedor de SU config contra sus ✓/✗, sin llaves
            prov = _config_model_provider(_read_text(os.path.join(carpeta_perfil(perfil), "config.yaml")) or "")
            if prov:
                rep = status_report(exe=exe or _exe(), runner=runner) or {}
                filas = [(label.lower(), ok) for rows in (rep.get("sections") or {}).values() for label, ok in rows]
                suyas = [ok for label, ok in filas if label.replace(" ", "") == prov.replace(" ", "")
                         or label.split(" /")[0].replace(" ", "") == prov.replace(" ", "")]
                if suyas:
                    lista = any(suyas)
                    if not lista:
                        st = dict(st, detail=_t("motorbar.hermes.perfil_sin_llave",
                                                "el perfil «{p}» no tiene la cuenta de {prov} (Workspace no copia "
                                                "llaves)", "the «{p}» profile has no {prov} account (Workspace "
                                                "doesn't copy keys)", p=perfil, prov=prov))
    out = {"perfil": perfil, "lista": lista, "detalle": str(st.get("detail") or ""),
           "comando": comando_cuenta(perfil, BINARY)}
    _CUENTAS[perfil] = (h, now, dict(out))
    return out


def perfiles_sin_cuenta(exe=None, runner=None):
    """Los perfiles de agente de Workspace en Hermes que todavía no tienen cuenta (Motores y Conexiones los listan)."""
    out = []
    for p in perfiles_de_agente():
        try:
            c = cuenta_de_perfil(p, exe=exe, runner=runner)
        except Exception:
            continue
        if c.get("lista") is False:
            out.append(c)
    return out


def _aviso_pestana_movida(brain, tab, perfil, sid_viejo):
    """cable-hermes: la primera vez que una pestaña de antes abre en el perfil propio de su agente, su conversación
    de antes no está ahí: una línea, una sola vez por pestaña (state: hermes-pestanas-movidas.json)."""
    clave = "%s|%s" % (os.path.realpath(str(brain or "")), tab[1] if isinstance(tab, (list, tuple)) else tab)
    ruta = os.path.join(os.path.dirname(_runs_path()) or ".", "hermes-pestanas-movidas.json")
    try:
        vistas = json.loads(_read_text(ruta) or "{}")
        if not isinstance(vistas, dict):
            vistas = {}
    except ValueError:
        vistas = {}
    if clave in vistas:
        return False
    print(_t("motorbar.hermes.pestana_movida",
             "WORKSPACE: esta pestaña empieza una conversación nueva en el perfil propio de este agente ({p}); la "
             "de antes sigue en el perfil compartido de Workspace, y la memoria de la pestaña sigue igual.",
             "WORKSPACE: this tab starts a new conversation in this agent's own profile ({p}); the previous one "
             "stays in Workspace's shared profile, and the tab's memory is unchanged.", p=perfil))
    vistas[clave] = {"t": time.time(), "antes": str(sid_viejo or "")}
    try:
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        _write_atomic(ruta, json.dumps(vistas, ensure_ascii=False))
    except OSError:
        pass
    return True


def cmd_acp(cerebro, agente, paquete_dir):
    """El comando ACP de la página para este agente: su perfil propio (el de su terminal: mismas skills y
    avisos). Levanta si el perfil no se puede o si todavía no tiene cuenta (la página usa el de Workspace, como
    antes, mientras Motores y Conexiones guían a conectarla)."""
    perfil, info = asegurar_perfil_agente(cerebro, agente or nombre_agente(cerebro), paquete_dir, esperar=False)
    if cuenta_de_perfil(perfil).get("lista") is False:
        # sin esperar a su MCP (hasta 75 s): este perfil no se usa (portón del primer mensaje, PC, 23-nov)
        raise RuntimeError("el perfil %s todavía no tiene cuenta" % perfil)
    if info.get("mcp_desde") is not None:
        info["mcp_listo"] = _esperar_mcp(perfil, info["mcp_desde"])
    return [BINARY, "--profile", perfil, "acp"]


def account_menu(active=None, exe=None):
    """«cuenta y proveedor» en Motores (engines_tui._account y la página): con perfiles de agente, uno por perfil
    (primero los que no tienen cuenta), cada uno con el selector oficial de ESE perfil (`hermes --profile <p> model`:
    proveedor, llave y modelo; Workspace no copia ni guarda llaves). Sin perfiles de agente: None (el de siempre)."""
    perfiles = perfiles_de_agente()
    if not perfiles:
        return None
    sin = {c["perfil"] for c in perfiles_sin_cuenta()}
    orden = sorted(perfiles, key=lambda p: (p not in sin, p))
    return {"account": " ".join(comando_cuenta("<perfil>", BINARY)), "model": "/model",
            "actions": [(p, comando_cuenta(p, exe or BINARY)) for p in orden]
            + [(_perfil_base(), comando_cuenta(_perfil_base(), exe or BINARY))]}


# ── corridas: qué pestaña es dueña de cada sesión nueva ────────────────────
#: Hermes crea la sesión con el primer mensaje y no acepta un id propio: al
#: cerrar, la sesión «nueva» de un cerebro puede ser de OTRA pestaña abierta en
#: él. Cada launch registra su corrida (cerebro, ventana de tiempo) y el hook
#: por turno anota qué sesiones vio esa corrida. Una sesión anotada por otra
#: corrida jamás se ata ni se respalda aquí; una sin anotar nacida mientras
#: otra corrida sin anotaciones estaba abierta es ambigua (no se adivina).
_RUN_TTL = 7 * 86400
_RUN_UNKNOWN_PID_TTL = 12 * 3600


def _runs_path():
    override = os.environ.get("WORKSPACE_HERMES_RUNS", "").strip()
    if override:
        return override
    import paths as _paths
    return os.path.join(_paths.state_dir(os.path.expanduser("~")), "hermes-runs.json")


def _runs_load(path=None):
    try:
        with open(path or _runs_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        runs = d.get("runs") if isinstance(d, dict) else None
        return [r for r in runs if isinstance(r, dict)] if isinstance(runs, list) else []
    except (OSError, ValueError):
        return []


def _runs_update(fn):
    from olock import file_lock
    path = _runs_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with file_lock(path, timeout=5):
        runs = _runs_load(path)
        fn(runs)
        _write_atomic(path, json.dumps({"version": 1, "runs": runs}, ensure_ascii=False))


def _pid_alive(pid):
    try:
        from olock import _pid_alive as alive
        return alive(pid)
    except Exception:
        return None


def run_open(brain, tab="", mem=None, larga=None, agent="", known=(), exe="", perfil="", wid=""):
    """Registra una corrida de Hermes en este cerebro → token (o '' si no se
    pudo: falla-suave, la captura vuelve al criterio de ventana). `mem` =
    {'desde': epoch, 'doc': huella o None}: desde cuándo lo que anote el
    agente es suyo y la huella de la memoria que quedó en el AGENTS.md (None
    si no quedó); lo usa el hook por turno (memoria_turno). `larga` =
    {'modo': 'hook'|'doc', 'tope': caracteres}: quién entrega STATE/MEMORY.md
    (el hook por turno o la copia del AGENTS.md) y el tope del contexto del
    hook en el perfil (memoria_larga_turno). Lo que el hook necesita para
    saber de quién es una sesión sin leer el entorno (run_de_sesion): el
    agente (su tono), la terminal (la miga de Hermes) y, ya anotada, la
    sesión que la pestaña retoma (`known`); `exe` = el binario, por si el
    PATH del gateway no lo trae."""
    token = uuid.uuid4().hex
    now = time.time()
    ya = [s for s in dict.fromkeys(str(s or "") for s in known or ()) if _valid_sid(s)]
    try:
        import pending_runs
        marca = pending_runs._proc_mark()  # pid + hora de arranque (también en Windows)
    except Exception:
        marca = None

    def fn(runs):
        keep = []
        for r in runs:
            if r.get("t1") is None and not _run_viva(r, now):
                r["t1"] = now              # corrida muerta sin cierre: termina ahora
            if r.get("t1") is not None and now - float(r["t1"]) > _RUN_TTL:
                continue
            keep.append(r)
        rec = {"id": token, "brain": os.path.realpath(brain or ""), "tab": tab,
               "pid": os.getpid(), "t0": now, "t1": None, "sessions": list(ya),
               "agent": str(agent or ""), "terminal": _terminal_id(), "exe": str(exe or "")}
        if perfil:                         # cable-hermes: el perfil del agente y la pestaña de su registro
            rec["perfil"] = str(perfil)
            rec["wid"] = str(wid or tab or "")
        if isinstance(marca, dict):
            rec["proc"] = marca
        if isinstance(mem, dict) and tab:
            rec["mem"] = {"desde": float(mem.get("desde") or now), "doc": mem.get("doc"),
                          "ses": {}}
        if isinstance(larga, dict):
            rec["larga"] = {"modo": str(larga.get("modo") or ""), "tope": larga.get("tope"),
                            "ses": []}
        keep.append(rec)
        runs[:] = keep
    try:
        _runs_update(fn)
        return token
    except Exception:
        return ""


def run_claim(token, sid):
    """El hook por turno: la sesión `sid` es de la corrida `token`."""
    if not token or not _valid_sid(sid):
        return
    for r in _runs_load():
        if r.get("id") == token and sid in (r.get("sessions") or []):
            return                          # ya anotada: sin lock ni escritura

    def fn(runs):
        for r in runs:
            if r.get("id") == token:
                r.setdefault("sessions", [])
                if sid not in r["sessions"]:
                    r["sessions"].append(sid)
    _runs_update(fn)


def run_close(token):
    if not token:
        return
    now = time.time()

    def fn(runs):
        for r in runs:
            if r.get("id") == token and r.get("t1") is None:
                r["t1"] = now
    try:
        _runs_update(fn)
    except Exception:
        pass


# ── de quién es una sesión, sin el entorno (gateway compartido, v0.22.5) ───
#: Desde v0.22.5 TODA sesión corre en UN gateway por raíz de Hermes (el
#: multiplexor de `default` sirve también los perfiles con nombre; cada
#: cliente lo arranca si no hay y queda 10 min tras el último uso). El hook
#: por turno corre DENTRO de ese proceso: su entorno es el de la pestaña que
#: lo arrancó, no el de la sesión del turno (VERIFICADO 2026-10-26 con dos
#: cerebros: B recibía la memoria y la pestaña de A, y A se quedaba con la
#: sesión de B). Por eso el hook ya no lee WORKSPACE_*: la corrida sale de la
#: sesión (`session_id` de la llamada). El `cwd` de la llamada tampoco sirve:
#: es el del gateway.
#: Identidad de la terminal como la calcula Hermes para su miga de `-c`
#: (hermes_cli/terminal_breadcrumbs.py, v0.22.5): el tty (stdin, luego
#: stdout) o, sin tty, la primera de estas variables.
_TERMINAL_VARS = ("ZELLIJ_PANE_ID", "TMUX_PANE", "KITTY_WINDOW_ID", "WEZTERM_PANE",
                  "TERM_SESSION_ID", "WT_SESSION")


def _miga_segura(raw):
    return re.sub(r"[^A-Za-z0-9._-]", "-", str(raw).strip().strip("/"))[:120]


def _terminal_id():
    """La terminal de ESTA pestaña con el nombre que Hermes da a su miga
    (`tty-dev-ttys008`), o ''. El REPL hereda la terminal del lanzador."""
    for fh in (sys.stdin, sys.stdout):
        try:
            name = os.ttyname(fh.fileno())
        except Exception:
            continue
        if name:
            return "tty-" + _miga_segura(name)
    for var in _TERMINAL_VARS:
        val = os.environ.get(var)
        if val:
            return "%s-%s" % (var.lower(), _miga_segura(val))
    return ""


def _miga(terminal, desde=0.0, con_hora=False):
    """Sesión de esa terminal según la miga de Hermes
    (`<perfil>/terminal-sessions/<terminal>`, la de `hermes -c`), o ''.
    VERIFICADO v0.22.5: Hermes la escribe al arrancar el REPL (también con
    `--resume`) y cuando la compresión rota el id; NO al hacer `/resume`
    dentro del REPL (esa sesión de arranque queda con end_reason
    `resumed_other`, ver dueno_de_sesion). Con `desde`, solo una miga escrita
    desde entonces (la de una pestaña anterior en la misma terminal no
    cuenta). Sin migas (versión anterior, `session.terminal_continue: false`)
    da ''. `con_hora` → (sesión, hora de la miga)."""
    nada = ("", 0.0) if con_hora else ""
    if not terminal or terminal != _miga_segura(terminal):
        return nada
    try:
        with open(os.path.join(profile_dir(), "terminal-sessions", terminal),
                  encoding="utf-8-sig") as fh:
            d = json.load(fh)
        if not isinstance(d, dict):
            return nada
        ts = float(d.get("ts") or 0)
        if desde and ts < float(desde) - 2:
            return nada
        sid = str(d.get("session_id") or "")
        return (sid, ts) if con_hora else sid
    except (OSError, ValueError, TypeError):
        return nada


def _run_viva(r, now=None):
    """¿La corrida sigue abierta? Sin cierre y con su lanzador vivo: con la
    huella del proceso (pid + hora de arranque, también en Windows, donde
    olock no sabe) y, en corridas de antes, con el pid; un pid que no se
    puede mirar vale hasta _RUN_UNKNOWN_PID_TTL."""
    if r.get("t1") is not None:
        return False
    if isinstance(r.get("proc"), dict) and r["proc"].get("pid") == r.get("pid"):
        try:
            import pending_runs
            return bool(pending_runs.proc_alive({"proc": r["proc"]}))
        except Exception:
            pass
    alive = _pid_alive(r.get("pid"))
    if alive is None:
        try:
            return (now or time.time()) - float(r.get("t0") or 0) <= _RUN_UNKNOWN_PID_TTL
        except (TypeError, ValueError):
            return False
    return bool(alive)


def en_gateway():
    """¿Este proceso corre dentro de un gateway de Hermes? El que arranca un
    cliente (v0.22.5) lleva HERMES_GATEWAY_DETACHED=1 y todo gateway pone
    HERMES_EXEC_ASK=1 al arrancar (gateway/run_bootstrap.py), también el que
    corre como servicio. Hasta v0.22.2 el hook corría en el REPL de su pestaña."""
    return (os.environ.get("HERMES_GATEWAY_DETACHED", "").strip() == "1"
            or os.environ.get("HERMES_EXEC_ASK", "").strip() == "1")


#: «No resuelta» por sesión: sin esto cada turno de una sesión headless o
#: ajena volvía a exportarla (~0,5 s). Vale mientras no se abra ni cierre una
#: pestaña (la firma = las corridas vivas) y como mucho _SIN_DUENO_TTL; una
#: sesión de terminal sin dueña, solo _SIN_DUENO_TTL_TERMINAL (una pestaña
#: puede retomarla con `/resume` sin abrir ni cerrar nada), y lo mismo si el
#: export falló (es transitorio).
_SIN_DUENO_TTL = 600
_SIN_DUENO_TTL_TERMINAL = 60
_SIN_DUENO_MAX = 500


def _sin_dueno_path():
    return os.path.join(os.path.dirname(_runs_path()) or ".", "hermes-sin-dueno.json")


def _firma(vivas):
    return ",".join(sorted(str(r.get("id") or "") for r in vivas))


def _sin_dueno_leer(sid, firma, now):
    try:
        with open(_sin_dueno_path(), encoding="utf-8") as fh:
            e = (json.load(fh).get("ses") or {}).get(sid)
        ttl = _SIN_DUENO_TTL_TERMINAL if (isinstance(e, dict) and e.get("terminal")) \
            else _SIN_DUENO_TTL
        if isinstance(e, dict) and e.get("firma") == firma \
                and now - float(e.get("t") or 0) <= ttl:
            return e
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return None


def _sin_dueno_anotar(sid, firma, brain, now, terminal=False):
    from olock import file_lock
    path = _sin_dueno_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with file_lock(path, timeout=5):
            try:
                with open(path, encoding="utf-8") as fh:
                    ses = dict(json.load(fh).get("ses") or {})
            except (OSError, ValueError, AttributeError, TypeError):
                ses = {}
            ses[sid] = {"firma": firma, "brain": brain, "t": now, "terminal": bool(terminal)}
            vivas = sorted(((k, v) for k, v in ses.items() if isinstance(v, dict)
                            and now - float(v.get("t") or 0) <= _SIN_DUENO_TTL),
                           key=lambda kv: float(kv[1].get("t") or 0))[-_SIN_DUENO_MAX:]
            _write_atomic(path, json.dumps({"version": 1, "ses": dict(vivas)},
                                           ensure_ascii=False))
    except Exception:
        pass


def _reanotar(token, sid, retomada=False):
    """La sesión `sid` pasa a ser de la corrida `token` y de ninguna otra: el
    cierre de cada pestaña ata lo suyo (una sesión retomada en otra pestaña
    deja de ser de la primera). `retomada`: se le atribuyó con evidencia de
    que la pestaña la retomó con `/resume` (o el hook corre en su REPL); solo
    esas cuenta el cierre como su conversación aunque naciera antes
    (session_chain)."""
    runs = _runs_load()
    # con `retomada`, `sid` tiene que quedar la ÚLTIMA: volver a una retomada
    # (K → M → K) la pasa al final (revisión nocturna, M2)
    if all((sid in (r.get("sessions") or [])) == (r.get("id") == token)
           and (not retomada or r.get("id") != token or (r.get("retomadas") or [])[-1:] == [sid])
           for r in runs):
        return                                   # ya está así: sin lock ni escritura

    def fn(runs):
        for r in runs:
            ses = [x for x in (r.get("sessions") or []) if x != sid]
            ret = [x for x in (r.get("retomadas") or []) if x != sid]
            if r.get("id") == token:
                ses.append(sid)
                if retomada:
                    ret.append(sid)
            r["sessions"] = ses
            if ret or "retomadas" in r:
                r["retomadas"] = ret
    _runs_update(fn)


#: `/resume` dentro del REPL: hasta cuánto después del cambio llega el primer
#: turno de la sesión retomada para atribuírsela a esa pestaña.
_RESUME_VENTANA = 600


def _cambio_por_resume(r, sid, nacio, now, exe=None, runner=None):
    """¿La pestaña `r` acaba de dejar su sesión con `/resume` para ir a `sid`?
    VERIFICADO v0.22.5: `/resume` dentro del REPL no reescribe la miga ni
    sella nada en la sesión retomada; la que la pestaña deja queda con
    end_reason `resumed_other`. Evidencia (todo): la sesión ACTUAL de la
    pestaña (la última que se le anotó o, sin ninguna, la de su miga) es otra
    y quedó `resumed_other` mientras la pestaña estaba abierta, hace menos de
    _RESUME_VENTANA, y `sid` ya existía entonces (se retoma lo que hay). Un
    cambio se usa una vez: atribuida la retomada, ella es la actual."""
    ses = r.get("sessions") or []
    actual = ses[-1] if ses else _miga(r.get("terminal"), desde=r.get("t0") or 0)
    if not actual or actual == sid:
        return False
    try:
        e = session_record(actual, exe=exe, runner=runner)
        cambio = float((e or {}).get("ended_at") or 0)
    except Exception:
        return False
    if not e or e.get("end_reason") != "resumed_other" or not cambio:
        return False
    return (float(r.get("t0") or 0) - 2 <= cambio <= now + 2
            and now - cambio <= _RESUME_VENTANA and 0 < nacio <= cambio)


def dueno_de_sesion(sid, exe=None, runner=None, pista="", gateway=True, cwd=""):
    """De quién es la sesión `sid` de Hermes → {'run': token de la corrida
    VIVA dueña o '', 'brain': su cerebro si se sabe}. Sin dueña, el hook solo
    manda el tono del agente de `brain` (nunca memoria de una pestaña).

    Fuera de un gateway (`gateway=False`, Hermes hasta v0.22.2) el hook corre
    en el REPL de su pestaña: la dueña es la corrida del entorno (`pista`) y
    el cerebro, su `cwd`. En un gateway (v0.22.5) el entorno es de otra
    pestaña y no cuenta; decide la evidencia, en orden:
      1. la miga de la terminal (`hermes -c`) de una corrida viva dice que
         ahí corre `sid` (también si otra pestaña la tenía; con dos, la miga
         más reciente): esa, y la sesión se re-anota a ella;
      2. la corrida viva que ya la tiene anotada (la que el hook vio antes o
         la que la pestaña retoma, anotada al abrir), si su miga no dice otra;
      3. su registro OFICIAL (`sessions export`, una vez; lo no resuelto se
         recuerda, _SIN_DUENO_TTL): solo una sesión de terminal (_tab_source);
         una continuación es de la corrida de su padre; una sesión que una
         pestaña viva de su cerebro retomó con `/resume` dentro del REPL (la
         miga no cambia), con la evidencia de _cambio_por_resume. Nada más:
         sin miga ni otra evidencia positiva no se anota, aunque sea la única
         pestaña viva del cerebro (mejor nada que lo ajeno: puede ser Hermes
         abierto a mano ahí)."""
    out = {"run": "", "brain": ""}
    if not _valid_sid(sid):
        return out
    runs = _runs_load()
    now = time.time()
    vivas = [r for r in runs if _run_viva(r, now)]
    if not gateway:
        r = next((r for r in vivas if pista and r.get("id") == pista), None)
        if r is None:
            out["brain"] = os.path.realpath(cwd) if cwd else ""
            return out
        _reanotar(r["id"], sid, retomada=True)       # el hook corre en su REPL
        out.update(run=r["id"], brain=r.get("brain") or "")
        return out
    if not vivas:
        return out                       # sin pestañas abiertas: no es de Workspace

    def miga(r):
        return _miga(r.get("terminal"), desde=r.get("t0") or 0)

    def suya(r):
        return miga(r) in ("", sid)      # su terminal no dice que corre otra sesión

    def dar(r, retomada=False):
        _reanotar(r["id"], sid, retomada=retomada)
        out.update(run=r["id"], brain=r.get("brain") or "")
        return out
    horas = {}
    for r in vivas:
        m, ts = _miga(r.get("terminal"), desde=r.get("t0") or 0, con_hora=True)
        if m == sid:
            horas[r["id"]] = ts
    por_miga = [r for r in vivas if r["id"] in horas]
    if por_miga:
        # dos terminales con la misma sesión (una la retomó con `hermes -c`
        # y la otra se fue con `/resume`, que no reescribe su miga): la más
        # reciente es la que la tiene (Hermes no deja dos dueños vivos)
        por_miga.sort(key=lambda r: horas[r["id"]])
        if len(por_miga) == 1 or horas[por_miga[-1]["id"]] > horas[por_miga[-2]["id"]]:
            return dar(por_miga[-1])
    duenas = [r for r in vivas if sid in (r.get("sessions") or []) and suya(r)]
    if len(duenas) == 1 and (not por_miga or duenas[0] in por_miga):
        return dar(duenas[0])
    firma = _firma(vivas)
    previa = _sin_dueno_leer(sid, firma, now)
    if previa is not None:
        out["brain"] = str(previa.get("brain") or "")
        return out
    exe = exe or _exe() or next((r.get("exe") for r in vivas if r.get("exe")), None)
    try:
        d = session_record(sid, exe=exe, runner=runner)
    except Exception:
        d = None
    cands, cerebro, retomada = [], "", False
    if d and _tab_source(d):
        cerebro = os.path.realpath(str(d.get("cwd"))) if d.get("cwd") else ""
        padre = str(d.get("parent_session_id") or "")
        if padre:
            # continuación (compresión): de la corrida viva de su padre
            cands = [r for r in vivas if padre in (r.get("sessions") or []) and suya(r)]
        elif cerebro:
            # Una sesión nueva de una pestaña ya se reconoce por su miga (paso
            # 1). Sin miga ni otra evidencia NO se anota, aunque sea la única
            # pestaña viva del cerebro: puede ser Hermes abierto a mano ahí.
            # Lo único más: una sesión que la pestaña retomó con `/resume`.
            try:
                nacio = float(d.get("started_at") or 0)
            except (TypeError, ValueError):
                nacio = 0.0
            cands = [r for r in vivas if r.get("brain") == cerebro
                     and _cambio_por_resume(r, sid, nacio, now, exe=exe, runner=runner)]
            retomada = True
    if len(cands) == 1:
        return dar(cands[0], retomada=retomada)
    # un export que falló (d=None) es transitorio: se recuerda poco
    _sin_dueno_anotar(sid, firma, cerebro, now, terminal=not d or _tab_source(d))
    out["brain"] = cerebro
    return out


def run_de_sesion(sid, exe=None, runner=None, pista="", gateway=True):
    """Token de la corrida viva dueña de `sid` (dueno_de_sesion), o ''."""
    return dueno_de_sesion(sid, exe=exe, runner=runner, pista=pista, gateway=gateway)["run"]


def run_info(token):
    """Registro de la corrida `token` (o {})."""
    return next((r for r in _runs_load() if r.get("id") == token), {}) if token else {}


# ── memoria de la pestaña por el hook por turno (sesión retomada) ──────────
#: Hermes guarda el system prompt al crear la sesión y lo REUSA al retomarla
#: (agent/conversation_loop.py): el bloque de la pestaña que Workspace pone en
#: AGENTS.md no le llega a una sesión retomada, y lo que otro motor anotó
#: después no lo ve. El hook `pre_llm_call` (hooks/hermes_turno.py) manda ese
#: mismo bloque en el primer turno de una sesión que no lo trae y cuando la
#: memoria cambió POR FUERA desde la última vez; nunca en todos los turnos:
#: Hermes guarda el contexto del hook en el mensaje de ese turno
#: (`api_content`) y lo reenvía en las llamadas siguientes de la sesión.
#: Tope: el tono y la memoria van juntos y Hermes «derrama» a disco el
#: contexto de un hook que pase su tope (ver HOOK_SPILL_CHARS); el paquete de
#: memoria ya se recorta a 5 000.
MEMORIA_TURNO_MAX = 6000
_MEMORIA_TURNO_CABEZA = ("[Workspace · memoria de la pestaña al día: vale más que la que trae el "
                         "arranque de esta conversación]")


def run_mem_doc(token, doc):
    """La memoria que quedó en el AGENTS.md cambió (p. ej. el contexto de
    arranque la sacó): `doc` = su huella, o None si ya no está."""
    if not token:
        return

    def fn(runs):
        for r in runs:
            if r.get("id") == token and isinstance(r.get("mem"), dict):
                r["mem"]["doc"] = doc
    try:
        _runs_update(fn)
    except Exception:
        pass


def _huella(brain, tab, desde):
    """memoria.huella de la pestaña para Hermes, o None si no se pudo leer."""
    try:
        import memoria
        return memoria.huella(brain, tab, motor="hermes", desde=desde)
    except Exception:
        return None


def _bloque_en_doc(brain):
    """El texto del bloque de pestaña que trae HOY el AGENTS.md del cerebro
    (entre las marcas WORKSPACE:SESSION), o ''."""
    try:
        from engines.codex import _SESSION_STARTS, _SESSION_ENDS
        with open(os.path.join(brain or "", "AGENTS.md"), encoding="utf-8",
                  errors="replace") as fh:
            lines = fh.read().splitlines()
    except Exception:
        return ""
    out, dentro = [], False
    for ln in lines:
        s = ln.strip()
        if not dentro and s in _SESSION_STARTS:
            dentro = True
        elif dentro and s in _SESSION_ENDS:
            break
        elif dentro:
            out.append(ln)
    return "\n".join(out).strip()


def _bloque_de_otra_ventana(brain):
    """El bloque de pestaña que trae HOY el AGENTS.md si es de otra corrida
    que sigue viva en el cerebro (es suyo), o ''. Revisión de la 0.5.1:
      · un bloque que nombra una pestaña SIN ventana viva es huérfano (lo
        dejó una ventana que ya cerró) y no se conserva: esta pestaña lo
        congelaba como «de otra ventana» (P2-1, P1-1);
      · el que se conserva lleva la línea «OJO: hay otra ventana…» aunque la
        ventana que lo escribió haya abierto sola: Hermes lo congela en el
        system prompt de ESTA pestaña, con el comando de memoria de la otra.
    Falla-suave."""
    try:
        import pending_runs
        import sessions_registry as reg
        if not brain:
            return ""
        actual = pending_runs.current()
        vivas = [r for r in pending_runs.pending(brain)
                 if r.get("run_id") != actual and pending_runs.proc_alive(r)]
        if not vivas:
            return ""
        blk = _bloque_en_doc(brain)
        m = re.search(r"PESTAÑA ACTIVA: «(.*?)»", blk)
        if m and reg._slug(m.group(1)) not in {reg._slug(r.get("tab") or "") for r in vivas}:
            return ""
        ojo = reg._otra_ventana_line()
        if blk and ojo not in blk:
            partes = blk.split("\n\n")
            at = 2 if m and len(partes) >= 2 and m.group(0) in partes[1] else 0
            blk = "\n\n".join(partes[:at] + [ojo] + partes[at:])
        return blk
    except Exception:
        return ""


def _doc_es_de(brain, tab):
    """¿El AGENTS.md trae HOY el bloque de ESTA pestaña? Hermes lo congela en
    el primer turno, no al abrir: si otra ventana del cerebro lo reescribió (o
    lo quitó) entre que esta abrió y su primer mensaje, la sesión nueva no
    recibió su memoria sino la de otra (prueba en vivo 2026-10-21, N3)."""
    import sessions_registry as reg
    return ("PESTAÑA ACTIVA: «%s»." % reg._clean_name(tab)) in _bloque_en_doc(brain)


def _mem_en_doc(inj):
    """¿El AGENTS.md quedó con el bloque de la pestaña? Una sesión NUEVA lo
    lee al crearse; una retomada, no."""
    inj = inj or {}
    if not inj.get("ok") or inj.get("session_dropped") or inj.get("blocked"):
        return False
    if inj.get("action") == "custom":
        return inj.get("session") == "appended"
    return inj.get("action") in ("created", "synced", "kept")


def _bloque_memoria(brain, tab):
    """El MISMO bloque de pestaña que va en AGENTS.md (como sesión retomada: la
    maleta trae solo lo de otro motor), con tope, y antes la pestaña de ESTA
    ventana dicha de forma explícita con el comando exacto de memoria (el
    AGENTS.md puede traer el bloque de otra ventana, N3). '' si el escáner de
    Hermes lo marcaría: tampoco va en AGENTS.md."""
    import memoria
    import sessions_registry as reg
    blk = reg.session_doc_block(brain, tab, engine="hermes", resumed=True, others=False)
    if not blk or scan_context(blk):
        return ""
    blk = "\n\n".join(p for p in (_MEMORIA_TURNO_CABEZA, memoria.linea_pestana(tab, "hermes"),
                                  blk) if p)
    if len(blk) > MEMORIA_TURNO_MAX:
        marca = "\n[… memoria recortada: el detalle está en el archivo de la pestaña …]"
        blk = blk[:MEMORIA_TURNO_MAX - len(marca)].rstrip() + marca
    return blk


def memoria_turno(token, sid, primer_turno=False):
    """El bloque de memoria de la pestaña para ESTE turno, o ''. Lo pide el hook
    por turno. Va cuando la sesión `sid` no lo tiene: la primera vez que se ve
    en esta corrida, salvo que sea nueva (`primer_turno`) y su AGENTS.md ya lo
    trajo (y lo sigue trayendo: otra ventana pudo reescribirlo antes del
    primer mensaje, N3); y cuando la memoria cambió por fuera desde la última
    vez que se le mandó. Una pestaña sin memoria recibe igual, una vez, su
    nombre y cómo guardar. Lo que el agente anotó o resumió en esta corrida no
    cuenta como cambio. La marca (una huella por sesión) vive en el registro
    de corridas, en el estado de Workspace, fuera del cerebro. Falla-suave:
    ''."""
    if not token or not _valid_sid(sid):
        return ""
    rec = next((r for r in _runs_load() if r.get("id") == token), None)
    mem = (rec or {}).get("mem")
    if not isinstance(mem, dict) or not rec.get("tab") or not rec.get("brain"):
        return ""
    import memoria
    actual = memoria.huella(rec["brain"], rec["tab"], motor="hermes",
                            desde=mem.get("desde") or rec.get("t0") or 0) or {}
    marcas = mem.get("ses") if isinstance(mem.get("ses"), dict) else {}
    previa = marcas.get(sid)
    if previa is None and primer_turno and _doc_es_de(rec["brain"], rec["tab"]):
        previa = mem.get("doc")              # sesión nueva: la memoria vino en su AGENTS.md
    if isinstance(previa, dict) and actual.get("resumen_propio"):
        actual = dict(actual, resumen=previa.get("resumen"))   # su propio resumen no es novedad
    partes = memoria.HUELLA_PARTES
    if not actual:                           # la pestaña no tiene memoria
        cambio = not isinstance(previa, dict) and sid not in marcas
    else:
        cambio = not isinstance(previa, dict) or any(actual.get(k) != previa.get(k)
                                                     for k in partes)
    texto = _bloque_memoria(rec["brain"], rec["tab"]) if cambio else ""
    if cambio or sid not in marcas:
        marca = {k: actual.get(k) for k in partes}

        def fn(runs):
            for r in runs:
                if r.get("id") == token and isinstance(r.get("mem"), dict):
                    ses = r["mem"].get("ses")
                    ses = dict(ses) if isinstance(ses, dict) else {}
                    ses[sid] = marca
                    r["mem"]["ses"] = ses
        try:
            _runs_update(fn)
        except Exception:
            pass
    return texto


# ── memoria larga del cerebro (STATE/MEMORY.md) por el hook por turno ──────
#: Hermes no la recibía (prueba en vivo 2026-10-21, 2 de 2): no hay mensaje de
#: arranque, la copia del AGENTS.md solo lleva el núcleo de identidad y el
#: hook solo mandaba el tono y la pestaña. OpenClaw la carga con su hook
#: `bootstrap-extra-files`, con 20 000 caracteres por archivo: el mismo tope.
#: Va en el primer turno de una sesión nueva, a la par que la memoria de la
#: pestaña, sin depender de que el modelo decida leer el archivo. Hermes
#: guarda el contexto del hook en el historial de la sesión y lo reenvía en
#: cada llamada, también al retomarla: mandarla de nuevo en cada reapertura
#: la acumulaba (5 reaperturas de un MEMORY.md de 20k ≈ 100k caracteres de
#: más por llamada; revisión de la 0.5.1, P2-2). Al retomar va solo si cambió
#: desde la última vez que se le mandó a ESA sesión: la huella por sesión
#: vive en el estado local de Workspace (junto al registro de corridas,
#: nunca en el cerebro) y sobrevive a la corrida.
MEMORIA_LARGA = "STATE/MEMORY.md"
MEMORIA_LARGA_MAX = 20_000
_MEMORIA_LARGA_CABEZA = ("[Workspace · memoria larga del cerebro (%s), ya cargada aquí: vale "
                         "para todas las pestañas y no hace falta leer el archivo]" % MEMORIA_LARGA)
#: Margen para lo que Hermes agrega al juntar contextos (saltos de línea).
_MEMORIA_LARGA_HOLGURA = 200
#: Con menos espacio que esto solo va el aviso de que existe (hooks del socio
#: con el tope de fábrica de Hermes).
_MEMORIA_LARGA_MIN = 1500


def _bloque_memoria_larga(brain, cabida):
    """STATE/MEMORY.md con su encabezado, sin pasar `cabida` caracteres en
    total ni MEMORIA_LARGA_MAX de cuerpo: si no cabe se queda el principio
    (cortado en un fin de línea) y una línea dice que se recortó. '' si no hay
    archivo o está vacío."""
    path = os.path.join(brain or "", *MEMORIA_LARGA.split("/"))
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            body = fh.read(1024 * 1024)
    except OSError:
        return ""
    body = body.replace("\r\n", "\n").strip()
    if not body:
        return ""
    if cabida < _MEMORIA_LARGA_MIN:
        return ("[Workspace · la memoria larga del cerebro está en %s (%d caracteres) y no cupo "
                "en este mensaje: léela antes de responder algo que dependa de ella]"
                % (MEMORIA_LARGA, len(body)))
    marca = ("\n[… %s recortada por tamaño: aquí va el principio (%%d de %d caracteres); el "
             "resto está en el archivo, léelo si lo necesitas]" % (MEMORIA_LARGA, len(body)))
    tope = min(MEMORIA_LARGA_MAX, cabida - len(_MEMORIA_LARGA_CABEZA) - len(marca) - 16)
    if len(body) > tope:
        corte = body[:tope]
        corte = (corte.rsplit("\n", 1)[0] if "\n" in corte else corte).rstrip()
        body = corte + marca % len(corte)
    return _MEMORIA_LARGA_CABEZA + "\n\n" + body


#: Huellas de STATE/MEMORY.md ya entregadas, por sesión de Hermes: cuánto se
#: guardan y cuántas como mucho (una sesión retomada después recibe la
#: memoria larga una vez más, nada peor).
_LARGA_TTL = 120 * 86400
_LARGA_MAX = 2000


def _larga_path():
    """`hermes-memoria-larga.json`, junto al registro de corridas (estado
    local de Workspace)."""
    return os.path.join(os.path.dirname(_runs_path()) or ".", "hermes-memoria-larga.json")


def _huella_larga(brain):
    """Huella de STATE/MEMORY.md del cerebro ('' si no hay o está vacío)."""
    import hashlib
    try:
        with open(os.path.join(brain or "", *MEMORIA_LARGA.split("/")), "rb") as fh:
            crudo = fh.read(1024 * 1024)
    except OSError:
        return ""
    crudo = crudo.replace(b"\r\n", b"\n").strip()
    return hashlib.sha256(crudo).hexdigest()[:32] if crudo else ""


def _larga_entregada(brain, sid):
    """La huella de STATE/MEMORY.md que se le mandó a la sesión `sid` de este
    cerebro, o None si nunca se le mandó. Falla-suave: None."""
    try:
        with open(_larga_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        e = (d.get("ses") or {}).get(sid) if isinstance(d, dict) else None
        if isinstance(e, dict) and e.get("brain") == os.path.realpath(brain or ""):
            return str(e.get("h") or "")
    except (OSError, ValueError, AttributeError):
        pass
    return None


def _larga_anotar(brain, sid, huella):
    """Anota (con candado) que la sesión `sid` ya tiene esa versión de
    STATE/MEMORY.md; poda lo viejo. Falla-suave."""
    from olock import file_lock
    path = _larga_path()
    now = time.time()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with file_lock(path, timeout=5):
            try:
                with open(path, encoding="utf-8") as fh:
                    d = json.load(fh)
                ses = d.get("ses") if isinstance(d, dict) else None
                ses = dict(ses) if isinstance(ses, dict) else {}
            except (OSError, ValueError):
                ses = {}
            ses[sid] = {"brain": os.path.realpath(brain or ""), "h": huella, "t": now}
            vivas = sorted(((k, v) for k, v in ses.items() if isinstance(v, dict)
                            and now - float(v.get("t") or 0) <= _LARGA_TTL),
                           key=lambda kv: float(kv[1].get("t") or 0))[-_LARGA_MAX:]
            _write_atomic(path, json.dumps({"version": 1, "ses": dict(vivas)},
                                           ensure_ascii=False))
    except Exception:
        pass


def memoria_larga_turno(token, sid, usado=0):
    """STATE/MEMORY.md para ESTE turno, o ''. Lo pide el hook por turno, solo
    si la corrida la entrega por el hook (larga.modo == 'hook'; si no, va en
    la copia del AGENTS.md) y cabiendo en el tope del contexto del hook junto
    con lo que ya lleva (`usado` caracteres). Se mira la primera vez que la
    corrida ve la sesión `sid`: va si a esa sesión nunca se le mandó (una
    sesión nueva) o si el archivo cambió desde la última vez que se le mandó
    (al retomarla); si no, ya la tiene en su historial y no se repite. Las
    marcas viven en el estado local de Workspace (registro de corridas y
    _larga_path). Falla-suave: ''."""
    if not token or not _valid_sid(sid):
        return ""
    rec = next((r for r in _runs_load() if r.get("id") == token), None)
    larga = (rec or {}).get("larga")
    if not isinstance(larga, dict) or larga.get("modo") != "hook" or not rec.get("brain"):
        return ""
    if sid in (larga.get("ses") or []):
        return ""
    tope = larga.get("tope")
    try:
        tope = int(tope) if tope is not None else 10 ** 9      # None = sin derrame
    except (TypeError, ValueError):
        tope = _HOOK_SPILL_DEFAULT
    huella = _huella_larga(rec["brain"])
    if _larga_entregada(rec["brain"], sid) == huella:
        texto = ""                 # ya la tiene en su historial (sesión retomada)
    else:
        texto = _bloque_memoria_larga(rec["brain"],
                                      tope - int(usado or 0) - _MEMORIA_LARGA_HOLGURA)

    def fn(runs):
        for r in runs:
            if r.get("id") == token and isinstance(r.get("larga"), dict):
                ses = [s for s in (r["larga"].get("ses") or []) if s != sid]
                r["larga"]["ses"] = ses + [sid]
    try:
        _runs_update(fn)
    except Exception:
        return ""                  # sin marca se repetiría en cada turno: mejor nada
    _larga_anotar(rec["brain"], sid, huella)
    return texto


def _owner_view(brain, token):
    """(mías, de otras corridas, ventanas de otras corridas SIN anotaciones)."""
    real = os.path.realpath(brain or "")
    mine, others, blind = set(), set(), []
    now = time.time()
    for r in _runs_load():
        if r.get("brain") != real:
            continue
        sessions = set(r.get("sessions") or [])
        if r.get("id") == token:
            mine |= sessions
            continue
        others |= sessions
        if not sessions:
            try:
                t0 = float(r.get("t0") or 0)
                t1 = float(r["t1"]) if r.get("t1") is not None else now
            except (TypeError, ValueError):
                continue
            blind.append((t0 - 2, t1 + 2))
    return mine, others, blind


# ── login / estado (sin leer credenciales) ─────────────────────────────────
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_CRED_SECTIONS = ("API Keys", "Auth Providers", "API-Key Providers")
#: Llaves de HERRAMIENTAS en «API Keys» (búsqueda web, navegador, voz…): no
#: son un proveedor de modelo, no cuentan como sesión.
_TOOL_KEYS = ("firecrawl", "tavily", "browser use", "browserbase", "fal",
              "elevenlabs", "github")


def parse_status(text):
    """Salida de `hermes status` → {'provider', 'model', 'sections':
    {sección: [(etiqueta, ✓?)]}} de las secciones de credenciales. Solo
    etiquetas y marcas: jamás guarda el resto de la línea."""
    out = {"provider": "", "model": "", "sections": {}}
    cur = None
    for raw in (text or "").splitlines():
        line = _ANSI.sub("", raw).rstrip()
        s = line.strip()
        if s and not line[:1].isspace():
            # Encabezado de sección («◆ API Keys»); sin depender del glifo,
            # que una consola sin UTF-8 puede cambiar.
            cur = re.sub(r"^[^A-Za-z]+", "", s).strip()
            if cur in _CRED_SECTIONS:
                out["sections"].setdefault(cur, [])
            continue
        if cur == "Environment":
            if s.startswith("Provider:"):
                out["provider"] = s.split(":", 1)[1].strip()
            elif s.startswith("Model:"):
                out["model"] = s.split(":", 1)[1].strip()
            continue
        if cur not in _CRED_SECTIONS or not line.startswith("  ") or line.startswith("    "):
            continue
        for mark, ok in (("✓", True), ("✗", False)):
            if mark in s:
                label = s.split(mark, 1)[0].strip()
                if label:
                    out["sections"][cur].append((label, ok))
                break
    return out


def _login_view(p):
    """(conectados, ¿el proveedor elegido aparece SIN sesión?)."""
    connected = []
    for sec, rows in (p or {}).get("sections", {}).items():
        for label, ok in rows:
            if ok and not (sec == "API Keys" and label.lower() in _TOOL_KEYS):
                connected.append(label)
    chosen = str((p or {}).get("provider") or "").lower()
    chosen_off = bool(chosen) and any(
        (not ok) and label.lower() == chosen
        for rows in (p or {}).get("sections", {}).values() for label, ok in rows)
    return connected, chosen_off


def _custom_provider(p):
    """Endpoint propio/local (base_url en su config): no aparece con ✓/✗."""
    prov = str((p or {}).get("provider") or "").lower()
    return prov.startswith("custom") or "local" in prov


def _status_run(base, runner=None):
    """`status --full` (VERIFICADO v0.22.2: `status` a secas ya solo da un
    resumen sin las secciones de credenciales); una versión que no conozca
    `--full` (v0.18.x) cae a `status`. 90 s NO cubre siempre el primer
    arranque de una raíz de datos nueva (v0.22.2 sincroniza sus dependencias:
    50-120 s medidos); vencido, status_report da None y el sync termina igual
    en segundo plano."""
    r = _run(base + ["status", "--full"], runner=runner, timeout=90)
    if getattr(r, "returncode", 1) != 0:
        err = ((getattr(r, "stderr", "") or "") + (getattr(r, "stdout", "") or "")).lower()
        if "does not exist" not in err and ("--full" in err or "unrecognized" in err
                                            or "no such option" in err):
            r = _run(base + ["status"], runner=runner, timeout=90)
    return r


def status_report(exe=None, runner=None):
    """`hermes --profile <p> status` parseado, o None si no se pudo leer.
    Si el perfil propio aún no existe (se crea al primer arranque o con
    «cuenta y proveedor»), devuelve un estado vacío con `profile_pending=True`:
    nace SIN las llaves del socio, así que el status de su Hermes personal no
    dice nada de él (antes se leía como anticipo de lo que el --clone copiaba)."""
    exe = exe or _exe()
    if not exe:
        return None
    try:
        r = _status_run(_base(exe), runner=runner)
        if getattr(r, "returncode", 1) != 0:
            err = (getattr(r, "stderr", "") or "") + (getattr(r, "stdout", "") or "")
            if "does not exist" not in err:
                return None
            return {"provider": "", "model": "", "sections": {}, "profile_pending": True}
        p = parse_status(getattr(r, "stdout", "") or "")
        if not p["sections"]:
            return None
        p["profile_pending"] = False
        return p
    except Exception:
        return None


def session_active(exe_override=None, runner=None):
    """¿Hay algún proveedor de modelo con sesión en Hermes? True/False, o None
    si no se pudo saber (salida ilegible o endpoint propio). Sin binario →
    False. Que el proveedor ELEGIDO no tenga sesión es «falta login del
    proveedor elegido» (status()['detail']), no «sin sesión»."""
    exe = _exe(exe_override)
    if not exe:
        return False
    p = status_report(exe=exe, runner=runner)
    if p is None:
        return None
    connected, _off = _login_view(p)
    if connected:
        return True
    return None if _custom_provider(p) else False


def _scalar(v):
    """Valor escalar de YAML sin comillas ni comentario final."""
    v = (v or "").strip()
    if v[:1] in ("'", '"'):
        q = v[0]
        end = v.find(q, 1)
        return v[1:end] if end > 0 else v[1:]
    return v.split(" #", 1)[0].split("\t#", 1)[0].strip()


def _config_model_provider(text):
    """`model.provider` del config.yaml de Hermes, en minúsculas: '' si no
    hay (o `model` es solo el nombre del modelo), o None si `model` tiene una
    forma que este lector no entiende (el llamador NO debe bloquear por eso).
    Sin PyYAML (stdlib): bloque indentado (solo el primer nivel, no claves
    anidadas), mapeo en línea `{provider: x}` y sin salto de línea final."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"model:(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest.startswith("{"):                       # model: {provider: nous, …}
            pm = re.search(r"""(?:^|[{,\s])provider\s*:\s*("[^"]*"|'[^']*'|[^,}\s]+)""", rest)
            return _scalar(pm.group(1)).lower() if pm else ""
        if rest and not rest.startswith("#"):          # model: "x/y" (solo nombre)
            return "" if rest[:1] in ("'", '"') or re.match(r"[\w./:@-]+$", rest) else None
        indent = None
        for sub in lines[i + 1:]:
            if not sub.strip() or sub.lstrip().startswith("#"):
                continue
            n = len(sub) - len(sub.lstrip(" \t"))
            if n == 0:
                break                                  # siguiente clave de raíz
            if indent is None:
                indent = n
            if n != indent:
                continue                               # clave anidada: no es model.provider
            pm = re.match(r"\s*provider\s*:(.*)$", sub)
            if pm:
                return _scalar(pm.group(1)).lower()
        return ""
    return ""


def _provider_chosen(p, home=None):
    """¿Hermes puede ELEGIR proveedor por sí mismo? Misma regla que su
    `resolve_provider("auto")` (VERIFICADO v0.22.2, hermes_cli/auth.py):
    `model.provider` fijo en config.yaml, o una llave de API en el entorno del
    perfil (sección «API Keys» con ✓), o `active_provider` en auth.json. Una
    sesión OAuth (p. ej. Nous Portal) SIN activar no cuenta: con `provider:
    auto` el chat abre el asistente «No inference provider is configured yet»
    aunque `status` diga «logged in». Solo metadatos: jamás lee llaves."""
    home = home or profile_dir()
    prov = _config_model_provider(_read_text(os.path.join(home, "config.yaml")) or "")
    if prov is None or (prov and prov != "auto"):
        return True          # fijo — o una forma que no sé leer: «no sé» no bloquea
    if any(ok for label, ok in ((p or {}).get("sections") or {}).get("API Keys", [])
           if label.lower() not in _TOOL_KEYS):
        return True
    try:
        with open(os.path.join(home, "auth.json"), encoding="utf-8-sig") as fh:
            return bool(str((json.load(fh) or {}).get("active_provider") or "").strip())
    except (OSError, ValueError, AttributeError):
        return False


def status(exe_override=None, runner=None):
    """Estado honesto para doctor / plan / harnesses.registry. Solo inspecciona."""
    exe = _exe(exe_override)
    out = {"engine": "hermes", "binary": BINARY, "binary_in_path": bool(exe),
           "profile": _profile(), "session_active": False, "ready": False,
           "auth": "proveedor con sesión en el perfil «%s» de Hermes (Motores › "
                   "cuenta y proveedor abre su setup oficial); WORKSPACE nunca ve "
                   "la llave" % _profile()}
    if not exe:
        return out
    p = status_report(exe=exe, runner=runner)
    if p is None:
        out.update(session_active=None, ready=True,
                   detail="no pude leer `hermes status` (se intenta al lanzar)")
        return out
    connected, chosen_off = _login_view(p)
    out["profile_pending"] = bool(p.get("profile_pending"))
    out["providers"] = connected
    out["provider"] = p.get("provider", "")
    out["model"] = p.get("model", "")
    if not connected and _custom_provider(p):
        out.update(session_active=None, ready=True,
                   detail="endpoint propio (%s): no se puede comprobar la sesión"
                          % out["provider"])
        return out
    out["session_active"] = bool(connected)
    out["ready"] = bool(connected) and not chosen_off
    if not connected and p.get("profile_pending"):
        out["detail"] = _t("motorbar.hermes.pending",
                           "el perfil «{p}» de Hermes aún no existe: se crea sin tus "
                           "llaves al abrir el agente; conecta el proveedor en Motores › "
                           "cuenta y proveedor",
                           "Hermes' «{p}» profile doesn't exist yet: it's created "
                           "without your keys when you open the agent; connect the "
                           "provider in Engines › account and provider", p=_profile())
    elif not connected:
        out["detail"] = _t("motorbar.hermes.no_provider",
                           "el perfil «{p}» de Hermes no tiene proveedor con sesión "
                           "(Workspace no copia las llaves de tu Hermes personal)",
                           "Hermes' «{p}» profile has no provider signed in (Workspace "
                           "doesn't copy your personal Hermes keys)", p=_profile())
    elif not p.get("profile_pending") and exe_override is None and not _provider_chosen(p):
        out["ready"], out["model_ready"] = False, False
        out["detail"] = ("%s tiene sesión, pero Hermes no lo tiene elegido como proveedor "
                         "ni hay modelo elegido — Motores › cuenta y proveedor (elige el "
                         "proveedor y el modelo)" % ", ".join(connected))
    elif chosen_off:
        out["model_ready"] = False
        out["detail"] = ("el proveedor elegido (%s) no tiene sesión — Motores › "
                         "cuenta y proveedor" % out["provider"])
    if exe_override is None and runner is None and _profile() == _perfil_base():
        # cable-hermes: Motores dice qué perfiles de agente aún no tienen cuenta (Workspace no copia llaves: la
        # conecta la persona con el selector oficial de ese perfil)
        try:
            sin = perfiles_sin_cuenta()
        except Exception:
            sin = []
        if sin:
            out["perfiles_sin_cuenta"] = [c["perfil"] for c in sin]
            linea = _t("motorbar.hermes.perfiles_sin_cuenta",
                       "perfiles de agente sin cuenta: {ps} (conéctala una vez: {cmd})",
                       "agent profiles without an account: {ps} (connect it once: {cmd})",
                       ps=", ".join(out["perfiles_sin_cuenta"]),
                       cmd=" ".join(comando_cuenta("<perfil>", BINARY)))
            out["detail"] = ("%s · %s" % (out["detail"], linea)) if out.get("detail") else linea
    return out


def available(exe_override=None):
    return bool(_exe(exe_override))


# ── sesiones: export OFICIAL (jamás se lee state.db directo) ───────────────
def _export(args, exe=None, runner=None, timeout=60):
    """`hermes sessions export - --format jsonl <filtros>` → [registro]."""
    exe = exe or _exe()
    if not exe:
        return []
    r = _run(_base(exe) + ["sessions", "export", "-", "--format", "jsonl"] + list(args),
             runner=runner, timeout=timeout)
    if getattr(r, "returncode", 1) != 0:
        msg = ((getattr(r, "stderr", "") or "") + (getattr(r, "stdout", "") or "")).strip()
        # VERIFICADO v0.22.2: un --session-id que no existe sale rc=1 con
        # «No session '<id>'» (v0.18.x: rc=0 y salida vacía) → no hay registro.
        if "No session '" in msg:
            return []
        raise OSError("hermes sessions export rc=%s: %s" % (
            getattr(r, "returncode", "?"), msg[-200:]))
    rows = []
    for line in (getattr(r, "stdout", "") or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("id"):
            rows.append(d)
    return rows


def session_record(sid, exe=None, runner=None):
    """Registro exportado de UNA sesión por id exacto (el filtro de Hermes
    acepta prefijos: se exige igualdad). None si no existe."""
    if not _valid_sid(sid):
        return None
    for d in _export(["--session-id", sid], exe=exe, runner=runner):
        if d.get("id") == sid:
            return d
    return None


def _same_dir(a, b):
    try:
        return os.path.realpath(str(a or "")) == os.path.realpath(str(b or "")) and bool(a)
    except (TypeError, ValueError):
        return False


#: Ids de sesión del REPL: `AAAAMMDD_HHMMSS_<hex>` (hora LOCAL de arranque)
#: hasta v0.22.2; desde v0.22.5, `local-<sha256 hex>` (hermes_state_keys.py),
#: que no trae la hora. Las sesiones viejas migradas conservan su id.
_ID_RE = re.compile(r"\b(\d{8}_\d{6}_[0-9a-f]{4,12}|local-[0-9a-f]{64})\b")


def _list_ids(brain, exe=None, runner=None):
    """Ids recientes de `hermes sessions list --workspace <cerebro>`. Se usa
    la LISTA y no el export filtrado: el export con filtros solo devuelve
    sesiones TERMINADAS (`ended_at`), y una pestaña cerrada de golpe o una
    sesión retomada quedan sin terminar (VERIFICADO v0.18.2)."""
    exe = exe or _exe()
    if not exe or not brain:
        return []
    r = _run(_base(exe) + ["sessions", "list", "--workspace", os.path.realpath(brain),
                           "--limit", "50"], runner=runner, timeout=60)
    if getattr(r, "returncode", 1) != 0:
        raise OSError("hermes sessions list rc=%s" % getattr(r, "returncode", "?"))
    return list(dict.fromkeys(_ID_RE.findall(getattr(r, "stdout", "") or "")))


def _id_time(sid):
    """Hora de arranque que trae el id (`AAAAMMDD_HHMMSS_…`), o None si el id
    no la trae (`local-<hex>` de v0.22.5)."""
    try:
        return time.mktime(time.strptime(str(sid)[:15], "%Y%m%d_%H%M%S"))
    except (ValueError, OverflowError):
        return None


#: Tope del recorrido de sesiones dentro de un cierre (cada export ~0,5 s;
#: la lista trae hasta 50). Con la X de Windows en curso manda lo que quede de
#: su gracia (interactive._CLOSE_GRACE), con margen para el resto del cierre.
_RECORRIDO_MAX_S = 15.0
_MARGEN_X_S = 1.5


def _plazo_recorrido():
    """Plazo (time.monotonic) para recorrer sesiones en ESTE cierre."""
    try:
        import interactive
        at = interactive._GUARD.get("at")
        if at:
            queda = interactive._CLOSE_GRACE - (time.time() - float(at)) - _MARGEN_X_S
            return time.monotonic() + max(0.5, queda)
    except Exception:
        pass
    return time.monotonic() + _RECORRIDO_MAX_S


def sessions_since(brain, t0, exe=None, runner=None, full=False, plazo=None, sigue="",
                   corte=None):
    """Sesiones del REPL del socio CREADAS en este cerebro desde `t0` (epoch):
    candidatos por la lista (hora del id ≥ t0, con margen) y, de cada uno, su
    registro exportado con cwd exacto, origen (lista blanca, _tab_source) y
    started_at verificados.

    Un id sin hora (v0.22.5) se exporta y se juzga por su registro. Para no
    exportar cada sesión del cerebro al cerrar (~0,5 s cada una), el recorrido
    corta en la primera sin actividad desde t0 (con margen): la lista sale
    ordenada por arranque, descendente (VERIFICADO v0.22.5,
    hermes_state_sessions.list_sessions_rich), y lo que viene después es más
    viejo. La excepción es la continuación reciente de una conversación vieja
    (compresión: la lista la muestra en el lugar de su raíz); `full=True`
    recorre todo para seguirla (session_chain lo pide si la pestaña se
    compactó).

    Topes (revisión 2026-10-26: con `full` se exportaban hasta 50 sesiones
    dentro del cierre): `plazo` (time.monotonic; por defecto
    _plazo_recorrido(), que respeta la gracia de la X en Windows) corta el
    recorrido; y con `sigue` (la sesión compactada de la pestaña) se corta en
    cuanto su cadena llega a una continuación que ya no se compactó. Un id
    con hora (hasta v0.22.2) anterior a la pestaña se salta sin exportarlo."""
    if not brain:
        return []
    if plazo is None:
        plazo = _plazo_recorrido()
    out = []
    punta = sigue
    for sid in _list_ids(brain, exe=exe, runner=runner):
        when = _id_time(sid)
        if when is not None and when < float(t0) - 120:
            continue
        if time.monotonic() > plazo:
            if corte is not None:
                corte["plazo"] = True     # quien llama decide si alcanza
            break               # sin tiempo: lo que falte, el cierre tardío
        d = session_record(sid, exe=exe, runner=runner)
        if not d:
            continue
        if when is None and not full and _last_activity(d) < float(t0) - 120:
            break
        try:
            started = float(d.get("started_at") or 0)
        except (TypeError, ValueError):
            continue
        if started < float(t0) - 2 or not _same_dir(d.get("cwd"), brain):
            continue
        # Lista BLANCA: hoy las de Discord graban cwd NULL, pero no se depende
        # de eso; una plataforma nueva tampoco se cuela.
        if not _tab_source(d):
            continue
        out.append(d)
        if full and punta and d.get("parent_session_id") == punta:
            punta = d["id"]
            if d.get("end_reason") != "compression":
                break           # la cadena de la pestaña ya llegó a su punta viva
    return sorted(out, key=lambda d: float(d.get("started_at") or 0))


def _last_activity(d):
    best = 0.0
    for v in [d.get("ended_at"), d.get("started_at")] + [
            m.get("timestamp") for m in d.get("messages") or [] if isinstance(m, dict)]:
        try:
            best = max(best, float(v or 0))
        except (TypeError, ValueError):
            continue
    return best


def _follow(rows, start_id):
    """Cadena start → hijo → … (Hermes con compresión «legacy» rota el id y
    deja parent_session_id). Un hijo ambiguo corta la cadena."""
    chain, cur = [], start_id
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        kids = [d for d in rows if d.get("parent_session_id") == cur]
        if len(kids) != 1:
            break
        chain.append(kids[0])
        cur = kids[0]["id"]
    return chain


def _tras_resume(chain, brain, run, rows, t0, exe=None, runner=None):
    """Si la punta de `chain` se cerró por un `/resume` dentro del REPL
    (end_reason `resumed_other`) y la corrida tiene retomadas CON evidencia, la
    conversación con la que cerró la pestaña es la última retomada: (cadena,
    estado), o None (revisión de la candidata, H2: se capturaba y ataba la
    abandonada). Si la retomada se compactó durante la corrida, se sigue hasta
    su continuación como en la rama `known` (revisión nocturna, M3)."""
    if not (run and chain and chain[-1].get("end_reason") == "resumed_other"):
        return None
    mine = _owner_view(brain, run)[0]
    punta = chain[-1].get("id")
    orden = [x for x in (run_info(run).get("retomadas") or []) if x in mine and x != punta]
    if not orden:
        return None
    base = session_record(orden[-1], exe=exe, runner=runner)
    if not (base and _same_dir(base.get("cwd"), brain) and _tab_source(base)):
        return None
    if base.get("end_reason") != "compression":
        return [base] + _follow(rows or [], base["id"]), "resolved"
    corte = {}
    filas = sessions_since(brain, t0, exe=exe, runner=runner, full=True, sigue=base["id"],
                           corte=corte)
    cadena = [base] + _follow(filas, base["id"])
    if corte.get("plazo") and cadena[-1].get("end_reason") == "compression":
        return cadena, "partial"
    return cadena, "resolved"


def session_chain(brain, t0, known="", exe=None, runner=None, run=""):
    """Sesión(es) de Hermes de ESTA corrida en el cerebro → (cadena, estado).
    cadena = [registro…] en orden (la última es la viva); estado ∈ resolved |
    stale | missing | ambiguous. Con `known` (la de la pestaña) se continúa
    esa; sin él solo cuenta una sesión NUEVA inequívoca de esta corrida
    (`run`, token de run_open): nunca la de otra pestaña abierta en el mismo
    cerebro (anotada por su hook, o nacida mientras ella estaba abierta sin
    anotaciones → ambigua)."""
    if known:
        base = session_record(known, exe=exe, runner=runner)
        if base is None:
            return [], "missing"
        # Compactada (Hermes rotó el id): su continuación puede estar más
        # abajo en la lista que donde sessions_since dejaría de buscar.
        full = base.get("end_reason") == "compression"
        corte = {}
        rows = sessions_since(brain, t0, exe=exe, runner=runner, full=full,
                              sigue=known if full else "", corte=corte)
        chain = [base] + _follow(rows, known)
        otra = _tras_resume(chain, brain, run, rows, t0, exe=exe, runner=runner)
        if otra:
            return otra
        if corte.get("plazo") and chain[-1].get("end_reason") == "compression":
            # se acabó el tiempo antes de llegar a la punta viva: no se da por
            # capturada a medias (el cierre tardío la reintenta con más tiempo)
            return chain, "partial"
        if len(chain) == 1 and _last_activity(base) < float(t0) - 1:
            return chain, "stale"
        return chain, "resolved"
    corte = {}
    rows = sessions_since(brain, t0, exe=exe, runner=runner, corte=corte)
    # Sesión NUEVA = sin padre. Una hija cuyo padre no es de esta corrida es
    # la continuación (compresión) de una conversación de otra pestaña.
    roots = [d for d in rows if not d.get("parent_session_id")]
    if run:
        mine, others, blind = _owner_view(brain, run)

        def ids_of(d):
            return {d["id"]} | {c["id"] for c in _follow(rows, d["id"])}
        if mine:
            roots = [d for d in roots if ids_of(d) & mine]
            if not roots:
                # `/resume` dentro del REPL: la sesión que el hook le atribuyó
                # a esta corrida CON evidencia de retome (`retomadas`) nació
                # antes que ella (no sale entre las nuevas). La última es la
                # conversación con la que cerró; sin evidencia, nada.
                nuevas = {d["id"] for d in rows}
                orden = [x for x in (run_info(run).get("retomadas") or [])
                         if x in mine and x not in nuevas]
                base = session_record(orden[-1], exe=exe, runner=runner) if orden else None
                if base and _same_dir(base.get("cwd"), brain) and _tab_source(base):
                    return [base] + _follow(rows, base["id"]), "resolved"
        else:
            roots = [d for d in roots if not ids_of(d) & others]
            for d in roots:
                try:
                    born = float(d.get("started_at") or 0)
                except (TypeError, ValueError):
                    born = 0.0
                if any(a <= born <= b for a, b in blind):
                    return [], "ambiguous"
    if not roots:
        return [], ("partial" if corte.get("plazo") else "missing")
    if len(roots) > 1:
        return [], "ambiguous"
    chain = [roots[0]] + _follow(rows, roots[0]["id"])
    return _tras_resume(chain, brain, run, rows, t0, exe=exe, runner=runner) or (chain, "resolved")


def ancestors(d, brain, exe=None, runner=None, limit=50, plazo=None, corte=None):
    """Sesiones de las que `d` es continuación (Hermes con compresión
    «legacy» rota el id y deja parent_session_id), de la más vieja a la más
    nueva. Así el respaldo de una pestaña retomada conserva la conversación
    entera aunque su id ya sea el de la hija."""
    out, seen, cur = [], {d.get("id")}, d
    if plazo is None:
        plazo = _plazo_recorrido()
    while len(out) < limit:
        pid = cur.get("parent_session_id")
        if pid and time.monotonic() > plazo:
            if corte is not None:
                corte["plazo"] = True     # faltó historia por tiempo
            break
        if not pid or pid in seen or not _valid_sid(pid):
            break
        p = session_record(pid, exe=exe, runner=runner)
        if (not p or not _same_dir(p.get("cwd"), brain)
                or str(p.get("source") or "") in _FOREIGN_SOURCES):
            break
        seen.add(pid)
        out.append(p)
        cur = p
    return list(reversed(out))


# ── headless ───────────────────────────────────────────────────────────────
def run_turn(prompt, *, model=None, cwd=None, timeout=300, exe_override=None,
             runner=None):
    """UN turno HEADLESS en el perfil propio: `hermes --profile <p>
    --oneshot=<prompt> --usage-file <tmp>` (sesión con origen `tool`, oculta
    de las listas del socio). Devuelve (ok, texto). Sin `model` no se pasa
    `-m` (manda la config del perfil). Hermes imprime el error como respuesta
    y sale con 0: SOLO es éxito un reporte de uso válido con `completed: true`
    y sin `failed` (VERIFICADO v0.18.2 con un turno real); sin reporte o con
    uno ilegible es fallo, con un error útil."""
    exe = _exe(exe_override)
    if not exe:
        return False, "hermes no está en PATH"
    ok, why = ensure_profile(exe, runner=runner)
    if not ok:
        return False, "hermes: perfil %s: %s" % (_profile(), why)
    fd, usage = tempfile.mkstemp(prefix="ws-hermes-usage-", suffix=".json")
    os.close(fd)
    os.unlink(usage)
    texto = prompt or ""
    import memoria
    if memoria.pasa_por_cmd(exe):
        # Sin hermes.exe, el lanzador es hermes.cmd y cmd.exe vuelve a leer el
        # argumento (corte en el primer salto de línea, %VAR%, comandos con una
        # comilla impar); `--oneshot` no lee stdin ni archivo: va en UNA línea
        # saneada, con el tope de la línea de comandos de cmd.exe.
        texto = memoria.argv_seguro(texto, tope=7000)
    cmd = _base(exe) + ["--oneshot=" + texto, "--usage-file", usage]
    if model:
        cmd += ["-m", model]
    import secret_store
    env = secret_store.engine_env()   # el motor no hereda la bóveda
    env["HERMES_SESSION_SOURCE"] = "tool"
    env.pop("WORKSPACE_HERMES_RUN", None)        # un turno headless no es de la pestaña
    # …ni de ningún cerebro: sin la variable, `${WORKSPACE_BRAIN}/skills` no
    # existe y Hermes no carga las skills del cerebro que haya dejado en el
    # entorno quien llama (podría ser el de otro agente).
    env.pop("WORKSPACE_BRAIN", None)
    try:
        if cwd:
            os.makedirs(cwd, exist_ok=True)
        r = _run(cmd, runner=runner, timeout=timeout, cwd=cwd or None, env=env)
        rc = getattr(r, "returncode", 1)
        out = (getattr(r, "stdout", "") or "").strip()
        if rc != 0:
            err = getattr(r, "stderr", "") or ""
            return False, "hermes -z exit %d: %s" % (rc, (err or out).strip()[-300:])
        try:
            with open(usage, encoding="utf-8") as fh:
                rep = json.load(fh)
        except (OSError, ValueError):
            rep = None
        if not isinstance(rep, dict):
            return False, ("hermes -z: sin reporte de uso válido (no se puede saber si "
                           "respondió): %s" % (out[-300:] or "sin salida"))
        if rep.get("failed") or rep.get("completed") is not True:
            detail = str(rep.get("failure") or "").strip() or out
            return False, "hermes -z falló: %s" % (detail[-300:] or "sin detalle")
        return True, out
    except subprocess.TimeoutExpired:
        return False, "hermes -z: timeout tras %ss" % timeout
    except Exception as e:
        return False, "hermes -z: fallo al invocar: %s" % e
    finally:
        try:
            os.remove(usage)
        except OSError:
            pass


# ── identidad: el MISMO AGENTS.md puntero + el núcleo incrustado ───────────
def inject_context(cfg, session_context="", larga=False):
    """AGENTS.md puntero → doc de identidad, con el NÚCLEO de identidad
    incrustado como copia generada (brain_identity.embed_core) + bloque
    invisible de la pestaña. Misma marca y mismo corte que los demás (archivo
    compartido). Por qué la copia: Hermes no expande imports y no tiene
    mensaje de arranque, así que «lee BRAIN.md» depende del modelo; con un
    modelo débil el agente arrancaba sin carácter ni socio (VERIFICADO
    2026-10-15). Un documento que el escáner de Hermes bloquearía no se
    incrusta; si el archivo completo dispararía el bloqueo, va sin copia.
    `larga`: la copia lleva también STATE/MEMORY.md, al final y dentro del
    mismo presupuesto (solo cuando el hook por turno no la va a entregar).
    Devuelve el dict de inject_agents_md + 'embed' (lo que entró/faltó)."""
    from engines.opencode import inject_agents_md
    emb = {}
    try:
        import brain_identity as _bi
        brain = (cfg or {}).get("_brain", "")
        if brain and os.path.isdir(brain):
            emb = _bi.embed_core(brain, cfg, reject=scan_context,
                                 extra=(MEMORIA_LARGA,) if larga else ())
    except Exception as e:
        emb = {"error": "%s: %s" % (type(e).__name__, e)}
    out = inject_agents_md(cfg, session_context=session_context, engine="hermes",
                           embed=emb.get("text", ""), check=scan_context)
    out["embed"] = emb
    return out


def embed_note(inj):
    """Una línea para el socio si la identidad NO llegó completa a Hermes
    ('' si llegó entera)."""
    inj = inj or {}
    emb = inj.get("embed") or {}
    bits = []
    if inj.get("blocked"):
        return ("el escáner de Hermes bloquearía el AGENTS.md (%s): el agente puede "
                "arrancar sin identidad; revisa BRAIN.md y el nombre del agente"
                % ", ".join(inj["blocked"][:3]))
    if inj.get("session_dropped"):
        bits.append("omití la memoria de la pestaña en AGENTS.md: su texto dispararía el "
                    "escáner de Hermes (%s) y bloquearía la identidad; el tono sigue "
                    "llegando por turno" % ", ".join(inj["session_dropped"][:3]))
    if inj.get("embed_dropped"):
        bits.append("va sin la copia de la identidad (el escáner de Hermes la "
                    "bloquearía: %s); el agente depende de leer BRAIN.md"
                    % ", ".join(inj["embed_dropped"][:3]))
    if emb.get("rejected"):
        bits.append("no incrusté %s (el escáner de Hermes lo bloquearía: %s)" % (
            ", ".join(r for r, _f in emb["rejected"]),
            ", ".join(sorted({f for _r, fs in emb["rejected"] for f in fs}))[:120]))
    if emb.get("truncated") or emb.get("omitted"):
        cut = ([emb["truncated"]] if emb.get("truncated") else []) + list(emb.get("omitted") or [])
        ident = [c for c in cut if c != MEMORIA_LARGA]
        if ident:
            bits.append("la identidad no cupo entera (%s queda para que el agente lo lea)"
                        % ", ".join(ident))
        if MEMORIA_LARGA in cut:
            bits.append("la memoria larga (%s) no cupo entera: el agente la lee si la "
                        "necesita" % MEMORIA_LARGA)
    return "; ".join(bits)


def _identity_doc(cfg):
    from engines.opencode import _identity_doc as _doc
    return _doc(cfg)


def overrides_in_root(brain):
    """Archivos en la raíz del cerebro que Hermes leería ANTES que AGENTS.md."""
    return [n for n in _OVERRIDES if brain and os.path.isfile(os.path.join(brain, n))]


# ── pestañas: id de Hermes atado post-hoc + --resume ───────────────────────
def _user_resume(passthrough):
    """(¿el socio eligió sesión a mano?, id si lo dio con --resume/-r)."""
    args = [str(a) for a in passthrough or []]
    for i, a in enumerate(args):
        if a.startswith("--resume="):
            return True, a.split("=", 1)[1]
        if a in ("--resume", "-r"):
            return True, args[i + 1] if i + 1 < len(args) else ""
        if a in ("--continue", "-c") or a.startswith("--continue="):
            return True, ""
    return False, ""


def _bound_elsewhere(brain, tab_name, sid):
    """¿Otra pestaña de este cerebro ya tiene atada esa sesión de Hermes?
    (Hermes crea la sesión con el primer mensaje: una pestaña que se cerró sin
    escribir no debe quedarse con la conversación de otra.)"""
    try:
        import sessions_registry as _reg
        slots = (_reg._local_load().get("map") or {}).get(_reg._brain_key(brain)) or {}
        mine = _reg._slug(tab_name)
        return any(isinstance(v, dict) and v.get("hermes") == sid and k != mine
                   for k, v in slots.items())
    except Exception:
        return False


def _interactive_argv(passthrough, resume_sid="", accept_hooks=False):
    """argv DESPUÉS de `hermes`: perfil propio (SOLO para este comando: el
    default del socio no cambia) + REPL (sin subcomando) + `--resume <id>` de
    la pestaña. Sin `-m` (manda la config del perfil). Un --resume/--continue
    del socio va tal cual y gana. `accept_hooks` (solo si el hook de Workspace
    es el ÚNICO del perfil, ver _hooks_only_ours) agrega `--accept-hooks`:
    Hermes lo aprueba y lo anota en la lista del perfil sin preguntar
    (VERIFICADO v0.18.2 y v0.22.2: hermes_cli/_parser.py, flag de primer
    nivel; agent/shell_hooks.py, _prompt_and_record)."""
    args = [str(a) for a in passthrough or []]
    argv = ["--profile", _profile()]
    if accept_hooks:
        argv.append("--accept-hooks")
    if resume_sid and not _user_resume(args)[0]:
        argv += ["--resume", resume_sid]
    return argv + args


def _offer_account(exe):
    """En una terminal: ¿abrir el selector oficial de proveedor y modelo de
    Hermes (en el perfil de Workspace) ahora? True si se abrió."""
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
        ans = input("  ¿Lo eliges ahora? Se abre el selector oficial de Hermes [S/n] ")
    except (EOFError, KeyboardInterrupt):
        return False
    if ans.strip().lower() in ("n", "no"):
        return False
    try:
        cmd = comando_cuenta(_profile(), exe)
        import secret_store
        subprocess.call(cmd, env=secret_store.engine_env())
    except Exception:
        return False
    return True


def _missing_provider(st):
    return st.get("session_active") is False or st.get("model_ready") is False


def _provider_gate(exe, st):
    """Sin proveedor (o sin proveedor ELEGIDO) Hermes abre su propio asistente
    en vez del agente. Se ofrece elegirlo AHORA con su selector oficial y, si
    sigue faltando, NO se abre salvo que el socio lo pida (escenario hm-nuevo,
    2026-10-16; mismo trato que OpenClaw). True = abrir la pestaña."""
    if _profile() != _perfil_base():
        # cable-hermes: el perfil propio del agente (su `status` puede decir «custom» y no ✓/✗): su cuenta
        try:
            c = cuenta_de_perfil(_profile(), exe=exe)
        except Exception:
            c = {}
        if c.get("lista") is False:
            st = dict(st, session_active=False, detail=c.get("detalle") or st.get("detail"))
    if not _missing_provider(st):
        return True
    print("WORKSPACE: %s." % (st.get("detail") or "Hermes no tiene proveedor"))
    if _offer_account(exe):
        st = status()
        if _profile() != _perfil_base():
            _CUENTAS.pop(_profile(), None)
            if cuenta_de_perfil(_profile(), exe=exe).get("lista") is False:
                st = dict(st, session_active=False)
        if not _missing_provider(st):
            return True
        print("WORKSPACE: aún falta: %s." % st.get("detail"))
    if _profile() != _perfil_base():
        # cable-hermes: el perfil propio de este agente (Workspace no copia ni guarda llaves): su cuenta, con la guía
        print(_t("motorbar.hermes.gate_hint_agente",
                 "  Este agente tiene su propio perfil de Hermes ({p}) y Workspace no copia ni guarda llaves: "
                 "conéctale su cuenta una vez con el selector oficial de Hermes. En esta terminal:\n"
                 "    {cmd}\n  (elige el proveedor, pega tu llave cuando Hermes te la pida y el modelo)",
                 "  This agent has its own Hermes profile ({p}) and Workspace doesn't copy or store keys: "
                 "connect its account once with Hermes' official selector. In this terminal:\n"
                 "    {cmd}\n  (pick the provider, paste your key when Hermes asks, and the model)",
                 p=_profile(), cmd=" ".join(shlex.quote(c) for c in comando_cuenta(_profile(), BINARY))))
    else:
        print(_t("motorbar.hermes.gate_hint",
                 "  El perfil de Workspace en Hermes tiene su propio proveedor (Workspace no "
                 "copia tus llaves). Sin él, Hermes abre su propio asistente en vez de tu "
                 "agente: conéctalo en Motores › Hermes › cuenta y proveedor (el proveedor "
                 "y el modelo).",
                 "  Workspace's Hermes profile has its own provider (Workspace doesn't copy "
                 "your keys). Without one, Hermes opens its own wizard instead of your "
                 "agent: connect it in Engines › Hermes › account and provider (provider "
                 "and model)."))
    try:
        import engine_versions as _EV
        return _EV.allow_anyway()
    except Exception:
        return True


def _perfil_para_lanzar(cfg, brain, exe):
    """cable-hermes · (perfil, info): con el sistema nuevo encendido (arquitectura.sesion.activo) y un cerebro, el
    perfil PROPIO del agente al día, ya elegido para todo lo de esta sesión (_profile). ('', {}) si está apagado;
    si falla, lo dice en una línea y sigue con el de Workspace."""
    if not brain:
        return "", {}
    try:
        from arquitectura import sesion as _s
        if not _s.activo():
            return "", {}
        pkg = _s.instalar(brain)
        perfil, info = asegurar_perfil_agente(brain, str(cfg.get("name") or "") or nombre_agente(brain, os.environ),
                                              pkg["agent-plugins"], exe=exe)
    except Exception as e:
        print(_t("motorbar.hermes.perfil_agente_falla",
                 "WORKSPACE: no pude preparar el perfil de Hermes de este agente ({e}); abre en el de Workspace, "
                 "como antes.", "WORKSPACE: couldn't prepare this agent's Hermes profile ({e}); opening in "
                 "Workspace's, as before.", e=str(e)[:200]))
        return "", {}
    os.environ[_PERFIL_AGENTE_ENV] = perfil
    if info.get("apartado"):
        print(_t("motorbar.hermes.perfil_agente_apartado",
                 "WORKSPACE: la creación anterior del perfil {p} quedó a medias; la aparté en {d} (no se borró nada) "
                 "y lo volví a crear.",
                 "WORKSPACE: the previous creation of profile {p} was left half-done; I moved it to {d} (nothing "
                 "was deleted) and created it again.", p=perfil, d=info["apartado"]))
    if info.get("creado"):
        print(_t("motorbar.hermes.perfil_agente_creado",
                 "WORKSPACE: este agente ya tiene su propio perfil de Hermes ({p}): sus avisos, su MCP y sus skills "
                 "van ahí; tus perfiles no cambian. Workspace no copia llaves: si le falta la cuenta, te guío.",
                 "WORKSPACE: this agent now has its own Hermes profile ({p}): its hooks, MCP and skills live there; "
                 "your profiles don't change. Workspace doesn't copy keys: if it lacks the account, I'll guide you.",
                 p=perfil))
    return perfil, info


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    """Arranca un agente EN HERMES (REPL oficial) envuelto por el wrapper
    neutral (session_start → REPL → session_end). plan=True NO lanza."""
    brain = cfg.get("_brain", "")
    exe = _exe()

    if plan:
        line = "─" * 66
        print(line)
        print("  WORKSPACE · plan de arranque — motor HERMES — agente: %s"
              % cfg.get("display", cfg.get("name")))
        print(line)
        print("  motor       : hermes (REPL oficial, en línea) en su perfil «%s» "
              "(propio de Workspace; el Hermes personal no cambia)" % _profile())
        print("  modelo      : lo fija el SOCIO en el perfil (Motores › cuenta y "
              "proveedor; Workspace no pasa -m)")
        print("  del cerebro : SOUL.md neutral, memoria, %s de Hermes apagados, "
              "context_file_max_chars=%d, hook de tono por turno (re-asegurados "
              "al lanzar)" % (" y ".join(_TOOLSETS_OFF), CONTEXT_FILE_CHARS))
        print(_t("motorbar.hermes.plan_skills",
                 "  skills      : las de fábrica del perfil + las de tu cerebro (skills/); "
                 "las que Hermes crea van a skills/aprendidas/ de tu cerebro",
                 "  skills      : the profile's built-in ones + your brain's (skills/); "
                 "the ones Hermes creates go to your brain's skills/aprendidas/"))
        print("  cerebro     : %s  (cwd de la sesión)" % brain)
        print("  identidad   : AGENTS.md puntero → %s + copia generada del núcleo "
              "(%s + BOOT/NN + perfil del socio); Hermes no crea archivos de "
              "identidad en el cerebro" % (_identity_doc(cfg), _identity_doc(cfg)))
        print("  pestañas    : picker compartido — cada pestaña con su sesión de "
              "Hermes (atada al cerrar, `--resume <id>` al reabrir)")
        print("  cierre      : export oficial de la sesión (`hermes sessions export`) "
              "→ respaldo, catálogo de skills/aprendidas/ y revisión de skills (si "
              "está encendida)")
        print(line)
        print("  [%s] binario hermes en PATH: %s"
              % ("✓" if exe else "✗ FALTA", exe or "(Motores › instalar)"))
        print("  [%s] cerebro: %s"
              % ("✓" if brain and os.path.isdir(brain) else "✗ FALTA", brain))
        print("  [%s] perfil: %s"
              % ("✓" if _quick_ok(profile_dir()) else "·", profile_dir()
                 if os.path.isdir(profile_dir()) else "(se crea al lanzar)"))
        over = overrides_in_root(brain)
        if over:
            print("  [!] %s en la raíz: Hermes lo lee ANTES que AGENTS.md"
                  % ", ".join(over))
        print(line)
        return

    if not exe:
        print("WORKSPACE: hermes no está en PATH — instálalo desde Motores.")
        sys.exit(1)

    # Perfil propio ANTES de cualquier cosa que abra una sesión. Camino
    # rápido: si sus archivos ya dicen que todo está bien, no se llama al CLI.
    ok, why = ensure_profile(exe)
    if not ok:
        print("WORKSPACE: no pude preparar el perfil de Hermes (%s)." % why)
        sys.exit(1)
    if why:
        print("WORKSPACE: %s." % why)
    # cable-hermes: con el sistema nuevo, el perfil PROPIO de este agente (sus avisos, su MCP y sus skills en
    # su config.yaml); todo lo de esta sesión va en él. Si no se puede, el de Workspace, como antes.
    perfil_ag, info_ag = _perfil_para_lanzar(cfg, brain, exe)
    wired, approved = hook_state()
    if perfil_ag:
        wired = True                 # su `hooks:` lo acaba de escribir asegurar_perfil_agente
    prof_cfg = _read_text(os.path.join(profile_dir(), "config.yaml"))
    # D-9: el comando del hook lleva la ruta de Python y del checkout; si
    # cambia, Hermes lo trata como hook nuevo y vuelve a preguntar. Si el
    # bloque `hooks:` es solo el de Workspace, Hermes lo aprueba solo
    # (`--accept-hooks`; en el REPL deja HERMES_ACCEPT_HOOKS=1 a lo que lance
    # esta sesión, por eso únicamente mientras falta la aprobación). Con hooks
    # del socio no se aprueba nada: se avisa y él decide.
    # En el perfil del agente, nunca: la aprobación de sus avisos es del socio (cero bypass).
    accept = bool(wired and not approved and _hooks_only_ours(prof_cfg)) and not perfil_ag
    # ¿El hook por turno va a correr sin que el socio decida nada? Entonces
    # él entrega la memoria larga (STATE/MEMORY.md); si no, va en la copia
    # del AGENTS.md.
    hook_ok = bool(wired and (approved or accept))
    if perfil_ag and info_ag.get("confianza") == "falta":
        # Workspace aprueba SUS avisos en SU perfil (aprobar_avisos); si no pudo, Hermes los pide aquí
        print(_t("motorbar.hermes.aprobar_avisos",
                 "WORKSPACE: no pude aprobar los avisos de Workspace en el perfil de este agente ({p}); Hermes te "
                 "los pedirá ({n}): anotan el estado de la pestaña, niegan leer llaves y secretos, y añaden tu tono "
                 "y tu memoria. Responde «y» a cada uno.",
                 "WORKSPACE: I couldn't approve Workspace's hooks in this agent's profile ({p}); Hermes will ask "
                 "you ({n}): they record the tab's status, refuse reading keys and secrets, and add your tone and "
                 "memory. Answer «y» to each.", n=info_ag.get("faltan") or "", p=perfil_ag))
    elif wired and not approved and not accept:
        print("WORKSPACE: Hermes te pedirá aprobar el hook de Workspace (%s → "
              "hooks/%s): añade tu tono y tu memoria a los mensajes y anota qué "
              "pestaña es dueña de la sesión; no guarda ni envía nada más. Responde "
              "«y» una vez; con «N» el tono y la memoria solo llegan al arrancar."
              % (_HOOK_EVENT, os.path.basename(_HOOK_SCRIPT)))

    if not _provider_gate(exe, status()):
        sys.exit(0)
    over = overrides_in_root(brain)
    if over:
        print("WORKSPACE: %s en la raíz del cerebro le gana a AGENTS.md en Hermes "
              "— la identidad del agente puede no cargarse." % ", ".join(over))

    tab, resume_sid, session_blk = None, "", ""
    mem_desde, mem_base = time.time(), None
    agent = str(cfg.get("name") or "")
    cfg.setdefault("_engine", "hermes")
    os.environ["WORKSPACE_ENGINE_LABEL"] = LABEL
    try:
        from engines import _ui
        import sessions_registry as _reg
        if not (preselect and preselect.get("wid")):
            from engines import claude_code as _cc0
            _cc0.session_preflight(cfg, "hermes")
        tab = _ui.pick_tab(cfg, preselect=preselect)
        if show_banner:                 # la limpieza de antes del REPL lo quita
            _ui.cargando(cfg, tab)
        if not tab:
            from engines import claude_code as _cc
            _cc.warn_no_tab(_cc.LAST_PICK_ERROR)
        if tab:
            wid, wname = tab
            _ui.export_tab_env(cfg, wid, wname)
            _reg.ensure_tab(brain, agent, wname, claude_wid=wid)
            resume_sid = _reg.resume_id(brain, agent, wname, "hermes") or ""
            if not _valid_sid(resume_sid):
                resume_sid = ""
            # La huella ANTES de armar el bloque: lo que llegue después cuenta
            # como cambio y el hook por turno lo manda (memoria_turno).
            mem_desde = time.time()
            mem_base = _huella(brain, wname, mem_desde)
            session_blk = _reg.session_doc_block(brain, wname, engine="hermes",
                                                 resumed=bool(resume_sid))
    except Exception as e:
        tab, resume_sid, session_blk = None, "", ""
        try:
            from engines import claude_code as _cc
            err = "no pude preparar la pestaña (%s: %s)" % (type(e).__name__, e)
            _cc._session_log(cfg, "hermes", err)
            _cc.warn_no_tab(err)
        except Exception:
            pass

    user_picked, user_sid = _user_resume(passthrough)
    if resume_sid and not user_picked:
        # Id huérfano (sesión borrada en Hermes): arrancar fresco y re-atar,
        # jamás un --resume que falla en cada apertura.
        try:
            if session_record(resume_sid, exe=exe) is None:
                if perfil_ag and tab:
                    _aviso_pestana_movida(brain, tab, perfil_ag, resume_sid)
                resume_sid = ""
        except Exception:
            pass

    # N3 (prueba en vivo 2026-10-21): el AGENTS.md es uno por cerebro y Hermes
    # lo congela en el PRIMER mensaje, no al abrir: si otra ventana lo
    # reescribía antes, esta pestaña se creía la otra toda la sesión. Con el
    # hook aprobado la pestaña llega por él (primer turno y retome, dicha de
    # forma explícita) y su bloque no pasa por el AGENTS.md; el de otra
    # ventana viva se respeta (OpenClaw lo relee en cada turno). Sin el hook,
    # como antes.
    # Corrida registrada ANTES de abrir y antes de decidir por dónde va la
    # pestaña: el hook por turno anota en ella las sesiones de ESTA pestaña
    # (env heredado por Hermes y su hook) y la memoria que ya le entregó a
    # cada una. Sin corrida (candado ocupado, disco lleno) el hook no sabe de
    # qué pestaña es: la pestaña y la memoria van por el AGENTS.md, como sin
    # hook (revisión de la 0.5.1, P2-8: no llegaban por ningún camino).
    # La sesión que esta pestaña retoma queda anotada desde ya: el hook (que
    # en v0.22.5 corre en un gateway con el entorno de otra pestaña) la
    # reconoce sin adivinar (run_de_sesion).
    run = run_open(brain, tab[1] if tab else "",
                   mem={"desde": mem_desde, "doc": None} if tab else None,
                   larga={"modo": "hook" if hook_ok else "doc", "tope": _spill_chars(prof_cfg)},
                   agent=agent, known=[user_sid if user_picked else resume_sid], exe=exe,
                   perfil=perfil_ag, wid=tab[0] if tab else "")
    if not run:
        hook_ok = False
    propio = bool(session_blk) and not hook_ok
    doc_blk = session_blk if not hook_ok else _bloque_de_otra_ventana(brain)
    inj = inject_context(cfg, session_context=doc_blk, larga=not hook_ok)
    # Una sesión NUEVA lee el AGENTS.md al crearse: si el bloque quedó ahí, el
    # hook no lo repite en su primer turno (sí si después cambia la memoria).
    mem_doc = mem_base if (propio and _mem_en_doc(inj)) else None
    if run and mem_doc is not None:
        run_mem_doc(run, mem_doc)
    if not inj.get("ok") and inj.get("detail"):
        print("WORKSPACE: identidad NO inyectada (%s) — Hermes arrancará "
              "genérico." % inj["detail"])
    elif tab and propio and inj.get("action") == "custom" and not inj.get("session"):
        print("WORKSPACE: no pude anexar la memoria de la pestaña al AGENTS.md "
              "del socio — Hermes arranca sin ella.")
    elif inj.get("ok") and inj.get("action") != "custom" and embed_note(inj):
        print("WORKSPACE: %s." % embed_note(inj))

    # Sin banner del cerebro: el REPL de Hermes es EN LÍNEA, el banner quedaría
    # fijo arriba de la sesión. Solo se limpia la pantalla.
    if show_banner:
        try:
            sys.stdout.write("\033[2J\033[3J\033[H")
            sys.stdout.flush()
        except Exception:
            pass

    argv = _interactive_argv(passthrough, resume_sid=resume_sid, accept_hooks=accept)

    # La captura al cierre exporta ESTA sesión: la de la pestaña (o la que el
    # socio pidió por id); sin id, busca la sesión nueva de este cerebro.
    known = user_sid if user_picked else resume_sid
    if known and _valid_sid(known):
        os.environ["WORKSPACE_HERMES_SESSION"] = known
    else:
        os.environ.pop("WORKSPACE_HERMES_SESSION", None)

    _doc_dirty = []

    def _ctx_sink(ctx):
        try:
            merged = "\n\n".join(p for p in (doc_blk, (ctx or "").strip()) if p)
            if not merged:
                return
            r = inject_context(cfg, session_context=merged, larga=not hook_ok)
            if propio and not _mem_en_doc(r):
                run_mem_doc(run, None)         # el arranque la sacó del AGENTS.md
            if r.get("ok") and (r.get("action") != "custom"
                                or r.get("session") == "appended"):
                _doc_dirty.append(True)
            elif (ctx or "").strip():
                print("[WORKSPACE · contexto de arranque]\n%s\n" % ctx.strip())
        except Exception:
            pass

    t0 = time.time()
    if run:
        os.environ["WORKSPACE_HERMES_RUN"] = run
    else:
        os.environ.pop("WORKSPACE_HERMES_RUN", None)
    try:
        import interactive
        rc = interactive.run_official_cli_interactive(
            "hermes", brain=brain or None, argv=argv, context_sink=_ctx_sink,
            pending={"tab": tab[1] if tab else "", "agent": agent,
                     "resume_id": resume_sid, "user_picked": bool(user_picked)})
    except Exception as e:
        run_close(run)
        print("WORKSPACE: no pude lanzar hermes (%s: %s)" % (type(e).__name__, e))
        sys.exit(1)
    # AGENTS.md es UNO por cerebro: si otra pestaña sigue viva en él (de
    # cualquier motor), el bloque es el suyo y no se toca; lo limpia la última
    # que cierre.
    try:
        import pending_runs
        otra = bool(brain) and pending_runs.live_in_brain(brain, exclude=pending_runs.current())
    except Exception:
        otra = False
    if (doc_blk or _doc_dirty) and not otra:
        try:
            inject_context(cfg)
        except Exception:
            pass
    if not otra and brain:
        # El bloque que quede (lo pudo escribir OTRA ventana que cerró antes
        # con esta abierta) es de Workspace y ya no es de nadie: lo quita
        # la última en cerrar, sin tocar el texto del socio (revisión de la
        # 0.5.1, P2-1).
        try:
            import pending_runs
            pending_runs.clean_docs("hermes", brain)
        except Exception:
            pass
    # Binding POST-HOC: la sesión que Hermes creó (o en la que siguió) queda
    # atada a la pestaña → la próxima vez `hermes --resume <id>`. Sin id previo
    # solo una sesión nueva inequívoca DE ESTA corrida; una elección manual del
    # socio no se ata.
    if tab and not user_picked:
        try:
            import sessions_registry as _reg
            chain, state = session_chain(brain, t0, known=resume_sid, exe=exe, run=run)
            sid = chain[-1]["id"] if chain and state in ("resolved", "stale") else ""
            if sid and sid != resume_sid and not _bound_elsewhere(brain, tab[1], sid):
                _reg.bind(brain, agent, tab[1], "hermes", sid)
        except Exception:
            pass
    run_close(run)
    try:
        import pending_runs
        pending_runs.done()               # atado y limpieza hechos: ya no está pendiente
    except Exception:
        pass
    sys.exit(rc if isinstance(rc, int) else 0)


def pick(cfg):
    """Picker de pestañas COMPARTIDO (registro neutral). Falla-suave → ''."""
    try:
        from engines import _ui
        cfg.setdefault("_engine", "hermes")
        return _ui.pick_keep_label(cfg, LABEL)
    except Exception:
        return ""
