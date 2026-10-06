#!/usr/bin/env python3
"""WORKSPACE · gcal — los Google Calendar del socio, en SOLO LECTURA.

Es la fuente REMOTA que se fusiona con la agenda local (`personal.py`) en el
layout `dia` del hub y en `calendario_tui`. Lee la «dirección secreta en
formato iCal» que Google da por calendario — una URL con token embebido, así
que ES UN SECRETO y se trata como tal.

MULTI-CUENTA (desde 2026-10): el socio puede vincular VARIOS calendarios de
Google (p. ej. personal + trabajo). El modelo es una LISTA de cuentas:

    {"id": str, "label": str, "url": str, "kind": "ical"}

    · La LISTA vive en la bóveda per-máquina (`secret_store`) bajo el nombre
      WORKSPACE_GCAL_ACCOUNTS, como un JSON de UNA línea — las URLs con token
      SIGUEN siendo secretas: nunca se versionan, nunca se imprimen.
    · `kind` es el SEAM para una futura cuenta de dos vías (OAuth): hoy solo
      existe "ical"; el resto del harness ya tolera el campo.
    · Compatibilidad: la URL ÚNICA de antes (secreto WORKSPACE_GCAL_ICS_URL, o
      el env del sistema que GANA) sigue funcionando. Si el env trae esa URL,
      es la cuenta "default" (el env manda, igual que siempre). Si solo estaba
      guardada en la bóveda, se MIGRA sola a la lista como cuenta "default" sin
      que el socio pierda la conexión.
    · JAMÁS se imprime una URL completa: solo el host (el path lleva el token).
    · Se exige https — una URL file:// o http:// no se toca.

CONTRATO con el hub (por qué está diseñado así):
  · `events()` / `events_on()` / `events_month()` NUNCA tocan la red: MERGEAN
    el caché de disco de TODAS las cuentas y, si alguna está vieja, disparan UN
    hilo daemon por cuenta que refresca en segundo plano. El render del hub
    (redraw cada ~0.5 s) no se puede congelar por un DNS lento.
  · Cada evento sale ETIQUETADO con su origen: `source` (id de la cuenta) y
    `source_label` (su nombre), para poder colorear/distinguir.
  · FALLA-SUAVE absoluta: sin cuentas, sin red, ICS corrupto → lista vacía o el
    caché viejo que haya. La agenda local sigue igual; nada levanta.
  · Los eventos salen en la MISMA forma que personal.events() —
    {"id","date","time","title","cat","notes","archived"} — más
    {"google": True, "source": id, "source_label": label} para que la vista
    los distinga y los editores los protejan (solo lectura).

Caché de disco (`~/.claude/workspace/gcal_cache.local.json`): un JSON
`{"accounts": {<id>: {"fetched","sig","ics"}}}`, una entrada por cuenta. El
formato VIEJO (plano `{"fetched","sig","ics"}`) se sigue leyendo como la cuenta
"default" y se migra al vuelo en el siguiente refresh.

Parser ICS propio, mínimo y honesto (RFC 5545, el subconjunto que Google
emite): unfolding, VEVENT (SUMMARY · DTSTART/DTEND con TZID/VALUE=DATE/Z ·
STATUS), RRULE básica (DAILY/WEEKLY/MONTHLY/YEARLY + INTERVAL/COUNT/UNTIL/
BYDAY semanal), EXDATE y overrides por RECURRENCE-ID. Lo que no se entiende
se degrada a la ocurrencia base — nunca se inventa una fecha.

CLI:
    python3 gcal.py status        → resumen de TODAS las cuentas vinculadas
    python3 gcal.py accounts      → lista de cuentas (id · label · host · estado)
    python3 gcal.py add           → vincula una cuenta (prompt oculto de la URL)
    python3 gcal.py remove <id>   → desvincula una cuenta
    python3 gcal.py rename <id> X  → renombra una cuenta
    python3 gcal.py refresh       → fetch SÍNCRONO de todas (para probar)
    python3 gcal.py list          → próximos eventos (todas las cuentas)
    python3 gcal.py set-url        → (compat) vincula/actualiza la cuenta default
    python3 gcal.py clear-url      → (compat) desvincula la cuenta default
    python3 gcal.py clear-cache    → borra el caché local

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

URL_VAR = "WORKSPACE_GCAL_ICS_URL"        # secreto de la URL ÚNICA (compat/env)
ACCOUNTS_VAR = "WORKSPACE_GCAL_ACCOUNTS"  # secreto de la LISTA de cuentas (JSON)
DEFAULT_ID = "default"                    # id de la cuenta ÚNICA (env/compat)
FETCH_TTL = 15 * 60                       # el feed se considera fresco 15 min
FETCH_TIMEOUT = 10                        # segundos de red, y solo en el hilo
MAX_ICS_BYTES = 5 * 1024 * 1024           # un calendario no pesa más que esto
WINDOW_BACK = 370                         # expansión de RRULE: hoy ± ~1 año
WINDOW_FWD = 370
_MEMO_TTL = 30.0                          # memo en proceso (render barato)

_memo = {"ts": 0.0, "sig": None, "events": []}
_fetch_lock = threading.Lock()            # single-flight del refresh por cuenta
_fetching = {}                            # id de cuenta → bool «ya refrescando»
_migrated = [False]                       # migración URL única → lista (1×/proc)


# ── ubicación / secreto ─────────────────────────────────────────────────────
def _workspace_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def cache_path():
    """`.local.json` ⇒ doblemente fuera del repo (vive en ~/.claude y el
    patrón está gitignoreado). `WORKSPACE_GCAL_CACHE` lo pisa (tests)."""
    return (os.environ.get("WORKSPACE_GCAL_CACHE")
            or os.path.join(_workspace_dir(), "gcal_cache.local.json"))


def _env_url():
    """La URL iCal única en el env del sistema (GANA sobre la bóveda, misma
    regla que toda credencial del harness). "" si no hay. NUNCA loguear."""
    return (os.environ.get(URL_VAR) or "").strip()


def _store_url():
    """La URL iCal única guardada en la bóveda (formato VIEJO). "" si no hay."""
    try:
        import secret_store
        return (secret_store.get(URL_VAR) or "").strip()
    except Exception:
        return ""


def url():
    """Compat: la URL iCal «principal» (env → bóveda vieja → 1ª cuenta de la
    lista). "" si no hay ninguna. NUNCA loguear lo que devuelve esto."""
    u = _env_url() or _store_url()
    if u:
        return u
    accts = _persisted_accounts()
    return accts[0]["url"] if accts else ""


def _url_ok(u):
    """Solo https con host — ni file://, ni http:// plano, ni cadenas raras."""
    try:
        p = urllib.parse.urlparse(u)
        return p.scheme == "https" and bool(p.netloc)
    except Exception:
        return False


