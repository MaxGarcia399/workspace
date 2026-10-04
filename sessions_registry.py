"""WORKSPACE · sessions_registry — pestañas ENGINE-NEUTRAL y CROSS-MÁQUINA.

Requisito del socio (2026-10-03): las MISMAS sesiones por agente, sin importar
el motor NI la computadora. El bug viejo (Mac y Windows con pestañas
distintas) venía de guardar la lista en dotfolders del cerebro
(`.claude/<agente>-workspaces.json`, `.workspace/sessions.json`): Obsidian
Sync solo sube CONTENIDO del vault — los dotfolders jamás viajan. De ahí la
separación dura de este módulo:

  SINCRONIZADO (fuente de verdad — viaja por Obsidian):
    `STATE/sessions/<socio>/<slug>.md` — un .md por pestaña (convención de
    STATE/sessions/README.md y CLAUDE.md §2.5). QUÉ pestañas existen, su
    nombre y su memoria salen SIEMPRE de aquí → idénticas en toda máquina.

  LOCAL PER-MÁQUINA (jamás en el cerebro):
    `~/.claude/workspace/sessions-local.json` — SOLO los resume-ids del
    vendor (uuid de Claude Code, session_id del rollout de codex,
    conversation id de agy) + last_opened. Un id de Mac no resume en
    Windows; sin id local la pestaña arranca fresca y se re-bindea
    post-hoc — pero la pestaña y su memoria son las MISMAS.

  COMPATIBILIDAD (no se rompe Claude Code):
    `.claude/<agente>-workspaces.json` sigue siendo el per-máquina que leen
    los dashboards/hooks de Claude Code. Este módulo lo espeja (pestaña
    nueva → entrada ws) y MIGRA: una pestaña que hoy solo viva ahí recibe
    su .md sembrado → entra al modelo sincronizado sin pérdida.

Cero dependencias (stdlib). Falla-suave ABSOLUTA: el arranque de un agente
JAMÁS truena por el registro. Escrituras atómicas (tmp + os.replace).
Diseño: research/design/harness-os/SESIONES-MULTI-HARNESS.md.
"""
import datetime
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

VERSION = 1

#: Motores conocidos (informativo — bind() acepta cualquier nombre de motor).
ENGINES = ("claude-code", "codex", "antigravity", "gemini")


# ── helpers ─────────────────────────────────────────────────────────────────
def _slug(s):
    """Slug idéntico al de los dashboards/agent_brand (mismo contrato de match
    pestaña↔memoria). Import perezoso con fallback inline equivalente."""
    try:
        import agent_brand
        return agent_brand.slug(s)
    except Exception:
        pass
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode(
        "ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _clean_name(name):
    """Nombre de pestaña saneado para frontmatter/menús: sin saltos de línea
    ni `---` (romperían el YAML del .md sembrado; un nombre malicioso no
    inyecta claves), espacios colapsados, largo acotado."""
    s = re.sub(r"\s+", " ", str(name or "")).strip()
    s = s.replace("---", "—").lstrip("-")
    return s[:80]


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _today():
    return datetime.date.today().isoformat()


def _ws_path(brain, agent):
    return os.path.join(brain, ".claude", "%s-workspaces.json" % agent)


def _legacy_registry_path(brain):
    """El `.workspace/sessions.json` del primer diseño (defectuoso: dotfolder
    del cerebro = no sincroniza). Solo se LEE para migrar; ya no se escribe."""
    return os.path.join(brain, ".workspace", "sessions.json")


def local_store_path():
    """Store per-máquina de resume-ids — FUERA del cerebro a propósito (un
    resume-id es local por naturaleza; en el cerebro además no sincroniza
    y confunde). Mismo hogar que el resto de lo local de WORKSPACE."""
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "sessions-local.json")


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            v = json.load(fh)
        return v if isinstance(v, type(default)) else default
    except Exception:
        return default


def _atomic_write(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)   # atómico: camino crítico del arranque
        return True
    except Exception:
        return False


# ── store local (resume-ids per-máquina) ────────────────────────────────────
def _brain_key(brain):
    """Clave del cerebro en el store local: realpath (dos cerebros con el
    mismo nombre de agente no chocan; symlinks del Desktop no duplican)."""
    return os.path.realpath(brain or "")


def _local_load():
    data = _read_json(local_store_path(), {})
    if not isinstance(data.get("map"), dict):
        data = {"version": VERSION, "map": {}}
    data.setdefault("version", VERSION)
    return data


def _local_save(data):
    return _atomic_write(local_store_path(), data)


