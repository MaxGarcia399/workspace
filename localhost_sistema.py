#!/usr/bin/env python3
"""WORKSPACE · localhost_sistema — MOTORES y USUARIOS del hub, para la página local.

Lo mismo que se hace en la terminal, como funciones que devuelven dicts listos
para JSON (sin secretos, sin rutas del disco). No reimplementa nada: llama a
las mismas funciones de las pantallas del hub.

  Motores de agentes   engines_tui    estado, versión, integración, quién lo usa;
                                      instalar · reinstalar · reparar · iniciar
                                      sesión · cuenta y proveedor (y su menú) ·
                                      verificar sesión · recargar · ofrecer en el hub
  Modelos de decisión  modelos_tui    conectar y desconectar la llave · modelo ·
                                      contexto · probar · volver a mirar (local)
  Usuarios             usuarios(_tui) crear · cambiar nombre · unir · soy yo en esta PC
  Agentes (hub ←→)     agent_manage   el motor de un agente en esta máquina

Lo que en la terminal corre un programa del motor (instalar, iniciar sesión,
«cuenta y proveedor») necesita una terminal: aquí se abre en una pestaña NUEVA
de herdr que corre `localhost_sistema.py correr …` (el mismo motores_logica.execute
del hub). La página sigue esa pestaña con `motor_tarea` (estado, la pantalla, el
enlace o el código que imprima el programa) y le puede mandar teclas a ESE
programa (`motor_tarea_teclas`), nunca a una shell. Workspace jamás lee, guarda
ni automatiza las credenciales: el inicio de sesión lo hace el programa oficial.

Validación: cada entrada se compara contra listas conocidas (motores de
motores_logica.SUPPORTED, acciones de aquí, opciones del menú del adapter,
decisores de deciders/, agentes registrados, usuarios de su cerebro). Ningún
comando sale de lo que manda la página: todos salen de engine_install y de los
adapters, y se corren como lista de argumentos (sin shell).

Resultados: {"ok": True, …, "mensaje"} o {"ok": False, "error": <clave i18n>,
"status": <código HTTP sugerido>, "datos": {…}, "mensaje"}. `mensaje` va en el
idioma de Workspace; `error` + `datos` permiten traducirlo en el de la página.
Stdlib.
"""
import json
import os
import re
import shlex
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

#: Acciones de un motor que corren un programa (en una pestaña de herdr).
ACCIONES = ("instalar", "actualizar", "reinstalar", "reparar", "iniciar_sesion", "cuenta")
#: Lo que la terminal le pide confirmar con un segundo Enter (muestra los
#: comandos antes): la página debe mandar `confirmado` tras mostrarlos.
_CONFIRMAR = ("instalar", "actualizar", "reinstalar", "reparar")
#: Opciones posibles del menú «cuenta y proveedor» de un adapter (account_menu).
CUENTA = ("whoami", "login", "models", "open", "switch", "add", "providers")
#: Las teclas que la página puede mandar a la pestaña de un motor: elegir en un
#: menú, confirmar, borrar, cancelar. Van a herdr con aviso_panel.tecla_herdr
#: (`c-u` → `ctrl+u`). H6 (17-nov): sin btab, home, end, pageup, pagedown ni
#: delete, que herdr 0.9.5 rechaza («unsupported key»).
TECLAS = {"enter", "esc", "backspace", "tab", "up", "down", "left", "right", "space", "c-c", "c-u"}
MAX_TECLAS = 16
MAX_TEXTO = 512
MAX_LLAVE = 512
MAX_NOMBRE = 40                  # lo que admite el campo de Usuarios en el hub
MAX_USUARIOS = 200               # por agente
MAX_LINEAS = 60                  # de la pantalla de una pestaña de motor
MAX_COL = 400
TAREA_VIVA_S = 30 * 60           # una pestaña de motor «sigue» a lo más esto
_TAREA_RE = re.compile(r"^[0-9a-f]{12}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+")
_CODIGO_RE = re.compile(r"\b(?=[A-Z0-9-]*[A-Z])[A-Z0-9]{4,5}-[A-Z0-9]{4,5}\b")


# ── textos y resultados ───────────────────────────────────────────────────────
def _t(clave, **kw):
    try:
        import i18n
        return i18n.t(clave, **kw)
    except Exception:
        return clave


def _err(clave, status=400, **datos):
    clave = "localhost.sistema.err." + clave
    return {"ok": False, "error": clave, "status": status, "datos": datos,
            "mensaje": _t(clave, **datos)}


def _ok(mensaje="", **extra):
    d = {"ok": True, "mensaje": mensaje}
    d.update(extra)
    return d


def _limpio(texto, n=200):
    """Texto hacia la página: sin controles, recortado y, si parece llave, oculto."""
    s = _CONTROL_RE.sub("", "" if texto is None else str(texto))
    try:
        import secret_scan
        if s and secret_scan.scan_text(s):
            return _t("localhost.sistema.oculto")
    except Exception:
        return ""
    return s[:n]


def _bloques(blocks):
    """Los bloques de ayuda de las pantallas (section_box) → JSON."""
    out = []
    for b in blocks or ():
        tipo = b[0] if b else ""
        if tipo == "h":
            out.append({"tipo": "titulo", "texto": _limpio(b[1], 300)})
        elif tipo in ("p", "dim"):
            out.append({"tipo": "parrafo" if tipo == "p" else "nota", "texto": _limpio(b[1], 2000)})
        elif tipo == "kv":
            out.append({"tipo": "pares", "pares": [[_limpio(k, 120), _limpio(v, 2000)] for k, v in b[1]]})
        elif tipo == "flow":
            out.append({"tipo": "flujo", "pasos": [[_limpio(k, 120), _limpio(v, 200)] for k, v in b[1]]})
        elif tipo == "list":
            out.append({"tipo": "lista", "items": [_limpio(x, 300) for x in b[1]]})
    return out


# ── MOTORES DE AGENTES (engines_tui) ──────────────────────────────────────────
def _ET():
    import motores_logica
    return motores_logica


_LOCK = threading.Lock()
_S = {}                          # el estado de Motores (el de engines_tui), vivo con el servidor


def _estado():
    """El estado de la pantalla de Motores (checks, versiones, bloqueos), con
    la lista de motores al día (binarios en el PATH: barato)."""
    ET = _ET()
    with _LOCK:
        if not _S:
            _S.update(ET.initial(probe=False))
        _S["engines"] = ET._rows()
        return _S


def _sondea():
    """¿Se puede preguntarle a los programas por su sesión? (la suite no)."""
    return not os.environ.get("WORKSPACE_NO_SESSION_PROBE")


def _fila(eid):
    if not isinstance(eid, str) or eid not in _ET().SUPPORTED:
        return None
    return next((d for d in _estado()["engines"] if d.get("id") == eid), None)


