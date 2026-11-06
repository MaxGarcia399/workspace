"""AUTOMÁTICA: Claude Code no escribe la config de los motores, git ni Obsidian
de tu cerebro, también abierto fuera de Workspace.

Con la autonomía «brain» (la de fábrica) el instalador deja en
`<cerebro>/.claude/settings.local.json` el permiso de escribir en el cerebro
sin preguntar (`Edit(//<cerebro>/**)`). Hasta 2026-11-06 el deny de las rutas
protegidas (rutas_protegidas: `.git`, `.kiro`, `.cursor`, `.obsidian`,
`.claude/settings*.json`…) iba SOLO en el `--settings` de cada pestaña: un
`claude` abierto fuera del lanzador (VS Code, Desktop, `claude` a secas) o con
su propio `--settings` escribía esa config sin preguntar.

Qué hace (KIND "auto", sin preguntar): en cada cerebro registrado cuyo
settings.local.json trae los permisos «brain» que escribió Workspace (su
marcador `__workspacePermissions`), agrega el deny que falta
(install.completar_deny) y lo anota en el marcador, para que el
desinstalador y un cambio de autonomía lo reconozcan. No toca el allow, el
modo ni nada tuyo (tus reglas allow/deny quedan). Respaldo del archivo en
<estado>/backups/<id>/ antes de escribir. Un cerebro con autonomía «ask», sin
marcador o con el archivo ilegible no se toca.

Idempotente y TOLERANTE POR CEREBRO: un archivo ilegible o que no se puede
escribir se anota y la cola sigue (el `--settings` de la pestaña sigue
negando esas rutas). Lo mismo hace configure_brain al reinstalar o cargar un
agente, así un cerebro cargado después de esta versión también queda al día.
Compatible hacia atrás: una versión anterior conserva el deny (lo lee como
regla tuya) y solo pregunta o niega más, nunca menos.
"""
import json
import os
import re
import shutil

TITLE = {"es": "Claude Code no escribe la config de los motores, git ni Obsidian de tu "
               "cerebro, también fuera de Workspace",
         "en": "Claude Code won't write the engines', git's or Obsidian's config in your "
               "brain, also outside Workspace"}
KIND = "auto"
MID = "202611062300_claude_deny_protegidas"


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
    """[(nombre, cerebro, settings ya completado)] con deny que agregar."""
    import install
    out = []
    for name, brain in _brains(ctx):
        try:
            s = _read(_settings_path(brain))
            if s is not None and install.completar_deny(s, brain):
                out.append((name, brain, s))
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
    """Atómico, con los reintentos de Windows (antivirus u Obsidian con el
    archivo abierto). Si no se logra (p. ej. el archivo es de solo lectura), el
    temporal se borra y la excepción sube: el cerebro queda «sin tocar» en el
    log y lo completa la siguiente carga del agente (install.configure_brain)."""
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
    for name, brain, settings in _targets(ctx):
        path = _settings_path(brain)
        try:
            _backup(ctx, name, path)
            _write(path, settings)
            ctx.log("%s: Claude Code ya no escribe la config de los motores, git ni "
                    "Obsidian del cerebro" % name)
        except Exception as e:           # un cerebro no traba la cola
            ctx.log("%s: settings.local.json sin tocar (%s: %s)" % (name, type(e).__name__, e))
