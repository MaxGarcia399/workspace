#!/usr/bin/env python3
"""WORKSPACE · selftest — «¿arranca esta versión en ESTA máquina?»

Lo corre el actualizador justo después de traer código nuevo, en un proceso
NUEVO (con el código nuevo) y con el MISMO Python del usuario. Si falla, el
actualizador vuelve a la versión anterior y la deja fijada hasta que llegue
otra más nueva (patrón de Try Omarchy: conservar lo anterior hasta comprobar
que lo nuevo arranca).

Qué revisa (solo lectura, sin red, sin escribir nada):
  1. Que TODO el código del producto compile con el Python de esta máquina.
     Atrapa el caso más probable en computadoras ajenas: alguien usó sintaxis
     de un Python más nuevo que el del cliente (p. ej. 3.9).
  2. Que los módulos centrales importen (rutas, ajustes, idioma, registro de
     agentes, lanzador, doctor, instalador, hub, actualizador, migraciones).
  3. Que el estado existente de la máquina se pueda LEER con el código nuevo
     (ajustes y registro de agentes), sin modificarlo.

Salida: una línea por problema y exit 1, o "selftest ok …" y exit 0.
`--json` imprime el resultado estructurado. Stdlib, Python 3.9+.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# Carpetas que NO son código del producto que corre en el cliente.
_SKIP_DIRS = {"__pycache__", ".git", "tests", "research", "vendor", "node_modules",
              "_shelved", "evals", "office-design", "banner", "brand",
              "venv", ".venv", "env", "site-packages"}

# Módulos que tienen que importar sí o sí para que Workspace arranque.
CORE_MODULES = ("paths", "settings", "i18n", "agentsreg", "brain_resolver",
                "dispatch", "install", "doctor", "migrate", "updater", "front")


def _git_py_files(root):
    """Archivos .py VERSIONADOS (lo que trae una actualización). None si no
    hay git: entonces se recorre la carpeta (instalación por zip/sync)."""
    if not os.path.exists(os.path.join(root, ".git")):
        return None
    try:
        import subprocess
        r = subprocess.run(["git", "-C", root, "ls-files", "-z", "--", "*.py"],
                           capture_output=True, timeout=30)
        if r.returncode != 0:
            return None
        rels = [x for x in r.stdout.decode("utf-8", "replace").split("\0") if x]
    except Exception:
        return None
    out = []
    for rel in rels:
        parts = rel.split("/")
        if any(p in _SKIP_DIRS or p.startswith(".") for p in parts[:-1]):
            continue
        full = os.path.join(root, *parts)
        if os.path.isfile(full):
            out.append(full)
    return out


def _py_files(root):
    tracked = _git_py_files(root)
    if tracked is not None:
        for p in tracked:
            yield p
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in _SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def check_compile(root=ROOT):
    """[(ruta_relativa, error)] de los archivos que no compilan."""
    bad = []
    n = 0
    for path in _py_files(root):
        n += 1
        try:
            with open(path, "rb") as fh:
                src = fh.read()
            compile(src, path, "exec", dont_inherit=True)
        except SyntaxError as e:
            bad.append((os.path.relpath(path, root),
                        "SyntaxError línea %s: %s" % (e.lineno, e.msg)))
        except Exception as e:
            bad.append((os.path.relpath(path, root), "%s: %s" % (type(e).__name__, e)))
    return n, bad


def check_imports(modules=CORE_MODULES):
    bad = []
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    for name in modules:
        try:
            __import__(name)
        except BaseException as e:          # SystemExit incluido: un import no debe salir
            bad.append((name, "%s: %s" % (type(e).__name__, e)))
    return bad


def check_state():
    """Lee (sin escribir) el estado de la máquina con el código nuevo."""
    bad = []
    try:
        import settings
        settings.get("ui.lang", "es")
    except Exception as e:
        bad.append(("ajustes", "%s: %s" % (type(e).__name__, e)))
    try:
        import dispatch
        reg = dispatch.load_registry()
        if not isinstance(reg, dict):
            bad.append(("registro de agentes", "formato inesperado"))
    except Exception as e:
        bad.append(("registro de agentes", "%s: %s" % (type(e).__name__, e)))
    return bad


def run(root=ROOT):
    # Nada de lo que importemos debe disparar un auto-update ni red.
    os.environ["WORKSPACE_NO_AUTOUPDATE"] = "1"
    os.environ["WORKSPACE_NO_AUTORENDER"] = "1"
    os.environ["WORKSPACE_SELFTEST"] = "1"
    n, comp = check_compile(root)
    imps = check_imports() if not comp else []
    state = check_state() if not (comp or imps) else []
    problems = ([("compilar " + p, e) for p, e in comp]
                + [("importar " + m, e) for m, e in imps]
                + [("leer " + w, e) for w, e in state])
    return {"ok": not problems, "files": n,
            "python": "%d.%d.%d" % sys.version_info[:3],
            "problems": [{"where": w, "error": e} for w, e in problems]}


def main(argv=None):
    args = list(argv if argv is not None else sys.argv[1:])
    try:                                    # consola Windows capturada = cp1252
        sys.path.insert(0, ROOT)
        import _utf8
        _utf8.harden()
    except Exception:
        pass
    res = run()
    if "--json" in args:
        print(json.dumps(res, ensure_ascii=False))
    elif res["ok"]:
        print("selftest ok (%d archivos · Python %s)" % (res["files"], res["python"]))
    else:
        for p in res["problems"]:
            print("✗ %s — %s" % (p["where"], p["error"]))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
