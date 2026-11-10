"""WORKSPACE · deciders/jev — Jev (TypeSafe AI), en la nube, SIN SDK.

Habla con la API de TypeSafe con la stdlib (http.client + json + ssl):
Workspace corre en Python 3.9+ y el SDK oficial pide 3.10+, así que no hay
nada que instalar; basta la llave. El cliente del protocolo (System One) vive
en deciders/_systemone.py, común a los decisores que lo hablan; esto es la
FICHA de TypeSafe encima. La petición es la MISMA que manda el SDK oficial
typesafe-sdk 0.7.5 (comparada byte a byte contra él:
tests/fixtures/decisores/typesafe_systemone_0.7.5.json):

  POST {TYPESAFE_BASE_URL o https://api.typesafe.ai}/v1/systemone
  Authorization: Bearer <llave> · Accept: application/json ·
  Content-Type: application/json (· Content-Encoding: zstd si este Python
  lo trae —3.14+— y el cuerpo pasa de 1 KB, igual que el SDK)
  {"state":{"context":…},"model":"jev-latest","questions":{"q":{"type":
   "choice","instructions":…,"criteria":{opción: descripción|null}}}}
  → {"model", "answers": {"q": {"type": "choice", "choice", "confidence",
     "probabilities"}}, "usage": {"input_tokens", "output_tokens"}}

Sin reintentos. El tiempo de CONEXIÓN es corto y va aparte del de lectura:
un host que no contesta es «sin conexión», no «tardó». Respeta HTTPS_PROXY y
NO_PROXY (túnel CONNECT); un proxy configurado pero MAL escrito no se ignora
(eso mandaría directo, saltándose el proxy): falla con el código «proxy».
Certificados: los del sistema; si este Python no trae ninguno (el de
python.org en Mac), certifi o /etc/ssl/cert.pem.

La llave sale, en este orden, del entorno (TYPESAFE_API_KEY) o de la bóveda
de Workspace (la guarda «conectar llave» en Motores → Modelos de decisión).
Jamás se imprime, se anota ni pasa al entorno de un motor.

Errores: `error` es un CÓDIGO por status HTTP y `detail.error_type`
(context_too_large · auth · payment · rate_limit · not_found · server ·
bad_request · bad_response · timeout · connection · proxy · no_key ·
need_options · error) y `error_detail` lleva status, tipo, request_id (o la clase del error
de red y la fase: connect / read) — para la bitácora y «d detalle», nunca
para el mensaje principal (decision_errors.py lo vuelve palabras)."""
import http.client  # noqa: F401  (las pruebas simulan jev.http.client)
import os
import time

from deciders import _systemone as S

ENV_KEY = "TYPESAFE_API_KEY"
ENV_BASE_URL = "TYPESAFE_BASE_URL"
ENV_MODEL = "TYPESAFE_DEFAULT_MODEL"
DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"
SYSTEM_ONE_PATH = "/v1/systemone"
REQUEST_ID_HEADER = "x-typesafe-request-id"

# lo del protocolo, desde la base común (las pruebas y otros módulos lo usan así)
MIN_COMPRESSED_BODY_LENGTH = S.MIN_COMPRESSED_BODY_LENGTH
CONNECT_TIMEOUT_S = S.CONNECT_TIMEOUT_S
_MAX_BODY = S._MAX_BODY
_MAX_DECODED = S._MAX_DECODED
_LOOPBACK = S._LOOPBACK
_PAYMENT = S._PAYMENT
_TOO_LARGE = S._TOO_LARGE
NetFail = S.NetFail
ProxyInvalid = S.ProxyInvalid
TooLarge = S.TooLarge
_CTX = S._CTX
ssl_context = S.ssl_context
_proxy_var = S._proxy_var
_proxy_for = S._proxy_for
_inflate = S._inflate
_decode = S._decode
url_segura = S.url_segura
send = S.send
_json = S._json
error_type = S.error_type
classify_http = S.classify_http
parse = S.parse
_version = S._version
_zstd = S._zstd

META = {"id": "jev", "label": "Jev", "local": False,
        "kinds": ["choice", "score"], "offer": True, "key_env": ENV_KEY,
        "provider": "TypeSafe", "site": "typesafe.ai",
        # MEDIDO con llamadas reales: el límite de entrada es ~32 768 tokens
        # (2026-11-06) y una llamada sin contexto gasta ~300 (301 con una
        # pregunta corta y 2 opciones, 2026-11-07).
        "context_tokens": 32768, "overhead_tokens": 300,
        # Precio APROXIMADO (agregadores de terceros): ~$0.042 por millón de
        # tokens de entrada; la salida no se cobra.
        "price_in_per_m": 0.042, "price_out_per_m": 0.0, "approx_price": True}

#: La ficha de TypeSafe para la base común (deciders/_systemone.py).
SPEC = {"id": "jev", "base_url": DEFAULT_BASE_URL, "base_url_env": ENV_BASE_URL,
        "path": SYSTEM_ONE_PATH, "auth": "bearer", "zstd": True,
        "request_id_header": REQUEST_ID_HEADER, "runtime_header": "X-TypeSafe-Runtime",
        "root_fields": S.ROOT_FIELDS, "errors": "typesafe", "key_envs": (ENV_KEY,)}


def _key():
    """La llave: la del entorno del sistema gana; si no, la de la bóveda."""
    k = (os.environ.get(ENV_KEY) or "").strip()
    if k:
        return k
    try:
        import secret_store
        return (secret_store.get(ENV_KEY) or "").strip()
    except Exception:
        return ""


def status():
    if not _key():
        return {"ready": False, "detail": "no_key"}
    return {"ready": True, "detail": "cloud"}


def base_url():
    return S.base_url(SPEC)


def model():
    return (os.environ.get(ENV_MODEL) or "").strip() or DEFAULT_MODEL


def build_request(key, question, options, criteria, context, url=None):
    """La petición EXACTA (sin mandarla): {"method", "url", "headers", "json"
    (el cuerpo sin comprimir), "body" (lo que viaja)}. Pura: la usa la prueba
    de paridad contra lo que manda el SDK."""
    return S.build_request(SPEC, key, question, options, criteria, context,
                           url=url or base_url(), model=model(), compress=_zstd() or False)


def cost(tokens):
    """Costo real (USD) de una llamada: uso × precio del META."""
    return S.cost(META, tokens)


def _scrub(txt, key=""):
    return S.scrub(txt, (key, os.environ.get(ENV_KEY) or ""))


def _fail(t0, code, key="", detail=None):
    return S.fail(SPEC, t0, code, key, detail)


def _send(req, timeout_s):
    # el `send` de ESTE módulo, buscado al llamar (las pruebas lo simulan aquí)
    return send(req, timeout_s)


def decide(req):
    t0 = time.time()
    key = _key()
    if not key:
        return _fail(t0, "no_key")
    try:
        return S.decide(SPEC, META, req, key, base_url(), model(), _send)
    except Exception as e:                      # el contrato: jamás levantar
        return _fail(t0, "error", key, {"class": type(e).__name__})
