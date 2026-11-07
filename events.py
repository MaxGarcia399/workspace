#!/usr/bin/env python3
"""WORKSPACE · events — contrato de eventos del harness (N9), como DATOS.

La spec humana (qué significa cada evento, payloads, observer vs middleware,
qué no expone cada motor) vive en `engines/EVENTS.md`. Este módulo es la misma
tabla en forma ejecutable, y es la ÚNICA fuente de verdad del wiring:

  · `install.build_hooks` DERIVA de aquí el bloque `hooks` que siembra en el
    settings.local.json de cada cerebro (ya no hay scripts hardcodeados ahí).
  · `doctor` (fase 5) valida los cerebros contra ESTE contrato — lo que el
    contrato dice que debe estar cableado, no una lista propia.

Agregar/quitar un listener (N2 memory_flush, N15 security_guidance, …) se hace
SOLO en `LISTENERS`; install y doctor lo siguen solos.

NO es un hook-system: es una capa declarativa fina sobre los hooks nativos del
motor. Cada engine declara en ENGINE_MAP cómo cablea cada evento WORKSPACE a su
mecanismo propio; None = ese motor no lo expone (pendiente motor #2, se
documenta — no se simula en silencio).

Cero dependencias (stdlib puro, Python 3.9+). Mac y Windows.

Además del contrato declarativo, este módulo ofrece el RASTRO unificado de
actividad del harness (N10): `~/.claude/workspace/events/YYYY-MM-DD.jsonl`.
Placement según análisis §1.3.1 — conocimiento al vault, EJECUCIÓN a
`~/.claude/workspace/` local (per-máquina, gitignored, reconstruible).

UN solo schema por línea (N10, vocabulario SSE de Odysseus — probado, no
inventado):

    {"ts", "kind", "source", "agent", "brain", "payload"}

  · kind    — taxonomía SSE de Odysseus: delta / tool_start / tool_output /
              agent_step / metrics / done. Hoy el harness emite agent_step
              (pasos de pipelines: audits, propuestas, workflows) y
              tool_output (post_tool_write); el resto queda reservado para
              el tee de stream-json (activity-strip, dashboard F2+).
  · source  — quién escribió (script emisor: nightly.py, skill_loop.py, …).
  · agent / brain — a quién pertenece la actividad (brain se extrae del
              payload si el emisor lo traía; agent opcional).
  · payload — metadata acotada del paso (strings recortados a _CLIP chars:
              actividad, NUNCA contenido de transcripts). El evento N9 que
              lo originó viaja como payload["event"].

APIs: `record(kind, …)` es el escritor núcleo; `emit(event, payload,
emitter)` es la fachada N9 (firma estable — skill_audit.py, nightly.py y
hooks la llaman) que mapea evento→kind vía EVENT_KIND; `read_events()` es
el lector del dashboard (sección Actividad), normaliza líneas legacy
pre-N10 (`{ts, event, emitter, …payload}` aplanado) al schema unificado.

Resolución de la tensión "dos logs sin schema común" (§1.3.1): este stream
es EL lugar de la actividad operacional. `skill_loop.skills-events.jsonl`
sigue existiendo como índice FUNCIONAL con cursor (lo consume sync_events),
pero espeja cada evento aquí. Un evento = un
record aquí, sea directo (emit) o espejo (_audit/log_event).

Falla-suave absoluta: record/emit/read_events jamás levantan.
"""
import datetime as _dt
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
import json as _json
import os as _os

# ── modos (distinción de Hermes) ──────────────────────────────────────────
# observer   = mira el payload y actúa por fuera; no cambia lo que el motor
#              le da al modelo (variantes aditivas acotadas: inyectar contexto
#              en session_start, instrucciones al compactador en pre_compact).
# middleware = puede MUTAR el payload en tránsito (reescribir/filtrar/bloquear).
#              En v1 SOLO pre_prompt es middleware — todo lo demás es observer
#              por diseño (hooks best-effort, jamás en el camino crítico).
OBSERVER, MIDDLEWARE = "observer", "middleware"

