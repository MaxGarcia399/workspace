#!/usr/bin/env python3
"""workflows.steps.integrate — wrap de `workspace integrate` (front.cmd_integrate).

El paso 7 de P1 tal cual ya existe: suite antes Y después del merge + guard
anti-trampa. No se reimplementa nada — se invoca el comando real y se lee su
código de salida. Import lazy (front carga dispatch/tema al importar).

IDEMPOTENTE (invariante v1.1 del runner): si la rama del run YA está
integrada en main (su tip es ancestro de main y no es el propio tip de main),
el paso es NO-OP en verde — re-correrlo tras un resume no re-mergea ni rompe.
El caso típico: el merge entró pero la suite post-merge falló → el paso quedó
FAIL → resume lo re-corre. La rama sale de los artefactos del run
(`branch`, lo deja worktree.acquire) o de `--param branch=…`; sin rama
conocida se corre el comando normal (git mismo trata un re-merge como
"already up to date").

Timeout: `front.cmd_integrate` corre in-process; sus subprocesos internos
(suite/git) llevan sus propios timeouts — el campo `timeout:` del spec NO
puede cortar este paso desde fuera (limitación documentada en MAPA.md)."""
import subprocess


def _git_rc(repo, args, timeout=30):
    """rc de un git informativo (solo lectura). Falla-suave → rc≠0."""
    try:
        r = subprocess.run(["git", "-C", repo] + list(args),
                           capture_output=True, timeout=timeout)
        return r.returncode
    except Exception:
        return 1


def _already_merged(repo, branch):
    """¿El tip de `branch` ya está contenido en main SIN ser el tip de main?
    - ancestro de main y tips distintos → el merge YA entró (no-op seguro).
    - tips iguales (rama recién creada u hoja de un ff) → NO se declara no-op:
      correr integrate ahí es inocuo (git: already up to date) y conserva los
      gates de suite — no enmascara un build que no commiteó nada."""
    if not branch or branch == "main":
        return False
    if _git_rc(repo, ["rev-parse", "--verify", "--quiet",
                      "refs/heads/%s" % branch]) != 0:
        return False
    if _git_rc(repo, ["merge-base", "--is-ancestor", branch, "main"]) != 0:
        return False
    # tips distintos = hubo merge real; iguales = nada nuevo que integrar
    return _tips_differ(repo, branch)


def _tips_differ(repo, branch):
    try:
        r1 = subprocess.run(["git", "-C", repo, "rev-parse", branch],
                            capture_output=True, timeout=30)
        r2 = subprocess.run(["git", "-C", repo, "rev-parse", "main"],
                            capture_output=True, timeout=30)
        return (r1.returncode == 0 and r2.returncode == 0
                and r1.stdout.strip() != r2.stdout.strip())
    except Exception:
        return False


def run(ctx, step):
    """Paso det: integra la rama del run a main vía el comando existente.
    Idempotente: rama ya integrada → no-op verde (ver cabecera)."""
    args = [str(a) for a in (step.get("args") or [])]
    if ctx.get("dry"):
        return {"ok": True, "detail": "dry: $ workspace integrate %s"
                % (" ".join(args) or "(sin flags)")}
    repo = ctx.get("repo")
    branch = ((ctx.get("artifacts") or {}).get("branch")
              or (ctx.get("params") or {}).get("branch"))
    if repo and branch and _already_merged(repo, branch):
        return {"ok": True,
                "detail": "idempotente: la rama `%s` ya está integrada en "
                          "main — no-op (re-corrida segura)" % branch,
                "artifacts": {"integrate_rc": 0, "integrate_noop": True}}
    import front
    rc = front.cmd_integrate(args)
    return {"ok": rc == 0, "detail": "workspace integrate → rc=%s" % rc,
            "artifacts": {"integrate_rc": rc}}
