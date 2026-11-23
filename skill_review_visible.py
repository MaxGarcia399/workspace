"""Visible skill review batches. Models always inherit a visible terminal.

The queue and proof belong to hooks/skill_review.py. This module schedules,
shows observed states and keeps recoverable snapshots; it never awards proof.
"""
import base64
import contextlib
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid

import paths
import olock
import pending_runs
import arbol_procesos
import motor_guardia

ROOT = Path(__file__).resolve().parent
START_GRACE_S = 120  # cinco llamadas herdr de hasta 10 s + arranque del controlador


def review():
    hooks = str(ROOT / "hooks")
    if hooks not in sys.path:
        sys.path.append(hooks)
    import skill_review
    return skill_review


def t(key, **kw):
    import i18n
    return i18n.t("skill_review." + key, **kw)


def home():
    return Path(paths.state_dir()) / "skill-review-batches"


def folder(bid):
    if not re.fullmatch(r"[a-f0-9]{12}", str(bid)):
        raise ValueError("invalid batch id")
    return home() / bid


def read(bid):
    value, status = review()._leer_json(str(folder(bid) / "batch.json"))
    return value if status == "ok" else {}


def update(bid, **changes):
    p = folder(bid) / "batch.json"
    with olock.file_lock(str(p), timeout=2):
        value, status = review()._leer_json(str(p))
        if status == "error_lectura":
            review()._log({"evento": "tanda_sin_lectura", "lote": bid})
            raise OSError("batch sin lectura")
        if status == "ilegible":
            _apartar_tanda(p, bid)
            raise OSError("batch ilegible")
        if status != "ok" or not isinstance(value, dict):
            value = {}
        value.update(changes)
        review()._write_json(str(p), value)
    return value


def _apartar_tanda(path, bid):
    """Ilegible no es vacío: el batch dañado se aparta y no se reescribe."""
    dest = path.with_name("batch.ilegible-%s-%s.json" % (
        time.strftime("%Y%m%d-%H%M%S", time.gmtime()), uuid.uuid4().hex[:8]))
    try:
        os.replace(path, dest)
    except OSError:
        pass
    try:
        review()._log({"evento": "tanda_ilegible", "lote": bid})
    except Exception:
        pass


def env():
    import secret_store
    return secret_store.engine_env()


def agents():
    import agentsreg
    return agentsreg.agents()


def estimate(plan):
    return t("estimate", n=plan["total"], tokens=plan["tokens"],
             batch=len(plan["revisiones"]), remaining=plan["restantes"])


def _viva(state):
    """¿Esta tanda tiene un controlador vivo (o está en su arranque)? Una
    muerta se recupera: no reserva nada."""
    if state.get("status") not in ("reserved", "running", "stopping"):
        return False
    if time.time() - state.get("t", 0) < START_GRACE_S:
        return True
    owner = state.get("proc") or {"pid": state.get("pid"), "t0": state.get("t"), "ctime": None}
    return bool(pending_runs.proc_alive({"proc": owner}))


def reservados(brain, clave):
    """Los ids de pendientes de (`brain`, `clave`) que una tanda VIVA de esta
    máquina ya reservó: un cierre no los reagrupa ni los borra (Greptile 0.9.2,
    confirmación #2). Sin tanda, o si no se puede leer: vacío."""
    try:
        active, status = review()._leer_json(str(home() / "active.json"))
        bid = active.get("id", "") if status == "ok" else ""
        if not re.fullmatch(r"[a-f0-9]{12}", str(bid)):
            return set()
        state = read(bid)
        if not _viva(state):
            return set()
        real = os.path.normcase(os.path.realpath(brain))
        out = set()
        for g in (state.get("plan") or {}).get("revisiones") or ():
            if (g.get("clave") == clave
                    and os.path.normcase(os.path.realpath(str(g.get("brain") or ""))) == real):
                out.update(str(i) for i in g.get("ids") or ())
        return out
    except Exception:
        return set()


