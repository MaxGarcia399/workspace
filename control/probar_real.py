#!/usr/bin/env python3
"""WORKSPACE · control/probar_real.py — la capa de control contra los motores
REALES (fuera del sandbox), cada uno en una carpeta temporal nueva, con el
binario oficial y el login del socio. No toca configs ni tokens del motor.

    python3 control/probar_real.py                        # los motores por defecto
    python3 control/probar_real.py --motores copilot,codex --salida /tmp/probar

Por motor, en orden: abrir → «responde: listo» → dos permisos que se NIEGAN
(escribir un archivo y un comando de terminal: no debe quedar ninguno) →
parar a medias → cerrar y retomar la misma conversación → uso. Guarda en
--salida: informe.json, y por motor help.txt (el --help de lo que usa),
trafico.jsonl (el tráfico crudo) y serve.log (el servidor que abre el
probador), con claves y tokens tapados, para ajustar los conectores donde el
motor real no hable como el falso.

Servidores: OpenCode y Hermes necesitan su servidor. Si no se pasa
--opencode-url / --hermes-url, el probador abre uno propio en la carpeta
temporal y lo cierra al final: `opencode serve` con una clave que pone el
probador (OPENCODE_SERVER_PASSWORD; si el servidor imprime otra, se usa la
que imprime: es la clave local de ESE servidor) y `hermes --profile
workspace serve --isolated` (solo del perfil; jamás `serve --stop`, que
apaga todos). OpenClaw enciende el gateway del perfil como una pestaña.

Antigravity (`agy acp`) no corre por defecto: con plan personal, sus términos
no permiten usarlo dentro de otra app. Pídelo explícito si la cuenta es de
empresa. OpenClaw por su gateway (WebSocket) necesita el token del gateway del
perfil: pásalo por una variable de entorno (--openclaw-token-env); sin él se
prueba solo el puente `openclaw acp`."""
import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import control  # noqa: E402
from control.base import ErrorControl  # noqa: E402
from control.canal import resolver  # noqa: E402

POR_DEFECTO = ["claude-code", "copilot", "cursor", "kiro", "codex", "opencode", "hermes",
               "hermes-acp", "openclaw", "openclaw-acp"]
AYUDAS = {
    "claude-code": [["claude", "--version"]],
    "copilot": [["copilot", "--version"], ["copilot", "--help"]],
    "cursor": [["cursor-agent", "--version"], ["cursor-agent", "acp", "--help"]],
    "kiro": [["kiro-cli", "--version"], ["kiro-cli", "acp", "--help"]],
    "antigravity": [["agy", "--version"], ["agy", "acp", "--help"]],
    "codex": [["codex", "--version"], ["codex", "app-server", "--help"]],
    "opencode": [["opencode", "--version"], ["opencode", "serve", "--help"],
                 ["opencode", "service", "--help"]],
    "hermes": [["hermes", "--version"], ["hermes", "serve", "--help"]],
    "hermes-acp": [["hermes", "acp", "--help"]],
    "openclaw": [["openclaw", "--version"], ["openclaw", "gateway", "--help"]],
    "openclaw-acp": [["openclaw", "acp", "--help"]],
}
#: Variables para que ningún motor se actualice durante la prueba.
SIN_ACTUALIZAR = {"DISABLE_AUTOUPDATER": "1"}
_TAPAR = re.compile(r'("(?:token|password|apiKey|api_key|secret|authorization)"\s*:\s*")[^"]*(")', re.I)
#: En los registros de los servidores: «password X», «token=X», «Bearer X», «Basic X».
_TAPAR_LINEA = re.compile(r"((?:password|token|secret|bearer|basic)\b[\s:=]+)\S+", re.I)

