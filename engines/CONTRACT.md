# Motores enchufables de WORKSPACE — contrato

Un **motor** (engine) es el adapter que arranca un agente con un runtime de modelo concreto.
WORKSPACE es vendor-neutral: el motor es la capa **enchufable**. Hoy hay tres: `claude-code`
(real, premium), `stub` (eco sin LLM — prueba viva del switching, corrida E-1) y `ollama`
(loop OpenAI-compat propio — el primer motor donde WORKSPACE arma el request, corrida E-2);
mañana `openrouter`, `codex`, etc. **sin reescribir el dispatcher.**

> Vocabulario completo (engine vs provider vs model) y plan del ciclo: `research/motor2-plan.md`.
> Desde la corrida E-1 la capa declarativa de providers está **implementada**
> (`providers/*.json` + `model_resolver.py`), igual que el context-budget C14 (`context_budget.py`).
> La capa de CONEXIÓN de cuentas (API key · OpenRouter+BYOK · endpoint OpenAI-compat incl.
> locales · CLI oficial con login del socio) vive en `connectors.py` (invariante de suscripción
> incluido); portabilidad de hooks/tools entre motores: `engines/PORTABILITY.md`.

## Cómo se enchufa un motor (cero edición del dispatcher)

1. Crea `engines/<nombre>.py` (copia `engines/_template.py`).
2. Implementa `launch()` (y opcionalmente `pick()` / `META`).
3. En el `agent.json` de un agente declara `"engine": "<nombre>"`.

El dispatcher hace **carga dinámica por nombre**: `"engine": "ollama"` → importa `engines/ollama.py`.
La conversión es `guion → guion_bajo` (`"claude-code"` → `engines/claude_code.py`). `dispatch.py` no
se toca nunca para agregar motores. Los archivos que empiezan con `_` (como `_template.py`) NO cuentan
como motores instalados.

## Cómo se CAMBIA de motor (selection-source policy, OpenClaw)

Precedencia, de más explícita a menos:

```bash
python3 dispatch.py zenith --engine stub    # 1. flag CLI    (source: cli — ESTRICTO)
WORKSPACE_ENGINE=stub zenith                  # 2. env var     (source: env — ESTRICTO)
# 3. "engine": "stub" en agent.json         #    (source: agent — default)
```

La elección **explícita** del socio (cli/env) es **estricta**: `model_resolver` vacía la cadena
de fallbacks — jamás contestarle desde un motor/modelo que no pidió. La elección default
(agent.json) permite la cadena `fallback_models` del provider. El motor recibe en `cfg`:
`cfg["engine"]` (el motor REAL de la corrida) y `cfg["_engine_source"]` (`cli`/`env`/`agent`).

## El contrato (lo que debe exponer un motor)

| Símbolo | Obligatorio | Qué hace |
|---|---|---|
| `launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True)` | **sí** | Arranca el agente. Normalmente hace `exec`/`sys.exit`. Si `plan=True`, NO lanza: imprime el wiring + chequeos y vuelve. |
| `pick(cfg) -> str` | no | Elección de sesión sin lanzar (flujos especiales). Omitir o `""` si no aplica. |
| `META = {...}` | no | Metadatos: `name`, `needs` (binarios), `auth` (none/oauth/api-key/subscription/local). |
| `CAPABILITIES = {...}` | no | Matriz de capacidades del harness (ver abajo). Omitida ⇒ defaults conservadores. |
| `status() -> dict` | no | Estado honesto (`{"ready": bool, …}`) para doctor / `harnesses.describe(probe=True)`. Inspección barata, jamás lanza al agente. |
| `run_turn(prompt, …) -> (ok, texto)` | no | UN turno headless real (lo reusan headless/eval/smokes). |
| `inject_context(cfg) -> dict` | no | Materializa la IDENTIDAD del agente (cerebro) en el formato que SU harness entiende, SIN duplicarla — el cerebro es la única fuente de verdad. claude-code: nativo (lee `CLAUDE.md` solo; no necesita la función). codex: genera `AGENTS.md` **puntero** marcado `WORKSPACE:GENERATED` en la raíz del cerebro, re-sincronizado en cada launch (un AGENTS.md propio del socio jamás se toca). Doc de identidad: `identity_doc` del agent.json (default `CLAUDE.md`). Falla-suave: `{'ok','action','path','detail'}`. |

## Harness-OS: registry + matriz de capacidades + binding (hub)

Un **harness** (visión harness-os, `research/design/harness-os/PLAN.md`) ES un
motor de `engines/` — no hay capa paralela. `harnesses.py` es la vista de
REGISTRO sobre los engines:

- `harnesses.registry(probe=)` — descriptores de todos los instalados
  (META + CAPABILITIES + binarios en PATH; `probe=True` consulta `status()`).
- `harnesses.selectable()` — los elegibles en el selector del hub
  (instalados + binarios presentes; el login se valida al lanzar).