def reserve(plan):
    """One queue per machine, including the gap before its controller starts."""
    pointer = home() / "active.json"
    with olock.file_lock(str(pointer), timeout=2):
        active, status = review()._leer_json(str(pointer))
        if status in ("error_lectura", "ilegible"):
            return ""
        if status == "ok":
            old_id = active.get("id", "")
            old = read(old_id) if re.fullmatch(r"[a-f0-9]{12}", str(old_id)) else {}
            if _viva(old):
                return ""                      # never overlap a live controller
        if not plan["revisiones"]:
            return ""
        bid = uuid.uuid4().hex[:12]
        update(bid, id=bid, plan=plan, status="reserved", t=time.time(), results=[],
               pid=os.getpid(), proc=pending_runs._proc_mark())
        review()._write_json(str(pointer), {"id": bid})
        return bid


def _herdr(args):
    proc = subprocess.run(["herdr"] + args, env=env(), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=10)
    if proc.returncode:
        raise RuntimeError("herdr failed")
    if not proc.stdout.strip():
        return {}  # pane run comunica el éxito solo con su exit code
    data = json.loads(proc.stdout)
    return data.get("result", data)


def pane_command(args, windows=None):
    windows = os.name == "nt" if windows is None else windows
    if windows:
        script = "& " + " ".join("'" + str(a).replace("'", "''") + "'" for a in args)
        payload = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return "powershell -NoProfile -EncodedCommand " + payload
    return shlex.join([str(a) for a in args])


def open_tab(bid):
    """Only herdr public CLI; no focus command, no existing pane writes."""
    created = _herdr(["tab", "create", "--cwd", str(ROOT), "--label", t("title"), "--no-focus", "--env", "WORKSPACE_NO_GREETER=1"])
    tab = created.get("tab", created)
    tabid = tab.get("tab_id")
    pane = tab.get("pane_id")
    if not pane and tabid:
        detail = _herdr(["pane", "list", "--workspace", tab.get("workspace_id") or tabid.split(":")[0]])
        panes = [p for p in detail.get("panes", []) if p.get("tab_id") == tabid]
        if len(panes) == 1:
            pane = panes[0].get("pane_id")
    if not tabid or not pane:
        raise RuntimeError("herdr did not return tab/pane ids")
    split = _herdr(["pane", "split", pane, "--direction", "right", "--ratio", "0.40",
                    "--no-focus", "--cwd", str(ROOT), "--env", "WORKSPACE_NO_GREETER=1"])
    right = split.get("pane", split).get("pane_id")
    if not right:
        raise RuntimeError("herdr did not return the review pane")
    update(bid, tab=tabid)
    command = [sys.executable, str(ROOT / "skill_review_visible.py")]
    _herdr(["pane", "run", right, pane_command(command + ["panel", bid])])
    _herdr(["pane", "run", pane, pane_command(command + ["run", bid])])


def _consola_real():
    """¿stdin y stdout son una consola de verdad? `isatty()` no basta en Windows: NUL es un
    dispositivo de caracteres (isatty True) y un `input()` o una pantalla ahí no tiene quién
    la conteste. _console es la regla compartida de Workspace."""
    try:
        import _console
        return _console.interactive()
    except Exception:
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            return False


def launch(agentes=None, automatic=False, modos=None, clave=None):
    if modos is None:
        modos = ("on_close",) if automatic else ("on_close", "button")
    plan = review().plan_tanda(agents() if agentes is None else agentes, modos=modos, clave=clave)
    print(estimate(plan))
    if not plan["revisiones"]:
        return False
    import multiplexer
    has_tabs = multiplexer.inside_herdr() and shutil.which("herdr")
    if not has_tabs and not _consola_real():
        return False  # no model without a visible terminal
    bid = reserve(plan)
    if not bid:
        print(t("busy"))
        return False
    update(bid, automatic=automatic)
    try:
        if has_tabs:
            open_tab(bid)
        else:
            print(t("same_window"))
            if input(t("confirm")).strip().lower() in ("d", "q"):
                update(bid, status="deferred")
                return False
            run(bid)
    except Exception:
        update(bid, status="failed")
        review()._aviso_cola(plan["revisiones"][0]["brain"], "lanzamiento_fallido")
        return False
    return True


