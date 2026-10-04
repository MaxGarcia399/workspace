#!/usr/bin/env python3
"""WORKSPACE · sandbox — confinamiento del runner `agent-real` de evals (F1).

Corre el boot de un agente bajo prueba dentro de un sandbox del SO, sobre una
**copia efímera** de su cerebro. Es el control de seguridad del runner
`agent-real` — ver `research/design/evals-platform/SECURITY-REVIEW-F1-sandbox.md`
y su corrección (bus, 2026-07-08): con modelo REMOTO el proceso NECESITA red
para llegar a la API, así que la defensa anti-exfiltración vive en la capa de
**tools** (allowlist read-only, sin Bash/WebFetch/MCP), NO en la capa del SO.
Este módulo aporta las otras dos garantías, que sí son del SO:

  · **Contención de ESCRITURA** — seatbelt niega `file-write*` fuera del workdir
    efímero (+ temp + estado del CLI). El agente no puede tocar el cerebro real
    ni el resto del host.
  · **Copia efímera** — el `cwd` del agente es una copia desechable del cerebro
    (symlinks copiados como links, no seguidos). Toda escritura muere con ella.

INVARIANTE (mismo espíritu que `headless.HeadlessSecurityError`, pedido por el
review N2): si la plataforma no ofrece una primitiva de sandbox verificada, NO
se corre — `SandboxUnavailable`, **sin bypass por env**. El caller cae a
`agent-lite` con flag honesto en la UI, JAMÁS a un subproceso desnudo. Hoy solo
macOS (`sandbox-exec`); Windows/Linux sin primitiva verificada → no disponible.

Allowlist de tools read-only (`READ_ONLY_TOOLS`): explícita a propósito. El
review documenta que `--allowedTools ""` NO deshabilita nada (es un merge sobre
las allow-rules del `settings.json` del socio). `agent-real` da SOLO tools de
lectura y además ignora los setting-sources del socio (lo aplica el caller vía
`headless`), así ningún `Bash(...)`/MCP del socio se filtra.

Cero dependencias (stdlib, Python 3.9+). Amputable (C10): quien lo importe
falla-suave si no está.
"""
import os
import platform
import shutil
import tempfile

#: Tools de SOLO LECTURA del agente real — FUENTE ÚNICA en headless (es quien
#: construye el argv que de verdad las aplica). Se reexporta aquí para el
#: allowlist conceptual del sandbox; amputable si headless no está.
try:
    from headless import READ_ONLY_TOOLS
except Exception:                     # pragma: no cover — amputable (C10)
    READ_ONLY_TOOLS = ("Read", "Grep", "Glob", "LS")

#: Dirs que NO se copian al cerebro efímero: pesados/irrelevantes para el boot y
#: fuente de conflictos. `.git` sobre todo (puede ser enorme). No es un filtro de
#: seguridad — la seguridad la da el no-red-de-tools + la contención de escritura.
_COPY_IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", "*.pyc", "node_modules", ".venv", "venv",
    ".DS_Store", "*.lock")


class SandboxError(RuntimeError):
    """Error del sandbox (configuración, no transitorio — no reintentar)."""


class SandboxUnavailable(SandboxError):
    """No hay primitiva de sandbox verificada en esta plataforma. Fail-closed:
    el caller cae a `agent-lite` honesto, nunca a un subproceso sin confinar."""


# ── disponibilidad (probe de capacidad, fail-closed) ────────────────────────
def available():
    """(ok, razón). True solo si esta plataforma tiene una primitiva de sandbox
    verificada Y presente. Hoy: macOS con `sandbox-exec` en el PATH."""
    if platform.system() != "Darwin":
        return False, "sandbox del SO solo verificado en macOS (seatbelt); " \
                      "SO actual: %s" % (platform.system() or "desconocido")
    if not _sandbox_exec_path():
        return False, "sandbox-exec no está en el PATH"
    return True, "macOS · sandbox-exec (seatbelt)"


def _sandbox_exec_path():
    # ruta absoluta esperada primero (sandbox-exec no siempre está en el PATH
    # de un subproceso con env recortado), luego PATH.
    for p in ("/usr/bin/sandbox-exec",):
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("sandbox-exec")


# ── copia efímera del cerebro ───────────────────────────────────────────────
def make_ephemeral_brain(brain, parent=None):
    """Copia `brain` a un dir temporal desechable y devuelve su ruta. El `cwd`
    del agente será esta copia: toda escritura que logre hacer muere aquí y el
    cerebro REAL queda intacto.

    `symlinks=True`: los symlinks se copian como links, NO se siguen — evita
    copiar targets gigantes/sensibles fuera del cerebro y cierra el escape por
    symlink hacia el host. Levanta SandboxError si la copia falla (fail-closed:
    sin copia no hay contención de escritura, así que no se corre)."""
    brain = os.path.expanduser(brain)
    if not os.path.isdir(brain):
        raise SandboxError("cerebro inexistente para copiar: %s" % brain)
    dst_parent = parent or tempfile.mkdtemp(prefix="workspace-sbx-")
    dst = os.path.join(dst_parent, "brain")
    try:
        shutil.copytree(brain, dst, symlinks=True, ignore=_COPY_IGNORE)
    except (OSError, shutil.Error) as e:
        # limpia lo que se haya alcanzado a copiar y falla-cerrado
        shutil.rmtree(dst_parent, ignore_errors=True)
        raise SandboxError("no pude crear el cerebro efímero: %s" % e)
    return dst


