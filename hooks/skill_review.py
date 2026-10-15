#!/usr/bin/env python3
"""WORKSPACE hook · SessionEnd — background skill review (robo #1 de Hermes).

Al cerrar una sesión, lanza un revisor AISLADO y en segundo plano que lee la sesión
y crea/parcha skills siguiendo el Skill Loop (CLAUDE.md §7) — FUERA del turno real,
sin gastar tokens del chat ni depender de que el agente "se acuerde".

OPCIONAL (0.3.0): corre solo si el agente lo pide en su agent.json
(`"skill_review": true`) o, si no dice nada, si el ajuste global
`hooks.skill_review` está prendido (viene APAGADO). WORKSPACE_NO_SKILL_REVIEW=1
siempre gana.

Revisor según el motor de la sesión que cerró (payload["engine"]; sin él es el
hook nativo de Claude Code):
- claude-code → `claude -p --model haiku` con tools solo de archivos.
- codex       → `codex exec --ephemeral` en el cerebro (-C), sandbox
                workspace-write SIN red, razonamiento bajo, prompt por stdin;
                modelo "luna" solo si tu cuenta lo lista (models_cache.json).
- antigravity → `agy -p` con --mode accept-edits y --add-dir del cerebro y del
                log, corrido desde una carpeta NEUTRA (<estado>/review-cwd) —
                nunca desde el cerebro (agy recuerda la última conversación
                por carpeta: el revisor no debe ocupar la del agente);
                modelo *-flash-low si `agy models` lo ofrece.
Si el CLI de ese motor no está pero `claude` sí, revisa `claude`.

El revisor nunca ve el crudo del vendor: lee una VISTA NEUTRA del transcript
(neutral_transcript → .md temporal en el log, se borra al terminar).

Como el background-review de Hermes:
- Corre detached: NO bloquea el cierre de la sesión (un proceso hijo propio
  elige el modelo, corre el revisor y limpia).
- Tools restringidas a archivos; sin terminal ni red.
- Modelo barato — es trabajo de bookkeeping.
- Guard anti-recursión (WORKSPACE_REVIEW_RUNNING): NO se dispara dentro de sí mismo.
- Throttle + chequeo de sustancia: no revisa sesiones triviales ni muy seguido.
- Probar sin lanzar: WORKSPACE_REVIEW_DRYRUN=1.

Usa la suscripción del motor (sin API key). Best-effort. Cero deps (3.9+).

Prompt gen-2 (robo Y3, Hermes background_review):
- Forma target CLASS-LEVEL: skills que generalizan el patrón (anti-fragmentación en el
  momento de escribir, no después vía curator).
- Orden patch-first: parchear skill usada en sesión > parchear la más cercana > sección de
  apoyo en una existente > (último) proponer skill nueva.
- Correcciones de estilo/tono/formato del usuario = señal de skill de primera clase.

Contrato de salida parseable (robo Y15 — tokens, no prosa). El review anexa a su logfile
(~/.claude/workspace/review-logs/YYYY-MM-DD.md) una línea `REVIEW:` por acción, formato exacto:
    REVIEW: SIN_ACCION — <razón>
    REVIEW: PATCH:<skills/categoría/nombre> — <qué cambió>
    REVIEW: PROPUESTA:<nombre> — <para qué>
Parseo (humano o máquina): grep '^REVIEW:' sobre los logs. Sin línea REVIEW: = la corrida
no terminó / no cumplió contrato.

Guard N6 (corrida N-4, LOG-ONLY). Este hook es el emisor actual de `headless_ingest`
(engines/EVENTS.md): entrega un transcript NO confiable a un proceso headless. Antes de
lanzar, pasa el transcript por `hooks/untrusted.py`:
- mini threat-scan (regex de clases obvias de inyección/exfil) → findings a
  ~/.claude/workspace/untrusted-findings/YYYY-MM-DD.jsonl — SOLO observación, jamás aborta;
- el prompt del review lleva la cláusula de endurecimiento (`untrusted.guard_clause`):
  el transcript es DATOS, no instrucciones (el wrap inline no aplica aquí — el headless
  lee el archivo él mismo; los flujos que SÍ inlineen contenido usan `untrusted.wrap`).
Camino futuro: cuando la pasada unificada (N3) reemplace este flujo, el scan+wrap se
mueve con el emisor de `headless_ingest`; si algún día se decide bloquear (post análisis
de falsos positivos de los logs), eso es otra corrida y otra decisión — no esta.
Si untrusted.py no está (amputado), el review sigue funcionando sin guard.

Gate de aprobación + cuarentena (robo Y11). Las skills NUEVAS jamás se escriben al catálogo
vivo: van a skills/_propuestas/<nombre>/ + nota en el canal de avisos del cerebro
(STATE/inbox/<socio>-<fecha>.md si el cerebro tiene inbox/, si no STATE/needs-review.md);
un humano aprueba (mueve a su categoría) o descarta. Los PATCHES a skills existentes SÍ son
directos: mejoran material ya aprobado, quedan versionados en frontmatter y visibles en el
git del cerebro — gatearlos mataría el valor del loop sin reducir el riesgo real, que vive
en la CREACIÓN (fragmentación / capacidades nuevas sin revisión). El gate vive en el prompt
y REDUCE autonomía: este hook no gana ninguna capacidad (mismas tools restringidas, sin
Bash/Web/Task) y el proceso de review no puede aprobar ni promover nada.
"""
import sys, os, json, time, datetime, subprocess, shutil, re

