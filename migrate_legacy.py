#!/usr/bin/env python3
"""WORKSPACE · migrate_legacy — migración RECUPERABLE de la instalación anterior.

Antes del rename (2026-10) el producto tenía otro nombre (ver `legacy.py`, el
único lugar con esos literales). En una máquina que lo usó quedan artefactos de
INSTALACIÓN (no datos) que hoy rompen o duplican: launchers que apuntan a la
carpeta vieja, el estado per-máquina viejo bajo ~/.claude, el archivo de
funciones PowerShell viejo + líneas en el $PROFILE/~/.zshrc, hooks/statusLine
horneados con la ruta vieja, el manifiesto viejo en cerebros nunca migrados y
las variables de entorno viejas. Este módulo los trata en CINCO pasos separados:

  1. DETECTAR  (`detect()`)  — solo lectura.
  2. PLAN      (`plan_text()`) — lista legible archivo → acción/destino. Default.
  3. MIGRAR    (`apply()`)   — copia atómica a Workspace, reapunta hooks/launchers,
                 migra el manifiesto viejo→`.workspace/agent.json` SIN borrar el
                 legado; valida con checks estáticos (def válida, rutas existentes).
  4. RETIRAR   (`retire()`)  — acción aparte y explícita. Antes de quitar NADA
                 guarda una copia recuperable (carpeta con manifest.json + sha256)
                 y solo quita artefactos de instalación listados en el plan.
  5. ROLLBACK  (`rollback(backup)`) — restaura desde esa copia.

SEGURIDAD (U06): jamás se elimina un cerebro, un secreto, una sesión ni STATE por
asociación de nombre. `_protected()` es la última barrera antes de mover nada:
cerebros registrados (y lo que esté dentro), la raíz de Workspace, HOME, ~/.claude,
el estado de Workspace, transcripts (~/.claude/projects) y archivos de secretos.
Todo es idempotente: repetir apply/retire/rollback no duplica ni falla.

CLI:  workspace migrar-legado [--plan|--apply|--retire|--rollback <backup>]
                              [--yes] [--json]
Stdlib pura (3.9+), falla-suave en la detección.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

import legacy

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

IS_WIN = os.name == "nt"
MANIFEST = "manifest.json"
#: nombres de launcher que SON el comando viejo (se retiran, no se reapuntan)
LEGACY_LAUNCHERS = legacy.LAUNCHERS
#: archivos efímeros del estado viejo: no cuentan para "¿está todo copiado?"
_EPHEMERAL = re.compile(r"(\.lock|\.pid|\.tmp(-\d+)?|~)$|^__pycache__$", re.I)
#: marcadores de líneas legadas en $PROFILE (PowerShell)
_PS_LEGACY = legacy.PS_PROFILE_MARKS
_RC_FILES = (".zshrc", ".bashrc", ".bash_profile", ".profile", ".zprofile")
_SECRET_NAMES = re.compile(r"^(secrets?\.local.*|.*\.env|credentials.*|token.*)$", re.I)
#: comando de CLI que corre este módulo (para las pistas de "siguiente paso")
CLI = "workspace migrar-legado"


# ── rutas (funciones: respetan HOME parchado en tests) ───────────────────────
def _home():
    return os.path.expanduser("~")


def _state_dir():
    import paths
    return paths.workspace_dir()


def legacy_state_dir():
    return os.path.join(_home(), ".claude", legacy.STATE_SUBDIR)


def backups_root():
    # Ruta PERSISTIDA (hay respaldos reales ahí): el nombre de la subcarpeta no
    # cambia o --rollback/--backups dejarían de encontrarlos.
    return os.path.join(_state_dir(), "backups", legacy.BACKUPS_SUBDIR)


def _bindir():
    return os.path.join(_home(), ".local", "bin")


def memory_path():
    """Raíces de la instalación anterior vistas por --apply (tras reapuntar ya
    nada las menciona, pero --retire debe seguir encontrándolas). Archivo
    PERSISTIDO: su nombre no cambia (un --retire posterior lo relee)."""
    return os.path.join(_state_dir(), legacy.MIGRATION_MEMORY_FILE)


def _remembered_roots():
    try:
        with open(memory_path(), encoding="utf-8") as fh:
            r = (json.load(fh) or {}).get("legacy_roots", [])
        return [str(x) for x in r if isinstance(x, str)]
    except Exception:
        return []


def _ps_cmds_legacy():
    return os.path.join(_home(), ".claude", legacy.PS_CMDS_FILE)


def _norm(p):
    try:
        return os.path.normcase(os.path.realpath(os.path.expanduser(p)))
    except Exception:
        return os.path.normcase(os.path.abspath(p))


def _under(child, parent):
    c, p = _norm(child), _norm(parent)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def _read_text(path):
    """Texto UTF-8 estricto o None (binario/ilegible → no lo tocamos)."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tree_hashes(root):
    """{rel: sha256} de todos los archivos regulares bajo `root` (symlinks no se
    siguen: se registran como 'link:<destino>')."""
    out = {}
    for dp, dns, fns in os.walk(root, followlinks=False):
        for n in list(dns):
            full = os.path.join(dp, n)
            if os.path.islink(full):
                out[os.path.relpath(full, root)] = "link:" + os.readlink(full)
        for n in fns:
            full = os.path.join(dp, n)
            rel = os.path.relpath(full, root)
            try:
                out[rel] = ("link:" + os.readlink(full)) if os.path.islink(full) else _sha(full)
            except OSError:
                out[rel] = "unreadable"
    return out


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _atomic_copy(src, dst):
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    tmp = "%s.tmp-%d" % (dst, os.getpid())
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


# ── qué hay instalado de Workspace / qué cerebros existen ───────────────────
def workspace_installed():
    """¿Hay un comando `workspace` cableado en esta máquina? Precondición para
    QUITAR cableado viejo del perfil (si no, el socio se queda sin comando)."""
    b = _bindir()
    return any(os.path.isfile(os.path.join(b, n)) for n in ("workspace", "workspace.cmd")) \
        or os.path.isfile(os.path.join(_home(), ".claude", "workspace-cmds.ps1"))


