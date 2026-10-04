#!/usr/bin/env python3
"""WORKSPACE · proyectos_demo — abre la UI v2 (F6) contra un HOME DESECHABLE.

Para que el socio PRUEBE la app v2 (pestañas por agente · historial por día · handoff ·
archivos) sin tocar ni migrar su data real:

  1. crea un HOME temporal (en /tmp),
  2. COPIA ahí su `proyectos.json` real (solo lectura del original),
  3. corre la migración v1→v2 sobre la COPIA,
  4. siembra un poco de demo (2 hilos de agente en 2 días, un handoff, un archivo),
  5. levanta el server v2 y abre el navegador.

Su `~/.claude` real NO se toca. Al cerrar (Ctrl-C) el sandbox queda en /tmp (el
SO lo limpia); nada permanente. La migración REAL + el merge los hace el socio cuando
decida (este script es solo para probar el borrador de la rama).

Uso:
    python3 proyectos_demo.py               # puerto 9137
    python3 proyectos_demo.py --port 9200
"""
import datetime
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _real_source():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "proyectos", "proyectos.json")


def _seed(fs):
    """Un poco de contenido v2 para que se vea vivo: hilos de zenith/atlas en 2
    días, un handoff y un archivo — en el 1er proyecto migrado."""
    st = fs.load()
    if not st["projects"]:
        return None, None
    p = st["projects"][0]
    pid = p["id"]
    root = next(n for n in p["nodes"] if n["root"])["id"]
    fs.set_resumen(pid, root,
                   "## Handoff del nodo raíz\n\nEstado: demo v2 lista para "
                   "revisión.\nPendientes: clicar pestañas, subir un archivo, "
                   "navegar el historial por día.\nArchivos: ver la lista abajo.")
    hoy = datetime.date.today().isoformat()
    ayer = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    def seed(agent, dia, turns):
        d = fs.sesiones_agent_dir(pid, root, agent)
        os.makedirs(d, exist_ok=True)
        body = "# Sesión — %s · %s\n\n" % (agent, dia)
        for i, (role, text) in enumerate(turns):
            body += "<!--turn role=%s ts=%sT12:00:0%d-->\n%s\n\n" % (role, dia, i, text)
        with open(os.path.join(d, dia + ".md"), "w", encoding="utf-8") as fh:
            fh.write(body)

    seed("zenith", ayer, [("user", "¿por dónde empiezo este nodo?"),
                          ("assistant", "Arranca por el resumen; el plan queda en el handoff.")])
    seed("zenith", hoy, [("user", "seguimos hoy"),
                         ("assistant", "Cerré el punto 2, falta el 3.")])
    seed("atlas", hoy, [("user", "atlas, resume la investigación"),
                        ("assistant", "Tres fuentes clave, todas apuntan a lo mismo.")])
    fs.save_file(pid, root, "notas-demo.txt",
                 b"Archivo de ejemplo del nodo. Se baja como attachment.")
    return p["name"], pid


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    dev = "--dev" in argv                 # embebe la app como SECCIÓN del dev panel
    port = "9121" if dev else "9137"
    if "--port" in argv:
        try:
            port = str(int(argv[argv.index("--port") + 1]))
        except Exception:
            pass

    sandbox = os.path.join(tempfile.mkdtemp(prefix="proyectos-v2-demo-"), "home")
    pdir = os.path.join(sandbox, ".claude", "workspace", "proyectos")
    os.makedirs(pdir, exist_ok=True)

    src = _real_source()
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(pdir, "proyectos.json"))
        origen = "copia de tu proyectos.json real (%d proyectos)" % _count(src)
    else:
        origen = "sin data real — arranca vacío"

    # HOME al sandbox ANTES de tocar el almacén (fsstore/migrate leen HOME por
    # llamada, no lo cachean al importar).
    os.environ["HOME"] = sandbox
    os.environ["USERPROFILE"] = sandbox

    import proyectos_migrate as mig
    import proyectos_fsstore as fs
    if os.path.isfile(os.path.join(pdir, "proyectos.json")):
        mig.migrate(apply=True, out=lambda *a, **k: None)
    name, _pid = _seed(fs)

    url = "http://127.0.0.1:%s" % port
    print("\n  ── DEMO v2 (borrador de la rama feat/proyectos-v2) ──")
    print("  HOME desechable: %s" % sandbox)
    print("  Origen: %s" % origen)
    print("  Tu ~/.claude REAL no se toca.")
    if dev:
        print("  Modo DEV PANEL: en el panel, abre la sección «Proyectos»")
        print("  (barra lateral) — ahí vive la app v2 embebida con la data demo.")
    elif name:
        print("  Abre el proyecto «%s» → nodo raíz: verás pestañas (zenith/atlas),"
              % name)
        print("  historial por día, el handoff y un archivo para descargar.")
    print("  URL: %s     (Ctrl-C para parar)\n" % url)
    sys.stdout.flush()

    # el server en su propio proceso, con HOME=sandbox; abre el navegador solo.
    # --dev → el dev panel (dashboard.py --dev), con la app como sección «Proyectos».
    env = dict(os.environ)
    cmd = ([sys.executable, os.path.join(ROOT, "dashboard.py"), "--dev", "--port", port]
           if dev else
           [sys.executable, os.path.join(ROOT, "proyectos.py"), "--port", port])
    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        pass
    print("\n  demo detenida. El sandbox en /tmp lo limpia el sistema.\n")
    return 0


def _count(path):
    try:
        import json
        with open(path, encoding="utf-8") as fh:
            return len(json.load(fh).get("projects", []))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
