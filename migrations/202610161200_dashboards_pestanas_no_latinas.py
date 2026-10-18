"""AUTOMÁTICA: los menús de pestañas guardados en tus cerebros encuentran la
memoria de las pestañas con nombre en coreano, chino, ruso u otro alfabeto.

El paso de marca de «crear agente» copia el menú de pestañas a
`<cerebro>/brand/<nombre>-dashboard.py` una sola vez. Las copias anteriores a
esta versión calculaban el nombre corto de la pestaña solo con letras
inglesas: en Claude Code una pestaña «도시 계획» no recibía su memoria.

Qué hace con cada agente registrado (agent_brand.refresh_brand_dashboards):
mira SOLO el menú que el agente usa (su `scripts.dashboard`, la misma
resolución que el arranque) y solo si vive dentro de su cerebro; las copias
sueltas que nadie ejecuta no se tocan. Regenera desde la plantilla SOLO sus
tres funciones de memoria de pestaña (`_slug`, `session_body`,
`render_context`), que pasan a usar agent_brand.slug, y solo si vienen tal
cual de una versión anterior de la plantilla (también las de memoria v1).
Desde memoria v1 la regeneración trae además su `render_context` de v1: con un
Workspace al día el menú calla y la memoria la da memoria.paquete. Un menú
editado a mano no se toca (`workspace doctor` lo señala; en un Workspace al
día el arranque igual le da su memoria por memoria.paquete y quita el bloque
viejo del menú). Respaldo de cada archivo en `<state_dir>/backups/<id>/` antes
de escribir. Idempotente. Nunca borra nada.

Se queda con su fecha (anterior a 202610162300/202610170100) a propósito: el
runner aplica toda migración SIN SELLO (migrate.py), no una marca de agua, así
que una máquina que ya corrió las de memoria v1 también corre esta, y la que ya
la corrió (con su sello) no la repite. No depende del orden: solo toca el menú.

Compatible hacia atrás (el cerebro viaja por Obsidian a máquinas con otra
versión): las funciones nuevas llaman a agent_brand.slug, que existe en toda
versión con menús de marca, y a agent_brand.session_memory SOLO si existe
(antes del 2026-10-10 no existía: ahí usan el cuerpo de la memoria tal cual,
como hacía la plantilla de entonces). Con un Workspace anterior, el menú
calcula su slug de siempre.
"""
import os

TITLE = {"es": "Los menús de pestañas de tus agentes encuentran la memoria de las "
               "pestañas con nombre en coreano, chino o ruso (con respaldo)",
         "en": "Your agents' tab menus now find the memory of tabs named in "
               "Korean, Chinese or Russian (with a backup)"}
KIND = "auto"
MID = "202610161200_dashboards_pestanas_no_latinas"


def _menus(ctx):
    """[(agente, cerebro, dashboard)]: el `scripts.dashboard` que cada agente
    registrado usa de verdad (misma resolución que el arranque), sin repetir
    cerebros (el mismo cerebro con dos nombres)."""
    import dispatch
    cfgs = {}
    try:
        for entry in dispatch.load_registry().get("agents", []):
            try:
                cfgs[entry["name"]] = dispatch.load_agent_cfg(entry)
            except Exception:
                continue
    except Exception:
        pass
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key in seen:
            continue
        seen.add(key)
        dash = dispatch.expand_scripts(cfgs.get(name) or {}, brain).get("dashboard", "")
        out.append((name, brain, dash))
    return out


def needed(ctx):
    import agent_brand
    return any(estado == "por actualizar"
               for _name, brain, dash in _menus(ctx)
               for _rel, estado in agent_brand.refresh_brand_dashboards(brain, dash,
                                                                        dry_run=True))


def run(ctx):
    import agent_brand
    respaldo = os.path.join(ctx.state_dir, "backups", MID)
    for name, brain, dash in _menus(ctx):
        for rel, estado in agent_brand.refresh_brand_dashboards(brain, dash,
                                                                backup_dir=respaldo):
            # «personalizado» o un error no detienen la cola: ese menú sigue
            # como estaba y doctor lo muestra
            ctx.log("%s: %s — %s" % (name, rel, estado))
