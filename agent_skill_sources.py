"""Skills de fuentes permitidas: selección local, snapshot, audit y recibo.

No LLM, no secretos, no git clone, no instalación de dependencias ni ejecución.
La relevancia es coincidencia explícita de capacidades, no juicio de dominio.
Contenido remoto con alertas/dependencias externas queda fuera del catálogo.
"""
import concurrent.futures
import datetime
import hashlib
import json
import os
import posixpath
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time
import unicodedata
import urllib.request
import urllib.parse
import skill_source_preferences as preferences

# i18n (lado cliente): los pasos EN VIVO, las notas de avance y los motivos de
# revisión los ve el socio en la pantalla «Agregar agente». Import guardado —
# sin i18n, _t() devuelve el español inline (paridad EXACTA con lo de siempre).
try:
    import i18n
except Exception:
    i18n = None


def _t(key, es):
    if i18n is None:
        return es
    try:
        s = i18n.t(key)
        return s if s != key else es
    except Exception:
        return es


SOURCES = ("anthropics/skills", "openai/plugins")
MAX_CANDIDATES = 16
MAX_SELECTED = 5
MAX_FILES = 100
MAX_FILE_BYTES = 512_000
MAX_BUNDLE_BYTES = 3_000_000
MAX_RUN_SECONDS = 180
POLICY = "user-sources-v2"
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
TEXT_EXT = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv",
            ".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".ps1", ".html",
            ".css", ".xsd", ".xml", ".svg", ".sql", ".r", ".ini", ".cfg"}
GROUPS = (
    ("pdf", "documentos pdf"),
    ("xlsx", "excel spreadsheet spreadsheets hojas calculo financiero finanzas accounting contabilidad"),
    ("docx", "word documentos document contracts contratos legal juridico abogado"),
    ("pptx", "powerpoint slides presentaciones presentations"),
    ("frontend", "frontend web website interfaz interfaces ui ux html css"),
    ("testing", "test tests testing pruebas playwright"),
    ("design", "design diseño diseno visual figma"),
    ("research", "research investigacion investigar"),
    ("data", "data datos analysis analisis analytics estadistica"),
)


def _tokens(text):
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return set(re.findall(r"[a-z0-9]+", text)) - {
        "agent", "agente", "skills", "skill", "con", "para", "de", "the",
        "and", "with", "que", "una", "del", "los", "las", "copiloto"}


def profile(params):
    # Jamás se envía a GitHub: solo sirve para puntuar localmente. No usar
    # nombre, tono, dueño ni texto de límites para inventar capacidades.
    intake = params.get("intake") or {}
    return " ".join(str(v or "") for v in (
        params.get("skills"), params.get("tagline"),
        *(intake.get(k) for k in ("skills", "rol", "proposito", "alcance", "ejemplos"))))


def _terms(text):
    terms = _tokens(text)
    for canonical, aliases in GROUPS:
        if terms & _tokens(aliases):
            terms.add(canonical)
    return terms


def _fetch(url, cap=MAX_FILE_BYTES):
    # Sólo URLs generadas por este módulo; no sigue redirecciones a terceros.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("redirección remota no permitida")
    req = urllib.request.Request(url, headers={"User-Agent": "Workspace-Skills/1",
                                              "Accept": "application/json"})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=12) as res:
        body = res.read(cap + 1)
    if len(body) > cap:
        raise ValueError("archivo excede el límite de tamaño")
    return body


def _json(url, cap=6_000_000):
    return json.loads(_fetch(url, cap).decode("utf-8"))


def _safe_path(path):
    p = PurePosixPath(path)
    if (not path or any(ord(c) < 32 for c in path) or p.is_absolute() or "\\" in path or ":" in path
            or any(x in (".", "..", "") for x in path.split("/"))):
        raise ValueError("ruta remota inválida")
    return p


def _blob(repo, sha, path):
    if preferences.normalize_repo(repo) != repo or not SHA.fullmatch(sha):
        raise ValueError("fuente o commit no permitido")
    _safe_path(path)
    data = _fetch("https://raw.githubusercontent.com/%s/%s/%s" % (repo, sha, urllib.parse.quote(path, safe="/")))
    return data


