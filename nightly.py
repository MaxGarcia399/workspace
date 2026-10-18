#!/usr/bin/env python3
"""WORKSPACE · nightly — mantenimiento MECÁNICO del cerebro y de la máquina (sin IA).

2026-10-16: este módulo era la «pasada nocturna unificada» (N3): un LLM SIN
VENTANA leía cada transcript respaldado y escribía journal, candidatos a
memoria (un archivo de candidatos para aprobación humana) y propuestas de skills.
El dueño retiró ese diseño: nada de agentes sin ventana en la máquina del
cliente y nada de aprobación humana en el proceso de memoria. Lo que necesite
entender texto lo hace el agente en su sesión visible; lo mecánico, código.
Lo que queda aquí es SOLO lo mecánico, sin ningún modelo:
  · retención per-máquina (purga M6 de .jsonl viejos; job `retention`, OFF);
  · rotación de STATE/log-recent.md a STATE/log-archive/ (E1);
  · refresco del índice FTS5 si está stale (memory_index);
  · cuarentena de regenerables del cerebro (brain_cleanup; job `brain-cleanup`, OFF).

DISPARO (manual hoy):
    python3 nightly.py --brain "/ruta/al/CEREBRO" [--dry-run] [--force]
    python3 nightly.py --retention          # solo la purga M6
    python3 nightly.py --brain X --rotate-logs [--dry-run]
  El job `consolidador-nocturno` (settings) lo apaga/prende; --force lo puentea.

Cero dependencias (stdlib, 3.9+). Mac y Windows. Falla-suave: cada paso es
best-effort y un fallo nunca tumba a los demás.
"""
import argparse
import datetime
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import brain_write   # lock N8 + timeout compartidos (la puerta segura del cerebro)


# ── lock compartido (brain_cleanup y la rotación toman este mismo) ────────
def _nightly_dir():
    return os.path.join(_paths.state_dir(), "nightly")


def _state_path():
    return os.path.join(_nightly_dir(), "state.json")


# ── flags de jobs (settings.py — los toggles de CRONS del config) ─────────
def _job_enabled(job_id):
    """Flag del job en el settings unificado. Falla-suave: sin settings.py /
    store roto → True (la pasada no se apaga sola por un módulo ausente)."""
    try:
        import settings as _settings
        return bool(_settings.is_job_enabled(job_id))
    except Exception:
        return True


# ── retención per-máquina (M6 — job `retention`, OFF por default) ─────────
def _retention_days():
    """Días de retención (settings otros.retention_days). Falla-suave → 90."""
    try:
        import settings as _settings
        v = _settings.get("otros.retention_days", 90)
        if isinstance(v, int) and not isinstance(v, bool) and v > 0:
            return v
    except Exception:
        pass
    return 90


def _retention_roots():
    """Carpetas per-máquina que la purga toca (SOLO estas — jamás el cerebro):
    events/ (rastro N10), telemetry/ (N-telem) y transcripts-backup/ (Y2b)."""
    base = _paths.state_dir()
    return (os.path.join(base, "events"),
            os.path.join(base, "telemetry"),
            os.path.join(base, "transcripts-backup"))


def run_retention(out=print, now=None, announce_off=True, dry_run=False):
    """Purga M6: borra los .jsonl per-máquina con mtime más viejo que
    `otros.retention_days` en events/, telemetry/ y transcripts-backup/.

    GATED por el job `retention` (settings jobs — OFF por default: los
    backups de transcripts son materia prima de la memoria; prenderlo es
    decisión del socio). Solo toca archivos .jsonl bajo esas tres carpetas;
    jamás el cerebro, jamás otros tipos de archivo. Falla-suave por archivo
    (uno ilegible no detiene la purga). `dry_run` = ensayo: solo cuenta lo
    que borraría, no borra nada. Devuelve (borrados, escaneados)."""
    if not _job_enabled("retention"):
        if announce_off:
            out("NIGHTLY: RETENCIÓN off — job `retention` deshabilitado "
                "(settings.py jobs enable retention lo prende)")
        return (0, 0)
    days = _retention_days()
    cutoff = (time.time() if now is None else float(now)) - days * 86400
    removed = scanned = 0
    for root in _retention_roots():
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if not name.endswith(".jsonl"):
                    continue            # SOLO los rastros .jsonl — nada más
                path = os.path.join(dirpath, name)
                scanned += 1
                try:
                    if os.path.getmtime(path) < cutoff:
                        if not dry_run:  # ensayo: contar, jamás borrar
                            os.remove(path)
                        removed += 1
                except OSError:
                    continue            # archivo en uso/ido: seguir
    out("NIGHTLY: RETENCIÓN — purga >%d día(s): %d de %d .jsonl %s "
        "(events/telemetry/transcripts-backup)%s"
        % (days, removed, scanned,
           "se borraría(n)" if dry_run else "borrado(s)",
           " [DRY-RUN]" if dry_run else ""))
    return (removed, scanned)


