"""WORKSPACE · deciders/jev — Jev (TypeSafe AI), en la nube, SIN SDK.

Habla con la API de TypeSafe con la stdlib (http.client + json + ssl):
Workspace corre en Python 3.9+ y el SDK oficial pide 3.10+, así que no hay
nada que instalar; basta la llave. La petición es la MISMA que manda el SDK
oficial typesafe-sdk 0.7.5 (comparada byte a byte contra él:
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
import base64
import http.client
import json
import os
import platform
import re
import socket
import ssl
import sys
import time
import zlib
from urllib.parse import unquote, urlsplit

ENV_KEY = "TYPESAFE_API_KEY"
ENV_BASE_URL = "TYPESAFE_BASE_URL"
ENV_MODEL = "TYPESAFE_DEFAULT_MODEL"
DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"
SYSTEM_ONE_PATH = "/v1/systemone"
REQUEST_ID_HEADER = "x-typesafe-request-id"
#: Como el SDK: un cuerpo chico no se comprime (cabe en un paquete TCP).
MIN_COMPRESSED_BODY_LENGTH = 1024
#: Tope del tiempo de conexión (TCP + TLS): un host que no contesta en esto
#: es «sin conexión». La lectura usa lo que quede del tiempo de la petición.
CONNECT_TIMEOUT_S = 3.0
#: Topes de la respuesta: lo que se lee del socket y lo que puede crecer al
#: descomprimir (una «bomba» de 4 MB comprimidos se volvía GB).
_MAX_BODY = 4 * 1024 * 1024
_MAX_DECODED = 8 * 1024 * 1024
#: Sin https, la llave solo viaja a esta misma máquina (el simulador de la QA).
_LOOPBACK = ("localhost", "127.0.0.1", "::1")

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
    return ((os.environ.get(ENV_BASE_URL) or "").strip() or DEFAULT_BASE_URL).rstrip("/")


def model():
    return (os.environ.get(ENV_MODEL) or "").strip() or DEFAULT_MODEL


def _version():
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip() or "0"
    except Exception:
        return "0"


def _zstd():
    """El compresor zstd de la stdlib (Python 3.14+), o None."""
    try:
        from compression.zstd import compress   # 3.14+
        return compress
    except Exception:
        return None


def build_request(key, question, options, criteria, context, url=None):
    """La petición EXACTA (sin mandarla): {"method", "url", "headers", "json"
    (el cuerpo sin comprimir), "body" (lo que viaja)}. Pura: la usa la prueba
    de paridad contra lo que manda el SDK."""
    crit = criteria or {}
    payload = {"state": {"context": context or ""},
               "model": model(),
               "questions": {"q": {"type": "choice", "instructions": question,
                                   "criteria": {o: (crit.get(o) or None) for o in options}}}}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Authorization": "Bearer %s" % key,
               "Accept": "application/json",
               "Content-Type": "application/json",
               "Accept-Encoding": "gzip, deflate",
               "User-Agent": "workspace/%s (decisores)" % _version(),
               "X-TypeSafe-Runtime": "python/%s (%s; %s)" % (platform.python_version(),
                                                             sys.platform, platform.machine())}
    body = raw
    comp = _zstd() if len(raw) >= MIN_COMPRESSED_BODY_LENGTH else None
    if comp is not None:
        try:
            body = comp(raw)
            headers["Content-Encoding"] = "zstd"
        except Exception:
            body = raw
    return {"method": "POST", "url": (url or base_url()) + SYSTEM_ONE_PATH,
            "headers": headers, "json": raw, "body": body}


# ── la red ──────────────────────────────────────────────────────────────────
class NetFail(Exception):
    """Un fallo de red ya clasificado: code = connection | timeout | proxy."""

    def __init__(self, code, cls, phase, var=None):
        super().__init__(code)
        self.code, self.cls, self.phase, self.var = code, cls, phase, var


class ProxyInvalid(Exception):
    """Hay un proxy configurado pero no se puede usar tal como está escrito."""

    def __init__(self, var):
        super().__init__(var)
        self.var = var


_CTX = {}
_CA_FALLBACKS = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt",
                 "/etc/pki/tls/certs/ca-bundle.crt", "/usr/local/etc/openssl@3/cert.pem",
                 "/opt/homebrew/etc/openssl@3/cert.pem")


def ssl_context():
    """El contexto TLS (verifica siempre). Si este Python no trae ninguna CA
    (el de python.org en Mac sin «Install Certificates»), usa certifi o el
    archivo de CAs del sistema."""
    if "ctx" in _CTX:
        return _CTX["ctx"]
    ctx = ssl.create_default_context()
    try:
        vacio = not ctx.cert_store_stats().get("x509_ca")
    except Exception:
        vacio = True
    if vacio and not (os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR")):
        cands = []
        try:
            import certifi
            cands.append(certifi.where())
        except Exception:
            pass
        for p in cands + list(_CA_FALLBACKS):
            if p and os.path.isfile(p):
                try:
                    ctx.load_verify_locations(cafile=p)
                    break
                except Exception:
                    continue
    _CTX["ctx"] = ctx
    return ctx


#: Un host de proxy sano: nombre DNS, IPv4 o IPv6 (urlsplit le quita los corchetes).
_HOST_OK = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,62})(?:\.[A-Za-z0-9-]{1,63})*\.?"
                      r"|[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*)$")


def _proxy_var(scheme):
    """El NOMBRE de la variable que trae el proxy (para el mensaje; jamás su
    valor, que puede llevar usuario y contraseña). En Windows el entorno no
    distingue mayúsculas (os.environ.get("https_proxy") encuentra HTTPS_PROXY):
    ahí, el nombre de siempre, en mayúsculas."""
    n = scheme + "_proxy"
    if os.name == "nt":
        return n.upper()
    for v in (n, n.upper()):                      # urllib prefiere la minúscula
        if (os.environ.get(v) or "").strip():
            return v
    return n.upper()


def _proxy_for(scheme, host):
    """(host, port, Proxy-Authorization|None) del proxy configurado, o None
    si se va directo (no hay proxy, o NO_PROXY excluye este host). Un proxy
    configurado pero inválido NO se ignora: levanta ProxyInvalid."""
    import urllib.request
    # solo el ENTORNO (como el SDK): mismo resultado en Mac, Windows y Linux
    try:
        if urllib.request.proxy_bypass_environment(host):
            return None
    except Exception:
        pass
    try:
        raw = urllib.request.getproxies_environment().get(scheme)
    except Exception:
        raw = os.environ.get(scheme + "_proxy") or os.environ.get((scheme + "_proxy").upper())
    v = str(raw or "").strip()
    if not v:
        return None
    var = _proxy_var(scheme)
    try:
        u = urlsplit(v if "://" in v else "http://" + v)
        ph, pp = u.hostname, u.port                   # .port levanta si no es un número
    except ValueError:
        raise ProxyInvalid(var)
    sch = (u.scheme or "").lower()
    if sch not in ("http", "https") or not ph or not _HOST_OK.match(ph):
        raise ProxyInvalid(var)
    if pp is None:
        pp = 443 if sch == "https" else 80            # como urllib
    auth = None
    if u.username:
        cred = "%s:%s" % (unquote(u.username), unquote(u.password or ""))
        auth = "Basic " + base64.b64encode(cred.encode("utf-8")).decode("ascii")
    return ph, pp, auth


class TooLarge(ValueError):
    """La respuesta (ya descomprimida) pasaría de _MAX_DECODED."""


def _inflate(data, wbits):
    d = zlib.decompressobj(wbits)
    out = d.decompress(data, _MAX_DECODED)
    if d.unconsumed_tail or len(out) >= _MAX_DECODED:
        raise TooLarge("respuesta demasiado grande")
    return out + d.flush()


def _decode(data, enc):
    """El cuerpo según su Content-Encoding, con tope de tamaño al descomprimir."""
    enc = (enc or "").strip().lower()
    if enc == "gzip":
        return _inflate(data, 16 + zlib.MAX_WBITS)
    if enc == "deflate":
        try:
            return _inflate(data, zlib.MAX_WBITS)
        except zlib.error:
            return _inflate(data, -zlib.MAX_WBITS)
    if enc == "zstd":
        from compression import zstd      # solo si el servidor lo mandó sin pedirlo
        d = zstd.ZstdDecompressor()
        out = d.decompress(data, max_length=_MAX_DECODED)
        if len(out) >= _MAX_DECODED or not d.eof:
            raise TooLarge("respuesta demasiado grande")
        return out
    return data


def url_segura(url):
    """¿Se le puede mandar la llave a esta URL? https, o http solo a esta
    misma máquina (localhost / 127.0.0.1 / ::1: el simulador de la QA). Un
    TYPESAFE_BASE_URL con http:// a otro host mandaba la llave en claro."""
    try:
        u = urlsplit(url)
        host = (u.hostname or "").lower()
    except ValueError:
        return False
    if (u.scheme or "").lower() == "https" and host:
        return True
    return (u.scheme or "").lower() == "http" and host in _LOOPBACK


