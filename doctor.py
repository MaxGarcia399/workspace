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

Fases (cada una: CHECK → ¿ya conectada? → saltar · si no → FIX o acción manual):
  1. Prerrequisitos       git · python 3.9+ · CLI de los MOTORES en uso
                          (claude/codex/gemini…) · gh auth             [solo instruye]
  2. Repos hermanos       WORKSPACE + cerebros con NOMBRE EXACTO        [solo instruye]
  3. Repos al día         detrás de origin → git pull --ff-only

TRANSPORT DE CEREBROS (política firme): los cerebros sincronizan EXCLUSIVAMENTE
por Obsidian Sync — es el DEFAULT (dispatch.brain_transport). Las fases 2 y 3
JAMÁS marcan ⚠/✗ de git en un cerebro obsidian-sync ("no es repo git", "detrás
de origin", "cambios sin commitear"… no aplican): reportan ✓ "sincroniza por
Obsidian Sync — git no aplica". git solo se valida si el socio lo declara por
máquina en paths.local.json → {"transport": {"<agente>": "git"}}. WORKSPACE (el
harness) sí va por git siempre.

CIERRE INTERACTIVO: si al terminar quedan hallazgos ⚠/✗ y hay TTY (y NO es
--check), el doctor ofrece enviarlos a Zenith — abre una sesión interactiva
normal (vía dispatch, como `workspace zenith`) sembrada con el reporte para
resolverlos conversando. Falla-suave siempre; opt-out: WORKSPACE_DOCTOR_NO_ZENITH=1.
  4. Cerebros resolubles  dispatch.resolve_brain por agente → paths.local.json
  5. Hooks por cerebro    settings.local.json → SOLO `hooks` (+ `statusLine` si
                          apunta a ruta vieja pre-migración brand→WORKSPACE)
  6. Launchers            workspace / zenith / atlas                    [reusa install.py]
  7. Greeter·socio·tema   menú al abrir terminal · socio.local · tema [reusa install.py]
  8. Cerebro              presupuesto de boot (chars por archivo/total) +
                          core blocks de MEMORY.md (N13, solo mide) +
                          drift de identidad (hash de BOOT/)          [WARN-only, jamás ✗]
  8b. Signos vitales      superficie HOT real (boot + session vía
                          STATE/hot-manifest.md) + junk de disco/sync
                          (node_modules/dist/caches/STATE-tmp/binarios)
                          + stubs de path-pollution                   [WARN-only,
                          SOLO LECTURA — la limpieza es brain_cleanup.py, opt-in]
  9. Secretos             secret-scan (N14) del working tree de cada cerebro
                          (claves API/tokens/private keys)            [WARN-only, jamás ✗;
                          solo-lectura SIEMPRE — escanear no repara]
 10. Skills por máquina   gating N11: skills con `requires:` (bins/env/os/
                          config) no satisfecho se reportan OCULTAS aquí
                          [informativo, jamás ⚠/✗ — ausencia ≠ problema;
                          solo-lectura SIEMPRE]
 11. Liveness             estado colgante (dash.dev.liveness): worktrees
                          huérfanos (>24h y sucios) [WARN-only, solo
                          detección; fail-soft — jamás tumba el doctor]

REGLA DURA: el doctor NUNCA escribe `permissions` en settings.local.json
(el clasificador de seguridad bloquea defaultMode dontAsk + Bash escrito por un
agente). Si falta el modo autónomo, se reporta como ACCIÓN MANUAL del socio.

SETUP POR AGENTE: cada agents/<x>/agent.json puede declarar qué requiere su
setup en un bloque opcional `"setup"`:
    "setup": { "session_journal": true|false, "autonomous": true|false }
  · session_journal — ¿usa el journaling por sesión (hooks session_start/end +
    socio.local)? Si es false, el doctor NO los exige (setup ligero, p. ej.
    Atlas hoy). skill_review es UNIVERSAL: siempre requerido, sin importar setup.
    transcript_backup (Y2b) también es universal, pero su falta es ⚠ (menor).
  · autonomous — ¿queremos modo autónomo (permissions dontAsk)? Si es false,
    el doctor ni lo menciona. Si es true y falta, es solo nota manual (⚠), nunca ✗.
  DEFAULT si el bloque no existe: session_journal=true, autonomous=true —
  conservador a propósito: un agente viejo sin bloque `setup` conserva la
  cobertura completa de chequeos (mejor una alarma de más que perder journaling
  sin enterarnos). Quien quiera setup ligero lo declara explícito.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Vive en git → se
auto-actualiza con `workspace update`.
"""
import os
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
import re
import sys
import json
import shutil
import hashlib
import subprocess

sys.dont_write_bytecode = True   # no generar __pycache__ (mantiene limpio el sync)
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import dispatch   # noqa: E402  (registry efectivo + transporte de cerebros)
import brain_resolver  # noqa: E402  (Z20 — resolución CANÓNICA de cerebros, la misma que dispatch)
import install    # noqa: E402  (fixers ya probados: launchers, greeter, tema, gitignore)
import events     # noqa: E402  (contrato de eventos N9 — la fase 5 valida contra él)
import session_paths  # noqa: E402  (única fuente del path de sesiones de Claude Code)
import secret_scan  # noqa: E402  (N14 — la fase 9 escanea cerebros con él)
import legacy     # noqa: E402  (literales de la instalación anterior — fase 5d)
import skill_meta   # noqa: E402  (N11 — la fase 10 reporta el gating por máquina)
import memory_blocks  # noqa: E402  (N13 — la fase 8 mide core blocks de MEMORY.md)
import pathguard   # noqa: E402  (P0-4 — detección de rutas redirigidas a OneDrive)
import brain_vitals  # noqa: E402  (fase 8b — HOT real por manifiesto + junk; SOLO lee)

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


# paleta dorada (consistente con front.py)
C, WH, DIM, GREY = _fg(221), _fg(230), _fg(136), _fg(242)
GRN, YEL, RED = _fg(114), _fg(178), _fg(203)
R, BO = "\033[0m", "\033[1m"

OK, FIXED, WARN, FAIL = "ok", "fixed", "warn", "fail"
SYM = {OK: f"{GRN}✓{R}", FIXED: f"{C}✓{R}", WARN: f"{YEL}⚠{R}", FAIL: f"{RED}✗{R}"}
RANK = {OK: 0, FIXED: 1, WARN: 2, FAIL: 3}

# URLs de clone conocidas por nombre de cerebro — el equipo las puebla en su
# config local (paths.local.json declara la ruta; el transport por defecto es
# Obsidian Sync). Vacío por defecto: el doctor cae al instructivo genérico.
CLONE_URLS = {}


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
    return os.path.isdir(os.path.join(path, ".git"))


def _in_repo(path):
    """True si `path` vive DENTRO de WORKSPACE (agente IN-REPO).

    Patron legitimo del harness: un agente cuyo cerebro viaja dentro del propio
    repo (`brain: "."` relativo a agents/<nombre>/) para que la app lo lleve
    consigo en cualquier maquina — p.ej. el motor background de Workspace. Esos
    agentes NO tienen ni deben tener vault hermano "<NOMBRE> - BRAIN", y su
    sincronizacion es la de WORKSPACE (git), no Obsidian Sync.
    """
    if not path:
        return False
    try:
        r, p = os.path.normcase(os.path.realpath(ROOT)),                os.path.normcase(os.path.realpath(path))
        return p == r or p.startswith(r + os.sep)
    except Exception:
        return False


def _is_dist_install():
    """True si este WORKSPACE es el repo de DISTRIBUCIÓN (externos): el remote origin
    apunta a `workspace-harness`. El concepto 'canal del equipo (stable)' y el branding
    interno (tema zenith) no aplican a un usuario externo."""
    rc, url, _ = _run(["git", "-C", ROOT, "remote", "get-url", "origin"], timeout=10)
    return rc == 0 and "workspace-harness" in (url or "").lower()


def _report_hint():
    """DEPLOY-5: en un install externo damos un mensaje genérico (sin marca del
    equipo, sin sentido para un cliente); en uno interno, el canal del equipo."""
    if _is_dist_install():
        return _t("doctor.report_hint.1", "revisa la salida y contacta a soporte con ella")
    return _t("doctor.report_hint.2", "repórtalo al equipo (o a tu agente principal) con esta salida")


# ══════════════════════════════════════════════════════════════════════════
#  Contexto compartido entre fases
# ══════════════════════════════════════════════════════════════════════════
def build_ctx():
    reg = dispatch.load_registry()
    agents = []
    names = []
    for a in reg.get("agents", []):
        try:
            cfg = dispatch.load_agent_cfg(a)
        except Exception:
            cfg = {}
        res = brain_resolver.resolve(a["name"], cfg, a)
        agents.append({"entry": a, "name": a["name"], "cfg": cfg,
                       "brain": res.path, "resolution": res})
        names += [a["name"]] + [x for x in a.get("aliases", []) if x != a["name"]]
    return {"agents": agents, "agent_names": list(dict.fromkeys(names)), "socio": None}


def _resolved_brains(ctx):
    """[(agent_name, brain_path)] solo de cerebros que existen en disco."""
    return [(a["name"], a["brain"]) for a in ctx["agents"]
            if a["brain"] and os.path.isdir(a["brain"])]


def _get_socio(ctx, fix):
    """Resuelve el socio activo: socio.local existente (por cerebro o
    per-máquina) > prompt (solo en modo fix)."""
    if ctx["socio"]:
        return ctx["socio"]
    candidates = [os.path.join(brain, ".claude", "socio.local")
                  for _, brain in _resolved_brains(ctx)]
    candidates.append(install.machine_socio_path())
    for path in candidates:
        s = ""
        try:
            s = open(path, encoding="utf-8").read().strip().lower()
        except Exception:
            pass
        if s and install.SOCIO_RE.match(s):       # trío O dueño externo (D3)
            ctx["socio"] = s
            return s
    if fix:
        ctx["socio"] = install.ask_socio()
    return ctx["socio"]


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


def _engines_in_use(ctx):
    """{engine: [agentes]} — el motor REAL por agente, con la precedencia de
    dispatch sin red: override per-máquina (settings) > agent.json > entry del
    registry > default claude-code. Fail-soft: si algo no se puede leer, cae
    a lo declarado."""
    use = {}
    for a in ctx["agents"]:
        eng = (a["cfg"].get("engine") or a["entry"].get("engine")
               or "claude-code")
        try:
            ov = dispatch._settings_agent_engine(a["name"])
            if ov:
                eng = ov
        except Exception:
            pass
        use.setdefault(eng, []).append(a["name"])
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
        out.append(f(OK, _t("doctor.phase_prereqs.5", "motores"), _t("doctor.phase_prereqs.6", "sin agentes registrados — el CLI del motor se valida al registrar el primero (Agregar agente)")))
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
    # gh (sesión de GitHub para clonar/pull de repos privados)
    gh = shutil.which("gh")
    if not gh:
        out.append(f(WARN, _t("doctor.phase_prereqs.13", "gh (GitHub CLI) no está instalado"),
                     _t("doctor.phase_prereqs.14", "git puede funcionar igual con credential manager"),
                     _t("doctor.phase_prereqs.15", "opcional pero recomendado: instala gh y corre `gh auth login` (con tu cuenta de GitHub)")))
    else:
        rc, _, err = _run(["gh", "auth", "status"], timeout=15)
        if rc == 0:
            out.append(f(OK, "gh auth", _t("doctor.phase_prereqs.16", "sesión de GitHub activa")))
        else:
            out.append(f(WARN, _t("doctor.phase_prereqs.17", "gh sin sesión de GitHub"), (err.splitlines() or [""])[0],
                         _t("doctor.phase_prereqs.18", "corre `gh auth login` y entra con tu cuenta de GitHub")))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 1b · Rutas redirigidas a la nube (OneDrive/known-folders) — SOLO DETECCIÓN
# ══════════════════════════════════════════════════════════════════════════
# P0-4: OneDrive (y la redirección de Desktop/Documents) sincroniza y bloquea
# los archivos del harness → locks, latencia, estado per-máquina pisado, y doble
# canal con Obsidian Sync (corrupción del vault). Si WORKSPACE o un cerebro vive ahí
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
                         _t("doctor.phase_redirected_paths.5", "muévelo a C:\\{up} - BRAIN (fuera de OneDrive) y vuelve a declararlo en {v}  →  {{\"brains\": {{\"{name}\": \"C:\\\\{up} - BRAIN\"}}}}. OneDrive + Obsidian Sync sobre el mismo vault = doble canal (corrupción); además los locks/latencia de la nube rompen sesiones (resume) y el estado per-máquina (settings.local.json)", up=up, v=dispatch._paths_local(), name=name)))
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
#  FASE 2 · Repos hermanos con nombres EXACTOS (solo instruye: no clona)
# ══════════════════════════════════════════════════════════════════════════
def phase_siblings(ctx, fix):
    out = []
    parent = os.path.dirname(ROOT)
    if _is_git(ROOT):
        out.append(f(OK, _t("doctor.phase_siblings.1", "WORKSPACE es repo git"), ROOT))
    else:
        out.append(f(WARN, _t("doctor.phase_siblings.2", "WORKSPACE no es repo git"), _t("doctor.phase_siblings.3", "instalación por sync — sin auto-update"),
                     _t("doctor.phase_siblings.4", "clona el repo del harness con git (carpeta \"WORKSPACE\" en {parent}) para recibir actualizaciones", parent=parent)))
    for a in ctx["agents"]:
        name = a["name"]
        # IN-REPO primero: su cerebro vive dentro de WORKSPACE y exigirle carpeta
        # hermana era un FALSO ROJO (hallazgo 2026-09-21, agente `doctor`).
        if _in_repo(a.get("brain")) and os.path.isdir(a.get("brain") or ""):
            out.append(f(OK, _t("doctor.phase_siblings.5", "cerebro \"{name}\" in-repo", name=name),
                         _t("doctor.phase_siblings.6", "vive dentro del harness (viaja con la app) · sin vault hermano por diseño")))
            continue
        raw = a["cfg"].get("brain", "")
        target = os.path.basename(os.path.normpath(raw)) if raw else name
        sibling = os.path.join(parent, target)
        # W-F02: el estado lo decide el resolver CANÓNICO (el mismo del launcher),
        # no la «carpeta hermana». Un cerebro registrado por ruta absoluta fuera
        # del repo (C:\TURING - BRAIN con el harness en C:\dev\…) es VÁLIDO.
        res = _resolution(a)
        brain = res.path if res.get("exists") else ""
        via = {brain_resolver.SOURCE_OVERRIDE: _t("doctor.via.override", "vía paths.local.json"),
               brain_resolver.SOURCE_LOADED: _t("doctor.via.loaded", "registrado en esta máquina (agents.local.json)"),
               }.get(res.source, _t("doctor.via.sibling", "carpeta hermana")
                     if brain_resolver.same_path(brain, sibling)
                     else _t("doctor.via.declared", "ruta declarada"))
        if brain:
            # transporte del cerebro: obsidian-sync (DEFAULT, canal de primera
            # clase — git no aplica) o git (solo si el socio lo declara).
            transport = dispatch.brain_transport(name, brain)
            if transport == "obsidian-sync":
                out.append(f(OK, _t("doctor.phase_siblings.7", "cerebro \"{target}\"", target=target),
                             _t("doctor.phase_siblings.8", "{via} · sincroniza por Obsidian Sync — git no aplica", via=via)))
            elif _is_git(brain) and dispatch.obsidian_sync_enabled(brain):
                # transport git DECLARADO + Sync activo = DOS canales sobre el
                # mismo vault → corrupción segura (solo aplica con override git)
                out.append(f(FAIL, _t("doctor.phase_siblings.9", "\"{target}\": repo git Y Obsidian Sync a la vez", target=target), brain,
                             _t("doctor.phase_siblings.10", "un solo canal por vault: apaga Obsidian Sync en este vault o quita el override de transport git en {v}", v=dispatch._paths_local())))
            elif _is_git(brain):
                out.append(f(OK, _t("doctor.phase_siblings.11", "cerebro \"{target}\"", target=target), _t("doctor.phase_siblings.12", "{via} · repo git (transport declarado)", via=via)))
            else:
                out.append(f(WARN, _t("doctor.phase_siblings.13", "\"{target}\": transport git declarado pero no es repo git", target=target),
                             _t("doctor.phase_siblings.14", "no recibirá actualizaciones por git pull"),
                             _t("doctor.phase_siblings.15", "re-clónalo con git o quita el override de transport en {v} para volver al default (Obsidian Sync)", v=dispatch._paths_local())))
        else:
            url = CLONE_URLS.get(target) or _t("doctor.clone_url_placeholder", "<URL del repo de tu cerebro>")
            sug = _suggestion_for(ctx, name, fix)
            detail = (_t("doctor.resolved_from", "resuelto ({src}) → ",
                         src=_source_label(res.source))
                      + f"{res.path or _t('doctor.no_path', '(sin ruta)')} · {res.get('error') or _t('doctor.not_exists', 'no existe')}")
            if sug and sug.get("found"):
                action = (_t("doctor.phase_siblings.16", "encontrado en {found} — repáralo: python agentsreg.py relocate {name} \"{found}\"  (o `workspace doctor` sin --check)", found=sug['found'], name=name))
            else:
                action = (_t("doctor.phase_siblings.17", "instala el vault por Obsidian Sync (canal por defecto de los cerebros) junto a WORKSPACE, o clónalo:  git clone {url} \"{target}\"  (en {parent}) — o si ya vive en otra ruta, decláralo en {v}  →  {{\"brains\": {{\"{name}\": \"/ruta\"}}}}", url=url, target=target, parent=parent, v=dispatch._paths_local(), name=name)
                          + (f" · candidatos: {', '.join(sug['options'])}" if sug else ""))
            out.append(f(FAIL, _t("doctor.phase_siblings.18", "falta el cerebro \"{target}\"", target=target), detail, action))
        # Punto ciego histórico: el override de paths.local.json GANA en runtime
        # (dispatch.resolve_brain lo prefiere SOBRE la carpeta hermana), aunque
        # exista la hermana real. Si el override apunta a OTRO sitio que la
        # hermana existente, el launcher/picker leen ahí — y las sesiones del
        # cerebro real "desaparecen" (bug observado: paths.local quedó con rutas
        # /tmp de una prueba). Doctor antes no lo veía porque elegía la hermana
        # primero. WARN, no FAIL: un override a otra ruta REAL puede ser legítimo.
        try:
            runtime = a.get("brain", "")   # = resolve_brain (paths.local primero)
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
                  _report_hint())]
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
                     "workspace migrate --offer %s" % mid))
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
    repos = [("WORKSPACE", ROOT, "git")] + \
            [(_t("doctor.phase_updated.3", "cerebro {n}", n=n), b, dispatch.brain_transport(n, b)) for n, b in _resolved_brains(ctx)]
    for label, path, transport in repos:
        if path != ROOT and _in_repo(path):
            # cerebro in-repo: ya se actualiza con WORKSPACE (misma linea de arriba).
            # Decir "Obsidian Sync" aqui seria mentira.
            out.append(f(OK, _t("doctor.phase_updated.4", "{label}: viaja dentro de WORKSPACE — se actualiza con el harness", label=label), path))
            continue
        if transport == "obsidian-sync":
            # canal sano y DEFAULT de los cerebros: Obsidian Sync se encarga
            # (sync en segundos) — git no aplica, aunque exista un .git vestigial.
            out.append(f(OK, _t("doctor.phase_updated.5", "{label}: sincroniza por Obsidian Sync — git no aplica", label=label), path))
            continue
        if not _is_git(path):
            out.append(f(WARN, _t("doctor.phase_updated.6", "{label}: transport git pero no es repo git", label=label), path,
                         _t("doctor.phase_updated.7", "sin git no hay actualizaciones automáticas — re-clónalo con git o, si es un cerebro, quita el override de transport en {v} para volver al default (Obsidian Sync)", v=dispatch._paths_local())))
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
                         _t("doctor.phase_updated.19", "verifica conexión / credenciales (gh auth login) y reintenta")))
        else:  # behind
            if not fix:
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
    # canal del equipo: los socios (no-max) viven en `stable` con upstream rastreado.
    # ⚠ informativo a propósito (una máquina puede estar en una rama de trabajo adrede).
    socio = _get_socio(ctx, fix=False)
    if socio and socio != "max" and _is_git(ROOT) and not _is_dist_install():
        _, br, _ = _run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
        rc_u, _, _ = _run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "@{upstream}"], timeout=10)
        if br == "stable" and rc_u == 0:
            out.append(f(OK, _t("doctor.phase_updated.27", "canal del equipo"), _t("doctor.phase_updated.34", "WORKSPACE en `stable` · upstream rastreado")))
        else:
            why = []
            if br != "stable":
                why.append(_t("doctor.phase_updated.28", "rama actual: {v} (el equipo vive en stable)", v=br or '?'))
            if rc_u != 0:
                why.append(_t("doctor.phase_updated.29", "la rama no rastrea a origin"))
            out.append(f(WARN, _t("doctor.phase_updated.30", "WORKSPACE fuera del canal del equipo"), " · ".join(why),
                         _t("doctor.phase_updated.31", "para volver al canal: git -C \"{root}\" checkout stable — o si la rama es intencional, fija upstream: git -C \"{root}\" branch --set-upstream-to=origin/{v}", root=ROOT, v=br or "stable")))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 4 · Cerebros resolubles (la lógica REAL de dispatch.resolve_brain)
# ══════════════════════════════════════════════════════════════════════════
def phase_brains(ctx, fix):
    out = []
    discovered = {}
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
                act = (_t("doctor.phase_brains.4", "clona la carpeta con el nombre exacto (fase 2) o declárala en {v}", v=dispatch._paths_local()))
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
                         _t("doctor.phase_brains.8", "clónalo (fase 2) o declara la ruta en {v}  →  {{\"brains\": {{\"{name}\": \"/ruta\"}}}}", v=dispatch._paths_local(), name=name)))
    if discovered:
        pl = dispatch._paths_local()
        cur = _read_json(pl)
        cur.setdefault("brains", {}).update(discovered)
        install.write_json(pl, cur)
    # Sesiones (resume): la carpeta calculada (session_paths.session_dir, con
    # realpath) debe coincidir con donde Claude Code guarda DE VERDAD. Si no
    # coincide, `claude --resume` falla en silencio (arranca sesión nueva) —
    # típico cuando hay un symlink en la ruta del cerebro. Esto lo vuelve
    # detectable en cualquier máquina. El doctor no lo repara solo: la acción
    # depende de dónde está el symlink.
    for a in ctx["agents"]:
        name, brain = a["name"], a["brain"]
        if not (brain and os.path.isdir(brain)):
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
                         + _report_hint()))
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


def phase_hooks(ctx, fix):
    out = []
    if not _resolved_brains(ctx):
        return [f(WARN, _t("doctor.phase_hooks.1", "sin cerebros resueltos"), _t("doctor.phase_hooks.2", "nada que cablear"), _t("doctor.phase_hooks.3", "resuelve la fase 4 primero"))]
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
        broken = crit or minor or not sline_ok or py_bad or not os.path.exists(sp)
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
                              ([] if sline_ok else [_t("doctor.phase_hooks.22", "statusLine (ruta vieja)")]) +
                              ([_t("doctor.phase_hooks.23", "intérprete horneado roto/frágil: {v}", v=py_bad[0])] if py_bad else [])) \
                    or _t("doctor.phase_hooks.19", "settings.local.json no existe")
            st = FAIL if (crit or not os.path.exists(sp)) else WARN
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
        # gitignore del cerebro (estado per-máquina nunca se sincroniza)
        gi = os.path.join(brain, ".gitignore")
        gi_cur = ""
        try:
            gi_cur = open(gi, encoding="utf-8").read()
        except Exception:
            pass
        missing_gi = [ln for ln in (".claude/settings.local.json", ".claude/socio.local")
                      if ln not in gi_cur]
        if missing_gi:
            if fix:
                install.ensure_gitignore(brain, install.GITIGNORE_LINES)
                out.append(f(FIXED, _t("doctor.phase_hooks.21", "[{name}] .gitignore completado", name=name), ", ".join(missing_gi)))
            else:
                out.append(f(WARN, _t("doctor.phase_hooks.12", "[{name}] .gitignore no excluye estado per-máquina", name=name),
                             ", ".join(missing_gi), _t("doctor.phase_hooks.13", "corre `workspace doctor`")))
        # modo autónomo: el doctor NO lo escribe (hard-block del clasificador) → manual.
        # Solo se menciona si el agente lo quiere (setup.autonomous) y SIEMPRE como
        # acción manual del socio (⚠ informativo), nunca ✗.
        if setup["autonomous"] and settings and \
                settings.get("permissions", {}).get("defaultMode") != "dontAsk":
            out.append(f(WARN, _t("doctor.phase_hooks.14", "[{name}] modo autónomo no activo (permissions)", name=name),
                         _t("doctor.phase_hooks.15", "el doctor no escribe `permissions` (bloqueado por seguridad)"),
                         _t("doctor.phase_hooks.16", "ACCIÓN MANUAL: copia el bloque \"permissions\" desde el settings.local.json de un cerebro ya configurado (p. ej. MI - BRAIN) a {sp} — o corre `python3 install.py` tú mismo", sp=sp)))
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
        return [f(WARN, _t("doctor.phase_mcps.1", "sin cerebros resueltos"), _t("doctor.phase_mcps.2", "nada que materializar"),
                  _t("doctor.phase_mcps.3", "resuelve la fase 4 primero"))]
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
            else:
                out.append(f(OK, _t("doctor.phase_mcps.7", "[{name}] sin MCPs para este motor", name=name),
                             reason or channel or _t("doctor.phase_mcps.8", "motor sin canal MCP")))
            continue
        if not drift:
            out.append(f(OK, _t("doctor.phase_mcps.16", "[{name}] MCPs materializados", name=name),
                         f"{n_scope} server(s) en `mcpServers`" if n_scope
                         else _t("doctor.phase_mcps.9", "sin MCPs en scope")))
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
        # `workspace` es el comando; `workspace` el alias — los dos deben estar.
        missing += [c for c in ("workspace", "workspace")
                    if f"function {c} " not in cur]
        missing += [n for n in names if f"function {n} " not in cur]
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
                         _t("doctor.phase_launchers.1", "{v} · abre una PowerShell nueva", v=', '.join(['workspace', 'workspace'] + names))))
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
    targets = [("workspace", _hub), ("workspace", _hub)] + \
              [(n, os.path.join(ROOT, "dispatch.py")) for n in names]
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
#  FASE 7 · Greeter · socio.local · tema — reusa install.py
# ══════════════════════════════════════════════════════════════════════════
def phase_extras(ctx, fix):
    out = []
    # greeter (menú al abrir terminal)
    outdated = False
    if IS_WIN:
        prof = install._ps_profile()
        content = ""
        try:
            content = open(prof, encoding="utf-8").read() if prof else ""
        except Exception:
            pass
        has = install.WIN_GREETER_MARK in content              # versión actual (v2)
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
    elif fix:
        install.install_greeter()
        out.append(f(FIXED, _t("doctor.phase_extras.3", "greeter al día"), rc_label))
    elif outdated:
        out.append(f(WARN, _t("doctor.phase_extras.4", "greeter desactualizado (bloque viejo)"),
                     _t("doctor.phase_extras.5", "sin guard de interactividad/Windows Terminal ni reset de colores"),
                     _t("doctor.phase_extras.6", "corre `workspace doctor` (reemplaza el bloque por la versión actual)")))
    else:
        out.append(f(WARN, _t("doctor.phase_extras.22", "greeter no configurado"), _t("doctor.phase_extras.7", "sin menú al abrir terminal ({rc_label})", rc_label=rc_label),
                     _t("doctor.phase_extras.8", "corre `workspace doctor` (es opt-out: WORKSPACE_NO_GREETER=1)")))
    # socio.local por cerebro — solo requerido si el agente usa session_journal
    # (el socio alimenta la ruta del journal). Setup ligero → nota neutra, sin ✗.
    socio = _get_socio(ctx, fix=False)
    setups = {a["name"]: _setup(a["cfg"]) for a in ctx["agents"]}
    for name, brain in _resolved_brains(ctx):
        journal = setups.get(name, SETUP_DEFAULTS)["session_journal"]
        sl = os.path.join(brain, ".claude", "socio.local")
        cur = ""
        try:
            cur = open(sl, encoding="utf-8").read().strip().lower()
        except Exception:
            pass
        if cur and install.SOCIO_RE.match(cur):       # trío O dueño externo (D3)
            out.append(f(OK, f"[{name}] socio.local", cur))
        elif not journal:
            out.append(f(OK, _t("doctor.phase_extras.23", "[{name}] socio.local no requerido", name=name),
                         _t("doctor.phase_extras.9", "setup ligero · sin journaling (por diseño)")))
        elif fix:
            s = _get_socio(ctx, fix=True) or "max"
            install.write_text(sl, s)
            out.append(f(FIXED, _t("doctor.phase_extras.24", "[{name}] socio.local escrito", name=name), s))
        else:
            # ⚠ (no ✗): lo resuelve `workspace doctor` (fix) solo → es "por terminar", no una falla.
            out.append(f(WARN, _t("doctor.phase_extras.10", "[{name}] socio.local por configurar", name=name), cur or _t("doctor.missing_paren", "(no existe)"),
                         _t("doctor.phase_extras.11", "corre `workspace doctor` (preguntará quién eres)")
                         + (_t("doctor.phase_extras.12", " — detectado en otro cerebro: {socio}", socio=socio) if socio else "")))
    # socio.local per-máquina (~/.claude/workspace/) — identidad del CHAT cuando
    # no hay cerebro activo (TUI abierta desde el menú workspace, cwd=$HOME).
    # Sin él, chat.self_ids puede caer a $USER ("maxgarcia") en instalaciones
    # sin cerebro de equipo resoluble (QA ALTA-1).
    msl = install.machine_socio_path()
    cur = ""
    try:
        cur = open(msl, encoding="utf-8").read().strip().lower()
    except Exception:
        pass
    if cur and install.SOCIO_RE.match(cur):       # trío O dueño externo (D3)
        out.append(f(OK, _t("doctor.phase_extras.13", "socio.local per-máquina (chat)"), cur))
    elif fix:
        s = _get_socio(ctx, fix=True) or "max"
        install.write_machine_socio(s)
        out.append(f(FIXED, _t("doctor.phase_extras.14", "socio.local per-máquina escrito"), s))
    else:
        out.append(f(WARN, _t("doctor.phase_extras.15", "socio.local per-máquina por configurar"),
                     cur or _t("doctor.missing_paren", "(no existe)"),
                     _t("doctor.phase_extras.16", "corre `workspace doctor` — sin él, el chat del menú puede firmar como $USER en vez del socio")))
    # Tema in-app: ahora es POR-AGENTE (settings.local.json del cerebro, lo instala
    # configure_brain desde themes-cc/<agente>.json) — ya NO se hornea un tema global
    # 'zenith' en ~/.claude/settings.json (DEPLOY-1 + SEC-05: no tocar el settings
    # global del usuario). Por eso aquí no se repara ningún tema global.
    # retención de transcripts (runbook windows-support §4.5 — TODA máquina, Mac incluido):
    # Claude Code borra los .jsonl crudos a los 30 días por default; son materia
    # prima de la memoria → cleanupPeriodDays ≥ 3650 en ~/.claude/settings.json.
    gset = _read_json(os.path.join(HOME, ".claude", "settings.json"))
    cur = gset.get("cleanupPeriodDays")
    if isinstance(cur, (int, float)) and not isinstance(cur, bool) and cur >= install.CLEANUP_DAYS:
        out.append(f(OK, _t("doctor.phase_extras.17", "retención de transcripts"), f"cleanupPeriodDays={int(cur)}"))
    elif fix:
        install.ensure_cleanup_days()
        out.append(f(FIXED, _t("doctor.phase_extras.18", "retención de transcripts asegurada"),
                     f"cleanupPeriodDays={install.CLEANUP_DAYS} en ~/.claude/settings.json"))
    else:
        out.append(f(WARN, _t("doctor.phase_extras.19", "transcripts se borran a los 30 días (default)"),
                     _t("doctor.phase_extras.25", "cleanupPeriodDays actual: {v}", v=cur if cur is not None else _t('doctor.undefined', '(sin definir)')),
                     _t("doctor.phase_extras.20", "corre `workspace doctor` — fija cleanupPeriodDays={cleanup_days} en ~/.claude/settings.json (no pisa nada más)", cleanup_days=install.CLEANUP_DAYS)))
    # App de escritorio: YA NO se verifica ni se crea aquí (terminal-only,
    # decisión de producto 2026-10). Antes el doctor en fix re-creaba
    # ~/Desktop/WORKSPACE.app en cada `workspace update` — si el socio la borraba,
    # el update se la regresaba. Quien la quiera la pide explícito:
    # `python3 install.py --desktop-app` o `bash dist/make-app.sh` (dev panel).
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 8 · Cerebro: presupuesto de boot + drift de identidad (WARN-only)
# ══════════════════════════════════════════════════════════════════════════
# Y8 (OpenClaw R3): el boot se PAGA en cada arranque — medir cuántos chars
# carga de verdad (CLAUDE.md + BOOT/ numerados + STATE de arranque) y avisar
# cuando un archivo o el total engordan. Sin medición continua, la dieta Y14
# se re-engorda en silencio; y es el sustrato de N17 (perfil `lite` ≤4k).
# N13 (MemGPT core blocks): mide los bloques acotados de STATE/MEMORY.md
# (memory_blocks.py, read-only) y avisa cuál excede su cota suave — el
# archivado del excedente es humano/Atlas-con-gate; NADA escribe MEMORY.md.
# Y13 (patrón CI-snapshot): huella sha256 de BOOT/ (la identidad) guardada
# per-máquina; si cambió desde el último doctor → "¿fue intencional?" (es
# territorio N3 — un cambio legítimo NO es error, por eso jamás ✗).
# REGLA: toda esta fase es WARN-only y solo-lectura en --check (la huella
# solo se escribe en modo fix). Estado per-máquina: ~/.claude/workspace/.
DOCTOR_STATE = os.path.join(_paths.state_dir(HOME), "doctor-state.json")
BOOT_BUDGET_FILE = 12_000    # chars/archivo — budget de bootstrap de OpenClaw (R3)
BOOT_BUDGET_TOTAL = 96_000   # chars total (~24k tokens) = 8 archivos a presupuesto;
#   referencia §10-bis.1: post-Y14 el boot de Zenith ronda ~78k (sano), el estado
#   pre-Y14 medido (109k, log-recent 32k) es el failure mode que este techo cacha.
CHARS_PER_TOKEN = 4          # estimación gruesa para reportar tokens


def _read_len(p):
    """Chars del archivo (lo que el boot inyecta). -1 = ilegible."""
    try:
        return len(open(p, encoding="utf-8", errors="replace").read())
    except Exception:
        return -1


def _boot_files(brain, socio):
    """[(rel, path)] de lo que el boot inyecta — fuente única: brain_vitals
    (la fase 8b y el CLI `brain_vitals.py` miden con la MISMA lista)."""
    return brain_vitals.boot_files(brain, socio)


def _boot_fingerprint(brain):
    """{archivo: sha256} de los archivos de identidad (BOOT/*.md). Por-archivo
    a propósito: cuando hay drift, el warn nombra EXACTAMENTE qué cambió."""
    bdir = os.path.join(brain, "BOOT")
    fp = {}
    try:
        names = sorted(x for x in os.listdir(bdir) if x.endswith(".md"))
    except Exception:
        return fp
    for x in names:
        try:
            fp[x] = hashlib.sha256(open(os.path.join(bdir, x), "rb").read()).hexdigest()[:16]
        except Exception:
            fp[x] = "(ilegible)"
    return fp


def phase_brain_budget(ctx, fix):
    out = []
    brains = _resolved_brains(ctx)
    if not brains:
        return [f(WARN, _t("doctor.phase_brain_budget.1", "sin cerebros resueltos"), _t("doctor.phase_brain_budget.2", "nada que medir"), _t("doctor.phase_brain_budget.3", "resuelve la fase 4 primero"))]
    socio = _get_socio(ctx, fix=False)
    state = _read_json(DOCTOR_STATE)
    hashes = state.setdefault("boot_hash", {})
    dirty = False
    for name, brain in brains:
        # — Y8 · presupuesto de boot —
        sizes = [(rel, _read_len(p)) for rel, p in _boot_files(brain, socio)]
        sizes = [(rel, n) for rel, n in sizes if n >= 0]
        total = sum(n for _, n in sizes)
        top = max(sizes, key=lambda x: x[1]) if sizes else (_t("doctor.phase_brain_budget.4", "(nada)"), 0)
        det = (_t("doctor.phase_brain_budget.5", "{total:,} chars (~{v:.1f}k tokens) en {n} archivos · mayor: {v2} ({v3:,})", total=total, v=total / CHARS_PER_TOKEN / 1000, n=len(sizes), v2=top[0], v3=top[1]))
        if total > BOOT_BUDGET_TOTAL:
            out.append(f(WARN, _t("doctor.phase_brain_budget.6", "[{name}] boot sobre presupuesto total (>{v}k chars)", name=name, v=BOOT_BUDGET_TOTAL // 1000), det,
                         _t("doctor.phase_brain_budget.7", "adelgaza el boot empezando por {v}: lo volátil se rota a archivo histórico (p. ej. STATE/log-archive/), lo curado se destila — cada char se paga en TODOS los arranques (Y14)", v=top[0])))
        else:
            out.append(f(OK, _t("doctor.phase_brain_budget.8", "[{name}] presupuesto de boot", name=name), det))
        fat = [(rel, n) for rel, n in sizes if n > BOOT_BUDGET_FILE]
        if fat:
            out.append(f(WARN, _t("doctor.phase_brain_budget.9", "[{name}] archivo(s) de boot sobre presupuesto (>{v}k chars c/u)", name=name, v=BOOT_BUDGET_FILE // 1000),
                         ", ".join(f"{rel} ({n:,})" for rel, n in fat),
                         _t("doctor.phase_brain_budget.10", "rota o destila cada offender: log-recent → archivar entradas viejas a STATE/log-archive/ (convención Y14); MEMORY/PENDIENTES/CLAUDE.md → destilar (mover detalle a wiki/ y dejar punteros)")))
        # — N13 · core blocks de MEMORY.md (read-only, WARN-only) —
        # El doctor MIDE y AVISA; archivar/destilar el excedente es humano
        # (o Atlas con gate). NADA aquí escribe MEMORY.md — jamás.
        mem_path = os.path.join(brain, "STATE", "MEMORY.md")
        if os.path.isfile(mem_path):
            try:
                mm = memory_blocks.measure(mem_path)
            except Exception:
                mm = None
            if mm is None:
                out.append(f(WARN, _t("doctor.phase_brain_budget.11", "[{name}] MEMORY.md ilegible para medir core blocks (N13)", name=name), mem_path,
                             _t("doctor.phase_brain_budget.12", "revisa permisos/encoding del archivo")))
            elif not mm["has_blocks"]:
                out.append(f(OK, _t("doctor.phase_brain_budget.13", "[{name}] MEMORY.md sin core blocks (N13)", name=name),
                             _t("doctor.phase_brain_budget.14", "{total:,} chars sin estructurar", total=mm['total']),
                             _t("doctor.phase_brain_budget.15", "opcional: etiquetar headings `## [bloque] Título` (convención en memory_blocks.py) — migración humana, el harness solo mide")))
            else:
                over = memory_blocks.overflowing(mm)
                det = " · ".join(f"[{lb}] {b['chars']:,}/{b['limit']:,}"
                                 for lb, b in mm["blocks"].items())
                if over:
                    out.append(f(WARN, _t("doctor.phase_brain_budget.16", "[{name}] core block(s) de MEMORY.md sobre su cota (N13)", name=name),
                                 ", ".join(f"[{lb}] +{b['excess']:,} chars"
                                           for lb, b in over) + f" · {det}",
                                 _t("doctor.phase_brain_budget.17", "destila/archiva el excedente menos relevante a STATE/memoria-archivo/ (humano o Atlas con gate — el pipeline JAMÁS edita MEMORY.md); detalle: python3 memory_blocks.py --brain \"{brain}\"", brain=brain)))
                else:
                    out.append(f(OK, _t("doctor.phase_brain_budget.18", "[{name}] core blocks de MEMORY.md dentro de cota", name=name), det))
        # — E2 · INDEX.md (contrato de retrieval) —
        # Solo AVISA (⚠) sobre los caps — JAMÁS edita INDEX.md ni MEMORY.md.
        index_path = os.path.join(brain, "STATE", "INDEX.md")
        if os.path.isfile(index_path):
            try:
                idx_text = open(index_path, encoding="utf-8",
                                errors="replace").read()
                idx_lines = sum(
                    1 for ln in idx_text.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                    and not ln.strip().startswith("<!--")
                    and not ln.strip().startswith("-->")
                    and not ln.strip().startswith("*"))
                if idx_lines >= 100:
                    out.append(f(WARN,
                                 _t("doctor.phase_brain_budget.19", "[{name}] STATE/INDEX.md sobre tope (≥100 líneas útiles)", name=name),
                                 _t("doctor.phase_brain_budget.20", "~{idx_lines} entradas útiles", idx_lines=idx_lines),
                                 _t("doctor.phase_brain_budget.21", "consolidar INDEX.md: fusionar/archivar entradas muertas — el consolidador (nightly) puede añadir nuevas; el humano archiva las que ya no aplican (python3 migrate_memory_v1.py --brain \"{brain}\" --apply)", brain=brain)))
                else:
                    out.append(f(OK, _t("doctor.phase_brain_budget.22", "[{name}] STATE/INDEX.md dentro de tope", name=name),
                                 _t("doctor.phase_brain_budget.23", "~{idx_lines} entradas útiles de máx 100", idx_lines=idx_lines)))
            except Exception:
                out.append(f(WARN, _t("doctor.phase_brain_budget.43", "[{name}] STATE/INDEX.md ilegible", name=name),
                             index_path, _t("doctor.phase_brain_budget.24", "revisa permisos/encoding")))
        else:
            out.append(f(WARN, _t("doctor.phase_brain_budget.42", "[{name}] STATE/INDEX.md no existe (E2)", name=name),
                         _t("doctor.phase_brain_budget.25", "contrato de retrieval por capas ausente"),
                         _t("doctor.phase_brain_budget.26", "crear con: python3 migrate_memory_v1.py --brain \"{brain}\" --apply --stage 2 (o dry-run primero sin --apply)", brain=brain)))

        # — E1 · log-recent.md sobre cap → rotar —
        log_recent_path = os.path.join(brain, "STATE", "log-recent.md")
        if os.path.isfile(log_recent_path):
            try:
                lr_len = _read_len(log_recent_path)
                _log_cap = 4_000
                try:
                    import nightly as _nightly
                    _log_cap = _nightly._log_recent_cap()
                except Exception:
                    pass
                if lr_len > _log_cap:
                    out.append(f(WARN,
                                 _t("doctor.phase_brain_budget.27", "[{name}] STATE/log-recent.md sobre cap (>{v}k chars)", name=name, v=_log_cap // 1000),
                                 f"{lr_len:,} chars · cap {_log_cap:,}",
                                 _t("doctor.phase_brain_budget.28", "rotar el excedente al archivo histórico: python3 nightly.py --brain \"{brain}\" --rotate-logs (es seguro y atómico; NUNCA toca BOOT/MEMORY)", brain=brain)))
                # else: ya cubierto por el chequeo de presupuesto general arriba
            except Exception:
                pass

        # — E1 · MEMORY.md — asegurar que el aviso apunte a la acción —
        # (N13 ya lo hace arriba; solo añadimos hint de acción al overflow)
        # Los bloques sobre cota ya incluyen la acción en la fase N13 anterior.

        # — Y13 · drift de identidad (BOOT/) —
        cur = _boot_fingerprint(brain)
        prev = hashes.get(name)
        if not cur:
            out.append(f(WARN, _t("doctor.phase_brain_budget.29", "[{name}] BOOT/ sin archivos de identidad", name=name), brain,
                         _t("doctor.phase_brain_budget.30", "el cerebro no tiene BOOT/*.md — revisa que el clon esté completo (fase 2) o ") + _report_hint()))
        elif prev is None:
            if fix:
                hashes[name] = cur
                dirty = True
                out.append(f(OK, _t("doctor.phase_brain_budget.31", "[{name}] identidad (BOOT/): huella registrada", name=name),
                             _t("doctor.phase_brain_budget.32", "baseline · {n} archivos", n=len(cur))))
            else:
                out.append(f(OK, _t("doctor.phase_brain_budget.33", "[{name}] identidad (BOOT/): sin huella aún", name=name),
                             _t("doctor.phase_brain_budget.34", "se registra al correr `workspace doctor` (sin --check)")))
        elif prev == cur:
            out.append(f(OK, _t("doctor.phase_brain_budget.35", "[{name}] identidad (BOOT/) sin cambios desde el último doctor", name=name),
                         _t("doctor.phase_brain_budget.36", "{n} archivos", n=len(cur))))
        else:
            diff = []
            for k in sorted(set(prev) | set(cur)):
                if k not in cur:
                    diff.append(f"{k} (eliminado)")
                elif k not in prev:
                    diff.append(_t("doctor.phase_brain_budget.37", "{k} (nuevo)", k=k))
                elif prev[k] != cur[k]:
                    diff.append(k)
            if fix:
                hashes[name] = cur
                dirty = True
            out.append(f(WARN, _t("doctor.phase_brain_budget.38", "[{name}] la identidad cambió desde el último doctor", name=name),
                         ", ".join(diff),
                         _t("doctor.phase_brain_budget.39", "¿fue intencional? BOOT/ es territorio N3 (consenso de los 3 socios) — revisa: git -C \"{brain}\" log --oneline -- BOOT/", brain=brain)
                         + (_t("doctor.phase_brain_budget.40", "  · huella re-registrada: este aviso no se repetirá") if fix
                            else _t("doctor.phase_brain_budget.41", "  · si fue legítimo, corre `workspace doctor` para re-registrar la huella"))))
    if dirty:
        install.write_json(DOCTOR_STATE, state)
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 8b · Signos vitales del cerebro — WARN-only, SOLO LECTURA SIEMPRE
# ══════════════════════════════════════════════════════════════════════════
# Dos monedas que la fase 8 no cubre:
#   · TOKENS session-time: superficies HOT declaradas en STATE/hot-manifest.md
#     (p. ej. un library/INDEX.md que se retrievea en cada research) — el
#     mayor costo real de un cerebro puede NO estar en el boot.
#   · DISCO/SYNC: junk regenerable (node_modules, dist, caches…) que nunca
#     se carga en contexto pero infla backup/Obsidian Sync + stubs de
#     path-pollution (un `X-BRAIN` duplicado junto a `X - BRAIN`).
# REGLA: jamás ✗, jamás escribe/mueve/borra — mide y aconseja. La limpieza
# vive aparte (brain_cleanup.py), opt-in del socio dueño (N3).
MAX_JUNK_SHOWN = 5


def phase_brain_vitals(ctx, fix):
    out = []
    brains = _resolved_brains(ctx)
    if not brains:
        return [f(WARN, _t("doctor.phase_brain_vitals.1", "sin cerebros resueltos"), _t("doctor.phase_brain_vitals.2", "nada que medir"),
                  _t("doctor.phase_brain_vitals.3", "resuelve la fase 4 primero"))]
    socio = _get_socio(ctx, fix=False)
    for name, brain in brains:
        # — superficie HOT real (boot + session del manifiesto) —
        try:
            m = brain_vitals.measure_hot(brain, socio)
        except Exception as e:
            out.append(f(WARN, _t("doctor.phase_brain_vitals.22", "[{name}] signos vitales ilegibles", name=name), str(e),
                         _t("doctor.phase_brain_vitals.4", "revisa permisos del cerebro")))
            continue
        top = sorted(m["boot"] + m["session"], key=lambda x: -x[1])[:3]
        det = (_t("doctor.phase_brain_vitals.5", "~{v:.1f}k tok (boot {v2} + sesión {v3}) · mayor: ", v=m['total_chars'] // brain_vitals.CHARS_PER_TOKEN / 1000, v2=brain_vitals.tokens_k(m['boot_chars']), v3=brain_vitals.tokens_k(m['session_chars']))
               + ", ".join(f"{rel} ({brain_vitals.tokens_k(n)})" for rel, n in top))
        if m["total_chars"] > brain_vitals.HOT_BUDGET_TOTAL:
            offender = top[0][0] if top else _t("doctor.phase_brain_vitals.6", "(nada)")
            out.append(f(WARN, _t("doctor.phase_brain_vitals.7", "[{name}] superficie HOT sobre presupuesto (>{v}k chars ≈ {v2})", name=name, v=brain_vitals.HOT_BUDGET_TOTAL // 1000, v2=brain_vitals.tokens_k(brain_vitals.HOT_BUDGET_TOTAL)),
                         det,
                         _t("doctor.phase_brain_vitals.8", "cada char se paga en CADA sesión — destilar/partir es decisión HUMANA del socio dueño (empezar por {offender}); detalle: python3 brain_vitals.py --brain \"{brain}\"", offender=offender, brain=brain)))
        else:
            out.append(f(OK, _t("doctor.phase_brain_vitals.9", "[{name}] superficie HOT dentro de presupuesto", name=name), det))
        if not m["manifest"]:
            out.append(f(OK, _t("doctor.phase_brain_vitals.10", "[{name}] sin STATE/hot-manifest.md — solo se midió el boot", name=name),
                         _t("doctor.phase_brain_vitals.11", "las superficies session-time (índices retrieveados) no se ven sin manifiesto"),
                         _t("doctor.phase_brain_vitals.12", "declara lo que ese cerebro carga por sesión en STATE/hot-manifest.md (formato: templates/agent/brain/STATE/hot-manifest.md)")))
        if m["missing"]:
            out.append(f(WARN, _t("doctor.phase_brain_vitals.13", "[{name}] manifiesto HOT declara archivos inexistentes", name=name), ", ".join(m["missing"]),
                         _t("doctor.phase_brain_vitals.14", "corrige o retira esas líneas de STATE/hot-manifest.md")))
        # — junk de disco/sync (no gasta tokens — solo avisar) —
        try:
            junk = brain_vitals.scan_junk(brain)
        except Exception:
            junk = []
        if junk:
            junk = sorted(junk, key=lambda j: -j["bytes"])
            shown = ", ".join(f"{j['rel']} ({brain_vitals.human(j['bytes'])}"
                              f" · {j['kind']})" for j in junk[:MAX_JUNK_SHOWN])
            more = len(junk) - MAX_JUNK_SHOWN
            out.append(f(WARN, _t("doctor.phase_brain_vitals.15", "[{name}] junk en el cerebro ({n} hallazgo(s) — disco/sync, NO tokens)", name=name, n=len(junk)),
                         shown + (_t("doctor.phase_brain_vitals.16", " · +{more} más", more=more) if more > 0 else ""),
                         brain_vitals.SYNC_HINT + _t("doctor.phase_brain_vitals.17", "; regenerables → cuarentena opt-in: python3 brain_cleanup.py --brain \"{brain}\" (dry-run; N3 — decisión del socio dueño)", brain=brain)))
        else:
            out.append(f(OK, _t("doctor.phase_brain_vitals.18", "[{name}] sin junk detectado", name=name),
                         _t("doctor.phase_brain_vitals.19", "node_modules/dist/caches/.bak/binarios grandes: nada")))
    # — stubs de path-pollution (hermanos duplicados del cerebro) —
    try:
        stubs = brain_vitals.detect_stubs(brains)
    except Exception:
        stubs = []
    for s in stubs:
        out.append(f(WARN, _t("doctor.phase_brain_vitals.20", "stub de path-pollution junto a un cerebro"),
                     f"{s['stub']} duplica {s['brain']}",
                     _t("doctor.phase_brain_vitals.21", "alguna sesión escribió a un path mal resuelto — revisar contenido, fusionar A MANO y retirar el stub (y paths.local.json si apunta ahí)")))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 9 · Secret-scan de cerebros (N14) — WARN-only, solo-lectura SIEMPRE
# ══════════════════════════════════════════════════════════════════════════
# Los cerebros se respaldan a git: una clave API commiteada (aunque el repo
# sea privado) es una fuga — git guarda historia. Esta fase escanea el working
# tree de cada cerebro con secret_scan (patrones de proveedor + anti-FP de
# placeholders) y reporta WARN, JAMÁS ✗: no bloquear el flujo del socio
# (regla 3 de la serie N). No modifica nada ni en --check ni en fix: escanear
# no repara — el fix-it (env var / .gitignore / rotar) es del socio.
# Pre-commit opt-in (decisión N14): `python3 secret_scan.py --staged`, lo
# agrega el socio A MANO si lo quiere; WORKSPACE no instala git hooks solo.
MAX_SECRET_FINDINGS_SHOWN = 6


def phase_secrets(ctx, fix):
    out = []
    brains = _resolved_brains(ctx)
    if not brains:
        return [f(WARN, _t("doctor.phase_secrets.1", "sin cerebros resueltos"), _t("doctor.phase_secrets.2", "nada que escanear"),
                  _t("doctor.phase_secrets.3", "resuelve la fase 4 primero"))]
    for name, brain in brains:
        try:
            findings, nfiles = secret_scan.scan_brain(brain)
        except Exception as e:   # falla-suave: el escáner jamás tumba al doctor
            out.append(f(WARN, _t("doctor.phase_secrets.4", "[{name}] el secret-scan falló", name=name),
                         f"{type(e).__name__}: {e}",
                         _report_hint()))
            continue
        if not findings:
            out.append(f(OK, _t("doctor.phase_secrets.5", "[{name}] sin secretos detectables en el working tree", name=name),
                         _t("doctor.phase_secrets.6", "{nfiles} archivo(s) escaneados · {n} clases de credencial · historia git no escaneada (audit manual: --history)", nfiles=nfiles, n=len(secret_scan.PATTERNS))))
            continue
        shown = findings[:MAX_SECRET_FINDINGS_SHOWN]
        det = " · ".join(f"{x['path']}:{x['line']} [{x['class']}] {x['excerpt']}"
                         for x in shown)
        if len(findings) > len(shown):
            det += _t("doctor.phase_secrets.7", " · (+{v} más)", v=len(findings) - len(shown))
        out.append(f(WARN, f"[{name}] posible(s) secreto(s) rumbo a git "
                          f"({len(findings)})", det,
                     _t("doctor.phase_secrets.8", "NO lo commitees: mueve la clave a una variable de entorno o a un archivo en .gitignore — y si ya se commiteó alguna vez, RÓTALA (git guarda historia). ¿Falso positivo? marca la línea con `{allow_marker}`. Chequeo manual pre-commit (opt-in): python3 \"{v}\" --staged · Auditar historia git (WARN-only): python3 \"{v}\" --history \"{brain}\"", allow_marker=secret_scan.ALLOW_MARKER,
                        v=os.path.join(ROOT, 'secret_scan.py'),
                        brain=brain)))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 10 · Skills por máquina (gating N11) — INFORMATIVO, jamás ⚠/✗
#  Una skill oculta NO es un problema: es el diseño (el catálogo efectivo es
#  por máquina — una máquina Windows no tiene los mismos binarios que una Mac).
#  Solo el fallo del propio escáner amerita WARN (falla-suave).
# ══════════════════════════════════════════════════════════════════════════
MAX_HIDDEN_SKILLS_SHOWN = 8


def phase_skill_gating(ctx, fix):
    out = []
    brains = _resolved_brains(ctx)
    if not brains:
        return [f(OK, _t("doctor.phase_skill_gating.1", "sin cerebros resueltos"), _t("doctor.phase_skill_gating.2", "nada que evaluar"))]
    for name, brain in brains:
        try:
            results = skill_meta.scan_catalog(brain)
        except Exception as e:   # falla-suave: el gating jamás tumba al doctor
            out.append(f(WARN, _t("doctor.phase_skill_gating.3", "[{name}] el escaneo de gating falló", name=name),
                         f"{type(e).__name__}: {e}",
                         _report_hint()))
            continue
        if not results:
            out.append(f(OK, _t("doctor.phase_skill_gating.4", "[{name}] sin skills que evaluar", name=name),
                         _t("doctor.phase_skill_gating.5", "no hay skills/ con archivos de instrucciones")))
            continue
        declared = [r for r in results if r["requires"]]
        hidden = [r for r in results if not r["available"]]
        if not hidden:
            out.append(f(OK, _t("doctor.phase_skill_gating.6", "[{name}] catálogo completo disponible en esta máquina", name=name),
                         _t("doctor.phase_skill_gating.7", "{n} skill(s) · {n2} declaran `requires:` y todas se satisfacen aquí", n=len(results), n2=len(declared))))
            continue
        shown = hidden[:MAX_HIDDEN_SKILLS_SHOWN]
        det = " · ".join(_t("doctor.phase_skill_gating.11", "{name} (falta {missing})", name=r['name'], missing=', '.join(r['missing']))
                         for r in shown)
        if len(hidden) > len(shown):
            det += _t("doctor.phase_skill_gating.8", " · (+{v} más)", v=len(hidden) - len(shown))
        out.append(f(OK, _t("doctor.phase_skill_gating.9", "[{name}] {n} skill(s) auto-oculta(s) en esta máquina — por diseño (N11)", name=name, n=len(hidden)), det,
                     _t("doctor.phase_skill_gating.10", "informativo: la skill se omite del catálogo efectivo aquí, el archivo queda intacto. Instala lo que falta SOLO si la necesitas en esta máquina. Detalle: python3 \"{v}\" \"{brain}\" --hidden",
                        v=os.path.join(ROOT, 'skill_meta.py'),
                        brain=brain)))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  Reporte
# ══════════════════════════════════════════════════════════════════════════
def phase_brand(ctx, fix):
    """Completitud del BRAND por-agente: banner/dashboard/statusline declarados en el
    agent.json deben RESOLVER y EXISTIR. Tras la migración v2.3 el estado canónico es
    WORKSPACE-resident ({root}/agents/<n>/brand/...) — el cerebro es contenido puro; las
    copias viejas en el cerebro quedaron deprecadas. Por eso aquí NO importa de DÓNDE
    salen (cerebro o harness): importa que los scripts existan. Solo se WARNea cuando
    falta una declaración o cuando un script declarado NO resuelve a un archivo real
    (el motor cae al banner genérico mientras tanto). Solo lectura: reporta, no repara."""
    out = []
    if not _resolved_brains(ctx):
        return []
    for a in ctx["agents"]:
        name, brain = a["name"], a["brain"]
        if not (brain and os.path.isdir(brain)):
            continue
        declared = a["cfg"].get("scripts") or {}
        scripts = install.expand(declared, brain)
        if not scripts.get("banner"):
            # Sin banner resoluble: o no está declarado, o expand lo descartó por
            # resolver FUERA del cerebro/harness (SEC) → en ambos casos no sale brand.
            why = (_t("doctor.phase_brand.1", "su agent.json no define scripts.banner")
                   if not declared.get("banner")
                   else _t("doctor.phase_brand.2", "scripts.banner ({banner}) resuelve fuera del cerebro/harness y se descartó", banner=declared['banner']))
            out.append(f(WARN, _t("doctor.phase_brand.3", "[{name}] sin banner resoluble", name=name), why,
                         _t("doctor.phase_brand.8", "declara scripts.banner = {root}/agents/<n>/brand/<n>-banner.py")))
            continue
        missing = [k for k in ("banner", "dashboard", "statusline")
                   if scripts.get(k) and not os.path.exists(scripts[k])]
        if missing:
            out.append(f(WARN, _t("doctor.phase_brand.9", "[{name}] brand incompleto", name=name),
                         _t("doctor.phase_brand.4", "falta(n): ") + " · ".join(f"{k}→{scripts[k]}" for k in missing),
                         _t("doctor.phase_brand.5", "verifica que los scripts existan en {root}/agents/<n>/brand/")))
        else:
            # Canónico v2.3: viven en el harness ({root}); el cerebro como fallback
            # de compatibilidad sigue siendo válido. Lo que cuenta es que EXISTAN.
            from_brain = scripts["banner"].startswith(os.path.realpath(brain))
            origen = _t("doctor.phase_brand.6", "el cerebro") if from_brain else "WORKSPACE"
            out.append(f(OK, _t("doctor.phase_brand.10", "[{name}] brand completo desde {origen}", name=name, origen=origen),
                         _t("doctor.phase_brand.7", "banner+dashboard+statusline resueltos y existentes")))
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
        else:
            out.append(f(OK, _t("doctor.phase_legacy_residue.5", "agents.local.json sin punteros a la instalación anterior"),
                         _t("doctor.phase_legacy_residue.6", "ninguna entrada bajo la ruta vieja")))
    except Exception as e:
        out.append(f(OK, _t("doctor.phase_legacy_residue.22", "agents.local.json no evaluable"),
                     _t("doctor.phase_legacy_residue.7", "%s: %s — señal omitida (fail-soft)") % (type(e).__name__, e)))
    # (a)/(c) por cerebro resuelto
    for name, brain in _resolved_brains(ctx):
        hits = _scan_brand_legacy(brain)
        if hits:
            out.append(f(WARN, _t("doctor.phase_legacy_residue.8", "[%s] marca brain-resident con refs muertas de la instalación anterior") % name,
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
        if not hits and not os.path.isdir(old_dir):
            out.append(f(OK, _t("doctor.phase_legacy_residue.19", "[%s] sin restos de la instalación anterior") % name,
                         _t("doctor.phase_legacy_residue.20", "marca brain-resident limpia · sin %s") % sub))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 11 · Liveness (estado colgante · SOLO DETECCIÓN)
# ══════════════════════════════════════════════════════════════════════════
def phase_liveness(ctx, fix):
    """Estado colgante del harness vía dash.dev.liveness.check(): worktrees
    huérfanos — entradas del registry de dueños viejas (>24h) Y sucias
    confirmadas. Se llama SIN agent/brain a propósito: la señal de inbox es
    per-agente y no aplica al contexto multi-agente del doctor; aquí solo
    interesa la señal GLOBAL. SOLO DETECCIÓN (como las fases 1b/9/10): `fix`
    no hace nada — rescatar o descartar un worktree a medias es decisión del
    socio. Fail-soft total: si liveness/el registry truenan, la fase reporta
    "no evaluable" y el doctor sigue — jamás lo tumba."""
    out = []
    try:
        from dash.dev import liveness
        warns = liveness.check()          # sin agent/brain → solo worktrees
        for w in warns:
            # liveness ya trae "⚠ " en el texto; el símbolo lo pone el doctor
            out.append(f(WARN, _t("doctor.phase_liveness.5", "estado colgante detectado"),
                         str(w).lstrip("⚠").strip(),
                         _t("doctor.phase_liveness.1", "rescata el trabajo (commit en su rama) o descarta el worktree — el registry vive en ~/.claude/workspace/worktree-owners.json")))
        if not out:
            out.append(f(OK, _t("doctor.phase_liveness.2", "sin estado colgante"),
                         _t("doctor.phase_liveness.3", "registry de worktrees limpio (dash.dev.liveness)")))
    except Exception as e:
        # informativo: liveness roto/ausente no es un problema del harness
        out.append(f(OK, _t("doctor.phase_liveness.6", "liveness no evaluable"),
                     _t("doctor.phase_liveness.4", "{name}: {e} — señal omitida (fail-soft)", name=type(e).__name__, e=e)))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 12 · Voz global (dictado local por whisper.cpp) — macOS F1, opcional
# ══════════════════════════════════════════════════════════════════════════
# Feature OPCIONAL (opt-in de verdad): sus faltantes son WARN, nunca FAIL — no
# tener voz no rompe el harness. Reusa los helpers de voice.py (fuente única).
# El fix NO instala nada por sí solo (antes un `workspace update` disparaba
# `brew install` de minutos + un modelo de 150MB sin preguntar — una feature
# opcional no se instala sola): instalar es opt-in explícito,
#   WORKSPACE_VOICE_SETUP=1 workspace doctor
# y entonces sí brew + modelo, idempotente. Sin el opt-in, solo diagnostica.
VOICE_SETUP_ENV = "WORKSPACE_VOICE_SETUP"


def phase_voice(ctx, fix):
    import capabilities
    vc = capabilities.voice()
    if vc["state"] == "unsupported":     # no soportado por OS ≠ dependencia faltante
        return [f(OK, _t("doctor.phase_voice.9", "voz (dictado)"), _t("doctor.phase_voice.14", "no soportado: ") + vc["detail"])]
    try:
        import voice
    except Exception as e:
        return [f(WARN, _t("doctor.phase_voice.10", "voz no evaluable"), "%s: %s" % (type(e).__name__, e))]
    out = []
    brew = shutil.which("brew")
    setup = fix and os.environ.get(VOICE_SETUP_ENV) == "1"
    # whisper.cpp
    if voice._find_whisper():
        out.append(f(OK, "whisper.cpp", _t("doctor.phase_voice.11", "instalado (dictado local disponible)")))
    else:
        if setup and brew:
            _run(["brew", "install", "whisper-cpp"], timeout=600)
        out.append(f(OK if voice._find_whisper() else WARN, "whisper.cpp",
                     _t("doctor.phase_voice.1", "STT local del dictado por voz (opcional)"),
                     _t("doctor.phase_voice.12", "brew install whisper-cpp — o todo junto: {voice_setup_env}=1 workspace doctor", voice_setup_env=VOICE_SETUP_ENV)))
    # modelo
    model = voice.default_model()
    if os.path.isfile(model):
        out.append(f(OK, _t("doctor.phase_voice.2", "modelo de whisper"), os.path.basename(model)))
    else:
        if setup:
            _download_whisper_model(model)
        out.append(f(OK if os.path.isfile(model) else WARN, _t("doctor.phase_voice.3", "modelo de whisper"),
                     _t("doctor.phase_voice.4", "falta %s (~150MB)") % os.path.basename(model),
                     _t("doctor.phase_voice.13", "{voice_setup_env}=1 workspace doctor lo baja, o descarga ggml-base.bin a ", voice_setup_env=VOICE_SETUP_ENV) + os.path.dirname(model)))
    # grabador
    tool, _ = voice._recorder_cmd("x.wav")
    if tool:
        out.append(f(OK, _t("doctor.phase_voice.5", "grabador de micro"), tool))
    else:
        if setup and brew:
            _run(["brew", "install", "ffmpeg"], timeout=600)
        tool2, _ = voice._recorder_cmd("x.wav")
        out.append(f(OK if tool2 else WARN, _t("doctor.phase_voice.6", "grabador de micro"),
                     _t("doctor.phase_voice.7", "ffmpeg o sox para capturar el audio"), "brew install ffmpeg"))
    # guía del atajo + permisos (siempre informativo)
    out.append(f(OK, "atajo + permisos",
                 _t("doctor.phase_voice.8", "enlaza `workspace voice` a una tecla en Atajos de macOS; da permiso de Micrófono y Accesibilidad (para pegar). `workspace voice --check` reporta lo que falte")))
    return out


def _download_whisper_model(dest):
    """Baja ggml-base a `dest` (una vez, en --fix). Falla-suave; NO es parte del
    runtime de la voz (que es 100% local) — es setup como un `brew install`."""
    url = ("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
           "ggml-base.bin")
    curl = shutil.which("curl")
    if not curl:
        return
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        _run([curl, "-fsSL", "-o", dest, url], timeout=600)
    except Exception:
        pass


# ─── 13 · Capacidades efectivas (OS + motor + deps — capabilities.py) ──────────
# Fuente única de «qué funciona AQUÍ» (U05/W-F06/W-F07): distingue no soportado
# (por OS o motor) de dependencia faltante y de lo no verificable. Solo lectura:
# PATH y archivos de config, sin red, sin login, sin lanzar motores.
_CAP_STATUS = {"supported": OK, "unsupported": OK, "off": OK, "unknown": OK,
               "missing_dependency": WARN}


def phase_capabilities(ctx, fix):
    import capabilities
    out = []
    base = capabilities.matrix()
    for key in ("split", "panel", "voice"):
        c = base[key]
        out.append(f(_CAP_STATUS[c["state"]], key,
                     "%s · %s" % (capabilities.label(c["state"]), c["detail"]), c["remedy"]))
    engines = []
    for a in ctx["agents"]:
        e = (a.get("cfg") or {}).get("engine") or a["entry"].get("engine")
        if e and e not in engines:
            engines.append(e)
    for e in engines:
        m = capabilities.matrix(e)
        for key in ("status_live", "headless"):
            c = m[key]
            out.append(f(_CAP_STATUS[c["state"]], "%s · %s" % (e, key),
                         "%s · %s" % (capabilities.label(c["state"]), c["detail"]), c["remedy"]))
    return out


PHASES = [
    ("1 · Prerrequisitos (git · python · CLI de motores · gh)", phase_prereqs),
    ("1b · Rutas redirigidas (OneDrive/known-folders · solo detección)", phase_redirected_paths),
    ("2 · Repos hermanos (nombres exactos)", phase_siblings),
    ("3 · Repos al día con origin", phase_updated),
    ("3b · Versión y ajustes de actualización", phase_update_state),
    ("4 · Cerebros resolubles (dispatch) · sesiones (resume)", phase_brains),
    ("5 · Hooks por cerebro (contrato de eventos N9 · events.py)", phase_hooks),
    ("5b · Brand por-agente (banner/dashboard/statusline resueltos y existentes)", phase_brand),
    ("5c · MCPs por cerebro (materialización · connectors.PORTABILITY)", phase_mcps),
    ("5d · Restos de la instalación anterior (anti-recurrencia)", phase_legacy_residue),
    ("6 · Launchers (workspace + agentes)", phase_launchers),
    ("7 · Greeter · socio · tema · retención", phase_extras),
    ("8 · Cerebro: presupuesto de boot + identidad (BOOT/)", phase_brain_budget),
    ("8b · Cerebro: signos vitales — HOT real (manifiesto) + junk (solo mide)",
     phase_brain_vitals),
    ("9 · Secretos en cerebros (secret-scan N14 · WARN-only)", phase_secrets),
    ("10 · Skills por máquina (gating N11 · informativo)", phase_skill_gating),
    ("11 · Liveness (worktrees huérfanos · solo detección)", phase_liveness),
    ("12 · Voz global (dictado local whisper.cpp · macOS · opcional)", phase_voice),
    ("13 · Capacidades efectivas (OS + motor + dependencias)", phase_capabilities),
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


# ══════════════════════════════════════════════════════════════════════════
#  Cierre interactivo: resolver lo pendiente con Zenith
# ══════════════════════════════════════════════════════════════════════════
# Si al terminar quedan hallazgos ⚠/✗, ofrecer enviarlos a Zenith: una sesión
# INTERACTIVA NORMAL (vía dispatch, igual que `workspace zenith`) sembrada con el
# reporte, enfocada SOLO en resolverlos conversando.
# REGLAS DURAS:
#   · falla-suave SIEMPRE: sin TTY / sin agente / si el lanzamiento truena →
#     los hallazgos ya están impresos arriba (con fix-its) y el doctor termina
#     normal — este cierre jamás rompe el doctor ni cambia su exit code.
#   · en --check / no-interactivo NO se bloquea esperando input (la UI y CI
#     corren el doctor con --check; además: WORKSPACE_DOCTOR_NO_ZENITH=1 lo apaga).
#   · SEGURIDAD: sesión supervisada estándar — NADA de `claude -p`, NADA de
#     --dangerously-skip-permissions, NADA de escribir settings/permissions.
ZENITH_SESSION_NAME = "doctor"   # pestaña dedicada a resolver pendientes del doctor


def _seed_path():
    return os.path.join(_paths.state_dir(HOME), "doctor-report.md")


def pending_findings(results):
    """[(titulo_fase, finding)] con status ⚠/✗ — lo que quedó sin resolver."""
    out = []
    for title, _, finds in results:
        for x in finds:
            if x["status"] in (WARN, FAIL):
                out.append((title, x))
    return out


def build_zenith_report(pending, mode=""):
    """Markdown que siembra la sesión de Zenith: hallazgos ⚠/✗ + fix-its del
    doctor, con instrucciones de foco. Texto plano (sin ANSI)."""
    import datetime
    lines = [
        _t("doctor.build_zenith_report.1", "# workspace doctor — pendientes por resolver"),
        _t("doctor.report.generated", "Generado: {when}",
           when=datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
        + (_t("doctor.report.mode", " · modo: {mode}", mode=mode) if mode else "")
        + f" · WORKSPACE: {ROOT}",
        "",
        _t("doctor.build_zenith_report.2", "Esta sesión la abrió `workspace doctor`: quedaron hallazgos sin resolver y el socio eligió resolverlos contigo. Tu ÚNICO objetivo aquí es guiarlo a arreglar/configurar estos puntos, uno por uno, conversando."),
        _t("doctor.build_zenith_report.3", "Reglas: cambios mínimos y explicados antes de ejecutarlos; los fix-its de abajo son la sugerencia del doctor (síguelos salvo mejor razón); NO toques BOOT/ ni `permissions`; al terminar, sugiere re-correr `workspace doctor --check` para verificar."),
        "",
    ]
    for title, x in pending:
        sym = "✗" if x["status"] == FAIL else "⚠"
        lines.append(_t("doctor.build_zenith_report.4", "## [{sym}] FASE {title}", sym=sym, title=title))
        lines.append(_t("doctor.build_zenith_report.5", "- hallazgo: {label}", label=x['label']))
        if x["detail"]:
            lines.append(_t("doctor.report.detail", "- detalle: {detail}", detail=x['detail']))
        if x["action"]:
            lines.append(_t("doctor.report.fixit", "- fix-it sugerido: {action}", action=x['action']))
        lines.append("")
    return "\n".join(lines)


def launch_zenith_session(report):
    """Lanza una sesión interactiva de Zenith sembrada con `report`, reusando
    dispatch (mismo arranque que `workspace zenith`, sin banner y sin menú:
    pestaña directa `doctor`). True si la sesión corrió; False = falla-suave
    (el caller solo informa — los hallazgos ya están impresos)."""
    try:
        if not dispatch.find_agent("zenith"):
            return False
        seed = _seed_path()
        try:   # archivo-semilla: persistencia/auditoría del reporte (best-effort)
            os.makedirs(os.path.dirname(seed), exist_ok=True)
            with open(seed, "w", encoding="utf-8") as fh:
                fh.write(report)
            report += _t("doctor.launch_zenith_session.1", "\n(Este reporte también quedó en {seed}.)", seed=seed)
        except Exception:
            pass
        import uuid
        wid = str(uuid.uuid4())
        # Sesión NORMAL supervisada: dispatch → engine → `claude` interactivo.
        # El reporte viaja como prompt inicial (passthrough) — cero flags de
        # permisos, cero -p, cero settings.
        cmd = [sys.executable, os.path.join(ROOT, "dispatch.py"), "zenith",
               "--no-banner", "--open", wid, "--name", ZENITH_SESSION_NAME, report]
        return subprocess.call(cmd) == 0
    except Exception:
        return False


def offer_zenith_handoff(results, check_only):
    """Cierre del doctor: si quedan ⚠/✗ y hay TTY (y NO es --check), ofrecer
    enviarlos a Zenith. Jamás bloquea en --check/no-interactivo, jamás lanza
    excepción, jamás cambia el exit code del doctor."""
    try:
        pending = pending_findings(results)
        if not pending or check_only:
            return False
        if os.environ.get("WORKSPACE_DOCTOR_NO_ZENITH"):
            return False
        if _is_dist_install():        # DEPLOY-5: a un externo no le ofrecemos "enviar a Zenith"
            return False
        try:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                return False
        except Exception:
            return False
        print(_t("doctor.offer_zenith_handoff.1", "\n  {yel}Quedan {n} punto(s) por resolver.{r}", yel=YEL, n=len(pending), r=R))
        print(_t("doctor.offer_zenith_handoff.2", "  {dim}[s] enviarlos a Zenith (abre una sesión temporal con el reporte)   ·   [Enter] salir{r}", dim=DIM, r=R))
        try:
            ans = input("  › ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if ans not in ("s", "si", "sí", "y", "yes"):
            return False
        print(_t("doctor.offer_zenith_handoff.3", "  {dim}Abriendo sesión de Zenith con el reporte…{r}", dim=DIM, r=R))
        if launch_zenith_session(build_zenith_report(pending, mode="fix")):
            return True
        print(_t("doctor.offer_zenith_handoff.4", "  {yel}No pude abrir la sesión de Zenith{r} {dim}— los hallazgos y sus fix-its ya están arriba; resuélvelos a mano o corre `zenith` tú mismo.{r}", yel=YEL, r=R, dim=DIM))
        return False
    except Exception:
        return False   # falla-suave total: el cierre jamás rompe el doctor


def main(argv=None):
    args = list(argv) if argv is not None else sys.argv[1:]
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
                       _report_hint())]
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
    # cierre: resolver lo pendiente con Zenith (interactivo, falla-suave;
    # NUNCA en --check ni sin TTY — no bloquea flujos automáticos ni la UI/CI)
    offer_zenith_handoff(results, check_only)
    print()
    return 1 if n[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
