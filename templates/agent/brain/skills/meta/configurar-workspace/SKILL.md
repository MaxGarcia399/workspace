---
name: configurar-workspace
description: "Cómo {{AGENT_DISPLAY}} configura Workspace para el socio: motores, llaves y actualizaciones. Usar cuando pida conectar un motor, ver de dónde sale una llave o saber si hay actualización. Los comandos son los de la ayuda real; si un flag no está ahí, no existe."
version: 1.1.0
category: meta
tags: [meta, workspace, motores, llaves, actualizar]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Configurar Workspace — {{AGENT_DISPLAY}}

Workspace abre los motores oficiales con la cuenta del socio. No reescribe su
configuración ni guarda sus credenciales. Las llaves de Workspace y
las actualizaciones sí son de Workspace.

## Cuándo usarla
- «Conecta el motor», «no entra a la cuenta».
- «¿Dónde quedó la llave?», «¿hay una actualización?».
- Antes de tocar un archivo de configuración de un motor: casi nunca hace falta.

## Comandos

Motores y cerebros (la ayuda de `workspace --help`):

`workspace agentes estado`

`workspace agentes descubrir`

`workspace agentes reubicar`

Entrar a la cuenta de un motor se hace en el hub, en **Motores**: «Iniciar
sesión», «Instalar» y «Reparar» abren el programa oficial de ese motor en la
terminal y, al terminar, el socio vuelve a Motores. El login exacto está en el
manual, capítulo «Agentes y motores». No le agregues flags.

Llaves de Workspace. Nunca imprime el valor:

`workspace llaves estado`

`workspace llaves auditar`

`workspace llaves auditar --json`

Actualizaciones. `--check` solo mira:

`workspace version`

`workspace actualizar --check`

`workspace migrar --pending`

Si el socio prefiere verlo en pantalla: en el hub, **Ajustes › Actualizaciones**
muestra los pasos en vivo.

En Windows el programa es `python`, no `python3`, cuando un comando lleve el
intérprete. Estos no lo llevan.

## Qué no hacer
- No editar a mano los archivos que Workspace administra (hooks, el registro de
  agentes, la bóveda, `settings` del hub).
- No tocar llaves en texto plano: no las pegues en el chat, en un archivo del
  cerebro ni en un mensaje de sala. `workspace llaves` no muestra el valor; tú
  tampoco.
- No publicar. No hagas `git push`, ni un release, ni `workspace actualizar` sin
  `--check` salvo que el socio lo pida en esta pestaña: sin `--check` actualiza
  y repara.
- No leas el código de un motor. Su documentación, su `--help` y lo que se ve
  desde fuera alcanzan.

## Cómo comprobar
- `workspace agentes estado` lista el agente y no dice que le falta el cerebro.
- `workspace llaves estado` dice el modo y dónde se guardan, sin un secreto.
- `workspace llaves auditar` termina en «sin restos en texto plano» o marca la
  ruta del resto, nunca el valor.
- `workspace actualizar --check` dice si hay versión nueva y no cambia nada.


## Preferencias del equipo
**(sin preferencias registradas)**
