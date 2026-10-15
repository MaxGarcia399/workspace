"""Deterministic, provider-neutral continuity. No LLM calls or credentials.

Shared: validated checkpoints in STATE/sessions/<socio>/checkpoints/*.md.
Local: capture/distillation receipts outside the brain. Unknown stays unknown.
"""
import argparse
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
from contextlib import closing
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
import time
import sqlite3
import shutil
import uuid

from olock import file_lock

FIELDS = ("objective", "decision", "blocker", "next_step", "result")
LABELS = ("Objetivo", "Decisión", "Bloqueo", "Siguiente paso", "Resultado")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def checkpoint_path(brain, tab):
    import sessions_registry as reg
    source = reg._md_path(str(brain), tab)
    if not source or not Path(source).is_file():
        raise ValueError("La pestaña debe existir para guardar un checkpoint")
    # Never accept a path-like socio from configuration.
    directory = Path(source).parent.resolve()
    base = (Path(brain) / "STATE" / "sessions").resolve()
    if base not in directory.parents:
        raise ValueError("Socio fuera de STATE/sessions")
    return directory / "checkpoints" / (Path(source).stem + ".md")


def read_checkpoint(brain, tab):
    try:
        text = checkpoint_path(brain, tab).read_text(encoding="utf-8")
        data = json.loads(text.split("```json\n", 1)[1].split("\n```", 1)[0])
        if data.get("schema") != 1 or not isinstance(data.get("revision"), int):
            return None
        if data["revision"] < 1 or not isinstance(data.get("updated"), str) or len(data["updated"]) > 40:
            return None
        if any(not isinstance(data.get(k), str) or len(data[k]) > 600 for k in FIELDS):
            return None
        return data
    except (OSError, ValueError, IndexError, TypeError, AttributeError):
        return None


def write_checkpoint(brain, tab, expected_revision=None, engine="", **fields):
    """Explicit semantic fields only; validation, CAS and persistence in code."""
    from secret_scan import scan_text
    import sessions_registry as reg
    path = checkpoint_path(brain, tab)
    clean = {}
    for k in FIELDS:
        v = fields.get(k, "")
        if not isinstance(v, str) or len(v) > 600 or "\x00" in v:
            raise ValueError("Campo inválido o mayor a 600 caracteres: " + k)
        clean[k] = " ".join(v.split())
    if not clean["objective"] or not clean["next_step"]:
        raise ValueError("Objetivo y siguiente paso son obligatorios")
    from secret_scan import ALLOW_MARKER
    if scan_text(json.dumps(clean, ensure_ascii=False).replace(ALLOW_MARKER, "")):
        raise ValueError("Checkpoint rechazado: contiene posibles secretos")
    lock = local_root() / (hashlib.sha256(str(path).encode()).hexdigest() + ".checkpoint")
    with file_lock(str(lock), timeout=5):
        previous = read_checkpoint(brain, tab)
        if path.exists() and previous is None:
            raise ValueError("Checkpoint corrupto: conservar y reparar explícitamente")
        revision = previous["revision"] if previous else 0
        if expected_revision is None:
            raise ValueError("Se requiere --expected-revision para evitar pisar otro chat")
        if expected_revision != revision:
            raise ValueError("Conflicto de revisión: actual=%s" % revision)
        data = dict(clean, schema=1, revision=revision + 1, updated=now(),
                    engine=engine, tab=reg._slug(tab), checkpoint_id=uuid.uuid4().hex)
        # Immutable version + latest pointer, both synchronized Markdown.
        version = path.parent / "history" / (path.stem + "-" + data["checkpoint_id"] + ".md")
        text = "# Checkpoint de continuidad\n\n```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```\n"
        atomic(version, text)
        atomic(path, text)
    return data


