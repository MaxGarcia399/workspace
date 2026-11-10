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
    nueva → entrada ws). Sesiones v2 (2026-11-05): ya NO es fuente de
    pestañas ni siembra `.md` (las pruebas de una sola máquina revivían en
    las demás). Sus ids y last_opened pasan al store local
    (absorber_json_local) y lo que no tiene `.md` queda anotado como
    `huerfanas` en el store, recuperable con `desarchivar`.

  ARCHIVAR (sesiones v2): `estado: archivada` + `archivada: <fecha>` en el
    frontmatter del `.md` — viaja, así que sale del menú en todas las
    máquinas; el archivo no se mueve ni se borra. archivar/desarchivar/
    archivadas/desarchivar_ultimas, auto_archivar (ajuste
    sesiones.archivar_dias) y tabs(…, archivadas=False).

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
           "openclaw", "hermes", "kiro", "copilot", "cursor")


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
        # tmp ÚNICO (el banner/hook y el dashboard escriben el mismo registro
        # al arrancar) + reintento en Windows; si falla, sin `.tmp` y con aviso
        import atomico
        atomico.escribir(path, json.dumps(data, indent=2, ensure_ascii=False), avisar=True)
        return True
    except Exception:
        return False


def _apartar_ilegible(path):
    """Un workspaces.json ilegible se aparta —no se pisa ni se borra— con un
    aviso de una línea. → la ruta nueva, o '' si no se pudo."""
    import uuid
    dest = "%s.ilegible-%s-%s" % (path, datetime.datetime.now().strftime("%y%m%dT%H%M%S"),
                                  uuid.uuid4().hex[:6])
    try:
        os.replace(path, dest)
    except OSError:
        return ""
    try:
        sys.stderr.write("⚠ Workspace: no pude leer %s; quedó aparte en %s (no se borró)\n"
                         % (path, dest))
    except Exception:
        pass
    return dest


def actualizar_ws(path, cambiar, timeout=5):
    """EL camino para escribir `.claude/<agente>-workspaces.json`: leer,
    cambiar y guardar bajo UN candado común (olock.local_lock: el `.lock` en
    `<cerebro>/.claude/locks/`, que no viaja por Obsidian), con temporal
    único + os.replace. TODOS sus escritores pasan por aquí: el espejo de un
    fork (_espejar_id), la pestaña nueva (_mirror_to_claude), el panel
    (_register_workspace, _stamp_opened), el hook de cierre y el menú de
    pestañas de los dashboards. Sin esto, un fork que espejaba su id pisaba
    la pestaña que otra ventana acababa de crear (Greptile 0.8.x, 8).
    `cambiar(ws)` recibe la lista actual ([] si no hay) y devuelve la nueva,
    o None para no escribir. JAMÁS escribe fuera del candado: si sigue
    ocupado tras `timeout`, reintenta UNA vez y, si no, devuelve False (el
    que lo tiene puede tardar —en Windows, los reintentos de os.replace— y
    escribir sin él borraba la pestaña que ese otro acababa de agregar:
    Greptile final 0.9.0, 1). → True si escribió. Falla-suave."""
    try:
        from olock import local_lock, LockTimeout
    except Exception:
        return False                       # sin candado, no se escribe
    lk = None
    for _intento in range(2):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            lk = local_lock(path, timeout=timeout)
            lk.__enter__()
            break
        except LockTimeout:
            lk = None
            continue
        except Exception:
            return False
    if lk is None:
        return False
    try:
        import atomico
        try:
            # una lectura que falla (el antivirus, un instante) se reintenta
            # como el reemplazo; si sigue, no se escribe nada (revisor final)
            ws = json.loads(atomico.leer(path, "utf-8-sig"))
            if not isinstance(ws, list):
                raise ValueError("no es una lista")
        except FileNotFoundError:
            ws = []
        except ValueError:
            # ilegible NO es vacío —JSON roto, UTF-8 malo, otra forma—: se
            # aparta intacto y se avisa antes de guardar; si no se puede
            # apartar, no se escribe (Greptile final, 3)
            if not _apartar_ilegible(path):
                return False
            ws = []
        except OSError:
            return False
        nuevo = cambiar(ws)
        return False if nuevo is None else _atomic_write(path, nuevo)
    except Exception:
        return False
    finally:
        lk.__exit__(None, None, None)


# ── store local (resume-ids per-máquina) ────────────────────────────────────
def _brain_key(brain):
    """Clave del cerebro en el store local: realpath (dos cerebros con el
    mismo nombre de agente no chocan; symlinks del Desktop no duplican)."""
    return os.path.realpath(brain or "")


def _local_load(path=None):
    data = _read_json(path or local_store_path(), {})
    if not isinstance(data.get("map"), dict):
        data = {"version": VERSION, "map": {}}
    data.setdefault("version", VERSION)
    return data


def _local_save(data, path=None):
    return _atomic_write(path or local_store_path(), data)


def _con_store(fn, path=None):
    """Corre `fn()` —un leer-modificar-escribir del store local— con su
    candado: el menú, el motor y los hooks arrancan a la vez y, sin él, uno
    pisaba los `lotes` o los ids del otro (en Windows se vio). Sin olock, o
    con el candado ocupado más de 5 s, corre igual: mejor escribir que
    perder el cambio."""
    try:
        from olock import file_lock, LockTimeout
    except Exception:
        return fn()
    try:
        lk = file_lock(path or local_store_path(), timeout=5)
        lk.__enter__()
    except LockTimeout:
        return fn()
    try:
        return fn()
    finally:
        lk.__exit__(None, None, None)


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
    """Socio activo del cerebro. Quién eres es de la MÁQUINA (sesiones v2,
    identidad.py → `<state_dir>/identidad.json`): el «soy yo en esta PC» de
    este cerebro → tu persona resuelta contra SUS cédulas (nombre, luego
    alias) → la carpeta con tu nombre (se crea al escribir). Solo si esta
    máquina no sabe quién eres, el orden de antes (_socio_legado). '' si no
    se resuelve. Un nombre viejo de un usuario renombrado/unido se lee como el
    actual."""
    try:
        import identidad
        s = identidad.socio(brain)
        if s:
            return s
    except Exception:
        pass
    return _socio_legado(brain)


def _socio_legado(brain):
    """El orden de antes (máquina sin identidad): `.claude/socio.local` → env
    WORKSPACE_SOCIO → única carpeta de `STATE/sessions/` (sin prefijo _),
    salvo que esa carpeta ya sea de alguien con cédula: sin saber quién eres,
    tomar la carpeta de otra persona te mostraba sus pestañas y guardaba las
    tuyas en ella (sesiones v2, F1). Ahí no se adivina: el preflight te dice
    cómo elegir (una vez)."""
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
        if len(cands) == 1 and not _de_alguien(brain, cands[0]):
            return cands[0]
    except Exception:
        pass
    return ""


