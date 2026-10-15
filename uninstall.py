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
#    python3 uninstall.py [--dry-run] [--keep-folder] [--workspace /ruta/WORKSPACE]
#                         [--yes|-y] [--backup|--no-backup]
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


def rm_path(p, label):
    if not p or not os.path.exists(p) and not os.path.islink(p):
        return
    if DRY:
        dry(_t("uninstall.x.rm_path.1", "borraría {label}: {p}", label=label, p=p))
        return
    try:
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
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


def remove_launchers_unix():
    """Borra de ~/.local/bin los launchers que el instalador creó (los marca con
    'WORKSPACE' en el cuerpo). Solo toca archivos de texto que llevan el marcador."""
    bindir = os.path.join(HOME, ".local", "bin")
    if not os.path.isdir(bindir):
        return
    for fn in sorted(os.listdir(bindir)):
        p = os.path.join(bindir, fn)
        if not os.path.isfile(p):
            continue
        try:
            head = open(p, encoding="utf-8", errors="ignore").read(400)
        except Exception:
            continue
        if "WORKSPACE" in head:
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


def reset_theme():
    """Quita los temas in-app que instaló WORKSPACE (themes/<agente>.json) y, si el
    settings GLOBAL apunta a uno nuestro (installs viejos), lo limpia. DEPLOY-1/SEC-05."""
    known = known_themes()
    for n in known:
        rm_path(os.path.join(HOME, ".claude", "themes", f"{n}.json"), _t("uninstall.x.theme", "tema {n}", n=n))
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


def _plan_print(root, state, app, cerebros, backup):
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
    item(_t("uninstall.plan.themes", "temas de Workspace en ~/.claude/themes"))
    if os.path.isdir(app):
        item(_t("uninstall.plan.app", "app de escritorio: {p}").replace("{p}", app))
    if not KEEP_FOLDER and os.path.isdir(root):
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
    tb = os.path.join(state, STATE_KEEP[0])
    if os.path.isdir(tb) and os.listdir(tb):
        item(_t("uninstall.plan.tbackup", "respaldo de transcripts: {p}").replace("{p}", tb))
    item(_t("uninstall.plan.engines", "las conversaciones y logins de cada motor "
            "(Claude Code, Codex, …) y los propios motores"))
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


def main():
    root = workspace_root()
    state = _paths.state_dir(HOME)
    app = os.path.join(HOME, "Desktop", "WORKSPACE.app")
    print(_t("uninstall.x.main.1", "\n  {b}{c}Desinstalador de WORKSPACE{r}  {dim}· {v} · {root}{r}", b=B, c=C, r=R, dim=DIM, v=platform.system(), root=root)
          + (f"  {DIM}(DRY-RUN){R}" if DRY else "") + "\n")

    # 1) GUARDAS antes de todo: si una carpeta a borrar no prueba ser de
    #    Workspace (o contiene un cerebro), se cancela TODO — nada se borra.
    cerebros = brains()
    targets = [(state, "estado")]
    if os.path.isdir(app):
        targets.append((app, "app"))
    if not KEEP_FOLDER and os.path.lexists(root):
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
    _plan_print(root, state, app, cerebros, backup)

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

    restore_retention()   # ANTES de borrar el estado (lee pre-install.json de ahí)
    rm_state(state)
    if IS_WIN:
        strip_profile_windows()
    else:
        remove_launchers_unix()
        strip_zshrc()
    reset_theme()
    rm_path(app, _t("uninstall.x.main.2", "app de escritorio"))       # ya pasó guard_dir (o no existe)

    if KEEP_FOLDER:
        info(_t("uninstall.x.main.3", "{dim}carpeta del harness conservada (--keep-folder): {root}{r}", dim=DIM, root=root, r=R))
    elif not _is_harness(root):   # SEC-06: no borrar una carpeta que no sea el harness
        info(_t("uninstall.x.main.4", "{dim}aviso: {root} no parece un harness WORKSPACE (sin front.py/dispatch.py/install.py) — NO borro la carpeta. Usa --workspace <ruta> si es otra.{r}", dim=DIM, root=root, r=R))
    else:
        rm_path(root, _t("uninstall.x.main.5", "carpeta del harness"))

    print(_t("uninstall.x.main.6", "\n  {c}Listo.{r} WORKSPACE desinstalado de esta máquina.", c=C, r=R))
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