def send(req, timeout_s, connect_timeout_s=None):
    """Manda la petición → (status, {header en minúsculas: valor}, cuerpo).
    Conexión con su propio tiempo (corto); la lectura, con lo que quede.
    Levanta NetFail("connection" | "timeout", clase, fase)."""
    t0 = time.monotonic()
    total = max(0.2, float(timeout_s))
    ct = min(CONNECT_TIMEOUT_S if connect_timeout_s is None else connect_timeout_s, total * 0.6)
    u = urlsplit(req["url"])
    scheme = (u.scheme or "https").lower()
    host = u.hostname or ""
    port = u.port or (443 if scheme == "https" else 80)
    path = (u.path or "/") + ("?" + u.query if u.query else "")
    try:
        proxy = _proxy_for(scheme, host)
    except ProxyInvalid as e:                          # jamás directo saltándose un proxy
        raise NetFail("proxy", "ProxyInvalid", "config", var=e.var)
    try:
        if scheme == "https":
            if proxy:
                conn = http.client.HTTPSConnection(proxy[0], proxy[1], timeout=ct, context=ssl_context())
                conn.set_tunnel(host, port, headers={"Proxy-Authorization": proxy[2]} if proxy[2] else None)
            else:
                conn = http.client.HTTPSConnection(host, port, timeout=ct, context=ssl_context())
        else:
            if proxy:
                conn = http.client.HTTPConnection(proxy[0], proxy[1], timeout=ct)
                path = req["url"]                  # proxy HTTP: la URL completa
            else:
                conn = http.client.HTTPConnection(host, port, timeout=ct)
    except Exception as e:
        raise NetFail("connection", type(e).__name__, "connect")
    try:
        try:
            conn.connect()
        except socket.timeout:
            raise NetFail("connection", "timeout", "connect")     # el host no contestó
        except (OSError, http.client.HTTPException) as e:          # rechazo, DNS, TLS…
            raise NetFail("connection", type(e).__name__, "connect")
        restante = max(0.2, total - (time.monotonic() - t0))
        try:
            conn.sock.settimeout(restante)
        except Exception:
            pass
        headers = dict(req["headers"])
        headers["Content-Length"] = str(len(req["body"]))
        if proxy and scheme == "http" and proxy[2]:
            headers["Proxy-Authorization"] = proxy[2]
        try:
            conn.request(req["method"], path, body=req["body"], headers=headers)
            resp = conn.getresponse()
            data = resp.read(_MAX_BODY)
        except socket.timeout:
            raise NetFail("timeout", "timeout", "read")
        except (OSError, http.client.HTTPException) as e:
            raise NetFail("connection", type(e).__name__, "read")
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        try:
            data = _decode(data, hdrs.get("content-encoding"))
        except Exception:
            data = b""
        return resp.status, hdrs, data
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── errores y costo ─────────────────────────────────────────────────────────
#: Palabras del `error_type` que delatan falta de saldo (un 429
#: «insufficient_quota» es crédito, no prisa).
_PAYMENT = ("credit", "balance", "payment", "billing", "insufficient", "funds")
_TOO_LARGE = ("max_tokens", "too large", "too long", "context length", "maximum context",
              "token limit", "too many tokens", "payload")


