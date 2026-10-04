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
              (pasos de pipelines: destilados, audits, propuestas) y
              tool_output (post_tool_write); el resto queda reservado para
              el tee de stream-json (activity-strip, dashboard F2+).
  · source  — quién escribió (script emisor: nightly.py, dream.py, …).
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
pero espeja cada evento aquí; `dream.runs.jsonl` ídem. Un evento = un
record aquí, sea directo (emit) o espejo (_audit/log_event).

Falla-suave absoluta: record/emit/read_events jamás levantan.
"""
import datetime as _dt
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
        "desc": "el harness entrega un transcript a un proceso headless para "
                "destilarlo (hoy skill_review; mañana la pasada unificada N3)",
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
        "model_fallback": INTERNAL,  # E-3: lo emite failover.py por transición
        "pre_tool": None,            # sin tools en E-2 (ver post_tool_write)
        "post_tool": None,
        "wf_step": INTERNAL,         # lo emite el harness, no el motor
        "wf_run": INTERNAL,          # ídem — pasada del runner (v1.5)
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
    {"script": "skill_review.py", "event": "session_end", "timeout": 15,
     "severity": CRITICAL, "requires": None},
    # transcript_backup (Y2b): universal pero MENOR (⚠, jamás ✗)
    {"script": "transcript_backup.py", "event": "session_end", "timeout": 15,
     "severity": MINOR, "requires": None},
    # memory_flush (N2): flush a disco ANTES de compactar — universal (el
    # journal es opcional dentro del hook; sin journal igual deja rastro en
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
    return _os.path.join(_os.path.expanduser("~"), ".claude", "workspace",
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
    # que los pasos de destilados/audits). wf_run (pasada) ídem.
    "wf_step": "agent_step",
    "wf_run": "agent_step",
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


def wired_events(engine="claude-code"):
    """Eventos CON listeners que `engine` puede cablear a un hook nativo,
    en orden estable de declaración (build_hooks itera esto)."""
    out = []
    for l in LISTENERS:
        ev = l["event"]
        if ev not in out and native_event(ev, engine) not in (None, INTERNAL):
            out.append(ev)
    return out
