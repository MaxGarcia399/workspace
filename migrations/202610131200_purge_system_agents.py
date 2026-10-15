"""Quita del registro de agentes los motores internos que se colaron.

Hasta 0.2.0, al traer el estado de la instalación anterior se copiaba el
registro de agentes tal cual — incluido un agente INTERNO del producto
(`doctor`, oculto) que nunca fue del usuario. Desde entonces `workspace doctor`
lo revisaba como si fuera suyo (avisos de BOOT, INDEX, resume, banner…) y su
registro impedía retirar la instalación anterior.

Qué hace: saca de `agents.local.json` las entradas de agentes internos
(dispatch.SYSTEM_AGENTS, `hidden: true`, o cerebro dentro de la carpeta
`agents/` de un harness) en CUALQUIER instalación — salvo un agente interno
vivo de ESTA instalación (su carpeta existe dentro de este Workspace: un
registro vigente, no una copia vieja). Respaldo antes de escribir en
<estado>/backups/<id>/. Los cerebros no se tocan: solo el registro.
Si una versión anterior vuelve a correr, simplemente no ve ese agente interno.
"""
import json
import os
import shutil

TITLE = {"es": "Quitar del registro un agente interno copiado por error",
         "en": "Remove an internal agent copied into your agent list by mistake"}
KIND = "auto"
MID = "202610131200_purge_system_agents"


def _path(ctx):
    return os.path.join(ctx.state_dir, "agents.local.json")


def _read(ctx):
    try:
        with open(_path(ctx), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _inside(path, root):
    try:
        p = os.path.normcase(os.path.realpath(os.path.expanduser(path)))
        r = os.path.normcase(os.path.realpath(root))
        return p == r or p.startswith(r.rstrip(os.sep) + os.sep)
    except Exception:
        return False


def _stale(ctx, entry):
    """True si `entry` es un agente interno que NO pertenece a esta instalación."""
    import migrate_legacy
    if migrate_legacy.importable_agent(entry):
        return False
    brain = str((entry or {}).get("brain", "") or "")
    live_here = bool(brain) and _inside(brain, ctx.root) and \
        os.path.isdir(os.path.expanduser(brain))
    return not live_here


def _plan(ctx):
    data = _read(ctx)
    if not data or not isinstance(data.get("agents"), list):
        return None, []
    gone = [a for a in data["agents"] if isinstance(a, dict) and _stale(ctx, a)]
    return data, gone


def needed(ctx):
    return bool(_plan(ctx)[1])


def run(ctx):
    data, gone = _plan(ctx)
    if not gone:
        return
    src = _path(ctx)
    bdir = os.path.join(ctx.state_dir, "backups", MID)
    os.makedirs(bdir, exist_ok=True)
    shutil.copy2(src, os.path.join(bdir, "agents.local.json"))
    keep = [a for a in data["agents"] if not (isinstance(a, dict) and _stale(ctx, a))]
    out = dict(data)
    out["agents"] = keep
    tmp = "%s.tmp-%d" % (src, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, src)
    ctx.log("agents.local.json: %s" % ", ".join(
        str(a.get("name", "?")) for a in gone))
