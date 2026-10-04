#!/usr/bin/env python3
"""WORKSPACE · skill_loop — loop medido de skills F1-F3 (N5, cierra el lazo N4).

EL AGREGADOR del loop de auto-mejora (loop-automejora-skills §4, estación ④
"curar por dato"): junta las señales que el harness YA produce — uso N12
(`.usage.json`), veredicto+historial N4 (`.audit.json`), propuestas Y11/N4
(`skills/_propuestas/`) — en una vista de "¿esta skill sirve?" y la deja
frente a un humano. NO mide nada nuevo, NO invoca ningún LLM, NO toca el
catálogo vivo: consume, agrega, recomienda. Tres piezas:

F1 — EFECTIVIDAD COMO DATO (`skills-events.jsonl`):
  Registro append-only de eventos del ciclo de vida de las skills, derivado
  por diff de las señales existentes (sidecars + propuestas + _archive/).
  PLACEMENT (análisis events.py §1.3.1 — conocimiento→vault, ejecución→local):
    · el STREAM de eventos es EJECUCIÓN: derivado y reconstruible desde los
      sidecars + git (regla 2 del foso: lo derivado jamás es fuente de
      verdad) y de churn alto → vive PER-MÁQUINA en
      ~/.claude/workspace/skill-loop/<enc>/skills-events.jsonl (gitignored
      por ubicación). El diseño fuente sugería STATE/; se desvía a
      propósito: cada línea al vault sería ruido de git sin valor de equipo.
    · el DATO CURADO del equipo SÍ va al vault: ya viaja en los sidecars
      versionados (N12/N4) y en el reporte F2 (STATE/skills-report.md) —
      el conocimiento, no el log.
  SCHEMA (una línea JSON por evento):
    {"ts": "<ISO-8601 UTC>", "schema": 1, "event": "<tipo>",
     "skill": "categoría/nombre" | null, "brain": "/ruta/del/cerebro",
     "source": "usage|audit|propuestas|archive|loop", …payload}
  Vocabulario v1 (cerrado — un evento fuera de la lista no se escribe):
    usada / vista / mejorada (patch aplicado) / propuesta (skill nueva o
    mejora en _propuestas/) / auditada (veredicto N4 nuevo) / archivada
    (un HUMANO la movió a _archive/) / rollback_preparado / revertida
    (rollback confirmado por humano) / reporte (corrida F2).
  El cursor (idempotencia del diff) vive junto al log: cursor.json.

F2 — CURACIÓN POR DATO (reporte, sin acción):
  `run()` clasifica el catálogo cruzando uso + veredicto + historial +
  propuestas pendientes y escribe STATE/skills-report.md (vía el chokepoint
  `dream._write_brain_file`: MEMORY.md/BOOT vetados + secret-scan N14, bajo
  lock N8). Estados: mantener · propuesta_pendiente · vigilar ·
  candidata_archivar · posible_regresion · protegida (provenance). El
  reporte es REGENERABLE (se sobreescribe por corrida) y queda versionado
  en el git del cerebro. Ninguna clasificación ejecuta nada.

F3 — REVERSIÓN POR GIT CON GATE HUMANO (🔴 lo más sensible):
  `--rollback categoría/nombre` PREPARA el rollback de una skill a una
  versión previa usando el git del cerebro (linaje trazable, DGM §3.1):
  identifica el commit (el previo que tocó la skill, o `--to <commit>`),
  muestra el DIFF completo de lo que cambiaría, y se detiene. Ejecutar =
  REPETIR el comando con `--confirm` (la confirmación explícita del humano,
  jamás implícita): restaura los archivos vía `git checkout <commit> -- …`
  en el WORKING TREE, sin commit (el humano revisa y commitea/descarta).
  FLUJO COMPLETO: el loop detecta "esta mejora empeoró la skill" (caída de
  score tras un patch, F2) → el reporte propone el rollback con el comando
  exacto → el humano revisa el diff (--rollback sin --confirm) → el humano
  aprueba (--confirm) → git restaura → nota al canal humano del cerebro.
  El pipeline JAMÁS revierte solo; ninguna corrida nocturna pasa --confirm.

GUARDA ANTI-GOODHART (loop-automejora-skills §3.6 — DGM reward-hackeó; SICA
mide con utilidad compuesta; el LLM-judge sesga al falso positivo):
  · Las recomendaciones son SEÑALES para el humano, no verdad: ningún número
    de este módulo es un objetivo a optimizar.
  · USO BAJO ≠ INÚTIL: una skill poco usada puede ser estacional o de
    caso-de-borde crítico — la candidatura a archivar viene del VEREDICTO
    del juez (que ya exige obsoleta/rota ADEMÁS de sin uso), nunca de la
    frecuencia sola, y aun así es solo recomendación.
  · Muestra chica = etiqueta `muestra: low` y estado `vigilar` — ninguna
    recomendación dura con pocos datos (small-sample bias, §5 del diseño).
  · La defensa final es el GATE HUMANO: archivar/mejorar/revertir pasan
    todos por una decisión humana explícita.

GATES (duros, ninguno relajable):
  · El catálogo vivo `skills/<categoría>/` NUNCA se muta automáticamente:
    F1/F2 son solo-lectura sobre él; F3 solo escribe con --confirm humano.
  · NEVER-DELETE: nada se borra ni se mueve; el rollback solo RESTAURA
    contenido (archivos nuevos posteriores al commit objetivo se conservan).
  · PROVENANCE (Y5): skills `created_by: max/fer/mau` = intocables (sin
    recomendaciones, sin rollback).
  · Sidecars `.usage.json`/`.audit.json` NO se revierten (son señal del
    presente, no contenido de la skill).
  · MEMORY.md / BOOT/ vetados: toda escritura al cerebro pasa por el
    chokepoint `dream._write_brain_file` (+ lock N8).

DISPARO (manual hoy; el cron es C6):
    python3 skill_loop.py --brain "/ruta/al/CEREBRO"
        [--dry-run] [--status]
        [--rollback categoría/nombre [--to <commit>] [--confirm]]

Contrato de salida parseable (Y15) — líneas `LOOP:`:
    LOOP: PLAN — N skills · P protegidas (socio) · A auditadas · U con uso
    LOOP: EVENTOS — +N evento(s) nuevos → <ruta del jsonl>
    LOOP: REPORTE — STATE/skills-report.md (mantener X · propuesta Y · …)
    LOOP: DRYRUN — emitiría N evento(s); reporte a stdout, nada se escribe
    LOOP: ROLLBACK-PREP:<skill> — a <hash> (diff N líneas; ejecutar = --confirm)
    LOOP: ROLLBACK-OK:<skill> — restaurada a <hash> (working tree, SIN commit)
    LOOP: ROLLBACK-GATE:<skill> — <por qué no>
    LOOP: ERROR — <razón>

Cero dependencias (stdlib, 3.9+). Mac y Windows. Falla-suave: el log de
eventos jamás tumba al caller; un cerebro sin git solo pierde F3. Amputable
(C10): borrar este archivo apaga el loop; nada más lo importa.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# dream.py aporta el chokepoint de escrituras al cerebro (veto MEMORY/BOOT +
# secret-scan N14), el lock N8 y _brain_enc; skill_audit/usage son las
# fuentes de señal que este módulo AGREGA (no duplica).
import dream
from dream import ForbiddenWrite                       # noqa: F401 (patchable)
import skill_audit                 # N4 — read_audit, catálogo, provenance
import usage as usage_mod          # N12 — read_usage

# ── constantes ─────────────────────────────────────────────────────────────
SCHEMA = 1
EVENTS_NAME = "skills-events.jsonl"
CURSOR_NAME = "cursor.json"
REPORT_REL = "STATE/skills-report.md"

# vocabulario v1 del ciclo de vida (cerrado; ver docstring F1)
EVENT_TYPES = ("usada", "vista", "mejorada", "propuesta", "auditada",
               "archivada", "rollback_preparado", "revertida", "reporte")

# muestra (small-sample bias, diseño §5): low <3 · med 3-7 · high ≥8
MUESTRA_MED = 3
MUESTRA_HIGH = 8

# caída de score entre audits consecutivos que dispara "posible_regresion"
REGRESSION_DROP = 15
# veredictos "peores que mantener" para detectar empeoramiento categórico
WORSE_VERDICTS = ("reescritura", "archivar")

MAX_DIFF_LINES = 400               # cota de lo que se imprime del diff
GIT_TIMEOUT = 30                   # s por comando git (local, sin red)

# archivos que el rollback JAMÁS toca (señal del presente, no contenido)
ROLLBACK_SKIP_BASENAMES = (usage_mod.SIDECAR_NAME, skill_audit.SIDECAR_NAME)

ESTADO_ORDEN = ("posible_regresion", "candidata_archivar",
                "propuesta_pendiente", "vigilar", "mantener", "protegida")


# ══════════════════════════════════════════════════════════════════════════
#  F1 — skills-events.jsonl (índice local append-only + cursor)
# ══════════════════════════════════════════════════════════════════════════
def _loop_dir(enc):
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "skill-loop", enc)


def events_path(enc):
    return os.path.join(_loop_dir(enc), EVENTS_NAME)


def _cursor_path(enc):
    return os.path.join(_loop_dir(enc), CURSOR_NAME)


def _utcnow_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def log_event(brain, event, skill=None, source="loop", **payload):
    """Anexa UN evento del ciclo de vida al skills-events.jsonl del cerebro.

    Solo vocabulario v1 (EVENT_TYPES) — un evento desconocido no se escribe.
    Best-effort absoluto: devuelve la ruta del log o None, JAMÁS levanta
    (un rastro caído no puede tumbar una corrida)."""
    try:
        if event not in EVENT_TYPES:
            return None
        enc = dream._brain_enc(brain)
        d = _loop_dir(enc)
        os.makedirs(d, exist_ok=True)
        rec = dict(payload)
        rec["ts"] = _utcnow_iso()
        rec["schema"] = SCHEMA
        rec["event"] = event
        rec["skill"] = skill
        rec["brain"] = str(brain)
        rec["source"] = source
        path = events_path(enc)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # espejo al rastro unificado del harness (N10, §1.3.1): este índice
        # sigue siendo el FUNCIONAL (cursor de sync_events); la actividad
        # vive además en el stream común que lee el dashboard
        try:
            import events as _harness_events
            mirror = dict(payload)
            mirror["event"] = "skill-" + event
            if skill:
                mirror["skill"] = skill
            _harness_events.record("agent_step", mirror,
                                   source="skill_loop.py", brain=str(brain))
        except Exception:
            pass
        return path
    except Exception:
        return None


def _load_cursor(enc):
    try:
        with open(_cursor_path(enc), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cursor(enc, cursor):
    path = _cursor_path(enc)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cursor, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def _pending_proposals(brain):
    """Propuestas vivas en skills/_propuestas/ (la salida gated de Y11/N4):
    [{id, tipo, target, rel}] — `target` = skill objetivo (mejoras N4) o
    None (skills nuevas del review). Solo lectura, falla-suave."""
    out = []
    root = os.path.join(brain, "skills", "_propuestas")
    if not os.path.isdir(root):
        return out
    # mejoras del audit N4: _mejoras/*.md con frontmatter skill_objetivo:
    mejoras = os.path.join(root, "_mejoras")
    if os.path.isdir(mejoras):
        for f in sorted(os.listdir(mejoras)):
            if not f.endswith(".md"):
                continue
            target = _fm_field_of_file(os.path.join(mejoras, f),
                                       "skill_objetivo")
            out.append({"id": "_mejoras/" + f, "tipo": "mejora",
                        "target": target,
                        "rel": "skills/_propuestas/_mejoras/" + f})
    # skills nuevas del review (Y11): _propuestas/<nombre>/SKILL.md
    for d in sorted(os.listdir(root)):
        if d.startswith(("_", ".")):
            continue
        sdir = os.path.join(root, d)
        if os.path.isdir(sdir) and skill_audit._skill_file(sdir):
            out.append({"id": d, "tipo": "skill-nueva", "target": None,
                        "rel": "skills/_propuestas/" + d + "/"})
    return out


def _fm_field_of_file(path, field):
    """Campo escalar del frontmatter de UN archivo .md. Falla-suave."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read(16384)
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    block = text[3:end] if end != -1 else text[3:]
    for ln in block.splitlines():
        if ln.startswith(field + ":"):
            v = ln.split(":", 1)[1].strip().strip("'\"")
            return v or None
    return None


