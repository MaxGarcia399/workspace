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
(hooks/hermes_turno.py; Hermes pide aprobarlo una vez en su REPL), las
herramientas `session_search` y `memory` apagadas (leen todo el perfil: un
agente leía las conversaciones de otro) y `context_file_max_chars` con espacio
para la identidad incrustada. Lo demás (modelo, proveedor, skills, cron) es
vanilla.

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

#: Hook por turno (tono + dueño de la sesión). Nombre distinto de cualquier
#: módulo de la raíz (runbook §6).
_HOOK_EVENT = "pre_llm_call"
_HOOK_SCRIPT = os.path.join(_ROOT, "hooks", "hermes_turno.py")
_HOOK_TIMEOUT = 10


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


def _setting_off(text, leaf):
    return bool(re.search(r"(?m)^[ \t]+%s:[ \t]*false[ \t]*$" % re.escape(leaf), text or ""))


def _hooks_span(lines):
    """(inicio, fin, ¿valor en línea?) de la clave `hooks:` de primer nivel, o
    None. «En línea» = un valor no vacío en la misma línea (`hooks: {…}`):
    YAML válido que no se re-escribe a mano."""
    for i, ln in enumerate(lines):
        m = re.match(r"hooks:(.*)$", ln.rstrip("\r\n"))
        if not m:
            continue
        val = m.group(1).strip()
        if val and not val.startswith("#") and not re.match(
                r"(\{\s*\}|\[\s*\]|null|~)\s*(#.*)?$", val):
            return i, i + 1, True
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j][:1] in (" ", "\t", "-")):
            j += 1
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
    events = set(re.findall(r"(?m)^[ \t]+([A-Za-z_]+):[ \t]*$", block))
    if events <= {_HOOK_EVENT} and cmds == block.count(os.path.basename(_HOOK_SCRIPT)):
        return "stale"
    return "foreign"


def _with_hook(text):
    """config.yaml con el bloque de Workspace en lugar del suyo (o al final)."""
    lines = (text or "").splitlines(True)
    span = _hooks_span(lines)
    if span is None:
        body = "".join(lines)
        if body and not body.endswith("\n"):
            body += "\n"
        return body + _hook_block()
    return "".join(lines[:span[0]]) + _hook_block() + "".join(lines[span[1]:])


def _context_chars(text):
    """`context_file_max_chars` de primer nivel del config.yaml (0 = no hay)."""
    m = re.search(r"(?m)^context_file_max_chars:[ \t]*['\"]?(\d+)['\"]?[ \t]*(#.*)?$",
                  text or "")
    return int(m.group(1)) if m else 0


