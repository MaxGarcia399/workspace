#!/usr/bin/env python3
"""WORKSPACE · pending_runs — la red de seguridad del cierre (Fase 1, 2026-10-16).

Por qué existe: en Windows, cerrar la ventana con la X mataba al envoltorio de
un motor (codex, antigravity, opencode, openclaw, hermes) sin correr su
`finally`: sin respaldo de la conversación, sin atarla a su pestaña (cuatro de
seis motores la atan al cerrar), con el bloque de la pestaña pegado en
AGENTS.md/GEMINI.md y now.json en «en sesión». En esta máquina había 28
corridas reales sin cierre contra 7 con recibo
(deliverables/workspace-motores/Panorama_Contexto_Sesiones_v1.md, hallazgos 1-2).

Cómo funciona (capa delgada, igual para todos los motores envueltos):
  1. begin(): ANTES de abrir el TUI se anota la corrida — el «separador
     provisional»: motor, cerebro, agente, pestaña, t0, el proceso del
     envoltorio (pid + hora de creación) y lo que cada motor necesita para atar
     la conversación después (el env de la pestaña y `extra` del adaptador).
  2. Cierre normal: closed() la marca cuando terminó la captura y done() la
     borra cuando el adaptador ya ató y limpió.
  3. Windows: interrupted() la corre el manejador de CTRL_CLOSE de
     interactive.py: marca la corrida, deja el recibo «interrupted», limpia el
     bloque de la pestaña y now.json (si no hay otra corrida viva en ese
     cerebro) y le da al cierre normal unos segundos (wait_done).
  4. reconcile(): al abrir un agente, cada corrida cuyo envoltorio ya no existe
     se cierra tarde — captura (recibo con `close_mode: reconciled`), atado
     inequívoco de la conversación a su pestaña, limpieza — y se borra.
     Idempotente, falla-suave y con tope de tiempo: lo que no alcance queda
     para la próxima. Nunca bloquea la apertura.

Workspace no reemplaza al motor: la conversación y su retomar siguen siendo
del motor. Esto solo asegura que el separador, la copia de respaldo y la
limpieza sobrevivan a la X. Cero dependencias (stdlib, 3.9+).
"""
import contextlib
import json
import os
import re
import sys
import threading
import time

SCHEMA = 1
_DIR = "pending-runs"
#: El env de la pestaña que el cierre tardío necesita (lo que el adaptador deja
#: en el entorno para la captura y el atado). Lista EXPLÍCITA: jamás una llave.
ENV_KEYS = ("WORKSPACE_WS", "WORKSPACE_WID", "WORKSPACE_AGENT_NAME",
            "WORKSPACE_OPENCODE_SESSION", "WORKSPACE_OPENCODE_FIND",
            "WORKSPACE_OPENCLAW_SESSION", "WORKSPACE_OPENCLAW_PROFILE",
            "WORKSPACE_HERMES_SESSION", "WORKSPACE_HERMES_RUN", "WORKSPACE_HERMES_PROFILE",
            "WORKSPACE_NO_TRANSCRIPT_BACKUP")
#: Corridas más viejas que esto (o con tantos intentos fallidos) se dan por
#: perdidas: recibo «interrupted» y fuera (no se reintenta para siempre).
MAX_AGE = 14 * 86400
MAX_ATTEMPTS = 3
#: Arranques recientes por cerebro y motor (ventana del atado tardío).
_STARTS_KEEP = 200
_RID = re.compile(r"[0-9a-f]{8,64}")

_CURRENT = {}
_DONE = threading.Event()


# ── almacenamiento ──────────────────────────────────────────────────────────
def _dir():
    import paths
    d = os.path.join(paths.state_dir(), _DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _path(run_id):
    if not _RID.fullmatch(str(run_id or "")):
        raise ValueError("run_id inválido")
    return os.path.join(_dir(), "%s.json" % run_id)


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) and d.get("schema") == SCHEMA else None
    except (OSError, ValueError):
        return None


def _write(path, data):
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def _update(run_id, fn):
    p = _path(run_id)
    rec = _read(p)
    if rec is None:
        return None
    fn(rec)
    _write(p, rec)
    return rec


def _proc_mark():
    try:
        import openclaw_gateway as G
        return G._mark()
    except Exception:
        return {"pid": os.getpid(), "ctime": None, "t0": time.time()}


