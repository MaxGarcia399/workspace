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
import arbol_procesos  # noqa: E402  (Windows: al vencer el tiempo muere el árbol entero)
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


#: Modo de una sesión con autonomía «edit» (Editar sin preguntar) y
#: agentes.auto_mode apagado: el que pregunta. Es el contrato de «edit»: su
#: cerebro sin preguntar (reglas Edit del settings.local.json), la terminal y lo
#: de fuera preguntan. Va explícito porque el CHANGELOG oficial de 2.1.284 dice
#: «Changed interactive terminal and VS Code sessions to start in auto mode when
#: no permission mode is configured». Se pasa «manual», el que lista el --help:
#: el de 2.1.200 dice «Changed the "default" permission mode to "Manual" …
#: `--permission-mode manual` … accepted alongside `default`» («default» ya es un
#: alias oculto). Antes de 2.1.200: MIN_SUPPORTED.
BRAIN_PERMISSION_MODE = "manual"
#: Decisión del dueño (18-nov-2026, reemplaza a M1 del 16-nov): el modo automático
#: de Claude Code de fábrica, con interruptor en Configuración → Permisos. Es el de
#: la autonomía «brain» (la de fábrica, «Automático»): `--permission-mode auto`,
#: en la terminal y en las corridas de la página (`claude -p`). Su --help (2.1.326)
#: lo lista entre las opciones de --permission-mode; la doc (permission-modes): «A
#: separate classifier model reviews actions before they run, blocking anything that
#: escalates beyond your request…», las reglas deny siguen en todos los modos, y si
#: el plan o el modelo no lo tienen «Claude Code starts the session in Manual
#: instead» (sin error). Existe desde antes de MIN_SUPPORTED (la doc: `--enable-
#: auto-mode` «Removed in v2.1.111 … use `--permission-mode auto`»). Nunca
#: bypassPermissions.
AUTO_PERMISSION_MODE = "auto"
#: «manual» existe desde 2.1.200 (nota oficial): una más vieja no abre.
MIN_SUPPORTED = "2.1.200"
UPGRADE_HINT = ("tu Claude Code es muy viejo para Workspace (necesita 2.1.200+): "
                "actualízalo con `claude update`")
#: Decisión del dueño (M5, 16-nov-2026): dentro de Workspace, Claude Code no se
#: actualiza solo. Camino oficial (code.claude.com/docs/en/env-vars): «Set to `1`
#: to disable automatic background updates. Manual `claude update` still works».
#: Va en el entorno de cada lanzamiento (aquí y en headless.py), sin tocar la
#: config global del socio. Avisar de una versión nueva probada es del Vigía.
SIN_AUTOUPDATE = {"DISABLE_AUTOUPDATER": "1"}


def _modo_del_socio(brain):
    """El defaultMode que eligió el socio en el settings.local.json del cerebro,
    o "": en «brain» gana como su --permission-mode (install.render_permissions
    lo respeta; el «dontAsk» de antes era de Workspace y se quita); en «ask»
    no gana (M2)."""
    if not brain:
        return ""
    try:
        import json
        with open(os.path.join(str(brain), ".claude", "settings.local.json"),
                  encoding="utf-8-sig") as fh:          # con BOM, si lo escribió Windows
            mode = ((json.load(fh) or {}).get("permissions") or {}).get("defaultMode")
        return mode if isinstance(mode, str) and mode != "dontAsk" else ""
    except Exception:
        return ""


def nivel(cfg):
    """La autonomía del agente en Claude Code: "ask" | "edit" | "auto". «brain» (la
    de fábrica, la que guarda cada agente al crearse), una que falta, un "full" de
    antes o un valor raro → "auto" (el de fábrica). «sandbox» → "edit": sin el
    paquete, como antes; con él, arquitectura/permisos lo cambia por su sandbox."""
    v = str((cfg or {}).get("autonomy") or "").strip().lower()
    if v == "ask":
        return "ask"
    if v in ("edit", "sandbox"):
        return "edit"
    return "auto"


#: Los modos de Claude Code que no son «sandbox»: el automático (su clasificador) y el que no pregunta nada.
MODOS_AUTO = (AUTO_PERMISSION_MODE, "bypassPermissions")


def en_sandbox(cfg):
    """¿La autonomía del agente es «sandbox» (sin permisos SOLO dentro de su sandbox)? Regla del dueño (18-nov):
    un agente en sandbox (uno que trabaja solo) NUNCA abre en modo automático: el sandbox manda sobre el
    auto de fábrica, sobre un defaultMode «auto» de su cerebro y sobre un `--permission-mode auto` en el comando."""
    return str((cfg or {}).get("autonomy") or "").strip().lower() == "sandbox"


