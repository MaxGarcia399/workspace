#!/usr/bin/env python3
"""WORKSPACE · amigable — la página para gente que no sabe de terminal.

Qué le pasa a un motor, dicho en simple, y lo que Workspace arregla solo:

  · de_texto(motor, texto): lo que dijo el motor por la capa de control (un error, el porqué de que no
    abrió, o la respuesta de Copilot que en realidad es su error de cuota) → uno de ESTADOS. Una función por
    motor (claude_code, codex, copilot) con las frases que ese motor mandó de verdad, y una genérica para el
    resto. Lo que no se reconoce da None: una conversación que HABLA de cuotas no es un error.
  · de_sondeo(motor): lo que dicen sus comandos oficiales (motores_logica, sin leer pantallas): sin instalar,
    sin sesión, o una versión que hay que actualizar.
  · alternativa(motor): otro motor listo en esta computadora, para «Seguir con …» en un toque.
  · Los arreglos (uno a la vez por agente):
      - iniciar sesión: el login OFICIAL del motor en una pestaña de herdr (localhost_sistema.motor_correr),
        con la página guiando paso a paso;
      - actualizar o instalar: su instalador oficial (engine_install), en segundo plano;
      - Codex: la confianza de sus hooks (D6-a), que el socio da UNA vez en /hooks de su terminal: Workspace
        abre Codex («Ir a la terminal», el lanzador de siempre) y la página guía con dibujos.
    Cada uno sabe solo cuándo terminó, por el archivo de su tarea, su código de salida y la sesión que dice
    el comando oficial del motor (nunca la pantalla), y entonces llama a `al_listo` (la página sigue con tu
    mensaje). La confianza de Codex, por `hooks/list` de su app-server (confianza_codex).

Nada se teclea en un motor, nada se borra y ninguna llave se lee: el inicio de sesión lo hace el programa
oficial. Stdlib.
"""
import os
import re
import secrets
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

#: Lo que la página sabe explicar (y, cuando se puede, arreglar sola).
ESTADOS = ("sin_instalar", "actualizar", "sin_sesion", "sin_creditos", "sin_internet", "terminal_vieja")

# ── qué le pasa: por lo que dijo el motor ─────────────────────────────────────
# Frases de falla de verdad (no palabras sueltas): un agente que habla de «quota» o de «login» no es un error.
_SESION = ("please run /login", "run /login", "not logged in", "oauth token has expired", "authentication_error",
           "authentication error", "authentication required", "pide iniciar sesión", "login required",
           "session has expired", "session expired", "invalid api key", "unauthorized")
_CREDITOS = ("credit balance is too low", "insufficient credits", "insufficient balance", "insufficient funds",
             "quota exceeded", "exceeded your quota", "exceeded your current quota", "exceeded your monthly quota",
             "exceeded your monthly premium requests", "out of credits", "no credits left", "no credit left",
             "payment required", "billing hard limit", "usage limit reached", "hit your usage limit",
             "hit your limit", "reached your usage limit", "reached your weekly limit", "reached your 5-hour limit")
_RED = ("connection error", "network error", "econnrefused", "enotfound", "etimedout", "getaddrinfo",
        "failed to connect", "unable to connect", "network is unreachable", "fetch failed",
        "could not resolve host", "no route to host")
_HTTP_401 = re.compile(r"\b(?:http|status|error)[^\n]{0,12}\b401\b|\b401 unauthorized\b", re.I)


def _con(texto, frases):
    t = " ".join(str(texto or "").lower().replace("’", "'").split())
    return any(f in t for f in frases)


def generico(texto):
    """Cualquier motor: sesión vencida, sin créditos o sin cuota, sin internet (en ese orden). None si no es
    ninguna de esas."""
    if _con(texto, _SESION) or _HTTP_401.search(str(texto or "")):
        return "sin_sesion"
    if _con(texto, _CREDITOS):
        return "sin_creditos"
    if _con(texto, _RED):
        return "sin_internet"
    return None