def _metadata(text):
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md sin frontmatter")
    parts = text.split("\n---", 1)
    if len(parts) != 2:
        raise ValueError("frontmatter incompleto")
    header, body = parts
    fields = {}
    lines = header.splitlines()[1:]
    for i, line in enumerate(lines):
        m = re.match(r"^(name|description):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.groups()
        if val in ("|", ">", "|-", ">-"):
            rest = []
            for sub in lines[i + 1:]:
                if sub and not sub[0].isspace():
                    break
                rest.append(sub.strip())
            val = " ".join(rest)
        fields[key] = val.strip().strip("\"'")
    if not SLUG.fullmatch(fields.get("name", "")) or not fields.get("description"):
        raise ValueError("name/description inválidos")
    if len(fields["description"]) > 4000 or any(ord(c) < 32 for c in fields["description"]):
        raise ValueError("description demasiado larga o con controles")
    if not body.strip():
        raise ValueError("skill sin procedimiento")
    return fields


def _tree(repo):
    cache = Path(os.path.expanduser("~")) / ".claude/workspace/skill-sources"
    path = cache / (repo.replace("/", "-") + ".json")
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - saved["at"] < 3600:
            return saved["tree"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    commit = _json("https://api.github.com/repos/%s/commits/HEAD" % repo)["sha"]
    if not SHA.fullmatch(commit):
        raise ValueError("commit inválido")
    tree = _json("https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (repo, commit))
    if tree.get("truncated"):
        raise ValueError("catálogo remoto truncado")
    result = {"sha": commit, "files": tree["tree"]}
    try:
        cache.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp-%d" % os.getpid())
        tmp.write_text(json.dumps({"at": time.time(), "tree": result}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass
    return result


def discover(params, fetch_tree=None, read_blob=None, search=None, should_cancel=None):
    """Descubrimiento acotado por paths; sólo descarga metadata de candidatos.
    Devuelve razones, errores parciales y SHA. No escribe al cerebro.
    """
    fetch_tree, read_blob = fetch_tree or _tree, read_blob or _blob
    cancelled = should_cancel or (lambda: False)
    terms = _terms(profile(params))
    result = {"candidates": [], "errors": [], "policy": POLICY,
              "note": _t("addagent.src.note", "coincidencia de capacidades; no valida conocimiento de dominio")}
    if not terms:
        result["note"] = _t("addagent.src.note_empty", "describe tareas o skills para buscar coincidencias")
        return result
    choices = []
    deadline = time.monotonic() + 90
    config = params.get("skill_source_config")
    repos = list(preferences.enabled(config)) if config is not None else list(SOURCES)
    community_repos = set()
    query = str(params.get("community_query") or "").strip()[:120]
    if config and preferences.validate(config)["community"] and query and not cancelled():
        try:
            response = (search or _json)("https://skills.sh/api/search?q=" + urllib.parse.quote(query) + "&limit=10")
            for item in response.get("skills", [])[:10]:
                repo = preferences.normalize_repo(item["source"])
                if repo not in {r["repo"] for r in config["repos"]} and repo not in repos and len(community_repos) < 4:
                    repos.append(repo)
                    community_repos.add(repo)
        except Exception as exc:
            result["errors"].append("skills.sh: " + type(exc).__name__)
    for repo in repos:
        if cancelled():
            break
        if time.monotonic() >= deadline:
            result["errors"].append(_t("addagent.src.err_timeout", "búsqueda acotada: tiempo máximo alcanzado"))
            break
        try:
            tree = fetch_tree(repo)
            if not SHA.fullmatch(tree["sha"]):
                raise ValueError("commit inválido")
            files = tree["files"]
            for entry in files:
                path = entry["path"]
                _safe_path(path)
                if (path != "SKILL.md" and not path.endswith("/SKILL.md")) or entry.get("type") != "blob":
                    continue
                if repo == "anthropics/skills" and not path.startswith("skills/"):
                    continue
                if repo == "openai/plugins" and not re.match(r"^plugins/[^/]+/skills/", path):
                    continue
                prefix = path.rsplit("/", 1)[0] if "/" in path else ""
                # Incluye sólo el nombre de skill, no el plugin padre: evita
                # recomendar todas las skills de un plugin por un keyword.
                matches = terms & _tokens(prefix.split("/skills/")[-1].split("/")[-1] if prefix else repo.split("/")[-1])
                if not matches:
                    continue
                bundle = [e for e in files if (not prefix or e["path"].startswith(prefix + "/"))
                          and e.get("type") != "tree"]
                plugin = prefix.split("/skills/")[0] if repo == "openai/plugins" else ""
                companions = [e["path"] for e in files if plugin and
                              e["path"] in (plugin + "/.mcp.json", plugin + "/.app.json")]
                inherited = []
                if not any(PurePosixPath(e["path"]).name.upper().startswith("LICENSE") for e in bundle):
                    ancestor = PurePosixPath(prefix)
                    while True:
                        matches_license = [e for e in files if e.get("type") == "blob" and
                            PurePosixPath(e["path"]).parent == ancestor and
                            PurePosixPath(e["path"]).name.upper().startswith("LICENSE")]
                        if matches_license:
                            inherited = matches_license
                            break
                        if str(ancestor) == ".":
                            break
                        ancestor = ancestor.parent
                choices.append({"repo": repo, "license_files": inherited,
                                "discovered_via": "skills.sh" if repo in community_repos else "github",
 "sha": tree["sha"], "path": prefix,
                                "files": bundle, "companions": companions,
                                "matches": sorted(matches), "score": len(matches)})
        except Exception as exc:
            result["errors"].append("%s: %s" % (repo, type(exc).__name__))
    choices.sort(key=lambda c: (-c["score"], c["repo"], c["path"]))
    def describe(c):
        if cancelled():
            raise InterruptedError("búsqueda reemplazada")
        data = read_blob(c["repo"], c["sha"], (c["path"] + "/" if c["path"] else "") + "SKILL.md")
        meta = _metadata(data.decode("utf-8"))
        return dict(c, **meta, metadata_sha256=hashlib.sha256(data).hexdigest(),
                    reason=_t("addagent.src.reason_match", "coincide con: ") + ", ".join(c["matches"]),
                    source_url="https://github.com/%s/tree/%s/%s" % (c["repo"], c["sha"], c["path"]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(describe, c) for c in choices[:MAX_CANDIDATES]]
        for job in jobs:
            try:
                result["candidates"].append(job.result())
            except Exception as exc:
                result["errors"].append("metadata: %s" % type(exc).__name__)
    return result


def steps_skeleton():
    return [{"key": k, "label": label, "st": "pend", "note": ""}
            for k, label in (("skills-audit", _t("addagent.src.step.audit", "skills: descargar y revisar")),
                             ("skills-install", _t("addagent.src.step.install", "skills: instalar y catalogar")))]


def _review(candidate, read_blob, cancelled, report=None, params=None):
    repo, sha, prefix = candidate["repo"], candidate["sha"], candidate["path"]
    if prefix:
        _safe_path(prefix)
    permitted = preferences.permitted(repo, params, candidate) if params and "skill_source_config" in params else repo in SOURCES
    if not permitted or not SHA.fullmatch(sha):
        raise ValueError(_t("addagent.src.err_not_permitted", "fuente no permitida por el usuario"))
    if repo == "anthropics/skills" and not prefix.startswith("skills/"):
        raise ValueError("skill fuera del catálogo")
    if repo == "openai/plugins" and not re.match(r"^plugins/[^/]+/skills/", prefix + "/"):
        raise ValueError("skill fuera del catálogo")
    files = list(candidate["files"]) + list(candidate.get("license_files", []))
    if len(files) > MAX_FILES or not files:
        raise ValueError(_t("addagent.src.err_too_many_files", "cantidad de archivos excedida"))
    # Guard obligatorio: si falta el scanner NO se activa contenido remoto.
    from hooks.untrusted import scan
    from secret_scan import scan_text
    contents, alerts, notes, total = {}, [], [], 0
    if candidate.get("companions"):
        alerts.append(_t("addagent.src.alert_plugin_apps", "plugin requiere apps/MCP: instalar skill sola no lo conecta"))
    for entry in files:
        if cancelled():
            raise InterruptedError("cancelado")
        path = entry["path"]
        _safe_path(path)
        inherited = entry in candidate.get("license_files", [])
        if inherited:
            parent = PurePosixPath(path).parent
            if (not PurePosixPath(path).name.upper().startswith("LICENSE") or
                    parent not in (PurePosixPath(prefix), *PurePosixPath(prefix).parents)):
                raise ValueError("licencia fuera de los ancestros de la skill")
        if (not inherited and prefix and not path.startswith(prefix + "/")) or entry.get("type") != "blob" or entry.get("mode") == "120000":
            raise ValueError("symlink, submódulo o ruta fuera de la skill")
        rel = "LICENSE.upstream-" + PurePosixPath(path).name if inherited else path[len(prefix) + 1:] if prefix else path
        if rel in (".source.json", ".usage.json", ".audit.json") or any(p in (".git", ".claude", ".codex", ".workspace") for p in PurePosixPath(rel).parts):
            raise ValueError("sidecar de procedencia reservado")
        if rel in contents:
            raise ValueError("ruta duplicada")
        data = read_blob(repo, sha, path)
        total += len(data)
        if len(data) > MAX_FILE_BYTES or total > MAX_BUNDLE_BYTES:
            raise ValueError("bundle excede límite de tamaño")
        # Git blob hash verifica que TODOS los recursos son los del snapshot.
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != entry.get("sha"):
            raise ValueError("hash Git de recurso no coincide")
        suffix = PurePosixPath(rel).suffix.lower()
        if suffix not in TEXT_EXT and not PurePosixPath(rel).name.upper().startswith("LICENSE"):
            alerts.append(_t("addagent.src.alert_binary", "recurso binario/no inspeccionable: ") + rel)
        else:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                alerts.append(_t("addagent.src.alert_not_utf8", "recurso no UTF-8: ") + rel)
            else:
                findings = {f["class"] for f in scan(text)} | {f["class"] for f in scan_text(text)}
                alerts.extend("%s: %s" % (rel, k) for k in sorted(findings))
                if re.search(r"(?i)(?:\$\{?CLAUDE_PLUGIN_ROOT|\$\{?CODEX_HOME|mcp__|tools\.mcp|app://)", text):
                    alerts.append(_t("addagent.src.alert_runtime_dep", "dependencia de runtime/app: ") + rel)
                if re.search(r"/(?:mnt/data|opt/|home/oai/)|[A-Za-z]:\\", text):
                    notes.append(_t("addagent.src.note_adapt_paths", "adaptar rutas de ejemplo al entorno: ") + rel)
                # Referencias relativas dentro de recursos no son traversal del
                # instalador. Los nombres de archivo sí se validan estrictamente.
                relative_refs = re.findall(r"(?:\.\./)+[A-Za-z0-9_.\-/]+", text)
                if relative_refs:
                    notes.append(_t("addagent.src.note_relative_refs", "referencias relativas de ejemplo; adaptar al contexto de uso: ") + rel)
                # Un enlace Markdown a un recurso necesario debe resolverse.
                # Los Targets XML de PPTX y rutas de salida son datos de ejemplo,
                # no nombres de archivo que el importador vaya a escribir.
                for ref in re.findall(r"\]\((\.\./[^)\s]+)\)", text):
                    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), ref.split("#")[0]))
                    relative_files = [e["path"][len(prefix) + 1:] if prefix else e["path"] for e in candidate["files"]]
                    if resolved.startswith("../") or not any(p == resolved or p.startswith(resolved.rstrip("/") + "/") for p in relative_files):
                        alerts.append(_t("addagent.src.alert_linked_missing", "recurso enlazado no incluido: ") + rel)
                if suffix in (".py", ".js", ".ts", ".sh", ".ps1") and re.search(r"(?i)\b(?:eval|exec)\s*\(|(?:curl|wget)\b[^\n]*[|;]\s*(?:sh|bash)|\b(?:b64decode|frombase64string)\s*\(", text):
                    alerts.append(_t("addagent.src.alert_dynamic_code", "código dinámico o ejecución remota requiere revisión: ") + rel)
        contents[rel] = data
        if report:
            report(_t("addagent.src.audit_progress", "%s: %d/%d recursos revisados") % (candidate["name"], len(contents), len(files)))
    from skill_meta import parse_requires, evaluate
    if contents.get("SKILL.md"):
        requires = parse_requires(contents["SKILL.md"].decode("utf-8"))
        available, missing = evaluate(requires)
        if not available:
            alerts.append(_t("addagent.src.alert_missing_reqs", "requisitos no disponibles: ") + ", ".join(missing))
    skill = contents.get("SKILL.md", b"")
    meta = _metadata(skill.decode("utf-8"))
    if hashlib.sha256(skill).hexdigest() != candidate.get("metadata_sha256"):
        raise ValueError("metadata cambió desde el plan")
    if meta["name"] != candidate["name"]:
        raise ValueError("nombre cambió desde el plan")
    # No reescribir metadata o licencias upstream. Procedencia va en sidecar.
    license_files = [p for p in contents if PurePosixPath(p).name.upper().startswith("LICENSE")]
    if not license_files:
        alerts.append(_t("addagent.src.alert_no_license", "licencia no incluida en la skill: requiere revisión"))
    candidate["compatibility_notes"] = sorted(set(notes))
    return contents, sorted(set(alerts))


def _catalogs(brain):
    root = Path(brain) / "skills"
    rows = []
    if any(p.is_symlink() for p in root.rglob("*")):
        raise ValueError("catálogo con symlinks: no se leen ni regeneran índices")
    for p in sorted(root.glob("*/*/SKILL.md")):
        if any(x.startswith("_") for x in p.relative_to(root).parts):
            continue
        try:
            meta = _metadata(p.read_text(encoding="utf-8"))
            desc = meta["description"].replace("|", "/").replace("\n", " ")
        except (ValueError, OSError):
            desc = "Consultar SKILL.md"
        rows.append((p.parent.relative_to(root).as_posix(), desc))
    readme = root / "README.md"
    prior = readme.read_text(encoding="utf-8") if readme.exists() else ""
    conventions = prior.split("## Convenciones", 1)[-1].split("<!-- SOURCED-CATALOG -->", 1)[0] if "## Convenciones" in prior else ""
    text = "# Skills — catálogo\n\n**Total: %d skills**\n\n" % len(rows)
    text += "Consultar INDEX-LITE.md al arrancar y cargar SKILL.md según la tarea.\n\n"
    for cat in sorted({r[0].split("/")[0] for r in rows}):
        subset = [r for r in rows if r[0].startswith(cat + "/")]
        text += "## %s (%d)\n\n| Skill | Qué hace |\n|---|---|\n" % (cat, len(subset))
        text += "".join("| `%s/` | %s |\n" % row for row in subset) + "\n"
    if conventions:
        text += "## Convenciones" + conventions.rstrip() + "\n"
    text += "\n<!-- SOURCED-CATALOG -->\n\nLas importadas conservan licencia y recursos originales. " \
            "Su procedencia está en .source.json; la revisión estática no certifica seguridad " \
            "ni conocimientos de dominio. Las pendientes no están activadas: ver " \
            "`.workspace/skill-sourcing.json`. No se conectan apps ni se ejecutan scripts al importar.\n"
    _atomic(readme, text.encode("utf-8"))
    lite = "# Skills — índice de arranque\n\nTotal: %d skills. Consultar README.md y SKILL.md según la tarea.\n\n" % len(rows)
    # Índice HOT pequeño: categorías + conteos, nunca cuerpos completos.
    for cat in sorted({r[0].split("/")[0] for r in rows}):
        lite += "- `%s/`: %d skills\n" % (cat, sum(r[0].startswith(cat + "/") for r in rows))
    _atomic(root / "INDEX-LITE.md", lite.encode("utf-8"))


def _atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-%d" % os.getpid())
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def run(brain, params, progress=None, should_cancel=None, read_blob=None):
    """Cada bundle se publica por rename atómico; colisiones nunca sobrescriben.
    Los fallos se registran, no derriban al agente ni activan contenido parcial.
    """
    progress = progress or (lambda *a: None)
    cancelled = should_cancel or (lambda: False)
    raw_read = read_blob or _blob
    deadline = time.monotonic() + MAX_RUN_SECONDS
    def read_blob(repo, sha, path):
        if time.monotonic() > deadline:
            raise TimeoutError("tiempo máximo de sourcing alcanzado")
        return raw_read(repo, sha, path)
    result = {"policy": POLICY, "tokens": 0, "installed": [], "held": [], "errors": [],
              "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "review": "estática; no certifica seguridad, exactitud ni competencia"}
    selected = params.get("skill_candidates") or []
    if len(selected) > MAX_SELECTED:
        result["errors"].append(_t("addagent.src.err_max_skills", "máximo %d skills por creación") % MAX_SELECTED)
        selected = []
    progress("skills-audit", "run", _t("addagent.src.audit_selected", "%d seleccionadas · 0 tokens") % len(selected))
    root = Path(brain).resolve()
    skill_root = root / "skills"
    published, indices = [], {}
    try:
        if not skill_root.is_dir() or skill_root.is_symlink():
            raise ValueError("carpeta skills inválida")
        if (root / ".workspace").is_symlink():
            raise ValueError("carpeta .workspace symlink no permitida")
        for filename in ("README.md", "INDEX-LITE.md"):
            path = skill_root / filename
            if path.is_symlink():
                raise ValueError("índice symlink no permitido")
            indices[path] = path.read_bytes() if path.exists() else None
        for c in selected:
            if cancelled():
                result["errors"].append(_t("addagent.src.err_cancelled_kept", "cancelado; las skills instaladas se conservan"))
                break
            name = c.get("name", "")
            try:
                if not SLUG.fullmatch(name):
                    raise ValueError(_t("addagent.src.err_bad_name", "nombre inválido"))
                contents, alerts = _review(c, read_blob, cancelled,
                                          lambda note: progress("skills-audit", "run", note), params=params)
                record = {k: c[k] for k in ("name", "repo", "sha", "path", "reason", "source_url")}
                record["discovered_via"] = c.get("discovered_via", "github")
                record["compatibility_notes"] = c.get("compatibility_notes", [])
                record["license_origins"] = [e["path"] for e in c.get("license_files", [])]
                record["files"] = {p: hashlib.sha256(b).hexdigest() for p, b in contents.items()}
                if alerts:
                    result["held"].append(dict(record, reasons=alerts))
                    continue
                parent = skill_root / ("oficiales" if c["repo"] in SOURCES else "externas")
                if parent.is_symlink():
                    raise ValueError("categoría symlink no permitida")
                parent.mkdir(exist_ok=True)
                dest = parent / name
                if dest.exists() or dest.is_symlink():
                    raise ValueError(_t("addagent.src.err_exists", "skill existente: no se sobrescribe"))
                if any(p.parent.name == name for p in skill_root.glob("*/*/SKILL.md")):
                    raise ValueError(_t("addagent.src.err_name_elsewhere", "nombre ya presente en otra categoría"))
                stage = Path(tempfile.mkdtemp(prefix=".skill-stage-", dir=str(parent)))
                try:
                    for rel, data in contents.items():
                        p = stage / rel
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(data)
                    (stage / ".source.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                    if cancelled():
                        raise InterruptedError(_t("addagent.src.err_cancelled_pre", "cancelado antes de instalar"))
                    stage.rename(dest)
                    published.append(dest)
                    result["installed"].append(record)
                finally:
                    if stage.exists():
                        shutil.rmtree(stage)
            except Exception as exc:
                result["errors"].append("%s: %s" % (name, str(exc)))
        progress("skills-audit", "warn" if result["held"] or result["errors"] else "ok",
                 _t("addagent.src.audit_done", "%d instaladas · %d requieren revisión") % (len(result["installed"]), len(result["held"])))
        progress("skills-install", "run", _t("addagent.src.install_run", "actualizar índices y recibo"))
        _catalogs(root)
        receipt = root / ".workspace/skill-sourcing.json"
        if receipt.parent.is_symlink():
            raise ValueError("carpeta .workspace symlink no permitida")
        _atomic(receipt, json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
        progress("skills-install", "warn" if result["errors"] else "ok",
                 _t("addagent.src.install_done", "%d skills activadas · recibo .workspace/skill-sourcing.json") % len(result["installed"]))
    except Exception as exc:
        result["errors"].append(str(exc))
        # Sólo revertir carpetas NUEVAS publicadas por esta corrida. Nunca
        # tocar skills anteriores/del dueño; restaurar ambos índices juntos.
        for path in published:
            try:
                shutil.rmtree(path)
            except OSError:
                result["errors"].append("rollback incompleto: " + path.name)
        if published:
            result["installed"] = []
        for path, original in indices.items():
            try:
                if original is None:
                    if path.exists():
                        path.unlink()
                else:
                    _atomic(path, original)
            except OSError:
                result["errors"].append("no se pudo restaurar índice: " + path.name)
        progress("skills-install", "warn", _t("addagent.src.install_reverted", "skills revertidas; agente conservado"))
    return result
