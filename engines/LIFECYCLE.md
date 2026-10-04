# Ciclo de vida NEUTRAL de hooks — contrato del runner (`neutral_hooks.py`)

Los hooks ricos del harness (memoria de sesión, status en vivo, inbox del bus,
flush pre-compactación…) NO pueden vivir cableados al hook-system de un vendor:
la visión es "lo mejor de todos los mundos" — WORKSPACE dueño de sus
comportamientos con CUALQUIER motor (Claude Code / Codex / Gemini / local).

Este documento define (1) el **inventario** de lo que hoy hace el wiring de
Claude Code, y (2) el **contrato de ciclo de vida neutral** que un adaptador de
motor llama para obtener esos comportamientos sin depender del vendor.

> Vocabulario de eventos (N9): `events.py` / `engines/EVENTS.md`.
> Seam de portabilidad (tools=MCP · hooks=orquestación neutral): `engines/PORTABILITY.md`.
> Implementación: `neutral_hooks.py` (raíz del harness). Adaptador vivo: `workspace_hook.py`
> (Claude Code) — DELEGA en el runner neutral; no duplica lógica.

## 1 · Inventario — qué hace el wiring actual de Claude Code

Cableado real (settings.local.json de cada cerebro, sembrado por
`install.build_hooks` desde `events.LISTENERS`): cada hook nativo invoca
`workspace_hook.py <evento-N9>` y el runner hace fan-out.

| Evento N9 | Hook nativo CC | Comportamiento hoy | Depende de |
|---|---|---|---|
| `session_start` | `SessionStart` | ① marcador de sesión + early-warning de secretos (`hooks/session_start.py`, gate `session_journal`) · ② **memoria de sesión**: dashboard del agente `--context --brain <brain>` (solo `source` startup/fresco) → additionalContext | dispatch (cfg del agente + `scripts.dashboard`), secret_scan, `WORKSPACE_WS`/`ZENITH_WS` |
| `session_end` | `SessionEnd` | journal/breadcrumb (`session_end.py`, gate `session_journal`) · skill review headless (`skill_review.py`) · backup de transcript (`transcript_backup.py`) | headless.py (destilación SIN tools — guard N6), markers en `~/.claude/workspace/` |
| `pre_compact` | `PreCompact` | flush de memoria ANTES de compactar (`memory_flush.py`; kill-switch `WORKSPACE_NO_MEMORY_FLUSH`) | transcript_path del payload, respaldo Y2b |
| `post_tool_write` | `PostToolUse` (matcher `Write\|Edit\|NotebookEdit`) | guidance de seguridad no-bloqueante (`security_guidance.py`) → additionalContext | tool_input del payload |
| `pre_tool` / `post_tool` | `PreToolUse`/`PostToolUse` (matcher `*`) | telemetría en vivo (`telemetry.py` — solo metadata, jamás tool_input/response) | rastro N10 (`events.record`) |
| `user_prompt` | `UserPromptSubmit` | — sin listeners en main. En la rama preservada `feat/agent-status`: re-estampar la tarea viva en `<brain>/STATE/now.json` (**status en vivo**) | status/now.json (extraído de main el 2026-06-26, commit 02eabc3) |
| `pre_prompt` | **no existe en CC** (UserPromptSubmit es aditivo+veto, no middleware) | — | motor #2 (loop propio) |

Comportamientos del ecosistema que HOY van por regla manual o rama aparte:

- **Status en vivo (now.json)** — preservado completo en `feat/agent-status`
  (status.py + hooks/status_update.py + UI). Extraído de main.
- **Inbox-on-boot del bus** — en `feat/inbox-on-boot` (session_start.py inyecta
  los `msgs/` pendientes); en main aún es regla manual en el CLAUDE.md del agente.

## 2 · Contrato de ciclo de vida neutral

Un adaptador de motor (build A) llama estos puntos; el runner neutral ejecuta
los comportamientos y devuelve **texto plano** (`context`) — el adaptador lo
traduce al shape de SU motor (additionalContext en CC, system-msg en un loop
propio, etc.). El runner JAMÁS habla el JSON de un vendor hacia afuera.

### Puntos de enganche (v1)