#: registro per-máquina de agentes (dentro del estado; viejo y nuevo)
REGISTRY_FILE = "agents.local.json"


def _in_harness_agents(brain):
    """True si `brain` vive en la carpeta agents/ de un harness (cerebro interno
    del producto, no del usuario). Si ya no existe y su carpeta padre se llama
    agents/, también: era un agente in-repo de un harness que ya se borró."""
    b = os.path.abspath(os.path.expanduser(brain))
    d = b
    while True:
        parent = os.path.dirname(d)
        if parent == d:
            return False
        if os.path.basename(parent) == "agents":
            if _looks_like_harness(os.path.dirname(parent)):
                return True
            if parent == os.path.dirname(b) and not os.path.isdir(b):
                return True
        d = parent


def importable_agent(entry):
    """¿Esta entrada del registro es un agente DEL USUARIO? False para motores
    internos: nombre en dispatch.SYSTEM_AGENTS, `hidden: true` (en la entrada o
    en su definición) o cerebro dentro de la carpeta agents/ de un harness.
    Esas entradas no se traen de la instalación anterior (se copiaban tal cual
    y el doctor terminaba revisando un agente que el usuario ni conoce)."""
    if not isinstance(entry, dict):
        return True                   # forma desconocida: no la juzgamos
    try:
        import dispatch
        system = dispatch.SYSTEM_AGENTS
    except Exception:
        system = frozenset({"doctor"})
    if str(entry.get("name", "")).strip().lower() in system or entry.get("hidden") is True:
        return False
    brain = str(entry.get("brain", "") or "").strip()
    if not brain:
        return True
    b = os.path.abspath(os.path.expanduser(brain))
    for sub in (".workspace", legacy.BRAIN_SUBDIR):
        try:
            with open(os.path.join(b, sub, "agent.json"), encoding="utf-8") as fh:
                d = json.load(fh)
            if isinstance(d, dict) and d.get("hidden") is True:
                return False
            break
        except Exception:
            continue
    return not _in_harness_agents(b)


def filter_registry(data):
    """(data_filtrada, [nombres quitados]) — copia de un agents.local.json sin
    las entradas que no son del usuario (importable_agent). No muta `data`."""
    if not isinstance(data, dict) or not isinstance(data.get("agents"), list):
        return data, []
    keep, gone = [], []
    for a in data["agents"]:
        (keep if importable_agent(a) else gone).append(a)
    out = dict(data)
    out["agents"] = keep
    return out, [str((a or {}).get("name", "?")) for a in gone if isinstance(a, dict)]


def _read_json_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _brains():
    """Cerebros conocidos en esta máquina (registro per-máquina + paths.local).
    Los agentes internos (importable_agent → False) no cuentan: su "cerebro"
    vive dentro de un harness y protegerlo impedía retirar el harness viejo."""
    out, seen = [], set()
    cands = []
    try:
        import agentsreg
        cands += [a["brain"] for a in agentsreg.agents() if importable_agent(a)]
    except Exception:
        pass
    try:                                  # Z20: overrides vía el resolver único
        import brain_resolver
        cands += [str(v) for v in brain_resolver.brain_overrides().values()]
    except Exception:
        pass
    for c in cands:
        c = os.path.abspath(os.path.expanduser(c))
        if os.path.isdir(c) and _norm(c) not in seen:
            seen.add(_norm(c))
            out.append(c)
    return out


def _looks_like_brain(d):
    j = os.path.join
    return (os.path.isfile(j(d, "CLAUDE.md")) and (os.path.isdir(j(d, "BOOT"))
                                                   or os.path.isdir(j(d, "STATE")))) \
        or os.path.isfile(j(d, ".workspace", "agent.json")) \
        or os.path.isfile(j(d, legacy.BRAIN_SUBDIR, "agent.json"))


#: subárboles de un HARNESS que traen cerebros-semilla propios (no del usuario)
_HARNESS_SEEDS = ("agents", "templates", "tests")


def _contains_brain(root):
    """Primer subdirectorio de `root` que parece un cerebro, o "". En un harness
    se ignoran sus cerebros-semilla (agents/, templates/, tests/): son código del
    producto, no datos del usuario."""
    harness = _looks_like_harness(root)
    for dp, dns, _fns in os.walk(root):
        if _looks_like_brain(dp):
            return dp
        skip = {".git", "node_modules", "__pycache__"}
        if harness and dp == root:
            skip |= set(_HARNESS_SEEDS)
        dns[:] = [n for n in dns if n not in skip]
    return ""


def _looks_like_harness(d):
    return all(os.path.isfile(os.path.join(d, f)) for f in ("front.py", "dispatch.py"))


def _protected(path):
    """Razón (str) por la que `path` JAMÁS se retira, o "" si es retirable.
    Última barrera: se consulta justo antes de mover cualquier cosa."""
    if not path:
        return "ruta vacía"
    home = _home()
    for fixed, why in ((home, "es tu HOME"),
                       (os.path.join(home, ".claude"), "es ~/.claude"),
                       (_state_dir(), "es el estado de Workspace"),
                       (os.path.join(home, ".claude", "projects"), "son tus transcripts/sesiones")):
        if _norm(path) == _norm(fixed):
            return why
    if _under(path, os.path.join(home, ".claude", "projects")):
        return "está dentro de tus transcripts/sesiones"
    if _under(ROOT, path):
        return "contiene el Workspace que está corriendo"
    for b in _brains():
        if _under(path, b):
            return "está dentro de un cerebro registrado (%s)" % b
        if _under(b, path):
            return "contiene un cerebro registrado (%s)" % b
    if os.path.isfile(path) and _SECRET_NAMES.match(os.path.basename(path)):
        return "parece un archivo de secretos"
    if os.path.isdir(path):
        inner = _contains_brain(path)
        if inner:
            return "contiene algo que parece un cerebro (%s)" % inner
    return ""


