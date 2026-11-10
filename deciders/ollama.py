"""WORKSPACE · deciders/ollama — modelos de decisión EN ESTA COMPUTADORA (Ollama).

Ollama ≥ 0.35.0 habla System One («decision models through /v1/systemone,
based on TypeSafe's Jev API»): el mismo protocolo que Jev
(deciders/_systemone.py), sin llave y sin salir de la máquina.

  POST {OLLAMA_HOST o http://127.0.0.1:11434}/v1/systemone
  {"state", "model": "<descargado>", "questions", "keep_alive": "30m"}
  → answers.q.{choice, confidence, probabilities} + usage
  errores {"error": "…"}: 404 el modelo no está descargado · 400 contexto
  excedido (Ollama no recorta nunca) o modelo no soportado · 413 más de 64 KiB

  · SIN LLAVE: jamás se manda Authorization (ni una llave de otro proveedor).
  · El modelo se elige entre los DESCARGADOS (GET /api/tags) que son DE
    DECISIÓN: lo dice `/api/show` ("capabilities": ["decision"]; respaldo: las
    familias conocidas). Los de chat ni se ofrecen ni se guardan (se cuentan
    para la pantalla); un guardado que ya no sirve cae solo al primero de
    decisión. Los de licencia no comercial (nimble-v3, OpenJev) ni se listan.
    Tres barreras: la lista · guardar valida (decisions.check_model) · el
    endpoint rechaza los de chat (400 → `not_decision`, falla cerrado).
  · status() es barato: conexión ≤ 0.3 s, lectura corta y un caché de unos
    segundos (después se refresca en segundo plano): no instalado · apagado ·
    versión < 0.35.0 (GET /api/version) · sin modelo de decisión · listo.
  · El límite de contexto sale del modelo (POST /api/show, en caché): la
    ventana que Ollama carga (`num_ctx`), nunca más que la del modelo; sin
    dato, 4096.
  · FRÍO: cargar el modelo no cabe en 1.5 s. `keep_alive` en cada petición lo
    deja cargado; warm() lo precarga en segundo plano (Probar y encender un uso
    lo llaman). Un tiempo agotado con el modelo sin cargar (GET /api/ps) es
    «loading» (cargando el modelo), no «sin conexión» ni la pausa de 60 s.
  · Un OLLAMA_HOST de otra máquina ya no es «en esta computadora»: live_meta()
    lo marca `local: False` (y entonces sí hay aviso de que el contenido sale).

Las pruebas (y quien no quiera sondear) apagan el sondeo con
WORKSPACE_NO_LOCAL_PROBE=1: status() y warm() no tocan la red."""
import os
import re
import shutil
import threading
import time

from deciders import _systemone as S

ENV_HOST = "OLLAMA_HOST"
ENV_NO_PROBE = "WORKSPACE_NO_LOCAL_PROBE"
DEFAULT_PORT = 11434
MIN_VERSION = (0, 35, 0)
KEEP_ALIVE = "30m"
DEFAULT_CONTEXT = 4096
#: Sondeos del estado: rápidos o nada.
PROBE_CONNECT_S = 0.3
PROBE_READ_S = 0.6
STATUS_TTL_S = 5.0
SHOW_TTL_S = 600.0
WARM_TIMEOUT_S = 180.0
#: Familias de modelos de DECISIÓN conocidas (ollama.com/library).
DECISION_FAMILIES = ("nimble", "tev1", "kev", "d3", "strands-decider", "clef-flash",
                     "pplx-decider-flash", "d1", "laya", "autotrust-jev")
#: Licencia NO comercial (CC BY-NC): ni se listan.
_NO_COMERCIAL = re.compile(r"^(?:nimble-v3(?:$|[-.])|.*openjev)", re.I)
#: El primero que se sugiere descargar.
SUGERIDO = "nimble"

META = {"id": "ollama", "label": "Ollama", "local": True,
        "kinds": ["choice", "score"], "offer": True,
        "provider": "Ollama", "site": "ollama.com",
        "context_tokens": DEFAULT_CONTEXT, "overhead_tokens": 300,
        "price_in_per_m": 0.0, "price_out_per_m": 0.0, "approx_price": False,
        "dynamic_models": True}

