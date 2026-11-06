#!/usr/bin/env python3
"""WORKSPACE · rutas_protegidas — lo que el AGENTE no escribe nunca en su cerebro.

Con autonomía «brain» cada motor escribe en el cerebro sin preguntar. Pero el
cerebro lo comparten TODOS los motores, git y Obsidian: si un motor escribe la
config de otro, ese otro la carga al abrir y corre lo que diga (hooks, MCP,
agentes con permisos, plugins). Ejemplo real: Copilot escribía sin preguntar
`.kiro/agents/x.json`, y Kiro, que Workspace abre con `--trust-workspace`, lo
cargaba. O `.git/config` con `core.fsmonitor`, que corre en el siguiente
`git status`.

Esta es la ÚNICA lista. Cada motor la niega como regla de ESCRITURA de su
agente (engines/copilot.brain_write_args, memoria_mcp.kiro_agente_config /
agy_deny / cursor_cli_plantilla, memoria.claude_settings_args). Workspace no
pasa por estas reglas: él sigue escribiendo lo suyo (`.cursor/mcp.json`,
`.kiro/agents/workspace.json`, `.agents/mcp_config.json`,
`.claude/settings.local.json`…), y el socio también, a mano.

Las instrucciones (AGENTS.md, BRAIN.md, CLAUDE.md…) NO están: son contenido
del cerebro y el agente las mantiene; no abren una puerta que no tenga ya
cualquier motor con su cerebro.

Rutas RELATIVAS al cerebro, con `/` (cada motor la arma en su forma). Sin
dependencias: lo importan módulos que corren antes que el resto.
"""

CARPETA = "carpeta"
ARCHIVO = "archivo"

#: (ruta relativa al cerebro, tipo, por qué, doc oficial).
PROTEGIDAS = (
    (".git", CARPETA,
     "config (core.fsmonitor, core.hooksPath) y hooks que git corre solo",
     "https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefsmonitor "
     "https://git-scm.com/docs/githooks"),
    (".github", CARPETA,
     "Copilot: hooks, MCP (.github/mcp.json), LSP, skills y agentes del proyecto",
     "https://docs.github.com/en/copilot/reference/hooks-reference "
     "https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers "
     "https://docs.github.com/en/copilot/reference/custom-agents-configuration "
     "https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/add-lsp-servers "
     "https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/"
     "customize-cloud-agent/add-skills"),
    (".agents", CARPETA,
     "Antigravity: MCP (mcp_config.json), skills, reglas y hooks; skills de Copilot y Codex",
     "https://antigravity.google/docs/mcp/ https://antigravity.google/docs/skills"),
    (".agent", CARPETA,
     "Antigravity: el nombre de antes de .agents, que sigue leyendo",
     "https://antigravity.google/docs/skills"),
    (".claude/settings.json", ARCHIVO,
     "Claude Code (y los hooks que Copilot y Cursor leen de ahí): permisos y hooks",
     "https://code.claude.com/docs/en/settings "
     "https://docs.github.com/en/copilot/reference/hooks-reference"),
    (".claude/settings.local.json", ARCHIVO,
     "ídem, la local (Workspace escribe aquí los permisos de la autonomía)",
     "https://code.claude.com/docs/en/settings"),
    (".claude/skills", CARPETA,
     "skills con allowed-tools (Claude Code, Copilot, Cursor, opencode)",
     "https://code.claude.com/docs/en/skills"),
    (".claude/agents", CARPETA,
     "subagentes con herramientas y MCP propios",
     "https://code.claude.com/docs/en/sub-agents"),
    (".claude/commands", CARPETA,
     "comandos con allowed-tools",
     "https://code.claude.com/docs/en/slash-commands"),
    (".claude/hooks", CARPETA,
     "scripts de hooks del proyecto",
     "https://code.claude.com/docs/en/hooks"),
    (".cursor", CARPETA,
     "Cursor: permisos (cli.json), MCP, hooks, reglas",
     "https://cursor.com/docs/cli/reference/permissions https://cursor.com/docs/agent/hooks"),
    (".kiro", CARPETA,
     "Kiro: agentes, MCP (settings/mcp.json), hooks, steering, skills",
     "https://kiro.dev/docs/permissions/ "
     "https://kiro.dev/docs/cli/custom-agents/configuration-reference/"),
    (".amazonq", CARPETA,
     "Kiro sigue leyendo agentes, reglas y MCP de la carpeta de Amazon Q",
     "https://kiro.dev/docs/cli/migrating-from-q/"),
    (".codex", CARPETA,
     "Codex: config.toml, hooks y reglas del proyecto",
     "https://learn.chatgpt.com/docs/config-file/config-reference"),
    (".gemini", CARPETA,
     "Gemini CLI: settings.json con mcpServers, hooks y tools.discoveryCommand",
     "https://geminicli.com/docs/reference/configuration"),
    (".vscode", CARPETA,
     "VS Code y Copilot: mcp.json, tasks.json (runOn folderOpen)",
     "https://code.visualstudio.com/docs/copilot/customization/mcp-servers "
     "https://code.visualstudio.com/docs/debugtest/tasks"),
    (".obsidian", CARPETA,
     "Obsidian: plugins (JavaScript que corre al abrir la bóveda)",
     "https://obsidian.md/help/plugin-security"),
    (".mcp.json", ARCHIVO,
     "MCP del proyecto (Claude Code y Copilot)",
     "https://code.claude.com/docs/en/mcp "
     "https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers"),
    ("opencode.json", ARCHIVO,
     "opencode: config del proyecto (plugins, MCP, permisos)",
     "https://opencode.ai/docs/config/"),
    ("opencode.jsonc", ARCHIVO,
     "ídem, con comentarios",
     "https://opencode.ai/docs/config/"),
    (".opencode", CARPETA,
     "opencode: plugins (.opencode/plugins), agentes y comandos del proyecto",
     "https://opencode.ai/docs/plugins/"),
    (".hermes", CARPETA,
     "Hermes: plugins del proyecto (.hermes/plugins)",
     "https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins"),
)

