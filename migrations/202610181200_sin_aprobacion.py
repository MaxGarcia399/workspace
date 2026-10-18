"""AUTOMÁTICA: en tus cerebros nada espera a una persona (skills, memoria, identidad).

Decisión del dueño (2026-10-18): el proceso de skills, memoria e identidad no
tiene a nadie en medio. Un cliente no aprueba skills una por una, no confirma
lo que su agente anota en la memoria, no diseña a mano la personalidad del
agente y no contesta permisos del motor para tareas de rutina. El agente aplica
directo, lo deja recuperable y lo reporta en su línea 🧠. La plantilla nueva ya
lo dice; esta migración lleva lo mismo a los cerebros que ya existían.

Qué hace en cada cerebro registrado (sin_aprobacion.actualizar; nada se borra):
  · Reemplaza los bloques de texto viejos que pedían a una persona —aprobar
    skills en skills/_propuestas/, skills «intocables» de un socio, «si dudo,
    pregunto», confirmación para escribir la memoria (N2), diseñar a mano el
    SOUL, ofrecer un monitor que no existe— o un comando que el motor pregunta
    (usage.py, git commit, find | wc -l, memory_index.py) por el texto actual.
    SOLO si cada línea es IDÉNTICA a la de alguna versión de la plantilla; lo
    que el dueño editó no se toca (el paquete de arranque avisa al agente). Los
    registros históricos (log-recent, brain-version, MILESTONES) no se tocan.
  · `skills/_propuestas/README.md` y `skills/_propuestas/_mejoras/` (y las
    propuestas que el agente ya marcó integradas o archivadas) pasan a
    `skills/_archive/` con nombre por contenido.
Antes de cambiar nada se copia a `<estado>/backups/<id>/<agente>-<hash>/`.
Un cerebro que no se puede tocar (solo lectura, iCloud sin conexión) se salta
y se avisa: no frena a los demás ni a las migraciones siguientes. Las otras
dos puertas (cargar un agente, `workspace doctor --fix`) lo reintentan y
llevan lo mismo a los cerebros que lleguen después.

Cerebros compartidos (regla 4): cada máquina corre esto sobre su copia, quizá
antes de sincronizarse. Lo escrito sale solo del contenido (sin fechas ni
rutas) y lo archivado se nombra por su huella: todas llegan a los mismos bytes.

Compatibilidad hacia atrás: una versión anterior de Workspace lee los mismos
archivos sin problema; los textos nuevos solo piden herramientas de archivos
(sin subcomandos nuevos), así que también sirven en una máquina con la versión
anterior. skills/_propuestas/ la vuelve a crear esa versión si la necesita.
"""
import os

TITLE = {"es": "Tus agentes ya no esperan aprobación para sus skills, su memoria ni su identidad",
         "en": "Your agents no longer wait for approval for their skills, memory or identity"}
KIND = "auto"
MID = "202610181200_sin_aprobacion"


def _brains(ctx):
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key not in seen:
            seen.add(key)
            out.append((name, brain))
    return out


def needed(ctx):
    import sin_aprobacion
    return any(sin_aprobacion.pendiente(brain, ctx.root) for _name, brain in _brains(ctx))


def run(ctx):
    import sin_aprobacion
    for name, brain in _brains(ctx):
        try:
            hechos = sin_aprobacion.actualizar(brain, root=ctx.root, state_dir=ctx.state_dir,
                                               name=name, dry_run=ctx.dry_run,
                                               log=lambda m, n=name: ctx.log("%s: %s" % (n, m)))
        except Exception as e:                # las otras dos puertas lo reintentan
            ctx.log("%s: textos de aprobación sin cambiar (%s: %s); `workspace doctor --fix` "
                    "lo reintenta" % (name, type(e).__name__, e))
            continue
        if hechos and not ctx.dry_run:
            ctx.log("%s: ya nada espera aprobación (%s; respaldo en la máquina)"
                    % (name, ", ".join(hechos)))