#: estado de la sesión en engines_tui → código estable para la página.
_ESTADOS = {"verified": "listo", "needs_login": "sin_sesion", "needs_model": "falta_modelo",
            "version": "revisar_version", "blocked": "bloqueado", "incomplete": "incompleta",
            "checking": "verificando", None: "verificando", "unknown": "instalado"}
#: opción de la pantalla → acción de aquí (o el dato que es).
_OPCIONES = {"install": "instalar", "reload": "recargar", "session": "verificar",
             "login": "iniciar_sesion", "account": "cuenta", "reinstall": "reinstalar",
             "repair": "reparar", "hub": "en_hub", "version": "version",
             "integration": "integracion"}


def _activa(S, eid):
    """Lo que la pantalla sabe de la sesión (como engines_tui._account)."""
    st = (S["checks"].get(eid) or {}).get("state")
    return {"verified": True, "needs_login": False}.get(st)


def _motor(S, d):
    ET = _ET()
    eid = d["id"]
    instalado = bool(d.get("binaries_ok"))
    chk = (S["checks"].get(eid) or {}).get("state")
    texto, _color = ET.status_of(S, d)
    integ = ET.integration_of(eid) if instalado else None
    if not instalado:
        estado = "no_instalado"
    else:
        estado = _ESTADOS.get(chk, "instalado")
        if estado == "listo" and integ and integ.get("level") == "experimental":
            estado = "experimental"
    opciones = []
    for clave, etiqueta, valor in ET.options(S, d):
        if isinstance(valor, bool):
            tipo = "interruptor"
        elif clave in ET._ACCIONES:
            tipo, valor = "accion", None
        else:
            tipo = "dato"
        opciones.append({"clave": _OPCIONES.get(clave, clave), "etiqueta": _limpio(etiqueta, 80),
                         "tipo": tipo, "valor": valor if isinstance(valor, bool) or valor is None
                         else _limpio(valor, 80)})
    ver = (S.get("versions") or {}).get(eid) if instalado else None
    version = None
    if ver:
        version = {"estado": ver.get("st"), "instalada": _limpio(ver.get("have"), 40),
                   "texto": _limpio(ET.version_label(ver)[0], 80),
                   "nota": _limpio(ET.version_note(ver), 400)}
    integracion = None
    if integ:
        integracion = {"nivel": integ.get("level"), "texto": _limpio(ET.integration_label(integ)[0], 40),
                       "nota": _limpio(ET.integration_note(integ), 500)}
    import engine_install
    rec = engine_install.recipe(eid) or {}
    falta = [_limpio(x, 40) for x in engine_install.missing_prereqs(rec)] if not instalado and rec else []
    receta = bool(rec)
    bloqueo = ""
    if chk in ("blocked", "incomplete"):
        bloqueo = _limpio(((S.get("blocked") or {}).get(eid) or {}).get("why"), 400)
    siguiente = {"no_instalado": "instalar" if receta and not falta else "",
                 "bloqueado": "reinstalar", "incompleta": "reparar",
                 "sin_sesion": "iniciar_sesion", "falta_modelo": "cuenta"}.get(estado, "")
    return {"id": eid, "nombre": _limpio(ET.engine_name(d), 40), "instalado": instalado,
            "estado": estado, "estado_texto": _limpio(texto, 60),
            "listo": estado in ("listo", "experimental"),
            "sesion": {"verified": True, "needs_model": True, "needs_login": False}.get(chk),
            "sesion_texto": _limpio(ET.session_label(chk if instalado else "missing"), 60),
            "version": version, "integracion": integracion, "bloqueo": bloqueo,
            "receta": receta, "login": bool(rec.get("login_cmd")), "falta": falta, "siguiente": siguiente,
            "en_hub": bool(ET.m_enabled(eid)),
            "agentes": [_limpio(a, 40) for a in ET.users_of(eid)][:20],
            "opciones": opciones}


def motores(verificar=False):
    """La sección Motores de agentes: cada motor con su estado, lo que le falta
    y sus opciones (las mismas de la terminal). Como la pantalla, al verlos por
    primera vez verifica la sesión de cada motor instalado EN SEGUNDO PLANO
    (mientras tanto: «verificando»); `verificar` vuelve a preguntar (con la
    caché de 60 s de motores_logica). Además: el motor de cada agente en esta
    máquina y los que ofrece ←→ en el hub."""
    ET = _ET()
    S = _estado()
    if _sondea():
        for d in S["engines"]:
            if d.get("binaries_ok") and (verificar or d["id"] not in S["checks"]):
                ET.verify(S, d["id"])
    agentes = []
    try:
        import agent_state
        for a in agent_state.snapshot().registered():
            agentes.append({"agente": _limpio(a.get("name"), 60), "nombre": _limpio(a.get("display"), 60),
                            "motor": _limpio(a.get("engine"), 30),
                            "origen": "local" if a.get("engine_source") == "local" else "agente"})
    except Exception:
        pass
    try:
        import harnesses
        elegibles = [_limpio(x, 30) for x in harnesses.cycle_options()]
    except Exception:
        elegibles = []
    return {"motores": [_motor(S, d) for d in S["engines"]], "por_agente": agentes,
            "elegibles": elegibles}


def motores_recargar():
    """«ya lo instalé: recargar» / `r`: re-detecta binarios (PATH de una
    terminal nueva), olvida los veredictos de macOS y vuelve a verificar."""
    ET = _ET()
    try:
        import path_refresh
        nuevas = path_refresh.refresh()
    except Exception:
        nuevas = []
    try:
        import agent_state
        agent_state.invalidate()
    except Exception:
        pass
    try:
        import engine_gatekeeper
        engine_gatekeeper.forget()
    except Exception:
        pass
    S = _estado()
    S["checks"] = {}
    ET._INTEGRATION_CACHE.clear()
    if _sondea():
        ET.verify_all(S, force=True)
    msg = _t("localhost.sistema.res.recargados")
    if nuevas:
        msg += " · " + _t("localhost.sistema.res.path", n=len(nuevas))
    return _ok(msg, path=len(nuevas))


def motor_verificar(motor):
    """Enter sobre «sesión»: vuelve a preguntarle al programa (sin caché)."""
    d = _fila(motor)
    if d is None:
        return _err("motor", 404)
    if not d.get("binaries_ok"):
        return _err("no_instalado", 409, n=_ET().engine_name(d))
    if _sondea():
        _ET().verify(_estado(), motor, force=True)
    return _ok(_t("localhost.sistema.res.verificando"))


