#!/usr/bin/env python3
"""workflows.steps.integrate — wrap de `workspace integrate` (front.cmd_integrate).

El paso 7 de P1 tal cual ya existe: suite antes Y después del merge + guard
anti-trampa. No se reimplementa nada — se invoca el comando real y se lee su
código de salida. Import lazy (front carga dispatch/tema al importar).

Integra SIEMPRE la rama DEL RUN (v1.6): la saca de los artefactos (`branch`,
lo deja worktree.acquire) o de `--param branch=…` y se la pasa EXPLÍCITA a
`cmd_integrate` — que la prueba en su worktree y la mergea en el checkout
principal (`ctx["root"]`), ya parado en main. Jamás la rama en la que esté
parado ese checkout: sin rama del run, el paso FALLA. Después COMPRUEBA que
esa rama quedó contenida en main (rc=0 solo no basta).

Sin verde por no hacer nada: el trabajo del run es lo que la rama trae y no
tienen ni main ni el main del que nació (`rama ^main ^branch_base`; rama
adoptada: `main..rama`) — no cuenta lo que vino DE main (fast-forward) ni
lo que main descartó mientras el run esperaba (rollback del update, amend,
reset, pull --rebase), que si no volvería a main. Antes del merge, ese tip se
guarda como EVIDENCIA de este run (`integrate_tip`): a disco en ese momento
(`ctx["checkpoint"]` del runner; si no se puede escribir, no hay merge) y
en los artefactos del resultado. Si la rama ya no trae nada, el paso solo
sigue si ESA evidencia —el commit exacto que este run llevó a su merge— ya
está en main. Nada más prueba nada: un merge ajeno en main (otra rama que
se puso al día con `git merge main`, un pull con merge) puede tener como
padre al tip de una rama vacía. Sin evidencia → FALLA: nada que integrar.

IDEMPOTENTE (invariante v1.1 del runner) SIN atajos: si la rama ya está en
main (el merge entró pero la suite post-merge falló → el paso quedó FAIL →
resume lo re-corre), se vuelve a llamar al comando: git no mergea nada
("already up to date") y las DOS suites corren otra vez — el verde sale de
la suite de ahora, jamás de un no-op. `integrate_noop` solo avisa que el
merge ya estaba. Vale para ramas adoptadas y tras un corte a media suite.

Timeout: `front.cmd_integrate` corre in-process; sus subprocesos internos
(suite/git) llevan sus propios timeouts — el campo `timeout:` del spec NO
puede cortar este paso desde fuera (limitación documentada en MAPA.md)."""
import re as _re
import subprocess


def _git(repo, args, timeout=30):
    """(rc, stdout) de un git informativo (solo lectura). Falla-suave → rc≠0."""
    try:
        r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        return r.returncode, (r.stdout or "").strip()
    except Exception:
        return 1, ""


def _tip(repo, branch):
    """sha del tip de `branch` (rama local) o "" si no existe."""
    rc, out = _git(repo, ["rev-parse", "--verify", "--quiet",
                          "refs/heads/%s^{commit}" % branch])
    return out if rc == 0 else ""


def _in_main(repo, sha):
    """¿El commit `sha` ya está contenido en main?"""
    return _git(repo, ["merge-base", "--is-ancestor", sha, "main"])[0] == 0


def _pending(repo, tip, base=""):
    """Commits del RUN que main todavía NO tiene: lo que trae `tip` y no está
    ni en main ni en el main del que nació la rama (`base` = branch_base).
    Así no cuenta lo que vino DE main (fast-forward) ni lo que main descartó
    mientras el run esperaba (rollback del update, amend, reset, pull
    --rebase: el tip de una corrida vacía sale de main, pero sigue siendo su
    base). Rama adoptada (sin base) o base que no resuelve → `main..tip`.
    None si git falla."""
    args = ["rev-list", "--count", tip, "^main"]
    if (_re.match(r"[0-9a-f]{7,64}\Z", base or "") and
            _git(repo, ["rev-parse", "--verify", "--quiet",
                        "%s^{commit}" % base])[0] == 0):
        args.append("^" + base)
    rc, out = _git(repo, args)
    try:
        return int(out) if rc == 0 else None
    except ValueError:
        return None


