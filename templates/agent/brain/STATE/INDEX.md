# Índice — qué hay y dónde (contrato de retrieval)

<!-- Tope: 100 líneas. 1 línea por entidad/proyecto/decisión VIVA → path.
     Lo mantiene el consolidador (cron, nightly) + humano en sesión.
     Si rebasa 100 líneas: CONSOLIDAR (fusionar/archivar entradas muertas),
     nunca ampliar. Entradas cerradas/muertas → mover a sección Archivo o
     borrar la línea (el contenido NO se borra — sigue en su capa, alcanzable
     por grep o FTS5 en E3). Falla-suave: sin INDEX.md el agente opera como E1. -->

## Proyectos
<!-- 1 línea por proyecto activo: descripción breve (estado) → path -->
*(vacío al nacer — agregar al primer proyecto activo)*

## Decisiones vigentes
<!-- 1 línea por decisión arquitectónica en pie: qué + cuándo → path del documento -->
*(vacío al nacer — agregar en las primeras sesiones con el equipo)*

## Entidades
<!-- 1 línea por cliente, agente externo, proveedor clave → path en wiki/ -->
*(vacío al nacer — agregar conforme el agente gana contexto de equipo)*

## Convenciones
<!-- 1 línea por convención operativa que vale recordar durante el trabajo -->
- Append-only STATE + single-writer de canónicos → `wiki/concepts/append-only-state.md` (si existe)
- Sesiones por pestaña/socio → `STATE/sessions/README.md`
- Memoria por capas HOT/WARM/COLD → `BOOT/04-BRAIN-MAP.md`
- Skills: INDEX-LITE (HOT) · README completo (WARM) · skill JIT al detectar tarea → `skills/INDEX-LITE.md`

## Archivo
<!-- Entradas que ya no están activas pero conviene recordar dónde quedaron.
     No borrar: la línea describe dónde vivía algo → path en COLD (memoria-archivo/, log-archive/) -->
*(vacío al nacer)*