def claude_code(texto):
    """Claude Code (`claude -p`, el `result` con is_error). Lo que mandó de verdad:
      · «Invalid API key · Please run /login» y «OAuth token has expired»: sin sesión; se arregla entrando
        de nuevo con su login, no poniendo otra llave (pantalla_motor y tests/test_errores_motor);
      · «Credit balance is too low»: sin crédito (el error del motor falso, copiado del real);
      · «Claude AI usage limit reached»: el límite de su plan (su error de uso)."""
    if _con(texto, ("please run /login", "run /login", "oauth token has expired", "invalid api key")):
        return "sin_sesion"
    if _con(texto, ("credit balance is too low", "usage limit reached")):
        return "sin_creditos"
    return generico(texto)


def codex(texto):
    """Codex (app-server). «Not logged in» es lo que dice su login oficial sin sesión (`codex login status`,
    VERIFICADO en engines/codex: «not logged in» contiene «logged in», por eso se mira entero); «You've hit
    your usage limit» es su límite de uso."""
    if _con(texto, ("not logged in", "logged out")):
        return "sin_sesion"
    if _con(texto, ("you've hit your usage limit", "you have hit your usage limit", "usage limit reached")):
        return "sin_creditos"
    return generico(texto)


def copilot(texto):
    """GitHub Copilot por ACP. Lo que mandó de verdad:
      · «Error: You have exceeded your monthly quota (Request ID: …)», como TEXTO de su respuesta, sin señal de
        error (probador real, 17-nov; y «✗ You have exceeded your monthly quota» en su terminal, F10);
      · sin sesión, el ACP falla al abrir y la capa de control lo dice: «copilot pide iniciar sesión…»."""
    if _con(texto, ("exceeded your monthly quota", "exceeded your monthly premium requests")):
        return "sin_creditos"
    if _con(texto, ("pide iniciar sesión", "not logged in", "authentication required")):
        return "sin_sesion"
    return generico(texto)


POR_MOTOR = {"claude-code": claude_code, "codex": codex, "copilot": copilot}


def de_texto(motor, texto):
    """El estado que dice lo que mandó `motor` (uno de ESTADOS), o None."""
    if not texto:
        return None
    return POR_MOTOR.get(motor, generico)(texto)


#: Una respuesta que en realidad es el error del motor es corta y empieza como su error.
_RESPUESTA_ERROR = re.compile(r"^\s*(?:error\b|✗|❌)", re.I)
RESPUESTA_ERROR_MAX = 300


def respuesta_de_error(motor, texto):
    """¿La RESPUESTA del agente es en realidad su error? Copilot manda su error de cuota como texto (ver
    copilot): solo si es corta, empieza como un error y su función la reconoce. → el estado, o None."""
    t = str(texto or "").strip()
    if motor != "copilot" or not t or len(t) > RESPUESTA_ERROR_MAX or not _RESPUESTA_ERROR.match(t):
        return None
    return copilot(t)


# ── qué le pasa: por sus comandos oficiales ───────────────────────────────────
def de_sondeo(motor):
    """Lo que dicen sus comandos oficiales (los mismos de Motores): «sin_instalar», «actualizar» (su versión ya
    no sirve con Workspace), «sin_sesion», o None (está bien, o no se pudo saber). La suite no corre programas
    (WORKSPACE_NO_SESSION_PROBE)."""
    if os.environ.get("WORKSPACE_NO_SESSION_PROBE"):
        return None
    try:
        import motores_logica as ET
        d = next((x for x in ET._rows() if x.get("id") == motor), None)
        if d is None:
            return None
        if not d.get("binaries_ok"):
            return "sin_instalar"
        if (ET.version_of(motor) or {}).get("st") == "unsupported":
            return "actualizar"
        sesion = sondeo_sesion(motor)
    except Exception:
        return None
    if sesion == "version":
        return "actualizar"
    return "sin_sesion" if sesion is False else None


def _sondeo_sesion(motor):
    """True/False/None (o «version», «needs_model»…) con el comando oficial del motor, sin la caché de 60 s."""
    if os.environ.get("WORKSPACE_NO_SESSION_PROBE"):
        return None
    import motores_logica as ET
    ET._SESSION_CACHE.pop(motor, None)
    return ET._probe(motor)


#: Las pruebas lo cambian (los motores falsos no tienen comando de sesión).
sondeo_sesion = _sondeo_sesion

#: En qué orden se ofrece seguir con otro motor.
ORDEN = ("claude-code", "codex", "copilot", "cursor", "kiro", "opencode", "antigravity", "hermes", "openclaw",
         "gemini")


def _listos():
    import localhost_web
    return localhost_web._motores_listos()