| Punto | Evento N9 | Cuándo lo llama el adaptador | Devuelve |
|---|---|---|---|
| `on_session_start(payload)` | `session_start` | al abrir sesión (startup/resume/compact — `payload["source"]`) | `context` a inyectar |
| `on_pre_turn(payload)` | `user_prompt` | el socio mandó un prompt, ANTES del turno | `context` (aditivo; la mutación middleware queda para motores dueños del loop) |
| `on_post_turn(payload)` | — (reservado) | al terminar un turno | no-op documentado (sin evento N9 v1; se activa cuando un consumidor lo pida) |
| `on_pre_compact(payload)` | `pre_compact` | el contexto está por compactarse | `context` siempre `""` (cleanup) |
| `on_session_end(payload)` | `session_end` | al cerrar sesión | `""` (cleanup) |
| `on_pre_tool(payload)` / `on_post_tool(payload)` | `pre_tool`/`post_tool` | alrededor de CADA tool (solo metadata) | `""` |
| `on_post_tool_write(payload)` | `post_tool_write` | tras un tool de ESCRITURA | `context` (guidance) |
| `on_status(brain, task, agent=None, state=...)` | — (API directa) | el orquestador/loop quiere publicar la tarea viva | `True/False` |

Todos son wrappers finos de `run_event(event, payload, *, brain=None,
behaviors=None, raw=None)` → `{"context": str, "ran": [behaviors]}`.

### Reglas del contrato

1. **Payload**: dict con el JSON nativo del motor (passthrough — mínimos
   garantizados en `engines/EVENTS.md §Payload`). El runner solo asume
   `cwd`/`source`/`prompt`/`session_id`; basura o `None` → resultado vacío.
2. **Brain**: `payload["cwd"]` > `$CLAUDE_PROJECT_DIR` > `$WORKSPACE_BRAIN` > cwd
   del proceso (misma precedencia P0-1 de siempre).
3. **Fail-open ABSOLUTO**: ningún punto levanta jamás; peor caso
   `{"context": "", "ran": []}`. Los hooks nunca están en el camino crítico.
4. **Behaviors opt-in**: `behaviors` selecciona qué corre. Sets publicados:
   - `DEFAULT_BEHAVIORS` = `("listeners", "memory_context", "status",
     "inbox_on_boot")` — lo que un motor nuevo quiere.
   - `CLAUDE_CODE_PARITY` = `("listeners", "memory_context")` — EXACTAMENTE lo
     que Claude Code hace hoy en main; `workspace_hook.py` pasa este set
     (paridad: encender status/inbox para CC es una decisión aparte — viven en
     `feat/agent-status` / `feat/inbox-on-boot`).
5. **Los listeners de `hooks/` no cambian**: el runner neutral les hace el
   mismo fan-out subprocess (gate `requires`, timeout, falla-suave por hijo) y
   parsea su salida (shape `hookSpecificOutput` u legacy `{"type":"text"}`) a
   texto neutral. Siguen amputables borrando el archivo.
6. **Kill-switches respetados**: `WORKSPACE_NO_STATUS`, `WORKSPACE_NO_MSGS`,
   `WORKSPACE_NO_MEMORY_FLUSH` (en el listener), etc.
7. **Seguridad**: nada del runner anuncia tools ni toca credenciales; la
   destilación headless conserva el guard N6 (va por `skill_review.py`).

### Comportamientos levantados a la capa neutral (1ª pasada)

| Behavior | Qué hace | Estado |
|---|---|---|
| `listeners` | fan-out de `events.LISTENERS` (subprocess, gate, merge aditivo) | ✅ levantado (movido desde workspace_hook) |
| `memory_context` | memoria de sesión: dashboard del agente `--context` en session_start fresco | ✅ levantado |
| `status` | status en vivo `<brain>/STATE/now.json` (session_start "en sesión" sin pisar tarea vigente · user_prompt re-estampa · end/compact limpian; schema compatible con `feat/agent-status`) | ✅ levantado (neutral); para CC sigue OFF hasta mergear la rama de UI |
| `inbox_on_boot` | msgs/ pendientes del bus → aviso 📨 en el arranque | ✅ levantado (neutral); para CC sigue OFF (rama `feat/inbox-on-boot`) |

### TODO (siguientes pasadas) — dónde engancha cada uno

- **memory_flush nativo** — hoy corre como listener subprocess en
  `pre_compact`; levantarlo a función del runner cuando otro motor tenga
  transcript compactable (enganche: `on_pre_compact`).
- **skill_review / transcript_backup / journal** — ídem, listeners subprocess
  en `session_end`; portables ya vía `behaviors=("listeners",)` en cualquier
  motor cuyo adaptador llame `on_session_end` con `transcript_path` en el
  payload (el ingester neutral ya normaliza formatos — `neutral_transcript.py`).
- **security_guidance / telemetry** — listeners subprocess; funcionan en
  cualquier motor que llame `on_post_tool_write` / `on_pre_tool`+`on_post_tool`.
- **pre_prompt middleware real** — solo motores dueños del loop (ollama/E-2);
  el loop llama `run_event("pre_prompt", …)` y ahí SÍ puede mutar (v2).
- **presencia de socios** (`STATE/presence/`) — vive en `feat/agent-status`;
  al mergear, engancha en `on_pre_turn`/`on_session_start` dentro del behavior
  `status`.
