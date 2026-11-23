"""AUTOMÁTICA: el renglón de la guía en skills/INDEX-LITE.md vuelve a caber.

La 0.9.2 (202611110130_skills_guia_agentes) le agregaba a INDEX-LITE.md, lo
de skills que se carga siempre (≤300 tokens), el bloque entero de la guía: en
un cerebro de la plantilla 0.9.0 lo dejaba en 1270 caracteres, más de los 1200
de su presupuesto, y la línea de la bandeja de aprendidas ya no cabía. Ahora
INDEX-LITE recibe la línea corta de la plantilla (skills_de_plantilla). Esta
migración cambia el bloque largo por esa línea en su lugar, solo si está tal
cual (LF o CRLF), con copia exacta previa en
`<estado>/backups/202611220230_guia_lite_corta/<agente>-<hash>/skills/` (para
deshacer, copiarla encima: el sello `.workspace/guia-agentes-corta.json` evita
que vuelva a acortarlo). skills/README.md no cambia. No borra nada.

Las otras dos puertas (cargar un agente y `workspace doctor`) hacen lo mismo,
porque el sello de la migración es por máquina.

Compatibilidad hacia atrás: la línea corta nombra las cinco skills de la guía,
así que una 0.9.2 la da por anotada y no vuelve a agregar el bloque largo.
"""
import os

TITLE = {"es": "El índice ligero de skills vuelve a caber en su presupuesto",
         "en": "The light skills index fits its budget again"}
KIND = "auto"
MID = "202611220230_guia_lite_corta"


def _brains(ctx):
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key not in seen:
            seen.add(key)
            out.append((name, brain))
    return out


def needed(ctx):
    import skills_de_plantilla
    return any(skills_de_plantilla.por_acortar(brain, ctx.root) for _name, brain in _brains(ctx))


def run(ctx):
    import skills_de_plantilla
    for name, brain in _brains(ctx):
        try:
            hechos = skills_de_plantilla.acortar(
                brain, root=ctx.root, state_dir=ctx.state_dir, name=name, dry_run=ctx.dry_run,
                log=lambda m, n=name: ctx.log("%s: %s" % (n, m)))
        except Exception as e:
            ctx.log("%s: renglón de la guía sin acortar (%s: %s)" % (name, type(e).__name__, e))
            continue
        if hechos and not ctx.dry_run:
            ctx.log("%s: el renglón de la guía en %s quedó más corto (con respaldo)" % (name, ", ".join(hechos)))
