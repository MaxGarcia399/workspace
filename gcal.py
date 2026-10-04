#!/usr/bin/env python3
"""WORKSPACE · gcal — el Google Calendar del socio, en SOLO LECTURA (fase 1).

Es la fuente REMOTA que se fusiona con la agenda local (`personal.py`) en el
layout `dia` del hub y en `calendario_tui`. Lee la «dirección secreta en
formato iCal» que Google da por calendario — una URL con token embebido, así
que ES UN SECRETO y se trata como tal:

    · La URL vive en la bóveda per-máquina (`secret_store`, 0600, fuera del
      repo) bajo el nombre  WORKSPACE_GCAL_ICS_URL  — o en el env del sistema,
      que GANA (misma regla que todas las credenciales del harness).
    · JAMÁS se imprime completa: `status` enseña solo el host.
    · Se exige https — una URL file:// o http:// en la config no se toca.

CONTRATO con el hub (por qué está diseñado así):
  · `events()` / `events_on()` / `events_month()` NUNCA tocan la red: leen el
    caché de disco (`~/.claude/workspace/gcal_cache.local.json`) y, si está
    viejo, disparan UN hilo daemon que refresca en segundo plano. El render
    del hub (redraw cada ~0.5 s) no se puede congelar por un DNS lento.
  · FALLA-SUAVE absoluta: sin URL, sin red, ICS corrupto → lista vacía o el
    caché viejo que haya. La agenda local sigue igual; nada levanta.
  · Los eventos salen en la MISMA forma que personal.events() —
    {"id","date","time","title","cat","notes","archived"} — más
    {"google": True} para que la vista los distinga y los editores los
    protejan (solo lectura hasta la fase 2 / OAuth, ver `gcal_oauth.py`).

Parser ICS propio, mínimo y honesto (RFC 5545, el subconjunto que Google
emite): unfolding, VEVENT (SUMMARY · DTSTART/DTEND con TZID/VALUE=DATE/Z ·
STATUS), RRULE básica (DAILY/WEEKLY/MONTHLY/YEARLY + INTERVAL/COUNT/UNTIL/
BYDAY semanal), EXDATE y overrides por RECURRENCE-ID. Lo que no se entiende
se degrada a la ocurrencia base — nunca se inventa una fecha.

CLI:
    python3 gcal.py status        → ¿URL configurada? ¿caché? ¿cuántos eventos?
    python3 gcal.py set-url       → pide la URL (prompt oculto; nada en argv
                                    ni en el historial del shell) y la guarda
    python3 gcal.py refresh       → fetch SÍNCRONO ahora (para probar)
    python3 gcal.py list          → próximos eventos parseados
    python3 gcal.py clear-url     → borra el secreto
    python3 gcal.py clear-cache   → borra el caché local

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

URL_VAR = "WORKSPACE_GCAL_ICS_URL"          # nombre del secreto (nunca el valor)
FETCH_TTL = 15 * 60                       # el feed se considera fresco 15 min
FETCH_TIMEOUT = 10                        # segundos de red, y solo en el hilo
MAX_ICS_BYTES = 5 * 1024 * 1024           # un calendario no pesa más que esto
WINDOW_BACK = 370                         # expansión de RRULE: hoy ± ~1 año
WINDOW_FWD = 370
_MEMO_TTL = 30.0                          # memo en proceso (render barato)

_memo = {"ts": 0.0, "sig": None, "events": []}
_fetch_lock = threading.Lock()            # single-flight del refresh en fondo
_fetching = [False]


# ── ubicación / secreto ─────────────────────────────────────────────────────
def _workspace_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def cache_path():
    """`.local.json` ⇒ doblemente fuera del repo (vive en ~/.claude y el
    patrón está gitignoreado). `WORKSPACE_GCAL_CACHE` lo pisa (tests)."""
    return (os.environ.get("WORKSPACE_GCAL_CACHE")
            or os.path.join(_workspace_dir(), "gcal_cache.local.json"))


def url():
    """La URL iCal secreta: env del sistema GANA, luego la bóveda. "" si no
    hay. NUNCA loguear lo que devuelve esto."""
    u = (os.environ.get(URL_VAR) or "").strip()
    if not u:
        try:
            import secret_store
            u = (secret_store.get(URL_VAR) or "").strip()
        except Exception:
            u = ""
    return u


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


# ── caché de disco ──────────────────────────────────────────────────────────
def _cache_load():
    try:
        with open(cache_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("ics"), str):
            return d
    except Exception:
        pass
    return None


def _cache_save(ics_text, sig):
    try:
        os.makedirs(_workspace_dir(), exist_ok=True)
        dest = cache_path()
        tmp = "%s.tmp-%d" % (dest, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fetched": time.time(), "sig": sig, "ics": ics_text},
                      f, ensure_ascii=False)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, dest)
        return True
    except Exception:
        return False


def _url_sig(u):
    """Huella de la URL para invalidar el caché si el socio cambia de calendario —
    sin guardar la URL misma en el caché."""
    return hashlib.sha256(u.encode("utf-8", "replace")).hexdigest()[:16]


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


def refresh(force=False, timeout=FETCH_TIMEOUT):
    """Fetch SÍNCRONO (CLI / pruebas). True si el caché quedó fresco."""
    u = url()
    if not u:
        return False
    sig = _url_sig(u)
    if not force:
        c = _cache_load()
        if c and c.get("sig") == sig \
                and time.time() - float(c.get("fetched") or 0) < FETCH_TTL:
            return True
    text = _fetch(u, timeout=timeout)
    if text is None:
        return False
    return _cache_save(text, sig)


def _refresh_bg():
    """Refresca en un hilo daemon, una corrida a la vez. Jamás bloquea."""
    with _fetch_lock:
        if _fetching[0]:
            return
        _fetching[0] = True

    def _run():
        try:
            refresh()
        finally:
            _fetching[0] = False

    try:
        threading.Thread(target=_run, name="gcal-refresh",
                         daemon=True).start()
    except Exception:
        _fetching[0] = False


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


# ── API pública (lo que consumen hub y TUI) ─────────────────────────────────
def _shape(d, hhmm, title, uid):
    """Un evento en la MISMA forma que personal.events(), marcado google."""
    return {"id": "g" + hashlib.sha1(
                ("%s|%s|%s" % (uid, d.isoformat(), hhmm))
                .encode("utf-8", "replace")).hexdigest()[:10],
            "date": d.isoformat(), "time": hhmm, "title": title,
            "cat": "otro", "notes": "", "archived": False, "google": True}


def events(refresh_bg=True):
    """TODOS los eventos de Google en la ventana (hoy ± ~1 año), forma
    personal.py + {"google": True}, ordenados por (fecha, hora). SIN red:
    caché de disco + memo; si el caché está viejo dispara el refresh en
    fondo (la siguiente lectura ya lo ve). Sin URL/caché → []."""
    u = url()
    if not u:
        return []
    sig = _url_sig(u)
    now = time.monotonic()
    if _memo["sig"] == sig and now - _memo["ts"] < _MEMO_TTL:
        if refresh_bg:
            _maybe_bg(sig)
        return _memo["events"]
    out = []
    c = _cache_load()
    if c and c.get("sig") == sig:
        try:
            hoy = _dt.date.today()
            win_a = hoy - _dt.timedelta(days=WINDOW_BACK)
            win_b = hoy + _dt.timedelta(days=WINDOW_FWD)
            raw = parse_ics(c["ics"])
            overrides = {}                    # uid → {fechas con override}
            for ev in raw:
                if ev["recur_id"] is not None:
                    overrides.setdefault(ev["uid"], set()).add(
                        ev["recur_id"].date())
            for ev in raw:
                if ev["cancelled"] or not ev["summary"]:
                    continue
                skip = (overrides.get(ev["uid"], set())
                        if ev["recur_id"] is None and ev["uid"] else set())
                for d, hhmm in _expand(ev, win_a, win_b, skip):
                    out.append(_shape(d, hhmm, ev["summary"], ev["uid"]))
            out.sort(key=lambda e: (e["date"], e["time"] or "99:99"))
        except Exception:
            out = []
    _memo.update(ts=now, sig=sig, events=out)
    if refresh_bg:
        _maybe_bg(sig)
    return out


def _maybe_bg(sig):
    """Refresh en fondo si el caché no está fresco (o es de otra URL)."""
    try:
        c = _cache_load()
        stale = (not c or c.get("sig") != sig
                 or time.time() - float(c.get("fetched") or 0) >= FETCH_TTL)
        if stale:
            _refresh_bg()
    except Exception:
        pass


def invalidate():
    """Tira el memo (tras un refresh síncrono, para releer ya)."""
    _memo.update(ts=0.0, sig=None, events=[])


def events_on(date_s):
    """Eventos de Google de UN día (ISO), ordenados por hora."""
    return [e for e in events() if e["date"] == str(date_s)[:10]]


def events_month(year, month):
    """Eventos de Google de UN mes: {día(int): [ev, …]}."""
    pref = "%04d-%02d-" % (int(year), int(month))
    out = {}
    for e in events():
        if e["date"].startswith(pref):
            out.setdefault(int(e["date"][8:10]), []).append(e)
    return out


def configured():
    """True si hay URL puesta (no dice si sirve — eso lo dice `status`)."""
    return bool(url())


# ── CLI ─────────────────────────────────────────────────────────────────────
def _cmd_status():
    u = url()
    if not u:
        print("google calendar: SIN conectar")
        print("  conecta con:  python3 gcal.py set-url   (la URL «Dirección "
              "secreta en formato iCal» de Google Calendar)")
        return 0
    print("google calendar: URL configurada  →  %s" % _url_display(u))
    if not _url_ok(u):
        print("  ⚠ la URL no es https válida — revísala (set-url de nuevo)")
        return 1
    c = _cache_load()
    if not c or c.get("sig") != _url_sig(u):
        print("  caché: aún no hay — corre  python3 gcal.py refresh")
        return 0
    age = int(time.time() - float(c.get("fetched") or 0))
    evs = events(refresh_bg=False)
    print("  caché: hace %dm%02ds · %d eventos en la ventana (±1 año)"
          % (age // 60, age % 60, len(evs)))
    return 0


def _cmd_set_url():
    try:
        import getpass
        u = getpass.getpass("pega la URL iCal secreta (no se muestra): ")
    except Exception:
        u = input("pega la URL iCal secreta: ")
    u = (u or "").strip()
    if not u:
        print("nada que guardar")
        return 1
    if not _url_ok(u):
        print("eso no es una URL https — Google la da como "
              "https://calendar.google.com/calendar/ical/…/basic.ics",
              file=sys.stderr)
        return 1
    try:
        import secret_store
        r = secret_store.set_secret(URL_VAR, u)
    except Exception as e:
        r = {"ok": False, "error": str(e)}
    if not r.get("ok"):
        print("no pude guardarla: %s" % r.get("error"), file=sys.stderr)
        return 1
    print("guardada en la bóveda per-máquina (%s)" % URL_VAR)
    invalidate()
    print("bajando el calendario…")
    ok = refresh(force=True)
    print("listo — %d eventos" % len(events(refresh_bg=False)) if ok
          else "no pude bajarlo ahora (¿red?) — el hub reintenta solo")
    return 0 if ok else 1


def _cmd_refresh():
    if not configured():
        print("sin URL — primero:  python3 gcal.py set-url", file=sys.stderr)
        return 1
    ok = refresh(force=True)
    invalidate()
    if ok:
        print("caché fresco — %d eventos" % len(events(refresh_bg=False)))
        return 0
    print("no pude bajar el calendario (red o URL revocada)", file=sys.stderr)
    return 1


def _cmd_list():
    evs = events(refresh_bg=False)
    hoy = _dt.date.today().isoformat()
    prox = [e for e in evs if e["date"] >= hoy][:20]
    if not prox:
        print("sin eventos por venir (¿caché vacío? corre refresh)")
        return 0
    for e in prox:
        print("  %s %-5s  %s" % (e["date"], e["time"] or "", e["title"]))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "status"
    if cmd in ("status", "st"):
        return _cmd_status()
    if cmd in ("set-url", "seturl", "connect", "conectar"):
        return _cmd_set_url()
    if cmd in ("refresh", "sync", "actualizar"):
        return _cmd_refresh()
    if cmd in ("list", "ls", "lista"):
        return _cmd_list()
    if cmd == "clear-url":
        try:
            import secret_store
            secret_store.remove(URL_VAR)
        except Exception:
            pass
        invalidate()
        print("URL borrada de la bóveda")
        return 0
    if cmd == "clear-cache":
        try:
            os.unlink(cache_path())
        except Exception:
            pass
        invalidate()
        print("caché borrado")
        return 0
    print("uso: gcal.py [status|set-url|refresh|list|clear-url|clear-cache]",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
