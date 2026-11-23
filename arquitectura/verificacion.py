#!/usr/bin/env python3
"""WORKSPACE · arquitectura/verificacion — ¿el backend está cableado como lo planeamos? La última verificación REAL.

Conexiones (la página) y `workspace doctor` enseñan esto y nada más:

  · arriba, las piezas COMUNES (no son de un motor): el servidor local vivo y único dueño del estado, el registro de
    eventos escribiendo, el MCP núcleo respondiendo y el paquete por sesión encendido (`comunes`);
  · debajo, una matriz pieza × motor con las piezas del plan (Plan_Arquitectura_v1 §3 «Las que USAMOS» y el cableado
    del hub directo: la vía de control con su nombre real por motor —`claude -p --resume`, ACP, app-server, serve—,
    el paquete, los avisos, el MCP núcleo con sus herramientas, formularios e instrucciones, las skills, los permisos,
    el número oficial y el bloqueo de lo prohibido). Conexiones en verde (F1): la maleta, la misma conversación
    terminal ↔ página, la cola y el Vigía ya no salen (ninguna prueba los revisa: quedan en el informe); los «falta
    tu confianza» de Codex salen de tus carpetas (no de la de la prueba) y lo que la prueba no pudo correr por algo
    suyo (el perfil de prueba de Hermes, sin cuenta; OpenClaw sin terminar de arrancar) es «sin verificar», nunca ✗.
    Desde F5 esta matriz es la vista de laboratorio (modo desarrollador y el informe); lo que ve el socio es el
    chequeo rápido (arquitectura/chequeo).

Cada celda sale del plan (si en ese motor se usa o no, y por qué) y de la última auditoría con el motor real
(arquitectura/auditoria, que guarda aquí lo que vio por la terminal y por la página). Cinco estados:

  · ok            ✓ funciona: la auditoría lo vio, con su fecha;
  · falla         ✗ falló: el plan dice que se usa y la auditoría no lo vio (nunca ✓ sin evidencia), con qué hacer;
  · no_se_usa     neutro: no hay vía oficial, o el plan no lo pide en ese motor (el porqué en una línea);
  · confianza     falta tu confianza una vez (Codex: sus avisos, en /hooks), con la guía;
  · sin_verificar todavía no hay una verificación real que lo mire.

«Verificar ahora» (`lanzar`) corre la auditoría en segundo plano —un turno por motor y camino, con un cerebro
temporal— y deja su avance aquí (`estado`) para el estado amable de la página. El Vigía la corre igual cuando un motor
cambia de versión (`lanzar(["copilot"])`) y deja su última corrida en `ruta_vigia`. Solo escribe en el estado de
Workspace. Stdlib, falla-suave.
"""
import datetime as _dt
import io
import json
import os
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

from arquitectura import estado_json
from olock import LockTimeout, file_lock

#: Las piezas del plan en cada motor, en el orden de Conexiones (id, nombre en simple).
SISTEMAS = (
    ("via", "Vía de control desde la página"),
    ("paquete", "Paquete por sesión"),
    ("avisos", "Avisos del motor (hooks)"),
    ("mcp", "MCP núcleo: herramientas"),
    ("formularios", "MCP núcleo: formularios"),
    ("instrucciones", "MCP núcleo: instrucciones del servidor"),
    ("skills", "Skills en su menú"),
    ("permisos", "Permisos por sesión"),
    ("numero", "Número oficial de la conversación"),
    ("secretos", "Bloqueo de lo prohibido"),
)
#: Conexiones en verde (F1, C2-a): lo que ninguna prueba revisa no se enseña (nunca se iba a poner verde): la maleta
#: y la misma conversación terminal ↔ página quedan solo en el informe de la prueba a fondo (auditoria.md).
SIN_REVISION = ("maleta", "compartida")
IDS = tuple(s for s, _n in SISTEMAS)
#: skills-cierre (22-nov): el caso `skills` de la auditoría (arquitectura/auditoria.caso_skills), por la página: dos skills
#: en la misma conversación, con la evidencia de sus ejecuciones, las fotos y las tarjetas (no la palabra de la skill).
CASO_SKILLS = (("visible", "Skill visible"), ("botones", "Pregunta con botones"), ("cierra", "Cierra sola"),
               ("tarjetas", "Sin tarjetas"))
