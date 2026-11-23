#!/usr/bin/env python3
"""WORKSPACE · pagina_v2 — la página como VISTA del núcleo (arquitectura nueva, F3).

La página ya no lee la pantalla de los motores ni teclea en su terminal:

  · LEE del núcleo: el registro de eventos de la pestaña (arquitectura/registro.py:
    estado en vivo, herramientas, permisos, terminó), el historial por eventos de la
    conversación (historial_eventos, solo de anexar) y, de los archivos del cerebro,
    lo demás (memoria, skills, pendientes: rutas /api/front/* que ya eran de archivos).
  · ESCRIBE por la capa de control (control/, de B): abrir, mandar, eventos en vivo,
    responder_permiso y parar, con el motor de la conversación, por su vía oficial.
    Claude Code por `claude -p --resume` (D2-c): solo con su terminal cerrada; si
    está abierta, se dice y se ofrece «Ir a la terminal». Un motor sin vía que
    funcione queda en «solo mirar», con «Ir a la terminal». Nada se teclea.

Lo que hablas en la terminal entra a la conversación de la página desde el registro
(lo anotan los hooks del paquete, F1), con su mensaje y su respuesta: sin leer la
pantalla ni fusionar ventanas.

Las respuestas tienen la MISMA forma que las de la página de antes (/api/front/vivo y
/api/conversacion), así el diseño aprobado de web/front/src se queda igual.
"""
import hashlib
import json
import os
import re
import secrets
import sys
import threading
import time

import paths as _paths

NAV = "navegador"
#: modo escritorio (D1-a, idea del dueño): el monito de escritorio tiene SU conversación con cada agente, aparte de la de
#: la página y del hub (pestaña `escritorio`, su historial y su sesión del motor), con su guía y sus manos desde el primer
#: mensaje. La memoria se comparte por el cerebro, no por el historial; «Seguir en la página» lleva el hilo.
ESC = "escritorio"
CANALES = (NAV, ESC)
#: El entorno de cada canal (WORKSPACE_VIA): la página y el hub, «pagina»; el monito, «escritorio». En el registro de la
#: pestaña las dos corridas van «via: pagina» (no son su terminal: registro.eco_de_la_pagina, _de_su_terminal).
VIA_DE = {NAV: "pagina", ESC: "escritorio"}
#: Dónde guarda cada canal, en las preferencias del agente, el número de la conversación de cada conector.
_SESIONES = {NAV: "sesiones", ESC: "sesiones_escritorio"}
#: Cuánto se ve «terminó» antes de volver a «libre» (la página festeja 6 s).
TERMINO_S = 8
#: Skills v11: cuántas de sus últimas herramientas lleva la foto (`hizo`, para «Lo que va haciendo»).
HIZO_MAX = 8
#: Tope de mensajes en cola por agente.
COLA_MAX = 20
#: Cada cuánto el long-poll mira si algo cambió (el registro lo escriben otros procesos).
PASO_S = 0.4
#: El candado global: solo para leer o cambiar el estado de las sesiones, un momento. Nunca se tiene mientras se
#: llama al motor (abrir, mandar, cerrar, parar, un permiso) ni mientras se enciende su servidor: un motor que no
#: abre (Kiro sin contestar) no frena las demás rutas, ni el long-poll, ni cambiar de motor (F3d).
_LOCK = threading.RLock()
_CAMBIO = threading.Condition(_LOCK)
#: agente → la _Sesion de su conversación de siempre (⌂, «navegador»); (agente, pestaña) → la de otra pestaña (H4-a:
#: una de sus sesiones, por su slug en el registro de sesiones). La pestaña es la llave de toda conversación de la
#: página: la del monito de escritorio será una más, (agente, «escritorio»).
#: (junto5: ya lo es. El escritorio es la pestaña «escritorio»: `canal` es solo otra forma de nombrarla.)
_SES = {}
_EPOCA = secrets.token_hex(4)
#: H4-a · los motores cuya sesión de su programa oficial la página retoma por su número (Claude Code `--resume`,
#: Codex `thread/resume`): una de esas sesiones abierta como pestaña es LA MISMA conversación. Las de los demás se
#: abren para mirar (su historial) con «Ir a la terminal» (Hermes le escribe por su ACP: sería un chat aparte).
RETOMA = ("claude-code", "codex")
#: H4-a · una pestaña quieta suelta su motor a los tantos segundos (su app-server o su ACP retienen la conversación:
#: con él abierto, su programa oficial no la puede retomar, «already has an active writer» en Codex). El siguiente
#: mensaje la retoma por su número. Claude Code no retiene nada entre corridas. La de siempre no cambia.
SOLTAR_TAB_S = 20.0
#: H4-a · el nombre de la pestaña de siempre en la tira.
NOMBRE_NAV = "Conversación"
#: La fábrica de conectores (las pruebas ponen la de los motores falsos de B).
FABRICA = None
#: Solo leer (el render en CDP del worktree): nada se escribe en el cerebro ni en el registro.
SOLO_LEER = os.environ.get("WORKSPACE_PAGINA_SOLO_LEER") == "1"
#: Modelos por motor que la capa de control sabe aplicar (solo lo que el conector acepta).
MODELOS = {"claude-code": [("fable", "Fable"), ("opus", "Opus"), ("sonnet", "Sonnet")]}
#: Errores del motor por tipo (la tarjeta de error de la página los explica).
_TIPOS_ERROR = (("creditos", ("credit", "crédito", "billing", "quota exceeded", "insufficient")),
                ("limite", ("rate limit", "usage limit", "limit reached", "límite")),
                ("login", ("login", "log in", "sign in", "authenticat", "iniciar sesión", "unauthorized")),
                ("sobrecarga", ("overloaded", "529", "saturad")),
                ("red", ("network", "connection", "timed out", "conexión")))


def _LW():
    import localhost_web
    return localhost_web


def _control():
    import control
    return control


def _canal(canal):
    """El canal de una conversación: el del escritorio o, si no, el de la página (lo de siempre)."""
    return canal if canal in CANALES else NAV


def _PP():
    import pagina_pestanas
    return pagina_pestanas


def _tab(tab):
    """La pestaña de una conversación: la de siempre (⌂) si no viene."""
    return tab if tab and tab != NAV else NAV


def _t(tab=NAV, canal=NAV):
    """UNA sola llave para toda conversación: su pestaña. La del Compañero de escritorio es la pestaña «escritorio»
    (lo que el modo escritorio llama `canal`); la de siempre, «navegador»; las demás (H4-a), el slug de su sesión."""
    return ESC if _canal(canal) == ESC else _tab(tab)


def _clave(agente, tab=NAV, canal=NAV):
    """La llave de su sesión en _SES: la de siempre es el agente (como siempre); la de otra pestaña (o la del
    escritorio), (agente, pestaña)."""
    t = _t(tab, canal)
    return agente if t == NAV else (agente, t)


def _ses(agente, tab=NAV, canal=NAV):
    return _SES.get(_clave(agente, tab, canal))


# ── el servidor que pide el conector de algunos motores (F3b) ──────────────
#: Los conectores de OpenCode y de Hermes hablan con un servidor local del motor. La página lo
#: enciende como lo hace el probador (control/probar_real.py): `opencode serve` con una clave
#: local que pone ella (OPENCODE_SERVER_PASSWORD) y `hermes serve --isolated` solo del perfil de
#: Workspace, en un puerto libre de 127.0.0.1 y con el cerebro de carpeta. Uno ya encendido para
#: ese cerebro se reusa mientras siga vivo; al apagar la página se cierran los suyos. OpenClaw lo
#: enciende su propio conector (preparar_gateway: el mismo gateway que usan sus pestañas). Se pide por
#: el conector que de verdad escribe (F3e): Hermes por hermes-acp no necesita `hermes serve`.
SERVIDOR_ESPERA_S = 30
#: Los motores cuyo conector necesita un servidor encendido.
CON_SERVIDOR = ("opencode", "hermes")
#: Que el motor no se actualice solo mientras lo usa la página (lo mismo que el probador).
SIN_ACTUALIZAR = {"DISABLE_AUTOUPDATER": "1"}
_SERVIDORES = {}           # (motor, cerebro) → {"proc", "url", "clave"?}
#: Su propio candado (no el global): encender uno, que tarda hasta SERVIDOR_ESPERA_S, solo espera a otro del mismo
#: motor y cerebro.
_SERV_LOCK = threading.Lock()
_SERV_ENCIENDE = {}        # (motor, cerebro) → Lock
#: Para las pruebas: Popen y «¿escucha el puerto?».
POPEN = None
ESCUCHA = None


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


def _receta(motor, puerto):
    """(argv, env extra, opciones del conector) del servidor de `motor`, o None si no usa uno."""
    if motor == "opencode":
        clave = secrets.token_urlsafe(24)
        return (["opencode", "serve", "--port", str(puerto), "--hostname", "127.0.0.1"],
                {"OPENCODE_SERVER_PASSWORD": clave}, {"url": "http://127.0.0.1:%d" % puerto, "clave": clave})
    if motor == "hermes":
        from control.hermes import comando_servidor, url_servidor
        return comando_servidor(puerto), {}, {"url": url_servidor(puerto)}
    return None


def clave_openclaw(agente, brain, wid, canal=NAV):
    """B18: la clave de sesión del gateway de OpenClaw para la página de ESTA pestaña: el agente de este cerebro
    (engines/openclaw.prepare_agent, lo mismo que al abrir su terminal: lo crea si falta, con el cerebro como su carpeta;
    nunca el «main» del perfil) y una clave estable por pestaña, `agent:<id>:ws-pagina-<hash>`, para que la página
    retome la suya. '' si no se pudo (la página abre como antes)."""
    try:
        import hashlib
        from engines import openclaw as oc
        ok, aid = oc.prepare_agent({"name": agente, "_brain": str(brain)})
        if not ok:
            return ""
        clave = "agent:%s:%spagina-%s" % (aid, oc._KEY_PREFIX, hashlib.sha1(str(wid).encode("utf-8")).hexdigest()[:16])
        if not oc._valid_session_key(clave, aid):
            return ""
        _indice_openclaw(brain, wid, clave, canal)
        return clave
    except Exception:
        return ""


def _indice_openclaw(brain, wid, clave, canal=NAV):
    """cable-openclaw: la clave de la página en el índice número → pestaña, marcada «pagina» (la del escritorio,
    «escritorio»). Los avisos y el MCP del plugin de Workspace corren en el gateway, sin el entorno de la pestaña: con
    esto hallan la de la página (y lo suyo no cuenta como su terminal). Solo si cambió (no llena el registro de la
    pestaña en cada apertura). Falla-suave."""
    try:
        from arquitectura import registro
        canal, fila = _canal(canal), registro.indice(clave) or {}
        if (fila.get("brain") == os.path.realpath(str(brain)) and fila.get("pestana") == str(wid)
                and fila.get("via") == VIA_DE[canal]):
            return
        registro.conversacion(brain, wid, "openclaw", clave, "fijado", ws=canal, via=VIA_DE[canal])
    except Exception:
        pass


