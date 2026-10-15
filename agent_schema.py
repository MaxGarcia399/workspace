#!/usr/bin/env python3
"""WORKSPACE · agent_schema — validador ÚNICO de la definición de un agente (Z23).

La definición `<brain>/.workspace/agent.json` viaja con el cerebro (Obsidian
Sync) entre máquinas y sistemas operativos. Este módulo es el contrato que
usan create/load/import/discover/migrate, el estado compartido (agent_state →
invalid_config) y el pipeline de creación (workflows/steps/agent.validate):
un formato, una validación — no un segundo formato paralelo.

Reglas (errores bloquean «listo»; avisos se muestran):
  · name: slug válido (agentsreg.NAME_RE). `id` opcional, estable (slug/uuid).
  · version: opcional; si viene, entero soportado (SUPPORTED_VERSIONS).
  · engine: texto no vacío si viene (el adapter se valida aparte).
  · SIN datos de máquina en un archivo sincronizado: ni rutas absolutas
    (C:\\…, \\\\server\\…, /Users/…, ~/…) en brain/scripts, ni binarios
    detectados, ni secretos. La ruta del cerebro en ESTA máquina vive en
    agents.local.json / paths.local.json.
  · scripts: solo placeholders `{root}`/`{brain}` (portables entre OS).
  · aliases: lista de slugs.
  · autonomy (brain|ask|full) y skill_review (bool): opcionales; un valor raro
    solo AVISA (se usa el valor seguro).
Stdlib puro. `validate(dict) → (errores, avisos)`; `validate_file(path)`.
"""
import json
import ntpath
import posixpath
import re

SUPPORTED_VERSIONS = (1,)
#: `autonomy` del agente: brain (default: libre dentro de su cerebro) | ask
#: (pregunta también dentro de su cerebro). Un "full" de una versión anterior
#: se tolera sin aviso (se lee "brain"; la migración lo convierte).
#: `skill_review`: bool opcional.
AUTONOMY_LEVELS = ("ask", "brain", "full")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")
_SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})")
_MACHINE_KEYS = ("_brain", "binary", "binaries", "token", "api_key", "password")


def _is_machine_path(v):
    """¿Ruta atada a UNA máquina? (absoluta en cualquier OS o ~ de HOME)."""
    if not isinstance(v, str) or not v.strip():
        return False
    s = v.strip()
    if s.startswith(("{root}", "{brain}")):
        return False
    return (ntpath.isabs(s) and (s[1:2] == ":" or s.startswith("\\\\"))) \
        or posixpath.isabs(s) or s.startswith("~")


def validate(d):
    errs, warns = [], []
    if not isinstance(d, dict):
        return ["la definición no es un objeto JSON"], []
    name = d.get("name")
    if not isinstance(name, str) or not _SLUG.match(name.strip().lower()):
        errs.append("name inválido o ausente: %r (slug: minúsculas, números, - _)" % (name,))
    if "id" in d and (not isinstance(d["id"], str) or not _ID.match(d["id"].strip().lower())):
        errs.append("id inválido: %r" % (d.get("id"),))
    if "version" in d and d["version"] not in SUPPORTED_VERSIONS:
        errs.append("versión de definición no soportada: %r (soportadas: %s)"
                    % (d["version"], ", ".join(map(str, SUPPORTED_VERSIONS))))
    if "engine" in d and (not isinstance(d["engine"], str) or not d["engine"].strip()):
        errs.append("engine debe ser texto no vacío")
    al = d.get("aliases")
    if al is not None and not (isinstance(al, list)
                               and all(isinstance(x, str) and _SLUG.match(x.lower()) for x in al)):
        errs.append("aliases debe ser una lista de slugs")
    if _is_machine_path(d.get("brain")):
        errs.append("brain trae una ruta de ESTA máquina (%s) — va en agents.local.json/"
                    "paths.local.json, no en la definición sincronizada" % d["brain"])
    scripts = d.get("scripts")
    if scripts is not None:
        if not isinstance(scripts, dict):
            errs.append("scripts debe ser un objeto")
        else:
            for k, v in scripts.items():
                if not isinstance(v, str):
                    errs.append("scripts.%s no es texto" % k)
                elif _is_machine_path(v):
                    errs.append("scripts.%s usa ruta de máquina (%s) — usa {root}/{brain}" % (k, v))
    # permisos y revisión de skills (contrato común de los motores): un valor
    # raro no bloquea — se usa el seguro (brain / el ajuste global) y se avisa.
    if "autonomy" in d and d["autonomy"] not in AUTONOMY_LEVELS:
        warns.append("autonomy desconocida: %r (se usa 'brain'; válidas: %s)"
                     % (d["autonomy"], ", ".join(AUTONOMY_LEVELS)))
    if "skill_review" in d and not isinstance(d["skill_review"], bool):
        warns.append("skill_review debe ser true o false (se usa el ajuste "
                     "global hooks.skill_review)")
    for k in _MACHINE_KEYS:
        if k in d:
            errs.append("campo per-máquina en la definición sincronizada: %s" % k)
    raw = json.dumps(d, ensure_ascii=False)
    if _SECRET.search(raw):
        errs.append("la definición contiene algo con forma de secreto — quítalo")
    if "{{" in raw:
        errs.append("placeholders del template sin renderizar ({{…}})")
    if "version" not in d:
        warns.append("sin 'version' (se asume 1)")
    return errs, warns


def validate_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return ["no existe: %s" % path], []
    except ValueError as e:
        return ["JSON corrupto en %s: %s" % (path, e)], []
    except OSError as e:
        return ["ilegible: %s (%s)" % (path, type(e).__name__)], []
    return validate(d)
