#!/usr/bin/env python3
# ════════════════════════════════════════════════════════════════════════════
#  WORKSPACE — desinstalador per-máquina (espejo de install.py).
#  Quita TODO lo que el instalador dejó en ESTA máquina:
#    · comando `workspace` + launchers por agente (~/.local/bin)  [Win: $PROFILE]
#    · estado per-máquina (~/.claude/workspace/)
#    · tema 'zenith' (~/.claude/themes/zenith.json) + theme=custom:zenith
#    · bloques de ~/.zshrc (PATH + greeter)  [Win: bloques del $PROFILE]
#    · la carpeta del harness (a menos que --keep-folder)
#  NO toca los CEREBROS (carpetas de agentes) ni los transcripts: la separación
#  harness/agente es justo el punto — reinstalas y vuelves a apuntar el agente.
#  (El respaldo local de transcripts dentro del estado también se conserva.)
#
#  Red de seguridad: ANTES de borrar, cada carpeta prueba con sus marcadores que
#  es de Workspace (y que no contiene un cerebro); si una falla, no se borra
#  nada (exit 2). Lista qué se borra y qué se conserva, y respalda el estado
#  per-máquina en un zip (Escritorio) salvo --no-backup.
#
#  Opcional (--limpiar-todo / --clean-all, o la pregunta interactiva): limpia
#  también cerebros y motores — SOLO lo que Workspace escribió en ellos, con
#  respaldo al lado de cada archivo que cambia (ver plan_clean_all).
#
#    python3 uninstall.py [--dry-run] [--keep-folder] [--workspace /ruta/WORKSPACE]
#                         [--yes|-y] [--backup|--no-backup] [--limpiar-todo|--clean-all]
# ════════════════════════════════════════════════════════════════════════════
import os, re, sys, json, shutil, platform
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)

HOME = os.path.expanduser("~")
IS_WIN = platform.system() == "Windows"
DRY = "--dry-run" in sys.argv
KEEP_FOLDER = "--keep-folder" in sys.argv
C, R, B, DIM = "\033[38;5;51m", "\033[0m", "\033[1m", "\033[38;5;67m"
try:    # acento/tenue del TEMA del hub (el mismo de cada pantalla); sin tema, los de arriba
    import tuitheme as _tuitheme
    _TP = _tuitheme.palette()
    C, R, B, DIM = _TP.C, _TP.R, _TP.BO, _TP.DIM
except Exception:
    pass
if IS_WIN:
    os.system("")  # habilita ANSI en Windows 10+


def ok(m):  print(f"  {C}✓{R} {m}")
def info(m): print(f"  {m}")
def dry(m): print(f"  {DIM}[dry-run] {m}{R}")


def _quitar_solo_lectura(func, path, _exc):
    """En Windows los objetos de `.git` son de solo lectura y rmtree no los borra:
    se les quita la marca y se reintenta. Solo borrar se reintenta (en Unix
    rmtree también avisa de os.open/os.scandir, que no se llaman así); lo que siga
    fallando lo dice rm_path."""
    if func not in (os.remove, os.unlink, os.rmdir):
        return
    try:
        os.chmod(path, 0o700)
        func(path)
    except OSError:
        pass


def _rmtree(p):
    if sys.version_info >= (3, 12):
        shutil.rmtree(p, onexc=_quitar_solo_lectura)
    else:
        shutil.rmtree(p, onerror=_quitar_solo_lectura)


def rm_path(p, label):
    if not p or not os.path.exists(p) and not os.path.islink(p):
        return
    if DRY:
        dry(_t("uninstall.x.rm_path.1", "borraría {label}: {p}", label=label, p=p))
        return
    try:
        if os.path.isdir(p) and not os.path.islink(p):
            _rmtree(p)
            if os.path.exists(p):              # verificar, no suponer
                raise OSError(_t("uninstall.x.rm_path.4", "quedaron archivos en uso"))
        else:
            os.remove(p)
        ok(_t("uninstall.x.rm_path.3", "{label} borrado: {p}", label=label, p=p))
    except OSError as e:
        info(_t("uninstall.x.rm_path.2", "{dim}no pude borrar {p} ({e}){r}", dim=DIM, p=p, e=e, r=R))


def workspace_root():
    for i, a in enumerate(sys.argv):
        if a == "--workspace" and i + 1 < len(sys.argv):
            return os.path.abspath(os.path.expanduser(sys.argv[i + 1]))
        if a.startswith("--workspace="):
            return os.path.abspath(os.path.expanduser(a.split("=", 1)[1]))
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(here).upper().startswith("WORKSPACE"):
        return here
    return os.path.join(HOME, "Desktop", "WORKSPACE")


#: Forma EXACTA de los shims `.cmd` de Windows (install.win_cmd_shims):
#:   @echo off
#:   "<python>" "<harness>\front.py" %*              → workspace.cmd
#:   "<python>" "<harness>\dispatch.py" <agente> %*  → <agente>.cmd
#: No llevan la marca WORKSPACE: antes solo se borraban si la ruta del harness
#: la contenía (una carpeta `workspace-personal` no la tiene en mayúsculas).
_CMD_SHIM_RX = re.compile(r'@echo off\r?\n"[^"\r\n]+" "([^"\r\n]+[\\/](?:front|dispatch)\.py)"'
                          r'(?: (?:"[^"\r\n]+"|[^\s"%]+))? %\*(?:\r?\n)?')


def _harness_roots():
    """Raíces del harness que se desinstala: la elegida y la de este archivo."""
    out = []
    for p in (workspace_root(), os.path.dirname(os.path.abspath(__file__))):
        if _norm(p) not in out:
            out.append(_norm(p))
    return out


def _is_cmd_shim(text, roots):
    """¿`text` es un shim .cmd de Workspace? Forma exacta y destino en este
    harness (o en una carpeta que ya no existe: un shim roto de esa forma)."""
    m = _CMD_SHIM_RX.fullmatch(text or "")
    if not m:
        return False
    d = os.path.dirname(m.group(1))
    return _norm(d) in roots or not os.path.isdir(d)


def our_launchers():
    """[(nombre, ruta)] de ~/.local/bin que escribió el instalador, y solo
    esos: los que llevan su marca EXACTA en las primeras líneas
    (install.is_workspace_launcher: `# WORKSPACE · comando …` o la de la
    instalación anterior) y los shims `.cmd` con su forma exacta y destino en
    este harness (_is_cmd_shim). Un script del socio que solo MENCIONA
    «WORKSPACE» (p. ej. $GITHUB_WORKSPACE) no es nuestro. Sin poder leer la
    marca (install ilegible), nada es nuestro."""
    bindir = os.path.join(HOME, ".local", "bin")
    if not os.path.isdir(bindir):
        return []
    try:
        from install import is_workspace_launcher
    except Exception:
        return []
    roots, out = _harness_roots(), []
    for fn in sorted(os.listdir(bindir)):
        p = os.path.join(bindir, fn)
        if os.path.islink(p) or not os.path.isfile(p):
            continue
        if fn.lower().endswith(".cmd"):
            try:
                with open(p, encoding="utf-8", errors="ignore") as fh:
                    ours = _is_cmd_shim(fh.read(4096), roots)
            except OSError:
                ours = False
        else:
            ours = is_workspace_launcher(p)
        if ours:
            out.append((fn, p))
    return out


