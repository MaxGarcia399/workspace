#!/usr/bin/env python3
"""WORKSPACE · agent_state — estado de RUNTIME compartido de los agentes (U12/Z12-Z13).

Una sola fuente por perfil/máquina para TODAS las vistas que listan agentes
(hub, Agentes/gestión, Tonos, Settings/Config, Motores, Sesiones, Dev). Ninguna
vista mantiene su propio roster ni decide "listo" por presencia en una lista.

Deriva de: registry efectivo (dispatch.load_registry = committeado + cargados
per-máquina), definiciones `<brain>/.workspace/agent.json`, overrides locales
(paths.local.json), settings (binding de motor per-máquina, agentes ocultos) y
disponibilidad barata de motores (engine cargable + binarios en PATH — sin
login/red: eso es un probe aparte, con timeout, que la vista pide explícito).

Contrato (ver research/agent-state-contract.md):
  · `snapshot()` → Snapshot con `revision` (hash de la FIRMA de los stores:
    mtime/size de registry, agents.local.json, paths.local.json, settings y
    cada definición/cerebro). Si la firma no cambió, devuelve el cache.
  · Cada AgentState separa: registrado · cerebro (ruta/existe/legible) ·
    definición (presente/válida) · motor (adapter/binarios) · oculto. `status`
    es UNO de STATUSES; `launchable` solo si status == "ready"; `openable`
    también con el motor caído (ENGINE_STATUSES: al abrir se elige otro).
  · `brain_source` (override|loaded|committed|none) viene del resolver
    canónico (brain_resolver); en BRAIN_MISSING, `suggested_brain` trae la
    ruta donde el discovery (índice/escaneo acotado) lo encontró, si hay.
  · Registro ≠ utilizable: un averiado se reporta con `cause` y `repair`; las
    vistas lo muestran para reparar, nunca lo anuncian listo.
  · Errores parciales no vacían la lista: entradas inválidas van a
    `snapshot.errors`, las válidas sobreviven. Nunca se inventan agentes.
  · `revalidate(agent_id, brain)` antes de guardar/lanzar: si el agente fue
    retirado o reemplazado (otra ruta) desde otra ventana, la acción se cancela
    — jamás se redirige al siguiente de la lista ni a GLOBAL.

Stdlib puro, falla-suave (nunca levanta hacia la vista).
"""
import hashlib
import os
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── estados (orden = gravedad; el primero que aplica gana) ────────────────────
READY = "ready"
INVALID_CONFIG = "invalid_config"      # entrada de registro/definición inválida
BRAIN_MISSING = "brain_missing"        # ruta no resuelta o no existe
BRAIN_UNREADABLE = "brain_unreadable"  # existe pero sin permiso de lectura
DEFINITION_MISSING = "definition_missing"  # cerebro sin .workspace/agent.json
ENGINE_UNKNOWN = "engine_unknown"      # el motor asignado no tiene adapter
ENGINE_MISSING = "engine_missing"      # adapter presente, binario fuera de PATH
HIDDEN = "hidden"                      # registrado y sano, oculto por el socio

STATUSES = (READY, INVALID_CONFIG, BRAIN_MISSING, BRAIN_UNREADABLE,
            DEFINITION_MISSING, ENGINE_UNKNOWN, ENGINE_MISSING, HIDDEN)

#: Averías que NO impiden ABRIR al agente: solo su motor está caído. Al abrir,
#: dispatch dice cuál y por qué y ofrece otro motor disponible — un agente
#: jamás queda bloqueado por su motor (el resto de averías sí bloquean).
ENGINE_STATUSES = (ENGINE_UNKNOWN, ENGINE_MISSING)

