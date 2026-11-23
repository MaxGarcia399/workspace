"""WORKSPACE · control/opencode.py — OpenCode por su servidor oficial (API
HTTP v2 + eventos SSE). El servicio es dueño de las sesiones y la terminal es
un cliente más: la página escribe y mira la MISMA conversación que la TUI.

Rutas (v2, bajo /api; ver RUTAS): crear sesión, prompt, interrupt, responder
permiso y GET /api/event (SSE). Eventos que se usan: session.text.delta,
session.tool.called/success/failed, permission.asked/replied, session.idle,
session.execution.succeeded/failed, session.usage.updated.

La dirección del servidor: `url` (opencode serve --port N; el servicio
compartido no documenta su puerto).

Autenticación: VERIFICADO con el probador real (v2.1.4, 17-nov): `opencode
serve` arranca con «server password …» y sin ella no abre /api/event. Quien
abre el servidor le pasa la clave (`clave`, y `usuario`, por defecto
«opencode») y va como HTTP Basic, como OPENCODE_SERVER_PASSWORD en su doc de
servidor; o la cabecera que haga falta (`cabeceras`). Es la clave LOCAL de ese
servidor, no el login del socio; este módulo no la guarda ni la busca. Si el
servidor dice que no, el error trae el estado HTTP y su WWW-Authenticate.

F4 · `compartida=True`: el servidor es el de SU TERMINAL (control/compartido.py) y la
sesión, la de la TUI. Entonces el conector sigue también los turnos que empiezan en la
terminal: VERIFICADO en el tráfico real del probador 7 (v2.1.4, líneas 18-19 y 34-35),
cada mensaje llega como `session.inbox.enqueued` ({item: {type: "user", payload: {text}}})
y luego `session.execution.started`. Uno que llega sin turno nuestro en curso abre un turno
AJENO (Conector._empezar_ajeno: el evento `entrada` con su texto) y cierra con su
`terminado` como cualquiera; sus permisos se contestan desde la página igual.

B2 · si los eventos se cortan y vuelven (LectorSSE reconecta sin Last-Event-ID), lo que pasó
en el hueco no llega. Si ahí cayó su session.idle, el turno quedaba «trabajando» hasta Parar.
Ahora, al volver con un turno en curso, se le pregunta a su servidor (estado_sesion) y el
turno se cierra si quedó libre (`terminado` con `resincronizado`). El texto que cayó en el
hueco no se recupera. La forma de su respuesta está SIN VERIFICAR (ver RUTAS["estado"] y
estado_de); si no se reconoce, el turno sigue como antes."""
import base64
import http.client
import json
import os
import threading
import time
from urllib.parse import quote, urlencode, urlsplit

from control.base import INTERRUMPIDO, Conector, ErrorControl, campo, corto, pregunta_nativa
from control.sse import LectorSSE, abrir_tcp

URL = "http://127.0.0.1:4096"
RUTAS = {
    "crear": "/api/session",
    "sesion": "/api/session/{id}",
    "prompt": "/api/session/{id}/prompt",
    "parar": "/api/session/{id}/interrupt",
    "permiso": "/api/session/{id}/permission/{pid}/reply",
    "eventos": "/api/event",
    # B2 · SIN VERIFICAR: el estado de las sesiones, la ruta de su API v1 (/session/status: {sesión: {type}})
    # bajo /api. La de la sesión («sesion») sí está verificada; lo que dice de su estado, no. Las dos
    # respuestas quedan en el tráfico del probador real (paso «reconectar»).
    "estado": "/api/session/status",
}
#: B2 · al volver sus eventos tras un corte: la pausa entre las dos consultas de su estado (s).
PAUSA_RESYNC = 1.0
_LIBRE = ("idle", "done", "completed", "ready")
_OCUPADA = ("busy", "running", "working", "retry", "pending", "executing", "started")


