#!/usr/bin/env python3
"""WORKSPACE · interfaz_agente — lo que el agente le dice a Workspace para que el socio lo vea en la página y el hub:

  · preguntar: una pregunta con opciones (o de sí/no, o abierta). Sale en la caja de escribir del socio, enmarcada en
    el color del agente, con sus opciones como botones (Q-2); la respuesta le llega al agente como su próximo mensaje;
  · usar_skill: activa una skill del cerebro A LA VISTA, igual que «Usar» en la página: su ejecución (pasos.py) con
    «Empezó …», su proceso y su barra; devuelve el id de la ejecución y lo que dice su SKILL.md;
  · personalizar: su color, su monito (forma) o el nombre con que lo ve el socio en esta computadora (los mismos de
    la página: localhost_front.apariencia y .nombre); la página lo cambia en vivo;
  · mostrar_archivo (modo chat): un archivo DENTRO de su cerebro, como tarjeta en el chat con «Abrir» y «Mostrar en la
    carpeta» (el equivalente en chat del menú «1 abrir / 2 revelar» de la terminal); uno de fuera, nunca;
  · el avance de una skill sigue en pasos.py (`workspace pasos <id> plan|ahora|hecho|pide|fin`), y su «pide» admite
    opciones (`--opcion`).

Iguales en todos los motores, por dos caminos que hacen LO MISMO:
  · el MCP núcleo (arquitectura/nucleo_mcp: preguntar, usar_skill, personalizar, reportar_avance), donde el motor lo
    tiene;
  · el comando de respaldo, donde no: `workspace pasos preguntar|usar|personalizar|archivo …` (dentro de `workspace pasos`,
    preaprobado: no pide permiso nuevo). Lo de la pestaña sale del entorno que pone Workspace al abrir el motor
    (WORKSPACE_BRAIN, WORKSPACE_WID/WS, WORKSPACE_ENGINE, WORKSPACE_AGENT_NAME).

Nada se teclea ni se lee de una pantalla: se escribe donde lee la página (el registro de eventos, las ejecuciones,
sus preferencias), y el servidor de la página lo enseña. Stdlib.
"""
import datetime as _dt
import json
import os
import secrets
import sys
import time
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

TIPOS = ("texto", "opcion", "confirmar")
MAX_PREGUNTA, MAX_OPCION, MAX_OPCIONES = 500, 200, 12
MAX_TEXTO_SKILL = 600
MAX_SKILL_MD = 24 * 1024
NAV = "navegador"


class Error(ValueError):
    """Lo que no se pudo, en simple, para el agente (el MCP lo devuelve con su código)."""

    def __init__(self, texto, codigo="ENTRADA_INVALIDA"):
        super().__init__(texto)
        self.codigo = codigo


def _una(texto, tope):
    return " ".join(str(texto or "").split())[:tope]


# ── preguntar ─────────────────────────────────────────────────────────────────
def forma_de_pregunta(pregunta, opciones=None, tipo=None):
    """(pregunta, tipo, opciones) ya validados. Sin `tipo`: con opciones, «opcion»; si no, «texto»."""
    pregunta = _una(pregunta, MAX_PREGUNTA)
    if not pregunta:
        raise Error("la pregunta no puede ir vacía")
    opciones = list(dict.fromkeys(o for o in (_una(x, MAX_OPCION) for x in (opciones or [])) if o))
    if len(opciones) > MAX_OPCIONES:
        raise Error("hasta %d opciones" % MAX_OPCIONES)
    tipo = tipo or ("opcion" if opciones else "texto")
    if tipo not in TIPOS:
        raise Error("tipo: %s" % ", ".join(TIPOS))
    if tipo == "opcion" and len(opciones) < 2:
        raise Error("una pregunta con opciones necesita al menos 2")
    if tipo == "confirmar":
        opciones = []                       # la página pone Sí / No
    return pregunta, tipo, opciones


