#!/usr/bin/env python3
"""WORKSPACE · arquitectura/reporte_global — lo que Workspace escribió en la config global de los motores (F7).

    python3 -m arquitectura.reporte_global [--json]

SOLO LEE Y LISTA: la limpieza (la migración que saca eso, con respaldo y deshacer) se decide aparte. Dos fuentes:

  · lo que Workspace dejó fuera de los cerebros y sabe reconocer por sus marcas (uninstall.plan_clean_all, que
    solo lee: el plan de `--limpiar-todo`), con lo que se dejaría por estar cambiado a mano;
  · la config global de cada motor según su ficha (`config_global`), con la huella del probador (tamaño y
    sha256; nunca el contenido), para comparar contra una máquina limpia o contra la próxima corrida.
Stdlib."""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)


def _dentro(ruta, raices):
    r = os.path.realpath(os.path.abspath(os.path.expanduser(str(ruta))))
    return any(r == b or r.startswith(b + os.sep) for b in raices)


def reporte(cerebros=None, home=None):
    """{"de_workspace": [{que, ruta, tipo}], "a_mano": [rutas], "motores": {motor: [{ruta, existe, tam?, sha256?}]}}.
    `cerebros` = [(nombre, carpeta)] (por defecto, los que conoce Workspace)."""
    import uninstall
    from arquitectura import contrato, probador
    home = home or os.path.expanduser("~")
    if cerebros is None:
        cerebros = uninstall.brains()
    raices = [os.path.realpath(os.path.abspath(os.path.expanduser(b))) for _n, b in cerebros]
    items, editados = uninstall.plan_clean_all(cerebros)
    out = {"de_workspace": [{"que": t, "ruta": r, "tipo": tipo} for t, r, tipo, _accion in items
                            if not _dentro(r, raices)],
           "a_mano": sorted(str(r) for r in (editados or ()) if not _dentro(r, raices)),
           "motores": {}}
    for motor, f in contrato.fichas().items():
        filas = []
        for ruta, h in sorted(probador.huella(f.get("config_global") or [], {"home": home}).items()):
            fila = {"ruta": ruta, "existe": h is not None}
            if h and "tam" in h:
                fila.update(tam=h["tam"], sha256=h["sha256"][:16])
            filas.append(fila)
        out["motores"][motor] = filas
    return out


def texto(r):
    lineas = ["Lo que Workspace escribió en la config global (solo lectura; la limpieza se decide aparte):"]
    lineas += ["  · %s — %s" % (x["que"], x["ruta"]) for x in r["de_workspace"]] or ["  (nada que reconozca)"]
    if r["a_mano"]:
        lineas += ["Cambiado a mano después (se dejaría):"] + ["  · %s" % x for x in r["a_mano"]]
    lineas.append("La config global de cada motor (huella del probador: tamaño y sha256):")
    for motor, filas in r["motores"].items():
        hay = [f for f in filas if f["existe"]]
        lineas.append("  %s: %d de %d %s" % (motor, len(hay), len(filas), "existen" if len(hay) != 1 else "existe"))
        lineas += ["      %s (%s B, %s)" % (f["ruta"], f.get("tam", "?"), f.get("sha256", "?")) for f in hay]
    return "\n".join(lineas)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    r = reporte()
    print(json.dumps(r, ensure_ascii=False, indent=2) if "--json" in argv else texto(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