def estado_de(x):
    """«libre» | «ocupada» | None de lo que su servidor dice de una sesión: su `status` o `state` (texto, o
    {type}) o `busy`/`idle` (booleanos). La forma de OpenCode 2 está SIN VERIFICAR (B2): lo que no se
    reconoce da None, y con None no se cierra nada."""
    if not isinstance(x, dict):
        return None
    for k in ("status", "state"):
        v = x.get(k)
        if isinstance(v, dict):
            v = campo(v, "type", "status", "state")
        if isinstance(v, str):
            v = v.strip().lower()
            if v in _LIBRE:
                return "libre"
            if v in _OCUPADA:
                return "ocupada"
    for k, libre in (("busy", False), ("idle", True)):
        if isinstance(x.get(k), bool):
            return "libre" if x[k] == libre else "ocupada"
    return None
#: B03 (cacería 19-nov): su «always» guarda el patrón de `save` del permiso («*» para editar, «date *», «touch *»…),
#: más amplio que lo que muestra la tarjeta, PARA SIEMPRE en su base, atado al proyecto git del cerebro (~/Workspace,
#: el de todos los cerebros): le gana a «Preguntarme todo», vale en sesiones y servidores nuevos y desde aquí no se ve
#: ni se revoca (tests/control_falsos/opencode_real7.json: edit de prueba.txt con save ["*"]). La página no ofrece
#: «Siempre» en OpenCode y nunca manda «always»: una respuesta que no sea permitir (una vez) se contesta «reject».
_RESPUESTA = {"permitir": "once", "negar": "reject"}
#: Lo que la tarjeta de un permiso de OpenCode ofrece (B03: sin «Siempre»).
OPCIONES_PERMISO = ("permitir", "negar")
#: La clave de la respuesta a un permiso. VERIFICADO con el probador real (v2.1.4, 18-nov):
#: con {"reply": "reject"} contestó 400 «Missing key at ["decision"]» y el permiso quedó
#: pendiente para siempre. Los VALORES (once/always/reject, los de su doc v1) siguen SIN
#: VERIFICAR: si no los acepta, el error dice lo que contestó y el turno se cierra igual.
CLAVE_RESPUESTA = "decision"


#: «Preguntar» como config de SESIÓN de `opencode serve` (punto A, 18-nov: con su config de
#: siempre, OpenCode no pidió permiso). Va por la variable OPENCODE_CONFIG_CONTENT: una capa
#: más de config solo para ESE proceso; nada se escribe en la config global ni en el cerebro.
#: La forma exacta no está verificada aquí (sin su doc ni su --help, que no la nombra): «v2»
#: sale de su doc v2 según la investigación C (reglas {action, resource, effect}, acciones
#: edit y shell); «v1» es la de su doc de servidor v1 (permission: {edit, bash}). El
#: probador abre con v2 y, si `serve` no la acepta, con v1, y dice cuál quedó.
PREGUNTAR = {
    "v2": {"permissions": [{"action": "edit", "resource": "*", "effect": "ask"},
                           {"action": "shell", "resource": "*", "effect": "ask"}]},
    "v1": {"permission": {"edit": "ask", "bash": "ask"}},
}
VARIABLE_CONFIG = "OPENCODE_CONFIG_CONTENT"


def comando_servidor(puerto):
    """`opencode serve` en 127.0.0.1:<puerto> (su --help: --hostname, --port)."""
    from control.canal import resolver
    return resolver(["opencode", "serve", "--port", str(int(puerto)), "--hostname", "127.0.0.1"])


def entorno_servidor(permisos=None, base=None, forma="v2", pestana=None):
    """El entorno con el que se abre `opencode serve`: sin las variables de
    identidad de otra pestaña y con las de `pestana` (punto F, entorno.py). Con
    permisos «preguntar» (el nivel elegido en Workspace), además la config de
    sesión que hace preguntar antes de editar y antes de correr comandos."""
    from control import entorno
    env = entorno.para_motor(base, pestana, "opencode")
    if permisos == "preguntar":
        env[VARIABLE_CONFIG] = json.dumps(PREGUNTAR[forma], separators=(",", ":"))
    return env


