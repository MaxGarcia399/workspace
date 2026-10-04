"""WORKSPACE · engines/gemini.py — motor Gemini CLI (Google · login del socio).

Hace ejecutable la cuenta Google/Gemini del socio vía el CLI oficial `gemini`
(npm `@google/gemini-cli`). Vendor-neutral, enchufable por nombre — dispatch.py
lo carga solo ("gemini" → engines/gemini.py); NO se toca el dispatcher
(engines/CONTRACT.md).

🔴 INVARIANTE DE SEGURIDAD (mismo de connectors/codex): la cuenta del socio la
gestiona el BINARIO OFICIAL con su propio login (OAuth en ~/.gemini / env
GEMINI_API_KEY) — WORKSPACE JAMÁS lee, extrae ni reusa credenciales (jamás toca
~/.gemini/oauth_creds.json; solo constata que el archivo EXISTE, como señal).

Flags CONFIRMADOS contra `gemini --help` (gemini-cli 0.40.1, binario real de
esta máquina — 2026-10-01): `-m/--model`, `-p/--prompt` ("non-interactive
(headless) mode… Appended to input on stdin (if any)"), `--approval-mode
{default|auto_edit|yolo|plan}` (plan = read-only), `-o/--output-format
{text|json|stream-json}`, `-r/--resume`, `gemini mcp` / `gemini hooks`.
NADA inventado.

⚠ A-VERIFICAR (honestidad): una CORRIDA real no se ha hecho — esta máquina no
tiene login de gemini (sin ~/.gemini/oauth_creds.json ni GEMINI_API_KEY). El
wiring de flags está verificado por --help; la semántica E2E (stdin+`-p ""`,
formato del stdout) queda pendiente del primer `gemini` logueado. Al
verificarla, quitar este aviso y marcar `verified` en
interactive.INTERACTIVE_CLIS.

Seguridad / aprobaciones (espejo del gate M1 de codex): por default lo más
CONTENIDO — headless = `--approval-mode plan` (read-only); interactivo =
`--approval-mode default` (pide aprobación por acción), ANCLADO por WORKSPACE
(no dependemos del default del CLI). WORKSPACE JAMÁS agrega `--yolo`/`-y` ni
`--approval-mode yolo` desde config; solo el socio tecleándolo en su comando
(explícito gana y no se duplica).

A diferencia de codex, la falta de login NO bloquea el launch interactivo: el
propio CLI corre su flujo OAuth en el primer arranque (bloquearlo impediría
loguearse). Solo se AVISA. El headless (run_turn) sí exige señal de auth.

Cero dependencias (stdlib, 3.9+). Mac/Windows. Falla-suave.
"""
import os
import shutil
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

META = {"name": "gemini", "needs": ["gemini"], "auth": "subscription"}

#: Matriz de capacidades (contrato harness-os §3; la consume harnesses.py).
CAPABILITIES = {
    "launch": "wrapper",          # TUI oficial envuelto en el ciclo neutral
    "inject_context": "print",    # el contexto se imprime al socio (honesto)
    "mcp": True,                  # `gemini mcp` (verificado en --help 0.40.1)
    "hooks": True,                # `gemini hooks` existe; WORKSPACE aún NO los cablea
    "sessions": "vendor",         # `gemini --resume` (verificado en --help)
    "status_live": False,         # sin now.json desde dentro (hooks sin cablear)
    "headless": True,             # run_turn (-p; corrida E2E A-VERIFICAR)
}

BINARY = "gemini"

#: Env de override de MODELO (opt-in explícito per-máquina). Sin esto, y sin
#: engine_config.model, NO se pasa -m: el CLI elige el modelo de la cuenta.
_GEMINI_MODEL_ENV = "WORKSPACE_GEMINI_MODEL"

#: Política de aprobación ANCLADA por WORKSPACE (espejo del L1 de codex — no
#: dependemos del default del CLI). Verificadas en --help 0.40.1:
#:   plan     = read-only (el headless corre así: solo lecturas)
#:   default  = pide aprobación por acción (la sesión interactiva)
#: `yolo`/`auto_edit` NUNCA los agrega WORKSPACE — solo el socio, explícito.
APPROVAL_HEADLESS = "plan"
APPROVAL_INTERACTIVE = "default"

#: Flags de aprobación que, si el socio los pasa, GANAN (no se duplica nada).
_APPROVAL_FLAGS = ("-y", "--yolo", "--approval-mode")


def _exe(override=None):
    """Ruta al binario. override=None → PATH; override="" → no hay (tests);
    override="/ruta" → esa ruta."""
    if override is None:
        return shutil.which(BINARY)
    return override or None


