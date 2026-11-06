"""AUTOMÁTICA: tras actualizar, el archivo automático de pestañas espera N días.

Sesiones v2 archiva solas las pestañas sin usar en `sesiones.archivar_dias`
días (15 de fábrica). Hasta esta versión el último uso de una pestaña solo
quedaba en cada máquina (`last_opened`), así que el día de la actualización
casi todo parecería viejo: se archivarían de golpe muchas pestañas que sí se
usan, y como el archivo viaja, también desaparecerían en las otras máquinas.

Qué hace (KIND "auto", sin preguntar): si esta máquina ya tiene pestañas en
alguno de sus cerebros registrados y su estado local (`sessions-local.json`)
no tiene `archivar_desde`, lo pone con la fecha de hoy. El archivo automático
cuenta el último uso de cada pestaña como no anterior a esa fecha: en los
primeros N días nada se archiva solo, y mientras tanto cada pestaña que se
abre en cualquier máquina deja `usada: <fecha>` en su .md, el uso que sí
viaja. Una máquina nueva no recibe la marca (no tiene pestañas viejas
propias); la protege el `usada` que dejaron las demás.

Solo agrega una clave al estado local (expandir → contraer: una versión
anterior la ignora y la conserva). No escribe en el cerebro. Correrla de
nuevo no cambia nada: la fecha que ya está se respeta. Un estado local que
no se puede leer no se pisa.
"""
import datetime
import json
import os

TITLE = {"es": "Tras actualizar, el archivo automático de pestañas espera unos días",
         "en": "After updating, automatic tab archiving waits a few days"}
KIND = "auto"
MID = "202611052100_archivar_desde"


def _store(ctx):
    return os.path.join(ctx.state_dir, "sessions-local.json")


def _leer(path):
    """(dict, legible). Un archivo que no existe es legible y vacío."""
    if not os.path.exists(path):
        return {}, True
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return (data, True) if isinstance(data, dict) else ({}, False)
    except (OSError, ValueError):
        return {}, False


def _tiene_pestanas(brain):
    """¿Algún `.md` de pestaña en `STATE/sessions/<persona>/`?"""
    d = os.path.join(brain, "STATE", "sessions")
    try:
        carpetas = [x for x in os.listdir(d) if not x.startswith(("_", "."))
                    and os.path.isdir(os.path.join(d, x))]
    except OSError:
        return False
    for c in carpetas:
        try:
            if any(f.endswith(".md") and f != "README.md"
                   for f in os.listdir(os.path.join(d, c))):
                return True
        except OSError:
            continue
    return False


def needed(ctx):
    data, legible = _leer(_store(ctx))
    if not legible or data.get("archivar_desde"):
        return False
    return any(_tiene_pestanas(b) for _n, b in ctx.brains())


def run(ctx):
    import sessions_registry as reg
    from olock import file_lock
    path = _store(ctx)
    if not needed(ctx):
        return
    hoy = datetime.date.today().isoformat()
    if ctx.dry_run:
        ctx.log("pondría archivar_desde = %s en %s" % (hoy, path))
        return
    with file_lock(path, timeout=5):
        data, legible = _leer(path)
        if not legible or data.get("archivar_desde"):
            return
        data = reg._local_load(path)        # mismo formato que el resto del store
        data["archivar_desde"] = hoy
        if not reg._local_save(data, path):
            raise RuntimeError("no pude guardar archivar_desde en %s" % path)
    ctx.log("el archivo automático de pestañas empieza a contar desde %s" % hoy)
