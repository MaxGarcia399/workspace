"""WORKSPACE · deciders/_systemone — el cliente del protocolo System One, común.

System One (el protocolo de Jev, de TypeSafe) se volvió estándar de facto:
OpenRouter, Liquid y Ollama lo implementan tal cual (`state` + `questions` →
`answers.q.{choice, confidence, probabilities}` + `usage`). Aquí vive el
cliente UNA vez — con la stdlib (http.client + json + ssl), sin SDK — y cada
decisor es una FICHA de proveedor encima (deciders/jev.py, openrouter.py,
liquid.py, ollama.py). El `_` inicial = no es un decisor (no se lista).

La ficha (un dict):
  id                 el decisor ("jev", "openrouter"…): va en `decider` de la respuesta
  base_url           https://… por omisión;  base_url_env  la variable que la cambia
  path               "/v1/systemone"
  auth               "bearer" (Authorization: Bearer <llave>) | "none" (JAMÁS se manda)
  zstd               ¿comprimir con zstd (Python 3.14+) un cuerpo de 1 KB o más?
  request_id_header  el header con el id de la petición (para «d detalle»)
  runtime_header     un header con la versión de Python (TypeSafe) o None
  root_fields        campos permitidos en la RAÍZ del cuerpo (un campo de más da 400)
  errors             el clasificador de errores: "typesafe" (status + detail.error_type;
                     también OpenRouter y Liquid, con su respaldo por status) | "ollama"
                     ({"error": msg}: 404 = el modelo no está descargado…)
  key_envs           las variables con la llave (para tacharla de un error)
  key_own / key_std  la llave: nombre propio (entorno y bóveda) y la variable estándar
                     del proveedor (solo entorno) — ver read_key()
  max_body           tope del cuerpo que acepta el proveedor (bytes) o None
  usage_cost         ¿la respuesta trae `usage.cost` (el costo real)?

Sin reintentos ni redirecciones (http.client no las sigue). El tiempo de
CONEXIÓN es corto y va aparte del de lectura: un host que no contesta es «sin
conexión», no «tardó». Respeta HTTPS_PROXY y NO_PROXY (túnel CONNECT); un
proxy configurado pero MAL escrito no se ignora (eso mandaría directo,
saltándose el proxy): falla con el código «proxy»; uno https:// con
usuario y contraseña, también (no se abre TLS hacia el proxy: la contraseña
viajaría sin cifrar). Certificados: los del
sistema; si este Python no trae ninguno (el de python.org en Mac), certifi o
/etc/ssl/cert.pem. Una llave solo viaja por https (o por http a esta misma
máquina: el simulador de la QA). Jamás levanta hacia el decisor que la usa."""
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
#: Los campos de la raíz que manda cualquier proveedor System One.
ROOT_FIELDS = ("state", "model", "questions")


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


#: Lo que base_url devuelve cuando la variable pide otro destino para una
#: llave: una dirección que url_segura rechaza («insecure_url», sin conectar).
URL_RECHAZADA = "rechazada://override"


def base_url(spec):
    """La URL base, sin «/» final: la de fábrica o, si la ficha declara una
    variable y está puesta, esa — pero para un decisor CON llave solo si
    apunta a ESTA máquina (el simulador de la QA) o al mismo host de fábrica.
    Cualquier otro destino se rechaza (URL_RECHAZADA → «insecure_url», sin
    conectar): un agente dentro de un motor que pone
    `OPENROUTER_DECISIONS_BASE_URL=https://otro` y corre `workspace decidir`
    no puede mandarle la llave a otro host (revisión 2026-11-08)."""
    var = spec.get("base_url_env")
    v = (os.environ.get(var) or "").strip() if var else ""
    if not v:
        return spec["base_url"].rstrip("/")
    if spec.get("auth") != "none":
        try:
            host = (urlsplit(v).hostname or "").lower()
            fabrica = (urlsplit(spec["base_url"]).hostname or "").lower()
        except ValueError:
            return URL_RECHAZADA
        if host not in _LOOPBACK and host != fabrica:
            return URL_RECHAZADA
    return v.rstrip("/")


