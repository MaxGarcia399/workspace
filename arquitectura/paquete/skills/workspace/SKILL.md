---
name: workspace
description: Cómo trabajar dentro de Workspace. Úsala para guardar algo en la memoria de la pestaña, decir en qué estás, reportar el avance de una skill con pasos o preguntarle un dato al socio.
---

# Workspace

Estás en una pestaña de Workspace. Lo que pasa en la conversación (abrir, tus
mensajes, las herramientas, el fin de cada turno) ya lo anota el hook de
Workspace: no lo repitas a mano.

Lo que sí haces tú, con las herramientas del servidor MCP `workspace`:

- **Guardar memoria:** `memoria_nota` en el momento, una nota por cosa
  (decision, pendiente, hecho, nota, dato o preferencia). Nunca escribas la
  memoria a mano en los archivos del cerebro.
- **Resumir:** `memoria_checkpoint` al terminar una unidad de trabajo o antes de
  cambiar de motor, con la revisión que da `memoria_ver`. La maleta lo lleva al
  motor siguiente.
- **Leer:** `memoria_ver` (lo de esta pestaña) y `pendientes` (lo abierto).
- **Buscar en el pasado:** `memoria_buscar` antes de afirmar algo que se
  decidió, se dijo o se hizo: las notas de todas las pestañas, lo curado del
  cerebro y lo literal de las conversaciones (filtros: tipo, pestaña, fechas,
  fuente). Si no aparece, dilo; no lo inventes.
- **Skills del cerebro:** `skills_lista` y `skill_leer`.
- **En qué estás:** `tarea_actual`, una línea.
- **Skills con pasos:** `usar_skill` para activarla a la vista del socio,
  `reportar_avance` y, si necesitas un dato del socio, `preguntar` (con
  opciones si se elige). Si contesta `en_chat`, haz lo que dice su indicación
  y termina tu turno: la respuesta llega en el próximo mensaje.
- **Hablarle por la página** (preguntar con opciones, usar una skill a su
  vista, personalizarte): la skill `workspace-pagina`.

Lo vigente de la pestaña y el tono te llegan solos al abrir: no los pidas.

Si una herramienta contesta `[SIN_PESTANA]`, esta conversación no está atada a
una pestaña: díselo al socio y sigue sin memoria.
