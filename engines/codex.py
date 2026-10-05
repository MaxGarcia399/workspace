"""WORKSPACE · engines/codex.py — motor Codex (OpenAI Codex CLI · login ChatGPT).

Hace EJECUTABLE la cuenta ChatGPT/Codex que el socio ya conectó: un agente
puede CORRER en su plan ChatGPT vía el CLI oficial `codex`. Vendor-neutral,
enchufable por nombre — `dispatch.py` lo carga solo (guion→guion_bajo:
"codex" → engines/codex.py); NO se toca el dispatcher (engines/CONTRACT.md).

🔴 INVARIANTE DE SEGURIDAD (mismo de connectors): la SUSCRIPCIÓN del socio la
gestiona el BINARIO OFICIAL con su propio login en ~/.codex — WORKSPACE JAMÁS
lee ni extrae ni reusa el token (jamás toca ~/.codex/auth.json). El estado de
sesión se consulta con `codex login status` (no con el token).

Tres formas de correr, según el contrato de WORKSPACE:
  · INTERACTIVO — `launch()`: banner + delega al wrapper neutral
    (interactive.run_official_cli_interactive: session_start → TUI `codex` en
    el cerebro → session_end). Es el `dispatch.py <agente> --engine codex`.
  · HEADLESS one-shot — `run_turn()`: `codex exec` no-interactivo, prompt por
    stdin, respuesta limpia vía --output-last-message. Es lo que prueba que la
    cuenta EJECUTA (smoke real) y lo que reusa headless/eval.
  · INGESTA — sesiones crudas en ~/.codex/sessions → neutral_transcript.parse_codex
    (post-hoc; el schema neutral workspace.transcript).

Flags CONFIRMADOS contra `codex exec --help` (codex-cli 0.144): `-m/--model`,
`-s/--sandbox {read-only|workspace-write|danger-full-access}`, `--skip-git-repo-
check`, `--color never`, `-o/--output-last-message <file>`, prompt por stdin
con `-`. NADA inventado.

Seguridad / sandbox (🔴 REVISA ARGUS): por default lo más CONTENIDO que corre —
headless = `read-only` (solo lecturas); interactivo = `workspace-write`
(escribe solo dentro del cerebro, red restringida, approvals OnRequest). Nunca
`--dangerously-bypass-*`. Override por `engine_config.sandbox` en agent.json.

MODELO (fix de prod): con login ChatGPT, codex AUTO-ELIGE el modelo que la
cuenta soporta (hoy `gpt-5.6-sol`) y RECHAZA con 400 cualquier `-m` ajeno
(gpt-5, gpt-5-codex → verificado contra la cuenta real). Por eso WORKSPACE NO
pasa `-m` por default — ni el override per-máquina ni engine_config. Escape
hatch avanzado: env WORKSPACE_CODEX_MODEL=<id de TU cuenta> (ver _resolve_model).

Cero dependencias (stdlib, 3.9+). Mac/Windows. Falla-suave.
"""
import calendar
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

META = {"name": "codex", "needs": ["codex"], "auth": "subscription"}

#: Matriz de capacidades (contrato harness-os §3; la consume harnesses.py).
CAPABILITIES = {
    "launch": "wrapper",          # TUI oficial envuelto en el ciclo neutral
    "inject_context": "project-doc",  # AGENTS.md puntero → doc de identidad
    "mcp": True,                  # codex soporta MCP servers (config propia)
    "hooks": False,               # sin hook-system expuesto
    "sessions": "workspace",        # pestañas del registro NEUTRAL (sessions_
                                  # registry) + resume con `codex resume <id>`
                                  # (binding post-hoc del session_id del rollout)
    "status_live": False,         # sin now.json desde dentro (sin hooks)
    "statusline": "native-config",  # barra nativa configurada por corrida
                                    # (-c tui.status_line; VERIFICADO 0.160)
    "headless": True,             # run_turn (codex exec, verificado v0.144)
}

BINARY = "codex"
#: Postura de sandbox por default (contenida). Override: engine_config.sandbox.
SANDBOX_HEADLESS = "read-only"        # one-shot: solo lecturas
SANDBOX_INTERACTIVE = "workspace-write"   # sesión: escribe solo al workspace
#: Modos de sandbox ALCANZABLES desde config (agent.json / API). `danger-full-
#: access` NO está aquí a propósito (M1 · Argus): apaga disco+red+approvals; un
#: agent.json/config jamás debe poder llegar a él. Solo se habilita con opt-in
#: RUIDOSO por env (banner rojo + trato N3) — ver _sandbox()/_full_access_ok().
_SANDBOX_SAFE = ("read-only", "workspace-write")
_SANDBOX_FULL = "danger-full-access"
#: Env de opt-in explícito para full-access (per-máquina, N3). Sin esto, ningún
#: path de config llega a full-access.
_FULL_ACCESS_ENV = "WORKSPACE_CODEX_ALLOW_FULL_ACCESS"

#: Política de aprobación ANCLADA por WORKSPACE (L1 · Argus): no dependemos del
#: default de codex (podría cambiar). `on-request` = el modelo pide aprobación
#: cuando toca algo sensible. El socio puede pasar su propio `-a` (gana).
APPROVAL_POLICY = "on-request"

#: Cache corto de session_active — no spamear `codex login status` por tick.
_SESSION_TTL = 30.0
_session_cache = {"ts": 0.0, "val": None}


def _full_access_ok():
    """¿Está el opt-in RUIDOSO de full-access activo? (env per-máquina). Sin
    esto, `danger-full-access` NO es alcanzable desde config alguna."""
    return os.environ.get(_FULL_ACCESS_ENV, "").strip().lower() in (
        "1", "true", "yes", "on", "si", "sí")

#: Cache corto de session_active — no spamear `codex login status` por tick.
_SESSION_TTL = 30.0
_session_cache = {"ts": 0.0, "val": None}


def _exe(override=None):
    """Ruta al binario. override=None → busca en PATH; override="" → NO hay
    binario (explícito, para tests); override="/ruta" → esa ruta."""
    if override is None:
        return shutil.which(BINARY)
    return override or None