def _json(data):
    try:
        return json.loads(data.decode("utf-8")) if data else None
    except Exception:
        return None


def error_type(body):
    """El `error_type` que manda TypeSafe ({"detail": {"error_type": …}})."""
    if isinstance(body, dict):
        for k in ("detail", "error"):
            v = body.get(k)
            if isinstance(v, dict):
                t = v.get("error_type") or v.get("type") or v.get("code")
                if t:
                    return str(t)
        t = body.get("error_type") or body.get("type") or body.get("code")
        if t:
            return str(t)
    return ""


def classify_http(status, body=None, text=""):
    """Código de un status HTTP que no es 200 (más su error_type)."""
    etype = error_type(body).lower()
    txt = ("%s %s %s" % (etype, json.dumps(body, ensure_ascii=False) if body else "", text)).lower()
    if status == 413 or (status in (400, 422) and any(k in txt for k in _TOO_LARGE)):
        return "context_too_large"
    if status == 402 or any(k in etype for k in _PAYMENT):
        return "payment"
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "rate_limit"
    if status == 404:
        return "not_found"
    if isinstance(status, int) and status >= 500:
        return "server"
    if isinstance(status, int) and 400 <= status < 500:
        return "bad_request"
    return "bad_response"


def cost(tokens):
    """Costo real (USD) de una llamada: uso × precio del META."""
    if not tokens:
        return None
    try:
        ins = float(tokens.get("in") or 0)
        out = float(tokens.get("out") or 0)
    except (TypeError, ValueError):
        return None
    return ins / 1e6 * META["price_in_per_m"] + out / 1e6 * META["price_out_per_m"]