def motor_en_hub(motor, encendido):
    """«ofrecer en el hub»: si ←→ en el hub lo ofrece al cambiar el motor de
    un agente (engines_tui.toggle_m, con el valor explícito)."""
    d = _fila(motor)
    if d is None:
        return _err("motor", 404)
    if not isinstance(encendido, bool):
        return _err("formato")
    import harnesses
    ids = [x["id"] for x in _estado()["engines"]]
    cur = harnesses.enabled_ids() or list(ids)
    nuevo = [i for i in cur if i != motor] + ([motor] if encendido else [])
    nuevo = [i for i in ids if i in nuevo]
    r = harnesses.set_enabled([] if set(nuevo) == set(ids) else nuevo)
    if not r.get("ok"):
        return _err("guardar", 500)
    n = _ET().engine_name(d)
    return _ok(_t("localhost.sistema.res.hub_on" if encendido else "localhost.sistema.res.hub_off", n=n),
               en_hub=encendido)


def agente_motor(agente, motor):
    """El motor de un agente en ESTA máquina (←→ en el hub / Agentes):
    agent_manage.set_engine, solo con un motor que ←→ ofrece."""
    if not isinstance(agente, str) or not isinstance(motor, str):
        return _err("formato")
    try:
        import agent_state
        nombres = {a.get("name") for a in agent_state.snapshot().registered()}
    except Exception:
        nombres = set()
    if agente not in nombres:
        return _err("agente", 404)
    import harnesses
    if motor not in harnesses.cycle_options():
        return _err("no_elegible", 409, n=_ET().engine_name(motor))
    import agent_manage
    r = agent_manage.set_engine(agente, motor)
    if not r.get("ok"):
        return _err("guardar", 409)
    return _ok(_t("localhost.sistema.res.agente_motor", a=agente, m=_ET().engine_name(motor)))


def ayuda_motores(motor=None):
    """La ayuda de la pantalla (`i`): qué es un motor, quién lo usa y qué hace
    cada opción, del motor elegido."""
    ET = _ET()
    S = dict(_estado())
    ids = [d["id"] for d in S["engines"]]
    if motor is not None and motor not in ids:
        return _err("motor", 404)
    S["engine"] = ids.index(motor) if motor else 0
    return _ok(bloques=_bloques(ET.info_blocks(S, {})))


# ── las acciones que corren un programa del motor ─────────────────────────────
def _pedido(accion, eid, opcion="", activa=None):
    """El pedido de la terminal (engines_tui._enter / _account / _reinstall /
    _account_do) → ((clase, comandos, opciones), None) o (None, (error,
    status, datos)). Los comandos salen SOLO de engine_install y del adapter."""
    ET = _ET()
    d = _fila(eid)
    if d is None:
        return None, ("motor", 404, {})
    n = ET.engine_name(d)
    if accion not in ACCIONES:
        return None, ("accion", 400, {})
    if opcion and (accion != "cuenta" or opcion not in CUENTA):
        return None, ("opcion", 400, {"n": n})
    import engine_install
    rec = engine_install.recipe(eid)
    if accion in ("instalar", "actualizar"):
        if accion == "instalar" and d.get("binaries_ok"):
            return None, ("ya_instalado", 409, {"n": n})
        if accion == "actualizar" and not d.get("binaries_ok"):
            return None, ("no_instalado", 409, {"n": n})
        if not rec:
            return None, ("sin_receta", 409, {"n": n})
        falta = engine_install.missing_prereqs(rec)
        if falta:
            return None, ("falta", 409, {"n": n, "m": ", ".join(falta)})
        return ("install", list(rec["cmd"]), {}), None
    if not d.get("binaries_ok"):
        return None, ("no_instalado", 409, {"n": n})
    if accion in ("reinstalar", "reparar"):
        info = ET.gatekeeper(eid) if accion == "reinstalar" else ET.install_block(eid)
        if not info:
            return None, ("no_aplica", 409, {"n": n})
        cmds = engine_install.reinstall(eid, info)
        if not cmds:
            return None, ("sin_receta", 409, {"n": n})
        return ("reinstall", cmds, {}), None
    if ET.gatekeeper(eid):                 # correrlo abriría el diálogo de macOS
        return None, ("bloqueado", 409, {"n": n})
    if accion == "iniciar_sesion":
        cmd = (rec or {}).get("login_cmd") or []
        return (("login", cmd, {}), None) if cmd else (None, ("sin_flujo", 409, {"n": n}))
    menu = ET._account_menu(eid, activa)
    if menu:
        acts = dict(menu.get("actions") or [])
        if opcion not in acts:
            return None, ("opcion", 400, {"n": n})
        return ("account", acts[opcion], {"cwd": ET._open_dir(eid)} if opcion == "open" else {}), None
    if opcion:
        return None, ("opcion", 400, {"n": n})
    cmd = (rec or {}).get("account_cmd") or []
    return (("login", cmd, {}), None) if cmd else (None, ("sin_flujo", 409, {"n": n}))


def _mostrar(cmd):
    """Los comandos tal cual los ve el socio antes de correrlos (`$ …`, y en
    Windows qué instalador oficial baja Workspace)."""
    import engine_install
    cmds = cmd if cmd and isinstance(cmd[0], (list, tuple)) else [cmd]
    out = []
    for c in cmds:
        out += [_limpio(x, 600) for x in engine_install.shown(list(c), lambda argv: "$ " + shlex.join(argv))]
    return out


def _etiqueta_accion(accion, opcion="", motor=""):
    """El nombre de la acción (el de la terminal para una opción del menú de cuenta)."""
    if accion == "cuenta" and opcion:
        return _limpio(_ET()._acct_label(opcion, {"id": motor}), 60)
    return _t("localhost.ui.sistema.accion." + accion)


def motor_preparar(motor, accion, opcion=""):
    """Lo que la terminal muestra ANTES de correr (la confirmación de instalar,
    reinstalar o reparar; el comando de iniciar sesión o de cuenta): los
    comandos, la fuente oficial, el diálogo del sistema que va a salir y si hay
    que confirmar. No corre nada."""
    if not isinstance(opcion, str):
        return _err("formato")
    S = _estado()
    pedido, e = _pedido(accion, motor, opcion, _activa(S, motor))
    if e:
        return _err(e[0], e[1], **e[2])
    import engine_install
    rec = engine_install.recipe(motor) or {}
    clase, cmd, _o = pedido
    return _ok(motor=motor, accion=accion, opcion=opcion, comandos=_mostrar(cmd),
               fuente=_limpio(rec.get("source"), 200),
               aviso=_limpio(rec.get("aviso"), 400) if clase in ("install", "reinstall") else "",
               nota=_limpio(rec.get("note"), 300) if clase == "install" else "",
               confirmar=accion in _CONFIRMAR or opcion == "switch")


