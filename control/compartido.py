"""WORKSPACE · control/compartido.py — F4: la MISMA conversación en la terminal y en la página.

Para los motores cuyo servidor oficial atiende a varios clientes a la vez:

  · OpenCode (v2.1.4, su --help): la TUI es un cliente de un servidor (`--server <url>`, si no el
    servicio de fondo) y abre la sesión que se le da (`--session <id>`: «continue, or create if it
    does not exist»). Con el paquete encendido, su terminal ya no usa el servicio de fondo: Workspace
    le enciende un `opencode serve` PROPIO de esa pestaña (127.0.0.1, puerto libre, una clave local
    nueva en OPENCODE_SERVER_PASSWORD), con el entorno de la sesión (el núcleo y los permisos de su
    OPENCODE_CONFIG_CONTENT van al servidor, que es quien corre al agente), crea la conversación por
    su API si la pestaña no trae una, y abre la TUI con `--server <url> --session <id>`. Al cerrar la
    TUI, el servidor se apaga.
  · OpenClaw: el gateway del perfil de Workspace ya es compartido (openclaw_gateway); su TUI abre con
    `--session <clave>` de la pestaña. Se anota esa clave: la página entra por su puente ACP con la
    misma (`openclaw acp --session <clave>`, de su --help, 2026.10.7).

Lo que se anota (`anotar`) es el «dónde» de la terminal abierta: url, clave local, sesión, el pid de
quien la abrió y el del servidor. Va en el estado de Workspace (<estado>/control/terminales, 0600),
nunca en la config del motor ni en la global. La página lo busca (`buscar`) para conectarse a ESE
servidor y a ESA sesión; si la terminal está cerrada (no hay anotación, o su dueño murió), abre el
suyo como antes.

Stdlib. Nada aquí lee credenciales del socio: la clave es la de ese servidor local, nueva cada vez."""
import hashlib
import json
import os
import secrets
import time

#: Carpeta de las anotaciones (None = <estado de la máquina>/control/terminales; las pruebas la cambian).
CARPETA = None
#: Lo que se espera a que el servidor de la terminal escuche (como la página: SERVIDOR_ESPERA_S).
ESPERA_S = 30
#: Que el motor no se actualice solo mientras corre su servidor (lo mismo que la página y el probador).
SIN_ACTUALIZAR = {"DISABLE_AUTOUPDATER": "1"}
#: La variable con la clave local de `opencode serve` (VERIFICADO con el probador real, 17-nov).
CLAVE_OPENCODE = "OPENCODE_SERVER_PASSWORD"
#: Opciones del socio con las que la terminal no se toca: ya eligió servidor, o «la última» (sin id).
_OPENCODE_DEL_SOCIO = ("--server", "--standalone", "-c", "--continue")
_SESION_OPENCODE = ("-s", "--session")
#: Para las pruebas: Popen, «¿escucha el puerto?», el puerto libre y crear la sesión por la API.
POPEN = None
ESCUCHA = None
PUERTO = None
CREAR = None


# ── las anotaciones ────────────────────────────────────────────────────────
def _dir():
    d = CARPETA or os.environ.get("WORKSPACE_CONTROL_TERMINALES")
    if not d:
        import paths
        d = os.path.join(paths.state_dir(), "control", "terminales")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def _ruta(motor, cerebro, wid):
    clave = "%s\0%s\0%s" % (motor, os.path.realpath(str(cerebro)), wid)
    return os.path.join(_dir(), "%s-%s.json" % (motor, hashlib.sha1(clave.encode("utf-8")).hexdigest()[:16]))


def marca(pid=None):
    """La huella de un proceso (pid y hora de arranque: un pid reciclado no pasa por vivo), la misma
    de pending_runs y del gateway de OpenClaw."""
    try:
        import openclaw_gateway as G
        return G._mark(pid)
    except Exception:
        return {"pid": int(pid or os.getpid()), "ctime": None, "t0": time.time()}


def _vive(m):
    """¿Sigue vivo el proceso de esa huella? En Windows jamás os.kill(pid, 0) (allí no pregunta: manda
    Ctrl+C o termina el proceso): lo resuelve openclaw_gateway._alive con OpenProcess."""
    try:
        import openclaw_gateway as G
        return bool(G._alive(m))
    except Exception:
        if os.name == "nt":
            return True
        from control import hijos
        return hijos.vivo((m or {}).get("pid"))


