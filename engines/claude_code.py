"""Adapter del motor Claude Code para WORKSPACE.

Generaliza el launcher shell de Zenith (banner → menú de pestañas → `claude --resume`)
leyendo la config del agente. Cross-platform, cero dependencias (stdlib, Python 3.9+).

Claude Code corre modelos de Anthropic vía la suscripción del socio (OAuth) — sin API key.
Es el motor premium. Otros motores (agnósticos, locales) llegan en pasos posteriores.
"""
import sys, os, re, shutil, subprocess

# La carpeta de sesiones se calcula en UN solo lugar: WORKSPACE/session_paths.py
# (resuelve symlinks con realpath, igual que Claude Code). dispatch.py ya pone la
# raíz en sys.path al importar el motor; el insert es defensivo por si alguien
# importa este módulo directo.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from session_paths import session_dir as _session_dir  # noqa: E402

META = {"name": "claude-code", "needs": ["claude"], "auth": "subscription"}

#: Matriz de capacidades (contrato harness-os §3; la consume harnesses.py).
#: Es el harness de REFERENCIA: hooks nativos, sesiones de WORKSPACE, status vivo.
CAPABILITIES = {
    "launch": "native",           # path propio: banner → picker → claude
    "inject_context": "hooks",    # inyección real (workspace_hook → neutral_hooks)
    "mcp": "native",              # MCPs de Claude Code (config del cerebro)
    "hooks": "native",            # hook-system completo (EVENTS.md)
    "sessions": "workspace",        # picker/journals propios (session_paths)
    "status_live": True,          # now.json + statusline (adapters de brand)
    "statusline": "workspace",      # la barra inferior la pintan los scripts
                                  # de brand del cerebro (statusline propia)
    "headless": True,             # headless.py / claude -p
}


def _py():
    return sys.executable or ("python" if os.name == "nt" else "python3")


def session_env_names(cfg):
    """(session_env, session_id_env) del agente. El default se DERIVA del nombre
    (<UPPER>_WS / <UPPER>_WID) — idéntico a lo que escribe agent_admin.create —
    en vez del sentinel 'ZENITH_WS'/'ZENITH_WID' que estaba hardcodeado (residuo
    de cuando zenith era el agente canónico: un agente sin session_env explícito
    heredaba el workspace de zenith → colisión). SSOT consumido por claude_code y
    por engines/_ui.export_tab_env."""
    up = ((cfg.get("name") or "").strip().upper()) or "WORKSPACE"
    return (cfg.get("session_env") or up + "_WS",
            cfg.get("session_id_env") or up + "_WID")


def _utf8_env():
    """B2 · Windows: un hijo Python capturado por un pipe usa cp1252, no UTF-8 →
    UnicodeEncodeError al imprimir box-drawing/braille (banner, dashboard).
    PYTHONUTF8=1 lo fuerza a UTF-8. No-op en Mac/Linux (UTF-8 ya es default)."""
    return {**os.environ, "PYTHONUTF8": "1"}


def auto_mode_args(passthrough, cfg=None):
    """AUTO-MODE opcional: con settings `agentes.auto_mode` ON, las sesiones
    interactivas arrancan con `--permission-mode acceptEdits`, el mecanismo
    OFICIAL de Claude Code (el mismo "accept edits on" del shift+tab).
    JAMÁS bypassPermissions ni --dangerously-skip-permissions desde aquí.

    De fábrica está OFF: mandan los permisos del cerebro (la autonomía del
    agente, ver install.render_permissions). Reversible: aplica al siguiente
    lanzamiento, sin reinstalar. Un --permission-mode (o un
    --dangerously-skip-permissions) EXPLÍCITO del socio en el comando siempre
    gana → no se agrega nada encima. Un agente con autonomía "ask" (el usuario
    apagó su acceso automático en Agentes → Enter) nunca recibe acceptEdits.
    Falla-suave: sin settings.py o store ilegible → OFF."""
    if str((cfg or {}).get("autonomy") or "").strip().lower() == "ask":
        return []
    for a in passthrough or []:
        if str(a).startswith(("--permission-mode", "--dangerously-skip-permissions")):
            return []
    on = False
    try:
        import settings as _settings
        v = _settings.get("agentes.auto_mode", False)
        if isinstance(v, bool):
            on = v
    except Exception:
        pass
    return ["--permission-mode", "acceptEdits"] if on else []