def _scrub(txt, key=""):
    txt = str(txt or "")
    for k in (key, os.environ.get(ENV_KEY) or ""):
        if k and k in txt:                     # redactar ANTES de truncar
            txt = txt.replace(k, "•••")
    return txt


def _fail(t0, code, key="", detail=None):
    det = None
    if detail:
        det = {k: _scrub(v, key)[:160] if isinstance(v, str) else v
               for k, v in detail.items() if v is not None}
    return {"choice": None, "score": None, "probs": {},
            "ms": int((time.time() - t0) * 1000), "cost_usd": None,
            "decider": "jev", "ok": False, "error": code, "error_detail": det or None}


def parse(body):
    """(elección, probabilidades, tokens) de una respuesta 200; ValueError si
    no tiene la forma de la API."""
    if not isinstance(body, dict):
        raise ValueError("no es un objeto")
    a = (body.get("answers") or {}).get("q")
    if not isinstance(a, dict) or not isinstance(a.get("choice"), str):
        raise ValueError("answers.q.choice")
    probs = a.get("probabilities")
    if not isinstance(probs, dict) or not probs:
        # sin el mapa: solo la confianza de la elegida (si vino). Jamás 1.0 por
        # omisión: una certeza inventada hacía aplicar «decide» siempre
        conf = a.get("confidence")
        probs = {a["choice"]: float(conf)} if isinstance(conf, (int, float)) and not \
            isinstance(conf, bool) else {}
    out = {}
    for k, v in probs.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    probs = out
    u = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    tokens = None
    if u:
        tokens = {"in": u.get("input_tokens"), "out": u.get("output_tokens")}
    return a["choice"], probs, tokens


def decide(req):
    t0 = time.time()
    key = _key()
    if not key:
        return _fail(t0, "no_key")
    try:
        kind = req.get("kind") or "choice"
        opts = [str(o) for o in (req.get("options") or []) if str(o).strip()]
        if kind == "score" and not opts:
            opts = ["yes", "no"]
        if len(opts) < 2:
            return _fail(t0, "need_options", key)
        if not url_segura(base_url()):
            return _fail(t0, "insecure_url", key, {"var": ENV_BASE_URL})
        r = build_request(key, req.get("question") or "Which option applies?", opts,
                          req.get("criteria") or {}, req.get("context") or "")
        tmo = max(0.2, float(req.get("timeout_ms") or 1500) / 1000.0)
        try:
            status, hdrs, data = send(r, tmo)
        except NetFail as f:
            return _fail(t0, f.code, key, {"class": f.cls, "phase": f.phase, "var": f.var})
        body = _json(data)
        rid = hdrs.get(REQUEST_ID_HEADER)
        if status != 200:
            text = "" if body is not None else data[:300].decode("utf-8", "replace")
            return _fail(t0, classify_http(status, body, text), key,
                         {"status": status, "type": error_type(body) or None, "request_id": rid})
        try:
            choice, probs, tokens = parse(body)
        except (ValueError, TypeError, KeyError) as e:
            return _fail(t0, "bad_response", key, {"status": status, "class": type(e).__name__,
                                                   "request_id": rid})
        return {"choice": choice,
                "score": probs.get(opts[0], 0.0) if kind == "score" else None,
                "probs": probs, "ms": int((time.time() - t0) * 1000),
                "cost_usd": cost(tokens), "tokens": tokens, "decider": "jev", "ok": True,
                "error": None}
    except Exception as e:                      # el contrato: jamás levantar
        return _fail(t0, "error", key, {"class": type(e).__name__})
