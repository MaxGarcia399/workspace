"""WORKSPACE · agents_tui — sección AGENTES del hub (transparencia por agente).

Qué muestra, por agente (Tab cambia de agente, ◄► / 1-5 de sección):
  · Config   — los campos de agent.json que importan + overrides per-máquina,
               con qué significa cada uno, dónde vive y cómo se cambia hoy.
  · Cerebro  — el árbol REAL del cerebro (leído del disco) con su propósito.
  · Skills   — el catálogo del cerebro (frontmatter de cada SKILL.md).
  · Rutas    — rutas resueltas: cerebro, sesiones, per-máquina (checkpoints
               solo si la instalación trae session_continuity).
  · Ciclo    — cómo habla WORKSPACE con el cerebro: arranque, guardar,
               recuperar y sync, trazado al código (hooks, launcher, memoria).
               Sin session_continuity / agent_sandbox la pantalla describe lo
               que SÍ hay (variantes `.nocp` del catálogo) — nunca un sistema
               ausente como si fuera el mecanismo principal.

SOLO LECTURA: nada se escribe desde aquí (el layout deja lugar para editar
después). Los mapas reutilizan el lenguaje existente: brain_view.render (el
mapa de «tu cerebro en construcción»), brain_view.pipeline (el mini-mapa del
dev panel) y brain_view.fan (el grupo «se queda» del mapa del dev panel),
sobre el lienzo agent_create_ui._MapCanvas. Cabecera = HL.screen_header con
el wordmark titulado AGENTES/AGENTS. Cero dependencias (stdlib, Py 3.9+).
"""
import hashlib
import json
import os
import shutil
import sys
import textwrap
import time

import hublayout as HL
import brain_view

ROOT = os.path.dirname(os.path.abspath(__file__))


# ── i18n: el catálogo ES es la fuente (byte-idéntico por construcción) ─────
def _load_es():
    try:
        from lang.es import agents as _m
        return dict(_m.STRINGS)
    except Exception:
        return {}


_ES = _load_es()


def _t(key, **kw):
    try:
        import i18n
        v = i18n.t(key, **kw)
        if v != key:
            return v
    except Exception:
        pass
    s = _ES.get(key, key)
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def word():
    """La palabra del wordmark de esta sección (AGENTES / AGENTS)."""
    return _t("agents.word")


SECS = ("config", "brain", "skills", "paths", "cycle")
FLOWS = ("boot", "save", "retrieve", "sync")


def _K():
    """Paleta del TEMA activo (igual que el hub), con fallback que no truena."""
    try:
        import tuitheme
        return HL.cols(tuitheme.palette())
    except Exception:
        return HL.cols(type("P", (), {"GLYPHS": {}})())


def _home(p):
    """Ruta con ~ para leer corto (el detalle muestra la completa)."""
    p = str(p or "")
    h = os.path.expanduser("~")
    return ("~" + p[len(h):]) if h and p.startswith(h) else p


def _continuity():
    """El subsistema de continuidad (workspace memoria) está en este árbol."""
    return os.path.isfile(os.path.join(ROOT, "session_continuity.py"))


def _sandbox_available():
    """El sandbox por agente (agent_sandbox) viene en esta instalación."""
    return os.path.isfile(os.path.join(ROOT, "agent_sandbox.py"))


def _tc(key, **kw):
    """Como _t, pero sin el subsistema de continuidad usa la variante
    `<key>.nocp` si existe: la pantalla describe lo que HAY en esta
    instalación (journal + hooks + dream) y no menciona checkpoints."""
    if (key + ".nocp") in _ES and not _continuity():
        key += ".nocp"
    return _t(key, **kw)


# ═══════════════════════════════════════════════════════════════════════════
# DATOS (solo lectura, falla-suave)
# ═══════════════════════════════════════════════════════════════════════════

def agents():
    """Agentes visibles para el socio, con su cerebro resuelto y la fuente
    de esa resolución (paths.local.json vs agent.json)."""
    out = []
    try:
        import dispatch
        entries = dispatch.visible_agents()
        overrides = (dispatch._local_overrides() or {}).get("brains") or {}
    except Exception:
        return out
    for entry in entries:
        try:
            cfg = dict(dispatch.load_agent_cfg(entry))
        except Exception:
            cfg = {"name": entry.get("name", ""), "_missing_def": True}
        name = cfg.get("name") or entry.get("name", "")
        cfg["name"] = name
        try:
            brain = dispatch.resolve_brain(name, cfg) or ""
        except Exception:
            brain = ""
        cfg["_brain"] = brain
        cfg["_brain_src"] = "paths" if name in overrides else "agent"
        out.append(cfg)
    return out


def _read_head(path, limit=4096):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except Exception:
        return ""


def frontmatter(text):
    """Claves de nivel superior del frontmatter YAML (`---`): `k: v`,
    comillas, y bloques `>`/`|` (líneas sangradas unidas). {} si no hay."""
    if not text or not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out, key, buf = {}, None, []
    for line in text[3:end].split("\n"):
        if key and (line.startswith((" ", "\t")) or not line.strip()):
            if line.strip():
                buf.append(line.strip())
            continue
        if key:
            out[key] = " ".join(buf)
            key, buf = None, []
        if ":" not in line or line.startswith((" ", "#", "-")):
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v in ("", ">", ">-", ">+", "|", "|-", "|+"):
            key, buf = k, []
            continue
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k] = v
    if key:
        out[key] = " ".join(buf)
    return out


def _first_heading(text):
    """Primer `# título` (o primera línea con texto) fuera de frontmatter y
    comentarios HTML."""
    body = text
    if body.startswith("---"):
        end = body.find("\n---", 3)
        body = body[end + 4:] if end != -1 else body
    incom = False
    for line in body.split("\n"):
        s = line.strip()
        if incom:
            if "-->" in s:
                incom = False
            continue
        if s.startswith("<!--"):
            incom = "-->" not in s
            continue
        if s.startswith("#"):
            return s.lstrip("#").strip()
    return ""


def _purpose_of_file(path):
    txt = _read_head(path)
    fm = frontmatter(txt)
    return " ".join(str(fm.get("description") or "").split()) \
        or _first_heading(txt)


def _purpose_of_dir(path, name):
    """Propósito según el README/índice de la carpeta: su primer título,
    sin el prefijo `nombre/ —` que suelen llevar."""
    for fn in ("README.md", "INDEX.md", "index.md"):
        p = os.path.join(path, fn)
        if os.path.isfile(p):
            h = _first_heading(_read_head(p))
            for sep in (" — ", " – ", " - ", ": "):
                head, s, rest = h.partition(sep)
                if s and head.strip().rstrip("/").lower() == name.lower():
                    h = rest
                    break
            if h:
                return h.strip(), fn
    return "", ""


_KNOWN = (("CLAUDE.md", "agents.n.claude"), ("BOOT", "agents.n.boot"),
          ("STATE", "agents.n.state"), ("wiki", "agents.n.wiki"),
          ("skills", "agents.n.skills"), ("adapters", "agents.n.adapters"),
          (".workspace", "agents.n.workspace"),
          (".claude", "agents.n.claudedir"))
_KNOWN_STATE = (("MEMORY.md", "agents.n.memory"), ("INDEX.md", "agents.n.index"),
                ("sessions", "agents.n.sessions"), ("inbox", "agents.n.inbox"),
                ("DESTILADO.md", "agents.n.destilado"))
_READS = {"CLAUDE.md": "agents.n.reads.claude", "BOOT": "agents.n.reads.boot",
          "STATE": "agents.n.reads.state", "wiki": "agents.n.reads.wiki",
          "skills": "agents.n.reads.skills", ".claude": "agents.n.reads.claudedir",
          ".workspace": "agents.n.reads.workspace"}
_SKIP_ROOT = {".git", ".obsidian", ".DS_Store", ".trash", "__pycache__"}


