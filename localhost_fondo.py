#!/usr/bin/env python3
"""WORKSPACE · localhost_fondo — «Workspace en el navegador» sin ocupar la terminal.

La página local (localhost_web) la sirve UN solo proceso por máquina:

  · `servir(fondo=True)` — lo que lanza el hub (`front.py web --fondo`,
    desprendido y sin terminal, ver lanzar()): si ya hay una página viva la
    reusa (abre el navegador en su link y sale); si no, la levanta, abre el
    navegador y se queda sirviendo hasta «Apagar» en la página o un día
    entero sin que nadie la use (INACTIVO_S).
  · `servir()` — `workspace web` en una terminal: lo mismo, pero en ESTE
    proceso hasta Ctrl+C (como siempre). Si ya hay una viva, la reusa.

El servidor vivo se anota en `<estado>/web/servidor.json`: pid y huella del
proceso, puerto, link con la llave y la firma del código. Ese archivo es
PRIVADO — 0600 en una carpeta 0700 (y la ACL de solo-tú en Windows), en la
carpeta de estado de esta máquina (nunca en un cerebro) — y su contenido no
se imprime ni va a un log: el link solo sale en pantalla cuando el navegador
no se pudo abrir, como siempre hizo `workspace web`.

Antes de reusar se comprueba que el proceso vive (con su huella: un pid
reciclado no pasa), que el puerto responde CON esa llave y que el código no
cambió: tras una actualización, la página vieja se apaga y nace una nueva.
La decisión «reusar o levantar» se toma bajo un candado (olock), dentro del
mismo proceso que va a servir: dos hubs a la vez no levantan dos páginas.

Relevo tras una actualización (renovar(): lo usan el hub y `workspace
update`): una página de otro código que no tiene nada a medio hacer (un turno,
un permiso, un mensaje abriendo su motor) se apaga como con «Apagar» y nace la
de hoy; si tiene algo a medio hacer, se queda hasta que quede libre. Si no se
va con «Apagar», se termina SOLO si es sin duda la nuestra (_es_nuestra: su
huella pid + hora de inicio, y su comando `front.py web` o, en Windows, su
programa Python). Cada página se anota además en `web/vivas/`: una que se
quedó sirviendo sin ser la anotada (huérfana) se apaga al nacer la siguiente,
para que nunca queden dos. Solo se renueva la página de ESTA instalación
(su `raiz`): la de otra copia de Workspace no se toca.

Stdlib; Mac, Linux y Windows. No toca localhost_web: usa su crear_servidor()
y su enlace().
"""
import hmac
import http.client
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser

import paths

HERE = os.path.dirname(os.path.abspath(__file__))

#: Cómo termina `front.py web --fondo` cuando NO se queda sirviendo.
RC_FALLO = 1
RC_REUSADA = 10           # ya había una página viva: abrió el navegador en ella
RC_SIN_NAVEGADOR = 11     # ya había una viva, pero el navegador no se abrió
#: Una página desprendida que nadie usa en un día entero se apaga sola.
INACTIVO_S = 24 * 3600
VIGIA_CADA_S = 60.0
SONDEO_S = 1.5            # tope de cada pregunta al puerto
APAGAR_S = 3.0            # cuánto se espera a que la página vieja se vaya
RELEVO_S = 6.0            # en un relevo: «Apagar» cierra sus motores (puede tardar unos segundos)
TERMINAR_S = 2.0          # si no se fue con «Apagar» y es nuestra: cuánto se espera tras cada señal
OCUPADA_S = 5.0           # tope de «¿tiene algo a medio hacer?» (la foto de todos los agentes)
CANDADO_S = 20.0
ESPERA_HUB_S = 15.0       # cuánto mira el hub al proceso que lanzó
_LLAVE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
#: Lo que decide si la página viva corre el código de hoy (más web/localhost/*; el front nuevo es web/front/index.html).
_CODIGO = ("VERSION", "localhost_web.py", "pantalla_motor.py", "localhost_fondo.py", "localhost_sistema.py",
           "localhost_front.py", "front_vivo.py", "neutral_transcript.py", os.path.join("web", "front", "index.html"), "dashboard.py", "i18n.py", os.path.join("lang", "es", "localhost.py"), os.path.join("lang", "en", "localhost.py"),
           os.path.join("lang", "es", "sistema_web.py"), os.path.join("lang", "en", "sistema_web.py"))