def motor_cuenta(motor):
    """«cuenta y proveedor»: con sesión (o sin saber) en Kiro, GitHub Copilot o
    Cursor, el menú que declara su adapter (ver la cuenta, ver los modelos,
    abrir el motor, cambiar de cuenta…); si no, el flujo oficial de cuenta y
    proveedor del motor, que se corre con motor_correr(motor, "cuenta")."""
    ET = _ET()
    d = _fila(motor)
    if d is None:
        return _err("motor", 404)
    if not d.get("binaries_ok"):
        return _err("no_instalado", 409, n=ET.engine_name(d))
    if ET.gatekeeper(motor):
        return _err("bloqueado", 409, n=ET.engine_name(d))
    S = _estado()
    activa = _activa(S, motor)
    menu = ET._account_menu(motor, activa)
    n = ET.engine_name(d)
    if not menu:
        prep = motor_preparar(motor, "cuenta")
        if not prep.get("ok"):
            return prep
        return _ok(menu=False, comandos=prep["comandos"])
    nota = ET.account_note(menu, n)
    acciones = [{"clave": k, "etiqueta": _limpio(ET._acct_label(k, d), 60), "comandos": _mostrar(c),
                 "confirmar": k == "switch"} for k, c in (menu.get("actions") or []) if k in CUENTA]
    return _ok(menu=True, sesion=activa, nota=_limpio(nota, 300), aviso=_limpio(menu.get("warn"), 400),
               acciones=acciones)


# ── tareas: el programa del motor en una pestaña de herdr ────────────────────
def _dir_tareas():
    import paths
    return os.path.join(paths.state_dir(), "localhost", "motores")


def _ruta(tarea):
    return os.path.join(_dir_tareas(), tarea + ".json")


def _leer_tarea(tarea):
    if not isinstance(tarea, str) or not _TAREA_RE.match(tarea):
        return None
    try:
        with open(_ruta(tarea), encoding="utf-8") as fh:
            t = json.load(fh)
    except (OSError, ValueError):
        return None
    return t if isinstance(t, dict) and t.get("tarea") == tarea else None


def _guardar_tarea(tarea, **campos):
    """Mezcla `campos` en la tarea (bajo candado: la pestaña y el servidor la
    escriben los dos). → la tarea."""
    import atomico
    import olock
    ruta = _ruta(tarea)
    with olock.file_lock(ruta, timeout=3):
        try:
            with open(ruta, encoding="utf-8") as fh:
                t = json.load(fh)
        except (OSError, ValueError):
            t = {"tarea": tarea}
        t.update(campos)
        atomico.escribir(ruta, json.dumps(t, ensure_ascii=False))
    return t


def _barrer_tareas(ahora=None):
    """Las tareas de hace más de un día se borran (solo sus .json: estado)."""
    ahora = time.time() if ahora is None else ahora
    try:
        nombres = os.listdir(_dir_tareas())
    except OSError:
        return
    for f in nombres:
        p = os.path.join(_dir_tareas(), f)
        try:
            if ahora - os.path.getmtime(p) > 86400:
                os.remove(p)
        except OSError:
            pass


def _herdr(args, json_out=True):
    import aviso_panel
    return aviso_panel._herdr(args, json_out=json_out)


def _panel_vivo(t):
    """¿Sigue la pestaña de la tarea? (su panel existe en herdr)."""
    panel = (t or {}).get("panel") or ""
    if not panel:
        return False
    g = _herdr(["pane", "get", panel])
    return ((g or {}).get("pane") or {}).get("pane_id") == panel


def _nuestro_al_frente(t):
    """¿Al frente de su panel corre ESTA tarea (o el programa del motor)? Sin
    eso no se teclea: el panel pudo quedar en una shell."""
    import aviso_panel
    pi = _herdr(["pane", "process-info", "--pane", t["panel"]])
    info = (pi or {}).get("process_info")
    for p in (info or {}).get("foreground_processes") or ():
        linea = str(p.get("cmdline") or " ".join(str(x) for x in (p.get("argv") or ())))
        if "localhost_sistema.py" in linea and t["tarea"] in linea:
            return True
    if aviso_panel.motor_corre(info, t.get("motor") or ""):
        return True
    # Windows: process-info solo ve la shell del panel; vale lo que herdr
    # reconoce como el programa del motor (como aviso_panel.estado_panel)
    agente = aviso_panel.AGENTE_HERDR.get(t.get("motor") or "")
    pane = (_herdr(["pane", "get", t["panel"]]) or {}).get("pane") or {}
    return bool(agente) and pane.get("agent") == agente


def _tarea_en_curso(motor):
    """La tarea de `motor` que sigue abierta (para no abrir dos), o None."""
    try:
        nombres = sorted(os.listdir(_dir_tareas()))
    except OSError:
        return None
    for f in nombres:
        if not f.endswith(".json"):
            continue
        t = _leer_tarea(f[:-5])
        if (t and t.get("motor") == motor and t.get("estado") in ("abriendo", "corriendo")
                and time.time() - float(t.get("inicio") or 0) < TAREA_VIVA_S and _panel_vivo(t)):
            return t
    return None


def _abrir_pestana(tarea, args, etiqueta):
    """Una pestaña NUEVA de herdr (sin foco, como las del menú de sesiones) que
    corre `localhost_sistema.py correr …`. → (tab, panel) o None."""
    import aviso_panel
    if not aviso_panel._exe():
        return None
    creado = _herdr(["tab", "create", "--cwd", HERE, "--label", etiqueta[:40], "--no-focus",
                     "--env", "WORKSPACE_NO_GREETER=1"])
    tab = (creado or {}).get("tab", creado or {})
    panel = tab.get("pane_id") or ""
    if not panel and tab.get("tab_id"):
        lista = _herdr(["pane", "list"]) or {}
        panes = [p for p in lista.get("panes", []) if p.get("tab_id") == tab.get("tab_id")]
        panel = panes[0].get("pane_id") if len(panes) == 1 else ""
    if not panel:
        return None
    cmd = [sys.executable or "python3", os.path.join(HERE, "localhost_sistema.py"), "correr", tarea] + args
    if os.name == "nt":
        import skill_review_visible
        linea = skill_review_visible.pane_command(cmd, windows=True)
    else:
        linea = shlex.join(cmd)
    if _herdr(["pane", "run", panel, linea], json_out=False) is None:
        return None
    return tab.get("tab_id") or "", panel


