#!/usr/bin/env python3
"""WORKSPACE · config_engine — motor de configuración por TIERS (backend real).

EL PROBLEMA: la Config profunda (proto en feat/config-profunda-proto) necesita
un backend que el front pueda enchufar SIN miedo a romper agentes. El sustrato
ya existe (settings.py = store validado+atómico; agent.json = ficha del agente;
build_hooks = wiring derivado; secret_scan = Regla de Oro), pero no había un
punto único que (a) exponga TODO el schema de forma renderizable y (b) ejecute
los writes con la cadena de seguridad completa según su nivel de riesgo.

ESTE MÓDULO ES ese punto único. Tres tiers de escritura (ARQUITECTURA §2):

  Tier A — SEGUROS (store per-máquina). Wrappers sobre settings.set/reset y
    jobs: ya validados, atómicos y reversibles. Aquí solo se suma el gate de
    secretos (valores str) y el CHANGELOG (settings-log.jsonl per-máquina).

  Tier B — PROTEGIDOS (agent.json de agentes PERSONALES). Escritura CAMPO A
    CAMPO — jamás texto libre — con la cadena completa:
      validar campo+valor → validar la def RESULTANTE completa → gate de
      secretos → BACKUP fechado → escritura atómica (tmp+os.replace) →
      re-derivar hooks si `setup.*` cambió (install.render_hooks_only) →
      VERIFICAR que el agente sigue resolviendo (equivalente in-process de
      `dispatch.py --plan`) → si algo falla, ROLLBACK al backup.
    Exige `confirm=True` explícito; sin confirm devuelve el PLAN (dry-run).

  Tier C — CONSENSO (identidad/estructura de agentes COMPARTIDOS · N3). El
    motor NO ESCRIBE: genera una PROPUESTA por el bus (messages.send
    --type encargo --approval) y reporta "pendiente de consenso". El flip
    real lo aplica un humano del equipo — jamás este módulo.

Detección de tier (conservadora — en la duda, C):
  · agente PRESENTE en el registry committeado del repo (equipo) → C SIEMPRE.
    La membresía es un HECHO DEL REPO (viaja por git): manda sobre cualquier
    flag auto-declarado en agent.json — que es contenido de cerebro, editable
    por cualquiera con acceso al vault. Un "personal": true sembrado en el
    cerebro de un agente del equipo NO lo sube a tier B (anti-envenenamiento).
  · def con "shared": true → C.
  · tier B SOLO para el agente genuinamente personal: NO committeado, cargado
    per-máquina, "personal": true Y owner == socio de la máquina. Todo lo
    demás → C.
  Complemento defensivo (N3 — lo ejecuta un humano del equipo, JAMÁS este
  código): sembrar "shared": true en los agent.json de los cerebros del
  equipo, como cinturón del lado contenido. Este módulo no escribe en
  cerebros del equipo.

🔴 N3 — MARCADO EXPLÍCITO (este módulo JAMÁS los ejecuta):
  · flip de config/identidad de agentes del equipo (zenith/atlas/…): solo
    propuesta por el bus; el write es humano tras consenso.
  · BOOT/00-SOUL.md y todo contenido del cerebro: territorio del agente, este
    motor ni lo lee ni lo escribe (la personalidad NO es config del harness).
  · themes.json / registry committeado / defaults del repo: viajan por git a
    TODO el equipo → aquí solo lectura; lo personal va a capas *.local
    per-máquina (themes.local.json, agents.local.json) que JAMÁS se commitean.
  · `name` y `brain` de un agent.json: estructurales — ni siquiera en tier B
    (brain per-máquina se cambia vía paths.local.json, que es tier A).

Brechas de la ARQUITECTURA que este módulo cierra:
  · mcps.json GESTIONADO (~/.claude/workspace/mcps.json): store declarativo de
    servidores MCP con gate de secretos en el write (mismo patrón que el bus)
    y env como NOMBRES de variables, jamás valores. La MATERIALIZACIÓN al
    canal del motor (mcpServers/.mcp.json) es del doctor — fase siguiente.
  · routing por tarea: formato CONGELADO {"research"|"task"|"utility"|
    "default": "<modelo>"} guardado como JSON en `modelos.task_routing`
    (la semántica de caída a utility ya vive en model_resolver).
  · changelog de settings: ~/.claude/workspace/settings-log.jsonl (per-máquina,
    cero PII, valores recortados) — alimenta "Últimos cambios" y el anillo.
  · themes.local.json (per-máquina): paleta PERSONAL que gana por nombre
    sobre themes.json del repo (theme.py hace el overlay).

Garantías: stdlib puro (3.9+), cross-platform; NINGÚN write sin validar;
escritura atómica siempre; el changelog jamás rompe un write (best-effort);
falla-suave en TODAS las lecturas; amputable (C10): borrar este archivo deja
settings/dispatch/install como estaban.

API:  describe() · stats() · origin_of(k) ·
      set_setting(k,v) · reset_setting(k) · set_job(id,on) ·
      agent_tier(n) · plan_agent_write(n,f,v) · set_agent_field(n,f,v,confirm) ·
      propose_change(n,f,v) ·
      mcp_list() · mcp_set(...) · mcp_remove(n) ·
      get_task_routing() · set_task_routing(map) ·
      themes_effective() · set_theme_local(agente, paleta) · read_log(n).

CLI:  python3 config_engine.py schema [--json] | get <k> | set <k> <v> |
      reset <k> | jobs [enable|disable <id>] | agents [--json] |
      agent get <n> | agent set <n> <campo> <valor> [--yes] |
      agent propose <n> <campo> <valor> [--from <actor>] |
      mcp list|set|rm ... | routing get|set k=v ... |
      theme-local <agente> bg=#rrggbb ... | log [n] | stats
"""
import copy
import datetime
import json
import os
import re
import shutil
import sys
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import settings                                   # noqa: E402 — sustrato tier A
import dispatch                                   # noqa: E402 — registry/verify

try:                                              # gate de secretos (Regla de Oro)
    import secret_scan
except Exception:                                 # falla-suave CON rastro (como el bus)
    secret_scan = None

try:                                              # lock RMW (amputable, como settings)
    from olock import file_lock, LockTimeout
except Exception:
    file_lock, LockTimeout = None, None


# ── rutas (funciones: respetan HOME parchado en tests) ──────────────────────
def _workspace_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def changelog_path():
    return os.path.join(_workspace_dir(), "settings-log.jsonl")


def mcps_path():
    return os.path.join(_workspace_dir(), "mcps.json")


def themes_local_path():
    return os.path.join(_workspace_dir(), "themes.local.json")


def _machine_socio():
    """Socio de ESTA máquina (~/.claude/workspace/socio.local). '' si no hay."""
    try:
        with open(os.path.join(_workspace_dir(), "socio.local"),
                  encoding="utf-8") as fh:
            s = fh.read().strip().lower()
        return s if re.match(r"^[a-z0-9_-]{1,24}$", s) else ""
    except Exception:
        return ""


