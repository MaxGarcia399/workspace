#!/usr/bin/env python3
"""WORKSPACE · connectors — capa de CONEXIÓN de cuentas/motores (modelo aprobado).

El modelo de conexión (spec aprobada por el dueño del harness — INVARIANTE,
no preferencia):

  (a) API key por proveedor            → connection: openai_compatible / native_api
  (b) OpenRouter + BYOK                → openai_compatible (las keys de los
      proveedores subyacentes viven EN OpenRouter, server-side; WORKSPACE solo
      ve OPENROUTER_API_KEY desde el env per-máquina)
  (c) endpoint OpenAI-compatible       → openai_compatible — cubre OpenAI,
      OpenRouter y MODELOS LOCALES (Ollama / LM Studio / vLLM) de una vez
  (d) CLI oficial con el login del socio → official_cli (Claude Code / Codex
      CLI / Gemini CLI)

🔴 INVARIANTE DE SEGURIDAD DURO (ejecutado por vet_provider, no solo escrito):
  una credencial de SUSCRIPCIÓN de consumidor (auth_type subscription/oauth)
  JAMÁS se extrae ni se reusa en un cliente no oficial (Anthropic lo prohíbe
  explícito; Google banea cuentas). La suscripción SOLO se usa lanzando el
  CLI OFICIAL (connection: official_cli). Solo API keys / endpoints se
  conectan directo. Un provider que declare suscripción con conexión directa
  NO se registra — se rechaza con el porqué.

Más leyes de esta capa:
  · Secretos: providers/*.json declaran NOMBRES de env-vars (regla de oro de
    model_resolver + secret_scan); el valor se lee del env AL LLAMAR y jamás
    se loguea (los mensajes de error pasan por _redact).
  · Endpoints locales: auth_type "none" ⇒ JAMÁS se manda Authorization (una
    key del socio no viaja a un endpoint que no la pidió).
  · api_key sobre http:// plano solo a loopback — a un host remoto sin TLS
    NO se manda una key (vet_provider lo rechaza).
  · Los conectores directos (openai_compatible y native_api) NO tienen canal
    de tools por construcción (el request jamás anuncia "tools") ⇒ cumplen
    tools="none" del contrato headless trivialmente — aptos para destilación
    (guard N6).

CÓMO SE ENCHUFA (cero flip de default — claude-code sigue siendo el primario;
todo esto es opt-in por nombre de backend):

  providers/<name>.json  →  register_provider_backends()  →  backend headless
  `<name>` disponible para run_headless / WORKSPACE_DREAM_BACKEND /
  WORKSPACE_EVAL_BACKEND. headless.get_backend hace la registración LAZY al
  primer miss, así que `WORKSPACE_DREAM_BACKEND=ollama workspace dream` funciona
  sin tocar código. Un backend ya registrado (builtin) JAMÁS se pisa.

Ejemplo (modelo local, cero nube):
  ollama pull llama3.1   # una vez, en la máquina del socio
  WORKSPACE_DREAM_BACKEND=ollama WORKSPACE_DREAM_MODEL=llama3.1 \
      python3 dream.py <cerebro>

Portabilidad de hooks/tools por tipo de conexión: `PORTABILITY` (datos) +
`engines/PORTABILITY.md` (doc). Tools cross-motor = MCP; hooks que un motor
no tenga = capa de orquestación neutral de WORKSPACE (events.py N9).

Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Amputable (C10):
borra este archivo y headless queda EXACTO como antes (builtins intactos).
"""
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request

import headless
import model_resolver

try:
    import neutral_transcript
except ImportError:            # amputable — el status lo reporta honesto
    neutral_transcript = None

# ── vocabulario cerrado de tipos de conexión ────────────────────────────────
CONNECTION_TYPES = ("openai_compatible", "native_api", "official_cli")

#: auth de CONSUMIDOR: solo puede conectarse lanzando el CLI oficial (d).
_CONSUMER_AUTH = ("subscription", "oauth")

#: api_mode → tipo de conexión (derivación cuando el provider no lo declara)
_API_MODE_MAP = {
    "openai-chat": "openai_compatible",
    "openai": "openai_compatible",
    "anthropic": "native_api",
    "gemini": "native_api",
    "google": "native_api",
}

#: hosts loopback: únicos destinos válidos de una api_key sobre http:// plano
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


class ConnectorError(RuntimeError):
    """Error de configuración de la capa de conexión (no transitorio)."""


class ConnectorSecurityError(ConnectorError):
    """INVARIANTE violado (suscripción conectada directo, key sin TLS, …)."""


# ── clasificación + vet de seguridad ────────────────────────────────────────
def connection_type(provider):
    """Tipo de conexión de un provider. Explícito (`"connection": …`) gana;
    si no, se deriva: auth de consumidor ⇒ official_cli (el invariante ni
    siquiera deja derivar otra cosa); si no, por api_mode. "" = desconocido
    (no se conecta — jamás se adivina)."""
    p = provider or {}
    explicit = p.get("connection", "")
    if explicit:
        return explicit if explicit in CONNECTION_TYPES else ""
    if p.get("auth_type") in _CONSUMER_AUTH:
        return "official_cli"
    return _API_MODE_MAP.get(p.get("api_mode", ""), "")


