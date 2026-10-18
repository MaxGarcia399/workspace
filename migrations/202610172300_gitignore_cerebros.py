"""AUTOMÁTICA: el .gitignore de tus cerebros ignora los archivos de la memoria.

La memoria v1 (0.3.4) deja en cada cerebro candados (`.claude/locks/*.lock`, con
el pid y el nombre de la máquina) y una bandeja de notas
(`.claude/memoria-entrada/`). Son estado de ESTA máquina. El instalador y
«cargar agente» agregan esas carpetas al `.gitignore` del cerebro, pero un
cerebro que ya existía antes de actualizar no las recibía: en un cerebro
versionado con git aparecían como archivos sin rastrear y se podían commitear
por error.

Qué hace (KIND "auto", sin preguntar): a cada cerebro registrado le agrega al
final del `.gitignore` las líneas de install.GITIGNORE_LINES que le falten (la
misma función del instalador, install.ensure_gitignore). Solo agrega: no borra
ni reordena nada, y correrla de nuevo no cambia nada. Un `.gitignore` ilegible
no se toca (se anota y la cola sigue). Un cerebro que vive dentro del propio
Workspace se salta (ensuciaría el código y bloquearía las actualizaciones).
Una versión anterior lee el mismo archivo sin problema.
"""
import os

TITLE = {"es": "El .gitignore de tus cerebros ignora los archivos de la memoria",
         "en": "Your brains' .gitignore ignores the memory's files"}
KIND = "auto"
MID = "202610172300_gitignore_cerebros"


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
    """Líneas que faltan; None si el .gitignore no se puede leer."""
    import install
    try:
        return install.gitignore_missing(brain, install.GITIGNORE_LINES)
    except (OSError, UnicodeDecodeError):
        return None


def needed(ctx):
    return any(_missing(b) for _n, b in _brains(ctx))


def run(ctx):
    import install
    for name, brain in _brains(ctx):
        falta = _missing(brain)
        if falta is None:
            ctx.log("%s: .gitignore ilegible — no se tocó" % name)
            continue
        if not falta:
            continue
        install.ensure_gitignore(brain, install.GITIGNORE_LINES)
        if install.gitignore_missing(brain, install.GITIGNORE_LINES):
            raise RuntimeError("no pude completar el .gitignore de %s" % name)
        ctx.log("%s: .gitignore al día (%s)" % (name, ", ".join(falta)))