#: B31 · recién encendido, `opencode serve` contesta 503 un momento ({"code": "service_starting"}, también en
#: /api/event; VERIFICADO en caja negra y en el tráfico de la reverificación, v2.1.4, 19-nov). Antes, ese 503 al
#: retomar hacía que la página abriera otra conversación sin avisar (y la terminal, una TUI sin su conversación).
#: Lo que se espera a que arranque (s) y la pausa entre intentos.
ARRANQUE_S = 20
PAUSA_ARRANQUE = 0.5


def arrancando(estado, fallo=""):
    """¿Su servidor dice que aún está arrancando? Un 503 (estado, o en el texto del fallo de sus eventos)."""
    return estado == 503 or "HTTP 503" in str(fallo or "")


#: Lo que se espera al export de una sesión (s).
ESPERA_EXPORT = 30


def historial(url, clave, sesion, cwd=None, correr=None, timeout=ESPERA_EXPORT):
    """F4c · lo que ya había en la conversación `sesion` de ESE servidor, como turnos
    ([{"rol": "yo"|"agente", "texto", "t"}], ver turnos_del_export): por el export OFICIAL,
    `opencode session export --server <url> <sesion>` (su --help 2.1.4), con la clave local
    en OPENCODE_SERVER_PASSWORD como la TUI (probado en real con F4b). Levanta ErrorControl
    si no salió."""
    import subprocess
    from control.canal import opciones_proceso, resolver
    cmd = resolver(["opencode", "session", "export", "--server", url, str(sesion)])
    env = dict(os.environ, DISABLE_AUTOUPDATER="1")
    if clave:
        env["OPENCODE_SERVER_PASSWORD"] = clave
    try:
        r = (correr or subprocess.run)(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, timeout=timeout, **opciones_proceso())
    except (OSError, subprocess.SubprocessError) as e:
        raise ErrorControl("no pude exportar la sesión %s de OpenCode: %s" % (sesion, e))
    salida = (r.stdout or b"").decode("utf-8", "replace")
    if r.returncode != 0 or "{" not in salida:
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise ErrorControl("OpenCode no exportó la sesión %s (%s): %s" % (sesion, r.returncode,
                                                                          err[-1] if err else "sin salida"))
    try:
        export = json.loads(salida[salida.index("{"):])
    except ValueError as e:
        raise ErrorControl("el export de OpenCode no es JSON: %s" % e)
    return turnos_del_export(export)


def turnos_del_export(export):
    """Los turnos visibles del export oficial ({info, messages}), en los dos formatos que ya lee
    el adaptador (engines/opencode._first_user_text y la captura de cierre): opencode 1 ({info:
    {role, time}, parts: [{type: "text", text}]}) y opencode 2 ({type: "user", text, time} / {type: "assistant", content: [{type: "text", text}]};
    VERIFICADO 2.0.29). Solo diálogo: sin razonamiento ni herramientas. Los mensajes seguidos del
    agente (antes y después de una herramienta) son UN turno, como en la página. `t`: epoch o None."""
    out = []
    for m in (export or {}).get("messages") or []:
        if not isinstance(m, dict):
            continue
        info = m.get("info")
        if isinstance(info, dict) and isinstance(m.get("parts"), list):
            rol, partes = info.get("role"), m["parts"]
            hora = info["time"].get("created") if isinstance(info.get("time"), dict) else None
            texto = "\n".join(p.get("text", "") for p in partes if isinstance(p, dict)
                              and p.get("type") == "text" and isinstance(p.get("text"), str)).strip()
        else:
            rol = m.get("type")
            hora = m["time"].get("created") if isinstance(m.get("time"), dict) else None
            if rol == "user":
                texto = m.get("text").strip() if isinstance(m.get("text"), str) else ""
            else:
                partes = m.get("content") if isinstance(m.get("content"), list) else []
                texto = "\n".join(p.get("text", "") for p in partes if isinstance(p, dict)
                                  and p.get("type") == "text" and isinstance(p.get("text"), str)).strip()
        if rol not in ("user", "assistant") or not texto:
            continue
        t = float(hora) / 1000.0 if isinstance(hora, (int, float)) else None
        if rol == "assistant" and out and out[-1]["rol"] == "agente":
            out[-1]["texto"] += "\n\n" + texto
            continue
        out.append({"rol": "yo" if rol == "user" else "agente", "texto": texto, "t": t})
    return out