def _auth_signal():
    """Señal HEURÍSTICA de auth (sin correr el binario ni tocar contenido):
    ~/.gemini/oauth_creds.json existe (login OAuth previo) o hay API key en
    el entorno. Solo EXISTENCIA del archivo — jamás se lee. Puede dar falso
    negativo con métodos de auth nuevos → por eso solo AVISA, no bloquea el
    interactivo. Falla-suave → ""."""
    try:
        if (os.environ.get("GEMINI_API_KEY") or "").strip():
            return "api-key (GEMINI_API_KEY)"
        if (os.environ.get("GOOGLE_API_KEY") or "").strip():
            return "api-key (GOOGLE_API_KEY)"
        creds = os.path.join(os.path.expanduser("~"), ".gemini",
                             "oauth_creds.json")
        if os.path.isfile(creds):
            return "oauth (login previo del CLI)"
    except Exception:
        pass
    return ""


def session_active(exe_override=None):
    """¿Hay señal de auth? (heurística, ver _auth_signal). A diferencia de
    codex no hay subcomando `login status` documentado — no se spawnea nada."""
    return bool(_exe(exe_override)) and bool(_auth_signal())


def available(exe_override=None):
    """LISTO para ejecutar: binario en PATH + señal de auth."""
    return bool(_exe(exe_override) and session_active(exe_override))


def status(exe_override=None):
    """Estado honesto del motor (para doctor / plan / harnesses.registry)."""
    exe = _exe(exe_override)
    sig = _auth_signal() if exe else ""
    return {"engine": "gemini", "binary": BINARY, "binary_in_path": bool(exe),
            "session_active": bool(sig),
            # ready = binario presente: el login lo resuelve el propio CLI en
            # el primer arranque (no bloquear por heurística de auth).
            "ready": bool(exe),
            "auth": sig or ("sin señal de login — el CLI abre su OAuth al "
                            "arrancar, o exporta GEMINI_API_KEY"),
            "verified": False}     # ⚠ flags de docs públicas, sin corrida real


def _resolve_model(cfg):
    """Modelo para `-m`: env WORKSPACE_GEMINI_MODEL (explícito del socio) >
    engine_config.model del agent.json > "" (el CLI elige). Falla-suave."""
    forced = os.environ.get(_GEMINI_MODEL_ENV, "").strip()
    if forced:
        return forced
    try:
        ec = (cfg or {}).get("engine_config") or {}
        m = str(ec.get("model") or "").strip()
        return m
    except Exception:
        return ""


def run_turn(prompt, *, model=None, cwd=None, timeout=120,
             exe_override=None, runner=None):
    """UN turno HEADLESS: `-p ""` fuerza el modo no-interactivo y el prompt
    entra por STDIN (el --help confirma: el -p se APPENDEA al stdin — así un
    prompt que empiece con `--` jamás se cuela como flag, igual que codex).
    Read-only anclado (`--approval-mode plan`) + salida `-o text`.
    ⚠ A-VERIFICAR la corrida E2E (flags confirmados por --help 0.40.1; sin
    login en esta máquina no se pudo correr). Devuelve (ok, texto).
    `runner`/`exe_override` son knobs de test (la suite jamás corre un CLI
    real ni toca la red)."""
    exe = _exe(exe_override)
    if not exe:
        return False, "gemini no está en PATH"
    if runner is None and not session_active(exe_override):
        return False, ("sin señal de login de gemini — corre `gemini` una vez "
                       "(OAuth) o exporta GEMINI_API_KEY")
    cmd = [exe, "--approval-mode", APPROVAL_HEADLESS, "-o", "text", "-p", ""]
    if model:
        cmd += ["-m", model]
    try:
        if cwd:
            os.makedirs(cwd, exist_ok=True)
        env = dict(os.environ)
        env["WORKSPACE_NO_AUTOUPDATE"] = "1"
        if runner is not None:
            r = runner(cmd, cwd=cwd or None, env=env, timeout=timeout,
                       input=prompt or "")
        else:
            r = subprocess.run(cmd, cwd=cwd or None, env=env, timeout=timeout,
                               input=(prompt or "").encode("utf-8"),
                               capture_output=True)
        rc = getattr(r, "returncode", 1)
        raw_out = getattr(r, "stdout", b"") or b""
        out = raw_out.decode("utf-8", "replace") if isinstance(raw_out, bytes) \
            else str(raw_out)
        if rc != 0:
            raw = getattr(r, "stderr", b"") or b""
            err = raw.decode("utf-8", "replace") if isinstance(raw, bytes) \
                else str(raw)
            return False, "gemini exit %d: %s" % (rc, (err or out)[:300])
        return True, out
    except subprocess.TimeoutExpired:
        return False, "gemini: timeout tras %ss" % timeout
    except OSError as e:
        return False, "gemini: no pude preparar la corrida: %s" % e
    except Exception as e:
        return False, "gemini: fallo al invocar: %s" % e