def remove_launchers_unix():
    """Borra de ~/.local/bin los launchers que el instalador creó
    (our_launchers). Jamás toca otro archivo."""
    for fn, p in our_launchers():
        rm_path(p, f"launcher `{fn}`")


def strip_zshrc():
    """Quita de ~/.zshrc el bloque del PATH y el bloque del greeter (idempotente)."""
    rc = os.path.join(HOME, ".zshrc")
    if not os.path.exists(rc):
        return
    src = open(rc, encoding="utf-8").read()
    lines = src.splitlines()
    out, i, skip_greeter = [], 0, False
    while i < len(lines):
        ln = lines[i]
        if skip_greeter:                                   # dentro del greeter: hasta el `fi`
            if ln.strip() == "fi":
                skip_greeter = False
            i += 1
            continue
        if "WORKSPACE · PATH" in ln:                         # bloque PATH: marca + export
            i += 1
            if i < len(lines) and "export PATH" in lines[i] and ".local/bin" in lines[i]:
                i += 1
            continue
        if "WORKSPACE · menú al abrir terminal" in ln:       # bloque greeter: arranca aquí
            skip_greeter = True
            i += 1
            continue
        out.append(ln)
        i += 1
    new = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).rstrip("\n") + "\n"
    if new == src:
        return
    if DRY:
        dry(_t("uninstall.x.strip_zshrc.1", "limpiaría los bloques de WORKSPACE de {rc}", rc=rc))
        return
    open(rc, "w", encoding="utf-8").write(new)
    ok(_t("uninstall.x.strip_zshrc.2", "~/.zshrc limpiado (PATH + greeter de WORKSPACE)"))


def strip_profile_windows():
    """DEPLOY-6: quita del $PROFILE SOLO los marcadores de WORKSPACE (no toda línea con
    'workspace' — eso borraba líneas del usuario). Quirúrgico, espejo de strip_zshrc."""
    rm_path(os.path.join(HOME, ".claude", "workspace-cmds.ps1"), _t("uninstall.x.ps_cmds", "comandos PowerShell"))
    prof = ""
    try:
        import subprocess
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "$PROFILE"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=10)
        prof = r.stdout.strip()
    except Exception:
        prof = ""
    if not prof or not os.path.exists(prof):
        return
    src = open(prof, encoding="utf-8").read()
    MARK = ("# WORKSPACE-cmds", "workspace-cmds.ps1", "# WORKSPACE-greeter", "WORKSPACE_GREETER")
    kept = [ln for ln in src.splitlines() if not any(m in ln for m in MARK)]
    new = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).rstrip("\n") + "\n"
    if new == src:
        return
    if DRY:
        dry(_t("uninstall.x.strip_profile_windows.1", "limpiaría los marcadores de WORKSPACE de {prof}", prof=prof))
        return
    open(prof, "w", encoding="utf-8").write(new)
    ok(_t("uninstall.x.strip_profile_windows.2", "$PROFILE limpiado (marcadores WORKSPACE): {prof}", prof=prof))


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_json(path, data):
    """Escritura ATÓMICA del settings.json global: tmp en el mismo dir +
    os.replace. Antes era `json.dump(open('w'))` sin cerrar — si el dump fallaba a
    medias dejaba el settings GLOBAL del usuario truncado o vacío."""
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def known_themes():
    """Temas in-app que WORKSPACE pudo instalar en ESTA máquina, DERIVADOS (no
    hardcode): un tema por agente del registry (su tema lleva el nombre del
    agente) más los que el harness trae en themes-cc/. Así el desinstalador no
    nombra agentes ajenos ni fuga marcas de otros clientes."""
    names = set()
    root = workspace_root()
    try:
        reg = _read_json(os.path.join(root, "agents", "registry.json"))
        names.update(a["name"] for a in reg.get("agents", []) if a.get("name"))
    except Exception:
        pass
    try:
        d = os.path.join(root, "themes-cc")
        names.update(f[:-5] for f in os.listdir(d) if f.endswith(".json"))
    except Exception:
        pass
    return tuple(sorted(names))


def our_themes():
    """[(nombre, ruta)] de ~/.claude/themes que quita el desinstalador: los de
    known_themes() (como siempre) y los de los agentes creados o cargados en
    ESTA máquina (agents.local.json) que Workspace generó TAL CUAL
    (theme_render.is_generated: registro + mismo contenido). Uno editado o
    ajeno se deja. Se calcula ANTES de borrar el estado: ahí viven el registro
    de agentes y el de temas (B07, 2026-10-17)."""
    tdir = os.path.join(HOME, ".claude", "themes")
    out = [(n, os.path.join(tdir, "%s.json" % n)) for n in known_themes()]
    try:
        import theme_render as _tr
    except Exception:
        _tr = None
    vistos = {n for n, _p in out}
    agentes = _read_json(os.path.join(_paths.state_dir(HOME), "agents.local.json"))
    for a in (agentes.get("agents") or []) if isinstance(agentes, dict) else []:
        n = str(a.get("name") or "") if isinstance(a, dict) else ""
        if not n or n in vistos or os.sep in n or "/" in n or n.startswith("."):
            continue
        vistos.add(n)
        p = os.path.join(tdir, "%s.json" % n)
        if _tr is not None and _tr.is_generated(p, HOME):
            out.append((n, p))
    return out


def reset_theme(temas=None):
    """Quita los temas in-app que instaló WORKSPACE (our_themes) y, si el
    settings GLOBAL apunta a uno nuestro (installs viejos), lo limpia. DEPLOY-1/SEC-05."""
    temas = our_themes() if temas is None else temas
    known = set(known_themes()) | {n for n, _p in temas}
    for n, p in temas:
        rm_path(p, _t("uninstall.x.theme", "tema {n}", n=n))
    sp = os.path.join(HOME, ".claude", "settings.json")
    s = _read_json(sp)
    th = s.get("theme")
    if isinstance(th, str) and th.startswith("custom:") and th.split(":", 1)[1] in known:
        if DRY:
            dry(_t("uninstall.x.reset_theme.1", "quitaría theme={th} de ~/.claude/settings.json", th=th))
            return
        s.pop("theme", None)
        _write_json(sp, s)
        ok(_t("uninstall.x.reset_theme.2", "theme {th} removido de ~/.claude/settings.json", th=th))


def restore_retention():
    """SEC-05: revierte cleanupPeriodDays al valor que había ANTES del install
    (install lo guardó en ~/.claude/workspace/pre-install.json). DEBE correr antes de
    borrar el estado per-máquina. Si no hay registro, no toca nada (no asume)."""
    pre = _read_json(os.path.join(_paths.state_dir(HOME), "pre-install.json"))
    if "cleanupPeriodDays" not in pre:
        return
    sp = os.path.join(HOME, ".claude", "settings.json")
    s = _read_json(sp)
    if not s:
        return
    prior = pre.get("cleanupPeriodDays")   # None = la clave no existía antes
    if DRY:
        dry(_t("uninstall.x.restore_retention.1", "restauraría cleanupPeriodDays={prior!r} en {sp}", prior=prior, sp=sp))
        return
    if prior is None:
        s.pop("cleanupPeriodDays", None)
    else:
        s["cleanupPeriodDays"] = prior
    _write_json(sp, s)
    ok(_t("uninstall.x.restore_retention.2", "cleanupPeriodDays restaurado ({v})", v=_t("uninstall.x.no_value", "sin valor") if prior is None else prior))


