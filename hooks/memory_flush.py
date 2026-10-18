#!/usr/bin/env python3
"""WORKSPACE hook · PreCompact — memory flush (N2, robo OpenClaw R2).

Antes de que Claude Code COMPACTE el contexto (manual o auto), este hook
"guarda a disco lo importante" para que sobreviva a la compactación y la
pestaña retome con su maleta al día (memoria v1). Primer consumidor real del evento
`pre_compact` del contrato N9 (`events.py` / `engines/EVENTS.md`): se declara
en `events.LISTENERS` y `install.build_hooks` lo cablea solo.

Payload PreCompact de Claude Code (stdin JSON): `session_id`,
`transcript_path`, `cwd`, `trigger` ("manual"/"auto"), `custom_instructions`,
`hook_event_name`. El contrato garantiza session_id/transcript_path/trigger;
todo lo demás se trata con tolerancia (basura/vacío → exit 0).

Qué hace (3 capas, todas best-effort):
1. **Snapshot del transcript crudo** — refresca el respaldo Y2b
   (~/.claude/workspace/transcripts-backup/<enc>/) vía
   `transcript_backup.backup_transcript()`. El crudo PRE-compactación
   sobrevive aunque la sesión muera después.
2. **Maleta de la pestaña** (memoria v1) — si la sesión tiene pestaña (ws),
   rehace `STATE/sessions/<socio>/maleta/<slug>.md` con el extracto sin IA
   de la conversación ANTES de compactar (memoria.actualizar_maleta). Antes
   era una línea «contexto compactado» en el diario: ruido.
3. **Rastro JSONL** — siempre (con o sin pestaña: Atlas no tiene), un evento a
   `~/.claude/workspace/memory-flush/YYYY-MM-DD.jsonl`: qué sesiones se
   compactaron y dónde está su crudo (el campo `journal` = ruta de la maleta).

Por qué NO escribe a STATE/MEMORY.md ni a la ficha de la pestaña: este hook es
mecánico (sin LLM) y solo garantiza que nada se pierda en el momento de la
compactación. Lo que se guarda lo decide el agente con `workspace memoria
nota`; ordenar es de memoria.al_cerrar al cerrar la sesión. Jamás escribe canónicos.

Diseño: observer puro (la salida se ignora; PreCompact no puede bloquear la
compactación y este hook JAMÁS lo intenta). Falla-suave absoluta (todo en
try/except, exit 0 siempre). Cross-platform, stdlib (3.9+). Amputable (C10):
borrar este archivo + su fila en events.LISTENERS = la feature se apaga.
On-by-default; kill-switch: WORKSPACE_NO_MEMORY_FLUSH=1 (el env SIEMPRE gana)
o `settings set hooks.memory_flush off` (canal nuevo, settings.py).
"""
import sys, os, json, datetime

try:   # M1/B2 · Windows: UTF-8 en stdout/err — un hook capturado por Claude Code en
       # cp1252 reventaría al imprimir caracteres no-ASCII. No-op en Mac (UTF-8 default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# transcript_backup vive junto a este hook (hooks/ no es paquete) y la raíz
# de WORKSPACE trae session_paths — ambos al path. Import tolerante: si
# transcript_backup no está (amputado), el snapshot se salta y el resto sigue.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
try:
    import transcript_backup as _tb
except Exception:
    _tb = None

KILL_SWITCH = "WORKSPACE_NO_MEMORY_FLUSH"


def _stdin():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _flush_dir():
    return os.path.join(_paths.state_dir(), "memory-flush")


def _marker(sid):
    """Marcador de session_start.py (trae la pestaña `ws` cuando el env ya
    no está disponible). Best-effort."""
    p = os.path.join(_paths.state_dir(), "markers",
                     (sid or "unknown") + ".json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _snapshot(transcript, brain):
    """Capa 1: refrescar el respaldo Y2b del transcript crudo. '' si no aplicó."""
    if not _tb:
        return ""
    try:
        return _tb.backup_transcript(transcript, brain)
    except Exception:
        return ""


def _maleta(brain, sid, transcript=""):
    """Capa 2 (memoria v1, 2026-10-17): en vez de la línea «contexto
    compactado» en el diario (ruido), se rehace la MALETA de la pestaña con
    el extracto de la conversación ANTES de compactar; el paquete que vuelve
    a entrar tras la compactación la trae. Devuelve la ruta de la maleta o
    '' si no aplicó (sin pestaña/socio/ficha)."""
    try:
        ws = (os.environ.get("WORKSPACE_WS", "")
              or os.environ.get("ZENITH_WS", "")
              or _marker(sid).get("ws", ""))
        if not (ws and brain and transcript):
            return ""
        import memoria
        root = memoria.raiz_cerebro(brain)
        if memoria.actualizar_maleta(root, ws, "claude-code", transcript):
            return memoria.maleta_path(root, ws)
        return ""
    except Exception:
        return ""


def _log(rec):
    """Capa 3: rastro JSONL per-máquina (qué se compactó y dónde quedó)."""
    try:
        d = _flush_dir()
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, datetime.date.today().isoformat() + ".jsonl")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return path
    except Exception:
        return ""


def _setting_on(key):
    """Setting bool del store unificado (settings.py, raíz de WORKSPACE).
    Falla-suave → True (on-by-default). El env kill-switch SIEMPRE gana."""
    try:
        import settings as _settings   # la raíz ya está en sys.path (arriba)
        return _settings.enabled(key, default=True)
    except Exception:
        return True


def main():
    if os.environ.get(KILL_SWITCH):
        return                                   # env: el kill-switch gana
    if not _setting_on("hooks.memory_flush"):
        return                                   # canal nuevo (settings.py)
    data = _stdin()
    sid = data.get("session_id", "")
    transcript = data.get("transcript_path", "")
    trigger = data.get("trigger", "")
    brain = data.get("cwd", "") or os.getcwd()

    backup = _snapshot(transcript, brain)
    journal = _maleta(brain, sid, transcript)
    _log({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
          "session_id": sid, "trigger": trigger, "brain": brain,
          "transcript": transcript, "backup": backup, "journal": journal})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # falla-suave absoluta: jamás romper la compactación
