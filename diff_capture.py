#!/usr/bin/env python3
"""WORKSPACE · diff_capture — ciclo del CLON efímero + captura de diff (F1.5).

Soporta la write-capability del autobus: un agente despachado escribe en un
**clon aislado** (nunca el repo/cerebro real), commitea, y el daemon captura el
**diff** que va al socio para el diff-gate. El agente/daemon JAMÁS aplican, mergean
ni pushean — el socio revisa y aplica en sesión real si aprueba.

Decisión clave (spec F1.5): **`git clone --local --no-hardlinks`, NO
`git worktree add`.** Un worktree comparte el `.git` del repo real (refs/heads/
main, packed-refs alcanzables) — un agente podría tocar refs reales. El clon
tiene su PROPIA `.git`; el seatbelt permite escritura SOLO bajo el clon, así el
repo real queda denegado a nivel FS. El clon vive FUERA de todo cerebro/repo:
`WORKSPACE-BUS-WORKTREES/<msg-id>/`.

Además: **canary de BOOT** — hash de `BOOT/*` del cerebro real ANTES y DESPUÉS
del dispatch (detección independiente de la jaula: si algo mutó BOOT, se aborta
el resultado). El diff se scrubbea de rutas del host antes de publicarse.

Cero deps (stdlib, 3.9+). Falla-suave.
"""
import hashlib
import os
import re
import shutil
import subprocess
import time

BRANCH_PREFIX = "bus/f1.5"
CLONE_TIMEOUT = 120
TTL_SECONDS = 24 * 3600          # retención de los clones antes de barrerlos
_HOST_PATH_RX = re.compile(r"(/Users/[^/\s]+|/home/[^/\s]+)\S*")


class DiffCaptureError(RuntimeError):
    """Error del ciclo de clon/diff (no transitorio)."""


def worktrees_root():
    """Dir raíz de los clones efímeros — FUERA de cerebros/repos. Override
    WORKSPACE_BUS_WORKTREES (tests / per-máquina)."""
    d = os.environ.get("WORKSPACE_BUS_WORKTREES")
    if not d:
        d = os.path.join(os.path.expanduser("~"), "WORKSPACE-BUS-WORKTREES")
    return d


def _scrub(s):
    try:
        return _HOST_PATH_RX.sub("‹ruta›", s or "")
    except Exception:
        return s or ""


def _git(args, cwd=None, timeout=CLONE_TIMEOUT):
    """(rc, stdout, stderr). rc=-1 si no se pudo correr."""
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)


# Flags/env que NEUTRALIZAN config del repo-local al capturar el diff en el DAEMON
# (que corre FUERA del sandbox, sobre el host real). Defensa en profundidad: el fix
# PRIMARIO es que <clon>/.git sea read-only para el agente (sandbox) → no puede
# plantar config; esto blinda igual la captura por si acaso. `-c` en la línea de
# comando GANA sobre el config local, así un core.fsmonitor/diff.external/pager
# plantado NUNCA se honra; hooksPath=/dev/null mata hooks; NOSYSTEM/GLOBAL=/dev/null
# ignoran config de sistema/global. Sin esto, un git add/diff podría ejecutar un
# comando arbitrario del atacante en el proceso del daemon.
_HARDEN_GIT = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
               "-c", "diff.external=", "-c", "core.pager=cat",
               "-c", "core.sshCommand=", "-c", "core.editor=true"]


def _git_capture(args, cwd=None, timeout=CLONE_TIMEOUT):
    """`_git` ENDURECIDO para la captura del daemon: ignora config global/sistema y
    neutraliza fsmonitor/hooks/external-diff/pager/ssh/editor. NUNCA honra config
    maliciosa plantada en el clon. Úsalo para TODO git que corra sobre el clon
    DESPUÉS de que el agente pudo escribir."""
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        r = subprocess.run(["git"] + _HARDEN_GIT + args, cwd=cwd, env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)


def _safe_seg(s):
    """Segmento seguro para path/branch (alnum/-/_)."""
    seg = "".join(c for c in str(s or "") if c.isalnum() or c in "-_")
    return seg or "x"


