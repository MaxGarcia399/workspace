"""Adapter del motor Claude Code para WORKSPACE.

Generaliza el launcher shell de Zenith (banner → menú de pestañas → `claude --resume`)
leyendo la config del agente. Cross-platform, cero dependencias (stdlib, Python 3.9+).

Claude Code corre modelos de Anthropic vía la suscripción del socio (OAuth) — sin API key.
Es el motor premium. Otros motores (agnósticos, locales) llegan en pasos posteriores.
"""
import sys, os, shutil, subprocess

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


def _utf8_env():
    """B2 · Windows: un hijo Python capturado por un pipe usa cp1252, no UTF-8 →
    UnicodeEncodeError al imprimir box-drawing/braille (banner, dashboard).
    PYTHONUTF8=1 lo fuerza a UTF-8. No-op en Mac/Linux (UTF-8 ya es default)."""
    return {**os.environ, "PYTHONUTF8": "1"}


def auto_mode_args(passthrough):
    """POLÍTICA DEL EQUIPO: las sesiones interactivas arrancan en AUTO-MODE —
    `--permission-mode acceptEdits`, el mecanismo OFICIAL de Claude Code (el
    mismo "accept edits on" del shift+tab que el socio prendía a mano).
    JAMÁS bypassPermissions ni --dangerously-skip-permissions desde aquí.

    Configurable y reversible: settings `agentes.auto_mode` off lo apaga
    (aplica al siguiente lanzamiento, sin reinstalar). Un --permission-mode
    (o un --dangerously-skip-permissions) EXPLÍCITO del socio en el comando
    siempre gana → no se agrega nada encima. Falla-suave: sin settings.py
    o store ilegible → ON (el default del equipo)."""
    for a in passthrough or []:
        if str(a).startswith(("--permission-mode", "--dangerously-skip-permissions")):
            return []
    on = True
    try:
        import settings as _settings
        v = _settings.get("agentes.auto_mode", True)
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


def pick(cfg):
    """Corre solo el menú interactivo del agente y devuelve la elección cruda
    ('WS\\t<wid>\\t<name>') sin lanzar nada. Lo usa el hub tmux (mux.py)."""
    import agent_ui
    agent_ui.export_context(cfg)
    os.environ["WORKSPACE_ENGINE_LABEL"] = _engine_label(cfg)
    dashboard = (cfg.get("_scripts") or {}).get("dashboard")
    if not dashboard or not os.path.exists(dashboard):
        return ""
    if cfg.get("_brain"):   # los scripts viven en WORKSPACE; el cerebro va por env
        os.environ["WORKSPACE_BRAIN"] = cfg["_brain"]
    try:
        r = subprocess.run([_py(), dashboard, "--pick"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           env=_utf8_env())
        return (r.stdout or "").strip()
    except Exception:
        return ""


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
    session_env = cfg.get("session_env", "ZENITH_WS")
    wid_env = cfg.get("session_id_env", "ZENITH_WID")
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
        auto = auto_mode_args(passthrough)
        print(f"  permisos    : " + ("auto-mode (--permission-mode acceptEdits) — política del "
                                     "equipo (off: settings agentes.auto_mode)" if auto
                                     else "sin flag (agentes.auto_mode off o flag explícito del socio)"))
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
    elif dashboard and os.path.exists(dashboard):
        try:
            r = subprocess.run([py, dashboard, "--pick"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               env=_utf8_env())
            choice = (r.stdout or "").strip()
        except Exception:
            choice = ""
    else:
        choice = ""

    env = _utf8_env()   # B2 · PYTHONUTF8=1 lo hereda el hijo `claude` y todo lo que
                        # spawnea (hooks, statusline) → UTF-8 de punta a punta en Windows.
    env["CLAUDE_CODE_HIDE_CWD"] = "1"
    env["WORKSPACE_BRAIN"] = brain   # explícito: la statusline (hija de claude) lo lee
    # which() resuelve la ruta completa del binario: imprescindible en Windows, donde
    # el shim de npm es `claude.cmd` y CreateProcess no lo encuentra por nombre pelado.
    # En Mac/Linux devuelve el mismo binario que el PATH lookup (no cambia nada).
    # auto_mode_args: política del equipo — sesión interactiva arranca en
    # acceptEdits (configurable: settings agentes.auto_mode; reversible).
    # model_args: override de modelo por agente (settings agentes.<n>.model;
    # un --model explícito del socio o ANTHROPIC_MODEL ganan — ver docstring).
    cmd = ([shutil.which("claude") or "claude"]
           + auto_mode_args(passthrough) + model_args(cfg, passthrough)
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
            cmd += ["--session-id", wid, "--name", wname]
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


def _exec(cmd, env):
    if os.name == "nt":
        sys.exit(subprocess.run(cmd, env=env).returncode)
    os.execvpe(cmd[0], cmd, env)
