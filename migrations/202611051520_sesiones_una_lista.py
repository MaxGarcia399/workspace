"""AUTOMÁTICA: tus pestañas salen de una sola lista, la del cerebro (sesiones v2).

Antes el menú de pestañas juntaba los `.md` del cerebro (viajan entre tus
máquinas) con `.claude/<agente>-workspaces.json`, que es de cada máquina y no
viaja. Lo que vivía solo en ese json aparecía solo en esa máquina (pruebas
viejas en una PC) y, peor, se volvía a sembrar como `.md` en el cerebro: por
eso una pestaña quitada a mano regresaba.

Qué hace (KIND "auto", sin preguntar), por cada cerebro registrado y cada
`.claude/<agente>-workspaces.json` que tenga:
  · el id de Claude Code y el last_opened de cada pestaña que SÍ tiene `.md`
    pasan al estado local de esta máquina (`sessions-local.json`);
  · las entradas SIN `.md` NO se siembran: quedan anotadas como `huerfanas`
    en ese mismo estado local, para deshacer (`workspace sesiones desarchivar
    <nombre>` le siembra su `.md` con su id).
El json no se toca (expandir → contraer): los dashboards y hooks de una
versión anterior lo siguen leyendo. Correrla de nuevo no cambia nada (es la
misma función que corre, perezosa, cada vez que se listan las pestañas:
sessions_registry.absorber_json_local). No escribe en el cerebro.
"""
import glob
import os

TITLE = {"es": "Tus pestañas salen de una sola lista, la del cerebro",
         "en": "Your tabs come from a single list, the brain's"}
KIND = "auto"
MID = "202611051520_sesiones_una_lista"

_SUFIJO = "-workspaces.json"


def _pares(ctx):
    """[(agente, cerebro)]: un par por cada `.claude/<agente>-workspaces.json`
    de los cerebros registrados (sin repetir cerebros)."""
    out, vistos = [], set()
    for _name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key in vistos:
            continue
        vistos.add(key)
        for p in sorted(glob.glob(os.path.join(brain, ".claude", "*" + _SUFIJO))):
            agent = os.path.basename(p)[:-len(_SUFIJO)]
            if agent:
                out.append((agent, brain))
    return out


def _store(ctx):
    return os.path.join(ctx.state_dir, "sessions-local.json")


def needed(ctx):
    return bool(_pares(ctx))


def run(ctx):
    import sessions_registry as reg
    for agent, brain in _pares(ctx):
        if ctx.dry_run:
            ctx.log("%s: pasaría los ids de su lista local al estado de esta máquina" % agent)
            continue
        r = reg.absorber_json_local(brain, agent, store=_store(ctx))
        if r.get("ids") or r.get("huerfanas"):
            ctx.log("%s: %d id(s) al estado local · %d sin memoria en el cerebro, "
                    "no se siembran" % (agent, r.get("ids", 0), len(r.get("huerfanas") or ())))