# ── vocabulario v1: los eventos PROPIOS de WORKSPACE ────────────────────────
EVENTS = {
    "session_start": {
        "mode": OBSERVER,
        "desc": "arranca una sesión interactiva (startup/resume/compact); "
                "lo que el listener imprime se SUMA al contexto (aditivo)",
    },
    "session_end": {
        "mode": OBSERVER,
        "desc": "cierra una sesión (exit/logout/clear/...); cleanup-only — "
                "la salida se ignora, no puede bloquear ni invocar al modelo",
    },
    "pre_compact": {
        "mode": OBSERVER,
        "desc": "el contexto está por compactarse (manual/auto); puede sugerir "
                "qué preservar, no edita el contexto — N2 cuelga aquí",
    },
    "post_tool_write": {
        "mode": OBSERVER,
        "desc": "el motor ejecutó un tool de escritura (Write/Edit/Notebook); "
                "guidance no-bloqueante al tool-result — N15 cuelga aquí",
    },
    "pre_prompt": {
        "mode": MIDDLEWARE,
        "desc": "el prompt ensamblado está por mandarse al modelo; único "
                "evento que puede MUTAR el payload (modo middleware de Hermes)",
    },
    "user_prompt": {
        "mode": OBSERVER,
        "desc": "el socio mandó un prompt en una sesión interactiva; observer "
                "puro (payload trae el texto; los listeners miran, no mutan) — "
                "la degradación honesta de pre_prompt que EVENTS.md anticipó",
    },
    "headless_ingest": {
        "mode": OBSERVER,
        "desc": "el harness entrega un transcript a un proceso headless. "
                "Desde 2026-10-16 NINGÚN flujo del cliente lo emite (la revisión "
                "de skills y la memoria corren en la sesión visible); queda para "
                "herramientas de desarrollo (skill_audit)",
    },
    "model_fallback": {
        "mode": OBSERVER,
        "desc": "el failover (E-3) cambió de modelo, se recuperó tras un "
                "fallo, o agotó la cadena; payload con campos PLANOS para "
                "diagnóstico (from_model/to_model/reason/strategy y "
                "fallbackStep* al agotarse)",
    },
    "pre_tool": {
        "mode": OBSERVER,
        "desc": "el motor está a punto de ejecutar cualquier herramienta; "
                "emite solo metadata (tool_name, session_id, ts) — "
                "NUNCA tool_input. Base de la telemetría en vivo (N-telem).",
    },
    "post_tool": {
        "mode": OBSERVER,
        "desc": "el motor terminó de ejecutar una herramienta (éxito); "
                "emite solo metadata (tool_name, session_id, ts, ok=True) — "
                "NUNCA tool_response. Complemento de pre_tool para duración.",
    },
    "wf_step": {
        "mode": OBSERVER,
        "desc": "el runner de workflows terminó una tentativa de un paso "
                "(run/paso/kind/status/attempt/ms); lo emite el propio "
                "harness (workflows/) — la traza que steps/evidence.py "
                "verifica",
    },
    "wf_run": {
        "mode": OBSERVER,
        "desc": "transición de una PASADA del runner de workflows (v1.5, "
                "observabilidad P1-D): phase start/resume/end — el end trae "
                "estado final (done/failed/rejected/paused_human), duración "
                "total (ms) y resumen de conteos; lo emite el harness",
    },
    "turn_end": {
        "mode": OBSERVER,
        "desc": "el agente terminó UNA respuesta (no corre si el socio la "
                "interrumpe); observer puro, la salida se ignora — la maleta "
                "de la pestaña se refresca aquí para que un cierre a la mala "
                "(kill -9, se fue la luz) no la pierda",
    },
}

# ── mapping evento WORKSPACE → mecanismo nativo, POR MOTOR ──────────────────
# valor = nombre del hook nativo que lo dispara
# None  = el motor NO lo expone (pendiente motor #2 — honestidad, no simular)
# INTERNAL = lo emite el propio harness, no el motor (no se cablea a settings)
INTERNAL = "@internal"