def session_active(exe_override=None, runner=None):
    """¿Hay sesión de codex ACTIVA (login del socio)? Vía `codex login status`
    — rápido, sin red pesada, y JAMÁS toca el token/auth.json. Cache 30s (se
    salta con runner de test). Falla-suave → False."""
    now = time.time()
    if (runner is None and _session_cache["val"] is not None
            and now - _session_cache["ts"] < _SESSION_TTL):
        return _session_cache["val"]
    exe = _exe(exe_override)
    if not exe:
        val = False
    else:
        try:
            if runner is not None:
                r = runner([exe, "login", "status"])
            else:
                r = subprocess.run([exe, "login", "status"],
                                   capture_output=True, text=True, timeout=15,
                                   encoding="utf-8", errors="replace")
            out = ((getattr(r, "stdout", "") or "")
                   + (getattr(r, "stderr", "") or "")).lower()
            val = (getattr(r, "returncode", 1) == 0
                   and ("logged in" in out or "chatgpt" in out))
        except Exception:
            val = False
    if runner is None:
        _session_cache.update(ts=now, val=val)
    return val


def available(exe_override=None):
    """LISTO para ejecutar agentes: binario en PATH + sesión activa. Es lo que
    el config TUI usa para marcar codex 'listo' (no 'en construcción')."""
    return bool(_exe(exe_override) and session_active(exe_override))


def status(exe_override=None):
    """Estado honesto del motor (para doctor / plan / picker). Solo inspecciona."""
    exe = _exe(exe_override)
    active = session_active(exe_override) if exe else False
    return {"engine": "codex", "binary": BINARY, "binary_in_path": bool(exe),
            "session_active": active, "ready": bool(exe and active),
            "auth": "subscription ChatGPT — login del CLI (WORKSPACE nunca ve "
                    "el token)"}


# Escape hatch AVANZADO y explícito para forzar el modelo de codex (a tu propio
# riesgo): env WORKSPACE_CODEX_MODEL=<id>. Solo para quien conozca el modelo que
# SU cuenta ChatGPT soporta. Sin esto, WORKSPACE NO pasa -m (ver _resolve_model).
_CODEX_MODEL_ENV = "WORKSPACE_CODEX_MODEL"


def _resolve_model(cfg):
    """Modelo para el `-m` de codex. Por DEFAULT VACÍO → codex AUTO-ELIGE el
    modelo que la cuenta ChatGPT soporta (hoy `gpt-5.6-sol`; robusto ante
    renombres).

    🔴 POR QUÉ NO FORZAMOS -m: con login ChatGPT, codex RECHAZA con
    400 invalid_request_error cualquier modelo ajeno — verificado contra la
    cuenta real: `gpt-5` y `gpt-5-codex` dan 400 ("not supported when using
    Codex with a ChatGPT account"); SIN -m funciona y codex elige `gpt-5.6-sol`.
    Por eso NO usamos el override per-máquina `agentes.<n>.model` (pensado para
    los alias de Claude / con ids que codex-ChatGPT no soporta) ni
    engine_config.model. La ÚNICA vía de forzar es el env WORKSPACE_CODEX_MODEL
    (opt-in explícito, a tu riesgo). Falla-suave → ""."""
    forced = os.environ.get(_CODEX_MODEL_ENV, "").strip()
    return forced or ""


def _resolve_sandbox(requested, default):
    """Resuelve un modo de sandbox pedido (por config o API) a uno EFECTIVO,
    con el gate de seguridad M1 (Argus):
      · read-only / workspace-write → se honran.
      · danger-full-access → SOLO si el opt-in ruidoso por env está activo
        (_full_access_ok); si no, cae al `default` seguro (config JAMÁS apaga
        el sandbox por sí sola).
      · vacío / valor raro → default seguro.
    Devuelve (modo_efectivo, pidio_full_sin_permiso: bool)."""
    sb = str(requested or "").strip()
    if not sb:
        return default, False
    if sb in _SANDBOX_SAFE:
        return sb, False
    if sb == _SANDBOX_FULL:
        if _full_access_ok():
            return _SANDBOX_FULL, False          # opt-in explícito (banner rojo)
        return default, True                     # pedido pero SIN permiso → gate
    return default, False                        # valor desconocido → seguro


def _sandbox(cfg, default):
    """Modo de sandbox EFECTIVO desde engine_config.sandbox (con el gate M1).
    Un `danger-full-access` en el agent.json NO apaga el sandbox salvo opt-in
    por env — cae al default contenido."""
    ec = (cfg or {}).get("engine_config") or {}
    mode, _blocked = _resolve_sandbox(ec.get("sandbox"), default)
    return mode


def run_turn(prompt, *, model=None, cwd=None, timeout=120, sandbox=None,
             exe_override=None, runner=None):
    """UN turno HEADLESS real contra el plan ChatGPT del socio: `codex exec`
    no-interactivo. El prompt entra por STDIN (con `-`) — nunca como arg, así
    un prompt que empiece con `--` no se cuela como flag. La respuesta limpia
    sale por --output-last-message (el stdout de codex mezcla logs). Devuelve
    (ok, texto). sandbox default read-only (contenido). NUNCA extrae el token.

    Flags verificados contra `codex exec --help` v0.144. `runner`/`exe_override`
    son knobs de test (la suite JAMÁS toca la red ni un codex real)."""
    exe = _exe(exe_override)
    if not exe:
        return False, "codex no está en PATH"
    # M1: el sandbox pedido pasa por el mismo gate — `danger-full-access` no es
    # alcanzable sin el opt-in por env (aunque se pase explícito por la API).
    sb, _blocked = _resolve_sandbox(sandbox, SANDBOX_HEADLESS)
    # L2: TODO el trabajo con efectos (mkstemp incluido) va DENTRO del try —
    # un cwd inescribible / disco lleno devuelve (False, msg), jamás escapa.
    outfile = None
    try:
        if cwd:
            os.makedirs(cwd, exist_ok=True)
        fd, outfile = tempfile.mkstemp(prefix="workspace-codex-", suffix=".txt",
                                       dir=cwd or None)
        os.close(fd)
        cmd = [exe, "exec", "--sandbox", sb, "--skip-git-repo-check",
               "--color", "never", "--output-last-message", outfile]
        if model:
            cmd += ["--model", model]
        cmd += ["-"]                   # prompt por stdin (anti flag-injection)
        env = dict(os.environ)
        env["WORKSPACE_REVIEW_RUNNING"] = "1"
        env["WORKSPACE_NO_AUTOUPDATE"] = "1"
        if runner is not None:
            r = runner(cmd, cwd=cwd or None, env=env, timeout=timeout,
                       input=prompt or "")
        else:
            r = subprocess.run(cmd, cwd=cwd or None, env=env, timeout=timeout,
                               input=(prompt or "").encode("utf-8"),
                               capture_output=True)
        rc = getattr(r, "returncode", 1)
        if rc != 0:
            raw = getattr(r, "stderr", b"") or b""
            err = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            return False, "codex exec exit %d: %s" % (rc, err[:300])
        out = ""
        try:
            with open(outfile, encoding="utf-8", errors="replace") as fh:
                out = fh.read()
        except OSError:
            out = ""
        if not out.strip():           # no escribió el archivo → stdout crudo
            raw = getattr(r, "stdout", b"") or b""
            out = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        return True, out
    except subprocess.TimeoutExpired:
        return False, "codex exec: timeout tras %ss" % timeout
    except OSError as e:               # L2: cwd inescribible / mkstemp / disco
        return False, "codex exec: no pude preparar la corrida: %s" % e
    except Exception as e:
        return False, "codex exec: fallo al invocar: %s" % e
    finally:
        if outfile:
            try:
                os.remove(outfile)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════════════════
