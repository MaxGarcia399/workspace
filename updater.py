#!/usr/bin/env python3
"""WORKSPACE · updater — actualizar el harness con red de seguridad.

POR QUÉ EXISTE: Workspace corre en computadoras ajenas y se actualiza solo
(cada 6 h al lanzar un agente) o con `workspace update`. Que se actualice
solo es una ELECCIÓN del usuario (`auto_mode()`): automático (default), solo
avisar, o apagado. `workspace update` siempre funciona, elija lo que elija. Antes eran tres
copias del mismo `git pull --ff-only` (front.cmd_update, dispatch.maybe_
autoupdate y la pantalla Actualizaciones) y, si una versión nueva no
arrancaba en la máquina del cliente, no había vuelta atrás. Este módulo es
el ÚNICO motor de actualización del harness, con el ciclo de Try Omarchy:

  1. Candado: una sola actualización a la vez por máquina.
  2. Anotar desde dónde salimos (commit + versión) ANTES de tocar nada.
  3. Traer y avanzar SOLO en fast-forward (jamás se reescribe nada local; si
     hay cambios sin guardar, no se toca).
  4. Comprobar que la versión nueva arranca AQUÍ (`selftest.py`, proceso
     nuevo, mismo Python del usuario).
  5. Si no arranca → volver solo al commit anterior y FIJAR esa versión hasta
     que publiquemos una más nueva (el auto-update no reintenta la misma rota).
  6. Si arranca → aplicar los ajustes registrados (`migrate.py`) con el
     código nuevo, y dejar constancia en el historial.

`workspace update --rollback` usa el historial para volver a la versión
anterior a mano, con la misma fijación.

Solo el HARNESS pasa por aquí. Los cerebros son datos del usuario: se
actualizan con su pull de siempre (front._update_repo), sin selftest.

Todo el estado vive en `<state_dir>/update/`:
  history.jsonl  — una línea por intento (máx. 50)
  hold.json      — versión fijada tras una vuelta atrás (si existe)
  update.lock    — candado

Stdlib, Python 3.9+, Mac/Windows/Linux. Nunca lanza hacia el llamador.
"""
import datetime
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paths as _paths  # noqa: E402

HISTORY_MAX = 50
SELFTEST_TIMEOUT = 120
FETCH_TIMEOUT = 60

# Resultados posibles de update_harness()["status"]
UPDATED, UPTODATE, SKIPPED, HELD, ROLLED_BACK, BUSY = (
    "updated", "uptodate", "skipped", "held", "rolled-back", "busy")
# Solo con apply=False: hay versión nueva y NO se tocó nada.
AVAILABLE = "available"

# ── ¿se actualiza solo? (elección del usuario) ──────────────────────────────
# auto   = al lanzar un agente se actualiza solo, con la red de seguridad.
# notify = solo avisa que hay versión nueva; instalarla es `workspace update`.
# off    = no consulta nada por su cuenta (ni red); solo `workspace update`.
AUTO_MODES = ("auto", "notify", "off")
AUTO_SETTING = "otros.auto_update"


def auto_mode():
    """El modo vigente en esta máquina. WORKSPACE_NO_AUTOUPDATE=1 gana (= off:
    lo usan los procesos hijos y quien lo tenga puesto desde antes); si no, el
    ajuste `otros.auto_update`; ante cualquier problema, "auto" (el default
    de siempre: nadie que no lo haya pedido pierde las actualizaciones)."""
    if os.environ.get("WORKSPACE_NO_AUTOUPDATE"):
        return "off"
    try:
        import settings
        v = settings.get(AUTO_SETTING)
        return v if v in AUTO_MODES else "auto"
    except Exception:
        return "auto"


def set_auto_mode(mode):
    """Guarda la elección. Devuelve True si quedó guardada. ValueError si el
    modo no existe (no escribe nada)."""
    if mode not in AUTO_MODES:
        raise ValueError(mode)
    import settings
    settings.set(AUTO_SETTING, mode)
    return True