# ── referencias a rutas viejas dentro de texto ──────────────────────────────
_TOKEN = re.compile(r'"([^"\r\n]+)"|\'([^\'\r\n]+)\'|([^\s"\'|&;<>(){}=]+)')


def _map_legacy_path(tok):
    """Si `tok` es una ruta que pasa por una carpeta del harness anterior o por
    el estado viejo bajo ~/.claude, devuelve (nueva_ruta, existe). Si no, None."""
    t = tok.strip()
    if not t or ("/" not in t and "\\" not in t):
        return None
    if os.path.isabs(t) and _under(t, ROOT):
        return None                      # ya es ESTE Workspace (aunque se llame como el viejo)
    parts = re.split(r"[\\/]", t)
    for i, comp in enumerate(parts):
        if comp.lower() != legacy.NAME_LOWER:
            continue
        rest = [p for p in parts[i + 1:] if p]
        if i > 0 and parts[i - 1].lower() == ".claude":
            new_root = _state_dir()
        else:
            # una carpeta con el nombre viejo que es un CEREBRO (no un harness) no es legado:
            # sus rutas son datos del usuario y jamás se reapuntan al harness.
            old_root = os.path.expanduser(t[:len("/".join(parts[:i + 1]))])
            if os.path.isdir(old_root) and _looks_like_brain(old_root) \
                    and not _looks_like_harness(old_root):
                return None
            new_root = ROOT
        new = os.path.join(new_root, *rest) if rest else new_root
        return new, os.path.exists(new)
    return None


def _rewrite_text(text):
    """Reapunta cada ruta vieja de `text` a su equivalente en Workspace.
    Devuelve (nuevo_texto, [(viejo, nuevo)], [no_resueltas])."""
    changes, unresolved = [], []

    def sub(m):
        raw = m.group(0)
        tok = m.group(1) or m.group(2) or m.group(3)
        mp = _map_legacy_path(tok)
        if not mp:
            return raw
        new, exists = mp
        if not exists:
            unresolved.append(tok)
            return raw
        if m.group(3) is not None and " " in new:
            rep = '"%s"' % new
        else:
            rep = raw.replace(tok, new)
        if rep != raw:
            changes.append((tok, new))
        return rep

    out = _TOKEN.sub(sub, text)
    return out, changes, unresolved


def _referenced_roots(text):
    """Raíces del harness anterior (no su estado bajo ~/.claude) mencionadas en `text`."""
    roots = set()
    for m in _TOKEN.finditer(text or ""):
        tok = m.group(1) or m.group(2) or m.group(3)
        if not tok or ("/" not in tok and "\\" not in tok):
            continue
        parts = re.split(r"([\\/])", tok)
        acc = ""
        for p in parts:
            acc += p
            if p.lower() == legacy.NAME_LOWER and not acc[:-len(p)].rstrip("\\/").lower().endswith(".claude"):
                roots.add(os.path.abspath(os.path.expanduser(acc)))
                break
    return roots


# ── limpieza de shells ───────────────────────────────────────────────────────
def strip_ps_profile(text):
    """Quita las líneas de la instalación anterior de un $PROFILE. Devuelve (nuevo, quitadas)."""
    kept, removed = [], []
    for ln in text.splitlines():
        (removed if any(m in ln for m in _PS_LEGACY) else kept).append(ln)
    if not removed:
        return text, []
    new = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip("\n") + "\n"
    return new, removed


def strip_rc(text):
    """Quita bloques de la instalación anterior de un rc POSIX (~/.zshrc…):
    comentarios-marcador con el nombre viejo y su `if…fi` o su `export PATH`, los
    `export` de sus variables, su `alias` y el `source` de sus funciones (literales
    en `legacy.py`). El PATH viejo solo se quita si ya existe el bloque
    PATH de Workspace (si no, ~/.local/bin quedaría fuera del PATH)."""
    lines = text.splitlines()
    has_ws_path = "WORKSPACE · PATH" in text
    out, removed, i = [], [], 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if s.startswith("#") and legacy.NAME in s:
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if "PATH" in s or (nxt.startswith("export PATH") and ".local/bin" in nxt):
                if not has_ws_path:
                    out.append(ln)
                    i += 1
                    continue
                removed.append(ln)
                i += 1
                if i < len(lines) and lines[i].strip().startswith("export PATH"):
                    removed.append(lines[i])
                    i += 1
                continue
            removed.append(ln)
            i += 1
            if nxt.startswith("if "):
                depth = 0
                while i < len(lines):
                    t = lines[i].strip()
                    removed.append(lines[i])
                    i += 1
                    if re.match(r"^if\b", t):
                        depth += 1
                    elif t == "fi":
                        depth -= 1
                        if depth <= 0:
                            break
            continue
        if re.match(legacy.RC_EXPORT_RE, ln) \
                or re.match(legacy.RC_ALIAS_RE, ln) \
                or (re.match(r"^\s*(source|\.)\s", ln) and legacy.NAME_LOWER in ln.lower()
                    and legacy.BRAIN_SUBDIR not in ln):
            removed.append(ln)
            i += 1
            continue
        out.append(ln)
        i += 1
    if not removed:
        return text, []
    new = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n") + "\n"
    return new, removed


def _ps_profiles():
    """$PROFILE candidatos bajo HOME (sin preguntarle a PowerShell: hermético).
    Cubre Documents, OneDrive\\Documentos (redirigido/localizado) y pwsh de POSIX."""
    import glob
    h = _home()
    pats = [os.path.join(h, "*", "WindowsPowerShell", "*profile*.ps1"),
            os.path.join(h, "*", "PowerShell", "*profile*.ps1"),
            os.path.join(h, "OneDrive*", "*", "WindowsPowerShell", "*profile*.ps1"),
            os.path.join(h, "OneDrive*", "*", "PowerShell", "*profile*.ps1"),
            os.path.join(h, ".config", "powershell", "*profile*.ps1")]
    seen, out = set(), []
    for pat in pats:
        for p in sorted(glob.glob(pat)):
            if os.path.isfile(p) and _norm(p) not in seen:
                seen.add(_norm(p))
                out.append(p)
    return out