PASOS = {
    "listo": "Responde solo con la palabra: listo",
    "permiso_escribir": "Crea en esta carpeta el archivo prueba.txt con el texto hola. "
                        "No preguntes nada más.",
    "permiso_comando": "Corre en la terminal el comando `touch prueba2.txt` (no lo hagas de otra "
                       "forma) y dime qué pasó.",
    "parar": "Cuenta del 1 al 300, un número por línea, sin usar herramientas.",
    "retomar": "¿Qué palabra respondiste en tu primera respuesta? Contesta solo esa palabra.",
    "reconectar": "Cuenta del 1 al 60, un número por línea, sin usar herramientas.",
}
#: B2 · el paso «reconectar» (OpenCode): cuánto quedan cortados sus eventos a media respuesta (s). Lo normal es que el
#: turno termine en el hueco y su session.idle se pierda, como en un corte de verdad.
HUECO_S = 20.0
#: Donde un servidor suele dar su especificación OpenAPI (`opencode api` la usa; su --help no dice dónde).
RUTAS_OPENAPI = ("/doc", "/api/doc", "/openapi.json", "/api/openapi.json")


def tapar(texto):
    """Tráfico JSON: solo los valores de claves secretas (no se rompe el JSON)."""
    return _TAPAR.sub(r"\1***\2", texto)


def tapar_log(texto):
    """Registros de servidores y mensajes de error: además, «password X», «Bearer X»…"""
    return _TAPAR_LINEA.sub(r"\1***", tapar(texto))


def _ayuda(motor, carpeta):
    with open(os.path.join(carpeta, "help.txt"), "w", encoding="utf-8") as fh:
        for cmd in AYUDAS.get(motor, []):
            fh.write("$ %s\n" % " ".join(cmd))
            try:
                r = subprocess.run(resolver(cmd), capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=30, env=dict(os.environ, **SIN_ACTUALIZAR))
                fh.write((r.stdout + r.stderr)[-20000:] + "\n(rc=%s)\n\n" % r.returncode)
            except (OSError, subprocess.TimeoutExpired) as e:
                fh.write("(no corrió: %s)\n\n" % e)


def _puerto_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _escucha(puerto, timeout=0.5):
    try:
        socket.create_connection(("127.0.0.1", puerto), timeout=timeout).close()
        return True
    except OSError:
        return False