def _archived_names(brain):
    """Skills que un HUMANO ya movió a skills/_archive/ (gate ejercido)."""
    out = []
    root = os.path.join(brain, "skills", "_archive")
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        if any(f in filenames for f in usage_mod.SKILL_FILES):
            out.append(os.path.relpath(dirpath, root).replace(os.sep, "/"))
            dirnames[:] = []
    return sorted(out)


def sync_events(brain, dry_run=False):
    """F1: deriva los eventos NUEVOS desde la última corrida (diff de
    sidecars N12/N4 + propuestas + _archive/ contra el cursor) y los anexa
    al jsonl. Idempotente: una segunda corrida sin cambios emite 0.
    Devuelve (n_nuevos, eventos). Con dry_run=True no escribe nada."""
    enc = dream._brain_enc(brain)
    cursor = _load_cursor(enc)
    skills_cur = cursor.get("skills", {})
    new = []

    for e in skill_audit.catalog_entries(brain):
        name = e["name"]
        prev = skills_cur.get(name, {})
        u = usage_mod.read_usage(e["dir"])
        for field, ev in (("use_count", "usada"), ("view_count", "vista"),
                          ("patch_count", "mejorada")):
            now_n = int(u.get(field) or 0)
            delta = now_n - int(prev.get(field) or 0)
            if delta > 0:
                rec = {"event": ev, "skill": name, "source": "usage",
                       "n": delta, field: now_n}
                if ev == "mejorada" and u.get("last_patched"):
                    rec["last_patched"] = u["last_patched"]
                new.append(rec)
        audit = skill_audit.read_audit(e["dir"])
        if audit and audit.get("audited_at") and \
                audit.get("audited_at") != prev.get("audited_at"):
            new.append({"event": "auditada", "skill": name, "source": "audit",
                        "veredicto": audit.get("veredicto"),
                        "confianza": audit.get("confianza"),
                        "score": audit.get("score")})
        skills_cur[name] = {
            "use_count": int(u.get("use_count") or 0),
            "view_count": int(u.get("view_count") or 0),
            "patch_count": int(u.get("patch_count") or 0),
            "audited_at": (audit or {}).get("audited_at"),
        }

    seen_props = set(cursor.get("proposals", []))
    props = _pending_proposals(brain)
    for p in props:
        if p["id"] not in seen_props:
            new.append({"event": "propuesta", "skill": p["target"],
                        "source": "propuestas", "tipo": p["tipo"],
                        "rel": p["rel"]})
    seen_arch = set(cursor.get("archived", []))
    archived = _archived_names(brain)
    for name in archived:
        if name not in seen_arch:
            new.append({"event": "archivada", "skill": name,
                        "source": "archive"})

    if not dry_run:
        for rec in new:
            log_event(brain, rec.pop("event"), skill=rec.pop("skill"),
                      source=rec.pop("source"), **rec)
        cursor["schema"] = SCHEMA
        cursor["skills"] = skills_cur
        cursor["proposals"] = sorted({p["id"] for p in props} | seen_props)
        cursor["archived"] = sorted(set(archived) | seen_arch)
        cursor["synced_at"] = _utcnow_iso()
        try:
            _save_cursor(enc, cursor)
        except OSError:
            pass                    # falla-suave: el próximo sync re-emite
    return len(new), new


