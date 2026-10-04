---
name: skill-curator
description: Meta-skill — mantenimiento de la biblioteca de skills de {{AGENT_DISPLAY}} (stale→archive + consolidar) con guardas
version: 1.0.0
category: meta
tags: [meta, skill-lifecycle, brain-maintenance, curator]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Skill Curator — mantener sana la biblioteca de skills a largo plazo

Complemento de skill-creator (CREA) y skill-improver (MEJORA): éste **poda y consolida** para que
la biblioteca no se infle. Viene de fábrica con el template de agente.

> **Mantra:** *cientos de skills estrechas = FALLA de la biblioteca, no feature.* Mejor pocas
> skills "paraguas" con secciones que muchas casi-idénticas.

## Cuándo corre
**Semanal** (solo si han pasado ≥7 días desde la última curación — stamp en
`STATE/.skill-curator-last`). On-demand: "cura las skills".

## Parte 0 — Guardas antes de tocar nada (obligatorio, en este orden)

### 0.1 Backup pre-corrida
Antes de marcar/archivar/fusionar CUALQUIER skill: **commit de snapshot** del estado actual
(si el cerebro es repo git):
```bash
git add skills/ && git commit -m "skill-curator: snapshot pre-curación YYYY-MM-DD"
```
- Si no hay nada que commitear, anotar el HEAD actual como punto de rollback y continuar.
- Si el cerebro NO es repo git (transport obsidian-sync): copiar `skills/` a
  `STATE/tmp/skills-backup-YYYY-MM-DD/` antes de curar.
- Sin snapshot/punto de rollback → **no curar**. Reportar y abortar.

### 0.2 Provenance — `created_by` decide qué es curable

| `created_by` | Elegibilidad |
|---|---|
| un socio/dueño (ej. su identificador) | **INTOCABLE** para curación automática: no stale, no archive, no fusión. A lo sumo, sugerir en el reporte. |
| `{{AGENT_NAME}}`, otro agente del equipo, `skill-review` (agente/proceso) | curable por Parte 1 y Parte 2 |
| ausente | tratar como de socio (conservador) + flag en el reporte |

### 0.3 Skills protegidas — NUNCA se archivan ni fusionan
Lista fija (CLAUDE.md y el boot las referencian por nombre): `skill-creator` · `skill-improver` ·
`skill-curator` · `reload-brain` · `deep-research` · `research-session` · **toda skill con
`status: stub`** (son semillas, su bajo uso es esperado). Cambios a esta lista: solo un socio,
editando esta skill.

### 0.4 Fuera de alcance
`skills/_propuestas/` (cuarentena — solo un socio aprueba desde ahí) y `skills/_archive/`
(salvo reactivación de Parte 1) no se curan.

## Parte 1 — Lifecycle (mecánico)
Recorrer `skills/**/SKILL.md` **elegibles según Parte 0**. El uso se lee **primero del sidecar
`.usage.json`** (`use_count`, `last_used`; convención N12) y, sin sidecar, del `used_count:`
legacy del frontmatter (congelado):

| Estado | Condición | Acción |
|---|---|---|
| **stale** | sin uso registrado ni edición en 30+ días | `status: stale` en frontmatter |
| **archive** | stale y 90+ días sin uso | mover a `skills/_archive/<categoría>/<skill>/` (NUNCA borrar) |
| **reactivar** | una archivada se vuelve a usar | regresarla a su categoría, quitar `status: stale` |

- **Nunca borrar** — archivar preserva histórico y permite reactivar.
- **Uso bajo ≠ inútil** (anti-Goodhart): skills estacionales o de caso-de-borde se señalan, no se
  ejecutan automático.

## Parte 2 — Consolidación (con criterio)
Detectar **clusters de skills hermanas** (mismo verbo/dominio, descripciones solapadas) — solo
entre elegibles:
1. Fusionar en **una umbrella skill** con secciones; conservar lo mejor de cada una.
2. Las absorbidas se archivan con nota `absorbed_into: <umbrella>` en su frontmatter.
3. No fragmentar por socio: una skill para los tres; preferencias en `## Preferencias del equipo`.

## Salida (siempre)
- Versionar lo tocado (bump `version`, set `last_improved`).
- Stamp `STATE/.skill-curator-last` con la fecha.
- **Reconciliar `skills/README.md` + `skills/INDEX-LITE.md`** con el disco (GATE de índice).
- Reportar en `STATE/log-recent.md`: snapshot/punto de rollback + cuántas stale/archivadas/
  fusionadas + saltadas por provenance/protección. Si nada: "biblioteca sana, sin cambios".

## Preferencias del equipo
- **(ejemplo)** Conservador con la consolidación: ante duda, dejar separadas
  y solo marcar candidatas a fusión en el reporte.

## Relacionado
- `skills/meta/skill-creator/SKILL.md` · `skills/meta/skill-improver/SKILL.md` · `skills/README.md`
