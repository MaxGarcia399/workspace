#!/usr/bin/env python3
"""WORKSPACE · agent_load_job — el JOB de conectar un agente que ya existe (cargar su cerebro), EN VIVO.

Es la carga que hacía la pantalla «Agregar agente» de antes dentro de sí misma (add_agent_tui._ljob_*), sacada a un
módulo sin pantalla para que la usen la tarjeta del hub, la página local y esa pantalla por igual:
  · start(items, prefs, origen)   un hilo que corre agent_admin.load con sus pasos (LOAD_STEPS) en vivo; con varios
                                  cerebros, un paso por cerebro. `items` = [(nombre, carpeta)]: un `nombre` distinto
                                  del de su cerebro lo registra con ese nombre (choque de nombres); la carpeta jamás
                                  se renombra;
  · iniciar(items, prefs)         lo mismo con las salidas de la tarjeta y la página ({"ok", "job"} o su error);
  · active() / vista(job) / ack() el job de ESTE proceso, su vista para la página y darlo por visto.
install.py imprime (say/ok): mientras carga, stdout/stderr/stdin se capturan (una carga a la vez, STDIO_LOCK, el mismo
candado que la búsqueda de cerebros) y se restauran SIEMPRE. Los WARN de esa salida vuelven como avisos.

Stdlib, Python 3.9+. Mac y Windows. Falla-suave."""
import io
import os
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

import agent_admin  # noqa: E402

try:
    import i18n
except Exception:
    i18n = None

#: Cargar y buscar cerebros capturan la salida de todo el proceso: uno a la vez.
STDIO_LOCK = threading.Lock()
_JOB = None
_LOCK = threading.Lock()


def _t(key, es):
    if i18n is None:
        return es
    try:
        s = i18n.t(key)
        return s if s != key else es
    except Exception:
        return es


def _ruta_corta(p):
    home = os.path.expanduser("~")
    return ("~" + p[len(home):]) if p and p.startswith(home) else p


def steps_single():
    return [{"key": k, "label": _t("addagent.lstep.%s" % k, lbl), "st": "pend", "note": ""}
            for k, lbl in agent_admin.LOAD_STEPS]


def active():
    return _JOB


def start(items, prefs=None, origen=""):
    """Arranca la carga en un hilo. → el job (la UI solo lo LEE). Si ya hay una en curso, devuelve ESA."""
    global _JOB
    with _LOCK:
        if _JOB is not None and not _JOB.get("done"):
            return _JOB
        items = [(str(n or ""), str(c or "")) for n, c in items]
        bulk = len(items) > 1
        if bulk:
            steps = [{"key": n or c, "label": "%s  %s" % (n, _ruta_corta(c)), "st": "pend", "note": ""}
                     for n, c in items]
        else:
            steps = steps_single()
        job = {"items": items, "bulk": bulk, "steps": steps, "live": [], "warns": [], "res_map": {},
               "done": False, "ok": False, "error": "", "res": "", "origen": origen, "prefs": dict(prefs or {}),
               "t0": time.monotonic(), "t1": None}
        _JOB = job
    threading.Thread(target=_worker, args=(job,), daemon=True).start()
    return job


def iniciar(items, prefs=None):
    """start() con las salidas de la tarjeta y la página: {"ok": True, "job": vista} o {"ok": False, "error"}."""
    try:
        import agent_create_job
        cj = agent_create_job.active()
        if cj and not cj.get("done"):                   # las dos capturan la salida: una a la vez
            return {"ok": False, "error": "localhost.err.crear_en_curso", "status": 409}
    except Exception:
        pass
    j = _JOB
    if j is not None and not j.get("done"):
        return {"ok": False, "error": "localhost.err.cargar_en_curso", "status": 409}
    if not items:
        return {"ok": False, "error": "localhost.err.formato", "status": 400}
    return {"ok": True, "job": vista(start(items, prefs))}


def ack():
    global _JOB
    with _LOCK:
        if _JOB is not None and _JOB.get("done"):
            _JOB = None


def vista(job):
    """Lo que la página y la tarjeta enseñan del job (sin rutas largas)."""
    if not job:
        return None
    return {"pasos": [{"key": s["key"], "label": s["label"], "st": s["st"], "note": str(s.get("note") or "")[:160]}
                      for s in job.get("steps") or []],
            "done": bool(job.get("done")), "ok": bool(job.get("ok")), "error": str(job.get("error") or "")[:300],
            "res": str(job.get("res") or ""), "avisos": [str(w)[:200] for w in job.get("warns") or []][:10],
            "nombres": [n for n, v in (job.get("res_map") or {}).items() if v == "ok"][:50]}


def _load(folder, name, **kw):
    """agent_admin.load con el nombre solo si cambia el de su cerebro (choque de nombres)."""
    if name:
        info = agent_admin.inspect_brain(folder)
        if (info.get("name") or "") != name:
            kw["name"] = name
    return agent_admin.load(folder, **kw)


def _worker(job):
    """Corre agent_admin.load con los pasos en vivo; captura la salida del proceso y la restaura SIEMPRE."""
    def _out(*a, **_k):
        txt = " ".join(str(x) for x in a)
        if "WARN" in txt:
            job["warns"].append(txt.split("WARN:", 1)[-1].strip())

    def _on_step(key, st, note=""):
        for s in job["steps"]:
            if s["key"] == key:
                s["st"], s["note"] = st, str(note or "")
                break
        if st in ("ok", "warn", "fail", "skip"):
            lbl = next((s["label"] for s in job["steps"] if s["key"] == key), key)
            job["live"].append((st, lbl + ((" — " + str(note)) if note else "")))
            del job["live"][:-60]

    STDIO_LOCK.acquire()
    old = (sys.stdout, sys.stderr, sys.stdin)
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    sys.stdin = io.StringIO("")
    try:
        prefs = job.get("prefs") or {}
        if job["bulk"]:
            oks = 0
            for s, (name, folder) in zip(job["steps"], job["items"]):
                s["st"] = "run"
                try:
                    ok, res = _load(folder, name, out=_out, **prefs)
                except Exception as e:
                    ok, res = False, "%s: %s" % (type(e).__name__, e)
                s["st"] = "ok" if ok else "fail"
                s["note"] = "" if ok else str(res)
                job["res_map"][res if ok else (name or folder)] = "ok" if ok else ("err:%s" % res)
                job["live"].append((s["st"], (name or folder) + ("" if ok else " — %s" % res)))
                oks += 1 if ok else 0
            job["ok"] = oks == len(job["steps"])
            job["res"] = "%d/%d" % (oks, len(job["steps"]))
        else:
            name, folder = job["items"][0]
            try:
                ok, res = _load(folder, name, out=_out, progress=_on_step, **prefs)
            except Exception as e:
                ok, res = False, "%s: %s" % (type(e).__name__, e)
            job["ok"] = bool(ok)
            job["res"] = str(res)
            if not ok:
                job["error"] = str(res)
            job["res_map"][res if ok else (name or folder)] = "ok" if ok else ("err:%s" % res)
    finally:
        try:
            sys.stdout, sys.stderr, sys.stdin = old
        except Exception:
            pass
        STDIO_LOCK.release()
        for s in job["steps"]:                    # nada se queda «corriendo»
            if s["st"] in ("pend", "run"):
                s["st"] = "skip"
        job["t1"] = time.monotonic()
        job["done"] = True
