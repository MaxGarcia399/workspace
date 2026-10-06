#!/usr/bin/env python3
"""WORKSPACE · actualizaciones_tui — la pantalla «Actualizaciones» del hub.

CONSOLIDACIÓN (pedido del socio 2026-10-02): antes la pantalla solo ELEGÍA la
acción y el doctor/update se volcaban crudos a la terminal. Ahora TODO el
flujo vive aquí, en la misma vista del hub (patrón tono_tui/calendario_tui:
wordmark + reflejo, paleta del TEMA activo, cajas `full_box`, cursor `❯`,
statusline al pie), con tres estados:

  · MENÚ      — tres acciones, una por fila; el panel derecho explica QUÉ
                hace cada una y qué comando equivale. Al abrir, un hilo de
                fondo consulta si hay actualización (sin bloquear nada).
  · EN VIVO   — la acción corre AQUÍ: caja izquierda = cada paso con su
                estado (· pendiente / ● corriendo / ✓ / ⚠ / ✗), caja derecha
                = progreso (slider del tema) + el detalle de lo que va
                pasando. Nada de texto crudo de git/doctor volcado.
  · RESULTADO — veredicto + conteos + QUÉ LLEGÓ (commits jalados) +
                pendientes con su acción sugerida (↑↓ para desplazar).

El motor NO cambió: las fases son las de `doctor.py` (devuelven hallazgos
estructurados — por eso se pueden pintar bonito) y los pulls replican la
clasificación de `front.cmd_update`. El runner corre en un hilo daemon con
stdout/stderr/stdin capturados (nada imprime sobre la pantalla); cancelar
con q espera a que termine el paso en curso (fail-soft: jamás deja la
terminal rota ni el update a medias sin avisar).

CONTRATO con front._doctor_submenu: run() devuelve None cuando todo se
atendió aquí (o el socio volvió), y devuelve el token "check"|"repair"|
"update" SOLO cuando esta pantalla no puede correr el flujo (p. ej. el modo
reparar necesitaría preguntar quién eres) → front cae al camino clásico de
terminal, que sí promptea. Sin TTY el caller ni nos llama.

Teclas:  MENÚ ↑↓ · Enter · 1-3 · q   |   EN VIVO q cancela al fin del paso
         RESULTADO ↑↓ desplaza · Enter/q vuelve al menú

Misma fórmula de pantalla que tono_tui (2J3JH al entrar, H + \\033[K por
línea después — nunca 2J a media sesión; el render SIEMPRE devuelve h-1
líneas, así cambiar de estado no deja residuos) y los dos drivers de
teclado: termios+select en Unix, msvcrt en Windows.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import io
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import hublayout as HL                                          # noqa: E402
import i18n                                                      # noqa: E402

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

LETRA_CHICA = (
    "actualizaciones.fine.1",
    "actualizaciones.fine.2",
    "actualizaciones.fine.3",
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


def _divisor(K, txt, w, tono=-1):
    """`titulo ────` — el gesto de encabezado del Tono: versalita + regla
    tenue. `tono` ≥ 0 la pinta en ese paso del gradiente; -1 = apagada."""
    col = (K["WCOL"][tono % len(K["WCOL"])] + K["BO"]) if tono >= 0 \
        else K["DK"]
    regla = K["SEP"] * max(1, w - HL.vis(txt) - 2)
    return HL.clip("%s%s%s %s%s%s" % (col, str(txt), K["R"], K["DK"], regla,
                                      K["R"]), w)


def _version():
    try:
        return open(os.path.join(ROOT, "VERSION"),
                    encoding="utf-8").read().strip()
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
        commits = []
        if behind > 0:
            rc, log, _ = _gitq(ROOT, "log", "--format=%h\x1f%s", "-30",
                               "HEAD..origin/%s" % branch, timeout=10)
            if rc == 0:
                commits = [tuple(ln.split("\x1f", 1))
                           for ln in log.splitlines() if "\x1f" in ln]
        return {"ok": True, "behind": behind, "branch": branch,
                "commits": commits}
    except Exception as e:
        return {"ok": False, "reason": "%s" % type(e).__name__}


def _lanza_chk(S):
    """Chequeo de update en 2º plano al abrir el menú (no bloquea nada)."""
    if (S.get("chk") or {}).get("state") == "busy":
        return
    S["chk"] = {"state": "busy"}

    def _w():
        info = _update_info()
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
        # el fix puede necesitar preguntar «¿quién eres?» (socio.local): esa
        # conversación es de la terminal clásica, no de esta pantalla
        if fix and not doctor._get_socio(ctx, fix=False):
            return "fallback"
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
        finds = [doctor.f(doctor.FAIL, "error interno de la fase",
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


def _paso_pull(job, i, paso):
    """Pull --ff-only de UN repo en su rama actual — misma clasificación que
    front._update_repo, pero estructurada para pintarse en la pantalla."""
    _, label, path, transport = paso
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


# UNA fuente de verdad de los atajos POR VISTA: la cabecera enseña los
# clave + salir (HL.top_hints recorta) y el pie la lista completa. Son
# FUNCIONES (no constantes) para resolver t() en cada render → el idioma
# flipea en vivo.
def PARES_MENU():
    return (("↑↓", t("actualizaciones.hint.action")),
            ("Enter", t("actualizaciones.hint.run")),
            ("1-3", t("actualizaciones.hint.direct")),
            ("q", t("actualizaciones.hint.back_menu")))


def PARES_RUN():
    return (("q", t("actualizaciones.hint.cancel_run")),)


def PARES_DONE():
    return (("↑↓", t("actualizaciones.hint.scroll_pending")),
            (t("actualizaciones.hint.enter_q"),
             t("actualizaciones.hint.back_menu")))


def _marco(S, K, w, h, sub, hints=None):
    """Wordmark + reflejo + subtítulo + atajos clave + regla — el
    encabezado común (HL.screen_header, compartido con todo el hub)."""
    return HL.screen_header(K, w, h, sub, hints=hints)


def _linea_chk(S, K, iw):
    """El estado del chequeo de updates, para la caja de estado del menú."""
    chk = S.get("chk") or {}
    if chk.get("state") == "busy":
        return HL.clip(" %s %s%s%s"
                       % (_icono(K, "run"), K["DIM"],
                          t("actualizaciones.chk.searching"), K["R"]), iw)
    if chk.get("state") == "done" and chk.get("ok"):
        n = chk.get("behind", 0)
        if n > 0:
            return HL.clip(" %s%s%s%s"
                           % (K["B"], K["BO"],
                              t("actualizaciones.chk.new", n=n,
                                s="s" if n != 1 else ""), K["R"]), iw)
        return HL.clip(" %s%s%s %s%s%s"
                       % (K["OK"], t("actualizaciones.chk.uptodate"), K["R"],
                          K["DK"],
                          t("actualizaciones.chk.branch",
                            branch=chk.get("branch", "?")), K["R"]), iw)
    if chk.get("state") == "done":
        return HL.clip(" %s%s%s"
                       % (K["DK"], t("actualizaciones.chk.unverified",
                                     reason=chk.get("reason", "?")), K["R"]),
                       iw)
    return HL.clip(" %s—%s" % (K["DK"], K["R"]), iw)


# ── vista MENÚ ──────────────────────────────────────────────────────────────
def _cuerpo_acciones(S, K, iw):
    """Caja izquierda: las tres acciones + estado (versión y updates)."""
    wc = K["WCOL"]
    out = []
    for i, (_tok, lblk, tagk, _desc, _cmd) in enumerate(ACCIONES):
        sel = (i == S["si"])
        rec = (_tok == "update")          # la acción recomendada (estilo)
        cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
        lcol = (wc[i % len(wc)] + K["BO"]) if sel else K["INACTIVE"]
        num = "%s%d%s" % ((K["WH"] + K["BO"]) if sel else K["DK"], i + 1,
                          K["R"])
        lab = "%s%s%s" % (lcol, HL.pad(t(lblk), 18), K["R"])
        tcol = (K["B2"] if rec else K["DK"]) if not sel \
            else (K["B"] + K["BO"] if rec else K["GREY"])
        out.append(HL.clip(" %s %s %s %s%s%s" % (cur, num, lab, tcol, t(tagk),
                                                 K["R"]), iw))
    out.append("")
    out.append(_divisor(K, t("actualizaciones.sec.state"), iw))
    v = _version()
    est = " · ".join(p for p in (("v" + v) if v else "",
                                 S.get("version_text") or "") if p)
    out.append(HL.clip(" %s%s%s" % (K["GREY"],
                                    est or t("actualizaciones.ver.unavailable"),
                                    K["R"]), iw))
    out.append(_linea_chk(S, K, iw))
    return out


def _cuerpo_detalle(S, K, iw, full=True):
    """Caja derecha — TRANSPARENCIA de la acción elegida: qué hace, que corre
    aquí mismo (y su equivalente de terminal) y la letra chica."""
    _tok, lblk, _tag, desc, cmd = ACCIONES[S["si"]]
    out = []
    for ln in desc:
        for sub in _wrap(t(ln), max(8, iw - 3)):
            out.append(HL.clip(" %s%s%s" % (K["GREY"], sub, K["R"]), iw))
        out.append("")
    if out and not out[-1]:
        out.pop()
    out.append("")
    out.append(_divisor(K, t("actualizaciones.sec.on_confirm"), iw, tono=3))
    out.append(HL.clip(" %s%s%s"
                       % (K["WH"], t("actualizaciones.detail.runs_here"),
                          K["R"]), iw))
    out.append(HL.clip(" %s%s%s%s%s%s"
                       % (K["DIM"], t("actualizaciones.detail.equiv"), K["R"],
                          K["OK"], cmd, K["R"]), iw))
    if not full:
        return out
    out.append("")
    out.append(_divisor(K, t("actualizaciones.sec.how"), iw, tono=4))
    for ln in LETRA_CHICA:
        for sub in _wrap(t(ln), max(8, iw - 4)):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  sub, K["R"]), iw))
    return out


def _render_menu(S, K, w, h):
    L = _marco(S, K, w, h, t("actualizaciones.sub.menu"),
               hints=PARES_MENU())
    top = len(L)
    apilado = w < 100
    lw = (w - 1) if apilado else max(34, min(44, (w - 6) * 42 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    avail = max(8, (h - 1) - top - 3)
    bi = _cuerpo_acciones(S, K, lw - 4)
    si0, full = S["si"], True
    # ALTURA ESTABLE: la caja derecha mide lo del detalle MÁS LARGO de las 3
    for full_try in (True, False):
        full = full_try
        altos = []
        for i in range(len(ACCIONES)):
            S["si"] = i
            altos.append(len(_cuerpo_detalle(S, K, rw - 4, full=full)))
        S["si"] = si0
        ih = max(len(bi), max(altos))
        need = (len(bi) + ih + 4) if apilado else (ih + 2)
        if need <= avail:
            break
    bd = _cuerpo_detalle(S, K, rw - 4, full=full)
    t_izq = t("actualizaciones.box.left")
    t_der = t("actualizaciones.box.what", label=t(ACCIONES[S["si"]][1]))
    if apilado:
        ih_d = max(3, min(ih, avail - (len(bi) + 2) - 2))
        for ln in HL.full_box(t_izq, bi, K, lw - 1, len(bi), True,
                              border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
        for ln in HL.full_box(t_der, bd, K, rw - 1, ih_d, False,
                              border=K["B2"], label=K["B"] + K["BO"]):
            L.append(HL.clip(" " + ln, w - 1))
    else:
        ih = min(ih, avail - 2)
        izq = HL.full_box(t_izq, bi, K, lw, ih, True, border=K["C"])
        der = HL.full_box(t_der, bd, K, rw, ih, False, border=K["B2"],
                          label=K["B"] + K["BO"])
        for i in range(ih + 2):
            L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "", lw)
                             + "  " + (der[i] if i < len(der) else ""),
                             w - 1))
    L.append("")
    L.append(" %s%s%s" % (K["B2"], S.get("msg") or "", K["R"])
             if S.get("msg") else "")
    L.append(HL.foot_hints(K, PARES_MENU(), w))
    return L


# ── vista EN VIVO ───────────────────────────────────────────────────────────
def _cuerpo_pasos(S, K, iw, ih):
    """Caja izquierda: CADA paso con su estado. Si no caben, ventana centrada
    en el paso actual con marcadores «↑ n antes / ↓ n más»."""
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
        out.append(HL.clip(" %s%s%s"
                           % (K["DK"],
                              t("actualizaciones.steps.before", n=start),
                              K["R"]), iw))
    for i in range(start, min(fin, n)):
        st = steps[i]
        icon = _icono(K, st["st"])
        note = st.get("note") or ""
        lcol = (K["WH"] + K["BO"]) if st["st"] == "run" else \
            (K["DK"] if st["st"] in ("pend", "skip") else K["GREY"])
        if note:
            lab = HL.pad(st["label"], max(8, iw - 5 - HL.vis(note)))
            ncol = {"warn": K["B"], "fail": K["ERR"],
                    "fixed": K["C"]}.get(st["st"], K["DK"])
            out.append(HL.clip(" %s %s%s%s %s%s%s"
                               % (icon, lcol, lab, K["R"], ncol, note,
                                  K["R"]), iw))
        else:
            out.append(HL.clip(" %s %s%s%s"
                               % (icon, lcol, st["label"], K["R"]), iw))
    if fin < n:
        out.append(HL.clip(" %s%s%s"
                           % (K["DK"],
                              t("actualizaciones.steps.after", n=n - fin),
                              K["R"]), iw))
    return out


def _cuerpo_vivo(S, K, iw, ih):
    """Caja derecha EN VIVO: progreso (slider del tema) + lo último que pasó."""
    job = S["job"]
    total = len(job["steps"])
    hechos = sum(1 for s in job["steps"]
                 if s["st"] not in ("pend", "run"))
    cur = job["steps"][job["cur"]]["label"] if 0 <= job["cur"] < total else ""
    out = [_divisor(K, t("actualizaciones.sec.progress"), iw, tono=2)]
    out.append(HL.clip(" %s  %s%d/%d%s" % (
        _progreso(K, hechos, total, max(6, iw - 12)),
        K["WH"] + K["BO"], hechos, total, K["R"]), iw))
    out.append(HL.clip(" %s %s%s%s"
                       % (_icono(K, "run"), K["DIM"],
                          cur or t("actualizaciones.live.preparing"),
                          K["R"]), iw))
    # degradación honesta: con alto de sobra, sección «lo último»; apretado,
    # las líneas vivas directas; sin espacio, solo el progreso
    resto = ih - len(out)
    if resto >= 3:
        out.append("")
        out.append(_divisor(K, t("actualizaciones.sec.latest"), iw))
        quedan = ih - len(out)
    else:
        quedan = max(0, resto)
    vivos = job["live"][-quedan:] if quedan else []
    for st, txt in vivos:
        col, ch = _ICO.get(st, ("DK", "·"))
        for sub in _wrap(txt, max(8, iw - 4))[:1]:
            out.append(HL.clip(" %s%s%s %s%s%s"
                               % (K[col], ch, K["R"], K["DIM"], sub, K["R"]),
                               iw))
    if quedan and not vivos:
        out.append(HL.clip(" %s%s%s"
                           % (K["DK"], t("actualizaciones.live.starting"),
                              K["R"]), iw))
    return out


def _render_run(S, K, w, h):
    job = S["job"]
    L = _marco(S, K, w, h,
               t("actualizaciones.sub.run", label=job["label"]),
               hints=PARES_RUN())
    top = len(L)
    apilado = w < 100
    lw = (w - 1) if apilado else max(36, min(52, (w - 6) * 46 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    avail = max(8, (h - 1) - top - 3)
    if apilado:
        ih_i = max(4, min(len(job["steps"]), (avail - 4) * 55 // 100))
        ih_d = max(3, avail - ih_i - 4)
    else:
        ih_i = ih_d = max(4, avail - 2)
    bi = _cuerpo_pasos(S, K, lw - 4, ih_i)
    bd = _cuerpo_vivo(S, K, rw - 4, ih_d)
    t_izq = t("actualizaciones.box.steps", label=job["label"])
    t_der = t("actualizaciones.box.live")
    if apilado:
        for ln in HL.full_box(t_izq, bi, K, lw - 1, ih_i, True,
                              border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
        for ln in HL.full_box(t_der, bd, K, rw - 1, ih_d, False,
                              border=K["B2"], label=K["B"] + K["BO"]):
            L.append(HL.clip(" " + ln, w - 1))
    else:
        izq = HL.full_box(t_izq, bi, K, lw, ih_i, True, border=K["C"])
        der = HL.full_box(t_der, bd, K, rw, ih_d, False, border=K["B2"],
                          label=K["B"] + K["BO"])
        for i in range(ih_i + 2):
            L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "", lw)
                             + "  " + (der[i] if i < len(der) else ""),
                             w - 1))
    L.append("")
    el = _mmss(time.monotonic() - job["t0"])
    msg = job["aviso"] or S.get("msg") or ""
    estado = "%s⏱ %s%s" % (K["GREY"], el, K["R"]) \
        + (("   %s%s%s" % (K["B"], msg, K["R"])) if msg else "")
    L.append(" " + estado)
    L.append(HL.clip(" %s%s%s %s·%s "
                     % (K["DIM"], t("actualizaciones.run.steps_auto"), K["R"],
                        K["DK"], K["R"])
                     + HL.keyline(K, PARES_RUN(), max(10, w - 30)), w - 1))
    return L


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


def _cuerpo_resumen(S, K, iw):
    job = S["job"]
    col, txt = _veredicto(job, K)
    out = [HL.clip(" %s%s%s" % (col, txt, K["R"]), iw)]
    n = {s: sum(1 for st in job["steps"] if st["st"] == s)
         for s in ("ok", "fixed", "warn", "fail", "skip")}
    linea = " %s%d ✓%s · %s%d %s%s · %s%d ⚠%s · %s%d ✗%s" % (
        K["OK"], n["ok"], K["R"], K["C"], n["fixed"],
        t("actualizaciones.sum.fixed_word"), K["R"],
        K["B"], n["warn"], K["R"], K["ERR"], n["fail"], K["R"])
    out.append(HL.clip(linea, iw))
    dur = _mmss((job["t1"] or time.monotonic()) - job["t0"])
    out.append(HL.clip(" %s%s%s"
                       % (K["DK"],
                          t("actualizaciones.sum.duration", dur=dur,
                            n=len(job["steps"])), K["R"]), iw))
    out.append("")
    if job["modo"] == "update":
        out.append(_divisor(K, t("actualizaciones.sec.arrived"), iw, tono=3))
        if job["n_new"]:
            out.append(HL.clip(" %s%s%s"
                               % (K["WH"] + K["BO"],
                                  t("actualizaciones.sum.ws_new",
                                    n=job["n_new"]), K["R"]), iw))
            for sha, subj in job["new_commits"][:5]:
                out.append(HL.clip("  %s%s%s %s%s%s"
                                   % (K["C"], sha, K["R"], K["DIM"],
                                      subj, K["R"]), iw))
            resto = job["n_new"] - min(5, len(job["new_commits"]))
            if resto > 0:
                out.append(HL.clip("  %s%s%s"
                                   % (K["DK"],
                                      t("actualizaciones.sum.more", n=resto),
                                      K["R"]), iw))
        else:
            out.append(HL.clip(" %s%s%s"
                               % (K["GREY"],
                                  t("actualizaciones.sum.nothing_new"),
                                  K["R"]), iw))
        otros = [(lb, st, tx) for lb, st, tx in job["pulled"]
                 if lb != "WORKSPACE"]
        for lb, st, tx in otros[:4]:
            colb, ch = _ICO.get(st, ("DK", "·"))
            out.append(HL.clip(" %s%s%s %s%s: %s%s"
                               % (K[colb], ch, K["R"], K["DIM"], lb, tx,
                                  K["R"]), iw))
    else:
        out.append(_divisor(K, t("actualizaciones.sec.update"), iw, tono=3))
        cf = job.get("chk_final") or {}
        if cf.get("ok") and cf.get("behind", 0) > 0:
            out.append(HL.clip(" %s%s%s%s"
                               % (K["B"], K["BO"],
                                  t("actualizaciones.sum.available",
                                    n=cf["behind"]), K["R"]), iw))
            for sha, subj in (cf.get("commits") or [])[:3]:
                out.append(HL.clip("  %s%s%s %s%s%s"
                                   % (K["C"], sha, K["R"], K["DIM"], subj,
                                      K["R"]), iw))
        elif cf.get("ok"):
            out.append(HL.clip(" %s%s%s"
                               % (K["OK"],
                                  t("actualizaciones.sum.uptodate",
                                    branch=cf.get("branch", "?")), K["R"]),
                               iw))
        else:
            out.append(HL.clip(" %s%s%s"
                               % (K["DK"],
                                  t("actualizaciones.sum.cannot_verify",
                                    reason=cf.get("reason")
                                    or t("actualizaciones.reason.no_data")),
                                  K["R"]), iw))
    out.append("")
    out.append(_divisor(K, t("actualizaciones.sec.next"), iw))
    if _pendientes(job):
        for sub in _wrap(t("actualizaciones.sum.next_pending"), iw - 3):
            out.append(HL.clip(" %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    else:
        out.append(HL.clip(" %s%s%s"
                           % (K["GREY"], t("actualizaciones.sum.next_clear"),
                              K["R"]), iw))
    return out


def _lineas_pendientes(job, K, iw):
    """Las líneas (ya coloreadas) del panel de pendientes, para desplazar."""
    pend = _pendientes(job)
    if job["error"]:
        out = [HL.clip(" %s✗ %s%s" % (K["ERR"], job["error"], K["R"]), iw)]
        out.append(HL.clip(" %s%s%s"
                           % (K["DIM"], t("actualizaciones.pend.error_cmd"),
                              K["R"]), iw))
        return out
    if not pend:
        return [HL.clip(" %s%s%s"
                        % (K["OK"], t("actualizaciones.pend.none"), K["R"]),
                        iw)]
    out = []
    for titulo, x in pend:
        sym = ("%s✗%s" % (K["ERR"], K["R"])) if x["status"] == "fail" \
            else ("%s⚠%s" % (K["B"], K["R"]))
        fase = str(titulo).split("·")[0].strip()
        out.append(HL.clip(" %s %s[f%s]%s %s%s%s"
                           % (sym, K["DK"], fase, K["R"],
                              K["WH"], x["label"], K["R"]), iw))
        if x.get("detail"):
            for sub in _wrap(x["detail"], max(8, iw - 5))[:2]:
                out.append(HL.clip("    %s%s%s" % (K["DIM"], sub, K["R"]),
                                   iw))
        if x.get("action"):
            lineas = _wrap(x["action"], max(8, iw - 7))
            out.append(HL.clip("    %s→%s %s%s%s"
                               % (K["B"], K["R"], K["GREY"], lineas[0],
                                  K["R"]), iw))
            for sub in lineas[1:3]:
                out.append(HL.clip("      %s%s%s" % (K["GREY"], sub, K["R"]),
                                   iw))
        out.append("")
    if out and not out[-1]:
        out.pop()
    return out


def _render_done(S, K, w, h):
    job = S["job"]
    L = _marco(S, K, w, h,
               t("actualizaciones.sub.done", label=job["label"]),
               hints=PARES_DONE())
    top = len(L)
    apilado = w < 100
    lw = (w - 1) if apilado else max(36, min(52, (w - 6) * 46 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    avail = max(8, (h - 1) - top - 3)
    bi = _cuerpo_resumen(S, K, lw - 4)
    pend_all = _lineas_pendientes(job, K, rw - 4)
    if apilado:
        ih_i = max(4, min(len(bi), (avail - 4) * 55 // 100))
        ih_d = max(3, avail - ih_i - 4)
    else:
        ih_i = ih_d = max(4, avail - 2)
    # desplazamiento del panel de pendientes (↑↓)
    maxs = max(0, len(pend_all) - ih_d)
    S["scroll"] = max(0, min(S.get("scroll", 0), maxs))
    vista = pend_all[S["scroll"]:S["scroll"] + ih_d]
    if maxs and S["scroll"] < maxs and vista:
        vista[-1] = HL.clip(" %s%s%s"
                            % (K["DK"],
                               t("actualizaciones.pend.more",
                                 n=maxs - S["scroll"]), K["R"]), rw - 4)
    npend = len(_pendientes(job))
    t_izq = t("actualizaciones.box.summary", label=job["label"])
    t_der = t("actualizaciones.box.pending_n", n=npend) if npend \
        else t("actualizaciones.box.pending")
    if apilado:
        for ln in HL.full_box(t_izq, bi, K, lw - 1, ih_i, True,
                              border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
        for ln in HL.full_box(t_der, vista, K, rw - 1, ih_d, False,
                              border=K["B2"], label=K["B"] + K["BO"]):
            L.append(HL.clip(" " + ln, w - 1))
    else:
        izq = HL.full_box(t_izq, bi, K, lw, ih_i, True, border=K["C"])
        der = HL.full_box(t_der, vista, K, rw, ih_d, False, border=K["B2"],
                          label=K["B"] + K["BO"])
        for i in range(ih_i + 2):
            L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "", lw)
                             + "  " + (der[i] if i < len(der) else ""),
                             w - 1))
    L.append("")
    L.append(" %s%s%s" % (K["B2"], S.get("msg") or "", K["R"])
             if S.get("msg") else "")
    L.append(HL.foot_hints(K, PARES_DONE(), w))
    return L


def render(S, w, h):
    K = _K()
    view = S.get("view", "menu")
    if view == "run" and S.get("job"):
        L = _render_run(S, K, w, h)
    elif view == "done" and S.get("job"):
        L = _render_done(S, K, w, h)
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
    S["msg"] = ""
    if key in ("q", "Q", "\x1b", "\x03"):
        S["tok"] = None
        return False
    if key == "up":
        S["si"] = (S["si"] - 1) % len(ACCIONES)
    elif key == "down":
        S["si"] = (S["si"] + 1) % len(ACCIONES)
    elif key in tuple("123") or key in ("\r", "\n"):
        if key in tuple("123"):
            S["si"] = int(key) - 1
        tok = ACCIONES[S["si"]][0]
        if _inicia_job(S, tok) == "fallback":
            S["tok"] = tok                       # front corre el camino clásico
            return False
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


def run(version_text=""):
    """Abre la pantalla. El flujo entero (revisar/reparar/actualizar) corre
    AQUÍ, en vivo. Devuelve None cuando todo se atendió (o el socio volvió),
    o el token "check"|"repair"|"update" SOLO si esta pantalla no puede
    correrlo (→ front cae al camino clásico de terminal, que sí promptea).
    Sin terminal interactiva → None (el caller ya tiene su camino seguro)."""
    S = {"view": "menu", "si": 2, "msg": "", "tok": None, "scroll": 0,
         "job": None, "chk": None,
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
