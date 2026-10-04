# Skills de {{AGENT_DISPLAY}} — índice ligero (tier 1)

> Esto es lo ÚNICO de skills que se carga al boot (≤300 tokens). El catálogo completo es
> `skills/README.md` (tier 2) — cargarlo solo al iniciar una tarea no trivial.

**Categorías:** {{SKILL_CATS}} · investigación · meta
**Total:** 6 skills base (el conteo real vive en `skills/README.md` — reconciliar ahí).

| Categoría | Cuándo cargar el catálogo |
|---|---|
| {{SKILL_CATS}} | tareas del dominio de {{AGENT_DISPLAY}} *(nacen vacías — se pueblan por uso)* |
| investigación | investigar un tema a fondo / producir documento citado |
| meta | crear/mejorar/curar skills · reload del cerebro |

**Regla del Skill Loop (inmutable):** antes de cualquier tarea no trivial, revisar este índice;
si la categoría aplica → `Read skills/README.md` → cargar la skill → seguirla → registrar uso
(`python3 <WORKSPACE>/usage.py <skill_dir> use`). Toda respuesta con tool calls termina con el
bloque 🧠 (`CLAUDE.md §6`).