def _url_display(u):
    """Forma IMPRIMIBLE de la URL: solo el host (el path lleva el token)."""
    try:
        return urllib.parse.urlparse(u).netloc or "(url inválida)"
    except Exception:
        return "(url inválida)"


def _url_sig(u):
    """Huella de la URL para invalidar el caché si el socio cambia de calendario —
    sin guardar la URL misma en el caché."""
    return hashlib.sha256((u or "").encode("utf-8", "replace")).hexdigest()[:16]


# ── modelo de cuentas (lista en la bóveda) ──────────────────────────────────
def _persisted_accounts():
    """La LISTA de cuentas guardada en la bóveda (ACCOUNTS_VAR, JSON). Falla-
    suave → []. Normaliza cada cuenta a {id,label,url,kind}; descarta basura."""
    try:
        import secret_store
        raw = (secret_store.get(ACCOUNTS_VAR) or "").strip()
    except Exception:
        raw = ""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    out = []
    for a in (data if isinstance(data, list) else []):
        if not isinstance(a, dict):
            continue
        u, aid = str(a.get("url") or "").strip(), str(a.get("id") or "").strip()
        if not u or not aid:
            continue
        out.append({"id": aid,
                    "label": str(a.get("label") or _url_display(u))[:60],
                    "url": u,
                    "kind": str(a.get("kind") or "ical")})
    return out


def _save_accounts(accts):
    """Persiste la lista (solo {id,label,url,kind}) como JSON de una línea en la
    bóveda. Lista vacía → borra el secreto. True si quedó guardado."""
    try:
        import secret_store
    except Exception:
        return False
    clean = [{"id": a["id"], "label": a["label"], "url": a["url"],
              "kind": a.get("kind", "ical")} for a in accts]
    if not clean:
        try:
            secret_store.remove(ACCOUNTS_VAR)
            return True
        except Exception:
            return False
    try:
        blob = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
        return bool(secret_store.set_secret(ACCOUNTS_VAR, blob).get("ok"))
    except Exception:
        return False


def _ensure_migrated():
    """Migra la URL ÚNICA guardada en la bóveda (formato viejo) a la LISTA, como
    cuenta "default", sin perder la conexión. NO toca el env (ese sigue siendo
    la cuenta default en vivo). Idempotente y falla-suave; corre 1× por proceso
    (invalidate() lo resetea para los tests)."""
    if _migrated[0]:
        return
    _migrated[0] = True
    try:
        import secret_store
        if (secret_store.get(ACCOUNTS_VAR) or "").strip():
            return                                   # ya está en formato lista
        old = _store_url()
        if not old or not _url_ok(old):
            return
        acc = {"id": DEFAULT_ID, "label": "Principal", "url": old,
               "kind": "ical"}
        if not _save_accounts([acc]):
            return
        # funde el caché plano viejo bajo la nueva cuenta "default"
        raw = _cache_load_raw()
        if raw and isinstance(raw.get("ics"), str) and not raw.get("accounts"):
            _cache_put(DEFAULT_ID, raw["ics"],
                       raw.get("sig") or _url_sig(old))
        try:
            secret_store.remove(URL_VAR)             # ya vive en la lista
        except Exception:
            pass
    except Exception:
        pass


