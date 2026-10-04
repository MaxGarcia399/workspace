# WORKSPACE · templates/ — el paquete inicial de agente

Template para crear agentes nuevos del equipo sin cablear todo a mano. Colapsa los 8 pasos de la
skill `cablear-agente-workspace` en: **correr un comando + diseñar el SOUL**.
Incorpora el sistema de memoria eficiente (tiers HOT/WARM/COLD + sesiones) desde el día 1.

```
templates/
├── README.md          ← esto
├── new_agent.py       ← instanciador (stdlib, cross-platform, --selftest incluido)
└── agent/
    ├── brain/         ← scaffold del cerebro → "<UPPER> - BRAIN/" (~26 archivos)
    │   ├── CLAUDE.md                 entry point lean + context_budget declarado
    │   ├── .gitignore                settings.local / socio.local / locks fuera de sync
    │   ├── BOOT/00…04                soul (esqueleto guiado) · tarjeta · equipo · reglas · mapa
    │   ├── STATE/                    MEMORY (core blocks N13 acotados) · PENDIENTES ·
    │   │                             MILESTONES · log-recent · DESTILADO · brain-version ·
    │   │                             sessions/<socio> · inbox · users · memoria-archivo
    │   ├── skills/                   INDEX-LITE (tier 1) + README (tier 2) + _propuestas +
    │   │                             meta/{skill-creator,skill-improver,skill-curator,reload-brain}
    │   │                             investigación/{deep-research,research-session}
    │   ├── wiki/index.md             tier 3, nace vacío
    │   └── adapters/claude-code.md   runtime primario
    └── workspace/       ← lado harness → WORKSPACE/agents/<nombre>/
        ├── agent.json                con scripts.statusline SIEMPRE (pitfall conocido)
        └── brand/agent-{banner,dashboard,statusline}.py   stubs sobrios por paleta
```

## Los 6 parámetros (todo lo demás es común)

| # | Parámetro | Flag | Placeholder(s) | Ejemplo |
|---|---|---|---|---|
| 1 | **nombre** | `<name>` (+ `--display`) | `{{AGENT_NAME}}` `{{AGENT_DISPLAY}}` `{{AGENT_UPPER}}` | `hermes` / Hermes / HERMES |
| 2 | **rol / tagline** | `--tagline` | `{{TAGLINE}}` | "Motor de ejecución autónoma en VPS" |
| 3 | **soul (semilla)** | `--soul` | `{{SOUL_HINT}}` | "mensajero-ejecutor: rápido, silencioso" |
| 4 | **categorías de skills** | `--skills` | `{{SKILL_CATS}}` | `ejecución,automatización,monitoreo` |
| 5 | **color de marca** | `--color` | `{{COLOR}}` | `azul` (dorado·coral·verde·azul·morado·cyan·gris) |
| 6 | **scope / restricciones** | `--scope` | `{{SCOPE}}` | "escribe solo en su cerebro; WORKSPACE solo lectura" |

(`{{DATE}}` se sustituye solo, con la fecha del día. Si el color elegido ya lo usa otro agente
del equipo, el instanciador lo avisa; `--force-color` para insistir.)

## Flujo de creación

```bash
cd ~/Desktop/WORKSPACE
python3 templates/new_agent.py hermes \
  --tagline "Motor de ejecución autónoma en VPS" \
  --soul "mensajero-ejecutor: rápido, silencioso, sin preguntas" \
  --skills "ejecución,automatización,monitoreo" \
  --color azul \
  --scope "escribe solo en su cerebro y /srv/jobs; WORKSPACE solo lectura" \
  --register            # opcional: lo agrega a agents/registry.json
```

Eso produce `~/Desktop/HERMES - BRAIN/` + `WORKSPACE/agents/hermes/` en ~2 minutos, verifica que
no quedaron placeholders y valida el agent.json. `--dry-run` para ver el plan sin escribir.
**Se niega a tocar destinos existentes** — jamás pisa un cerebro real.