def motor_correr(motor, accion, opcion="", confirmado=False):
    """Corre una acción del motor como la terminal (instalar, reinstalar,
    reparar, iniciar sesión, cuenta y proveedor o una opción de su menú), en
    una pestaña nueva de herdr. Lo que pide confirmar en la terminal pide aquí
    `confirmado` (tras mostrar motor_preparar). Sin herdr: los comandos y
    dónde hacerlo en el hub. → {"estado": "abriendo"|"ya", "tarea"}."""
    if not isinstance(opcion, str) or not isinstance(confirmado, bool):
        return _err("formato")
    S = _estado()
    activa = _activa(S, motor)
    pedido, e = _pedido(accion, motor, opcion, activa)
    if e:
        return _err(e[0], e[1], **e[2])
    if (accion in _CONFIRMAR or opcion == "switch") and not confirmado:
        return _err("confirmar", 409)
    ET = _ET()
    n = ET.engine_name(motor)
    previa = _tarea_en_curso(motor)
    if previa:
        return _ok(_t("localhost.sistema.res.ya", n=n), estado="ya", tarea=previa["tarea"])
    comandos = _mostrar(pedido[1])
    import aviso_panel
    if not aviso_panel._exe():
        r = _err("sin_herdr", 409, n=n, a=_etiqueta_accion(accion, opcion, motor))
        r["comandos"] = comandos
        return r
    _barrer_tareas()
    tarea = uuid.uuid4().hex[:12]
    etiqueta = "%s · %s" % (n, _etiqueta_accion(accion, opcion, motor))
    _guardar_tarea(tarea, motor=motor, accion=accion, opcion=opcion, estado="abriendo",
                   inicio=time.time(), etiqueta=etiqueta)
    args = [accion, motor, {True: "si", False: "no"}.get(activa, "nd")] + ([opcion] if opcion else [])
    abierta = _abrir_pestana(tarea, args, etiqueta)
    if not abierta:
        _guardar_tarea(tarea, estado="cerrada", fin=time.time())
        r = _err("sin_herdr", 409, n=n, a=_etiqueta_accion(accion, opcion, motor))
        r["comandos"] = comandos
        return r
    _guardar_tarea(tarea, tab=abierta[0], panel=abierta[1])
    return _ok(_t("localhost.sistema.res.abriendo", e=etiqueta), estado="abriendo", tarea=tarea,
               comandos=comandos)


