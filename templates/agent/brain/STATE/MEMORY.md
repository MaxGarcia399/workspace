# Memoria de {{AGENT_DISPLAY}} — curada, largo plazo

Mi memoria destilada (no cronológica — para eso está `STATE/log-recent.md`). Cada sesión arranco
fresh; **este archivo ES mi memoria.** Visible para los tres socios — info que no debe compartirse
no va aquí.

<!-- core blocks (N13 — convención MemGPT/Letta aterrizada a archivos):
bloques `## [bloque] Título` con límite SUAVE en chars; secciones con la misma
etiqueta se suman. Medir: `python3 ~/Desktop/WORKSPACE/memory_blocks.py --brain .`
u `workspace doctor` (fase 8 — solo avisa, jamás edita). Excedente → ARCHIVAR
(decay, nunca borrar) a `STATE/memoria-archivo/<bloque>-YYYY-MM.md`; lo hace un
humano o consolidación CON gate — ningún pipeline escribe este archivo
(el Dreaming N1 escribe STATE/DESTILADO.md; promover de ahí = humano).
core-block-limits: persona=1500 equipo=1200 proyectos=2000 infra=1500 preferencias=1000
tier1-target: ~2.5k tokens en total (presupuesto de boot del template)
-->

## [persona] Modo de operación

- Soy **{{AGENT_DISPLAY}}** — {{TAGLINE}}. Color {{COLOR}}. Detalle en BOOT.
- *(vacío al nacer — se llena en las primeras sesiones con lo que de verdad importa recordar)*

## [equipo] Equipo

- *(vacío al nacer — los socios/dueños y sus IDs viven en `BOOT/02-TEAM.md`; resumir aquí solo
  lo que de verdad importe recordar entre sesiones.)*
- Otros agentes del equipo (si los hay) y sus dominios: se anotan aquí conforme se colabora.
  Coordinación por inboxes.

## [proyectos] Proyectos activos

- *(vacío al nacer)*

## [infra] Estado del agente

- **Runtime:** Claude Code vía WORKSPACE (`{{AGENT_NAME}}` / menú `workspace`).
- **Cerebro:** `~/Desktop/{{AGENT_UPPER}} - BRAIN` · nacido {{DATE}} del template
  `WORKSPACE/templates/agent/` (sistema de memoria por tiers incorporado de fábrica).
- **Registro:** `WORKSPACE/agents/{{AGENT_NAME}}/agent.json` + brand {{COLOR}}.

## [preferencias] Convenciones aprendidas

- *(vacío al nacer — se puebla por uso real, no con datos de ejemplo)*
