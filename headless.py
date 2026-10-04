#!/usr/bin/env python3
"""WORKSPACE · headless — contrato pluggable de invocación LLM one-shot.

La destilación (dream.py) y demás bookkeeping del harness necesitan un LLM
"texto adentro → texto afuera", SIN sesión interactiva. Históricamente eso
estaba cableado a UN solo CLI (`claude -p`, duplicado en dream.py y
eval_runner.py). Este módulo lo extrae a un contrato con backends
registrables — la pieza F2 del plan model-agnostic: independencia del LLM
que destila, complementaria a la independencia de DATOS
(`neutral_transcript.py`).

CONTRATO:

    run_headless(prompt, *, backend="claude-code", model=None, cwd=None,
                 tools="none", timeout=300, exe_override=None) -> (ok, out)

  · `tools="none"` (DEFAULT) = el LLM NO tiene tools: texto puro, no toca
    filesystem ni red por su cuenta. Es el modo del flujo de destilación
    (el transcript es contenido NO confiable — ver dream.py, guard N6).
  · `cwd` = directorio de trabajo del subproceso (dream pasa su staging;
    JAMÁS el cerebro). None = heredar el del caller.
  · `exe_override` = binario alterno (los knobs WORKSPACE_DREAM_CMD /
    WORKSPACE_EVAL_CMD de siempre pasan por aquí).

INVARIANTE DE SEGURIDAD (pedido por Argus — es LEY, no preferencia):
  un backend que NO puede deshabilitar tools se RECHAZA cuando
  `tools="none"` (levanta HeadlessSecurityError, error de configuración,
  no transitorio). Sin esto, "cambiar de backend" degradaría en silencio
  la garantía de que el destilador corre sin manos: un prompt-injection
  en un transcript podría ejecutar tools. Sin bypass por env DEL
  INVARIANTE; `exe_override` y los knobs WORKSPACE_DREAM_CMD/WORKSPACE_EVAL_CMD
  que pasan por él son knobs de test con poder total (ejecutan un binario
  arbitrario) — riesgo pre-existente, aceptado bajo el modelo Y1
  single-user.

BACKENDS (registro por nombre, mismo naming que engines/):

  claude-code   REAL, verificado — el histórico dream._invoke_claude
                ENDURECIDO (Argus): `--allowedTools ""` solo era un
                merge-allowlist sobre el settings.json del usuario (sus
                allow-rules de Bash/MCP seguían aplicando), NO un disable
                duro. Ahora tools="none" añade `--tools ""` (deshabilita
                TODAS las tools built-in), `--permission-mode plan` (nada
                mutante) y `--setting-sources ""` (ignora las allow-rules
                de user/project/local). Env anti-recursión, stdin cerrado.
  codex         ⚠ BEST-EFFORT, A-VERIFICAR contra un Codex CLI real.
                `codex exec` puede acotarse a sandbox read-only, pero NO
                hay knob confirmado para deshabilitar tools por completo
                → declara can_disable_tools=False y por el invariante NO
                sirve para destilar (tools="none") hasta verificarse.
                Queda funcional para tools="read-only" (probado contra
                mocks en la suite; jamás se corre el CLI real ahí).
  stub          sin LLM: responde desde WORKSPACE_HEADLESS_STUB_OUTPUT /
                WORKSPACE_HEADLESS_STUB_FILE (o eco). Sin tools por
                construcción → can_disable_tools=True. Es la prueba viva
                del switching (la suite destila end-to-end con él) y un
                doble de pruebas sin mocks.

  register_backend(name, invoke, can_disable_tools=…, verified=…) permite
  enchufar más (openrouter, ollama, …) sin tocar a los consumidores.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Amputable (C10):
dream.py falla-suave si este módulo no está.
"""
import os
import shutil
import subprocess
import tempfile

DEFAULT_TIMEOUT = 300
DEFAULT_BACKEND = "claude-code"

