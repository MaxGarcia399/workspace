# Contrato de eventos de WORKSPACE (N9)

WORKSPACE define un set chico de **eventos propios** (~6) — vocabulario del harness, no del vendor.
Cada **motor** (ver `CONTRACT.md`) declara cómo cablea cada evento a su mecanismo nativo: en
`claude-code` son los hooks de Claude Code; en un motor futuro será lo que ese runtime ofrezca.
Resultado: los listeners de `hooks/` son **intercambiables entre motores** sin escribir un
hook-system propio.

> Esto **NO reemplaza** los hooks de Claude Code: es una capa declarativa FINA encima.
> La tabla de este documento existe también **como datos** en `events.py` (raíz de WORKSPACE):
> `install.build_hooks` deriva de ahí el bloque `hooks` que siembra en cada cerebro, y
> `doctor` (fase 5) valida contra ese mismo contrato. Los eventos de `events.POR_ARRANQUE`
> (hoy `turn_end`) no van al cerebro: `memoria.claude_settings_args` los mete, con el mismo
> runner, en el `--settings` que se rehace en cada arranque (`build_hooks(launch=True)`). Una sola fuente de verdad: agregar o
> quitar un listener se hace en `events.LISTENERS` y install/doctor lo siguen solos.

## Los eventos (vocabulario v1)