def anotar(motor, cerebro, wid, servidor_pid=None, **datos):
    """Anota la terminal abierta de esa pestaña (su dueño = este proceso). → la anotación."""
    d = dict(datos, motor=motor, cerebro=os.path.realpath(str(cerebro)), wid=str(wid),
             pid=os.getpid(), dueno=marca(), desde=time.time())
    if servidor_pid:
        d["servidor"] = marca(servidor_pid)
    ruta = _ruta(motor, cerebro, wid)
    tmp = "%s.%d.tmp" % (ruta, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    os.replace(tmp, ruta)
    return d


def buscar(motor, cerebro, wid, limpiar=True):
    """La anotación de la terminal ABIERTA de esa pestaña, o None. Una cuyo dueño (o su servidor)
    ya murió se borra (con `limpiar`): la terminal se cerró de golpe."""
    if not (motor and cerebro and wid):
        return None
    ruta = _ruta(motor, cerebro, wid)
    try:
        with open(ruta, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not _vive(d.get("dueno")) or \
            (d.get("servidor") and not _vive(d["servidor"])):
        if not limpiar:
            return None
        _cerrar_huerfano(d)
        try:
            os.remove(ruta)
        except OSError:
            pass
        return None
    return d


def _cerrar_huerfano(d):
    """La terminal se cerró de golpe (su dueño murió sin apagar su servidor): el servidor que Workspace
    le encendió a ESA pestaña se apaga, si sigue vivo y es el mismo proceso (su huella: un pid reciclado
    no se toca), como hijos.limpiar_huerfano. El de un dueño vivo nunca."""
    srv = d.get("servidor") if isinstance(d, dict) else None
    if not srv or _vive(d.get("dueno")) or not _vive(srv):
        return False
    try:
        from control import hijos
        hijos.matar_grupo(int(srv["pid"]))
        return True
    except Exception:
        return False


def quitar(motor, cerebro, wid):
    """Borra la anotación, solo si es de este proceso."""
    ruta = _ruta(motor, cerebro, wid)
    try:
        with open(ruta, encoding="utf-8") as fh:
            if json.load(fh).get("pid") != os.getpid():
                return
        os.remove(ruta)
    except (OSError, ValueError, AttributeError):
        pass


def identidad(t):
    """Lo que distingue una terminal abierta de otra (para ver si la página sigue en la misma)."""
    return (t.get("pid"), t.get("url"), t.get("sesion"), t.get("desde")) if t else None


# ── la terminal de OpenCode con su servidor ────────────────────────────────
def _valor(argv, flags):
    for i, a in enumerate(argv):
        for f in flags:
            if a == f and i + 1 < len(argv):
                return argv[i + 1]
            if a.startswith(f + "="):
                return a.split("=", 1)[1]
    return ""


def _tiene(argv, flags):
    return any(a in flags or a.split("=", 1)[0] in flags for a in argv)


def _puerto_libre():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _escucha(puerto):
    import socket
    try:
        socket.create_connection(("127.0.0.1", puerto), timeout=0.5).close()
        return True
    except OSError:
        return False


def _crear_sesion(url, clave, cerebro, espera=None):
    """POST /api/session?directory=<cerebro> en ESE servidor (la ruta y el sobre {"data"}
    VERIFICADOS con el probador real, v2.1.4) → el id, o '' si no la creó.

    cable-opencode: recién abierto su puerto, `opencode serve` contesta un momento 503
    {"code": "service_starting"} (VERIFICADO en caja negra, v2.1.4, 19-nov: 2 de 3 arranques). Antes se
    pedía una sola vez: sin número, la TUI abría con `--server` y SIN `--session`, creaba la suya en
    otra carpeta y ahí no estaban el plugin ni las skills del proyecto. Ahora se pide otra vez mientras
    conteste 503, hasta `espera` s (control.opencode.ARRANQUE_S, lo mismo que la página: B31)."""
    from control.opencode import OpenCode
    oc = OpenCode(cwd=cerebro, url=url, clave=clave, timeout=10)
    try:
        st, r = oc.pedir_al_arrancar("POST", oc._ruta("crear"), {}, espera=espera)
    except Exception:
        return ""
    sid = r.get("id") if isinstance(r, dict) else ""
    return sid if st < 400 and isinstance(sid, str) else ""


def _apagar(proc):
    """Apaga el servidor con lo que haya corrido, como pagina_v2._cerrar_proc (revisión en frío): su grupo (POSIX) o
    su árbol (Windows: con `opencode.cmd` de npm, terminate() mataba solo cmd.exe y el servidor seguía escuchando)."""
    if proc is None:
        return
    try:
        if proc.poll() is None:
            if isinstance(getattr(proc, "pid", None), int):
                if os.name == "nt":                # pragma: no cover
                    import arbol_procesos
                    arbol_procesos.matar_arbol(proc)
                else:
                    from control import hijos
                    hijos.matar_grupo(proc.pid)    # su grupo propio: el servidor y lo que corrió
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(10)
            except Exception:
                proc.kill()
    except Exception:
        pass


def _en_el_cerebro(env, cerebro):
    """El entorno con PWD = el cerebro (POSIX), que es la carpeta en la que Workspace abre el servidor y la TUI
    (su cwd). VERIFICADO en caja negra (v2.1.4, 19-nov): el cliente de OpenCode (`opencode run`) toma la carpeta
    del proyecto de PWD y no de la del proceso: con el PWD heredado de quien lo abre, su conversación no veía el
    `.opencode/` del cerebro (ni el plugin ni las skills); con PWD = cwd, sí. Es lo que hace una shell al entrar
    a una carpeta; no toca ninguna config. Aquí es la red: la conversación de la pestaña ya va al cerebro por su
    API (`directory`), y esto cubre una TUI que abre sin ella."""
    env = dict(env)
    if os.name != "nt" and cerebro:
        env["PWD"] = str(cerebro)
    return env


def servidor_opencode(cerebro, wid, argv, env, al_crear=None, aviso=print):
    """(argv, env, al_salir) para abrir la TUI de OpenCode con un servidor encontrable. `argv` y
    `env` son los de la corrida YA preparados (paquete por sesión: el núcleo y los permisos van en su
    env, que es el del servidor). `al_crear(sid)`: la conversación que se creó por su API para esta
    pestaña (el lanzador la ata). `al_salir()`: borra la anotación y apaga el servidor (en ese
    orden: la página ve primero que la terminal se cerró).

    No hace nada (lo de siempre) con el paquete apagado, sin pestaña, o si el socio eligió servidor o
    «la última» (`--server`, `--standalone`, `-c`). Falla-suave: si el servidor no arranca, la TUI
    abre como siempre y se dice."""
    nada = (argv, env, lambda: None)
    try:
        from arquitectura import sesion as S
        if not (cerebro and wid) or not S.activo(env) or _tiene(argv[1:], _OPENCODE_DEL_SOCIO):
            return nada
    except Exception:
        return nada
    import subprocess
    from control.opencode import comando_servidor
    buscar("opencode", cerebro, wid)             # una terminal anterior que murió de golpe: su servidor se va
    puerto = (PUERTO or _puerto_libre)()
    clave = secrets.token_urlsafe(24)
    url = "http://127.0.0.1:%d" % puerto
    env = _en_el_cerebro(env, cerebro)
    env_srv = dict(env, **SIN_ACTUALIZAR)
    env_srv[CLAVE_OPENCODE] = clave
    from control.canal import opciones_proceso
    kw = opciones_proceso()                      # su grupo (Ctrl+C en la TUI no lo tumba) y, en Windows, sin ventana
    proc = None
    try:
        proc = (POPEN or subprocess.Popen)(comando_servidor(puerto), cwd=str(cerebro), env=env_srv,
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, **kw)
        escucha, fin = ESCUCHA or _escucha, time.time() + ESPERA_S
        while time.time() < fin and proc.poll() is None and not escucha(puerto):
            time.sleep(0.25)
        if proc.poll() is not None or not escucha(puerto):
            raise RuntimeError("no arrancó")
    except Exception as e:
        _apagar(proc)
        if aviso:
            aviso("WORKSPACE: no pude encender el servidor de OpenCode de esta pestaña (%s): la terminal "
                  "abre como siempre y la página no la comparte." % e)
        return nada
    argv = list(argv)
    sid = _valor(argv[1:], _SESION_OPENCODE)
    if not sid:
        sid = (CREAR or _crear_sesion)(url, clave, str(cerebro))
        if sid:
            argv[1:1] = ["--session", sid]
            try:                                 # el número de la pestaña, como lo fija para_lanzar (F5 lo retoma)
                from arquitectura import registro
                registro.conversacion(cerebro, wid, "opencode", sid, "fijado")
            except Exception:
                pass
            if al_crear:
                try:
                    al_crear(sid)
                except Exception:
                    pass
    argv[1:1] = ["--server", url]               # la TUI no tiene subcomando: van tras el binario
    env_tui = dict(env)
    env_tui[CLAVE_OPENCODE] = clave             # la TUI se presenta con la clave local (A VERIFICAR)
    anotar("opencode", cerebro, wid, url=url, clave=clave, sesion=sid, servidor_pid=getattr(proc, "pid", None))

    def al_salir():
        quitar("opencode", cerebro, wid)
        _apagar(proc)
    return argv, env_tui, al_salir


# ── la terminal de OpenClaw (su gateway ya es compartido) ──────────────────
def sesion_openclaw(cerebro, wid, argv, env):
    """(argv, env, al_salir): anota la clave de sesión con que abre su TUI (`tui --session <clave>`),
    para que la página entre a la misma por su puente ACP. Con `--local` (sin gateway), sin pestaña o
    con el paquete apagado, nada."""
    nada = (argv, env, lambda: None)
    try:
        from arquitectura import sesion as S
        clave = _valor(argv, ("--session",))
        if not (cerebro and wid and clave) or "tui" not in argv or "--local" in argv or not S.activo(env):
            return nada
        anotar("openclaw", cerebro, wid, sesion=clave)
    except Exception:
        return nada
    return argv, env, lambda: quitar("openclaw", cerebro, wid)