def nucleo_servidor(motor, brain, env):
    """arq-default: lo del núcleo en el entorno del servidor que la página le prende a un motor (OpenCode): su config
    de la corrida (OPENCODE_CONFIG_CONTENT con el servidor MCP `workspace` y su permiso, lo mismo que su terminal)
    JUNTA con la que ya trae ese entorno («preguntar»). La auditoría real del 18-nov vio que el servidor de la página
    no lo traía. {} si el paquete está apagado, no hay cerebro o algo falla."""
    try:
        from arquitectura import contrato, nucleo, permisos, sesion as S
        if not brain or not S.activo():
            return {}
        ficha = contrato.ficha(motor)
        pkg = S.instalar(brain)
        valores = {"paquete": pkg[ficha["paquete"]["formato"]], "cerebro": str(brain), "python": S.python()}
        nuevo = {}
        _argv, nuevo, _info = nucleo.aplicar(motor, brain, [motor], nuevo, valores, ficha=ficha)
        if motor == "opencode" and env.get("WORKSPACE_VIA") == VIA_DE[ESC]:
            # modo escritorio: su servidor (el de la pestaña del escritorio) pregunta todo lo que no es libre; las manos,
            # si van, aprobadas por nombre
            cfg = permisos._junta(json.loads(nuevo.get("OPENCODE_CONFIG_CONTENT") or "{}"), estricto_opencode())
            if manos_para(motor):
                cfg = permisos._junta(cfg, manos_opencode())
            nuevo["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
        out = {}
        for k, v in nuevo.items():
            antes = env.get(k)
            try:
                a, b = json.loads(antes) if antes else {}, json.loads(v)
                out[k] = json.dumps(permisos._junta(a, b), ensure_ascii=False, separators=(",", ":")) \
                    if isinstance(a, dict) and isinstance(b, dict) else v
            except ValueError:
                out[k] = v
        return out
    except Exception:
        return {}


def _entorno_servidor(motor, extra, pestana):
    """El entorno del servidor del motor: sin la identidad de otra pestaña ni de otra sesión (control/entorno, punto
    F), con la de la pestaña de la página y, en OpenCode, «preguntar» antes de editar y de correr comandos (su config
    de sesión, opencode.entorno_servidor): sin ella corría todo sin pedir permiso. Las tarjetas de permiso de la
    página contestan."""
    base = dict(os.environ, **SIN_ACTUALIZAR)
    base["WORKSPACE_VIA"] = VIA_DE[_canal((pestana or {}).get("ws"))]
    if motor == "opencode":
        from control import opencode as _oc
        env = _oc.entorno_servidor("preguntar", base=base, pestana=pestana)
        env.update(nucleo_servidor(motor, (pestana or {}).get("cerebro"), env))
    else:
        from control import entorno as _en
        env = _en.para_motor(base, pestana, motor)
    env.update(extra)
    return env


def servidor_de(motor, brain, pestana=None):
    """Las opciones del conector de `motor` para su servidor ({} si no usa uno): el que ya está
    encendido para este cerebro o uno que la página enciende ahora. Levanta si no arrancó. El escritorio tiene el
    suyo (su pestaña, su entorno y sus manos): (motor, cerebro, «escritorio»)."""
    if motor not in CON_SERVIDOR:
        return {}
    clave = (motor, os.path.realpath(str(brain)))
    if _canal((pestana or {}).get("ws")) == ESC:
        clave += (ESC,)
    with _SERV_LOCK:
        enciende = _SERV_ENCIENDE.setdefault(clave, threading.Lock())
    with enciende:
        with _SERV_LOCK:
            s = _SERVIDORES.get(clave)
            if s and s["proc"].poll() is None:
                return dict(s["opciones"])
            _SERVIDORES.pop(clave, None)
        puerto = _puerto_libre()
        receta = _receta(motor, puerto)
        if not receta:
            return {}
        cmd, extra, opciones = receta
        from control.canal import opciones_proceso, resolver
        from control import hijos
        env = _entorno_servidor(motor, extra, pestana)
        import subprocess
        # el de una página anterior que murió sin pasar por el apagado (SIGKILL): se cierra antes de encender otro
        _anotado(hijos.limpiar_huerfano, clave)
        # su propio grupo (cerrarlo cierra lo que corrió) y, en Windows, sin ventana
        proc = (POPEN or subprocess.Popen)(resolver(cmd), cwd=str(brain), env=env, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           **opciones_proceso())
        escucha, fin = ESCUCHA or _escucha, time.time() + SERVIDOR_ESPERA_S
        while time.time() < fin and proc.poll() is None and not escucha(puerto):
            time.sleep(0.25)
        if proc.poll() is not None or not escucha(puerto):
            _cerrar_proc(proc)
            raise RuntimeError("no arrancó el servidor de %s (%s)" % (motor, " ".join(cmd[:2])))
        with _SERV_LOCK:
            _SERVIDORES[clave] = {"proc": proc, "opciones": opciones}
        _anotado(hijos.registrar, clave, getattr(proc, "pid", None))   # dueño: este proceso (control/hijos)
        _cierre_al_salir()
        return dict(opciones)


def _anotado(fn, clave, *pid):
    """Los servidores de la página van anotados como los procesos de la capa de control (control/hijos): con su
    dueño (este proceso). Falla-suave."""
    try:
        motor, brain = clave[:2]
        return fn("pagina-" + motor + ("-" + ESC if clave[2:] == (ESC,) else ""), brain, *pid)
    except Exception:
        return None


_AL_SALIR = []


def _cierre_al_salir():
    """atexit: al salir el proceso de la página SIN pasar por «Apagar» (Ctrl+C, sys.exit, una señal que
    localhost_web.serve convierte en salida), sus servidores se cierran. Se registra una vez, con el primero."""
    if not _AL_SALIR:
        import atexit
        atexit.register(cerrar_servidores)
        _AL_SALIR.append(True)


def _cerrar_proc(proc):
    """Cierra un servidor que encendió la página con lo que haya corrido: su grupo (POSIX) o su árbol (Windows: con
    `opencode.cmd` de npm, terminate() mataba solo cmd.exe y el servidor seguía escuchando)."""
    try:
        pid = getattr(proc, "pid", None)
        if proc.poll() is None and isinstance(pid, int):
            if os.name == "nt":                         # pragma: no cover
                import arbol_procesos
                arbol_procesos.matar_arbol(proc)
            else:
                from control import hijos
                hijos.matar_grupo(pid, pid, gracia=5.0)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(10)
            except Exception:
                proc.kill()
    except Exception:
        pass


def cerrar_servidores():
    """Cierra los servidores que encendió la página (nunca los de otros). Lo llaman «Apagar» y atexit."""
    with _SERV_LOCK:
        servidores = list(_SERVIDORES.items())
        _SERVIDORES.clear()
    for clave, s in servidores:
        _cerrar_proc(s["proc"])
        _anotado(_soltar_anotado, clave, getattr(s["proc"], "pid", None))


def _soltar_anotado(motor, brain, pid):
    from control import hijos
    hijos.soltar(motor, brain, pid)


def _cerrar_con(con, reinicio=False):
    """Cierra un conector, fuera del candado global (cerrar espera al proceso del motor). `reinicio`: la página se
    apaga o se reinicia (E9: los permisos que esperaban quedan interrumpidos, no negados)."""
    if con is not None:
        try:
            if reinicio:
                con.cerrar(reinicio=True)
            else:
                con.cerrar()
        except Exception:
            pass


#: Los motores que la capa de control abre por ACP con el MCP núcleo en su session/new.
NUCLEO_ACP = ("copilot", "cursor", "kiro")
# banderas de la ficha que el modo ACP de cada motor rechaza (probado con el motor real)
ACP_NO_ACEPTA = {"kiro": ("--trust-tools",)}
#: arq-default (auditoría real 18-nov): por ACP, Copilot no llamó al servidor de su session/new y pidió leer
#: ~/.copilot; por su terminal, con el plugin del paquete (--plugin-dir), el MCP, los avisos y las skills funcionaron.
#: Su ACP abre con el mismo plugin (el servidor viaja en él: sin session/new, para no declararlo dos veces). A
#: VERIFICAR con arquitectura.auditoria: si su modo ACP no aceptara la bandera, va a ACP_NO_ACEPTA.
ACP_CON_PLUGIN = ("copilot",)
#: Solo el servidor MCP del núcleo en la sesión ACP (sin el paquete al abrir ni el tono: esos siguen como hoy). Hermes:
#: su terminal no tiene vía por sesión, pero su ACP declara servidores en session/new (protocolo ACP). Antigravity (B16,
#: cacería 19-nov): la página le hablaba por `agy acp` con mcpServers vacío; el verificador comprobó que `agy acp` carga
#: el núcleo por session/new (listó todas las del núcleo y memoria_buscar funcionó). OpenClaw NO (cable-openclaw, 19-nov):
#: su puente rechaza los servidores por sesión («ACP bridge mode does not support per-session MCP servers», -32603
#: «Internal error»: la página no abría con el paquete encendido); su MCP llega por el plugin de su agente.
SOLO_MCP_ACP = {"hermes": "hermes-acp", "antigravity": "antigravity"}
#: El núcleo viaja en el entorno de SU servidor, no en las opciones del conector (nucleo_para da {}): OpenCode, con
#: OPENCODE_CONFIG_CONTENT (su ficha, `nucleo`), en el de su terminal (el lanzador) y en el que enciende la página
#: (nucleo_servidor, arq-default). OpenClaw (cable-openclaw): en el plugin compartido, que su gateway carga para la
#: página y para la terminal (engines/openclaw.asegurar_plugin, que corre clave_openclaw).
NUCLEO_EN_SU_SERVIDOR = ("opencode", "openclaw")


def nucleo_previsto(motor):
    """skills-cierre (Fix 4): ¿la corrida de la página de `motor` va a traer el núcleo (MCP workspace)? La misma regla
    que nucleo_para y trae_nucleo, sin abrir nada (la instrucción de una skill puede ser lo primero que abre su motor).
    Con el paquete apagado, no: no hay herramientas de Workspace."""
    if not _paquete_activo():
        return False
    if motor == "claude-code" or motor in NUCLEO_ACP or motor in SOLO_MCP_ACP or motor in NUCLEO_EN_SU_SERVIDOR:
        return True
    if motor == "codex":
        try:
            from arquitectura import contrato
            return bool((contrato.ficha(motor).get("sesion") or {}).get("mcp_del_nucleo"))
        except Exception:
            return False
    return False


def herramientas_de(s):
    """¿Tiene la conversación de la página de `s` las herramientas del núcleo (reportar_avance, usar_skill…)? La de su
    conector abierto (trae_nucleo, con el paquete encendido); sin él, la que tendrá al abrirlo (nucleo_previsto). Así
    la instrucción de la skill dice lo mismo que la guía de chat (antes la elegía una lista vieja, memoria_mcp.MOTORES)."""
    if s is None or not _paquete_activo():
        return False
    with _LOCK:
        con = s.con
        if con is not None and con.estado() != "cerrado":
            return bool(s.con_nucleo)
    return nucleo_previsto(s.motor)


def trae_nucleo(motor, nucleo):
    """agente-interfaz: ¿trae esta corrida de la página el núcleo? Si no, el manual del respaldo (manual_respaldo).
    Con el paquete apagado no hay a qué remitirlo."""
    return bool(nucleo) or not _paquete_activo() or motor in NUCLEO_EN_SU_SERVIDOR


# ── modo escritorio: las manos (ver y señalar), solo en las sesiones del escritorio ──
#: El servidor MCP de las manos del escritorio (escritorio/manos_mcp.py: lo que mira y señala la app del monito, que es
#: la que tiene los permisos de la Mac). Va SOLO en las sesiones del escritorio, por la misma vía que el del núcleo en
#: cada motor. Si el archivo todavía no está, no va, y la guía no las ofrece.
MANOS_NOMBRE = "escritorio"
#: Las de ver y señalar, aprobadas por nombre donde el motor lo deja (el permiso de verdad es el de la Mac, y el monito
#: enseña el ojito mientras mira), E1 encargar (solo PROPONE: la app enseña su tarjeta y nada pasa sin tu clic) y
#: `actuar` (A0): su OK es la tarjeta de la app del monito (la arma con lo que dice el sistema; lo rojo nunca), así no
#: hay dos tarjetas para lo mismo.
MANOS_LIBRES = ("contexto_escritorio", "leer_ventana", "ver_pantalla", "senalar", "encargar", "actuar",
                # ronda 2, carril 6 (manos de trabajo): como actuar, su OK es la ficha de la app del monito (su portero)
                "buscar_archivo", "abrir", "redactar_correo")
#: Lo más que espera un motor a una herramienta de las manos (escritorio/manos_mcp.TOPES: señalar, 75 s, + margen).
MANOS_TOPE_S = 140
#: OpenClaw rechaza servidores MCP por sesión (cable-openclaw): ahí no van (su guía no las ofrece).
SIN_MANOS = ("openclaw", "openclaw-acp")
#: Para las pruebas: otra ruta del servidor de las manos.
MANOS = None


def manos_mcp():
    """La ruta del servidor de las manos (escritorio/manos_mcp.py) si existe, o ''."""
    r = MANOS or os.path.join(os.path.dirname(os.path.abspath(__file__)), "escritorio", "manos_mcp.py")
    return r if os.path.isfile(r) else ""


def manos_para(motor):
    """¿Las sesiones del escritorio de `motor` llevan las manos? (el servidor existe, su vía las acepta y su motor
    pregunta antes de actuar por la vía de la página: decisión del dueño, 21-nov. Los que escriben o corren comandos
    sin preguntar por esa vía, como OpenClaw, Hermes o Cursor, no miran tu pantalla desde el monito: sin_manos_de)."""
    return bool(manos_mcp()) and motor not in SIN_MANOS and motor_de_control(motor) not in SIN_MANOS \
        and not sin_preguntar_de(motor)


def sin_manos_de(motor):
    """Modo escritorio: la línea amable de por qué este agente no puede mirar tu pantalla desde el monito todavía
    ('' si sí puede, o si las manos no están instaladas)."""
    if not manos_mcp() or manos_para(motor):
        return ""
    return ("Con %s, este agente todavía no puede mirar tu pantalla desde Compañero (su motor hace cosas sin "
            "preguntarte). Sí puedes platicar con él." % _nombre_motor(motor))


#: Modo escritorio: las banderas de preaprobación de una sesión que no van en la del monito (ahí todo lo que no es libre
#: pregunta, y lo libre lo aprueba la capa de control por nombre).
PREAPRUEBA = ("--allow-tool", "--allow-all-tools", "--allow-all", "--trust-tools", "--trust-all-tools", "--yolo",
              "--auto-review", "--force")


def sin_preaprobar(args):
    """Los argumentos sin sus banderas de preaprobación (las dos formas: «--x=v» y «--x v»)."""
    out, saltar = [], False
    for a in args or []:
        if saltar:
            saltar = False
            continue
        a = str(a)
        if any(a == b or a.startswith(b + "=") for b in PREAPRUEBA):
            saltar = a in PREAPRUEBA and a not in ("--allow-all-tools", "--allow-all", "--trust-all-tools", "--yolo",
                                                   "--auto-review", "--force")
            continue
        out.append(a)
    return out


def estricto_claude(extra):
    """Modo escritorio en Claude Code: su --allowedTools de todo el núcleo se cambia por lo libre del monito."""
    from control import propias
    E = propias.politica_escritorio()
    out = [a for a in (extra or []) if not str(a).startswith("--allowedTools")]
    return out + ["--allowedTools=" + ",".join(E.permitidas_claude())]


def _entorno_manos(env):
    """De la pestaña, lo que lleva el servidor de las manos (sabe de qué agente y qué conversación es)."""
    return {k: str(v) for k, v in sorted((env or {}).items())
            if k in ("WORKSPACE_ROOT", "WORKSPACE_BRAIN", "WORKSPACE_WID", "WORKSPACE_WS", "WORKSPACE_ENGINE",
                     "WORKSPACE_VIA")}


def manos_opencode():
    """Las manos en la config de la corrida de OpenCode (su forma v2, como el núcleo: sin Code Mode) y aprobadas por
    nombre (sus herramientas se llaman <servidor>_<herramienta>)."""
    return {"mcp": {"servers": {MANOS_NOMBRE: {"type": "local", "command": [sys.executable, manos_mcp()],
                                               "enabled": True, "codemode": False}}},
            "permission": {"%s_%s" % (MANOS_NOMBRE, h): "allow" for h in MANOS_LIBRES}}


def estricto_opencode():
    """Modo escritorio en OpenCode: preguntar antes de editar, correr, ir a internet, salir de su carpeta y usar del
    núcleo lo que no es libre en el monito (sus herramientas se llaman <servidor>_<herramienta>). A VERIFICAR en vivo."""
    from control import propias
    E = propias.politica_escritorio()
    # ronda 2 · E8: sin ayudantes en el monito (su herramienta `task`, negada en la config de ESTA corrida)
    p = {"edit": "ask", "bash": "ask", "webfetch": "ask", "external_directory": "ask", "task": "deny"}
    try:
        from arquitectura import nucleo_mcp
        for h in nucleo_mcp.herramientas():
            if h.get("name") not in E.LIBRES_NUCLEO:
                p["workspace_%s" % h["name"]] = "ask"
    except Exception:
        pass
    return {"permission": p}


def _con_manos(motor, out):
    """Las opciones del núcleo de una sesión del escritorio, con las manos por la vía del núcleo en ese motor:
    Claude Code, su --mcp-config de la corrida y sus herramientas en --allowedTools; Codex, `-c mcp_servers.…` de su
    app-server; los de ACP, un servidor más en su session/new (`mcp_servers`)."""
    env = _entorno_manos(out.get("env"))
    if motor == "claude-code":
        mcp = {"mcpServers": {MANOS_NOMBRE: {"type": "stdio", "command": sys.executable, "args": [manos_mcp()],
                                             "env": env}}}
        extra = list(out.get("extra") or [])
        antes = [a for a in extra if str(a).startswith("--allowedTools=")]
        libres = [t for a in antes for t in str(a).split("=", 1)[1].split(",") if t]
        libres += [t for t in ("mcp__%s__%s" % (MANOS_NOMBRE, h) for h in MANOS_LIBRES) if t not in libres]
        out["extra"] = [a for a in extra if not str(a).startswith("--allowedTools=")] + [
            "--mcp-config", json.dumps(mcp, ensure_ascii=False, separators=(",", ":")),
            "--allowedTools=" + ",".join(libres)]                 # una sola lista (con lo libre del monito)
        return out
    if motor == "codex":
        cmd = list(out.get("cmd") or ["codex", "app-server"])
        pre = "mcp_servers.%s." % MANOS_NOMBRE
        manos = ["-c", pre + "command=" + json.dumps(sys.executable), "-c", pre + "args=" + json.dumps([manos_mcp()]),
                 "-c", pre + "env_vars=" + json.dumps(sorted(env)),
                 # Codex corta una herramienta MCP a los 60 s; señalar puede durar hasta 75 (sus pasos): si la cortara,
                 # el turno seguiría sin esperar a que el monito regrese
                 "-c", pre + "tool_timeout_sec=%d" % MANOS_TOPE_S]
        out["cmd"] = cmd[:1] + manos + cmd[1:]
        return out
    out["mcp_servers"] = list(out.get("mcp_servers") or []) + [
        {"name": MANOS_NOMBRE, "command": sys.executable, "args": [manos_mcp()],
         "env": [{"name": k, "value": v} for k, v in sorted(env.items())]}]
    return out


def nucleo_para(motor, brain, wid, agente="", canal=NAV, ws=NAV):
    """F6: las opciones de la capa de control para que una corrida de la página traiga el núcleo como
    una de su terminal (con el paquete encendido): el entorno de su pestaña (marcado WORKSPACE_VIA=pagina:
    sus hooks no cuentan como su terminal) y, según su vía, el plugin del paquete con el MCP preaprobado
    y el tono (Claude Code: `extra`) o el servidor `workspace` en su sesión ACP (`mcp_servers`).
    modo escritorio (`canal` «escritorio»): su pestaña, WORKSPACE_VIA=escritorio y, si están, las manos (_con_manos).
    H4-a (`ws`): la pestaña de la página que la pide (su WORKSPACE_WS).
    {} si el paquete está apagado, el motor no va por aquí o algo falla."""
    canal = _canal(_t(ws, canal))
    out = _nucleo_para(motor, brain, wid, agente, canal, ws)
    if out and canal == ESC and manos_para(motor):
        try:
            return _con_manos(motor, out)
        except Exception:
            return out
    return out


def _nucleo_para(motor, brain, wid, agente, canal, ws=NAV):
    import sys
    try:
        from arquitectura import contrato, nucleo, sesion as S
        try:
            # arq-default: los archivos del proyecto de su vía por sesión (hooks, skills), como al abrir su terminal
            S.preparar_proyecto(motor, brain)
        except Exception:
            pass
        ficha = contrato.ficha(motor)
        s = ficha.get("sesion") or {}
        codex = motor == "codex" and s.get("mcp_del_nucleo")
        if not S.activo() or (motor != "claude-code" and motor not in NUCLEO_ACP and motor not in SOLO_MCP_ACP
                              and not codex):
            return {}
        pkg = S.instalar(brain)                 # F7: el de este cerebro (sus skills en el plugin)
        valores = {"paquete": pkg[ficha["paquete"]["formato"]], "cerebro": str(brain), "python": S.python()}
        pestana_env = {"WORKSPACE_BRAIN": str(brain), "WORKSPACE_WID": str(wid), "WORKSPACE_WS": ESC if canal == ESC else (ws or NAV),
                       "WORKSPACE_ENGINE": motor, "WORKSPACE_ROOT": os.path.dirname(os.path.abspath(__file__)),
                       "WORKSPACE_VIA": VIA_DE[canal]}
        if canal == ESC and manos_para(motor):
            pestana_env["WORKSPACE_MANOS"] = "1"        # la guía del escritorio (la de «argv») ofrece las manos
        env = dict(os.environ, **pestana_env)
        if motor == "claude-code":
            argv, env, _info = nucleo.aplicar(motor, brain, ["claude"], env, valores, ficha=ficha)
            extra = ["--plugin-dir", valores["paquete"]] + argv[1:]
            return {"extra": estricto_claude(extra) if canal == ESC else extra, "env": env}
        if codex:
            # arq-default: su app-server con el mismo servidor MCP que su terminal (-c mcp_servers.workspace…, con
            # env_vars: Codex le recorta el entorno a sus servidores MCP)
            argv, env, _hubo = nucleo.solo_mcp(motor, brain, ["codex", "app-server"], env, valores, ficha=ficha)
            return {"cmd": argv, "env": env}
        mcp = {"name": "workspace", "command": sys.executable,
               "args": [os.path.join(valores["paquete"], "lanzador", "mcp.py")],
               "env": [{"name": k, "value": env[k]} for k in sorted(pestana_env)]}
        if motor in SOLO_MCP_ACP:
            out = {"env": env, "mcp_servers": [mcp]}
            if motor == "hermes":
                # cable-hermes: su ACP en el perfil PROPIO del agente (sus skills, sus avisos y su MCP, los de su
                # terminal). Ese perfil ya trae el servidor `workspace`: otro con el mismo nombre en su session/new lo
                # tapa y el modelo llamaba al tapado («MCP server 'workspace' is not connected», auditoría 19-nov), así
                # que va solo el del perfil (la pestaña de cada llamada: engines/hermes.pestana_para_mcp). Sin ese
                # perfil, el de Workspace con el servidor en su sesión, como antes.
                try:
                    from engines import hermes as _hm
                    out["cmd"] = _hm.cmd_acp(brain, agente, valores["paquete"])
                    out.pop("mcp_servers")
                except Exception:
                    pass
            return out
        from control import acp
        base = list(acp.FICHAS[motor]["cmd"])
        # por ACP el servidor va en su session/new: los archivos del proyecto para el MCP (los de su terminal) no
        argv, env, _info = nucleo.aplicar(motor, brain, base[:1], env, valores, ficha=ficha, archivos=False)
        mcp["env"] += [{"name": k, "value": env[k]} for k in (nucleo.ENV_AL_ABRIR, nucleo.ENV_TONO) if k in env]
        # su preaprobación por sesión (la de su ficha) va al final de su comando ACP, salvo las banderas que
        # su modo ACP no acepta (verificado en real, 18-nov: `kiro-cli acp --agent-engine v3` rechaza
        # «--trust-tools»; el MCP de la sesión ACP se declara en `mcp_servers`, sin esa bandera)
        extra = [a for a in argv[1:] if not any(a == b or a.startswith(b + "=") for b in ACP_NO_ACEPTA.get(motor, ()))]
        if canal == ESC:
            extra = sin_preaprobar(extra)        # modo escritorio: lo que no es libre pregunta (y lo libre, por nombre)
        if motor in ACP_CON_PLUGIN:
            return {"env": env, "cmd": base + ["--plugin-dir", valores["paquete"]] + extra}
        return {"env": env, "mcp_servers": [mcp], "cmd": base + extra}
    except Exception:
        return {}


def motor_de_control(motor):
    """El conector por el que la página le escribe a `motor`, según la capa de control (control.para_escribir, de B):
    él mismo; o, si está en «solo mirar» y tiene `escribir_por`, ese otro: Hermes → hermes-acp, OpenClaw →
    openclaw-acp (chats aparte de los de su terminal: el chip lo dice). Sin ninguno, el suyo, y queda en solo
    mirar."""
    try:
        return _control().para_escribir(motor) or motor
    except Exception:
        return motor


def solo_mirar_de(motor, nombre):
    """El aviso de «solo mirar» si la capa de control no deja escribirle a este motor, o ''."""
    C = _control()
    m = motor_de_control(motor)
    if m not in C.VIAS:
        return "%s no tiene una vía oficial para escribirle desde aquí." % nombre
    if not C.puede_escribir(m):
        return C.VIAS[m].get("aviso") or "%s: desde aquí solo se mira." % nombre
    return ""


# ── F4: la misma conversación que su terminal (control/compartido) ─────────
#: Los motores cuya terminal, abierta, comparte su conversación con la página: OpenCode (la TUI va a un
#: servidor encontrable de su pestaña: la página se conecta a ESE y a ESA sesión) y OpenClaw (la página
#: entra a la clave de sesión de su TUI por su puente ACP). Con la terminal cerrada, lo de antes.
COMPARTIBLES = ("opencode", "openclaw")
#: Los que la página sigue EN VIVO con la terminal abierta, aunque no le hayas escrito: sus eventos
#: traen también los turnos de la terminal (OpenCode: session.inbox.enqueued, verificado en real).
SIGUE_EN_VIVO = ("opencode",)
#: Si unirse a su terminal no salió, no se reintenta antes de esto (s).
SEGUIR_REINTENTO_S = 15
#: F4c · para las pruebas: (url, clave, sesion, cwd) → turnos de lo que ya había (si no, control.opencode.historial).
HISTORIAL = None
#: F4c: lo que se espera sin eventos, recién unida a su terminal, para saber que no está a media respuesta (s).
AL_DIA_CALMA_S = 1.5


def terminal_compartida(motor, brain, wid, limpiar=True):
    """La terminal abierta de esa pestaña con la que la página comparte la conversación
    ({url, clave, sesion, …} de control/compartido), o None (cerrada, o el motor no comparte).
    `limpiar=False` con el candado global tomado: no apaga el servidor huérfano de una que murió."""
    if motor not in COMPARTIBLES:
        return None
    try:
        from control import compartido
        t = compartido.buscar(motor, brain, wid, limpiar=limpiar)
    except Exception:
        return None
    return t if t and t.get("sesion") else None


# ── la pestaña de la página y su motor ─────────────────────────────────────
_CACHE = {}                # clave → (hora, valor): lo que cuesta leer de los archivos del cerebro
CACHE_S = 5.0


def _cacheado(clave, fn):
    ahora = time.time()
    c = _CACHE.get(clave)
    if c and ahora - c[0] < CACHE_S:
        return c[1]
    v = fn()
    _CACHE[clave] = (ahora, v)
    return v


def cerebros():
    return _cacheado("cerebros", lambda: list(_LW()._cerebros()))


def cerebro(agente):
    """El cerebro del agente. Si no está en la lista guardada (CACHE_S), se lee de nuevo: lo acaban de crear o cargar.
    RC 0.10.0 (en vivo, 23-nov): con la página o el hub preguntando por su estado, el primer mensaje a un agente nacido
    hacía menos de 5 s salía 404 «Esa pestaña ya no está» (lo mismo que ya hace localhost_web._cerebro)."""
    b = dict(cerebros()).get(agente)
    if b is None and agente:
        _CACHE.pop("cerebros", None)
        b = dict(cerebros()).get(agente)
    return b


def pestana(agente, crear=False, canal=NAV, tab=NAV):
    """(cerebro, bt, wid) de la conversación de la página del agente (o la del escritorio, con `canal`), o None.
    `crear`: la siembra si todavía no existe (nace con el primer mensaje). `tab` (H4-a): la de otra pestaña, una de sus
    sesiones por su slug (esa no se siembra aquí: la crea «+», tab_abrir)."""
    canal = _canal(_t(tab, canal))
    if canal == NAV and _tab(tab) != NAV:
        return _cacheado(("pestana", agente, tab), lambda: _pestana_de_sesion(agente, tab))
    clave = ("pestana", agente) if canal == NAV else ("pestana", agente, canal)
    if not crear:
        return _cacheado(clave, lambda: _pestana(agente, False) if canal == NAV else _pestana(agente, False, canal))
    p = _pestana(agente, True) if canal == NAV else _pestana(agente, True, canal)
    _CACHE[clave] = (time.time(), p)
    return p


def _pestana(agente, crear, canal=NAV):
    import sessions_registry as reg
    LW = _LW()
    brain = cerebro(agente)
    if not brain:
        return None
    esc = _canal(canal) == ESC
    for vuelta in (0, 1):
        try:
            soc = reg.socio(brain)
            tabs = LW._pestanas_escritorio(brain, soc) if esc else LW._pestanas_web(brain, soc)
            bt = next((t for t in tabs if t.get("slug") == (ESC if esc else NAV)), None)
        except Exception:
            bt = None
        if bt:
            return brain, bt, LW._wid_de(bt)
        if not crear or vuelta or not (LW._sembrar_escritorio(agente) if esc else LW._sembrar_navegador(agente)):
            return None
    return None


def _pestana_de_sesion(agente, slug):
    """H4-a · (cerebro, bt, wid) de la sesión `slug` del agente (también si está archivada), o None. Nunca la de siempre
    ni la del monito de escritorio."""
    import agent_brand
    import sessions_registry as reg
    LW = _LW()
    brain = cerebro(agente)
    if not brain or not _PP().valido(slug):
        return None
    try:
        bt = next((t for t in LW._pestanas_web(brain, reg.socio(brain)) if t.get("slug") == slug), None)
    except Exception:
        return None
    if not bt or bt.get("canal") in (agent_brand.CANAL_NAVEGADOR, _PP().ESC):
        return None
    wid = LW._wid_de(bt)
    return (brain, bt, wid) if wid else None


def _olvidar_pestana(agente, slug):
    """Lo que se recuerda de sus pestañas (la lista de sus sesiones y la de `slug`) se vuelve a leer."""
    for k in (("pestana", agente, slug), ("tabs", agente), ("atados", agente)):
        _CACHE.pop(k, None)


def _prefs_ruta(agente):
    return os.path.join(_paths.state_dir(), "pagina", "%s.json" % agente)


def prefs(agente):
    try:
        with open(_prefs_ruta(agente), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_prefs(agente, d):
    r = _prefs_ruta(agente)
    os.makedirs(os.path.dirname(r), exist_ok=True)
    tmp = r + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    os.replace(tmp, r)


def motor_de(agente, brain=None):
    """El motor de la conversación: el que eligió el socio en la página; si no, el del
    último tramo de su historial; si no, el del agente."""
    m = prefs(agente).get("motor")
    if m:
        return m
    LW = _LW()
    brain = brain or cerebro(agente)
    try:
        tr = LW._tramos(_leer_historial(brain)) if brain else []
        if tr and tr[-1][0]:
            return tr[-1][0]
    except Exception:
        pass
    return LW._motores_de_agentes().get(agente) or ""


def via_de(motor):
    """{via, misma_conversacion, aviso?} de la capa de control (la vía que de verdad usa la página:
    motor_de_control), o None si no tiene. Si le escribe por OTRO conector suyo (F3e: Hermes por hermes-acp),
    también `escribe_por` y `aparte` (no es la conversación de su terminal): el chip dice «Hermes · chat aparte»."""
    try:
        C, mc = _control(), motor_de_control(motor)
        v = dict(C.VIAS[mc])
    except Exception:
        return None
    if mc != motor:
        v["escribe_por"], v["aparte"] = mc, not v.get("misma_conversacion")
    return v


# ── la terminal de la conversación: ¿abierta? (sin leer su pantalla) ───────
def _panel_vivo(reg):
    """¿Su panel de herdr existe y corre su motor? Por `pane get` y `process-info`, como
    aviso_panel.estado_panel pero sin su lectura de pantalla."""
    import aviso_panel as AP
    if not reg or not reg.get("panel") or not AP._exe():
        return False
    g = AP._herdr(["pane", "get", reg["panel"]], reg.get("socket", ""))
    pane = (g or {}).get("pane") or {}
    if pane.get("pane_id") != reg["panel"]:
        return False
    if reg.get("terminal") and pane.get("terminal_id") != reg["terminal"]:
        return False
    motor = reg.get("motor", "")
    if AP.AGENTE_HERDR.get(motor) and pane.get("agent") == AP.AGENTE_HERDR.get(motor):
        return True
    pi = AP._herdr(["pane", "process-info", "--pane", reg["panel"]], reg.get("socket", ""))
    return AP.motor_corre((pi or {}).get("process_info"), motor)


def _de_su_terminal(eventos):
    """B11: lo que anotaron su terminal y sus hooks, sin lo de las corridas de la página (via «pagina»: lo de una
    página que ya no vive, sin su turn_end, se leía «pensando» o «esperando_permiso» para siempre)."""
    return [e for e in eventos if (e.get("datos") or {}).get("via") != "pagina"]


def _inicio_de_su_terminal(eventos):
    """El session_start de su terminal si sus hooks la dan por abierta (lo de la página no cuenta), o None."""
    abierta = None
    for e in _de_su_terminal(eventos):
        if e["momento"] == "session_start":
            abierta = e
        elif e["momento"] == "session_end":
            abierta = None
    return abierta


def _terminal_en_registro(eventos):
    """¿Los hooks de su terminal dicen que está abierta? (lo de la página no cuenta)."""
    return _inicio_de_su_terminal(eventos) is not None


#: B11: las líneas de comando de los procesos de esta máquina, o None si no se puede saber. Las pruebas lo cambian.
PROCESOS = None


def _procesos():
    if PROCESOS is not None:
        return PROCESOS()
    if os.name == "nt":
        return None
    import subprocess
    try:
        r = subprocess.run(["ps", "-A", "-o", "command="], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=3)
    except Exception:
        return None
    return r.stdout.splitlines() if r.returncode == 0 else None


def _terminal_viva(motor, sesion):
    """B11: ¿corre en esta máquina la terminal de esa conversación? Claude Code lleva su número en la línea de comandos
    (`--resume`/`--session-id <número>`, también si la abriste a mano); las corridas de la página son `claude -p`.
    None si no se puede saber (otro motor, Windows, sin `ps`): entonces se cree a sus hooks, como antes."""
    if motor != "claude-code" or not sesion:
        return None
    lineas = _procesos()
    if lineas is None:
        return None
    return any(sesion in t and "-p" not in t and "--print" not in t for t in (ln.split() for ln in lineas))


def terminal_abierta(agente, brain, wid, canal=NAV):
    """¿La terminal de esta conversación está abierta? (la página no escribe encima). En la del monito (canal
    escritorio) solo cuenta una terminal de verdad en ESA conversación (su número, en los procesos o en sus avisos):
    nunca un registro de panel por agente y pestaña, que pudo heredar otra terminal."""
    try:
        from arquitectura import registro
        inicio = _inicio_de_su_terminal(registro.leer(brain, wid)[0])
        if inicio is not None:
            if _terminal_viva(inicio.get("motor"), inicio.get("session_id")) is not False:
                return True
            # B11: murió de golpe (un kill -9 no deja su session_end): se anota que ya no corre, para todos
            if not SOLO_LEER:
                registro.anotar(brain, wid, "session_end", inicio.get("motor") or "", inicio.get("session_id") or "",
                                {"reason": "sin_proceso", "origen": registro.ORIGEN_PAGINA})
    except Exception:
        pass
    if _canal(canal) == ESC:
        return _terminal_viva("claude-code", wid) is True
    try:
        import aviso_panel
        return _panel_vivo(aviso_panel.panel_de("%s--%s" % (agente, wid)))
    except Exception:
        return False


# ── la sesión de la página con su motor (capa de control) ──────────────────
def _tipo_error(msg):
    m = (msg or "").lower()
    for tipo, claves in _TIPOS_ERROR:
        if any(c in m for c in claves):
            return tipo
    return ""


def _fallo_del_bombeo(agente):
    """Un fallo en el hilo del bombeo, a stderr (el log del servidor) con su traza: el hilo sigue."""
    import traceback
    try:
        sys.stderr.write("pagina_v2: el bombeo de %s siguió tras un fallo:\n%s" % (agente, traceback.format_exc()))
        sys.stderr.flush()
    except Exception:
        pass


class _Sesion:
    """Una conversación de la página con un motor por su vía oficial. El bombeo lleva
    cada evento al registro de la pestaña y, al terminar el turno, al historial."""

    def __init__(self, agente, brain, wid, motor, canal=NAV, tab=NAV):
        self.agente, self.brain, self.wid, self.motor = agente, brain, wid, motor
        #: H4-a: su pestaña (la de siempre, «navegador», una de sus sesiones, o «escritorio»): su historial, su número
        #: de motor
        self.tab = _t(tab, canal)
        #: modo escritorio (D1-a): «navegador» (la página y el hub) o «escritorio» (el Compañero): su pestaña, su
        #: historial, su sesión del motor, su guía y, en el escritorio, sus manos
        self.canal = _canal(self.tab)
        self.con = None
        self.solo_mirar = ""
        #: cable-openclaw: no abrió por algo pasajero (su gateway aún encendiendo, sin respuesta a tiempo): la caja sigue
        #: libre y el próximo mensaje lo intenta otra vez (antes quedaba en «solo mirar» con el error crudo)
        self.pasajero = ""
        self.texto = ""
        self.herr = []
        self.cid = ""
        self.cola = []
        self.permiso = None
        self.en_espera = []             # B09: los que pidió mientras había otro (salen uno tras otro)
        self.pregunta_motor = None      # B14/B15: la pregunta propia de su motor, hasta tu siguiente mensaje
        self.resueltos = []             # los permisos que contestaste en este turno (van con su respuesta)
        self.corte, self.bloque = False, None   # el texto que siga es de otro mensaje suyo (párrafo nuevo)
        self.error = None
        self.vistos = set()
        self.saliendo = set()           # los ids que están saliendo ahora (mientras su motor los recibe)
        self.entrando = 0               # H4-a: mensajes dentro de `mandar` (de entrar a salir): no se suelta en medio
        self.hizo = []                  # skills v11: sus últimas herramientas con su hora (foto.hizo)
        self.termino = 0.0
        self.turno_pendiente = False     # el conector puede quedar listo antes de que la página guarde el fin
        self.desde = time.time()
        self.cambio = None
        self.vivo = False
        # F3d: abrir su motor y mandarle van SIN el candado global. `epoca` sube al soltar su conector (cambiar de
        # motor, cerrar): lo que se abría o se mandaba para el de antes ya no se instala. `ocupado` es el mensaje que
        # está abriendo su motor (otro, mientras tanto, no abre un segundo motor: se le dice). `turno` ordena tu
        # mensaje y lo que contesta: lo que llega se procesa después de anotar lo que mandaste.
        self.epoca = 0
        self.ocupado = None
        self.turno = threading.RLock()
        #: F4: la terminal abierta cuya conversación comparte el conector de ahora (control/compartido), o None.
        self.compartida = None
        self.siguiendo = None           # la terminal a la que se está uniendo en vivo (un hilo a la vez)
        self.fallo_seguir = None        # (terminal, hora) del último intento de unirse que no salió
        #: F4c: la terminal cuya conversación falta traer (lo que ya había antes de unirse), cuando el motor esté libre
        self.al_dia = None
        self.a_medias = False           # el turno de su terminal en curso empezó antes de unirse (sin su mensaje)
        #: Amigable: tu último mensaje ({texto, cid}) y el que sale solo cuando Workspace arregle su motor
        #: (entraste a tu cuenta, se actualizó, seguiste con otro). `aviso`: lo que Workspace hizo solo, con deshacer.
        self.ultimo = None
        self.por_arreglar = None
        self.aviso = None
        #: P-A: la última herramienta que empezó en este turno ({n, d}: su nombre y su entrada, como la manda su
        #: conector): la barra del proceso de una skill dice en simple «lo que está haciendo ahora».
        self.hace = None
        #: agente-interfaz: ¿su conector trae el núcleo (MCP workspace: preguntar, usar_skill, personalizar…)?
        #: modo chat: la guía de chat que va UNA vez por conector antes de tu primer mensaje (`guia`, por su ficha: la
        #: vía «mensaje»; con sus herramientas o, sin núcleo, con el comando de respaldo) y si ya salió (guia_dada).
        self.con_nucleo, self.guia, self.guia_dada = True, "", False
        #: B11: lo último de la respuesta a medias que quedó en disco (_guardar_parcial) y cuándo
        self.parcial_guardado, self.parcial_t = "", 0.0
        #: B12: cuándo llegó cada id por primera vez (_llegada): la cola va en ese orden, también tras un reintento
        self.llegadas = {}
        #: skills-cierre: el fin del turno de la página que falta llevar a sus skills ({motivo, error, texto}): lo hace
        #: el bombeo fuera del candado global (_skills_al_terminar)
        self.fin_turno = None
        #: Fix 3: la skill que su motor usó por su propia herramienta en este evento (skill_del_motor), por activar
        self.skill_motor = None

    def conciliar(self):
        """B11: lo que dejó una página que ya no vive (su servidor murió de golpe: un kill, un apagón). Al crear la
        sesión en un proceso no hay conector suyo: un turno de la página sin su turn_end se cierra «cortado», con lo
        que alcanzó a decir (lo que quedó en disco), y una terminal que sus hooks dan por abierta se mira si sigue
        viva (terminal_abierta). Quien llama tiene `self.turno`: nada tuyo sale mientras. → True si cerró un turno."""
        if SOLO_LEER:
            return False
        from arquitectura import registro
        try:
            evs = registro.leer(self.brain, self.wid)[0]
            pag = registro.estado([e for e in evs if (e.get("datos") or {}).get("via") == "pagina"])
            cerro = pag["estado"] in EN_CURSO
            if cerro:
                texto, motor = _parcial_de(self.brain, self.wid), pag.get("motor") or self.motor
                registro.anotar(self.brain, self.wid, "turn_end", motor, "",
                                {"last_assistant_message": texto, "motivo": "cortado", "via": "pagina",
                                 "origen": registro.ORIGEN_PAGINA})
                self._al_hist([_ev("agente", texto, motor, cortado=True)])
                # skills-cierre: la skill de ese turno cortado tampoco se queda corriendo
                self._skills_al_terminar({"motivo": "error", "error": True, "texto": texto})
            _sin_parcial(self.brain, self.wid)
            terminal_abierta(self.agente, self.brain, self.wid, canal=self.canal)
            return cerro
        except Exception:
            return False

    # ── H4-a: lo de su pestaña ──
    @property
    def _otra(self):
        """¿Es OTRA pestaña de la página (H4-a: una de sus sesiones, con su registro en pagina_pestanas)? Ni la de
        siempre ni la del Compañero de escritorio, que no son sesiones de su programa."""
        return self.tab not in (NAV, ESC)

    def _al_hist(self, evs, desde=None):
        """Al historial de ESTA pestaña (la de siempre, con las llamadas de siempre)."""
        if self.tab == NAV:
            return _al_historial(self.brain, evs) if desde is None else _al_historial(self.brain, evs, desde=desde)
        return _al_historial(self.brain, evs, desde=desde, tab=self.tab)

    def _programar_suelta(self):
        """H4-a: si sigue quieta SOLTAR_TAB_S, suelta su motor (su programa oficial ya la puede retomar)."""
        if self.motor == "claude-code" or SOLO_LEER:
            return
        epoca = self.epoca
        t = threading.Timer(SOLTAR_TAB_S, self._soltar_si_sigue_quieta, args=(epoca,))
        t.daemon = True
        t.start()

    def _soltar_si_sigue_quieta(self, epoca):
        with _LOCK:
            if self.epoca != epoca or self.con is None or _trabaja(self) or \
                    time.time() - (self.termino or 0) < SOLTAR_TAB_S - 0.5:
                return
            con = self.soltar()
        _cerrar_con(con)
        _avisar()

    def _rec(self):
        """Lo que se guarda de su pestaña (pagina_pestanas), o {}."""
        return (_PP().de(self.agente, self.tab) or {}) if self._otra else {}

    def _bt(self):
        p = pestana(self.agente, tab=self.tab) if self.tab != NAV else pestana(self.agente)
        return p[1] if p else None

    def _oficial(self):
        """¿Es una sesión que ya existía en su programa oficial? (la retoma por su número, sin crear otra)."""
        return self._otra and self._rec().get("tipo", "sesion") == "sesion"

    def _numero_oficial(self, motor):
        """El número de la conversación de `motor` en esta sesión, el que retomaría su programa
        (sessions_registry.resume_id: lo que dicen sus hooks, también tras un /clear), o ''."""
        bt = self._bt() or {}
        try:
            import sessions_registry as reg
            return reg.resume_id(self.brain, self.agente, bt.get("name") or self.tab, motor) or ""
        except Exception:
            return ""

    def _sesiones_tab(self, mc):
        """{conector: número}: la conversación de su motor que la página le abrió a esta pestaña o, en una sesión de su
        programa, la de su programa (Codex: su hilo)."""
        ses = dict(self._rec().get("sesiones") or {})
        if not ses.get(mc) and self._oficial() and self.motor in RETOMA and self.motor != "claude-code":
            n = self._numero_oficial(self.motor)
            if n:
                ses[mc] = n
        return ses

    def _guardar_sid(self, mc, nuevo):
        """El número de la conversación que abrió la página, en su pestaña y en su sesión: su programa oficial la
        retoma (sessions_registry.bind, lo mismo que hace su lanzador)."""
        try:
            _PP().poner(self.agente, self.tab, sesiones={mc: nuevo})
        except OSError:
            pass
        if mc != self.motor or not nuevo:
            return
        try:
            import sessions_registry as reg
            bt = self._bt() or {}
            reg.bind(self.brain, self.agente, bt.get("name") or self.tab, mc, nuevo)
            _CACHE.pop(("atados", self.agente), None)
        except Exception:
            pass

    def _no_retoma(self):
        """'' si la página le puede escribir a esta pestaña; si no, por qué (una sesión de un motor que la página
        todavía no retoma: se mira, con «Ir a la terminal»)."""
        if not self._oficial() or self.motor in RETOMA or self._rec().get("sesiones"):
            return ""
        return ("Esta sesión es de %s: aquí ves su historial. Para escribirle, «Ir a la terminal» (la página todavía no "
                "retoma sus sesiones)." % self._nombre())

    def _parcial_por_guardar(self, ev):
        """B11, con el candado global: lo que hay que dejar en disco de la respuesta a medias (cada PARCIAL_S como
        mucho, también tras el último trozo), "" para borrarlo al terminar el turno, o None."""
        if ev is not None and ev["tipo"] == "terminado":
            hubo, self.parcial_guardado, self.parcial_t = self.parcial_guardado, "", 0.0
            return "" if hubo else None
        if self.texto and self.texto != self.parcial_guardado and time.time() - self.parcial_t >= PARCIAL_S:
            self.parcial_guardado, self.parcial_t = self.texto, time.time()
            return self.texto
        return None

    def _al_disco(self, parcial):
        if parcial == "":
            _sin_parcial(self.brain, self.wid)
        elif parcial:
            _guardar_parcial(self.brain, self.wid, parcial)

    # abrir
    def abrir(self, terminal=None, silencioso=False):
        """Abre su motor por la capa de control. El candado global solo se toma para leer y para instalar el
        conector: mientras el motor abre (o no contesta), las demás rutas siguen. True si quedó abierto.
        F4: con la terminal de su pestaña abierta (`terminal`, de terminal_compartida), en SU conversación.
        `silencioso`: si no abre, no queda en «solo mirar» (unirse en vivo a su terminal, sin que escribieras)."""
        LW = _LW()
        with _LOCK:
            if self.con is not None and self.con.estado() != "cerrado":
                return True
            epoca, motor, antes = self.epoca, self.motor, self.con
            aviso = solo_mirar_de(motor, self._nombre()) or (self._no_retoma() if self._otra else "")
            if aviso:
                self.solo_mirar = aviso
                return False
            p = prefs(self.agente)
        if terminal is None:
            terminal = terminal_compartida(motor, self.brain, self.wid)
        mc = motor_de_control(motor)            # el conector (Hermes y OpenClaw: su ACP, un chat aparte)
        opciones = {"cwd": self.brain}
        identidad_para(motor, self.brain)       # B19: su AGENTS.md puntero, como al abrir su terminal
        if mc == "codex":
            # B05 (el sandbox del nivel del agente), cable-codex (la carpeta «untrusted» solo en el hilo) y lo prohibido
            # de leer (el perfil de permisos del hilo): hilo_codex. En el monito, su regla: hilo_codex_escritorio
            opciones.update(hilo_codex_escritorio(self.brain) if self.canal == ESC else hilo_codex(self.brain))
        elif mc == "kiro":
            # lo prohibido de leer: su agente de la página (cierre auditoría); en el monito, el que pregunta
            opciones.update(opciones_kiro(self.brain, canal=self.canal))
        sid = None
        if motor == "claude-code":
            opciones["terminal_abierta"] = lambda s: terminal_abierta(self.agente, self.brain, self.wid, canal=self.canal)
            # el mismo --permission-mode que su terminal (Configuración → Permisos): «Automático» de fábrica. Modo
            # escritorio (decisión del dueño, 21-nov): el monito pregunta todo lo que no es libre, con cualquier nivel
            opciones["modo_permisos"] = "manual" if self.canal == ESC else modo_claude(self.brain)
            # y los mismos permisos de sesión que su lanzador (B04): el avance de una skill sin una tarjeta por paso
            # y lo protegido negado, con cualquier nivel (en el monito, solo lo negado: nada pasa sin preguntar)
            ajustes = ajustes_claude_escritorio(self.brain) if self.canal == ESC else ajustes_claude(self.brain)
            if ajustes:
                opciones["settings"] = ajustes
            modelo = (p.get("modelo") or {}).get(motor)
            if modelo:
                opciones["modelo"] = modelo
            sid = self.wid                      # la misma conversación que su terminal
            if self._otra:                      # H4-a: la de su programa (también tras un /clear)
                sid = self._numero_oficial(motor) or self.wid
        elif terminal and mc == "opencode":
            # F4: el servidor de su terminal y SU sesión (la página no enciende el suyo)
            opciones.update(url=terminal["url"], clave=terminal["clave"], compartida=True)
            sid = terminal["sesion"]
        elif terminal and mc == "openclaw-acp":
            # F4: su puente ACP con la clave de sesión de su TUI (`openclaw acp --session`, de su --help):
            # cada session/new del puente va a esa sesión del gateway, la que ve su terminal
            from control.openclaw import comando_acp
            opciones["cmd"] = comando_acp(terminal["sesion"])
        elif mc == "openclaw-acp":
            # B18 (cacería 19-nov): sin su terminal, la página caía en el agente «main» del perfil (sin identidad, en
            # una carpeta compartida). Ahora entra como el agente de ESTE cerebro (asegurado como al abrir su
            # terminal) con una clave de sesión propia de la pestaña
            clave = clave_openclaw(self.agente, self.brain, self.wid, canal=self.canal)
            if clave:
                from control.openclaw import comando_acp
                opciones["cmd"] = comando_acp(clave)
            else:                                # sin su agente: lo de antes (la sesión guardada del conector)
                ses = (p.get(_SESIONES[self.canal]) or {}) if self.tab in (NAV, ESC) else self._sesiones_tab(mc)
                sid = ses.get(mc) or ses.get(motor)
            # con la clave, cada session/new del puente va a ESA sesión del gateway (como con su terminal): sin sid
        else:
            # la sesión es del conector (la de su ACP no sirve para su gateway); antes se guardaba por motor. H4-a: la
            # de otra pestaña, la suya (la que le abrió la página o la de su programa)
            ses = (p.get(_SESIONES[self.canal]) or {}) if self.tab in (NAV, ESC) else self._sesiones_tab(mc)
            sid = ses.get(mc) or (ses.get(motor) if mc != motor else None)
        # la pestaña de la página: su identidad llega al motor (y a su servidor) en lugar de la que herede este
        # proceso; sin ella la capa de control quitaba también WORKSPACE_BRAIN/WID/WS y el MCP núcleo no sabía dónde
        # anotar (control/entorno, punto F)
        pestana = {"ws": self.tab, "wid": self.wid, "agente": self.agente, "cerebro": str(self.brain)}
        try:
            # F6: el núcleo, como en su terminal (antes que su servidor: así el servidor ya encuentra el proyecto listo)
            nucleo = nucleo_para(motor, self.brain, self.wid, agente=self.agente) if self.tab == NAV else \
                nucleo_para(motor, self.brain, self.wid, agente=self.agente, canal=ESC) if self.tab == ESC else \
                nucleo_para(motor, self.brain, self.wid, agente=self.agente, ws=self.tab)
            if not terminal:                    # F4: con su terminal abierta, el servidor es el de ella
                opciones.update(servidor_de(mc, self.brain, pestana))   # el servidor local de su conector (OpenCode)
            opciones.update(nucleo)                                     # F6: el núcleo, como en su terminal
            if not terminal and mc != "opencode":
                opciones["env"] = dict(opciones.get("env") or os.environ, WORKSPACE_VIA=VIA_DE[self.canal])
            opciones["pestana"] = pestana
            fab = FABRICA or _control().conector
            con = fab(mc, **opciones)
            try:
                nuevo = con.abrir(sid)
            except Exception:
                # la de su terminal no se cambia por otra; H4-a: la de su programa oficial tampoco (nunca otra en
                # su lugar: si no se retoma, se dice)
                if not sid or terminal or self._oficial():
                    raise
                con = fab(mc, **opciones)       # no se pudo retomar: una nueva
                nuevo = con.abrir(None)
            if motor == "claude-code" and not (_existe_en_claude(LW, self.brain, self.wid) if self.tab == NAV else
                                               _existe_en_claude(LW, self.brain, self.wid, canal=ESC) if self.tab == ESC else
                                               _existe_en_claude(LW, self.brain, self.wid, tab=self.tab, sid=sid)):
                con._existe = False             # la primera corrida la crea con --session-id <wid>
        except Exception as e:
            # Amigable: si se sabe qué le pasa (sin sesión, sin instalar, sin créditos…), su tarjeta en simple en
            # lugar de «solo mirar» con el error crudo; lo que no se reconoce queda como antes
            limpio = _sin_ansi(e)
            est = None if silencioso else _estado_amigable(motor, limpio, sondear=True)
            pasa = not est and _al_abrir_pasajero(motor, limpio)
            with _LOCK:
                if self.epoca == epoca and not silencioso:
                    self.pasajero = ""
                    if est:
                        self.solo_mirar = ""
                        self.error = {"tipo": "", "estado": est, "motor": motor, "fatal": True,
                                      "texto": "No pude abrir %s: %s" % (self._nombre(), limpio)}
                    elif pasa:
                        self.solo_mirar = ""
                        self.pasajero = "%s todavía no contesta (%s). Vuelve a mandarlo en un momento." % (
                            self._nombre(), limpio[:300])
                    else:
                        self.solo_mirar = "No pude abrir %s por su vía oficial: %s" % (self._nombre(), limpio)
                    self.con = None
            return False
        with _LOCK:
            sobra = self.epoca != epoca or self.con is not antes
            if not sobra:
                self.con, self.solo_mirar, self.vivo, self.pasajero = con, "", True, ""
                # modo chat: con el paquete encendido, la guía de chat de su ficha (la de «argv» ya va en su sesión),
                # con sus herramientas si trae el núcleo (trae_nucleo) o con el comando de respaldo si no...
                self.con_nucleo, self.guia_dada = trae_nucleo(motor, nucleo), False
                # ...salvo en la conversación de su terminal abierta (F4): es la de su terminal, y ahí no es un chat
                self.guia = "" if terminal else guia_para(motor, self.con_nucleo, canal=self.canal,
                                                          manos=self.canal == ESC and self.con_nucleo
                                                          and _paquete_activo() and manos_para(motor))
                self.compartida = terminal or None
                # F4c: lo que ya había en su conversación (lo de antes de unirse) se trae con el motor libre
                self.al_dia = terminal if (terminal and mc == "opencode") else None
                self.a_medias = False
                # En OpenCode privado el servidor puede emitir avisos sin el entorno del conector.
                # Una sesión retomada de la terminal conserva sus avisos. OpenClaw marca su clave al crearla.
                if not SOLO_LEER and not terminal and nuevo and nuevo != sid and motor == "opencode":
                    from arquitectura import registro
                    registro.anotar(self.brain, self.wid, registro.CONVERSACION, motor, nuevo, {"via": "pagina"})
                # el bombeo primero: si guardar las prefs falla, el conector no queda sin quien lea sus eventos
                threading.Thread(target=self._bombear, args=(con,), name="pagina-v2-%s" % self.agente,
                                 daemon=True).start()
                # F4: la de OpenCode se guarda también compartida: cerrada su terminal, la página sigue ESA en su
                # servidor. La del puente de OpenClaw con la clave de su TUI, no (es un id del puente, no de la
                # conversación).
                if motor != "claude-code" and not (terminal and mc != "opencode") and self._otra:
                    self._guardar_sid(mc, nuevo)    # H4-a: en su pestaña y en su sesión (su programa la retoma)
                elif motor != "claude-code" and not (terminal and mc != "opencode"):
                    try:
                        p = prefs(self.agente)
                        p.setdefault(_SESIONES[self.canal], {})[mc] = nuevo
                        _guardar_prefs(self.agente, p)
                    except OSError:
                        pass
        if sobra:                               # cambiaste de motor (o se cerró) mientras abría: no se instala
            _cerrar_con(con)
            return self.epoca == epoca and self.con is not None
        if terminal and mc == "opencode":
            self._al_dia_con_calma(con)
        return True

    def _al_dia_con_calma(self, con):
        """F4c: recién unida, la página no sabe si su terminal está a media respuesta (hasta que llega algo, el conector
        dice «listo»). Espera AL_DIA_CALMA_S: si sigue libre, trae lo de antes; si en ese rato empezó (o terminó) un
        turno, lo trae el fin de ese turno (_evento, «terminado»), ya con la respuesta entera."""
        def esperar():
            time.sleep(AL_DIA_CALMA_S)
            self._ponerse_al_dia(con)           # solo si sigue pendiente y el motor libre
        threading.Thread(target=esperar, name="pagina-v2-calma-%s" % self.agente, daemon=True).start()

    def _ponerse_al_dia(self, con, respaldo=None):
        """F4c: al unirse a la conversación de su terminal, lo que ya había en ella (lo que escribiste en la terminal
        ANTES de que la página se conectara) entra al historial: por el export oficial de ESE servidor, en un hilo, y
        solo lo que la página no tenga. Con el motor a media vuelta, espera a que termine. `respaldo`: la respuesta
        parcial de un turno al que se unió a medias, si el export no sale. True si salió a traerlo."""
        with _LOCK:
            t = self.al_dia
            if t is None or self.con is not con or con.estado() != "listo":
                return False
            self.al_dia = None
        brain = self.brain

        def traer():
            pedido = time.time()
            try:
                from control import opencode as _oc
                turnos = (HISTORIAL or _oc.historial)(t["url"], t["clave"], t["sesion"], cwd=brain)
            except Exception:
                turnos = None
            if turnos is None:
                if respaldo:
                    self._al_hist([respaldo])
            elif self.tab == NAV:
                _sumar_lo_de_antes(brain, t["sesion"], turnos, pedido=pedido,
                                   ocupado=lambda: con.estado() in ("trabajando", "esperando_permiso"))
            else:
                _sumar_lo_de_antes(brain, t["sesion"], turnos, pedido=pedido,
                                   ocupado=lambda: con.estado() in ("trabajando", "esperando_permiso"), tab=self.tab)
            _avisar()
        threading.Thread(target=traer, name="pagina-v2-al-dia-%s" % self.agente, daemon=True).start()
        return True

    def _nombre(self):
        try:
            import motores_logica
            return motores_logica.engine_name(self.motor)
        except Exception:
            return self.motor

    def soltar(self):
        """Suelta su conector (con el candado global tomado): lo que se estaba abriendo o mandando para él ya no se
        instala. → el conector, para cerrarlo FUERA del candado (_cerrar_con)."""
        con, self.con = self.con, None
        self.vivo = False
        self.epoca += 1
        self.ocupado = None
        self.compartida = None
        self.turno_pendiente = False
        return con

    def _otra_terminal(self, terminal):
        """F4: ¿el conector de ahora NO es el de la terminal abierta de ahora? (la abriste o la cerraste desde que
        se abrió). Con el candado global tomado."""
        if self.motor not in COMPARTIBLES or self.con is None or self.con.estado() == "cerrado":
            return False
        from control import compartido
        return compartido.identidad(terminal) != compartido.identidad(self.compartida)

    def seguir_terminal(self):
        """F4: con la terminal de su pestaña abierta, la página se une a su conversación EN VIVO aunque no le hayas
        escrito (OpenCode: lo que escribes en la terminal aparece aquí mientras pasa). Sin bloquear: un hilo."""
        if self.motor not in SIGUE_EN_VIVO:
            return
        t = terminal_compartida(self.motor, self.brain, self.wid)
        from control import compartido
        with _LOCK:
            if not t or self.ocupado or self.turno_pendiente or self.siguiendo == compartido.identidad(t):
                return
            fallo = self.fallo_seguir
            if fallo and fallo[0] == compartido.identidad(t) and time.time() - fallo[1] < SEGUIR_REINTENTO_S:
                return                          # no se pudo hace poco: no se reintenta en cada vuelta
            if self.con is not None and self.con.estado() != "cerrado" and not self._otra_terminal(t):
                return                          # ya la sigue
            if self.con is not None and self.con.estado() not in ("listo", "cerrado"):
                return                          # a media respuesta de la página: al terminar
            self.siguiendo = compartido.identidad(t)
            viejo = self.soltar() if (self.con is not None and self.con.estado() != "cerrado") else None

        def unirse():
            ok = False
            try:
                _cerrar_con(viejo)
                ok = self.abrir(t, silencioso=True)
            finally:
                with _LOCK:
                    self.siguiendo = None
                    self.fallo_seguir = None if ok else (compartido.identidad(t), time.time())
                _avisar()
        threading.Thread(target=unirse, name="pagina-v2-sigue-%s" % self.agente, daemon=True).start()

    def cerrar(self):
        with _LOCK:
            con = self.soltar()
        _cerrar_con(con)

    # el turno
    def _en_cola(self, texto, cid, motivo="trabajando", desde=None, reintento="", frente=None):
        """En la cola, en el orden en que llegaron (B12: el que abría su motor va antes de lo que llegó mientras).
        `frente` (modo escritorio): lo que tenía enfrente al escribirlo; sale con él."""
        if len(self.cola) >= COLA_MAX:
            return {"ok": False, "status": 429, "error": "localhost.err.v2_cola_llena"}
        self.vistos.add(cid)
        e = {"id": cid, "texto": texto, "desde": desde or time.time(), "motivo": motivo}
        if reintento:
            e["reintento"] = reintento
        if frente:
            e["frente"] = frente
        i = len(self.cola)
        while i and self.cola[i - 1]["desde"] > e["desde"]:
            i -= 1
        self.cola.insert(i, e)
        _avisar()
        return {"ok": True, "en_cola": True}

    def _llegada(self, cid):
        """B12 (con el candado global): cuándo llegó este id por primera vez. Un reintento (el mismo id, tras «no
        salió») conserva su lugar: sale antes de lo que llegó después."""
        t = self.llegadas.get(cid)
        if t is None:
            t = self.llegadas[cid] = time.time()
            if len(self.llegadas) > LLEGADAS_MAX:
                for viejo in list(self.llegadas)[:LLEGADAS_MAX // 2]:
                    del self.llegadas[viejo]
        return t

    def mandar(self, texto, cid, reintento="", frente=None):
        """→ dict de la respuesta (ok, en_cola) o {"ok": False, …} con el motivo. Sin el candado global mientras
        abre su motor o le manda: si no contesta, las demás rutas siguen (el tope lo pone la capa de control y, en la
        página, a los 60 s queda la tarjeta con «Reintentar»). `frente` (modo escritorio, D3-a): {linea, resumen} de lo
        que tenía enfrente; le llega al motor como contexto, no como lo que escribiste."""
        terminal = terminal_compartida(self.motor, self.brain, self.wid)   # F4 (lee un archivo: fuera del candado)
        viejo, libre = None, None
        with _LOCK:
            if cid in self.vistos or cid in self.saliendo:     # ya salió, o está saliendo ahora: no sale dos veces
                return {"ok": True, "repetido": True}
            t0 = self._llegada(cid)
            if self.ocupado:
                if self.ocupado["cid"] == cid:  # este mismo, reintentado mientras abre su motor: ya va a salir
                    return {"ok": True, "repetido": True}
                # B12 (cacería 19-nov): otro mensaje está abriendo su motor: este espera su turno en la cola y sale
                # después (antes: 409 «todavía estoy abriendo» y se podía perder)
                return self._en_cola(texto, cid, motivo="abriendo", desde=t0, reintento=reintento, frente=frente)
            abierto = self.con is not None and self.con.estado() != "cerrado"
            if abierto and (self.turno_pendiente or self.con.estado() != "listo" or self.cola):
                en_cola = self._en_cola(texto, cid, desde=t0, reintento=reintento, frente=frente)
                if not (en_cola.get("ok") and not self.turno_pendiente and self.con.estado() == "listo"):
                    return en_cola
                libre = self.con                # nada corre y había cola (quedó de antes): que salga ahora
            if libre is None and abierto and self._otra_terminal(terminal):
                # F4: abriste (o cerraste) su terminal: a SU conversación (la cola, si queda, sale al instalarse)
                viejo, abierto = self.soltar(), False
            epoca, yo = self.epoca, None
            if not abierto:
                yo = self.ocupado = {"cid": cid, "t": t0, "texto": texto}     # la foto lo enseña (B12)
            # H4-a: desde aquí hasta que salga (o no), la pestaña no se suelta por quieta (_trabaja): el temporizador
            # de SOLTAR_TAB_S que vence justo ahora ya no tira tu mensaje con «cambiaste de motor (o se cerró)»
            self.entrando += 1
        try:
            _cerrar_con(viejo)
            if libre is not None:
                self._drenar(libre)
                return en_cola
            if yo is not None:
                abrio = self.abrir(terminal)
                with _LOCK:
                    # no abrió: lo que llegue ahora lo intenta otra vez. Si abrió, sigue «ocupado» hasta tener su turno
                    # (B12): el bombeo recién empezado no manda antes lo que entró a la cola mientras abría
                    if self.ocupado is yo and not abrio:
                        self.ocupado = None
                    if self.epoca != epoca:
                        return self._cambio_mientras()
                    est = (self.error or {}).get("estado") if not abrio else None
                    if est:
                        # Amigable: su tarjeta lo explica y Workspace lo arregla solo si puede; tu mensaje sale
                        # solo al terminar (o al seguir con otro motor)
                        self.por_arreglar = {"texto": texto, "cid": reintento or cid}
                        if reintento:
                            self.por_arreglar["ya"] = True
                        _avisar()
                    if not abrio and not est and self.pasajero and not self.solo_mirar:
                        # algo pasajero: tu mensaje no salió, la caja sigue libre y «Reintentar» lo manda
                        return {"ok": False, "status": 409, "error": "localhost.err.v2_no_salio",
                                "datos": {"motivo": self.pasajero}, "abriendo": True}
                    if not abrio and not est:
                        return {"ok": False, "status": 409, "error": "localhost.err.v2_solo_mirar",
                                "datos": {"motivo": self.solo_mirar}, "solo_mirar": True}
                if est:
                    self._arreglar_solo(est)
                    return {"ok": False, "status": 409, "error": "localhost.err.v2_no_salio",
                            "datos": {"motivo": self.error.get("texto") or ""}, "amigable": est}
            with self.turno:                    # otro que sale a la vez: espera aquí y luego va en cola
                with _LOCK:
                    if yo is not None and self.ocupado is yo:
                        self.ocupado = None     # B12: ya tiene su turno: lo que llegue ahora va en cola detrás
                    if self.epoca != epoca or self.con is None:
                        return self._cambio_mientras()
                    if cid in self.vistos:      # el mismo id, reintentado mientras el primero salía: ya salió
                        return {"ok": True, "repetido": True}
                    en_cola = None
                    # B12: lo que entró a la cola mientras su motor abría llegó DESPUÉS de este: este sale primero
                    if self.turno_pendiente or self.con.estado() != "listo" or any(
                            x["desde"] < t0 for x in self.cola):
                        en_cola = self._en_cola(texto, cid, desde=t0, reintento=reintento, frente=frente)
                        libre = self.con if (en_cola.get("ok") and not self.turno_pendiente
                                             and self.con.estado() == "listo") else None
                if en_cola is not None:
                    if libre is not None:
                        self._drenar(libre)     # reabrió con cola de antes: sale la primera
                    return en_cola
                return self._salir(texto, cid, reintento=reintento, frente=frente)
        finally:
            with _LOCK:
                self.entrando -= 1
                if yo is not None and self.ocupado is yo:
                    self.ocupado = None
            _avisar()

    def _cambio_mientras(self):
        return {"ok": False, "status": 409, "error": "localhost.err.v2_no_salio",
                "datos": {"motivo": "cambiaste de motor (o se cerró) mientras abría"}}

    def _salir(self, texto, cid, sig=None, reintento="", frente=None):
        """Le manda tu mensaje por la capa de control, SIN el candado global. Quien llama tiene `self.turno`: lo que
        conteste se procesa después de anotar tu mensaje. `sig`: el de la cola que sale ahora (_de_la_cola). Mientras
        sale, su id está en `saliendo`: un reintento con el mismo id no sale otra vez (si este falla, sí puede)."""
        with _LOCK:
            self.saliendo.add(cid)
        try:
            return self._salir_ya(texto, cid, sig, reintento or (sig or {}).get("reintento", ""),
                                  frente or (sig or {}).get("frente"))
        finally:
            with _LOCK:
                self.saliendo.discard(cid)

    def _salir_ya(self, texto, cid, sig, reintento, frente=None):
        with _LOCK:
            con, motor, epoca = self.con, self.motor, self.epoca
        if con is None:
            return self._cambio_mientras()
        # F3c, punto 1: si desde su última vez la conversación siguió con otros motores, esos turnos van UNA vez
        # antes de tu mensaje (la nota de contexto del sistema de antes, entera: por la capa de control no hay caja
        # que desbordar). Se cuenta solo si el mensaje salió. La conversación del escritorio no la lleva (es otra); la
        # de la página lleva, una vez, lo que le pasaste del escritorio («Seguir en la página»)
        if self.tab == NAV:
            nota, marcar = _nota_de_contexto(self.brain, motor)
            del_esc, marcar_esc = _nota_del_escritorio(self.agente)
        elif self.tab == ESC:
            nota, marcar, del_esc, marcar_esc = "", None, "", None
        else:                                   # H4-a: otra pestaña de la página
            nota, marcar = _nota_de_contexto(self.brain, motor, tab=self.tab)
            del_esc, marcar_esc = "", None
        # modo escritorio (D3-a): lo que tenía enfrente, como contexto (una línea), no como lo que escribió
        linea = (frente or {}).get("linea") or ""
        # E9: lo que quedó sin contestar por un reinicio de la página (una vez; se quita solo si el mensaje salió)
        reinicio = nota_de_interrumpidos(self.brain, self.wid, quitar=False)
        # modo chat: la guía de chat (la vía «mensaje» de su ficha), UNA vez por conector
        with _LOCK:
            guia = "" if self.guia_dada else self.guia
        # Fable v2 ⛔: el turno de un encargo va acotado a SU nivel (nunca con el de la página sin que el socio lo elija)
        acotar = self._acotar_encargo(con, cid)
        if acotar is not None:
            return acotar
        falla = None
        for intento in (0, 1):
            # skills-cierre: el turno empieza ANTES de que su motor lo acepte: lo que enseña (mostrar_archivo) mientras
            # lo recibe es de este turno. Antes `desde` se fijaba al volver de mandar y la tarjeta se perdía si su
            # motor tardaba más de 2 ms (una máquina cargada)
            inicio = time.time()
            try:
                con.mandar("\n\n".join(x for x in (guia, del_esc, nota, reinicio, linea, texto) if x))
                falla = None
                break
            except Exception as e:
                falla = e
            # Amigable: si lo frena una terminal vieja de esta conversación (quieta y sin uso), se cierra sola y
            # tu mensaje sale; una que usaste hace poco, no (queda su tarjeta)
            if intento or sig is not None or "terminal" not in str(falla).lower() \
                    or con.estado() in ("trabajando", "esperando_permiso") or not self._quitar_terminal_vieja():
                break
        if falla is not None:
            e = falla
            if con.estado() in ("trabajando", "esperando_permiso"):
                with _LOCK:                     # F4: su terminal empezó un turno justo ahora: el tuyo espera
                    if self.epoca == epoca:
                        if sig is None:
                            return self._en_cola(texto, cid, reintento=reintento, frente=frente)
                        if not any(x["id"] == cid for x in self.cola):
                            self.cola.insert(0, sig)    # el de la cola vuelve al frente: no pierde su lugar
                        self.vistos.add(cid)
                        _avisar()
                        return {"ok": True, "en_cola": True}
            terminal = "terminal" in str(e).lower()
            return {"ok": False, "status": 409, "error": "localhost.err.v2_no_salio",
                    "datos": {"motivo": str(e)}, "terminal": terminal,
                    "cerrable": terminal and terminal_cerrable(self.agente, self.brain, self.wid)}
        with _LOCK:
            if self.epoca != epoca:
                return self._cambio_mientras()
            if guia and self.con is con:
                self.guia_dada = True
            if reinicio:
                nota_de_interrumpidos(self.brain, self.wid)       # contada: no se repite
            for m in (marcar, marcar_esc):
                if m:
                    try:
                        m()
                    except Exception:
                        pass
            self.vistos.add(cid)
            self.turno_pendiente = True
            self.cid, self.texto, self.herr, self.error, self.termino = cid, "", [], None, 0.0
            self.pregunta_motor = None          # B14/B15: tu mensaje la contesta (o la deja atrás)
            self.ultimo = {"texto": texto, "cid": reintento or cid}
            self.hace = None
            self.corte, self.bloque = False, None
            self.desde = inicio
            if not reintento:
                self._al_hist([_ev("yo", texto, motor, envio_id=cid, contexto=bool(nota), sesion_motor=con.sesion,
                                   frente=(frente or {}).get("resumen"), del_escritorio=bool(del_esc))])
            _al_registro(self, "user_prompt", {"prompt": texto, "reintento": bool(reintento)})
            _avisar()
        self._skills_al_mandar(cid)
        return {"ok": True}

    def _acotar_encargo(self, con, cid):
        """Si `cid` es un encargo: su turno va con SU nivel (el conector lo pone solo para esa corrida). None si sale;
        si no se puede acotar como dice su nivel, la respuesta de error (y el encargo queda en error): no sale."""
        try:
            reg = _E().regimen_turno(self.brain, cid)
        except Exception:
            reg = None if not str(cid).startswith("en-") else {"nivel": {"acotado": True}}
        if reg is None:
            return None
        n = reg.get("nivel") or {}
        if not n.get("acotado"):
            return None if n.get("como_pagina") else self._encargo_no_sale(cid, "su motor no se puede acotar")
        try:
            cfg = regimen_claude(self.brain, reg) if self.motor == "claude-code" else None
            ok = bool(cfg) and bool(getattr(con, "acota_turnos", False)) and con.para_el_turno(**cfg)
        except Exception:
            ok = False
        return None if ok else self._encargo_no_sale(cid, "su conector no pudo acotar este turno")

    def _encargo_no_sale(self, cid, por):
        try:
            pasos = _E()._pasos()
            eid = "s-" + str(cid)[3:]
            d = pasos.leer(eid, self.brain)
            if d.get("encargo"):
                d["estado"] = "error"
                d["encargo"]["fin"] = {"estado": "error", "t": round(time.time(), 3), "archivos": [], "resumen": "",
                                       "error": "No lo mandé con más permisos de los que elegiste (%s)." % por}
                pasos.guardar(eid, d, self.brain)
        except Exception:
            pass
        return {"ok": False, "status": 409, "error": "localhost.err.encargo_sin_acotar", "datos": {"motivo": por}}

    # ── skills-cierre (22-nov): nadie deja una skill «corriendo» para siempre ─────
    def _skills_al_mandar(self, cid):
        """Tu mensaje salió: lo que una skill te pedía ya no te espera. Con su botón, en la caja o el archivo que pidió
        (rq-/ar-), contestado: sigue corriendo. Otra cosa (cambiaste de tema, «Saltar este paso»): corre con lo que pedía
        pendiente; si el turno acaba sin que siga, se pausa «quedó pendiente: ¿…?». Su instrucción (skill-) y «Hacer
        ahora» (ha-) no la tocan. Sin el candado global (lee y escribe sus archivos)."""
        if SOLO_LEER or not cid or cid.startswith(("skill-", "ha-")) or self.tab != NAV:
            return                              # H4-a: las skills son de la conversación de siempre
        P = _pasos()
        responde = cid.startswith(("rq-", "ar-"))
        for e in _abiertas(self.brain):
            if e.get("estado") == "pide":
                try:
                    P.actualizar(e["id"], P.contestada if responde else P.soltar_pide, self.brain)
                except Exception:
                    pass

    def _skill_del_motor(self, pedida):
        """Fix 3 · su motor usó su propia herramienta de skills: si no corre ya una (la de «Usar», o la que activó con
        usar_skill), su ejecución `por: motor` para que la página y el hub la enseñen. Sin el candado global."""
        if SOLO_LEER or self.tab != NAV or any(not e.get("pendiente") for e in _abiertas(self.brain)):
            return
        try:
            if _IA().activar_por_motor(self.brain, self.agente, NAV, self.motor, pedida):
                _avisar()
        except Exception:
            pass

    def _pregunta_abierta(self):
        """¿Quedó esperando tu respuesta a algo que no es de pasos (preguntar del núcleo, el buzón, la pregunta propia
        de su motor)? Entonces su skill no se pausa: te espera."""
        if self.pregunta_motor:
            return True
        try:
            from arquitectura import registro
            eventos = registro.leer(self.brain, self.wid)[0]
            return bool(_pregunta_de(registro.estado(eventos)) or _del_buzon(self.brain, self.wid, eventos))
        except Exception:
            return False

    def _skills_al_terminar(self, fin, sig=None):
        """C1 · el turno de la página terminó: ninguna skill suya se queda abierta sin nadie que la cierre. La que
        sigue en `arrancando` o `corriendo` (sin `pide`) pasa a `pausada` (pasos.pausar) con su motivo: Parar → parado,
        un error de su motor → error, lo que pedía quedó sin contestar → otro_mensaje, si no → sin_fin. No se toca la
        que te pide algo, la que espera tu respuesta a una pregunta, ni la que todavía no recibe su instrucción (en la
        cola). Fix 3: la que activó su motor con su propia herramienta (por: motor) termina con su turno. Sin el
        candado global; quien llama tiene `self.turno`."""
        if SOLO_LEER or self.tab != NAV:
            return                              # H4-a: las skills son de la conversación de siempre
        P = _pasos()
        with _LOCK:
            esperan = [x["id"] for x in self.cola] + [x["cid"] for x in (self.ocupado,) if x] + \
                ([sig["id"]] if sig else [])
        abiertas = [e for e in _abiertas(self.brain) if e.get("estado") != "pide"
                    and not any(c.startswith("skill-" + e["id"]) for c in esperan)]
        if not abiertas or self._pregunta_abierta():
            return
        motivo_turno = fin.get("motivo") or "fin"
        cambio = False

        def motivo_de(d):
            return ("parado" if motivo_turno == "parado" else
                    "error" if motivo_turno == "error" or fin.get("error") else
                    "otro_mensaje" if d.get("pendiente") else "sin_fin")
        for e in abiertas:
            # la foto puede ser vieja: su `pide` pudo llegar entre la foto y el candado (Copilot y OpenCode mandan en
            # paralelo). Se decide otra vez dentro del candado: la que ya te pregunta no se pausa ni se cierra.
            try:
                if e.get("por") == "motor" and not e.get("tomada"):
                    r = P.actualizar(e["id"], lambda d: _sin_pide(d) and _cerrar_del_motor(d, fin.get("texto") or ""),
                                     self.brain)[1]
                else:
                    r = P.actualizar(e["id"], lambda d: _sin_pide(d) and P.pausar(d, motivo_de(d)), self.brain)[1]
                cambio = cambio or bool(r)
            except Exception:
                continue
        if cambio:
            _avisar()

    # ── Amigable: lo que Workspace arregla solo ──────────────────────────────
    def _error_amigable(self, est):
        """Con el candado global tomado: el estado en simple del error de ahora (su tarjeta). Tu mensaje de este
        turno queda para salir solo cuando se arregle, y lo que se arregla solo empieza (en un hilo)."""
        if not est or not self.error:
            return
        self.error["estado"] = est
        if self.ultimo:
            self.por_arreglar = dict(self.ultimo, ya=True)      # ya está en la conversación (salió y falló)
        self._arreglar_solo(est)

    def _arreglar_solo(self, est):
        """Sin que muevas nada: sesión vencida → su login oficial en una ventana al frente, con la guía en la
        página; versión vieja → su instalador oficial en segundo plano. No se repite solo antes de
        ARREGLO_REPITE_S (si cerraste su ventana sin entrar, la tarjeta tiene su botón)."""
        if est not in ("sin_sesion", "actualizar"):
            return
        clave, ahora = (self.agente, self.motor, est), time.time()
        if ahora - _AUTO.get(clave, 0) < ARREGLO_REPITE_S:
            return
        _AUTO[clave] = ahora
        threading.Thread(target=_arreglar, args=(self.agente, self.motor, est), name="pagina-v2-arreglo",
                         daemon=True).start()

    def _quitar_terminal_vieja(self):
        """«Una terminal vieja que estorba»: su panel de herdr de esta conversación, quieto y sin nada de su
        terminal desde hace TERMINAL_VIEJA_S, se cierra solo (lo de «Cerrar esa terminal», sin pulsar). Queda un
        aviso con «Volver a abrirla». True si quedó libre."""
        if not terminal_vieja(self.agente, self.brain, self.wid):
            return False
        r = cerrar_terminal(self.agente)
        if not (r.get("ok") and r.get("libre")):
            return False
        with _LOCK:
            self.aviso = {"tipo": "terminal_vieja", "motor": self.motor, "t": time.time()}
            _avisar()
        return True

    def _de_la_cola(self, sig):
        """Manda el que esperaba en cola (quien llama tiene `self.turno`). Si no sale (su terminal abierta, el motor
        lo negó, cambió el motor), NO se pierde: vuelve al frente de la cola y la tarjeta de error dice por qué; sale
        con el próximo fin de turno, al reabrir o con «Quitar». True si salió."""
        r = self._salir(sig["texto"], sig["id"], sig)
        if r.get("ok"):
            return True
        with _LOCK:
            if not any(x["id"] == sig["id"] for x in self.cola):
                self.cola.insert(0, sig)
            self.vistos.add(sig["id"])
            motivo = (r.get("datos") or {}).get("motivo") or r.get("error") or ""
            self.error = {"tipo": "", "texto": "Un mensaje en cola no salió: %s" % motivo, "motor": self.motor,
                          "fatal": False}
            _avisar()
        return False

    def _drenar(self, con):
        """Si el motor está libre y hay cola, sale el primero. Al instalar un conector (la cola de antes de que el
        motor muriera no se queda atascada) y cuando llega un mensaje con el motor libre y cola."""
        with self.turno:
            with _LOCK:
                # B12: con alguien abriendo su motor, el suyo sale primero (lo de la cola llegó mientras abría)
                if (self.con is not con or not self.cola or con.estado() != "listo" or self.ocupado
                        or self.turno_pendiente):
                    return False
                sig = self.cola.pop(0)
                self.vistos.discard(sig["id"])
            return self._de_la_cola(sig)

    def _bombear(self, con):
        """El hilo que lleva lo que dice su motor a la página. Un fallo con un evento (el historial que no se deja
        tomar a tiempo, un dato raro) no lo mata: se cuenta en stderr y sigue con el próximo. Antes el hilo moría
        sin aviso y el turno quedaba «trabajando» para siempre."""
        try:
            self._drenar(con)                   # lo que quedó en cola cuando el motor de antes se cerró
        except Exception:
            _fallo_del_bombeo(self.agente)
        while self.con is con:
            try:
                ev = con.siguiente(0.5)
                if ev is None:
                    if con.estado() == "cerrado" and self.con is con:
                        self.vivo = False
                        _avisar()
                        return
                    with _LOCK:
                        parcial = self._parcial_por_guardar(None)
                    self._al_disco(parcial)     # B11: lo último que dijo, aunque ya no llegue nada más
                    continue
                with self.turno:
                    with _LOCK:
                        if self.con is not con:
                            return
                        sig = self._evento(ev)
                        parcial = self._parcial_por_guardar(ev)
                        fin, self.fin_turno = self.fin_turno, None
                        pedida, self.skill_motor = self.skill_motor, None
                        _avisar()
                    self._al_disco(parcial)     # B11: fuera del candado global
                    if pedida:
                        self._skill_del_motor(pedida)
                    if fin is not None:         # skills-cierre: ANTES de que salga el de la cola
                        self._skills_al_terminar(fin, sig)
                    if sig:                     # el que esperaba en cola sale ahora (sin el candado global)
                        self._de_la_cola(sig)
            except Exception:
                _fallo_del_bombeo(self.agente)
                time.sleep(0.2)                 # si el fallo se repite, no gira en vacío

    def _sumar_texto(self, ev):
        """F3c, punto 2: los trozos de un mismo mensaje se pegan tal cual; uno de OTRO mensaje (después de una
        herramienta o un permiso, o con otro `mensaje` si su conector lo dice) empieza un párrafo nuevo. Antes
        Cursor pegaba «…antes de responder.listo-cursor»."""
        trozo = ev.get("texto") or ""
        if not trozo:
            return
        bloque = ev.get("mensaje")
        otro = self.corte or (bloque is not None and self.bloque is not None and bloque != self.bloque)
        if otro and self.texto.strip():
            self.texto = self.texto.rstrip(" \t") + ("" if self.texto.endswith("\n\n") else
                                                     "\n" if self.texto.endswith("\n") else "\n\n")
            trozo = trozo.lstrip(" \t\n")
        self.texto += trozo
        self.corte = False
        if bloque is not None:
            self.bloque = bloque

    def _evento(self, ev):
        t = ev["tipo"]
        if t == "texto":
            self._sumar_texto(ev)
            return
        self.corte = True                       # entre dos mensajes suyos pasó algo: lo que siga es otro bloque
        # F4: lo de un turno de su terminal (ajeno) no se anota como de la página: lo anotan sus propios hooks
        anota = (lambda *a: None) if ev.get("ajeno") else (lambda m, d: _al_registro(self, m, d))
        if t == "pregunta":
            # B14/B15 (cacería 19-nov): la pregunta con opciones PROPIA de su motor (Codex, OpenCode): en la caja con
            # sus botones; la contestas como tu siguiente mensaje (responder). Antes se perdía
            texto = " ".join(str(ev.get("texto") or "").split())[:500]
            if texto:
                ops = [str(o)[:200] for o in (ev.get("opciones") or [])][:12]
                self.pregunta_motor = {"id": "nat-" + hashlib.sha256(("%s|%s" % (ev.get("id"), texto)).encode(
                                           "utf-8")).hexdigest()[:12],
                                       "pregunta": texto, "tipo": "opcion" if ops else "texto", "opciones": ops,
                                       "paso": "", "en_terminal": False}
            return None
        if t == "entrada":
            # F4: escribiste en su terminal (la misma conversación): tu mensaje y lo que conteste, aquí en vivo
            self.pregunta_motor = None
            self.texto, self.herr, self.error, self.termino, self.resueltos = "", [], None, 0.0, []
            self.hace = None
            self.corte, self.bloque = False, None
            self.cid, self.desde = "", time.time()
            self.turno_pendiente = True
            # F4c: sin su mensaje, la página se unió a medias (su respuesta llega cortada): la trae entera el export
            self.a_medias = not (ev.get("texto") or "").strip()
            if (ev.get("texto") or "").strip():
                self._al_hist([_ev("yo", ev["texto"], self.motor, terminal=True,
                                   sesion_motor=self.con.sesion if self.con else "")], desde=self.desde)
            return None
        if t == "herramienta":
            if ev.get("fase") == "empieza":
                self.herr.append({"n": ev.get("nombre") or "?", "d": str(ev.get("detalle") or "")[:120]})
                # skills v11: «Lo que va haciendo» (sus herramientas con su hora; las últimas HIZO_MAX)
                # B01: su clase, solo si su vía la dice (ACP); sin ella, como siempre
                c = {"c": str(ev["clase"])[:20]} if ev.get("clase") else {}
                self.hizo = (self.hizo + [dict({"n": ev.get("nombre") or "?", "d": str(ev.get("detalle") or "")[:400],
                                                "f": str(ev.get("archivo") or "")[:300],
                                                "t": round(time.time(), 3)}, **c)])[-HIZO_MAX:]
                self.hace = dict({"n": ev.get("nombre") or "?", "d": str(ev.get("detalle") or "")[:400],
                                  "f": str(ev.get("archivo") or "")[:300]}, **c)
                anota("pre_tool", {"tool_name": ev.get("nombre") or "?"})
                if not ev.get("ajeno"):
                    # skills-cierre (Fix 3): usó la herramienta de skills de SU motor (sin usar_skill): el bombeo crea
                    # su ejecución a la vista al salir del candado global
                    self.skill_motor = skill_del_motor(ev, getattr(self, "motor", "")) or getattr(
                        self, "skill_motor", None)
            else:
                anota("post_tool", {"tool_name": ev.get("nombre") or "", "ok": ev.get("fase") != "falla"})
        elif t == "permiso":
            pm = {"id": ev["id"], "herramienta": ev.get("herramienta") or "",
                  "detalle": ev.get("detalle") or "", "archivo": ev.get("archivo") or "",
                  "opciones": ev.get("opciones") or [], "que": que_en_su_carpeta(ev.get("que"), self.brain)}
            if isinstance(ev.get("grupo"), dict):
                pm["grupo"] = ev["grupo"]          # Monito UX: se puede agrupar («Sí, y lo demás en esta carpeta»)
            # B09 (cacería 19-nov): dos a la vez (Cursor, 1 ms entre los dos) pisaban al primero y el turno se colgaba
            # esperando uno que la página ya no tenía: el segundo espera su turno
            if self.permiso is None:
                self.permiso = pm
            else:
                self.en_espera.append(pm)
            anota("permission_request", {"tool_name": pm["herramienta"], "permiso_id": ev["id"],
                                         "detalle": pm["detalle"], "opciones": pm["opciones"]})
        elif t == "error":
            if ev.get("fatal") and self.compartida and \
                    not terminal_compartida(self.motor, self.brain, self.wid, limpiar=False):
                return None                     # F4: se cerró su terminal y con ella su servidor: no es un error tuyo
            self.error = {"tipo": _tipo_error(ev.get("mensaje")), "texto": ev.get("mensaje") or "",
                          "motor": self.motor, "fatal": bool(ev.get("fatal"))}
            if not ev.get("ajeno") and self.cid and self.ultimo:
                self.error["cid"] = self.ultimo["cid"]
            self._error_amigable(_estado_amigable(self.motor, self.error["texto"]))
            anota("error", {"mensaje": self.error["texto"]})
        elif t == "terminado":
            if not ev.get("ajeno"):
                # skills-cierre (C1): lo que el bombeo cierra o pausa de sus skills al salir del candado global
                self.fin_turno = {"motivo": ev.get("motivo") or "fin", "error": bool(self.error),
                                  "texto": self.texto}
            self.permiso, self.en_espera = None, []
            # Amigable: Copilot manda su error de cuota como TEXTO de la respuesta (probador real, 17-nov): no es
            # una respuesta suya sino su tarjeta, en simple y con su salida
            est = None if ev.get("ajeno") else _AM().respuesta_de_error(self.motor, self.texto)
            if est:
                self.error = {"tipo": "creditos" if est == "sin_creditos" else "", "texto": self.texto.strip(),
                              "motor": self.motor, "fatal": False}
                self._error_amigable(est)
                anota("error", {"mensaje": self.error["texto"]})
                self.texto = ""
            # un turno sin texto (Antigravity tras negar un permiso) no es una burbuja: queda la tarjeta
            # del permiso con lo que contestaste, y nada más
            # modo chat: los archivos que enseñó en este turno (mostrar_archivo) van con su respuesta, DESPUÉS de su texto
            archivos = [] if ev.get("ajeno") else _archivos_del_turno(self.brain, self.wid, self.desde)
            burbuja = None
            if self.texto.strip() or self.herr or self.resueltos or archivos:
                burbuja = _ev("agente", self.texto if self.texto.strip() else "", self.motor, envio_id=self.cid,
                              herr=self.herr, permisos=self.resueltos, terminal=bool(ev.get("ajeno")),
                              archivos=archivos, sesion_motor=self.con.sesion if self.con else "")
            a_medias, self.a_medias = bool(ev.get("ajeno") and self.a_medias and self.compartida), False
            if a_medias and self.motor == "opencode":
                # F4c: lo que se vio es parcial: la respuesta entera la trae el export (si no sale, esta)
                self.al_dia = self.al_dia or self.compartida
            elif burbuja:
                self._al_hist([burbuja], desde=self.desde if ev.get("ajeno") else None)
                burbuja = None
            fin = {"last_assistant_message": self.texto, "motivo": ev.get("motivo") or "fin"}
            u = self.con.uso() if self.con is not None else None     # F5: el uso oficial, si la capa de control lo da
            if u and isinstance(u.get("costo_usd"), (int, float)):
                fin["costo_usd"] = float(u["costo_usd"])
            anota("turn_end", fin)              # F4: el de un turno de su terminal lo anotan sus hooks
            self.texto, self.herr, self.termino, self.desde = "", [], time.time(), time.time()
            self.hace = None
            self.resueltos = []
            # F4c: lo de antes de unirse, ahora que el motor está libre (si no sale a traerlo, la parcial)
            sale = self.al_dia is not None and self.con is not None and self._ponerse_al_dia(self.con, burbuja)
            if burbuja and not sale:
                self._al_hist([burbuja])
            self.turno_pendiente = False
            if self._otra:
                self._programar_suelta()
            if self.cola and self.con is not None and self.con.estado() == "listo":
                sig = self.cola.pop(0)
                self.vistos.discard(sig["id"])
                return sig                      # lo manda _bombear, ya sin el candado global
        return None

    def _permiso_visible(self, con):
        """B09: el primero de los permisos de este turno que su motor SIGUE esperando (los contestados en su terminal
        o cancelados ya no están en su conector); sin conector que lo diga, el de siempre. Los demás salen después."""
        todos = ([self.permiso] if self.permiso else []) + list(self.en_espera)
        try:
            vivos = set(con.permisos_pendientes()) if con is not None else None
        except Exception:
            vivos = None
        return next((p for p in todos if vivos is None or p["id"] in vivos), None)

    # la foto, con la forma de la de antes
    def foto(self, eventos):
        from arquitectura import registro
        est = registro.estado(eventos)
        # B11: lo que trabaja o pide permiso EN SU TERMINAL lo dicen sus hooks; lo de la página lo sabe su conector
        su_terminal = registro.estado(_de_su_terminal(eventos))
        con = self.con                          # se lee sin el candado global: el de este momento
        propio = bool(con and (self.turno_pendiente or con.estado() in ("trabajando", "esperando_permiso")))
        trabajando = propio
        if con is None and su_terminal["estado"] in ("pensando", "usando"):
            trabajando = True                   # su terminal trabaja (lo dicen los hooks)
        ahora = time.time()
        permiso = self._permiso_visible(con)
        if permiso and self.compartida and con is not None and con.estado() != "esperando_permiso":
            permiso = None                      # F4: lo contestaste en su terminal (permission.replied)
        # B10 (cacería 19-nov): el registro sigue en «esperando_permiso» hasta el post_tool de lo que ya contestaste
        # aquí: con su conexión en su propio turno, ese no es un permiso de su terminal (era la tarjeta fantasma
        # «Te pide permiso en su terminal», sin Parar)
        if not permiso and su_terminal["estado"] == "esperando_permiso" and not propio:
            permiso = {"id": "", "herramienta": su_terminal.get("herramienta") or "", "detalle": "",
                       "opciones": [], "en_terminal": True}
        if permiso and self.canal == ESC and permiso.get("id"):
            leidas = [h for h in self.herr if any(str(h.get("n") or "").endswith(m) for m in
                                                  ("leer_ventana", "ver_pantalla", "contexto_escritorio"))]
            permiso = dict(permiso, leyo=bool(leidas))
            # Monito UX: lo que pide en una frase (qué, sobre qué y para qué), con lo técnico aparte
            permiso["frase"] = _frases().permiso(permiso, carpeta=self.brain, tarea=est.get("tarea") or "")
        if permiso:
            estado = "esperandote"
        elif trabajando:
            estado = "trabajando"
        elif self.error and not self.texto:
            estado = "error"
        elif self.termino and ahora - self.termino < TERMINO_S:
            estado = "termino"
        else:
            estado = "libre" if (con or not self.solo_mirar) else "dormido"
        compartida = bool(self.compartida and con is not None and con.estado() != "cerrado")
        via = via_de(self.motor)
        if via and compartida:                  # F4: la misma conversación que su terminal (no un chat aparte)
            via = dict(via, aparte=False, misma_conversacion=True, compartida=True)
        f = {"estado": estado, "desde": round(self.desde, 3), "trans": [], "existe": True,
             "viva": bool(con) or est["estado"] not in ("sin_datos", "cerrado"),
             "motor": self.motor, "status": est["estado"], "trabajando": trabajando,
             "pregunta": _pregunta_de(est) or self.pregunta_motor, "tarea": est.get("tarea") or "",
             "permiso": permiso, "uso": _uso_de(con),
             "subagentes": None, "error": self.error, "cerrado": False,
             "cola": [dict(e, desde=round(e["desde"], 3)) for e in self.cola],
             # B12: el mensaje que está abriendo su motor (se ve también tras recargar, hasta que sale)
             "abriendo": _abriendo_de(self.ocupado),
             "solo_mirar": self.solo_mirar, "via": via, "cambio": self.cambio,
             "resueltos": list(self.resueltos), "fuente": "nucleo",
             "hace": self.hace if trabajando else None, "hizo": list(self.hizo),
             "terminal": compartida or (est["estado"] not in ("sin_datos", "cerrado")
                                        and _terminal_en_registro(eventos))}
        if self.canal == ESC:
            # Monito UX: lo que está haciendo en simple («Leyendo «README.md»») y lo que el socio dejó pasar en este
            # trabajo («Sí, y lo demás en esta carpeta»)
            h = f.get("hace") or {}
            f["hace_frase"] = _frases().hace(h.get("n"), h.get("d"), h.get("f"), carpeta=self.brain) if h else ""
            f["licencia"] = licencia_de(con, self.brain)
            # ronda 2 · P2-b/P5-a (control/ausente.py): todos los permisos que esperan y lo que quedó para después
            from control import ausente
            f["fichas"] = ausente.para_la_foto(self, con)
        # modo chat: lo que escribe en vivo, limpio como lo terminado, y los archivos que va enseñando en este turno
        f["parcial"], f["archivos"] = _en_vivo(self.texto, self.brain, self.wid, self.desde, eventos) \
            if trabajando else ("", [])
        if self.cambio and ahora - self.cambio.get("t", 0) > 8:
            self.cambio = None
        # Amigable: con qué otro motor se puede seguir (sin créditos, sin instalar…), cómo va lo que Workspace
        # arregla solo, y lo que hizo solo con su «deshacer»
        if self.error and self.error.get("estado"):
            f["error"] = dict(self.error, alternativa=_AM().alternativa(self.motor))
        f["arreglo"] = _AM().arreglo(self.agente)
        f["confianza"] = _confianza(self.brain, self.motor)
        f["aviso"] = self.aviso if self.aviso and ahora - self.aviso["t"] < AVISO_S else None
        p = self.por_arreglar
        f["por_arreglar"] = {"texto": p["texto"], "ya": bool(p.get("ya"))} if p else None
        return f


def _abriendo_de(ocupado):
    o = ocupado                                 # se lee sin el candado global: el de este momento
    if not o or not o.get("texto"):
        return None
    return {"id": o["cid"], "texto": o["texto"], "desde": round(o["t"], 3)}


def _existe_en_claude(LW, brain, wid, tab=NAV, sid=None, canal=NAV):
    """¿Ya hay conversación de Claude Code con ese número? Lo dicen el historial de la página
    (alguna respuesta de Claude Code) o el registro (su terminal abrió con ese número). H4-a, en otra pestaña (`sid`:
    el número de su programa): su transcripción en esta máquina, una respuesta suya con ese número en el historial de
    la pestaña, o el registro."""
    if _tab(tab) != NAV:
        sid = sid or wid
        try:
            if LW._transcripcion("claude-code", sid):
                return True
            if any(e.get("motor") == "claude-code" and e.get("rol") == "agente" and e.get("sesion_motor") == sid
                   for e in _leer_historial(brain, tab)):
                return True
            from arquitectura import registro
            return any(e.get("session_id") == sid and e["momento"] in ("session_start", "conversacion", "turn_end")
                       and (e.get("datos") or {}).get("via") != "pagina" for e in registro.leer(brain, wid)[0])
        except Exception:
            return False
    try:
        with LW._HIST_LOCK:
            if any(e.get("motor") == "claude-code" and e.get("rol") == "agente"
                   for e in (LW._eventos(brain) if _canal(canal) == NAV else _leer_historial(brain, canal))):
                return True
    except Exception:
        pass
    try:
        from arquitectura import registro
        return any(e.get("session_id") == wid and e["momento"] in ("session_start", "conversacion", "turn_end")
                   and (e.get("datos") or {}).get("via") != "pagina" for e in registro.leer(brain, wid)[0])
    except Exception:
        return False


def _uso_de(con):
    """Campos oficiales para la conversación y /api/v2/uso."""
    u = con.uso() if con is not None else None
    if not u:
        return None

    def numero(valor):
        return isinstance(valor, (int, float)) and not isinstance(valor, bool) and 0 <= valor < float("inf")

    def contexto(usado, capacidad):
        if numero(usado) and numero(capacidad) and capacidad > 0:
            out["contexto"] = round(100 * (usado / capacidad))

    out = {}
    costo = u.get("costo_usd")
    if numero(costo):
        out["gasto"] = "$%.2f" % costo
    tokens = u.get("tokens") or {}
    fuente = u.get("fuente")
    if fuente == "acp":
        crudo = u.get("crudo") or {}
        contexto(crudo.get("used"), crudo.get("size"))
    elif fuente == "codex":
        ultimo = (tokens.get("last") or {}).get("totalTokens")
        total = (tokens.get("total") or {}).get("totalTokens")
        contexto(ultimo, tokens.get("modelContextWindow"))
        if numero(total):
            out["tokens_sesion"] = total
        limites = u.get("limites") or {}
        for clave in ("primary", "secondary"):
            limite = limites.get(clave) or {}
            usado = limite.get("usedPercent")
            minutos = limite.get("windowDurationMins")
            if not numero(usado) or usado > 100:
                continue
            duracion = numero(minutos) and minutos > 0
            if duracion and minutos == 7 * 24 * 60:
                out["semana_usada"] = usado
            elif ((duracion and minutos < 24 * 60) or (minutos is None and clave == "primary")) \
                    and "ventana" not in out:
                ventana = {"libre": round(100 - usado, 1)}
                if duracion:
                    ventana["minutos"] = minutos
                reinicio = limite.get("resetsAt")
                if numero(reinicio) and reinicio < 253402300800:
                    ventana["reinicia"] = reinicio
                out["ventana"] = ventana
    elif fuente == "claude-code":
        partes = [tokens.get(k) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                          "cache_read_input_tokens")]
        disponibles = [n for n in partes if numero(n)]
        if disponibles:
            out["tokens_turno"] = sum(disponibles)
    return out or None


def _ev(rol, texto, motor, **kw):
    t = time.time()
    return dict({"id": "v2-%s" % secrets.token_hex(8), "rol": rol, "texto": texto or "", "motor": motor,
                 "t": t, "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + "Z"},
                **{k: v for k, v in kw.items() if v})


def _archivos_del_turno(brain, wid, desde, eventos=None):
    """modo chat · los archivos que el agente enseñó (mostrar_archivo) desde `desde` (el inicio de su turno): del
    registro de la pestaña y, si su sandbox no lo dejó escribir ahí, del buzón de su cerebro. [{ruta, titulo}]."""
    from arquitectura import modo_chat, registro
    out = []
    try:
        for e in (registro.leer(brain, wid)[0] if eventos is None else eventos):
            if e.get("momento") == registro.ARCHIVO and _epoch(e.get("ts")) >= desde - 0.002:
                d = e.get("datos") or {}
                out.append({"ruta": d.get("ruta") or "", "titulo": d.get("titulo") or ""})
    except Exception:
        pass
    try:
        for d in _IA().archivos_del_buzon(brain):
            if str(d.get("pestana") or "") == str(wid) and float(d.get("ts") or 0) >= desde - 0.002:
                out.append({"ruta": d.get("ruta") or "", "titulo": d.get("titulo") or ""})
    except Exception:
        pass
    return modo_chat.juntar(out)


def _en_vivo(texto, brain, wid, desde, eventos):
    """modo chat · (parcial, archivos) del turno en curso: su texto limpio (modo_chat.limpiar) y sus tarjetas."""
    from arquitectura import modo_chat
    limpio, del_texto = modo_chat.limpiar(texto, brain)
    return limpio, modo_chat.juntar(_archivos_del_turno(brain, wid, desde, eventos), del_texto)


def _para_pintar(t, e, brain):
    """modo chat · un turno del agente como se pinta: su texto limpio (sin la sintaxis interna de su motor, sin ---
    sueltos) y sus tarjetas de archivo (las de mostrar_archivo y los enlaces a archivos DENTRO del cerebro). El historial
    guarda lo que escribió tal cual: se limpia al pintar."""
    if t.get("rol") == "yo":
        if str(e.get("envio_id") or "").startswith("rq-"):
            t["envio_id"] = e["envio_id"]
        return t
    from arquitectura import modo_chat
    texto, del_texto = modo_chat.limpiar(t.get("texto"), brain)
    guardados = e.get("archivos") if isinstance(e.get("archivos"), list) else []
    archivos = modo_chat.juntar(guardados, del_texto)
    t["texto"] = texto
    if archivos:
        t["archivos"] = archivos
    return t


def _ruta_historial(brain, tab=NAV, canal=NAV):
    """El historial por eventos de la conversación de esa pestaña (el de la de siempre: como siempre; el del
    escritorio: el suyo, aparte)."""
    LW = _LW()
    t = _t(tab, canal)
    return LW._eventos_path(brain) if t == NAV else LW._eventos_path(brain, canal=ESC) if t == ESC else LW._eventos_path(brain, t)


def _leer_historial(brain, tab=NAV, canal=NAV):
    """Los eventos de la conversación de la página (H4-a: o los de otra pestaña; o la del escritorio). Solo leyendo, sin
    migrar ni crear nada."""
    tab = _t(tab, canal)
    import historial_eventos as HE
    LW = _LW()
    if _tab(tab) != NAV:
        with LW._HIST_LOCK:
            ruta = _ruta_historial(brain, tab)
            return HE.leer(ruta) if os.path.exists(ruta) else []
    with LW._HIST_LOCK:
        if SOLO_LEER or _canal(canal) != NAV:
            ruta = _ruta_historial(brain, canal)
            return HE.leer(ruta) if os.path.exists(ruta) else []
        return LW._eventos(brain)


def _al_historial(brain, evs, desde=None, tab=NAV, canal=NAV):
    import historial_eventos as HE
    LW = _LW()
    if SOLO_LEER:
        return
    tab = _t(tab, canal)
    with LW._HIST_LOCK:
        if desde is not None:
            evs = [e for e in evs if not (e["texto"].strip() and (_ya_del_registro(
                brain, e["rol"], e["texto"], e["motor"], desde, e.get("sesion_motor", "")) if tab == NAV else
                _ya_del_registro(brain, e["rol"], e["texto"], e["motor"], desde, e.get("sesion_motor", ""), tab=tab)))]
            if not evs:
                return
        if tab != NAV:                           # H4-a: el de otra pestaña, o el del escritorio (no migra nada)
            ruta = _ruta_historial(brain, tab)
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            (HE.anexar if os.path.exists(ruta) else HE.crear)(ruta, evs)
            return
        ruta = LW._eventos_path(brain)
        LW._eventos(brain)                       # migra el de antes si hace falta (sin pantalla)
        if not os.path.exists(ruta):
            HE.crear(ruta, evs)
        else:
            HE.anexar(ruta, evs)


#: B11: lo que va diciendo su motor se guarda en disco cada PARCIAL_S como mucho (fuera del candado global). Si el
#: servidor de la página muere a media respuesta, el siguiente cierra ese turno «cortado» con lo que alcanzó a decir.
PARCIAL_S = 2.0
EN_CURSO = ("pensando", "usando", "esperando_permiso")
#: B12: cuántas horas de llegada (por id de envío) recuerda cada sesión
LLEGADAS_MAX = 200


def _ruta_parcial(brain, wid):
    clave = hashlib.sha1(("%s|%s" % (os.path.realpath(str(brain)), wid)).encode("utf-8")).hexdigest()[:20]
    return os.path.join(_paths.state_dir(), "pagina", "parcial", clave + ".json")


def _guardar_parcial(brain, wid, texto):
    if SOLO_LEER:
        return
    r = _ruta_parcial(brain, wid)
    tmp = "%s.%d.tmp" % (r, os.getpid())
    try:
        os.makedirs(os.path.dirname(r), exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)     # es lo que te contesta: solo tuyo
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"texto": texto, "t": time.time()}, fh, ensure_ascii=False)
        os.replace(tmp, r)
    except OSError:
        pass


def _parcial_de(brain, wid):
    try:
        with open(_ruta_parcial(brain, wid), encoding="utf-8") as fh:
            return str(json.load(fh).get("texto") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def _sin_parcial(brain, wid):
    try:
        os.remove(_ruta_parcial(brain, wid))
    except OSError:
        pass


# ── E9 · un reinicio de la página no contesta «no» por el socio ──
#: Monito ronda 2 (22-nov, 11:27): la página se reinició con 5 permisos esperando y el agente los leyó como «el usuario
#: no quiso». Lo que quedó sin contestar al apagar se guarda por conversación (solo en esta máquina, 600) y el
#: siguiente mensaje de ESA conversación lo lleva una vez, para cualquier motor: «la página se reinició; no los negó».
INTERRUMPIDOS_MAX = 12
INTERRUMPIDOS_VENCE_S = 7 * 24 * 3600


def _ruta_interrumpidos(brain, wid):
    clave = hashlib.sha1(("%s|%s" % (os.path.realpath(str(brain)), wid)).encode("utf-8")).hexdigest()[:20]
    return os.path.join(_paths.state_dir(), "pagina", "interrumpidos", clave + ".json")


def _permiso_en_simple(p):
    """«Bash (date)»: la herramienta y, corto, lo que iba a hacer. Solo letras de una línea (va dentro de un mensaje)."""
    h = " ".join(str((p or {}).get("herramienta") or "?").split())[:60]
    d = " ".join(str((p or {}).get("archivo") or (p or {}).get("detalle") or "").split())[:80]
    return "%s (%s)" % (h, d) if d else h


def guardar_interrumpidos(brain, wid, permisos, motivo="reinicio"):
    """Los permisos que esperaban cuando la página se apagó: se suman a los que ya hubiera de esa conversación."""
    permisos = [p for p in (permisos or []) if isinstance(p, dict)]
    if SOLO_LEER or not (brain and wid and permisos):
        return False
    r = _ruta_interrumpidos(brain, wid)
    antes = []
    try:
        with open(r, encoding="utf-8") as fh:
            antes = [x for x in (json.load(fh).get("permisos") or []) if isinstance(x, str)]
    except (OSError, ValueError, AttributeError):
        pass
    lista = antes + [x for x in (_permiso_en_simple(p) for p in permisos) if x not in antes]
    tmp = "%s.%d.tmp" % (r, os.getpid())
    try:
        os.makedirs(os.path.dirname(r), exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"permisos": lista[-INTERRUMPIDOS_MAX:], "motivo": str(motivo or "reinicio"), "t": time.time()},
                      fh, ensure_ascii=False)
        os.replace(tmp, r)
        return True
    except OSError:
        return False


def nota_de_interrumpidos(brain, wid, quitar=True):
    """La línea para el agente con lo que quedó sin contestar por un reinicio de la página, o ''. Se da UNA vez
    (`quitar`); lo de hace más de 7 días ya no se cuenta."""
    r = _ruta_interrumpidos(brain, wid)
    try:
        with open(r, encoding="utf-8") as fh:
            d = json.load(fh)
        lista = [x for x in (d.get("permisos") or []) if isinstance(x, str)]
        viejo = time.time() - float(d.get("t") or 0) > INTERRUMPIDOS_VENCE_S
    except (OSError, ValueError, AttributeError, TypeError):
        return ""
    if quitar or viejo:
        try:
            os.remove(r)
        except OSError:
            pass
    if viejo or not lista:
        return ""
    n = len(lista)
    return ("[Workspace · página reiniciada] La página local de Workspace se reinició mientras esperabas %s de tu "
            "socio: %s. Tu socio no los negó: quedaron sin contestar (si tu conversación dice que «el usuario no "
            "quiso», fue el reinicio). No los repitas por tu cuenta: dile en una frase qué quedó pendiente y, si "
            "todavía hace falta, vuelve a pedirlo." % ("un permiso" if n == 1 else "%d permisos" % n, "; ".join(lista)))


def _al_registro(s, momento, datos):
    from arquitectura import registro
    if SOLO_LEER:
        return
    # su origen la distingue del eco de los avisos de su motor en esta corrida (registro.eco_de_la_pagina)
    registro.anotar(s.brain, s.wid, momento, s.motor, (s.con.sesion if s.con else "") or "",
                    dict(datos, via="pagina", origen=registro.ORIGEN_PAGINA))


def _avisar():
    with _CAMBIO:
        _GEN[0] += 1                    # la foto común se mira otra vez en la siguiente vuelta
        _CAMBIO.notify_all()


def sesion(agente, crear=False, canal=NAV, tab=NAV):
    """La sesión de la página del agente (la crea si hace falta). None si no hay pestaña. Con `canal` «escritorio», la
    del monito de escritorio: otra pestaña, otro historial y otra sesión del motor (D1-a), con el motor del agente.
    `tab` (H4-a): la de otra pestaña (una de sus sesiones), con su motor."""
    canal = _canal(_t(tab, canal))
    if canal == NAV and _tab(tab) != NAV:
        return _sesion_de_pestana(agente, tab)
    with _LOCK:
        s = _SES.get(_clave(agente, canal))
        if s is not None:
            return s
        p = pestana(agente, crear=crear) if canal == NAV else pestana(agente, crear=crear, canal=canal)
        if not p:
            return None
        brain, _bt, wid = p
        s = _Sesion(agente, brain, wid, motor_de(agente, brain)) if canal == NAV else \
            _Sesion(agente, brain, wid, motor_de(agente, brain), canal=canal)
        s.solo_mirar = solo_mirar_de(s.motor, s._nombre())
        s.turno.acquire()                       # B11: nada tuyo sale por ella hasta conciliar (es nueva: nadie la tiene)
        _SES[_clave(agente, canal)] = s
    try:
        s.conciliar()                           # lo que dejó una página que ya no vive, fuera del candado global
    finally:
        s.turno.release()
    return s


def _motor_de_sesion(brain, wid, agente="", nombre=""):
    """El motor con que se usó una sesión de su programa: lo que dice su registro; si no lo dice (sin los avisos de
    Workspace), el motor cuyo número quedó atado a esa sesión (lo ata su lanzador), o Claude Code si su número tiene
    transcripción en esta máquina. '' si no se sabe."""
    try:
        res = _PS().resumen(brain, wid)
        if (res or {}).get("motor"):
            return res["motor"]
    except Exception:
        pass
    if not (agente and nombre):
        return ""
    try:
        import sessions_registry as reg
        return _motor_atado(reg._slug(nombre), _atados(agente, brain))
    except Exception:
        return ""


def _atados(agente, brain):
    """{slug: {motor: número}} de sus sesiones: los números que ató su lanzador en esta máquina (unos segundos en
    caché: la lista de sus sesiones se pide en cada foto)."""
    def leer():
        import sessions_registry as reg
        return {t["slug"]: {m: v for m, v in (t.get("resume") or {}).items() if v}
                for t in reg.tabs(brain, agente, archivadas=True)}
    return _cacheado(("atados", agente), leer)


def _motor_atado(slug, atados):
    """El motor de una sesión por el número que tiene atado: el único que no es el de Claude Code (que toda pestaña
    lleva), o Claude Code si su número tiene transcripción aquí. '' si no se sabe."""
    at = atados.get(slug) or {}
    otros = [m for m in at if m != "claude-code"]
    if len(otros) == 1:
        return otros[0]
    if not otros and at.get("claude-code") and _LW()._transcripcion("claude-code", at["claude-code"]):
        return "claude-code"
    return ""


def _sesion_de_pestana(agente, tab):
    """H4-a · la _Sesion de la pestaña `tab` (una de sus sesiones), con el motor de su pestaña. None si ya no existe."""
    with _LOCK:
        s = _SES.get(_clave(agente, tab))
        if s is not None:
            return s
        p = pestana(agente, tab=tab)
        if not p:
            return None
        brain, bt, wid = p
        rec = _PP().de(agente, tab) or {}
        motor = rec.get("motor") or _motor_de_sesion(brain, wid, agente, bt.get("name")) or motor_de(agente, brain)
        s = _Sesion(agente, brain, wid, motor, tab=tab)
        s.solo_mirar = solo_mirar_de(s.motor, s._nombre()) or s._no_retoma()
        s.turno.acquire()
        _SES[_clave(agente, tab)] = s
    try:
        s.conciliar()
    finally:
        s.turno.release()
    return s


# ── lo que hablas en la terminal, a la conversación de la página (desde el registro) ──
def _ingerir(brain, wid, ses=None, tab=NAV, desde=0):
    """Los mensajes y respuestas que anotaron los hooks de su terminal, al historial de la
    página (ids por posición en el registro). Devuelve los ids de los ecos para ocultar también los ya importados."""
    from arquitectura import registro
    import historial_eventos as HE
    LW = _LW()
    if SOLO_LEER:
        return
    evs, nuevos, herr = registro.leer(brain, wid)[0], [], {}
    if desde:                                    # H4-a: lo de antes ya vino de su programa al abrirla
        evs = [e for e in evs if e.get("pos", 0) >= desde]
    # El registro ya contiene el id del conector para los turnos anteriores a la marca de sesión.
    # Claude y los motores compartibles también pueden usar ese id desde la terminal.
    pagina = {(e.get("motor"), e.get("session_id")) for e in evs
              if e.get("session_id") and (e.get("datos") or {}).get("via") == "pagina"
              and (e["momento"] == registro.CONVERSACION
                   or (e.get("motor") not in (*COMPARTIBLES, "claude-code")
                       and (e.get("datos") or {}).get("origen") == registro.ORIGEN_PAGINA))}
    if _tab(tab) != NAV:
        # H4-a: la de otra pestaña retoma el MISMO número que su terminal: lo de su terminal no es eco de la página (lo
        # de la página va marcado «via: pagina» y se salta abajo)
        pagina = set()
    ecos, reintentos = set(), []
    with _LOCK:
        # El aviso compartido puede llegar antes de que mandar() confirme y anote la entrada.
        # La siguiente lectura lo cotejará con esa entrada, sin bloquear la página en el transporte.
        enviando = (ses.motor, ses.con.sesion) if ses and ses.compartida and ses.con and ses.saliendo else None
    for e in evs:
        d = e.get("datos") or {}
        clave = (e.get("motor"), e.get("session_id"))
        eid = "r-%s-%d" % (wid[:24], e["pos"])
        if d.get("origen") == registro.ORIGEN_PAGINA and d.get("reintento") and clave[0] in COMPARTIBLES:
            reintentos.append({"rol": "yo", "texto": d.get("prompt") or "", "motor": clave[0],
                               "sesion_motor": clave[1], "ts": e.get("ts") or "", "envio_id": "reintento"})
        if registro.eco_de_la_pagina(e) or clave in pagina:
            ecos.add(eid)
            continue
        if d.get("via") == "pagina" or (enviando and clave == enviando):
            continue
        if e["momento"] == "pre_tool":
            herr.setdefault(clave, []).append({"n": d.get("tool_name") or "?", "d": ""})
        elif e["momento"] in ("user_prompt", "turn_end"):
            yo = e["momento"] == "user_prompt"
            texto = d.get("prompt" if yo else "last_assistant_message") or ""
            herramientas = [] if yo else herr.pop(clave, [])
            if not texto and not yo and not herramientas:
                continue
            nuevos.append({"id": eid, "rol": "yo" if yo else "agente",
                           "texto": texto, "motor": e.get("motor") or "", "sesion_motor": e.get("session_id") or "",
                           "t": time.time(), "ts": e.get("ts") or "", "herr": herramientas, "terminal": True})
    if not nuevos:
        return ecos
    with LW._HIST_LOCK:
        ruta = _ruta_historial(brain, tab)
        hist = (LW._eventos(brain) if _tab(tab) == NAV else _leer_historial(brain, tab)) if os.path.exists(ruta) else []
        ya = {x["id"] for x in hist}
        terminal = _sin_lo_visto_en_vivo(nuevos, hist + reintentos)
        ecos.update(x["id"] for x in nuevos)
        ecos.difference_update(x["id"] for x in terminal)
        faltan = [x for x in terminal if x["id"] not in ya and (x["rol"] != "yo" or x["texto"])]
        if faltan:
            (HE.anexar if os.path.exists(ruta) else HE.crear)(ruta, faltan)
    return ecos


#: F4: cuánto se separan, a lo sumo, un mensaje visto en vivo y el mismo anotado por los hooks (s).
VENTANA_MISMO_S = 600


def _norm(texto):
    return " ".join(str(texto or "").split())


def _hora(e):
    """La hora (epoch) de un evento del historial o del registro, o None."""
    if isinstance(e.get("t"), (int, float)) and not str(e.get("id", "")).startswith("r-"):
        return float(e["t"])
    from arquitectura import registro
    import calendar
    ts = registro.ts_utc(e.get("ts")) if e.get("ts") else ""
    try:
        return calendar.timegm(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")) if ts else None
    except ValueError:
        return None


def _mismo(vivo, x, ventana=VENTANA_MISMO_S):
    """¿`x` (del registro o del export) es el mismo mensaje que `vivo` (de la página: lo que mandaste o lo que siguió
    en vivo de su terminal)? Mismo rol, mismo texto (el del registro puede traer delante la nota de contexto que la
    página agregó) y cerca en el tiempo."""
    if vivo["rol"] != x["rol"] or (vivo.get("motor") or "") != (x.get("motor") or ""):
        return False
    a, b = _norm(vivo["texto"]), _norm(x["texto"])
    if not a or not b:
        return False
    coincide = a == b or b.endswith(" " + a) or a.endswith(" " + b)
    if not coincide and vivo.get("rol") == "yo":
        from arquitectura.registro import TOPES
        crudo = x["texto"]
        if len(crudo) == TOPES["prompt"]:
            # El registro corta el prompt completo, incluida la guía o la nota antepuesta.
            partes = re.split(r"\n[ \t]*(?:---[ \t]*\n|\n)", crudo)
            recorte = _norm(partes[-1])
            coincide = a.startswith(b) or (len(partes) > 1 and len(recorte) >= 256 and a.startswith(recorte))
    if not coincide:
        return False
    ta, tb = _hora(vivo), _hora(x)
    return ta is None or tb is None or abs(ta - tb) <= ventana


#: F4c: entre un mensaje del export (su hora de creación) y el mismo en el historial (cuando la página lo anotó: una
#: respuesta larga, al terminar) puede pasar más que entre el registro y lo en vivo (s).
VENTANA_EXPORT_S = 3600
#: F4c: lo más que se trae de una vez (lo último de la conversación).
TOPE_AL_DIA = 200


def _iso(t):
    """La hora como la de _ev (al segundo): dentro de un mismo segundo manda el orden en que entraron."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + "Z"


def _sumar_lo_de_antes(brain, sesion, turnos, ocupado=lambda: False, pedido=None, tab=NAV):
    """F4c: los turnos del export de la conversación `sesion` (control.opencode.historial) que el historial de la
    página no tiene, al historial: marcados `terminal` (los escribiste allá), con la hora real (se ordenan con lo
    demás) y un id por su lugar en la conversación (`x-<sesion>-<n>`: traerlo otra vez no los repite). Lo que ya está
    (en vivo, por los hooks o de una vez anterior) no entra: mismo rol y texto, cada uno cubre a uno solo. Si la
    conversación tiene un turno en curso (`ocupado`), lo creado después de pedir el export es de ese turno y lo trae
    en vivo la página: no entra (su respuesta estaría a medias). `pedido`: cuándo se pidió el export. → cuántos
    entraron."""
    LW = _LW()
    import historial_eventos as HE
    if SOLO_LEER:
        return 0
    inicio = pedido or time.time()
    with LW._HIST_LOCK:
        ruta = _ruta_historial(brain, tab)
        hist = (LW._eventos(brain) if _tab(tab) == NAV else _leer_historial(brain, tab)) if os.path.exists(ruta) else []
        pool = [e for e in hist if e.get("rol") in ("yo", "agente") and e.get("motor") == "opencode"]
        donde = {e.get("id"): i for i, e in enumerate(pool)}
        vivo = ocupado()
        usados, faltan = set(), []
        lista = list(turnos or [])
        for n, x in list(enumerate(lista))[-TOPE_AL_DIA:]:
            if vivo and x.get("t") is not None and x["t"] >= inicio - 1:
                continue
            c = {"id": "x-%s-%d" % (str(sesion)[-24:], n), "rol": x["rol"], "texto": x["texto"], "motor": "opencode",
                 "terminal": True, "t": x["t"] if x.get("t") is not None else time.time()}
            if x.get("t") is not None:
                c["ts"] = _iso(x["t"])
            if c["id"] in donde:
                usados.add(donde[c["id"]])
                # una respuesta que se trajo a medias (la página se unió durante una herramienta larga y callada) y
                # creció: entra lo que le faltaba, como su continuación (una vez: su id lleva el largo)
                antes, ahora = pool[donde[c["id"]]].get("texto") or "", c["texto"]
                sigue = dict(c, id="%s+%d" % (c["id"], len(ahora)), texto=ahora[len(antes):].strip())
                if ahora.startswith(antes) and sigue["texto"] and sigue["id"] not in donde:
                    faltan.append(sigue)
                continue
            i = next((i for i, v in enumerate(pool) if i not in usados
                      and _mismo(v, dict(c, t=x.get("t")), VENTANA_EXPORT_S)), None)
            if i is not None:
                usados.add(i)
                continue
            faltan.append(c)
        if faltan:
            (HE.anexar if os.path.exists(ruta) else HE.crear)(ruta, faltan)
    return len(faltan)


def _sin_lo_visto_en_vivo(nuevos, hist):
    """F4: con su terminal en la MISMA conversación (OpenCode por su servidor), cada turno llega dos veces: en vivo
    (lo que mandaste desde aquí, y lo de su terminal por los eventos del servidor) y por los hooks del plugin, que
    corren en ese servidor. Lo del registro que ya está en vivo no entra otra vez; cada mensaje en vivo cubre a uno
    solo (dos «sí» seguidos en la terminal son dos), y la respuesta de un mensaje repetido, tampoco. `nuevos`
    conserva las entradas sin texto para cortar su par. Solo se cotejan así los motores compartibles."""
    pool = [e for e in hist if e.get("rol") in ("yo", "agente") and not str(e.get("id", "")).startswith("r-")
            and (e.get("envio_id") or e.get("terminal")) and e.get("motor") in COMPARTIBLES]
    usados, out, saltar_fin = set(), [], set()
    for x in nuevos:
        clave = (x.get("motor"), x.get("sesion_motor"))
        if clave[0] not in COMPARTIBLES:
            out.append(x)
            continue
        if x["rol"] == "agente" and clave in saltar_fin:
            saltar_fin.discard(clave)
            continue
        saltar_fin.discard(clave)
        i = next((i for i, v in enumerate(pool) if i not in usados
                  and (not v.get("sesion_motor") or not clave[1] or v["sesion_motor"] == clave[1])
                  and _mismo(v, x)), None)
        if i is None:
            out.append(x)
        else:
            usados.add(i)
            if x["rol"] == "yo":
                saltar_fin.add(clave)
    return out


#: F4c: lo anotado por los hooks de ESTE turno puede llevar una hora un poco anterior a la que lo vio la página (s).
HOLGURA_TURNO_S = 2.0


def _ya_del_registro(brain, rol, texto, motor, desde, sesion_motor="", tab=NAV, canal=NAV):
    """F4: ¿lo que llega en vivo de su terminal ya entró al historial por los hooks (el registro se leyó antes)? Solo lo
    anotado desde que empezó ESTE turno (`desde`): un mensaje igual de antes es otro (F4c: dos «Hola» seguidos)."""
    LW = _LW()
    with LW._HIST_LOCK:
        tab = _t(tab, canal)
        if not os.path.exists(_ruta_historial(brain, tab)):
            return False
        x = {"rol": rol, "texto": texto, "motor": motor}
        for e in (LW._eventos(brain) if _tab(tab) == NAV else _leer_historial(brain, tab))[-50:]:
            if not str(e.get("id", "")).startswith("r-"):
                continue
            if sesion_motor and e.get("sesion_motor") and e["sesion_motor"] != sesion_motor:
                continue
            h = _hora(e)
            if h is not None and h >= desde - HOLGURA_TURNO_S and _mismo(dict(e, t=h), x):
                return True
        return False


# ── las rutas (las llama localhost_web) ────────────────────────────────────
def _pend(brain):
    """La firma de sus pendientes (front_vivo._firma_pend, la de la página de antes: solo stat de su PENDIENTES.md, su
    inbox y la memoria de su conversación). Si cambia, la página vuelve a leer el panel de pendientes."""
    try:
        import front_vivo
        return front_vivo._firma_pend(brain) if brain else ""
    except Exception:
        return ""


def _PS():
    import pagina_sesiones
    return pagina_sesiones


def _sesiones_de(agente, brain, wid):
    """H3 (rama de prueba marca-lab): sus sesiones oficiales, de su registro de eventos (pagina_sesiones)."""
    import agent_brand
    import sessions_registry as reg
    LW = _LW()
    tabs = _cacheado(("tabs", agente), lambda: list(LW._pestanas_web(brain, reg.socio(brain))))
    lista = _PS().lista(brain, tabs, wid, LW._wid_de, lambda bt: agent_brand.es_archivada(bt.get("estado")))
    if any(not x.get("motor") for x in lista):
        # H4-a: una sesión sin los avisos de Workspace (su registro no dice su motor): el que ató su lanzador
        try:
            atados = _atados(agente, brain)
            for x in lista:
                x["motor"] = x.get("motor") or _motor_atado(x.get("slug"), atados)
        except Exception:
            pass
    return lista


def _al_dia_sesiones(brain, ses):
    """H3: lo que una sesión oficial terminó llega a la conversación directa como una línea (solo se anexa)."""
    import historial_eventos as HE
    LW = _LW()
    ruta = LW._eventos_path(brain)
    if SOLO_LEER or not os.path.exists(ruta):
        return
    with LW._HIST_LOCK:
        nuevas = _PS().lineas_nuevas(ses, HE.leer(ruta))
        if nuevas:
            HE.anexar(ruta, nuevas)


def sesiones(agente):
    """/api/v2/sesiones: las sesiones oficiales del agente (H3), aparte de su conversación directa."""
    brain = cerebro(agente)
    if not brain:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    p = pestana(agente)
    return {"sesiones": _sesiones_de(agente, brain, p[2] if p else "")}


def _cuenta_sesiones(agente, brain, wid):
    try:
        ses = _sesiones_de(agente, brain, wid)
        _al_dia_sesiones(brain, ses)
        return _PS().cuenta(ses)
    except Exception:
        return None


def _paquete_activo():
    try:
        from arquitectura import sesion as S
        return bool(S.activo())
    except Exception:
        return False


def manual_respaldo():
    """agente-interfaz · lo que sabe un motor que en la página no trae el núcleo (trae_nucleo): desde el modo chat, la
    guía de chat con el comando de respaldo de cada herramienta (interfaz_agente, dentro de `workspace pasos`,
    preaprobado)."""
    from arquitectura import modo_chat
    return modo_chat.guia(con_nucleo=False)


def guia_para(motor, con_nucleo, canal=NAV, manos=False):
    """modo chat · la guía que la página le manda a `motor` UNA vez por conector antes de tu primer mensaje (su vía
    «mensaje»): con sus herramientas si su conector trae el núcleo; sin él, con el comando de respaldo. '' con el
    paquete apagado (la página como antes) o si la guía ya va en la pieza de sistema de su sesión (su vía «argv»: Claude
    Code, nucleo.aplicar). La conversación guarda solo lo que escribiste. modo escritorio: la del monito (la misma guía
    de chat, con las reglas de la burbuja y, si `manos`, sus herramientas de ver y señalar)."""
    if not _paquete_activo():
        return ""
    try:
        from arquitectura import modo_chat
        if con_nucleo and modo_chat.via(motor) == "argv":
            return ""
        if _canal(canal) == ESC:
            return modo_chat.guia(con_nucleo=con_nucleo, canal=ESC, manos=manos)
        return modo_chat.guia(con_nucleo=con_nucleo)
    except Exception:
        return ""


def _perfil(agente):
    """agente-interfaz · cómo se ve (su color, su monito y el nombre con que lo ves en esta computadora: las
    preferencias de localhost_front). Si el agente se personaliza (personalizar), la página lo cambia en vivo."""
    try:
        import localhost_front as LF
        p = LF._prefs_de(LF.leer_prefs(), agente)
        av = p.get("avatar") or {}
        return {"color": av.get("color") or "", "forma": av.get("forma") or "", "nombre": p.get("nombre") or ""}
    except Exception:
        return None


def _perfil_al_dia(agente, brain):
    """Su perfil, después de aplicar lo que el agente pidió en el buzón de su cerebro (si su terminal no podía
    escribirlo: interfaz_agente.aplicar_perfil_pedido). Nunca levanta."""
    if brain and not SOLO_LEER:
        try:
            _IA().aplicar_perfil_pedido(agente, brain)
        except Exception:
            pass
    return _perfil(agente)


def _foto_de(agente, canal=NAV):
    if _canal(canal) == ESC:
        return _foto_escritorio(agente)
    from arquitectura import registro
    p = pestana(agente)
    if not p:
        brain = cerebro(agente)
        ejecuciones = _ejecuciones(agente)
        return _con_pestanas(agente, {
                "estado": "dormido", "existe": False, "viva": False, "motor": motor_de(agente),
                "cola": [], "via": via_de(motor_de(agente)), "solo_mirar": "", "fuente": "nucleo",
                "ejecuciones": ejecuciones, "skill_vigente": skill_vigente(agente, ejecuciones), "pend": _pend(brain),
                "sesiones": _cuenta_sesiones(agente, brain, "") if brain else None,
                "perfil": _perfil_al_dia(agente, brain)})
    brain, _bt, wid = p
    s = sesion(agente)
    if not SOLO_LEER:
        s.seguir_terminal()                     # F4: su terminal abierta → a su conversación, en vivo
    eventos = registro.leer(brain, wid)[0]
    f = s.foto(eventos)
    f["ejecuciones"] = _ejecuciones(agente)
    # skills-cierre (Fix 2): «la skill que corre», con UNA regla (la del servidor): la página y el hub la toman de aquí
    f["skill_vigente"] = skill_vigente(agente, f["ejecuciones"])
    f["sesiones"] = _cuenta_sesiones(agente, brain, wid)     # antes de su firma: la línea de una sesión cuenta
    if not f.get("pregunta"):                   # agente-interfaz: lo que pide su skill, en la caja como una pregunta
        f["pregunta"] = _pide_como_pregunta(agente, f["ejecuciones"], eventos) or _del_buzon(brain, wid, eventos)
    f["perfil"] = _perfil_al_dia(agente, brain)
    f["conv"] = _firma_conv(brain, wid)
    f["ajustes"] = ajustes(agente, s.motor)
    f["revision"] = _revision(agente, brain, wid)
    f["pend"] = _pend(brain)
    _con_pestanas(agente, f)
    return f


# ── H4-a: las pestañas en el borde (las mismas en el hub y en la página) ───
def _foto_tab(agente, rec):
    """La foto de la conversación de la pestaña `rec` (la misma forma que la de siempre, sin lo que es del agente:
    skills, pendientes, la revisión)."""
    from arquitectura import registro
    sl = rec["slug"]
    s = sesion(agente, tab=sl)
    p = pestana(agente, tab=sl)
    if s is None or not p:
        return {"estado": "dormido", "existe": False, "viva": False, "motor": rec.get("motor") or "", "cola": [],
                "solo_mirar": "Esta sesión ya no está en su lista.", "fuente": "nucleo", "tab": sl, "falta": True}
    brain, _bt, wid = p
    if not SOLO_LEER:
        s.seguir_terminal()
    eventos = registro.leer(brain, wid)[0]
    f = s.foto(eventos)
    f["conv"] = _firma_conv(brain, wid, sl)
    f["ajustes"] = ajustes(agente, s.motor)
    f["tab"] = sl
    f["oficial"] = s._oficial()
    return f


def _con_pestanas(agente, f):
    """La tira del agente en su foto (`tabs`: ⌂ primero, luego las abiertas, en su orden) y la foto de cada una
    (`tab_fotos`): las dos vistas pintan lo mismo."""
    try:
        abiertas = _PP().abiertas(agente)
    except Exception:
        abiertas = []
    tira, fotos = [{"slug": NAV, "nombre": NOMBRE_NAV, "tipo": NAV, "motor": f.get("motor") or "",
                    "estado": f.get("estado") or ""}], {}
    for rec in abiertas:
        try:
            ft = _foto_tab(agente, rec)
        except Exception:
            ft = {"estado": "dormido", "existe": False, "motor": rec.get("motor") or "", "cola": [], "tab": rec["slug"]}
        fotos[rec["slug"]] = ft
        tira.append({"slug": rec["slug"], "nombre": str(rec.get("nombre") or rec["slug"])[:80],
                     "motor": ft.get("motor") or rec.get("motor") or "", "tipo": rec.get("tipo") or "sesion",
                     "estado": ft.get("estado") or "", "terminal": bool(ft.get("terminal")),
                     "solo_mirar": bool(ft.get("solo_mirar")), "de": rec.get("de") or ""})
    f["tabs"], f["tab_fotos"] = tira, fotos
    return f


def _foto_escritorio(agente):
    """modo escritorio · la foto de la conversación del monito (la misma forma que la de la página, con lo que el
    monito pinta): su estado, lo que escribe en vivo, su pregunta, su permiso, su uso y su error. Sin sesiones, sin
    revisión de skills ni pendientes: eso vive en la página."""
    from arquitectura import registro
    p = pestana(agente, canal=ESC)
    if not p:
        m = motor_de(agente)
        return {"estado": "libre", "existe": False, "viva": False, "motor": m, "cola": [], "via": via_de(m),
                "solo_mirar": solo_mirar_de(m, _nombre_motor(m)), "fuente": "nucleo", "canal": ESC,
                "perfil": _perfil(agente), "encargos": _encargos_de(agente)}
    brain, _bt, wid = p
    s = sesion(agente, canal=ESC)
    eventos = registro.leer(brain, wid)[0]
    f = s.foto(eventos)
    ejec = _ejecuciones(agente, ESC)
    if not f.get("pregunta"):
        f["pregunta"] = _pide_como_pregunta(agente, ejec, eventos) or _del_buzon(brain, wid, eventos, canal=ESC)
    f["canal"] = ESC
    f["perfil"] = _perfil_al_dia(agente, brain)
    f["conv"] = _firma_conv(brain, wid, ESC)
    f["sin_manos"] = sin_manos_de(s.motor if s else motor_de(agente))
    f["encargos"] = _encargos_de(agente)
    return f


# ── modo escritorio · E1: entregas y encargos (lo largo lo hace su conversación de trabajo: encargos.py) ──
def _E():
    import encargos
    return encargos


def _encargos_de(agente):
    """Sus encargos para la foto del monito (nunca levanta: sin ellos, el monito sigue)."""
    try:
        return _E().de(agente)
    except Exception:
        return []


def encargar(agente, pedido, titulo="", plantilla="", archivo="", base="", archivo_nombre="", archivo_datos="",
             comandos=None, internet=None, como_pagina=False):
    """modo escritorio · un encargo a su conversación de trabajo (la de la página), con lo que armó la app y tu clic. Con
    SU nivel (Fable v2): lo que marcaste en su tarjeta (comandos · internet), nunca el de la página sin elegirlo."""
    return _E().crear(agente, pedido, titulo=titulo, plantilla=plantilla, archivo=archivo, base=base,
                      archivo_nombre=archivo_nombre, archivo_datos=archivo_datos, comandos=comandos, internet=internet,
                      como_pagina=como_pagina)


def encargo(agente, id, accion):
    """modo escritorio · visto, parar o reintentar un encargo."""
    return _E().accion(agente, id, accion)


def pasar(de, a, ruta="", nota="", archivo_nombre="", archivo_datos="", comandos=False, internet=False, como_pagina=False):
    """modo escritorio · «Pásaselo a…»: una entrega (o el archivo de verdad) a otro agente, como encargo suyo (con el
    nivel de ESTE encargo, no el de su página: Fable v2)."""
    return _E().pasar(de, a, ruta=ruta, nota=nota, archivo_nombre=archivo_nombre, archivo_datos=archivo_datos,
                      comandos=comandos, internet=internet, como_pagina=como_pagina)


# ── Fable v2 ⛔: el turno de un encargo va acotado a SU nivel ──────────────────
#: Del núcleo, lo que el turno de un encargo deja pasar en Claude Code (sin memoria: lo leído de un archivo ajeno no va
#: a su memoria; ver arquitectura/paquete/lanzador/encargo_regimen.py).
def _regimen_mod():
    import importlib.util
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquitectura", "paquete", "lanzador",
                        "encargo_regimen.py")
    spec = importlib.util.spec_from_file_location("workspace_encargo_regimen", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m, ruta


def regimen_claude(brain, reg):
    """Lo que lleva el turno de un encargo en Claude Code (control/claude_code.para_el_turno): `--permission-mode
    dontAsk` (lo no permitido se niega sin preguntar), su `--settings` (permitir solo lo del encargo, negar comandos e
    internet si no se marcaron, lo protegido negado como siempre, y el aviso del encargo antes de cada herramienta), qué
    herramientas pasan y cuáles no, y las marcas del turno para ese aviso."""
    R, ruta = _regimen_mod()
    n = reg["nivel"]
    base = ((ajustes_claude(brain) or {}).get("permissions") or {}).get("deny") or []
    settings = R.ajustes_claude(reg["carpeta"], reg["cerebro"], n, negar_base=base, hook=ruta)
    permitidas = list(R.INTERNAS) + ["%s%s" % (R.PREFIJOS_NUCLEO[0], h) for h in R.NUCLEO] + ["Read", "Glob", "Grep", "LS",
                                                                                              "Write", "Edit", "MultiEdit"]
    negadas = ["%s%s" % (R.PREFIJOS_NUCLEO[0], h) for h in ("memoria_nota", "memoria_checkpoint", "personalizar")]
    if n.get("comandos"):
        permitidas.append("Bash")
    else:
        negadas += list(R.COMANDOS)
    if n.get("internet"):
        permitidas += list(R.INTERNET)
    else:
        negadas += list(R.INTERNET)
    env = {R.ENV_ID: reg["id"], R.ENV_NIVEL: _E().nivel_texto(n), R.ENV_ESCRIBE: reg["carpeta"],
           R.ENV_CEREBRO: reg["cerebro"]}
    return {"modo": "dontAsk", "settings": settings, "permitidas": permitidas, "negadas": negadas, "env": env}


def entrega(agente, ruta):
    """modo escritorio · la tarjeta de una entrega (su ruta real para la app, su tipo y sus versiones)."""
    return _E().entrega(agente, ruta)


def entregas(agente):
    """modo escritorio · lo entregado del agente (el panel grande)."""
    return _E().entregas(agente)


# ── lo que una skill te pregunta y «Hacer ahora» (F6: la parte de F2 sin salas) ──
def _pregunta_de(est):
    """La pregunta abierta de una skill (MCP núcleo · preguntar), como tarjeta: con formulario la
    contestas en su terminal; en el chat, aquí (la respuesta va por la capa de control)."""
    p = est.get("pregunta")
    if not p or not p.get("id"):
        return None
    return {"id": p["id"], "pregunta": p.get("pregunta") or "", "tipo": p.get("tipo") or "texto",
            "opciones": list(p.get("opciones") or [])[:12], "paso": p.get("paso") or "",
            "en_terminal": p.get("via") == "formulario"}


#: Lo que la página tiene por la skill que corre (como su ejecVigente): sin terminar, de hace menos de 6 h; una que
#: nunca arrancó deja de contar a los 10 min.
VIGENTE_S, NUNCA_ARRANCO_S = 6 * 3600, 600


def _hora_local(s):
    try:
        import datetime as _dt
        d = _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))     # Python 3.9 no lee la «Z»
        return d.timestamp()
    except (TypeError, ValueError):
        return 0.0


def _pasos():
    import pasos
    return pasos


def _abiertas(brain, tope=20):
    """skills-cierre · las ejecuciones abiertas (arrancando, corriendo, pide) de la conversación de la página, de la
    más nueva a la más vieja (sus archivos completos, no la vista de la página)."""
    P = _pasos()
    try:
        nombres = sorted((n for n in os.listdir(P.carpeta(brain)) if n.endswith(".json")), reverse=True)[:tope]
    except OSError:
        return []
    out = []
    for n in nombres:
        e = P.leer(n[:-5], brain)
        if e and P.abierta(e) and (e.get("pestana") or NAV) == NAV:
            out.append(e)
    return out


#: Fix 3 · las herramientas de skills PROPIAS de cada motor (diagnóstico del 21-nov): Copilot «Using skill: <nombre>»,
#: OpenCode y Claude Code su herramienta `skill`/`Skill` ({"id"|"name"|"skill": …}); Kiro lee el SKILL.md.
_USA_SKILL_RE = re.compile(r"^\s*using skill:\s*(\S.*?)\s*$", re.I)
_SKILL_MD_RE = re.compile(r"(?:^|[\\/])skills[\\/](.+?)[\\/]SKILL\.md$", re.I)
#: Los motores que usan una skill LEYENDO su SKILL.md (sin herramienta de skills). En los demás, leer un SKILL.md es
#: otra cosa (el Skill Loop lo lee para mejorarla) y no se toma por usarla.
LEEN_LA_SKILL = ("kiro",)


def skill_del_motor(ev, motor=""):
    """La skill que su motor usó con su propia herramienta en este evento de herramienta (su nombre, o la ruta
    `skills/<rel>/SKILL.md` que leyó si es de los que la usan así: LEEN_LA_SKILL), o None. La de Workspace
    (usar_skill) no cuenta: esa ya se ve."""
    nombre = str(ev.get("nombre") or "")
    if "usar_skill" in nombre:
        return None
    m = _USA_SKILL_RE.match(nombre)
    if m:
        return m.group(1).split(":")[-1].strip()
    if nombre.strip().lower() in ("skill", "use_skill", "load_skill"):
        try:
            d = json.loads(str(ev.get("detalle") or "{}"))
        except ValueError:
            d = {}
        if isinstance(d, dict):
            v = next((d[k] for k in ("skill", "name", "id", "skill_name") if isinstance(d.get(k), str)), "")
            return v.split(":")[-1].strip() or None
        return None
    if motor not in LEEN_LA_SKILL:
        return None
    ruta = str(ev.get("archivo") or "")
    if not ruta:
        try:
            d = json.loads(str(ev.get("detalle") or "{}"))
            ruta = str((d.get("path") or d.get("file_path") or d.get("filePath") or "") if isinstance(d, dict)
                       else "")
        except ValueError:
            ruta = ""
    m = _SKILL_MD_RE.search(ruta.strip())
    return "skills/%s/SKILL.md" % m.group(1).replace("\\", "/") if m else None


def _sin_pide(d):
    """skills-cierre · dentro del candado de la ejecución: ¿sigue sin pedirte nada? (la que te pregunta no se pausa
    ni se cierra al acabar un turno o con Parar; la foto de `_abiertas` puede ser de antes de su `pide`)."""
    return (d or {}).get("estado") != "pide"


def _cerrar_del_motor(d, texto):
    """Fix 3 · la que activó su motor con su propia herramienta de skills (sin usar_skill, así que nunca supo su id)
    termina con su turno: «Terminó» con la primera línea de lo que contestó. → True si cambió."""
    P = _pasos()
    if not P.abierta(d):
        return False
    try:
        from arquitectura import modo_chat
        texto = modo_chat.limpiar(texto)[0]
    except Exception:
        pass
    linea = next((x.strip(" #*>-") for x in str(texto or "").splitlines()
                  if x.strip(" #*>-") and not x.strip().startswith("🧠")), "")
    P.aplicar(d, "fin", [linea[:200] or "Terminó con su turno."])
    d["cierre"] = "turno"
    return True


def _vigente(agente, ejecuciones, ahora=None):
    """La ejecución que corre en la conversación (la regla de «la skill que corre», una sola: el servidor la manda en la
    foto como `skill_vigente` y la usan la página y el hub). Una abierta (arrancando, corriendo, pide), no detenida en
    la página, de hace menos de 6 h; la que nunca arrancó deja de contar a los 10 min. `pausada` y `listo`, no."""
    ahora = time.time() if ahora is None else ahora
    P = _pasos()
    for e in ejecuciones or []:
        if not P.abierta(e) or _LW()._detenida_en_la_pagina(agente, e.get("id")):
            continue
        t = _hora_local(e.get("actualizado") or e.get("creado"))
        if e.get("estado") == "arrancando" and t and ahora - t > NUNCA_ARRANCO_S:
            continue
        if not t or ahora - t < VIGENTE_S:
            return e
    return None


def skill_vigente(agente, ejecuciones, ahora=None):
    """El id de la skill que corre en la conversación de la página (o None): lo que la foto manda como
    `skill_vigente`. La página (30_datos.js · ejecVigente) y el hub (hub_directo.vigente) no la vuelven a calcular."""
    e = _vigente(agente, ejecuciones, ahora)
    return e.get("id") if e else None


def _IA():
    import interfaz_agente
    return interfaz_agente


def _epoch(ts):
    """Una hora de un evento del registro (UTC con Z) en segundos; 0 si no se entiende."""
    try:
        import datetime as _dt
        return _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _contestada(eventos, pid, desde):
    """¿Ya se contestó? Su respuesta en el registro, o un mensaje tuyo después de la pregunta (como registro.estado:
    una pregunta del chat se da por contestada con tu siguiente mensaje). El eco de los avisos del motor en una
    corrida de la página no es tu mensaje (registro.eco_de_la_pagina)."""
    from arquitectura import registro
    for x in eventos or ():
        if x.get("momento") == registro.RESPUESTA and (x.get("datos") or {}).get("id") == pid:
            return True
        if desde and x.get("momento") == "user_prompt" and not registro.eco_de_la_pagina(x) \
                and _epoch(x.get("ts")) > desde:
            return True
    return False


def _del_buzon(brain, wid, eventos, ahora=None, canal=NAV):
    """agente-interfaz · la pregunta que el agente dejó en el buzón de su cerebro (interfaz_agente: su terminal no
    podía escribir el registro de esta máquina; Codex en su sandbox): la más nueva, de esta pestaña y de las últimas
    6 h, si no se contestó (las de antes no reviven). → la pregunta o None."""
    ahora = time.time() if ahora is None else ahora
    try:
        lista = _IA().preguntas_del_buzon(brain)
    except Exception:
        return None
    suyas = (wid, NAV, "") if _canal(canal) == NAV else (wid, _canal(canal))
    for d in reversed(lista):
        if d.get("pestana") not in suyas:
            continue
        t = float(d.get("ts") or 0)
        if ahora - t > VIGENTE_S or _contestada(eventos, d["id"], t):
            return None
        ops = [str(o) for o in d.get("opciones") or [] if o][:12]
        tipo = d.get("tipo") if d.get("tipo") in ("texto", "opcion", "confirmar") else ("opcion" if ops else "texto")
        return {"id": str(d["id"])[:60], "pregunta": str(d.get("pregunta"))[:500], "tipo": tipo, "opciones": ops,
                "paso": str(d.get("paso") or "")[:64], "en_terminal": False}
    return None


def _pide_como_pregunta(agente, ejecuciones, eventos, ahora=None):
    """agente-interfaz · el bug de Atlas (18-nov): lo que una skill pide con `workspace pasos <id> pide …` (o
    reportar_avance) se guarda en su ejecución, y la página v11 solo enseñaba en la caja (Q-2) las preguntas del
    registro (preguntar del MCP). Aquí lo que pide la skill que corre sale como la pregunta de su foto, con sus
    opciones: la caja con su marco, la barra y el proceso lo pintan igual, y responder() lo contesta. Un archivo no (su
    tarjeta lo pide con «Subir archivo»). Contestado (su respuesta, o tu siguiente mensaje), ya no sale. → la pregunta
    o None."""
    import hashlib
    e = _vigente(agente, ejecuciones, ahora)
    p = (e or {}).get("pide") or {}
    if not e or e.get("estado") != "pide" or not p.get("texto") or p.get("archivo"):
        return None
    huella = hashlib.sha1(("%s|%s" % (p.get("desde") or "", p.get("texto"))).encode("utf-8")).hexdigest()[:8]
    pid = "pide-%s-%s" % (str(e.get("id"))[-40:], huella)
    # su `desde` va en segundos: un mensaje tuyo del MISMO segundo (la instrucción que la arrancó) no la contesta
    desde = _hora_local(p.get("desde"))
    if _contestada(eventos, pid, desde + 1 if desde else 0):
        return None
    opciones = [o for o in p.get("opciones") or [] if o][:12]
    ahora_paso = next((x.get("texto") for x in e.get("pasos") or [] if x.get("estado") == "now"), "")
    return {"id": pid, "pregunta": p["texto"], "tipo": "opcion" if len(opciones) >= 2 else "texto",
            "opciones": opciones if len(opciones) >= 2 else [], "paso": (ahora_paso or "")[:200],
            "en_terminal": False, "ejecucion": e.get("id")}


def _skill_review():
    import sys
    hooks = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hooks")
    if hooks not in sys.path:
        sys.path.append(hooks)            # al final: no tapa módulos de la raíz
    import skill_review
    return skill_review


def _revision(agente, brain, wid):
    """La revisión de skills que espera en la pestaña de la página ({clave, n}), o None."""
    try:
        for r in _skill_review().pendientes_hub([{"brain": brain, "name": agente}]):
            if r.get("wid") == wid:
                return {"clave": r["clave"], "n": int(r.get("n") or 1)}
    except Exception:
        pass
    return None


def responder(agente, id, texto, canal=NAV, tab=NAV):
    """Tu respuesta a lo que preguntó una skill en el chat: va por la capa de control al mismo motor
    (un mensaje más de la conversación) y la pregunta queda contestada en el registro. H4-a: `tab` es la pestaña donde
    la viste (una de sus sesiones): la pregunta se busca en SU registro y en la de SU motor (lo mismo que enseña su
    foto) y la respuesta va a SU conversación, nunca a la de siempre. Lo que pide una skill y el buzón son de la de
    siempre (las skills corren ahí)."""
    from arquitectura import registro
    tab = _t(tab, canal)
    p = pestana(agente) if tab == NAV else pestana(agente, tab=tab)
    if not p:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    brain, _bt, wid = p
    eventos = registro.leer(brain, wid)[0]
    q = _pregunta_de(registro.estado(eventos))
    if tab == NAV and (not q or q["id"] != id):
        # lo que pide la skill que corre, o lo que el agente dejó en el buzón de su cerebro (agente-interfaz)
        q = _pide_como_pregunta(agente, _ejecuciones(agente, canal), eventos) \
            or _del_buzon(brain, wid, eventos, canal=canal)
    if not q or q["id"] != id:
        s = _ses(agente, tab)                   # B14/B15: la pregunta propia de su motor
        q = s.pregunta_motor if s is not None else None
    if not q or q["id"] != id or q["en_terminal"]:
        return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_pregunta"}
    texto = " ".join((texto or "").split())
    # sin el candado global: mandar puede abrir su motor (el id fijo evita que salga dos veces)
    t = "Respuesta a «%s»: %s" % (q["pregunta"][:120], texto)
    r = mandar(agente, t, "rq-" + id[-12:]) if tab == NAV else mandar(agente, t, "rq-" + id[-12:], tab=tab)
    if r.get("ok") and not r.get("repetido"):
        s = _ses(agente, tab)
        if s is not None:
            _al_registro(s, registro.RESPUESTA, {"id": id, "respuesta": texto})
        # skills-cierre (Fix 2): contestada, la skill sigue corriendo (aunque tu respuesta espere en la cola): antes
        # se quedaba en «te espera» 5-10 s de más
        P = _pasos()
        for e in (_abiertas(brain) if tab == NAV else ()):
            if e.get("estado") == "pide":
                try:
                    P.actualizar(e["id"], P.contestada, brain)
                except Exception:
                    pass
        _avisar()
    return r


def hacer_ahora(agente):
    """«Hacer ahora»: la revisión de skills pendiente le llega al agente por la capa de control (su
    misma conversación de la página), sin leer ni escribir en ningún panel. Sin el candado global (mandar puede
    abrir su motor): dos «Hacer ahora» seguidos los ordena el candado de la revisión (skill_review)."""
    p = pestana(agente)
    if not p:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    brain, bt, wid = p
    rev = _revision(agente, brain, wid)
    if not rev:
        return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_revision"}
    salida = {}

    def por_control(texto):
        r = mandar(agente, texto, "ha-" + secrets.token_hex(4))
        if not r.get("ok"):
            salida.update(r)
            raise RuntimeError(r.get("error") or "no salió")
    s = sesion(agente, crear=True)
    res = _skill_review().hacer_ahora_por_control(
        brain, rev["clave"], por_control,
        {"wid": wid, "nombre": (bt or {}).get("name") or NAV, "agente": agente, "motor": s.motor if s else ""})
    if res.get("accion") == "mandada":
        return {"ok": True, "msg": res.get("msg") or ""}
    if salida:
        return salida                          # lo que dijo mandar (terminal abierta, solo mirar…)
    return {"ok": False, "status": 409, "error": "localhost.err.v2_no_salio", "motivo": res.get("msg") or ""}


def _ejecuciones(agente, canal=NAV):
    try:
        d = _LW().datos_ejecuciones(agente) or {}
        return [e for e in d.get("ejecuciones") or [] if e.get("pestana") == _canal(canal)]
    except Exception:
        return []


def _firma_conv(brain, wid, tab=NAV, canal=NAV):
    from arquitectura import registro
    partes = []
    for r in (_ruta_historial(brain, _t(tab, canal)), registro.ruta(brain, wid)):
        try:
            st = os.stat(r)
            partes.append("%d.%d" % (st.st_size, st.st_mtime_ns))
        except OSError:
            partes.append("-")
    return "|".join(partes)


def vivo(v="", e="", espera=0, act="", canal=NAV):
    """El long-poll de la página (la misma forma que /api/front/vivo): vuelve en cuanto
    cambia la foto de algún agente, o a los `espera` s. Con `canal` «escritorio», el del monito: las fotos de las
    conversaciones del escritorio (la misma forma)."""
    canal = _canal(canal)
    try:
        espera = max(0.0, min(25.0, float(espera or 0)))
    except (TypeError, ValueError):
        espera = 0.0
    limite = time.time() + espera
    if canal == ESC:
        return _vivo_escritorio(v, e, limite)
    with _ACTIVOS_LOCK:
        _ACTIVOS[0] += 1
        solo = _ACTIVOS[0] == 1
    try:
        primera = True
        while True:
            # la de un solo cliente, al día al entrar (como siempre); con muchos esperando, la misma para todos
            fotos, firma = _fotos_comunes(forzar=primera and solo)
            primera = False
            if e != _EPOCA or v != firma:
                return {"v": firma, "e": _EPOCA, "completo": True, "agentes": fotos, "ocupada": pagina_ocupada()}
            if time.time() >= limite:
                return {"v": v, "e": _EPOCA, "agentes": {}, "ocupada": pagina_ocupada()}
            with _CAMBIO:
                _CAMBIO.wait(PASO_S)
    finally:
        with _ACTIVOS_LOCK:
            _ACTIVOS[0] -= 1


def _vivo_escritorio(v, e, limite):
    """El long-poll del Compañero de escritorio: las fotos de las conversaciones del escritorio (la misma forma). Es un
    solo cliente (el puente de la app), así que lleva su propia vuelta; la foto común de la página no se toca."""
    rapida, armada = None, 0.0
    while True:
        r = _firma_rapida(ESC)
        if r != rapida or time.time() - armada > 2.0:      # algo cambió (o cada 2 s: las skills)
            rapida, armada = r, time.time()
            fotos = {}
            for agente, _brain in cerebros():
                try:
                    fotos[agente] = _foto_de(agente, ESC)
                except Exception:
                    continue
            firma = _firma(fotos)
            if e != _EPOCA or v != firma:
                return {"v": firma, "e": _EPOCA, "completo": True, "agentes": fotos}
        if time.time() >= limite:
            return {"v": v, "e": _EPOCA, "agentes": {}}
        with _CAMBIO:
            _CAMBIO.wait(PASO_S)


#: La foto de todos los agentes, UNA para todos los que esperan en /api/v2/vivo: la firma rápida se mira a lo más una
#: vez por PASO_S (o en cuanto algo avisa, _GEN) y la foto entera solo si cambió o cada 2 s (las skills). Con 60 hubs
#: escuchando, cada uno la calculaba por su cuenta (su firma cada 0.4 s y su foto cada 2 s): la página se iba a 130 %
#: de CPU y nada más le contestaba.
_COMUN = {"t": -1e9, "gen": -1, "rapida": None, "armada": -1e9, "fotos": {}, "firma": ""}
_COMUN_LOCK = threading.Lock()
_GEN = [0]
_ACTIVOS = [0]
_ACTIVOS_LOCK = threading.Lock()


def _fotos_comunes(forzar=False):
    """(fotos, firma) de todos los agentes, compartidas por los long-polls. `forzar`: al día ahora mismo."""
    with _COMUN_LOCK:
        c, ahora = _COMUN, time.time()
        if forzar or c["gen"] != _GEN[0] or ahora - c["t"] >= PASO_S * 0.9:
            c["gen"], c["t"] = _GEN[0], ahora
            r = _firma_rapida()
            if forzar or r != c["rapida"] or ahora - c["armada"] > 2.0:     # algo cambió (o cada 2 s: las skills)
                fotos = {}
                for agente, _brain in cerebros():
                    try:
                        fotos[agente] = _foto_de(agente)
                    except Exception:
                        continue
                c.update(rapida=r, armada=ahora, fotos=fotos, firma=_firma(fotos))
        return c["fotos"], c["firma"]


def pagina_ocupada():
    """¿Algo de lo que esta página abrió está a medio hacer (un turno, un permiso, un mensaje abriendo su motor o en
    cola)? «Apagar» lo cortaría: el relevo tras una actualización (localhost_fondo.renovar) espera a que quede libre."""
    for s in list(_SES.values()):
        try:
            con = getattr(s, "con", None)
            if getattr(s, "turno_pendiente", False) or getattr(s, "ocupado", None) or getattr(s, "cola", None) or \
                    (con is not None and con.estado() in ("trabajando", "esperando_permiso")):
                return True
        except Exception:
            return True
    # crear o conectar un agente corre en un hilo fuera de _SES: cortarlo lo dejaría a medio configurar
    for modulo in ("agent_create_job", "agent_load_job"):
        try:
            m = sys.modules.get(modulo)             # sin cargarlo aquí (esto corre en cada consulta de la página)
            job = m.active() if m is not None else None
            if job is not None and not job.get("done"):
                return True
        except Exception:
            continue
    return False


def _firma_rapida(canal=NAV):
    """Lo barato de mirar: el tamaño del registro y del historial de cada pestaña, y la
    sesión de la página. Si no cambió, la foto tampoco (salvo el reloj de «terminó»)."""
    out = []
    for agente, _b in cerebros():
        p = pestana(agente) if canal == NAV else pestana(agente, canal=canal)
        if p:
            brain, _bt, wid = p
            out.append(_firma_conv(brain, wid, canal))
        if canal == ESC:
            try:
                out.append(_E().firma(agente))      # E1: el avance de sus encargos (su conversación de trabajo)
            except Exception:
                pass
        s = _ses(agente, canal)
        if s:
            out.append(_firma_ses(s))
        try:                                    # H4-a: sus pestañas (cuáles y cómo va cada una)
            out.append(_PP().firma(agente))
            for rec in _PP().abiertas(agente):
                pt = pestana(agente, tab=rec["slug"])
                if pt:
                    out.append(_firma_conv(pt[0], pt[2], rec["slug"]))
                st = _ses(agente, rec["slug"])
                if st:
                    out.append(_firma_ses(st))
        except Exception:
            pass
    return repr(out)


def _firma_ses(s):
    con = s.con                                 # una vez: un soltar() entre dos lecturas daba 500 en /vivo
    return (s.motor, con.estado() if con else "", len(s.texto), len(s.cola),
            (s.permiso or {}).get("id"), len(s.en_espera), (s.pregunta_motor or {}).get("id"),
            (s.ocupado or {}).get("cid"),     # B12: el que abre su motor sale en la foto
            bool(s.error), s.solo_mirar,
            bool(s.termino and time.time() - s.termino < TERMINO_S), bool(s.cambio))


def _firma(fotos):
    import hashlib
    return hashlib.sha1(json.dumps(fotos, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _nota_de_contexto(brain, motor, tab=NAV):
    """(nota, marcar): la nota de contexto del sistema de antes (localhost_web.nota_de_contexto: lo que se habló con
    los OTROS motores desde la última vez de `motor`, una vez por vuelta), con su texto entero en lugar del renglón
    que nombraba su archivo. ('', None) si no hay nada que contarle. `marcar()` la deja contada."""
    if SOLO_LEER or not (brain and motor):
        return "", None
    LW = _LW()
    try:
        if _tab(tab) == NAV:
            linea, marcar = LW.nota_de_contexto(brain, motor)
        else:                                   # H4-a: la de otra pestaña (la que siguió de otra con otro motor)
            linea, marcar = LW.nota_de_contexto(brain, motor, tab)
        if not linea:
            return "", None
        with open(LW._contexto_path(brain) if _tab(tab) == NAV else LW._contexto_path(brain, tab),
                  encoding="utf-8") as fh:
            cuerpo = fh.read().strip()
    except Exception:
        return "", None
    return "%s\n%s\n%s" % (LW._CTX_INI, cuerpo, LW._CTX_FIN), marcar


def _en_orden(evs):
    """Los eventos del historial en orden de hora (estable) y con su hora en UTC con Z. Lo de la
    terminal entra al historial cuando la página lo lee, no cuando pasó, y el registro de antes
    escribía hora local sin zona: así todo se ordena junto. Uno sin hora sigue al de antes."""
    from arquitectura import registro
    out, clave = [], ""
    for i, e in enumerate(evs):
        ts = registro.ts_utc(e.get("ts")) if e.get("ts") else ""
        if ts:
            e, clave = dict(e, ts=ts), ts
        out.append((clave, i, e))
    out.sort(key=lambda x: (x[0], x[1]))
    return [e for _c, _i, e in out]


def conversacion(agente, slug=NAV, v="", canal=NAV):
    """La conversación de la página (la forma de /api/conversacion): su historial por
    eventos, con lo de la terminal que llegó por el registro y, al final, el turno en curso. Con `canal` (o `slug`)
    «escritorio», la del monito (_conversacion_escritorio)."""
    if _canal(canal) == ESC or slug == ESC:
        return _conversacion_escritorio(agente, v)
    import historial_eventos as HE
    LW = _LW()
    if slug and slug != NAV:
        return _conversacion_tab(agente, slug, v)
    p = pestana(agente)
    if not p or slug != NAV:
        return {"soporta": False, "motor": "", "vivo": False}
    brain, _bt, wid = p
    ecos = set()
    try:
        ecos = _ingerir(brain, wid, _SES.get(agente)) or set()
    except Exception:
        pass
    evs = _en_orden([e for e in _leer_historial(brain) if e.get("id") not in ecos])
    s = sesion(agente)
    if not evs:
        return {"soporta": True, "fuente": "nucleo", "motor": s.motor if s else "", "vivo": False,
                "total": 0, "turnos": [], "motores": []}
    # solo lo terminado: el texto del turno en curso viaja en la foto (`parcial`), y así no sale dos veces
    base = HE.antes_de(LW._eventos_path(brain))
    turnos, motores = [], []
    for m, es, _contado, fallido in LW._tramos(evs):
        if fallido:
            continue                               # el cambio a ese motor falló y no se le habló: sin «Siguió con …»
        motores.append({"i": base + len(turnos), "motor": str(m or "")[:30]})
        # F3c, punto 3: qué motor contestó (o a cuál le hablaste) cada turno; si el evento no lo guardó, el de su tramo.
        # modo chat: lo del agente, limpio y con sus tarjetas de archivo
        turnos += [_para_pintar(dict(LW._turno(e), motor=str(e.get("motor") or m or "")[:30] or None), e, brain)
                   for e in es]
    ventana = turnos[-LW.MAX_TURNOS:]
    d = {"soporta": True, "fuente": "nucleo", "motor": s.motor if s else "", "vivo": bool(s and s.con),
         "total": base + len(turnos), "turnos": ventana, "motores": motores,
         # H3 (rama de prueba marca-lab): lo que terminaron sus sesiones oficiales, con el turno antes del que va
         "sesiones": _PS().en_la_conversacion(evs, ventana, base + len(turnos) - len(ventana))}
    return LW.con_version(agente, NAV, d, v)


def _conversacion_escritorio(agente, v=""):
    """modo escritorio · la conversación del monito: su historial (aparte del de la página), limpio y con sus tarjetas
    de archivo, como la de la página. Sin lo de su terminal (no tiene) ni las líneas de sesiones."""
    import historial_eventos as HE
    LW = _LW()
    p = pestana(agente, canal=ESC)
    s = _ses(agente, ESC)
    if not p:
        return {"soporta": True, "fuente": "nucleo", "motor": s.motor if s else motor_de(agente), "vivo": False,
                "total": 0, "turnos": [], "motores": [], "canal": ESC}
    brain = p[0]
    evs = _en_orden(_leer_historial(brain, ESC))
    ruta = _ruta_historial(brain, ESC)
    base = HE.antes_de(ruta) if os.path.exists(ruta) else 0
    turnos, motores = [], []
    for m, es, _contado, fallido in LW._tramos(evs):
        if fallido:
            continue
        motores.append({"i": base + len(turnos), "motor": str(m or "")[:30]})
        turnos += [_para_pintar(dict(LW._turno(e), motor=str(e.get("motor") or m or "")[:30] or None), e, brain)
                   for e in es]
    ventana = turnos[-LW.MAX_TURNOS:]
    d = {"soporta": True, "fuente": "nucleo", "motor": s.motor if s else motor_de(agente, brain),
         "vivo": bool(s and s.con), "total": base + len(turnos), "turnos": ventana, "motores": motores, "canal": ESC}
    return LW.con_version(agente, ESC, d, v)


def _conversacion_tab(agente, slug, v=""):
    """H4-a · la conversación de otra pestaña (la forma de la de siempre): su historial (lo de su programa al abrirla y
    lo de la página), lo que siguió en su terminal (de su registro) y, al final, el turno en curso. Mirarla cuenta como
    verla (la que llevas más tiempo sin ver es la que se cierra sola)."""
    import historial_eventos as HE
    LW = _LW()
    p = pestana(agente, tab=slug)
    if not p:
        return {"soporta": False, "motor": "", "vivo": False}
    brain, _bt, wid = p
    rec = _PP().de(agente, slug) or {}
    s = sesion(agente, tab=slug)
    # lo que se trajo de su programa al abrirla llega hasta `registro_desde` de su registro: lo de antes no se repite
    desde = next((int(e.get("registro_desde") or 0) for e in _leer_historial(brain, slug)
                  if e.get("rol") == "sistema" and e.get("tipo") == "importado"), 0)
    ecos = set()
    try:
        ecos = _ingerir(brain, wid, s, tab=slug, desde=desde) or set()
    except Exception:
        pass
    if rec and not SOLO_LEER:
        try:
            _PP().ver(agente, slug)
        except OSError:
            pass
    evs = _en_orden([e for e in _leer_historial(brain, slug) if e.get("id") not in ecos])
    motor = s.motor if s else rec.get("motor") or ""
    if not evs:
        return LW.con_version(agente, slug, {"soporta": True, "fuente": "nucleo", "motor": motor, "vivo": False,
                                             "total": 0, "turnos": [], "motores": [], "tab": slug}, v)
    ruta = _ruta_historial(brain, slug)
    base = HE.antes_de(ruta) if os.path.exists(ruta) else 0
    turnos, motores = [], []
    for m, es, _contado, fallido in LW._tramos(evs):
        if fallido:
            continue
        motores.append({"i": base + len(turnos), "motor": str(m or "")[:30]})
        turnos += [_para_pintar(dict(LW._turno(e), motor=str(e.get("motor") or m or "")[:30] or None), e, brain)
                   for e in es]
    d = {"soporta": True, "fuente": "nucleo", "motor": motor, "vivo": bool(s and s.con),
         "total": base + len(turnos), "turnos": turnos[-LW.MAX_TURNOS:], "motores": motores, "tab": slug}
    return LW.con_version(agente, slug, d, v)


def mandar(agente, texto, cid="", reintento="", canal=NAV, contexto=None, tab=NAV):
    """Tu mensaje a la conversación de la página (o, con `canal` «escritorio», a la del monito, con lo que tenías
    enfrente en `contexto`: D3-a)."""
    texto = (texto or "").strip()
    if not texto:
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    cid = cid or "c" + secrets.token_hex(6)
    if _t(tab, canal) == ESC:
        return _mandar_escritorio(agente, texto, cid, reintento, contexto)
    if _tab(tab) != NAV:                        # H4-a: a la conversación de esa pestaña
        s = sesion(agente, tab=tab)
        if s is None:
            return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
        _seguir_abierta(agente, tab, s)
        return s.mandar(texto, cid, reintento=reintento) if reintento else s.mandar(texto, cid)
    with _LOCK:
        s = sesion(agente, crear=True)
    if s is None:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    return s.mandar(texto, cid, reintento=reintento) if reintento else s.mandar(texto, cid)


def _mandar_escritorio(agente, texto, cid, reintento="", contexto=None):
    with _LOCK:
        s = sesion(agente, crear=True, canal=ESC)
        if s is None:
            return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
        viejo = _al_motor_de_la_pagina(s)
    _cerrar_con(viejo)
    if not manos_para(s.motor) and manos_mcp():
        contexto = None                 # su motor actúa sin preguntar: lo de tu pantalla no le llega (sin_manos_de)
    return s.mandar(texto, cid, reintento=reintento, frente=frente_de(contexto))


def _al_motor_de_la_pagina(s):
    """modo escritorio · el monito habla con el motor del agente (el que elegiste en la página): si lo cambiaste desde
    que se abrió su conversación, y está libre, sigue con el nuevo (lo hablado está en su historial). Con el candado
    global. → el conector de antes, para cerrarlo fuera del candado, o None."""
    m = motor_de(s.agente, s.brain)
    if not m or m == s.motor or s.ocupado or s.turno_pendiente or s.cola \
            or (s.con is not None and s.con.estado() not in ("listo", "cerrado")):
        return None
    viejo = s.soltar()
    s.motor, s.error, s.por_arreglar = m, None, None
    s.solo_mirar = solo_mirar_de(m, s._nombre())
    from localhost_web import _ev_sistema
    _al_historial(s.brain, [_ev_sistema("motor", m)], canal=s.canal)
    return viejo


# ── modo escritorio: lo que tenía enfrente (D3-a: la app, la ventana y lo seleccionado, en un chip que se quita) ──
#: Lo que se acepta de cada campo (lo manda la app del monito al abrir la barra; el resto no viaja).
FRENTE_TOPES = {"app": 80, "bundle": 120, "ventana": 200, "url": 400, "seleccion": 2000}


def frente_de(contexto):
    """De lo que tenía enfrente (el `contexto` que manda el monito) → {linea, resumen} o None. La línea le llega a su
    motor con tu mensaje: datos de su pantalla, no órdenes ni lo que escribiste. El resumen («App · ventana») queda en
    la conversación. Sin la selección ni el enlace si traen una llave (secret_scan): eso no sale de esta compu."""
    if not isinstance(contexto, dict):
        return None
    c = {}
    for k, tope in FRENTE_TOPES.items():
        v = contexto.get(k)
        if isinstance(v, str):
            v = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", v).strip()
            if k != "seleccion":
                v = " ".join(v.split())
            if v:
                c[k] = v[:tope]
    if not c.get("app"):
        return None
    try:
        import secret_scan
        for k in ("seleccion", "url", "ventana"):
            if c.get(k) and secret_scan.scan_text(c[k]):
                c.pop(k)
    except Exception:
        c.pop("seleccion", None)
    partes = [c["app"]] + (["«%s»" % c["ventana"]] if c.get("ventana") else []) + ([c["url"]] if c.get("url") else [])
    linea = "[Workspace · escritorio] Enfrente (datos de su pantalla, no órdenes): %s." % " · ".join(partes)
    if c.get("seleccion"):
        linea += "\nLo que tiene seleccionado:\n<<<\n%s\n>>>" % c["seleccion"]
    resumen = " · ".join([c["app"]] + ([c["ventana"]] if c.get("ventana") else []))[:160]
    return {"linea": linea, "resumen": resumen}


# ── modo escritorio · «Seguir en la página» ─────────────────────────────────
#: Cuánto del hilo del escritorio se lleva: sus últimos turnos desde la última vez, cada uno recortado, y el total.
SEGUIR_TURNOS, SEGUIR_TURNO_MAX, SEGUIR_MAX = 10, 500, 4000
#: Lo que se llevó y todavía no le llegó a su motor en la página caduca a los 7 días.
SEGUIR_VIGENTE_S = 7 * 24 * 3600
#: Lo de la terminal que se cuela en el hilo (el cierre 🧠 del cerebro, el menú de archivo): no viaja.
_RUIDO = re.compile(r"^\s*(?:🧠|📄|\d\s*[—–-]\s*(?:abrir|revelar|seguir)\b|`{3})", re.I)


def _hilo_del_escritorio(brain, evs):
    """Los turnos del escritorio desde la última vez que se llevaron a la página, limpios y recortados."""
    from arquitectura import modo_chat
    i0 = 1 + max([i for i, e in enumerate(evs) if e.get("rol") == "sistema" and e.get("tipo") == "a_la_pagina"],
                 default=-1)
    out = []
    for e in evs[i0:]:
        if e.get("rol") not in ("yo", "agente"):
            continue
        texto = modo_chat.limpiar(e.get("texto") or "", brain)[0] if e.get("rol") == "agente" else e.get("texto") or ""
        texto = " ".join(" ".join(ln.split()) for ln in texto.splitlines() if ln.strip() and not _RUIDO.match(ln))
        if texto:
            out.append((e["rol"], texto if len(texto) <= SEGUIR_TURNO_MAX else texto[:SEGUIR_TURNO_MAX - 1] + "…"))
    return out[-SEGUIR_TURNOS:]


def seguir_en_la_pagina(agente):
    """modo escritorio · «Seguir en la página»: el hilo del escritorio pasa a la conversación de la página, sin IA y sin
    mandarle nada a su motor todavía (lo más simple que no se pierde):
      · lo último que hablaron (desde la última vez que lo pasaste), cada turno recortado, queda en las preferencias del
        agente y le llega UNA vez a su motor con tu próximo mensaje en la página, como la nota de la maleta;
      · la conversación de la página enseña una línea «Escritorio» (la de las sesiones: pagina_sesiones), así ves que
        llegó;
      · en la del escritorio queda la marca de hasta dónde se llevó (la próxima vez solo va lo nuevo).
    Abrir la página en ese agente lo hace quien llama (el monito). → {ok, turnos}: 0 si no había nada nuevo."""
    from localhost_web import _ev_sistema
    pe = pestana(agente, canal=ESC)
    if not pe:
        return {"ok": True, "turnos": 0}
    brain = pe[0]
    hilo = _hilo_del_escritorio(brain, _leer_historial(brain, ESC))
    if not hilo:
        return {"ok": True, "turnos": 0}
    s = _ses(agente, ESC)
    motor = (s.motor if s else "") or motor_de(agente, brain)
    cuerpo = "\n".join("%s: %s" % ("El socio" if rol == "yo" else "Tú", t) for rol, t in hilo)
    with _LOCK:
        p = prefs(agente)
        antes = p.get("del_escritorio") if isinstance(p.get("del_escritorio"), dict) else None
        if antes and time.time() - float(antes.get("t") or 0) < SEGUIR_VIGENTE_S:
            cuerpo = (str(antes.get("cuerpo") or "") + "\n" + cuerpo).strip()
        if len(cuerpo) > SEGUIR_MAX:
            cuerpo = "…" + cuerpo[-(SEGUIR_MAX - 1):]
        p["del_escritorio"] = {"cuerpo": cuerpo, "t": time.time(), "n": len(hilo)}
        _guardar_prefs(agente, p)
    tuyos = [t for rol, t in hilo if rol == "yo"]
    tema = (tuyos or [hilo[0][1]])[0]
    tema = tema[:120] + ("…" if len(tema) > 120 else "")
    # la línea de la página («Terminó en <motor> · «Escritorio»: …»): de qué era, y que sigue aquí
    linea = "«%s»%s; sigue aquí" % (tema, " y %d mensajes más" % (len(tuyos) - 1) if len(tuyos) > 1 else "")
    pn = pestana(agente, crear=True)
    if pn:
        _al_historial(pn[0], [{"id": "esc-%s" % secrets.token_hex(6), "rol": "sistema", "tipo": "sesion",
                               "texto": linea,
                               "motor": "", "sesion": pe[2], "nombre": "Escritorio", "sesion_motor": motor,
                               "t": time.time(), "ts": _iso(time.time())}])
    _al_historial(brain, [_ev_sistema("a_la_pagina", motor, n=len(hilo))], canal=ESC)
    _avisar()
    return {"ok": True, "turnos": len(hilo)}


def _nota_del_escritorio(agente):
    """(nota, marcar): lo que pasaste del escritorio a la página («Seguir en la página»), para tu próximo mensaje en la
    página, o ('', None). `marcar()` lo da por entregado (solo ese: uno que llegó mientras tanto, se queda)."""
    if SOLO_LEER:
        return "", None
    d = prefs(agente).get("del_escritorio")
    if not isinstance(d, dict) or not d.get("cuerpo") or time.time() - float(d.get("t") or 0) > SEGUIR_VIGENTE_S:
        return "", None
    nota = ("[Workspace · del escritorio] El socio siguió aquí lo que hablaron en Workspace Compañero, su app de escritorio (su otra "
            "conversación contigo). Lo último, para que sigas el hilo sin volver a preguntar:\n%s" % d["cuerpo"])

    def marcar():
        with _LOCK:
            p = prefs(agente)
            if isinstance(p.get("del_escritorio"), dict) and p["del_escritorio"].get("t") == d.get("t"):
                p.pop("del_escritorio")
                _guardar_prefs(agente, p)
    return nota, marcar


def _quitar_permiso(s, id):
    """El pendiente `id` de la sesión (el que se ve o uno en espera: B09), quitado; el siguiente pasa a verse. → él o
    None. Con el candado global."""
    if s.permiso and s.permiso["id"] == id:
        pm, s.permiso = s.permiso, (s.en_espera.pop(0) if s.en_espera else None)
        return pm
    for i, p in enumerate(s.en_espera):
        if p["id"] == id:
            return s.en_espera.pop(i)
    return None


def _frases():
    from escritorio import frases
    return frases


def licencia_de(con, brain):
    """Monito UX · la licencia del turno de esa conversación, en simple: {"texto", "usadas", "ultima"} o None."""
    try:
        return _frases().licencia(con.licencia() if con is not None else None, carpeta=brain)
    except Exception:
        return None


def permiso(agente, id, decision, canal=NAV, tab=NAV):
    with _LOCK:
        s = _ses(agente, _t(tab, canal))
    if s is None:
        return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_permiso"}
    # El conector puede emitir «terminado» al contestar. El bombeo debe esperar a que anotemos la decisión.
    with s.turno:
        with _LOCK:
            con = s.con
            pm = _quitar_permiso(s, id) if con is not None else None
        if pm is None:
            return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_permiso"}
        try:
            con.responder_permiso(id, decision)
        except Exception:
            with _LOCK:
                if s.con is con:                    # vuelve adelante, como estaba
                    if s.permiso is not None:
                        s.en_espera.insert(0, s.permiso)
                    s.permiso = pm
            return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_permiso"}
        with _LOCK:
            if s.con is con:
                # «permitir_turno» (Monito UX) se guarda como lo que es para el motor: un «permitir» (y que fue por turno)
                r = {"herramienta": pm["herramienta"][:80], "detalle": pm["detalle"][:200],
                     "decision": "permitir" if decision == "permitir_turno" else decision}
                if decision == "permitir_turno":
                    r["turno"] = True
                if pm.get("archivo"):
                    r["archivo"] = pm["archivo"][:300]
                if pm.get("que"):
                    r["que"] = pm["que"]
                s.resueltos.append(r)
            _avisar()
    return {"ok": True}


def permiso_despues(agente, ids, decision):
    """Monito ronda 2 · P2-b: «Permitir y seguir» (o «No») de una ficha que quedó para después (control/ausente.py)."""
    from control import ausente
    return ausente.de_la_pagina(sys.modules[__name__], agente, ids, decision)


def _pausar_al_parar(s):
    """skills-cierre · Parar: la skill que corría (arrancando o corriendo, ya con su instrucción enviada) se pausa en
    ese momento con motivo «parado» (su motor puede tardar en cerrar el turno, o no tener conector aquí). Si su motor
    sigue reportando, la retoma; al cerrar su turno parado vuelve a pausarse."""
    if s is None or SOLO_LEER or s.tab != NAV:
        return
    P = _pasos()
    with _LOCK:
        esperan = [x["id"] for x in s.cola] + [x["cid"] for x in (s.ocupado,) if x]
    for e in _abiertas(s.brain):
        if e.get("estado") != "pide" and not any(c.startswith("skill-" + e["id"]) for c in esperan):
            try:                                # otra vez dentro del candado: su `pide` pudo llegar después de la foto
                P.actualizar(e["id"], lambda d: _sin_pide(d) and P.pausar(d, "parado"), s.brain)
            except Exception:
                pass


def parar(agente, canal=NAV, tab=NAV):
    # B11: crearla concilia lo que dejó una página que ya no vive
    t = _t(tab, canal)
    s = sesion(agente) if t == NAV else sesion(agente, tab=t)
    _pausar_al_parar(s)
    with _LOCK:
        con = s.con if s is not None else None
    if con is None:
        # B11: sin conector suyo aquí, lo que trabaja es su terminal (lo dicen sus hooks): se para ahí
        try:
            from arquitectura import registro
            if s is not None and registro.estado(_de_su_terminal(registro.leer(s.brain, s.wid)[0]))["estado"] \
                    in EN_CURSO:
                return {"ok": True, "parado": False, "en_su_terminal": True}
        except Exception:
            pass
        return {"ok": True, "parado": False}
    try:
        return {"ok": True, "parado": bool(con.parar())}
    finally:
        _avisar()


def quitar(agente, cid, canal=NAV, tab=NAV):
    with _LOCK:
        s = _ses(agente, _t(tab, canal))
        if s is None:
            return {"ok": True}
        s.cola = [x for x in s.cola if x["id"] != cid]
        s.vistos.discard(cid)
        _avisar()
        return {"ok": True}


def cambiar_motor(agente, motor, tab=NAV):
    """Sigue la MISMA conversación de la página con otro motor (lo hablado viaja en su
    historial; el motor nuevo abre con su maleta). Si el de antes se estaba abriendo (o no contestaba), se suelta:
    no se espera a que abra. H4-a: una sesión de otra pestaña es de su motor: cambiarlo abre una pestaña nueva que
    sigue con la nota de contexto (tab_otro_motor)."""
    if _tab(tab) != NAV:
        return tab_otro_motor(agente, tab, motor)
    with _LOCK:
        s = sesion(agente, crear=True)
        if s is None:
            return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
        if s.con is not None and (s.turno_pendiente or s.con.estado() in ("trabajando", "esperando_permiso")):
            return {"ok": False, "status": 409, "error": "localhost.err.trabajando", "datos": {}}
        de = s.motor
        p = prefs(agente)
        p["motor"] = motor
        _guardar_prefs(agente, p)
        viejo = s.soltar()
        s.motor, s.solo_mirar, s.error = motor, "", None
        s.por_arreglar = None                   # Amigable: lo que esperaba al motor de antes ya no sale solo
        s.solo_mirar = solo_mirar_de(motor, s._nombre())
        if de != motor:
            from localhost_web import _ev_sistema
            _al_historial(s.brain, [_ev_sistema("motor", motor)])
        s.cambio = {"motor": motor, "de": de, "paso": "listo", "t": time.time()}
        _avisar()
    _cerrar_con(viejo)
    ar = _AM().arreglo(agente)
    if ar and ar.get("motor") != motor:
        _AM().olvidar(agente)                   # el arreglo del motor de antes ya no es de esta conversación
    return {"ok": True, "estado": "listo"}


def ajustes(agente, motor=None):
    """Lo que la capa de control sabe cambiar de su motor (hoy: el modelo de Claude Code,
    por corrida) y lo elegido: la forma de foto.ajustes de antes."""
    motor = motor or motor_de(agente)
    elegido = (prefs(agente).get("modelo") or {}).get(motor)
    valores = {}
    if elegido:
        t = dict(MODELOS.get(motor, ())).get(elegido, elegido)
        valores["modelo"] = {"actual": {"v": elegido, "t": t}}
    return {"motor": motor, "valores": valores, "guardados": {motor: {"modelo": elegido}} if elegido else {},
            "tabla": [{"k": "modelo", "t": "Modelo", "via": "control",
                       "opciones": [{"v": v, "t": t} for v, t in MODELOS[motor]]}] if motor in MODELOS else []}


def ajuste(agente, ajuste, valor):
    with _LOCK:
        motor = motor_de(agente)
        if ajuste != "modelo" or valor not in dict(MODELOS.get(motor, ())):
            return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_ajuste"}
        s = _SES.get(agente)
        if s and s.con is not None and s.con.estado() != "listo":
            return {"ok": False, "status": 409, "error": "localhost.err.trabajando", "datos": {}}
        p = prefs(agente)
        p.setdefault("modelo", {})[motor] = valor
        _guardar_prefs(agente, p)
        viejo = s.soltar() if s else None       # la próxima corrida ya va con el modelo nuevo
        e = _ses(agente, ESC)                   # la del monito también, si está libre
        viejo_esc = e.soltar() if e and (e.con is None or e.con.estado() == "listo") else None
        _avisar()
    _cerrar_con(viejo)
    _cerrar_con(viejo_esc)
    return {"ok": True, "via": "control", "confirmado": True}


def _donde_panel(reg):
    """Dónde está su panel en herdr, con los nombres que herdr muestra: {panel, tab, espacio_id, pestana, espacio,
    sesion} (lo que se pueda saber; sesion: la sesión de herdr con nombre, si su socket es el de una)."""
    import re
    import aviso_panel as AP
    sock = reg.get("socket", "")
    pane = (AP._herdr(["pane", "get", reg["panel"]], sock) or {}).get("pane") or {}
    tab = str(pane.get("tab_id") or reg.get("tab") or "")
    ws = str(pane.get("workspace_id") or reg.get("workspace") or "")
    if not ws:
        ws = next((x.split(":")[0] for x in (tab, reg["panel"]) if ":" in x), "")

    def nombre(tipo, i):
        r = (AP._herdr([tipo, "get", i], sock) or {}) if i else {}
        x = r.get(tipo) if isinstance(r.get(tipo), dict) else r
        return " ".join(str(x.get("label") or x.get("name") or x.get("title") or "").split())[:60]
    m = re.search(r"[\\/]sessions[\\/]([^\\/]+)[\\/][^\\/]+$", sock or "")
    return {"panel": reg["panel"], "tab": tab, "espacio_id": ws, "pestana": nombre("tab", tab),
            "espacio": nombre("workspace", ws), "sesion": m.group(1) if m else ""}


def _enfocar_panel(reg):
    """«Ir a la terminal» con su panel ya abierto: herdr no enfoca un panel por su id (`pane focus` solo va a un
    vecino, herdr 0.9.5), así que se enfoca su espacio y su pestaña (`workspace focus`, `tab focus`) en el herdr de
    ese panel. → {"estado": "enfocada" | "ya", "donde": _donde_panel}: si no se pudo, la página dice dónde está."""
    import aviso_panel as AP
    donde, sock = _donde_panel(reg), reg.get("socket", "")
    ok = bool(donde["tab"])
    if ok and donde["espacio_id"]:
        ok = AP._herdr(["workspace", "focus", donde["espacio_id"]], sock, json_out=False) is not None
    if ok:
        ok = AP._herdr(["tab", "focus", donde["tab"]], sock, json_out=False) is not None
    return {"estado": "enfocada" if ok else "ya", "donde": donde}


def ir_a_la_terminal(agente, enfocar=False, tab=NAV):
    """«Ir a la terminal»: si su panel está abierto, se enfoca en herdr (su espacio y su pestaña) y se dice dónde
    está; si no, se abre en herdr con el lanzador de siempre (`dispatch --open`); en Windows, en una ventana nueva de
    la terminal (localhost_web._abrir_ventana: `donde` = {"ventana"}). Nada se teclea. `enfocar` (B06,
    la confianza de Codex: la persona tiene que verlo para escribir /hooks): el panel recién abierto también se enfoca.
    `tab` (H4-a): la de esa pestaña (su sesión, con su motor)."""
    import aviso_panel
    LW = _LW()
    tab = _tab(tab)
    p = pestana(agente, crear=True) if tab == NAV else pestana(agente, tab=tab)
    if not p:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    brain, bt, wid = p
    reg = aviso_panel.panel_de("%s--%s" % (agente, wid))
    if _panel_vivo(reg):
        try:
            return dict({"ok": True}, **_enfocar_panel(reg))
        except Exception:
            return {"ok": True, "estado": "ya", "donde": {"panel": reg["panel"]}}
    nombre = str(bt.get("name") or "").strip()
    if LW._ventana_viva(agente, wid):                # Windows: su ventana sigue abierta (no se abre otra)
        return {"ok": True, "estado": "ya", "donde": {"ventana": nombre[:60]}}
    with _LOCK:
        s = _ses(agente, tab)
        if s and s.con is not None and s.con.estado() != "listo":
            return {"ok": False, "status": 409, "error": "localhost.err.trabajando", "datos": {}}
        viejo = s.soltar() if s else None       # su conversación pasa a la terminal
    _cerrar_con(viejo)
    if not LW._WID_RE.match(wid) or not nombre:
        return {"ok": False, "status": 409, "error": "localhost.err.abrir_sin_sesion"}
    motor = motor_de(agente, brain) if tab == NAV else (s.motor if s else (_PP().de(agente, tab) or {}).get("motor")
                                                        or motor_de(agente, brain))
    r = LW._lanzar(agente, wid, nombre, motor if motor != LW._motores_de_agentes().get(agente) else "", [])
    if r != "ok":
        return {"ok": False, "status": 409, "error": "localhost.err.abrir_" + str(r)}
    if LW._ventana_viva(agente, wid):                # Windows: en una ventana nueva de la terminal, al frente
        return {"ok": True, "estado": "abriendo", "donde": {"ventana": nombre[:60]}}
    nuevo = LW._LANZADOS.get((agente, wid))           # se abre sin foco (como en el hub): se dice dónde
    try:
        donde = _donde_panel({"panel": nuevo}) if nuevo else {}
    except Exception:
        donde = {}
    donde["pestana"] = donde.get("pestana") or nombre[:60]     # _lanzar le pone ese nombre
    if enfocar and nuevo:
        try:
            r = _enfocar_panel({"panel": nuevo})
            if r.get("estado") == "enfocada":
                return {"ok": True, "estado": "enfocada", "donde": dict(donde, **(r.get("donde") or {}))}
        except Exception:
            pass
    return {"ok": True, "estado": "abriendo", "donde": donde}


#: «Cerrar esa terminal»: cuánto se espera a que su terminal deje de contar como abierta (s).
CERRAR_TERMINAL_S = 5.0
CERRAR_TERMINAL_PASO_S = 0.25


def _panel_quieto(reg):
    """¿Su motor está quieto en su panel? Solo por `herdr pane get`, sin leer su pantalla: herdr lo reconoce como
    su motor y dice idle o done. Si herdr no lo reconoce (OpenClaw, Hermes), sin mirar no se sabe: no."""
    import aviso_panel as AP
    pane = (AP._herdr(["pane", "get", reg["panel"]], reg.get("socket", "")) or {}).get("pane") or {}
    suyo = AP.AGENTE_HERDR.get(reg.get("motor", ""))
    return bool(suyo) and pane.get("pane_id") == reg["panel"] and pane.get("agent") == suyo \
        and str(pane.get("agent_status") or "") in AP.QUIETO


def terminal_cerrable(agente, brain, wid):
    """¿La terminal abierta de la conversación de la página es un panel de herdr registrado aquí (que la página
    puede cerrar con «Cerrar esa terminal»)?"""
    try:
        import aviso_panel
        return _panel_vivo(aviso_panel.panel_de("%s--%s" % (agente, wid)))
    except Exception:
        return False


def cerrar_terminal(agente, tab=NAV):
    """«Cerrar esa terminal» (la tarjeta «Tu mensaje no salió» con su terminal abierta): cierra, sin escribirle nada, el panel
    de herdr registrado para la conversación de la página (`<agente>--<wid>`), solo si sigue siendo esa terminal, corre
    su motor y está quieto. Bajo el mismo candado que los avisos de sala a ese panel. Su conversación no se pierde: el
    próximo mensaje la retoma por la capa de control con su mismo número. `libre`: ya nada la tiene abierta."""
    import hashlib
    import aviso_panel as AP
    import olock
    p = pestana(agente) if _tab(tab) == NAV else pestana(agente, tab=tab)
    if not p:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    brain, _bt, wid = p
    reg = AP.panel_de("%s--%s" % (agente, wid))
    if not _panel_vivo(reg):
        if terminal_abierta(agente, brain, wid):     # abierta, pero no en un panel de herdr de esta computadora
            return {"ok": False, "status": 409, "error": "localhost.err.v2_terminal_sin_panel"}
        return {"ok": True, "estado": "ya", "libre": True}
    clave = hashlib.sha256(str(reg["panel"]).encode("utf-8")).hexdigest()
    try:
        with olock.file_lock(os.path.join(AP._estado(), "escritura-panel", clave), timeout=AP.PANEL_LOCK_S):
            if not _panel_vivo(reg):
                cerro = True
            elif not _panel_quieto(reg):
                return {"ok": False, "status": 409, "error": "localhost.err.v2_terminal_trabajando"}
            else:
                cerro = AP._herdr(["pane", "close", reg["panel"]], reg.get("socket", ""), json_out=False) is not None
    except olock.LockTimeout:
        return {"ok": False, "status": 409, "error": "localhost.err.v2_terminal_trabajando"}
    if not cerro:
        return {"ok": False, "status": 409, "error": "localhost.err.v2_terminal_no_cerro"}
    tope, libre = time.time() + CERRAR_TERMINAL_S, False
    while True:
        libre = not terminal_abierta(agente, brain, wid)
        if libre or time.time() >= tope:
            break
        time.sleep(CERRAR_TERMINAL_PASO_S)
    if not libre and _panel_vivo(reg):
        return {"ok": False, "status": 409, "error": "localhost.err.v2_terminal_no_cerro"}
    _avisar()
    return {"ok": True, "estado": "cerrada", "libre": libre}


# ── Amigable: la página para gente que no sabe de terminal (amigable.py) ──
#: Lo que Workspace arregla solo no se repite solo antes de esto (s).
ARREGLO_REPITE_S = 120
_AUTO = {}                 # (agente, motor, estado) → cuándo se arregló solo por última vez
#: Una terminal de la conversación de la página sin nada suyo desde hace esto (y quieta en herdr) es «vieja».
TERMINAL_VIEJA_S = 10 * 60
#: Cuánto se ve lo que Workspace hizo solo (con su «deshacer»).
AVISO_S = 60
#: Lo que la página puede pedir que se arregle (a pedido, con su botón).
ARREGLOS = ("iniciar_sesion", "actualizar", "instalar", "seguir_con", "deshacer", "confiar_hooks", "reintentar")


def _AM():
    import amigable
    if amigable.avisar is None:
        amigable.avisar = _avisar
        amigable.enfocar = lambda panel: _enfocar_panel({"panel": panel})
    return amigable


_ANSI = None
#: cable-openclaw: los motores cuyo «no abrió» puede ser pasajero (su gateway tarda en encender: hasta minutos en frío,
#: VERIFICADO 19-nov) y lo que lo dice. Un error así no deja la caja en «solo mirar»: el próximo mensaje reintenta.
PASAJERO_AL_ABRIR = {"openclaw": ("sin respuesta en", "timeout", "timed out", "econnrefused", "no terminó en",
                                  "no encendió en", "no pude conectar con el gateway", "waiting for gateway",
                                  "gateway closed", "se cerró la conexión con el gateway", "socket hang up")}


def _sin_ansi(texto):
    """El texto de un error sin los códigos de color de la terminal (el log del gateway de OpenClaw los trae)."""
    global _ANSI
    if _ANSI is None:
        import re
        _ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
    return _ANSI.sub("", str(texto or "")).strip()


def _al_abrir_pasajero(motor, texto):
    """¿El «no abrió» de `motor` es pasajero (se arregla solo volviendo a intentar)?"""
    t = str(texto or "").lower()
    return any(p in t for p in PASAJERO_AL_ABRIR.get(motor, ()))


def _estado_amigable(motor, texto, sondear=False):
    """Qué le pasa a `motor`, en simple (amigable.ESTADOS), por lo que dijo; si no se reconoce y `sondear`, por
    sus comandos oficiales (sin instalar, sin sesión, versión vieja). None si nada."""
    try:
        am = _AM()
        return am.de_texto(motor, texto) or (am.de_sondeo(motor) if sondear else None)
    except Exception:
        return None


def _confianza(brain, motor):
    """hooks5 · D6-a: con el paquete por sesión encendido, Codex no corre los hooks de Workspace en su terminal hasta
    que el socio los confía UNA vez en su /hooks. → lo que sabe amigable.confianza_codex (sin bloquear), o None: otro
    motor, el paquete apagado (no hay hooks que confiar), la página de solo leer o todavía no se sabe."""
    if motor != "codex" or SOLO_LEER or not brain:
        return None
    try:
        if not _paquete()["encendido"]:
            return None
        return _AM().confianza_codex(brain)
    except Exception:
        return None


def _ultima_actividad_terminal(eventos):
    """Hace cuántos segundos hubo algo de su terminal en el registro (lo de la página no cuenta), o None."""
    import datetime as _dt
    ult = None
    for e in eventos:
        if (e.get("datos") or {}).get("via") == "pagina":
            continue
        try:
            t = _dt.datetime.strptime(str(e.get("ts")), "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=_dt.timezone.utc).timestamp()
        except ValueError:
            continue
        ult = t if ult is None else max(ult, t)
    return None if ult is None else time.time() - ult


def terminal_vieja(agente, brain, wid):
    """¿La terminal abierta de la conversación de la página es un panel de herdr de aquí, quieto, y sin nada suyo
    en el registro desde hace TERMINAL_VIEJA_S (o nunca)?"""
    try:
        import aviso_panel
        from arquitectura import registro
        reg = aviso_panel.panel_de("%s--%s" % (agente, wid))
        if not _panel_vivo(reg) or not _panel_quieto(reg):
            return False
        hace = _ultima_actividad_terminal(registro.leer(brain, wid)[0])
    except Exception:
        return False
    return hace is None or hace >= TERMINAL_VIEJA_S


def _arreglar(agente, motor, que):
    """Empieza un arreglo de `motor` (iniciar_sesion/sin_sesion, actualizar, instalar). → el arreglo."""
    am = _AM()

    def sigue():
        _seguir_tras_arreglo(agente, motor, reabrir=que in ("actualizar", "instalar"))
    if que in ("sin_sesion", "iniciar_sesion"):
        return am.iniciar_sesion(agente, motor, al_listo=sigue)
    return am.instalar(agente, motor, al_listo=sigue, tipo="instalar" if que == "instalar" else "actualizar")


def _seguir_tras_arreglo(agente, motor, reabrir=False):
    """Su motor quedó arreglado: su tarjeta se va y tu mensaje sale solo (si la conversación sigue con ese motor).
    `reabrir`: tras actualizarlo o instalarlo, su conector se abre de nuevo (el programa nuevo)."""
    with _LOCK:
        s = _SES.get(agente)
        if s is None or s.motor != motor:
            return
        p, s.por_arreglar = s.por_arreglar, None
        if s.error and s.error.get("estado"):
            s.error = None
        cerrado = s.con is not None and s.con.estado() == "cerrado"
        libre = s.con is not None and s.con.estado() == "listo"
        viejo = s.soltar() if (cerrado or (reabrir and libre)) else None
        _avisar()
    _cerrar_con(viejo)
    if p:
        _reenviar(agente, p)


def _args_reenvio(agente, p):
    """Usa el id guardado, también cuando el pendiente lo trae con el nombre de la cola."""
    original = p.get("cid") or p.get("id")
    if p.get("ya"):
        intento = "a" + secrets.token_hex(6)
        return agente, p["texto"], intento, original or intento
    return agente, p["texto"], original or ""


def _reenviar(agente, p):
    threading.Thread(target=mandar, args=_args_reenvio(agente, p),
                     name="pagina-v2-sigue", daemon=True).start()


def arreglar(agente, accion):
    """Lo que pide la tarjeta de un motor con problemas, con su botón: iniciar sesión (su login oficial, con la
    guía), actualizarlo o instalarlo (su instalador oficial, en segundo plano), seguir con otro motor listo (tu
    mensaje sale ahí, con lo hablado), deshacer lo que Workspace hizo solo (volver a abrir su terminal) o, en Codex,
    abrirlo para que confíes en sus hooks (la guía de /hooks, y la página se da cuenta sola cuando quedó)."""
    if accion not in ARREGLOS:
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    with _LOCK:
        s = sesion(agente, crear=True)
        if s is None:
            return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
        motor, brain = s.motor, s.brain
    if accion == "reintentar":
        with _LOCK:
            error = s.error or {}
            p = s.por_arreglar
            if p is None and s.ultimo and error.get("cid"):
                if error["cid"] == (s.ultimo.get("cid") or s.ultimo.get("id")):
                    p = dict(s.ultimo, ya=True)
            if not p or not error:
                return {"ok": True, "repetido": True}
            s.error, s.por_arreglar = None, None
        r = mandar(*_args_reenvio(agente, p))
        if not r.get("ok"):
            with _LOCK:
                if s.motor == motor and not s.error:
                    s.error, s.por_arreglar = error, p
        _avisar()
        return r
    if accion == "confiar_hooks":
        if motor != "codex":
            return {"ok": False, "status": 409, "error": "localhost.err.v2_no_es_codex"}
        # B06: Codex al frente (enfocado), no en otro espacio del hub sin que se vea
        return {"ok": True, "arreglo": _AM().confiar_hooks(agente, motor, brain,
                                                           abrir=lambda: ir_a_la_terminal(agente, enfocar=True))}
    if accion == "deshacer":
        with _LOCK:
            av, s.aviso = s.aviso, None
            _avisar()
        if not av or av.get("tipo") != "terminal_vieja":
            return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_deshacer"}
        return ir_a_la_terminal(agente)
    if accion == "seguir_con":
        alt = _AM().alternativa(motor)
        if not alt:
            return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_alternativa"}
        with _LOCK:
            p, s.por_arreglar = s.por_arreglar, None
        r = cambiar_motor(agente, alt)
        if not r.get("ok"):
            with _LOCK:
                s.por_arreglar = s.por_arreglar or p
            return r
        _AM().olvidar(agente)
        with _LOCK:
            s.error = None
            _avisar()
        if p:
            _reenviar(agente, p)
        return {"ok": True, "motor": alt, "manda": bool(p)}
    if accion == "iniciar_sesion":
        with _LOCK:
            e = s.error
            if e and not e.get("estado") and e.get("tipo") in ("login", "llave"):
                # «Entrar a mi cuenta» desde la tarjeta de siempre (sesión o llave): desde aquí es la tarjeta en
                # simple, con su guía, y tu mensaje sale solo cuando quede (como si se hubiera reconocido al fallar)
                e["estado"] = "sin_sesion"
                if s.ultimo:
                    s.por_arreglar = dict(s.ultimo, ya=True)
                _avisar()
    return {"ok": True, "arreglo": _arreglar(agente, motor, accion)}


def uso(agente, canal=NAV):
    """El uso del plan por la vía oficial de su motor: lo que la capa de control informó
    (costo o % del plan) y, si no, nada."""
    s = _ses(agente, canal)
    u = _uso_de(s.con) if s else None
    return {"uso": u or {}, "fuente": "control" if u else ""}


def skill(agente, skill, texto=""):
    """Arranca una skill en la conversación de la página: su ejecución (pasos) y la
    instrucción de siempre, que sale por `mandar` (la capa de control), no tecleada."""
    import datetime as _dt
    import pasos
    LW = _LW()
    rel, nombre = LW._skill_de(agente, skill)
    if not rel:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    with _LOCK:
        s = sesion(agente, crear=True)
        if s is None:
            return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
        texto = " ".join(str(texto or "").split())[:600]
        ejecucion = "s-%s-%s" % (_dt.datetime.now().strftime("%Y%m%d%H%M%S"), secrets.token_hex(2))
        motor = s.motor
        pasos.guardar(ejecucion, {"id": ejecucion, "skill": nombre, "ruta": rel, "agente": agente, "pestana": NAV,
                                  "motor": motor, "texto": texto, "estado": "arrancando", "pasos": [],
                                  "pide": None, "creado": _dt.datetime.now().isoformat(timespec="seconds")}, s.brain)
    # «skill-», no «sk-»: con «sk-» el escáner de secretos tomaba el id por una llave de OpenAI (alarma al arrancar)
    r = s.mandar(LW._instruccion(ejecucion, nombre, rel, texto, motor=motor, con_nucleo=herramientas_de(s)),
                 "skill-" + ejecucion)
    if r.get("ok") is False:
        return r
    return {"ok": True, "id": ejecucion, "slug": NAV, "arrancada": not r.get("en_cola")}


#: Lo que se le hace a una ejecución desde la página o el hub (POST /api/v2/skill/accion).
ACCIONES_SKILL = ("detener", "seguir", "cerrar")


def skill_accion(agente, id, accion):
    """skills-cierre · «Detener» (la página y, ahora, el hub), y «Seguir» / «Cerrar» de una que se detuvo sola.
      detener: se pausa con motivo «detenida» (te esperara o corriera); si su motor trabaja en ella, se le pide parar.
      seguir:  la pausada vuelve a correr y su instrucción le dice al agente desde qué paso (sale por `mandar`).
      cerrar:  la pausada deja de verse (se queda pausada).
    → {ok, estado} o {ok: False, status, error}."""
    P = _pasos()
    if accion not in ACCIONES_SKILL:
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    brain = cerebro(agente)
    if not brain or not P.leer(id, brain):
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    if accion == "cerrar":
        d, _r = P.actualizar(id, P.cerrar, brain)
        _avisar()
        return {"ok": True, "estado": d.get("estado")}
    if accion == "detener":
        d, r = P.actualizar(id, lambda x: P.pausar(x, "detenida"), brain)
        s = _SES.get(agente)
        con = s.con if s is not None else None
        if r and con is not None and con.estado() in ("trabajando", "esperando_permiso"):
            try:
                con.parar()
            except Exception:
                pass
        _avisar()
        return {"ok": True, "estado": d.get("estado")}
    antes = P.leer(id, brain)
    pausa = dict(antes.get("pausa") or {})
    d, r = P.actualizar(id, P.seguir, brain)
    if not r:
        return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_skill"}
    LW = _LW()
    with _LOCK:
        s = sesion(agente, crear=True)
    motor = s.motor if s is not None else d.get("motor") or ""
    texto = LW._instruccion(id, d.get("skill") or "", d.get("ruta") or "", d.get("texto") or "", motor=motor,
                            seguir={"paso": pausa.get("paso") or 0, "pendiente": pausa.get("pendiente") or ""},
                            con_nucleo=herramientas_de(s))
    r = mandar(agente, texto, "skill-%s-s%s" % (id, secrets.token_hex(2)))
    if r.get("ok") is False:
        P.actualizar(id, lambda x: P.pausar(x, pausa.get("motivo") or "sin_fin"), brain)
        return r
    _avisar()
    return {"ok": True, "estado": "corriendo"}


def archivo(agente, id, nombre, datos):
    """El archivo que pidió una skill: se guarda junto a su ejecución y el aviso al agente
    sale por `mandar` (antes se tecleaba)."""
    import base64
    import pasos
    LW = _LW()
    brain = cerebro(agente)
    if not brain or not pasos.leer(id, brain):
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    nombre = LW._ARCH_RE.sub("_", os.path.basename(str(nombre or "")))[:80].strip(" .") or "archivo"
    try:
        crudo = base64.b64decode(datos or "", validate=True)
    except Exception:
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    if not crudo or len(crudo) > LW.MAX_ARCHIVO:
        return {"ok": False, "status": 413, "error": "localhost.err.largo"}
    carpeta = os.path.join(pasos.carpeta(brain), id, "archivos")
    os.makedirs(carpeta, exist_ok=True)
    destino, k = os.path.join(carpeta, nombre), 2
    raiz, ext = os.path.splitext(destino)
    while os.path.exists(destino):
        destino, k = "%s-%d%s" % (raiz, k, ext), k + 1
    with open(destino, "wb") as fh:
        fh.write(crudo)
    rel = os.path.relpath(destino, str(brain)).replace(os.sep, "/")
    r = mandar(agente, "El socio te dejó el archivo que pediste en %s (dentro de tu cerebro). Sigue con la "
                       "skill." % rel, "ar-" + secrets.token_hex(6))
    return {"ok": True, "ruta": rel, "avisado": r.get("ok") is not False}


# ── H4-a: abrir, cerrar y deshacer pestañas (las mismas en el hub y en la página) ──
#: Lo más que se trae de su programa al abrir una de sus sesiones como pestaña (sus últimos turnos).
IMPORTAR_TAB_MAX = 160


def _tab_publica(rec):
    """Lo que las vistas necesitan de una pestaña."""
    if not rec:
        return None
    return {"slug": rec.get("slug"), "nombre": str(rec.get("nombre") or rec.get("slug") or "")[:80],
            "motor": rec.get("motor") or "", "tipo": rec.get("tipo") or "sesion", "de": rec.get("de") or ""}


def _trabaja(s):
    """¿Trabaja ahora? (con el candado global). También lo que está entrando o saliendo hacia su motor: entre que tu
    mensaje entra y su motor pasa a «trabajando», la pestaña no se suelta ni la cierra el tope."""
    return s is not None and bool(s.turno_pendiente or s.ocupado or s.cola or getattr(s, "saliendo", None) or
                                  getattr(s, "entrando", 0) or (
        s.con is not None and s.con.estado() in ("trabajando", "esperando_permiso")))


def _ocupadas(agente):
    """Las pestañas que trabajan ahora: el tope nunca las cierra solas."""
    with _LOCK:
        return {rec["slug"] for rec in _PP().abiertas(agente) if _trabaja(_ses(agente, rec["slug"]))}


def _soltar_si_quieta(agente, slug):
    """Una pestaña que se cerró suelta su motor si está quieta (si trabaja, termina lo suyo y luego se va)."""
    with _LOCK:
        s = _SES.get(_clave(agente, slug))
        if s is None or _trabaja(s):
            return
        _SES.pop(_clave(agente, slug), None)
        con = s.soltar()
    _cerrar_con(con)


def _seguir_abierta(agente, tab, s):
    """Le escribiste a una pestaña que otra vista cerró: vuelve a abrirse (con lo que tenía)."""
    try:
        if _PP().de(agente, tab) is None:
            _PP().abrir(agente, {"slug": tab, "nombre": (s._bt() or {}).get("name") or tab, "wid": s.wid,
                                 "motor": s.motor}, ocupadas=_ocupadas(agente))
    except (OSError, ValueError):
        pass


def _importar_de_su_programa(brain, wid, slug, motor, sid):
    """Al abrir por primera vez una de sus sesiones como pestaña, su historial nace con lo que su programa ya tiene (su
    transcripción en esta máquina: Claude Code y Codex), marcado «importado», con su número. → hasta qué byte de su
    registro llega eso (lo que siga entra por su registro), 0 si no se trajo nada, o None si ya tenía historial."""
    import historial_eventos as HE
    from arquitectura import registro
    LW = _LW()
    ruta = _ruta_historial(brain, slug)
    if SOLO_LEER or os.path.exists(ruta):
        return None
    turnos = []
    try:
        tr = LW._transcripcion(motor, sid) if motor in LW._CONV_MOTORES and sid else None
        if tr:
            turnos = LW._sin_nota(LW._sin_arranques(LW._turnos_transcripcion(motor, tr)))[-IMPORTAR_TAB_MAX:]
    except Exception:
        turnos = []
    if not turnos:
        return 0
    fin = registro.leer(brain, wid)[1]
    # hasta dónde de su registro llega lo que se trajo (`registro_desde`): lo que siga entra por _ingerir
    evs = [LW._ev_sistema("motor", motor), LW._ev_sistema("importado", motor, n=len(turnos), registro_desde=fin)]
    for x in turnos:
        e = {"id": "i-" + secrets.token_hex(8), "rol": x["rol"], "texto": x.get("texto") or "", "motor": motor,
             "t": evs[0]["t"], "ts": x.get("ts") or "", "herr": x.get("herr") or [], "importado": True,
             "sesion_motor": sid}
        for k in ("contexto", "arranque"):
            if x.get(k):
                e[k] = True
        evs.append(e)
    with LW._HIST_LOCK:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        if not os.path.exists(ruta):
            HE.crear(ruta, evs)
    return fin


def _abrir_tab(agente, rec):
    """La abre (o la enfoca) en la lista compartida; la que se pasa del tope se cierra sola. → la respuesta."""
    try:
        t, cerrada = _PP().abrir(agente, rec, ocupadas=_ocupadas(agente))
    except (OSError, ValueError):
        return {"ok": False, "status": 409, "error": "localhost.err.pestana"}
    if cerrada:
        _soltar_si_quieta(agente, cerrada["slug"])
    _avisar()
    return {"ok": True, "tab": _tab_publica(t), "cerrada": _tab_publica(cerrada)}


def _tab_nueva(agente, brain, motor, nombre="", de="", eventos=None):
    """Una conversación nueva como pestaña: una sesión más del agente (su .md en el cerebro, con su número de Claude
    Code), que también sale en la lista de sus sesiones y se abre en su programa oficial. `eventos`: con lo que nace su
    historial (la conversación de la que salió, para su nota de contexto)."""
    import uuid
    import historial_eventos as HE
    import sessions_registry as reg
    LW = _LW()
    base = " ".join(str(nombre or "").split())[:60] or NOMBRE_NAV
    try:
        ya = {t.get("slug") for t in LW._pestanas_web(brain, reg.socio(brain))}
    except Exception:
        ya = set()
    cand, n = (base, 1) if nombre else ("%s 2" % base, 2)        # «Conversación 2» (⌂ es «Conversación»)
    while not _PP().valido(reg._slug(cand)) or reg._slug(cand) in ya:
        n += 1
        cand = "%s %d" % (base, n)
        if n > 500:
            return {"ok": False, "status": 409, "error": "localhost.err.pestana"}
    wid = str(uuid.uuid4())
    if not reg._seed_md(brain, cand, claude_wid=wid):
        return {"ok": False, "status": 409, "error": "localhost.err.pestana"}
    slug = reg._slug(cand)
    _olvidar_pestana(agente, slug)
    evs = list(eventos or []) or [LW._ev_sistema("motor", motor)]
    ruta = _ruta_historial(brain, slug)
    if not SOLO_LEER:
        with LW._HIST_LOCK:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            if not os.path.exists(ruta):
                HE.crear(ruta, evs)
    rec = {"slug": slug, "nombre": cand, "wid": wid, "motor": motor, "tipo": "nueva"}
    if de:
        rec["de"] = de
    return _abrir_tab(agente, rec)


def tab_abrir(agente, slug="", nueva=False, motor="", nombre=""):
    """H4-a · «+»: abre como pestaña una de sus sesiones (`slug`: las mismas que abres en su programa oficial, la lista
    de S-1) o, con `nueva`, una conversación nueva con `motor` (también queda en esa lista). Sin nada, la de siempre.
    → {ok, tab: {slug, nombre, motor, tipo}, cerrada: la que se cerró sola por el tope (se deshace) o None}."""
    brain = cerebro(agente)
    if not brain:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    if nueva:
        return _tab_nueva(agente, brain, motor or motor_de(agente, brain), nombre)
    if not slug or slug == NAV:
        return {"ok": True, "tab": {"slug": NAV, "nombre": NOMBRE_NAV, "motor": motor_de(agente, brain), "tipo": NAV},
                "cerrada": None}
    _olvidar_pestana(agente, slug)
    p = pestana(agente, tab=slug)
    if not p:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    brain, bt, wid = p
    try:
        import agent_brand
        import sessions_registry as reg
        if agent_brand.es_archivada(bt.get("estado")):
            reg.desarchivar(brain, agente, bt.get("name") or slug)     # abrirla la devuelve a su lista
            _olvidar_pestana(agente, slug)
    except Exception:
        pass
    rec = {"slug": slug, "nombre": bt.get("name") or slug, "wid": wid}
    previa = _PP().de(agente, slug)
    if previa is None:
        motor = _motor_de_sesion(brain, wid, agente, bt.get("name")) or motor_de(agente, brain)
        rec["motor"] = motor
        s0 = _Sesion(agente, brain, wid, motor, tab=slug)
        try:
            sid = (s0._numero_oficial(motor) or wid) if motor == "claude-code" else s0._numero_oficial(motor)
            _importar_de_su_programa(brain, wid, slug, motor, sid)
        except Exception:
            pass
    return _abrir_tab(agente, rec)


def tab_cerrar(agente, tab=NAV):
    """H4-a · cierra la pestaña (la de siempre no se cierra). Su sesión no se toca: sigue en su lista y en su
    programa. → {ok, cerrada} para el aviso con «deshacer»."""
    if _tab(tab) == NAV:
        return {"ok": False, "status": 409, "error": "localhost.err.v2_tab_fija"}
    try:
        rec = _PP().cerrar(agente, tab)
    except OSError:
        return {"ok": False, "status": 409, "error": "localhost.err.pestana"}
    if rec:
        _soltar_si_quieta(agente, tab)
        _avisar()
    return {"ok": True, "cerrada": _tab_publica(rec)}


def tab_deshacer(agente):
    """H4-a · vuelve a abrir la última que se cerró, en su lugar. → {ok, tab, cerrada}."""
    try:
        rec, cerrada = _PP().deshacer(agente, ocupadas=_ocupadas(agente))
    except OSError:
        return {"ok": False, "status": 409, "error": "localhost.err.pestana"}
    if cerrada:
        _soltar_si_quieta(agente, cerrada["slug"])
    _avisar()
    return {"ok": True, "tab": _tab_publica(rec), "cerrada": _tab_publica(cerrada)}


def tab_otro_motor(agente, tab, motor):
    """H4-a · una sesión de otra pestaña es de su motor (es la de su programa): cambiar el motor abre una pestaña nueva
    con lo hablado, que sigue con el motor nuevo y su nota de contexto (como «Siguió con …» en la de siempre)."""
    s = sesion(agente, tab=tab)
    p = pestana(agente, tab=tab)
    if s is None or not p:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    if motor == s.motor:
        return {"ok": True, "estado": "listo", "tab": _tab_publica(_PP().de(agente, tab))}
    if _trabaja(s):
        return {"ok": False, "status": 409, "error": "localhost.err.trabajando", "datos": {}}
    brain, bt, _wid = p
    from localhost_web import _ev_sistema
    evs = [dict(e, id="d-%s" % e.get("id")) for e in _en_orden(_leer_historial(brain, tab))
           if e.get("rol") in ("yo", "agente")]
    evs = [_ev_sistema("motor", s.motor)] + evs + [_ev_sistema("motor", motor)]
    r = _tab_nueva(agente, brain, motor, "%s · %s" % (bt.get("name") or tab, _nombre_motor(motor)), de=tab,
                   eventos=evs)
    if r.get("ok"):
        r["estado"], r["nueva"] = "listo", True
    return r


def pestanas():
    """La conversación de la página de cada agente (la forma de /api/pestanas, solo la del
    navegador): si existe, su motor y si está viva. Sin mirar paneles ni pantallas."""
    out = []
    for agente, _b in cerebros():
        p = pestana(agente)
        if not p:
            continue
        _brain, bt, _wid = p
        s = _SES.get(agente)
        out.append({"agente": agente, "slug": NAV, "nombre": str(bt.get("name") or "")[:80],
                    "motor": s.motor if s else motor_de(agente), "abierta": bool(s and s.con),
                    "actualizada": str(bt.get("actualizada") or "")[:40]})
    return {"pestanas": out}


#: Configuración → Permisos (decisión del dueño, 18-nov): lo que eliges por agente → su autonomía (agent.json, el
#: contrato común de engines/_ui). Dos opciones, las dos modos oficiales de su motor: «Automático» («brain», la de
#: fábrica, la que guarda cada agente al crearse) y «Preguntarme todo» («ask»).
NIVEL_A_AUTONOMIA = {"auto": "brain", "preguntar": "ask"}
#: Lo que se lee: también los niveles que se eligen en su terminal («edit», «sandbox»). La página muestra el más
#: cercano y no los reescribe hasta que eliges; «sandbox» (en su caja) es de solo lectura aquí.
_AUTONOMIA_A_NIVEL = {"ask": "preguntar", "edit": "editar", "sandbox": "sin_permisos"}


#: B19 (cacería 19-nov): los motores cuya identidad es el AGENTS.md puntero de la raíz del cerebro (su doc oficial lo lee
#: siempre). Lo escribe su lanzador al abrir la terminal: un agente usado solo desde la página no lo tenía y contestaba
#: «Soy Claude Haiku…» (OpenCode) o «soy Kiro, un asistente de IA».
IDENTIDAD_AGENTS_MD = ("opencode", "kiro", "openclaw")


def identidad_para(motor, brain):
    """B19: el AGENTS.md puntero de `motor` en el cerebro, como al abrir su terminal (engines/<motor>.inject_context, sin
    el bloque de la pestaña; uno propio del socio conserva su contenido). None si no aplica o falla (abre igual)."""
    if motor not in IDENTIDAD_AGENTS_MD:
        return None
    try:
        import importlib
        return importlib.import_module("engines." + motor).inject_context(definicion(brain), session_context="")
    except Exception:
        return None


def sandbox_codex(brain):
    """B05: el sandbox de Codex para la página, el MISMO que su terminal según el nivel del agente
    (engines/codex._interactive_sandbox: «preguntar» → read-only; si no, workspace-write; lo que fije el agent.json, con
    su candado: nunca danger-full-access). None si no se sabe (Codex usa lo suyo, como antes)."""
    try:
        from engines import codex as _cx
        s = _cx._interactive_sandbox(definicion(brain))
        return s if s in ("read-only", "workspace-write") else None
    except Exception:
        return None


def config_codex(brain):
    """cable-codex: el `config` del hilo de Codex en la página (engines/codex.config_del_hilo): sin una decisión del
    socio sobre la carpeta, «untrusted» solo en ese hilo, para que su app-server no guarde la confianza en su config
    global. None si el socio ya decidió (manda lo suyo). Ante un fallo, «untrusted» igual: nunca se escribe."""
    try:
        from engines import codex as _cx
        return _cx.config_del_hilo(brain)
    except Exception:
        return {"projects": {os.path.realpath(str(brain)): {"trust_level": "untrusted"}}}


def hilo_codex(brain):
    """{"sandbox"?, "config"?}: lo que lleva el hilo de Codex en la página. El sandbox del nivel del agente (B05) y la
    carpeta «untrusted» solo en el hilo (cable-codex); y, cierre de la auditoría (19-nov), lo prohibido de leer: por el
    app-server Codex no corre avisos, así que el nivel va como un perfil de permisos del hilo (arquitectura/secretos.
    codex_config: el mismo :workspace o :read-only, con `deny` para llaves y secretos). Con el perfil NO va `sandbox`:
    juntos, Codex usa los ajustes de antes (doc «Permissions»; caja negra 19-nov: activePermissionProfile null)."""
    out = {}
    sb = sandbox_codex(brain)
    cfg = dict(config_codex(brain) or {})
    perfil = None
    try:
        from arquitectura import secretos
        perfil = secretos.codex_config(sb)
    except Exception:
        perfil = None
    if perfil:
        cfg.update(perfil)
    elif sb:
        out["sandbox"] = sb
    if cfg:
        out["config"] = cfg
    return out


def hilo_codex_escritorio(brain):
    """Modo escritorio en Codex (decisión del dueño, 21-nov): el hilo del monito con la política «untrusted» (solo corre
    sin preguntar los comandos de lectura que Codex conoce; todo lo demás pide aprobación: su tarjeta), su sandbox de
    solo lectura con lo prohibido negado (el perfil de siempre sobre :read-only), y sin búsqueda en internet. Sin
    importar el nivel del agente. Sus herramientas MCP: control/codex (solo lo libre pasa sin tarjeta)."""
    cfg = dict(config_codex(brain) or {})
    try:
        from arquitectura import secretos
        cfg.update(secretos.codex_config("read-only") or {})
    except Exception:
        pass
    cfg["web_search"] = "disabled"
    out = {"aprobacion": "untrusted", "config": cfg}
    if "default_permissions" not in cfg:
        out["sandbox"] = "read-only"
    return out


#: Monito ronda 2 · E8: la herramienta de ayudantes de Claude Code (hoy «Agent»; «Task» hasta la 2.1.63).
SIN_AYUDANTES_CLAUDE = ("Agent", "Task")


def ajustes_claude_escritorio(brain):
    """Modo escritorio en Claude Code: solo lo negado de su sesión (lo protegido y la bóveda), sin las reglas que dejan
    pasar `workspace pasos`, la memoria por terminal ni el bus: en el monito todo eso pregunta."""
    a = ajustes_claude(brain)
    perm = dict((a or {}).get("permissions") or {})
    perm.pop("allow", None)
    # ronda 2 · E8: sin ayudantes en el monito. Su herramienta va negada en los permisos de ESTA corrida (config oficial
    # por sesión: `permissions.deny` del --settings; «Agent», y «Task», su nombre de antes). Nunca la config global.
    perm["deny"] = list(perm.get("deny") or []) + [t for t in SIN_AYUDANTES_CLAUDE if t not in (perm.get("deny") or [])]
    return {"permissions": perm}


def opciones_kiro(brain, canal=NAV):
    """{"meta_sesion"?}: el agente de la página de Kiro (cierre de la auditoría, 19-nov). Por ACP Kiro no corre los
    avisos de Workspace, y el de antes de cada herramienta es el que niega leer llaves y secretos: la página abre su
    sesión con el agente `workspace-pagina` de la carpeta (memoria_mcp.preparar_kiro_pagina: el de la terminal sin
    sus servidores, con reglas `fs_read` deny de lo prohibido), elegido con `_meta.kiro.modeId` en session/new (doc de
    ACP de Kiro, 3.5.0). {} si el paquete está apagado o el agente no se pudo dejar (abre como antes, sin él)."""
    try:
        from arquitectura import sesion as S
        if not S.activo():
            return {}
        import memoria_mcp
        from engines import _ui
        if _canal(canal) == ESC:
            # modo escritorio: su agente del monito, que pregunta antes de escribir (con cualquier nivel)
            hecho = memoria_mcp.preparar_kiro_pagina(brain, autonomia="ask", nombre=memoria_mcp.KIRO_AGENTE_ESCRITORIO)
            nombre = memoria_mcp.KIRO_AGENTE_ESCRITORIO
        else:
            hecho = memoria_mcp.preparar_kiro_pagina(brain, autonomia=_ui.autonomy(definicion(brain)))
            nombre = memoria_mcp.KIRO_AGENTE_PAGINA
        if hecho not in ("ready", "written", "restored"):
            return {}
        return {"meta_sesion": {"kiro": {"modeId": nombre}}}
    except Exception:
        return {}


def definicion(brain):
    """La definición del agente de ese cerebro (agent.json) con `_brain`, como la ven los lanzadores."""
    try:
        import agentsreg
        d = agentsreg.load_definition(str(brain)) or {}
    except Exception:
        d = {}
    return dict(d if isinstance(d, dict) else {}, _brain=str(brain))


def modo_claude(brain):
    """El --permission-mode de las corridas de la página: el MISMO que su terminal (engines/claude_code.
    modo_permisos: «Automático» → auto). None = no se pasa: manda el defaultMode del socio (M2)."""
    try:
        from engines import claude_code as _cc
        return _cc.modo_permisos(definicion(brain)) or None
    except Exception:
        return "manual"                          # lo de antes: pregunta


#: Lo que una vía de la página hace sin preguntar (control.VIAS[…]["sin_preguntar"]), en simple.
_HACE_SIN_PREGUNTAR = (("escribir", "escribe archivos"), ("comando", "corre comandos"))


def sin_preguntar_de(motor):
    """Lo que `motor` hace sin preguntar por la vía con la que la página le escribe (la capa de control:
    VIAS[motor_de_control(motor)]["sin_preguntar"]): () si pregunta antes de escribir y de correr algo."""
    try:
        return tuple((_control().VIAS.get(motor_de_control(motor)) or {}).get("sin_preguntar") or ())
    except Exception:
        return ()


def _nombre_motor(motor):
    try:
        import motores_logica
        return motores_logica.engine_name(motor)
    except Exception:
        return motor


def no_pregunta(motor):
    """B02 (cacería 19-nov): por qué «Preguntarme todo» NO se ofrece para `motor`, en una línea; "" si su vía oficial
    sí pregunta antes de escribir y de correr algo. Con «Preguntar», OpenClaw, Hermes y Cursor escribían y corrían
    comandos (incluso rm, y fuera de su carpeta) sin tarjeta: el nivel no llega a su vía ni la cambia."""
    sp = sin_preguntar_de(motor)
    if not sp:
        return ""
    hace = [t for k, t in _HACE_SIN_PREGUNTAR if k in sp] or ["hace cosas"]
    return "%s no puede preguntarte todo por su vía oficial: %s sin preguntarte, también fuera de su carpeta." % (
        _nombre_motor(motor), " y ".join(hace))


def que_en_su_carpeta(que, brain):
    """B01 (cacería 19-nov): lo que pide un permiso (control.base.que_permiso: clase, comando, ruta) con DÓNDE: `fuera`
    True si el archivo no está dentro de su cerebro (una ruta relativa es de su carpeta: ahí abre su motor) y la ruta
    para mostrar: la relativa a su carpeta, o la entera fuera de ella (con ~ por tu carpeta personal). La tarjeta decía
    «en tu carpeta» de un archivo en /tmp, con solo su nombre o sin nombre. None si no viene."""
    if not isinstance(que, dict) or not que.get("clase"):
        return None
    out = {"clase": str(que["clase"])[:20], "comando": str(que.get("comando") or "")[:500], "ruta": "", "fuera": None}
    ruta = str(que.get("ruta") or "").strip()
    if not ruta:
        return out
    try:
        p = os.path.expanduser(ruta)
        p = os.path.normpath(p if os.path.isabs(p) else os.path.join(str(brain), p))
        base, real = os.path.realpath(str(brain)), os.path.realpath(p)      # un enlace que sale, sale
        dentro = real == base or real.startswith(base.rstrip(os.sep) + os.sep)
        out["fuera"] = not dentro
        if dentro:
            out["ruta"] = os.path.relpath(real, base)
        else:                                                                # tal como lo pidió, con ~ por tu casa
            casa = os.path.expanduser("~").rstrip(os.sep)
            out["ruta"] = "~" + p[len(casa):] if p.startswith(casa + os.sep) else p
    except (OSError, ValueError):
        out["ruta"] = ruta
    out["ruta"] = out["ruta"][-300:]
    return out


def ajustes_claude(brain):
    """El `--settings` de las corridas de la página en Claude Code (control/claude_code: «los mismos que arma el
    lanzador»): los permisos de la sesión de su terminal (memoria.claude_permisos_sesion), con lo protegido del
    cerebro negado SIEMPRE: `workspace pasos`, `workspace memoria` y el bus sin preguntar, la config protegida y la
    bóveda negadas. Solo permisos: los hooks y la memoria automática de su terminal no cambian aquí. Hasta la
    cacería del 19-nov (B04) la página no pasaba ninguno. None si algo falla (la corrida va sin él, como antes)."""
    try:
        import memoria
        return {"permissions": memoria.claude_permisos_sesion(str(brain), protegidas=True)}
    except Exception:
        return None


def _tiene_auto(motor):
    """¿Su ficha dice cuál es su modo automático oficial? (permisos.niveles.auto, sin «no»)."""
    try:
        from arquitectura import contrato
        a = ((contrato.ficha(motor).get("permisos") or {}).get("niveles") or {}).get("auto") or {}
        return bool(a) and "no" not in a
    except Exception:
        return False


def permisos():
    """Configuración → Permisos, por agente: el nivel elegido («auto» si no dice nada: el de fábrica), su motor, si
    ese motor tiene modo automático, si pregunta todo por la vía de la página (`pregunta`; si no, `no_pregunta` dice
    por qué y «Preguntarme todo» no se ofrece: B02), y lo que el socio fijó a mano en su config y gana (M2: el
    defaultMode de Claude Code en el settings.local.json del cerebro, fuera de «Preguntar»)."""
    out = []
    try:
        from engines import claude_code as _cc
    except Exception:
        _cc = None
    for agente, brain in cerebros():
        v = str(definicion(brain).get("autonomy") or "").strip().lower()
        nivel = _AUTONOMIA_A_NIVEL.get(v, "auto")
        motor = motor_de(agente, brain)
        fijado = ""
        if motor == "claude-code" and nivel != "preguntar" and _cc is not None:
            suyo = _cc._modo_del_socio(brain)
            if suyo:
                fijado = ("Tu config fija el modo «%s» (defaultMode en .claude/settings.local.json de su cerebro): "
                          "en Claude Code gana sobre esto." % suyo)
        por_que = no_pregunta(motor)
        out.append({"agente": agente, "nivel": nivel, "motor": motor, "auto": _tiene_auto(motor),
                    "pregunta": not por_que, "no_pregunta": por_que, "fijado": fijado,
                    # Fable v2: ¿Workspace acota el turno de sus encargos a su nivel propio? (la tarjeta lo dice)
                    "motor_nombre": _nombre_motor(motor), "encargo_acotado": _E().acotable(motor)})
    return out


def autonomia(agente, nivel):
    """Configuración → Permisos: el nivel de un agente («auto» | «preguntar»). Lo guarda en su agent.json
    (agent_manage.set_autonomy: también los permisos de Claude Code del cerebro) y suelta su conector de la página,
    para que la próxima corrida ya vaya con el modo nuevo. En la terminal, desde su próxima sesión. Un agente en su
    caja (sandbox, elegido en su terminal) no se cambia desde aquí."""
    valor = NIVEL_A_AUTONOMIA.get(str(nivel or ""))
    if not valor:
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    brain = cerebro(agente)
    if not brain:
        return {"ok": False, "status": 404, "error": "localhost.err.pestana"}
    if str(definicion(brain).get("autonomy") or "").strip().lower() == "sandbox":
        return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_ajuste",
                "datos": {"motivo": "en su caja (sandbox del motor): se cambia en su terminal"}}
    if valor == "ask":
        por_que = no_pregunta(motor_de(agente, brain))
        if por_que:                             # B02: no se ofrece un nivel que su motor no cumple
            return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_ajuste",
                    "datos": {"motivo": por_que}}
    with _LOCK:
        # modo escritorio: el nivel es el de la página; el monito tiene su regla fija (pregunta todo lo que no es
        # libre), así que su conversación no se toca
        s = _SES.get(agente)
        if s and s.con is not None and s.con.estado() in ("trabajando", "esperando_permiso"):
            return {"ok": False, "status": 409, "error": "localhost.err.trabajando", "datos": {}}
    import agent_manage
    r = agent_manage.set_autonomy(agente, valor, expected_brain=brain)
    if not r.get("ok"):
        return {"ok": False, "status": 409, "error": "localhost.err.v2_sin_ajuste",
                "datos": {"motivo": str(r.get("error") or "")[:300]}}
    viejos = []
    with _LOCK:
        s = _SES.get(agente)
        if s and s.con is not None and s.con.estado() not in ("trabajando", "esperando_permiso"):
            viejos.append(s.soltar())
        _avisar()
    for viejo in viejos:
        _cerrar_con(viejo)
    return {"ok": True, "nivel": nivel, "texto": str(r.get("msg") or "")[:300]}


def info():
    """La versión de Workspace (Configuración → Actualizaciones), lo que cada motor hace sin preguntar por su vía de
    control, según la capa de control (Configuración → Permisos: así es el motor, no un fallo), y el nivel de
    permisos de cada agente (permisos()). Y `canales`: las conversaciones que entiende esta página (el monito de
    escritorio no habla con una que no tenga la suya: caería en la de la página)."""
    # por el id del motor (el de Configuración → Motores), con el aviso de la vía con la que la página le escribe:
    # antes iba por la llave de la vía («hermes-acp») y Hermes nunca salía en la lista (B02)
    sin_preguntar = {}
    try:
        from arquitectura import contrato
        vias = _control().VIAS
        for motor in sorted(contrato.fichas()):
            v = vias.get(motor_de_control(motor)) or {}
            if v.get("sin_preguntar") and v.get("aviso"):
                sin_preguntar[motor] = str(v["aviso"])[:300]
    except Exception:
        pass
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION"), encoding="utf-8") as fh:
            version = fh.read().strip()[:40]
    except OSError:
        version = ""
    try:
        niveles = permisos()
    except Exception:
        niveles = []
    return {"canales": list(CANALES), "version": version, "sin_preguntar": sin_preguntar, "paquete": _paquete(), "permisos": niveles}


#: El ajuste de la arquitectura nueva (settings.py): el paquete por sesión al abrir cada motor.
AJUSTE_PAQUETE = "arquitectura.paquete"


def _paquete():
    """{encendido, guardado, entorno}: lo que vale al abrir un motor (WORKSPACE_PAQUETE gana), lo guardado en
    el ajuste y si el entorno lo fija."""
    import settings
    entorno = str(os.environ.get("WORKSPACE_PAQUETE") or "").strip()
    guardado = settings.enabled(AJUSTE_PAQUETE, True)       # ON de fábrica: el sistema nuevo
    return {"encendido": entorno == "1" if entorno in ("0", "1") else guardado, "guardado": guardado,
            "entorno": entorno if entorno in ("0", "1") else ""}


def paquete(encendido):
    """Configuración → General: prende o apaga el ajuste (lo mismo que `settings.py set arquitectura.paquete`).
    Se aplica al abrir cada motor."""
    import settings
    try:
        settings.set(AJUSTE_PAQUETE, bool(encendido))
    except (ValueError, OSError):
        return {"ok": False, "status": 500, "error": "localhost.err.leer"}
    return dict({"ok": True}, **_paquete())


def apagar_todo():
    """Al apagar la página: cierra los motores que abrió y los servidores que encendió."""
    with _LOCK:
        # E9: lo que cada conversación tenía esperando tu permiso NO se contesta «no»: queda interrumpido
        sesiones = [(s, [p for p in [s.permiso] + list(s.en_espera or []) if p], s.soltar()) for s in _SES.values()]
        _SES.clear()
    for s, pendientes, con in sesiones:
        _cerrar_con(con, reinicio=True)
        try:
            # los que el motor tenía en fila detrás (uno por tarjeta) llegaron al conector mientras cerraba
            de_la_fila = [p for p in (con.interrumpidos() if con is not None else [])
                          if _permiso_en_simple(p) not in [_permiso_en_simple(x) for x in pendientes]]
            guardar_interrumpidos(s.brain, s.wid, pendientes + de_la_fila, motivo="reinicio")
        except Exception:
            pass
    cerrar_servidores()


def revisar_conexiones(motor=""):
    """Conexiones → «Revisar ahora» (de todos, o de `motor`): el chequeo rápido (arquitectura/chequeo), sin IA y en
    segundo plano, con el saludo de cada canal; su resultado lo lee GET /api/v2/chequeo. Una a la vez: si ya corre, la
    que corre trae lo mismo. Solo escribe en el estado de Workspace."""
    from arquitectura import chequeo, contrato
    if motor and motor not in contrato.MOTORES:
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    empezo = chequeo.en_fondo(motores=[motor] if motor else None, saludar=[motor] if motor else True,
                              arreglar=not SOLO_LEER)  # la que solo mira revisa, pero no arregla
    return {"ok": True, "revisando": True, "empezo": bool(empezo)}


def arreglar_conexion(arreglo):
    """Conexiones → «Arreglar» en una fila: solo lo de Workspace (arquitectura/arreglos: respaldo, arreglo, otra
    revisión). → {ok, texto, deshacer, sigue_mal}."""
    if SOLO_LEER:
        return {"ok": False, "status": 409, "error": "localhost.err.verificar",
                "datos": {"motivo": "Esta página solo mira: desde aquí no se arregla."}}
    from arquitectura import arreglos
    if not arreglos.conocido(arreglo):
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    return arreglos.arreglar(arreglo)


def deshacer_arreglo(id):
    """El «Deshacer» del aviso de un arreglo: deja lo que tocó como estaba."""
    if SOLO_LEER:
        return {"ok": False, "status": 409, "error": "localhost.err.verificar",
                "datos": {"motivo": "Esta página solo mira: desde aquí no se arregla."}}
    from arquitectura import arreglos
    return arreglos.deshacer(id)


def reportar_conexion(motor="", fila=""):
    """Conexiones → «Reportar»: el zip redactado con la evidencia de la fila, en ~/Workspace/Respaldos, mostrado en
    su carpeta y con su resumen de cinco líneas. Nada se envía (C4-a)."""
    from arquitectura import arreglos, contrato
    if motor and motor not in contrato.MOTORES:
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    return arreglos.reportar(motor, fila)


def verificar_ahora(motor=""):
    """Conexiones → «Verificar ahora» (de todos, o de `motor`): la auditoría con el motor real, en segundo plano y una a la vez
    (arquitectura/verificacion.lanzar); su avance lo lee GET /api/v2/conexiones. → lo de `lanzar` si empezó. Si no,
    el error con su porqué en el idioma de la página (un {"ok": false} sin llave de error saldría «No entendí el
    mensaje»): 409 si ya hay una en marcha, 500 si no pudo empezar."""
    if SOLO_LEER:
        return {"ok": False, "status": 409, "error": "localhost.err.verificar",
                "datos": {"motivo": "Esta página solo mira: desde aquí no se verifica."}}
    from arquitectura import contrato, verificacion
    if motor and motor not in contrato.MOTORES:       # uno de los nueve (o ninguno: todos)
        return {"ok": False, "status": 400, "error": "localhost.err.formato"}
    r = verificacion.lanzar([motor]) if motor else verificacion.lanzar()
    if r.get("ok"):
        return r
    if r.get("corriendo"):
        return dict(r, status=409, error="localhost.err.verificar_en_marcha")
    motivo = str(r.get("motivo") or "no pude empezar la verificación")
    return dict(r, status=500, error="localhost.err.verificar", datos={"motivo": motivo[:1].upper() + motivo[1:]})
