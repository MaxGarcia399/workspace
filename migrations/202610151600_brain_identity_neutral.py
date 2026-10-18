"""AUTOMÁTICA: la identidad de tus agentes pasa a BRAIN.md (formato de cerebro v2).

Desde esta versión la identidad de un agente vive en `BRAIN.md`, un archivo
neutral de motor. `CLAUDE.md` queda como un puntero más (contiene `@BRAIN.md`,
que Claude Code carga solo), igual que `AGENTS.md` y `GEMINI.md` ya lo eran
para los demás motores. Decisión del dueño (2026-10-15): se aplica SOLO, en la
misma actualización, a todos los cerebros registrados (clientes no técnicos).

Qué hace en cada cerebro registrado (brain_format.ensure_brain_format):
  respaldo → `BRAIN.md` = copia byte a byte de `CLAUDE.md` → `CLAUDE.md` pasa a
  puntero → agrega `motores/` (espacio previsto por motor) → renombra las líneas
  con el nombre anterior del producto que vengan TAL CUAL del template viejo.
Nunca borra. Un cerebro raro (identidad personalizada, enlace, conflicto de
sync, recién modificado…) se SALTA, se reporta y sigue funcionando con el
formato viejo: el código de esta versión lee los dos formatos. Las otras dos
puertas (cargar un agente, `workspace doctor --fix`) lo reintentan.

Compatibilidad hacia atrás: `CLAUDE.md` nunca se borra; una versión anterior de
Workspace sigue funcionando (Claude Code expande `@BRAIN.md` por su cuenta y los
demás motores llegan por la cadena de punteros). Deshacer:
`workspace migrate --undo 202610151600_brain_identity_neutral`.
"""
import json
import os

TITLE = {"es": "La identidad de tus agentes ahora vive en BRAIN.md (se movió sola, con respaldo)",
         "en": "Your agents' identity now lives in BRAIN.md (moved automatically, with a backup)"}
KIND = "auto"


def _brains(ctx):
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key in seen:
            continue                          # el mismo cerebro con dos nombres
        seen.add(key)
        out.append((name, brain))
    return out


def needed(ctx):
    import brain_format
    for name, brain in _brains(ctx):
        r = brain_format.ensure_brain_format(brain, state_dir=ctx.state_dir, name=name,
                                             dry_run=True)
        if r["changed"]:
            return True
    return False


def run(ctx):
    import brain_format
    report = []
    for name, brain in _brains(ctx):
        r = brain_format.ensure_brain_format(brain, state_dir=ctx.state_dir, name=name)
        report.append({"agent": name, "state": r["state"], "reason": r["reason"],
                       "changed": r["changed"], "legacy_lines": r["legacy_lines"]})
        if r["state"] in (brain_format.MIGRATED, brain_format.COMPLETED):
            ctx.log("%s: identidad movida a BRAIN.md (respaldo guardado)" % name)
        elif r["state"] in (brain_format.SKIPPED, brain_format.CONFLICT, brain_format.MISSING,
                            brain_format.ERROR):
            ctx.log("%s: se dejó como estaba — %s" % (name, r["reason"]))
    # Reporte por máquina para `workspace doctor` (un cerebro saltado o en
    # conflicto NO detiene la cola de migraciones: sigue funcionando con el
    # formato viejo y doctor lo muestra; `doctor --fix` lo reintenta).
    d = os.path.join(ctx.state_dir, "brain-format")
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, "last-run.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"mid": brain_format.MID, "brains": report}, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(d, "last-run.json"))


def undo(ctx):
    """`workspace migrate --undo <id>`: restaura el formato viejo SOLO donde nada
    cambió después de migrar. Devuelve [(cerebro, estado, mensaje)]."""
    import brain_format
    return brain_format.undo_all(ctx.state_dir)