# ── crear el clon aislado + branch ──────────────────────────────────────────
def create_clone(repo, agent, msg_id):
    """Clona `repo` (local) a un dir efímero propio y crea el branch de trabajo.
    Devuelve {clone_dir, branch, base_sha, root}. Levanta DiffCaptureError si
    algo falla (fail-closed: sin clon no hay dónde escribir de forma segura)."""
    if not repo or not os.path.isdir(os.path.join(repo, ".git")):
        raise DiffCaptureError("repo inválido (sin .git): %s" % _scrub(repo))
    root = os.path.join(worktrees_root(), _safe_seg(msg_id))
    clone_dir = os.path.join(root, "clone")
    try:
        os.makedirs(root, exist_ok=True)
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir, ignore_errors=True)
        # --local + --no-hardlinks: objetos INDEPENDIENTes (no hardlink al source
        # → el clon no comparte el object store del repo real).
        rc, _, err = _git(["clone", "--local", "--no-hardlinks", "--quiet",
                           repo, clone_dir])
        if rc != 0:
            raise DiffCaptureError("git clone falló: %s" % _scrub(err)[:200])
        branch = "%s/%s/%s" % (BRANCH_PREFIX, _safe_seg(agent), _safe_seg(msg_id))
        rc, _, err = _git(["checkout", "-b", branch], cwd=clone_dir)
        if rc != 0:
            raise DiffCaptureError("git checkout -b falló: %s" % _scrub(err)[:200])
        rc, base_sha, _ = _git(["rev-parse", "HEAD"], cwd=clone_dir)
        # TMPDIR del agente DENTRO del clon (para que git escriba su temporal
        # confinado por el seatbelt, no fuera).
        os.makedirs(os.path.join(clone_dir, ".tmp"), exist_ok=True)
        return {"clone_dir": clone_dir, "branch": branch,
                "base_sha": base_sha if rc == 0 else "", "root": root}
    except DiffCaptureError:
        shutil.rmtree(root, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(root, ignore_errors=True)
        raise DiffCaptureError("clon: %s" % e)


# ── capturar el diff ─────────────────────────────────────────────────────────
def capture_diff(clone_dir, base_sha):
    """TODOS los cambios del agente vs `base_sha` → dict scrubbeado, haya
    committeado o NO. Hace `git add -A` para incluir lo untracked/sin commitear
    (el agente suele escribir archivos sin `git commit`) y diffea el índice
    contra base. Usa git ENDURECIDO (_git_capture) porque corre en el daemon fuera
    del sandbox. `capture_ok`=False señala que git FALLÓ (≠ diff vacío real) para
    que el caller no lo confunda con "no escribió nada" y descarte trabajo. El
    hardblock se evalúa sobre el diff COMPLETO (antes de truncar a 200KB para
    publicar) → no se evade con relleno. Nunca levanta."""
    out = {"branch": "", "base_sha": base_sha, "diff_text": "",
           "files_changed": [], "stats": "", "commits": 0,
           "capture_ok": True, "hardblock_hit": False, "hardblock_pat": ""}
    try:
        rc, branch, _ = _git_capture(["rev-parse", "--abbrev-ref", "HEAD"], cwd=clone_dir)
        if rc == 0:
            out["branch"] = branch
        # stage TODO lo que el agente escribió (untracked incluido) → el diff-gate
        # ve su trabajo completo aunque no haya hecho commit.
        rc_add, _, _ = _git_capture(["add", "-A"], cwd=clone_dir)
        base = base_sha or _EMPTY_TREE
        rc, diff, _ = _git_capture(["diff", "--cached", "--no-ext-diff", base], cwd=clone_dir)
        # hardblock sobre el diff COMPLETO (sin truncar) antes de recortar a 200KB.
        full = _scrub(diff) if rc == 0 else ""
        hit, pat = hardblock_match(full)
        out["hardblock_hit"], out["hardblock_pat"] = hit, pat
        out["diff_text"] = full[:200_000]
        rc2, names, _ = _git_capture(["diff", "--cached", "--name-only", base], cwd=clone_dir)
        out["files_changed"] = [l for l in (names.splitlines() if rc2 == 0 else []) if l]
        rc3, stat, _ = _git_capture(["diff", "--cached", "--stat", base], cwd=clone_dir)
        out["stats"] = _scrub(stat) if rc3 == 0 else ""
        # capture_ok: git tiene que haber cooperado en add + diff. Si alguno falló,
        # NO afirmamos "sin cambios" — el caller debe tratarlo como bloqueado.
        out["capture_ok"] = (rc_add == 0 and rc == 0 and rc2 == 0)
        rc4, cnt, _ = _git_capture(["rev-list", "--count", "%s..HEAD" % base_sha], cwd=clone_dir) \
            if base_sha else (1, "0", "")
        try:
            out["commits"] = int(cnt) if rc4 == 0 else 0
        except ValueError:
            pass
    except Exception as e:
        out["capture_ok"] = False
        out["error"] = str(e)[:200]
    return out


# árbol vacío de git (para diffear cuando no hay base_sha)
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


# ── canary de BOOT (detección independiente de mutación al cerebro real) ────
def boot_canary(brain):
    """{rel: sha256} de BOOT/*.md del cerebro real. Compara pre/post para probar
    que el dispatch NO mutó la identidad (independiente de la jaula). {} si no
    hay BOOT / falla-suave."""
    out = {}
    boot = os.path.join(os.path.expanduser(brain or ""), "BOOT")
    try:
        for fn in sorted(os.listdir(boot)):
            p = os.path.join(boot, fn)
            if not os.path.isfile(p):
                continue
            try:
                with open(p, "rb") as fh:
                    out[fn] = hashlib.sha256(fh.read()).hexdigest()
            except OSError:
                continue
    except OSError:
        return {}
    return out


def canary_intact(pre, post):
    """True si el canary de BOOT no cambió (mismos archivos y hashes)."""
    return pre == post


# ── limpieza / retención ────────────────────────────────────────────────────
def cleanup(root):
    """Borra el dir del clon (el diff ya se capturó a un artefacto)."""
    if root:
        shutil.rmtree(root, ignore_errors=True)


def sweep_stale(ttl_seconds=TTL_SECONDS):
    """Barre clones más viejos que el TTL (política de retención). Falla-suave."""
    base = worktrees_root()
    now = time.time()
    swept = 0
    try:
        for name in os.listdir(base):
            p = os.path.join(base, name)
            try:
                if os.path.isdir(p) and now - os.path.getmtime(p) > ttl_seconds:
                    shutil.rmtree(p, ignore_errors=True)
                    swept += 1
            except OSError:
                continue
    except OSError:
        return 0
    return swept


# ── detección adicional de hard-block en el diff (NUNCA la única cobertura) ──
# Los hard-blocks se enforzan POR CONSTRUCCIÓN (jaula-FS + sin-red + allowlist de
# git). Esto es detección EXTRA: si el diff/transcripción huele a push/main-stable/
# credenciales/financiero/destructivo/N3 → el daemon killpg + escala sin abrir el
# diff-gate. Es una red, no el control primario (Argus).
_HARDBLOCK_RX = re.compile(
    r"\b(git\s+push|remote\s+add|force[- ]?push|--force\b|origin/(main|stable)"
    r"|rm\s+-rf|mkfs|dd\s+if=|:\s*\(\)\s*\{|/etc/(passwd|shadow)"
    r"|AKIA[0-9A-Z]{16}|-----BEGIN\b.*PRIVATE KEY|\bsk-(ant|proj|live)"
    r"|BEGIN OPENSSH PRIVATE KEY)\b", re.IGNORECASE | re.DOTALL)


def hardblock_match(*texts):
    """(True, patrón) si algún texto (diff/transcripción) matchea un hard-block.
    Detección adicional — no reemplaza la contención por construcción."""
    for t in texts:
        m = _HARDBLOCK_RX.search(t or "")
        if m:
            return True, m.group(0)[:60]
    return False, ""
