#!/usr/bin/env python3
"""WORKSPACE · arquitectura/chequeo — el chequeo rápido de Conexiones: sin IA, en segundos (Conexiones en verde, F2).

Lo que ve el socio en Conexiones (y la línea de Motores) sale de aquí, no de la prueba a fondo con el motor real
(arquitectura/auditoria: esa es nuestra, el canario de nuestras máquinas · C1-a). Solo se enseña lo que Workspace
SABE revisar, en una palabra y con tres estados:

  · ok    ✓ funciona: el chequeo pasó (y, si lo hubo, el uso real lo confirma: «visto hace 2 h»);
  · tuyo  ⚠ algo que solo tú puedes hacer (iniciar sesión, confiar los avisos en Codex): nunca es rojo;
  · roto  ✗ falló algo de Workspace o del motor, con su porqué en una frase.

Lo que no se puede revisar, o lo que un motor no usa, no aparece (C2-a). Cinco filas por motor instalado, cada una
con UNA acción (`accion`): Arreglar (solo lo de Workspace: arquitectura/arreglos), Abrir en el cliente oficial (lo
del motor: login, confiar en Codex) o Reportar (un zip redactado, local).

  · mcp         Herramientas de Workspace (MCP): el núcleo contesta (initialize + tools/list en este proceso) y el
                paquete de ese motor las declara (se arma de verdad, en una carpeta temporal);
  · avisos      Avisos (hooks): van en su paquete, con la confianza donde existe — Codex por su `hooks/list` en las
                carpetas de TUS agentes; Hermes, la lista de aprobados de los perfiles de tus agentes;
  · skills      Skills: van en su paquete o en la carpeta del proyecto que lee el motor, sin enlaces rotos;
  · canal       Canal de la página: un saludo oficial SIN mensaje y sin gastar plan (`initialize` de ACP o del
                app-server de Codex, la API de `opencode serve`, el perfil de OpenClaw con su `config validate`);
                donde no hay saludo gratis (Claude Code: `claude -p` siempre es un turno; Hermes), solo sale si la
                página ya le habló de verdad. Antigravity no tiene: la página no le habla (sus términos);
  · proteccion  Protección: el aviso de antes de cada herramienta está y niega la bóveda (una prueba de mentira: no
                lee nada).

Arriba, «Workspace por dentro» en una línea (el registro de eventos, el MCP núcleo y el paquete). El saludo del canal
abre el programa oficial del motor y lo cierra: se corre la primera vez, con «Revisar ahora» y cuando ese motor cambia
de versión (la revisión al abrir, F4); si no, se reusa el último con su fecha. Lo demás se recalcula en cada revisión.

Solo lee: los archivos de Workspace, los comandos de estado oficiales y los nombres de tus MCP. Nunca escribe la
config de un motor ni imprime una llave. Guarda su último resultado en <estado>/arquitectura/chequeo.json. Stdlib,
falla-suave: una fila que no se pudo revisar no aparece (nunca «?»).
"""
import datetime as _dt
import json
import os
import shutil
import sys
import tempfile
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

from arquitectura import estado_json  # noqa: E402
from olock import file_lock  # noqa: E402

OK, TUYO, ROTO = "ok", "tuyo", "roto"
#: Del peor al mejor (el estado de un motor es el de su peor fila).
ORDEN = (ROTO, TUYO, OK)
GLIFO = {OK: "✓", TUYO: "⚠", ROTO: "✗"}
#: Las filas de cada motor, en su orden (id, nombre en simple).
FILAS = (("mcp", "Herramientas de Workspace (MCP)"), ("avisos", "Avisos (hooks)"), ("skills", "Skills"),
         ("canal", "Canal de la página"), ("proteccion", "Protección"))
NOMBRE_FILA = dict(FILAS)
#: Cómo le habla la página a cada motor (su nombre real).
CANAL = {"claude-code": "claude -p", "codex": "app-server", "copilot": "ACP", "cursor": "ACP", "kiro": "ACP",
         "opencode": "serve", "openclaw": "gateway", "hermes": "ACP"}
#: Los motores con un saludo oficial sin mensaje (no gasta plan): se abre su programa, contesta y se cierra.
SALUDO = ("codex", "copilot", "cursor", "kiro", "opencode", "openclaw")
#: La página no le habla: el porqué en una frase (Motores lo dice; Conexiones no enseña esa fila).
SIN_PAGINA = {"antigravity": "Con un plan personal, sus términos no permiten usarlo dentro de otra app: la página "
                             "no le habla (en su terminal funciona igual)."}
#: Cada cuánto se rehace sola la revisión mientras la página o el hub preguntan (s).
FRESCO_S = 10 * 60
#: Lo más que espera un saludo (s): un motor que tarda más, no contestó.
SALUDO_S = 20
#: Hasta cuándo vale un saludo guardado si nada cambió (s): un día. Uno de hace una semana ya no dice si el canal
#: contesta hoy (la sesión se vence, el motor se rompe sin cambiar de versión): la revisión sola de cada 10 min lo
#: repite una vez al día (unos segundos, sin gastar plan). Mientras vale, la fila dice de cuándo es.
SALUDO_VALE_S = 24 * 3600
#: Lo más viejo que puede ser el uso real de la página para que un canal sin saludo gratis (Claude Code, Hermes) salga
#: en ✓ (s): una semana. Más viejo, no dice nada de hoy: la fila no aparece (no se puede revisar sin un mensaje).
USO_VALE_S = 7 * 24 * 3600
#: La suite no le pregunta nada a los programas reales (igual que Motores y la confianza de Codex): con esta variable
#: no hay saludos ni revisión sola al abrir.
SIN_SONDEOS = "WORKSPACE_NO_SESSION_PROBE"
#: La página que solo mira (pagina_v2.SOLO_LEER, la misma variable): revisa y enseña, pero nunca arregla sola.
SOLO_LEER = "WORKSPACE_PAGINA_SOLO_LEER"


# ── dónde vive ─────────────────────────────────────────────────────────────
def _dir(state_dir=None):
    if not state_dir:
        import paths
        state_dir = paths.state_dir()
    return os.path.join(state_dir, "arquitectura")


def ruta(state_dir=None):
    return os.path.join(_dir(state_dir), "chequeo.json")


def _valido(d):
    return isinstance(d.get("motores", []), list)


def _valido_vistas(d):
    return all(isinstance(v, dict) for v in d.values())


def _apartar_si_danado(p, valido):
    """«Ilegible no es vacío», bajo el candado de `p` y antes de guardar: si lo que hay no se entiende (los lectores
    lo vieron vacío), se aparta con su aviso (estado_json) y no se guarda encima. Si no se pudo apartar, sube."""
    try:
        estado_json.leer(p, apartar=True, valido=valido)
    except ValueError:
        pass


def leer(state_dir=None):
    """El último resultado guardado ({} si no hay)."""
    try:
        d = estado_json.leer(ruta(state_dir), valido=_valido)
    except OSError:
        d = {}
    return d if isinstance(d, dict) else {}


def _ahora_iso(t=None):
    return _dt.datetime.fromtimestamp(t if t is not None else time.time()).isoformat(timespec="seconds")


