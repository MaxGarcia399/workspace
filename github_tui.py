#!/usr/bin/env python3
"""WORKSPACE · github_tui — pantalla GITHUB del menú: tus repos, local + nube.

Expansión de la sección «Ramas» (pedido del socio 2026-10-04): el mapa local
de ramas/worktrees (git_tui) se conserva INTACTO — tecla m lo abre tal cual —
y encima vive la capa GitHub: repos conectados, PRs con el estado de sus
checks, issues, ramas remotas, commits recientes, releases y corridas de
Actions. Todo vía el CLI oficial `gh` (shell-out, cero deps): `gh` ES el
manejo seguro de credenciales (keyring del sistema) — aquí jamás se leen,
piden ni guardan tokens.

Principios no negociables:
  · SEGURIDAD — gated por sesión: si `gh auth status` no reporta sesión, la
    capa GitHub queda APAGADA (la pantalla dice claro «gh auth login») y NO
    se toca la red jamás. Lo local sigue completo.
  · CERO red en el redraw (lección del lag del mapa): la nube se consulta
    SOLO con f, en segundo plano (la UI no se congela), y queda cacheada en
    disco con su hora — al volver a entrar ves el último snapshot con su
    «hace Xm», nunca un spinner eterno.
  · Multi-repo per-máquina: la lista vive en
    ~/.claude/workspace/github-repos.json (a conecta — abre un SELECTOR de
    repos git locales detectados en el disco, con su owner/nombre resuelto
    del origin, para elegir con flechas/click; teclear owner/nombre o URL
    sigue disponible · x desconecta — solo editan esa lista; nada se clona,
    nada se borra del disco ni de GitHub). El escaneo de repos locales es
    SOLO lectura de disco (.git/config a mano): cero subprocess, cero red.
  · Ramas sin fricción: las ramas LOCALES de cada copia se leen de archivos
    (.git/HEAD, refs/heads, packed-refs — cero subprocess) y se ven al
    instante, sin consultar la nube; Enter o c cambia la copia a la rama
    elegida con las guardas de siempre (árbol limpio, jamás --force).
  · Acciones seguras: abrir en el navegador (Enter/o — solo URLs de
    github.com), consultar (f), y cambiar la copia local a una rama (c, con
    árbol limpio). Lo destructivo (merge, close, delete, force) queda FUERA
    de esta pantalla a propósito; el panel operativo (git_panel, dentro del
    mapa local) cubre el flujo de PR/release con confirmación por plan.

Mismo esqueleto que git_tui/tono_tui (wordmark del hub, paleta del TEMA,
dos cajas full_box), teclas + click (mouse SGR, fail-soft), altura estable.
Falla-suave en todo; sin tty cae a un listado de texto. Cero dependencias
(stdlib, Python 3.9+). Mac y Windows.
"""
import json
import os
import re
import shutil
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import hublayout as HL                                          # noqa: E402
import git_ops as O                                             # noqa: E402
import git_tui as GT                                            # noqa: E402

# owner/nombre estricto (también es la anti-inyección: jamás llega un flag
# ni un `;` a la línea de gh) · URL https/ssh de github.com
_SLUG_RE = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+$")
_URL_RE = re.compile(r"^(?:git@github\.com:|https://github\.com/|"
                     r"ssh://git@github\.com/)([\w.-]+/[\w.-]+?)(?:\.git)?/?$")
# tope de filas por sección del detalle (la ventana hace el resto)
_CAPS = {"lbranch": 8, "prs": 6, "issues": 6, "branches": 8, "commits": 5,
         "releases": 3, "runs": 5}
_FAIL = ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED",
         "STARTUP_FAILURE")


# ── persistencia per-máquina (lista de repos + cache de consultas) ─────────
def _wsdir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def _cfg_path():
    return os.path.join(_wsdir(), "github-repos.json")


def _cache_path():
    return os.path.join(_wsdir(), "github-cache.json")


def _load(path, fallback):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, type(fallback)) else fallback
    except Exception:
        return fallback


def _save(path, data):
    """Escritura atómica, falla-suave (False si no se pudo)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.tmp%d" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _cfg_repos():
    """Los repos conectados del archivo de config. Acepta el formato v1
    ({version, repos:[{repo, local}]}) y una lista simple de slugs."""
    try:
        with open(_cfg_path(), encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        d = {}
    rows = d.get("repos", []) if isinstance(d, dict) else d
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, str):
            r = {"repo": r}
        if isinstance(r, dict) and _SLUG_RE.match(str(r.get("repo", ""))):
            out.append({"repo": r["repo"], "local": str(r.get("local") or "")})
    return out


def _cfg_write(rows):
    return _save(_cfg_path(), {"version": 1, "repos": rows})


def parse_target(text):
    """`owner/nombre`, URL de github.com o carpeta local → (slug, local, err).
    La carpeta local se resuelve a su origin (y se recuerda como copia)."""
    t = (text or "").strip().strip('"').strip("'")
    if not t:
        return "", "", "cancelado — sin repo no hay conexión"
    p = os.path.expanduser(t)
    if os.path.isdir(p):
        local = O.top(p)
        if not local:
            return "", "", "esa carpeta no es un repositorio git"
        slug = O.github_repo(local)
        if not slug:
            return "", "", ("ese repo no tiene origin de github.com — "
                            "conéctalo con owner/nombre")
        return slug, local, ""
    m = _URL_RE.match(t)
    if m:
        return m.group(1), "", ""
    if _SLUG_RE.match(t):
        return t, "", ""
    return "", "", ("no entendí el repo: usa owner/nombre, una URL de "
                    "github.com o una carpeta local clonada")


def connect(text):
    """Agrega un repo a la lista per-máquina. (slug, mensaje)."""
    slug, local, err = parse_target(text)
    if err:
        return "", err
    rows = _cfg_repos()
    for r in rows:
        if r["repo"].lower() == slug.lower():
            if local and not r.get("local"):
                r["local"] = local
                _cfg_write(rows)
                return slug, ("%s ya estaba conectado — registré su copia "
                              "local ✓" % slug)
            return slug, "%s ya está conectado" % slug
    rows.append({"repo": slug, "local": local})
    if not _cfg_write(rows):
        return "", "no pude escribir github-repos.json — nada cambió"
    return slug, "%s conectado ✓ — f consulta su estado" % slug


def disconnect(slug):
    """Quita un repo de la lista. SOLO la lista: nada se borra del disco
    ni de GitHub (por eso no es una acción destructiva)."""
    rows = [r for r in _cfg_repos() if r["repo"].lower() != slug.lower()]
    if not _cfg_write(rows):
        return "no pude escribir github-repos.json — nada cambió"
    return "%s desconectado ✓ — solo salió de tu lista; nada se borró" % slug


# ── descubrir repos git locales (SOLO disco: cero subprocess, cero red) ────
# lugares comunes donde vive el código; (raíz, profundidad máxima)
_SCAN_ROOTS = (("~/Desktop", 2), ("~/Documents", 2), ("~/Projects", 2),
               ("~/projects", 2), ("~/code", 2), ("~/dev", 2), ("~/src", 2),
               ("~/repos", 2), ("~/work", 2), ("~", 1))
_SCAN_SKIP = {"node_modules", "venv", ".venv", "__pycache__", "Library",
              "Applications", "Pictures", "Music", "Movies", "Downloads",
              "vendor", "dist", "build", "target"}


def _git_dir(path):
    """El gitdir real de `path` ('' si no es repo): dir .git o archivo
    `gitdir:` (worktrees/submódulos). Solo lectura de disco."""
    g = os.path.join(path, ".git")
    try:
        if os.path.isdir(g):
            return g
        if os.path.isfile(g):
            with open(g, encoding="utf-8", errors="replace") as fh:
                first = fh.readline().strip()
            if first.startswith("gitdir:"):
                p = first[7:].strip()
                if not os.path.isabs(p):
                    p = os.path.normpath(os.path.join(path, p))
                return p if os.path.isdir(p) else ""
    except Exception:
        pass
    return ""


def _git_common(gitdir):
    """El dir común del repo (donde viven refs/config) — en worktrees el
    gitdir apunta a commondir. Falla-suave: devuelve el propio gitdir."""
    try:
        cd = os.path.join(gitdir, "commondir")
        if os.path.isfile(cd):
            with open(cd, encoding="utf-8", errors="replace") as fh:
                b = fh.read().strip()
            if not os.path.isabs(b):
                b = os.path.normpath(os.path.join(gitdir, b))
            if os.path.isdir(b):
                return b
    except Exception:
        pass
    return gitdir


def _origin_slug(gitdir):
    """owner/nombre del origin leyendo .git/config A MANO (cero subprocess).
    '' si no hay origin o no es de github.com."""
    for cfg in (os.path.join(gitdir, "config"),
                os.path.join(_git_common(gitdir), "config")):
        try:
            with open(cfg, encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        except Exception:
            continue
        m = re.search(r'\[remote\s+"origin"\][^\[]*?url\s*=\s*(\S+)', txt)
        if m:
            mm = _URL_RE.match(m.group(1))
            return mm.group(1) if mm else ""
    return ""


def scan_local_repos(max_dirs=4000, budget=2.5):
    """Repos git en los lugares comunes del disco, con su owner/nombre
    resuelto del origin. BFS acotado (dirs + segundos) y SOLO lectura de
    archivos — jamás subprocess ni red. Orden: con github primero, a-z."""
    t0 = time.time()
    vistos, repos, cola = set(), [], []
    for raiz, hondo in _SCAN_ROOTS:
        p = os.path.realpath(os.path.expanduser(raiz))
        if os.path.isdir(p):
            cola.append((p, 0, hondo))
    visitados = 0
    while cola:
        path, depth, hondo = cola.pop(0)
        if visitados >= max_dirs or time.time() - t0 > budget:
            break
        rp = os.path.realpath(path)
        if rp in vistos:
            continue
        vistos.add(rp)
        visitados += 1
        gd = _git_dir(path)
        if gd:                                   # repo: no bajar adentro
            repos.append({"path": path, "slug": _origin_slug(gd),
                          "name": os.path.basename(path.rstrip("/\\"))})
            continue
        if depth >= hondo:
            continue
        try:
            with os.scandir(path) as it:
                for e in it:
                    try:
                        if (e.is_dir(follow_symlinks=False)
                                and not e.name.startswith(".")
                                and e.name not in _SCAN_SKIP):
                            cola.append((e.path, depth + 1, hondo))
                    except OSError:
                        continue
        except OSError:
            continue
    repos.sort(key=lambda r: (not r["slug"], r["name"].lower(), r["path"]))
    return repos


class _Scan(threading.Thread):
    """El escaneo de disco en 2º plano; la UI solo lee .done (como _Fetch)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.done, self.repos = False, []

    def run(self):
        try:
            self.repos = scan_local_repos()
        except Exception:                        # jamás tumbar la pantalla
            self.repos = []
        self.done = True


