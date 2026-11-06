"""AUTOMÁTICA: el .gitignore de tus cerebros ignora la herramienta de memoria
de Antigravity.

Desde 2026-11-06 Antigravity también guarda la memoria con la herramienta MCP
de Workspace (memoria_mcp): en cada cerebro donde abres Antigravity queda
`.agents/mcp_config.json`. Es de ESTA máquina (lleva la ruta de su Python y de
Workspace) y Workspace lo rehace al abrir cada pestaña: en un cerebro
versionado con git no debe commitearse.

Qué hace (KIND "auto", sin preguntar): a cada cerebro registrado le agrega al
final del `.gitignore` la línea si le falta (install.ensure_gitignore, la
misma función del instalador). Solo agrega: no borra ni reordena nada y
correrla de nuevo no cambia nada. TOLERANTE POR CEREBRO: un `.gitignore`
ilegible o que no se puede escribir se anota y la cola sigue (nunca lanza).
Un cerebro que vive dentro del propio Workspace se salta. Una versión
anterior lee el mismo archivo sin problema.
"""
import os

TITLE = {"es": "El .gitignore de tus cerebros ignora la herramienta de memoria de Antigravity",
         "en": "Your brains' .gitignore ignores Antigravity's memory tool"}
KIND = "auto"
MID = "202611060000_gitignore_memoria_antigravity"
#: Las líneas de esta migración (fijas: una migración publicada no cambia).
LINEAS = (".agents/mcp_config.json",)


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
