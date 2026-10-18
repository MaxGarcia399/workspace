"""AUTOMÁTICA: la memoria de las pestañas pasa a ser de Workspace (memoria v1).

Desde esta versión el agente guarda la memoria de cada pestaña con
`workspace memoria nota` (con etiqueta: decisión, pendiente, hecho…) y
Workspace la ordena sola, sin IA: lo vigente arriba, lo viejo al archivo, y
una «maleta» con lo último de cada motor para seguir en otro. La instrucción
vieja («haz append a ## Historial a mano») queda retirada.

Qué hace en cada cerebro registrado (memoria_textos.actualizar), SOLO si el
archivo sigue igual que como lo dejó alguna versión de la plantilla de
Workspace (lo que el socio personalizó no se toca):
  · `STATE/sessions/README.md` → la explicación nueva.
  · La sección «2.5 Memoria de sesión» de la identidad → el texto nuevo.
Antes de cambiar nada se copia a `<estado>/backups/<id>/<agente>-<hash>/`. Si el
cerebro tiene sus propios textos, el paquete que Workspace inyecta al abrir
cada pestaña ya dice cómo guardar y que reemplaza la instrucción vieja. Las
otras dos puertas (cargar un agente, `workspace doctor --fix`) lo llevan a los
cerebros que lleguen después.

Compatibilidad hacia atrás: los textos nuevos viajan por Obsidian a máquinas
que pueden tener la versión anterior, donde `workspace memoria nota` no existe
(«invalid choice: 'nota'»). Por eso también dicen qué hacer ahí: agregar una
línea fechada al final de `## Historial`, como antes; la versión nueva la lee
como una nota más. `workspace memoria checkpoint` existe en las dos.
"""
import os

TITLE = {"es": "Tus agentes guardan la memoria de cada pestaña igual en todos los motores",
         "en": "Your agents keep each tab's memory the same way on every engine"}
KIND = "auto"
MID = "202610170100_memoria_v1"

# Marcas de la plantilla anterior (no aparecen en un README propio)
_README_VIEJO = ("## Dos capas: live journal vs destilado mensual", "### Capa 1 — Live journal")
_P25_VIEJO = ("Un archivo por pestaña + socio: `STATE/sessions/<socio>/<slug>.md`. El hook de arranque\n"
              "inyecta la sesión activa vía `$WORKSPACE_WS`. Al cerrar trabajo significativo: append fechado\n"
              "a `## Historial` + actualizar frontmatter. Solo toco `STATE/sessions/<socio-activo>/`.\n"
              "Convención completa: `STATE/sessions/README.md`.")


def _brains(ctx):
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key not in seen:
            seen.add(key)
            out.append((name, brain))
    return out


def needed(ctx):
    import memoria_textos
    return any(memoria_textos.trabajos(brain, ctx.root) for _name, brain in _brains(ctx))


def run(ctx):
    import memoria_textos
    for name, brain in _brains(ctx):
        try:
            hechos = memoria_textos.actualizar(brain, root=ctx.root, state_dir=ctx.state_dir,
                                               name=name, dry_run=ctx.dry_run)
        except Exception as e:                # las otras dos puertas lo reintentan
            ctx.log("%s: textos de memoria sin cambiar (%s: %s)" % (name, type(e).__name__, e))
            continue
        if hechos and not ctx.dry_run:
            ctx.log("%s: textos de memoria actualizados (%s; respaldo en la máquina)"
                    % (name, ", ".join(rel.replace(os.sep, "/") for rel in hechos)))
