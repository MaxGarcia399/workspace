"""OFERTA: aparta el MEMORY.md y la carpeta memory/ sueltos en la raíz de los
cerebros que usan OpenClaw.

OpenClaw carga en CADA turno el MEMORY.md de la raíz de su workspace (en
Workspace, el cerebro) y escribía ahí su memoria propia. Esa memoria está
apagada en el perfil de Workspace y el cierre de cada sesión aparta lo que
OpenClaw toque, pero un cerebro que ya usaba OpenClaw puede tener los de
antes: OpenClaw los sigue leyendo como si fueran la memoria del agente, y no
lo son (la memoria del agente es STATE/MEMORY.md, la de todos los motores).

Qué hace (KIND "offer": solo si el socio la acepta con `workspace migrate
--offer`; con `--decline` deja de ofrecerse): en cada cerebro registrado que
usa OpenClaw en esta máquina (su motor, o alguna pestaña atada a OpenClaw),
MUEVE esos dos a motores/openclaw/ (con fecha si ya hay uno ahí), con la
misma función del cierre (memoria.mover_raiz_openclaw). Nunca borra nada.
Correrla otra vez no hace nada. Una versión anterior no lee lo que se movió.
"""
import os

TITLE = {"es": "Apartar el MEMORY.md suelto de los cerebros que usan OpenClaw (lo carga en "
               "cada turno y no es la memoria del agente)",
         "en": "Move aside the loose MEMORY.md of brains used with OpenClaw (it loads it on "
               "every turn and it isn't the agent's memory)"}
KIND = "offer"
MID = "202610200100_openclaw_memoria_suelta"


def _inside(path, root):
    p = os.path.normcase(os.path.realpath(path))
    r = os.path.normcase(os.path.realpath(root))
    return p == r or p.startswith(r + os.sep)


def _cerebros(ctx):
    """[(nombre, cerebro, [sueltos])] únicos, fuera del harness, que usan
    OpenClaw y tienen algo suelto."""
    from engines import openclaw as oc
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key in seen or _inside(brain, ctx.root):
            continue
        seen.add(key)
        sueltos = oc.memoria_suelta(brain)
        if sueltos and oc.used_by(brain, name=name):
            out.append((name, brain, sueltos))
    return out


def needed(ctx):
    return bool(_cerebros(ctx))


def run(ctx):
    import memoria
    from engines import openclaw as oc
    for name, brain, sueltos in _cerebros(ctx):
        if getattr(ctx, "dry_run", False):
            ctx.log("%s: se movería %s a motores/openclaw/" % (name, ", ".join(sueltos)))
            continue
        movidos = memoria.mover_raiz_openclaw(brain, 0)
        quedan = oc.memoria_suelta(brain)
        if quedan:
            raise RuntimeError("no pude mover %s de %s (¿abierto en otro programa?)"
                               % (", ".join(quedan), name))
        ctx.log("%s: %s → %s" % (name, ", ".join(sueltos), ", ".join(movidos)))
