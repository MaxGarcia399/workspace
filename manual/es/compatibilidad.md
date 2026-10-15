# Compatibilidad: motor × sistema operativo

Qué funciona hoy, con qué motor y en qué sistema. Si algo no está aquí como "funciona",
no lo prometemos.

<!-- Fuente: capabilities.py (estados y reglas por OS) + CAPABILITIES de engines/*.py.
Tablas verificadas contra el código; tests/test_manual_compat.py recalcula cada celda desde
capabilities.py y falla si la tabla queda desactualizada (aquí o en ../en/compatibility.md). -->

## Cómo verlo en tu máquina

Las tablas de abajo son generales. Lo que vale **en tu equipo**, con lo que tienes instalado:

- **Motores:** la sección **Motores** del hub dice si cada uno está instalado y con
  sesión. Además, `workspace doctor` avisa si falta el programa del motor que usa alguno de
  tus agentes.
- **Dictado por voz:** `workspace voice --check` dice qué falta; `workspace voice --setup`
  lo instala.
- **Terminal partida:** si la activas y falta tmux (o herdr), al abrir un agente te avisa y
  abre la sesión sencilla.

Son funciones opcionales: el doctor no las revisa.

## Por motor

Vale para macOS, Linux y Windows, salvo donde se indica.

| Función | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Abrir el agente desde el hub | ✅ | ✅ (envuelto) | ✅ (envuelto) |
| El agente arranca con su memoria | ✅ automático | ✅ vía un `AGENTS.md` que Workspace genera en el cerebro | ✅ vía un `GEMINI.md` que Workspace genera en el cerebro |
| Conectores MCP | ✅ | ✅ (configuración del propio Codex) | ✅ |
| Avisos de sesión (*hooks*: guardar memoria al cerrar, etc.) | ✅ | ✅ solo al abrir y al cerrar (los emite Workspace) | ✅ solo al abrir y al cerrar (los emite Workspace) |
| Retomar sesiones desde las pestañas de Workspace | ✅ | ✅ | ✅ |
| Estado en vivo del agente en el hub | ✅ | ❌ | ❌ |
| Tareas sin ventana (evals, workflows) | ✅ | ✅ | ❌ |

✅ funciona · ❌ no disponible · ❔ sin verificar

Si el programa del motor no está instalado (o no está en el PATH), nada de esto funciona con
él: `workspace doctor` te dice que instales su programa oficial ([Motores](motores.md)).

Codex y Antigravity también traen *hooks* propios, pero Workspace no los activa: los avisos de
abrir y cerrar ya los emite Workspace alrededor del programa, y activarlos los duplicaría. Por
eso con esos dos motores no hay avisos por herramienta ni estado en vivo.

## Permisos por motor

Cada agente tiene una **autonomía** (`"autonomy"` en su `.workspace/agent.json`). Si no dice
nada, es **cerebro**. Workspace la traduce a lo que entiende cada motor y nunca usa los modos
que se saltan todos los permisos.

| | Cerebro (por defecto) | Pregunta (`"ask"`) |
|---|---|---|
| En los tres motores | lee, crea y edita dentro de su cerebro sin preguntar; la terminal, los archivos fuera del cerebro y la red piden permiso | pregunta antes de crear o editar, también dentro de su cerebro |
| Claude Code | lectura y edición permitidas solo en la carpeta del cerebro | sin reglas de Workspace: pide permiso para editar |
| Codex | `-s workspace-write -a on-request`, con la red apagada | `-s read-only -a on-request`: pide aprobación para editar o correr algo |
| Antigravity | `--mode accept-edits` y la regla `write_file(<cerebro>)` | sin `--mode`; la regla queda en `read_file(<cerebro>)` |

Se cambia en **Agentes** (elige el agente y Enter) (ver [Permisos](motores.md#permisos)).

- En una tarea sin ventana, lo que pediría permiso se niega.
- **Codex:** con *cerebro*, sus comandos corren sin preguntar **dentro de su caja**: solo pueden
  escribir en su cerebro y en las carpetas temporales del sistema, y sin red. Lo que necesite
  salir de la caja te lo pide. Con *pregunta*, la caja es de solo lectura y pide aprobación antes
  de editar o correr algo.
- **Antigravity:** la regla `write_file(<cerebro>)` vive en la configuración general de
  Antigravity, así que cualquier sesión de Antigravity puede editar ese cerebro sin preguntar.
- Correr comandos sin preguntar ya no existe. Un agente que lo traía de una versión anterior
  (`"full"` en su `agent.json`) pasa a *cerebro* al actualizar.
- Si al abrir el motor pasas tus propias opciones (`-a` en Codex; `--mode` o `--project` en
  Antigravity), ganan las tuyas.

## Barra de estado y tema por motor

| | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Barra de estado | la de Workspace | la de Codex: modelo, contexto, límites de 5 h y semanal, y el proyecto si el cerebro es un repositorio git | la de Antigravity y, debajo, la de Workspace: agente, modelo, contexto, modo y cuotas |
| Nombre del agente | en la barra | en el título de la ventana | en la barra y en el título de la ventana |
| Tema del hub | un tema de Claude Code generado con la paleta | un tema `.tmTheme` en `~/.codex/themes/` que colorea la barra, el código y los cambios | recolorea los colores básicos de la terminal mientras corre y los devuelve al salir |
| Si ya elegiste los tuyos | se respetan | se respetan (`tui.theme`, `tui.status_line` o `tui.terminal_title` en tu `config.toml`) | se respetan (tu `colorScheme` o tu propia `statusLine`) |

- **Codex muestra una sola barra.** Workspace tiene además un pie propio de dos líneas, con los
  reinicios de las cuotas y el tiempo activo; está apagado y se activa con
  `WORKSPACE_CODEX_LIVE_BAR=1`. Necesita tmux (macOS y Linux). Cuando aparece, la barra de
  Codex se oculta para no duplicar.
- **Antigravity:** si tu configuración tenía una barra de Workspace vieja o con una ruta que ya
  no existe, se repara sola al abrir un agente. La nueva apunta a
  `~/.local/bin/workspace-agy-statusline`, que encuentra Workspace aunque lo muevas.
- **Antigravity** pinta con los colores básicos de tu terminal solo con su esquema
  `"terminal"` (el de fábrica). Si elegiste otro esquema, Workspace no lo cambia.

## Por sistema (funciones de Workspace)

| Función | macOS | Linux | Windows |
|---|---|---|---|
| Dictado por voz (local) | ✅ si instalas whisper.cpp, su modelo y ffmpeg o sox | ❌ por ahora | ❌ por ahora |
| Terminal partida (chat + tablero) | ✅ con tmux o herdr | ✅ con tmux o herdr | ❌ abre la sesión sencilla |
| Controles del panel lateral | ✅ dentro de la terminal partida | ✅ dentro de la terminal partida | solo lectura |

## Límites actuales

- **"Tú eliges el motor" es verdad a medias hoy.** Los tres motores abren agentes con su
  memoria, pero Claude Code tiene más integración, y parte de la configuración local todavía
  vive en `~/.claude/workspace/` aunque no uses Claude Code.
- **Cambiar de motor no traslada conversaciones**: el cerebro sí viaja; el historial interno
  de cada proveedor, no.
