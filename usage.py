#!/usr/bin/env python3
"""WORKSPACE · usage — sidecar de uso de skills `.usage.json` (N12).

Robo Hermes E + Odysseus (convergencia ×2): el bookkeeping de uso de una skill
(`used_count` y compañía) NO vive más en el frontmatter del SKILL.md — cada
incremento ahí era churn en git y rompía el cache del archivo. Vive en un
sidecar por skill:

    skills/<categoría>/<nombre>/.usage.json

Formato (schema 1):
    {
      "schema": 1,
      "use_count": 3,        # la skill se SIGUIÓ para ejecutar una tarea
      "view_count": 1,       # se LEYÓ/consultó sin ejecutarla completa
      "patch_count": 2,      # recibió un patch (skill_review / improver)
      "last_used": "2026-06-11T03:12:45Z",      # cualquier evento lo refresca
      "last_patched": "2026-06-10T22:01:02Z",   # solo eventos patch
      "seeded_from_frontmatter": 2              # migración lazy (si aplicó)
    }

Reglas (las del foso — regla 2: derivado y reconstruible, jamás fuente de
verdad del CONTENIDO de la skill):
- El SKILL.md queda ESTABLE: su `used_count:` histórico se congela, no se
  edita más. Migración LAZY: al primer evento registrado, el sidecar nace
  sembrando `use_count` desde ese frontmatter — nada se migra a mano.
- Back-compat: si NO hay sidecar, `read_usage()` cae al frontmatter viejo.
  Nadie que lea `used_count` se rompe; nadie que lea el sidecar ve menos.
- Escrituras SIEMPRE bajo `olock.file_lock` + write atómico (tmp + os.replace):
  dos sesiones registrando uso a la vez no corrompen el JSON.
- Git: el sidecar SÍ se versiona en el git del cerebro (el conteo es del
  EQUIPO y viaja con el sync); el `.usage.json.lock` se gitignora (estado
  per-máquina). Decisión documentada en skills/README.md de cada cerebro.

API:
    record(skill_dir, event)        # event ∈ {"use","view","patch"} — con lock
    read_usage(skill_dir)           # estado efectivo (sidecar > frontmatter)
    frontmatter_used_count(skill_dir)   # el valor legacy, o None
    sidecar_path(skill_dir)

CLI (para hooks/scripts):  python3 usage.py <skill_dir> [use|view|patch]
Stdlib puro (3.9+), cross-platform, amputable. Consumidores: skill_review
(hoy, vía prompt), audit pipeline N4 y loop medido N5 (mañana).
"""
import datetime
import json
import os
import re
import sys

import olock

SIDECAR_NAME = ".usage.json"
SCHEMA = 1
EVENTS = ("use", "view", "patch")
# archivos donde puede vivir el frontmatter legacy (kits usan otros nombres)
SKILL_FILES = ("SKILL.md", "CLAUDE.md", "INSTRUCCIONES.md")

_FM_USED = re.compile(r"^used_count:\s*(\d+)\s*$", re.MULTILINE)


def sidecar_path(skill_dir):
    return os.path.join(str(skill_dir), SIDECAR_NAME)


def frontmatter_used_count(skill_dir):
    """`used_count:` del frontmatter YAML del SKILL.md (o CLAUDE/INSTRUCCIONES
    en kits). None si no hay archivo, frontmatter o campo. Solo lectura —
    este módulo JAMÁS edita un SKILL.md."""
    for name in SKILL_FILES:
        p = os.path.join(str(skill_dir), name)
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read(8192)        # frontmatter vive al inicio
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        block = text[:end] if end != -1 else text
        m = _FM_USED.search(block)
        if m:
            return int(m.group(1))
    return None


def _fresh():
    return {"schema": SCHEMA, "use_count": 0, "view_count": 0,
            "patch_count": 0, "last_used": None}


def _normalize(data):
    """Sidecar leído de disco → shape completo (campos faltantes = default)."""
    out = _fresh()
    for k in out:
        if k in data:
            out[k] = data[k]
    for k in ("last_patched", "seeded_from_frontmatter"):
        if k in data:
            out[k] = data[k]
    for k in ("use_count", "view_count", "patch_count"):
        if not isinstance(out[k], int) or out[k] < 0:
            out[k] = 0
    out["schema"] = SCHEMA
    return out


def _load_sidecar(skill_dir):
    """dict del sidecar o None (no existe / corrupto — corrupto se reporta
    como None y `record` lo reconstruye; jamás truena al llamador)."""
    try:
        with open(sidecar_path(skill_dir), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return _normalize(data) if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _seed(skill_dir):
    """Sidecar inicial: migración lazy desde el frontmatter legacy (si hay)."""
    data = _fresh()
    legacy = frontmatter_used_count(skill_dir)
    if legacy:
        data["use_count"] = legacy
        data["seeded_from_frontmatter"] = legacy
    return data


def read_usage(skill_dir):
    """Estado efectivo de uso, SIN escribir nada: el sidecar si existe; si no,
    fallback al `used_count` del frontmatter (back-compat)."""
    data = _load_sidecar(skill_dir)
    return data if data is not None else _seed(skill_dir)


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _atomic_write_json(path, data):
    """tmp + fsync + os.replace: o queda la versión vieja o la nueva entera —
    un sidecar a medio escribir no existe (regla: jamás corromper un cerebro)."""
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def record(skill_dir, event="use", when=None, timeout=5.0):
    """Registra un evento de uso en el sidecar de la skill, con lock N8 y
    escritura atómica. Crea el sidecar si no existe (sembrando del frontmatter
    legacy). Devuelve el estado resultante. Levanta ValueError si el evento no
    es use/view/patch, y olock.LockTimeout si el lock no se pudo adquirir —
    el llamador decide si el conteo perdido importa (normalmente no)."""
    if event not in EVENTS:
        raise ValueError("evento desconocido: %r (válidos: %s)"
                         % (event, "/".join(EVENTS)))
    skill_dir = str(skill_dir)
    if not os.path.isdir(skill_dir):
        raise FileNotFoundError("no es una carpeta de skill: %s" % skill_dir)
    sc = sidecar_path(skill_dir)
    ts = (when or _utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")
    with olock.file_lock(sc, timeout=timeout):
        data = _load_sidecar(skill_dir)
        if data is None:
            data = _seed(skill_dir)
        data[event + "_count"] = data.get(event + "_count", 0) + 1
        data["last_used"] = ts
        if event == "patch":
            data["last_patched"] = ts
        _atomic_write_json(sc, data)
    return data


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.split("API:")[0].strip())
        print("\nUso: python3 usage.py <skill_dir> [use|view|patch]")
        return 2
    skill_dir = args[0]
    event = args[1] if len(args) > 1 else "use"
    try:
        data = record(skill_dir, event)
    except (ValueError, FileNotFoundError, olock.LockTimeout) as e:
        print("usage.py: %s" % e, file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
