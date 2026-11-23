"""WORKSPACE · control/base.py — la interfaz común de la capa de control.

La página (o el hub) habla con cualquier motor por su vía OFICIAL con las
mismas operaciones, sin leer su pantalla ni teclear en ella:

    c = control.conector("copilot", cwd=cerebro)
    sid = c.abrir()                    # o c.abrir("<id>") para retomar
    c.mandar("hola")                   # no bloquea: los eventos llegan solos
    for ev in c.eventos(timeout=60):   # texto, herramienta, permiso, terminado, error
        if ev["tipo"] == "permiso":
            c.responder_permiso(ev["id"], "permitir")
        if ev["tipo"] == "terminado":
            break
    c.parar(); c.estado(); c.uso(); c.cerrar()

EVENTOS (dicts; todos llevan `tipo`, `motor` y `sesion`):
  · texto        {texto}                         un trozo de la respuesta, en vivo
  · herramienta  {id, nombre, fase, detalle}     fase: empieza | termina | falla
  · permiso      {id, herramienta, detalle, opciones}
                 opciones ⊆ DECISIONES; se contesta con responder_permiso(id, d)
  · error        {mensaje, fatal}                fatal = se perdió el motor
  · terminado    {motivo}                        fin | parado | error
  · entrada      {texto}                         F4: un mensaje que llegó por OTRO cliente de la
                 misma conversación (su terminal): abre un turno AJENO. Lo que sigue hasta su
                 `terminado` (texto, herramienta, permiso…) es de ese turno y lleva `ajeno: True`.
  · pregunta     {id, texto, opciones}           la pregunta con opciones PROPIA del motor (Codex:
                 su agentMessage con `questions`; OpenCode: su formulario `question`). No espera
                 respuesta por aquí: la respuesta es el siguiente `mandar` (cacería 19-nov, B14/B15).

Invariante: cada `mandar` termina con UN solo `terminado` (puede haber `error`
antes). Así quien consume solo espera ese evento. Cada `entrada`, igual.

ESTADOS: cerrado → (abrir) → listo → (mandar) → trabajando ⇄ esperando_permiso
→ (terminado) → listo. Si el motor muere: cerrado.

Stdlib (3.9+). Nada aquí lee credenciales ni tokens: cada motor corre con su
propio login."""
import atexit
import itertools
import os
import queue
import threading
import time
import weakref

#: «pregunta»: la pregunta con opciones PROPIA del motor (Codex: un agentMessage con `questions`; OpenCode: su
#: herramienta `question`, form.created): {id, texto, opciones}. La página la pone en la caja con sus botones y tu
#: respuesta le llega como tu siguiente mensaje (B14, B15: cacería 19-nov, se perdían).
TIPOS = ("texto", "herramienta", "permiso", "terminado", "error", "entrada", "pregunta")
DECISIONES = ("permitir", "permitir_siempre", "negar")
#: Monito UX (22-nov): «Sí, y lo demás en esta carpeta (solo este trabajo)». Lo elige el SOCIO (nunca la ofrece un
#: motor): al motor le llega un «permitir» normal y, en la conversación del monito, lo que siga en ESE turno del mismo
#: tipo (crear y cambiar archivos) dentro de ESA carpeta de su cerebro pasa sin otra tarjeta (la licencia del turno).
#: Nunca comandos, internet, otras herramientas ni nada fuera de su cerebro; se acaba con el turno.
PERMITIR_TURNO = "permitir_turno"
DECISIONES_SOCIO = DECISIONES + (PERMITIR_TURNO,)
#: Las carpetas de su cerebro donde no hay licencia (su memoria, quién es, su motor): ahí, cada vez, la tarjeta.
_SIN_LICENCIA = ("STATE", "BOOT", ".claude", ".git", ".obsidian", "motores", ".kiro", ".codex", ".cursor")
ESTADOS = ("cerrado", "listo", "trabajando", "esperando_permiso")
MOTIVOS = ("fin", "parado", "error")

#: Los conectores abiertos en este proceso (apagar() los cierra).
_CONECTORES = weakref.WeakSet()
#: Lo que se espera a que un motor termine de abrir (punto H).
TOPE_ABRIR = 45.0


def apagar():
    """Para el apagado del servidor de la página (punto G): cierra cada conector
    abierto y, por si alguno quedó, el grupo de cada proceso de motor. Va
    también en atexit; un servidor que recibe SIGTERM tiene que salir con
    sys.exit para que corra. Si el servidor muere de golpe (SIGKILL), lo que
    quede lo cierra el siguiente abrir() de esa conversación."""
    for c in list(_CONECTORES):
        try:
            c.cerrar()                         # lo que esperaba permiso queda interrumpido, no negado (E9)
        except Exception:
            pass
    from control import canal
    canal.cerrar_todos()


atexit.register(apagar)