try:   # M1/B2 · Windows: UTF-8 en stdout/err — un hook capturado por Claude Code en
       # cp1252 reventaría al imprimir caracteres no-ASCII. No-op en Mac (UTF-8 default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# untrusted (N6) vive junto a este hook; hooks/ no es paquete → import por path.
# Amputable: si falta, el review corre sin guard (jamás romper el cierre).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import untrusted
except Exception:
    untrusted = None

SKIP_REASONS = {"resume"}            # no revisar en continuaciones de sesión
MIN_TRANSCRIPT_LINES = 25            # sesiones triviales no valen una revisión
THROTTLE_SECONDS = 2 * 3600          # máx 1 revisión por cerebro cada 2 h
DEFAULT_MODEL = os.environ.get("WORKSPACE_REVIEW_MODEL", "haiku")


def _stdin():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _state_dir():
    """Dir de estado per-máquina vía el resolver único (`paths.py`, en la raíz
    de WORKSPACE = padre de hooks/). append (no insert) para no alterar qué
    módulo homónimo de hooks/ gana en sys.path."""
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.append(_root)
    import paths
    return paths.state_dir()


def _workspace_dir():
    return _state_dir()


def _throttle_path(brain):
    enc = re.sub(r"[^a-zA-Z0-9]", "-", brain)
    return os.path.join(_workspace_dir(), "review-throttle", enc + ".stamp")