# ══════════════════════════════════════════════════════════════════════════
#  F2 — curación por dato (clasificación + reporte; CERO acción)
# ══════════════════════════════════════════════════════════════════════════
def _sample_label(u):
    n = int(u.get("use_count") or 0)
    if n >= MUESTRA_HIGH:
        return "high"
    return "med" if n >= MUESTRA_MED else "low"


def _detect_regression(audit, u):
    """¿El último cambio empeoró la skill? Señal: caída de score ≥
    REGRESSION_DROP o veredicto mantener→peor entre audits consecutivos
    (historial N4). Si hubo un patch entre ambos audits, se correlaciona
    (la señal del diseño: "esta mejora empeoró la efectividad").
    Devuelve dict o None. SEÑAL, no veredicto — el humano decide."""
    if not audit or not audit.get("history"):
        return None
    prev = audit["history"][0] or {}
    try:
        drop = int(prev.get("score")) - int(audit.get("score"))
    except (TypeError, ValueError):
        drop = 0
    worse = (prev.get("veredicto") == "mantener"
             and audit.get("veredicto") in WORSE_VERDICTS)
    if drop < REGRESSION_DROP and not worse:
        return None
    reg = {"prev_score": prev.get("score"), "score": audit.get("score"),
           "drop": drop, "prev_veredicto": prev.get("veredicto"),
           "veredicto": audit.get("veredicto"), "patch_correlado": False}
    lp = (u or {}).get("last_patched")
    if lp and prev.get("audited_at") and audit.get("audited_at") and \
            str(prev["audited_at"]) <= str(lp) <= str(audit["audited_at"]):
        reg["patch_correlado"] = True
        reg["last_patched"] = lp
    return reg


