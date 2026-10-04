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
#
#    python3 uninstall.py [--dry-run] [--keep-folder] [--workspace /ruta/WORKSPACE]
# ════════════════════════════════════════════════════════════════════════════
import os, re, sys, json, shutil, platform

HOME = os.path.expanduser("~")
IS_WIN = platform.system() == "Windows"
DRY = "--dry-run" in sys.argv
KEEP_FOLDER = "--keep-folder" in sys.argv
C, R, B, DIM = "\033[38;5;51m", "\033[0m", "\033[1m", "\033[38;5;67m"
if IS_WIN:
    os.system("")  # habilita ANSI en Windows 10+


def ok(m):  print(f"  {C}✓{R} {m}")
def info(m): print(f"  {m}")
def dry(m): print(f"  {DIM}[dry-run] {m}{R}")


def rm_path(p, label):
    if not p or not os.path.exists(p) and not os.path.islink(p):
        return
    if DRY:
        dry(f"borraría {label}: {p}")
        return
    try:
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p, ignore_errors=True)
        else:
            os.remove(p)
        ok(f"{label} borrado: {p}")
    except OSError as e:
        info(f"{DIM}no pude borrar {p} ({e}){R}")


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
        dry(f"limpiaría los bloques de WORKSPACE de {rc}")
        return
    open(rc, "w", encoding="utf-8").write(new)
    ok("~/.zshrc limpiado (PATH + greeter de WORKSPACE)")


def strip_profile_windows():
    """DEPLOY-6: quita del $PROFILE SOLO los marcadores de WORKSPACE (no toda línea con
    'workspace' — eso borraba líneas del usuario). Quirúrgico, espejo de strip_zshrc."""
    rm_path(os.path.join(HOME, ".claude", "workspace-cmds.ps1"), "comandos PowerShell")
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
        dry(f"limpiaría los marcadores de WORKSPACE de {prof}")
        return
    open(prof, "w", encoding="utf-8").write(new)
    ok(f"$PROFILE limpiado (marcadores WORKSPACE): {prof}")


def _read_json(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


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
        rm_path(os.path.join(HOME, ".claude", "themes", f"{n}.json"), f"tema {n}")
    sp = os.path.join(HOME, ".claude", "settings.json")
    s = _read_json(sp)
    th = s.get("theme")
    if isinstance(th, str) and th.startswith("custom:") and th.split(":", 1)[1] in known:
        if DRY:
            dry(f"quitaría theme={th} de ~/.claude/settings.json")
            return
        s.pop("theme", None)
        json.dump(s, open(sp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        ok(f"theme {th} removido de ~/.claude/settings.json")


def restore_retention():
    """SEC-05: revierte cleanupPeriodDays al valor que había ANTES del install
    (install lo guardó en ~/.claude/workspace/pre-install.json). DEBE correr antes de
    borrar el estado per-máquina. Si no hay registro, no toca nada (no asume)."""
    pre = _read_json(os.path.join(HOME, ".claude", "workspace", "pre-install.json"))
    if "cleanupPeriodDays" not in pre:
        return
    sp = os.path.join(HOME, ".claude", "settings.json")
    s = _read_json(sp)
    if not s:
        return
    prior = pre.get("cleanupPeriodDays")   # None = la clave no existía antes
    if DRY:
        dry(f"restauraría cleanupPeriodDays={prior!r} en {sp}")
        return
    if prior is None:
        s.pop("cleanupPeriodDays", None)
    else:
        s["cleanupPeriodDays"] = prior
    json.dump(s, open(sp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    ok(f"cleanupPeriodDays restaurado ({'sin valor' if prior is None else prior})")


def _is_harness(root):
    """SEC-06: ¿`root` es de verdad un harness WORKSPACE? (no borrar una carpeta ajena
    si --workspace apunta mal)."""
    return all(os.path.isfile(os.path.join(root, f))
               for f in ("front.py", "dispatch.py", "install.py"))


def main():
    root = workspace_root()
    print(f"\n  {B}{C}Desinstalador de WORKSPACE{R}  {DIM}· {platform.system()} · {root}{R}"
          + (f"  {DIM}(DRY-RUN){R}" if DRY else "") + "\n")

    # Confirmación (salvo --yes/-y o no-interactivo): borra el harness, no los cerebros.
    yes = "--yes" in sys.argv or "-y" in sys.argv
    if not DRY and not yes and sys.stdin.isatty():
        info(f"Esto desinstala WORKSPACE de esta máquina ({root}).")
        info(f"{DIM}Los cerebros (agentes) y los transcripts NO se tocan.{R}")
        try:
            r = input("  ¿Seguro? escribe 'si' para continuar: ").strip().lower()
        except EOFError:
            r = ""
        if r not in ("si", "sí", "s", "yes", "y"):
            print("  Cancelado.\n")
            return

    restore_retention()   # ANTES de borrar el estado (lee pre-install.json de ahí)
    rm_path(os.path.join(HOME, ".claude", "workspace"), "estado per-máquina")
    if IS_WIN:
        strip_profile_windows()
    else:
        remove_launchers_unix()
        strip_zshrc()
    reset_theme()
    rm_path(os.path.join(HOME, "Desktop", "WORKSPACE.app"), "app de escritorio")

    if KEEP_FOLDER:
        info(f"{DIM}carpeta del harness conservada (--keep-folder): {root}{R}")
    elif not _is_harness(root):   # SEC-06: no borrar una carpeta que no sea el harness
        info(f"{DIM}aviso: {root} no parece un harness WORKSPACE (sin front.py/dispatch.py/"
             f"install.py) — NO borro la carpeta. Usa --workspace <ruta> si es otra.{R}")
    else:
        rm_path(root, "carpeta del harness")

    print(f"\n  {C}Listo.{R} WORKSPACE desinstalado de esta máquina.")
    print(f"  {DIM}Los CEREBROS (carpetas de agentes) y los transcripts NO se tocaron.{R}")
    if not DRY:
        print(f"  {DIM}Abre una terminal NUEVA para soltar el PATH/greeter viejos.{R}")
    print()


if __name__ == "__main__":
    main()
