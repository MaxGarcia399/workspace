#!/usr/bin/env python3
"""WORKSPACE · arquitectura/salud — lo cableado por motor según su ficha, las marcas de uso y el diagnóstico del MCP.

Lo que enseñan el doctor y Conexiones es la verificación REAL (arquitectura/verificacion, desde la auditoría con el
motor real): nada cuenta como conectado por tener el archivo puesto. Aquí queda lo que la alimenta: el diagnóstico del
MCP núcleo (`diagnostico`: qué cliente lo abrió y cómo salió cada llamada), si el paquete se arma (`paquete_listo`), la
confianza de Codex en los cerebros de verdad (`_confianza_codex`) y lo que la ficha declara (`cableado`, `revisar`).

Por cada motor instalado, tres piezas: el MCP núcleo, los hooks y las skills. Cada una en uno de cuatro estados:

  · «ok»         ✓ se conecta solo al abrir el motor (por su vía oficial por sesión, o la de antes donde la ficha lo dice);
  · «confianza»  falta tu confianza UNA vez (Codex: sus hooks del proyecto, en su /hooks);
  · «sin_via»    ✗ el motor no tiene una vía por sesión para eso (lo dice su ficha, tal cual);
  · «falta»      ✗ debería conectarse y algo lo impide (el paquete no se arma, el lanzador no está).

Lo que dice sale de la ficha de cada motor (lo cableado) y de lo que de verdad pasó en esta máquina: el hook del
paquete y el MCP núcleo dejan aquí su último uso por motor y por vía (`marcar`: terminal o página), así el doctor dice
«visto hace 2 h» o «todavía sin usar». Solo lee la config de los motores para lo que ya hace la página (la confianza
de Codex por su `hooks/list`); nunca la escribe. Stdlib, falla-suave.
"""
import json
import os
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

import atomico
from arquitectura import estado_json
from olock import file_lock

OK, CONFIANZA, SIN_VIA, FALTA = "ok", "confianza", "sin_via", "falta"
PIEZAS = ("mcp", "hooks", "skills")
#: Una marca de uso más nueva que esto no se vuelve a escribir (los hooks corren en cada herramienta).
_CADA_S = 60


def _ruta(state_dir=None):
    if not state_dir:
        import paths
        state_dir = paths.state_dir()
    return os.path.join(state_dir, "arquitectura", "salud.json")


def _valido(d):
    """La forma de salud.json por dentro (revisor 5): {motor: {pieza: {vía: epoch}}}. Una casilla null o un epoch que
    no es número hacían fallar cada marca sin respaldo ni aviso."""
    return all(isinstance(piezas, dict) and all(
        isinstance(vias, dict) and all(isinstance(t, (int, float)) and not isinstance(t, bool) for t in vias.values())
        for vias in piezas.values()) for piezas in d.values())


def usos(state_dir=None):
    """{motor: {"mcp"|"hooks": {"terminal"|"pagina": epoch}}} de esta máquina, o {}."""
    try:
        return estado_json.leer(_ruta(state_dir), valido=_valido)
    except OSError:
        return {}


#: Las carpetas temporales de la prueba a fondo (arquitectura/auditoria: sus cerebros y su salida).
_DE_PRUEBA = "workspace-auditoria-"


def de_prueba(cerebro):
    """¿`cerebro` es un cerebro temporal de la prueba a fondo? Su uso no es uso real (Conexiones en verde, F2)."""
    partes = os.path.normpath(str(cerebro or "")).replace("\\", "/").split("/")
    return any(p.startswith(_DE_PRUEBA) for p in partes)


def marcar(motor, pieza, via="terminal", ahora=None, state_dir=None, cerebro=None):
    """El último uso de `pieza` («mcp» o «hooks») en `motor` por `via`. Nunca levanta; a lo más una escritura por
    minuto y por casilla. Las corridas de la prueba a fondo (su cerebro temporal: `cerebro` o WORKSPACE_BRAIN) no
    cuentan: «visto hace 2 h» es solo uso real."""
    try:
        motor, via = str(motor or "").strip()[:40], ("pagina" if via in ("pagina", "escritorio") else "terminal")
        if not motor or pieza not in ("mcp", "hooks"):
            return False
        if de_prueba(cerebro if cerebro is not None else os.environ.get("WORKSPACE_BRAIN")):
            return False
        ahora = time.time() if ahora is None else ahora
        ruta = _ruta(state_dir)
        with file_lock(ruta):
            d = estado_json.leer(ruta, apartar=True, valido=_valido)
            casilla = d.setdefault(motor, {}).setdefault(pieza, {})
            if ahora - float(casilla.get(via) or 0) < _CADA_S:
                return False
            casilla[via] = round(ahora, 1)
            estado_json.escribir(ruta, d)
        return True
    except Exception:
        return False


#: El diagnóstico del MCP núcleo: un renglón por arranque (initialize) y por llamada, sin contenido.
_DIAG = "mcp-diagnostico.jsonl"
_DIAG_MAX = 256 * 1024


def _ruta_diag(state_dir=None):
    return os.path.join(os.path.dirname(_ruta(state_dir)), _DIAG)


