"""Antigravity CLI adapter. Flags verified against installed agy --help (1.2.16).

Login and sessions belong to agy; WORKSPACE never reads credentials.
Native MCP is supported; WORKSPACE tool hooks are not wired yet.

Pestañas NEUTRALES (sessions_registry · el socio 2026-10-03): el MISMO picker de
Claude Code corre antes del exec (subproceso agnóstico); el resume usa
`agy --conversation <id>` (validado contra el store local de agy antes de
usarlo) y el id del vendor se ata POST-HOC leyendo
`~/.gemini/antigravity-cli/cache/last_conversations.json` (VERIFICADO contra
la instalación real: mapa cwd → último conversation id; se compara el
snapshot ANTES/DESPUÉS de la corrida para no bindear un id stale).

INYECCIÓN INVISIBLE: la memoria de la pestaña activa va en el GEMINI.md
GENERADO (doc de proyecto que agy lee como contexto) — el socio NO ve el
bloque en el chat. El bloque se regenera por corrida y se LIMPIA al cerrar
(_strip_session_block). Si el GEMINI.md es PROPIO del socio, su CONTENIDO
no se toca: el bloque de sesión va ANEXADO al final, marcado y efímero
(strip al cerrar + strip-antes-de-anexar en cada launch — un huérfano por
crash se auto-limpia). Solo si ni el anexo se puede escribir, la memoria
cae al primer prompt (visible — último recurso honesto). Fix 2026-10-04.
Falla-suave absoluta: nada de esto impide el launch.
"""
import json
import os
import shutil
import sys

META = {"name": "antigravity", "needs": ["agy"], "auth": "subscription"}
CAPABILITIES = {
    "launch": "wrapper", "inject_context": "project-doc", "mcp": True,
    "hooks": False,
    "sessions": "workspace",   # pestañas del registro neutral (sessions_registry)
                             # + resume con `agy --conversation <id>` (binding
                             # post-hoc vía cache/last_conversations.json)
    "status_live": False,
    "headless": False,
}

#: Primera línea EXACTA del GEMINI.md generado — detector de "es nuestro".
_GEMINI_MARK = "<!-- WORKSPACE:GENERATED antigravity-context v1 -->"
#: Marca pre-rename (OLYMPUS→Workspace 2026-10): los cerebros existentes aún
#: la traen; sin reconocerla el doc generado parecía "del socio" y la memoria
#: caía al primer prompt visible. Solo se LEE; se escribe siempre la nueva.
_GEMINI_MARK_LEGACY = "<!-- OLYMPUS:GENERATED antigravity-context v1 -->"
#: Marcas del bloque de SESIÓN (pestaña activa) dentro del GEMINI.md.
#: Se quitan por LÍNEA completa — contenido con `-->` adentro no las rompe.
_SESSION_START = "<!-- WORKSPACE:SESSION start — contexto de la pestaña activa; se regenera en cada launch -->"
_SESSION_END = "<!-- WORKSPACE:SESSION end -->"
#: Variantes pre-rename (solo LECTURA: huérfanos de corridas OLYMPUS también
#: deben poder limpiarse — había reales en los cerebros).
_SESSION_STARTS = (_SESSION_START,
                   "<!-- OLYMPUS:SESSION start — contexto de la pestaña activa; se regenera en cada launch -->")
_SESSION_ENDS = (_SESSION_END, "<!-- OLYMPUS:SESSION end -->")


def status():
    exe = shutil.which("agy")
    return {"ready": bool(exe), "binary": "agy", "binary_in_path": bool(exe),
            "auth": "managed by agy; login not probed"}


def _interactive_argv(cfg, passthrough, resume_cid="", first_prompt=""):
    """argv para `agy`. Sin kwargs = comportamiento histórico. Con pestaña:
      · `resume_cid` → `--conversation <id>` (VERIFICADO en agy --help
        1.2.16) y SIN prompt inicial (el hilo ya tiene el contexto);
      · `first_prompt` → SOLO el fallback visible (GEMINI.md propio del
        socio); el camino normal inyecta la memoria en el doc de proyecto.
    Prompts/resume explícitos del socio en el passthrough SIEMPRE ganan."""
    args = list(passthrough or [])
    # Bootstrap only a new interactive session; preserve explicit prompts/resume.
    owns_prompt = any(str(a).split("=", 1)[0] in (
        "-p", "--print", "--prompt", "-i", "--prompt-interactive",
        "-c", "--continue", "--conversation") for a in args)
    if args or owns_prompt:
        return args
    resume_cid = str(resume_cid or "").strip()
    if resume_cid:
        return ["--conversation", resume_cid]
    return ["--prompt-interactive",
            first_prompt or ("Lee CLAUDE.md e inicia el cerebro. Al terminar, confirma en "
                             "una línea breve.")]


