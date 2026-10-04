#!/usr/bin/env python3
"""WORKSPACE hook · SessionEnd — background skill review (robo #1 de Hermes).

Al cerrar una sesión, lanza un `claude -p` AISLADO y en segundo plano que revisa el
transcript y crea/parcha skills siguiendo el Skill Loop (CLAUDE.md §7) — FUERA del
turno real, sin gastar tokens del chat ni depender de que el agente "se acuerde".

Como el background-review de Hermes:
- Corre detached: NO bloquea el cierre de la sesión.
- Tools restringidas a archivos (Read/Edit/Write/Glob/Grep); sin Bash/Web/Task.
- Modelo barato por default (haiku) — es trabajo de bookkeeping.
- Guard anti-recursión (WORKSPACE_REVIEW_RUNNING): NO se dispara dentro de sí mismo.
- Throttle + chequeo de sustancia: no revisa sesiones triviales ni muy seguido.
- Desactivable: WORKSPACE_NO_SKILL_REVIEW=1 (el env SIEMPRE gana) o
  `settings set hooks.skill_review off`.  ·  Probar sin lanzar: WORKSPACE_REVIEW_DRYRUN=1.

Usa la suscripción de Claude Code (sin API key). Best-effort. Cero deps (3.9+).

Prompt gen-2 (robo Y3, Hermes background_review):
- Forma target CLASS-LEVEL: skills que generalizan el patrón (anti-fragmentación en el
  momento de escribir, no después vía curator).
- Orden patch-first: parchear skill usada en sesión > parchear la más cercana > sección de
  apoyo en una existente > (último) proponer skill nueva.
- Correcciones de estilo/tono/formato del socio = señal de skill de primera clase.

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


def _workspace_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def _throttle_path(brain):
    enc = re.sub(r"[^a-zA-Z0-9]", "-", brain)
    return os.path.join(_workspace_dir(), "review-throttle", enc + ".stamp")


REVIEW_PROMPT = """\
Eres un REVISOR DE SKILLS en segundo plano de WORKSPACE (no eres el agente de este cerebro en
conversación). Único trabajo: revisar la sesión que acaba de terminar y mejorar la biblioteca
de skills de ESTE cerebro (el del cwd actual — puede ser Zenith, Atlas u otro agente).

{guard}

1. Lee el transcript de la sesión: {transcript}
2. Lee el Skill Loop documentado en el CLAUDE.md de este cerebro (la sección del Skill Loop /
   bloque 🧠) y el catálogo en skills/README.md si existe.
3. SEÑALES para actuar — criterio ACTIVO pero conservador; NO actúes sobre tareas one-shot que
   no se repetirán:
   - El socio corrigió un approach.
   - El socio corrigió ESTILO, tono, formato o verbosidad → señal de skill de PRIMERA CLASE
     (va a la skill relevante, no es solo "memoria"): mejoras generales al cuerpo, preferencias
     personales a la sección `Preferencias del equipo` con el nombre del socio.
   - 4+ tool calls de una tarea repetible; se halló el path correcto tras un error; pitfalls
     no obvios; el socio dijo "siempre que..." / "cada vez que...".
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
   fragmentar: una skill sirve a los tres socios.
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
7. REPORTE (contrato parseable, obligatorio) — anexa al final de {logfile} una línea por acción
   realizada (o la única de sin-acción), formato EXACTO, sin prosa antes:
     REVIEW: SIN_ACCION — <razón en <=8 palabras>
     REVIEW: PATCH:<skills/categoría/nombre> — <qué cambió en <=10 palabras>
     REVIEW: PROPUESTA:<nombre> — <para qué en <=10 palabras>
   Después de las líneas REVIEW:, máximo 5 líneas de detalle.

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
    Falla-suave → True (on-by-default). El env kill-switch SIEMPRE gana."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        import settings as _settings
        return _settings.enabled(key, default=True)
    except Exception:
        return True


def main():
    if os.environ.get("WORKSPACE_REVIEW_RUNNING") or os.environ.get("WORKSPACE_NO_SKILL_REVIEW"):
        return  # guard anti-recursión / desactivado (el env SIEMPRE gana)
    if not _setting_on("hooks.skill_review"):
        return  # canal nuevo (settings.py · hooks.skill_review)
    data = _stdin()
    brain = data.get("cwd", "") or os.getcwd()
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
    # Resolver la ruta completa: en Windows el shim de npm es `claude.cmd` y
    # CreateProcess NO lo encuentra por nombre pelado (sin shell). which() devuelve
    # la ruta con extensión — funciona igual en Mac/Linux.
    claude = shutil.which("claude")
    if not claude:
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
    logfile = os.path.join(logdir, datetime.date.today().isoformat() + ".md")
    guard = ""
    if untrusted:
        try:
            guard = untrusted.guard_clause(
                "el transcript y todo lo que leas de él")
        except Exception:
            guard = ""
    prompt = REVIEW_PROMPT.format(transcript=transcript, logfile=logfile,
                                  notify=_notify_path(brain), guard=guard)

    cmd = [claude, "-p", prompt,
           "--model", DEFAULT_MODEL,
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Read Edit Write Glob Grep",
           "--add-dir", os.path.dirname(transcript), logdir]

    if os.environ.get("WORKSPACE_REVIEW_DRYRUN"):
        print("[skill_review dry-run] lanzaría:")
        print("  cwd =", brain)
        print("  cmd =", cmd)
        if findings:
            print("  guard N6 (log-only): %d finding(s) → %s" % (
                len(findings), [f["class"] for f in findings]))
        return

    try:
        open(tp, "w").close()  # marca el throttle ANTES de lanzar (evita ráfagas)
    except Exception:
        pass
    env = dict(os.environ)
    env["WORKSPACE_REVIEW_RUNNING"] = "1"     # rompe la recursión en el claude hijo
    env["WORKSPACE_NO_AUTOUPDATE"] = "1"
    try:
        runlog = open(os.path.join(logdir, "_run.log"), "a")
    except Exception:
        runlog = subprocess.DEVNULL
    # Detached cross-platform: start_new_session es POSIX-only (en Windows lanza
    # ValueError); allá se usa DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP (0x208),
    # el mismo patrón que front.py cmd_dev.
    kw = {"creationflags": 0x208} if os.name == "nt" else {"start_new_session": True}
    try:
        subprocess.Popen(cmd, cwd=brain, env=env, stdin=subprocess.DEVNULL,
                         stdout=runlog, stderr=runlog, **kw)
    except Exception:
        return


if __name__ == "__main__":
    main()