def stop(bid):
    # Independent flag: a worker progress update can never erase a stop.
    review()._escribir(str(folder(bid) / "stop"), "stop")


def stopped(bid):
    return (folder(bid) / "stop").exists()


def prompt_args(engine, prompt):
    # Interactive paths only. No --print, exec, --oneshot, -Q or permission bypass.
    return {
        "claude-code": [prompt], "codex": [prompt], "kiro": [prompt],
        "cursor": ["--", prompt], "opencode": ["--prompt", prompt],
        "antigravity": ["--prompt-interactive", prompt], "copilot": ["-i", prompt],
        "hermes": ["chat", "-q", prompt], "openclaw": ["--message", prompt],
    }[engine]


def snapshot(brain, dest=None):
    """Only regular files inside skills; never follow user symlinks."""
    root = Path(brain) / "skills"
    files = {}
    if not root.is_dir() or root.is_symlink():
        return files
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [n for n in dirs if not (Path(base) / n).is_symlink()]
        for name in names:
            path = Path(base) / name
            if path.is_symlink() or not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()   # same key on every OS
            data = path.read_bytes()
            files[rel] = hashlib.sha256(data).hexdigest()
            if dest is not None:
                copy = Path(dest) / rel
                copy.parent.mkdir(parents=True, exist_ok=True)
                copy.write_bytes(data)
    return files


def changes(before, after):
    return [p for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)]


def receiver_hashes(state, turnos, written):
    """Postimages from the receiver's operations, never the final directory scan.

    An unsupported operation is deliberately not undoable. Full writes carry
    their bytes; replacements are replayed against the saved preimage and
    must be unambiguous. A concurrent edit makes the resulting hash differ.
    """
    brain = (state.get("group") or {}).get("brain")
    saved = folder(state["id"]) / str(state.get("index", 0)) / "before"
    out = {}
    full_writes = {"write", "write_file", "create_file", "write_to_file"}
    replacements = {"edit", "edit_file", "multiedit", "replace_string_in_file", "replace_in_file"}
    for rel in written:
        path = Path(brain) / "skills" / rel
        before = saved / rel
        data = before.read_bytes() if before.is_file() else None
        known = False
        for turn in turnos:
            for call in turn.get("tool_calls") or ():
                if not review()._la_escribio([dict(turn, tool_calls=[call])], str(path)):
                    continue
                name = str(call.get("name") or "").rsplit(".", 1)[-1].lower()
                inp = call.get("input") or {}
                if name in full_writes and isinstance(inp.get("content"), str):
                    data, known = inp["content"].encode("utf-8"), True
                elif name in replacements and data is not None:
                    edits = inp.get("edits") if name == "multiedit" else [inp]
                    known = isinstance(edits, list) and bool(edits)
                    for edit in edits or ():
                        old, new = edit.get("old_string"), edit.get("new_string")
                        if not isinstance(old, str) or not old or not isinstance(new, str):
                            known = False
                            break
                        old, new = old.encode("utf-8"), new.encode("utf-8")
                        count = data.count(old)
                        if not count or (count != 1 and not edit.get("replace_all")):
                            known = False
                            break
                        data = data.replace(old, new, -1 if edit.get("replace_all") else 1)
                    if not known:
                        data = None
                else:
                    data, known = None, False
        if known and data is not None:
            out[rel] = hashlib.sha256(data).hexdigest()
    return out


def proved(bid, result, turnos=()):
    """Called ONLY by the existing proof after examining the receiver transcript."""
    if not bid:
        return
    state = read(bid)
    results = list(state.get("results") or [])
    brain = (state.get("group") or {}).get("brain")
    written = []
    if brain:
        skills = Path(brain) / "skills"
        candidates = set((state.get("before") or {}).keys())
        if skills.is_dir():
            candidates.update(p.relative_to(skills).as_posix() for p in skills.rglob("*") if p.is_file())
        written = [p for p in candidates if review()._la_escribio(turnos, str(skills / p))]
    postimages = receiver_hashes(state, turnos, written) if result.get("resultado") in (
        "skill_creada", "skill_mejorada") else {}
    result = dict(result, written=written, receiver_after=postimages)
    results.append(result)
    update(bid, results=results)


