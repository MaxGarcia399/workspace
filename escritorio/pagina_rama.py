#!/usr/bin/env python3
"""WORKSPACE · escritorio/pagina_rama — la página local de ESTA copia, aparte de la de siempre (la prende
escritorio/probar_rama.py): en otro puerto de 127.0.0.1, con una llave nueva, con tu estado de verdad y SIN anotarse en
<estado>/web/servidor.json (así no apaga ni reemplaza la tuya). Escribe su puerto y su llave en el archivo que le digan
(600) y se apaga con SIGTERM (cierra también los motores que encendió).

Su pagina.json es SUYO: al apagarse solo lo borra si todavía es el suyo (antes, la página vieja que se apagaba despacio
—cerrando sus motores— borraba el de la nueva, que ya estaba prendida: la nueva quedaba sin archivo y el monito y
`probar_rama.py estado` no la encontraban). Y si el archivo desaparece mientras está prendida, lo vuelve a escribir.

Anota en su salida (pagina.log, al lado) qué pasa en cada turno, para poder entender uno que se atora: lo que mandó
el monito (agente, canal, cuántas letras, con o sin lo que tenías enfrente), cada cambio que vio el monito en su foto
(estado, abriendo, permiso, pregunta, error, sin manos), las decisiones de una tarjeta y cualquier error de una ruta.
Nunca lo que escribiste ni lo que contestó.

    python3 escritorio/pagina_rama.py <ruta de pagina.json>
Stdlib."""
import inspect
import json
import os
import signal
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


def _resumen_foto(f):
    """Lo que se anota de una foto: qué cambió de lo que el monito pinta, sin texto de nadie."""
    f = f if isinstance(f, dict) else {}
    perm, preg, err = f.get("permiso"), f.get("pregunta"), f.get("error")
    return (("estado", f.get("estado")), ("abriendo", bool(f.get("abriendo"))),
            ("permiso", perm.get("id") if isinstance(perm, dict) else None),
            ("pregunta", preg.get("id") if isinstance(preg, dict) else None),
            ("error", (str(err.get("tipo") or "") + " " + str(err.get("texto") or ""))[:240].strip()
             if isinstance(err, dict) else None),
            ("sin_manos", bool(f.get("sin_manos"))))


def anotar_turnos(P, salida=None, reloj=time.time):
    """Envuelve las rutas de pagina_v2 que usa el monito para que la página diga qué pasó en cada turno (una línea por
    cosa, con la hora). Devuelve la función que escribe (para las pruebas)."""
    out = salida or sys.stderr
    visto, cerrojo = {}, threading.Lock()

    def linea(s):
        with cerrojo:
            out.write("%s %s\n" % (time.strftime("%H:%M:%S", time.localtime(reloj())), s))
            out.flush()

    def envolver(nombre, resumen):
        orig = getattr(P, nombre, None)
        if orig is None or getattr(orig, "_anotada", False):
            return
        firma = inspect.signature(orig)

        def f(*a, **k):
            try:
                r = orig(*a, **k)
            except Exception as e:
                linea("%s · falló: %s: %s" % (nombre, type(e).__name__, str(e)[:300]))
                raise
            try:
                arg = firma.bind(*a, **k)
                arg.apply_defaults()
                s = resumen(arg.arguments, r)
                if s:
                    linea(s)
            except Exception:
                pass
            return r
        f._anotada = True
        f.__wrapped__ = orig
        setattr(P, nombre, f)

    def de_vivo(a, r):
        canal = a.get("canal") or "navegador"
        cambios = []
        for aid, foto in ((r or {}).get("agentes") or {}).items():
            ahora = dict(_resumen_foto(foto))
            antes = visto.get((canal, aid))
            visto[(canal, aid)] = ahora
            if antes is None:
                if canal == "escritorio" or ahora["estado"] not in ("libre", "dormido", None):
                    cambios.append("%s: %s" % (aid, ", ".join("%s=%s" % kv for kv in ahora.items() if kv[1])))
                continue
            d = ["%s %s→%s" % (k, antes.get(k), v) for k, v in ahora.items() if antes.get(k) != v]
            if d:
                cambios.append("%s: %s" % (aid, ", ".join(d)))
        return ("vivo[%s] " % canal + " · ".join(cambios)) if cambios else ""

    def de_mandar(a, r):
        r = r if isinstance(r, dict) else {}
        return "mandar[%s] %s · %d letras%s → %s" % (
            a.get("canal") or "navegador", a.get("agente"), len(a.get("texto") or ""),
            " · con lo que tenías enfrente" if a.get("contexto") else "",
            "ok" if r.get("ok", True) and not r.get("error") else "no: %s" % str(r.get("error"))[:200])

    def de_decision(nombre):
        def s(a, r):
            r = r if isinstance(r, dict) else {}
            return "%s[%s] %s · %s%s → %s" % (
                nombre, a.get("canal") or "navegador", a.get("agente"), a.get("id") or "",
                (" · " + str(a.get("decision"))) if a.get("decision") else "",
                "ok" if r.get("ok", True) and not r.get("error") else "no: %s" % str(r.get("error"))[:200])
        return s

    envolver("vivo", de_vivo)
    envolver("mandar", de_mandar)
    envolver("permiso", de_decision("permiso"))
    envolver("responder", de_decision("responder"))
    envolver("parar", de_decision("parar"))
    return linea