REVIEW_PROMPT = """\
Eres un REVISOR DE SKILLS en segundo plano de WORKSPACE (no eres el agente de este cerebro en
conversación). Único trabajo: revisar la sesión que acaba de terminar y mejorar la biblioteca
de skills de ESTE cerebro: {brain}
Toda ruta relativa de abajo (CLAUDE.md, skills/, STATE/) es relativa a esa carpeta, aunque tu
directorio actual sea otro.

{guard}

1. Lee el transcript de la sesión (vista neutral de Workspace): {transcript}
2. Lee el Skill Loop documentado en el CLAUDE.md de este cerebro (la sección del Skill Loop /
   bloque 🧠) y el catálogo en skills/README.md si existe.
3. SEÑALES para actuar — criterio ACTIVO pero conservador; NO actúes sobre tareas one-shot que
   no se repetirán:
   - El usuario corrigió un approach.
   - El usuario corrigió ESTILO, tono, formato o verbosidad → señal de skill de PRIMERA CLASE
     (va a la skill relevante, no es solo "memoria"): mejoras generales al cuerpo, preferencias
     personales a la sección de preferencias que ya use este cerebro (si no hay, `## Preferencias`).
   - 4+ tool calls de una tarea repetible; se halló el path correcto tras un error; pitfalls
     no obvios; el usuario dijo "siempre que..." / "cada vez que...".
   - Se usó una skill existente → registra el uso en su SIDECAR `.usage.json` (paso 4-bis).
     NO edites el `used_count:` del frontmatter — quedó congelado como valor histórico.
4-bis. REGISTRO DE USO (convención N12, documentada en skills/README.md del cerebro): por cada
   skill USADA o PARCHADA en la sesión, actualiza skills/<categoría>/<nombre>/.usage.json —
   JSON con {{"schema": 1, "use_count": N, "view_count": N, "patch_count": N, "last_used":
   "<ISO-8601 UTC>"}}. Si no existe: créalo sembrando use_count desde el `used_count:` del
   frontmatter (si lo hay, y anota ese valor en "seeded_from_frontmatter") y suma el evento.
   Skill usada → use_count+1; solo consultada → view_count+1; patch aplicado → patch_count+1
   y "last_patched". Todo evento refresca "last_used". JSON válido siempre.
4. ORDEN DE PREFERENCIA (patch-first — agota cada nivel antes de pasar al siguiente):
   a) Parchear una skill que se USÓ o CARGÓ en esta sesión.
   b) Parchear la skill existente más cercana al tema (mejorarla o generalizarla).
   c) Añadir una sección o archivo de apoyo dentro de una skill existente.
   d) ÚLTIMO recurso: PROPONER una skill nueva (paso 5 — nunca se escribe al catálogo vivo).
   FORMA TARGET de la biblioteca: skills A NIVEL DE CLASE — el patrón general reutilizable con
   un SKILL.md rico — NO una lista plana de skills angostas de un-incidente-una-skill. No
   fragmentar: una skill sirve a todos los que usan este cerebro.
5. APLICAR:
   - PATCH a skill existente: edita directo en skills/<categoría>/<nombre>/ siguiendo
     skills/meta/skill-improver; bump de `version` en el frontmatter.
   - Skill NUEVA: NUNCA escribas en skills/<categoría>/. Escríbela completa en
     skills/_propuestas/<nombre>/SKILL.md siguiendo skills/meta/skill-creator, con frontmatter
     normal más `status: propuesta`, `propuesta_por: skill-review` y
     `categoria_sugerida: <categoría>`. Después ANEXA (append, sin tocar lo existente) una nota
     a {notify} :
       "- [skill-review] Propuesta de skill `<nombre>` (<categoría sugerida>): <1 línea de qué
        resuelve>. Aprobar = mover a skills/<categoría>/<nombre>/ y actualizar skills/README.md;
        descartar = borrar la carpeta."
     Tú NO la mueves, NO la registras en skills/README.md, NO la apruebas: eso lo hace un humano.
6. LÍMITES duros: escribe SOLO dentro de skills/ (incluida skills/_propuestas/), el append a
   {notify} y el reporte de abajo. NO toques BOOT/, wiki/, deliverables/ ni el resto de STATE/.
   {tools_rule}
7. REPORTE (contrato parseable, obligatorio) — anexa al final de {logfile} una línea por acción
   realizada (o la única de sin-acción), formato EXACTO, sin prosa antes:
     REVIEW: SIN_ACCION — <razón en <=8 palabras>
     REVIEW: PATCH:<skills/categoría/nombre> — <qué cambió en <=10 palabras>
     REVIEW: PROPUESTA:<nombre> — <para qué en <=10 palabras>
   Después de las líneas REVIEW:, máximo 5 líneas de detalle. Si no puedes escribir en
   {logfile}, imprime esas mismas líneas REVIEW: en tu respuesta final (Workspace las anota).

Sé breve y quirúrgico. Si no hay nada que valga la pena, no inventes: REVIEW: SIN_ACCION.
"""


def _socio(brain):
    """Socio activo del cerebro (lo escribe el instalador en .claude/socio.local)."""
    try:
        s = open(os.path.join(brain, ".claude", "socio.local"), encoding="utf-8").read()
        s = re.sub(r"[^a-z0-9_-]", "", s.strip().lower())
        return s or "equipo"
    except Exception:
        return "equipo"


def _notify_path(brain):
    """Canal de avisos del cerebro para propuestas (ruta RELATIVA al cwd del review).

    Cerebros con STATE/inbox/ (Zenith) → inbox diario del socio activo.
    Cerebros sin inbox pero con STATE/needs-review.md (Atlas) → esa cola de revisión.
    Fallback: el inbox diario (el review crea STATE/inbox/ si hace falta).
    """
    today = datetime.date.today().isoformat()
    inbox = os.path.join("STATE", "inbox", "%s-%s.md" % (_socio(brain), today))
    if os.path.isdir(os.path.join(brain, "STATE", "inbox")):
        return inbox
    if os.path.exists(os.path.join(brain, "STATE", "needs-review.md")):
        return os.path.join("STATE", "needs-review.md")
    return inbox