# Statusline — la info de abajo estilo Claude Code (capability `status` §3)
# ═══════════════════════════════════════════════════════════════════════════
# Codex 0.160.0 SÍ trae un status line configurable — VERIFICADO contra su
# fuente real (codex-rs/tui/src/bottom_pane/status_line_setup.rs, mismo tag
# que el binario instalado): `[tui] status_line = [<ids kebab-case>]`, con
# items nativos para TODO lo medible: `context-remaining`/`context-used` (%
# de contexto), `five-hour-limit` (límite primario ≈ "uso sesión"),
# `weekly-limit` (límite secundario ≈ "uso semanal"), `model`, `permissions`
# (sandbox activo), `approval-mode`, `git-branch`, `used-tokens`, etc. Los
# datos de límites salen de la cuenta ChatGPT del socio vía el propio codex
# (RateLimitWindow: used_percent/resets_at) — WORKSPACE no fabrica números.
#
# El adapter lo activa con un override POR CORRIDA (`-c 'tui.status_line=
# […]'`) — jamás escribe la preferencia persistida del socio. Precedencia:
#   1. el socio ya fijó su status line (config.toml `[tui] status_line`, o
#      un -c propio en el comando) → WORKSPACE no agrega nada (lo suyo gana);
#   2. engine_config.status_line (lista de ids) en agent.json → esa;
#   3. default de WORKSPACE (espejo de la barra de Claude Code).
# Opt-out total: WORKSPACE_CODEX_NO_STATUSLINE=1 (queda la barra nativa).
#
# LÍMITES HONESTOS (lo que codex NO expone como item): el nombre del AGENTE
# como texto libre (lo más cercano: `project-name` = carpeta del cerebro),
# el "brain vX" de WORKSPACE, el tiempo "activa Xm" y el costo $ en cuentas
# no-Enterprise (`estimated-thread-cost` se omite solo). Sin hook-system ni
# item custom, eso no se puede inyectar en SU barra — queda para la vista
# del hub (pestañas/now.json). El launch añade codex_status: una barra
# de Workspace vía tmux con reinicios/uptime; no modifica el binario ni su TUI.

#: Items default (ids kebab-case REALES del enum StatusLineItem de codex).
STATUS_LINE_DEFAULT = ("model", "context-remaining", "five-hour-limit",
                       "weekly-limit", "permissions", "approval-mode")
_NO_STATUSLINE_ENV = "WORKSPACE_CODEX_NO_STATUSLINE"
#: Saneo de ids (van DENTRO de un literal TOML que armamos): solo kebab-case.
_SL_ID_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def _user_has_status_line():
    """¿El socio ya fijó `status_line` en el `[tui]` de su config.toml de
    codex? (su elección persistida de /statusline — se respeta). Lectura de
    texto, sin parser TOML (stdlib 3.9). Falla-suave → False."""
    try:
        with open(_codex_config_path(), encoding="utf-8",
                  errors="replace") as fh:
            section = ""
            for ln in fh:
                s = ln.strip()
                if s.startswith("[") and s.endswith("]"):
                    section = s
                elif section == "[tui]" and re.match(r"^status_line\s*=", s):
                    return True
    except Exception:
        pass
    return False


def _status_line_args(cfg, passthrough):
    """Flags `-c tui.status_line=[…]` para la corrida, o [] si el socio ya
    tiene la suya / opt-out / ids inválidos. Los ids se sanean (van dentro
    de un literal TOML construido aquí — un agent.json raro no inyecta)."""
    if os.environ.get(_NO_STATUSLINE_ENV, "").strip():
        return []
    for a in passthrough or []:
        # el socio trae su propio override de status line en el comando
        if str(a).replace(" ", "").startswith(("tui.status_line=",
                                               "-ctui.status_line=")):
            return []
    if _user_has_status_line():
        return []
    ec = (cfg or {}).get("engine_config") or {}
    items = ec.get("status_line") or STATUS_LINE_DEFAULT
    if not isinstance(items, (list, tuple)):
        return []
    clean = [str(i) for i in items if _SL_ID_RX.match(str(i))]
    if not clean:
        return []
    toml_list = "[" + ", ".join('"%s"' % i for i in clean) + "]"
    return ["-c", "tui.status_line=%s" % toml_list]


def _interactive_argv(cfg, passthrough, resume_sid="", first_prompt=""):
    """argv DESPUÉS de `codex` para la sesión interactiva: -s <sandbox>,
    -a <approval> (anclado por WORKSPACE), -m <model> (si el socio no lo pasó
    explícito), -c tui.status_line=… (info de abajo estilo Claude Code) +
    passthrough del socio.

    Pestañas (registro neutral — sessions_registry):
      · `resume_sid` → la sesión se REANUDA: `codex resume <id> [flags]`
        (VERIFICADO 0.160: resume acepta -s/-a/-m/-c igual que el TUI nuevo)
        y SIN prompt de arranque (la conversación ya tiene el contexto).
      · `first_prompt` → pestaña nueva en un harness sin hooks: el arranque
        + la memoria de ESA pestaña van como primer prompt (paridad honesta
        con el hook SessionStart de Claude Code).
    Sin estos kwargs el comportamiento es EXACTAMENTE el histórico."""
    argv = []
    pt = list(passthrough or [])
    resume_sid = str(resume_sid or "").strip()
    # El socio dueño del comando gana: si él ya trae resume/fork en el
    # passthrough, WORKSPACE no mete el suyo.
    if resume_sid and not any(str(a) in ("resume", "fork") for a in pt):
        argv += ["resume", resume_sid]
    sb = _sandbox(cfg, SANDBOX_INTERACTIVE)
    argv += ["-s", sb]
    # L1: anclar la política de aprobación (no depender del default de codex).
    # Si el socio pasó su propio -a/--ask-for-approval, gana (no se duplica).
    has_appr = any(str(a) in ("-a", "--ask-for-approval")
                   or str(a).startswith("--ask-for-approval=") for a in pt)
    if not has_appr:
        argv += ["-a", APPROVAL_POLICY]
    has_model = any(str(a) in ("-m", "--model") or str(a).startswith("--model=")
                    for a in pt)
    model = _resolve_model(cfg)
    if model and not has_model:
        argv += ["-m", model]
    argv += _status_line_args(cfg, pt)
    # A bare hub launch starts boot immediately. Explicit prompts, flags and
    # resume/fork commands remain owned by the caller. Al REANUDAR no se
    # inyecta prompt (el hilo ya está en contexto; el socio sigue donde iba).
    if not pt and not resume_sid:
        pt = [first_prompt or "Inicia el cerebro."]
    return argv + pt


