"""WORKSPACE · engines/copilot.py — motor GitHub Copilot CLI (binario `copilot`).

Hace ejecutable un agente sobre el CLI oficial de GitHub Copilot, con la cuenta
de Copilot del socio. Vendor-neutral, enchufable por nombre — dispatch.py lo
carga solo ("copilot" → engines/copilot.py); NO se toca el dispatcher
(engines/CONTRACT.md).

🔴 INVARIANTE DE SEGURIDAD (mismo de codex/opencode): la credencial la gestiona
el BINARIO OFICIAL (`copilot login`: llavero del sistema, o las variables
COPILOT_GITHUB_TOKEN / GH_TOKEN / GITHUB_TOKEN, o el token de `gh`; o un
proveedor propio BYOK con COPILOT_PROVIDER_BASE_URL). WORKSPACE JAMÁS lee,
extrae ni reusa el token: el estado se consulta solo por presencia (nombres de
variables, el item del llavero sin su secreto, `gh auth status`). De
~/.copilot/config.json (puede guardar el token en texto plano si no hay llavero)
solo se mira la lista `loggedInUsers`; el token se descarta sin usarse
(_usuarios_en_config, excepción aprobada por el dueño 2026-11-06).

Tres formas de correr (contrato de WORKSPACE):
  · INTERACTIVO — `launch()`: banner + wrapper neutral
    (interactive.run_official_cli_interactive: session_start → `copilot` en el
    cerebro → session_end). Es el `dispatch.py <agente> --engine copilot`.
  · HEADLESS one-shot — `run_turn()`: `copilot --prompt=<mensaje> -s`.
  · INGESTA — `<COPILOT_HOME>/session-state/<id>/events.jsonl`:
    session_continuity.capture_copilot lo respalda envuelto y
    neutral_transcript.parse_copilot saca el diálogo visible.

VERIFICADO con el binario 1.0.105 (npm `@github/copilot`, macOS, 2026-10-28),
en un HOME desechable, sin cuenta: con un proveedor BYOK FALSO local
(COPILOT_PROVIDER_BASE_URL → servidor OpenAI-compatible de prueba; Copilot no
pide cuenta de GitHub con BYOK), sin costo:
  · Lee como instrucciones, TODOS fusionados en el prompt de sistema, el
    `AGENTS.md`, el `CLAUDE.md` y el `GEMINI.md` de la carpeta de trabajo
    (`copilot instruction list --json`), y EXPANDE `@BRAIN.md` del CLAUDE.md
    puntero. Además el adapter genera el MISMO `AGENTS.md` puntero de
    codex/opencode (marca WORKSPACE:GENERATED) con el bloque INVISIBLE de la
    pestaña; al retomar, Copilot vuelve a leerlo (el tono nuevo llega).
  · `--session-id <uuid>` CREA la sesión con ese id si no existe, y la retoma
    si existe (evento session.resume, con el historial); un id que no es UUID
    falla («not a valid UUID»). Por eso, como Claude Code, Workspace genera el
    id de la pestaña y lo ata ANTES de abrir: determinista, y dos pestañas a la
    vez no se pisan (dos ventanas en el mismo cerebro, VERIFICADO).
  · `-i <mensaje>` abre interactivo y manda ese mensaje (el arranque del
    cerebro). Cerrar la ventana (SIGHUP) deja el registro cerrado
    (session.shutdown).
  · En la carpeta de trabajo LEE sin pedir permiso; fuera de ella, la terminal
    y escribir piden aprobación (sin ventana: se niegan). La primera vez en un
    cerebro pregunta «¿confías en esta carpeta?» (lo guarda en config.json,
    que es del CLI: Workspace no lo escribe). Copilot no escribe nada en el
    cerebro (su estado vive en ~/.copilot).
  · Sin cuenta: `-p` sale con 1 y «No authentication information found.».

Permisos (mínimo invasivo): nada escrito en la config de Copilot; todo va POR
CORRIDA. Copilot ya lee el cerebro sin preguntar. Con autonomía «brain» (la
de fábrica) ESCRIBE en su cerebro sin preguntar: `--allow-tool=write(<cerebro
real>/**)` más unos `--deny-tool` (la salida por `..` y la config de proyecto
de Copilot que corre comandos). Fuera del cerebro sigue preguntando; con
«ask», nada. Ver brain_write_args(). Guardar memoria no pide permiso: Workspace le da la
herramienta MCP de memoria (memoria_mcp: `guardar_nota`, `guardar_resumen`,
`ver_memoria`, sin terminal) POR CORRIDA, con las opciones documentadas
`--additional-mcp-config=@<archivo de Workspace>` y `--allow-tool=
workspace-memoria(<herramienta>)` (doc: «SERVER-NAME(tool)»); nada escrito en
~/.copilot. VERIFICADO 1.0.105 con un proveedor falso: la herramienta corre
sin preguntar y guarda en la pestaña; sin el `--allow-tool` y cualquier
comando de terminal se niegan sin ventana. Antes iba por la RUTA de un comando
(`--allow-tool=shell(<ruta>)`): en Windows se colaba otro comando (comillas
tipográficas que PowerShell entiende y el analizador de bash no). Y cada
corrida lleva `--excluded-tools=session_store_sql` (AISLAMIENTO_ARG): sin
ella, un agente leía las conversaciones de Copilot de los demás.

HOOKS DEL CEREBRO: Copilot también corre los hooks de Claude Code que Workspace
cabla en `<cerebro>/.claude/settings.local.json` (los llama «repo settings»).
En Windows los corre con PowerShell, donde `"PY" "RUNNER" <evento>` no parsea,
y `preToolUse` falla cerrado: TODA terminal salía «Denied by preToolUse hook
from "repo settings" (hook errored)». Por eso, en Windows, cada hook lleva
también la clave `powershell` (install.runner_cmd_powershell), que Copilot usa
en lugar de `command` y Claude Code ignora (VERIFICADO 2026-11-05, Windows 11,
1.0.105 de WinGet, PowerShell 7.6.9: la terminal corre y el hook recibe su JSON).
Su `SessionStart`, `UserPromptSubmit` y `SessionEnd` ahí (session_id,
timestamp, cwd; SIN transcript_path) son ecos del inicio y el cierre que ya
emite el wrapper, y lo que devuelven no llega a su modelo (VERIFICADO
2026-11-06 en macOS con un proveedor falso, con `-p` y en un pty con `-i`):
workspace_hook.py no los despacha (events.eco_de_otro_motor, ECO_DESCARTADO).

BARRA: la statusLine NATIVA de Copilot (`statusLine` del settings.json de
USUARIO; la del repo no la activa, VERIFICADO 1.0.105) apunta al shim estable
`~/.local/bin/workspace-copilot-statusline` y pinta la línea de Workspace
debajo del pie de Copilot (agente · pestaña · modelo · contexto · uso de la
sesión · versión del cerebro). Se re-asegura en cada arranque; una statusLine
del socio JAMÁS se toca. Ver motor_statusline.

🔴 EL HARNESS NO FIJA MODELO (regla de producto): el modelo es el de la cuenta
o la config del socio (`/model`, `COPILOT_MODEL`). Ningún `--model` en el
launch; en run_turn, `model` es solo override explícito de smokes/eval.

A-VERIFICAR (necesita una cuenta de Copilot): la lectura de la cuenta
(llavero `copilot-cli`, doc oficial), un turno real con un modelo de Copilot,
Windows (winget / npm `copilot.cmd`).

Cero dependencias (stdlib, 3.9+). Mac/Windows/Linux. Falla-suave.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import uuid

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import arbol_procesos  # noqa: E402  (Windows: al vencer el tiempo muere el árbol entero)

import rutas_protegidas  # noqa: E402 — la raíz ya está en sys.path

META = {"name": "copilot", "needs": ["copilot"], "auth": "subscription"}

#: Matriz de capacidades (contrato harness-os §3; la consume harnesses.py).
#: TODAS las claves de capabilities.ENGINE_KEYS (lo exige test_capabilities).
CAPABILITIES = {
    "launch": "wrapper",              # CLI oficial envuelto en el ciclo neutral
    "inject_context": "project-doc",  # AGENTS.md puntero (+ su CLAUDE.md/@BRAIN.md)
    "mcp": True,                      # MCP nativo (~/.copilot/mcp-config.json, del socio)
    "hooks": "wrapper",               # Copilot trae hooks propios; NO se cablean
                                      # (doble disparo con el session_end del wrapper)
    "sessions": "workspace",          # pestañas del registro neutral ↔ --session-id
    "status_live": False,             # sin now.json desde dentro (sin hooks por turno)
    "headless": True,                 # run_turn (copilot --prompt=… -s, VERIFICADO con BYOK)
    "statusline": "native-config",    # su statusLine nativa (settings.json de
                                      # usuario) → shim de Workspace; la del
                                      # socio gana (motor_statusline)
}

BINARY = "copilot"

#: Versiones del CLI con las que se VERIFICARON las lecturas de este adapter
#: (engine_versions: doctor avisa si la instalada es de otra línea; lo exige
#: tests/test_engine_versions.py). 1.0.105 = npm @github/copilot, macOS.
VERIFIED_VERSIONS = ("1.0.105",)

#: Variables de credencial que Copilot mira, en su orden (`copilot login
#: --help`). Solo se mira si EXISTEN (nombre), jamás su valor.
TOKEN_ENVS = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
#: Proveedor propio (BYOK): con él Copilot no necesita cuenta de GitHub
#: (`copilot help environment`; VERIFICADO con un proveedor falso local).
BYOK_ENV = "COPILOT_PROVIDER_BASE_URL"
#: Servicio del llavero donde `copilot login` guarda el token (doc oficial).
KEYCHAIN_SERVICE = "copilot-cli"

_SESSION_FLAGS = ("-r", "--resume", "--continue", "--session-id", "--connect")
#: AISLAMIENTO ENTRE AGENTES (invariante de Workspace). El almacén de sesiones
#: de Copilot (`~/.copilot/session-store.db`) es uno por usuario: con su
#: herramienta `session_store_sql` el agente B leyó la conversación del A
#: (VERIFICADO 1.0.105, runbooks/agregar-motor.md «Aislamiento»). Cada corrida
#: la quita (`--excluded-tools`, VERIFICADO: la herramienta desaparece; nada
#: escrito). La memoria de la pestaña cubre lo que daba.
AISLAMIENTO_ARG = "--excluded-tools=session_store_sql"
#: Si el socio pasa las suyas, ganan (la nota del arranque lo dice).
_TOOL_FLAGS_DEL_SOCIO = ("--excluded-tools", "--available-tools")
_UUID_RX = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# ── escribir en su cerebro sin preguntar (autonomía «brain») ────────────────
# Doc: `copilot help permissions` — «write(path?) Matches tools that create
# and modify files, except shell tool invocations […] use an absolute path»;
# «Denial rules always take precedence over allow rules, even
# --allow-all-tools». Lo demás, VERIFICADO de caja negra con 1.0.105 (macOS,
# HOME desechable, proveedor BYOK falso que pide `create`/`edit`;
# tests/test_motores_copilot.py · EscrituraBinarioReal):
#   · `write(<carpeta>)` NO cubre lo de adentro (compara la ruta exacta);
#     `<carpeta>/*` cubre un nivel y `<carpeta>/**` todo lo de adentro,
#     incluidas carpetas con punto (.obsidian).
#   · El hermano con prefijo parecido (`<cerebro>-x/`) y lo de fuera piden.
#   · Copilot compara la ruta que pide el modelo Y la resuelta: con la regla
#     sobre la ruta REAL valen las dos (/var/… y /private/var/…, relativa);
#     con la no-real, la real no. Por eso la regla usa os.path.realpath.
#   · `**` también acepta `..`: `<cerebro>/../<otra>` se escribía sin
#     preguntar si <otra> estaba en la temporal del sistema o en un --add-dir.
#     Lo cierra `--deny-tool=write(<cerebro>/**/../**)` (también niega
#     `sub/../x` dentro: el modelo reintenta con la ruta limpia).
#   · `[ ] * ? { }` en el nombre son comodines (`Cerebro [v2]` no se cubría y
#     sí `Cerebro v`): se escapan como clase de un carácter (`[[]`, `[*]`…).
#     Un paréntesis no se puede escribir: Copilot rechaza la regla y NO ABRE
#     («Invalid rule format»). Con paréntesis en la ruta no va regla (pide).
#   · Compara sin mayúsculas en macOS (`.MCP.json` cae en el deny de
#     `.mcp.json`). Un enlace dentro del cerebro hacia fuera pide, salvo si
#     apunta a la temporal del sistema (que Copilot deja tocar de fábrica).
#: Config de PROYECTO que algún motor, git u Obsidian carga del cerebro (hooks,
#: MCP, agentes, skills con permisos, plugins): escribirla sin preguntar le
#: daría al agente permisos para la siguiente sesión, de Copilot o de OTRO
#: motor (Copilot escribía `.kiro/agents/x.json` y Kiro lo cargaba). La lista
#: es UNA para todos los motores, con la doc de cada entrada:
#: rutas_protegidas.PROTEGIDAS. Se niega (`--deny-tool`): el deny de Copilot
#: no ofrece aprobar, así que esas rutas quedan negadas, no preguntadas.
#: Las instrucciones (AGENTS.md, BRAIN.md…) sí se escriben: son el mismo riesgo
#: que ya tiene cualquier motor con su cerebro y no abren una puerta nueva.
CONFIG_CARPETAS = rutas_protegidas.CARPETAS
CONFIG_ARCHIVOS = rutas_protegidas.ARCHIVOS + rutas_protegidas.EXACTAS
#: Comodines de la regla que se escapan como clase de un carácter.
_COMODINES = "[]*?{}"
#: Lo que la regla no puede llevar (Copilot no abre) o no se sabe escapar.
_NO_EXPRESABLE = "()\n\r\t"
#: Lo que el cmd.exe del lanzador .cmd de npm (Windows) vuelve a interpretar en
#: un argumento (memoria._ARGV_RARO): con eso en la ruta, tampoco va regla.
_RARO_CMD = "\"%^!<>|&"
#: Las del socio que ganan: con ellas, Workspace no pone las suyas.
_TODO_PERMITIDO = ("--allow-all-tools", "--allow-all", "--yolo")
_PERMISO_DEL_SOCIO = ("--allow-tool", "--deny-tool")
_WRITE_RX = re.compile(r"^write(\(.*\))?$")
#: `COPILOT_ALLOW_ALL` verdadero (doc: «"true", "1", "yes", "on", or "y"»).
_ALLOW_ALL_ENV = "COPILOT_ALLOW_ALL"
_VERDADERO = ("true", "1", "yes", "on", "y")
#: Windows: tope ESTIMADO de la línea de comandos con las reglas. El lanzador
#: `copilot.cmd` de npm pasa por cmd.exe, que corta en 8191 caracteres; por
#: encima de esto no va regla (pide permiso como antes) y el arranque avisa.
_TOPE_ARGV_WIN = 7000
#: Lo que se reserva en la estimación para el resto del argv (binario,
#: herramienta de memoria, sesión, mensaje de arranque).
_MARGEN_ARGV = 1500
#: Windows: el `.git` como ARCHIVO, con lo que Windows quita al guardar
#: (`.git.`, `.git `, `.git::$DATA` = `.git`) y sin negar `.gitignore` ni
#: `.gitattributes`: la exacta + la clase de un carácter `[.: ]` seguida de
#: lo que sea.
_GIT_ARCHIVO_WIN = ("", "[.: ]*")


def _literal(ruta):
    """La ruta con sus comodines escapados (`[` → `[[]`, `*` → `[*]`…)."""
    return "".join("[%s]" % c if c in _COMODINES else c for c in ruta)


def _raices(brain, windows=None):
    """[(raíz, separador)] para las reglas. POSIX: la ruta REAL. Windows: la
    resuelta, con `\\` (UNA forma: Copilot 1.0.105 normaliza separadores y
    letra de unidad, VERIFICADO en Windows 11 en la PC; con las dos formas, un
    cerebro de ~118 caracteres pasaba de los 8191 de cmd.exe). [] si no hay
    ruta o es la raíz del disco."""
    win = (os.name == "nt") if windows is None else windows
    if not brain:
        return []
    if win:
        import ntpath
        import pathguard
        # pathguard._real: el realpath de Python 3.9 en Windows LANZA con una
        # ruta de red que no responde (WinError 53, \\srv\share); abrir Copilot
        # en ese cerebro tronaba (VERIFICADO 2026-11-05, suite con 3.9.13)
        p = pathguard._real(brain) if os.name == "nt" else brain
        p = ntpath.normpath(p)
        if p.startswith("\\\\?\\UNC\\"):
            p = "\\\\" + p[8:]
        elif p.startswith("\\\\?\\"):
            p = p[4:]
        drive, rest = ntpath.splitdrive(p)
        rest = rest.rstrip("\\/")
        if not drive or not rest:
            return []
        return [(drive + rest, "\\")]
    import posixpath
    p = posixpath.normpath(os.path.realpath(brain)).rstrip("/")
    return [(p, "/")] if p else []


def _socio_elige_escritura(passthrough, env=None):
    """¿El socio ya decidió los permisos de escritura? (`--allow-all-tools`,
    `--allow-all`, `--yolo`, un `--allow-tool`/`--deny-tool` de `write`, o
    COPILOT_ALLOW_ALL verdadero). Su elección gana: Workspace no agrega nada
    (ni sus deny, que la recortarían)."""
    args = [str(a) for a in passthrough or ()]
    for i, a in enumerate(args):
        if a in _TODO_PERMITIDO or a.startswith(tuple(f + "=" for f in _TODO_PERMITIDO)):
            return True
        for f in _PERMISO_DEL_SOCIO:
            if a.startswith(f + "=") and _WRITE_RX.match(a[len(f) + 1:].strip("'\"")):
                return True
            if a == f and any(_WRITE_RX.match(v.strip("'\"")) for v in args[i + 1:i + 3]):
                return True
    v = str((os.environ if env is None else env).get(_ALLOW_ALL_ENV) or "")
    return v.strip().lower() in _VERDADERO


def _autonomia(cfg):
    try:
        from engines import _ui
        return _ui.autonomy(cfg)
    except Exception:
        v = str((cfg or {}).get("autonomy") or "").strip().lower()
        return "ask" if v == "ask" else "brain"


def brain_write_args(cfg, brain, passthrough=(), windows=None, env=None, exe=None):
    """(args, motivo). Con autonomía «brain» (y un «full» de antes, que se lee
    «brain»): escribir en SU cerebro sin preguntar, por corrida:
      --allow-tool=write(<cerebro real>/**)
      --deny-tool=write(<cerebro real>/**/../**)         (salir por `..`)
      --deny-tool=write(<cerebro real>/<config>/**)       (CONFIG_CARPETAS)
      --deny-tool=write(<cerebro real>/<archivo>)         (CONFIG_ARCHIVOS)
    (rutas_protegidas: la config de TODOS los motores, git y Obsidian)
    En Windows, cada parte del nombre protegido lleva `*` al final
    (`<cerebro>\\.kiro*\\**`, `<cerebro>\\.claude*\\settings.json*`): Windows
    guarda `.kiro.`, `.kiro ` y `.kiro::$DATA` como `.kiro`, y el deny de
    Copilot compara el nombre tal cual lo pide el modelo (VERIFICADO
    2026-11-06 en Windows 11 con un archivo; `.kiro.\\settings\\mcp.json` creaba
    `.kiro\\settings\\…`). El `.git` como archivo va exacto + `.git[.: ]*`
    (no niega `.gitignore`). Los nombres cortos 8.3 (`GITHUB~1`) los niega
    Copilot solo en carpetas que existen (VERIFICADO en la PC).
    Nunca `write` sin ruta ni --allow-all-tools. motivo: "ok" | "ask" (no
    cambia nada) | "socio" (sus permisos ganan) | "sin_cerebro" | "ruta" (la
    ruta lleva un paréntesis, que Copilot no acepta, o algo que el cmd.exe
    del lanzador .cmd reinterpreta: sin regla, pide permiso como antes) |
    "largo" (Windows: la línea de comandos estimada pasaría de
    _TOPE_ARGV_WIN; sin regla, pide permiso como antes)."""
    if _autonomia(cfg) == "ask":
        return [], "ask"
    if _socio_elige_escritura(passthrough, env):
        return [], "socio"
    raices = _raices(brain, windows)
    if not raices:
        return [], "sin_cerebro"
    raro = _NO_EXPRESABLE
    try:
        import memoria
        if memoria.pasa_por_cmd(exe):
            raro += _RARO_CMD
    except Exception:
        pass
    # en Mac/Linux, una barra invertida en el nombre tampoco se sabe escapar
    if any(c in r for r, _s in raices for c in raro) \
            or any(sep == "/" and "\\" in r for r, sep in raices):
        return [], "ruta"
    win = (os.name == "nt") if windows is None else bool(windows)
    allow, deny = [], []
    def nombre(rel):
        # Windows: `*` al final de CADA parte (`.claude.\\skills` = `.claude\\skills`)
        partes = rel.split("/")
        return sep.join(c + "*" for c in partes) if win else sep.join(partes)

    for raiz, sep in raices:
        base = _literal(raiz) + sep
        allow.append("--allow-tool=write(%s**)" % base)
        deny.append("--deny-tool=write(%s**%s..%s**)" % (base, sep, sep))
        for d in CONFIG_CARPETAS:
            deny.append("--deny-tool=write(%s%s%s**)" % (base, nombre(d), sep))
        for f in rutas_protegidas.ARCHIVOS:
            deny.append("--deny-tool=write(%s%s)" % (base, nombre(f)))
        for f in rutas_protegidas.EXACTAS:
            for cola in (_GIT_ARCHIVO_WIN if win else ("",)):
                deny.append("--deny-tool=write(%s%s%s)" % (base, f.replace("/", sep), cola))
    reglas = allow + deny
    if win:
        estimado = (len(str(exe or BINARY)) + _MARGEN_ARGV
                    + sum(len(str(a)) + 3 for a in list(passthrough or ()) + reglas))
        if estimado > _TOPE_ARGV_WIN:
            return [], "largo"
    return reglas, "ok"


def _t(key, es, en=None, **kw):
    try:
        import workspace_status
        return workspace_status.t(key, es, en, **kw)
    except Exception:
        return es.format(**kw) if kw else es


def write_plan_line(cfg, brain, passthrough=(), exe=None):
    """La línea de escritura del plan de arranque (solo lee)."""
    _a, motivo = brain_write_args(cfg, brain, passthrough, exe=exe)
    if motivo == "ask":
        return _t("motorbar.copilot.ask",
                  "ask — pregunta antes de crear o editar, también en el cerebro",
                  "ask — asks before creating or editing, also in the brain")
    if motivo == "socio":
        return _t("motorbar.copilot.socio",
                  "tus permisos de escritura de Copilot ganan (Workspace no agrega los suyos)",
                  "your Copilot write permissions win (Workspace adds none of its own)")
    if motivo == "largo":
        return _t("motorbar.copilot.largo",
                  "la ruta del cerebro es tan larga que las reglas no caben en la línea de "
                  "comandos de Windows: pregunta antes de escribir, también en el cerebro",
                  "the brain path is so long that the rules don't fit in the Windows command "
                  "line: it asks before writing, also in the brain")
    if motivo == "ruta":
        return _t("motorbar.copilot.ruta",
                  "la ruta del cerebro lleva caracteres que no caben en la regla de Copilot "
                  "(paréntesis; en Windows con el lanzador .cmd, también \" % ^ ! < > | &): "
                  "pregunta antes de escribir, también en el cerebro",
                  "the brain path has characters that do not fit in a Copilot rule "
                  "(parentheses; on Windows with the .cmd launcher, also \" % ^ ! < > | &): it "
                  "asks before writing, also in the brain")
    return _t("motorbar.copilot.brain",
              "brain — escribe en su cerebro sin preguntar (`write(<cerebro>/**)` por "
              "corrida); fuera del cerebro, la terminal y su config de Copilot "
              "(.github/, .mcp.json, .claude/settings…) piden permiso o se niegan",
              "brain — writes in its brain without asking (`write(<brain>/**)` per run); "
              "outside the brain, the terminal and its Copilot config (.github/, .mcp.json, "
              ".claude/settings…) ask or are denied")


def _exe(override=None):
    """Ruta al binario. override=None → PATH; override="" → no hay (tests);
    override="/ruta" → esa ruta."""
    if override is None:
        return shutil.which(BINARY)
    return override or None


def _env_motor():
    """El env para correr procesos del motor: sin NADA de la bóveda
    (secret_store.engine_env). Falla-suave: sin secret_store, el heredado."""
    try:
        import secret_store
        return secret_store.engine_env()
    except Exception:
        return None


# ── macOS: no ejecutar un programa que Gatekeeper retiene ───────────────────
def gatekeeper_block(exe=None):
    """None si macOS deja correr `copilot`; si no, {path, cask, files, why}
    (engine_gatekeeper.check). El cask `copilot-cli` (1.0.103) quedó retenido:
    cada `copilot …` abría «No se abrió copilot» (VERIFICADO 2026-10-28).
    Workspace NO lo ejecuta y Motores ofrece reinstalar con la receta oficial
    (npm, sin cuarentena)."""
    exe = exe or _exe()
    if not exe:
        return None
    try:
        import engine_gatekeeper as _gk
        info = _gk.check(exe)
        return dict(info, why=_gk.message(info)) if info else None
    except Exception:
        return None


def account_menu(active=None, exe=None):
    """«cuenta y proveedor» en Motores (engines_tui._account), según la cuenta.

    En Copilot la cuenta y el modelo se manejan DENTRO del programa
    (VERIFICADO 1.0.105, `copilot help commands`: /user «Manage signed-in
    accounts», /login, /logout, /model). Fuera solo hay `copilot login` (OAuth;
    con una cuenta ya puesta AGREGA otra, Copilot maneja varias) y `copilot
    config model …`, que escribiría la config del socio (Workspace no fija
    modelo). El proveedor propio (BYOK) son variables COPILOT_PROVIDER_*
    (`copilot help providers`): Workspace no las pone.
      · sin cuenta (False) → None: Motores corre `copilot login`;
      · con cuenta o sin saber → abrir Copilot (en una carpeta vacía), entrar
        con otra cuenta y la ayuda oficial de proveedor propio."""
    if active is False:
        return None
    return {"model": "/model", "account": "/user",
            "actions": [("open", [BINARY]), ("add", [BINARY, "login"]),
                        ("providers", [BINARY, "help", "providers"])]}


# ── estado del motor en disco (solo rutas; de config.json SOLO los usuarios) ─
def _usuarios_en_config(env=None):
    """¿Hay usuario con sesión en <copilot_home>/config.json? True/False, o
    None si el archivo no existe o no se puede leer.

    Excepción acotada a la regla «nunca config.json» (dueño, 2026-11-06): en
    Windows/Linux sin llavero Copilot guarda ahí la cuenta y el token en texto
    plano, y sin esto la sesión salía «no se pudo verificar» con la cuenta
    abierta. Se mira SOLO `loggedInUsers`; el resto del dict (incluido
    `authTokens`) se descarta en el acto: nunca se guarda, registra ni muestra."""
    p = os.path.join(copilot_home(env), "config.json")
    try:
        if not os.path.isfile(p) or os.path.getsize(p) > 1_000_000:
            return None
        with open(p, "rb") as fh:
            texto = fh.read().decode("utf-8-sig", errors="replace")
        # Copilot lo escribe como JSONC: abre con líneas `// …` (VERIFICADO
        # 1.0.106, Windows). Solo se quitan líneas que EMPIEZAN con //: un
        # `//` dentro de un valor (https://…) no se toca.
        texto = "\n".join(ln for ln in texto.splitlines()
                          if not ln.lstrip().startswith("//"))
        data = json.loads(texto)
        del texto
        usuarios = data.get("loggedInUsers") if isinstance(data, dict) else None
        del data
        if usuarios is None:
            return False
        return bool(isinstance(usuarios, list) and usuarios)
    except Exception:
        return None


def copilot_home(env=None):
    """Carpeta de estado de Copilot: $COPILOT_HOME o ~/.copilot (`copilot help
    environment`: COPILOT_HOME reemplaza la ruta entera)."""
    env = os.environ if env is None else env
    h = str(env.get("COPILOT_HOME") or "").strip()
    return os.path.abspath(os.path.expanduser(h)) if h else \
        os.path.join(os.path.expanduser("~"), ".copilot")


def _valid_session_id(sid):
    """¿Es un UUID canónico (minúsculas)? Es lo que Workspace genera y lo
    único con lo que `--session-id` crea una sesión nueva."""
    return bool(_UUID_RX.fullmatch(str(sid or "")))


def new_session_id():
    """Id nuevo para una pestaña: UUID v4."""
    return str(uuid.uuid4())


def session_dir(sid, env=None):
    return os.path.join(copilot_home(env), "session-state", str(sid))


def events_path(sid, env=None):
    """El registro de eventos de la sesión (append-only; VERIFICADO 1.0.105)."""
    return os.path.join(session_dir(sid, env), "events.jsonl")


def session_has_dialogue(sid, env=None):
    """¿La sesión `sid` ya tiene una conversación (algún mensaje del socio)?
    Copilot crea la carpeta de la sesión aunque el turno falle (sin cuenta,
    VERIFICADO): la carpeta sola no prueba que haya algo que retomar. Lee por
    líneas y para en el primer `user.message`. Falla-suave: False."""
    if not _valid_session_id(sid):
        return False
    try:
        with open(events_path(sid, env), "rb") as fh:
            for raw in fh:
                if b'"user.message"' in raw:
                    return True
    except OSError:
        pass
    return False


# ── cuenta: presencia, nunca el token ───────────────────────────────────────
def _run_quiet(cmd, runner=None, timeout=10):
    if runner is not None:
        return runner(cmd)
    return arbol_procesos.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace",
                              stdin=subprocess.DEVNULL, env=_env_motor())


def _auth_signal(runner=None, env=None, platform=None, gh=None, security=None):
    """Señal de cuenta SIN tocar credenciales → 'byok' | 'env:<NOMBRE>' |
    'keychain' | 'gh' (hay con qué entrar), '' (Copilot no tendría nada) o
    None (no se puede saber). En el orden de búsqueda de Copilot:
      1. Proveedor propio (COPILOT_PROVIDER_BASE_URL): no necesita GitHub.
      2. COPILOT_GITHUB_TOKEN / GH_TOKEN / GITHUB_TOKEN en el env del motor
         (solo si existen; el valor no se lee).
      3. macOS: el item `copilot-cli` del llavero, SIN su secreto
         (`security find-generic-password -s copilot-cli`, sin -w/-g: el
         chequeo de la guía oficial; rc 44 = no hay item, VERIFICADO).
      4. `gh auth status` (Copilot usa el token de gh si no hay otro).
    «Sin cuenta» ('') solo si el llavero dice explícitamente que no hay item y
    tampoco existe ~/.copilot/config.json (donde Copilot guarda el token en
    texto plano cuando no hay llavero). En Windows/Linux, sin variable ni gh,
    es «no sé». `runner`/`env`/`platform`/`gh`/`security` son knobs de test."""
    env = _env_motor() if env is None else env
    env = env if env is not None else os.environ
    if str(env.get(BYOK_ENV) or "").strip():
        return "byok"
    for name in TOKEN_ENVS:
        if str(env.get(name) or "").strip():
            return "env:" + name
    platform = platform or sys.platform
    keychain_none = False
    try:
        if platform == "darwin":
            sec = security if security is not None else "/usr/bin/security"
            if sec and (runner is not None or os.path.isfile(sec)):
                r = _run_quiet([sec, "find-generic-password", "-s", KEYCHAIN_SERVICE],
                               runner=runner)
                rc = getattr(r, "returncode", 1)
                if rc == 0:
                    return "keychain"
                keychain_none = rc == 44      # errSecItemNotFound: no hay item
        ghx = gh if gh is not None else shutil.which("gh")
        if ghx:
            r = _run_quiet([ghx, "auth", "status"], runner=runner)
            if getattr(r, "returncode", 1) == 0:
                return "gh"
    except Exception:
        return None
    # 5. config.json de Copilot: SOLO su lista `loggedInUsers` (ver
    #    _usuarios_en_config). Ahí vive la cuenta en Windows/Linux sin
    #    llavero; antes esto quedaba en «no sé» con la sesión abierta.
    if _usuarios_en_config(env) is True:
        return "config"
    if keychain_none and not os.path.exists(os.path.join(copilot_home(env), "config.json")):
        return ""
    return None


def session_active(exe_override=None, runner=None, **kw):
    """¿Copilot tiene con qué entrar? True/False, o None si no se pudo saber
    (la UI lo muestra como desconocido, jamás «activa» a ciegas). Sin binario
    → False. Que la cuenta tenga Copilot (suscripción, política de la
    organización) solo lo sabe Copilot al abrir."""
    exe = _exe(exe_override)
    if not exe:
        return False
    sig = _auth_signal(runner=runner, **kw)
    return None if sig is None else bool(sig)


def available(exe_override=None):
    """LISTO para ejecutar agentes: binario en PATH (Copilot resuelve el login)."""
    return bool(_exe(exe_override))


def status(exe_override=None, runner=None, **kw):
    """Estado honesto del motor (doctor / plan / harnesses.registry). Solo
    inspecciona: binario en PATH + presencia de cuenta (sin tokens)."""
    exe = _exe(exe_override)
    blk = gatekeeper_block(exe) if exe else None
    if blk:
        return {"engine": "copilot", "binary": BINARY, "binary_in_path": True,
                "session_active": None, "ready": False, "gatekeeper": blk,
                "detail": blk["why"],
                "auth": "cuenta de GitHub con Copilot (`copilot login`) o proveedor "
                        "propio; WORKSPACE nunca usa, guarda ni muestra el token"}
    active = session_active(exe_override=exe or "", runner=runner, **kw) if exe else False
    return {"engine": "copilot", "binary": BINARY, "binary_in_path": bool(exe),
            "session_active": active,
            # ready = binario + cuenta (o desconocido: no se bloquea por una
            # lectura que no se pudo hacer; sí cuando no hay ninguna).
            "ready": bool(exe) and active is not False,
            "auth": "cuenta de GitHub con Copilot (`copilot login`) o proveedor "
                    "propio; WORKSPACE nunca usa, guarda ni muestra el token"}


# ── headless ────────────────────────────────────────────────────────────────
def run_turn(prompt, *, model=None, cwd=None, timeout=120, exe_override=None,
             runner=None, session_id=""):
    """UN turno HEADLESS: `copilot --prompt=<mensaje> -s --no-color
    --excluded-tools=session_store_sql` (-s = solo la respuesta, sin
    estadísticas; sin el buscador de sesiones de todos los agentes,
    AISLAMIENTO_ARG). Devuelve (ok, texto). VERIFICADO 1.0.105
    con un proveedor BYOK falso: la salida es solo la respuesta y sale con 0;
    sin cuenta sale con 1 y el error en stderr. Las herramientas que pedirían
    permiso se niegan solas (sin ventana). `session_id` (UUID) = el turno va a
    esa sesión (`--session-id`: la crea o la retoma, VERIFICADO). `runner`/
    `exe_override` son knobs de test (la suite jamás corre un Copilot real).

    El mensaje va como argumento con `--prompt=` (un texto que empiece con «-»
    no se cuela como opción, VERIFICADO). En Windows, si el binario es el
    lanzador .cmd de npm, cmd.exe relee cada argumento → va saneado en una
    línea (memoria.argv_seguro). Una respuesta vacía se trata como fallo."""
    exe = _exe(exe_override)
    if not exe:
        return False, "copilot no está en PATH"
    blk = gatekeeper_block(exe)
    if blk:
        return False, "copilot: " + blk["why"]
    text = prompt or ""
    try:
        import memoria
        if memoria.pasa_por_cmd(exe):
            text = memoria.argv_seguro(text, tope=7000)
    except Exception:
        pass
    cmd = [exe, "--prompt=" + text, "-s", "--no-color", AISLAMIENTO_ARG]
    if session_id and _valid_session_id(session_id):
        cmd += ["--session-id", session_id]
    if model:
        cmd += ["--model", model]
    try:
        if cwd:
            os.makedirs(cwd, exist_ok=True)
        import secret_store
        env = secret_store.engine_env()   # el motor no hereda la bóveda
        env["WORKSPACE_REVIEW_RUNNING"] = "1"    # anti-recursión, como codex/opencode/kiro
        if runner is not None:
            r = runner(cmd, cwd=cwd or None, env=env, timeout=timeout)
        else:
            r = arbol_procesos.run(cmd, cwd=cwd or None, env=env, timeout=timeout,
                                   stdin=subprocess.DEVNULL, capture_output=True)
        rc = getattr(r, "returncode", 1)
        raw = getattr(r, "stdout", b"") or b""
        out = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        if rc != 0:
            e = getattr(r, "stderr", b"") or b""
            err = e.decode("utf-8", "replace") if isinstance(e, bytes) else str(e)
            return False, "copilot -p exit %d: %s" % (rc, (err or out).strip()[:300])
        if not out.strip():
            return False, "copilot -p: sin respuesta"
        return True, out.strip()
    except subprocess.TimeoutExpired:
        return False, "copilot -p: timeout tras %ss" % timeout
    except OSError as e:
        return False, "copilot -p: no pude preparar la corrida: %s" % e
    except Exception as e:
        return False, "copilot -p: fallo al invocar: %s" % e


# ── inject_context: el MISMO AGENTS.md puntero de codex/opencode ────────────
def _identity_doc(cfg):
    try:
        from engines.codex import _identity_doc as _idoc
        return _idoc(cfg)
    except Exception:                   # pragma: no cover — defensa
        return "CLAUDE.md"


def inject_context(cfg, session_context=""):
    """Identidad del agente (contrato §3): el AGENTS.md puntero compartido
    (opencode.inject_agents_md, una sola implementación) + bloque INVISIBLE de
    la pestaña activa. Un AGENTS.md propio del socio conserva su contenido (el
    bloque va anexado, marcado, y se limpia al cerrar). Falla-suave."""
    try:
        from engines import opencode as _oc
        return _oc.inject_agents_md(cfg, session_context=session_context, engine="copilot")
    except Exception as e:
        return {"ok": False, "action": "skipped", "path": "",
                "detail": "%s: %s" % (type(e).__name__, e)}


def _banner(cfg):
    """Arranque visible mínimo (Windows-safe: sin glifos 0x2600–0x27BF)."""
    name = str(cfg.get("display") or cfg.get("name", "agente")).upper()
    tag = str(cfg.get("tagline", ""))
    C, D = "\033[38;5;111m", "\033[38;5;240m"
    try:                                   # tema del hub
        from engines import _ui
        C, D = _ui.theme_cols(C, D)
    except Exception:
        pass
    R = "\033[0m"; B = "\033[1m"
    bar = C + "═" * 52 + R
    try:
        sys.stdout.write("\033[2J\033[3J\033[H")
        print("\n  %s" % bar)
        print("    %s%s%s%s   %svía GitHub Copilot%s" % (B, C, name, R, D, R))
        if tag:
            print("    %s%s%s" % (D, tag, R))
        print("  %s\n" % bar)
        sys.stdout.flush()
    except Exception:
        pass


# ── pestañas ────────────────────────────────────────────────────────────────
def _has_session_flag(passthrough):
    """¿El socio eligió sesión a mano (`-r/--resume`, `--continue`,
    `--session-id`, `--connect`)? Su elección explícita gana y no se ata nada."""
    for a in passthrough or []:
        a = str(a)
        if a in _SESSION_FLAGS or a.startswith(("--resume=", "--session-id=", "--connect=")):
            return True
    return False


def _session_from_passthrough(passthrough):
    """El UUID de `--session-id X` / `--session-id=X` / `--resume=<uuid>` /
    `-r <uuid>` que pasó el socio, o '' (un nombre o un prefijo no se sabe a
    qué sesión llevan: captura honesta «missing»)."""
    args = [str(a) for a in passthrough or []]
    for i, a in enumerate(args):
        if a.startswith(("--session-id=", "--resume=")):
            sid = a.split("=", 1)[1]
        elif a in ("--session-id", "--resume", "-r") and i + 1 < len(args):
            sid = args[i + 1]
        else:
            continue
        sid = sid.strip().lower()
        if _valid_session_id(sid):
            return sid
    return ""


def socio_elige_herramientas(passthrough):
    """¿El socio pasó su propio `--excluded-tools`/`--available-tools`?"""
    return any(str(a) == f or str(a).startswith(f + "=")
               for a in passthrough or () for f in _TOOL_FLAGS_DEL_SOCIO)


def _interactive_argv(cfg, passthrough, session_id="", boot="", extra=()):
    """argv DESPUÉS de `copilot`: el aislamiento entre agentes
    (AISLAMIENTO_ARG, salvo que el socio elija sus herramientas), `extra` (la
    herramienta de memoria y su permiso, memoria_mcp.copilot_args()), la sesión de
    la pestaña (`--session-id <uuid>`), el passthrough del socio y, en una
    sesión NUEVA, el arranque del cerebro (`-i`: abre interactivo y manda ese
    mensaje). El harness NO fija modelo ni más permisos: un `--model`, una
    sesión o un `--allow-tool` que el socio pase a mano van tal cual y ganan."""
    args = list(passthrough or [])
    pre = [] if socio_elige_herramientas(args) else [AISLAMIENTO_ARG]
    pre += list(extra or ())
    if session_id and not _has_session_flag(args):
        pre += ["--session-id", session_id]
    out = pre + args
    if boot and not any(str(a) in ("-i", "--interactive", "-p", "--prompt")
                        or str(a).startswith(("--interactive=", "--prompt="))
                        for a in args):
        out += ["-i", boot]
    return out


def boot_message(cfg):
    """Mensaje de arranque de una sesión NUEVA (como codex/opencode)."""
    return ("Lee %s e inicia el cerebro. Al terminar, confirma en una línea breve."
            % _identity_doc(cfg))


def _plan(cfg, passthrough, brain, exe):
    line = "─" * 66
    print(line)
    print("  WORKSPACE · plan de arranque — motor COPILOT — agente: %s"
          % cfg.get("display", cfg.get("name")))
    print(line)
    print("  motor       : copilot  (GitHub Copilot CLI · cuenta del socio con "
          "`copilot login`; WORKSPACE nunca usa, guarda ni muestra el token)")
    print("  modelo      : el de tu cuenta o tu config de Copilot (Workspace no "
          "pasa --model)")
    print("  cerebro     : %s" % brain)
    print("  identidad   : AGENTS.md puntero → %s (inject_context; marca "
          "WORKSPACE:GENERATED compartida) + su CLAUDE.md, que Copilot también "
          "lee" % _identity_doc(cfg))
    print("  pestañas    : picker compartido + registro neutral — id UUID atado "
          "ANTES de abrir y `--session-id <id>` (crea o retoma); memoria de la "
          "pestaña INVISIBLE en el AGENTS.md")
    print("  permisos    : los de Copilot (lee el cerebro sin preguntar; la terminal "
          "y escribir fuera del cerebro piden aprobación), salvo:")
    print("  escritura   : " + write_plan_line(cfg, brain, passthrough, exe=exe))
    try:
        import memoria_mcp
        print("  memoria     : " + memoria_mcp.plan_line("copilot", brain))
    except Exception:
        pass
    print("  sesiones    : %s/session-state/<id>/events.jsonl → respaldo "
          "envuelto + diálogo visible al cerrar" % copilot_home())
    print("  aislamiento : " + (
        "tus --excluded-tools/--available-tools ganan: si dejan `session_store_sql`, "
        "este agente puede leer las sesiones de Copilot de tus otros agentes"
        if socio_elige_herramientas(passthrough) else
        "`%s` por corrida (su buscador de sesiones lee las de todos tus agentes; "
        "nada escrito)" % AISLAMIENTO_ARG))
    try:
        import motor_statusline as _msl
        print("  barra       : " + _msl.plan_line("copilot"))
    except Exception:
        pass
    try:
        import memoria_mcp
        extra = memoria_mcp.copilot_args()
    except Exception:
        extra = []
    extra = list(extra) + brain_write_args(cfg, brain, passthrough, exe=exe)[0]
    print("  argv        : copilot %s" % " ".join(
        _interactive_argv(cfg, passthrough, session_id="<uuid de la pestaña>", extra=extra)))
    print(line)
    print("  [%s] binario copilot en PATH: %s"
          % ("✓" if exe else "✗ FALTA", exe or
             "(no está — Motores › GitHub Copilot › instalar)"))
    blk = gatekeeper_block(exe) if exe else None
    if blk:
        print("  [✗] macOS: %s (no se ejecuta: Motores › GitHub Copilot › reinstalar)"
              % blk["why"])
    elif exe:
        try:
            import engine_versions
            ver = engine_versions.installed_version(exe) or "?"
            st = engine_versions.drift(sys.modules[__name__], ver)[0]
        except Exception:
            ver, st = "?", "?"
        print("  [%s] versión: %s (%s)" % ("✓" if st in ("ok", "newer") else "?",
                                           ver.splitlines()[0] if ver else "?", st))
    act = session_active(exe_override=exe or "") if exe else False
    print("  [%s] cuenta: %s" % ({True: "✓", False: "✗"}.get(act, "?"),
                                 {True: "hay con qué entrar",
                                  False: "sin cuenta — corre `copilot login`"}.get(
                                      act, "no se pudo saber (Copilot la pide al abrir)")))
    print("  [%s] cerebro: %s"
          % ("✓" if brain and os.path.isdir(brain) else "✗ FALTA", brain))
    print(line)


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    """Arranca un agente EN COPILOT (interactivo). Delega al wrapper neutral
    de interactive.py (session_start → `copilot` → session_end). plan=True NO
    lanza: imprime el wiring + chequeos."""
    brain = cfg.get("_brain", "")
    exe = _exe()
    if plan:
        _plan(cfg, passthrough, brain, exe)
        return
    if not exe:
        print("WORKSPACE: copilot no está en PATH — instálalo (Motores › GitHub "
              "Copilot › instalar) y entra con `copilot login`.")
        sys.exit(1)
    blk = gatekeeper_block(exe)
    if blk:
        # Ejecutarlo abriría el diálogo de macOS (y volvería en cada llamada).
        print("WORKSPACE: GitHub Copilot — %s. Motores › GitHub Copilot › reinstalar."
              % blk["why"])
        sys.exit(1)

    # Memoria sin pedir permiso: la herramienta MCP de Workspace y su permiso
    # POR CORRIDA, antes del bloque de la pestaña (sus instrucciones nombran la
    # herramienta solo si quedó lista). Falla-suave: [] → `workspace memoria`
    # pidiendo permiso.
    try:
        import memoria_mcp
        extra = memoria_mcp.preparar("copilot", brain=brain, exe=exe, passthrough=passthrough)
    except Exception:
        extra = []
    # Escribir en su cerebro sin preguntar (autonomía «brain»), por corrida;
    # con «ask», nada. Falla-suave: sin reglas, Copilot pregunta como siempre.
    escritura = ""
    try:
        wargs, motivo = brain_write_args(cfg, brain, passthrough, exe=exe)
        extra = list(extra) + wargs
        if motivo in ("ruta", "largo"):
            escritura = write_plan_line(cfg, brain, passthrough, exe=exe)
    except Exception:
        pass

    tab, session_id, session_blk, resumed = None, "", "", False
    agent = str(cfg.get("name") or "")
    cfg.setdefault("_engine", "copilot")
    # Etiqueta honesta ANTES del picker (si no, el picker compartido y el
    # banner dicen «Claude Code»). Sin modelo: lo elige el socio.
    os.environ["WORKSPACE_ENGINE_LABEL"] = "GitHub Copilot · modelo de tu cuenta"
    user_session = _has_session_flag(passthrough)
    try:
        from engines import _ui
        import sessions_registry as _reg
        if not (preselect and preselect.get("wid")):
            from engines import claude_code as _cc0
            _cc0.session_preflight(cfg, "copilot")
        tab = _ui.pick_tab(cfg, preselect=preselect)
        if not tab:
            from engines import claude_code as _cc
            _cc.warn_no_tab(_cc.LAST_PICK_ERROR)
        if tab:
            wid, wname = tab
            _ui.export_tab_env(cfg, wid, wname)
            _reg.ensure_tab(brain, agent, wname, claude_wid=wid)
            if not user_session:
                session_id = str(_reg.resume_id(brain, agent, wname, "copilot") or "")
                if not _valid_session_id(session_id):
                    # pestaña nueva (o id ajeno): id propio, atado YA — con
                    # `--session-id` Copilot crea la sesión con ese id.
                    session_id = new_session_id()
                    _reg.bind(brain, agent, wname, "copilot", session_id)
                # atada pero sin conversación (se cerró sin escribir, o es de
                # otra máquina): abre como nueva con el mismo id y manda el
                # arranque del cerebro
                resumed = session_has_dialogue(session_id)
            session_blk = _reg.session_doc_block(brain, wname, engine="copilot",
                                                 resumed=resumed)
    except Exception as e:
        tab, session_id, session_blk, resumed = None, "", "", False
        try:
            from engines import claude_code as _cc
            err = "no pude preparar la pestaña (%s: %s)" % (type(e).__name__, e)
            _cc._session_log(cfg, "copilot", err)
            _cc.warn_no_tab(err)
        except Exception:
            pass

    # inject_context (contrato §3): identidad + bloque de la PESTAÑA ACTIVA,
    # INVISIBLE. Solo si ni el anexo a un AGENTS.md del socio se pudo
    # escribir, la memoria cae al primer mensaje (visible — último recurso).
    first_prompt = ""
    inj = inject_context(cfg, session_context=session_blk)
    if not inj.get("ok") and inj.get("detail"):
        print("WORKSPACE: identidad NO inyectada (%s) — Copilot arrancará "
              "sin el puntero de Workspace." % inj["detail"])
    if tab and session_blk and inj.get("action") == "custom" \
            and not inj.get("session") and not resumed:
        try:
            import sessions_registry as _reg
            first_prompt = _reg.first_prompt_context(brain, tab[1], engine="copilot")
            print("WORKSPACE: no pude anexar la memoria al AGENTS.md del "
                  "socio — irá en el primer mensaje (visible).")
        except Exception:
            first_prompt = ""

    if show_banner:
        try:
            from engines import _ui
            _ui.show_brain_banner(cfg)
        except Exception:
            _banner(cfg)
    # Lo que la herramienta de memoria rehízo en el cerebro (alguien lo había
    # cambiado): una línea cada uno, DESPUÉS del banner (que limpia la pantalla).
    try:
        import memoria_mcp
        for aviso in memoria_mcp.avisos():
            print(aviso)
    except Exception:
        pass
    if escritura:
        print("WORKSPACE: " + escritura)

    # Arranque del cerebro como codex/opencode: una sesión NUEVA sin
    # argumentos del socio arranca sola; al retomar no se inyecta nada.
    boot = first_prompt or ("" if (passthrough or resumed) else boot_message(cfg))
    if boot:
        try:
            import memoria
            if memoria.pasa_por_cmd(exe):   # el lanzador .cmd pasa por cmd.exe
                boot = memoria.argv_seguro(boot)
        except Exception:
            pass
    argv = _interactive_argv(cfg, passthrough, session_id=session_id, boot=boot, extra=extra)
    if socio_elige_herramientas(passthrough):
        print("WORKSPACE: tus --excluded-tools/--available-tools ganan; si dejan "
              "`session_store_sql`, este agente puede leer las sesiones de Copilot de tus "
              "otros agentes.")

    # La captura al cierre (session_continuity.capture_copilot) lee ESTA
    # sesión: necesita su id real. `--continue` o un nombre no lo dicen →
    # captura honesta «missing».
    real_sid = session_id or _session_from_passthrough(passthrough)
    if real_sid:
        os.environ["WORKSPACE_COPILOT_SESSION"] = real_sid
    else:
        os.environ.pop("WORKSPACE_COPILOT_SESSION", None)

    _doc_dirty = []

    def _ctx_sink(ctx):
        # Contexto neutral de arranque (tono, etc.) → INVISIBLE al AGENTS.md
        # junto con el bloque de la pestaña; solo si no se pudo escribir, se
        # imprime.
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

    # La barra de Workspace en la statusLine nativa de Copilot (la del socio
    # gana; falla-suave: jamás tumba el arranque).
    try:
        import motor_statusline
        motor_statusline.ensure_statusline("copilot")
    except Exception:
        pass

    try:
        import interactive
        rc = interactive.run_official_cli_interactive(
            "copilot", brain=brain or None, argv=argv, context_sink=_ctx_sink,
            pending={"tab": tab[1] if tab else "", "agent": agent,
                     "resume_id": session_id, "no_bind": user_session})
    except Exception as e:
        print("WORKSPACE: no pude lanzar copilot interactivo (%s: %s)"
              % (type(e).__name__, e))
        sys.exit(1)
    # Limpieza: el bloque de la pestaña era de ESTA corrida → se restaura el
    # puntero base (o se quita el anexo del doc del socio). AGENTS.md es UNO
    # por cerebro: si otra pestaña sigue viva en él (de cualquier motor), el
    # bloque es el suyo y no se toca; lo limpia la última que cierre.
    try:
        import pending_runs
        otra = bool(brain) and pending_runs.live_in_brain(brain, exclude=pending_runs.current())
    except Exception:
        otra = False
    if (session_blk or _doc_dirty) and not otra:
        try:
            inject_context(cfg)
        except Exception:
            pass
    if not otra and brain:
        try:
            import pending_runs
            pending_runs.clean_docs("copilot", brain)
        except Exception:
            pass
    try:
        import pending_runs
        pending_runs.done()               # atado y limpieza hechos: ya no está pendiente
    except Exception:
        pass
    sys.exit(rc if isinstance(rc, int) else 0)


def pick(cfg):
    """El picker de pestañas COMPARTIDO (registro neutral): la misma elección
    cruda ('WS\\t<wid>\\t<name>') que claude_code.pick — lo usa el hub tmux
    (mux.py). Falla-suave → ''."""
    try:
        from engines import _ui
        cfg.setdefault("_engine", "copilot")
        return _ui.pick_keep_label(cfg, "GitHub Copilot · modelo de tu cuenta")
    except Exception:
        return ""