def diagnostico(evento, state_dir=None, **datos):
    """Un renglón del MCP núcleo para la verificación: `initialize` (qué cliente lo abrió, su versión, si ofrece
    formularios) o `llamada` (qué herramienta y el resultado: ok o el código del error). Nunca el contenido de una
    llamada. Con tope de tamaño (se queda la mitad nueva). Nunca levanta."""
    try:
        ruta = _ruta_diag(state_dir)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        fila = dict({k: v for k, v in datos.items() if isinstance(v, (str, int, float, bool))},
                    t=round(time.time(), 2), evento=str(evento), pid=os.getpid())
        linea = json.dumps(fila, ensure_ascii=False) + "\n"
        with file_lock(ruta):
            if os.path.isfile(ruta) and os.path.getsize(ruta) > _DIAG_MAX:
                with open(ruta, encoding="utf-8-sig", errors="replace") as fh:
                    resto = fh.readlines()[-200:]
                atomico.escribir(ruta, "".join(resto) + linea, avisar=True)
            else:
                atomico.anexar(ruta, linea)
        return True
    except Exception:
        return False


def leer_diagnostico(desde=0.0, hasta=None, state_dir=None):
    """Los renglones del diagnóstico entre `desde` y `hasta` (epoch), viejos primero."""
    out = []
    try:
        with open(_ruta_diag(state_dir), encoding="utf-8-sig", errors="replace") as fh:
            for linea in fh:
                try:
                    x = json.loads(linea)
                except ValueError:
                    continue
                t = float(x.get("t") or 0)
                if t >= desde and (hasta is None or t <= hasta):
                    out.append(x)
    except OSError:
        pass
    return out