# ── el archivo del servidor vivo ─────────────────────────────────────────────
def ruta_estado():
    return os.path.join(paths.state_dir(), "web", "servidor.json")


def firma():
    """Huella barata del código que sirve la página (stat, sin leer archivos)."""
    import hashlib
    rels = list(_CODIGO)
    try:
        rels += sorted(os.path.join("web", "localhost", n)
                       for n in os.listdir(os.path.join(HERE, "web", "localhost")))
    except OSError:
        pass
    partes = []
    for rel in rels:
        try:
            st = os.stat(os.path.join(HERE, rel))
            partes.append("%s:%d:%d" % (rel, st.st_mtime_ns, st.st_size))
        except OSError:
            partes.append(rel + ":-")
    return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()[:20]


def _valido(d):
    try:
        if not (isinstance(d, dict) and int(d.get("pid")) > 0
                and 0 < int(d.get("puerto")) < 65536
                and _LLAVE_RE.match(str(d.get("llave") or ""))):
            return False
    except (TypeError, ValueError):
        return False
    return True


def leer():
    """El servidor anotado (dict) o None. Solo lectura; no comprueba si vive."""
    try:
        with open(ruta_estado(), encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    return d if _valido(d) else None


def enlace(d):
    """El link de entrada (con la llave) del servidor anotado."""
    base = "http://127.0.0.1:%d/" % int(d["puerto"])
    e = str(d.get("enlace") or "")
    if e.startswith(base) and str(d["llave"]) in e:
        return e
    return base + "?k=" + str(d["llave"])


def _solo_mio(ruta):
    try:
        import acl_privada
        acl_privada.solo_mio(ruta)
    except Exception:
        pass


def _escribir_privado(ruta, texto):
    """`texto` a `ruta`, atómico y solo para el dueño: el temporal nace 0600 con
    nombre impredecible (O_EXCL no sigue symlinks) y la carpeta queda 0700."""
    d = os.path.dirname(ruta)
    os.makedirs(d, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    tmp = "%s.tmp-%d-%s" % (ruta, os.getpid(), secrets.token_hex(6))
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            _solo_mio(tmp)                     # Windows: la ACL antes del contenido
            fh.write(texto.encode("utf-8"))
        try:
            import atomico
            atomico.reemplazar(tmp, ruta)      # reintenta lo pasajero de Windows
        except ImportError:
            os.replace(tmp, ruta)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass


def _marca():
    """Huella de ESTE proceso (pid + hora de inicio): un pid reciclado no pasa."""
    try:
        import openclaw_gateway as G
        return G._mark()
    except Exception:
        return {"pid": os.getpid(), "ctime": None, "t0": time.time()}


def _guardar(srv, navegador=None):
    import localhost_web
    if not getattr(srv, "ws_desde", None):
        srv.ws_desde, srv.ws_marca, srv.ws_firma = time.time(), _marca(), firma()
        srv.ws_reg = "%d-%s.json" % (os.getpid(), secrets.token_hex(4))
    d = {"pid": os.getpid(), "proc": srv.ws_marca, "puerto": int(srv.server_address[1]),
         "llave": srv.llave, "enlace": localhost_web.enlace(srv), "firma": srv.ws_firma,
         "desde": srv.ws_desde, "navegador": navegador, "raiz": HERE}
    texto = json.dumps(d)
    _escribir_privado(ruta_estado(), texto)
    try:                                       # y en el registro de las que viven (las huérfanas: _barrer)
        _escribir_privado(os.path.join(_ruta_vivas(), srv.ws_reg), texto)
    except OSError:
        pass


def _ruta_vivas():
    return os.path.join(paths.state_dir(), "web", "vivas")


def _soltar_registro(srv):
    nombre = getattr(srv, "ws_reg", None)
    if nombre:
        try:
            os.remove(os.path.join(_ruta_vivas(), nombre))
        except OSError:
            pass


def _borrar_si_mio(llave):
    """Quita la anotación solo si sigue siendo la de esa llave."""
    d = leer()
    if d and hmac.compare_digest(str(d.get("llave")), str(llave)):
        try:
            os.remove(ruta_estado())
        except OSError:
            pass


# ── ¿sigue viva? ─────────────────────────────────────────────────────────────
def _proceso_vivo(d):
    try:
        import openclaw_gateway as G
        return bool(G._alive(d.get("proc") if isinstance(d.get("proc"), dict)
                             else {"pid": d.get("pid"), "t0": d.get("desde")}))
    except Exception:
        pass
    if os.name == "nt":
        return True                    # jamás os.kill ahí (lo terminaría): decide la llave
    try:
        os.kill(int(d["pid"]), 0)
        return True
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False


def _peticion(d, metodo, ruta, timeout=SONDEO_S):
    """Una petición al servidor anotado CON su llave → código HTTP o None."""
    try:
        import localhost_web
        galleta = getattr(localhost_web, "COOKIE", "ws_llave")
    except Exception:
        galleta = "ws_llave"
    puerto = int(d["puerto"])
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=timeout)
    try:
        h = {"Host": "127.0.0.1:%d" % puerto, "Cookie": "%s=%s" % (galleta, d["llave"])}
        if metodo == "POST":
            h["Origin"] = "http://127.0.0.1:%d" % puerto
            h["Content-Length"] = "0"
        c.request(metodo, ruta, headers=h)
        r = c.getresponse()
        r.read()
        return r.status
    except (OSError, http.client.HTTPException, ValueError):
        return None
    finally:
        c.close()


def vivo():
    """(anotado, cómo): «vivo» se puede reusar · «viejo» vive pero corre otro
    código · «muerto» ya no responde · «sin» no hay nada anotado."""
    d = leer()
    if not d:
        return None, "sin"
    if not _proceso_vivo(d):
        return d, "muerto"
    if _peticion(d, "GET", "/api/textos") != 200:
        return d, "muerto"
    if d.get("firma") != firma():
        return d, "viejo"
    return d, "vivo"


def _apagar(d, tope=APAGAR_S):
    """Le pide a la página anotada que se apague («Apagar» de la página) y
    espera a que deje de responder. → True si se fue."""
    _peticion(d, "POST", "/api/apagar")
    fin = time.monotonic() + tope
    while time.monotonic() < fin:
        if _peticion(d, "GET", "/api/textos", timeout=0.5) is None:
            return True
        time.sleep(0.1)
    return False


# ── ¿es la nuestra? ¿tiene algo a medio hacer? ───────────────────────────────
def _G():
    import openclaw_gateway
    return openclaw_gateway


def _misma_ruta(a, b):
    try:
        return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))
    except (OSError, TypeError, ValueError):
        return False


