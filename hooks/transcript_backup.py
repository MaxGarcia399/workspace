#!/usr/bin/env python3
"""WORKSPACE hook · SessionEnd — backup crudo de transcripts (robo Y2b).

Al cerrar una sesión, copia el .jsonl crudo de Claude Code
(~/.claude/projects/<enc>/<wid>.jsonl) a un backup local FUERA del cerebro:

    ~/.claude/workspace/transcripts-backup/<enc>/<wid>.jsonl

Por qué existe: los transcripts crudos son la materia prima del backfill de
memoria v2 (N1 · Dreaming). `cleanupPeriodDays=3650` (Y2a) mitiga el borrado
por edad, pero un reinstall / limpieza de ~/.claude/projects los pierde todos.
Este hook es el respaldo activo: "no perder". La curación/destilación es N1.

Diseño:
- Idempotente: si el destino existe con el mismo tamaño y mtime que la fuente,
  no recopia (shutil.copy2 preserva mtime → la comparación es estable).
- Best-effort y silencioso: JAMÁS rompe el cierre de sesión (todo en try/except,
  exit 0 siempre). Cleanup-only: Claude Code ignora la salida de SessionEnd.
- Cross-platform: stdlib puro (shutil.copy2, os.makedirs), sin POSIX-isms.
- Amputable (C10): borrar este archivo = la feature se apaga (el doctor fase 5
  lo re-esperaría; quitarlo de install.build_hooks lo apaga de verdad).
- NO toca el cerebro: el backup vive en ~/.claude/workspace/ (per-máquina,
  fuera del vault sincronizado y fuera de cualquier git de cerebro).
- Desactivable: WORKSPACE_NO_TRANSCRIPT_BACKUP=1 (el env SIEMPRE gana) o
  `settings set hooks.transcript_backup off` (canal nuevo, settings.py).

Retención: el backup CRECE sin rotación (a propósito — Y2b es "no perder";
los .jsonl son texto, MBs por sesión). Cuando N1 (Dreaming) destile los
transcripts a journals, la curación/poda del backup será suya. Si algún día
estorba: borrar ~/.claude/workspace/transcripts-backup/ es seguro (solo se
pierde el respaldo, no los originales).

Cero dependencias (Python 3.9+). Mac y Windows.
"""
import sys, os, json, shutil

try:   # M1/B2 · Windows: UTF-8 en stdout/err — un hook capturado por Claude Code en
       # cp1252 reventaría al imprimir caracteres no-ASCII. No-op en Mac (UTF-8 default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# session_paths vive en la raíz de WORKSPACE (padre de hooks/) — única fuente de
# verdad de la codificación <enc> de Claude Code (realpath + no-alfanumérico → '-').
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import session_paths
except Exception:
    session_paths = None

BACKUP_ROOT = os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                           "transcripts-backup")


def _stdin():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _encoded_dir(transcript, brain):
    """Nombre <enc> de la carpeta de backup para este transcript.

    Fuente primaria: el propio path del transcript — si vive bajo
    ~/.claude/projects/<enc>/, ese <enc> es la verdad de Claude Code en esta
    máquina (cubre symlinks, encodings viejos, todo). Fallback: calcularlo con
    session_paths.session_dir(brain) — la misma fórmula, NO redefinida aquí.
    """
    parent = os.path.dirname(os.path.abspath(transcript))
    projects = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    try:
        if os.path.dirname(parent) == os.path.normpath(projects):
            return os.path.basename(parent)
    except Exception:
        pass
    if session_paths and brain:
        try:
            return os.path.basename(session_paths.session_dir(brain))
        except Exception:
            pass
    return os.path.basename(parent) or "unknown"


def _same_copy(src, dst):
    """True si dst ya es copia fiel de src (tamaño + mtime; copy2 preserva mtime)."""
    try:
        ss, ds = os.stat(src), os.stat(dst)
        return ss.st_size == ds.st_size and abs(ss.st_mtime - ds.st_mtime) < 2
    except Exception:
        return False


def backup_transcript(transcript, brain):
    """Respalda `transcript` (jsonl crudo) al backup local. Reutilizable: la
    usa este hook (SessionEnd) y `memory_flush.py` (N2, PreCompact) para
    refrescar el respaldo a media sesión. Idempotente, atómica (vía .part),
    falla-suave. Devuelve la ruta del backup ('' si no aplicó/falló)."""
    if not (transcript and transcript.endswith(".jsonl")
            and os.path.isfile(transcript)):
        return ""   # solo respaldamos transcripts crudos
    dst_dir = os.path.join(BACKUP_ROOT, _encoded_dir(transcript, brain))
    dst = os.path.join(dst_dir, os.path.basename(transcript))
    if _same_copy(transcript, dst):
        return dst  # idempotente: ya está respaldado y sin cambios
    tmp = dst + ".part"
    try:
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(transcript, tmp)   # vía .part: nunca dejar un backup a medias
        os.replace(tmp, dst)
        return dst
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return ""  # best-effort: jamás romper al caller


def _setting_on(key):
    """Setting bool del store unificado (settings.py, raíz de WORKSPACE).
    Falla-suave: sin settings.py / sin store / error → True (on-by-default,
    el comportamiento de siempre). El env kill-switch se chequea APARTE y
    SIEMPRE gana."""
    try:
        import settings as _settings   # la raíz ya está en sys.path (arriba)
        return _settings.enabled(key, default=True)
    except Exception:
        return True


def main():
    if os.environ.get("WORKSPACE_NO_TRANSCRIPT_BACKUP"):
        return                                   # env: el kill-switch gana
    if not _setting_on("hooks.transcript_backup"):
        return                                   # canal nuevo (settings.py)
    data = _stdin()
    brain = data.get("cwd", "") or os.getcwd()
    backup_transcript(data.get("transcript_path", ""), brain)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # falla-suave absoluta