# ── rotación de log-recent.md (E1 — peso mayor del boot, ~4k tok) ─────────
LOG_RECENT_REL = os.path.join("STATE", "log-recent.md")
LOG_ARCHIVE_REL = os.path.join("STATE", "log-archive")
LOG_RECENT_CAP = 4_000   # chars; configurable en settings (otros.log_recent_cap)


def _log_recent_cap():
    """Tope configurable (settings otros.log_recent_cap). Falla-suave → 4k."""
    try:
        import settings as _settings
        v = _settings.get("otros.log_recent_cap", LOG_RECENT_CAP)
        if isinstance(v, int) and not isinstance(v, bool) and v > 0:
            return v
    except Exception:
        pass
    return LOG_RECENT_CAP


# Fecha ISO en la línea que abre una entrada (`## 2026-10-30`, `## [2026-10-30] …`,
# `- 2026-10-30 · …`, `## 2026-10-30T14:30`): de ahí sale el orden REAL de la
# bitácora. Sin `\b`: la «T» de una hora ISO es letra y escondía la fecha.
_LOG_DATE_RE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")


def _es_item(linea):
    """¿Abre un ítem? Viñeta `- `/`* ` o línea que empieza con fecha («fecha ·
    tema · ruta», como anota la skill research-session)."""
    return linea.startswith(("- ", "* ")) or bool(_LOG_DATE_RE.match(linea))


def _log_fecha(texto):
    """Fecha de una entrada: la más nueva entre su primera línea y los ítems
    que contenga (una sección vale lo que su contenido más reciente), o None."""
    ls = texto.splitlines()
    fs = [m.group(1) for m in (_LOG_DATE_RE.search(l) for l in
                               ls[:1] + [l for l in ls[1:] if _es_item(l)]) if m]
    return max(fs) if fs else None


def _log_items(lines):
    """[(texto, es_entrada)] en orden: cada ítem con sus líneas de
    continuación es una entrada; lo anterior al primer ítem queda fijo."""
    starts = [i for i, l in enumerate(lines) if _es_item(l)]
    if not starts:
        return [("".join(lines), False)] if lines else []
    partes = [("".join(lines[:starts[0]]), False)] if starts[0] else []
    return partes + [("".join(lines[a:b]), True)
                     for a, b in zip(starts, starts[1:] + [len(lines)])]


