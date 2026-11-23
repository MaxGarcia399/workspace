"""AUTOMÁTICA: las skills de la guía mandan a las pantallas nuevas del hub.

Las cuatro skills de la guía (configurar-workspace, personalizar-workspace,
reparar-workspace y calendario-y-tareas) llegaron a los cerebros en la 0.9.2
o al crear un agente, y mandaban al socio a pantallas de antes («Motores →
cuenta y proveedor», «Personalización», `workspace bienvenida`). La plantilla
nueva (1.1.0) manda a las del hub (Motores, Ajustes › Apariencia, Agentes ›
Tono, Calendario, Ajustes › Actualizaciones). Un cerebro que ya existía no se
recrea: esta migración cambia cada copia por la versión nueva
(skills_puertas_nuevas) SOLO si es, byte por byte, una versión anterior de la
plantilla con sus datos llenos; la nueva lleva los mismos (nombre, cara y
fecha). Una copia que el socio o su agente editaron no se toca. Con respaldo
previo (copia exacta) en
`<estado>/backups/202611221218_skills_puertas_nuevas/<agente>-<hash>/skills/`.
Para deshacer, copiar el respaldo encima. No borra nada. Se entrega una vez
por cerebro (`.workspace/skills-puertas-nuevas.json`): lo que el socio cambie
después no se vuelve a tocar.

Las otras dos puertas (cargar un agente y `workspace doctor --fix`) hacen lo
mismo, porque el sello de la migración es por máquina.

Compatibilidad hacia atrás: es el texto de una skill. Una versión anterior lo
lee como cualquier otra skill; sus comandos (`workspace tono`, `workspace
calendario`…) siguen existiendo en ella.
"""
import os

TITLE = {"es": "Las skills de la guía de tus agentes mandan a las pantallas nuevas del hub",
         "en": "Your agents' guide skills point to the hub's new screens"}
KIND = "auto"
MID = "202611221218_skills_puertas_nuevas"


def _brains(ctx):
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key not in seen:
            seen.add(key)
            out.append((name, brain))
    return out


def needed(ctx):
    import skills_puertas_nuevas
    return any(skills_puertas_nuevas.trabajos(brain, ctx.root) for _name, brain in _brains(ctx))


def run(ctx):
    import skills_puertas_nuevas
    for name, brain in _brains(ctx):
        try:
            hechos = skills_puertas_nuevas.actualizar(
                brain, root=ctx.root, state_dir=ctx.state_dir, name=name, dry_run=ctx.dry_run,
                log=lambda m, n=name: ctx.log("%s: %s" % (n, m)))
        except Exception as e:
            ctx.log("%s: skills de la guía sin poner al día (%s: %s)" % (name, type(e).__name__, e))
            continue
        if hechos and not ctx.dry_run:
            ctx.log("%s: las skills de la guía ya mandan a las pantallas nuevas (%s; respaldo guardado)"
                    % (name, ", ".join(hechos)))