#: Las piezas comunes, arriba (id, nombre en simple).
COMUNES = (
    ("servidor", "Servidor local, vivo y único dueño del estado"),
    ("registro", "Registro de eventos escribiendo"),
    ("mcp", "MCP núcleo respondiendo"),
    ("paquete", "Paquete por sesión encendido"),
)
CAMINOS = ("terminal", "pagina")
#: La vía oficial con la que la página le habla a cada motor (cableado del hub directo), con su nombre real.
VIA = {"claude-code": "claude -p --resume", "codex": "app-server", "opencode": "serve", "copilot": "ACP",
       "cursor": "ACP", "kiro": "ACP", "antigravity": "ACP", "openclaw": "ACP", "hermes": "ACP"}
#: Lo que el plan pide solo en algunos motores (§3): formularios MCP, instrucciones del servidor y la misma conversación
#: en la terminal y la página (el servidor propio del motor, F4).
PLAN = {
    "formularios": ("claude-code", "codex", "copilot", "opencode", "hermes", "cursor"),
    "instrucciones": ("opencode", "codex", "copilot"),
    "compartida": ("opencode", "openclaw", "hermes"),
}
POR_QUE_NO = {
    "formularios": "El plan no lo pide aquí: {nombre} no ofrece formularios MCP; la pregunta llega por el chat.",
    "instrucciones": "El plan no lo pide aquí: el manual de Workspace va en sus instrucciones de siempre.",
    "compartida": "Así lo pide el plan: la página lleva su propia conversación con {nombre} y la terminal, la suya.",
}
#: Piezas que solo existen en un camino: la vía es de la página; permisos, número y maleta, de la terminal.
SOLO = {"via": ("pagina",), "permisos": ("terminal",), "numero": ("terminal",), "maleta": ("terminal",)}
OK, FALLA, NO_SE_USA, CONFIANZA, SIN_VERIFICAR = "ok", "falla", "no_se_usa", "confianza", "sin_verificar"
TEXTO = {OK: "funciona", FALLA: "falló", NO_SE_USA: "no se usa en este motor",
         CONFIANZA: "falta tu confianza una vez", SIN_VERIFICAR: "sin verificar todavía"}
QUE_HACER = {
    FALLA: "Toca «Verificar ahora» otra vez; si sigue en ✗, corre `workspace doctor --bundle` y mándalo a soporte.",
    CONFIANZA: "Abre {nombre} en la terminal de ese agente, escribe /hooks y confía en los de Workspace (una sola "
               "vez); la página también te guía.",
    SIN_VERIFICAR: "Toca «Verificar ahora» en Conexiones: prueba cada motor con un turno corto.",
}
#: cable-hermes: lo que se hace en un motor cuya confianza no es la de Codex (/hooks).
QUE_HACER_MOTOR = {
    ("hermes", CONFIANZA): "Abre ese agente una vez desde Workspace: aprueba los avisos de Workspace en su perfil "
                           "propio de {nombre} (si no pudo, {nombre} te los pide en su terminal).",
}
#: Lo que no tiene vía oficial (o todavía no se verifica así), dicho en simple: (motor, camino) → (estado, por qué).
SIN_VIA = {
    ("openclaw", "terminal"): (NO_SE_USA, "OpenClaw solo carga complementos desde su configuración general o la de su "
                                          "agente: en la terminal va con el agente propio de Workspace."),
    ("antigravity", "pagina"): (NO_SE_USA, "Con un plan personal, los términos de Antigravity no permiten usarlo dentro "
                                           "de otra app: por eso la página no le habla."),
}
_ESTADOS_PIEZA = {"ok": OK, "no": FALLA, "confianza": CONFIANZA, "no_se_usa": NO_SE_USA, "sin_dato": SIN_VERIFICAR}
#: F1: un camino que la prueba no pudo correr por algo SUYO (no del socio ni de Workspace) no es ✗: «no se pudo
#: probar». Hermes: la prueba usa su perfil propio, sin cuenta (Workspace no copia llaves); OpenClaw: el agente
#: temporal no terminó de arrancar cuando la prueba le habló.
NO_SE_PUDO = {
    "sin_cuenta": "No se pudo probar: la prueba usa su propio perfil, sin cuenta (Workspace no copia llaves). "
                  "Tus perfiles se revisan aparte.",
    "no_arranco": "No se pudo probar: el agente temporal de la prueba no terminó de arrancar.",
}
#: OpenClaw, cuando la prueba le habla antes de que su agente termine de arrancar (su respuesta, tal cual).
_SIN_ARRANCAR = "has not completed startup"


# ── dónde vive ─────────────────────────────────────────────────────────────
def _dir(state_dir=None):
    if not state_dir:
        import paths
        state_dir = paths.state_dir()
    return os.path.join(state_dir, "arquitectura")