def escribir(ruta, datos):
    """pagina.json, de una vez (600): o el de antes o el nuevo, nunca a medias."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = "%s.%d.tmp" % (ruta, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(datos, fh)
    os.replace(tmp, ruta)


def de_quien(ruta):
    """El pid que dice pagina.json, o 0 (no está o no se entiende)."""
    try:
        with open(ruta, encoding="utf-8") as fh:
            return int((json.load(fh) or {}).get("pid") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def _vivo(pid):
    """¿Vive ese proceso? Por control/hijos.vivo: en Windows `os.kill(pid, 0)` no pregunta (la señal 0 es
    CTRL_C_EVENT: un Ctrl+C a la consola); ahí va por la API de Windows."""
    try:
        from control import hijos
    except ImportError:
        hijos = None
    if hijos is not None:
        return bool(hijos.vivo(pid))
    if os.name == "nt":
        return False                    # sin poder saberlo sin señales: no se afirma
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False


def al_dia(ruta, datos):
    """Si pagina.json no está (o es de una página que ya no vive), lo vuelve a escribir. El de OTRA página viva no
    se toca. → True si lo escribió."""
    otro = de_quien(ruta)
    if otro == datos["pid"] or (otro and _vivo(otro)):
        return False
    escribir(ruta, datos)
    return True


def soltar(ruta, pid=None):
    """Al apagarse: borra pagina.json solo si todavía es el suyo. → True si lo borró."""
    if de_quien(ruta) != (pid or os.getpid()):
        return False
    try:
        os.remove(ruta)
        return True
    except OSError:
        return False


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    ruta = argv[0]
    import localhost_web as LW
    import pagina_v2
    linea = anotar_turnos(pagina_v2)
    srv = LW.crear_servidor(0)
    linea("página de esta copia: puerto %d · pid %d · %s" % (srv.server_address[1], os.getpid(), RAIZ))
    datos = {"puerto": srv.server_address[1], "llave": srv.llave, "pid": os.getpid(), "raiz": RAIZ}
    escribir(ruta, datos)

    def vigilar():
        while True:
            time.sleep(2.0)
            try:
                if al_dia(ruta, datos):
                    linea("pagina.json no estaba: lo volví a escribir")
            except Exception:
                pass
    threading.Thread(target=vigilar, daemon=True).start()

    def apagar(*_a):
        try:
            soltar(ruta)                       # primero: que ya nadie la busque (y nunca el de otra página)
            pagina_v2.apagar_todo()
        finally:
            os._exit(0)
    signal.signal(signal.SIGTERM, apagar)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        apagar()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