# ── helpers ─────────────────────────────────────────────────────────────────
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _atomic_json(path, data):
    """Escritura atómica (tmp en el MISMO dir + os.replace). Levanta si falla
    — un write de config a medias NO se tolera en silencio.
    El tmp es único por CALL (pid+token), no solo por proceso: dos hilos del
    mismo pid (ThreadingHTTPServer) jamás comparten tmp."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d-%s" % (path, os.getpid(), uuid.uuid4().hex[:8])
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _with_lock(path, fn):
    """Serializa un RMW sobre `path`. Sin olock/timeout → degrada a sin-lock
    (mismo trade-off que settings._with_store_lock)."""
    if file_lock is None:
        return fn()
    try:
        with file_lock(path, timeout=5):
            return fn()
    except LockTimeout:
        return fn()


def _clip(v, n=400):
    """Valor apto para el changelog: serializado y RECORTADO (cero blobs)."""
    try:
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    except Exception:
        s = str(v)
    return s if len(s) <= n else s[:n] + "…"


def _gate(text, where):
    """Gate duro de secretos (reusa secret_scan.gate_text — respeta el
    marcador inline y el override de emergencia, con rastro ruidoso).
    Devuelve (findings, mensaje_de_bloqueo)."""
    if secret_scan is None:
        try:
            print("⚠ config_engine: secret_scan no disponible — write SIN "
                  "escanear (revísalo a mano).", file=sys.stderr)
        except Exception:
            pass
        return [], ""
    findings = secret_scan.gate_text(str(text or ""), where=where)
    if findings:
        return findings, secret_scan.block_message(findings, where)
    return [], ""


def _gate_fields(data, where):
    """Gate de secretos CAMPO POR CAMPO sobre un dict anidado.

    Antes se escaneaba `json.dumps(data)` — UNA línea — y el marcador
    `workspace:allow-secret` en cualquier campo eximía el write COMPLETO
    (un allow en `tagline` dejaba pasar un secreto en `display`). Aquí cada
    hoja se escanea por separado: el allow inline exime SOLO su campo.
    El override de emergencia WORKSPACE_ALLOW_SECRET sigue siendo global y
    RUIDOSO (lo maneja secret_scan.gate_text); se corta en un solo aviso.
    Devuelve (findings, mensaje) del PRIMER campo bloqueado; ([], "") si pasa.
    """
    if secret_scan is not None:
        try:
            if secret_scan.env_override_active():
                # un solo aviso ruidoso para todo el write, no uno por campo
                return _gate(json.dumps(data, ensure_ascii=False), where)
        except Exception:
            pass

    def _leaves(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield from _leaves(v, "%s.%s" % (prefix, k) if prefix else str(k))
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                yield from _leaves(v, "%s[%d]" % (prefix, i))
        else:
            yield prefix, obj

    for fld, val in _leaves(data):
        findings, msg = _gate(json.dumps(val, ensure_ascii=False),
                              "%s · campo %s" % (where, fld))
        if findings:
            return findings, msg
    return [], ""


def _blocked(msg):
    return {"ok": False, "blocked": True, "error": msg}


# ── changelog (settings-log.jsonl · per-máquina · cero PII) ─────────────────
def _log(action, key, old, new, tier, actor="", extra=None):
    """Append JSONL best-effort — el changelog JAMÁS rompe un write."""
    try:
        rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "action": action, "key": key, "tier": tier,
               "old": _clip(old), "new": _clip(new)}
        if actor:
            rec["actor"] = str(actor)[:24]
        if isinstance(extra, dict):
            rec.update(extra)
        p = changelog_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_log(limit=50):
    """Últimas `limit` entradas del changelog (viejas→nuevas). Falla-suave."""
    out = []
    try:
        with open(changelog_path(), encoding="utf-8") as fh:
            lines = fh.readlines()
        for ln in lines[-max(1, int(limit)):]:
            try:
                rec = json.loads(ln)
                if isinstance(rec, dict):
                    out.append(rec)
            except Exception:
                continue
    except Exception:
        pass
    return out


# ═══════════════════════════════════════════════════════════════════════════
# CAPA READ — schema estructurado para que el front renderice ambos tiers
# ═══════════════════════════════════════════════════════════════════════════

# env que GANA sobre el setting (candado 🔒 del proto — precedencia real)
_ENV_LOCKS = {
    "hooks.skill_review": "WORKSPACE_NO_SKILL_REVIEW",
    "hooks.transcript_backup": "WORKSPACE_NO_TRANSCRIPT_BACKUP",
    "hooks.memory_flush": "WORKSPACE_NO_MEMORY_FLUSH",
    "hooks.security_guidance": "WORKSPACE_NO_SECURITY_GUIDANCE",
    "hooks.telemetry": "WORKSPACE_NO_TELEMETRY",
    "ui.stars": "WORKSPACE_NO_STARS",
    "ui.anim": "WORKSPACE_NO_ANIM",
    "modelos.default_engine": "WORKSPACE_ENGINE",
}


def _env_lock_active(key):
    var = _ENV_LOCKS.get(key, "")
    return var if var and os.environ.get(var) else ""


def origin_of(key):
    """Origen del valor EFECTIVO: 'env' | 'delegado' | 'custom' | 'default'.
    Es la transparencia que pide la visión (saber qué manda)."""
    spec = settings._BY_KEY.get(key)
    if spec is None:
        return ""
    if _env_lock_active(key):
        return "env"
    if spec.get("delegated"):
        try:
            if settings._delegated_read(key) is not None:
                return "delegado"
        except Exception:
            pass
    if settings.get_stored(key) is not None:
        return "custom"
    return "default"


def describe_settings():
    """El SETTINGS_SCHEMA renderizable: cada entrada con valor efectivo,
    origen y candado de env. Read-only, jamás toca disco para escribir."""
    out = []
    for s in settings.SETTINGS_SCHEMA:
        key = s["key"]
        try:
            value = settings.get(key)
        except Exception:
            value = s.get("default")
        env_var = _ENV_LOCKS.get(key, "")
        row = {"key": key, "group": s["group"], "label": s["label"],
               "type": s["type"], "default": s.get("default"),
               "help": s.get("help", ""), "applies": s.get("applies", ""),
               "scaffold": bool(s.get("scaffold")),
               "delegated": bool(s.get("delegated")),
               "readonly": bool(s.get("readonly")),
               "value": value, "origin": origin_of(key),
               "tier": "A" if not s.get("readonly") else "read"}
        if s.get("choices"):
            row["choices"] = list(s["choices"])
        if s.get("range"):
            row["range"] = list(s["range"])
        if env_var:
            row["env_lock"] = env_var
            row["env_active"] = bool(_env_lock_active(key))
        out.append(row)
    return out


def describe_agents():
    """Agentes del registry efectivo con su TIER de escritura y campos
    editables. La def cruda es SOLO LECTURA (el front la muestra, no la edita)."""
    out = []
    try:
        agents = dispatch.load_registry().get("agents", [])
    except Exception:
        agents = []
    for entry in agents:
        name = entry.get("name", "")
        try:
            cfg = dispatch.load_agent_cfg(entry)
        except Exception:
            cfg = {"name": name, "_missing_def": True}
        try:
            brain = dispatch.resolve_brain(name, cfg)
        except Exception:
            brain = ""
        tier, why = agent_tier(name)
        row = {"name": name, "display": cfg.get("display", ""),
               "tagline": cfg.get("tagline", ""),
               "engine": cfg.get("engine", entry.get("engine", "")),
               "color": cfg.get("color", ""),
               "owner": cfg.get("owner", ""),
               "brain": brain, "loaded": bool(entry.get("_loaded")),
               "setup": cfg.get("setup") if isinstance(cfg.get("setup"), dict) else {},
               "scripts": sorted((cfg.get("scripts") or {}).keys()),
               "missing_def": bool(cfg.get("_missing_def")),
               "tier": tier, "tier_reason": why,
               "writable_fields": sorted(_AGENT_FIELDS) if tier == "B" else [],
               "n3": tier == "C"}
        out.append(row)
    return out


def describe_hooks():
    """Contrato de eventos (listeners + kill-switches + candado env)."""
    rows = []
    try:
        import events
        for l in events.LISTENERS:
            rows.append({"script": l["script"], "event": l["event"],
                         "timeout": l.get("timeout"),
                         "severity": l.get("severity"),
                         "requires": l.get("requires"),
                         "matcher": l.get("matcher")})
    except Exception:
        pass
    switches = []
    for s in settings.SETTINGS_SCHEMA:
        if s["group"] != "hooks":
            continue
        k = s["key"]
        switches.append({"key": k, "label": s["label"],
                         "enabled": settings.enabled(k),
                         "env_lock": _ENV_LOCKS.get(k, ""),
                         "env_active": bool(_env_lock_active(k))})
    return {"listeners": rows, "switches": switches,
            "note": "wiring DERIVADO (build_hooks); settings.local.json se "
                    "regenera — jamás editarlo a mano"}


def describe_models():
    """Panel de modelos: motor default, overrides por agente, routing por
    tarea (formato congelado) y providers (solo nombres — read-only)."""
    overrides = {}
    for s in settings.SETTINGS_SCHEMA:
        k = s["key"]
        if s["group"] == "agentes" and k.endswith(".model"):
            v = settings.get_stored(k)
            if v:
                overrides[k.split(".")[1]] = v
    providers = []
    try:
        pdir = os.path.join(ROOT, "providers")
        providers = sorted(f[:-5] for f in os.listdir(pdir)
                           if f.endswith(".json"))
    except Exception:
        pass
    return {"default_engine": settings.get("modelos.default_engine"),
            "engines": dispatch.available_engines(),
            "agent_overrides": overrides,
            "task_routing": get_task_routing(),
            "providers": providers,
            "providers_note": "declarativos (providers/*.json) — solo lectura "
                              "aquí; editables a mano con secret_scan al cargar"}


def describe_mcps():
    data = _load_mcps()
    return {"servers": data.get("servers", {}),
            "path": mcps_path(),
            "materialized": False,
            "note": "capa GESTIONADA per-máquina; la materialización al canal "
                    "del motor (claude-code: bloque mcpServers) la corre "
                    "`workspace config mcp materialize` o `workspace doctor` (fase "
                    "5c). env = NOMBRES de variables, jamás valores."}


def describe_themes():
    local = _read_json(themes_local_path())
    repo = _read_json(os.path.join(ROOT, "themes.json"))
    return {"repo": repo, "local": local, "effective": themes_effective(),
            "repo_note": "themes.json viaja por git a TODO el equipo — "
                         "editarlo es tier C (propuesta); lo personal va a "
                         "themes.local.json (per-máquina, gana por nombre)."}


def stats():
    """El anillo del proto: cuánto está personalizado en esta máquina."""
    rows = describe_settings()
    editable = [r for r in rows if not r["readonly"]]
    custom = [r for r in editable if r["origin"] in ("custom", "env")]
    jobs = settings.jobs_status()
    return {"settings_total": len(editable), "settings_custom": len(custom),
            "pct_custom": round(100.0 * len(custom) / len(editable), 1) if editable else 0.0,
            "jobs_on": sum(1 for j in jobs if j["enabled"]),
            "jobs_total": len(jobs),
            "mcps": len(_load_mcps().get("servers", {})),
            "agents": len(describe_agents()),
            "changes_logged": len(read_log(limit=10000))}


def describe():
    """TODO el schema estructurado — lo que el front renderiza (Simple ↔
    Avanzado salen de los MISMOS datos: label/help = simple; key/applies/
    origen/candados = avanzado)."""
    return {
        "settings": describe_settings(),
        "jobs": settings.jobs_status(),
        "agents": describe_agents(),
        "hooks": describe_hooks(),
        "models": describe_models(),
        "mcps": describe_mcps(),
        "themes": describe_themes(),
        "stats": stats(),
        "tiers": {
            "A": "store per-máquina (settings/jobs/routing/themes.local/mcps) "
                 "— validado, atómico, reversible, con changelog",
            "B": "agent.json de agentes GENUINAMENTE personales (no "
                 "committeados + personal:true + owner=socio), campo a campo: "
                 "validar → "
                 "backup fechado → write atómico → re-derivar hooks → "
                 "verificar (--plan) → rollback si falla. Exige confirm.",
            "C": "identidad/estructura COMPARTIDA (N3): este backend NO "
                 "escribe — propone por el bus y queda pendiente de consenso.",
        },
        "n3": [
            "flip de config/identidad de agentes del equipo (solo propuesta)",
            "BOOT/00-SOUL.md y contenido del cerebro (territorio del agente)",
            "themes.json / registry / defaults del repo (viajan por git)",
            "lo personal JAMÁS se commitea (capas *.local per-máquina)",
            "name/brain de agent.json (estructurales — ni en tier B)",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# TIER A — writes seguros (store per-máquina) + changelog
# ═══════════════════════════════════════════════════════════════════════════

def set_setting(key, value, actor=""):
    """Wrapper seguro de settings.set: gate de secretos (valores str) +
    changelog. Inválido → {"ok": False} SIN tocar disco."""
    if isinstance(value, str):
        findings, msg = _gate(value, "setting %s" % key)
        if findings:
            return _blocked(msg)
    try:
        old = settings.get(key)
    except ValueError:
        old = None
    try:
        v = settings.set(key, value)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    _log("set", key, old, v, "A", actor=actor)
    return {"ok": True, "key": key, "old": old, "new": v, "tier": "A",
            "origin": origin_of(key)}


def reset_setting(key, actor=""):
    """Quita el override del store (vuelve a default/delegado) + changelog."""
    try:
        old = settings.get(key)
        settings.reset(key)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    new = settings.get(key)
    _log("reset", key, old, new, "A", actor=actor)
    return {"ok": True, "key": key, "old": old, "new": new, "tier": "A",
            "origin": origin_of(key)}


def set_job(job_id, on, actor=""):
    """Enable/disable de un job del catálogo + changelog."""
    old = settings.is_job_enabled(job_id)
    try:
        v = settings.set_job_enabled(job_id, on)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    _log("job", "jobs.%s" % job_id, old, v, "A", actor=actor)
    return {"ok": True, "job": job_id, "old": old, "new": v, "tier": "A"}


# ── routing por tarea (formato CONGELADO — la brecha del scaffold) ──────────
try:
    from model_resolver import TASKS as _ROUTING_TASKS
except Exception:
    _ROUTING_TASKS = ("research", "task", "utility", "default")

_MODEL_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,63}$")


def get_task_routing():
    """{tarea: modelo} parseado de `modelos.task_routing` (JSON en el store).
    Falla-suave → {}. La SEMÁNTICA (caída a utility, jamás al default caro)
    vive en model_resolver — aquí solo el dato."""
    try:
        raw = settings.get("modelos.task_routing")
        data = json.loads(raw) if raw else {}
        return {k: v for k, v in data.items()
                if k in _ROUTING_TASKS and isinstance(v, str)} \
            if isinstance(data, dict) else {}
    except Exception:
        return {}


def set_task_routing(mapping, actor=""):
    """Valida y guarda el routing por tarea. Claves ⊆ TASKS (research/task/
    utility/default); valores = tokens de modelo ('' = quitar la regla)."""
    if not isinstance(mapping, dict):
        return {"ok": False, "error": "routing espera un mapa {tarea: modelo}"}
    clean = {}
    for k, v in mapping.items():
        if k not in _ROUTING_TASKS:
            return {"ok": False,
                    "error": "tarea desconocida %r (válidas: %s)"
                             % (k, "/".join(_ROUTING_TASKS))}
        if v in ("", None):
            continue
        if not isinstance(v, str) or not _MODEL_RX.match(v):
            return {"ok": False, "error": "modelo inválido para %r: %r" % (k, v)}
        clean[k] = v
    old = get_task_routing()
    payload = json.dumps(clean, ensure_ascii=False, sort_keys=True) if clean else ""
    findings, msg = _gate(payload, "modelos.task_routing")
    if findings:
        return _blocked(msg)
    try:
        settings.set("modelos.task_routing", payload)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    _log("set", "modelos.task_routing", old, clean, "A", actor=actor)
    return {"ok": True, "old": old, "new": clean, "tier": "A"}


# ── tema PERSONAL (themes.local.json — jamás el repo) ───────────────────────
_HEX_RX = re.compile(r"^#[0-9a-fA-F]{6}$")
_THEME_KEYS = ("bg", "fg", "cursor")
_NAME_RX = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def themes_effective():
    """themes.json del repo con el overlay de themes.local.json (el local
    gana por nombre, mergeando por clave). Espejo del merge de theme.py."""
    base = _read_json(os.path.join(ROOT, "themes.json"))
    local = _read_json(themes_local_path())
    for name, pal in local.items():
        if isinstance(pal, dict):
            merged = dict(base.get(name) or {})
            merged.update(pal)
            base[name] = merged
    return base


def set_theme_local(agent, palette, actor=""):
    """Escribe la paleta PERSONAL de `agent` en themes.local.json (per-máquina).
    palette = {bg/fg/cursor: '#rrggbb'} · None = quitar el override local.
    JAMÁS toca themes.json del repo (eso es tier C — propuesta)."""
    name = str(agent or "").strip().lower()
    if not _NAME_RX.match(name):
        return {"ok": False, "error": "nombre de agente inválido: %r" % agent}
    if palette is not None:
        if not isinstance(palette, dict) or not palette:
            return {"ok": False, "error": "paleta vacía o inválida"}
        for k, v in palette.items():
            if k not in _THEME_KEYS:
                return {"ok": False, "error": "clave de paleta desconocida %r "
                                              "(válidas: bg/fg/cursor)" % k}
            if not isinstance(v, str) or not _HEX_RX.match(v):
                return {"ok": False,
                        "error": "%s espera color hex #rrggbb, no %r" % (k, v)}
    path = themes_local_path()

    def _rmw():
        data = _read_json(path)
        old = data.get(name)
        if palette is None:
            data.pop(name, None)
        else:
            data[name] = dict(palette)
        _atomic_json(path, data)
        return old
    old = _with_lock(path, _rmw)
    _log("theme-local", "themes.local.%s" % name, old, palette, "A", actor=actor)
    return {"ok": True, "agent": name, "old": old, "new": palette, "tier": "A"}


# ═══════════════════════════════════════════════════════════════════════════
# TIER B — agent.json campo a campo (la cadena completa de seguridad)
# ═══════════════════════════════════════════════════════════════════════════

# Campos EDITABLES vía tier B. `name` y `brain` NO están (estructurales, N3);
# `scripts` tampoco (rutas ejecutables — editarlas es superficie de ataque;
# el front las muestra read-only). Jamás textarea libre sobre el archivo.
_AGENT_FIELDS = {
    "engine": {"type": "engine",
               "help": "motor del agente (engines/*.py instalados)"},
    "display": {"type": "str", "max": 48, "empty": False,
                "help": "nombre para mostrar"},
    "tagline": {"type": "str", "max": 120, "empty": True,
                "help": "lema corto bajo el banner"},
    "color": {"type": "color",
              "help": "color canónico del banner/tema"},
    "setup.session_journal": {"type": "bool", "rederive_hooks": True,
                              "help": "journals de sesión (gate de hooks)"},
    "setup.autonomous": {"type": "bool", "rederive_hooks": True,
                         "help": "participa del trabajo autónomo (heartbeat)"},
}

_TRUE = ("1", "true", "yes", "on", "si", "sí")
_FALSE = ("0", "false", "no", "off")


def _has_ctrl_chars(s):
    """True si `s` trae caracteres de control: C0 (incl. \\n/\\r/\\t y ESC —
    inicio de secuencias ANSI/OSC), DEL, o C1 (0x80–0x9F: CSI/OSC de un byte).
    display/tagline se pintan en banner/TUI/terminal: un escape inyectado ahí
    es inyección de terminal — se RECHAZA, jamás se sanea en silencio."""
    return any(ord(c) < 0x20 or ord(c) == 0x7f or 0x80 <= ord(c) <= 0x9f
               for c in s)


def _validate_agent_field(field, value):
    """(valor_normalizado, error). Campo fuera del catálogo → error."""
    spec = _AGENT_FIELDS.get(field)
    if spec is None:
        return None, ("campo no editable: %r (editables: %s; name/brain/"
                      "scripts son estructurales)" %
                      (field, ", ".join(sorted(_AGENT_FIELDS))))
    t = spec["type"]
    if t == "bool":
        if isinstance(value, bool):
            return value, ""
        if isinstance(value, str):
            v = value.strip().lower()
            if v in _TRUE:
                return True, ""
            if v in _FALSE:
                return False, ""
        return None, "%s espera bool (true/false), no %r" % (field, value)
    if t == "str":
        if not isinstance(value, str):
            return None, "%s espera texto, no %r" % (field, value)
        v = value.strip()
        if not v and not spec.get("empty"):
            return None, "%s no puede quedar vacío" % field
        if len(v) > spec["max"]:
            return None, "%s excede %d caracteres" % (field, spec["max"])
        if _has_ctrl_chars(v):
            return None, ("%s contiene caracteres de control o secuencias de "
                          "escape (\\n, ESC/ANSI/OSC…) — solo texto plano "
                          "imprimible (se pinta en banner/TUI)" % field)
        return v, ""
    if t == "engine":
        v = str(value or "").strip().lower()
        avail = dispatch.available_engines()
        if v not in avail:
            return None, ("motor %r no instalado (instalados: %s)"
                          % (value, ", ".join(avail) or "ninguno"))
        return v, ""
    if t == "color":
        try:
            from agent_admin import CANON_COLORS, _COLOR_ALIASES
        except Exception:
            CANON_COLORS, _COLOR_ALIASES = ("gray",), {}
        v = str(value or "").strip().lower()
        v = _COLOR_ALIASES.get(v, v)
        if v not in CANON_COLORS:
            return None, ("color desconocido %r (canónicos: %s)"
                          % (value, ", ".join(CANON_COLORS)))
        return v, ""
    return None, "tipo de campo desconocido: %r" % t


def _validate_agent_def(defn, expect_name):
    """Valida la def COMPLETA resultante contra el shape que dispatch espera.
    '' = válida. Se corre ANTES de escribir — jamás se persiste una def rota."""
    if not isinstance(defn, dict):
        return "la definición no es un objeto JSON"
    name = defn.get("name")
    if not isinstance(name, str) or not name:
        return "falta `name` en la definición"
    if expect_name and name != expect_name:
        return ("`name` cambió (%r → %r) — el nombre es estructural (N3), "
                "no se toca" % (expect_name, name))
    try:
        import agentsreg
        if not agentsreg.is_valid_name(name):
            return "nombre inválido: %r" % name
    except Exception:
        pass
    eng = defn.get("engine")
    if eng is not None and (not isinstance(eng, str) or not eng.strip()):
        return "`engine` debe ser string no vacío"
    setup = defn.get("setup")
    if setup is not None:
        if not isinstance(setup, dict):
            return "`setup` debe ser un objeto"
        for k, v in setup.items():
            if not str(k).startswith("_") and not isinstance(v, bool):
                return "`setup.%s` debe ser bool, no %r" % (k, v)
    scripts = defn.get("scripts")
    if scripts is not None:
        if not isinstance(scripts, dict):
            return "`scripts` debe ser un mapa nombre→ruta"
        for k, v in scripts.items():
            if not isinstance(v, str) or not v:
                return "`scripts.%s` debe ser ruta (string)" % k
    for f in ("display", "tagline", "color", "owner"):
        v = defn.get(f)
        if v is not None and not isinstance(v, str):
            return "`%s` debe ser string" % f
    return ""


def _committed_agents():
    """Nombres+aliases del registry COMMITTEADO del repo, en minúsculas.

    La membresía aquí es un HECHO DEL REPO (el archivo viaja por git y lo
    protege el flujo de PRs) — a diferencia de los flags de agent.json, que
    son CONTENIDO DE CEREBRO editable por cualquiera con acceso al vault.
    Por eso la pertenencia manda sobre lo auto-declarado. Falla-suave → set()
    vacío (sin registry no hay membresía que reclamar; el resto del tier
    sigue siendo conservador)."""
    names = set()
    try:
        reg = _read_json(dispatch.registry_path())
        for a in reg.get("agents", []) or []:
            if not isinstance(a, dict):
                continue
            nm = str(a.get("name", "")).strip().lower()
            if nm:
                names.add(nm)
            aliases = a.get("aliases", [])
            if isinstance(aliases, str):
                aliases = [aliases]
            if isinstance(aliases, (list, tuple)):
                names.update(str(x).strip().lower()
                             for x in aliases if x is not None and str(x).strip())
    except Exception:
        pass
    return names


def agent_tier(name):
    """('B'|'C'|'', razón). CONSERVADOR: en la duda → C (propuesta, no write).

    ORDEN (la membresía en el repo manda — anti-envenenamiento):
      · presente en el registry committeado (equipo) → C SIEMPRE, aunque su
        agent.json declare personal:true (los flags son contenido de cerebro,
        editable; jamás suben de tier a un agente del equipo).
      · def "shared": true → C.
      · genuinamente personal (NO committeado + "personal": true + owner ==
        socio de la máquina) → B.
      · todo lo demás (sin personal, owner ausente/ajeno, socio sin declarar)
        → C.
    Complemento N3 (lo ejecuta un humano del equipo, no este código): sembrar
    shared:true en los agent.json de los cerebros del equipo como cinturón
    del lado contenido.
    """
    entry = dispatch.find_agent(name)
    if entry is None:
        return "", "agente desconocido: %r" % name
    # ── membresía en el repo: se decide ANTES de leer el agent.json (contenido
    #    potencialmente hostil) — un agente del equipo es C sin apelación.
    if str(entry.get("name", "")).strip().lower() in _committed_agents():
        return "C", ("agente del registry committeado (equipo) — identidad "
                     "compartida, requiere consenso N3; la membresía en el "
                     "repo manda sobre flags del agent.json")
    if not entry.get("_loaded"):
        # en el registry efectivo sin estar committeado ni cargado: anómalo →
        # conservador (misma razón: identidad no personal verificable)
        return "C", ("agente del registry committeado (equipo) — identidad "
                     "compartida, requiere consenso N3")
    defpath = _agent_def_path(entry)
    try:
        with open(defpath, encoding="utf-8") as fh:
            defn = json.load(fh)
        if not isinstance(defn, dict):
            raise ValueError("no es un objeto JSON")
    except FileNotFoundError:
        defn = {}
    except Exception as e:
        # def ILEGIBLE/corrupta: ni B ni C — se repara antes de configurar
        return "", ("la definición está ilegible/corrupta (%s) — repárala "
                    "primero (agent_admin.load / doctor): %s" % (e, defpath))
    if defn.get("shared") is True:
        return "C", "definición marcada shared:true — requiere consenso N3"
    owner = str(defn.get("owner", "")).strip().lower()
    socio = _machine_socio()
    if defn.get("personal") is True and owner and socio and owner == socio:
        return "B", ("agente personal del socio activo (personal:true, "
                     "owner=%s)" % owner)
    if defn.get("personal") is True:
        return "C", ("personal:true pero el dueño no coincide con la máquina "
                     "(owner=%r, socio=%r) — conservador: consenso N3"
                     % (owner, socio))
    return "C", ("no marcado personal / dueño no verificable (owner=%r, "
                 "socio=%r) — conservador: consenso N3" % (owner, socio))


def _agent_def_path(entry):
    """Ruta del agent.json de un agente CARGADO (tier B solo aplica a estos)."""
    try:
        import agentsreg
        return agentsreg.agent_json_path(entry["brain"])
    except Exception:
        return os.path.join(entry.get("brain", ""), ".workspace", "agent.json")


def _get_dotted(d, field):
    if "." in field:
        a, b = field.split(".", 1)
        sub = d.get(a)
        return sub.get(b) if isinstance(sub, dict) else None
    return d.get(field)


def _set_dotted(d, field, value):
    if "." in field:
        a, b = field.split(".", 1)
        if not isinstance(d.get(a), dict):
            d[a] = {}
        d[a][b] = value
    else:
        d[field] = value


def _backup_file(path):
    """Backup FECHADO junto al archivo (agent.json.bak-YYYYMMDD-HHMMSS[-N]).
    Devuelve la ruta del backup. Levanta si no se puede — sin backup no hay
    write."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak-%s" % (path, stamp)
    n = 1
    while os.path.exists(bak):
        bak = "%s.bak-%s-%d" % (path, stamp, n)
        n += 1
    shutil.copy2(path, bak)
    return bak


