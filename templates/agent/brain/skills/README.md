# Skills de {{AGENT_DISPLAY}} — catálogo

Capacidades operacionales de {{AGENT_DISPLAY}}, organizadas por categoría. **Antes de cualquier
tarea no trivial, revisar `skills/INDEX-LITE.md`** (tier 1) y, si la categoría aplica, este
catálogo. El protocolo completo del Skill Loop está en `CLAUDE.md §6`.

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
| `meta/skill-curator/` | Poda y consolidación con guardas: backup pre-corrida, provenance, protegidas, never-delete. |
| `meta/reload-brain/` | Recargar mis archivos core a mitad de sesión + reportar cambios del pipeline. |

---

## Convenciones

- Una skill = una carpeta `skills/<categoría>/<nombre>/SKILL.md` con frontmatter
  (`name`, `description`, `version`, `category`, `tags`, `created`, `created_by`, `last_improved`,
  `used_count`; opcional `status: stub`).
- Categorías de {{AGENT_DISPLAY}}: **{{SKILL_CATS}} · investigación · meta**.
- `created_by`: `{{AGENT_NAME}}` (auto-creadas), el identificador de un socio/dueño, u otro agente
  del equipo. Las de socio son intocables para procesos automáticos.
- No fragmentar: una skill sirve a todo el equipo; preferencias personales en
  `## Preferencias del equipo` dentro del mismo archivo.
- **GATE de índice (obligatorio):** después de crear/mover/archivar una skill, el `**Total: N**`
  de este README debe cuadrar con el disco. **Y reflejar el cambio en `INDEX-LITE.md` si
  cambió una categoría o el conteo.**
  ```bash
  find skills -mindepth 2 -name SKILL.md -not -path "*/_propuestas/*" -not -path "*/_archive/*" | wc -l
  ```
- **`skills/_propuestas/` (cuarentena):** las skills NUEVAS que proponga el review automático de
  WORKSPACE (`skill_review`, SessionEnd) van ahí con `status: propuesta` — nunca directo al catálogo.
- **Uso:** sidecar `.usage.json` (N12, `python3 <WORKSPACE>/usage.py <skill_dir> use`); se versiona,
  su `.lock` no.