def local_branches(path):
    """(rama_actual, [ramas]) de una copia local — SOLO lectura de archivos
    (.git/HEAD, refs/heads/, packed-refs): cero subprocess, cero red. La
    rama actual va primero. Falla-suave: ('', [])."""
    gd = _git_dir(path) if path else ""
    if not gd:
        return "", []
    cur = ""
    try:
        with open(os.path.join(gd, "HEAD"), encoding="utf-8",
                  errors="replace") as fh:
            head = fh.read().strip()
        if head.startswith("ref: refs/heads/"):
            cur = head[len("ref: refs/heads/"):]
    except Exception:
        pass
    base = _git_common(gd)
    nombres = set()
    heads = os.path.join(base, "refs", "heads")
    try:
        for dirpath, _dirs, files in os.walk(heads):
            for f in files:
                rel = os.path.relpath(os.path.join(dirpath, f), heads)
                nombres.add(rel.replace(os.sep, "/"))
    except Exception:
        pass
    try:
        with open(os.path.join(base, "packed-refs"), encoding="utf-8",
                  errors="replace") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln.startswith("#") or ln.startswith("^"):
                    continue
                partes = ln.split(" ", 1)
                if len(partes) == 2 and partes[1].startswith("refs/heads/"):
                    nombres.add(partes[1][len("refs/heads/"):])
    except Exception:
        pass
    ramas = sorted(nombres)
    if cur in ramas:
        ramas.remove(cur)
        ramas.insert(0, cur)
    return cur, ramas


# ── la puerta de seguridad: sesión gh ───────────────────────────────────────
def auth_check():
    """¿Hay sesión de GitHub? {ok, account, msg}. Corre UNA vez al entrar y
    con r — jamás en el redraw. Es la ÚNICA llave de toda la capa nube: sin
    ok=True no se lanza ninguna consulta de red."""
    if not shutil.which("gh"):
        return {"ok": False, "account": "",
                "msg": ("GitHub CLI (gh) no está instalado — la nube queda "
                        "apagada; lo local sigue completo")}
    rc, out, err = O.run(["gh", "auth", "status", "--hostname", "github.com"],
                         os.path.expanduser("~"), timeout=12)
    if rc != 0:
        return {"ok": False, "account": "",
                "msg": ("sin sesión de GitHub — conéctate: gh auth login "
                        "(r re-verifica al volver)")}
    cur = acct = ""
    for ln in ((out or "") + "\n" + (err or "")).splitlines():
        m = re.search(r"account (\S+)", ln)
        if m:
            cur = m.group(1)
            acct = acct or cur                   # fallback: la primera cuenta
        if "Active account: true" in ln and cur:
            acct = cur                           # la ACTIVA manda
            break
    return {"ok": True, "account": acct, "msg": ""}


# ── repos visibles: el harness primero, luego los conectados ───────────────
def repos_list():
    repo = GT._repo()
    slug = O.github_repo(repo)
    top = os.path.realpath(repo)
    rows = [{"slug": slug, "local": repo, "harness": True,
             "name": os.path.basename(top.rstrip("/\\"))}]
    for r in _cfg_repos():
        if slug and r["repo"].lower() == slug.lower():
            continue                             # el harness ya está listado
        rows.append({"slug": r["repo"], "local": r.get("local", ""),
                     "harness": False, "name": r["repo"].split("/")[-1]})
    _attach_branches(rows)
    return rows


def _attach_branches(rows):
    """Anota en cada fila con copia local sus ramas (lcur/lbranches) —
    lectura de archivos, cero subprocess; así el detalle las muestra al
    instante sin tocar la red."""
    for row in rows:
        loc = row.get("local") or ""
        if loc and os.path.isdir(loc):
            row["lcur"], row["lbranches"] = local_branches(loc)
    return rows


def _sel_repo(S):
    reps = S["repos"]
    if not reps:
        return None
    S["si"] = min(S["si"], len(reps) - 1)
    return reps[S["si"]]


# ── consulta a GitHub (solo tras auth_check, solo con f, en 2º plano) ──────
def _gh_json(args, timeout=25):
    """(datos, error). Una llamada a gh que devuelve JSON; falla-suave."""
    rc, out, err = O.run(["gh"] + list(args), os.path.expanduser("~"),
                         timeout=timeout)
    if rc != 0:
        msg = (err or out or "consulta fallida").strip()
        return None, O.clean_text(msg.splitlines()[0][:120] if msg else
                                  "consulta fallida")
    try:
        return json.loads(out), ""
    except ValueError:
        return None, "respuesta no válida"


def _checks(p):
    """Estado agregado de los checks de un PR: '' (sin checks) · ok · fail ·
    pend — del statusCheckRollup que ya trae `gh pr list`."""
    roll = p.get("statusCheckRollup") or []
    states = [str(c.get("conclusion") or c.get("state") or "").upper()
              for c in roll if isinstance(c, dict)]
    if not states:
        return ""
    if any(s in _FAIL for s in states):
        return "fail"
    if all(s in ("SUCCESS", "NEUTRAL", "SKIPPED") for s in states):
        return "ok"
    return "pend"