SPEC = {"id": "ollama", "base_url": "http://127.0.0.1:%d" % DEFAULT_PORT,
        "base_url_env": ENV_HOST, "path": "/v1/systemone", "auth": "none", "zstd": False,
        "request_id_header": "x-request-id", "runtime_header": None,
        "root_fields": S.ROOT_FIELDS + ("keep_alive",), "errors": "ollama", "key_envs": ()}

_LOCK = threading.Lock()
_CACHE = {"status": None, "at": 0.0, "refreshing": False, "show": {}, "gen": 0, "hilo": None}
_COLD = {}
_WARMING = set()


def _reset():
    """Para las pruebas: olvida el caché."""
    with _LOCK:
        _CACHE.update(status=None, at=0.0, refreshing=False, show={}, gen=_CACHE["gen"] + 1)
        _COLD.clear()
        _WARMING.clear()


def invalidate():
    """El estado en caché ya no vale (el socio eligió otro modelo): el
    siguiente status() vuelve a mirar. Un refresco en curso no lo pisa."""
    with _LOCK:
        _CACHE.update(status=None, at=0.0, refreshing=False, gen=_CACHE["gen"] + 1)


# ── la dirección (OLLAMA_HOST, como la lee el propio Ollama) ────────────────
def base_url():
    """http://127.0.0.1:11434, o lo que diga OLLAMA_HOST: «host», «host:puerto»,
    «http(s)://host[:puerto]». Sin esquema, el puerto es 11434; con http://
    y sin puerto, 80 (como Ollama). 0.0.0.0 (escuchar en todas) = esta máquina."""
    v = (os.environ.get(ENV_HOST) or "").strip().rstrip("/")
    if not v:
        return SPEC["base_url"]
    if "://" in v:
        scheme, rest = v.split("://", 1)
        scheme = scheme.lower()
        defport = {"http": 80, "https": 443}.get(scheme, DEFAULT_PORT)
    else:
        scheme, rest, defport = "http", v, DEFAULT_PORT
    rest = rest.split("/", 1)[0]
    host, port = rest, None
    if rest.startswith("["):                                   # [::1]:11434
        fin = rest.find("]")
        host = rest[1:fin] if fin > 0 else rest.strip("[]")
        tail = rest[fin + 1:] if fin > 0 else ""
        port = tail[1:] if tail.startswith(":") else None
    elif rest.count(":") == 1:
        host, port = rest.split(":", 1)
    host = host or "127.0.0.1"
    if host in ("0.0.0.0", "*"):
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    hostfmt = "[%s]" % host if ":" in host else host
    return "%s://%s:%s" % (scheme, hostfmt, port or defport)


def remote():
    """¿OLLAMA_HOST apunta a OTRA máquina? (entonces no es «en esta computadora»)."""
    return not S.es_loopback(base_url())


def live_meta():
    """Lo del META que depende de esta máquina: el límite de contexto del modelo
    elegido (del caché de /api/show; jamás red aquí) y si es local de verdad."""
    out = {}
    m = _chosen_cached()
    show = _CACHE["show"].get(m) if m else None
    if show and show[1]:
        out["context_tokens"] = int(show[1])
    if remote():
        out["local"] = False
    return out


# ── sondeos (rápidos) ────────────────────────────────────────────────────────
def _probe_off():
    return os.environ.get(ENV_NO_PROBE) == "1"


def _get(path, payload=None, connect_s=PROBE_CONNECT_S, read_s=PROBE_READ_S):
    """GET/POST chico a Ollama → (status, JSON|None). Directo (sin proxy) si es
    esta máquina. Levanta NetFail."""
    url = base_url() + path
    return S.get_json(url, connect_s + read_s, connect_s, method="POST" if payload else "GET",
                      payload=payload, proxy=remote())