def _restore_from_backup(path, backup):
    """Rollback atómico: copia el backup a un tmp y os.replace sobre el
    archivo. El backup se CONSERVA (evidencia)."""
    tmp = "%s.rollback-%d-%s" % (path, os.getpid(), uuid.uuid4().hex[:8])
    shutil.copy2(backup, tmp)
    os.replace(tmp, path)


def _rederive_hooks(defn, brain):
    """Re-deriva el bloque `hooks` de settings.local.json del cerebro
    (install.render_hooks_only — la MISMA fuente que install/doctor/repair)."""
    import install
    install.render_hooks_only(dict(defn), brain)


def _verify_agent(name):
    """Verificación post-write EQUIVALENTE a `dispatch.py --plan <agente>`,
    in-process (mismas funciones que --plan usa, sin subprocess — determinista
    y hermética): el agente resuelve en el registry, su def carga y no está
    corrupta, el cerebro existe y el motor declarado está disponible.
    '' = OK; si no, la razón."""
    try:
        entry = dispatch.find_agent(name)
        if not entry:
            return "el agente ya no resuelve en el registry"
        cfg = dispatch.load_agent_cfg(entry)
        if cfg.get("_missing_def"):
            return "la definición quedó faltante o corrupta"
        brain = dispatch.resolve_brain(entry["name"], cfg)
        if not brain or not os.path.isdir(brain):
            return "el cerebro no resuelve: %r" % brain
        engine = cfg.get("engine") or entry.get("engine") or ""
        if engine and dispatch.load_engine(engine) is None:
            return "el motor %r no está disponible" % engine
        dispatch.expand_scripts(cfg, brain)   # no debe levantar
        return ""
    except Exception as e:
        return "la verificación falló: %s: %s" % (type(e).__name__, e)