def _count(path, budget):
    """Archivos .md/.json bajo `path` (sin seguir symlinks), acotado."""
    n = 0
    stack = [path]
    while stack and budget[0] > 0:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    budget[0] -= 1
                    if budget[0] <= 0:
                        break
                    if e.is_symlink() or e.name.startswith("."):
                        continue
                    if e.is_dir():
                        stack.append(e.path)
                    elif e.name.endswith((".md", ".json")):
                        n += 1
        except OSError:
            continue
    return n


def brain_tree(brain, max_files=6000):
    """Nodos del cerebro en orden de contrato (CLAUDE.md, BOOT, STATE, wiki,
    skills, adapters, .workspace, .claude) y después el resto de la raíz.
    BOOT y STATE se expanden un nivel. Cada nodo trae su propósito y de
    dónde sale ese propósito (convención vs su README). [] si no hay cerebro."""
    if not brain or not os.path.isdir(brain):
        return []
    budget = [max_files]
    try:
        names = sorted(os.listdir(brain), key=str.lower)
    except OSError:
        return []
    known = [k for k, _ in _KNOWN]
    order = [k for k in known if k in names]
    order += [n for n in names if n not in known and n not in _SKIP_ROOT
              and not n.startswith(".") and os.path.isdir(os.path.join(brain, n))]
    order += [n for n in names if n not in known and not n.startswith(".")
              and n.endswith(".md") and os.path.isfile(os.path.join(brain, n))]
    conv = dict(_KNOWN)
    nodes = []
    for n in order:
        p = os.path.join(brain, n)
        if os.path.islink(p):
            continue
        isdir = os.path.isdir(p)
        node = {"name": n, "label": n + ("/" if isdir else ""), "depth": 0,
                "path": p, "dir": isdir, "key": n}
        if isdir:
            readme, rfile = _purpose_of_dir(p, n)
            node["readme"], node["readme_file"] = readme, rfile
            node["count"] = _count(p, budget)
        else:
            readme, rfile = _purpose_of_file(p), ""
            node["readme"], node["readme_file"] = readme, n if readme else ""
        if n in conv:
            node["purpose"], node["src"] = _tc(conv[n]), "conv"
        elif readme:
            node["purpose"], node["src"] = readme, "readme"
        else:
            node["purpose"] = _t("agents.n.other_dir" if isdir
                                 else "agents.n.other_file")
            node["src"] = "none"
        nodes.append(node)
        if n in ("BOOT", "STATE") and isdir:
            nodes += _children(p, n)
    if budget[0] <= 0 and nodes:
        nodes[0]["truncated"] = True
    return nodes


def _children(path, parent, cap=14):
    try:
        names = sorted(os.listdir(path), key=str.lower)
    except OSError:
        return []
    conv = dict(_KNOWN_STATE) if parent == "STATE" else {}
    first = [k for k, _ in _KNOWN_STATE if parent == "STATE" and k in names]
    files = [n for n in names if n not in first and n.endswith(".md")
             and os.path.isfile(os.path.join(path, n))]
    dirs = [n for n in names if n not in first and not n.startswith((".", "_"))
            and os.path.isdir(os.path.join(path, n))]
    out = []
    for n in (first + files + dirs)[:cap]:
        p = os.path.join(path, n)
        isdir = os.path.isdir(p)
        if isdir:
            readme, rfile = _purpose_of_dir(p, n)
        else:
            readme, rfile = _purpose_of_file(p), n
        purpose = _tc(conv[n]) if n in conv else (readme or _t(
            "agents.n.other_dir" if isdir else "agents.n.other_file"))
        out.append({"name": n, "label": n + ("/" if isdir else ""),
                    "depth": 1, "path": p, "dir": isdir,
                    "key": parent + "/" + n, "purpose": purpose,
                    "src": "conv" if n in conv else ("readme" if readme else "none"),
                    "readme": readme, "readme_file": rfile if readme else "",
                    "count": _count(p, [2000]) if isdir else None})
    return out


def brain_model(cfg, nodes):
    """Modelo para brain_view.render (el mapa de creación de agentes) con
    los archivos REALES del cerebro: carpeta → hasta 3 hojas + propósito."""
    branches = []
    tops = [n for n in nodes if n["depth"] == 0 and n["name"] in dict(_KNOWN)]
    for top in tops:
        name = top["name"]
        if not top["dir"]:
            branches.append((top["label"], [(name, top["purpose"])]))
            continue
        kids = [(c["label"], c["purpose"]) for c in nodes
                if c["depth"] == 1 and c["key"].startswith(name + "/")]
        if not kids:
            try:
                ls = sorted(x for x in os.listdir(top["path"])
                            if not x.startswith((".", "_")))
            except OSError:
                ls = []
            pick = [x for x in ("index.md", "INDEX-LITE.md", "README.md",
                                "agent.json", "settings.local.json",
                                "claude-code.md") if x in ls] or ls
            kids = [(x, top["purpose"]) for x in pick[:3]]
        branches.append((top["label"], kids))
    return {"name": str(cfg.get("display") or cfg.get("name") or "?"),
            "preview": False, "branches": branches}


def skills(brain):
    """[{cat, name, desc, path, dir}] del cerebro, por categoría y nombre."""
    root = os.path.join(brain or "", "skills")
    if not brain or not os.path.isdir(root):
        return []
    try:
        import skill_meta
        dirs = list(skill_meta.iter_skill_dirs(root))
        files = skill_meta.SKILL_FILES
    except Exception:
        return []
    out = []
    for d in dirs:
        rel = os.path.relpath(d, root).replace(os.sep, "/")
        f = next((os.path.join(d, x) for x in files
                  if os.path.isfile(os.path.join(d, x))), "")
        fm = frontmatter(_read_head(f, 8192)) if f else {}
        cat, _, nm = rel.rpartition("/")
        desc = " ".join(str(fm.get("description") or "").split())
        head = "" if desc or not f else _first_heading(_read_head(f, 8192))
        out.append({"cat": cat or "·", "name": fm.get("name") or nm,
                    "desc": desc or head, "desc_head": bool(head),
                    "path": f, "dir": d})
    out.sort(key=lambda s: (s["cat"].lower(), s["name"].lower()))
    return out


def _proposals(brain):
    p = os.path.join(brain or "", "skills", "_propuestas")
    try:
        return len([x for x in os.listdir(p) if os.path.isdir(os.path.join(p, x))])
    except OSError:
        return 0


def _catalog_file(brain):
    for fn in ("INDEX-LITE.md", "README.md"):
        if os.path.isfile(os.path.join(brain or "", "skills", fn)):
            return fn
    return "README.md"


def wired_events(brain):
    """Eventos del motor cableados al runner de WORKSPACE en el
    .claude/settings.local.json REAL del cerebro (lo que escribió install)."""
    p = os.path.join(brain or "", ".claude", "settings.local.json")
    try:
        with open(p, encoding="utf-8") as fh:
            hooks = (json.load(fh) or {}).get("hooks") or {}
    except Exception:
        return []
    out = []
    for ev, groups in hooks.items():
        try:
            if "workspace_hook.py" in json.dumps(groups):
                out.append(ev)
        except Exception:
            continue
    return out


def socio(brain):
    try:
        import sessions_registry
        return sessions_registry.socio(brain) if brain else ""
    except Exception:
        return ""


