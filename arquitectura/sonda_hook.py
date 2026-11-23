#!/usr/bin/env python3
"""La SONDA del probador: ocupa el lugar de lanzador/hook.py en una copia del
paquete, con el mismo comando. Anota lo que el motor le manda y contesta al
inicio con una marca para ver si la inyección llega al modelo.

Lee `sonda.json` de su carpeta: {"registro": <jsonl>, "ctx": <marca>}. Anota
por evento: destino, momento, el JSON que llegó por stdin, las variables
WORKSPACE_* y las *_PLUGIN_ROOT, la carpeta y cuánto tardó la sonda. Nunca
anota otras variables (llaves). Siempre sale con 0.
"""
import json
import os
import sys
import time

T0 = time.perf_counter()
AQUI = os.path.dirname(os.path.abspath(__file__))
_TOPE = 64 * 1024

#: Cómo devuelve contexto el inicio en cada destino (sale de su documentación).
def _inyeccion(destino, texto):
    if destino in ("claude", "codex"):
        return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                  "additionalContext": texto}})
    if destino == "cursor":
        return json.dumps({"additional_context": texto})
    return texto                               # kiro, hermes, opencode: el stdout tal cual


def main(argv):
    with open(os.path.join(AQUI, "sonda.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    destino, momento = (argv + ["", ""])[:2]
    raw = sys.stdin.buffer.read()[:_TOPE]
    try:
        payload = json.loads(raw.decode("utf-8-sig") or "{}")
    except ValueError:
        payload = raw.decode("utf-8", "replace")
    env = {k: v for k, v in os.environ.items()
           if k.startswith("WORKSPACE_") or k.endswith("_PLUGIN_ROOT")}
    out = _inyeccion(destino, cfg["ctx"]) if momento == "session_start" else ""
    rec = {"t": time.time(), "destino": destino, "momento": momento, "cwd": os.getcwd(),
           "env": env, "payload": payload,
           "dur_ms": round((time.perf_counter() - T0) * 1000, 2)}
    with open(cfg["registro"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    try:
        s = main(sys.argv[1:])
        if s:
            sys.stdout.write(s)
    except Exception:
        pass
    sys.exit(0)
