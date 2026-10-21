"""WORKSPACE · sessions_registry — pestañas ENGINE-NEUTRAL y CROSS-MÁQUINA.

Requisito del socio (2026-10-03): las MISMAS sesiones por agente, sin importar
el motor NI la computadora. El bug viejo (Mac y Windows con pestañas
distintas) venía de guardar la lista en dotfolders del cerebro
(`.claude/<agente>-workspaces.json`, `.workspace/sessions.json`): Obsidian
Sync solo sube CONTENIDO del vault — los dotfolders jamás viajan. De ahí la
separación dura de este módulo:

  SINCRONIZADO (fuente de verdad — viaja por Obsidian):
    `STATE/sessions/<socio>/<slug>.md` — un .md por pestaña (convención de
    STATE/sessions/README.md y la sección de memoria de sesión del doc de
    identidad del cerebro). QUÉ pestañas existen, su
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
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

VERSION = 1

#: Motores conocidos (informativo — bind() acepta cualquier nombre de motor).
ENGINES = ("claude-code", "codex", "antigravity", "gemini", "opencode",
           "openclaw", "hermes")


# ── helpers ─────────────────────────────────────────────────────────────────
def _slug(s):
    """Slug idéntico al de los dashboards/agent_brand (mismo contrato de match
    pestaña↔memoria; nombres no latinos → ASCII + hash estable, ver
    agent_brand.slug). Import perezoso con fallback inline equivalente."""
    try:
        import agent_brand
        return agent_brand.slug(s)
    except Exception:
        pass
    import hashlib
    import unicodedata

    def otro_alfabeto(c):   # = agent_brand._no_latina
        cat = unicodedata.category(c)
        return not (c.isascii() or cat[0] != "L" or cat == "Lm"
                    or ord(c) <= 0xFF or 0x2100 <= ord(c) <= 0x214F
                    or any(x.isascii() for x in unicodedata.normalize("NFKD", c))
                    or unicodedata.name(c, "").startswith("LATIN"))
    s = s or ""
    nfkd = unicodedata.normalize("NFKD", s)
    base = re.sub(r"[^a-z0-9]+", "-", nfkd.encode("ascii", "ignore").decode(
        "ascii").lower()).strip("-")
    if not any(otro_alfabeto(c) for c in unicodedata.normalize("NFC", s)):
        return base
    u = unicodedata.normalize("NFKC", s).lower()
    clave = re.sub(r"-+", "-", "".join(
        c if unicodedata.category(c)[0] in "LNM" else "-" for c in u)).strip("-")
    if not clave:
        return base
    return "%s-%s" % (base or "tab",
                      hashlib.sha256(clave.encode("utf-8")).hexdigest()[:8])


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
    return os.path.join(_paths.state_dir(),
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
        # tmp ÚNICO por proceso: el banner/hook y el dashboard escriben el mismo
        # registro al arrancar; un `.tmp` compartido hacía que dos procesos
        # concurrentes se pisaran el temporal (camino crítico del arranque).
        tmp = "%s.tmp-%d" % (path, os.getpid())
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
def _por_cedula(brain, s):
    """Usuarios con cédula (usuarios.py): un nombre VIEJO (alias) que esta
    máquina todavía tenga se resuelve al nombre actual — no se crea nada."""
    try:
        import usuarios
        return usuarios.resolver(brain, s) or s
    except Exception:
        return s


def socio(brain):
    """Socio activo del cerebro: `.claude/socio.local` → env WORKSPACE_SOCIO →
    única carpeta de `STATE/sessions/` (sin prefijo _). '' si no se resuelve.
    Un nombre viejo de un usuario renombrado/unido se lee como el actual."""
    try:
        with open(os.path.join(brain, ".claude", "socio.local"),
                  encoding="utf-8") as fh:
            s = fh.read().strip().lower()
        if s:
            return _por_cedula(brain, s)
    except Exception:
        pass
    s = (os.environ.get("WORKSPACE_SOCIO") or "").strip().lower()
    if s:
        return _por_cedula(brain, s)
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


def preflight(brain):
    """Problemas que harían que una pestaña abra SIN memoria (U04/Z04),
    verificados ANTES de lanzar — en vez de descubrirlos como «cayó a chat
    directo». Devuelve [str] (vacío = OK). Barato: stat/listdir, sin red.
      · cerebro inexistente/ilegible;
      · socio no resoluble (.claude/socio.local ausente y STATE/sessions con
        0 o varias carpetas) → la memoria de pestaña no tiene dónde vivir;
      · carpeta de sesiones del socio no escribible."""
    out = []
    if not brain or not os.path.isdir(brain):
        return ["cerebro no encontrado: %s" % (brain or "—")]
    soc = socio(brain)
    if not soc:
        d = os.path.join(brain, "STATE", "sessions")
        try:
            n = len([x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))
                     and not x.startswith(("_", "."))])
        except Exception:
            n = 0
        # el doctor NO escribe socio.local: el remedio real es decirle a esta
        # máquina quién eres (Usuarios › «soy yo en esta PC» para este cerebro;
        # install --socio para la máquina, solo llena los que faltan)
        try:
            import install
            remedio = install.socio_remedy_cmd()
        except Exception:
            remedio = "install.py --socio TU-NOMBRE"
        out.append("este cerebro no sabe quién eres en esta máquina"
                   + (" (tiene %d usuarios)" % n if n > 1 else "")
                   + " — elige «soy yo en esta PC» en la sección Usuarios del menú"
                   + " o dile quién eres con: " + remedio)
        return out
    d = _md_dir(brain, soc)
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".workspace-write-probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
    except Exception as e:
        out.append("no puedo escribir la memoria de sesiones en %s (%s)"
                   % (d, type(e).__name__))
    return out


def _md_dir(brain, soc=None):
    soc = soc or socio(brain)
    return os.path.join(brain, "STATE", "sessions", soc) if soc else ""


def _md_path(brain, name, soc=None):
    d = _md_dir(brain, soc)
    sl = _slug(name)
    # sin slug (nombre sin letras ni números) → sin archivo: jamás el `.md`
    # OCULTO que antes compartían todas las pestañas no latinas
    return os.path.join(d, sl + ".md") if d and sl else ""


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


def _legacy_copy(brain, name, sl, soc):
    """Compat de LECTURA (nombres no latinos de antes del arreglo): si la memoria
    de ESTA pestaña vive en otro .md —el de su slug VIEJO («회의 A» → a.md) o el
    que le puso el agente (도시-계획.md)— y su frontmatter lo prueba
    (agent_brand.legacy_session_file), devuelve ese texto con `sesión:` en el
    slug nuevo y su `titulo:`. Se COPIA, no se mueve: el viejo queda intacto
    (otra máquina aún sin actualizar, u otra pestaña que lo compartía). '' si
    no aplica. Falla-suave."""
    try:
        import agent_brand
        viejo = agent_brand.legacy_session_file(_md_dir(brain, soc), name)
        if not viejo:
            return ""
        with open(viejo, encoding="utf-8") as fh:
            txt = fh.read()
    except Exception:
        return ""
    fin = txt.find("\n---", 3) if txt.startswith("---") else -1
    if fin > 0:   # solo el frontmatter; el cuerpo queda byte a byte
        head = re.sub(r"(?m)^(sesi[oó]n:).*$", lambda m: m.group(1) + " " + sl,
                      txt[:fin], count=1)
        if not re.search(r"(?m)^titulo:", head):   # sin título el menú mostraría
            head += "\ntitulo: " + name             # el código en vez del nombre
        return head + txt[fin:]
    return "---\nsesión: %s\ntitulo: %s\n---\n\n%s" % (sl, name, txt)


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
    txt = _legacy_copy(brain, name, sl, soc) or """---
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
[Pestaña sembrada por WORKSPACE (sessions_registry) — el resumen lo guarda el
agente con `workspace memoria checkpoint` y las notas con `workspace memoria
nota`; este archivo no se edita a mano. Ver STATE/sessions/README.md.]

