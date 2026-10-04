#!/usr/bin/env python3
"""WORKSPACE · model_resolver — capa declarativa de providers + resolución
motor→provider→modelo (motor #2, corrida E-1; spec congelada C1 de la síntesis).

Vocabulario (ver research/motor2-plan.md §1):
  · engine   = código que arranca al agente (engines/<n>.py, contrato CONTRACT.md)
  · provider = perfil DECLARATIVO de dónde/cómo se habla con modelos (providers/<n>.json)
  · model    = string que el provider conoce; se resuelve POR TAREA

Los 4 ejes de cambio de motor (auth · API · ubicación · costo) viven como
campos del provider — DATOS, jamás ifs en engines/ (quirks-as-data, Hermes §4).

🔴 Regla de oro (EJECUTADA aquí, no solo escrita): providers/*.json declaran
NOMBRES de env-vars, jamás valores de credenciales. `load_provider` valida el
shape y pasa el archivo crudo por `secret_scan.scan_text`: cualquier secreto
detectado ⇒ el provider NO carga (validate_provider lo reporta).

Resolución de modelo por tarea (resolver de Odysseus, cicatrices incluidas):
  · default          → engine_config.model → provider.default_model → 1er modelo CHAT
  · research / task  → aux_models[t] → task_models[t] → CAEN A utility
                       (jamás saltan al default global — tareas de fondo no
                        terminan en el modelo caro)
  · utility          → aux_models/task_models.utility → default_aux_model →
                       último recurso default_model (marcado degraded)
  · hidden_models nunca se eligen; embeddings/tts/whisper nunca se auto-eligen
    (_first_chat_model — la cicatriz "text-embedding-ada-002 listado primero").

Selection-source policy (OpenClaw): elección explícita del socio (cli/env) =
ESTRICTA ⇒ sin cadena de fallback; default (agent.json) ⇒ fallbacks permitidos.

FAILOVER_REASONS: taxonomía razón→estrategia como DATOS desde el día 1 (lección
Hermes: años de if-strings dispersos antes de extraer el clasificador — heredamos
la lección sin pagar los años). Desde E-3 la consume `failover.py` end-to-end:
FAILOVER_STRATEGIES (abajo) define CÓMO se ejecuta cada estrategia (reintentos
acotados, si cae al siguiente de la cadena, qué escalera de cooldown aplica).

Cero dependencias (stdlib, Python 3.9+). Cross-platform. Amputable (C10):
borra este archivo y providers/ deja de cargar — claude-code sigue lanzando igual.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
PROVIDERS_DIR = os.path.join(ROOT, "providers")

# ── vocabulario cerrado (datos, no ifs) ─────────────────────────────────────
TASKS = ("research", "task", "utility", "default")
AUTH_TYPES = ("api_key", "oauth", "subscription", "none")

# nombre válido de env-var: MAYÚSCULAS_CON_GUIONES_BAJOS (jamás un valor)
_ENV_NAME_RX = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
# modelos que JAMÁS se auto-eligen como chat (cicatriz _first_chat_model, Odysseus)
_NON_CHAT_RX = re.compile(r"embed|embedding|tts|whisper|rerank", re.IGNORECASE)

# ── taxonomía de failover (C1 — datos desde el día 1; consumo real en E-3) ──
FAILOVER_REASONS = {
    "rate_limit":         "cooldown_retry",        # backoff exponencial por credencial
    "billing":            "cooldown_long",         # billing ≠ rate-limit (ventanas distintas)
    "auth_expired":       "refresh_credential",    # OAuth/suscripción: refresh at-call-time
    "auth_invalid":       "rotate_credential",
    "context_overflow":   "compress",              # → context_budget.trim_for_context
    "server_error":       "retry_then_fallback",
    "network":            "retry",
    "timeout":            "retry_then_fallback",
    "bad_request":        "abort",                 # reintentar lo mismo no lo arregla
    "model_not_found":    "fallback_model",
    "content_filter":     "abort",
    "malformed_response": "retry_once",            # quirk típico de modelos locales
    "unknown":            "fallback_model",
}

# Cómo se EJECUTA cada estrategia (la otra mitad de la taxonomía — también
# DATOS; la consume failover.run_with_failover desde E-3):
#   · retries  — reintentos extra sobre el MISMO modelo (acotado, jamás loop)
#   · fallback — al agotar reintentos, ¿pasar al siguiente de la cadena?
#                False en errores que otro modelo NO arregla (red caída,
#                credencial rota — misma key ⇒ mismo 401) o que reintentar
#                empeora (abort).
#   · cooldown — escalera de enfriamiento que se le aplica al modelo fallado
#                ("" = ninguna). billing ≠ rate_limit: VENTANAS DISTINTAS
#                (robo de OpenClaw) — las escaleras viven en
#                failover.COOLDOWN_LADDERS, model-scoped y persistidas.
FAILOVER_STRATEGIES = {
    "retry":               {"retries": 2, "fallback": False, "cooldown": ""},
    "retry_once":          {"retries": 1, "fallback": True,  "cooldown": ""},
    "retry_then_fallback": {"retries": 2, "fallback": True,  "cooldown": ""},
    "cooldown_retry":      {"retries": 0, "fallback": True,  "cooldown": "rate_limit"},
    "cooldown_long":       {"retries": 0, "fallback": True,  "cooldown": "billing"},
    "refresh_credential":  {"retries": 0, "fallback": False, "cooldown": ""},  # refresh real: E-4
    "rotate_credential":   {"retries": 0, "fallback": False, "cooldown": ""},  # E-4
    "compress":            {"retries": 0, "fallback": False, "cooldown": ""},  # C14 ya corrió antes del POST
    "fallback_model":      {"retries": 0, "fallback": True,  "cooldown": ""},
    "abort":               {"retries": 0, "fallback": False, "cooldown": ""},
}


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── carga y validación de providers ─────────────────────────────────────────
def list_providers():
    """Nombres de providers declarados (providers/*.json, sin '_')."""
    out = []
    if os.path.isdir(PROVIDERS_DIR):
        for f in sorted(os.listdir(PROVIDERS_DIR)):
            if f.endswith(".json") and not f.startswith("_"):
                out.append(f[:-5])
    return out


def validate_provider(data, raw_text=""):
    """Valida el shape declarativo. Devuelve lista de errores ([] = válido).

    Incluye la regla de oro: env_vars deben PARECER nombres de variables de
    entorno, y el archivo crudo no puede contener un secreto detectable."""
    errors = []
    if not isinstance(data, dict):
        return ["el provider no es un objeto JSON"]
    if not data.get("name"):
        errors.append("falta 'name'")
    auth = data.get("auth_type", "")
    if auth not in AUTH_TYPES:
        errors.append("auth_type '%s' inválido (válidos: %s)"
                      % (auth, "/".join(AUTH_TYPES)))
    ev = data.get("env_vars", [])
    if not isinstance(ev, list):
        errors.append("env_vars debe ser lista de NOMBRES de env-vars")
        ev = []
    for v in ev:
        if not isinstance(v, str) or not _ENV_NAME_RX.match(v):
            errors.append("env_vars: '%s' no parece NOMBRE de env-var "
                          "(MAYUSCULAS_GUION_BAJO; jamás el valor)" % (v,))
    for campo in ("models", "fallback_models", "hidden_models"):
        if campo in data and not isinstance(data[campo], list):
            errors.append("%s debe ser lista" % campo)
    tm = data.get("task_models", {})
    if not isinstance(tm, dict):
        errors.append("task_models debe ser objeto {tarea: modelo}")
    else:
        for t in tm:
            if t not in TASKS:
                errors.append("task_models: tarea '%s' fuera del vocabulario %s"
                              % (t, "/".join(TASKS)))
    # 🔴 regla de oro: ningún secreto en el archivo (reusa el escáner N14)
    if raw_text:
        try:
            import secret_scan
            for f in secret_scan.scan_text(raw_text):
                errors.append("REGLA DE ORO violada: posible secreto [%s] en "
                              "línea %d — providers/*.json llevan NOMBRES de "
                              "env-vars, jamás valores" % (f["class"], f["line"]))
        except ImportError:
            pass   # secret_scan amputado → la validación de shape sigue valiendo
    return errors


def load_provider(name):
    """Carga providers/<name>.json validado. Devuelve (data, errores):
    (dict, []) si es válido · (None, [errores]) si no carga o es inválido.
    Falla-suave: jamás levanta."""
    if not name:
        return None, ["sin nombre de provider"]
    path = os.path.join(PROVIDERS_DIR, str(name) + ".json")
    if not os.path.isfile(path):
        return None, ["no existe providers/%s.json (declarados: %s)"
                      % (name, ", ".join(list_providers()) or "ninguno")]
    try:
        raw = open(path, encoding="utf-8").read()
        data = json.loads(raw)
    except Exception as e:
        return None, ["providers/%s.json ilegible: %s" % (name, e)]
    errors = validate_provider(data, raw_text=raw)
    if errors:
        return None, errors
    return data, []


def missing_env_vars(provider):
    """Nombres de env-vars declarados por el provider que NO están en el
    entorno (chequeo de salud para --plan/doctor; jamás lee los valores)."""
    return [v for v in (provider or {}).get("env_vars", [])
            if not os.environ.get(v)]


# ── resolución de modelo por tarea ──────────────────────────────────────────
def _is_chat_model(model):
    return bool(model) and not _NON_CHAT_RX.search(model)


def _first_chat_model(provider):
    """Primer modelo utilizable como chat de provider.models — excluye
    embeddings/tts/whisper/rerank y los hidden_models."""
    hidden = set(provider.get("hidden_models", []))
    for m in provider.get("models", []):
        if m not in hidden and _is_chat_model(m):
            return m
    return ""


def _visible(provider, model):
    """True si el modelo NO está escondido por el admin del provider."""
    return bool(model) and model not in set((provider or {}).get("hidden_models", []))


def resolve_model(engine_config, provider, task="default"):
    """Resuelve el modelo para una tarea. Devuelve dict:
      {"model": str, "task": tarea, "degraded": bool, "chain": [intentos]}
    `chain` documenta el camino recorrido (para --plan y debugging).
    Tareas fuera del vocabulario caen a 'default'."""
    ec = engine_config or {}
    p = provider or {}
    task = task if task in TASKS else "default"
    aux = ec.get("aux_models") or {}
    tm = p.get("task_models") or {}
    chain, degraded = [], False

    def _try(label, model):
        chain.append("%s=%s" % (label, model or "—"))
        return model if (model and _visible(p, model)) else ""

    m = ""
    if task == "default":
        m = (_try("engine_config.model", ec.get("model"))
             or _try("provider.default_model", p.get("default_model"))
             or _try("primer_modelo_chat", _first_chat_model(p)))
    else:
        # tarea de fondo: específica → utility. JAMÁS salta al default global.
        if task != "utility":
            m = (_try("aux_models.%s" % task, aux.get(task))
                 or _try("task_models.%s" % task, tm.get(task)))
        if not m:
            m = (_try("aux_models.utility", aux.get("utility"))
                 or _try("task_models.utility", tm.get("utility"))
                 or _try("provider.default_aux_model", p.get("default_aux_model")))
        if not m:
            # último recurso, MARCADO: no hay nada barato configurado
            m = (_try("provider.default_model(degraded)", p.get("default_model"))
                 or _try("primer_modelo_chat(degraded)", _first_chat_model(p)))
            degraded = bool(m)
    return {"model": m, "task": task, "degraded": degraded, "chain": chain}


def resolve(cfg, task="default"):
    """Resolución completa motor→provider→modelo para un agente ya cargado
    por dispatch (cfg trae engine, engine_config, _engine_source).

    Devuelve:
      {"engine", "source", "strict", "provider", "provider_errors",
       "model", "task", "degraded", "fallbacks", "missing_env", "chain"}

    · source/strict — selection-source policy (OpenClaw): cli/env = elección
      explícita del socio = ESTRICTA ⇒ fallbacks vacíos. agent = default ⇒
      cadena fallback_models permitida (menos hidden).
    · provider None es legítimo (motor #1: claude-code no consume providers)."""
    cfg = cfg or {}
    ec = cfg.get("engine_config") or {}
    engine = cfg.get("engine", "")
    source = cfg.get("_engine_source", "agent")
    strict = source in ("cli", "env")

    pname = ec.get("provider") or ""
    provider, perr = (None, [])
    if pname:
        provider, perr = load_provider(pname)
    elif engine and engine in list_providers():
        # convención: si existe un provider homónimo del motor, es el suyo
        pname = engine
        provider, perr = load_provider(engine)

    r = resolve_model(ec, provider, task=task)
    fallbacks = []
    if provider and not strict:
        fallbacks = [m for m in provider.get("fallback_models", [])
                     if _visible(provider, m) and m != r["model"]]
    return {
        "engine": engine,
        "source": source,
        "strict": strict,
        "provider": (provider or {}).get("name") or (pname or None),
        "provider_errors": perr,
        "model": r["model"],
        "task": r["task"],
        "degraded": r["degraded"],
        "fallbacks": fallbacks,
        "missing_env": missing_env_vars(provider),
        "chain": r["chain"],
    }


if __name__ == "__main__":
    # inspección rápida:  python3 model_resolver.py [provider] [tarea]
    import sys
    args = sys.argv[1:]
    name = args[0] if args else ""
    task = args[1] if len(args) > 1 else "default"
    if not name:
        print("providers declarados:", ", ".join(list_providers()) or "(ninguno)")
        sys.exit(0)
    p, errs = load_provider(name)
    if errs:
        print("✗ providers/%s.json INVÁLIDO:" % name)
        for e in errs:
            print("   ·", e)
        sys.exit(1)
    r = resolve({"engine": name, "engine_config": {"provider": name}}, task=task)
    print("✓ provider %s — auth=%s api=%s base_url=%s cost=%s"
          % (p["name"], p.get("auth_type"), p.get("api_mode"),
             p.get("base_url") or "(n/a)", p.get("cost", "?")))
    print("  tarea %-8s → modelo %s%s · fallbacks %s"
          % (r["task"], r["model"] or "(ninguno)",
             " (DEGRADED)" if r["degraded"] else "", r["fallbacks"] or "—"))
    print("  camino:", " → ".join(r["chain"]))