def _classify(row):
    """(estado, señales). Decisión por DATO, conservadora; jamás una acción.
    Orden: provenance > regresión > candidata_archivar > propuesta
    pendiente > vigilar (sin dato / muestra chica) > mantener."""
    senales = []
    if row["socio"]:
        return "protegida", ["created_by: %s — intocable" % row["socio"]]
    audit, u = row["audit"], row["usage"]
    if row["regresion"]:
        r = row["regresion"]
        s = "score %s→%s" % (r.get("prev_score"), r.get("score"))
        if r.get("prev_veredicto") != r.get("veredicto"):
            s += " · veredicto %s→%s" % (r.get("prev_veredicto"),
                                         r.get("veredicto"))
        if r.get("patch_correlado"):
            s += " · tras patch del %s" % str(r.get("last_patched"))[:10]
        return "posible_regresion", [s]
    if audit and audit.get("veredicto") == "archivar" \
            and not audit.get("protegida_curator"):
        senales = ["; ".join(audit.get("razones") or []) or "ver .audit.json"]
        return "candidata_archivar", senales
    if row["proposals"]:
        senales = ["%s: %s" % (p["tipo"], p["rel"]) for p in row["proposals"]]
        return "propuesta_pendiente", senales
    if audit and audit.get("veredicto") in ("mejora_menor", "reescritura"):
        return "propuesta_pendiente", [
            "veredicto %s (la propuesta puede haberse aplicado ya)"
            % audit["veredicto"]]
    if not audit:
        return "vigilar", ["sin auditar aún (N4 no la ha rotado)"]
    if row["muestra"] == "low":
        return "vigilar", ["muestra chica (use_count %d) — uso bajo ≠ inútil"
                           % int(u.get("use_count") or 0)]
    return "mantener", []


def analyze(brain):
    """Cruza TODAS las señales por skill del catálogo vivo. Solo lectura.
    Devuelve (rows, propuestas_pendientes)."""
    props = _pending_proposals(brain)
    by_target = {}
    for p in props:
        if p["target"]:
            by_target.setdefault(p["target"], []).append(p)
    rows = []
    for e in skill_audit.catalog_entries(brain):
        d = e["dir"]
        row = {"name": e["name"], "dir": d,
               "socio": (skill_audit.created_by(d)
                         if skill_audit.is_socio_skill(d) else None),
               "usage": usage_mod.read_usage(d),
               "audit": skill_audit.read_audit(d),
               "proposals": by_target.get(e["name"], [])}
        row["muestra"] = _sample_label(row["usage"])
        row["regresion"] = _detect_regression(row["audit"], row["usage"])
        row["estado"], row["senales"] = _classify(row)
        rows.append(row)
    return rows, props


