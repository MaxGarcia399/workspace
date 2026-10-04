---
name: skill-creator
description: Meta-skill — cuándo y cómo {{AGENT_DISPLAY}} crea skills automáticamente desde tareas completadas
version: 1.0.0
category: meta
tags: [meta, automatización, skill-lifecycle]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Skill Creator — memoria procedural de {{AGENT_DISPLAY}}

Define CUÁNDO y CÓMO {{AGENT_DISPLAY}} crea nuevas skills automáticamente. Cuando termino una
tarea y se cumplen los criterios, creo una skill para no re-descubrir el camino la próxima vez.
Viene de fábrica con el template de agente.

---

## Cuándo crear una skill automáticamente

Crear skill al terminar una tarea si se cumple **al menos uno**:

| Criterio | Ejemplo |
|---|---|
| 4+ tool calls para completar la tarea | Busqué en 3 lugares + corrí 2 comandos + verifiqué |
| Descubrí el camino correcto tras un error | Intenté X, falló, la solución era Y |
| El socio (u otro agente) corrigió mi approach | "No, hazlo así" |
| Pasos no obvios o pitfalls reales | El orden importa, hay un falso amigo, etc. |
| Pidieron repetibilidad explícita | "Siempre que hagas X..." |

**NO crear skill si:** la tarea fue one-shot y no se repetirá; ya existe una skill (revisar
`skills/README.md`); fue puramente conversacional sin ejecución.

---

## Procedimiento

### 1. Nombre y categoría
**Nombre:** `kebab-case`, descriptivo, accionable.

**Categorías de {{AGENT_DISPLAY}}** (el detalle de cada una vive en `skills/README.md`):
**{{SKILL_CATS}}** (dominio) · **investigación** (research a fondo) · **meta** (el propio
sistema de skills). Si una skill de dominio es la PRIMERA de su categoría, crear la carpeta de
la categoría y su sección en el README.

### 2. Escribir el SKILL.md
Path: `skills/<categoría>/<nombre>/SKILL.md`. Template:

```markdown
---
name: <nombre>
description: <qué hace — 1 línea accionable>
version: 1.0.0
category: <categoría>
tags: [<tag1>, <tag2>]
created: <YYYY-MM-DD>
created_by: <{{AGENT_NAME}} | socio>
last_improved: <YYYY-MM-DD>
used_count: 0
---

# <Título legible>

## Cuándo usar
Usar cuando: [condición]. NO usar si: [exclusión].

## Inputs requeridos
- [ ] <dato 1>

## Procedimiento
1. <paso atómico 1>
2. <paso atómico 2>

## Pitfalls conocidos
- **<problema>:** <solución>   <!-- solo los reales que encontré -->

## Verificación
- [ ] <check 1>

## Preferencias del equipo
*(una línea por persona del equipo o dueño — se registran con el uso)*
```

### 3. Actualizar el índice — GATE OBLIGATORIO
> Fuga histórica #1 del equipo: skills creadas que nunca entran al README. **No se cierra la
> creación sin esto.**

En `skills/README.md`: agregar fila en la categoría correcta + reconciliar el `**Total: N skills**`
contando de verdad:
```bash
find skills -mindepth 2 -name SKILL.md -not -path "*/_propuestas/*" -not -path "*/_archive/*" | wc -l
```
Si cambió el conteo o nació una categoría: reflejarlo también en `skills/INDEX-LITE.md` (tier 1).

### 4. Notificar
Última línea de la respuesta, tras `---`:
```
---
🧠 Skill creada: `<nombre>` → `skills/<categoría>/`
```

---

## Checklist de calidad
- [ ] No invento — capturo lo que realmente hice
- [ ] Pasos atómicos · Pitfalls reales (no hipotéticos)
- [ ] Nombre accionable · Categoría correcta para retrieval
- [ ] No duplica skill existente (revisé `skills/README.md`)

## Preferencias del equipo
*(una línea por persona del equipo o dueño — se registran con el uso)*

## Relacionado
- `skills/meta/skill-improver/SKILL.md` · `skills/meta/skill-curator/SKILL.md` · `skills/README.md`