def path_rows(cfg):
    """[(id, label, path, kind)] — rutas RESUELTAS como las usa el código."""
    brain = cfg.get("_brain") or ""
    soc = socio(brain) or _t("agents.p.socio_ph")
    home_ws = os.path.join(os.path.expanduser("~"), ".claude", "workspace")
    try:
        import session_paths
        tdir = session_paths.session_dir(brain) if brain else ""
        enc = os.path.basename(tdir)
    except Exception:
        tdir, enc = "", ""
    try:
        import dispatch
        plocal = dispatch._paths_local()
    except Exception:
        plocal = os.path.join(home_ws, "paths.local.json")
    try:
        import memory_index
        fts = memory_index.db_path(brain) if brain else ""
    except Exception:
        fts = ""
    try:
        import sessions_registry
        tabs = sessions_registry.local_store_path()
    except Exception:
        tabs = os.path.join(home_ws, "sessions-local.json")
    sess = os.path.join(brain, "STATE", "sessions", soc)
    B = "brain"
    rows = [("root", "agents.p.root", brain, B),
            ("def", "agents.p.def", os.path.join(cfg.get("_dir") or "", "agent.json")
             if cfg.get("_dir") else "", "def"),
            ("sessions", "agents.p.sessions", sess, B)]
    if _continuity():
        rows.append(("checkpoints", "agents.p.checkpoints",
                     os.path.join(sess, "checkpoints"), B))
    rows += [("inbox", "agents.p.inbox", os.path.join(brain, "STATE", "inbox"), B),
             ("memory", "agents.p.memory", os.path.join(brain, "STATE", "MEMORY.md"), B),
             ("index", "agents.p.index", os.path.join(brain, "STATE", "INDEX.md"), B),
             ("destilado", "agents.p.destilado",
              os.path.join(brain, "STATE", "DESTILADO.md"), B),
             ("hooks", "agents.p.hooks",
              os.path.join(brain, ".claude", "settings.local.json"), "local"),
             ("socio", "agents.p.socio", os.path.join(brain, ".claude", "socio.local"),
              "local"),
             ("pathslocal", "agents.p.pathslocal", plocal, "machine"),
             ("tabs", "agents.p.tabs", tabs, "machine"),
             ("backup", "agents.p.backup",
              os.path.join(home_ws, "transcripts-backup", enc) if enc else "", "machine")]
    if _continuity() and brain:
        key = hashlib.sha256(os.path.realpath(brain).encode()).hexdigest()
        rows.append(("receipts", "agents.p.receipts",
                     os.path.join(home_ws, "continuity", key + ".json"), "machine"))
    rows += [("fts", "agents.p.fts", fts, "machine"),
             ("transcripts", "agents.p.transcripts", tdir, "engine")]
    if not brain:
        rows = [r for r in rows if r[3] not in (B, "local")]
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# CONTENIDO POR SECCIÓN: items (caja izq) + detalle (caja der) + mapa
# ═══════════════════════════════════════════════════════════════════════════

def _transport(cfg):
    try:
        import dispatch
        return dispatch.brain_transport(cfg.get("name", ""))
    except Exception:
        return "obsidian-sync"


def _transport_label(cfg):
    return "Obsidian Sync" if _transport(cfg) == "obsidian-sync" else "git"


def config_items(cfg):
    """Filas de la caja CONFIGURACIÓN: ({'g'}) grupos y campos
    {id, label, value, x} con el valor efectivo y su fuente."""
    name = cfg.get("name", "")
    brain = cfg.get("_brain") or ""
    items = [{"g": _t("agents.g.identity")},
             {"id": "name", "label": _t("agents.f.name"), "value": name},
             {"id": "display", "label": _t("agents.f.display"),
              "value": str(cfg.get("display") or _t("agents.none"))},
             {"id": "tagline", "label": _t("agents.f.tagline"),
              "value": str(cfg.get("tagline") or _t("agents.none"))},
             {"g": _t("agents.g.engine")}]
    try:
        import harnesses
        eng, src = harnesses.binding(name, cfg.get("engine") or "")
    except Exception:
        eng, src = (cfg.get("engine") or "claude-code"), "agente"
    items.append({"id": "engine", "label": _t("agents.f.engine"),
                  "value": "%s · %s" % (eng, _t("agents.v.src_local") if src == "local"
                                         else _t("agents.v.src_agent")),
                  "engine": eng})
    try:
        import settings
        model = settings.get("agentes.%s.model" % name.lower(), "") or ""
    except Exception:
        model = ""
    items.append({"id": "model", "label": _t("agents.f.model"),
                  "value": model.strip() if isinstance(model, str) and model.strip()
                  else _t("agents.v.model_none")})
    items.append({"g": _t("agents.g.brain")})
    bsrc = _t("agents.v.src_paths") if cfg.get("_brain_src") == "paths" \
        else _t("agents.v.src_agent")
    mark = "" if brain and os.path.isdir(brain) else " ✗"
    items.append({"id": "brain", "label": _t("agents.f.brain"),
                  "value": "%s%s · %s" % (_home(brain) or _t("agents.none"), mark, bsrc)})
    try:
        import dispatch
        obs = dispatch.obsidian_sync_enabled(brain)
    except Exception:
        obs = False
    items.append({"id": "transport", "label": _t("agents.f.transport"),
                  "value": "%s · %s" % (_transport_label(cfg),
                                        _t("agents.v.obsidian_on") if obs
                                        else _t("agents.v.obsidian_off"))})
    items.append({"g": _t("agents.g.setup")})
    try:
        import events
        setup = events.setup_of(cfg)
    except Exception:
        setup = {"session_journal": True, "autonomous": True}
    declared = cfg.get("setup") if isinstance(cfg.get("setup"), dict) else {}
    for k in ("session_journal", "autonomous"):
        items.append({"id": "journal" if k == "session_journal" else "autonomous",
                      "label": _t("agents.f.journal" if k == "session_journal"
                                  else "agents.f.autonomous"),
                      "value": "%s · %s" % ("true" if setup.get(k) else "false",
                                            _t("agents.v.declared") if k in declared
                                            else _t("agents.v.default"))})
    items.append({"g": _t("agents.g.access")})
    have_sbx = _sandbox_available()
    pol = None
    if have_sbx and not cfg.get("_missing_def"):
        try:
            import agent_sandbox
            pol = agent_sandbox.policy(cfg)
        except Exception:
            pol = None
    if not have_sbx:
        sval = _t("agents.v.sandbox_absent")
    elif pol:
        srcs = {"agent": _t("agents.v.src_agent"), "local": _t("agents.v.src_local"),
                "legacy": _t("agents.v.default"), "once": "1×", "cli": "cli"}
        sval = "%s · %s" % (_t("agents.v.on") if pol.get("enabled") else _t("agents.v.off"),
                            srcs.get(pol.get("source"), pol.get("source", "")))
    else:
        sval = _t("agents.none")
    items.append({"id": "sandbox", "label": _t("agents.f.sandbox"), "value": sval})
    try:
        import personalidad
        tone = personalidad.resumen(name) or _t("agents.v.tone_neutral")
    except Exception:
        tone = _t("agents.none")
    items.append({"id": "tone", "label": _t("agents.f.tone"), "value": tone})
    items.append({"g": _t("agents.g.def")})
    defp = os.path.join(cfg.get("_dir") or "", "agent.json") if cfg.get("_dir") else ""
    items.append({"id": "defpath", "label": _t("agents.f.defpath"),
                  "value": _home(defp) or _t("agents.none")})
    decl = cfg.get("scripts") or {}
    try:
        import dispatch
        exp = dispatch.expand_scripts(cfg, brain) if brain else {}
    except Exception:
        exp = {}
    ok = sum(1 for k in decl if exp.get(k) and os.path.exists(exp[k]))
    items.append({"id": "scripts", "label": _t("agents.f.scripts"),
                  "value": (_t("agents.v.scripts_n", ok=ok, n=len(decl))
                            + (" · " + " ".join(sorted(decl)) if decl else ""))})
    env = cfg.get("session_env") or ""
    items.append({"id": "tabenv", "label": _t("agents.f.tabenv"),
                  "value": ("%s + WORKSPACE_WS" % env) if env else "WORKSPACE_WS"})
    return items


def _gated_by(req):
    try:
        import events
        return [l["script"] + " (" + l["event"] + ")" for l in events.LISTENERS
                if l.get("requires") == req]
    except Exception:
        return []


def config_detail(item):
    x = "agents.x." + item["id"]
    if item["id"] == "sandbox" and not _sandbox_available():
        return item["value"], [("agents.d.what", _t(x + ".absent"))]
    blocks = [("agents.d.what", _t(x)), ("agents.d.where", _t(x + ".where"))]
    if (x + ".effect") in _ES:
        blocks.append(("agents.d.effect", _tc(x + ".effect")))
    if item["id"] == "journal":
        g = _gated_by("session_journal")
        if g:
            blocks.append(("agents.d.code", " · ".join(g)))
    blocks.append(("agents.d.edit", _t(x + ".edit")))
    return item["value"], blocks