def _interactive_argv(cfg, passthrough):
    """argv DESPUÉS de `gemini` para la sesión interactiva: --approval-mode
    default (anclado por WORKSPACE — pide aprobación por acción) + -m <model>
    (si el socio no pasó el suyo) + passthrough. Si el socio pasó su propio
    -y/--yolo/--approval-mode, GANA (no se duplica). JAMÁS se agrega yolo
    desde aquí (gate M1 espejo de codex: config no apaga aprobaciones)."""
    argv = []
    pt = list(passthrough or [])
    has_appr = any(str(a) in _APPROVAL_FLAGS
                   or str(a).startswith("--approval-mode=") for a in pt)
    if not has_appr:
        argv += ["--approval-mode", APPROVAL_INTERACTIVE]
    has_model = any(str(a) in ("-m", "--model") or str(a).startswith("--model=")
                    for a in pt)
    model = _resolve_model(cfg)
    if model and not has_model:
        argv += ["-m", model]
    return argv + pt


def _banner(cfg):
    """Arranque visible mínimo (Windows-safe: sin glifos 0x2600–0x27BF)."""
    name = str(cfg.get("display") or cfg.get("name", "agente")).upper()
    tag = str(cfg.get("tagline", ""))
    C = "\033[38;5;75m"; D = "\033[38;5;240m"; R = "\033[0m"; B = "\033[1m"
    bar = C + "═" * 52 + R
    try:
        sys.stdout.write("\033[2J\033[3J\033[H")
        print("\n  %s" % bar)
        print("    %s%s%s%s   %svía Gemini CLI (Google)%s" % (B, C, name, R, D, R))
        if tag:
            print("    %s%s%s" % (D, tag, R))
        print("  %s\n" % bar)
        sys.stdout.flush()
    except Exception:
        pass


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    """Arranca un agente EN GEMINI CLI (interactivo). Delega al wrapper neutral
    de interactive.py (session_start → TUI `gemini` → session_end). plan=True
    NO lanza: imprime el wiring + chequeos."""
    brain = cfg.get("_brain", "")
    model = _resolve_model(cfg)
    exe = _exe()
    sig = _auth_signal()

    if plan:
        line = "─" * 66
        print(line)
        print("  WORKSPACE · plan de arranque — motor GEMINI — agente: %s"
              % cfg.get("display", cfg.get("name")))
        print(line)
        print("  motor       : gemini  (CLI oficial · login Google del socio; "
              "WORKSPACE nunca ve credenciales)")
        print("  modelo      : %s" % (model or "(el default del CLI)"))
        print("  aprobación  : %s (anclado por WORKSPACE; headless = %s/read-only"
              " — jamás --yolo desde config)"
              % (APPROVAL_INTERACTIVE, APPROVAL_HEADLESS))
        print("  cerebro     : %s" % brain)
        print("  flujo       : banner → interactive.run_official_cli_interactive"
              "('gemini') → gemini --approval-mode %s%s (TUI en el cerebro)"
              % (APPROVAL_INTERACTIVE, (" -m %s" % model) if model else ""))
        print("  ⚠ A-VERIFICAR: flags confirmados por --help 0.40.1; corrida "
              "E2E pendiente del primer login")
        print(line)
        print("  [%s] binario gemini en PATH: %s"
              % ("✓" if exe else "✗ FALTA", exe or
                 "(no está — npm install -g @google/gemini-cli)"))
        print("  [%s] señal de auth: %s"
              % ("✓" if sig else "·",
                 sig or "ninguna — el CLI abre su OAuth al arrancar"))
        print("  [%s] cerebro: %s"
              % ("✓" if brain and os.path.isdir(brain) else "✗ FALTA", brain))
        print(line)
        return

    if not exe:
        print("WORKSPACE: gemini no está en PATH — instálalo "
              "(`npm install -g @google/gemini-cli`) y arranca una vez "
              "(`gemini`) para el login de Google.")
        sys.exit(1)
    if not sig:
        # NO bloquea: el primer arranque del CLI corre su propio OAuth.
        print("WORKSPACE: sin señal de login de gemini — si es tu primer "
              "arranque, el CLI te pedirá iniciar sesión con Google.")

    if show_banner:
        _banner(cfg)

    argv = _interactive_argv(cfg, passthrough)
    try:
        import interactive
        rc = interactive.run_official_cli_interactive(
            "gemini", brain=brain or None, argv=argv)
    except Exception as e:
        print("WORKSPACE: no pude lanzar gemini interactivo (%s: %s)"
              % (type(e).__name__, e))
        sys.exit(1)
    sys.exit(rc if isinstance(rc, int) else 0)


def pick(cfg):
    """gemini gestiona sus propias sesiones — sin picker de pestañas propio."""
    return ""


# Compatibility for existing gemini bindings: interactive launches use agy.
from engines.antigravity import launch, pick, META, CAPABILITIES, status