def _comando(pid):
    """Mac/Linux: la línea de comandos del proceso (o None)."""
    try:
        return _G()._command(pid)
    except Exception:
        return None


def _es_python_windows(pid):
    """Windows: ¿el programa del proceso es Python? (QueryFullProcessImageNameW: sin consola ni WMI)."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                   ctypes.POINTER(wintypes.DWORD))
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        h = k32.OpenProcess(0x1000, False, int(pid))          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            buf = ctypes.create_unicode_buffer(1024)
            n = wintypes.DWORD(1024)
            if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return False
            nombre = os.path.basename(buf.value).lower()
        finally:
            k32.CloseHandle(h)
        return nombre.startswith("python") or nombre in ("py.exe", "pyw.exe")
    except Exception:
        return False


def _es_nuestra(d):
    """¿El proceso anotado es, sin duda, una página de Workspace viva? Su huella (pid + hora de inicio, la que anotó
    ella misma al nacer) tiene que coincidir; además, en Mac/Linux su comando es `front.py web` y en Windows su programa
    es Python. Sin huella (anotación de una versión anterior) o con dudas: no. Jamás este proceso ni su padre."""
    try:
        proc = d.get("proc") if isinstance(d, dict) else None
        if not isinstance(proc, dict) or not proc.get("ctime"):
            return False
        pid = int(proc.get("pid") or 0)
        if pid <= 0 or pid != int(d.get("pid") or 0) or pid in (os.getpid(), os.getppid()):
            return False
        G = _G()
        vive, ctime = G._identity(pid)
        if not vive or not ctime or not G._same_start(proc["ctime"], ctime):
            return False
        if os.name == "nt":
            return _es_python_windows(pid)
        cmd = _comando(pid) or ""
        return "front.py" in cmd and " web" in cmd
    except Exception:
        return False


def _de_aqui(d):
    """¿La página anotada es de ESTA instalación? (`raiz` anotada; en las de antes, su comando en Mac/Linux o la
    instalación a la que apunta el comando `workspace`). Una de otra copia de Workspace no se renueva desde aquí."""
    if not isinstance(d, dict):
        return False
    if d.get("raiz"):
        return _misma_ruta(d["raiz"], HERE)
    if os.name != "nt":
        cmd = _comando(d.get("pid"))
        if cmd:
            return os.path.join(HERE, "front.py") in cmd or os.path.join(os.path.realpath(HERE), "front.py") in cmd
    try:
        raiz = paths.installed_root()
    except Exception:
        raiz = ""
    return bool(raiz) and _misma_ruta(raiz, HERE)


def _terminar_windows(pid, ctime):
    """TerminateProcess sobre el MISMO handle en que se comprobó su hora de inicio (sin carrera con un pid reciclado)."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        h = k32.OpenProcess(0x0001 | 0x1000, False, int(pid))  # PROCESS_TERMINATE | QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            t = [wintypes.FILETIME() for _ in range(4)]
            if not k32.GetProcessTimes(h, *[ctypes.byref(x) for x in t]):
                return False
            if ((t[0].dwHighDateTime << 32) | t[0].dwLowDateTime) != ctime:
                return False
            return bool(k32.TerminateProcess(h, 1))
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False