def select_memory(text, limit=1200):
    """Deterministic budget: current summary + latest complete history lines."""
    if limit <= 0:
        return ""
    if text.lstrip().startswith("---"):
        pieces = text.split("---", 2)
        text = pieces[2].strip() if len(pieces) == 3 else text.strip()
    else:
        text = text.strip()
    if len(text) <= limit:
        return text
    marker = "[… recortado; consultar ficha completa …]"
    budget = max(0, limit - len(marker) - 1)
    if budget == 0:
        return marker[:limit]
    if "## Historial" in text:
        head, history = text.split("## Historial", 1)
        head = head.strip()[:budget // 3]
        tail = history.strip()[-max(0, budget - len(head) - 15):]
        result = head + "\n## Historial\n" + tail
    else:
        result = text[-budget:]
    return (marker + "\n" + result)[-limit:] if limit < len(marker) else (marker + "\n" + result)[:limit]


def context(brain, tab, limit=1200):
    cp = read_checkpoint(brain, tab)
    if not cp:
        return ""
    title = "Checkpoint vigente · revisión %s · %s\n" % (cp["revision"], cp["updated"])
    rows = ["%s: %s" % (label, cp[k] or "sin registrar") for label, k in zip(LABELS, FIELDS)]
    text = title + "\n".join(rows)
    if len(text) <= limit:
        return text
    # Distribute a fixed allowance across fields; never omit next_step.
    budget = max(0, (limit - len(title) - 100) // len(FIELDS))
    rows = ["%s: %s" % (label, cp[k][:budget] + ("…" if len(cp[k]) > budget else ""))
            for label, k in zip(LABELS, FIELDS)]
    return (title + "\n".join(rows) + "\n[… checkpoint recortado; leer detalle …]")[:limit]


def local_root():
    p = Path(_paths.state_dir(str(Path.home()))) / "continuity"
    p.mkdir(parents=True, exist_ok=True)
    return p


def receipt_path(brain):
    key = hashlib.sha256(os.path.realpath(brain).encode()).hexdigest()
    return local_root() / (key + ".json")


def receipts(brain):
    p = receipt_path(brain)
    if not p.exists():
        return {"schema": 1, "runs": {}}
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("runs"), dict):
        raise ValueError("Estado local de continuidad inválido")
    return data


def record(brain, run_id, **values):
    p = receipt_path(brain)
    with file_lock(str(p), timeout=5):
        data = receipts(brain)
        row = data["runs"].setdefault(run_id, {})
        row.update(values)
        row["updated"] = now()
        atomic(p, json.dumps(data, ensure_ascii=False, indent=2))


def resolve_codex(brain, started, root=None, expected_sid=""):
    """Match cwd+mtime; reject ambiguity instead of claiming another tab's chat."""
    from engines import codex
    matches = []
    for path in codex._recent_rollouts(root or codex._sessions_root(), limit=64):
        try:
            if os.path.getmtime(path) < started - 1:
                continue
            with open(path, encoding="utf-8") as f:
                meta = json.loads(f.readline()).get("payload") or {}
            if os.path.realpath(meta.get("cwd") or "") != os.path.realpath(brain):
                continue
            sid = meta.get("session_id") or meta.get("id") or ""
            if sid and (not expected_sid or sid == expected_sid):
                matches.append((sid, path))
        except (OSError, ValueError, TypeError):
            continue
    if len(matches) != 1:
        return {"capture_state": "ambiguous" if matches else "missing"}
    return {"session_id": matches[0][0], "transcript_path": matches[0][1],
            "capture_state": "resolved"}


def capture_antigravity(brain, started):
    """Consistent SQLite snapshot; decoding proprietary payloads is separate."""
    from engines import antigravity as agy
    import session_paths
    cid = agy._vendor_conversation_for(brain)
    if not cid or not agy._conversation_exists(cid):
        return {"capture_state": "missing", "distillation_state": "unsupported-format"}
    source = Path(agy._agy_home()) / "conversations" / (cid + ".db")
    wal_path = Path(str(source) + "-wal")
    modified = max(p.stat().st_mtime for p in (source, wal_path) if p.exists())
    if modified < started - 1:
        return {"capture_state": "stale", "distillation_state": "unsupported-format"}
    dest = Path(_paths.state_dir(str(Path.home()))) / "transcripts-backup" / Path(session_paths.session_dir(brain)).name / ("antigravity-" + cid + ".db")
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=dest.name + ".", dir=str(dest.parent))
    os.close(fd)
    try:
        # Original vendor storage may reject SQLite locks even when byte
        # reads are permitted. Clone DB + WAL, rejecting concurrent changes;
        # let SQLite recover the disposable copy, never the vendor files.
        with tempfile.TemporaryDirectory(prefix="agy-snapshot-") as scratch:
            clone = Path(scratch) / "conversation.db"
            wal = Path(str(source) + "-wal")
            journal = Path(str(source) + "-journal")
            def signature():
                if journal.exists():
                    raise OSError("Active rollback journal; retry after closing Antigravity")
                return tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns)
                             for p in (source, wal) if p.exists())
            before = signature()
            shutil.copyfile(source, clone)
            if wal.exists():
                shutil.copyfile(wal, Path(str(clone) + "-wal"))
            if signature() != before:
                raise OSError("Database changed while copying; retry capture")
            with closing(sqlite3.connect(str(clone))) as src:
                with closing(sqlite3.connect(tmp)) as dst:
                    deadline = time.monotonic() + 5
                    def progress(status, remaining, total):
                        if time.monotonic() > deadline:
                            raise TimeoutError("SQLite snapshot timeout")
                    src.backup(dst, pages=256, progress=progress, sleep=0.05)
                    if dst.execute("pragma quick_check").fetchone() != ("ok",):
                        raise sqlite3.DatabaseError("Snapshot integrity check failed")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    result = {"session_id": cid, "capture_state": "captured", "captured_at": now(),
              "backup": str(dest), "native_format": "sqlite",
              "distillation_state": "unsupported-format"}
    # Documented hook log avoids decoding proprietary SQLite blobs.
    log = Path(agy._agy_home()) / "brain" / cid / ".system_generated" / "logs" / "transcript.jsonl"
    if log.is_file():
        import neutral_transcript
        target = dest.with_suffix(".jsonl")
        fd, log_tmp = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
        os.close(fd)
        try:
            before = (log.stat().st_size, log.stat().st_mtime_ns)
            shutil.copyfile(log, log_tmp)
            after = (log.stat().st_size, log.stat().st_mtime_ns)
            if before != after:
                raise OSError("Antigravity transcript changed while copying")
            doc = neutral_transcript.parse_antigravity(log_tmp)
            doc["session"]["id"] = cid
            if neutral_transcript.validate(doc) or not doc["turns"]:
                raise ValueError("No validated visible Antigravity dialogue")
            os.replace(log_tmp, target)
            result.update(transcript_backup=str(target), distillation_state="pending",
                          dialogue_turns=len(doc["turns"]))
        except (OSError, ValueError) as exc:
            result["transcript_error"] = type(exc).__name__
        finally:
            if os.path.exists(log_tmp):
                os.unlink(log_tmp)
    return result


