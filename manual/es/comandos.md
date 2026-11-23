# Comandos de Workspace

Todo lo que puedes escribir en la terminal. Cada comando acepta su nombre en español y en inglés.

## tus agentes

### `workspace`

Abre el hub: tus agentes y sus secciones; escribe para buscar.

**Cuándo:** Para empezar a trabajar.

### `<agente>   (p. ej. el nombre de tu agente)`

Abre ese agente directo, sin pasar por el hub.

**Cuándo:** Cuando ya sabes con quién quieres hablar.

### `workspace agentes [descubrir | reubicar | estado]`

Sin nada más, abre el hub en Agentes; estado los lista, descubrir busca cerebros, reubicar repara una ruta.

**Cuándo:** Si un agente no aparece o dice que no encuentra su cerebro.

_también: `agents`_

**Ejemplos:**

    workspace agentes descubrir
    workspace agentes estado

### `workspace tono`

Cómo te hablan tus agentes (diales del 1 al 5). Sin nada más, abre el hub en Agentes › Tono; con argumentos, en texto.

**Cuándo:** Si quieres respuestas más cortas, más cálidas, más técnicas…

_también: `tone`, `personalidad`_

### `workspace bienvenida`

Abre el hub con la tarjeta para agregar tu primer agente.

**Cuándo:** Si todavía no tienes un agente.

_también: `onboarding`_

## tu día

### `workspace agenda [add | rm]`

Tu agenda local: eventos con fecha y hora.

**Cuándo:** Para anotar algo rápido sin abrir el calendario.

### `workspace calendario`

Abre el hub en Calendario, con tu agenda.

**Cuándo:** Para organizar la semana o el mes.

_también: `calendar`, `cal`_

### `workspace correo --to <correo> --subject <asunto> [--dry-run]`

Envía un correo desde la terminal; con --dry-run lo ves sin enviarlo.

**Cuándo:** Para mandar un aviso o resumen rápido.

_también: `mail`_

## trabajo

### `workspace evaluar <agente>`

Prueba a un agente contra su set de preguntas de referencia.

**Cuándo:** Después de cambiar algo importante en un agente.

_también: `eval`, `evals`_

## esta máquina

### `workspace conexiones [--counts]`

Abre el hub en Ajustes › Conexiones: qué conecta Workspace en cada motor; --counts, el conteo en JSON.

**Cuándo:** Para ver qué conecta Workspace en cada motor.

_también: `connections`_

### `workspace web`

Abre Workspace en tu navegador: una página local, solo en esta computadora.

**Cuándo:** Para ver y hablar con tus agentes sin la terminal; se cierra con Ctrl+C.

### `workspace actualizar [--check | --rollback | --force | --auto auto|notify|off]`

Actualiza Workspace y tus cerebros, y repara lo necesario.

**Cuándo:** Cuando hay una versión nueva o algo dejó de funcionar.

_también: `update`, `up`_

**Ejemplos:**

    workspace actualizar --rollback
    workspace actualizar --auto notify

> Cambia cosas en esta máquina.

### `workspace version`

Muestra tu versión, tu última actualización y sus novedades.

**Cuándo:** Para saber qué tienes o al pedir ayuda.

_también: `versión`_

### `workspace migrar [--run | --pending | --offer <id> | --decline <id>]`

Muestra y aplica los ajustes que trae cada actualización.

**Cuándo:** Si el doctor dice que un ajuste quedó pendiente o falló.

_también: `migrate`_

**Ejemplos:**

    workspace migrar --run

### `workspace sistema-nuevo [on | off]`

Enciende o apaga el sistema nuevo: los hooks, el MCP y las skills de Workspace por sesión en tus motores.

**Cuándo:** Si quieres que tus motores abran como antes, o volver al sistema nuevo.

_también: `new-system`_

**Ejemplos:**

    workspace sistema-nuevo off
    workspace sistema-nuevo on

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

### `workspace metricas [estado | salud | importar | exportar --json <archivo> | borrar --mio | apagar | encender]`

Registro local del desempeño de tus agentes: estado, salud, importar la historia, exportar agregados, borrar lo tuyo o apagarlo.

**Cuándo:** Para ver qué se registra, o para compartir solo totales sin tu conversación.

_también: `metrics`, `métricas`_

**Ejemplos:**

    workspace metricas importar
    workspace metricas borrar --mio

### `workspace llaves [estado | auditar] [--json]`

Tus llaves de Workspace: de dónde sale cada una (tu sistema, el llavero o el archivo) y una auditoría de restos en texto plano. Nunca muestra un valor.

**Cuándo:** Para saber dónde quedó una llave, o revisar que no quede ninguna a la vista.

_también: `keys`, `secretos`, `secrets`_

**Ejemplos:**

    workspace llaves auditar

### `workspace configurar-desarrollo`

Revisa si esta máquina está lista para contribuir a Workspace.

**Cuándo:** Si vas a programar en Workspace.

_también: `dev-setup`_

### `workspace migrar-legado [--apply | --retire | --rollback <respaldo>]`

Migra o retira la instalación anterior de Workspace, con respaldo.

**Cuándo:** Solo si venías de la versión anterior (con el nombre viejo).

_también: `migrate-legacy`_

### `workspace desinstalar [--dry-run | --no-backup | --keep-folder | --limpiar-todo]`

Desinstala Workspace de esta máquina (tus cerebros se quedan).

**Cuándo:** Si ya no lo vas a usar aquí.

_también: `uninstall`, `remove`_

> Cambia cosas en esta máquina.

### `workspace comandos [--json | --markdown | --check]`

Sin nada más, abre el hub en Ayuda › Comandos; --json para agentes, --markdown para el manual.

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
