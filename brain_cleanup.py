#!/usr/bin/env python3
"""WORKSPACE · brain_cleanup — cuarentena de REGENERABLES en cerebros (opt-in).

POR QUÉ: un cerebro puede acumular artefactos de build (node_modules de un
demo, dist/, caches) que NO gastan tokens pero inflan disco/backup/Obsidian
Sync. Este módulo los mueve a cuarentena reversible — y NADA más.

QUÉ TOCA (allowlist EXACTA, denylist-by-default):
  · dirs por nombre exacto:  node_modules · .next · dist · build · .turbo · .cache
  · archivos por sufijo:     *.tsbuildinfo
  TODO lo demás (src, *.jpeg, *.xlsx, entregables, STATE/tmp/ y su contenido)
  queda FUERA: solo se reporta vía brain_vitals, JAMÁS se toca. Cero
  heurística "parece junk" — si no está en la allowlist, no existe para
  este módulo.

SEGURIDAD (N3 — toca el cerebro, por eso TODO es opt-in):
  · OFF por default: job `brain-cleanup` en settings (default False). El
    nightly lo respeta; habilitarlo es decisión del socio DUEÑO del cerebro
    (el demo de un cliente no se toca sin su dueño).
  · DRY-RUN por default: `--apply` es una decisión explícita.
  · CUARENTENA, NUNCA rm: mover a ~/.claude/workspace/trash/<cerebro>/<ts>/
    conservando la ruta relativa + MANIFEST.json (origen→destino). Restaurar:
    `--restore <dir>`. La purga de la cuarentena (>N días) es el ÚNICO borrado
    real y solo dentro de trash/.
  · GUARDAS de árbol vivo: NO se mueve un árbol con archivos modificados
    <48h ni con archivos abiertos por un proceso (lsof, donde exista) —
    salvo `--force`.
  · LOCK compartido con el nightly (olock N8 sobre el state del nightly —
    el mismo mecanismo/timeout de rotate_log_recent): una limpieza y una
    pasada nocturna no se pisan. Lock ocupado → skip falla-suave.
  · ANTI-TRAVERSAL: candidato con realpath fuera del cerebro (o symlink) se
    salta. JAMÁS toca BOOT/, STATE/MEMORY.md, .obsidian/, .git/ ni config
    de Sync (ni entra a esos subárboles).
  · Atómico y falla-suave: move por os.rename con fallback shutil.move;
    un candidato podrido se reporta y se sigue.

USO:
    python3 brain_cleanup.py --brain "/ruta/al/CEREBRO"            # dry-run
    python3 brain_cleanup.py --brain "/ruta/al/CEREBRO" --apply
    python3 brain_cleanup.py --restore "~/.claude/workspace/trash/X/<ts>"
    python3 brain_cleanup.py --purge-trash                          # >N días

Cero dependencias (stdlib, 3.9+). Mac y Windows (lsof ausente → esa guarda
se salta con nota; el resto aplica igual).
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── allowlist EXACTA (única fuente compartida con brain_vitals) ───────────
ALLOWLIST_DIRS = ("node_modules", ".next", "dist", "build", ".turbo", ".cache")
ALLOWLIST_FILE_SUFFIXES = (".tsbuildinfo",)
# Subárboles PROHIBIDOS: ni se escanean ni se tocan, sin excepción.
FORBIDDEN_DIRS = ("BOOT", ".obsidian", ".git")
FORBIDDEN_FILES = ("MEMORY.md",)          # (no matchea la allowlist, pero explícito)

RECENT_HOURS = 48                          # guarda de árbol vivo (mtime)
DEFAULT_TRASH_DAYS = 30                    # retención de la cuarentena
LSOF_TIMEOUT = 15                          # s — la guarda jamás cuelga la pasada

JOB_ID = "brain-cleanup"


def _home():
    return os.path.expanduser("~")


def trash_base():
    return os.path.join(_home(), ".claude", "workspace", "trash")


# ── settings/lock (mismos patrones falla-suave del nightly) ───────────────
def job_enabled():
    """Flag del job en settings. Falla-suave → False (esto toca el cerebro:
    ante la duda, APAGADO — al revés que los jobs de solo-lectura)."""
    try:
        import settings as _settings
        return bool(_settings.is_job_enabled(JOB_ID))
    except Exception:
        return False


def _trash_days():
    try:
        import settings as _settings
        v = _settings.get("otros.trash_retention_days", DEFAULT_TRASH_DAYS)
        if isinstance(v, int) and not isinstance(v, bool) and v > 0:
            return v
    except Exception:
        pass
    return DEFAULT_TRASH_DAYS


def _nightly_lock():
    """(file_lock, LockTimeout, lock_path, timeout) — el MISMO lock N8 que
    serializa el estado del nightly (rotate_log_recent y _mark_done usan el
    mismo mecanismo). Falla-suave: sin olock/nightly → (None, None, "", 0)."""
    try:
        from olock import file_lock, LockTimeout
        import nightly as _nightly
        import dream as _dream
        lock_path = _nightly._state_path()
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        return (file_lock, LockTimeout, lock_path, _dream._lock_timeout())
    except Exception:
        return (None, None, "", 0)


# ══════════════════════════════════════════════════════════════════════════
#  Candidatos (allowlist estricta + anti-traversal)
# ══════════════════════════════════════════════════════════════════════════
def _under(real_root, path):
    try:
        rp = os.path.realpath(path)
        return rp == real_root or rp.startswith(real_root + os.sep)
    except OSError:
        return False


def find_candidates(brain):
    """[{rel, path, kind, bytes}] SOLO de la allowlist, fuera de los
    subárboles prohibidos, sin symlinks, realpath bajo el cerebro."""
    import brain_vitals
    brain = os.path.abspath(os.path.expanduser(brain))
    real_brain = os.path.realpath(brain)
    out = []
    try:
        for dirpath, dirs, files in os.walk(brain, followlinks=False):
            rel_dir = os.path.relpath(dirpath, brain)
            if rel_dir == ".":
                rel_dir = ""
            pruned = []
            for d in list(dirs):
                full = os.path.join(dirpath, d)
                if d in FORBIDDEN_DIRS:
                    pruned.append(d)
                elif d in ALLOWLIST_DIRS:
                    pruned.append(d)      # no descender: se mueve completo
                    if os.path.islink(full) or not _under(real_brain, full):
                        continue          # symlink/fuera del cerebro → jamás
                    out.append({"rel": os.path.join(rel_dir, d).replace(os.sep, "/"),
                                "path": full, "kind": "dir",
                                "bytes": brain_vitals._du(full)})
            for d in pruned:
                dirs.remove(d)
            for name in files:
                if not name.endswith(ALLOWLIST_FILE_SUFFIXES) \
                        or name in FORBIDDEN_FILES:
                    continue
                full = os.path.join(dirpath, name)
                if os.path.islink(full) or not _under(real_brain, full):
                    continue
                try:
                    size = os.lstat(full).st_size
                except OSError:
                    continue
                out.append({"rel": os.path.join(rel_dir, name).replace(os.sep, "/"),
                            "path": full, "kind": "file", "bytes": size})
    except Exception:
        pass
    return out


# ── guardas de árbol vivo ─────────────────────────────────────────────────
def tree_recent(path, hours=RECENT_HOURS, now=None):
    """True si el árbol tiene ALGÚN mtime más nuevo que `hours` (trabajo
    fresco — no se toca). Falla-suave: error de lectura → True (conservador)."""
    cutoff = (time.time() if now is None else float(now)) - hours * 3600
    try:
        if os.path.isfile(path):
            return os.lstat(path).st_mtime > cutoff
        if os.lstat(path).st_mtime > cutoff:
            return True
        for dirpath, _dirs, files in os.walk(path, followlinks=False):
            for name in files:
                try:
                    if os.lstat(os.path.join(dirpath, name)).st_mtime > cutoff:
                        return True
                except OSError:
                    continue
        return False
    except Exception:
        return True


def tree_open(path):
    """(abierto, chequeado): ¿algún proceso tiene archivos abiertos bajo
    `path`? Vía lsof (mac/linux). Sin lsof (Windows) o error → (False, False):
    la guarda no aplica pero se DICE que no se pudo chequear."""
    if os.name == "nt" or not shutil.which("lsof"):
        return (False, False)
    try:
        r = subprocess.run(["lsof", "+D", path], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=LSOF_TIMEOUT)
        # lsof: rc 0 = encontró archivos abiertos; rc 1 = ninguno (o warning)
        return (r.returncode == 0 and bool((r.stdout or "").strip()), True)
    except Exception:
        return (False, False)


# ══════════════════════════════════════════════════════════════════════════
#  Cuarentena (mover, jamás borrar) + restauración + purga
# ══════════════════════════════════════════════════════════════════════════
def _write_json_atomic(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _quarantine_dir(brain):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(trash_base(), os.path.basename(brain), ts)


def run_cleanup(brain, apply=False, force=False, out=print, now=None):
    """Pasada de limpieza sobre UN cerebro. DRY-RUN salvo apply=True.

    El plan (candidatos + guardas, que puede ser lento: du/lsof) corre SIN
    lock; solo la sección de MOVES toma el lock N8 compartido con el nightly
    (crítica corta — un rename por item). Lock ocupado → skip falla-suave.

    Devuelve {"moved": [..], "skipped": [..], "bytes": n, "trash": dir|None}.
    Falla-suave SIEMPRE: nada aquí lanza al caller (nightly)."""
    import brain_vitals
    brain = os.path.abspath(os.path.expanduser(brain))
    empty = {"moved": [], "skipped": [], "bytes": 0, "trash": None}
    if not os.path.isdir(os.path.join(brain, "STATE")):
        out("CLEANUP: ERROR — %s no parece un cerebro (sin STATE/) — skip"
            % brain)
        return empty

    cands = find_candidates(brain)
    tag = "" if apply else " [DRY-RUN]"
    if not cands:
        out("CLEANUP: %s — sin regenerables de la allowlist (nada que hacer)"
            % os.path.basename(brain))
        return empty

    # ── plan: guardas por candidato (fuera del lock — lento no bloquea) ──
    plan, skipped = [], []
    for c in cands:
        why = None
        if tree_recent(c["path"], now=now):
            why = "modificado <%dh (árbol vivo)" % RECENT_HOURS
        else:
            is_open, checked = tree_open(c["path"])
            if is_open:
                why = "archivos abiertos por un proceso (lsof)"
            elif not checked and os.name != "nt":
                out("CLEANUP: nota — no se pudo chequear lsof en %s "
                    "(guarda mtime sí aplicó)" % c["rel"])
        if why and not force:
            out("CLEANUP: SKIP %s — %s (usa --force para puentear)%s"
                % (c["rel"], why, tag))
            skipped.append(dict(c, reason=why))
        else:
            plan.append(c)

    qdir = _quarantine_dir(brain)
    for c in plan:
        out("CLEANUP: %s %s (%s) → %s%s"
            % ("MOVER" if apply else "movería", c["rel"],
               brain_vitals.human(c["bytes"]),
               os.path.relpath(os.path.join(qdir, *c["rel"].split("/")),
                               trash_base()), tag))
    if not apply:
        return {"moved": plan, "skipped": skipped,
                "bytes": sum(c["bytes"] for c in plan), "trash": None}

    # ── moves: bajo el lock N8 compartido con el nightly ─────────────────
    file_lock, LockTimeout, lock_path, lock_timeout = _nightly_lock()
    if file_lock:
        try:
            with file_lock(lock_path, timeout=lock_timeout):
                return _apply_moves(brain, plan, skipped, qdir, out)
        except LockTimeout:
            out("CLEANUP: lock del nightly ocupado — skip (cerebro intacto)")
            return dict(empty, skipped=skipped)
        except Exception as e:
            out("CLEANUP: ERROR de lock: %s — skip (cerebro intacto)" % e)
            return dict(empty, skipped=skipped)
    return _apply_moves(brain, plan, skipped, qdir, out)


def _apply_moves(brain, plan, skipped, qdir, out):
    import brain_vitals
    moved, entries, total = [], [], 0
    for c in plan:
        dest = os.path.join(qdir, *c["rel"].split("/"))
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                os.rename(c["path"], dest)          # atómico mismo FS
            except OSError:
                shutil.move(c["path"], dest)        # cross-device
            entries.append({"src": c["path"], "dst": dest,
                            "rel": c["rel"], "bytes": c["bytes"]})
            moved.append(c)
            total += c["bytes"]
        except Exception as e:
            out("CLEANUP: ERROR moviendo %s: %s (falla-suave; se sigue)"
                % (c["rel"], e))
            skipped.append(dict(c, reason=str(e)))
    if entries:
        try:
            _write_json_atomic(os.path.join(qdir, "MANIFEST.json"), {
                "version": 1, "brain": brain,
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "retention_days": _trash_days(),
                "moves": entries,
            })
            out("CLEANUP: %d item(s), %s → cuarentena %s (reversible: "
                "brain_cleanup.py --restore \"%s\")"
                % (len(entries), brain_vitals.human(total), qdir, qdir))
        except Exception as e:
            out("CLEANUP: ERROR escribiendo MANIFEST.json: %s — los items "
                "movidos siguen en %s" % (e, qdir))
    return {"moved": moved, "skipped": skipped, "bytes": total,
            "trash": qdir if entries else None}


def restore(qdir, out=print):
    """Regresa TODO lo de una cuarentena a su origen (según MANIFEST.json).
    No pisa: si el origen ya existe, se reporta y se salta ese item."""
    qdir = os.path.abspath(os.path.expanduser(qdir))
    man_path = os.path.join(qdir, "MANIFEST.json")
    try:
        with open(man_path, encoding="utf-8") as fh:
            man = json.load(fh)
    except Exception as e:
        out("RESTORE: ERROR — sin MANIFEST.json legible en %s (%s)" % (qdir, e))
        return 1
    rc = 0
    for mv in man.get("moves", []):
        src, dst = mv.get("dst"), mv.get("src")     # invertido: volver a casa
        if not src or not dst or not os.path.exists(src):
            continue
        if os.path.exists(dst):
            out("RESTORE: SKIP %s — el origen ya existe (no piso nada)" % dst)
            rc = 1
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                os.rename(src, dst)
            except OSError:
                shutil.move(src, dst)
            out("RESTORE: %s → %s" % (mv.get("rel", src), dst))
        except Exception as e:
            out("RESTORE: ERROR con %s: %s" % (src, e))
            rc = 1
    return rc


def purge_trash(days=None, out=print, now=None):
    """Borra cuarentenas más viejas que `days` (ÚNICO borrado real del
    módulo, SOLO dentro de trash_base). Devuelve nº de dirs purgados."""
    days = days if days else _trash_days()
    base = os.path.realpath(trash_base())
    if not os.path.isdir(base):
        return 0
    cutoff = (time.time() if now is None else float(now)) - days * 86400
    purged = 0
    try:
        for brain_dir in os.listdir(base):
            bfull = os.path.join(base, brain_dir)
            if not os.path.isdir(bfull):
                continue
            for ts_dir in os.listdir(bfull):
                tfull = os.path.join(bfull, ts_dir)
                if not os.path.isdir(tfull) or not _under(base, tfull):
                    continue
                try:
                    if os.lstat(tfull).st_mtime < cutoff:
                        shutil.rmtree(tfull, ignore_errors=True)
                        purged += 1
                except OSError:
                    continue
    except Exception:
        pass
    if purged:
        out("CLEANUP: purga de cuarentena — %d lote(s) >%d día(s) borrados"
            % (purged, days))
    return purged


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="brain_cleanup.py",
        description="Cuarentena reversible de REGENERABLES (allowlist exacta) "
                    "en un cerebro. DRY-RUN por default; N3 → opt-in.")
    ap.add_argument("--brain", default=None, help="ruta del cerebro")
    ap.add_argument("--apply", action="store_true",
                    help="ejecutar de verdad (default: dry-run)")
    ap.add_argument("--force", action="store_true",
                    help="puentear guardas de árbol vivo (mtime<48h / lsof)")
    ap.add_argument("--restore", default=None, metavar="DIR",
                    help="regresar una cuarentena a su origen")
    ap.add_argument("--purge-trash", action="store_true",
                    help="borrar cuarentenas más viejas que la retención")
    ap.add_argument("--retention-days", type=int, default=None,
                    help="días de retención para --purge-trash")
    args = ap.parse_args(argv)
    if args.restore:
        return restore(args.restore)
    if args.purge_trash:
        purge_trash(days=args.retention_days)
        return 0
    if not args.brain:
        ap.error("--brain requerido (o --restore / --purge-trash)")
    run_cleanup(args.brain, apply=args.apply, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