def auto_mode_text(mode=None):
    """Una línea para el usuario: qué hace el modo elegido."""
    mode = mode or auto_mode()
    env = bool(os.environ.get("WORKSPACE_NO_AUTOUPDATE"))
    key = {"auto": ("updater.mode.auto", "automáticas: se instalan solas, con red de seguridad"),
           "notify": ("updater.mode.notify", "solo avisar: te digo que hay versión nueva y tú decides"),
           "off": ("updater.mode.off", "apagadas: solo cuando corras `workspace update`")}[mode]
    txt = _t(*key)
    if env and mode == "off":
        txt += _t("updater.mode.env", " (WORKSPACE_NO_AUTOUPDATE=1 está puesto)")
    return txt
# La versión nueva no arrancó Y no se pudo volver limpio a la anterior
# (archivo bloqueado, index.lock…). Nunca se disfraza de vuelta atrás.
ROLLBACK_FAILED = "rollback-failed"


def _t(key, default, **kw):
    try:
        import i18n
        s = i18n.t(key, **kw)
        if s != key:
            return s
    except Exception:
        pass
    try:
        return default.format(**kw) if kw else default
    except Exception:
        return default


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ── estado en disco ─────────────────────────────────────────────────────────
def update_dir(home=None):
    return os.path.join(_paths.state_dir(home), "update")