def proc_alive(rec):
    """¿Sigue vivo el envoltorio de la corrida? Windows: OpenProcess + hora
    de creación (los pid se reciclan); jamás os.kill(pid, 0) ahí, que sería
    TerminateProcess. Sin poder saberlo → «vivo» por un rato (no se le roba
    la corrida a nadie)."""
    try:
        import openclaw_gateway as G
        return G._alive((rec or {}).get("proc"))
    except Exception:
        return True


def _norm(brain):
    return os.path.realpath(brain) if brain else ""


# ── 1. antes de abrir ───────────────────────────────────────────────────────
def begin(run_id, engine, brain, started, extra=None):
    """Anota la corrida ANTES de lanzar el TUI. Falla-suave: None si no se
    pudo (la corrida sigue igual, solo sin red de seguridad)."""
    try:
        extra = dict(extra or {})
        rec = {"schema": SCHEMA, "run_id": run_id, "engine": str(engine or ""),
               "brain": _norm(brain), "started": float(started), "state": "running",
               "proc": _proc_mark(),
               "tab": str(extra.pop("tab", None) or os.environ.get("WORKSPACE_WS") or ""),
               "agent": str(extra.pop("agent", None) or os.environ.get("WORKSPACE_AGENT_NAME") or ""),
               "env": {k: os.environ[k] for k in ENV_KEYS if os.environ.get(k)},
               "extra": extra, "attempts": 0}
        _write(_path(run_id), rec)
        _remember_start(rec)
        _CURRENT.clear()
        _CURRENT.update(run_id=run_id, engine=rec["engine"], brain=rec["brain"])
        _DONE.clear()
        return rec
    except Exception:
        return None


def _starts_path():
    return os.path.join(_dir(), "_starts.json")


def _remember_start(rec):
    try:
        from olock import file_lock
        p = _starts_path()
        with file_lock(p, timeout=2):
            try:
                with open(p, encoding="utf-8") as fh:
                    rows = json.load(fh)
            except (OSError, ValueError):
                rows = []
            rows = [r for r in rows if isinstance(r, dict)][-(_STARTS_KEEP - 1):]
            rows.append({"run_id": rec["run_id"], "engine": rec["engine"],
                         "brain": rec["brain"], "started": rec["started"]})
            _write(p, rows)
    except Exception:
        pass


def _next_start(rec, same_engine=True):
    """Hora del siguiente arranque en el MISMO cerebro (y motor) después de
    esta corrida, o None. Acota la ventana del atado tardío: lo creado
    después es de otra corrida."""
    try:
        with open(_starts_path(), encoding="utf-8") as fh:
            rows = json.load(fh)
    except (OSError, ValueError):
        return None
    later = [float(r.get("started") or 0) for r in rows if isinstance(r, dict)
             and r.get("brain") == rec.get("brain") and r.get("run_id") != rec.get("run_id")
             and (not same_engine or r.get("engine") == rec.get("engine"))
             and float(r.get("started") or 0) > float(rec.get("started") or 0)]
    return min(later) if later else None


def current():
    return _CURRENT.get("run_id") or ""


# ── 2. cierre normal ────────────────────────────────────────────────────────
def closed(run_id, result=None):
    """La captura y session_end ya corrieron (falta el atado del adaptador)."""
    res = result or {}

    def fn(rec):
        rec["state"] = "closed"
        rec["closed"] = {k: res.get(k) for k in ("capture_state", "session_id", "capture_error")
                         if res.get(k) is not None}
    try:
        _update(run_id, fn)
    except Exception:
        pass


#: Capturas que ya no se reintentan: hecha, o la conversación no cambió.
_CAPTURA_FINAL = ("captured", "stale", "skipped")


def done(run_id=None):
    """El adaptador terminó (atado + limpieza): la corrida ya no está
    pendiente. Despierta al manejador de la X si está esperando.
    Excepción (memoria v1, 2026-10-17): si llegó la X y la captura no
    alcanzó (opencode exporta en más de los ~4 s que da Windows), la corrida
    se queda como «interrupted» para que reconcile() la capture al reabrir —
    sin esa copia no hay maleta de la sesión. Lo mismo si en un cierre
    normal la captura falló (el export de OpenClaw venció o dio error): se
    reintenta al reabrir, con el mismo tope de intentos (segunda revisión
    de la candidata 0.5.1, N1)."""
    rid = run_id or current()
    try:
        if rid:
            rec = _read(_path(rid))
            st = ((rec or {}).get("closed") or {}).get("capture_state")
            cortada = bool(rec) and bool(rec.get("interrupted_at")) and st not in _CAPTURA_FINAL
            if cortada or (rec and st == "failed"):
                _update(rid, lambda r: r.update(state="interrupted"))
            else:
                os.remove(_path(rid))
    except (OSError, ValueError):
        pass
    _DONE.set()