def _host(base_url):
    try:
        return (urllib.parse.urlsplit(base_url).hostname or "").lower()
    except ValueError:
        return ""


def vet_provider(provider):
    """Vet de SEGURIDAD de la conexión (encima del shape/secret_scan que ya
    ejecuta model_resolver.load_provider). Devuelve lista de errores
    ([] = conectable). Reglas:
      1. INVARIANTE: auth de consumidor (subscription/oauth) ⇒ SOLO
         official_cli. Directo = rechazado, sin bypass.
      2. `connection` explícito debe estar en el vocabulario.
      3. Conexión directa exige base_url http(s).
      4. api_key sin TLS solo a loopback (una key no viaja en claro a un
         host remoto).
      5. auth_type api_key exige env_vars declarados (el NOMBRE de la key).
    """
    p = provider or {}
    errors = []
    explicit = p.get("connection", "")
    if explicit and explicit not in CONNECTION_TYPES:
        errors.append("connection '%s' fuera del vocabulario (%s)"
                      % (explicit, "/".join(CONNECTION_TYPES)))
    ct = connection_type(p)
    auth = p.get("auth_type", "")
    if auth in _CONSUMER_AUTH and ct != "official_cli":
        errors.append(
            "INVARIANTE DE CONEXIÓN violado: auth_type '%s' es credencial "
            "de SUSCRIPCIÓN de consumidor — jamás se extrae/reusa su token "
            "en un cliente directo (Anthropic lo prohíbe; Google banea "
            "cuentas). Solo connection: official_cli (lanzar el CLI oficial "
            "con el login del socio)." % auth)
    if ct in ("openai_compatible", "native_api"):
        burl = p.get("base_url", "") or ""
        if not burl.startswith(("http://", "https://")):
            errors.append("conexión directa sin base_url http(s) válido: %r"
                          % burl)
        elif (auth == "api_key" and burl.startswith("http://")
                and _host(burl) not in _LOOPBACK_HOSTS):
            errors.append(
                "api_key sobre http:// plano a host remoto (%s) — la key "
                "viajaría en claro. Usa https:// o un endpoint loopback."
                % (_host(burl) or "?"))
        if auth == "api_key" and not p.get("env_vars"):
            errors.append("auth_type api_key sin env_vars: declara el "
                          "NOMBRE de la env-var de la key (jamás el valor)")
    return errors


# ── credenciales (env per-máquina; jamás al repo, jamás al log) ─────────────
def _resolve_key(provider):
    """(key, err). Primera env-var declarada que esté seteada. El VALOR no
    sale de aquí más que hacia el header Authorization."""
    names = (provider or {}).get("env_vars") or []
    for n in names:
        v = os.environ.get(n, "")
        if v:
            return v, ""
    return "", ("falta credencial: exporta %s (per-máquina, jamás al repo)"
                % (" o ".join(names) or "una env-var declarada"))


def _redact(msg, key):
    """Un secreto jamás llega a logs/errores aunque el server lo eque.
    Regla de uso: SIEMPRE redactar ANTES de truncar — si el corte cae a
    media key, el prefijo parcial ya no matchea y se fugaría al log."""
    if key and key in msg:
        msg = msg.replace(key, "•••")
    return msg


# Headers que un quirk (`quirks.extra_headers`) JAMÁS mete de contrabando:
# las credenciales viajan SOLO por el canal auth del provider (auth_type +
# env_vars). ÚNICA definición del filtro — la comparten el path headless
# (aquí) y el interactivo (interactive.py).
FORBIDDEN_HEADERS = ("authorization", "proxy-authorization", "cookie")


# ── adaptador CONCRETO: openai_compatible ───────────────────────────────────
def make_openai_compatible(provider):
    """Backend headless para un provider OpenAI-compatible (OpenAI,
    OpenRouter, DeepSeek, xAI, Mistral y LOCALES: Ollama/LM Studio/vLLM).

    POST {base_url}/chat/completions, stdlib puro. El request JAMÁS anuncia
    tools ⇒ el modelo no tiene manos por construcción (can_disable_tools=True
    honesto). `exe_override` (knob de CLIs) no aplica y se ignora."""
    p = dict(provider or {})
    name = p.get("name", "?")
    url = (p.get("base_url") or "").rstrip("/") + "/chat/completions"

    def invoke(prompt, *, model, timeout, cwd, tools, exe_override):
        # preflight COMPARTIDO con los adaptadores nativos (_native_preflight):
        # mismos chequeos, mismos mensajes — una sola fuente, cero divergencia.
        key, mdl, err = _native_preflight(p, name, model, tools,
                                          "openai_compatible")
        if err:
            return False, err
        payload = {"model": mdl, "stream": False,
                   "messages": [{"role": "user", "content": prompt}]}
        hdrs = {"Content-Type": "application/json"}
        extra = (p.get("quirks") or {}).get("extra_headers") or {}
        for k, v in extra.items():
            # un quirk jamás mete una credencial de contrabando (el MISMO
            # filtro que el path interactivo — FORBIDDEN_HEADERS)
            if (isinstance(k, str) and isinstance(v, str)
                    and k.lower() not in FORBIDDEN_HEADERS):
                hdrs[k] = v
        if key:                       # auth none ⇒ jamás Authorization
            hdrs["Authorization"] = "Bearer " + key
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            try:
                # redactar ANTES de truncar (un corte a media key fugaría
                # el prefijo parcial al log)
                body = _redact(e.read().decode("utf-8", errors="replace"),
                               key)[:300]
            except Exception:
                body = ""
            return False, _redact("%s: HTTP %d: %s" % (name, e.code, body),
                                  key)
        except Exception as e:        # URLError / timeout / conexión rechazada
            return False, _redact("%s: red: %s" % (name, e), key)
        try:
            content = json.loads(raw)["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return False, ("%s: respuesta malformada (no es chat.completion): "
                           "%s" % (name, _redact(raw, key)[:200]))
        if not isinstance(content, str):
            return False, ("%s: respuesta sin texto (content=%s)"
                           % (name, type(content).__name__))
        return True, content

    return invoke