def group_outcomes(results, group, index):
    """Results of one batch item. Same tab can hold a retry and a new session;
    clave+brain is not enough. An index, once any result has one, wins."""
    rows = [x for x in results or () if isinstance(x, dict)]
    if any("indice" in x for x in rows):
        return [x for x in rows if x.get("indice") == index]
    return [x for x in rows if x.get("clave") == (group or {}).get("clave")
            and x.get("brain") == (group or {}).get("brain")]


def requeue(brain, key, bid):
    r = review()
    def restore():
        path = r._delivered_path(brain, key)
        rec, status = r._leer_json(path)
        if status != "ok" or rec.get("tanda") != bid:
            return
        rec = {k: v for k, v in rec.items() if k not in (
            "entregada_t", "via", "sesion_receptora", "motor_receptor", "wid_receptor",
            "clave", "reporte", "tanda")}
        rec["id"] = uuid.uuid4().hex[:12]
        r._write_json(r._pending_path(brain, key, rec["id"]), rec)
        os.remove(path)
    r._bajo_candado(brain, 5, restore)


def close_child(proc, windows=None):
    windows = os.name == "nt" if windows is None else windows
    if windows:
        proc.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        proc.terminate()


def child_fingerprint(proc):
    pid = getattr(proc, "pid", None)
    return motor_guardia.huella(pid) if isinstance(pid, int) and pid > 1 else None


def force_close_child(proc, fingerprint=None):
    # POSIX guard: fingerprints descendants and excludes shared daemons in
    # other groups. Windows helper: taskkill /T /F before killing the launcher.
    if os.name != "nt" and fingerprint:
        motor_guardia.detener(fingerprint, gracia=0)
    arbol_procesos.matar_arbol(proc)
    proc.wait(timeout=arbol_procesos.ESPERA_TRAS_MATAR)


def stop_and_wait(proc, fingerprint=None):
    close_child(proc)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        force_close_child(proc, fingerprint)


def refill(bid, completed):
    """Pick up closes arriving during automatic work, within the same cap.

    The launcher uses this pointer lock too: it can either observe a live
    batch or start a new one after this final queue check, never lose a close
    in the gap between the check and marking the controller finished.
    """
    with olock.file_lock(str(home() / "active.json"), timeout=2):
        state = read(bid)
        if not state.get("automatic") or stopped(bid):
            return False
        plan = state["plan"]
        scheduled = list(plan["revisiones"])
        known = {(g["brain"], g["clave"]) for g in scheduled}
        fresh = review().plan_tanda(agents(), modos=("on_close",), excluir=known)
        added = fresh["revisiones"][:max(0, review().TANDA_MAX - len(scheduled))]
        plan = dict(plan, revisiones=scheduled + added,
                    total=len(scheduled) + fresh["total"],
                    tokens=sum(g["tokens"] for g in scheduled) + fresh["tokens"],
                    restantes=max(0, fresh["total"] - len(added)))
        done = completed >= len(plan["revisiones"])
        update(bid, plan=plan, status="finished" if done else "running")
        return done


