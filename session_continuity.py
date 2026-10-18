"""Deterministic, provider-neutral continuity. No LLM calls or credentials.

Shared: validated checkpoints in STATE/sessions/<socio>/checkpoints/*.md.
Local: capture receipts outside the brain. Unknown stays unknown.
Notes, Vigente, maleta and compaction live in memoria.py (memoria v1); the old
human review of distilled candidates (STATE/DESTILADO.md) was retired with it.
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


#: Checkpoint todavía vacío que Workspace deja creado ANTES de abrir un motor
#: con sandbox (Codex): lo que el sandbox crea de cero queda ilegible para el
#: socio, pero reescribir un archivo que ya existe conserva sus permisos.
VACIO = ("# Checkpoint de continuidad\n\n(sin resumen todavía: el agente lo guarda con "
         "«workspace memoria checkpoint»)\n")


def _relleno_necesario():
    """El relleno solo hace falta en Windows: ahí lo que CREA el sandbox de
    Codex queda con permisos que el socio no puede leer. En Mac y Linux lo
    crea con el dueño de siempre."""
    return os.name == "nt"


def preparar_checkpoint(brain, tab):
    """Deja el checkpoint de la pestaña creado (vacío) si no existe y hace
    falta (Windows). Lo corre el lanzador, fuera del sandbox. El relleno
    viaja por Obsidian y una versión anterior de Workspace lo toma por un
    checkpoint corrupto (revisión 0.3.4): no se deja donde no sirve y al
    cerrar se quita si sigue vacío (quitar_vacio). Falla-suave: False."""
    try:
        path = checkpoint_path(brain, tab)
        if not path.exists() and _relleno_necesario():
            atomic(path, VACIO)
        return True
    except (OSError, ValueError):
        return False


def quitar_vacio(brain, tab):
    """Al cerrar la sesión: el relleno que sigue vacío se quita, con el
    candado del checkpoint. Un resumen de verdad nunca se toca. → True si lo
    quitó."""
    from olock import local_lock
    try:
        path = checkpoint_path(brain, tab)
    except ValueError:
        return False
    if not path.exists():
        return False
    with local_lock(str(path), timeout=5):
        if _es_vacio(path):
            os.remove(str(path))
            return True
    return False


def _es_vacio(path):
    try:
        return path.read_text(encoding="utf-8").strip() == VACIO.strip()
    except OSError:
        return False


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
    # memoria v1: candado fuera del cerebro (o en <cerebro>/.claude/ dentro del
    # sandbox de un motor, donde el estado per-máquina no se puede escribir).
    from olock import local_lock, sin_estado
    engine = engine or os.environ.get("WORKSPACE_ENGINE", "")
    with local_lock(str(path), timeout=5):
        previous = read_checkpoint(brain, tab)
        if path.exists() and previous is None and not _es_vacio(path):
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
        if sin_estado() and path.exists():
            # Dentro del sandbox de un motor, un archivo NUEVO puede quedar
            # ilegible para el socio: sin versión nueva en history/ y el
            # vigente se reescribe en su lugar (conserva sus permisos).
            with open(path, "r+", encoding="utf-8") as fh:
                fh.seek(0)
                fh.write(text)
                fh.truncate()
            return data
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
        return {"capture_state": "missing"}
    source = Path(agy._agy_home()) / "conversations" / (cid + ".db")
    wal_path = Path(str(source) + "-wal")
    modified = max(p.stat().st_mtime for p in (source, wal_path) if p.exists())
    if modified < started - 1:
        return {"capture_state": "stale"}
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
              "backup": str(dest), "native_format": "sqlite"}
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
            result.update(transcript_backup=str(target), dialogue_turns=len(doc["turns"]))
        except (OSError, ValueError) as exc:
            result["transcript_error"] = type(exc).__name__
        finally:
            if os.path.exists(log_tmp):
                os.unlink(log_tmp)
    return result


def capture_opencode(brain, started, session_id="", exe=None, runner=None):
    """Transcript de ESTA sesión vía el export OFICIAL de opencode
    (`opencode session export <id>` → JSON con info + messages), guardado como
    `opencode-<id>.jsonl` junto a los demás respaldos y legible por
    neutral_transcript.parse_opencode → revisión de skills y maleta.
    Antes se copiaba el SQLite GLOBAL: todas las sesiones de todos los
    proyectos, con un nombre fijo que se pisaba en cada cierre y sin
    transcript legible. `session_id` = el `ses_ws…` que el adapter ató a la
    pestaña (env WORKSPACE_OPENCODE_SESSION). `exe`/`runner`: knobs de test."""
    import subprocess
    import session_paths
    import neutral_transcript as nt
    from engines import opencode as _oc
    sid = str(session_id or os.environ.get("WORKSPACE_OPENCODE_SESSION") or "").strip()
    exe = exe or shutil.which("opencode")
    find = os.environ.get("WORKSPACE_OPENCODE_FIND")
    if not sid and find and exe:
        # opencode 1: la pestaña abrió sin id → la sesión que creó (y se deja en
        # el entorno para que el adapter la ate a la pestaña).
        try:
            sid = _oc.find_new_session(exe, json.loads(find), cwd=str(brain) if brain else None,
                                       runner=runner)
        except (ValueError, TypeError):
            sid = ""
        if sid:
            os.environ["WORKSPACE_OPENCODE_SESSION"] = sid
    if not re.fullmatch(r"ses[A-Za-z0-9_-]{4,96}", sid):
        st = {"capture_state": "missing"}
        if find:
            st["capture_error"] = "no encontré una sesión única de esta pestaña"
        return st
    if not exe:
        return {"capture_state": "missing", "session_id": sid}
    run = runner or subprocess.run
    extra = {} if runner else dict(_oc._sin_consola(), env=_oc._env_motor())
    r = run(_oc.export_cmd(exe, sid, runner=runner), cwd=str(brain) if brain else None,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, **extra)
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        # "Session not found": se abrió y cerró sin mensajes → no hay qué capturar.
        state = "missing" if "not found" in err.lower() else "failed"
        return {"capture_state": state, "session_id": sid,
                "capture_error": err[:200] or "export rc=%s" % r.returncode}
    out = r.stdout or ""
    data = json.loads(out[out.find("{"):]) if "{" in out else None
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        raise ValueError("Export de opencode sin el formato esperado")
    info = data.get("info") or {}
    if info.get("id") != sid:
        raise ValueError("El export de opencode es de otra sesión")
    times = info.get("time") or {}
    try:
        if times.get("updated") is not None and float(times["updated"]) / 1000.0 < started - 1:
            return {"capture_state": "stale", "session_id": sid}
    except (TypeError, ValueError):
        pass
    dest_dir = (Path(_paths.state_dir(str(Path.home()))) / "transcripts-backup"
                / Path(session_paths.session_dir(brain)).name)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / ("opencode-%s.jsonl" % sid)
    header = {"type": nt.OPENCODE_HEADER, "id": sid, "title": info.get("title") or "",
              "directory": (info.get("location") or {}).get("directory") or str(brain),
              "created": times.get("created"), "updated": times.get("updated")}
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=str(dest_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(header, ensure_ascii=False) + "\n")
            for m in data["messages"]:
                fh.write(json.dumps({"type": nt.OPENCODE_MESSAGE, "message": m},
                                    ensure_ascii=False) + "\n")
        doc = nt.parse_opencode(tmp)
        if nt.validate(doc) or not doc["turns"]:
            return {"capture_state": "missing", "session_id": sid,
                    "capture_error": "sin diálogo visible"}
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"capture_state": "captured", "captured_at": now(), "session_id": sid,
            "backup": str(target), "native_format": "opencode-export-json",
            "transcript_backup": str(target), "dialogue_turns": len(doc["turns"])}


def _iso_epoch(ts):
    """'2026-10-16T06:15:30.487Z' → epoch (float) o None."""
    try:
        import datetime
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _capture_openclaw_export(brain, started, key, aid, exe=None, runner=None):
    """OpenClaw 2026.9.x/2026.10.x (VERIFICADO 2026-10-16): las sesiones viven en
    SQLite (`agents/<id>/agent/openclaw-agent.sqlite`), ya no en `.jsonl` con
    `sessions.json`. El camino OFICIAL es `sessions export-trajectory
    --session-key <clave>` (exporta un paquete redactado): su
    `session-branch.json` = {header, entries} con la MISMA forma de los
    renglones del `.jsonl` de antes → se reescribe como `.jsonl` y lo lee
    neutral_transcript.parse_openclaw. Se exporta a una carpeta temporal
    (jamás al cerebro). `exe`/`runner`: knobs de test."""
    import session_paths
    import neutral_transcript as nt
    from engines import openclaw as _oc
    exe = exe or _oc._exe()
    if not exe:
        return {"capture_state": "missing",
                "capture_error": "openclaw no está en PATH"}
    tmpd = tempfile.mkdtemp(prefix="ws-openclaw-export-")
    try:
        r = _oc._run(_oc._base(exe) + ["sessions", "export-trajectory", "--agent", aid,
                                       "--session-key", key, "--workspace", tmpd,
                                       "--output", "ws", "--json"],
                     runner=runner, timeout=120, cwd=tmpd)
        if getattr(r, "returncode", 1) != 0:
            # Se abrió y cerró sin turnos: OpenClaw no creó la sesión.
            err = ((getattr(r, "stderr", "") or "") + (getattr(r, "stdout", "") or "")).strip()
            return {"capture_state": "missing",
                    "capture_error": err[-200:] or "export rc=%s" % getattr(r, "returncode", "?")}
        info = _oc._json_out(getattr(r, "stdout", "") or "") or {}
        out_dir = os.path.realpath(str(info.get("outputDir") or os.path.join(
            tmpd, ".openclaw", "trajectory-exports", "ws")))
        if not out_dir.startswith(os.path.realpath(tmpd) + os.sep):
            raise ValueError("export de OpenClaw fuera de la carpeta temporal")
        with open(os.path.join(out_dir, "session-branch.json"), encoding="utf-8") as fh:
            branch = json.load(fh)
        header = branch.get("header") if isinstance(branch, dict) else None
        entries = branch.get("entries") if isinstance(branch, dict) else None
        if not isinstance(header, dict) or not isinstance(entries, list):
            return {"capture_state": "missing",
                    "capture_error": "export sin header/entries"}
        sid = str(header.get("id") or info.get("sessionId") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{4,96}", sid):
            raise ValueError("id de sesión de OpenClaw inválido")
        # VERIFICADO 2026.9.33: session-branch.json RECORTA las entradas de una
        # sesión larga («[Truncated]», sin fecha ni texto); events.jsonl trae
        # cada mensaje completo (`user.message`/`assistant.message` con
        # data.message). Si está, manda events.jsonl; si no, la rama.
        ev_path = os.path.join(out_dir, "events.jsonl")
        if os.path.isfile(ev_path):
            rows = []
            with open(ev_path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    msg = (ev.get("data") or {}).get("message") if isinstance(ev, dict) else None
                    if ev.get("type") in ("user.message", "assistant.message") \
                            and isinstance(msg, dict):
                        rows.append({"type": "message", "timestamp": ev.get("ts"),
                                     "message": msg})
            if rows:
                entries = rows
        last = max([t for t in (_iso_epoch(e.get("timestamp")) for e in entries
                                if isinstance(e, dict)) if t] or [0])
        if last and last < started - 1:
            return {"capture_state": "stale", "session_id": sid}
        dest_dir = (Path(_paths.state_dir(str(Path.home()))) / "transcripts-backup"
                    / Path(session_paths.session_dir(brain)).name)
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / ("openclaw-%s.jsonl" % sid)
        fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=str(dest_dir))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            for row in [header] + entries:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        try:
            doc = nt.parse_openclaw(tmp)
            if nt.validate(doc) or not doc["turns"]:
                return {"capture_state": "missing", "session_id": sid,
                        "capture_error": "sin diálogo visible"}
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return {"capture_state": "captured", "captured_at": now(), "session_id": sid,
                "backup": str(target), "native_format": "openclaw-trajectory-branch",
                "transcript_backup": str(target), "dialogue_turns": len(doc["turns"])}
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def capture_openclaw(brain, started, session_key="", state=None, exe=None, runner=None):
    """Transcript de ESTA sesión de OpenClaw (2026.5.12, VERIFICADO): la clave
    de la pestaña (`agent:<id>:ws-…`, env WORKSPACE_OPENCLAW_SESSION) se
    resuelve en `<estado>/agents/<id>/sessions/sessions.json` → `sessionFile`
    (`<sessionId>.jsonl`, transcript oficial legible). Copia estable a
    `openclaw-<sessionId>.jsonl` junto a los demás respaldos. `state` =
    directorio de estado del perfil de Workspace (knob de test)."""
    import session_paths
    import neutral_transcript as nt
    key = str(session_key or os.environ.get("WORKSPACE_OPENCLAW_SESSION") or "").strip()
    m = re.fullmatch(r"agent:([a-z0-9-]{1,64}):[A-Za-z0-9_.-]{1,96}", key)
    if not m:
        return {"capture_state": "missing"}
    if state is None:
        from engines import openclaw as _oc
        state = _oc.state_dir()
    state = os.path.realpath(state)
    index = Path(state) / "agents" / m.group(1) / "sessions" / "sessions.json"
    if not index.is_file():
        # 2026.9+: sin índice .json — las sesiones están en SQLite → export oficial
        return _capture_openclaw_export(brain, started, key, m.group(1), exe=exe, runner=runner)
    try:
        entry = (json.loads(index.read_text(encoding="utf-8")) or {}).get(key)
    except (OSError, ValueError):
        entry = None
    if not isinstance(entry, dict) or not entry.get("sessionFile"):
        # Se abrió y cerró sin turnos: OpenClaw no creó la sesión (mismo texto
        # que el export de 2026.9+: la pestaña suelta la clave, hallazgo 16).
        return {"capture_state": "missing",
                "capture_error": "Session not found: %s" % key}
    sid = str(entry.get("sessionId") or "")
    source = Path(os.path.realpath(str(entry["sessionFile"])))
    if not str(source).startswith(state + os.sep) or not re.fullmatch(r"[A-Za-z0-9_.-]{4,96}", sid):
        raise ValueError("sessionFile fuera del estado de OpenClaw")
    if not source.is_file():
        return {"capture_state": "missing", "session_id": sid}
    if source.stat().st_mtime < started - 1:
        return {"capture_state": "stale", "session_id": sid}
    dest_dir = (Path(_paths.state_dir(str(Path.home()))) / "transcripts-backup"
                / Path(session_paths.session_dir(brain)).name)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / ("openclaw-%s.jsonl" % sid)
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=str(dest_dir))
    os.close(fd)
    try:
        before = (source.stat().st_size, source.stat().st_mtime_ns)
        shutil.copyfile(source, tmp)
        if (source.stat().st_size, source.stat().st_mtime_ns) != before:
            raise OSError("El transcript de OpenClaw cambió durante la copia")
        doc = nt.parse_openclaw(tmp)
        if nt.validate(doc) or not doc["turns"]:
            return {"capture_state": "missing", "session_id": sid,
                    "capture_error": "sin diálogo visible"}
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"capture_state": "captured", "captured_at": now(), "session_id": sid,
            "backup": str(target), "native_format": "openclaw-jsonl",
            "transcript_backup": str(target), "dialogue_turns": len(doc["turns"])}


def capture_hermes(brain, started, session_id="", exe=None, runner=None):
    """Transcript de ESTA sesión de Hermes vía el export OFICIAL (`hermes
    sessions export --format jsonl`, v0.18.2 VERIFICADO), guardado como
    `hermes-<id>.jsonl` junto a los demás respaldos y legible por
    neutral_transcript.parse_hermes. `session_id` = la sesión de la pestaña
    (env WORKSPACE_HERMES_SESSION); sin ella, la sesión NUEVA inequívoca de
    este cerebro desde `started` (nunca la de otra pestaña). Si Hermes rotó el
    id al compactar, se respalda la cadena completa. `exe`/`runner`: knobs de
    test. La corrida (env WORKSPACE_HERMES_RUN) distingue las sesiones de esta
    pestaña de las de otra abierta en el mismo cerebro. El respaldo incluye
    los ANCESTROS ya compactados (`parent_session_id`): reemplazarlo solo con
    la hija borraría lo que el respaldo anterior sí tenía."""
    import session_paths
    import neutral_transcript as nt
    from engines import hermes as _h
    known = str(session_id or os.environ.get("WORKSPACE_HERMES_SESSION") or "").strip()
    if known and not _h._valid_sid(known):
        return {"capture_state": "missing"}
    chain, state = _h.session_chain(brain, started, known=known, exe=exe, runner=runner,
                                    run=os.environ.get("WORKSPACE_HERMES_RUN", ""))
    if not chain or state not in ("resolved", "stale"):
        return {"capture_state": state}
    sid = str(chain[-1]["id"])
    if state == "stale":
        return {"capture_state": "stale", "session_id": sid}
    chain = _h.ancestors(chain[0], brain, exe=exe, runner=runner) + chain
    dest_dir = (Path(_paths.state_dir(str(Path.home()))) / "transcripts-backup"
                / Path(session_paths.session_dir(brain)).name)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / ("hermes-%s.jsonl" % sid)
    header = {"type": nt.HERMES_HEADER, "id": sid, "chain": [str(d["id"]) for d in chain],
              "title": chain[-1].get("title") or "", "cwd": chain[0].get("cwd") or str(brain),
              "source": chain[-1].get("source") or "",
              "started_at": chain[0].get("started_at"), "ended_at": chain[-1].get("ended_at")}
    fd, tmp = tempfile.mkstemp(prefix=target.name + ".", dir=str(dest_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(header, ensure_ascii=False) + "\n")
            for d in chain:
                for m in d.get("messages") or []:
                    if isinstance(m, dict):
                        fh.write(json.dumps({"type": nt.HERMES_MESSAGE, "session": d["id"],
                                             "message": m}, ensure_ascii=False) + "\n")
        doc = nt.parse_hermes(tmp)
        if nt.validate(doc) or not doc["turns"]:
            return {"capture_state": "missing", "session_id": sid,
                    "capture_error": "sin diálogo visible"}
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"capture_state": "captured", "captured_at": now(), "session_id": sid,
            "backup": str(target), "native_format": "hermes-export-jsonl",
            "transcript_backup": str(target), "dialogue_turns": len(doc["turns"])}


def close_payload(brain, engine, started, payload, run_id):
    result = dict(payload, source="exit", run_id=run_id, started=started)
    tab = os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS") or ""
    result["tab"] = tab
    import settings
    if os.environ.get("WORKSPACE_NO_TRANSCRIPT_BACKUP") or not settings.enabled("hooks.transcript_backup", default=True):
        result["capture_state"] = "disabled"
    elif engine == "codex":
        result.update(resolve_codex(brain, started))
    elif engine == "opencode":
        import subprocess
        try:
            result.update(capture_opencode(brain, started))
        except (OSError, ValueError, TimeoutError, subprocess.SubprocessError) as exc:
            result.update(capture_state="failed", capture_error=type(exc).__name__)
            print("WORKSPACE: respaldo opencode falló (%s); consulta workspace memoria status" % type(exc).__name__, file=__import__("sys").stderr)
        # Mismo contrato que Antigravity para los listeners de session_end
        # (revisión de skills): `transcript_path` = la copia legible.
        if result.get("transcript_backup"):
            result["transcript_path"] = result["transcript_backup"]
    elif engine == "openclaw":
        import subprocess
        try:
            result.update(capture_openclaw(brain, started))
        except (OSError, ValueError, TimeoutError, subprocess.SubprocessError) as exc:
            result.update(capture_state="failed", capture_error=type(exc).__name__)
            print("WORKSPACE: respaldo OpenClaw falló (%s); consulta workspace memoria status" % type(exc).__name__, file=__import__("sys").stderr)
        if result.get("transcript_backup"):
            result["transcript_path"] = result["transcript_backup"]
    elif engine == "hermes":
        import subprocess
        try:
            result.update(capture_hermes(brain, started))
        except (OSError, ValueError, TimeoutError, subprocess.SubprocessError) as exc:
            result.update(capture_state="failed", capture_error=type(exc).__name__)
            print("WORKSPACE: respaldo Hermes falló (%s); consulta workspace memoria status" % type(exc).__name__, file=__import__("sys").stderr)
        if result.get("transcript_backup"):
            result["transcript_path"] = result["transcript_backup"]
    elif engine == "antigravity":
        try:
            result.update(capture_antigravity(brain, started))
        except (OSError, ValueError, TimeoutError, sqlite3.Error) as exc:
            result.update(capture_state="failed", capture_error=type(exc).__name__)
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
           capture_state=result["capture_state"], **{k: result[k] for k in
               ("backup", "captured_at", "native_format", "capture_error", "transcript_backup", "transcript_error", "dialogue_turns") if k in result})
    return result


def captured(brain, payload, backup):
    if not brain:
        return
    sid = str(payload.get("session_id") or Path(backup).stem)
    rid = payload.get("run_id") or sid
    st = os.stat(backup)
    signature = "%s:%s" % (st.st_size, st.st_mtime_ns)
    record(brain, rid, signature=signature,
           session_id=sid, engine=payload.get("engine", "claude-code"),
           tab=payload.get("tab") or os.environ.get("WORKSPACE_WS", ""),
           capture_state="captured", captured_at=now(), backup=backup)


def _parser():
    """El parser de `workspace memoria checkpoint|context|status` (los que
    delega memoria.py). Aparte de main para que su ayuda se pueda imprimir
    sin correr nada."""
    p = argparse.ArgumentParser(prog="workspace memoria")
    p.add_argument("command", choices=("checkpoint", "context", "status"))
    p.add_argument("--brain", default=os.getcwd())
    p.add_argument("--tab", default=os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS"))
    p.add_argument("--expected-revision", type=int)
    p.add_argument("--engine", default="")
    for k in FIELDS:
        p.add_argument("--" + k.replace("_", "-"), default="")
    return p


def main(argv=None):
    a = _parser().parse_args(argv)
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