# ── settings (hooks / statusLine) ────────────────────────────────────────────
def _settings_files():
    h = _home()
    out = [os.path.join(h, ".claude", "settings.json")]
    for b in _brains():
        out += [os.path.join(b, ".claude", "settings.json"),
                os.path.join(b, ".claude", "settings.local.json")]
    return [p for p in out if os.path.isfile(p)]


def _rewrite_settings(text):
    """Reapunta cadenas dentro de `hooks` y `statusLine`. Devuelve
    (nuevo_texto|None, changes, unresolved). None si el JSON es ilegible."""
    try:
        data = json.loads(text)
    except Exception:
        return None, [], []
    if not isinstance(data, dict):
        return None, [], []
    changes, unresolved = [], []

    def walk(v):
        if isinstance(v, str):
            nv, ch, un = _rewrite_text(v)
            changes.extend(ch)
            unresolved.extend(un)
            return nv
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    for key in ("hooks", "statusLine"):
        if key in data:
            data[key] = walk(data[key])
    if not changes:
        return text, [], unresolved
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", changes, unresolved


# ── 1. DETECTAR ──────────────────────────────────────────────────────────────
def _item(kind, action, path, detail, dest="", blocked=""):
    return {"kind": kind, "action": action, "path": path, "dest": dest,
            "detail": detail, "blocked": blocked}


def _edit_item(kind, path, new, removed, changes, unresolved, label):
    det = []
    if removed:
        det.append("quita %d línea(s) legada(s)" % len(removed))
    if changes:
        det.append("reapunta %d ruta(s) → Workspace" % len(changes))
    it = _item(kind, "reapuntar", path, "; ".join(det) or label)
    it["new_sha"] = _sha_text(new)
    if unresolved:
        it["action"] = "avisar"
        it["detail"] = ("rutas viejas sin equivalente en Workspace: %s — corre "
                        "`workspace repair` o `python install.py`"
                        % ", ".join(sorted(set(unresolved))))
    return it


def detect():
    """Inventario de artefactos legados. Solo lectura, falla-suave por bloque.
    Devuelve {"workspace": ROOT, "items": [..]} (orden = orden de ejecución)."""
    items, roots = [], set()
    ws_ok = workspace_installed()

    # (a) estado per-máquina viejo → copiar lo que falte a ~/.claude/workspace
    st = legacy_state_dir()
    if os.path.isdir(st):
        for dp, dns, fns in os.walk(st):
            dns[:] = [d for d in dns if not _EPHEMERAL.search(d)]
            for n in fns:
                if _EPHEMERAL.search(n):
                    continue
                src = os.path.join(dp, n)
                dst = os.path.join(_state_dir(), os.path.relpath(src, st))
                if not os.path.exists(dst):
                    items.append(_item("estado", "migrar", src,
                                       "copiar al estado de Workspace (no pisa nada)", dst))

    # (b) manifiesto viejo en cerebros registrados → `.workspace/agent.json`
    for b in _brains():
        leg = os.path.join(b, legacy.BRAIN_SUBDIR, "agent.json")
        can = os.path.join(b, ".workspace", "agent.json")
        if os.path.isfile(leg) and not os.path.isfile(can):
            items.append(_item("definición", "migrar", leg,
                               "migrar la definición del agente (el legado se conserva)", can))

    # (c) agents.local.json con cerebros bajo el estado viejo (~/.claude/<viejo>)
    try:
        import agentsreg
        dead = st + os.sep
        for a in agentsreg.read_local().get("agents", []):
            br = str((a or {}).get("brain", "")) if isinstance(a, dict) else ""
            if br.startswith(dead):
                new = os.path.join(_state_dir(), os.path.relpath(br, st))
                items.append(_item("registro", "reapuntar", agentsreg.local_path(),
                                   "agente '%s': %s" % (a.get("name", "?"), br), new))
    except Exception:
        pass

    # (d) launchers en ~/.local/bin
    bd = _bindir()
    if os.path.isdir(bd):
        for n in sorted(os.listdir(bd)):
            p = os.path.join(bd, n)
            if not os.path.isfile(p) or os.path.islink(p):
                continue
            if n.lower() in LEGACY_LAUNCHERS:
                items.append(_item("launcher", "retirar", p, "comando de la instalación anterior (`%s`)" % n))
                continue
            try:
                if os.path.getsize(p) > 256 * 1024:
                    continue
            except OSError:
                continue
            txt = _read_text(p)
            if not txt:
                continue
            roots |= _referenced_roots(txt)
            new, ch, un = _rewrite_text(txt)
            if ch or un:
                items.append(_edit_item("launcher", p, new, [], ch, un, "launcher"))

    wc = os.path.join(_home(), ".claude", "workspace-cmds.ps1")
    txt = _read_text(wc) if os.path.isfile(wc) else None
    if txt:
        roots |= _referenced_roots(txt)
        new, ch, un = _rewrite_text(txt)
        if ch or un:
            items.append(_edit_item("launcher", wc, new, [], ch, un, "comandos PowerShell"))

    # (e) shells: $PROFILE (PowerShell) y rc POSIX
    for prof in _ps_profiles():
        txt = _read_text(prof)
        if txt is None:
            continue
        roots |= _referenced_roots(txt)
        new, removed = strip_ps_profile(txt)
        new, ch, un = _rewrite_text(new)
        if removed or ch or un:
            it = _edit_item("perfil", prof, new, removed, ch, un, "perfil")
            if not ws_ok and it["action"] == "reapuntar":
                it["action"], it["detail"] = "avisar", (
                    "tiene cableado de la instalación anterior pero Workspace aún no "
                    "está instalado: corre "
                    "`python install.py` y repite (si no, te quedarías sin comando)")
            items.append(it)
    for rc in _RC_FILES:
        p = os.path.join(_home(), rc)
        txt = _read_text(p) if os.path.isfile(p) else None
        if txt is None:
            continue
        roots |= _referenced_roots(txt)
        new, removed = strip_rc(txt)
        new, ch, un = _rewrite_text(new)
        if removed or ch or un:
            it = _edit_item("shell", p, new, removed, ch, un, "rc")
            if not ws_ok and it["action"] == "reapuntar":
                it["action"], it["detail"] = "avisar", (
                    "tiene cableado de la instalación anterior pero Workspace aún no "
                    "está instalado: corre "
                    "`python install.py` y repite")
            items.append(it)

    # (f) hooks / statusLine horneados con la ruta vieja
    for sp in _settings_files():
        txt = _read_text(sp)
        if txt is None:
            continue
        roots |= _referenced_roots(txt)
        new, ch, un = _rewrite_settings(txt)
        if new is None:
            continue
        if ch or un:
            items.append(_edit_item("settings", sp, new, [], ch, un, "settings"))

    # (g) RETIRAR: funciones PowerShell viejas, estado viejo, carpeta(s) del harness viejo
    pc = _ps_cmds_legacy()
    if os.path.isfile(pc):
        items.append(_item("comandos-ps", "retirar", pc, "funciones PowerShell de la instalación anterior"))
    if os.path.isdir(st):
        items.append(_item("estado", "retirar", st, "estado per-máquina de la instalación anterior"))
    env_root = os.environ.get(legacy.ENV_ROOT, "")
    cands = set(roots) | set(_remembered_roots())
    for c in ([env_root] if env_root else []) + [
            os.path.join(_home(), "Desktop", legacy.HARNESS_DIRNAME),
            os.path.join(_home(), legacy.HARNESS_DIRNAME)]:
        cands.add(os.path.abspath(os.path.expanduser(c)))
    seen, harness_roots = set(), []
    for c in sorted(cands):
        if not os.path.isdir(c) or _norm(c) in seen or _norm(c) == _norm(ROOT):
            continue
        seen.add(_norm(c))
        if _looks_like_harness(c):
            harness_roots.append(c)
            items.append(_item("harness", "retirar", c, "carpeta del harness viejo"))
        else:
            items.append(_item("harness", "avisar", c,
                               "existe pero NO parece un harness — no la toco"))

    # (h) env viva: solo aviso (no editamos el entorno persistente del usuario)
    for var in legacy.ENV_VARS:
        if os.environ.get(var):
            how = ("[Environment]::SetEnvironmentVariable('%s',$null,'User')" % var
                   if IS_WIN else "quita `export %s=…` de tu shell" % var)
            items.append(_item("env", "avisar", var, "variable legada definida — " + how))

    _mark_retire_blockers(items)
    return {"workspace": ROOT, "items": items, "roots": harness_roots}


