"""AUTOMÁTICA: los cerebros que ya existen reciben la guía de skills.

Un agente nuevo sale de la plantilla con las skills para configurar,
personalizar y reparar Workspace. Uno que ya estaba no se recrea: esta
migración le copia solo las skills que le faltan (skills_de_plantilla) y
anota una línea en skills/README.md y skills/INDEX-LITE.md si todavía no las
nombran, con respaldo previo (copia exacta) de esos dos archivos en
`<estado>/backups/202611110130_skills_guia_agentes/<agente>-<hash>/` (para
deshacer, copiarla encima; sin copia no se toca el archivo). La skill que el
usuario ya tiene no se toca, aunque el texto sea distinto. No borra nada.

Las otras dos puertas (cargar un agente y `workspace doctor`) hacen lo mismo,
porque el sello de la migración es por máquina: un cerebro que llega después
no pasaría por aquí.

Compatibilidad hacia atrás: son archivos nuevos. Una versión anterior los
ignora. Quitarlos queda para dentro de dos versiones.
"""
import os

TITLE = {"es": "Tus agentes aprenden a configurar y reparar Workspace",
         "en": "Your agents learn how to configure and repair Workspace"}
KIND = "auto"
MID = "202611110130_skills_guia_agentes"


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
    return any(skills_de_plantilla.trabajos(brain, ctx.root) for _name, brain in _brains(ctx))


def run(ctx):
    import skills_de_plantilla
    for name, brain in _brains(ctx):
        try:
            hechos = skills_de_plantilla.actualizar(
                brain, root=ctx.root, state_dir=ctx.state_dir, name=name, dry_run=ctx.dry_run,
                log=lambda m, n=name: ctx.log("%s: %s" % (n, m)))
        except Exception as e:
            ctx.log("%s: skills de la guía sin cambiar (%s: %s)" % (name, type(e).__name__, e))
            continue
        if hechos and not ctx.dry_run:
            ctx.log("%s: skills de la guía copiadas (%s); las que ya estaban no se tocaron"
                    % (name, ", ".join(hechos)))
