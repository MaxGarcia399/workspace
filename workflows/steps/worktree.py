#!/usr/bin/env python3
"""workflows.steps.worktree — wrap de `dash/dev/_worktrees` (NO reinventa).

acquire: IDEMPOTENTE (invariante v1.1 del runner: re-correr un paso EFECTIVO
tras un resume debe ser no-op seguro). Si la rama/worktree del run YA existe,
la ADOPTA en vez de fallar: (1) entrada viva del registry de dueños (sin
sesión dueña y del agente del run → el run la reclama para su release),
(2) worktree existente en esa rama (`git worktree list --porcelain`),
(3) rama ya creada sin worktree → `worktree add` SIN `-b` (adjunta, no
re-crea). Solo si nada existe crea desde cero: pool tibio primero
(`pool_acquire` — ignorados intactos, reserva atómica) y si no,
`git worktree add -b` hermano del repo (misma convención de ruta que
front.cmd_worktree: `<repo>-trees/<slug>`), registrando al dueño.

La rama nueva nace SIEMPRE del sha de main (v1.6), en los dos caminos: el
árbol del pool queda detached en el tip del lease ANTERIOR (quizá una rama
sin mergear) y un `switch -c` sin punto de partida arrastraba ese trabajo
ajeno a la rama del run. Ese sha se deja como artefacto `branch_base` (de
qué main nació la rama: front.integrate no lo cuenta como trabajo del run).
El repo es el checkout principal (`ctx["root"]`; las llamadas directas
traen `repo`).

release: `_worktrees.release(agent=…, session=wf:<run-id>)` — SOLO los
worktrees de ESTE run (acquire lo registra como sesión dueña; si la rama del
run quedó sin dueña — acquire de antes —, release la reclama primero); otro
run en paralelo del mismo agente conserva el suyo. Hereda su regla de oro (jamás
remueve trabajo sin commitear, jamás --force). Idempotente por construcción:
un release sin nada que liberar es no-op.

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


def _session(ctx):
    """Sesión dueña de los worktrees del run: su release suelta solo los suyos
    (el run-id sobrevive a pausas/resume — sigue siendo el mismo dueño)."""
    return "wf:" + str(ctx.get("run_id") or "run")


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


def _main_sha(wt, repo):
    """(sha de main, error): el punto de partida EXACTO de la rama del run.
    Se resuelve antes de tocar el pool — sin main no se reserva ningún árbol."""
    rc, out, err = wt._git(["-C", repo, "rev-parse", "--verify", "--quiet",
                            "refs/heads/main^{commit}"])
    sha = (out or "").strip()
    if rc == 0 and sha:
        return sha, ""
    return "", (err or "").strip() or "rc=%s" % rc


def _adopt(wt, repo, branch, agent, session):
    """Idempotencia del acquire: si el estado del run YA existe, adoptarlo.
    Devuelve el resultado del paso (dict) o None si no hay nada que adoptar."""
    # (1) el registry de dueños ya conoce la rama y su árbol sigue en disco.
    #     Si la entrada no tiene sesión dueña (registrada antes de existir, o a
    #     mano) y es del agente del run, el run la reclama: si no, su release
    #     la saltaría y el árbol quedaría colgado con la rama tomada. La de
    #     otra sesión u otro agente se usa pero NO se le quita.
    entry = (wt.load_owners() or {}).get(branch)
    if isinstance(entry, dict):
        path = (entry.get("path") or "").strip()
        if path and os.path.isdir(path):
            detail = ("idempotente: worktree ya registrado para `%s` en %s — "
                      "adoptado (re-corrida = no-op)" % (branch, path))
            if not wt.claim(branch, session, agent=agent):
                detail += ("; no quedó a nombre de este run (es de otra "
                           "sesión o agente): su release no lo suelta")
            return {"ok": True, "detail": detail,
                    "artifacts": {"worktree_path": path, "branch": branch,
                                  "adopted": True}}
    # (2) hay un worktree en esa rama aunque el registry lo haya perdido
    path = _worktree_of_branch(wt, repo, branch)
    if path and os.path.isdir(path):
        wt.register(branch, agent=agent, path=path, session=session)
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
    Adopta lo ya creado (resume seguro); si no hay nada, pool tibio primero.
    La rama nueva nace del sha de main (`branch_base`), jamás del árbol."""
    repo = ctx.get("root") or ctx.get("repo") or os.getcwd()
    branch, agent, session = _branch(ctx, step), _agent(ctx), _session(ctx)
    if ctx.get("dry"):
        return {"ok": True,
                "detail": "dry: adquiriría worktree para `%s` (adopción "
                          "idempotente, pool tibio o git worktree add) con "
                          "dueño `%s`" % (branch, agent)}
    wt = _wt()
    adopted = _adopt(wt, repo, branch, agent, session)
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
        wt.register(branch, agent=agent, path=path, session=session)
        return {"ok": True,
                "detail": "idempotente: rama `%s` ya existía — worktree "
                          "adjuntado en %s (sin re-crear la rama)"
                          % (branch, path),
                "artifacts": {"worktree_path": path, "branch": branch,
                              "adopted": True}}
    base, err = _main_sha(wt, repo)
    if not base:
        return {"ok": False,
                "detail": "no encuentro la rama `main` en %s (%s) — la rama del "
                          "run nace de main" % (repo, err),
                "retriable": False}
    got = wt.pool_acquire(repo=repo, agent=agent, branch=branch)
    if got:
        # árbol del pool: detached en el tip del lease anterior → la rama nace
        # del sha de main (sin punto de partida heredaba ese trabajo ajeno)
        rc, _, err = wt._git(["-C", got["path"], "switch", "-c", branch, base])
        if rc != 0:
            return {"ok": False,
                    "detail": "pool: no pude crear la rama `%s` en %s (%s)"
                              % (branch, got["path"], err.strip() or rc)}
        wt.register(branch, agent=agent, path=got["path"], pool=True,
                    session=session)
        return {"ok": True,
                "detail": "worktree del pool `%s` (%s) en la rama `%s` (desde "
                          "main %s)" % (got["name"], got["path"], branch,
                                        base[:12]),
                "artifacts": {"worktree_path": got["path"], "branch": branch,
                              "branch_base": base}}
    # sin pool: worktree nuevo, hermano del repo (convención del equipo)
    rc, _, err = wt._git(["-C", repo, "worktree", "add", path,
                          "-b", branch, base], timeout=_timeout(step))
    if rc != 0:
        return {"ok": False, "detail": "git worktree add falló: %s"
                % (err.strip() or "rc=%s" % rc)}
    wt.register(branch, agent=agent, path=path, session=session)
    return {"ok": True,
            "detail": "worktree nuevo en %s (rama `%s` desde main %s)"
                      % (path, branch, base[:12]),
            "artifacts": {"worktree_path": path, "branch": branch,
                          "branch_base": base}}