def run(bid):
    state = read(bid)
    update(bid, status="running", pid=os.getpid(), proc=pending_runs._proc_mark())
    try:
        for i in range(review().TANDA_MAX):
            current = read(bid)
            if stopped(bid) or i >= len(current["plan"]["revisiones"]):
                break
            group = current["plan"]["revisiones"][i]
            live = {rec.get("id") for _, key, rec in review()._pendientes(group["brain"])
                    if key == group["clave"]}
            if not live.intersection(group["ids"]):
                # consumed, changed or unreadable since the estimate: no tokens
                # spent, and it is SAID (the controller never waits blind)
                omitidas = list(read(bid).get("omitidas") or [])
                omitidas.append({"indice": i, "clave": group["clave"], "brain": group["brain"]})
                update(bid, omitidas=omitidas)
                print(t("skipped", n=1), flush=True)
                try:
                    review()._log({"evento": "tanda_grupo_omitido", "lote": bid, "indice": i})
                except Exception:
                    pass
                continue
            update(bid, index=i, group=group, stage="starting")
            print("\n".join(panel_lines(read(bid))), flush=True)
            before = snapshot(group["brain"], folder(bid) / str(i) / "before")
            update(bid, before=before)
            child_env = env()
            child_env.update(WORKSPACE_REVIEW_BATCH=bid,
                WORKSPACE_REVIEW_SOURCE_KEY=group["clave"],
                WORKSPACE_REVIEW_IDS=",".join(group["ids"]),
                WORKSPACE_REVIEW_INDEX=str(i))
            message = t("task")
            cmd = [sys.executable, str(ROOT / "dispatch.py"), group["agente"],
                   "--engine", group["motor"], "--open", str(uuid.uuid4()),
                   "--name", t("title")] + prompt_args(group["motor"], message)
            # No capture: the user sees the real motor and its normal approvals.
            proc = subprocess.Popen(cmd, env=child_env, cwd=group["brain"],
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0)
            fingerprint = child_fingerprint(proc)
            terminating = False
            stopping_since = None
            while proc.poll() is None:
                receipt, status = review()._leer_json(
                    review()._delivered_path(group["brain"], group["clave"]))
                report = status == "ok" and receipt.get("tanda") == bid and receipt.get("reporte")
                if not terminating and (stopped(bid) or report):
                    # Graceful close invokes the adapter's transcript capture.
                    # A report triggers cleanup; ONLY the close hook awards proof.
                    close_child(proc)
                    terminating = True
                    stopping_since = time.monotonic()
                if terminating and time.monotonic() - stopping_since >= 10:
                    update(bid, forced=True)
                    force_close_child(proc, fingerprint)
                update(bid, stage="reported" if report else "delivered" if status == "ok" else "starting")
                time.sleep(0.5)
            requeue(group["brain"], group["clave"], bid)
            after = snapshot(group["brain"], folder(bid) / str(i) / "after")
            outcomes = group_outcomes(read(bid).get("results", []), group, i)
            authored = {p for x in outcomes for p in x.get("written", [])}
            touched = [p for p in changes(before, after) if p in authored]
            receiver_after = {p: digest for x in outcomes for p, digest in x.get("receiver_after", {}).items()}
            update(bid, after=after, touched=touched, stage="finished")
            # Each item keeps its own snapshot even after the next item starts.
            review()._write_json(str(folder(bid) / str(i) / "result.json"),
                {"group": group, "before": before, "after": after,
                 "touched": touched, "receiver_after": receiver_after, "results": outcomes})
            if refill(bid, i + 1):
                break
        update(bid, status="stopped" if stopped(bid) else "finished")
        print("\n".join(panel_lines(read(bid))), flush=True)
        if state.get("tab"):
            _herdr(["tab", "close", state["tab"]])
    except BaseException:
        stop(bid)
        if "proc" in locals() and proc.poll() is None:
            try:
                stop_and_wait(proc, locals().get("fingerprint"))
            except subprocess.TimeoutExpired:
                update(bid, status="stopping", forced=True)
                raise
        if "group" in locals():
            requeue(group["brain"], group["clave"], bid)
        update(bid, status="failed")
        raise


def diff(bid, index):
    root = folder(bid) / str(index)
    rec = json.loads((root / "result.json").read_text(encoding="utf-8"))
    out = []
    for rel in rec["touched"]:
        def lines(side):
            p = root / side / rel
            return p.read_text(encoding="utf-8", errors="replace").splitlines(True) if p.exists() else []
        out.extend(difflib.unified_diff(lines("before"), lines("after"), rel + " (before)", rel + " (after)"))
    return "".join(out)


def view(bid, index):
    root = folder(bid) / str(index)
    if (root / "result.json").is_file():
        return diff(bid, index)
    state = read(bid)
    group = state.get("group") or {}
    if not group.get("brain") or index != state.get("index"):
        return ""
    skills = Path(group["brain"]) / "skills"
    after = snapshot(group["brain"])
    out = [t("unverified") + "\n"]
    for rel in changes(state.get("before") or {}, after):
        before_file = root / "before" / rel
        after_file = skills / rel
        old = before_file.read_text(encoding="utf-8", errors="replace").splitlines(True) if before_file.is_file() else []
        new = after_file.read_text(encoding="utf-8", errors="replace").splitlines(True) if after_file.is_file() and not after_file.is_symlink() else []
        out.extend(difflib.unified_diff(old, new, rel + " (before)", rel + " (current)"))
    return "".join(out)


