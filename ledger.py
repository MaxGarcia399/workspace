#!/usr/bin/env python3
"""WORKSPACE · ledger — historial append-only de corridas de eval (F2).

Cada corrida del golden set se APILA como una línea JSONL en
`<brain>/STATE/evals/ledger.jsonl`. De ahí salen tendencia, detección de
regresión y comparación entre corridas (panel). JSONL y NO SQLite a propósito:
respeta el modelo de sync por archivos de Obsidian — sin blobs binarios que
choquen entre máquinas (plan §Capa 4).

Cada registro lleva **provenance de engine/modelo OBLIGATORIA** (§0.5): sin
saber con qué engine/modelo corrió el sujeto y el juez, los números no son
comparables (no hay model-A/B ni regresión válida). La detección de regresión
compara SOLO corridas del mismo engine+juez para no mezclar peras con manzanas.

Cero dependencias (stdlib, 3.9+). Falla-suave: un ledger podrido nunca tumba
nada — línea inválida se salta, escritura que falla devuelve False.
"""
import datetime
import json
import os


def ledger_path(brain):
    return os.path.join(os.path.expanduser(brain), "STATE", "evals", "ledger.jsonl")


def _now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _run_id():
    return os.urandom(6).hex()


def entry_from_report(report, subject, suite="golden", ts=None, run_id=None):
    """Construye el registro del ledger desde el reporte de eval_runner.run().
    La provenance (engine/modelo/runner) sale del propio reporte."""
    prov = report.get("provenance", {}) or {}
    return {
        "ts": ts or _now_iso(),
        "run_id": run_id or _run_id(),
        "subject": subject,
        "suite": suite,
        "runner": prov.get("subject_runner", "?"),
        "n": report.get("total", 0),
        "pass_rate": report.get("pass_rate"),
        "passed": report.get("passed", 0),
        "failed": report.get("failed", 0),
        "errors": report.get("errors", 0),
        "dims": report.get("dim_avg", {}),
        "subject_engine": prov.get("subject_engine", "?"),
        "subject_model": prov.get("subject_model", "?"),
        "judge_engine": prov.get("judge_engine", "?"),
        "judge_model": prov.get("judge_model", "?"),
    }


def append(brain, report, subject=None, suite="golden", ts=None, run_id=None):
    """Apila una corrida al ledger del cerebro. Devuelve el entry escrito, o
    None si no se pudo (falla-suave — NUNCA levanta; el eval no debe morir
    porque el historial falle). Append atómico de una línea JSONL."""
    subject = subject or os.path.basename(os.path.normpath(os.path.expanduser(brain)))
    entry = entry_from_report(report, subject, suite=suite, ts=ts, run_id=run_id)
    path = ledger_path(brain)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return None
    return entry


def load(brain):
    """Todas las corridas del ledger (orden de archivo = orden temporal).
    Falla-suave: archivo ausente o línea podrida → se salta. Nunca levanta."""
    out = []
    try:
        with open(ledger_path(brain), encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    out.append(d)
    except OSError:
        return []
    return out


def _pr(e):
    """pass_rate numérico de un entry, o None si no lo tiene."""
    v = e.get("pass_rate")
    return v if isinstance(v, (int, float)) else None


def trend(entries, subject=None):
    """Serie temporal [(ts, pass_rate), …] para un sujeto (o todos), en orden.
    Solo entries con pass_rate numérico."""
    seq = [e for e in entries if subject is None or e.get("subject") == subject]
    return [(e.get("ts"), _pr(e)) for e in seq if _pr(e) is not None]


def _engine_key(e):
    """Firma de comparabilidad: mismo sujeto+engine+juez → números comparables."""
    return (e.get("subject"), e.get("subject_engine"), e.get("subject_model"),
            e.get("judge_engine"), e.get("judge_model"))


def _median(nums):
    s = sorted(nums)
    n = len(s)
    if n == 0:
        return None
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def detect_regression(entries, subject=None, window=5, drop=0.1):
    """¿La ÚLTIMA corrida del sujeto cayó vs. la mediana de las anteriores del
    MISMO engine+juez? (comparabilidad, §Capa 4). Devuelve dict:
      {regression: bool, latest, median, window, delta}  ó  None si no hay
    suficiente historial comparable (nunca inventa una alarma sin datos).

    `window` = cuántas corridas previas comparables se miran; `drop` = caída
    mínima de pass_rate para marcar regresión (default 0.10 = 10 pts)."""
    seq = [e for e in entries
           if (subject is None or e.get("subject") == subject) and _pr(e) is not None]
    if len(seq) < 2:
        return None
    latest = seq[-1]
    key = _engine_key(latest)
    # corridas PREVIAS comparables (mismo engine+juez), las últimas `window`
    prev = [e for e in seq[:-1] if _engine_key(e) == key][-window:]
    if not prev:
        return None                       # sin base comparable → sin veredicto
    med = _median([_pr(e) for e in prev])
    cur = _pr(latest)
    if med is None or cur is None:        # (guardado arriba; explícito para claridad)
        return None
    return {
        "regression": cur < med - drop,
        "latest": cur,
        "median": round(med, 4),
        "window": len(prev),
        "delta": round(cur - med, 4),
    }
