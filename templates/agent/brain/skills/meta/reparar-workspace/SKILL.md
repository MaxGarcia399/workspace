---
name: reparar-workspace
description: "Cómo {{AGENT_DISPLAY}} diagnostica Workspace cuando algo no abre: doctor, pestañas, hooks y el aviso de una sesión que sigue en segundo plano. Mirar no cambia nada; reparar, sí, y solo si el socio lo pidió."
version: 1.1.0
category: meta
tags: [meta, workspace, doctor, sesiones, hooks]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Reparar Workspace — {{AGENT_DISPLAY}}

Primero se mira. Reparar escribe. Las dos cosas son idempotentes: correrlas
dos veces no duplica nada.

## Cuándo usarla
- «No abre mi pestaña», «no recuerda», «el doctor se queja», «no me avisó».
- Una pestaña de Claude Code que sigue trabajando y, al volver, no retoma.

## Comandos

Solo mirar (`workspace doctor --help`):

`workspace doctor --check`

Repara lo automático. Sin `--check` sí cambia cosas; pídele al socio que lo
quiera antes de lanzarlo:

`workspace doctor`

Si el socio prefiere verlo en pantalla: en el hub, **Ajustes › Actualizaciones**
revisa y repara con los pasos en vivo.

El paquete para pedir ayuda, sin conversaciones ni llaves:

`workspace doctor --bundle`

Hooks de cada cerebro (los vuelve a preparar, no los edita):

`workspace reparar`

Pestañas. Archivar no borra (`workspace sesiones` tiene estas acciones):

`workspace sesiones lista`

`workspace sesiones lista --archivadas`

`workspace sesiones archivar <nombre>`

`workspace sesiones desarchivar <nombre>`

Si un agente no encuentra el cerebro:

`workspace agentes estado`

`workspace agentes reubicar`

Aviso de sesión en segundo plano (0.9.1). Al volver a abrir una pestaña de
Claude Code que sigue viva, Workspace escribe una línea: la pestaña sigue
trabajando en segundo plano y te conecta a ella. No hay un flag para forzar
eso. Si la línea no sale, la sesión no estaba en segundo plano o el programa
no contestó, y se abre la sesión de siempre. No lances tú el programa del
motor para engancharte.

En Windows, `python` en vez de `python3` cuando el comando lleve intérprete.

## Qué no hacer
- No editar a mano los archivos que Workspace administra: hooks,
  `settings.local.json`, la lista de pestañas. `workspace reparar` y
  `workspace doctor` los rehacen.
- No tocar llaves en texto plano. El ZIP de `workspace doctor --bundle` no las
  trae; no las agregues al reporte.
- No publicar. Un doctor en verde no es un release.
- No corras `workspace doctor` sin `--check` para «ver qué pasa»: eso repara.

## Cómo comprobar
- `workspace doctor --check` termina sin escribir y cada fase dice ✓, ⚠ o ✗.
- Tras `workspace reparar`, el agente abre y guarda una nota
  (`workspace memoria ver` muestra la nota nueva).
- `workspace sesiones lista` muestra la pestaña que el socio no encontraba, o
  `workspace sesiones lista --archivadas` si estaba archivada.
- La línea de «segundo plano» aparece sola al abrir esa pestaña. Si no aparece,
  no la inventes: di que se abrió la sesión de siempre.

## Preferencias del equipo
**(sin preferencias registradas)**