def wait_done(timeout):
    return _DONE.wait(timeout)


# ── 3. la X (Windows) ───────────────────────────────────────────────────────
def interrupted(run_id, engine=None, brain=None):
    """Lo mínimo e inmediato cuando se cierra la consola (lo llama el
    manejador de CTRL_CLOSE): marca la corrida, deja el recibo «interrupted»
    y, si no hay otra corrida viva en el cerebro, quita el bloque de la
    pestaña y limpia now.json. Lo pesado (captura y atado) lo termina el
    cierre normal si alcanza, o reconcile() la próxima vez. Falla-suave."""
    rec = None
    try:
        def fn(r):
            r["state"] = "interrupted" if r.get("state") == "running" else r.get("state")
            r["interrupted_at"] = time.time()
        rec = _update(run_id, fn)
    except Exception:
        rec = None
    engine = (rec or {}).get("engine") or engine or ""
    brain = (rec or {}).get("brain") or _norm(brain)
    if not brain:
        return
    try:
        import session_continuity
        row = session_continuity.receipts(brain)["runs"].get(run_id) or {}
        if row.get("capture_state") in (None, "", "interrupted"):
            session_continuity.record(brain, run_id, engine=engine,
                                      tab=(rec or {}).get("tab", ""),
                                      capture_state="interrupted",
                                      interrupted_at=session_continuity.now())
    except Exception:
        pass
    if live_in_brain(brain, exclude=run_id):
        return
    clean_docs(engine, brain)
    try:
        import neutral_hooks
        neutral_hooks.clear_status(brain)
    except Exception:
        pass


# ── utilidades compartidas ──────────────────────────────────────────────────
def pending(brain=None):
    """Corridas pendientes (de un cerebro o de todos), más viejas primero."""
    out = []
    try:
        d = _dir()
        for name in os.listdir(d):
            if not name.endswith(".json") or name.startswith("_"):
                continue
            rec = _read(os.path.join(d, name))
            if rec and (brain is None or rec.get("brain") == _norm(brain)):
                out.append(rec)
    except OSError:
        pass
    return sorted(out, key=lambda r: float(r.get("started") or 0))


def live_in_brain(brain, exclude=None):
    """¿Hay OTRA corrida envuelta viva en este cerebro? Entonces el
    AGENTS.md/GEMINI.md y now.json son de ella: no se tocan."""
    for rec in pending(brain):
        if rec.get("run_id") != exclude and proc_alive(rec):
            return True
    return False


def clean_docs(engine, brain):
    """Quita SOLO el bloque marcado de la pestaña (WORKSPACE:SESSION) de los
    docs de proyecto del cerebro; el resto de cada archivo queda byte a byte.
    Lo demás del doc generado lo re-sincroniza el siguiente arranque. GEMINI.md
    generado vuelve además a su puntero en reposo (sin la ruta de esta máquina
    ni el contexto de arranque); el del socio, solo pierde lo anexado.
    Los DOS docs, sea cual sea el motor que cierra (`engine` queda por
    compatibilidad): quien llama es la última corrida viva del cerebro y el
    bloque pudo escribirlo OTRA ventana, de otro motor, que cerró antes con
    esta abierta; se quedaba huérfano con la pestaña de una ventana cerrada
    (revisión de la 0.5.1, P2-1). Idempotente y falla-suave."""
    hecho = False
    try:
        from engines import antigravity as agy
        hecho = bool(agy._restore_gemini(brain)) or hecho
    except Exception:
        pass
    try:
        from engines import codex
        hecho = bool(codex._strip_session_block(brain)) or hecho
    except Exception:
        pass
    return hecho


@contextlib.contextmanager
def _env(values):
    """El env de la pestaña de la corrida, solo mientras se cierra tarde."""
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    try:
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        for k, v in (values or {}).items():
            if k in ENV_KEYS and v:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── 4. el cierre tardío ─────────────────────────────────────────────────────