class Servidor:
    """Un servidor que abre el probador: su salida va TAPADA a serve.log y se
    buscan en ella `patrones` ({nombre: regex con un grupo})."""

    def __init__(self, cmd, cwd, log, env=None, patrones=None):
        self.encontrado = {}
        self.limpiar = []                       # carpetas que se borran al cerrar (el token propio)
        self._patrones = {k: re.compile(v) for k, v in (patrones or {}).items()}
        self._log = open(log, "w", encoding="utf-8")
        self.proc = subprocess.Popen(resolver(cmd), cwd=cwd, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        for crudo in iter(self.proc.stdout.readline, b""):
            linea = crudo.decode("utf-8", "replace")
            for k, rx in self._patrones.items():
                m = rx.search(linea)
                if m and k not in self.encontrado:
                    self.encontrado[k] = m.group(1)
            try:
                self._log.write(tapar_log(linea))
                self._log.flush()
            except ValueError:                  # ya se cerró el registro (cerrar)
                return

    def esperar(self, condicion, espera):
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            if condicion():
                return True
            if self.proc.poll() is not None:
                return False
            time.sleep(0.25)
        return False

    def cerrar(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if not self._log.closed:
            self._log.close()
        for d in self.limpiar:
            shutil.rmtree(d, ignore_errors=True)


def _resumen(evs):
    tipos = {}
    for e in evs:
        tipos[e["tipo"]] = tipos.get(e["tipo"], 0) + 1
    fin = next((e for e in reversed(evs) if e["tipo"] == "terminado"), None)
    return {"tipos": tipos, "texto": "".join(e.get("texto", "") for e in evs if e["tipo"] == "texto")[:500],
            "terminado": fin.get("motivo") if fin else None,
            "errores": [e.get("mensaje") for e in evs if e["tipo"] == "error"][:5],
            "permisos": [{"herramienta": e.get("herramienta"), "opciones": e.get("opciones")}
                         for e in evs if e["tipo"] == "permiso"]}


def _turno(c, texto, tope):
    try:
        return c.turno(texto, timeout=tope, al_permiso=lambda e: "negar")
    except ErrorControl as e:
        return [{"tipo": "error", "mensaje": str(e)}, {"tipo": "terminado", "motivo": "error"}]


def _parar(c, tope):
    try:
        c.mandar(PASOS["parar"])
    except ErrorControl as e:
        return {"ok": False, "error": str(e)}
    evs, t0, parado_en = [], time.monotonic(), None
    while time.monotonic() - t0 < tope:
        ev = c.siguiente(1)
        if ev is None:
            continue
        evs.append(ev)
        if ev["tipo"] == "permiso":
            c.responder_permiso(ev["id"], "negar")
        if ev["tipo"] == "texto" and parado_en is None:
            parado_en = time.monotonic()
            c.parar()
        if ev["tipo"] == "terminado":
            break
    r = _resumen(evs)
    r["ok"] = r["terminado"] == "parado"
    r["segundos_hasta_terminado"] = round(time.monotonic() - parado_en, 2) if parado_en else None
    return r


def _reconectar(c, tope):
    """B2 (OpenCode): con la sesión quieta, lo que dice su servidor de ella (estado_sesion: «libre» si se reconoce
    su forma; sus respuestas quedan en el tráfico). Después, a media respuesta, sus eventos se cortan HUECO_S: el
    turno tiene que cerrar igual. `resincronizado`: lo cerró la consulta al volver (su idle cayó en el hueco)."""
    r = {"estado_quieta": c.estado_sesion()}
    try:
        c.mandar(PASOS["reconectar"])
    except ErrorControl as e:
        return dict(r, ok=False, error=tapar_log(str(e)))
    evs, t0, cortado = [], time.monotonic(), None
    while time.monotonic() - t0 < tope:
        ev = c.siguiente(1)
        if ev is None:
            continue
        evs.append(ev)
        if ev["tipo"] == "permiso":
            c.responder_permiso(ev["id"], "negar")
        if ev["tipo"] == "texto" and cortado is None:
            cortado = time.monotonic()
            c.cortar_eventos(HUECO_S)
        if ev["tipo"] == "terminado":
            break
    fin = next((e for e in reversed(evs) if e["tipo"] == "terminado"), {})
    r.update(_resumen(evs), resincronizado=bool(fin.get("resincronizado")),
             segundos_desde_el_corte=round(time.monotonic() - cortado, 2) if cortado else None)
    r["ok"] = r["terminado"] == "fin"
    if r["terminado"] is None:                           # no cerró: que no quede trabajando para lo que sigue
        c.parar()
        limite = time.monotonic() + 15
        while time.monotonic() < limite and c.estado() != "listo":
            time.sleep(0.25)
    return r


def _especificacion(c, carpeta):
    """La especificación OpenAPI de su servidor, si la da en alguna de RUTAS_OPENAPI: se guarda en openapi.json
    (para ver las rutas y la forma del estado de una sesión). → la ruta que contestó, o None."""
    import http.client
    for ruta in RUTAS_OPENAPI:
        try:
            conn = c._conexion(15)                 # la del conector: su servidor (y, en las pruebas, su falso)
            try:
                conn.request("GET", ruta, headers=dict({"Accept": "application/json"}, **c._cabeceras))
                resp = conn.getresponse()
                crudo = resp.read()
            finally:
                conn.close()
            if resp.status == 200 and crudo.lstrip()[:1] == b"{":
                json.loads(crudo)
                with open(os.path.join(carpeta, "openapi.json"), "wb") as fh:
                    fh.write(crudo)
                return ruta
        except (OSError, ValueError, http.client.HTTPException):
            continue
    return None


def _abrir_servidor(motor, args, cwd, carpeta, informe):
    """OpenCode y Hermes: el servidor que el probador abre (si no se pasó uno).
    Devuelve (Servidor|None, opciones extra para el conector)."""
    env = dict(os.environ, **SIN_ACTUALIZAR)
    log = os.path.join(carpeta, "serve.log")
    if motor == "opencode" and not args.opencode_url:
        # Con «preguntar» (punto A): la config de SESIÓN que pide permiso para editar y para
        # comandos. Primero la forma v2; si `serve` no arranca con ella, la v1. Nunca global.
        from control.opencode import PREGUNTAR, comando_servidor, entorno_servidor
        clave = secrets.token_urlsafe(24)
        formas = list(PREGUNTAR) if args.permisos_opencode == "preguntar" else [None]
        for forma in formas:
            puerto = _puerto_libre()
            env_s = entorno_servidor(args.permisos_opencode, dict(env, OPENCODE_SERVER_PASSWORD=clave),
                                     forma=forma or "v2")
            s = Servidor(comando_servidor(puerto), cwd,
                         log if forma in (None, "v2") else log.replace(".log", "-%s.log" % forma),
                         env=env_s, patrones={"url": r"listening on (http://\S+)",
                                              "clave": r"server password (\S+)"})
            listo = s.esperar(lambda: "url" in s.encontrado or _escucha(puerto), args.espera_servidor)
            informe["servidor"] = {"listo": listo, "clave_propia_respetada":
                                   s.encontrado.get("clave") in (None, clave),
                                   "permisos": args.permisos_opencode, "forma_config": forma}
            if listo or forma == formas[-1]:
                return s, {"url": s.encontrado.get("url", "http://127.0.0.1:%d" % puerto),
                           "clave": s.encontrado.get("clave") or clave}
            s.cerrar()
    if motor == "opencode":
        return None, {"url": args.opencode_url,
                      "clave": os.environ.get(args.opencode_clave_env or "", "") or None}
    if motor == "hermes" and not args.hermes_url:
        return _hermes_propio(args, cwd, carpeta, env, informe)
    if motor == "hermes":
        return None, {"url": args.hermes_url}
    return None, {}


#: Los saludos al WebSocket de `hermes serve` que se prueban, en orden. El token de
#: un solo uso (`--ssh-session-token-file`) ya no: la 0.22.5 lo exige «under the
#: desktop-ssh directory», dentro del HOME de Hermes (probador real, 18-nov).
SALUDOS_HERMES = [
    ("origen+subprotocolo", {}),
    ("subprotocolo", {"origen": False}),
    ("origen", {"subprotocolo": None}),
    ("nada", {"origen": False, "subprotocolo": None}),
]


def _hermes_propio(args, cwd, carpeta, env, informe):
    """`hermes serve --isolated` del perfil en un puerto libre; devuelve los
    saludos a probar (SALUDOS_HERMES), en orden."""
    from control.hermes import comando_servidor, entorno_servidor, url_servidor
    puerto = _puerto_libre()
    s = Servidor(comando_servidor(puerto), cwd, os.path.join(carpeta, "serve.log"),
                 env=entorno_servidor(env))
    listo = s.esperar(lambda: _escucha(puerto), args.espera_servidor)
    informe.setdefault("servidor", {})["listo"] = listo
    url = url_servidor(puerto)
    if not listo:
        s.cerrar()
        return None, {"url": url}
    return s, [(nombre, dict(op, url=url)) for nombre, op in SALUDOS_HERMES]


def opciones_de(motor, cwd, args, grabar, extra):
    op = {"cwd": cwd, "grabar": grabar}
    env = dict(os.environ, **SIN_ACTUALIZAR)
    if motor == "claude-code":
        op.update(env=env, candados=cwd)
    elif motor in ("copilot", "cursor", "kiro", "antigravity", "openclaw-acp", "hermes-acp", "codex"):
        op["env"] = env
    elif motor == "openclaw":
        if args.openclaw_url:
            op["url"] = args.openclaw_url
        op["token"] = os.environ.get(args.openclaw_token_env or "", "") or None
    op.update(extra)
    return op


def _permiso(c, motor, paso, cwd, archivo, tope):
    r = _resumen(_turno(c, PASOS[paso], tope))
    r["archivo_creado"] = os.path.exists(os.path.join(cwd, archivo))
    # arq-control8: el turno tiene que CERRAR. En el probador real 7, OpenCode preguntó,
    # no aceptó la respuesta y el turno quedó abierto; el paso salía ✓ igual y la falla
    # aparecía después, en el paso siguiente («está trabajando»).
    r["cerro_turno"] = r["terminado"] is not None
    clase = paso.split("_", 1)[1]                        # escribir | comando
    if clase in control.VIAS[motor].get("sin_preguntar", ()):
        r["ok"] = None                                   # no aplica: así es el motor
        r["nota"] = "%s no pide permiso para %s (no tiene «preguntar»)" % (motor, clase)
    else:
        r["ok"] = bool(r["permisos"]) and not r["archivo_creado"] and r["cerro_turno"]
    return r


def probar(motor, args, salida):
    carpeta = os.path.join(salida, motor)
    os.makedirs(carpeta, exist_ok=True)
    _ayuda(motor, carpeta)
    cwd = tempfile.mkdtemp(prefix="ws-probar-%s-" % motor)
    with open(os.path.join(cwd, "notas.md"), "w", encoding="utf-8") as fh:
        fh.write("# Carpeta de prueba de la capa de control\n")
    traf = open(os.path.join(carpeta, "trafico.jsonl"), "a", encoding="utf-8")

    def grabar(direccion, texto):
        traf.write(json.dumps({"t": round(time.time(), 3), "d": direccion, "m": tapar(texto)},
                              ensure_ascii=False) + "\n")
        traf.flush()
    informe = {"motor": motor, "cwd": cwd, "via": control.VIAS[motor]["via"], "pasos": {},
               "solo_mirar": not control.puede_escribir(motor)}
    servidor = None
    try:
        if motor == "openclaw" and not os.environ.get(args.openclaw_token_env or "", ""):
            informe["omitido"] = "sin --openclaw-token-env: se probó solo openclaw-acp"
            return informe
        servidor, extra = _abrir_servidor(motor, args, cwd, carpeta, informe)
        # Uno o varios saludos a probar en orden (Hermes); con el conector de verdad,
        # sin sondeos previos que gasten un token de un solo uso.
        candidatos = extra if isinstance(extra, list) else [("", extra)]
        t0 = time.monotonic()
        c, sid, error, intentos = None, None, "", []
        for nombre, op in candidatos:
            prueba = control.conector(motor, **opciones_de(motor, cwd, args, grabar, op))
            try:
                sid = prueba.abrir()
            except ErrorControl as e:
                error = tapar_log(str(e))
                intentos.append({"variante": nombre, "abrio": False, "error": error})
                continue
            c, extra = prueba, op
            intentos.append({"variante": nombre, "abrio": True})
            break
        if len(candidatos) > 1:
            informe.setdefault("servidor", {})["intentos"] = intentos
        if c is None:
            informe["pasos"]["abrir"] = {"ok": False, "error": error}
            return informe
        informe["pasos"]["abrir"] = {"ok": True, "sesion": sid, "segundos": round(time.monotonic() - t0, 2)}
        r = _resumen(_turno(c, PASOS["listo"], args.tope))
        r["ok"] = r["terminado"] == "fin" and "listo" in r["texto"].lower()
        informe["pasos"]["mandar"] = r
        informe["pasos"]["permiso_escribir"] = _permiso(c, motor, "permiso_escribir", cwd, "prueba.txt",
                                                        args.tope)
        informe["pasos"]["permiso_comando"] = _permiso(c, motor, "permiso_comando", cwd, "prueba2.txt",
                                                       args.tope)
        informe["pasos"]["parar"] = _parar(c, args.tope)
        if motor == "opencode":                          # B2: sus eventos se cortan y vuelven
            informe["openapi"] = _especificacion(c, carpeta)
            informe["pasos"]["reconectar"] = _reconectar(c, args.tope)
        informe["uso"] = c.uso()
        c.cerrar()
        c2 = control.conector(motor, **opciones_de(motor, cwd, args, grabar, extra))
        try:
            c2.abrir(sid)
            r = _resumen(_turno(c2, PASOS["retomar"], args.tope))
            r["ok"] = "listo" in r["texto"].lower()
            informe["pasos"]["retomar"] = r
        except ErrorControl as e:
            informe["pasos"]["retomar"] = {"ok": False, "error": tapar_log(str(e))}
        finally:
            c2.cerrar()
    except Exception as e:                                # el informe sale igual
        informe["excepcion"] = tapar_log("%s: %s" % (type(e).__name__, e))
    finally:
        traf.close()
        if servidor is not None:
            servidor.cerrar()
        if not args.conservar:
            shutil.rmtree(cwd, ignore_errors=True)
    return informe


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--motores", default=",".join(POR_DEFECTO))
    ap.add_argument("--salida", default=os.path.join(tempfile.gettempdir(), "ws-probar-control"))
    ap.add_argument("--tope", type=float, default=180, help="segundos por paso")
    ap.add_argument("--opencode-url", help="un servidor de OpenCode ya abierto (si no, el probador "
                                           "abre `opencode serve` en la carpeta temporal)")
    ap.add_argument("--opencode-clave-env", help="variable de entorno con la clave de ese servidor")
    ap.add_argument("--permisos-opencode", choices=("preguntar", "como-este"), default="preguntar",
                    help="con qué permisos abre el probador su `opencode serve`: «preguntar» (config "
                         "de sesión, el nivel de Workspace) o su config tal cual")
    ap.add_argument("--hermes-url", help="un servidor de Hermes ya abierto (ws://…/api/ws; si no, el "
                                         "probador abre `hermes serve --isolated`)")
    ap.add_argument("--espera-servidor", type=float, default=90,
                    help="segundos máximos para que el servidor propio escuche")
    ap.add_argument("--openclaw-url", help="por defecto, el gateway del perfil de Workspace")
    ap.add_argument("--openclaw-token-env", help="variable de entorno con el token del gateway")
    ap.add_argument("--conservar", action="store_true", help="no borrar las carpetas temporales")
    args = ap.parse_args(argv)
    motores = [m.strip() for m in args.motores.split(",") if m.strip()]
    for m in motores:
        if m not in control.VIAS:
            ap.error("motor desconocido: %s" % m)
        if control.VIAS[m].get("aviso"):
            print("· %s: %s" % (m, control.VIAS[m]["aviso"]))
    os.makedirs(args.salida, exist_ok=True)
    informes = []
    for m in motores:
        print("→ %s …" % m, flush=True)
        inf = probar(m, args, args.salida)
        informes.append(inf)
        pasos = inf.get("pasos", {})
        linea = " · ".join("%s %s" % (k, {True: "✓", None: "—"}.get(v.get("ok"), "✗"))
                           for k, v in pasos.items())
        print("  %s%s" % (linea or "", (" · " + (inf.get("omitido") or inf.get("excepcion")))
                          if inf.get("omitido") or inf.get("excepcion") else ""), flush=True)
    with open(os.path.join(args.salida, "informe.json"), "w", encoding="utf-8") as fh:
        json.dump(informes, fh, ensure_ascii=False, indent=2)
    print("informe: %s" % os.path.join(args.salida, "informe.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
