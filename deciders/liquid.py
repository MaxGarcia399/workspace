"""WORKSPACE · deciders/liquid — Liquid d1.1 / d1-ultra, en la nube.

Liquid «implements TypeSafe's System One API»: el mismo protocolo que Jev
(deciders/_systemone.py) con otra dirección y SIN zstd (no lo acepta; el
cliente de Jev comprime en Python 3.14+):

  POST {LIQUID_DECISIONS_BASE_URL o https://api.liquid.ai/decisions}/v1/systemone
  Authorization: Bearer <llave> · {"state", "model": "d1.1" | "d1-ultra", "questions"}

El cuerpo admite hasta 4.5 MB: uno más grande ni se manda (`context_too_large`).
El modelo se elige en Motores → Modelos de decisión (`decisions.decider_models`).

La llave, en este orden: WORKSPACE_DECIDER_LIQUID_KEY del entorno →
LIQUID_API_KEY del entorno → la bóveda (con el nombre propio). Jamás se
imprime ni se anota."""
import time

from deciders import _systemone as S

ENV_KEY = "WORKSPACE_DECIDER_LIQUID_KEY"
ENV_KEY_STD = "LIQUID_API_KEY"
ENV_BASE_URL = "LIQUID_DECISIONS_BASE_URL"
DEFAULT_BASE_URL = "https://api.liquid.ai/decisions"
DEFAULT_MODEL = "d1.1"
#: Sus modelos de DECISIÓN (solo estos se eligen; Liquid tiene también de chat).
MODELS = (DEFAULT_MODEL, "d1-ultra")
#: Precio de ENTRADA por millón de tokens, por modelo (liquid.ai/pricing,
#: 2026-11-08); la salida no se cobra.
PRICES = {"d1.1": 0.02, "d1-ultra": 0.042}
#: Lo más que acepta en el cuerpo (4.5 MB, su documentación).
MAX_BODY = 4500000

META = {"id": "liquid", "label": "Liquid", "local": False,
        "kinds": ["choice", "score"], "offer": True,
        "key_env": ENV_KEY, "key_env_std": ENV_KEY_STD,
        "provider": "Liquid", "site": "liquid.ai",
        # sin verificar: no se declara un límite que no se midió
        "context_tokens": None, "overhead_tokens": 300,
        "price_in_per_m": PRICES[DEFAULT_MODEL], "price_out_per_m": 0.0, "approx_price": True,
        "models": list(MODELS), "default_model": DEFAULT_MODEL}

SPEC = {"id": "liquid", "base_url": DEFAULT_BASE_URL, "base_url_env": ENV_BASE_URL,
        "path": "/v1/systemone", "auth": "bearer", "zstd": False,
        "request_id_header": "x-request-id", "runtime_header": None,
        "root_fields": S.ROOT_FIELDS, "errors": "models", "max_body": MAX_BODY,
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


def model_info(model_id):
    """{"price_in_per_m"} del modelo (la pista de su fila en la lista de Modelos)."""
    return {"price_in_per_m": PRICES.get(str(model_id or ""))}


def live_meta():
    """El precio del modelo elegido (d1-ultra cuesta más)."""
    return {"price_in_per_m": PRICES.get(model(), PRICES[DEFAULT_MODEL])}


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
        meta = dict(META, **live_meta())
        return S.decide(SPEC, meta, req, key, base_url(), model(), _send)
    except Exception as e:                      # el contrato: jamás levantar
        return S.fail(SPEC, t0, "error", key, {"class": type(e).__name__})