def _mark_retire_blockers(items):
    """Un artefacto solo se retira si nada vivo lo sigue usando y no está protegido."""
    pending_refs = [it for it in items if it["action"] in ("reapuntar", "avisar")
                    and it["kind"] in ("launcher", "perfil", "shell", "settings")]
    pending_state = [it for it in items if it["kind"] in ("estado", "registro")
                     and it["action"] in ("migrar", "reapuntar")]
    for it in items:
        if it["action"] != "retirar":
            continue
        why = _protected(it["path"])
        if not why and it["kind"] == "comandos-ps" and any(
                i["kind"] == "perfil" for i in pending_refs):
            why = "el $PROFILE aún lo carga — corre --apply primero"
        if not why and it["kind"] == "harness" and pending_refs:
            why = ("aún hay launchers/hooks/perfil apuntando a la instalación anterior — "
                   "corre --apply primero")
        if not why and it["kind"] == "estado":
            if pending_state:
                why = "falta copiar su contenido a Workspace — corre --apply primero"
            else:
                diff = _state_differs(it["path"])
                if diff:
                    why = ("tiene archivos distintos a los de ~/.claude/workspace (%s) — "
                           "revísalos a mano" % ", ".join(diff[:3]))
        it["blocked"] = why


def _state_differs(st):
    """[rel] de archivos del estado viejo SIN copia idéntica en el estado nuevo."""
    out = []
    for dp, dns, fns in os.walk(st):
        dns[:] = [d for d in dns if not _EPHEMERAL.search(d)]
        for n in fns:
            if _EPHEMERAL.search(n):
                continue
            src = os.path.join(dp, n)
            rel = os.path.relpath(src, st)
            dst = os.path.join(_state_dir(), rel)
            if rel == REGISTRY_FILE and _registry_covered(src, dst):
                continue
            try:
                if not os.path.isfile(dst) or _sha(dst) != _sha(src):
                    out.append(rel)
            except OSError:
                out.append(rel)
    return out


def _registry_covered(old, new):
    """El registro viejo se trajo FILTRADO (sin agentes internos): está cubierto
    si cada agente del usuario que tenía sigue registrado en el nuevo."""
    o, n = _read_json_file(old), _read_json_file(new)
    if not isinstance(o, dict) or not isinstance(n, dict):
        return False
    have = {str((a or {}).get("name", "")).strip().lower()
            for a in (n.get("agents") or []) if isinstance(a, dict)}
    want = filter_registry(o)[0].get("agents") or []
    return all(str((a or {}).get("name", "")).strip().lower() in have
               for a in want if isinstance(a, dict))


# ── 2. PLAN ─────────────────────────────────────────────────────────────────
_VERB = {"migrar": "MIGRAR", "reapuntar": "REAPUNTAR", "retirar": "RETIRAR", "avisar": "REVISAR"}