# ═══════════════════════════════════════════════════════════════════════════
# Saldo/límites SIN gastar tokens — snapshot de los rollouts locales
# ═══════════════════════════════════════════════════════════════════════════
# codex guarda en cada sesión (~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl)
# eventos `token_count` con `rate_limits`: primary (ventana 5h · 300 min) y
# secondary (semanal · 10080 min), cada una con used_percent + resets_at
# (epoch), más plan_type. VERIFICADO contra los rollouts reales de codex
# 0.160.0 — es LA MISMA fuente que alimenta su statusline (five-hour-limit /
# weekly-limit). Leerla es I/O local puro: 0 tokens, 0 red, y JAMÁS toca
# auth.json (invariante de seguridad: transcripts sí, credenciales no).
# HONESTO: el snapshot tiene la EDAD de la última corrida — se devuelve `at`
# para que la UI lo diga tal cual; si `resets_at` ya pasó, esa ventana ya se
# reinició (la UI debe tratarla como llena, no como el % viejo).

_RL_TTL = 30.0                 # cache corto — no re-escanear el disco por tick
_rl_cache = {"ts": 0.0, "val": None}
_RL_TAIL = 262_144             # leer solo la COLA de cada rollout (son largos)
_RL_FILES = 8                  # revisar a lo más N rollouts recientes


def _sessions_root():
    home = os.environ.get("CODEX_HOME") or os.path.join(
        os.path.expanduser("~"), ".codex")
    return os.path.join(home, "sessions")


def _recent_rollouts(root, limit=_RL_FILES):
    """Los rollouts más recientes, más nuevos primero. El nombre del archivo
    EMBEBE su timestamp (rollout-YYYY-MM-DDThh-mm-ss-…) y los dirs son
    YYYY/MM/DD → ordenar strings al revés = cronología inversa, sin stat."""
    out = []
    try:
        for base, dirs, files in os.walk(root):
            dirs.sort(reverse=True)
            out.extend(os.path.join(base, f)
                       for f in sorted(files, reverse=True)
                       if f.endswith(".jsonl"))
            if len(out) >= limit:
                break
    except Exception:
        pass
    return out[:limit]


