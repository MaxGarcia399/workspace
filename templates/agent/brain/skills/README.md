# Skills de {{AGENT_DISPLAY}} — catálogo

Capacidades operacionales de {{AGENT_DISPLAY}}, organizadas por categoría. **Antes de cualquier
tarea no trivial, revisar `skills/INDEX-LITE.md`** (tier 1) y, si la categoría aplica, este
catálogo. El protocolo completo del Skill Loop está en `BRAIN.md §6`.

**Total: 6 skills**

## {{SKILL_CATS}} (0) — el dominio de {{AGENT_DISPLAY}}

*(nacen vacías a propósito — las skills de dominio se construyen por uso real con skill-creator,
no por scaffold. Crear las carpetas de categoría con la primera skill de cada una.)*

## investigación (2)

| Skill | Qué hace |
|---|---|
| `investigación/deep-research/` | El motor: descomponer → abanico → verificación adversarial → síntesis citada. |
| `investigación/research-session/` | Flujo completo: acotar → investigar → documento citado → catalogar. Incluye la regla "¿mío o del agente bibliotecario?". |

## meta (4) — el sistema de skills

| Skill | Qué hace |
|---|---|
| `meta/skill-creator/` | Cuándo y cómo creo skills nuevas desde tareas completadas. |
| `meta/skill-improver/` | Cómo aplico feedback (general vs. preferencia personal). |
| `meta/skill-curator/` | Poda y consolidación semanal, sola: copia previa, protegidas, never-delete. |
| `meta/reload-brain/` | Recargar mis archivos core a mitad de sesión + reportar cambios del pipeline. |

---

## Convenciones

- Una skill = una carpeta `skills/<categoría>/<nombre>/SKILL.md` con frontmatter
  (`name`, `description`, `version`, `category`, `tags`, `created`, `created_by`, `last_improved`,
  `used_count`; opcional `status: stub`).
- Categorías de {{AGENT_DISPLAY}}: **{{SKILL_CATS}} · investigación · meta**.
- `created_by`: siempre `{{AGENT_NAME}}` (u otro agente del equipo que la creó); si la pidió un
  socio, va además `pedido_por: <socio>`. Ninguna skill espera aprobación de nadie.
- No fragmentar: una skill sirve a todo el equipo; preferencias personales en
  `## Preferencias del equipo` dentro del mismo archivo.
- **GATE de índice (obligatorio):** después de crear/mover/archivar una skill, el `**Total: N**`
  de este README debe cuadrar con el disco. **Y reflejar el cambio en `INDEX-LITE.md` si
  cambió una categoría o el conteo.**
  Cuento con mis herramientas de archivos, sin comandos: `skills/*/*/SKILL.md`, sin las carpetas
  que empiezan con `_` ni las skills con `status: archivada`.
- **Sin aprobación:** creo, mejoro y archivo skills directo y lo digo en mi línea 🧠. Archivar =
  `status: archivada` en su frontmatter + sacarla de este README (la carpeta se queda; nada se borra).
- **Revisión de skills (opcional):** si está encendida, al abrir una sesión Workspace me pide
  revisar la anterior; parcho o creo skills directo en su categoría, como en el Skill Loop.
- **Uso:** sidecar `skills/<categoría>/<nombre>/.usage.json` (N12), editado con mis herramientas de
  archivos, sin comandos: al usar una skill, `use_count` +1 y `last_used` (ISO-8601 UTC); al
  parcharla, `patch_count` +1 y `last_patched`. Si no existe, lo creo así: `{"schema": 1,
  "use_count": 1, "view_count": 0, "patch_count": 0, "last_used": "…"}` (sumando el `used_count:`
  viejo del frontmatter, si lo tiene). Se versiona; su `.lock` no.
