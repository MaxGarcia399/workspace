---
name: workspace-pagina
description: El detalle de cómo hablarle al socio por la página y el hub de Workspace (el modo chat). Las reglas cortas ya te llegan siempre en esa conversación; léela para preguntarle con opciones, enseñarle un archivo, usar una skill a su vista, contarle tu avance o cambiar tu color, tu monito o tu nombre.
---

# Hablarle al socio por la página (modo chat)

El socio te lee en un chat de Workspace (la página o el hub), no en una terminal. Cuando la conversación es de ahí, la
guía corta del modo chat te llega sola (en tu sesión o antes de su primer mensaje); esta skill es su detalle. No le
pidas que pique nada: estas herramientas lo hacen por ti. Usa las del servidor MCP `workspace`; si no las tienes, el
comando de respaldo (cada uno completo, solo, en una línea: no pide permiso).

| Para | Herramienta | Respaldo |
|---|---|---|
| Enseñarle un archivo | `mostrar_archivo` (ruta, titulo) | `workspace pasos archivo <ruta> --titulo "…"` |
| Preguntarle algo | `preguntar` (pregunta, opciones) | `workspace pasos preguntar "¿…?" --opcion "A" --opcion "B"` |
| Usar una skill a su vista | `usar_skill` (skill) | `workspace pasos usar <skill>` |
| Contar tu avance en esa skill | `reportar_avance` (ejecucion, accion) | `workspace pasos <id> plan`, `ahora N`, `hecho N`, `pide "…" --opcion …`, `fin "…"` |
| Cambiar cómo te ve | `personalizar` (color, forma, nombre) | `workspace pasos personalizar --color verde` |

## Cómo se ve en un chat

- **Corto y lo esencial primero**, en markdown simple: párrafos cortos, alguna lista, **negritas** y `código`.
- **Archivos:** con `mostrar_archivo`: una tarjeta con «Abrir» y «Mostrar en la carpeta» (el menú «1 abrir / 2 revelar
  / 3 seguir» de la terminal). Nada de rutas crudas ni enlaces `file://`. Solo archivos dentro de tu carpeta (tu
  cerebro); la ruta, relativa a ella o completa.
- **Elegir:** con `preguntar` y sus opciones, nunca una lista numerada para que teclee un número.
- **Sin cosas de terminal:** ni separadores `---`, ni menús numerados, ni la sintaxis de tus herramientas pegada en el
  texto.
- **Lo que Workspace ya enseña no se narra:** «Empezó», tus pasos y «Terminó» ya los ve; no le digas «Workspace
  registró el cierre».
- **El cierre de tu cerebro** (la línea 🧠, si tu cerebro la pide): en una sola línea al final. La página la enseña
  discreta, o como tarjeta si aprendiste o mejoraste una skill.

## Cuándo

- **Pregunta con opciones** siempre que la respuesta sea elegir: de 2 a 6 opciones cortas. Si es sí o no, tipo
  `confirmar`. Abierta solo si de verdad es texto libre. Después **termina tu turno**: le sale en su caja de escribir,
  enmarcada en tu color, y su respuesta te llega como su próximo mensaje. En la página no la repitas en el chat.
- **Usa una skill a la vista** cuando el socio te pida una skill o tú decidas usar una: con `usar_skill` ve «Empezó
  …», su proceso y su barra. Te devuelve el id de la ejecución y su SKILL.md: síguela en ese mismo turno.
- **Cuenta tu avance** con ese id: `plan` al empezar, `ahora` y `hecho` en cada paso, `pide` si necesitas algo de él
  (con opciones si se elige) y `fin` con el resumen en una línea: es lo que ve en «Terminó».
- **Enséñale el archivo** que dejaste con `mostrar_archivo`, en el turno donde lo terminas.
- **Personalízate** solo si él lo pide o te dice que sí: pregúntale antes, con opciones Sí / No. Colores: verde,
  azul, rosa, morado, amarillo o blanco. Monitos: bolita, pico, cuadrito, gatito, fantasma o nube.

## Ejemplo

«Usa una skill para hacer una página, pregúntame un color y al final enséñame el archivo»: `usar_skill` → `plan` →
`preguntar` «¿De qué color?» con opciones y termina tu turno → con su respuesta, `ahora` y `hecho` → `mostrar_archivo`
con la página, `fin` con el resumen y un mensaje corto.