def _terminar(d, tope=TERMINAR_S):
    """Termina la página anotada SOLO si es sin duda la nuestra (_es_nuestra). Mac/Linux: SIGTERM (sale ordenada:
    borra su anotación y cierra sus motores) y, si no, SIGKILL; Windows: TerminateProcess. → True si ya no vive."""
    if not _es_nuestra(d):
        return False
    G, proc = _G(), d["proc"]
    pid = int(proc["pid"])

    def se_fue():
        vive, ctime = G._identity(pid)
        return not vive or not ctime or not G._same_start(proc["ctime"], ctime)
    if os.name == "nt":
        pasos = ("windows",)
    else:
        import signal
        pasos = (signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM))
    for paso in pasos:
        if paso == "windows":
            _terminar_windows(pid, proc["ctime"])
        else:
            if not _es_nuestra(d):               # entre una señal y otra, que siga siendo ella
                return se_fue()
            try:
                os.kill(pid, paso)
            except OSError:
                pass
        fin = time.monotonic() + tope
        while time.monotonic() < fin:
            if se_fue():
                return True
            time.sleep(0.05)
    return se_fue()


def _salio(d, tope=TERMINAR_S):
    """¿El proceso anotado terminó (o ya no es ese)? Espera hasta `tope` s."""
    G, proc = _G(), d.get("proc") or {}
    fin = time.monotonic() + tope
    while True:
        vive, ctime = G._identity(proc.get("pid"))
        if not vive or not ctime or not G._same_start(proc.get("ctime"), ctime):
            return True
        if time.monotonic() >= fin:
            return False
        time.sleep(0.05)


def _retirar(d, tope=RELEVO_S):
    """Quita la página anotada: «Apagar» (lo mismo que el botón: cierra los motores que abrió) y, si su proceso sigue
    ahí (una colgada deja de contestar pero no se va), lo termina SOLO si es el nuestro. → True si ya no sirve."""
    se_fue = _apagar(d, tope)
    if not _es_nuestra(d):
        return se_fue
    return _salio(d) or _terminar(d)


def _pedir_json(d, ruta, timeout=OCUPADA_S):
    """GET con su llave → (código, dict) o (None, None)."""
    try:
        import localhost_web
        galleta = getattr(localhost_web, "COOKIE", "ws_llave")
    except Exception:
        galleta = "ws_llave"
    puerto = int(d["puerto"])
    c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=timeout)
    try:
        c.request("GET", ruta, headers={"Host": "127.0.0.1:%d" % puerto,
                                        "Cookie": "%s=%s" % (galleta, d["llave"])})
        r = c.getresponse()
        crudo = r.read()
        try:
            cuerpo = json.loads(crudo.decode("utf-8")) if crudo else {}
        except ValueError:
            cuerpo = None
        return r.status, cuerpo
    except (OSError, http.client.HTTPException, ValueError):
        return None, None
    finally:
        c.close()


def _foto_ocupada(f):
    """Una foto de /api/v2/vivo: ¿algo que «Apagar» cortaría? Lo que trabaja SOLO en su terminal (sin conector de la
    página) no: esos motores no son de la página."""
    if not isinstance(f, dict):
        return False
    if f.get("abriendo") or f.get("cola"):
        return True
    est = f.get("estado")
    if est == "esperandote":
        return not (f.get("permiso") or {}).get("en_terminal")
    if est == "trabajando":
        return not (f.get("terminal") and f.get("uso") is None)
    return False


