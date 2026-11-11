# v0.9.2
etapa: pruebas
autor: Equipo de Workspace
actualizado: 2026-11-11

Estamos probando la v0.9.2 a mano, en Mac y en Windows, antes de publicarla. Ya pasó todas sus pruebas automáticas en las dos. Trae también todo lo de la v0.9.1, que no salió por separado.

## Lo que viene
- [x] **Conexiones** — Una sección nueva del hub para ver qué MCP tiene cada uno de tus motores.
  Solo lectura: te dice si el MCP está en el motor, si solo está en Workspace (el motor no lo lee), si el archivo no se pudo leer o si ese motor no lo admite. También con `workspace conexiones`.
- [x] **Workspace en el navegador** — Tus agentes en una página local, solo en esta computadora.
  Una entrada nueva del hub (y `workspace web`) abre la página en tu navegador. Se cierra con Ctrl+C o con «Apagar».
- [x] **Revisión de skills a la vista** — Opcional y apagada de fábrica.
  Si la enciendes, la revisión de lo que tu agente aprendió corre en una pestaña que ves, con el motor que elijas, un tope de tokens y Deshacer. Solo cuenta una skill como creada si puede comprobar quién la escribió.
- [x] **Tus agentes saben usar Workspace** — Cinco skills nuevas y un manual en español e inglés.
  Configurar, personalizar y reparar Workspace, calendario y tareas, y memoria de la pestaña. Llegan solas a los cerebros que ya tienes, con respaldo.
- [x] **Conversaciones: salir y volver** — `conversar salir` y `conversar unirse`.
  Lo que alguien dijo en una sala nunca deja de contar, aunque tu Mac y tu PC tengan la hora distinta.
- [x] **Decisores te dice qué pasó después** — De la v0.9.1.
  El Historial separa una opinión de un resultado comprobado y solo dice «sí» cuando hay prueba.
- [x] **Arreglos** — MCPs honestos, ajustes que no se pierden, proxy y Windows.
  Workspace ya no pisa un MCP que agregaste a mano ni dice «conectado» si el motor no lo lee; no escribe encima de un `settings.local.json` que no pudo leer; con el proxy apagado lo dice tal cual; y en Windows la revisión de skills cierra bien el motor.
- [~] **Pulido con las pruebas a mano** — Lo que encontremos al usarla, antes de publicarla.
  Ya empezamos con Conexiones, Workspace en el navegador, la guía para agentes y Conversaciones.

## Bitácora
- 2026-11-11 — Empezamos a pulir Conexiones, Workspace en el navegador, la guía para agentes y Conversaciones con lo que vimos al usarlas.
- 2026-11-11 — Conexiones y Workspace en el navegador ya aparecen en el hub. Empiezan las pruebas a mano en Mac y Windows.
- 2026-11-11 — La v0.9.2 pasó todas sus pruebas automáticas en Mac y Windows, con dos revisiones de Greptile.
- 2026-11-10 — Terminamos la v0.9.1; sale junto con la v0.9.2.
