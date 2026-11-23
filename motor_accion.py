#!/usr/bin/env python3
r"""WORKSPACE · motor_accion — Motores › Cuenta / Iniciar sesión / Reparar / Instalar desde el hub, SIN la pantalla de
Motores de antes (I09: engines_tui.run caía en su `_loop` al volver del programa oficial).

    python3 motor_accion.py <motor> <account|login|repair|install> [activa|sin-sesion]

Lo mismo que hace la página en su pestaña (localhost_sistema: los comandos salen SOLO de engine_install y del adapter,
y se corren con engines_tui.execute), en esta terminal y en pocas líneas:
  · el título (el motor y la acción) y los comandos tal cual se van a correr;
  · lo que hay que confirmar (instalar, reinstalar, reparar, cambiar de cuenta): Enter sigue, Esc o q no;
  · «Cuenta y proveedor» con el menú del adapter (Kiro, Copilot, Cursor…): sus opciones numeradas;
  · el programa oficial, con su salida a la vista (Workspace no la lee);
  · lo que pasó de verdad (engines_tui.outcome) y «Enter para volver al hub», que vuelve a Motores y lo revisa.
Las mismas palabras que la página (lang/<idioma>/localhost.py: localhost.sistema.*). → 0 hecho · 1 no se pudo ·
130 cancelado. Stdlib."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

#: La acción que pide el hub (la de engines_tui por su CLI) → la de la página. «repair» depende del motor.
ACCIONES = {"account": "cuenta", "login": "iniciar_sesion", "install": "instalar", "repair": "reparar"}
#: Lo que se confirma con Enter antes de correr (como la página: localhost_sistema._CONFIRMAR, y cambiar de cuenta).
CONFIRMAR = ("instalar", "actualizar", "reinstalar", "reparar")


def _t(clave, es, **kw):
    try:
        import i18n
        s = i18n.t(clave, **kw)
        if isinstance(s, str) and s and s != clave:
            return s
    except Exception:
        pass
    return es.format(**kw) if kw else es


def _LS():
    import localhost_sistema
    return localhost_sistema


def _ET():
    """La lógica de Motores sin pantalla: motores_logica (la saca la rama de la tarjeta de engines_tui, que la
    re-exporta); mientras no esté en esta copia, engines_tui como biblioteca (nunca su pantalla)."""
    try:
        import motores_logica as ET
    except ImportError:
        import engines_tui as ET
    return ET


def accion_de(motor, accion):
    """La acción de la página para `accion` del hub. «repair»: «reparar» si la instalación quedó a medias
    (install_block), si no «reinstalar» (macOS lo retiene: gatekeeper) — lo mismo que engines_tui."""
    a = ACCIONES.get(accion)
    if accion == "repair":
        try:
            a = "reparar" if _ET().install_block(motor) else "reinstalar"
        except Exception:
            a = "reparar"
    return a


def _tecla(entrada=None):
    """Una línea de la terminal (Enter = ""; None si no hay terminal o se cortó)."""
    try:
        return (entrada or input)("")
    except (EOFError, KeyboardInterrupt):
        return None


def _confirma(out, entrada=None):
    out("  " + _t("puertas.motor.confirmar", "Enter para seguir · q y Enter para no hacer nada"))
    r = _tecla(entrada)
    return r is not None and r.strip().lower() not in ("q", "n", "no", "esc", "\x1b")


def correr(motor, accion, sesion=None, out=None, entrada=None, ejecutar=None):
    """Lo de arriba. `out`/`entrada`/`ejecutar` (engines_tui.execute): las pruebas los cambian. → código."""
    out = out or (lambda s: (sys.stdout.write(s + "\n"), sys.stdout.flush()))
    LS = _LS()
    ET = _ET()
    a = accion_de(motor, accion)
    if not a:
        out("\n  " + _t("puertas.motor.no_se", "No sé hacer «{a}» con un motor.", a=accion))
        return 1
    d = LS._fila(motor)
    if d is None:
        out("\n  " + _t("puertas.motor.no_esta", "Workspace no conoce el motor «{m}».", m=motor))
        return 1
    nombre = ET.engine_name(d)
    activa = {"activa": True, "sin-sesion": False}.get(sesion or "")
    if activa is None:
        activa = LS._activa(LS._estado(), motor)
    opcion = ""
    out("\n  " + nombre + " · " + LS._etiqueta_accion(a, "", motor))
    if a == "cuenta":
        c = LS.motor_cuenta(motor)
        if not c.get("ok"):
            out("\n  " + str(c.get("mensaje") or ""))
            return 1
        if c.get("menu"):
            acciones = c.get("acciones") or []
            if c.get("nota"):
                out("  " + c["nota"])
            if c.get("aviso"):
                out("  " + c["aviso"])
            for i, x in enumerate(acciones, 1):
                out("    %d  %s" % (i, x.get("etiqueta") or x.get("clave")))
            out("  " + _t("puertas.motor.elige", "Escribe su número y Enter (Enter solo: no hacer nada)."))
            r = _tecla(entrada)
            if not r or not r.strip().isdigit() or not 1 <= int(r.strip()) <= len(acciones):
                out("  " + _t("puertas.motor.cancelado", "Listo: no hice nada."))
                return 130
            opcion = acciones[int(r.strip()) - 1]["clave"]
    prep = LS.motor_preparar(motor, a, opcion)
    if not prep.get("ok"):
        out("\n  " + str(prep.get("mensaje") or ""))
        return 1
    for linea in prep.get("comandos") or []:
        out("    " + linea)
    for k in ("aviso", "nota"):
        if prep.get(k):
            out("  " + prep[k])
    if (a in CONFIRMAR or opcion == "switch") and not _confirma(out, entrada):
        out("  " + _t("puertas.motor.cancelado", "Listo: no hice nada."))
        return 130
    pedido, e = LS._pedido(a, motor, opcion, activa)
    if e:
        out("\n  " + LS._t("localhost.sistema.err." + e[0], **e[2]))
        return 1
    clase, cmd, opts = pedido
    rc, problema, listo = (ejecutar or ET.execute)(clase, motor, cmd, opts)
    clave, detalle = ET.outcome(clase, motor, rc, problema, listo)
    out("\n  " + LS._mensaje_final(motor, clave, detalle))
    return 0 if clave in ("installed", "done") else 1


def delegada(motor, accion):
    """Instalar y entrar los corre la lógica de Motores sin pantalla (motores_logica.correr_accion, de la rama de la
    tarjeta: corre el comando oficial, dice qué pasó y espera Enter), si está en esta copia. → su código, o None si
    no está (lo corre `correr`, aquí)."""
    if accion not in ("install", "login"):
        return None
    try:
        import motores_logica
    except ImportError:
        return None
    fn = getattr(motores_logica, "correr_accion", None)
    if not callable(fn):
        return None
    rc = fn(accion, motor)
    return rc if isinstance(rc, int) else 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("uso: motor_accion.py <motor> <account|login|repair|install> [activa|sin-sesion]")
        return 2
    try:
        rc = delegada(argv[0], argv[1])
    except KeyboardInterrupt:
        return 130
    if rc is not None:
        return rc
    try:
        rc = correr(argv[0], argv[1], argv[2] if len(argv) > 2 else None)
    except KeyboardInterrupt:
        rc = 130
    try:
        if sys.stdin.isatty():
            input("\n  " + _t("puertas.motor.volver", "Enter para volver al hub") + " ")
    except (EOFError, KeyboardInterrupt, OSError, ValueError):
        pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
