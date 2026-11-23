---
name: memoria-de-la-pestana
description: "Cómo {{AGENT_DISPLAY}} guarda y lee la memoria de esta pestaña: nota, vigente, maleta y resumen. Workspace la ordena; no se escribe el archivo a mano. Usar cuando haya que recordar una decisión, un pendiente o el resumen para otro motor."
version: 1.0.0
category: meta
tags: [meta, workspace, memoria, pestaña]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Memoria de la pestaña — {{AGENT_DISPLAY}}

Cada pestaña tiene su memoria. Workspace la ordena: lo vigente arriba, lo
viejo al archivo, y una maleta con lo último de cada motor. Tú pones la nota;
no editas el archivo.

## Cuándo usarla
- Hay que recordar una decisión, un pendiente, un dato o una preferencia.
- Cierras un pendiente o dejas el resumen para seguir en otro motor.
- El socio pregunta qué quedó vigente en esta pestaña.

## Comandos

La ayuda de `workspace memoria --help` lista estos comandos:

`workspace memoria ver`

`workspace memoria vigente`

`workspace memoria maleta`

Una nota. `--tipo` es `decision`, `pendiente`, `hecho`, `nota`, `dato` o
`preferencia`. Un pendiente devuelve un id (`P-3`). Cerrarlo es un hecho:

`workspace memoria nota --tipo pendiente "texto"`

`workspace memoria nota --tipo hecho "texto" --cierra P-1`

`dato` y `preferencia` valen para todas las pestañas. El resto, para esta.

El resumen, al terminar una unidad de trabajo. `--expected-revision` es la
revisión que acabas de leer; si alguien la cambió, el comando no pisa:

`workspace memoria checkpoint --expected-revision 0 --objective "que" --decision "decision" --blocker "nada" --next-step "siguiente" --result "listo"`

`--objective` y `--next-step` hacen falta. Los otros pueden ir vacíos. No
pases `--tab` ni `--brain` si ya estás en tu pestaña: Workspace los resuelve.
`--json` solo cambia el formato de la nota, no lo que guarda.

En Windows, `python` en vez de `python3` cuando el comando lleve intérprete.
En PowerShell 5.1 el acento se pierde en la tubería: el texto va entre comillas
simples o en un archivo, no inventes otro flag.

## Qué no hacer
- No editar a mano los archivos que Workspace administra (la ficha de la
  pestaña, `STATE/MEMORY.md` para una nota de sesión, el checkpoint).
- No tocar llaves en texto plano. Una nota no lleva secretos ni contraseñas.
- No publicar. La memoria se queda en el cerebro.
- No cierres un pendiente con otro tipo: se cierra con `--tipo hecho` y
  `--cierra`.

## Cómo comprobar
- `workspace memoria ver` muestra la nota con su etiqueta.
- Un pendiente imprime su id. Tras el hecho, `workspace memoria vigente` ya no
  lo trae abierto.
- `workspace memoria checkpoint` responde JSON `ok` y un número de `revision`.
  Si responde que hay conflicto, lee `workspace memoria ver` y reintenta con
  esa revisión. No pises.

## Preferencias del equipo
**(sin preferencias registradas)**