def _de_alguien(brain, carpeta):
    try:
        import identidad
        return identidad.es_de_alguien(brain, carpeta)
    except Exception:
        return False


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
    # La carpeta del socio se crea al ESCRIBIR una pestaña (ensure_tab), no
    # aquí: con la identidad por máquina, abrir el cerebro de otra persona no
    # debe dejarle una carpeta (ni un perfil) tuyos vacíos. Se prueba en la
    # carpeta más cercana que ya exista dentro del cerebro.
    sonda, base = d, os.path.abspath(brain)
    while not os.path.isdir(sonda) and os.path.abspath(sonda) != base:
        sonda = os.path.dirname(sonda)
    try:
        probe = os.path.join(sonda, ".workspace-write-probe")
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
                    "workspace": "", "actualizada": "", "estado": "",
                    "archivada": "", "archivo": os.path.join(d, fn)})
    return out


def _pestanas(brain, archivadas=False):
    """La lista del NÚCLEO común (agent_brand.pestanas: los `.md`, una por
    slug, sin las archivadas por default) — la misma que ven los dashboards
    y el panel. Fallback inline (sin agent_brand): _brain_tabs deduplicado."""
    soc = socio(brain)
    if not soc:
        return []
    try:
        import agent_brand
        return agent_brand.pestanas(brain, soc, archivadas)
    except Exception:
        pass
    out, seen = [], set()
    for bt in _brain_tabs(brain):
        arch = str(bt.get("estado") or "").strip().lower() == "archivada"
        if bt["slug"] in seen or (archivadas == "solo" and not arch) \
                or (not archivadas and arch):
            continue
        seen.add(bt["slug"])
        out.append(bt)
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
        import atomico                    # tmp único + reintento (ver _atomic_write)
        atomico.escribir(path, txt, avisar=True)
        return True
    except Exception:
        return False


# ── migración (sin pérdida, perezosa, idempotente) ──────────────────────────
def absorber_json_local(brain, agent, store=None):
    """Sesiones v2 (expandir→contraer): lo útil del `.claude/<agente>-
    workspaces.json` per-máquina pasa al store local — el id de Claude Code y
    el last_opened de cada pestaña que SÍ tiene `.md` — y las entradas SIN
    `.md` quedan anotadas en `huerfanas` del store, SIN sembrarse (eran de
    una sola máquina: las pruebas de la PC revivían en la Mac). `desarchivar
    <nombre>` recupera una huérfana. El json no se toca: lo siguen leyendo
    los dashboards y hooks viejos. Idempotente (lo corre la migración y cada
    tabs()/ensure_tab(); solo escribe si algo cambia). `store` = ruta del
    sessions-local.json (la migración pasa el de su HOME). Falla-suave →
    {"ids": n, "huerfanas": [nombres sin .md]}."""
    res = {"ids": 0, "huerfanas": []}
    try:
        ws = _read_json(_ws_path(brain, agent), [])
        soc = socio(brain) if ws else ""
        if not ws or not soc:          # sin socio no se sabe qué tiene .md
            return res
        import agent_brand
        have = {t["slug"] for t in _brain_tabs(brain)}   # también archivadas
        path = store or local_store_path()
        bk = _brain_key(brain)

        def aplicar(data):
            changed, ids, huer = False, 0, []
            hb = data.setdefault("huerfanas", {})
            if not isinstance(hb, dict):
                hb = data["huerfanas"] = {}
            mine = hb.get(bk) if isinstance(hb.get(bk), dict) else {}
            for w in ws:
                if not isinstance(w, dict):
                    continue
                name = _clean_name(w.get("name"))
                sl = _slug(name)
                if not name or not sl:
                    continue
                wid = str(w.get("id") or "").strip()
                lo = str(w.get("last_opened") or "").strip()
                if sl in have:
                    slot = _local_slot(data, brain, sl, create=True)
                    if wid and not slot.get("claude-code"):
                        slot["claude-code"] = wid
                        changed, ids = True, ids + 1
                    if lo and agent_brand._epoch(lo) > agent_brand._epoch(
                            slot.get("last_opened", "")):
                        slot["last_opened"] = lo
                        changed = True
                    if sl in mine:                   # ya tiene su .md
                        mine.pop(sl)
                        changed = True
                    continue
                huer.append(name)
                rec = {"name": name, "agente": str(agent or ""), "id": wid,
                       "last_opened": lo,
                       "created": str(w.get("created") or "").strip()}
                if mine.get(sl) != rec:
                    mine[sl] = rec
                    changed = True
            if mine:
                hb[bk] = mine
            elif bk in hb:
                hb.pop(bk)
                changed = True
            return changed, ids, huer

        changed, ids, huer = aplicar(_local_load(path))
        res["huerfanas"] = huer
        if changed:
            from olock import file_lock
            with file_lock(path, timeout=5):
                data = _local_load(path)
                changed, ids, huer = aplicar(data)
                if changed:
                    _local_save(data, path)
            res.update(ids=ids, huerfanas=huer)
    except Exception:
        pass
    return res


def huerfanas(brain=None):
    """Las entradas del workspaces.json local SIN `.md` que la sesiones v2 no
    siembra: {cerebro: {slug: {name, agente, id, …}}} (todas) o {slug: …} de
    `brain`. Solo lee."""
    hb = _local_load().get("huerfanas")
    hb = hb if isinstance(hb, dict) else {}
    if brain is None:
        return hb
    mine = hb.get(_brain_key(brain))
    return mine if isinstance(mine, dict) else {}


def _migrate(brain, agent):
    """(1) Sesiones v2: el workspaces.json per-máquina YA NO siembra `.md`
    (absorber_json_local: sus ids y last_opened pasan al store local; lo que
    no tiene `.md` queda anotado como huérfano). (2) El legacy
    `.workspace/sessions.json` (primer diseño) → sus resume-ids pasan al store
    local y el archivo se renombra a `.migrated` (ya no es fuente de nada).
    Corre en cada tabs()/ensure_tab() — barato e idempotente. Falla-suave."""
    soc = socio(brain)
    # (1) workspaces.json → store local (sin sembrar nada)
    absorber_json_local(brain, agent)
    # (2) legacy .workspace/sessions.json → store local + rename
    try:
        lp = _legacy_registry_path(brain)
        legacy = _read_json(lp, {})
        tabs_l = legacy.get("tabs") if isinstance(legacy, dict) else None
        if isinstance(tabs_l, list):
            ids = []
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
                    ids.append((sl, r))

            def _pasar():
                data, changed = _local_load(), False
                for sl, r in ids:
                    slot = _local_slot(data, brain, sl, create=True)
                    for eng, rid in r.items():
                        if rid and slot.get(eng) != rid:
                            slot[eng] = rid
                            changed = True
                if changed:
                    _local_save(data)
            if ids:
                _con_store(_pasar)
            if os.path.exists(lp):
                os.replace(lp, lp + ".migrated")
    except Exception:
        pass


