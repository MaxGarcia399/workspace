---
name: buscar-memoria
description: "Cómo {{AGENT_DISPLAY}} recupera algo de su memoria: INDEX.md primero, índice FTS5 para la cola larga, grep como último recurso. Usar ante cualquier pregunta sobre el pasado/decisiones/proyectos que el contexto cargado no responde."
version: 1.0.0
category: meta
tags: [meta, memoria, retrieval, búsqueda, fts5, índice]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Buscar en memoria — {{AGENT_DISPLAY}}

El contrato de retrieval por capas (arquitectura de memoria E2+E3). El orden importa:
empieza barato (ya en contexto) y solo baja de capa si hace falta.

## Cuándo usar
- El socio pregunta por una decisión, proyecto, cliente o evento del pasado que NO está en
  lo que ya tengo cargado (MEMORY.md, la sesión actual).
- Necesito el detalle de algo que `STATE/INDEX.md` solo menciona en una línea.
- Voy a afirmar un hecho sobre el historial del equipo y quiero verificarlo, no inventarlo.

## Procedimiento (de barato a caro)

1. **Capa 1 — `STATE/INDEX.md` (ya en boot).** Es el contrato: 1 línea por cosa viva → path.
   Si la pregunta cae en algo listado, hago **1 `Read`** del path y listo. Cero búsqueda.

2. **Capa 2 — índice FTS5 (la cola larga).** Si INDEX.md no lo lista (cosa histórica, detalle
   fino), consulto el índice derivado:
   ```bash
   python3 <WORKSPACE>/memory_index.py --brain . --query "términos clave de la pregunta"
   ```
   Devuelve top snippets rankeados (BM25 × recencia × importancia) con su path. Leo el path
   del mejor resultado con `Read`. Para ver invalidados/históricos: `--historico`.
   - Si dice "sin resultados" o el .db está stale: `--reindex` y reintento (es derivado, barato).

3. **Capa 3 — `grep` (fallback eterno).** Si el índice no encuentra (término muy raro, o sin
   .db en esta máquina), `grep -ri "término" STATE/ wiki/`. Nunca falla, solo es más lento.

## Reglas
- **Verificar, no inventar.** Si la respuesta depende de un hecho del pasado, lo BUSCO. "No lo
  encuentro" es una respuesta válida; alucinarlo no.
- **El índice es DERIVADO.** Vive fuera del cerebro (`~/.claude/workspace/index/`), per-máquina,
  regenerable. Si no existe, no es un error — bajo a grep. El cron lo refresca solo.
- **Cita el path** de donde saqué el dato cuando importe (el socio puede abrirlo).

## Pitfalls
- **No re-indexar en cada consulta:** el .db ya está fresco si el cron corrió; solo `--reindex`
  si `--status` dice stale o una búsqueda esperada no aparece.
- **Query con comillas/operadores:** el módulo las sanitiza (tokens OR), no hace falta cuidarlas.

## Verificación
- [ ] Probé INDEX.md antes de buscar
- [ ] Si busqué, leí el path del resultado (no me quedé con el snippet)
- [ ] Cité la fuente si afirmé un hecho del historial

## Preferencias del equipo
**(sin preferencias registradas)**
