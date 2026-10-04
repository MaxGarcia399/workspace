#!/usr/bin/env python3
"""workflows.steps.agent — pasos det del workflow `crear-agente` (agentes a
nivel harness). ENVUELVEN el sustrato que ya existe — `agent_admin.create`
scaffolda el cerebro desde `templates/agent/brain/` (placeholders renderizados)
+ `.workspace/agent.json` + registro per-máquina — no reinventan nada:

  · create       — crea el agente vía `agent_admin.create`. Config = artefacto
                   `agent_config` (base, lo deja un paso agent de intake) ⊕
                   `--param` (override). IDEMPOTENTE: "ya existe" = no-op verde
                   (invariante 4 del runner); nombre inválido / template
                   faltante = contrato roto, permanente.
  · verify_brain — quality bar ESTRUCTURAL del cerebro creado (sin LLM): la
                   anatomía mínima de `protocols/agent-creation/02-BRAIN-FORMAT.md`
                   (BOOT/ completo, CLAUDE.md, .workspace/agent.json, STATE/ con
                   su capa HOT) + CERO placeholders `{{…}}` sin renderizar
                   (`agent_admin._scan_placeholders` — un placeholder vivo =
                   template crudo, no un agente configurado).

La calidad SEMÁNTICA (¿el SOUL es bueno? ¿el agente responde bien?) NO se
verifica aquí — eso es el launch gate de 03-QUALITY-BAR.md (juez/golden set/
humano). Este verify solo prueba forma y existencia, y lo dice honesto.

Import LAZY de `agent_admin` DENTRO de cada función (misma convención que los
demás steps: resolver un paso no carga el mundo).
"""
import os

# Campos de config que `agent_admin.create` entiende — lo demás se ignora
# (falla-suave: un intake que deja campos extra no rompe el paso).
_CONFIG_FIELDS = ("name", "display", "tagline", "owner", "color",
                  "scope", "soul", "skills", "brain_dest", "emblem")

_SIN_NAME = ("falta `name` en la config del agente "
             "(artefacto `agent_config` o --param name=<slug>)")


def _config(ctx):
    """Config efectiva del agente: artefacto `agent_config` (base) ⊕
    `ctx["params"]` (override — lo que el socio pasó a mano GANA). Solo
    campos conocidos; None/ausente no pisa la base."""
    arts = ctx.get("artifacts") or {}
    base = arts.get("agent_config")
    base = base if isinstance(base, dict) else {}
    params = ctx.get("params") or {}
    cfg = {}
    for k in _CONFIG_FIELDS:
        v = params.get(k, base.get(k))
        if v is not None:
            cfg[k] = v
    return cfg


def _brain_path(name, brain_dest=None):
    """Ruta del cerebro que `agent_admin.create` usa: `brain_dest` explícito
    o el default `~/Desktop/<UPPER> - BRAIN` (mismo cómputo que create —
    normaliza el nombre igual: strip+lower antes del upper)."""
    if brain_dest:
        return os.path.abspath(os.path.expanduser(str(brain_dest)))
    upper = str(name or "").strip().lower().upper()
    return os.path.abspath(os.path.join(
        os.path.expanduser("~"), "Desktop", "%s - BRAIN" % upper))


def _registered_brain(name):
    """Cerebro REGISTRADO del agente (agents.local.json per-máquina), si lo
    hay — la fuente más veraz cuando el agente ya existe. None si no está."""
    try:
        import agentsreg
        entry = agentsreg.find(name)
        if entry and entry.get("brain"):
            return os.path.abspath(os.path.expanduser(entry["brain"]))
    except Exception:
        pass
    return None


