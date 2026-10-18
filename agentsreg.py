#!/usr/bin/env python3
"""WORKSPACE · agentsreg — registro PER-MÁQUINA de agentes cargados.

El harness se distribuye VACÍO (sin agentes). Los agentes se CARGAN apuntando a
una carpeta de cerebro autocontenida (que lleva `<BRAIN>/.workspace/agent.json`) o
se CREAN. Este módulo es la fuente de verdad de "qué agentes hay en ESTA máquina".

Archivo: `~/.claude/workspace/agents.local.json` (per-máquina, gitignored — como
paths.local.json):
    {"version": 1, "agents": [ {"name": "mi", "brain": "/ruta/MI - BRAIN"} ]}

Cada agente cargado se DESCRIBE A SÍ MISMO en `<brain>/.workspace/agent.json`
(identidad: name/display/tagline/engine/color/owner/setup/memory). El registro
per-máquina solo mapea name → ruta del cerebro. Así "cargar" = registrar una
ruta, y el cerebro es portátil entre máquinas.

Principios: stdlib puro (3.9+), falla-suave (archivo ausente/corrupto → vacío,
nunca levanta en los lectores), escritura ATÓMICA (tmp + os.replace), idempotente
(add del mismo name actualiza, no duplica), forward-compat (preserva claves
desconocidas). Amputable: sin este archivo, el harness simplemente no tiene
agentes cargados.

API:  local_path() · read_local() · agents() · find(name) · add(name, brain) ·
      remove(name) · agent_json_path(brain) · load_definition(brain) ·
      discover() · candidates() · repair_suggestions() · relocate(name, path) ·
      discover_and_register() (registro EXPLÍCITO)
"""
import json
import os
import re

import legacy


def _t(key, es, **kw):
    """i18n falla-suave (el aviso de descubrir lo ve el cliente en «Agregar
    agente»). Sin i18n → el español inline, idéntico."""
    s = es
    try:
        import i18n
        v = i18n.t(key)
        s = v if v != key else es
    except Exception:
        s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")   # slug de agente válido
WORKSPACE_SUBDIR = ".workspace"                            # carpeta auto-descriptiva en el cerebro
LEGACY_SUBDIR = legacy.BRAIN_SUBDIR                        # layout de la instalación anterior (pre-rename)


# ── rutas (funciones, no constantes: respetan HOME parchado en tests) ────────
def _workspace_dir():
    import paths                       # SSOT de la ruta de estado per-máquina
    return paths.workspace_dir()


def local_path():
    return os.path.join(_workspace_dir(), "agents.local.json")


def agent_json_path(brain):
    """Ruta de la definición auto-descriptiva de un cerebro. CANÓNICO:
    `<brain>/.workspace/agent.json`. FALLBACK (robustez): si no existe pero hay un
    `<brain>/agent.json` en la raíz, se usa ese — así un cerebro/drop-in externo
    que traiga su manifiesto en la raíz también funciona (mata el bug "banner
    genérico porque la def estaba en la raíz"). Si ninguno existe, devuelve el
    canónico (para mensajes y escritura)."""
    base = os.path.expanduser(brain or "")
    canonical = os.path.join(base, WORKSPACE_SUBDIR, "agent.json")
    if os.path.isfile(canonical):
        return canonical
    legacy = os.path.join(base, "agent.json")
    if os.path.isfile(legacy):
        return legacy
    return canonical