def sin_auto(cfg, passthrough):
    """El passthrough sin un `--permission-mode auto` (o bypassPermissions) si el agente va en sandbox (en_sandbox);
    tal cual en otro caso. El modo de la sesión lo pone entonces su nivel (modo_permisos / arquitectura/permisos)."""
    args = [str(a) for a in passthrough or []]
    if not en_sandbox(cfg):
        return args
    out, saltar = [], False
    for i, a in enumerate(args):
        if saltar:
            saltar = False
            continue
        if a == "--permission-mode" and args[i + 1:i + 2] and args[i + 1] in MODOS_AUTO:
            saltar = True
            continue
        if a in ("--permission-mode=%s" % m for m in MODOS_AUTO):
            continue
        out.append(a)
    return out


def modo_permisos(cfg=None, passthrough=()):
    """El `--permission-mode` de una sesión de este agente ('' = no se pasa: manda
    lo del socio). Lo usan la terminal (auto_mode_args) y las corridas de la página
    (pagina_v2), para que las dos hagan lo mismo:
      · un --permission-mode (o un --dangerously-skip-permissions) EXPLÍCITO del
        socio en el comando → '' (el suyo gana);
      · «ask» (Preguntar) → `manual`: pregunta antes de editar, también en el
        cerebro; gana sobre un defaultMode suyo (M2);
      · un defaultMode suyo en el settings.local.json del cerebro → '' (gana en
        «Automático» y en «Editar sin preguntar»: decisión M2);
      · «edit» (Editar sin preguntar) → BRAIN_PERMISSION_MODE, o `acceptEdits` con
        el ajuste `agentes.auto_mode` ON (el "accept edits on" del shift+tab);
      · «brain» (Automático, el de fábrica) → AUTO_PERMISSION_MODE;
      · «sandbox» (en_sandbox): como «edit», y NUNCA auto: un defaultMode «auto» del cerebro o un
        --permission-mode auto en el comando no cuentan (regla del dueño: en sandbox, nunca en auto);
        con el paquete, arquitectura/permisos le pone su sandbox.
    JAMÁS bypassPermissions ni --dangerously-skip-permissions desde aquí.
    Falla-suave: sin settings.py o store ilegible → agentes.auto_mode OFF."""
    sandbox = en_sandbox(cfg)
    for a in sin_auto(cfg, passthrough):
        if str(a).startswith(("--permission-mode", "--dangerously-skip-permissions")):
            return ""
    n = nivel(cfg)
    if n == "ask":
        return "manual"
    suyo = _modo_del_socio((cfg or {}).get("_brain"))
    if suyo and not (sandbox and suyo in MODOS_AUTO):
        return ""
    if n == "auto":
        return AUTO_PERMISSION_MODE
    on = False
    try:
        import settings as _settings
        v = _settings.get("agentes.auto_mode", False)
        if isinstance(v, bool):
            on = v
    except Exception:
        pass
    return "acceptEdits" if on else BRAIN_PERMISSION_MODE


def auto_mode_args(passthrough, cfg=None):
    """El `--permission-mode` de la sesión interactiva, SIEMPRE explícito
    (Claude Code 2.1.284+ abre en «auto» si no recibe uno; «Automático» lo pide
    igual, por nombre): ["--permission-mode", modo_permisos(…)], o [] si manda lo
    del socio (su flag en el comando, o su defaultMode en el cerebro fuera de
    «ask»). Reversible: aplica al siguiente lanzamiento, sin reinstalar."""
    modo = modo_permisos(cfg, passthrough)
    return ["--permission-mode", modo] if modo else []


