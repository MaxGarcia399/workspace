# Desinstalar

```bash
workspace uninstall
```

Te muestra qué va a borrar y te pide confirmación.

- `workspace uninstall --dry-run` — solo enseña qué borraría; no toca nada.
- `workspace uninstall --keep-folder` — quita todo de tu máquina pero **conserva la carpeta**
  de Workspace.
- `workspace uninstall --limpiar-todo` (o `--clean-all`; también te lo pregunta) — limpia
  además tus cerebros y los motores. Ver [Limpiar también cerebros y motores](#limpiar-también-cerebros-y-motores).

## Qué se borra

- El comando `workspace`, los comandos de cada agente y `workspace-memoria`.
- La configuración local de Workspace en `~/.claude/workspace/` (ajustes, atajos, temas
  elegidos, estado de esta máquina).
- Lo que el instalador añadió a tu terminal (PATH y menú al abrir; en Windows, el bloque del
  perfil de PowerShell).
- El tema que instaló dentro de Claude Code, si lo hizo.
- La carpeta de Workspace (salvo `--keep-folder`).

## Qué NO se borra

- **Los cerebros de tus agentes** (sus carpetas): son tuyos y viven aparte.
- Las conversaciones guardadas por cada motor. Si eliges limpiar también los motores, las de
  los perfiles de Workspace en OpenClaw y Hermes se mueven a una carpeta de respaldo (ver abajo).
- Los motores (Claude Code, Codex, Antigravity, OpenCode, OpenClaw, Hermes, Kiro, GitHub Copilot,
  Cursor) ni sus sesiones.

## Limpiar también cerebros y motores

Por defecto, lo que Workspace escribió en tus cerebros y en los motores se queda. Si eliges
limpiarlo, primero te muestra la lista exacta y quita **solo lo que escribió Workspace**:

- En cada cerebro: sus hooks, barra, permisos y tema en `.claude/settings.local.json`, y los
  `AGENTS.md`/`GEMINI.md` que generó. El `CLAUDE.md` y todo el contenido del cerebro se quedan.
- Codex: la confianza de tus cerebros en `config.toml` y sus temas `workspace-*`.
- Antigravity: tus cerebros, sus reglas y la barra en su `settings.json`, y sus proyectos
  `workspace-*`.
- GitHub Copilot: la barra en su `settings.json` y la copia que Workspace guardó antes
  (`settings.workspace-statusline-backup.json`).
- Cursor: la barra y la regla vieja de `workspace-memoria` en su `cli-config.json`, y las marcas
  de confianza `.workspace-trusted` que dejó Workspace (las que aceptaste tú en Cursor se quedan).
- Kiro: el agente `agents/workspace.json` de una versión anterior y, en su `settings/cli.json`,
  solo los segmentos de la barra que prendió Workspace (también con `KIRO_HOME`).
- En cada cerebro, la herramienta de memoria: en `.cursor/mcp.json`, `.cursor/cli.json` y
  `.agents/mcp_config.json` solo lo de Workspace (lo tuyo se queda; el archivo y su carpeta se
  borran solo si quedan vacíos) y el agente `.kiro/agents/workspace.json`. Quitar un agente
  desde Agentes también los quita de su cerebro.
- En `~/.local/bin`: los comandos de las barras
  (`workspace-copilot-statusline`, `workspace-cursor-statusline`, `workspace-agy-statusline`),
  solo si llevan la marca de Workspace.
- OpenClaw y Hermes: el perfil propio de Workspace **no se borra**. Se mueve entero, con sus
  conversaciones y el proveedor que conectaste ahí, a una carpeta al lado
  (`<perfil>.workspace-respaldo-<fecha>`). Si no se puede mover, se queda donde está. Tu
  OpenClaw y tu Hermes personales no se tocan.

Cada archivo de configuración que cambia queda respaldado al lado
(`<archivo>.workspace-respaldo-<fecha>`), y lo que editaste a mano, o que Workspace no escribió
tal cual (por ejemplo, un tema `workspace-*` sin su registro), se deja como está.

## Respaldo y protecciones

- Antes de borrar te muestra la lista **SE BORRA / SE CONSERVA / RESPALDO**, con cada cerebro
  por su nombre.
- Te ofrece un **respaldo** de tus ajustes en un zip en `~/Workspace/Respaldos` (fuera del
  Escritorio) y al terminar te lo muestra en su carpeta (`--no-backup` para no hacerlo). El respaldo **no lleva tus claves ni tokens**: al reinstalar las vuelves a pegar.
  Si el respaldo falla, no se borra nada.
- Sin una terminal donde preguntarte (un script o un agente) no borra nada, salvo que añadas
  `--yes`.
- Si la carpeta de Workspace es un checkout de git con trabajo sin publicar (cambios sin commit
  o commits sin push), **no la borra**: desinstala lo demás y te dice qué tiene.
- **Se niega a borrar** una carpeta que no parece de Workspace (sin sus archivos propios), tu
  carpeta personal, la raíz del disco o una carpeta que contenga un cerebro. En ese caso no
  borra nada y te dice por qué.

Reinstalar es el mismo comando de [Instalar](instalar.md); después, vuelve a cargar tus
agentes con **Agregar agente**.
