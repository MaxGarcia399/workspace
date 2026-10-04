#!/usr/bin/env python3
"""workflows.steps.worktree — wrap de `dash/dev/_worktrees` (NO reinventa).

acquire: IDEMPOTENTE (invariante v1.1 del runner: re-correr un paso EFECTIVO
tras un resume debe ser no-op seguro). Si la rama/worktree del run YA existe,
la ADOPTA en vez de fallar: (1) entrada viva del registry de dueños,
(2) worktree existente en esa rama (`git worktree list --porcelain`),
(3) rama ya creada sin worktree → `worktree add` SIN `-b` (adjunta, no
re-crea). Solo si nada existe crea desde cero: pool tibio primero
(`pool_acquire` — ignorados intactos, reserva atómica) y si no,
`git worktree add -b` hermano del repo (misma convención de ruta que
front.cmd_worktree: `<repo>-trees/<slug>`), registrando al dueño.

release: barrido de `_worktrees.release(agent=…)` — hereda su regla de oro
(jamás remueve trabajo sin commitear, jamás --force). Idempotente por
construcción: un barrido sin nada que liberar es no-op.

La rama sale de params (`--param branch=…`) o del paso; default derivado del
run-id (única por run). Timeout de los `git worktree add`: `timeout:` del
paso o 120s.
"""
import os

_ADD_TIMEOUT = 120             # s para `git worktree add` (default sensato)


def _wt():
    from dash.dev import _worktrees
    return _worktrees


def _branch(ctx, step):
    params = ctx.get("params") or {}
    return (params.get("branch") or step.get("branch")
            or "feat/wf-" + str(ctx.get("run_id") or "run"))


def _agent(ctx):
    return (ctx.get("params") or {}).get("agent") or "wf"


def _timeout(step):
    try:
        t = float(step.get("timeout") or 0)
    except (TypeError, ValueError):
        t = 0
    return t if t > 0 else _ADD_TIMEOUT


def _worktree_of_branch(wt, repo, branch):
    """Ruta del worktree que YA tiene `branch` checked-out, o None.
    Lee `git worktree list --porcelain` (formato estable de git)."""
    rc, out, _ = wt._git(["-C", repo, "worktree", "list", "--porcelain"])
    if rc != 0:
        return None
    path = None
    for line in (out or "").splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):].strip()
        elif line.strip() == "branch refs/heads/%s" % branch and path:
            return path
    return None


def _branch_exists(wt, repo, branch):
    """rc==0 Y sha en stdout — `--verify` imprime el sha del ref cuando
    existe; exigir ambos evita falsos positivos si git devuelve rc raro."""
    rc, out, _ = wt._git(["-C", repo, "rev-parse", "--verify", "--quiet",
                          "refs/heads/%s" % branch])
    return rc == 0 and bool((out or "").strip())


def _adopt(wt, repo, branch, agent):
    """Idempotencia del acquire: si el estado del run YA existe, adoptarlo.
    Devuelve el resultado del paso (dict) o None si no hay nada que adoptar."""
    # (1) el registry de dueños ya conoce la rama y su árbol sigue en disco
    entry = (wt.load_owners() or {}).get(branch)
    if isinstance(entry, dict):
        path = (entry.get("path") or "").strip()
        if path and os.path.isdir(path):
            return {"ok": True,
                    "detail": "idempotente: worktree ya registrado para `%s` "
                              "en %s — adoptado (re-corrida = no-op)"
                              % (branch, path),
                    "artifacts": {"worktree_path": path, "branch": branch,
                                  "adopted": True}}
    # (2) hay un worktree en esa rama aunque el registry lo haya perdido
    path = _worktree_of_branch(wt, repo, branch)
    if path and os.path.isdir(path):
        wt.register(branch, agent=agent, path=path)
        return {"ok": True,
                "detail": "idempotente: worktree existente en la rama `%s` "
                          "(%s) — adoptado y re-registrado" % (branch, path),
                "artifacts": {"worktree_path": path, "branch": branch,
                              "adopted": True}}
    # (3) la rama ya existe (p. ej. el add anterior murió a medias) → adjuntar
    #     worktree SIN `-b`: re-correr `-b` fallaría con "branch already exists"
    if _branch_exists(wt, repo, branch):
        return "branch-exists"
    return None