def ocupada_en(cuerpo):
    """¿Una respuesta de /api/v2/vivo dice que la página tiene algo a medio hacer? (las de hoy lo dicen en `ocupada`;
    las de antes, por la foto de cada agente y de cada pestaña)."""
    if not isinstance(cuerpo, dict):
        return False
    if "ocupada" in cuerpo:
        return bool(cuerpo["ocupada"])
    for f in (cuerpo.get("agentes") or {}).values():
        if _foto_ocupada(f) or any(_foto_ocupada(t) for t in ((f or {}).get("tab_fotos") or {}).values()):
            return True
    return False


def ocupada(d, tope=OCUPADA_S):
    """¿La página anotada tiene algo a medio hacer que «Apagar» cortaría? → True/False; None si no se pudo saber."""
    st, cuerpo = _pedir_json(d, "/api/v2/vivo?espera=0", tope)
    if st == 404:
        return False                            # sin la conversación directa: no abrió motores
    if st != 200 or not isinstance(cuerpo, dict):
        return None
    return ocupada_en(cuerpo)


def _barrer(menos=()):
    """Las páginas anotadas en `web/vivas/` que no son la de ahora: muertas, se borra su nota; vivas (una huérfana que
    siguió sirviendo), se apagan como con «Apagar» o, si no se van, se terminan SOLO si son las nuestras. `menos`:
    las llaves que no se tocan. → cuántas se apagaron."""
    try:
        nombres = sorted(os.listdir(_ruta_vivas()))
    except OSError:
        return 0
    n = 0
    for nombre in nombres:
        if not nombre.endswith(".json"):
            continue
        ruta = os.path.join(_ruta_vivas(), nombre)
        try:
            with open(ruta, encoding="utf-8") as fh:
                e = json.load(fh)
        except (OSError, ValueError):
            e = None
        if not _valido(e):
            if not nombre.startswith("%d-" % os.getpid()):
                _quitar(ruta)
            continue
        if str(e.get("llave")) in menos:
            continue
        if int(e.get("pid") or 0) == os.getpid():
            continue                            # las de este proceso (las pruebas): las cierra quien las abrió
        if not _proceso_vivo(e):
            _quitar(ruta)
            continue
        if _peticion(e, "GET", "/api/textos") != 200 and not _es_nuestra(e):
            continue                            # no contesta con su llave y no se sabe de quién es: no se toca
        if _retirar(e):
            n += 1
            _quitar(ruta)
    return n


def _quitar(ruta):
    try:
        os.remove(ruta)
    except OSError:
        pass


# ── servir ───────────────────────────────────────────────────────────────────
class _Candado(object):
    """olock sobre el archivo del servidor; sin olock (o tomado demasiado
    tiempo) se sigue sin él — mejor abrir que quedarse sin página."""

    def __enter__(self):
        self.lk = None
        try:
            from olock import file_lock
            lk = file_lock(ruta_estado(), timeout=CANDADO_S)
            lk.__enter__()
            self.lk = lk
        except Exception:
            self.lk = None
        return self

    def __exit__(self, *exc):
        if self.lk is not None:
            self.lk.__exit__(*exc)
        return False


def _navegador(url):
    # las pruebas nunca abren el navegador de quien las corre, tampoco una página desprendida que alguna dejó
    # (22-nov: pestañas en la pantalla del socio); tests/_testutil lo prende para toda la suite y sus hijos
    if os.environ.get("WORKSPACE_SIN_NAVEGADOR") == "1":
        return False
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def _t(clave, **kw):
    import i18n
    return i18n.t(clave, **kw)


def _vigia(srv, inactivo=INACTIVO_S, cada=VIGIA_CADA_S):
    """Apaga la página desprendida tras `inactivo` s sin una sola petición."""
    srv.ultimo = time.monotonic()
    original = srv.verify_request

    def verificar(request, client_address):
        srv.ultimo = time.monotonic()
        return original(request, client_address)
    srv.verify_request = verificar
    apagado = getattr(srv, "apagado", None) or threading.Event()

    def mirar():
        while not apagado.wait(cada):
            if time.monotonic() - srv.ultimo >= inactivo:
                apagado.set()
                srv.shutdown()
                return
    t = threading.Thread(target=mirar, name="web-vigia", daemon=True)
    t.start()
    return t