def _split_log_recent(content, cap):
    """Parte log-recent en (conservar, archivar, lo_nuevo_arriba, aviso).

    Entradas: cada sección `## …` hasta la siguiente (formato de la plantilla:
    una fecha con sus viñetas) y cada ítem suelto antes de la primera sección
    (viñeta o línea fechada, como anota la skill research-session). Lo que va
    antes del primer ítem o sección es la cabecera y se queda siempre. Si hay
    UNA sola sección y sus ítems traen fechas distintas (un agente que anota
    todo bajo la sección de nacimiento o un «## Bitácora»), se abre por ítems
    y su título se queda. Sin secciones ni ítems, cada línea es una entrada.

    Lo más nuevo lo deciden las FECHAS de cada entrada: una fuera de lugar
    (29, 30, 28…) no se archiva por estar abajo. Sin fecha, una entrada hereda
    la de la anterior en el orden del archivo, que también sale de las fechas
    (voto entre consecutivas); sin fechas o con empate manda la plantilla de
    cerebro: «Lo más nuevo arriba». Se conservan las entradas más nuevas que
    quepan en `cap` y se archivan las demás, cada parte en el orden en que
    estaba; se corta ENTRE entradas y la más nueva jamás se archiva. `aviso`
    explica por qué log-recent seguirá sobre el tope (o None)."""
    lines = content.splitlines(True)
    secs = [i for i, l in enumerate(lines) if l.startswith("## ")]
    partes = _log_items(lines[:secs[0] if secs else len(lines)])
    if not secs and not any(e for _, e in partes):
        partes = [(l, True) for l in lines]                # sin estructura: cada línea
    for a, b in zip(secs, secs[1:] + [len(lines)]):
        # solo la ÚNICA sección se abre (con fechas que ordenen sus ítems); la
        # regla no depende del tamaño: la siguiente pasada la vuelve a abrir
        # mientras le queden ítems con fechas distintas
        internas = _log_items(lines[a:b]) if len(secs) == 1 else []
        if len({_log_fecha(t) for t, e in internas if e} - {None}) >= 2:
            partes += internas                             # título fijo + ítems
        else:
            partes.append(("".join(lines[a:b]), True))
    idx = [i for i, (_, e) in enumerate(partes) if e]
    if not idx:
        return content, "", True, "no hay entradas que rotar"
    fechas = {i: _log_fecha(partes[i][0]) for i in idx}
    con_fecha = [fechas[i] for i in idx if fechas[i]]
    pares = list(zip(con_fecha, con_fecha[1:]))
    newest_first = (sum(1 for a, b in pares if a < b)
                    <= sum(1 for a, b in pares if a > b))
    orden = idx if newest_first else idx[::-1]             # por posición: nuevo → viejo
    clave, ultima = {}, None
    for i in orden:
        ultima = fechas[i] or ultima
        clave[i] = ultima or "9999-99-99"                  # las del principio, sin fecha: nuevas
    fijo = sum(len(t) for t, e in partes if not e)
    keep, size = set(), fijo
    for i in sorted(orden, key=clave.get, reverse=True):   # estable: a igual fecha, la posición
        if keep and size + len(partes[i][0]) > cap:
            break
        size += len(partes[i][0])
        keep.add(i)
    conservar = "".join(t for i, (t, e) in enumerate(partes) if not e or i in keep)
    archivar = "".join(t for i, (t, e) in enumerate(partes) if e and i not in keep)
    aviso = None
    if len(conservar) > cap:
        if fijo > cap:
            aviso = ("la cabecera (texto antes de la primera entrada) mide %d "
                     "caracteres, más que el tope" % fijo)
        else:                       # solo cupo la más nueva y sola rebasa el tope
            t = partes[min(keep)][0]
            aviso = ("la entrada más nueva («%s», %d caracteres) sola no cabe "
                     "en el tope y no se parte, para no archivar algo nuevo "
                     "por error" % (t.split("\n", 1)[0].strip()[:60], len(t)))
    return conservar, archivar, newest_first, aviso


def rotate_log_recent(brain, dry_run=False, out=print):
    """Rota el excedente ANTIGUO de STATE/log-recent.md a
    STATE/log-archive/log-YYYY-MM.md (append), dejando la cabecera y solo el
    contenido más reciente (hasta el cap) según el orden REAL del archivo: la
    plantilla pone lo más nuevo ARRIBA (detalle en _split_log_recent).

    Seguridad:
      · Atómica: tmp + os.replace en todos los writes.
      · Falla-suave: cualquier error se reporta y no lanza (log-recent es
        operacional pero no identidad — el agente sigue funcionando).
      · Idempotente: si log-recent ya está bajo el cap, no hace nada.
      · NUNCA toca BOOT/ ni MEMORY.md.
      · No pasa por el gate de secretos: solo REUBICA contenido ya gateado
        (ya estaba en el cerebro); no introduce texto nuevo influenciable.

    Devuelve (rotado_chars, total_chars_antes) o (0, 0) si no aplica.
    """
    brain = os.path.abspath(os.path.expanduser(brain))
    log_path = os.path.join(brain, LOG_RECENT_REL)

    if not os.path.isfile(log_path):
        out("NIGHTLY: LOG-ROTATE — sin log-recent.md en %s (skip)"
            % os.path.basename(brain))
        return (0, 0)

    # R3-F3: el RMW completo (leer → cortar → os.replace) bajo lock N8 sobre
    # log-recent.md — el MISMO lock que usa _append_brain_locked, así un
    # append concurrente (SessionEnd / consolidador) no cae en la ventana
    # read→replace y se pierde. El read ocurre DENTRO del lock. Falla-suave:
    # lock ocupado → skip (la rotación reintenta en el próximo nightly).
    if brain_write.file_lock:
        try:
            with brain_write.file_lock(log_path, timeout=brain_write._lock_timeout()):
                return _rotate_log_recent_rmw(brain, log_path, dry_run, out)
        except brain_write.LockTimeout:
            out("NIGHTLY: LOG-ROTATE — lock ocupado (skip; log-recent intacto)")
            return (0, 0)
    return _rotate_log_recent_rmw(brain, log_path, dry_run, out)