def build_request(spec, key, question, options, criteria, context, url=None, model="",
                  extra=None, compress=None):
    """La petición EXACTA (sin mandarla): {"method", "url", "headers", "json"
    (el cuerpo sin comprimir), "body" (lo que viaja)}. Pura: la usa la prueba
    de paridad contra lo que manda el SDK. `extra` = campos de raíz además de
    state/model/questions (solo los que la ficha permite, en `root_fields`).
    `compress` = la función de zstd (None = la de este Python; False = no)."""
    crit = criteria or {}
    payload = {"state": {"context": context or ""},
               "model": model,
               "questions": {"q": {"type": "choice", "instructions": question,
                                   "criteria": {o: (crit.get(o) or None) for o in options}}}}
    permitidos = tuple(spec.get("root_fields") or ROOT_FIELDS)
    for k, v in (extra or {}).items():
        if k in permitidos and k not in payload and v is not None:
            payload[k] = v
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {}
    if spec.get("auth", "bearer") == "bearer":
        headers["Authorization"] = "Bearer %s" % key
    headers.update({"Accept": "application/json",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "User-Agent": "workspace/%s (decisores)" % _version()})
    if spec.get("runtime_header"):
        headers[spec["runtime_header"]] = "python/%s (%s; %s)" % (platform.python_version(),
                                                                   sys.platform, platform.machine())
    body = raw
    comp = None
    if spec.get("zstd") and len(raw) >= MIN_COMPRESSED_BODY_LENGTH:
        comp = _zstd() if compress is None else (compress or None)
    if comp is not None:
        try:
            body = comp(raw)
            headers["Content-Encoding"] = "zstd"
        except Exception:
            body = raw
    return {"method": "POST", "url": (url or base_url(spec)) + spec["path"],
            "headers": headers, "json": raw, "body": body}


# ── la red ──────────────────────────────────────────────────────────────────
class NetFail(Exception):
    """Un fallo de red ya clasificado: code = connection | timeout | proxy."""

    def __init__(self, code, cls, phase, var=None):
        super().__init__(code)
        self.code, self.cls, self.phase, self.var = code, cls, phase, var


class ProxyInvalid(Exception):
    """Hay un proxy configurado pero no se puede usar tal como está escrito.
    `cls`: «ProxyInvalid» (mal escrito) o «ProxyHttpsAuth» (https:// con
    usuario y contraseña: ver _proxy_for)."""

    def __init__(self, var, cls="ProxyInvalid"):
        super().__init__(var)
        self.var, self.cls = var, cls


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
    if sch == "https" and u.username:
        # Workspace no abre TLS hacia el proxy: el CONNECT (con
        # Proxy-Authorization) saldría SIN cifrar antes del TLS al destino.
        # No se conecta; el mensaje lo dice (Greptile 0.8.x, 0).
        raise ProxyInvalid(var, cls="ProxyHttpsAuth")
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


def es_loopback(url):
    """¿La URL apunta a esta misma máquina (localhost / 127.0.0.1 / ::1)?"""
    try:
        return (urlsplit(url).hostname or "").lower() in _LOOPBACK
    except ValueError:
        return False


def url_segura(url):
    """¿Se le puede mandar la llave a esta URL? https, o http solo a esta
    misma máquina (localhost / 127.0.0.1 / ::1: el simulador de la QA). Una
    URL base con http:// a otro host mandaba la llave en claro."""
    try:
        u = urlsplit(url)
        host = (u.hostname or "").lower()
    except ValueError:
        return False
    if (u.scheme or "").lower() == "https" and host:
        return True
    return (u.scheme or "").lower() == "http" and host in _LOOPBACK


def url_valida(url):
    """¿Es una URL http(s) con host? (para un decisor SIN llave: no hay nada
    que proteger en el camino, pero una dirección rota no se intenta)."""
    try:
        u = urlsplit(url)
        u.port                                      # levanta si el puerto no es un número
        return (u.scheme or "").lower() in ("http", "https") and bool(u.hostname)
    except ValueError:
        return False


