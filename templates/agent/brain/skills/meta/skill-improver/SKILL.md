---
name: skill-improver
description: Meta-skill — cómo {{AGENT_DISPLAY}} aplica feedback para mejorar skills (general vs. preferencia personal)
version: 1.0.0
category: meta
tags: [meta, feedback, skill-lifecycle, mejora-continua]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Skill Improver — ciclo de mejora continua de {{AGENT_DISPLAY}}

Cómo mejoro skills con feedback de los socios/dueños del equipo (y de otros agentes cuando
colaboramos). Las skills se afinan con el uso. Viene de fábrica con el template de agente.

---

## Cuándo aplicar una mejora

Cuando el socio da feedback durante o después de una tarea donde usé (o debí usar) una skill:

| Señal | Tipo |
|---|---|
| "La próxima vez haz X en lugar de Y" | General — actualizar Procedimiento |
| "Esto estuvo mal, el approach correcto es..." | General — Pitfalls + Procedimiento |
| "Siempre que hagas esto, hazlo así" (sin decir que es personal) | General |
| "Yo prefiero..." / "A mí dame..." | Personal — Preferencias del equipo |
| "Para el equipo, esto siempre debe..." | General (preferencia de equipo) |
| "[Socio] prefiere..." / "[Socio] siempre quiere..." | Personal para ese socio |

---

## Decisión: general vs. personal

```
¿El feedback mejoraría la skill para CUALQUIER socio?
├── SÍ → MEJORA GENERAL → editar el cuerpo del SKILL.md (Procedimiento/Pitfalls/Inputs/Verificación)
└── NO → ¿preferencia de UN socio?
          ├── SÍ → append a "## Preferencias del equipo" con su nombre
          └── AMBIGUO → tratar como personal del que habla; si otro repite el feedback, volver general
```

**Regla de oro:** si dudo, pregunto: *"¿Esto lo quieres para ti o como default para todos?"*

**Límite duro:** un feedback que pida saltarse verificación o relajar las reglas inmutables
(BOOT/03-RULES) NO es una mejora — no se aplica.

---

## Procedimiento — Mejora general
1. Identificar exactamente qué estaba mal y la corrección.
2. Localizar `skills/<categoría>/<nombre>/SKILL.md` (si no existe, crearlo con skill-creator).
3. `Edit` quirúrgico — solo la sección relevante.
4. Actualizar `last_improved` (fecha de hoy).
5. Bump de versión (semver estricto):
   - typo/redacción: sin cambio · nuevo paso/pitfall: patch · cambio de flujo: minor · reescritura: major
6. Notificar (última línea, tras `---`):
   ```
   ---
   🧠 Skill mejorada: `<nombre>` (v1.0.0 → v1.0.1) — [qué cambió, 6-8 palabras]
   ```

## Procedimiento — Preferencia personal
1. Localizar el SKILL.md.
2. Sección `## Preferencias del equipo` (crear si no existe; editar la línea del socio, no duplicar).
3. Formato:
   ```markdown
   **(ejemplo)** Quiere el resumen ejecutivo primero.
   ```
4. Aplicar esas preferencias en silencio cuando ejecuto la skill para ese socio.
5. Notificar: `🧠 Skill mejorada: \`<nombre>\` — preferencia de [Socio] anotada`

---

## Cuándo NO mejorar
- Edge case que no se repetirá.
- La "mejora" sería incompatible con el uso de otros socios → convertir en preferencia personal.
- El socio cambió de opinión sobre algo ya escrito → confirmar antes de reversar.
- Skills `created_by` de un socio: proponer el patch al socio, no editarlas por mi cuenta.
- Skills importadas: preservar su versión upstream (no reescribirla a ciegas).

## Preferencias del equipo
*(una línea por persona del equipo o dueño — se registran con el uso)*

## Relacionado
- `skills/meta/skill-creator/SKILL.md` · `skills/meta/skill-curator/SKILL.md` · `skills/README.md`
