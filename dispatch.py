#!/usr/bin/env python3
"""WORKSPACE — dispatcher de agentes.

Invoca un agente por nombre: lee el registry, carga su config, resuelve su cerebro
y lo arranca con su motor. Los aliases de terminal (`zenith`, `argus`, …) son atajos
que llaman aquí.

Uso:
  python3 dispatch.py <agente> [args claude...]
  python3 dispatch.py <agente> ls | migrar
  python3 dispatch.py <agente> --engine <motor>   # cambia de motor SOLO esta corrida
  python3 dispatch.py --plan <agente>     # no lanza nada; muestra el wiring (validación)
  python3 dispatch.py <agente> --plan     # ídem — --plan vale en CUALQUIER posición
  python3 dispatch.py --list              # lista los agentes registrados

Cambio de motor (precedencia, de más explícita a menos):
  1. flag --engine <n>     2. env WORKSPACE_ENGINE=<n>     3. agent.json "engine"
  4. settings unificado `modelos.default_engine` (solo si el agente NO declara
     motor — hoy todos lo declaran, así que nada cambia por default).
La elección explícita (1/2) es ESTRICTA (selection-source policy — sin fallbacks).

Cero dependencias (stdlib, Python 3.9+). Config en JSON.
Resolución del cerebro (en orden) — brain_resolver.py es la ÚNICA implementación:
  1. ~/.claude/workspace/paths.local.json → brains.<agente>  (per-máquina)
  2. agente cargado (agents.local.json, ruta absoluta per-máquina)
  3. campo "brain" del agent.json, relativo a la raíz de WORKSPACE
"""
import sys, os, json
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
sys.dont_write_bytecode = True   # no generar __pycache__ (mantiene limpio el sync)
if os.name == "nt":
    os.system("")  # habilita ANSI en Windows 10+ (también para banner/dashboard hijos) — igual que doctor.py
import _utf8; _utf8.harden()  # B2 · UTF-8 en stdout/err (cp1252 reventaría con box-drawing)

ROOT = os.path.dirname(os.path.abspath(__file__))

# Agentes de SISTEMA — FILTRO HEREDADO. El agente interno `doctor` (motor oculto
# que nunca se usó) salió del producto en 0.2.1 (aparcado en feat/agente-doctor),
# pero instalaciones anteriores pueden traer una entrada vieja suya en su
# agents.local.json. Este filtro la ignora en TODA pantalla y en doctor/update/
# repair (vía `visible_agents()` / `is_system_agent()`) hasta que la migración
# 202610131200_purge_system_agents la quita. Al agregar una pantalla nueva que
# pinte agentes, consúmela vía `visible_agents()`.
SYSTEM_AGENTS = frozenset({"doctor"})

# Empty compatibility fallback: roster always belongs to the effective profile.
# Compatibility export only. An unreadable/empty profile must not invent users.
FALLBACK_ROSTER = ()


def is_system_agent(entry, cfg=None):
    """True si la entrada es un agente INTERNO del harness, no del usuario: su
    nombre está en SYSTEM_AGENTS, o se declara `hidden: true` (en la entrada
    del registro o en su definición `cfg`, si se pasa). Lo usan las pantallas
    (vía visible_agents) y el doctor/update, que no deben revisar ni tocar
    motores internos que una instalación anterior dejó registrados."""
    try:
        name = str((entry or {}).get("name", "")).strip().lower()
        if name in SYSTEM_AGENTS:
            return True
        if (entry or {}).get("hidden") is True:
            return True
        return isinstance(cfg, dict) and cfg.get("hidden") is True
    except Exception:
        return False


def visible_agents(reg=None):
    """Las entradas de agentes que ve el SOCIO — el registry EFECTIVO menos los
    de SISTEMA. `reg` = un registry ya cargado (evita re-leer); None = lo carga.
    Falla-suave → lista vacía. Úsalo en vez de filtrar `SYSTEM_AGENTS` a mano en
    cada consumidor (esa duplicación fue el bug: Tonos mostraba `doctor` porque
    re-derivaba la lista sin el filtro que solo vivía en el hub)."""
    try:
        if reg is None:
            reg = load_registry()
        return [a for a in (reg.get("agents") or ())
                if isinstance(a, dict) and isinstance(a.get("name"), str)
                and a['name'].strip()
                and not is_system_agent(a)]
    except Exception:
        return []


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def registry_path():
    """Ruta del registry committeado. Env WORKSPACE_REGISTRY la sobrescribe — lo
    usan los tests para sembrar un registry canónico y NO depender del archivo
    del repo (que se distribuye vacío). Función para que sea mockeable."""
    return os.environ.get("WORKSPACE_REGISTRY") or os.path.join(
        ROOT, "agents", "registry.json")