def _senales():
    """SIGTERM/SIGHUP (Mac/Linux) → salida ordenada: la anotación se borra.
    → los manejadores anteriores, para restaurarlos."""
    antes = {}
    if os.name == "nt":
        return antes
    import signal

    def salir(signum, frame):
        raise SystemExit(0)
    for s in (signal.SIGTERM, signal.SIGHUP):
        try:
            antes[s] = signal.signal(s, salir)
        except (ValueError, OSError):
            pass
    return antes


def _restaurar(antes):
    if not antes:
        return
    import signal
    for s, h in antes.items():
        try:
            signal.signal(s, h)
        except (ValueError, OSError, TypeError):
            pass


def servir(fondo=False, abrir=True, decir=None):
    """Reusa la página viva o levanta una y la sirve. `fondo`: el proceso
    desprendido del hub (sin pantalla, se apaga sola si nadie la usa); si no,
    `workspace web` en una terminal (Ctrl+C la cierra). → código de salida."""
    import localhost_web
    if decir is None:
        def decir(s):
            print(s, flush=True)
    srv = None
    try:
        with _Candado():
            d, como = vivo()
            if como == "muerto" and _es_nuestra(d) and \
                    _peticion(d, "GET", "/api/textos", timeout=OCUPADA_S) == 200:
                como = "vivo" if d.get("firma") == firma() else "viejo"     # solo tardó: no era muerta
            if como == "viejo" and ocupada(d) is not False:
                como = "vivo"       # tiene algo a medio hacer: se usa así hasta que quede libre (renovar)
            if como == "vivo":
                ok = _navegador(enlace(d)) if abrir else True
                if not fondo:
                    if ok:
                        decir(_t("navegador.cli.reusada"))
                    else:
                        decir(_t("localhost.abrir", url=enlace(d)))
                        decir(_t("localhost.no_compartir"))
                    return 0
                return RC_REUSADA if ok else RC_SIN_NAVEGADOR
            if como == "viejo" or (como == "muerto" and _es_nuestra(d)):
                _retirar(d)                     # la de antes (o una colgada que es la nuestra): que no queden dos
            if d:
                _borrar_si_mio(d["llave"])      # lo anotado ya no sirve
            _barrer(menos=(str(d["llave"]),) if d else ())     # y las huérfanas que siguieran sirviendo
            srv = localhost_web.crear_servidor()
            try:
                _guardar(srv)
            except OSError:
                pass                            # sin anotación se sirve igual (no se podrá reusar)
    except Exception as e:
        if srv is not None:
            srv.server_close()
        if not fondo:
            decir(_t("navegador.cli.fallo", err=type(e).__name__))
        return RC_FALLO
    url = localhost_web.enlace(srv)
    abierto = False
    if abrir:
        abierto = _navegador(url)
        try:
            _guardar(srv, navegador=abierto)
        except OSError:
            pass
    if not fondo:
        # el link lleva la llave: solo se imprime si el navegador no pudo abrirlo
        if abierto:
            decir(_t("localhost.abierto"))
        else:
            decir(_t("localhost.abrir", url=url))
            decir(_t("localhost.no_compartir"))
        decir(_t("localhost.apagar"))
    antes = _senales()
    if fondo:
        _vigia(srv)
    try:                                        # Conexiones en verde (F4): la revisión al abrir, sin IA
        from arquitectura import chequeo
        chequeo.al_abrir()
    except Exception:
        pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        _borrar_si_mio(srv.llave)
        _soltar_registro(srv)
        _restaurar(antes)
    return 0


# ── desde el hub ─────────────────────────────────────────────────────────────
#: CREATE_NO_WINDOW (0x08000000) | CREATE_NEW_PROCESS_GROUP (0x200)
LANZAR_FLAGS_WINDOWS = 0x08000200


def lanzar(abrir=True):
    """`front.py web --fondo` desprendido: sesión propia, sin terminal ni salida
    (nada de lo que diga llega a un log). Sobrevive al hub y al agente que el
    hub lance después. `abrir=False`: sin abrir el navegador (el hub Paleta la
    prende para su conversación directa). → Popen."""
    argv = [sys.executable or "python3", os.path.join(HERE, "front.py"), "web", "--fondo"]
    if not abrir:
        argv.append("--sin-navegador")
    # Windows: CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP (su consola, escondida: los programas de consola que
    # abra —un motor, un `--version`— no sacan una ventana cada uno, como con DETACHED_PROCESS; y fuera del grupo
    # del hub, para que un Ctrl+C no la apague)
    kw = {"creationflags": LANZAR_FLAGS_WINDOWS} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, cwd=HERE, **kw)


