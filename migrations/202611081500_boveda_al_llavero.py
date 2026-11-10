"""AUTOMÁTICA: tus llaves de Workspace pasan del archivo en texto plano al
llavero del sistema (Llaves en macOS, DPAPI en Windows, Secret Service en
Linux con secret-tool).

Hasta 2026-11-08 la bóveda (`<estado>/secrets.local`) guardaba cada llave en
texto plano, 0600: cualquier programa de tu usuario —un agente incluido— o un
respaldo (Time Machine, Historial de archivos) la podía leer tal cual.

Qué hace (KIND "auto", sin preguntar): secret_store.migrar() — respalda el
archivo (cifrado con el mismo llavero; si no cabe, 0600 en `<estado>/boveda/`,
nunca en el cerebro), mueve cada valor al llavero, lo VERIFICA leyéndolo de
vuelta por el camino de lectura y solo entonces deja `secrets.local` sin
valores. El valor que Workspace usa no cambia; lo que el llavero ya tuviera
con el mismo nombre y otro valor se archiva (no se borra).

Falla-suave a propósito (excepción a la regla 5 del README): si el llavero no
está (cerrado, por SSH, Linux sin secret-tool) o algo falla, TODO queda como
estaba y funciona igual que hoy; no se lanza nada (la cola de ajustes no se
detiene por esto). secret_store vuelve a intentarlo al arrancar y en cada
escritura.

Compatibilidad hacia atrás (regla 3): una versión anterior solo lee
`secrets.local`. Por eso `workspace update --rollback` (updater.rollback),
con el código NUEVO y ANTES de volver, deshace las migraciones que la
versión destino no conoce (esta incluida): todo vuelve al archivo y la
versión anterior lo encuentra igual que antes. Un hub o un hook de la
versión anterior que siga abierto durante la actualización ve «sin llave»
hasta reiniciar y no puede escribir un `secrets.local` a medias (queda
SELLADO: una carpeta; secret_store._SELLO): nada se pierde ni se borra.

Deshacer: undo() = secret_store.deshacer(): todo vuelve a `secrets.local`,
lo de Workspace sale del llavero y el modo queda «file» (no se migra sola
otra vez; los respaldos y lo archivado se quedan).
"""
import os

TITLE = {"es": "Tus llaves de Workspace pasan del archivo al llavero de tu sistema",
         "en": "Your Workspace keys move from the file to your system keychain"}
KIND = "auto"
MID = "202611081500_boveda_al_llavero"
#: updater.rollback la deshace ANTES de volver a una versión que no la trae.
UNDO_AL_VOLVER = True


def _misma_maquina(ctx):
    """La bóveda de secret_store es la del estado de ESTA corrida (un HOME
    de prueba no toca otra)."""
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
    return secret_store.migracion_pendiente()


def run(ctx):
    import secret_store
    r = secret_store.migrar(timeout=5)
    if r.get("estado") == "hecho":
        ctx.log("bóveda: %d llave(s) al llavero (%s)" % (r.get("n", 0), r.get("donde")))
    else:
        # falla-suave: todo quedó como estaba; se reintenta al arrancar
        ctx.log("bóveda: sigue en el archivo (%s)" % r.get("estado"))


def undo(ctx):
    if not _misma_maquina(ctx):
        return []
    import secret_store
    if not secret_store._leer_indice():
        return []
    # volver a una versión anterior (updater.rollback): todo al archivo, pero
    # sin apagar la migración (la próxima versión que la conozca vuelve a
    # aplicarla); pedido por el socio: queda en «file» hasta reactivar
    r = secret_store.deshacer(apagar=getattr(ctx, "motivo", "") != "rollback")
    if r.get("ok"):
        return [("bóveda", "undone",
                 "tus %d llave(s) volvieron a %s (texto plano, solo tuyo); Workspace ya no "
                 "usa el llavero" % (r.get("n", 0), secret_store.store_path()))]
    if r.get("faltan"):
        return [("bóveda", "refused", "no pude leer del llavero ni del respaldo: %s; nada "
                 "cambió" % ", ".join(r["faltan"]))]
    return [("bóveda", "refused", "no pude deshacer (%s); nada cambió" % r.get("error", "?"))]