def desenvolver(cuerpo):
    """La API v2 envuelve TODA respuesta en {"data": …}. VERIFICADO con el
    probador real (v2.1.4, 17-nov): POST /api/session → {"data":{"id":"ses_…",
    …}}. Lo mismo los eventos: {"type", "data": {"sessionID", …}}. Sin sobre
    (una versión que no lo use), el cuerpo pasa tal cual."""
    if isinstance(cuerpo, dict) and "data" in cuerpo and isinstance(cuerpo["data"], (dict, list)):
        return cuerpo["data"]
    return cuerpo


class OpenCode(Conector):
    motor = "opencode"
    misma_conversacion = True

    def __init__(self, cwd=None, url=URL, clave=None, usuario="opencode", cabeceras=None,
                 conectar=None, grabar=None, timeout=30, reintentos_sse=5, pausa_sse=0.5,
                 espera_parar=5.0, compartida=False, pausa_resync=PAUSA_RESYNC):
        super().__init__(cwd=cwd, grabar=grabar)
        self._pausa_resync = pausa_resync
        self._eventos_vistos = 0               # de SU sesión (B2: algo llegó entre dos consultas)
        #: F4: el servidor y la sesión son los de su terminal (sigue también sus turnos).
        self.compartida = bool(compartida)
        self._espera_parar = espera_parar        # tope para cerrar «parado» si no llega el evento
        self.url = url.rstrip("/")
        self._cabeceras = dict(cabeceras or {})
        if clave:
            par = base64.b64encode(("%s:%s" % (usuario, clave)).encode("utf-8")).decode("ascii")
            self._cabeceras.setdefault("Authorization", "Basic " + par)
        self._conectar = conectar              # () → socket ya abierto (pruebas)
        self._timeout = timeout
        self._sse = None                       # control.sse.LectorSSE
        self._reintentos_sse = reintentos_sse
        self._pausa_sse = pausa_sse
        self._parando = False
        self._corte = None                     # «error» si el turno se cortó por una falla nuestra
        self._prompt_enviado = None            # threading.Event del prompt de este turno
        self._n_turno = 0
        #: B38 · el nombre de cada herramienta por su id: solo session.tool.input.started lo trae (data.name);
        #: called/success/failed traen el id (tráfico real de la reverificación, v2.1.4, 19-nov).
        self._herramientas = {}

    # ── HTTP ────────────────────────────────────────────────────────────────
    def _conexion(self, timeout):
        p = urlsplit(self.url)
        conn = http.client.HTTPConnection(p.hostname or "127.0.0.1", p.port or 80, timeout=timeout)
        if self._conectar:
            conn.sock = self._conectar()
        return conn

    def _ruta(self, clave, **kw):
        ruta = RUTAS[clave].format(**{k: quote(str(v), safe="") for k, v in kw.items()})
        return ruta + "?" + urlencode({"directory": self.cwd})

    def _pedir(self, metodo, ruta, cuerpo=None):
        datos = None if cuerpo is None else json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        hs = dict({"Accept": "application/json", "Content-Type": "application/json"}, **self._cabeceras)
        if self._grabar:
            self._grabar(">", "%s %s %s" % (metodo, ruta, datos.decode("utf-8") if datos else ""))
        conn = self._conexion(self._timeout)
        try:
            conn.request(metodo, ruta, body=datos, headers=hs)
            r = conn.getresponse()
            crudo = r.read()
        finally:
            conn.close()
        if self._grabar:
            self._grabar("<", "%s %s" % (r.status, crudo[:4000].decode("utf-8", "replace")))
        try:
            cuerpo = json.loads(crudo) if crudo.strip() else None
        except ValueError:
            cuerpo = crudo.decode("utf-8", "replace")
        return r.status, desenvolver(cuerpo)

    def pedir_al_arrancar(self, metodo, ruta, cuerpo=None, espera=None):
        """_pedir, otra vez mientras su servidor diga 503 (arrancando: ARRANQUE_S), hasta `espera` s."""
        fin = time.time() + (ARRANQUE_S if espera is None else espera)
        while True:
            st, r = self._pedir(metodo, ruta, cuerpo)
            if not arrancando(st) or time.time() >= fin:
                return st, r
            time.sleep(PAUSA_ARRANQUE)

    # ── abrir: primero escuchar, después crear (no se pierde ningún evento) ─
    def _abrir(self, sesion):
        p = urlsplit(self.url)
        host, puerto = p.hostname or "127.0.0.1", p.port or 80
        abrir = self._conectar or abrir_tcp(host, puerto, self._timeout)
        fin = time.time() + ARRANQUE_S
        while True:
            self._sse = LectorSSE(abrir, "%s:%s" % (host, puerto), self._ruta("eventos"),
                                  cabeceras=self._cabeceras, reintentos=self._reintentos_sse,
                                  pausa=self._pausa_sse, grabar=self._grabar)
            threading.Thread(target=self._escuchar, args=(self._sse,), name="control-opencode-sse",
                             daemon=True).start()
            if self._sse.conectado.wait(self._timeout) and self._sse.aceptado:
                break
            fallo = self._sse.fallo or "sin respuesta en %s s" % self._timeout
            self._cerrar()
            if arrancando(None, fallo) and time.time() < fin:     # B31: aún arranca; no es que no esté
                time.sleep(PAUSA_ARRANQUE)
                continue
            raise ErrorControl("no pude escuchar los eventos de OpenCode en %s (%s)" % (self.url, fallo))
        try:
            if sesion:
                st, r = self.pedir_al_arrancar("GET", self._ruta("sesion", id=sesion))
                if st != 200:
                    raise ErrorControl("OpenCode no tiene la sesión %s (%s)" % (sesion, st))
                return sesion
            st, r = self.pedir_al_arrancar("POST", self._ruta("crear"), {})
            sid = campo(r if isinstance(r, dict) else {}, "id", "sessionID", "sessionId")
            if st >= 400 or not sid:
                raise ErrorControl("OpenCode no creó la sesión (%s): %s" % (st, corto(r)))
            return sid
        except (OSError, http.client.HTTPException) as e:
            self._cerrar()
            raise ErrorControl("OpenCode no responde en %s: %s" % (self.url, e))
        except ErrorControl:
            self._cerrar()
            raise

    def _escuchar(self, lector):
        def al_evento(texto):
            try:
                d = json.loads(texto)
            except ValueError:
                return
            if isinstance(d, dict):
                self._evento(d)
        fin = lector.correr(al_evento, al_conectar=self._al_conectar)
        if fin == "perdido" and lector is self._sse:
            self._perdido("se cortaron los eventos de OpenCode y no volvieron (%s)" % lector.fallo)

    # ── B2: los eventos vuelven tras un corte ───────────────────────────────
    def _al_conectar(self, n):
        """Sus eventos volvieron tras un corte (n ≥ 1). Lo que pasó en el hueco no llega: si su
        session.idle cayó ahí, el turno quedaba «trabajando» hasta Parar. Con un turno en curso, un
        vigilante le pregunta a su servidor y lo cierra si quedó libre."""
        if n < 1 or self.estado() != "trabajando":
            return
        threading.Thread(target=self._resincronizar, args=(self._n_turno,), name="control-opencode-resync",
                         daemon=True).start()

    def _resincronizar(self, este):
        """Cierra el turno `este` solo si su servidor dice dos veces, con `pausa_resync` entre medio, que la
        sesión está libre, y entre tanto no llegó nada de ella. Antes espera a que su prompt haya salido: un
        prompt que todavía no entra no se toma por un turno terminado. Si no se sabe (None), no toca nada."""
        enviado = self._prompt_enviado
        if enviado is not None:
            enviado.wait(self._timeout)
        visto = self._eventos_vistos
        for i in range(2):
            if i:
                threading.Event().wait(self._pausa_resync)
            if self._n_turno != este or self.estado() != "trabajando" or self._eventos_vistos != visto:
                return
            if self.estado_sesion() != "libre":
                return
        if self._n_turno == este and self._eventos_vistos == visto:
            self._terminar(self._motivo_parado() if self._parando else "fin", resincronizado=True)

    def cortar_eventos(self, espera=0.0):
        """Corta sus eventos como un corte de red; vuelven tras `espera` s (el probador real: paso «reconectar»)."""
        if self._sse is not None:
            self._sse.cortar(espera)

    def estado_sesion(self):
        """¿Su sesión está libre? «libre» | «ocupada» | None (no se supo). Pregunta a la sesión y, si su
        respuesta no lo dice, al estado de las sesiones ({sesión: {type}}). Ver estado_de y RUTAS["estado"]."""
        if not self.sesion:
            return None
        for clave in ("sesion", "estado"):
            try:
                st, r = self._pedir("GET", self._ruta(clave, id=self.sesion))
            except (OSError, http.client.HTTPException):
                return None
            if st != 200:
                continue
            # en el estado de las sesiones, cada una es su estado tal cual ({type}), como el `status` de la sesión
            e = estado_de(r if clave == "sesion" else {"status": r.get(self.sesion) if isinstance(r, dict) else None})
            if e:
                return e
        return None

    # ── turno ───────────────────────────────────────────────────────────────
    def _mandar(self, texto):
        self._parando = False
        self._corte = None
        self._n_turno += 1
        enviado = self._prompt_enviado = threading.Event()

        def enviar():
            try:
                # VERIFICADO con el probador real (v2.1.4): con {"parts": […]} contesta
                # 400 «Missing key at ["text"]»: el cuerpo es {"text": …}.
                st, r = self._pedir("POST", self._ruta("prompt", id=self.sesion), {"text": texto})
            except (OSError, http.client.HTTPException) as e:
                st, r = 0, str(e)
            finally:
                enviado.set()
            if st == 0 or st >= 400:
                self._emitir("error", mensaje="OpenCode no aceptó el mensaje (%s): %s" % (st, corto(r)),
                             fatal=False)
                self._terminar("error")
        threading.Thread(target=enviar, name="control-opencode-prompt", daemon=True).start()

    def _parar(self):
        """VERIFICADO con el probador real (v2.1.4, 18-nov): tras POST …/interrupt
        ({"interrupted":true}) NO llega session.idle; llegan session.step.failed
        (error aborted) y session.execution.interrupted (reason user), que ya
        cierran el turno. Por si una versión no manda ninguno, a los
        `espera_parar` s el turno se cierra «parado» igual."""
        self._parando = True
        # Un parar justo después de mandar no se adelanta al prompt (va en su hilo): si el
        # interrupt llega antes, OpenCode no tiene nada que parar y el turno sigue solo
        # (arq-control8: el turno se cerraba «parado» por el tope y su texto seguía llegando).
        enviado = self._prompt_enviado
        if enviado is not None:
            enviado.wait(self._timeout)
        try:
            self._pedir("POST", self._ruta("parar", id=self.sesion), {})
        except (OSError, http.client.HTTPException) as e:
            self._emitir("error", mensaje="no pude parar OpenCode: %s" % e, fatal=False)

        este = self._n_turno

        def tope():
            if self._parando and self._n_turno == este:     # solo ESTE turno, no el siguiente
                self._terminar(self._motivo_parado())
        t = threading.Timer(self._espera_parar, tope)
        t.daemon = True
        t.start()

    def _motivo_parado(self):
        return self._corte or "parado"

    def _cortar(self, mensaje):
        """Una falla nuestra a media vuelta deja a OpenCode esperando (probador real
        7: no aceptó la respuesta a un permiso y esperó para siempre; el turno no se
        cerraba y la sesión quedaba «está trabajando»). Avisa CON el texto, interrumpe
        su ejecución (como parar) y cierra el turno «error»: la sesión vuelve a listo."""
        self._emitir("error", mensaje=mensaje, fatal=False)
        self._corte = "error"
        self._parar()

    def _formulario(self, form):
        """B15 (cacería 19-nov): su herramienta `question` abre un formulario (form.created) y OpenCode espera su
        respuesta; la página no lo veía y el turno quedaba «Pensando…» para siempre, con lo nuevo en cola. Su primera
        pregunta va a la página (control.base: «pregunta», en la caja con sus botones) y su ejecución se interrumpe
        como al parar (lo verificó la cacería: form.cancelled + execution.interrupted, y la sesión sigue). El turno
        cierra «fin», no «parado»: tu respuesta le llega como tu siguiente mensaje."""
        campos = form.get("fields") if isinstance(form, dict) else None
        if isinstance(campos, dict):
            campos = list(campos.values())
        titulo, opciones = "", []
        for c in campos or []:
            titulo, opciones = pregunta_nativa(c)
            if titulo:
                break
        if not titulo:
            titulo = corto(campo(form, "title", "message", defecto="")) or "OpenCode te pregunta algo"
        self._emitir("pregunta", id=str(campo(form, "id", defecto="form")), texto=titulo, opciones=opciones)
        self._corte = "fin"
        threading.Thread(target=self._parar, name="opencode-formulario", daemon=True).start()

    def _cerrar(self):
        lector, self._sse = self._sse, None
        if lector is not None:
            lector.cerrar()

    # ── eventos ─────────────────────────────────────────────────────────────
    def _evento(self, d):
        tipo = d.get("type")
        p = campo(d, "properties", "payload", "data", defecto=d)
        # B15 (cacería 19-nov): form.created y form.cancelled traen la sesión DENTRO de su formulario (data.form)
        sid = campo(p, "sessionID", "sessionId", "session_id") or \
            campo(campo(p, "form", defecto={}), "sessionID", "sessionId", "session_id")
        if sid != self.sesion:
            return
        if tipo == "form.created":
            self._formulario(campo(p, "form", defecto={}))
            return
        self._eventos_vistos += 1
        if self.compartida and tipo in _ABREN_TURNO:
            self._turno_de_la_terminal(tipo, p)
        if tipo == "session.text.delta":
            t = campo(p, "delta", "text")
            if t:
                self._emitir("texto", texto=t)
        elif tipo == "session.tool.input.started":
            nombre = campo(p, "name", "tool")
            if isinstance(nombre, str) and nombre:
                self._herramientas[str(campo(p, "callID", "toolCallID", "id", defecto=""))] = nombre
        elif tipo in ("session.tool.called", "session.tool.success", "session.tool.failed"):
            fase = {"session.tool.called": "empieza", "session.tool.success": "termina",
                    "session.tool.failed": "falla"}[tipo]
            hid = str(campo(p, "callID", "toolCallID", "id", defecto=""))
            nombre = campo(p, "tool", "name") or self._herramientas.get(hid) or "?"   # B38
            if fase != "empieza":
                self._herramientas.pop(hid, None)
            self._emitir("herramienta", id=hid, nombre=nombre, fase=fase,
                         detalle=corto(campo(p, "input", "error", "title")))
        elif tipo == "permission.asked":
            pid = str(campo(p, "id", "requestID", "permissionID", defecto=""))

            def responder(decision, pid=pid):
                if decision is None and self.corte() in INTERRUMPIDO:
                    # E9: la página se apaga o se reinicia: no se contesta «reject» a nombre del socio (el turno se
                    # corta al cerrar; en un servidor compartido con su terminal, el pedido sigue ahí). A VERIFICAR
                    # con el motor real.
                    return
                try:
                    st, r = self._pedir("POST", self._ruta("permiso", id=self.sesion, pid=pid),
                                        {CLAVE_RESPUESTA: _RESPUESTA.get(decision, "reject")})
                except (OSError, http.client.HTTPException) as e:
                    st, r = 0, str(e)
                if decision is None:                 # cancelado (parar/cerrar): ya se cierra por ahí
                    return
                if st == 0 or st >= 400:
                    self._cortar("OpenCode no aceptó la respuesta al permiso (%s): %s"
                                 % (st or "sin conexión", _su_mensaje(r)))
            # VERIFICADO con el probador real (v2.1.4, 18-nov): {"id": "per_…", "action":
            # "edit", "resources": ["prueba.txt"], "save", "metadata": {"files": …}}.
            self._anunciar_permiso(pid, campo(p, "action", "permission", "tool", "type", defecto="permiso"),
                                   campo(p, "resources", "patterns", "metadata", "title"),
                                   OPCIONES_PERMISO, responder)
        elif tipo == "permission.replied":
            self._olvidar_permiso(campo(p, "id", "requestID", "permissionID", defecto=""))
        elif tipo == "session.usage.updated":
            self._poner_uso(fuente="opencode", crudo={k: v for k, v in p.items() if k != "sessionID"})
        elif tipo == "session.execution.failed":
            self._emitir("error", mensaje="OpenCode: %s" % (corto(campo(p, "error", "message"))
                                                            or "el turno falló"), fatal=False)
            self._terminar(self._motivo_parado() if self._parando else "error")
        elif tipo in ("session.idle", "session.execution.succeeded"):
            self._terminar(self._motivo_parado() if self._parando else "fin")
        elif tipo == "session.execution.interrupted":
            self._terminar(self._motivo_parado())

    def _turno_de_la_terminal(self, tipo, p):
        """F4: sin turno nuestro en curso, lo que empieza en la sesión es de su terminal. Con
        uno nuestro en curso, su `inbox.enqueued` es nuestro propio mensaje (u otro que la
        terminal le sumó al turno: va en el mismo)."""
        texto = ""                                # (otro evento: empezó sin que viéramos su mensaje)
        if tipo == "session.inbox.enqueued":
            item = campo(p, "item", defecto={})
            if campo(item, "type") != "user":
                return
            texto = campo(campo(item, "payload", defecto={}), "text", defecto="")
        if self._empezar_ajeno(texto if isinstance(texto, str) else ""):
            # un turno nuevo, como en _mandar: un «parar» de antes no lo marca «parado»
            self._parando, self._corte = False, None
            self._n_turno += 1


#: F4: los eventos que, sin turno nuestro en curso, dicen que la terminal empezó uno. No los de
#: cierre ni los de uso: lo que llega tarde de un turno ya cerrado no abre otro.
_ABREN_TURNO = ("session.inbox.enqueued", "session.execution.started", "session.text.delta",
                "session.tool.called", "permission.asked")


def _su_mensaje(r):
    """Lo que OpenCode dijo al rechazar un pedido: su «message» (p. ej. «Missing key
    at ["decision"]») en una línea; si no trae, el cuerpo acotado."""
    texto = campo(r, "message", "error") if isinstance(r, dict) else r
    if not isinstance(texto, str):
        texto = corto(r)
    return " ".join(texto.split()) or "sin texto"
