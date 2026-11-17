# v0.9.2
etapa: pruebas
autor: Equipo de Workspace
actualizado: 2026-11-17

La cara nueva de Workspace ya existe y la estamos usando todos los días. Ahora la hacemos sentir como producto: rápida, sin sorpresas y con una salida clara cuando algo falla. Tus agentes, sus cerebros, los 9 motores y las skills siguen igual.

## Lo que viene
- [x] **Workspace en tu navegador, más simple** — Una página local con tus agentes, cada uno con su personaje, su conversación, su tono, sus pendientes y sus archivos. Ya funciona en nuestra versión de desarrollo; ahora la pulimos.
  Las skills corren dentro del chat con su avance a la vista, y lo que el agente te pide se contesta ahí mismo.
- [x] **Cambiar de motor sin perder la conversación** — Sigues en el mismo chat con otro motor, y el motor nuevo sabe lo que se habló con los anteriores, también cuando regresas a uno que ya habías usado.
  Mientras cambia, la página dice qué está pasando y no te deja escribir a medias.
- [x] **Fallas con salida** — Si un motor se queda sin crédito, llega a su límite o pierde la sesión, la página te lo dice en simple y te ofrece seguir con otro motor o reintentar.
- [x] **Más rápida con muchos agentes** — La página ya no le pregunta todo al servidor a cada rato: el servidor le avisa solo cuando algo cambia. Con 20 agentes en reposo, el trabajo del servidor bajó de 72,9 a 3,7 ms por segundo.
- [x] **Crear un agente con un botón** — Le pones nombre y le dices en qué te va a ayudar; lo demás lo arma Workspace, con su cerebro completo desde el primer minuto.
- [x] **Modelo, esfuerzo y modo desde la página** — Cada motor ofrece solo lo que de verdad tiene, y se aplica por su camino oficial.
- [x] **Motores al día** — Workspace revisa cada versión nueva de los 9 motores antes de que te afecte, y conserva tus permisos aunque un motor cambie su comportamiento al actualizarse.
- [ ] **Grupos de agentes** — Varios agentes en la misma conversación, cada uno con su motor.
- [x] **Decisores se toma una pausa** — Sale de esta versión mientras lo rediseñamos. Tu historial se queda guardado.

## Bitácora
- 2026-11-17 — Todo lo de la v0.9.2 ya está construido y unido: la página nueva, el cambio de motor sin perder la conversación, crear agentes, modelo y modo por motor, y los motores al día. Pasó dos revisiones independientes y las pruebas en Mac y Windows; ahora la usamos antes de publicarla.
- 2026-11-16 — Probamos la página de punta a punta con agentes reales en los 9 motores, incluido crear un agente nuevo. Encontramos 19 fallas y las estamos cerrando una por una.
- 2026-11-16 — El servidor de la página ahora avisa cuando algo cambia, en vez de releerlo todo; con muchos agentes se nota.
- 2026-11-16 — Cambiar de motor ya no empieza de cero: una sola conversación por agente en el navegador, con el historial de todos sus motores.
- 2026-11-16 — Revisamos las versiones de los 9 motores y empezamos a certificarlos en sus versiones más nuevas.
- 2026-11-15 — Nuevo rumbo: la siguiente versión se enfoca en una cara nueva y simple para lo que ya funciona. Decisores sale por ahora.
- 2026-11-11 — La revisión de skills a la vista también entra a la v0.9.2.
- 2026-11-11 — Reordenamos la v0.9.2: sale sobre la v0.9.1 con Decisores, Conversaciones y la página en el navegador. Lo demás, en las siguientes.
- 2026-11-11 — En la PC avanzan Conexiones (agregar y quitar MCPs), la revisión de skills en los 9 motores, invitar a una sala y Proyectos a la vista.
- 2026-11-10 — Terminamos la v0.9.1; sale junto con la v0.9.2.