def _pantalla(t):
    """Lo que se ve en la pestaña (texto plano), sin controles, con los
    renglones que parecen llave tapados → (renglones, enlaces, código)."""
    import aviso_panel
    texto = aviso_panel.leer({"panel": t["panel"]}, MAX_LINEAS) or ""
    lineas, enlaces, codigo = [], [], ""
    for ln in texto.replace("\r", "").split("\n")[-MAX_LINEAS:]:
        ln = _limpio(re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", ln), MAX_COL)
        lineas.append(ln)
        for u in _URL_RE.findall(ln):
            u = u.rstrip(".,;:")
            if u not in enlaces and len(enlaces) < 5:
                enlaces.append(u)
        if re.search(r"(?i)code|c[óo]digo", ln):
            m = _CODIGO_RE.search(ln)
            if m:
                codigo = m.group(0)
    while lineas and not lineas[-1].strip():
        lineas.pop()
    return lineas, enlaces, codigo


def _tras_tarea(motor):
    """Al terminar el programa, como al volver a Motores en la terminal:
    PATH nuevo, veredictos de macOS olvidados y la sesión otra vez."""
    ET = _ET()
    try:
        import path_refresh
        path_refresh.refresh()
    except Exception:
        pass
    try:
        import engine_gatekeeper
        engine_gatekeeper.forget()
    except Exception:
        pass
    try:
        import agent_state
        agent_state.invalidate()
    except Exception:
        pass
    ET._INTEGRATION_CACHE.clear()
    S = _estado()
    S["checks"].pop(motor, None)
    if _sondea():
        ET.verify(S, motor, force=True)


def motor_tarea(tarea, resumen=False):
    """Cómo va una acción abierta con motor_correr: su estado (abriendo ·
    corriendo · terminada · cerrada), el resultado al terminar y, mientras su
    pestaña siga, lo que se ve en ella (con los enlaces y el código de
    dispositivo que imprima el programa: así se entra desde la página clásica).
    `resumen` solo consulta el estado y nunca lee la pantalla de configuración."""
    t = _leer_tarea(tarea)
    if not t:
        return _err("tarea", 404)
    vivo = bool(t.get("panel")) and _panel_vivo(t)
    if t.get("estado") in ("abriendo", "corriendo") and t.get("panel") and not vivo:
        t = _guardar_tarea(tarea, estado="cerrada", fin=time.time())
    if t.get("estado") in ("terminada", "cerrada") and not t.get("recargado"):
        _tras_tarea(t.get("motor"))           # como al volver a Motores en la terminal
        t = _guardar_tarea(tarea, recargado=True)
    lineas, enlaces, codigo = _pantalla(t) if vivo and not resumen else ([], [], "")
    return _ok(t.get("mensaje") or "", tarea=tarea, motor=t.get("motor"), accion=t.get("accion"),
               opcion=t.get("opcion") or "", estado=t.get("estado"), etiqueta=_limpio(t.get("etiqueta"), 60),
               resultado=t.get("resultado") or "", bien=t.get("bien"), abierta=vivo,
               pantalla=lineas, enlaces=enlaces, codigo=codigo)


def motor_tarea_teclas(tarea, texto="", teclas=None):
    """Lo que el socio teclea en la página llega al programa de esa pestaña
    (elegir proveedor, confirmar, pegar lo que el programa pida). Solo si al
    frente corre esa tarea o el motor: nunca en una shell. Nada se guarda."""
    teclas = [] if teclas is None else teclas
    if not isinstance(texto, str) or not isinstance(teclas, list) or len(teclas) > MAX_TECLAS \
            or not all(isinstance(k, str) and k.lower() in TECLAS for k in teclas):
        return _err("teclas")
    if len(texto) > MAX_TEXTO:
        return _err("largo", 413)
    if _CONTROL_RE.search(texto):
        return _err("control")
    if not texto and not teclas:
        return _err("formato")
    t = _leer_tarea(tarea)
    if not t:
        return _err("tarea", 404)
    if not t.get("panel") or t.get("estado") == "cerrada" or not _panel_vivo(t) \
            or not _nuestro_al_frente(t):
        return _err("panel", 409)
    if texto and _herdr(["pane", "send-text", t["panel"], texto], json_out=False) is None:
        return _err("panel", 409)
    import aviso_panel
    if teclas and _herdr(["pane", "send-keys", t["panel"]] + [aviso_panel.tecla_herdr(k) for k in teclas],
                         json_out=False) is None:
        return _err("panel", 409)
    return _ok()


def _cerrar_pestana(t):
    """Cierra la pestaña de la tarea: su tab si herdr confirma que el panel es
    de ese tab; si herdr no dio el tab, solo su panel. → True si se cerró."""
    g = _herdr(["pane", "get", t["panel"]]) or {}
    pane = g.get("pane") or {}
    if pane.get("pane_id") != t["panel"]:
        return False
    tab = pane.get("tab_id") or ""
    if tab and tab == t.get("tab"):
        return _herdr(["tab", "close", tab], json_out=False) is not None
    return _herdr(["pane", "close", t["panel"]], json_out=False) is not None


def motor_tarea_cerrar(tarea):
    """Cierra la pestaña de la tarea (si el programa seguía, se corta: como
    cerrar su ventana)."""
    t = _leer_tarea(tarea)
    if not t:
        return _err("tarea", 404)
    if t.get("panel") and _panel_vivo(t) and not _cerrar_pestana(t):
        return _err("panel", 409)
    if t.get("estado") != "terminada":
        _guardar_tarea(tarea, estado="cerrada", fin=time.time())
    return _ok()


def _mensaje_final(eid, clave, detalle):
    n = _ET().engine_name(eid)
    if clave == "problem":
        return str(detalle)
    if clave == "not_ready":
        return _t("localhost.sistema.res.no_listo")
    if clave in ("failed", "blocked"):
        return "✗ " + str(detalle)
    if clave == "installed":
        return "✓ " + _t("localhost.sistema.res.instalado", n=n)
    if clave == "exit":
        return _t("localhost.sistema.res.codigo", rc=detalle)
    return _t("localhost.sistema.res.hecho")


def correr(tarea, accion, motor, activa, opcion=""):
    """Lo que corre DENTRO de la pestaña de herdr (`localhost_sistema.py correr
    …`): valida otra vez, arma el pedido de la terminal y lo corre con
    motores_logica.execute; deja el resultado en la tarea y espera Enter para
    cerrar su pestaña. → código de salida."""
    t = _leer_tarea(tarea)
    if (not t or t.get("motor") != motor or t.get("accion") != accion
            or (t.get("opcion") or "") != opcion or activa not in ("si", "no", "nd")
            or t.get("estado") != "abriendo"):
        print("\n  " + _t("localhost.sistema.driver.invalido"))
        return 2
    ET = _ET()
    pedido, e = _pedido(accion, motor, opcion, {"si": True, "no": False}.get(activa))
    if e:                                  # el motor cambió entre la página y la pestaña
        clave, msg, rc = "problem", _t("localhost.sistema.err." + e[0], **e[2]), None
    else:
        _guardar_tarea(tarea, estado="corriendo")
        print("\n  " + _t("localhost.sistema.driver.titulo", n=ET.engine_name(motor),
                          a=_etiqueta_accion(accion, opcion, motor)))
        clase, cmd, opts = pedido
        try:
            rc, problema, listo = ET.execute(clase, motor, cmd, opts)
            clave, detalle = ET.outcome(clase, motor, rc, problema, listo)
        except Exception as ex:            # jamás deja la tarea «corriendo» para siempre
            rc, clave, detalle = None, "problem", "✗ %s" % type(ex).__name__
        msg = _mensaje_final(motor, clave, detalle)
    _guardar_tarea(tarea, estado="terminada", resultado=clave, bien=clave in ("installed", "done"),
                   rc=rc if isinstance(rc, int) else None, mensaje=msg, fin=time.time())
    print("\n  " + msg)
    try:
        input("\n  " + _t("localhost.sistema.driver.cerrar"))
    except (EOFError, KeyboardInterrupt):
        pass
    t = _leer_tarea(tarea) or {}
    if t.get("panel") and os.environ.get("HERDR_PANE_ID") == t["panel"]:
        _cerrar_pestana(t)
    return 0 if not e else 1


# ── MODELOS DE DECISIÓN (modelos_tui) ─────────────────────────────────────────
def _MT():
    import modelos_tui
    return modelos_tui


_PRUEBAS = {}                    # decisor → el estado de «probar» (el S de modelos_tui)
#: opción de la pantalla → la acción de aquí que la aplica ("" = solo dato).
_ACC_DEC = {"connect": "conectar", "disconnect": "desconectar", "model": "modelo",
            "probe": "probar", "ctx": "contexto", "local": "revisar"}


def _decisor(did):
    MT = _MT()
    return isinstance(did, str) and did in MT.models() and MT.selectable(did)


def _estado_decisor(did):
    MT = _MT()
    if not MT.selectable(did):
        return "no_instalado"
    import decisions as DC
    st = DC.decider_status(did)
    if st.get("ready"):
        try:
            if MT.DT.DV.sin_conexion(did):
                return "sin_conexion"
        except Exception:
            pass
        return "listo"
    return {"no_key": "sin_llave", "ollama_missing": "sin_programa", "ollama_off": "apagado",
            "ollama_old": "version_vieja", "no_model": "sin_modelo",
            "checking": "comprobando"}.get(st.get("detail"), "no_listo")


def _prueba(did):
    S = _PRUEBAS.get(did) or {}
    pr = S.get("probe")
    if not pr:
        return None
    if pr.get("running"):
        return {"estado": "probando", "texto": _limpio(_t("modelos.probe.running"), 80)}
    bien, txt = _MT().probe_text(pr)
    return {"estado": "bien" if bien else "mal", "texto": _limpio(txt, 400)}


def decisores():
    """La sección Modelos de decisión: cada modelo con su estado real, su
    llave (de dónde sale, nunca el valor), modelo, contexto, precio, el
    siguiente paso de uno local, «tu llave, en simple» y la última prueba."""
    from decisions import decisores_activos
    if not decisores_activos():
        return {"ok": False, "error": "en_pausa", "status": 404}
    MT = _MT()
    import decisions as DC
    out = []
    try:
        activo = DC.global_model()
    except Exception:
        activo = ""
    for did in MT.models():
        sel = MT.selectable(did)
        m = DC.meta(did) or {}
        texto, _c = MT.state(did)
        item = {"id": did, "nombre": _limpio(MT.name(did), 40), "seleccionable": sel,
                "estado": _estado_decisor(did), "estado_texto": _limpio(texto, 60),
                "listo": bool(sel and MT.ready(did)), "activo": did == activo,
                "local": MT.is_local(did), "proveedor": _limpio(m.get("provider"), 60),
                "llave": None, "modelo": None, "contexto": None, "precio": [], "local_texto": "",
                "siguiente": "", "notas": [], "sobre_la_llave": [], "prueba": None, "opciones": []}
        if not sel:
            out.append(item)
            continue
        if m.get("key_env"):
            src = DC.key_source(did) or ""
            item["llave"] = {"fuente": {"store": "guardada", "env": "entorno"}.get(src, ""),
                             "variable": _limpio(DC.key_var(did) or DC.key_env(did), 60)
                             if src == "env" else "",
                             "consejo": _limpio(MT.key_tip(did), 200),
                             "donde_crearla": _limpio(MT.keys_line(did), 200)}
            item["sobre_la_llave"] = [{"titulo": _limpio(a, 60), "texto": _limpio(b, 800)}
                                      for a, b in (MT.key_facts(did) or [])]
        if MT.model_list(did):
            item["modelo"] = {"actual": _limpio(MT.current_model(did), 120),
                              "opciones": [{"id": _limpio(i, 120), "pista": _limpio(p, 80)}
                                           for i, p in MT.pick_items(did)][:300]}
        item["contexto"] = {"limite": MT.ctx_limit(did), "base": MT._base_limit(did),
                            "opciones": list(MT._limits(did)), "texto": _limpio(MT._ctx_value(did), 60)}
        item["precio"] = [{"etiqueta": _limpio(a, 40), "valor": _limpio(b, 60)}
                          for _k, a, b in MT._price_rows(did)]
        item["siguiente"] = _limpio(MT.next_step(did), 200)
        item["notas"] = [_limpio(x, 200) for x in MT.local_notes(did)]
        item["prueba"] = _prueba(did)
        for clave, etiqueta, valor in MT.options({}, did):
            item["opciones"].append({"clave": clave, "etiqueta": _limpio(etiqueta, 60),
                                     "valor": _limpio(valor, 80), "accion": _ACC_DEC.get(clave, "")})
            if clave == "local":
                item["local_texto"] = _limpio(valor, 80)
        out.append(item)
    return {"modelos": out}


def decisor_conectar(decisor, llave):
    """«conectar llave»: la guarda en la bóveda de Workspace (el campo
    enmascarado de la terminal). La llave no vuelve en la respuesta ni se
    escribe en ningún registro."""
    from decisions import decisores_activos
    if not decisores_activos():
        return {"ok": False, "error": "en_pausa", "status": 404}
    if not _decisor(decisor):
        return _err("decisor", 404)
    import decisions as DC
    if not DC.meta(decisor).get("key_env"):
        return _err("sin_llave", 409, m=_MT().name(decisor))
    if not isinstance(llave, str) or len(llave) > MAX_LLAVE or _CONTROL_RE.search(llave):
        return _err("llave")
    S = {}
    if not _MT().connect_key(S, decisor, llave):
        r = _err("llave")
        r["mensaje"] = _limpio(S.get("msg"), 300)
        return r
    return _ok(_limpio(S.get("msg"), 400))


def decisor_desconectar(decisor):
    """«desconectar llave»: la borra de esta computadora (la de una variable
    del sistema no se toca: se dice dónde quitarla) y dice cómo revocarla."""
    from decisions import decisores_activos
    if not decisores_activos():
        return {"ok": False, "error": "en_pausa", "status": 404}
    if not _decisor(decisor):
        return _err("decisor", 404)
    import decisions as DC
    MT = _MT()
    if not DC.meta(decisor).get("key_env"):
        return _err("sin_llave", 409, m=MT.name(decisor))
    src = DC.key_source(decisor)
    if src == "env":
        return _err("llave_entorno", 409, var=DC.key_var(decisor) or DC.key_env(decisor))
    if src != "store":
        return _err("no_conectada", 409, m=MT.name(decisor))
    S = {}
    if not MT.disconnect_key(S, decisor):
        return _err("guardar", 500)
    return _ok(_limpio(S.get("msg"), 400), revocar=_limpio(MT.revoke_line(decisor), 300))


def decisor_modelo(decisor, modelo):
    """«modelo»: elige uno de la lista (solo los de decisión)."""
    from decisions import decisores_activos
    if not decisores_activos():
        return {"ok": False, "error": "en_pausa", "status": 404}
    if not _decisor(decisor):
        return _err("decisor", 404)
    MT = _MT()
    if not isinstance(modelo, str) or modelo not in [i for i, _p in MT.pick_items(decisor)]:
        return _err("modelo", 400, m=MT.name(decisor))
    ok, msg = MT.save_model(decisor, modelo)
    if not ok:
        return _err("guardar", 409)
    pr = (_PRUEBAS.get(decisor) or {}).get("probe") or {}
    if not pr.get("running"):
        _PRUEBAS.pop(decisor, None)              # la prueba de antes era de otro modelo
    return _ok(_limpio(msg, 300))


def decisor_contexto(decisor, tokens):
    """«contexto»: un límite menor que el del modelo (más barato y rápido)."""
    from decisions import decisores_activos
    if not decisores_activos():
        return {"ok": False, "error": "en_pausa", "status": 404}
    if not _decisor(decisor):
        return _err("decisor", 404)
    MT = _MT()
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens not in MT._limits(decisor):
        return _err("contexto", 400, m=MT.name(decisor))
    import decision_context as C
    n = MT.set_limit(decisor, tokens)
    return _ok(_t("modelos.msg.limit", m=MT.name(decisor), n=C.fmt_exact(n)))


def decisor_probar(decisor):
    """«probar»: una llamada real chiquita en segundo plano; el resultado sale
    en decisores() (prueba). El primero que queda listo se activa solo."""
    from decisions import decisores_activos
    if not decisores_activos():
        return {"ok": False, "error": "en_pausa", "status": 404}
    if not _decisor(decisor):
        return _err("decisor", 404)
    MT = _MT()
    S = _PRUEBAS.setdefault(decisor, {})
    if MT.busy(S):
        return _err("probando", 409)
    if not MT.ready(decisor):
        paso = MT.next_step(decisor) if MT.is_local(decisor) else ""
        return _err("no_listo", 409, m=MT.name(decisor),
                    x=paso or _t("modelos.msg.probe_needs"))
    if MT.is_local(decisor):
        import decisions as DC
        DC.warm(decisor)
    MT.start_probe(S, decisor)
    return _ok(_t("modelos.probe.running"), estado="probando")


def decisor_revisar(decisor):
    """Enter en el estado de un decisor local (Ollama): vuelve a mirar."""
    from decisions import decisores_activos
    if not decisores_activos():
        return {"ok": False, "error": "en_pausa", "status": 404}
    if not _decisor(decisor):
        return _err("decisor", 404)
    MT = _MT()
    if not MT.is_local(decisor):
        return _err("no_local", 409, m=MT.name(decisor))
    S = {}
    MT._recheck(S, decisor)
    return _ok(_limpio(S.get("msg"), 300), listo=bool(MT.ready(decisor)))


def ayuda_decisores(decisor=None):
    """La ayuda de la pantalla (`i`): qué es, y «tu llave, en simple»."""
    from decisions import decisores_activos
    if not decisores_activos():
        return {"ok": False, "error": "en_pausa", "status": 404}
    MT = _MT()
    if decisor is not None and not _decisor(decisor):
        return _err("decisor", 404)
    que = [b for b in MT.info_blocks(decisor, "que") if not (b[0] == "dim" and str(b[1]).startswith("Tab"))]
    llave = MT.key_blocks(decisor) if decisor else []
    return _ok(bloques=_bloques(que), llave=_bloques(llave))


# ── USUARIOS (usuarios_tui / usuarios) ────────────────────────────────────────
def _agentes():
    """[(nombre, display, cerebro)] — los de la sección Usuarios."""
    import usuarios_tui
    return usuarios_tui._agents()


def _cerebro(agente):
    if not isinstance(agente, str):
        return None
    return next((b for n, _d, b in _agentes() if n == agente), None)


def _fila_usuario(brain, quien):
    import usuarios as U
    if not isinstance(quien, str):
        return None
    return next((r for r in U.resumen(brain) if r["nombre"] == quien), None)


def usuarios():
    """La sección Usuarios: cada agente con cerebro en esta PC y sus usuarios
    (cédula, nombres anteriores, pestañas, «tú», el que parece la misma
    persona) y lo que se puede hacer con cada uno. Solo lee."""
    import usuarios as U
    out = []
    for nombre, display, brain in _agentes():
        try:
            filas = U.resumen(brain)
            error = False
        except Exception:
            filas, error = [], True
        varios = len(filas) > 1
        out.append({"agente": _limpio(nombre, 60), "nombre": _limpio(display, 60), "error": error,
                    "usuarios": [{"nombre": _limpio(r["nombre"], 40), "id": _limpio(r["id"], 20),
                                  "alias": [_limpio(a, 40) for a in r["alias"]][:20],
                                  "pestanas": int(r["pestanas"]), "yo": bool(r["yo"]),
                                  "revision": int(r["revision"]), "parecido": _limpio(r["parecido"], 40),
                                  "opciones": ["soy_yo", "renombrar"] + (["unir"] if varios else [])}
                                 for r in filas[:MAX_USUARIOS]]})
    return {"agentes": out}


def usuarios_asegurar(agente):
    """Lo automático que la sección corre al abrir (y al cambiar de agente):
    cédulas y marcas al día (usuarios.asegurar). Nada se borra."""
    brain = _cerebro(agente)
    if not brain:
        return _err("agente", 404)
    import usuarios as U
    try:
        U.asegurar(brain)
    except Exception:
        return _err("guardar", 500)
    return _ok()


#: el principio del ValueError de usuarios.py → (error, ¿lleva el nombre?)
_ERRORES_U = (("Nombre inválido", "nombre"), ("Conflicto", "conflicto"), ("Ya existe", "existe"),
              ("No hay un usuario", "usuario"), ("Es el mismo", "mismo"),
              ("El perfil de", "perfil"), ("No pude guardar", "guardar"))


def _error_usuarios(e, n=""):
    txt = str(e)
    clave = next((c for prefijo, c in _ERRORES_U if txt.startswith(prefijo)), "guardar")
    return _err(clave, {"guardar": 500, "usuario": 404, "nombre": 400}.get(clave, 409), n=n)


def _nombre_nuevo(texto):
    return isinstance(texto, str) and 0 < len(texto) <= MAX_NOMBRE and not _CONTROL_RE.search(texto)


def usuario_crear(agente, nombre):
    """«+ usuario nuevo»: para otra persona que use este agente."""
    brain = _cerebro(agente)
    if not brain:
        return _err("agente", 404)
    if not _nombre_nuevo(nombre):
        return _err("nombre")
    import usuarios as U
    limpio = U.limpiar_nombre(nombre)
    try:
        c = U.crear(brain, nombre)
    except (ValueError, OSError) as e:
        return _error_usuarios(e, limpio)
    return _ok(_t("localhost.sistema.res.usuario_creado", n=c["nombre"]), nombre=c["nombre"])


def usuario_renombrar(agente, usuario, nuevo, revision=None):
    """«cambiar nombre»: la cédula no cambia; el nombre viejo queda de alias.
    `revision` = la que vio la página (si otra máquina cambió algo: conflicto)."""
    brain = _cerebro(agente)
    if not brain:
        return _err("agente", 404)
    if not _nombre_nuevo(nuevo) or (revision is not None and (not isinstance(revision, int)
                                                              or isinstance(revision, bool))):
        return _err("nombre")
    row = _fila_usuario(brain, usuario)
    if not row:
        return _err("usuario", 404, n=usuario if isinstance(usuario, str) else "")
    import usuarios as U
    try:
        c = U.renombrar(brain, row["id"] or row["nombre"], nuevo, revision=revision)
    except (ValueError, OSError) as e:
        return _error_usuarios(e, U.limpiar_nombre(nuevo) if "Ya existe" in str(e) else row["nombre"])
    return _ok(_t("localhost.sistema.res.usuario_renombrado", o=row["nombre"], n=c["nombre"]),
               nombre=c["nombre"])


def usuario_unir(agente, origen, destino):
    """«unir a otro usuario…»: `origen` es la misma persona que `destino`; sus
    pestañas pasan a destino (la más nueva gana, la otra va a history/) y su
    nombre queda de alias. Nada se borra."""
    brain = _cerebro(agente)
    if not brain:
        return _err("agente", 404)
    o, d = _fila_usuario(brain, origen), _fila_usuario(brain, destino)
    if not o:
        return _err("usuario", 404, n=origen if isinstance(origen, str) else "")
    if not d:
        return _err("usuario", 404, n=destino if isinstance(destino, str) else "")
    if o["nombre"] == d["nombre"]:
        return _err("mismo", 409)
    import usuarios as U
    try:
        r = U.unir(brain, o["nombre"], d["nombre"])
    except (ValueError, OSError) as e:
        return _error_usuarios(e, d["nombre"])
    n = len(r["movidas"]) + len(r["dobles"])
    return _ok(_t("localhost.sistema.res.usuario_unido", o=o["nombre"], d=d["nombre"], n=n),
               pestanas=n)


def usuario_soy_yo(agente, usuario):
    """«soy yo en esta PC»: esta máquina te reconoce como ese usuario."""
    brain = _cerebro(agente)
    if not brain:
        return _err("agente", 404)
    row = _fila_usuario(brain, usuario)
    if not row:
        return _err("usuario", 404, n=usuario if isinstance(usuario, str) else "")
    if row["yo"]:
        return _ok(_t("localhost.sistema.res.ya_eres", n=row["nombre"]))
    import usuarios as U
    try:
        U.elegir(brain, row["nombre"])
    except (ValueError, OSError) as e:
        return _error_usuarios(e, row["nombre"])
    return _ok(_t("localhost.sistema.res.eres", n=row["nombre"]))


def ayuda_usuarios():
    """La ayuda de la pantalla (`i`): la cédula, el nombre y qué hace cada opción."""
    import usuarios_tui
    return _ok(bloques=_bloques(usuarios_tui.info_blocks({}, {})))


# ── la pestaña de herdr ───────────────────────────────────────────────────────
def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) in (5, 6) and a[0] == "correr" and _TAREA_RE.match(a[1]) and a[2] in ACCIONES \
            and a[3] in _ET().SUPPORTED and a[4] in ("si", "no", "nd") \
            and (len(a) == 5 or a[5] in CUENTA):
        return correr(*a[1:])
    print("\n  " + _t("localhost.sistema.driver.invalido"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