def _committed_registry():
    """El registry committeado del repo. El harness se distribuye con esto
    VACÍO; el equipo lo tiene poblado por back-compat. Falla-suave → vacío."""
    try:
        return _read_json(registry_path())
    except Exception:
        return {"version": 1, "agents": [], "planned": []}


def load_registry():
    """Registry EFECTIVO = committeado (back-compat) + agentes CARGADOS
    per-máquina (agents.local.json, ganan por nombre). Un agente cargado se
    auto-describe en `<brain>/.workspace/agent.json`; aquí lo materializamos como
    una entrada de registry con `brain` absoluto y `_loaded: True`. Falla-suave:
    sin agentsreg / sin archivo → solo el committeado."""
    reg = _committed_registry()
    if not isinstance(reg, dict):
        reg = {}
    reg.setdefault("agents", [])
    reg.setdefault("planned", [])
    try:
        import agentsreg
        loaded = agentsreg.agents()
    except Exception:
        loaded = []
    if not loaded:
        return reg
    by_name = {}
    for a in reg["agents"]:
        nm = str(a.get("name", "")).lower()
        if nm:
            by_name[nm] = a
    for la in loaded:
        try:
            defn = agentsreg.load_definition(la["brain"])
        except Exception:
            defn = {}
        by_name[la["name"]] = {
            "name": la["name"],
            "brain": la["brain"],
            "engine": defn.get("engine", "claude-code"),
            "aliases": defn.get("aliases", [la["name"]]),
            "_loaded": True,
        }
    reg["agents"] = list(by_name.values())
    return reg


def find_agent(name):
    name = (name or "").lower()
    for a in load_registry().get("agents", []):
        # aliases vive en agent.json (editable a mano en el cerebro): saneamos
        # tipos raros ([123], "turing", null) en vez de crashear (falla-suave).
        aliases = a.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        elif not isinstance(aliases, (list, tuple)):
            aliases = []
        aliases = [str(x).lower() for x in aliases if x is not None]
        if a.get("name", "").lower() == name or name in aliases:
            return a
    return None


def _paths_local():
    # per-máquina, FUERA del vault (no se sincroniza). Override de rutas de cerebros.
    # SSOT: brain_resolver (Z20) — aquí solo se delega.
    import brain_resolver
    return brain_resolver.paths_local()


def _local_overrides():
    import brain_resolver                  # nuevo per-máquina · legacy en ROOT
    return brain_resolver.local_overrides(ROOT)


def obsidian_sync_enabled(path):
    """True si `path` es un vault de Obsidian con Sync activo.
    .obsidian/core-plugins.json lista los plugins: forma vieja = lista
    ["sync", ...], forma nueva = objeto {"sync": true}."""
    cp = os.path.join(path or "", ".obsidian", "core-plugins.json")
    try:
        data = _read_json(cp)
    except Exception:
        return False
    if isinstance(data, dict):
        return bool(data.get("sync"))
    return isinstance(data, list) and "sync" in data


def brain_transport(agent_name, brain=None):
    """Transporte de sync del cerebro de un agente: 'obsidian-sync' | 'git'.

    POLÍTICA (firme): los cerebros sincronizan EXCLUSIVAMENTE por Obsidian
    Sync — es el DEFAULT y un canal de primera clase. git aplica SOLO si el
    socio lo declara explícito por máquina:
        paths.local.json → {"transport": {"<agente>": "git"}}
    Un cerebro 'obsidian-sync' es un canal SANO: update/doctor lo reportan
    como gestionado por Obsidian Sync y JAMÁS le exigen git (ni ⚠ ni ✗ por
    "no es repo git" / "detrás de origin" / "cambios sin commitear").
    `brain` se conserva en la firma por compatibilidad (los callers la pasan);
    ya no se infiere nada del disco — el default no depende del vault."""
    t = (_local_overrides().get("transport") or {}).get(agent_name, "")
    if t in ("git", "obsidian-sync"):
        return t
    return "obsidian-sync"


def resolve_brain(agent_name, agent_cfg):
    """Ruta efectiva del cerebro. FACHADA de brain_resolver.resolve (Z20): la
    única resolución del producto (override por máquina > registro por máquina
    > definición committeada relativa a ROOT). Para fuente/estado usa
    brain_resolver.resolve directamente."""
    import brain_resolver
    return brain_resolver.resolve_path(agent_name, agent_cfg, root=ROOT)


