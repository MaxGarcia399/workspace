#!/usr/bin/env python3
"""Genera `legacy_template_lines.json`: las líneas con el NOMBRE ANTERIOR del
producto (`legacy.NAME`) que traían las versiones VIEJAS del template de
cerebro (antes del renombre 9e5b797, 2026-10-04) y su versión renombrada. Lo
usa la migración 202610151600_brain_identity_neutral para limpiar cerebros de
clientes creados con esos templates SIN tocar lo que el cliente haya editado.

Cómo: para cada archivo, empareja línea a línea la última versión previa al
renombre (8fa2a0e) con la del commit del renombre (9e5b797) usando difflib.
Solo entran pares cuya línea vieja contiene el nombre anterior (sin importar
mayúsculas). Una línea de una versión más vieja del template solo se cubre si
es IDÉNTICA a una de 8fa2a0e (así su reemplazo está definido); las que
cambiaron de forma irregular entre versiones se dejan. Corre solo en el repo
de desarrollo (necesita git); el JSON resultante viaja con la migración.

Uso:  python3 migrations/data/gen_legacy_template_lines.py
"""
import difflib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import legacy  # noqa: E402

PRE, POST = "8fa2a0e", "9e5b797"
BASE = "templates/agent/brain/"
#: Registros HISTÓRICOS del cerebro: no se reescriben aunque su línea venga del
#: template (regla del dueño: la historia no se edita; «nació del template de la
#: instalación anterior» fue cierto). Solo se actualizan instrucciones.
HISTORY = {"STATE/log-recent.md", "STATE/brain-version.md", "STATE/MILESTONES.md"}
#: 02-TEAM.md del template es el del EQUIPO: make-dist.sh lo reemplaza por un
#: placeholder, así que ningún cerebro de cliente trae esas líneas, y copiarlas
#: aquí metería nombres internos en un archivo que SÍ viaja (gate LEAK).
NOT_SHIPPED = {"BOOT/02-TEAM.md"}


def git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True,
                          text=True, encoding="utf-8").stdout


def files(rev):
    return [p for p in git("ls-tree", "-r", "--name-only", rev, "--", BASE).splitlines()
            if p.endswith(".md")]


def lines(rev, path):
    out = git("show", "%s:%s" % (rev, path))
    return out.splitlines() if out else []


def has_old_name(line):
    return legacy.NAME_LOWER in line.lower()


def main():
    entries = {}
    if not files(PRE) or not files(POST):
        # sin la historia de git (p.ej. en una instalación de cliente) NO se
        # regenera: escribir una tabla vacía apagaría el renombre en silencio.
        sys.exit("sin historia de git (%s/%s): la tabla no se toca" % (PRE, POST))
    post_files = set(files(POST))
    for path in files(PRE):
        rel = path[len(BASE):]
        if rel in HISTORY or rel in NOT_SHIPPED:
            continue
        a = lines(PRE, path)
        b = lines(POST, path) if path in post_files else []
        if not b:
            continue
        pairs = {}
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace" and (i2 - i1) == (j2 - j1):
                for k in range(i2 - i1):
                    old, new = a[i1 + k], b[j1 + k]
                    if has_old_name(old) and old != new:
                        pairs[old] = new
        if not pairs:
            continue
        entries[rel] = [{"old": o, "new": n} for o, n in sorted(pairs.items())]
    out = {"_doc": "Generado por gen_legacy_template_lines.py desde git (%s → %s). "
                   "Placeholders {{X}} se comparan como comodín; el resto, literal." % (PRE, POST),
           "files": entries}
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legacy_template_lines.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    n = sum(len(v) for v in entries.values())
    print("archivos: %d · líneas: %d → %s" % (len(entries), n, dest))


if __name__ == "__main__":
    main()