def send(req, timeout_s, connect_timeout_s=None, proxy=True):
    """Manda la petición → (status, {header en minúsculas: valor}, cuerpo).
    Conexión con su propio tiempo (corto); la lectura, con lo que quede.
    Levanta NetFail("connection" | "timeout", clase, fase). `proxy=False` =
    directo aunque haya HTTP(S)_PROXY (un servidor en esta misma máquina: el
    proxy no lo alcanza y vería el contexto)."""
    t0 = time.monotonic()
    total = max(0.2, float(timeout_s))
    ct = min(CONNECT_TIMEOUT_S if connect_timeout_s is None else connect_timeout_s, total * 0.6)
    u = urlsplit(req["url"])
    scheme = (u.scheme or "https").lower()
    host = u.hostname or ""
    port = u.port or (443 if scheme == "https" else 80)
    path = (u.path or "/") + ("?" + u.query if u.query else "")
    try:
        # A esta misma máquina, JAMÁS por un proxy (aunque quien llama lo
        # pida): el http a loopback va en claro y el proxy vería la llave y
        # el contexto (revisión 2026-11-08, reproducido con un proxy de red).
        proxy = _proxy_for(scheme, host) if proxy and host.lower() not in _LOOPBACK else None
    except ProxyInvalid as e:                          # jamás directo saltándose un proxy
        raise NetFail("proxy", e.cls, "config", var=e.var)
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


def get_json(url, timeout_s, connect_timeout_s=0.3, method="GET", payload=None, proxy=True):
    """Una consulta chica (JSON) sin llave — el estado de un servidor local:
    → (status, cuerpo JSON o None). Levanta NetFail como send()."""
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    hdrs = {"Accept": "application/json", "User-Agent": "workspace/%s (decisores)" % _version()}
    if payload is not None:
        hdrs["Content-Type"] = "application/json"
    st, _h, data = send({"method": method, "url": url, "headers": hdrs, "body": body},
                        timeout_s, connect_timeout_s, proxy=proxy)
    return st, _json(data)


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
    """Código de un status HTTP que no es 200 (más su error_type) — TypeSafe;
    OpenRouter y Liquid usan el mismo (su respaldo es el status)."""
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


def ollama_message(body, text=""):
    """El texto del error de Ollama ({"error": "…"})."""
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return body["error"]
    return str(text or "")


def classify_ollama(status, body=None, text=""):
    """Ollama: {"error": msg}. 404 = el modelo no está descargado; 400 con
    «context» = no cupo (no recorta nunca); 400 «… is not a … decision model» o
    «unsupported model» = ese modelo no es de decisión (`not_decision`); 413 =
    más de 64 KiB de texto. Lo demás, por status (como TypeSafe)."""
    msg = ollama_message(body, text).lower()
    if status == 404:
        return "not_found"
    if status == 413 or (status == 400 and "context" in msg):
        return "context_too_large"
    if status == 400 and _NOT_DECISION.search(msg):
        return "not_decision"                       # un modelo de chat: /systemone lo rechaza
    return classify_http(status, body, text)


#: El proveedor dice que ese modelo NO es de decisión (uno de chat, p. ej.:
#: Ollama 0.40.15 responde 400 «model "smollm2:135m" is not a llama.cpp
#: decision model»).
_NOT_DECISION = re.compile(r"not\s+(?:a|an)\s+(?:[\w.\-]+\s+){0,3}decision\s+model"
                           r"|unsupported\s+model|does\s+not\s+support\s+(?:decisions?|systemone)"
                           r"|only\s+(?:supports\s+)?decision\s+models", re.I)
#: El proveedor no encuentra el MODELO (un id que no existe o que no sirve ahí).
_BAD_MODEL = re.compile(r"model\b[^.]{0,80}?\b(?:not\s+found|does\s+not\s+exist|is\s+not\s+a\s+valid"
                        r"|not\s+available)|(?:not\s+a\s+valid|invalid|unknown)\s+model"
                        r"|no\s+endpoints\s+found",
                        re.I)


def _error_text(body, text=""):
    return "%s %s" % (json.dumps(body, ensure_ascii=False) if body else "", text or "")


def classify_models(status, body=None, text=""):
    """OpenRouter y Liquid: como TypeSafe, pero un 400/404/422 POR EL MODELO dice
    qué pasó — «no es de decisión» (`not_decision`) o «no lo encuentra»
    (`not_found`) —, no un «rechazó la pregunta» genérico."""
    code = classify_http(status, body, text)
    if code in ("bad_request", "not_found"):
        txt = _error_text(body, text)
        if _NOT_DECISION.search(txt):
            return "not_decision"
        if _BAD_MODEL.search(txt):
            return "not_found"
    return code