def model_args(cfg, passthrough):
    """Override de modelo POR AGENTE (settings `agentes.<nombre>.model` —
    sección MODELOS del config): si el socio fijó un modelo para este agente,
    el lanzamiento lleva `--model <ese>`. Precedencia (lo explícito gana):
      1. `--model`/`--model=` del socio en el comando → no se agrega nada.
      2. env ANTHROPIC_MODEL → no se agrega nada (Claude Code la honra solo;
         meter --model encima la pisaría).
      3. settings `agentes.<nombre>.model` (no vacío) → ["--model", <eso>].
      4. nada configurado → [] (el modelo que el agente/Claude Code decida).
    Compatible con --resume y --session-id (Claude Code acepta --model en
    ambos). Falla-suave: sin settings.py / store roto / agente sin nombre →
    [] (todo como antes)."""
    for a in passthrough or []:
        if str(a) == "--model" or str(a).startswith("--model="):
            return []
    if (os.environ.get("ANTHROPIC_MODEL") or "").strip():
        return []
    try:
        import settings as _settings
        name = str((cfg or {}).get("name") or "").strip().lower()
        if not name:
            return []
        v = _settings.get("agentes.%s.model" % name, "")
        if isinstance(v, str) and v.strip():
            return ["--model", v.strip()]
    except Exception:
        pass
    return []


def _engine_label(cfg, passthrough=()):
    """Motor + modelo REAL de la corrida para el banner (regla del socio: el
    banner dice con qué se carga, dinámico — nada de modelos hardcodeados).
    El engine lo exporta en WORKSPACE_ENGINE_LABEL y los banners lo leen.
    Precedencia del modelo: --model del socio > override per-máquina
    (settings agentes.<n>.model) > ANTHROPIC_MODEL > agent.json."""
    mdl = ""
    pt = [str(a) for a in (passthrough or [])]
    for i, a in enumerate(pt):              # --model X | --model=X del socio
        if a == "--model" and i + 1 < len(pt):
            mdl = pt[i + 1]; break
        if a.startswith("--model="):
            mdl = a.split("=", 1)[1]; break
    if not mdl:
        ma = model_args(cfg, passthrough)
        mdl = ma[1] if len(ma) == 2 else ""
    mdl = mdl or (os.environ.get("ANTHROPIC_MODEL") or "").strip() \
        or str((cfg or {}).get("model") or "").strip()
    return "Claude Code" + (" · " + mdl if mdl else "")


_REDACT = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|(?i:bearer)\s+[A-Za-z0-9._-]{8,}|"
                     r"(?i:(token|api[_-]?key|password|secret))\s*[=:]\s*\S+)")

#: Último error del picker de pestañas (U04/Z04) — lo lee el motor que lo
#: invocó para AVISAR en vez de caer en silencio a un chat sin pestaña.
LAST_PICK_ERROR = ""


def session_log_path():
    try:
        import paths
        return os.path.join(paths.workspace_dir(), "logs", "session-open.log")
    except Exception:
        return ""


def _session_log(cfg, engine, error, detail=""):
    """Traza LOCAL y redactada de una apertura de sesión fallida: agente,
    motor, cerebro, causa y cola del stderr (sin secretos, ≤2 KB). Sirve
    para reproducir el incidente de sesiones (Z04) sin adivinar la causa."""
    p = session_log_path()
    if not p:
        return ""
    try:
        import datetime
        import json as _json
        os.makedirs(os.path.dirname(p), exist_ok=True)
        rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "agent": cfg.get("name", ""), "engine": engine,
               "brain": cfg.get("_brain", ""), "error": error,
               "detail": _REDACT.sub("[redactado]", (detail or "")[-2048:]),
               "platform": sys.platform}
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(_json.dumps(rec, ensure_ascii=False) + "\n")
        return p
    except Exception:
        return ""


