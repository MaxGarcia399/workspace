#!/usr/bin/env python3
"""WORKSPACE · workspace_hook.py — ADAPTADOR Claude Code del hook-runner (P0-1 → build B).

Cada hook nativo de Claude Code se cablea a UNA sola invocación de ejecutable:

    "<PY>" "<WORKSPACE>/workspace_hook.py" <evento-workspace>

Sin control-flow de shell (if/test/&&/||): parsea idéntico en cmd.exe,
git-bash, PowerShell o sh (argv citado, cero metacaracteres). El shell de
hooks de Claude Code en Windows NO está garantizado — ese es justo el punto.

Desde el build B (hooks portables) este módulo es SOLO el adaptador de motor:
la lógica (fan-out de listeners, gate `requires`, memoria de sesión vía
dashboard --context, merges) vive en `neutral_hooks.py` — la capa neutral que
cualquier motor puede llamar (contrato: `engines/LIFECYCLE.md`). Aquí queda lo
específico de Claude Code:

  · leer el evento de argv y el payload crudo de stdin (UNA vez, bytes).
  · delegar en `neutral_hooks.run_event(...)` con el set CLAUDE_CODE_PARITY
    (= exactamente el comportamiento de siempre; encender status/inbox para
    CC es una decisión aparte — ramas feat/agent-status / feat/inbox-on-boot).
  · traducir el `context` neutral al shape que Claude Code entiende
    (hookSpecificOutput.additionalContext) SOLO en eventos aditivos.
  · SIEMPRE exit 0 (fail-open absoluto: el runner JAMÁS bloquea).

Los `hooks/*.py` por-evento quedan IGUAL (los invoca el runner neutral) →
siguen amputables: borrar uno lo apaga, sin tocar settings.json.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import _utf8; _utf8.harden()   # B2 · UTF-8 en stdout/err antes de emitir JSON con no-ASCII
import os
import sys
import json

WORKSPACE = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)
import events         # noqa: E402  (contrato N9)
import neutral_hooks  # noqa: E402  (la lógica vive en la capa neutral)

# Eventos cuya salida se SUMA (contexto / tool-result); el resto es cleanup.
# DEBE espejear neutral_hooks._ADDITIVE: user_prompt es aditivo también aquí —
# Claude Code soporta el shape nativo (UserPromptSubmit inyecta
# additionalContext al turno); si faltara, el día que se registre un listener
# de user_prompt el install lo cablearía a UserPromptSubmit y este adaptador
# TIRARÍA su contexto en silencio.
_ADDITIVE = ("session_start", "post_tool_write", "user_prompt")
# Nombre nativo del hook CC por evento aditivo (para hookSpecificOutput).
_CC_EVENT_NAME = {"session_start": "SessionStart",
                  "post_tool_write": "PostToolUse",
                  "user_prompt": "UserPromptSubmit"}

# ── back-compat (P0-1): la implementación vive en neutral_hooks ────────────
# Aliases para callers/tests que usaban la API del runner viejo. La lógica es
# UNA sola (regla del build B: cero duplicación).
_resolve_brain = neutral_hooks._resolve_brain
_agent_cfg_for_brain = neutral_hooks._agent_cfg_for_brain
_dashboard_of = neutral_hooks._dashboard_of
_run_child = neutral_hooks._run_child
_merge_session_start = neutral_hooks._merge_session_start
_merge_post_tool = neutral_hooks._merge_post_tool


def _read_stdin():
    """Lee el stdin del runner UNA vez como bytes (se reenvía crudo a cada
    hijo). Falla-suave: stdin ausente/cerrado → b''."""
    try:
        return sys.stdin.buffer.read() or b""
    except Exception:
        return b""


def _parse(raw):
    """raw (bytes) → dict del payload del motor. Basura/vacío → {} (nunca levanta)."""
    try:
        d = json.loads(raw.decode("utf-8", "replace") or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _emit(event, ctx):
    """Traduce el `context` neutral al shape de Claude Code y lo emite.
    Fail-open: cualquier fallo → NO emite nada (jamás bloquea el arranque
    ni el tool-result — la pieza más delicada del runner)."""
    try:
        if not ctx:
            return
        name = _CC_EVENT_NAME.get(event)
        if not name:
            return
        sys.stdout.write(json.dumps(
            {"hookSpecificOutput": {"hookEventName": name,
                                    "additionalContext": ctx}},
            ensure_ascii=False))
    except Exception:
        pass


def main():
    if len(sys.argv) < 2:
        return
    event = sys.argv[1]
    if event not in events.EVENTS:
        return                              # evento desconocido → no-op (exit 0)

    raw = _read_stdin()
    data = _parse(raw)
    res = neutral_hooks.run_event(event, data, raw=raw,
                                  behaviors=neutral_hooks.CLAUDE_CODE_PARITY)

    if event in _ADDITIVE:
        _emit(event, (res or {}).get("context", ""))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass            # falla-suave absoluta: el runner JAMÁS bloquea
    sys.exit(0)