_LABELS = {
    "es": {
        READY: "listo",
        INVALID_CONFIG: "configuración inválida",
        BRAIN_MISSING: "cerebro no encontrado",
        BRAIN_UNREADABLE: "cerebro sin permiso de lectura",
        DEFINITION_MISSING: "cerebro sin definición (.workspace/agent.json)",
        ENGINE_UNKNOWN: "motor sin adaptador",
        ENGINE_MISSING: "motor no instalado",
        HIDDEN: "oculto",
    },
    "en": {
        READY: "ready",
        INVALID_CONFIG: "invalid configuration",
        BRAIN_MISSING: "brain not found",
        BRAIN_UNREADABLE: "brain not readable",
        DEFINITION_MISSING: "brain has no definition (.workspace/agent.json)",
        ENGINE_UNKNOWN: "engine has no adapter",
        ENGINE_MISSING: "engine not installed",
        HIDDEN: "hidden",
    },
}

_REPAIR = {
    "es": {
        INVALID_CONFIG: "Agentes › editar o quitar la entrada",
        BRAIN_MISSING: "Agentes › cambiar ruta del cerebro",
        BRAIN_UNREADABLE: "revisa permisos de la carpeta",
        DEFINITION_MISSING: "Agentes › cargar de nuevo (crea la definición)",
        ENGINE_UNKNOWN: "Agentes › elegir otro motor",
        ENGINE_MISSING: "Motores › instalar o recargar (r)",
        HIDDEN: "Agentes › mostrar",
    },
    "en": {
        INVALID_CONFIG: "Agents › edit or remove the entry",
        BRAIN_MISSING: "Agents › change brain path",
        BRAIN_UNREADABLE: "check folder permissions",
        DEFINITION_MISSING: "Agents › load again (creates the definition)",
        ENGINE_UNKNOWN: "Agents › choose another engine",
        ENGINE_MISSING: "Engines › install or reload (r)",
        HIDDEN: "Agents › show",
    },
}


def _ui_lang():
    """Idioma de la UI (i18n.lang()); falla-suave → "es"."""
    try:
        import i18n
        return i18n.lang()
    except Exception:
        return "es"


def _tr(key, es, **kw):
    """Cadena de la UI (i18n) con fallback al español inline."""
    try:
        import i18n
        s = i18n.t(key)
        if s == key:
            s = es
    except Exception:
        s = es
    try:
        return s % kw if kw else s
    except Exception:
        return s


def label(status, lang=None):
    lang = lang or _ui_lang()
    return _LABELS.get(lang, _LABELS["es"]).get(status, status)


def repair_hint(status, lang=None):
    lang = lang or _ui_lang()
    return _REPAIR.get(lang, _REPAIR["es"]).get(status, "")


class AgentState(dict):
    """Un agente tal como lo ve TODA vista. dict para que los consumidores
    existentes (que usan .get) migren sin fricción; atributos de conveniencia."""

    @property
    def launchable(self):
        return self.get("status") == READY

    @property
    def openable(self):
        """¿Se puede ABRIR desde el hub? Listo, o con el motor caído (dispatch
        ofrece otro al abrir). `launchable` sigue siendo «listo de verdad»."""
        return self.get("status") in (READY,) + ENGINE_STATUSES

    @property
    def id(self):
        return self.get("id", "")


class Snapshot(object):
    def __init__(self, agents, errors, revision, planned=()):
        self.agents = list(agents)
        self.errors = list(errors)
        self.revision = revision
        self.planned = list(planned)

    # ── selectores por propósito (las vistas NO filtran a mano) ──────────────
    def registered(self, include_hidden=True):
        """Todos los agentes registrados visibles al socio (sanos y averiados).
        Para gestión (Agentes) y Tonos/preferencias."""
        return [a for a in self.agents
                if include_hidden or not a.get("hidden")]

    def for_hub(self):
        """Lo que pinta el hub: registrados no ocultos (sanos y averiados —
        el averiado se ve para repararlo, con active=False)."""
        return [a for a in self.agents if not a.get("hidden")]

    def launchable(self):
        return [a for a in self.agents if a["status"] == READY]

    def names(self, include_hidden=True):
        return [a["name"] for a in self.registered(include_hidden)]

    def find(self, name_or_id):
        k = str(name_or_id or "").strip().lower()
        for a in self.agents:
            if a["id"] == k or a["name"] == k or k in a.get("aliases", ()):
                return a
        return None