def _p(name, home=None):
    return os.path.join(update_dir(home), name)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def history(home=None):
    """Intentos de actualización, del más viejo al más nuevo."""
    out = []
    try:
        with open(_p("history.jsonl", home), encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    try:
                        out.append(json.loads(ln))
                    except ValueError:
                        continue
    except OSError:
        pass
    return out


def _record(entry, home=None):
    try:
        hist = history(home)[-(HISTORY_MAX - 1):] + [entry]
        os.makedirs(update_dir(home), exist_ok=True)
        tmp = _p("history.jsonl.tmp-%d" % os.getpid(), home)
        with open(tmp, "w", encoding="utf-8") as fh:
            for e in hist:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.replace(tmp, _p("history.jsonl", home))
    except Exception:
        pass


def last_update(home=None):
    """Último intento que CAMBIÓ algo (updated / rolled-back), o None."""
    for e in reversed(history(home)):
        if e.get("status") in (UPDATED, ROLLED_BACK):
            return e
    return None


def hold(home=None):
    data = _read_json(_p("hold.json", home))
    return data if isinstance(data, dict) and data.get("bad") else None


def _set_hold(bad, good, reason, home=None, bad_version="", kind="selftest"):
    """kind: "selftest" (no arrancó aquí) | "manual" (el usuario volvió atrás)."""
    _write_json_atomic(_p("hold.json", home), {
        "bad": bad, "good": good, "reason": reason, "at": _now(),
        "bad_version": bad_version, "kind": kind})


def clear_hold(home=None):
    try:
        os.remove(_p("hold.json", home))
    except OSError:
        pass


# ── git ─────────────────────────────────────────────────────────────────────
def _git(root, *args, timeout=30):
    """(rc, stdout, stderr). rc=-1 timeout, rc=-2 git no instalado."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"        # jamás pedir credenciales a ciegas
    env["GCM_INTERACTIVE"] = "never"        # ni la ventana de Git Credential Manager
    try:
        r = subprocess.run(["git", "-C", root] + list(args), capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "git no instalado"
    except Exception as e:
        return -3, "", "%s: %s" % (type(e).__name__, e)


def read_version(root=ROOT):
    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:
        return ""


def current(root=ROOT):
    """{version, sha, short, branch} de la copia instalada (fail-soft)."""
    _, sha, _ = _git(root, "rev-parse", "HEAD", timeout=8)
    _, branch, _ = _git(root, "rev-parse", "--abbrev-ref", "HEAD", timeout=8)
    return {"version": read_version(root), "sha": sha, "short": sha[:7],
            "branch": branch}


def _classify_fail(text):
    low = (text or "").lower()
    if "no tracking" in low or "no upstream" in low or "remote ref" in low:
        return "no_tracking"
    if any(k in low for k in ("could not resolve", "unable to access", "timeout",
                              "connection", "network", "could not read from remote")):
        return "offline"
    if "fast-forward" in low or "divergent" in low or "diverged" in low:
        return "divergent"
    return "failed"


REASONS = {
    "not_git": ("updater.reason.not_git", "esta copia no es un repo git (instalación por sync) — se actualiza por otra vía"),
    "git_missing": ("updater.reason.git_missing", "git no está instalado en esta máquina"),
    "no_remote": ("updater.reason.no_remote", "sin repositorio remoto configurado — nada que traer"),
    "dirty": ("updater.reason.dirty", "hay cambios locales sin guardar — no actualizo encima para no perderlos"),
    "detached": ("updater.reason.detached", "la copia no está en una rama (detached) — no actualizo"),
    "no_tracking": ("updater.reason.no_tracking", "la rama no sigue a una rama remota"),
    "offline": ("updater.reason.offline", "sin conexión con el servidor — se queda como está"),
    "divergent": ("updater.reason.divergent", "la historia local y la remota divergen — hay que resolverlo a mano"),
    "failed": ("updater.reason.failed", "git no pudo traer la actualización"),
    "busy": ("updater.reason.busy", "ya hay otra actualización en curso"),
    "no_target": ("updater.reason.no_target", "no hay una actualización reciente a la que volver desde esta versión"),
    "missing_commit": ("updater.reason.missing_commit", "la versión anterior ya no está disponible en esta copia"),
    "interrupted": ("updater.reason.interrupted", "actualización interrumpida — se quedó la versión que tenías"),
    "reset_failed": ("updater.reason.reset_failed", "la versión nueva no arrancó y no pude volver limpio a la anterior (¿un archivo bloqueado?)"),
}


def reason_text(code):
    key, default = REASONS.get(code, ("", code))
    return _t(key, default) if key else default


# ── piezas del ciclo ────────────────────────────────────────────────────────
def _child_env():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["WORKSPACE_NO_AUTOUPDATE"] = "1"     # el hijo jamás vuelve a actualizar
    env["WORKSPACE_NO_AUTORENDER"] = "1"
    return env


def selftest_problems(root=ROOT, timeout=SELFTEST_TIMEOUT):
    """[problemas] (lista vacía = arranca) corriendo selftest.py del código EN
    DISCO con el MISMO Python del usuario. Sin selftest.py (versión vieja) →
    []. Cada problema es un texto "dónde — error"."""
    script = os.path.join(root, "selftest.py")
    if not os.path.isfile(script):
        return []
    try:
        r = subprocess.run([sys.executable, script, "--json"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=_child_env(), cwd=root,
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return [_t("updater.selftest.timeout", "la versión nueva tardó demasiado en arrancar")]
    except Exception as e:
        return ["%s: %s" % (type(e).__name__, e)]
    try:
        data = json.loads((r.stdout or "").strip().splitlines()[-1])
        if data.get("ok"):
            return []
        return ["%s — %s" % (p.get("where"), p.get("error"))
                for p in (data.get("problems") or [])] or ["selftest"]
    except Exception:
        if r.returncode == 0:
            return []
        tail = ((r.stderr or r.stdout or "").strip().splitlines() or ["?"])[-1]
        return [tail[:300]]


def run_selftest(root=ROOT, timeout=SELFTEST_TIMEOUT):
    """(ok, detalle) — forma corta de selftest_problems()."""
    probs = selftest_problems(root, timeout)
    return (not probs), "; ".join(probs[:3])


def run_migrations(root=ROOT, timeout=300):
    """Corre `migrate.py --run --json` con el código NUEVO. Devuelve el dict
    de migrate.run_pending o {"error": ...}. Nunca lanza."""
    script = os.path.join(root, "migrate.py")
    if not os.path.isfile(script):
        return {"applied": [], "not_needed": [], "failed": None, "remaining": []}
    try:
        r = subprocess.run([sys.executable, script, "--run", "--json"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=_child_env(),
                           cwd=root, stdin=subprocess.DEVNULL)
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}


def _lock(home=None):
    try:
        import olock
        os.makedirs(update_dir(home), exist_ok=True)
        return olock.file_lock(_p("update", home), timeout=3)
    except Exception:
        return None


def _commits(root, rng, limit=30):
    rc, log, _ = _git(root, "log", "--format=%h\x1f%s", "-%d" % limit, rng, timeout=10)
    if rc != 0:
        return []
    return [tuple(ln.split("\x1f", 1)) for ln in log.splitlines() if "\x1f" in ln]


def _version_at(root, sha):
    rc, out, _ = _git(root, "show", "%s:VERSION" % sha, timeout=8)
    return out.strip() if rc == 0 else ""


# ── el ciclo completo ───────────────────────────────────────────────────────
def update_harness(root=ROOT, mode="manual", home=None, force=False,
                   migrate=True, fetch_timeout=FETCH_TIMEOUT, notify=None, apply=True):
    """Actualiza el harness. `mode`: "manual" (`workspace update`, pantalla
    Actualizaciones) | "auto" (al lanzar un agente). `force` ignora una
    versión fijada (el usuario lo pidió explícitamente). `apply=False` solo
    COMPRUEBA (trae del servidor y compara): nunca cambia la copia del usuario
    ni el historial; si hay versión nueva devuelve status "available".

    Devuelve SIEMPRE un dict:
      status   updated | uptodate | skipped | held | rolled-back | busy
      reason   código (ver REASONS) cuando status es skipped/held/rolled-back
      detail   texto extra (p. ej. qué falló en el selftest)
      from / to / from_version / to_version / branch
      commits  [(sha, asunto)] que llegaron (o que se intentaron)
      migrations  resultado de migrate (solo si status=updated)
    `notify(texto)` se llama UNA vez, justo antes del trabajo lento (aplicar y
    comprobar la versión nueva), para que nadie vea una terminal congelada.
    Ctrl+C a mitad: se vuelve al commit de partida y se devuelve "interrupted"."""
    res = {"status": SKIPPED, "reason": "", "detail": "", "from": "", "to": "",
           "from_version": read_version(root), "to_version": "", "branch": "",
           "commits": [], "migrations": None, "mode": mode}
    try:
        if not os.path.isdir(os.path.join(root, ".git")) and \
                not os.path.isfile(os.path.join(root, ".git")):
            res["reason"] = "not_git"
            return res
        lk = _lock(home)
        if lk is not None:
            try:
                lk.__enter__()
            except Exception:
                res["status"], res["reason"] = BUSY, "busy"
                return res
        try:
            return _update_locked(root, mode, home, force, migrate, fetch_timeout, res,
                                  notify, apply)
        except KeyboardInterrupt:
            # Nada a medias: si ya habíamos avanzado sin verificar, volvemos.
            if res.get("from"):
                _, now, _ = _git(root, "rev-parse", "HEAD", timeout=8)
                if now and now != res["from"] and res["status"] != UPDATED:
                    _git(root, "reset", "--hard", "--quiet", res["from"], timeout=60)
            res["status"], res["reason"] = SKIPPED, "interrupted"
            return res
        finally:
            if lk is not None:
                try:
                    lk.__exit__(None, None, None)
                except Exception:
                    pass
    except Exception as e:                      # red final: jamás lanza
        res["status"], res["reason"] = SKIPPED, "failed"
        res["detail"] = "%s: %s" % (type(e).__name__, e)
        return res


def _update_locked(root, mode, home, force, migrate, fetch_timeout, res, notify=None,
                   apply=True):
    rc, remotes, _ = _git(root, "remote", timeout=10)
    if rc == -2:
        res["reason"] = "git_missing"
        return res
    if rc != 0 or not remotes:
        res["reason"] = "no_remote"
        return res
    rc, dirty, _ = _git(root, "status", "--porcelain", "--untracked-files=no", timeout=20)
    if rc != 0 or dirty:
        res["reason"] = "dirty"
        return res
    _, branch, _ = _git(root, "rev-parse", "--abbrev-ref", "HEAD", timeout=8)
    if not branch or branch == "HEAD":
        res["reason"] = "detached"
        return res
    res["branch"] = branch
    _, old, _ = _git(root, "rev-parse", "HEAD", timeout=8)
    res["from"] = res["to"] = old
    h = hold(home)
    if h and old == h.get("bad") and apply:
        clear_hold(home)                # llegó aquí por otra vía (pull a mano, setup)

    rc, out, err = _git(root, "fetch", "--quiet", timeout=fetch_timeout)
    if rc != 0:
        res["reason"] = _classify_fail(out + " " + err)
        return res
    rc, up, err = _git(root, "rev-parse", "@{u}", timeout=8)
    if rc != 0:
        res["reason"] = "no_tracking"
        return res
    if up == old or _git(root, "merge-base", "--is-ancestor", up, old, timeout=10)[0] == 0:
        res["status"] = UPTODATE                # remoto ya contenido en local
        h = hold(home)
        if apply and h and h.get("good") == old and up != h.get("bad"):
            clear_hold(home)
        return res

    h = hold(home)
    if h and up == h.get("bad") and not force:
        res["status"], res["reason"] = HELD, "held"
        res["detail"] = h.get("reason", "")
        res["to_version"] = h.get("bad_version", "")
        return res

    res["commits"] = _commits(root, "%s..%s" % (old, up))
    if not apply:
        res["status"], res["to"] = AVAILABLE, up
        res["to_version"] = _version_at(root, up)
        return res
    if notify:
        try:
            notify(_t("updater.notify.applying", "Actualizando Workspace… (comprobando que la "
                      "versión nueva arranca en esta máquina)"))
        except Exception:
            pass
    # Línea base: ¿la versión ACTUAL pasa su selftest en esta máquina? Si ya
    # falla (un ajuste corrupto, un permiso raro), ese problema es del entorno,
    # no de la versión nueva: no debe provocar una vuelta atrás eterna.
    baseline = set(selftest_problems(root))
    rc, out, err = _git(root, "merge", "--ff-only", "--quiet", up, timeout=60)
    if rc != 0:
        res["reason"] = _classify_fail(out + " " + err)
        _record(_entry(res, SKIPPED), home)
        return res
    _, new, _ = _git(root, "rev-parse", "HEAD", timeout=8)
    res["to"], res["to_version"] = new, read_version(root)

    probs = selftest_problems(root)
    new_probs = [p for p in probs if p not in baseline]
    detail = "; ".join((new_probs or probs)[:3])
    if new_probs:
        # La versión nueva no arranca en ESTA máquina → volver y fijar.
        rc, _, _ = _git(root, "reset", "--hard", "--quiet", old, timeout=60)
        _, now, _ = _git(root, "rev-parse", "HEAD", timeout=8)
        _, dirty, _ = _git(root, "status", "--porcelain", "--untracked-files=no", timeout=20)
        if rc != 0 or now != old or dirty:
            # No mentir: no quedó en la anterior. Sin pausa (no aplica) y con
            # el camino de ayuda. El doctor lo ve como copia sucia/desfasada.
            res["status"], res["reason"] = ROLLBACK_FAILED, "reset_failed"
            res["detail"] = detail
            _record(_entry(res, ROLLBACK_FAILED), home)
            return res
        _set_hold(new, old, detail, home, bad_version=res["to_version"])
        res["status"], res["reason"], res["detail"] = ROLLED_BACK, "selftest", detail
        _record(_entry(res, ROLLED_BACK), home)
        return res

    clear_hold(home)
    res["status"] = UPDATED
    if probs:      # mismos problemas que antes: del entorno, se reportan tal cual
        res["detail"] = detail
    if migrate:
        res["migrations"] = run_migrations(root)
    _record(_entry(res, UPDATED), home)
    return res


def _entry(res, status):
    mig = res.get("migrations") or {}
    return {"at": _now(), "mode": res.get("mode"), "status": status,
            "branch": res.get("branch"), "from": res.get("from"), "to": res.get("to"),
            "from_version": res.get("from_version"), "to_version": res.get("to_version"),
            "reason": res.get("reason"), "detail": (res.get("detail") or "")[:500],
            "commits": len(res.get("commits") or []),
            "migrations_applied": [a[0] if isinstance(a, (list, tuple)) else a
                                   for a in (mig.get("applied") or [])],
            "migration_failed": (mig.get("failed") or {}).get("id") if mig.get("failed") else None}


# ── vuelta atrás manual ─────────────────────────────────────────────────────
def rollback_target(root=ROOT, home=None):
    """El último update aplicado cuya versión nueva es la que está corriendo
    → (entry, from_sha). None si no hay a dónde volver."""
    cur = _git(root, "rev-parse", "HEAD", timeout=8)[1]
    for e in reversed(history(home)):
        if e.get("status") == UPDATED and e.get("to") == cur and e.get("from"):
            return e
    # Sin historial (p. ej. la actualización la hizo una versión anterior del
    # actualizador): git deja ORIG_HEAD en el commit previo a un pull. Solo se
    # usa si es un ancestro de HEAD con OTRA versión (no un paso intermedio).
    rc, orig, _ = _git(root, "rev-parse", "-q", "--verify", "ORIG_HEAD", timeout=8)
    if rc == 0 and orig and orig != cur and \
            _git(root, "merge-base", "--is-ancestor", orig, cur, timeout=10)[0] == 0:
        ov = _version_at(root, orig)
        if ov and ov != read_version(root):
            _, br, _ = _git(root, "rev-parse", "--abbrev-ref", "HEAD", timeout=8)
            return {"status": UPDATED, "from": orig, "to": cur, "from_version": ov,
                    "to_version": read_version(root), "at": "", "branch": br,
                    "source": "orig_head"}
    return None


def rollback(root=ROOT, home=None):
    """Vuelve a la versión anterior al último update y la fija.
    Devuelve dict {ok, reason, from, to, from_version, to_version}."""
    out = {"ok": False, "reason": "", "from": "", "to": "",
           "from_version": read_version(root), "to_version": ""}
    try:
        e = rollback_target(root, home)
        if not e:
            out["reason"] = "no_target"
            return out
        rc, dirty, _ = _git(root, "status", "--porcelain", "--untracked-files=no", timeout=20)
        if rc != 0 or dirty:
            out["reason"] = "dirty"
            return out
        if _git(root, "cat-file", "-e", e["from"] + "^{commit}", timeout=8)[0] != 0:
            out["reason"] = "missing_commit"
            return out
        cur = e["to"]
        rc, _, err = _git(root, "reset", "--hard", "--quiet", e["from"], timeout=60)
        if rc != 0:
            out["reason"] = "failed"
            return out
        _set_hold(cur, e["from"], _t("updater.hold.manual", "vuelta atrás pedida por el usuario"),
                  home, bad_version=e.get("to_version", ""), kind="manual")
        out.update(ok=True, **{"from": cur, "to": e["from"],
                               "to_version": read_version(root)})
        _record({"at": _now(), "mode": "manual", "status": ROLLED_BACK,
                 "branch": e.get("branch"), "from": cur, "to": e["from"],
                 "from_version": e.get("to_version"), "to_version": out["to_version"],
                 "reason": "manual", "detail": "", "commits": 0,
                 "migrations_applied": [], "migration_failed": None}, home)
        return out
    except Exception as ex:
        out["reason"] = "%s: %s" % (type(ex).__name__, ex)
        return out