- `harnesses.binding(agente, default)` / `set_binding` / `cycle` — el binding
  agente→harness PER-MÁQUINA (settings `agentes.<n>.engine`, tier A con
  gate+changelog de config_engine). dispatch ya lo honra al lanzar; cambiar el
  default de EQUIPO sigue siendo editar el agent.json (N3).

`CAPABILITIES` — claves estándar (datos, no ifs; honestas y conservadoras):

| clave | valores | qué dice |
|---|---|---|
| `launch` | `native` / `wrapper` / `repl` | path propio · TUI oficial envuelto en el ciclo neutral · loop propio |
| `inject_context` | `hooks` / `project-doc` / `print` / `none` | inyección vía hook-system · doc de proyecto PUNTERO (p.ej. AGENTS.md→CLAUDE.md) · imprimir al socio · nada |
| `mcp` | `native` / `True` / `False` | ¿soporta MCP servers? |
| `hooks` | `native` / `False` | ¿hook-system? |
| `sessions` | `workspace` / `vendor` / `none` | quién gestiona sesiones |
| `status_live` | bool | ¿publica tarea-en-vivo (now.json/statusline de WORKSPACE)? |
| `statusline` | `workspace` / `native-config` / `False` | info de abajo: scripts de brand de WORKSPACE · barra NATIVA del CLI configurada por el adapter (codex: `-c tui.status_line=[…]` por corrida — contexto %, límite 5h, semanal, modelo, permisos; datos reales del vendor, jamás fabricados) · nada |
| `headless` | bool | ¿tiene `run_turn` one-shot? |

**En el hub**: la caja AGENTES muestra el binding del agente seleccionado
(`motor ▸ claude-code ▾`); la tecla `m` lo cicla entre los harnesses elegibles
y lo PERSISTE al instante (per-máquina). El siguiente Enter lanza con ese
harness — binding automático, cero pasos extra.

`cfg` ya viene resuelto por el dispatcher: `name`, `display`, `engine`, `_brain` (ruta del vault),
`_scripts` (con `{brain}` expandido), `_dir`, y `engine_config` (opcional, ver abajo).

## Config declarativa del motor (shape — robo #4 de Hermes)

Adoptamos **ahora** la forma del config para no repensarla después. Dos niveles:

### En `agent.json` — qué motor y con qué parámetros

```jsonc
{
  "engine": "claude-code",
  "engine_config": {                 // opcional; lo lee el motor
    "model": "claude-opus-4-8",      // modelo principal
    "provider": "anthropic",         // referencia a providers/<provider>.json (futuro)
    "aux_models": {                  // "modelo variable por tarea" (futuro)
      "bulk": "haiku",
      "vision": "claude-sonnet-4-6"
    }
  }
}
```

`claude-code` hoy ignora `engine_config` (usa la suscripción tal cual); el campo queda listo para
motores que sí enrutan modelos.

### En `providers/<name>.json` — declarar un provider UNA vez (✅ IMPLEMENTADO, corrida E-1)

Shape estilo `ProviderProfile` de Hermes — quirks como DATOS, jamás ifs en `engines/`.
Los carga y valida `model_resolver.py`; perfiles vivos en `providers/` (anthropic · ollama · stub):

```jsonc
{
  "name": "ollama",
  "api_mode": "openai-chat",          // eje API: anthropic | openai-chat | echo | …
  "base_url": "http://localhost:11434/v1",   // eje ubicación: localhost = local, https = nube
  "auth_type": "none",                // eje auth: api_key | oauth | subscription | none
  "cost": "free",                     // eje costo (informativo): subscription | metered | free
  "env_vars": [],                     // p.ej. ["OPENROUTER_API_KEY"] — NUNCA el valor, solo el nombre
  "models": ["llama3.1", "qwen2.5"],
  "default_model": "llama3.1",
  "default_aux_model": "qwen2.5",
  "task_models": { "utility": "qwen2.5" },   // resolver por tarea (research/task/utility/default)
  "fallback_models": ["qwen2.5"],     // se prueban en orden ante error/rate-limit (no si la selección fue estricta)
  "hidden_models": [],                // el resolver JAMÁS los elige (deshabilitados por el admin)
  "context_windows": { "llama3.1": 32768 },  // alimenta context_budget (C14)
  "quirks": { "compression_thresholds": {} } // cicatrices por modelo = CAMPOS, no ifs
}
```

> 🔴 Regla de oro (**ejecutada por el loader**, no solo escrita): los `providers/*.json` declaran
> **nombres** de variables de entorno, jamás el valor de la credencial. `model_resolver.load_provider`
> valida el shape Y pasa el archivo crudo por `secret_scan` — un provider con un secreto hardcodeado
> **no carga**. Las keys viven per-máquina en `~/.claude/workspace/`, gitignored. Ver ARCHITECTURE.md.

### Resolución por tarea (`model_resolver.resolve(cfg, task=…)`)

- `default` → `engine_config.model` → `provider.default_model` → primer modelo CHAT
  (excluye embeddings/tts/whisper — cicatriz `_first_chat_model` de Odysseus).