# ── firma barata de los stores (detección de cambios, también entre ventanas) ──
def _stat(path):
    try:
        st = os.stat(path)
        return (path, st.st_mtime_ns, st.st_size)
    except OSError:
        return (path, 0, -1)


def _store_paths():
    out = []
    try:
        import dispatch
        out.append(dispatch.registry_path())
        out.append(dispatch._paths_local())
        out.append(os.path.join(ROOT, "paths.local.json"))
    except Exception:
        pass
    try:
        import agentsreg
        out.append(agentsreg.local_path())
        out.append(agentsreg.index_path())   # discovery: sugerencias de reparación
    except Exception:
        pass
    try:
        import settings
        out.append(settings.store_path())
    except Exception:
        pass
    return out


def signature(brains=()):
    """Firma de los stores locales + definiciones de cada cerebro conocido.
    Barata (solo stat), sin red ni escaneo de disco."""
    parts = [_stat(p) for p in _store_paths()]
    for b in brains:
        if not b:
            continue
        parts.append(_stat(b))
        parts.append(_stat(os.path.join(b, ".workspace", "agent.json")))
        parts.append(_stat(os.path.join(b, "agent.json")))
    # PATH influye en binarios detectados (U01: recargar tras instalar)
    parts.append(("PATH", os.environ.get("PATH", ""), 0))
    h = hashlib.sha1(repr(parts).encode("utf-8", "replace")).hexdigest()
    return h[:16]


# ── construcción ──────────────────────────────────────────────────────────────
_engine_cache = {}


def _engine_status(engine_id, path_env):
    """(status|None, detail) de un motor — barato: adapter cargable + binarios
    en PATH. Cacheado por (motor, PATH). Login/cuota NO se prueban aquí."""
    key = (engine_id, path_env)
    if key in _engine_cache:
        return _engine_cache[key]
    res = (None, "")
    try:
        import harnesses
        d = harnesses.describe(engine_id, probe=False)
        if not d.get("installed"):
            res = (ENGINE_UNKNOWN, d.get("detail") or engine_id)
        elif not d.get("binaries_ok"):
            res = (ENGINE_MISSING, d.get("detail") or "")
    except Exception as e:
        res = (None, "probe de motor falló: %s" % e)   # desconocido ≠ roto
    _engine_cache[key] = res
    return res


def _hidden_set():
    try:
        import settings
        v = settings.get_stored("agentes.hidden")
    except Exception:
        return set()
    if isinstance(v, str):
        v = [x for x in v.replace(";", ",").split(",")]
    if not isinstance(v, (list, tuple)):
        return set()
    return {str(x).strip().lower() for x in v if str(x).strip()}


def _readable(path):
    try:
        os.listdir(path)
        return True
    except OSError:
        return False


