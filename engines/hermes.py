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

#: Versiones del CLI oficial con las que se VERIFICARON las lecturas de este
#: adapter (engine_versions: doctor avisa si la instalada es de otra línea).
#: Al verificar una versión nueva, agrégala aquí (runbooks/agregar-motor.md).
#: 0.18.2 (`status` completo) · 0.22.2 (`status --full`; export rc=1 «No session»).
VERIFIED_VERSIONS = ("0.18.2", "0.22.2")
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
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
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
    `AAAAMMDD_HHMMSS_<6 hex>`; se aceptan otros sin espacios ni guion inicial)."""
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
#: «context» de `tools/threat_patterns.py` (v0.18.2), para no incrustar un
#: documento que dispare el bloqueo. test_motores_hermes compara esta copia
#: con la del Hermes instalado cuando existe (avisa si Hermes la cambia).
_SCAN_FILLER = r"(?:\w+\s+){0,8}"
_SCAN_PATTERNS = (
    (r'ignore\s+%s(previous|all|above|prior)\s+%sinstructions' % (_SCAN_FILLER, _SCAN_FILLER), "prompt_injection"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'disregard\s+%s(your|all|any)\s+%s(instructions|rules|guidelines)' % (_SCAN_FILLER, _SCAN_FILLER), "disregard_rules"),
    (r'act\s+as\s+(if|though)\s+%syou\s+%s(have\s+no|don\'t\s+have)\s+%s(restrictions|limits|rules)' % (_SCAN_FILLER, _SCAN_FILLER, _SCAN_FILLER), "bypass_restrictions"),
    (r'<!--[^>]{0,512}(?:ignore|override|system|secret|hidden)[^>]{0,512}-->', "html_comment_injection"),
    (r'<\s*div\s+style\s*=\s*["\'][^>]{0,2048}display\s*:\s*none', "hidden_div"),
    (r'translate\s+[^\n]{0,512}\s+into\s+[^\n]{0,512}\s+and\s+(execute|run|eval)', "translate_execute"),
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
    (r'curl\s+[^\n]{0,2048}\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl"),
    (r'wget\s+[^\n]{0,2048}\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget"),
    (r'cat\s+[^\n]{0,2048}(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)', "read_secrets"),
)
_SCAN_INVISIBLE = frozenset("​‌‍⁠⁢⁣⁤﻿"
                            "‪‫‬‭‮⁦⁧⁨⁩")
_SCAN_MAX = 65_536
_SCAN_COMPILED = tuple((re.compile(p, re.IGNORECASE), pid) for p, pid in _SCAN_PATTERNS)


def scan_context(text):
    """Hallazgos que el escáner de contexto de Hermes daría para `text` (misma
    normalización: BOM inicial fuera, invisibles sobre el texto crudo, NFKC,
    sin mayúsculas). [] = Hermes lo carga."""
    import unicodedata
    text = str(text or "")
    if text.startswith("﻿"):
        text = text[1:]
    text = text[:_SCAN_MAX]
    found = ["invisible_unicode_U+%04X" % ord(c)
             for c in sorted(set(text) & _SCAN_INVISIBLE)]
    norm = unicodedata.normalize("NFKC", text)
    found += [pid for rx, pid in _SCAN_COMPILED if rx.search(norm)]
    return found


def _profile():
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
def _global_off_parse(text):
    """`agent.disabled_toolsets` del config.yaml → {state: absent|block|foreign,
    items (la lista, o None si la clave no está), y dónde está cada cosa para
    editar sin tocar lo demás}. Lee la lista sangrada (como la vuelca Hermes),
    en una línea (`[a, b]`), vacía/null, un nombre suelto o el texto de una
    lista (`"['memory']"`, como lo lee Hermes: parse_config_string_list).
    Conservador: de `agent:` solo mira esa clave; «foreign» = `agent:` o la
    clave en una forma que no se edita a mano."""
    lines = (text or "").splitlines(True)
    out = {"lines": lines, "state": "absent", "items": None, "span": None, "ci": "  ",
           "at": None, "end": None, "form": None, "item_lead": None}
    span = _top_span(lines, "agent")
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
        if m.group(1) != _GLOBAL_OFF_KEY:
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


def _with_global_off(text):
    """config.yaml con session_search y memory en `agent.disabled_toolsets`, o
    None si no hace falta o `agent:` tiene una forma que no se edita a mano.
    La lista del socio se conserva (solo gana las que falten); lo demás de
    `agent:` y del archivo queda byte a byte."""
    p = _global_off_parse(text)
    if p["state"] == "foreign":
        return None
    falta = [t for t in _TOOLSETS_OFF if t not in (p["items"] or [])]
    if not falta:
        return None
    lines = list(p["lines"])
    if p["state"] == "absent":
        body = "".join(lines)
        if body and not body.endswith("\n"):
            body += "\n"
        return body + "agent:\n  %s:\n" % _GLOBAL_OFF_KEY + "".join(
            "  - %s\n" % t for t in _TOOLSETS_OFF)
    s0, s1, ci = p["span"][0], p["span"][1], p["ci"]
    if lines[s1 - 1:s1] and not lines[s1 - 1].endswith("\n"):
        lines[s1 - 1] += "\n"
    if _yaml_value(lines[s0].rstrip("\r\n")[len("agent:"):]):
        lines[s0] = "agent:\n"                       # `agent: {}` / null → bloque

    def items(lead, names):
        return ["%s- %s\n" % (lead, _yaml_quote(t)) for t in names]
    if p["at"] is None:
        lines[s0 + 1:s0 + 1] = ["%s%s:\n" % (ci, _GLOBAL_OFF_KEY)] + items(ci, falta)
    elif p["form"] == "block":
        lines[p["end"]:p["end"]] = items(p["item_lead"], falta)
    else:                                            # vacía o en una línea
        lines[p["at"]:p["at"] + 1] = (["%s%s:\n" % (ci, _GLOBAL_OFF_KEY)]
                                      + items(ci, list(p["items"] or []) + falta))
    new = "".join(lines)
    return new if _global_off_ok(new) else None


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
            and _skills_ok(cfg))


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


def run_open(brain, tab="", mem=None, larga=None):
    """Registra una corrida de Hermes en este cerebro → token (o '' si no se
    pudo: falla-suave, la captura vuelve al criterio de ventana). `mem` =
    {'desde': epoch, 'doc': huella o None}: desde cuándo lo que anote el
    agente es suyo y la huella de la memoria que quedó en el AGENTS.md (None
    si no quedó); lo usa el hook por turno (memoria_turno). `larga` =
    {'modo': 'hook'|'doc', 'tope': caracteres}: quién entrega STATE/MEMORY.md
    (el hook por turno o la copia del AGENTS.md) y el tope del contexto del
    hook en el perfil (memoria_larga_turno)."""
    token = uuid.uuid4().hex
    now = time.time()

    def fn(runs):
        keep = []
        for r in runs:
            if r.get("t1") is None:
                alive = _pid_alive(r.get("pid"))
                if alive is False or (alive is None and now - float(r.get("t0") or 0)
                                      > _RUN_UNKNOWN_PID_TTL):
                    r["t1"] = now          # corrida muerta sin cierre: termina ahora
            if r.get("t1") is not None and now - float(r["t1"]) > _RUN_TTL:
                continue
            keep.append(r)
        rec = {"id": token, "brain": os.path.realpath(brain or ""), "tab": tab,
               "pid": os.getpid(), "t0": now, "t1": None, "sessions": []}
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


#: Ids de sesión del REPL: `AAAAMMDD_HHMMSS_<hex>` (hora LOCAL de arranque).
_ID_RE = re.compile(r"\b(\d{8}_\d{6}_[0-9a-f]{4,12})\b")


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
    try:
        return time.mktime(time.strptime(str(sid)[:15], "%Y%m%d_%H%M%S"))
    except (ValueError, OverflowError):
        return None


def sessions_since(brain, t0, exe=None, runner=None):
    """Sesiones del REPL del socio CREADAS en este cerebro desde `t0` (epoch):
    candidatos por la lista (hora del id ≥ t0, con margen) y, de cada uno, su
    registro exportado con cwd exacto, origen (lista blanca _TAB_SOURCES) y
    started_at verificados."""
    if not brain:
        return []
    out = []
    for sid in _list_ids(brain, exe=exe, runner=runner):
        when = _id_time(sid)
        if when is None or when < float(t0) - 120:
            continue
        d = session_record(sid, exe=exe, runner=runner)
        if not d:
            continue
        try:
            started = float(d.get("started_at") or 0)
        except (TypeError, ValueError):
            continue
        if started < float(t0) - 2 or not _same_dir(d.get("cwd"), brain):
            continue
        # Lista BLANCA: hoy las de Discord graban cwd NULL, pero no se depende
        # de eso; una plataforma nueva tampoco se cuela.
        if str(d.get("source") or "") not in _TAB_SOURCES:
            continue
        out.append(d)
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


def session_chain(brain, t0, known="", exe=None, runner=None, run=""):
    """Sesión(es) de Hermes de ESTA corrida en el cerebro → (cadena, estado).
    cadena = [registro…] en orden (la última es la viva); estado ∈ resolved |
    stale | missing | ambiguous. Con `known` (la de la pestaña) se continúa
    esa; sin él solo cuenta una sesión NUEVA inequívoca de esta corrida
    (`run`, token de run_open): nunca la de otra pestaña abierta en el mismo
    cerebro (anotada por su hook, o nacida mientras ella estaba abierta sin
    anotaciones → ambigua)."""
    rows = sessions_since(brain, t0, exe=exe, runner=runner)
    if known:
        base = session_record(known, exe=exe, runner=runner)
        if base is None:
            return [], "missing"
        chain = [base] + _follow(rows, known)
        if len(chain) == 1 and _last_activity(base) < float(t0) - 1:
            return chain, "stale"
        return chain, "resolved"
    # Sesión NUEVA = sin padre. Una hija cuyo padre no es de esta corrida es
    # la continuación (compresión) de una conversación de otra pestaña.
    roots = [d for d in rows if not d.get("parent_session_id")]
    if run:
        mine, others, blind = _owner_view(brain, run)

        def ids_of(d):
            return {d["id"]} | {c["id"] for c in _follow(rows, d["id"])}
        if mine:
            roots = [d for d in roots if ids_of(d) & mine]
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
        return [], "missing"
    if len(roots) > 1:
        return [], "ambiguous"
    return [roots[0]] + _follow(rows, roots[0]["id"]), "resolved"


def ancestors(d, brain, exe=None, runner=None, limit=50):
    """Sesiones de las que `d` es continuación (Hermes con compresión
    «legacy» rota el id y deja parent_session_id), de la más vieja a la más
    nueva. Así el respaldo de una pestaña retomada conserva la conversación
    entera aunque su id ya sea el de la hija."""
    out, seen, cur = [], {d.get("id")}, d
    while len(out) < limit:
        pid = cur.get("parent_session_id")
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
        import engine_install
        cmd = list(engine_install.recipe("hermes")["account_cmd"])
        cmd[0] = exe
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
    if not _missing_provider(st):
        return True
    print("WORKSPACE: %s." % (st.get("detail") or "Hermes no tiene proveedor"))
    if _offer_account(exe):
        st = status()
        if not _missing_provider(st):
            return True
        print("WORKSPACE: aún falta: %s." % st.get("detail"))
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
              "proveedor; el harness no pasa -m)")
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
    wired, approved = hook_state()
    prof_cfg = _read_text(os.path.join(profile_dir(), "config.yaml"))
    # D-9: el comando del hook lleva la ruta de Python y del checkout; si
    # cambia, Hermes lo trata como hook nuevo y vuelve a preguntar. Si el
    # bloque `hooks:` es solo el de Workspace, Hermes lo aprueba solo
    # (`--accept-hooks`; en el REPL deja HERMES_ACCEPT_HOOKS=1 a lo que lance
    # esta sesión, por eso únicamente mientras falta la aprobación). Con hooks
    # del socio no se aprueba nada: se avisa y él decide.
    accept = bool(wired and not approved and _hooks_only_ours(prof_cfg))
    # ¿El hook por turno va a correr sin que el socio decida nada? Entonces
    # él entrega la memoria larga (STATE/MEMORY.md); si no, va en la copia
    # del AGENTS.md.
    hook_ok = bool(wired and (approved or accept))
    if wired and not approved and not accept:
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
    run = run_open(brain, tab[1] if tab else "",
                   mem={"desde": mem_desde, "doc": None} if tab else None,
                   larga={"modo": "hook" if hook_ok else "doc", "tope": _spill_chars(prof_cfg)})
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