def verify_acquired(ctx, step):
    """Verify det: el artefacto `worktree_path` del run existe en disco."""
    p = (ctx.get("artifacts") or {}).get("worktree_path")
    if not p:
        return {"ok": False, "detail": "sin artefacto worktree_path en el run"}
    ok = os.path.isdir(p)
    return {"ok": ok, "detail": "worktree %s %s"
            % (p, "existe" if ok else "NO existe")}


def release(ctx, step):
    """Paso det: libera los worktrees LIMPIOS de ESTE run (nunca los de otro
    run en paralelo del mismo agente). Hereda la falla-suave de
    `_worktrees.release`: lo sucio queda intacto (se reporta, no falla el
    paso — el cleanup jamás pierde trabajo ni bloquea)."""
    agent, session = _agent(ctx), _session(ctx)
    if ctx.get("dry"):
        return {"ok": True, "detail": "dry: liberaría los worktrees limpios "
                                      "del run `%s` (agente `%s`)"
                                      % (ctx.get("run_id") or "?", agent)}
    wt = _wt()
    # Un run retomado tras actualizar no re-corre acquire: si su rama quedó
    # registrada SIN sesión dueña (acquire de antes), se reclama aquí — si no,
    # el release la saltaría y la rama quedaría tomada. Mismo criterio que
    # _adopt: solo entradas sin dueña y del agente del run.
    branch = ((ctx.get("artifacts") or {}).get("branch")
              or _branch(ctx, step))
    wt.claim(branch, session, agent=agent)
    res = wt.release(agent=agent, session=session)
    resumen = " · ".join("%s=%d" % (k, len(v)) for k, v in sorted(res.items()))
    return {"ok": True, "detail": "release: " + (resumen or "nada"),
            "artifacts": {"worktree_release": res}}