def _last_rate_limits(path):
    """El ÚLTIMO evento rate_limits de UN rollout, o None. Lee solo la cola
    del archivo y recorre las líneas al revés. Falla-suave absoluta."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > _RL_TAIL:
                fh.seek(size - _RL_TAIL)
            data = fh.read().decode("utf-8", "replace")
    except Exception:
        return None
    for ln in reversed(data.splitlines()):
        if '"rate_limits"' not in ln:
            continue
        try:
            ev = json.loads(ln)
        except ValueError:
            continue                    # línea cortada por el seek — seguir
        rl = (ev.get("payload") or {}).get("rate_limits") or {}
        if not rl.get("primary") and not rl.get("secondary"):
            continue
        ts = str(ev.get("timestamp") or "")
        try:                            # "2026-10-02T18:07:29.840Z" (UTC)
            at = calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            try:
                at = os.path.getmtime(path)
            except OSError:
                at = time.time()
        return {"primary": rl.get("primary") or None,
                "secondary": rl.get("secondary") or None,
                "plan_type": str(rl.get("plan_type") or ""),
                "at": float(at)}
    return None


def rate_limit_snapshot(root=None):
    """Último estado CONOCIDO de los límites de la cuenta (5h + semanal), sin
    gastar tokens: {primary, secondary, plan_type, at, age_s} o None si no
    hay rollouts legibles. `root` es knob de test (sin cache). Solo lectura —
    jamás toca auth.json ni la red."""
    now = time.time()
    if root is None and _rl_cache["val"] is not None \
            and now - _rl_cache["ts"] < _RL_TTL:
        return _rl_cache["val"]
    snap = None
    try:
        for path in _recent_rollouts(root or _sessions_root()):
            snap = _last_rate_limits(path)
            if snap:
                snap["age_s"] = max(0.0, time.time() - snap["at"])
                break
    except Exception:
        snap = None
    if root is None:
        _rl_cache.update(ts=now, val=snap)
    return snap


def _rollout_exists(sid, root=None, max_files=4000):
    """¿El rollout de `sid` sigue existiendo localmente? El session_id va
    EMBEBIDO en el nombre del archivo (rollout-<ts>-<sid>.jsonl — verificado
    0.160). Valida un resume-id ANTES de `codex resume` (sesión borrada o
    migrada → arrancar fresco, no un error en loop). Acotado y falla-suave:
    ante cualquier duda devuelve False (= fresco, el camino seguro)."""
    sid = str(sid or "").strip()
    if not sid:
        return False
    seen = 0
    try:
        for base, dirs, files in os.walk(root or _sessions_root()):
            dirs.sort(reverse=True)            # años/meses/días nuevos primero
            for f in files:
                if sid in f and f.endswith(".jsonl"):
                    return True
                seen += 1
                if seen >= max_files:
                    return False
    except Exception:
        pass
    return False


def _vendor_session_after(brain, t0, root=None, limit=16):
    """Binding POST-HOC de pestañas (sessions_registry): el `session_id` del
    rollout que ESTA corrida creó para este cerebro, o ''. VERIFICADO contra
    rollouts reales 0.160: la línea 1 es `session_meta` con payload.session_id
    + payload.cwd. Se buscan solo rollouts recientes con mtime >= t0 y
    cwd == realpath(cerebro). Solo lectura; jamás toca auth.json. Falla-suave."""
    try:
        real = os.path.realpath(brain or "")
        if not real:
            return ""
        for path in _recent_rollouts(root or _sessions_root(), limit=limit):
            try:
                if os.path.getmtime(path) < t0 - 1.0:
                    continue          # viejo — no es de esta corrida
                with open(path, "rb") as fh:
                    first = fh.readline().decode("utf-8", "replace")
                meta = json.loads(first)
                pay = meta.get("payload") or {}
                if os.path.realpath(str(pay.get("cwd") or "")) != real:
                    continue
                sid = str(pay.get("session_id") or pay.get("id") or "").strip()
                if sid:
                    return sid
            except Exception:
                continue
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# inject_context — identidad del agente vía AGENTS.md (contrato harness-os §3)
# ═══════════════════════════════════════════════════════════════════════════
# Codex NO lee CLAUDE.md: su project doc oficial es `AGENTS.md` (VERIFICADO
# contra el binario 0.160.0: keys `project_doc_max_bytes` /
# `project_doc_fallback_filenames`, scope = árbol del directorio que lo
# contiene, y AGENTS.md es contenido CONFIABLE para el modelo). El adapter
# genera en la raíz del cerebro un AGENTS.md **puntero** que manda leer el
# doc de identidad del agente — JAMÁS duplica la identidad (el cerebro es la
# única fuente de verdad; reescribirla sería N3). El doc de identidad default
# es `CLAUDE.md`; un agente puede declarar otro con `identity_doc` en su
# agent.json (hueco harness-agnóstico del agente-spec).
#
# Reglas de convivencia (falla-suave SIEMPRE, jamás rompe el launch):
#   · AGENTS.md no existe            → se crea (marcado GENERADO).
#   · existe CON la marca WORKSPACE    → se re-sincroniza si el texto cambió.
#   · existe con la marca LEGACY (pre-rename OLYMPUS) → es NUESTRO: se
#     re-sincroniza (migración automática a la marca nueva).
#   · existe SIN marca (del socio)   → su CONTENIDO no se toca; el bloque de
#     sesión va ANEXADO al final, marcado y efímero (strip al cerrar +
#     strip-antes-de-anexar en cada launch) — fix 2026-10-04: antes la
#     memoria de la pestaña caía al primer prompt VISIBLE.
#   · no hay doc de identidad        → no se genera nada (un puntero a la
#     nada confunde más que un codex genérico honesto).

#: Primera línea EXACTA de un AGENTS.md generado — es el detector de "es
#: nuestro, se puede re-sincronizar". No cambiar sin migración.
_GEN_MARK = "<!-- WORKSPACE:GENERATED inject_context v1 -->"
#: Marca pre-rename (OLYMPUS→Workspace 2026-10): los cerebros existentes aún
#: la traen; sin reconocerla el doc generado parecía "del socio" y la memoria
#: caía al primer prompt visible. Solo se LEE (detección); se escribe siempre
#: la nueva.
_GEN_MARK_LEGACY = "<!-- OLYMPUS:GENERATED inject_context v1 -->"


def _is_generated(text):
    """¿El AGENTS.md es NUESTRO (marca actual o legacy pre-rename)?"""
    head = (text or "").lstrip()
    return head.startswith(_GEN_MARK) or head.startswith(_GEN_MARK_LEGACY)

#: Doc de identidad por default (convención de los cerebros). Override por
#: agente: "identity_doc" en agent.json.
DEFAULT_IDENTITY_DOC = "CLAUDE.md"


def _identity_doc(cfg):
    """Nombre del doc de identidad del agente (relativo al cerebro). Saneado:
    un path absoluto o con separadores se rechaza (el doc vive en la RAÍZ del
    cerebro; un agent.json no debe apuntar fuera — misma defensa SEC que
    expand_scripts). Falla-suave → default."""
    d = str((cfg or {}).get("identity_doc") or "").strip()
    if not d or os.path.isabs(d) or "/" in d or "\\" in d or d.startswith(".."):
        return DEFAULT_IDENTITY_DOC
    return d


def _agents_doc_text(cfg, session_context=""):
    """Texto del AGENTS.md generado: PUNTERO al doc de identidad, cero
    contenido de identidad duplicado. Genérico — nada de agentes/rutas
    nuestros horneados (el nombre sale del cfg en runtime). `session_context`
    agrega el bloque GENERADO de la pestaña activa (ver _SESSION_START)."""
    doc = _identity_doc(cfg)
    name = str(cfg.get("display") or cfg.get("name") or "el agente")
    return """%s
<!-- Archivo GENERADO por WORKSPACE (engines/codex.py · inject_context).
     NO editarlo a mano: el adapter lo re-sincroniza en cada launch.
     Si este cerebro deja de usarse con codex, puede borrarse sin efecto.
     La identidad NO vive aquí: vive en %s (única fuente de verdad). -->

# Identidad de este workspace

Este directorio es el CEREBRO de **%s**. Su identidad, reglas, memoria y
protocolo de arranque viven en `%s` (raíz de este directorio) y en los
documentos que ese archivo indica.

AL INICIAR LA SESIÓN, ANTES DE CUALQUIER OTRA COSA:

1. Lee `%s` COMPLETO.
2. Sigue su secuencia de arranque (los documentos que manda leer, en orden)
   y adopta ESA identidad, reglas y tono. No te presentes como "Codex" ni
   como un asistente genérico: eres %s corriendo sobre el motor codex.