def close_payload(brain, engine, started, payload, run_id):
    result = dict(payload, source="exit", run_id=run_id)
    tab = os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS") or ""
    result["tab"] = tab
    import settings
    if os.environ.get("WORKSPACE_NO_TRANSCRIPT_BACKUP") or not settings.enabled("hooks.transcript_backup", default=True):
        result["capture_state"] = "disabled"
    elif engine == "codex":
        result.update(resolve_codex(brain, started))
    elif engine == "antigravity":
        try:
            result.update(capture_antigravity(brain, started))
        except (OSError, ValueError, TimeoutError, sqlite3.Error) as exc:
            result.update(capture_state="failed", distillation_state="unsupported-format",
                          capture_error=type(exc).__name__)
            print("WORKSPACE: respaldo Antigravity falló (%s); consulta workspace memoria status" % type(exc).__name__, file=__import__("sys").stderr)
        # Los listeners de session_end (revisión de skills) leen el contrato
        # de siempre: `transcript_path` + `cwd`. En Antigravity el transcript
        # legible es la copia del log de diálogo (no el .db propietario).
        if result.get("transcript_backup"):
            result["transcript_path"] = result["transcript_backup"]
    else:
        result["capture_state"] = "unsupported"
    result.setdefault("cwd", brain)
    record(brain, run_id, engine=engine, tab=tab,
           session_id=result.get("session_id", ""),
           capture_state=result["capture_state"], distilled_at=None,
           consolidated_at=None, **{k: result[k] for k in
               ("backup", "captured_at", "native_format", "distillation_state", "capture_error", "transcript_backup", "transcript_error", "dialogue_turns") if k in result})
    return result