#: valores válidos del parámetro `tools`
TOOLS_NONE = "none"            # sin tools — modo destilación (default)
TOOLS_READ_ONLY = "read-only"  # tools acotadas a lectura (si el backend puede)
TOOLS_GEN = "gen"              # sin tools, modo GENERACIÓN (sin plan-mode)
TOOLS_WRITE_SCOPED = "write-scoped"   # lectura + escritura + git ACOTADO (F1.5)
_VALID_TOOLS = (TOOLS_NONE, TOOLS_READ_ONLY, TOOLS_GEN, TOOLS_WRITE_SCOPED)

# write-scoped (F1.5): el agente ESCRIBE archivos, NADA MÁS. NO tiene Bash.
# C-BLOCK de Argus (opción 1, la preferida) + hallazgo de mi self-review: con Bash
# + red/Keychain abiertos, el único control anti-push/anti-exfil era un allowlist de
# subcomandos git SIN VERIFICAR y evadible (encadenar comandos, git -c, subshell) —
# y peor: con Write el agente podía plantar <clon>/.git/config con diff.external/
# fsmonitor/filter y disparar RCE cuando el DAEMON corre git fuera del sandbox. El
# fix por CONSTRUCCIÓN: el agente NO corre git. El DAEMON hace todo git (capture_diff
# = git add -A + diff --cached sobre el working-tree del clon) → el agente no necesita
# git para nada. Sin Bash no hay allowlist que evadir, ni curl-exfil, ni push-remoto.
_WRITE_TOOLS = ("Read", "Grep", "Glob", "LS", "Write", "Edit")
# Deny EXPLÍCITO (belt-and-suspenders): aunque --tools ya no los incluye, se niegan
# por nombre por si algún setting/futuro los reintrodujera. Bash = manos arbitrarias;
# WebFetch/WebSearch = red por la capa de tools.
_WRITE_DENY = ("Bash", "WebFetch", "WebSearch")

#: tools de SOLO LECTURA que expone tools="read-only" (built-ins de claude-code).
#: Fuente ÚNICA — sandbox.py la importa de aquí para no divergir. Explícita a
#: propósito (allowlist, no lista negra): nada que escriba, ejecute o abra red.
#: Es el set del runner agent-real (F1); la garantía anti-daño la refuerza el
#: sandbox del SO (sandbox.py), esta lista es la capa de tools.
READ_ONLY_TOOLS = ("Read", "Grep", "Glob", "LS")


class HeadlessError(RuntimeError):
    """Error del contrato headless (configuración, no transitorio)."""


class UnknownBackend(HeadlessError):
    """Backend no registrado."""


class HeadlessSecurityError(HeadlessError):
    """INVARIANTE: se pidió `tools=none` con un backend que no puede
    deshabilitar tools. Error de configuración — reintentar no lo arregla."""