#: Los motores listos en esta computadora (las pruebas lo cambian).
listos = _listos


#: La página lo pide en cada vuelta mientras su tarjeta está: los motores listos se miran cada tanto.
ALTERNATIVA_S = 10.0
_ALT = {}


def alternativa(motor):
    """Otro motor listo en esta computadora al que la página le puede escribir, sin una sesión que ya se
    sepa vencida. None si no hay."""
    hit = _ALT.get(motor)
    if hit and time.time() - hit[0] < ALTERNATIVA_S:
        return hit[1]
    out = None
    try:
        hay = set(listos())
        import control
        import motores_logica as ET
        cache = dict(ET._SESSION_CACHE)
        for m in ORDEN:
            if m != motor and m in hay and control.puede_escribir(m) and \
                    (cache.get(m) or (0, None))[1] is not False:
                out = m
                break
    except Exception:
        out = None
    _ALT[motor] = (time.time(), out)
    return out


# ── los arreglos ─────────────────────────────────────────────────────────────
#: Lo que se espera a que termines de entrar a tu cuenta, y a un instalador.
TOPE_LOGIN_S = 15 * 60
TOPE_INSTALAR_S = 15 * 60
#: Cada cuánto se mira cómo va.
PASO_S = 2.0
#: Cada cuántos pasos se le pregunta a su comando oficial por la sesión (mientras su ventana sigue abierta).
SONDEO_CADA = 3
#: Cuánto se ve «¡Listo!» antes de irse.
LISTO_S = 10

_LOCK = threading.Lock()
_ARREGLOS = {}                     # agente → el arreglo de ahora (dict)
#: Lo que despierta a la página (pagina_v2 pone el suyo).
avisar = None
#: Enfoca la pestaña nueva en herdr y dice dónde está: panel → {"estado", "donde"} (pagina_v2 pone el suyo).
enfocar = None


def _sistema():
    import localhost_sistema
    return localhost_sistema


def _avisar():
    if avisar:
        try:
            avisar()
        except Exception:
            pass


def arreglo(agente):
    """El arreglo de `agente` para la página (sin lo interno), o None. «¡Listo!» se ve LISTO_S y se va."""
    with _LOCK:
        ar = _ARREGLOS.get(agente)
        if not ar:
            return None
        if ar["paso"] == "listo" and time.time() - ar["t"] > LISTO_S:
            _ARREGLOS.pop(agente, None)
            return None
        return {k: v for k, v in ar.items() if not k.startswith("_")}


def _nuevo(agente, tipo, motor, **campos):
    """El arreglo nuevo de `agente`, o el que ya va igual (mismo tipo y motor, sin terminar): (arreglo, nuevo?)."""
    with _LOCK:
        cur = _ARREGLOS.get(agente)
        if cur and cur["tipo"] == tipo and cur["motor"] == motor and cur["paso"] in ("abriendo", "esperando",
                                                                                     "trabajando"):
            return cur, False
        ahora = time.time()
        ar = dict({"id": secrets.token_hex(4), "tipo": tipo, "motor": motor, "paso": "abriendo", "t": ahora,
                   "inicio": ahora}, **campos)
        _ARREGLOS[agente] = ar
    _avisar()
    return ar, True


def _poner(agente, ar, **campos):
    """Avance del arreglo `ar` (si sigue siendo el de ahora). → True si quedó."""
    with _LOCK:
        if _ARREGLOS.get(agente) is not ar:
            return False
        ar.update(campos, t=time.time())
    _avisar()
    return True


def olvidar(agente):
    """Cuando ya no hace falta (cambiaste de motor, lo cerraste)."""
    with _LOCK:
        _ARREGLOS.pop(agente, None)
    _avisar()


def _hilo(fn, *args):
    threading.Thread(target=fn, args=args, name="amigable-%s" % fn.__name__, daemon=True).start()


def _listo(agente, ar, al_listo):
    if _poner(agente, ar, paso="listo") and al_listo:
        try:
            al_listo()
        except Exception:
            pass