def _hace(segundos):
    s = max(0, int(segundos))
    if s < 3600:
        return "%d min" % max(1, s // 60)
    if s < 2 * 86400:
        return "%d h" % (s // 3600)
    return "%d días" % (s // 86400)


def _visto(uso, ahora):
    """«visto hace X en la terminal» / «… en la página» / '' (de la marca de uso)."""
    partes = []
    for via, nombre in (("terminal", "la terminal"), ("pagina", "la página")):
        t = (uso or {}).get(via)
        if t:
            partes.append("hace %s en %s" % (_hace(ahora - float(t)), nombre))
    return ("visto " + " y ".join(partes)) if partes else "todavía sin usar en esta máquina"


# ── lo cableado, desde la ficha ────────────────────────────────────────────
def cableado(ficha):
    """{pieza: (estado, por_que)} según la ficha (sin mirar la máquina, salvo su sistema: contrato.sin_via)."""
    s, n = ficha.get("sesion") or {}, ficha.get("nucleo") or {}
    mcp, sk, antes = n.get("mcp") or {}, s.get("skills") or {}, s.get("de_antes") or {}
    from arquitectura import contrato
    sin_sesion = contrato.sin_via(s)
    out = {}
    if mcp and "no" not in mcp and not sin_sesion and (not s.get("sin_nucleo") or s.get("mcp_del_nucleo")):
        out["mcp"] = (OK, "por sesión: " + str(mcp.get("declara") or "su ficha"))
    elif antes.get("mcp"):
        out["mcp"] = (OK, "por la vía de antes: " + antes["mcp"])
    else:
        out["mcp"] = (SIN_VIA, mcp.get("no") or sin_sesion or s.get("sin_nucleo") or "su ficha no trae el MCP")
    if not sin_sesion and (s.get("argv") or s.get("archivos")):
        out["hooks"] = (OK, "por sesión")
    elif not sin_sesion and s.get("perfil_agente"):          # cable-hermes: el perfil del motor, uno por agente
        out["hooks"] = (OK, "por el perfil propio del agente")
    elif not sin_sesion and s.get("perfil"):
        out["hooks"] = (OK, "por el perfil: " + s["perfil"])
    elif antes.get("hooks"):
        out["hooks"] = (OK, "por la vía de antes: " + antes["hooks"])
    else:
        out["hooks"] = (SIN_VIA, sin_sesion or "su ficha no trae vía por sesión para los hooks")
    if not sin_sesion and sk.get("via") in ("paquete", "proyecto", "perfil"):
        out["skills"] = (OK, "por sesión: " + {"paquete": "en el plugin del paquete",
                                               "proyecto": "en la carpeta de skills del proyecto",
                                               "perfil": "en el perfil propio del agente"}[sk["via"]])
    elif antes.get("skills"):
        out["skills"] = (OK, "por la vía de antes: " + antes["skills"])
    else:
        out["skills"] = (SIN_VIA, sin_sesion or "su ficha no trae vía por sesión para las skills del cerebro")
    return out


def instalado(ficha, which=shutil.which):
    return bool(which(ficha.get("binario") or ficha.get("motor") or ""))


#: Lo que se le dice al socio, en simple, por estado (la acción del doctor).
GUIA = {
    CONFIANZA: "Abre {nombre} en la terminal de ese agente, escribe /hooks y confía en los de Workspace (una sola vez); "
               "la página también te lo muestra con su guía.",
    SIN_VIA: "Nada que hacer de tu lado: Workspace todavía no puede cargarle eso a {nombre} por sesión sin tocar su "
             "config (el porqué va arriba). Lo demás funciona igual.",
    FALTA: "Corre `workspace doctor` otra vez; si sigue, `workspace doctor --bundle` y mándalo a soporte.",
}


def _confianza_codex(cerebros):
    """Lo peor que dice Codex de los hooks de Workspace en los cerebros que lo usan: None (no se sabe), "listo" o
    "falta"/"modificados" (amigable.confianza_codex, por su `hooks/list`)."""
    peor = None
    for b in cerebros:
        if not os.path.isfile(os.path.join(str(b), ".codex", "hooks.json")):
            continue                     # todavía no se abrió con el paquete: los pone al abrir
        try:
            import amigable
            r = amigable.confianza_codex(b, esperar=True)
        except Exception:
            r = None
        e = (r or {}).get("estado")
        if e in ("falta", "modificados"):
            return e
        if e == "listo":
            peor = "listo"
    return peor


def paquete_listo():
    """(True, '') si el paquete se arma en esta máquina (lo mismo que hace cada apertura, pero en una carpeta temporal:
    el doctor --check no escribe nada) con su lanzador y el MCP, y el Python de Workspace está; o (False, por qué)."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="workspace-salud-")
    try:
        from arquitectura import generar, sesion
        for fmt, d in generar.armar(os.path.join(tmp, "p"), version=generar._version()).items():
            for f in (os.path.join("lanzador", "hook.py"), os.path.join("lanzador", "mcp.py")):
                if not os.path.isfile(os.path.join(d, f)):
                    return False, "al paquete %s le falta %s" % (fmt, f)
        py = sesion.python()
        if not (os.path.isfile(py) or shutil.which(py)):
            return False, "no encuentro el Python de Workspace: %s" % py
        return True, ""
    except Exception as e:
        return False, "el paquete no se arma: %s: %s" % (type(e).__name__, e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def revisar(cerebros_por_motor=None, which=None, ahora=None, state_dir=None, armar=None):
    """[{motor, nombre, piezas: {pieza: {estado, por_que, visto}}}] por cada motor instalado. `cerebros_por_motor`:
    {motor: [cerebros de sus agentes]} (para la confianza de Codex)."""
    from arquitectura import contrato
    ahora = time.time() if ahora is None else ahora
    marcas = usos(state_dir)
    listo, por_que = (armar or paquete_listo)()
    which = which or shutil.which
    filas = []
    for motor in contrato.MOTORES:
        ficha = contrato.ficha(motor)
        if not instalado(ficha, which):
            continue
        piezas = {}
        for pieza, (estado, texto) in cableado(ficha).items():
            if estado == OK and not listo:
                estado, texto = FALTA, por_que
            piezas[pieza] = {"estado": estado, "por_que": texto,
                             "visto": _visto((marcas.get(motor) or {}).get(pieza), ahora)
                             if pieza in ("mcp", "hooks") else ""}
        if motor == "codex" and piezas["hooks"]["estado"] == OK:
            c = _confianza_codex((cerebros_por_motor or {}).get(motor) or ())
            if c in ("falta", "modificados"):
                piezas["hooks"].update(estado=CONFIANZA, por_que=(
                    "Codex no corre los hooks del proyecto hasta que los confías una vez en /hooks" if c == "falta" else
                    "cambiaron desde que los confiaste (otro Python o una actualización): confía otra vez en /hooks"))
        if motor == "hermes" and piezas["hooks"]["estado"] == OK and _confianza_hermes() == "falta":
            piezas["hooks"].update(estado=CONFIANZA, por_que=(
                "a un perfil de agente de Hermes le faltan avisos de Workspace aprobados: Workspace los aprueba al "
                "abrir el agente; ábrelo una vez desde Workspace"))
        filas.append({"motor": motor, "nombre": ficha.get("nombre") or motor, "piezas": piezas})
    return filas


def _confianza_hermes():
    """cable-hermes: «falta» si algún perfil de agente de Workspace en Hermes (no el de la auditoría) tiene avisos sin
    aprobar (su lista de aprobados, engines/hermes.confianza_perfil); «listo» si todos; None si no hay."""
    try:
        from engines import hermes as _h
        perfiles = [p for p in _h.perfiles_de_agente() if p != _h.perfil_de_agente("auditoria")]
        if not perfiles:
            return None
        return "falta" if any(_h.confianza_perfil(p)[0] == "falta" for p in perfiles) else "listo"
    except Exception:
        return None


_SIMBOLO = {OK: "✓", CONFIANZA: "falta tu confianza una vez", SIN_VIA: "✗", FALTA: "✗"}


def linea(fila):
    """«MCP ✓ · hooks falta tu confianza una vez · skills ✗ sin vía oficial»."""
    return " · ".join("%s %s" % (("MCP" if p == "mcp" else p), _SIMBOLO[fila["piezas"][p]["estado"]]) for p in PIEZAS)
