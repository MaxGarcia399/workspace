#!/usr/bin/env python3
"""WORKSPACE · dev_setup — onboarding de DESARROLLO, separado del de cliente (U11/Z11).

`workspace dev setup` (o `workspace configurar-desarrollo`) recorre lo que un
dev necesita para contribuir SIN tocar la instalación de cliente:
  1. Git presente · este árbol es un checkout (rama, remoto, cambios sin commit)
  2. Python ≥ 3.9 · runner de tests (tests/run.py) · gh OPCIONAL
  3. Directorio temporal escribible para perfiles de prueba (HOME aislado)
  4. Contrato: núcleo + adapters (ARCHITECTURE.md, engines/CONTRACT.md,
     engines/PORTABILITY.md), workflow de contribución (WORKFLOW.md)
  5. Siguiente paso: rama → checks → revisión (`workspace feature …`,
     `python tests/run.py`, `workspace integrate`)
Modo dev = marker per-máquina explícito (`--enable` / `--disable`), NO la
identidad de nadie ni un roster del equipo. Uso cliente funciona sin repo ni
gh: este flujo solo informa y, con --enable, escribe ese marker.

Checks locales, sin red (no hace fetch: el estado remoto se consulta
explícito con `workspace doctor --remote`).
"""
import os
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))

DOCS = ("ARCHITECTURE.md", "WORKFLOW.md", os.path.join("engines", "CONTRACT.md"),
        os.path.join("engines", "PORTABILITY.md"), os.path.join("tests", "README.md"))


def _git(*args, which=shutil.which):
    if not which("git"):
        return None
    try:
        r = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=8)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def marker_path():
    return os.path.join(_paths.state_dir(), "dev-mode")


def checks(which=shutil.which, git=_git):
    """[(id, ok|None, detalle, cómo_arreglar)] — ok None = opcional ausente."""
    out = []
    has_git = bool(which("git"))
    out.append(("git", has_git, which("git") or "no encontrado",
                "" if has_git else "instala Git (https://git-scm.com/downloads)"))
    top = git("rev-parse", "--show-toplevel") if has_git else None
    out.append(("checkout", bool(top), top or "este árbol no es un repo Git (¿paquete cliente?)",
                "" if top else "clona el repo de desarrollo en una carpeta propia — "
                               "no conviertas la instalación cliente en checkout"))
    if top:
        br = git("rev-parse", "--abbrev-ref", "HEAD") or "?"
        rem = git("remote", "get-url", "origin") or "sin remoto 'origin'"
        dirty = git("status", "--porcelain")
        out.append(("rama", True, "%s · remoto: %s" % (br, rem), ""))
        out.append(("cambios", True, "%d archivos sin commit" % len(dirty.splitlines())
                    if dirty else "árbol limpio", ""))
    pyok = sys.version_info >= (3, 9)
    out.append(("python", pyok, sys.version.split()[0],
                "" if pyok else "usa Python 3.9 o superior"))
    runner = os.path.isfile(os.path.join(ROOT, "tests", "run.py"))
    out.append(("tests", runner, "python tests/run.py [filtro]" if runner
                else "tests/ no viene en este árbol (paquete cliente)",
                "" if runner else "los tests viven en el checkout de desarrollo"))
    gh = which("gh")
    out.append(("gh", True if gh else None, gh or "no instalado (opcional: PRs/issues)",
                "" if gh else "opcional: https://cli.github.com"))
    try:
        d = tempfile.mkdtemp(prefix="workspace-dev-check-")
        os.rmdir(d)
        tmpok, tmpd = True, tempfile.gettempdir()
    except Exception as e:
        tmpok, tmpd = False, "no escribible (%s)" % type(e).__name__
    out.append(("tmp", tmpok, tmpd, "" if tmpok else "revisa TEMP/TMPDIR"))
    missing = [d for d in DOCS if not os.path.isfile(os.path.join(ROOT, d))]
    out.append(("docs", not missing, "contrato y workflow presentes" if not missing
                else "faltan: " + ", ".join(missing), ""))
    return out


def dev_mode():
    try:
        txt = open(marker_path(), encoding="utf-8").read().strip().lower()
        return txt not in ("off", "0", "no", "false")
    except Exception:
        return None


def set_dev_mode(on):
    p = marker_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("on\n" if on else "off\n")
    os.replace(tmp, p)


def report(rows):
    lines = ["Workspace · configurar desarrollo", ""]
    for cid, ok, detail, fix in rows:
        mark = "✓" if ok else ("·" if ok is None else "✗")
        lines.append("  %s %-9s %s" % (mark, cid, detail))
        if fix and ok is not True:
            lines.append("    → " + fix)
    dm = dev_mode()
    lines += ["", "  modo dev en esta máquina: %s" % (
        "ON" if dm else ("OFF" if dm is False else "sin marker (se infiere de la rama)")),
        "  (activar: workspace dev setup --enable · desactivar: --disable)", "",
        "  Contribuir:",
        "    1. workspace feature <nombre>        rama propia desde main",
        "    2. python tests/run.py <módulo>      checks mientras iteras (HOME aislado)",
        "    3. python tests/run.py               suite completa antes de cerrar",
        "    4. workspace integrate               merge local suite-gated (revisión)",
        "  Contrato: ARCHITECTURE.md · engines/CONTRACT.md · engines/PORTABILITY.md",
        "  La instalación de cliente NO se toca: el checkout dev es otra carpeta."]
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--enable" in argv or "--disable" in argv:
        set_dev_mode("--enable" in argv)
        print("modo dev: %s (marker %s)" % ("ON" if "--enable" in argv else "OFF", marker_path()))
        return 0
    rows = checks()
    print(report(rows))
    return 0 if all(ok is not False for _c, ok, _d, _f in rows) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