def plan_agent_write(agent, field, value):
    """El PLAN de un write tier B (dry-run absoluto — cero efectos): qué se
    cambiaría y la cadena que correría. Es lo que set_agent_field devuelve
    cuando confirm=False."""
    tier, why = agent_tier(agent)
    if tier != "B":
        return {"ok": False, "tier": tier, "error": why,
                "hint": "tier C no escribe — usa propose_change() "
                        "(propuesta por el bus, consenso N3)" if tier == "C" else ""}
    v, err = _validate_agent_field(field, value)
    if err:
        return {"ok": False, "tier": "B", "error": err}
    entry = dispatch.find_agent(agent)
    cur = _read_json(_agent_def_path(entry))
    spec = _AGENT_FIELDS[field]
    steps = ["validar campo y def resultante", "gate de secretos",
             "backup fechado", "escritura atómica (tmp+os.replace)"]
    if spec.get("rederive_hooks"):
        steps.append("re-derivar hooks (install.render_hooks_only)")
    steps += ["verificar que el agente resuelve (≡ dispatch --plan)",
              "rollback al backup si algo falla"]
    return {"ok": False, "needs_confirm": True, "tier": "B",
            "agent": entry["name"], "field": field,
            "old": _get_dotted(cur, field), "new": v, "chain": steps,
            "hint": "repite con confirm=True (CLI: --yes) para aplicar"}