def _counts(rows):
    c = {k: 0 for k in ESTADO_ORDEN}
    for r in rows:
        c[r["estado"]] = c.get(r["estado"], 0) + 1
    return c


def _rollback_cmd(brain, name, confirm=False):
    return ("python3 %s --brain \"%s\" --rollback %s%s"
            % (os.path.join(_HERE, "skill_loop.py"), brain, name,
               " --confirm" if confirm else ""))


def render_report(brain, rows, props, n_events=0):
    """El reporte de curación (markdown) — ranking + recomendaciones, todas
    gated. Regenerable: cada corrida lo reescribe entero."""
    today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    c = _counts(rows)
    by_estado = {}
    for r in rows:
        by_estado.setdefault(r["estado"], []).append(r)

    L = []
    L += [
        "# Skills — reporte de curación (loop medido N5)", "",
        "> Generado por `WORKSPACE/skill_loop.py` · %s · cerebro `%s`"
        % (today, os.path.basename(brain)),
        ">",
        "> **SEÑAL, NO VERDAD (guarda anti-Goodhart).** Este reporte agrega "
        "señales débiles —uso (N12), veredicto del juez frío (N4), historial "
        "y propuestas pendientes— en una vista de atención. Ninguna métrica "
        "de aquí es un objetivo a optimizar: **uso bajo ≠ inútil** (una "
        "skill puede ser estacional o de caso-de-borde crítico) y un score "
        "alto puede ser complacencia del juez. **Nada de lo listado se "
        "ejecuta solo**: mantener, mejorar, archivar y revertir son "
        "decisiones humanas, siempre.", "",
        "## Resumen", "",
        "- catálogo vivo: %d skills · %d protegidas (provenance socio)"
        % (len(rows), c["protegida"]),
        "- auditadas (N4): %d · con uso registrado (N12): %d"
        % (sum(1 for r in rows if r["audit"]),
           sum(1 for r in rows if int(r["usage"].get("use_count") or 0)
               + int(r["usage"].get("view_count") or 0) > 0)),
        "- estados: mantener %d · propuesta pendiente %d · vigilar %d · "
        "candidata a archivar %d · posible regresión %d"
        % (c["mantener"], c["propuesta_pendiente"], c["vigilar"],
           c["candidata_archivar"], c["posible_regresion"]),
        "- eventos nuevos en este ciclo (skills-events.jsonl local): %d"
        % n_events, "",
    ]

    L += ["## 🔴 Posibles regresiones — propuesta de rollback (gate humano)",
          ""]
    regs = by_estado.get("posible_regresion", [])
    if regs:
        for r in regs:
            L += ["- `%s` — %s" % (r["name"], "; ".join(r["senales"])),
                  "  - revisar el diff (solo prepara, no ejecuta): `%s`"
                  % _rollback_cmd(brain, r["name"]),
                  "  - ejecutar TRAS revisar (restaura por git, working "
                  "tree, sin commit): `%s`"
                  % _rollback_cmd(brain, r["name"], confirm=True)]
        L += ["", "> El pipeline JAMÁS revierte solo: `--confirm` es la "
              "aprobación humana explícita. El linaje queda en el git del "
              "cerebro."]
    else:
        L += ["- _sin regresiones detectadas en este ciclo_"]
    L += [""]

    L += ["## Propuestas pendientes de revisar (`skills/_propuestas/`)", ""]
    if props:
        for p in props:
            tgt = " → `%s`" % p["target"] if p["target"] else ""
            L += ["- [%s] `%s`%s" % (p["tipo"], p["rel"], tgt)]
        L += ["", "> Aprobar una mejora = aplicarla a mano (skill-improver) "
              "y borrar la nota; aprobar una skill nueva = moverla a su "
              "categoría y actualizar skills/README.md. Descartar = borrar "
              "la propuesta. El catálogo vivo no se toca solo."]
    else:
        L += ["- _sin propuestas pendientes_"]
    L += [""]

    L += ["## Candidatas a archivar (NEVER-DELETE — solo recomendación)", ""]
    cands = by_estado.get("candidata_archivar", [])
    if cands:
        for r in cands:
            u = r["usage"]
            a = r["audit"] or {}
            L += ["- `%s` — veredicto archivar (confianza %s, score %s): %s. "
                  "Uso: %s use / %s view · last_used: %s"
                  % (r["name"], a.get("confianza"), a.get("score"),
                     "; ".join(r["senales"]), u.get("use_count", 0),
                     u.get("view_count", 0), u.get("last_used") or "nunca")]
        L += ["", "> Archivar = un humano mueve la carpeta a "
              "`skills/_archive/` (NUNCA borrar). Antes de decidir, "
              "verificar que no sea caso-de-borde crítico o estacional: "
              "**uso bajo ≠ inútil**."]
    else:
        L += ["- _sin candidatas en este ciclo_"]
    L += [""]

    L += ["## Ranking (vista compuesta — orden de atención, no calificación)",
          "",
          "| skill | estado | veredicto (N4) | score | uso (use/view) | "
          "muestra | last_used |",
          "|---|---|---|---|---|---|---|"]
    orden = {e: i for i, e in enumerate(ESTADO_ORDEN)}
    for r in sorted(rows, key=lambda r: (
            orden.get(r["estado"], 99),
            -((r["audit"] or {}).get("score") or -1), r["name"])):
        a, u = r["audit"] or {}, r["usage"]
        L += ["| `%s` | %s | %s | %s | %s/%s | %s | %s |" % (
            r["name"], r["estado"], a.get("veredicto") or "—",
            a.get("score") if a.get("score") is not None else "—",
            u.get("use_count", 0), u.get("view_count", 0), r["muestra"],
            (u.get("last_used") or "—")[:10])]
    L += [""]

    prot = by_estado.get("protegida", [])
    if prot:
        L += ["## Protegidas (provenance — intocables para los pipelines)",
              ""]
        L += ["- `%s` — %s" % (r["name"], "; ".join(r["senales"]))
              for r in prot]
        L += [""]

    L += ["---",
          "> Gates vigentes: el catálogo vivo jamás se muta automáticamente "
          "· never-delete · rollback SOLO vía `skill_loop.py --rollback … "
          "--confirm` tras revisar el diff · skills de socio intocables · "
          "MEMORY.md/BOOT vetados (chokepoint dream). Reporte regenerable: "
          "cada corrida lo reescribe.", ""]
    return "\n".join(L)


