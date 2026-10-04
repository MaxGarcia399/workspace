#!/usr/bin/env python3
"""WORKSPACE · progress — progreso ESTRUCTURADO en vivo de un agente.

Un agente en sesión interactiva publica sus pasos (hecho/ahora/pendiente) en
`<brain>/STATE/progress.json` para que el panel muestre su PROCESO real en vivo
(no datos mock). Hermano de `now.json` (que lleva task/state grueso) — NO lo
pisa; el panel cae a now.json si progress falta o está rancio.

Fuente natural de los pasos: la lista de tareas del harness (done/now/todo). La
sesión llama a `publish()` al mover sus tareas.

Contrato (acordado con Zenith por el bus, 2026-07-11):
    {
      "task":   "construir X",
      "steps":  [{"label": "...", "state": "done|now|todo"}],
      "pct":    0-100,                 # opcional; si falta se deriva done/total
      "since":  "<iso>",               # arranque (para elapsed) — se preserva
      "updated":"<iso>",
      "engine": "claude-code",         # motor en uso (verificación de harness)
      "model":  "opus"                 # modelo en uso
    }

Barato, falla-suave, sin PII: los `label` los pone el agente; el panel scrubbea
rutas al leer. Escritura ATÓMICA. Autobus (dispatch read-only) NO usa esto —
no puede escribir el cerebro; su estado grueso lo publica el daemon aparte.
Cero deps (stdlib, 3.9+).
"""
import datetime
import json
import os

STATE_DIRNAME = "STATE"
FILENAME = "progress.json"
STALE_SECONDS = 10 * 60          # más viejo que esto → el panel lo ignora (idle)
VALID_STATES = ("done", "now", "todo")


def _now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def progress_path(brain):
    return os.path.join(os.path.expanduser(brain), STATE_DIRNAME, FILENAME)


def _clean_steps(steps):
    """Normaliza los pasos: [{label:str, state:done|now|todo}]. Descarta basura,
    normaliza estado desconocido a 'now'. Cota de 40 pasos."""
    out = []
    for s in (steps or []):
        if not isinstance(s, dict):
            continue
        label = str(s.get("label") or "").strip()
        if not label:
            continue
        state = s.get("state")
        if state not in VALID_STATES:
            state = "now"
        out.append({"label": label[:120], "state": state})
        if len(out) >= 40:
            break
    return out


def _derive_pct(steps):
    if not steps:
        return None
    done = sum(1 for s in steps if s.get("state") == "done")
    return int(round(done / len(steps) * 100))


def publish(brain, task, steps, pct=None, engine=None, model=None):
    """Escribe/actualiza progress.json. Devuelve el dict escrito, o None si no
    se pudo (falla-suave — NUNCA levanta; publicar progreso jamás debe romper la
    sesión). `since` se PRESERVA del archivo previo (arranque de la tarea)."""
    try:
        brain = os.path.expanduser(brain)
        steps = _clean_steps(steps)
        prev = read(brain, ignore_stale=True) or {}
        since = prev.get("since") or _now_iso()
        # si cambió la tarea, reinicia el 'since' (nueva tarea = nuevo cronómetro)
        if prev.get("task") and prev.get("task") != (task or ""):
            since = _now_iso()
        entry = {
            "task": str(task or "")[:200],
            "steps": steps,
            "pct": pct if isinstance(pct, (int, float)) else _derive_pct(steps),
            "since": since,
            "updated": _now_iso(),
            "engine": (engine or prev.get("engine") or "") or None,
            "model": (model or prev.get("model") or "") or None,
        }
        path = progress_path(brain)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(entry, fh, ensure_ascii=False)
        os.replace(tmp, path)
        return entry
    except Exception:
        return None


def read(brain, ignore_stale=False):
    """progress.json de `brain` → dict normalizado, o None (falta / rancio /
    roto). Falla-suave. `ignore_stale` lo usa publish para preservar `since`."""
    try:
        path = progress_path(brain)
        if not ignore_stale:
            try:
                if datetime.datetime.now().timestamp() - os.path.getmtime(path) > STALE_SECONDS:
                    return None          # rancio: mejor idle que un progreso viejo
            except OSError:
                return None
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        if not isinstance(d, dict):
            return None
        return {
            "task": str(d.get("task") or ""),
            "steps": _clean_steps(d.get("steps")),
            "pct": d.get("pct") if isinstance(d.get("pct"), (int, float)) else _derive_pct(_clean_steps(d.get("steps"))),
            "since": str(d.get("since") or ""),
            "updated": str(d.get("updated") or ""),
            "engine": str(d.get("engine") or "") or None,
            "model": str(d.get("model") or "") or None,
        }
    except (OSError, ValueError):
        return None


def clear(brain):
    """Borra progress.json (fin de tarea → el panel cae a now.json/idle)."""
    try:
        os.remove(progress_path(brain))
    except OSError:
        pass