ENGINE_MAP = {
    "claude-code": {
        "session_start": "SessionStart",
        "session_end": "SessionEnd",
        "pre_compact": "PreCompact",
        "post_tool_write": "PostToolUse",   # matcher Write|Edit|NotebookEdit al integrar N15
        # UserPromptSubmit de Claude Code es inyección aditiva + veto, NO
        # mutación del prompt → no alcanza para middleware. Ver EVENTS.md.
        "pre_prompt": None,
        # …pero SÍ alcanza para observer: user_prompt es esa degradación
        # honesta (otro evento, no pre_prompt) — base del status en vivo.
        "user_prompt": "UserPromptSubmit",
        "headless_ingest": INTERNAL,
        # el failover del motor #1 lo hace el VENDOR por dentro — opaco
        "model_fallback": None,
        # telemetría en vivo (N-telem): PreToolUse/PostToolUse con matcher "*"
        # (todos los tools — la granularidad fina que distingue de post_tool_write)
        "pre_tool": "PreToolUse",
        "post_tool": "PostToolUse",
        # el runner de workflows (F1) lo emite él mismo por paso — no se
        # cablea a ningún hook del motor. wf_run ídem, por pasada (v1.5).
        "wf_step": INTERNAL,
        "wf_run": INTERNAL,
        # hook oficial Stop (corre al terminar cada respuesta; doc:
        # https://code.claude.com/docs/en/hooks#stop). Va POR ARRANQUE, en el
        # --settings de la pestaña (ver POR_ARRANQUE), no en settings.local.json.
        "turn_end": "Stop",
    },
    # ollama (motor #2, corrida E-2): WORKSPACE posee el loop — el motor emite
    # los eventos él mismo (events.emit) en vez de cablearse a hooks nativos
    # de un vendor. INTERNAL = no se siembra nada en settings; None = aún no
    # existe en este motor (honestidad: sin tools de escritura ni compactador
    # propio en E-2). NOTA: el provider del motor vive en la rama
    # `feat/multi-engine` (engines/ollama.py se extrajo de main); este bloque
    # se queda como contrato de referencia del modelo de eventos engine-agnóstico.
    "ollama": {
        "session_start": INTERNAL,
        "session_end": INTERNAL,
        "pre_compact": None,         # trim por request (C14) ≠ compactar sesión
        "post_tool_write": None,     # sin tools de escritura en E-2
        "pre_prompt": INTERNAL,      # middleware REAL: el motor arma el request
        "user_prompt": None,         # el loop aún no lo emite (pre_prompt
                                     # INTERNAL ya cubre el momento del request;
                                     # se emite cuando un consumidor lo pida)
        "headless_ingest": INTERNAL,
        "model_fallback": INTERNAL,  # E-3: lo emitía failover.py por transición
                                     # (fuera de main desde la 0.5; el motor ya
                                     # había salido antes)
        "pre_tool": None,            # sin tools en E-2 (ver post_tool_write)
        "post_tool": None,
        "wf_step": INTERNAL,         # lo emite el harness, no el motor
        "wf_run": INTERNAL,          # ídem — pasada del runner (v1.5)
        "turn_end": None,            # el loop no lo emite
    },
    # codex y antigravity (wrapper, 2026-10-13): WORKSPACE envuelve el TUI
    # oficial y emite ÉL MISMO inicio/cierre (interactive.run_official_cli_
    # interactive → neutral_hooks) → INTERNAL. Ambos CLIs traen hooks nativos
    # (codex 0.162: SessionStart/UserPromptSubmit/Stop/SessionEnd con
    # confianza por hash; agy 1.3: SessionStart/PreToolUse/PostToolUse/
    # Pre-PostInvocation/Stop, sin SessionEnd) pero NO se cablean todavía:
    # session_end dispararía doble con el del wrapper. Lo demás = None
    # (honestidad: hoy no se observa desde dentro). wired_events → [].
    "codex": {
        "session_start": INTERNAL, "session_end": INTERNAL,
        "pre_compact": None, "post_tool_write": None, "pre_prompt": None,
        "user_prompt": None, "headless_ingest": INTERNAL,
        "model_fallback": None, "pre_tool": None, "post_tool": None,
        "wf_step": INTERNAL, "wf_run": INTERNAL, "turn_end": None,
    },
    "antigravity": {
        "session_start": INTERNAL, "session_end": INTERNAL,
        "pre_compact": None, "post_tool_write": None, "pre_prompt": None,
        "user_prompt": None, "headless_ingest": None,
        "model_fallback": None, "pre_tool": None, "post_tool": None,
        "wf_step": INTERNAL, "wf_run": INTERNAL, "turn_end": None,
    },
    # opencode y openclaw (wrapper, 2026-10-15): mismo ciclo neutral que
    # codex/antigravity. headless_ingest None igual que agy: su transcript SÍ es
    # legible (export de opencode / JSONL de OpenClaw) y la revisión de skills
    # corre desde session_end; este mapa no cablea un emisor propio.
    "opencode": {
        "session_start": INTERNAL, "session_end": INTERNAL,
        "pre_compact": None, "post_tool_write": None, "pre_prompt": None,
        "user_prompt": None, "headless_ingest": None,
        "model_fallback": None, "pre_tool": None, "post_tool": None,
        "wf_step": INTERNAL, "wf_run": INTERNAL, "turn_end": None,
    },
    "openclaw": {
        "session_start": INTERNAL, "session_end": INTERNAL,
        "pre_compact": None, "post_tool_write": None, "pre_prompt": None,
        "user_prompt": None, "headless_ingest": None,
        "model_fallback": None, "pre_tool": None, "post_tool": None,
        "wf_step": INTERNAL, "wf_run": INTERNAL, "turn_end": None,
    },
    # hermes (wrapper, 2026-10-15): mismo ciclo neutral; transcript legible por
    # el export oficial de la sesión. Sus hooks nativos no se cablean.
    "hermes": {
        "session_start": INTERNAL, "session_end": INTERNAL,
        "pre_compact": None, "post_tool_write": None, "pre_prompt": None,
        "user_prompt": None, "headless_ingest": None,
        "model_fallback": None, "pre_tool": None, "post_tool": None,
        "wf_step": INTERNAL, "wf_run": INTERNAL, "turn_end": None,
    },
    # kiro (wrapper, 2026-10-28): mismo ciclo neutral; transcript legible por
    # la copia de messages.jsonl de su sesión. Sus hooks nativos (agentSpawn,
    # userPromptSubmit, preToolUse…) no se cablean (doble disparo).
    "kiro": {
        "session_start": INTERNAL, "session_end": INTERNAL,
        "pre_compact": None, "post_tool_write": None, "pre_prompt": None,
        "user_prompt": None, "headless_ingest": None,
        "model_fallback": None, "pre_tool": None, "post_tool": None,
        "wf_step": INTERNAL, "wf_run": INTERNAL, "turn_end": None,
    },
    # copilot (wrapper, 2026-10-28): mismo ciclo neutral; transcript legible
    # por su registro de eventos (session-state/<id>/events.jsonl). Copilot
    # trae hooks propios (doc oficial) que no se cablean (doble disparo).
    "copilot": {
        "session_start": INTERNAL, "session_end": INTERNAL,
        "pre_compact": None, "post_tool_write": None, "pre_prompt": None,
        "user_prompt": None, "headless_ingest": None,
        "model_fallback": None, "pre_tool": None, "post_tool": None,
        "wf_step": INTERNAL, "wf_run": INTERNAL, "turn_end": None,
    },
    # cursor (wrapper, 2026-10-28): mismo ciclo neutral; transcript legible por
    # el agent-transcripts que escribe el CLI. Sus hooks (y los de Claude Code
    # que Cursor importa) no se cablean: el de Workspace se apaga en Cursor.
    "cursor": {
        "session_start": INTERNAL, "session_end": INTERNAL,
        "pre_compact": None, "post_tool_write": None, "pre_prompt": None,
        "user_prompt": None, "headless_ingest": None,
        "model_fallback": None, "pre_tool": None, "post_tool": None,
        "wf_step": INTERNAL, "wf_run": INTERNAL, "turn_end": None,
    },
}

