#!/usr/bin/env python3
"""WORKSPACE · personal — el dato PERSONAL del socio: FOCO del día + AGENDA.

Es la fuente que consume el layout `dia` del hub (hublayout._dia_lines) para
las dos cajas que no existían: «◆ FOCO» y «⏱ AGENDA». Nada de esto vive en un
cerebro ni se sincroniza: es de ESTA máquina y de ESTE socio.

    ~/.claude/workspace/personal.json     (per-máquina, gitignored, reconstruible)

Mismo trato que board.json / calendar.json del dashboard de dev:
  · escritura ATÓMICA (tmp con pid + token único + os.replace),
  · FALLA-SUAVE absoluta (ausente/corrupto/ilegible → vacío, jamás levanta —
    el hub no se puede romper por esto),
  · validación de fecha/hora REAL (nada de 2026-13-40),
  · papelera: «borrar» conserva el evento por 15 días; después expira y
    se purga en la próxima escritura. --hard es borrado explícito inmediato.

Modelo (schema 1 — aditivo, los eventos viejos se normalizan al leer):
    {"schema": 1,
     "foco": {"text": str, "date": "YYYY-MM-DD", "updated": "<iso>"},
     "eventos": [{"id", "date", "time", "title", "cat", "notes",
                  "done", "prio", "archived", "created"}]}

  · foco.date  — el día para el que se fijó: si no es HOY, el hub lo pinta
                 como «de ayer» en vez de mentir que es el foco de hoy.
  · date       — ISO YYYY-MM-DD obligatoria y validada.
  · time       — "HH:MM" opcional (evento de día entero si va vacío).
  · cat        — reunion / hito / recordatorio / cumple / otro (default otro).
  · notes      — descripción LARGA (proyectos, contexto); hasta 30 000 chars.
  · done       — HECHA sin borrarla: se tacha en la UI y sale del conteo de
                 «faltan». Reversible (toggle). Default False (migración
                 suave: un evento viejo sin el campo se lee como pendiente).
  · prio       — "alta" o "" — la alta lleva marca ! y se ordena primero.

CLI (lo que tecleas tú):
    workspace foco                      → muestra el foco de hoy
    workspace foco "cerrar el NDA"      → lo fija
    workspace foco --clear              → lo borra
    workspace agenda                    → lo que viene (próximos 30 días)
    workspace agenda add 2026-09-25 "Junta con Miguel" --time 18:00 --cat reunion
    workspace agenda done <id>          → la marca hecha / la desmarca (toggle)
    workspace agenda rm <id>            → archiva (--hard para borrar de verdad)

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import json
import os
import sys
import uuid
import functools
import threading
from olock import file_lock, LockTimeout
from datetime import date as _date, datetime, timedelta

SCHEMA = 1
CATEGORIES = ("reunion", "hito", "recordatorio", "cumple", "otro")
#: tope de la descripción larga — el socio la usa para tareas y proyectos enteros
NOTES_MAX = 30000
PROMPT_MAX = 30000
TASK_STATUSES = ("draft", "ready", "in_progress", "blocked", "done")
_LOCK_STATE = threading.local()
TRASH_DAYS = 15


# ── ubicación ───────────────────────────────────────────────────────────────
def _workspace_dir():
    """~/.claude/workspace (mismo directorio local que usa todo el harness)."""
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def path():
    """Ruta del store. `WORKSPACE_PERSONAL` la pisa (tests herméticos)."""
    p = os.environ.get("WORKSPACE_PERSONAL")
    return p if p else os.path.join(_workspace_dir(), "personal.json")


def _mutation(fn):
    """Serialize full read-modify-write, including nested helpers."""
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        if getattr(_LOCK_STATE, "depth", 0):
            return fn(*args, **kwargs)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path())), exist_ok=True)
            with file_lock(path(), timeout=5):
                _LOCK_STATE.depth = 1
                try:
                    return fn(*args, **kwargs)
                finally:
                    _LOCK_STATE.depth = 0
        except (OSError, LockTimeout):
            return None
    return wrapped


def task_status(event):
    if event.get("done"):
        return "done"
    value = event.get("task_status")
    return value if value in TASK_STATUSES and value != "done" else "draft"


# ── lectura / escritura ─────────────────────────────────────────────────────
def _empty():
    return {"schema": SCHEMA, "foco": None, "eventos": []}


def load():
    """El store completo. Ausente/corrupto/ilegible → vacío. Jamás levanta."""
    try:
        with open(path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty()
        out = _empty()
        foco = data.get("foco")
        if isinstance(foco, dict) and (foco.get("text") or "").strip():
            out["foco"] = {"text": str(foco.get("text"))[:200].strip(),
                           "date": str(foco.get("date") or "")[:10],
                           "updated": str(foco.get("updated") or "")}
        evs = data.get("eventos")
        if isinstance(evs, list):
            for e in evs:
                if isinstance(e, dict) and _valid_date(e.get("date")) \
                        and (e.get("title") or "").strip():
                    out["eventos"].append({
                        "id": str(e.get("id") or uuid.uuid4().hex[:8]),
                        "date": str(e["date"])[:10],
                        "time": _valid_time(e.get("time")),
                        "title": str(e["title"])[:120].strip(),
                        "cat": (e.get("cat") if e.get("cat") in CATEGORIES
                                else "otro"),
                        "notes": str(e.get("notes") or "")[:NOTES_MAX],
                        "prompt": str(e.get("prompt") or "")[:PROMPT_MAX],
                        "task_status": task_status(e),
                        "claimed_by": str(e.get("claimed_by") or ""),
                        "claim_token": str(e.get("claim_token") or ""),
                        "claimed_at": str(e.get("claimed_at") or ""),
                        "result": str(e.get("result") or "")[:NOTES_MAX],
                        # migración suave: eventos viejos sin estos campos
                        # se leen como pendientes sin prioridad — nada se
                        # pierde ni cambia de significado
                        "done": bool(e.get("done")),
                        "prio": ("alta" if e.get("prio") in
                                 ("alta", "high", "!") else ""),
                        "archived": bool(e.get("archived")),
                        "created": str(e.get("created") or ""),
                        "deleted_at": str(e.get("deleted_at") or "")})
        return out
    except Exception:
        return _empty()


@_mutation
def save(data):
    """Escritura ATÓMICA (tmp + os.replace). True si quedó en disco."""
    try:
        data = dict(data)
        now = datetime.now().astimezone()
        data["eventos"] = [dict(e) for e in data.get("eventos", [])
                           if not _trash_expired(e, now)]
        for e in data["eventos"]:
            if e.get("archived") and not e.get("deleted_at"):
                e["deleted_at"] = now.isoformat()
        d = os.path.dirname(os.path.abspath(path()))
        if not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        dest = path()
        tmp = "%s.tmp-%d-%s" % (dest, os.getpid(), uuid.uuid4().hex[:8])
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
        return True
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        return False


# ── validación ──────────────────────────────────────────────────────────────
def _valid_date(s):
    """True si `s` es una fecha ISO REAL (YYYY-MM-DD)."""
    try:
        datetime.strptime(str(s)[:10], "%Y-%m-%d")
        return True
    except Exception:
        return False


def _valid_time(s):
    """"HH:MM" normalizado, o "" si no es una hora real."""
    s = str(s or "").strip()
    if not s:
        return ""
    for fmt in ("%H:%M", "%H%M", "%I:%M%p"):
        try:
            return datetime.strptime(s.upper(), fmt).strftime("%H:%M")
        except Exception:
            continue
    return ""


def _today():
    return _date.today().isoformat()


def _now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


# ── FOCO ────────────────────────────────────────────────────────────────────
def foco():
    """El foco guardado: {"text", "date", "updated", "hoy": bool} o None.
    `hoy` False = se fijó otro día (el hub lo dice, no lo disfraza)."""
    f = (load() or {}).get("foco")
    if not f:
        return None
    f = dict(f)
    f["hoy"] = (f.get("date") == _today())
    return f


@_mutation
def set_foco(text):
    """Fija el foco del día. Texto vacío = lo borra. True si guardó."""
    data = load()
    text = (text or "").strip()
    data["foco"] = ({"text": text[:200], "date": _today(),
                     "updated": _now_iso()} if text else None)
    return save(data)


def clear_foco():
    return set_foco("")


# ── AGENDA ──────────────────────────────────────────────────────────────────
def events(include_archived=False):
    """Todos los eventos, ordenados por (fecha, hora)."""
    evs = [e for e in (load() or {}).get("eventos") or ()
           if include_archived or not e.get("archived")]
    return sorted(evs, key=lambda e: (e["date"], e.get("time") or "99:99"))


def upcoming(limit=5, days=30, now=None):
    """Lo que VIENE: eventos de hoy en adelante (hasta `days` días), ya
    ordenados, con `delta_min` = minutos que faltan cuando hay hora (None
    para los de día entero) y `dias` = días que faltan. Solo dato real.
    Las HECHAS no salen: ya no son «lo que viene»."""
    now = now or datetime.now()
    hoy = now.date()
    tope = hoy + timedelta(days=max(1, int(days)))
    out = []
    for e in events():
        if e.get("done"):
            continue
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except Exception:
            continue
        if d < hoy or d > tope:
            continue
        e = dict(e)
        e["dias"] = (d - hoy).days
        e["delta_min"] = None
        if e.get("time"):
            try:
                hh, mm = e["time"].split(":")
                when = datetime.combine(d, datetime.min.time()).replace(
                    hour=int(hh), minute=int(mm))
                e["delta_min"] = int((when - now).total_seconds() // 60)
            except Exception:
                e["delta_min"] = None
        # ya pasó hoy (hora vencida) → no es «lo que viene»
        if e["dias"] == 0 and e["delta_min"] is not None \
                and e["delta_min"] < -60:
            continue
        out.append(e)
        if len(out) >= max(1, int(limit)):
            break
    return out


@_mutation
def add_event(date_s, title, time_s="", cat="otro", notes="", prio="", prompt=""):
    """Agrega un evento. Devuelve su id, o None si la fecha/título no sirven."""
    if len(str(notes or "")) > NOTES_MAX or len(str(prompt or "")) > PROMPT_MAX:
        return None
    if not _valid_date(date_s) or not (title or "").strip():
        return None
    data = load()
    ev = {"id": uuid.uuid4().hex[:8], "date": str(date_s)[:10],
          "time": _valid_time(time_s), "title": str(title).strip()[:120],
          "cat": cat if cat in CATEGORIES else "otro",
          "notes": str(notes or "")[:NOTES_MAX],
          "prompt": str(prompt or "")[:PROMPT_MAX], "task_status": "draft",
          "done": False, "prio": "alta" if prio == "alta" else "",
          "archived": False, "created": _now_iso()}
    data["eventos"].append(ev)
    return ev["id"] if save(data) else None


@_mutation
def update_event(ev_id, date_s=None, title=None, time_s=None, notes=None,
                 cat=None, done=None, prio=None, prompt=None):
    """Edita un evento EN SITIO (conserva su id, su `created` y lo que no se
    toca). True si lo encontro y guardo. Fecha invalida -> False y no toca
    nada: mas vale no editar que corromper el store."""
    if (notes is not None and len(str(notes)) > NOTES_MAX) or (prompt is not None and len(str(prompt)) > PROMPT_MAX):
        return False
    if date_s is not None and not _valid_date(date_s):
        return False
    data = load()
    hit = False
    for i, e in enumerate(data.get("eventos") or ()):
        if e.get("id") != ev_id:
            continue
        hit = True
        nuevo = dict(e)
        if date_s is not None:
            nuevo["date"] = str(date_s)[:10]
        if title is not None and str(title).strip():
            nuevo["title"] = str(title).strip()[:120]
        if time_s is not None:
            nuevo["time"] = _valid_time(time_s)
        if prompt is not None:
            nuevo["prompt"] = str(prompt)[:PROMPT_MAX]
        if notes is not None:
            nuevo["notes"] = str(notes)[:NOTES_MAX]
        if cat is not None and cat in CATEGORIES:
            nuevo["cat"] = cat
        if done is not None:
            nuevo["done"] = bool(done)
            nuevo["task_status"] = "done" if done else "draft"
            nuevo["claimed_by"], nuevo["claim_token"], nuevo["claimed_at"] = "", "", ""
        if prio is not None:
            nuevo["prio"] = "alta" if prio == "alta" else ""
        nuevo["updated"] = _now_iso()
        data["eventos"][i] = nuevo
        break
    return save(data) if hit else False


@_mutation
def toggle_done(ev_id):
    """HECHA ↔ pendiente, sin borrar nada. Devuelve el estado nuevo (True =
    quedó hecha, False = quedó pendiente) o None si el id no existe."""
    for e in events(include_archived=True):
        if e.get("id") == ev_id:
            nuevo = not e.get("done")
            return nuevo if update_event(ev_id, done=nuevo) else None
    return None


@_mutation
def toggle_prio(ev_id):
    """Prioridad alta ↔ normal. Devuelve la prio nueva ("alta"/"") o None."""
    for e in events(include_archived=True):
        if e.get("id") == ev_id:
            nueva = "" if e.get("prio") == "alta" else "alta"
            return nueva if update_event(ev_id, prio=nueva) else None
    return None


def overdue(days=60, now=None):
    """ATRASADAS: pendientes (ni hechas ni archivadas) de días PASADOS,
    hasta `days` atrás, las más recientes primero — para que lo que se le
    pasó a un día no desaparezca de la vista. Solo eventos locales."""
    hoy = (now or datetime.now()).date()
    piso = (hoy - timedelta(days=max(1, int(days)))).isoformat()
    out = [e for e in events()
           if not e.get("done") and piso <= e["date"] < hoy.isoformat()]
    out.sort(key=lambda e: (e["date"], e.get("time") or "99:99"),
             reverse=True)
    return out


def events_on(date_s):
    """Los eventos vivos de UN dia (ISO), ordenados por hora."""
    return [e for e in events() if e.get("date") == str(date_s)[:10]]


@_mutation
def remove_event(ev_id, hard=False):
    """Archiva el evento (o lo borra de verdad con hard=True). True si tocó algo."""
    data = load()
    hit = False
    keep = []
    for e in data.get("eventos") or ():
        if e.get("id") == ev_id:
            hit = True
            if hard:
                continue
            e = dict(e, archived=True,
                     deleted_at=e.get("deleted_at") or datetime.now().astimezone().isoformat())
        keep.append(e)
    if not hit:
        return False
    data["eventos"] = keep
    return save(data)


def _trash_expired(event, now=None):
    if not event.get("archived") or not event.get("deleted_at"):
        return False
    try:
        deleted = datetime.fromisoformat(event["deleted_at"]).astimezone()
        return (now or datetime.now().astimezone()) >= deleted + timedelta(days=TRASH_DAYS)
    except (ValueError, TypeError):
        return False


@_mutation
def trash_events():
    """Recoverable deletions; legacy archives receive a fresh 15-day window."""
    data = load()
    if any(e.get("archived") and not e.get("deleted_at") for e in data["eventos"]):
        if save(data):
            data = load()
    return sorted((e for e in data["eventos"]
                   if e.get("archived") and not _trash_expired(e)),
                  key=lambda e: e.get("deleted_at") or "", reverse=True)


@_mutation
def restore_event(ev_id):
    data = load()
    for e in data["eventos"]:
        if e["id"] == ev_id and e.get("archived") and not _trash_expired(e):
            e["archived"], e["deleted_at"] = False, ""
            return save(data)
    return False


@_mutation
def move_event(ev_id, date_s):
    if not _valid_date(date_s) or len(str(date_s)) != 10:
        return False
    if not any(e["id"] == ev_id for e in events()):
        return False
    return update_event(ev_id, date_s=date_s)


# ── CLI ─────────────────────────────────────────────────────────────────────
def task_queue(status="ready"):
    """Explicitly ready local tasks, all dates; priority then date then id."""
    return sorted((e for e in events() if task_status(e) == status),
                  key=lambda e: (0 if e.get("prio") == "alta" else 1,
                                 e["date"], e.get("time") or "99:99",
                                 e.get("created") or "", e["id"]))


@_mutation
def set_task_status(ev_id, status):
    """User control: ready/draft/blocked/done; cannot fabricate a claim."""
    if status not in TASK_STATUSES or status == "in_progress":
        return False
    data = load()
    for e in data["eventos"]:
        if e["id"] == ev_id and not e.get("archived"):
            if task_status(e) == "in_progress":
                return False  # finish/release requires this task's claim token
            e["task_status"], e["done"] = status, status == "done"
            e["updated"] = _now_iso()
            return save(data)
    return False


@_mutation
def claim_task(ev_id="next", agent=""):
    """Atomic ready -> in_progress. Never selects drafts or expired deletes."""
    if not agent.strip():
        return None
    ready = task_queue()
    hit = next((e for e in ready if ev_id == "next" or e["id"] == ev_id), None)
    if not hit:
        return None
    data = load()
    for e in data["eventos"]:
        if e["id"] == hit["id"]:
            e.update(task_status="in_progress", claimed_by=agent.strip()[:120],
                     claim_token=uuid.uuid4().hex, claimed_at=_now_iso(), result="")
            return dict(e) if save(data) else None
    return None


@_mutation
def finish_task(ev_id, token, status="done", result=""):
    """Claim owner closes, blocks, or releases the task; failed saves keep it claimed."""
    if status not in ("done", "blocked", "ready") or not token:
        return False
    data = load()
    for e in data["eventos"]:
        if (e["id"] == ev_id and not e.get("archived")
                and task_status(e) == "in_progress"
                and e.get("claim_token") == token):
            e.update(task_status=status, done=status == "done",
                     result=str(result)[:NOTES_MAX], claim_token="", updated=_now_iso())
            return save(data)
    return False


def _task_cli(argv):
    """Machine-readable task queue; no agent is launched by these commands."""
    import argparse
    parser = argparse.ArgumentParser(prog="workspace agenda tareas")
    sub = parser.add_subparsers(dest="action")
    listing = sub.add_parser("list")
    listing.add_argument("--status", choices=TASK_STATUSES, default="ready")
    listing.add_argument("--json", action="store_true")
    mark = sub.add_parser("mark")
    mark.add_argument("id")
    mark.add_argument("status", choices=("draft", "ready", "blocked", "done"))
    claim = sub.add_parser("claim")
    claim.add_argument("id", nargs="?", default="next")
    claim.add_argument("--agent", required=True)
    for action in ("finish", "block", "release"):
        item = sub.add_parser(action)
        item.add_argument("id")
        item.add_argument("--token", required=True)
        item.add_argument("--result", default="")
    args = parser.parse_args(argv or ["list"])
    if args.action in (None, "list"):
        rows = task_queue(getattr(args, "status", "ready"))
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for e in rows:
                print("%s  %s  %s  %s" % (e["id"], e["date"], task_status(e), e["title"]))
        return 0
    if args.action == "mark":
        ok = set_task_status(args.id, args.status)
        print(json.dumps({"ok": bool(ok)}, ensure_ascii=False))
        return 0 if ok else 1
    if args.action == "claim":
        task = claim_task(args.id, args.agent)
        print(json.dumps({"task": task}, ensure_ascii=False, indent=2))
        return 0 if task else 1
    status = {"finish": "done", "block": "blocked", "release": "ready"}[args.action]
    ok = finish_task(args.id, args.token, status, args.result)
    print(json.dumps({"ok": bool(ok)}, ensure_ascii=False))
    return 0 if ok else 1


def _fmt_delta(mins):
    if mins is None:
        return ""
    if mins < -5:
        return "pasó"
    if mins < 0:
        return "ahora"
    if mins < 60:
        return "en %dm" % mins
    h, m = divmod(mins, 60)
    if h < 24:
        return "en %dh %02dm" % (h, m) if m else "en %dh" % h
    return "en %dd" % int(round(h / 24.0))


def cmd_foco(argv):
    if argv and argv[0] in ("--clear", "-c", "clear", "borrar"):
        clear_foco()
        print("foco borrado")
        return 0
    if argv:
        txt = " ".join(argv).strip()
        if set_foco(txt):
            print("foco de hoy: %s" % txt)
            return 0
        print("no pude guardar el foco", file=sys.stderr)
        return 1
    f = foco()
    if not f:
        print('sin foco — fíjalo con:  workspace foco "lo que importa hoy"')
        return 0
    print("%s%s" % (f["text"], "" if f.get("hoy") else "   (de %s)" % f.get("date")))
    return 0


def cmd_agenda(argv):
    if argv and argv[0] in ("tasks", "tareas"):
        return _task_cli(argv[1:])
    if argv and argv[0] in ("trash", "papelera"):
        for e in trash_events():
            print("%s  %s  %s" % (e["id"], e["date"], e["title"]))
        return 0
    if argv and argv[0] in ("restore", "restaurar"):
        return 0 if len(argv) == 2 and restore_event(argv[1]) else 1
    if argv and argv[0] in ("move", "mover"):
        return 0 if len(argv) == 3 and move_event(argv[1], argv[2]) else 1
    if argv and argv[0] in ("add", "nuevo", "+"):
        rest = argv[1:]
        time_s, cat, notes, prompt = "", "otro", "", ""
        pos = []
        i = 0
        while i < len(rest):
            a = rest[i]
            if a in ("--time", "--hora") and i + 1 < len(rest):
                time_s = rest[i + 1]
                i += 2
            elif a in ("--cat", "--tipo") and i + 1 < len(rest):
                cat = rest[i + 1]
                i += 2
            elif a == "--prompt" and i + 1 < len(rest):
                prompt = rest[i + 1]
                i += 2
            elif a in ("--notes", "--nota") and i + 1 < len(rest):
                notes = rest[i + 1]
                i += 2
            else:
                pos.append(a)
                i += 1
        if len(pos) < 2:
            print('uso: workspace agenda add YYYY-MM-DD "título" '
                  '[--time HH:MM] [--cat reunion|hito|recordatorio|cumple|otro]',
                  file=sys.stderr)
            return 2
        ev_id = add_event(pos[0], " ".join(pos[1:]), time_s, cat, notes, prompt=prompt)
        if not ev_id:
            print("fecha inválida o título vacío — no se agregó", file=sys.stderr)
            return 1
        print("agregado  %s  %s %s  %s" % (ev_id, pos[0], time_s,
                                           " ".join(pos[1:])))
        return 0
    if argv and argv[0] in ("done", "hecho", "x"):
        ids = [a for a in argv[1:] if not a.startswith("--")]
        if not ids:
            print("uso: workspace agenda done <id>", file=sys.stderr)
            return 2
        rc = 0
        for i in ids:
            st = toggle_done(i)
            if st is None:
                print("no existe: %s" % i, file=sys.stderr)
                rc = 1
            else:
                print("%s  %s" % (i, "hecha ✓" if st else "pendiente otra vez"))
        return rc
    if argv and argv[0] in ("rm", "del", "quitar", "borrar"):
        hard = "--hard" in argv
        ids = [a for a in argv[1:] if not a.startswith("--")]
        if not ids:
            print("uso: workspace agenda rm <id> [--hard]", file=sys.stderr)
            return 2
        ok = all(remove_event(i, hard=hard) for i in ids)
        print("listo" if ok else "algún id no existe")
        return 0 if ok else 1
    if argv and argv[0] in ("all", "todo", "list", "ls"):
        rows = events(include_archived="--archived" in argv)
    else:
        rows = upcoming(limit=20, days=365)
    if not rows:
        print('agenda vacía — agrega con:  workspace agenda add '
              '2026-09-25 "Junta" --time 18:00')
        return 0
    for e in rows:
        when = _fmt_delta(e.get("delta_min"))
        if not when and e.get("dias") is not None:
            when = ("hoy" if e["dias"] == 0 else
                    "mañana" if e["dias"] == 1 else "en %dd" % e["dias"])
        print("  %-8s %s %-5s %s %-40s %s%s%s" % (
            e["id"], e["date"], e.get("time") or "",
            "✓" if e.get("done") else ("!" if e.get("prio") == "alta"
                                       else " "),
            e["title"], when,
            "  (hecha)" if e.get("done") else "",
            "  (archivado)" if e.get("archived") else ""))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.split("CLI (lo que tecleas tú):")[1].split("Cero")[0]
              .strip())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in ("foco", "focus"):
        return cmd_foco(rest)
    if cmd in ("agenda", "cal", "calendario"):
        return cmd_agenda(rest)
    print("personal: comando desconocido '%s' (foco | agenda)" % cmd,
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
