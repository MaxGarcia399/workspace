"""Aparta los plugins por cerebro y registra el compartido en el perfil de Workspace."""
import os

TITLE = {"es": "Una copia del plugin de Workspace para OpenClaw",
         "en": "One copy of the Workspace plugin for OpenClaw"}
KIND = "auto"
MID = "202611200100_openclaw_plugin_compartido"


def _es_local(ctx):
    import paths
    return os.path.realpath(ctx.state_dir) == os.path.realpath(paths.state_dir())


def _cerebros(ctx):
    from engines import openclaw as oc
    return dict.fromkeys(os.path.realpath(b) for b in
                         [*(b for _, b in ctx.brains()), *oc.cerebros_del_perfil()])


def needed(ctx):
    from engines import openclaw as oc
    if not _es_local(ctx):
        return False
    brains = _cerebros(ctx)
    if any(oc.plugin_owned(oc.legacy_plugin(b)) for b in brains):
        return True
    config = oc._profile_config()
    return bool(config and oc._paquete_activo() and not oc._plugin_ok(config)
                and any(oc.plugin_owned(oc.legacy_backup(b)) for b in brains))


def run(ctx):
    from engines import openclaw as oc
    if ctx.dry_run:
        ctx.log("OpenClaw: se apartarían las copias anteriores del plugin.")
        return
    if oc._paquete_activo():
        oc.asegurar_plugin()
    for brain in _cerebros(ctx):
        backup = oc.mover_plugin_anterior(brain)
        if backup:
            ctx.log("OpenClaw: plugin anterior apartado en %s." % backup)
    if oc._profile_config() is not None and oc._paquete_activo() and not oc.reparar_plugin():
        raise RuntimeError("perfil de OpenClaw inválido o pendiente de verificar")


def undo(ctx):
    from engines import openclaw as oc
    if not _es_local(ctx):
        return []
    brains = [b for b in _cerebros(ctx) if oc.plugin_owned(oc.legacy_backup(b))]
    if not brains:
        return []
    config = oc._profile_config()
    paths = oc._get_path(config, oc.PLUGIN_PATHS)
    remaining = [p for p in paths if not oc._same_path(p, oc.plugin_dir())] if isinstance(paths, list) else paths
    result = []
    if remaining != paths:
        # La entrada del plugin sigue siendo válida al quitar la ruta fija
        # solo si el CLI ya puede descubrir una copia por el camino anterior.
        profile_brains = {os.path.realpath(b) for b in oc.cerebros_del_perfil()}
        first = next((b for b in brains if b in profile_brains), None)
        exe = oc._exe()
        if not first or not exe:
            raise RuntimeError("no hay un agente del perfil para restaurar la copia anterior")
        result.append((first, "ok", oc.mover_plugin_anterior(first, deshacer=True)))
        try:
            if oc._set_batch(exe, [{"path": oc.PLUGIN_PATHS, "value": remaining}]) != 0:
                raise RuntimeError("no pude retirar la ruta compartida del perfil")
        except Exception:
            oc.mover_plugin_anterior(first)
            raise
        brains.remove(first)
    for brain in brains:
        moved = oc.mover_plugin_anterior(brain, deshacer=True)
        if moved:
            result.append((brain, "ok", moved))
    return result
