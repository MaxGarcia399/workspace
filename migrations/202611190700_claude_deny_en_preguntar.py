"""AUTOMÁTICA: con «Preguntarme todo», Claude Code vuelve a tener negada la
config protegida de tu cerebro y la bóveda de llaves.

Hasta la cacería del 19-nov (B04), poner un agente de Claude Code en
«Preguntar» (autonomía «ask», desde Configuración → Permisos o Agentes) dejaba
`<cerebro>/.claude/settings.local.json` sin el deny de Workspace: las reglas que
niegan escribir `.git`, los hooks, `.claude/settings*.json`, `.mcp.json`… y leer
la bóveda de llaves (install.deny_workspace). Preguntaba, pero si aprobabas, lo
hacía.

Qué hace (KIND "auto", sin preguntar): en cada cerebro registrado cuyo
settings.local.json trae los permisos que escribió Workspace (su marcador
`__workspacePermissions`) con autonomía «ask», agrega el deny que falta
(install.completar_deny) y lo anota en el marcador. No toca el allow, el modo
ni nada tuyo (tus reglas allow/deny quedan). Respaldo del archivo en
<estado>/backups/<id>/ antes de escribir. Sin marcador o con el archivo
ilegible, no se toca. Los de «brain» ya los completó
202611062300_claude_deny_protegidas.

Idempotente y TOLERANTE POR CEREBRO: un archivo ilegible o que no se puede
escribir se anota y la cola sigue (configure_brain lo completa al reinstalar o
cargar el agente). Compatible hacia atrás: una versión anterior conserva el
deny (lo lee como regla tuya, o lo quita al cambiar otra vez el nivel) y solo
pregunta o niega más, nunca menos.
"""
import json
import os
import re
import shutil

TITLE = {"es": "Con «Preguntarme todo», Claude Code sigue sin poder tocar la config protegida "
               "de tu cerebro ni la bóveda de llaves",
         "en": "With «Ask me everything», Claude Code still can't touch your brain's protected "
               "config or the key vault"}
KIND = "auto"
MID = "202611190700_claude_deny_en_preguntar"


def _settings_path(brain):
    return os.path.join(brain, ".claude", "settings.local.json")


def _inside(path, root):
    p = os.path.normcase(os.path.realpath(path))
    r = os.path.normcase(os.path.realpath(root))
    return p == r or p.startswith(r + os.sep)


def _read(path):
    """dict | None (no existe, enlace o ilegible: jamás se pisa)."""
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _en_preguntar(settings):
    import install
    m = settings.get(install._PERM_MARKER)
    return isinstance(m, dict) and m.get("autonomy") == "ask"


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


def _targets(ctx):
    """[(nombre, cerebro)] en «ask» con deny que agregar."""
    import install
    out = []
    for name, brain in _brains(ctx):
        try:
            s = _read(_settings_path(brain))
            if s is not None and _en_preguntar(s) and install.completar_deny(s, brain, ("ask",)):
                out.append((name, brain))
        except Exception:
            continue
    return out


def needed(ctx):
    return bool(_targets(ctx))


def _backup(ctx, name, src):
    bdir = os.path.join(ctx.state_dir, "backups", MID)
    os.makedirs(bdir, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name) or "agente"
    shutil.copy2(src, os.path.join(bdir, "%s-settings.local.json" % safe))


def _write(path, data):
    """Atómico, con los reintentos de Windows; si no se logra, el temporal se borra y la excepción sube."""
    tmp = "%s.tmp-%d" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        try:
            import atomico
            atomico.reemplazar(tmp, path)
        except ImportError:
            os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def run(ctx):
    import install
    import olock
    for name, brain in _targets(ctx):
        path = _settings_path(brain)
        try:
            with olock.local_lock(path, timeout=5):      # lo leído en _targets pudo cambiar
                settings = _read(path)
                if settings is None or not _en_preguntar(settings) or \
                        not install.completar_deny(settings, brain, ("ask",)):
                    continue
                if ctx.dry_run:
                    ctx.log("%s: (simulado) volvería el deny de Workspace con «Preguntarme todo»" % name)
                    continue
                _backup(ctx, name, path)
                _write(path, settings)
            ctx.log("%s: con «Preguntarme todo», lo protegido del cerebro vuelve a estar negado" % name)
        except Exception as e:           # un cerebro no traba la cola
            ctx.log("%s: settings.local.json sin tocar (%s: %s)" % (name, type(e).__name__, e))