def brain_items(nodes):
    return [{"id": n["key"], "label": ("  " * n["depth"]) + n["label"],
             "value": n["purpose"], "node": n} for n in nodes]


def brain_detail(node):
    blocks = [("agents.d.what", node["purpose"] + "  ("
               + (_t("agents.n.purpose_conv") if node["src"] == "conv"
                  else _t("agents.n.purpose_readme", file=node.get("readme_file") or "")
                  if node["src"] == "readme" else _t("agents.none")) + ")")]
    if node["src"] == "conv" and node.get("readme"):
        blocks.append(("agents.d.contents",
                       _t("agents.n.purpose_readme", file=node["readme_file"])
                       + ": " + node["readme"]))
    blocks.append(("agents.d.where", node["path"]))
    if node.get("dir"):
        n_md = node.get("count")
        try:
            kids = len([x for x in os.listdir(node["path"]) if not x.startswith(".")])
        except OSError:
            kids = 0
        blocks.append(("agents.d.contents", _t("agents.n.children", n=kids)
                       + (" · " + _t("agents.n.files", n=n_md) if n_md is not None else "")))
    top = node["key"].split("/")[0]
    blocks.append(("agents.d.reads", _tc(_READS.get(top, "agents.n.reads.other"))))
    if node.get("truncated"):
        blocks.append(("agents.d.contents", _t("agents.n.truncated")))
    return node["key"], blocks


def skill_items(sk):
    out, last = [], None
    for s in sk:
        if s["cat"] != last:
            out.append({"g": s["cat"]})
            last = s["cat"]
        out.append({"id": s["cat"] + "/" + s["name"], "label": s["name"],
                    "value": s["desc"] or _t("agents.s.nodesc"), "skill": s})
    return out


def skill_detail(s, brain):
    what = s["desc"] or _t("agents.s.nodesc")
    if s.get("desc_head"):
        what += "  " + _t("agents.s.from_heading", file=os.path.basename(s["path"]))
    blocks = [("agents.d.what", what),
              ("agents.s.cat", s["cat"]),
              ("agents.s.path", s["path"])]
    try:
        import skill_meta
        r = skill_meta.check_skill(s["dir"], base_dir=brain)
        if not r.get("requires"):
            req = _t("agents.s.req_none")
        elif r.get("available"):
            req = _t("agents.s.req_ok")
        else:
            req = _t("agents.s.req_missing", what=", ".join(map(str, r.get("missing") or [])))
        blocks.append(("agents.s.req", req))
    except Exception:
        pass
    return s["name"], blocks


def path_items(cfg):
    groups = {"brain": "agents.p.k.brain", "def": "agents.p.k.brain",
              "local": "agents.p.k.brain", "machine": "agents.p.k.machine",
              "engine": "agents.p.k.engine"}
    out, last = [], None
    for pid, lk, p, kind in path_rows(cfg):
        g = groups[kind]
        if g != last:
            out.append({"g": _t(g)})
            last = g
        ex = bool(p) and os.path.exists(p)
        brain = cfg.get("_brain") or ""
        shown = _home(p)
        if brain and p and pid != "root" and p.startswith(brain + os.sep):
            shown = os.path.relpath(p, brain).replace(os.sep, "/")
        out.append({"id": pid, "label": _t(lk), "value": shown or _t("agents.none"),
                    "ok": ex, "path": p, "kind": kind})
    return out


def path_detail(item, cfg):
    x = _t("agents.p.x." + item["id"], transport=_transport_label(cfg))
    st = _t("agents.exists") if item["ok"] else _t("agents.missing")
    sync = {"brain": _t("agents.p.k.brain") + " · " + _transport_label(cfg),
            "def": _t("agents.p.k.brain") + " · " + _transport_label(cfg),
            "local": _t("agents.m.sync.d.brain3"),
            "machine": _t("agents.p.k.machine"),
            "engine": _t("agents.p.k.engine")}[item["kind"]]
    if item["kind"] == "def" and not str(item["path"]).startswith(
            str(cfg.get("_brain") or "\0")):
        sync = _t("agents.m.sync.d.harn1")
    blocks = [("agents.d.what", x),
              ("agents.d.where", (item["path"] or _t("agents.none")) + "  · " + st),
              ("agents.d.sync", sync)]
    return item["label"], blocks


# ── CICLO: pasos reales, agrupados por flujo, cada uno con su carril ──────
_STEPS = {
    "boot": (("pick", 0), ("launch", 0), ("hooks", 1), ("listeners", 1),
             ("ctx", 1), ("read", 2)),
    "save": (("cp", 0), ("cas", 0), ("cpstore", 0), ("flush", 1), ("end", 1),
             ("receipt", 1), ("dream", 2)),
    "retrieve": (("rboot", 0), ("rindex", 1), ("rwiki", 1), ("rfts", 2)),
    "sync": (("sbrain", 0), ("smach", 0), ("sharn", 0)),
}
# Sin el subsistema de continuidad, GUARDAR es lo que existe: el agente
# escribe el journal de su pestaña (primario), los hooks dejan red de
# seguridad y dream destila en frío. Sin checkpoints ni recibos.
_STEPS_NOCP = {
    "save": (("journal", 0), ("flush", 1), ("end", 1), ("dream", 2)),
}


def _steps(flow):
    if not _continuity():
        return _STEPS_NOCP.get(flow, _STEPS[flow])
    return _STEPS[flow]


def _listener_lines(cfg, event):
    """Los listeners REALES de `event` (events.LISTENERS) con su estado para
    ESTE agente: activo / apagado por setup / script ausente."""
    try:
        import events
        setup = events.setup_of(cfg)
        out = []
        for l in events.listeners_for(event):
            present = os.path.isfile(os.path.join(ROOT, "hooks", l["script"]))
            if not present:
                st = _t("agents.l.missing")
            elif events.gated(l, setup):
                st = _t("agents.l.gated", req=l.get("requires"))
            else:
                st = _t("agents.l.on")
            out.append("%s · %s" % (l["script"], st))
        return out
    except Exception:
        return []


def cycle_items():
    out = []
    for f in FLOWS:
        out.append({"g": _t("agents.flow." + f)})
        for sid, lane in _steps(f):
            out.append({"id": sid, "label": _tc("agents.st." + sid), "value": "",
                        "flow": f, "lane": lane})
    return out


def cycle_detail(item, cfg):
    sid = item["id"]
    tr = _transport_label(cfg)
    blocks = [("agents.d.what", _tc("agents.st.%s.x" % sid, transport=tr))]
    if sid in ("listeners", "end"):
        ev = "session_start" if sid == "listeners" else "session_end"
        for ln in _listener_lines(cfg, ev):
            blocks.append((None, "· " + ln))
    if sid == "hooks":
        wired = wired_events(cfg.get("_brain"))
        blocks.append(("agents.d.where",
                       _t("agents.wired", events=", ".join(wired)) if wired
                       else _t("agents.wired_none")))
    blocks.append(("agents.d.code", _tc("agents.st.%s.src" % sid)))
    return item["label"], blocks


# ═══════════════════════════════════════════════════════════════════════════
# MAPAS (reuso: brain_view.render / pipeline / fan sobre _MapCanvas)
# ═══════════════════════════════════════════════════════════════════════════

class _API:
    HL = HL