def _setting_on(key):
    """Setting bool del store unificado (settings.py, raíz de WORKSPACE).
    Falla-suave → False (la revisión es opcional: ante la duda, no corre). El
    env kill-switch se chequea aparte y SIEMPRE gana."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        import settings as _settings
        return _settings.enabled(key, default=False)
    except Exception:
        return False


def _root_import(name):
    """Importa un módulo de la raíz de WORKSPACE (append: no altera qué
    homónimo de hooks/ gana). None si no se puede."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.append(root)
    try:
        return __import__(name)
    except Exception:
        return None


def _agent_def(brain):
    """La definición del agente de este cerebro (<cerebro>/.workspace/agent.json)
    o {}. Falla-suave."""
    ar = _root_import("agentsreg")
    try:
        if ar is not None:
            d = ar.load_definition(brain)
            return d if isinstance(d, dict) else {}
        with open(os.path.join(brain, ".workspace", "agent.json"),
                  encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


#: La regla de herramientas del paso 6, por motor. Codex no tiene herramientas
#: de archivos aparte de la terminal: con «no uses la terminal» se negaba a
#: leer nada y la revisión terminaba en SIN_ACCION (visto en vivo 2026-10-14).
#: Su sandbox (escritura solo en el cerebro y el log, sin red) es el límite.
TOOLS_RULE = {
    "codex": ("Sin red. En Codex lees y editas archivos con comandos dentro de tu sandbox: "
              "úsalos SOLO para leer (cat, sed -n, ls, rg) y editar (apply_patch) archivos "
              "de este cerebro y el reporte; ningún otro comando."),
}
TOOLS_RULE_DEFAULT = "No uses la terminal ni la red: solo leer y editar archivos."


def tools_rule(engine):
    return TOOLS_RULE.get(engine or "", TOOLS_RULE_DEFAULT)


def brain_root(cwd, env=None):
    """La RAÍZ del cerebro de la sesión. El hook recibe el cwd del momento, que
    puede ser una subcarpeta (p. ej. deliverables/…) si el agente se movió:
    revisar ahí dejaba las skills en el lugar equivocado e ignoraba la elección
    del agente en Agentes → Enter. Orden: 1) subir desde el cwd hasta la carpeta
    con la definición de un agente (la más cercana: un agente abierto dentro
    del cerebro de otro revisa ESE cerebro), 2) WORKSPACE_BRAIN (lo exporta el
    lanzador; cubre un cwd fuera de todo cerebro), 3) el cwd tal cual."""
    env = os.environ if env is None else env
    ar = _root_import("agentsreg")
    start = os.path.abspath(cwd or os.getcwd())
    cur = start
    while True:
        try:
            has = ar.has_definition(cur) if ar is not None else os.path.isfile(
                os.path.join(cur, ".workspace", "agent.json"))
        except Exception:
            has = False
        if has:
            return cur
        up = os.path.dirname(cur)
        if up == cur:
            break
        cur = up
    wb = str(env.get("WORKSPACE_BRAIN") or "").strip()
    if wb and os.path.isdir(wb):
        return wb
    return start


def review_enabled(brain):
    """¿Revisar las sesiones de este cerebro? `skill_review` del agent.json
    (true/false) gana; si el agente no dice nada, el ajuste global
    `hooks.skill_review` (default OFF). El env kill-switch va aparte."""
    v = _agent_def(brain).get("skill_review")
    if isinstance(v, bool):
        return v
    return _setting_on("hooks.skill_review")


#: binario del revisor por motor (los demás motores revisan con claude)
REVIEWER_BIN = {"claude-code": "claude", "codex": "codex", "antigravity": "agy"}
REVIEW_TIMEOUT = 30 * 60             # el hijo detached corta un revisor colgado


def pick_reviewer(engine, which=None):
    """(motor_revisor, ejecutable) para una sesión del motor `engine`: su
    propio CLI si es codex/antigravity y está instalado; si no, `claude`.
    (None, None) si no hay revisor posible. which() resuelve la ruta completa
    (en Windows el shim de npm es `claude.cmd` y CreateProcess no lo
    encuentra por nombre pelado)."""
    which = which or shutil.which
    engine = (engine or "claude-code").strip().lower()
    if engine in ("codex", "antigravity"):
        exe = which(REVIEWER_BIN[engine])
        if exe:
            return engine, exe
    exe = which("claude")
    return ("claude-code", exe) if exe else (None, None)


def codex_model(codex_home=None):
    """El modelo "luna" de codex SOLO si tu cuenta lo lista en
    models_cache.json (el más barato de la familia); '' = el default de
    codex. Solo lectura local, jamás credenciales."""
    home = codex_home or os.environ.get("CODEX_HOME") or os.path.join(
        os.path.expanduser("~"), ".codex")
    try:
        with open(os.path.join(home, "models_cache.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        models = data.get("models") if isinstance(data, dict) else data
        for m in models or []:
            slug = str((m or {}).get("slug") or "")
            if "luna" in slug and (m or {}).get("visibility") != "hide":
                return slug
    except Exception:
        pass
    return ""


def agy_model(exe, runner=None, timeout=20):
    """El primer modelo *-flash-low que `agy models` ofrece a tu cuenta; ''
    = el default de agy. Corre en el hijo detached (puede tardar unos
    segundos): nunca en el cierre de la sesión."""
    run = runner or subprocess.run
    try:
        r = run([exe, "models"], stdin=subprocess.DEVNULL, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=timeout)
        for line in (r.stdout or "").splitlines():
            mid = line.strip().split("\t")[0].split(" ")[0]
            if mid.endswith("-flash-low"):
                return mid
    except Exception:
        pass
    return ""


def review_cwd():
    """Carpeta NEUTRA desde la que corre el revisor de Antigravity."""
    d = os.path.join(_workspace_dir(), "review-cwd")
    os.makedirs(d, exist_ok=True)
    return d


def claude_no_persist(exe, runner=None):
    """True si este `claude` conoce --no-session-persistence (las versiones
    viejas no: pasarlo rompería la revisión). Sin él, cada revisión quedaba
    guardada como una sesión más del cerebro (aparecía en /resume), lo mismo
    que evitan --ephemeral en Codex y la carpeta neutra en Antigravity."""
    run = runner or subprocess.run
    try:
        r = run([exe, "--help"], capture_output=True, text=True, timeout=20)
        out = getattr(r, "stdout", "")
        return isinstance(out, str) and "--no-session-persistence" in out
    except Exception:
        return False


_PLACEHOLDER = re.compile(r"<[^<>]{1,60}>")


def _append_review_lines(logfile, output):
    """Anota en el log las líneas `REVIEW:` que el revisor imprimió y no pudo
    escribir él mismo (Claude Code protege ~/.claude: le niega el log)."""
    if not logfile or not isinstance(output, str):
        return 0
    lines = []
    for ln in output.splitlines():
        ln = ln.strip()
        # solo líneas del contrato; jamás las de ejemplo del prompt («<razón…>»),
        # que algunos CLIs repiten en su salida
        if ln.startswith("REVIEW:") and not _PLACEHOLDER.search(ln) and ln not in lines:
            lines.append(ln)
    if not lines:
        return 0
    try:
        with open(logfile, encoding="utf-8") as fh:
            have = set(ln.strip() for ln in fh)
    except OSError:
        have = set()
    new = [ln for ln in lines if ln not in have]
    if not new:
        return 0
    try:
        with open(logfile, "a", encoding="utf-8") as fh:
            fh.write("\n".join(new) + "\n")
    except OSError:
        return 0
    return len(new)


def reviewer_cmd(engine, exe, prompt, brain, logdir, model="", cwd=None,
                 no_persist=False):
    """(argv, cwd, stdin) EXACTOS del revisor de `engine`. Sin red ni
    terminal en ninguno; nunca --dangerously-* ni bypass. `no_persist` (solo
    Claude Code): la revisión no se guarda como sesión del cerebro."""
    if engine == "codex":
        argv = [exe, "exec", "--ephemeral", "--skip-git-repo-check",
                "-C", brain, "-s", "workspace-write", "--add-dir", logdir,
                "-c", "sandbox_workspace_write.network_access=false",
                "-c", 'model_reasoning_effort="low"', "--color", "never"]
        if model:
            argv += ["-m", model]
        return argv + ["-"], brain, prompt               # prompt por stdin
    if engine == "antigravity":
        argv = [exe, "-p", prompt]
        if model:
            argv += ["--model", model]
        argv += ["--mode", "accept-edits", "--add-dir", brain, "--add-dir", logdir]
        return argv, cwd or review_cwd(), None
    return ([exe, "-p", prompt, "--model", DEFAULT_MODEL,
             "--permission-mode", "acceptEdits",
             "--allowedTools", "Read Edit Write Glob Grep",
             "--add-dir", logdir] + (["--no-session-persistence"] if no_persist else []),
            brain, None)


def write_neutral_transcript(transcript, logdir, engine=""):
    """Vista NEUTRA del transcript (neutral_transcript) a un .md temporal en
    `logdir` — el revisor jamás lee el crudo del vendor. '' si el formato no
    se reconoce o no hay diálogo visible."""
    nt = _root_import("neutral_transcript")
    if nt is None:
        return ""
    try:
        doc = nt.ingest(transcript)
        if not doc:
            return ""
        text, meta = nt.sanitized_view(doc)
        if not text.strip():
            return ""
        head = ["# Sesión a revisar (vista neutral de Workspace)", "",
                "- motor: %s" % ((doc.get("session") or {}).get("engine") or engine or "?")]
        files = meta.get("files_touched") or []
        if files:
            head.append("- archivos tocados: %s" % ", ".join(str(f) for f in files[:40]))
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(logdir, "transcript-%s-%d.md" % (stamp, os.getpid()))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(head) + "\n\n" + text + "\n")
        return path
    except Exception:
        return ""


def _detached():
    # Detached cross-platform: start_new_session es POSIX-only (en Windows lanza
    # ValueError); allá se usa DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP (0x208),
    # el mismo patrón que front.py cmd_dev.
    return {"creationflags": 0x208} if os.name == "nt" else {"start_new_session": True}


def _review_env():
    env = dict(os.environ)
    env["WORKSPACE_REVIEW_RUNNING"] = "1"     # rompe la recursión en el revisor
    env["WORKSPACE_NO_AUTOUPDATE"] = "1"
    return env


def run_spec(spec_path, runner=None):
    """El HIJO detached: elige el modelo, corre el revisor y limpia (el .md
    neutral y el spec). Nunca levanta."""
    try:
        with open(spec_path, encoding="utf-8") as fh:
            spec = json.load(fh)
    except Exception:
        return 1
    engine, exe = spec.get("engine"), spec.get("exe")
    model = ""
    try:
        if engine == "codex":
            model = codex_model()
        elif engine == "antigravity":
            model = agy_model(exe)
    except Exception:
        model = ""
    run = runner or subprocess.run
    try:
        np = engine not in ("codex", "antigravity") and claude_no_persist(exe, run)
        argv, cwd, stdin = reviewer_cmd(engine, exe, spec["prompt"], spec["brain"],
                                        spec["logdir"], model=model, no_persist=np)
        kw = {"text": True, "encoding": "utf-8", "errors": "replace",
              "stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        if stdin is not None:
            kw["input"] = stdin
        else:
            kw["stdin"] = subprocess.DEVNULL
        r = run(argv, cwd=cwd, env=_review_env(), timeout=REVIEW_TIMEOUT, **kw)
        out = getattr(r, "stdout", "")
        err = getattr(r, "stderr", "")
        for chunk in (out, err):                     # ambos siguen quedando en _run.log
            if isinstance(chunk, str) and chunk:
                try:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                except Exception:
                    pass
        if isinstance(out, str) and out:             # solo la RESPUESTA (stdout)
            _append_review_lines(spec.get("logfile"), out)
        return 0
    except Exception:
        return 1
    finally:
        for p in (spec.get("transcript_md"), spec_path):
            try:
                if p:
                    os.remove(p)
            except OSError:
                pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["--run"] and len(argv) > 1:
        return run_spec(argv[1])                 # el hijo detached
    if os.environ.get("WORKSPACE_REVIEW_RUNNING") or os.environ.get("WORKSPACE_NO_SKILL_REVIEW"):
        return  # guard anti-recursión / desactivado (el env SIEMPRE gana)
    data = _stdin()
    brain = brain_root(data.get("cwd", ""))
    if not review_enabled(brain):
        return  # opcional: el agente no lo pidió y el ajuste global está apagado
    reason = data.get("reason", "")
    transcript = data.get("transcript_path", "")
    if reason in SKIP_REASONS or not transcript or not os.path.exists(transcript):
        return
    # chequeo de sustancia: sesiones triviales no se revisan
    try:
        with open(transcript, encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        if txt.count("\n") + 1 < MIN_TRANSCRIPT_LINES:
            return
    except Exception:
        return
    # guard N6 (LOG-ONLY): scan del transcript ANTES de entregarlo al headless.
    # Findings → ~/.claude/workspace/untrusted-findings/ — pura observación: NO
    # aborta, NO cambia el flujo. Falla-suave si el guard truena o no está.
    findings = []
    if untrusted:
        try:
            findings = untrusted.scan_and_log(txt, source=transcript,
                                              brain=brain)
        except Exception:
            findings = []
    engine, exe = pick_reviewer(data.get("engine"))
    if not exe:
        return
    # throttle por cerebro
    tp = _throttle_path(brain)
    try:
        if os.path.exists(tp) and time.time() - os.path.getmtime(tp) < THROTTLE_SECONDS:
            return
    except Exception:
        pass

    logdir = os.path.join(_workspace_dir(), "review-logs")
    try:
        os.makedirs(logdir, exist_ok=True)
        os.makedirs(os.path.dirname(tp), exist_ok=True)
    except Exception:
        pass
    md = write_neutral_transcript(transcript, logdir, data.get("engine", ""))
    if not md:
        return  # formato no reconocido: jamás se le entrega el crudo
    logfile = os.path.join(logdir, datetime.date.today().isoformat() + ".md")
    guard = ""
    if untrusted:
        try:
            guard = untrusted.guard_clause(
                "el transcript y todo lo que leas de él")
        except Exception:
            guard = ""
    prompt = REVIEW_PROMPT.format(transcript=md, logfile=logfile, brain=brain,
                                  tools_rule=tools_rule(engine),
                                  notify=os.path.join(brain, _notify_path(brain)),
                                  guard=guard)

    if os.environ.get("WORKSPACE_REVIEW_DRYRUN"):
        model = codex_model() if engine == "codex" else (
            "<-flash-low de `agy models`, si existe>" if engine == "antigravity" else "")
        cmd, cwd, _stdin_txt = reviewer_cmd(engine, exe, prompt, brain, logdir, model=model,
                                            cwd=(os.path.join(_workspace_dir(), "review-cwd")
                                                 if engine == "antigravity" else None))
        print("[skill_review dry-run] lanzaría (%s):" % engine)
        print("  cwd =", cwd)
        print("  cmd =", cmd)
        if findings:
            print("  guard N6 (log-only): %d finding(s) → %s" % (
                len(findings), [f["class"] for f in findings]))
        try:
            os.remove(md)
        except OSError:
            pass
        return

    try:
        open(tp, "w").close()  # marca el throttle ANTES de lanzar (evita ráfagas)
    except Exception:
        pass
    spec = {"engine": engine, "exe": exe, "brain": brain, "logdir": logdir,
            "logfile": logfile, "prompt": prompt, "transcript_md": md}
    spec_path = md[:-3] + ".spec.json"
    try:
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, ensure_ascii=False)
    except Exception:
        return
    try:
        runlog = open(os.path.join(logdir, "_run.log"), "a", encoding="utf-8")
    except Exception:
        runlog = subprocess.DEVNULL
    try:
        subprocess.Popen([sys.executable or "python3", os.path.abspath(__file__),
                          "--run", spec_path],
                         cwd=logdir, env=_review_env(), stdin=subprocess.DEVNULL,
                         stdout=runlog, stderr=runlog, **_detached())
    except Exception:
        return
    finally:
        if runlog is not subprocess.DEVNULL:
            try:
                runlog.close()               # el hijo ya tiene su copia
            except Exception:
                pass


if __name__ == "__main__":
    main()