def ruta(state_dir=None):
    return os.path.join(_dir(state_dir), "verificacion.json")


def ruta_progreso(state_dir=None):
    return os.path.join(_dir(state_dir), "verificacion-progreso.json")


def ruta_vigia(state_dir=None):
    """Donde el Vigía deja su última corrida: {"fecha", "resultado": ok|falla, "detalle"}."""
    return os.path.join(_dir(state_dir), "vigia.json")


def carpeta_salida(state_dir=None):
    """Donde «Verificar ahora» deja la tabla y la salida de cada motor (se reescribe en cada corrida)."""
    return os.path.join(_dir(state_dir), "verificacion-ultima")


def _leer(p, valido=None):
    try:
        return estado_json.leer(p, valido=valido)
    except OSError:
        return {}


def _es_dict_de_dicts(x):
    return isinstance(x, dict) and all(isinstance(v, dict) for v in x.values())


def _valido(d):
    """La forma de verificacion.json por dentro (revisor 5): motores → caminos → sistemas, cada nivel un objeto. Un
    `"motores": null` o una celda que no es objeto hacían fallar cada guardado (y la matriz) sin respaldo ni aviso."""
    motores = d.get("motores", {})
    if not _es_dict_de_dicts(motores):
        return False
    for f in motores.values():
        caminos = f.get("caminos", {})
        if not _es_dict_de_dicts(caminos):
            return False
        if not all(_es_dict_de_dicts(c.get("sistemas", {})) for c in caminos.values()):
            return False
    return True


def leer(state_dir=None):
    """{"fecha", "motores": {motor: {"fecha", "caminos": {camino: {"sistemas", "estado", "motivo"}}}}} o vacío."""
    d = _leer(ruta(state_dir), _valido)
    d.setdefault("motores", {})
    return d


