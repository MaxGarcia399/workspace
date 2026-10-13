"""WORKSPACE · legacy — literales de la INSTALACIÓN ANTERIOR (nombre viejo del producto).

Antes del rename (2026-10) el producto tenía otro nombre. En máquinas que lo
tuvieron quedan RESTOS reales en disco y en el entorno: la subcarpeta de
manifiesto en los cerebros, la carpeta del harness en el escritorio, el estado
per-máquina bajo ~/.claude, el launcher, variables de entorno, líneas en el
$PROFILE/~/.zshrc y marcas HTML dentro de AGENTS.md/GEMINI.md.

Estas cadenas existen SOLO para reconocer y migrar (o limpiar) esos restos.
NO usar para nada nuevo: ningún texto visible, ningún archivo nuevo, ninguna
clave nueva. Para el usuario esto es «la instalación anterior» (ES) /
«the previous install» (EN).

Este es el ÚNICO archivo .py del producto que puede contener el nombre viejo
(lo vigila tests/test_legacy_name_guard.py). Stdlib pura, sin imports del
proyecto: lo importan módulos de arranque (agentsreg, brain_resolver, engines).
"""

#: nombre anterior del producto (mayúsculas, como lo escribía el harness viejo)
NAME = "OLYMPUS"
#: mismo nombre en minúsculas (carpetas de estado, launcher, comparaciones)
NAME_LOWER = "olympus"

# ── en los cerebros ──────────────────────────────────────────────────────────
#: subcarpeta de manifiesto en un cerebro: <brain>/.olympus/agent.json
BRAIN_SUBDIR = "." + NAME_LOWER
#: ruta relativa (POSIX) del manifiesto viejo. Se PERSISTE como `_migrated_from`
#: en el `.workspace/agent.json` migrado: es un dato histórico, no cambia.
AGENT_JSON_REL = BRAIN_SUBDIR + "/agent.json"
#: valor del campo `marker` de un cerebro descubierto con el manifiesto viejo.
#: Se PERSISTE en el índice de descubrimiento (brains.index.json); una versión
#: anterior lo lee de vuelta → el valor no cambia.
MARKER = NAME_LOWER

# ── en la máquina ────────────────────────────────────────────────────────────
#: variables de entorno del harness viejo
ENV_ROOT = NAME + "_ROOT"
ENV_BRAIN = NAME + "_BRAIN"
ENV_VARS = (ENV_ROOT, ENV_BRAIN)
#: carpeta del harness viejo (~/Desktop/OLYMPUS, ~/OLYMPUS)
HARNESS_DIRNAME = NAME
#: subcarpeta del estado per-máquina viejo: ~/.claude/olympus
STATE_SUBDIR = NAME_LOWER
#: funciones PowerShell viejas: ~/.claude/olympus-cmds.ps1
PS_CMDS_FILE = NAME_LOWER + "-cmds.ps1"
#: nombre del comando viejo y sus variantes en ~/.local/bin
LAUNCHER = NAME_LOWER
LAUNCHERS = (LAUNCHER, LAUNCHER + ".cmd", LAUNCHER + ".bat", LAUNCHER + ".ps1")
#: marcadores de líneas viejas en el $PROFILE de PowerShell
PS_PROFILE_MARKS = ("# " + NAME + "-cmds", PS_CMDS_FILE, NAME + "_GREETER",
                    "# " + NAME + "-greeter", "$env:" + ENV_ROOT, "$env:" + ENV_BRAIN)
#: regex de líneas viejas en un rc POSIX (~/.zshrc…)
RC_EXPORT_RE = r"^\s*export\s+" + NAME + r"_(ROOT|BRAIN)="
RC_ALIAS_RE = r"^\s*alias\s+" + NAME_LOWER + r"="

# ── en el estado de Workspace (valores PERSISTIDOS: no cambiar) ─────────────
#: subcarpeta de respaldos de la migración: <estado>/backups/olympus/. Hay
#: respaldos reales ahí y `--rollback`/`--backups` los buscan en esta ruta.
BACKUPS_SUBDIR = NAME_LOWER
#: memoria de raíces vistas por --apply: <estado>/olympus-migration.json
MIGRATION_MEMORY_FILE = NAME_LOWER + "-migration.json"

# ── marcas dentro de AGENTS.md / GEMINI.md de los cerebros ──────────────────
#: marca de archivo generado por engines/codex.py (versión anterior)
CODEX_GEN_MARK = "<!-- " + NAME + ":GENERATED inject_context v1 -->"
#: marca de archivo generado por engines/antigravity.py (versión anterior)
GEMINI_GEN_MARK = "<!-- " + NAME + ":GENERATED antigravity-context v1 -->"
#: bloque de sesión que escribían ambos engines (solo LECTURA: limpiar huérfanos)
SESSION_START = ("<!-- " + NAME + ":SESSION start — contexto de la pestaña activa; "
                 "se regenera en cada launch -->")
SESSION_END = "<!-- " + NAME + ":SESSION end -->"

# ── referencias muertas (doctor fase 5d) ────────────────────────────────────
#: refs que rompen la resolución de raíz si siguen en una marca brain-resident
DEAD_REFS = (ENV_ROOT, ENV_BRAIN, "~/Desktop/" + NAME, "Desktop/" + NAME,
             ".claude/" + STATE_SUBDIR)

# ── CLI ──────────────────────────────────────────────────────────────────────
#: nombres viejos del comando de migración (aliases ocultos, solo compatibilidad)
CLI_ALIASES = ("migrar-" + NAME_LOWER, "migrate-" + NAME_LOWER)