def reconcile(brain=None, budget=8.0, notify=None, engine=None):
    """Cierra tarde las corridas cuyo envoltorio murió sin terminar su cierre
    (la X, un crash, un apagón). `brain` = solo las de ese cerebro (None =
    todas); `engine` = solo las de ese motor (None = todos). → lista de
    resúmenes. Jamás levanta."""
    out = []
    t_end = time.monotonic() + max(0.0, float(budget))
    try:
        from olock import file_lock, LockTimeout
    except Exception:
        return out
    for rec in pending(brain):
        if time.monotonic() >= t_end:      # `>=`: con tope 0 no empieza ninguna (el
            break                          # reloj de Windows avanza a saltos de ~15 ms)
        if engine and rec.get("engine") != engine:
            continue
        if proc_alive(rec):
            continue
        p = _path(rec["run_id"])
        try:
            with file_lock(p, timeout=0.2):
                rec = _read(p)
                if rec is None or proc_alive(rec):
                    continue
                if notify:
                    try:
                        notify("WORKSPACE: cerrando una sesión anterior que quedó abierta "
                               "(%s · pestaña «%s»)…" % (rec.get("engine"), rec.get("tab") or "—"))
                    except Exception:
                        pass
                summary = _finish(rec)
                out.append(summary)
                # Una captura que falló NO se olvida: queda para el próximo
                # arranque hasta MAX_ATTEMPTS o MAX_AGE (Greptile, 2026-10-17:
                # un error pasajero de export borraba para siempre con qué reintentar).
                fallo = summary.get("capture_state") in ("failed", "interrupted")
                intentos = int(rec.get("attempts") or 0) + 1
                viejo = time.time() - float(rec.get("started") or 0) > MAX_AGE
                if fallo and intentos < MAX_ATTEMPTS and not viejo:
                    rec.update(state="interrupted", attempts=intentos,
                               last_error=str(summary.get("capture_error") or "captura fallida")[:200])
                    _write(p, rec)
                    summary["reintento"] = intentos
                    continue
                if fallo:
                    rec["last_error"] = str(summary.get("capture_error") or "captura fallida")[:200]
                    _give_up(rec)
                try:
                    os.remove(p)
                except OSError:
                    pass
            try:
                os.remove(p + ".lock")    # el candado de una corrida ya cerrada
            except OSError:
                pass
        except LockTimeout:
            continue                      # otro proceso la está cerrando
        except Exception as exc:
            try:
                def fn(r):
                    r["attempts"] = int(r.get("attempts") or 0) + 1
                    r["last_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:200])
                r2 = _update(rec["run_id"], fn)
                if r2 and (r2["attempts"] >= MAX_ATTEMPTS
                           or time.time() - float(r2.get("started") or 0) > MAX_AGE):
                    _give_up(r2)
                    os.remove(p)
            except Exception:
                pass
    return out


def _give_up(rec):
    try:
        import session_continuity
        session_continuity.record(rec["brain"], rec["run_id"], engine=rec.get("engine", ""),
                                  tab=rec.get("tab", ""), capture_state="interrupted",
                                  capture_error=(rec.get("last_error") or "")[:200],
                                  close_mode="abandoned")
    except Exception:
        pass


def _finish(rec):
    """El cierre que la corrida no alcanzó a hacer, en el mismo orden que el
    normal: captura + session_end, atado, limpieza."""
    import session_continuity
    brain, engine, run_id = rec["brain"], rec["engine"], rec["run_id"]
    started = float(rec.get("started") or 0)
    summary = {"run_id": run_id, "engine": engine, "brain": brain, "tab": rec.get("tab", "")}
    if not brain or not os.path.isdir(brain):
        summary["skipped"] = "el cerebro ya no existe"
        return summary
    others = live_in_brain(brain, exclude=run_id)
    with _env(rec.get("env")):
        if rec.get("state") in ("running", "interrupted"):
            payload = {"source": "startup", "engine": engine, "session_id": run_id, "cwd": brain}
            try:
                res = session_continuity.close_payload(brain, engine, started, payload, run_id)
            except Exception as exc:
                res = dict(payload, source="exit", run_id=run_id, capture_state="interrupted",
                           capture_error=type(exc).__name__)
                session_continuity.record(brain, run_id, engine=engine, tab=rec.get("tab", ""),
                                          capture_state="interrupted",
                                          capture_error=type(exc).__name__)
            session_continuity.record(brain, run_id, close_mode="reconciled",
                                      recovered_at=session_continuity.now())
            try:
                import neutral_hooks
                beh = ("listeners",) if others else ("listeners", "status")
                neutral_hooks.on_session_end(res, brain=brain, behaviors=beh)
            except Exception:
                pass
        else:
            res = dict(rec.get("closed") or {})
        summary["capture_state"] = res.get("capture_state", "")
        if res.get("capture_error"):
            summary["capture_error"] = res.get("capture_error")
        try:
            summary["bound"] = late_bind(rec, res)
        except Exception as exc:
            summary["bound"] = ""
            summary["bind_error"] = type(exc).__name__
    if not others:
        summary["doc_cleaned"] = clean_docs(engine, brain)
        if rec.get("state") == "closed":
            try:
                import neutral_hooks
                neutral_hooks.clear_status(brain)
            except Exception:
                pass
    return summary


def openclaw_never_created(res):
    """¿La clave atada de OpenClaw nunca tuvo sesión? (se abrió y se cerró sin
    turnos: «Session not found»). Entonces la pestaña debe abrir como nueva y
    mandar su mensaje de arranque (hallazgo 16)."""
    return (str((res or {}).get("capture_state") or "") == "missing"
            and "not found" in str((res or {}).get("capture_error") or "").lower())


def late_bind(rec, res):
    """Ata la conversación a su pestaña SOLO si es inequívoca (nunca la de otra
    pestaña). → el id atado ('' si no). OpenClaw ya ató antes de abrir: aquí
    solo suelta una clave que nunca llegó a existir."""
    import sessions_registry as reg
    brain, engine = rec["brain"], rec["engine"]
    tab, agent = rec.get("tab") or "", rec.get("agent") or ""
    x = rec.get("extra") or {}
    env = rec.get("env") or {}
    started = float(rec.get("started") or 0)
    if not tab or not agent or x.get("no_bind"):
        return ""
    known = str(x.get("resume_id") or "")
    sid = ""
    if engine == "codex":
        if known:
            return ""
        from engines import codex
        end = rec.get("interrupted_at") or _next_start(rec)
        # la que prueba ser de OTRA pestaña (su contexto inyectado) tampoco
        sid = codex._vendor_session_after(brain, started, t1=end, tab=tab,
                                          by_signal=True)
        if sid and reg.owner(brain, "codex", sid, exclude=tab):
            sid = ""
    elif engine == "antigravity":
        # su caché es «la última conversación POR CARPETA»: si después corrió
        # otra pestaña de agy en este cerebro, ya no se sabe de quién es.
        if _next_start(rec):
            return ""
        from engines import antigravity as agy
        cid = agy._vendor_conversation_for(brain)
        if cid and cid != x.get("before_cid") and cid != known \
                and not reg.owner(brain, "antigravity", cid, exclude=tab):
            sid = cid
    elif engine == "opencode":
        if not env.get("WORKSPACE_OPENCODE_FIND"):
            return ""
        from engines import opencode as oc
        sid = str((res or {}).get("session_id") or "")
        if not oc._valid_session_id(sid):
            import shutil
            exe = shutil.which("opencode")
            sid = oc.find_new_session(exe, json.loads(env["WORKSPACE_OPENCODE_FIND"]),
                                      cwd=brain) if exe else ""
        if not oc._valid_session_id(sid) or reg.owner(brain, "opencode", sid, exclude=tab):
            sid = ""
    elif engine == "hermes":
        from engines import hermes as hm
        run = env.get("WORKSPACE_HERMES_RUN", "")
        try:
            if not x.get("user_picked"):
                chain, state = hm.session_chain(brain, started, known=known, run=run)
                cand = chain[-1]["id"] if chain and state in ("resolved", "stale") else ""
                if cand and cand != known and not hm._bound_elsewhere(brain, tab, cand):
                    sid = cand
        finally:
            hm.run_close(run)
    elif engine == "openclaw":
        key = env.get("WORKSPACE_OPENCLAW_SESSION", "")
        if key and openclaw_never_created(res):
            reg.unbind(brain, agent, tab, "openclaw", key)
        return ""
    if sid and sid != known:
        reg.bind(brain, agent, tab, engine, sid)
        return sid
    return ""


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="pending_runs",
                                 description="Corridas de motores que quedaron sin cerrar")
    ap.add_argument("accion", choices=("lista", "reconcilia"))
    ap.add_argument("--cerebro", default=None)
    ap.add_argument("--tope", type=float, default=30.0)
    a = ap.parse_args(argv)
    if a.accion == "lista":
        for r in pending(a.cerebro):
            print("%s  %-11s %-8s %s · «%s»" % (
                time.strftime("%Y-%m-%d %H:%M", time.localtime(float(r.get("started") or 0))),
                r.get("engine"), "viva" if proc_alive(r) else r.get("state"),
                os.path.basename(r.get("brain") or ""), r.get("tab") or "—"))
        return 0
    for s in reconcile(a.cerebro, budget=a.tope, notify=print):
        print(json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