def hace(iso, ahora=None):
    """«hace 5 min» desde una fecha ISO ('' si no se entiende)."""
    try:
        t = time.mktime(_dt.datetime.fromisoformat(str(iso)).timetuple())
    except (TypeError, ValueError, OverflowError):
        return ""
    s = max(0, int((ahora or time.time()) - t))
    if s < 60:
        return "hace un momento"
    if s < 3600:
        return "hace %d min" % (s // 60)
    if s < 2 * 86400:
        return "hace %d h" % (s // 3600)
    return "hace %d días" % (s // 86400)


def _hace_s(seg):
    s = max(0, int(seg))
    if s < 3600:
        return "%d min" % max(1, s // 60)
    if s < 2 * 86400:
        return "%d h" % (s // 3600)
    return "%d días" % (s // 86400)


def redactar(texto, limite=240):
    """Un error en una línea, sin llaves (los patrones de secret_scan) y con el HOME como «~»."""
    t = " ".join(str(texto or "").split())
    try:
        import secret_scan
        for _cls, rx in secret_scan.PATTERNS:
            t = rx.sub("<secreto>", t)
    except Exception:
        pass
    casa = os.path.expanduser("~")
    if casa and len(casa) > 1:
        t = t.replace(casa, "~")
    return t[:limite]


# ── las filas ──────────────────────────────────────────────────────────────
def fila(id_, estado, texto, accion=None, chequeo="", detalle="", fecha=None):
    """Una fila: {id, nombre, estado, glifo, texto, accion, evidencia, fecha}."""
    return {"id": id_, "nombre": NOMBRE_FILA.get(id_, id_), "estado": estado, "glifo": GLIFO[estado],
            "texto": texto, "accion": accion,
            "evidencia": {"chequeo": chequeo or id_, "detalle": redactar(detalle, 600)},
            "fecha": fecha or _ahora_iso()}


def arreglar(arreglo, etiqueta="Arreglar"):
    """La acción de una pieza de Workspace: la arregla Workspace (arquitectura/arreglos), con respaldo y Deshacer."""
    return {"tipo": "arreglar", "etiqueta": etiqueta, "arreglo": arreglo}


def abrir(que, etiqueta, motor, agente=None, comando=None):
    """La acción de lo que es del motor: se abre su programa oficial (login, confiar en Codex, su cuenta)."""
    a = {"tipo": "abrir", "etiqueta": etiqueta, "abrir": que, "motor": motor}
    if agente:
        a["agente"] = agente
    if comando:
        a["comando"] = list(comando)
    return a


def reportar():
    return {"tipo": "reportar", "etiqueta": "Reportar"}


def _peor(estados):
    for e in ORDEN:
        if e in estados:
            return e
    return OK


# ── lo que se mira una sola vez por revisión (compartido por los motores) ──
class Sondas:
    """Lo que el chequeo le pregunta a la máquina. Las pruebas cambian cualquiera (sin motores reales)."""

    def __init__(self, **cambios):
        for k, v in cambios.items():
            setattr(self, k, v)

    # Workspace
    def nucleo(self):
        from arquitectura import verificacion
        return verificacion._mcp_responde()

    def paquete(self):
        from arquitectura import salud
        return salud.paquete_listo()

    def lanzador(self):
        return lanzador_completo()

    def probar_lanzador(self):
        return probar_lanzador()

    def paquete_instalado(self, cerebros):
        return paquete_instalado(cerebros)

    def openclaw_perfil(self):
        return openclaw_perfil()

    def registro(self):
        from arquitectura import verificacion
        return verificacion._registro(time.time())

    def usos(self):
        from arquitectura import salud
        return salud.usos()

    def prohibe_boveda(self):
        return prohibe_boveda()

    def inventario_mcp(self):
        import mcp_inventory
        return mcp_inventory.scan()

    # la máquina
    def which(self, binario):
        return shutil.which(binario)

    def agentes(self):
        """[(nombre que se ve, motor, cerebro, id)] de los agentes registrados en esta máquina."""
        try:
            import agent_state
            return [(a.get("display") or a.get("name") or "", a.get("engine") or "", a.get("brain") or "",
                     a.get("name") or "") for a in agent_state.snapshot().registered()]
        except Exception:
            return []

    # los motores (solo lectura o su saludo oficial)
    def confianza_codex(self, cerebros):
        from arquitectura import salud
        return salud._confianza_codex(cerebros)

    def hermes_avisos(self):
        return hermes_avisos()

    def saludo(self, motor):
        if os.environ.get(SIN_SONDEOS):
            raise RuntimeError("sin sondeos: no se le pregunta al motor")
        return saludar(motor)

    def version(self, motor, exe):
        if os.environ.get(SIN_SONDEOS):
            return "", ""
        return version_de(motor, exe)

    def huella(self, exe):
        """(ruta real, fecha, tamaño) del programa del motor: si cambia, el motor se actualizó (o se reinstaló)."""
        try:
            real = os.path.realpath(exe)
            st = os.stat(real)
            return [real, int(st.st_mtime), int(st.st_size)]
        except (OSError, TypeError):
            return None


# ── las piezas de Workspace ────────────────────────────────────────────────
#: Lo que tiene que tener el lanzador fijo de Workspace (el que corren los avisos y el MCP de cada motor): hook.py
#: importa comun, prohibidos y traductor al cargar (sin uno, ningún aviso corre); mcp.py, comun.
LANZADOR = ("hook.py", "mcp.py", "comun.py", "prohibidos.py", "traductor.py")
#: Lo más que espera cada prueba del lanzador (s): arrancar Python e importar.
LANZADOR_S = 20


def lanzador_completo():
    """(True, '') si el lanzador fijo de Workspace está completo o todavía no se armó (se arma al abrir el primer
    motor); (False, qué le falta) si existe y le falta algo: los avisos de un motor que ya lo usa fallarían."""
    try:
        from arquitectura import sesion
        d = sesion.carpeta_lanzador()
    except Exception as e:
        return False, "no sé dónde está el lanzador de Workspace: %s" % e
    if not os.path.isdir(d):
        return True, ""
    faltan = [f for f in LANZADOR if not os.path.isfile(os.path.join(d, f))]
    return (not faltan), ("al lanzador de Workspace le falta %s" % ", ".join(faltan) if faltan else "")


def carpeta_que_corren():
    """La carpeta del lanzador que de verdad corren los avisos y el MCP de cada motor: la fija, si ya se armó; si no,
    la del paquete (la que se copia ahí al abrir el primer motor)."""
    from arquitectura import sesion
    d = sesion.carpeta_lanzador()
    return d if os.path.isdir(d) else os.path.join(AQUI, "paquete", "lanzador")


def _entorno_lanzador(casa):
    """El entorno de una prueba del lanzador: el de esta máquina sin la identidad de ninguna pestaña, la raíz de este
    Workspace (como la pone la pestaña que abre un motor) y un HOME temporal: lo que el lanzador llegara a escribir
    (su diagnóstico, un evento) va ahí, nunca a tu estado ni a tu registro."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("WORKSPACE_", "ZENITH_", "HERDR_", "CLAUDE"))}
    env.update(HOME=casa, USERPROFILE=casa, WORKSPACE_ROOT=RAIZ_REPO, PYTHONIOENCODING="utf-8")
    return env


def _cola(b, n=160):
    lineas = [x.strip() for x in (b or b"").decode("utf-8", "replace").splitlines() if x.strip()]
    return redactar(lineas[-1], n) if lineas else ""


def probar_lanzador(timeout=LANZADOR_S):
    """El lanzador que corren los motores, corrido de verdad como lo corre un motor: el Python de Workspace con su
    archivo, sin IA ni red, y con un HOME temporal (no lee ni escribe tu estado).

      · avisos: `hook.py claude pre_tool` con una lectura de la bóveda de llaves tiene que NEGARLA (sale con 2). Si
        hook.py, comun.py, traductor.py o prohibidos.py no cargan, ningún aviso corre y lo prohibido no se niega (un
        aviso que se cae sale con 1: el motor sigue y deja leer);
      · mcp: `mcp.py` (el servidor que abre cada motor) contesta initialize y tools/list.

    → {"carpeta", "avisos": (True, '') | (False, por qué), "mcp": (n herramientas, '') | (0, por qué)}."""
    import subprocess
    import arbol_procesos
    from arquitectura import sesion
    d = carpeta_que_corren()
    py = sesion.python()
    casa = tempfile.mkdtemp(prefix="workspace-chequeo-")
    out = {"carpeta": d}
    try:
        env = _entorno_lanzador(casa)
        import paths
        boveda = os.path.join(paths.state_dir(casa), "secrets.local")
        pedido = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read",
                             "tool_input": {"file_path": boveda}}).encode("utf-8")
        try:
            r = subprocess.run([py, os.path.join(d, "hook.py"), "claude", "pre_tool"], input=pedido,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=casa, timeout=timeout,
                               **arbol_procesos.sin_ventana())
            out["avisos"] = (True, "") if r.returncode == 2 else (False, (
                "su aviso de antes de cada herramienta no negó leer la bóveda (salió con %s%s)"
                % (r.returncode, (": " + _cola(r.stderr)) if _cola(r.stderr) else "")))
        except (OSError, subprocess.TimeoutExpired) as e:
            out["avisos"] = (False, "su aviso de antes de cada herramienta no corrió: %s" % redactar(e, 160))
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "workspace-chequeo", "version": "1"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
        try:
            r = subprocess.run([py, os.path.join(d, "mcp.py")],
                               input=b"".join(json.dumps(m).encode("utf-8") + b"\n" for m in msgs),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=casa, timeout=timeout,
                               **arbol_procesos.sin_ventana())
            n = 0
            for linea in r.stdout.splitlines():
                try:
                    x = json.loads(linea)
                except ValueError:
                    continue
                if isinstance(x, dict) and x.get("id") == 2:
                    n = len(((x.get("result") or {}).get("tools")) or ())
            out["mcp"] = (n, "") if n else (0, "su servidor MCP no contestó (salió con %s%s)" % (
                r.returncode, (": " + _cola(r.stderr)) if _cola(r.stderr) else ""))
        except (OSError, subprocess.TimeoutExpired) as e:
            out["mcp"] = (0, "su servidor MCP no arrancó: %s" % redactar(e, 160))
    finally:
        shutil.rmtree(casa, ignore_errors=True)
    return out


def prohibe_boveda():
    """(True, '') si el aviso de antes de cada herramienta niega leer la bóveda de Workspace. Prueba de mentira: se
    le pregunta al aviso (el del lanzador que corren los motores, el fijo; o el del paquete solo si todavía no se
    armó: con el fijo armado y sin su prohibidos.py, el del paquete NO lo reemplaza) por una lectura de la bóveda,
    sin leer nada."""
    try:
        import importlib.util
        import paths
        ruta_ = os.path.join(carpeta_que_corren(), "prohibidos.py")
        spec = importlib.util.spec_from_file_location("workspace_prohibidos_chequeo", ruta_)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        boveda = os.path.join(paths.state_dir(), "secrets.local")
        motivo = m.motivo({"tool_name": "Read", "tool_input": {"file_path": boveda}})
        return bool(motivo), ("" if motivo else "el aviso dejaría leer la bóveda de llaves")
    except Exception as e:
        return False, "no pude cargar el aviso de lo prohibido: %s: %s" % (type(e).__name__, e)


# ── el paquete INSTALADO: el que de verdad cargan los motores ──────────────
def formato_de(motor):
    from arquitectura import contrato
    return ((contrato.ficha(motor).get("paquete") or {}).get("formato")) or ""


def _leer_paquete(d):
    """{ruta relativa con «/»: bytes} de un formato del paquete, sin cachés y SIN las skills del cerebro (las que
    llevan el sello: esas se revisan por nombre)."""
    from arquitectura import skills_cerebro
    out = {}
    for base, ds, fs in os.walk(d):
        ds[:] = sorted(x for x in ds if x != "__pycache__" and not skills_cerebro.es_nuestra(os.path.join(base, x)))
        for f in fs:
            if f.endswith((".pyc", ".DS_Store")):
                continue
            ruta_ = os.path.join(base, f)
            try:
                with open(ruta_, "rb") as fh:
                    out[os.path.relpath(ruta_, d).replace("\\", "/")] = fh.read()
            except OSError:
                continue
    return out


def _de_plantilla(datos, rel, raiz, py, raices):
    """El archivo instalado vuelto a su plantilla: lo que sesion._fijar_raiz fijó ({{RAIZ}}: su carpeta; {{PY}}: el
    Python de Workspace; {{WS}}: la raíz de Workspace) otra vez como marcas, y los saltos de línea iguales."""
    from arquitectura import generar
    if not rel.endswith((".json", ".yaml", ".js")):
        return datos
    import re
    t = datos.decode("utf-8", "replace").replace("\r\n", "\n")
    marcas = [(raiz, generar.RAIZ), (py, generar.PY)] + [(ws, generar.WS) for ws in raices]
    for ruta_, marca in sorted(marcas, key=lambda x: len(x[0]), reverse=True):   # la más larga primero (un Python
        if ruta_:                                                                 # dentro de la raíz, p. ej.)
            # en Windows la misma carpeta puede venir con otra caja («C:\\dev» / «c:\\dev»): es la misma
            t = re.sub(re.escape(ruta_), lambda _m, marca=marca: marca, t,
                       flags=re.IGNORECASE if os.name == "nt" else 0)
    return t.encode("utf-8")


def _raices_validas():
    """Las raíces de Workspace que puede llevar un paquete bien instalado: la de este proceso y la del comando
    `workspace` de esta máquina (la misma en la de un cliente)."""
    out = [RAIZ_REPO.replace("\\", "/")]
    try:
        import paths
        r = paths.installed_root()
        if r and r.replace("\\", "/") not in out:
            out.append(r.replace("\\", "/"))
    except Exception:
        pass
    return sorted(out, key=len, reverse=True)


def _otra_raiz(plantilla, datos, rel, raiz, py, raices):
    """La raíz de Workspace que lleva el archivo instalado si ESA es su única diferencia (lo armó otra carpeta de
    Workspace, p. ej. otra copia en la misma máquina: sus motores corren ese código), o ''."""
    import re
    from arquitectura import generar
    t = plantilla.decode("utf-8", "replace")
    if generar.WS not in t:
        return ""
    linea = next((x for x in t.splitlines() if generar.WS in x), "")
    rx = re.escape(linea).replace(re.escape(generar.WS), "(.+?)", 1)
    m = re.search(rx.replace(re.escape(generar.RAIZ), ".*?").replace(re.escape(generar.PY), ".*?"),
                  datos.decode("utf-8", "replace"))
    otra = m.group(1) if m else ""
    if otra and _de_plantilla(datos, rel, raiz, py, list(raices) + [otra]) == plantilla:
        return otra
    return ""


def comparar_formato(molde, instalado, esperadas=()):
    """('', '') si el formato instalado (`instalado`, una carpeta) es el que arma esta versión (`molde`: el mismo
    formato recién armado, sin fijar); si no, (la ruta relativa, qué no cuadra en una frase): la primera diferencia.
    `esperadas`: los nombres de las skills del cerebro que tiene que llevar (cada una con su SKILL.md)."""
    from arquitectura import sesion
    if not os.path.isdir(instalado):
        return ".", "falta su carpeta %s" % os.path.basename(instalado)
    raiz = instalado.replace("\\", "/")
    py, raices = sesion.python(), _raices_validas()
    hay = _leer_paquete(instalado)
    plantilla = _leer_paquete(molde)
    for rel in sorted(plantilla):
        if rel not in hay:
            return rel, "le falta %s" % rel
        a = plantilla[rel].replace(b"\r\n", b"\n") if rel.endswith((".json", ".yaml", ".js")) else plantilla[rel]
        if _de_plantilla(hay[rel], rel, raiz, py, raices) != a:
            otra = _otra_raiz(a, hay[rel], rel, raiz, py, raices)
            if otra:
                return rel, "lo armó otra carpeta de Workspace (%s), no la de este" % redactar(otra, 80)
            return rel, "%s no es el de esta versión" % rel
    faltan = [n for n in esperadas if not os.path.isfile(os.path.join(instalado, "skills", n, "SKILL.md"))]
    if faltan:
        return "skills/", "le faltan %d skills del cerebro (%s)" % (len(faltan), ", ".join(faltan[:4]))
    return "", ""


def paquete_instalado(cerebros=()):
    """¿El paquete INSTALADO (el que cargan los motores: el de esta versión y el de cada cerebro de tus agentes) es el
    que arma esta versión? Uno «listo» no se vuelve a armar al abrir: si se dañó (un archivo de menos, su .mcp.json
    sin el servidor, un aviso de menos, sus skills vacías) cada motor lo carga tal cual, aunque uno nuevo sí se arme.
    Solo lee (lo nuevo se arma en una carpeta temporal). → {formato: (rel, por qué)} de lo que no cuadra: {} si todo
    cuadra o si todavía no se instaló (se arma al abrir)."""
    malos = {}
    for _c, _final, fmts in paquetes_danados(cerebros):
        for fmt, x in fmts.items():
            malos.setdefault(fmt, x)
    return malos


def paquetes_danados(cerebros=()):
    """[(cerebro o None, carpeta instalada, {formato: (rel, por qué)})] de los paquetes instalados que no cuadran con
    lo que arma esta versión (paquete_instalado, uno por carpeta: el arreglo «paquete» rehace justo esos)."""
    from arquitectura import generar, sesion, skills_cerebro
    out, vistos, molde = [], set(), None
    tmp = tempfile.mkdtemp(prefix="workspace-chequeo-paquete-")
    try:
        for c in [None] + [x for x in cerebros if x]:
            try:
                final, con_skills = sesion.carpeta_de(c)
            except Exception:
                continue
            if final in vistos or not os.path.isfile(os.path.join(final, ".listo")):
                continue
            vistos.add(final)
            if molde is None:
                molde = generar.armar(os.path.join(tmp, "p"), version=generar._version())
            esperadas = [x["nombre"] for x in skills_cerebro.indice(c)] if con_skills else []
            fmts = {}
            for fmt in generar.FORMATOS:
                rel, por = comparar_formato(molde[fmt], os.path.join(final, fmt),
                                            () if fmt in generar.SIN_SKILLS_DEL_CEREBRO else esperadas)
                if por:
                    fmts[fmt] = (rel, por)
            if fmts:
                out.append((c, final, fmts))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


#: Qué fila tumba un archivo dañado del paquete (por su nombre) — lo demás (sus avisos, su plugin) es «avisos».
_PIEZA_MCP = (".mcp.json", "mcp.json", "openclaw.plugin.json", "mcp.py")


def filas_del_dano(rel):
    """Las filas que tumba un archivo dañado del paquete instalado."""
    rel = str(rel or "").replace("\\", "/")
    nombre = rel.rstrip("/").rsplit("/", 1)[-1]
    if rel.startswith("skills/"):
        return ("skills",)
    if nombre in _PIEZA_MCP:
        return ("mcp",)
    if nombre == "comun.py":
        return ("mcp", "avisos", "proteccion")
    return ("avisos", "proteccion")


def dano_de(motor, instalado):
    """(rel, por qué) del daño del paquete instalado que toca a `motor`, o None: solo su formato, y dentro de él solo
    lo suyo (el hooks.json de Cursor no es de Codex; el de Antigravity no es de Claude Code)."""
    from arquitectura import contrato
    fmt = formato_de(motor)
    d = (instalado or {}).get(fmt)
    if not d:
        return None
    primero = str(d[0]).split("/", 1)[0]
    if primero in contrato.MOTORES or primero in ("antigravity",):
        return d if primero == motor else None
    if fmt == "claude" and motor == "antigravity" and not str(d[0]).startswith("skills/"):
        return None                         # sus avisos van en claude/antigravity/; su MCP, por su .agents/
    return d


# ── OpenClaw: su perfil propio y el plugin de Workspace ────────────────────
def openclaw_perfil():
    """Lo de Workspace en el perfil propio de OpenClaw, leído de sus archivos (sin correr nada): que el perfil cargue
    el plugin de Workspace (plugins.load.paths) encendido, y que ese plugin sea el de esta versión (el que copia
    Workspace al abrirlo: uno viejo lleva otro lanzador y otra raíz). → (True, '') · (False, por qué) · (None, '') si
    no hay perfil todavía (se arma al abrir) o no se pudo leer (su `config validate` lo revisa aparte)."""
    try:
        from engines import openclaw as oc
        from arquitectura import sesion
        if not os.path.isfile(os.path.join(oc.state_dir(), "openclaw.json")):
            return None, ""
        d = oc._profile_config()
        if not isinstance(d, dict):
            return None, ""
        if not oc._ruta_plugin_registrada(d):
            return False, "su perfil no carga el plugin de Workspace (plugins.load.paths)"
        if oc._get_path(d, "plugins.entries.%s.enabled" % oc.PLUGIN_ID) is False:
            return False, "el plugin de Workspace está apagado en su perfil"
        dst = oc.plugin_dir()
        final, _c = sesion.carpeta_de(None)
        if not os.path.isdir(dst):
            return False, "falta el plugin de Workspace que carga su perfil"
        if os.path.isfile(os.path.join(final, ".listo")) and sesion._archivos(dst) != sesion._archivos(
                os.path.join(final, "openclaw")):
            return False, "el plugin de Workspace que carga no es el de esta versión"
        return True, ""
    except Exception:
        return None, ""


def hermes_avisos(excluir_prueba=True):
    """[(perfil, 'lista'|'falta')] de los perfiles de agente de Workspace en Hermes (no el de la prueba a fondo)."""
    try:
        from engines import hermes as _h
        prueba = _h.perfil_de_agente("auditoria")
        return [(p, _h.confianza_perfil(p)[0]) for p in _h.perfiles_de_agente()
                if not (excluir_prueba and p == prueba)]
    except Exception:
        return []


# ── el saludo del canal de la página ───────────────────────────────────────
class SinSesion(Exception):
    """El motor contestó que falta iniciar sesión: es tuyo (⚠), no roto."""


class PerfilInvalido(Exception):
    """OpenClaw: el perfil de Workspace no pasa su `config validate` (es de Workspace: se arregla)."""


def _entorno_motor():
    try:
        from control import entorno
        env = entorno.con_basicas(entorno.limpio())
    except Exception:
        env = dict(os.environ)
    try:
        import secret_store
        env = secret_store.engine_env(env)
    except Exception:
        pass
    env["DISABLE_AUTOUPDATER"] = "1"
    return env


def _saludo_acp(motor, cwd, timeout):
    from control import acp
    from control.canal import CanalProceso
    from control.jsonrpc import ErrorRPC, Par
    canal = CanalProceso(list(acp.FICHAS[motor]["cmd"]), cwd=cwd, env=_entorno_motor())
    rpc = Par(canal)
    try:
        ini = rpc.llamar("initialize", {
            "protocolVersion": acp.VERSION_ACP,
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False},
            "clientInfo": acp.CLIENTE}, timeout) or {}
    except ErrorRPC as e:
        if getattr(e, "codigo", None) == acp.AUTH_REQUERIDA:
            raise SinSesion(str(getattr(e, "mensaje", e)))
        raise RuntimeError("%s%s" % (getattr(e, "mensaje", e), acp._detalle(e)))
    finally:
        canal.cerrar(espera=1.0)
    v = ini.get("protocolVersion")
    return "contestó al saludo de ACP%s, sin mensaje y sin gastar plan" % ((" (v%s)" % v) if v else "")


def _saludo_codex(cwd, timeout):
    from control import codex as cc
    from control.canal import CanalProceso
    from control.jsonrpc import ErrorRPC, Par
    canal = CanalProceso(["codex", "app-server"], cwd=cwd, env=_entorno_motor())
    rpc = Par(canal, cabecera=False)
    try:
        rpc.llamar("initialize", {"clientInfo": cc.CLIENTE}, timeout)
    except ErrorRPC as e:
        raise RuntimeError(str(getattr(e, "mensaje", e)))
    finally:
        canal.cerrar(espera=1.0)
    return "su app-server contestó al saludo, sin hilo y sin gastar plan"


def _saludo_opencode(cwd, timeout):
    """`opencode serve` en un puerto libre de 127.0.0.1 con una clave local nueva (como la página), una consulta a su
    API y se apaga. Sin sesión ni mensaje."""
    import base64
    import secrets
    import socket
    import subprocess
    import urllib.error
    import urllib.request
    from control.canal import opciones_proceso, resolver
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    clave = secrets.token_urlsafe(24)
    env = dict(_entorno_motor(), OPENCODE_SERVER_PASSWORD=clave)
    proc = subprocess.Popen(resolver(["opencode", "serve", "--port", str(puerto), "--hostname", "127.0.0.1"]),
                            cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **opciones_proceso())
    try:
        fin = time.time() + timeout
        while time.time() < fin:
            if proc.poll() is not None:
                raise RuntimeError("`opencode serve` se cerró al arrancar (código %s)" % proc.returncode)
            try:
                socket.create_connection(("127.0.0.1", puerto), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("`opencode serve` no abrió su puerto en %d s" % timeout)
        pedido = urllib.request.Request("http://127.0.0.1:%d/api/session" % puerto, headers={
            "Authorization": "Basic " + base64.b64encode(("opencode:" + clave).encode()).decode()})
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with op.open(pedido, timeout=5) as r:
                codigo = r.status
        except urllib.error.HTTPError as e:
            codigo = e.code
        if codigo >= 500:
            raise RuntimeError("su servidor contestó %d" % codigo)
        return "su servidor (`opencode serve`) contestó, sin sesión y sin gastar plan"
    finally:
        _cerrar_arbol(proc)


def _cerrar_arbol(proc, windows=None, gracia=1.0):
    """Cierra un programa de motor y TODO lo que lanzó, como la capa de control (CanalProceso.cerrar): en Windows su
    árbol (arbol_procesos.matar_arbol: `opencode` es un .cmd que lanza node, y `proc.kill()` solo mataba el .cmd), en
    Mac/Linux su grupo entero (control.hijos.matar_grupo: SIGTERM y, si algo se queda, SIGKILL). Falla suave."""
    try:
        if os.name == "nt" if windows is None else windows:
            import arbol_procesos
            arbol_procesos.matar_arbol(proc)
        else:
            from control import hijos
            hijos.matar_grupo(proc.pid, proc.pid, gracia=gracia)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=3)
    except Exception:
        pass


def _saludo_openclaw():
    """OpenClaw: la página le habla por el puente ACP de su gateway, con el perfil propio de Workspace. Sin mensaje: su
    revisión oficial de ese perfil (`openclaw --profile workspace config validate`); el gateway lo prende la página al
    usarlo (y lo apaga). Sin perfil todavía, se arma la primera vez que lo abres."""
    from engines import openclaw as oc
    if not os.path.isfile(os.path.join(oc.state_dir(), "openclaw.json")):
        # todavía sin perfil (se arma la primera vez que lo abres): que su programa abra, sin mensaje (`--version`)
        _openclaw_abre()
        return "su programa abre; su perfil de Workspace se arma la primera vez que lo abres"
    v = oc.validar_perfil()
    if v is False:
        _openclaw_abre()                    # un programa que no abre no es un perfil inválido: dice lo que es
        raise PerfilInvalido("config validate: no")
    if v is None:
        raise RuntimeError("no contestó a su revisión oficial del perfil (config validate)")
    return "su perfil de Workspace pasa su revisión oficial (config validate); la página prende su gateway al usarlo"


def _openclaw_abre():
    """`openclaw --version` (sin mensaje ni perfil): levanta RuntimeError si su programa no abre."""
    import subprocess
    from control.canal import opciones_proceso, resolver
    try:
        r = subprocess.run(resolver(["openclaw", "--version"]), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, env=_entorno_motor(), timeout=SALUDO_S, **opciones_proceso())
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("`openclaw --version` no corrió: %s" % e)
    if r.returncode:
        raise RuntimeError("`openclaw --version` salió con %s%s" % (r.returncode, (": " + _cola(r.stderr))
                                                                      if _cola(r.stderr) else ""))


def saludar(motor, timeout=SALUDO_S):
    """El saludo oficial del canal de la página de `motor`: → el porqué de ✓; SinSesion si falta tu sesión;
    cualquier otra excepción = no contestó. En una carpeta temporal que se borra (no es la de ningún agente)."""
    cwd = tempfile.mkdtemp(prefix="workspace-saludo-")
    try:
        if motor in ("copilot", "cursor", "kiro"):
            return _saludo_acp(motor, cwd, timeout)
        if motor == "codex":
            return _saludo_codex(cwd, timeout)
        if motor == "opencode":
            return _saludo_opencode(cwd, timeout)
        if motor == "openclaw":
            return _saludo_openclaw()
        raise RuntimeError("sin saludo para %s" % motor)
    finally:
        shutil.rmtree(cwd, ignore_errors=True)


def version_de(motor, exe):
    """(versión, estado: probada|nueva|vieja|rota|sin_probar|'') de `exe` (su `--version`, cacheado por la fecha del
    programa: engine_versions). Una nueva es solo informativa (C8-a): nunca cambia el estado de una fila."""
    try:
        import dispatch
        import engine_versions as EV
        mod = dispatch.load_engine(motor)
        try:
            import engines_tui
            if engines_tui._blk(mod):
                return "", ""
        except Exception:
            pass
        st, have, _r = EV.drift(mod, EV.installed_version(exe))
        return (have or ""), {"ok": "probada", "newer": "nueva", "older": "vieja", "broken": "rota",
                              "unsupported": "rota", "untested": "sin_probar"}.get(st, "")
    except Exception:
        return "", ""


# ── la revisión de un motor ────────────────────────────────────────────────
def _nombres(lista):
    lista = [x for x in lista if x]
    if len(lista) <= 1:
        return "".join(lista)
    return ", ".join(lista[:-1]) + " y " + lista[-1]


def _visto(uso, ahora):
    partes = []
    for via, nombre in (("terminal", "la terminal"), ("pagina", "la página")):
        t = (uso or {}).get(via)
        if t:
            partes.append("hace %s en %s" % (_hace_s(ahora - float(t)), nombre))
    return (" · vistos " + " y ".join(partes)) if partes else ""


def _danada(motor, ctx, fila_id):
    """La fila rota por el paquete INSTALADO dañado (el que carga `motor`) o por el plugin de OpenClaw, o None."""
    d = dano_de(motor, ctx.get("instalado"))
    if d and fila_id in filas_del_dano(d[0]):
        from arquitectura import contrato
        return fila(fila_id, ROTO, "El paquete de Workspace instalado para %s está dañado: %s." % (
            contrato.ficha(motor).get("nombre") or motor, redactar(d[1], 140)), arreglar("paquete"),
            "%s.paquete_instalado" % fila_id, d[1])
    if motor == "openclaw" and fila_id in ("mcp", "avisos", "proteccion"):
        ok, por = ctx.get("openclaw") or (None, "")
        if ok is False:
            return fila(fila_id, ROTO, "Su perfil propio no carga bien lo de Workspace: %s." % por,
                        arreglar("openclaw-perfil"), "%s.openclaw_perfil" % fila_id, por)
    return None


def _fila_mcp(motor, nombre, cab, ctx):
    from arquitectura import salud
    est, _por = cab.get("mcp", (salud.SIN_VIA, ""))
    if est == salud.SIN_VIA:
        return None
    n, err = ctx["nucleo"]
    if not n:
        return fila("mcp", ROTO, "Las herramientas de Workspace no contestan: %s." % redactar(err, 140),
                    arreglar("lanzador"), "mcp.lanzador", err or "sin herramientas")
    listo, por = ctx["paquete"]
    if not listo:
        return fila("mcp", ROTO, "El paquete de Workspace no se arma: %s" % redactar(por, 120),
                    arreglar("paquete"), "mcp.paquete", por)
    roto = _danada(motor, ctx, "mcp")
    if roto:
        return roto
    texto = "Su servidor arranca y contesta (%d herramientas), como lo abre %s." % (n, nombre)
    if formato_de(motor) == "claude" and motor != "antigravity":
        texto += " Su paquete instalado lo declara."
    if motor == "codex":
        texto += " La primera vez, Codex te pregunta antes de usar una: es normal de Codex."
    texto += _visto(ctx["usos"].get(motor, {}).get("mcp"), ctx["ahora"])
    return fila("mcp", OK, texto, None, "mcp.lanzador+paquete", "%d herramientas" % n)


def _codex_confianza(ctx, agentes):
    """(estado, sin): lo que dice Codex (`hooks/list`) de los avisos de Workspace en las carpetas de tus agentes que ya
    los tienen: "listo" · "falta" · "modificados" · "no_contesto" (los tiene y Codex no contestó) · None (ninguna
    carpeta los tiene todavía: se ponen al abrir); `sin`, los nombres de los agentes que faltan."""
    cerebros = [c for _n, c in agentes]
    conf = ctx["sondas"].confianza_codex(cerebros) if cerebros else None
    if conf in ("falta", "modificados"):
        sin = [n for n, c in agentes if ctx["sondas"].confianza_codex([c]) in ("falta", "modificados")]
        return conf, sin
    if conf is None and any(os.path.isfile(os.path.join(c, ".codex", "hooks.json")) for c in cerebros):
        conf = ctx["sondas"].confianza_codex(cerebros)     # una vez más: un Codex que tardó en abrir no es un rojo
        if conf in ("falta", "modificados"):
            return conf, [n for n, c in agentes if ctx["sondas"].confianza_codex([c]) in ("falta", "modificados")]
        if conf is None:
            return "no_contesto", []
    return conf, []


def _fila_avisos(motor, nombre, cab, ctx):
    from arquitectura import salud
    est, _por = cab.get("hooks", (salud.SIN_VIA, ""))
    if est == salud.SIN_VIA:
        return None
    listo, por = ctx["lanzador"]
    if not listo:
        return fila("avisos", ROTO, "Los avisos no llegarían: %s." % por, arreglar("lanzador"), "avisos.lanzador", por)
    listo, por = ctx["paquete"]
    if not listo:
        return fila("avisos", ROTO, "El paquete de Workspace no se arma: %s" % redactar(por, 120),
                    arreglar("paquete"), "avisos.paquete", por)
    roto = _danada(motor, ctx, "avisos")
    if roto:
        return roto
    visto = _visto(ctx["usos"].get(motor, {}).get("hooks"), ctx["ahora"])
    agentes = ctx["agentes_de"](motor)
    if motor == "codex":
        conf, sin = ctx["codex_confianza"](agentes)
        if conf in ("falta", "modificados"):
            primero = sin[0] if sin else (agentes[0][0] if agentes else "")
            texto = ("Falta confiar en los avisos de Workspace en Codex (una vez, en /hooks)" if conf == "falta" else
                     "Cambiaron desde que los confiaste: confía otra vez en Codex (/hooks)")
            a = abrir("confiar", "Abrir Codex y confiar", motor, agente=ctx["ids"].get(primero) or primero)
            a["agente_nombre"] = primero
            return fila("avisos", TUYO, texto + (": %s." % _nombres(sin) if sin else "."), a,
                        "avisos.codex_hooks_list", "hooks/list: %s" % conf)
        if conf == "no_contesto":
            return fila("avisos", ROTO, "No pude preguntarle a Codex si confías en los avisos (su hooks/list no "
                                        "contestó).", reportar(), "avisos.codex_hooks_list", "hooks/list: sin respuesta")
        if conf == "listo":
            return fila("avisos", OK, "Confiados en %s (lo dice Codex: hooks/list).%s" % (
                _nombres([n for n, _c in agentes]), visto), None, "avisos.codex_hooks_list", "hooks/list: listo")
        return fila("avisos", OK, "Listos: Codex te pide confiarlos una vez la primera vez que abras un agente con "
                                  "él." + visto, None, "avisos.codex_hooks_list", "sin carpetas abiertas con Codex")
    if motor == "hermes":
        perfiles = ctx["sondas"].hermes_avisos()
        faltan = [p for p, e in perfiles if e == "falta"]
        if faltan:
            return fila("avisos", ROTO, "A %s le faltan avisos de Workspace aprobados." % _nombres(faltan),
                        arreglar("hermes-avisos"), "avisos.hermes_allowlist", ", ".join(faltan))
        if perfiles:
            return fila("avisos", OK, "Aprobados en el perfil de cada agente; su aviso corre y niega lo prohibido."
                        "%s" % visto, None, "avisos.hermes_allowlist", "%d perfiles" % len(perfiles))
    return fila("avisos", OK, "Su aviso corre y niega lo prohibido, como lo corre %s.%s" % (nombre, visto), None,
                "avisos.lanzador+paquete")


def _skills_rotas(motor, ficha, cerebros):
    """[(cerebro, carpeta)] de skills de Workspace (con su sello) sin su SKILL.md, en la carpeta del proyecto que lee el
    motor (solo las que puso Workspace; las tuyas no se miran)."""
    via = (ficha.get("sesion") or {}).get("skills") or {}
    if via.get("via") != "proyecto":
        return []
    from arquitectura import skills_cerebro
    rotas = []
    for c in cerebros:
        dst = str(via.get("ruta") or "").replace("{cerebro}", c)
        if not dst or not os.path.isdir(dst):
            continue
        for n in sorted(os.listdir(dst)):
            d = os.path.join(dst, n)
            if os.path.islink(d) and not os.path.exists(d):
                rotas.append((c, n))
            elif os.path.isdir(d) and skills_cerebro.es_nuestra(d) and not os.path.isfile(os.path.join(d, "SKILL.md")):
                rotas.append((c, n))
    return rotas


def _skills_faltan(ficha, cerebros):
    """[(cerebro, [nombres])] de las skills del cerebro que NO están en la carpeta del proyecto que lee el motor, en
    las carpetas que ya la tienen (la vista se pone al abrir: una carpeta que todavía no existe no cuenta). Una tuya con
    el mismo nombre cuenta como puesta (la tuya gana)."""
    via = (ficha.get("sesion") or {}).get("skills") or {}
    if via.get("via") != "proyecto":
        return []
    from arquitectura import skills_cerebro
    out = []
    for c in cerebros:
        dst = str(via.get("ruta") or "").replace("{cerebro}", c)
        if not dst or not os.path.isdir(dst):
            continue
        faltan = [x["nombre"] for x in skills_cerebro.indice(c) if not os.path.isdir(os.path.join(dst, x["nombre"]))]
        if faltan:
            out.append((c, faltan))
    return out


def _cuantas(cerebros):
    from arquitectura import skills_cerebro
    try:
        return sum(len(skills_cerebro.indice(c)) for c in cerebros)
    except Exception:
        return 0


def _skills_vistas(motor, ficha, cerebro):
    """¿Se VIERON puestas las skills de `cerebro` donde las lee `motor`? Sí, si ya están en su carpeta del proyecto
    (vía «proyecto») o en el paquete instalado de ese cerebro (vía «paquete»: lo revisa paquete_instalado); OpenClaw las
    lee de la carpeta skills/ del cerebro mismo. No, si todavía no se pusieron (se ponen al abrir) o van en un perfil
    que no se lee aquí (Hermes)."""
    from arquitectura import generar, sesion
    via = (ficha.get("sesion") or {}).get("skills") or {}
    if via.get("via") == "proyecto":
        return os.path.isdir(str(via.get("ruta") or "").replace("{cerebro}", cerebro))
    if via.get("via") == "paquete":
        if formato_de(motor) in generar.SIN_SKILLS_DEL_CEREBRO:
            return os.path.isdir(os.path.join(cerebro, "skills"))
        try:
            return os.path.isfile(os.path.join(sesion.carpeta_de(cerebro)[0], ".listo"))
        except Exception:
            return False
    return False


def _fila_skills(motor, nombre, cab, ficha, ctx):
    from arquitectura import salud
    est, _por = cab.get("skills", (salud.SIN_VIA, ""))
    if est == salud.SIN_VIA:
        return None
    listo, por = ctx["paquete"]
    if not listo:
        return fila("skills", ROTO, "El paquete de Workspace no se arma: %s" % redactar(por, 120),
                    arreglar("paquete"), "skills.paquete", por)
    roto = _danada(motor, ctx, "skills")
    if roto:
        return roto
    agentes = ctx["agentes_de"](motor)
    cerebros = [c for _n, c in agentes]
    rotas = _skills_rotas(motor, ficha, cerebros)
    if rotas:
        return fila("skills", ROTO, "%d skills de Workspace quedaron a medias en la carpeta que lee %s." % (
            len(rotas), nombre), arreglar("skills:" + motor), "skills.proyecto",
            "; ".join("%s/%s" % (os.path.basename(c), n) for c, n in rotas[:6]))
    faltan = _skills_faltan(ficha, cerebros)
    if faltan:
        n = sum(len(x) for _c, x in faltan)
        return fila("skills", ROTO, "Faltan %d skills del cerebro de %s en la carpeta que lee %s." % (
            n, _nombres([a for a, c in agentes if any(c == x for x, _f in faltan)]), nombre),
            arreglar("skills:" + motor), "skills.proyecto",
            "; ".join("%s: %s" % (os.path.basename(c), ", ".join(x[:4])) for c, x in faltan[:3]))
    n = _cuantas(cerebros)
    if agentes and n:
        vistas = all(_skills_vistas(motor, ficha, c) for c in cerebros)
        return fila("skills", OK, "Las %d skills del cerebro de %s %s donde las lee %s%s." % (
            n, _nombres([a for a, _c in agentes]), "están" if vistas else "van", nombre,
            "" if vistas else " al abrirlo"), None, "skills.paquete+proyecto",
            "%d skills%s" % (n, "" if vistas else ", todavía sin poner"))
    if agentes:
        return fila("skills", OK, "Las de Workspace van en su paquete (el cerebro de %s no trae skills propias)." % (
            _nombres([a for a, _c in agentes])), None, "skills.paquete")
    return fila("skills", OK, "Van donde las lee %s al abrir un agente con él." % nombre, None, "skills.paquete")


def _fila_canal(motor, nombre, ctx, guardado, saludar_ya):
    if motor in SIN_PAGINA:
        return None
    via = CANAL.get(motor, "")
    titulo = "Canal de la página · " + via if via else None
    if motor in SALUDO:
        r = ctx["saludos"].get(motor)
        if r is None and vigente(guardado, ctx["ahora"]):
            f = dict(guardado)                # el de antes, con su fecha: la fila dice de cuándo es el saludo
            base = f.get("saludo") or f.get("texto") or ""
            cuando = hace(f.get("fecha"), ctx["ahora"])
            if cuando and cuando != "hace un momento":
                f["texto"] = "%s (saludo de %s)." % (base.rstrip("."), cuando)
        else:
            r = r or _saludo_seguro(ctx["sondas"], motor)
            if r[0] == OK:
                f = fila("canal", OK, r[1][:1].upper() + r[1][1:] + ".", None, "canal.saludo")
                f["saludo"] = f["texto"]
            elif r[0] == "perfil":                # OpenClaw: el perfil de Workspace no pasa su config validate
                f = fila("canal", ROTO, "El perfil de Workspace en OpenClaw no pasa su revisión oficial "
                                        "(config validate).", arreglar("openclaw-perfil"),
                         "canal.openclaw_config_validate", r[1])
            elif r[0] == TUYO:
                f = fila("canal", TUYO, "Inicia sesión en %s para que la página le hable." % nombre,
                         abrir("login", "Iniciar sesión", motor), "canal.saludo", r[1])
            else:
                f = fila("canal", ROTO, "No contestó al saludo: %s" % redactar(r[1], 140), reportar(),
                         "canal.saludo", r[1])
    else:
        uso = ctx["usos"].get(motor, {})
        t = max([float(uso.get(p, {}).get("pagina") or 0) for p in ("hooks", "mcp")] or [0])
        if not t or ctx["ahora"] - t > USO_VALE_S:
            return None                       # sin saludo gratis ni uso real reciente: no se puede revisar → no aparece
        f = fila("canal", OK, "La página le habló hace %s (uso real: sin gastar un mensaje no se puede revisar "
                              "antes)." % _hace_s(ctx["ahora"] - t), None, "canal.uso_real")
    if titulo:
        f["nombre"] = titulo
    return f


def vigente(guardado, ahora):
    """¿El saludo guardado de un motor todavía vale (funcionaba o era tuyo, y no es más viejo que SALUDO_VALE_S)?"""
    return bool(guardado and guardado.get("id") == "canal" and guardado.get("estado") in (OK, TUYO)
                and ahora - _epoch(guardado.get("fecha")) < SALUDO_VALE_S)


def _saludo_seguro(sondas, motor):
    """(OK, por qué) · (TUYO, lo que dijo) · (ROTO, el error): el saludo, sin levantar nunca."""
    try:
        return OK, str(sondas.saludo(motor))
    except SinSesion as e:
        return TUYO, str(e)
    except PerfilInvalido as e:
        return "perfil", str(e)
    except Exception as e:
        return ROTO, "%s: %s" % (type(e).__name__, e)


def saludos_en_paralelo(sondas, motores):
    """{motor: _saludo_seguro} de varios motores a la vez (cada uno abre su programa: así tarda lo del más lento)."""
    out, hilos = {}, []
    for m in motores:
        def uno(m=m):
            out[m] = _saludo_seguro(sondas, m)
        t = threading.Thread(target=uno, name="workspace-saludo-" + m, daemon=True)
        t.start()
        hilos.append(t)
    fin = time.time() + SALUDO_S + 10
    for t in hilos:
        t.join(max(0.1, fin - time.time()))
    for m in motores:
        # uno que no contestó (o tardó: varios programas que arrancan a la vez se estorban) se pregunta otra vez, solo:
        # un rojo por una carrera sería un rojo falso
        if out.get(m, (ROTO,))[0] == ROTO:
            out[m] = _saludo_seguro(sondas, m)
    return out


def _epoch(iso):
    try:
        return time.mktime(_dt.datetime.fromisoformat(str(iso)).timetuple())
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _kiro_sin_regla(cerebros):
    """Los cerebros cuyo agente `workspace` de Kiro (el que elige su terminal) ya existe y NO trae la regla de lectura
    que niega la bóveda (memoria_mcp: fs_read deny)."""
    out = []
    for c in cerebros:
        p = os.path.join(c, ".kiro", "agents", "workspace.json")
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        reglas = (d.get("permissions") or {}).get("rules") or d.get("rules") or []
        lee = ((d.get("toolsSettings") or {}).get("fs_read") or {}).get("deniedPaths") or []
        if not lee and not any(isinstance(r, dict) and r.get("capability") == "fs_read" and r.get("effect") == "deny"
                               for r in reglas):
            out.append(c)
    return out


def _fila_proteccion(motor, nombre, cab, ctx):
    from arquitectura import salud
    ok, por = ctx["proteccion"]
    if not ok:
        return fila("proteccion", ROTO, "Lo prohibido no quedaría bloqueado: %s." % por, arreglar("lanzador"),
                    "proteccion.prohibidos", por)
    roto = _danada(motor, ctx, "proteccion")
    if roto:
        return roto
    agentes = ctx["agentes_de"](motor)
    if cab.get("hooks", (salud.SIN_VIA, ""))[0] == salud.SIN_VIA:
        # el motor no corre los avisos de Workspace en este sistema (Kiro en Windows): lo niegan las reglas de su perfil
        if motor != "kiro":
            return fila("proteccion", ROTO, "En este sistema %s no corre el aviso de Workspace que bloquea lo "
                                            "prohibido." % nombre, reportar(), "proteccion.sin_avisos")
        sin = _kiro_sin_regla([c for _n, c in agentes])
        if sin:
            return fila("proteccion", ROTO, "Al agente de Kiro de %s le falta la regla que niega leer la bóveda." % (
                _nombres([n for n, c in agentes if c in sin])), reportar(), "proteccion.kiro_reglas")
        return fila("proteccion", OK, "Aquí Kiro no corre el aviso de Workspace: lo prohibido lo niegan las reglas de "
                                      "lectura de su agente (fs_read) y, en la página, Workspace.", None,
                    "proteccion.kiro_reglas")
    if motor == "codex":
        conf, sin = ctx["codex_confianza"](agentes)
        if conf in ("falta", "modificados"):
            primero = sin[0] if sin else (agentes[0][0] if agentes else "")
            a = abrir("confiar", "Abrir Codex y confiar", motor, agente=ctx["ids"].get(primero) or primero)
            a["agente_nombre"] = primero
            return fila("proteccion", TUYO, "En su terminal lo prohibido se bloquea cuando confíes los avisos de "
                                            "Workspace (/hooks); en la página ya, por su perfil de permisos.", a,
                        "proteccion.codex_hooks_list", "hooks/list: %s" % conf)
        if conf == "no_contesto":
            return fila("proteccion", ROTO, "No pude saber si Codex corre el aviso que bloquea lo prohibido (su "
                                            "hooks/list no contestó).", reportar(), "proteccion.codex_hooks_list")
    return fila("proteccion", OK, "Probado sin leer nada: su aviso de antes de cada herramienta niega leer la bóveda de "
                                  "llaves y tus secretos.", None, "proteccion.lanzador+prohibidos")


def _tus_mcp(motor, data):
    """Los nombres de TUS MCP en `motor` (no los de los archivos de Workspace). None si no se pudo leer."""
    if data is None:
        return None
    if any(f.get("engine") == motor and f.get("state") == "unreadable" and f.get("scope") != "profile"
           for f in data.get("files") or ()):
        return None
    return sorted({r["name"] for r in data.get("records") or ()
                   if r.get("engine") == motor and r.get("scope") != "profile" and r.get("name")})


def revisar_motor(motor, ctx, guardado=None, saludar_ya=False):  # noqa: ARG001 (saludar_ya: ctx["saludos"])
    """{motor, nombre, version, version_estado, estado, filas, tus_mcp, sin_pagina} de un motor instalado."""
    from arquitectura import contrato, salud
    ficha = contrato.ficha(motor)
    nombre = ficha.get("nombre") or motor
    cab = salud.cableado(ficha)
    previas = {f.get("id"): f for f in (guardado or {}).get("filas") or ()}
    filas = []
    for f in (_fila_mcp(motor, nombre, cab, ctx), _fila_avisos(motor, nombre, cab, ctx),
              _fila_skills(motor, nombre, cab, ficha, ctx),
              _fila_canal(motor, nombre, ctx, previas.get("canal"), saludar_ya),
              _fila_proteccion(motor, nombre, cab, ctx)):
        if f:
            filas.append(f)
    v = (ctx.get("vistas") or {}).get(motor)
    if v and v.get("version"):                       # lo de la revisión al abrir (su --version, solo si cambió)
        version, vest = v.get("version") or "", v.get("version_estado") or ""
    else:
        exe = ctx["sondas"].which(ficha.get("binario") or motor)
        version, vest = ctx["sondas"].version(motor, exe) if exe else ("", "")
    out = {"motor": motor, "nombre": nombre, "version": version, "version_estado": vest,
           "estado": _peor([f["estado"] for f in filas]), "filas": filas, "tus_mcp": _tus_mcp(motor, ctx["mcp"]),
           "fecha": _ahora_iso(ctx["ahora"])}
    if motor in SIN_PAGINA:
        out["sin_pagina"] = SIN_PAGINA[motor]
    return out


def _workspace(ctx):
    """«Workspace por dentro» en una línea: el lanzador que corren los motores (sus avisos y su servidor MCP, corridos
    de verdad), el paquete (que se arme y que el instalado sea el de esta versión) y el registro de eventos."""
    malas = []
    n, err = ctx["nucleo"]
    if not n:
        malas.append(("el MCP núcleo no contesta", err, arreglar("lanzador")))
    listo, por = ctx["paquete"]
    if not listo:
        malas.append(("el paquete no se arma", por, arreglar("paquete")))
    ok_l, por_l = ctx["lanzador"]
    if not ok_l:
        malas.append(("su lanzador no corre bien", por_l, arreglar("lanzador")))
    for fmt, (_rel, por_i) in sorted((ctx.get("instalado") or {}).items()):
        malas.append(("el paquete instalado (%s) está dañado" % fmt, por_i, arreglar("paquete")))
    _ultimo, escribe = ctx["registro"]
    if not escribe:
        malas.append(("no se puede escribir el registro de eventos", "", reportar()))
    if malas:
        return {"estado": ROTO, "glifo": GLIFO[ROTO], "texto": "Workspace por dentro: " + "; ".join(m[0] for m in malas),
                "detalle": redactar("; ".join(m[1] for m in malas if m[1]), 400), "accion": malas[0][2]}
    return {"estado": OK, "glifo": GLIFO[OK], "texto": "Workspace por dentro",
            "detalle": "su lanzador corre (el aviso niega lo prohibido y el MCP núcleo contesta con %d herramientas), "
                       "el paquete instalado es el de esta versión y el registro de eventos se escribe" % n,
            "accion": None}


def contexto(sondas=None, ahora=None):
    """Lo que se mira una vez por revisión."""
    s = sondas or Sondas()
    ahora = time.time() if ahora is None else ahora
    agentes = [tuple(a) + (("", ) * (4 - len(a))) for a in s.agentes()]
    ids = {a[0]: (a[3] or a[0].lower()) for a in agentes}

    def agentes_de(motor):
        return [(a[0], a[2]) for a in agentes if a[1] == motor and a[2] and os.path.isdir(a[2])]
    try:
        usos = s.usos() or {}
    except Exception:
        usos = {}
    try:
        mcp = s.inventario_mcp()
    except Exception:
        mcp = None
    # el lanzador que corren los motores: que esté completo y, sobre todo, que CORRA (su aviso niega lo prohibido y su
    # servidor MCP contesta), con el Python de Workspace y su archivo, como lo abre un motor
    lanzador = s.lanzador()
    try:
        prueba = s.probar_lanzador() or {}
    except Exception as e:
        prueba = {"avisos": (False, "no pude correr su lanzador: %s" % e), "mcp": (0, "no pude correr su lanzador")}
    if lanzador[0]:
        lanzador = prueba.get("avisos") or lanzador
    nucleo = prueba.get("mcp") or s.nucleo()
    proteccion = s.prohibe_boveda()
    if proteccion[0] and not (prueba.get("avisos") or (True, ""))[0]:
        proteccion = prueba["avisos"]
    if proteccion[0]:
        proteccion = _pagina_niega()
    cerebros = sorted({a[2] for a in agentes if a[2] and os.path.isdir(a[2])})
    try:
        instalado = s.paquete_instalado(cerebros) or {}
    except Exception:
        instalado = {}
    try:
        oc = s.openclaw_perfil()
    except Exception:
        oc = (None, "")
    ctx = {"sondas": s, "ahora": ahora, "nucleo": nucleo, "paquete": s.paquete(), "lanzador": lanzador,
           "registro": s.registro(), "usos": usos, "proteccion": proteccion, "agentes_de": agentes_de,
           "mcp": mcp, "saludos": {}, "ids": ids, "instalado": instalado, "openclaw": oc}
    memo = {}

    def codex_confianza(agentes_):
        clave = tuple(agentes_)
        if clave not in memo:
            memo[clave] = _codex_confianza(ctx, agentes_)
        return memo[clave]
    ctx["codex_confianza"] = codex_confianza
    return ctx


def _pagina_niega():
    """(True, '') si la capa de control de la página (la que niega sola un permiso que pide leer lo prohibido, en los
    motores que no corren avisos por su canal: Cursor, Kiro, Codex) niega leer la bóveda. En este proceso, sin leer."""
    try:
        import paths
        from arquitectura import secretos
        boveda = os.path.join(paths.state_dir(), "secrets.local")
        if secretos.motivo_permiso("Read", boveda, "read", [boveda]):
            return True, ""
        return False, "la página dejaría leer la bóveda de llaves"
    except Exception as e:
        return False, "no pude cargar lo prohibido de la página: %s: %s" % (type(e).__name__, e)


# ── la revisión al abrir: cuando un motor se actualiza (F4) ───────────────
#: Cuánto se queda la tarjeta «se actualizó» en Motores y en Conexiones (s).
CAMBIO_S = 24 * 3600


def ruta_vistas(state_dir=None):
    """«versión vista → resultado» de cada motor: <estado>/arquitectura/versiones-vistas.json."""
    return os.path.join(_dir(state_dir), "versiones-vistas.json")


def _leer_vistas(state_dir=None):
    try:
        d = estado_json.leer(ruta_vistas(state_dir), valido=_valido_vistas)
    except OSError:
        d = {}
    return d if isinstance(d, dict) else {}


def cambios_de_version(motores, sondas, state_dir=None, ahora=None):
    """Solo código, sin IA ni red: el `stat()` del programa de cada motor contra lo anotado (milisegundos). Si cambió,
    su `--version` (engine_versions lo cachea por la fecha del programa) y, si la versión es otra, un cambio.
    → ({motor: {"antes", "ahora"}}, lo anotado al día). La primera vez solo se anota (no es un cambio)."""
    from arquitectura import contrato
    vistas = _leer_vistas(state_dir)
    cambios = {}
    for m in motores:
        try:
            exe = sondas.which(contrato.ficha(m).get("binario") or m)
        except Exception:
            exe = None
        h = sondas.huella(exe) if exe else None
        if not h:
            continue
        v = vistas.get(m) or {}
        ws = _version_workspace()
        if v.get("huella") == h and v.get("version") and v.get("ws") == ws:
            continue                                 # el mismo programa (y la misma lista de probadas): nada que correr
        version, vest = sondas.version(m, exe)
        if v.get("version") and version and version != v.get("version"):
            cambios[m] = {"antes": v["version"], "ahora": version}
            v = dict(v, antes=v["version"], cambio=_ahora_iso(ahora))
        vistas[m] = dict(v, huella=h, version=version or v.get("version") or "", version_estado=vest, ws=ws)
    return cambios, vistas


def huellas_cambiadas(state_dir=None, sondas=None):
    """Los motores anotados cuyo programa cambió (solo `stat()`: milisegundos, sin correr nada)."""
    from arquitectura import contrato
    s = sondas or Sondas()
    out = []
    for m, v in _leer_vistas(state_dir).items():
        try:
            exe = s.which(contrato.ficha(m).get("binario") or m)
        except Exception:
            continue
        h = s.huella(exe) if exe else None
        if h and v.get("huella") and h != v.get("huella"):
            out.append(m)
    return out


def _tarjeta(m, v, ahora):
    """La tarjeta «se actualizó» de un motor (mientras dure CAMBIO_S), con lo que salió al revisarlo."""
    if not v.get("cambio") or ahora - _epoch(v["cambio"]) > CAMBIO_S:
        return None
    nombre, est = m["nombre"], m["estado"]
    antes, ahora_v = v.get("antes") or "", v.get("version") or ""
    if est == OK:
        # lo que de verdad se revisó: su saludo (si tiene uno gratis) y lo de Workspace; nunca un turno
        texto = "%s se actualizó a %s · revisado al abrir: %slo de Workspace sigue en su lugar (sin gastar un " \
                "mensaje)." % (nombre, ahora_v, "contesta y " if m.get("motor") in SALUDO else "")
        botones = []
    else:
        malas = [f for f in m.get("filas") or () if f.get("estado") != OK]
        que = malas[0] if malas else {}
        frase = {"avisos": "sus avisos ya no llegan", "mcp": "las herramientas de Workspace no contestan",
                 "skills": "sus skills no quedaron", "canal": "la página ya no le habla",
                 "proteccion": "lo prohibido no quedaría bloqueado"}.get(que.get("id"), "algo cambió")
        if est == TUYO:
            frase = que.get("texto") or frase
        texto = "%s se actualizó (%s → %s) y %s.%s" % (
            nombre, antes or "?", ahora_v, frase[:1].lower() + frase[1:].rstrip("."),
            " Lo demás funciona." if len(malas) < len(m.get("filas") or ()) else "")
        botones = ["otro", "reportar", "revisar"] if est == ROTO else []
    return {"antes": antes, "ahora": ahora_v, "fecha": v["cambio"], "estado": est, "texto": texto,
            "botones": botones}


def _alternativa(motores, motor):
    """Otro motor instalado que salió bien en esta revisión (para «Seguir con otro motor»), o ''."""
    preferidos = ("claude-code", "codex", "copilot", "cursor", "kiro", "opencode", "openclaw", "hermes",
                  "antigravity")
    bien = {m["motor"] for m in motores if m.get("estado") == OK and m["motor"] != motor}
    return next((m for m in preferidos if m in bien), "")


def instalados(sondas=None):
    from arquitectura import contrato
    s = sondas or Sondas()
    out = []
    for m in contrato.MOTORES:
        try:
            ficha = contrato.ficha(m)
        except Exception:
            continue
        if s.which(ficha.get("binario") or m):
            out.append(m)
    return out


def revisar(motores=None, saludar=None, sondas=None, state_dir=None, ahora=None, guardar=True, arreglar=False):
    """La revisión rápida: {fecha, workspace, motores: [...], resumen: {ok, tuyo, roto}, avisos}. `motores`: cuáles
    (por defecto, todos los instalados; los demás guardados se quedan); `saludar`: a qué motores se les vuelve a hacer
    el saludo del canal ahora (True = a todos; por defecto, solo a los que no tienen uno vigente). `arreglar` (C3-a):
    lo de Workspace que salió roto se arregla solo (arquitectura/arreglos: respaldo, arreglo, otra revisión) y queda
    un aviso de una línea con su «Deshacer» en `avisos`."""
    s = sondas or Sondas()
    ctx = contexto(s, ahora)
    previo = leer(state_dir)
    prev_m = {m.get("motor"): m for m in previo.get("motores") or ()}
    inst = instalados(s)
    cuales = [m for m in (motores or inst) if m in inst]
    cambios, vistas = cambios_de_version(inst, s, state_dir, ctx["ahora"])
    ctx["vistas"] = vistas
    for m in cambios:                                # el motor que cambió se revisa entero, con su saludo
        if m not in cuales:
            cuales.append(m)
    if cambios and saludar is not True:
        saludar = sorted(set(saludar or ()) | set(cambios))
    toca = [m for m in cuales if m in SALUDO and (
        saludar is True or (saludar not in (None, True) and m in saludar) or not vigente(
            next((f for f in (prev_m.get(m) or {}).get("filas") or () if f.get("id") == "canal"), None),
            ctx["ahora"]))]
    ctx["saludos"] = saludos_en_paralelo(s, toca) if toca else {}
    filas = []
    for m in inst:
        if m not in cuales and m in prev_m:
            filas.append(prev_m[m])
            continue
        ya = saludar is True or (saludar is not None and saludar is not True and m in saludar)
        try:
            filas.append(revisar_motor(m, ctx, prev_m.get(m), saludar_ya=ya))
        except Exception as e:                    # un motor que no se pudo revisar no tumba a los demás
            filas.append({"motor": m, "nombre": m, "version": "", "version_estado": "", "estado": ROTO,
                          "filas": [fila("mcp", ROTO, "No pude revisar este motor: %s" % redactar(e, 120),
                                         reportar(), "motor", "%s: %s" % (type(e).__name__, e))],
                          "tus_mcp": None, "fecha": _ahora_iso(ctx["ahora"])})
    for m in filas:                                  # «versión vista → resultado» y la tarjeta, si cambió
        v = vistas.get(m["motor"])
        if v is None:
            continue
        if m["motor"] in cuales:
            v["resultado"] = m["estado"]
        tarjeta = _tarjeta(m, v, ctx["ahora"])
        if tarjeta:
            if tarjeta["botones"]:
                tarjeta["alternativa"] = _alternativa(filas, m["motor"])
            m["cambio"] = tarjeta
        else:
            m.pop("cambio", None)
    if guardar:
        _guardar_vistas(vistas, state_dir)
    if cambios and guardar:
        _al_cambiar(cambios, state_dir)
    avisos = [a for a in previo.get("avisos") or () if ctx["ahora"] - _epoch(a.get("fecha")) < AVISO_S]
    if guardar:
        avisos += [{"arreglo": "", "texto": t, "deshacer": "", "ok": True, "fecha": _ahora_iso(ctx["ahora"])}
                   for t in _canario_pendientes(state_dir)]
    out = {"forma": 1, "fecha": _ahora_iso(ctx["ahora"]), "workspace": _workspace(ctx), "motores": filas,
           "workspace_version": _version_workspace(), "avisos": avisos}
    out["resumen"] = resumen(out)
    if guardar:
        _guardar(out, state_dir)
    if arreglar and guardar and not solo_leer():
        out = _arreglar_lo_de_workspace(out, state_dir, s, ctx["ahora"])
    return out


def solo_leer():
    """¿Corre dentro de la página que solo mira? Entonces revisa y enseña, pero no arregla sola."""
    return os.environ.get(SOLO_LEER) == "1"


#: Cuánto se queda un aviso de arreglo (con su Deshacer) en lo que enseña Conexiones (s), y cada cuánto se reintenta
#: solo uno que no quedó.
AVISO_S = 24 * 3600
REINTENTO_S = 3600
#: El aviso de un arreglo que corrió pero cuya fila siguió rota en la otra revisión.
NO_QUEDO = "Workspace lo intentó y sigue igual. Puedes reportarlo."


def _arreglar_lo_de_workspace(d, state_dir, sondas, ahora=None):
    """C3-a: cada pieza de Workspace que salió rota se arregla (una vez por revisión) y se vuelve a revisar. Un
    arreglo cuenta como hecho solo si su fila quedó bien en esa otra revisión: «no tronó» no basta. El que no quedó
    se marca `ok: False` (con su texto honesto) y no se repite hasta pasada REINTENTO_S: ni avisos falsos ni un
    respaldo nuevo en cada revisión."""
    from arquitectura import arreglos
    ahora = time.time() if ahora is None else ahora
    pendientes = []
    # uno que ya se intentó hace poco y no quedó no se repite en cada revisión (una vez por REINTENTO_S)
    recientes = {a.get("arreglo") for a in d.get("avisos") or ()
                 if not a.get("ok") and ahora - _epoch(a.get("fecha")) < REINTENTO_S}
    for a in [(d.get("workspace") or {}).get("accion")] + [f.get("accion") for m in d.get("motores") or ()
                                                           for f in m.get("filas") or ()]:
        if a and a.get("tipo") == "arreglar" and a.get("arreglo") not in pendientes \
                and a.get("arreglo") not in recientes:
            pendientes.append(a["arreglo"])
    if not pendientes:
        if _a_reportar(d, recientes):
            _guardar(d, state_dir)
        return d
    avisos = list(d.get("avisos") or [])
    nuevos = []
    for arreglo in pendientes:
        r = arreglos.arreglar(arreglo, state_dir=state_dir, revisar=False)
        aviso = {"arreglo": arreglo, "texto": r["texto"], "deshacer": r.get("deshacer") or "",
                 "ok": bool(r.get("ok")), "fecha": _ahora_iso(ahora)}
        avisos.append(aviso)
        nuevos.append(aviso)
    leido = leer(state_dir)
    leido["avisos"] = avisos
    _guardar(leido, state_dir)
    d = revisar(sondas=sondas, state_dir=state_dir, ahora=ahora, guardar=True, arreglar=False)
    # «corrió sin tronar» no es «quedó»: el que sigue roto en esta otra revisión cuenta como fallido
    siguen = {x for x in pendientes if arreglos._sigue_mal(d, x)}
    for a in d.get("avisos") or ():
        if any(a == n for n in nuevos) and a.get("arreglo") in siguen and a.get("ok"):
            a["ok"] = False
            a["texto"] = NO_QUEDO
    _a_reportar(d, set(pendientes) | recientes)
    _guardar(d, state_dir)
    return d


def _a_reportar(d, arreglos_):
    """Lo que siguió roto tras un arreglo (este o uno de hace menos de REINTENTO_S) ya no ofrece «Arreglar» otra
    vez: «Reportar». → True si cambió algo."""
    cambio = False
    for m in d.get("motores") or ():
        for f in m.get("filas") or ():
            a = f.get("accion") or {}
            if a.get("tipo") == "arreglar" and a.get("arreglo") in arreglos_:
                f["accion"] = reportar()
                f["texto"] += " Workspace ya intentó arreglarlo."
                cambio = True
    w = d.get("workspace") or {}
    if (w.get("accion") or {}).get("tipo") == "arreglar" and w["accion"].get("arreglo") in arreglos_:
        w["accion"] = reportar()
        cambio = True
    return cambio


def resumen(d):
    """{ok, tuyo, roto}: cuántos motores en cada estado (más «Workspace por dentro» si está roto)."""
    r = {OK: 0, TUYO: 0, ROTO: 0}
    for m in d.get("motores") or ():
        r[m.get("estado") if m.get("estado") in r else OK] += 1
    if (d.get("workspace") or {}).get("estado") == ROTO:
        r[ROTO] += 1
    return r


def _guardar_vistas(v, state_dir=None):
    try:
        p = ruta_vistas(state_dir)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with file_lock(p):
            _apartar_si_danado(p, _valido_vistas)
            estado_json.escribir(p, v)
    except Exception:
        pass


def _al_cambiar(cambios, state_dir=None):
    """Lo que pasa cuando un motor cambió de versión, además de revisarlo: en NUESTRAS máquinas, el canario (F6)."""
    try:
        from arquitectura import canario
        canario.al_cambiar(cambios, state_dir=state_dir)
    except Exception:
        pass


def _canario_pendientes(state_dir=None):
    """F6: en nuestras máquinas, el veredicto de una prueba a fondo que el canario dejó corriendo (solo código)."""
    try:
        from arquitectura import canario
        return canario.revisar_pendientes(state_dir=state_dir)
    except Exception:
        return []


def _version_workspace():
    try:
        with open(os.path.join(RAIZ_REPO, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _guardar(d, state_dir=None):
    try:
        p = ruta(state_dir)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with file_lock(p):
            _apartar_si_danado(p, _valido)
            estado_json.escribir(p, d)
        return True
    except Exception:
        return False


# ── lo que pide la página o el hub: el último, y uno nuevo en segundo plano ─
_HILO = {"t": None, "lock": threading.Lock()}


def revisando():
    t = _HILO["t"]
    return bool(t and t.is_alive())


def en_fondo(**kw):
    """Corre `revisar(**kw)` en un hilo (uno a la vez en este proceso). → True si empezó. Nunca en la suite (un hilo
    que sobrevive a su prueba vería el HOME de verdad)."""
    if os.environ.get(SIN_SONDEOS):
        return False
    with _HILO["lock"]:
        if revisando():
            return False

        def correr():
            try:
                revisar(**kw)
            except Exception:
                pass
        t = threading.Thread(target=correr, name="workspace-chequeo", daemon=True)
        _HILO["t"] = t
        t.start()
        return True


def vista(state_dir=None, refrescar=True, ahora=None):
    """Lo que enseñan Conexiones y la línea de Motores: el último resultado guardado, con `revisando` y `hace`. Si
    no hay, si tiene más de FRESCO_S o si Workspace cambió de versión, pide uno nuevo en segundo plano (la primera
    vez, el saludo de todos)."""
    d = leer(state_dir)
    ahora = time.time() if ahora is None else ahora
    viejo = not d or ahora - _epoch(d.get("fecha")) > FRESCO_S or d.get("workspace_version") != _version_workspace()
    if os.environ.get(SIN_SONDEOS):
        refrescar = False
    arreglar = not solo_leer()                       # la página que solo mira no arregla sola
    if refrescar and viejo:
        en_fondo(state_dir=state_dir, arreglar=arreglar,
                 saludar=(True if not d or d.get("workspace_version") != _version_workspace() else None))
    elif refrescar:                                  # la revisión al abrir: un motor que cambió, enseguida
        cambiados = huellas_cambiadas(state_dir)
        if cambiados:
            en_fondo(state_dir=state_dir, arreglar=arreglar, motores=cambiados, saludar=cambiados)
    out = dict(d) if d else {"forma": 1, "fecha": None, "workspace": None, "motores": [],
                             "resumen": {OK: 0, TUYO: 0, ROTO: 0}}
    out["revisando"] = revisando()
    out["hace"] = hace(out.get("fecha"), ahora) if out.get("fecha") else ""
    out["dev"] = es_dev()                            # la matriz de laboratorio, solo en nuestras máquinas
    if out["dev"]:
        out["prueba_a_fondo"] = prueba_a_fondo()
    return out


def prueba_a_fondo():
    """F6: en nuestras máquinas, si la prueba a fondo (la del canario o «Verificar» del laboratorio) está corriendo,
    su avance en una línea para el hub y la página («Prueba a fondo: Copilot por la terminal… 2 de 4»); '' si no."""
    try:
        from arquitectura import verificacion
        e = verificacion.estado()
    except Exception:
        return ""
    if not e.get("corriendo"):
        return ""
    p = e.get("progreso") or {}
    hecho, total = int(p.get("hecho") or 0), int(p.get("total") or 0)
    return "Prueba a fondo (canario): %s%s" % ((p.get("actual") or "preparando") + "…",
                                               (" %d de %d" % (min(hecho + 1, total), total)) if total else "")


_DEV = {}


def es_dev():
    """¿Una de nuestras máquinas de desarrollo? (dev_tui.is_dev, una vez por proceso: corre git)."""
    if "v" not in _DEV:
        try:
            import dev_tui
            _DEV["v"] = bool(dev_tui.is_dev())
        except Exception:
            _DEV["v"] = False
    return _DEV["v"]


def al_abrir(espera=8.0):
    """La revisión al abrir la página o el hub (el servidor local, al arrancar): unos segundos después (para no
    estorbar al arranque), en segundo plano, lo mismo que pide Conexiones. Nunca en la suite."""
    if os.environ.get(SIN_SONDEOS):
        return False
    t = threading.Timer(espera, lambda: vista())
    t.daemon = True
    t.start()
    return True


def linea(d):
    """La línea de Motores: (estado, texto) — «✓ todo responde · hace 5 min», «⚠ 1 cosa por hacer», «✗ 1 rota»
    o «revisando…». «Responde», no «todo en orden»: el chequeo rápido revisa que lo de Workspace esté y que cada motor
    conteste a su saludo (sin gastar un mensaje), no que un turno funcione; y dice cuándo fue."""
    if not d or not d.get("motores") and not d.get("workspace"):
        return "", "revisando…"
    rotas = sum(1 for m in d.get("motores") or () for f in m.get("filas") or () if f.get("estado") == ROTO)
    if (d.get("workspace") or {}).get("estado") == ROTO:
        rotas += 1
    tuyas = sum(1 for m in d.get("motores") or () for f in m.get("filas") or () if f.get("estado") == TUYO)
    if rotas:
        return ROTO, "✗ %d %s" % (rotas, "rota" if rotas == 1 else "rotas")
    if tuyas:
        return TUYO, "⚠ %d %s" % (tuyas, "cosa por hacer" if tuyas == 1 else "cosas por hacer")
    return OK, "✓ todo responde" + ((" · " + d["hace"]) if d.get("hace") else "")


def main(argv=None):
    """`python3 -m arquitectura.chequeo [--json] [--sin-saludo] [--no-guardar]`: la revisión rápida, en la terminal."""
    args = list(sys.argv[1:] if argv is None else argv)
    d = revisar(saludar=None if "--sin-saludo" in args else True, guardar="--no-guardar" not in args)
    if "--json" in args:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0
    w = d["workspace"]
    print("%s %s · %s" % (w["glifo"], w["texto"], w["detalle"]))
    for m in d["motores"]:
        print("\n%s %s%s" % (GLIFO[m["estado"]], m["nombre"], ("  " + m["version"]) if m.get("version") else ""))
        for f in m["filas"]:
            acc = (" → " + f["accion"]["etiqueta"]) if f.get("accion") else ""
            print("   %s %-34s %s%s" % (f["glifo"], f["nombre"], f["texto"], acc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