def _version_tuple(v):
    m = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?", str(v or ""))
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def _instalado():
    """¿Hay un Ollama en esta máquina, aunque esté apagado? (el programa en el
    PATH o la app de Mac / Windows)."""
    if shutil.which("ollama"):
        return True
    cands = ["/Applications/Ollama.app", os.path.expanduser("~/Applications/Ollama.app")]
    la = os.environ.get("LOCALAPPDATA")
    if la:
        cands.append(os.path.join(la, "Programs", "Ollama", "ollama.exe"))
    return any(os.path.exists(c) for c in cands)


def familia(name):
    """«nimble» de «usuario/nimble:latest»."""
    base = str(name or "").split("/")[-1]
    return base.split(":", 1)[0].lower()


def es_de_decision(name):
    """¿Es un modelo de decisión? La señal PRINCIPAL es la de Ollama: `/api/show`
    trae `"capabilities": ["decision"]` (Ollama 0.40.15 la da para nimble). Solo
    si no se pudo preguntar (o no trae `capabilities`), por la familia conocida."""
    hit = _CACHE["show"].get(name) or _CACHE["show"].get(_norm(name))
    if hit and hit[2] is not None:
        return "decision" in hit[2]
    f = familia(name)
    return any(f == x or f.startswith(x + "-") for x in DECISION_FAMILIES)


def no_comercial(name):
    return bool(_NO_COMERCIAL.match(familia(name)))


def _norm(name):
    """«nimble» y «nimble:latest» son el mismo modelo."""
    n = str(name or "").strip()
    return n if ":" in n.split("/")[-1] else (n + ":latest" if n else n)


def normalize_model(name):
    """El nombre canónico de un modelo de Ollama («nimble» → «nimble:latest»): la
    fachada lo usa al guardar, al validar el ajuste y en el chequeo en vivo."""
    return _norm(name)


def _tags(show_budget_s=0.0, prefer=""):
    """TODOS los descargados: [{"id", "decision"}] (los de chat también: para
    contarlos y para decir por qué uno no sirve; elegibles son SOLO los de
    decisión, ver _de_decision). Con `show_budget_s`, pregunta a `/api/show`
    por sus `capabilities` (en caché) hasta agotar ese tiempo — `prefer`
    primero —; los que no alcanzaron, por la familia."""
    st, body = _get("/api/tags")
    if st != 200 or not isinstance(body, dict):
        return []
    nombres = []
    for it in body.get("models") or []:
        if not isinstance(it, dict):
            continue
        n = str(it.get("name") or it.get("model") or "").strip()
        if n and not no_comercial(n) and n not in nombres:
            nombres.append(n)
    pref = {prefer, _norm(prefer)} - {""}
    fin = time.time() + max(0.0, float(show_budget_s or 0))
    for n in sorted(nombres, key=lambda x: x not in pref):
        resta = fin - time.time()
        if resta > 0.05:
            _show_info(n, read_s=min(PROBE_READ_S, resta))
    out = [{"id": n, "decision": es_de_decision(n)} for n in nombres]
    out.sort(key=lambda x: (not x["decision"], _rango(x["id"]), x["id"]))
    return out


def _de_decision(todos):
    """Solo los de DECISIÓN: lo único que se ofrece, se guarda o se usa."""
    return [x for x in todos if x["decision"]]


def _rango(name):
    """El orden de las familias de decisión (la primera, la mejor medida por su
    autor): el modelo de fábrica es el primero que esté descargado."""
    f = familia(name)
    for i, x in enumerate(DECISION_FAMILIES):
        if f == x or f.startswith(x + "-"):
            return i
    return len(DECISION_FAMILIES)


def _context_of(show):
    """La ventana de contexto de /api/show: `num_ctx` de sus parámetros (lo que
    Ollama carga), nunca más que la del modelo (`<arch>.context_length`); sin
    num_ctx, la de fábrica (4096) o la del modelo si es menor."""
    if not isinstance(show, dict):
        return None
    trained = 0
    for k, v in (show.get("model_info") or {}).items():
        if str(k).endswith(".context_length"):
            try:
                trained = int(v)
            except (TypeError, ValueError):
                pass
    num_ctx = 0
    m = re.search(r"(?m)^\s*num_ctx\s+(\d+)", str(show.get("parameters") or ""))
    if m:
        num_ctx = int(m.group(1))
    if num_ctx:
        return min(num_ctx, trained) if trained else num_ctx
    return min(DEFAULT_CONTEXT, trained) if trained else DEFAULT_CONTEXT


