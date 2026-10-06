#!/usr/bin/env python3
"""WORKSPACE · agent_create_job — el JOB de crear un agente: EN VIVO y resumible.

La pantalla «Agregar agente» dejó de ser black-box: la creación corre en un
hilo daemon que reporta CADA paso de `agent_admin.CREATE_STEPS` (pend/run/ok/
warn/fail/skip) y PERSISTE su estado en `~/.claude/workspace/create-job.json` en
cada transición. Con eso:

  · EN VIVO     la UI solo LEE el dict del job (patrón «Estados EN VIVO»,
                validado en actualizaciones_tui): nada de stdout crudo — el
                worker captura sys.stdout/err/in (install.py imprime ✓ con
                say/ok y eso ROMPÍA la pantalla raw) y lo restaura en finally.
  · RESUMIBLE   el job vive en un global de módulo (_JOB): el hub cachea los
                módulos, así que salir de la pantalla y volver RE-ENGANCHA la
                vista al proceso en curso. Si el PROCESO murió a media
                creación, el archivo persistido lo delata (pid muerto + not
                done) y la UI ofrece limpiar los restos o reintentar — jamás
                un cerebro a medias en silencio.
  · HONESTO     costo: crear un agente NO consume tokens (es scaffolding
                local, sin modelo). Lo que SÍ cuesta es el ARRANQUE de cada
                sesión futura: estimate() mide la superficie HOT real del
                template (brain_vitals) y la reporta como estimado. La pasada
                OPCIONAL de personalización (agent_personalize, opt-in) SÍ
                consume tokens — se estiman antes (estimate()[
                "personalize_tokens"]) y se reportan al correr (notas de sus
                pasos + job["personalize"] + recibo en el cerebro).

Cancel = cooperativo: `cancel()` marca la bandera; agent_admin.create la lee
ENTRE pasos (antes del registro revierte todo; después, el agente ya existe y
solo se salta el pulido). Jamás se mata el hilo.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Falla-suave SIEMPRE.
"""
import io
import json
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import agent_admin                                              # noqa: E402
import agent_skill_sources

# i18n (lado cliente): las notas EN VIVO y los avisos de limpieza los ve el
# socio en la pantalla «Agregar agente». Import guardado — sin i18n, _t()
# devuelve el español inline (paridad EXACTA con lo de siempre).
try:
    import i18n
except Exception:
    i18n = None


def _t(key, es):
    if i18n is None:
        return es
    try:
        s = i18n.t(key)
        return s if s != key else es
    except Exception:
        return es

# Pasada OPCIONAL de personalización con modelo (opt-in: params["personalize"]
# truthy o env WORKSPACE_CREATE_PERSONALIZE=1; detalle en agent_personalize.py).
# Amputable (C10): sin el módulo, crear funciona EXACTAMENTE como siempre
# (scaffolding local, 0 tokens).
try:
    import agent_personalize                                    # noqa: E402
except Exception:
    agent_personalize = None

#: El job EN CURSO (o recién terminado) de ESTE proceso. El hub importa el
#: módulo una vez → el global sobrevive entre entradas a la pantalla.
_JOB = None
_LOCK = threading.Lock()

#: Estimación HOT del template (se mide una vez por proceso).
_EST = None


# ── persistencia (~/.claude/workspace/create-job.json) ─────────────────────────
def state_path():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "create-job.json")


def _persist(job):
    """Escribe el snapshot del job (atómico). Falla-suave: sin disco no hay
    resumen cross-proceso, pero el job sigue."""
    try:
        snap = {k: job[k] for k in
                ("name", "display", "engine", "dest", "owner", "steps",
                 "done", "ok", "error", "cancel", "t0_wall", "pid",
                 "created_by_job", "params", "personalize", "skill_sourcing") if k in job}
        path = state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp-%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        pass


