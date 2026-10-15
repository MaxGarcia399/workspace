#!/usr/bin/env python3
"""WORKSPACE · doctor — instalador-reparador por FASES, idempotente.

`workspace doctor`           revisa cada fase y REPARA lo que pueda (fase OK → se salta).
`workspace doctor --check`   solo diagnostica: tabla de salud, NO modifica nada y
                             NO consulta el remoto (sin `git fetch`: compara contra
                             las refs LOCALES y lo dice explícitamente).
`workspace doctor --check --remote`  diagnóstico + verificación REMOTA explícita
                             (`git fetch` de los repos git; alias `--fetch`).
`workspace doctor --tests`   corre la suite de tests del harness (tests/run.py, N18).

Es el mismo comando para una máquina nueva (instala lo que falta) y para una
existente (repara lo que se rompió). Correrlo dos veces no duplica ni rompe nada.

ALCANCE (regla de producto, 0.2.1): el doctor revisa y repara SOLO lo esencial
para que Workspace funcione — git/Python/el CLI del motor, las actualizaciones,
los agentes VISIBLES del usuario (su carpeta, sus hooks, sus comandos) y los
restos de la instalación anterior. Nada más: ni convenciones internas de
cerebros, ni funciones opcionales (voz, terminal partida: cada usuario decide;
`workspace voice --check` revisa la voz). Se comporta IGUAL en cualquier
instalación. Los agentes internos (dispatch.is_system_agent) jamás se revisan,
y "aún no hay agentes" es un estado normal (✓), nunca ⚠.

Fases (cada una: CHECK → ¿ya conectada? → saltar · si no → FIX o acción manual):
  1. Prerrequisitos       git · python 3.9+ · CLI de los MOTORES que usan los
                          agentes visibles (claude/codex/agy…)          [solo instruye]
  1b. Rutas en la nube    OneDrive/known-folders                       [solo detección]
  2. Carpetas de cerebros cada agente → su carpeta                      [solo instruye]
  3. Al día               WORKSPACE detrás de origin → actualizador
  3b. Versión y ajustes   versión, versión fijada, migraciones pendientes/fallidas
  4. Cerebros resolubles  resolución canónica + sesiones (resume, solo Claude Code)
  5. Hooks por cerebro    settings.local.json → SOLO `hooks` (+ `statusLine` si
                          apunta a ruta vieja) · detecta hooks que apuntan a un
                          Workspace o intérprete que ya no existe
  5c. MCPs                solo si el agente tiene MCPs configurados
  5d. Instalación anterior restos per-máquina (anti-recurrencia)
  6. Launchers            `workspace` + un comando por agente           [reusa install.py]
  7. Greeter · retención  greeter (opcional: nunca ⚠, nunca se re-impone) ·
                          cleanupPeriodDays (365 si no hay valor propio; nunca ⚠)

TRANSPORT DE CEREBROS: el DEFAULT (dispatch.brain_transport) es que el cerebro
es una carpeta del usuario, NO un repo que Workspace actualice: las fases 2 y 3
JAMÁS le marcan ⚠/✗ de git. git solo se valida si se declara por máquina en
paths.local.json → {"transport": {"<agente>": "git"}}. WORKSPACE sí va por git.

REGLA DURA: el doctor NUNCA escribe `permissions` en settings.local.json.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Vive en git → se
auto-actualiza con `workspace update`.
"""
import os
import re
import sys
import json
import shutil
import subprocess

sys.dont_write_bytecode = True   # no generar __pycache__ (mantiene limpio el sync)
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import paths as _paths  # noqa: E402  (SSOT del dir de estado — tests/test_state_dir_guard.py)
import dispatch   # noqa: E402  (registry efectivo + transporte de cerebros)
import brain_resolver  # noqa: E402  (Z20 — resolución CANÓNICA de cerebros, la misma que dispatch)
import install    # noqa: E402  (fixers ya probados: launchers, greeter, hooks)
import events     # noqa: E402  (contrato de eventos N9 — la fase 5 valida contra él)
import session_paths  # noqa: E402  (única fuente del path de sesiones de Claude Code)
import legacy     # noqa: E402  (literales de la instalación anterior — fase 5d)
import pathguard   # noqa: E402  (P0-4 — detección de rutas redirigidas a OneDrive)

HOME = os.path.expanduser("~")
IS_WIN = os.name == "nt"
if IS_WIN:
    os.system("")  # habilita ANSI en Windows 10+ (no-op en consolas viejas)
import _utf8; _utf8.harden()  # B2 · UTF-8 en stdout/err (cp1252 reventaría con box-drawing)


def _t(key, default, **kw):
    """i18n falla-suave (patrón de updater/migrate): cadena del idioma activo;
    sin catálogo/clave → el `default` español (con .format(**kw))."""
    try:
        import i18n
        s = i18n.t(key, **kw)
        if s != key:
            return s
    except Exception:
        pass
    try:
        return default.format(**kw) if kw else default
    except Exception:
        return default


def _fg(n):
    return f"\033[38;5;{n}m"


# Paleta del TEMA del hub (tuitheme — la misma del hub y de cada sección):
# acento, tinta, tenue, ok, aviso y error salen de los roles del tema; en una
# terminal sin color (NO_COLOR) no hay ANSI. Antes era el dorado fijo del
# recinto viejo. Sin tuitheme (copia rota) quedan índices neutros.
C, WH, DIM, GREY = _fg(152), _fg(255), _fg(245), _fg(242)
GRN, YEL, RED = _fg(114), _fg(180), _fg(203)
R, BO = "\033[0m", "\033[1m"
try:
    import tuitheme as _tuitheme
    _TP = _tuitheme.palette()
    C, WH, DIM, GREY = _TP.C, _TP.WH, _TP.DIM, _TP.GREY
    GRN, YEL, RED = _TP.OK, _TP.B, _TP.BAD
    R, BO = _TP.R, _TP.BO
except Exception:
    pass

OK, FIXED, WARN, FAIL = "ok", "fixed", "warn", "fail"
SYM = {OK: f"{GRN}✓{R}", FIXED: f"{C}✓{R}", WARN: f"{YEL}⚠{R}", FAIL: f"{RED}✗{R}"}
RANK = {OK: 0, FIXED: 1, WARN: 2, FAIL: 3}

# Default conservador del bloque `setup`: FUENTE ÚNICA en events.py (Tema D) —
# doctor e install comparten el merge (`setup_of`) y el gate (`gated`) para no
# divergir (antes install ignoraba el gate `requires` que doctor sí aplicaba).
SETUP_DEFAULTS = events.SETUP_DEFAULTS


def _setup(cfg):
    """Bloque `setup` del agent.json mergeado sobre SETUP_DEFAULTS (vía events)."""
    return events.setup_of(cfg)


def f(status, label, detail="", action=""):
    return {"status": status, "label": label, "detail": detail, "action": action}


