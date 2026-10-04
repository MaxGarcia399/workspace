# Contrato INTERACTIVO por motor — `interactive.py` (build A)

La conversación EN VIVO de un agente (turnos + tool-use) corriendo en un motor
NO-Claude, con los comportamientos del harness orquestados por el runner
neutral (`neutral_hooks.py`, build B). Complementa — no reemplaza — los otros
dos contratos:

| Contrato | Módulo | Forma | Para qué |
|---|---|---|---|
| headless one-shot | `headless.py` | texto→texto, sin sesión, sin tools (guard N6) | destilación / bookkeeping |
| ciclo de vida neutral | `neutral_hooks.py` | `run_event(...)` → texto neutral | los comportamientos ricos, sin vendor |
| **interactivo** | `interactive.py` | sesión con estado, N turnos, loop tool-calling | **la conversación viva en otro motor** |

> El default del harness NO cambia: `claude-code` sigue siendo el motor
> primario (N3 del socio). Todo lo de aquí es **opt-in por nombre**.

## 1 · El contrato de turno (por motor)

Un motor interactivo aporta UN callable:

```python
turn_fn(messages, tools_spec, *, model=None, timeout=120) -> (ok, reply | err)
```

- `messages` — historial en **formato chat OpenAI** (`{"role","content",…}`).
  Es el formato canónico del estado de sesión v1; un motor con otro protocolo
  (Anthropic Messages, Gemini nativo) traduce ADENTRO de su `turn_fn`.
- `tools_spec` — herramientas anunciables, shape function-calling de OpenAI.
  `[]` ⇒ el request **jamás** anuncia tools.
- `reply` — `{"content": str, "tool_calls": [{"id","name","arguments": dict}],
  "assistant_message": <mensaje verbatim para reanudar el hilo>}`.
- `err` — string YA redactado (una key jamás llega al log).

Adaptadores:

| Motor | Estado |
|---|---|
| `make_openai_compatible_turn(provider)` | ✅ CONCRETO — cubre locales (Ollama/LM Studio/vLLM) + OpenRouter + OpenAI de una; probado end-to-end contra un stub HTTP OpenAI-compat en loopback (tool-call incluido) |
| `native_api` (Anthropic Messages / Gemini) | A-IMPLEMENTAR (mismo patrón; vive en la rama `feat/native-api`) |
| `official_cli` interactivo | ANDAMIAJE (ver §4) — wrapper de proceso, A-VERIFICAR |

## 2 · `InteractiveSession` — orquestación del ciclo de vida

```python
ses = InteractiveSession(turn_fn, brain=..., tools=reg, behaviors=...)
ses.start()            # on_session_start → contexto/memoria → msg system
ok, out = ses.turn(p)  # on_pre_turn → loop{modelo → [pre_tool→tool→post_tool]*} → on_post_turn
ses.end()              # on_session_end → cleanup + clear del status
doc = ses.transcript() # doc neutral workspace.transcript v1 (neutral_transcript)
```

Mapeo exacto al contrato de `engines/LIFECYCLE.md`:

| Momento | Punto neutral | Traducción del adaptador |
|---|---|---|
| abrir sesión | `on_session_start` | `context` → mensaje `system` `[WORKSPACE · contexto de arranque]` (memoria de sesión, inbox 📨) |
| prompt del socio | `on_pre_turn` | `context` → mensaje `system` ADITIVO (jamás muta el prompt); el behavior `status` re-estampa `now.json` |
| cada herramienta | `on_pre_tool` / `on_post_tool` | solo METADATA (tool_name, ok) — jamás args/resultados (ley N10) |
| fin del turno | `on_post_turn` | no-op documentado v1 |
| cerrar | `on_session_end` | cleanup + clear del status |

`behaviors=None` ⇒ `DEFAULT_BEHAVIORS` de neutral_hooks (motor nuevo = todo:
listeners, memoria, status, inbox). La sesión mantiene en paralelo el doc
NEUTRAL (`neutral_transcript.empty_doc/make_turn/make_tool_call`) — la
traducción motor↔schema vive en el adaptador, los consumidores (memoria v2)
jamás ven el shape del vendor.

## 3 · Seguridad (misma postura que connectors — nada se debilita)

- **Tools**: SOLO las registradas explícitamente en el `ToolRegistry` local de
  la sesión (funciones Python). Un `tool_call` a un nombre no registrado
  devuelve una negativa de texto al modelo — **jamás ejecuta**. Resultado
  recortado (`MAX_TOOL_RESULT_CHARS`), loop acotado (`max_tool_rounds`).
- **Confirmaciones N2/N3 = capa WORKSPACE**: el hook `tool_gate(name, args) ->
  bool` corre ANTES de cada ejecución; `False` (o gate roto — fail-closed) ⇒
  la herramienta no corre. El wiring a los tiers reales es del orquestador,
  no del adaptador.
- **Credenciales**: `connectors.vet_provider` se EJECUTA al construir el
  adaptador (suscripción directa ⇒ `InteractiveSecurityError`, sin bypass);
  keys solo por NOMBRE de env-var resueltas al llamar; `auth_type: none` ⇒
  jamás viaja `Authorization` (locales); `quirks.extra_headers` no puede
  meter `Authorization`/`Cookie` de contrabando; errores redactados.
- **El guard headless queda intacto**: la destilación sigue por `headless.py`
  con `tools="none"` (N6). Este path es OTRO contrato, para sesiones vivas.

## 4 · `official_cli` interactivo — andamiaje (A-VERIFICAR)

`INTERACTIVE_CLIS` + `interactive_cli_status(cli)` (inspección pura) +
`run_official_cli_interactive(cli, …)` (wrapper de proceso):

- `claude-code` — **rechazado a propósito** por el wrapper: su path real es
  dispatch + `engines/claude_code.py` con hooks nativos; un wrapper encima
  haría double-fire de listeners.
- `codex` / `gemini` — el wrapper emite `on_session_start` (el contexto se
  IMPRIME al socio: un TUI ajeno no acepta inyección externa — limitación
  documentada) → corre el binario con la tty → `on_session_end` al salir
  (con lo que el behavior `status` marca/limpia `now.json`). Sesión cruda de
  codex → `parse_codex` post-hoc (connectors).
- ⚠ **A-VERIFICAR contra binarios reales** (la suite jamás los corre): argv
  interactivos de codex/gemini; si aceptan contexto de arranque por flag
  (p.ej. AGENTS.md / system-prompt append); shape real de sus sesiones.

## 5 · TODO (siguiente paso, documentado — no simulado)

- **Wiring MCP real**: hoy las tools son locales de juguete/registro
  explícito. El puente MCP (tools cross-motor, `PORTABILITY["openai_compatible"]["tools_channel"]`)
  llega después, montándose sobre el mismo `ToolRegistry` + `tool_gate`.
- **native_api interactivo** (Anthropic Messages / Gemini): mismo contrato de
  turno, traducción adentro del `turn_fn` (rama `feat/native-api`).
- **Enganche a dispatch** (`engines/<motor>.py` con REPL sobre
  `InteractiveSession`): reconciliar con `engines/ollama.py` de
  `feat/model-agnostic-core` al mergear — un solo loop, no dos.
- **Flip de agentes a otros motores/cuentas**: decisión del socio (N3) — este
  build solo deja la capacidad lista, opt-in por nombre.

Prueba manual (opt-in explícito): `python3 interactive.py --provider ollama
--brain <cerebro>`. Prueba viva de la suite: `tests/test_interactive.py`.