def _read_state():
    try:
        with open(state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def clear_state():
    """Borra el snapshot persistido (al dar por visto un resultado)."""
    try:
        os.remove(state_path())
    except OSError:
        pass


def _pid_alive(pid):
    """¿Vive el proceso? Falla-suave → False. En Windows NO usamos os.kill
    (con sig≠señales de consola TERMINA el proceso) — OpenProcess readonly."""
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


# ── API del job ──────────────────────────────────────────────────────────────
def steps_skeleton():
    """[{key, label, st, note}] fresco desde agent_admin.CREATE_STEPS (fuente
    única: si el backend gana un paso, aquí aparece solo)."""
    return [{"key": k, "label": lbl, "st": "pend", "note": ""}
            for k, lbl in agent_admin.CREATE_STEPS]


def active():
    """El job vivo de ESTE proceso (corriendo o terminado sin dar por visto),
    o None."""
    return _JOB


def start(params):
    """Arranca la creación en un hilo daemon. `params` = kwargs de
    agent_admin.create (name, display, tagline, owner, scope, soul, skills,
    engine). Devuelve el job dict (la UI lo lee; solo el worker escribe).
    Si ya hay un job corriendo, devuelve ESE (un solo job a la vez)."""
    global _JOB
    with _LOCK:
        if _JOB is not None and not _JOB.get("done"):
            return _JOB
        name = str(params.get("name", "")).strip().lower()
        job = {
            "name": name,
            "display": params.get("display") or name.capitalize(),
            "engine": params.get("engine") or "claude-code",
            "owner": params.get("owner") or "",
            "dest": os.path.abspath(os.path.expanduser(
                params.get("brain_dest")
                or agent_admin.default_brain_dest(name))),
            "steps": steps_skeleton(),
            "live": [],                 # [(st, txt)] — lo último que pasó
            "done": False, "ok": False, "error": "", "cancel": False,
            "t0": time.monotonic(), "t1": None, "t0_wall": time.time(),
            "pid": os.getpid(), "created_by_job": True,
            "params": {k: v for k, v in params.items() if v},
        }
        # pasos EXTRA de la pasada de personalización (solo si se pidió): la
        # vista EN VIVO pinta job["steps"] tal cual → aparecen solos, con la
        # misma barra. Falla-suave: sin módulo no hay pasos ni pasada.
        if agent_personalize is not None:
            try:
                if agent_personalize.requested(job["params"]):
                    job["steps"].extend(agent_personalize.steps_skeleton())
            except Exception:
                pass
        if params.get("source_skills"):
            job["steps"].extend(agent_skill_sources.steps_skeleton())
        _JOB = job
    _persist(job)
    threading.Thread(target=_worker, args=(job,), daemon=True).start()
    return job


def cancel():
    """Marca el cancel cooperativo del job vivo (el paso en curso termina)."""
    job = _JOB
    if job is not None and not job.get("done"):
        job["cancel"] = True
        _persist(job)


def ack():
    """Da por VISTO el resultado: suelta el global y borra el snapshot."""
    global _JOB
    with _LOCK:
        if _JOB is not None and _JOB.get("done"):
            _JOB = None
    clear_state()


def _worker(job):
    """Corre agent_admin.create con el callback de pasos. Captura stdio
    GLOBAL (install.py imprime con say/ok → rompería la pantalla raw) y lo
    restaura SIEMPRE en finally."""
    def _on_step(key, st, note=""):
        for s in job["steps"]:
            if s["key"] == key:
                s["st"], s["note"] = st, str(note or "")
                break
        if st in ("ok", "warn", "fail", "skip"):
            lbl = next((s["label"] for s in job["steps"]
                        if s["key"] == key), key)
            txt = lbl + ((" — " + str(note)) if note else "")
            job["live"].append((st, txt))
            del job["live"][:-60]
        _persist(job)

    old = (sys.stdout, sys.stderr, sys.stdin)
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    sys.stdin = io.StringIO("")
    ok, res = False, ""
    try:
        p = job.get("params") or {}
        ok, res = agent_admin.create(
            job["name"],
            tagline=p.get("tagline", ""), display=p.get("display"),
            owner=p.get("owner", ""), scope=p.get("scope", ""),
            soul=p.get("soul", ""), skills=p.get("skills", ""),
            intake=p.get("intake"),
            brain_dest=p.get("brain_dest"), engine=job["engine"],
            out=lambda *a, **k: None, progress=_on_step,
            should_cancel=lambda: job["cancel"])
    except Exception as e:
        ok, res = False, "%s: %s" % (type(e).__name__, e)
    else:
        # ── pasada OPCIONAL de personalización con modelo (opt-in) ──
        # ADITIVA y fail-soft TOTAL: el agente YA quedó creado con la
        # plantilla; si esto falla/cancela, los pasos quedan warn/skip con
        # «sin personalizar — córrelo luego» y job["ok"] NO cambia. El costo
        # real (tokens) lo reporta la propia pasada en las notas de sus pasos
        # y en job["personalize"] (+ recibo en <brain>/.workspace/).
        if ok and agent_personalize is not None and not job["cancel"]:
            try:
                if agent_personalize.requested(p):
                    job["personalize"] = agent_personalize.run(
                        job["dest"], p, progress=_on_step,
                        should_cancel=lambda: job["cancel"])
            except Exception as e:               # jamás tumba la creación
                _on_step("perso-aplicar", "warn",
                         _t("addagent.job.perso_warn", "sin personalizar (%s) — plantilla intacta") % e)
        if ok and p.get("source_skills") and not job["cancel"]:
            try:
                job["skill_sourcing"] = agent_skill_sources.run(
                    job["dest"], p, progress=_on_step,
                    should_cancel=lambda: job["cancel"])
            except Exception as e:
                _on_step("skills-install", "warn", _t("addagent.job.skills_warn", "skills pendientes: %s") % e)
    finally:
        try:
            sys.stdout, sys.stderr, sys.stdin = old
        except Exception:
            pass
        job["ok"] = bool(ok)
        if not ok:
            job["error"] = str(res)
        for s in job["steps"]:                    # nada se queda "corriendo"
            if s["st"] in ("pend", "run"):
                s["st"] = "skip"
        job["t1"] = time.monotonic()
        job["done"] = True
        _persist(job)


# ── restos de una corrida interrumpida (proceso muerto a medias) ─────────────
def stale():
    """Snapshot de un job que quedó INTERRUMPIDO: el archivo dice `not done`
    y su proceso ya no vive (o era este proceso y el global ya no está — crash
    del hilo). Devuelve el dict persistido o None."""
    if _JOB is not None:
        return None                     # hay job vivo en ESTE proceso
    snap = _read_state()
    if not snap or snap.get("done"):
        return None
    pid = snap.get("pid")
    if pid == os.getpid() or not _pid_alive(pid):
        return snap
    return None                         # otro proceso vivo lo está corriendo


def cleanup(snap):
    """Limpia los RESTOS de un job interrumpido: borra la carpeta del cerebro
    (solo si la creó el job — create() exige que no existiera antes), quita el
    registro per-máquina y el snapshot. Devuelve (ok, detalle)."""
    import shutil
    if not snap:
        clear_state()
        return True, _t("addagent.job.cleanup.nothing", "nada que limpiar")
    det = []
    dest = snap.get("dest") or ""
    home = os.path.realpath(os.path.expanduser("~"))
    if snap.get("created_by_job") and dest and os.path.isdir(dest):
        rd = os.path.realpath(dest)
        if rd.startswith(home + os.sep) and rd != home:   # guard: solo bajo ~
            shutil.rmtree(dest, ignore_errors=True)
            det.append(_t("addagent.job.cleanup.folder_deleted", "carpeta borrada"))
        else:
            det.append(_t("addagent.job.cleanup.folder_outside", "carpeta fuera de ~ — no la toco"))
    name = snap.get("name") or ""
    if name:
        try:
            import agentsreg
            reg = agentsreg.find(name)
            if reg and os.path.realpath(reg["brain"]) == \
                    os.path.realpath(dest or reg["brain"]):
                agentsreg.remove(name)
                det.append(_t("addagent.job.cleanup.reg_removed", "registro quitado"))
        except Exception:
            det.append(_t("addagent.job.cleanup.reg_fail", "no pude tocar el registro"))
    clear_state()
    return True, " · ".join(det) or _t("addagent.job.cleanup.snapshot_deleted", "snapshot borrado")


# ── costo HONESTO ────────────────────────────────────────────────────────────
def estimate():
    """Qué cuesta crear un agente, SIN inventar números:
      · crear = 0 tokens (scaffolding local, ningún modelo interviene);
      · cada sesión futura carga la superficie HOT del cerebro — se MIDE del
        template real (brain_vitals, ~4 chars/token) y se marca estimado.
    Devuelve {"create_tokens": 0, "boot_tokens": int|None, "files": int}."""
    global _EST
    if _EST is not None:
        return _EST
    est = {"create_tokens": 0, "boot_tokens": None, "files": 0,
           "personalize_tokens": None}
    try:
        import brain_vitals
        m = brain_vitals.measure_hot(agent_admin.BRAIN_TEMPLATE)
        est["boot_tokens"] = m["total_chars"] // brain_vitals.CHARS_PER_TOKEN
        est["files"] = len(m["boot"]) + len(m["session"])
    except Exception:
        pass
    # costo de la pasada OPCIONAL de personalización (si se activa) — estimado
    # por chars, marcado como tal. None = módulo ausente o no medible.
    if agent_personalize is not None:
        try:
            pe = agent_personalize.estimate_for_template(
                agent_admin.BRAIN_TEMPLATE)
            est["personalize_tokens"] = pe["total"] if pe else None
        except Exception:
            pass
    _EST = est
    return est


if __name__ == "__main__":              # inspección rápida
    print(json.dumps({"active": _JOB is not None, "stale": stale(),
                      "estimate": estimate()}, ensure_ascii=False, indent=2))