# ── adaptadores CONCRETOS: native_api ───────────────────────────────────────
# Protocolos PROPIOS de cada vendor, hablados directo con stdlib (urllib).
# Mismas leyes que openai_compatible: API key por NOMBRE de env-var (JAMÁS
# suscripción — eso es official_cli y vet_provider lo rechaza), redacción de
# la key en errores, y el request JAMÁS anuncia tools (sin manos por
# construcción ⇒ apto para destilación, guard N6).

#: versión del Messages API de Anthropic (header anthropic-version requerido)
ANTHROPIC_API_VERSION = "2023-06-01"

#: max_tokens default para APIs nativas que lo exigen (Anthropic Messages).
#: Override por provider: quirks.max_tokens en providers/<name>.json.
NATIVE_MAX_TOKENS = 8192

#: roles del schema neutral (fallback si neutral_transcript está amputado)
_NEUTRAL_ROLES = (tuple(neutral_transcript.VALID_ROLES)
                  if neutral_transcript is not None else ("user", "assistant"))


def _neutral_turn(role, text):
    """Turno del schema neutral (workspace.transcript). Reusa el constructor
    de neutral_transcript; shape idéntico si el módulo está amputado."""
    if neutral_transcript is not None:
        return neutral_transcript.make_turn(role, text)
    return {"role": role, "ts": "", "text": text or "",
            "noise": False, "tool_calls": []}


def neutral_turns_to_anthropic(turns):
    """Turnos neutrales → `messages` del Messages API de Anthropic.
    Solo texto visible; `noise` y turnos vacíos fuera; tool_calls JAMÁS se
    traducen (el conector no tiene canal de tools por diseño)."""
    out = []
    for t in turns or []:
        role = (t or {}).get("role")
        text = ((t or {}).get("text") or "").strip()
        if role not in _NEUTRAL_ROLES or not text or t.get("noise"):
            continue
        out.append({"role": role,
                    "content": [{"type": "text", "text": text}]})
    return out


def anthropic_response_to_turn(data):
    """Respuesta del Messages API → turno neutral del asistente, o None si
    no hay bloque de texto (concatena los content blocks type=text)."""
    blocks = (data or {}).get("content")
    if not isinstance(blocks, list):
        return None
    texts = [b.get("text", "") for b in blocks
             if isinstance(b, dict) and b.get("type") == "text"]
    if not texts:
        return None
    return _neutral_turn("assistant", "\n".join(texts))


def neutral_turns_to_gemini(turns):
    """Turnos neutrales → `contents` de generateContent (Gemini). El rol
    assistant del schema neutral es `model` en el vocabulario de Google."""
    out = []
    for t in turns or []:
        role = (t or {}).get("role")
        text = ((t or {}).get("text") or "").strip()
        if role not in _NEUTRAL_ROLES or not text or t.get("noise"):
            continue
        out.append({"role": "model" if role == "assistant" else "user",
                    "parts": [{"text": text}]})
    return out


def gemini_response_to_turn(data):
    """Respuesta de generateContent → turno neutral del asistente, o None
    (toma candidates[0].content.parts y concatena los `text`)."""
    cands = (data or {}).get("candidates")
    if not isinstance(cands, list) or not cands or not isinstance(cands[0], dict):
        return None
    parts = ((cands[0].get("content") or {}).get("parts")
             if isinstance(cands[0].get("content"), dict) else None)
    if not isinstance(parts, list):
        return None
    texts = [p.get("text", "") for p in parts
             if isinstance(p, dict) and isinstance(p.get("text"), str)]
    if not texts:
        return None
    return _neutral_turn("assistant", "\n".join(texts))