def back_to_hub():
    """Esc en el menú de sesiones: si el agente se abrió DESDE el hub
    (WORKSPACE_FROM_HUB, lo pone front.launch), se reabre el hub; si se
    abrió desde el shell, se sale limpio. No regresa."""
    if os.environ.get("WORKSPACE_FROM_HUB") == "1":
        front = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "front.py")
        argv = [sys.executable, front]
        env = _utf8_env()                # B2: UTF-8 también en el hub reabierto
        env.pop("WORKSPACE_FROM_HUB", None)
        if os.name == "nt":
            sys.exit(subprocess.run(argv, env=env).returncode)
        os.execve(sys.executable, argv, env)
    sys.exit(0)


def run_dashboard_pick(cfg, py, dashboard, engine="claude-code"):
    """Corre `dashboard --pick` y devuelve (choice, error).
    choice = 'WS\\t<wid>\\t<name>' o ''. error = '' si el picker terminó
    bien; si no, la CAUSA legible (exit code + última línea del stderr) — y
    queda trazada en session_log_path(). Antes cualquier fallo devolvía ''
    y el motor abría un chat sin pestaña SIN decir por qué."""
    global LAST_PICK_ERROR
    LAST_PICK_ERROR = ""
    if not dashboard or not os.path.exists(dashboard):
        err = "sin selector de pestañas (dashboard ausente: %s)" % (dashboard or "—")
        LAST_PICK_ERROR = err
        _session_log(cfg, engine, err)
        return "", err
    try:
        r = subprocess.run([py, dashboard, "--pick"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           env=_utf8_env())
    except Exception as e:
        err = "no pude correr el selector (%s: %s)" % (type(e).__name__, e)
        LAST_PICK_ERROR = err
        _session_log(cfg, engine, err)
        return "", err
    out = r.stdout if isinstance(getattr(r, "stdout", None), str) else ""
    errtxt = r.stderr if isinstance(getattr(r, "stderr", None), str) else ""
    rc = r.returncode if isinstance(getattr(r, "returncode", None), int) else 0
    choice = out.strip()
    if rc == 0 and choice.startswith("WS\t"):
        return choice, ""
    if rc == 0 and choice == "BACK":
        back_to_hub()
    tail = [ln for ln in errtxt.strip().splitlines() if ln.strip()]
    err = "el selector de pestañas terminó con código %s%s" % (
        rc, (": " + _REDACT.sub("[redactado]", tail[-1][:200])) if tail else
        (" sin elegir pestaña" if rc == 0 else ""))
    LAST_PICK_ERROR = err
    _session_log(cfg, engine, err, errtxt)
    return "", err


def warn_no_tab(err):
    """Aviso visible cuando una sesión arranca SIN pestaña por un fallo."""
    if not err:
        return
    p = session_log_path()
    try:
        sys.stdout.write("\nWORKSPACE: %s — abro una conversación SIN pestaña "
                         "(la memoria de pestaña no se carga).%s\n"
                         % (err, (" Diagnóstico: %s" % p) if p else ""))
        sys.stdout.flush()
    except Exception:
        pass


def session_preflight(cfg, engine):
    """Avisa (y traza) ANTES del picker si la pestaña abriría sin memoria.
    No bloquea el launch: la sesión arranca igual, pero el socio sabe por qué."""
    try:
        import sessions_registry as _reg
        issues = _reg.preflight(cfg.get("_brain", ""))
    except Exception:
        issues = []
    for msg in issues:
        _session_log(cfg, engine, msg)
        try:
            sys.stdout.write("WORKSPACE: %s\n" % msg)
            sys.stdout.flush()
        except Exception:
            pass
    return issues


def pick(cfg):
    """Corre solo el menú interactivo del agente y devuelve la elección cruda
    ('WS\\t<wid>\\t<name>') sin lanzar nada. Lo usa el hub tmux (mux.py) y
    el picker compartido de los motores wrapper. Si falla, la causa queda en
    LAST_PICK_ERROR y en el log de apertura (no se traga en silencio)."""
    import agent_ui
    agent_ui.export_context(cfg)
    os.environ["WORKSPACE_ENGINE_LABEL"] = _engine_label(cfg)
    dashboard = (cfg.get("_scripts") or {}).get("dashboard")
    if cfg.get("_brain"):   # los scripts viven en WORKSPACE; el cerebro va por env
        os.environ["WORKSPACE_BRAIN"] = cfg["_brain"]
    choice, _err = run_dashboard_pick(cfg, _py(), dashboard,
                                      engine=cfg.get("_engine") or "claude-code")
    return choice


_COLOR_CODE = {"blue": 39, "red": 196, "green": 46, "pink": 213, "violet": 141,
               "purple": 141, "wine": 131, "cyan": 51, "gold": 220, "coral": 209,
               "gray": 244, "gris": 244}


def _generic_banner(cfg):
    """Agent title with the active theme when no illustration is available."""
    import agent_ui
    cols = shutil.get_terminal_size((80,24)).columns
    name = cfg.get('display') or cfg.get('name', 'agente')
    sys.stdout.write('\n'.join(agent_ui.heading(name,cfg.get('tagline',''),cols))+'\n')
    sys.stdout.flush()


import re as _re, unicodedata as _ud   # noqa: E402
_CSI = _re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _max_visual_width(text):
    """Ancho visual máximo (sin ANSI; CJK/Hangul cuentan 2) de un bloque de texto."""
    mx = 0
    for line in text.split("\n"):
        s = _CSI.sub("", line)
        w = sum(2 if _ud.east_asian_width(c) in ("W", "F") else 1 for c in s)
        if w > mx:
            mx = w
    return mx


def _too_narrow_banner(cfg, cols, need):
    """Use the agent title when the full illustration cannot fit."""
    import agent_ui
    name = cfg.get('display') or cfg.get('name', 'agente')
    sys.stdout.write('\n'.join(agent_ui.heading(name, cfg.get('tagline', ''), cols)) + '\n')
    sys.stdout.flush()


def launch(cfg, passthrough, plan=False, preselect=None, show_banner=True):
    import agent_ui
    agent_ui.export_context(cfg)
    # motor+modelo REAL de esta corrida → lo leen banner y picker (dinámico)
    os.environ["WORKSPACE_ENGINE_LABEL"] = _engine_label(cfg, passthrough)
    brain = cfg["_brain"]
    # Los scripts de UI (banner/dashboard/statusline) viven en WORKSPACE y resuelven
    # su cerebro por env — exportarlo aquí cubre banner, dashboard y subprocesos.
    os.environ["WORKSPACE_BRAIN"] = brain
    scripts = cfg["_scripts"]
    banner = scripts.get("banner")
    dashboard = scripts.get("dashboard")
    session_env, wid_env = session_env_names(cfg)
    py = _py()

    # Utilidades passthrough: `<agente> ls` / `<agente> migrar`
    if passthrough and passthrough[0] in ("ls", "list", "migrar", "migracion"):
        flag = "--list" if passthrough[0] in ("ls", "list") else "--migracion"
        if not dashboard:
            return
        if plan:
            print(f"[plan] correría: {py} {dashboard} {flag}   (cwd={brain})")
            return
        subprocess.run([py, dashboard, flag], cwd=brain)
        return

    if plan:
        sdir = _session_dir(brain)
        line = "─" * 66
        print(line)
        print(f"  WORKSPACE · plan de arranque — agente: {cfg.get('display', cfg.get('name'))}")
        print(line)
        print(f"  motor       : claude-code  (Anthropic vía suscripción, sin API key)")
        auto = auto_mode_args(passthrough, cfg)
        try:
            import install as _inst
            _aut = _inst.autonomy_of(cfg)
        except Exception:
            _aut = "brain"
        print(f"  permisos    : " + ("auto-mode (--permission-mode acceptEdits) — "
                                     "settings agentes.auto_mode on" if auto
                                     else "los del cerebro — autonomía '%s' (.claude/"
                                          "settings.local.json)" % _aut))
        ma = model_args(cfg, passthrough)
        print(f"  modelo      : " + (f"override --model {ma[1]} (settings "
                                     f"agentes.{cfg.get('name','?')}.model)" if ma
                                     else "el del agente (sin override; settings agentes.<n>.model lo fija)"))
        print(f"  cerebro     : {brain}")
        print(f"  banner      : {banner or '(ninguno)'}")
        print(f"  dashboard   : {dashboard or '(ninguno)'}")
        print(f"  env sesión  : {session_env} / {wid_env}  (+ WORKSPACE_WS / WORKSPACE_WID genéricos)")
        print(f"  python      : {py}")
        print(f"  sesiones en : {sdir}")
        try:
            import memoria as _memoria
            import settings as _settings
            _dir = _memoria.claude_memoria_dir(brain)
            if not _settings.enabled("cerebro.claude_memoria_en_cerebro", default=True):
                _mem = "la de Claude Code en esta máquina (ajuste cerebro.claude_memoria_en_cerebro apagado)"
            elif not _dir:
                _mem = "la de Claude Code en esta máquina (no se sabe quién es el socio: .claude/socio.local)"
            else:
                _mem = _dir + "  (--settings autoMemoryDirectory)"
        except Exception:
            _mem = "?"
        print(f"  memoria CC  : {_mem}")
        if preselect and preselect.get("wid"):
            print(f"  preselect   : {preselect.get('name','')} ({preselect['wid']})  → sin menú")
        print(f"  banner      : {'sí' if show_banner else 'no (modo directo)'}")
        print(f"  flujo       : "
              + ("(directo) cd cerebro → " if preselect else "banner → dashboard --pick → cd cerebro → ")
              + "claude --resume <wid>  (o --session-id <wid> --name <ws> la 1ª vez)")
        # chequeos de salud
        print(line)
        for label, path in (("banner", banner), ("dashboard", dashboard), ("cerebro", brain)):
            mark = "✓" if (path and os.path.exists(path)) else "✗ FALTA"
            print(f"  [{mark}] {label}: {path}")
        print(line)
        return

    # 1) Banner (best-effort, hereda la tty). Se omite en modo directo (tmux).
    #    Limpia ANTES del banner para que SIEMPRE salga pegado arriba — entres por el
    #    menú `workspace` (que ya limpia) o escribiendo el agente directo (`zenith`), donde
    #    antes no limpiaba nada y el banner salía cortado. Orden 2J→3J→H (ver front.py).
    #    Si el banner del cerebro NO existe (cerebro incompleto / copia vieja), cae a un
    #    banner GENÉRICO desde la def del agente → SIEMPRE hay un arranque visible.
    if show_banner:
        sys.stdout.write("\033[2J\033[3J\033[H"); sys.stdout.flush()
        cols = shutil.get_terminal_size((80, 24)).columns
        shown = False
        if banner and os.path.exists(banner):
            try:
                # Render a buffer + medir: el banner tiene ancho fijo (~114 col); si la
                # ventana es más chica NO lo mostramos roto → mensaje 'agranda' (como el hub).
                rendered = subprocess.run([py, banner], capture_output=True,
                                          text=True, encoding="utf-8",
                                          errors="replace", env=_utf8_env()).stdout
                if rendered.strip():
                    need = _max_visual_width(rendered)
                    if need <= cols:
                        # CENTRADO horizontal (regla del greeter unificado):
                        # el banner no se pega a la izquierda.
                        pad = " " * max(0, (cols - need) // 2)
                        sys.stdout.write("\n".join(
                            (pad + ln if ln.strip() else ln)
                            for ln in rendered.split("\n")))
                        sys.stdout.flush()
                    else:
                        _too_narrow_banner(cfg, cols, need)
                    shown = True
            except Exception:
                shown = False
        if not shown:
            _generic_banner(cfg)

    # 2) Elegir pestaña: preselección (tmux) o menú interactivo.
    if preselect and preselect.get("wid"):
        choice = "WS\t%s\t%s" % (preselect["wid"], preselect.get("name", ""))
    else:
        session_preflight(cfg, "claude-code")
        choice, pick_err = run_dashboard_pick(cfg, py, dashboard)
        warn_no_tab(pick_err)

    env = _utf8_env()   # B2 · PYTHONUTF8=1 lo hereda el hijo `claude` y todo lo que
                        # spawnea (hooks, statusline) → UTF-8 de punta a punta en Windows.
    env["CLAUDE_CODE_HIDE_CWD"] = "1"
    env["WORKSPACE_BRAIN"] = brain   # explícito: la statusline (hija de claude) lo lee
    import engines                            # memoria v1: el motor de cada nota
    engines.mark_session_engine(env, "claude-code")
    # which() resuelve la ruta completa del binario: imprescindible en Windows, donde
    # el shim de npm es `claude.cmd` y CreateProcess no lo encuentra por nombre pelado.
    # En Mac/Linux devuelve el mismo binario que el PATH lookup (no cambia nada).
    # auto_mode_args: opcional (settings agentes.auto_mode, OFF de fábrica)
    # — con ON la sesión interactiva arranca en acceptEdits.
    # model_args: override de modelo por agente (settings agentes.<n>.model;
    # un --model explícito del socio o ANTHROPIC_MODEL ganan — ver docstring).
    # memoria v1: `--settings` con autoMemoryDirectory → la memoria propia de
    # Claude Code se guarda en el cerebro (motores/claude-code/memoria/<socio>/,
    # una carpeta por persona), viaja con él a otras máquinas; opción
    # documentada, sin escribir su config.
    import memoria as _memoria
    cmd = ([shutil.which("claude") or "claude"]
           + auto_mode_args(passthrough, cfg) + model_args(cfg, passthrough)
           + _memoria.claude_settings_args(brain, passthrough)
           + list(passthrough))
    parts = choice.split("\t")
    if len(parts) >= 3 and parts[0] == "WS":
        wid, wname = parts[1], parts[2]
        env[session_env] = wname
        env[wid_env] = wid
        # Genéricos, agnósticos del agente: los hooks de sesión y los dashboards
        # leen WORKSPACE_WS (con fallback al env específico por back-compat).
        env["WORKSPACE_WS"] = wname
        env["WORKSPACE_WID"] = wid
        jsonl = os.path.join(_session_dir(brain), wid + ".jsonl")
        if os.path.exists(jsonl):
            cmd += ["--resume", wid]
        else:
            # Un claude instalado por npm en Windows es `claude.cmd`: el nombre
            # de la pestaña (puede venir de otra máquina) pasa por cmd.exe.
            nombre = (_memoria.argv_seguro(wname, tope=200)
                      if _memoria.pasa_por_cmd(cmd[0]) else wname)
            cmd += ["--session-id", wid, "--name", nombre or wid]
        # Modelo SINCRONIZADO de pestañas (sessions_registry): la pestaña
        # elegida/creada queda con su .md en STATE/sessions/<socio>/ — eso SÍ
        # viaja por Obsidian; el workspaces.json es dotfolder y NO sincroniza
        # (el bug Mac≠Windows del socio). Best-effort: jamás frena el launch.
        try:
            import sessions_registry as _reg
            _reg.ensure_tab(brain, cfg.get("name", ""), wname, claude_wid=wid)
        except Exception:
            pass

    os.chdir(brain)
    _exec(cmd, env)


# La verificación de sesión corre el programa oficial DESPEGADO de la
# terminal: sin stdin y, en Mac/Linux, en su propia sesión (sin terminal de
# control). Si hereda la terminal, al salir la deja en modo normal y la
# pantalla que lo llamó (Motores, el hub) se queda sin teclado.
_DETACHED = {"stdin": subprocess.DEVNULL}
if os.name != "nt":
    _DETACHED["start_new_session"] = True


def _env_motor():
    """El env para correr el CLI del motor: sin NADA de la bóveda
    (secret_store.engine_env). Falla-suave: sin secret_store, el heredado."""
    try:
        import secret_store
        return secret_store.engine_env()
    except Exception:
        return None


def session_active(runner=None):
    """¿Hay sesión de Claude Code? Vía el comando OFICIAL `claude auth status
    --json` y SOLO su campo `loggedIn` (jamás se lee ni se guarda el correo ni
    nada más de la respuesta, ni las credenciales). True/False; None si no se
    pudo saber (sin el programa, versión sin ese comando, error)."""
    exe = shutil.which("claude")
    if not exe:
        return None
    run = runner or subprocess.run
    extra = {} if runner else {"env": _env_motor()}
    try:
        r = run([exe, "auth", "status", "--json"], capture_output=True, text=True,
                timeout=15, encoding="utf-8", errors="replace", **_DETACHED, **extra)
        import json as _json
        data = _json.loads(getattr(r, "stdout", "") or "{}")
        v = data.get("loggedIn") if isinstance(data, dict) else None
        return v if isinstance(v, bool) else None
    except Exception:
        return None


def _exec(cmd, env):
    try:                        # el motor no hereda lo que cargó la bóveda
        import secret_store
        env = secret_store.engine_env(env)
    except Exception:
        pass
    if os.name == "nt":
        sys.exit(subprocess.run(cmd, env=env).returncode)
    os.execvpe(cmd[0], cmd, env)
