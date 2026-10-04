---
name: reload-brain
description: "Recarga los archivos core del cerebro de {{AGENT_DISPLAY}} en la sesión actual y reporta qué cambió. Usar cuando el socio dice reload/recarga, o hubo cambios al pipeline durante la sesión."
version: 1.0.0
category: meta
tags: [meta, reload, versión, contexto, sesión]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Reload Brain — {{AGENT_DISPLAY}}

## Cuándo usar
- El socio dice "reload", "recarga", "actualiza tu cerebro".
- Hubo cambios a `CLAUDE.md`, `BOOT/` o mis skills durante esta sesión abierta.
- Mi comportamiento no refleja cambios recientes al pipeline.
- Al detectar `monitored: false` en `STATE/brain-version.md` (ofrecer monitor, una vez por sesión).

## Procedimiento
1. **Leer versión:** `Read STATE/brain-version.md` → anotar `version`, `last_updated`, `monitored`,
   y las últimas entradas del changelog.
2. **Re-leer core en orden:**
   ```
   Read CLAUDE.md
   Read BOOT/00-SOUL.md
   Read BOOT/01-IDENTITY.md
   Read BOOT/02-TEAM.md
   Read BOOT/03-RULES.md
   Read BOOT/04-BRAIN-MAP.md
   Read skills/INDEX-LITE.md
   Read STATE/MEMORY.md
   ```
3. **Reportar (breve, al inicio):**
   ```
   ✅ Cerebro recargado — v[X.X.X] (actualizado [fecha])
   Cambios recientes:
   - [entrada más reciente del changelog]
   ```
   Si cambiaron las reglas (`03-RULES.md`) o el Skill Loop, destacarlo.
4. **Monitor:** si `monitored: false`, ofrecer activar un monitor diario que avise de cambios al
   pipeline (una sola vez por sesión). Si el socio dice no, respetar y dejar `monitored: false`.

## Pitfalls
- **Monitor ya activo:** verificar antes de crear el task (no duplicar).
- **`monitored: false` tras rechazo:** no volver a preguntar en la misma sesión.

## Verificación
- [ ] `brain-version.md` leído y versión anotada
- [ ] Todos los core re-leídos (CLAUDE, BOOT 00-04, INDEX-LITE, MEMORY)
- [ ] Reporte con versión + changelog reciente

## Preferencias del equipo
*(una línea por persona del equipo o dueño — se registran con el uso)*