def set_agent_field(agent, field, value, confirm=False, actor=""):
    """EL WRITE TIER B — un campo de agent.json con la cadena completa.

    Sin confirm → devuelve el plan (no toca disco). Con confirm:
      validar → backup fechado → write atómico → re-derivar hooks (si
      setup.*) → verificar (≡ --plan) → rollback al backup si falla.
    Devuelve dict con ok/old/new/backup/verified/rolled_back/error."""
    tier, why = agent_tier(agent)
    if tier == "":
        return {"ok": False, "error": why}
    if tier == "C":
        return {"ok": False, "tier": "C", "applied": False, "error": why,
                "hint": "genera una propuesta: propose_change(%r, %r, …) — "
                        "el flip de agentes del equipo es N3 (consenso), este "
                        "backend jamás lo aplica" % (agent, field)}
    v, err = _validate_agent_field(field, value)
    if err:
        return {"ok": False, "tier": "B", "error": err}
    if not confirm:
        return plan_agent_write(agent, field, v)

    entry = dispatch.find_agent(agent)
    name = entry["name"]
    brain = entry.get("brain", "")
    path = _agent_def_path(entry)

    # El RMW COMPLETO (leer → validar → backup → write → rederivar → verificar)
    # corre bajo lock (olock, mismo patrón que mcps/themes): dos POSTs
    # concurrentes del mismo pid (ThreadingHTTPServer) o de dos procesos se
    # serializan — sin lost-updates ni backups/rollbacks entrelazados.
    def _rmw():
        # lectura ESTRICTA: una def ilegible no se edita (load/doctor la repara)
        try:
            with open(path, encoding="utf-8") as fh:
                cur = json.load(fh)
            if not isinstance(cur, dict) or not cur.get("name"):
                raise ValueError("definición sin `name`")
        except Exception as e:
            return {"ok": False, "tier": "B",
                    "error": "no edito una def ilegible/corrupta (%s) — "
                             "repárala primero (agent_admin.load / doctor): %s"
                             % (e, path)}

        old = _get_dotted(cur, field)
        if old == v:
            return {"ok": True, "tier": "B", "agent": name, "field": field,
                    "old": old, "new": v, "changed": False,
                    "note": "sin cambio — no se escribió nada"}

        new_def = copy.deepcopy(cur)
        _set_dotted(new_def, field, v)
        err = _validate_agent_def(new_def, expect_name=cur.get("name"))
        if err:
            return {"ok": False, "tier": "B", "error": err}
        # gate POR CAMPO: un allow-secret inline exime SOLO su campo (F3)
        findings, msg = _gate_fields(new_def, "agent.json de %s" % name)
        if findings:
            return _blocked(msg)

        # ── backup fechado (sin backup NO hay write) ──
        try:
            backup = _backup_file(path)
        except Exception as e:
            return {"ok": False, "tier": "B",
                    "error": "no pude crear el backup (%s) — write abortado "
                             "sin tocar el archivo" % e}

        rederive = bool(_AGENT_FIELDS[field].get("rederive_hooks"))

        def _fail(stage, detail):
            """Rollback al backup + (si aplica) re-derivar hooks con la def
            vieja."""
            rolled = False
            try:
                _restore_from_backup(path, backup)
                rolled = True
                if rederive:
                    try:
                        _rederive_hooks(cur, brain)
                    except Exception:
                        pass   # best-effort: doctor/repair lo recablea
            except Exception as e:
                detail += " · ADEMÁS el rollback falló (%s) — restaura a " \
                          "mano desde %s" % (e, backup)
            _log("write-failed", "agent.%s.%s" % (name, field), old, v, "B",
                 actor=actor, extra={"stage": stage, "rolled_back": rolled})
            return {"ok": False, "tier": "B", "agent": name, "field": field,
                    "error": "%s: %s" % (stage, detail), "backup": backup,
                    "rolled_back": rolled}

        # ── escritura atómica ──
        try:
            _atomic_json(path, new_def)
        except Exception as e:
            return _fail("escritura", str(e))
        # ── re-derivar wiring dependiente ──
        if rederive:
            try:
                _rederive_hooks(new_def, brain)
            except Exception as e:
                return _fail("re-derivación de hooks", str(e))
        # ── verificación post-write (≡ dispatch --plan) ──
        verr = _verify_agent(name)
        if verr:
            return _fail("verificación post-write", verr)

        _log("agent-set", "agent.%s.%s" % (name, field), old, v, "B",
             actor=actor, extra={"backup": os.path.basename(backup)})
        return {"ok": True, "tier": "B", "agent": name, "field": field,
                "old": old, "new": v, "changed": True, "backup": backup,
                "hooks_rederived": rederive, "verified": True}

    return _with_lock(path, _rmw)


