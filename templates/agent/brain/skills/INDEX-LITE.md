# Skills de {{AGENT_DISPLAY}} — índice ligero (tier 1)

> Esto es lo ÚNICO de skills que se carga al boot. El catálogo completo es
> `skills/README.md` (tier 2) — cargarlo solo al iniciar una tarea no trivial.

**Categorías:** {{SKILL_CATS}} · investigación · meta
**Total:** 12 (el conteo real está en `skills/README.md`).

| Categoría | Cuándo cargar el catálogo |
|---|---|
| {{SKILL_CATS}} | tareas del dominio de {{AGENT_DISPLAY}} *(nacen vacías — se pueblan por uso)* |
| investigación | investigar un tema a fondo / producir documento citado |
| meta | crear/mejorar/curar skills · reload del cerebro · colaborar con otro agente por el bus |

configurar-workspace, personalizar-workspace, reparar-workspace, calendario-y-tareas, memoria-de-la-pestana.

**Regla del Skill Loop (inmutable):** antes de cualquier tarea no trivial, revisar este índice;
si la categoría aplica → `Read skills/README.md` → `usar_skill` → seguirla → registrar uso
(su `.usage.json`, editado sin comandos: ver README). Toda respuesta con tool calls termina con el
bloque 🧠 (`BRAIN.md §6`).
