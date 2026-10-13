<!-- ARCHIVO GENERADO con `workspace comandos --markdown --lang es`: no lo edites a mano. tests/test_manual_commands.py vigila que coincida. -->

# Comandos de Workspace

Todo lo que puedes escribir en la terminal. Cada comando acepta su nombre en español y en inglés.

## tus agentes

### `workspace`

Abre el hub: tus agentes y el menú; escribe para buscar.

**Cuándo:** Para empezar a trabajar.

### `<agente>   (p. ej. el nombre de tu agente)`

Abre ese agente directo, sin pasar por el hub.

**Cuándo:** Cuando ya sabes con quién quieres hablar.

### `workspace agentes [descubrir | reubicar | estado]`

Tus agentes y su estado; descubrir busca cerebros, reubicar repara una ruta.

**Cuándo:** Si un agente no aparece o dice que no encuentra su cerebro.

_también: `agents`_

**Ejemplos:**

    workspace agentes descubrir
    workspace agentes estado

### `workspace tono`

Ajusta cómo te hablan tus agentes (diales del 1 al 5).

**Cuándo:** Si quieres respuestas más cortas, más cálidas, más técnicas…

_también: `tone`, `personalidad`_

### `workspace bienvenida`

Vuelve a correr la configuración guiada (continúa donde quedó).

**Cuándo:** Si quedó algo pendiente al instalar.

_también: `onboarding`_

## tu día

### `workspace foco [texto]`

Fija el foco del día que ves en el hub.

**Cuándo:** Al empezar el día.

_también: `focus`_

**Ejemplos:**

    workspace foco "cerrar la propuesta"

### `workspace agenda [add | rm]`

Tu agenda local: eventos con fecha y hora.

**Cuándo:** Para anotar algo rápido sin abrir el calendario.

### `workspace calendario`

Editor del calendario: mes, altas, cambios y bajas.

**Cuándo:** Para organizar la semana o el mes.

_también: `calendar`, `cal`_

### `workspace proyectos [stop]`

App «Proyectos»: el mapa de todos tus proyectos con tu agente.

**Cuándo:** Para ver en qué va cada proyecto.

_también: `projects`, `proyecto`, `mapa`_

### `workspace correo --to <correo> --subject <asunto> [--dry-run]`

Envía un correo desde la terminal; con --dry-run lo ves sin enviarlo.

**Cuándo:** Para mandar un aviso o resumen rápido.

_también: `mail`_

## trabajo

### `workspace wf new | list | run | status | resume | stats`

Flujos de trabajo paso a paso (crear un agente, construir una función…).

**Cuándo:** Para tareas largas que conviene hacer por pasos.

_también: `flujos`, `workflows`_

**Ejemplos:**

    workspace wf list

### `workspace split [agente]`

Terminal partida: el chat a un lado y el tablero de flujos al otro.

**Cuándo:** Cuando corres un flujo y quieres verlo mientras hablas.

### `workspace evaluar <agente>`

Prueba a un agente contra su set de preguntas de referencia.

**Cuándo:** Después de cambiar algo importante en un agente.

_también: `eval`, `evals`_

## esta máquina

### `workspace actualizar [--check | --rollback | --force | --auto auto|notify|off]`

Actualiza Workspace y tus cerebros, y repara lo necesario.

**Cuándo:** Cuando hay una versión nueva o algo dejó de funcionar.

_también: `update`, `up`_

**Ejemplos:**

    workspace actualizar --rollback
    workspace actualizar --auto notify

> Pide confirmación en la pantalla Comandos.

### `workspace version`

Muestra tu versión, tu última actualización y sus novedades.

**Cuándo:** Para saber qué tienes o al pedir ayuda.

_también: `versión`_

### `workspace migrar [--run | --pending | --offer <id>]`

Muestra y aplica los ajustes que trae cada actualización.

**Cuándo:** Si el doctor dice que un ajuste quedó pendiente o falló.

_también: `migrate`_

**Ejemplos:**

    workspace migrar --run

### `workspace doctor [--check | --remote | --bundle]`

Revisa que todo esté bien; sin --check también repara. --bundle arma un ZIP de diagnóstico sin datos personales para pedir ayuda.

**Cuándo:** Si algo se ve raro. --check solo mira, no cambia nada.

_también: `doc`_

**Ejemplos:**

    workspace doctor --check
    workspace doctor --bundle

### `workspace reparar`

Vuelve a preparar las conexiones de cada cerebro.

**Cuándo:** Si un agente abre pero no recuerda o no guarda.

_también: `repair`, `fix`_

### `workspace configurar-desarrollo`

Revisa si esta máquina está lista para contribuir a Workspace.

**Cuándo:** Si vas a programar en Workspace.

_también: `dev-setup`_

### `workspace migrar-legado [--apply | --retire | --rollback <respaldo>]`

Migra o retira la instalación anterior de Workspace, con respaldo.

**Cuándo:** Solo si venías de la versión anterior (con el nombre viejo).

_también: `migrate-legacy`_

### `workspace desinstalar [--dry-run | --no-backup | --keep-folder]`

Desinstala Workspace de esta máquina (tus cerebros se quedan).

**Cuándo:** Si ya no lo vas a usar aquí.

_también: `uninstall`, `remove`_

> Pide confirmación en la pantalla Comandos.

### `workspace comandos [--json | --markdown | --check]`

Esta lista de comandos; --json para agentes, --markdown para el manual.

**Cuándo:** Cuando quieres ver o exportar todos los comandos.

_también: `commands`_

**Ejemplos:**

    workspace comandos --json

### `workspace ayuda`

Muestra la lista de comandos en la terminal.

**Cuándo:** Cuando no recuerdas un comando.

_también: `help`, `--help`, `-h`_

### `workspace --banner`

Imprime el hub sin animación (vista estática, no interactiva).

**Cuándo:** Para capturas o terminales sin teclado.