def plan_text(det=None):
    det = det or detect()
    items = det["items"]
    L = ["Migración de la instalación anterior → Workspace  (%s)" % det["workspace"]]
    if not items:
        L.append("  ✓ No hay restos de la instalación anterior en esta máquina. Nada que hacer.")
        return "\n".join(L)
    for act in ("migrar", "reapuntar", "retirar", "avisar"):
        sel = [i for i in items if i["action"] == act]
        if not sel:
            continue
        L.append("")
        L.append("  %s (%d)%s" % (_VERB[act], len(sel),
                                  "  ← con --retire, tras copia recuperable" if act == "retirar"
                                  else "  ← con --apply" if act in ("migrar", "reapuntar")
                                  else "  ← manual, no se toca"))
        for i in sel:
            L.append("    · [%s] %s" % (i["kind"], i["path"]))
            if i["dest"]:
                L.append("        → %s" % i["dest"])
            L.append("        %s" % i["detail"])
            if i.get("blocked"):
                L.append("        (bloqueado: %s)" % i["blocked"])
    L.append("")
    L.append("  Cerebros, sesiones, secretos y STATE NO se tocan. Nada se ejecutó (plan).")
    L.append("  Siguiente: %s --apply   ·   luego --retire" % CLI)
    return "\n".join(L)