class _FallbackCanvas:
    """Clon mínimo de agent_create_ui._MapCanvas si aquel no importa."""
    def __init__(self, api, K, width, height):
        self.api, self.K, self.width, self.height = api, K, width, height
        self.cells = [[[" ", K["DK"]] for _ in range(width)] for _ in range(height)]

    def put(self, x, y, value, color=None, limit=None):
        if not 0 <= y < self.height:
            return
        text = HL.clip(" ".join(str(value).split()),
                       limit if limit is not None else max(0, self.width - x))
        for ch in text:
            size = HL.vis(ch)
            if size == 0:
                continue
            if 0 <= x and x + size <= self.width:
                self.cells[y][x] = [ch, color or self.K["WH"]]
                for c in range(1, size):
                    self.cells[y][x + c] = ["", color or self.K["WH"]]
            x += size

    def edge(self, x1, y1, x2, y2, active=True):
        col = self.K["B2"] if active else self.K["DK"]
        if y1 == y2:
            for x in range(min(x1, x2), max(x1, x2) + 1):
                self.put(x, y1, "─", col)
        elif x1 == x2:
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.put(x1, y, "│", col)

    def lines(self):
        out = []
        for row in self.cells:
            s, prev = "", None
            for ch, col in row:
                if col != prev:
                    s += self.K["R"] + col
                    prev = col
                s += ch
            out.append(s + self.K["R"])
        return out


def _canvas_type():
    try:
        from agent_create_ui import _MapCanvas
        return _MapCanvas
    except Exception:
        return _FallbackCanvas


def _mk(K, w, h):
    return _canvas_type()(_API, K, w, h)


def _pad(lines, ih):
    return list(lines[:ih]) + [""] * max(0, ih - len(lines))


