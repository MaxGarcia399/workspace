#!/usr/bin/env python3
"""WORKSPACE hook · PreCompact — memory flush (N2, robo OpenClaw R2).

Antes de que Claude Code COMPACTE el contexto (manual o auto), este hook
"guarda a disco lo importante" para que sobreviva a la compactación y
alimente memoria v2 (N1 · Dreaming). Primer consumidor real del evento
`pre_compact` del contrato N9 (`events.py` / `engines/EVENTS.md`): se declara
en `events.LISTENERS` y `install.build_hooks` lo cablea solo.

Payload PreCompact de Claude Code (stdin JSON): `session_id`,
`transcript_path`, `cwd`, `trigger` ("manual"/"auto"), `custom_instructions`,
`hook_event_name`. El contrato garantiza session_id/transcript_path/trigger;
todo lo demás se trata con tolerancia (basura/vacío → exit 0).

Qué hace (3 capas, todas best-effort):
1. **Snapshot del transcript crudo** — refresca el respaldo Y2b
   (~/.claude/workspace/transcripts-backup/<enc>/) vía
   `transcript_backup.backup_transcript()`. El crudo PRE-compactación es la
   materia prima de N1; con esto sobrevive aunque la sesión muera después.
2. **Breadcrumb al journal de sesión** — si la sesión tiene pestaña (ws) y
   socio, anexa una línea fechada a `STATE/sessions/<socio>/<slug>.md`
   (## Historial): "el contexto se compactó; el detalle previo vive en el
   crudo respaldado". Eso queda en el CEREBRO (sincronizado) y le dice al
   agente post-compactación —y al destilador N1— dónde está el detalle.
   Máx. 1 breadcrumb por sesión/día (anti-spam en compactaciones repetidas).
3. **Rastro JSONL** — siempre (con o sin journal: Atlas no tiene), un evento a
   `~/.claude/workspace/memory-flush/YYYY-MM-DD.jsonl`. Es el índice barato que
   memoria v2 puede leer para saber qué sesiones se compactaron y dónde está
   su crudo.

Por qué NO escribe a STATE/MEMORY.md ni a staging de memoria canónica: este
hook es mecánico (sin LLM) — destilar es N1/N3. N2 solo garantiza que nada
se pierda en el momento de la compactación. Jamás escribe canónicos.

Diseño: observer puro (la salida se ignora; PreCompact no puede bloquear la
compactación y este hook JAMÁS lo intenta). Falla-suave absoluta (todo en
try/except, exit 0 siempre). Cross-platform, stdlib (3.9+). Amputable (C10):
borrar este archivo + su fila en events.LISTENERS = la feature se apaga.
On-by-default; kill-switch: WORKSPACE_NO_MEMORY_FLUSH=1 (el env SIEMPRE gana)
o `settings set hooks.memory_flush off` (canal nuevo, settings.py).
"""
import sys, os, json, datetime, re, unicodedata

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
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "memory-flush")


def _marker(sid):
    """Marcador de session_start.py (trae la pestaña `ws` cuando el env ya
    no está disponible). Best-effort."""
    p = os.path.join(os.path.expanduser("~"), ".claude", "workspace", "markers",
                     (sid or "unknown") + ".json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _socio(brain):
    try:
        return open(os.path.join(brain, ".claude", "socio.local"),
                    encoding="utf-8").read().strip().lower()
    except Exception:
        return ""


def _home_rel(path):
    """Ruta legible con ~ (para breadcrumbs portables entre máquinas)."""
    home = os.path.expanduser("~")
    if path and path.startswith(home):
        return "~" + path[len(home):].replace(os.sep, "/")
    return path or ""


def _atomic_write(path, text):
    """tmp + os.replace (F1): el archivo de sesión nunca queda truncado si el
    proceso muere escribiendo. Amputable/duplicado a propósito (C10)."""
    tmp = "%s.tmp%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _append_breadcrumb(memfile, line):
    """Anexa `line` al final de ## Historial (misma convención que
    session_end.py — duplicado a propósito: cada hook es amputable, C10)."""
    with open(memfile, encoding="utf-8") as fh:
        txt = fh.read()
    lines = txt.splitlines()
    hidx = next((i for i, l in enumerate(lines)
                 if l.strip().startswith("## Historial")), None)
    if hidx is None:
        lines += ["", "## Historial", line]
    else:
        nxt = next((j for j in range(hidx + 1, len(lines))
                    if lines[j].startswith("## ")), len(lines))
        at = nxt
        while at - 1 > hidx and lines[at - 1].strip() == "":
            at -= 1
        lines.insert(at, line)
    _atomic_write(memfile, "\n".join(lines) + "\n")


def _snapshot(transcript, brain):
    """Capa 1: refrescar el respaldo Y2b del transcript crudo. '' si no aplicó."""
    if not _tb:
        return ""
    try:
        return _tb.backup_transcript(transcript, brain)
    except Exception:
        return ""


def _journal_breadcrumb(brain, sid, trigger, backup):
    """Capa 2: breadcrumb fechado al journal de la pestaña activa.
    Devuelve la ruta del journal tocado, o '' si no aplicó (sin ws/socio/
    journal — p. ej. Atlas con setup ligero: capa 3 igual deja rastro)."""
    try:
        ws = (os.environ.get("WORKSPACE_WS", "")
              or os.environ.get("ZENITH_WS", "")
              or _marker(sid).get("ws", ""))
        soc = _socio(brain)
        if not (ws and soc and brain):
            return ""
        memfile = os.path.join(brain, "STATE", "sessions", soc,
                               _slug(ws) + ".md")
        if not os.path.isfile(memfile):
            return ""   # no auto-creamos archivos estructurados curados
        today = datetime.date.today().isoformat()
        tag = f"(pre-compact · {(sid or 'sin-id')[:8]})"
        txt = open(memfile, encoding="utf-8").read()
        if today + " " + tag in txt:
            return memfile   # ya hay flush de esta sesión hoy — no spamear
        where = _home_rel(backup) if backup else \
            "~/.claude/workspace/transcripts-backup/ (al cierre de sesión)"
        line = (f"- {today} {tag} — contexto compactado"
                + (f" [{trigger}]" if trigger else "")
                + f"; el detalle previo vive en el transcript crudo: {where}."
                  " Si falta contexto fino post-compactación, está ahí.")
        _append_breadcrumb(memfile, line)
        return memfile
    except Exception:
        return ""


def _log(rec):
    """Capa 3: rastro JSONL per-máquina (índice barato para memoria v2)."""
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
    journal = _journal_breadcrumb(brain, sid, trigger, backup)
    _log({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
          "session_id": sid, "trigger": trigger, "brain": brain,
          "transcript": transcript, "backup": backup, "journal": journal})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # falla-suave absoluta: jamás romper la compactación