def _all_accounts():
    """TODAS las cuentas activas, en orden. El env de la URL única (si está)
    es la cuenta "default" y GANA su lugar (igual que siempre el env manda);
    cualquier cuenta persistida con esa misma URL o ese id queda a la sombra."""
    _ensure_migrated()
    accts = list(_persisted_accounts())
    env = _env_url()
    if env and _url_ok(env):
        accts = [a for a in accts
                 if a["url"] != env and a["id"] != DEFAULT_ID]
        accts = [{"id": DEFAULT_ID, "label": "Principal", "url": env,
                  "kind": "ical", "_env": True}] + accts
    return accts


def _env_owns_default():
    """True si la cuenta "default" la respalda el env (no es persistida) — no
    se puede quitar/renombrar desde aquí (se cambia la variable del sistema)."""
    env = _env_url()
    return bool(env and _url_ok(env))


# ── caché de disco (por cuenta) ──────────────────────────────────────────────
def _cache_load_raw():
    """El JSON crudo del caché (formato nuevo {"accounts":{…}} o el viejo plano
    {"fetched","sig","ics"}). Falla-suave → None."""
    try:
        with open(cache_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _cache_for(acc_id):
    """La entrada de caché {"fetched","sig","ics"} de UNA cuenta, o None. El
    caché VIEJO plano se interpreta como la cuenta "default" (compat)."""
    raw = _cache_load_raw()
    if not raw:
        return None
    accs = raw.get("accounts")
    if isinstance(accs, dict):
        e = accs.get(acc_id)
        return e if isinstance(e, dict) and isinstance(e.get("ics"), str) \
            else None
    if acc_id == DEFAULT_ID and isinstance(raw.get("ics"), str):
        return raw
    return None


def _write_cache(obj):
    """Escribe el JSON del caché atómico + chmod 0600. Falla-suave → False."""
    try:
        os.makedirs(_workspace_dir(), exist_ok=True)
        dest = cache_path()
        tmp = "%s.tmp-%d" % (dest, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, dest)
        return True
    except Exception:
        return False


def _cache_put(acc_id, ics_text, sig):
    """Guarda/actualiza la entrada de UNA cuenta, preservando las demás y
    migrando un caché plano viejo a la nueva forma. True si quedó en disco."""
    raw = _cache_load_raw() or {}
    accs = raw.get("accounts")
    if not isinstance(accs, dict):
        accs = {}
        if isinstance(raw.get("ics"), str):          # funde el plano viejo
            accs[DEFAULT_ID] = {"fetched": raw.get("fetched"),
                                "sig": raw.get("sig"), "ics": raw["ics"]}
    accs[acc_id] = {"fetched": time.time(), "sig": sig, "ics": ics_text}
    return _write_cache({"accounts": accs})


def _cache_drop(acc_id):
    """Quita la entrada de caché de UNA cuenta (al desvincularla)."""
    raw = _cache_load_raw()
    if not raw:
        return
    accs = raw.get("accounts")
    if isinstance(accs, dict) and acc_id in accs:
        accs.pop(acc_id, None)
        _write_cache({"accounts": accs})
    elif acc_id == DEFAULT_ID and isinstance(raw.get("ics"), str):
        _write_cache({"accounts": {}})               # tira el plano viejo


# ── fetch (solo el hilo de fondo o el CLI lo llaman) ───────────────────────
def _fetch(u, timeout=FETCH_TIMEOUT):
    """Baja el ICS. Devuelve el texto o None. No levanta."""
    if not _url_ok(u):
        return None
    try:
        req = urllib.request.Request(
            u, headers={"User-Agent": "workspace-hub/1.0 (calendar reader)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(MAX_ICS_BYTES + 1)
        if len(raw) > MAX_ICS_BYTES:
            return None
        text = raw.decode("utf-8", "replace")
        # sanidad mínima: si no parece un iCalendar no pisa el caché bueno
        if "BEGIN:VCALENDAR" not in text[:2000]:
            return None
        return text
    except Exception:
        return None


def refresh_account(acc, force=False, timeout=FETCH_TIMEOUT):
    """Fetch SÍNCRONO de UNA cuenta. True si su caché quedó fresco."""
    u = acc.get("url") or ""
    if not _url_ok(u):
        return False
    sig = _url_sig(u)
    if not force:
        c = _cache_for(acc["id"])
        if c and c.get("sig") == sig \
                and time.time() - float(c.get("fetched") or 0) < FETCH_TTL:
            return True
    text = _fetch(u, timeout=timeout)
    if text is None:
        return False
    return _cache_put(acc["id"], text, sig)


def refresh(force=False, timeout=FETCH_TIMEOUT):
    """Fetch SÍNCRONO de TODAS las cuentas (CLI / pruebas). True si todas
    quedaron frescas (o no hay cuentas)."""
    ok = True
    for acc in _all_accounts():
        ok = refresh_account(acc, force=force, timeout=timeout) and ok
    return ok


def _refresh_bg(acc):
    """Refresca UNA cuenta en un hilo daemon, una corrida a la vez por cuenta.
    Jamás bloquea."""
    aid = acc["id"]
    with _fetch_lock:
        if _fetching.get(aid):
            return
        _fetching[aid] = True

    def _run():
        try:
            refresh_account(acc)
        finally:
            _fetching[aid] = False

    try:
        threading.Thread(target=_run, name="gcal-refresh-%s" % aid,
                         daemon=True).start()
    except Exception:
        _fetching[aid] = False


# ── parser ICS ──────────────────────────────────────────────────────────────
def _unfold(text):
    """RFC 5545 §3.1: una línea que sigue con espacio/tab continúa la
    anterior. Devuelve la lista de líneas lógicas."""
    out = []
    for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if ln[:1] in (" ", "\t") and out:
            out[-1] += ln[1:]
        else:
            out.append(ln)
    return out


def _unescape(s):
    return (s.replace("\\n", " · ").replace("\\N", " · ")
             .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\"))


def _prop(line):
    """`DTSTART;TZID=X:20260929T180000` → ("DTSTART", {"TZID":"X"}, valor).
    Línea sin `:` → None."""
    if ":" not in line:
        return None
    head, val = line.split(":", 1)
    parts = head.split(";")
    name = parts[0].strip().upper()
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip()
    return name, params, val.strip()


def _tz(tzid):
    """ZoneInfo(tzid) o None (sin tzdata / tzid raro → hora naive, honesto)."""
    if not tzid:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tzid.strip('"'))
    except Exception:
        return None


def _parse_dt(val, params):
    """Valor DATE/DATE-TIME de ICS → (datetime LOCAL naive, all_day: bool).
    UTC (`Z`) y TZID se convierten a la hora local de ESTA máquina; una hora
    floating se toma tal cual. Ilegible → (None, False)."""
    v = (val or "").strip()
    if params.get("VALUE") == "DATE" or re.match(r"^\d{8}$", v):
        try:
            return _dt.datetime.strptime(v[:8], "%Y%m%d"), True
        except Exception:
            return None, False
    m = re.match(r"^(\d{8})T(\d{6})(Z?)$", v)
    if not m:
        return None, False
    try:
        base = _dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except Exception:
        return None, False
    if m.group(3) == "Z":
        aware = base.replace(tzinfo=_dt.timezone.utc)
    else:
        z = _tz(params.get("TZID"))
        if z is None:
            return base, False                      # floating/local: tal cual
        aware = base.replace(tzinfo=z)
    try:
        return aware.astimezone().replace(tzinfo=None), False
    except Exception:
        return base, False


def parse_ics(text):
    """Texto ICS → lista de VEVENTs crudos:
    {"uid","summary","start","end","all_day","rrule","exdates","recur_id",
     "cancelled"}. Nunca levanta; lo ilegible se omite."""
    evs, cur = [], None
    for ln in _unfold(text or ""):
        s = ln.strip()
        if s == "BEGIN:VEVENT":
            cur = {"uid": "", "summary": "", "start": None, "end": None,
                   "all_day": False, "rrule": "", "exdates": set(),
                   "recur_id": None, "cancelled": False}
            continue
        if s == "END:VEVENT":
            if cur and cur["start"] is not None:
                evs.append(cur)
            cur = None
            continue
        if cur is None:
            continue
        p = _prop(s)
        if not p:
            continue
        name, params, val = p
        if name == "SUMMARY":
            cur["summary"] = _unescape(val)[:120].strip()
        elif name == "UID":
            cur["uid"] = val[:120]
        elif name == "DTSTART":
            cur["start"], cur["all_day"] = _parse_dt(val, params)
        elif name == "DTEND":
            cur["end"], _ = _parse_dt(val, params)
        elif name == "RRULE":
            cur["rrule"] = val
        elif name == "EXDATE":
            for piece in val.split(","):
                d, _ad = _parse_dt(piece, params)
                if d is not None:
                    cur["exdates"].add(d.strftime("%Y%m%d%H%M"))
        elif name == "RECURRENCE-ID":
            d, _ad = _parse_dt(val, params)
            if d is not None:
                cur["recur_id"] = d
        elif name == "STATUS" and val.upper() == "CANCELLED":
            cur["cancelled"] = True
    return evs


# ── expansión de RRULE (subconjunto, acotada a la ventana) ─────────────────
_BYDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _parse_rrule(s):
    out = {}
    for part in (s or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().upper()] = v.strip()
    return out


def _rrule_matches(freq, start_d, d, interval, bydays):
    """¿El día `d` es una ocurrencia de la regla anclada en `start_d`?"""
    if d < start_d:
        return False
    if freq == "DAILY":
        return (d - start_d).days % interval == 0
    if freq == "WEEKLY":
        monday = lambda x: x - _dt.timedelta(days=x.weekday())   # noqa: E731
        weeks = (monday(d) - monday(start_d)).days // 7
        if weeks % interval != 0:
            return False
        wanted = bydays if bydays else {start_d.weekday()}
        return d.weekday() in wanted
    if freq == "MONTHLY":
        if d.day != start_d.day:
            return False
        months = (d.year - start_d.year) * 12 + (d.month - start_d.month)
        return months % interval == 0
    if freq == "YEARLY":
        if (d.month, d.day) != (start_d.month, start_d.day):
            return False
        return (d.year - start_d.year) % interval == 0
    return False


def _expand(ev, win_a, win_b, skip_dates):
    """Ocurrencias de UN VEVENT dentro de [win_a, win_b] (fechas date).
    Devuelve lista de (date, "HH:MM" | ""). `skip_dates` = fechas con
    override RECURRENCE-ID de su mismo UID (las pinta el override)."""
    start = ev["start"]
    hhmm = "" if ev["all_day"] else start.strftime("%H:%M")
    start_d = start.date()
    out = []

    def _emit(d):
        if win_a <= d <= win_b and d not in skip_dates \
                and d.strftime("%Y%m%d") + ("0000" if ev["all_day"]
                                            else start.strftime("%H%M")) \
                not in ev["exdates"]:
            out.append((d, hhmm))

    rr = _parse_rrule(ev["rrule"]) if ev["rrule"] else None
    if not rr or "FREQ" not in rr:
        # sin recurrencia: la ocurrencia base; un all-day multi-día pinta
        # cada día del rango (DTEND exclusivo), acotado por cordura
        if ev["all_day"] and ev["end"] is not None:
            end_d = ev["end"].date()                 # exclusivo en VALUE=DATE
            d, n = start_d, 0
            while d < end_d and n < 60:
                _emit(d)
                d += _dt.timedelta(days=1)
                n += 1
            if not out and win_a <= start_d <= win_b:
                _emit(start_d)
        else:
            _emit(start_d)
        return out

    freq = rr.get("FREQ", "").upper()
    try:
        interval = max(1, int(rr.get("INTERVAL", "1")))
    except Exception:
        interval = 1
    count = None
    if rr.get("COUNT"):
        try:
            count = max(1, int(rr["COUNT"]))
        except Exception:
            count = None
    until = None
    if rr.get("UNTIL"):
        u, _ad = _parse_dt(rr["UNTIL"], {})
        if u is not None:
            until = u.date()
    bydays = set()
    for tok in (rr.get("BYDAY") or "").split(","):
        tok = tok.strip().upper()
        if tok[-2:] in _BYDAY and (len(tok) == 2 or freq == "WEEKLY"):
            bydays.add(_BYDAY[tok[-2:]])
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        _emit(start_d)                               # regla exótica → honesto
        return out

    # COUNT obliga a contar desde el ancla; sin COUNT basta desde la ventana
    d = start_d if count is not None else max(start_d, win_a)
    stop = min(win_b, until) if until is not None else win_b
    seen, guard = 0, 0
    while d <= stop and guard < 20000:
        guard += 1
        if _rrule_matches(freq, start_d, d, interval, bydays):
            seen += 1
            _emit(d)
            if count is not None and seen >= count:
                break
        d += _dt.timedelta(days=1)
    return out


def _expand_ics(text):
    """Texto ICS → lista de (uid, date, "HH:MM"|"", summary) dentro de la
    ventana (hoy ± ~1 año), con overrides por RECURRENCE-ID aplicados. Nunca
    levanta; lo ilegible se omite."""
    hoy = _dt.date.today()
    win_a = hoy - _dt.timedelta(days=WINDOW_BACK)
    win_b = hoy + _dt.timedelta(days=WINDOW_FWD)
    raw = parse_ics(text)
    overrides = {}                        # uid → {fechas con override}
    for ev in raw:
        if ev["recur_id"] is not None:
            overrides.setdefault(ev["uid"], set()).add(ev["recur_id"].date())
    out = []
    for ev in raw:
        if ev["cancelled"] or not ev["summary"]:
            continue
        skip = (overrides.get(ev["uid"], set())
                if ev["recur_id"] is None and ev["uid"] else set())
        for d, hhmm in _expand(ev, win_a, win_b, skip):
            out.append((ev["uid"], d, hhmm, ev["summary"]))
    return out


# ── API pública (lo que consumen hub y TUI) ─────────────────────────────────
def _shape(d, hhmm, title, uid, acc):
    """Un evento en la MISMA forma que personal.events(), marcado google y con
    su ORIGEN (source id + label). El id incluye la cuenta para que dos
    calendarios con el mismo UID no colisionen."""
    sid = acc.get("id", "")
    return {"id": "g" + hashlib.sha1(
                ("%s|%s|%s|%s" % (sid, uid, d.isoformat(), hhmm))
                .encode("utf-8", "replace")).hexdigest()[:10],
            "date": d.isoformat(), "time": hhmm, "title": title,
            "cat": "otro", "notes": "", "archived": False, "google": True,
            "source": sid, "source_label": acc.get("label") or sid}


def _events_for(acc):
    """Eventos de UNA cuenta desde su caché (SIN red). [] si no hay caché o es
    de otra URL (sig distinto)."""
    c = _cache_for(acc["id"])
    if not c or c.get("sig") != _url_sig(acc.get("url") or ""):
        return []
    out = []
    try:
        for uid, d, hhmm, summary in _expand_ics(c["ics"]):
            out.append(_shape(d, hhmm, summary, uid, acc))
    except Exception:
        return []
    return out


def _accounts_sig(accts):
    """Huella del CONJUNTO de cuentas (id + sig de URL) para el memo: cambia si
    se agrega/quita/renombra/recambia cualquier cuenta."""
    parts = ["%s:%s:%s" % (a["id"], _url_sig(a.get("url") or ""),
                           a.get("label") or "") for a in accts]
    return hashlib.sha256("|".join(parts).encode("utf-8", "replace")) \
        .hexdigest()[:16]


def events(refresh_bg=True):
    """TODOS los eventos de Google de TODAS las cuentas en la ventana (hoy ±
    ~1 año), forma personal.py + {"google": True, "source", "source_label"},
    ordenados por (fecha, hora). SIN red: mergea el caché de disco + memo; si
    alguna cuenta está vieja dispara su refresh en fondo. Sin cuentas → []."""
    accts = _all_accounts()
    if not accts:
        return []
    sig = _accounts_sig(accts)
    now = time.monotonic()
    if _memo["sig"] == sig and now - _memo["ts"] < _MEMO_TTL:
        if refresh_bg:
            _maybe_bg_all(accts)
        return _memo["events"]
    out = []
    for acc in accts:
        try:
            out.extend(_events_for(acc))
        except Exception:
            pass
    out.sort(key=lambda e: (e["date"], e["time"] or "99:99"))
    _memo.update(ts=now, sig=sig, events=out)
    if refresh_bg:
        _maybe_bg_all(accts)
    return out


def _maybe_bg_all(accts):
    """Refresh en fondo de cada cuenta cuyo caché no esté fresco."""
    for acc in accts:
        try:
            c = _cache_for(acc["id"])
            stale = (not c or c.get("sig") != _url_sig(acc.get("url") or "")
                     or time.time() - float(c.get("fetched") or 0) >= FETCH_TTL)
            if stale and _url_ok(acc.get("url") or ""):
                _refresh_bg(acc)
        except Exception:
            pass


def invalidate():
    """Tira el memo (tras un refresh síncrono, para releer ya) y rearma la
    comprobación de migración (los tests cambian de HOME entre casos)."""
    _memo.update(ts=0.0, sig=None, events=[])
    _migrated[0] = False


def events_on(date_s):
    """Eventos de Google de UN día (ISO), de todas las cuentas, por hora."""
    return [e for e in events() if e["date"] == str(date_s)[:10]]


def events_month(year, month):
    """Eventos de Google de UN mes (todas las cuentas): {día(int): [ev, …]}."""
    pref = "%04d-%02d-" % (int(year), int(month))
    out = {}
    for e in events():
        if e["date"].startswith(pref):
            out.setdefault(int(e["date"][8:10]), []).append(e)
    return out


def configured():
    """True si hay ≥1 cuenta vinculada (no dice si sirve — eso lo dice
    `list_accounts`/`status`)."""
    return bool(_all_accounts())


# ── gestión de cuentas (lo que consume la UI del hub) ───────────────────────
def _mk_id(label, taken):
    """Un id corto, estable y único a partir del label (reservando los ids
    especiales). Falla a 'cal' si el label no deja nada usable."""
    base = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")[:16]
    base = base or "cal"
    reserved = set(taken) | {DEFAULT_ID, "env"}
    aid, i = base, 2
    while aid in reserved:
        aid = "%s-%d" % (base, i)
        i += 1
    return aid


def list_accounts():
    """El estado PÚBLICO de cada cuenta (sin URL, solo el host). Cada entrada:
    {id, label, kind, host, state: "ok"|"error"|"nofetch", events, last_sync,
    env}. Falla-suave → []. NO toca la red."""
    out = []
    for acc in _all_accounts():
        u = acc.get("url") or ""
        host = _url_display(u)
        if not _url_ok(u):
            state, nev, last = "error", 0, None
        else:
            c = _cache_for(acc["id"])
            if c and c.get("sig") == _url_sig(u):
                state, last = "ok", c.get("fetched")
                try:
                    nev = len(_events_for(acc))
                except Exception:
                    nev = 0
            else:
                state, nev, last = "nofetch", 0, None
        out.append({"id": acc["id"], "label": acc["label"],
                    "kind": acc.get("kind", "ical"), "host": host,
                    "state": state, "events": nev, "last_sync": last,
                    "env": bool(acc.get("_env"))})
    return out


def add_account(label, url_value, timeout=FETCH_TIMEOUT):
    """Vincula una cuenta NUEVA (kind ical): valida la URL, hace un fetch de
    PRUEBA y, si baja bien, la guarda + cachea. Devuelve
    {"ok":True,"id","label","host","events"} o {"ok":False,"error"}. El valor
    de la URL JAMÁS aparece en el resultado."""
    _ensure_migrated()
    u = (url_value or "").strip()
    if not _url_ok(u):
        return {"ok": False, "error": "not_https"}
    if any((a.get("url") or "") == u for a in _all_accounts()):
        return {"ok": False, "error": "duplicate"}
    text = _fetch(u, timeout=timeout)
    if text is None:
        return {"ok": False, "error": "fetch_failed"}
    label = (label or "").strip()[:60] or _url_display(u)
    accts = _persisted_accounts()
    aid = _mk_id(label, {a["id"] for a in accts})
    acc = {"id": aid, "label": label, "url": u, "kind": "ical"}
    accts.append(acc)
    if not _save_accounts(accts):
        return {"ok": False, "error": "save_failed"}
    _cache_put(aid, text, _url_sig(u))
    invalidate()
    try:
        nev = len(_events_for(acc))
    except Exception:
        nev = 0
    return {"ok": True, "id": aid, "label": label,
            "host": _url_display(u), "events": nev}


def remove_account(acc_id):
    """Desvincula una cuenta por id. {"ok":True,"id"} o {"ok":False,"error"}.
    La cuenta "default" respaldada por el env NO se quita desde aquí."""
    _ensure_migrated()
    acc_id = str(acc_id or "")
    if acc_id == DEFAULT_ID and _env_owns_default():
        return {"ok": False, "error": "env"}
    accts = _persisted_accounts()
    new = [a for a in accts if a["id"] != acc_id]
    if len(new) == len(accts):
        return {"ok": False, "error": "not_found"}
    if not _save_accounts(new):
        return {"ok": False, "error": "save_failed"}
    _cache_drop(acc_id)
    invalidate()
    return {"ok": True, "id": acc_id}


def rename_account(acc_id, label):
    """Renombra una cuenta. {"ok":True,"id","label"} o {"ok":False,"error"}.
    La cuenta "default" respaldada por el env NO se renombra desde aquí."""
    _ensure_migrated()
    acc_id = str(acc_id or "")
    label = (label or "").strip()[:60]
    if not label:
        return {"ok": False, "error": "empty"}
    if acc_id == DEFAULT_ID and _env_owns_default():
        return {"ok": False, "error": "env"}
    accts = _persisted_accounts()
    found = False
    for a in accts:
        if a["id"] == acc_id:
            a["label"], found = label, True
    if not found:
        return {"ok": False, "error": "not_found"}
    if not _save_accounts(accts):
        return {"ok": False, "error": "save_failed"}
    invalidate()
    return {"ok": True, "id": acc_id, "label": label}


def _upsert_default(url_value, timeout=FETCH_TIMEOUT):
    """Compat (`set-url`): vincula o ACTUALIZA la cuenta persistida "default".
    Si el env manda la URL única, avisa en vez de pisarla."""
    u = (url_value or "").strip()
    if not _url_ok(u):
        return {"ok": False, "error": "not_https"}
    if _env_owns_default():
        return {"ok": False, "error": "env"}
    text = _fetch(u, timeout=timeout)
    if text is None:
        return {"ok": False, "error": "fetch_failed"}
    accts = _persisted_accounts()
    for a in accts:
        if a["id"] == DEFAULT_ID:
            a["url"], a["kind"] = u, "ical"
            break
    else:
        accts.insert(0, {"id": DEFAULT_ID, "label": "Principal", "url": u,
                         "kind": "ical"})
    if not _save_accounts(accts):
        return {"ok": False, "error": "save_failed"}
    _cache_put(DEFAULT_ID, text, _url_sig(u))
    invalidate()
    return {"ok": True, "id": DEFAULT_ID, "host": _url_display(u),
            "events": len(events(refresh_bg=False))}


# ── CLI ─────────────────────────────────────────────────────────────────────
def _state_es(state):
    return {"ok": "conectado", "error": "URL inválida",
            "nofetch": "sin bajar aún"}.get(state, state)


def _cmd_status():
    accts = list_accounts()
    if not accts:
        print("google calendar: SIN cuentas vinculadas")
        print("  vincula una con:  python3 gcal.py add   (la URL «Dirección "
              "secreta en formato iCal» de Google Calendar)")
        return 0
    print("google calendar: %d cuenta(s) vinculada(s)" % len(accts))
    for a in accts:
        extra = " · env" if a["env"] else ""
        if a["state"] == "ok" and a["last_sync"]:
            age = int(time.time() - float(a["last_sync"]))
            extra += " · hace %dm%02ds" % (age // 60, age % 60)
        print("  [%s] %s  →  %s  (%s · %d eventos%s)"
              % (a["id"], a["label"], a["host"], _state_es(a["state"]),
                 a["events"], extra))
    return 0


def _cmd_accounts():
    accts = list_accounts()
    if not accts:
        print("sin cuentas — vincula con:  python3 gcal.py add")
        return 0
    for a in accts:
        print("  %-12s %-20s %-28s %-12s %d ev%s"
              % (a["id"], a["label"][:20], a["host"][:28],
                 _state_es(a["state"]), a["events"],
                 " (env)" if a["env"] else ""))
    return 0


def _prompt_url():
    try:
        import getpass
        return getpass.getpass("pega la URL iCal secreta (no se muestra): ")
    except Exception:
        return input("pega la URL iCal secreta: ")


def _cmd_add():
    try:
        label = input("nombre de la cuenta (p. ej. Trabajo): ").strip()
    except Exception:
        label = ""
    u = (_prompt_url() or "").strip()
    if not u:
        print("nada que guardar")
        return 1
    r = add_account(label, u)
    if r.get("ok"):
        print("conectado ✓ · %s (%s) · %d eventos"
              % (r["label"], r["host"], r["events"]))
        return 0
    err = {"not_https": "eso no es una URL https — Google la da como "
           "https://calendar.google.com/calendar/ical/…/basic.ics",
           "duplicate": "esa cuenta ya está vinculada",
           "fetch_failed": "no pude bajar el calendario (¿red o URL revocada?)",
           "save_failed": "no pude guardarla en la bóveda"}.get(
               r.get("error"), r.get("error"))
    print(err, file=sys.stderr)
    return 1


def _cmd_remove(argv):
    if not argv:
        print("uso: gcal.py remove <id>   (ve los ids con  gcal.py accounts)",
              file=sys.stderr)
        return 2
    r = remove_account(argv[0])
    if r.get("ok"):
        print("desvinculada: %s" % r["id"])
        return 0
    err = {"env": "esa cuenta viene de la variable %s del sistema — bórrala "
           "ahí" % URL_VAR,
           "not_found": "no hay una cuenta con ese id"}.get(
               r.get("error"), r.get("error"))
    print(err, file=sys.stderr)
    return 1


def _cmd_rename(argv):
    if len(argv) < 2:
        print("uso: gcal.py rename <id> <nombre nuevo>", file=sys.stderr)
        return 2
    r = rename_account(argv[0], " ".join(argv[1:]))
    if r.get("ok"):
        print("renombrada: [%s] %s" % (r["id"], r["label"]))
        return 0
    err = {"env": "esa cuenta viene de la variable %s del sistema" % URL_VAR,
           "empty": "el nombre no puede ir vacío",
           "not_found": "no hay una cuenta con ese id"}.get(
               r.get("error"), r.get("error"))
    print(err, file=sys.stderr)
    return 1


def _cmd_set_url():
    u = (_prompt_url() or "").strip()
    if not u:
        print("nada que guardar")
        return 1
    r = _upsert_default(u)
    if r.get("ok"):
        print("guardada la cuenta default (%s) — %d eventos"
              % (r["host"], r["events"]))
        return 0
    err = {"not_https": "eso no es una URL https — Google la da como "
           "https://calendar.google.com/calendar/ical/…/basic.ics",
           "env": "la URL única viene del env %s — cámbiala ahí" % URL_VAR,
           "fetch_failed": "no pude bajarlo ahora (¿red?) — el hub reintenta "
           "solo",
           "save_failed": "no pude guardarla en la bóveda"}.get(
               r.get("error"), r.get("error"))
    print(err, file=sys.stderr)
    return 1


def _cmd_refresh():
    if not configured():
        print("sin cuentas — primero:  python3 gcal.py add", file=sys.stderr)
        return 1
    ok = refresh(force=True)
    invalidate()
    n = len(events(refresh_bg=False))
    if ok:
        print("caché fresco — %d eventos en %d cuenta(s)"
              % (n, len(_all_accounts())))
        return 0
    print("alguna cuenta no bajó (red o URL revocada) — %d eventos en caché"
          % n, file=sys.stderr)
    return 1


def _cmd_list():
    evs = events(refresh_bg=False)
    hoy = _dt.date.today().isoformat()
    prox = [e for e in evs if e["date"] >= hoy][:20]
    if not prox:
        print("sin eventos por venir (¿caché vacío? corre refresh)")
        return 0
    multi = len({e.get("source") for e in prox}) > 1
    for e in prox:
        tag = ("  [%s]" % e.get("source_label", "")) if multi else ""
        print("  %s %-5s  %s%s" % (e["date"], e["time"] or "", e["title"], tag))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "status"
    rest = argv[1:]
    if cmd in ("status", "st"):
        return _cmd_status()
    if cmd in ("accounts", "acc", "cuentas"):
        return _cmd_accounts()
    if cmd in ("add", "connect", "conectar", "vincular"):
        return _cmd_add()
    if cmd in ("remove", "rm", "quitar", "desvincular"):
        return _cmd_remove(rest)
    if cmd in ("rename", "renombrar"):
        return _cmd_rename(rest)
    if cmd in ("set-url", "seturl"):
        return _cmd_set_url()
    if cmd in ("refresh", "sync", "actualizar"):
        return _cmd_refresh()
    if cmd in ("list", "ls", "lista"):
        return _cmd_list()
    if cmd == "clear-url":
        r = remove_account(DEFAULT_ID)
        invalidate()
        if r.get("ok"):
            print("cuenta default desvinculada")
        elif r.get("error") == "env":
            print("la URL única viene del env %s — bórrala ahí" % URL_VAR,
                  file=sys.stderr)
        else:
            print("no había cuenta default que borrar")
        return 0
    if cmd == "clear-cache":
        try:
            os.unlink(cache_path())
        except Exception:
            pass
        invalidate()
        print("caché borrado")
        return 0
    print("uso: gcal.py [status|accounts|add|remove <id>|rename <id> <nombre>|"
          "refresh|list|set-url|clear-url|clear-cache]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