# ── listeners: qué scripts de hooks/ escuchan qué evento ──────────────────
# script   — relativo a hooks/ (los listeners viven SIEMPRE ahí)
# severity — CRITICAL: el doctor marca ✗ si falta · MINOR: ⚠ (regla: checks
#            nuevos no convierten una instalación sana en fallo)
# requires — clave del bloque `setup` del agent.json que condiciona el
#            listener (p. ej. session_journal=false → ni se cablea ni se
#            exige; setup ligero) · None = universal (todo agente)
# El ORDEN importa: es el orden de cableado/ejecución dentro de cada evento.
CRITICAL, MINOR = "critical", "minor"

LISTENERS = (
    {"script": "session_start.py", "event": "session_start", "timeout": 10,
     "severity": MINOR, "requires": "session_journal"},
    {"script": "session_end.py", "event": "session_end", "timeout": 10,
     "severity": MINOR, "requires": "session_journal"},
    # tono (2026-09-24): inyecta al ABRIR sesión los diales de personalidad
    # que el socio movió del neutro (personalidad.py). MINOR y universal: con
    # todo en 3 el hook no escribe NADA (ni un token), y si revienta el
    # arranque sigue igual.
    {"script": "personalidad.py", "event": "session_start", "timeout": 5,
     "severity": MINOR, "requires": None},
    # …y en CADA mensaje (user_prompt): el recordatorio compacto. Es lo que
    # hace que mover un dial se sienta al SIGUIENTE mensaje sin reabrir la
    # sesión (pedido del socio 2026-09-24). Con todo en neutro no escribe nada,
    # así que el coste real es el arranque de un Python por mensaje — el
    # mismo orden que la telemetría, que ya corre en cada tool.
    {"script": "personalidad.py", "event": "user_prompt", "timeout": 5,
     "severity": MINOR, "requires": None},
    # revisión de skills (opcional): al CERRAR solo deja la tarea pendiente
    # (vista neutral, sin lanzar procesos); al ABRIR se la entrega al agente,
    # que la hace en su sesión, a la vista (2026-10-16: nada sin ventana).
    {"script": "skill_review.py", "event": "session_end", "timeout": 15,
     "severity": CRITICAL, "requires": None},
    {"script": "skill_review_start.py", "event": "session_start", "timeout": 5,
     "severity": MINOR, "requires": None},
    # transcript_backup (Y2b): universal pero MENOR (⚠, jamás ✗)
    {"script": "transcript_backup.py", "event": "session_end", "timeout": 15,
     "severity": MINOR, "requires": None},
    # memoria v1 (2026-10-17): al cerrar, sin IA — maleta de la pestaña,
    # datos/preferencias a MEMORY.md, compactar el diario. Universal y MENOR.
    {"script": "memoria_cierre.py", "event": "session_end", "timeout": 20,
     "severity": MINOR, "requires": None},
    # …y al terminar CADA respuesta (turn_end = Stop de Claude Code): SOLO la
    # maleta (el paso 1 de memoria.al_cerrar), en milisegundos. Si Claude Code
    # muere sin SessionEnd (kill -9), la maleta trae hasta la última respuesta.
    # Va por arranque (POR_ARRANQUE). MENOR y universal.
    {"script": "memoria_turno.py", "event": "turn_end", "timeout": 5,
     "severity": MINOR, "requires": None},
    # métricas F1 (2026-10-26): al cerrar, sin IA ni red — números y nombres de
    # la sesión a <estado>/metricas/ (metricas.py). Universal y MENOR; va
    # ÚLTIMO para no demorar la memoria, y se acota solo (PRESUPUESTO_VIVO):
    # lo que no alcance se mide en el siguiente cierre de esa sesión.
    {"script": "metricas_cierre.py", "event": "session_end", "timeout": 10,
     "severity": MINOR, "requires": None},
    # memory_flush (N2): flush a disco ANTES de compactar — universal (la
    # maleta solo se rehace si hay pestaña; sin ella igual deja rastro en
    # ~/.claude/workspace/). MENOR: su falta jamás convierte un setup sano en ✗.
    {"script": "memory_flush.py", "event": "pre_compact", "timeout": 10,
     "severity": MINOR, "requires": None},
    # security_guidance (N15): aviso no-bloqueante al tool-result cuando el
    # agente escribe código con patrones de riesgo (Write/Edit/NotebookEdit).
    # Observer puro — jamás bloquea ni revierte. MENOR: su falta nunca ✗.
    # matcher: PostToolUse de claude-code filtra por nombre de tool (Write|Edit|…).
    {"script": "security_guidance.py", "event": "post_tool_write", "timeout": 10,
     "severity": MINOR, "requires": None, "matcher": "Write|Edit|NotebookEdit"},
    # telemetría en vivo (N-telem): pre_tool + post_tool → hooks/telemetry.py
    # matcher "*" (todos los tools — la cobertura total es el punto).
    # MINOR (⚠ no ✗ si falta): la telemetría mejora el dashboard pero jamás ✗.
    # requires=None: universal (zenith, atlas y cualquier agente futuro).
    {"script": "telemetry.py", "event": "pre_tool", "timeout": 3,
     "severity": MINOR, "requires": None, "matcher": "*"},
    {"script": "telemetry.py", "event": "post_tool", "timeout": 3,
     "severity": MINOR, "requires": None, "matcher": "*"},
)
# hooks/untrusted.py (guard N6) NO va en LISTENERS: es una librería que usan
# los emisores de headless_ingest, no un script cableado a eventos del motor.


