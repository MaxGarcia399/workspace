"""AUTOMÁTICA: esta máquina sabe quién eres, en todos tus cerebros.

Hasta ahora cada cerebro decidía quién eres con `<cerebro>/.claude/socio.local`.
Ese archivo vive en una carpeta con punto: Obsidian no lo sincroniza (cada
máquina tenía el suyo, o ninguno) y otros métodos de sync sí (la otra persona
heredaba el tuyo). Sin él, Workspace tomaba «la única carpeta» de
`STATE/sessions/`, fuera de quien fuera.

Desde esta versión quién eres es de la MÁQUINA: `<estado>/identidad.json`
(identidad.py). Qué hace (KIND "auto", sin preguntar): lee el `socio.local` de
cada cerebro registrado, lo resuelve con las cédulas de ese cerebro (un nombre
viejo cae en el actual) y se queda con la persona que más cerebros declaran
(empate: la del cerebro con más pestañas), con sus otros nombres como alias.
Si ningún cerebro tiene `socio.local`, toma el de la máquina (`install
--socio`). Si nada dice quién eres, no escribe nada: la sección Usuarios lo
pregunta una vez («soy yo en esta PC»).

Nada de lo que ya veías cambia: un cerebro cuyo `socio.local` es OTRA persona
(la elegiste ahí a mano, o es el «owner» de un agente creado sin dueño y ya
tiene pestañas) recibe un override en identidad.json con esa persona, así
sus pestañas siguen saliendo en el menú.

Solo AGREGA a `identidad.json`: no toca ningún archivo de ningún cerebro (los
`socio.local` se quedan como están, para que la versión anterior los siga
leyendo tras un `workspace update --rollback`) y no pisa una identidad ni un
override que ya existan. Correrla de nuevo no cambia nada. Un cerebro que no
se puede leer (permisos, un `socio.local` que no está en UTF-8) se anota y se
salta: no detiene la cola. Juntar las carpetas duplicadas de la misma persona
pasa al abrir cada agente (una línea con su deshacer).
"""

TITLE = {"es": "Esta máquina sabe quién eres, en todos tus cerebros",
         "en": "This machine knows who you are, in all your brains"}
KIND = "auto"
MID = "202611051531_identidad_por_maquina"


def _propuesta(ctx, errores=None):
    import identidad
    return identidad.construir(ctx.brains(), state_dir=ctx.state_dir, errores=errores)


def needed(ctx):
    import identidad
    return identidad.pendiente(_propuesta(ctx), state_dir=ctx.state_dir)


def run(ctx):
    import identidad
    errores = []
    prop = _propuesta(ctx, errores)
    for b, motivo in errores:
        ctx.log("%s: %s (lo salté)" % (b, motivo))
    if not identidad.pendiente(prop, state_dir=ctx.state_dir):
        return
    if getattr(ctx, "dry_run", False):
        ctx.log("en esta máquina serías «%s»" % (prop["persona"]["nombre"] or "—"))
        return
    hecho = identidad.aplicar(prop, state_dir=ctx.state_dir)
    data = identidad.cargar(ctx.state_dir)
    if prop["persona"]["nombre"] and not data["persona"]["nombre"]:
        raise RuntimeError("no pude guardar quién eres en %s" % identidad.ruta(ctx.state_dir))
    for tipo, nombre, cerebro in hecho:
        if tipo == "persona":
            alias = data["persona"]["alias"]
            ctx.log("en esta máquina eres «%s»%s (%s)" % (
                nombre, (" · también: " + ", ".join(alias)) if alias else "", data["origen"]))
        else:
            ctx.log("en %s sigues siendo «%s» (lo que ya decía ese cerebro)" % (cerebro, nombre))