def _componente_enlace(base, dest):
    """True if `dest` or any existing component from `base` down is a symlink.
    A missing tail is fine: it does not exist yet, so it cannot be a link."""
    base, dest = Path(base), Path(dest)
    try:
        parts = dest.relative_to(base).parts
    except ValueError:
        return True
    cur = base
    if cur.is_symlink():
        return True
    for part in parts:
        cur = cur / part
        if cur.is_symlink():
            return True
        if not cur.exists():
            return False
    return False


class _Choque(Exception):
    """Un destino de Deshacer apareció ocupado o inseguro a media operación."""


def _mover_sin_pisar(src, dest):
    """Mueve `src` a `dest` sin reemplazar nada: un enlace duro (falla si `dest`
    ya existe) y luego se quita el original; donde no hay enlaces duros, se
    comprueba que `dest` siga libre y se renombra (el candado del archivo cubre
    la carrera dentro de Workspace)."""
    try:
        os.link(src, dest)
    except FileExistsError:
        raise _Choque()
    except OSError:
        if os.path.lexists(dest):
            raise _Choque()
        os.rename(src, dest)
        return
    os.remove(src)


def _archivo_libre(dest, tomados=()):
    """`dest` si está libre; si no, `<nombre>-2`, `-3`… (nunca se pisa nada).
    None si no hay un nombre libre razonable."""
    if not os.path.lexists(dest) and dest not in tomados:
        return dest
    for n in range(2, 100):
        cand = dest.with_name("%s-%d%s" % (dest.stem, n, dest.suffix))
        if not os.path.lexists(cand) and cand not in tomados:
            return cand
    return None


def _volver(hechos):
    """Devuelve lo ya hecho por un Deshacer que no pudo terminar (en orden
    inverso): lo archivado vuelve a su lugar y lo restaurado a lo que había."""
    for accion, path, otro in reversed(hechos):
        try:
            if accion == "archivado":
                if not os.path.lexists(path):
                    os.rename(otro, path)
            elif accion == "restaurado" and otro is not None and os.path.lexists(otro):
                os.replace(otro, path)
        except OSError:
            pass


