# Guía para agentes

Qué puede hacer un agente por ti dentro de Workspace, y en qué skill está cada
cosa. Las skills viajan en la plantilla del cerebro (`skills/meta/`). Un
cerebro que ya existía las recibe al actualizar, al cargarlo o con
`workspace doctor`: se copian las que faltan. Una copia que sigue tal cual la
dejó una versión anterior se pone al día, con respaldo; la que tú o tu agente
cambiaron no se toca.

*[English version](../en/agents.md)*

## Dónde está cada skill

| Si le pides… | La skill |
|---|---|
| Conectar un motor, ver una llave, saber si hay actualización | `skills/meta/configurar-workspace/` |
| Cambiar el tema, el tono o el idioma | `skills/meta/personalizar-workspace/` |
| Que algo no abre: doctor, pestañas, hooks, una sesión que sigue en segundo plano | `skills/meta/reparar-workspace/` |
| Un evento o una tarea | `skills/meta/calendario-y-tareas/` |
| Hablar con otro agente | `skills/meta/colaborar-por-bus/` |
| Recordar algo de esta pestaña | `skills/meta/memoria-de-la-pestana/` |

La lista completa de comandos, generada del programa: [Comandos](comandos.md).
Un agente la vuelve a leer con `workspace comandos --json`. Si un flag no sale
ahí, no existe.

## Qué no hace el agente

- No edita a mano los archivos que Workspace administra (hooks, la agenda, la
  memoria de la pestaña, la bóveda).
- No pone llaves en texto plano. `workspace llaves` dice de dónde sale cada
  una y nunca muestra el valor.
- No publica ni sube código. Actualizar, sin pedirte antes, solo se mira con
  `workspace actualizar --check`.

## Cómo saber que quedó

`workspace doctor --check` mira y no cambia nada. Cada skill dice, al final,
qué comando confirma el cambio.