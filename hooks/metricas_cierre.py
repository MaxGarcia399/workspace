#!/usr/bin/env python3
"""WORKSPACE hook · session_end — métricas de la sesión al cerrar (F1).

Corre en CADA cierre de CUALQUIER motor: el SessionEnd nativo de Claude Code
(payload con transcript_path, session_id, cwd), el cierre normal de los
envueltos (interactive → session_continuity.close_payload: engine, run_id,
started, tab, session_id, transcript_path) y el cierre tardío de pending_runs
(la X en Windows). Mide SOLO lo nuevo del transcript desde el último cierre
(cursor) y deja una fila de números y nombres en <estado>/metricas/ —
jamás texto de la conversación, jamás dentro del cerebro.

Sin IA, sin red. Silencioso y falla-suave: nada aquí rompe ni demora el
cierre más allá de su presupuesto (metricas.PRESUPUESTO_VIVO); lo que no
alcance se mide en el siguiente cierre de esa sesión.

Kill-switch: WORKSPACE_NO_METRICAS=1 (o `workspace metricas apagar`). El
interruptor de emergencia NO mide nada: excluye la sesión que cierra desde
que EMPEZÓ, por fuente (no apaga a los otros procesos ni lo deshace un
cierre ajeno); lo hecho con él puesto no se mide nunca, tampoco al quitarlo.
Cero dependencias (3.9+). Mac y Windows.
"""
import json
import os
import sys

try:   # Windows: UTF-8 en stdout/err (no-op en Mac)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)   # append: no cambia qué módulo homónimo de hooks/ gana


def _log(rec):
    """Rastro mínimo SOLO de fallos (<estado>/logs/metricas.log): sin esto un
    cierre que no midió sería invisible. Nunca contenido."""
    try:
        import datetime
        import paths
        d = os.path.join(paths.state_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        rec = dict(rec, ts=datetime.datetime.now().isoformat(timespec="seconds"))
        with open(os.path.join(d, "metricas.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: str(v)[:200] for k, v in rec.items()},
                                ensure_ascii=False) + "\n")
    except Exception:
        pass


def _excluir_de_emergencia(data):
    """Con WORKSPACE_NO_METRICAS: la sesión que cierra queda excluida desde que
    empezó (metricas.excluir_cierre). Nada más: ni recibo, ni medición."""
    try:
        import metricas
        metricas.excluir_cierre(data)
    except Exception as exc:
        _log({"error": type(exc).__name__, "fase": "excluir_de_emergencia"})


def main():
    emergencia = bool(os.environ.get("WORKSPACE_NO_METRICAS"))
    try:
        # limpieza del cierre: un 2º Ctrl+C en la consola (opencode y codex se
        # cierran así) no debe cortarla a medias
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError, AttributeError):
        pass
    try:
        # el lector único de los hooks: BYTES → UTF-8 (tolera el BOM). Leído
        # como texto, en Windows sin PYTHONUTF8 salía en cp1252 y una ruta con
        # «José» llegaba rota: el transcript «no existía» y no se medía.
        import _utf8
        data = _utf8.json_de_stdin()
    except Exception:
        data = {}
    if emergencia:
        _excluir_de_emergencia(data)
        return
    try:
        import metricas
        metricas.al_cerrar(data)
    except Exception as exc:
        _log({"error": type(exc).__name__, "engine": data.get("engine") or "claude-code"})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass   # falla-suave absoluta