def _rotate_log_recent_rmw(brain, log_path, dry_run, out):
    """Cuerpo read-modify-write de rotate_log_recent (correr BAJO lock)."""
    archive_dir = os.path.join(brain, LOG_ARCHIVE_REL)
    cap = _log_recent_cap()

    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as e:
        out("NIGHTLY: LOG-ROTATE — ERROR: ilegible: %s" % e)
        return (0, 0)

    total = len(content)
    if total <= cap:
        out("NIGHTLY: LOG-ROTATE — %s · %d chars ≤ tope %d — sin rotación"
            % (os.path.basename(brain), total, cap))
        return (0, total)

    # Conservar la cabecera + lo MÁS NUEVO hasta el tope y archivar lo más
    # viejo, en el orden real del archivo. Antes se conservaba siempre el
    # FINAL: con la plantilla (lo nuevo arriba) se archivaba lo más nuevo y
    # log-recent quedaba congelado en lo viejo.
    to_keep, to_archive, newest_first, aviso = _split_log_recent(content, cap)
    rotated = len(to_archive)
    if not rotated:
        out("NIGHTLY: LOG-ROTATE — %s · %d chars > tope %d — sin rotación: %s"
            % (os.path.basename(brain), total, cap, aviso or "nada que rotar"))
        return (0, total)

    month = datetime.date.today().strftime("%Y-%m")
    archive_file = os.path.join(archive_dir, "log-%s.md" % month)

    out("NIGHTLY: LOG-ROTATE — %s · %d chars → rotar %d al archivo "
        "(log-%s.md) · conservar %d (lo nuevo %s)%s"
        % (os.path.basename(brain), total, rotated, month, len(to_keep),
           "arriba" if newest_first else "abajo",
           " [DRY-RUN]" if dry_run else ""))
    if aviso:
        out("NIGHTLY: LOG-ROTATE — ⚠ log-recent seguirá sobre el tope: %s"
            % aviso)

    if dry_run:
        return (rotated, total)

    try:
        os.makedirs(archive_dir, exist_ok=True)
        # Append al archivo mensual (atómico vía lectura+reescritura completa).
        # Si existe pero no se puede leer, el error sube al falla-suave de
        # abajo: tratarlo como vacío lo REEMPLAZABA y se perdía lo ya archivado.
        existing = ""
        try:
            with open(archive_file, encoding="utf-8", errors="replace") as fh:
                existing = fh.read()
        except FileNotFoundError:
            pass                        # primer archivado del mes
        sep = "\n" if existing and not existing.endswith("\n") else ""
        new_archive = existing + sep + to_archive
        tmp_a = archive_file + ".tmp%d" % os.getpid()
        with open(tmp_a, "w", encoding="utf-8") as fh:
            fh.write(new_archive)
        os.replace(tmp_a, archive_file)

        # Reescribir log-recent solo con lo reciente
        tmp_r = log_path + ".tmp%d" % os.getpid()
        with open(tmp_r, "w", encoding="utf-8") as fh:
            fh.write(to_keep)
        os.replace(tmp_r, log_path)

        out("NIGHTLY: LOG-ROTATE — ok · archivado en %s"
            % os.path.relpath(archive_file, brain))
    except Exception as e:
        out("NIGHTLY: LOG-ROTATE — ERROR: %s (falla-suave; log-recent intacto)"
            % e)
        # Limpiar temporales huérfanos sin propagar la excepción
        for tmp in (archive_file + ".tmp%d" % os.getpid(),
                    log_path + ".tmp%d" % os.getpid()):
            try:
                os.remove(tmp)
            except OSError:
                pass
        return (0, total)

    return (rotated, total)


def _maybe_retention(dry_run, out):
    """Purga M6 si el job `retention` está ON (silenciosa
    cuando está off — el aviso explícito es de `--retention`). Best-effort:
    una purga fallida JAMÁS cambia el resultado del mantenimiento."""
    if dry_run:
        return
    try:
        run_retention(out=out, announce_off=False)
    except Exception:
        pass