def cleanup(ephemeral_brain):
    """Borra el cerebro efímero (y su parent temporal). Falla-suave."""
    if not ephemeral_brain:
        return
    # el parent es el mkdtemp; el brain es <parent>/brain — borra el parent.
    parent = os.path.dirname(os.path.abspath(ephemeral_brain))
    shutil.rmtree(parent, ignore_errors=True)


# ── perfil seatbelt (contención de ESCRITURA) ───────────────────────────────
def _sb_path(p):
    """Escapa una ruta para un literal `(subpath "…")` de seatbelt."""
    return os.path.realpath(os.path.expanduser(p)).replace("\\", "\\\\").replace('"', '\\"')


def seatbelt_profile(workdir):
    """Perfil SBPL: permite todo por default MENOS escritura, y re-permite
    escritura SOLO al workdir efímero, al temp del sistema y al estado propio del
    CLI (`~/.claude`, que el binario necesita para su cache/sesión). La lectura
    queda permitida (sin red-de-tools, leer ≠ exfiltrar). La RED se deja al
    caller/tools a propósito (el modelo remoto la necesita; ver docstring del
    módulo)."""
    allow_write = [workdir, tempfile.gettempdir(),
                   os.path.join(os.path.expanduser("~"), ".claude")]
    # /private/var/folders es el temp real de macOS (TMPDIR suele apuntar ahí,
    # pero lo incluimos explícito por si TMPDIR viene recortado en el subproc).
    allow_write.append("/private/var/folders")
    subpaths = "\n".join('    (subpath "%s")' % _sb_path(p) for p in allow_write)
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny file-write*)\n"
        "(allow file-write*\n" + subpaths + ")\n"
        # /dev básicos (el CLI escribe a stdout/err/null/tty)
        '(allow file-write-data\n'
        '    (path "/dev/null") (path "/dev/zero") (path "/dev/dtracehelper")\n'
        '    (path "/dev/tty") (path "/dev/stdout") (path "/dev/stderr"))\n'
    )


def wrap_prefix(workdir):
    """Prefijo argv del SO que confina un subproceso: `[sandbox-exec, -p,
    <perfil>]`. Es lo que se pasa como `wrapper` a `headless.run_headless` para
    envolver al agente real. Levanta SandboxUnavailable si la plataforma no
    puede sandboxear (fail-closed — el caller NO debe correr sin confinar)."""
    ok, why = available()
    if not ok:
        raise SandboxUnavailable(why)
    exe = _sandbox_exec_path()
    if not exe:                                   # doble-check (carrera improbable)
        raise SandboxUnavailable("sandbox-exec desapareció del PATH")
    return [exe, "-p", seatbelt_profile(workdir)]


# ── perfil WRITE-SCOPED (F1.5): jaula-FS al clon + deny-read de credenciales ──
# Dirs de credenciales bajo $HOME que se DENIEGAN a la LECTURA (condición 3 de
# Argus). ~/.claude NO está: el CLI de Claude Code LO NECESITA para su auth
# (modelo remoto) — mitigado por la allowlist SIN tools de red (no exfiltra el
# token aunque lo lea) + isolation_vars (credenciales de push per-agente).
# ~/.workspace: aloja la CLAVE HMAC RAÍZ del bus (~/.workspace/bus/hmac.key, la que
# gatea verify()/dispatch_one_write). Un agente write-scoped NO debe poder leerla
# (podría escribirla al working-tree → entra al diff publicado → Obsidian-sync).
_DENY_READ_UNDER_HOME = (".ssh", ".aws", ".gnupg", ".config", ".gsutil",
                         ".netrc", ".env", ".pgpass", ".npmrc", ".docker",
                         ".workspace")

# ~/.claude es un ALLOWLIST, no un denylist (Argus F1.5 #3, flip exigido): se
# deniega la lectura de TODO ~/.claude y se re-permite SOLO el mínimo que el CLI
# necesita para auth. Bisección empírica (Mac): el CLI autentica con ~/.claude
# ENTERO denegado (rc 0) → el token vive en el Keychain, NO en ~/.claude → el
# allowlist es VACÍO (no hay que permitir nada). Así queda cerrado por
# construcción: transcripts-backup (datos de otros agentes/clientes externos),
# history, projects, daemon/control.key (¡llave del daemon!), daemon.log, jobs,
# settings.local — TODO deny, y cualquier subdir NUEVO que agregue Claude Code
# filtra por default = deny (postura correcta de una jaula).
_CLAUDE_AUTH_ALLOW = ()          # vacío: el token está en Keychain, no en archivos


