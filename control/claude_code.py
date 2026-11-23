"""WORKSPACE · control/claude_code.py — Claude Code desde la página con su modo
sin pantalla (D2-c, uso personal con la suscripción del socio): UNA corrida
`claude -p --resume <id> --output-format stream-json` por mensaje, sobre la
misma conversación de la pestaña.

  · Conversación nueva: la primera corrida usa `--session-id <uuid>` (el id lo
    fija Workspace); las siguientes, `--resume <uuid>`.
  · Permisos: `--permission-mode` y `--settings` de la sesión (los mismos que
    arma el lanzador) y, para lo que igual pide permiso, `--permission-prompt-
    tool` con el MCP de control/permiso_mcp.py: el pedido llega a la página
    como evento `permiso` y la respuesta vuelve a la corrida.
  · El mensaje entra por stdin (no queda en la lista de procesos).
  · Parar: SIGINT (la doc: «To end the turn instead, send SIGINT»); si sigue
    vivo, SIGTERM (sale con 143 y deja el turno sin resultado).

EL CHOQUE CON LA TERMINAL. La doc (sessions): «If you resume the same session
in two terminals or two `claude -p` runs at the same time, both write to one
transcript. When you resume that session later, messages from one of them can
be missing. To keep both conversations, add `--fork-session`». No hay candado
entre una terminal abierta y una corrida `-p`. Regla de Workspace:
  1. la página escribe SOLO si la terminal de esa conversación no está abierta
     (`terminal_abierta(id)`, que da el estado en vivo del núcleo); si está
     abierta, se niega y la página ofrece «Ir a la terminal»;
  2. mientras corre un mensaje de la página, la conversación queda marcada
     (`ocupada(id)`): ni otra pestaña de la página ni el hub la reabren con
     `--resume` hasta que termine;
  3. «seguir en una copia» (`--fork-session`) solo como elección explícita del
     socio, nunca automática."""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid

from control import permiso_mcp
from control.base import Conector, ErrorControl, archivo_de, campo, corto, texto_cancelado
from control.canal import CanalProceso

#: Segundos entre SIGINT y SIGTERM al parar.
GRACIA_PARAR = 5.0


def _dir_candados():
    import paths
    d = os.path.join(paths.state_dir(), "control")
    os.makedirs(d, exist_ok=True)
    return d


def _candado(sesion, carpeta=None):
    return os.path.join(carpeta or _dir_candados(), "claude-%s.lock" % sesion)


def _vivo(pid):
    from control import hijos                      # en Windows, sin os.kill(pid, 0) (es un Ctrl+C)
    return hijos.vivo(pid)


def ocupada(sesion, carpeta=None):
    """¿Hay una corrida de la página escribiendo en esta conversación? (el hub
    lo pregunta antes de abrir la terminal con --resume)."""
    try:
        with open(_candado(sesion, carpeta), encoding="utf-8") as fh:
            pid = json.load(fh).get("pid")
    except (OSError, ValueError, AttributeError):
        return False
    return _vivo(pid)


#: E9: lo más que espera un cierre a que el motor lea sus permisos interrumpidos, y cuánto sin novedad es «ya no hay más».
DRENAJE_S = 4.0
QUIETO_S = 1.0


def respuesta_permiso(decision, corte=""):
    """Lo que se le contesta a Claude Code por su herramienta de permisos: «allow», o «deny» con su porqué. Sin
    decisión del socio (None) dice por qué se canceló: paró el turno, o la página se reinició / la conversación se
    cerró (E9: eso NO es un «no» del socio, y se lo dice)."""
    if decision in ("permitir", "permitir_siempre"):
        return {"behavior": "allow"}
    return {"behavior": "deny", "message": permiso_mcp.NEGADO if decision else texto_cancelado(corte)}