def captured(brain, payload, backup):
    if not brain:
        return
    sid = str(payload.get("session_id") or Path(backup).stem)
    rid = payload.get("run_id") or sid
    st = os.stat(backup)
    signature = "%s:%s" % (st.st_size, st.st_mtime_ns)
    old = receipts(brain)["runs"].get(rid, {})
    invalidation = {} if old.get("signature") == signature else {"distilled_at": None, "consolidated_at": None}
    record(brain, rid, signature=signature, **invalidation,
           session_id=sid, engine=payload.get("engine", "claude-code"),
           tab=payload.get("tab") or os.environ.get("WORKSPACE_WS", ""),
           capture_state="captured", captured_at=now(), backup=backup)


def distilled(brain, session_id, journal):
    data = receipts(brain)
    for rid, row in data["runs"].items():
        if row.get("session_id") == session_id:
            record(brain, rid, distilled_at=now(), journal=journal)


def consolidated(brain, session_id):
    """Sella consolidated_at. Solo tras revisión humana (gate N1): este módulo
    JAMÁS promueve a MEMORY.md; la promoción vive en el inbox + consolidador."""
    data = receipts(brain)
    for rid, row in data["runs"].items():
        if row.get("session_id") == session_id:
            record(brain, rid, consolidated_at=now())


# ── consolidación · revisión humana (gate N1 🔴) ─────────────────────────────
# El pipeline Dreaming deja candidatos en STATE/DESTILADO.md con checkbox. El
# checkbox marcado `[x]` ES la aprobación explícita del socio (N1). Consolidar =
# recoger SOLO lo marcado y anexarlo al inbox (append-only); el consolidador /
# el humano promueve a MEMORY.md. Lo no marcado nunca se promueve, así un
# candidato mal atribuido (p.ej. recomendación del agente etiquetada "decision")
# queda inerte mientras nadie lo marque.
DESTILADO_REL = os.path.join("STATE", "DESTILADO.md")
_CAND = re.compile(r"^- \[([ xX])\]\s+\*\*\((\d+)[^·)]*·\s*([^)]+)\)\*\*\s*(.+)$")


def _destilado_candidates(brain, sid8):
    """Candidatos de la sección de DESTILADO.md de esta sesión (por sid8 en el
    header `## … · <sid8> (…`), con su estado de checkbox. [] si no hay sección
    (no destilado / sin candidatos sobre umbral)."""
    try:
        lines = (Path(brain) / DESTILADO_REL).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    marker = "· %s (" % sid8
    start = next((i for i, l in enumerate(lines)
                  if l.startswith("## ") and marker in l), None)
    if start is None:
        return []
    end = next((j for j in range(start + 1, len(lines))
                if lines[j].startswith("## ")), len(lines))
    out = []
    for l in lines[start + 1:end]:
        m = _CAND.match(l.strip())
        if m:
            out.append({"approved": m.group(1).lower() == "x",
                        "score": int(m.group(2)), "tipo": m.group(3).strip(),
                        "texto": m.group(4).strip()})
    return out


def _inbox_append(brain, socio, titulo, campos):
    """APPEND-only a STATE/inbox/<socio>-AAAA-MM-DD.md. Nunca toca canónicos
    (MEMORY/INDEX). `campos` = [(etiqueta, valor)]. Ruta o None."""
    who = re.sub(r"[^a-z0-9_-]", "", str(socio or "").lower())
    if not who or not os.path.isdir(brain):
        return None
    hoy = datetime.date.today().isoformat()
    idir = Path(brain) / "STATE" / "inbox"
    fp = idir / ("%s-%s.md" % (who, hoy))
    idir.mkdir(parents=True, exist_ok=True)
    fresh = not fp.exists()
    body = ["## Entry — consolidación de memoria: %s"
            % str(titulo).replace("\n", " ")[:160],
            "- op: consolidación de memoria",
            "- origen: workspace memoria consolidate"]
    for k, v in campos:
        if v:
            body.append("- %s: %s" % (k, str(v).replace("\n", " ")))
    with file_lock(str(fp), timeout=5):
        with open(fp, "a", encoding="utf-8") as fh:
            if fresh:
                fh.write("# Inbox %s — %s\n" % (who, hoy))
            fh.write("\n" + "\n".join(body) + "\n")
    return str(fp)


