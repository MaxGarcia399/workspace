# Portabilidad de hooks y tools entre motores — el seam

Cómo WORKSPACE mantiene **hooks y tools portables** cuando el motor deja de ser
únicamente `claude-code`. La tabla vive también **como datos** en
`connectors.PORTABILITY` (un canal por tipo de conexión); este doc es el porqué
y el contrato que cada adaptador de motor debe cumplir. Vocabulario de eventos:
`engines/EVENTS.md` (N9). Tipos de conexión: `connectors.py` (modelo a/b/c/d).
El principio 2 (orquestación neutral) ya está IMPLEMENTADO: contrato de ciclo
de vida en `engines/LIFECYCLE.md`, runner en `neutral_hooks.py` (build B).

## Principios

1. **Tools cross-motor = MCP.** El estándar que Claude Code, Codex CLI y Gemini
   CLI soportan. WORKSPACE no inventa un protocolo de tools propio: expone las
   suyas como servidores MCP y cada CLI oficial las consume con su mecanismo
   nativo de registro (⚠ flags exactas por CLI: A-VERIFICAR).
2. **Hooks ricos que un motor no tenga = capa de orquestación neutral.** Los
   listeners de `hooks/` escuchan el vocabulario N9 de `events.py`, no el
   hook-system de ningún vendor. Donde el vendor no ofrece un hook equivalente,
   quien emite el evento es WORKSPACE (su propio loop o su wrapper) — jamás se
   simula que el vendor lo emitió.
3. **Honestidad por canal.** Cada adaptador declara qué eventos puede emitir de
   verdad (patrón `events.ENGINE_MAP`: `None` = este motor no lo expone). Un
   evento que no se puede observar NO se emite.

## Canales por tipo de conexión (= `connectors.PORTABILITY`)

| Tipo | Tools | Hooks (N9) | Estado |
|---|---|---|---|
| `openai_compatible` (API keys, OpenRouter+BYOK, locales) | **ninguno** en el uso actual (headless one-shot de destilación: el request jamás anuncia `tools` — sin manos POR DISEÑO, guard N6). Cuando WORKSPACE sea dueño del loop interactivo (motor #2, E-4+): loop de tool-calling propio + **puente MCP** (WORKSPACE ejecuta la tool que el modelo pide, vía cliente MCP propio). | `workspace-loop`: WORKSPACE arma el request ⇒ emite TODOS los eventos desde su loop (`events.emit`), incluido `pre_prompt` como middleware REAL (el punto que claude-code no expone). | headless: ✅ vivo (suite). Loop interactivo: extraído en `feat/multi-engine` (patrón probado en la corrida E-2/E-3). |
| `native_api` (Anthropic Messages, Gemini API) | igual que openai_compatible: mismo seam, otro shape de request. | `workspace-loop` (idéntico). | **A-IMPLEMENTAR** — el registro los salta con razón visible, no los finge. |
| `official_cli` (Claude Code / Codex CLI / Gemini CLI, login del socio) | **MCP nativo del CLI**: WORKSPACE registra sus tools como servidor MCP en la config del CLI (claude-code: ✅ mecanismo conocido del harness; codex/gemini: ⚠ A-VERIFICAR flags/config exactas). | `vendor-hooks` donde existan (claude-code: mapping completo en EVENTS.md). Donde NO existan (codex/gemini): `workspace-wrapper` — el proceso que lanza el CLI emite lo observable desde fuera: `session_start`/`session_end` alrededor de la corrida y `headless_ingest` al normalizar la sesión (ingester → schema neutral). `pre_prompt`/`post_tool_write` NO son observables desde fuera de un CLI ajeno ⇒ no se emiten (honestidad). | claude-code: ✅ completo. codex: andamiaje (`OFFICIAL_CLIS`, `official_cli_status`, ingester `parse_codex`) ⚠ A-VERIFICAR. gemini: asiento A-IMPLEMENTAR. |

## Qué debe traducir cada adaptador de motor (checklist del seam)

Un adaptador nuevo (motor o CLI) declara/implementa:

1. **Conexión** — perfil en `providers/<n>.json` (tipo, base_url, auth por
   NOMBRE de env-var). El vet de `connectors.py` es ley: suscripción ⇒ solo
   CLI oficial; jamás secretos en el perfil.
2. **Invocación headless** — backend en `headless.py` (o vía
   `register_provider_backends`) con `can_disable_tools` HONESTO: sin
   tools-off verificado no hay destilación (invariante Argus).
3. **Datos** — ingester en `neutral_transcript.py` (crudo del vendor → schema
   `workspace.transcript` v1). Los consumidores jamás ven el formato del vendor.
4. **Eventos** — columna en `events.ENGINE_MAP`: para cada evento N9, el hook
   nativo equivalente, `INTERNAL` (lo emite WORKSPACE) o `None` (no existe — no
   se finge).
5. **Tools** — cómo el motor consume los servidores MCP de WORKSPACE (config
   nativa del CLI) o, si WORKSPACE es dueño del loop, el puente MCP propio.

Lo que quede sin verificar contra el binario/API real se marca **A-VERIFICAR**
en el código y en `OFFICIAL_CLIS` — igual que hoy codex.
