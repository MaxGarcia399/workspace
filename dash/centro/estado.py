#!/usr/bin/env python3
"""WORKSPACE · dash.centro.estado — snapshot AGREGADO del estado vivo de agentes.

La capa read-only que junta TODAS las fuentes que ya existen en el harness
(ARQUITECTURA.md §1) en un solo dict limpio que el front del Centro (o un
agente por CLI) consume sin saber dónde vive cada dato:

    cuenta    ← ~/.claude/workspace/usage.json    (statusline la stampea)
    latido    ← heartbeat.py (config + presupuesto + silencio)
    agentes[] ← por agente del registry (o `brains` inyectado):
                  now       ← <BRAIN>/STATE/now.json  (estado+tarea en vivo)
                  inbox     ← messages.inbox(brain, agente)  (pendientes)
                  worktrees ← ~/.claude/workspace/worktree-owners.json
                  misiones  ← taskboard (conteo por fase)
    taskboard ← dash.centro.tareas.summary()
    warns     ← dash.dev.liveness.check()  (worktrees colgados)

CONTRATO — falla-suave POR FUENTE: una fuente ausente/corrupta/ilegible deja
su campo en None (o {} / []) y el resto del snapshot sale completo; snapshot()
JAMÁS levanta. Solo LECTURA: este módulo no escribe nada, nunca.

Honestidad de la energía (DECISIONES.md §3 — ⚠ pendiente del socio): la ventana
de 5 h es de la CUENTA, no del agente — por eso `cuenta` va a nivel GLOBAL del
snapshot y NO se pinta por agente. `context_pct` tampoco se reparte: es de la
ÚLTIMA sesión que stampeó. El split real por agente requiere el stamp
per-agente (ARQUITECTURA §4, por construir) — cuando exista, se agrega aquí.
"""
import json
import os
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USAGE_STALE_SEC = 20 * 60      # mismo criterio que heartbeat.py


def _top_import(name):
    """Importa un módulo top-level del harness aunque el caller no traiga ROOT
    en sys.path (mismo patrón que dash.dev.liveness). Puede levantar — cada
    fuente lo envuelve en try/except."""
    try:
        return __import__(name)
    except ImportError:
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        return __import__(name)


def _workspace_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ── fuentes (cada una falla-suave e independiente) ───────────────────────────
def _cuenta(now_ts=None):
    """usage.json normalizado → {energia_pct, five_hour_pct, five_hour_resets_at,
    seven_day_pct, context_pct, stamped, stale} o None (ausente/ilegible)."""
    raw = _read_json(os.path.join(_workspace_dir(), "usage.json"))
    if raw is None:
        return None
    try:
        pct = float(raw["five_hour_pct"])
    except (KeyError, TypeError, ValueError):
        return None
    try:
        import time as _time
        now = float(now_ts) if now_ts is not None else _time.time()
        stamped = float(raw.get("stamped") or 0)
        stale = (now - stamped) > USAGE_STALE_SEC
    except (TypeError, ValueError):
        stamped, stale = None, True

    def _num(key):
        v = raw.get(key)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    return {
        "energia_pct": max(0.0, min(100.0, 100.0 - pct)),
        "five_hour_pct": pct,
        "five_hour_resets_at": _num("five_hour_resets_at"),
        "seven_day_pct": _num("seven_day_pct"),
        "context_pct": _num("context_pct"),
        "stamped": raw.get("stamped"),
        "stale": bool(stale),
    }


def _latido():
    """Turno/presupuesto del heartbeat → {mode, quiet_hours, quiet, budget:{pct,
    cap, ok, resets_at, stale}} o None si heartbeat no está/está roto."""
    try:
        hb = _top_import("heartbeat")
        cfg = hb.get_config()
        u = hb.read_usage()
        return {
            "mode": cfg.get("mode"),
            "quiet_hours": cfg.get("quiet_hours", ""),
            "quiet": bool(hb.in_quiet_hours(cfg)),
            "budget": {
                "pct": u["pct"] if u else None,
                "cap": cfg.get("budget_cap_pct"),
                "ok": hb.budget_ok(cfg),
                "resets_at": u["resets_at"] if u else None,
                "stale": u["stale"] if u else True,
            },
        }
    except Exception:
        return None