# ── wiring POR ARRANQUE ───────────────────────────────────────────────────
# Estos eventos NO se siembran en el settings.local.json del cerebro: los cablea
# cada arranque en el `--settings` de la pestaña (memoria.claude_settings_args →
# install.build_hooks(launch=True)). Así llegan sin `workspace doctor`/repair
# (el archivo se rehace al abrir), solo los ve Claude Code (Cursor también corre
# los hooks de `.claude/settings*.json`) y doctor no los exige en el cerebro.
POR_ARRANQUE = {"claude-code": ("turn_end",)}


# ── eco de otro motor ─────────────────────────────────────────────────────
# Copilot y Cursor corren TAMBIÉN los hooks de Claude Code que Workspace cablea
# en `<cerebro>/.claude/settings.local.json`, con su propio payload. El inicio y
# el cierre de verdad ya los emite su wrapper (payload con `engine`): sin este
# filtro cada listener de session_start/session_end (marcador, tono, revisión
# de skills, memoria, respaldo, métricas) corría dos veces por sesión, y el de
# user_prompt (el tono) en cada mensaje para nada. Lo aplica el runner
# (workspace_hook.py) antes de despachar a NINGÚN listener de ECO_DESCARTADO;
# métricas lo reusa como defensa propia.
#
# VERIFICADO 2026-11-06 con los binarios (caja negra, HOME desechable):
#   · Copilot 1.0.105 (proveedor falso; `-p` y en un pty con `-i`, como lo abre
#     Workspace): SessionStart {session_id, timestamp, cwd, source,
#     initial_prompt}, UserPromptSubmit {session_id, timestamp, cwd, prompt} y
#     SessionEnd {session_id, timestamp, cwd, reason}; NINGUNO trae
#     transcript_path, y el additionalContext que devuelven esos hooks NO llega
#     al modelo (descartarlos no le quita nada a Copilot).
#   · Claude Code 2.1.319 (llave falsa, sin llamar al modelo): SessionStart,
#     UserPromptSubmit y SessionEnd traen SIEMPRE transcript_path y nunca
#     timestamp, también con WORKSPACE_SESSION_ENGINE=copilot heredado.
# Fuera de estos tres no se descarta: pre_tool/post_tool de Copilot solo llegan
# por aquí (su wrapper no los emite) y su Stop sí trae transcript_path.
ECO_DESCARTADO = ("session_start", "user_prompt", "session_end")