def esperar(proc, tope=ESPERA_HUB_S, desde=None, pausa=0.1):
    """Mira al proceso lanzado hasta `tope` s → «abierta» (página nueva y el
    navegador abrió) · «reusada» · «sin_navegador» · «fallo» · «tarde» (sigue
    arrancando: el navegador se abre solo en cuanto esté)."""
    desde = time.time() if desde is None else desde
    fin = time.monotonic() + tope
    while True:
        rc = proc.poll()
        if rc is not None:
            return {0: "abierta", RC_REUSADA: "reusada",
                    RC_SIN_NAVEGADOR: "sin_navegador"}.get(rc, "fallo")
        d = leer()
        # la anotación de ESTE lanzamiento: nació después de lanzarlo (el pid
        # no basta: en Mac el python del framework puede ser hijo del lanzado)
        if d and d.get("navegador") is not None and (
                int(d.get("pid") or 0) == proc.pid or float(d.get("desde") or 0) >= desde):
            return "abierta" if d.get("navegador") else "sin_navegador"
        if time.monotonic() >= fin:
            return "tarde"
        time.sleep(pausa)


def _recoger(proc):
    """Que el proceso no quede zombi mientras este (el hub) siga vivo."""
    if proc.poll() is None:
        threading.Thread(target=proc.wait, name="web-recoger", daemon=True).start()


def abrir_desde_hub(tope=ESPERA_HUB_S):
    """Lo que hace el hub (en un hilo): lanza la página desprendida y mira cómo
    terminó. Jamás levanta."""
    t0 = time.time()
    try:
        proc = lanzar()
    except Exception:
        return "fallo"
    try:
        return esperar(proc, tope, desde=t0)
    except Exception:
        return "fallo"
    finally:
        _recoger(proc)


# ── el relevo tras una actualización ─────────────────────────────────────────
#: La línea que dice el hub cuando renovó la página (y `workspace update`).
AVISO_RENOVADA = "Workspace se actualizó: reinicié la página"


def renovar(tope=ESPERA_HUB_S, abrir=None, dormir=time.sleep, reloj=time.monotonic):
    """Si la página anotada corre el código de antes (una actualización) y no tiene nada a medio hacer, nace la de hoy
    en su lugar: se lanza `front.py web --fondo` (el código nuevo), que bajo el candado apaga la vieja como «Apagar» y
    se anota. `abrir`: abrir el navegador en la nueva (por omisión, si la vieja se abrió en él). Jamás prende una
    página si no había ninguna, ni toca la de otra instalación. → (anotación, resultado): «al_dia» (ya corría la de
    hoy) · «renovada» · «ocupada» (tiene algo a medio hacer: se queda hasta que quede libre) · «ajena» (de otra copia
    de Workspace) · «sin» (no hay ninguna viva) · «tarde» · «fallo»."""
    d, como = vivo()
    if como == "vivo":
        return d, "al_dia"
    if como != "viejo":
        return d, "sin"
    if not _de_aqui(d):
        return d, "ajena"
    if ocupada(d) is not False:
        return d, "ocupada"
    try:
        proc = lanzar(abrir=bool(d.get("navegador")) if abrir is None else bool(abrir))
    except Exception:
        return d, "fallo"
    _recoger(proc)
    fin = reloj() + tope
    while reloj() < fin:
        dormir(0.15)
        n, c = vivo()
        if c == "vivo" and n and n.get("llave") != d.get("llave"):
            return n, "renovada"
        rc = proc.poll()
        if rc is not None and rc != 0:
            if rc in (RC_REUSADA, RC_SIN_NAVEGADOR):       # al decidir ya tenía algo a medio hacer: se quedó
                return n or d, "ocupada"
            return n or d, "fallo"
    return d, "tarde"


def tras_actualizar(tope=10.0):
    """Lo que hace `workspace update` al traer código nuevo: renueva la página de esta instalación si corre la de
    antes y está libre (si no hay ninguna, no prende otra). Falla-suave. → el resultado de renovar()."""
    try:
        return renovar(tope=tope)[1]
    except Exception:
        return "fallo"