3. Ante cualquier conflicto entre este archivo y `%s`, gana `%s`.
""" % (_GEN_MARK, doc, name, doc, doc, name, doc, doc) + (
        "" if not session_context else
        "\n%s\n%s\n%s\n" % (_SESSION_START, session_context, _SESSION_END))


#: Marcas del bloque de SESIÓN dentro del AGENTS.md generado — inyección
#: INVISIBLE de la pestaña activa (el socio no ve este contexto en el chat).
#: Se regenera en cada launch y se LIMPIA al cerrar (restore post-run); un
#: launch sin pestaña también lo elimina (re-sync al texto base).
_SESSION_START = "<!-- WORKSPACE:SESSION start — contexto de la pestaña activa; se regenera en cada launch -->"
_SESSION_END = "<!-- WORKSPACE:SESSION end -->"
#: Marcas pre-rename (solo LECTURA: un bloque viejo de una corrida OLYMPUS
#: también debe poder limpiarse — había huérfanos reales en los cerebros).
_SESSION_STARTS = (_SESSION_START,
                   "<!-- OLYMPUS:SESSION start — contexto de la pestaña activa; se regenera en cada launch -->")
_SESSION_ENDS = (_SESSION_END, "<!-- OLYMPUS:SESSION end -->")


def _split_session_block(text):
    """(texto_sin_bloque, había_bloque). Corta por LÍNEAS completas entre las
    marcas (actuales o legacy) — contenido con `-->` adentro no rompe el
    corte, y el resto del archivo queda byte-a-byte intacto."""
    out, skip, found = [], False, False
    for ln in (text or "").splitlines(True):
        s = ln.strip()
        if not skip and s in _SESSION_STARTS:
            skip, found = True, True
            continue
        if skip:
            if s in _SESSION_ENDS:
                skip = False
            continue
        out.append(ln)
    return "".join(out), found


def _strip_session_block(brain):
    """Quita el bloque de sesión del AGENTS.md — generado O del socio (solo
    corta entre nuestras marcas; el contenido del socio queda intacto).
    Limpieza al cerrar: el contexto de la pestaña era de ESTA corrida.
    Idempotente y falla-suave (False si no había bloque o ante error)."""
    try:
        p = os.path.join(brain or "", "AGENTS.md")
        if not brain or not os.path.isfile(p):
            return False
        with open(p, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        base, found = _split_session_block(txt)
        if not found:
            return False
        tmp = p + ".workspace-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(base.rstrip() + "\n")
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def inject_context(cfg, session_context=""):
    """Materializa la identidad del agente en el formato que ESTE harness
    entiende (contrato §3): AGENTS.md puntero en la raíz del cerebro.
    `session_context` (opcional) agrega el bloque de la pestaña activa —
    inyección SILENCIOSA: codex lo lee como project doc, no como mensaje.
    AGENTS.md del socio → su contenido se respeta y el bloque va ANEXADO
    al final (marcado, strip-antes-de-anexar, se limpia al cerrar).
    Devuelve {'ok', 'action': created|synced|kept|custom|skipped, 'path',
    'detail'} + 'session': 'appended' cuando el bloque quedó anexado a un
    doc del socio (el caller sabe que NO hace falta el fallback visible).
    Falla-suave: errores → skipped con detail, jamás levanta."""
    brain = (cfg or {}).get("_brain", "")
    out = {"ok": False, "action": "skipped", "path": "", "detail": ""}
    try:
        if not brain or not os.path.isdir(brain):
            out["detail"] = "sin cerebro resuelto"
            return out
        doc = _identity_doc(cfg)
        if not os.path.isfile(os.path.join(brain, doc)):
            out["detail"] = "no existe %s en el cerebro — nada que apuntar" % doc
            return out
        path = os.path.join(brain, "AGENTS.md")
        out["path"] = path
        want = _agents_doc_text(cfg, session_context=session_context)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    cur = fh.read()
            except OSError as e:
                out["detail"] = "AGENTS.md ilegible: %s" % e
                return out
            if not _is_generated(cur):
                # AGENTS.md PROPIO del socio → su contenido se respeta; el
                # bloque de sesión va ANEXADO (marcado, efímero) para que la
                # memoria llegue INVISIBLE igual que con el doc generado.
                # strip-antes-de-anexar: un bloque huérfano (crash de una
                # corrida previa) se auto-limpia aquí mismo.
                try:
                    base, had = _split_session_block(cur)
                    if session_context:
                        body = (base.rstrip() + "\n\n%s\n%s\n%s\n"
                                % (_SESSION_START, session_context,
                                   _SESSION_END))
                        tmp = path + ".workspace-tmp"
                        with open(tmp, "w", encoding="utf-8") as fh:
                            fh.write(body)
                        os.replace(tmp, path)
                        out.update(ok=True, action="custom",
                                   session="appended",
                                   detail="AGENTS.md del socio — bloque de "
                                          "sesión anexado (marcado; se "
                                          "limpia al cerrar)")
                    elif had:
                        tmp = path + ".workspace-tmp"
                        with open(tmp, "w", encoding="utf-8") as fh:
                            fh.write(base.rstrip() + "\n")
                        os.replace(tmp, path)
                        out.update(ok=True, action="custom",
                                   detail="AGENTS.md del socio — bloque de "
                                          "sesión viejo limpiado")
                    else:
                        out.update(ok=True, action="custom",
                                   detail="AGENTS.md del socio (sin marca) "
                                          "— intacto")
                except Exception as e:
                    # No se pudo anexar (disco/permiso): el doc del socio
                    # queda como estaba y el caller cae al camino visible.
                    out.update(ok=True, action="custom",
                               detail="AGENTS.md del socio — anexo falló "
                                      "(%s: %s)" % (type(e).__name__, e))
                return out
            if cur == want:
                out.update(ok=True, action="kept")
                return out
            action = "synced"
        else:
            action = "created"
        tmp = path + ".workspace-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(want)
        os.replace(tmp, path)            # escritura atómica (no medio-archivo)
        out.update(ok=True, action=action)
        return out
    except Exception as e:
        out["detail"] = "%s: %s" % (type(e).__name__, e)
        return out


# ═══════════════════════════════════════════════════════════════════════════
# Auto-trust del cerebro — comodidad, NO bypass (contrato: solo onboarding)
# ═══════════════════════════════════════════════════════════════════════════
# Codex marca carpetas de confianza en ~/.codex/config.toml:
#     [projects."<path>"]
#     trust_level = "trusted"
# (VERIFICADO contra el config.toml real — codex lo escribe así cuando el
# socio contesta el prompt "do you trust this folder"). Lo ÚNICO que hace es
# saltarse ese prompt de onboarding al abrir el cerebro: el sandbox
# (workspace-write) y la approval policy (on-request) que WORKSPACE ancla en el
# argv SIGUEN exactamente igual — esto no habilita nada que el socio no
# tuviera ya al contestar "sí" a mano. Reglas:
#   · solo se auto-confía el CEREBRO del agente (carpeta que el socio ya
#     eligió conscientemente al cargar el agente) — nada más.
#   · si el path YA tiene una entrada [projects."…"] (cualquier trust_level,
#     incluso negativo) → NO SE TOCA: la decisión del socio gana.
#   · opt-out: WORKSPACE_CODEX_NO_AUTOTRUST=1.
#   · falla-suave: si no se puede escribir, codex simplemente preguntará
#     como siempre.

_NO_AUTOTRUST_ENV = "WORKSPACE_CODEX_NO_AUTOTRUST"


def _codex_config_path():
    home = os.environ.get("CODEX_HOME") or os.path.join(
        os.path.expanduser("~"), ".codex")
    return os.path.join(home, "config.toml")


def _toml_key_escape(path):
    """Path → contenido de un basic string TOML ("..."): escapa \\ y \"."""
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def ensure_trusted(brain):
    """Agrega `[projects."<brain>"] trust_level = "trusted"` al config.toml
    de codex si el path NO tiene entrada aún. Devuelve {'ok', 'action':
    added|exists|skipped, 'detail'}. Append puro con stdlib (3.9 no trae
    writer TOML); jamás reescribe lo existente. Falla-suave."""
    out = {"ok": False, "action": "skipped", "detail": ""}
    try:
        if os.environ.get(_NO_AUTOTRUST_ENV, "").strip():
            out["detail"] = "opt-out por %s" % _NO_AUTOTRUST_ENV
            return out
        if not brain or not os.path.isdir(brain):
            out["detail"] = "sin cerebro resuelto"
            return out
        real = os.path.realpath(brain)
        cfgp = _codex_config_path()
        cur = ""
        if os.path.exists(cfgp):
            with open(cfgp, encoding="utf-8", errors="replace") as fh:
                cur = fh.read()
        header = '[projects."%s"]' % _toml_key_escape(real)
        # ¿ya hay entrada para ESTE path (trusted o no)? → decisión del socio.
        for ln in cur.splitlines():
            if ln.strip() == header:
                out.update(ok=True, action="exists")
                return out
        os.makedirs(os.path.dirname(cfgp), exist_ok=True)
        block = "%s%s\ntrust_level = \"trusted\"\n" % (
            ("" if (not cur or cur.endswith("\n\n")) else
             ("\n" if cur.endswith("\n") else "\n\n")), header)
        with open(cfgp, "a", encoding="utf-8") as fh:
            fh.write(block)
        out.update(ok=True, action="added")
        return out
    except Exception as e:
        out["detail"] = "%s: %s" % (type(e).__name__, e)
        return out