def write_report(brain, text):
    """Escribe STATE/skills-report.md vía el chokepoint (veto MEMORY/BOOT +
    secret-scan N14) bajo lock N8. Sobrescribe: es una vista derivada."""
    path = os.path.join(brain, *REPORT_REL.split("/"))

    def _apply():
        dream._write_brain_file(brain, REPORT_REL, text)

    if dream.file_lock:
        with dream.file_lock(path, timeout=dream._lock_timeout()):
            _apply()
    else:
        _apply()


def run(brain, dry_run=False, out=print):
    """F1 (sync de eventos) + F2 (reporte de curación). Sin LLM, sin red,
    sin acción sobre el catálogo. Devuelve exit code."""
    brain = os.path.abspath(os.path.expanduser(brain))
    if not os.path.isdir(os.path.join(brain, "skills")):
        out("LOOP: ERROR — %s no parece un cerebro con skills/" % brain)
        return 2
    rows, props = analyze(brain)
    out("LOOP: PLAN — %d skills · %d protegidas (socio) · %d auditadas · "
        "%d con uso%s"
        % (len(rows), _counts(rows)["protegida"],
           sum(1 for r in rows if r["audit"]),
           sum(1 for r in rows
               if int(r["usage"].get("use_count") or 0) > 0),
           " [DRY-RUN]" if dry_run else ""))
    n_events, _ = sync_events(brain, dry_run=dry_run)
    report = render_report(brain, rows, props, n_events=n_events)
    if dry_run:
        out("LOOP: DRYRUN — emitiría %d evento(s); reporte a stdout, nada "
            "se escribe" % n_events)
        out(report)
        return 0
    out("LOOP: EVENTOS — +%d evento(s) nuevos → %s"
        % (n_events, events_path(dream._brain_enc(brain))))
    try:
        write_report(brain, report)
    except ForbiddenWrite as e:
        out("LOOP: ERROR — escritura vetada: %s" % e)
        return 1
    except Exception as e:
        out("LOOP: ERROR — reporte falló: %s" % e)
        return 1
    c = _counts(rows)
    log_event(brain, "reporte", source="loop", skills=len(rows),
              eventos=n_events, regresiones=c["posible_regresion"],
              candidatas=c["candidata_archivar"])
    out("LOOP: REPORTE — %s (mantener %d · propuesta %d · vigilar %d · "
        "candidata-archivar %d · regresión %d)"
        % (REPORT_REL, c["mantener"], c["propuesta_pendiente"],
           c["vigilar"], c["candidata_archivar"], c["posible_regresion"]))
    return 0


# ══════════════════════════════════════════════════════════════════════════
#  F3 — rollback por git con gate humano (🔴 jamás automático)
# ══════════════════════════════════════════════════════════════════════════
def _git(args, cwd):
    """git local (sin red). → (rc, stdout, stderr). Falla-suave: git ausente
    o timeout = rc≠0 con razón, jamás excepción."""
    exe = shutil.which("git")
    if not exe:
        return 127, "", "git no está en PATH"
    try:
        r = subprocess.run([exe] + list(args), cwd=cwd, timeout=GIT_TIMEOUT,
                           capture_output=True, stdin=subprocess.DEVNULL)
    except Exception as e:
        return 1, "", "fallo al invocar git: %s" % e
    return (r.returncode, r.stdout.decode("utf-8", errors="replace"),
            r.stderr.decode("utf-8", errors="replace"))