#: Carpetas: se niega la carpeta y TODO lo de adentro.
CARPETAS = tuple(r for r, t, _p, _d in PROTEGIDAS if t == CARPETA)
#: Archivos: se niega ese archivo.
ARCHIVOS = tuple(r for r, t, _p, _d in PROTEGIDAS if t == ARCHIVO)
#: Carpetas que además se niegan como ARCHIVO con ese nombre: un archivo
#: `.git` con `gitdir: <ruta>` manda a git a otra carpeta, con su config
#: (https://git-scm.com/docs/gitrepository-layout). Las demás, como archivo,
#: no cargan nada.
EXACTAS = (".git",)


def todas():
    """Todas las rutas (carpetas y archivos), en el orden de la lista."""
    return tuple(r for r, _t, _p, _d in PROTEGIDAS)


def es_protegida(rel):
    """¿`rel` (relativa al cerebro, `/` o `\\`) cae en una ruta protegida? Sin
    distinguir mayúsculas: en macOS y Windows `.KIRO` es `.kiro`. Para el
    lado de Workspace (avisos, pruebas); los motores aplican sus reglas."""
    p = str(rel or "").replace("\\", "/").strip("/").lower()
    while p.startswith("./"):
        p = p[2:]
    for r in CARPETAS:
        r = r.lower()
        if p == r or p.startswith(r + "/"):
            return True
    return p in tuple(a.lower() for a in ARCHIVOS)


def sin_mayusculas(rel):
    """`rel` como glob que acepta cualquier mezcla de mayúsculas: cada letra
    como clase de un carácter (`.kiro` → `.[kK][iI][rR][oO]`). Para los
    motores que comparan la ruta tal cual y aceptan clases `[…]` en su
    patrón (Kiro: doc «permissions», «character classes ([abc]) are
    supported»). Lo demás va igual."""
    out = []
    for c in str(rel):
        lo, up = c.lower(), c.upper()
        out.append("[%s%s]" % (lo, up) if lo != up else c)
    return "".join(out)