def acquire(ctx, step):
    """Paso det IDEMPOTENTE: worktree con dueño para la rama del run.
    Adopta lo ya creado (resume seguro); si no hay nada, pool tibio primero."""
    repo = ctx.get("repo") or os.getcwd()
    branch, agent = _branch(ctx, step), _agent(ctx)
    if ctx.get("dry"):
        return {"ok": True,
                "detail": "dry: adquiriría worktree para `%s` (adopción "
                          "idempotente, pool tibio o git worktree add) con "
                          "dueño `%s`" % (branch, agent)}
    wt = _wt()
    adopted = _adopt(wt, repo, branch, agent)
    if isinstance(adopted, dict):
        return adopted
    parent = os.path.dirname(repo)
    path = os.path.join(parent, os.path.basename(repo) + "-trees",
                        branch.replace("/", "-"))
    if adopted == "branch-exists":
        rc, _, err = wt._git(["-C", repo, "worktree", "add", path, branch],
                             timeout=_timeout(step))
        if rc != 0:
            return {"ok": False,
                    "detail": "la rama `%s` ya existe pero no pude adjuntarle "
                              "worktree: %s" % (branch, err.strip() or rc),
                    "retriable": False}
        wt.register(branch, agent=agent, path=path)
        return {"ok": True,
                "detail": "idempotente: rama `%s` ya existía — worktree "
                          "adjuntado en %s (sin re-crear la rama)"
                          % (branch, path),
                "artifacts": {"worktree_path": path, "branch": branch,
                              "adopted": True}}
    got = wt.pool_acquire(repo=repo, agent=agent, branch=branch)
    if got:
        # árbol del pool queda detached y pristino → crear ahí la rama
        rc, _, err = wt._git(["-C", got["path"], "switch", "-c", branch])
        if rc != 0:
            return {"ok": False,
                    "detail": "pool: no pude crear la rama `%s` en %s (%s)"
                              % (branch, got["path"], err.strip() or rc)}
        wt.register(branch, agent=agent, path=got["path"], pool=True)
        return {"ok": True,
                "detail": "worktree del pool `%s` (%s) en la rama `%s`"
                          % (got["name"], got["path"], branch),
                "artifacts": {"worktree_path": got["path"], "branch": branch}}
    # sin pool: worktree nuevo, hermano del repo (convención del equipo)
    rc, _, err = wt._git(["-C", repo, "worktree", "add", path,
                          "-b", branch, "main"], timeout=_timeout(step))
    if rc != 0:
        return {"ok": False, "detail": "git worktree add falló: %s"
                % (err.strip() or "rc=%s" % rc)}
    wt.register(branch, agent=agent, path=path)
    return {"ok": True,
            "detail": "worktree nuevo en %s (rama `%s`)" % (path, branch),
            "artifacts": {"worktree_path": path, "branch": branch}}


def verify_acquired(ctx, step):
    """Verify det: el artefacto `worktree_path` del run existe en disco."""
    p = (ctx.get("artifacts") or {}).get("worktree_path")
    if not p:
        return {"ok": False, "detail": "sin artefacto worktree_path en el run"}
    ok = os.path.isdir(p)
    return {"ok": ok, "detail": "worktree %s %s"
            % (p, "existe" if ok else "NO existe")}


def release(ctx, step):
    """Paso det: libera los worktrees LIMPIOS del agente del run. Hereda la
    falla-suave de `_worktrees.release`: lo sucio queda intacto (se reporta,
    no falla el paso — el cleanup jamás pierde trabajo ni bloquea)."""
    agent = _agent(ctx)
    if ctx.get("dry"):
        return {"ok": True, "detail": "dry: liberaría los worktrees limpios "
                                      "del agente `%s`" % agent}
    res = _wt().release(agent=agent)
    resumen = " · ".join("%s=%d" % (k, len(v)) for k, v in sorted(res.items()))
    return {"ok": True, "detail": "release: " + (resumen or "nada"),
            "artifacts": {"worktree_release": res}}
