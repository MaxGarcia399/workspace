#!/usr/bin/env python3
"""workflows.steps.suite — wrap del gate de la suite (`tests/run.py`).

El MISMO gate que `_suite_green` de front.py (integrate/promote), como paso
det del runner: corre `python3 tests/run.py` del repo y reporta VERDE/ROJA.
En dry no ejecuta nada — imprime el comando (convención de _suite_green).

Timeout (v1.1): el subproceso corre con corte DURO — `timeout:` del paso o
DEFAULT_TIMEOUT. Al vencer, el proceso se mata y el paso FALLA con detalle
(jamás cuelga el run para siempre). Un timeout se trata como transitorio
(el runner puede reintentar con backoff si el paso declara retry)."""
import os
import subprocess
import sys

DEFAULT_TIMEOUT = 900          # s — el suite-gate real puede pasar de 5 min


def _timeout(step):
    try:
        t = float(step.get("timeout") or 0)
    except (TypeError, ValueError):
        t = 0
    return t if t > 0 else DEFAULT_TIMEOUT


def green(ctx, step):
    """Paso/verify det: suite del repo VERDE (rc=0). Contrato de steps/."""
    repo = ctx.get("repo") or os.getcwd()
    cmd = [sys.executable, os.path.join(repo, "tests", "run.py")]
    if ctx.get("dry"):
        return {"ok": True, "detail": "dry: $ " + " ".join(cmd)}
    t = _timeout(step)
    try:
        rc = subprocess.call(cmd, timeout=t)
    except subprocess.TimeoutExpired:
        # subprocess.call mata el proceso al vencer (Popen ctx-manager):
        # el paso falla con detalle — el run jamás queda colgado.
        return {"ok": False,
                "detail": "suite ABORTADA por timeout (%.0fs) — el proceso "
                          "fue terminado; el paso falla, no cuelga" % t,
                "artifacts": {"suite_rc": None, "suite_timeout_s": t}}
    return {"ok": rc == 0,
            "detail": "suite %s (rc=%s)" % ("VERDE" if rc == 0 else "ROJA", rc),
            "artifacts": {"suite_rc": rc}}