def load_agent_cfg(entry):
    """Config del agente. Para un agente CARGADO (per-máquina) la identidad vive
    en `<brain>/.workspace/agent.json` (autocontenido, portátil). Para uno
    committeado, en `agents/<dir>/agent.json` (back-compat)."""
    if entry.get("_loaded") or entry.get("brain"):
        brain = os.path.abspath(os.path.expanduser(entry["brain"]))
        try:                                   # CANÓNICO .workspace/agent.json, con
            import agentsreg                   # fallback a <brain>/agent.json (robustez)
            defpath = agentsreg.agent_json_path(brain)
        except Exception:
            defpath = os.path.join(brain, ".workspace", "agent.json")
        try:                                   # falla-suave: def faltante/corrupta
            cfg = _read_json(defpath)
        except Exception:
            cfg = {}
        if not isinstance(cfg, dict) or not cfg.get("name"):
            cfg = {"name": entry.get("name", ""), "_missing_def": True}
        cfg["_dir"] = os.path.dirname(defpath)
        cfg["brain"] = brain          # absoluto → resolve_brain lo devuelve tal cual
        return cfg
    d = os.path.join(ROOT, "agents", entry.get("dir") or entry.get("name", ""))
    try:
        cfg = _read_json(os.path.join(d, "agent.json"))
    except Exception:
        cfg = {}        # I1: agent.json committeado ausente/corrupto
    if not isinstance(cfg, dict) or not cfg.get("name"):
        # I1: degradar amable como la rama de agente CARGADO (que ya lo hace),
        # en vez de un traceback crudo / cfg sin "name". _read_json de dispatch
        # NO es fail-soft (levanta), por eso el try.
        cfg = {"name": entry.get("name", ""), "_missing_def": True}
    cfg["_dir"] = d
    return cfg


def _within(path, *roots):
    """True si `path` resuelto está contenido en alguno de `roots` (defensa SEC:
    un agent.json auto-descubierto no debe apuntar a scripts fuera del cerebro/harness)."""
    rp = os.path.realpath(path)
    for r in roots:
        if r:
            rr = os.path.realpath(r)
            if rp == rr or rp.startswith(rr + os.sep):
                return True
    return False


def expand_scripts(cfg, brain):
    """Placeholders en agent.json → rutas reales.
    {brain} = cerebro del agente · {root} = raíz de WORKSPACE (los scripts de UI
    viven aquí desde la migración brand→WORKSPACE; el cerebro es contenido puro).
    SEC: descarta scripts que resuelvan FUERA del cerebro o del harness."""
    out = {}
    for k, v in (cfg.get("scripts") or {}).items():
        p = os.path.normpath(v.replace("{brain}", brain).replace("{root}", ROOT))
        if _within(p, brain, ROOT):
            out[k] = p
    return out


def _settings_default_engine():
    """Fallback FINAL del motor: `modelos.default_engine` del settings
    unificado, SOLO si el socio lo fijó explícito en el store (get_stored —
    sin defaults de schema): un agente sin motor declarado sigue dando el
    mismo error de siempre salvo elección expresa. Falla-suave → ''."""
    try:
        import settings as _settings
        return _settings.get_stored("modelos.default_engine") or ""
    except Exception:
        return ""


def _settings_agent_engine(name):
    """Override de MOTOR PER-MÁQUINA de un agente: `agentes.<n>.engine` del
    store (tier A, gitignoreado). NO viene del agent.json committeado (eso es
    N3) — es la elección LOCAL del socio, que gana sobre el default del
    agent.json pero cede a un --engine/env explícito. '' si no hay.
    Falla-suave → ''."""
    try:
        import settings as _settings
        n = str(name or "").strip().lower()
        if not n:
            return ""
        v = _settings.get_stored("agentes.%s.engine" % n)
        return v.strip() if isinstance(v, str) and v.strip() else ""
    except Exception:
        return ""


# ── Motores enchufables: carga dinámica por nombre (contrato en engines/CONTRACT.md) ──
def available_engines():
    """Motores instalados = engines/*.py que no empiezan con '_' (excluye plantilla)."""
    d = os.path.join(ROOT, "engines")
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".py") and not f.startswith("_") and f != "__init__.py":
                out.append(f[:-3].replace("_", "-"))
    return out