def _is_harness(root):
    """SEC-06: ¿`root` es de verdad un harness WORKSPACE? (no borrar una carpeta ajena
    si --workspace apunta mal)."""
    return all(os.path.isfile(os.path.join(root, f))
               for f in ("front.py", "dispatch.py", "install.py"))


# ── red de seguridad (Tanda Omarchy · acción 7, estilo Try Omarchy
#    uninstall_guard.go): cada carpeta a borrar debe PROBAR que es de Workspace
#    con sus marcadores; si una falla, no se borra NADA. Se ofrece un respaldo
#    del estado per-máquina antes, y se lista qué se borra y qué se conserva.
try:
    import i18n as _i18n
except Exception:
    _i18n = None


def _t(key, es, **kw):
    """Idioma activo con fallback al español inline. Con **kw aplica
    .format (las cadenas viejas sin kw siguen usando .replace("{p}", …))."""
    if _i18n is not None:
        try:
            got = _i18n.t(key, **kw)
            if got != key:
                return got
        except Exception:
            pass
    if kw:
        try:
            return es.format(**kw)
        except Exception:
            return es
    return es


#: Marcadores del estado per-máquina: archivos que SOLO Workspace escribe ahí.
#: Basta uno (una carpeta vacía también vale: no hay nada que perder).
STATE_MARKERS = ("settings.json", "agents.local.json", "onboarded.json", "socio.local",
                 "keybinds.json", "pre-install.json", "doctor-state.json",
                 "paths.local.json", "brains.index.json", "themes.local.json",
                 "personal.json", "tono.json", "usage.json", "sessions-local.json",
                 "last_update_check", "logs", "events", "markers", "themes-cc",
                 "continuity", "transcripts-backup")
#: Lo que se CONSERVA aunque viva dentro del estado (la promesa: los
#: transcripts no se tocan; su respaldo local tampoco).
STATE_KEEP = ("transcripts-backup",)


def _norm(p):
    return os.path.normcase(os.path.realpath(os.path.abspath(p))).rstrip("\\/")


def _inside(child, parent):
    c, p = _norm(child), _norm(parent)
    return c == p or c.startswith(p + os.sep)