# ── backup / manifest ────────────────────────────────────────────────────────
class _Backup:
    """Carpeta de respaldo con manifest.json (sha256 por archivo). Se crea SOLO
    si hay algo que respaldar (repetir sin cambios no deja carpetas vacías)."""

    def __init__(self, op):
        self.op = op
        self.dir = ""
        self.entries = []

    def _ensure(self):
        if not self.dir:
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            self.dir = os.path.join(backups_root(), "%s-%s" % (stamp, self.op))
            os.makedirs(os.path.join(self.dir, "files"), exist_ok=True)
        return self.dir

    def _slot(self):
        self._ensure()
        return os.path.join("files", "%04d" % len(self.entries))

    def save_original(self, path):
        """Copia el original de un archivo que se va a MODIFICAR."""
        rel = self._slot()
        shutil.copy2(path, os.path.join(self.dir, rel))
        e = {"op": "modified", "kind": "file", "path": path, "backup": rel,
             "sha256": _sha(path)}
        self.entries.append(e)
        self.write()
        return e

    def created(self, path):
        e = {"op": "created", "kind": "file", "path": path, "after_sha256": _sha(path)}
        self.entries.append(e)
        self.write()
        return e

    def move_in(self, path):
        """RETIRA `path` moviéndolo al respaldo (con hashes verificados)."""
        rel = self._slot()
        dst = os.path.join(self.dir, rel)
        if os.path.isdir(path) and not os.path.islink(path):
            before = _tree_hashes(path)
            shutil.move(path, dst)
            after = _tree_hashes(dst)
            if after != before:
                # copia incompleta: devolver y abortar ESTE artefacto
                if not os.path.exists(path):
                    shutil.move(dst, path)
                raise OSError("verificación de hashes falló al respaldar %s" % path)
            e = {"op": "removed", "kind": "dir", "path": path, "backup": rel,
                 "files": before}
        else:
            sha = _sha(path)
            shutil.move(path, dst)
            if _sha(dst) != sha:
                shutil.move(dst, path)
                raise OSError("verificación de hash falló al respaldar %s" % path)
            e = {"op": "removed", "kind": "file", "path": path, "backup": rel, "sha256": sha}
        self.entries.append(e)
        self.write()
        return e

    def write(self):
        if not self.dir:
            return
        doc = {"version": 1, "op": self.op, "workspace": ROOT,
               "created": datetime.datetime.now().isoformat(timespec="seconds"),
               "entries": self.entries}
        _atomic_write(os.path.join(self.dir, MANIFEST),
                      json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def list_backups():
    r = backups_root()
    try:
        return sorted(os.path.join(r, d) for d in os.listdir(r)
                      if os.path.isfile(os.path.join(r, d, MANIFEST)))
    except OSError:
        return []


# ── 3. MIGRAR ────────────────────────────────────────────────────────────────
def _apply_edit(bk, it):
    path = it["path"]
    txt = _read_text(path)
    if txt is None:
        return "ilegible"
    if it["kind"] == "perfil":
        new, _ = strip_ps_profile(txt)
        new, _, un = _rewrite_text(new)
    elif it["kind"] == "shell":
        new, _ = strip_rc(txt)
        new, _, un = _rewrite_text(new)
    elif it["kind"] == "settings":
        new, _, un = _rewrite_settings(txt)
    else:
        new, _, un = _rewrite_text(txt)
    if new is None or un:
        return "cambió desde el plan (repite --plan)"
    if new == txt:
        return ""
    bk.save_original(path)
    _atomic_write(path, new)
    bk.entries[-1]["after_sha256"] = _sha(path)
    bk.write()
    return ""


def apply(det=None):
    """Aplica migrar+reapuntar. NO retira nada. Devuelve
    {"backup", "done", "skipped", "checks"}."""
    det = det or detect()
    bk = _Backup("apply")
    done, skipped = [], []
    # Mismo guard anti-envenenamiento que install.global_writes_blocked: desde un git
    # WORKTREE secundario, reapuntar hornearía rutas a un árbol temporal.
    wt = os.path.isfile(os.path.join(ROOT, ".git")) \
        and os.environ.get("WORKSPACE_FORCE_LAUNCHERS") != "1"
    for it in det["items"]:
        act = it["action"]
        if wt and act == "reapuntar" and it["kind"] in ("launcher", "perfil", "shell",
                                                         "settings"):
            skipped.append((it, "Workspace corre desde un git worktree: no reapunto a un "
                                "árbol temporal (corre desde el checkout principal)"))
            continue
        if act not in ("migrar", "reapuntar"):
            continue
        try:
            if it["kind"] == "estado":
                if os.path.exists(it["dest"]):
                    continue                                  # idempotente: no pisa
                data = (_read_json_file(it["path"])
                        if os.path.basename(it["path"]) == REGISTRY_FILE
                        and os.path.dirname(it["dest"]) == _state_dir() else None)
                if isinstance(data, dict):
                    # el registro se trae SIN los agentes internos (no copia ciega)
                    _atomic_write(it["dest"], json.dumps(filter_registry(data)[0],
                                                         indent=2, ensure_ascii=False) + "\n")
                else:
                    _atomic_copy(it["path"], it["dest"])
                bk.created(it["dest"])
            elif it["kind"] == "definición":
                import agentsreg
                brain = os.path.dirname(os.path.dirname(it["path"]))
                ok, msg = agentsreg.migrate_legacy(brain)
                if not ok:
                    if msg:
                        skipped.append((it, msg))
                    continue
                bk.created(it["dest"])
            elif it["kind"] == "registro":
                import agentsreg
                if not os.path.isdir(it["dest"]):
                    skipped.append((it, "destino aún no existe: %s" % it["dest"]))
                    continue
                path = agentsreg.local_path()
                bk.save_original(path)
                data = agentsreg.read_local()
                st = legacy_state_dir() + os.sep
                for a in data.get("agents", []):
                    if isinstance(a, dict) and str(a.get("brain", "")).startswith(st):
                        a["brain"] = os.path.join(_state_dir(),
                                                  os.path.relpath(a["brain"], st[:-1]))
                if not agentsreg._write_local(data):
                    skipped.append((it, "no pude escribir agents.local.json"))
                    continue
                bk.entries[-1]["after_sha256"] = _sha(path)
                bk.write()
            else:
                why = _apply_edit(bk, it)
                if why:
                    skipped.append((it, why))
                    continue
            done.append(it)
        except Exception as e:                                # falla-suave por ítem
            skipped.append((it, "%s: %s" % (type(e).__name__, e)))
    if done:
        _remember(bk, det.get("roots", []))
    return {"backup": bk.dir, "done": done, "skipped": skipped, "checks": validate()}


def _remember(bk, roots):
    """Anota (con respaldo) las raíces del harness viejo para que --retire las
    encuentre aunque ya nada las referencie. Idempotente."""
    known = _remembered_roots()
    new = sorted(set(known) | set(roots))
    if new == sorted(known):
        return
    path = memory_path()
    existed = os.path.isfile(path)
    if existed:
        bk.save_original(path)
    _atomic_write(path, json.dumps({"version": 1, "legacy_roots": new},
                                   indent=2, ensure_ascii=False) + "\n")
    if existed:
        bk.entries[-1]["after_sha256"] = _sha(path)
        bk.write()
    else:
        bk.created(path)


def validate():
    """Checks ESTÁTICOS post-migración: launch y memoria verificables sin lanzar
    nada. [{ok, label, detail}]."""
    out = []

    def chk(ok, label, detail=""):
        out.append({"ok": bool(ok), "label": label, "detail": detail})

    chk(_looks_like_harness(ROOT), "Workspace lanzable", ROOT)
    try:
        import agentsreg
        for a in agentsreg.agents():
            chk(os.path.isdir(a["brain"]), "agente '%s' → cerebro existe (memoria)"
                % a["name"], a["brain"])
    except Exception:
        pass
    for b in _brains():
        if os.path.isfile(os.path.join(b, legacy.BRAIN_SUBDIR, "agent.json")):
            can = os.path.join(b, ".workspace", "agent.json")
            try:
                with open(can, encoding="utf-8") as fh:
                    d = json.load(fh)
                good = isinstance(d, dict) and bool(str(d.get("name", "")).strip())
            except Exception:
                good = False
            chk(good, "definición migrada válida", can)
    for sp in _settings_files():
        txt = _read_text(sp) or ""
        _new, ch, un = _rewrite_settings(txt)
        chk(not ch and not un, "hooks/statusLine sin rutas de la instalación anterior", sp)
        try:
            data = json.loads(txt)
        except Exception:
            continue
        missing = [p for p in _py_paths([data.get("hooks"), data.get("statusLine")])
                   if not os.path.exists(p)]
        chk(not missing, "hooks apuntan a rutas existentes",
            sp + (" · faltan: " + ", ".join(missing[:3]) if missing else ""))
    bd = _bindir()
    if os.path.isdir(bd):
        for n in sorted(os.listdir(bd)):
            p = os.path.join(bd, n)
            if n.lower() in LEGACY_LAUNCHERS or not os.path.isfile(p):
                continue
            txt = _read_text(p) if os.path.getsize(p) < 256 * 1024 else None
            if not txt:
                continue
            _n, ch, un = _rewrite_text(txt)
            if ch or un:
                chk(False, "launcher aún apunta a la instalación anterior", p)
    return out


def _strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _strings(x)


def _py_paths(value):
    """Rutas absolutas a .py mencionadas en las cadenas de `value`."""
    out = []
    for text in _strings(value):
        for m in _TOKEN.finditer(text):
            tok = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            if tok.endswith(".py") and os.path.isabs(os.path.expanduser(tok)):
                out.append(os.path.expanduser(tok))
    return out


# ── 4. RETIRAR ───────────────────────────────────────────────────────────────
def retire_paths(paths, op="retire"):
    """Retira `paths` (lista explícita) con copia recuperable previa. Cada ruta
    pasa por `_protected()`; las protegidas se SALTAN. Devuelve
    (backup_dir, retiradas, [(ruta, razón)])."""
    bk = _Backup(op)
    done, skipped = [], []
    for p in paths:
        if not os.path.lexists(p):
            continue
        why = _protected(p)
        if why:
            skipped.append((p, why))
            continue
        try:
            bk.move_in(p)
            done.append(p)
        except Exception as e:
            skipped.append((p, "%s: %s" % (type(e).__name__, e)))
    return bk.dir, done, skipped


def retire(det=None):
    det = det or detect()
    targets = [i["path"] for i in det["items"]
               if i["action"] == "retirar" and not i.get("blocked")]
    blocked = [(i["path"], i["blocked"]) for i in det["items"]
               if i["action"] == "retirar" and i.get("blocked")]
    bdir, done, skipped = retire_paths(targets)
    return {"backup": bdir, "done": done, "skipped": blocked + skipped}


# ── 5. ROLLBACK ──────────────────────────────────────────────────────────────
def rollback(backup_dir):
    """Restaura desde un respaldo. Idempotente; nunca pisa algo que el usuario
    cambió después (lo reporta). Devuelve {"restored", "skipped"}."""
    mp = os.path.join(backup_dir, MANIFEST)
    with open(mp, encoding="utf-8") as fh:
        doc = json.load(fh)
    restored, skipped = [], []
    for e in reversed(doc.get("entries", [])):
        path, op = e["path"], e["op"]
        src = os.path.join(backup_dir, e.get("backup", "")) if e.get("backup") else ""
        try:
            if op == "created":
                if not os.path.exists(path):
                    continue
                if _sha(path) != e.get("after_sha256"):
                    skipped.append((path, "cambió después de migrar — no lo borro"))
                    continue
                os.remove(path)
                restored.append(path)
            elif op == "modified":
                if os.path.isfile(path) and _sha(path) == e["sha256"]:
                    continue                                  # ya restaurado
                if os.path.isfile(path) and e.get("after_sha256") \
                        and _sha(path) != e["after_sha256"]:
                    skipped.append((path, "cambió después de migrar — no lo piso"))
                    continue
                if _sha(src) != e["sha256"]:
                    skipped.append((path, "respaldo corrupto (hash)"))
                    continue
                _atomic_copy(src, path)
                restored.append(path)
            elif op == "removed":
                if os.path.lexists(path):
                    continue                                  # ya está (idempotente)
                if e["kind"] == "dir":
                    if _tree_hashes(src) != e.get("files", {}):
                        skipped.append((path, "respaldo corrupto (hashes)"))
                        continue
                    shutil.copytree(src, path, symlinks=True)
                else:
                    if _sha(src) != e["sha256"]:
                        skipped.append((path, "respaldo corrupto (hash)"))
                        continue
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    shutil.copy2(src, path)
                restored.append(path)
        except Exception as ex:
            skipped.append((path, "%s: %s" % (type(ex).__name__, ex)))
    return {"restored": restored, "skipped": skipped}


# ── sugerencia para el doctor (solo lectura) ─────────────────────────────────
def summary():
    """(pendientes:int, texto) para el doctor. Falla-suave → (0, '')."""
    try:
        items = detect()["items"]
    except Exception:
        return 0, ""
    if not items:
        return 0, ""
    counts = {}
    for i in items:
        counts[i["action"]] = counts.get(i["action"], 0) + 1
    return len(items), " · ".join("%s %d" % (k, v) for k, v in sorted(counts.items()))


# ── CLI ──────────────────────────────────────────────────────────────────────
def _confirm(prompt):
    try:
        if not sys.stdin.isatty():
            return False
        return input(prompt).strip().lower() in ("retirar", "si", "sí", "yes")
    except Exception:
        return False


def _print_result(res, verb):
    for it in res.get("done", []):
        path = it["path"] if isinstance(it, dict) else it
        print("  ✓ %s: %s" % (verb, path))
    for it, why in res.get("skipped", []):
        path = it["path"] if isinstance(it, dict) else it
        print("  · omitido: %s — %s" % (path, why))
    if res.get("backup"):
        print("  respaldo recuperable: %s" % res["backup"])
        print("  (deshacer: %s --rollback \"%s\")" % (CLI, res["backup"]))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    if "-h" in argv or "--help" in argv:
        print("uso: " + CLI + " [--plan|--apply|--retire|--rollback <respaldo>]"
              " [--yes] [--json]\n  --plan (default) solo muestra; --apply migra/reapunta;"
              "\n  --retire quita artefactos viejos con respaldo; --rollback restaura;"
              "\n  --backups lista respaldos.")
        return 0
    if "--backups" in argv:
        for b in list_backups():
            print(b)
        return 0
    if "--rollback" in argv:
        i = argv.index("--rollback")
        target = argv[i + 1] if i + 1 < len(argv) else ""
        if not target or not os.path.isfile(os.path.join(target, MANIFEST)):
            print("migrar-legado: indica un respaldo válido (--backups los lista).")
            return 2
        res = rollback(target)
        if as_json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            for p in res["restored"]:
                print("  ✓ restaurado: %s" % p)
            for p, why in res["skipped"]:
                print("  · omitido: %s — %s" % (p, why))
            if not res["restored"] and not res["skipped"]:
                print("  Nada que restaurar (ya estaba restaurado).")
        return 0 if not res["skipped"] else 1
    det = detect()
    if "--apply" in argv:
        res = apply(det)
        if as_json:
            print(json.dumps({"backup": res["backup"],
                              "done": [i["path"] for i in res["done"]],
                              "skipped": [(i["path"], w) for i, w in res["skipped"]],
                              "checks": res["checks"]}, ensure_ascii=False, indent=2))
        else:
            if not res["done"] and not res["skipped"]:
                print("  Nada que migrar (ya está migrado).")
            _print_result(res, "migrado")
            for c in res["checks"]:
                print("  %s %s  %s" % ("✓" if c["ok"] else "✗", c["label"], c["detail"]))
        return 0 if all(c["ok"] for c in res["checks"]) and not res["skipped"] else 1
    if "--retire" in argv:
        if "--yes" not in argv:
            print(plan_text(det))
            if not _confirm("\n  Escribe 'retirar' para retirar SOLO lo listado en RETIRAR: "):
                print("  No retiré nada (sin confirmación; usa --yes en no-interactivo).")
                return 1
        res = retire(det)
        if as_json:
            print(json.dumps({"backup": res["backup"], "done": res["done"],
                              "skipped": res["skipped"]}, ensure_ascii=False, indent=2))
        else:
            if not res["done"] and not res["skipped"]:
                print("  Nada que retirar.")
            _print_result(res, "retirado")
        return 0
    if as_json:
        print(json.dumps(det, ensure_ascii=False, indent=2))
    else:
        print(plan_text(det))
    return 0


if __name__ == "__main__":
    sys.exit(main())
