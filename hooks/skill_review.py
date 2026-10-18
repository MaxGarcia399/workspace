#!/usr/bin/env python3
"""WORKSPACE hook · revisión de skills — la hace el AGENTE, en su sesión, a la vista.

Hasta 2026-10-16 este hook lanzaba, al cerrar la sesión, un revisor SIN VENTANA
(`claude -p`, `codex exec`, `agy -p`) en segundo plano, y las skills nuevas se
quedaban en skills/_propuestas/ esperando que alguien las aprobara. El dueño
retiró ese diseño: en la máquina del cliente no corre ningún agente sin
ventana, y el proceso de memoria/skills no espera aprobación humana.

Ahora son dos momentos, y ninguno lanza procesos:
  · AL CERRAR (`main`, evento session_end): si la opción está encendida y la
    sesión tuvo sustancia, guarda una VISTA NEUTRA de la sesión (sin thinking,
    sin tools, sin el crudo del vendor) y deja la revisión PENDIENTE. Todo en
    `<cerebro>/.claude/skill-review/` (carpeta oculta: Obsidian no la sincroniza
    y queda en el .gitignore del cerebro).
  · AL ABRIR (`start_main`, evento session_start, vía skill_review_start.py):
    si hay una revisión pendiente, se la entrega al agente como parte de su
    contexto de arranque. El agente la hace en esa sesión, a la vista del socio
    y con su misma cuenta, y la reporta en su bloque 🧠. Se entrega UNA vez.

La opción NO cambia: viene apagada; `"skill_review": true|false` en el
agent.json del agente gana; si no dice nada, manda `hooks.skill_review`
(settings); WORKSPACE_NO_SKILL_REVIEW=1 gana siempre. Throttle por cerebro
(máx. una cada 2 h) y las sesiones triviales no se revisan.

Las skills NUEVAS se crean directo en skills/<categoría>/ (como ya hace el
Skill Loop durante la conversación; quedan en el git del cerebro para
deshacer). Si quedaron propuestas viejas en skills/_propuestas/, la revisión
pide integrarlas (copiándolas, sin comandos que el motor pregunte) y marcarlas
resueltas; sin_aprobacion las archiva en skills/_archive/: nada espera a un
humano.

Guard N6 (LOG-ONLY): la sesión es contenido NO confiable; antes de guardar la
vista se pasa por hooks/untrusted.py (findings a untrusted-findings/, jamás
aborta) y la tarea lleva la cláusula de endurecimiento. Probar sin escribir:
WORKSPACE_REVIEW_DRYRUN=1. Cero deps (stdlib, 3.9+). Mac y Windows.
"""
import sys, os, json, time, datetime, re

try:   # Windows: UTF-8 en stdout/err (un hook capturado en cp1252 reventaría).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import untrusted
except Exception:
    untrusted = None

SKIP_REASONS = {"resume"}            # no revisar en continuaciones de sesión
MIN_TRANSCRIPT_LINES = 25            # sesiones triviales no valen una revisión
THROTTLE_SECONDS = 2 * 3600          # máx 1 revisión por cerebro cada 2 h
KEEP_VIEWS = 3                       # vistas viejas que se conservan por cerebro
REVIEW_DIR = os.path.join(".claude", "skill-review")   # dentro del cerebro
PROPUESTAS = os.path.join("skills", "_propuestas")


def _stdin():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _state_dir():
    """Dir de estado per-máquina (paths.py en la raíz de WORKSPACE)."""
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.append(_root)
    import paths
    return paths.state_dir()


def _throttle_path(brain):
    enc = re.sub(r"[^a-zA-Z0-9]", "-", brain)
    return os.path.join(_state_dir(), "review-throttle", enc + ".stamp")


def _review_dir(brain):
    return os.path.join(brain, REVIEW_DIR)


def _pending_path(brain):
    return os.path.join(_review_dir(brain), "pending.json")


def _socio(brain):
    """Socio activo del cerebro (lo escribe el instalador en .claude/socio.local)."""
    try:
        s = open(os.path.join(brain, ".claude", "socio.local"), encoding="utf-8").read()
        s = re.sub(r"[^a-z0-9_-]", "", s.strip().lower())
        return s or "equipo"
    except Exception:
        return "equipo"