def eco_de_otro_motor(data, env=None):
    """¿Este hook lo disparó OTRO motor con los ganchos de Claude Code del
    cerebro? GitHub Copilot (1.0.105) lee `<cerebro>/.claude/settings*.json`
    («repo settings») y dispara su SessionStart, UserPromptSubmit y SessionEnd
    con su propio payload (`session_id` de Copilot, `timestamp` ISO, `cwd`;
    doc oficial de hooks de Copilot, y VERIFICADO arriba), SIN
    `transcript_path`, que Claude Code manda siempre. Cursor manda
    `cursor_version`. El inicio y el cierre de verdad de esos motores los emite
    su wrapper, con `engine`. Un Claude Code abierto desde la terminal de otro
    motor hereda la marca del entorno (WORKSPACE_SESSION_ENGINE), pero trae
    `transcript_path`: ese es suyo y corre."""
    if not isinstance(data, dict) or data.get("engine"):
        return False
    if data.get("cursor_version"):
        return True
    if data.get("transcript_path"):
        return False
    env = _os.environ if env is None else env
    marca = str(env.get("WORKSPACE_SESSION_ENGINE") or "")
    return (bool(marca) and marca != "claude-code") or bool(data.get("timestamp"))


def native_event(event, engine="claude-code"):
    """Mecanismo nativo que dispara `event` en `engine`.
    None = no disponible en ese motor · INTERNAL = lo emite el harness."""
    return ENGINE_MAP.get(engine, {}).get(event)