#: Monito ronda 2 · E9 (22-nov, 11:27): con 5 permisos esperando, la página se reinició y el motor apuntó «el usuario no
#: quiso». Un permiso que se queda sin contestar porque Workspace se cierra NO es un «no» del socio: lo que le llega al
#: agente lo dice tal cual (por la vía de cada motor que deje mandar un texto; los demás reciben «cancelado»).
#: `corte()`: por qué se cancelaron los permisos pendientes («parar»: el socio paró el turno · «reinicio»: la página
#: local se apagó o se reinició · «cierre»: la conversación se cerró en Workspace).
INTERRUMPIDO = {
    "reinicio": ("La página de Workspace se reinició antes de que tu socio contestara este permiso: no lo negó, quedó "
                 "sin contestar. No lo tomes como un «no» ni lo intentes por otro camino. Cuando te vuelva a "
                 "escribir, dile en una frase que quedó pendiente por el reinicio y vuelve a pedirlo si todavía hace "
                 "falta."),
    "cierre": ("Esta conversación se cerró en Workspace antes de que tu socio contestara este permiso: no lo negó, "
               "quedó sin contestar. No lo tomes como un «no» ni lo intentes por otro camino. Cuando te vuelva a "
               "escribir, dile en una frase que quedó pendiente y vuelve a pedirlo si todavía hace falta."),
}
PARADO = "Se paró el turno."


def texto_cancelado(corte):
    """Lo que lee el agente cuando un permiso se cancela sin respuesta del socio, según por qué (`corte`)."""
    if corte == "ausente":                  # ronda 2 · P2-b (control/ausente.py): el socio no está; queda pendiente
        from control import ausente
        return ausente.TEXTO
    return INTERRUMPIDO.get(corte or "", PARADO)


class ErrorControl(Exception):
    """Una operación que no se puede hacer ahora (o un motor que falló al abrir)."""