# ═══════════════════════════════════════════════════════════════════════════
# TIER C — consenso: PROPUESTA por el bus, jamás write (N3)
# ═══════════════════════════════════════════════════════════════════════════

def propose_change(agent, field, value, actor="", note=""):
    """Genera una PROPUESTA de cambio por el bus (messages.py, --approval).
    NO escribe configuración — el flip de identidad/estructura de agentes
    compartidos es N3: lo aplica un humano tras consenso del equipo.
    `field`/`value` van como texto en la propuesta (el bus les aplica su
    propio gate de secretos antes de escribir el mensaje)."""
    entry = dispatch.find_agent(agent)
    if entry is None:
        return {"ok": False, "error": "agente desconocido: %r" % agent}
    field = str(field or "").strip()[:64]
    if not field:
        return {"ok": False, "error": "falta el campo a proponer"}
    sender = actor or _machine_socio() or "config"
    subject = "[config·N3] propuesta: %s.%s → %s" % (
        entry["name"], field, _clip(value, 60))
    body = (
        "PROPUESTA DE CONFIGURACIÓN (tier C — consenso N3)\n\n"
        "· agente : %s\n· campo  : %s\n· valor  : %s\n· propone: %s\n%s\n"
        "NADA se ha aplicado. Este cambio toca identidad/estructura "
        "compartida: requiere consenso del equipo y el flip lo ejecuta un "
        "humano (no el backend de config)."
        % (entry["name"], field, _clip(value, 400), sender,
           ("· nota   : %s\n" % _clip(note, 400)) if note else ""))
    try:
        import messages
        ids = messages.send(from_agent=sender, to_agent=entry["name"],
                            type="encargo", subject=subject, body=body,
                            requires_approval=True)
    except Exception as e:
        return {"ok": False, "error": "el bus no está disponible: %s" % e}
    if not ids:
        return {"ok": False, "tier": "C", "applied": False,
                "error": "la propuesta no se pudo escribir (cerebro destino "
                         "sin resolver, o el gate de secretos la bloqueó — "
                         "revisa stderr)"}
    _log("propose", "agent.%s.%s" % (entry["name"], field), None,
         _clip(value, 120), "C", actor=sender,
         extra={"proposal_ids": ids, "applied": False})
    return {"ok": True, "tier": "C", "applied": False, "agent": entry["name"],
            "field": field, "proposal_ids": ids,
            "status": "pendiente de consenso (N3) — propuesta enviada por el bus"}