def _maybe_rotate_logs(brain, dry_run, out):
    """Cola de la pasada: rota log-recent si supera el cap. Best-effort."""
    try:
        rotate_log_recent(brain, dry_run=dry_run, out=out)
    except Exception:
        pass


def _maybe_brain_cleanup(brain, dry_run, out):
    """Cola de la pasada: cuarentena de REGENERABLES (brain_cleanup) SOLO si
    el job `brain-cleanup` está ON (default OFF — toca el cerebro, N3: lo
    prende el socio dueño). Silenciosa cuando está off. En --dry-run del
    nightly corre en dry-run (plan sin mover). Best-effort: un fallo jamás
    cambia el resultado del nightly. NOTA: gate vía brain_cleanup.job_enabled()
    (falla-CERRADO → False), no _job_enabled (falla-abierto): un settings roto
    jamás debe prender solo algo que toca el cerebro."""
    try:
        import brain_cleanup
        if not brain_cleanup.job_enabled():
            return
        brain_cleanup.run_cleanup(brain, apply=not dry_run, out=out)
        if not dry_run:
            brain_cleanup.purge_trash(out=out)
    except Exception:
        pass


def _maybe_reindex(brain, dry_run, out):
    """Cola de la pasada: refresca el índice FTS5 (E3) si está stale. Es
    DERIVADO y regenerable → best-effort puro: un fallo jamás cambia el
    resultado del nightly. Si memory_index no está, se ignora (amputable)."""
    if dry_run:
        return
    try:
        import memory_index
        if memory_index.is_stale(brain):
            memory_index.reindex(brain, out=out)
    except Exception:
        pass


def run(brain, dry_run=False, out=print, force=False):
    """El mantenimiento mecánico completo de un cerebro (sin IA)."""
    if not force and not _job_enabled("consolidador-nocturno"):
        out("NIGHTLY: OFF — job `consolidador-nocturno` deshabilitado "
            "(settings.py jobs enable consolidador-nocturno lo prende; "
            "--force puentea a mano)")
        return 0
    brain = os.path.abspath(os.path.expanduser(brain))
    if not os.path.isdir(os.path.join(brain, "STATE")):
        out("NIGHTLY: ERROR — %s no parece un cerebro (sin STATE/)" % brain)
        return 2
    _maybe_retention(dry_run, out)
    _maybe_rotate_logs(brain, dry_run, out)
    _maybe_reindex(brain, dry_run, out)
    _maybe_brain_cleanup(brain, dry_run, out)
    return 0


def status(brain, out=print):
    brain = os.path.abspath(os.path.expanduser(brain))
    log = os.path.join(brain, LOG_RECENT_REL)
    try:
        size = os.path.getsize(log)
    except OSError:
        size = 0
    out("NIGHTLY: STATUS — %s · mantenimiento %s · retención %s · limpieza %s · "
        "log-recent %d/%d chars" % (
            os.path.basename(brain),
            "on" if _job_enabled("consolidador-nocturno") else "off",
            "on" if _job_enabled("retention") else "off",
            "on" if _job_enabled("brain-cleanup") else "off",
            size, _log_recent_cap()))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="nightly.py",
        description="Mantenimiento mecánico (sin IA): retención, rotación de "
                    "log-recent, índice y limpieza de regenerables.")
    ap.add_argument("--brain", default=os.getcwd(),
                    help="ruta del cerebro (default: cwd)")
    ap.add_argument("--dry-run", action="store_true",
                    help="planea sin escribir ni borrar nada")
    ap.add_argument("--status", action="store_true",
                    help="estado del mantenimiento para este cerebro")
    ap.add_argument("--force", action="store_true",
                    help="corre aunque el job consolidador-nocturno esté off")
    ap.add_argument("--retention", action="store_true",
                    help="SOLO la purga M6 (job `retention` + otros.retention_days)")
    ap.add_argument("--rotate-logs", action="store_true",
                    help="SOLO rotar log-recent.md si supera el tope (E1). "
                         "Atómico, falla-suave, idempotente. Respeta --dry-run.")
    args = ap.parse_args(argv)
    if args.status:
        return status(args.brain)
    if args.retention:
        run_retention(dry_run=args.dry_run)
        return 0
    if args.rotate_logs:
        brain = os.path.abspath(os.path.expanduser(args.brain))
        rotate_log_recent(brain, dry_run=args.dry_run)
        return 0
    return run(args.brain, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
