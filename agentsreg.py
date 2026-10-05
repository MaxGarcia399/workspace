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
      remove(name) · agent_json_path(brain) · load_definition(brain)
"""
import json
import os
import re

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")   # slug de agente válido
WORKSPACE_SUBDIR = ".workspace"                            # carpeta auto-descriptiva en el cerebro
OLYMPUS_SUBDIR = ".olympus"                                # layout LEGACY (pre-rename OLYMPUS→WORKSPACE)


# ── rutas (funciones, no constantes: respetan HOME parchado en tests) ────────
def _workspace_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


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


def read_local():
    """El doc completo del registro per-máquina, saneado. Falla-suave → vacío."""
    data = _read_json(local_path())
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


# ── legacy OLYMPUS (<brain>/.olympus/agent.json) ─────────────────────────────
# Cerebros que vienen del harness viejo traen su manifiesto en `.olympus/` y
# NUNCA se migraron a `.workspace/`. Quien actualiza desde OLYMPUS no vería sus
# agentes si discover() exigiera `.workspace/`. Se detectan aquí y se MIGRAN al
# conectarlos. NO se borra el `.olympus/` — de eso se encarga `workspace doctor`
# (Fase 5d), que solo lo elimina cuando ya existe el `.workspace/agent.json`.
def olympus_json_path(brain):
    """Ruta del manifiesto LEGACY de un cerebro OLYMPUS."""
    return os.path.join(os.path.expanduser(brain or ""), OLYMPUS_SUBDIR, "agent.json")


def has_olympus_definition(brain):
    return os.path.isfile(olympus_json_path(brain))


def _normalize_definition(d):
    """Normaliza una def legacy OLYMPUS al schema `.workspace` actual. Hoy el
    schema es idéntico (mismo `agent.json`), así que es un passthrough que
    PRESERVA toda clave desconocida (forward-compat) — punto único donde
    re-mapear si algún día divergen. Falla-suave → {}."""
    if not isinstance(d, dict):
        return {}
    return dict(d)


def migrate_olympus(brain):
    """Si `<brain>` trae SOLO `.olympus/agent.json` (legacy) y NO
    `.workspace/agent.json`, escribe el `.workspace/agent.json` a partir de él
    (normalizado). NO borra el `.olympus/` (doctor Fase 5d lo hace cuando ya hay
    `.workspace/`). Idempotente, atómico, falla-suave. Devuelve
    (migrado: bool, name|error|"")."""
    base = os.path.abspath(os.path.expanduser(brain or ""))
    canonical = os.path.join(base, WORKSPACE_SUBDIR, "agent.json")
    legacy = os.path.join(base, OLYMPUS_SUBDIR, "agent.json")
    if os.path.isfile(canonical):
        return False, ""                       # ya está en el schema nuevo — `.workspace/` gana
    if not os.path.isfile(legacy):
        return False, ""                       # nada legacy que migrar
    defn = _normalize_definition(_read_json(legacy))
    if not defn:
        return False, "%s ilegible o vacío" % legacy
    defn.setdefault("_migrated_from", OLYMPUS_SUBDIR + "/agent.json")
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
        return False, "nombre inválido: %r (usa minúsculas, dígitos, - o _)" % name
    brain = os.path.abspath(os.path.expanduser((brain or "").strip()))
    if not os.path.isdir(brain):
        return False, "la carpeta del cerebro no existe: %s" % brain
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


# ── auto-descubrimiento de cerebros ──────────────────────────────────────────
# Con el harness distribuido VACÍO, el equipo (y cualquier usuario) no debería
# tener que registrar a mano cada cerebro presente en su máquina. discover()
# escanea ubicaciones conocidas y encuentra cerebros AUTO-DESCRIPTIVOS. Marcador
# de opt-in INEQUÍVOCO para descubrir = `<brain>/.workspace/agent.json` (NO el
# fallback de raíz: evitar falsos positivos de cualquier `agent.json` suelto).
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
        for v in (_read_json(c).get("vaults", {}) or {}).values():
            p = v.get("path")
            if p:
                out.append(p)
    return out


def _scan_parents():
    """Carpetas donde típicamente viven los cerebros (se escanean UN nivel)."""
    home = os.path.expanduser("~")
    return [os.path.join(home, "Desktop"), os.path.join(home, "Documents"),
            os.path.join(home, "Documents", "Obsidian"), os.path.join(home, "Obsidian")]


def discover(extra_roots=None):
    """Devuelve [{name, brain, legacy_olympus}] de cerebros auto-descriptivos en
    ubicaciones conocidas (vaults de Obsidian + hijos de Desktop/Documents/…).
    Marcador canónico = `<brain>/.workspace/agent.json`; FALLBACK legacy =
    `<brain>/.olympus/agent.json` SOLO si no existe el `.workspace/` (cerebros
    de OLYMPUS nunca migrados — se marcan `legacy_olympus=True` para que el
    caller los migre al conectar). NO registra; solo descubre. Dedup por nombre
    (primero encontrado gana) y por carpeta (realpath). Falla-suave SIEMPRE →
    en el peor caso []."""
    direct = list(_obsidian_vault_paths())
    children = []
    for par in (_scan_parents() + list(extra_roots or [])):
        try:
            for nm in sorted(os.listdir(par)):
                children.append(os.path.join(par, nm))
        except OSError:
            continue
    found, seen = {}, set()
    for cand in direct + children:
        try:
            if not os.path.isdir(cand):
                continue
            rp = os.path.realpath(cand)
            if rp in seen:
                continue
            seen.add(rp)
            legacy_olympus = False
            defpath = os.path.join(cand, WORKSPACE_SUBDIR, "agent.json")
            if not os.path.isfile(defpath):                 # fallback: cerebro OLYMPUS legacy
                legacy = os.path.join(cand, OLYMPUS_SUBDIR, "agent.json")
                if os.path.isfile(legacy):
                    defpath, legacy_olympus = legacy, True
                else:
                    continue
            name = str(_read_json(defpath).get("name", "")).strip().lower()
            if not NAME_RE.match(name):
                continue
            if name in found:                          # colisión de nombres: NO la tragues en silencio
                if os.path.abspath(cand) != found[name]["brain"]:
                    import sys
                    sys.stderr.write(
                        "WORKSPACE · aviso: dos cerebros con nombre '%s' — uso %s, ignoro %s "
                        "(renombra uno o cárgalo explícito)\n"
                        % (name, found[name]["brain"], os.path.abspath(cand)))
                continue
            found[name] = {"name": name, "brain": os.path.abspath(cand),
                           "legacy_olympus": legacy_olympus}
        except Exception:
            continue
    return list(found.values())


def discover_and_register(extra_roots=None):
    """Descubre y registra (idempotente) los cerebros encontrados que aún no
    estén en el registro per-máquina. Devuelve [nombres registrados]."""
    have = {a["name"] for a in agents()}
    added = []
    for a in discover(extra_roots):
        if a["name"] in have:
            continue
        if a.get("legacy_olympus"):                # OLYMPUS legacy → migra antes de registrar
            migrate_olympus(a["brain"])            # falla-suave: queda igual si no se pudo
        ok, _ = add(a["name"], a["brain"])
        if ok:
            added.append(a["name"])
    return added


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
    if cmd == "discover":
        register = ("--register" in args) or ("-r" in args)
        if register:
            added = discover_and_register()
            if added:
                print("registrados: " + ", ".join(added))
            else:
                print("agentsreg: nada nuevo que registrar (ya estaban o no hay cerebros)")
        else:
            for a in discover():
                print("  %-12s → %s" % (a["name"], a["brain"]))
            if not discover():
                print("agentsreg: no encontré cerebros con .workspace/agent.json")
        return 0
    print("uso: agentsreg.py list | add <name> <brain> | remove <name> | "
          "discover [--register]")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