def iniciar_sesion(agente, motor, al_listo=None):
    """Abre el login OFICIAL del motor en una pestaña de herdr (al frente) y sigue cómo va, sin leer su
    pantalla: cuando su comando oficial dice que ya hay sesión, «listo» y `al_listo()`. Sin herdr, los
    comandos para copiar. → el arreglo (para la página)."""
    ar, nuevo = _nuevo(agente, "login", motor)
    if not nuevo:
        return arreglo(agente)
    try:
        r = _sistema().motor_correr(motor, "iniciar_sesion")
    except Exception as e:
        r = {"ok": False, "error": "", "mensaje": "%s: %s" % (type(e).__name__, e)}
    if not r.get("ok"):
        sin_herdr = str(r.get("error") or "").endswith(".sin_herdr")
        _poner(agente, ar, paso="sin_herdr" if sin_herdr else "fallo", comandos=list(r.get("comandos") or [])[:4],
               detalle=str(r.get("mensaje") or r.get("error") or "")[:400])
        return arreglo(agente)
    tarea = r.get("tarea") or ""
    t = _sistema()._leer_tarea(tarea) or {}
    donde = {}
    if enfocar and t.get("panel"):
        try:
            donde = (enfocar(t["panel"]) or {}).get("donde") or {}
        except Exception:
            donde = {}
    _poner(agente, ar, paso="esperando", tarea=tarea, donde=donde, etiqueta=str(t.get("etiqueta") or "")[:60])
    _hilo(_vigilar_login, agente, ar, tarea, al_listo)
    return arreglo(agente)


def _vigilar_login(agente, ar, tarea, al_listo):
    LS = _sistema()
    fin, vuelta = time.time() + TOPE_LOGIN_S, 0
    while time.time() < fin:
        with _LOCK:
            if _ARREGLOS.get(agente) is not ar:
                return                                    # lo reemplazó otro arreglo
        t = LS._leer_tarea(tarea) or {}
        termino = t.get("estado") in ("terminada", "cerrada") or (t.get("panel") and not LS._panel_vivo(t))
        vuelta += 1
        if termino or vuelta % SONDEO_CADA == 0:
            if sondeo_sesion(ar["motor"]) is True:
                if termino and t.get("panel") and LS._panel_vivo(t):
                    LS._cerrar_pestana(t)                 # su ventana ya no hace falta
                if termino:
                    LS._tras_tarea(ar["motor"])           # como al volver a Motores: la sesión, otra vez
                return _listo(agente, ar, al_listo)
            if termino:
                _poner(agente, ar, paso="sin_terminar", detalle=str(t.get("mensaje") or "")[:400])
                return
        time.sleep(PASO_S)
    _poner(agente, ar, paso="sin_terminar")


def _correr(cmd, log, tope):
    """El instalador oficial, sin terminal (stdin cerrado), con su salida a `log`. → código de salida."""
    from control.canal import opciones_proceso, resolver
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "ab") as fh:
        try:
            r = subprocess.run(resolver(cmd), stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                               timeout=tope, env=dict(os.environ, DISABLE_AUTOUPDATER="1"), **opciones_proceso())
            return r.returncode
        except (OSError, subprocess.SubprocessError) as e:
            fh.write(("\n%s: %s\n" % (type(e).__name__, e)).encode("utf-8", "replace"))
            return None


#: Las pruebas lo cambian (nada real se instala).
correr = _correr


def _log(motor, tipo):
    import paths
    return os.path.join(paths.state_dir(), "amigable", "%s-%s.log" % (motor, tipo))


def _cola_log(ruta, n=12):
    try:
        with open(ruta, encoding="utf-8", errors="replace") as fh:
            return "\n".join(fh.read().splitlines()[-n:])[-1500:]
    except OSError:
        return ""


def instalar(agente, motor, al_listo=None, tipo="actualizar"):
    """Actualiza (o instala, `tipo`) el motor con su instalador OFICIAL (engine_install.recipe: el mismo de
    Motores, que deja la última versión) en segundo plano. Si le falta algo (npm, curl…) o no hay receta, no
    corre nada: lo dice. → el arreglo."""
    ar, nuevo = _nuevo(agente, tipo, motor)
    if not nuevo:
        return arreglo(agente)
    try:
        import engine_install
        rec = engine_install.recipe(motor)
        falta = engine_install.missing_prereqs(rec) if rec else []
    except Exception:
        rec, falta = None, []
    if not rec or falta:
        _poner(agente, ar, paso="fallo", detalle=("le falta: " + ", ".join(falta)) if falta else "sin instalador")
        return arreglo(agente)
    _poner(agente, ar, paso="trabajando")
    _hilo(_instalar, agente, ar, list(rec["cmd"]), al_listo)
    return arreglo(agente)