def _cli_toolsets(text):
    """Lista `platform_toolsets.cli` del config.yaml, o None si no está (Hermes
    usa entonces su super-toolset `hermes-cli`, que lo incluye todo). Lee las
    dos formas en que Hermes vuelca listas (`- x` al nivel de la clave o
    sangrado) y la forma en línea `[a, b]`.

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
        m = re.match(r"([ \t]+)cli:(.*)$", ln)
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


def _tool_on(text, name):
    """¿La herramienta `name` queda encendida en el REPL/`-z` del perfil? Sin
    lista cli, o con un compuesto `hermes-*`, está encendida; session_search
    también la enciende el compuesto `coding`."""
    ts = _cli_toolsets(text)
    if ts is None or any(t.startswith("hermes-") for t in ts):
        return True
    if name == _LEAK_TOOL and any(t in _LEAKY_TOOLSETS for t in ts):
        return True
    return name in ts


def _toolsets_off(text):
    """¿Las herramientas de _TOOLSETS_OFF están apagadas en la lista cli?"""
    return not any(_tool_on(text, t) for t in _TOOLSETS_OFF)


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_TOOLS_LIST_LINE = re.compile(r"^\s*(?:[✓✗]\s*)?(enabled|disabled)\s+([A-Za-z0-9_.:@/-]+)")


def _cli_tools_state(exe, runner=None):
    """{toolset: encendido?} según la FUENTE OFICIAL, `hermes --profile <p>
    tools list` (v0.18.2: «✓ enabled  web …» / «✗ disabled  memory …», ya
    resuelto con compuestos y `agent.disabled_toolsets`; sin traducir). {} si
    el CLI falla o su salida no se reconoce: quien lo use lo toma como
    «encendido» (fail-closed). Solo fuera del camino feliz."""
    try:
        r = _run(_base(exe) + ["tools", "list"], runner=runner, timeout=60)
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
            and _toolsets_off(cfg)
            and _context_chars(cfg) >= CONTEXT_FILE_CHARS
            and _hooks_state(cfg) == "ours")


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
        # TimeoutExpired crudo con la ruta del .cmd.
        return False, ("Hermes no respondió en %d s (`hermes %s`). La primera vez que corre en "
                       "esta máquina prepara su entorno y puede tardar unos minutos: corre "
                       "`hermes --version` en otra terminal, espera a que termine y vuelve a "
                       "abrir el agente" % (int(e.timeout or 0), " ".join(
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
    if not _toolsets_off(_read_text(cfgp)):
        # Nuestro lector del YAML es conservador (lo que no reconoce cuenta como
        # encendido); la FUENTE OFICIAL decide: `tools list` da el estado ya
        # resuelto por Hermes. Solo se apaga lo que Hermes dice encendido, y se
        # verifica por el estado (config, luego CLI), nunca por el código de
        # salida. Sin respuesta reconocible del CLI, todo cuenta como encendido.
        st = _cli_tools_state(exe, runner)
        pending = [t for t in _TOOLSETS_OFF if st.get(t) is not False]
        if pending:
            _run(_base(exe) + ["tools", "disable"] + pending, runner=runner, timeout=60)
            if _LEAK_TOOL in pending and _tool_on(_read_text(cfgp), _LEAK_TOOL):
                # Si las dos juntas fallan (p. ej. Hermes renombró `memory`).
                _run(_base(exe) + ["tools", "disable", _LEAK_TOOL],
                     runner=runner, timeout=60)
            still = [t for t in pending if _tool_on(_read_text(cfgp), t)]
            if still:
                st = _cli_tools_state(exe, runner)
                still = [t for t in still if st.get(t) is not False]
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
        _write_atomic(cfgp, _with_hook(text))
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


def run_open(brain, tab=""):
    """Registra una corrida de Hermes en este cerebro → token (o '' si no se
    pudo: falla-suave, la captura vuelve al criterio de ventana)."""
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
        keep.append({"id": token, "brain": os.path.realpath(brain or ""), "tab": tab,
                     "pid": os.getpid(), "t0": now, "t1": None, "sessions": []})
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
    `--full` (v0.18.x) cae a `status`. 90 s: el primer `status` de un
    HERMES_HOME nuevo prepara sus dependencias."""
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
    registro exportado con cwd exacto, origen y started_at verificados."""
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
        if str(d.get("source") or "") in _FOREIGN_SOURCES:
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
    cmd = _base(exe) + ["--oneshot=" + (prompt or ""), "--usage-file", usage]
    if model:
        cmd += ["-m", model]
    import secret_store
    env = secret_store.engine_env()   # el motor no hereda la bóveda
    env["HERMES_SESSION_SOURCE"] = "tool"
    env.pop("WORKSPACE_HERMES_RUN", None)        # un turno headless no es de la pestaña
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
def inject_context(cfg, session_context=""):
    """AGENTS.md puntero → doc de identidad, con el NÚCLEO de identidad
    incrustado como copia generada (brain_identity.embed_core) + bloque
    invisible de la pestaña. Misma marca y mismo corte que los demás (archivo
    compartido). Por qué la copia: Hermes no expande imports y no tiene
    mensaje de arranque, así que «lee BRAIN.md» depende del modelo; con un
    modelo débil el agente arrancaba sin carácter ni socio (VERIFICADO
    2026-10-15). Un documento que el escáner de Hermes bloquearía no se
    incrusta; si el archivo completo dispararía el bloqueo, va sin copia.
    Devuelve el dict de inject_agents_md + 'embed' (lo que entró/faltó)."""
    from engines.opencode import inject_agents_md
    emb = {}
    try:
        import brain_identity as _bi
        brain = (cfg or {}).get("_brain", "")
        if brain and os.path.isdir(brain):
            emb = _bi.embed_core(brain, cfg, reject=scan_context)
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
        bits.append("la identidad no cupo entera (%s queda para que el agente lo lea)"
                    % ", ".join(cut))
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


def _interactive_argv(passthrough, resume_sid=""):
    """argv DESPUÉS de `hermes`: perfil propio (SOLO para este comando: el
    default del socio no cambia) + REPL (sin subcomando) + `--resume <id>` de
    la pestaña. Sin `-m` (manda la config del perfil). Un --resume/--continue
    del socio va tal cual y gana."""
    args = [str(a) for a in passthrough or []]
    argv = ["--profile", _profile()]
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
        print("  cerebro     : %s  (cwd de la sesión)" % brain)
        print("  identidad   : AGENTS.md puntero → %s + copia generada del núcleo "
              "(%s + BOOT/NN + perfil del socio); Hermes no crea archivos en el "
              "cerebro" % (_identity_doc(cfg), _identity_doc(cfg)))
        print("  pestañas    : picker compartido — cada pestaña con su sesión de "
              "Hermes (atada al cerrar, `--resume <id>` al reabrir)")
        print("  cierre      : export oficial de la sesión (`hermes sessions export`) "
              "→ respaldo y revisión de skills (si está encendida)")
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
    if wired and not approved:
        print("WORKSPACE: Hermes te pedirá aprobar el hook de Workspace (%s → "
              "hooks/%s): añade tu tono a cada mensaje y anota qué pestaña es dueña "
              "de la sesión; no guarda ni envía nada más. Responde «y» una vez; con "
              "«N» el tono solo llega al arrancar." % (_HOOK_EVENT,
                                                     os.path.basename(_HOOK_SCRIPT)))

    if not _provider_gate(exe, status()):
        sys.exit(0)
    over = overrides_in_root(brain)
    if over:
        print("WORKSPACE: %s en la raíz del cerebro le gana a AGENTS.md en Hermes "
              "— la identidad del agente puede no cargarse." % ", ".join(over))

    tab, resume_sid, session_blk = None, "", ""
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

    inj = inject_context(cfg, session_context=session_blk)
    if not inj.get("ok") and inj.get("detail"):
        print("WORKSPACE: identidad NO inyectada (%s) — Hermes arrancará "
              "genérico." % inj["detail"])
    elif tab and session_blk and inj.get("action") == "custom" and not inj.get("session"):
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

    argv = _interactive_argv(passthrough, resume_sid=resume_sid)

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
            merged = "\n\n".join(p for p in (session_blk, (ctx or "").strip()) if p)
            if not merged:
                return
            r = inject_context(cfg, session_context=merged)
            if r.get("ok") and (r.get("action") != "custom"
                                or r.get("session") == "appended"):
                _doc_dirty.append(True)
            elif (ctx or "").strip():
                print("[WORKSPACE · contexto de arranque]\n%s\n" % ctx.strip())
        except Exception:
            pass

    t0 = time.time()
    # Corrida registrada ANTES de abrir: el hook por turno anota en ella las
    # sesiones de ESTA pestaña (env heredado por Hermes y su hook).
    run = run_open(brain, tab[1] if tab else "")
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
    if session_blk or _doc_dirty:
        try:
            inject_context(cfg)
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