def _build_one(entry, hidden, path_env):
    import dispatch
    name = str(entry.get("name", "")).strip().lower()
    a = AgentState(
        id=name, name=name, display=name.capitalize(), color="", tagline="",
        brain="", brain_source="none", suggested_brain="", def_path="",
        loaded=bool(entry.get("_loaded")),
        engine_default="", engine="", engine_source="", aliases=[name],
        status=READY, cause="", repair="", hidden=name in hidden)
    try:
        cfg = dispatch.load_agent_cfg(entry)
    except Exception as e:
        cfg = {"_missing_def": True, "_error": str(e)}
    if not isinstance(cfg, dict):
        cfg = {"_missing_def": True}
    if isinstance(cfg.get("id"), str) and cfg["id"].strip():
        a["id"] = cfg["id"].strip().lower()
    a["display"] = str(cfg.get("display_hub") or cfg.get("display") or a["display"])
    a["color"] = str(cfg.get("color") or "")
    a["tagline"] = str(cfg.get("tagline") or "")
    al = cfg.get("aliases", entry.get("aliases", [name]))
    if isinstance(al, str):
        al = [al]
    if isinstance(al, (list, tuple)):
        a["aliases"] = sorted({str(x).lower() for x in al if x is not None} | {name})
    # cerebro: el resolver CANÓNICO (Z20) — el mismo del launcher y del doctor
    try:
        import brain_resolver
        res = brain_resolver.resolve(name, cfg, entry, probe=False)
        brain, a["brain_source"] = res.path, res.source
    except Exception:
        brain = ""
    a["brain"] = brain
    a["def_path"] = cfg.get("_dir", "")
    eng_default = str(cfg.get("engine") or entry.get("engine") or "")
    a["engine_default"] = eng_default
    try:
        import harnesses
        eff, src = harnesses.binding(name, eng_default)
    except Exception:
        eff, src = (eng_default or "claude-code"), "agente"
    a["engine"], a["engine_source"] = eff, src

    def fail(status, cause):
        a["status"], a["cause"] = status, cause
        a["repair"] = repair_hint(status)
        return a

    if not brain:
        if entry.get("dir") and not cfg.get("_missing_def"):
            return _missing(fail(BRAIN_MISSING, _tr(
                "agentstate.cause.no_brain_decl",
                "la definición no declara cerebro")))
        return _missing(fail(BRAIN_MISSING, _tr("agentstate.cause.no_brain_path",
                                                "sin ruta de cerebro")))
    if not os.path.isdir(brain):
        return _missing(fail(BRAIN_MISSING, _tr(
            "agentstate.cause.not_found", "no existe: %(path)s", path=brain)))
    if not _readable(brain):
        return fail(BRAIN_UNREADABLE, brain)
    if cfg.get("_missing_def") and a["loaded"]:
        return fail(DEFINITION_MISSING, os.path.join(brain, ".workspace", "agent.json"))
    if a["loaded"]:
        # Z23: el MISMO validador que create/load/workflows (agent_schema)
        try:
            import agent_schema
            import agentsreg
            errs, _warns = agent_schema.validate_file(agentsreg.agent_json_path(brain))
        except Exception:
            errs = []
        if errs:
            return fail(INVALID_CONFIG, errs[0])
    st, detail = _engine_status(eff, path_env)
    if st:
        return fail(st, "%s: %s" % (eff, detail) if detail else eff)
    if name in hidden:
        a["status"], a["repair"] = HIDDEN, repair_hint(HIDDEN)
    return a


def _missing(a):
    """BRAIN_MISSING + sugerencia de reparación del discovery (Z03): si el
    cerebro aparece en otra ruta, `suggested_brain` la trae y `repair` la cita.
    Usa el índice local (o un escaneo ACOTADO si no hay índice fresco) — solo
    cuando hay un agente roto y la firma cambió, nunca por frame."""
    sug = _suggestions().get(a["name"])
    if sug and sug.get("found"):
        a["suggested_brain"] = sug["found"]
        a["repair"] = _tr("agentstate.repair.found",
                          "%(repair)s → encontrado en %(path)s",
                          repair=a["repair"], path=sug["found"])
    return a


_sug_cache = {"val": None}


def _suggestions():
    if _sug_cache["val"] is None:
        try:
            import agentsreg
            # escaneo acotado con presupuesto corto: corre en la reconstrucción
            # del snapshot (no por frame) y solo si no hay índice fresco
            _sug_cache["val"] = {s["name"]: s for s in
                                 agentsreg.repair_suggestions(time_budget=1.5)}
        except Exception:
            _sug_cache["val"] = {}
    return _sug_cache["val"]


_lock = threading.Lock()
_cache = {"sig": None, "snap": None}


def _registry_entries():
    """(entries, errors, planned) del registry efectivo. Entradas malformadas
    se reportan y no vacían la lista (U12 aceptación 6)."""
    import dispatch
    errors = []
    try:
        reg = dispatch.load_registry()
    except Exception as e:
        return [], ["registry ilegible: %s" % e], []
    raw = reg.get("agents") if isinstance(reg, dict) else None
    if not isinstance(raw, list):
        return [], ["registry sin lista de agentes"], []
    out, seen = [], set()
    for i, e in enumerate(raw):
        if not isinstance(e, dict) or not isinstance(e.get("name"), str) \
                or not e["name"].strip():
            errors.append("entrada %d inválida en el registro" % i)
            continue
        n = e["name"].strip().lower()
        if n in dispatch.SYSTEM_AGENTS:
            continue
        if n in seen:
            errors.append("agente duplicado: %s" % n)
            continue
        seen.add(n)
        out.append(e)
    planned = [p for p in (reg.get("planned") or []) if isinstance(p, str)]
    return out, errors, planned