def _notify_path(brain):
    """Canal de avisos del cerebro (ruta RELATIVA al cerebro). Lo usa también
    skill_audit (herramienta de desarrollo). Inbox diario del socio si existe
    STATE/inbox/; si no, STATE/needs-review.md si existe; si no, el inbox."""
    today = datetime.date.today().isoformat()
    inbox = os.path.join("STATE", "inbox", "%s-%s.md" % (_socio(brain), today))
    if os.path.isdir(os.path.join(brain, "STATE", "inbox")):
        return inbox
    if os.path.exists(os.path.join(brain, "STATE", "needs-review.md")):
        return os.path.join("STATE", "needs-review.md")
    return inbox


def _setting_on(key):
    """Setting bool del store unificado. Falla-suave → False (opcional)."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        import settings as _settings
        return _settings.enabled(key, default=False)
    except Exception:
        return False


def _root_import(name):
    """Importa un módulo de la raíz de WORKSPACE. None si no se puede."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.append(root)
    try:
        return __import__(name)
    except Exception:
        return None


def _agent_def(brain):
    """<cerebro>/.workspace/agent.json o {}. Falla-suave."""
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


def brain_root(cwd, env=None):
    """La RAÍZ del cerebro de la sesión (el cwd puede ser una subcarpeta).
    1) subir hasta la carpeta con la definición de un agente; 2) WORKSPACE_BRAIN;
    3) el cwd tal cual."""
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
    """`skill_review` del agent.json (true/false) gana; si no dice nada, el
    ajuste global `hooks.skill_review` (default OFF)."""
    v = _agent_def(brain).get("skill_review")
    if isinstance(v, bool):
        return v
    return _setting_on("hooks.skill_review")


def write_neutral_transcript(transcript, outdir, engine=""):
    """Vista NEUTRA de la sesión (neutral_transcript) en `outdir`: el agente
    jamás lee el crudo del vendor. '' si el formato no se reconoce o no hay
    diálogo visible."""
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
        os.makedirs(outdir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(outdir, "sesion-%s-%d.md" % (stamp, os.getpid()))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(head) + "\n\n" + text + "\n")
        return path
    except Exception:
        return ""