def create(ctx, step):
    """Paso det: crea el agente vía `agent_admin.create` (scaffold del cerebro
    desde el template + agent.json + registro). IDEMPOTENTE: si el agente ya
    existe, no-op verde con el path del cerebro (re-correr el workflow no
    revienta). Nombre inválido / template faltante = permanente (reintentar
    no lo arregla). dry → no-op reportando qué haría."""
    cfg = _config(ctx)
    name = str(cfg.get("name") or "").strip().lower()
    if ctx.get("dry"):
        # dry PRIMERO: nada real corre — no-op ok aunque falte el name
        return {"ok": True,
                "detail": ("crearía el agente `%s` (dry)" % name if name
                           else "crearía el agente (dry)")}
    if not name:
        # config rota (nadie dijo QUIÉN nace) — permanente, no transitoria
        return {"ok": False, "detail": _SIN_NAME, "retriable": False}
    import agent_admin
    try:
        ok, res = agent_admin.create(
            name,
            tagline=str(cfg.get("tagline") or ""),
            display=cfg.get("display"),
            owner=str(cfg.get("owner") or ""),
            scope=str(cfg.get("scope") or ""),
            soul=str(cfg.get("soul") or ""),
            skills=str(cfg.get("skills") or ""),
            color=str(cfg.get("color") or "gris"),
            brain_dest=cfg.get("brain_dest"),
            out=lambda *_a, **_k: None)      # sin ruido al stdout del runner
    except Exception as e:
        return {"ok": False,
                "detail": "agent_admin.create REVENTÓ para `%s`: %s: %s"
                          % (name, type(e).__name__, e)}
    brain = (_registered_brain(name)
             or _brain_path(name, cfg.get("brain_dest")))
    if ok:
        return {"ok": True,
                "detail": "agente `%s` creado — cerebro en %s" % (name, brain),
                "artifacts": {"agent_name": name, "agent_brain": brain}}
    if "ya existe" in str(res):
        # idempotencia: el efecto ya existe — adoptar, no reventar
        return {"ok": True,
                "detail": "`%s` ya existe (no-op)" % name,
                "artifacts": {"agent_name": name, "agent_brain": brain}}
    # nombre/owner inválido, template faltante, creación revertida — contrato
    # o entorno roto: PERMANENTE, reintentar produce el mismo error.
    return {"ok": False,
            "detail": "no se pudo crear `%s`: %s" % (name, res),
            "retriable": False}


# Anatomía MÍNIMA del cerebro (derivada de 02-BRAIN-FORMAT.md — el contrato
# por ROLES): identidad inmutable (BOOT/), ensamblador (CLAUDE.md), identidad
# portátil (.workspace/agent.json) y la capa HOT de STATE/. El 02 tolera el
# dialecto TEAM (interno) u OWNER (externo) — cualquiera de los dos cumple.
_BOOT_REQUIRED = ("00-SOUL.md", "01-IDENTITY.md", "03-RULES.md",
                  "04-BRAIN-MAP.md")
_BOOT_ANY_02 = ("02-TEAM.md", "02-OWNER.md")
_STATE_REQUIRED = ("brain-version.md", "MEMORY.md", "INDEX.md")


def verify_brain(ctx, step):
    """Paso det: quality bar ESTRUCTURAL del cerebro creado (sin LLM) —
    estructura mínima de 02-BRAIN-FORMAT + cero placeholders `{{…}}` sin
    renderizar. Verde = el cerebro tiene la anatomía completa Y está
    configurado (no es un template crudo). La calidad semántica es del
    launch gate humano (03-QUALITY-BAR), no de este paso."""
    if ctx.get("dry"):
        # dry PRIMERO: nada real corre — no se lee el disco
        return {"ok": True,
                "detail": "verificaría la estructura del cerebro (dry)"}
    arts = ctx.get("artifacts") or {}
    brain = arts.get("agent_brain")
    if not brain:
        # sin artefacto directo: resolver por nombre (registro per-máquina
        # primero — la fuente veraz — luego el default del Desktop)
        name = arts.get("agent_name") or (ctx.get("params") or {}).get("name")
        if name:
            name = str(name).strip().lower()
            brain = _registered_brain(name) or _brain_path(name)
    if not brain:
        return {"ok": False,
                "detail": "sin cerebro que verificar (ni artefacto "
                          "`agent_brain` ni `agent_name`/--param name=)",
                "retriable": False}
    brain = os.path.abspath(os.path.expanduser(str(brain)))
    if not os.path.isdir(brain):
        gaps = ["la carpeta del cerebro no existe: %s" % brain]
        return {"ok": False,
                "detail": "cerebro INEXISTENTE: %s" % brain,
                "artifacts": {"brain_ok": False, "brain_gaps": gaps}}

    gaps = []
    for rel in ("CLAUDE.md", os.path.join(".workspace", "agent.json")):
        if not os.path.isfile(os.path.join(brain, rel)):
            gaps.append(rel.replace(os.sep, "/"))
    for fn in _BOOT_REQUIRED:
        if not os.path.isfile(os.path.join(brain, "BOOT", fn)):
            gaps.append("BOOT/" + fn)
    if not any(os.path.isfile(os.path.join(brain, "BOOT", fn))
               for fn in _BOOT_ANY_02):
        gaps.append("BOOT/02-TEAM.md (o 02-OWNER.md)")
    if not os.path.isdir(os.path.join(brain, "STATE")):
        gaps.append("STATE/")
    else:
        for fn in _STATE_REQUIRED:
            if not os.path.isfile(os.path.join(brain, "STATE", fn)):
                gaps.append("STATE/" + fn)

    # agent.json RICO (portero): un agente COMPLETO declara su tema, sus env de
    # sesión PROPIOS (sin `session_env` el engine cae al default ZENITH_WS →
    # colisión de workspace) y el contrato de `memory` (lo audita doctor). Que
    # falten = agente a medias → no pasa la barra estructural.
    defn = {}
    try:
        import json as _json
        ajp = os.path.join(brain, ".workspace", "agent.json")
        defn = _json.load(open(ajp, encoding="utf-8")) if os.path.isfile(ajp) else {}
        for key in ("theme", "session_env", "session_id_env"):
            if not str(defn.get(key) or "").strip():
                gaps.append("agent.json sin `%s`" % key)
        if not isinstance(defn.get("memory"), dict):
            gaps.append("agent.json sin bloque `memory`")
    except Exception as e:
        gaps.append("no se pudo leer agent.json: %s" % type(e).__name__)

    # BANNER de calidad de EQUIPO (no el plano viejo): fuente shadow 3D + sufijo
    # AGENT + sistema de emblema. Un banner pobre/sin emblema = un agente que nace
    # a medias — se verifica sobre el banner renderizado del cerebro.
    # (calidad SI hay banner renderizado; su PRESENCIA la garantiza el paso
    # `brand`, que corre ANTES de verify en el flujo — no la re-exige acá.)
    try:
        nm = str((defn or {}).get("name") or "").strip().lower()
        bp = os.path.join(brain, "brand", "%s-banner.py" % nm) if nm else ""
        if bp and os.path.isfile(bp):
            btxt = open(bp, encoding="utf-8").read()
            if "╗" not in btxt:                         # glifos de la fuente shadow
                gaps.append("banner sin fuente shadow (formato pobre)")
            if "AGENT" not in btxt:
                gaps.append("banner sin sufijo AGENT")
            if "emblem_lines" not in btxt:
                gaps.append("banner sin sistema de emblema")
    except Exception:
        pass

    # cero placeholders {{…}}: un placeholder vivo = template crudo cargado
    # en vez de un agente configurado (solo create() renderiza).
    try:
        import agent_admin
        pendientes = sorted(agent_admin._scan_placeholders(brain))
    except Exception as e:
        pendientes = []
        gaps.append("no se pudo escanear placeholders: %s: %s"
                    % (type(e).__name__, e))
    for ph in pendientes:
        gaps.append("placeholder sin renderizar: %s" % ph)

    ok = not gaps
    if ok:
        detail = ("cerebro %s completo: estructura mínima OK + 0 "
                  "placeholders sin renderizar" % brain)
    else:
        detail = ("cerebro %s INCOMPLETO (%d gap%s): %s"
                  % (brain, len(gaps), "" if len(gaps) == 1 else "s",
                     " · ".join(gaps)))
    return {"ok": ok, "detail": detail,
            "artifacts": {"brain_ok": ok, "brain_gaps": gaps}}


