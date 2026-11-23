#!/usr/bin/env python3
"""Genera `skills_puertas_nuevas.json`: cada versión ANTERIOR de las cuatro
skills de la guía (configurar-workspace, personalizar-workspace,
reparar-workspace y calendario-y-tareas), tal como estaba en la plantilla
(templates/agent/brain/skills/meta/<skill>/SKILL.md, con sus marcadores
{{X}}), en el orden del historial de git (la más vieja primero).

Lo usa `skills_puertas_nuevas.py` (migración 202611221218_skills_puertas_nuevas,
cargar un agente y `workspace doctor --fix`): una copia del cerebro se cambia
por la versión actual de la plantilla SOLO si es, byte por byte, una de estas
versiones con sus marcadores llenos (los mismos valores en cada uno). Lo que
el socio editó no se toca.

Entra cada contenido distinto del historial de esas rutas, menos el de la
plantilla actual (del disco). Si la plantilla cambia otra vez, la versión que
hoy es la actual pasa a la lista al regenerar.

Corre solo en el repo de desarrollo (necesita git). Uso:
    python3 migrations/data/gen_skills_puertas_nuevas.py [--check]
(--check: verifica que el JSON del disco sea el que se generaría.)
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills_puertas_nuevas.json")
BASE = "templates/agent/brain/"
RELS = (
    "skills/meta/configurar-workspace/SKILL.md",
    "skills/meta/personalizar-workspace/SKILL.md",
    "skills/meta/reparar-workspace/SKILL.md",
    "skills/meta/calendario-y-tareas/SKILL.md",
)


def git(*args):
    p = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True)
    return p.stdout.decode("utf-8") if p.returncode == 0 else ""


def versiones(rel):
    """Los contenidos distintos de `rel` en el historial (el más viejo primero), sin el de la plantilla actual."""
    with open(os.path.join(ROOT, BASE, rel), encoding="utf-8", newline="") as fh:
        actual = fh.read()
    out = []
    for commit in reversed(git("log", "--format=%H", "--", BASE + rel).split()):
        texto = git("show", "%s:%s%s" % (commit, BASE, rel))
        if texto and texto != actual and texto not in out:
            out.append(texto)
    return out


def generar():
    return {rel: versiones(rel) for rel in RELS}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not git("log", "-1", "--format=%h"):
        # sin la historia de git (instalación de cliente) NO se regenera: una
        # lista vacía apagaría la migración en silencio.
        sys.exit("sin historia de git: el JSON no se toca")
    tabla = generar()
    vacias = [rel for rel, vs in tabla.items() if not vs]
    if vacias:
        print("\n".join("✗ sin versiones anteriores: " + rel for rel in vacias))
        return 1
    out = {"_doc": "Generado por gen_skills_puertas_nuevas.py desde el historial de templates/agent/brain. "
                   "Por skill, sus versiones anteriores (la más vieja primero), con sus marcadores {{X}}.",
           "skills": tabla}
    texto = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if "--check" in argv:
        try:
            with open(DEST, encoding="utf-8", newline="") as fh:
                igual = fh.read() == texto
        except OSError:
            igual = False
        print("✓ al día" if igual else "✗ el JSON del disco no es el que se generaría")
        return 0 if igual else 1
    with open(DEST, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)
    print("skills: %d · versiones anteriores: %d → %s" % (len(tabla), sum(len(v) for v in tabla.values()), DEST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
