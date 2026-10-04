#!/usr/bin/env python3
"""WORKSPACE · harnesses.py — registry de HARNESSES (visión Harness-OS, F1-F3).

Un **harness** es el ejecutor intercambiable que corre a un agente (Claude
Code, Codex CLI, Gemini CLI, …). En WORKSPACE el adapter de cada harness ES su
motor en `engines/<nombre>.py` (contrato en engines/CONTRACT.md): este módulo
NO inventa una capa paralela — es la vista de REGISTRO sobre los engines:

  · qué harnesses hay instalados (archivo del engine presente y cargable),
  · cuáles están LISTOS (sus binarios en PATH; con probe=True además su
    sesión/login, vía el status() del engine),
  · su matriz de CAPACIDADES (META/CAPABILITIES del engine — datos, no ifs),
  · y el BINDING agente→harness: leer el efectivo y cambiarlo PER-MÁQUINA
    (settings `agentes.<n>.engine`, tier A — el agent.json committeado no se
    toca; cambiar ESE es N3). dispatch.py ya honra ese override al lanzar,
    así que el binding del hub es automático: eliges y el próximo Enter
    lanza con ese harness, sin pasos extra.

Precedencia del motor al LANZAR (la aplica dispatch.py, aquí solo se refleja):
    --engine (cli) > WORKSPACE_ENGINE (env) > agentes.<n>.engine (per-máquina)
    > agent.json "engine" > settings modelos.default_engine.

Cero dependencias (stdlib, Python 3.9+). Falla-suave: cualquier problema
degrada a listas vacías / dicts con "error" — jamás rompe el hub.
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

#: Matriz de capacidades por DEFAULT cuando un engine no declara CAPABILITIES.
#: Claves del contrato (PLAN harness-os §3) — valores honestos y conservadores:
#:   launch          cómo arranca (native = path propio · wrapper = TUI oficial
#:                   envuelto en el ciclo neutral · repl = loop propio de WORKSPACE)
#:   inject_context  cómo llega identidad/memoria al harness (hooks = inyección
#:                   real · print = se imprime al socio · none)
#:   mcp / hooks     ¿el harness soporta MCPs / hook-system? (bool o "native")
#:   sessions        quién gestiona sesiones ("workspace" = picker/journals
#:                   propios · "vendor" = el CLI oficial · "none")
#:   status_live     ¿publica tarea-en-vivo (now.json/statusline)? (bool)
#:   headless        ¿tiene one-shot no interactivo (run_turn)? (bool)
_DEFAULT_CAPS = {
    "launch": "wrapper", "inject_context": "print", "mcp": False,
    "hooks": False, "sessions": "vendor", "status_live": False,
    "headless": False,
}

#: Orden de PRESENTACIÓN en selectores (los demás van después, alfabético).
_PREFERRED_ORDER = ("claude-code", "codex", "antigravity")


def _dispatch():
    import dispatch
    return dispatch


def installed():
    """Ids de harnesses INSTALADOS (= engines presentes en engines/*.py).
    Orden: preferidos primero, resto alfabético. Falla-suave → []."""
    try:
        ids = [i for i in _dispatch().available_engines() if i != "stub"]
        if "antigravity" in ids:
            ids = [i for i in ids if i != "gemini"]
    except Exception:
        return []
    pref = [i for i in _PREFERRED_ORDER if i in ids]
    rest = sorted(i for i in ids if i not in _PREFERRED_ORDER)
    return pref + rest


def describe(engine_id, probe=False):
    """Descriptor de UN harness: {id, name, needs, auth, capabilities,
    installed, binaries_ok, ready, detail}.

    probe=False (default, BARATO): solo mira que el engine cargue y que sus
    binarios (META.needs) estén en PATH — apto para el hub (sin spawnear CLIs
    por keypress). probe=True además consulta el status()/available() del
    engine si los expone (puede correr p.ej. `codex login status`).
    Falla-suave: errores → descriptor con ready=False + detail."""
    d = {"id": engine_id, "name": engine_id, "needs": [], "auth": "?",
         "capabilities": dict(_DEFAULT_CAPS), "installed": False,
         "binaries_ok": False, "ready": False, "detail": ""}
    try:
        mod = _dispatch().load_engine(engine_id)
    except Exception as e:
        d["detail"] = "registry roto: %s" % e
        return d
    if mod is None:
        d["detail"] = "engine no instalado o sin launch()"
        return d
    d["installed"] = True
    meta = getattr(mod, "META", None) or {}
    d["name"] = str(meta.get("name") or engine_id)
    d["needs"] = list(meta.get("needs") or [])
    d["auth"] = str(meta.get("auth") or "none")
    caps = getattr(mod, "CAPABILITIES", None)
    if isinstance(caps, dict):
        d["capabilities"] = dict(_DEFAULT_CAPS, **caps)
    missing = [b for b in d["needs"] if not shutil.which(b)]
    d["binaries_ok"] = not missing
    if missing:
        d["detail"] = "falta en PATH: " + ", ".join(missing)
        return d
    if not probe:
        d["ready"] = True          # binarios OK; login/sesión se ve con probe
        return d
    try:                           # probe profundo: el engine sabe su estado
        if hasattr(mod, "status"):
            st = mod.status() or {}
            d["ready"] = bool(st.get("ready", True))
            if not d["ready"]:
                d["detail"] = str(st.get("auth") or "sesión no activa")
        elif hasattr(mod, "available"):
            d["ready"] = bool(mod.available())
            if not d["ready"]:
                d["detail"] = "no disponible (available() → False)"
        else:
            d["ready"] = True
    except Exception as e:
        d["ready"], d["detail"] = False, "status falló: %s" % e
    return d


def registry(probe=False):
    """Lista de descriptores de TODOS los harnesses instalados (ver describe).
    El menú del hub ofrece de aquí solo los `ready` (PLAN §4)."""
    return [describe(i, probe=probe) for i in installed()]


def selectable():
    """Ids ELEGIBLES en el selector del hub: instalados + binarios en PATH
    (chequeo barato; el login se verifica al lanzar — el engine avisa claro).
    Jamás vacío si hay engines: si ninguno tiene binarios, devuelve los
    instalados (mejor ofrecer y avisar al lanzar que un selector muerto)."""
    reg = registry(probe=False)
    ok = [d["id"] for d in reg if d["ready"]]
    return ok or [d["id"] for d in reg if d["installed"]]


# ── BINDING agente → harness ────────────────────────────────────────────────

def binding(agent_name, agent_default=""):
    """Binding EFECTIVO de un agente (lo que dispatch usará al lanzar, sin
    contar --engine/env de una corrida puntual): el override per-máquina
    (settings agentes.<n>.engine) si existe, si no el default del agent.json.
    Devuelve (engine_id, source) con source ∈ {'local', 'agente'}."""
    try:
        ov = _dispatch()._settings_agent_engine(agent_name)
    except Exception:
        ov = ""
    if ov:
        return ("antigravity" if ov == "gemini" else ov), "local"
    return ("antigravity" if agent_default == "gemini" else
            (agent_default or "claude-code")), "agente"


def set_binding(agent_name, engine_id, agent_default="", actor="hub"):
    """Fija el binding PER-MÁQUINA de un agente (tier A, con gate+changelog de
    config_engine). Si `engine_id` coincide con el default del agent.json, se
    LIMPIA el override (el store no acumula redundancia y el agente vuelve a
    seguir a su spec). Devuelve {'ok': bool, ...}. Jamás toca agent.json."""
    n = str(agent_name or "").strip().lower()
    if not n:
        return {"ok": False, "error": "agente sin nombre"}
    eid = str(engine_id or "").strip()
    if eid not in installed():
        return {"ok": False, "error": "harness desconocido: %r" % eid}
    key = "agentes.%s.engine" % n
    try:
        import config_engine
        if agent_default and eid == agent_default:
            return config_engine.reset_setting(key, actor=actor)
        return config_engine.set_setting(key, eid, actor=actor)
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def cycle(agent_name, agent_default=""):
    """Avanza el binding del agente al SIGUIENTE harness elegible (circular) y
    lo persiste. Devuelve {'ok', 'engine', 'source', 'error'?} — pensado para
    el gesto del hub (una tecla = siguiente motor, guardado al instante)."""
    opts = selectable()
    if not opts:
        return {"ok": False, "error": "sin harnesses instalados"}
    cur, _src = binding(agent_name, agent_default)
    try:
        nxt = opts[(opts.index(cur) + 1) % len(opts)]
    except ValueError:            # el actual ya no es elegible → el primero
        nxt = opts[0]
    res = set_binding(agent_name, nxt, agent_default)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "no se pudo guardar")}
    eng, src = binding(agent_name, agent_default)
    return {"ok": True, "engine": eng, "source": src}


if __name__ == "__main__":        # inspección rápida: python3 harnesses.py
    probe = "--probe" in sys.argv
    print("\n  Harnesses instalados%s:\n" % (" (probe)" if probe else ""))
    for d in registry(probe=probe):
        mark = "✓" if d["ready"] else "·"
        extra = ("  — " + d["detail"]) if d["detail"] else ""
        print("  %s %-12s auth=%-13s needs=%s%s"
              % (mark, d["id"], d["auth"], ",".join(d["needs"]) or "-", extra))
    print()