def _center(K, txt, iw, col=None):
    t = HL.clip(txt, max(1, iw - 2))
    return " " * max(0, (iw - HL.vis(t)) // 2) + (col or K["DIM"]) + t + K["R"]


def _lanes_text(K, lanes, active, iw, base=0):
    out = []
    for i, (title, nodes, _caps) in enumerate(lanes):
        on = i == active
        chain = " → ".join(str(n[0]).partition("|")[2] or str(n[0]) for n in nodes)
        col = (K["C"] + K["BO"]) if on else K["DK"]
        out.append(HL.clip(" %s%d · %s%s" % (col, base + i + 1, title, K["R"]), iw))
        out.append(HL.clip("   %s%s%s" % (K["WH"] if on else K["DK"], chain, K["R"]), iw))
    return out


def lanes_map(K, iw, ih, lanes, active, nota):
    """Carriles apilados (título + mini-pipeline): el carril activo con sus
    colores, el resto en grises (ilumina sólo el camino elegido). Si no caben
    todos, ventana alrededor del activo + aviso; angosto → texto."""
    if ih <= 0:
        return []
    per = 5
    room = ih - 1
    nfit = room // per if iw >= 44 else 0
    if nfit <= 0:
        txt = _lanes_text(K, lanes, active, iw)
        if len(txt) > ih:                        # el activo SIEMPRE visible
            txt = txt[2 * active:2 * active + ih]
        return _pad(txt, ih)
    start = 0
    if nfit < len(lanes):
        start = max(0, min(active, len(lanes) - nfit))
    out = []
    for i in range(start, min(len(lanes), start + nfit)):
        title, nodes, caps = lanes[i]
        on = i == active
        col = (K["C"] + K["BO"]) if on else K["DK"]
        out.append(HL.clip(" %s%d · %s%s" % (col, i + 1, title, K["R"]), iw))
        nc = nodes if on else [(n[0], "dk") for n in nodes]
        pl = brain_view.pipeline(HL, K, _mk, iw, 4, nc, caps, "")
        if pl is None:
            pl = _lanes_text(K, [lanes[i]], 0 if on else -1, iw, base=i)[1:] + ["", "", ""]
        out += pl[:4]
    shown = set(range(start, min(len(lanes), start + nfit)))
    for i in range(len(lanes)):                  # sobra alto: el resto en texto
        if i not in shown and (ih - 1) - len(out) >= 2:
            out += _lanes_text(K, [lanes[i]], -1, iw, base=i)
            shown.add(i)
    hidden = len(lanes) - len(shown)
    if hidden > 0:
        nota = "+%d · %s" % (hidden, nota)
    out = _pad(out, ih - 1)
    out.append(_center(K, nota, iw))
    return out


def _flow_lanes(flow, cfg):
    eng = None
    for it in config_items(cfg):
        if it.get("id") == "engine":
            eng = it.get("engine")
    eng = eng or "claude-code"
    cont = _continuity()
    if flow == "boot":
        return [
            (_t("agents.lane.boot1"),
             (("dashboard --pick|" + _t("agents.n.picker"), "b2"),
              (_t("agents.n.launch"), "c"), (eng, "c")),
             (_t("agents.c.pick"), _t("agents.c.cd"))),
            (_t("agents.lane.boot2"),
             ((eng, "c"), ("workspace_hook.py|" + _t("agents.n.hook"), "b"),
              ("neutral_hooks.py|" + _t("agents.n.neutral"), "b"),
              (_t("agents.n.ctx"), "ok")),
             (_t("agents.c.start"), _t("agents.c.run"), _t("agents.c.inject"))),
            (_t("agents.lane.boot3"),
             (("CLAUDE.md", "c"), (_t("agents.n.boot_dir"), "c"),
              (_t("agents.n.memidx"), "b")),
             (_t("agents.c.reads"), _t("agents.c.then"))),
        ]
    if flow == "save":
        if cont:
            primary = (_t("agents.lane.save1"),
                       ((_t("agents.n.work"), "wh"), (_t("agents.n.memoria"), "c"),
                        (_t("agents.n.cas"), "b"), (_t("agents.n.cpfile"), "ok")),
                       (_t("agents.c.cli"), _t("agents.c.cas"), _t("agents.c.atomic")))
        else:                                    # lo que existe: el journal
            primary = (_t("agents.lane.save1.nocp"),
                       ((_t("agents.n.work"), "wh"), (_t("agents.n.tabjournal"), "c"),
                        (_t("agents.m.cfg.brain"), "ok")),
                       (_t("agents.c.append"), _t("agents.c.livesin")))
        return [
            primary,
            (_t("agents.lane.save2"),
             ((_t("agents.n.compact") + " · " + _t("agents.n.close") + "|"
               + _t("agents.n.close"), "wh"),
              (_t("agents.n.backup"), "b2"), (_t("agents.n.journal"), "ok")),
             ("memory_flush · transcript_backup|" + _t("agents.c.end"),
              _t("agents.c.breadcrumb"))),
            (_t("agents.lane.save3"),
             ((_t("agents.n.backup"), "b2"), (_t("agents.n.dream"), "b"),
              (_t("agents.m.n.destilado"), "b"), ("MEMORY.md", "ok")),
             (_t("agents.c.reads"), _t("agents.c.distill"), _t("agents.c.review"))),
        ]
    if flow == "retrieve":
        if cont:
            first = (_t("agents.lane.ret1"),
                     ((_t("agents.n.checkpoint"), "c"), (_t("agents.n.tabmem"), "b2"),
                      (_t("agents.n.ctx"), "ok")),
                     (_t("agents.c.fallback"), _t("agents.c.inject")))
        else:                                    # la memoria de la pestaña
            first = (_t("agents.lane.ret1.nocp"),
                     ((_t("agents.n.tabjournal"), "c"), (_t("agents.n.tabmem"), "b2"),
                      (_t("agents.n.ctx"), "ok")),
                     (_t("agents.c.trim"), _t("agents.c.inject")))
        return [
            first,
            (_t("agents.lane.ret2"),
             ((_t("agents.n.question"), "wh"), (_t("agents.m.n.index"), "c"),
              (_t("agents.n.file"), "ok")),
             (_t("agents.c.lookup"), _t("agents.c.open"))),
            (_t("agents.lane.ret3"),
             ((_t("agents.m.n.index"), "dk"), (_t("agents.n.fts"), "b"),
              (_t("agents.n.grep"), "b2")),
             (_t("agents.c.query"), _t("agents.c.miss"))),
        ]
    return []


def sync_map(K, iw, ih, cfg, focus=None):
    """El panorama de sync con el lenguaje del grupo «se queda» del dev panel:
    tres nodos (cerebro / esta máquina / harness) con sus hojas en rama."""
    tr = _transport_label(cfg)
    nota = _t("agents.m.sync.note", transport=tr)
    groups = [
        ("brain", _t("agents.m.sync.brain") + " · " + tr, K["OK"],
         [(_t("agents.m.sync.l.brain1"), _t("agents.m.sync.d.brain1")),
          (_tc("agents.m.sync.l.brain2"), _tc("agents.m.sync.d.brain2")),
          (_t("agents.m.sync.l.brain3"), _t("agents.m.sync.d.brain3"))]),
        ("machine", _t("agents.m.sync.machine"), K["B2"],
         [(_t("agents.m.sync.l.mach1"), _t("agents.m.sync.d.mach1")),
          (_t("agents.m.sync.l.mach2"), _t("agents.m.sync.d.mach2")),
          (_tc("agents.m.sync.l.mach3"), _t("agents.m.sync.d.mach3"))]),
        ("harness", _t("agents.m.sync.harness") + " · git", K["C"],
         [(_t("agents.m.sync.l.harn1"), _t("agents.m.sync.d.harn1"))]),
    ]
    if ih >= 12 and iw >= 64:
        gw = max(HL.vis(g[1]) for g in groups) + 4
        span = min(iw, gw + 3 + 34 + 46)
        o = max(0, (iw - span) // 2)
        c = _mk(K, iw, ih)
        y = 0
        for gid, label, col, leaves in groups:
            on = focus in (None, gid)
            gc = col if on else K["DK"]
            brain_view.fan(c, HL, K, o, y, gw, label,
                           [(n, d, gc) for n, d in leaves], gc, o + span)
            y += max(3, len(leaves)) + 1
        out = c.lines()[:ih - 1]
        out = _pad(out, ih - 1)
        out.append(_center(K, nota, iw))
        return out
    out = []
    for gid, label, col, leaves in groups:
        on = focus in (None, gid)
        gc = col if on else K["DK"]
        out.append(HL.clip(" %s%s%s  %s%s%s" % (
            gc + K["BO"], label, K["R"], K["WH"] if on else K["DK"],
            " · ".join(n for n, _ in leaves), K["R"]), iw))
    if ih > len(out):
        out.append(_center(K, nota, iw))
    return _pad(out, ih)


def config_map(K, iw, ih, cfg, focus_id=None):
    eng = "claude-code"
    for it in config_items(cfg):
        if it.get("id") == "engine":
            eng = it.get("engine") or eng
    hi = {"name": (0, 1), "display": (1,), "tagline": (1,), "engine": (2, 3),
          "model": (3,), "brain": (2, 4), "transport": (4,), "journal": (4,),
          "autonomous": (4,), "sandbox": (2,), "tone": (4,), "defpath": (1,),
          "scripts": (2,), "tabenv": (2, 3)}.get(focus_id, ())
    labels = [("registry.json|" + _t("agents.m.cfg.reg")), "agent.json",
              "dispatch", eng, _t("agents.m.cfg.brain")]
    nodes = [(lb, "c" if i in hi else "b2") for i, lb in enumerate(labels)]
    caps = (_t("agents.m.cfg.c1"), _t("agents.m.cfg.c2"), _t("agents.m.cfg.c3"),
            _t("agents.m.cfg.c4"))
    return _simple_pipeline(K, iw, ih, nodes, caps, _t("agents.m.cfg.note"))


def skills_map(K, iw, ih, brain, sel=None):
    nodes = (("CLAUDE.md", "c"), (_catalog_file(brain), "b"),
             ((("%s/%s/" % (sel["cat"], os.path.basename(sel["dir"]))) if sel else "")
              + os.path.basename((sel or {}).get("path") or "SKILL.md")
              + "|" + os.path.basename((sel or {}).get("path") or "SKILL.md"), "ok"),
             ("skill_review.py|" + _t("agents.m.sk.review"), "b2"))
    caps = (_t("agents.m.sk.c1"), _t("agents.m.sk.c2"), _t("agents.m.sk.c3"))
    return _simple_pipeline(K, iw, ih, nodes, caps, _t("agents.m.sk.note"))


def _simple_pipeline(K, iw, ih, nodes, caps, nota):
    """Un carril: el mini-pipeline del dev panel. Alto < 6 → sin nota; si no
    cabe → texto «a → b → c» con honestidad."""
    pl = brain_view.pipeline(HL, K, _mk, iw, max(4, min(ih, 6)), nodes, caps,
                             nota if ih >= 6 else "") if ih >= 4 else None
    if pl is None:
        chain = " → ".join(str(n[0]).partition("|")[2] or str(n[0]) for n in nodes)
        out = [HL.clip(" %s%s%s" % (K["C"] + K["BO"], chain, K["R"]), iw)]
        if ih > 1:
            out += [HL.clip(" %s%s%s" % (K["DIM"], ln, K["R"]), iw)
                    for ln in _wrap(nota, iw - 2)[:ih - 1]]
        return _pad(out, ih)
    top = max(0, (ih - len(pl)) // 2)
    return _pad([""] * top + pl, ih)


def brain_map(K, iw, ih, cfg, nodes):
    if not nodes:
        return _pad([HL.clip(" %s%s%s" % (K["DIM"], ln, K["R"]), iw) for ln in
                     _wrap(_t("agents.nobrain", path=_home(cfg.get("_brain"))), iw - 2)], ih)
    model = brain_model(cfg, nodes)
    if iw < 60:                                  # brain_view cede a 1 línea: texto
        cols = [K["C"], K["C"], K["B"], K["B2"], K["OK"]]
        out = [HL.clip(" %s%s%s %s%s%s" % (
            cols[min(i, 4)] + K["BO"], lab, K["R"], K["DIM"],
            " · ".join(x for x, _ in kids[:4]), K["R"]), iw)
            for i, (lab, kids) in enumerate(model["branches"])]
        return _pad(out, ih)
    lines = brain_view.render(model, _API, K, _canvas_type(), iw, ih, "setup")
    return _pad(lines, ih)


# ═══════════════════════════════════════════════════════════════════════════
# RENDER
# ═══════════════════════════════════════════════════════════════════════════

def _wrap(text, width):
    return textwrap.wrap(str(text), max(8, width), break_long_words=True) or [""]


def _divisor(K, txt, w):
    """`titulo ────` — encabezado de sub-sección (versalita + regla tenue)."""
    regla = K["SEP"] * max(1, w - HL.vis(txt) - 3)
    return HL.clip(" %s%s%s %s%s%s" % (K["DK"] + K["BO"], str(txt), K["R"],
                                       K["DK"], regla, K["R"]), w)


def pares():
    """LA fila de atajos: vive SOLO en el pie (sin repetirla en la cabecera
    ni junto a la tira de agentes — una instrucción, un lugar)."""
    return (("Tab", _t("agents.hint.agent")), ("◄►", _t("agents.hint.section")),
            ("↑↓", _t("agents.hint.item")), ("1-5", _t("agents.hint.direct")),
            (_t("agents.hint.space"), _t("agents.hint.scroll")),
            ("q", _t("agents.hint.back")))


def initial(name=None):
    items = agents()
    idx = next((i for i, c in enumerate(items) if c.get("name") == name), 0)
    return {"agents": items, "index": idx, "sec": 0, "row": 0, "xoff": 0,
            "msg": "", "cache": {}}


def _data(S):
    cfg = S["agents"][S["index"]]
    key = cfg.get("name", "")
    c = S["cache"].get(key)
    if c is None:
        brain = cfg.get("_brain") or ""
        c = {"nodes": brain_tree(brain), "skills": skills(brain)}
        S["cache"][key] = c
    return cfg, c


def section_items(S):
    cfg, c = _data(S)
    sec = SECS[S["sec"]]
    if sec == "config":
        return config_items(cfg)
    if sec == "brain":
        return brain_items(c["nodes"])
    if sec == "skills":
        return skill_items(c["skills"])
    if sec == "paths":
        return path_items(cfg)
    return cycle_items()


def _selectable(items):
    return [i for i, it in enumerate(items) if "g" not in it]


def current(S, items=None):
    items = items if items is not None else section_items(S)
    sel = _selectable(items)
    if not sel:
        return None
    S["row"] = max(0, min(S["row"], len(sel) - 1))
    return items[sel[S["row"]]]


def _list_lines(S, K, items, iw):
    """Caja izquierda: grupos con divisor tenue y cursor ❯ en lo elegido.
    Devuelve (líneas, índice de la línea del cursor)."""
    sec = SECS[S["sec"]]
    cur = current(S, items)
    labw = {"config": 16, "paths": 22, "cycle": iw - 4}.get(sec)
    if labw is None:
        labw = min(max([HL.vis(it["label"]) for it in items if "g" not in it] or [8]) + 1,
                   max(10, iw // 2))
    out, anchor = [], 0
    for it in items:
        if "g" in it:
            if out:
                out.append("")
            out.append(_divisor(K, it["g"], iw))
            continue
        on = it is cur
        if on:
            anchor = len(out)
        ptr = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if on else " "
        ink = (K["WH"] + K["BO"]) if on else K["GREY"]
        lab = HL.pad(HL.clip(it["label"], labw), labw)
        val = it.get("value", "")
        if sec == "paths":
            mk = ("%s✓%s " % (K["OK"], K["R"])) if it.get("ok") \
                else ("%s∅%s " % (K["DK"], K["R"]))
            val_s = mk + "%s%s%s" % (K["WH"] if on else K["DIM"], val, K["R"])
        elif sec == "config":
            val_s = "%s%s%s" % ((K["C"] + K["BO"]) if on else K["C"], val, K["R"])
        else:
            val_s = "%s%s%s" % (K["WH"] if on else K["DIM"], val, K["R"])
        row = " %s %s%s%s" % (ptr, ink, lab, K["R"])
        if val and sec != "cycle":
            row += " " + val_s
        out.append(HL.clip(row, iw))
    return out, anchor


def _detail_lines(S, K, iw):
    cfg, c = _data(S)
    sec = SECS[S["sec"]]
    it = current(S)
    if it is None:
        msg = _t("agents.s.none") if sec == "skills" and cfg.get("_brain") \
            and os.path.isdir(cfg["_brain"]) else _t("agents.nobrain",
                                                     path=_home(cfg.get("_brain")))
        return [HL.clip(" %s%s%s" % (K["DIM"], ln, K["R"]), iw)
                for ln in _wrap(msg, iw - 2)]
    if sec == "config":
        head, blocks = config_detail(it)
    elif sec == "brain":
        head, blocks = brain_detail(it["node"])
    elif sec == "skills":
        head, blocks = skill_detail(it["skill"], cfg.get("_brain"))
    elif sec == "paths":
        head, blocks = path_detail(it, cfg)
    else:
        head, blocks = cycle_detail(it, cfg)
    out = []
    for ln in _wrap(head, iw - 2)[:2]:
        out.append(HL.clip(" %s%s%s" % (K["C"] + K["BO"], ln, K["R"]), iw))
    for title, text in blocks:
        if title is not None:
            out.append("")
            out.append(_divisor(K, _t(title), iw))
        for ln in _wrap(text, iw - 3):
            out.append(HL.clip(" %s%s%s" % (K["WH"], ln, K["R"]), iw))
    if sec == "skills" and it is not None:
        n = _proposals(cfg.get("_brain"))
        if n:
            out += ["", HL.clip(" %s%s%s" % (K["DIM"], _t("agents.s.proposals", n=n), K["R"]), iw)]
    return out


def _scrolled(S, K, lines, iw, ih):
    """Texto completo siempre accesible: espacio desplaza (como dev)."""
    if len(lines) <= ih:
        S["xoff"] = 0
        return lines
    S["_xpage"] = max(3, ih - 2)
    off = min(S.get("xoff", 0), max(0, len(lines) - ih + 1))
    S["xoff"] = off
    vis = lines[off:off + ih - 1]
    rest = len(lines) - (off + len(vis))
    vis.append(HL.clip(" %s%s%s" % (K["DK"], _t("agents.more", n=rest) if rest > 0
                                    else _t("agents.top"), K["R"]), iw))
    return vis


def _agent_strip(S, K, w):
    tabs = []
    for i, c in enumerate(S["agents"]):
        name = str(c.get("display") or c.get("name"))
        if i == S["index"]:
            tabs.append("%s%s %s %s%s" % (K["C"] + K["BO"], K["BL"], name, K["BR"], K["R"]))
        else:
            tabs.append("%s%s%s" % (K["GREY"], name, K["R"]))
    return HL.clip(" " + "   ".join(tabs), w - 1)


def _tab_strip(K, labels, active, iw, col=None):
    segs = []
    for i, lb in enumerate(labels):
        on = i == active
        segs.append(((col or K["C"]) + K["BO"] if on else K["DIM"])
                    + "[ %s ]" % lb + K["R"])
    line = "  ".join(segs)
    if HL.vis(line) > iw:                         # angosto: sin corchetes
        line = " ".join(((col or K["C"]) + K["BO"] if i == active else K["DK"])
                        + lb + K["R"] for i, lb in enumerate(labels))
    return " " * max(0, (iw - HL.vis(line)) // 2) + line


def _map_block(S, K, iw, ih):
    """(título, líneas) del mapa de la sección activa, alto exacto ih."""
    cfg, c = _data(S)
    sec = SECS[S["sec"]]
    it = current(S)
    if sec == "config":
        return _t("agents.box.config_m"), config_map(K, iw, ih, cfg, (it or {}).get("id"))
    if sec == "brain":
        return _t("agents.box.brain_m"), brain_map(K, iw, ih, cfg, c["nodes"])
    if sec == "skills":
        return _t("agents.box.skills_m"), skills_map(K, iw, ih, cfg.get("_brain"),
                                                      (it or {}).get("skill"))
    if sec == "paths":
        kind = (it or {}).get("kind")
        focus = {"brain": "brain", "def": None, "local": "brain",
                 "machine": "machine", "engine": "machine"}.get(kind)
        return _t("agents.box.paths_m"), sync_map(K, iw, ih, cfg, focus)
    flow = (it or {}).get("flow", "boot")
    strip = _tab_strip(K, [_t("agents.flow." + f) for f in FLOWS], FLOWS.index(flow), iw)
    body_h = max(0, ih - 1)
    if flow == "sync":
        focus = {"sbrain": "brain", "smach": "machine", "sharn": "harness"}.get(it["id"])
        body = sync_map(K, iw, body_h, cfg, focus)
    else:
        note = _tc("agents.note." + flow, transport=_transport_label(cfg))
        body = lanes_map(K, iw, body_h, _flow_lanes(flow, cfg), it.get("lane", 0), note)
    return _t("agents.box.cycle_m"), [strip] + body


def _map_need(S, iw=999):
    sec = SECS[S["sec"]]
    if sec in ("config", "skills"):
        return 6
    if sec == "brain":
        _cfg, c = _data(S)
        nb = len(brain_model(_cfg, c["nodes"])["branches"])
        return max(4, nb if iw < 60 else 3 * nb)
    if sec == "paths":
        return 12
    return 17                                      # tira + 3 carriles + nota


def _titles(S, cfg):
    sec = SECS[S["sec"]]
    name = str(cfg.get("display") or cfg.get("name"))
    it = current(S)
    if sec == "config":
        return _t("agents.box.config", name=name), _t("agents.box.config_d")
    if sec == "brain":
        return (_t("agents.box.brain", name=name),
                _t("agents.box.brain_d", node=(it or {}).get("label", "").strip()))
    if sec == "skills":
        return (_t("agents.box.skills", n=len(_data(S)[1]["skills"])),
                _t("agents.box.skills_d", name=(it or {}).get("label", "")))
    if sec == "paths":
        return (_t("agents.box.paths", name=name),
                _t("agents.box.paths_d", name=(it or {}).get("label", "")))
    return _t("agents.box.cycle"), _t("agents.box.cycle_d")


def _size_notice(w, h):
    try:
        import responsive_ui
        lines = responsive_ui.size_notice(word(), w, h)
    except Exception:
        lines = [word()]
    return _pad([HL.clip(l, w - 1) for l in lines], h - 1)[:h - 1]


def render(S, w, h):
    """Bloque de EXACTAMENTE h-1 líneas, cada una ≤ w-1 (altura estable)."""
    K = _K()
    w, h = max(1, int(w)), max(2, int(h))
    if w < 50 or h < 18:
        S["size_blocked"] = True
        return _size_notice(w, h)
    S["size_blocked"] = False
    P = pares()
    L = HL.screen_header(K, w, h, _t("agents.sub"), word=word(),
                         compact_h=40, refl_min_h=54)
    tail = 3                                       # '' + mensaje + pie
    if not S["agents"]:
        for ln in _wrap(_t("agents.empty"), w - 4):
            L.append(HL.clip(" %s%s%s" % (K["DIM"], ln, K["R"]), w - 1))
        L = L[:h - 1 - tail]
        L += [""] * max(0, (h - 1 - tail) - len(L))
        L += ["", "", HL.foot_hints(K, P, w)]
        return [HL.clip(x, w - 1) for x in L[:h - 1]]
    cfg, _c = _data(S)
    L.append(_agent_strip(S, K, w))
    L.append(_tab_strip(K, [_t("agents.sec." + s) for s in SECS], S["sec"], w - 1))
    if h >= 30:
        L.append("")
    avail = max(6, (h - 1) - len(L) - tail)
    items = section_items(S)
    t_izq, t_der = _titles(S, cfg)
    side = w >= 100

    if side:
        lw = max(40, min(60, (w - 6) * 42 // 100))
        rw = (w - 1) - lw - 3
        mw = w - 2
        need = _map_need(S)
        share = 55 if SECS[S["sec"]] == "cycle" else 45
        map_ih = min(need, max(3, avail * share // 100), max(3, avail - 2 - 1 - 2 - 10))
        up_ih = avail - (map_ih + 2) - 1 - 2
        lst, anchor = _list_lines(S, K, items, lw - 4)
        ini = max(0, min(anchor - up_ih // 2, len(lst) - up_ih))
        izq = HL.full_box(t_izq, lst[ini:ini + up_ih], K, lw, up_ih, True, border=K["C"])
        det = _scrolled(S, K, _detail_lines(S, K, rw - 4), rw - 4, up_ih)
        der = HL.full_box(t_der, det, K, rw, up_ih, False, border=K["B2"],
                          label=K["B"] + K["BO"])
        for i in range(up_ih + 2):
            L.append(HL.clip(" " + HL.pad(izq[i], lw) + "  " + der[i], w - 1))
        L.append("")
    else:
        mw = w - 2
        need = _map_need(S, mw - 4)
        ih_i = max(4, avail * 30 // 100)
        map_ih = max(3, min(need, avail * 32 // 100))
        ih_d = avail - ih_i - map_ih - 6 - 1
        while ih_d < 5 and map_ih > 3:
            map_ih -= 1
            ih_d += 1
        while ih_d < 5 and ih_i > 4:
            ih_i -= 1
            ih_d += 1
        lst, anchor = _list_lines(S, K, items, mw - 4)
        ini = max(0, min(anchor - ih_i // 2, len(lst) - ih_i))
        for ln in HL.full_box(t_izq, lst[ini:ini + ih_i], K, mw, ih_i, True, border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
        det = _scrolled(S, K, _detail_lines(S, K, mw - 4), mw - 4, ih_d)
        for ln in HL.full_box(t_der, det, K, mw, ih_d, False, border=K["B2"],
                              label=K["B"] + K["BO"]):
            L.append(HL.clip(" " + ln, w - 1))
        L.append("")
    mt, mlines = _map_block(S, K, mw - 4, map_ih)
    for ln in HL.full_box(mt, mlines, K, mw, map_ih, False, border=K["B2"],
                          label=K["B"] + K["BO"]):
        L.append(HL.clip(" " + ln, w - 1))
    L = L[:h - 1 - tail]
    L += [""] * max(0, (h - 1 - tail) - len(L))
    L.append("")
    msg = S.get("msg") or _t("agents.readonly")
    L.append(HL.clip(" %s%s%s" % (K["DK"], msg, K["R"]), w - 1))
    L.append(HL.foot_hints(K, P, w))
    return [HL.clip(x, w - 1) for x in L[:h - 1]]


# ═══════════════════════════════════════════════════════════════════════════
# ACCIONES Y LOOP
# ═══════════════════════════════════════════════════════════════════════════

def act(S, key):
    """True = sigue · False = vuelve al hub."""
    if key in ("q", "Q", "\x1b", "\x03"):
        return False
    if not S["agents"] or S.get("size_blocked"):
        return True
    if key == "tab":
        S["index"] = (S["index"] + 1) % len(S["agents"])
        S["row"] = S["xoff"] = 0
    elif key == "right":
        S["sec"] = (S["sec"] + 1) % len(SECS)
        S["row"] = S["xoff"] = 0
    elif key == "left":
        S["sec"] = (S["sec"] - 1) % len(SECS)
        S["row"] = S["xoff"] = 0
    elif key in tuple("12345"):
        S["sec"] = int(key) - 1
        S["row"] = S["xoff"] = 0
    elif key in ("up", "down"):
        n = len(_selectable(section_items(S)))
        if n:
            S["row"] = (S["row"] + (-1 if key == "up" else 1)) % n
        S["xoff"] = 0
    elif key == " ":
        S["xoff"] = S.get("xoff", 0) + S.get("_xpage", 6)
    return True


def _size(out=None):
    try:
        sz = os.get_terminal_size(out.fileno()) if out else shutil.get_terminal_size((110, 44))
        return sz.columns, sz.lines
    except (OSError, AttributeError, ValueError):
        sz = shutil.get_terminal_size((110, 44))
        return sz.columns, sz.lines


def _draw(out, S, first=False):
    w, h = _size(out)
    lines = render(S, w, h)
    try:
        import responsive_ui
        responsive_ui.paint(out, lines, first=first)
    except Exception:
        out.write("\033[H" + "".join("\033[2K" + ln + "\r\n" for ln in lines) + "\033[J")
        out.flush()


def run(name=None):
    """Pantalla interactiva; vuelve al hub con q/Esc. Sin tty → imprime un
    frame (diagnóstico headless) y vuelve."""
    S = initial(name)
    if not sys.stdin.isatty():
        for ln in render(S, 110, 44):
            print(ln)
        return None
    if os.name == "nt":
        return _loop_windows(S)
    return _loop_unix(S)


def _loop_unix(S):
    import select
    import termios
    import tty
    from add_agent_tui import _read_key_unix
    fd = os.open("/dev/tty", os.O_RDWR)
    out = open("/dev/tty", "w")
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        out.write("\033[?1049h\033[?25l")
        first = True
        while True:
            _draw(out, S, first)
            first = False
            if not select.select([fd], [], [], .5)[0]:
                continue
            if not act(S, _read_key_unix(fd, select)):
                return None
    finally:
        out.write("\033[?25h\033[?1049l")
        out.flush()
        out.close()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        os.close(fd)


def _loop_windows(S):
    import msvcrt
    out = sys.stdout
    out.write("\033[?1049h\033[?25l")
    try:
        first = True
        while True:
            _draw(out, S, first)
            first = False
            while not msvcrt.kbhit():
                time.sleep(.1)
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                key = {"H": "up", "P": "down", "K": "left",
                       "M": "right"}.get(msvcrt.getwch(), "")
            elif key == "\t":
                key = "tab"
            if not act(S, key):
                return None
    finally:
        out.write("\033[?25h\033[?1049l")
        out.flush()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="workspace agentes")
    ap.add_argument("agent", nargs="?")
    a = ap.parse_args(argv)
    run(a.agent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
