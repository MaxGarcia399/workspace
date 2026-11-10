#!/usr/bin/env python3
"""WORKSPACE · aviso_panel — el aviso a una pestaña que no escucha, en su panel de herdr.

Decisión del socio (opción A, 2026-11-08): 6 de 9 motores (codex, opencode,
kiro, copilot, hermes, openclaw) no esperan en segundo plano. Cuando les llega
un `pide` o un `responde` de una sala se quedan quietos hasta que alguien les
escribe. Workspace les escribe UNA línea en su panel, y Enter:

    Workspace: te llegó un pedido en la sala «<título>». Sigue tu skill
    colaborar-por-bus: <comando del bus> esperar --sala <id> --timeout 0

Reglas (todas a la vez):
  · solo a una pestaña que NO escucha (sin un `esperar` vivo: el mismo
    criterio que el aviso «X no está escuchando» de salas.py);
  · solo a una pestaña con su panel REGISTRADO en ESTA máquina:
    `<estado>/salas/paneles/<agente>--<WID>.json` (local, no viaja), escrito
    al lanzar la pestaña, en su session_start y en cada comando `conversar`,
    con las variables que herdr exporta a cada panel (HERDR_PANE_ID,
    HERDR_TAB_ID, HERDR_WORKSPACE_ID, HERDR_SOCKET_PATH). Nunca en otro panel;
  · antes de escribir se verifica, con el socket de ESE panel, que siga vivo,
    que sea la misma terminal que se registró y que corra el motor esperado:
    herdr lo reconoce ahí (`pane get` → `agent`) o su proceso está al frente
    (`pane process-info`; en Windows solo ve la shell). Nunca en una shell;
  · solo si `herdr pane get` dice `agent_status` idle o done y `focused`
    false. Con foco o trabajando no se escribe nada: el hub ofrece «Avisar»
    (a mano, misma verificación del panel);
  · una sola vez por mensaje y por participante, con un registro local
    (`<estado>/salas/avisos-panel.json`, no viaja). Queda a la vista: el hub
    muestra «◆ avisé a X» y `conversar ver` lo dice bajo el mensaje.
En otra máquina no se avisa nada: el hub de ESA máquina, si está abierto,
avisa a sus pestañas locales con la misma regla. Sin herdr, o si herdr
falla, no se hace nada y nada se rompe: una línea dice por qué. Sin daemon:
lo corre quien publica (en su propio comando) y el hub mientras está abierto.
Dentro del sandbox de Codex, herdr no responde (el socket queda fuera): el
`publicar` de un agente en Codex no avisa, y lo hace el hub de la máquina
(prueba en vivo, 2026-11-09). El registro del lanzador sí corre fuera.

Stdlib, Python 3.9+. Mac, Linux y Windows (ahí herdr es herdr.exe: se usa el
HERDR_BIN_PATH que exporta cada panel o el del PATH).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HERDR_ENV = ("HERDR_PANE_ID", "HERDR_TAB_ID", "HERDR_WORKSPACE_ID", "HERDR_SOCKET_PATH")
QUIETO = ("idle", "done")
TIMEOUT_S = 3.0
PAUSA_ENTER_S = 0.15        # entre el texto y el Enter: que el motor termine de recibirlo
AVISO_MAX_S = 24 * 3600     # un mensaje más viejo que esto ya no se avisa solo
AVISOS_MAX = 500
BARRIDO_S = 5.0             # el hub mira cada tanto (no en cada cuadro)
#: Los ejecutables de cada motor (lo que `process-info` debe mostrar en el
#: panel). Una prueba exige que coincidan con `META["needs"]` de engines/.
BINARIOS = {"claude-code": ("claude",), "codex": ("codex",), "opencode": ("opencode",),
            "kiro": ("kiro-cli", "kiro"), "copilot": ("copilot",), "hermes": ("hermes",),
            "openclaw": ("openclaw",), "cursor": ("cursor-agent",),
            "antigravity": ("agy", "antigravity"), "gemini": ("gemini",)}
_INTERPRETES = re.compile(r"^(python[0-9.]*|node|bun|deno)$")
#: El nombre con que herdr reconoce a cada motor en un panel (`pane get` →
#: `agent`). En Windows `process-info` solo ve la shell del panel (no hay
#: grupo de procesos al frente; prueba en la PC, 2026-11-09): ahí el motor se
#: comprueba por lo que herdr reconoció.
AGENTE_HERDR = {"claude-code": "claude", "codex": "codex", "opencode": "opencode",
                "kiro": "kiro", "copilot": "copilot", "cursor": "cursor",
                "antigravity": "agy", "gemini": "gemini"}
#: Lo que nunca se teclea en un panel: lo que una shell o la entrada de un
#: motor podría interpretar (el título lo escribió otro agente).
_RARO = re.compile(r"[`$\\\"'<>|;&(){}\[\]*?!#~%^]")


# ═══════════════════════════════════════════════════════════════════════════
# Registro de paneles (local, no viaja)
# ═══════════════════════════════════════════════════════════════════════════

def _estado():
    import paths
    return os.path.join(paths.state_dir(), "salas")


def _nombre(clave):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(clave or ""))[:120] or "pestana"


def ruta_panel(clave):
    return os.path.join(_estado(), "paneles", _nombre(clave) + ".json")


def _clave(agente, wid):
    return "%s--%s" % (agente, wid)


def _leer(ruta, defecto=None):
    """El JSON de `ruta` (con BOM también); `defecto` si no está o es ilegible."""
    import salas
    d, est = salas._leer_json_estado(ruta)
    return d if est == "ok" else defecto


def _escribir(ruta, datos):
    import atomico
    atomico.escribir(ruta, json.dumps(datos, ensure_ascii=False, indent=1) + "\n")


def registrar(agente, wid, motor="", env=None, fuente="arranque"):
    """Guarda el panel de herdr de la pestaña `<agente>--<wid>` (lo que exporta
    herdr en `env`). `fuente`: «lanzar» o «arranque» (el lanzador o el
    session_start: mandan) · «conversar» (un comando del bus: solo si aún no
    hay registro o el que hay también vino de un comando). True si quedó."""
    env = os.environ if env is None else env
    panel = str(env.get("HERDR_PANE_ID") or "").strip()
    agente, wid = str(agente or "").strip(), str(wid or "").strip()
    if not (panel and agente and wid):
        return False
    try:
        ruta = ruta_panel(_clave(agente, wid))
        previo = _leer(ruta, {}) or {}
        sock = str(env.get("HERDR_SOCKET_PATH") or "")
        motor = str(motor or env.get("WORKSPACE_SESSION_ENGINE") or "")
        if fuente == "conversar" and previo and previo.get("fuente") != "conversar":
            return previo.get("panel") == panel
        if (previo.get("panel") == panel and previo.get("socket") == sock
                and previo.get("motor") == motor and previo.get("terminal")
                and time.time() - float(previo.get("t") or 0) < 3600):
            return True                                     # igual y reciente: sin escribir
        terminal = ""
        g = _herdr(["pane", "get", panel], sock, env=env)
        if g:
            terminal = str((g.get("pane") or {}).get("terminal_id") or "")
        _escribir(ruta, {"version": 1, "agente": agente, "wid": wid, "panel": panel,
                         "tab": str(env.get("HERDR_TAB_ID") or ""),
                         "workspace": str(env.get("HERDR_WORKSPACE_ID") or ""),
                         "socket": sock, "terminal": terminal, "motor": motor,
                         "fuente": fuente, "t": time.time()})
        return True
    except Exception:
        return False


def registrar_entorno(agente=None, fuente="conversar"):
    """Registra la pestaña de ESTE proceso (WORKSPACE_AGENT_NAME/WID/ENGINE)."""
    return registrar(agente or os.environ.get("WORKSPACE_AGENT_NAME"),
                     os.environ.get("WORKSPACE_WID"), os.environ.get("WORKSPACE_SESSION_ENGINE"),
                     fuente=fuente)


def panel_de(clave):
    d = _leer(ruta_panel(clave))
    return d if isinstance(d, dict) and d.get("panel") else None


def paneles_de_agente(agente):
    """Los paneles registrados aquí de las pestañas de `agente`."""
    out = []
    d = os.path.join(_estado(), "paneles")
    try:
        nombres = sorted(os.listdir(d))
    except OSError:
        return out
    for n in nombres:
        if n.endswith(".json"):
            r = _leer(os.path.join(d, n))
            if isinstance(r, dict) and r.get("agente") == agente and r.get("panel"):
                out.append(r)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# herdr
# ═══════════════════════════════════════════════════════════════════════════

def _exe(env=None):
    """El binario de herdr, o None (sin herdr, o el aviso apagado con
    WORKSPACE_NO_AVISO_PANEL=1: así corre la suite)."""
    if os.environ.get("WORKSPACE_NO_AVISO_PANEL"):
        return None
    # el HERDR_BIN_PATH del panel que se registra, luego el de este proceso
    # (cada panel lo exporta; en Windows es herdr.exe), y solo al final el PATH
    for e in ((env,) if env is not None else ()) + (os.environ,):
        b = str(e.get("HERDR_BIN_PATH") or "")
        if b and os.path.isfile(b) and os.access(b, os.X_OK):
            return b
    return shutil.which("herdr")


def _herdr(args, socket="", env=None, json_out=True):
    """`herdr <args>` contra el server de ESE panel (su socket). → el `result`
    del JSON ({} si no trae), o None si herdr no está o falló."""
    exe = _exe(env)
    if not exe:
        return None
    e = dict(os.environ)
    e.pop("HERDR_SESSION", None)
    if socket:
        e["HERDR_SOCKET_PATH"] = socket
    try:
        import arbol_procesos             # en Windows, sin ventana de consola (corre de fondo)
        r = subprocess.run([exe] + list(args), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=TIMEOUT_S, env=e,
                           stdin=subprocess.DEVNULL, **arbol_procesos._sin_ventana())
    except Exception:
        return None
    if r.returncode != 0:
        return None
    if not json_out:
        return {}
    try:
        return (json.loads(r.stdout or "{}") or {}).get("result") or {}
    except ValueError:
        return {}


def _base(x):
    x = os.path.basename(str(x or "")).lower()
    return x[:-4] if x.endswith(".exe") else x


def motor_corre(info, motor):
    """¿Algún proceso al frente del panel es el motor `motor`? Por el nombre
    del ejecutable (argv0, argv[0], name); si es un intérprete (python, node,
    bun), por la ruta en su línea de comando (Hermes corre como python)."""
    nombres = set(BINARIOS.get(motor) or ((motor,) if motor else ()))
    if not nombres:
        return False
    for p in (info or {}).get("foreground_processes") or ():
        argv = p.get("argv") or [""]
        cand = {_base(p.get("argv0")), _base(argv[0] if argv else ""), _base(p.get("name"))}
        if cand & nombres:
            return True
        if any(_INTERPRETES.match(c or "") for c in cand):
            linea = str(p.get("cmdline") or " ".join(argv))
            for n in nombres:
                if re.search(r"(^|[\\/\s.])%s([-\\/\s.]|$)" % re.escape(n), linea):
                    return True
    return False


def estado_panel(reg):
    """{ok, motivo, quieto, foco, status} del panel registrado."""
    if not _exe():
        return {"ok": False, "motivo": "sin herdr en esta máquina"}
    g = _herdr(["pane", "get", reg["panel"]], reg.get("socket", ""))
    pane = (g or {}).get("pane") or {}
    if pane.get("pane_id") != reg["panel"]:
        return {"ok": False, "motivo": "su panel ya no está (o herdr no responde)"}
    if reg.get("terminal") and pane.get("terminal_id") != reg["terminal"]:
        return {"ok": False, "motivo": "su panel ya es otra terminal"}
    motor = reg.get("motor", "")
    reconocido = AGENTE_HERDR.get(motor) and pane.get("agent") == AGENTE_HERDR.get(motor)
    if not reconocido:
        pi = _herdr(["pane", "process-info", "--pane", reg["panel"]], reg.get("socket", ""))
        if not motor_corre((pi or {}).get("process_info"), motor):
            return {"ok": False, "motivo": "en su panel ya no corre %s" % (motor or "su motor")}
    st = str(pane.get("agent_status") or "")
    return {"ok": True, "motivo": "", "quieto": st in QUIETO, "foco": bool(pane.get("focused")),
            "status": st}


def escribir(reg, texto):
    """La línea y Enter en el panel registrado. True si herdr lo aceptó."""
    if _herdr(["pane", "send-text", reg["panel"], texto], reg.get("socket", ""),
              json_out=False) is None:
        return False
    time.sleep(PAUSA_ENTER_S)
    return _herdr(["pane", "send-keys", reg["panel"], "Enter"], reg.get("socket", ""),
                  json_out=False) is not None


# ═══════════════════════════════════════════════════════════════════════════
# El aviso
# ═══════════════════════════════════════════════════════════════════════════

def _titulo(t):
    import salas
    t = salas._CONTROL_RE.sub(" ", str(t or "")).replace("\n", " ").replace("\r", " ")
    t = " ".join(_RARO.sub("", t).split())
    return (t[:57] + "…") if len(t) > 60 else t


def linea(sala, nota):
    import salas
    que = {"responde": "una respuesta", "delegado": "un pedido que te pasaron"}.get(
        nota, "un pedido")
    return ("Workspace: te llegó %s en la sala «%s». Sigue tu skill colaborar-por-bus: "
            "%s esperar --sala %s --timeout 0" % (que, _titulo(sala.get("titulo")), salas._cmd(),
                                                    sala["id"]))


def ruta_avisos():
    return os.path.join(_estado(), "avisos-panel.json")


def avisos():
    d = _leer(ruta_avisos(), {}) or {}
    a = d.get("avisos") if isinstance(d, dict) else None
    return a if isinstance(a, dict) else {}


def _registro():
    """(avisos, reinicio) para quien ESCRIBE el registro (bajo su candado).
    Ilegible: se aparta (no se pisa) y se reinicia con la hora de ahora —
    lo de antes de `reinicio` no se vuelve a escribir en un panel solo (el
    botón «Avisar» del hub, sí)."""
    import salas
    d, est = salas._leer_json_estado(ruta_avisos())
    if est == "transitorio":             # no se pudo leer ahora: ni se pisa ni se teclea
        raise salas.EstadoTransitorio(ruta_avisos())
    if est == "ilegible":
        if not salas._apartar(ruta_avisos()):   # sin apartarlo, ni se pisa ni se teclea
            raise salas.SinApartar(ruta_avisos())
        return {}, time.time()
    if est == "no_existe" and salas._apartado_de(ruta_avisos()):
        return {}, time.time()           # se apartó y el nuevo no se guardó: recuperación
    d = d or {}
    a = d.get("avisos")
    try:
        reinicio = float(d.get("reinicio") or 0)
    except (TypeError, ValueError):
        reinicio = 0.0
    return (a if isinstance(a, dict) else {}), reinicio


def _guardar_registro(av, reinicio):
    datos = {"version": 1, "avisos": av}
    if reinicio:
        datos["reinicio"] = reinicio
    _escribir(ruta_avisos(), datos)


def _k(sala_id, mid, clave):
    return "%s:%s:%s" % (sala_id, mid, clave)


def avisos_de(sala_id):
    """{(mid, clave): registro} de los avisos y bloqueos de una sala (local)."""
    out = {}
    for k, v in avisos().items():
        if isinstance(v, dict) and v.get("sala") == sala_id:
            out[(v.get("msg"), v.get("para"))] = v
    return out


def _anotar(sala_id, mid, clave, estado, **extra):
    """Deja el resultado en el registro local (bajo su candado)."""
    def hacer():
        av, reinicio = _registro()
        k = _k(sala_id, mid, clave)
        previo = av.get(k) or {}
        if previo.get("estado") == "avisado" and estado != "avisado":
            return                       # un bloqueo posterior no borra el aviso
        av[k] = dict({"sala": sala_id, "msg": mid, "para": clave, "estado": estado,
                      "t": time.time()}, **extra)
        if len(av) > AVISOS_MAX:
            for kk, _v in sorted(av.items(), key=lambda kv: kv[1].get("t", 0))[:len(av) - AVISOS_MAX]:
                av.pop(kk, None)
        _guardar_registro(av, reinicio)
    _con_candado(hacer)


def _con_candado(fn):
    """fn() bajo el candado del registro de avisos (salas._bajo_candado). Sin
    candado no corre (ni se escribe en un panel ni se anota): el barrido lo
    reintenta. None si no corrió o si falló."""
    try:
        import salas
        _hecho, r = salas._bajo_candado(ruta_avisos(), fn)
        return r
    except Exception:
        return None


def _candidatos(sala, token):
    """Las claves de esta máquina a las que puede ir `token`: la suya, o, si es
    «?agente» (nadie de ese agente entró aún), la ÚNICA pestaña de ese agente
    con panel registrado aquí y vivo (con varias, ninguna: no se adivina)."""
    import salas
    if not str(token).startswith("?"):
        return [token]
    a = salas.agente_de(token)
    regs = [r for r in paneles_de_agente(a)
            if _clave(r["agente"], r["wid"]) not in sala["participantes"]]
    if len(regs) > 1:                    # los registros de pestañas cerradas no se limpian:
        regs = [r for r in regs if estado_panel(r).get("ok")]   # solo cuentan los vivos
    return [_clave(regs[0]["agente"], regs[0]["wid"])] if len(regs) == 1 else []


def avisar(sala, mid, token, nota="pide", manual=False, brains=None, quien=""):
    """Avisa (si toca) a la pestaña `token` por el mensaje `mid`. → (estado,
    texto): avisado · ya (ya se le avisó) · escucha · sin_panel (no es de esta
    máquina, o su panel no pasa la verificación) · foco · trabajando · falla.
    `manual` (el botón del hub): sin mirar foco ni si trabaja, y aunque ya se
    le haya avisado; la verificación del panel es la misma. Jamás levanta."""
    try:
        return _avisar(sala, mid, token, nota, manual, brains, quien)
    except Exception as e:
        return "falla", "no pude avisar: %s" % type(e).__name__


def _avisar(sala, mid, token, nota, manual, brains, quien):
    import salas
    cands = _candidatos(sala, token)
    if not cands:
        return "sin_panel", "no tiene panel registrado en esta máquina"
    clave = cands[0]
    nombre = salas.nombre_de(sala, clave)
    k = _k(sala["id"], mid, clave)
    if not manual and (avisos().get(k) or {}).get("estado") == "avisado":
        return "ya", "ya le avisé a %s en su panel" % nombre
    est = salas.estado_participante(sala, clave, brains=brains)
    if est.get("estado") == "escuchando":
        return "escucha", "%s está escuchando" % nombre
    reg = panel_de(clave)
    if reg is None:
        return "sin_panel", "%s no tiene panel registrado en esta máquina" % nombre
    ep = estado_panel(reg)
    if not ep["ok"]:
        return "sin_panel", "no le escribí a %s: %s" % (nombre, ep["motivo"])
    if not manual and ep["foco"]:
        _anotar(sala["id"], mid, clave, "foco", nota=nota)
        return "foco", "no le escribí a %s: su panel tiene el foco" % nombre
    if not manual and not ep["quieto"]:
        _anotar(sala["id"], mid, clave, "trabajando", nota=nota, status=ep.get("status"))
        return "trabajando", "no le escribí a %s: está trabajando (%s)" % (
            nombre, ep.get("status") or "?")
    res = {}

    def hacer():                         # bajo el candado: el que publica y el hub no avisan dos veces
        try:
            av, reinicio = _registro()
        except salas.EstadoTransitorio:  # no se pudo leer (ya reintentado): se dice, no se teclea
            res["r"] = ("falla", "no le escribí a %s: no puedo leer el registro de avisos (%s · "
                        "%s)" % (nombre, ruta_avisos(), salas._ERRORES_LECTURA.get(ruta_avisos())
                                 or "error de lectura"))
            return
        m = next((x for x in sala.get("mensajes") or () if x.get("id") == mid), None)
        if not manual and ((av.get(k) or {}).get("estado") == "avisado"
                           or (reinicio and m is not None and m.get("t", 0) <= reinicio)):
            if reinicio and k not in av:         # el registro se dañó: anotado, sin teclear
                av[k] = {"sala": sala["id"], "msg": mid, "para": clave, "estado": "avisado",
                         "t": time.time(), "nota": nota, "manual": False, "reinicio": True}
                _guardar_registro(av, reinicio)
            res["r"] = ("ya", "ya le avisé a %s en su panel" % nombre)
            return
        if not escribir(reg, linea(sala, nota)):
            res["r"] = ("falla", "no le escribí a %s: herdr no aceptó el texto" % nombre)
            return
        av[k] = {"sala": sala["id"], "msg": mid, "para": clave, "estado": "avisado",
                 "t": time.time(), "nota": nota, "manual": bool(manual), "panel": reg["panel"],
                 "quien": quien}
        _guardar_registro(av, reinicio)
        res["r"] = ("avisado", "◆ avisé a %s en su panel" % nombre)
    _con_candado(hacer)
    return res.get("r") or ("falla", "no pude avisar a %s" % nombre)


# ═══════════════════════════════════════════════════════════════════════════
# Qué despierta a quién (lo mira el que publica y el hub)
# ═══════════════════════════════════════════════════════════════════════════

def despertares(sala, ahora=None):
    """[(mid, token, nota)]: lo que despertaría a alguien en la sala y aún no le
    llega (según su cursor local). nota = pide · delegado · responde. Sin las
    salas cerradas o en pausa (en pausa se retiene) ni lo más viejo que
    AVISO_MAX_S."""
    import salas
    if sala["cerrada"] or sala["pausada"] or sala["borrada"]:
        return []
    ahora = time.time() if ahora is None else ahora
    out = []
    for m in sala["mensajes"]:
        if not m["entregable"] or ahora - m["t"] > AVISO_MAX_S:
            continue
        if m["tipo"] == "pide":
            p = sala["pedidos"].get(m["id"])
            if not p or p["estado"] != "esperando":
                continue
            for d in p["pendientes"]:
                if salas.es_socio(d):
                    continue
                if d.startswith("?") or not _entregado(sala, d, m["id"], p):
                    out.append((m["id"], d, "delegado" if d in p["delegados"] else "pide"))
        elif m["tipo"] == "responde":
            ped = sala["pedidos"].get(m.get("en_respuesta_a"))
            if ped and not salas.es_socio(ped["de"]) and not _entregado(sala, ped["de"], m["id"]):
                out.append((m["id"], ped["de"], "responde"))
    return out


def _entregado(sala, clave, mid, p=None):
    import salas
    ids = set(salas.cursor(clave)["ids"].get(sala["id"], ()))
    if mid in ids:
        return True
    dl = (p or {}).get("delegados", {}).get(clave)
    return bool(dl and dl.get("evento") in ids)


def tras_publicar(sala_id, mid, brains=None, quien=""):
    """Lo que corre `publicar` (y el socio desde el hub) tras escribir: avisa a
    las pestañas de esta máquina que ese mensaje despierta. → {token: (estado,
    texto)}."""
    import salas
    out = {}
    try:
        sala = salas.encontrar(sala_id, brains, salas.Almacen())
        if sala is None:
            return out
        for m_id, token, nota in despertares(sala):
            if m_id == mid:
                out[token] = avisar(sala, mid, token, nota, brains=brains, quien=quien)
    except Exception:
        pass
    return out


def barrer(brains=None, ahora=None):
    """Una pasada del hub: avisa a las pestañas locales a las que algo las
    despierta y nadie les ha avisado. → [(sala, mid, token, estado, texto)]."""
    import salas
    out = []
    if not _exe():
        return out
    try:
        ss = salas.todas(brains, salas.Almacen(), archivadas=False, recientes=True)
    except Exception:
        return out
    for s in ss:
        for mid, token, nota in despertares(s, ahora):
            if not _candidatos(s, token):
                continue
            est, txt = avisar(s, mid, token, nota, brains=brains, quien="hub")
            out.append((s["id"], mid, token, est, txt))
    return out


class Barrido(object):
    """El barrido del hub, en un hilo (no frena el dibujo): como mucho uno a la
    vez y uno cada BARRIDO_S. No es un daemon: vive mientras el hub está
    abierto."""

    def __init__(self, brains=None, cada=BARRIDO_S):
        self.brains, self.cada = brains, cada
        self._t, self._hilo, self.ultimo = 0.0, None, []

    def tal_vez(self, ahora=None):
        ahora = time.monotonic() if ahora is None else ahora
        if ahora - self._t < self.cada or (self._hilo is not None and self._hilo.is_alive()):
            return False
        if not _exe():
            return False
        self._t = ahora

        def correr():
            try:
                self.ultimo = barrer(self.brains)
            except Exception:
                self.ultimo = []
        self._hilo = threading.Thread(target=correr, name="workspace-aviso-panel")
        self._hilo.daemon = True
        self._hilo.start()
        return True


if __name__ == "__main__":
    # `python3 aviso_panel.py registrar` desde un panel: registra esa pestaña
    if sys.argv[1:2] == ["registrar"]:
        sys.exit(0 if registrar_entorno(fuente="lanzar") else 1)
    print(__doc__.split("\n\n")[0])
