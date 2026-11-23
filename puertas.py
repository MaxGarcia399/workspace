#!/usr/bin/env python3
r"""WORKSPACE · puertas — las pantallas de antes ya no se abren (versión 1 de 2: aquí se cierran las puertas; los
archivos se borran en la siguiente).

Lo que queda para quien todavía llega por un camino viejo:
  · `cerrada(que)`: la línea que dice dónde vive ahora lo que buscabas (un script viejo corrido directo, un hub que
    se quedó abierto durante la actualización y lanza una pantalla por su ruta, un subcomando sin pantalla);
  · `variables_viejas(env)`: las variables de antes (WORKSPACE_HUB_VIEJO, WORKSPACE_HUB_PIEL=bloque…) ya no hacen
    nada en una instalación de cliente; el hub lo dice una vez, en una línea;
  · `dev()`: ¿es una copia de desarrollo? (trae el panel de dev, que make-dist no embarca). Solo ahí las variables
    viejas siguen abriendo lo de antes, para comparar.
Todo texto con su clave ES/EN (lang/<idioma>/puertas.py) y el español de red. Stdlib."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def _t(clave, es, **kw):
    try:
        import i18n
        s = i18n.t(clave, **kw)
        if isinstance(s, str) and s and s != clave:
            return s
    except Exception:
        pass
    try:
        return es.format(**kw)
    except (KeyError, IndexError, ValueError):
        return es


def dev():
    """¿Copia de desarrollo? (el panel de dev viaja solo aquí: make-dist lo quita.) Ante la duda, no."""
    try:
        return os.path.isfile(os.path.join(ROOT, "dashboard-dev.html"))
    except Exception:
        return False


#: Las pantallas que se cerraron → dónde vive hoy lo suyo (clave del texto, español de red).
DESTINOS = {
    "agregar": ("puertas.destino.agregar", "«+ Agregar» en el hub (Inicio, o al pie de tus agentes)"),
    "agentes": ("puertas.destino.agentes", "Agentes, en el hub (`workspace agentes`)"),
    "motores": ("puertas.destino.motores", "Motores, en el hub"),
    "actualizaciones": ("puertas.destino.actualizaciones", "Ajustes › Actualizaciones, en el hub (o `workspace update`)"),
    "comandos": ("puertas.destino.comandos", "Ayuda › Comandos, en el hub (`workspace comandos`)"),
    "conexiones": ("puertas.destino.conexiones", "Ajustes › Conexiones, en el hub (`workspace conexiones`)"),
    "tono": ("puertas.destino.tono", "Agentes › Tono, en el hub (`workspace tono`)"),
    "calendario": ("puertas.destino.calendario", "Calendario, en el hub (`workspace calendario`)"),
    "usuarios": ("puertas.destino.usuarios", "Ajustes › Usuarios, en el hub"),
    "docs": ("puertas.destino.docs", "Ayuda › Documentación, en el hub"),
    "decisores": ("puertas.destino.decisores", "Motores, en el hub"),
    "modelos": ("puertas.destino.modelos", "Motores, en el hub"),
    "primer_arranque": ("puertas.destino.primer_arranque", "el hub: abre `workspace` y agrega tu primer agente"),
    "hub": ("puertas.destino.hub", "el hub: escribe `workspace`"),
}


def destino(que):
    clave, es = DESTINOS.get(que, DESTINOS["hub"])
    return _t(clave, es)


def cerrada(que):
    """La línea para quien llega a una pantalla que ya no está: dónde vive ahora."""
    return _t("puertas.cerrada", "Esa pantalla ya no está en esta versión de Workspace. Ahora: {donde}.",
              donde=destino(que))


def reinicia():
    """Para un hub que se quedó abierto durante la actualización y lanza una pantalla de antes por su ruta."""
    return _t("puertas.reinicia", "Si tenías el hub abierto, ciérralo y ábrelo de nuevo (escribe `workspace`).")


def avisar(que, esperar=True, salida=None):
    """Imprime `cerrada(que)` y, con terminal, espera Enter (para que se lea antes de volver a donde estabas).
    → 0 (no es un error: solo cambió de lugar)."""
    out = salida or sys.stdout
    try:
        out.write("\n  " + cerrada(que) + "\n  " + reinicia() + "\n")
        out.flush()
    except (OSError, ValueError):
        return 0
    if esperar:
        try:
            if sys.stdin.isatty() and out.isatty():
                input("  " + _t("puertas.enter", "Enter para seguir") + " ")
        except (EOFError, KeyboardInterrupt, OSError, ValueError):
            pass
    return 0


#: Las variables de antes y el valor que abría lo viejo. En una instalación de cliente ya no hacen nada.
VARIABLES = (
    ("WORKSPACE_HUB_VIEJO", "1", "puertas.var.lanzador", "el lanzador de antes"),
    ("WORKSPACE_HUB_DIRECTO", "0", "puertas.var.paleta", "el hub «Paleta»"),
    ("WORKSPACE_HUB_PIEL", "bloque", "puertas.var.bloque", "la piel «Bloque»"),
    ("WORKSPACE_MONITOS", "paleta", "puertas.var.monitos", "los monitos «paleta»"),
    ("WORKSPACE_HUB_S1", "0", "puertas.var.s1", "el menú de sesiones de antes"),
)


def variable(nombre, env=None):
    """¿La variable vieja `nombre` está puesta con el valor que abría lo de antes, Y esta es una copia de desarrollo?
    Solo entonces se respeta (para comparar). En una instalación de cliente, nunca."""
    env = os.environ if env is None else env
    val = next((v for n, v, _c, _e in VARIABLES if n == nombre), None)
    return val is not None and str(env.get(nombre) or "").strip().lower() == val and dev()


def variables_viejas(env=None):
    """La línea (una sola) para las variables de antes que están puestas y ya no hacen nada; '' si ninguna. En una
    copia de desarrollo no se dice nada: ahí siguen funcionando."""
    env = os.environ if env is None else env
    if dev():
        return ""
    puestas = [n for n, v, _c, _e in VARIABLES if str(env.get(n) or "").strip().lower() == v]
    if not puestas:
        return ""
    return _t("puertas.var.aviso", "{vars} ya no cambia nada: Workspace abre siempre el hub nuevo.",
              vars=", ".join(puestas))


def redirigir(que, argv=(), salida=None):
    """El ARCHIVO MÍNIMO de una pantalla de antes (su bloque __main__ por una versión; se borra en la versión 2): quien
    la corre directo, o un hub que se quedó abierto durante la actualización y la lanza por su ruta, llega a lo nuevo:
      · «agregar» → la tarjeta «Agregar agente» (hub_agregar.correr, de su rama); sin ella, la línea de dónde está;
      · «motores» con <motor> <acción> → esa acción sin la pantalla de antes (motor_accion);
      · lo demás → la línea de dónde vive ahora (y Enter). → código de salida."""
    argv = list(argv or [])
    if que == "agregar":
        try:
            import hub_agregar
        except ImportError:
            hub_agregar = None
        if hub_agregar is not None and callable(getattr(hub_agregar, "correr", None)):
            rc = hub_agregar.correr("crear")
            return rc if isinstance(rc, int) else 0
    if que == "motores" and len(argv) >= 2:
        import motor_accion
        return motor_accion.main(argv[:3])
    return avisar(que, salida=salida)


# ── instalaciones por sync (sin git): lo que ya no viaja y se quedó en la carpeta ─────────────────────────────────────
#: Lo que la entrega de un cliente NO trae (make-dist lo quita: herramientas y comparaciones de desarrollo). En una
#: copia por sync (sin .git) que lo tenga, sobra: con dashboard-dev.html, por ejemplo, la copia se cree de desarrollo
#: y las puertas de antes vuelven (dev()). tests/test_puertas_viejas lo cruza con make-dist.sh.
SOLO_DESARROLLO = ("puertas_dev.py", "dashboard-dev.html", "dev_tui.py", "comandos_dev.py", "maquinas_dev.py",
                   "prototipo_conversaciones.py", "vigia_aviso.py", "skill_audit.py", "skill_loop.py", "bus_daemon.py",
                   "migrate_chat_identity.py", "make-dist.sh", "test-onboarding.sh")
#: Las pantallas de antes que una versión ya borró (versión 2 del plan: aquí van sus archivos). Hoy, ninguna: esta
#: versión solo cierra sus puertas.
BORRADAS = ()


def restos(root=None):
    """Lo que sobra en una instalación por sync (sin .git) → [rutas relativas]; [] en un repo git (git se encarga)."""
    root = root or ROOT
    if os.path.exists(os.path.join(root, ".git")):
        return []
    return [rel for rel in SOLO_DESARROLLO + tuple(BORRADAS) if os.path.lexists(os.path.join(root, *rel.split("/")))]


def apartar(rels, root=None, estado=None, ahora=None):
    """Aparta lo que sobra (no lo borra): lo mueve a <estado>/backups/pantallas-retiradas/<fecha>/, con su misma ruta,
    y deja ahí un LEEME. Solo código de Workspace de esta carpeta: nada de tus cerebros ni de tus datos.
    → (apartados, a_donde)."""
    import shutil
    import time
    root = root or ROOT
    if estado is None:
        import paths
        estado = paths.state_dir()
    destino = os.path.join(estado, "backups", "pantallas-retiradas", time.strftime("%Y%m%d-%H%M%S",
                                                                                     time.localtime(ahora)))
    hechos = []
    for rel in rels:
        src = os.path.join(root, *rel.split("/"))
        if not os.path.lexists(src) or os.path.isdir(src) and not os.path.islink(src):
            continue
        dst = os.path.join(destino, *rel.split("/"))
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)
            os.remove(src)
            hechos.append(rel)
        except OSError:
            continue
    if hechos:
        try:
            with open(os.path.join(destino, "LEEME.txt"), "w", encoding="utf-8") as fh:
                fh.write(_t("puertas.doctor.leeme", "Workspace apartó estos archivos de {root}: ya no vienen en tu "
                            "versión (eran de desarrollo o de pantallas que se fueron). Para devolverlos, cópialos de "
                            "aquí a su lugar.", root=root) + "\n\n" + "\n".join(hechos) + "\n")
        except OSError:
            pass
    return hechos, destino