def _brains_hint(entries):
    """Rutas candidatas de cerebro para la firma (sin cargar definiciones)."""
    out = []
    try:
        import brain_resolver
        ov = brain_resolver.brain_overrides()
    except Exception:
        return out
    for e in entries:
        b = brain_resolver.resolve(e.get("name"), {}, e, overrides=ov, probe=False).path
        if b:
            out.append(b)
        elif e.get("dir"):
            out.append(os.path.join(ROOT, "agents", e["dir"]))
    return out


def snapshot(force=False):
    """Snapshot actual. Cacheado mientras la firma de los stores no cambie."""
    with _lock:
        try:
            entries, errors, planned = _registry_entries()
        except Exception as e:
            entries, errors, planned = [], ["estado ilegible: %s" % e], []
        # El idioma de la UI entra en la REVISIÓN: causa/reparación se
        # construyen localizadas, así que cambiar de idioma reconstruye el
        # snapshot (y las vistas que comparan revision se refrescan solas).
        sig = signature(_brains_hint(entries)) + "|" + _ui_lang()
        if not force and _cache["sig"] == sig and _cache["snap"] is not None:
            return _cache["snap"]
        if force:
            _engine_cache.clear()
        hidden = _hidden_set()
        _sug_cache["val"] = None            # sugerencias: una vez por reconstrucción
        path_env = os.environ.get("PATH", "")
        agents = []
        for e in entries:
            try:
                agents.append(_build_one(e, hidden, path_env))
            except Exception as ex:
                errors.append("%s: %s" % (e.get("name"), ex))
        snap = Snapshot(agents, errors, sig, planned)
        _cache["sig"], _cache["snap"] = sig, snap
        return snap


def invalidate():
    """Tras una mutación propia (add/remove/binding/ruta): fuerza relectura."""
    with _lock:
        _cache["sig"], _cache["snap"] = None, None
        _engine_cache.clear()


def changed(revision):
    """True si el estado cambió respecto a `revision` (polling barato entre
    ventanas — la vista lo llama en su tick, acotado)."""
    try:
        return snapshot().revision != revision
    except Exception:
        return False


def revalidate(agent_id, brain=None):
    """Antes de guardar/lanzar: ¿el agente sigue siendo el mismo?
    Devuelve (ok, agent|None, motivo). Si fue retirado o su cerebro cambió
    (reemplazado desde otra ventana), ok=False — el caller CANCELA la acción
    con aviso, no la redirige."""
    snap = snapshot()
    a = snap.find(agent_id)
    if a is None:
        return False, None, "retirado"
    if brain is not None and _norm(a.get("brain")) != _norm(brain):
        return False, a, "reemplazado"
    return True, a, ""


def _norm(p):
    if not p:
        return ""
    return os.path.normcase(os.path.normpath(os.path.abspath(os.path.expanduser(p))))


def main(argv=None):
    """`python agent_state.py [--json]` — diagnóstico legible del estado."""
    import json
    argv = list(sys.argv[1:] if argv is None else argv)
    snap = snapshot(force=True)
    if "--json" in argv:
        print(json.dumps({"revision": snap.revision, "errors": snap.errors,
                          "agents": snap.agents}, ensure_ascii=False, indent=2))
        return 0
    if not snap.agents:
        print(_tr("agentstate.cli.empty",
                  "sin agentes registrados — carga uno con `workspace agentes`"))
    for a in snap.agents:
        mark = "✓" if a.launchable else ("·" if a["status"] == HIDDEN else "✗")
        line = "%s %-10s %-8s %s" % (mark, a["name"], a["engine"], label(a["status"]))
        if a["cause"]:
            line += " — " + a["cause"]
        if a["repair"] and not a.launchable:
            line += "  [" + a["repair"] + "]"
        print(line)
    for e in snap.errors:
        print("! " + e)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