def corto(valor, tope=400):
    """Un detalle legible y acotado (la página lo muestra tal cual)."""
    if valor is None:
        return ""
    if not isinstance(valor, str):
        try:
            import json
            valor = json.dumps(valor, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            valor = repr(valor)
    return valor if len(valor) <= tope else valor[:tope - 1] + "…"


#: Las claves con que las herramientas de los motores nombran el archivo que tocan.
_CLAVES_ARCHIVO = ("file_path", "filePath", "path", "file", "notebook_path")


def archivo_de(entrada):
    """El archivo que toca una herramienta, de su entrada ANTES de recortarla: `corto` ordena las claves y corta a
    400, y en un Write largo «content» va antes que «file_path» (la página no sabía qué archivo creaba). '' si no."""
    if isinstance(entrada, dict):
        for k in _CLAVES_ARCHIVO:
            v = entrada.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()[-300:]
    return ""


#: B01 (cacería 19-nov): lo que pide un permiso, en las clases que la página dice en simple. Sale de lo ESTRUCTURADO
#: que manda el motor (la clase ACP de su herramienta, el nombre EXACTO de su herramienta o las claves de su entrada),
#: nunca de palabras sueltas de un título o de una ruta: «mkdir -p /tmp/caza-ver-dir» salía «leer» por «ver» y
#: «touch …cambio.txt» salía «cambiar» por «cambio».
CLASES_PERMISO = ("comando", "crear", "cambiar", "borrar", "leer", "buscar", "web", "otra")
#: Las clases de herramienta de ACP (su esquema: ToolKind).
_KIND_ACP = {"execute": "comando", "edit": "cambiar", "delete": "borrar", "move": "cambiar", "read": "leer",
             "search": "buscar", "fetch": "web"}
#: Los nombres de herramienta que se conocen, enteros (minúsculas, con «_» en lugar de espacios y guiones).
_NOMBRES_PERMISO = {
    "comando": ("bash", "shell", "execute", "exec", "run", "run_command", "run_shell_command", "shell_command",
                "execute_command",
                "execute_bash", "exec_command", "local_shell", "terminal", "comando", "command"),
    "crear": ("write", "create", "write_file", "create_file", "fs_write", "writefile"),
    "cambiar": ("edit", "multiedit", "notebookedit", "patch", "apply_patch", "str_replace", "str_replace_editor",
                "edit_file", "cambio_de_archivos", "filechange"),
    "borrar": ("delete", "remove", "rm", "delete_file"),
    "leer": ("read", "read_file", "fs_read", "readfile"),
    "buscar": ("grep", "glob", "search", "find", "ls", "list", "codebase_search"),
    "web": ("webfetch", "websearch", "fetch", "web_fetch", "web_search", "browse"),
}
_POR_NOMBRE = {n: k for k, ns in _NOMBRES_PERMISO.items() for n in ns}


def _clase_por_entrada(e):
    if not isinstance(e, dict):
        return ""
    if e.get("command") or e.get("cmd") or e.get("argv"):
        return "comando"
    if e.get("url"):
        return "web"
    if any(e.get(k) is not None for k in ("old_string", "new_string", "edits", "diff", "patch")):
        return "cambiar"
    if e.get("content") is not None and archivo_de(e):
        return "crear"
    if e.get("pattern") or e.get("query"):
        return "buscar"
    return ""


def _texto_comando(entrada):
    """El comando tal cual: un texto; de una lista, su único elemento (OpenCode: resources ["date +%j"]) o sus
    argumentos como los escribiría la shell (Codex: ["bash", "-lc", "touch x"] → bash -lc 'touch x')."""
    import shlex
    c = entrada
    if isinstance(entrada, dict):
        c = campo(entrada, "command", "cmd", "argv", defecto="")
    if isinstance(c, (list, tuple)):
        partes = [str(x) for x in c]
        c = partes[0] if len(partes) == 1 else shlex.join(partes)
    return c.strip() if isinstance(c, str) else ""


def _ruta_de(entrada, rutas=()):
    """El archivo que toca: el de sus `locations` (ACP), el de su entrada, el primero de una lista (OpenCode:
    resources) o el de un cambio de archivos de Codex ({ruta: cambio} o [{path: …}])."""
    for r in rutas or ():
        if isinstance(r, str) and r.strip():
            return r.strip()
    a = archivo_de(entrada)
    if a:
        return a
    if isinstance(entrada, dict) and isinstance(entrada.get("changes"), (dict, list)):
        entrada = entrada["changes"]
    if isinstance(entrada, dict) and entrada:
        k = next(iter(entrada))
        return k.strip() if isinstance(k, str) and ("/" in k or "." in k) else ""
    if isinstance(entrada, (list, tuple)) and entrada:
        x = entrada[0]
        return (x.strip() if isinstance(x, str) else archivo_de(x))[-300:]
    return ""


def que_permiso(herramienta, entrada, kind=None, rutas=()):
    """B01: {clase, comando, ruta} de un permiso: la clase ACP de su herramienta (`kind`) si la hay; si no, su nombre
    EXACTO (_NOMBRES_PERMISO); si no, las claves de su entrada; si no, «otra». El comando tal cual (los comandos se
    ven enteros: aprobar uno sin verlo era aprobar otra cosa) y el archivo con su ruta entera (la página dice si está
    FUERA de su carpeta)."""
    n = "_".join(str(herramienta or "").strip().lower().replace("-", " ").split())
    clase = _KIND_ACP.get(str(kind or "").lower(), "") or _POR_NOMBRE.get(n, "") or _clase_por_entrada(entrada)
    if clase == "cambiar" and _clase_por_entrada(entrada) == "crear":
        clase = "crear"                                          # ACP «edit» también es crear: su entrada lo dice
    clase = clase or "otra"
    entero = _texto_comando(entrada) if clase == "comando" else ""
    if clase == "comando" and not entero and n not in _POR_NOMBRE:
        entero = str(herramienta or "").strip()                  # Kiro: su título ES el comando crudo
    comando = entero[:500]
    ruta = "" if clase in ("comando", "web") else _ruta_de(entrada, rutas)[-300:]
    q = {"clase": clase, "comando": comando, "ruta": ruta}
    if len(entero) > len(comando):
        q["cortado"] = True          # M-2: lo que no cabe se DICE (la ficha del Compañero no deja permitirlo a ciegas)
    return q


def pregunta_nativa(entrada):
    """B14/B15: (texto, [opciones]) de la pregunta propia de un motor, de las formas que mandan (Codex: {title,
    options}; OpenCode: un campo de su formulario {title|label|question, options}); cada opción, un texto o {label|
    title|value|text}. ('', []) si no trae pregunta."""
    if not isinstance(entrada, dict):
        return "", []
    texto = campo(entrada, "title", "question", "label", "header", "text", "prompt", defecto="")
    ops = []
    for o in entrada.get("options") or entrada.get("choices") or []:
        t = o if isinstance(o, str) else campo(o, "label", "title", "value", "text", defecto="") \
            if isinstance(o, dict) else ""
        if isinstance(t, str) and t.strip() and t.strip() not in ops:
            ops.append(t.strip()[:200])
    return (texto.strip()[:500] if isinstance(texto, str) else ""), ops[:12]


def campo(d, *nombres, defecto=None):
    """El primer campo presente de `nombres` en el dict `d` (tolerante a
    variantes de nombre entre versiones de un motor)."""
    if not isinstance(d, dict):
        return defecto
    for n in nombres:
        if n in d and d[n] is not None:
            return d[n]
    return defecto


class Conector:
    """Base de todos los conectores. Cada uno implementa `_abrir`, `_mandar`,
    `_parar` y, si lo necesita, `_cerrar`. Los eventos se emiten con
    `_emitir` / `_terminar` y los permisos con `_anunciar_permiso` o
    `_esperar_permiso` (protocolos donde el motor espera la respuesta)."""

    motor = "?"
    #: ¿Comparte la conversación con la terminal del motor? (la página lo dice)
    misma_conversacion = False
    #: Fable v2: ¿puede acotar UN turno a otro nivel (el de un encargo) sin cambiar la conversación? Solo los que corren
    #: una vez por mensaje (Claude Code); los demás ya tienen su nivel en un proceso abierto.
    acota_turnos = False

    def para_el_turno(self, **cfg):
        """El nivel del próximo turno (solo ese). → True si lo va a cumplir; aquí, nunca."""
        return False

    def __init__(self, cwd=None, grabar=None):
        self.cwd = os.path.abspath(cwd or os.getcwd())
        self.sesion = None
        self._grabar = grabar           # callable(direccion, texto): tráfico crudo
        self._cola = queue.Queue()
        self._candado = threading.RLock()
        self._estado = "cerrado"
        self._turno = False
        self._ajeno = False             # F4: el turno en curso lo empezó otro cliente (su terminal)
        self._permisos = {}             # id corto (p1, p2…) → responder(decision|None)
        self._de_motor = {}             # id del motor → id corto
        self._ids_permiso = itertools.count(1)
        self._uso = None
        #: Lo prohibido de leer que esta conexión negó sola (motivo_permiso): [motivo, …]. Y, si el motor confirmó su
        #: bloqueo oficial de lo prohibido al abrir (Codex: el perfil del hilo; Kiro: el agente de la página), cuál.
        self.negados = []
        self.bloqueo_secretos = ""
        self._cerrando = False
        #: E9: por qué se cancelaron los permisos pendientes («parar», «reinicio», «cierre» o '') y los que quedaron
        #: sin contestar al cerrar: [{herramienta, detalle}] (la página se lo recuerda al agente en su próximo mensaje).
        self._motivo_corte = ""
        self._pedidos = {}              # id corto → {herramienta, detalle} de lo que espera
        self._interrumpidos = []
        #: La pestaña de la página (punto F): sus variables se ponen a propósito en el motor.
        self.pestana = None
        self._canal = None                     # el proceso del motor, si el conector lo abre
        #: Tope (s) para que el motor termine de abrir: initialize, session/new… (punto H).
        self.tope_abrir = TOPE_ABRIR
        #: Monito UX · la licencia del turno: [{clase, carpeta}] que el socio dejó pasar, lo que pasó por ella y, de cada
        #: tarjeta que se puede agrupar, su grupo (por id corto).
        self._licencias, self._licencia_usos, self._agrupables = [], [], {}

    # ── operaciones públicas ────────────────────────────────────────────────
    def abrir(self, sesion=None, nueva=False):
        """Abre una conversación nueva (sesion=None), retoma la de ese id, o
        —con nueva=True— crea una NUEVA con ese número (el de la pestaña, D3-a).
        Devuelve el id oficial de la conversación. Un motor que no deja fijar el
        número de una conversación nueva contesta ErrorControl.

        Antes de seguir, si quedó un proceso HUÉRFANO de esta misma
        conversación (su servidor murió a media vuelta), lo cierra (punto G)."""
        if nueva and not sesion:
            raise ValueError("nueva=True necesita el número de la conversación")
        with self._candado:
            if self._estado != "cerrado":
                raise ErrorControl("ya está abierta")
            self._cerrando = False
            self._ped()
            self._motivo_corte, self._interrumpidos = "", []
        if sesion:
            self._limpiar_huerfano(sesion)
        self._preparar()                           # lo que puede tardar más (fuera del tope)
        sid = self._abrir_con_tope(sesion, nueva)
        self._registrar_hijo(sid)
        _CONECTORES.add(self)
        with self._candado:
            self.sesion = sid
            self._estado = "listo"
        return sid

    def _abrir_con_tope(self, sesion, nueva):
        """El saludo del motor (initialize, session/new…) con un tope de
        `tope_abrir` s (punto H). Probador real (18-nov): Kiro por ACP, sin
        TMPDIR/SHELL en su entorno, no terminaba de abrir y abrir()/mandar()
        quedaban colgados para siempre. Al vencer: error claro con lo último de
        su stderr, el proceso (y su grupo) cerrado y el conector cerrado; una
        respuesta tardía ya no lo reabre."""
        caja = {}

        def trabajo():
            try:
                caja["sid"] = self._abrir_nueva(sesion) if nueva else self._abrir(sesion)
            except BaseException as e:            # se re-lanza en el hilo de abrir()
                caja["error"] = e
        hilo = threading.Thread(target=trabajo, name="control-abrir", daemon=True)
        hilo.start()
        hilo.join(self.tope_abrir)
        if hilo.is_alive():
            ultimo = self._ultimo_stderr()
            with self._candado:
                self._cerrando = True              # su EOF no es «se perdió el motor»
            try:
                self._cerrar()                     # el proceso y su grupo, sin dejarlo a medias
            except Exception:
                pass
            hilo.join(2.0)
            raise ErrorControl("%s no abrió en %g s%s" % (
                self.motor, self.tope_abrir, ": " + ultimo if ultimo else " (sin nada en su stderr)"))
        if "error" in caja:
            raise caja["error"]
        return caja["sid"]

    def _ultimo_stderr(self):
        canal = self._canal
        try:
            return canal.stderr(6) if canal is not None and hasattr(canal, "stderr") else ""
        except Exception:
            return ""

    def mandar(self, texto):
        """Manda un mensaje. No bloquea: la respuesta llega como eventos."""
        if not isinstance(texto, str) or not texto.strip():
            raise ValueError("el mensaje está vacío")
        with self._candado:
            if self._estado == "cerrado":
                raise ErrorControl("no está abierta")
            if self._estado != "listo":
                raise ErrorControl("está trabajando: espera a que termine o páralo")
            self._puede_mandar()
            self._estado = "trabajando"
            self._turno = True
        from control import ausente          # ronda 2 · P2-b: un mensaje nuevo → se vuelve a esperar al socio
        ausente.presente(self)
        try:
            self._mandar(texto)
        except Exception as e:
            self._emitir("error", mensaje=self._motivo(e), fatal=False)
            self._terminar("error")

    def responder_permiso(self, permiso_id, decision):
        """`decision` ∈ DECISIONES_SOCIO. «permitir_turno» le llega al motor como «permitir» y, si esa tarjeta se podía
        agrupar (la conversación del monito: crear o cambiar en una carpeta de su cerebro), deja la licencia del turno.
        En cualquier otra, vale lo mismo que «permitir»."""
        if decision not in DECISIONES_SOCIO:
            raise ValueError("decisión desconocida: %r (hay: %s)" % (decision, ", ".join(DECISIONES_SOCIO)))
        turno = decision == PERMITIR_TURNO
        if turno:
            decision = "permitir"
        with self._candado:
            responder = self._permisos.pop(permiso_id, None)
            if responder is None:
                raise ErrorControl("no hay un permiso pendiente con id %r" % (permiso_id,))
            self._de_motor = {k: v for k, v in self._de_motor.items() if v != permiso_id}
            self._ped().pop(permiso_id, None)
            if not self._permisos and self._estado == "esperando_permiso":
                self._estado = "trabajando"
            grupo = self._lic()[2].pop(permiso_id, None)
            if turno and grupo and self._turno and grupo not in self._licencias:
                self._licencias.append(grupo)
        responder(decision)

    # — Monito UX · la licencia del turno —
    def _lic(self):
        """(licencias, usos, agrupables), creados si un conector viejo no pasó por __init__."""
        if not hasattr(self, "_licencias"):
            self._licencias, self._licencia_usos, self._agrupables = [], [], {}
        return self._licencias, self._licencia_usos, self._agrupables

    def _ruta_entera(self, detalle, rutas=()):
        """El archivo que toca, ENTERO y real (resuelto desde su carpeta), o ''. Recortado (archivo_de da las últimas
        300 letras) no sirve: una ruta absoluta sin su principio parecería de adentro."""
        r = ""
        for x in rutas or ():
            if isinstance(x, str) and x.strip():
                r = x.strip()
                break
        if not r and isinstance(detalle, dict):
            for k in _CLAVES_ARCHIVO:
                v = detalle.get(k)
                if isinstance(v, str) and v.strip():
                    r = v.strip()
                    break
        if not r or len(r) > 1000:
            return ""
        try:
            p = os.path.expanduser(r)
            return os.path.realpath(p if os.path.isabs(p) else os.path.join(self.cwd, p))
        except (OSError, ValueError):
            return ""

    def _grupo_de(self, herramienta, detalle, kind=None, rutas=()):
        """Si esta tarjeta se puede agrupar: {clase «escribir», carpeta (real)}; si no, None. Solo en el monito, solo
        crear y cambiar, solo dentro de una carpeta de su cerebro (no su raíz, ni su memoria, ni los insumos del
        cliente)."""
        try:
            if not self.en_escritorio() or que_permiso(herramienta, detalle, kind, rutas)["clase"] not in ("crear",
                                                                                                          "cambiar"):
                return None
            real = self._ruta_entera(detalle, rutas)
            base = os.path.realpath(self.cwd)
            if not real or not real.startswith(base.rstrip(os.sep) + os.sep):
                return None
            partes = os.path.relpath(real, base).split(os.sep)
            if len(partes) < 2 or partes[0] in _SIN_LICENCIA or any(x.startswith("_insumos") for x in partes):
                return None
            return {"clase": "escribir", "carpeta": os.path.dirname(real)}
        except Exception:
            return None

    def _por_licencia(self, herramienta, detalle, kind=None, rutas=()):
        """¿Lo deja pasar la licencia del turno? (mismo grupo, dentro de una carpeta que el socio ya dejó)."""
        lic = self._lic()[0]
        if not lic:
            return False
        g = self._grupo_de(herramienta, detalle, kind, rutas)
        if not g:
            return False
        real = self._ruta_entera(detalle, rutas)
        return any(x["clase"] == g["clase"] and (real.startswith(x["carpeta"].rstrip(os.sep) + os.sep))
                   for x in lic)

    def licencia(self):
        """Lo que el socio dejó pasar en este turno y lo que pasó por ahí: {"grupos": [{clase, carpeta}], "usadas":
        [{herramienta, detalle, archivo, que}]}, o None."""
        with self._candado:
            lic, usos, _ag = self._lic()
            if not lic:
                return None
            return {"grupos": [dict(x) for x in lic], "usadas": [dict(u) for u in usos]}

    def parar(self):
        """Corta el turno en curso. El `terminado` (motivo «parado») llega
        como evento. Sin turno en curso no hace nada."""
        with self._candado:
            if not self._turno:
                return False
            self._motivo_corte = "parar"
        self._cancelar_permisos()
        self._parar()
        return True

    # — E9 · lo que quedó sin contestar —
    def _ped(self):
        """Los pedidos que esperan (id corto → {herramienta, detalle}), creado si un conector viejo no pasó por
        __init__."""
        if not hasattr(self, "_pedidos"):
            self._pedidos, self._interrumpidos, self._motivo_corte = {}, [], ""
        return self._pedidos

    def corte(self):
        """Por qué se cancelaron los permisos pendientes: «parar», «reinicio», «cierre» o ''."""
        return getattr(self, "_motivo_corte", "") or ""

    def interrumpidos(self):
        """Los permisos que se quedaron SIN contestar porque la conversación se cerró (la página se apagó o se
        reinició): [{herramienta, detalle}]. No son un «no» del socio."""
        with self._candado:
            self._ped()
            return [dict(x) for x in self._interrumpidos]

    def estado(self):
        with self._candado:
            return self._estado

    def uso(self):
        """Lo último que el motor informó de uso (costo, tokens o % del plan),
        o None si el motor no lo da por esta vía."""
        with self._candado:
            return dict(self._uso) if self._uso else None

    def cerrar(self, reinicio=False):
        """Cierra la conversación. `reinicio`: la página local se apaga o se reinicia (pagina_v2.apagar_todo). Los
        permisos que esperaban quedan INTERRUMPIDOS (interrumpidos()), nunca negados: al agente le llega que la página
        se reinició (texto_cancelado), no que su socio dijo que no."""
        with self._candado:
            if self._estado == "cerrado" and not self._turno:
                return
            self._cerrando = True        # el EOF que viene no es «se perdió el motor»
            self._motivo_corte = "reinicio" if reinicio else "cierre"
        self._cancelar_permisos(interrumpidos=True)
        try:
            self._cerrar()
        finally:
            self._soltar_hijo()
            _CONECTORES.discard(self)
            self._terminar("parado")
            with self._candado:
                self._estado = "cerrado"

    # ── procesos hijos y entorno (puntos F y G) ─────────────────────────────
    def _entorno(self, env=None):
        """El entorno del motor: sin las variables de identidad de otra pestaña
        y con las de la pestaña de la página (control/entorno.py)."""
        from control import entorno
        return entorno.para_motor(env, self.pestana, self.motor)

    def _pid_hijo(self):
        canal = self._canal
        proc = getattr(canal, "proc", None)
        return proc.pid if proc is not None and proc.poll() is None else None

    def _registrar_hijo(self, sesion):
        pid = self._pid_hijo()
        if sesion and pid:
            from control import hijos
            try:
                hijos.registrar(self.motor, sesion, pid)
            except OSError:
                pass

    def _soltar_hijo(self):
        canal = self._canal
        proc = getattr(canal, "proc", None)
        if self.sesion and proc is not None:
            from control import hijos
            hijos.soltar(self.motor, self.sesion, proc.pid)

    def _limpiar_huerfano(self, sesion):
        from control import hijos
        try:
            if hijos.limpiar_huerfano(self.motor, sesion):
                self._emitir("error", fatal=False, mensaje="%s: cerré un proceso que había quedado "
                             "huérfano de esta conversación" % self.motor)
        except OSError:
            pass

    # ── leer eventos ────────────────────────────────────────────────────────
    def siguiente(self, timeout=None):
        """El próximo evento, o None si no llega ninguno en `timeout` s."""
        try:
            return self._cola.get(timeout=timeout)
        except queue.Empty:
            return None

    def eventos(self, timeout=None):
        """Itera los eventos hasta que pasen `timeout` s sin ninguno."""
        while True:
            ev = self.siguiente(timeout)
            if ev is None:
                return
            yield ev

    def turno(self, texto, timeout=300, al_permiso=None):
        """Atajo (pruebas, probador): manda y junta los eventos hasta el
        `terminado`. `al_permiso(evento)` → decisión (None = negar)."""
        self.mandar(texto)
        limite = time.monotonic() + timeout
        vistos = []
        while True:
            ev = self.siguiente(max(0.0, limite - time.monotonic()))
            if ev is None:
                vistos.append({"tipo": "error", "motor": self.motor, "sesion": self.sesion,
                               "mensaje": "sin respuesta en %s s" % timeout, "fatal": False})
                return vistos
            vistos.append(ev)
            if ev["tipo"] == "permiso":
                d = al_permiso(ev) if al_permiso else None
                try:
                    self.responder_permiso(ev["id"], d or "negar")
                except ErrorControl:
                    pass
            if ev["tipo"] == "terminado":
                return vistos

    # ── para los conectores ────────────────────────────────────────────────
    def _abrir(self, sesion):
        raise NotImplementedError

    def _preparar(self):
        """Lo previo al saludo que puede tardar más que el tope (p. ej. encender
        el gateway de OpenClaw la primera vez). Va FUERA de `tope_abrir`."""

    def _abrir_nueva(self, sesion):
        """Crear una conversación nueva con un número dado (abrir(id, nueva=True))."""
        raise ErrorControl("%s no deja fijar el número de una conversación nueva" % self.motor)

    def _mandar(self, texto):
        raise NotImplementedError

    def _parar(self):
        raise NotImplementedError

    def _cerrar(self):
        pass

    def _puede_mandar(self):
        """Un conector puede negarse a mandar (levanta ErrorControl) antes de
        empezar el turno: p. ej. Claude Code con su terminal abierta."""

    def _emitir(self, tipo, **campos):
        assert tipo in TIPOS, tipo
        ev = {"tipo": tipo, "motor": self.motor, "sesion": self.sesion}
        if self._ajeno:
            ev["ajeno"] = True
        ev.update(campos)
        self._cola.put(ev)
        return ev

    def _empezar_ajeno(self, texto=""):
        """F4: un turno que empezó OTRO cliente de la misma conversación (su terminal).
        Si no hay turno en curso, abre uno ajeno: estado «trabajando» (lo que mandes
        mientras tanto espera, como con un turno tuyo) y el evento `entrada` con su
        mensaje. False si ya había un turno (el nuestro o uno ajeno)."""
        with self._candado:
            if self._turno or self._estado == "cerrado":
                return False
            self._turno, self._ajeno = True, True
            self._estado = "trabajando"
        self._emitir("entrada", texto=texto or "")
        return True

    def _terminar(self, motivo, **extra):
        """Cierra el turno UNA sola vez (lo llamen el evento del motor, parar
        o la muerte del proceso)."""
        with self._candado:
            if not self._turno:
                return False
            self._turno = False
            if self._estado != "cerrado":
                self._estado = "listo"
            pend = self._permisos
            self._permisos, self._de_motor = {}, {}
            self._ped().clear()
            ajeno, self._ajeno = self._ajeno, False
            self._lic()
            self._licencias, self._licencia_usos, self._agrupables = [], [], {}     # la licencia: solo ese turno
        for r in pend.values():
            r(None)
        if ajeno:
            extra = dict(extra, ajeno=True)
        self._emitir("terminado", motivo=motivo if motivo in MOTIVOS else "fin", **extra)
        return True

    def _perdido(self, mensaje):
        """El motor se fue (proceso muerto, conexión cerrada)."""
        with self._candado:
            if self._estado == "cerrado" or self._cerrando:
                return
            self._estado = "cerrado"
        self._emitir("error", mensaje=mensaje, fatal=True)
        self._terminar("error")

    def _anunciar_permiso(self, id_motor, herramienta, detalle, opciones, responder, kind=None, rutas=()):
        """Un permiso que el motor espera. `responder(decision)` lo contesta
        por la vía del motor; decision None = cancelado (parar/cerrar). El
        evento lleva `que` (que_permiso: qué pide, de lo estructurado; B01), con
        `kind` y `rutas` si su vía los da (ACP: la clase y las locations).

        El evento lleva un id CORTO y seguro (p1, p2, …), nunca el del motor:
        VERIFICADO desde la página (18-nov), Cursor manda ids con salto de línea
        ("call-…-1\\nfc_…_0") y la página los rechazaba con 400, así que la
        tarjeta no se podía contestar. El id del motor se queda aquí adentro
        (en `responder` y en el mapa para `_olvidar_permiso`).

        B08 (cacería 19-nov): una herramienta de los servidores MCP de Workspace (y solo ellas: control/propias) se
        aprueba aquí, sin tarjeta, como en la terminal. Aquí el cliente que contesta es Workspace (ACP, OpenCode).
        Modo escritorio (decisión del dueño, 21-nov): en la conversación del monito, sin tarjeta SOLO lo libre de ahí
        (propias.libre_en_escritorio: ver y señalar, preguntar, mostrar_archivo, memoria_nota y leer en su carpeta);
        todo lo demás sale como tarjeta aunque sea de Workspace."""
        with self._candado:
            cerrando = bool(self._cerrando) and self.corte() in INTERRUMPIDO
            if cerrando:                # E9: llegó mientras se cierra: ni tarjeta ni «no»; interrumpido
                self._ped()
                self._interrumpidos.append({"herramienta": herramienta or "?", "detalle": corto(detalle)})
        if cerrando:
            responder(None)
            return
        if self.en_escritorio():        # E8: en el monito no hay ayudantes (se niega con su porqué, sin tarjeta)
            try:
                from control import propias
                E = propias.politica_escritorio()
                if E.es_ayudante(herramienta):
                    hid = "ayudantes-%d" % (abs(hash(str(id_motor))) % 10 ** 8)
                    self._emitir("herramienta", id=hid, nombre="Workspace no lanzó ayudantes desde Compañero",
                                 fase="empieza", detalle=corto(detalle))
                    self._emitir("herramienta", id=hid, nombre="Workspace no lanzó ayudantes desde Compañero",
                                 fase="falla", detalle=E.SIN_AYUDANTES)
                    responder("negar")
                    return
            except Exception:
                pass
        motivo = None
        if "permitir" in opciones:
            try:
                from control import propias
                libre = propias.libre_en_escritorio(herramienta, detalle, kind, rutas, carpeta=self.cwd) \
                    if self.en_escritorio() else propias.de_workspace(herramienta, detalle)
                if libre and self.en_escritorio() and not propias.herramienta(herramienta):
                    # leer en su carpeta es libre, pero no un secreto de su carpeta (Monito UX: antes un Read de su
                    # .env pasaba por libre antes de mirar lo prohibido)
                    motivo = self._prohibido(herramienta, detalle, kind, rutas)
                    libre = not motivo
                if libre:
                    responder("permitir")
                    return
            except Exception:
                pass
        # Cierre de la auditoría (19-nov): lo prohibido de leer (llaves y secretos) se niega solo, como el aviso de
        # antes de cada herramienta en la terminal: por la página Codex, Cursor y Kiro no corren avisos y este pedido
        # llega aquí (un comando escalado de Codex, un `cat` de Cursor, una lectura de Kiro fuera de su carpeta).
        motivo = motivo or self._prohibido(herramienta, detalle, kind, rutas)
        if motivo:
            self.negados.append(motivo)
            hid = "prohibido-%d" % len(self.negados)
            self._emitir("herramienta", id=hid, nombre="Workspace negó leer " + motivo, fase="empieza",
                         detalle=corto(detalle))
            self._emitir("herramienta", id=hid, nombre="Workspace negó leer " + motivo, fase="falla",
                         detalle="Workspace no deja leer %s desde un agente." % motivo)
            responder("negar")
            return
        # Monito UX · la licencia del turno: lo del mismo tipo en una carpeta que el socio ya dejó, en este turno
        if "permitir" in opciones and self._por_licencia(herramienta, detalle, kind, rutas):
            with self._candado:
                self._lic()[1].append({"herramienta": herramienta or "?", "detalle": corto(detalle),
                                       "archivo": archivo_de(detalle), "que": que_permiso(herramienta, detalle, kind,
                                                                                         rutas)})
            responder("permitir")
            return
        from control import ausente          # ronda 2 · P2-b: el pase de un solo uso de «Permitir y seguir»
        if "permitir" in opciones and ausente.pase(self, herramienta, detalle):
            responder("permitir")
            return
        grupo = self._grupo_de(herramienta, detalle, kind, rutas) if "permitir" in opciones else None
        with self._candado:
            pid = "p%d" % next(self._ids_permiso)
            self._permisos[pid] = responder
            self._ped()[pid] = {"herramienta": herramienta or "?", "detalle": corto(detalle)}
            self._de_motor[str(id_motor)] = pid
            if grupo:
                self._lic()[2][pid] = grupo
            if self._estado == "trabajando":
                self._estado = "esperando_permiso"
        base = os.path.realpath(self.cwd)
        self._emitir("permiso", id=pid, herramienta=herramienta or "?", detalle=corto(detalle),
                     archivo=archivo_de(detalle), opciones=[o for o in DECISIONES if o in opciones],
                     que=que_permiso(herramienta, detalle, kind, rutas),
                     grupo={"clase": grupo["clase"], "carpeta": os.path.relpath(grupo["carpeta"], base)} if grupo
                     else None)
        ausente.vigilar(self, pid, herramienta, detalle, que=que_permiso(herramienta, detalle, kind, rutas),
                        archivo=archivo_de(detalle), corto=corto)      # P2-b: a los 3 min sin respuesta, para después

    def en_escritorio(self):
        """¿Es la conversación del monito de escritorio (su pestaña «escritorio»)?"""
        return str((getattr(self, "pestana", None) or {}).get("ws") or "") == "escritorio"

    @staticmethod
    def _prohibido(herramienta, detalle, kind=None, rutas=()):
        """El motivo si el permiso pide leer lo prohibido (arquitectura/secretos.motivo_permiso), o ''."""
        try:
            from arquitectura import secretos
            return secretos.motivo_permiso(herramienta, detalle, kind, rutas)
        except Exception:
            return ""

    def _esperar_permiso(self, pid, herramienta, detalle, opciones=DECISIONES, kind=None, rutas=()):
        """Igual, pero bloquea al llamador (un hilo del protocolo) hasta la
        respuesta. Devuelve la decisión o None (cancelado)."""
        hecho = threading.Event()
        caja = {}

        def responder(d):
            caja["d"] = d
            hecho.set()
        self._anunciar_permiso(pid, herramienta, detalle, opciones, responder, kind=kind, rutas=rutas)
        hecho.wait()
        return caja.get("d")

    def permisos_pendientes(self):
        """Los ids (p1, p2…) de los permisos que el motor sigue esperando: la página muestra solo esos. B09 (cacería
        19-nov): dos pedidos a la vez quedaban aquí y la página veía uno; uno contestado en su terminal se olvida
        aquí (_olvidar_permiso) sin avisar."""
        with self._candado:
            return list(self._permisos)

    def _olvidar_permiso(self, id_motor):
        """Un permiso que se contestó por otro lado (la terminal del motor);
        llega con el id DEL MOTOR."""
        with self._candado:
            pid = self._de_motor.pop(str(id_motor), None)
            if pid:
                self._permisos.pop(pid, None)
                self._ped().pop(pid, None)
            if not self._permisos and self._estado == "esperando_permiso":
                self._estado = "trabajando"

    def _cancelar_permisos(self, interrumpidos=False):
        """Cancela los permisos que esperan (su `responder` recibe None; por qué: corte()). `interrumpidos`: se cierra
        la conversación; quedan anotados como sin contestar."""
        with self._candado:
            pend = self._permisos
            self._permisos, self._de_motor = {}, {}
            pedidos = self._ped()
            if interrumpidos:
                self._interrumpidos.extend(dict(pedidos[p]) for p in pend if p in pedidos)
            pedidos.clear()
            if self._estado == "esperando_permiso":
                self._estado = "trabajando"
        for r in pend.values():
            r(None)

    def _poner_uso(self, **datos):
        datos = {k: v for k, v in datos.items() if v is not None}
        if datos:
            with self._candado:
                self._uso = dict(self._uso or {}, **datos)

    @staticmethod
    def _motivo(e):
        return "%s: %s" % (type(e).__name__, e) if not isinstance(e, ErrorControl) else str(e)