# ── store local de agy (solo lectura — jamás credenciales) ──────────────────
def _agy_home():
    return os.environ.get("ANTIGRAVITY_CLI_HOME") or os.path.join(
        os.path.expanduser("~"), ".gemini", "antigravity-cli")


def _last_conversations_path():
    return os.path.join(_agy_home(), "cache", "last_conversations.json")


def _conversation_exists(cid, home=None):
    """¿La conversación sigue existiendo localmente? agy guarda una .db por
    conversación en `<home>/conversations/<id>.db` (verificado contra la
    instalación real). Valida el resume-id ANTES de `--conversation` —
    conversación borrada → arrancar fresco, no un error. Falla-suave→False."""
    cid = str(cid or "").strip()
    if not cid or any(c in cid for c in "/\\."):
        return False
    return os.path.isfile(os.path.join(home or _agy_home(),
                                       "conversations", cid + ".db"))


def _vendor_conversation_for(brain, cache_path=None):
    """El último conversation id de agy para ESTE cerebro, según su cache
    `last_conversations.json` ({cwd: conversation_id} — verificado contra
    ~/.gemini/antigravity-cli real). Se matchea el path crudo y el realpath.
    '' si no hay. Solo lectura; falla-suave."""
    try:
        with open(cache_path or _last_conversations_path(),
                  encoding="utf-8") as fh:
            m = json.load(fh)
        if not isinstance(m, dict):
            return ""
        real = os.path.realpath(brain or "")
        for k, v in m.items():
            if str(k) in (str(brain), real) or os.path.realpath(str(k)) == real:
                return str(v or "").strip()
    except Exception:
        pass
    return ""


def ensure_brain_access(brain, settings_path=None):
    """Trust this explicit brain and allow recursive reads; preserve other rules."""
    import json
    from pathlib import Path
    from antigravity_usage import _atomic
    root = os.path.realpath(os.path.abspath(os.path.expanduser(str(brain))))
    if not brain or not os.path.isdir(root) or not os.path.isfile(os.path.join(root,'CLAUDE.md')):
        return False
    path = Path(settings_path or os.path.join(_agy_home(),'settings.json'))
    try:
        if path.is_symlink():
            return False
        if path.exists() and path.stat().st_size > 1024*1024:
            return False
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if not isinstance(data,dict):
            return False
        original = json.dumps(data,sort_keys=True)
        trusted = data.setdefault('trustedWorkspaces',[])
        permissions = data.setdefault('permissions',{})
        if not isinstance(trusted,list) or not isinstance(permissions,dict):
            return False
        allowed = permissions.setdefault('allow',[])
        if not isinstance(allowed,list):
            return False
        if root not in trusted:
            trusted.append(root)
        rule = 'read_file(%s)' % root
        if rule not in allowed:
            allowed.append(rule)
        if original != json.dumps(data,sort_keys=True):
            if path.exists():
                backup = path.with_name('settings.workspace-brain-access-backup.json')
                if not backup.exists():
                    _atomic(backup,json.loads(path.read_text(encoding='utf-8')))
            _atomic(path,data)
        return True
    except (OSError,ValueError,TypeError):
        return False


# ── GEMINI.md generado (identidad + bloque de sesión INVISIBLE) ─────────────
def _gemini_path(brain):
    return os.path.join(brain, "GEMINI.md")


def _gemini_is_custom(brain):
    """¿El GEMINI.md existente es PROPIO del socio (sin nuestra marca, ni la
    actual ni la legacy pre-rename)? Su CONTENIDO jamás se pisa — gana el
    socio (el bloque de sesión solo se ANEXA/limpia, marcado)."""
    p = _gemini_path(brain)
    try:
        if not os.path.exists(p):
            return False
        with open(p, encoding="utf-8", errors="replace") as fh:
            head = fh.read().lstrip()
        return not (head.startswith(_GEMINI_MARK)
                    or head.startswith(_GEMINI_MARK_LEGACY))
    except Exception:
        return True          # ilegible → trátalo como del socio (no pisar)