def build_write_profile(clone_dir, deny_read_extra=None):
    """Perfil SBPL para el modo WRITE-SCOPED del agente (F1.5): permite ESCRITURA
    SOLO bajo `clone_dir` (el clon efímero) MENOS su `.git/` (read-only, para que
    el agente no pueda plantar config maliciosa que dispare RCE en la captura del
    daemon) — el repo real y todos los cerebros quedan deny-write a nivel FS.
    Además DENIEGA la LECTURA de credenciales del socio (~/.ssh, ~/.aws, dotfiles
    sensibles, ~/.workspace con la clave HMAC del bus) y de los paths extra que pase
    el daemon (BOOT/.claude de OTROS cerebros). La RED no se corta en el SO (el
    modelo remoto la necesita); el bloqueo de red es por la capa de tools — y
    ahora es completo POR CONSTRUCCIÓN: sin Bash el agente no puede spawnear un
    subproceso (curl/git) que alcance la red por fuera de la capa de tools (era el
    hueco del C-BLOCK de Argus). `deny_read_extra` = paths absolutos extra a
    bloquear (otros cerebros, off-limits del socio)."""
    home = os.path.expanduser("~")
    # ESCRITURA SOLO bajo el clon (spec F1.5). NO el temp del sistema — sería
    # demasiado amplio. El runner apunta TMPDIR a <clon>/.tmp para que git
    # escriba su temporal DENTRO del clon (sigue confinado).
    allow_write = [clone_dir]
    # ...PERO el .git del clon queda READ-ONLY para el agente: aunque el agente ya
    # no tiene Bash/git, SÍ conserva Write/Edit. Sin este deny podría plantar
    # <clon>/.git/config con diff.external/core.fsmonitor/[filter] clean y disparar
    # RCE cuando el DAEMON corre `git add -A`/`git diff` en capture_diff FUERA del
    # sandbox (sobre el host real). Deny-write a <clon>/.git DESPUÉS del allow del
    # clon (SBPL = last-match-wins) → el agente escribe solo el working-tree; el
    # daemon (fuera del sandbox) sigue escribiendo .git para capturar el diff.
    deny_write_git = [os.path.join(clone_dir, ".git")]
    claude = os.path.join(home, ".claude")
    # deny-read: dirs de credenciales (denylist para esos, todos all-deny) +
    # ~/.claude ENTERO (allowlist: se re-permite abajo solo el mínimo de auth) +
    # extras del daemon (otros cerebros / off-limits del socio).
    deny_read = [os.path.join(home, d) for d in _DENY_READ_UNDER_HOME]
    deny_read.append(claude)
    deny_read += list(deny_read_extra or [])
    claude_allow = [os.path.join(claude, p) for p in _CLAUDE_AUTH_ALLOW]
    wsub = "\n".join('    (subpath "%s")' % _sb_path(p) for p in allow_write)
    gsub = "\n".join('    (subpath "%s")' % _sb_path(p) for p in deny_write_git)
    dsub = "\n".join('    (subpath "%s")' % _sb_path(p) for p in deny_read)
    asub = "\n".join('    (path "%s")' % _sb_path(p) for p in claude_allow)
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny file-write*)\n"
        "(allow file-write*\n" + wsub + ")\n"
        # RE-deny del .git del clon DESPUÉS del allow (last-match-wins): el agente
        # escribe el working-tree, nunca .git → no puede envenenar la config.
        + ("(deny file-write*\n" + gsub + ")\n" if deny_write_git else "")
        + '(allow file-write-data\n'
        '    (path "/dev/null") (path "/dev/zero") (path "/dev/dtracehelper")\n'
        '    (path "/dev/tty") (path "/dev/stdout") (path "/dev/stderr"))\n'
        # deny-READ (después de allow default → el deny gana). ~/.claude entero
        # denegado; el allow-read de abajo re-permite SOLO el mínimo de auth.
        + ("(deny file-read*\n" + dsub + ")\n" if deny_read else "")
        + ("(allow file-read*\n" + asub + ")\n" if claude_allow else "")
    )


def wrap_write_prefix(clone_dir, deny_read_extra=None):
    """Prefijo `[sandbox-exec, -p, <perfil-write-scoped>]`. Fail-closed:
    SandboxUnavailable si la plataforma no puede sandboxear (nunca correr un
    agente que ESCRIBE sin la jaula del SO)."""
    ok, why = available()
    if not ok:
        raise SandboxUnavailable(why)
    exe = _sandbox_exec_path()
    if not exe:
        raise SandboxUnavailable("sandbox-exec desapareció del PATH")
    return [exe, "-p", build_write_profile(clone_dir, deny_read_extra)]


def wrap_command(cmd, workdir):
    """Prefija `cmd` (argv list) con el wrapper del SO para que corra confinado.
    Fail-closed vía wrap_prefix."""
    return wrap_prefix(workdir) + list(cmd)