def _resolve_brain(ctx):
    """El cerebro del agente (mismo orden que verify_brain): artefacto
    `agent_brain`, si no por nombre (registro per-máquina > default Desktop)."""
    arts = ctx.get("artifacts") or {}
    brain = arts.get("agent_brain")
    if not brain:
        name = arts.get("agent_name") or (ctx.get("params") or {}).get("name")
        if name:
            name = str(name).strip().lower()
            brain = _registered_brain(name) or _brain_path(name)
    return os.path.abspath(os.path.expanduser(str(brain))) if brain else None


# Kit de MARCA del agente: los tres assets visuales que lo hacen SUYO, no el
# genérico compartido — (clave en agent.json, archivo del template, sufijo del
# destino, clave del artefacto). El banner es el emblema; la statusline es su
# barra en Claude Code (sin esto un agente nace SIN barra propia — cae al
# template crudo con {{…}} → gris neutro); el dashboard es su panel de sesiones.
_BRAND_ASSETS = (
    ("banner", "agent-banner.py", "banner", "banner_path"),
    ("statusline", "agent-statusline.py", "statusline", "statusline_path"),
    ("dashboard", "agent-dashboard.py", "dashboard", "dashboard_path"),
)


def brand(ctx, step):
    """Paso det: le da al agente su KIT DE MARCA PROPIO (no el genérico
    compartido) — banner + statusline + dashboard. Renderiza cada template a
    `<brain>/brand/<name>-<asset>.py` con los datos del agente sustituidos
    (auto-contenido, no depende de encontrar agent_brand desde el cerebro) y
    repunta `agent.json` a los tres. Antes solo hacía el banner → los agentes
    nacían SIN statusline propia (barra vacía, como le pasó a Iris): la
    statusline apuntaba al template crudo con {{AGENT_DISPLAY}} → gris neutro.
    IDEMPOTENTE por-asset: el que ya exista se repunta sin re-renderizar. dry →
    no-op. Es la cara del 'crear personaje': cada agente nace con su marca."""
    if ctx.get("dry"):
        return {"ok": True,
                "detail": "renderizaría el kit de marca del agente "
                          "(banner · statusline · dashboard) (dry)"}
    cfg = _config(ctx)
    arts = ctx.get("artifacts") or {}
    name = str(cfg.get("name") or arts.get("agent_name") or "").strip().lower()
    if not name:
        return {"ok": False, "detail": _SIN_NAME, "retriable": False}
    brain = _resolve_brain(ctx)
    if not brain or not os.path.isdir(brain):
        return {"ok": False,
                "detail": "sin cerebro donde poner la marca (%s)" % brain,
                "retriable": False}
    dest_dir = os.path.join(brain, "brand")
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tmpl_dir = os.path.join(root, "templates", "agent", "workspace", "brand")

    # subs COMPLETO: cada template usa un subconjunto; los placeholders que un
    # template no tenga son no-ops. Fuente única para los tres assets.
    try:
        import agent_admin
        color = agent_admin.norm_color(str(cfg.get("color") or "gris"))
    except Exception:
        color = str(cfg.get("color") or "gris")
    display = str(cfg.get("display") or name.capitalize())
    subs = {
        "{{AGENT_DISPLAY}}": display,
        "{{AGENT_NAME}}": name,
        "{{AGENT_UPPER}}": name.upper(),
        "{{TAGLINE}}": str(cfg.get("tagline") or ""),
        "{{SKILL_CATS}}": str(cfg.get("skills") or ""),
        "{{SCOPE}}": str(cfg.get("scope") or ""),
        "{{COLOR}}": color,
    }

    def _repoint(agent_key, rel):
        # apunta agent.json a un asset propio (best-effort — el asset ya existe)
        try:
            import json
            p = os.path.join(brain, ".workspace", "agent.json")
            d = json.load(open(p, encoding="utf-8"))
            d.setdefault("scripts", {})[agent_key] = rel
            json.dump(d, open(p, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass

    out_artifacts, rendered, existed, missing = {}, [], [], []
    for asset, tmpl_file, agent_key, art_key in _BRAND_ASSETS:
        dest = os.path.join(dest_dir, "%s-%s.py" % (name, asset))
        rel = "{brain}/brand/%s-%s.py" % (name, asset)
        tmpl = os.path.join(tmpl_dir, tmpl_file)
        if os.path.isfile(dest):
            _repoint(agent_key, rel)                # idempotente por-asset
            out_artifacts[art_key] = dest
            existed.append(asset)
            continue
        if not os.path.isfile(tmpl):
            missing.append(asset)                   # template ausente → se anota
            continue
        try:
            s = open(tmpl, encoding="utf-8").read()
            for k, v in subs.items():
                s = s.replace(k, v)
            os.makedirs(dest_dir, exist_ok=True)
            open(dest, "w", encoding="utf-8").write(s)
        except Exception as e:
            return {"ok": False,
                    "detail": "no se pudo renderizar el %s: %s: %s"
                              % (asset, type(e).__name__, e),
                    "retriable": False}
        _repoint(agent_key, rel)
        out_artifacts[art_key] = dest
        rendered.append(asset)

    # ── emblema: copiar el elegido de la galería a {brain}/brand/emblem.txt ──
    # El banner lo lee y lo tiñe con el color del agente. Sin elegido → el banner
    # cae al monograma de la inicial (nunca vacío). Falla-suave: emblema ausente
    # de la galería se anota, no rompe.
    emblem = str(cfg.get("emblem") or "").strip().lower()
    emblem_note = None
    if emblem:
        src = os.path.join(root, "templates", "agent", "emblems", "%s.txt" % emblem)
        if os.path.isfile(src):
            try:
                os.makedirs(dest_dir, exist_ok=True)
                with open(src, encoding="utf-8") as fh:
                    art = fh.read()
                with open(os.path.join(dest_dir, "emblem.txt"), "w", encoding="utf-8") as fh:
                    fh.write(art)
                emblem_note = "emblema «%s»" % emblem
            except OSError:
                emblem_note = "no pude copiar el emblema «%s»" % emblem
        else:
            emblem_note = "emblema «%s» no está en la galería → monograma default" % emblem

    # el banner es el asset ESPINA (produces lo declara); si su template falta,
    # es entorno roto — permanente. statusline/dashboard ausentes solo se anotan.
    if "banner" in missing:
        return {"ok": False,
                "detail": "falta el template del banner: %s"
                          % os.path.join(tmpl_dir, "agent-banner.py"),
                "retriable": False}
    parts = []
    if rendered:
        parts.append("renderizado: " + " · ".join(rendered))
    if existed:
        parts.append("ya existía: " + " · ".join(existed))
    if missing:
        parts.append("sin template: " + " · ".join(missing))
    if emblem_note:
        parts.append(emblem_note)
    return {"ok": True,
            "detail": "kit de marca de `%s` — %s" % (name, "; ".join(parts)),
            "artifacts": out_artifacts}