def fetch(slug):
    """TODO el estado nube de un repo en una pasada (consultas en paralelo,
    1 hilo por consulta — total ≈ la más lenta). SOLO se llama tras pasar
    auth_check(); jamás desde el redraw. Errores por clave, nunca truena."""
    data = {"stamped": time.time(), "errors": []}
    jobs = {
        "view": ["repo", "view", slug, "--json",
                 "name,description,isPrivate,defaultBranchRef,url"],
        "prs": ["pr", "list", "--repo", slug, "--state", "open",
                "--limit", "15", "--json",
                "number,title,headRefName,baseRefName,isDraft,url,"
                "statusCheckRollup"],
        "issues": ["issue", "list", "--repo", slug, "--state", "open",
                   "--limit", "15", "--json", "number,title,url,updatedAt"],
        "branches": ["api", "repos/%s/branches?per_page=40" % slug],
        "commits": ["api", "repos/%s/commits?per_page=8" % slug],
        "releases": ["release", "list", "--repo", slug, "--limit", "6",
                     "--json", "tagName,name,isDraft,publishedAt"],
        "runs": ["run", "list", "--repo", slug, "--limit", "10", "--json",
                 "displayTitle,headBranch,status,conclusion,url,createdAt"],
    }
    res = {}

    def work(key, args):
        res[key] = _gh_json(args)

    hilos = [threading.Thread(target=work, args=kv, daemon=True)
             for kv in jobs.items()]
    for t in hilos:
        t.start()
    for t in hilos:
        t.join(35)
    for key in jobs:
        val, err = res.get(key) or (None, "sin respuesta")
        if err or val is None:
            data[key] = {} if key == "view" else []
            data["errors"].append("%s: %s" % (key, err or "sin respuesta"))
        else:
            data[key] = val
    # adelgazar lo crudo de la API a lo que la pantalla usa
    data["branches"] = [{"name": str(b.get("name", "")),
                         "protected": bool(b.get("protected"))}
                        for b in (data.get("branches") or [])
                        if isinstance(b, dict) and b.get("name")]
    slim = []
    for c in (data.get("commits") or []):
        if not isinstance(c, dict):
            continue
        cc = c.get("commit") or {}
        slim.append({"sha": str(c.get("sha") or "")[:40],
                     "short": str(c.get("sha") or "")[:7],
                     "msg": O.clean_text(str(cc.get("message") or "")
                                         .splitlines()[0][:120]
                                         if cc.get("message") else ""),
                     "date": str((cc.get("author") or {}).get("date")
                                 or "")[:19]})
    data["commits"] = slim
    for p in (data.get("prs") or []):
        if isinstance(p, dict):
            p["checks"] = _checks(p)
            p.pop("statusCheckRollup", None)
    if not isinstance(data.get("view"), dict):
        data["view"] = {}
    return data


class _Fetch(threading.Thread):
    """Una consulta de repo corriendo en 2º plano; la UI solo lee .done."""

    def __init__(self, slug):
        super().__init__(daemon=True)
        self.slug, self.done, self.data = slug, False, None

    def run(self):
        try:
            self.data = fetch(self.slug)
        except Exception as e:                   # jamás tumbar la pantalla
            self.data = {"stamped": time.time(),
                         "errors": ["consulta: " + O.clean_text(str(e))]}
        self.done = True


class _Cmd(threading.Thread):
    """Secuencia corta de git LOCAL en 2º plano (fetch/switch) con mensaje
    honesto al terminar. Nada de red de GitHub aquí: origin ya configurado."""

    def __init__(self, steps, okmsg):
        super().__init__(daemon=True)
        self.steps, self.okmsg = steps, okmsg
        self.done, self.msg = False, ""

    def run(self):
        for argv, cwd in self.steps:
            rc, out, err = O.run(argv, cwd, timeout=120)
            if rc != 0:
                detalle = (err or out or "").strip()
                self.msg = "falló `%s`: %s" % (
                    " ".join(argv[:3]),
                    detalle.splitlines()[0][:80] if detalle else "?")
                self.done = True
                return
        self.msg = self.okmsg
        self.done = True


# ── acciones ────────────────────────────────────────────────────────────────
def _abrir(url):
    """Abre una URL en el navegador — SOLO github.com (nada de URLs de datos
    remotos sin revisar). Falla-suave."""
    if not str(url).startswith("https://github.com/"):
        return "solo abro URLs de github.com — esta no lo es"
    try:
        webbrowser.open(url)
        return "abierto en el navegador ✓ — %s" % url
    except Exception as e:
        return "no pude abrir el navegador: %s" % e


def _item_url(slug, kind, obj):
    base = "https://github.com/" + slug
    if kind in ("pr", "issue", "run"):
        u = str(obj.get("url") or "")
        return u if u.startswith("https://github.com/") else base
    if kind == "branch":
        return base + "/tree/" + str(obj.get("name", ""))
    if kind == "commit":
        return base + "/commit/" + str(obj.get("sha") or obj.get("short", ""))
    if kind == "release":
        return base + "/releases/tag/" + str(obj.get("tagName", ""))
    return base


def _checkout(S, r, branch, remote=True):
    """Cambia la COPIA LOCAL del repo a `branch` — mismas guardas que el
    mapa: árbol limpio o no se toca; jamás --force. Corre en 2º plano.
    `remote=False` = rama que ya existe local: switch directo, sin fetch."""
    local = r.get("local")
    if not branch:
        return "esa fila no es una rama"
    if not local or not os.path.isdir(local):
        return ("sin copia local — Enter la abre en el navegador; clónala "
                "para poder cambiarte de rama")
    if S.get("job"):
        return "hay un cambio de rama en curso — espera a que termine"
    rc, out, _ = O.run(["git", "status", "--porcelain"], local, timeout=15)
    if rc != 0:
        return "no pude confirmar si el árbol local está limpio — no lo toco"
    n = len([l for l in out.splitlines() if l.strip()])
    if n:
        return ("la copia local tiene %d cambio%s sin commitear — commit o "
                "stash antes de cambiar de rama" % (n, "" if n == 1 else "s"))
    if O.value(local, "branch", "--show-current") == branch:
        return "la copia local ya está en %s" % branch
    pasos = ([(["git", "fetch", "origin", branch], local)] if remote else [])
    pasos.append((["git", "switch", branch], local))
    S["job"] = _Cmd(pasos, "la copia local ahora está en %s ✓" % branch)
    S["job"].start()
    return ("cambiando a %s… (%s en segundo plano)"
            % (branch, "fetch + switch" if remote else "switch"))


# ── estado de la pantalla ───────────────────────────────────────────────────
def _state():
    return {"auth": auth_check(), "repos": repos_list(),
            "cloud": _load(_cache_path(), {}), "si": 0, "ci": 0,
            "focus": "repos", "modo": "nav", "buf": "", "pend": None,
            "msg": "", "fetching": {}, "job": None, "hits": [],
            "found": None, "scan": None, "ai": 0}


def _poll(S):
    """Recoge consultas/jobs terminados. True si algo cambió (redraw)."""
    moved = False
    for slug, th in list(S["fetching"].items()):
        if th.done:
            del S["fetching"][slug]
            if th.data is not None:
                S["cloud"][slug] = th.data
                cache = _load(_cache_path(), {})
                cache[slug] = th.data
                _save(_cache_path(), cache)
                n = len(th.data.get("errors") or [])
                S["msg"] = ("%s consultado ✓" % slug if not n else
                            "%s consultado — %d consulta%s fallida%s (ver "
                            "detalle)" % (slug, n, "" if n == 1 else "s",
                                          "" if n == 1 else "s"))
            moved = True
    if S.get("job") and S["job"].done:
        S["msg"] = S["job"].msg
        S["job"] = None
        _attach_branches(S["repos"])             # la rama actual pudo cambiar
        moved = True
    sc = S.get("scan")
    if sc is not None and sc.done:               # escaneo de disco listo
        S["found"] = sc.repos
        S["scan"] = None
        if S["modo"] == "add":
            S["ai"] = min(S.get("ai", 0), len(_add_opts(S)))
        moved = True
    return moved


def _det_items(S):
    """Las filas SELECCIONABLES del detalle (cache + ramas locales ya
    leídas: cero subprocess). Las ramas de la copia local van PRIMERO —
    se ven y se eligen sin consultar la nube."""
    r = _sel_repo(S)
    if not r:
        return []
    its = []
    for b in (r.get("lbranches") or [])[:_CAPS["lbranch"]]:
        its.append(("lbranch", {"name": b,
                                "current": b == r.get("lcur")}))
    if not r["slug"]:
        return its
    d = S["cloud"].get(r["slug"]) or {}
    for p in (d.get("prs") or [])[:_CAPS["prs"]]:
        its.append(("pr", p))
    for i in (d.get("issues") or [])[:_CAPS["issues"]]:
        its.append(("issue", i))
    for b in (d.get("branches") or [])[:_CAPS["branches"]]:
        its.append(("branch", b))
    for c in (d.get("commits") or [])[:_CAPS["commits"]]:
        its.append(("commit", c))
    for rel in (d.get("releases") or [])[:_CAPS["releases"]]:
        its.append(("release", rel))
    for rn in (d.get("runs") or [])[:_CAPS["runs"]]:
        its.append(("run", rn))
    return its