def _write_gemini(brain, ctx, session_block=""):
    """Escribe el GEMINI.md GENERADO (arranque + contexto neutral + bloque de
    la pestaña activa). Atómico; jamás pisa un GEMINI.md del socio. Devuelve
    True si quedó escrito. NUNCA levanta (el launch no depende de esto)."""
    try:
        if _gemini_is_custom(brain):
            return False
        body = (_GEMINI_MARK + "\n# Arranque de WORKSPACE\n"
                "El cerebro de esta sesión está en " + os.path.realpath(brain) + ". "
                "Su identidad está en " + os.path.join(os.path.realpath(brain), "CLAUDE.md") + ". "
                "Lee CLAUDE.md completo y sigue su protocolo de arranque. "
                "Los documentos de estado están en STATE/ (STATE/brain-version.md, "
                "STATE/MEMORY.md, STATE/PENDIENTES.md, STATE/MILESTONES.md). "
                "Durante el arranque usa las herramientas de lectura de archivos; "
                "evita comandos de shell para listar carpetas o comprobar rutas. "
                "El inbox ya está resumido abajo: no vuelvas a consultarlo al iniciar. "
                "No enumeres la configuración ni el protocolo al socio; al terminar "
                "confirma en una línea breve.\n\n" + (ctx or ""))
        if session_block:
            body += "\n\n%s\n%s\n%s\n" % (_SESSION_START, session_block,
                                          _SESSION_END)
        p = _gemini_path(brain)
        tmp = p + ".workspace-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def _split_session_block(text):
    """(texto_sin_bloque, había_bloque). Corta por LÍNEAS completas entre las
    marcas (actuales o legacy pre-rename) — contenido con `-->` adentro no
    rompe el corte; el resto del archivo queda byte-a-byte intacto."""
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
    """Quita el bloque de sesión del GEMINI.md — GENERADO o del socio (solo
    corta entre nuestras marcas; el contenido del socio queda intacto).
    Limpieza al cerrar: el contexto de la pestaña era de ESTA corrida; no
    dejar basura que el siguiente arranque u otro harness lea desfasada.
    Idempotente. Falla-suave."""
    try:
        p = _gemini_path(brain)
        if not os.path.exists(p):
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