def _capabilities(show):
    """Las `capabilities` de /api/show (["decision"], ["completion"]…) o None si
    no las trae."""
    caps = show.get("capabilities") if isinstance(show, dict) else None
    if not isinstance(caps, list):
        return None
    return [str(c).strip().lower() for c in caps if str(c).strip()]


def _show_info(model, read_s=PROBE_READ_S):
    """(límite de contexto, capabilities) del modelo, de /api/show, en caché
    largo. (None, None) si no se pudo."""
    now = time.time()
    hit = _CACHE["show"].get(model)
    if hit and now - hit[0] < SHOW_TTL_S:
        return hit[1], hit[2]
    try:
        st, body = _get("/api/show", payload={"model": model}, read_s=read_s)
        n, caps = (_context_of(body), _capabilities(body)) if st == 200 else (None, None)
    except S.NetFail:
        n, caps = None, None
    _CACHE["show"][model] = (now, n, caps)
    return n, caps


def _show(model):
    """El límite del modelo (caché largo). None si no se pudo."""
    return _show_info(model)[0]


def _probe():
    """El estado REAL (con red, acotada). Un dict de status()."""
    try:
        st, ver = _get("/api/version")
    except S.NetFail as f:
        if f.code == "proxy":
            return {"ready": False, "detail": "ollama_off"}
        if remote():
            return {"ready": False, "detail": "ollama_off", "host": "remote"}
        return {"ready": False, "detail": "ollama_off" if _instalado() else "ollama_missing"}
    version = str((ver or {}).get("version") or "") if isinstance(ver, dict) else ""
    vt = _version_tuple(version)
    if st == 200 and vt is not None and vt < MIN_VERSION:
        return {"ready": False, "detail": "ollama_old", "version": version}
    saved = S.saved_model(META["id"])
    try:
        todos = _tags(show_budget_s=1.0, prefer=saved)
    except S.NetFail:
        return {"ready": False, "detail": "ollama_off"}
    lista = _de_decision(todos)
    chat = [x["id"] for x in todos if not x["decision"]]
    out = {"version": version, "models": lista, "chat_models": len(chat), "_chat": chat}
    m = _pick(lista)
    if not m:
        out.update(ready=False, detail="no_model")
        return out
    out.update(ready=True, detail="local", model=m)
    if saved and m not in (saved, _norm(saved)):
        # el guardado ya no sirve: se usa el primero de decisión, sin esperar a nadie,
        # y la pantalla lo dice en una línea
        out["fallback"] = {"from": saved,
                           "why": "not_decision" if (saved in chat or _norm(saved) in chat)
                           else "missing"}
    _show(m)
    return out


def _refresh():
    gen = _CACHE["gen"]
    try:
        st = _probe()
    except Exception as e:
        st = {"ready": False, "detail": "ollama_off", "error": type(e).__name__}
    with _LOCK:
        if gen == _CACHE["gen"]:                 # nadie lo invalidó mientras tanto
            _CACHE.update(status=st, at=time.time(), refreshing=False)
    return st


#: Lo más que status() hace esperar a quien pregunta (s): la pantalla se
#: pinta en el hilo del render y no puede congelarse aunque Ollama tarde
#: (cargando un modelo grande). Lo que falte se termina en segundo plano.
STATUS_ESPERA_S = 0.3