def _fail(detail):
    # permanente: re-intentar tal cual no crea los commits ni la rama que faltan
    return {"ok": False, "detail": detail, "retriable": False}


def run(ctx, step):
    """Paso det: integra la rama DEL RUN a main vía el comando existente."""
    args = [str(a) for a in (step.get("args") or [])]
    arts = ctx.get("artifacts") or {}
    branch = str(arts.get("branch")
                 or (ctx.get("params") or {}).get("branch") or "").strip()
    if ctx.get("dry"):
        return {"ok": True, "detail": "dry: $ workspace integrate %s (rama del "
                "run: %s)" % (" ".join(args) or "(sin flags)",
                              "`%s`" % branch if branch else "ninguna")}
    # checkout principal (donde vive main): `root` del runner; las llamadas
    # directas (tests/consumidores viejos) solo traen `repo`.
    root = ctx.get("root") or ctx.get("repo")
    if not branch:
        return _fail("el run no tiene rama propia (ni artefacto `branch` de "
                     "worktree.acquire ni --param branch=…) — no integro la "
                     "rama en la que esté parado el checkout principal")
    if branch in ("main", "stable"):
        return _fail("la rama del run es `%s` — no es una rama de feature"
                     % branch)
    tip = _tip(root, branch)
    if not tip:
        return _fail("la rama del run `%s` no existe en %s — nada que integrar"
                     % (branch, root))
    pending = _pending(root, tip, str(arts.get("branch_base") or "").strip())
    if pending is None:
        return _fail("no pude contar los commits de `%s` que main no tiene — "
                     "no integro a ciegas" % branch)
    arts_out = {}
    if pending:
        # EVIDENCIA de ESTE run, a disco ANTES del merge: este tip trae trabajo
        # que main no tiene. Si el proceso muere a media suite, el resume la
        # ve; si no se puede guardar, el checkpoint levanta y no hay merge.
        arts_out["integrate_tip"] = tip
        checkpoint = ctx.get("checkpoint")
        if callable(checkpoint):
            checkpoint({"integrate_tip": tip})
    else:
        prev = str(arts.get("integrate_tip") or "").strip()
        if not (prev and _in_main(root, prev)):
            return _fail("la rama `%s` no trae commits que main no tenga y este "
                         "run no tiene registro de haberla integrado — nada que "
                         "integrar: sin verde sin integrar (¿el build no "
                         "commiteó? un merge hecho fuera del run no prueba que "
                         "el trabajo sea suyo)" % branch)
        arts_out["integrate_noop"] = True      # el merge ya estaba en main
    import front
    try:
        rc = front.cmd_integrate(args, branch=branch)
    except Exception as e:                     # la evidencia no se pierde
        return {"ok": False, "artifacts": arts_out,
                "detail": "workspace integrate reventó con la rama del run "
                          "`%s`: %s: %s" % (branch, type(e).__name__, e)}
    arts_out["integrate_rc"] = rc
    if rc != 0:
        return {"ok": False, "artifacts": arts_out,
                "detail": "workspace integrate de la rama del run `%s` → rc=%s "
                          "(suite roja, conflicto, o checkout principal fuera "
                          "de main / sucio — ver su salida)" % (branch, rc)}
    if not _in_main(root, tip):
        return {"ok": False, "artifacts": arts_out,
                "detail": "integrate devolvió rc=0 pero la rama del run `%s` "
                          "NO quedó contenida en main — no doy verde" % branch}
    return {"ok": True, "artifacts": arts_out,
            "detail": ("la rama del run `%s` ya estaba en main — merge no-op, "
                       "suites re-corridas VERDES (rc=0)" if not pending else
                       "rama del run `%s` integrada a main — suites antes y "
                       "después VERDES (rc=0)") % branch}