def _banner(cfg):
    """Arranque visible mínimo (Windows-safe: sin glifos 0x2600–0x27BF)."""
    name = str(cfg.get("display") or cfg.get("name", "agente")).upper()
    tag = str(cfg.get("tagline", ""))
    C = "\033[38;5;214m"; D = "\033[38;5;240m"; R = "\033[0m"; B = "\033[1m"
    bar = C + "═" * 52 + R
    try:
        sys.stdout.write("\033[2J\033[3J\033[H")
        print("\n  %s" % bar)
        print("    %s%s%s%s   %svía Codex (ChatGPT)%s" % (B, C, name, R, D, R))
        if tag:
            print("    %s%s%s" % (D, tag, R))
        print("  %s\n" % bar)
        sys.stdout.flush()
    except Exception:
        pass


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    """Arranca un agente EN CODEX (interactivo). Delega al wrapper neutral de
    interactive.py (session_start → TUI `codex` → session_end). plan=True NO
    lanza: imprime el wiring + chequeos."""
    brain = cfg.get("_brain", "")
    model = _resolve_model(cfg)
    sandbox = _sandbox(cfg, SANDBOX_INTERACTIVE)
    exe = _exe()
    active = session_active() if exe else False

    if plan:
        line = "─" * 66
        print(line)
        print("  WORKSPACE · plan de arranque — motor CODEX — agente: %s"
              % cfg.get("display", cfg.get("name")))
        print(line)
        print("  motor       : codex  (CLI oficial · login ChatGPT del socio; "
              "WORKSPACE nunca ve el token)")
        print("  modelo      : %s" % (model or "(el default de codex)"))
        print("  sandbox     : %s (interactivo; headless one-shot = %s)"
              % (sandbox, SANDBOX_HEADLESS))
        print("  approval    : %s (anclado por WORKSPACE)" % APPROVAL_POLICY)
        if sandbox == _SANDBOX_FULL:
            print("  !! FULL-ACCESS: sandbox APAGADO (disco+red, sin approvals) "
                  "— opt-in por %s (N3)." % _FULL_ACCESS_ENV)
        print("  cerebro     : %s" % brain)
        print("  identidad   : AGENTS.md puntero → %s (inject_context; codex "
              "no lee %s solo)" % (_identity_doc(cfg), DEFAULT_IDENTITY_DOC))
        print("  trust       : auto-confía el cerebro en ~/.codex/config.toml "
              "(solo salta el prompt de onboarding; opt-out %s)"
              % _NO_AUTOTRUST_ENV)
        print("  pestañas    : picker compartido + registro neutral — resume: "
              "`codex resume <id>` (validado vs rollouts); memoria de la "
              "pestaña va INVISIBLE en el AGENTS.md generado (se limpia al "
              "cerrar); id atado post-hoc")
        sl = _status_line_args(cfg, passthrough)
        print("  statusline  : %s"
              % (("-c %s  (por corrida; su /statusline persistido gana; "
                  "opt-out %s)" % (sl[1], _NO_STATUSLINE_ENV)) if sl
                 else "la del socio / nativa (sin override de WORKSPACE)"))
        print("  flujo       : inject_context → trust → banner → "
              "interactive.run_official_cli_interactive('codex') → codex -s "
              "%s%s (TUI en el cerebro)"
              % (sandbox, (" -m %s" % model) if model else ""))
        print(line)
        print("  [%s] binario codex en PATH: %s"
              % ("✓" if exe else "✗ FALTA", exe or "(no está)"))
        print("  [%s] sesión activa (codex login): %s"
              % ("✓" if active else "✗", "sí" if active else
                 "no — corre `codex login`"))
        print("  [%s] cerebro: %s"
              % ("✓" if brain and os.path.isdir(brain) else "✗ FALTA", brain))
        print(line)
        return

    if not exe:
        print("WORKSPACE: codex no está en PATH — instálalo "
              "(`npm i -g @openai/codex`) y corre `codex login`.")
        sys.exit(1)
    if not active:
        print("WORKSPACE: no hay sesión de codex activa — corre `codex login` "
              "(ChatGPT) y reintenta. WORKSPACE nunca toca tu token.")
        sys.exit(1)

    # Motor+modelo REAL en el banner (dinámico — regla del socio). Codex con
    # login ChatGPT AUTO-ELIGE el modelo salvo el env de escape (ver
    # _resolve_model) — etiqueta honesta en ambos casos.
    os.environ["WORKSPACE_ENGINE_LABEL"] = (
        "Codex · " + (model or "auto (cuenta ChatGPT)"))
    # Banner del CEREBRO (patrón buffered+width-check compartido). Caveat
    # honesto: el TUI de codex es full-screen (alt-screen) — el banner se ve
    # al arrancar y queda tapado durante el chat; reaparece al salir.
    if show_banner:
        try:
            from engines import _ui
            _ui.show_brain_banner(cfg)
        except Exception:
            _banner(cfg)              # fallback mínimo de siempre

    # Pestañas NEUTRALES (sessions_registry): el MISMO picker de Claude Code
    # corre aquí (subproceso, agnóstico) → misma lista de pestañas en todos
    # los motores. La elección trae el uuid de claude-code; el resume-id de
    # CODEX sale del registro (atado post-hoc en una corrida previa) y se
    # VALIDA contra los rollouts locales: un id huérfano (sesión borrada /
    # `codex migrate-rollouts`) arranca fresco y se re-bindea — jamás un
    # loop de `codex resume <id-muerto>`.
    tab, resume_sid, session_blk = None, "", ""
    agent = str(cfg.get("name") or "")
    try:
        from engines import _ui
        import sessions_registry as _reg
        tab = _ui.pick_tab(cfg, preselect=preselect)
        if tab:
            wid, wname = tab
            _ui.export_tab_env(cfg, wid, wname)
            _reg.ensure_tab(brain, agent, wname, claude_wid=wid)
            resume_sid = _reg.resume_id(brain, agent, wname, "codex")
            if resume_sid and not _rollout_exists(resume_sid):
                resume_sid = ""       # id local huérfano → fresco + re-bind
            session_blk = _reg.session_doc_block(brain, wname)
    except Exception:
        tab, resume_sid, session_blk = None, "", ""

    # inject_context (contrato §3): identidad + bloque de la PESTAÑA ACTIVA
    # — inyección INVISIBLE (project doc, no un mensaje en el chat). Doc
    # GENERADO → bloque adentro; doc PROPIO del socio → bloque ANEXADO al
    # final (marcado, se limpia al cerrar). Solo si ni el anexo se pudo
    # escribir, la memoria cae al primer prompt (visible — último recurso).
    first_prompt = ""
    inj = inject_context(cfg, session_context=session_blk)
    if not inj.get("ok") and inj.get("detail"):
        print("WORKSPACE: identidad NO inyectada (%s) — codex arrancará "
              "genérico." % inj["detail"])
    if tab and inj.get("action") == "custom" and not inj.get("session") \
            and not resume_sid:
        try:
            import sessions_registry as _reg
            first_prompt = _reg.first_prompt_context(brain, tab[1])
            print("WORKSPACE: no pude anexar la memoria al AGENTS.md del "
                  "socio — irá en el primer mensaje (visible).")
        except Exception:
            first_prompt = ""
    # auto-trust del cerebro (comodidad: salta el prompt "do you trust this
    # folder" de codex; sandbox y approvals de WORKSPACE siguen intactos).
    ensure_trusted(brain)

    # M1: si el sandbox EFECTIVO es full-access (solo posible con el opt-in
    # ruidoso por env), avisar en ROJO — el socio ve que el sandbox está
    # APAGADO. Un agent.json solo JAMÁS llega aquí.
    if sandbox == _SANDBOX_FULL:
        RED = "\033[1;38;5;196m"; R = "\033[0m"
        try:
            print("%s  ############################################%s" % (RED, R))
            print("%s  !! CODEX FULL-ACCESS — SANDBOX APAGADO       %s" % (RED, R))
            print("%s  !! disco completo + red + SIN approvals      %s" % (RED, R))
            print("%s  !! activo por %s (N3)%s"
                  % (RED, _FULL_ACCESS_ENV, R))
            print("%s  ############################################%s\n" % (RED, R))
            sys.stdout.flush()
        except Exception:
            pass

    argv = _interactive_argv(cfg, passthrough, resume_sid=resume_sid,
                             first_prompt=first_prompt)

    _doc_dirty = []       # ¿quedó contexto de corrida en el AGENTS.md?

    def _ctx_sink(ctx):
        # El contexto neutral de arranque también va INVISIBLE al AGENTS.md
        # (antes el wrapper lo IMPRIMÍA en la terminal). Doc del socio → el
        # bloque va ANEXADO (marcado, se limpia al cerrar); solo si ni eso
        # se pudo escribir, se imprime (último canal honesto). Jamás levanta.
        try:
            merged = "\n\n".join(p for p in (session_blk,
                                             (ctx or "").strip()) if p)
            if not merged:
                return
            r = inject_context(cfg, session_context=merged)
            if r.get("ok") and (r.get("action") != "custom"
                                or r.get("session") == "appended"):
                _doc_dirty.append(True)
            elif (ctx or "").strip():
                print("[WORKSPACE · contexto de arranque]\n%s\n" % ctx.strip())
        except Exception:
            pass

    t0 = time.time()
    try:
        import interactive
        import codex_status
        rc = interactive.run_official_cli_interactive(
            "codex", brain=brain or None, argv=argv, context_sink=_ctx_sink,
            runner=lambda cmd, **kw: codex_status.run(cmd, cfg, env=kw.get("env")))
    except Exception as e:
        print("WORKSPACE: no pude lanzar codex interactivo (%s: %s)"
              % (type(e).__name__, e))
        sys.exit(1)
    # Limpieza (session_end): el bloque de sesión/contexto del AGENTS.md era
    # de ESTA corrida — doc generado → se restaura el puntero base (sin
    # bloque); doc del socio → se le quita el bloque anexado (strip) y queda
    # byte-a-byte como era. Best-effort; un crash deja un bloque huérfano que
    # el strip-antes-de-anexar del siguiente launch auto-limpia.
    if session_blk or _doc_dirty:
        try:
            inject_context(cfg)
        except Exception:
            pass
    # Binding POST-HOC: la sesión que codex creó/usó para este cerebro queda
    # atada a la pestaña → la próxima vez `codex resume <id>`. Se bindea si
    # DIFIERE del id con que entramos (cubre: pestaña nueva, resume huérfano
    # que arrancó fresco, fork del socio). Best-effort.
    if tab:
        try:
            import sessions_registry as _reg
            sid = _vendor_session_after(brain, t0)
            if sid and sid != resume_sid:
                _reg.bind(brain, agent, tab[1], "codex", sid)
        except Exception:
            pass
    sys.exit(rc if isinstance(rc, int) else 0)


def pick(cfg):
    """El picker de pestañas ahora es COMPARTIDO (registro neutral): la misma
    elección cruda ('WS\\t<wid>\\t<name>') que claude_code.pick — lo usa el
    hub tmux (mux.py). Falla-suave → ''."""
    try:
        from engines import claude_code as _cc
        return _cc.pick(cfg)
    except Exception:
        return ""