- `research`/`task` → `aux_models[t]` → `task_models[t]` → **caen a `utility`**, jamás al
  default global (las tareas de fondo no terminan en el modelo caro).
- `utility` → … → `default_aux_model` → último recurso `default_model` (marcado `degraded`).
- `hidden_models` nunca se eligen; selección estricta (cli/env) ⇒ `fallbacks: []`.

### Context budget (C14) — `context_budget.py`

Para el motor real (E-2): budget adaptativo (`ventana × 0.85`, cap 200k, piso 6k si la ventana
es desconocida), régimen small-context (≤8,192), threshold de compresión POR modelo (quirk del
provider) y escalera de degradación de 4 pasos (`trim_for_context`; `_protected` jamás cae;
toda truncación deja marca visible). `claude-code` NO lo usa — el vendor compacta solo.

## Honestidad: qué provee cada motor

| Capacidad | `claude-code` (motor #1) | motor #2 (stub hoy / ollama E-2) |
|---|---|---|
| modelo activo, failover, compaction | lo hace el VENDOR por dentro; WORKSPACE no lo ve | lo resuelve WORKSPACE (resolver + budget + FAILOVER_REASONS) |
| providers/*.json + engine_config | los IGNORA (suscripción tal cual) | los consume |
| `pre_prompt` middleware (N9) | no expuesto por el vendor | posible: WORKSPACE arma el request |

## El motor real #2: `engines/ollama.py` (✅ corrida E-2)

La promesa de E-1, cumplida sin tocar `dispatch.py`:

1. `engines/ollama.py` implementa el loop **OpenAI-compat** (`POST {base_url}/chat/completions`;
   el `base_url` del provider ya trae el `/v1`) — NO el `/api/chat` nativo de Ollama: con el
   estándar OpenAI el mismo motor sirve a N providers (ollama, openrouter, vLLM…) cambiando JSON.
2. Consume TODO lo de E-1: `model_resolver.resolve()` (provider+modelo por tarea, selección
   estricta), `context_budget.trim_for_context()` EN VIVO antes de cada request (escalera C14
   con marcas visibles), `FAILOVER_REASONS` para clasificar errores (red/HTTP/parseo), y emite
   los eventos N9 (`session_start` / `pre_prompt` / `session_end` / `model_fallback`) **desde
   su propio loop** (`events.emit`) — `pre_prompt` es por fin el punto middleware real.
3. `base_url`: env `WORKSPACE_OLLAMA_BASE_URL` > `engine_config.base_url` > `provider.base_url`
   (así los tests lo verifican contra un mock HTTP local — sin Ollama instalado).
4. Selección, igual que siempre: `dispatch.py <agente> --engine ollama` · `WORKSPACE_ENGINE=ollama` ·
   `"engine": "ollama"` en agent.json.

Alcance E-2 (chico a propósito): chat one-shot + REPL + `/leer <ruta>` (comando local).
**TODO E-4+** (honesto, no simulado): suscripciones (device-flow + refresh at-call-time),
streaming, tool-calling del LLM, listeners de `hooks/` por subprocess, dieta de boot.
Detalle en el docstring del motor.

## Failover completo (✅ corrida E-3) — `failover.py`

El consumo REAL de `FAILOVER_REASONS`, reusable por cualquier motor genérico (el motor solo
provee `attempt(model) -> (resultado, razón)` a `failover.run_with_failover`):

- **Cadena de fallback**: primario + `provider.fallback_models` (sin hidden — los quitó el
  resolver), reintentos acotados por estrategia (`model_resolver.FAILOVER_STRATEGIES`, datos)
  y cota dura `MAX_ATTEMPTS`. Estrategias que NO caen a otro modelo: red caída, credencial
  rota (mismo 401 con la misma key — refresh real en E-4), abort.
- **Selection-source policy**: elección explícita del socio (cli/env) = ESTRICTA — cadena de
  UN modelo, sin filtro por cooldown; jamás contestarle desde un fallback que no pidió.
- **Cooldowns con backoff**: model-scoped con host EXACTO en la llave (`failover.scope`,
  urlsplit — jamás substring), escaleras por clase con **billing ≠ rate-limit**
  (1m/5m/25m vs 1h/6h/24h, OpenClaw), persistidos per-máquina en
  `~/.claude/workspace/failover/` (gitignored) — sobreviven entre invocaciones. Falla-suave.
- **Persist-override ANTES del retry + rollback estrecho** (la race de OpenClaw): la decisión
  de fallback se escribe a disco antes de reintentar (un crash no la pierde; la próxima
  invocación la antepone vía `active_override`, con TTL) y al terminar se borra SOLO la
  entrada propia (token-compare — un cambio en vivo del socio no se pisa).
- **`FallbackSummaryError`** al agotarse la cadena: detalle por intento (modelo · razón →
  estrategia) + eventos N9 `model_fallback` con campos planos `fallbackStep1..N` al rastro N10.

`claude-code` NO pasa por aquí: su failover lo hace el vendor (opaco — `model_fallback: None`
en su columna de `events.ENGINE_MAP`, honestidad N9).
