"""WORKSPACE · deciders/openrouter — OpenRouter Decisions, en la nube.

Una llave, muchos modelos de decisión de varias marcas, con el MISMO
protocolo que Jev (System One: deciders/_systemone.py), solo cambia la URL
base («cambiar la URL base», dice su guía):

  POST {OPENROUTER_DECISIONS_BASE_URL o https://openrouter.ai/api}/v1/systemone
  Authorization: Bearer <llave> · {"state", "model": "<marca/modelo>", "questions"}
  → answers.q.{choice, confidence, probabilities} + usage (con `cost`: el
    costo REAL de la llamada, que gana sobre la cuenta uso × precio)

El modelo se elige en Motores → Modelos de decisión (ajuste
`decisions.decider_models`); de fábrica, el Jev más nuevo. Es alpha («the
shape may change»): sin reintentos, y un cambio de forma es `bad_response`.

La llave, en este orden: WORKSPACE_DECIDER_OPENROUTER_KEY del entorno →
OPENROUTER_API_KEY del entorno → la bóveda (siempre con el nombre propio:
guardarla como OPENROUTER_API_KEY le quitaría a Hermes, OpenClaw u opencode
la que exportaste a mano con el mismo valor). Jamás se imprime ni se anota.
Términos: la llave es SIEMPRE la del socio (OpenRouter prohíbe revender su
acceso); Workspace no trae una propia."""
import time

from deciders import _systemone as S

ENV_KEY = "WORKSPACE_DECIDER_OPENROUTER_KEY"
ENV_KEY_STD = "OPENROUTER_API_KEY"
ENV_BASE_URL = "OPENROUTER_DECISIONS_BASE_URL"
DEFAULT_BASE_URL = "https://openrouter.ai/api"
DEFAULT_MODEL = "~typesafe/jev-latest"
#: Los modelos de decisión que lista OpenRouter (ids de su documentación del
#: 2026-11-08; el primero es el de fábrica). SOLO estos: OpenRouter también
#: sirve modelos de chat (openai/gpt-4o…) y ninguno de esos se puede elegir,
#: ni guardar, ni medir (decisions.check_model). Medidos con llave real el
#: 2026-11-08 (97 casos): fuera inception/mercury-decide (404 en todas: no existe
#: hoy) y upstage/solar-decide (se agota el tiempo: 79/97, p95 5 s).
MODELS = (DEFAULT_MODEL, "typesafe/jev-1.14", "liquid/d1", "liquid/d1-ultra",
          "cloudflare/clef", "cloudflare/clef-flash", "perplexity/pplx-decider-v1.2",
          "perplexity/pplx-decider-flash-v1.2", "openai/gpt-6-luna-decisions",
          "microsoft/microsoft-decision-1")
#: Medidos LENTOS para los usos (p95 por encima de su tiempo límite de 1.5 s):
#: cloudflare/clef, p95 1.7 s. Se ofrece, con la pista «lento».
SLOW = frozenset(("cloudflare/clef",))

META = {"id": "openrouter", "label": "OpenRouter", "local": False,
        "kinds": ["choice", "score"], "offer": True,
        "key_env": ENV_KEY, "key_env_std": ENV_KEY_STD,
        "provider": "OpenRouter", "site": "openrouter.ai",
        # CONSERVADOR: Jev admite 262 144 por OpenRouter, pero arriba de ~32 KB de
        # texto entra en «long-context» («slower and less accurate»).
        "context_tokens": 32768, "overhead_tokens": 300,
        # el precio es el de cada modelo: el costo real llega en usage.cost
        "price_in_per_m": None, "price_out_per_m": 0.0, "approx_price": True,
        "price_from_response": True,
        # su página de llaves (docs de OpenRouter) y que cada llave admite un tope de
        # gasto propio: la pantalla de conectar lo recomienda
        "keys_url": "https://openrouter.ai/keys", "key_spend_limit": True,
        "models": list(MODELS), "default_model": DEFAULT_MODEL}

SPEC = {"id": "openrouter", "base_url": DEFAULT_BASE_URL, "base_url_env": ENV_BASE_URL,
        "path": "/v1/systemone", "auth": "bearer", "zstd": True,
        "request_id_header": "x-request-id", "runtime_header": None,
        "root_fields": S.ROOT_FIELDS, "errors": "models", "usage_cost": True,
        "key_own": ENV_KEY, "key_std": ENV_KEY_STD, "key_envs": (ENV_KEY, ENV_KEY_STD)}


def key_source():
    return S.key_source(SPEC)


def _key():
    return S.read_key(SPEC)


def status():
    if not _key():
        return {"ready": False, "detail": "no_key"}
    return {"ready": True, "detail": "cloud"}


def models():
    return list(MODELS)


def model():
    return S.chosen_model(META["id"], MODELS, DEFAULT_MODEL)


#: La marca de cada modelo (la pista de su fila en la lista de Modelos).
BRANDS = {"typesafe": "TypeSafe", "liquid": "Liquid", "cloudflare": "Cloudflare",
          "perplexity": "Perplexity", "openai": "OpenAI", "microsoft": "Microsoft"}


def model_info(model_id):
    """{"brand", "slow"} de un modelo de la lista («perplexity/…» → Perplexity;
    `slow` = medido más lento que el tiempo límite de los usos)."""
    pref = str(model_id or "").lstrip("~").split("/")[0].lower()
    return {"brand": BRANDS.get(pref, pref.capitalize()), "slow": model_id in SLOW}


def base_url():
    return S.base_url(SPEC)


def _send(req, timeout_s):
    return S.send(req, timeout_s)


def decide(req):
    t0 = time.time()
    key = _key()
    if not key:
        return S.fail(SPEC, t0, "no_key")
    try:
        return S.decide(SPEC, META, req, key, base_url(), model(), _send)
    except Exception as e:                      # el contrato: jamás levantar
        return S.fail(SPEC, t0, "error", key, {"class": type(e).__name__})

