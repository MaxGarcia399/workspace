#!/usr/bin/env python3
"""WORKSPACE hook · session_end — la memoria de la pestaña al cerrar (memoria v1).

Corre en CADA cierre de CUALQUIER motor: el hook nativo de Claude Code, el
cierre normal de los envueltos y el cierre tardío de pending_runs (la X en
Windows). Todo sin IA, en milisegundos (memoria.al_cerrar):

  1. maleta   → extracto de la conversación (últimos mensajes del socio, la
                última respuesta, archivos tocados) en
                STATE/sessions/<socio>/maleta/<pestaña>.md: el próximo motor
                que abra la pestaña sabe en qué quedó este.
  2. memoria  → datos y preferencias de la pestaña suben a STATE/MEMORY.md.
  3. compactar→ diario largo: Vigente + 10 notas; lo viejo al archivo del mes.
  4. MEMORY   → más de 200 líneas: lo más viejo de la sección de Workspace
                pasa a STATE/memoria-archivo/.
  5. OpenClaw → lo que dejó suelto en la raíz se mueve a motores/openclaw/.

Lee el payload JSON de stdin. Silencioso y falla-suave (jamás rompe el cierre).
Kill-switch: WORKSPACE_NO_MEMORIA=1. Cero dependencias (3.9+).
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

# Transiciones de media sesión de Claude Code: no son un cierre.
SKIP_REASONS = {"clear", "resume"}


def main():
    if os.environ.get("WORKSPACE_NO_MEMORIA"):
        return
    try:
        # Es limpieza del cierre: un 2º Ctrl+C en la consola (opencode y codex
        # se cierran así) no debe cortarla a medias (prueba real 2026-10-17).
        import signal
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError, AttributeError):
        pass
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    if not isinstance(data, dict) or data.get("reason") in SKIP_REASONS:
        return
    tab = (os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS")
           or data.get("tab") or "").strip()
    if not tab:
        _log({"sin_pestana": True, "engine": data.get("engine") or ""})
        return
    res, brain = {}, ""
    try:
        import memoria
        brain = memoria.raiz_cerebro(os.environ.get("WORKSPACE_BRAIN") or data.get("cwd") or "")
        res = memoria.al_cerrar(brain, tab, motor=data.get("engine") or "claude-code",
                                transcript=data.get("transcript_path") or data.get("transcript_backup") or "",
                                desde=data.get("started") or 0)
        try:
            import events
            events.record("agent_step", payload={"event": "memoria_cierre", "tab": tab,
                                                 **{k: (v if isinstance(v, (int, bool)) else str(v))
                                                    for k, v in res.items()}},
                          source="memoria_cierre", brain=brain)
        except Exception:
            pass
    except Exception as exc:
        res = {"error": "%s: %s" % (type(exc).__name__, str(exc)[:200])}
    _log(dict(res, tab=tab, engine=data.get("engine") or "claude-code", brain=brain))


def _log(rec):
    """Rastro local de cada cierre (<estado>/logs/memoria.log): lo que pasó,
    también cuando algo falla — sin esto un cierre fallido era invisible."""
    try:
        import datetime
        import paths
        d = os.path.join(paths.state_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        rec = dict(rec, ts=datetime.datetime.now().isoformat(timespec="seconds"))
        with open(os.path.join(d, "memoria.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: (v if isinstance(v, (int, bool, str)) else str(v))
                                 for k, v in rec.items()}, ensure_ascii=False) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