def _run(cmd, timeout=25, cwd=None):
    """(returncode, stdout, stderr). returncode -1 = no se pudo correr (timeout, falta binario…)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=cwd)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)


def _read_json(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _is_git(path):
    return os.path.exists(os.path.join(path, ".git"))   # dir, o archivo en un worktree


def _in_repo(path):
    """True si `path` vive DENTRO de WORKSPACE (agente IN-REPO).

    Patron legitimo del harness: un agente cuyo cerebro viaja dentro del propio
    repo (`brain: "."` relativo a agents/<nombre>/) para que la app lo lleve
    consigo en cualquier maquina. Esos
    agentes NO tienen carpeta hermana propia: viajan y se actualizan con
    WORKSPACE (git).
    """
    if not path:
        return False
    try:
        r, p = os.path.normcase(os.path.realpath(ROOT)),                os.path.normcase(os.path.realpath(path))
        return p == r or p.startswith(r + os.sep)
    except Exception:
        return False


def _help_hint():
    """Qué hacer cuando algo falla y el doctor no sabe arreglarlo: el mismo
    texto para todos (sin canales internos)."""
    return _t("doctor.help_hint", "si no se resuelve, `workspace doctor --bundle` "
              "genera un zip de diagnóstico para pedir ayuda")


# ══════════════════════════════════════════════════════════════════════════
#  Contexto compartido entre fases
# ══════════════════════════════════════════════════════════════════════════
def build_ctx():
    """Agentes que el doctor revisa: SOLO los visibles del usuario. Los internos
    (dispatch.is_system_agent: SYSTEM_AGENTS o `hidden: true`) se ignoran en
    TODAS las fases — un registro viejo de un motor interno no es algo que el
    usuario tenga que mantener (era el origen de avisos de BOOT/INDEX/resume
    sobre un agente que el cliente ni conoce)."""
    reg = dispatch.load_registry()
    agents = []
    names = []
    for a in reg.get("agents", []):
        try:
            cfg = dispatch.load_agent_cfg(a)
        except Exception:
            cfg = {}
        if dispatch.is_system_agent(a, cfg):
            continue
        res = brain_resolver.resolve(a["name"], cfg, a)
        agents.append({"entry": a, "name": a["name"], "cfg": cfg,
                       "brain": res.path, "resolution": res})
        names += [a["name"]] + [x for x in a.get("aliases", []) if x != a["name"]]
    return {"agents": agents, "agent_names": list(dict.fromkeys(names))}


def _resolved_brains(ctx):
    """[(agent_name, brain_path)] solo de cerebros que existen en disco."""
    return [(a["name"], a["brain"]) for a in ctx["agents"]
            if a["brain"] and os.path.isdir(a["brain"])]


# ══════════════════════════════════════════════════════════════════════════
#  FASE 1 · Prerrequisitos (nunca auto-instala: solo diagnostica e instruye)
# ══════════════════════════════════════════════════════════════════════════
# Harness-agnóstico (objetivo WORKSPACE 2026-10): el CLI que se exige es el de
# cada MOTOR que los agentes registrados usan de verdad (claude-code → claude,
# codex → codex, gemini → gemini…), no un harness horneado. Sin agentes
# registrados no se exige ninguno (instalación recién nacida / cliente).
ENGINE_BINARIES = {"claude-code": "claude"}   # motores sin BINARY declarado
ENGINE_INSTALL_HINTS = {
    "claude-code": "instala Claude Code (npm install -g @anthropic-ai/"
                   "claude-code) e inicia sesión con la suscripción",
    "codex": "instala Codex CLI (npm install -g @openai/codex) e inicia sesión",
    "gemini": "instala Gemini CLI (npm install -g @google/gemini-cli) "
              "e inicia sesión",
}


def _engine_of(a):
    """El motor REAL de un agente del ctx, con la precedencia de dispatch sin
    red: override per-máquina (settings) > agent.json > entry del registry >
    default claude-code. Fail-soft: si algo no se puede leer, cae a lo
    declarado."""
    eng = ((a.get("cfg") or {}).get("engine") or (a.get("entry") or {}).get("engine")
           or "claude-code")
    try:
        ov = dispatch._settings_agent_engine(a["name"])
        if ov:
            eng = ov
    except Exception:
        pass
    return eng


def _engines_in_use(ctx):
    """{engine: [agentes]} de los agentes visibles."""
    use = {}
    for a in ctx["agents"]:
        use.setdefault(_engine_of(a), []).append(a["name"])
    return use


def phase_prereqs(ctx, fix):
    out = []
    # git
    git = shutil.which("git")
    if git:
        _, v, _ = _run(["git", "--version"], timeout=10)
        out.append(f(OK, "git", v or git))
    else:
        out.append(f(FAIL, _t("doctor.phase_prereqs.1", "git no está en PATH"), "",
                     _t("doctor.phase_prereqs.2", "instala Git (https://git-scm.com) y abre una terminal nueva")))
    # python (estamos corriendo en él; solo validar versión)
    if sys.version_info >= (3, 9):
        out.append(f(OK, "python", f"{sys.version.split()[0]} · {sys.executable}"))
    else:
        out.append(f(WARN, _t("doctor.phase_prereqs.3", "python viejo"), sys.version.split()[0],
                     _t("doctor.phase_prereqs.4", "instala Python 3.9+ — WORKSPACE lo requiere")))
    # CLI de los MOTORES en uso (harness-agnóstico): se valida el binario de
    # cada engine que algún agente registrado usa — nada de asumir uno solo.
    engines = _engines_in_use(ctx)
    if not engines:
        out.append(f(OK, _t("doctor.phase_prereqs.5", "motores"), _t("doctor.phase_prereqs.6", "aún no hay agentes — el CLI del motor se revisa cuando agregues el primero")))
    for eng, who in sorted(engines.items()):
        try:
            mod = dispatch.load_engine(eng)
        except Exception:
            mod = None
        if mod is None:
            out.append(f(FAIL, _t("doctor.phase_prereqs.7", "motor '{eng}' no disponible", eng=eng),
                         _t("doctor.used_by", "lo usan: {who}", who=', '.join(who)),
                         _t("doctor.phase_prereqs.8", "engines/{v}.py falta o no carga — actualiza el harness (`workspace update`) o corrige el agente a un motor instalado", v=eng.replace('-', '_'))))
            continue
        binary = getattr(mod, "BINARY", None) or ENGINE_BINARIES.get(eng)
        if not binary:      # motor sin BINARY: su META declara qué necesita
            needs = (getattr(mod, "META", None) or {}).get("needs") or []
            binary = needs[0] if needs and isinstance(needs[0], str) else None
        if not binary:
            out.append(f(OK, _t("doctor.phase_prereqs.9", "motor '{eng}'", eng=eng),
                         _t("doctor.phase_prereqs.10", "sin CLI externo que validar · lo usan: {v}", v=', '.join(who))))
            continue
        exe = shutil.which(binary)
        if exe:
            _, v, _ = _run([binary, "--version"], timeout=15)
            out.append(f(OK, _t("doctor.phase_prereqs.11", "{binary} CLI (motor {eng})", binary=binary, eng=eng), v or exe))
        else:
            out.append(f(FAIL, _t("doctor.phase_prereqs.12", "{binary} CLI no está en PATH (motor '{eng}')", binary=binary, eng=eng),
                         _t("doctor.used_by", "lo usan: {who}", who=', '.join(who)),
                         _t("doctor.install_hint." + eng, ENGINE_INSTALL_HINTS[eng])
                         if eng in ENGINE_INSTALL_HINTS else
                         _t("doctor.install_hint.generic",
                            "instala el CLI `{binary}` de ese motor y abre una "
                            "terminal nueva", binary=binary)))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 1b · Rutas redirigidas a la nube (OneDrive/known-folders) — SOLO DETECCIÓN
# ══════════════════════════════════════════════════════════════════════════
# P0-4: OneDrive (y la redirección de Desktop/Documents) sincroniza y bloquea
# los archivos del harness → locks, latencia, estado per-máquina pisado. Si
# WORKSPACE o un cerebro vive ahí
# → FAIL con instrucción de reubicar. SOLO DETECCIÓN (read-only por diseño, como
# las fases 9/10): `fix` NO mueve nada — la reubicación es decisión/acción del
# socio. En Mac/Linux pathguard.redirected_root devuelve "" siempre → no-op limpio.
def phase_redirected_paths(ctx, fix):
    out = []
    root_lbl = pathguard.redirected_root(ROOT)
    if root_lbl:
        out.append(f(FAIL, _t("doctor.phase_redirected_paths.1", "WORKSPACE vive en una ruta redirigida a la nube"),
                     f"{ROOT}  (bajo {root_lbl})",
                     _t("doctor.phase_redirected_paths.2", "muévelo FUERA de OneDrive — a %LOCALAPPDATA%\\Workspace o C:\\Workspace — y reinstala (python install.py). OneDrive sincroniza y BLOQUEA los archivos del harness (locks, latencia, settings per-máquina) → fallos intermitentes difíciles de diagnosticar")))
    else:
        out.append(f(OK, _t("doctor.phase_redirected_paths.3", "WORKSPACE fuera de rutas redirigidas (OneDrive/known-folders)"), ROOT))
    for name, brain in _resolved_brains(ctx):
        lbl = pathguard.redirected_root(brain)
        if lbl:
            up = name.upper()
            out.append(f(FAIL, _t("doctor.phase_redirected_paths.4", "[{name}] el cerebro vive en una ruta redirigida a la nube", name=name),
                         f"{brain}  (bajo {lbl})",
                         _t("doctor.phase_redirected_paths.5", "muévelo a C:\\{up} - BRAIN (fuera de OneDrive) y vuelve a declararlo en {v}  →  {{\"brains\": {{\"{name}\": \"C:\\\\{up} - BRAIN\"}}}}. Los bloqueos y la latencia de la nube rompen sesiones (resume) y el estado per-máquina (settings.local.json)", up=up, v=dispatch._paths_local(), name=name)))
        else:
            out.append(f(OK, _t("doctor.phase_redirected_paths.6", "[{name}] cerebro fuera de rutas redirigidas", name=name), brain))
    return out


def _resolution(a):
    """Resolución canónica (brain_resolver) del agente del ctx — la de
    build_ctx si viene, o recalculada. Siempre con fuente y estado."""
    res = a.get("resolution")
    if res is None or res.path != (a.get("brain") or ""):
        res = brain_resolver.resolve(a["name"], a.get("cfg") or {}, a.get("entry"))
        a["resolution"] = res
    return res


def _suggestion_for(ctx, name, fix=False):
    """Sugerencia de reparación (discovery acotado + índice) para un agente con
    cerebro roto. Se calcula UNA vez por corrida. Falla-suave → None."""
    if "suggestions" not in ctx:
        try:
            import agentsreg
            # --check no escribe ni el índice de discovery (caché por máquina)
            ctx["suggestions"] = {s["name"]: s for s in
                                  agentsreg.repair_suggestions(persist=bool(fix))}
        except Exception:
            ctx["suggestions"] = {}
    return ctx["suggestions"].get(name)


# ══════════════════════════════════════════════════════════════════════════
#  FASE 2 · Carpetas de los cerebros (solo instruye: no clona ni mueve nada)
# ══════════════════════════════════════════════════════════════════════════
def phase_siblings(ctx, fix):
    out = []
    if _is_git(ROOT):
        out.append(f(OK, _t("doctor.phase_siblings.1", "WORKSPACE es repo git"), ROOT))
    else:
        out.append(f(WARN, _t("doctor.phase_siblings.2", "WORKSPACE no es repo git"),
                     _t("doctor.phase_siblings.3", "sin git no recibe actualizaciones"),
                     _t("doctor.phase_siblings.4", "reinstala con el instalador (setup.sh / setup.ps1) para recibir actualizaciones")))
    for a in ctx["agents"]:
        name = a["name"]
        # IN-REPO primero: su cerebro vive dentro de WORKSPACE y exigirle carpeta
        # hermana era un FALSO ROJO (hallazgo 2026-09-21).
        if _in_repo(a.get("brain")) and os.path.isdir(a.get("brain") or ""):
            out.append(f(OK, _t("doctor.phase_siblings.5", "cerebro \"{name}\" in-repo", name=name),
                         _t("doctor.phase_siblings.6", "vive dentro de Workspace y viaja con él")))
            continue
        raw = a["cfg"].get("brain", "")
        target = os.path.basename(os.path.normpath(raw)) if raw else name
        sibling = os.path.join(os.path.dirname(ROOT), target)
        # W-F02: el estado lo decide el resolver CANÓNICO (el mismo del launcher),
        # no la «carpeta hermana». Un cerebro registrado por ruta absoluta fuera
        # del repo es VÁLIDO.
        res = _resolution(a)
        brain = res.path if res.get("exists") else ""
        via = {brain_resolver.SOURCE_OVERRIDE: _t("doctor.via.override", "vía paths.local.json"),
               brain_resolver.SOURCE_LOADED: _t("doctor.via.loaded", "registrado en esta máquina (agents.local.json)"),
               }.get(res.source, _t("doctor.via.sibling", "carpeta hermana")
                     if brain_resolver.same_path(brain, sibling)
                     else _t("doctor.via.declared", "ruta declarada"))
        if brain:
            # El cerebro es una carpeta del usuario: git solo aplica si se
            # declaró transport git por máquina (paths.local.json).
            if dispatch.brain_transport(name, brain) != "git":
                out.append(f(OK, _t("doctor.phase_siblings.7", "cerebro \"{target}\"", target=target), via))
            elif _is_git(brain):
                out.append(f(OK, _t("doctor.phase_siblings.11", "cerebro \"{target}\"", target=target), _t("doctor.phase_siblings.12", "{via} · repo git (transport declarado)", via=via)))
            else:
                out.append(f(WARN, _t("doctor.phase_siblings.13", "\"{target}\": transport git declarado pero no es repo git", target=target),
                             _t("doctor.phase_siblings.14", "no recibirá actualizaciones por git pull"),
                             _t("doctor.phase_siblings.15", "re-clónalo con git o quita el override de transport en {v}", v=dispatch._paths_local())))
        else:
            sug = _suggestion_for(ctx, name, fix)
            detail = (_t("doctor.resolved_from", "resuelto ({src}) → ",
                         src=_source_label(res.source))
                      + f"{res.path or _t('doctor.no_path', '(sin ruta)')} · {res.get('error') or _t('doctor.not_exists', 'no existe')}")
            if sug and sug.get("found"):
                action = (_t("doctor.phase_siblings.16", "encontrado en {found} — repáralo: python agentsreg.py relocate {name} \"{found}\"  (o `workspace doctor` sin --check)", found=sug['found'], name=name))
            else:
                action = (_t("doctor.phase_siblings.17", "si moviste la carpeta, indica la ruta nueva en Agentes › cambiar ruta del cerebro (o en {v}  →  {{\"brains\": {{\"{name}\": \"/ruta\"}}}})", v=dispatch._paths_local(), name=name)
                          + (f" · candidatos: {', '.join(sug['options'])}" if sug and sug.get('options') else ""))
            out.append(f(FAIL, _t("doctor.phase_siblings.18", "falta el cerebro \"{target}\"", target=target), detail, action))
        # Punto ciego histórico: el override de paths.local.json GANA en runtime
        # aunque exista la carpeta hermana real. Si apunta a OTRO sitio, el
        # launcher/picker leen ahí y las sesiones del cerebro real "desaparecen".
        # WARN, no FAIL: un override a otra ruta REAL puede ser legítimo.
        try:
            runtime = a.get("brain", "")
            if (res.source == brain_resolver.SOURCE_OVERRIDE
                    and os.path.isdir(sibling) and runtime
                    and os.path.realpath(runtime) != os.path.realpath(sibling)):
                out.append(f(WARN,
                             _t("doctor.phase_siblings.19", "cerebro \"{target}\": paths.local.json lo redirige a otra ruta", target=target),
                             _t("doctor.phase_siblings.20", "runtime usa {runtime} pero existe la carpeta hermana real {sibling} — el launcher y el picker leen el override (las sesiones del cerebro real no aparecen)", runtime=runtime, sibling=sibling),
                             _t("doctor.phase_siblings.21", "apunta brains.{name} a \"{sibling}\" o elimina esa clave en {v}", name=name, sibling=sibling, v=dispatch._paths_local())))
        except Exception:
            pass
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 3 · Repos al día (detrás de origin → pull --ff-only)
# ══════════════════════════════════════════════════════════════════════════
def _repo_state(path, fetch=False):
    """('ok'|'behind'|'no-remote'|'no-upstream'|'offline', behind, ahead, dirty)

    W-F11: SIN `fetch` (default, el de --check) NO se consulta el remoto — la
    comparación es contra las refs LOCALES de origin (pueden estar viejas) y el
    caller lo dice explícitamente. `fetch=True` (modo reparar, o --remote) hace
    `git fetch` y entonces sí es una verificación remota."""
    rc, remotes, _ = _run(["git", "-C", path, "remote"], timeout=10)
    if rc != 0 or not remotes:
        return "no-remote", 0, 0, False
    rc_f = 0
    if fetch:
        rc_f, _, _ = _run(["git", "-C", path, "fetch", "--quiet"], timeout=40)
    rc, out, _ = _run(["git", "-C", path, "rev-list", "--count", "--left-right",
                       "HEAD...@{upstream}"], timeout=10)
    if rc != 0:
        return ("offline" if rc_f != 0 else "no-upstream"), 0, 0, False
    try:
        ahead, behind = (int(x) for x in out.split())
    except Exception:
        ahead, behind = 0, 0
    _, st, _ = _run(["git", "-C", path, "status", "--porcelain"], timeout=10)
    state = "behind" if behind > 0 else "ok"
    if rc_f != 0 and behind == 0:
        state = "offline"   # no se pudo consultar origin; lo local puede estar viejo
    return state, behind, ahead, bool(st)


# ══════════════════════════════════════════════════════════════════════════
#  FASE 3b · Versión y ajustes de actualización (updater.py · migrate.py)
# ══════════════════════════════════════════════════════════════════════════
# Lo que el usuario necesita saber tras una actualización: qué versión corre,
# si una actualización se revirtió sola (y por qué), si quedó algún ajuste
# registrado sin aplicar o fallido, y si hay cambios opcionales ofrecidos.
# Reparar = aplicar los ajustes "auto" pendientes (idempotentes, misma cola
# que el hub). Las ofertas NUNCA se aplican aquí: requieren el OK del usuario.
def phase_update_state(ctx, fix):
    out = []
    try:
        import updater
        import migrate
    except Exception as e:
        return [f(WARN, _t("doctor.phase_update_state.1", "no pude cargar el actualizador"), "%s: %s" % (type(e).__name__, e),
                  _help_hint())]
    cur = updater.current(ROOT)
    out.append(f(OK, "Workspace v%s" % (cur.get("version") or "?"),
                 (_t("doctor.phase_update_state.2", "código %s · rama %s") % (cur.get("short"), cur.get("branch")))
                 if cur.get("sha") else ""))
    h = updater.hold(HOME)
    if h:
        bad = h.get("bad_version") or h.get("bad", "")[:7]
        if h.get("kind") == "manual":
            out.append(f(WARN, _t("doctor.phase_update_state.3", "volviste a la versión anterior; la v%s queda en pausa") % bad,
                         "", _t("doctor.phase_update_state.4", "se actualiza sola cuando publiquemos una más nueva (o `workspace update --force` para volver a ella)")))
        else:
            out.append(f(WARN, _t("doctor.phase_update_state.5", "versión fijada: la v%s no arrancó en esta máquina") % bad,
                         (h.get("reason") or "")[:200],
                         _t("doctor.phase_update_state.6", "nada que hacer: se actualiza sola cuando publiquemos un arreglo (o `workspace update --force` para reintentar)")))
    st = migrate.status(HOME)
    if st["pending"] and fix:
        res = migrate.run_pending(HOME, force=True)       # reparar = reintentar
        for mid, title in res["applied"]:
            out.append(f(FIXED, _t("doctor.phase_update_state.7", "ajuste aplicado: %s") % title, mid))
        st = migrate.status(HOME)
    if st["failed"]:
        fl = st["failed"]
        out.append(f(FAIL, _t("doctor.phase_update_state.8", "un ajuste de la actualización falló: %s") % fl["id"],
                     (fl.get("error") or "")[:200],
                     _t("doctor.phase_update_state.9", "corrige la causa y corre `workspace migrate --run`; si no sabes cuál es, `workspace doctor --bundle` y envíanos el zip")))
    elif st["pending"]:
        out.append(f(WARN, _t("doctor.phase_update_state.10", "%d ajuste(s) de actualización pendiente(s)") % len(st["pending"]),
                     ", ".join(st["pending"][:5]), "workspace migrate --run"))
    else:
        out.append(f(OK, _t("doctor.phase_update_state.11", "ajustes de actualización al día"),
                     "%d aplicado(s)" % len(st["applied"])))
    for mid, title in migrate.offers_available(HOME):
        out.append(f(WARN, _t("doctor.phase_update_state.12", "cambio opcional disponible: %s") % title, mid,
                     migrate.offer_actions(mid)))
    return out


def _harness_update_finding(label):
    """Un hallazgo del doctor a partir de updater.update_harness (modo reparar).
    Respeta la elección del usuario: si apagó las actualizaciones automáticas
    o pidió solo aviso, el doctor COMPRUEBA y avisa, pero no instala (eso lo
    hace `workspace update`, que el usuario corre cuando quiere)."""
    try:
        import updater
        modo = updater.auto_mode()
        r = updater.update_harness(ROOT, mode="manual", home=HOME, apply=(modo == "auto"))
    except Exception as e:
        return f(WARN, _t("doctor.harness_update_finding.1", "{label}: no pude correr el actualizador", label=label), "%s: %s" % (type(e).__name__, e),
                 "workspace update")
    st = r.get("status")
    if st == updater.AVAILABLE:
        v = r.get("to_version")
        return f(WARN, _t("doctor.harness_update_finding.2", "{label}: hay una versión nueva", label=label) + (f" (v{v})" if v else ""),
                 "actualizaciones " + updater.auto_mode_text(modo),
                 _t("doctor.harness_update_finding.11", "workspace update (cuando quieras)"))
    if st == updater.UPDATED:
        return f(FIXED, f"{label} actualizado a v{r.get('to_version') or r.get('to', '')[:7]}",
                 _t("doctor.harness_update_finding.3", "%d cambio(s) · lo que sigue de este doctor usa la versión anterior: vuelve a correr `workspace doctor` para revisar con la nueva") % len(r.get("commits") or []))
    if st == updater.UPTODATE:
        return f(OK, _t("doctor.harness_update_finding.4", "{label} al día con origin", label=label), _t("doctor.harness_update_finding.5", "verificado contra el remoto"))
    if st == updater.HELD:
        return f(WARN, _t("doctor.harness_update_finding.6", "{label}: hay una versión más nueva en pausa en esta máquina", label=label),
                 _t("doctor.harness_update_finding.7", "ver fase 3b"), "")
    if st == updater.ROLLED_BACK:
        return f(WARN, _t("doctor.harness_update_finding.8", "{label}: la versión nueva no arrancó aquí; se quedó la anterior", label=label),
                 (r.get("detail") or "")[:200], _t("doctor.harness_update_finding.9", "nada que hacer: se reintenta cuando publiquemos un arreglo"))
    return f(WARN, _t("doctor.harness_update_finding.10", "{label}: no se actualizó", label=label), updater.reason_text(r.get("reason")),
             "workspace update")


def phase_updated(ctx, fix):
    out = []
    # W-F11: consultar el remoto es EXPLÍCITO — modo reparar (va a hacer pull)
    # o --remote/--fetch. --check a secas compara contra refs locales.
    remote = bool(fix or ctx.get("remote"))
    basis = _t("doctor.phase_updated.1", "verificado contra el remoto") if remote else \
        _t("doctor.phase_updated.2", "según refs locales — sin consultar remoto (usa --remote)")
    # WORKSPACE + SOLO los cerebros con transport git DECLARADO. Por defecto un
    # cerebro es una carpeta del usuario (no un repo que Workspace actualice):
    # no aparece aquí. Un cerebro in-repo se actualiza con WORKSPACE.
    repos = [("WORKSPACE", ROOT, "git")] + \
            [(_t("doctor.phase_updated.3", "cerebro {n}", n=n), b, "git")
             for n, b in _resolved_brains(ctx)
             if not _in_repo(b) and dispatch.brain_transport(n, b) == "git"]
    for label, path, transport in repos:
        if not _is_git(path):
            if path == ROOT:
                continue            # la fase 2 ya lo dice (sin git no hay updates)
            out.append(f(WARN, _t("doctor.phase_updated.6", "{label}: transport git pero no es repo git", label=label), path,
                         _t("doctor.phase_updated.7", "sin git no hay actualizaciones — re-clónalo con git o quita el override de transport en {v}", v=dispatch._paths_local())))
            continue
        if path == ROOT and fix:
            # El HARNESS jamás se jala "a pelo": pasa por el actualizador (comprueba
            # que la versión nueva arranca, vuelve sola si no, respeta una versión
            # fijada y aplica los ajustes registrados). Ver updater.py.
            out.append(_harness_update_finding(label))
            continue
        state, behind, ahead, dirty = _repo_state(path, fetch=remote)
        if path == ROOT and state == "behind":
            try:
                import updater
                h = updater.hold(HOME)
            except Exception:
                h = None
            if h:
                out.append(f(WARN, _t("doctor.phase_updated.8", "{label}: hay una versión más nueva en pausa en esta máquina", label=label),
                             _t("doctor.phase_updated.9", "ver fase 3b"), ""))
                continue
        extra = (_t("doctor.phase_updated.10", " · {ahead} commit(s) locales por subir", ahead=ahead) if ahead else "") + \
                (_t("doctor.phase_updated.11", " · cambios locales sin commitear") if dirty else "")
        if state == "ok":
            if remote:
                out.append(f(OK, _t("doctor.phase_updated.12", "{label} al día con origin", label=label),
                             " · ".join(x for x in (extra.strip(" ·"), basis) if x)))
            else:
                out.append(f(OK, _t("doctor.phase_updated.13", "{label} sin commits pendientes según refs locales", label=label),
                             " · ".join(x for x in (extra.strip(" ·"), basis) if x)))
        elif state == "no-remote":
            out.append(f(WARN, _t("doctor.phase_updated.14", "{label}: sin remote configurado", label=label), path,
                         _t("doctor.phase_updated.15", "agrega el remote (git remote add origin <url>) para recibir updates")))
        elif state == "no-upstream":
            # la rama ACTUAL (stable para el equipo, main para quien desarrolla) — nunca hardcodear main
            _, br, _ = _run(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
            out.append(f(WARN, _t("doctor.phase_updated.16", "{label}: la rama no rastrea a origin", label=label), path,
                         _t("doctor.phase_updated.17", "corre: git -C \"{path}\" branch --set-upstream-to=origin/{v}", path=path, v=br or "main")))
        elif state == "offline":
            out.append(f(WARN, _t("doctor.phase_updated.32", "{label}: no se pudo consultar origin", label=label),
                         _t("doctor.phase_updated.18", "¿offline o sin acceso al repo?"),
                         _t("doctor.phase_updated.19", "revisa tu conexión a internet y reintenta (`workspace update`)")))
        else:  # behind
            if not fix and path == ROOT:
                # una versión nueva disponible no es una falla: se instala con
                # el actualizador (selftest + vuelta atrás), nunca con git pull.
                out.append(f(WARN, _t("doctor.phase_updated.20", "{label}: {behind} commit(s) detrás de origin", label=label, behind=behind)
                                   + ("" if remote else _t("doctor.phase_updated.33", " (refs locales)")),
                             " · ".join(x for x in (extra.strip(" ·"), basis) if x),
                             _t("doctor.harness_update_finding.11", "workspace update (cuando quieras)")))
            elif not fix:
                out.append(f(FAIL, _t("doctor.phase_updated.20", "{label}: {behind} commit(s) detrás de origin", label=label, behind=behind)
                                   + ("" if remote else _t("doctor.phase_updated.33", " (refs locales)")),
                             " · ".join(x for x in (extra.strip(" ·"), basis) if x),
                             _t("doctor.phase_updated.21", "actualízalo: git -C \"{path}\" pull --ff-only  (o `workspace doctor`)", path=path)))
            elif dirty:
                out.append(f(WARN, _t("doctor.phase_updated.22", "{label}: {behind} detrás, pero hay cambios locales", label=label, behind=behind),
                             _t("doctor.phase_updated.23", "no jalo encima de trabajo sin commitear"),
                             _t("doctor.phase_updated.24", "commitea o guarda los cambios y corre: git -C \"{path}\" pull --ff-only", path=path)))
            else:
                rc, o, e = _run(["git", "-C", path, "pull", "--ff-only"], timeout=60)
                if rc == 0:
                    out.append(f(FIXED, f"{label} actualizado", f"{behind} commit(s) jalados"))
                else:
                    out.append(f(FAIL, _t("doctor.phase_updated.25", "{label}: el pull falló", label=label), (e or o).splitlines()[-1] if (e or o) else "",
                                 _t("doctor.phase_updated.26", "resuélvelo a mano: git -C \"{path}\" pull --ff-only", path=path)))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 4 · Cerebros resolubles (la lógica REAL de dispatch.resolve_brain)
# ══════════════════════════════════════════════════════════════════════════
def phase_brains(ctx, fix):
    out = []
    discovered = {}
    if not ctx["agents"]:
        return [f(OK, _t("doctor.no_agents", "aún no hay agentes"),
                  _t("doctor.no_agents.detail", "agrega uno desde el menú `workspace` (Agregar agente)"))]
    for a in ctx["agents"]:
        name = a["name"]
        # re-resuelve (fase 2 pudo cambiar algo) con el resolver CANÓNICO
        res = brain_resolver.resolve(name, a["cfg"], a.get("entry"))
        a["resolution"], a["brain"] = res, res.path
        src = _source_label(res.source)
        if res.get("exists") and res.get("readable"):
            out.append(f(OK, f"{name} → {a['brain']}", src))
            continue
        if res.get("exists"):
            out.append(f(FAIL, _t("doctor.phase_brains.1", "el cerebro de {name} no es legible", name=name), a["brain"],
                         _t("doctor.phase_brains.2", "revisa los permisos de la carpeta")))
            continue
        sug = _suggestion_for(ctx, name, fix)
        if not fix:
            if sug and sug.get("found"):
                act = (_t("doctor.phase_brains.3", "encontrado en {found} — repáralo: python agentsreg.py relocate {name} \"{found}\"  (o `workspace doctor`)", found=sug['found'], name=name))
            else:
                act = (_t("doctor.phase_brains.4", "si moviste la carpeta, indica la ruta nueva en Agentes › cambiar ruta del cerebro (o en {v})", v=dispatch._paths_local()))
            out.append(f(FAIL, _t("doctor.phase_brains.5", "dispatch no resuelve el cerebro de {name}", name=name),
                         f"{a['brain'] or _t('doctor.undefined', '(sin definir)')} · {src}", act))
            continue
        if sug and sug.get("found"):
            # reparación validada (marcador/nombre de carpeta) y atómica
            try:
                import agentsreg
                ok, err, dest = agentsreg.relocate(name, sug["found"])
            except Exception as e:
                ok, err, dest = False, str(e), ""
            if ok:
                a["brain"] = sug["found"]
                a["resolution"] = brain_resolver.resolve(name, a["cfg"], a.get("entry"))
                out.append(f(FIXED, f"{name} → {sug['found']}",
                             _t("doctor.phase_brains.15", "reubicado (antes {v}) · escrito en {dest}", v=res.path or _t('doctor.no_path', '(sin ruta)'), dest=dest)))
                continue
        # FIX: usar el detector del instalador (Obsidian, spots comunes, prompt)
        brain, persist = install.find_brain(name, a["cfg"])
        if brain and os.path.isdir(brain):
            a["brain"] = brain
            if persist:
                discovered[name] = brain
            out.append(f(FIXED, f"{name} → {brain}", _t("doctor.phase_brains.6", "detectado y registrado")))
        else:
            out.append(f(FAIL, _t("doctor.phase_brains.7", "no encontré el cerebro de {name}", name=name), "",
                         _t("doctor.phase_brains.8", "si moviste la carpeta, indica la ruta nueva en Agentes › cambiar ruta del cerebro (o en {v}  →  {{\"brains\": {{\"{name}\": \"/ruta\"}}}})", v=dispatch._paths_local(), name=name)))
    if discovered:
        pl = dispatch._paths_local()
        cur = _read_json(pl)
        cur.setdefault("brains", {}).update(discovered)
        install.write_json(pl, cur)
    # Sesiones (resume): la carpeta calculada (session_paths.session_dir, con
    # realpath) debe coincidir con donde Claude Code guarda DE VERDAD. Si no
    # coincide, `claude --resume` falla en silencio (arranca sesión nueva) —
    # típico cuando hay un symlink en la ruta del cerebro. El doctor no lo
    # repara solo: la acción depende de dónde está el symlink. SOLO aplica a
    # agentes con motor Claude Code (otros motores guardan sus sesiones a su
    # manera: el chequeo sería ruido).
    for a in ctx["agents"]:
        name, brain = a["name"], a["brain"]
        if not (brain and os.path.isdir(brain)):
            continue
        if _engine_of(a) != "claude-code":
            continue
        sdir = session_paths.session_dir(brain)
        if os.path.isdir(sdir):
            n = sum(1 for x in os.listdir(sdir) if x.endswith(".jsonl"))
            out.append(f(OK, _t("doctor.phase_brains.9", "[{name}] sesiones (resume) en el path esperado", name=name),
                         _t("doctor.phase_brains.10", "{n} sesión(es) · {v}", n=n, v=os.path.basename(sdir))))
            continue
        cands = session_paths.mismatch_candidates(brain)
        if cands:
            out.append(f(WARN, _t("doctor.phase_brains.11", "[{name}] resume no funcionará: el path calculado no coincide con el real", name=name),
                         _t("doctor.phase_brains.16", "calculado: {v} · Claude Code guarda en: {v2}", v=os.path.basename(sdir), v2=os.path.basename(cands[0])),
                         _t("doctor.phase_brains.12", "hay un symlink u otra codificación en la ruta del cerebro — revisa `ls -l` sobre los componentes de \"{brain}\", declara la ruta REAL (sin symlinks) en {v} y ", brain=brain, v=dispatch._paths_local())
                         + _help_hint()))
        else:
            out.append(f(OK, _t("doctor.phase_brains.13", "[{name}] sesiones (resume)", name=name),
                         _t("doctor.phase_brains.14", "sin sesiones aún — la carpeta se crea al primer arranque")))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 5 · Hooks cableados por cerebro (escribe SOLO el bloque `hooks`)
# ══════════════════════════════════════════════════════════════════════════
def _wired_events(groups):
    """Tokens de evento WORKSPACE cableados al runner en un bloque nativo. Con el
    runner shell-agnóstico (P0-1) el comando es `"PY" "RUNNER" <evento>`; el token
    es el ÚLTIMO campo (sin comillas, sin espacios). Solo cuentan los comandos del
    runner (`workspace_hook.py`) — un comando viejo (soft_hook_cmd con paths) o un
    `true` puesto por el socio no aporta token → se reporta como faltante y el doctor reescribe."""
    toks = set()
    for g in groups or []:
        for h in g.get("hooks", []):
            cmd = h.get("command", "") or ""
            if "workspace_hook.py" in cmd and cmd.split():
                toks.add(cmd.rsplit(None, 1)[-1])
    return toks


def _hooks_status(settings, setup, scripts=None):
    """(faltantes_criticos, faltantes_menores) validando contra el CONTRATO de
    eventos (N9 · events.py): cada listener de events.LISTENERS debe estar
    cableado en el bloque `hooks` de este cerebro — no hay lista propia aquí.
    La severidad la declara el contrato (CRITICAL → ✗, MINOR → ⚠ — regla:
    checks nuevos no convierten una instalación sana en fallo) y `requires`
    condiciona por `setup` del agente (p. ej. session_start/end solo si
    session_journal=true; con false es setup ligero y no se exige).

    P0-1 · detección por TOKEN, no por path de script: el wiring es shell-
    agnóstico (`"PY" "RUNNER" <evento>`), así que el blob ya no nombra scripts.
    Un listener está cableado si el TOKEN de su evento WORKSPACE aparece bajo SU
    evento nativo (el runner abanica a todos los listeners_for de ese token). El
    check sigue siendo POR EVENTO NATIVO: un cerebro con SessionStart cableado
    pero NO SessionEnd debe acusar los listeners de SessionEnd. `scripts` queda
    en la firma por compat (el dashboard ya NO se hornea — lo resuelve el runner)."""
    hooks_block = settings.get("hooks", {})
    if not isinstance(hooks_block, dict):
        hooks_block = {}
    crit, minor = [], []
    for l in events.LISTENERS:
        if events.gated(l, setup):     # Tema D: mismo gate que install.build_hooks
            continue
        native = events.native_event(l["event"])
        if native in (None, events.INTERNAL):
            continue           # el motor no expone el evento: nada que exigir
        if l["event"] in _wired_events(hooks_block.get(native)):
            continue
        label = "%s (%s)" % (l["script"][:-3], native)
        (crit if l["severity"] == events.CRITICAL else minor).append(label)
    return crit, minor


def _statusline_ok(settings, scripts):
    """True si el statusLine apunta al script esperado (en WORKSPACE) — o si el
    agente no declara statusline (nada que exigir)."""
    expected = (scripts or {}).get("statusline", "")
    if not expected:
        return True
    return expected in (settings.get("statusLine", {}) or {}).get("command", "")


def _stale_interpreters(settings):
    """SOLO Windows: intérpretes horneados en hooks/statusLine que ya no existen
    (bump/reinstall del Python de la Store) o que son el path VERSIONADO de la
    Store pudiendo usar el alias estable (install.win_python()). [] = todo bien.
    La cura es re-escribir hooks/statusLine — install.build_hooks ya hornea el
    intérprete estable."""
    cmds = []
    for groups in (settings.get("hooks", {}) or {}).values():
        for g in groups or []:
            for h in g.get("hooks", []):
                cmds.append(h.get("command", ""))
    cmds.append((settings.get("statusLine", {}) or {}).get("command", ""))
    stable = install.win_python()
    bad = set()
    for c in cmds:
        m = re.match(r'^"([^"]+\.exe)"', c or "", flags=re.I)
        if not m:
            continue
        p = m.group(1)
        if not os.path.exists(p):
            bad.add(p)
        elif install._store_versioned(p) and os.path.normcase(p) != os.path.normcase(stable):
            bad.add(p)
    return sorted(bad)


_CMD_TOKEN = re.compile(r'"([^"]*)"|(\S+)')


def _stale_runner_paths(settings):
    """(muertas, ajenas) — rutas horneadas en los hooks del runner que ya no
    sirven. `muertas`: el workspace_hook.py o el intérprete apuntan a algo que
    YA NO EXISTE (harness movido/borrado, Python desinstalado) → el hook truena
    en cada evento. `ajenas`: el runner existe pero es de OTRA copia de
    Workspace (corre código viejo). El token del evento por sí solo no basta:
    un hook con el token correcto y la ruta muerta se veía «cableado»."""
    want = os.path.normcase(os.path.realpath(install.RUNNER))
    dead, other = set(), set()
    for groups in (settings.get("hooks", {}) or {}).values():
        if not isinstance(groups, list):
            continue
        for g in groups:
            for h in (g or {}).get("hooks", []) if isinstance(g, dict) else []:
                cmd = (h or {}).get("command", "") if isinstance(h, dict) else ""
                if "workspace_hook.py" not in (cmd or ""):
                    continue
                toks = [a or b for a, b in _CMD_TOKEN.findall(cmd)]
                for i, tok in enumerate(toks):
                    if not tok.endswith("workspace_hook.py"):
                        continue
                    if not os.path.isfile(tok):
                        dead.add(tok)
                    elif os.path.normcase(os.path.realpath(tok)) != want:
                        other.add(tok)
                    interp = toks[i - 1] if i > 0 else ""
                    if os.path.isabs(interp) and not os.path.exists(interp):
                        dead.add(interp)
    return sorted(dead), sorted(other)


def phase_hooks(ctx, fix):
    out = []
    if not _resolved_brains(ctx):
        return [f(OK, _t("doctor.no_agents", "aún no hay agentes"),
                  _t("doctor.phase_hooks.2", "nada que cablear"))]
    for a in ctx["agents"]:
        name, brain = a["name"], a["brain"]
        if not (brain and os.path.isdir(brain)):
            continue
        setup = _setup(a["cfg"])
        scripts = install.expand(a["cfg"].get("scripts"), brain)
        sp = os.path.join(brain, ".claude", "settings.local.json")
        settings = _read_json(sp)
        crit, minor = _hooks_status(settings, setup, scripts)
        sline_ok = _statusline_ok(settings, scripts)
        # Windows: intérprete horneado roto (bump de la Store) o versionado-frágil
        py_bad = _stale_interpreters(settings) if IS_WIN else []
        # cualquier SO: runner/intérprete en una ruta muerta o de otra copia
        dead, other = _stale_runner_paths(settings)
        broken = (crit or minor or not sline_ok or py_bad or dead or other
                  or not os.path.exists(sp))
        # R3-F1 (read-guard): _read_json colapsa 'corrupto' y 'no existe' a {}.
        # Un settings TRUNCADO (crash a media escritura) se veía como vacío y el
        # fix lo 'reparaba' escribiendo solo hooks — descartando permissions/
        # env/mcpServers/model del socio EN SILENCIO. Reparación automática
        # sobre un archivo ilegible = destructiva → se ABORTA y se reporta.
        if install.json_corrupt(sp):
            out.append(f(FAIL, _t("doctor.phase_hooks.17", "[{name}] settings.local.json ilegible (JSON corrupto)", name=name),
                         _t("doctor.phase_hooks.4", "el doctor NO lo reescribe: pisarlo descartaría permissions/env/mcpServers en silencio"),
                         _t("doctor.phase_hooks.5", "revisa/respalda {sp} y bórralo o restáuralo; luego corre `python3 install.py`", sp=sp)))
        elif not broken:
            detail = ("skill_review + transcript_backup + memory_flush + session_start/end"
                      if setup["session_journal"]
                      else _t("doctor.phase_hooks.6", "skill_review + transcript_backup + memory_flush · setup ligero — sin journaling (por diseño)"))
            out.append(f(OK, _t("doctor.phase_hooks.18", "[{name}] hooks cableados", name=name), detail))
        elif not fix:
            falta = ", ".join(crit + minor +
                              ([_t("doctor.phase_hooks.24", "apuntan a una ruta que ya no existe: {v}", v=dead[0])] if dead else []) +
                              ([_t("doctor.phase_hooks.25", "apuntan a otra copia de Workspace: {v}", v=other[0])] if other else []) +
                              ([] if sline_ok else [_t("doctor.phase_hooks.22", "statusLine (ruta vieja)")]) +
                              ([_t("doctor.phase_hooks.23", "intérprete horneado roto/frágil: {v}", v=py_bad[0])] if py_bad else [])) \
                    or _t("doctor.phase_hooks.19", "settings.local.json no existe")
            st = FAIL if (crit or dead or not os.path.exists(sp)) else WARN
            out.append(f(st, _t("doctor.phase_hooks.7", "[{name}] hooks incompletos o con ruta vieja", name=name), _t("doctor.phase_hooks.8", "falta: {falta}", falta=falta),
                         _t("doctor.phase_hooks.9", "corre `workspace doctor` (reescribe SOLO hooks/statusLine")
                         + (_t("doctor.phase_hooks.10", " con el intérprete estable") if py_bad else "") + ")"))
        else:
            # build_hooks YA aplica el gate `requires` (tiene el cfg→setup): para
            # un agente con session_journal=false omite los listeners gated. El
            # runner además reaplica el gate en runtime → no hace falta un strip
            # posterior (y con runner_cmd no habría path de script que recortar).
            # P0-3: el RMW de `hooks` lo hace render_hooks_only (fuente única que
            # comparten install/doctor/repair) — muta `settings` sin escribir, el
            # write_json de abajo persiste hooks + statusLine en un solo paso.
            install.render_hooks_only(a["cfg"], brain, settings=settings)
            redo_sline = (not sline_ok or bool(py_bad)) and scripts.get("statusline")
            if redo_sline:   # ruta vieja pre-migración O intérprete frágil/roto → re-hornear
                settings["statusLine"] = {
                    "type": "command",
                    "command": install.hook_cmd(install.PY, scripts["statusline"], "--brain", brain),
                    "padding": 0, "refreshInterval": 60}
            install.write_json(sp, settings)
            out.append(f(FIXED, _t("doctor.phase_hooks.20", "[{name}] bloque hooks escrito", name=name),
                         "solo `hooks`" + ("" if not redo_sline else " + `statusLine`")
                         + _t("doctor.phase_hooks.11", " — el resto del archivo se respeta")))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 5c · MCPs por cerebro (materialización · connectors.PORTABILITY)
# ══════════════════════════════════════════════════════════════════════════
def _mcps_drift(cfg, brain, settings):
    """(drift, n_scope, channel, reason). Simula render_mcps_only sobre una
    COPIA y compara — cero divergencia con el materializador real. `n_scope` =
    MCP en scope para el agente; `channel`/`reason` = dispatch por motor."""
    channel, _ct, reason = install._mcp_projection(cfg)
    n_scope = len(install._mcps_for_agent(cfg.get("name", "")))
    if channel != "claude-code":
        return False, n_scope, channel, reason           # sin proyector real
    before = settings if isinstance(settings, dict) else {}
    trial = json.loads(json.dumps(before))               # deep-copy JSON-safe
    desired = install._mcps_for_agent(cfg.get("name", ""))
    install._project_mcps_claude_code(trial, desired)
    return trial != before, n_scope, channel, reason


def phase_mcps(ctx, fix):
    out = []
    if not _resolved_brains(ctx):
        return [f(OK, _t("doctor.no_agents", "aún no hay agentes"),
                  _t("doctor.phase_mcps.2", "nada que materializar"))]
    for a in ctx["agents"]:
        name, brain = a["name"], a["brain"]
        if not (brain and os.path.isdir(brain)):
            continue
        sp = os.path.join(brain, ".claude", "settings.local.json")
        # R3-F1 (read-guard, mismo que hooks): un settings TRUNCADO/corrupto NO
        # se reescribe — pisarlo descartaría permissions/env/mcpServers manuales
        # del socio EN SILENCIO. Reparación automática sobre archivo ilegible =
        # destructiva → se ABORTA y se reporta.
        if install.json_corrupt(sp):
            out.append(f(FAIL, _t("doctor.phase_mcps.12", "[{name}] settings.local.json ilegible (JSON corrupto)", name=name),
                         _t("doctor.phase_mcps.4", "el doctor NO materializa MCPs sobre un archivo corrupto: pisarlo descartaría permissions/env/mcpServers en silencio"),
                         _t("doctor.phase_mcps.5", "revisa/respalda {sp} y bórralo o restáuralo; luego corre `python3 install.py`", sp=sp)))
            continue
        settings = _read_json(sp)
        drift, n_scope, channel, reason = _mcps_drift(a["cfg"], brain, settings)
        if channel != "claude-code":
            # motor sin proyector real (codex/gemini/local/API): honesto, no ✗.
            # Solo se menciona si HAY MCP en scope que no se están enchufando.
            if n_scope:
                out.append(f(WARN, _t("doctor.phase_mcps.6", "[{name}] {n_scope} MCP(s) en scope sin materializar", name=name, n_scope=n_scope),
                             reason))
            continue
        if not drift:
            if n_scope:     # sin MCPs no hay nada que reportar (función opcional)
                out.append(f(OK, _t("doctor.phase_mcps.16", "[{name}] MCPs materializados", name=name),
                             f"{n_scope} server(s) en `mcpServers`"))
        elif not fix:
            out.append(f(WARN, _t("doctor.phase_mcps.13", "[{name}] MCPs desincronizados (store ↔ mcpServers)", name=name),
                         _t("doctor.phase_mcps.14", "{n_scope} server(s) en scope no reflejados en settings.local.json", n_scope=n_scope),
                         _t("doctor.phase_mcps.10", "corre `workspace doctor` (reescribe SOLO `mcpServers`)")))
        else:
            # P0-3: el RMW lo hace render_mcps_only (fuente única que comparten
            # doctor/CLI) — muta `settings` sin escribir; el write_json de abajo
            # persiste SOLO el bloque mcpServers, el resto del archivo se respeta.
            install.render_mcps_only(a["cfg"], brain, settings=settings)
            install.write_json(sp, settings)
            out.append(f(FIXED, _t("doctor.phase_mcps.15", "[{name}] bloque mcpServers materializado", name=name),
                         _t("doctor.phase_mcps.11", "{n_scope} server(s) — solo `mcpServers`, el resto del archivo se respeta", n_scope=n_scope)))
    if not out:
        out.append(f(OK, _t("doctor.phase_mcps.9", "sin MCPs configurados"), ""))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 6 · Launchers (workspace / zenith / atlas) — reusa install.py
# ══════════════════════════════════════════════════════════════════════════
def phase_launchers(ctx, fix):
    out = []
    names = ctx["agent_names"]
    if IS_WIN:
        ps1 = os.path.join(HOME, ".claude", "workspace-cmds.ps1")
        cur = ""
        try:
            cur = open(ps1, encoding="utf-8").read()
        except Exception:
            pass
        front = os.path.join(ROOT, "front.py")
        missing = [] if front in cur else ["workspace"]
        missing += [c for c in ["workspace"] + list(names)
                    if f"function {c} " not in cur and c not in missing]
        prof = install._ps_profile()
        prof_ok, prof_txt = False, ""
        try:
            prof_txt = open(prof, encoding="utf-8").read() if prof else ""
            prof_ok = bool(prof) and "# WORKSPACE-cmds" in prof_txt
        except Exception:
            pass
        # dot-source duplicado (línea legacy sin marcar + bloque marcado) → doble carga
        dup = sum(1 for ln in prof_txt.splitlines()
                  if "workspace-cmds.ps1" in ln and not ln.strip().startswith("#")) > 1
        # intérprete horneado en los launchers: debe EXISTIR y ser el ESTABLE
        # (el python versionado de la Store muere con cada bump → workspace/doctor varados)
        baked = set(re.findall(r'&\s+"([^"]+)"', cur))
        stale = sorted(p for p in baked if not os.path.exists(p))
        want = install.win_python()
        fragile = sorted(p for p in baked if os.path.exists(p) and install._store_versioned(p)
                         and os.path.normcase(p) != os.path.normcase(want))
        if not missing and prof_ok and not stale and not fragile and not dup:
            out.append(f(OK, _t("doctor.phase_launchers.15", "comandos PowerShell instalados"), ps1))
        elif fix:
            install.launchers_windows(names)
            out.append(f(FIXED, _t("doctor.phase_launchers.16", "comandos PowerShell reescritos"),
                         _t("doctor.phase_launchers.1", "{v} · abre una PowerShell nueva", v=', '.join(['workspace'] + list(names)))))
        elif missing or not prof_ok:
            out.append(f(FAIL, _t("doctor.phase_launchers.2", "launchers de Windows incompletos"),
                         _t("doctor.phase_launchers.3", "faltan: {v}", v=', '.join(missing) or 'dot-source en $PROFILE'),
                         _t("doctor.phase_launchers.4", "corre `workspace doctor` o `python install.py`")))
        else:
            det = []
            if stale:
                det.append(_t("doctor.phase_launchers.5", "intérprete horneado ya no existe: {v}", v=stale[0]))
            if fragile:
                det.append(_t("doctor.phase_launchers.6", "intérprete = python VERSIONADO de la Store (se rompe al actualizar)"))
            if dup:
                det.append(_t("doctor.phase_launchers.7", "workspace-cmds.ps1 dot-sourceado más de una vez en $PROFILE"))
            out.append(f(WARN, _t("doctor.phase_launchers.8", "launchers de Windows por endurecer"), " · ".join(det),
                         _t("doctor.phase_launchers.9", "corre `workspace doctor` — reescribe launchers con el intérprete estable ({want}) y deduplica el $PROFILE", want=want)))
        return out
    # Unix
    bindir = os.path.join(HOME, ".local", "bin")
    _hub = os.path.join(ROOT, "front.py")
    targets = [("workspace", _hub)] + \
              [(n, os.path.join(ROOT, "dispatch.py")) for n in names if n != "workspace"]
    broken = []
    for name, script in targets:
        p = os.path.join(bindir, name)
        body = ""
        try:
            body = open(p, encoding="utf-8").read()
        except Exception:
            pass
        if body and script in body and os.access(p, os.X_OK):
            out.append(f(OK, f"comando `{name}`", p))
        else:
            broken.append(name)
    if broken:
        if fix:
            install.install_launchers(names)
            out.append(f(FIXED, _t("doctor.phase_launchers.17", "launchers reinstalados"), ", ".join(broken)))
        else:
            out.append(f(FAIL, _t("doctor.phase_launchers.10", "launchers faltantes o apuntando a otra ruta"),
                         ", ".join(broken), _t("doctor.phase_launchers.11", "corre `workspace doctor` o `python3 install.py`")))
    if bindir not in os.environ.get("PATH", "").split(os.pathsep):
        out.append(f(WARN, _t("doctor.phase_launchers.12", "~/.local/bin no está en tu PATH"),
                     _t("doctor.phase_launchers.13", "los comandos existen pero la terminal no los ve"),
                     _t("doctor.phase_launchers.14", "ACCIÓN MANUAL: agrega a tu ~/.zshrc:  export PATH=\"$HOME/.local/bin:$PATH\"  y abre una terminal nueva")))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 7 · Greeter · retención de transcripts — reusa install.py
# ══════════════════════════════════════════════════════════════════════════
def phase_extras(ctx, fix):
    out = []
    # greeter (menú al abrir terminal): OPCIONAL. Nunca ⚠ y nunca se re-impone:
    # si no está, el usuario lo quitó (el instalador lo pone) y se respeta. Solo
    # se actualiza un bloque VIEJO que el usuario sí conserva.
    outdated = False
    if IS_WIN:
        prof = install._ps_profile()
        content = ""
        try:
            content = open(prof, encoding="utf-8").read() if prof else ""
        except Exception:
            pass
        has = install.WIN_GREETER_MARK in content              # versión actual
        outdated = (not has) and ("# WORKSPACE-greeter" in content)   # bloque viejo sin guards
        rc_label = _t("doctor.phase_extras.1", "$PROFILE de PowerShell")
    else:
        rc = os.path.join(HOME, ".zshrc")
        has = False
        try:
            has = install.GREETER_MARK in open(rc, encoding="utf-8").read()
        except Exception:
            pass
        rc_label = "~/.zshrc"
    if has:
        out.append(f(OK, _t("doctor.phase_extras.21", "greeter configurado"), _t("doctor.phase_extras.2", "menú WORKSPACE al abrir terminal ({rc_label})", rc_label=rc_label)))
    elif outdated and fix:
        install.install_greeter()
        out.append(f(FIXED, _t("doctor.phase_extras.3", "greeter al día"), rc_label))
    elif outdated:
        out.append(f(OK, _t("doctor.phase_extras.4", "greeter desactualizado (bloque viejo)"),
                     _t("doctor.phase_extras.5", "sin guard de interactividad/Windows Terminal ni reset de colores"),
                     _t("doctor.phase_extras.6", "corre `workspace doctor` (reemplaza el bloque por la versión actual)")))
    else:
        out.append(f(OK, _t("doctor.phase_extras.22", "greeter no configurado"),
                     _t("doctor.phase_extras.7", "opcional: sin menú al abrir terminal ({rc_label})", rc_label=rc_label)))
    # retención de transcripts (~/.claude/settings.json → cleanupPeriodDays):
    # Claude Code borra los .jsonl a los 30 días si no hay valor, y son la
    # materia prima de la memoria y del menú de sesiones. Sin valor → 365 días
    # (install.ensure_cleanup_days). Un valor que el usuario eligió JAMÁS se
    # toca ni se reprocha: nunca ⚠.
    gset = _read_json(os.path.join(HOME, ".claude", "settings.json"))
    cur = gset.get("cleanupPeriodDays") if isinstance(gset, dict) else None
    if cur is not None:
        out.append(f(OK, _t("doctor.phase_extras.17", "retención de transcripts"),
                     f"cleanupPeriodDays={int(cur) if isinstance(cur, (int, float)) and not isinstance(cur, bool) else cur}"))
    elif fix and install.ensure_cleanup_days():
        out.append(f(FIXED, _t("doctor.phase_extras.18", "retención de transcripts asegurada"),
                     f"cleanupPeriodDays={install.CLEANUP_DAYS} en ~/.claude/settings.json"))
    else:
        out.append(f(OK, _t("doctor.phase_extras.19", "retención de transcripts: la de Claude Code (30 días)"),
                     _t("doctor.phase_extras.25", "cleanupPeriodDays sin definir"),
                     _t("doctor.phase_extras.20", "`workspace doctor` la fija en {cleanup_days} días en ~/.claude/settings.json (no pisa nada más)", cleanup_days=install.CLEANUP_DAYS)))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 5d · Restos de la instalación anterior (anti-recurrencia)
# ══════════════════════════════════════════════════════════════════════════
# Tras el rename (2026-10; nombre viejo y sus rutas en legacy.py) quedaron
# vestigios PER-MÁQUINA que rompen el brand de un agente sin tocar el distro:
# (a) scripts de marca brain-resident de generación vieja que resuelven la raíz
# con la env / carpeta de escritorio / estado de la instalación anterior
# (legacy.DEAD_REFS: env/rutas muertas → menú/statusline truenan y filtran el
# nombre viejo); (b) entradas en agents.local.json con `brain` bajo el estado
# viejo (~/.claude/<viejo>, puntero stale); (c) la subcarpeta vieja de manifiesto
# sobrante en los cerebros (el harness lee SOLO `.workspace/` → config_engine).
# Reparación conservadora:
#   · (b) es config del HARNESS per-máquina → auto-repara en --fix (repunta a la
#     ruta equivalente bajo ~/.claude/workspace si existe; si no, WARN).
#   · (c) es metadata MUERTA del harness en el cerebro → auto-borra en --fix SOLO
#     si `.workspace/agent.json` ya existe (la fuente viva); si no, WARN.
#   · (a) toca scripts que PORTAN identidad (paleta/scope) → SOLO detecta+WARN;
#     regenerarlos desde templates/agent/workspace/brand/ es trabajo de dev, no
#     algo que el doctor deba inventar. Fail-soft total: jamás tumba el doctor.
_LEGACY_DEAD_REFS = legacy.DEAD_REFS


def _scan_brand_legacy(brain):
    """[nombres] de scripts en {brain}/brand/*.py que referencian env/rutas muertas
    de la instalación anterior (las que rompen la resolución de raíz). Solo
    lectura, fail-soft."""
    bdir = os.path.join(brain or "", "brand")
    hits = []
    try:
        names = sorted(n for n in os.listdir(bdir) if n.endswith(".py"))
    except OSError:
        return hits
    for n in names:
        try:
            with open(os.path.join(bdir, n), encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        except OSError:
            continue
        if any(ref in txt for ref in _LEGACY_DEAD_REFS):
            hits.append(n)
    return hits


def phase_legacy_residue(ctx, fix):
    out = []
    # (0) instalación anterior (launchers/perfil/hooks/estado/harness viejo):
    # SOLO sugerencia — la migración/retirada es un comando aparte, explícito y
    # recuperable (`workspace migrar-legado`); el doctor jamás la ejecuta.
    try:
        import migrate_legacy
        n, resumen = migrate_legacy.summary()
        if n:
            out.append(f(WARN, _t("doctor.phase_legacy_residue.1", "restos de la instalación anterior detectados (%d artefacto(s))") % n,
                         resumen,
                         _t("doctor.phase_legacy_residue.21", "%s (plan) → --apply → --retire (respaldo + --rollback)")
                         % migrate_legacy.CLI))
    except Exception:
        pass
    # (b) agents.local.json: punteros bajo el estado viejo (config del harness)
    dead_label = "~/.claude/" + legacy.STATE_SUBDIR
    dead = os.path.join(os.path.expanduser("~"), ".claude", legacy.STATE_SUBDIR) + os.sep
    live_root = _paths.state_dir()
    try:
        import agentsreg
        data = agentsreg.read_local()
        entries = data.get("agents", [])
        stale = [a for a in entries if isinstance(a, dict)
                 and str(a.get("brain", "")).startswith(dead)]
        if stale:
            repaired, unresolved = [], []
            for a in stale:
                old = str(a["brain"])
                cand = os.path.join(live_root, os.path.relpath(old, dead.rstrip(os.sep)))
                if fix and os.path.isdir(cand):
                    a["brain"] = cand
                    repaired.append("%s→%s" % (a.get("name", "?"), cand))
                else:
                    unresolved.append("%s (%s)" % (a.get("name", "?"), old))
            if repaired and agentsreg._write_local(data):
                out.append(f(FIXED, _t("doctor.phase_legacy_residue.2", "agents.local.json repuntado fuera del estado de la instalación anterior (%s)") % dead_label,
                             " · ".join(repaired)))
            for u in unresolved:
                out.append(f(WARN, _t("doctor.phase_legacy_residue.3", "agents.local.json apunta al estado de la instalación anterior (%s)") % dead_label, u,
                             _t("doctor.phase_legacy_residue.4", "repunta `brain` a la ubicación real bajo ~/.claude/workspace (o quita la entrada si ese agente ya no existe)")))
    except Exception as e:
        out.append(f(OK, _t("doctor.phase_legacy_residue.22", "agents.local.json no evaluable"),
                     _t("doctor.phase_legacy_residue.7", "%s: %s — señal omitida (fail-soft)") % (type(e).__name__, e)))
    # (a)/(c) por cerebro resuelto
    for name, brain in _resolved_brains(ctx):
        hits = _scan_brand_legacy(brain)
        if hits:
            out.append(f(WARN, _t("doctor.phase_legacy_residue.8", "[%s] scripts de brand/ con refs muertas de la instalación anterior") % name,
                         "brand/: " + ", ".join(hits),
                         _t("doctor.phase_legacy_residue.9", "regenera desde templates/agent/workspace/brand/ (usan WORKSPACE_ROOT y degradan con gracia); sustituye ")
                         + "/".join(_LEGACY_DEAD_REFS)))
        sub = legacy.BRAIN_SUBDIR + "/"
        old_dir = os.path.join(brain, legacy.BRAIN_SUBDIR)
        if os.path.isdir(old_dir):
            has_ws = os.path.isfile(os.path.join(brain, ".workspace", "agent.json"))
            if fix and has_ws:
                try:
                    shutil.rmtree(old_dir)
                    out.append(f(FIXED, _t("doctor.phase_legacy_residue.10", "[%s] %s sobrante eliminado (instalación anterior)")
                                 % (name, sub),
                                 _t("doctor.phase_legacy_residue.11", "el harness lee solo .workspace/ (metadata muerta)")))
                except OSError as e:
                    out.append(f(WARN, _t("doctor.phase_legacy_residue.23", "[%s] no se pudo borrar %s") % (name, sub), str(e),
                                 _t("doctor.phase_legacy_residue.12", "bórralo a mano: rm -rf \"%s\"") % old_dir))
            elif has_ws:
                out.append(f(WARN, _t("doctor.phase_legacy_residue.13", "[%s] %s sobrante en el cerebro (instalación anterior)")
                             % (name, sub),
                             _t("doctor.phase_legacy_residue.14", "el harness lee solo .workspace/ (está muerto)"),
                             _t("doctor.phase_legacy_residue.15", "workspace doctor --fix lo borra (o: rm -rf \"%s\")") % old_dir))
            else:
                out.append(f(WARN, _t("doctor.phase_legacy_residue.16", "[%s] %s sin .workspace/agent.json") % (name, sub),
                             _t("doctor.phase_legacy_residue.17", "NO borrar aún — puede tener la única definición"),
                             _t("doctor.phase_legacy_residue.18", "migra %sagent.json a .workspace/agent.json y luego borra %s")
                             % (sub, sub)))
    if not out:     # todo limpio: una sola línea, no una por agente
        out.append(f(OK, _t("doctor.phase_legacy_residue.24", "sin restos de la instalación anterior"), ""))
    return out


PHASES = [
    ("1 · Prerrequisitos (git · python · CLI del motor)", phase_prereqs),
    ("1b · Rutas en la nube (OneDrive · solo detección)", phase_redirected_paths),
    ("2 · Carpetas de los cerebros", phase_siblings),
    ("3 · Al día con origin", phase_updated),
    ("3b · Versión y ajustes de actualización", phase_update_state),
    ("4 · Cerebros de tus agentes · sesiones (resume)", phase_brains),
    ("5 · Hooks de cada agente", phase_hooks),
    ("5c · MCPs (solo si los usas)", phase_mcps),
    ("5d · Restos de la instalación anterior", phase_legacy_residue),
    ("6 · Comandos (workspace + agentes)", phase_launchers),
    ("7 · Greeter · retención de transcripts", phase_extras),
]

HEAD = {OK: "✓ ya conectada", FIXED: "✓ reparada", WARN: "⚠ atención", FAIL: "✗ falta"}
_HEAD_KEYS = {OK: "doctor.head.ok", FIXED: "doctor.head.fixed",
              WARN: "doctor.head.warn", FAIL: "doctor.head.fail"}


def _source_label(src):
    """Origen de la ruta de un cerebro (brain_resolver.SOURCE_LABELS = fuente
    es), en el idioma activo."""
    return _t("doctor.source." + str(src),
              brain_resolver.SOURCE_LABELS.get(src, src))


def head(st):
    """Encabezado de estado de una fase, en el idioma activo (HEAD = fuente es)."""
    return _t(_HEAD_KEYS[st], HEAD[st])


def phase_title(title, fn=None):
    """Título VISIBLE de una fase en el idioma activo. PHASES guarda el título
    español (fuente, estable para tests/consumidores); la clave sale del nombre
    de la función de la fase (`doctor.phase.<fn>`), así el idioma se resuelve
    en el punto de uso (el hub cambia de idioma en vivo)."""
    if fn is None:
        fn = next((f_ for t_, f_ in PHASES if t_ == title), None)
    if fn is None:
        return title
    return _t("doctor.phase." + fn.__name__, title)
HEADC = {OK: GRN, FIXED: C, WARN: YEL, FAIL: RED}


def _worst(finds):
    return max(finds, key=lambda x: RANK[x["status"]])["status"] if finds else OK


def _print_phase(title, finds, fix_mode):
    st = _worst(finds)
    print(_t("doctor.print_phase.1", "\n  {bo}{wh}FASE {title}{r}   {v}{v2}{r}", bo=BO, wh=WH, title=title, r=R, v=HEADC[st], v2=head(st)))
    if fix_mode and st == OK:
        return st   # fase ya conectada → se salta el detalle
    for x in finds:
        line = f"      {SYM[x['status']]} {x['label']}"
        if x["detail"]:
            line += f"  {DIM}— {x['detail']}{R}"
        print(line)
        if x["action"]:
            print(_t("doctor.print_phase.2", "        {yel}→ acción:{r} {action}", yel=YEL, r=R, action=x['action']))
    return st


# Funciones que el doctor de esta versión necesita de módulos que un proceso
# VIEJO pudo haber cargado antes de actualizarse. Si alguna falta, ese proceso
# trae código de la versión anterior en memoria.
_FRESH_ENV = "WORKSPACE_DOCTOR_FRESH"
_CANARIES = (("dispatch", "is_system_agent"),)


def _stale_process():
    """True si este doctor corre dentro de un proceso que importó módulos del
    harness ANTES de actualizarse. Pasa con `workspace update` de la 0.1.0: hace el
    pull y luego importa este doctor en su mismo proceso, donde `dispatch` y
    compañía siguen siendo los viejos → AttributeError a media revisión."""
    for mod, attr in _CANARIES:
        m = sys.modules.get(mod)
        if m is not None and not hasattr(m, attr):
            return True
    return False


def main(argv=None):
    args = list(argv) if argv is not None else sys.argv[1:]
    if os.environ.get(_FRESH_ENV) != "1" and _stale_process():
        # Relanzar en un proceso limpio: ahí todo el código es el de esta versión.
        env = dict(os.environ, **{_FRESH_ENV: "1"})
        return subprocess.call([sys.executable, os.path.join(ROOT, "front.py"), "doctor"] + args,
                               env=env)
    if "--bundle" in args:
        # ZIP de diagnóstico REDACTADO para soporte (lógica en diag_bundle.py).
        import diag_bundle
        return diag_bundle.main([a for a in args if a != "--bundle"])
    if "--tests" in args:
        # Suite N18 (tests/run.py): la red de edición del harness. Aditivo —
        # solo corre con el flag explícito; el doctor normal no la toca.
        runner = os.path.join(ROOT, "tests", "run.py")
        if not os.path.exists(runner):
            print(_t("doctor.main.1", "  {red}✗{r} no encuentro la suite: {runner}", red=RED, r=R, runner=runner))
            return 1
        rest = [a for a in args if a != "--tests"]
        return subprocess.call([sys.executable, runner] + rest)
    check_only = "--check" in args or "-c" in args
    # Guard anti-envenenamiento (espejo de install.global_writes_blocked): un
    # doctor con FIX corrido desde un git WORKTREE reescribiría shims/hooks
    # apuntando al árbol temporal → al borrarse, hub muerto. Desde un worktree
    # el doctor se DEGRADA a --check (solo lectura) y avisa fuerte.
    wt_downgraded = (not check_only and install.running_from_worktree(ROOT)
                     and os.environ.get(install.FORCE_ENV) != "1")
    if wt_downgraded:
        check_only = True
    mode = _t("doctor.main.2", "diagnóstico (--check, no modifica nada)") if check_only else _t("doctor.main.3", "revisar y reparar")
    osname = "Windows" if IS_WIN else ("Mac" if sys.platform == "darwin" else "Linux")
    print(f"\n  {BO}{C}WORKSPACE doctor{R}  {DIM}· {mode} · {osname} · {ROOT}{R}")
    if wt_downgraded:
        print(_t("doctor.main.4", "  {yel}⚠ Este WORKSPACE es un git WORKTREE — modo reparación desactivado (solo diagnóstico).{r}", yel=YEL, r=R))
        print(_t("doctor.main.5", "  {dim}Corre el doctor desde el checkout principal para reparar (override consciente: {force_env}=1).{r}", dim=DIM, force_env=install.FORCE_ENV, r=R))

    # NO auto-descubrimos cerebros aquí: el harness se distribuye a clientes y debe
    # quedar VACÍO salvo lo que el usuario conecte explícitamente (Agregar agente).
    # El doctor configura/repara lo YA registrado; descubrir es acción manual
    # (`agentsreg.py discover --register` o el menú Agregar agente → Descubrir).
    ctx = build_ctx()
    # W-F11: consultar el remoto es EXPLÍCITO en --check
    ctx["remote"] = ("--remote" in args or "--fetch" in args)
    if check_only:
        print(f"  {DIM}" + (_t("doctor.main.6", "verificación remota explícita (--remote): se hará git fetch")
                            if ctx["remote"] else
                            _t("doctor.main.7", "sin consultar remoto: repos comparados contra refs locales (añade --remote para git fetch)")) + f"{R}")
    results = []
    for title, fn in PHASES:
        try:
            finds = fn(ctx, fix=not check_only)
        except Exception as e:
            finds = [f(FAIL, _t("doctor.main.8", "error interno de la fase"), f"{type(e).__name__}: {e}",
                       _help_hint())]
        title = phase_title(title, fn)
        results.append((title, _print_phase(title, finds, not check_only), finds))

    # tabla de salud
    print(f"\n  {DIM}{'─' * 60}{R}")
    print(_t("doctor.main.9", "  {bo}{wh}Salud del harness{r}", bo=BO, wh=WH, r=R))
    for title, st, _ in results:
        print(f"    {SYM[st]}  {title}")
    n = {s: sum(1 for _, st, _ in results if st == s) for s in (OK, FIXED, WARN, FAIL)}
    print(_t("doctor.main.10", "\n  {dim}Fases:{r} {grn}{v} ✓{r} · {c}{v2} reparadas{r} · {yel}{v3} ⚠{r} · {red}{v4} ✗{r}", dim=DIM, r=R, grn=GRN, v=n[OK], c=C, v2=n[FIXED], yel=YEL, v3=n[WARN], red=RED, v4=n[FAIL]))
    if check_only and (n[WARN] or n[FAIL]):
        print(_t("doctor.main.11", "  {dim}Corre {r}{bo}workspace doctor{r}{dim} (sin --check) para reparar lo automático; lo manual viene marcado como → acción.{r}", dim=DIM, r=R, bo=BO))
    elif not check_only and n[FAIL]:
        print(_t("doctor.main.12", "  {dim}Quedan pendientes manuales (→ acción). Resuélvelos y vuelve a correr {r}{bo}workspace doctor{r}{dim} — es idempotente.{r}", dim=DIM, r=R, bo=BO))
    print()
    return 1 if n[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