def pending_consolidation(brain, tab):
    """Runs de la pestaña destilados pero no consolidados."""
    rows = []
    for rid, row in receipts(brain)["runs"].items():
        if tab and row.get("tab") != tab:
            continue
        if row.get("distilled_at") and not row.get("consolidated_at"):
            rows.append((rid, row.get("session_id") or "", row))
    return rows


def consolidate(brain, tab, apply=False, allow_empty=False):
    """Revisión humana de candidatos destilados. apply=False → solo reporta
    (read-only). apply=True → promueve SOLO los `[x]` al inbox y sella
    consolidated_at. Jamás escribe MEMORY.md."""
    import sessions_registry as reg
    soc = reg.socio(brain)
    report = {"tab": tab, "socio": soc, "applied": bool(apply), "runs": []}
    seen = set()
    for rid, sid, row in pending_consolidation(brain, tab):
        key = sid or rid
        if key in seen:        # una sesión = una entrada (varios runs = misma captura)
            continue
        seen.add(key)
        sid8 = (sid or rid)[:8]
        cands = _destilado_candidates(brain, sid8)
        approved = [c for c in cands if c["approved"]]
        entry = {"session_id": sid, "sid8": sid8, "journal": row.get("journal"),
                 "candidates": len(cands), "approved": len(approved)}
        if apply:
            if not cands:
                entry["status"] = "sin-destilado"          # nada que revisar
            elif not approved and not allow_empty:
                entry["status"] = "sin-marcar"              # requiere checkbox
            else:
                inbox = None
                if approved:
                    inbox = _inbox_append(
                        brain, soc, "sesión %s" % sid8,
                        [("candidato", "(%d · %s) %s"
                          % (c["score"], c["tipo"], c["texto"]))
                         for c in approved])
                if sid:
                    consolidated(brain, sid)
                else:
                    record(brain, rid, consolidated_at=now())
                entry["status"] = "consolidado" if approved else "revisado-vacío"
                entry["promoted"] = len(approved)
                entry["inbox"] = inbox
        else:
            entry["status"] = "pendiente"
            entry["items"] = [{"approved": c["approved"], "tipo": c["tipo"],
                               "score": c["score"], "texto": c["texto"]}
                              for c in cands]
        report["runs"].append(entry)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(prog="workspace memoria")
    p.add_argument("command", choices=("checkpoint", "context", "status", "consolidate"))
    p.add_argument("--brain", default=os.getcwd())
    p.add_argument("--tab", default=os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS"))
    p.add_argument("--expected-revision", type=int)
    p.add_argument("--engine", default="")
    p.add_argument("--apply", action="store_true",
                   help="consolidate: promueve lo marcado [x] al inbox y sella")
    p.add_argument("--allow-empty", action="store_true",
                   help="consolidate --apply: sella aunque nada esté marcado")
    for k in FIELDS:
        p.add_argument("--" + k.replace("_", "-"), default="")
    a = p.parse_args(argv)
    try:
        if a.command == "status":
            data = receipts(a.brain)
            if a.tab:
                data["runs"] = {k: v for k, v in data["runs"].items() if v.get("tab") == a.tab}
                cp = read_checkpoint(a.brain, a.tab)
                data["checkpoint"] = {k: cp[k] for k in ("revision", "updated")} if cp else None
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif not a.tab:
            raise ValueError("Falta --tab o WORKSPACE_WS")
        elif a.command == "context":
            print(context(a.brain, a.tab))
        elif a.command == "consolidate":
            print(json.dumps(consolidate(a.brain, a.tab, a.apply, a.allow_empty),
                             ensure_ascii=False, indent=2))
        else:
            cp = write_checkpoint(a.brain, a.tab, a.expected_revision, engine=a.engine,
                                  **{k: getattr(a, k) for k in FIELDS})
            print(json.dumps({"ok": True, "revision": cp["revision"]}))
        return 0
    except (ValueError, OSError, TimeoutError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
