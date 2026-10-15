#!/usr/bin/env python3
"""WORKSPACE · actualizaciones_tui — la pantalla «Actualizaciones» del hub.

REDISEÑO 2026-10-14 (concepto Omarchy, pedido del dueño: «solo las opciones
que están disponibles»): una caja centrada y vertical (section_box) con tres
vistas:

  · MENÚ      — tu versión, si hay nueva, y SOLO lo que se puede hacer ahora:
                actualizar a vX (si hay versión nueva) · revisar y reparar ·
                solo revisar · volver a vX (si hay a cuál; pide Enter otra
                vez) · buscar de nuevo (si no se pudo verificar) · y el ajuste
                de automáticas (sí / solo avisar / no). Al abrir, un hilo de
                fondo consulta si hay versión nueva (sin bloquear nada). Lo
                didáctico (cómo llega una versión, la red de seguridad, qué
                cambia en tu máquina, los comandos equivalentes) va en `i`.
  · EN CURSO  — progreso + cada paso con su estado (· ● ✓ ⚠ ✗) + lo último
                que pasó. Nada de texto crudo de git/doctor volcado.
  · RESULTADO — veredicto, qué llegó y los pendientes con su acción sugerida
                (↑↓ para desplazar). Sin números de fase.

El motor NO cambió: las fases son las de `doctor.py` (devuelven hallazgos
estructurados — por eso se pueden pintar bonito), el harness se actualiza con
`updater` (la misma red de seguridad que `workspace update`) y volver a la
versión anterior es `updater.rollback` (= `workspace update --rollback`). El
runner corre en un hilo daemon con stdout/stderr/stdin capturados (nada
imprime sobre la pantalla); cancelar con q espera a que termine el paso en
curso (fail-soft: jamás deja la terminal rota ni el update a medias sin
avisar).

CONTRATO con front._doctor_submenu: run() devuelve None cuando todo se
atendió aquí (o el usuario volvió), y devuelve el token "check"|"repair"|
"update" SOLO cuando esta pantalla no puede correr el flujo (p. ej. no carga
el motor del doctor) → front cae al camino clásico de terminal. Sin TTY el
caller ni nos llama. Si el código cambió en disco (actualizar o volver), al
salir front reabre el hub con el código nuevo.

Teclas:  MENÚ ↑↓ · Enter · i · q (a y 1-3 siguen funcionando, sin anunciarse)
         EN CURSO q cancela al fin del paso · RESULTADO ↑↓ desplaza · Enter/q vuelve

Misma fórmula de pantalla que tono_tui (2J3JH al entrar, H + \\033[K por
línea después — nunca 2J a media sesión; el render SIEMPRE devuelve h-1
líneas, así cambiar de estado no deja residuos) y los dos drivers de
teclado: termios+select en Unix, msvcrt en Windows.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import io
import os
import re
import subprocess
import sys
import threading
import time
from theme import screen as _theme_screen  # fondo/tinta del tema

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import hublayout as HL                                          # noqa: E402
import i18n                                                      # noqa: E402
import section_box as SB                                         # noqa: E402

t = i18n.t

# (token, clave-etiqueta, clave-tag, claves-descripción, comando equivalente).
# Las etiquetas/tags/descripciones son CLAVES i18n — se resuelven con t() al
# pintar (así el hub flipea de idioma EN VIVO). El comando NO se traduce.
ACCIONES = (
    ("check", "actualizaciones.act.check.label", "actualizaciones.act.check.tag",
     ("actualizaciones.act.check.d1", "actualizaciones.act.check.d2",
      "actualizaciones.act.check.d3"),
     "workspace doctor --check"),
    ("repair", "actualizaciones.act.repair.label",
     "actualizaciones.act.repair.tag",
     ("actualizaciones.act.repair.d1", "actualizaciones.act.repair.d2",
      "actualizaciones.act.repair.d3"),
     "workspace doctor"),
    ("update", "actualizaciones.act.update.label",
     "actualizaciones.act.update.tag",
     ("actualizaciones.act.update.d1", "actualizaciones.act.update.d2",
      "actualizaciones.act.update.d3"),
     "workspace update"),
)

# tok → CLAVE i18n de la etiqueta (se resuelve con t() en el punto de uso).
_LBL = {tok: lblk for tok, lblk, _tag, _d, _c in ACCIONES}


def _K():
    """La paleta del TEMA activo, igual que el hub. Sin tuitheme, el
    fallback de hublayout.cols() (nunca truena, solo pierde color)."""
    try:
        import tuitheme
        return HL.cols(tuitheme.palette())
    except Exception:
        return HL.cols(type("P", (), {"GLYPHS": {}})())


def _size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 100, 34


def _wrap(txt, w):
    pal, ln, out = str(txt).split(), "", []
    for p in pal:
        if len(ln) + len(p) + 1 > w:
            out.append(ln)
            ln = p
        else:
            ln = (ln + " " + p).strip()
    if ln:
        out.append(ln)
    return out or [""]


def _version():
    try:
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:
        return ""


def _mmss(seg):
    seg = max(0, int(seg))
    return "%d:%02d" % (seg // 60, seg % 60)


# ── git / chequeo de actualización (falla-suave SIEMPRE) ────────────────────
def _gitq(path, *args, timeout=30):
    """git -C <path> <args> capturado. (rc, stdout, stderr). Nunca lanza."""
    try:
        r = subprocess.run(["git", "-C", path] + list(args),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)


def _update_info(timeout=12):
    """¿Hay actualización del harness? fetch de la rama ACTUAL + conteo.
    {ok, behind, branch, commits:[(sha, asunto)…]} o {ok:False, reason}."""
    try:
        if not os.path.isdir(os.path.join(ROOT, ".git")):
            return {"ok": False, "reason": t("actualizaciones.reason.not_git")}
        rc, remotes, _ = _gitq(ROOT, "remote", timeout=8)
        if rc != 0 or not remotes:
            return {"ok": False, "reason": t("actualizaciones.reason.no_remote")}
        rc, branch, _ = _gitq(ROOT, "rev-parse", "--abbrev-ref", "HEAD",
                              timeout=8)
        if rc != 0 or not branch or branch == "HEAD":
            return {"ok": False,
                    "reason": t("actualizaciones.reason.branch_undeterminable")}
        rc, _, err = _gitq(ROOT, "fetch", "--quiet", "origin", branch,
                           timeout=timeout)
        if rc != 0:
            return {"ok": False, "reason": t("actualizaciones.reason.offline")}
        rc, cnt, _ = _gitq(ROOT, "rev-list", "--count",
                           "HEAD..origin/%s" % branch, timeout=8)
        behind = int(cnt) if rc == 0 and cnt.isdigit() else 0
        commits, new_version, upstream = [], "", ""
        if behind > 0:
            rc, upstream, _ = _gitq(ROOT, "rev-parse", "origin/%s" % branch, timeout=8)
            upstream = upstream if rc == 0 else ""
            rc, nv, _ = _gitq(ROOT, "show", "origin/%s:VERSION" % branch, timeout=8)
            new_version = nv.strip() if rc == 0 and len(nv.strip()) <= 20 else ""
            rc, log, _ = _gitq(ROOT, "log", "--format=%h\x1f%s", "-30",
                               "HEAD..origin/%s" % branch, timeout=10)
            if rc == 0:
                commits = [tuple(ln.split("\x1f", 1))
                           for ln in log.splitlines() if "\x1f" in ln]
        return {"ok": True, "behind": behind, "branch": branch,
                "commits": commits, "new_version": new_version,
                "upstream": upstream}
    except Exception as e:
        return {"ok": False, "reason": "%s" % type(e).__name__}


def _lanza_chk(S):
    """Chequeo de update en 2º plano al abrir el menú (no bloquea nada)."""
    if (S.get("chk") or {}).get("state") == "busy":
        return
    S["chk"] = {"state": "busy"}

    def _w():
        info = _update_info()
        try:   # ¿a qué versión se puede volver? ¿la nueva es la que quedó en pausa?
            import updater
            e = updater.rollback_target(ROOT)
            S["rb"] = (e.get("from_version") or (e.get("from") or "")[:7]) if e else None
            h = updater.hold()
            info["held"] = bool(h and info.get("upstream") and h.get("bad") == info["upstream"])
        except Exception:
            S["rb"] = None
        info["state"] = "done"
        S["chk"] = info

    threading.Thread(target=_w, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════
#  El TRABAJO (hilo daemon) — pasos estructurados, jamás imprime en pantalla
# ══════════════════════════════════════════════════════════════════════════
def _fase_corta(titulo):
    """'5 · Hooks por cerebro (contrato…)' → '5 · Hooks por cerebro'."""
    t = str(titulo).split("(")[0].split(" — ")[0].strip()
    return t.rstrip("·").strip()


def _live(job, st, txt):
    job["live"].append((st, str(txt)))
    del job["live"][:-150]


def _inicia_job(S, tok):
    """Prepara el plan y arranca el hilo. Devuelve "ok" si corre aquí, o
    "fallback" si este flujo necesita la terminal clásica (front lo corre)."""
    try:
        import doctor
        import install
        import dispatch
    except Exception:
        return "fallback"
    try:
        ctx = doctor.build_ctx()
    except Exception:
        return "fallback"
    fix, aviso = tok in ("repair", "update"), ""
    if fix:
        try:   # mismo guard que doctor.main: desde un worktree NO se repara
            if install.running_from_worktree(ROOT) and \
                    os.environ.get(install.FORCE_ENV) != "1":
                fix = False
                aviso = t("actualizaciones.aviso.worktree")
        except Exception:
            pass
    plan, steps = [], []
    if tok == "update":
        vistos = set()
        for label, path, transport in _repos_update(ctx, dispatch):
            if path:
                key = os.path.normcase(os.path.realpath(path))
                if key in vistos:
                    continue
                vistos.add(key)
            plan.append(("pull", label, path, transport))
            steps.append({"label": t("actualizaciones.step.fetch",
                                     label=label), "st": "pend", "note": ""})
    for titulo, fn in doctor.PHASES:
        titulo = doctor.phase_title(titulo, fn)       # título en el idioma de la UI
        plan.append(("fase", titulo, fn))
        steps.append({"label": _fase_corta(titulo), "st": "pend", "note": ""})
    if tok != "update":
        plan.append(("chk",))
        steps.append({"label": t("actualizaciones.step.check_update"),
                      "st": "pend", "note": ""})
    job = {"modo": tok, "label": t(_LBL.get(tok, tok)), "fix": fix,
           "aviso": aviso, "plan": plan, "steps": steps, "cur": -1,
           "live": [], "findings": [], "pulled": [], "new_commits": [],
           "n_new": 0, "chk_final": None, "t0": time.monotonic(), "t1": None,
           "done": False, "cancel": False, "error": "", "_oldio": None}
    S["job"], S["view"], S["scroll"], S["msg"] = job, "run", 0, ""
    threading.Thread(target=_worker, args=(S, ctx, doctor), daemon=True) \
        .start()
    return "ok"


def _repos_update(ctx, dispatch):
    """[(label, path|None, transport)] — misma enumeración que cmd_update:
    WORKSPACE + cada cerebro registrado, con su transport real."""
    repos = [("WORKSPACE", ROOT, "git")]
    for a in ctx.get("agents", []):
        name, brain = a["name"], a.get("brain")
        if brain and os.path.isdir(brain):
            try:
                tr = dispatch.brain_transport(name, brain)
            except Exception:
                tr = "git"
            repos.append((t("actualizaciones.repo.brain", name=name),
                          brain, tr))
        else:
            repos.append((t("actualizaciones.repo.brain", name=name),
                          None, "git"))
    return repos


def _worker(S, ctx, doctor):
    """Corre el plan en orden. Captura stdout/stderr/stdin del proceso (las
    fases del doctor no imprimen, pero los fixers de install sí podrían) para
    que NADA se cuele sobre la pantalla. Restaura SIEMPRE."""
    job = S["job"]
    old = (sys.stdout, sys.stderr, sys.stdin)
    job["_oldio"] = old
    sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
    sys.stdin = io.StringIO("")
    try:
        for i, paso in enumerate(job["plan"]):
            if job["cancel"]:
                for st in job["steps"][i:]:
                    st["st"], st["note"] = "skip", ""
                break
            job["cur"] = i
            job["steps"][i]["st"] = "run"
            try:
                if paso[0] == "pull":
                    _paso_pull(job, i, paso)
                elif paso[0] == "fase" and job.get("harness_new"):
                    # El harness cambió en disco: las fases cargadas en ESTE
                    # proceso son las de la versión vieja. La revisión la hace
                    # la versión nueva, en su propio proceso, una sola vez.
                    if not job.get("new_doctor_done"):
                        _paso_doctor_nuevo(job, i)
                        job["new_doctor_done"] = True
                    else:
                        job["steps"][i]["st"] = "skip"
                        job["steps"][i]["note"] = ""
                elif paso[0] == "fase":
                    _paso_fase(job, i, paso, ctx, doctor)
                else:
                    _paso_chk(job, i)
            except Exception as e:
                job["steps"][i]["st"] = "fail"
                job["steps"][i]["note"] = "error"
                _live(job, "fail", t("actualizaciones.live.step_error",
                                     name=type(e).__name__, msg=e))
    except Exception as e:
        job["error"] = "%s: %s" % (type(e).__name__, e)
    finally:
        try:
            sys.stdout, sys.stderr, sys.stdin = old
        except Exception:
            pass
        job["t1"] = time.monotonic()
        job["done"] = True


def _paso_fase(job, i, paso, ctx, doctor):
    """Una fase del doctor: corre fn(ctx, fix) y guarda hallazgos ya
    estructurados (status/label/detail/action) — nada de parsear texto."""
    _, titulo, fn = paso
    try:
        finds = fn(ctx, fix=job["fix"])
    except Exception as e:
        finds = [doctor.f(doctor.FAIL,
                          doctor._t("doctor.main.8", "error interno de la fase"),
                          "%s: %s" % (type(e).__name__, e), "")]
    stmap = {doctor.OK: "ok", doctor.FIXED: "fixed", doctor.WARN: "warn",
             doctor.FAIL: "fail"}
    worst = doctor._worst(finds) if finds else doctor.OK
    n = {s: sum(1 for x in finds if x["status"] == s)
         for s in (doctor.OK, doctor.FIXED, doctor.WARN, doctor.FAIL)}
    nota = []
    if n[doctor.FIXED]:
        nota.append(t("actualizaciones.note.fixed", n=n[doctor.FIXED],
                      s="s" if n[doctor.FIXED] != 1 else ""))
    if n[doctor.WARN]:
        nota.append("%d⚠" % n[doctor.WARN])
    if n[doctor.FAIL]:
        nota.append("%d✗" % n[doctor.FAIL])
    job["steps"][i]["st"] = stmap.get(worst, "ok")
    job["steps"][i]["note"] = " ".join(nota)
    for x in finds:
        job["findings"].append((titulo, x))
        if x["status"] != doctor.OK:    # el live solo cuenta lo interesante
            _live(job, stmap.get(x["status"], "ok"),
                  x["label"] + ((" — " + x["detail"]) if x["detail"] else ""))
    if worst == doctor.OK:
        _live(job, "ok", t("actualizaciones.live.phase_ok",
                           fase=_fase_corta(titulo), n=len(finds)))


def _paso_harness(job, i, label):
    """El HARNESS se actualiza con el mismo motor que `workspace update`
    (updater.update_harness: candado, fast-forward, comprueba que la versión
    nueva arranca y si no vuelve sola, ajustes registrados)."""
    import updater
    res = updater.update_harness(ROOT, mode="manual")
    stt = res.get("status")
    st, note, txt = "ok", "", ""
    if stt == updater.UPDATED:
        n = len(res.get("commits") or [])
        st, note = "fixed", "+%d" % n
        txt = t("actualizaciones.pull.updated_version",
                v=res.get("to_version") or res.get("to", "")[:7], n=n)
        job["new_commits"], job["n_new"] = list(res.get("commits") or [])[:15], n
        job["harness_new"] = True
        mig = res.get("migrations") or {}
        try:
            import migrate
            line = migrate.summary_line(mig) if not mig.get("error") else ""
        except Exception:
            line = ""
        if line:
            _live(job, "warn" if mig.get("failed") else "ok", line)
    elif stt == updater.UPTODATE:
        note = t("actualizaciones.note.uptodate")
        txt = t("actualizaciones.pull.uptodate", branch=res.get("branch") or "?")
    elif stt == updater.ROLLED_BACK:
        st = "warn"
        txt = t("actualizaciones.pull.rolled_back")
    elif stt == updater.HELD:
        st = "warn"
        txt = t("actualizaciones.pull.paused_manual"
                if (updater.hold() or {}).get("kind") == "manual"
                else "actualizaciones.pull.held")
    else:
        st = "warn"
        txt = updater.reason_text(res.get("reason"))
    job["steps"][i]["st"] = st
    job["steps"][i]["note"] = note or ("⚠" if st == "warn" else "")
    job["pulled"].append((label, st, txt))
    _live(job, st, "%s: %s" % (label, txt))


def _paso_doctor_nuevo(job, i):
    """Revisión con la versión NUEVA del harness (proceso aparte): el doctor
    cargado aquí es el viejo y podría reparar con reglas viejas."""
    args = [sys.executable, os.path.join(ROOT, "front.py"), "doctor", "--from-update"]
    if not job.get("fix"):
        args.append("--check")
    env = dict(os.environ)
    env.update(PYTHONIOENCODING="utf-8", WORKSPACE_NO_AUTOUPDATE="1")
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600, env=env,
                           stdin=subprocess.DEVNULL, cwd=ROOT)
        ok = r.returncode == 0
    except Exception:
        ok = False
    job["steps"][i]["st"] = "ok" if ok else "warn"
    job["steps"][i]["note"] = t("actualizaciones.note.new_version")
    _live(job, "ok" if ok else "warn",
          t("actualizaciones.live.new_doctor_ok") if ok
          else t("actualizaciones.live.new_doctor_warn"))


def _paso_pull(job, i, paso):
    """Pull --ff-only de UN repo en su rama actual — misma clasificación que
    front._update_repo, pero estructurada para pintarse en la pantalla. El
    harness (ROOT) va por updater (ver _paso_harness)."""
    _, label, path, transport = paso
    if path and os.path.normcase(os.path.realpath(path)) == \
            os.path.normcase(os.path.realpath(ROOT)):
        return _paso_harness(job, i, label)
    st, note, txt = "ok", "", ""
    if transport == "obsidian-sync":
        note, txt = t("actualizaciones.note.sync"), t("actualizaciones.pull.sync")
    elif not path:
        st, note = "warn", ""
        txt = t("actualizaciones.pull.brain_unresolved")
    elif not os.path.isdir(os.path.join(path, ".git")):
        st, txt = "warn", t("actualizaciones.pull.not_git")
    else:
        rc, remotes, _ = _gitq(path, "remote", timeout=10)
        _, dirty, _ = _gitq(path, "status", "--porcelain", timeout=15)
        if rc != 0 or not remotes:
            st, txt = "warn", t("actualizaciones.pull.no_remote")
        elif dirty:
            st, txt = "warn", t("actualizaciones.pull.dirty")
        else:
            _, branch, _ = _gitq(path, "rev-parse", "--abbrev-ref", "HEAD",
                                 timeout=10)
            _, old, _ = _gitq(path, "rev-parse", "--short", "HEAD",
                              timeout=10)
            rc, out, err = _gitq(path, "pull", "--ff-only", timeout=120)
            low = (out + " " + err).lower()
            if rc != 0:
                st = "warn"
                if "no tracking" in low or "remote ref" in low:
                    txt = t("actualizaciones.pull.no_tracking",
                            branch=branch or "?")
                elif any(k in low for k in ("could not resolve",
                                            "unable to access", "timeout",
                                            "connection")):
                    txt = t("actualizaciones.pull.offline")
                elif "fast-forward" in low or "divergent" in low:
                    txt = t("actualizaciones.pull.divergent")
                else:
                    txt = ((err or out).splitlines()[-1][:70]
                           if (err or out) else t("actualizaciones.pull.failed"))
            else:
                _, new, _ = _gitq(path, "rev-parse", "--short", "HEAD",
                                  timeout=10)
                if new and new != old:
                    rc2, cnt, _ = _gitq(path, "rev-list", "--count",
                                        "%s..%s" % (old, new), timeout=10)
                    n = int(cnt) if rc2 == 0 and cnt.isdigit() else 0
                    st, note = "fixed", "+%d" % n
                    txt = t("actualizaciones.pull.updated", n=n, new=new,
                            branch=branch or "?")
                    rc3, log, _ = _gitq(path, "log", "--format=%h\x1f%s",
                                        "-15", "%s..%s" % (old, new),
                                        timeout=10)
                    if rc3 == 0 and os.path.realpath(path) == \
                            os.path.realpath(ROOT):
                        job["new_commits"] = [
                            tuple(ln.split("\x1f", 1))
                            for ln in log.splitlines() if "\x1f" in ln]
                        job["n_new"] = n
                else:
                    note = t("actualizaciones.note.uptodate")
                    txt = t("actualizaciones.pull.uptodate",
                            branch=branch or "?")
    job["steps"][i]["st"] = st
    job["steps"][i]["note"] = note or ("⚠" if st == "warn" else "")
    job["pulled"].append((label, st, txt))
    _live(job, st, "%s: %s" % (label, txt))


def _paso_chk(job, i):
    """Último paso de revisar/reparar: ¿hay actualización del harness?"""
    info = _update_info()
    job["chk_final"] = info
    if info.get("ok") and info.get("behind", 0) > 0:
        job["steps"][i]["st"] = "warn"
        job["steps"][i]["note"] = "↓%d" % info["behind"]
        _live(job, "warn", t("actualizaciones.chk.available",
                             n=info["behind"]))
    elif info.get("ok"):
        job["steps"][i]["st"] = "ok"
        job["steps"][i]["note"] = t("actualizaciones.note.uptodate")
        _live(job, "ok", t("actualizaciones.chk.harness_uptodate",
                           branch=info.get("branch", "?")))
    else:
        job["steps"][i]["st"] = "warn"
        job["steps"][i]["note"] = t("actualizaciones.note.offline")
        _live(job, "warn", t("actualizaciones.chk.cannot_verify",
                             reason=info.get("reason", "?")))


def _pendientes(job):
    """[(titulo_fase, finding)] con ⚠/✗ — lo que queda por resolver."""
    return [(t, x) for t, x in job["findings"]
            if x["status"] in ("warn", "fail")]


# ══════════════════════════════════════════════════════════════════════════
#  Render — tres vistas, SIEMPRE h-1 líneas (cambiar de vista no deja basura)
# ══════════════════════════════════════════════════════════════════════════
_ICO = {"pend": ("DK", "·"), "ok": ("OK", "✓"), "fixed": ("C", "✓"),
        "warn": ("B", "⚠"), "fail": ("ERR", "✗"), "skip": ("DK", "—")}


def _icono(K, st):
    if st == "run":    # perilla ● que pulsa por el gradiente del wordmark
        wc = K["WCOL"]
        return "%s%s●%s" % (wc[int(time.monotonic() * 6) % len(wc)],
                            K["BO"], K["R"])
    col, ch = _ICO.get(st, ("DK", "·"))
    return "%s%s%s" % (K[col], ch, K["R"])


def _progreso(K, hechos, total, ancho):
    """`━━━●────` — el slider del hub como barra de avance (recorrido en el
    gradiente del wordmark, perilla ● en el punto actual)."""
    ancho = max(5, ancho)
    v = 1 + int((ancho - 1) * (hechos / float(max(1, total))))
    v = max(1, min(ancho, v))
    wc = K["WCOL"]
    col = wc[2 % len(wc)] + K["BO"]
    return "%s%s%s%s%s%s%s" % (col, "━" * (v - 1), "●", K["R"],
                               K["DK"], "─" * (ancho - v), K["R"])


# ══ REDISEÑO 2026-10-14 (concepto Omarchy, pedido del dueño) ═══════════════
# Una caja centrada y VERTICAL, como Agentes y Motores. En el menú, SOLO lo
# que se puede hacer ahora: la versión que tienes, si hay nueva, y las
# acciones disponibles («actualizar» aparece cuando hay versión nueva;
# «volver a vX», cuando hay a cuál; «buscar de nuevo», si no se pudo
# verificar) más el ajuste de automáticas. Lo didáctico (cómo se prueba una
# versión, la red de seguridad, qué cambia en tu máquina y los comandos
# equivalentes) vive detrás de `i`. EN CURSO y RESULTADO usan la misma caja.
BOX_W = 50
#: Pasos visibles en la vista EN CURSO (más → ventana con «↑/↓ n más»).
PASOS_VISIBLES = 9


def word():
    return HL.section_word('actualizaciones')


def _modo_auto():
    """(modo, texto) de las actualizaciones automáticas; falla-suave."""
    try:
        import updater
        m = updater.auto_mode()
        return m, updater.auto_mode_text(m)
    except Exception:
        return "auto", ""


def _cicla_modo_auto(S):
    """`a` (o Enter sobre «automáticas»): sí → solo avisar → no → sí."""
    try:
        import updater
        if os.environ.get("WORKSPACE_NO_AUTOUPDATE"):
            S["msg"] = t("actualizaciones.msg.auto_env")
            return
        cur = updater.auto_mode()
        nxt = updater.AUTO_MODES[(updater.AUTO_MODES.index(cur) + 1)
                                 % len(updater.AUTO_MODES)]
        updater.set_auto_mode(nxt)
        S["msg"] = t("actualizaciones.msg.auto_set",
                     mode=updater.auto_mode_text(nxt))
    except Exception as e:
        S["msg"] = t("actualizaciones.msg.auto_fail", err=type(e).__name__)


def _chips(S):
    view = S.get("view", "menu")
    if view == "run" and S.get("job"):
        return (("q", t("actualizaciones.hint.cancel_run")),)
    if view == "done" and S.get("job"):
        return (("↑↓", t("actualizaciones.k.scroll")),
                ("Enter", t("actualizaciones.k.back")))
    if S.get("confirm"):
        return (("Enter", t("actualizaciones.k.confirm")),
                ("Esc", t("actualizaciones.k.cancel")))
    return (("↑↓", t("actualizaciones.k.pick")),
            ("Enter", t("actualizaciones.k.apply")),
            ("i", t("actualizaciones.k.info")),
            ("q", t("actualizaciones.k.back")))


def _regla(K, txt, iw):
    """`── txt ─────` — el separador con nombre de las cajas del rediseño."""
    return HL.clip("%s── %s%s%s %s%s%s" % (K["DK"], K["DIM"], txt, K["R"], K["DK"],
                                         K["SEP"] * max(1, iw - HL.vis(txt) - 4),
                                         K["R"]), iw)


# ── vista MENÚ ──────────────────────────────────────────────────────────────
def _hay_nueva(S):
    """La búsqueda terminó y hay versión nueva que SÍ se puede traer (no la
    que quedó en pausa porque el usuario volvió a la anterior)."""
    chk = S.get("chk") or {}
    return (chk.get("state") == "done" and chk.get("ok")
            and chk.get("behind", 0) > 0 and not chk.get("held"))


def _opciones(S):
    """[(token, etiqueta)] — SOLO lo que se puede hacer ahora."""
    chk = S.get("chk") or {}
    ops = []
    if _hay_nueva(S):
        nv = chk.get("new_version") or ""
        ops.append(("update", t("actualizaciones.o.update_to", v=nv) if nv
                    else t("actualizaciones.o.update")))
    ops += [("repair", t("actualizaciones.o.repair")),
            ("check", t("actualizaciones.o.check"))]
    if S.get("rb"):
        ops.append(("rollback", t("actualizaciones.o.rollback", v=S["rb"])))
    if chk.get("state") == "done" and not chk.get("ok"):
        ops.append(("recheck", t("actualizaciones.o.recheck")))
    ops.append(("auto", t("actualizaciones.o.auto")))
    return ops


def _elegida(S, ops):
    """Índice de la opción elegida. Se recuerda por su TOKEN: si «actualizar»
    aparece arriba al terminar la búsqueda, el cursor no cambia de acción
    por debajo del usuario; si aún no se ha movido, va a «actualizar»."""
    toks = [o[0] for o in ops]
    tok = S.get("sel")
    if "update" in toks and not S.get("moved"):
        tok = "update"
    if tok not in toks:
        tok = toks[max(0, min(int(S.get("si", 0) or 0), len(toks) - 1))]
    S["sel"], S["si"] = tok, toks.index(tok)
    return S["si"]


def _estado(S, K):
    """(color, texto) del estado: buscando · hay nueva · al día · en pausa ·
    sin verificar (con el porqué)."""
    chk = S.get("chk") or {}
    if not chk:
        return K["DK"], "—"
    if chk.get("state") == "busy":
        return K["DIM"], t("actualizaciones.st.searching")
    if chk.get("ok") and chk.get("behind", 0) > 0 and chk.get("held"):
        return K["B2"], t("actualizaciones.st.held")
    if chk.get("ok") and chk.get("behind", 0) > 0:
        nv = chk.get("new_version")
        return K["B"] + K["BO"], (t("actualizaciones.st.new_v", v=nv) if nv
                                  else t("actualizaciones.st.new"))
    if chk.get("ok"):
        return K["OK"], t("actualizaciones.st.uptodate")
    return K["DIM"], t("actualizaciones.st.unverified", reason=chk.get("reason") or "?")


def _valor_auto(K):
    """El ajuste de automáticas como interruptor de tres posiciones:
    `━━●` sí · `━●━` solo avisar · `○━━` no."""
    m, _txt = _modo_auto()
    if m == "auto":
        return "%s %s%s%s" % (SB.switch(K, True), K["OK"],
                              t("actualizaciones.auto.v.auto"), K["R"])
    if m == "off":
        return "%s %s%s%s" % (SB.switch(K, False), K["DIM"],
                              t("actualizaciones.auto.v.off"), K["R"])
    return "%s━●━%s %s%s%s" % (K["B2"] + K["BO"], K["R"], K["B2"],
                               t("actualizaciones.auto.v.notify"), K["R"])


def _cuerpo_menu(S, K, iw):
    ops = _opciones(S)
    si = _elegida(S, ops)
    lab_w = max(HL.vis(t("actualizaciones.f.version")),
                HL.vis(t("actualizaciones.f.state")),
                HL.vis(t("actualizaciones.o.auto"))) + 2
    v = _version()
    out = [HL.clip("  %s%s%s%s%s%s" % (K["GREY"], HL.pad(t("actualizaciones.f.version"), lab_w),
                                       K["R"], K["WH"] + K["BO"], ("v" + v) if v else "—",
                                       K["R"]), iw),
           ]
    # el estado se parte en varias filas si no cabe (el porqué de «sin
    # verificar» es largo); las de continuación, alineadas con el valor
    col, txt = _estado(S, K)
    for n, sub in enumerate(_wrap(txt, max(8, iw - 2 - lab_w))[:2]):
        lab = t("actualizaciones.f.state") if n == 0 else ""
        out.append(HL.clip("  %s%s%s%s%s%s" % (K["GREY"], HL.pad(lab, lab_w), K["R"],
                                               col, sub, K["R"]), iw))
    out.append("")
    fila = 0
    for n, (tok, lab) in enumerate(ops):
        if tok == "auto":
            out.append("  %s%s%s" % (K["DK"], K["SEP"] * max(1, iw - 2), K["R"]))
        on = (n == si)
        if on:
            fila = len(out)
        cur = ("%s%s %s" % (K["C"] + K["BO"], K["PTR"], K["R"])) if on else "  "
        tinta = (K["WH"] + K["BO"]) if on else K["GREY"]
        if tok == "rollback" and S.get("confirm") == "rollback":
            out.append(HL.clip("%s%s%s%s" % (
                cur, K["ERR"] + K["BO"],
                t("actualizaciones.o.rollback_confirm", v=S.get("rb") or "?"), K["R"]), iw))
            continue
        if tok == "auto":
            out.append(HL.clip("%s%s%s%s%s" % (cur, tinta, HL.pad(lab, lab_w), K["R"],
                                               _valor_auto(K)), iw))
            continue
        if tok == "update":
            tinta = (K["B"] + K["BO"]) if on else K["B"]
        flecha = "%s›%s" % ((K["C"] + K["BO"]) if on else K["DK"], K["R"])
        hueco = max(1, iw - 2 - HL.vis(lab) - 1)
        out.append(HL.clip("%s%s%s%s%s%s" % (cur, tinta, lab, K["R"], " " * hueco, flecha),
                           iw))
    S["_cur"] = fila
    return out


def _info_blocks(S, K):
    """El cuadro de `i`: tu versión, cómo llega una versión nueva (con su red
    de seguridad), qué cambia en tu máquina, cada opción y su comando."""
    v = _version()
    ahora = [(t("actualizaciones.f.version"), ("v" + v) if v else "—")]
    if S.get("version_text"):
        ahora.append((t("actualizaciones.info.detail"), S["version_text"]))
    _m, txt = _modo_auto()
    if txt:
        ahora.append((t("actualizaciones.o.auto"), txt))
    return [
        ("h", t("actualizaciones.info.h_now")),
        ("kv", ahora),
        ("gap",),
        ("h", t("actualizaciones.info.h_how")),
        ("flow", [(t("actualizaciones.info.n1"), t("actualizaciones.info.c1")),
                  (t("actualizaciones.info.n2"), t("actualizaciones.info.c2")),
                  (t("actualizaciones.info.n3"), t("actualizaciones.info.c3"))]),
        ("gap",),
        ("p", t("actualizaciones.info.p1")),
        ("gap",),
        ("p", t("actualizaciones.info.p2")),
        ("h", t("actualizaciones.info.h_opts")),
        ("kv", [(t("actualizaciones.o.update"), t("actualizaciones.info.o_update")),
                (t("actualizaciones.o.repair"), t("actualizaciones.info.o_repair")),
                (t("actualizaciones.o.check"), t("actualizaciones.info.o_check")),
                (t("actualizaciones.info.k_rollback"), t("actualizaciones.info.o_rollback")),
                (t("actualizaciones.o.auto"), t("actualizaciones.info.o_auto"))]),
        ("h", t("actualizaciones.info.h_cmds")),
        ("kv", [("workspace update", t("actualizaciones.info.c_update")),
                ("workspace doctor", t("actualizaciones.info.c_repair")),
                ("workspace doctor --check", t("actualizaciones.info.c_check")),
                ("workspace update --rollback", t("actualizaciones.info.c_rollback"))]),
    ]


def _render_menu(S, K, w, h):
    if S.get("info"):
        return SB.info_frame(K, w, h, word(), t("actualizaciones.info.title"),
                             _info_blocks(S, K), state=S["info"], box_w=64)
    # alto de referencia: versión + estado (hasta 2 filas) + aire + hasta 4
    # acciones + regla + automáticas
    return SB.frame(K, w, h, word(), t("actualizaciones.box.left"),
                    lambda iw: _cuerpo_menu(S, K, iw), _chips(S),
                    msg=S.get("msg", ""), cursor_line=lambda: S.get("_cur", 0),
                    box_w=BOX_W, stable_rows=10)


# ── vista EN CURSO ──────────────────────────────────────────────────────────
def _sin_numero(label):
    """«5 · Hooks por cerebro» → «Hooks por cerebro»: el número de fase es
    interno (el dueño: «cada uno empezaba con un f5 o f8»)."""
    return re.sub(r"^\s*\d[\w-]*\s*·\s*", "", str(label))


def _cuerpo_pasos(S, K, iw, ih):
    """CADA paso con su estado. Si no caben, ventana centrada en el paso
    actual con marcadores «↑ n antes / ↓ n más»."""
    job = S["job"]
    steps = job["steps"]
    n = len(steps)
    cur = max(0, job["cur"])
    start, fin = 0, n
    if n > ih:
        start = min(max(0, cur - ih // 2), max(0, n - ih))
        fin = start + ih
        if start > 0:                 # el marcador ↑ ocupa la primera fila
            start += 1
        if fin < n:                   # el marcador ↓ ocupa la última fila
            fin -= 1
    out = []
    if start > 0:
        out.append(HL.clip("  %s%s%s" % (K["DK"], t("actualizaciones.steps.before", n=start),
                                         K["R"]), iw))
    for i in range(start, min(fin, n)):
        st = steps[i]
        icon = _icono(K, st["st"])
        note = st.get("note") or ""
        label = _sin_numero(st["label"])
        lcol = (K["WH"] + K["BO"]) if st["st"] == "run" else \
            (K["DK"] if st["st"] in ("pend", "skip") else K["GREY"])
        if note:
            lab = HL.pad(HL.clip(label, max(4, iw - 6 - HL.vis(note))),
                         max(4, iw - 5 - HL.vis(note)))
            ncol = {"warn": K["B"], "fail": K["ERR"],
                    "fixed": K["C"]}.get(st["st"], K["DK"])
            out.append(HL.clip("  %s %s%s%s %s%s%s" % (icon, lcol, lab, K["R"], ncol, note,
                                                       K["R"]), iw))
        else:
            out.append(HL.clip("  %s %s%s%s" % (icon, lcol, label, K["R"]), iw))
    if fin < n:
        out.append(HL.clip("  %s%s%s" % (K["DK"], t("actualizaciones.steps.after", n=n - fin),
                                         K["R"]), iw))
    return out


def _cuerpo_run(S, K, iw):
    """Progreso + reloj, cada paso con su estado y lo último que pasó."""
    job = S["job"]
    total = len(job["steps"])
    hechos = sum(1 for s in job["steps"] if s["st"] not in ("pend", "run"))
    reloj = "%d/%d · %s" % (hechos, total, _mmss(time.monotonic() - job["t0"]))
    out = [HL.clip("  %s  %s%s%s" % (_progreso(K, hechos, total,
                                               max(6, iw - 4 - HL.vis(reloj))),
                                     K["WH"] + K["BO"], reloj, K["R"]), iw), ""]
    out += _cuerpo_pasos(S, K, iw, min(total, PASOS_VISIBLES) or 1)
    out += ["", _regla(K, t("actualizaciones.sec.latest"), iw)]
    vivos = job["live"][-2:]
    for st, txt in vivos:
        col, ch = _ICO.get(st, ("DK", "·"))
        out.append(HL.clip("  %s%s%s %s%s%s" % (K[col], ch, K["R"], K["DIM"],
                                                _wrap(txt, max(8, iw - 4))[0], K["R"]), iw))
    if not vivos:
        out.append(HL.clip("  %s%s%s" % (K["DK"], t("actualizaciones.live.starting"), K["R"]),
                           iw))
    return out


# ── vista RESULTADO ─────────────────────────────────────────────────────────
def _veredicto(job, K):
    pend = _pendientes(job)
    fails = sum(1 for _t, x in pend if x["status"] == "fail")
    warns = len(pend) - fails
    if job["error"]:
        return (K["ERR"] + K["BO"],
                t("actualizaciones.verdict.error", err=job["error"]))
    if job["cancel"]:
        return (K["B"] + K["BO"], t("actualizaciones.verdict.cancelled"))
    if fails:
        return (K["ERR"] + K["BO"],
                t("actualizaciones.verdict.fails", n=fails))
    if warns:
        return (K["B"] + K["BO"],
                t("actualizaciones.verdict.warns", n=warns))
    return (K["OK"] + K["BO"], t("actualizaciones.verdict.ok"))


def _lineas_pendientes(job, K, iw):
    """Cada pendiente: qué es, por qué y qué hacer (sin el número de fase)."""
    if job["error"]:
        return [HL.clip("  %s✗ %s%s" % (K["ERR"], job["error"], K["R"]), iw),
                HL.clip("  %s%s%s" % (K["DIM"], t("actualizaciones.pend.error_cmd"), K["R"]),
                        iw)]
    out = []
    for _titulo, x in _pendientes(job):
        sym = ("%s✗%s" % (K["ERR"], K["R"])) if x["status"] == "fail" \
            else ("%s⚠%s" % (K["B"], K["R"]))
        lab = _wrap(x["label"], max(8, iw - 5))
        out.append(HL.clip("  %s %s%s%s" % (sym, K["WH"], lab[0], K["R"]), iw))
        out += [HL.clip("    %s%s%s" % (K["WH"], sub, K["R"]), iw) for sub in lab[1:2]]
        if x.get("detail"):
            for sub in _wrap(x["detail"], max(8, iw - 6))[:2]:
                out.append(HL.clip("    %s%s%s" % (K["DIM"], sub, K["R"]), iw))
        if x.get("action"):
            lineas = _wrap(x["action"], max(8, iw - 8))
            out.append(HL.clip("    %s→%s %s%s%s" % (K["B"], K["R"], K["GREY"], lineas[0],
                                                     K["R"]), iw))
            for sub in lineas[1:3]:
                out.append(HL.clip("      %s%s%s" % (K["GREY"], sub, K["R"]), iw))
        out.append("")
    if out and not out[-1]:
        out.pop()
    return out


def _texto(K, col, txt, iw, sangria=2):
    """Un texto que no cabe en una fila se parte en varias (no se recorta)."""
    return [HL.clip("%s%s%s%s" % (" " * sangria, col, sub, K["R"]), iw)
            for sub in _wrap(txt, max(8, iw - sangria - 1))]


def _cuerpo_done(S, K, iw):
    """Veredicto, qué llegó (o si hay actualización) y los pendientes."""
    job = S["job"]
    col, txt = _veredicto(job, K)
    dur = _mmss((job["t1"] or time.monotonic()) - job["t0"])
    out = _texto(K, col, txt, iw) + [
        HL.clip("  %s%s%s" % (K["DK"], t("actualizaciones.sum.duration", dur=dur,
                                         n=len(job["steps"])), K["R"]), iw)]
    if job["modo"] == "update":
        out += ["", _regla(K, t("actualizaciones.sec.arrived"), iw)]
        if job["n_new"]:
            out.append(HL.clip("  %s%s%s" % (K["WH"] + K["BO"],
                                             t("actualizaciones.sum.ws_new", n=job["n_new"]),
                                             K["R"]), iw))
            for sha, subj in job["new_commits"][:5]:
                out.append(HL.clip("  %s%s%s %s%s%s" % (K["C"], sha, K["R"], K["DIM"], subj,
                                                        K["R"]), iw))
            resto = job["n_new"] - min(5, len(job["new_commits"]))
            if resto > 0:
                out.append(HL.clip("  %s%s%s" % (K["DK"], t("actualizaciones.sum.more", n=resto),
                                                 K["R"]), iw))
        else:
            out.append(HL.clip("  %s%s%s" % (K["GREY"], t("actualizaciones.sum.nothing_new"),
                                             K["R"]), iw))
        for lb, st, tx in [p for p in job["pulled"] if p[0] != "WORKSPACE"][:4]:
            colb, ch = _ICO.get(st, ("DK", "·"))
            out.append(HL.clip("  %s%s%s %s%s: %s%s" % (K[colb], ch, K["R"], K["DIM"], lb, tx,
                                                        K["R"]), iw))
    else:
        cf = job.get("chk_final") or {}
        out += ["", _regla(K, t("actualizaciones.sec.update"), iw)]
        if cf.get("ok") and cf.get("behind", 0) > 0:
            out += _texto(K, K["B"] + K["BO"],
                          t("actualizaciones.sum.available", n=cf["behind"]), iw)
        elif cf.get("ok"):
            out.append(HL.clip("  %s%s%s" % (K["OK"], t("actualizaciones.sum.uptodate",
                                                         branch=cf.get("branch", "?")), K["R"]),
                               iw))
        else:
            out += _texto(K, K["DK"], t("actualizaciones.sum.cannot_verify",
                                        reason=cf.get("reason")
                                        or t("actualizaciones.reason.no_data")), iw)
    npend = len(_pendientes(job))
    if npend or job["error"]:
        out += ["", _regla(K, t("actualizaciones.sec.pending_n", n=npend) if npend
                           else t("actualizaciones.sec.pending"), iw)]
        out += _lineas_pendientes(job, K, iw)
    return out


_NOMBRE = {"update": "actualizaciones.o.update", "repair": "actualizaciones.o.repair",
           "check": "actualizaciones.o.check"}


def _nombre(job):
    """El nombre de la acción tal como se ve en el menú (actualizar · revisar
    y reparar · solo revisar), para el título de la caja."""
    k = _NOMBRE.get(job.get("modo"))
    return t(k) if k else job.get("label", "")


def render(S, w, h):
    K = _K()
    view = S.get("view", "menu")
    job = S.get("job")
    if view == "run" and job:
        titulo = t("actualizaciones.box.running", label=_nombre(job).upper())
        alto = 2 + min(len(job["steps"]), PASOS_VISIBLES) + 2 + 2
        L = SB.frame(K, w, h, word(), titulo, lambda iw: _cuerpo_run(S, K, iw), _chips(S),
                     msg=job.get("aviso") or S.get("msg", ""), box_w=BOX_W,
                     stable_rows=alto)
    elif view == "done" and job:
        titulo = t("actualizaciones.box.result", label=_nombre(job).upper())
        L = SB.frame(K, w, h, word(), titulo, lambda iw: _cuerpo_done(S, K, iw), _chips(S),
                     msg=S.get("msg", ""), box_w=BOX_W, scroll=S.get("scroll", 0))
        S["scroll"] = max(0, min(S.get("scroll", 0), SB.frame.last_max_scroll))
    else:
        L = _render_menu(S, K, w, h)
    # SIEMPRE h-1 líneas: cambiar de vista jamás deja residuos en pantalla
    L = [HL.clip(x, w - 1) for x in L[:h - 1]]
    L += [""] * max(0, (h - 1) - len(L))
    return L


# ── acciones + transición de estados ────────────────────────────────────────
def _tick(S):
    """Mantenimiento por ciclo (sin tecla): job terminado → vista resultado;
    lo aprendido refresca el estado del menú. True si algo cambió."""
    job = S.get("job")
    if S.get("view") == "run" and job and job.get("done"):
        S["view"], S["scroll"] = "done", 0
        cf = job.get("chk_final")
        if cf:
            S["chk"] = dict(cf, state="done")
        elif job["modo"] == "update" and not job["error"] and job["pulled"]:
            lb, st, _tx = job["pulled"][0]        # WORKSPACE va primero
            if st in ("ok", "fixed"):
                S["chk"] = {"state": "done", "ok": True, "behind": 0,
                            "branch": "", "commits": []}
        return True
    return False


def _busy(S):
    return S.get("view") == "run" or \
        (S.get("chk") or {}).get("state") == "busy"


def _accion(S, key):
    """True = sigue · False = salir de la pantalla."""
    view = S.get("view", "menu")
    if view == "run":
        job = S.get("job") or {}
        if key in ("q", "Q", "\x1b"):
            if not job.get("cancel"):
                job["cancel"] = True
                S["msg"] = t("actualizaciones.msg.cancelling")
            return True
        if key == "\x03":                        # Ctrl-C: salida dura
            job["cancel"] = True
            old = job.get("_oldio")
            if old and not job.get("done"):
                try:
                    sys.stdout, sys.stderr, sys.stdin = old
                except Exception:
                    pass
            S["tok"] = None
            return False
        return True
    if view == "done":
        if key == "up":
            S["scroll"] = max(0, S.get("scroll", 0) - 1)
        elif key == "down":
            S["scroll"] = S.get("scroll", 0) + 1
        elif key in ("q", "Q", "\x1b", "\x03", "\r", "\n"):
            job = S.get("job") or {}
            npend = len(_pendientes(job)) if job else 0
            S["view"], S["job"], S["scroll"] = "menu", None, 0
            lbl = job.get("label", t("actualizaciones.msg.done_fallback"))
            S["msg"] = t("actualizaciones.msg.done_pending", label=lbl,
                         n=npend) if npend else \
                t("actualizaciones.msg.done_ok", label=lbl)
        return True
    # — menú —
    if S.get("confirm"):
        if key in ("\r", "\n"):
            return _vuelve_atras(S)
        S["confirm"] = None
        S["msg"] = t("actualizaciones.msg.rollback_cancel")
        return True
    if SB.info_key(S, key):
        return True
    S["msg"] = ""
    if key in ("q", "Q", "\x1b", "\x03"):
        S["tok"] = None
        return False
    ops = _opciones(S)
    si = _elegida(S, ops)
    if key in ("up", "down"):
        si = (si + (-1 if key == "up" else 1)) % len(ops)
        S["si"], S["sel"], S["moved"] = si, ops[si][0], True
    elif key in ("a", "A"):
        _cicla_modo_auto(S)
    elif key in tuple("123"):        # los atajos de siempre (ya no se anuncian)
        return _corre(S, ACCIONES[int(key) - 1][0])
    elif key in ("\r", "\n", " "):
        tok = ops[si][0]
        if tok == "auto":
            _cicla_modo_auto(S)
        elif tok == "recheck":
            S["chk"] = None
            _lanza_chk(S)
        elif tok == "rollback":
            S["confirm"] = "rollback"
        else:
            return _corre(S, tok)
    return True


def _corre(S, tok):
    """Arranca revisar/reparar/actualizar AQUÍ; si no se puede, front lo
    corre por el camino clásico de terminal."""
    if _inicia_job(S, tok) == "fallback":
        S["tok"] = tok
        return False
    return True


def _vuelve_atras(S):
    """Segundo Enter sobre «volver a vX»: el mismo motor que
    `workspace update --rollback` (deja fija la versión anterior). Al salir
    de la pantalla, el hub se reabre con ella (front._code_stamp)."""
    S["confirm"] = None
    try:
        import updater
        out = updater.rollback(ROOT)
        reason = out.get("reason") or ""
        txt = updater.reason_text(reason) if reason in updater.REASONS else reason
    except Exception as e:
        out, txt = {"ok": False}, type(e).__name__
    if out.get("ok"):
        S["msg"] = t("actualizaciones.msg.rollback_ok",
                     v=out.get("to_version") or (out.get("to") or "")[:7])
        S["rb"], S["sel"] = None, None
        S["chk"] = None
        _lanza_chk(S)
    else:
        S["msg"] = t("actualizaciones.msg.rollback_fail", reason=txt or "?")
    return True


import responsive_ui as _responsive
render = _responsive.renderer(render, 'ACTUALIZACIONES')
_accion = _responsive.action(_accion)

def _draw(tout, S, first=False):
    w, h = _size()
    try:
        _responsive.paint(tout, render(S, w, h), first=first)
    except Exception:
        pass


def _run_unix(S):
    import select
    import termios
    import tty
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        tout = open("/dev/tty", "w")
    except Exception:
        return None
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h\033[?25l")
        _draw(tout, S, first=True)
        prev_busy = True
        while True:
            busy = _busy(S)
            ready = select.select([fd], [], [], 0.12 if busy else 0.5)[0]
            cambio = _tick(S)
            if not ready:
                _draw(tout, S)
                prev_busy = busy
                continue
            prev_busy = busy
            ch = os.read(fd, 1).decode("utf-8", "replace")
            key = ch
            if ch == "\x1b":
                if select.select([fd], [], [], 0.05)[0]:
                    seq = os.read(fd, 2).decode("utf-8", "replace")
                    key = {"[A": "up", "[B": "down", "[C": "down",
                           "[D": "up"}.get(seq, "\x1b")
                else:
                    key = "\x1b"
            if not _accion(S, key):
                break
            _draw(tout, S)
    finally:
        try:
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.close(fd)
        except Exception:
            pass
    return S.get("tok")


def _run_windows(S):
    import msvcrt
    tout = sys.stdout                    # referencia REAL: el worker captura
    tout.write("\033[?1049h\033[?25l")   # sys.stdout después, tout no cambia
    try:
        _draw(tout, S, first=True)
        last = 0.0
        while True:
            cambio = _tick(S)
            now = time.monotonic()
            if (cambio or _busy(S)) and now - last > 0.12:
                _draw(tout, S)
                last = now
            if not msvcrt.kbhit():
                time.sleep(0.1)
                _draw(tout, S)
                continue
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                a = msvcrt.getwch()
                key = {"H": "up", "P": "down", "M": "down",
                       "K": "up"}.get(a, "")
            else:
                key = ch
            if not key:
                continue
            if not _accion(S, key):
                break
            _draw(tout, S)
            last = time.monotonic()
    finally:
        try:
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
        except Exception:
            pass
    return S.get("tok")


@_theme_screen
def run(version_text=""):
    """Abre la pantalla. El flujo entero (revisar/reparar/actualizar) corre
    AQUÍ, en vivo. Devuelve None cuando todo se atendió (o el socio volvió),
    o el token "check"|"repair"|"update" SOLO si esta pantalla no puede
    correrlo (→ front cae al camino clásico de terminal, que sí promptea).
    Sin terminal interactiva → None (el caller ya tiene su camino seguro)."""
    S = {"view": "menu", "si": 0, "msg": "", "tok": None, "scroll": 0,
         "job": None, "chk": None, "rb": None,
         "version_text": version_text or ""}
    try:
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactivo = False
    if not interactivo:
        return None
    _lanza_chk(S)
    try:
        if os.name == "nt":
            return _run_windows(S)
        return _run_unix(S)
    except Exception:
        try:
            sys.stdout.write("\033[?25h\033[?1049l")
        except Exception:
            pass
        return None


if __name__ == "__main__":
    print(run() or "")
