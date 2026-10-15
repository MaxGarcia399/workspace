"""AUTOMÁTICA: tus agentes quedan libres solo dentro de su cerebro.

Hasta 0.2.x el instalador dejaba en CADA cerebro
`permissions: {"defaultMode": "dontAsk", "allow": [Bash, Write, Edit, WebFetch,
… y un MCP del equipo]}`: en Claude Code el agente podía correr cualquier
comando de terminal, editar fuera de su carpeta y salir a la red sin
preguntarte. Desde 0.3.0 un agente lee, crea y edita dentro de su cerebro sin
preguntar; para lo demás te pregunta. «Comandos sin preguntar» ya no existe
(decisión del dueño 2026-10-14): no se ofrece ni se avisa, se ajusta solo.

Qué hace (KIND "auto", sin preguntar ni avisar): en cada cerebro registrado
1. si su `.claude/settings.local.json` trae ese `dontAsk` con `Bash` libre,
   reescribe `permissions` a las reglas del cerebro (install.render_permissions:
   conserva tus reglas propias, deny/ask y cualquier otra clave);
2. si su `.workspace/agent.json` dice `"autonomy": "full"`, lo cambia a "brain".
Respaldo de cada archivo en <estado>/backups/<id>/ antes de escribir. Un
archivo ilegible no se toca. Una versión anterior que vuelva a correr lee los
mismos archivos (solo con menos permisos). Reemplaza a la oferta
202610131300_brain_permissions, que nunca se publicó.
"""
import json
import os
import re
import shutil

TITLE = {"es": "Tus agentes quedan libres solo dentro de su cerebro",
         "en": "Your agents are now free only inside their brain"}
KIND = "auto"
MID = "202610141400_brain_permissions"


def _settings_path(brain):
    return os.path.join(brain, ".claude", "settings.local.json")


def _def_path(brain):
    return os.path.join(brain, ".workspace", "agent.json")


def _read(path):
    """dict | None (no existe o ilegible: jamás se pisa)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _broad(settings):
    """¿Trae el `dontAsk` con terminal libre que dejaba 0.2.x?"""
    perms = (settings or {}).get("permissions")
    if not isinstance(perms, dict) or perms.get("defaultMode") != "dontAsk":
        return False
    allow = perms.get("allow")
    return isinstance(allow, list) and "Bash" in allow


def _targets(ctx):
    """[(nombre, cerebro, settings|None, definición|None)] con algo que ajustar."""
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key in seen:
            continue                          # el mismo cerebro con dos nombres
        seen.add(key)
        s = _read(_settings_path(brain))
        d = _read(_def_path(brain))
        s = s if (s is not None and _broad(s)) else None
        d = d if (d is not None and d.get("autonomy") == "full") else None
        if s is not None or d is not None:
            out.append((name, brain, s, d))
    return out


def needed(ctx):
    return bool(_targets(ctx))


def _backup(ctx, name, src, tag):
    bdir = os.path.join(ctx.state_dir, "backups", MID)
    os.makedirs(bdir, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name) or "agente"
    shutil.copy2(src, os.path.join(bdir, "%s-%s" % (safe, tag)))


def _write(path, data):
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def run(ctx):
    import install
    for name, brain, settings, defn in _targets(ctx):
        if defn is not None:
            _backup(ctx, name, _def_path(brain), "agent.json")
            _write(_def_path(brain), dict(defn, autonomy="brain"))
        if settings is not None:
            _backup(ctx, name, _settings_path(brain), "settings.local.json")
            d = _read(_def_path(brain)) or {}
            cfg = dict(d, autonomy="ask" if d.get("autonomy") == "ask" else "brain")
            install.render_permissions(settings, cfg, brain)
            _write(_settings_path(brain), settings)
        ctx.log("%s: libre solo dentro de su cerebro" % name)
