"""Retención de transcripts: un año (365 días) en vez de diez.

Hasta 0.2.0 el instalador fijaba `cleanupPeriodDays = 3650` en
~/.claude/settings.json (el ajuste GLOBAL de Claude Code del usuario: afecta
también su uso fuera de Workspace, y el disco crece sin tope). Desde 0.2.1 el
valor es 365 días.

Qué hace: si el valor es EXACTAMENTE 3650 (el que dejaba nuestro instalador) o
no hay valor, lo deja en 365. Cualquier otro valor lo eligió el usuario y no
se toca. Respaldo de settings.json en <estado>/backups/<id>/ antes de escribir.
Un settings.json ilegible no se toca nunca.
"""
import json
import os
import shutil

TITLE = {"es": "Conservar tus sesiones un año (antes: diez)",
         "en": "Keep your sessions for one year (was: ten)"}
KIND = "auto"
MID = "202610131210_retention_365"
NEW_DAYS = 365
OLD_DAYS = 3650


def _path(ctx):
    return os.path.join(ctx.home, ".claude", "settings.json")


def _read(ctx):
    """(dict | None si ilegible, existe)."""
    p = _path(ctx)
    if not os.path.exists(p):
        return {}, False
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return (data if isinstance(data, dict) else None), True
    except Exception:
        return None, True


def needed(ctx):
    data, _ = _read(ctx)
    if data is None:
        return False                       # ilegible: jamás se pisa
    cur = data.get("cleanupPeriodDays")
    return cur is None or (cur == OLD_DAYS and not isinstance(cur, bool))


def run(ctx):
    data, exists = _read(ctx)
    if data is None or not needed(ctx):
        return
    p = _path(ctx)
    if exists:
        bdir = os.path.join(ctx.state_dir, "backups", MID)
        os.makedirs(bdir, exist_ok=True)
        shutil.copy2(p, os.path.join(bdir, "settings.json"))
    else:
        # sin valor previo: que `workspace uninstall` sepa que no había nada
        pre = os.path.join(ctx.state_dir, "pre-install.json")
        if not os.path.exists(pre):
            os.makedirs(ctx.state_dir, exist_ok=True)
            with open(pre, "w", encoding="utf-8") as fh:
                json.dump({"cleanupPeriodDays": None}, fh)
    data["cleanupPeriodDays"] = NEW_DAYS
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = "%s.tmp-%d" % (p, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, p)