# ── backend: claude-code (real, verificado) ────────────────────────────────
def _invoke_claude_code(prompt, *, model, timeout, cwd, tools, exe_override,
                        wrapper=None, env_extra=None, kill_group=False):
    """`claude -p` texto puro — el histórico dream._invoke_claude con el
    disable de tools ENDURECIDO (Argus). `--allowedTools ""` a secas NO
    deshabilita nada: es un merge-allowlist sobre las reglas del
    settings.json del usuario, así que sus allow-rules (Bash(...), MCP)
    seguían vivas frente a un prompt-injection en el transcript. Para
    tools="none" el argv añade, además del histórico:
      · `--tools ""`             — deshabilita TODAS las tools built-in
                                   (semántica documentada del CLI)
      · `--permission-mode plan` — nada mutante aunque algo se filtre
      · `--setting-sources ""`   — NO se cargan user/project/local: las
                                   allow-rules del socio no aplican
    Verificado contra el CLI real (2.1.199): responde texto normal y un
    prompt que exige ejecutar Bash NO logra tocar el filesystem.
    Env anti-recursión y stdin cerrado, como siempre.

    tools="read-only" (runner agent-real, F1): expone SOLO las built-in de
    lectura (`--tools Read,Grep,Glob,LS`) — misma técnica que el disable de
    tools="none", pero acotando el set en vez de vaciarlo — con
    `--permission-mode plan` (nada mutante) y `--setting-sources ""` (no
    hereda las allow-rules del socio, misma razón que en tools="none"). La
    garantía anti-daño NO descansa solo aquí: el caller (agent-real) envuelve
    además el proceso en el sandbox del SO vía `wrapper` (sandbox-exec) — el
    tool-layer y el OS-layer son defensa en profundidad. `wrapper` (argv
    prefix, p.ej. sandbox-exec) se antepone al comando; None = sin sandbox
    (el histórico)."""
    exe = exe_override or shutil.which("claude")
    if not exe:
        return False, "claude no está en PATH"
    cmd = [exe, "-p", prompt]
    if model:
        cmd += ["--model", model]
    cmd += ["--output-format", "text"]
    if tools == TOOLS_NONE:
        # Disable DURO (ver docstring): allowedTools solo merjea allowlists,
        # las tres flags extra son las que de verdad dejan al LLM sin manos.
        cmd += ["--allowedTools", "",
                "--tools", "",
                "--permission-mode", "plan",
                "--setting-sources", ""]
    elif tools == TOOLS_READ_ONLY:
        # SOLO built-ins de lectura + nada mutante + sin heredar el settings
        # del socio. Confinado además por el sandbox del SO (wrapper).
        cmd += ["--tools", ",".join(READ_ONLY_TOOLS),
                "--permission-mode", "plan",
                "--setting-sources", ""]
    elif tools == TOOLS_GEN:
        # GENERACIÓN de artefactos (Lavish Studio): sin tools (--tools "") y sin
        # MCP (--setting-sources "") → el modelo NO tiene manos. A diferencia de
        # tools="none" NO fuerza --permission-mode plan: el plan-mode hace que el
        # modelo intente explorar/actuar en vez de EMITIR el artefacto (verificado
        # con el CLI real). Sin tools el plan-mode no aporta seguridad (no hay tool
        # que restringir), así que se omite para que genere libremente.
        cmd += ["--tools", "",
                "--setting-sources", ""]
    elif tools == TOOLS_WRITE_SCOPED:
        # F1.5: el agente ESCRIBE (Write/Edit) en su clon y NADA MÁS — sin Bash,
        # sin git, sin red. --setting-sources '' (no hereda allow-rules del socio)
        # + --permission-mode acceptEdits (auto-aprueba edits — NUNCA
        # bypassPermissions). PRIMARIO: la jaula-FS del seatbelt (wrapper) confina
        # las escrituras al working-tree del clon (ni el repo real ni <clon>/.git).
        # El agente no corre git → el daemon captura el diff del working-tree.
        cmd += ["--tools", ",".join(_WRITE_TOOLS),
                "--permission-mode", "acceptEdits",
                "--setting-sources", ""]
        for pat in _WRITE_DENY:
            cmd += ["--disallowedTools", pat]
    if wrapper:                       # sandbox-exec u otro prefijo del SO
        cmd = list(wrapper) + cmd
    env = dict(os.environ)
    env["WORKSPACE_REVIEW_RUNNING"] = "1"    # anti-recursión (no review del review)
    env["WORKSPACE_NO_AUTOUPDATE"] = "1"
    if env_extra:                     # p.ej. TMPDIR dentro del clon (write-scoped)
        env.update({str(k): str(v) for k, v in env_extra.items()})
    if cwd:
        os.makedirs(cwd, exist_ok=True)
    if kill_group:                    # write-scoped: mata TODO el grupo en timeout
        return _run_killgroup(cmd, cwd, env, timeout)
    try:
        r = subprocess.run(cmd, cwd=cwd or None, env=env, timeout=timeout,
                           capture_output=True, stdin=subprocess.DEVNULL)
    except Exception as e:
        return False, "fallo al invocar: %s" % e
    out = r.stdout.decode("utf-8", errors="replace")
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace")[:300]
        return False, "exit %d: %s" % (r.returncode, err)
    return True, out


