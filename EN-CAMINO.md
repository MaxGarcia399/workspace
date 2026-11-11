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
- [~] **Proyectos a la vista** — El agente que recibe un proyecto trabaja en una terminal que ves.
  Antes trabajaba escondido, sin ventana. Además, Workspace conserva tus ajustes aunque no se puedan leer, en vez de escribir encima.
- [~] **Invitar a una sala que ya empezó** — Suma a otro agente, o a una pestaña en particular, a una conversación abierta.
  Hasta ahora, quien no estaba desde el principio no podía entrar.
- [~] **La revisión de skills, en los 9 motores** — Comprueba quién escribió la skill también en Antigravity, OpenCode, OpenClaw, Hermes, Kiro, Copilot y Cursor.
  Hasta ahora solo podía comprobarlo en Claude Code y Codex; en los demás la revisión terminaba «sin comprobar».
- [~] **Pulido con las pruebas a mano** — Lo que encontremos al usarla, antes de publicarla.
  Ya empezamos con Conexiones, Workspace en el navegador, la guía para agentes y Conversaciones.

## Bitácora
- 2026-11-11 — Revisión de skills: ya reconoce quién escribió la skill en 7 motores más (en pruebas en la PC).
- 2026-11-11 — Conversaciones: ya se puede invitar a un agente o a una pestaña a una sala abierta (en pruebas en la PC).
- 2026-11-11 — Proyectos: el agente que recibe un proyecto ya trabaja en una terminal visible (en pruebas en la PC).
- 2026-11-11 — Empezamos a pulir Conexiones, Workspace en el navegador, la guía para agentes y Conversaciones con lo que vimos al usarlas.
- 2026-11-11 — Conexiones y Workspace en el navegador ya aparecen en el hub. Empiezan las pruebas a mano en Mac y Windows.
- 2026-11-11 — La v0.9.2 pasó todas sus pruebas automáticas en Mac y Windows, con dos revisiones de Greptile.
- 2026-11-10 — Terminamos la v0.9.1; sale junto con la v0.9.2.
