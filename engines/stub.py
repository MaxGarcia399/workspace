"""WORKSPACE · engines/stub.py — motor STUB (eco, sin LLM): prueba viva del switch.

Existe para demostrar END-TO-END que WORKSPACE puede registrar, seleccionar y
lanzar un motor que NO es Claude Code: dispatch lo carga por nombre (contrato
engines/CONTRACT.md), el resolver declarativo (model_resolver + providers/stub.json)
le asigna provider y modelo por tarea, y el "loop" es un eco trivial — cero LLM,
cero red, cero credenciales.

Cómo se selecciona (selection-source policy — elección explícita = estricta):
    python3 dispatch.py zenith --engine stub --plan   # wiring sin lanzar
    python3 dispatch.py zenith --engine stub          # lanza el eco
    WORKSPACE_ENGINE=stub zenith                        # por env
    "engine": "stub" en agent.json                    # permanente

Qué NO hace (honestidad): no habla con ningún modelo, no cablea eventos N9
(no tiene sesiones reales — el motor real E-2 los emite de su loop), no usa
banner/dashboard del agente. Lo que Claude Code no expone (modelo activo,
compaction, failover) aquí se MUESTRA resuelto por WORKSPACE — esa es la gracia.

Cero dependencias (stdlib, Python 3.9+). Cross-platform. Amputable (C10):
borra este archivo y `--engine stub` deja de existir; nada más cambia.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import context_budget    # noqa: E402
import model_resolver    # noqa: E402

META = {
    "name": "stub",
    "needs": [],          # nada: ni binarios, ni red, ni credenciales
    "auth": "none",
}

#: Matriz de capacidades (contrato harness-os §3; la consume harnesses.py).
CAPABILITIES = {
    "launch": "repl",             # loop propio de WORKSPACE (eco, sin LLM)
    "inject_context": "none",     # no hay a quién inyectar
    "mcp": False, "hooks": False,
    "sessions": "none",           # sin sesiones reales (honestidad del stub)
    "status_live": False, "headless": False,
}

EXIT_WORDS = ("salir", "exit", "quit", ":q")


def _resolved(cfg):
    """Resolución declarativa completa (motor→provider→modelo) para este cfg."""
    cfg = dict(cfg or {})
    cfg.setdefault("engine", "stub")
    return model_resolver.resolve(cfg, task="default")


def _window(cfg, r):
    """Ventana de contexto del modelo resuelto: engine_config.context_window
    del agente → context_windows del provider (datos, no ifs)."""
    ec = (cfg or {}).get("engine_config") or {}
    if ec.get("context_window"):
        return int(ec["context_window"])
    p, _ = model_resolver.load_provider(r.get("provider") or "")
    return int(((p or {}).get("context_windows") or {}).get(r.get("model"), 0))


def _header(cfg, r, win):
    b = context_budget.budget(win or None)
    lines = [
        "  motor       : stub  (eco sin LLM — prueba de cambio de motor)",
        "  selección   : %s (%s)" % (r["source"],
                                     "ESTRICTA — sin fallbacks" if r["strict"]
                                     else "default — fallbacks permitidos"),
        "  provider    : %s" % (r["provider"] or "(ninguno)"),
        "  modelo      : %s%s" % (r["model"] or "(ninguno)",
                                  "  [DEGRADED]" if r["degraded"] else ""),
        "  fallbacks   : %s" % (", ".join(r["fallbacks"]) or "—"),
        "  ventana     : %s → budget %d tokens%s"
        % (win or "(desconocida)", b,
           "  · régimen small-context" if context_budget.is_small_context(win)
           else ""),
        "  camino      : %s" % " → ".join(r["chain"]),
    ]
    if r["provider_errors"]:
        lines.append("  ⚠ provider  : " + " · ".join(r["provider_errors"]))
    if r["missing_env"]:
        lines.append("  ⚠ env-vars  : faltan %s" % ", ".join(r["missing_env"]))
    return lines


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    brain = (cfg or {}).get("_brain", "")
    r = _resolved(cfg)
    win = _window(cfg, r)
    line = "─" * 66

    print(line)
    print("  WORKSPACE · motor STUB — agente: %s"
          % (cfg or {}).get("display", (cfg or {}).get("name", "?")))
    print("  cerebro     : %s" % (brain or "(ninguno)"))
    for ln in _header(cfg, r, win):
        print(ln)
    print(line)
    if plan:
        print("  (plan — no se lanza nada)")
        return

    # Modo one-shot: argumentos passthrough se ecoan y se sale (scriptable).
    if passthrough:
        print("  [%s·%s] eco: %s" % (r["provider"] or "stub",
                                     r["model"] or "?", " ".join(passthrough)))
        sys.exit(0)

    # Loop trivial interactivo: eco hasta EOF o palabra de salida.
    print("  eco interactivo — escribe algo ('salir' o Ctrl-D para terminar)\n")
    tag = "[%s·%s]" % (r["provider"] or "stub", r["model"] or "?")
    while True:
        try:
            text = input("  tú > ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.strip().lower() in EXIT_WORDS:
            break
        print("  %s eco: %s" % (tag, text))
    print("  motor stub: sesión terminada (el switch funcionó — esto NO fue "
          "Claude Code).")
    sys.exit(0)


def pick(cfg):
    return ""
