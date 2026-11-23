#!/usr/bin/env python3
"""WORKSPACE · arquitectura/nucleo_mcp — el MCP núcleo (servidor `workspace`, F6).

Las herramientas de la pestaña, preaprobadas en el paquete por sesión de cada motor. La lista y la
entrada de cada una salen de arquitectura/mcp_nucleo.json (el contrato): se valida con él antes de
hacer nada. Debajo usan lo mismo que el comando de hoy, para que no haya dos dueños:

  · memoria_nota, memoria_checkpoint, memoria_ver: las de memoria_mcp (memoria.py y
    session_continuity: = `workspace memoria nota|checkpoint|ver`);
  · memoria_buscar: memoria_buscar.py sobre memory_index (solo lee; la única que mira más allá de la
    pestaña: todo el cerebro, o el de otro agente de esta computadora);
  · pendientes: lo vigente de la ficha de la pestaña y STATE/PENDIENTES.md (lo que enseña la página);
  · skills_lista, skill_leer: skills/ del cerebro (skill_meta, como la página);
  · tarea_actual: el registro de eventos de la pestaña (arquitectura/registro.py);
  · preguntar: la pregunta al registro (la página y el hub la enseñan en la caja de escribir, con sus opciones como
    botones) y, si el cliente ofrece formularios (MCP elicitation), el formulario del motor;
  · reportar_avance: pasos.aplicar (= `workspace pasos <id> …`; su «pide» admite opciones);
  · usar_skill, personalizar y mostrar_archivo: interfaz_agente (= `workspace pasos usar|personalizar|archivo …`, el
    respaldo).

Dónde escribe: SOLO en la pestaña de la ventana que abrió al motor (memoria_mcp.contexto: la corrida
viva y, sin ella, WORKSPACE_BRAIN + WORKSPACE_WS). Ninguna herramienta acepta cerebro, pestaña ni motor.

Sus instrucciones (initialize) llevan el manual y, donde la ficha del motor lo diga (nucleo.al_abrir y
nucleo.tono = «mcp»), el tono y el paquete de la pestaña (arquitectura/nucleo.py).

Protocolo: JSON-RPC 2.0 por stdio, un mensaje por línea; stdout lleva solo el protocolo. Stdlib.
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:           # corre con `python -I`: sin la carpeta del script
    sys.path.insert(0, RAIZ_REPO)

import memoria_mcp as MM  # noqa: E402
from arquitectura import contrato, nucleo, registro  # noqa: E402

SERVIDOR = "workspace"
VERSION = "2"
#: El argumento que el plugin de OpenClaw le suma a cada llamada con la clave de su sesión (generar.CLAVE_SESION_OPENCLAW).
CLAVE_SESION = "_workspace_sesion"
MAX_SKILL = 64 * 1024
MAX_SKILLS = 200
MAX_PENDIENTES = 40


class Fallo(Exception):
    """Un error de la herramienta, con su código del contrato."""

    def __init__(self, codigo, texto):
        super().__init__(texto)
        self.codigo = codigo


def _contrato():
    return contrato.mcp_nucleo()


def herramientas():
    """tools/list, tal cual el contrato."""
    out = []
    for h in _contrato()["herramientas"]:
        out.append({"name": h["nombre"], "description": h["hace"], "inputSchema": h["entrada"],
                    "annotations": {"readOnlyHint": bool(h.get("solo_lee"))}})
    return out


def _esquema(nombre):
    for h in _contrato()["herramientas"]:
        if h["nombre"] == nombre:
            return h["entrada"]
    return None


def _de_rechazo(e):
    """Un Rechazo de memoria_mcp, con el código del contrato que le toca."""
    t = str(e)
    if t.startswith("Conflicto de revisión"):
        return Fallo("CONFLICTO", t)
    if "no existe" in t:
        return Fallo("NO_ENCONTRADO", t)
    return Fallo("ENTRADA_INVALIDA", t)


def _pestana_registro(run, env):
    """La pestaña del registro de eventos: la misma que usa el hook del paquete (la ventana, si se sabe)."""
    return (MM._valor(env, "WORKSPACE_WID") or MM._valor(env, "WORKSPACE_WS") or run.get("tab") or "").strip()


# ── las herramientas ────────────────────────────────────────────────────────
#: Modo escritorio: la nota que se guarda desde el monito lleva su origen (pudo salir de lo que había en pantalla, que
#: escribieron otros): al leerla después, es un dato citado, no una instrucción.
ORIGEN_ESCRITORIO = "[desde el monito] "


def memoria_nota(args, run, srv):
    try:
        if str(MM._valor(srv.env, "WORKSPACE_VIA") or "") == "escritorio" and isinstance(args, dict) \
                and isinstance(args.get("texto"), str) and not args["texto"].startswith(ORIGEN_ESCRITORIO):
            import memoria
            cabe = memoria.MAX_TEXTO - len(ORIGEN_ESCRITORIO)
            if len(" ".join(args["texto"].split())) > cabe:     # con su marca no cabría: se dice el tope de aquí
                raise MM.Rechazo("texto es muy largo para una nota desde Compañero (máximo %d caracteres): acórtalo "
                                 "o divídelo" % cabe)
            args = dict(args, texto=ORIGEN_ESCRITORIO + args["texto"])
        return MM.guardar_nota(args, run)
    except MM.Rechazo as e:
        raise _de_rechazo(e)


def memoria_checkpoint(args, run, srv):
    try:
        return MM.guardar_resumen(args, run)
    except MM.Rechazo as e:
        raise _de_rechazo(e)


def memoria_ver(args, run, srv):
    try:
        texto = MM.ver_memoria(args, run)
    except MM.Rechazo as e:
        raise _de_rechazo(e)
    return texto.replace("expected_revision para guardar_resumen", "expected_revision para memoria_checkpoint")


def _cerebro_de_agente(nombre):
    """El cerebro de un agente registrado en esta computadora (por su nombre), o None."""
    try:
        import agent_state
        for a in agent_state.snapshot().registered():
            if nombre.lower() in (str(a.get("name") or "").lower(), str(a.get("display") or "").lower()):
                return a.get("brain") or None
    except Exception:
        return None
    return None


def memoria_buscar(args, run, srv):
    """Busca en la memoria (memoria_buscar.py): la de este agente o, con `agente`, la de otro de esta computadora
    (solo lee). `pestana: "esta"` es la de ahora."""
    import memoria_buscar as MB
    brain, de_quien = run["brain"], ""
    agente = (args.get("agente") or "").strip()
    if agente:
        otro = _cerebro_de_agente(agente)
        if not otro or not os.path.isdir(otro):
            raise Fallo("NO_ENCONTRADO", "no hay un agente «%s» en esta computadora" % agente)
        if os.path.realpath(otro) != os.path.realpath(brain):
            brain, de_quien = otro, agente
    pestana = (args.get("pestana") or "").strip() or None
    if pestana == "esta":
        pestana = run["tab"]
    res = MB.buscar(brain, args["consulta"], tipo=args.get("tipo"), pestana=pestana, desde=args.get("desde"),
                    hasta=args.get("hasta"), fuente=args.get("fuente") or "todo", top=args.get("max") or MB.TOP)
    return MB.como_texto(res, args["consulta"], de_quien)


def pendientes(args, run, srv):
    import memoria
    brain, tab = run["brain"], run["tab"]
    try:
        ficha = memoria.Ficha(memoria._leer_vista(memoria.ficha_path(brain, tab)))
        propios = [v for v in memoria.vigente(ficha) if v.get("tipo") == "pendiente"]
    except (ValueError, OSError):
        propios = []
    out = []
    if propios:
        out.append("De esta pestaña (ciérralos con memoria_nota tipo hecho y cierra):")
        out += ["  - %s (%s): %s" % (v["id"], (v.get("fecha") or "")[5:], v["texto"]) for v in propios[:MAX_PENDIENTES]]
    del_cerebro = []
    try:
        import localhost_front as LF
        ruta = os.path.join(brain, *LF.RUTA_PEND.split("/"))
        if os.path.isfile(ruta):
            del_cerebro = [i for i in LF._items(LF._leer(ruta)) if not i.get("hecho") and not i.get("pausa")]
    except Exception:
        del_cerebro = []
    if del_cerebro:
        out.append("Del cerebro (STATE/PENDIENTES.md):")
        for i in del_cerebro[:MAX_PENDIENTES]:
            extra = " · ".join(x for x in (i.get("quien"), i.get("fecha")) if x)
            out.append("  - %s%s" % (i["texto"], (" [%s]" % extra) if extra else ""))
    return "\n".join(out) if out else "No hay pendientes abiertos."


def _skills(brain):
    """[(rel, carpeta, frontmatter)] de skills/ del cerebro."""
    import skill_meta
    raiz = os.path.join(brain, "skills")
    out = []
    if not os.path.isdir(raiz):
        return out
    for d in skill_meta.iter_skill_dirs(raiz):
        rel = os.path.relpath(d, raiz).replace(os.sep, "/")
        out.append((rel, d, _frontmatter(os.path.join(d, "SKILL.md"))))
        if len(out) >= MAX_SKILLS:
            break
    return out


def _frontmatter(ruta):
    import skill_meta
    try:
        with open(ruta, encoding="utf-8", errors="replace") as fh:
            bloque = skill_meta._frontmatter(fh.read(skill_meta.FM_READ_BYTES)) or ""
    except OSError:
        return {}
    out = {}
    for ln in bloque.split("\n"):
        if ":" in ln and not ln.startswith((" ", "\t", "-")):
            k, v = ln.split(":", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


def skills_lista(args, run, srv):
    filas = []
    for rel, _d, fm in _skills(run["brain"]):
        partes = rel.split("/")
        cat = partes[0] + "/" if len(partes) > 1 else ""
        nombre = fm.get("name") or partes[-1]
        desc = " ".join(str(fm.get("description") or "").split())[:280]
        filas.append("  - %s%s%s" % (cat, nombre, (" — " + desc) if desc else ""))
    if not filas:
        return "Este cerebro no tiene skills todavía (skills/)."
    return "Skills del cerebro (léelas con skill_leer):\n" + "\n".join(filas)


def skill_leer(args, run, srv):
    pedida = args["skill"].strip("/")
    if ".." in pedida.split("/"):
        raise Fallo("ENTRADA_INVALIDA", "skill: sin «..»")
    for rel, d, fm in _skills(run["brain"]):
        if pedida in (rel, rel.split("/")[-1], fm.get("name")):
            ruta = os.path.join(d, "SKILL.md")
            try:
                with open(ruta, encoding="utf-8", errors="replace") as fh:
                    texto = fh.read(MAX_SKILL + 1)
            except OSError:
                break
            if len(texto) > MAX_SKILL:
                texto = texto[:MAX_SKILL] + "\n[… recortado]"
            otros = sorted(os.path.relpath(os.path.join(b, f), d).replace(os.sep, "/")
                           for b, _ds, fs in os.walk(d) for f in fs if f != "SKILL.md" and not f.startswith("."))
            pie = ("\n\nOtros archivos de la skill (léelos con tus herramientas): " + ", ".join(otros[:40])) if otros else ""
            return "skills/%s/SKILL.md\n\n%s%s" % (rel, texto, pie)
    raise Fallo("NO_ENCONTRADO", "no hay una skill «%s» en este cerebro (míralas con skills_lista)" % pedida)


def tarea_actual(args, run, srv):
    tarea = " ".join(str(args.get("tarea") or "").split())
    ok = registro.anotar(run["brain"], _pestana_registro(run, srv.env), registro.TAREA, run.get("engine") or "", "",
                         {"tarea": tarea})
    return json.dumps({"ok": bool(ok)})


def _esquema_formulario(tipo, opciones):
    if tipo == "confirmar":
        prop = {"type": "boolean", "title": "Respuesta"}
    elif tipo == "opcion":
        prop = {"type": "string", "title": "Respuesta", "enum": list(opciones)}
    else:
        prop = {"type": "string", "title": "Respuesta"}
    return {"type": "object", "properties": {"respuesta": prop}, "required": ["respuesta"]}


def _IA():
    import interfaz_agente
    return interfaz_agente


def _con_formulario(srv):
    """¿La pregunta va como formulario del motor (MCP elicitation)? Solo si el cliente lo ofrece Y no corre para la
    página. B13 (cacería 19-nov): `claude -p`, y Kiro y Cursor por ACP, anuncian elicitation pero en la página no lo
    pueden mostrar: lo cancelaban en 3-18 ms, el registro la daba por contestada y la caja nunca la mostraba. Para la
    página (WORKSPACE_VIA=pagina, nucleo_para) va al chat: la caja enmarcada con sus botones. Lo mismo en el monito de
    escritorio (WORKSPACE_VIA=escritorio): su burbuja la enseña con botones."""
    from arquitectura import modo_chat
    return bool(srv.formulario) and not modo_chat.es_chat(MM._valor(srv.env, "WORKSPACE_VIA"))


def preguntar(args, run, srv):
    """Una pregunta al socio (interfaz_agente.preguntar: la caja de escribir de la página y del hub, con sus opciones
    como botones). Sin `tipo`: con opciones, de opción; si no, abierta."""
    IA = _IA()
    try:
        pregunta, tipo, opciones = IA.forma_de_pregunta(args["pregunta"], args.get("opciones"), args.get("tipo"))
        via = "formulario" if _con_formulario(srv) else "chat"
        brain, pestana, motor = run["brain"], _pestana_registro(run, srv.env), run.get("engine") or ""
        pid = IA.preguntar(brain, pestana, motor, pregunta, opciones, tipo, args.get("paso") or "", via)
    except IA.Error as e:
        raise Fallo(e.codigo, str(e))
    if via == "chat":
        return json.dumps({"en_chat": True, "id": pid, "indicacion": IA.indicacion(srv.env, bool(opciones))},
                          ensure_ascii=False)
    r = srv.pedir("elicitation/create", {"message": pregunta,
                                         "requestedSchema": _esquema_formulario(tipo, opciones)})
    accion = (r or {}).get("action")
    valor = ((r or {}).get("content") or {}).get("respuesta")
    if accion == "accept" and valor is not None:
        texto = ("sí" if valor else "no") if isinstance(valor, bool) else " ".join(str(valor).split())[:2000]
        registro.anotar(brain, pestana, registro.RESPUESTA, motor, "",
                        {"id": pid, "respuesta": texto, "via": "formulario"})
        return json.dumps({"respuesta": texto, "id": pid}, ensure_ascii=False)
    registro.anotar(brain, pestana, registro.RESPUESTA, motor, "", {"id": pid, "via": "formulario",
                                                                    "motivo": str(accion or "sin_respuesta")})
    return json.dumps({"cancelada": True, "id": pid})


def reportar_avance(args, run, srv):
    try:
        return MM.reportar_avance(args, run)
    except MM.Rechazo as e:
        raise _de_rechazo(e)


def usar_skill(args, run, srv):
    """Activa una skill a la vista del socio, igual que «Usar» en la página (interfaz_agente.usar_skill): su ejecución
    con su proceso y su barra. Devuelve su id y su SKILL.md: el agente la sigue en este mismo turno."""
    IA = _IA()
    pestana = (MM._valor(srv.env, "WORKSPACE_WS") or run.get("tab") or "").strip()
    try:
        r = IA.usar_skill(run["brain"], IA.agente_de(run["brain"], srv.env), pestana, run.get("engine") or "",
                          args["skill"], args.get("texto") or "")
    except IA.Error as e:
        raise Fallo(e.codigo, str(e))
    return "%s «%s» (ejecucion %s): el socio ya ve su proceso. %s\n\n%s\n\n%s" % (
        "Ya estaba activada" if r.get("ya") else "Empezó", r["skill"], r["ejecucion"], IA.como_seguir(r["ejecucion"]),
        r["ruta"], r["skill_md"])


def personalizar(args, run, srv):
    """Su color, su monito o su nombre en la página (interfaz_agente.personalizar): cambia en vivo."""
    IA = _IA()
    try:
        r = IA.personalizar(IA.agente_de(run["brain"], srv.env), args.get("color"), args.get("forma"),
                            args.get("nombre"))
    except IA.Error as e:
        raise Fallo(e.codigo, str(e))
    return json.dumps(dict(r, ok=True), ensure_ascii=False)


def mostrar_archivo(args, run, srv):
    """Modo chat: un archivo del cerebro como tarjeta en el chat (interfaz_agente.mostrar_archivo), con «Abrir» y
    «Mostrar en la carpeta». Uno de fuera del cerebro, nunca."""
    IA = _IA()
    try:
        r = IA.mostrar_archivo(run["brain"], _pestana_registro(run, srv.env), run.get("engine") or "", args["ruta"],
                               args.get("titulo") or "")
    except IA.Error as e:
        raise Fallo(e.codigo, str(e))
    return json.dumps(dict(r, ok=True, indicacion=IA.indicacion_archivo(srv.env)), ensure_ascii=False)


LLAMAR = {"memoria_nota": memoria_nota, "memoria_checkpoint": memoria_checkpoint, "memoria_ver": memoria_ver,
          "memoria_buscar": memoria_buscar, "pendientes": pendientes, "skills_lista": skills_lista, "skill_leer": skill_leer,
          "tarea_actual": tarea_actual, "preguntar": preguntar, "reportar_avance": reportar_avance,
          "usar_skill": usar_skill, "personalizar": personalizar, "mostrar_archivo": mostrar_archivo}


# ── el servidor ─────────────────────────────────────────────────────────────
class Servidor:
    """Un cliente por stdio. `formulario`: el cliente ofreció elicitation en initialize."""

    def __init__(self, entrada=None, salida=None, env=None, cadena=None, diagnosticar=True):
        self.entrada = entrada
        self.salida = salida
        self.env = os.environ if env is None else env
        self.cadena = cadena
        self.formulario = False
        self.diagnosticar = diagnosticar   # el doctor lo prueba en su proceso: eso no es un motor de verdad
        self._cliente = ""
        self._n = 0
        self._despues = []              # lo que llegó mientras se esperaba una respuesta del cliente

    # -- E/S
    def _escribir(self, msg):
        self.salida.write(json.dumps(msg, ensure_ascii=False).encode("utf-8") + b"\n")
        self.salida.flush()

    def _leer(self):
        """El próximo mensaje: dict, {} si no se entiende, None al cerrarse la entrada."""
        while True:
            linea = self.entrada.readline(MM.MAX_LINEA + 1)
            if not linea:
                return None
            if len(linea) > MM.MAX_LINEA:
                while linea and not linea.endswith(b"\n"):      # el resto de esa línea se descarta
                    linea = self.entrada.readline(MM.MAX_LINEA + 1)
                return {}
            texto = linea.decode("utf-8", "replace").strip()
            if not texto:
                continue
            try:
                msg = json.loads(texto)
            except ValueError:
                return {}
            return msg if isinstance(msg, dict) else {}

    def pedir(self, metodo, params):
        """Una petición al cliente (elicitation) y su respuesta; None si se cerró o contestó con error."""
        self._n += 1
        mid = "ws-%d" % self._n
        self._escribir({"jsonrpc": "2.0", "id": mid, "method": metodo, "params": params})
        while True:
            msg = self._leer()
            if msg is None:
                return None
            if msg.get("id") == mid and "method" not in msg:
                return msg.get("result") if "result" in msg else None
            if msg.get("method") == "ping" and "id" in msg:
                self._escribir(MM._ok(msg["id"], {}))
            elif msg.get("method") and "id" in msg:
                self._despues.append(msg)

    # -- protocolo
    def atender(self, msg):
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return MM._error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
        metodo, mid = msg.get("method"), msg.get("id")
        if not isinstance(metodo, str) or "id" not in msg:
            return None
        params = msg.get("params") or {}
        if not isinstance(params, dict):
            return MM._error(mid, -32602, "params tiene que ser un objeto")
        if metodo == "initialize":
            cap = params.get("capabilities") or {}
            self.formulario = isinstance(cap, dict) and isinstance(cap.get("elicitation"), dict)
            cliente = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
            self._diagnostico("initialize", cliente=str(cliente.get("name") or "")[:60],
                              version=str(cliente.get("version") or "")[:30], formularios=self.formulario,
                              perfil=MM._valor(self.env, "WORKSPACE_HERMES_PERFIL")[:60])
            pedida = params.get("protocolVersion")
            return MM._ok(mid, {"protocolVersion": pedida if pedida in MM.PROTOCOLOS else MM.PROTOCOLOS[0],
                                "capabilities": {"tools": {"listChanged": False}},
                                "serverInfo": {"name": SERVIDOR, "title": "Workspace", "version": VERSION},
                                "instructions": self.instrucciones()})
        if metodo == "ping":
            return MM._ok(mid, {})
        if metodo == "tools/list":
            return MM._ok(mid, {"tools": herramientas()})
        if metodo == "tools/call":
            texto, es_error = self.llamar(params.get("name"), params.get("arguments"))
            if texto is None:
                return MM._error(mid, -32602, "Herramienta desconocida: %r (hay: %s)"
                                 % (params.get("name"), ", ".join(sorted(LLAMAR))))
            return MM._ok(mid, {"content": [{"type": "text", "text": texto}], "isError": es_error})
        return MM._error(mid, -32601, "Method not found: %s" % metodo)

    def _diagnostico(self, evento, **datos):
        """Un renglón para la verificación (salud.diagnostico): qué cliente, qué herramienta, cómo salió."""
        if not self.diagnosticar:
            return
        try:
            from arquitectura import salud
            self._cliente = datos.get("cliente") or self._cliente
            salud.diagnostico(evento, cliente=self._cliente, motor=MM._valor(self.env, "WORKSPACE_ENGINE"),
                              via=MM._valor(self.env, "WORKSPACE_VIA") or "terminal",
                              **{k: v for k, v in datos.items() if k != "cliente"})
        except Exception:
            pass

    def instrucciones(self):
        try:
            run = MM.contexto(self.env, self.cadena)
        except Exception:
            return nucleo.MANUAL
        return nucleo.instrucciones(run["brain"], run["tab"], run.get("engine") or MM._valor(self.env, "WORKSPACE_ENGINE"))

    def _pestana_hermes(self, nombre):
        """cable-hermes: el MCP del perfil de un agente de Hermes (WORKSPACE_HERMES_PERFIL) lo abre su gateway UNA vez
        por perfil, sin pestaña en su entorno: la de CADA llamada sale de la corrida viva de ese perfil
        (engines/hermes.pestana_para_mcp). Sin una clara, ninguna (SIN_PESTANA): nunca la de la llamada anterior."""
        perfil = MM._valor(self.env, "WORKSPACE_HERMES_PERFIL")
        if not perfil:
            return
        try:
            from engines import hermes as _h
            d = _h.pestana_para_mcp(perfil, nombre)
        except Exception:
            d = {}
        for k in ("WORKSPACE_BRAIN", "WORKSPACE_WS", "WORKSPACE_WID", "ZENITH_WS", "WORKSPACE_AGENT_NAME",
                  "WORKSPACE_VIA"):
            self.env.pop(k, None)
        self.env.update(d)

    def _de_su_sesion(self, args):
        """OpenClaw: el gateway abre este servidor por sesión pero sin el entorno de la pestaña ni decirle de qué
        sesión es (VERIFICADO 2026.10.7: ni entorno, ni _meta). El aviso before_tool_call del plugin de Workspace le
        suma a cada llamada la clave de SU sesión (ctx.sessionKey, la del gateway, no la del modelo), y aquí se halla la
        pestaña con el índice número → pestaña que dejó Workspace al abrirla. → (args sin esa clave, entorno de la
        pestaña o None). Solo si este proceso no sabe ya su pestaña, y solo una sesión de OpenClaw que abrió
        Workspace."""
        if not isinstance(args, dict) or CLAVE_SESION not in args:
            return args, None
        args = dict(args)
        clave = str(args.pop(CLAVE_SESION) or "").strip()
        if MM._valor(self.env, "WORKSPACE_WID") or MM._valor(self.env, "WORKSPACE_WS"):
            return args, None
        fila = registro.indice(clave)
        if not fila or fila.get("motor") != "openclaw":
            return args, None
        env = dict(self.env)
        env.update(WORKSPACE_BRAIN=fila["brain"], WORKSPACE_WID=fila["pestana"],
                   WORKSPACE_WS=fila.get("ws") or fila["pestana"], WORKSPACE_ENGINE=fila["motor"])
        if fila.get("via"):
            env["WORKSPACE_VIA"] = fila["via"]
        return args, env

    def llamar(self, nombre, args):
        """tools/call → (texto, es_error); (None, True) si la herramienta no existe. Nunca lanza."""
        if nombre not in LLAMAR:
            return None, True
        args = {} if args is None else args
        antes = self.env
        try:
            args, env = self._de_su_sesion(args)
            if env is not None:
                self.env = env
            return self._llamar(nombre, args)
        finally:
            self.env = antes

    def _llamar(self, nombre, args):
        try:
            errs = contrato.validar(args, _esquema(nombre))
            if errs:
                raise Fallo("ENTRADA_INVALIDA", "; ".join(errs[:4]))
            self._pestana_hermes(nombre)
            try:
                run = MM.contexto(self.env, self.cadena)
            except MM.Rechazo as e:
                raise Fallo("SIN_PESTANA", str(e))
            MM._fijar(run)
            texto = LLAMAR[nombre](args, run, self)
            self._diagnostico("llamada", herramienta=nombre, resultado="ok", motor_run=run.get("engine") or "")
            try:                               # para el doctor: el MCP de este motor responde (a lo más 1/min)
                from arquitectura import salud
                salud.marcar(run.get("engine") or MM._valor(self.env, "WORKSPACE_ENGINE"), "mcp",
                             MM._valor(self.env, "WORKSPACE_VIA") or "terminal",
                             cerebro=run.get("brain") or MM._valor(self.env, "WORKSPACE_BRAIN") or "")
            except Exception:
                pass
            return texto, False
        except Fallo as e:
            self._diagnostico("llamada", herramienta=nombre, resultado=e.codigo)
            return "[%s] %s" % (e.codigo, e), True
        except Exception as e:                     # jamás un traceback al motor
            self._diagnostico("llamada", herramienta=nombre, resultado="NO_DISPONIBLE")
            MM._log("núcleo · %s: %s: %s" % (nombre, type(e).__name__, e))
            return "[NO_DISPONIBLE] Error interno de Workspace (%s). Avísale al socio en una línea." \
                % type(e).__name__, True

    def servir(self):
        while True:
            msg = self._despues.pop(0) if self._despues else self._leer()
            if msg is None:
                return 0
            if not msg:
                self._escribir(MM._error(None, -32700, "Parse error"))
                continue
            try:
                resp = self.atender(msg)
            except Exception as e:                 # defensa: nunca un traceback
                MM._log("núcleo · %s: %s" % (type(e).__name__, e))
                resp = MM._error(msg.get("id"), -32603, "Internal error")
            if resp is not None:
                self._escribir(resp)


def main():
    real = sys.stdout.buffer
    sys.stdout = sys.stderr              # un print de un módulo no ensucia el protocolo
    try:
        return Servidor(sys.stdin.buffer, real).servir()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