def undo_detail(bid, index):
    root = folder(bid) / str(index)
    rec = json.loads((root / "result.json").read_text(encoding="utf-8"))
    skills = Path(rec["group"]["brain"]) / "skills"
    if skills.is_symlink():
        return False, t("conflict")
    expected = rec.get("receiver_after") or {}
    targets = sorted(rec["touched"])
    if any(rel not in expected for rel in targets):
        return False, t("undo_unverified")
    try:
        with contextlib.ExitStack() as locks:
            for rel in targets:
                path = skills / rel
                if not path.resolve().is_relative_to(skills.resolve()) or path.is_symlink():
                    return False, t("conflict")
                locks.enter_context(olock.local_lock(str(path), timeout=5))
            # Hashes are read and compared only AFTER every shared file lock is held.
            for rel in targets:
                path = skills / rel
                if path.is_symlink() or not path.resolve().is_relative_to(skills.resolve()):
                    return False, t("conflict")
                current = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
                if current != expected[rel]:
                    return False, t("undo_changed", file=rel)
            # Plan COMPLETO antes de mover nada (no queda a medias): el destino de
            # cada archivo nuevo es `_archive/review-<tanda>/<grupo>/<ruta>` (dos
            # grupos de la misma tanda pueden traer la misma skill) y, si ya hay
            # algo ahí, un nombre libre: nunca se pisa una copia archivada.
            plan, tomados = [], set()
            for rel in targets:
                path = skills / rel
                original = root / "before" / rel
                if original.exists():
                    plan.append(("restaurar", path, original))
                elif path.exists():
                    archive = _archivo_libre(skills / "_archive" / ("review-" + bid) / str(index) / rel,
                                             tomados)
                    if archive is None or _componente_enlace(skills, archive):
                        return False, t("conflict")
                    tomados.add(archive)
                    plan.append(("archivar", path, archive))
            hechos = []
            try:
                for accion, path, otro in plan:
                    if accion == "restaurar":
                        path.parent.mkdir(parents=True, exist_ok=True)
                        previo = None
                        if path.exists():               # lo de ahora, por si hay que volver
                            previo = path.with_name(path.name + ".review-prev-" + uuid.uuid4().hex)
                            shutil.copy2(path, previo)
                        tmp = path.with_name(path.name + ".review-" + uuid.uuid4().hex)
                        try:
                            shutil.copy2(otro, tmp)
                            os.replace(tmp, path)
                        finally:
                            if tmp.exists():
                                tmp.unlink()
                        hechos.append(("restaurado", path, previo))
                    else:
                        otro.parent.mkdir(parents=True, exist_ok=True)
                        if _componente_enlace(skills, otro):
                            raise _Choque()
                        _mover_sin_pisar(path, otro)
                        hechos.append(("archivado", path, otro))
            except (_Choque, OSError):
                _volver(hechos)                          # lo ya hecho se devuelve: nada a medias
                return False, t("conflict")
            for accion, _path, previo in hechos:
                if accion == "restaurado" and previo is not None:
                    try:
                        os.remove(previo)
                    except OSError:
                        pass
    except olock.LockTimeout:
        return False, t("undo_busy")
    except OSError:
        return False, t("undo_failed")
    return True, t("undone")


def undo(bid, index):
    return undo_detail(bid, index)[0]


def panel_lines(state):
    group = state.get("group") or {}
    stage = state.get("stage", "starting")
    # Honest observed progress: a report is not a verified result.
    return ["▛▀ " + t("title"), estimate(state["plan"]) if state.get("plan") else "",
            group.get("pestana", ""),
            t("stage." + stage), t("pending", n=state.get("plan", {}).get("restantes", 0)),
            t("controls"), *([t("forced")] if state.get("forced") else []),
            *list(state.get("touched") or []),
            *[__import__("decision_visible").texto_resultado(x.get("resultado"), x.get("detalle") or x.get("skill"))
              for x in state.get("results", [])]]


#: Quién habla en el panel: Workspace, con su monito (la piel del hub).
_WS = {"id": "", "n": "Workspace", "c": "#b9a7e6", "f": "bolita"}


def panel_tarjeta(state, cols=50, rows=24):
    """El panel de la revisión con la piel del hub (la tarjeta H-1 de hub_carga: su área, el monito y sus líneas), en
    lugar de la caja de las secciones de antes. → las filas en ANSI."""
    import hub_carga
    import hub_paleta as P
    lineas = [x for x in panel_lines(state)[1:] if x]
    T = hub_carga.tarjeta(max(30, int(cols)), _WS, [(t("title"), P.C["tx"], True)], lineas,
                          alto_max=max(10, int(rows)))
    return T.ansi(P._colores())


def panel(bid):
    viewing = False
    with contextlib.ExitStack() as stack:
        if os.name != "nt":
            import termios
            import tty
            old = termios.tcgetattr(sys.stdin)
            stack.callback(termios.tcsetattr, sys.stdin, termios.TCSADRAIN, old)
            tty.setcbreak(sys.stdin.fileno())
        while True:
            state = read(bid)
            cols, rows = shutil.get_terminal_size((50, 24))
            if state.get("group") and state.get("stage") != "finished":
                observed = changes(state.get("before") or {}, snapshot(state["group"]["brain"]))
                state = dict(state, touched=[t("unverified")] + observed if observed else [])
            rendered = panel_tarjeta(state, cols, rows)
            if not viewing:
                print("\033[2J\033[H" + "\n".join(rendered), flush=True)
            if os.name == "nt":
                import msvcrt
                key = msvcrt.getwch() if msvcrt.kbhit() else ""
                time.sleep(0.2)
            else:
                import select
                key = sys.stdin.read(1) if select.select([sys.stdin], [], [], 0.5)[0] else ""
            if viewing:
                if key:
                    viewing = False
                continue
            if key.lower() == "p":
                stop(bid)
            elif key.lower() in ("v", "u"):
                index = state.get("index", 0)
                try:
                    if key.lower() == "v":
                        print(view(bid, index) + "\n" + t("back_key"), flush=True)
                        viewing = True
                    else:
                        print(undo_detail(bid, index)[1], flush=True)
                        time.sleep(2)
                except (OSError, ValueError):
                    print(t("unverified"), flush=True)
            elif key.lower() == "q":
                return


