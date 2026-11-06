"""AUTOMÁTICA: el .gitignore de tus cerebros ignora la herramienta de memoria
de Cursor y Kiro.

Desde la memoria por herramienta MCP (memoria_mcp), Workspace deja en cada
cerebro donde abres Cursor o Kiro `.cursor/mcp.json`, `.cursor/cli.json` y
`.kiro/agents/workspace.json`. Son de ESTA máquina (llevan la ruta de su
Python y de Workspace) y Workspace los rehace al abrir cada pestaña: en un
cerebro versionado con git no deben commitearse.

Qué hace (KIND "auto", sin preguntar): a cada cerebro registrado le agrega al
final del `.gitignore` las líneas que le falten (install.ensure_gitignore, la
misma función del instalador). Solo agrega: no borra ni reordena nada y
correrla de nuevo no cambia nada. TOLERANTE POR CEREBRO: un `.gitignore`
ilegible o que no se puede escribir se anota y la cola sigue (nunca lanza).
Un cerebro que vive dentro del propio Workspace se salta. Una versión
anterior lee el mismo archivo sin problema.
"""
import os

TITLE = {"es": "El .gitignore de tus cerebros ignora la herramienta de memoria de Cursor y Kiro",
         "en": "Your brains' .gitignore ignores Cursor's and Kiro's memory tool"}
KIND = "auto"
MID = "202611052000_gitignore_herramienta_memoria"
#: Las líneas de esta migración (fijas: una migración publicada no cambia).
LINEAS = (".cursor/mcp.json", ".cursor/cli.json", ".kiro/agents/workspace.json")


def _inside(path, root):
    p = os.path.normcase(os.path.realpath(path))
    r = os.path.normcase(os.path.realpath(root))
    return p == r or p.startswith(r + os.sep)


def _brains(ctx):
    """[(nombre, cerebro)] únicos, fuera del harness."""
    out, seen = [], set()
    try:
        todos = list(ctx.brains())
    except Exception:
        return []
    for name, brain in todos:
        try:
            key = os.path.normcase(os.path.realpath(brain))
            if key in seen or _inside(brain, ctx.root):
                continue
        except Exception:
            continue
        seen.add(key)
        out.append((name, brain))
    return out


def _missing(brain):
    """Líneas que faltan; None si el .gitignore no se puede leer."""
    import install
    try:
        return install.gitignore_missing(brain, list(LINEAS))
    except Exception:
        return None


def needed(ctx):
    return any(_missing(b) for _n, b in _brains(ctx))


def run(ctx):
    import install
    for name, brain in _brains(ctx):
        try:
            falta = _missing(brain)
            if falta is None:
                ctx.log("%s: .gitignore ilegible — no se tocó" % name)
                continue
            if not falta:
                continue
            install.ensure_gitignore(brain, list(LINEAS))
            if install.gitignore_missing(brain, list(LINEAS)):
                ctx.log("%s: no pude completar el .gitignore — sigue sin %s"
                        % (name, ", ".join(falta)))
                continue
            ctx.log("%s: .gitignore al día (%s)" % (name, ", ".join(falta)))
        except Exception as e:          # un cerebro no traba la cola
            ctx.log("%s: .gitignore sin tocar (%s: %s)" % (name, type(e).__name__, e))