def _hace(iso_o_epoch, ahora=None):
    """«hace 5 min» desde una fecha ISO o un epoch; '' si no se entiende."""
    try:
        t = float(iso_o_epoch) if isinstance(iso_o_epoch, (int, float)) else \
            time.mktime(_dt.datetime.fromisoformat(str(iso_o_epoch)).timetuple())
    except (TypeError, ValueError, OverflowError):
        return ""
    s = max(0, int((ahora or time.time()) - t))
    if s < 3600:
        return "hace %d min" % max(1, s // 60)
    if s < 2 * 86400:
        return "hace %d h" % (s // 3600)
    return "hace %d días" % (s // 86400)


# ── lo que guarda la auditoría ─────────────────────────────────────────────
def guardar(inf, state_dir=None):
    """Junta un informe de arquitectura.auditoria con lo guardado: cada motor que se auditó reemplaza al suyo (con su
    fecha); los demás quedan. Solo motores instalados. Nunca levanta: → True si escribió."""
    try:
        p = ruta(state_dir)
        with file_lock(p):
            d = estado_json.leer(p, apartar=True, valido=_valido)
            d.setdefault("motores", {})
            fecha = inf.get("fecha") or _dt.datetime.now().isoformat(timespec="seconds")
            for motor, f in (inf.get("motores") or {}).items():
                if not f.get("instalado"):
                    continue
                caminos = {}
                for camino, c in (f.get("caminos") or {}).items():
                    info = c.get("info") or {}
                    est = info.get("estado") or ""
                    if est == "corrido" and _SIN_ARRANCAR in str(info.get("salida") or ""):
                        est = "no_arranco"            # F1: una sola causa, no seis ✗
                    caminos[camino] = {"estado": est, "motivo": str(info.get("motivo") or "")[:400],
                                       "sistemas": c.get("sistemas") or {}}
                previo = (d["motores"].get(motor) or {}) if isinstance(d["motores"].get(motor), dict) else {}
                d["motores"][motor] = {"fecha": fecha, "caminos": caminos,
                                       "seguridad": (f.get("seguridad") or {}).get("estado") or ""}
                cs = f.get("caso_skills")
                if cs and cs.get("celdas"):
                    d["motores"][motor]["caso_skills"] = {"fecha": fecha, "celdas": {
                        k: {"estado": str((cs["celdas"].get(k) or {}).get("estado") or "sin_dato")[:16],
                            "detalle": str((cs["celdas"].get(k) or {}).get("detalle") or "")[:300]}
                        for k, _n in CASO_SKILLS}}
                elif previo.get("caso_skills"):           # una auditoría sin el caso no borra el último
                    d["motores"][motor]["caso_skills"] = previo["caso_skills"]
            d["fecha"] = fecha
            estado_json.escribir(p, d)
        return True
    except Exception:
        return False


# ── «Verificar ahora» ──────────────────────────────────────────────────────
_ENV_ESTADO = "WORKSPACE_VERIFICACION_ESTADO"


#: ¿Windows? Las pruebas lo cambian para ejercitar ese camino en la Mac.
_WINDOWS = os.name == "nt"
#: Lo más que dura una auditoría (9 motores × 2 caminos × su tope, con holgura). Una reserva SIN huella (la plataforma
#: no dio la hora de creación, o la anotó una versión anterior que solo guardaba el PID) cuenta como viva hasta aquí
#: cuando no hay comando que mirar (Windows): nunca para siempre por un PID reciclado (revisor 7).
_SIN_HUELLA_S = 3 * 3600


def _vive_sin_huella(d, pid):
    from openclaw_gateway import _command
    cmd = None if _WINDOWS else _command(pid)
    if cmd is not None:
        return " -m arquitectura.auditoria " in " " + cmd + " "
    try:
        return 0 <= time.time() - float(d.get("inicio") or 0) <= _SIN_HUELLA_S
    except (TypeError, ValueError):
        return False


def _corriendo(d):
    if d.get("fin"):
        return False
    pid = d.get("pid")
    if type(pid) is not int or pid <= 0:
        return False
    from openclaw_gateway import _identity
    vive, creado = _identity(pid)
    if vive is False:
        return False
    if vive and creado is not None and d.get("creado") is not None:
        return creado == d["creado"]
    return _vive_sin_huella(d, pid)


def _nuevo(pid):
    """La reserva de la auditoría `pid` con su huella (hora de creación). Si la plataforma no la da (revisor 7: en
    Windows puede responder «vivo, sin huella»), se reintenta un momento y, si sigue sin darla, la reserva queda sin
    huella (_vive_sin_huella) en vez de fallar y dejar al hijo ya lanzado sin reserva."""
    from openclaw_gateway import _identity
    for k in range(5):
        vive, creado = _identity(pid)
        if vive is False:
            raise ValueError("el proceso de verificación terminó al arrancar")
        if creado is not None:
            break
        if k < 4:
            time.sleep(0.05 * (k + 1))
    return {"pid": pid, "creado": creado, "inicio": time.time(), "hecho": 0,
            "total": 0, "actual": "", "fin": None}


def _candado_corrida(p):
    return file_lock(p + ".corrida", timeout=0)


@contextmanager
def corrida(state_dir=None, lanzada=False, publicar=True):
    """Reserva o reclama la corrida y la protege hasta que termine el guardado. Con `publicar=False`
    (`auditoria --no-guardar`) solo la exclusión: esa auditoría usa los mismos perfiles de prueba que las demás y,
    quizá, su carpeta de salida (revisor 4), pero no deja avance ni resultado para Conexiones."""
    p = ruta_progreso(state_dir)
    with ExitStack() as vida:
        with file_lock(p):
            vida.enter_context(_candado_corrida(p))
            d = estado_json.leer(p, apartar=True)
            pid = os.getpid()
            if lanzada:
                if d.get("pid") != pid or not _corriendo(d):
                    raise ValueError("no encontré la reserva de esta verificación")
            elif _corriendo(d):
                raise ValueError("ya hay una verificación en marcha")
            if not lanzada and publicar:
                _comprobar_guardado(state_dir)
                estado_json.escribir(p, _nuevo(pid))
        yield


def avanzar(state_dir=None, *, dueno=None, **datos):
    """Actualiza el avance sin reemplazar los campos del padre."""
    try:
        p = ruta_progreso(state_dir)
        with file_lock(p):
            d = estado_json.leer(p, apartar=True)
            if dueno is not None and d.get("pid") != dueno:
                return
            d.update(datos)
            estado_json.escribir(p, d)
    except (OSError, TypeError, ValueError):
        pass


def estado(state_dir=None):
    """{"corriendo": bool, "progreso": {pid, inicio, hecho, total, actual, fin} o None}."""
    d = _leer(ruta_progreso(state_dir))
    return {"corriendo": _corriendo(d), "progreso": d or None}


def _entorno():
    """El de este proceso sin la identidad de una pestaña (la auditoría pone la suya en cada corrida)."""
    try:
        from control import entorno
        return entorno.con_basicas(entorno.limpio())
    except Exception:
        return dict(os.environ)


def lanzar(motores=None, state_dir=None, popen=None):
    """Corre la auditoría con el motor real en segundo plano (python -m arquitectura.auditoria): guarda lo que vea y
    su avance aquí. → {"ok", "corriendo", "motivo"}. Una a la vez."""
    import paths
    state_dir = os.path.abspath(state_dir or paths.state_dir())
    p = ruta_progreso(state_dir)
    cmd = [sys.executable, "-m", "arquitectura.auditoria", "--salida", carpeta_salida(state_dir)]
    for m in motores or ():
        cmd += ["--motor", str(m)]
    try:
        with file_lock(p):
            try:
                with _candado_corrida(p):
                    d = estado_json.leer(p, apartar=True)
                    ocupada = _corriendo(d)
            except LockTimeout:
                ocupada = True
            if ocupada:
                return {"ok": False, "corriendo": True, "motivo": "ya hay una verificación en marcha"}
            _comprobar_guardado(state_dir)
            logs = os.path.join(state_dir, "logs")
            os.makedirs(logs, exist_ok=True)
            try:
                from control.canal import opciones_proceso
                extra = opciones_proceso()
            except Exception:
                extra = {}
            env = dict(_entorno(), **{_ENV_ESTADO: state_dir})
            with open(os.path.join(logs, "verificacion.log"), "a", encoding="utf-8") as log:
                proc = (popen or subprocess.Popen)(cmd, cwd=RAIZ_REPO, env=env, stdin=subprocess.DEVNULL,
                                                   stdout=log, stderr=subprocess.STDOUT, **extra)
            estado_json.escribir(p, _nuevo(proc.pid))
    except Exception as e:
        return {"ok": False, "corriendo": False, "motivo": "no pude empezar la verificación: %s" % e}
    return {"ok": True, "corriendo": True, "motivo": ""}


def _comprobar_guardado(state_dir):
    p = ruta(state_dir)
    with file_lock(p):
        estado_json.leer(p, apartar=True, valido=_valido)


# ── la matriz ──────────────────────────────────────────────────────────────
def _combinar(por_camino):
    """El estado de una celda desde sus caminos: ✗ si alguno falló; la confianza; ✓ si alguno funciona; neutro si en
    todos no se usa; si no, sin verificar."""
    estados = [c["estado"] for c in por_camino.values()]
    for e in (FALLA, CONFIANZA, OK):
        if e in estados:
            return e
    if estados and all(e == NO_SE_USA for e in estados):
        return NO_SE_USA
    return SIN_VERIFICAR


def _nombre_camino(camino):
    return "la terminal" if camino == "terminal" else "la página"


def no_se_usa(motor, sistema, nombre=""):
    """Por qué el PLAN no pide esta pieza en este motor ('' si la pide)."""
    if sistema in PLAN and motor not in PLAN[sistema]:
        return POR_QUE_NO[sistema].format(nombre=nombre or motor)
    return ""


def _celda(motor, nombre, sistema, guardado):
    base = {"via": VIA.get(motor, "")} if sistema == "via" else {}
    razon = no_se_usa(motor, sistema, nombre)
    if razon:
        return dict(base, estado=NO_SE_USA, texto=TEXTO[NO_SE_USA], por_que=razon, que_hacer="", fecha=None, caminos={})
    caminos = {}
    for camino in SOLO.get(sistema, CAMINOS):
        c = (guardado.get("caminos") or {}).get(camino)
        s = ((c or {}).get("sistemas") or {}).get(sistema)
        if (motor, camino) in SIN_VIA and (not c or not c.get("sistemas") or c.get("estado") == "omitido"
                                           or not s or s.get("estado") in ("no_se_usa", "sin_dato")):
            est, texto = SIN_VIA[(motor, camino)]
            caminos[camino] = {"estado": est, "detalle": texto}
            continue
        if not c:
            continue
        if c.get("estado") in NO_SE_PUDO:
            caminos[camino] = {"estado": SIN_VERIFICAR, "detalle": NO_SE_PUDO[c["estado"]]}
            continue
        if s:
            est_s = _ESTADOS_PIEZA.get(s.get("estado"), SIN_VERIFICAR)
            caminos[camino] = {"estado": est_s, "detalle": (_no_hace_falta(nombre, camino) if est_s == NO_SE_USA
                                                            else str(s.get("detalle") or ""))}
        elif c.get("motivo"):
            caminos[camino] = {"estado": SIN_VERIFICAR, "detalle": c["motivo"]}
    est = _combinar(caminos) if caminos else SIN_VERIFICAR
    # el porqué: el de los caminos con ese estado (todos si funciona o no se usa; el primero si falló o falta algo)
    iguales = [(k, v) for k, v in caminos.items() if v["estado"] == est and v["detalle"]]
    if est not in (OK, NO_SE_USA):
        iguales = iguales[:1]
    por_que = " · ".join("En %s: %s" % (_nombre_camino(k), v["detalle"]) for k, v in iguales)
    if not caminos:
        por_que = "Todavía no hay una verificación real de este motor."
    return dict(base, estado=est, texto=TEXTO[est], por_que=por_que[:500],
                que_hacer=(QUE_HACER_MOTOR.get((motor, est)) or QUE_HACER.get(est, "")).format(nombre=nombre),
                fecha=guardado.get("fecha") if est in (OK, FALLA, CONFIANZA) else None, caminos=caminos)


def caso_skills(guardado):
    """Las 4 celdas del caso `skills` de un motor, de su última auditoría con el caso: {fecha, celdas: {id: {estado,
    texto, detalle}}}, o None si nunca se corrió."""
    cs = (guardado or {}).get("caso_skills")
    if not isinstance(cs, dict) or not isinstance(cs.get("celdas"), dict):
        return None
    celdas = {}
    for k, _n in CASO_SKILLS:
        c = cs["celdas"].get(k) or {}
        est = _ESTADOS_PIEZA.get(c.get("estado"), SIN_VERIFICAR)
        celdas[k] = {"estado": est, "texto": TEXTO[est], "detalle": str(c.get("detalle") or "")}
    return {"fecha": cs.get("fecha"), "celdas": celdas}


def _no_hace_falta(nombre, camino):
    """F1: el porqué de «no se usa» en simple. Las notas de laboratorio (fechas de verificación, «caja negra», rutas
    del código, banderas) se quedan en el informe de la prueba a fondo, no en lo que lee el socio."""
    return "%s no lo necesita por %s." % (nombre, _nombre_camino(camino))


def _cuentas_hermes(fila):
    """cable-hermes: los perfiles de agente de Hermes sin cuenta (Workspace no copia ni guarda llaves): en la fila,
    `pendientes` con el comando oficial de cada uno, y lo mismo en qué hacer del paquete."""
    try:
        from engines import hermes as _h
        prueba = _h.perfil_de_agente("auditoria")       # F1: el perfil de la prueba nunca es un pendiente tuyo
        sin = [c for c in _h.perfiles_sin_cuenta() if c.get("perfil") != prueba]
    except Exception:
        sin = []
    if not sin:
        return
    import shlex
    fila["pendientes"] = [{"perfil": c["perfil"], "texto": "El perfil %s de Hermes todavía no tiene cuenta: conéctala "
                                                           "una vez con %s" % (c["perfil"], shlex.join(c["comando"])),
                           "comando": c["comando"]} for c in sin]
    celda = fila["celdas"].get("paquete") or {}
    celda["que_hacer"] = " ".join(x for x in (" · ".join(p["texto"] for p in fila["pendientes"]),
                                              celda.get("que_hacer") or "") if x)


#: F1: lo que depende de la confianza de los avisos de Codex (la terminal): con tus carpetas confiadas, funciona.
_CON_LOS_AVISOS = ("avisos", "numero", "secretos")


def cerebros_de(motor):
    """Los cerebros de los agentes que usan `motor` en esta máquina (agent_state), o []."""
    try:
        import agent_state
        return [a["brain"] for a in agent_state.snapshot().registered()
                if a.get("engine") == motor and a.get("brain") and os.path.isdir(a["brain"])]
    except Exception:
        return []


def _confianza_real_codex(fila):
    """F1: la prueba corre Codex en una carpeta nueva, y Codex nunca confía en una carpeta nueva: sus «falta tu
    confianza» eran de la prueba. Lo que vale es la confianza en las carpetas de TUS agentes (su `hooks/list`, como el
    doctor: salud._confianza_codex). Con todas confiadas, esas celdas funcionan; el permiso del MCP la primera vez es
    normal de Codex (su terminal te lo pregunta) y se explica, no es un pendiente."""
    try:
        from arquitectura import salud
        real = salud._confianza_codex(cerebros_de("codex"))
    except Exception:
        real = None
    if real != "listo":
        return
    for k, celda in (fila.get("celdas") or {}).items():
        if celda.get("estado") != CONFIANZA:
            continue
        if k in _CON_LOS_AVISOS:
            texto = "Confiados en las carpetas de tus agentes (lo dice el `hooks/list` de Codex)."
        elif k == "mcp":
            texto = ("Responde. La primera vez, Codex te pregunta antes de usar una herramienta de Workspace: "
                     "es normal de Codex.")
        else:
            continue
        celda.update(estado=OK, texto=TEXTO[OK], por_que=texto, que_hacer="",
                     caminos={c: (dict(v, estado=OK, detalle=texto) if v.get("estado") == CONFIANZA else v)
                              for c, v in (celda.get("caminos") or {}).items()})


# ── las piezas comunes ─────────────────────────────────────────────────────
def _pieza(id_, est, por_que, que_hacer="", fecha=None):
    nombre = dict(COMUNES).get(id_, id_)
    return {"id": id_, "nombre": nombre, "estado": est, "texto": TEXTO[est], "por_que": por_que,
            "que_hacer": que_hacer, "fecha": fecha}


def _servidor():
    """El servidor local: si este proceso ES el anotado (la página preguntando), vive; si no, se le pregunta."""
    try:
        import localhost_fondo as F
        d = F.leer()
        if d and str(d.get("pid")) == str(os.getpid()):
            return "vivo", d
        d, como = F.vivo()
        return como, d or {}
    except Exception as e:
        return "error", {"error": str(e)}


def _registro(ahora):
    """El renglón más nuevo del registro de eventos de esta máquina (epoch) y si la carpeta se puede escribir."""
    import paths
    raiz = os.path.join(paths.state_dir(), "arquitectura", "eventos")
    ultimo = 0.0
    for base, _ds, fs in os.walk(raiz):
        for f in fs:
            if f.endswith(".jsonl"):
                try:
                    ultimo = max(ultimo, os.path.getmtime(os.path.join(base, f)))
                except OSError:
                    pass
    try:
        os.makedirs(raiz, exist_ok=True)
        escribe = os.access(raiz, os.W_OK)
    except OSError:
        escribe = False
    return ultimo, escribe


def _mcp_responde():
    """El MCP núcleo en este proceso, como lo abre un motor: initialize + tools/list. → (n herramientas, error)."""
    try:
        from arquitectura import nucleo_mcp
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18",
                                                                              "capabilities": {}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
        entrada = io.BytesIO(b"".join(json.dumps(m).encode("utf-8") + b"\n" for m in msgs))
        salida = io.BytesIO()
        # sin pestaña (cadena vacía y sin entorno): sus instrucciones son el manual, sin tocar la memoria de nadie
        nucleo_mcp.Servidor(entrada, salida, env={}, cadena=[], diagnosticar=False).servir()
        respuestas = [json.loads(x) for x in salida.getvalue().splitlines() if x.strip()]
        tools = next((r["result"]["tools"] for r in respuestas if r.get("id") == 2 and "result" in r), [])
        return len(tools), ""
    except Exception as e:
        return 0, "%s: %s" % (type(e).__name__, e)


_PAQUETE_CACHE = {}


def _paquete_listo(ahora):
    """salud.paquete_listo, a lo más una vez por minuto (la página pregunta seguido mientras verifica)."""
    if _PAQUETE_CACHE and ahora - _PAQUETE_CACHE["t"] < 60:
        return _PAQUETE_CACHE["r"]
    from arquitectura import salud
    r = salud.paquete_listo()
    _PAQUETE_CACHE.update(t=ahora, r=r)
    return r


def comunes(ahora=None, servidor=None, state_dir=None):
    """Las piezas comunes, arriba de la matriz: [{id, nombre, estado, texto, por_que, que_hacer, fecha}]."""
    ahora = time.time() if ahora is None else ahora
    out = []
    como, d = (servidor or _servidor)()
    if como == "vivo":
        out.append(_pieza("servidor", OK, "Prendido en 127.0.0.1:%s y es el único: la página y el hub le hablan a él."
                          % d.get("puerto", "?"), fecha=_dt.datetime.now().isoformat(timespec="seconds")))
    elif como == "sin":
        out.append(_pieza("servidor", NO_SE_USA, "Apagado ahora: se prende solo al abrir la página o el hub."))
    elif como == "viejo":
        out.append(_pieza("servidor", FALLA, "Hay uno prendido con otra versión de Workspace.",
                          "Cierra la página y ábrela otra vez: Workspace prende el de esta versión."))
    else:
        out.append(_pieza("servidor", FALLA, "Quedó anotado pero no responde.",
                          "Abre la página otra vez: Workspace lo reemplaza solo."))
    ultimo, escribe = _registro(ahora)
    if not escribe:
        out.append(_pieza("registro", FALLA, "No se puede escribir en la carpeta del registro de esta máquina.",
                          "Corre `workspace doctor` para ver qué pasa con los permisos de esa carpeta."))
    elif ultimo:
        out.append(_pieza("registro", OK, "Último renglón %s." % _hace(ultimo, ahora),
                          fecha=_dt.datetime.fromtimestamp(ultimo).isoformat(timespec="seconds")))
    else:
        out.append(_pieza("registro", SIN_VERIFICAR, "Todavía no hay ningún renglón en esta máquina.",
                          QUE_HACER[SIN_VERIFICAR]))
    n, err = _mcp_responde()
    if n:
        ultima = ""
        try:
            from arquitectura import salud
            llamadas = [x for x in salud.leer_diagnostico() if x.get("evento") == "llamada"
                        and x.get("resultado") == "ok"]
            if llamadas:
                ultima = " Última llamada real de un motor: %s (%s)." % (
                    _hace(llamadas[-1].get("t"), ahora), llamadas[-1].get("motor") or llamadas[-1].get("cliente") or "?")
        except Exception:
            pass
        out.append(_pieza("mcp", OK, "Responde con sus %d herramientas.%s" % (n, ultima),
                          fecha=_dt.datetime.now().isoformat(timespec="seconds")))
    else:
        out.append(_pieza("mcp", FALLA, "No respondió: %s" % (err or "sin herramientas"),
                          "Corre `workspace doctor --bundle` y mándalo a soporte."))
    try:
        from arquitectura import sesion
        encendido = sesion.activo()
    except Exception:
        encendido = False
    if not encendido:
        out.append(_pieza("paquete", NO_SE_USA, "Lo apagaste: tus motores abren como antes.",
                          "Para volver al sistema nuevo: workspace sistema-nuevo on"))
    else:
        listo, por_que = _paquete_listo(ahora)
        out.append(_pieza("paquete", OK, "Encendido, y se arma en esta máquina con su lanzador y su MCP.",
                          fecha=_dt.datetime.now().isoformat(timespec="seconds")) if listo else
                   _pieza("paquete", FALLA, "Encendido, pero no se arma: %s" % por_que,
                          "Corre `workspace doctor --bundle` y mándalo a soporte."))
    # F1 (C2-a): la cola de mensajes y el Vigía ya no salen aquí: nadie los revisaba (eran notas nuestras). El canario
    # de nuestras máquinas (arquitectura/canario) los reemplaza.
    return out


def matriz(which=None, state_dir=None, servidor=None):
    """Lo que enseña Conexiones: {"fecha", "corriendo", "progreso", "comunes": [...], "sistemas": [{id, nombre}],
    "motores": [{motor, nombre, instalado, fecha, celdas: {sistema: {estado, texto, por_que, que_hacer, fecha,
    caminos[, via]}}}]}. Los instalados primero."""
    import shutil
    from arquitectura import contrato
    which = which or shutil.which
    d = leer(state_dir)
    filas = []
    for motor in contrato.MOTORES:
        try:
            ficha = contrato.ficha(motor)
        except Exception:
            continue
        nombre = ficha.get("nombre") or motor
        guardado = (d.get("motores") or {}).get(motor) or {}
        instalado = bool(which(ficha.get("binario") or motor))
        filas.append({"motor": motor, "nombre": nombre, "instalado": instalado, "fecha": guardado.get("fecha"),
                      "celdas": {s: _celda(motor, nombre, s, guardado) for s in IDS},
                      "caso_skills": caso_skills(guardado)})
        if motor == "openclaw" and instalado:
            from engines import openclaw as oc
            if oc.validar_perfil() is False:
                filas[-1]["celdas"]["via"].update(
                    estado=FALLA, texto=TEXTO[FALLA], fecha=None,
                    por_que="perfil de OpenClaw inválido",
                    que_hacer="Ejecuta workspace doctor --fix para reparar las piezas de Workspace.")
        if motor == "hermes" and instalado:
            _cuentas_hermes(filas[-1])
        if motor == "codex" and instalado:
            _confianza_real_codex(filas[-1])
    filas.sort(key=lambda f: not f["instalado"])
    e = estado(state_dir)
    try:
        piezas = comunes(servidor=servidor, state_dir=state_dir)
    except Exception:
        piezas = []
    return {"fecha": d.get("fecha"), "corriendo": e["corriendo"], "progreso": e["progreso"], "comunes": piezas,
            "sistemas": [{"id": s, "nombre": n} for s, n in SISTEMAS], "motores": filas,
            "caso_skills": [{"id": k, "nombre": n} for k, n in CASO_SKILLS]}