def _skill_history(top, rel):
    """Commits que tocaron la skill, nuevo→viejo: [{hash, date, subject}]."""
    rc, log, _ = _git(["log", "--format=%H|%cI|%s", "--", rel], top)
    if rc != 0:
        return []
    out = []
    for ln in log.splitlines():
        parts = ln.split("|", 2)
        if len(parts) == 3 and parts[0]:
            out.append({"hash": parts[0], "date": parts[1],
                        "subject": parts[2]})
    return out


def _files_at(top, commit, rel):
    """Archivos de la skill en `commit`, SIN sidecars/locks (no se revierten:
    son señal del presente). Rutas relativas al toplevel del repo."""
    rc, ls, _ = _git(["ls-tree", "-r", "--name-only", commit, "--", rel], top)
    if rc != 0:
        return []
    out = []
    for f in ls.splitlines():
        base = os.path.basename(f)
        if base in ROLLBACK_SKIP_BASENAMES or base.endswith(".lock"):
            continue
        if f.strip():
            out.append(f)
    return out


def prepare_rollback(brain, skill, to=None, confirm=False, out=print):
    """F3: PREPARA (y solo con confirm=True EJECUTA) el rollback de una
    skill a una versión previa vía el git del cerebro.

    Sin --confirm: identifica el commit objetivo, imprime el diff completo
    y el comando exacto para ejecutar — y NO toca nada. Con --confirm
    (la aprobación humana explícita): `git checkout <commit> -- <archivos>`
    en el working tree, SIN commit (el humano revisa y commitea/descarta).
    NEVER-DELETE: archivos nuevos posteriores al commit se conservan;
    sidecars no se revierten. Provenance: skills de socio, intocables."""
    brain = os.path.abspath(os.path.expanduser(brain))
    skill = (skill or "").strip().strip("/")
    entry = None
    for e in skill_audit.catalog_entries(brain):
        if e["name"] == skill:
            entry = e
            break
    if entry is None:
        out("LOOP: ERROR — skill '%s' no está en el catálogo vivo" % skill)
        return 2
    if skill_audit.is_socio_skill(entry["dir"]):
        out("LOOP: ROLLBACK-GATE:%s — created_by:%s (provenance Y5: "
            "intocable para el pipeline, incluso con --confirm)"
            % (skill, skill_audit.created_by(entry["dir"])))
        return 3

    rc, top, err = _git(["rev-parse", "--show-toplevel"], brain)
    if rc != 0:
        out("LOOP: ERROR — el cerebro no es un repo git (%s)"
            % (err.strip().splitlines() or ["?"])[0])
        return 1
    # realpath en ambos lados: en macOS git devuelve /private/var/… donde
    # el caller ve /var/… (symlink) — sin esto el relpath se escapa del repo
    top = os.path.realpath(top.strip())
    rel = os.path.relpath(os.path.realpath(entry["dir"]),
                          top).replace(os.sep, "/")

    history = _skill_history(top, rel)
    if not history:
        out("LOOP: ERROR — sin historial git para %s" % rel)
        return 1
    if to:
        rc, tv, err = _git(["rev-parse", "--verify", "--quiet",
                            str(to) + "^{commit}"], top)
        if rc != 0 or not tv.strip():
            out("LOOP: ERROR — commit '%s' no existe en el repo" % to)
            return 1
        target = tv.strip()
    else:
        if len(history) < 2:
            out("LOOP: ERROR — %s no tiene versión previa en git (un solo "
                "commit la toca); usar --to <commit> si aplica" % skill)
            return 1
        target = history[1]["hash"]      # el commit previo que tocó la skill
    t8 = target[:8]
    rc, head8, _ = _git(["rev-parse", "--short", "HEAD"], top)
    head8 = head8.strip() or "HEAD"

    files = _files_at(top, target, rel)
    if not files:
        out("LOOP: ERROR — la skill no existe en el commit %s (nada que "
            "restaurar; never-delete: tampoco se borraría lo actual)" % t8)
        return 1
    rc, diff, err = _git(["diff", "HEAD", target, "--"] + files, top)
    if rc != 0:
        out("LOOP: ERROR — git diff falló: %s" % err.strip()[:200])
        return 1
    if not diff.strip():
        out("LOOP: ROLLBACK-NADA:%s — sin diferencias contra %s (la skill "
            "ya está en ese estado)" % (skill, t8))
        return 0
    kept = [f for f in _files_at(top, "HEAD", rel) if f not in set(files)]

    out("LOOP: linaje de %s (git del cerebro — trazabilidad DGM):" % skill)
    for h in history[:6]:
        mark = " ← HEAD" if h is history[0] else (
            " ← OBJETIVO" if h["hash"] == target else "")
        out("  %s  %s  %s%s" % (h["hash"][:8], h["date"][:10],
                                h["subject"][:60], mark))
    out("LOOP: diff HEAD(%s) → %s (lo que el rollback aplicaría):"
        % (head8, t8))
    diff_lines = diff.splitlines()
    for ln in diff_lines[:MAX_DIFF_LINES]:
        out("  " + ln)
    if len(diff_lines) > MAX_DIFF_LINES:
        out("  [… %d líneas más — ver `git diff HEAD %s -- %s`]"
            % (len(diff_lines) - MAX_DIFF_LINES, t8, rel))
    if kept:
        out("LOOP: never-delete — se CONSERVAN (no existen en %s): %s"
            % (t8, ", ".join(kept)))
    out("LOOP: sidecars .usage.json/.audit.json NO se revierten (señal del "
        "presente)")

    if not confirm:
        log_event(brain, "rollback_preparado", skill=skill, source="loop",
                  target=t8, head=head8, files=len(files),
                  diff_lines=len(diff_lines))
        out("LOOP: ROLLBACK-PREP:%s — restauraría %d archivo(s) a %s "
            "(diff %d líneas). EJECUTAR = repetir con --confirm. El "
            "pipeline JAMÁS revierte solo."
            % (skill, len(files), t8, len(diff_lines)))
        return 0

    # ── solo aquí (confirm=True, decisión humana explícita) se escribe ──
    rc, _, err = _git(["checkout", target, "--"] + files, top)
    if rc != 0:
        out("LOOP: ERROR — git checkout falló: %s" % err.strip()[:200])
        return 1
    log_event(brain, "revertida", skill=skill, source="loop",
              target=t8, head=head8, files=len(files), confirmado=True)
    try:
        note = ("- [skill-loop] ROLLBACK ejecutado (confirmado por humano) "
                "`%s`: HEAD %s → %s (%d archivo(s), working tree SIN "
                "commit — revisar `git diff` y commitear o descartar). "
                "Sidecars conservados; linaje completo en el git del "
                "cerebro.\n" % (skill, head8, t8, len(files)))
        skill_audit._append_brain_locked(
            brain, skill_audit._notify_rel(brain), note)
    except Exception:
        pass                        # la nota es best-effort; el git ya trazó
    out("LOOP: ROLLBACK-OK:%s — restaurada a %s (%d archivo(s), working "
        "tree, SIN commit — revisar y commitear/descartar a mano)"
        % (skill, t8, len(files)))
    return 0