def classify(spec, status, body=None, text=""):
    if spec.get("errors") == "ollama":
        return classify_ollama(status, body, text)
    if spec.get("errors") == "models":
        return classify_models(status, body, text)
    return classify_http(status, body, text)


def _por_el_modelo(spec, code, body, text):
    """¿El fallo es por el MODELO elegido? (para decir cuál en el mensaje)."""
    if code == "not_decision":
        return True
    if code == "not_found" and spec.get("errors") == "models":
        return bool(_BAD_MODEL.search(_error_text(body, text)))
    return False


def cost(meta, tokens):
    """Costo real (USD) de una llamada: uso × precio del META (None sin precio)."""
    if not tokens:
        return None
    if meta.get("local"):
        return 0.0
    pin, pout = meta.get("price_in_per_m"), meta.get("price_out_per_m")
    if pin is None:
        return None
    try:
        ins = float(tokens.get("in") or 0)
        out = float(tokens.get("out") or 0)
        return ins / 1e6 * float(pin) + out / 1e6 * float(pout or 0.0)
    except (TypeError, ValueError):
        return None


def usage_cost(body):
    """El costo REAL que dice la respuesta (`usage.cost`, OpenRouter), o None."""
    try:
        c = (body.get("usage") or {}).get("cost")
    except AttributeError:
        return None
    if isinstance(c, bool) or not isinstance(c, (int, float)):
        return None
    c = float(c)
    return c if c == c and 0 <= c < float("inf") else None


def scrub(txt, keys=()):
    txt = str(txt or "")
    for k in keys:
        if k and k in txt:                     # redactar ANTES de truncar
            txt = txt.replace(k, "•••")
    return txt


def _keys_of(spec, key=""):
    out = [key]
    for var in spec.get("key_envs") or ():
        out.append(os.environ.get(var) or "")
    return tuple(k for k in out if k)


def fail(spec, t0, code, key="", detail=None):
    keys = _keys_of(spec, key)
    det = None
    if detail:
        det = {k: scrub(v, keys)[:160] if isinstance(v, str) else v
               for k, v in detail.items() if v is not None}
    return {"choice": None, "score": None, "probs": {},
            "ms": int((time.time() - t0) * 1000), "cost_usd": None,
            "decider": spec["id"], "ok": False, "error": code, "error_detail": det or None}


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
        # un bool (`true` sería 1.0) o algo que no es número vuelve INVÁLIDA
        # la respuesta (bad_response: nada se aplica); antes se convertía o
        # se descartaba en silencio y la regla de decisions._clean no lo veía
        # (revisor sobre ed793cd8, B). Un número en texto sigue valiendo.
        if isinstance(v, bool):
            raise ValueError("probabilities: bool")
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            raise ValueError("probabilities: no numérica")
    probs = out
    u = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    tokens = None
    if u:
        tokens = {"in": u.get("input_tokens"), "out": u.get("output_tokens")}
    return a["choice"], probs, tokens


# ── la llave (nombre propio, la variable del proveedor, la bóveda) ──────────
def _cargada_por_la_boveda(name):
    """¿Esta variable la puso en el entorno la bóveda (load_into_env, la llave
    de un PROVEEDOR de motores)? Esa no es «del entorno del sistema»: un motor
    no la hereda, así que un hook tampoco la vería."""
    try:
        import secret_store
        return name in secret_store.loaded_names()
    except Exception:
        return False


def key_source(spec):
    """(origen, variable) de la llave, en el orden en que se lee:
    ("env", <nombre propio>) → ("env", <variable estándar del proveedor>) →
    ("store", <nombre propio>) → ("", ""). La bóveda guarda SIEMPRE con el
    nombre propio (WORKSPACE_DECIDER_<ID>_KEY): con el estándar, quitaría del
    entorno de Hermes, OpenClaw u opencode la OPENROUTER_API_KEY que el socio
    exportó con el mismo valor (secret_store._strip_for_engine)."""
    own, std = spec.get("key_own") or "", spec.get("key_std") or ""
    if own and (os.environ.get(own) or "").strip():
        return "env", own
    if std and (os.environ.get(std) or "").strip() and not _cargada_por_la_boveda(std):
        return "env", std
    if own:
        try:
            import secret_store
            if (secret_store.get(own) or "").strip():
                return "store", own
        except Exception:
            pass
    return "", ""


