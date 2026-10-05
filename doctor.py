#!/usr/bin/env python3
"""WORKSPACE · doctor — instalador-reparador por FASES, idempotente.

`workspace doctor`           revisa cada fase y REPARA lo que pueda (fase OK → se salta).
`workspace doctor --check`   solo diagnostica: tabla de salud, NO modifica nada.
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
import dispatch   # noqa: E402  (resolución real de cerebros — la misma que usa el harness)
import install    # noqa: E402  (fixers ya probados: launchers, greeter, tema, gitignore)
import events     # noqa: E402  (contrato de eventos N9 — la fase 5 valida contra él)
import session_paths  # noqa: E402  (única fuente del path de sesiones de Claude Code)
import secret_scan  # noqa: E402  (N14 — la fase 9 escanea cerebros con él)
import skill_meta   # noqa: E402  (N11 — la fase 10 reporta el gating por máquina)
import memory_blocks  # noqa: E402  (N13 — la fase 8 mide core blocks de MEMORY.md)
import pathguard   # noqa: E402  (P0-4 — detección de rutas redirigidas a OneDrive)
import brain_vitals  # noqa: E402  (fase 8b — HOT real por manifiesto + junk; SOLO lee)

HOME = os.path.expanduser("~")
IS_WIN = os.name == "nt"
if IS_WIN:
    os.system("")  # habilita ANSI en Windows 10+ (no-op en consolas viejas)
import _utf8; _utf8.harden()  # B2 · UTF-8 en stdout/err (cp1252 reventaría con box-drawing)


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
        return json.load(open(p, encoding="utf-8"))
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
        return "revisa la salida y contacta a soporte con ella"
    return "repórtalo al equipo (o a tu agente principal) con esta salida"


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
        agents.append({"entry": a, "name": a["name"], "cfg": cfg,
                       "brain": dispatch.resolve_brain(a["name"], cfg)})
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
        out.append(f(FAIL, "git no está en PATH", "",
                     "instala Git (https://git-scm.com) y abre una terminal nueva"))
    # python (estamos corriendo en él; solo validar versión)
    if sys.version_info >= (3, 9):
        out.append(f(OK, "python", f"{sys.version.split()[0]} · {sys.executable}"))
    else:
        out.append(f(WARN, "python viejo", sys.version.split()[0],
                     "instala Python 3.9+ — WORKSPACE lo requiere"))
    # CLI de los MOTORES en uso (harness-agnóstico): se valida el binario de
    # cada engine que algún agente registrado usa — nada de asumir uno solo.
    engines = _engines_in_use(ctx)
    if not engines:
        out.append(f(OK, "motores", "sin agentes registrados — el CLI del "
                     "motor se valida al registrar el primero (Agregar agente)"))
    for eng, who in sorted(engines.items()):
        try:
            mod = dispatch.load_engine(eng)
        except Exception:
            mod = None
        if mod is None:
            out.append(f(FAIL, f"motor '{eng}' no disponible",
                         f"lo usan: {', '.join(who)}",
                         f"engines/{eng.replace('-', '_')}.py falta o no "
                         "carga — actualiza el harness (`workspace update`) "
                         "o corrige el agente a un motor instalado"))
            continue
        binary = getattr(mod, "BINARY", None) or ENGINE_BINARIES.get(eng)
        if not binary:
            out.append(f(OK, f"motor '{eng}'",
                         f"sin CLI externo que validar · lo usan: {', '.join(who)}"))
            continue
        exe = shutil.which(binary)
        if exe:
            _, v, _ = _run([binary, "--version"], timeout=15)
            out.append(f(OK, f"{binary} CLI (motor {eng})", v or exe))
        else:
            out.append(f(FAIL, f"{binary} CLI no está en PATH (motor '{eng}')",
                         f"lo usan: {', '.join(who)}",
                         ENGINE_INSTALL_HINTS.get(
                             eng, f"instala el CLI `{binary}` de ese motor y "
                                  "abre una terminal nueva")))
    # gh (sesión de GitHub para clonar/pull de repos privados)
    gh = shutil.which("gh")
    if not gh:
        out.append(f(WARN, "gh (GitHub CLI) no está instalado",
                     "git puede funcionar igual con credential manager",
                     "opcional pero recomendado: instala gh y corre `gh auth login` "
                     "(con tu cuenta de GitHub)"))
    else:
        rc, _, err = _run(["gh", "auth", "status"], timeout=15)
        if rc == 0:
            out.append(f(OK, "gh auth", "sesión de GitHub activa"))
        else:
            out.append(f(WARN, "gh sin sesión de GitHub", (err.splitlines() or [""])[0],
                         "corre `gh auth login` y entra con tu cuenta de GitHub"))
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
        out.append(f(FAIL, "WORKSPACE vive en una ruta redirigida a la nube",
                     f"{ROOT}  (bajo {root_lbl})",
                     "muévelo FUERA de OneDrive — a %LOCALAPPDATA%\\Workspace o C:\\Workspace — "
                     "y reinstala (python install.py). OneDrive sincroniza y BLOQUEA los "
                     "archivos del harness (locks, latencia, settings per-máquina) → fallos "
                     "intermitentes difíciles de diagnosticar"))
    else:
        out.append(f(OK, "WORKSPACE fuera de rutas redirigidas (OneDrive/known-folders)", ROOT))
    for name, brain in _resolved_brains(ctx):
        lbl = pathguard.redirected_root(brain)
        if lbl:
            up = name.upper()
            out.append(f(FAIL, f"[{name}] el cerebro vive en una ruta redirigida a la nube",
                         f"{brain}  (bajo {lbl})",
                         f"muévelo a C:\\{up} - BRAIN (fuera de OneDrive) y vuelve a declararlo "
                         f"en {dispatch._paths_local()}  →  {{\"brains\": {{\"{name}\": "
                         f"\"C:\\\\{up} - BRAIN\"}}}}. OneDrive + Obsidian Sync sobre el mismo "
                         "vault = doble canal (corrupción); además los locks/latencia de la nube "
                         "rompen sesiones (resume) y el estado per-máquina (settings.local.json)"))
        else:
            out.append(f(OK, f"[{name}] cerebro fuera de rutas redirigidas", brain))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 2 · Repos hermanos con nombres EXACTOS (solo instruye: no clona)
# ══════════════════════════════════════════════════════════════════════════
def phase_siblings(ctx, fix):
    out = []
    parent = os.path.dirname(ROOT)
    if _is_git(ROOT):
        out.append(f(OK, "WORKSPACE es repo git", ROOT))
    else:
        out.append(f(WARN, "WORKSPACE no es repo git", "instalación por sync — sin auto-update",
                     "clona el repo del harness con git "
                     f'(carpeta "WORKSPACE" en {parent}) para recibir actualizaciones'))
    ov = {}
    try:
        ov = dispatch._local_overrides().get("brains", {})
    except Exception:
        pass
    for a in ctx["agents"]:
        name = a["name"]
        # IN-REPO primero: su cerebro vive dentro de WORKSPACE y exigirle carpeta
        # hermana era un FALSO ROJO (hallazgo 2026-09-21, agente `doctor`).
        if _in_repo(a.get("brain")) and os.path.isdir(a.get("brain") or ""):
            out.append(f(OK, f'cerebro "{name}" in-repo',
                         "vive dentro del harness (viaja con la app) · "
                         "sin vault hermano por diseño"))
            continue
        raw = a["cfg"].get("brain", "")
        target = os.path.basename(os.path.normpath(raw)) if raw else name
        sibling = os.path.join(parent, target)
        brain, via = "", "carpeta hermana"
        if os.path.isdir(sibling):
            brain = sibling
        elif name in ov and os.path.isdir(os.path.expanduser(ov[name])):
            brain, via = os.path.expanduser(ov[name]), "vía paths.local.json"
        if brain:
            # transporte del cerebro: obsidian-sync (DEFAULT, canal de primera
            # clase — git no aplica) o git (solo si el socio lo declara).
            transport = dispatch.brain_transport(name, brain)
            if transport == "obsidian-sync":
                out.append(f(OK, f'cerebro "{target}"',
                             f"{via} · sincroniza por Obsidian Sync — git no aplica"))
            elif _is_git(brain) and dispatch.obsidian_sync_enabled(brain):
                # transport git DECLARADO + Sync activo = DOS canales sobre el
                # mismo vault → corrupción segura (solo aplica con override git)
                out.append(f(FAIL, f'"{target}": repo git Y Obsidian Sync a la vez', brain,
                             "un solo canal por vault: apaga Obsidian Sync en este vault "
                             "o quita el override de transport git en "
                             f"{dispatch._paths_local()}"))
            elif _is_git(brain):
                out.append(f(OK, f'cerebro "{target}"', f"{via} · repo git (transport declarado)"))
            else:
                out.append(f(WARN, f'"{target}": transport git declarado pero no es repo git',
                             "no recibirá actualizaciones por git pull",
                             "re-clónalo con git o quita el override "
                             f"de transport en {dispatch._paths_local()} para volver al "
                             "default (Obsidian Sync)"))
        else:
            url = CLONE_URLS.get(target, "<URL del repo de tu cerebro>")
            out.append(f(FAIL, f'falta el cerebro "{target}"',
                         "el nombre de carpeta debe ser EXACTO (con espacios)",
                         f"instala el vault por Obsidian Sync (canal por defecto de los "
                         f"cerebros) junto a WORKSPACE, o clónalo:  git clone {url} \"{target}\"  "
                         f"(en {parent}) — o si ya vive en otra ruta, decláralo en "
                         f"{dispatch._paths_local()}  →  {{\"brains\": {{\"{name}\": \"/ruta\"}}}}"))
        # Punto ciego histórico: el override de paths.local.json GANA en runtime
        # (dispatch.resolve_brain lo prefiere SOBRE la carpeta hermana), aunque
        # exista la hermana real. Si el override apunta a OTRO sitio que la
        # hermana existente, el launcher/picker leen ahí — y las sesiones del
        # cerebro real "desaparecen" (bug observado: paths.local quedó con rutas
        # /tmp de una prueba). Doctor antes no lo veía porque elegía la hermana
        # primero. WARN, no FAIL: un override a otra ruta REAL puede ser legítimo.
        try:
            runtime = a.get("brain", "")   # = resolve_brain (paths.local primero)
            if (name in ov and os.path.isdir(sibling) and runtime
                    and os.path.realpath(runtime) != os.path.realpath(sibling)):
                out.append(f(WARN,
                             f'cerebro "{target}": paths.local.json lo redirige a otra ruta',
                             f"runtime usa {runtime} pero existe la carpeta hermana real "
                             f"{sibling} — el launcher y el picker leen el override "
                             f"(las sesiones del cerebro real no aparecen)",
                             f'apunta brains.{name} a "{sibling}" o elimina esa clave en '
                             f"{dispatch._paths_local()}"))
        except Exception:
            pass
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 3 · Repos al día (detrás de origin → pull --ff-only)
# ══════════════════════════════════════════════════════════════════════════
def _repo_state(path):
    """('ok'|'behind'|'no-remote'|'no-upstream'|'offline', behind, ahead, dirty)"""
    rc, remotes, _ = _run(["git", "-C", path, "remote"], timeout=10)
    if rc != 0 or not remotes:
        return "no-remote", 0, 0, False
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


def phase_updated(ctx, fix):
    out = []
    repos = [("WORKSPACE", ROOT, "git")] + \
            [(f"cerebro {n}", b, dispatch.brain_transport(n, b)) for n, b in _resolved_brains(ctx)]
    for label, path, transport in repos:
        if path != ROOT and _in_repo(path):
            # cerebro in-repo: ya se actualiza con WORKSPACE (misma linea de arriba).
            # Decir "Obsidian Sync" aqui seria mentira.
            out.append(f(OK, f"{label}: viaja dentro de WORKSPACE — "
                            "se actualiza con el harness", path))
            continue
        if transport == "obsidian-sync":
            # canal sano y DEFAULT de los cerebros: Obsidian Sync se encarga
            # (sync en segundos) — git no aplica, aunque exista un .git vestigial.
            out.append(f(OK, f"{label}: sincroniza por Obsidian Sync — git no aplica", path))
            continue
        if not _is_git(path):
            out.append(f(WARN, f"{label}: transport git pero no es repo git", path,
                         "sin git no hay actualizaciones automáticas — re-clónalo con git "
                         "o, si es un cerebro, quita el "
                         f"override de transport en {dispatch._paths_local()} para volver "
                         "al default (Obsidian Sync)"))
            continue
        state, behind, ahead, dirty = _repo_state(path)
        extra = (f" · {ahead} commit(s) locales por subir" if ahead else "") + \
                (" · cambios locales sin commitear" if dirty else "")
        if state == "ok":
            out.append(f(OK, f"{label} al día con origin", (extra.strip(" ·") or "")))
        elif state == "no-remote":
            out.append(f(WARN, f"{label}: sin remote configurado", path,
                         "agrega el remote (git remote add origin <url>) para recibir updates"))
        elif state == "no-upstream":
            # la rama ACTUAL (stable para el equipo, main para quien desarrolla) — nunca hardcodear main
            _, br, _ = _run(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
            out.append(f(WARN, f"{label}: la rama no rastrea a origin", path,
                         f'corre: git -C "{path}" branch --set-upstream-to=origin/{br or "main"}'))
        elif state == "offline":
            out.append(f(WARN, f"{label}: no se pudo consultar origin",
                         "¿offline o sin acceso al repo?",
                         "verifica conexión / credenciales (gh auth login) y reintenta"))
        else:  # behind
            if not fix:
                out.append(f(FAIL, f"{label}: {behind} commit(s) detrás de origin", extra.strip(" ·"),
                             f'actualízalo: git -C "{path}" pull --ff-only  (o `workspace doctor`)'))
            elif dirty:
                out.append(f(WARN, f"{label}: {behind} detrás, pero hay cambios locales",
                             "no jalo encima de trabajo sin commitear",
                             f"commitea o guarda los cambios y corre: git -C \"{path}\" pull --ff-only"))
            else:
                rc, o, e = _run(["git", "-C", path, "pull", "--ff-only"], timeout=60)
                if rc == 0:
                    out.append(f(FIXED, f"{label} actualizado", f"{behind} commit(s) jalados"))
                else:
                    out.append(f(FAIL, f"{label}: el pull falló", (e or o).splitlines()[-1] if (e or o) else "",
                                 f"resuélvelo a mano: git -C \"{path}\" pull --ff-only"))
    # canal del equipo: los socios (no-max) viven en `stable` con upstream rastreado.
    # ⚠ informativo a propósito (una máquina puede estar en una rama de trabajo adrede).
    socio = _get_socio(ctx, fix=False)
    if socio and socio != "max" and _is_git(ROOT) and not _is_dist_install():
        _, br, _ = _run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
        rc_u, _, _ = _run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "@{upstream}"], timeout=10)
        if br == "stable" and rc_u == 0:
            out.append(f(OK, "canal del equipo", "WORKSPACE en `stable` · upstream rastreado"))
        else:
            why = []
            if br != "stable":
                why.append(f"rama actual: {br or '?'} (el equipo vive en stable)")
            if rc_u != 0:
                why.append("la rama no rastrea a origin")
            out.append(f(WARN, "WORKSPACE fuera del canal del equipo", " · ".join(why),
                         f'para volver al canal: git -C "{ROOT}" checkout stable — '
                         f'o si la rama es intencional, fija upstream: '
                         f'git -C "{ROOT}" branch --set-upstream-to=origin/{br or "stable"}'))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 4 · Cerebros resolubles (la lógica REAL de dispatch.resolve_brain)
# ══════════════════════════════════════════════════════════════════════════
def phase_brains(ctx, fix):
    out = []
    discovered = {}
    for a in ctx["agents"]:
        name = a["name"]
        a["brain"] = dispatch.resolve_brain(name, a["cfg"])   # re-resuelve (fase 2 pudo cambiar algo)
        if a["brain"] and os.path.isdir(a["brain"]):
            out.append(f(OK, f"{name} → {a['brain']}"))
            continue
        if not fix:
            out.append(f(FAIL, f"dispatch no resuelve el cerebro de {name}",
                         a["brain"] or "(sin definir)",
                         f"clona la carpeta con el nombre exacto (fase 2) o declárala en "
                         f"{dispatch._paths_local()}"))
            continue
        # FIX: usar el detector del instalador (Obsidian, spots comunes, prompt)
        brain, persist = install.find_brain(name, a["cfg"])
        if brain and os.path.isdir(brain):
            a["brain"] = brain
            if persist:
                discovered[name] = brain
            out.append(f(FIXED, f"{name} → {brain}", "detectado y registrado"))
        else:
            out.append(f(FAIL, f"no encontré el cerebro de {name}", "",
                         f"clónalo (fase 2) o declara la ruta en {dispatch._paths_local()}  →  "
                         f"{{\"brains\": {{\"{name}\": \"/ruta\"}}}}"))
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
            out.append(f(OK, f"[{name}] sesiones (resume) en el path esperado",
                         f"{n} sesión(es) · {os.path.basename(sdir)}"))
            continue
        cands = session_paths.mismatch_candidates(brain)
        if cands:
            out.append(f(WARN, f"[{name}] resume no funcionará: el path calculado "
                               "no coincide con el real",
                         f"calculado: {os.path.basename(sdir)} · "
                         f"Claude Code guarda en: {os.path.basename(cands[0])}",
                         f"hay un symlink u otra codificación en la ruta del cerebro — "
                         f"revisa `ls -l` sobre los componentes de \"{brain}\", declara la "
                         f"ruta REAL (sin symlinks) en {dispatch._paths_local()} y "
                         + _report_hint()))
        else:
            out.append(f(OK, f"[{name}] sesiones (resume)",
                         "sin sesiones aún — la carpeta se crea al primer arranque"))
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
        return [f(WARN, "sin cerebros resueltos", "nada que cablear", "resuelve la fase 4 primero")]
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
            out.append(f(FAIL, f"[{name}] settings.local.json ilegible (JSON corrupto)",
                         "el doctor NO lo reescribe: pisarlo descartaría "
                         "permissions/env/mcpServers en silencio",
                         f"revisa/respalda {sp} y bórralo o restáuralo; "
                         f"luego corre `python3 install.py`"))
        elif not broken:
            detail = ("skill_review + transcript_backup + memory_flush + session_start/end"
                      if setup["session_journal"]
                      else "skill_review + transcript_backup + memory_flush · setup ligero — "
                           "sin journaling (por diseño)")
            out.append(f(OK, f"[{name}] hooks cableados", detail))
        elif not fix:
            falta = ", ".join(crit + minor +
                              ([] if sline_ok else ["statusLine (ruta vieja)"]) +
                              ([f"intérprete horneado roto/frágil: {py_bad[0]}"] if py_bad else [])) \
                    or "settings.local.json no existe"
            st = FAIL if (crit or not os.path.exists(sp)) else WARN
            out.append(f(st, f"[{name}] hooks incompletos o con ruta vieja", f"falta: {falta}",
                         "corre `workspace doctor` (reescribe SOLO hooks/statusLine"
                         + (" con el intérprete estable" if py_bad else "") + ")"))
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
            out.append(f(FIXED, f"[{name}] bloque hooks escrito",
                         "solo `hooks`" + ("" if not redo_sline else " + `statusLine`")
                         + " — el resto del archivo se respeta"))
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
                out.append(f(FIXED, f"[{name}] .gitignore completado", ", ".join(missing_gi)))
            else:
                out.append(f(WARN, f"[{name}] .gitignore no excluye estado per-máquina",
                             ", ".join(missing_gi), "corre `workspace doctor`"))
        # modo autónomo: el doctor NO lo escribe (hard-block del clasificador) → manual.
        # Solo se menciona si el agente lo quiere (setup.autonomous) y SIEMPRE como
        # acción manual del socio (⚠ informativo), nunca ✗.
        if setup["autonomous"] and settings and \
                settings.get("permissions", {}).get("defaultMode") != "dontAsk":
            out.append(f(WARN, f"[{name}] modo autónomo no activo (permissions)",
                         "el doctor no escribe `permissions` (bloqueado por seguridad)",
                         f"ACCIÓN MANUAL: copia el bloque \"permissions\" desde el "
                         f"settings.local.json de un cerebro ya configurado (p. ej. MI - BRAIN) "
                         f"a {sp} — o corre `python3 install.py` tú mismo"))
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
        return [f(WARN, "sin cerebros resueltos", "nada que materializar",
                  "resuelve la fase 4 primero")]
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
            out.append(f(FAIL, f"[{name}] settings.local.json ilegible (JSON corrupto)",
                         "el doctor NO materializa MCPs sobre un archivo corrupto: "
                         "pisarlo descartaría permissions/env/mcpServers en silencio",
                         f"revisa/respalda {sp} y bórralo o restáuralo; "
                         f"luego corre `python3 install.py`"))
            continue
        settings = _read_json(sp)
        drift, n_scope, channel, reason = _mcps_drift(a["cfg"], brain, settings)
        if channel != "claude-code":
            # motor sin proyector real (codex/gemini/local/API): honesto, no ✗.
            # Solo se menciona si HAY MCP en scope que no se están enchufando.
            if n_scope:
                out.append(f(WARN, f"[{name}] {n_scope} MCP(s) en scope sin materializar",
                             reason))
            else:
                out.append(f(OK, f"[{name}] sin MCPs para este motor",
                             reason or channel or "motor sin canal MCP"))
            continue
        if not drift:
            out.append(f(OK, f"[{name}] MCPs materializados",
                         f"{n_scope} server(s) en `mcpServers`" if n_scope
                         else "sin MCPs en scope"))
        elif not fix:
            out.append(f(WARN, f"[{name}] MCPs desincronizados (store ↔ mcpServers)",
                         f"{n_scope} server(s) en scope no reflejados en settings.local.json",
                         "corre `workspace doctor` (reescribe SOLO `mcpServers`)"))
        else:
            # P0-3: el RMW lo hace render_mcps_only (fuente única que comparten
            # doctor/CLI) — muta `settings` sin escribir; el write_json de abajo
            # persiste SOLO el bloque mcpServers, el resto del archivo se respeta.
            install.render_mcps_only(a["cfg"], brain, settings=settings)
            install.write_json(sp, settings)
            out.append(f(FIXED, f"[{name}] bloque mcpServers materializado",
                         f"{n_scope} server(s) — solo `mcpServers`, "
                         f"el resto del archivo se respeta"))
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
            out.append(f(OK, "comandos PowerShell instalados", ps1))
        elif fix:
            install.launchers_windows(names)
            out.append(f(FIXED, "comandos PowerShell reescritos",
                         f"{', '.join(['workspace', 'workspace'] + names)} · abre una PowerShell nueva"))
        elif missing or not prof_ok:
            out.append(f(FAIL, "launchers de Windows incompletos",
                         f"faltan: {', '.join(missing) or 'dot-source en $PROFILE'}",
                         "corre `workspace doctor` o `python install.py`"))
        else:
            det = []
            if stale:
                det.append(f"intérprete horneado ya no existe: {stale[0]}")
            if fragile:
                det.append("intérprete = python VERSIONADO de la Store (se rompe al actualizar)")
            if dup:
                det.append("workspace-cmds.ps1 dot-sourceado más de una vez en $PROFILE")
            out.append(f(WARN, "launchers de Windows por endurecer", " · ".join(det),
                         f"corre `workspace doctor` — reescribe launchers con el intérprete "
                         f"estable ({want}) y deduplica el $PROFILE"))
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
            out.append(f(FIXED, "launchers reinstalados", ", ".join(broken)))
        else:
            out.append(f(FAIL, "launchers faltantes o apuntando a otra ruta",
                         ", ".join(broken), "corre `workspace doctor` o `python3 install.py`"))
    if bindir not in os.environ.get("PATH", "").split(os.pathsep):
        out.append(f(WARN, "~/.local/bin no está en tu PATH",
                     "los comandos existen pero la terminal no los ve",
                     'ACCIÓN MANUAL: agrega a tu ~/.zshrc:  export PATH="$HOME/.local/bin:$PATH"  '
                     "y abre una terminal nueva"))
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
        rc_label = "$PROFILE de PowerShell"
    else:
        rc = os.path.join(HOME, ".zshrc")
        has = False
        try:
            has = install.GREETER_MARK in open(rc, encoding="utf-8").read()
        except Exception:
            pass
        rc_label = "~/.zshrc"
    if has:
        out.append(f(OK, "greeter configurado", f"menú WORKSPACE al abrir terminal ({rc_label})"))
    elif fix:
        install.install_greeter()
        out.append(f(FIXED, "greeter al día", rc_label))
    elif outdated:
        out.append(f(WARN, "greeter desactualizado (bloque viejo)",
                     "sin guard de interactividad/Windows Terminal ni reset de colores",
                     "corre `workspace doctor` (reemplaza el bloque por la versión actual)"))
    else:
        out.append(f(WARN, "greeter no configurado", f"sin menú al abrir terminal ({rc_label})",
                     "corre `workspace doctor` (es opt-out: WORKSPACE_NO_GREETER=1)"))
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
            out.append(f(OK, f"[{name}] socio.local no requerido",
                         "setup ligero · sin journaling (por diseño)"))
        elif fix:
            s = _get_socio(ctx, fix=True) or "max"
            install.write_text(sl, s)
            out.append(f(FIXED, f"[{name}] socio.local escrito", s))
        else:
            # ⚠ (no ✗): lo resuelve `workspace doctor` (fix) solo → es "por terminar", no una falla.
            out.append(f(WARN, f"[{name}] socio.local por configurar", cur or "(no existe)",
                         f"corre `workspace doctor` (preguntará quién eres)"
                         + (f" — detectado en otro cerebro: {socio}" if socio else "")))
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
        out.append(f(OK, "socio.local per-máquina (chat)", cur))
    elif fix:
        s = _get_socio(ctx, fix=True) or "max"
        install.write_machine_socio(s)
        out.append(f(FIXED, "socio.local per-máquina escrito", s))
    else:
        out.append(f(WARN, "socio.local per-máquina por configurar",
                     cur or "(no existe)",
                     "corre `workspace doctor` — sin él, el chat del menú puede "
                     "firmar como $USER en vez del socio"))
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
        out.append(f(OK, "retención de transcripts", f"cleanupPeriodDays={int(cur)}"))
    elif fix:
        install.ensure_cleanup_days()
        out.append(f(FIXED, "retención de transcripts asegurada",
                     f"cleanupPeriodDays={install.CLEANUP_DAYS} en ~/.claude/settings.json"))
    else:
        out.append(f(WARN, "transcripts se borran a los 30 días (default)",
                     f"cleanupPeriodDays actual: {cur if cur is not None else '(sin definir)'}",
                     f"corre `workspace doctor` — fija cleanupPeriodDays={install.CLEANUP_DAYS} "
                     "en ~/.claude/settings.json (no pisa nada más)"))
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
DOCTOR_STATE = os.path.join(HOME, ".claude", "workspace", "doctor-state.json")
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
        return [f(WARN, "sin cerebros resueltos", "nada que medir", "resuelve la fase 4 primero")]
    socio = _get_socio(ctx, fix=False)
    state = _read_json(DOCTOR_STATE)
    hashes = state.setdefault("boot_hash", {})
    dirty = False
    for name, brain in brains:
        # — Y8 · presupuesto de boot —
        sizes = [(rel, _read_len(p)) for rel, p in _boot_files(brain, socio)]
        sizes = [(rel, n) for rel, n in sizes if n >= 0]
        total = sum(n for _, n in sizes)
        top = max(sizes, key=lambda x: x[1]) if sizes else ("(nada)", 0)
        det = (f"{total:,} chars (~{total / CHARS_PER_TOKEN / 1000:.1f}k tokens) "
               f"en {len(sizes)} archivos · mayor: {top[0]} ({top[1]:,})")
        if total > BOOT_BUDGET_TOTAL:
            out.append(f(WARN, f"[{name}] boot sobre presupuesto total "
                               f"(>{BOOT_BUDGET_TOTAL // 1000}k chars)", det,
                         f"adelgaza el boot empezando por {top[0]}: lo volátil se rota "
                         f"a archivo histórico (p. ej. STATE/log-archive/), lo curado "
                         f"se destila — cada char se paga en TODOS los arranques (Y14)"))
        else:
            out.append(f(OK, f"[{name}] presupuesto de boot", det))
        fat = [(rel, n) for rel, n in sizes if n > BOOT_BUDGET_FILE]
        if fat:
            out.append(f(WARN, f"[{name}] archivo(s) de boot sobre presupuesto "
                               f"(>{BOOT_BUDGET_FILE // 1000}k chars c/u)",
                         ", ".join(f"{rel} ({n:,})" for rel, n in fat),
                         "rota o destila cada offender: log-recent → archivar entradas "
                         "viejas a STATE/log-archive/ (convención Y14); MEMORY/PENDIENTES/"
                         "CLAUDE.md → destilar (mover detalle a wiki/ y dejar punteros)"))
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
                out.append(f(WARN, f"[{name}] MEMORY.md ilegible para medir "
                                   f"core blocks (N13)", mem_path,
                             "revisa permisos/encoding del archivo"))
            elif not mm["has_blocks"]:
                out.append(f(OK, f"[{name}] MEMORY.md sin core blocks (N13)",
                             f"{mm['total']:,} chars sin estructurar",
                             "opcional: etiquetar headings `## [bloque] Título` "
                             "(convención en memory_blocks.py) — migración "
                             "humana, el harness solo mide"))
            else:
                over = memory_blocks.overflowing(mm)
                det = " · ".join(f"[{lb}] {b['chars']:,}/{b['limit']:,}"
                                 for lb, b in mm["blocks"].items())
                if over:
                    out.append(f(WARN, f"[{name}] core block(s) de MEMORY.md "
                                       f"sobre su cota (N13)",
                                 ", ".join(f"[{lb}] +{b['excess']:,} chars"
                                           for lb, b in over) + f" · {det}",
                                 "destila/archiva el excedente menos relevante a "
                                 "STATE/memoria-archivo/ (humano o Atlas con gate "
                                 "— el pipeline JAMÁS edita MEMORY.md); detalle: "
                                 f"python3 memory_blocks.py --brain \"{brain}\""))
                else:
                    out.append(f(OK, f"[{name}] core blocks de MEMORY.md "
                                     f"dentro de cota", det))
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
                                 f"[{name}] STATE/INDEX.md sobre tope (≥100 líneas útiles)",
                                 f"~{idx_lines} entradas útiles",
                                 "consolidar INDEX.md: fusionar/archivar entradas muertas — "
                                 "el consolidador (nightly) puede añadir nuevas; "
                                 "el humano archiva las que ya no aplican "
                                 f"(python3 migrate_memory_v1.py --brain \"{brain}\" --apply)"))
                else:
                    out.append(f(OK, f"[{name}] STATE/INDEX.md dentro de tope",
                                 f"~{idx_lines} entradas útiles de máx 100"))
            except Exception:
                out.append(f(WARN, f"[{name}] STATE/INDEX.md ilegible",
                             index_path, "revisa permisos/encoding"))
        else:
            out.append(f(WARN, f"[{name}] STATE/INDEX.md no existe (E2)",
                         "contrato de retrieval por capas ausente",
                         "crear con: python3 migrate_memory_v1.py "
                         f"--brain \"{brain}\" --apply --stage 2 "
                         "(o dry-run primero sin --apply)"))

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
                                 f"[{name}] STATE/log-recent.md sobre cap "
                                 f"(>{_log_cap // 1000}k chars)",
                                 f"{lr_len:,} chars · cap {_log_cap:,}",
                                 "rotar el excedente al archivo histórico: "
                                 f"python3 nightly.py --brain \"{brain}\" --rotate-logs "
                                 "(es seguro y atómico; NUNCA toca BOOT/MEMORY)"))
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
            out.append(f(WARN, f"[{name}] BOOT/ sin archivos de identidad", brain,
                         "el cerebro no tiene BOOT/*.md — revisa que el clon esté completo "
                         "(fase 2) o " + _report_hint()))
        elif prev is None:
            if fix:
                hashes[name] = cur
                dirty = True
                out.append(f(OK, f"[{name}] identidad (BOOT/): huella registrada",
                             f"baseline · {len(cur)} archivos"))
            else:
                out.append(f(OK, f"[{name}] identidad (BOOT/): sin huella aún",
                             "se registra al correr `workspace doctor` (sin --check)"))
        elif prev == cur:
            out.append(f(OK, f"[{name}] identidad (BOOT/) sin cambios desde el último doctor",
                         f"{len(cur)} archivos"))
        else:
            diff = []
            for k in sorted(set(prev) | set(cur)):
                if k not in cur:
                    diff.append(f"{k} (eliminado)")
                elif k not in prev:
                    diff.append(f"{k} (nuevo)")
                elif prev[k] != cur[k]:
                    diff.append(k)
            if fix:
                hashes[name] = cur
                dirty = True
            out.append(f(WARN, f"[{name}] la identidad cambió desde el último doctor",
                         ", ".join(diff),
                         f"¿fue intencional? BOOT/ es territorio N3 (consenso de los 3 "
                         f"socios) — revisa: git -C \"{brain}\" log --oneline -- BOOT/"
                         + ("  · huella re-registrada: este aviso no se repetirá" if fix
                            else "  · si fue legítimo, corre `workspace doctor` para "
                                 "re-registrar la huella")))
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
        return [f(WARN, "sin cerebros resueltos", "nada que medir",
                  "resuelve la fase 4 primero")]
    socio = _get_socio(ctx, fix=False)
    for name, brain in brains:
        # — superficie HOT real (boot + session del manifiesto) —
        try:
            m = brain_vitals.measure_hot(brain, socio)
        except Exception as e:
            out.append(f(WARN, f"[{name}] signos vitales ilegibles", str(e),
                         "revisa permisos del cerebro"))
            continue
        top = sorted(m["boot"] + m["session"], key=lambda x: -x[1])[:3]
        det = (f"~{m['total_chars'] // brain_vitals.CHARS_PER_TOKEN / 1000:.1f}k tok "
               f"(boot {brain_vitals.tokens_k(m['boot_chars'])} + sesión "
               f"{brain_vitals.tokens_k(m['session_chars'])}) · mayor: "
               + ", ".join(f"{rel} ({brain_vitals.tokens_k(n)})" for rel, n in top))
        if m["total_chars"] > brain_vitals.HOT_BUDGET_TOTAL:
            offender = top[0][0] if top else "(nada)"
            out.append(f(WARN, f"[{name}] superficie HOT sobre presupuesto "
                               f"(>{brain_vitals.HOT_BUDGET_TOTAL // 1000}k chars "
                               f"≈ {brain_vitals.tokens_k(brain_vitals.HOT_BUDGET_TOTAL)})",
                         det,
                         f"cada char se paga en CADA sesión — destilar/partir es "
                         f"decisión HUMANA del socio dueño (empezar por {offender}); "
                         f"detalle: python3 brain_vitals.py --brain \"{brain}\""))
        else:
            out.append(f(OK, f"[{name}] superficie HOT dentro de presupuesto", det))
        if not m["manifest"]:
            out.append(f(OK, f"[{name}] sin STATE/hot-manifest.md — solo se "
                             f"midió el boot",
                         "las superficies session-time (índices retrieveados) "
                         "no se ven sin manifiesto",
                         "declara lo que ese cerebro carga por sesión en "
                         "STATE/hot-manifest.md (formato: templates/agent/"
                         "brain/STATE/hot-manifest.md)"))
        if m["missing"]:
            out.append(f(WARN, f"[{name}] manifiesto HOT declara archivos "
                               f"inexistentes", ", ".join(m["missing"]),
                         "corrige o retira esas líneas de STATE/hot-manifest.md"))
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
            out.append(f(WARN, f"[{name}] junk en el cerebro "
                               f"({len(junk)} hallazgo(s) — disco/sync, NO tokens)",
                         shown + (f" · +{more} más" if more > 0 else ""),
                         brain_vitals.SYNC_HINT + "; regenerables → cuarentena "
                         "opt-in: python3 brain_cleanup.py --brain "
                         f"\"{brain}\" (dry-run; N3 — decisión del socio dueño)"))
        else:
            out.append(f(OK, f"[{name}] sin junk detectado",
                         "node_modules/dist/caches/.bak/binarios grandes: nada"))
    # — stubs de path-pollution (hermanos duplicados del cerebro) —
    try:
        stubs = brain_vitals.detect_stubs(brains)
    except Exception:
        stubs = []
    for s in stubs:
        out.append(f(WARN, "stub de path-pollution junto a un cerebro",
                     f"{s['stub']} duplica {s['brain']}",
                     "alguna sesión escribió a un path mal resuelto — revisar "
                     "contenido, fusionar A MANO y retirar el stub (y "
                     "paths.local.json si apunta ahí)"))
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
        return [f(WARN, "sin cerebros resueltos", "nada que escanear",
                  "resuelve la fase 4 primero")]
    for name, brain in brains:
        try:
            findings, nfiles = secret_scan.scan_brain(brain)
        except Exception as e:   # falla-suave: el escáner jamás tumba al doctor
            out.append(f(WARN, f"[{name}] el secret-scan falló",
                         f"{type(e).__name__}: {e}",
                         _report_hint()))
            continue
        if not findings:
            out.append(f(OK, f"[{name}] sin secretos detectables en el working tree",
                         f"{nfiles} archivo(s) escaneados · "
                         f"{len(secret_scan.PATTERNS)} clases de credencial · "
                         f"historia git no escaneada (audit manual: --history)"))
            continue
        shown = findings[:MAX_SECRET_FINDINGS_SHOWN]
        det = " · ".join(f"{x['path']}:{x['line']} [{x['class']}] {x['excerpt']}"
                         for x in shown)
        if len(findings) > len(shown):
            det += f" · (+{len(findings) - len(shown)} más)"
        out.append(f(WARN, f"[{name}] posible(s) secreto(s) rumbo a git "
                          f"({len(findings)})", det,
                     "NO lo commitees: mueve la clave a una variable de entorno "
                     "o a un archivo en .gitignore — y si ya se commiteó alguna "
                     "vez, RÓTALA (git guarda historia). ¿Falso positivo? marca "
                     f"la línea con `{secret_scan.ALLOW_MARKER}`. Chequeo manual "
                     f"pre-commit (opt-in): python3 "
                     f"\"{os.path.join(ROOT, 'secret_scan.py')}\" --staged"
                     f" · Auditar historia git (WARN-only): python3 "
                     f"\"{os.path.join(ROOT, 'secret_scan.py')}\" --history \"{brain}\""))
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
        return [f(OK, "sin cerebros resueltos", "nada que evaluar")]
    for name, brain in brains:
        try:
            results = skill_meta.scan_catalog(brain)
        except Exception as e:   # falla-suave: el gating jamás tumba al doctor
            out.append(f(WARN, f"[{name}] el escaneo de gating falló",
                         f"{type(e).__name__}: {e}",
                         _report_hint()))
            continue
        if not results:
            out.append(f(OK, f"[{name}] sin skills que evaluar",
                         "no hay skills/ con archivos de instrucciones"))
            continue
        declared = [r for r in results if r["requires"]]
        hidden = [r for r in results if not r["available"]]
        if not hidden:
            out.append(f(OK, f"[{name}] catálogo completo disponible en esta "
                             f"máquina",
                         f"{len(results)} skill(s) · {len(declared)} declaran "
                         f"`requires:` y todas se satisfacen aquí"))
            continue
        shown = hidden[:MAX_HIDDEN_SKILLS_SHOWN]
        det = " · ".join(f"{r['name']} (falta {', '.join(r['missing'])})"
                         for r in shown)
        if len(hidden) > len(shown):
            det += f" · (+{len(hidden) - len(shown)} más)"
        out.append(f(OK, f"[{name}] {len(hidden)} skill(s) auto-oculta(s) en "
                        f"esta máquina — por diseño (N11)", det,
                     "informativo: la skill se omite del catálogo efectivo "
                     "aquí, el archivo queda intacto. Instala lo que falta "
                     "SOLO si la necesitas en esta máquina. Detalle: "
                     f"python3 \"{os.path.join(ROOT, 'skill_meta.py')}\" "
                     f"\"{brain}\" --hidden"))
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
            why = ("su agent.json no define scripts.banner"
                   if not declared.get("banner")
                   else f"scripts.banner ({declared['banner']}) resuelve fuera "
                        "del cerebro/harness y se descartó")
            out.append(f(WARN, f"[{name}] sin banner resoluble", why,
                         "declara scripts.banner = {root}/agents/<n>/brand/<n>-banner.py"))
            continue
        missing = [k for k in ("banner", "dashboard", "statusline")
                   if scripts.get(k) and not os.path.exists(scripts[k])]
        if missing:
            out.append(f(WARN, f"[{name}] brand incompleto",
                         "falta(n): " + " · ".join(f"{k}→{scripts[k]}" for k in missing),
                         "verifica que los scripts existan en {root}/agents/<n>/brand/"))
        else:
            # Canónico v2.3: viven en el harness ({root}); el cerebro como fallback
            # de compatibilidad sigue siendo válido. Lo que cuenta es que EXISTAN.
            from_brain = scripts["banner"].startswith(os.path.realpath(brain))
            origen = "el cerebro" if from_brain else "WORKSPACE"
            out.append(f(OK, f"[{name}] brand completo desde {origen}",
                         "banner+dashboard+statusline resueltos y existentes"))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  FASE 5d · Residuos del rename OLYMPUS→WORKSPACE (anti-recurrencia)
# ══════════════════════════════════════════════════════════════════════════
# Tras el rename OLYMPUS→WORKSPACE quedaron vestigios PER-MÁQUINA que rompen el
# brand de un agente sin tocar el distro: (a) scripts de marca brain-resident de
# generación vieja que resuelven la raíz con OLYMPUS_ROOT / ~/Desktop/OLYMPUS /
# ~/.claude/olympus (env/rutas muertas → menú/statusline truenan y filtran
# "OLYMPUS"); (b) entradas en agents.local.json con `brain` bajo ~/.claude/olympus
# (puntero stale); (c) carpetas `.olympus/` sobrantes en los cerebros (el harness
# lee SOLO `.workspace/` → config_engine). Reparación conservadora:
#   · (b) es config del HARNESS per-máquina → auto-repara en --fix (repunta a la
#     ruta equivalente bajo ~/.claude/workspace si existe; si no, WARN).
#   · (c) es metadata MUERTA del harness en el cerebro → auto-borra en --fix SOLO
#     si `.workspace/agent.json` ya existe (la fuente viva); si no, WARN.
#   · (a) toca scripts que PORTAN identidad (paleta/scope) → SOLO detecta+WARN;
#     regenerarlos desde templates/agent/workspace/brand/ es trabajo de dev, no
#     algo que el doctor deba inventar. Fail-soft total: jamás tumba el doctor.
_OLYMPUS_DEAD_REFS = ("OLYMPUS_ROOT", "OLYMPUS_BRAIN", "~/Desktop/OLYMPUS",
                      "Desktop/OLYMPUS", ".claude/olympus")


def _scan_brand_olympus(brain):
    """[nombres] de scripts en {brain}/brand/*.py que referencian env/rutas muertas
    de OLYMPUS (las que rompen la resolución de raíz). Solo lectura, fail-soft."""
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
        if any(ref in txt for ref in _OLYMPUS_DEAD_REFS):
            hits.append(n)
    return hits


def phase_olympus_residue(ctx, fix):
    out = []
    # (b) agents.local.json: punteros bajo ~/.claude/olympus (config del harness)
    dead = os.path.join(os.path.expanduser("~"), ".claude", "olympus") + os.sep
    live_root = os.path.join(os.path.expanduser("~"), ".claude", "workspace")
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
                out.append(f(FIXED, "agents.local.json repuntado fuera de ~/.claude/olympus",
                             " · ".join(repaired)))
            for u in unresolved:
                out.append(f(WARN, "agents.local.json apunta bajo ~/.claude/olympus", u,
                             "repunta `brain` a la ubicación real bajo ~/.claude/workspace "
                             "(o quita la entrada si ese agente ya no existe)"))
        else:
            out.append(f(OK, "agents.local.json sin punteros a ~/.claude/olympus",
                         "ninguna entrada bajo la ruta vieja"))
    except Exception as e:
        out.append(f(OK, "agents.local.json no evaluable",
                     "%s: %s — señal omitida (fail-soft)" % (type(e).__name__, e)))
    # (a)/(c) por cerebro resuelto
    for name, brain in _resolved_brains(ctx):
        hits = _scan_brand_olympus(brain)
        if hits:
            out.append(f(WARN, "[%s] marca brain-resident con refs muertas de OLYMPUS" % name,
                         "brand/: " + ", ".join(hits),
                         "regenera desde templates/agent/workspace/brand/ (usan "
                         "WORKSPACE_ROOT y degradan con gracia); sustituye "
                         "OLYMPUS_ROOT/OLYMPUS_BRAIN/~/Desktop/OLYMPUS/~/.claude/olympus"))
        legacy = os.path.join(brain, ".olympus")
        if os.path.isdir(legacy):
            has_ws = os.path.isfile(os.path.join(brain, ".workspace", "agent.json"))
            if fix and has_ws:
                try:
                    shutil.rmtree(legacy)
                    out.append(f(FIXED, "[%s] .olympus/ sobrante eliminado" % name,
                                 "el harness lee solo .workspace/ (metadata muerta)"))
                except OSError as e:
                    out.append(f(WARN, "[%s] no se pudo borrar .olympus/" % name, str(e),
                                 "bórralo a mano: rm -rf \"%s\"" % legacy))
            elif has_ws:
                out.append(f(WARN, "[%s] .olympus/ sobrante en el cerebro" % name,
                             "el harness lee solo .workspace/ (está muerto)",
                             "workspace doctor --fix lo borra (o: rm -rf \"%s\")" % legacy))
            else:
                out.append(f(WARN, "[%s] .olympus/ sin .workspace/agent.json" % name,
                             "NO borrar aún — puede tener la única definición",
                             "migra .olympus/agent.json a .workspace/agent.json y luego borra .olympus/"))
        if not hits and not os.path.isdir(legacy):
            out.append(f(OK, "[%s] sin residuos de OLYMPUS" % name,
                         "marca brain-resident limpia · sin .olympus/"))
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
            out.append(f(WARN, "estado colgante detectado",
                         str(w).lstrip("⚠").strip(),
                         "rescata el trabajo (commit en su rama) o descarta el "
                         "worktree — el registry vive en ~/.claude/workspace/"
                         "worktree-owners.json"))
        if not out:
            out.append(f(OK, "sin estado colgante",
                         "registry de worktrees limpio (dash.dev.liveness)"))
    except Exception as e:
        # informativo: liveness roto/ausente no es un problema del harness
        out.append(f(OK, "liveness no evaluable",
                     f"{type(e).__name__}: {e} — señal omitida (fail-soft)"))
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
    if sys.platform != "darwin":
        return [f(OK, "voz (dictado)", "F1 es solo macOS — Windows/Linux en F3")]
    try:
        import voice
    except Exception as e:
        return [f(WARN, "voz no evaluable", "%s: %s" % (type(e).__name__, e))]
    out = []
    brew = shutil.which("brew")
    setup = fix and os.environ.get(VOICE_SETUP_ENV) == "1"
    # whisper.cpp
    if voice._find_whisper():
        out.append(f(OK, "whisper.cpp", "instalado (dictado local disponible)"))
    else:
        if setup and brew:
            _run(["brew", "install", "whisper-cpp"], timeout=600)
        out.append(f(OK if voice._find_whisper() else WARN, "whisper.cpp",
                     "STT local del dictado por voz (opcional)",
                     "brew install whisper-cpp — o todo junto: "
                     f"{VOICE_SETUP_ENV}=1 workspace doctor"))
    # modelo
    model = voice.default_model()
    if os.path.isfile(model):
        out.append(f(OK, "modelo de whisper", os.path.basename(model)))
    else:
        if setup:
            _download_whisper_model(model)
        out.append(f(OK if os.path.isfile(model) else WARN, "modelo de whisper",
                     "falta %s (~150MB)" % os.path.basename(model),
                     f"{VOICE_SETUP_ENV}=1 workspace doctor lo baja, o descarga "
                     "ggml-base.bin a " + os.path.dirname(model)))
    # grabador
    tool, _ = voice._recorder_cmd("x.wav")
    if tool:
        out.append(f(OK, "grabador de micro", tool))
    else:
        if setup and brew:
            _run(["brew", "install", "ffmpeg"], timeout=600)
        tool2, _ = voice._recorder_cmd("x.wav")
        out.append(f(OK if tool2 else WARN, "grabador de micro",
                     "ffmpeg o sox para capturar el audio", "brew install ffmpeg"))
    # guía del atajo + permisos (siempre informativo)
    out.append(f(OK, "atajo + permisos",
                 "enlaza `workspace voice` a una tecla en Atajos de macOS; da permiso "
                 "de Micrófono y Accesibilidad (para pegar). `workspace voice --check` "
                 "reporta lo que falte"))
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


PHASES = [
    ("1 · Prerrequisitos (git · python · CLI de motores · gh)", phase_prereqs),
    ("1b · Rutas redirigidas (OneDrive/known-folders · solo detección)", phase_redirected_paths),
    ("2 · Repos hermanos (nombres exactos)", phase_siblings),
    ("3 · Repos al día con origin", phase_updated),
    ("4 · Cerebros resolubles (dispatch) · sesiones (resume)", phase_brains),
    ("5 · Hooks por cerebro (contrato de eventos N9 · events.py)", phase_hooks),
    ("5b · Brand por-agente (banner/dashboard/statusline resueltos y existentes)", phase_brand),
    ("5c · MCPs por cerebro (materialización · connectors.PORTABILITY)", phase_mcps),
    ("5d · Residuos del rename OLYMPUS→WORKSPACE (anti-recurrencia)", phase_olympus_residue),
    ("6 · Launchers (workspace + agentes)", phase_launchers),
    ("7 · Greeter · socio · tema · retención", phase_extras),
    ("8 · Cerebro: presupuesto de boot + identidad (BOOT/)", phase_brain_budget),
    ("8b · Cerebro: signos vitales — HOT real (manifiesto) + junk (solo mide)",
     phase_brain_vitals),
    ("9 · Secretos en cerebros (secret-scan N14 · WARN-only)", phase_secrets),
    ("10 · Skills por máquina (gating N11 · informativo)", phase_skill_gating),
    ("11 · Liveness (worktrees huérfanos · solo detección)", phase_liveness),
    ("12 · Voz global (dictado local whisper.cpp · macOS · opcional)", phase_voice),
]

HEAD = {OK: "✓ ya conectada", FIXED: "✓ reparada", WARN: "⚠ atención", FAIL: "✗ falta"}
HEADC = {OK: GRN, FIXED: C, WARN: YEL, FAIL: RED}


def _worst(finds):
    return max(finds, key=lambda x: RANK[x["status"]])["status"] if finds else OK


def _print_phase(title, finds, fix_mode):
    st = _worst(finds)
    print(f"\n  {BO}{WH}FASE {title}{R}   {HEADC[st]}{HEAD[st]}{R}")
    if fix_mode and st == OK:
        return st   # fase ya conectada → se salta el detalle
    for x in finds:
        line = f"      {SYM[x['status']]} {x['label']}"
        if x["detail"]:
            line += f"  {DIM}— {x['detail']}{R}"
        print(line)
        if x["action"]:
            print(f"        {YEL}→ acción:{R} {x['action']}")
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
    return os.path.join(HOME, ".claude", "workspace", "doctor-report.md")


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
        "# workspace doctor — pendientes por resolver",
        f"Generado: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        + (f" · modo: {mode}" if mode else "") + f" · WORKSPACE: {ROOT}",
        "",
        "Esta sesión la abrió `workspace doctor`: quedaron hallazgos sin resolver "
        "y el socio eligió resolverlos contigo. Tu ÚNICO objetivo aquí es guiarlo "
        "a arreglar/configurar estos puntos, uno por uno, conversando.",
        "Reglas: cambios mínimos y explicados antes de ejecutarlos; los fix-its "
        "de abajo son la sugerencia del doctor (síguelos salvo mejor razón); "
        "NO toques BOOT/ ni `permissions`; al terminar, sugiere re-correr "
        "`workspace doctor --check` para verificar.",
        "",
    ]
    for title, x in pending:
        sym = "✗" if x["status"] == FAIL else "⚠"
        lines.append(f"## [{sym}] FASE {title}")
        lines.append(f"- hallazgo: {x['label']}")
        if x["detail"]:
            lines.append(f"- detalle: {x['detail']}")
        if x["action"]:
            lines.append(f"- fix-it sugerido: {x['action']}")
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
            report += f"\n(Este reporte también quedó en {seed}.)"
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
        print(f"\n  {YEL}Quedan {len(pending)} punto(s) por resolver.{R}")
        print(f"  {DIM}[s] enviarlos a Zenith (abre una sesión temporal con el reporte)"
              f"   ·   [Enter] salir{R}")
        try:
            ans = input("  › ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if ans not in ("s", "si", "sí", "y", "yes"):
            return False
        print(f"  {DIM}Abriendo sesión de Zenith con el reporte…{R}")
        if launch_zenith_session(build_zenith_report(pending, mode="fix")):
            return True
        print(f"  {YEL}No pude abrir la sesión de Zenith{R} {DIM}— los hallazgos y sus "
              f"fix-its ya están arriba; resuélvelos a mano o corre `zenith` tú mismo.{R}")
        return False
    except Exception:
        return False   # falla-suave total: el cierre jamás rompe el doctor


def main(argv=None):
    args = list(argv) if argv is not None else sys.argv[1:]
    if "--tests" in args:
        # Suite N18 (tests/run.py): la red de edición del harness. Aditivo —
        # solo corre con el flag explícito; el doctor normal no la toca.
        runner = os.path.join(ROOT, "tests", "run.py")
        if not os.path.exists(runner):
            print(f"  {RED}✗{R} no encuentro la suite: {runner}")
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
    mode = "diagnóstico (--check, no modifica nada)" if check_only else "revisar y reparar"
    osname = "Windows" if IS_WIN else ("Mac" if sys.platform == "darwin" else "Linux")
    print(f"\n  {BO}{C}WORKSPACE doctor{R}  {DIM}· {mode} · {osname} · {ROOT}{R}")
    if wt_downgraded:
        print(f"  {YEL}⚠ Este WORKSPACE es un git WORKTREE — modo reparación desactivado "
              f"(solo diagnóstico).{R}")
        print(f"  {DIM}Corre el doctor desde el checkout principal para reparar "
              f"(override consciente: {install.FORCE_ENV}=1).{R}")

    # NO auto-descubrimos cerebros aquí: el harness se distribuye a clientes y debe
    # quedar VACÍO salvo lo que el usuario conecte explícitamente (Agregar agente).
    # El doctor configura/repara lo YA registrado; descubrir es acción manual
    # (`agentsreg.py discover --register` o el menú Agregar agente → Descubrir).
    ctx = build_ctx()
    results = []
    for title, fn in PHASES:
        try:
            finds = fn(ctx, fix=not check_only)
        except Exception as e:
            finds = [f(FAIL, "error interno de la fase", f"{type(e).__name__}: {e}",
                       _report_hint())]
        results.append((title, _print_phase(title, finds, not check_only), finds))

    # tabla de salud
    print(f"\n  {DIM}{'─' * 60}{R}")
    print(f"  {BO}{WH}Salud del harness{R}")
    for title, st, _ in results:
        print(f"    {SYM[st]}  {title}")
    n = {s: sum(1 for _, st, _ in results if st == s) for s in (OK, FIXED, WARN, FAIL)}
    print(f"\n  {DIM}Fases:{R} {GRN}{n[OK]} ✓{R} · {C}{n[FIXED]} reparadas{R} · "
          f"{YEL}{n[WARN]} ⚠{R} · {RED}{n[FAIL]} ✗{R}")
    if check_only and (n[WARN] or n[FAIL]):
        print(f"  {DIM}Corre {R}{BO}workspace doctor{R}{DIM} (sin --check) para reparar lo automático; "
              f"lo manual viene marcado como → acción.{R}")
    elif not check_only and n[FAIL]:
        print(f"  {DIM}Quedan pendientes manuales (→ acción). Resuélvelos y vuelve a correr "
              f"{R}{BO}workspace doctor{R}{DIM} — es idempotente.{R}")
    # cierre: resolver lo pendiente con Zenith (interactivo, falla-suave;
    # NUNCA en --check ni sin TTY — no bloquea flujos automáticos ni la UI/CI)
    offer_zenith_handoff(results, check_only)
    print()
    return 1 if n[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