# ══════════════════════════════════════════════════════════════════════════
#  status + CLI
# ══════════════════════════════════════════════════════════════════════════
def status(brain, out=print):
    brain = os.path.abspath(os.path.expanduser(brain))
    if not os.path.isdir(os.path.join(brain, "skills")):
        out("LOOP: ERROR — %s no parece un cerebro con skills/" % brain)
        return 2
    rows, props = analyze(brain)
    c = _counts(rows)
    ep = events_path(dream._brain_enc(brain))
    try:
        with open(ep, encoding="utf-8") as fh:
            n_ev = sum(1 for _ in fh)
    except OSError:
        n_ev = 0
    report = os.path.join(brain, *REPORT_REL.split("/"))
    out("LOOP: STATUS — %s · %d skills · mantener %d · propuesta %d · "
        "vigilar %d · candidata %d · regresión %d · protegidas %d · "
        "propuestas pendientes %d · eventos %d · reporte %s"
        % (os.path.basename(brain), len(rows), c["mantener"],
           c["propuesta_pendiente"], c["vigilar"], c["candidata_archivar"],
           c["posible_regresion"], c["protegida"], len(props), n_ev,
           "sí" if os.path.isfile(report) else "aún no"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="skill_loop.py",
        description="Loop medido de skills (N5, F1-F3): agrega uso N12 + "
                    "veredictos N4 en eventos (skills-events.jsonl local) y "
                    "un reporte de curación (STATE/skills-report.md). "
                    "Rollback por git SOLO con --confirm (gate humano). "
                    "NEVER-DELETE; el catálogo vivo no se muta solo.")
    ap.add_argument("--brain", default=os.getcwd(),
                    help="ruta del cerebro (default: cwd)")
    ap.add_argument("--dry-run", action="store_true",
                    help="reporte a stdout, sin escribir nada (ni eventos)")
    ap.add_argument("--status", action="store_true",
                    help="estado del loop para este cerebro")
    ap.add_argument("--rollback", default=None, metavar="CAT/NOMBRE",
                    help="preparar el rollback de una skill (muestra el "
                         "diff; NO ejecuta sin --confirm)")
    ap.add_argument("--to", default=None, metavar="COMMIT",
                    help="commit objetivo del rollback (default: el previo "
                         "que tocó la skill)")
    ap.add_argument("--confirm", action="store_true",
                    help="EJECUTAR el rollback preparado (la aprobación "
                         "humana explícita; jamás lo pasa un proceso "
                         "automático)")
    args = ap.parse_args(argv)
    if args.rollback:
        return prepare_rollback(args.brain, args.rollback, to=args.to,
                                confirm=args.confirm)
    if args.status:
        return status(args.brain)
    return run(args.brain, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