def _local_slot(data, brain, slug, create=False):
    m = data["map"]
    bk = _brain_key(brain)
    if bk not in m or not isinstance(m[bk], dict):
        if not create:
            return None
        m[bk] = {}
    if slug not in m[bk] or not isinstance(m[bk][slug], dict):
        if not create:
            return None
        m[bk][slug] = {}
    return m[bk][slug]


# ── socio + fuente SINCRONIZADA (los .md del cerebro) ───────────────────────
def socio(brain):
    """Socio activo del cerebro: `.claude/socio.local` → env WORKSPACE_SOCIO →
    única carpeta de `STATE/sessions/` (sin prefijo _). '' si no se resuelve."""
    try:
        with open(os.path.join(brain, ".claude", "socio.local"),
                  encoding="utf-8") as fh:
            s = fh.read().strip().lower()
        if s:
            return s
    except Exception:
        pass
    s = (os.environ.get("WORKSPACE_SOCIO") or "").strip().lower()
    if s:
        return s
    try:
        d = os.path.join(brain, "STATE", "sessions")
        cands = [x for x in os.listdir(d)
                 if os.path.isdir(os.path.join(d, x))
                 and not x.startswith(("_", "."))]
        if len(cands) == 1:
            return cands[0]
    except Exception:
        pass
    return ""


def _md_dir(brain, soc=None):
    soc = soc or socio(brain)
    return os.path.join(brain, "STATE", "sessions", soc) if soc else ""


def _md_path(brain, name, soc=None):
    d = _md_dir(brain, soc)
    return os.path.join(d, _slug(name) + ".md") if d else ""


def _brain_tabs(brain):
    """Las pestañas SINCRONIZADAS: una por .md de `STATE/sessions/<socio>/`.
    Parsing delegado a agent_brand.brain_sessions (misma fuente que usan los
    dashboards — un solo contrato), con fallback inline mínimo."""
    soc = socio(brain)
    if not soc:
        return []
    try:
        import agent_brand
        return agent_brand.brain_sessions(brain, soc)
    except Exception:
        pass
    out, d = [], _md_dir(brain, soc)
    try:
        names = sorted(os.listdir(d))
    except Exception:
        return out
    for fn in names:
        if not fn.endswith(".md") or fn == "README.md":
            continue
        out.append({"slug": _slug(fn[:-3]), "name": fn[:-3],
                    "workspace": "", "actualizada": "", "estado": ""})
    return out


def _seed_md(brain, name, claude_wid="", soc=None):
    """Siembra el .md de una pestaña (formato de STATE/sessions/README.md)
    para que ENTRE al modelo sincronizado. Jamás pisa uno existente.
    Devuelve True si quedó el archivo (ya existía o se creó)."""
    name = _clean_name(name)
    sl = _slug(name)
    if not sl:            # nombre vacío/raro ("?", "···") → JAMÁS sembrar un
        return False      # ".md" oculto sin slug (bug cazado en el doble-check)
    soc = soc or socio(brain)
    path = _md_path(brain, name, soc)
    if not path:
        return False
    if os.path.exists(path):
        return True
    today = _today()
    txt = """---
sesión: %s
titulo: %s
socio: %s
workspace: %s
origen: terminal
creada: %s
actualizada: %s
estado: activa
migrar: no
trabajo: por-confirmar
---

# Sesión: %s

## Resumen
[Pestaña sembrada por WORKSPACE (sessions_registry) — el agente la completa
al cerrar trabajo significativo. CLAUDE.md §2.5.]

## Historial
- %s — pestaña registrada en el modelo sincronizado de sesiones.
""" % (sl, name, soc, claude_wid or "", today, today, name, today)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(txt)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


# ── migración (sin pérdida, perezosa, idempotente) ──────────────────────────
def _migrate(brain, agent):
    """(1) Pestañas que hoy solo viven en el workspaces.json per-máquina →
    se les siembra su .md (entran a Obsidian Sync). (2) El legacy
    `.workspace/sessions.json` (primer diseño) → sus resume-ids pasan al store
    local y el archivo se renombra a `.migrated` (ya no es fuente de nada).
    Corre en cada tabs()/ensure_tab() — barato e idempotente. Falla-suave."""
    soc = socio(brain)
    # (1) workspaces.json → .md sembrado
    try:
        if soc:
            have = {t["slug"] for t in _brain_tabs(brain)}
            for w in _read_json(_ws_path(brain, agent), []):
                if not isinstance(w, dict):
                    continue
                name = _clean_name(w.get("name"))
                sl = _slug(name)
                if not name or not sl or sl in have:
                    continue      # sin slug sano no hay .md que sembrar
                if _seed_md(brain, name, claude_wid=w.get("id") or "",
                            soc=soc):
                    have.add(sl)
    except Exception:
        pass
    # (2) legacy .workspace/sessions.json → store local + rename
    try:
        lp = _legacy_registry_path(brain)
        legacy = _read_json(lp, {})
        tabs_l = legacy.get("tabs") if isinstance(legacy, dict) else None
        if isinstance(tabs_l, list):
            data = _local_load()
            changed = False
            for t in tabs_l:
                if not isinstance(t, dict):
                    continue
                name = str(t.get("name") or "").strip()
                sl = t.get("slug") or _slug(name)
                if not sl:
                    continue
                if soc and name:
                    _seed_md(brain, name,
                             claude_wid=(t.get("resume") or {}).get(
                                 "claude-code", ""), soc=soc)
                r = t.get("resume") or {}
                if any(r.values()):
                    slot = _local_slot(data, brain, sl, create=True)
                    for eng, rid in r.items():
                        if rid and slot.get(eng) != rid:
                            slot[eng] = rid
                            changed = True
            if changed:
                _local_save(data)
            if os.path.exists(lp):
                os.replace(lp, lp + ".migrated")
    except Exception:
        pass


