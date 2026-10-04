# Brain Version — {{AGENT_DISPLAY}}

version: 1.0.0
last_updated: {{DATE}}
monitored: false

## Archivos core del pipeline
Cambios a estos = cambio al pipeline de {{AGENT_DISPLAY}}:
- `CLAUDE.md` — entry point, Skill Loop §6, memoria por tiers §7, context_budget
- `BOOT/00-SOUL.md` … `BOOT/04-BRAIN-MAP.md` — identidad, equipo, reglas, mapa
- `skills/INDEX-LITE.md` + `skills/README.md` — catálogo de capacidades
- `STATE/MEMORY.md` — memoria curada (core blocks N13)

## Changelog

### v1.0.0 — {{DATE}}
- **Nace del template de agente de WORKSPACE** (`WORKSPACE/templates/agent/`): scaffold completo
  BOOT 00-04 + STATE (MEMORY con core blocks acotados / PENDIENTES / MILESTONES / log-recent /
  DESTILADO / sessions / inbox / users / memoria-archivo) + Skill Loop con bloque 🧠 +
  journaling por sesión + **sistema de memoria por tiers** (context_budget declarado,
  INDEX-LITE de skills, flujo Dreaming→DESTILADO→MEMORY).
- **6 skills base:** meta (skill-creator / skill-improver / skill-curator / reload-brain) +
  investigación (deep-research / research-session). Las de dominio se construyen por uso.
- **Parámetros de instanciación:** nombre `{{AGENT_NAME}}` · tagline "{{TAGLINE}}" ·
  color {{COLOR}} · categorías {{SKILL_CATS}} · scope "{{SCOPE}}".
- **Pendiente humano:** diseñar `BOOT/00-SOUL.md` (es esqueleto guiado, no personalidad).