def status(espera=None):
    """Barato y SIN congelar a quien pregunta: el caché (≤ STATUS_TTL_S);
    vencido, se refresca en SEGUNDO PLANO y responde el anterior; sin caché,
    el sondeo arranca en segundo plano y se espera como mucho
    STATUS_ESPERA_S (0.3 s): si no terminó, {"ready": False, "detail":
    "checking"} («comprobando…») y la siguiente pintada ya lo trae."""
    if _probe_off():
        return {"ready": False, "detail": "ollama_missing"}
    espera = STATUS_ESPERA_S if espera is None else espera
    with _LOCK:
        st, at, busy = _CACHE["status"], _CACHE["at"], _CACHE["refreshing"]
        vencido = st is None or (time.time() - at) >= STATUS_TTL_S
        lanzar = vencido and not busy
        if lanzar:
            _CACHE["refreshing"] = True
            _CACHE["hilo"] = threading.Thread(target=_refresh, daemon=True, name="ollama-status")
        hilo = _CACHE.get("hilo")
    if lanzar:
        hilo.start()
    if st is None and hilo is not None:
        hilo.join(max(0.0, float(espera)))
        with _LOCK:
            st = _CACHE["status"]
    if st is None:
        return {"ready": False, "detail": "checking"}
    return dict(st)


# ── el modelo ────────────────────────────────────────────────────────────────
def _pick(lista):
    """El elegido entre los de DECISIÓN: el guardado si es uno de ellos; si no
    (uno de chat, o ya no está descargado), el primero. Uno de chat jamás."""
    ids = [x["id"] for x in lista if x.get("decision")]
    saved = S.saved_model(META["id"])
    for cand in (saved, _norm(saved)):
        if cand and cand in ids:
            return cand
    return ids[0] if ids else ""


def model_kind(name):
    """Qué es `name` en este Ollama (del estado en caché): "decision" · "chat"
    (descargado, pero no es de decisión) · "no_comercial" · "missing" (no está
    descargado) · "unknown" (Ollama no respondió: no se puede saber)."""
    n = _norm(name)
    if no_comercial(n):
        return "no_comercial"
    st = status()
    if "models" not in st:
        return "unknown"
    if n in [x["id"] for x in st.get("models") or []] or name in [x["id"] for x in st.get("models") or []]:
        return "decision"
    if n in (st.get("_chat") or []) or name in (st.get("_chat") or []):
        return "chat"
    return "missing"


def pull_cmd(model_id=None):
    """El siguiente paso para tener un modelo: «ollama pull nimble»."""
    return "ollama pull %s" % (str(model_id or "").strip() or SUGERIDO)


def models():
    """Los modelos que se pueden elegir: SOLO los de decisión [{"id",
    "decision": True}] (del estado; sin sondeo si no se puede). Los de chat no
    se ofrecen: status()["chat_models"] los cuenta."""
    st = status()
    return [dict(x) for x in (st.get("models") or []) if x.get("decision")]


def default_model():
    ms = models()
    return ms[0]["id"] if ms else ""


def _chosen_cached():
    st = _CACHE.get("status") or {}
    return st.get("model") or ""


def _elegir():
    """(modelo, NetFail|None): el guardado si está descargado; si no (o si no
    hay uno guardado), el primero de decisión que haya. Con la lista en caché
    (status) no hay red; sin ella, una consulta a /api/tags (esta máquina). Si
    no se puede saber, el guardado tal cual (si no está descargado, Ollama
    responde 404 y el mensaje dice cómo bajarlo) y el fallo de red."""
    saved = S.saved_model(META["id"])
    st = _CACHE.get("status") or {}
    if "models" in st:
        return st.get("model") or "", None
    if _probe_off():
        return saved, None
    try:
        # saber cuáles son de decisión (capabilities; el guardado primero), con
        # poco tiempo: es el camino de una pregunta
        return _pick(_de_decision(_tags(show_budget_s=0.25, prefer=saved))), None
    except S.NetFail as f:
        return saved, f
    except Exception:
        return saved, None


def model():
    """El modelo con el que se decide ('' si no hay ninguno)."""
    return _elegir()[0]


