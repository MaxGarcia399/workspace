"""AUTOMÁTICA: el .gitignore de tus cerebros deja fuera las conversaciones.

Sesiones v2 (nivel 2, opcional): con `sesiones.llevar_conversacion` prendido,
al cerrar una pestaña su conversación de Claude Code se guarda comprimida en
`motores/claude-code/conversaciones/<socio>/` del cerebro para retomarla en otra
máquina. Eso viaja por el sync del cerebro (Obsidian u otro), pero NUNCA debe
ir al espejo de git: una conversación puede traer una llave pegada.

Qué hace (KIND "auto", sin preguntar): a cada cerebro registrado le agrega al
final del `.gitignore` la línea `motores/*/conversaciones/` si le falta (la
misma función del instalador, install.ensure_gitignore). Va aunque el ajuste
esté apagado: así, el día que se prenda, ya está protegido. Solo agrega: no
borra ni reordena nada, y correrla de nuevo no cambia nada. Los errores son
POR CEREBRO: un `.gitignore` ilegible (no UTF-8), de solo lectura o cualquier
otro problema en un cerebro se anota en el log y se sigue con el siguiente;
jamás detiene la cola de migraciones (el instalador y «cargar agente» vuelven
a intentarlo con install.GITIGNORE_LINES). Un cerebro que vive dentro del
propio Workspace se salta. Una versión anterior lee el mismo archivo sin
problema (expandir → contraer).
"""
import os

TITLE = {"es": "El .gitignore de tus cerebros deja fuera las conversaciones",
         "en": "Your brains' .gitignore leaves the conversations out"}
KIND = "auto"
MID = "202611051947_conversaciones_fuera_de_git"
LINEAS = ["motores/*/conversaciones/"]


def _inside(path, root):
    p = os.path.normcase(os.path.realpath(path))
    r = os.path.normcase(os.path.realpath(root))
    return p == r or p.startswith(r + os.sep)


def _brains(ctx):
    """[(nombre, cerebro)] únicos, fuera del harness."""
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key in seen or _inside(brain, ctx.root):
            continue
        seen.add(key)
        out.append((name, brain))
    return out


def _missing(brain):
    """Líneas que faltan; None si el .gitignore no se puede leer (o lo que sea
    que falle al leerlo: nunca lanza)."""
    import install
    try:
        return install.gitignore_missing(brain, LINEAS)
    except Exception:
        return None


def needed(ctx):
    try:
        return any(_missing(b) for _n, b in _brains(ctx))
    except Exception:
        return False


def _un_cerebro(ctx, name, brain):
    import install
    falta = _missing(brain)
    if falta is None:
        ctx.log("%s: .gitignore ilegible — no se tocó" % name)
        return
    if not falta:
        return
    if ctx.dry_run:
        ctx.log("%s: agregaría %s al .gitignore" % (name, ", ".join(falta)))
        return
    install.ensure_gitignore(brain, LINEAS)
    if _missing(brain):
        ctx.log("%s: no pude completar el .gitignore — sigue con el siguiente" % name)
        return
    ctx.log("%s: .gitignore sin conversaciones (%s)" % (name, ", ".join(falta)))


def run(ctx):
    try:
        cerebros = _brains(ctx)
    except Exception as exc:
        ctx.log("no pude listar los cerebros (%s) — nada que hacer" % type(exc).__name__)
        return
    for name, brain in cerebros:
        try:
            _un_cerebro(ctx, name, brain)
        except Exception as exc:     # por cerebro: jamás traba la cola
            ctx.log("%s: .gitignore no se tocó (%s: %s) — sigue con el siguiente"
                    % (name, type(exc).__name__, str(exc)[:120]))