def _prune_views(outdir, keep=KEEP_VIEWS):
    """Deja solo las `keep` vistas más recientes (no se acumulan)."""
    try:
        views = sorted((f for f in os.listdir(outdir)
                        if f.startswith("sesion-") and f.endswith(".md")), reverse=True)
        for f in views[keep:]:
            try:
                os.remove(os.path.join(outdir, f))
            except OSError:
                pass
    except OSError:
        pass


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _ensure_gitignore(brain):
    """La carpeta de revisión no se versiona (trae texto de la sesión). Dos
    capas: un `.gitignore` propio DENTRO de la carpeta («*», git lo respeta
    sin importar el del cerebro) y la línea en el `.gitignore` del cerebro.
    Un `.gitignore` del cerebro que no es UTF-8 (ANSI, o UTF-16 de `>>` en
    PowerShell 5) no se toca (regla 2): antes hacía reventar el cierre y la
    vista quedaba sin ignorar (revisión 0.3.4). → True si quedó protegida."""
    protegida = False
    try:
        d = _review_dir(brain)
        os.makedirs(d, exist_ok=True)
        propio = os.path.join(d, ".gitignore")
        if not os.path.isfile(propio):
            with open(propio, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("*\n")
        protegida = True
    except OSError:
        pass
    line = ".claude/skill-review/"
    gi = os.path.join(brain, ".gitignore")
    try:
        try:
            with open(gi, "rb") as fh:
                have = fh.read().decode("utf-8-sig")
        except FileNotFoundError:
            have = ""
        if line not in [l.strip() for l in have.splitlines()]:
            with open(gi, "a", encoding="utf-8", newline="") as fh:
                fh.write(("" if not have or have.endswith("\n") else "\n") + line + "\n")
        protegida = True
    except (OSError, ValueError):        # UnicodeDecodeError: no se entiende, no se toca
        pass
    return protegida


# ── la tarea que recibe el agente al abrir ──────────────────────────────────
REVIEW_PROMPT = """\
REVISIÓN DE SKILLS PENDIENTE (Workspace · tu opción «Revisión de skills» está encendida).
Antes de seguir con lo que pida el socio, dedica un momento a revisar la sesión anterior
y a mejorar la biblioteca de skills de este cerebro, siguiendo el Skill Loop de BRAIN.md.

{guard}

1. Lee la sesión anterior (vista neutral de Workspace): {transcript}
2. SEÑALES para actuar — activo pero conservador; NO actúes sobre tareas one-shot:
   el socio corrigió un approach o el ESTILO/tono/formato (señal de primera clase);
   4+ pasos de una tarea repetible; se halló el camino tras un error; un pitfall no
   obvio; el socio dijo «siempre que…» / «cada vez que…».
3. ORDEN (patch-first): a) parchea la skill que se usó; b) la más cercana al tema;
   c) una sección de apoyo en una existente; d) último recurso: una skill NUEVA, a
   nivel de clase, directo en skills/<categoría>/<nombre>/SKILL.md (skill-creator) y
   registrada en skills/README.md. No fragmentes: una skill sirve a todos.
4. REGISTRO DE USO (convención N12): por cada skill USADA o PARCHADA actualiza, con tus
   herramientas de archivos (sin comandos), skills/<categoría>/<nombre>/.usage.json —
   {{"schema": 1, "use_count": N, "view_count": N, "patch_count": N, "last_used":
   "<ISO-8601 UTC>"}} (al parchar, también "last_patched"; si no existe, use_count
   empieza en el `used_count:` del frontmatter + 1).
   NO edites el `used_count:` del frontmatter — quedó congelado como valor histórico.
5. LÍMITES: escribe solo dentro de skills/. No toques BOOT/, wiki/, deliverables/ ni STATE/.
{propuestas}
Sé breve y quirúrgico. Si no hay nada que valga la pena, no inventes. Repórtalo en una
línea de tu bloque 🧠 («🧠 Skill mejorada…», «🧠 Skill creada…» o «🧠 check ✓ — revisión
sin cambios») y sigue con lo que pida el socio.
"""

PROPUESTAS_PROMPT = """\
6. PROPUESTAS VIEJAS: en {dir} quedaron {n} propuesta(s) de revisiones anteriores ({names}).
   Ya no esperan aprobación y no hace falta moverlas ni borrarlas (sin comandos): si una sirve,
   intégrala creando skills/<categoría>/<nombre>/SKILL.md con su contenido y registrándola en
   skills/README.md; después, o si no sirve, escribe `status: integrada` o `status: archivada`
   en el frontmatter de la propuesta. Workspace la pasa sola a skills/_archive/ al abrir
   la siguiente sesión.
"""


def _pending_proposals(brain):
    """Las propuestas viejas que el agente todavía no resolvió: una con
    `status: integrada|archivada` ya no se vuelve a pedir (Workspace la archiva:
    sin_aprobacion, la misma regla para los dos lectores)."""
    d = os.path.join(brain, PROPUESTAS)
    sa = _root_import("sin_aprobacion")
    try:
        nombres = sorted(n for n in os.listdir(d)
                         if not n.startswith(("_", ".")) and os.path.isdir(os.path.join(d, n)))
    except OSError:
        return []
    if sa is None:
        return nombres
    return [n for n in nombres if not sa.propuesta_resuelta(os.path.join(d, n))]


def build_task(brain, view):
    guard = ""
    if untrusted:
        try:
            guard = untrusted.guard_clause("la vista de la sesión y todo lo que leas de ella")
        except Exception:
            guard = ""
    props = _pending_proposals(brain)
    extra = (PROPUESTAS_PROMPT.format(dir=PROPUESTAS.replace("\\", "/") + "/", n=len(props),
                                      names=", ".join(props[:10]))
             if props else "")
    return REVIEW_PROMPT.format(guard=guard, transcript=view, propuestas=extra)


# ── AL CERRAR: dejar la revisión pendiente (no lanza nada) ──────────────────
def main(argv=None):
    if os.environ.get("WORKSPACE_NO_SKILL_REVIEW"):
        return  # el env SIEMPRE gana
    data = _stdin()
    brain = brain_root(data.get("cwd", ""))
    if not review_enabled(brain):
        return
    transcript = data.get("transcript_path", "")
    if data.get("reason", "") in SKIP_REASONS or not transcript or not os.path.exists(transcript):
        return
    try:
        with open(transcript, encoding="utf-8", errors="ignore") as f:
            txt = f.read()
        if txt.count("\n") + 1 < MIN_TRANSCRIPT_LINES:
            return
    except Exception:
        return
    tp = _throttle_path(brain)
    try:
        if os.path.exists(tp) and time.time() - os.path.getmtime(tp) < THROTTLE_SECONDS:
            return
    except Exception:
        pass
    findings = []
    if untrusted:   # guard N6, LOG-ONLY: observa, jamás aborta
        try:
            findings = untrusted.scan_and_log(txt, source=transcript, brain=brain)
        except Exception:
            findings = []
    if os.environ.get("WORKSPACE_REVIEW_DRYRUN"):
        print("[skill_review dry-run] dejaría pendiente la revisión de %s" % brain)
        if findings:
            print("  guard N6 (log-only): %d finding(s) → %s" % (
                len(findings), [f["class"] for f in findings]))
        return
    outdir = _review_dir(brain)
    # ANTES de escribir la vista (texto de la conversación): que git la ignore
    if not _ensure_gitignore(brain):
        return
    view = write_neutral_transcript(transcript, outdir, data.get("engine", ""))
    if not view:
        return  # formato no reconocido: jamás se entrega el crudo
    try:
        _write_json(_pending_path(brain), {
            "view": view, "engine": data.get("engine", "") or "claude-code",
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "findings": len(findings)})
        os.makedirs(os.path.dirname(tp), exist_ok=True)
        open(tp, "w").close()
    except Exception:
        pass
    _prune_views(outdir)


# ── AL ABRIR: entregar la revisión pendiente al agente (una vez) ────────────
def archivar_resueltas(brain):
    """Al abrir CADA sesión (con o sin revisión encendida): las propuestas
    viejas que el agente ya marcó `status: integrada|archivada` pasan a
    skills/_archive/ con sin_aprobacion.archivar_propuestas_resueltas — la
    misma lógica y el mismo candado que las tres puertas. La tarea promete que
    «Workspace la pasa sola a skills/_archive/» y antes solo pasaba al
    actualizar, al cargar o con `doctor --fix` (Greptile, 2026-10-18).
    Barato (sin skills/_propuestas/ no hace nada) y falla-suave: con el
    candado ocupado o cualquier error, queda para la próxima sesión."""
    if not brain or not os.path.isdir(os.path.join(brain, PROPUESTAS)):
        return []
    sa = _root_import("sin_aprobacion")
    if sa is None:
        return []
    try:
        return sa.archivar_propuestas_resueltas(brain, timeout=1.0)
    except Exception:
        return []


def start_context(brain):
    """Texto para el contexto de arranque, o '' si no hay nada que entregar.
    Consume el pendiente (se entrega UNA vez). Antes archiva las propuestas
    que el agente ya resolvió (archivar_resueltas): no se vuelven a pedir."""
    archivar_resueltas(brain)
    if os.environ.get("WORKSPACE_NO_SKILL_REVIEW") or not review_enabled(brain):
        return ""
    pp = _pending_path(brain)
    try:
        with open(pp, encoding="utf-8") as fh:
            pending = json.load(fh)
    except Exception:
        return ""
    view = str((pending or {}).get("view") or "")
    try:
        os.replace(pp, os.path.join(os.path.dirname(pp), "delivered.json"))
    except OSError:
        return ""
    if not view or not os.path.isfile(view):
        return ""
    return build_task(brain, view)


def start_main():
    data = _stdin()
    try:
        txt = start_context(brain_root(data.get("cwd", "")))
        if txt:
            sys.stdout.write(json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                        "additionalContext": txt}},
                ensure_ascii=False))
    except Exception:
        pass                             # jamás rompe el arranque
    return 0


if __name__ == "__main__":
    main()