def preguntar(brain, pestana, motor, pregunta, opciones=None, tipo=None, paso="", via="chat"):
    """La pregunta al registro de eventos de la pestaña: la página y el hub la enseñan en la caja de escribir (Q-2).
    Si no se puede escribir ahí (el sandbox de la terminal de un motor solo deja escribir en el cerebro: Codex), va al
    buzón del cerebro y el servidor de la página la enseña igual. → su id (q-…)."""
    from arquitectura import registro
    pregunta, tipo, opciones = forma_de_pregunta(pregunta, opciones, tipo)
    if not (brain and pestana):
        raise Error("no se sabe de qué pestaña es esta corrida", "SIN_PESTANA")
    pid = "q-" + uuid.uuid4().hex[:12]
    datos = {"id": pid, "pregunta": pregunta, "tipo": tipo, "opciones": opciones, "paso": paso or "", "via": via}
    if registro.anotar(brain, pestana, registro.PREGUNTA, motor or "", "", datos):
        return pid
    if not _al_buzon(brain, PREGUNTAS, json.dumps(dict(datos, pestana=pestana, motor=motor or "", ts=time.time(),
                                                         maquina=maquina()), ensure_ascii=False) + "\n"):
        raise Error("no se pudo anotar la pregunta", "NO_DISPONIBLE")
    return pid


# ── mostrar un archivo (modo chat) ────────────────────────────────────────────
def mostrar_archivo(brain, pestana, motor, ruta, titulo=""):
    """Un archivo (o carpeta) DENTRO del cerebro, al registro de la pestaña: la página y el hub lo pintan como su tarjeta
    en el turno donde se enseñó («Abrir» / «Mostrar en la carpeta», localhost_front.abrir, que vuelve a comprobar que
    está dentro). Fuera del cerebro o inexistente, no. Si el registro no se puede escribir (el sandbox de la terminal
    de un motor), al buzón del cerebro. → {ruta (relativa al cerebro), titulo}."""
    from arquitectura import modo_chat, registro
    if not (brain and pestana):
        raise Error("no se sabe de qué pestaña es esta corrida", "SIN_PESTANA")
    pedida = str(ruta or "").strip()
    if not pedida:
        raise Error("ruta: la del archivo que quieres enseñar")
    rel = modo_chat.archivo_del_cerebro(brain, modo_chat._local(pedida))
    if not rel:
        raise Error("solo se enseñan archivos que existen dentro de tu carpeta (tu cerebro): %s no está ahí" % pedida,
                    "NO_ENCONTRADO")
    datos = {"ruta": rel, "titulo": modo_chat.titulo_de(titulo, rel)}
    if registro.anotar(brain, pestana, registro.ARCHIVO, motor or "", "", datos):
        return datos
    if not _al_buzon(brain, ARCHIVOS, json.dumps(dict(datos, pestana=pestana, motor=motor or "", ts=time.time(),
                                                     maquina=maquina()), ensure_ascii=False) + "\n"):
        raise Error("no se pudo anotar el archivo", "NO_DISPONIBLE")
    return datos


def indicacion_archivo(env=None):
    """Lo que hace el agente después de mostrar_archivo."""
    if en_la_pagina(env):
        return "Ya le salió al socio como tarjeta con «Abrir» y «Mostrar en la carpeta»: no repitas la ruta en el chat."
    return "La página y el hub lo enseñan como tarjeta; en la terminal, dile dónde está."


# ── el buzón del cerebro: lo que el agente deja donde su sandbox lo deja escribir ──
#: <cerebro>/STATE/pagina/: preguntas.jsonl y archivos.jsonl (uno por renglón, solo se anexan) y perfil.json (el último
#: cambio pedido). Lo lee y lo aplica el servidor de la página (pagina_v2), el único dueño. Cada cosa lleva la huella de
#: la máquina: el cerebro se sincroniza, y lo de otra computadora no se enseña aquí.
PREGUNTAS, PERFIL, ARCHIVOS = "preguntas.jsonl", "perfil.json", "archivos.jsonl"
MAX_BUZON = 64 * 1024


def buzon(brain):
    return os.path.join(str(brain), "STATE", "pagina")


def maquina():
    import hashlib
    import socket
    return hashlib.sha1(socket.gethostname().encode("utf-8", "replace")).hexdigest()[:12]