# ── lectura (falla-suave SIEMPRE → estructura vacía válida) ──────────────────
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def read_local(strict=False):
    """El doc completo del registro per-máquina, saneado. Falla-suave → vacío.
    `strict=True`: si el archivo EXISTE pero no se puede leer (o no trae la
    lista de agentes) LANZA en vez de pasar por vacío — para quien decide
    algo destructivo con «no está registrado» (agent_create_job.cleanup)."""
    path = local_path()
    if strict and os.path.lexists(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not isinstance(data.get("agents"), list):
            raise ValueError("forma inesperada: %s" % path)
    else:
        data = _read_json(path)
    ags = data.get("agents")
    if not isinstance(ags, list):
        data["agents"] = []
    data.setdefault("version", 1)
    return data


def agents():
    """Lista [{name, brain}, …] de agentes cargados en esta máquina. Solo
    entradas sanas (name válido + brain string). Falla-suave → []."""
    out = []
    for a in read_local().get("agents", []):
        if not isinstance(a, dict):
            continue
        name = str(a.get("name", "")).strip().lower()
        brain = str(a.get("brain", "")).strip()
        if NAME_RE.match(name) and brain:
            entry = dict(a)
            entry["name"] = name
            entry["brain"] = os.path.expanduser(brain)
            out.append(entry)
    return out


def find(name):
    name = (name or "").strip().lower()
    for a in agents():
        if a["name"] == name:
            return a
    return None


def is_valid_name(name):
    return bool(NAME_RE.match((name or "").strip().lower()))


# ── definición auto-descriptiva del cerebro ─────────────────────────────────
def load_definition(brain):
    """Lee `<brain>/.workspace/agent.json` (la identidad del agente). Devuelve
    dict o {} si no existe / corrupto (falla-suave — el caller decide si sembrar)."""
    return _read_json(agent_json_path(brain))


def has_definition(brain):
    return os.path.isfile(agent_json_path(brain))


# ── instalación anterior (<brain>/<LEGACY_SUBDIR>/agent.json) ────────────────
# Cerebros que vienen del harness anterior (nombre viejo del producto) traen su
# manifiesto en la subcarpeta vieja y NUNCA se migraron a `.workspace/`. Quien
# actualiza desde la instalación anterior no vería sus agentes si discover()
# exigiera `.workspace/`. Se detectan aquí y se MIGRAN al conectarlos. NO se
# borra la carpeta vieja — de eso se encarga `workspace doctor` (Fase 5d), que
# solo la elimina cuando ya existe el `.workspace/agent.json`.
def legacy_json_path(brain):
    """Ruta del manifiesto de la instalación anterior de un cerebro."""
    return os.path.join(os.path.expanduser(brain or ""), LEGACY_SUBDIR, "agent.json")


def has_legacy_definition(brain):
    return os.path.isfile(legacy_json_path(brain))


def _normalize_definition(d):
    """Normaliza una def de la instalación anterior al schema `.workspace` actual. Hoy el
    schema es idéntico (mismo `agent.json`), así que es un passthrough que
    PRESERVA toda clave desconocida (forward-compat) — punto único donde
    re-mapear si algún día divergen. Falla-suave → {}."""
    if not isinstance(d, dict):
        return {}
    return dict(d)


def migrate_legacy(brain):
    """Si `<brain>` trae SOLO el manifiesto de la instalación anterior y NO
    `.workspace/agent.json`, escribe el `.workspace/agent.json` a partir de él
    (normalizado). NO borra la carpeta vieja (doctor Fase 5d lo hace cuando ya
    hay `.workspace/`). Idempotente, atómico, falla-suave. Devuelve
    (migrado: bool, name|error|"")."""
    base = os.path.abspath(os.path.expanduser(brain or ""))
    canonical = os.path.join(base, WORKSPACE_SUBDIR, "agent.json")
    old = os.path.join(base, LEGACY_SUBDIR, "agent.json")
    if os.path.isfile(canonical):
        return False, ""                       # ya está en el schema nuevo — `.workspace/` gana
    if not os.path.isfile(old):
        return False, ""                       # nada legacy que migrar
    defn = _normalize_definition(_read_json(old))
    if not defn:
        return False, "%s ilegible o vacío" % old
    # Dato histórico PERSISTIDO en el agent.json: de qué ruta vino. Conserva su
    # valor original (lo genera legacy.py) — no se reescribe con el nombre nuevo.
    defn.setdefault("_migrated_from", legacy.AGENT_JSON_REL)
    tmp = canonical + ".tmp-%d" % os.getpid()
    try:
        os.makedirs(os.path.dirname(canonical), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(defn, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, canonical)
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False, str(e)
    return True, str(defn.get("name", "")).strip().lower()


# ── escritura (atómica + idempotente) ───────────────────────────────────────
def _write_local(data):
    os.makedirs(_workspace_dir(), exist_ok=True)
    path = local_path()
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def add(name, brain):
    """Registra (o actualiza) un agente cargado. Idempotente: mismo name →
    actualiza su brain. Devuelve (ok, error|""). Valida name y que el brain
    exista como carpeta."""
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        return False, _t("agentsreg.err.bad_name",
                         "nombre inválido: {name} (usa minúsculas, dígitos, - o _)",
                         name=repr(name))
    brain = os.path.abspath(os.path.expanduser((brain or "").strip()))
    if not os.path.isdir(brain):
        return False, _t("agentsreg.err.no_brain_dir",
                         "la carpeta del cerebro no existe: {path}", path=brain)
    data = read_local()
    ags = [a for a in data.get("agents", [])
           if str(a.get("name", "")).strip().lower() != name]
    ags.append({"name": name, "brain": brain})
    data["agents"] = ags
    if not _write_local(data):
        return False, "no se pudo escribir %s" % local_path()
    return True, ""


def remove(name):
    """Quita un agente del registro per-máquina (NO toca su cerebro). Devuelve
    (ok, error|""). Quitar algo inexistente es éxito idempotente."""
    name = (name or "").strip().lower()
    data = read_local()
    before = len(data.get("agents", []))
    data["agents"] = [a for a in data.get("agents", [])
                      if str(a.get("name", "")).strip().lower() != name]
    if len(data["agents"]) == before:
        return True, ""        # no estaba → idempotente
    if not _write_local(data):
        return False, "no se pudo escribir %s" % local_path()
    return True, ""


# ── auto-descubrimiento de cerebros (Z03 · U03) ──────────────────────────────
# Con el harness distribuido VACÍO nadie debería registrar a mano cada cerebro.
# discover() escanea ubicaciones CONOCIDAS de forma ACOTADA y CANCELABLE:
#   · padre del checkout · raíz del drive del checkout (Windows, p.ej. C:\) ·
#     HOME · Desktop/Documents (+ OneDrive) · ~/Obsidian · vaults de obsidian.json
#     · carpeta elegida por el socio;
#   · profundidad 0-2 por raíz, tope de entradas y de tiempo, `should_cancel`;
#   · JAMÁS recorre todo el disco.
# Marcador canónico `<brain>/.workspace/agent.json`; legado: el de la instalación anterior
# (NO el fallback de raíz: un `agent.json` suelto daría falsos positivos).
# Devuelve CANDIDATOS: nunca registra en silencio. Registrar es
# `discover_and_register` (explícito) y reparar una ruta rota es `relocate`.
# Índice por máquina `~/.claude/workspace/brains.index.json` (ruta, nombre,
# mtime de la def, última validación) para no re-escanear en cada arranque.
#
# SEAM de tests (hermeticidad, Z23): env WORKSPACE_DISCOVERY_ROOTS (separada por
# os.pathsep) REEMPLAZA las raíces por defecto — vacía = ninguna. TempHomeCase
# la fija vacía: ningún test escanea el disco real.
import time

DISCOVERY_ROOTS_ENV = "WORKSPACE_DISCOVERY_ROOTS"
SCAN_MAX_ENTRIES = 4000          # tope duro de carpetas inspeccionadas
SCAN_TIME_BUDGET = 3.0           # segundos
INDEX_TTL = 24 * 3600            # el índice evita re-escanear durante un día
MARKER_WORKSPACE = "workspace"
# Valor PERSISTIDO en brains.index.json (y que una versión anterior relee):
# conserva el literal viejo, que vive en legacy.py.
MARKER_LEGACY = legacy.MARKER
MARKER_FOLDER = "folder"         # sin def: coincide el NOMBRE de carpeta del committeado
# carpetas que nunca son cerebros y cuestan caro al listar (sobre todo en C:\)
_SKIP_DIRS = frozenset(x.lower() for x in (
    "node_modules", "$recycle.bin", "system volume information", "windows",
    "program files", "program files (x86)", "programdata", "appdata",
    "recovery", "perflogs", "library", "applications", "__pycache__"))


def _obsidian_vault_paths():
    """Rutas de vaults registradas en Obsidian (lo más fiable; los cerebros son
    vaults). Falla-suave → []."""
    home = os.path.expanduser("~")
    cands = [os.path.join(home, "Library", "Application Support", "obsidian", "obsidian.json"),
             os.path.join(home, ".config", "obsidian", "obsidian.json")]
    ap = os.environ.get("APPDATA")
    if ap:
        cands.append(os.path.join(ap, "obsidian", "obsidian.json"))
    out = []
    for c in cands:
        vaults = _read_json(c).get("vaults", {})
        if not isinstance(vaults, dict):
            continue
        for v in vaults.values():
            p = v.get("path") if isinstance(v, dict) else None
            if isinstance(p, str) and p:
                out.append(p)
    return out


def _harness_root():
    return os.path.dirname(os.path.abspath(__file__))


def default_scan_roots(root=None):
    """[(ruta, profundidad, origen)] de las ubicaciones conocidas que existen.
    Con env WORKSPACE_DISCOVERY_ROOTS definida, SOLO esas (seam de tests)."""
    env = os.environ.get(DISCOVERY_ROOTS_ENV)
    if env is not None:
        return [(p.strip(), 1, "env") for p in env.split(os.pathsep) if p.strip()]
    root = root or _harness_root()
    home = os.path.expanduser("~")
    cand = [(os.path.dirname(root), 1, "checkout")]
    if os.name == "nt":
        drive = os.path.splitdrive(root)[0]
        if drive and not drive.startswith("\\\\"):      # UNC: no listar la raíz del share
            cand.append((drive + "\\", 1, "drive"))
    cand += [(home, 1, "home"),
             (os.path.join(home, "Desktop"), 1, "desktop"),
             (os.path.join(home, "Documents"), 1, "documents"),
             (os.path.join(home, "Documents", "Obsidian"), 1, "obsidian-dir"),
             (os.path.join(home, "Obsidian"), 1, "obsidian-dir")]
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        od = os.environ.get(var)
        if od:
            cand += [(os.path.join(od, "Desktop"), 1, "onedrive"),
                     (os.path.join(od, "Documents"), 1, "onedrive")]
    cand += [(p, 0, "obsidian") for p in _obsidian_vault_paths()]
    out, seen = [], set()
    for p, d, o in cand:
        try:
            k = os.path.normcase(os.path.abspath(p))
            if k in seen or not os.path.isdir(p):
                continue
            seen.add(k)
            out.append((os.path.abspath(p), d, o))
        except Exception:
            continue
    return out


def _probe_dir(path):
    """Marcador de un posible cerebro: (def_path, marker) o ("", "")."""
    canonical = os.path.join(path, WORKSPACE_SUBDIR, "agent.json")
    if os.path.isfile(canonical):
        return canonical, MARKER_WORKSPACE
    old = os.path.join(path, LEGACY_SUBDIR, "agent.json")
    if os.path.isfile(old):
        return old, MARKER_LEGACY
    return "", ""


def _mtime(p):
    try:
        return os.stat(p).st_mtime
    except OSError:
        return 0


def scan(roots=None, extra_roots=None, chosen=None, targets=None,
         max_entries=SCAN_MAX_ENTRIES, time_budget=SCAN_TIME_BUDGET,
         should_cancel=None, root=None):
    """Escaneo ACOTADO. NO escribe nada. Devuelve dict:
      found    [{name, brain, marker, legacy_install, def_path, def_mtime}]
      invalid  [{brain, def_path, error}]  def corrupta / nombre inválido / sin permiso
      denied   [ruta]   carpetas sin permiso de listar
      folders  [{brain, basename}]  carpetas cuyo nombre está en `targets`
      truncated / cancelled / elapsed / roots
    `roots`   [(ruta, profundidad)] o [ruta] — None = default_scan_roots().
    `extra_roots` rutas adicionales (profundidad 1) · `chosen` carpeta elegida
    (profundidad 2) · `targets` nombres de carpeta a reportar aunque no tengan
    definición (cerebros committeados reubicados)."""
    t0 = time.monotonic()
    base = default_scan_roots(root) if roots is None else [
        (tuple(r) if isinstance(r, (tuple, list)) else (r, 1)) for r in roots]
    plan = [(r[0], int(r[1]) if len(r) > 1 else 1) for r in base]
    plan += [(r, 1) for r in (extra_roots or [])]
    if chosen:
        plan.append((chosen, 2))
    tg = {str(t).lower() for t in (targets or ()) if t}
    res = {"found": [], "invalid": [], "denied": [], "folders": [],
           "truncated": False, "cancelled": False, "elapsed": 0.0,
           "roots": [p for p, _ in plan]}
    seen = set()
    count = [0]

    def stop():
        if should_cancel is not None:
            try:
                if should_cancel():
                    res["cancelled"] = True
                    return True
            except Exception:
                pass
        if count[0] >= max_entries or (time.monotonic() - t0) > time_budget:
            res["truncated"] = True
            return True
        return False

    def visit(path, depth):
        if res["cancelled"] or res["truncated"] or stop():
            return
        try:
            rp = os.path.normcase(os.path.realpath(path))
        except Exception:
            return
        if rp in seen:
            return
        seen.add(rp)
        count[0] += 1
        try:
            if not os.path.isdir(path):
                return
        except Exception:
            return
        bn = os.path.basename(os.path.normpath(path))
        if tg and bn.lower() in tg:
            res["folders"].append({"brain": os.path.abspath(path), "basename": bn})
        defpath, marker = _probe_dir(path)
        if defpath:
            try:
                with open(defpath, encoding="utf-8") as fh:
                    d = json.load(fh)
                if not isinstance(d, dict):
                    raise ValueError("no es un objeto JSON")
                name = str(d.get("name", "")).strip().lower()
                if not NAME_RE.match(name):
                    res["invalid"].append({"brain": os.path.abspath(path), "def_path": defpath,
                                           "error": "nombre inválido: %r" % name})
                else:
                    res["found"].append({
                        "name": name, "brain": os.path.abspath(path), "marker": marker,
                        "legacy_install": marker == MARKER_LEGACY, "def_path": defpath,
                        "def_mtime": _mtime(defpath)})
            except PermissionError:
                res["invalid"].append({"brain": os.path.abspath(path), "def_path": defpath,
                                       "error": "sin permiso de lectura"})
            except Exception as e:
                res["invalid"].append({"brain": os.path.abspath(path), "def_path": defpath,
                                       "error": "definición ilegible (%s)" % type(e).__name__})
            return                        # un cerebro no se recorre por dentro
        if depth <= 0:
            return
        try:
            names = sorted(os.listdir(path))
        except PermissionError:
            res["denied"].append(os.path.abspath(path))
            return
        except OSError:
            return
        for nm in names:
            if nm.startswith(".") or nm.lower() in _SKIP_DIRS:
                continue
            visit(os.path.join(path, nm), depth - 1)
            if res["cancelled"] or res["truncated"]:
                return

    for p, d in plan:
        visit(p, d)
        if res["cancelled"] or res["truncated"]:
            break
    res["elapsed"] = round(time.monotonic() - t0, 3)
    return res


# ── índice local por máquina ─────────────────────────────────────────────────
def index_path():
    return os.path.join(_workspace_dir(), "brains.index.json")


def write_index(scan_res):
    """Persiste el resultado de un escaneo (atómico, falla-suave → False)."""
    now = time.time()
    brains = [{"path": f["brain"], "name": f["name"], "marker": f["marker"],
               "def_mtime": f.get("def_mtime", 0), "validated_at": now}
              for f in scan_res.get("found", [])]
    brains += [{"path": f["brain"], "name": "", "marker": MARKER_FOLDER,
                "basename": f["basename"], "def_mtime": 0, "validated_at": now}
               for f in scan_res.get("folders", [])]
    doc = {"version": 1, "scanned_at": now, "roots": scan_res.get("roots", []),
           "truncated": bool(scan_res.get("truncated")), "entries": brains}
    path = index_path()
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def load_index(max_age=INDEX_TTL):
    """Índice re-validado barato (stat de cada entrada) con la forma de `scan`,
    o None si no hay / está viejo / corrupto. Entradas que ya no validan
    (carpeta movida, def cambiada) se descartan: el índice es caché, no verdad."""
    data = _read_json(index_path())
    if not data:
        return None
    try:
        ts = float(data.get("scanned_at", 0))
    except Exception:
        return None
    if max_age is not None and time.time() - ts > max_age:
        return None
    res = {"found": [], "invalid": [], "denied": [], "folders": [],
           "truncated": bool(data.get("truncated")), "cancelled": False,
           "elapsed": 0.0, "roots": data.get("roots", []), "from_index": True}
    for b in data.get("entries") or []:
        if not isinstance(b, dict) or not isinstance(b.get("path"), str):
            continue
        p = b["path"]
        if b.get("marker") == MARKER_FOLDER:
            if os.path.isdir(p):
                res["folders"].append({"brain": p, "basename": b.get("basename")
                                       or os.path.basename(os.path.normpath(p))})
            continue
        defpath, marker = _probe_dir(p)
        if not defpath:
            continue
        name = str(b.get("name", "")).strip().lower()
        if _mtime(defpath) != b.get("def_mtime"):
            name = str(_read_json(defpath).get("name", "")).strip().lower()
        if not NAME_RE.match(name):
            continue
        res["found"].append({"name": name, "brain": p, "marker": marker,
                             "legacy_install": marker == MARKER_LEGACY,
                             "def_path": defpath, "def_mtime": _mtime(defpath)})
    return res


# ── API pública de descubrimiento ────────────────────────────────────────────
def discover(extra_roots=None, roots=None, chosen=None, should_cancel=None,
             max_entries=SCAN_MAX_ENTRIES, time_budget=SCAN_TIME_BUDGET):
    """[{name, brain, legacy_install, marker}] de cerebros auto-descriptivos
    (escaneo acotado; ver `scan`). NO registra. Dedup por nombre (primero gana)
    y por carpeta; una colisión de nombres se AVISA por stderr (no se traga).
    Actualiza el índice local (caché). Falla-suave SIEMPRE → en el peor caso []."""
    try:
        r = scan(roots=roots, extra_roots=extra_roots, chosen=chosen,
                 should_cancel=should_cancel, max_entries=max_entries,
                 time_budget=time_budget)
    except Exception:
        return []
    if not r.get("cancelled"):
        write_index(r)
    found = {}
    for f in r["found"]:
        name = f["name"]
        if name in found:
            if os.path.normcase(f["brain"]) != os.path.normcase(found[name]["brain"]):
                import sys
                sys.stderr.write(
                    _t("addagent.discover.warn_prefix", "WORKSPACE · aviso: ")
                    + _t("addagent.discover.warn_dup",
                         "dos cerebros con nombre '{n}' — uso {a}, ignoro {b} "
                         "(renombra uno o cárgalo explícito)",
                         n=name, a=found[name]["brain"], b=f["brain"])
                    + "\n")
            continue
        found[name] = {"name": name, "brain": f["brain"],
                       "legacy_install": f["legacy_install"], "marker": f["marker"]}
    return list(found.values())


def _registered_states():
    """{name: {res, loaded, target, aliases}} del registry efectivo, resueltos
    por el resolver canónico (brain_resolver). Falla-suave → {}."""
    out = {}
    try:
        import dispatch
        import brain_resolver
        reg = dispatch.load_registry()
    except Exception:
        return out
    for e in reg.get("agents") or []:
        if not isinstance(e, dict) or not isinstance(e.get("name"), str):
            continue
        n = e["name"].strip().lower()
        try:
            cfg = dispatch.load_agent_cfg(e)
        except Exception:
            cfg = {}
        res = brain_resolver.resolve(n, cfg, e)
        raw = res.get("raw") or ""
        target = os.path.basename(os.path.normpath(raw)) if raw else ""
        al = e.get("aliases") or []
        out[n] = {"res": res, "loaded": bool(e.get("_loaded")), "target": target,
                  "aliases": [str(x).lower() for x in al if isinstance(x, str)]
                  if isinstance(al, (list, tuple)) else []}
    return out


def _same(a, b):
    try:
        import brain_resolver
        return brain_resolver.same_path(a, b)
    except Exception:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _suggest(regs, scan_res):
    """Sugerencias de REPARACIÓN para agentes registrados con cerebro roto."""
    out = []
    for n, st in sorted(regs.items()):
        res = st["res"]
        if res.get("exists"):
            continue
        opts = [f for f in scan_res.get("found", []) if f["name"] == n]
        if not opts and st["target"]:
            tl = st["target"].lower()
            opts = [{"name": n, "brain": f["brain"], "marker": MARKER_FOLDER}
                    for f in scan_res.get("folders", []) if f["basename"].lower() == tl]
        uniq = []
        for o in opts:
            if not any(_same(o["brain"], u["brain"]) for u in uniq):
                uniq.append(o)
        if not uniq:
            continue
        cur = res.get("path") or "(sin ruta)"
        found = uniq[0]["brain"] if len(uniq) == 1 else ""
        if found:
            msg = "%s registrado en %s (no existe) → encontrado en %s" % (n, cur, found)
        else:
            msg = "%s registrado en %s (no existe) → %d candidatos: %s" % (
                n, cur, len(uniq), " · ".join(u["brain"] for u in uniq))
        out.append({"name": n, "current": res.get("path", ""), "source": res.get("source"),
                    "found": found, "marker": uniq[0]["marker"] if found else "",
                    "options": [u["brain"] for u in uniq], "message": msg})
    return out


def _empty_scan():
    return {"found": [], "folders": [], "invalid": [], "denied": [],
            "truncated": False, "cancelled": False, "elapsed": 0.0, "roots": []}


def repair_suggestions(scan_mode="auto", regs=None, persist=True, **kw):
    """[{name, current, source, found, marker, options, message}] para cada
    agente REGISTRADO cuyo cerebro no existe y que el discovery encontró en
    otra ruta (por marcador con su nombre o, para committeados sin definición,
    por nombre de carpeta). scan_mode: "auto" (índice fresco o escaneo
    acotado), "scan" (escanear siempre), "index" (solo índice; jamás toca el
    disco más allá de stat). persist=False → no actualiza el índice (modo
    diagnóstico de solo lectura, p.ej. doctor --check). Falla-suave → []."""
    try:
        regs = regs if regs is not None else _registered_states()
        if all(st["res"].get("exists") for st in regs.values()):
            return []
        r = None
        if scan_mode in ("auto", "index"):
            r = load_index()
            if r is None and scan_mode == "index":
                r = _empty_scan()
        if r is None:
            targets = {st["target"] for st in regs.values() if st["target"]}
            r = scan(targets=targets, **kw)
            if persist and not r.get("cancelled"):
                write_index(r)
        return _suggest(regs, r)
    except Exception:
        return []


def candidates(roots=None, extra_roots=None, chosen=None, should_cancel=None,
               max_entries=SCAN_MAX_ENTRIES, time_budget=SCAN_TIME_BUDGET):
    """Informe COMPLETO de discovery, SIN registrar nada:
      candidates  [{name, brain, marker, legacy_install, status, registered_brain,
                    registered_source, duplicate_of}]
                  status: new | registered | repair | elsewhere
      suggestions sugerencias de reparación del mismo escaneo
      duplicates  {name: [rutas]} misma def en 2+ rutas
      invalid / denied / truncated / cancelled / elapsed / roots"""
    regs = _registered_states()
    targets = {st["target"] for st in regs.values() if st["target"]}
    r = scan(roots=roots, extra_roots=extra_roots, chosen=chosen, targets=targets,
             should_cancel=should_cancel, max_entries=max_entries,
             time_budget=time_budget)
    if not r.get("cancelled"):
        write_index(r)
    by_name = {}
    for f in r["found"]:
        by_name.setdefault(f["name"], []).append(f["brain"])
    dups = {n: ps for n, ps in by_name.items() if len(ps) > 1}
    out = []
    for f in r["found"]:
        c = dict(f)
        st = regs.get(f["name"])
        c["registered_brain"] = st["res"].get("path", "") if st else ""
        c["registered_source"] = st["res"].get("source", "") if st else ""
        if not st:
            c["status"] = "new"
        elif _same(f["brain"], st["res"].get("path", "")):
            c["status"] = "registered"
        elif not st["res"].get("exists"):
            c["status"] = "repair"
        else:
            c["status"] = "elsewhere"
        c["duplicate_of"] = [p for p in dups.get(f["name"], []) if p != f["brain"]]
        out.append(c)
    return {"candidates": out, "suggestions": _suggest(regs, r), "duplicates": dups,
            "invalid": r["invalid"], "denied": r["denied"],
            "truncated": r["truncated"], "cancelled": r["cancelled"],
            "elapsed": r["elapsed"], "roots": r["roots"]}


def discover_and_register(extra_roots=None, names=None, roots=None):
    """Registro EXPLÍCITO (lo pide el socio: `discover --register`). Solo
    registra candidatos NUEVOS (no registrados), sin nombre duplicado y — si
    `names` — solo los elegidos. Un agente registrado con cerebro roto NO se
    re-registra aquí: eso es `relocate` (reparación). Devuelve [nombres]."""
    rep = candidates(roots=roots, extra_roots=extra_roots)
    want = {str(n).strip().lower() for n in names} if names else None
    added = []
    for c in rep["candidates"]:
        n = c["name"]
        if c["status"] != "new" or n in rep["duplicates"] or n in added:
            continue
        if want is not None and n not in want:
            continue
        if c.get("legacy_install"):                # instalación anterior → migra antes de registrar
            migrate_legacy(c["brain"])            # falla-suave: queda igual si no se pudo
        ok, _ = add(n, c["brain"])
        if ok:
            added.append(n)
    return added


def relocate(name, new_path, force=False):
    """Repara la ruta del cerebro de un agente REGISTRADO apuntándola a
    `new_path`, SIN tocar el cerebro. Valida: carpeta existente y legible, y
    que sea SU cerebro (definición con su nombre/alias, o — committeado sin
    definición — mismo nombre de carpeta que su `brain`; `force` salta esto).
    Escribe el override por máquina que GANA en la resolución:
      · ya hay override en paths.local.json → se actualiza ese;
      · agente cargado → agents.local.json (agentsreg.add);
      · committeado → paths.local.json brains.<name>.
    Atómico. Devuelve (ok, error|"", archivo_escrito|"")."""
    import brain_resolver
    name = (name or "").strip().lower()
    path = os.path.abspath(os.path.expanduser((new_path or "").strip()))
    regs = _registered_states()
    st = regs.get(name)
    if st is None:
        return False, _t("agentsreg.err.not_registered",
                         "no hay agente '{name}' registrado (para uno nuevo usa add)",
                         name=name), ""
    if not os.path.isdir(path):
        return False, _t("agentsreg.err.no_dir", "la carpeta no existe: {path}",
                         path=path), ""
    try:
        os.listdir(path)
    except OSError:
        return False, _t("agentsreg.err.no_read", "sin permiso de lectura: {path}",
                         path=path), ""
    defpath, _kind = brain_resolver.definition_of(path)
    if defpath:
        dn = brain_resolver.definition_name(defpath)
        if dn and dn != name and dn not in st["aliases"] and not force:
            return False, _t("agentsreg.err.other_agent",
                             "{path} declara al agente '{other}', no a '{name}' "
                             "(usa --force si es intencional)",
                             path=defpath, other=dn, name=name), ""
    elif not force:
        tgt = (st["target"] or "").lower()
        if not tgt or os.path.basename(os.path.normpath(path)).lower() != tgt:
            return False, _t("agentsreg.err.not_a_brain",
                             "{path} no tiene .workspace/agent.json ni se llama "
                             "como el cerebro declarado ({target}) — usa --force "
                             "si es intencional",
                             path=path, target=st["target"] or "?"), ""
    try:
        has_ov = name in brain_resolver.brain_overrides()
    except Exception:
        has_ov = False
    if has_ov or not st["loaded"]:
        ok, err = brain_resolver.set_override(name, path)
        dest = brain_resolver.paths_local()
    else:
        ok, err = add(name, path)
        dest = local_path()
    if ok:
        try:
            import agent_state
            agent_state.invalidate()
        except Exception:
            pass
    return ok, err, (dest if ok else "")


def _print_report(rep):
    tag = {"new": "nuevo", "registered": "ya registrado", "repair": "REPARA ruta rota",
           "elsewhere": "registrado en otra ruta"}
    if not rep["candidates"]:
        print("agentsreg: no encontré cerebros con .workspace/agent.json ni el de la "
              "instalación anterior")
    for c in rep["candidates"]:
        extra = " · de la instalación anterior" if c.get("legacy_install") else ""
        if c["duplicate_of"]:
            extra += " · DUPLICADO (también en %s)" % ", ".join(c["duplicate_of"])
        print("  %-12s → %s  [%s%s]" % (c["name"], c["brain"],
                                       tag.get(c["status"], c["status"]), extra))
    for s in rep["suggestions"]:
        print("  ⚑ " + s["message"])
        if s["found"]:
            print("      reparar: python agentsreg.py relocate %s \"%s\"" % (s["name"], s["found"]))
    for i in rep["invalid"]:
        print("  ! %s: %s" % (i["brain"], i["error"]))
    for d in rep["denied"]:
        print("  ! sin permiso para listar: %s" % d)
    if rep["truncated"]:
        print("  · búsqueda acotada: se alcanzó el tope de carpetas/tiempo — "
              "elige la carpeta con --root <ruta>")
    print("  (nada se registró — `discover --register` registra los nuevos; "
          "`relocate` repara rutas)")


# ── CLI mínimo ───────────────────────────────────────────────────────────────
def main(argv=None):
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "list"
    if cmd in ("list", "ls"):
        ags = agents()
        if not ags:
            print("agentsreg: (vacío — sin agentes cargados en esta máquina)")
        for a in ags:
            tag = load_definition(a["brain"]).get("tagline", "")
            print("  %-12s → %s%s" % (a["name"], a["brain"],
                                      ("  · " + tag) if tag else ""))
        return 0
    if cmd == "add" and len(args) >= 3:
        ok, err = add(args[1], args[2])
        print("ok" if ok else "error: " + err)
        return 0 if ok else 1
    if cmd in ("remove", "rm") and len(args) >= 2:
        ok, err = remove(args[1])
        print("ok" if ok else "error: " + err)
        return 0 if ok else 1
    if cmd in ("discover", "descubrir"):
        register = ("--register" in args) or ("-r" in args)
        roots = [args[i + 1] for i, x in enumerate(args[:-1]) if x == "--root"]
        if register:
            added = discover_and_register(extra_roots=roots or None)
            if added:
                print("registrados: " + ", ".join(added))
            else:
                print("agentsreg: nada nuevo que registrar (ya estaban, duplicados o no hay cerebros)")
            return 0
        rep = candidates(chosen=roots[0] if roots else None,
                         extra_roots=roots[1:] or None)
        if "--json" in args:
            print(json.dumps(rep, ensure_ascii=False, indent=2))
        else:
            _print_report(rep)
        return 0
    if cmd in ("relocate", "reubicar") and len(args) >= 3:
        ok, err, dest = relocate(args[1], args[2], force="--force" in args)
        print(("ok → " + dest) if ok else "error: " + err)
        return 0 if ok else 1
    print("uso: agentsreg.py list | add <name> <brain> | remove <name> | "
          "discover [--root <ruta>] [--json] [--register] | relocate <name> <ruta> [--force]")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