def _now_json(brain):
    """<BRAIN>/STATE/now.json → {task, state, since, updated} o None. Un state
    desconocido/ausente se normaliza a "working" (mismo criterio que la
    statusline: un now.json viejo jamás rompe)."""
    if not brain:
        return None
    raw = _read_json(os.path.join(brain, "STATE", "now.json"))
    if raw is None:
        return None
    state = raw.get("state")
    if state not in ("working", "blocked", "done"):
        state = "working"
    return {
        "task": raw.get("task") if isinstance(raw.get("task"), str) else "",
        "state": state,
        "since": raw.get("since", "") or "",
        "updated": raw.get("updated", "") or "",
    }


def _inbox_count(brain, agent):
    """Mensajes `pending` para el agente en su cerebro → int, o None si el bus
    no está disponible / el cerebro no se resolvió."""
    if not brain:
        return None
    try:
        messages = _top_import("messages")
        return len(messages.inbox(brain, agent))
    except Exception:
        return None


def _worktrees_by_agent():
    """worktree-owners.json agrupado por agente → {agente: [{branch, path,
    since, pool}]}. {} si el registry falta / está corrupto."""
    out = {}
    try:
        from dash.dev import _worktrees
        owners = _worktrees.load_owners()
        for branch in sorted(owners):
            info = owners[branch]
            if not isinstance(info, dict):
                continue
            agent = (info.get("agent") or "?").strip().lower() or "?"
            out.setdefault(agent, []).append({
                "branch": branch,
                "path": info.get("path", "") or "",
                "since": info.get("since", "") or "",
                "pool": bool(info.get("pool")),
            })
    except Exception:
        return {}
    return out


def _missions_by_agent():
    """Conteo de misiones vivas por agente y fase → {agente: {plan,exec,review,
    done}}. {} si el taskboard no está disponible."""
    out = {}
    try:
        from dash.centro import tareas
        for m in tareas.list_missions():
            a = m.get("agent") or "?"
            per = out.setdefault(a, {p: 0 for p in tareas.PHASES})
            per[m["phase"]] = per.get(m["phase"], 0) + 1
    except Exception:
        return {}
    return out


def _taskboard_summary():
    try:
        from dash.centro import tareas
        return tareas.summary()
    except Exception:
        return None


def _warns():
    """Liveness (worktrees colgados). Sin agent/brain: solo señal de worktrees —
    el inbox ya va por-agente en el snapshot. [] si liveness no está."""
    try:
        from dash.dev import liveness
        return liveness.check()
    except Exception:
        return []


def _registered_brains():
    """{agente: cerebro} del registry (vía messages, que ya resuelve igual que
    el dispatcher). {} falla-suave."""
    try:
        messages = _top_import("messages")
        return messages.registered_brains()
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════
def snapshot(brains=None, now_ts=None):
    """El estado agregado del olimpo, listo para pintar o para un agente:

        { ts, cuenta, latido, agentes: [ {name, brain, now, inbox_pending,
          worktrees, misiones} ], taskboard, warns }

    `brains` (dict {agente: ruta_cerebro}) inyectable — tests herméticos y
    fronts que ya conocen su registry; None → registry real. `now_ts` (epoch)
    inyectable para el cálculo de staleness. JAMÁS levanta; cada fuente
    ausente → None/{}/[] en su campo."""
    try:
        bm = brains if isinstance(brains, dict) else _registered_brains()
        trees = _worktrees_by_agent()
        missions = _missions_by_agent()
        agentes = []
        for name in sorted(bm):
            brain = bm.get(name) or None
            agentes.append({
                "name": name,
                "brain": brain,
                "now": _now_json(brain),
                "inbox_pending": _inbox_count(brain, name),
                "worktrees": trees.get((name or "").lower(), []),
                "misiones": missions.get((name or "").lower()) or missions.get(name),
            })
        return {
            "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "cuenta": _cuenta(now_ts=now_ts),
            "latido": _latido(),
            "agentes": agentes,
            "taskboard": _taskboard_summary(),
            "warns": _warns(),
        }
    except Exception:
        # última red: hasta un bug interno devuelve un snapshot mínimo válido
        return {"ts": None, "cuenta": None, "latido": None, "agentes": [],
                "taskboard": None, "warns": []}
