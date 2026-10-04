"""WORKSPACE · engines/_template.py — PLANTILLA y CONTRATO de un motor.

Para crear un motor nuevo: copia este archivo a engines/<tu-motor>.py (sin guion
bajo) e implementa launch(). Un agente lo usa declarando "engine": "<tu-motor>" en
su agent.json. El dispatcher lo carga solo por nombre — NO se toca dispatch.py.

══════════════════════════ CONTRATO ══════════════════════════
Lo que el dispatcher (dispatch.py) espera de un motor:

  launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True)   [OBLIGATORIO]
      Arranca el agente con este motor. Normalmente NO retorna (hace exec del
      runtime) o termina con sys.exit(code). Si plan=True NO lanza nada: imprime
      el "wiring" (qué correría + chequeos de salud) y vuelve — sirve de validación
      (`dispatch.py --plan <agente>`).

  pick(cfg) -> str                                                            [OPCIONAL]
      Devuelve una elección de sesión/pestaña sin lanzar (flujos especiales).
      Si tu motor no tiene menú, omite la función o devuelve "".

  META = {...}                                                               [OPCIONAL]
      Metadatos para info/plan: nombre legible, qué necesita, tipo de auth.

  CAPABILITIES = {...}                                                       [OPCIONAL]
      Matriz de capacidades del harness (contrato harness-os §3) — la consume
      harnesses.py para el registry y el selector del hub. Claves:
        launch ("native"/"wrapper"/"repl") · inject_context ("hooks"/
        "project-doc"/"print"/"none") · mcp · hooks · sessions ("workspace"/
        "vendor"/"none") · status_live · headless. Omitida → defaults
        conservadores (honestos).

  status() -> dict                                                           [OPCIONAL]
      Estado honesto del motor: {"ready": bool, ...}. harnesses.describe(id,
      probe=True) y doctor lo consultan. Solo inspección — puede spawnear un
      chequeo barato (p.ej. `codex login status`), jamás lanza al agente.

  inject_context(cfg) -> dict                                                [OPCIONAL]
      Materializa la IDENTIDAD del agente (cerebro) en el formato que ESTE
      harness entiende, SIN duplicarla — el cerebro es la única fuente de
      verdad. Patrón de referencia: engines/codex.py genera un AGENTS.md
      PUNTERO (marcado WORKSPACE:GENERATED) que manda leer el doc de identidad
      (`identity_doc` del agent.json, default CLAUDE.md). Un archivo propio
      del socio jamás se toca. Falla-suave: {'ok','action','path','detail'}.

cfg (dict del agente, ya resuelto por dispatch.py) trae:
  cfg["name"], cfg["display"], cfg["engine"]
  cfg["_brain"]    → ruta absoluta al cerebro (vault) del agente
  cfg["_scripts"]  → dict de scripts con {brain} ya expandido (banner, dashboard, …)
  cfg["_dir"]      → carpeta del agente en agents/<dir>
  cfg.get("engine_config")  → bloque declarativo opcional del motor (ver CONTRACT.md)

Reglas: cero dependencias (stdlib, Python 3.9+). Cross-platform (cuidado con el
entorno Windows del equipo: usa os.path, evita exec-only-POSIX sin fallback). Credenciales
NUNCA hardcoded ni en el repo — leerlas de entorno / ~/.claude/workspace/.
═══════════════════════════════════════════════════════════════
"""
import sys


META = {
    "name": "template",   # nombre legible del motor
    "needs": [],          # binarios/cosas requeridas (ej. ["ollama"] o ["claude"])
    "auth": "none",       # none | oauth | api-key | local
}


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    brain = cfg.get("_brain", "")
    ec = cfg.get("engine_config", {})
    if plan:
        line = "─" * 60
        print(line)
        print(f"  WORKSPACE · plan — motor TEMPLATE — agente: {cfg.get('display', cfg.get('name'))}")
        print(f"  cerebro       : {brain}")
        print(f"  engine_config : {ec or '(ninguno)'}")
        print(f"  passthrough   : {passthrough}")
        print("  (plantilla — no lanza nada real)")
        print(line)
        return
    print("WORKSPACE: 'template' es solo una plantilla de motor. "
          "Cópiala a engines/<tu-motor>.py e implementa launch() (ver engines/CONTRACT.md).")
    sys.exit(1)


def pick(cfg):
    return ""