def history():
    out = []
    if not home().is_dir():
        return out
    for item in home().glob("*/batch.json"):
        try:
            state = read(item.parent.name)
        except ValueError:
            continue
        if state.get("status") in ("finished", "stopped", "failed"):
            for result in item.parent.glob("*/result.json"):
                out.append((item.parent.name, int(result.parent.name)))
    return sorted(out, key=lambda x: (folder(x[0]) / str(x[1]) / "result.json").stat().st_mtime,
                  reverse=True)


def history_menu():
    while True:
        rows = history()
        print("▛▀ " + t("title"))
        for i, (bid, index) in enumerate(rows):
            item = json.loads((folder(bid) / str(index) / "result.json").read_text(encoding="utf-8"))
            group = item.get("group") or {}
            outcomes = item.get("results") or []
            label = " · ".join(__import__("decision_visible").texto_resultado(x.get("resultado"), x.get("detalle") or x.get("skill")) for x in outcomes)
            print(str(i + 1) + ". " + str(group.get("agente") or "") + " · "
                  + str(group.get("pestana") or "") + " · " + label)
        if not _consola_real():
            return
        # Stable displayed rows: a newer batch can never change the selected item.
        choice = input(t("history_controls")).strip().lower().split()
        if not choice or choice[0] == "q":
            return
        if choice[0] == "r":
            launch()
        elif len(choice) == 2 and choice[1].isdigit() and 0 < int(choice[1]) <= len(rows):
            bid, index = rows[int(choice[1]) - 1]
            if choice[0] == "v":
                print(diff(bid, index))
            elif choice[0] == "u":
                print(undo_detail(bid, index)[1])


def before_open(brain, agent, engine, preselect):
    if (not os.environ.get("WORKSPACE_REVIEW_BATCH") and preselect
            and review().review_mode(brain, engine) == "on_open"
            and review().review_engine(brain, engine) != engine):
        key = review().clave_pestana({"wid": preselect.get("wid"), "nombre": preselect.get("name")})
        launch([{"name": agent, "brain": brain}], modos=("on_open",), clave=key)


def wrap_terminal_close(brain, agent, engine, preselect, passthrough):
    """Keep a parent terminal for engines which replace dispatch with exec."""
    import multiplexer
    if (os.environ.get("WORKSPACE_REVIEW_BATCH") or os.environ.get("WORKSPACE_REVIEW_WRAPPER")
            or multiplexer.inside_herdr() or not _consola_real()
            or review().review_mode(brain, engine) != "on_close"):
        return False
    child_env = env()
    child_env["WORKSPACE_REVIEW_WRAPPER"] = "1"
    cmd = [sys.executable, str(ROOT / "dispatch.py"), agent, "--engine", engine]
    if preselect:
        cmd += ["--open", str(preselect.get("wid") or ""), "--name", str(preselect.get("name") or "")]
    cmd += list(passthrough or ())
    subprocess.call(cmd, env=child_env)
    launch(automatic=True)
    return True


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["ver"]:
        print(diff(args[1], int(args[2]) if len(args) > 2 else 0))
    elif args[:1] == ["deshacer"]:
        print(undo_detail(args[1], int(args[2]) if len(args) > 2 else 0)[1])
    elif args[:1] == ["run"]:
        run(args[1])
    elif args[:1] == ["panel"]:
        panel(args[1])
    elif args[:1] == ["stop"]:
        stop(args[1])
    else:
        launch()


if __name__ == "__main__":
    main()