def escribe_sin_preguntar(cfg, passthrough=()):
    """¿Claude Code escribe en el cerebro sin preguntar? Con autonomía «brain»
    (la de fábrica) sí: el `Edit(<cerebro>/**)` del settings.local.json del
    cerebro (install.brain_rules) y, con agentes.auto_mode, acceptEdits.
    Entonces la pestaña niega la config de los motores, git y Obsidian
    (memoria.claude_deny_protegidas), como respaldo del mismo deny que ya
    vive en el settings.local.json junto al allow (install.render_permissions:
    también para un `claude` abierto fuera del lanzador o con su propio
    --settings). Con «ask» pregunta todo (sin deny). Si
    el socio pasa --dangerously-skip-permissions o --permission-mode
    bypassPermissions, su elección gana (como en Copilot)."""
    if str((cfg or {}).get("autonomy") or "").strip().lower() == "ask":
        return False
    args = [str(a) for a in passthrough or []]
    for i, a in enumerate(args):
        if a.startswith("--dangerously-skip-permissions") \
                or a == "--permission-mode=bypassPermissions" \
                or (a == "--permission-mode" and args[i + 1:i + 2] == ["bypassPermissions"]):
            return False
    return True


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
    # Regla del dueño: un agente en sandbox nunca abre en modo automático, ni con un --permission-mode auto
    # en el comando (en_sandbox / sin_auto); se dice en una línea.
    _sin = sin_auto(cfg, passthrough)
    if len(_sin) != len(list(passthrough or [])):
        print("WORKSPACE: este agente va en sandbox: no abre en modo automático (quité --permission-mode del "
              "comando)")
        passthrough = _sin

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
        # la autonomía guardada (install.autonomy_of lee «edit» como «brain»: sus permisos del cerebro son los mismos)
        _aut = {"ask": "ask", "edit": "edit"}.get(nivel(cfg), "brain")
        print(f"  permisos    : " + ("modo automático (--permission-mode auto) — «Automático», "
                                     "el de fábrica; se cambia en Configuración → Permisos"
                                     if AUTO_PERMISSION_MODE in auto else
                                     "auto-mode (--permission-mode acceptEdits) — "
                                     "settings agentes.auto_mode on" if "acceptEdits" in auto
                                     else "los del cerebro — autonomía '%s' (%s.claude/"
                                          "settings.local.json)"
                                          % (_aut, " ".join(auto) + " + " if auto else "")))
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

    # Antes del banner (limpia la pantalla): una Claude anterior a MIN_SUPPORTED no
    # entiende `--permission-mode manual`; mejor el aviso que su error crudo (como opencode).
    try:
        import engine_versions as _ev
        if _ev.drift(sys.modules[__name__], _ev.installed_version(
                shutil.which("claude") or "claude"))[0] == "unsupported":
            print("WORKSPACE: " + UPGRADE_HINT)
            if not _ev.allow_anyway():
                sys.exit(1)
    except Exception:              # falla-suave: si no se lee la versión, no se bloquea
        pass

    # 1) Banner (best-effort, hereda la tty). Se omite en modo directo (tmux).
    #    Limpia ANTES del banner para que SIEMPRE salga pegado arriba — entres por el
    #    menú `workspace` (que ya limpia) o escribiendo el agente directo (`zenith`), donde
    #    antes no limpiaba nada y el banner salía cortado. Orden 2J→3J→H (ver front.py).
    #    Si el banner del cerebro NO existe (cerebro incompleto / copia vieja), cae a un
    #    banner GENÉRICO desde la def del agente → SIEMPRE hay un arranque visible.
    if show_banner:                        # I11: la tarjeta H-1 del hub (engines._ui.letrero), no el letrero de antes
        from engines import _ui as _letrero_ui
        _letrero_ui.letrero(cfg)

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
    env.update(SIN_AUTOUPDATE)       # M5: no se actualiza solo dentro de Workspace
    env["WORKSPACE_BRAIN"] = brain   # explícito: la statusline (hija de claude) lo lee
    import engines                            # memoria v1: el motor de cada nota
    engines.mark_session_engine(env, "claude-code")
    # which() resuelve la ruta completa del binario: imprescindible en Windows, donde
    # el shim de npm es `claude.cmd` y CreateProcess no lo encuentra por nombre pelado.
    # En Mac/Linux devuelve el mismo binario que el PATH lookup (no cambia nada).
    # auto_mode_args: el --permission-mode de su autonomía (modo_permisos): «Automático»
    # (de fábrica) → auto; «Editar sin preguntar» → manual (acceptEdits con el ajuste
    # agentes.auto_mode); «Preguntar» → manual.
    # model_args: override de modelo por agente (settings agentes.<n>.model;
    # un --model explícito del socio o ANTHROPIC_MODEL ganan — ver docstring).
    # memoria v1: `--settings` con autoMemoryDirectory → la memoria propia de
    # Claude Code se guarda en el cerebro (motores/claude-code/memoria/<socio>/,
    # una carpeta por persona), viaja con él a otras máquinas; opción
    # documentada, sin escribir su config.
    _perm = auto_mode_args(passthrough, cfg)
    _modo = _modo_del_socio(brain)
    if _modo not in ("", "default", "manual") and _perm == ["--permission-mode", "manual"] \
            and str(cfg.get("autonomy") or "").strip().lower() == "ask":
        # M2: en «ask» gana «ask» sobre el defaultMode del cerebro; se dice.
        print("WORKSPACE: Workspace aplicó «preguntar antes» (ask) sobre tu defaultMode %s"
              % _modo)
    import memoria as _memoria
    cmd = ([shutil.which("claude") or "claude"]
           + _perm + model_args(cfg, passthrough)
           + _memoria.claude_settings_args(brain, passthrough,
                                           protegidas=escribe_sin_preguntar(cfg, passthrough))
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
        try:                         # su panel de herdr, para el aviso de las salas
            from engines import _ui as _ui_panel
            _ui_panel.registrar_panel(cfg, wid, "claude-code", env)
        except Exception:
            pass
        jsonl = os.path.join(_session_dir(brain), wid + ".jsonl")
        # Nivel 2 (sesiones.llevar_conversacion, apagado de fábrica): si la
        # conversación viajó en el cerebro y aquí no está (o la del cerebro es
        # más nueva), se trae ANTES de decidir. Si falla, avisa en una línea y
        # sigue lo de siempre: jamás bloquea la apertura.
        try:
            import conversaciones as _conv
            for _aviso in _conv.al_abrir(brain, wid, wname):
                sys.stdout.write("WORKSPACE: %s\n" % _aviso)
            sys.stdout.flush()
        except Exception:
            pass
        if os.path.exists(jsonl):
            # Si la sesión SIGUE viva en segundo plano, `--resume` se niega y el
            # cliente queda en la shell: se conecta a ella con `claude attach`.
            bg = sesion_en_segundo_plano(cmd[0], wid)
            if bg:
                try:
                    import workspace_status as _ws
                    sys.stdout.write("WORKSPACE: %s\n" % _ws.t(
                        "claude.bg_attach",
                        "esta pestaña sigue trabajando en segundo plano: te conecto a ella",
                        "this tab is still working in the background: connecting you to it"))
                    sys.stdout.flush()
                except Exception:
                    pass
                cmd = [cmd[0], "attach", bg]
            else:
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

    # Los avisos de una línea que dispatch juntó al abrir: aquí, después del
    # banner y del menú (los dos limpian la pantalla y los borraban).
    try:
        from engines import _ui
        _ui.soltar_avisos()
    except Exception:
        pass
    # Arquitectura nueva (F1, encendida de fábrica): el paquete de Workspace por
    # sesión (--plugin-dir) y el número de la pestaña guardado en su registro.
    try:
        from arquitectura import sesion as _sesion
        cmd, env, _info = _sesion.para_lanzar(
            "claude-code", brain, env.get("WORKSPACE_WID") or env.get("WORKSPACE_WS"), cmd, env)
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
    run = runner or arbol_procesos.run
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


#: Cuánto se espera a `claude agents --json` antes de reanudar como siempre.
AGENTS_TIMEOUT_S = 3
_ID_SEGURO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def sesion_en_segundo_plano(exe, wid, runner=None):
    """El id corto (`claude attach <id>`) de la sesión `wid` SI sigue viva en
    segundo plano; si no, None. Vía el comando documentado `claude agents
    --json` (sesiones activas, interactivas y en segundo plano): solo cuenta
    una entrada con sessionId == wid y kind == "background". Falla-suave: sin
    el comando (Claude Code viejo), con JSON roto, código ≠ 0, tiempo vencido
    o un id con forma rara → None, y el llamador hace el resume de siempre."""
    if not exe or not wid:
        return None
    run = runner or arbol_procesos.run
    extra = {} if runner else {"env": _env_motor()}
    try:
        r = run([exe, "agents", "--json"], capture_output=True, text=True,
                timeout=AGENTS_TIMEOUT_S, encoding="utf-8", errors="replace",
                **_DETACHED, **extra)
        if getattr(r, "returncode", 1) != 0:
            return None
        import json as _json
        data = _json.loads(getattr(r, "stdout", "") or "null")
        if isinstance(data, dict):                 # por si algún día envuelve la lista
            data = data.get("agents") or data.get("sessions")
        for a in data if isinstance(data, list) else ():
            if (isinstance(a, dict) and a.get("sessionId") == wid
                    and a.get("kind") == "background"
                    and _ID_SEGURO.match(str(a.get("id") or ""))):
                return str(a["id"])
    except Exception:
        return None
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
