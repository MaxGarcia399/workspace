#!/usr/bin/env python3
"""WORKSPACE · git_tui — pantalla de RAMAS: el git del harness de un vistazo.

La versión TERMINAL de la sección «branches» del dev panel (pedido del socio
2026-10-02, para comparar contra la versión web). Mismo esqueleto que
`calendario_tui`/`tono_tui`: el wordmark del hub, la paleta del TEMA activo,
dos cajas `full_box` lado a lado — entrar aquí es cambiar de vista, no de app.

  · Caja izquierda **RAMAS**: el mapa — tronco (main · stable), features y
    treehouse (worktrees), cada rama con ↑adelante/↓atrás vs main, su último
    commit y quién la trabaja (⌂ agente). La rama actual lleva ●.
  · Caja derecha **DETALLE**: la transparencia — la rama seleccionada
    explicada en palabras: qué tan lejos está de main, qué archivos cambia
    (diff vs main), quién la tiene tomada, sus commits recientes, y qué hace
    cada tecla ANTES de tocarla.

Acciones (espejo seguro del dev panel — mismas guardas que dash/dev/_git.py):
  Enter/c  cambiar a la rama     — rechaza si hay cambios sin commitear o si
                                   la rama vive en un worktree (explica qué hacer)
  n        nueva rama desde main — kebab-case estricto → feat/<slug>
                                   («fix <slug>» → fix/<slug>); no cambia tu
                                   rama ni toca el árbol; reversible
  o        abrir la carpeta del worktree en el explorador
  x        liberar un worktree   — SOLO si está limpio; confirmación de 2
                                   pasos; jamás --force (regla de oro: no
                                   perder trabajo); pool tibio → se respeta
  r        refrescar             q  volver al menú

El panel operativo (git_panel.py + git_ops.py) agrega acciones, historial,
revisión, GitHub, proyectos y monitoreo. Tab cambia vista; a abre acciones.
Los comandos se preparan y explican antes de ejecutarse; corren en background.

Falla-suave en TODO: sin git / repo raro → un aviso en pantalla, nunca un
crash. Sin terminal interactiva cae a un listado de texto. El repo es la raíz
del harness (overridable con WORKSPACE_DEV_GIT_ROOT para tests herméticos —
mismo contrato que dash/dev/_git.py). Los datos se leen al entrar y al actuar
(r refresca): cero subprocess por keypress.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import json
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
import os
import re
import subprocess
import sys
import time
from theme import screen as _theme_screen  # fondo/tinta del tema

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import hublayout as HL                                          # noqa: E402


def _t(key, es, **kw):
    """i18n lado cliente, falla-suave: `key` en el idioma activo (catálogo
    lang/<code>/versiones.py); sin i18n / clave faltante → el español inline
    `es` (paridad exacta). .format(**kw) falla-suave."""
    s = es
    try:
        import i18n
        v = i18n.t(key)
        if v != key:
            s = v
    except Exception:
        s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s

US = "\x1f"
# Windows: sin consola, cada git hijo abriría una ventana. No-op en POSIX.
_NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}
# slug de feature: MISMO contrato kebab-case que `workspace feature` y el
# dev panel (dash/dev/_git.create_branch) — esto además es la anti-inyección.
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_DIFF_FILES = 6          # top de archivos del resumen de diff en DETALLE


# ── git (standalone: espejo mínimo de dash/dev/_git.py, que es dev-only y
#    no viaja en la distro — esta pantalla no debe depender de él) ──────────
def _repo():
    return os.environ.get("WORKSPACE_DEV_GIT_ROOT") or ROOT


_AGO_PART = re.compile(r"^(\d+) (second|minute|hour|day|week|month|year)s?$")
_AGO_ES = {"second": ("{n} segundo", "{n} segundos"),
           "minute": ("{n} minuto", "{n} minutos"),
           "hour": ("{n} hora", "{n} horas"),
           "day": ("{n} día", "{n} días"),
           "week": ("{n} semana", "{n} semanas"),
           "month": ("{n} mes", "{n} meses"),
           "year": ("{n} año", "{n} años")}


def ago_text(s):
    """La fecha relativa de git (`%cr`, siempre en inglés: «3 hours ago»,
    «1 year, 2 months ago») en el idioma de la UI. Formato raro → tal cual."""
    s = (s or "").strip()
    if not s.endswith(" ago"):
        return s
    parts = []
    for p in s[:-4].split(", "):
        m = _AGO_PART.match(p.strip())
        if not m:
            return s
        n, unit = int(m.group(1)), m.group(2)
        one, many = _AGO_ES[unit]
        parts.append(_t("versiones.ago.%s.%s" % (unit, "one" if n == 1 else "many"),
                        one if n == 1 else many, n=n))
    return _t("versiones.ago.wrap", "hace {x}", x=", ".join(parts))


def _git(args, repo=None, timeout=10):
    """(ok, stdout, stderr). Falla-suave: git ausente/timeout → (False,…)."""
    try:
        p = subprocess.run(["git"] + list(args), cwd=repo or _repo(),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, **_NO_WINDOW)
        return (p.returncode == 0, (p.stdout or "").strip(),
                (p.stderr or "").strip())
    except FileNotFoundError:
        return (False, "", _t("versiones.map.no_git", "git no está disponible"))
    except Exception as e:
        return (False, "", str(e))


def _has_ref(ref, repo=None):
    return _git(["rev-parse", "--verify", "--quiet", ref], repo)[0]


def _count(rng, repo=None):
    ok, out, _ = _git(["rev-list", "--count", rng], repo)
    try:
        return int(out) if ok else 0
    except ValueError:
        return 0


def _ahead_behind(base, ref, repo=None):
    """(ahead, behind) de `ref` vs `base` en UNA llamada (--left-right) —
    con 20+ ramas esto es lo que mantiene la entrada a la pantalla rápida."""
    ok, out, _ = _git(["rev-list", "--left-right", "--count",
                       "%s...%s" % (base, ref)], repo)
    p = out.split() if ok else []
    if len(p) == 2 and p[0].isdigit() and p[1].isdigit():
        return int(p[1]), int(p[0])
    return 0, 0


def _meta(ref, repo=None):
    """Último commit de `ref` → {sha, subject, ago} o None."""
    ok, out, _ = _git(["log", "-1", "--format=%h%x1f%s%x1f%cr", ref], repo)
    parts = out.split(US) if ok and out else []
    return ({"sha": parts[0], "subject": parts[1], "ago": parts[2]}
            if len(parts) >= 3 else None)


def _recientes(ref, n, repo=None):
    ok, out, _ = _git(["log", "-%d" % n, "--format=%h%x1f%s%x1f%cr", ref],
                      repo)
    rows = []
    for line in (out.splitlines() if ok else []):
        p = line.split(US)
        if len(p) >= 3:
            rows.append({"sha": p[0], "subject": p[1], "ago": p[2]})
    return rows


def _owners():
    """Registry de dueños de worktree (~/.claude/workspace/worktree-owners.json
    — lo escriben `workspace worktree` y los hooks). {} si falta/corrupto."""
    try:
        p = os.path.join(_paths.state_dir(),
                         "worktree-owners.json")
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _owner_clear(branch):
    """Quita la entrada de `branch` del registry (atómico, falla-suave)."""
    try:
        p = os.path.join(_paths.state_dir(),
                         "worktree-owners.json")
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        if not isinstance(d, dict) or branch not in d:
            return
        del d[branch]
        tmp = "%s.tmp%d" % (p, os.getpid())
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        pass


def _wt_clean(path):
    """¿El worktree está limpio? True/False/None (indeterminado → no tocar)."""
    if not path or not os.path.isdir(path):
        return None
    ok, out, _ = _git(["-C", path, "status", "--porcelain"])
    return (out.strip() == "") if ok else None


def snapshot(repo=None):
    """TODO el estado que pinta la pantalla, en una pasada (no por keypress):

      { repo, nombre, current, dirty, dirty_count,
        tronco:   [rama…]   main + stable (local u origin — remote_only),
        features: [rama…]   el resto, con ahead/behind vs main,
        wts:      [árbol…]  worktrees aparte: path, rama, dueño, limpio,
        unpushed, ready }   main vs origin · main por promover a stable

    rama = {name, current, sha, subject, ago, ahead, behind, base,
            remote_only, wt:{path,agent}|None}. {error:…} si no es repo."""
    repo = repo or _repo()
    ok, out, _ = _git(["rev-parse", "--is-inside-work-tree"], repo)
    if not (ok and out == "true"):
        return {"error": _t("versiones.map.not_repo",
                            "no es un repositorio git (o git no está "
                            "disponible)"),
                "repo": repo, "nombre": os.path.basename(repo.rstrip("/\\"))}

    ok, out, _ = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    current = out if ok and out != "HEAD" else ""
    # UNA pasada por todas las ramas locales: nombre + sha + subject + hace
    # (%1f = unit separator — jamás aparece en un subject)
    metas = {}
    ok, out, _ = _git(["for-each-ref",
                       "--format=%(refname:short)%1f%(objectname:short)"
                       "%1f%(contents:subject)%1f%(committerdate:relative)",
                       "refs/heads"], repo)
    for line in (out.splitlines() if ok else []):
        p = line.split(US)
        if len(p) >= 4 and p[0].strip():
            metas[p[0]] = {"sha": p[1], "subject": p[2], "ago": p[3]}
    locals_ = list(metas)
    ok, out, _ = _git(["status", "--porcelain"], repo)
    n_dirty = len([l for l in out.splitlines() if l.strip()]) if ok else 0

    has_main = _has_ref("main", repo)
    has_om = _has_ref("origin/main", repo)

    # ── worktrees aparte (treehouse): git es la verdad de QUÉ hay; el
    #    registry de dueños dice QUIÉN lo trabaja ──
    owners = _owners()
    wts, wt_by_branch = [], {}
    ok, out, _ = _git(["worktree", "list", "--porcelain"], repo)
    top = os.path.realpath(repo)
    cur_path = None
    for line in (out.splitlines() if ok else []):
        if line.startswith("worktree "):
            cur_path = line[len("worktree "):].strip()
        elif line.startswith("branch ") and cur_path:
            ref = line[len("branch "):].strip()
            br = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") \
                else ref
            if os.path.realpath(cur_path) != top:    # salta el checkout ppal
                o = owners.get(br) if isinstance(owners.get(br), dict) else {}
                row = {"path": cur_path, "branch": br,
                       "agent": (o.get("agent") or "?"),
                       "since": o.get("since") or "",
                       "pool": bool(o.get("pool")),
                       "clean": _wt_clean(cur_path)}
                wts.append(row)
                wt_by_branch[br] = row
            cur_path = None

    def _rama(name, ref=None, remote_only=False):
        ref = ref or name
        m = metas.get(name) or _meta(ref, repo) or {}
        if name == "main" and has_om:
            base = "origin/main"
            ahead, behind = _ahead_behind(base, "main", repo)
        elif name != "main" and has_main:
            base = "main"
            ahead, behind = _ahead_behind(base, ref, repo)
        else:
            ahead = behind = 0
            base = None
        return {"name": name, "ref": ref, "current": name == current,
                "sha": m.get("sha", ""), "subject": m.get("subject", ""),
                "ago": m.get("ago", ""), "ahead": ahead, "behind": behind,
                "base": base, "remote_only": remote_only,
                "wt": wt_by_branch.get(name)}

    tronco, features = [], []
    if has_main:
        tronco.append(_rama("main"))
    # canal stable: la rama local, o la de origin si el socio no la tiene
    # (mismo criterio que el pipeline del dev panel — se VE aunque sea remota)
    if "stable" in locals_:
        tronco.append(_rama("stable"))
    elif _has_ref("origin/stable", repo):
        tronco.append(_rama("stable", "origin/stable", remote_only=True))
    for b in sorted(locals_):
        if b not in ("main", "stable"):
            features.append(_rama(b))

    # sin llamadas extra: main.ahead = sin publicar · stable.behind = por
    # promover (los deltas ya calculados cuentan la historia completa)
    r_main = next((t for t in tronco if t["name"] == "main"), None)
    r_stable = next((t for t in tronco if t["name"] == "stable"), None)
    return {
        "repo": repo, "nombre": os.path.basename(top.rstrip("/\\")),
        "current": current, "dirty": n_dirty > 0, "dirty_count": n_dirty,
        "tronco": tronco, "features": features, "wts": wts,
        "unpushed": (r_main or {}).get("ahead", 0) if has_om else 0,
        "ready": (r_stable or {}).get("behind", 0),
    }


def _diff_resumen(S, rama):
    """Qué CAMBIA la rama vs main (three-dot: solo lo propio, no el avance de
    main) → {files:[(path,+,-)…], n, added, removed} | None. Cacheado por rama
    y por refresh (S["diff"]) — una sola corrida de git por rama navegada."""
    name = rama["name"]
    if name in S["diff"]:
        return S["diff"][name]
    base = "main" if _has_ref("main", S["D"]["repo"]) else (
        "origin/main" if _has_ref("origin/main", S["D"]["repo"]) else "")
    res = None
    if base and name != "main":
        ok, out, _ = _git(["diff", "--numstat",
                           "%s...%s" % (base, rama["ref"])], S["D"]["repo"])
        if ok:
            files, ta, tr = [], 0, 0
            for line in out.splitlines():
                p = line.split("\t")
                if len(p) < 3:
                    continue
                a = int(p[0]) if p[0].isdigit() else 0
                r = int(p[1]) if p[1].isdigit() else 0
                ta, tr = ta + a, tr + r
                files.append(("\t".join(p[2:]), a, r))
            files.sort(key=lambda f: f[1] + f[2], reverse=True)
            res = {"files": files[:_MAX_DIFF_FILES], "n": len(files),
                   "added": ta, "removed": tr}
    S["diff"][name] = res
    return res


# ── acciones (espejo seguro del dev panel) ──────────────────────────────────
def _switch(S, rama):
    """Cambiar de rama con las MISMAS guardas que el dev panel: rama real,
    árbol limpio, no tomada en worktree. Devuelve el mensaje del pie."""
    D = S["D"]
    if rama["remote_only"]:
        return _t("versiones.map.sw.remote_only",
                  "`{b}` solo existe en origin — tráela con git antes de "
                  "usarla", b=rama["name"])
    if rama["current"]:
        return _t("versiones.map.sw.already", "ya estás en {b}", b=rama["name"])
    if rama["wt"]:
        return _t("versiones.map.sw.in_wt",
                  "`{b}` está tomada en un worktree ({a}) — tu checkout no se "
                  "mueve; ábrela con o", b=rama["name"], a=rama["wt"]["agent"])
    ok, status, _ = _git(["status", "--porcelain"], D["repo"])
    if not ok:
        return _t("versiones.map.sw.unsure",
                  "no pude confirmar si el árbol está limpio — no cambio de "
                  "rama")
    dirty_count = len(status.splitlines())
    if dirty_count:
        return (_t("versiones.map.sw.dirty1",
                   "tienes {n} cambio sin commitear — commit o stash antes "
                   "de cambiar de rama", n=dirty_count) if dirty_count == 1
                else _t("versiones.map.sw.dirty",
                        "tienes {n} cambios sin commitear — commit o stash "
                        "antes de cambiar de rama", n=dirty_count))
    ok, _, err = _git(["switch", rama["name"]], D["repo"])
    if not ok:
        return _t("versiones.map.sw.failed", "git switch falló: {e}",
                  e=(err or "?").splitlines()[0][:60])
    _refresh(S)
    return _t("versiones.map.sw.ok", "ahora estás en {b} ✓", b=rama["name"])


def _crear(S, buf):
    """`<slug>` → feat/<slug> · `fix <slug>` → fix/<slug>. Nace de main SIN
    cambiar tu rama ni tocar el árbol (reversible con git branch -d)."""
    D = S["D"]
    txt = (buf or "").strip().lower()
    kind = "feat"
    if txt.startswith("fix "):
        kind, txt = "fix", txt[4:].strip()
    if not txt:
        return _t("versiones.map.new.noname",
                  "cancelado — sin nombre no hay rama")
    if not _SLUG_RE.match(txt):
        return _t("versiones.map.new.invalid",
                  "nombre inválido: kebab-case (minúsculas, dígitos, guiones "
                  "— ej. menu-de-archivo)")
    branch = "%s/%s" % (kind, txt)
    if _has_ref("refs/heads/%s" % branch, D["repo"]):
        return _t("versiones.map.new.exists", "la rama `{b}` ya existe",
                  b=branch)
    base = "main" if _has_ref("main", D["repo"]) else (
        "origin/main" if _has_ref("origin/main", D["repo"]) else "")
    if not base:
        return _t("versiones.map.new.nomain",
                  "no hay main (ni origin/main) desde donde crear la rama")
    ok, _, err = _git(["branch", branch, base], D["repo"])
    if not ok:
        return _t("versiones.map.new.failed", "git branch falló: {e}",
                  e=(err or "?").splitlines()[0][:60])
    _refresh(S)
    # dejar el cursor sobre la rama recién nacida (se ve lo que se hizo)
    for i, (kind_, obj) in enumerate(_items(S["D"])):
        if kind_ == "rama" and obj["name"] == branch:
            S["si"] = i
            break
    return _t("versiones.map.new.ok",
              "rama {b} creada desde {base} ✓ (Enter para cambiarte a ella)",
              b=branch, base=base)


def _liberar(S, wt):
    """Remueve un worktree LIMPIO (git worktree remove, jamás --force) +
    limpia su entrada del registry. Las guardas corren ANTES de confirmar."""
    D = S["D"]
    live = dict(wt, clean=_wt_clean(wt["path"]))
    guard = _guard_liberar(live)
    if guard:
        return guard
    ok, _, err = _git(["worktree", "remove", wt["path"]], D["repo"])
    if not ok:
        return _t("versiones.map.rel.failed", "no pude liberarlo: {e}",
                  e=(err or "?").splitlines()[0][:60])
    _git(["worktree", "prune"], D["repo"])
    _owner_clear(wt["branch"])
    _refresh(S)
    return _t("versiones.map.rel.ok",
              "worktree de {b} liberado ✓ — la rama sigue viva",
              b=wt["branch"])


def _guard_liberar(wt):
    """Por qué NO se puede liberar este worktree (None = adelante). La regla
    de oro del reaper: jamás remover trabajo sin commitear ni estado dudoso."""
    if wt["pool"]:
        return _t("versiones.map.rel.pool",
                  "es del pool tibio — devuélvelo desde el dev panel o con "
                  "`workspace worktree`")
    if wt["clean"] is None:
        return _t("versiones.map.rel.unsure",
                  "no pude confirmar si está limpio — no lo toco")
    if wt["clean"] is False:
        return _t("versiones.map.rel.dirty",
                  "tiene cambios sin commitear — no se libera (no perder "
                  "trabajo)")
    return None


def _revelar(path):
    """Abre la carpeta en el explorador del SO. Falla-suave."""
    if not path or not os.path.isdir(path):
        return _t("versiones.map.dir.gone", "la carpeta ya no existe")
    try:
        cmd = (["open", path] if sys.platform == "darwin" else
               ["explorer", path] if os.name == "nt" else ["xdg-open", path])
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return _t("versiones.map.dir.opened", "carpeta abierta: {p}", p=path)
    except Exception as e:
        return _t("versiones.map.dir.fail", "no pude abrir la carpeta: {e}",
                  e=e)


def _refresh(S):
    if S.get("panel"):
        import git_panel
        return git_panel.reload(S, sys.modules[__name__])
    S["D"] = snapshot()
    S["diff"] = {}
    S["recent"] = {}
    n = len(_items(S["D"]))
    S["si"] = min(S["si"], max(0, n - 1))


# ── navegación / cuerpos de las cajas ───────────────────────────────────────
def _items(D):
    """El orden VISUAL que recorre ↑↓: tronco → features → treehouse."""
    if D.get("error"):
        return []
    its = [("rama", b) for b in D["tronco"]]
    its += [("rama", b) for b in D["features"]]
    its += [("wt", w) for w in D["wts"]]
    return its


def _K():
    """La paleta del TEMA activo, igual que el hub (fallback: no truena)."""
    try:
        import tuitheme
        return HL.cols(tuitheme.palette())
    except Exception:
        return HL.cols(type("P", (), {"GLYPHS": {}})())


def _size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 100, 34


def _wrap(txt, w):
    pal, ln, out = str(txt).split(), "", []
    for p in pal:
        if len(ln) + len(p) + 1 > w:
            out.append(ln)
            ln = p
        else:
            ln = (ln + " " + p).strip()
    if ln:
        out.append(ln)
    return out or [""]


def _divisor(K, txt, w, tono=-1):
    """`titulo ────` — el encabezado de grupo del lenguaje WORKSPACE."""
    col = (K["WCOL"][tono % len(K["WCOL"])] + K["BO"]) if tono >= 0 \
        else K["DK"]
    regla = K["SEP"] * max(1, w - HL.vis(txt) - 2)
    return HL.clip("%s%s%s %s%s%s" % (col, str(txt), K["R"], K["DK"], regla,
                                      K["R"]), w)


def _delta(K, a, b):
    """`↑3↓5` — mismo lenguaje que el widget de rama del hub: ↑ acento,
    ↓ acento medio; al día → `=` tenue."""
    if not a and not b:
        return "%s=%s" % (K["DK"], K["R"])
    out = ""
    if a:
        out += "%s↑%d%s" % (K["C"], a, K["R"])
    if b:
        out += "%s↓%d%s" % (K["B2"], b, K["R"])
    return out


def _fila_estado(S, K, w):
    """La línea de contexto bajo el subtítulo: dónde estás parado y qué hay
    pendiente — el equivalente del header de la sección web."""
    D = S["D"]
    if D.get("error"):
        return HL.clip(" %s%s%s" % (K["DK"], D["error"], K["R"]), w - 1)
    limpio = ("%s%s %s%s" % (K["OK"], K["CHECK"],
                             _t("versiones.map.st.clean", "limpio"), K["R"])
              if not D["dirty"]
              else "%s±%s%s" % (K["BAD"],
                                _t("versiones.map.st.dirty",
                                   "{n} sin commitear", n=D["dirty_count"]),
                                K["R"]))
    trozos = ["%s%s %s%s%s" % (K["C"] + K["BO"], K["BRANCH"],
                               D["current"] or "detached", K["R"], ""),
              limpio,
              "%s%s%s" % (K["GREY"], _t("versiones.map.st.branches",
                                         "{n} ramas", n=len(D["tronco"])
                                         + len(D["features"])), K["R"]),
              "%s%s%s" % (K["GREY"],
                          _t("versiones.map.st.tree1", "{n} árbol",
                             n=len(D["wts"])) if len(D["wts"]) == 1
                          else _t("versiones.map.st.trees", "{n} árboles",
                                  n=len(D["wts"])), K["R"])]
    if D["unpushed"]:
        trozos.append("%s↑%s%s" % (K["B"] + K["BO"], _t(
            "versiones.map.st.unpushed", "{n} sin publicar a origin",
            n=D["unpushed"]), K["R"]))
    if D["ready"]:
        trozos.append("%s%s%s" % (K["B2"], _t(
            "versiones.map.st.ready", "{n} por promover a stable",
            n=D["ready"]), K["R"]))
    fila = " " + (" %s·%s " % (K["DK"], K["R"])).join(trozos)
    leg = "%s%s%s" % (K["DK"], _t("versiones.map.st.refresh", "r refresca"),
                      K["R"])
    hueco = (w - 1) - HL.vis(fila) - HL.vis(leg) - 1
    if hueco > 1:
        fila += " " * hueco + leg
    return HL.clip(fila, w - 1)


def _fila_rama(S, K, b, i, iw):
    """Una rama del mapa: cursor · ● actual · nombre · ↑↓ · ⌂dueño · hace."""
    sel = (i == S["si"])
    cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
    mark = ("%s●%s" % (K["C"] + K["BO"], K["R"]) if b["current"]
            else "%s·%s" % (K["DK"], K["R"]))
    nw = max(12, min(22, iw - 18))
    nombre = b["name"] + (" (origin)" if b["remote_only"] else "")
    ncol = (K["WH"] + K["BO"]) if sel else (
        (K["B"] + K["BO"]) if b["current"] else K["GREY"])
    delta = _delta(K, b["ahead"], b["behind"])
    extra = ""
    if b["wt"]:
        ag = b["wt"]["agent"]
        extra = " %s⌂%s%s" % (K["B2"], "" if ag == "?" else ag, K["R"])
    elif b["current"] and S["D"]["dirty"]:
        extra = " %s±%d%s" % (K["BAD"], S["D"]["dirty_count"], K["R"])
    ago = "%s%s%s" % (K["DK"], ago_text(b["ago"]), K["R"]) if b["ago"] else ""
    ln = " %s %s %s%s%s %s%s" % (cur, mark, ncol, HL.pad(nombre, nw), K["R"],
                                 HL.pad(delta, 7), extra)
    hueco = iw - HL.vis(ln) - HL.vis(ago)
    if hueco > 1 and ago:
        ln += " " * hueco + ago
    return HL.clip(ln, iw)


def _fila_wt(S, K, wt, i, iw):
    """Un árbol del treehouse: cursor · ⌂ · carpeta · rama · dueño · estado."""
    sel = (i == S["si"])
    cur = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if sel else " "
    nom = os.path.basename(wt["path"].rstrip("/\\"))
    nw = max(12, min(20, iw - 20))
    ncol = (K["WH"] + K["BO"]) if sel else K["GREY"]
    est = ("%s%s%s" % (K["OK"], K["CHECK"], K["R"]) if wt["clean"] is True
           else "%s±%s%s" % (K["BAD"], _t("versiones.map.wt.dirty", "sucio"),
                            K["R"]) if wt["clean"] is False
           else "%s?%s" % (K["DK"], K["R"]))
    dueno = "%s%s%s" % (K["B2"], "—" if wt["agent"] == "?" else wt["agent"],
                        K["R"])
    rama = "%s%s%s" % (K["DK"], wt["branch"], K["R"])
    ln = " %s %s⌂%s %s%s%s %s %s" % (cur, K["B2"], K["R"],
                                     ncol, HL.pad(nom, nw), K["R"], est,
                                     dueno)
    hueco = iw - HL.vis(ln) - HL.vis(rama)
    if hueco > 1:
        ln += " " * hueco + rama
    return HL.clip(ln, iw)


def _ventana(K, lineas, marca, ih, iw):
    """Si el mapa no cabe en `ih` filas, una VENTANA con el cursor siempre
    visible y bordes honestos (`↑ n más arriba` / `↓ n más abajo`) — un repo
    con 20 ramas no puede comerse el pie ni esconder la selección."""
    n = len(lineas)
    if n <= ih or ih < 3:
        return lineas[:max(1, ih)] if n > ih else lineas
    start = max(0, min(marca - ih // 2, n - ih))
    if start > 0 and marca <= start:           # el cursor nunca ES el borde
        start = max(0, marca - 1)
    end = min(n, start + ih)
    start = max(0, end - ih)
    if end < n and marca >= end - 1:
        end = min(n, marca + 2)
        start = max(0, end - ih)
    out = list(lineas[start:end])
    if start > 0:
        out[0] = HL.clip(" %s↑ %s%s" % (K["DK"], _t(
            "versiones.map.more_up", "{n} más arriba", n=start), K["R"]), iw)
    if end < n:
        out[-1] = HL.clip(" %s↓ %s%s" % (K["DK"], _t(
            "versiones.map.more_down", "{n} más abajo", n=n - end), K["R"]), iw)
    return out


def _cuerpo_mapa(S, K, iw):
    """Caja izquierda: tronco → features → treehouse, con sus divisores.
    Devuelve (líneas, nº de línea de la fila seleccionada) para la ventana."""
    D = S["D"]
    out, i, marca = [], 0, 0
    out.append(_divisor(K, _t("versiones.map.g.trunk",
                              "principal · main / stable"), iw, tono=0))
    for b in D["tronco"]:
        if i == S["si"]:
            marca = len(out)
        out.append(_fila_rama(S, K, b, i, iw))
        i += 1
    if not D["tronco"]:
        out.append(HL.clip(" %s%s%s" % (K["DK"], _t(
            "versiones.map.g.nomain", "sin main — repo raro"), K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("versiones.map.g.dev", "en desarrollo"), iw,
                        tono=2))
    for b in D["features"]:
        if i == S["si"]:
            marca = len(out)
        out.append(_fila_rama(S, K, b, i, iw))
        i += 1
    if not D["features"]:
        out.append(HL.clip(" %s%s%s" % (K["DIM"], _t(
            "versiones.map.g.nofeat", "ninguna — n crea una desde main"),
            K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("versiones.map.g.wts", "carpetas separadas"),
                        iw, tono=4))
    for wt in D["wts"]:
        if i == S["si"]:
            marca = len(out)
        out.append(_fila_wt(S, K, wt, i, iw))
        i += 1
    if not D["wts"]:
        out.append(HL.clip(" %s%s%s" % (K["DIM"], _t(
            "versiones.map.g.nowts", "ninguno — cada agente trabaja su rama "
            "en un árbol aparte"), K["R"]), iw))
    return out, marca


def _cuerpo_nueva(S, K, iw):
    """Caja derecha en modo ALTA: el campo + la transparencia de qué pasará."""
    out = [HL.clip(" %s%s%s" % (K["DIM"], _t("versiones.map.n.head",
                                         "nueva rama — nace de main"),
                                K["R"]), iw),
           HL.clip(" %s%s%s %s%s%s█%s" % (K["C"] + K["BO"], K["PTR"], K["R"],
                                          K["WH"], S["buf"],
                                          K["C"] + K["BO"], K["R"]), iw),
           ""]
    for ln in (_t("versiones.map.n.l1",
                  "kebab-case → feat/<nombre> · «fix <nombre>» → fix/…"),
               _t("versiones.map.n.l2",
                  "no cambia tu rama actual ni toca tus archivos"),
               _t("versiones.map.n.l3", "reversible: git branch -d la borra"),
               _t("versiones.map.n.l4", "Enter crea · Esc cancela")):
        for sub in _wrap(ln, max(8, iw - 4)):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  sub, K["R"]), iw))
    return out


def _det_rama(S, K, b, iw, full=2):
    """DETALLE de una rama: su delta en palabras, qué cambia, quién la tiene,
    commits recientes y qué hace cada tecla. `full` cede adornos: 2 = todo ·
    1 = sin archivos del diff · 0 = solo lo esencial."""
    out = []
    # último commit — lo primero que se quiere ver
    if b["sha"]:
        out.append(HL.clip(" %s%s%s %s%s%s" % (K["B"] + K["BO"], b["sha"],
                                               K["R"], K["WH"],
                                               _wrap(b["subject"],
                                                     max(8, iw - 12))[0],
                                               K["R"]), iw))
        out.append(HL.clip("   %s%s%s" % (K["DK"], ago_text(b["ago"]), K["R"]), iw))
    out.append("")
    # el delta EN PALABRAS (transparencia: nada de ↑↓ crípticos)
    base = b["base"] or "main"
    out.append(_divisor(K, "vs %s" % base, iw, tono=1))
    if b["name"] == "main":
        out.append(HL.clip(" %s↑%s %s%s%s" % (
            K["C"], K["R"], K["GREY"],
            _t("versiones.map.d.unpushed", "{n} commits sin publicar a "
               "origin", n=b["ahead"]) if b["ahead"]
            else _t("versiones.map.d.pushed", "todo publicado en origin"),
            K["R"]), iw))
        if b["behind"]:
            out.append(HL.clip(" %s↓%s %s%s%s" % (
                K["B2"], K["R"], K["GREY"],
                _t("versiones.map.d.behind_origin",
                   "origin trae {n} que no tienes — haz pull", n=b["behind"]),
                K["R"]), iw))
        if S["D"]["ready"]:
            out.append(HL.clip(" %s◦%s %s%s%s" % (
                K["B2"], K["R"], K["GREY"],
                _t("versiones.map.d.ready", "{n} listos para promover a "
                   "stable", n=S["D"]["ready"]), K["R"]), iw))
    else:
        out.append(HL.clip(" %s↑%s %s%s%s" % (
            K["C"], K["R"], K["GREY"],
            _t("versiones.map.d.own", "{n} commits propios por integrar",
               n=b["ahead"]) if b["ahead"]
            else _t("versiones.map.d.nothing", "no añade nada sobre {base}",
                    base=base), K["R"]), iw))
        out.append(HL.clip(" %s↓%s %s%s%s" % (
            K["B2"], K["R"], K["GREY"],
            _t("versiones.map.d.behind", "{n} detrás de {base}",
               n=b["behind"], base=base) if b["behind"]
            else _t("versiones.map.d.uptodate", "al día con {base}",
                    base=base), K["R"]), iw))
    # qué CAMBIA (solo features; main no se compara contra sí mismo)
    if b["name"] != "main" and not b["remote_only"]:
        d = _diff_resumen(S, b)
        if d and d["n"]:
            out.append("")
            out.append(_divisor(K, _t("versiones.map.d.changes",
                                      "qué cambia"), iw, tono=3))
            out.append(HL.clip(" %s%s · %s+%d%s %s−%d%s"
                               % (K["WH"],
                                  _t("versiones.map.d.file1", "{n} archivo",
                                     n=d["n"]) if d["n"] == 1 else
                                  _t("versiones.map.d.files", "{n} archivos",
                                     n=d["n"]), K["OK"],
                                  d["added"], K["R"], K["BAD"], d["removed"],
                                  K["R"]), iw))
            if full >= 2:
                for path, a, r in d["files"]:
                    out.append(HL.clip("  %s%s%s %s+%d%s %s−%d%s"
                                       % (K["GREY"],
                                          HL.pad(path, max(8, iw - 16)),
                                          K["R"], K["OK"], a, K["R"],
                                          K["BAD"], r, K["R"]), iw))
                if d["n"] > len(d["files"]):
                    out.append(HL.clip("  %s… %s%s" % (
                        K["DK"], _t("versiones.map.d.and_more", "y {n} más",
                                    n=d["n"] - len(d["files"])), K["R"]), iw))
    # quién la tiene
    out.append("")
    out.append(_divisor(K, _t("versiones.map.d.who", "quién"), iw, tono=4))
    if b["wt"]:
        quien = (_t("versiones.map.d.of", "de {a}", a=b["wt"]["agent"])
                 if b["wt"]["agent"] != "?"
                 else _t("versiones.map.d.noowner", "sin dueño registrado"))
        out.append(HL.clip(" %s⌂%s %s%s %s%s%s%s — %s" % (
            K["B2"], K["R"], K["GREY"],
            _t("versiones.map.d.in_wt", "en un worktree"), K["B"] + K["BO"],
            quien, K["R"], K["GREY"],
            _t("versiones.map.d.or_open", "o abre su carpeta")) + K["R"], iw))
    elif b["remote_only"]:
        out.append(HL.clip(" %s%s%s" % (K["DK"], _t(
            "versiones.map.d.remote_only",
            "solo en origin — nadie la tiene local"), K["R"]), iw))
    else:
        out.append(HL.clip(" %s%s%s" % (K["DK"], _t(
            "versiones.map.d.free", "libre — nadie la trabaja ahora"),
            K["R"]), iw))
    if full < 1:
        return out
    # commits recientes
    recent = S.setdefault("recent", {})
    if b["ref"] not in recent:
        recent[b["ref"]] = _recientes(b["ref"], 4, S["D"]["repo"])
    rec = recent[b["ref"]]
    if rec:
        out.append("")
        out.append(_divisor(K, _t("versiones.map.d.recent",
                                  "commits recientes"), iw, tono=5))
        for c in rec:
            out.append(HL.clip(" %s%s%s %s%s%s %s%s%s"
                               % (K["B2"], c["sha"], K["R"], K["GREY"],
                                  _wrap(c["subject"],
                                        max(8, iw - 20))[0], K["R"],
                                  K["DK"], ago_text(c["ago"]), K["R"]), iw))
    if full < 2:
        return out
    # qué hace cada tecla SOBRE ESTA rama (se dice antes de tocar)
    out.append("")
    out.append(_divisor(K, _t("versiones.map.d.actions", "acciones"), iw))
    acc = []
    if b["current"]:
        acc.append(_t("versiones.map.a.here",
                      "ya estás aquí — ↑↓ recorre las demás"))
    elif b["wt"]:
        acc.append(_t("versiones.map.a.wt",
                      "Enter no mueve tu checkout (vive en un worktree)"))
        acc.append(_t("versiones.map.a.open", "o abre su carpeta"))
    elif b["remote_only"]:
        acc.append(_t("versiones.map.a.ro",
                      "solo lectura: existe en origin, no local"))
    else:
        acc.append(_t("versiones.map.a.switch",
                      "Enter te cambia a esta rama (si tu árbol está limpio)"))
    acc.append(_t("versiones.map.a.new", "n crea una rama nueva desde main"))
    for ln in acc:
        for sub in _wrap(ln, max(8, iw - 4)):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  sub, K["R"]), iw))
    return out


def _det_wt(S, K, wt, iw, full=2):
    """DETALLE de un worktree: qué es, de quién, su estado y qué se puede
    hacer con él — con la guarda de liberación EXPLICADA antes de intentarlo."""
    out = [HL.clip(" %s⌂ %s%s" % (K["B"] + K["BO"],
                                  os.path.basename(wt["path"].rstrip("/\\")),
                                  K["R"]), iw), ""]
    est = (_t("versiones.map.w.clean", "limpio — sin cambios sin commitear")
           if wt["clean"] is True else
           _t("versiones.map.w.dirty", "con cambios sin commitear")
           if wt["clean"] is False else
           _t("versiones.map.w.unknown", "estado indeterminado"))
    ecol = K["OK"] if wt["clean"] is True else (
        K["BAD"] if wt["clean"] is False else K["DK"])
    filas = [(_t("versiones.map.w.branch", "rama"), wt["branch"], K["WH"]),
             (_t("versiones.map.w.owner", "dueño"),
              (_t("versiones.map.w.unreg", "sin registrar")
               if wt["agent"] == "?" else wt["agent"])
              + ((" — " + _t("versiones.map.w.since", "desde {d}",
                             d=wt["since"][:10]))
                 if wt["since"] else ""), K["GREY"]),
             (_t("versiones.map.w.state", "estado"), est, ecol),
             ("pool", _t("versiones.map.w.pool_warm",
                         "tibio (se devuelve, no se borra)") if wt["pool"]
              else _t("versiones.map.w.pool_no", "no — árbol normal"),
              K["GREY"])]
    for et, val, col in filas:
        out.append(HL.clip(" %s%s%s %s%s%s" % (K["DK"], HL.pad(et, 7),
                                               K["R"], col, val, K["R"]), iw))
    out.append("")
    out.append(_divisor(K, _t("versiones.map.w.path", "ruta"), iw, tono=3))
    ruta = wt["path"].replace(os.path.expanduser("~"), "~")
    paso = max(8, iw - 2)            # sin espacios no hay wrap: va en trozos
    for ln in [ruta[i:i + paso] for i in range(0, len(ruta), paso)][:2]:
        out.append(HL.clip(" %s%s%s" % (K["GREY"], ln, K["R"]), iw))
    if full < 1:
        return out
    out.append("")
    out.append(_divisor(K, _t("versiones.map.d.actions", "acciones"), iw))
    guard = _guard_liberar(wt)
    acc = [_t("versiones.map.w.a.open",
              "o / Enter abre la carpeta en el explorador")]
    if guard:
        acc.append(_t("versiones.map.w.a.noapply", "x no aplica: {g}", g=guard))
    else:
        acc.append(_t("versiones.map.w.a.release",
                      "x lo libera (la rama sigue viva; pide confirmación)"))
    for ln in acc:
        for sub in _wrap(ln, max(8, iw - 4)):
            out.append(HL.clip(" %s·%s %s%s%s" % (K["DK"], K["R"], K["DIM"],
                                                  sub, K["R"]), iw))
    if full >= 2:
        out.append("")
        for ln in _wrap(_t("versiones.map.w.note",
                           "liberar un worktree NUNCA borra commits: solo "
                           "quita la copia de trabajo y des-fija la rama."),
                        max(8, iw - 4)):
            out.append(HL.clip(" %s%s%s" % (K["DIM"], ln, K["R"]), iw))
    return out


def _map_render(S, w, h):
    K = _K()
    D = S["D"]
    L = [""]
    # mismo wordmark del hub (centrado) — cambiar de vista, no de app
    bt = HL.big_title(K, w, h, indent=" ", compact=(h < 30), center=True, word=HL.section_word("versiones"))
    L += bt
    if len(bt) > 1:
        L += HL.title_reflection(K, w, indent=" ", center=True, word=HL.section_word("versiones"))
    sub = _t("versiones.map.sub",
             "ramas — el git del harness: tronco · features · treehouse")
    L.append(" " * max(0, ((w - 1) - HL.vis(sub)) // 2)
             + "%s%s%s" % (K["DIM"], sub, K["R"]))
    L.append("%s%s%s%s%s" % (K["B2"], K["BOX"][5] * 3, K["DK"],
                             K["BOX"][5] * max(1, w - 5), K["R"]))
    L.append("")
    L.append(_fila_estado(S, K, w))
    L.append("")
    top = len(L)
    its = _items(D)
    apilado = w < 100
    lw = (w - 1) if apilado else max(36, min(52, (w - 6) * 48 // 100))
    rw = (w - 1) if apilado else (w - 1) - lw - 3
    avail = max(8, (h - 1) - top - 3)

    if D.get("error"):
        ew = (w - 1) - 5                         # ancho interior de la caja
        cuerpo = [HL.clip(" %s%s%s" % (K["BAD"], D["error"], K["R"]), ew),
                  "",
                  HL.clip(" %s%s%s" % (K["DK"], _t(
                      "versiones.map.e.path", "ruta: {p}",
                      p=D.get("repo", "?")), K["R"]), ew),
                  HL.clip(" %s%s%s" % (K["DIM"], _t(
                      "versiones.map.e.hint", "q vuelve al menú · r reintenta"),
                      K["R"]), ew)]
        for ln in HL.full_box(_t("versiones.map.box.branches", "RAMAS"), cuerpo, K, (w - 1) - 1,
                              min(avail - 2, len(cuerpo) + 2), True,
                              border=K["C"]):
            L.append(HL.clip(" " + ln, w - 1))
    else:
        sel = its[S["si"]] if its else None
        bi, marca = _cuerpo_mapa(S, K, lw - 4)
        # degradación honesta: primero los archivos del diff y las teclas,
        # luego commits recientes — el mapa y el delta esencial jamás
        _det = _t("versiones.map.box.detail", "DETALLE")
        bd, t_der = [], _det
        for full in (2, 1, 0):
            if S["modo"] == "new":
                bd, t_der = _cuerpo_nueva(S, K, rw - 4), _t(
                    "versiones.map.box.new", "NUEVA RAMA")
            elif sel and sel[0] == "rama":
                bd = _det_rama(S, K, sel[1], rw - 4, full=full)
                t_der = "%s · %s" % (_det, sel[1]["name"])
            elif sel and sel[0] == "wt":
                bd = _det_wt(S, K, sel[1], rw - 4, full=full)
                t_der = "%s · ⌂ %s" % (_det, os.path.basename(
                    sel[1]["path"].rstrip("/\\")))
            else:
                bd = [HL.clip(" %s%s%s" % (K["DK"], _t(
                    "versiones.map.empty", "nada que ver — repo vacío"),
                    K["R"]), rw - 4)]
            need = (len(bi) + len(bd) + 4) if apilado \
                else (max(len(bi), len(bd)) + 2)
            if need <= avail or S["modo"] == "new":
                break
        t_izq = "%s · %s" % (_t("versiones.map.box.branches", "RAMAS"),
                             D["nombre"])
        if apilado:                              # ── angosto: APILADO ──
            # presupuesto EXACTO (el pie nunca se come): el mapa recibe ~55%
            # del alto con ventana; el detalle lo que quede (mínimo 3 filas)
            ih_i = min(len(bi), max(5, (avail - 4) * 55 // 100))
            ih_d = max(3, min(len(bd), avail - 4 - ih_i))
            bi_v = _ventana(K, bi, marca, ih_i, lw - 4)
            for ln in HL.full_box(t_izq, bi_v, K, lw - 1, ih_i, True,
                                  border=K["C"]):
                L.append(HL.clip(" " + ln, w - 1))
            for ln in HL.full_box(t_der, bd, K, rw - 1, ih_d, False,
                                  border=K["B2"], label=K["B"] + K["BO"]):
                L.append(HL.clip(" " + ln, w - 1))
        else:                                    # ── lado a lado ──
            ch = min(avail, max(len(bi), len(bd)) + 2)
            bi_v = _ventana(K, bi, marca, ch - 2, lw - 4)
            izq = HL.full_box(t_izq, bi_v, K, lw, ch - 2, True,
                              border=K["C"])
            der = HL.full_box(t_der, bd, K, rw, ch - 2, False,
                              border=K["B2"], label=K["B"] + K["BO"])
            for i in range(ch):
                L.append(HL.clip(" " + HL.pad(izq[i] if i < len(izq) else "",
                                              lw) + "  "
                                 + (der[i] if i < len(der) else ""), w - 1))
    L.append("")
    if S["modo"] == "confirm" and S.get("pend"):
        L.append(" %s⚠ %s%s" % (K["BAD"] + K["BO"], _t(
            "versiones.map.confirm", "liberar el árbol de {b} — Enter "
            "confirma · Esc cancela", b=S["pend"]["branch"]), K["R"]))
    elif S.get("msg"):
        L.append(" %s%s%s" % (K["B2"], S["msg"], K["R"]))
    else:
        L.append("")
    hint = (_t("versiones.map.h.new",
               "escribe el nombre · Enter crea · Esc cancela")
            if S["modo"] == "new" else
            _t("versiones.map.h.nav",
               "↑↓ elige · Enter/c cambia · n nueva · o carpeta · x libera · "
               "r refresca · q vuelve al menú"))
    if w < 90 and S["modo"] != "new":
        hint = _t("versiones.map.h.nav_short",
                  "↑↓ elige · Enter cambia · n nueva · o abre · x libera · r · "
                  "q vuelve")
    L.append(" %s%s%s" % (K["DK"], hint, K["R"]))
    # ALTURA ESTABLE: siempre h-1 líneas exactas (pie anclado abajo) — así el
    # redraw jamás deja líneas rancias de un frame más alto, y la pantalla no
    # salta al mover la selección (el detalle varía; el bloque no).
    falta = (h - 1) - len(L)
    if falta > 0:
        L[-2:-2] = [""] * falta
    return [HL.clip(x, w - 1) for x in L[:h - 1]]


# ── acciones de teclado ─────────────────────────────────────────────────────
def _map_action(S, key):
    """False = salir. Las acciones re-leen git y refrescan; navegar no."""
    S["msg"] = ""
    its = _items(S["D"])
    sel = its[S["si"]] if its and S["si"] < len(its) else None

    if S["modo"] == "new":                       # ── capturando el nombre ──
        if key == "\x1b":
            S["modo"], S["buf"], S["msg"] = "nav", "", _t(
                "versiones.map.m.cancel", "cancelado")
        elif key in ("\r", "\n"):
            buf = S["buf"]
            S["modo"], S["buf"] = "nav", ""
            S["msg"] = _crear(S, buf)
        elif key in ("\x7f", "\b", "\x08"):
            S["buf"] = S["buf"][:-1]
        elif key and len(key) == 1 and key.isprintable() \
                and len(S["buf"]) < 48:
            S["buf"] += key
        return True

    if S["modo"] == "confirm":                   # ── confirmación de x ──
        if key in ("\r", "\n"):
            wt = S.get("pend")
            S["modo"], S["pend"] = "nav", None
            S["msg"] = _liberar(S, wt) if wt else _t(
                "versiones.map.m.nothing_rel", "nada que liberar")
        elif key not in ("", None):
            S["modo"], S["pend"] = "nav", None
            S["msg"] = _t("versiones.map.m.rel_cancel",
                          "cancelado — el worktree queda como estaba")
        return True

    if key in ("q", "Q", "\x1b", "\x03"):
        return False
    if key == "up":
        S["si"] = (S["si"] - 1) % max(1, len(its))
    elif key in ("down", "tab"):
        S["si"] = (S["si"] + 1) % max(1, len(its))
    elif key in ("r", "R"):
        _refresh(S)
        S["msg"] = _t("versiones.map.m.reread", "estado releído de git ✓")
    elif key in ("n", "N"):
        S["modo"], S["buf"] = "new", ""
    elif key in ("\r", "\n", "c", "C"):
        if sel and sel[0] == "rama":
            S["msg"] = _switch(S, sel[1])
        elif sel and sel[0] == "wt":
            S["msg"] = _revelar(sel[1]["path"])
        else:
            S["msg"] = _t("versiones.map.m.nosel", "nada seleccionado")
    elif key in ("o", "O"):
        if sel and sel[0] == "wt":
            S["msg"] = _revelar(sel[1]["path"])
        elif sel and sel[0] == "rama" and sel[1]["wt"]:
            S["msg"] = _revelar(sel[1]["wt"]["path"])
        else:
            S["msg"] = _t("versiones.map.m.nowt",
                          "esta rama no tiene worktree — no hay carpeta "
                          "aparte")
    elif key in ("x", "X"):
        wt = (sel[1] if sel and sel[0] == "wt" else
              (sel[1]["wt"] if sel and sel[0] == "rama" else None))
        if not wt:
            S["msg"] = _t("versiones.map.m.x_nowt",
                          "x libera worktrees — esto no tiene uno")
        else:
            guard = _guard_liberar(wt)
            if guard:
                S["msg"] = guard
            else:
                S["modo"], S["pend"] = "confirm", wt
    return True


def render(S, w, h):
    import git_panel
    return git_panel.render(S, w, h, sys.modules[__name__], _map_render)


def _accion(S, key):
    import git_panel
    answer = git_panel.handle(S, key, sys.modules[__name__])
    if answer is not None:
        return answer
    before = S.get("si")
    result = _map_action(S, key)
    if S.get("si") != before:
        # Navegar el mapa NO toca git (cero subprocess por keypress): solo
        # suelta la versión elegida; las vistas que dependen de la selección
        # se sincronizan al entrar (git_panel.sync, lazy + memoizada).
        S["target"] = ""
    return result


# ── drivers (mismo patrón que tono_tui / calendario_tui) ────────────────────
import responsive_ui as _responsive
render = _responsive.renderer(render, 'RAMAS')
_accion = _responsive.action(_accion)

def _draw(tout, S, first=False):
    import git_panel
    if S.get("panel"):
        git_panel.poll(S, sys.modules[__name__])
    w, h = _size()
    try:
        _responsive.paint(tout, render(S, w, h), first=first)
    except Exception:
        pass


def _run_unix(S):
    import codecs
    import select
    import termios
    import tty
    try:
        fd = os.open("/dev/tty", os.O_RDWR)
        tout = open("/dev/tty", "w")
    except Exception:
        return _listado()
    old = termios.tcgetattr(fd)
    decoder = codecs.getincrementaldecoder('utf-8')('replace')
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h")
        _draw(tout, S, first=True)
        while True:
            if not select.select([fd], [], [], 0.5)[0]:
                _draw(tout, S)
                continue
            raw = os.read(fd, 1)
            if not raw:
                break
            ch = decoder.decode(raw)
            if not ch:
                continue
            key = ch
            if ch == "\x1b":
                if select.select([fd], [], [], 0.05)[0]:
                    seq = os.read(fd, 2).decode("utf-8", "replace")
                    key = {"[A": "up", "[B": "down", "[C": "down",
                           "[D": "up"}.get(seq, "\x1b")
                else:
                    key = "\x1b"
            elif ch == "\t":
                key = "tab"
            if not _accion(S, key):
                break
            _draw(tout, S)
    finally:
        try:
            tout.write("\033[?1049l")
            tout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.close(fd)
        except Exception:
            pass
    return 0


def _run_windows(S):
    import msvcrt
    tout = sys.stdout
    tout.write("\033[?1049h")
    _draw(tout, S, first=True)
    try:
        while True:
            if not msvcrt.kbhit():
                _draw(tout, S)
                time.sleep(0.1)
                continue
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                a = msvcrt.getwch()
                key = {"H": "up", "P": "down", "M": "down",
                       "K": "up"}.get(a, "")
            elif ch == "\t":
                key = "tab"
            else:
                key = ch
            if not key:
                continue
            if not _accion(S, key):
                break
            _draw(tout, S)
    finally:
        try:
            tout.write("\033[?1049l")
            tout.flush()
        except Exception:
            pass
    return 0


def _listado():
    """Sin terminal interactiva: al menos imprime el estado plano."""
    D = snapshot()
    if D.get("error"):
        print(_t("versiones.map.l.error", "ramas: {e} ({p})", e=D["error"],
                 p=D.get("repo", "?")))
        return 1
    print(_t("versiones.map.l.head", "repo {r} · en {b} · {s}",
             r=D["nombre"], b=D["current"] or "detached",
             s=_t("versiones.map.st.clean", "limpio") if not D["dirty"]
             else "±" + _t("versiones.map.st.dirty", "{n} sin commitear",
                           n=D["dirty_count"])))
    for b in D["tronco"] + D["features"]:
        print(" %s %-24s ↑%d ↓%d  %s  %s%s" % (
            "●" if b["current"] else "·", b["name"], b["ahead"], b["behind"],
            b["sha"], b["ago"],
            ("  ⌂" + b["wt"]["agent"]) if b["wt"] else ""))
    for wt in D["wts"]:
        print(" ⌂ %-24s %s  %s  %s" % (
            os.path.basename(wt["path"].rstrip("/\\")), wt["branch"],
            wt["agent"],
            _t("versiones.map.st.clean", "limpio") if wt["clean"]
            else _t("versiones.map.wt.dirty", "sucio")
            if wt["clean"] is False else "?"))
    return 0


@_theme_screen
def run():
    """Abre la pantalla. Sin tty cae al listado de texto; nunca truena."""
    S = {"D": snapshot(), "diff": {}, "si": 0, "msg": "", "modo": "nav",
         "buf": "", "pend": None}
    try:
        interactivo = sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        interactivo = False
    if not interactivo:
        return _listado()
    import git_panel
    git_panel.init(S, sys.modules[__name__])
    try:
        if os.name == "nt":
            return _run_windows(S)
        return _run_unix(S)
    except Exception as e:
        try:
            sys.stdout.write("\033[?1049l")
        except Exception:
            pass
        print("ramas: %s" % e)
        return _listado()


if __name__ == "__main__":
    sys.exit(run())