def _al_buzon(brain, nombre, texto, anexar=True):
    try:
        os.makedirs(buzon(brain), exist_ok=True)
        ruta = os.path.join(buzon(brain), nombre)
        if anexar:
            with open(ruta, "a", encoding="utf-8") as fh:
                fh.write(texto)
        else:
            import atomico
            tmp = "%s.%d.tmp" % (ruta, os.getpid())
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(texto)
            # Windows: si el servidor de la página lo está leyendo en ese instante, reemplazarlo da «acceso
            # denegado» un momento; con reintentos cortos el pedido no se pierde (atomico borra el temporal si no).
            atomico.reemplazar(tmp, ruta)
        return True
    except OSError:
        return False


def _del_buzon(brain, nombre, tope):
    """Los últimos renglones (dicts) de un .jsonl del buzón, de esta máquina (los más nuevos al final)."""
    try:
        with open(os.path.join(buzon(brain), nombre), "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - MAX_BUZON))
            crudo = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    out, yo = [], maquina()
    for ln in crudo.splitlines()[-tope:]:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("maquina") == yo:
            out.append(d)
    return out


def preguntas_del_buzon(brain, tope=20):
    """Las últimas preguntas que dejó el agente en el buzón de su cerebro, de esta máquina (las más nuevas al final)."""
    return [d for d in _del_buzon(brain, PREGUNTAS, tope) if d.get("id") and d.get("pregunta")]


def archivos_del_buzon(brain, tope=20):
    """Los últimos archivos que enseñó el agente desde el buzón de su cerebro, de esta máquina."""
    return [d for d in _del_buzon(brain, ARCHIVOS, tope) if d.get("ruta")]


def en_la_pagina(env=None):
    """¿Esta corrida es la conversación de la página (la abrió su servidor) o la del monito de escritorio? Ahí la
    pregunta ya sale en la caja (o en la burbuja)."""
    env = os.environ if env is None else env
    return env.get("WORKSPACE_VIA") in ("pagina", "escritorio") or (env.get("WORKSPACE_WS") or "").strip() == NAV


def indicacion(env=None, con_opciones=False):
    """Qué hace el agente después de preguntar (sin formulario del motor)."""
    if en_la_pagina(env):
        return ("Ya le salió al socio en su caja de escribir%s: no la repitas en el chat. Termina tu turno aquí; su "
                "respuesta te llega como su próximo mensaje." % (" con sus opciones" if con_opciones else ""))
    return ("Pregúntale al socio en el chat con estas mismas palabras%s y termina tu turno: su respuesta te llega en el "
            "próximo mensaje (la página también la enseña)." % (" y estas opciones" if con_opciones else ""))


# ── usar una skill a la vista ─────────────────────────────────────────────────
def skills_de(brain):
    """[(rel, carpeta, nombre, descripción)] de skills/ del cerebro (lo mismo que skills_lista)."""
    from arquitectura import nucleo_mcp
    return [(rel, d, fm.get("name") or rel.split("/")[-1], " ".join(str(fm.get("description") or "").split()))
            for rel, d, fm in nucleo_mcp._skills(brain)]


def buscar_skill(brain, pedida):
    """(rel, carpeta, nombre) de la skill `pedida` del cerebro (su ruta en skills/, su carpeta, el nombre de su
    frontmatter o, como la nombra el menú de su motor, el de skills_cerebro en kebab-case), o None."""
    pedida = str(pedida or "").strip().strip("/")
    if pedida.startswith("skills/") and pedida.endswith("/SKILL.md"):
        pedida = pedida[len("skills/"):-len("/SKILL.md")]
    if not pedida or ".." in pedida.split("/"):
        return None
    try:
        from arquitectura import skills_cerebro
        kebab = skills_cerebro.kebab
    except Exception:
        kebab = None
    for rel, d, nombre, _desc in skills_de(brain):
        if pedida in (rel, rel.split("/")[-1], nombre) or (kebab and pedida == kebab(nombre)):
            return rel, d, nombre
    return None


#: skills-cierre: la abierta de la misma skill en la misma conversación se reusa (de hace menos de 6 h, como la que
#: corre): la que activó «Usar» de la página o la que vio el servidor por la herramienta propia de su motor.
REUSA_S = 6 * 3600


def _abierta_de(brain, nombre, pestana):
    import pasos
    try:
        nombres = sorted((n for n in os.listdir(pasos.carpeta(brain)) if n.endswith(".json")), reverse=True)[:20]
    except OSError:
        return None
    for n in nombres:
        e = pasos.leer(n[:-5], brain)
        if not e or not pasos.abierta(e) or e.get("skill") != nombre or (e.get("pestana") or NAV) != pestana:
            continue
        try:
            t = _dt.datetime.fromisoformat(str(e.get("actualizado") or e.get("creado"))).timestamp()
        except (TypeError, ValueError):
            t = 0
        if not t or time.time() - t < REUSA_S:
            return e
    return None


def _nueva_ejecucion(brain, agente, pestana, motor, nombre, rel, texto="", por="agente", estado="arrancando"):
    import pasos
    ejecucion = "s-%s-%s" % (_dt.datetime.now().strftime("%Y%m%d%H%M%S"), secrets.token_hex(2))
    pasos.guardar(ejecucion, {"id": ejecucion, "skill": nombre, "ruta": "skills/%s/SKILL.md" % rel,
                              "agente": agente or "", "pestana": pestana or NAV, "motor": motor or "",
                              "texto": _una(texto, MAX_TEXTO_SKILL), "estado": estado, "pasos": [], "pide": None,
                              "por": por, "creado": _dt.datetime.now().isoformat(timespec="seconds")}, brain)
    return ejecucion


def usar_skill(brain, agente, pestana, motor, skill, texto=""):
    """Activa la skill `skill` del cerebro a la vista: su ejecución (la misma forma que «Usar» de la página,
    pagina_v2.skill) para que la página enseñe «Empezó …», su proceso y su barra. → {ejecucion, skill, ruta, skill_md,
    ya}. No le manda nada al motor: quien la usa es el agente, en este mismo turno.
    skills-cierre: si esa skill ya está abierta en esta conversación (la activó «Usar» de la página, o el servidor la
    vio en la herramienta propia de su motor), se reusa esa (`ya`: True) y no se crea otra: Cursor la duplicaba."""
    import pasos
    pedida = str(skill or "").strip().strip("/")
    if not pedida or ".." in pedida.split("/"):
        raise Error("skill: su nombre (míralas con skills_lista)")
    hallada = buscar_skill(brain, pedida)
    if hallada is None:
        raise Error("no hay una skill «%s» en este cerebro (míralas con skills_lista)" % pedida, "NO_ENCONTRADO")
    rel, d, nombre = hallada
    ruta_rel = "skills/%s/SKILL.md" % rel
    previa = _abierta_de(brain, nombre, pestana or NAV)
    if previa is not None:
        ejecucion = previa["id"]
        if previa.get("por") == "motor" and not previa.get("tomada"):
            pasos.actualizar(ejecucion, lambda x: x.update(tomada=True) or True, brain)
    else:
        ejecucion = _nueva_ejecucion(brain, agente, pestana, motor, nombre, rel, texto)
    try:
        with open(os.path.join(d, "SKILL.md"), encoding="utf-8", errors="replace") as fh:
            md = fh.read(MAX_SKILL_MD + 1)
    except OSError:
        md = ""
    if len(md) > MAX_SKILL_MD:
        md = md[:MAX_SKILL_MD] + "\n[… recortado: léelo entero en %s]" % ruta_rel
    return {"ejecucion": ejecucion, "skill": nombre, "ruta": ruta_rel, "skill_md": md, "ya": previa is not None}


def activar_por_motor(brain, agente, pestana, motor, pedida):
    """skills-cierre (Fix 3): su motor usó su PROPIA herramienta de skills (sin usar_skill): la ejecución que la página
    enseña («Empezó …»), `por: motor`, corriendo. Termina con su turno (pagina_v2). → su id, o None si no es una skill
    del cerebro o ya hay una abierta de esa skill."""
    hallada = buscar_skill(brain, pedida)
    if hallada is None:
        return None
    rel, _d, nombre = hallada
    if _abierta_de(brain, nombre, pestana or NAV) is not None:
        return None
    return _nueva_ejecucion(brain, agente, pestana, motor, nombre, rel, por="motor", estado="corriendo")


def como_seguir(ejecucion, mcp=True):
    """Lo que el agente hace después de usar_skill. skills-cierre (Fix 4): las mismas reglas que la instrucción de
    «Usar» (localhost_web._instruccion) y que la guía de chat: ya está activada, una llamada a la vez, dentro de la
    skill se pregunta solo con su «pide» y ahí termina el turno, y cada turno dentro de ella termina con pide o fin."""
    if mcp:
        return ("Ya está activada: no llames usar_skill otra vez. Reporta tu avance con reportar_avance "
                "(ejecucion \"%s\"), una llamada a la vez: al empezar, accion plan con pasos; en cada paso, ahora y hecho "
                "con n; para preguntarle algo al socio, solo accion pide con texto y opciones y termina tu turno ahí; al "
                "final, fin con el resumen en una línea: %s" % (ejecucion, _no_repreguntes()))
    cmd = "%s pasos %s" % ("workspace.cmd" if sys.platform == "win32" else "workspace", ejecucion)
    return ("Ya está activada: no la actives otra vez. Reporta tu avance, un comando a la vez (cada vez el comando "
            "completo, solo, en una línea): %s plan \"paso 1\" \"paso 2\"…; %s ahora N y %s hecho N; para preguntarle "
            "algo al socio, solo %s pide \"qué necesitas\" --opcion \"A\" --opcion \"B\" y termina tu turno ahí; al "
            "final, %s fin \"resumen en una línea\": %s" % (cmd, cmd, cmd, cmd, cmd, _no_repreguntes()))


def _no_repreguntes():
    try:
        import localhost_web
        return localhost_web.NO_REPREGUNTES
    except Exception:
        return ("cada turno dentro de la skill termina con pide o con fin; si mientras esperas te escribe otra cosa, "
                "contéstale solo eso, sin volver a preguntar: queda en pausa hasta que pulse «Seguir».")


# ── personalizarse ────────────────────────────────────────────────────────────
def agente_de(brain, env=None):
    """El id del agente dueño de `brain` (el que puso Workspace en el entorno, o el del registro)."""
    env = os.environ if env is None else env
    puesto = str(env.get("WORKSPACE_AGENT_NAME") or "").strip()
    try:
        import localhost_front as LF
        cerebros = dict(LF._cerebros())
    except Exception:
        cerebros = {}
    if puesto and (not cerebros or puesto in cerebros):
        return puesto
    real = os.path.realpath(str(brain or ""))
    for aid, b in cerebros.items():
        if b and os.path.realpath(str(b)) == real:
            return aid
    return puesto


def opciones_de_apariencia():
    import localhost_front as LF
    return {"colores": list(LF.COLORES), "formas": list(LF.FORMAS)}


#: Los colores también por su nombre (el agente dice «verde»).
def _color(c):
    import localhost_front as LF
    return LF._color_conocido(c) if c else None


def personalizar(agente, color=None, forma=None, nombre=None):
    """Su color, su monito o su nombre en esta computadora (localhost_front: lo mismo que la página). La página y el
    hub lo enseñan en vivo (pagina_v2: foto.perfil). Devuelve las preferencias guardadas o los campos solicitados
    con pedido=True si quedaron pendientes en el buzón."""
    import localhost_front as LF
    if color is None and forma is None and nombre is None:
        raise Error("di qué cambias: color, forma o nombre")
    if not agente:
        raise Error("no se sabe qué agente eres", "SIN_PESTANA")
    c = _color(color) if color is not None else None
    if color is not None and not c:
        raise Error("color: uno de %s (o su nombre: verde, azul, rosa, morado, amarillo, blanco)"
                    % ", ".join(LF.COLORES))
    if forma is not None and forma not in LF.FORMAS:
        raise Error("forma: una de %s" % ", ".join(LF.FORMAS))
    if nombre is not None and nombre.strip() and not LF._renglon_ok(nombre.strip(), 40):
        raise Error("ese nombre no sirve: una línea corta, sin símbolos raros", "ENTRADA_INVALIDA")
    hecho = True
    if c or forma:
        hecho = bool(LF.apariencia(agente, forma=forma, color=c).get("ok"))
    if hecho and nombre is not None:
        hecho = bool(LF.nombre(agente, nombre).get("ok"))
    if not hecho:
        # el sandbox de su terminal no deja escribir las preferencias de esta computadora: lo pide en el buzón de su
        # cerebro y el servidor de la página lo aplica (aplicar_perfil_pedido)
        pedido = {k: v for k, v in (("color", c), ("forma", forma), ("nombre", nombre)) if v is not None}
        if not _al_buzon(brain_de(agente), PERFIL, json.dumps(dict(pedido, agente=agente, ts=time.time(),
                                                                    maquina=maquina())), anexar=False):
            raise Error("no se pudo cambiar su apariencia", "NO_DISPONIBLE")
        return dict(pedido, pedido=True)
    p = LF._prefs_de(LF.leer_prefs(), agente)
    av = p.get("avatar") or {}
    return {"color": av.get("color"), "forma": av.get("forma"), "nombre": p.get("nombre") or ""}


def brain_de(agente):
    try:
        import localhost_front as LF
        return dict(LF._cerebros()).get(agente) or os.environ.get("WORKSPACE_BRAIN") or os.getcwd()
    except Exception:
        return os.environ.get("WORKSPACE_BRAIN") or os.getcwd()


#: Un pedido tomado por un servidor de la página que se cerró antes de terminar vuelve al buzón pasado este tiempo.
_TOMA_VIEJA_S = 60


def _leer_pedido(ruta):
    # Se lee entero y se cierra ANTES de interpretarlo: en Windows, mientras está abierto, el agente no puede
    # reemplazarlo con su pedido nuevo (_al_buzon).
    try:
        with open(ruta, encoding="utf-8") as fh:
            crudo = fh.read()
        d = json.loads(crudo)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _pedido_de_aqui(d, agente):
    return isinstance(d, dict) and d.get("maquina") == maquina() and d.get("agente") in (agente, None, "")


def _devolver_pedido(toma, ruta):
    """El pedido tomado vuelve al buzón, salvo que ya haya uno más nuevo (el más nuevo manda, como en _al_buzon)."""
    try:
        os.link(toma, ruta)                 # no pisa: falla si ya llegó otro
    except FileExistsError:
        pass
    except OSError:                         # sin enlaces (algunas carpetas sincronizadas): solo si no llegó otro
        if not os.path.exists(ruta):
            try:
                os.replace(toma, ruta)
            except OSError:
                pass
            return
    try:
        os.remove(toma)
    except OSError:
        pass


def _recuperar_tomas(ruta):
    import glob
    for toma in glob.glob(glob.escape(ruta) + ".*.aplicando"):
        try:
            if time.time() - os.path.getmtime(toma) > _TOMA_VIEJA_S:
                _devolver_pedido(toma, ruta)
        except OSError:
            pass


def _aplicar_pedido(d, agente):
    """→ (aplicado, quitar): quitar=False si alguna parte no se pudo guardar (se reintenta); un pedido sin nada
    aplicable se quita sin aplicar."""
    import localhost_front as LF
    c = _color(d.get("color")) if d.get("color") else None
    forma = d.get("forma") if d.get("forma") in LF.FORMAS else None
    partes = []
    if c or forma:
        partes.append(bool(LF.apariencia(agente, forma=forma, color=c).get("ok")))
    if isinstance(d.get("nombre"), str):
        partes.append(bool(LF.nombre(agente, d["nombre"]).get("ok")))
    if not partes:
        return False, True
    return all(partes), all(partes)


def aplicar_perfil_pedido(agente, brain):
    """Lo hace el servidor de la página: el cambio que el agente dejó en su buzón (de esta máquina), aplicado con las
    mismas funciones que la página. El pedido se TOMA de un solo golpe (se renombra: uno que llegue mientras tanto
    queda para la vuelta siguiente), se aplica y solo entonces se quita; si no se pudo guardar, vuelve al buzón para
    reintentarlo (revisor 8: antes se borraba antes de aplicarlo). Uno de otra computadora u otro agente no se toca.
    → True si lo aplicó."""
    ruta = os.path.join(buzon(brain), PERFIL)
    _recuperar_tomas(ruta)
    if not _pedido_de_aqui(_leer_pedido(ruta), agente):
        return False
    toma = "%s.%s.aplicando" % (ruta, uuid.uuid4().hex)
    try:
        os.replace(ruta, toma)
        os.utime(toma)                      # su edad cuenta desde que se tomó
    except OSError:
        return False                        # otra vuelta del servidor ya lo tomó
    d = _leer_pedido(toma)
    aplicado, quitar = _aplicar_pedido(d, agente) if _pedido_de_aqui(d, agente) else (False, False)
    if quitar:
        try:
            os.remove(toma)
        except OSError:
            pass
    else:
        _devolver_pedido(toma, ruta)
    return aplicado


# ── el comando de respaldo: `workspace pasos preguntar|usar|personalizar` ─────
def contexto(env=None):
    """{brain, pestana (la del registro), ws, motor, agente} de esta corrida, del entorno que puso Workspace."""
    env = os.environ if env is None else env
    brain = env.get("WORKSPACE_BRAIN") or os.getcwd()
    return {"brain": brain, "pestana": (env.get("WORKSPACE_WID") or env.get("WORKSPACE_WS") or "").strip(),
            "ws": (env.get("WORKSPACE_WS") or "").strip(), "motor": env.get("WORKSPACE_ENGINE") or "",
            "agente": agente_de(brain, env)}


AYUDA = """\
workspace pasos preguntar "¿Para quién es?" --opcion "Clientes" --opcion "El equipo"   (o --tipo confirmar)
workspace pasos usar <skill> ["para qué"]
workspace pasos personalizar [--color verde] [--forma gatito] [--nombre "Atlas"]
workspace pasos archivo <ruta> [--titulo "La demo"]"""


def _banderas(args, conocidas):
    vals, resto, i = {}, [], 0
    while i < len(args):
        a = args[i]
        k = a[2:].split("=", 1)[0] if a.startswith("--") else ""
        if k in conocidas:
            v = a.split("=", 1)[1] if "=" in a else (args[i + 1] if i + 1 < len(args) else None)
            if v is None:
                raise Error("--%s necesita su valor" % k)
            if "=" not in a:
                i += 1
            vals.setdefault(k, []).append(v)
        else:
            resto.append(a)
        i += 1
    return vals, resto


def main(argv, env=None):
    """`workspace pasos preguntar|usar|personalizar …` → código de salida; lo que dice va a stdout (al agente)."""
    ctx = contexto(env)
    sub, args = (argv[0] if argv else ""), list(argv[1:])
    try:
        if sub == "preguntar":
            vals, resto = _banderas(args, ("opcion", "tipo", "paso"))
            preguntar(ctx["brain"], ctx["pestana"], ctx["motor"], " ".join(resto), vals.get("opcion"),
                      (vals.get("tipo") or [None])[-1], (vals.get("paso") or [""])[-1])
            print(indicacion(env, bool(vals.get("opcion"))))
            return 0
        if sub == "usar":
            if not args:
                raise Error("usar necesita el nombre de la skill")
            r = usar_skill(ctx["brain"], ctx["agente"], ctx["ws"] or NAV, ctx["motor"], args[0], " ".join(args[1:]))
            print("%s «%s» (ejecución %s); el socio ya lo ve. %s\n\n%s\n\n%s"
                  % ("Ya estaba activada" if r.get("ya") else "Empezó", r["skill"], r["ejecucion"],
                     como_seguir(r["ejecucion"], mcp=False), r["ruta"], r["skill_md"]))
            return 0
        if sub == "personalizar":
            vals, resto = _banderas(args, ("color", "forma", "nombre"))
            if resto:
                raise Error("personalizar: --color, --forma o --nombre")
            r = personalizar(ctx["agente"], (vals.get("color") or [None])[-1], (vals.get("forma") or [None])[-1],
                             (vals.get("nombre") or [None])[-1])
            perfil = json.dumps(r, ensure_ascii=False)
            if r.get("pedido"):
                print("Pedido guardado (%s). El cambio se aplicará cuando la página lo procese." % perfil)
            else:
                print("Cambio aplicado (%s)." % perfil)
            return 0
        if sub == "archivo":
            vals, resto = _banderas(args, ("titulo",))
            if len(resto) != 1:
                raise Error("archivo: una ruta (entre comillas si lleva espacios) y, si quieres, --titulo \"…\"")
            mostrar_archivo(ctx["brain"], ctx["pestana"], ctx["motor"], resto[0], (vals.get("titulo") or [""])[-1])
            print(indicacion_archivo(env))
            return 0
    except Error as e:
        print("pasos: %s" % e, file=sys.stderr)
        return 2
    print(AYUDA)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