def read_key(spec):
    """La llave según key_source() (jamás se imprime ni se anota)."""
    src, var = key_source(spec)
    if src == "env":
        return (os.environ.get(var) or "").strip()
    if src == "store":
        try:
            import secret_store
            return (secret_store.get(var) or "").strip()
        except Exception:
            return ""
    return ""


# ── decidir (lo común a todos los System One) ───────────────────────────────
def decide(spec, meta, req, key, url, model, send_fn, extra=None, need_key=True):
    """La llamada completa: valida, arma, manda, clasifica y lee. `send_fn`
    = la función que manda (el decisor pasa la SUYA: las pruebas la
    simulan ahí). Jamás levanta: cualquier problema → ok False + un código."""
    t0 = time.time()
    if need_key and not key:
        return fail(spec, t0, "no_key")
    try:
        kind = req.get("kind") or "choice"
        opts = [str(o) for o in (req.get("options") or []) if str(o).strip()]
        if kind == "score" and not opts:
            opts = ["yes", "no"]
        if len(opts) < 2:
            return fail(spec, t0, "need_options", key)
        if spec.get("auth", "bearer") == "bearer":
            if not url_segura(url):
                return fail(spec, t0, "insecure_url", key, {"var": spec.get("base_url_env")})
        elif not url_valida(url):
            return fail(spec, t0, "connection", key, {"class": "BadURL", "phase": "config",
                                                       "var": spec.get("base_url_env")})
        r = build_request(spec, key, req.get("question") or "Which option applies?", opts,
                          req.get("criteria") or {}, req.get("context") or "", url=url,
                          model=model, extra=extra)
        if spec.get("max_body") and len(r["body"]) > int(spec["max_body"]):
            return fail(spec, t0, "context_too_large", key, {"reason": "body_limit",
                                                             "bytes": len(r["body"])})
        tmo = max(0.2, float(req.get("timeout_ms") or 1500) / 1000.0)
        try:
            status, hdrs, data = send_fn(r, tmo)
        except NetFail as f:
            return fail(spec, t0, f.code, key, {"class": f.cls, "phase": f.phase, "var": f.var})
        body = _json(data)
        rid = hdrs.get(spec.get("request_id_header") or "x-request-id")
        if status != 200:
            text = "" if body is not None else data[:300].decode("utf-8", "replace")
            etype = error_type(body) or None
            if spec.get("errors") == "ollama":
                etype = ollama_message(body, text)[:80] or None
            code = classify(spec, status, body, text)
            det = {"status": status, "type": etype, "request_id": rid}
            if _por_el_modelo(spec, code, body, text):
                det.update(model=model, reason="model")
            return fail(spec, t0, code, key, det)
        try:
            choice, probs, tokens = parse(body)
        except (ValueError, TypeError, KeyError) as e:
            return fail(spec, t0, "bad_response", key, {"status": status, "class": type(e).__name__,
                                                        "request_id": rid})
        real = usage_cost(body) if spec.get("usage_cost") else None
        return {"choice": choice,
                "score": probs.get(opts[0], 0.0) if kind == "score" else None,
                "probs": probs, "ms": int((time.time() - t0) * 1000),
                "cost_usd": real if real is not None else cost(meta, tokens),
                "tokens": tokens, "decider": spec["id"], "ok": True, "error": None}
    except Exception as e:                      # el contrato: jamás levantar
        return fail(spec, t0, "error", key, {"class": type(e).__name__})


# ── el modelo elegido (decisions.decider_models) ────────────────────────────
#: Un modelo SOLO para este proceso (el chequeo en vivo mide uno sin cambiar
#: el que eligió el socio): {decisor: modelo}.
MODEL_OVERRIDE = {}


def saved_model(did):
    """El modelo que el socio eligió para este decisor (ajuste
    `decisions.decider_models`), crudo: '' si no hay. Falla-suave."""
    if MODEL_OVERRIDE.get(did):
        return str(MODEL_OVERRIDE[did])
    try:
        import settings
        v = (settings.get("decisions.decider_models") or {}).get(did)
        return str(v or "").strip()
    except Exception:
        return ""


def chosen_model(did, models, default):
    """El guardado si está en la lista del decisor; si no, el de fábrica."""
    v = saved_model(did)
    return v if v and v in models else default
