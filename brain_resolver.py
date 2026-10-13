#!/usr/bin/env python3
"""WORKSPACE · brain_resolver — resolver CANÓNICO ÚNICO de la ruta del cerebro (Z20).

Antes cada consumidor re-derivaba la ruta a su manera (dispatch, doctor fase 2
con «carpeta hermana», install.find_brain, agent_state…) y discrepaban: doctor
marcaba FALTANTE un cerebro registrado por ruta absoluta fuera del repo que el
dispatcher resolvía y abría sin problema (W-F02). Ahora hay UNA función:

    resolve(name, cfg, entry) → Resolution {path, source, raw, exists,
                                            readable, definition, …}

Precedencia (de más local a más portable):
  1. override por máquina   ~/.claude/workspace/paths.local.json → brains.<name>
                            (legacy: <ROOT>/paths.local.json)       source="override"
  2. registro por máquina   agents.local.json (agente CARGADO, ruta absoluta;
                            dispatch.load_agent_cfg la deja en cfg["brain"])
                                                                   source="loaded"
  3. definición committeada campo "brain" del agent.json, relativo a ROOT
                            (o absoluto/«~/…», que se expande)     source="committed"
  Sin nada de lo anterior → path="" source="none".

La parte de ruta es PURA (`join_brain`, parametrizable con ntpath/posixpath)
para probar C:\\, UNC \\\\server\\share, espacios/acentos y «~/» sin depender del
SO donde corre el test. Las sondas de disco (existe/legible/definición) solo se
hacen con el os.path nativo.

Prevención (Z23): ningún módulo del producto debe resolver la ruta del cerebro
por su cuenta (`os.path.join(ROOT, raw)` y similares) — tests/test_brain_resolver
lo verifica estáticamente. `dispatch.resolve_brain` es una fachada de este módulo.

Stdlib puro, falla-suave en lectores.
"""
import json
import os
import sys

import legacy

_HERE = os.path.dirname(os.path.abspath(__file__))

SOURCE_OVERRIDE = "override"
SOURCE_LOADED = "loaded"
SOURCE_COMMITTED = "committed"
SOURCE_NONE = "none"
SOURCES = (SOURCE_OVERRIDE, SOURCE_LOADED, SOURCE_COMMITTED, SOURCE_NONE)

SOURCE_LABELS = {
    SOURCE_OVERRIDE: "override por máquina (paths.local.json)",
    SOURCE_LOADED: "registro por máquina (agents.local.json)",
    SOURCE_COMMITTED: "definición committeada (relativa al harness)",
    SOURCE_NONE: "sin ruta declarada",
}

# marcadores de definición, en orden de preferencia
DEF_WORKSPACE = "workspace"      # <brain>/.workspace/agent.json (canónico)
DEF_ROOT = "root"                # <brain>/agent.json (fallback de robustez)
DEF_LEGACY = legacy.MARKER       # <brain>/<subcarpeta vieja>/agent.json (instalación anterior)


def _t(key, default, **kw):
    """i18n falla-suave (patrón de updater/migrate): idioma activo; sin
    catálogo/clave → el `default` español."""
    try:
        import i18n
        s = i18n.t(key, **kw)
        if s != key:
            return s
    except Exception:
        pass
    try:
        return default.format(**kw) if kw else default
    except Exception:
        return default


def default_root():
    """Raíz del harness. Si `dispatch` ya está importado, se respeta SU ROOT
    (los tests lo parchean para simular otra instalación)."""
    d = sys.modules.get("dispatch")
    r = getattr(d, "ROOT", None) if d is not None else None
    return r if isinstance(r, str) and r else _HERE


# ── stores por máquina ────────────────────────────────────────────────────────
def paths_local():
    """~/.claude/workspace/paths.local.json (per-máquina, fuera del vault)."""
    try:
        import paths
    except ImportError:   # cargado por ruta sin la raíz en sys.path
        if _HERE not in sys.path:
            sys.path.append(_HERE)
        import paths
    return os.path.join(paths.state_dir(), "paths.local.json")


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def local_overrides(root=None):
    """Doc completo de paths.local.json (nuevo per-máquina · legacy en ROOT).
    Falla-suave → {}."""
    root = root or default_root()
    for p in (paths_local(), os.path.join(root, "paths.local.json")):
        if os.path.exists(p):
            try:
                data = _read_json(p)
                return data if isinstance(data, dict) else {}
            except Exception:
                pass
    return {}


def brain_overrides(root=None):
    b = local_overrides(root).get("brains", {})
    return b if isinstance(b, dict) else {}


# ── parte PURA de ruta ────────────────────────────────────────────────────────
def join_brain(raw, root, pathmod=None):
    """Ruta efectiva de un campo `brain` crudo. Pura respecto al disco:
    expande «~», respeta absolutas (drive, UNC, POSIX) y une relativas a `root`.
    `pathmod` = ntpath/posixpath para probar otra plataforma (default os.path)."""
    pm = pathmod or os.path
    raw = str(raw or "").strip()
    if not raw:
        return ""
    raw = pm.expanduser(raw)
    if pm.isabs(raw):
        return pm.normpath(raw)
    if pm is os.path:
        return os.path.abspath(os.path.join(root, raw))
    return pm.normpath(pm.join(root, raw))


def _override_path(raw, pathmod=None):
    pm = pathmod or os.path
    raw = pm.expanduser(str(raw or "").strip())
    if not raw:
        return ""
    if pm is os.path:
        return os.path.abspath(raw)
    return pm.normpath(raw)