def load_engine(name):
    """Carga el motor por nombre: 'claude-code' → engines/claude_code.py.
    Devuelve el módulo si cumple el contrato (tiene launch), o None.
    Agregar un motor = dropear engines/<nombre>.py — NO se toca dispatch.py."""
    import importlib
    mod_name = (name or "").replace("-", "_")
    if not mod_name:
        return None
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    full = "engines." + mod_name
    try:
        mod = importlib.import_module(full)
    except ModuleNotFoundError as e:
        # El motor EN SÍ no existe (caso legítimo "no instalado") → None silencioso.
        # Pero si lo que falta es OTRA cosa (una dependencia del engine), es un
        # fallo REAL disfrazado de "no instalado" → reportarlo.
        if getattr(e, "name", "") in (full, "engines"):
            return None
        _warn_engine_broken(full, e)
        return None
    except Exception as e:
        # must-fix #5: el archivo del motor EXISTE pero NO carga (SyntaxError,
        # ImportError de una dep, error a nivel módulo — p.ej. introducido por un
        # auto-update). Antes el `except: return None` lo confundía con "motor no
        # disponible" y dejaba a TODA la flota muerta sin traceback. Lo hacemos
        # VISIBLE: el error real a stderr, para que sea diagnosticable.
        _warn_engine_broken(full, e)
        return None
    return mod if hasattr(mod, "launch") else None


def _warn_engine_broken(full, exc):
    """El motor existe pero falló al cargar — NO es 'no instalado'. Rastro
    ruidoso + traceback a stderr. Falla-suave: avisar nunca rompe."""
    try:
        import traceback
        sys.stderr.write(
            "WORKSPACE: el motor '%s' EXISTE pero FALLÓ al cargar (%s: %s).\n"
            "  Esto NO es 'motor no instalado' — es una regresión real (revisa "
            "el archivo del engine o una actualización reciente):\n"
            % (full, type(exc).__name__, exc))
        traceback.print_exc()
    except Exception:
        pass


# ── Aislamiento de credenciales por agente (opt-in: "isolate": true en agent.json) ──
def _agent_home(agent_name):
    """Home per-agente para AISLAR credenciales de subprocesos. Per-máquina, fuera del
    repo. NO es el HOME del proceso — Claude Code necesita el HOME real para su auth."""
    return os.path.join(_paths.state_dir(), "agents",
                        (agent_name or "agent"), "home")


def isolation_vars(agent_name):
    """Vars que redirigen las credenciales de SUBPROCESOS (git/gh/npm/gpg/ssh) a
    un home per-agente, SIN tocar HOME (Claude Code necesita el HOME real para SU
    auth). Así un agente no filtra sus credenciales a otro. Crea los dirs.

    Cubre (F2):
      · git USER  → GIT_CONFIG_GLOBAL (~/.gitconfig per-agente).
      · git SYSTEM→ GIT_CONFIG_SYSTEM a un archivo vacío per-agente → corta el
        /etc/gitconfig del sistema, INCLUIDO el credential.helper (osxkeychain,
        manager) que vivía ahí: un agente aislado ya no hereda el keychain.
      · git SSH   → GIT_SSH_COMMAND con IdentitiesOnly=yes + IdentityFile a una
        .ssh per-agente + IdentityAgent=none → no usa ~/.ssh del socio ni el
        ssh-agent. Push sobre SSH ya NO va con la identidad del socio.
      · gh / npm / gpg → sus dirs de config per-agente.

    NO cubre (por diseño, HOME es el real): cualquier credencial que un proceso
    lea por HOME directo sin honrar estas vars. Para esos casos, HOME real es
    intencional (auth de Claude Code)."""
    h = _agent_home(agent_name)
    os.makedirs(h, exist_ok=True)
    # GIT_CONFIG_SYSTEM debe APUNTAR a un archivo (vacío) — no a un dir. Un
    # archivo vacío vetado del sistema corta credential.helper de /etc.
    sys_cfg = os.path.join(h, ".gitconfig-system")
    try:
        if not os.path.exists(sys_cfg):
            open(sys_cfg, "w").close()
    except OSError:
        sys_cfg = os.devnull   # falla-suave: al menos no leer el del sistema
    ssh_dir = os.path.join(h, ".ssh")
    try:
        os.makedirs(ssh_dir, exist_ok=True)
    except OSError:
        pass
    # SSH aislado: solo identidades de ESTE agente, sin ssh-agent del socio.
    # IdentityFile a un path que puede no existir aún (el socio coloca la llave
    # del agente ahí si quiere que pueda push) — IdentitiesOnly evita el fallback
    # a ~/.ssh/id_* del socio. Comillas: el path puede llevar espacios.
    ssh_key = os.path.join(ssh_dir, "id_ed25519")
    git_ssh = ('ssh -o IdentitiesOnly=yes -o IdentityAgent=none '
               '-o IdentityFile="%s"' % ssh_key)
    return {
        "GIT_CONFIG_GLOBAL": os.path.join(h, ".gitconfig"),
        "GIT_CONFIG_SYSTEM": sys_cfg,
        "GIT_SSH_COMMAND": git_ssh,
        "GH_CONFIG_DIR": os.path.join(h, "gh"),
        "NPM_CONFIG_USERCONFIG": os.path.join(h, ".npmrc"),
        "GNUPGHOME": os.path.join(h, "gnupg"),
        "WORKSPACE_AGENT_HOME": h,
    }