# ── tiempo relativo ─────────────────────────────────────────────────────────
def _ago(ts):
    try:
        s = max(0, time.time() - float(ts))
    except Exception:
        return ""
    if s < 90:
        return "hace %ds" % int(s)
    if s < 90 * 60:
        return "hace %dm" % int(s // 60)
    if s < 36 * 3600:
        return "hace %dh" % int(s // 3600)
    return "hace %dd" % int(s // 86400)


def _iso_ago(iso):
    try:
        import calendar
        t = calendar.timegm(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S"))
        return _ago(t)
    except Exception:
        return str(iso)[:10]


# ── render ──────────────────────────────────────────────────────────────────
def _vent(K, lineas, tags, marca, ih, iw):
    """La ventana de git_tui pero ARRASTRANDO los tags del hit-map (cada
    línea sabe si es un repo/ítem clickeable). Bordes honestos ↑/↓."""
    n = len(lineas)
    if n <= ih or ih < 3:
        m = max(1, ih)
        if n > ih:
            return lineas[:m], tags[:m]
        return lineas, tags
    start = max(0, min(marca - ih // 2, n - ih))
    if start > 0 and marca <= start:
        start = max(0, marca - 1)
    end = min(n, start + ih)
    start = max(0, end - ih)
    if end < n and marca >= end - 1:
        end = min(n, marca + 2)
        start = max(0, end - ih)
    out, tgs = list(lineas[start:end]), list(tags[start:end])
    if start > 0:
        out[0] = HL.clip(" %s↑ %d más arriba%s" % (K["DK"], start, K["R"]),
                         iw)
        tgs[0] = None
    if end < n:
        out[-1] = HL.clip(" %s↓ %d más abajo%s" % (K["DK"], n - end, K["R"]),
                          iw)
        tgs[-1] = None
    return out, tgs


def _fila_estado(S, K, w):
    """La línea de contexto: la PUERTA de la sesión, siempre visible."""
    a = S["auth"]
    if a["ok"]:
        trozos = ["%s%s gh: %s%s" % (K["OK"], K["CHECK"],
                                     a["account"] or "sesión activa",
                                     K["R"]),
                  "%s%d repo%s%s" % (K["GREY"], len(S["repos"]),
                                     "" if len(S["repos"]) == 1 else "s",
                                     K["R"]),
                  "%snube solo con f — nada corre solo%s" % (K["DK"],
                                                             K["R"])]
        if S["fetching"]:
            trozos.append("%sconsultando %s…%s"
                          % (K["C"], " ".join(sorted(S["fetching"])),
                             K["R"]))
    else:
        trozos = ["%s✗ sin sesión de GitHub%s" % (K["BAD"] + K["BO"],
                                                  K["R"]),
                  "%sconéctate: gh auth login%s" % (K["WH"] + K["BO"],
                                                    K["R"]),
                  "%slo local sigue: m abre el mapa de ramas%s"
                  % (K["GREY"], K["R"])]
    fila = " " + (" %s·%s " % (K["DK"], K["R"])).join(trozos)
    leg = "%sr re-verifica%s" % (K["DK"], K["R"])
    hueco = (w - 1) - HL.vis(fila) - HL.vis(leg) - 1
    if hueco > 1:
        fila += " " * hueco + leg
    return HL.clip(fila, w - 1)


def _bullet(K, ln, iw):
    """Un bullet `· texto` con continuaciones INDENTADAS (el punto no se
    repite en el wrap)."""
    subs = GT._wrap(ln, max(8, iw - 4))
    out = [HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"], subs[0],
                                      K["R"]), iw)]
    for sub in subs[1:]:
        out.append(HL.clip("   %s%s%s" % (K["DIM"], sub, K["R"]), iw))
    return out


def _fila_repo(S, K, r, i, iw):
    """Una fila del listado: cursor · ⌂/◦ · nombre · resumen · hace."""
    sel = (i == S["si"])
    foc = sel and S["focus"] == "repos"
    cur = ("%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if foc else
           "%s%s%s" % (K["DK"], K["PTR"], K["R"]) if sel else " ")
    glyph = ("%s⌂%s" % (K["B2"], K["R"]) if r["harness"]
             else "%s◦%s" % (K["DK"], K["R"]))
    nombre = r["slug"] or (r["name"] + " (sin github)")
    nw = max(14, min(26, iw - 19))               # deja aire al resumen
    ncol = (K["WH"] + K["BO"]) if sel else K["GREY"]
    d = S["cloud"].get(r["slug"]) or {}
    if r["slug"] in S["fetching"]:
        info = "%sconsultando…%s" % (K["C"], K["R"])
    elif d.get("stamped"):
        info = "%s%dPR·%diss%s" % (K["B2"], len(d.get("prs") or []),
                                   len(d.get("issues") or []), K["R"])
    elif not r["slug"]:
        info = "%ssolo local%s" % (K["DK"], K["R"])
    else:
        info = "%ssin consultar%s" % (K["DK"], K["R"])
    ago = ("%s%s%s" % (K["DK"], _ago(d["stamped"]), K["R"])
           if d.get("stamped") else "")
    ln = " %s %s %s%s%s %s" % (cur, glyph, ncol, HL.pad(nombre, nw),
                               K["R"], info)
    hueco = iw - HL.vis(ln) - HL.vis(ago)
    if hueco > 1 and ago:
        ln += " " * hueco + ago
    return HL.clip(ln, iw)


def _cuerpo_repos(S, K, iw):
    """Caja izquierda: el harness y los conectados. (líneas, tags, marca)."""
    out, tags, marca = [], [], 0

    def add(ln, tag=None):
        out.append(ln)
        tags.append(tag)

    add(GT._divisor(K, "este harness", iw, tono=0))
    for i, r in enumerate(S["repos"]):
        if i == 1:
            add("")
            add(GT._divisor(K, "conectados", iw, tono=2))
        if i == S["si"]:
            marca = len(out)
        add(_fila_repo(S, K, r, i, iw), ("repo", i))
    if len(S["repos"]) == 1:                     # primer uso: guía de 1 paso
        add("")
        add(GT._divisor(K, "conectados", iw, tono=2))
        add(HL.clip(" %sninguno todavía — es 1 paso:%s"
                    % (K["DIM"], K["R"]), iw))
        add(HL.clip(" %s%s a%s %selige un repo local detectado%s"
                    % (K["C"] + K["BO"], K["PTR"], K["R"], K["GREY"],
                       K["R"]), iw), ("add", 0))
        add(HL.clip("   %s(o pega owner/nombre · también con click aquí)%s"
                    % (K["DK"], K["R"]), iw), ("add", 0))
    return out, tags, marca


def _add_opts(S):
    """Los repos locales elegibles del selector (del último escaneo)."""
    return (S.get("found") or [])[:30]


def _cuerpo_conectar(S, K, iw):
    """Caja derecha en modo CONECTAR: SELECTOR de repos git locales
    detectados en el disco — elegir con ↑↓/click en vez de teclear.
    (líneas, tags, marca) para que el click y la ventana funcionen."""
    out, tags, marca = [], [], 0

    def add(ln, tag=None):
        out.append(ln)
        tags.append(tag)

    opts = _add_opts(S)
    con = {x["repo"].lower() for x in _cfg_repos()}
    for rr in S["repos"]:
        if rr.get("slug"):
            con.add(rr["slug"].lower())
    add(HL.clip(" %sconectar un repo — elige uno local o escríbelo%s"
                % (K["DIM"], K["R"]), iw))
    add("")
    add(GT._divisor(K, "repos locales detectados"
                    + (" · %d" % len(opts) if opts else ""), iw, tono=0))
    if S.get("scan"):
        add(HL.clip(" %sbuscando repos en tu disco… (solo lectura local, "
                    "cero red)%s" % (K["C"], K["R"]), iw))
    elif not opts:
        add(HL.clip(" %sno encontré repos git en las carpetas comunes — "
                    "escríbelo abajo%s" % (K["DK"], K["R"]), iw))
    for i, opt in enumerate(opts):
        sel = (i == S.get("ai", 0))
        if sel:
            marca = len(out)
        cur = ("%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel
               else " ")
        ncol = (K["WH"] + K["BO"]) if sel else K["GREY"]
        nw = max(12, min(22, iw - 32))
        slug = opt.get("slug") or ""
        if slug:
            etiq = "%s%s%s" % (K["B2"], slug, K["R"])
            if slug.lower() in con:
                etiq += " %s%s ya%s" % (K["OK"], K["CHECK"], K["R"])
        else:
            etiq = "%ssin origin github%s" % (K["DK"], K["R"])
        ruta = ("%s%s%s" % (K["DK"],
                            opt["path"].replace(os.path.expanduser("~"),
                                                "~"), K["R"]))
        ln = " %s %s%s%s %s" % (cur, ncol,
                                HL.pad(str(opt.get("name", ""))[:nw], nw),
                                K["R"], etiq)
        hueco = iw - HL.vis(ln) - HL.vis(ruta)
        if hueco > 1:
            ln += " " * hueco + ruta
        add(HL.clip(ln, iw), ("pick", i))
    add("")
    add(GT._divisor(K, "a mano", iw, tono=2))
    sel = (S.get("ai", 0) >= len(opts))
    if sel:
        marca = len(out)
    cur = ("%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " ")
    add(HL.clip(" %s %sescribir owner/nombre · URL de github.com · o una "
                "carpeta%s" % (cur, (K["WH"] + K["BO"]) if sel
                               else K["GREY"], K["R"]), iw),
        ("manual", 0))
    add("")
    for ln in ("Enter conecta lo elegido — solo se apunta en tu lista "
               "per-máquina (github-repos.json)",
               "no clona, no toca la red, no guarda tokens — la sesión "
               "la maneja gh",
               "escribe cualquier letra y pasas directo al campo de "
               "texto · Esc cancela"):
        for sub in _bullet(K, ln, iw):
            add(sub)
    return out, tags, marca


def _cuerpo_escribir(S, K, iw):
    """Caja derecha en modo A MANO: el campo + qué pasará exactamente."""
    out = [HL.clip(" %sconectar un repo de GitHub — a mano%s"
                   % (K["DIM"], K["R"]), iw),
           HL.clip(" %s%s%s %s%s%s█%s" % (K["C"] + K["BO"], K["PTR"],
                                          K["R"], K["WH"], S["buf"],
                                          K["C"] + K["BO"], K["R"]), iw),
           ""]
    for ln in ("owner/nombre · URL de github.com · o una carpeta local "
               "clonada",
               "solo se apunta en tu lista per-máquina "
               "(~/.claude/workspace/github-repos.json)",
               "no clona, no toca la red, no guarda tokens — la sesión "
               "la maneja gh",
               "Enter conecta · Esc vuelve al selector"):
        out += _bullet(K, ln, iw)
    return out


def _chk_glyph(K, st):
    return {"ok": "%s%s%s" % (K["OK"], K["CHECK"], K["R"]),
            "fail": "%s×%s" % (K["BAD"], K["R"]),
            "pend": "%s●%s" % (K["C"], K["R"])}.get(
                st, "%s·%s" % (K["DK"], K["R"]))


def _fila_item(S, K, kind, obj, idx, iw):
    """Una fila seleccionable del detalle, por tipo."""
    sel = (S["focus"] == "detalle" and idx == S["ci"])
    cur = ("%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " ")
    ncol = (K["WH"] + K["BO"]) if sel else K["GREY"]
    left, right = "", ""
    if kind == "pr":
        left = " %s %s %s#%s%s %s%s%s" % (
            cur, _chk_glyph(K, obj.get("checks", "")), K["B"] + K["BO"],
            obj.get("number", "?"), K["R"], ncol,
            str(obj.get("title", ""))[:60], K["R"])
        right = "%s%s→%s%s%s" % (K["DK"], obj.get("headRefName", "")[:18],
                                 obj.get("baseRefName", ""),
                                 " ·borrador" if obj.get("isDraft") else "",
                                 K["R"])
    elif kind == "issue":
        left = " %s %s◌%s %s#%s%s %s%s%s" % (
            cur, K["B2"], K["R"], K["B"], obj.get("number", "?"), K["R"],
            ncol, str(obj.get("title", ""))[:60], K["R"])
        right = "%s%s%s" % (K["DK"], _iso_ago(obj.get("updatedAt", "")),
                            K["R"])
    elif kind == "lbranch":
        glifo = ("%s●%s" % (K["OK"], K["R"]) if obj.get("current")
                 else "%s○%s" % (K["DK"], K["R"]))
        left = " %s %s %s%s%s" % (cur, glifo, ncol,
                                  str(obj.get("name", ""))[:40], K["R"])
        right = ("%saquí está tu copia%s" % (K["DK"], K["R"])
                 if obj.get("current") else
                 ("%sEnter cambia a esta rama%s" % (K["C"], K["R"])
                  if sel else ""))
    elif kind == "branch":
        left = " %s %s%s%s %s%s%s" % (cur, K["C"], K["BRANCH"], K["R"],
                                      ncol, str(obj.get("name", ""))[:40],
                                      K["R"])
        if obj.get("protected"):
            right = "%sprotegida%s" % (K["DK"], K["R"])
    elif kind == "commit":
        left = " %s %s%s%s %s%s%s" % (cur, K["B2"], obj.get("short", "?"),
                                      K["R"], ncol,
                                      str(obj.get("msg", ""))[:56], K["R"])
        right = "%s%s%s" % (K["DK"], _iso_ago(obj.get("date", "")), K["R"])
    elif kind == "release":
        left = " %s %s◆%s %s%s%s" % (cur, K["B"] + K["BO"], K["R"], ncol,
                                     str(obj.get("tagName", ""))[:30],
                                     K["R"])
        right = "%s%s%s" % (K["DK"], "borrador" if obj.get("isDraft")
                            else "publicado", K["R"])
    elif kind == "run":
        st = ("ok" if (obj.get("conclusion") or "").lower() == "success"
              else "fail" if (obj.get("conclusion") or "").lower() in
              ("failure", "cancelled", "timed_out")
              else "pend")
        left = " %s %s %s%s%s" % (cur, _chk_glyph(K, st), ncol,
                                  str(obj.get("displayTitle", ""))[:50],
                                  K["R"])
        right = "%s%s%s" % (K["DK"], str(obj.get("headBranch", ""))[:18],
                            K["R"])
    ln = left
    hueco = iw - HL.vis(ln) - HL.vis(right)
    if hueco > 1 and right:
        ln += " " * hueco + right
    return HL.clip(ln, iw)


def _det_body(S, K, iw):
    """Caja derecha: el repo seleccionado explicado. (líneas, tags, marca)."""
    out, tags, marca = [], [], 0

    def add(ln, tag=None):
        out.append(ln)
        tags.append(tag)

    r = _sel_repo(S)
    if not r:
        add(HL.clip(" %ssin repos%s" % (K["DK"], K["R"]), iw))
        return out, tags, 0
    slug = r["slug"]
    d = (S["cloud"].get(slug) or {}) if slug else {}
    v = d.get("view") or {}
    # encabezado: qué repo es y de cuándo son los datos
    priv = ("privado" if v.get("isPrivate") else
            "público" if v else "")
    add(HL.clip(" %s%s%s%s" % (K["C"] + K["BO"], slug or r["name"], K["R"],
                               ("  %s%s%s" % (K["DK"], priv, K["R"]))
                               if priv else ""), iw))
    desc = str(v.get("description") or "").strip()
    if desc:
        for ln in GT._wrap(desc, max(8, iw - 2))[:2]:
            add(HL.clip(" %s%s%s" % (K["DIM"], ln, K["R"]), iw))
    if slug:
        if slug in S["fetching"]:
            est = "%sconsultando GitHub…%s" % (K["C"], K["R"])
        elif d.get("stamped"):
            est = "%sconsultado %s — f refresca%s" % (K["DK"],
                                                      _ago(d["stamped"]),
                                                      K["R"])
        elif S["auth"]["ok"]:
            est = ("%ssin consultar — f trae PRs, issues, ramas, commits y "
                   "releases%s" % (K["DK"], K["R"]))
        else:
            est = "%ssin consultar%s" % (K["DK"], K["R"])
        add(HL.clip(" " + est, iw))
    local = r.get("local") or ""
    add(HL.clip(" %s%s%s" % (
        K["DK"],
        ("copia local · " + local.replace(os.path.expanduser("~"), "~"))
        if local and os.path.isdir(local)
        else "sin copia local — todo se abre en el navegador", K["R"]), iw))
    # ramas de la copia local — visibles AL INSTANTE, sin consultar la nube
    its = _det_items(S)
    lfilas = [(k, o) for k, o in its if k == "lbranch"]
    idx = 0
    if lfilas:
        tot_l = len(r.get("lbranches") or [])
        add("")
        add(GT._divisor(K, "ramas · copia local · %d" % tot_l, iw, tono=0))
        for k, o in lfilas:
            if S["focus"] == "detalle" and idx == S["ci"]:
                marca = len(out)
            add(_fila_item(S, K, k, o, idx, iw), ("det", idx))
            idx += 1
        if tot_l > len(lfilas):
            add(HL.clip("  %s… y %d más — m abre el mapa completo%s"
                        % (K["DK"], tot_l - len(lfilas), K["R"]), iw))
    # la puerta, explicada en su lugar
    if not S["auth"]["ok"]:
        add("")
        add(GT._divisor(K, "github desconectado", iw, tono=1))
        for ln in GT._wrap(S["auth"]["msg"], max(8, iw - 4)):
            add(HL.clip(" %s%s%s" % (K["BAD"], ln, K["R"]), iw))
        for ln in ("sin sesión NO se toca la red: cero consultas desde aquí",
                   "gh guarda tu sesión en el keyring del sistema — esta "
                   "pantalla nunca ve tokens",
                   "lo local sigue completo: m abre el mapa de ramas y "
                   "worktrees"):
            for sub in _bullet(K, ln, iw):
                add(sub)
    if not slug:
        add("")
        add(GT._divisor(K, "sin github", iw, tono=3))
        avisos = ["este repo no tiene origin de github.com — la nube no "
                  "aplica",
                  "m abre su mapa local de ramas y worktrees"]
        if lfilas:
            avisos.insert(1, "Enter o c en una rama de arriba cambia la "
                             "copia local (árbol limpio)")
        for ln in avisos:
            for sub in _bullet(K, ln, iw):
                add(sub)
        return out, tags, marca
    # secciones con datos (del cache — cero red aquí)
    if not d.get("stamped"):
        add("")
        add(GT._divisor(K, "qué verás al consultar", iw, tono=3))
        for ln in ("PRs abiertos con el estado de sus checks (✓ × ●)",
                   "issues abiertos · ramas remotas · commits recientes",
                   "releases y corridas de Actions",
                   "nada corre solo: f consulta, con tu sesión gh"):
            for sub in _bullet(K, ln, iw):
                add(sub)
    else:
        secciones = (
            ("prs", "revisiones abiertas · PR", 1),
            ("issues", "issues abiertos", 2),
            ("branches", "ramas remotas", 3),
            ("commits", "commits recientes · %s"
             % ((v.get("defaultBranchRef") or {}).get("name") or "default"),
             4),
            ("releases", "releases", 5),
            ("runs", "actions", 0),
        )
        for key, titulo, tono in secciones:
            total = len(d.get(key) or [])
            filas = [(k, o) for k, o in its
                     if k == {"prs": "pr", "issues": "issue",
                              "branches": "branch", "commits": "commit",
                              "releases": "release", "runs": "run"}[key]]
            add("")
            add(GT._divisor(K, "%s%s" % (titulo, " · %d" % total
                                         if total else ""), iw, tono=tono))
            if not filas:
                add(HL.clip(" %sninguno%s" % (K["DK"], K["R"]), iw))
            for k, o in filas:
                if S["focus"] == "detalle" and idx == S["ci"]:
                    marca = len(out)
                add(_fila_item(S, K, k, o, idx, iw), ("det", idx))
                idx += 1
            if total > len(filas):
                add(HL.clip("  %s… y %d más — Enter/o abre el repo en el "
                            "navegador%s" % (K["DK"], total - len(filas),
                                             K["R"]), iw))
    if d.get("errors"):
        add("")
        add(GT._divisor(K, "consultas fallidas", iw))
        for e in d["errors"][:4]:
            add(HL.clip(" %s%s%s" % (K["DK"], str(e)[:iw - 2], K["R"]), iw))
    # qué hace cada tecla AQUÍ (se dice antes de tocar)
    add("")
    add(GT._divisor(K, "acciones", iw))
    acc = [("Enter abre lo elegido en tu navegador — y en «ramas · copia "
            "local» cambia a esa rama") if lfilas else
           "Enter abre lo elegido en tu navegador — nunca modifica nada"]
    if local and os.path.isdir(local):
        acc.append("c cambia la copia local a la rama elegida (árbol "
                   "limpio, jamás --force) · m abre su mapa de ramas")
    if S["auth"]["ok"]:
        acc.append("f consulta GitHub otra vez · x desconecta (solo tu "
                   "lista)")
    else:
        acc.append("f está apagada sin sesión — gh auth login y r")
    for ln in acc:
        for sub in _bullet(K, ln, iw):
            add(sub)
    return out, tags, marca


# UNA fuente de verdad de los atajos POR MODO: la cabecera enseña los
# clave + salir (HL.top_hints recorta a 4) y el pie la lista COMPLETA
# (HL.foot_hints cede pares del final en angosto — adiós variante w<90).
_PARES_NAV = (("↑↓", "elige"), ("Tab/◄►", "foco"), ("Enter", "abre"),
              ("f", "consulta GitHub"), ("a", "conecta"),
              ("x", "desconecta"), ("c", "rama"), ("m", "mapa local"),
              ("q", "vuelve"))
_PARES_ADD = (("↑↓/click", "elige"), ("Enter", "conecta"),
              ("escribe", "para teclear a mano"), ("Esc", "cancela"))
_PARES_WRITE = (("escribe", "owner/nombre, URL o carpeta"),
                ("Enter", "conecta"), ("Esc", "vuelve al selector"))


def _pares_modo(S):
    return {"add": _PARES_ADD,
            "add_write": _PARES_WRITE}.get(S["modo"], _PARES_NAV)


def render(S, w, h):
    K = GT._K()
    S["hits"] = []
    # cabecera COMPARTIDA (wordmark + subtítulo + atajos clave + regla);
    # los atajos de arriba siguen el MODO (nav / conectar / teclear)
    L = HL.screen_header(
        K, w, h, "github — tus repos: ramas locales + PRs · issues · "
        "releases", hints=_pares_modo(S))
    L.append(_fila_estado(S, K, w))
    L.append("")
    top = len(L)
    apilado = w < 100
    lw = (w - 1) if apilado else max(34, min(48, (w - 6) * 42 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    avail = max(8, (h - 1) - top - 3)

    bi, ti, mi = _cuerpo_repos(S, K, lw - 4)
    r = _sel_repo(S)
    if S["modo"] == "add":
        bd, td, md = _cuerpo_conectar(S, K, rw - 4)
        t_der = "CONECTAR"
    elif S["modo"] == "add_write":
        bd = _cuerpo_escribir(S, K, rw - 4)
        td, md = [None] * len(bd), 0
        t_der = "CONECTAR"
    else:
        bd, td, md = _det_body(S, K, rw - 4)
        t_der = "DETALLE · %s" % ((r["slug"] or r["name"]) if r else "—")
    t_izq = "REPOS"
    foc_l = S["focus"] == "repos" and S["modo"] == "nav"

    def _caja(titulo, cuerpo, pw, ih, focused):
        return HL.full_box(titulo, cuerpo, K, pw, ih, focused,
                           border=K["C"] if focused else K["B2"],
                           label=None if focused else K["B"] + K["BO"])

    if apilado:                                  # ── angosto: APILADO ──
        ih_i = min(len(bi), max(5, (avail - 4) * 45 // 100))
        ih_d = max(3, min(len(bd), avail - 4 - ih_i))
        bi_v, ti_v = _vent(K, bi, ti, mi, ih_i, lw - 4)
        bd_v, td_v = _vent(K, bd, td, md, ih_d, rw - 4)
        base = len(L)
        for ln in _caja(t_izq, bi_v, lw - 1, ih_i, foc_l):
            L.append(HL.clip(" " + ln, w - 1))
        for j, tg in enumerate(ti_v):
            if tg:
                S["hits"].append((base + 1 + j, tg[0], tg[1]))
        base = len(L)
        for ln in _caja(t_der, bd_v, rw - 1, ih_d, not foc_l):
            L.append(HL.clip(" " + ln, w - 1))
        for j, tg in enumerate(td_v):
            if tg:
                S["hits"].append((base + 1 + j, tg[0], tg[1]))
    else:                                        # ── lado a lado ──
        ch = min(avail, max(len(bi), len(bd)) + 2)
        bi_v, ti_v = _vent(K, bi, ti, mi, ch - 2, lw - 4)
        bd_v, td_v = _vent(K, bd, td, md, ch - 2, rw - 4)
        izq = _caja(t_izq, bi_v, lw, ch - 2, foc_l)
        der = _caja(t_der, bd_v, rw, ch - 2, not foc_l)
        base = len(L)
        for i in range(ch):
            L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "",
                                          lw) + "  "
                             + (der[i] if i < len(der) else ""), w - 1))
        for j, tg in enumerate(ti_v):
            if tg:
                S["hits"].append((base + 1 + j, tg[0], tg[1]))
        for j, tg in enumerate(td_v):
            if tg:
                S["hits"].append((base + 1 + j, tg[0], tg[1]))
    L.append("")
    if S["modo"] == "confirm" and S.get("pend"):
        L.append(" %s⚠ desconectar %s — Enter confirma · Esc cancela (solo "
                 "sale de tu lista; nada se borra)%s"
                 % (K["BAD"] + K["BO"], S["pend"], K["R"]))
    elif S.get("msg"):
        L.append(" %s%s%s" % (K["B2"], S["msg"], K["R"]))
    else:
        L.append("")
    L.append(HL.foot_hints(K, _pares_modo(S), w))
    # ALTURA ESTABLE: h-1 líneas exactas, pie anclado (mismo contrato que
    # git_tui — el redraw jamás salta ni deja líneas rancias).
    falta = (h - 1) - len(L)
    if falta > 0:
        L[-2:-2] = [""] * falta
    return [HL.clip(x, w - 1) for x in L[:h - 1]]


# ── teclado + mouse ─────────────────────────────────────────────────────────
def _open_add(S):
    """Abre el selector de conexión. El escaneo de disco corre en 2º plano
    (solo lectura local, cero red) y el resultado queda cacheado para la
    sesión — abrirlo de nuevo lo refresca sin bloquear la pantalla."""
    S["modo"], S["buf"], S["ai"] = "add", "", 0
    if not S.get("scan"):
        S["scan"] = _Scan()
        S["scan"].start()


def _after_connect(S, slug):
    """Tras conectar: relee la lista y deja el cursor en el repo nuevo."""
    S["repos"] = repos_list()
    for i, r in enumerate(S["repos"]):
        if r["slug"].lower() == slug.lower():
            S["si"], S["ci"], S["focus"] = i, 0, "repos"
            break


def _connect_pick(S, opt):
    """Conecta el repo local elegido en el selector — por su CARPETA, para
    que su copia local quede registrada (y c/m funcionen de inmediato)."""
    slug, S["msg"] = connect(opt.get("path", ""))
    if slug:
        S["modo"] = "nav"
        _after_connect(S, slug)


def _activar_item(S):
    """Enter (o 2º click) sobre el ítem del detalle: una rama LOCAL cambia
    la copia a esa rama (guardas de siempre); lo demás abre el navegador."""
    r = _sel_repo(S)
    its = _det_items(S)
    if not r:
        return ""
    if its and S["ci"] < len(its):
        k, o = its[S["ci"]]
        if k == "lbranch":
            return _checkout(S, r, o.get("name", ""), remote=False)
        if r["slug"]:
            return _abrir(_item_url(r["slug"], k, o))
    if r["slug"]:
        return _abrir("https://github.com/" + r["slug"])
    return "este repo no tiene página de GitHub"


def _click(S, y):
    """Click en una fila del hit-map: 1º click apunta, 2º click actúa."""
    row = y - 1                                  # pantalla 1-based → índice
    hits = S.get("hits", [])
    if S["modo"] == "add":                       # en el selector mandan SUS
        hits = [t for t in hits if t[1] in ("pick", "manual")]   # filas
    for (ln, kind, idx) in hits:
        if ln != row:
            continue
        if kind == "repo":
            if S["si"] == idx and S["focus"] == "repos":
                S["focus"], S["ci"] = "detalle", 0
            else:
                S["si"], S["ci"], S["focus"] = idx, 0, "repos"
        elif kind == "add":                      # la guía de primer uso
            _open_add(S)
        elif kind == "pick":                     # repo local del selector
            opts = _add_opts(S)
            if S["modo"] == "add" and S.get("ai", 0) == idx and \
                    idx < len(opts):
                _connect_pick(S, opts[idx])
            else:
                S["ai"] = idx
        elif kind == "manual":                   # la fila «a mano»
            S["modo"], S["buf"] = "add_write", ""
        else:                                    # ítem del detalle
            if S["focus"] == "detalle" and S["ci"] == idx:
                S["msg"] = _activar_item(S)
            else:
                S["focus"], S["ci"] = "detalle", idx
        return True
    return True


def _action(S, key):
    """False = salir. Navegar NO toca git ni la red (cero subprocess por
    keypress); las acciones lo dicen antes de hacerlo."""
    S["msg"] = ""
    if isinstance(key, tuple) and key and key[0] == "mouse":
        return _click(S, key[2])

    if S["modo"] == "add":                       # ── selector de repos ──
        opts = _add_opts(S)
        n = len(opts) + 1                        # +1: la fila «a mano»
        if key == "\x1b":
            S["modo"], S["msg"] = "nav", "cancelado"
        elif key == "up":
            S["ai"] = (S.get("ai", 0) - 1) % n
        elif key in ("down", "tab"):
            S["ai"] = (S.get("ai", 0) + 1) % n
        elif key in ("\r", "\n"):
            if S.get("ai", 0) < len(opts):
                _connect_pick(S, opts[S["ai"]])
            else:                                # «a mano» → el campo
                S["modo"], S["buf"] = "add_write", ""
        elif (isinstance(key, str) and len(key) == 1
              and key.isprintable()):            # teclear = ir al campo
            S["modo"], S["buf"] = "add_write", key
        return True

    if S["modo"] == "add_write":                 # ── capturando el repo ──
        if key == "\x1b":
            S["modo"], S["buf"] = "add", ""      # vuelve al selector
        elif key in ("\r", "\n"):
            buf = S["buf"]
            S["buf"] = ""
            slug, S["msg"] = connect(buf)
            if slug:
                S["modo"] = "nav"
                _after_connect(S, slug)
            elif not buf.strip():
                S["modo"] = "nav"                # Enter vacío = cancelar
        elif key in ("\x7f", "\b", "\x08"):
            S["buf"] = S["buf"][:-1]
        elif (isinstance(key, str) and len(key) == 1 and key.isprintable()
              and len(S["buf"]) < 120):
            S["buf"] += key
        return True

    if S["modo"] == "confirm":                   # ── confirmación de x ──
        if key in ("\r", "\n"):
            slug = S.get("pend")
            S["modo"], S["pend"] = "nav", None
            S["msg"] = disconnect(slug) if slug else "nada que desconectar"
            S["repos"] = repos_list()
            S["si"] = min(S["si"], len(S["repos"]) - 1)
        elif key not in ("", None):
            S["modo"], S["pend"] = "nav", None
            S["msg"] = "cancelado — el repo sigue en tu lista"
        return True

    if key in ("q", "Q", "\x03"):
        return False
    if key == "\x1b":
        if S["focus"] == "detalle":
            S["focus"] = "repos"
            return True
        return False

    its = _det_items(S)
    r = _sel_repo(S)
    if key == "up":
        if S["focus"] == "repos":
            S["si"] = (S["si"] - 1) % max(1, len(S["repos"]))
            S["ci"] = 0
        else:
            S["ci"] = (S["ci"] - 1) % max(1, len(its))
    elif key == "down":
        if S["focus"] == "repos":
            S["si"] = (S["si"] + 1) % max(1, len(S["repos"]))
            S["ci"] = 0
        else:
            S["ci"] = (S["ci"] + 1) % max(1, len(its))
    elif key == "tab":
        S["focus"] = "detalle" if S["focus"] == "repos" else "repos"
        S["ci"] = min(S["ci"], max(0, len(its) - 1))
    elif key == "left":
        S["focus"] = "repos"
    elif key == "right":
        S["focus"] = "detalle"
        S["ci"] = min(S["ci"], max(0, len(its) - 1))
    elif key in ("\r", "\n"):
        if S["focus"] == "repos":
            if r and (r["slug"] or its):         # con ramas locales también
                S["focus"], S["ci"] = "detalle", 0
                if r["slug"] and not its:
                    S["msg"] = _abrir("https://github.com/" + r["slug"])
            else:
                S["msg"] = ("este repo no tiene GitHub — m abre su mapa "
                            "local de ramas")
        else:
            S["msg"] = _activar_item(S)
    elif key in ("f", "F"):
        if not S["auth"]["ok"]:
            S["msg"] = ("sin sesión de GitHub no consulto nada — corre "
                        "gh auth login y luego r")
        elif not (r and r["slug"]):
            S["msg"] = "este repo no tiene GitHub que consultar"
        elif r["slug"] in S["fetching"]:
            S["msg"] = "ya estoy consultando %s — un momento" % r["slug"]
        else:
            th = _Fetch(r["slug"])
            S["fetching"][r["slug"]] = th
            th.start()
            S["msg"] = ("consultando %s en segundo plano — la pantalla "
                        "sigue viva" % r["slug"])
    elif key in ("a", "A"):
        _open_add(S)
    elif key in ("x", "X"):
        if not r or r["harness"]:
            S["msg"] = ("el harness no se desconecta — es la base de esta "
                        "pantalla")
        else:
            S["modo"], S["pend"] = "confirm", r["slug"]
    elif key in ("m", "M"):
        local = (r or {}).get("local") or ""
        if local and os.path.isdir(local):
            S["open_map"] = local
        else:
            S["msg"] = ("sin copia local no hay mapa — a abre el selector "
                        "de repos locales (o pega su carpeta)")
    elif key in ("o", "O"):
        if r and r["slug"]:
            S["msg"] = _abrir("https://github.com/" + r["slug"])
        else:
            S["msg"] = "este repo no tiene página de GitHub"
    elif key in ("c", "C"):
        if (S["focus"] == "detalle" and its and S["ci"] < len(its)
                and its[S["ci"]][0] in ("branch", "lbranch")):
            k, o = its[S["ci"]]
            S["msg"] = _checkout(S, r, o.get("name", ""),
                                 remote=(k == "branch"))
        else:
            S["msg"] = ("c cambia la copia local a una RAMA — elige una en "
                        "«ramas» (Tab + ↑↓ o click)")
    elif key in ("r", "R"):
        S["auth"] = auth_check()
        S["repos"] = repos_list()
        S["cloud"] = _load(_cache_path(), {})
        S["si"] = min(S["si"], len(S["repos"]) - 1)
        S["msg"] = ("sesión y lista releídas ✓ — gh: %s"
                    % (S["auth"]["account"] or "sin sesión")
                    if S["auth"]["ok"] else
                    "lista releída — sigue sin sesión de GitHub")
    return True


import responsive_ui as _responsive                             # noqa: E402
render = _responsive.renderer(render, "GITHUB")
_action = _responsive.action(_action)


# ── drivers (mismo patrón que git_tui, + mouse SGR fail-soft) ───────────────
def _size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 100, 34


def _draw(tout, S, first=False):
    _poll(S)
    w, h = _size()
    try:
        _responsive.paint(tout, render(S, w, h), first=first)
    except Exception:
        pass


def _read_key(fd, decoder):
    """Una tecla (o ('mouse',x,y)); '' = ignorar; None = EOF. Drena los CSI
    completos (mismo contrato que el hub: cero teclas fantasma)."""
    import select
    raw = os.read(fd, 1)
    if not raw:
        return None
    ch = decoder.decode(raw)
    if not ch:
        return ""
    if ch == "\t":
        return "tab"
    if ch != "\x1b":
        return ch
    if not select.select([fd], [], [], 0.05)[0]:
        return "\x1b"
    if os.read(fd, 1).decode("utf-8", "replace") != "[":
        return "\x1b"
    seq = ""
    while True:
        if not select.select([fd], [], [], 0.05)[0]:
            return ""
        c = os.read(fd, 1).decode("utf-8", "replace")
        if not c:
            return ""
        if c == "M" and not seq:                 # mouse X10: 3 bytes crudos
            for _ in range(3):
                if select.select([fd], [], [], 0.05)[0]:
                    os.read(fd, 1)
            return ""
        seq += c
        if c.isalpha() or c == "~":
            break
        if len(seq) > 24:
            return ""
    flechas = {"A": "up", "B": "down", "C": "right", "D": "left"}
    if seq in flechas:
        return flechas[seq]
    if seq.startswith("<") and seq[-1] in "Mm":  # mouse SGR-1006
        try:
            b, x, y = (int(v) for v in seq[1:-1].split(";"))
        except Exception:
            return ""
        if seq[-1] == "M" and (b & ~28) == 0:    # press izquierdo
            return ("mouse", x, y)
        return ""
    return ""


def _sub_map(path):
    """Abre el mapa local (git_tui, INTACTO) sobre `path` y regresa — esta
    pantalla solo le presta la terminal al mapa de siempre."""
    prev = os.environ.get("WORKSPACE_DEV_GIT_ROOT")
    try:
        if os.path.realpath(path) != os.path.realpath(GT._repo()):
            os.environ["WORKSPACE_DEV_GIT_ROOT"] = path
        GT.run()
    except Exception:
        pass
    finally:
        if prev is None:
            os.environ.pop("WORKSPACE_DEV_GIT_ROOT", None)
        else:
            os.environ["WORKSPACE_DEV_GIT_ROOT"] = prev


_MOUSE_ON, _MOUSE_OFF = "\033[?1000;1006h", "\033[?1000;1006l"


def _run_unix(S):
    import codecs
    import select
    import termios
    import tty
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        tout = open("/dev/tty", "w")
    except Exception:
        return _listado(S)
    old = termios.tcgetattr(fd)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h" + _MOUSE_ON)
        _draw(tout, S, first=True)
        while True:
            # cadencia: viva cuando hay consulta/job (0.15s), calma si no
            tick = (0.15 if (S["fetching"] or S.get("job")
                             or S.get("scan")) else 0.5)
            if not select.select([fd], [], [], tick)[0]:
                _draw(tout, S)
                continue
            key = _read_key(fd, decoder)
            if key is None:
                break
            if key == "":
                continue
            if not _action(S, key):
                break
            target = S.pop("open_map", None)
            if target:                           # mapa local anidado
                tout.write(_MOUSE_OFF + "\033[?1049l")
                tout.flush()
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
                _sub_map(target)
                tty.setraw(fd)
                tout.write("\033[?1049h" + _MOUSE_ON)
                _draw(tout, S, first=True)
                continue
            _draw(tout, S)
    finally:
        try:
            tout.write(_MOUSE_OFF + "\033[?1049l")
            tout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.close(fd)
        except Exception:
            pass
    return 0


def _run_windows(S):
    import msvcrt
    tout = sys.stdout
    tout.write("\033[?1049h")                    # sin mouse en Windows: teclas
    _draw(tout, S, first=True)
    try:
        while True:
            if not msvcrt.kbhit():
                _draw(tout, S)
                time.sleep(0.15 if (S["fetching"] or S.get("job")
                                    or S.get("scan")) else 0.3)
                continue
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                a = msvcrt.getwch()
                key = {"H": "up", "P": "down", "M": "right",
                       "K": "left"}.get(a, "")
            elif ch == "\t":
                key = "tab"
            else:
                key = ch
            if not key:
                continue
            if not _action(S, key):
                break
            target = S.pop("open_map", None)
            if target:
                tout.write("\033[?1049l")
                tout.flush()
                _sub_map(target)
                tout.write("\033[?1049h")
                _draw(tout, S, first=True)
                continue
            _draw(tout, S)
    finally:
        try:
            tout.write("\033[?1049l")
            tout.flush()
        except Exception:
            pass
    return 0


def _listado(S=None):
    """Sin terminal interactiva: el estado plano (auth + repos + cache)."""
    S = S or _state()
    a = S["auth"]
    print("github: %s" % ("sesión gh %s ✓" % (a["account"] or "activa")
                          if a["ok"] else a["msg"]))
    for r in S["repos"]:
        d = S["cloud"].get(r["slug"]) or {}
        extra = ""
        if d.get("stamped"):
            extra = " · %d PR · %d issues · %s" % (
                len(d.get("prs") or []), len(d.get("issues") or []),
                _ago(d["stamped"]))
        print(" %s %-36s%s" % ("⌂" if r["harness"] else "·",
                               r["slug"] or (r["name"] + " (sin github)"),
                               extra))
    return 0


def run():
    """Abre la pantalla. Sin tty cae al listado de texto; nunca truena."""
    S = _state()
    try:
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactivo = False
    if not interactivo:
        return _listado(S)
    try:
        if os.name == "nt":
            return _run_windows(S)
        return _run_unix(S)
    except Exception as e:
        try:
            sys.stdout.write(_MOUSE_OFF + "\033[?1049l")
        except Exception:
            pass
        print("github: %s" % e)
        return _listado(S)


if __name__ == "__main__":
    sys.exit(run())
