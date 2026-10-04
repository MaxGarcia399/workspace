#!/usr/bin/env python3
"""WORKSPACE hook · PreToolUse / PostToolUse — telemetría en vivo (N-telem).

Appends eventos FINOS de actividad de herramientas a un archivo JSONL per-máquina
(~/.claude/workspace/telemetry/<enc>.jsonl) para el agregador de Mission Control.

SCHEMA por línea:
  {
    "ts":         <float — unix timestamp>,
    "event":      "tool_start" | "tool_end",
    "tool":       <str — nombre de la herramienta, p.ej. "Bash">,
    "session_id": <str>,
    "agent":      <str — WORKSPACE_AGENT_NAME o "" si no disponible>,
    "ms":         <int — duración en ms; solo presente en tool_end>,
    "ok":         <bool — success; solo presente en tool_end>
  }

PRIVACIDAD ABSOLUTA: NUNCA se registra tool_input, tool_response, contenido de
archivos, ni ningún campo de contenido del payload del hook. Solo metadata de
actividad (nombre del tool, timing, éxito). Mismo principio que OTel GenAI:
metadata en atributos, contenido JAMÁS en telemetría.

Kill-switches (en orden de precedencia):
  1. WORKSPACE_NO_TELEMETRY=1   → env var (más rápido, siempre gana)
  2. settings.py hooks.telemetry = off  → canal canónico de configuración

Falla-suave absoluta:
  · Cualquier excepción → exit 0 (el hook NUNCA bloquea la herramienta del socio)
  · Sin stdin / stdin basura / JSON malformado → exit 0 sin efecto
  · Directorio de telemetría no crea → exit 0 sin efecto
  · settings.py no disponible → asume habilitado (on-by-default)

Per-máquina (~/.claude/workspace/telemetry/): fuera del vault, no se sincroniza,
no se versiona. El agregador lo lee desde la misma ruta.

Naming del archivo: <enc>.jsonl donde <enc> es la codificación estilo Claude Code
de la ruta del cerebro (cwd del hook), igual que el rastro N10. Esto correlaciona
la telemetría con el cerebro sin hardcodear nombres de agente en el hook.
Si WORKSPACE_AGENT_NAME está seteado por el launcher, se usa también para el campo
`agent` (legibilidad del agregador).

Dependencias: stdlib Python 3.9+. Cross-platform (Mac/Windows/Linux).
Cero dependencias externas. Amputable (C10): borrar = feature apagada.
"""
import json
import os
import sys
import time

try:   # M1/B2 · Windows: UTF-8 en stdout/err — un hook capturado por Claude Code en
       # cp1252 reventaría al imprimir caracteres no-ASCII. No-op en Mac (UTF-8 default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── Kill-switch de entorno (el más rápido — se chequea primero) ──────────────
_ENV_KILL = "WORKSPACE_NO_TELEMETRY"


def _is_enabled():
    """True si la telemetría está habilitada. Falla-suave: cualquier error → True."""
    if os.environ.get(_ENV_KILL):
        return False
    try:
        # Importación lazy: settings.py puede no estar en el PATH en algunos
        # contextos de hook. Se busca relativo a este archivo.
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        import settings as _s
        return _s.enabled("hooks.telemetry", default=True)
    except Exception:
        return True   # sin settings → on-by-default


def _enc(path):
    """Codificación de ruta estilo Claude Code ('/a/b c' → '-a-b-c').
    Igual que dash/mission_control._enc — correlaciona sin hardcodear nombres."""
    import re
    if not path:
        return "unknown"
    return re.sub(r"[/\\. ]", "-", path) or "unknown"


def _telem_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace", "telemetry")


def _stdin_data():
    """Lee y parsea el JSON de stdin que envía Claude Code. {} si no puede."""
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def _write_event(rec, enc):
    """Append atómico (write + flush) al jsonl de telemetría. Falla-suave."""
    d = _telem_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, enc + ".jsonl")
    line = json.dumps(rec, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()


def main():
    """Punto de entrada principal. Exit 0 siempre — jamás bloquea."""
    try:
        if not _is_enabled():
            return
        data = _stdin_data()
        if not data:
            return

        hook_event = data.get("hook_event_name", "")
        tool_name = data.get("tool_name", "")
        session_id = data.get("session_id", "")
        cwd = data.get("cwd", "") or ""
        agent = os.environ.get("WORKSPACE_AGENT_NAME", "")
        ts = time.time()
        enc = _enc(cwd)

        if hook_event == "PreToolUse":
            rec = {
                "ts": ts,
                "event": "tool_start",
                "tool": tool_name,
                "session_id": session_id,
                "agent": agent,
            }
            _write_event(rec, enc)

        elif hook_event == "PostToolUse":
            # Calcular duración si hay timestamp de inicio en los datos
            # (Claude Code no entrega ms directamente, pero el agregador lo puede
            # calcular desde el par start/end). Aquí emitimos solo ts y ok.
            # NUNCA tool_response, NUNCA tool_input — solo metadata de éxito.
            rec = {
                "ts": ts,
                "event": "tool_end",
                "tool": tool_name,
                "session_id": session_id,
                "agent": agent,
                "ok": True,   # PostToolUse solo dispara en éxito
            }
            _write_event(rec, enc)

        # Cualquier otro hook_event_name se ignora silenciosamente (falla-suave)

    except Exception:
        pass  # Falla-suave absoluta: jamás propagar excepciones


if __name__ == "__main__":
    main()