def _instalar(agente, ar, cmd, al_listo):
    log = _log(ar["motor"], ar["tipo"])
    rc = correr(cmd, log, TOPE_INSTALAR_S)
    if rc != 0:
        _poner(agente, ar, paso="fallo", detalle=_cola_log(log))
        return
    try:                                                   # lo de después de instalar, como en Motores
        _sistema()._tras_tarea(ar["motor"])
    except Exception:
        pass
    _listo(agente, ar, al_listo)


# ── Codex: la confianza de sus hooks (D6-a) ──────────────────────────────────
# hooks5: con el paquete por sesión, Codex lee los hooks de Workspace del .codex/hooks.json del cerebro, pero no corre
# NINGUNO sin la confianza PERSISTIDA del socio, que se da una vez en /hooks de su terminal. Sin ella la página no ve
# lo que hace Codex en la terminal y lo prohibido no se frena antes de cada herramienta.
# Cómo se sabe sin leer su pantalla ni adivinar su huella: `hooks/list` de su app-server (control.codex.listar_hooks),
# que dice por hook «untrusted», «trusted» o «modified» (cambió su comando o su timeout desde que se confió). Nada se
# escribe en la config de Codex: la confianza la da el socio.

#: Sin que cambie nada, se le vuelve a preguntar a Codex cada tanto (s). Si cambia su config.toml (ahí guarda la
#: confianza) o el hooks.json del cerebro, enseguida.
CONFIANZA_S = 600
#: Lo que se espera a que confíes en ellos con la ventana abierta (s).
TOPE_CONFIANZA_S = 15 * 60
_CONF = {}                         # cerebro (real) → {"firma", "t", "res", "va"}
_CONF_LOCK = threading.Lock()


def _hooks_codex(cerebro):
    """El hooks.json que el lanzador deja en el cerebro (ficha de Codex · sesion.archivos)."""
    return os.path.join(str(cerebro), ".codex", "hooks.json")


def _config_codex():
    """Su config.toml (CODEX_HOME o ~/.codex), donde guarda la confianza."""
    return os.path.join(os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex"),
                        "config.toml")


def _firma_confianza(cerebro):
    """Lo barato de mirar: si cambia, se le pregunta a Codex otra vez."""
    out = []
    for r in (_config_codex(), _hooks_codex(cerebro)):
        try:
            st = os.stat(r)
            out.append((st.st_size, st.st_mtime_ns))
        except OSError:
            out.append(None)
    return tuple(out)


def _listar_hooks(cerebro):
    """hooks/list de su app-server en el cerebro. La suite no corre programas (WORKSPACE_NO_SESSION_PROBE): no se
    sabe."""
    if os.environ.get("WORKSPACE_NO_SESSION_PROBE"):
        raise RuntimeError("sin sondeos: no se le pregunta a Codex")
    from control import codex as control_codex
    return control_codex.listar_hooks(str(cerebro))


#: Las pruebas lo cambian (sin Codex real).
listar_hooks = _listar_hooks


def _de_la_lista(cerebro, hooks):
    """Lo que dice `hooks/list` de los hooks de Workspace (los del .codex/hooks.json del cerebro; los tuyos no
    cuentan): {"estado": "listo" | "falta" | "modificados", "total", "confiados", "faltan": [sus eventos]}.
    Un hook que apagaste en /hooks cuenta como resuelto: lo decidiste tú. Ninguno en la lista (el proyecto todavía
    sin confianza, o Codex nunca se abrió con el paquete) = falta."""
    ruta = os.path.normcase(os.path.realpath(_hooks_codex(cerebro)))
    nuestros = [h for h in hooks if os.path.normcase(os.path.realpath(str(h.get("sourcePath") or ""))) == ruta]
    faltan = [h for h in nuestros
              if h.get("trustStatus") not in ("trusted", "managed") and h.get("enabled") is not False]
    if nuestros and not faltan:
        estado = "listo"
    elif any(h.get("trustStatus") == "modified" for h in faltan):
        estado = "modificados"
    else:
        estado = "falta"
    return {"estado": estado, "total": len(nuestros), "confiados": len(nuestros) - len(faltan),
            "faltan": sorted({str(h.get("eventName") or "") for h in faltan})}


