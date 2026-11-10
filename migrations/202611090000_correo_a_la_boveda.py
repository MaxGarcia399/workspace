"""AUTOMÁTICA: la contraseña del correo (`workspace mail`) pasa de mail.json
(texto plano) a la bóveda de Workspace.

Hasta 2026-11-09 la App Password del correo vivía en
`<estado>/mail.json`, en texto plano, junto al usuario y el servidor (y en
Windows con los permisos heredados de la carpeta). Qué hace (KIND "auto",
sin preguntar, solo en la instalación activa):
secret_store.migrar_correo() — respalda mail.json (cifrado con el llavero;
si no, 0600 en `<estado>/boveda/`, que se borra al verificar), guarda la
contraseña en la bóveda con un nombre INTERNO (CORREO_PASS: jamás al entorno
del hub ni de un motor), la VERIFICA leyéndola de vuelta y solo entonces deja
mail.json sin ella (0600; en Windows, solo-dueño). Falla-suave: si algo
falla, mail.json queda como estaba y el correo funciona igual; se reintenta
al arrancar (secret_store.al_arrancar).

Compatibilidad hacia atrás: una versión anterior lee la contraseña de
mail.json, así que `workspace update --rollback` (updater.deshacer_para_volver)
corre undo() ANTES de volver: la contraseña vuelve a mail.json.
"""
import os

TITLE = {"es": "La contraseña del correo pasa de mail.json a la bóveda de Workspace",
         "en": "The mail password moves from mail.json to the Workspace vault"}
KIND = "auto"
MID = "202611090000_correo_a_la_boveda"
#: updater.rollback la deshace ANTES de volver a una versión que no la trae.
UNDO_AL_VOLVER = True


def _misma_maquina(ctx):
    try:
        import secret_store
        a = os.path.normcase(os.path.realpath(ctx.state_dir))
        b = os.path.normcase(os.path.realpath(secret_store._workspace_dir()))
        return a == b
    except Exception:
        return False


def needed(ctx):
    if not _misma_maquina(ctx):
        return False
    import secret_store
    return (secret_store._modo() != "archivo" and secret_store.instalacion_activa()
            and secret_store.correo_pendiente())


def run(ctx):
    import secret_store
    r = secret_store.migrar_correo(timeout=5)
    # falla-suave: si no se pudo, mail.json quedó como estaba; se reintenta al arrancar
    ctx.log("correo: %s" % r.get("estado"))


def undo(ctx):
    if not _misma_maquina(ctx):
        return []
    import secret_store
    r = secret_store.devolver_correo()
    if not r.get("ok"):
        return [("correo", "refused", "no pude devolver la contraseña del correo a mail.json; "
                 "nada cambió")]
    if r.get("n"):
        return [("correo", "undone", "la contraseña del correo volvió a %s"
                 % secret_store.correo_path())]
    return []