# ═══════════════════════════════════════════════════════════════════════════
# MCPs — capa GESTIONADA per-máquina (mcps.json) · la mayor brecha
# ═══════════════════════════════════════════════════════════════════════════

_ENVNAME_RX = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def _load_mcps():
    data = _read_json(mcps_path())
    if not isinstance(data.get("servers"), dict):
        data["servers"] = {}
    data.setdefault("version", 1)
    return data


def mcp_list():
    return _load_mcps().get("servers", {})


def mcp_set(name, cmd, scope="global", env=None, actor=""):
    """Alta/edición de un servidor MCP en la capa gestionada.

    Validación DURA antes de escribir:
      · name: slug [a-z0-9_-] ≤32.
      · cmd: string no vacío o lista de strings (el comando que lanza el server).
      · scope: "global" o lista de nombres de agente.
      · env: lista de NOMBRES de env-vars (MAYÚSCULAS) — un valor con pinta
        de credencial o un `NOMBRE=valor` se RECHAZA (regla de providers).
      · gate de secretos sobre la entrada completa (mismo patrón que el bus).
    Escritura atómica + lock + changelog. NO materializa al canal del motor
    (eso es del doctor — fase siguiente)."""
    name = str(name or "").strip().lower()
    if not _NAME_RX.match(name):
        return {"ok": False, "error": "nombre de MCP inválido: %r "
                                      "(slug [a-z0-9_-], ≤32)" % name}
    if isinstance(cmd, str):
        cmd = cmd.strip()
        ok_cmd = bool(cmd)
    elif isinstance(cmd, (list, tuple)):
        cmd = [str(c) for c in cmd]
        ok_cmd = bool(cmd) and all(c.strip() for c in cmd)
    else:
        ok_cmd = False
    if not ok_cmd:
        return {"ok": False, "error": "cmd debe ser string o lista de strings "
                                      "no vacíos"}
    if scope != "global":
        if not isinstance(scope, (list, tuple)) or not scope or \
                not all(isinstance(a, str) and _NAME_RX.match(a.strip().lower())
                        for a in scope):
            return {"ok": False, "error": "scope debe ser 'global' o lista de "
                                          "nombres de agente"}
        scope = sorted({a.strip().lower() for a in scope})
    env = env or []
    if not isinstance(env, (list, tuple)):
        return {"ok": False, "error": "env debe ser lista de NOMBRES de "
                                      "variables"}
    for e in env:
        s = str(e).strip()
        if "=" in s:
            return {"ok": False,
                    "error": "env lleva NOMBRES de variables, jamás valores "
                             "(%r trae '=') — Regla de Oro" % s}
        if not _ENVNAME_RX.match(s):
            return {"ok": False,
                    "error": "nombre de env-var inválido: %r (MAYÚSCULAS_CON_"
                             "GUIONES_BAJOS)" % s}
    entry = {"cmd": cmd, "scope": scope,
             "env": sorted({str(e).strip() for e in env})}
    # gate POR CAMPO (F3): un allow-secret en `cmd` no exime `env`, etc.
    findings, msg = _gate_fields(entry, "mcps.json (%s)" % name)
    if findings:
        return _blocked(msg)
    path = mcps_path()

    def _rmw():
        data = _load_mcps()
        old = data["servers"].get(name)
        data["servers"][name] = entry
        _atomic_json(path, data)
        return old
    old = _with_lock(path, _rmw)
    _log("mcp-set", "mcps.%s" % name, old, entry, "A", actor=actor)
    return {"ok": True, "name": name, "old": old, "new": entry, "tier": "A",
            "materialized": False,
            "note": "guardado en la capa gestionada; la materialización al "
                    "motor la hará doctor/install"}


def mcp_remove(name, actor=""):
    name = str(name or "").strip().lower()
    path = mcps_path()

    def _rmw():
        data = _load_mcps()
        if name not in data["servers"]:
            return None, False
        old = data["servers"].pop(name)
        _atomic_json(path, data)
        return old, True
    old, existed = _with_lock(path, _rmw)
    if not existed:
        return {"ok": False, "error": "MCP desconocido: %r" % name}
    _log("mcp-remove", "mcps.%s" % name, old, None, "A", actor=actor)
    return {"ok": True, "name": name, "old": old, "tier": "A"}