# ── frío: precargar y saber si está cargado ──────────────────────────────────
def _loaded(timeout_s=0.5):
    """Los modelos YA cargados en memoria (GET /api/ps), o None si no se supo."""
    try:
        st, body = _get("/api/ps", connect_s=min(PROBE_CONNECT_S, timeout_s), read_s=timeout_s)
    except S.NetFail:
        return None
    if st != 200 or not isinstance(body, dict):
        return None
    out = set()
    for it in body.get("models") or []:
        if isinstance(it, dict):
            for k in ("name", "model"):
                if it.get(k):
                    out.add(_norm(it[k]))
    return out


def _warm_request(m):
    req = S.build_request(SPEC, "", "warm-up", ["a", "b"], {}, "", url=base_url(), model=m,
                          extra={"keep_alive": KEEP_ALIVE})
    try:
        S.send(req, WARM_TIMEOUT_S, 1.0, proxy=remote())
    except Exception:
        pass
    finally:
        with _LOCK:
            _WARMING.discard(m)


def warm(model_id=None):
    """Precarga el modelo en SEGUNDO PLANO (una petición mínima con
    keep_alive). Regresa enseguida: True si arrancó la precarga."""
    if _probe_off():
        return False
    m = model_id or model()
    if not m:
        return False
    with _LOCK:
        if m in _WARMING:
            return False
        _WARMING.add(m)
    threading.Thread(target=_warm_request, args=(m,), daemon=True, name="ollama-warm").start()
    return True


def timeout_code(req=None):
    """Lo que significa un tiempo agotado AHORA (la fachada pregunta al vencer
    su tiempo límite; sin red): «loading» si la última pregunta encontró el
    modelo sin cargar."""
    return "loading" if _COLD.get("last") else "timeout"


# ── decidir ──────────────────────────────────────────────────────────────────
def _sin_la_ruta(det):
    """¿El 404 es de un Ollama que no tiene /v1/systemone (< 0.35.0)? Su 404 es
    el «404 page not found» de Go, no {"error": "model … not found"}; o el
    estado en caché ya decía que la versión es vieja."""
    if "page not found" in str(det.get("type") or "").lower():
        return True
    return (_CACHE.get("status") or {}).get("detail") == "ollama_old"



def _fail(t0, code, detail=None):
    return S.fail(SPEC, t0, code, "", detail)


def _send(req, timeout_s):
    return S.send(req, timeout_s, proxy=remote())


def decide(req):
    t0 = time.time()
    try:
        m, red = _elegir()
        if not m and red is not None:          # no es que falte el modelo: no hay Ollama
            return _fail(t0, red.code, {"class": red.cls, "phase": red.phase, "var": red.var})
        if not m:
            return _fail(t0, "no_model")
        hit = _CACHE["show"].get(m) or _CACHE["show"].get(_norm(m))
        if hit and hit[2] is not None and "decision" not in hit[2]:
            # Ollama ya dijo que no es de decisión: ni se pregunta (falla cerrado)
            return _fail(t0, "not_decision", {"model": m, "reason": "model"})
        cargados = _loaded()
        frio = cargados is not None and _norm(m) not in cargados
        _COLD["last"] = frio
        if frio:
            warm(m)               # que termine de cargar aunque esta pregunta se rinda
        req = dict(req)
        gastado = (time.time() - t0) * 1000.0
        req["timeout_ms"] = max(200, float(req.get("timeout_ms") or 1500) - gastado)
        r = S.decide(SPEC, META, req, "", base_url(), m, _send,
                     extra={"keep_alive": KEEP_ALIVE}, need_key=False)
        if not r.get("ok"):
            det = dict(r.get("error_detail") or {})
            if r.get("error") == "not_found" and _sin_la_ruta(det):
                det["reason"] = "old_version"        # no es el modelo: es un Ollama viejo
            if r.get("error") == "timeout" and frio:
                r["error"] = "loading"
                det["loading"] = True
            if r.get("error") in ("not_found", "bad_request", "loading", "context_too_large",
                                  "not_decision"):
                det["model"] = m
            r["error_detail"] = det or None
        if r.get("ok"):
            _COLD["last"] = False
        r["ms"] = int((time.time() - t0) * 1000)
        return r
    except Exception as e:                      # el contrato: jamás levantar
        return _fail(t0, "error", {"class": type(e).__name__})