class ClaudeCode(Conector):
    motor = "claude-code"
    misma_conversacion = True
    #: Fable v2: una corrida por mensaje, así que UN turno (el de un encargo) puede ir con otro nivel: su modo, su
    #: `--settings`, qué herramientas pasan y las marcas del entorno para el aviso del encargo. Solo esa corrida.
    acota_turnos = True

    def __init__(self, cwd=None, exe=None, modo_permisos="manual", settings=None, modelo=None,
                 extra=None, terminal_abierta=None, candados=None, env=None, grabar=None,
                 gracia_parar=GRACIA_PARAR):
        super().__init__(cwd=cwd, grabar=grabar)
        self.exe = exe
        self._modo = modo_permisos
        self._settings = settings
        self._modelo = modelo
        self._extra = list(extra or [])
        self._terminal_abierta = terminal_abierta
        self._candados = candados
        self._env = env
        self._gracia = gracia_parar
        self._existe = False
        self._canal = None
        self._parando = False
        self._permisos_dir = None
        self._ajustes_dir = None
        self._texto_vivo = False
        self._del_turno = None

    # ── Fable v2: un turno acotado (el de un encargo) ───────────────────────
    def para_el_turno(self, modo=None, settings=None, permitidas=None, negadas=None, env=None):
        """El nivel de la PRÓXIMA corrida y solo de ella (lo consume _mandar): `modo` (--permission-mode), `settings`
        (en lugar del de la sesión), `permitidas` (en lugar de su --allowedTools), `negadas` (--disallowedTools) y
        `env` (las marcas del aviso del encargo). → True."""
        self._del_turno = {"modo": modo, "settings": settings, "permitidas": list(permitidas or []),
                           "negadas": list(negadas or []), "env": dict(env or {})}
        return True

    def _soltar_turno(self):
        self._del_turno = None

    def _env_del_turno(self, base):
        """El entorno de la corrida: sin marcas de encargo de otra corrida; con las de este turno si es uno acotado."""
        out = {k: v for k, v in dict(base or {}).items() if not str(k).startswith("WORKSPACE_ENCARGO_")}
        if self._del_turno:
            out.update(self._del_turno.get("env") or {})
        return out

    # ── abrir: no corre nada (una corrida por mensaje) ──────────────────────
    def _abrir(self, sesion):
        exe = self.exe or shutil.which("claude")
        if not exe:
            raise ErrorControl("claude no está en PATH")
        self.exe = exe
        self._existe = bool(sesion)
        return sesion or str(uuid.uuid4())

    def _abrir_nueva(self, sesion):
        """abrir(id, nueva=True): una conversación NUEVA con el número que fija
        Workspace (la pestaña): la primera corrida va con `--session-id <id>`, las
        siguientes con `--resume <id>`. Claude Code pide un UUID."""
        try:
            sid = str(uuid.UUID(str(sesion)))
        except ValueError:
            raise ValueError("Claude Code fija conversaciones nuevas con un UUID: %r" % (sesion,))
        self._abrir(None)
        self._existe = False
        return sid

    def _puede_mandar(self):
        if self._terminal_abierta and self._terminal_abierta(self.sesion):
            raise ErrorControl("La terminal de esta conversación está abierta: escribe ahí, o "
                               "ciérrala para escribir desde la página.")
        if ocupada(self.sesion, self._candados):
            raise ErrorControl("Otra ventana ya está escribiendo en esta conversación.")

    def comando(self):
        """El argv de la próxima corrida (sin el mensaje: va por stdin)."""
        cmd = list(self.exe) if isinstance(self.exe, (list, tuple)) else [self.exe]
        cmd += ["-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages"]
        cmd += ["--resume", self.sesion] if self._existe else ["--session-id", self.sesion]
        t = self._del_turno or {}
        modo = t.get("modo") or self._modo
        if modo:
            cmd += ["--permission-mode", modo]
        settings = t["settings"] if t.get("settings") is not None else self._settings
        if settings:
            cmd += ["--settings", self._settings_arg(cmd[0], settings)]
        if self._modelo:
            cmd += ["--model", self._modelo]
        if self._permisos_dir:
            mcp = {"mcpServers": {permiso_mcp.SERVIDOR: {
                "type": "stdio", "command": sys.executable,
                "args": [os.path.abspath(permiso_mcp.__file__)],
                "env": {permiso_mcp.ENTORNO: self._permisos_dir}}}}
            cmd += ["--mcp-config", json.dumps(mcp, separators=(",", ":")),
                    "--permission-prompt-tool", permiso_mcp.NOMBRE_COMPLETO]
        if not t:
            return cmd + self._extra
        extra, saltar = [], False
        for a in self._extra:                    # su --allowedTools de la sesión no va: el del turno manda
            if saltar:
                saltar = False
                continue
            if a in ("--allowedTools", "--allowed-tools", "--disallowedTools", "--disallowed-tools"):
                saltar = True
                continue
            if str(a).startswith(("--allowedTools=", "--allowed-tools=", "--disallowedTools=", "--disallowed-tools=")):
                continue
            extra.append(a)
        if t.get("permitidas"):
            extra.append("--allowedTools=" + ",".join(t["permitidas"]))
        if t.get("negadas"):
            extra.append("--disallowedTools=" + ",".join(t["negadas"]))
        return cmd + extra

    def _settings_arg(self, exe, settings):
        """El valor de `--settings <file-or-json>`: el JSON tal cual; o, si `exe` es un lanzador .cmd/.bat (el claude
        de npm en Windows), la ruta de un archivo con él. La línea pasa entonces por cmd.exe, que no acepta más de
        8191 caracteres, y los permisos de la sesión llevan la ruta del cerebro en cada regla: con un cerebro en una
        ruta de ~100 caracteres la corrida no abría («La línea de comandos es demasiado larga»). El archivo vive en
        una carpeta de esta corrida y se va con ella (_limpiar). Si no se puede escribir, va como antes."""
        texto = settings if isinstance(settings, str) else json.dumps(settings, separators=(",", ":"))
        if not (os.name == "nt" and str(exe or "").lower().endswith((".cmd", ".bat"))):
            return texto
        try:
            if not self._ajustes_dir:
                self._ajustes_dir = tempfile.mkdtemp(prefix="ws-control-ajustes-")
            ruta = os.path.join(self._ajustes_dir, "settings.json")
            with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(texto)
            return ruta
        except OSError:
            return texto

    # ── turno ───────────────────────────────────────────────────────────────
    def _mandar(self, texto):
        self._parando = False
        self._texto_vivo = False
        # un `claude -p --resume` de esta conversación que quedó vivo de un servidor muerto
        # atora el siguiente --resume (punto G): se cierra antes de correr
        self._limpiar_huerfano(self.sesion)
        self._tomar_candado()                    # primero: si falla, no hay nada que limpiar
        self._permisos_dir = tempfile.mkdtemp(prefix="ws-control-permisos-")
        try:
            env = self._entorno(self._env_del_turno(self._env if self._env is not None else os.environ))
            try:
                cmd = self.comando()
            finally:
                self._soltar_turno()                 # el nivel de un encargo vale para esta corrida y nada más
            self._canal = CanalProceso(cmd, cwd=self.cwd, env=env, grabar=self._grabar)
            self._registrar_hijo(self.sesion)
            self._canal.enviar(texto)
            self._canal.cerrar_entrada()
        except OSError as e:
            self._limpiar()
            raise ErrorControl("no pude correr claude: %s" % e)
        threading.Thread(target=self._leer, args=(self._canal,), name="control-claude",
                         daemon=True).start()
        threading.Thread(target=self._vigilar_permisos, args=(self._canal, self._permisos_dir),
                         name="control-claude-permisos", daemon=True).start()

    def _leer(self, canal):
        cierre = None                                    # (motivo, extra, error) del `result`
        while True:
            linea = canal.recibir()
            if linea is None:
                break
            try:
                msg = json.loads(linea)
            except ValueError:
                continue
            if isinstance(msg, dict):
                cierre = self._linea(msg) or cierre
        try:
            rc = canal.proc.wait(timeout=10)
        except Exception:
            rc = None
        err = canal.stderr()
        canal.cerrar(espera=1.0)
        from control import hijos
        hijos.soltar(self.motor, self.sesion, canal.proc.pid)
        self._existe = self._existe or cierre is not None or rc == 0
        self._limpiar()                                  # antes del `terminado`: ya se puede mandar
        if cierre is None:
            if self._parando:
                cierre = ("parado", {}, None)
            else:
                cierre = ("error", {}, "claude terminó sin resultado (rc=%s)%s"
                          % (rc, ": " + err if err else ""))
        motivo, extra, error = cierre
        if error:
            self._emitir("error", mensaje=error, fatal=False)
        self._terminar(motivo, **extra)

    def _linea(self, m):
        """Una línea de stream-json. Si es el `result`, devuelve cómo cierra el
        turno (motivo, extra, error); el `terminado` sale después de limpiar."""
        tipo = m.get("type")
        if m.get("parent_tool_use_id"):                 # subagentes: no son la respuesta
            return None
        if tipo == "stream_event":
            ev = m.get("event") or {}
            d = ev.get("delta") or {}
            if ev.get("type") == "content_block_delta" and d.get("type") == "text_delta" and d.get("text"):
                self._texto_vivo = True
                self._emitir("texto", texto=d["text"])
        elif tipo == "assistant":
            for b in (m.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use":
                    self._emitir("herramienta", id=str(b.get("id") or ""), nombre=b.get("name") or "?",
                                 fase="empieza", detalle=corto(b.get("input")), archivo=archivo_de(b.get("input")))
                elif b.get("type") == "text" and b.get("text") and not self._texto_vivo:
                    self._emitir("texto", texto=b["text"])
        elif tipo == "user":
            for b in (m.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    self._emitir("herramienta", id=str(b.get("tool_use_id") or ""), nombre="",
                                 fase="falla" if b.get("is_error") else "termina",
                                 detalle=corto(b.get("content")))
        elif tipo == "result":
            self._poner_uso(fuente="claude-code", costo_usd=m.get("total_cost_usd"),
                            tokens=m.get("usage"), turnos=m.get("num_turns"))
            negados = [campo(d, "tool_name", defecto="?") for d in m.get("permission_denials") or []
                       if isinstance(d, dict)]
            extra = {"negados": negados} if negados else {}
            if m.get("is_error") or m.get("subtype") not in (None, "success"):
                if self._parando:
                    return "parado", extra, None
                return "error", extra, "claude: %s" % (m.get("result") or m.get("subtype"))
            return ("parado" if self._parando else "fin"), extra, None
        return None

    def _vigilar_permisos(self, canal, carpeta):
        """Los pedidos que deja permiso_mcp → eventos `permiso`."""
        vistos = set()
        while canal.vivo() and os.path.isdir(carpeta):
            try:
                nombres = sorted(os.listdir(carpeta))
            except OSError:
                break
            for n in nombres:
                if not (n.startswith("pedido-") and n.endswith(".json")) or n in vistos:
                    continue
                vistos.add(n)
                try:
                    with open(os.path.join(carpeta, n), encoding="utf-8") as fh:
                        p = json.load(fh)
                except (OSError, ValueError):
                    vistos.discard(n)
                    continue
                pid = str(p.get("id"))

                def responder(decision, pid=pid):
                    r = respuesta_permiso(decision, self.corte())
                    try:
                        permiso_mcp.escribir_json(os.path.join(carpeta, "respuesta-%s.json" % pid), r)
                    except OSError:
                        pass
                self._anunciar_permiso(pid, p.get("herramienta"), p.get("entrada"),
                                       ("permitir", "negar"), responder)
            time.sleep(0.05)

    def _parar(self):
        canal = self._canal
        if canal is None or not canal.vivo():
            return
        self._parando = True
        canal.senal_interrumpir()

        def escalar():
            time.sleep(self._gracia)
            if canal.vivo():                     # SIGTERM y luego SIGKILL al GRUPO (punto G)
                from control import hijos
                hijos.matar_grupo(canal.proc.pid, canal.proc.pid, gracia=1.0)
        threading.Thread(target=escalar, daemon=True).start()

    def _drenar_permisos(self, canal, carpeta):
        """E9: antes del Ctrl+C de un cierre, darle al motor el momento de LEER lo que se le contestó («la página se
        reinició, no lo negó») y de pedir los que venían en fila (cada uno se contesta igual, al llegar). Sin esto el
        corte le ganaba a la respuesta y Claude Code apuntaba «el usuario no quiso» para todos. Acotado: termina
        cuando no queda ninguna respuesta por leer y no llega otro pedido en QUIETO_S, o a los DRENAJE_S."""
        if not carpeta or not self.interrumpidos():
            return
        ahora = time.monotonic()
        limite, quieto, vistos = ahora + DRENAJE_S, ahora, len(self.interrumpidos())
        while canal.vivo() and time.monotonic() < limite:
            try:
                sin_leer = any(n.startswith("respuesta-") and n.endswith(".json") for n in os.listdir(carpeta))
            except OSError:
                return
            n = len(self.interrumpidos())
            if sin_leer or n != vistos:
                quieto, vistos = time.monotonic(), n
            elif time.monotonic() - quieto >= QUIETO_S:
                return
            time.sleep(0.03)

    def _cerrar(self):
        canal = self._canal
        if canal is not None and canal.vivo():
            self._drenar_permisos(canal, self._permisos_dir)
            self._parar()
            try:
                canal.proc.wait(timeout=self._gracia + 5)
            except Exception:
                pass

    # ── candado de la conversación y limpieza ───────────────────────────────
    def _tomar_candado(self):
        ruta = _candado(self.sesion, self._candados)
        try:
            fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            if ocupada(self.sesion, self._candados):
                raise ErrorControl("Otra ventana ya está escribiendo en esta conversación.")
            os.remove(ruta)                              # de una corrida que ya murió
            fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"pid": os.getpid(), "desde": time.time()}, fh)

    def _limpiar(self):
        try:
            os.remove(_candado(self.sesion, self._candados))
        except OSError:
            pass
        carpeta, self._permisos_dir = self._permisos_dir, None
        if carpeta:
            shutil.rmtree(carpeta, ignore_errors=True)
        ajustes, self._ajustes_dir = self._ajustes_dir, None
        if ajustes:
            shutil.rmtree(ajustes, ignore_errors=True)