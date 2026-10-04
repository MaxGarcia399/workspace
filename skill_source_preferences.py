"""Fuentes por máquina: catálogos conocidos y repos públicos elegidos por el dueño."""
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

REPO_RX = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38})/[a-z0-9][a-z0-9_.-]{0,99}$", re.I)
PRESETS = (
    ("anthropics/skills", "Anthropic · skills", True,
     "Skills publicadas por Anthropic. Revisión local obligatoria."),
    ("openai/plugins", "OpenAI · plugins", True,
     "Importa sólo skills; no instala hooks, apps ni servidores del plugin."),
    ("anthropics/claude-plugins-official", "Anthropic · directorio de plugins", True,
     "Incluye contenido propio y de terceros admitidos en el directorio."),
    ("vercel-labs/agent-skills", "Vercel · agent skills", False,
     "Skills de Vercel; habilítalas si sus capacidades te sirven."),
)
MAX_REPOS = 12


def normalize_repo(value):
    """Sólo owner/repo o URL HTTPS del repo raíz. Nunca git/ssh/auth/refs arbitrarios."""
    raw = str(value).strip()
    if "://" in raw:
        url = urlsplit(raw)
        if url.scheme != "https" or url.hostname != "github.com" or url.username or url.password or url.port or url.query or url.fragment:
            raise ValueError("usa https://github.com/autor/repositorio, sin credenciales")
        raw = url.path.strip("/")
    raw = raw.removesuffix(".git") if hasattr(raw, "removesuffix") else raw[:-4] if raw.endswith(".git") else raw
    if not REPO_RX.fullmatch(raw) or any(p in (".", "..") for p in raw.split("/")):
        raise ValueError("usa autor/repositorio o su URL raíz de GitHub")
    return raw.lower()


def defaults():
    return {"repos": [{"repo": r, "label": label, "enabled": enabled, "custom": False}
                       for r, label, enabled, _ in PRESETS], "community": False}


def validate(config):
    if not isinstance(config, dict) or not isinstance(config.get("repos"), list):
        raise ValueError("configuración de fuentes inválida")
    if len(config["repos"]) > MAX_REPOS:
        raise ValueError("máximo %d repositorios" % MAX_REPOS)
    result, seen = [], set()
    known = {r: label for r, label, _, _ in PRESETS}
    for item in config["repos"]:
        repo = normalize_repo(item["repo"])
        if repo in seen or not isinstance(item.get("enabled"), bool):
            raise ValueError("fuente duplicada o estado inválido")
        seen.add(repo)
        result.append({"repo": repo, "label": known.get(repo, repo),
                       "enabled": item["enabled"], "custom": repo not in known})
    if not isinstance(config.get("community", False), bool):
        raise ValueError("opción de comunidad inválida")
    return {"repos": result, "community": config.get("community", False)}


def path():
    return Path(os.path.expanduser("~")) / ".claude/workspace/skill-source-preferences.json"


def load():
    try:
        return validate(json.loads(path().read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return defaults()


def save(config):
    """Persistencia atómica; el llamador muestra errores, no simula guardado."""
    value = validate(config)
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".skill-preferences-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return value


def enabled(config):
    return tuple(r["repo"] for r in validate(config)["repos"] if r["enabled"])


def permitted(repo, params, candidate=None):
    config = validate(params.get("skill_source_config", defaults()))
    repo = normalize_repo(repo)
    if repo in enabled(config):
        return True
    # Opt-in del directorio permite ver candidatos; sólo una selección expresa
    # del repo específico permite su importación. No se amplía el whitelist global.
    if any(r["repo"] == repo and not r["enabled"] for r in config["repos"]):
        return False
    approved = [normalize_repo(r) for r in params.get("approved_community_repos", [])]
    return bool(config["community"] and repo in approved and candidate and
                candidate.get("discovered_via") == "skills.sh")


def add(config, value):
    config = validate(config)
    repo = normalize_repo(value)
    if any(r["repo"] == repo for r in config["repos"]):
        raise ValueError("ese repositorio ya está en tus fuentes")
    if len(config["repos"]) >= MAX_REPOS:
        raise ValueError("máximo %d repositorios" % MAX_REPOS)
    config["repos"].append({"repo": repo, "label": repo, "enabled": True, "custom": True})
    return config