def listeners_for(event):
    """Listeners declarados para un evento WORKSPACE, en orden de cableado."""
    return [l for l in LISTENERS if l["event"] == event]


# ── gate `requires` · fuente ÚNICA para install Y doctor (Tema D) ───────────
# Default conservador: un agente sin bloque `setup` se trata como setup COMPLETO
# (no perder cobertura en agentes viejos). Quien quiera setup ligero lo declara.
SETUP_DEFAULTS = {"session_journal": True, "autonomous": True}


def setup_of(cfg):
    """Bloque `setup` del agent.json mergeado sobre SETUP_DEFAULTS."""
    s = dict(SETUP_DEFAULTS)
    declared = (cfg or {}).get("setup")
    if isinstance(declared, dict):
        s.update({k: v for k, v in declared.items() if not k.startswith("_")})
    return s


def gated(listener, setup):
    """True si el listener está APAGADO por el gate `requires` (su clave de
    `setup` es false). D: install y doctor lo comparten para no divergir — antes
    build_hooks cableaba TODOS los listeners ignorando el gate que doctor SÍ
    aplica (para un agente `session_journal=false`, install horneaba hooks que
    doctor luego quitaba → oscilación + reporte engañoso)."""
    req = listener.get("requires")
    return bool(req) and not setup.get(req)


def _events_dir():
    return _os.path.join(_paths.state_dir(),
                         "events")


# ── rastro unificado N10 (schema arriba en el docstring) ──────────────────
# kinds = taxonomía SSE de Odysseus (agent_loop.py: delta/tool_start/
# tool_output/agent_step/metrics/[DONE] — "done" sin corchetes en disco).
KINDS = ("delta", "tool_start", "tool_output", "agent_step", "metrics",
         "done")

# evento N9 → kind SSE. Pasos de ciclo de vida = agent_step; post_tool_write
# observa el resultado de un tool = tool_output. delta/metrics/done quedan
# para el tee de stream-json (futuro F2 del dashboard).
EVENT_KIND = {
    "session_start": "agent_step",
    "session_end": "agent_step",
    "pre_compact": "agent_step",
    "post_tool_write": "tool_output",
    "pre_prompt": "agent_step",
    "user_prompt": "agent_step",
    "headless_ingest": "agent_step",
    "model_fallback": "agent_step",
    # telemetría en vivo: tool_start / tool_output son los kinds SSE más precisos
    "pre_tool": "tool_start",
    "post_tool": "tool_output",
    # pasos de pipeline del runner de workflows = agent_step (mismo criterio
    # que los pasos de audits). wf_run (pasada) ídem.
    "wf_step": "agent_step",
    "wf_run": "agent_step",
    "turn_end": "agent_step",
}

_CLIP = 300          # tope por string del payload: actividad, no contenido
_PAGE_MAX = 500      # cota dura del lector (el dashboard no vuelca megabytes)


def _clip(v):
    if isinstance(v, str) and len(v) > _CLIP:
        return v[:_CLIP] + "…"
    return v