def _run_killgroup(cmd, cwd, env, timeout):
    """Corre `cmd` en su PROPIO grupo de procesos (start_new_session) y, en
    timeout/abort, mata el GRUPO ENTERO con SIGKILL (sandbox-exec→claude→node→git
    no quedan huérfanos). Es el camino write-scoped (agente que ESCRIBE): Argus
    exige killpg cuando hay escritura/red. Devuelve (ok, out)."""
    import signal
    try:
        p = subprocess.Popen(cmd, cwd=cwd or None, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        return False, "fallo al invocar: %s" % e
    try:
        out_b, err_b = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)   # mata el grupo
        except (OSError, ProcessLookupError):
            try:
                p.kill()
            except Exception:
                pass
        p.communicate()
        return False, "timeout: grupo de procesos matado (killpg) tras %ss" % timeout
    out = (out_b or b"").decode("utf-8", errors="replace")
    if p.returncode != 0:
        err = (err_b or b"").decode("utf-8", errors="replace")[:300]
        return False, "exit %d: %s" % (p.returncode, err)
    return True, out


# ── backend: codex (⚠ best-effort, A-VERIFICAR) ────────────────────────────
def _invoke_codex(prompt, *, model, timeout, cwd, tools, exe_override,
                  wrapper=None):
    """`codex exec` no-interactivo. ⚠ A-VERIFICAR contra un Codex CLI real
    (flags basados en docs públicas; la suite solo lo prueba con mocks):
    - `--sandbox read-only` acota el shell a lecturas — NO lo deshabilita
      (por eso can_disable_tools=False; el invariante lo excluye de
      tools="none" hasta que exista/verifique un knob real).
    - `--output-last-message <tmp>`: stdout de codex exec mezcla logs con
      la respuesta; el mensaje final limpio va a un archivo temporal.
    - `--skip-git-repo-check`: el staging del harness no es repo git.
    """
    exe = exe_override or shutil.which("codex")
    if not exe:
        return False, "codex no está en PATH"
    if cwd:
        os.makedirs(cwd, exist_ok=True)
    fd, outfile = tempfile.mkstemp(prefix="workspace-headless-", suffix=".txt",
                                   dir=cwd or None)
    os.close(fd)
    cmd = [exe, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
           "--output-last-message", outfile]
    if model:
        cmd += ["--model", model]
    cmd += [prompt]
    if wrapper:                       # sandbox del SO (agent-real), como claude-code
        cmd = list(wrapper) + cmd
    env = dict(os.environ)
    env["WORKSPACE_REVIEW_RUNNING"] = "1"
    env["WORKSPACE_NO_AUTOUPDATE"] = "1"
    try:
        r = subprocess.run(cmd, cwd=cwd or None, env=env, timeout=timeout,
                           capture_output=True, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", errors="replace")[:300]
            return False, "exit %d: %s" % (r.returncode, err)
        try:
            with open(outfile, encoding="utf-8", errors="replace") as fh:
                out = fh.read()
        except OSError:
            out = ""
        if not out.strip():   # codex no escribió el archivo → stdout crudo
            out = r.stdout.decode("utf-8", errors="replace")
        return True, out
    except Exception as e:
        return False, "fallo al invocar: %s" % e
    finally:
        try:
            os.remove(outfile)
        except OSError:
            pass


# ── backend: stub (sin LLM — switching demostrable + doble de pruebas) ────
def _invoke_stub(prompt, *, model, timeout, cwd, tools, exe_override,
                 wrapper=None):
    """Responde sin LLM: WORKSPACE_HEADLESS_STUB_FILE (path) >
    WORKSPACE_HEADLESS_STUB_OUTPUT (texto inline) > eco del prompt. No tiene
    tools por construcción — cumple tools="none" trivialmente. `wrapper` se
    ignora (no hay subproceso que envolver)."""
    path = os.environ.get("WORKSPACE_HEADLESS_STUB_FILE")
    if path:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return True, fh.read()
        except OSError as e:
            return False, "stub: no pude leer %s: %s" % (path, e)
    inline = os.environ.get("WORKSPACE_HEADLESS_STUB_OUTPUT")
    if inline is not None:
        return True, inline
    return True, "STUB-ECO:\n" + (prompt or "")[:2000]


# ── registro ───────────────────────────────────────────────────────────────
_BACKENDS = {}


def register_backend(name, invoke, *, can_disable_tools, verified,
                     note=""):
    """Registra/reemplaza un backend. `invoke(prompt, *, model, timeout,
    cwd, tools, exe_override) -> (ok, out)`. `can_disable_tools` es la
    declaración de capacidad que consume el invariante de seguridad —
    declararlo True sin que sea cierto es mentirle al guard (no lo hagas)."""
    _BACKENDS[name] = {"name": name, "invoke": invoke,
                       "can_disable_tools": bool(can_disable_tools),
                       "verified": bool(verified), "note": note}


def get_backend(name):
    b = _BACKENDS.get(name)
    if b is None:
        # Registración LAZY de conectores por provider (providers/*.json →
        # connectors.register_provider_backends): al primer miss se intenta
        # una vez, así `WORKSPACE_DREAM_BACKEND=ollama` funciona sin wiring
        # extra. Fail-soft y amputable: sin connectors.py la conducta es
        # EXACTAMENTE la histórica. Los builtins jamás se pisan (el registro
        # de connectors se salta nombres ya registrados).
        try:
            import connectors
            connectors.register_provider_backends()
        except Exception:
            pass
        b = _BACKENDS.get(name)
    if b is None:
        raise UnknownBackend(
            "backend headless desconocido: %r (registrados: %s)"
            % (name, ", ".join(sorted(_BACKENDS)) or "ninguno"))
    return b


def backends():
    """Snapshot de los backends registrados (sin los callables)."""
    return {n: {k: v for k, v in b.items() if k != "invoke"}
            for n, b in _BACKENDS.items()}


register_backend("claude-code", _invoke_claude_code,
                 can_disable_tools=True, verified=True,
                 note="claude -p con disable duro: --tools '' + "
                      "--permission-mode plan + --setting-sources ''")
register_backend("codex", _invoke_codex,
                 can_disable_tools=False, verified=False,
                 note="A-VERIFICAR: sin knob confirmado de tools-off; "
                      "sandbox read-only ≠ sin tools")
register_backend("stub", _invoke_stub,
                 can_disable_tools=True, verified=True,
                 note="sin LLM; WORKSPACE_HEADLESS_STUB_OUTPUT/_FILE")


# ── el contrato ────────────────────────────────────────────────────────────
def run_headless(prompt, *, backend=DEFAULT_BACKEND, model=None, cwd=None,
                 tools=TOOLS_NONE, timeout=DEFAULT_TIMEOUT,
                 exe_override=None, wrapper=None, env_extra=None,
                 kill_group=False):
    """Invoca el LLM headless por el backend pedido. Devuelve (ok, out).

    `wrapper` (opcional): argv-prefix del SO que envuelve al subproceso —
    p.ej. `["sandbox-exec", "-p", <perfil>]` para confinar al agente real
    (F1). Solo lo consumen los backends que ejecutan un binario (claude-code,
    codex); se pasa SOLO cuando no es None, así los backends de red
    (connectors) no ven un kwarg que no aceptan.

    Levanta (errores de CONFIGURACIÓN, no transitorios — el caller no debe
    reintentarlos):
      · UnknownBackend        — backend no registrado
      · HeadlessSecurityError — tools="none" con un backend que no puede
                                deshabilitar tools (INVARIANTE; sin bypass)
      · ValueError            — `tools` fuera del vocabulario del contrato
    """
    if tools not in _VALID_TOOLS:
        raise ValueError("tools inválido: %r (válidos: %s)"
                         % (tools, ", ".join(_VALID_TOOLS)))
    b = get_backend(backend)
    if tools in (TOOLS_NONE, TOOLS_GEN) and not b["can_disable_tools"]:
        raise HeadlessSecurityError(
            "el backend %r no puede deshabilitar tools y se pidió tools=%r "
            "— destilación/generación exigen LLM sin manos (contenido no "
            "confiable / artefacto generado). Backend rechazado; verifica/usa "
            "un backend con can_disable_tools=True." % (backend, tools))
    extra = {"wrapper": wrapper} if wrapper is not None else {}
    if env_extra is not None:         # solo backends exec lo aceptan (claude-code)
        extra["env_extra"] = env_extra
    if kill_group:
        extra["kill_group"] = True
    return b["invoke"](prompt, model=model, timeout=timeout, cwd=cwd,
                       tools=tools, exe_override=exe_override, **extra)