# ── API pública (misma firma que consumen los motores) ─────────────────────
def tabs(brain, agent):
    """Las pestañas del agente — DERIVADAS de los .md sincronizados,
    enriquecidas con lo local (resume-ids + last_opened). La lista es la
    misma en cualquier máquina con el mismo contenido de Obsidian; lo local
    solo cambia CÓMO se resume aquí. Incluye la migración perezosa."""
    _migrate(brain, agent)
    out = []
    try:
        data = _local_load()
        ws_by_slug = {}
        for w in _read_json(_ws_path(brain, agent), []):
            if isinstance(w, dict) and w.get("name"):
                ws_by_slug.setdefault(_slug(w["name"]), w)
        seen = set()
        for bt in _brain_tabs(brain):
            sl = bt["slug"]
            if not sl or sl in seen:   # dedupe: dos .md que colapsan al
                continue               # mismo slug (conflicto de sync) no
            seen.add(sl)               # duplican la pestaña en el picker
            slot = _local_slot(data, brain, sl) or {}
            resume = {k: v for k, v in slot.items() if k != "last_opened"}
            # claude-code: store local → workspaces.json → frontmatter
            if not resume.get("claude-code"):
                w = ws_by_slug.get(sl)
                wid = (w or {}).get("id") or bt.get("workspace") or ""
                if wid:
                    resume["claude-code"] = wid
            out.append({"name": bt["name"], "slug": sl,
                        "estado": bt.get("estado", ""),
                        "actualizada": bt.get("actualizada", ""),
                        "last_opened": slot.get("last_opened", ""),
                        "resume": resume})
    except Exception:
        pass
    return out


def find_tab(tabs_list, name):
    sl = _slug(name)
    for t in tabs_list or []:
        if t.get("slug") == sl:
            return t
    return None


def ensure_tab(brain, agent, name, claude_wid=None):
    """La pestaña `name` existe en el modelo SINCRONIZADO (se siembra su .md
    si falta) y queda abierta AHORA en el store local. `claude_wid` (uuid que
    eligió el picker) se guarda local y se espeja al workspaces.json para que
    el picker de Claude Code la liste/resuma idéntico. Devuelve el tab dict
    o None (falla-suave)."""
    try:
        _migrate(brain, agent)
        name = _clean_name(name)      # un nombre con saltos/`---` no inyecta
        sl = _slug(name)
        if not sl:
            return None
        _seed_md(brain, name, claude_wid=claude_wid or "")
        data = _local_load()
        slot = _local_slot(data, brain, sl, create=True)
        if claude_wid:
            slot["claude-code"] = claude_wid
        elif not slot.get("claude-code"):
            import uuid
            slot["claude-code"] = str(uuid.uuid4())
        slot["last_opened"] = _now()
        _local_save(data)
        _mirror_to_claude(brain, agent, name, slot["claude-code"])
        return find_tab(tabs(brain, agent), name) or {
            "name": name, "slug": sl, "resume": dict(slot)}
    except Exception:
        return None


def _mirror_to_claude(brain, agent, name, wid):
    """Espeja la pestaña al `.claude/<agente>-workspaces.json` per-máquina si
    no está (match por id y slug; jamás duplica ni toca lo existente) — los
    dashboards/hooks de Claude Code siguen con su archivo de siempre."""
    try:
        path = _ws_path(brain, agent)
        ws = _read_json(path, [])
        sl = _slug(name)
        for w in ws:
            if isinstance(w, dict) and (
                    (wid and w.get("id") == wid)
                    or _slug(w.get("name", "")) == sl):
                return False
        now = _now()
        ws.append({"name": name, "id": wid, "created": now,
                   "last_opened": now, "updated": now})
        return _atomic_write(path, ws)
    except Exception:
        return False