def record(kind, payload=None, source="", agent="", brain=""):
    """Anexa UN record al rastro unificado (`~/.claude/workspace/events/`).

    Solo kinds del vocabulario SSE (KINDS) — el rastro habla un idioma
    probado, no inventa. `brain`/`agent` se extraen del payload si el emisor
    los traía ahí (compat con los payloads de N3/N4). Strings del payload
    recortados a _CLIP. Best-effort: devuelve la ruta del log o None; JAMÁS
    levanta (los emisores son hooks de cierre y pipelines nocturnos — un
    rastro caído no puede tumbar al caller)."""
    try:
        if kind not in KINDS:
            return None
        p = dict(payload or {})
        brain = str(brain or p.pop("brain", "") or "")
        agent = str(agent or p.pop("agent", "") or "")
        rec = {
            "ts": _dt.datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "source": str(source or ""),
            "agent": agent,
            "brain": brain,
            "payload": {str(k): _clip(v) for k, v in p.items()},
        }
        d = _events_dir()
        _os.makedirs(d, exist_ok=True)
        path = _os.path.join(d, _dt.date.today().isoformat() + ".jsonl")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(_json.dumps(rec, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return None


def emit(event, payload=None, emitter=""):
    """Fachada N9 sobre `record()` — firma estable (skill_audit, nightly,
    hooks). Solo acepta eventos del vocabulario v1 (EVENTS); el evento viaja
    como payload["event"] y el kind sale de EVENT_KIND. Best-effort: ruta
    del log o None, jamás levanta."""
    try:
        if event not in EVENTS:
            return None
        p = dict(payload or {})
        p["event"] = event
        return record(EVENT_KIND.get(event, "agent_step"), p, source=emitter)
    except Exception:
        return None


def _normalize(rec):
    """Una línea del rastro → schema unificado N10. Las líneas legacy
    (pre-N10: `{ts, event, emitter, …payload}` aplanado) se traducen."""
    if "kind" in rec and isinstance(rec.get("payload"), dict):
        return {
            "ts": str(rec.get("ts", "")),
            "kind": str(rec.get("kind", "")),
            "source": str(rec.get("source", "")),
            "agent": str(rec.get("agent", "")),
            "brain": str(rec.get("brain", "")),
            "payload": {str(k): _clip(v) for k, v in rec["payload"].items()},
        }
    ev = rec.get("event", "")
    return {
        "ts": str(rec.get("ts", "")),
        "kind": EVENT_KIND.get(ev, "agent_step"),
        "source": str(rec.get("emitter", "")),
        "agent": "",
        "brain": str(rec.get("brain", "")),
        "payload": {str(k): _clip(v) for k, v in rec.items()
                    if k not in ("ts", "emitter", "brain")},
    }


def read_events(limit=100, offset=0):
    """Últimos eventos del rastro local, MÁS RECIENTE PRIMERO, normalizados
    al schema unificado. Paginado (`limit` ≤ _PAGE_MAX, `offset`) — lee solo
    los días necesarios, nunca vuelca el stream entero. Read-only y
    falla-suave: lista (posiblemente vacía), jamás levanta."""
    try:
        limit = max(0, min(int(limit), _PAGE_MAX))
        offset = max(0, int(offset))
        d = _events_dir()
        if not limit or not _os.path.isdir(d):
            return []
        out, need = [], offset + limit
        files = sorted((f for f in _os.listdir(d) if f.endswith(".jsonl")),
                       reverse=True)            # YYYY-MM-DD.jsonl → desc
        for f in files:
            day = []
            try:
                with open(_os.path.join(d, f), encoding="utf-8") as fh:
                    for ln in fh:
                        try:
                            rec = _json.loads(ln)
                        except ValueError:
                            continue
                        if isinstance(rec, dict):
                            day.append(_normalize(rec))
            except OSError:
                continue
            out.extend(reversed(day))           # dentro del día: desc
            if len(out) >= need:
                break
        return out[offset:offset + limit]
    except Exception:
        return []


def _con_nativo(engine):
    out = []
    for l in LISTENERS:
        ev = l["event"]
        if ev not in out and native_event(ev, engine) not in (None, INTERNAL):
            out.append(ev)
    return out


def wired_events(engine="claude-code"):
    """Eventos CON listeners que `engine` cablea a un hook nativo EN EL
    CEREBRO (settings.local.json), en orden estable de declaración
    (build_hooks y doctor iteran esto). Los de POR_ARRANQUE van aparte."""
    arranque = POR_ARRANQUE.get(engine, ())
    return [ev for ev in _con_nativo(engine) if ev not in arranque]


def launch_events(engine="claude-code"):
    """Eventos CON listeners que `engine` cablea en cada ARRANQUE (el
    `--settings` de la pestaña), no en el cerebro. Ver POR_ARRANQUE."""
    arranque = POR_ARRANQUE.get(engine, ())
    return [ev for ev in _con_nativo(engine) if ev in arranque]
