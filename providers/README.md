# providers/ — perfiles declarativos de providers (motor #2, corrida E-1)

Un **provider** declara DÓNDE y CÓMO se habla con modelos: api_mode, base_url, auth,
modelos, fallbacks y quirks. Es **datos, jamás código** (patrón `ProviderProfile` de
Hermes: *"declares everything in one place"*; los quirks se acumulan como campos del
JSON, nunca como `if` en `engines/`). Shape canónico y ejemplos: `engines/CONTRACT.md`.

Los carga y valida `model_resolver.py` (raíz). Un provider inválido NO carga.

## 🔴 Regla de oro (ejecutada por el loader, no solo escrita)

Estos archivos declaran **NOMBRES** de variables de entorno (`"env_vars":
["OPENROUTER_API_KEY"]`) — **JAMÁS el valor de una credencial**. El loader valida que
cada entrada parezca nombre de env-var y pasa el archivo crudo por `secret_scan`:
cualquier secreto detectado ⇒ el provider se rechaza con error explícito. Las keys
viven per-máquina (env del socio / `~/.claude/workspace/`, gitignored).

## Los 4 ejes de cambio de motor viven aquí

| Eje | Campo | Valores |
|---|---|---|
| auth | `auth_type` | `api_key` · `oauth` · `subscription` · `none` |
| API | `api_mode` | `anthropic` · `openai-chat` · `echo` · `cli` · … |
| ubicación | `base_url` | localhost = local · https = nube |
| costo | `cost` (informativo) | `subscription` · `metered` · `free` |

## Modelo de conexión (capa `connectors.py`)

Además de los 4 ejes, un perfil declara (u obtiene por derivación) su **tipo de
conexión** — el modelo aprobado a/b/c/d:

| `connection` | Qué es | Cómo se conecta |
|---|---|---|
| `openai_compatible` | (a) API key directa · (b) OpenRouter+BYOK · (c) endpoint OpenAI-compat, incl. **modelos locales** (Ollama/LM Studio/vLLM) | `connectors.py` lo registra como backend headless CONCRETO (`WORKSPACE_DREAM_BACKEND=<name>`) |
| `native_api` | Anthropic Messages / Gemini API con api_key | A-IMPLEMENTAR (el registro lo salta con razón visible) |
| `official_cli` | (d) CLI oficial con el **login del socio** (Claude Code / Codex / Gemini CLI) | se LANZA el binario oficial (`cli:` apunta a `connectors.OFFICIAL_CLIS`); WORKSPACE jamás ve el token |

🔴 **INVARIANTE (ejecutado por `connectors.vet_provider`):** `auth_type`
`subscription`/`oauth` (credencial de consumidor) **solo** puede ser
`official_cli`. Un perfil de suscripción con conexión directa NO se registra —
extraer/reusar esos tokens en clientes no oficiales está prohibido por los
vendors (Anthropic explícito; Google banea cuentas). Y: `api_key` sin TLS solo
a loopback; `auth_type none` ⇒ jamás viaja `Authorization`.

Portabilidad de hooks/tools por tipo: `engines/PORTABILITY.md`.

## Perfiles actuales

- `anthropic.json` — motor #1 (claude-code, suscripción → `official_cli`). El vendor
  gestiona modelos y failover; el perfil es el registro declarativo.
- `codex.json` — Codex CLI oficial con el login del socio (`official_cli`, ⚠ backend
  headless A-VERIFICAR; sesiones → `neutral_transcript.parse_codex`).
- `ollama.json` — modelo LOCAL vía Ollama (OpenAI-compat, `auth none`). Conector vivo:
  `WORKSPACE_DREAM_BACKEND=ollama WORKSPACE_DREAM_MODEL=llama3.1`.
- `lmstudio.json` — modelo LOCAL vía LM Studio (OpenAI-compat; vLLM = mismo patrón).
- `openrouter.json` — agregador BYOK (las keys de proveedores subyacentes viven EN
  OpenRouter, server-side; aquí solo el NOMBRE `OPENROUTER_API_KEY`).
- `openai.json` — API metered de OpenAI (`OPENAI_API_KEY` del env; la suscripción
  ChatGPT NO va por aquí — eso es `codex.json`).
- `stub.json` — provider del motor `stub` (eco sin LLM): prueba viva del resolver y
  del switch end-to-end.