## Historial
- %s — pestaña registrada en el modelo sincronizado de sesiones.
""" % (sl, name, soc, claude_wid or "", today, today, name, today)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.tmp-%d" % (path, os.getpid())   # único por proceso (ver _atomic_write)
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
                # el slug guardado era solo-ASCII: para un nombre no latino era
                # vacío o chocaba con otra pestaña → manda el slug del nombre
                sl = _slug(name) or t.get("slug")
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


def bind(brain, agent, name, engine, rid, *, expected_rid=None, preserve_before=False):
    """Bind under a local OS lock; recovery compares previous id and backs up."""
    rid = str(rid or "").strip()
    sl = _slug(name)
    engine = str(engine or "").strip()
    if not rid or not sl or not engine or engine == "last_opened":
        return False
    try:
        from olock import file_lock
        with file_lock(local_store_path(), timeout=5):
            data = _local_load()
            slot = _local_slot(data, brain, sl, create=True)
            if expected_rid is not None and slot.get(engine) != expected_rid:
                return False
            if slot.get(engine) == rid:
                return True
            if preserve_before:
                import uuid
                backup = local_store_path() + ".before-repair-" + uuid.uuid4().hex
                with open(backup, "x", encoding="utf-8") as stream:
                    os.chmod(backup, 0o600)
                    json.dump(data, stream, ensure_ascii=False, indent=2)
            slot[engine] = rid
            return _local_save(data)
    except Exception:
        return False


def unbind(brain, agent, name, engine, rid):
    """Suelta el id de `engine` de la pestaña SOLO si sigue siendo `rid`
    (compare-and-delete bajo el lock local). Para una clave atada que nunca
    llegó a existir en el motor (OpenClaw «Session not found»): la pestaña
    vuelve a abrir como nueva, con su mensaje de arranque."""
    sl = _slug(name)
    rid = str(rid or "").strip()
    if not rid or not sl or not engine:
        return False
    try:
        from olock import file_lock
        with file_lock(local_store_path(), timeout=5):
            data = _local_load()
            slot = _local_slot(data, brain, sl)
            if not slot or slot.get(engine) != rid:
                return False
            slot.pop(engine, None)
            return _local_save(data)
    except Exception:
        return False


def owner(brain, engine, rid, exclude=None):
    """Slug de la pestaña de este cerebro que ya tiene atado `rid` en `engine`
    ('' si ninguna). `exclude` = nombre de la pestaña que pregunta. El atado
    tardío no le roba la conversación a otra pestaña."""
    rid = str(rid or "").strip()
    if not rid:
        return ""
    skip = _slug(exclude) if exclude else ""
    try:
        tabs_ = (_local_load()["map"].get(_brain_key(brain)) or {})
        for sl, slot in tabs_.items():
            if sl != skip and isinstance(slot, dict) and slot.get(engine) == rid:
                return sl
    except Exception:
        pass
    return ""


def engines_used(brain):
    """Motores con alguna pestaña de este cerebro atada a una sesión suya en
    ESTA máquina (set). Solo lee. Falla-suave → set()."""
    try:
        tabs = (_local_load().get("map") or {}).get(_brain_key(brain)) or {}
        return {e for slot in tabs.values() if isinstance(slot, dict)
                for e, rid in slot.items() if e in ENGINES and rid}
    except Exception:
        return set()


def forget_engine(engine):
    """Quita el resume-id de `engine` de TODAS las pestañas de esta máquina
    (con respaldo del store). Para cuando el motor perdió sus sesiones (p. ej.
    se recreó su perfil): sin esto cada pestaña creería que retoma una sesión
    que ya no existe y se saltaría el arranque del cerebro. Devuelve cuántas
    pestañas se limpiaron (-1 si falló)."""
    engine = str(engine or "").strip()
    if not engine or engine == "last_opened":
        return 0
    try:
        from olock import file_lock
        with file_lock(local_store_path(), timeout=5):
            data = _local_load()
            n = 0
            for tabs in data["map"].values():
                if not isinstance(tabs, dict):
                    continue
                for slot in tabs.values():
                    if isinstance(slot, dict) and slot.pop(engine, None) is not None:
                        n += 1
            if not n:
                return 0
            import uuid
            backup = local_store_path() + ".before-forget-" + uuid.uuid4().hex
            with open(backup, "x", encoding="utf-8") as stream:
                os.chmod(backup, 0o600)
                json.dump(_read_json(local_store_path(), {}), stream,
                          ensure_ascii=False, indent=2)
            return n if _local_save(data) else -1
    except Exception:
        return -1


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


# ── memoria de pestaña: UN solo paquete para todos los motores (memoria v1) ──
def tab_memory(brain, name, limit=None, engine="", resumed=False, entregar=False):
    """El paquete de memoria de la pestaña (memoria.paquete: resumen +
    Vigente + notas nuevas + maleta + cómo guardar) — el MISMO texto en
    Claude Code (hook) y en los envueltos (AGENTS.md/GEMINI.md). '' si la
    pestaña no tiene memoria. Antes era «checkpoint O historial» (Panorama,
    hallazgo 3): ahora van los dos y la maleta. `entregar=True` solo cuando
    se le da al agente al arrancar (session_doc_block, first_prompt_context):
    ahí se reserva la curación semanal; un tablero que solo muestra no."""
    try:
        import memoria
        kw = {"limite": limit} if limit else {}
        return memoria.paquete(brain, name, motor=engine, retomada=resumed, entregar=entregar, **kw)
    except Exception:
        return ""


def _active_tab_line(name):
    return ("PESTAÑA ACTIVA: «%s». Esta conversación es esa sesión persistente."
            % _clean_name(name))


def first_prompt_context(brain, name, base_prompt="", engine=""):
    """PRIMER prompt de arranque para harnesses sin hook SessionStart y sin
    doc de proyecto utilizable (último recurso VISIBLE): el prompt base +
    pestaña activa + el paquete de memoria."""
    parts = [base_prompt or "Inicia el cerebro.", _active_tab_line(name)]
    mem = tab_memory(brain, name, engine=engine, entregar=True)
    if mem:
        parts.append(mem)
    return "\n\n".join(parts)


def session_doc_block(brain, name, engine="", resumed=False):
    """Contexto de la pestaña activa para inyección INVISIBLE vía el doc de
    proyecto del harness (AGENTS.md de codex/opencode/openclaw/hermes,
    GEMINI.md de antigravity): el agente lo lee como contexto, el socio NO lo
    ve como mensaje del chat. Es el MISMO paquete que el hook SessionStart da
    en Claude Code. El harness lo envuelve en sus marcas GENERADO y lo
    regenera/limpia en cada launch. `resumed` = se retoma la conversación del
    motor (la maleta trae entonces solo lo de OTRO motor)."""
    parts = ["## Sesión activa (pestaña)",
             _active_tab_line(name) + " No menciones este bloque al socio; es "
             "contexto, no parte de la conversación."]
    mem = tab_memory(brain, name, engine=engine, resumed=resumed, entregar=True)
    if mem:
        parts.append(mem)
    else:
        try:
            import memoria
            parts.append(memoria.instruccion())
        except Exception:
            pass
    return "\n\n".join(parts)