def confianza_codex(cerebro, esperar=False):
    """¿Codex ya confía en los hooks de Workspace de `cerebro`? → _de_la_lista, o None si todavía no se sabe o no se
    pudo saber (Codex sin instalar, o una versión sin hooks/list). No bloquea: si cambió su config.toml o el hooks.json
    del cerebro, o pasó CONFIANZA_S, le pregunta en un hilo y, si la respuesta cambió, despierta a la página.
    `esperar`: le pregunta ya, en este hilo (la vigilancia del arreglo)."""
    clave = os.path.realpath(str(cerebro))
    firma = _firma_confianza(cerebro)
    with _CONF_LOCK:
        c = _CONF.get(clave) or {}
        if not esperar:
            if c.get("va") or (c.get("firma") == firma and time.time() - c.get("t", 0) < CONFIANZA_S):
                return c.get("res")
            _CONF[clave] = dict(c, va=True)
    if esperar:
        return _preguntar_confianza(clave, cerebro, firma)
    _hilo(_preguntar_confianza, clave, cerebro, firma)
    return c.get("res")


def _preguntar_confianza(clave, cerebro, firma):
    try:
        res = _de_la_lista(cerebro, listar_hooks(cerebro))
    except Exception:
        res = None
    with _CONF_LOCK:
        antes = (_CONF.get(clave) or {}).get("res")
        _CONF[clave] = {"firma": firma, "t": time.time(), "res": res, "va": False}
    if res != antes:
        _avisar()
    return res


#: B06: «No lo veo: llévame ahí» reabre o enfoca solo si la espera ya lleva esto (s): dos toques seguidos, un solo Codex.
REABRIR_S = 4.0


def confiar_hooks(agente, motor, cerebro, abrir, al_listo=None):
    """D6-a en simple: abre Codex en su terminal (`abrir`: «Ir a la terminal» de la página, con el lanzador de siempre,
    que deja sus hooks en el cerebro y confía el proyecto) y, sin leer su pantalla, espera a que confíes en los de
    Workspace en su /hooks: cuando hooks/list dice que ya, «listo». Nada se teclea en Codex. → el arreglo."""
    ar, nuevo = _nuevo(agente, "confianza", motor)
    if not nuevo:
        # (un doble toque sigue siendo un solo Codex: solo se reabre si ya lleva esperando un rato)
        if ar.get("paso") == "esperando" and time.time() - float(ar.get("t") or 0) >= REABRIR_S:
            # B06: «Llévame ahí» mientras espera: se vuelve a abrir o enfocar (antes no hacía nada durante 15 min).
            # La espera sigue la misma (su vigilante no cambia)
            try:
                r = abrir() or {}
            except Exception:
                r = {}
            if r.get("ok"):
                _poner(agente, ar, donde=r.get("donde") or ar.get("donde") or {},
                       abierta=str(r.get("estado") or ar.get("abierta") or ""))
        return arreglo(agente)
    try:
        r = abrir() or {}
    except Exception as e:
        r = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    if not r.get("ok"):
        _poner(agente, ar, paso="fallo", error=str(r.get("error") or "")[:200])
        return arreglo(agente)
    _poner(agente, ar, paso="esperando", donde=r.get("donde") or {}, abierta=str(r.get("estado") or ""))
    _hilo(_vigilar_confianza, agente, ar, cerebro, al_listo)
    return arreglo(agente)


def _vigilar_confianza(agente, ar, cerebro, al_listo):
    """Le pregunta a Codex al empezar y cada vez que cambia su config.toml (al confiar, /hooks lo escribe) o el
    hooks.json del cerebro (al abrir, el lanzador lo deja)."""
    fin, firma = time.time() + TOPE_CONFIANZA_S, None
    while time.time() < fin:
        with _LOCK:
            if _ARREGLOS.get(agente) is not ar:
                return                                    # lo reemplazó otro arreglo
        f = _firma_confianza(cerebro)
        if f != firma:
            firma = f
            if (confianza_codex(cerebro, esperar=True) or {}).get("estado") == "listo":
                return _listo(agente, ar, al_listo)
        time.sleep(PASO_S)
    _poner(agente, ar, paso="sin_terminar")
