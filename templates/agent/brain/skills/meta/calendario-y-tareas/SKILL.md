---
name: calendario-y-tareas
description: "Cómo {{AGENT_DISPLAY}} anota un evento o mueve una tarea de Workspace. El calendario está en el hub; la agenda y la cola de tareas tienen comandos. No inventes un subcomando que agenda tareas --help no liste."
version: 1.1.0
category: meta
tags: [meta, workspace, calendario, agenda, tareas]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Calendario y tareas — {{AGENT_DISPLAY}}

La agenda vive en esta máquina. El calendario la muestra en el hub. La cola de
tareas es otra vista de los mismos eventos, para que un agente reclame una.

## Cuándo usarla
- «Agrega un evento», «¿qué tengo el martes?», «marca esa tarea hecha».
- Una tarea de la agenda que hay que reclamar, bloquear o soltar.

## Comandos

El calendario está en el hub, en **Calendario**. Este comando abre el hub ahí:

`workspace calendario`

Un evento rápido, en texto. Fecha `YYYY-MM-DD`. `--cat` es `reunion`, `hito`,
`recordatorio`, `cumple` u `otro`:

`workspace agenda add YYYY-MM-DD "titulo" --time HH:MM --cat reunion`

`workspace agenda done <id>`

`workspace agenda rm <id> --hard`

`--hard` borra de verdad. Sin `--hard`, `rm` no es el camino para deshacer un
hecho: `done` marca, `rm` quita.

La cola (`workspace agenda tareas --help`):

`workspace agenda tareas list`

`workspace agenda tareas claim next --agent <agente>`

`workspace agenda tareas finish <id> --token <token>`

`claim` pasa una tarea `ready` a en curso y devuelve el token. `finish` la
cierra y exige ese token. También existen `mark`, `block` y `release`, con la
misma ayuda. `list` acepta `--status` (`ready` por defecto) y `--json`.

En Windows, `python` en vez de `python3` cuando el comando lleve intérprete.

## Qué no hacer
- No editar a mano los archivos que Workspace administra (el archivo de la
  agenda). Si el comando falla, no reescribas el JSON.
- Pide confirmación al socio antes de `workspace agenda rm <id> --hard`: borra de
  verdad y no se deshace.
- No tocar llaves en texto plano. Un evento no lleva secretos.
- No publicar. Anotar un evento no sale de esta máquina.
- No inventes un alta dentro de tareas: el alta es `workspace agenda add`.

## Cómo comprobar
- `workspace agenda tareas list` muestra el id nuevo, o ya no lo muestra si
  quedó `done`.
- `workspace agenda tareas claim next --agent <agente>` imprime JSON con
  `task` y un `claim_token`. Sin token, no llames a `finish`.
- El mismo evento se ve en el hub, en Calendario.

## Preferencias del equipo
**(sin preferencias registradas)**
