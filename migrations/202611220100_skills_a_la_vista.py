"""AUTOMÁTICA: el cerebro dice cómo se usa una skill a la vista del socio.

Diagnóstico del 21-nov: pedida en palabras, algunos motores usaban la skill con
su propia herramienta de skills y no con `usar_skill`, así que la página y el
hub no la enseñaban. La plantilla nueva lo dice en BRAIN.md §5 y en
skills/INDEX-LITE.md; un cerebro que ya existía no se recrea: esta migración le
agrega ese párrafo a BRAIN.md §5 (skills_a_la_vista) si todavía no nombra
usar_skill. En INDEX-LITE.md (siempre cargado, con presupuesto) no agrega un
párrafo: su frase «→ cargar la skill → seguirla» pasa a «→ `usar_skill` →
seguirla» en su lugar, o, si el socio la cambió, una línea al final solo si cabe.
Con respaldo previo (copia exacta) en
`<estado>/backups/202611220100_skills_a_la_vista/<agente>-<hash>/`. Para
deshacer, copiar el respaldo encima. No borra nada y lo demás del archivo queda
igual. Se entrega una vez por cerebro (`.workspace/skills-a-la-vista.json`):
lo que el socio quite después no vuelve.

Las otras dos puertas (cargar un agente y `workspace doctor --fix`) hacen lo
mismo, porque el sello de la migración es por máquina.

Compatibilidad hacia atrás: es texto nuevo en el cerebro. Una versión anterior
lo lee como cualquier otro párrafo.
"""
import os

TITLE = {"es": "Tus agentes activan las skills a la vista (en la página y el hub)",
         "en": "Your agents start skills where you can see them (page and hub)"}
KIND = "auto"
MID = "202611220100_skills_a_la_vista"


def _brains(ctx):
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key not in seen:
            seen.add(key)
            out.append((name, brain))
    return out


def needed(ctx):
    import skills_a_la_vista
    return any(skills_a_la_vista.trabajos(brain, ctx.root) for _name, brain in _brains(ctx))


def run(ctx):
    import skills_a_la_vista
    for name, brain in _brains(ctx):
        try:
            hechos = skills_a_la_vista.actualizar(
                brain, root=ctx.root, state_dir=ctx.state_dir, name=name, dry_run=ctx.dry_run,
                log=lambda m, n=name: ctx.log("%s: %s" % (n, m)))
        except Exception as e:
            ctx.log("%s: cómo usar las skills a la vista, sin cambiar (%s: %s)" % (name, type(e).__name__, e))
            continue
        if hechos and not ctx.dry_run:
            ctx.log("%s: el cerebro ya dice cómo usar las skills a la vista (%s; respaldo guardado)"
                    % (name, ", ".join(hechos)))