def mcp_materialize(argv, actor=""):
    """Proyecta los MCP gestionados al canal nativo del motor de cada agente.

    Fuente ÚNICA: install.render_mcps_only (DISPATCH POR TIPO DE CONEXIÓN,
    connectors.PORTABILITY). claude-code → bloque `mcpServers` de
    settings.local.json (real); codex/gemini y local/API → se SALTAN con razón
    visible (no fingen el enchufe). El store, el scope y este CLI son
    motor-agnósticos: aquí solo se dispara la proyección on-demand.

    argv: `--all` (todos los agentes resueltos) o `--agent <nombre>` (uno).
    NO lee valores de secretos — la Regla de Oro la impone el proyector
    (env = NOMBRES → ${NOMBRE})."""
    import install                                    # lazy (amputable)
    only, take_all = None, "--all" in argv
    if "--agent" in argv:
        i = argv.index("--agent")
        if i + 1 < len(argv):
            only = argv[i + 1].strip().lower()
    if not only and not take_all:
        return {"ok": False, "error": "usa --all o --agent <nombre>"}
    reg = dispatch.load_registry()
    results = []
    for entry in reg.get("agents", []):
        aname = str(entry.get("name", "")).lower()
        if only and aname != only:
            continue
        try:
            cfg = dispatch.load_agent_cfg(entry)
        except Exception:
            cfg = {}
        cfg.setdefault("name", aname)
        brain = dispatch.resolve_brain(aname, cfg)
        if not (brain and os.path.isdir(brain)):
            results.append({"agent": aname, "ok": False,
                            "reason": "cerebro no resuelto en disco"})
            continue
        channel, _ct, reason = install._mcp_projection(cfg)
        if channel != "claude-code":                 # sin proyector real → salta
            results.append({"agent": aname, "ok": True, "materialized": False,
                            "channel": channel or "?", "reason": reason})
            continue
        try:
            install.render_mcps_only(cfg, brain)     # settings None → escribe
        except Exception as e:
            results.append({"agent": aname, "ok": False, "reason": str(e)})
            continue
        desired = install._mcps_for_agent(aname)
        results.append({"agent": aname, "ok": True, "materialized": True,
                        "servers": sorted(desired), "count": len(desired)})
    if only and not results:
        return {"ok": False,
                "error": "agente desconocido o sin registrar: %s" % only}
    return {"ok": bool(results) and all(r.get("ok") for r in results),
            "results": results}


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def _print_result(res):
    print(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if res.get("ok") else 1


def _parse_kv(pairs):
    out = {}
    for p in pairs:
        if "=" not in p:
            raise ValueError("esperaba clave=valor, no %r" % p)
        k, v = p.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    actor = ""
    if "--from" in args:
        i = args.index("--from")
        if i + 1 < len(args):
            actor = args[i + 1]
            del args[i:i + 2]
    cmd = args[0] if args else "schema"
    try:
        if cmd == "schema":
            data = describe()
            if as_json:
                print(json.dumps(data, ensure_ascii=False, indent=2,
                                 sort_keys=True))
                return 0
            for row in data["settings"]:
                lock = " 🔒%s" % row["env_lock"] if row.get("env_active") else ""
                print("%-34s %-10s %s%s" % (row["key"], row["origin"],
                                            settings._fmt_val(row["value"]),
                                            lock))
            return 0
        if cmd == "stats":
            print(json.dumps(stats(), ensure_ascii=False, indent=2))
            return 0
        if cmd == "get" and len(args) >= 2:
            print(settings._fmt_val(settings.get(args[1])))
            return 0
        if cmd == "set" and len(args) >= 3:
            return _print_result(set_setting(args[1], args[2], actor=actor))
        if cmd == "reset" and len(args) >= 2:
            return _print_result(reset_setting(args[1], actor=actor))
        if cmd == "jobs":
            if len(args) >= 3 and args[1] in ("enable", "disable"):
                return _print_result(set_job(args[2], args[1] == "enable",
                                             actor=actor))
            for j in settings.jobs_status():
                print("%-22s %-4s %s" % (j["id"],
                                         "on" if j["enabled"] else "off",
                                         j["label"]))
            return 0
        if cmd == "agents":
            data = describe_agents()
            if as_json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return 0
            for a in data:
                print("%-12s tier=%s engine=%-12s %s" %
                      (a["name"], a["tier"] or "?", a["engine"],
                       a["tier_reason"]))
            return 0
        if cmd == "agent" and len(args) >= 3:
            sub = args[1]
            if sub == "get":
                for a in describe_agents():
                    if a["name"] == args[2].lower():
                        print(json.dumps(a, ensure_ascii=False, indent=2))
                        return 0
                print("agente desconocido: %s" % args[2], file=sys.stderr)
                return 1
            if sub == "set" and len(args) >= 5:
                yes = "--yes" in args
                clean = [a for a in args if a != "--yes"]
                return _print_result(set_agent_field(
                    clean[2], clean[3], clean[4], confirm=yes, actor=actor))
            if sub == "propose" and len(args) >= 5:
                return _print_result(propose_change(
                    args[2], args[3], args[4], actor=actor))
        if cmd == "mcp" and len(args) >= 2:
            sub = args[1]
            if sub == "list":
                print(json.dumps(describe_mcps(), ensure_ascii=False, indent=2))
                return 0
            if sub == "set" and len(args) >= 4:
                # mcp set <n> <cmd> [--scope a,b] [--env NAME1,NAME2]
                scope, env = "global", []
                rest = args[4:]
                i = 0
                while i < len(rest):
                    if rest[i] == "--scope" and i + 1 < len(rest):
                        scope = [s for s in rest[i + 1].split(",") if s]
                        i += 2
                    elif rest[i] == "--env" and i + 1 < len(rest):
                        env = [s for s in rest[i + 1].split(",") if s]
                        i += 2
                    else:
                        i += 1
                return _print_result(mcp_set(args[2], args[3], scope=scope,
                                             env=env, actor=actor))
            if sub == "rm" and len(args) >= 3:
                return _print_result(mcp_remove(args[2], actor=actor))
            if sub == "materialize":
                # workspace config mcp materialize [--agent <n> | --all]
                return _print_result(mcp_materialize(args[2:], actor=actor))
        if cmd == "routing":
            if len(args) >= 2 and args[1] == "set":
                return _print_result(set_task_routing(_parse_kv(args[2:]),
                                                      actor=actor))
            print(json.dumps(get_task_routing(), ensure_ascii=False, indent=2))
            return 0
        if cmd == "theme-local" and len(args) >= 3:
            pal = _parse_kv(args[2:])
            return _print_result(set_theme_local(args[1], pal or None,
                                                 actor=actor))
        if cmd == "log":
            n = int(args[1]) if len(args) >= 2 else 20
            for rec in read_log(n):
                print(json.dumps(rec, ensure_ascii=False))
            return 0
    except ValueError as e:
        print("config: %s" % e, file=sys.stderr)
        return 2
    print("uso: config_engine.py schema [--json] | stats | get <k> | "
          "set <k> <v> | reset <k> |\n"
          "     jobs [enable|disable <id>] | agents [--json] | "
          "agent get|set|propose <n> [<campo> <valor>] [--yes] |\n"
          "     mcp list|set|rm|materialize ... | routing [set tarea=modelo ...] | "
          "theme-local <agente> bg=#rrggbb ... | log [n]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