### Después del comando (gates deliberados — el comando NO los salta)

1. **Diseñar `BOOT/00-SOUL.md`** — nace como esqueleto guiado (preguntas en comentarios). La
   personalidad es diseño humano (N3); es lo que realmente importa diseñar. Hasta entonces el
   agente opera sobrio.
2. **Hook de auto-aprendizaje:** crear `<brain>/.claude/settings.local.json` con **SOLO** el
   bloque `hooks` (`SessionEnd → WORKSPACE/hooks/skill_review.py`). ⚠️ No incluir
   `permissions.defaultMode: dontAsk` + Bash — el clasificador lo bloquea
   (`cablear-agente-workspace §3`); los permisos los agrega el socio a mano.
3. **Registrar** (si no se usó `--register`): mover el agente a `agents` en
   `agents/registry.json`.
4. **`python3 install.py <socio>`** — genera launcher `~/.local/bin/<nombre>`, statusline,
   `socio.local`. Idempotente.
5. **Verificar:** `workspace doctor` + terminal nueva + lanzar `<nombre>`. La statusline aparece
   solo en terminal nueva (los settings se cargan al arrancar).
6. **Sync del cerebro:** Obsidian Sync por default; `git init` solo si el socio lo declara
   (`paths.local.json → transport`).

### Creación manual (sin el comando)

Copiar `templates/agent/brain/` al destino, `templates/agent/workspace/` a `agents/<nombre>/`,
renombrar `brand/agent-*.py` → `brand/<nombre>-*.py`, y buscar-y-reemplazar los placeholders de
la tabla (son los únicos: `grep -r "{{" <destino>` debe quedar vacío al terminar). Luego los
mismos gates de arriba.

## El sistema eficiente que trae de fábrica (T1 del diseño)

Los agentes del template nacen dentro de la cota — no hay que retro-aplicarles nada:

| Feature | Dónde quedó |
|---|---|
| `context_budget` declarado (target 2.5k tokens de boot) | comentario al inicio de `CLAUDE.md` |
| Boot lean: log-recent/MILESTONES/wiki/catálogo completo FUERA del tier 1 | `CLAUDE.md §2` + `BOOT/04-BRAIN-MAP.md` (tabla de tiers) |
| Core blocks acotados (N13: persona/equipo/proyectos/infra/preferencias) | frontmatter de `STATE/MEMORY.md` |
| `skills/INDEX-LITE.md` (≤300 tokens al boot; el README completo es tier 2) | `skills/` + gate de reconciliación en skill-creator/curator |
| Flujo episódico cerrado: sesión → journal → Dreaming → `DESTILADO.md` → MEMORY (gate humano) | `STATE/DESTILADO.md` + `CLAUDE.md §7` |
| Decay never-delete (`memoria-archivo/`) | `STATE/memoria-archivo/README.md` |
| `session_journal: true` + hooks genéricos de sesión | `agent.json` |
| Sin datos de ejemplo: los bloques nacen vacíos y se pueblan por uso | MEMORY/users/wiki |

## Mantenimiento del template

- El template es la **fuente única** de lo común (BOOT/02-TEAM, 03-RULES base, convenciones de
  STATE). Si algo común cambia por decisión del equipo, actualizar AQUÍ además del cerebro donde
  nació el cambio — los datos de socios en `BOOT/02-TEAM.md` son copia de los reales.
- Verificación rápida del template: `python3 templates/new_agent.py --selftest` (instancia un
  agente de prueba en un tmp, verifica estructura/sustitución/brand/registry, y limpia).
- Los brand scripts son stubs sobrios a propósito; el arte definitivo por agente (estética
  WORKSPACE) se hace después.
- NO instanciar sobre cerebros existentes ni "reestructurar" agentes vivos con esto — eso es
  decisión N3 aparte.