def _apply_isolation(name):
    """Aplica isolation_vars al entorno. must-fix #3 · FAIL-CLOSED: isolate:true
    es un opt-in de SEGURIDAD; si no se puede preparar el home aislado NO
    arrancamos en silencio con las credenciales reales del socio (fail-open
    mudo) — abortamos ruidoso. Mejor no-arrancar que filtrar credenciales."""
    try:
        os.environ.update(isolation_vars(name))
    except Exception as e:
        sys.stderr.write(
            "WORKSPACE: '%s' pide aislamiento de credenciales (isolate:true) "
            "pero NO se pudo preparar el home aislado (%s: %s). Abortado para "
            "no exponer tus credenciales reales al agente.\n"
            % (name, type(e).__name__, e))
        sys.exit(1)


def _spawn_repair():
    """P0-3 · auto-render self-healing: tras un pull que TRAJO cambios, re-renderiza
    los hooks de cada cerebro (un rename de hook / listener nuevo en events.py deja
    settings.local.json stale → este spawn lo recabla en el siguiente arranque).

    FIRE-AND-FORGET y NO-BLOCKING por diseño: lanza `front.py repair` en un proceso
    DETACHED (no se espera su salida) y se traga CUALQUIER error — el arranque del
    agente jamás se bloquea ni se rompe por el render. Desactivable con
    WORKSPACE_NO_AUTORENDER=1. Mac/Linux: start_new_session; Windows: CREATE_NO_WINDOW
    | CREATE_NEW_PROCESS_GROUP (0x208, igual que el dashboard de dev)."""
    if os.environ.get("WORKSPACE_NO_AUTORENDER"):
        return
    try:
        import subprocess
        front = os.path.join(ROOT, "front.py")
        kw = {"creationflags": 0x208} if os.name == "nt" else {"start_new_session": True}
        subprocess.Popen([sys.executable or "python3", front, "repair"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, **kw)
    except Exception:
        return   # falla-suave absoluta: el render jamás bloquea ni rompe el arranque


def _tinted(txt):
    """Aviso del auto-update antes de lanzar un agente, con el ACENTO del tema
    del hub (antes, el dorado fijo del recinto viejo). Termina en salto de
    línea. Falla-suave: sin tuitheme, el texto tal cual."""
    try:
        import tuitheme
        P = tuitheme.palette()
        return "%s%s%s\n" % (P.C, txt, P.R)
    except Exception:
        return "%s\n" % txt


def maybe_autoupdate():
    """Auto-update silencioso al arrancar (canal git del equipo y de clientes).

    Diseñado para ser INOFENSIVO: es NO-OP si la carpeta no es un repo git
    (instalaciones viejas por sync), si hay cambios locales sin commitear, si está
    offline, o ante cualquier error. Nunca bloquea ni rompe el arranque del agente.
    Throttle: máximo 1 chequeo cada 6 h. Es ELECCIÓN del usuario
    (updater.auto_mode: ajuste `otros.auto_update` o WORKSPACE_NO_AUTOUPDATE=1):
    auto = instala · notify = solo avisa (1 vez al día) · off = ni consulta.

    El trabajo lo hace `updater.update_harness(mode="auto")` — el MISMO motor que
    `workspace update`: candado, solo fast-forward, comprueba que la versión nueva
    arranca en esta máquina (si no, vuelve sola a la anterior y la fija) y aplica
    los ajustes registrados. Aquí solo queda el throttle y UNA línea visible.
    """
    if os.environ.get("WORKSPACE_NO_AUTOUPDATE"):
        return
    # Ajustes pendientes SIN mirar el throttle NI el modo: no traen nada de
    # internet, adaptan esta máquina al código que YA está en ella (llegue por
    # update, `git pull` a mano o un actualizador viejo). Apagar las
    # actualizaciones no debe dejar a nadie con código nuevo a medio ajustar.: el código nuevo puede haber
    # llegado por un actualizador viejo (que no lanza `repair` tras un pull
    # silencioso) o por un `git pull` a mano. `repair` los aplica en segundo
    # plano con el código nuevo; jamás bloquea este arranque.
    try:
        import migrate
        if migrate.has_runnable_pending():
            _spawn_repair()
    except Exception:
        pass
    if not os.path.exists(os.path.join(ROOT, ".git")):
        return  # no es repo git → instalación por sync; no tocar nada
    try:
        import time
        import updater
        modo = updater.auto_mode()
        if modo == "off":
            return  # el usuario lo apagó: ni red, ni aviso
        stamp = os.path.join(_paths.state_dir(), "last_update_check")

        def _seal():
            """Sella el throttle: el próximo chequeo no corre hasta dentro de 6h.
            Se sella en TODO desenlace cuyo resultado no cambiará en el siguiente
            arranque (sin remote, repo sucio, ya al día, actualizado, fijado) — F7.
            NO se sella si el intento FALLA por algo transitorio (red/candado) →
            reintentar pronto, no quedar 6h ciego a un fix urgente."""
            try:
                os.makedirs(os.path.dirname(stamp), exist_ok=True)
                open(stamp, "w").close()
            except Exception:
                pass

        # solo avisar = una vez al día (avisar cada 6 h sería insistir)
        ventana = 24 * 3600 if modo == "notify" else 6 * 3600
        if os.path.exists(stamp) and time.time() - os.path.getmtime(stamp) < ventana:
            return  # throttle

        def _notify(txt):
            sys.stderr.write(_tinted(txt))
            sys.stderr.flush()

        res = updater.update_harness(ROOT, mode="auto", fetch_timeout=20, notify=_notify,
                                     apply=(modo == "auto"))
        st, why = res.get("status"), res.get("reason")
        if why == "offline":
            # Sin red: reintentar en ~30 min, no en cada arranque (cada intento
            # cuesta hasta 20 s de espera con la red caída).
            _seal()
            try:
                t = time.time() - (6 * 3600 - 30 * 60)
                os.utime(stamp, (t, t))
            except Exception:
                pass
            return
        if st == updater.BUSY or why in ("failed", "interrupted"):
            return  # transitorio → NO sellar: reintentar al próximo arranque
        _seal()
        if st == updater.AVAILABLE:
            v = res.get("to_version")
            sys.stderr.write(_tinted(updater._t(
                "updater.auto.available",
                "Hay una versión nueva de Workspace{v}. Para instalarla: `workspace update` "
                "(elegiste solo avisar; se cambia en Actualizaciones).",
                v=(" (v%s)" % v) if v else "")))
        elif st == updater.UPDATED:
            v = res.get("to_version")
            sys.stderr.write(_tinted(updater._t(
                "updater.auto.updated", "✓ Workspace actualizado a v{v}.", v=v or "?")))
            mig = res.get("migrations") or {}
            if mig.get("failed"):
                import migrate
                sys.stderr.write(_tinted(migrate.summary_line(mig)))
            # P0-3 · self-healing: el pull trajo código nuevo (quizá renombró un
            # hook o sumó un listener) → recablear settings.local.json de cada
            # cerebro. Fire-and-forget, jamás bloquea el arranque (ver _spawn_repair).
            _spawn_repair()
        elif st == updater.ROLLBACK_FAILED:
            sys.stderr.write(_tinted(updater._t(
                "updater.auto.rollback_failed",
                "⚠ La versión nueva de Workspace no arrancó y no pude volver limpio a la "
                "anterior. Corre `workspace doctor` (y si sigue, `workspace doctor "
                "--bundle` para pedir ayuda).")))
        elif st == updater.ROLLED_BACK:
            sys.stderr.write(_tinted(updater._t(
                "updater.auto.rolled_back",
                "⚠ Llegó una versión nueva de Workspace que no arranca en esta máquina; "
                "sigues en la anterior. No tienes que hacer nada.")))
    except Exception:
        return  # offline / timeout / lo que sea → seguir normal


def cmd_list():
    reg = load_registry()
    print("\n  Agentes registrados en WORKSPACE:\n")
    for a in reg.get("agents", []):
        # agentes CARGADOS no tienen `dir` (viven en su cerebro); muestra brain
        loc = ("brain=%s" % a["brain"]) if a.get("brain") else ("dir=agents/%s" % a.get("dir", "?"))
        print(f"    {a.get('name','?'):<12} engine={a.get('engine','?'):<14} {loc}")
    if reg.get("planned"):
        print("\n    Planeados (aún no activos): " + ", ".join(reg["planned"]))
    print()


def main():
    argv = sys.argv[1:]
    plan = False
    if argv and argv[0] in ("--plan", "-n"):
        plan, argv = True, argv[1:]
    if argv and argv[0] == "--list":
        cmd_list(); return
    if not argv:
        print("uso: dispatch.py [--plan] <agente> [args...]   |   dispatch.py --list")
        sys.exit(2)

    name, rest = argv[0], argv[1:]
    # Flags propios de WORKSPACE (lo demás pasa a claude):
    #   --open <wid>  --name <ws>   abrir directo un workspace (sin menú; lo usa tmux)
    #   --no-banner                 omitir el banner (ventanas tmux)
    #   --pick-only                 solo correr el menú y devolver la elección (lo usa mux.py)
    #   --engine <n>                cambiar de motor SOLO esta corrida (selection-source
    #                               policy: elección explícita del socio = estricta)
    #   --plan | -n                 wiring sin lanzar — válido en CUALQUIER posición
    #                               (no solo como primer arg)
    preselect, show_banner, pick_only, passthrough = {}, True, False, []
    engine_cli = ""

    def _flag_value(flag, idx):
        # I2: una flag con valor exige un valor PRESENTE y que no sea otra flag.
        # Antes `rest[i] if i < len(rest) else ""` se tragaba el token siguiente a
        # ciegas (`--engine --name x` → engine="--name") o quedaba vacío sin avisar.
        nxt = rest[idx + 1] if idx + 1 < len(rest) else None
        if nxt is None or nxt.startswith("--"):
            sys.stderr.write("WORKSPACE: %s requiere un valor.\n" % flag)
            sys.exit(2)
        return nxt

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--open":
            preselect["wid"] = _flag_value(a, i); i += 1
        elif a == "--name":
            preselect["name"] = _flag_value(a, i); i += 1
        elif a == "--no-banner":
            show_banner = False
        elif a == "--pick-only":
            pick_only = True
        elif a == "--agent-sandbox" or (a == "--sandbox" and i + 1 < len(rest)
                                         and rest[i + 1] in ("on", "off")):
            # Compat: el sandbox de archivos por agente NO viaja en esta
            # versión (vive en feat/agent-sandbox). Sus flags se IGNORAN (no
            # llegan al motor) y el agente arranca normal. `--sandbox
            # read-only|…` del motor sigue pasando tal cual.
            if a == "--agent-sandbox" and i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                i += 1
            elif a == "--sandbox":
                i += 1
        elif a in ("--sandbox=on", "--sandbox=off", "--agent-sandbox=on", "--agent-sandbox=off"):
            pass                                  # idem: compat, se ignora
        elif a == "--engine":
            engine_cli = _flag_value(a, i); i += 1
        elif a in ("--plan", "-n"):
            # --plan vale en CUALQUIER posición (los docstrings de engines/
            # documentan `dispatch.py zenith --engine stub --plan`; antes solo
            # se aceptaba como PRIMER arg y aquí caía a passthrough → LANZABA).
            plan = True
        else:
            passthrough.append(a)
        i += 1
    preselect = preselect or None

    if not plan and not pick_only:
        maybe_autoupdate()

    entry = find_agent(name)
    if not entry:
        print(f"WORKSPACE: no conozco al agente '{name}'. Corre:  dispatch.py --list")
        sys.exit(1)

    cfg = load_agent_cfg(entry)
    if cfg.get("_missing_def"):
        print(f"WORKSPACE: '{name}' está registrado pero su definición falta o está "
              f"corrupta:\n  {os.path.join(cfg.get('_dir', ''), 'agent.json')}\n"
              f"Re-cárgalo:  python3 agent_admin.py load \"{entry.get('brain', '')}\"")
        sys.exit(1)
    brain = resolve_brain(entry["name"], cfg)
    if not brain or not os.path.isdir(brain):
        print(f"WORKSPACE: no encuentro el cerebro de '{name}':\n  {brain or '(sin definir)'}\n"
              f"Corre el instalador (lo detecta solo) o defínelo en {_paths_local()}  (clave brains.{name}).")
        try:                                   # Z03: sugerencia del índice de discovery (sin escanear)
            import agentsreg
            for s in agentsreg.repair_suggestions(scan_mode="index"):
                if s["name"] == entry["name"] and s.get("found"):
                    print(f"Encontrado en {s['found']} — repáralo:  "
                          f"workspace agentes reubicar {s['name']} \"{s['found']}\"")
        except Exception:
            pass
        sys.exit(1)

    cfg["_brain"] = brain
    cfg["_scripts"] = expand_scripts(cfg, brain)
    # Los scripts de UI (banner/dashboard/statusline) reciben su cerebro por env —
    # nunca lo derivan de su propia ubicación (__file__).
    os.environ["WORKSPACE_BRAIN"] = brain
    # El harness ANUNCIA su ubicación: los scripts de brand BRAIN-RESIDENT (que ya
    # viven DENTRO del cerebro) usan $WORKSPACE_ROOT para alcanzar los servicios
    # compartidos del harness (status/presencia + bus de mensajes) y fallan-suave si
    # no está (= correr el cerebro SIN harness). Es la relación simbiótica:
    # independientes para identidad/brand, enriquecidos por el harness para comunicarse.
    os.environ["WORKSPACE_ROOT"] = ROOT
    # QUIÉN es el agente de esta corrida — lo heredan los subprocesos (claude y sus
    # hooks). Lo usan: el hook SessionEnd para auto-liberar los worktrees de ESTE
    # agente al cerrar, y telemetry.py para etiquetar eventos. Nombre canónico del
    # registro (no el alias tecleado).
    os.environ["WORKSPACE_AGENT_NAME"] = entry["name"]
    engine = cfg.get("engine") or entry.get("engine") or _settings_default_engine()
    # Cambio de motor sin tocar agent.json — precedencia
    #   cli (--engine) > env (WORKSPACE_ENGINE) > settings agentes.<n>.engine
    #   (override PER-MÁQUINA, tier A) > agent.json.
    # El override per-máquina NO es "explícito de la corrida" (source 'settings',
    # no 'cli'/'env'): conserva la cadena de fallbacks del provider — a
    # diferencia de un --engine/env, que la vacía (selection-source, OpenClaw).
    engine_src = "agent"
    ov_engine = _settings_agent_engine(entry["name"])
    if ov_engine:
        engine, engine_src = ov_engine, "settings"
    env_engine = (os.environ.get("WORKSPACE_ENGINE") or "").strip()
    if env_engine:
        engine, engine_src = env_engine, "env"
    if engine_cli:
        engine, engine_src = engine_cli, "cli"
    cfg["engine"] = engine            # el motor REAL de esta corrida
    cfg["_engine_source"] = engine_src

    mod = load_engine(engine)
    if mod is None:
        avail = ", ".join(available_engines()) or "(ninguno)"
        print(f"WORKSPACE: el motor '{engine}' no está disponible o no cumple el contrato.\n"
              f"  Motores instalados: {avail}\n"
              f"  Para crear uno nuevo: copia engines/_template.py (contrato en engines/CONTRACT.md).")
        sys.exit(1)
    if cfg.get("isolate"):   # opt-in: aísla credenciales de subprocesos de este agente
        if plan:
            print(f"WORKSPACE: aislamiento de credenciales ON · home del agente: {_agent_home(entry['name'])}")
        else:
            _apply_isolation(entry["name"])   # fail-CLOSED (must-fix #3)

    if pick_only:
        sys.stdout.write(mod.pick(cfg) if hasattr(mod, "pick") else "")
        return
    if not plan:
        # El FONDO/tinta del chat es del TEMA del hub, no del agente (el socio
        # 2026-10-02) — espejo de front.py: tema no-default trae su propio
        # fondo (tui.osc en themes/<id>/theme.json); olympo usa el tema
        # legacy 'workspace' de themes.json. Con muchos agentes el color-por-
        # agente no escala (arcoíris); la identidad queda en banner y nombre.
        try:
            import theme
            theme.apply_current()          # SU fondo/tinta (tui.osc) o los de la terminal
        except Exception:
            pass
        # Y el tema DENTRO del motor (Claude Code: ~/.claude/themes/<n>.json)
        # también sale del tema del hub — cambiar el tema en el hub llega a la
        # siguiente sesión de cada agente. Lo editado a mano se respeta.
        try:
            import theme_render
            theme_render.sync_engine_theme(engine, cfg.get("theme") or entry["name"],
                                           display=cfg.get("display"), brain=brain)
        except Exception:
            pass
    mod.launch(cfg, passthrough, plan=plan, preselect=preselect, show_banner=show_banner)


if __name__ == "__main__":
    main()