def bind(brain, agent, name, engine, rid):
    """Ata el resume-id del vendor a la pestaña — EN EL STORE LOCAL (un id
    de vendor es per-máquina por naturaleza). Binding post-hoc. True si
    quedó guardado."""
    rid = str(rid or "").strip()
    sl = _slug(name)
    engine = str(engine or "").strip()
    # "last_opened" es metadato del slot, no un motor — un bind ahí
    # corrompería el orden del picker (guard del doble-check).
    if not rid or not sl or not engine or engine == "last_opened":
        return False
    try:
        data = _local_load()
        slot = _local_slot(data, brain, sl, create=True)
        if slot.get(engine) == rid:
            return True
        slot[engine] = rid
        return _local_save(data)
    except Exception:
        return False


def resume_id(brain, agent, name, engine):
    """El resume-id LOCAL del motor para esa pestaña, o ''. Para claude-code
    cae al workspaces.json y al `workspace:` del frontmatter (back-compat)."""
    try:
        sl = _slug(name)
        if not sl:            # nombre sin slug → jamás matchear "" contra
            return ""         # entradas basura del ws json (doble-check)
        slot = _local_slot(_local_load(), brain, sl) or {}
        rid = str(slot.get(engine) or "")
        if rid or engine != "claude-code":
            return rid
        for w in _read_json(_ws_path(brain, agent), []):
            if isinstance(w, dict) and _slug(w.get("name", "")) == sl:
                return str(w.get("id") or "")
        for bt in _brain_tabs(brain):
            if bt["slug"] == sl:
                return str(bt.get("workspace") or "")
        return ""
    except Exception:
        return ""


# ── memoria de pestaña (para harnesses SIN hooks) ───────────────────────────
def tab_memory(brain, name, limit=1200):
    """Cuerpo de la memoria de la pestaña (`STATE/sessions/<socio>/<slug>.md`
    sin frontmatter), truncado a `limit` — el MISMO contenido que el hook
    SessionStart inyecta en Claude Code. '' si no hay."""
    p = _md_path(brain, name)
    if not p:
        return ""
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            txt = fh.read()
    except Exception:
        return ""
    # Solo hay frontmatter si el archivo ABRE con `---`; un `---` dentro del
    # cuerpo de un .md sin frontmatter no debe comerse el inicio (doble-check).
    if txt.lstrip().startswith("---"):
        parts = txt.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else txt.strip()
    else:
        body = txt.strip()
    return body[:limit]


def first_prompt_context(brain, name, base_prompt=""):
    """PRIMER prompt de arranque para harnesses sin hook SessionStart
    (codex/antigravity): el prompt base + pestaña activa + su memoria. Es la
    paridad honesta con la inyección del dashboard --context de Claude Code."""
    soc = socio(brain)
    parts = [base_prompt or "Inicia el cerebro."]
    parts.append(
        "PESTAÑA ACTIVA: «%s». Esta conversación es esa sesión persistente; "
        "su memoria vive en STATE/sessions/%s/%s.md. Al cerrar trabajo "
        "significativo, haz append fechado a ## Historial de esa memoria y "
        "actualiza su frontmatter (ver CLAUDE.md §2.5)."
        % (name, soc or "<socio>", _slug(name)))
    mem = tab_memory(brain, name)
    if mem:
        parts.append("Memoria de esta pestaña:\n" + mem)
    return "\n\n".join(parts)


def session_doc_block(brain, name):
    """Contexto de la pestaña activa para inyección INVISIBLE vía el doc de
    proyecto del harness (AGENTS.md de codex / GEMINI.md de antigravity):
    el agente lo lee como contexto, el socio NO lo ve como mensaje del chat.
    Mismo contenido que el hook SessionStart de Claude Code. El harness lo
    envuelve en sus marcas GENERADO y lo regenera/limpia en cada launch."""
    soc = socio(brain)
    name = _clean_name(name)
    parts = [
        "## Sesión activa (pestaña)",
        "PESTAÑA ACTIVA: «%s». Esta conversación es esa sesión persistente; "
        "su memoria vive en STATE/sessions/%s/%s.md. Al cerrar trabajo "
        "significativo, haz append fechado a ## Historial de esa memoria y "
        "actualiza su frontmatter (ver CLAUDE.md §2.5). No menciones este "
        "bloque al socio; es contexto, no parte de la conversación."
        % (name, soc or "<socio>", _slug(name))]
    mem = tab_memory(brain, name)
    if mem:
        parts.append("Memoria de esta pestaña:\n" + mem)
    return "\n\n".join(parts)