def _append_session_block(brain, block):
    """ANEXA el bloque de sesión MARCADO al final del GEMINI.md PROPIO del
    socio, sin tocar su contenido (fix 2026-10-04: antes la memoria caía al
    primer prompt VISIBLE). Idempotente: strip-antes-de-anexar (un bloque
    huérfano por crash se auto-limpia solo). El cierre lo quita
    (_strip_session_block). Falla-suave → False (el caller decide el
    fallback visible)."""
    try:
        block = (block or "").strip()
        p = _gemini_path(brain)
        if not block or not os.path.isfile(p):
            return False
        with open(p, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
        base, _ = _split_session_block(txt)
        body = (base.rstrip() + "\n\n%s\n%s\n%s\n"
                % (_SESSION_START, block, _SESSION_END))
        tmp = p + ".workspace-tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    brain = cfg.get("_brain", "")
    agent = str(cfg.get("name") or "")
    if plan:
        print("  motor: antigravity · CLI agy")
        print("  cerebro: " + brain)
        print("  binario: " + (shutil.which("agy") or "FALTA agy en PATH"))
        print("  argumentos: " + repr(_interactive_argv(cfg, passthrough)))
        print("  pestañas: picker compartido + registro neutral — resume: "
              "--conversation <id> (validado); memoria de la pestaña va "
              "INVISIBLE en el GEMINI.md generado; id atado post-hoc "
              "(cache/last_conversations.json, snapshot antes/después)")
        print("  login/sesiones: credenciales las gestiona agy; hooks de "
              "tools pendientes")
        return
    if not brain or not os.path.isdir(brain):
        raise SystemExit("WORKSPACE: cerebro inexistente para Antigravity")
    if not shutil.which("agy"):
        raise SystemExit("WORKSPACE: falta Antigravity CLI (agy) en PATH")

    if not ensure_brain_access(brain):
        print('WORKSPACE: no pude registrar la lectura automática del cerebro en Antigravity.')

    # Motor+modelo REAL en el banner (dinámico — regla del socio). El modelo
    # sale del --model del socio si lo pasó; si no, lo elige agy.
    _mdl = ""
    _pt = [str(a) for a in (passthrough or [])]
    for _i, _a in enumerate(_pt):
        if _a == "--model" and _i + 1 < len(_pt):
            _mdl = _pt[_i + 1]; break
        if _a.startswith("--model="):
            _mdl = _a.split("=", 1)[1]; break
    os.environ["WORKSPACE_ENGINE_LABEL"] = (
        "Antigravity · " + (_mdl or "modelo de agy"))
    # Banner del CEREBRO (patrón buffered+width-check compartido con codex).
    if show_banner:
        try:
            from engines import _ui
            _ui.show_brain_banner(cfg)
        except Exception:
            print("  WORKSPACE · %s · Antigravity CLI"
                  % cfg.get("display", cfg.get("name", "")))

    # Pestañas neutrales: mismo picker, registro compartido entre motores.
    # El resume-id local se VALIDA contra el store de agy (conversación
    # borrada → fresco + re-bind, jamás un --conversation muerto en loop).
    tab, resume_cid, session_blk = None, "", ""
    try:
        from engines import _ui
        import sessions_registry as _reg
        tab = _ui.pick_tab(cfg, preselect=preselect)
        if tab:
            wid, wname = tab
            _ui.export_tab_env(cfg, wid, wname)
            _reg.ensure_tab(brain, agent, wname, claude_wid=wid)
            resume_cid = _reg.resume_id(brain, agent, wname, "antigravity")
            if resume_cid and not _conversation_exists(resume_cid):
                resume_cid = ""
            session_blk = _reg.session_doc_block(brain, wname)
    except Exception:
        tab, resume_cid, session_blk = None, "", ""

    # Inyección INVISIBLE por doc de proyecto. GEMINI.md PROPIO del socio →
    # su contenido no se pisa: el bloque de sesión va ANEXADO al final
    # (marcado, strip-antes-de-anexar, se limpia al cerrar). Solo si ni el
    # anexo se pudo escribir, la memoria cae al primer prompt (visible —
    # último recurso honesto).
    first_prompt = ""
    doc_ok = not _gemini_is_custom(brain)
    appended = bool(not doc_ok and session_blk
                    and _append_session_block(brain, session_blk))
    if tab and not doc_ok and not appended and not resume_cid:
        try:
            import sessions_registry as _reg
            first_prompt = _reg.first_prompt_context(brain, tab[1])
            print("WORKSPACE: GEMINI.md propio del socio y no pude anexar — "
                  "la memoria de la pestaña irá en el primer mensaje "
                  "(visible).")
        except Exception:
            first_prompt = ""

    args = _interactive_argv(cfg, passthrough, resume_cid=resume_cid,
                             first_prompt=first_prompt)

    import interactive
    import antigravity_usage
    antigravity_usage.ensure_statusline()

    _appended_ctx = []     # ¿quedó un bloque anexado al doc del socio?

    def save_context(ctx):
        # NUNCA levanta: un GEMINI.md del socio o un disco lleno no deben
        # tumbar el launch (bug cazado en el doble-check: el RuntimeError
        # anterior escapaba por el wrapper y abortaba el arranque).
        # Doc del socio → el contexto va ANEXADO (bloque marcado, invisible,
        # junto con la memoria de la pestaña); solo si tampoco se pudo
        # escribir, se imprime (último canal honesto).
        if _write_gemini(brain, ctx, session_block=session_blk):
            return
        try:
            merged = "\n\n".join(p for p in (session_blk,
                                             (ctx or "").strip()) if p)
            if merged and _append_session_block(brain, merged):
                _appended_ctx.append(True)
                return
        except Exception:
            pass
        if (ctx or "").strip():
            try:
                print("[WORKSPACE · contexto de arranque]\n%s\n" % ctx.strip())
            except Exception:
                pass

    before_cid = _vendor_conversation_for(brain)
    rc = interactive.run_official_cli_interactive(
        "antigravity", brain=brain, argv=args, context_sink=save_context)

    # Limpieza (session_end): el bloque de sesión era de ESTA corrida —
    # generado O anexado al doc del socio, se quita igual (strip). Un crash
    # deja un huérfano que el strip-antes-de-anexar del siguiente launch
    # auto-limpia.
    if session_blk or appended or _appended_ctx:
        _strip_session_block(brain)
    # Binding POST-HOC: solo si el cache CAMBIÓ durante esta corrida (un id
    # stale de una corrida vieja del mismo cerebro NO se bindea a esta
    # pestaña — bug cazado en el doble-check) y no es el que ya teníamos.
    if tab:
        try:
            import sessions_registry as _reg
            cid = _vendor_conversation_for(brain)
            if cid and cid != before_cid and cid != resume_cid:
                _reg.bind(brain, agent, tab[1], "antigravity", cid)
        except Exception:
            pass
    sys.exit(rc if isinstance(rc, int) else 0)


def pick(cfg):
    """El picker de pestañas ahora es COMPARTIDO (registro neutral): misma
    elección cruda que claude_code.pick — para el hub tmux. Falla-suave."""
    try:
        from engines import claude_code as _cc
        return _cc.pick(cfg)
    except Exception:
        return ""