# ── API pública (misma firma que consumen los motores) ─────────────────────
def tabs(brain, agent, archivadas=False):
    """Las pestañas del agente — DERIVADAS de los .md sincronizados (el núcleo
    común con los dashboards y el panel: agent_brand.pestanas), enriquecidas
    con lo local (resume-ids + last_opened). La lista es la misma en
    cualquier máquina con el mismo contenido del cerebro; lo local solo
    cambia CÓMO se resume aquí. Incluye la migración perezosa.

    `archivadas`: False (default) → sin las archivadas · True → todas ·
    "solo" → solo las archivadas (mejor: archivadas()). Cada pestaña trae
    `archivada` (la fecha, o '')."""
    _migrate(brain, agent)
    out = []
    try:
        data = _local_load()
        ws_by_slug = {}
        for w in _read_json(_ws_path(brain, agent), []):
            if isinstance(w, dict) and w.get("name"):
                ws_by_slug.setdefault(_slug(w["name"]), w)
        for bt in _pestanas(brain, archivadas):
            sl = bt["slug"]            # una por slug (dos .md que colapsan
            slot = _local_slot(data, brain, sl) or {}   # al mismo = UNA)
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
                        "archivada": bt.get("archivada", "") if _es_archivada(bt) else "",
                        "last_opened": slot.get("last_opened", ""),
                        "resume": resume})
    except Exception:
        pass
    return out


def _es_archivada(bt):
    try:
        import agent_brand
        return agent_brand.es_archivada(bt.get("estado"))
    except Exception:
        return str(bt.get("estado") or "").strip().lower() == "archivada"