| Evento WORKSPACE | Cuándo dispara | Modo | Mapping en `claude-code` | Listeners hoy |
|---|---|---|---|---|
| `session_start` | arranca una sesión interactiva (startup / resume / compact) | observer + **inyección aditiva** (lo que el listener imprime se suma al contexto) | hook `SessionStart` | `session_start.py` (marcador) · paquete de memoria de la pestaña (`memoria.paquete`, vía `neutral_hooks`) · dashboard `--context` (per-agente, matcher `startup`) |
| `session_end` | cierra una sesión (logout, exit, clear…) | observer **cleanup-only** (la salida se ignora; no puede bloquear ni invocar al modelo) | hook `SessionEnd` | `session_end.py` (limpieza) · `skill_review.py` (deja la revisión pendiente para la próxima sesión) · `transcript_backup.py` (Y2b) · `memoria_cierre.py` (memoria v1, sin IA: maleta, datos/preferencias a MEMORY.md, compactación) |
| `pre_compact` | el contexto está por compactarse (manual o auto) | observer + **instrucciones al compactador** (puede sugerir qué preservar; no edita el contexto) | hook `PreCompact` | `memory_flush.py` (N2 · corrida N-5: snapshot del transcript crudo al respaldo Y2b + maleta de la pestaña (memoria v1) + rastro JSONL en `~/.claude/workspace/memory-flush/` — todo ANTES de compactar; kill-switch `WORKSPACE_NO_MEMORY_FLUSH=1`) |
| `post_tool_write` | el motor ejecutó un tool de ESCRITURA (Write / Edit / NotebookEdit) | observer **no-bloqueante** (guidance al tool-result; jamás revierte ni bloquea) | hook `PostToolUse` con matcher `Write\|Edit\|NotebookEdit` | **disponible, sin listeners aún** — aquí cuelga N15 (`security_guidance`) |
| `pre_prompt` | el prompt/contexto ensamblado está por mandarse al modelo | **middleware** (único evento que puede MUTAR: reescribir/filtrar el payload antes del modelo — el modo middleware de Hermes) | **pendiente motor #2** (ver honestidad abajo) | — |
| `user_prompt` | el socio mandó un prompt en una sesión interactiva | observer puro (el payload trae el texto; los listeners miran, no mutan — la degradación observer honesta de `UserPromptSubmit`, "otro evento, no `pre_prompt`") | hook `UserPromptSubmit` ⚠ *en este hook, stdout se inyecta al contexto — los listeners NO imprimen nada* | — (disponible; sin listeners) |
| `headless_ingest` | el harness entrega un transcript a un proceso headless | observer (interno) | **interno** — lo emite el propio WORKSPACE, no el motor. Desde 2026-10-16 ningún flujo del cliente lo emite (la revisión de skills y la memoria corren en la sesión visible); queda para herramientas de desarrollo (`skill_audit`) | — · **guard N6**: todo emisor pasa el contenido por `hooks/untrusted.py` (ver abajo) |
| `turn_end` | el agente terminó UNA respuesta (no corre si el socio la interrumpe) | observer **cleanup-only** (la salida se ignora; jamás bloquea el fin del turno) | hook `Stop` ([doc](https://code.claude.com/docs/en/hooks#stop)), cableado **por arranque** en el `--settings` de la pestaña (`events.POR_ARRANQUE`), no en el `settings.local.json` del cerebro · en los envueltos: `None` (su cierre a la mala lo recoge `pending_runs`) | `memoria_turno.py` (solo la maleta, el paso 1 de `memoria.al_cerrar`: sin IA, idempotente, en milisegundos — si Claude Code muere con `kill -9` la maleta ya trae hasta la última respuesta) |
| `model_fallback` | el failover (E-3, `failover.py`; fuera de `main` desde la 0.5) cambió de modelo, se recuperó tras fallos, o agotó la cadena | observer (interno) | **None** — el failover del motor #1 lo hace el VENDOR por dentro (opaco, honestidad) · en `ollama` es `INTERNAL`: lo emitía `failover.py` por transición | — (diagnóstico al rastro N10: `from_model`/`to_model`/`reason`/`strategy`, y campos planos `fallbackStep1..N` al agotarse la cadena) |

## Observer vs middleware (la distinción de Hermes)

- **Observer**: el listener MIRA el payload y actúa por fuera (escribe archivos, lanza procesos,
  loguea). No puede cambiar lo que el motor le va a dar al modelo. Variantes acotadas que algunos
  motores ofrecen sin romper la categoría: *inyección aditiva* (`session_start`: sumar contexto,
  no reescribirlo) e *instrucciones al compactador* (`pre_compact`).
- **Middleware**: el listener puede **MUTAR el payload en tránsito** (reescribir el prompt, filtrar
  contexto, bloquear el turno). En el vocabulario v1 SOLO `pre_prompt` es middleware. Todo lo demás
  es observer **por diseño**: un hook de cierre o de backup que pudiera mutar sería superficie de
  ataque gratis (regla 3 de la serie N: hooks best-effort, jamás en el camino crítico).

## Payload

El payload de cada evento es **el JSON nativo del motor por stdin, passthrough** — no lo
re-empaquetamos (capa fina; re-mapear campos sería un hook-system). Lo que el contrato garantiza
es el MÍNIMO común que un listener puede asumir en cualquier motor:

| Evento | Campos garantizados | En claude-code además llegan |
|---|---|---|
| `session_start` | `session_id`, `cwd` (cerebro), `source` (`startup`/`resume`/`compact`) | `hook_event_name`, … |
| `session_end` | `session_id`, `cwd`, `reason` (`exit`/`logout`/`clear`/…), `transcript_path` | `hook_event_name`, … |
| `pre_compact` | `session_id`, `transcript_path`, `trigger` (`manual`/`auto`) | `custom_instructions` |
| `post_tool_write` | `tool_name`, `tool_input`, `tool_response`, `cwd` | `session_id`, … |
| `pre_prompt` | `prompt`, `session_id`, `cwd` | (pendiente motor #2) |
| `user_prompt` | `prompt`, `session_id`, `cwd` | `hook_event_name`, `transcript_path`, … |
| `turn_end` | `session_id`, `cwd`, `transcript_path` | `last_assistant_message` (la respuesta final: el transcript puede no traerla todavía en ese momento), `stop_hook_active`, … |
| `headless_ingest` | `transcript_path`, `brain` (vía cwd/env del proceso headless) | n/a (interno) |

Un listener portable parsea stdin con tolerancia (basura/vacío → exit 0, contrato probado en
`tests/test_hooks.py`) y solo depende de los campos garantizados.

## Honestidad: qué NO expone claude-code (pendiente motor #2)

- **`pre_prompt` como middleware**: Claude Code tiene `UserPromptSubmit`, pero es
  *inyección aditiva + veto* (puede sumar contexto o bloquear el turno), **no** mutación del
  prompt. El modo middleware completo se cura en el motor #2 (donde WORKSPACE arma el request y
  puede interceptarlo de verdad). Si algún día un listener necesita SOLO inyección/veto, se puede
  degradar honestamente a `UserPromptSubmit` — pero entonces es otro evento (observer), no este.
  **Eso ya pasó**: `user_prompt` ES esa degradación (observer sobre `UserPromptSubmit`, base del
  status en vivo) — `pre_prompt` sigue intacto como middleware pendiente del motor #2.
- **`headless_ingest`**: no es un hook del motor en ningún caso — lo emite el harness. Está en el
  vocabulario para que las herramientas de desarrollo y el dashboard (N10, `events.jsonl`) hablen el mismo
  idioma.

## Guard N6 — `hooks/untrusted.py` (obligación de los emisores de `headless_ingest`)

`untrusted.py` NO es un listener (no lee stdin, no se cablea en settings ni se declara en
`events.LISTENERS`): es una **librería de guard** que el EMISOR de `headless_ingest` aplica al
contenido no confiable (transcripts, markdown del vault compartido) antes de entregarlo a un
proceso headless. Estado actual: **LOG-ONLY** (corrida N-4) — observación, jamás aborta.

- `untrusted.scan_and_log(texto, source, brain)` → findings de inyección/exfil a
  `~/.claude/workspace/untrusted-findings/YYYY-MM-DD.jsonl`. 15 clases de regex ancladas en
  vocabulario de ataque inequívoco (filosofía anti-falsos-positivos de Hermes).
- `untrusted.wrap(texto, label)` → bloque con markers anti-breakout para INLINEAR contenido no
  confiable en un prompt (lo usan `skill_audit` y los workflows).
- `untrusted.guard_clause(label)` → cláusula de endurecimiento cuando el headless LEE él mismo
  los archivos (caso skill_review hoy).

Camino futuro: cuando N15 (`security_guidance`) cuelgue de `post_tool_write`, puede reusar
`untrusted.scan` como librería de patrones; pasar de log-only a cualquier acción requiere
primero el análisis de falsos positivos sobre los logs (decisión humana, otra corrida). La
regla-ley asociada ("contenido no confiable jamás en system role") es territorio BOOT/03 de
los cerebros = consenso N3 — propuesta en el inbox, nunca aplicada por código.

## Cómo cablea un motor (obligaciones del motor #2)

1. Declarar su columna en `events.ENGINE_MAP`: evento WORKSPACE → mecanismo nativo
   (`None` = "no lo expongo", `events.INTERNAL` = "lo emite el harness").
2. Derivar su wiring de `events.LISTENERS` (como hace `install.build_hooks` para claude-code) —
   nunca hardcodear scripts.
3. Pasar el payload nativo por stdin como JSON (los listeners ya toleran variaciones).
4. Lo no mapeado se documenta aquí — no se simula ni se aproxima en silencio.

N2 (`memory_flush`, corrida N-5) fue el **ensayo real** de este flujo para un evento nuevo:
una fila en `events.LISTENERS` bastó para que `install.build_hooks` sembrara el bloque
`PreCompact` y el doctor (fase 5) lo validara — install.py y doctor.py no se tocaron.

### La columna `ollama` (motor #2, corrida E-2)

WORKSPACE posee el loop ⇒ no hay hooks de vendor que cablear: el motor **emite él mismo**
(`events.emit`, al rastro N10) `session_start` / `pre_prompt` / `session_end` — todos
`INTERNAL` en `events.ENGINE_MAP["ollama"]`. `pre_prompt` deja de estar "pendiente motor #2":
el motor arma el request y lo ve pasar (el payload al rastro es metadata — modelo, nº de
mensajes, tokens estimados, pasos de trim — jamás contenido). Desde la corrida E-3 también
`model_fallback` es `INTERNAL`: `failover.py` lo emitía por cada transición de la cadena
(fallback, recuperación, cadena agotada con `fallbackStep*` planos); ese módulo salió de
`main` en la 0.5 (el motor ya había salido antes). Lo aún no mapeado,
honesto: `post_tool_write` = None (sin tools de escritura) y `pre_compact` = None (el trim
C14 por request no es compactar la sesión). Invocar los listeners de `hooks/` por subprocess
derivando de `events.LISTENERS` queda como TODO (documentado en `engines/ollama.py`).

## Rastro unificado de actividad — `events.jsonl` (N10)

Toda la ACTIVIDAD operacional del harness aterriza en **un** stream local:
`~/.claude/workspace/events/YYYY-MM-DD.jsonl` (ejecución → local per-máquina, gitignored,
reconstruible; conocimiento → vault — resolución de "dos logs sin schema común", análisis §1.3.1).

Schema por línea (vocabulario SSE de **Odysseus**, probado — no inventado):

```json
{"ts": "...", "kind": "agent_step", "source": "nightly.py", "agent": "", "brain": "/ruta", "payload": {"event": "headless_ingest", "...": "..."}}
```

- `kind` ∈ `delta / tool_start / tool_output / agent_step / metrics / done` (taxonomía del
  `stream_agent_loop` de Odysseus). Hoy el harness emite `agent_step` (pasos de pipelines:
  audits, propuestas de skills, workflows) — el resto queda reservado para el tee de
  stream-json (activity-strip, dashboard F2+). El mapping evento N9 → kind vive en
  `events.EVENT_KIND` (`post_tool_write` → `tool_output`, lo demás → `agent_step`).
- `payload` es **metadata acotada** (strings recortados a `events._CLIP`) — actividad, jamás
  contenido de transcripts. El evento N9 de origen viaja como `payload["event"]`.
- APIs en `events.py`: `record(kind, …)` (escritor núcleo) · `emit(event, payload, emitter)`
  (fachada N9, firma estable — la llaman skill_audit/nightly) · `read_events(limit, offset)`
  (lector paginado del dashboard; normaliza líneas legacy pre-N10).
- Espejo: `skill_loop.log_event` (su `skills-events.jsonl` sigue siendo el índice FUNCIONAL
  con cursor) duplica cada evento aquí. Un evento = un record, sea directo o espejo.
- Lo consume la sección **Actividad** del dashboard vía `GET /api/events` — read-only y detrás
  del guard Y1 (Host + token: 403 sin token, como toda `/api/*`).

## Cómo agregar un listener (N15, …)

1. Escribir el script en `hooks/<nombre>.py` (patrón `skill_review.py`: best-effort, exit 0
   siempre, kill-switch por env, cross-platform, stdlib).
2. Declararlo en `events.LISTENERS` (evento, timeout, `severity`: `critical` = ✗ del doctor si
   falta · `minor` = ⚠, `requires`: clave del `setup` del agente que lo condiciona, o `None`).
3. Sus tests en `tests/` en la misma corrida (regla 7 de la serie N).
4. `workspace doctor` re-siembra el bloque `hooks` en los cerebros — install y doctor ya derivan
   del contrato, no hay segundo lugar que tocar.

## Arquitectura nueva: los 8 momentos del hook (F0)

El plan de arquitectura nueva conecta el hook a los 9 motores por sus piezas oficiales
(plugin, hooks, MCP, skills). Su contrato son **8 momentos** con nombre neutral, montados
sobre este vocabulario N9: `session_start`, `user_prompt`, `pre_tool`, `post_tool`,
`permission_request` (nuevo: hoy no tiene evento N9), `turn_end`, `compact` (antes y
después; hoy cae en `pre_compact`) y `session_end`.

- **Qué trae y qué devuelve cada uno (JSON):** `arquitectura/momentos.json`.
- **Qué evento oficial de cada motor cae en cada momento:** la ficha de cada motor,
  `arquitectura/fichas/<motor>.json`. Sale de la documentación oficial (investigaciones A, B y C);
  el probador de caja negra (`python3 -m arquitectura.probador`) la confirma o la corrige.
- Esta tabla se genera de las fichas (`python3 -m arquitectura.contrato --tabla`);
  `tests/test_arq_f0.py` falla si se aleja de ellas.

(parcial) = existe con límites · (sin doc) = la documentación no lo dice ·
(por servidor) = llega por el servidor del motor, no por un hook · lo ve herdr = el motor
no lo avisa y se nota porque el panel se cierra.

| Momento | Claude Code | Codex CLI | GitHub Copilot CLI | Cursor CLI | Kiro CLI (V3) | Antigravity CLI | OpenCode | OpenClaw | Hermes Agent |
|---|---|---|---|---|---|---|---|---|---|
| `session_start` (Inicio) | `SessionStart` | `SessionStart` | `sessionStart` | `sessionStart` | `SessionStart` | `SessionStart` | `session.created` (parcial) | `session_start` | `on_session_start` |
| `user_prompt` (Mensaje) | `UserPromptSubmit` | `UserPromptSubmit` | `userPromptSubmitted` (parcial) | `beforeSubmitPrompt` (parcial) | `UserPromptSubmit` | `PreInvocation` | `session.prompt` · `session.context` | `before_prompt_build` | `pre_llm_call` |
| `pre_tool` (Antes de herramienta) | `PreToolUse` | `PreToolUse` (parcial) | `preToolUse` | `preToolUse` · `beforeShellExecution` · `beforeMCPExecution` | `PreToolUse` | `PreToolUse` | `tool.execute.before` | `before_tool_call` | `pre_tool_call` |
| `post_tool` (Después de herramienta) | `PostToolUse` · `PostToolUseFailure` | `PostToolUse` | `postToolUse` · `postToolUseFailure` | `postToolUse` · `afterShellExecution` · `afterMCPExecution` · `afterFileEdit` | `PostToolUse` | `PostToolUse` | `tool.execute.after` | `after_tool_call` | `post_tool_call` |
| `permission_request` (Permiso pedido) | `PermissionRequest` | `PermissionRequest` | `permissionRequest` | `beforeShellExecution` · `beforeMCPExecution` (parcial) | `PermissionRequest` (parcial) | parcial | `permission.evaluate` · `permission.asked` | `exec.approval.requested` (por servidor) | `pre_approval_request` |
| `turn_end` (Fin de turno) | `Stop` | `Stop` | `agentStop` | `stop` · `afterAgentResponse` | `Stop` (sin doc) | `Stop` · `PostInvocation` | `session.execution.succeeded` | `agent_end` | `post_llm_call` |
| `compact` (Compactado) | `PreCompact` · `PostCompact` | `PreCompact` · `PostCompact` | `preCompact` (parcial) | `preCompact` (parcial) | `PreCompact` · `PostCompact` | sin doc | `session.compaction` | `before_compaction` · `after_compaction` | `post_compaction` |
| `session_end` (Cierre) | `SessionEnd` | `SessionEnd` | `sessionEnd` | `sessionEnd` | `SessionEnd` | lo ve herdr | lo ve herdr | `session_end` | `on_session_finalize` |

Mientras dure la migración, el `ENGINE_MAP` de arriba sigue siendo el cableado de hoy; los
momentos no cambian nada hasta F1.

---
*N9 · corrida N-2 (2026-06-10). Spec antes que código (regla 10-bis.5.3). El vocabulario crece
solo cuando un consumidor real lo necesita — no inventar eventos especulativos.*