def _post_json(url, payload, hdrs, timeout, key, name):
    """POST JSON → (True, dict) | (False, error-str). Todo mensaje de error
    pasa por _redact: la key jamás llega a logs aunque el server la eque."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            # redactar ANTES de truncar (un corte a media key fugaría el
            # prefijo parcial al log)
            body = _redact(e.read().decode("utf-8", errors="replace"),
                           key)[:300]
        except Exception:
            body = ""
        return False, _redact("%s: HTTP %d: %s" % (name, e.code, body), key)
    except Exception as e:          # URLError / timeout / conexión rechazada
        return False, _redact("%s: red: %s" % (name, e), key)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("no es objeto JSON")
    except ValueError:
        return False, ("%s: respuesta malformada (no es JSON): %s"
                       % (name, _redact(raw, key)[:200]))
    return True, data


def _native_preflight(p, name, model, tools, connector_label):
    """Chequeos comunes de los adaptadores DIRECTOS (openai_compatible y
    nativos) ANTES de tocar la red — única fuente del preflight.
    Devuelve (key, mdl, err): err != "" ⇒ fallar sin request. Levanta
    HeadlessError si piden tools=read-only (no hay canal de tools)."""
    if tools == headless.TOOLS_READ_ONLY:
        raise headless.HeadlessError(
            'tools="read-only" no aplica al conector %s (%s): no hay canal '
            "de tools — usa tools=\"none\"" % (connector_label, name))
    key = ""
    if p.get("auth_type") == "api_key":
        key, err = _resolve_key(p)
        if not key:
            return "", "", "%s: %s" % (name, err)
    mdl = model or model_resolver.resolve_model({}, p)["model"]
    if not mdl:
        return "", "", ("%s: sin modelo — pasa model= o declara "
                        "default_model en providers/%s.json" % (name, name))
    return key, mdl, ""


def make_anthropic_native(provider):
    """Backend headless para el Messages API PROPIO de Anthropic:
    POST {base_url}/v1/messages con headers x-api-key + anthropic-version.

    Solo conexión por API key metered (ANTHROPIC_API_KEY por NOMBRE) — la
    SUSCRIPCIÓN del socio JAMÁS pasa por aquí (invariante: official_cli /
    providers/anthropic.json). El request nunca anuncia tools. `max_tokens`
    es requerido por el API: quirks.max_tokens o NATIVE_MAX_TOKENS."""
    p = dict(provider or {})
    name = p.get("name", "?")
    url = (p.get("base_url") or "").rstrip("/") + "/v1/messages"
    # `max_out` (no "…tokens"): el nombre evita un falso positivo del gate
    # env_secret de secret_scan (X_TOKEN = <valor> parece credencial .env).
    try:
        max_out = int((p.get("quirks") or {}).get("max_tokens")
                      or NATIVE_MAX_TOKENS)
    except (TypeError, ValueError):
        max_out = NATIVE_MAX_TOKENS

    def invoke(prompt, *, model, timeout, cwd, tools, exe_override):
        key, mdl, err = _native_preflight(p, name, model, tools,
                                          "anthropic native_api")
        if err:
            return False, err
        payload = {"model": mdl, "max_tokens": max_out,
                   "messages": neutral_turns_to_anthropic(
                       [_neutral_turn("user", prompt)])}
        hdrs = {"Content-Type": "application/json",
                "anthropic-version": ANTHROPIC_API_VERSION}
        if key:                     # auth none ⇒ jamás viaja credencial
            hdrs["x-api-key"] = key
        ok, data = _post_json(url, payload, hdrs, timeout, key, name)
        if not ok:
            return False, data
        turn = anthropic_response_to_turn(data)
        if turn is None:
            return False, ("%s: respuesta sin bloque de texto "
                           "(stop_reason=%r)" % (name, data.get("stop_reason")))
        return True, turn["text"]

    return invoke


def make_gemini_native(provider):
    """Backend headless para el API PROPIO de Google Gemini:
    POST {base_url}/v1beta/models/{model}:generateContent.

    La key va por HEADER x-goog-api-key (nunca por query ?key= — una
    credencial no se escribe en URLs que terminan en logs). Cuenta de
    consumidor de Google JAMÁS (vet_provider rechaza suscripción/oauth).
    El request nunca anuncia tools/toolConfig."""
    p = dict(provider or {})
    name = p.get("name", "?")
    base = (p.get("base_url") or "").rstrip("/")

    def invoke(prompt, *, model, timeout, cwd, tools, exe_override):
        key, mdl, err = _native_preflight(p, name, model, tools,
                                          "gemini native_api")
        if err:
            return False, err
        url = "%s/v1beta/models/%s:generateContent" % (
            base, urllib.parse.quote(mdl, safe=""))
        payload = {"contents": neutral_turns_to_gemini(
            [_neutral_turn("user", prompt)])}
        hdrs = {"Content-Type": "application/json"}
        if key:                     # auth none ⇒ jamás viaja credencial
            hdrs["x-goog-api-key"] = key
        ok, data = _post_json(url, payload, hdrs, timeout, key, name)
        if not ok:
            return False, data
        turn = gemini_response_to_turn(data)
        if turn is None:
            return False, ("%s: respuesta sin texto en candidates (%s)"
                           % (name, _redact(json.dumps(data), key)[:200]))
        return True, turn["text"]

    return invoke


#: api_mode → constructor del adaptador nativo CONCRETO
NATIVE_MAKERS = {
    "anthropic": make_anthropic_native,
    "gemini": make_gemini_native,
    "google": make_gemini_native,
}


# ── official_cli: andamiaje (Codex concreto; ver A-VERIFICAR) ───────────────
#: Qué CLI oficial existe, cómo se invoca headless y con qué ingester se
#: normalizan sus sesiones al schema neutral. La suscripción del socio la
#: gestiona el BINARIO OFICIAL (su propio login) — WORKSPACE jamás ve el token.
OFFICIAL_CLIS = {
    "claude-code": {
        "binary": "claude",
        "headless_backend": "claude-code",   # builtin en headless.py
        "ingester": "claude-code",           # neutral_transcript.PARSERS
        "sessions": "~/.claude/projects/<enc>/*.jsonl",
        "verified": True,
        "install_cmd": ["npm", "install", "-g", "@anthropic-ai/claude-code"],
        "login_cmd": ["claude"],             # el propio `claude` guía el login
        "account": "suscripción Claude (plan de pago) o API",
        "note": "primario del harness; hooks nativos completos (EVENTS.md)",
    },
    "codex": {
        "binary": "codex",
        "headless_backend": "codex",         # builtin (⚠ A-VERIFICAR)
        "ingester": "codex",                 # parse_codex (⚠ aproximación)
        "sessions": "~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl",
        "verified": False,
        # instalación + login del CLI OFICIAL (con el login del socio: la
        # suscripción ChatGPT). WORKSPACE jamás toca el token — solo instala el
        # binario (con confirmación) y lanza `codex login`, que gestiona su
        # propia auth.
        "install_cmd": ["npm", "install", "-g", "@openai/codex"],
        "login_cmd": ["codex", "login"],
        "account": "suscripción ChatGPT (Plus/Pro/Team)",
        "note": ("A-VERIFICAR contra un Codex CLI real: flags de `codex "
                 "exec` (--sandbox read-only / --output-last-message) según "
                 "docs públicas; parse_codex validado solo contra fixture; "
                 "sin knob confirmado de tools-off ⇒ el invariante headless "
                 "lo excluye de destilación (tools=\"none\")"),
    },
    "gemini": {
        "binary": "gemini",
        "headless_backend": "",              # A-IMPLEMENTAR
        "ingester": "",                      # A-IMPLEMENTAR
        "sessions": "",
        "verified": False,
        "install_cmd": ["npm", "install", "-g", "@google/gemini-cli"],
        "login_cmd": ["gemini"],
        "account": "cuenta Google (login del CLI)",
        "note": ("A-IMPLEMENTAR: Gemini CLI (login del socio). Sin backend "
                 "headless ni ingester aún — solo el asiento del andamiaje"),
    },
}


def official_cli_status(cli):
    """Estado del andamiaje de un CLI oficial (para doctor/--plan). Devuelve
    dict con binary_in_path / headless_registered / ingester_available, o
    None si el CLI no está en la tabla. Solo INSPECCIONA — jamás lanza el
    CLI real."""
    info = OFFICIAL_CLIS.get(cli)
    if not info:
        return None
    st = dict(info)
    st["cli"] = cli
    st["binary_in_path"] = bool(shutil.which(info["binary"]))
    hb = info.get("headless_backend", "")
    st["headless_registered"] = bool(hb and hb in headless.backends())
    ing = info.get("ingester", "")
    st["ingester_available"] = bool(
        ing and neutral_transcript is not None
        and ing in neutral_transcript.PARSERS)
    return st


def _env_present(provider):
    """(nombre, bool): la PRIMERA env-var declarada que esté seteada, y si
    alguna lo está. Reusa el mismo orden que _resolve_key pero SOLO devuelve
    el NOMBRE — el valor jamás sale (esto alimenta la UI de CUENTAS)."""
    for n in (provider or {}).get("env_vars") or []:
        if os.environ.get(n):
            return n, True
    return "", False


# ── metadata para el ASISTENTE de conexión (config TUI) ─────────────────────
#: Nombre bonito por provider (menos jerga que el `name` técnico).
PROVIDER_DISPLAY = {
    "openai": "OpenAI",
    "openrouter": "OpenRouter",
    "anthropic-api": "Anthropic API (medida)",
    "anthropic": "Claude (suscripción)",
    "codex": "Codex — ChatGPT",
    "gemini-api": "Google Gemini (API)",
    "gemini": "Gemini CLI",
    "ollama": "Ollama (local)",
    "lmstudio": "LM Studio (local)",
    "stub": "Stub (prueba)",
}

#: Dónde SACAR la credencial (URL real) — fallback si el provider.json no la
#: declara (`credential_url`). Es info pública, no un secreto.
CREDENTIAL_URLS = {
    "openai": "https://platform.openai.com/api-keys",
    "openrouter": "https://openrouter.ai/keys",
    "anthropic-api": "https://console.anthropic.com/settings/keys",
    "gemini-api": "https://aistudio.google.com/apikey",
}

#: Etiqueta legible del modelo de costo.
_COST_LABEL = {"metered": "API medida — pagas por uso",
               "subscription": "suscripción — tu plan mensual",
               "free": "local / gratis"}


def provider_display(provider):
    p = provider or {}
    return PROVIDER_DISPLAY.get(p.get("name", ""), p.get("name", "?"))


def credential_url(provider):
    """URL pública donde el socio saca su API key (declarativa en el
    provider.json → fallback a la tabla). '' si no aplica."""
    p = provider or {}
    return p.get("credential_url") or CREDENTIAL_URLS.get(p.get("name", ""), "")


def provider_group(provider):
    """Grupo del ASISTENTE (overview tipo doctor): 'subscription' | 'metered'
    | 'local' | 'other'. El eje que el socio entiende (qué CUENTA es)."""
    p = provider or {}
    ct = connection_type(p)
    auth = p.get("auth_type", "")
    if ct == "official_cli" or auth in _CONSUMER_AUTH:
        return "subscription"
    if auth == "api_key":
        return "metered"
    if auth in ("none", "") and ct in ("openai_compatible", "native_api"):
        return "local"
    return "other"


def _ping_url(p, key):
    """(url, headers) del endpoint de LISTADO de modelos (barato, sin gastar
    tokens) para verificar la credencial. La key va por header, jamás por
    query. auth none ⇒ sin Authorization."""
    burl = (p.get("base_url") or "").rstrip("/")
    api_mode = p.get("api_mode", "")
    if api_mode == "anthropic":
        hdrs = {"anthropic-version": ANTHROPIC_API_VERSION}
        if key:
            hdrs["x-api-key"] = key
        return burl + "/v1/models", hdrs
    if api_mode in ("gemini", "google"):
        hdrs = {}
        if key:
            hdrs["x-goog-api-key"] = key
        return burl + "/v1beta/models", hdrs
    hdrs = {}                                    # openai-compatible / openai
    if key:
        hdrs["Authorization"] = "Bearer " + key
    return burl + "/models", hdrs


def ping_provider(provider, key=None, timeout=6.0):
    """VERIFICA una credencial con una llamada REAL LIGERA (GET de listado de
    modelos — no gasta tokens). Fail-soft ABSOLUTO, timeout corto, la key SIEMPRE
    redactada en errores. Devuelve dict {ok, kind, detail}:
      kind: 'ok' (verificada) · 'auth' (rechazada 401/403 — NO guardar) ·
      'unverified' (alcanzable pero sin endpoint de verificación 404/405) ·
      'network'/'http' (no se pudo verificar) · 'no_key' · 'blocked' ·
      'cli'/'cli_missing' (official_cli: solo binario en PATH) · 'unsupported'.
    key=None ⇒ usa la del env (para RE-validar una ya conectada). Un secreto
    JAMÁS se loguea (pasa por _redact)."""
    p = provider or {}
    name = p.get("name", "?")
    verrs = vet_provider(p)
    if verrs:
        return {"ok": False, "kind": "blocked", "detail": verrs[0]}
    ct = connection_type(p)
    if ct == "official_cli":
        cli = p.get("cli") or name
        cst = official_cli_status(cli)
        if cst and cst.get("binary_in_path"):
            return {"ok": True, "kind": "cli",
                    "detail": "CLI '%s' en PATH — el login lo verifica el "
                              "propio CLI" % cli}
        return {"ok": False, "kind": "cli_missing",
                "detail": "CLI '%s' no está en PATH" % cli}
    auth = p.get("auth_type", "")
    if key is None and auth == "api_key":
        key, kerr = _resolve_key(p)
        if not key:
            return {"ok": False, "kind": "no_key", "detail": kerr}
    key = key or ""
    if not (p.get("base_url") or "").startswith(("http://", "https://")):
        return {"ok": False, "kind": "unsupported",
                "detail": "%s: sin base_url http(s) para verificar" % name}
    url, hdrs = _ping_url(p, key)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(64)                        # drena un poco; no nos importa
        return {"ok": True, "kind": "ok",
                "detail": "conexión verificada — %s respondió" % name}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"ok": False, "kind": "auth",
                    "detail": "%s rechazó la credencial (HTTP %d) — revisa la "
                              "key" % (name, e.code)}
        if e.code in (404, 405):                 # sin endpoint de listado
            return {"ok": True, "kind": "unverified",
                    "detail": "%s alcanzable; sin endpoint de verificación "
                              "(HTTP %d)" % (name, e.code)}
        return {"ok": False, "kind": "http",
                "detail": _redact("%s: HTTP %d" % (name, e.code), key)}
    except Exception as e:                        # URLError / timeout / rechazo
        return {"ok": False, "kind": "network",
                "detail": _redact("%s: no pude conectar: %s" % (name, e), key)}


def provider_status(provider):
    """Estado de conexión HONESTO de un provider — para la UI de CUENTAS del
    config TUI y para el doctor. Solo INSPECCIONA (env + `which`): jamás lanza
    un CLI ni toca la red, y el VALOR de un secreto JAMÁS sale (solo bool y
    NOMBRES). Reusa connection_type + vet_provider + _resolve_key (vía
    _env_present) + official_cli_status — cero lógica nueva de seguridad.

    Devuelve dict (además de los campos del ASISTENTE — display/group/cost/
    credential_url + install_cmd/login_cmd para official_cli):
      name, display, group, connection, auth_type, cost, cost_label,
      state   — "connected" | "needs_key" | "cli_missing" | "reachable" |
                "blocked" | "unknown"
      ok      — bool (True ⇒ punto verde: conectado/alcanzable)
      detail  — frase legible del estado
      env_vars/env_present, cli, cli_present, credential_url,
      install_cmd/login_cmd (official_cli),
      action  — "paste_key" | "cli_login" | "none"
      action_hint, blocked
    """
    p = provider or {}
    name = p.get("name", "?")
    auth = p.get("auth_type", "")
    env_vars = list(p.get("env_vars") or [])
    cost = p.get("cost", "")
    st = {"name": name, "display": provider_display(p),
          "group": provider_group(p), "connection": connection_type(p),
          "auth_type": auth, "cost": cost,
          "cost_label": _COST_LABEL.get(cost, cost or "—"),
          "env_vars": env_vars, "env_present": "", "cli": p.get("cli", ""),
          "cli_present": False, "credential_url": credential_url(p),
          "install_cmd": [], "login_cmd": [],
          "action": "none", "action_hint": "", "blocked": []}
    verrs = vet_provider(p)
    if verrs:
        st.update(state="blocked", ok=False, blocked=verrs, detail=verrs[0])
        return st
    ct = st["connection"]
    if ct == "official_cli":
        cli = p.get("cli") or name
        cst = official_cli_status(cli)
        info = OFFICIAL_CLIS.get(cli) or {}
        st["cli"] = cli
        st["cli_present"] = bool(cst and cst.get("binary_in_path"))
        st["install_cmd"] = list(info.get("install_cmd") or [])
        st["login_cmd"] = list(info.get("login_cmd") or [])
        st["action"] = "cli_login"
        st["action_hint"] = " ".join(st["login_cmd"]) or ("%s login" % cli)
        if st["cli_present"]:
            # binario presente: el LOGIN lo gestiona el CLI oficial — WORKSPACE
            # no puede (ni debe) inspeccionar su token. "alcanzable" honesto.
            st.update(state="reachable", ok=True,
                      detail="CLI '%s' instalado — inicia sesión con `%s` (el "
                             "CLI gestiona el token, WORKSPACE nunca lo toca)"
                             % (cli, st["action_hint"]))
        else:
            st.update(state="cli_missing", ok=False,
                      detail="CLI '%s' no instalado — el asistente lo instala "
                             "(con tu confirmación) y lanza el login" % cli)
        return st
    if auth == "api_key":
        env_name, present = _env_present(p)
        st["env_present"] = env_name
        st["action"] = "paste_key"
        pretty = " o ".join(env_vars) or "una env-var declarada"
        if present:
            st.update(state="connected", ok=True,
                      detail="conectada — %s presente en el env" % env_name)
        else:
            st.update(state="needs_key", ok=False,
                      detail="sin credencial — pega tu API key (vive "
                             "per-máquina, jamás en el repo); falta %s" % pretty)
        return st
    if auth in ("none", "") and ct in ("openai_compatible", "native_api"):
        # local / sin auth: alcanzable por construcción (no se hace ping).
        st.update(state="reachable", ok=True,
                  detail="local / sin credencial (%s) — alcanzable; jamás se "
                         "manda Authorization" % (p.get("base_url") or "?"))
        return st
    st.update(state="unknown", ok=False,
              detail="sin tipo de conexión reconocible (api_mode=%r)"
                     % p.get("api_mode", ""))
    return st


def all_provider_status():
    """[provider_status(...)] de TODOS los providers declarados, en orden
    alfabético. Falla-suave por provider: uno ilegible aparece como blocked
    con el error de carga (jamás tumba la lista)."""
    out = []
    for name in model_resolver.list_providers():
        p, errs = model_resolver.load_provider(name)
        if errs:
            out.append({"name": name, "display": PROVIDER_DISPLAY.get(name, name),
                        "group": "other", "connection": "", "auth_type": "",
                        "cost": "", "cost_label": "—",
                        "env_vars": [], "env_present": "", "cli": "",
                        "cli_present": False, "credential_url": "",
                        "install_cmd": [], "login_cmd": [],
                        "action": "none", "action_hint": "",
                        "state": "blocked", "ok": False, "blocked": errs,
                        "detail": errs[0]})
            continue
        out.append(provider_status(p))
    return out


def ingest_cli_session(cli, path):
    """Sesión cruda de un CLI oficial → doc neutral (workspace.transcript v1),
    reusando el ingester ya presente (Codex: parse_codex). Devuelve None si
    el CLI no tiene ingester; OSError si el archivo es ilegible."""
    info = OFFICIAL_CLIS.get(cli) or {}
    ing = info.get("ingester", "")
    if not ing or neutral_transcript is None:
        return None
    parser = neutral_transcript.PARSERS.get(ing)
    return parser(path) if parser else None


# ── seam de portabilidad (datos; doc: engines/PORTABILITY.md) ───────────────
PORTABILITY = {
    "openai_compatible": {
        "tools_channel": "none",           # headless one-shot: sin manos
        "hooks_channel": "workspace-loop",   # WORKSPACE arma el request ⇒ N9 propio
        "note": ("cuando WORKSPACE sea dueño del loop interactivo (motor #2), "
                 "tools = loop de tool-calling propio + puente MCP; hoy el "
                 "conector es one-shot sin tools POR DISEÑO (destilación)"),
    },
    "native_api": {
        "tools_channel": "none",           # sin canal de tools (mismo patrón)
        "hooks_channel": "workspace-loop",
        "note": ("CONCRETO: Anthropic Messages API + Gemini generateContent "
                 "(NATIVE_MAKERS); one-shot sin tools POR DISEÑO, igual que "
                 "openai_compatible"),
    },
    "official_cli": {
        "tools_channel": "mcp",            # estándar cross-motor
        "hooks_channel": "vendor-hooks|workspace-wrapper",
        "note": ("claude-code: hooks nativos (EVENTS.md). codex/gemini: sin "
                 "hook-system equivalente ⇒ el wrapper de WORKSPACE emite los "
                 "eventos N9 que pueda observar desde fuera (session_start/"
                 "end); pre_prompt middleware solo existe donde WORKSPACE es "
                 "dueño del request"),
    },
}


# ── registro: providers/*.json → backends headless ─────────────────────────
def register_provider_backends():
    """Registra como backends headless los providers CONECTABLES declarados
    en providers/*.json. Idempotente y fail-soft por provider. Devuelve
    reporte {"registered": [...], "skipped": {n: razón}, "rejected":
    {n: [errores]}}.

    Reglas:
      · provider inválido (shape/secret_scan de model_resolver) → rejected
      · vet_provider con errores (INVARIANTE incluido) → rejected
      · nombre ya registrado en headless → skipped (el builtin GANA; un
        provider jamás pisa un backend existente)
      · openai_compatible → se registra CONCRETO (make_openai_compatible)
      · native_api → se registra CONCRETO si su api_mode tiene adaptador en
        NATIVE_MAKERS (anthropic / gemini / google); si no, skipped honesto
      · official_cli → cubierto por el backend builtin del CLI si existe;
        si no, skipped A-IMPLEMENTAR (jamás se inventa un launcher)
      · desconocido → skipped (jamás se adivina)

    NO cambia el default de nada: DEFAULT_BACKEND sigue siendo claude-code;
    usar un provider es opt-in por nombre (WORKSPACE_DREAM_BACKEND=…)."""
    report = {"registered": [], "skipped": {}, "rejected": {}}
    for name in model_resolver.list_providers():
        p, errs = model_resolver.load_provider(name)
        if errs:
            report["rejected"][name] = errs
            continue
        verrs = vet_provider(p)
        if verrs:
            report["rejected"][name] = verrs
            continue
        ct = connection_type(p)
        if name in headless.backends():
            report["skipped"][name] = ("backend '%s' ya registrado — el "
                                       "builtin gana, jamás se pisa" % name)
            continue
        if ct == "openai_compatible":
            headless.register_backend(
                name, make_openai_compatible(p),
                can_disable_tools=True,   # sin canal de tools por construcción
                verified=True,            # probado vs stub HTTP local (suite)
                note="openai_compatible → %s" % (p.get("base_url") or "?"))
            report["registered"].append(name)
        elif ct == "official_cli":
            cli = p.get("cli") or name
            info = OFFICIAL_CLIS.get(cli) or {}
            hb = info.get("headless_backend", "")
            if hb and hb in headless.backends():
                report["skipped"][name] = ("official_cli cubierto por el "
                                           "backend builtin '%s'" % hb)
            else:
                report["skipped"][name] = ("official_cli '%s' A-IMPLEMENTAR "
                                           "(sin backend headless aún)" % cli)
        elif ct == "native_api":
            make = NATIVE_MAKERS.get(p.get("api_mode", ""))
            if make is None:
                report["skipped"][name] = (
                    "native_api con api_mode %r sin adaptador (disponibles: "
                    "%s)" % (p.get("api_mode", ""),
                             ", ".join(sorted(NATIVE_MAKERS))))
            else:
                headless.register_backend(
                    name, make(p),
                    can_disable_tools=True,  # sin canal de tools por construcción
                    # HONESTO: el shape está probado vs stub HTTP loopback
                    # (suite), pero NO hay llamada real verificada contra el
                    # vendor — verified se GANA con esa llamada, no se declara
                    verified=False,
                    note="native_api (%s) → %s — llamada real A-VERIFICAR"
                         % (p.get("api_mode", "?"), p.get("base_url") or "?"))
                report["registered"].append(name)
        else:
            report["skipped"][name] = ("sin tipo de conexión reconocible "
                                       "(api_mode=%r)" % p.get("api_mode", ""))
    return report


if __name__ == "__main__":
    # inspección rápida:  python3 connectors.py
    rep = register_provider_backends()
    print("conectores — modelo de conexión (a/b/c/d); default intacto: %s"
          % headless.DEFAULT_BACKEND)
    for n in rep["registered"]:
        p, _ = model_resolver.load_provider(n)
        print("  ✓ %-12s %-18s %s" % (n, connection_type(p),
                                      (p or {}).get("base_url", "")))
        missing = model_resolver.missing_env_vars(p)
        if missing:
            print("      ⚠ falta en el env: %s" % ", ".join(missing))
    for n, why in sorted(rep["skipped"].items()):
        print("  · %-12s %s" % (n, why))
    for n, errs in sorted(rep["rejected"].items()):
        print("  ✗ %-12s %s" % (n, "; ".join(errs)))
    print("CLIs oficiales:")
    for cli in sorted(OFFICIAL_CLIS):
        st = official_cli_status(cli)
        print("  %s %-12s binario=%s headless=%s ingester=%s — %s"
              % ("✓" if st["verified"] else "⚠", cli,
                 "sí" if st["binary_in_path"] else "no",
                 "sí" if st["headless_registered"] else "no",
                 "sí" if st["ingester_available"] else "no",
                 st["note"][:60]))