def same_path(a, b):
    """Igualdad de rutas tolerante a mayúsculas (Windows), separadores y ~."""
    if not a or not b:
        return False
    def n(p):
        return os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(p))))
    try:
        return n(a) == n(b)
    except Exception:
        return False


# ── definición del cerebro ───────────────────────────────────────────────────
def definition_of(brain):
    """(ruta, tipo) de la definición presente en `brain`, o ("", "")."""
    if not brain:
        return "", ""
    for kind, rel in ((DEF_WORKSPACE, (".workspace", "agent.json")),
                      (DEF_ROOT, ("agent.json",)),
                      (DEF_LEGACY, (legacy.BRAIN_SUBDIR, "agent.json"))):
        p = os.path.join(brain, *rel)
        if os.path.isfile(p):
            return p, kind
    return "", ""


def definition_name(def_path):
    """`name` declarado en una definición; "" si falta/corrupta."""
    try:
        d = _read_json(def_path)
    except Exception:
        return ""
    if not isinstance(d, dict):
        return ""
    return str(d.get("name", "") or "").strip().lower()


class Resolution(dict):
    """Resultado del resolver. dict (serializable, .get) con atributos."""

    @property
    def path(self):
        return self.get("path", "")

    @property
    def source(self):
        return self.get("source", SOURCE_NONE)

    @property
    def ok(self):
        return bool(self.get("exists") and self.get("readable"))


def _readable(path):
    try:
        os.listdir(path)
        return True
    except OSError:
        return False


def resolve(name, cfg=None, entry=None, root=None, overrides=None,
            pathmod=None, probe=True):
    """LA resolución de la ruta del cerebro de un agente.

    name      nombre del agente (clave de overrides).
    cfg       config del agente (dispatch.load_agent_cfg) — trae "brain".
    entry     entrada del registry efectivo (marca `_loaded` para cargados).
    root      raíz del harness para relativas (default: dispatch.ROOT).
    overrides dict brains.<name> ya leído (None → paths.local.json).
    pathmod   ntpath/posixpath para pruebas puras; con uno no nativo no se
              sondea el disco.
    probe     False → solo ruta y fuente (sin stat).
    """
    pm = pathmod or os.path
    cfg = cfg if isinstance(cfg, dict) else {}
    entry = entry if isinstance(entry, dict) else {}
    root = root or default_root()
    name = str(name or "").strip()
    ov = overrides if overrides is not None else brain_overrides(root)
    res = Resolution(name=name, path="", source=SOURCE_NONE, raw="",
                     exists=False, readable=False, definition="",
                     definition_kind="", error="")
    ovv = ov.get(name) if isinstance(ov, dict) else None
    if isinstance(ovv, str) and ovv.strip():
        res["raw"] = ovv
        res["path"] = _override_path(ovv, pm)
        res["source"] = SOURCE_OVERRIDE
    else:
        raw = cfg.get("brain") or entry.get("brain") or ""
        if isinstance(raw, str) and raw.strip():
            res["raw"] = raw
            res["path"] = join_brain(raw, root, pm)
            res["source"] = (SOURCE_LOADED if entry.get("_loaded") or cfg.get("_loaded")
                             else SOURCE_COMMITTED)
    if not res["path"]:
        res["error"] = _t("doctor.resolver.resolve.1", "sin ruta de cerebro declarada")
        return res
    if not probe or pm is not os.path:
        return res
    try:
        res["exists"] = os.path.isdir(res["path"])
        if not res["exists"]:
            res["error"] = _t("doctor.resolver.not_exists", "no existe: %s") % res["path"]
            return res
        res["readable"] = _readable(res["path"])
        if not res["readable"]:
            res["error"] = _t("doctor.resolver.resolve.2", "sin permiso de lectura: %s") % res["path"]
            return res
        res["definition"], res["definition_kind"] = definition_of(res["path"])
    except Exception as e:     # falla-suave: nunca levanta hacia el caller
        res["error"] = "%s: %s" % (type(e).__name__, e)
    return res


def resolve_path(name, cfg=None, root=None):
    """Solo la ruta (lo que devuelve dispatch.resolve_brain)."""
    return resolve(name, cfg, root=root, probe=False).path


def resolve_agent(name):
    """Resolución por NOMBRE contra el registry efectivo. None si no existe."""
    try:
        import dispatch
        entry = dispatch.find_agent(name)
        if not entry:
            return None
        cfg = dispatch.load_agent_cfg(entry)
    except Exception:
        return None
    return resolve(entry.get("name", name), cfg, entry)


# ── escritura del override por máquina (atómica, preserva claves) ─────────────
def set_override(name, path):
    """Escribe brains.<name> = path en ~/.claude/workspace/paths.local.json.
    Atómico (tmp + os.replace), preserva el resto del doc. (ok, error)."""
    p = paths_local()
    try:
        cur = _read_json(p) if os.path.exists(p) else {}
    except Exception as e:
        return False, _t("doctor.resolver.set_override.1", "paths.local.json ilegible (%s) — no lo sobrescribo") % e
    if not isinstance(cur, dict):
        return False, _t("doctor.resolver.set_override.2", "paths.local.json no es un objeto — no lo sobrescribo")
    brains = cur.get("brains")
    if not isinstance(brains, dict):
        brains = {}
    brains[name] = path
    cur["brains"] = brains
    tmp = p + ".tmp-%d" % os.getpid()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cur, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, p)
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False, _t("doctor.resolver.set_override.3", "no se pudo escribir %s: %s") % (p, e)
    return True, ""