def brains():
    """[(nombre, ruta)] de los cerebros registrados en ESTA máquina, leídos del
    estado ANTES de borrarlo (agents.local.json + paths.local.json). Solo para
    protegerlos y listarlos — jamás se abren."""
    sd = _paths.state_dir(HOME)
    out = []
    for a in (_read_json(os.path.join(sd, "agents.local.json")).get("agents") or []):
        if isinstance(a, dict) and a.get("brain"):
            out.append((str(a.get("name") or "?"), os.path.expanduser(str(a["brain"]))))
    try:                       # overrides por máquina: SOLO vía el resolver canónico (Z23)
        import brain_resolver
        pl = brain_resolver.brain_overrides(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pl = {}
    if isinstance(pl, dict):
        for n, p in pl.items():
            if isinstance(p, str) and p.strip():
                out.append((str(n), os.path.expanduser(p)))
    seen, uniq = set(), []
    for n, p in out:
        if _norm(p) not in seen:
            seen.add(_norm(p))
            uniq.append((n, p))
    return uniq


def guard_dir(path, kind, cerebros=()):
    """'' si `path` se puede borrar como `kind` (harness/estado/app); si no,
    el motivo (la operación ENTERA se cancela). Rechaza: rutas relativas, la
    raíz de un disco, el HOME o un ancestro suyo, carpetas sin los marcadores
    de su tipo y cualquier carpeta que contenga un cerebro registrado."""
    if not os.path.isabs(path):
        return _t("uninstall.guard.relative", "no es una ruta absoluta")
    if os.path.dirname(_norm(path)) == _norm(path):
        return _t("uninstall.guard.root", "es la raíz de un disco")
    if _inside(HOME, path):
        return _t("uninstall.guard.home", "es tu carpeta personal (o la contiene)")
    if os.path.islink(path) or not os.path.isdir(path):
        return _t("uninstall.guard.notdir", "no es una carpeta")
    for n, b in cerebros:
        if _inside(b, path):
            return _t("uninstall.guard.brain",
                      "contiene el cerebro «{n}» ({b})").replace("{n}", n).replace("{b}", b)
    if kind == "harness" and not _is_harness(path):
        return _t("uninstall.guard.no_harness",
                  "no tiene los marcadores de Workspace (front.py, dispatch.py, install.py)")
    if kind == "estado":
        try:
            names = os.listdir(path)
        except OSError as e:
            return str(e)
        if names and not any(m in names for m in STATE_MARKERS):
            return _t("uninstall.guard.no_state",
                      "no tiene ningún archivo de estado de Workspace")
    if kind == "app":
        try:
            with open(os.path.join(path, "Contents", "Info.plist"), encoding="utf-8",
                      errors="ignore") as fh:
                if "workspace" not in fh.read().lower():
                    raise OSError
        except OSError:
            return _t("uninstall.guard.no_app", "no es la app de Workspace")
    return ""


def trabajo_sin_publicar(root):
    """'' si `root` no es un checkout de git o no tiene nada sin publicar; si
    no, qué tiene (cambios sin commit, commits que no están en ningún remoto,
    stashes) o por qué no se pudo comprobar. Un checkout así NUNCA se borra: la
    carpeta se conserva y el resto se desinstala (B02, 2026-10-17)."""
    if not os.path.exists(os.path.join(root, ".git")):
        return ""
    git = shutil.which("git")
    if not git:
        return _t("uninstall.git.no_git", "no pude comprobar si tiene trabajo sin publicar "
                  "(git no está instalado)")
    import subprocess

    def lineas(*args):
        r = subprocess.run([git, "-C", root] + list(args), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60,
                           stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise OSError((r.stderr or "").strip()[:160] or "git %s: %d" % (args[0], r.returncode))
        return [ln for ln in r.stdout.splitlines() if ln.strip()]
    try:
        cambios = lineas("status", "--porcelain")
        commits = lineas("log", "--branches", "--not", "--remotes", "--format=%h")
        stashes = lineas("stash", "list")
    except Exception as e:
        return _t("uninstall.git.fail", "no pude comprobar con git si tiene trabajo sin "
                  "publicar ({e})", e=e)
    partes = []
    if cambios:
        partes.append(_t("uninstall.git.changes", "{n} cambio(s) sin commit", n=len(cambios)))
    if commits:
        partes.append(_t("uninstall.git.commits", "{n} commit(s) sin push", n=len(commits)))
    if stashes:
        partes.append(_t("uninstall.git.stashes", "{n} stash(es) guardado(s)", n=len(stashes)))
    return ", ".join(partes)


def _desktop():
    try:
        import diag_bundle
        return diag_bundle.escritorio()
    except Exception:
        d = os.path.join(HOME, "Desktop")
        return d if os.path.isdir(d) else ""


def backup_path():
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(_desktop() or os.getcwd(), "workspace-respaldo-%s.zip" % stamp)


def _is_secret_file(name):
    """Archivos con credenciales (API keys, tokens de OAuth): NO viajan en un
    zip que queda en el Escritorio. La bóveda es `secrets.local`
    (secret_store); el resto se reconoce por nombre."""
    low = name.lower()
    return (low == "secrets.local" or "secret" in low or "token" in low
            or "credential" in low or low.endswith((".key", ".pem")))


def make_backup(state, dest):
    """Zip del estado per-máquina (ajustes, atajos, agentes registrados,
    temas…) — para reinstalar y recuperarlo tal cual. Sin el respaldo de
    transcripts (se conserva en disco) y SIN credenciales: un zip en el
    Escritorio no debe llevar tus claves (se vuelven a pegar al reinstalar).
    Atómico: tmp + rename."""
    import zipfile
    tmp = dest + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, dns, fns in os.walk(state):
            if dp == state:
                dns[:] = [d for d in dns if d not in STATE_KEEP]
            for fn in fns:
                if _is_secret_file(fn):
                    continue
                p = os.path.join(dp, fn)
                try:
                    z.write(p, os.path.relpath(p, state))
                except OSError:
                    pass
    os.replace(tmp, dest)
    return dest


def rm_state(state):
    """Borra el estado per-máquina CONSERVANDO lo de STATE_KEEP (si tiene algo)."""
    keep = [k for k in STATE_KEEP if os.path.isdir(os.path.join(state, k))
            and os.listdir(os.path.join(state, k))]
    if not keep:
        rm_path(state, _t("uninstall.label.state", "estado per-máquina"))
        return
    for n in sorted(os.listdir(state)):
        if n not in keep:
            rm_path(os.path.join(state, n), _t("uninstall.label.state_item", "estado"))
    info(f"{DIM}" + _t("uninstall.kept_inside", "conservado: {p}").replace(
        "{p}", ", ".join(os.path.join(state, k) for k in keep)) + R)


def _plan_print(root, state, app, cerebros, backup, clean=False, sin_publicar=""):
    def item(txt):
        print(f"    · {txt}")
    print(f"  {B}" + _t("uninstall.plan.delete", "SE BORRA") + R)
    if os.path.isdir(state):
        item(_t("uninstall.plan.state", "estado per-máquina (ajustes, atajos, agentes "
                "registrados): {p}").replace("{p}", state))
    if IS_WIN:
        item(_t("uninstall.plan.win", "comandos de Workspace en tu $PROFILE de PowerShell"))
    else:
        item(_t("uninstall.plan.unix", "comando `workspace` y launchers en ~/.local/bin; "
                "bloques de Workspace en ~/.zshrc"))
    names = ["`%s`" % fn for fn, _p in our_launchers()]
    if names:   # cada uno por su nombre: el socio ve qué se borra antes de confirmar
        item(_t("uninstall.plan.launchers", "en ~/.local/bin, solo estos (llevan la marca "
                "del instalador): {n}", n=", ".join(names)))
    item(_t("uninstall.plan.themes", "temas de Workspace en ~/.claude/themes"))
    temas = [os.path.basename(p) for _n, p in our_themes() if os.path.lexists(p)]
    if temas:
        item(_t("uninstall.plan.theme_files", "en ~/.claude/themes, solo estos (los "
                "generó Workspace): {n}", n=", ".join(temas)))
    if os.path.isdir(app):
        item(_t("uninstall.plan.app", "app de escritorio: {p}").replace("{p}", app))
    if not KEEP_FOLDER and not sin_publicar and os.path.isdir(root):
        item(_t("uninstall.plan.harness", "carpeta del harness: {p}").replace("{p}", root))
    print(f"  {B}" + _t("uninstall.plan.keep", "SE CONSERVA (no se toca)") + R)
    for n, b in cerebros:
        item(_t("uninstall.plan.brain", "cerebro «{n}»: {b}").replace("{n}", n)
             .replace("{b}", b))
    if not cerebros:
        item(_t("uninstall.plan.brains", "tus cerebros (carpetas de agentes), estén donde estén"))
    if KEEP_FOLDER:
        item(_t("uninstall.plan.harness_kept", "carpeta del harness (--keep-folder): {p}")
             .replace("{p}", root))
    elif sin_publicar:
        item(_t("uninstall.plan.harness_git", "carpeta del harness: {p} — es un checkout de "
                "git con trabajo sin publicar ({w}); bórrala tú cuando lo hayas guardado",
                p=root, w=sin_publicar))
    tb = os.path.join(state, STATE_KEEP[0])
    if os.path.isdir(tb) and os.listdir(tb):
        item(_t("uninstall.plan.tbackup", "respaldo de transcripts: {p}").replace("{p}", tb))
    item(_t("uninstall.plan.engines", "las conversaciones y logins de cada motor "
            "(Claude Code, Codex, …) y los propios motores"))
    if clean:
        item(_t("uninstall.plan.engines_clean", "las conversaciones de los perfiles de "
                "Workspace en OpenClaw y Hermes, en una carpeta de respaldo al lado de cada "
                "perfil (ver abajo)"))
    item(_t("uninstall.plan.cc_settings", "tu ~/.claude/settings.json (solo se quitan "
            "las claves que puso Workspace)"))
    print(f"  {B}" + _t("uninstall.plan.backup", "RESPALDO") + R)
    item(_t("uninstall.plan.backup_to", "estado per-máquina → {p}").replace("{p}", backup)
         if backup else _t("uninstall.plan.no_backup", "sin respaldo (--no-backup)")
         if "--no-backup" in sys.argv
         else _t("uninstall.plan.nothing_to_backup", "nada que respaldar (no hay estado)"))
    print()


def _ask(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return ""


# ── LIMPIAR TAMBIÉN CEREBROS Y MOTORES (--limpiar-todo / --clean-all) ────────
# Por defecto no se tocan. Con la opción se quita SOLO lo que Workspace
# escribió: claves, reglas y bloques EXACTOS y archivos generados con su marca.
# Sus perfiles propios de OpenClaw y Hermes guardan conversaciones: se APARTAN
# enteros al lado, jamás se borran. Cada archivo de configuración que
# cambia se respalda al lado (<archivo>.workspace-respaldo-<fecha>). Lo que no
# coincide exacto (editado por el socio) se deja. El contenido del cerebro no
# se toca: el CLAUDE.md puntero es su formato (por él Claude Code lee BRAIN.md).
CLEAN_FLAGS = ("--limpiar-todo", "--clean-all")
_BAK = ".workspace-respaldo-"
#: Marcador de los permisos que escribió Workspace (install._PERM_MARKER).
_PERM_MARKER = "__workspacePermissions"


def _stamp():
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _our_command(cmd, roots):
    """¿El comando corre el runner de hooks o un script de este harness?"""
    c = str(cmd or "").replace("\\", "/").lower()
    if "workspace_hook.py" in c:
        return True
    return any(r.replace("\\", "/").lower().rstrip("/") + "/" in c for r in roots)


def clean_brain_settings(data, roots, themes):
    """(dict nuevo, [lo quitado]) del settings.local.json de un cerebro: los
    hooks y la statusLine que corren scripts del harness, los permisos que
    Workspace anotó en su marcador y su tema. Lo demás queda tal cual."""
    if not isinstance(data, dict):
        return data, []
    new, gone = json.loads(json.dumps(data)), []
    hooks = new.get("hooks")
    if isinstance(hooks, dict):
        n = 0
        for ev in list(hooks):
            groups = hooks[ev]
            if not isinstance(groups, list):
                continue
            keep, cut = [], 0
            for g in groups:
                hs = g.get("hooks") if isinstance(g, dict) else None
                if not isinstance(hs, list):
                    keep.append(g)
                    continue
                kept = [h for h in hs if not (isinstance(h, dict)
                                              and _our_command(h.get("command"), roots))]
                cut += len(hs) - len(kept)
                if kept:
                    keep.append(dict(g, hooks=kept) if len(kept) != len(hs) else g)
            if cut:
                n += cut
                if keep:
                    hooks[ev] = keep
                else:
                    del hooks[ev]
        if n:
            gone.append(_t("uninstall.clean.hooks", "hooks de Workspace ({k})", k=n))
            if not hooks:
                del new["hooks"]
    sl = new.get("statusLine")
    if isinstance(sl, dict):
        cmd = str(sl.get("command") or "")
        if _our_command(cmd, roots) or ("--brain" in cmd and "statusline.py" in cmd):
            del new["statusLine"]
            gone.append(_t("uninstall.clean.statusline", "barra (statusLine)"))
    mark = new.get(_PERM_MARKER)
    if isinstance(mark, dict):
        ours = [r for r in (mark.get("allow") or []) if isinstance(r, str)]
        perms, k = new.get("permissions"), 0
        if isinstance(perms, dict) and isinstance(perms.get("allow"), list):
            before = perms["allow"]
            perms["allow"] = [r for r in before if r not in ours]
            k = len(before) - len(perms["allow"])
            if perms == {"allow": []}:
                del new["permissions"]
        del new[_PERM_MARKER]
        gone.append(_t("uninstall.clean.perms", "permisos de Workspace ({k} reglas)", k=k))
    th = new.get("theme")
    if isinstance(th, str) and th.startswith("custom:") and th.split(":", 1)[1] in themes:
        del new["theme"]
        gone.append(_t("uninstall.clean.theme", "tema {t}", t=th))
    return new, gone


def strip_codex_trust(text, brain_roots, escape):
    """(texto nuevo, [cerebros]) del config.toml de Codex sin los bloques
    `[projects."<cerebro>"]` que agregó Workspace: solo si el bloque dice
    EXACTAMENTE `trust_level = "trusted"` (otra clave o un comentario = del
    socio, se deja)."""
    heads = {'[projects."%s"]' % escape(r): r for r in brain_roots}
    lines = (text or "").splitlines(True)
    out, gone, i, at_end = [], [], 0, False
    while i < len(lines):
        h = lines[i].strip()
        if h in heads:
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("["):
                j += 1
            body = [ln.strip() for ln in lines[i + 1:j] if ln.strip()]
            if body == ['trust_level = "trusted"']:
                gone.append(heads[h])
                at_end = j >= len(lines)
                i = j
                continue
        out.append(lines[i])
        i += 1
    new = "".join(out)
    if gone and at_end and new.strip():
        new = new.rstrip("\n") + "\n"
    return new, gone


def clean_agy_settings(data, brain_roots, memoria_rules, is_ours):
    """(dict nuevo, [lo quitado]) del settings.json de Antigravity: los
    cerebros en trustedWorkspaces, sus reglas write_file/read_file, las reglas
    `workspace memoria …` y la statusLine de Workspace."""
    if not isinstance(data, dict):
        return data, []
    new, gone = json.loads(json.dumps(data)), []
    trusted = new.get("trustedWorkspaces")
    if isinstance(trusted, list):
        kept = [t for t in trusted if t not in brain_roots]
        if len(kept) != len(trusted):
            new["trustedWorkspaces"] = kept
            gone.append(_t("uninstall.clean.agy_trust", "cerebros en trustedWorkspaces ({k})",
                           k=len(trusted) - len(kept)))
    perms = new.get("permissions")
    allow = perms.get("allow") if isinstance(perms, dict) else None
    if isinstance(allow, list):
        files = {"%s(%s)" % (k, r) for r in brain_roots for k in ("write_file", "read_file")}
        n_f = sum(1 for r in allow if r in files)
        n_m = sum(1 for r in allow if r in memoria_rules)
        if n_f or n_m:
            perms["allow"] = [r for r in allow if r not in files and r not in memoria_rules]
        if n_f:
            gone.append(_t("uninstall.clean.agy_rules", "reglas de archivos del cerebro ({k})",
                           k=n_f))
        if n_m:
            gone.append(_t("uninstall.clean.agy_memoria", "reglas `workspace memoria …` ({k})",
                           k=n_m))
    sl = new.get("statusLine")
    if isinstance(sl, dict) and is_ours(sl.get("command")):
        del new["statusLine"]
        gone.append(_t("uninstall.clean.statusline", "barra (statusLine)"))
    return new, gone


def _read_json_strict(path):
    """dict del JSON, o None (no existe, enlace, enorme, corrupto o no es un
    objeto: entonces no se toca)."""
    try:
        if os.path.islink(path) or not os.path.isfile(path) \
                or os.path.getsize(path) > 1024 * 1024:
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _read_text(path):
    try:
        if os.path.islink(path) or not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()
    except (OSError, ValueError):
        return None


def _rewrite(path, text, stamp):
    """Respaldo al lado (copia exacta) + escritura atómica. → ruta del respaldo."""
    bak = path + _BAK + stamp
    shutil.copy2(path, bak)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return bak


def _apartar(path, stamp, copiar=False):
    """Aparta una carpeta AL LADO (<carpeta>.workspace-respaldo-<fecha>) en vez
    de borrarla: los perfiles de Workspace en OpenClaw y Hermes guardan las
    conversaciones del socio. `copiar` deja el original (para que después lo
    quite el borrado oficial del motor). → ruta del respaldo, solo si quedó
    comprobado; si no, OSError y el original sigue donde estaba."""
    dst = path + _BAK + stamp
    if os.path.lexists(dst):
        raise OSError(_t("uninstall.clean.bak_exists", "ya existe {p}", p=dst))
    if copiar:
        try:
            shutil.copytree(path, dst, symlinks=True)
        except BaseException:
            shutil.rmtree(dst, ignore_errors=True)        # solo la copia a medias
            raise
    else:
        os.rename(path, dst)
    if not os.path.isdir(dst) or (not copiar and os.path.lexists(path)):
        raise OSError(_t("uninstall.clean.bak_missing", "el respaldo no quedó en {p}", p=dst))
    return dst


def _generated_doc(path, marks):
    """¿El archivo empieza con la marca de generado de Workspace?"""
    head = _read_text(path)
    return head is not None and any(head.lstrip().startswith(m) for m in marks)


def _which(binary):
    return shutil.which(binary)


def _run_quiet(cmd, timeout=300):
    import subprocess
    env = None
    try:                                         # el motor no hereda la bóveda
        import secret_store
        env = secret_store.engine_env()
    except Exception:
        pass
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
                          env=env)


def plan_clean_all(cerebros, stamp=None):
    """Qué quitaría --limpiar-todo. Solo LEE. → (ítems, editados): cada ítem es
    (texto, ruta, tipo 'edit'|'rm', acción); la acción re-lee y re-calcula al
    aplicarse. `editados` = rutas que se dejan por estar cambiadas a mano."""
    stamp = stamp or _stamp()
    roots = []                      # el harness como lo hornean hooks y statusLine
    for p in (workspace_root(), os.path.dirname(os.path.abspath(__file__))):
        for v in (os.path.abspath(p), os.path.realpath(p)):
            if v not in roots:
                roots.append(v)
    brain_roots = []
    for _n, b in cerebros:
        r = os.path.realpath(os.path.abspath(os.path.expanduser(b)))
        if r not in brain_roots:
            brain_roots.append(r)
    items, kept = [], []

    def json_item(path, label, transform):
        data = _read_json_strict(path)
        if data is None:
            return
        _new, gone = transform(data)
        if not gone:
            return

        def act():
            cur = _read_json_strict(path)
            new, again = transform(cur) if cur is not None else (None, [])
            if again:
                return _rewrite(path, json.dumps(new, indent=2, ensure_ascii=False) + "\n",
                                stamp)
            return ""
        items.append(("%s → %s" % (label, ", ".join(gone)), path, "edit", act))

    def rm_item(path, label, check=None):
        def act():
            if check is None or check():
                rm_path(path, os.path.basename(path))
            return ""
        items.append((label, path, "rm", act))

    # cerebros: su settings.local.json y los punteros que generó Workspace
    themes = set(known_themes()) | {n for n, _b in cerebros}
    try:
        from engines import codex as _cx
        agents_marks = (_cx._GEN_MARK, _cx._GEN_MARK_LEGACY)
    except Exception:
        _cx, agents_marks = None, ()
    try:
        from engines import antigravity as _agy
        gemini_marks = (_agy._GEMINI_MARK, _agy._GEMINI_MARK_LEGACY)
    except Exception:
        _agy, gemini_marks = None, ()
    for n, b in cerebros:
        sp = os.path.join(b, ".claude", "settings.local.json")
        json_item(sp, _t("uninstall.clean.brain", "cerebro «{n}»: {p}", n=n, p=sp),
                  lambda d: clean_brain_settings(d, roots, themes))
        for fn, marks in (("AGENTS.md", agents_marks), ("GEMINI.md", gemini_marks)):
            p = os.path.join(b, fn)
            if not marks or not os.path.isfile(p):
                continue
            if _generated_doc(p, marks):
                rm_item(p, _t("uninstall.clean.pointer",
                              "cerebro «{n}»: {f} generado por Workspace ({p})",
                              n=n, f=fn, p=p),
                        check=lambda p=p, marks=marks: _generated_doc(p, marks))
    # Codex: confianza de los cerebros y sus temas workspace-*.tmTheme
    codex_dir = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")
    cfg = os.path.join(codex_dir, "config.toml")
    text = _read_text(cfg)
    if _cx is not None and text is not None:
        esc = _cx._toml_key_escape
        _new, gone = strip_codex_trust(text, brain_roots, esc)
        if gone:
            def act_codex():
                cur = _read_text(cfg)
                new, again = strip_codex_trust(cur or "", brain_roots, esc)
                return _rewrite(cfg, new, stamp) if again else ""
            items.append((_t("uninstall.clean.codex_trust",
                             "Codex: {p} → confianza de {k} cerebro(s) ([projects.\"…\"])",
                             p=cfg, k=len(gone)), cfg, "edit", act_codex))
    tdir = os.path.join(codex_dir, "themes")
    try:
        import theme_render as _tr
        tnames = sorted(f for f in os.listdir(tdir)
                        if f.startswith("workspace-") and f.endswith(".tmTheme"))
    except Exception:
        _tr, tnames = None, []
    for f in tnames:
        p = os.path.join(tdir, f)
        # solo el que está TAL CUAL lo generó Workspace (registro + mismo
        # contenido); uno sin registro —hecho a mano o de otra instalación— se deja
        if _tr.is_generated(p, HOME):
            rm_item(p, _t("uninstall.clean.codex_theme", "Codex: tema {p}", p=p),
                    check=lambda p=p: _tr.is_generated(p, HOME))
        else:
            kept.append(p)
    # Antigravity: su settings.json y sus proyectos workspace-*.json
    if _agy is not None:
        try:
            import antigravity_usage as _au
            is_ours = _au.is_ours
        except Exception:
            is_ours = lambda c: False                     # noqa: E731
        agy_home = os.environ.get("ANTIGRAVITY_CLI_HOME") or os.path.join(
            HOME, ".gemini", "antigravity-cli")
        rules = set(_agy.MEMORIA_RULES) | set(_agy._MEMORIA_RULES_VIEJAS)
        ap = os.path.join(agy_home, "settings.json")
        json_item(ap, _t("uninstall.clean.agy", "Antigravity: {p}", p=ap),
                  lambda d: clean_agy_settings(d, brain_roots, rules, is_ours))
        pdir = os.path.join(HOME, ".gemini", "config", "projects")
        try:
            pnames = sorted(f for f in os.listdir(pdir)
                            if f.startswith(_agy.PROJECT_PREFIX) and f.endswith(".json"))
        except OSError:
            pnames = []
        for f in pnames:
            p = os.path.join(pdir, f)
            if _agy_project_ours(p, f[:-5], _agy.FULL_GRANT):
                rm_item(p, _t("uninstall.clean.agy_project", "Antigravity: proyecto {p}", p=p),
                        check=lambda p=p, pid=f[:-5]: _agy_project_ours(p, pid, _agy.FULL_GRANT))
            else:
                kept.append(p)
    # OpenClaw y Hermes: sus perfiles PROPIOS de Workspace (el personal, jamás).
    # Guardan las conversaciones del socio: se APARTAN al lado, nunca se borran.
    try:
        from engines import openclaw as _oc
        prof = _oc._profile()
        oc = os.path.join(HOME, ".openclaw-" + prof)
        if prof and os.path.isdir(oc) and not os.path.islink(oc):
            def act_oc(oc=oc, prof=prof):
                try:
                    import openclaw_gateway as _gw
                    if _gw.running(prof):
                        _gw.shutdown(_which("openclaw"), prof)
                except Exception:
                    pass
                bak = _apartar(oc, stamp)
                ok(_t("uninstall.clean.moved", "{label} apartado con sus conversaciones (no se "
                      "borró): {p} → {b}", label=_t("uninstall.clean.oc_label",
                                                     "perfil de OpenClaw"), p=oc, b=bak))
                return bak
            items.append((_t("uninstall.clean.openclaw",
                             "OpenClaw: perfil de Workspace {p} → se aparta (no se borra) a {b}, "
                             "con sus conversaciones y el proveedor que conectaste ahí; tu "
                             "OpenClaw personal no se toca", p=oc, b=oc + _BAK + stamp),
                          oc, "move", act_oc))
    except Exception:
        pass
    try:
        from engines import hermes as _hm
        prof, hp = _hm._profile(), _hm.profile_dir()
        if (prof and os.path.basename(hp) == prof
                and os.path.basename(os.path.dirname(hp)) == "profiles"
                and os.path.isdir(hp) and not os.path.islink(hp)):
            def act_hm(hp=hp, prof=prof):
                exe = _which("hermes")
                # Primero el respaldo comprobado; con Hermes instalado, una copia
                # para que su borrado OFICIAL (suelta su gateway e identidad) siga.
                bak = _apartar(hp, stamp, copiar=bool(exe))
                if exe:
                    try:
                        _run_quiet([exe, "profile", "delete", prof, "-y"])
                    except Exception:
                        pass
                    if os.path.isdir(hp):    # la copia ya está a salvo en `bak`
                        shutil.rmtree(hp, ignore_errors=True)
                    if os.path.lexists(hp):
                        raise OSError(_t("uninstall.clean.hm_left",
                                         "el perfil sigue ahí; su copia quedó en {b}", b=bak))
                ok(_t("uninstall.clean.moved", "{label} apartado con sus conversaciones (no se "
                      "borró): {p} → {b}", label=_t("uninstall.clean.hm_label",
                                                     "perfil de Hermes"), p=hp, b=bak))
                return bak
            items.append((_t("uninstall.clean.hermes",
                             "Hermes: perfil de Workspace {p} → se aparta (no se borra) a {b}, "
                             "con sus conversaciones y el proveedor que conectaste ahí; tu "
                             "Hermes personal no se toca", p=hp, b=hp + _BAK + stamp),
                          hp, "move", act_hm))
    except Exception:
        pass
    return items, kept


def _agy_project_ours(path, pid, grant):
    """¿El proyecto de agy es el que crea Workspace, sin nada agregado? (mismo
    id que su nombre, sin recursos y como mucho la regla de autonomía full)."""
    d = _read_json_strict(path)
    if d is None or d.get("id") != pid:
        return False
    # Cualquier cosa que no escribió Workspace (otra clave, reglas deny/ask,
    # recursos) = el socio lo editó → no se borra (Greptile, 2026-10-17).
    if set(d) - {"id", "name", "projectResources", "permissionGrants"}:
        return False
    if d.get("projectResources"):
        return False
    pg = d.get("permissionGrants") or {}
    if not isinstance(pg, dict) or set(pg) - {"permissionGrants", "v2Migrated"}:
        return False
    inner = pg.get("permissionGrants") or {}
    if not isinstance(inner, dict) or set(inner) - {"allow"}:
        return False
    allow = inner.get("allow") or []
    return isinstance(allow, list) and all(r == grant for r in allow)


def _clean_print(items, kept, stamp):
    def item(txt):
        print(f"    · {txt}")
    print(f"  {B}" + _t("uninstall.clean.title", "TAMBIÉN SE LIMPIA (cerebros y motores: "
                        "solo lo que escribió Workspace)") + R)
    if not items:
        item(_t("uninstall.clean.none", "nada: no queda nada de Workspace en tus cerebros "
                "ni en los motores"))
    for txt, _p, _k, _a in items:
        item(txt)
    if any(k == "edit" for _t2, _p, k, _a in items):
        item(_t("uninstall.clean.backups", "cada archivo de configuración que cambia queda "
                "respaldado al lado: <archivo>{b}", b=_BAK + stamp))
    print(f"  {B}" + _t("uninstall.clean.keep", "SE CONSERVA AL LIMPIAR") + R)
    item(_t("uninstall.clean.keep_claude", "el CLAUDE.md de cada cerebro (es el formato del "
            "cerebro: por él Claude Code lee BRAIN.md) y todo su contenido"))
    for p in kept:
        item(_t("uninstall.clean.kept_user", "se deja (lo editaste o no lo escribió Workspace tal cual): {p}", p=p))
    print()


def apply_clean_all(items):
    """Aplica el plan (o lo muestra en --dry-run). Falla-suave por ítem.
    → [(carpeta, respaldo)] de los perfiles que se apartaron (para el final)."""
    moved = []
    for txt, path, kind, act in items:
        if DRY:
            dry(_t("uninstall.clean.dry", "limpiaría: {what}", what=txt))
            continue
        try:
            bak = act()
            if bak and kind == "move":            # el ✓ lo dio la acción, ya comprobado
                moved.append((path, bak))
            elif bak:
                ok(_t("uninstall.clean.done", "limpiado: {p} (respaldo: {b})", p=path, b=bak))
        except Exception as e:
            info(_t("uninstall.clean.fail", "{dim}no pude limpiar {p} ({e}){r}",
                    dim=DIM, p=path, e=e, r=R))
    return moved
_USO = ("uso: python3 uninstall.py [--dry-run] [--keep-folder] [--workspace <ruta>]\n"
        "                          [--yes|-y] [--backup|--no-backup] [--limpiar-todo]\n"
        "  Desinstala Workspace de esta máquina; tus cerebros y conversaciones se quedan.\n"
        "  --dry-run muestra qué borraría, sin tocar nada.\n"
        "  --limpiar-todo quita también lo que Workspace escribió en cerebros y motores.")


def main():
    # `--help`/`-h`: el uso y salir. JAMÁS desinstalar por pedir ayuda (sin
    # terminal no hay confirmación). `workspace uninstall --help` ya lo corta
    # front.main; esto cubre `python3 uninstall.py --help` directo.
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        print(_t("uninstall.usage", _USO))
        return 0
    root = workspace_root()
    state = _paths.state_dir(HOME)
    app = os.path.join(HOME, "Desktop", "WORKSPACE.app")
    print(_t("uninstall.x.main.1", "\n  {b}{c}Desinstalador de WORKSPACE{r}  {dim}· {v} · {root}{r}", b=B, c=C, r=R, dim=DIM, v=platform.system(), root=root)
          + (f"  {DIM}(DRY-RUN){R}" if DRY else "") + "\n")

    # 1) GUARDAS antes de todo: si una carpeta a borrar no prueba ser de
    #    Workspace (o contiene un cerebro), se cancela TODO — nada se borra.
    cerebros = brains()
    # Un checkout con trabajo sin publicar (commits sin push, cambios sin
    # commit) jamás se borra: la carpeta se conserva y lo demás se desinstala.
    sin_publicar = "" if KEEP_FOLDER or not os.path.isdir(root) else trabajo_sin_publicar(root)
    keep_folder = KEEP_FOLDER or bool(sin_publicar)
    targets = [(state, "estado")]
    if os.path.isdir(app):
        targets.append((app, "app"))
    if not keep_folder and os.path.lexists(root):
        targets.append((root, "harness"))
    for path, kind in targets:
        if not os.path.lexists(path):
            continue
        why = guard_dir(path, kind, cerebros)
        if why:
            print(f"  ✗ " + _t("uninstall.refused", "Me niego a borrar {p}: {why}.")
                  .replace("{p}", path).replace("{why}", why))
            print(f"    {B}" + _t("uninstall.nothing", "Nada fue borrado.") + R)
            if kind == "harness":
                print(f"    {DIM}" + _t("uninstall.hint_folder",
                      "Si es otra carpeta: --workspace <ruta>. Para desinstalar sin "
                      "tocarla: --keep-folder.") + R)
            print()
            return 2
    if not KEEP_FOLDER and not os.path.lexists(root):
        info(f"{DIM}" + _t("uninstall.no_root", "no encuentro la carpeta del harness en {p} "
             "(nada que borrar ahí; usa --workspace <ruta> si está en otro lado)")
             .replace("{p}", root) + R)

    # 2) Qué se borra / qué se conserva / respaldo — SIEMPRE visible.
    yes = "--yes" in sys.argv or "-y" in sys.argv
    tty = sys.stdin.isatty()
    want_backup = "--no-backup" not in sys.argv and os.path.isdir(state) \
        and bool(os.listdir(state))
    backup = backup_path() if want_backup else ""
    clean = any(f in sys.argv for f in CLEAN_FLAGS)
    _plan_print(root, state, app, cerebros, backup, clean=clean, sin_publicar=sin_publicar)

    # Sin terminal no hay a quién preguntar (un script, un agente, CI): sin un
    # --yes explícito no se borra nada (igual que `workspace update --rollback`).
    if not DRY and not yes and not tty:
        print("  " + _t("uninstall.need_yes", "Sin terminal interactiva no puedo pedirte "
                        "confirmación. Nada fue borrado. Para desinstalar así, añade --yes "
                        "(y mira antes qué pasaría con --dry-run).") + "\n")
        return 2

    # 2b) Opcional: limpiar también cerebros y motores (flag o pregunta). Se
    #     calcula AHORA, antes de borrar el estado (registro de temas, gateway).
    if not clean and not DRY and not yes and tty:
        r = _ask("  " + _t("uninstall.clean.ask",
                           "¿Limpio también cerebros y motores? Se quita solo lo que "
                           "Workspace escribió en ellos, con respaldo al lado. Sus perfiles "
                           "de OpenClaw y Hermes, con tus conversaciones de ahí, se mueven a "
                           "una carpeta de respaldo junto a cada uno. El contenido de tus "
                           "cerebros no se toca [s/N]: "))
        clean = r in ("s", "si", "sí", "y", "yes")
    citems = []
    if clean:
        stamp = _stamp()
        citems, ckept = plan_clean_all(cerebros, stamp)
        _clean_print(citems, ckept, stamp)

    # 3) Confirmación (salvo --yes/-y o no-interactivo) + oferta de respaldo.
    if not DRY and not yes and tty:
        if want_backup and "--backup" not in sys.argv:
            r = _ask("  " + _t("uninstall.ask_backup",
                               "¿Creo el respaldo antes de borrar? [S/n]: "))
            if r in ("n", "no"):
                backup = ""
        r = _ask("  " + _t("uninstall.ask_sure", "¿Seguro? escribe 'si' para continuar: "))
        if r not in ("si", "sí", "s", "yes", "y"):
            print("  " + _t("uninstall.cancelled", "Cancelado. Nada fue borrado.") + "\n")
            return 0

    if backup:
        if DRY:
            dry(_t("uninstall.dry_backup", "crearía el respaldo: {p}").replace("{p}", backup))
        else:
            try:
                make_backup(state, backup)
                ok(_t("uninstall.backup_ok", "respaldo creado: {p} (trae tus ajustes y credenciales locales: guárdalo en privado)").replace("{p}", backup))
            except Exception as e:
                print(f"  ✗ " + _t("uninstall.backup_fail",
                      "No pude crear el respaldo ({e}). Nada fue borrado. Para seguir sin "
                      "respaldo: --no-backup.").replace("{e}", str(e)) + "\n")
                return 1

    moved = []
    if citems:
        moved = apply_clean_all(citems)   # ANTES de borrar el estado y el harness
    restore_retention()   # ANTES de borrar el estado (lee pre-install.json de ahí)
    reset_theme()         # ANTES de borrar el estado (agentes y registro de temas viven ahí)
    rm_state(state)
    if IS_WIN:
        strip_profile_windows()
        remove_launchers_unix()   # el shim sh de Git Bash (marcado WORKSPACE)
    else:
        remove_launchers_unix()
        strip_zshrc()
    rm_path(app, _t("uninstall.x.main.2", "app de escritorio"))       # ya pasó guard_dir (o no existe)

    if KEEP_FOLDER:
        info(_t("uninstall.x.main.3", "{dim}carpeta del harness conservada (--keep-folder): {root}{r}", dim=DIM, root=root, r=R))
    elif sin_publicar:
        info(_t("uninstall.x.main.git", "{dim}carpeta del harness conservada: {root} — tiene trabajo de git sin publicar ({w}).{r}", dim=DIM, root=root, w=sin_publicar, r=R))
    elif not _is_harness(root):   # SEC-06: no borrar una carpeta que no sea el harness
        info(_t("uninstall.x.main.4", "{dim}aviso: {root} no parece un harness WORKSPACE (sin front.py/dispatch.py/install.py) — NO borro la carpeta. Usa --workspace <ruta> si es otra.{r}", dim=DIM, root=root, r=R))
    else:
        rm_path(root, _t("uninstall.x.main.5", "carpeta del harness"))

    print(_t("uninstall.x.main.6", "\n  {c}Listo.{r} WORKSPACE desinstalado de esta máquina.", c=C, r=R))
    if clean:
        print(_t("uninstall.clean.final", "  {dim}De los cerebros y los motores solo se quitó lo que escribió Workspace, con respaldo al lado; el contenido de tus cerebros no se tocó.{r}", dim=DIM, r=R))
        for _p, bak in moved:
            print(_t("uninstall.clean.final_moved", "  {dim}Las conversaciones de {p} siguen en {b}{r}", dim=DIM, p=_p, b=bak, r=R))
    else:
        print(_t("uninstall.x.main.7", "  {dim}Los CEREBROS (carpetas de agentes) y los transcripts NO se tocaron.{r}", dim=DIM, r=R))
    print(_t("uninstall.x.main.9", "  {dim}Si vuelves a instalar Workspace, carga de nuevo cada agente (Agregar agente → cargar su carpeta) para que apunte a la instalación nueva; si restauraste tu respaldo, basta con `workspace doctor`.{r}", dim=DIM, r=R))
    if backup and not DRY:
        print(f"  {DIM}" + _t("uninstall.backup_where", "Tu respaldo: {p}").replace(
            "{p}", backup) + R)
    if not DRY:
        print(_t("uninstall.x.main.8", "  {dim}Abre una terminal NUEVA para soltar el PATH/greeter viejos.{r}", dim=DIM, r=R))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
