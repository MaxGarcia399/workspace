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
**Semanal, sola:** cuando pasaron ≥7 días desde la última curación (fecha en
`STATE/skill-curator-last.md`, que viaja con el cerebro), Workspace me lo pide al abrir la pestaña
y deja la curación reservada a mi sesión en ese archivo (así otra pestaña u otra máquina no la
repite). La hago en ese momento, sin preguntar, y al terminar escribo ahí solo la fecha de hoy
(AAAA-MM-DD). También a pedido: "cura las skills". Nada de esto espera la aprobación de nadie.

## Parte 0 — Guardas antes de tocar nada (obligatorio, en este orden)

### 0.1 Nada se pierde (sin comandos)
Nunca borro: archivar es marcar (Parte 1). Antes de fusionar o reescribir una skill, copio su
`SKILL.md` vigente a `skills/_archive/<categoría>/<skill>-v<versión>/SKILL.md` con mis
herramientas de archivos (si ya hay una copia igual, no la repito). Sin commits ni comandos.

### 0.2 Todas son curables
`created_by` es siempre un agente; quien la pidió va en `pedido_por:` (en cerebros viejos, un
`created_by` de socio cuenta igual). Ninguna espera aprobación: las curo todas con las mismas
reglas, conservo su `pedido_por` al fusionar y lo reporto en mi línea 🧠.

### 0.3 Skills protegidas — NUNCA se archivan ni fusionan
Lista fija (BRAIN.md y el boot las referencian por nombre): `skill-creator` · `skill-improver` ·
`skill-curator` · `reload-brain` · `deep-research` · `research-session` · **toda skill con
`status: stub`** (son semillas, su bajo uso es esperado). La lista se ajusta aquí como cualquier
mejora (skill-improver).

### 0.4 Fuera de alcance
`skills/_archive/` (salvo reactivación de Parte 1) y, si quedara de versiones anteriores,
`skills/_propuestas/` no se curan.

## Parte 1 — Lifecycle (mecánico)
Recorrer `skills/**/SKILL.md` **elegibles según Parte 0**. El uso se lee **primero del sidecar
`.usage.json`** (`use_count`, `last_used`; convención N12) y, sin sidecar, del `used_count:`
legacy del frontmatter (congelado):

| Estado | Condición | Acción |
|---|---|---|
| **stale** | sin uso registrado ni edición en 30+ días | `status: stale` en frontmatter |
| **archive** | stale y 90+ días sin uso | `status: archivada` + sacarla de `skills/README.md` (la carpeta se queda; NUNCA borrar) |
| **reactivar** | una archivada se vuelve a usar | quitar `status: stale`/`archivada` y registrarla de nuevo (si está en `skills/_archive/`, copiarla a su categoría) |

- **Nunca borrar** — archivar preserva histórico y permite reactivar.
- **Uso bajo ≠ inútil** (anti-Goodhart): una skill estacional o de caso de borde no se archiva por
  su bajo uso; decido yo con su contenido y lo anoto en el reporte.

## Parte 2 — Consolidación (con criterio)
Detectar **clusters de skills hermanas** (mismo verbo/dominio, descripciones solapadas) — solo
entre elegibles:
1. Fusionar en **una umbrella skill** con secciones; conservar lo mejor de cada una.
2. Las absorbidas se archivan con nota `absorbed_into: <umbrella>` en su frontmatter.
3. No fragmentar por socio: una skill para los tres; preferencias en `## Preferencias del equipo`.

## Salida (siempre)
- Versionar lo tocado (bump `version`, set `last_improved`).
- Sello `STATE/skill-curator-last.md` con la fecha (AAAA-MM-DD).
- **Reconciliar `skills/README.md` + `skills/INDEX-LITE.md`** con el disco (GATE de índice).
- Reportar en `STATE/log-recent.md` y en mi línea 🧠: copias previas + cuántas stale/archivadas/
  fusionadas + saltadas por protección. Si nada: "biblioteca sana, sin cambios".

## Preferencias del equipo
- **(ejemplo)** Conservador con la consolidación: ante duda, dejar separadas
  y solo marcar candidatas a fusión en el reporte.

## Relacionado
- `skills/meta/skill-creator/SKILL.md` · `skills/meta/skill-improver/SKILL.md` · `skills/README.md`