def archivadas(brain, agent):
    """Solo las pestañas archivadas (mismo formato que tabs()), la archivada
    más reciente primero. Su memoria sigue en el cerebro, intacta."""
    out = tabs(brain, agent, archivadas="solo")
    out.sort(key=lambda t: (t.get("name") or "").lower())
    out.sort(key=lambda t: t.get("archivada") or "", reverse=True)   # estable
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
    el picker de Claude Code la liste/resuma idéntico. Abrir una pestaña
    ARCHIVADA la desarchiva (sesiones v2). Los motores la llaman justo antes
    de lanzar (o del exec): este proceso es la ventana de la pestaña, y queda
    anotado con su pid para que el archivo automático no la toque mientras
    viva. Devuelve el tab dict o None (falla-suave)."""
    try:
        name = _clean_name(name)      # un nombre con saltos/`---` no inyecta
        sl = _slug(name)
        if not sl:
            return None
        _seed_md(brain, name, claude_wid=claude_wid or "")
        try:
            desarchivar(brain, agent, name)   # abrirla = vuelve a la lista
        except Exception:
            pass
        marcar_usada(brain, name)     # el uso viaja: `usada: <hoy>`, 1 vez al día
        _migrate(brain, agent)        # después de sembrar: la nueva no es huérfana

        def _abrir():
            data = _local_load()
            slot = _local_slot(data, brain, sl, create=True)
            if claude_wid:
                slot["claude-code"] = claude_wid
            elif not slot.get("claude-code"):
                import uuid
                slot["claude-code"] = str(uuid.uuid4())
            slot["last_opened"] = _now()
            _anotar_abierta(data, brain, sl)   # protegida mientras viva esta ventana
            _local_save(data)
            return dict(slot)
        slot = _con_store(_abrir)
        _mirror_to_claude(brain, agent, name, slot["claude-code"])
        return find_tab(tabs(brain, agent), name) or {
            "name": name, "slug": sl, "resume": dict(slot)}
    except Exception:
        return None


def _mirror_to_claude(brain, agent, name, wid):
    """Espeja la pestaña al `.claude/<agente>-workspaces.json` per-máquina si
    no está (match por id y slug; jamás duplica ni toca lo existente) — los
    dashboards/hooks de Claude Code siguen con su archivo de siempre."""
    sl = _slug(name)

    def agregar(ws):
        for w in ws:
            if isinstance(w, dict) and (
                    (wid and w.get("id") == wid)
                    or _slug(w.get("name", "")) == sl):
                return None
        now = _now()
        ws.append({"name": name, "id": wid, "created": now,
                   "last_opened": now, "updated": now})
        return ws
    try:
        return actualizar_ws(_ws_path(brain, agent), agregar)
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


def _owner_in(data, brain, engine, rid, skip=""):
    """owner() sobre un store ya cargado (dentro del candado)."""
    tabs_ = ((data.get("map") or {}).get(_brain_key(brain)) or {})
    for sl, slot in tabs_.items():
        if sl != skip and isinstance(slot, dict) and slot.get(engine) == rid:
            return sl
    return ""


def owner(brain, engine, rid, exclude=None):
    """Slug de la pestaña de este cerebro que ya tiene atado `rid` en `engine`
    ('' si ninguna). `exclude` = nombre de la pestaña que pregunta. El atado
    tardío no le roba la conversación a otra pestaña."""
    rid = str(rid or "").strip()
    if not rid:
        return ""
    skip = _slug(exclude) if exclude else ""
    try:
        return _owner_in(_local_load(), brain, engine, rid, skip)
    except Exception:
        return ""


# ── Claude Code: la pestaña sigue a su conversación bifurcada ───────────────
#: El único motor cuyo SessionStart llega con source «fork» (/fork, /branch,
#: mover la conversación al fondo, --fork-session). Los envueltos arrancan
#: siempre con «startup» (interactive.py) y `codex fork` no se ata.
_FORK_ENGINE = "claude-code"


def _espejar_id(brain, agent, name, antes, nuevo):
    """El espejo `.claude/<agente>-workspaces.json` sigue al store: la fila de
    la pestaña cambia de `antes` a `nuevo` (la que tenía `antes` o, si
    ninguna, la primera con su nombre). Jamás agrega una fila: una pestaña es
    una fila en el picker, el panel y el chat del dev panel."""
    if not agent:
        return False
    sl = _slug(name)

    def espejar(ws):
        mias = [w for w in ws if isinstance(w, dict) and _slug(w.get("name", "")) == sl]
        if not mias or any(w.get("id") == nuevo for w in mias):
            return None
        w = next((w for w in mias if w.get("id") == antes), mias[0])
        w["id"] = nuevo
        w["updated"] = _now()
        return ws
    try:
        return actualizar_ws(_ws_path(brain, agent), espejar)
    except Exception:
        return False


def seguir_fork(brain, agent, name, rid):
    """Claude Code abrió la conversación `rid` bifurcando la de la pestaña
    `name` (SessionStart con source «fork»). Sin esto la pestaña seguía atada
    a la madre y el hub la reabría vieja. El payload del fork NO trae el id de
    la madre (doc del motor y caja negra), así que el compare-and-set es
    contra lo que la pestaña tiene atado HOY, bajo el candado del store:

      · la pestaña sin atado de Claude Code aquí → nada (no se crea nada);
      · `rid` ya atado a OTRA pestaña → nada (jamás se roba);
      · si no, la pestaña pasa a `rid`, queda anotado el par (madre, hija)
        para reclamar_fork, y el espejo workspaces.json cambia ese id.

    True si la pestaña quedó en `rid`. Falla-suave → False."""
    rid = str(rid or "").strip()
    sl = _slug(name)
    if not rid or not sl:
        return False
    try:
        from olock import file_lock
        with file_lock(local_store_path(), timeout=5):
            data = _local_load()
            slot = _local_slot(data, brain, sl)
            antes = str((slot or {}).get(_FORK_ENGINE) or "")
            if not antes:
                return False
            if antes == rid:
                return True
            if _owner_in(data, brain, _FORK_ENGINE, rid, sl):
                return False
            slot[_FORK_ENGINE] = rid
            forks = data.get("forks") if isinstance(data.get("forks"), dict) else {}
            data["forks"] = forks
            bk = _brain_key(brain)
            mias = forks.get(bk) if isinstance(forks.get(bk), dict) else {}
            forks[bk] = mias
            mias[sl] = {"madre": antes, "hija": rid, "desde": _now()}
            if not _local_save(data):
                return False
    except Exception:
        return False
    _espejar_id(brain, agent, name, antes, rid)
    return True


def _otra_mitad(data, brain, sl, sid):
    """El id atado hoy a la pestaña `sl` si es la OTRA mitad del último fork
    de esa pestaña y `sid` es la suya; '' si no aplica."""
    rec = (((data.get("forks") or {}).get(_brain_key(brain)) or {}).get(sl))
    if not isinstance(rec, dict):
        return ""
    par = {str(rec.get("madre") or ""), str(rec.get("hija") or "")}
    actual = str((_local_slot(data, brain, sl) or {}).get(_FORK_ENGINE) or "")
    if "" in par or len(par) != 2 or sid not in par or actual not in par or actual == sid:
        return ""
    return actual


def reclamar_fork(brain, agent, name, sid):
    """El socio le escribió a la conversación `sid` de la pestaña `name`
    (UserPromptSubmit). Con /fork la copia corre al fondo y la ORIGINAL sigue
    en la terminal: si el socio sigue en una mitad del par, la pestaña vuelve
    a ella (reabre la que usó al último). Solo entre la madre y la hija del
    último fork de ESA pestaña, compare-and-set (la pestaña debe estar en la
    otra mitad) y sin robar. Sin par anotado no toma el candado. True si
    cambió. Falla-suave → False."""
    sid = str(sid or "").strip()
    sl = _slug(name)
    if not sid or not sl:
        return False
    try:
        if not _otra_mitad(_local_load(), brain, sl, sid):
            return False
        from olock import file_lock
        with file_lock(local_store_path(), timeout=5):
            data = _local_load()
            actual = _otra_mitad(data, brain, sl, sid)
            if not actual or _owner_in(data, brain, _FORK_ENGINE, sid, sl):
                return False
            _local_slot(data, brain, sl)[_FORK_ENGINE] = sid
            if not _local_save(data):
                return False
    except Exception:
        return False
    _espejar_id(brain, agent, name, actual, sid)
    return True


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


# ── sesiones v2: ARCHIVAR (quitar del menú sin borrar) ──────────────────────
#: Días sin uso tras los que una pestaña se archiva sola (decisión del dueño,
#: 2026-11-05). El ajuste `sesiones.archivar_dias` lo cambia; 0 lo apaga.
ARCHIVAR_DIAS_DEFAULT = 15
#: Lotes de archivo que se guardan para deshacer (`u`, `desarchivar --ultimas`).
LOTES_MAX = 30


def _t(key, es, **kw):
    """Texto al usuario en su idioma (i18n, catálogo lang/*/sesiones.py);
    sin i18n, el español de aquí. Jamás levanta."""
    try:
        import i18n
        s = i18n.t(key, **kw)
        if s != key:
            return s
    except Exception:
        pass
    try:
        return es.format(**kw) if kw else es
    except Exception:
        return es


def _rutas_tab(brain, name):
    """Los `.md` de la pestaña `name` (por su slug o por su nombre visible):
    el suyo y, si un conflicto de sync dejó otro que cae en el mismo slug,
    también ese — archivar los marca a todos, o la pestaña reaparecería con
    el otro. [] si no tiene memoria en el cerebro."""
    sl = _slug(name)
    out = []
    if not sl:
        return out
    for bt in _brain_tabs(brain):
        a = bt.get("archivo") or ""
        if a and a not in out and os.path.isfile(a) and (
                bt.get("slug") == sl or _slug(bt.get("name") or "") == sl):
            out.append(a)
    return out


def _front_archivo(texto, archivar, fecha):
    """El texto con el archivo puesto (`estado: archivada` + `archivada:
    <fecha>`) o quitado (`estado: activa`, sin `archivada:`). Solo toca esas
    dos claves de nivel 0 del frontmatter; el resto queda byte a byte. None
    si no hay nada que cambiar o si el frontmatter no se entiende (no se
    reescribe a ciegas)."""
    lineas = texto.split("\n")
    if not lineas or lineas[0].strip() != "---":
        if not archivar or not texto.strip():
            return None
        return "---\nestado: archivada\narchivada: %s\n---\n%s" % (fecha, texto)
    fin = next((i for i in range(1, len(lineas)) if lineas[i].strip() == "---"), -1)
    if fin < 0:
        return None
    head = lineas[1:fin]

    def clave(ln, k):
        return re.match(r"^%s\s*:" % k, ln) is not None

    def valor(ln):
        return ln.split(":", 1)[1].strip()

    try:
        import agent_brand
        es_arch = agent_brand.es_archivada
    except Exception:
        def es_arch(v):
            return str(v or "").strip().lower() == "archivada"
    ya = any(es_arch(valor(ln)) for ln in head if clave(ln, "estado"))
    if archivar and ya:
        return None                     # ya archivada: se queda su fecha
    out, puso_est, puso_arc = [], False, False
    for ln in head:
        if clave(ln, "estado"):
            if puso_est:
                continue                # duplicada: la última ganaría al leer
            puso_est = True
            if archivar:
                out.append("estado: archivada")
                if not puso_arc:
                    out.append("archivada: %s" % fecha)
                    puso_arc = True
            else:
                out.append("estado: activa" if es_arch(valor(ln)) else ln)
            continue
        if clave(ln, "archivada"):
            if archivar and not puso_arc:
                out.append("archivada: %s" % fecha)
                puso_arc = True
            continue                    # desarchivar: se quita
        out.append(ln)
    if archivar:
        if not puso_est:
            out.append("estado: archivada")
        if not puso_arc:
            out.append("archivada: %s" % fecha)
    if out == head:
        return None
    return "\n".join([lineas[0]] + out + lineas[fin:])


def _marcar(path, archivar, fecha=None):
    """Pone o quita el archivo en el frontmatter de `path` con el candado y la
    escritura atómica de `workspace memoria` (las notas del agente y esto no
    se pisan). True si ESTE llamado cambió el archivo, False si ya estaba
    así. Lanza si no se pudo (no es UTF-8, permisos, candado ocupado)."""
    if not path or not os.path.isfile(path):
        return False
    try:                                # sin candado ni escritura si ya está así
        import agent_brand              # (abrir cada pestaña pasa por aquí)
        fm = agent_brand.parse_frontmatter(path)
        if agent_brand.es_archivada(fm.get("estado")) == bool(archivar) \
                and (archivar or "archivada" not in fm):
            return False
    except Exception:
        pass
    return _reescribir(path, lambda texto: _front_archivo(texto, archivar, fecha or _today()))


def _reescribir(path, editar):
    """`editar(texto) → texto nuevo | None` sobre `path`, con el candado y la
    escritura atómica de `workspace memoria` (las notas del agente y esto no
    se pisan). True si cambió; lanza si no se pudo (no es UTF-8, permisos,
    candado ocupado)."""
    import memoria
    with memoria._lock(path):
        texto = memoria._leer(path)    # estricto: uno que no es UTF-8 no se reescribe
        nuevo = editar(texto)
        if nuevo is None:
            return False
        memoria._atomic(path, nuevo)   # frente C: helper común (os.replace con reintento)
        return True


def _front_clave(texto, clave, valor):
    """El texto con `clave: valor` (nivel 0) en el frontmatter: reemplaza la
    clave (y quita sus duplicadas) o la agrega al final; el resto queda byte
    a byte. Sin frontmatter, se le pone uno con esa sola clave. None si ya
    estaba así o si el frontmatter no se entiende."""
    lineas = texto.split("\n")
    linea = "%s: %s" % (clave, valor)
    if not lineas or lineas[0].strip() != "---":
        return "---\n%s\n---\n%s" % (linea, texto) if texto.strip() else None
    fin = next((i for i in range(1, len(lineas)) if lineas[i].strip() == "---"), -1)
    if fin < 0:
        return None
    head = lineas[1:fin]
    out, puesta = [], False
    for ln in head:
        if re.match(r"^%s\s*:" % re.escape(clave), ln):
            if not puesta:
                out.append(linea)
                puesta = True
            continue
        out.append(ln)
    if not puesta:
        out.append(linea)
    if out == head:
        return None
    return "\n".join([lineas[0]] + out + lineas[fin:])


def marcar_usada(brain, name, fecha=None):
    """Deja `usada: <hoy>` en el frontmatter de la pestaña `name`: el último
    uso que VIAJA (el `last_opened` es de cada máquina). Como mucho una
    escritura al día: si ya dice hoy, no se toca ni se toma el candado. Lo
    llama ensure_tab al abrir. True si escribió. Falla-suave."""
    fecha = fecha or _today()
    escribio = False
    for p in _rutas_tab(brain, name):
        try:
            import agent_brand
            if agent_brand.parse_frontmatter(p).get("usada", "").strip() == fecha:
                continue
            if _reescribir(p, lambda texto: _front_clave(texto, "usada", fecha)):
                escribio = True
        except Exception:
            continue
    return escribio


def _nombre_visible(brain, name):
    """El nombre con el que el menú muestra la pestaña (su `titulo:`)."""
    sl = _slug(name)
    for bt in _pestanas(brain, True):
        if bt.get("slug") == sl or _slug(bt.get("name") or "") == sl:
            return bt.get("name") or _clean_name(name)
    return _clean_name(name)


def _nuevo_lote():
    import uuid
    return "%s-%s" % (datetime.datetime.now().strftime("%Y%m%dT%H%M%S"), uuid.uuid4().hex[:6])


def _lote(lid, tipo, agregar=None, quitar=None):
    """Anota en el lote `lid` (lo crea si falta) la pestaña `agregar`, o le
    quita `quitar` (y el lote, si queda vacío). Quien archiva agrega cada
    pestaña ANTES de marcarla: si el proceso se corta a media pasada, lo ya
    marcado se puede deshacer (deshacer una que no llegó a archivarse no hace
    nada). Bajo el candado del store. Falla-suave."""
    def fn():
        data = _local_load()
        lotes = [x for x in (data.get("lotes") or []) if isinstance(x, dict)]
        lt = next((x for x in lotes if x.get("id") == lid), None)
        if lt is None:
            if not agregar:
                return
            lt = {"id": lid, "tipo": tipo, "cuando": _now(), "pestanas": []}
            lotes.append(lt)
        pest = [x for x in lt.get("pestanas") or [] if isinstance(x, dict)]
        if agregar:
            pest.append(agregar)
        if quitar:
            pest = [x for x in pest if (x.get("brain"), x.get("slug"))
                    != (quitar.get("brain"), quitar.get("slug"))]
        lt["pestanas"] = pest
        if not pest:
            lotes.remove(lt)
        data["lotes"] = lotes[-LOTES_MAX:]
        _local_save(data)
    try:
        _con_store(fn)
    except Exception:
        pass


def _poner(brain, name, archivar, fecha=None, rutas=None):
    """(ok, [rutas que cambiaron]). ok = la pestaña existe y quedó en el
    estado pedido."""
    rutas = rutas if rutas is not None else _rutas_tab(brain, name)
    if not rutas:
        return False, []
    cambio = []
    for p in rutas:
        try:
            if _marcar(p, archivar, fecha):
                cambio.append(p)
        except Exception:
            return False, cambio
    return True, cambio


def archivar(brain, agent, name, fecha=None):
    """Archiva la pestaña `name`: `estado: archivada` + `archivada: <fecha>`
    en su `.md`. El archivo no se mueve ni se borra; como viaja con el
    cerebro, sale del menú en TODAS las máquinas. Su memoria sigue ahí
    (`workspace memoria` la lee). Queda un lote para deshacer (`u` en el
    menú, `workspace sesiones desarchivar --ultimas`). True si quedó
    archivada (ahora o ya lo estaba); False si no existe o no se pudo."""
    try:
        rutas = _rutas_tab(brain, name)
        if not rutas:
            return False
        if esta_archivada(brain, name):
            return True
        visible = _nombre_visible(brain, name)
        lid = _nuevo_lote()
        item = {"brain": _brain_key(brain), "agente": str(agent or ""),
                "slug": _slug(visible) or _slug(name), "name": visible, "archivos": rutas}
        _lote(lid, "manual", agregar=item)          # antes de marcar (ver _lote)
        ok, cambio = _poner(brain, name, True, fecha, rutas=rutas)
        if not cambio:
            _lote(lid, "manual", quitar=item)
        return ok
    except Exception:
        return False


def desarchivar(brain, agent, name):
    """La pestaña `name` vuelve al menú (`estado: activa`, sin `archivada:`).
    Si no tiene `.md` pero es una huérfana del workspaces.json local (lo que
    la sesiones v2 dejó de sembrar), se le siembra su `.md`: así se deshace
    también eso. True si quedó en la lista; False si no existe o no se pudo."""
    try:
        rutas = _rutas_tab(brain, name)
        if not rutas:
            return _recuperar_huerfana(brain, agent, name)
        ok, _cambio = _poner(brain, name, False, rutas=rutas)
        return ok
    except Exception:
        return False


def _recuperar_huerfana(brain, agent, name):
    sl = _slug(name)
    rec = huerfanas(brain).get(sl) if sl else None
    if not isinstance(rec, dict):
        return False
    if not _seed_md(brain, rec.get("name") or name, claude_wid=rec.get("id") or ""):
        return False
    try:
        from olock import file_lock
        with file_lock(local_store_path(), timeout=5):
            data = _local_load()
            mine = (data.get("huerfanas") or {}).get(_brain_key(brain)) or {}
            mine.pop(sl, None)
            if rec.get("id"):
                slot = _local_slot(data, brain, sl, create=True)
                slot.setdefault("claude-code", rec["id"])
            _local_save(data)
    except Exception:
        pass
    return True


def esta_archivada(brain, name):
    """¿La pestaña `name` está archivada? (False si no existe). Ojo: no es
    agent_brand.es_archivada, que mira un valor de `estado:`."""
    rutas = _rutas_tab(brain, name)
    if not rutas:
        return False
    try:
        import agent_brand
        return all(agent_brand.es_archivada(agent_brand.parse_frontmatter(p).get("estado"))
                   for p in rutas)
    except Exception:
        return False


def _deshacer_item(p):
    """Desarchiva una pestaña de un lote. True si ESTE llamado la recuperó."""
    rutas = [a for a in (p.get("archivos") or []) if isinstance(a, str) and os.path.isfile(a)]
    if not rutas and p.get("brain") and p.get("name"):
        rutas = _rutas_tab(p["brain"], p["name"])
    _ok, cambio = _poner(p.get("brain") or "", p.get("name") or "", False, rutas=rutas)
    return bool(cambio)


def desarchivar_ultimas(brain=None, agent=None):
    """Deshace el último lote de archivo (el `u` del menú, `workspace sesiones
    desarchivar --ultimas`): con `brain`, el último que tocó ese cerebro; sin
    él, el más reciente de esta máquina. Lo deshecho sale del lote, así que
    otro `u` deshace el anterior. Si en el último lote ya no queda nada que
    recuperar (se abrieron o se recuperaron a mano), es «nada que deshacer»:
    no se salta a un lote viejo que nadie esperaba. → [nombres recuperados]
    ([] = nada que deshacer)."""
    recuperadas = []
    bk = _brain_key(brain) if brain else None

    def fn():
        data = _local_load()
        lotes = [lt for lt in (data.get("lotes") or []) if isinstance(lt, dict)]
        i = next((k for k in range(len(lotes) - 1, -1, -1)
                  if any(bk is None or p.get("brain") == bk
                         for p in lotes[k].get("pestanas") or [] if isinstance(p, dict))),
                 None)
        if i is None:
            return
        lt = lotes[i]
        todas = [p for p in lt.get("pestanas") or [] if isinstance(p, dict)]
        mias = [p for p in todas if bk is None or p.get("brain") == bk]
        for p in mias:
            if _deshacer_item(p):
                recuperadas.append(p.get("name") or p.get("slug") or "?")
        if not recuperadas:
            return                      # el lote se queda: nada que deshacer
        resto = [p for p in todas if p not in mias]
        if resto:
            lt["pestanas"] = resto
        else:
            lotes.pop(i)
        data["lotes"] = lotes
        _local_save(data)
    try:
        _con_store(fn)
    except Exception:
        pass
    return recuperadas


def dias_archivar():
    """Días sin uso tras los que una pestaña se archiva sola: el ajuste
    `sesiones.archivar_dias` (0 = apagado). Falla-suave → 15."""
    try:
        import settings
        return max(0, int(settings.get("sesiones.archivar_dias")))
    except Exception:
        return ARCHIVAR_DIAS_DEFAULT


def _fin_del_dia(fecha):
    """Epoch de una fecha del frontmatter o del store: una fecha sola
    (YYYY-MM-DD) cuenta hasta el final de ese día; una con hora, tal cual.
    Vacía o ilegible → 0."""
    try:
        import agent_brand
        ep = agent_brand._epoch(fecha)
    except Exception:
        return 0.0
    s = str(fecha or "").strip()
    return ep + 86399 if ep and len(s) == 10 else ep


def ultimo_uso(tab, slot=None):
    """Epoch del último uso de una pestaña (fila del núcleo): el MÁXIMO entre
    el last_opened de esta máquina, el `usada:` del `.md` (lo escribe cada
    máquina al abrirla: el uso que viaja), su `actualizada:` y la fecha de
    modificación del `.md` (lo que escribió otra máquina llega por ahí)."""
    try:
        import agent_brand
        ep = agent_brand._epoch
    except Exception:
        def ep(_s):
            return 0.0
    usos = [ep((slot or {}).get("last_opened", "")), ep(tab.get("actualizada", "")),
            _fin_del_dia(tab.get("usada", ""))]
    try:
        usos.append(os.path.getmtime(tab.get("archivo") or ""))
    except OSError:
        pass
    return max(usos)


def _marca_proceso():
    """Huella de ESTE proceso (pid + hora de inicio), la misma que usa
    pending_runs: un pid reciclado no pasa por vivo."""
    import time
    try:
        import openclaw_gateway as G
        return G._mark()
    except Exception:
        return {"pid": os.getpid(), "ctime": None, "t0": time.time()}


def _proceso_vivo(marca):
    """¿Vive el proceso de la huella? Mac/Linux y Windows (OpenProcess) vía
    openclaw_gateway._alive, como pending_runs. Sin él: os.kill(pid, 0) fuera
    de Windows; en Windows, vivo por 12 h (jamás os.kill ahí: lo terminaría)."""
    try:
        import openclaw_gateway as G
        return bool(G._alive(marca))
    except Exception:
        pass
    import time
    try:
        pid = int((marca or {}).get("pid") or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        return time.time() - float((marca or {}).get("t0") or 0) < 12 * 3600
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _anotar_abierta(data, brain, sl):
    """En el store (`abiertas`): la pestaña `sl` está abierta en ESTE proceso.
    Una entrada por pid (otra pestaña en el mismo proceso la reemplaza)."""
    ab = data.get("abiertas") if isinstance(data.get("abiertas"), dict) else {}
    data["abiertas"] = ab
    mias = ab.get(_brain_key(brain)) if isinstance(ab.get(_brain_key(brain)), dict) else {}
    ab[_brain_key(brain)] = mias
    marca = _marca_proceso()
    mias[str(marca.get("pid"))] = {"slug": sl, "proc": marca, "desde": _now()}


def abiertas_en_ventanas(brain):
    """Slugs de las pestañas de `brain` abiertas en una ventana viva de esta
    máquina (ensure_tab anota cada una con su pid al lanzarla; Claude Code
    hace exec y no pasa por pending_runs). Las de procesos muertos se limpian
    solas. Falla-suave → set()."""
    bk = _brain_key(brain)
    try:
        mias = (_local_load().get("abiertas") or {}).get(bk)
        if not isinstance(mias, dict) or not mias:
            return set()
        vivas, muertas = set(), {}
        for pid, e in mias.items():
            if isinstance(e, dict) and _proceso_vivo(e.get("proc")):
                vivas.add(str(e.get("slug") or ""))
            else:
                muertas[pid] = e
        if muertas:
            def limpiar():
                data = _local_load()
                ab = data.get("abiertas") if isinstance(data.get("abiertas"), dict) else {}
                actual = ab.get(bk) if isinstance(ab.get(bk), dict) else {}
                for pid, e in muertas.items():
                    if actual.get(pid) == e:        # nadie la reanotó mientras
                        actual.pop(pid)
                if not actual:
                    ab.pop(bk, None)
                if not ab:
                    data.pop("abiertas", None)
                _local_save(data)
            _con_store(limpiar)
        vivas.discard("")
        return vivas
    except Exception:
        return set()


def _abiertas_ahora(brain):
    """Slugs de las pestañas abiertas en este momento: la de esta ventana
    (WORKSPACE_WS), las de las ventanas vivas de esta máquina (con su pid) y
    las de las corridas vivas del cerebro (pending_runs)."""
    out = {_slug(os.environ.get(k) or "") for k in ("WORKSPACE_WS", "ZENITH_WS")}
    out |= abiertas_en_ventanas(brain)
    try:
        import pending_runs
        for rec in pending_runs.pending(brain):
            if rec.get("tab") and pending_runs.proc_alive(rec):
                out.add(_slug(rec["tab"]))
    except Exception:
        pass
    out.discard("")
    return out


#: Días que esta máquina pudo estar fuera sin que su copia del cerebro se
#: considere vieja para archivar solo (hallazgo de la revisión: una PC que
#: vuelve tras semanas archivaba lo que otra usó ayer).
FUERA_MAX_DIAS = 2


def _copia_confiable(brain, ahora):
    """¿La copia del cerebro en esta máquina sirve para decidir qué lleva N
    días sin uso? Lo dice la constancia de máquinas (frente C):
      · `maquinas.visto_previo(brain)`: la vez ANTERIOR que esta máquina dejó
        su constancia en ese cerebro (la de esta apertura ya se escribió).
        Sin ella o de hace más de FUERA_MAX_DIAS días, esta máquina estuvo
        fuera y su copia puede estar vieja → no;
      · `maquinas.copia_al_dia(brain)`: False si otra máquina trae actividad
        más nueva que lo que esta tiene en disco (aún no le llega) → no.
        None = no hay otra máquina con constancia (un solo equipo): no hay
        contra qué estar desfasada → sí (si no, un cliente con una sola
        máquina nunca archivaría).
    Cualquier otra duda (sin maquinas, sin esas funciones, error) → no."""
    try:
        import maquinas
        previo = getattr(maquinas, "visto_previo", None)
        al_dia = getattr(maquinas, "copia_al_dia", None)
        if not callable(previo) or not callable(al_dia):
            return False
        visto = previo(brain)
        if visto is None or float(visto) < ahora - FUERA_MAX_DIAS * 86400:
            return False
        return al_dia(brain) is not False
    except Exception:
        return False


def auto_archivar(brain, agent, dias=None, ahora=None, abiertas=()):
    """Archiva solas las pestañas sin uso en más de `dias` días (default: el
    ajuste `sesiones.archivar_dias`; 0 = apagado). Último uso = ultimo_uso().
    Corre solo en dispatch, sobre el cerebro que se abre.
      · No archiva nada si la copia del cerebro en esta máquina puede estar
        vieja (_copia_confiable: esta máquina estuvo fuera, u otra trae
        actividad que aún no llega).
      · Nunca archiva una pestaña abierta en este momento (`abiertas` + las
        que detecta _abiertas_ahora).
      · Con `archivar_desde` en el store local (la gracia que pone la
        migración al actualizar), el último uso nunca es anterior a esa fecha.
      · Cada pestaña entra al lote ANTES de marcarse (_lote): un corte a media
        pasada se puede deshacer.
    Barato (lee los frontmatter, sin red) y falla-suave. `ahora` (epoch) es
    para pruebas con reloj simulado. → [nombres archivados]."""
    try:
        dias = dias_archivar() if dias is None else int(dias)
        if dias <= 0 or not brain or not os.path.isdir(brain):
            return []
        import time
        ahora = time.time() if ahora is None else float(ahora)
        if not _copia_confiable(brain, ahora):
            return []
        limite = ahora - dias * 86400
        proteger = {_slug(x) for x in (abiertas or ())} | _abiertas_ahora(brain)
        data = _local_load()
        slots = data["map"].get(_brain_key(brain)) or {}
        # gracia tras actualizar (migración archivar_desde): nada cuenta como
        # sin uso antes de esa fecha — mientras, cada pestaña que se abre en
        # cualquier máquina gana su `usada:`
        desde = _fin_del_dia(data.get("archivar_desde", ""))
        fecha = datetime.date.fromtimestamp(ahora).isoformat()
        lid, nombres = None, []
        for t in _pestanas(brain, False):
            if t["slug"] in proteger:
                continue
            slot = slots.get(t["slug"]) if isinstance(slots.get(t["slug"]), dict) else {}
            uso = max(ultimo_uso(t, slot), desde)
            if not uso or uso >= limite:
                continue
            rutas = _rutas_tab(brain, t["name"])
            if t.get("archivo") and t["archivo"] not in rutas:
                rutas.append(t["archivo"])
            item = {"brain": _brain_key(brain), "agente": str(agent or ""),
                    "slug": t["slug"], "name": t["name"], "archivos": rutas}
            lid = lid or _nuevo_lote()
            _lote(lid, "auto", agregar=item)        # antes de marcar
            ok, cambio = _poner(brain, t["name"], True, fecha, rutas=rutas)
            if ok and cambio:
                nombres.append(t["name"])
            else:
                _lote(lid, "auto", quitar=item)
        return nombres
    except Exception:
        return []


def aviso_auto(n, dias=None, menu=False):
    """La línea que avisa lo que se archivó solo, con su deshacer. `menu`:
    la del menú de pestañas, donde se deshace con la tecla `u` (el comando
    no cabía en la caja y se cortaba justo antes del deshacer)."""
    dias = dias_archivar() if dias is None else dias
    if menu:
        if n == 1:
            return _t("sesiones.auto.uno_menu",
                      "archivé 1 pestaña sin usar en {dias} días · u para deshacer", dias=dias)
        return _t("sesiones.auto.varias_menu",
                  "archivé {n} pestañas sin usar en {dias} días · u para deshacer",
                  n=n, dias=dias)
    if n == 1:
        return _t("sesiones.auto.uno", "archivé 1 pestaña sin usar en {dias} días · deshacer: "
                  "`workspace sesiones desarchivar --ultimas`", dias=dias)
    return _t("sesiones.auto.varias", "archivé {n} pestañas sin usar en {dias} días · deshacer: "
              "`workspace sesiones desarchivar --ultimas`", n=n, dias=dias)


def aviso_pendiente(brain, menu=False):
    """La línea del último archivo automático de este cerebro, si en este
    cerebro nadie la ha visto todavía, UNA sola vez y sin importar cuánto
    tiempo pasó: el menú de pestañas la muestra al entrar, porque la
    pantalla del motor borra lo que dispatch imprime antes. '' si no hay o
    ya se vio. `menu`: el texto del menú (aviso_auto). Falla-suave."""
    bk = _brain_key(brain)

    def fn():
        data = _local_load()
        for lt in reversed([x for x in (data.get("lotes") or []) if isinstance(x, dict)]):
            mias = [p for p in lt.get("pestanas") or []
                    if isinstance(p, dict) and p.get("brain") == bk]
            if lt.get("tipo") != "auto" or not mias:
                continue
            vistos = lt.get("anunciado")
            if vistos is True or (isinstance(vistos, list) and bk in vistos):
                return ""
            lt["anunciado"] = (vistos if isinstance(vistos, list) else []) + [bk]
            _local_save(data)
            return aviso_auto(len(mias), menu=menu)
        return ""
    try:
        return _con_store(fn) or ""
    except Exception:
        return ""


def al_abrir(brain, agent, abiertas=()):
    """Al abrir un agente (dispatch, DESPUÉS de la constancia de máquinas):
    archiva solo lo que lleva más de N días sin uso en ESE cerebro. Es el
    único lugar donde corre el archivo automático (el hub ya no: su hilo
    moría a media escritura al elegir un agente). → la línea de aviso, o ''
    si no archivó nada."""
    try:
        n = len(auto_archivar(brain, agent, abiertas=abiertas))
        return aviso_auto(n) if n else ""
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


def _socio_line(brain):
    """Quién es el socio activo y dónde está su perfil. BRAIN.md dice que se
    resuelve por `.claude/socio.local` o el entorno, pero un motor sin entorno
    (OpenClaw: su gateway no hereda el de la pestaña) no lo ve y el agente lo
    buscaba a ciegas (auditoría 2026-10-21). '' si no se sabe quién es."""
    soc = socio(brain) if brain else ""
    if not soc:
        return ""
    perfil = "STATE/users/%s.md" % soc
    if not os.path.isfile(os.path.join(brain, "STATE", "users", soc + ".md")):
        perfil = ""
        try:
            import usuarios
            ced = next((c for c in usuarios.cedulas(brain) if c.get("nombre") == soc), None)
            if ced and ced.get("ruta"):
                perfil = "STATE/users/" + os.path.basename(ced["ruta"])
        except Exception:
            pass
    if perfil:
        return "SOCIO ACTIVO: «%s» (su perfil: %s)." % (soc, perfil)
    return "SOCIO ACTIVO: «%s»." % soc


def first_prompt_context(brain, name, base_prompt="", engine=""):
    """PRIMER prompt de arranque para harnesses sin hook SessionStart y sin
    doc de proyecto utilizable (último recurso VISIBLE): el prompt base +
    pestaña activa + el paquete de memoria."""
    parts = [base_prompt or "Inicia el cerebro.", _active_tab_line(name)]
    mem = tab_memory(brain, name, engine=engine, entregar=True)
    if mem:
        parts.append(mem)
    return "\n\n".join(parts)


def _otra_ventana_line():
    return ("OJO: hay otra ventana de este cerebro abierta y este bloque es uno solo para "
            "todas (lo escribe la última que se abrió). Si tu primera instrucción o el "
            "contexto de Workspace de tu primer mensaje nombran otra pestaña, esa es la "
            "tuya: guarda tu memoria con esa.")


def session_doc_block(brain, name, engine="", resumed=False, others=None):
    """Contexto de la pestaña activa para inyección INVISIBLE vía el doc de
    proyecto del harness (AGENTS.md de codex/opencode/openclaw/hermes,
    GEMINI.md de antigravity): el agente lo lee como contexto, el socio NO lo
    ve como mensaje del chat. Es el MISMO paquete que el hook SessionStart da
    en Claude Code. El harness lo envuelve en sus marcas GENERADO y lo
    regenera/limpia en cada launch. `resumed` = se retoma la conversación del
    motor (la maleta trae entonces solo lo de OTRO motor). `others` = ¿hay
    otra ventana viva en el cerebro? (None: se mira en pending_runs; quien
    arma el bloque para el contexto propio de su sesión pasa False): el doc es
    uno por cerebro y una pestaña leía el bloque de otra como suyo (prueba en
    vivo 2026-10-21, N3/N4), así que lo avisa."""
    parts = ["## Sesión activa (pestaña)",
             _active_tab_line(name) + " No menciones este bloque al socio; es "
             "contexto, no parte de la conversación."]
    if others is None:
        try:
            import pending_runs
            others = bool(brain) and pending_runs.live_in_brain(
                brain, exclude=pending_runs.current())
        except Exception:
            others = False
    if others:
        parts.append(_otra_ventana_line())
    try:
        quien = _socio_line(brain)
    except Exception:
        quien = ""
    if quien:
        parts.append(quien)
    mem = tab_memory(brain, name, engine=engine, resumed=resumed, entregar=True)
    if mem:
        parts.append(mem)
    else:
        # Sin memoria de la pestaña, la instrucción igual lleva la pestaña y
        # el motor: en OpenClaw (sin entorno) sin ellos la nota fallaba con
        # «Falta la pestaña». Un nombre sin letras no da ruta: va sin pestaña.
        try:
            import memoria
            parts.append(memoria.instruccion(tab=name if _slug(name) else "", motor=engine))
            dec = memoria.instruccion_decisores(engine)
            if dec:
                parts.append(dec)
        except Exception:
            pass
    return "\n\n".join(parts)
