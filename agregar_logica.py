#!/usr/bin/env python3
"""WORKSPACE · agregar_logica — «Agregar agente» sin pantalla: lo que la tarjeta del hub, la página y la pantalla de
antes necesitan para crear un agente o conectar uno que ya existe.

Crear
  · comando_de(nombre)      «Brisa Azul» → «brisa-azul» (su comando y el nombre de su carpeta);
  · revisar_nombre(nombre)  en vivo: libre, repetido (con el siguiente libre: «nilo-2»), un programa que ya existe,
                            una carpeta que ya existe (y si parece un agente: «Conectarlo»);
  · motores(srv) / elegir_motor(lista)   O5-a: el motor que ya tiene sesión queda puesto;
  · crear(campos, srv)      por la página prendida si contesta y es de esta versión; si no, la MISMA función que ella
                            llama (localhost_front.crear_agente → agent_create_job.start) aquí mismo. Un motor sin
                            sesión NO bloquea: el agente nace y «despierta» cuando entras a tu cuenta.
  · pasos_humanos(job)      los 8 pasos del job oficial en 4 frases («Hago su carpeta»…).
Ya tengo un agente
  · limpiar_ruta(texto)     lo que pegas o arrastras (comillas, «\\ », ~, file://, rutas de Windows y OneDrive);
  · radiografia(ruta)       qué hay en esa carpeta, en simple: un agente, uno a medio sincronizar, ya conectado, uno
                            con el mismo nombre que otro (con un nombre libre) o algo que no es un agente;
  · buscar(protegidas)      los cerebros de esta computadora (en Mac, Escritorio/Documentos/Descargas solo si lo
                            pides: cada uno abre un permiso de macOS);
  · conectar(items, srv)    el job de cargar (agent_load_job), por la página o aquí.

Las respuestas de error traen su `clave` (la misma de localhost.err.*): la tarjeta elige con ella el botón que lo
arregla. Stdlib, Python 3.9+. Mac y Windows. Falla-suave."""
import os
import re
import sys
import threading
import unicodedata
from urllib.parse import unquote, urlparse

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

#: El id de la tarjeta dormida al final de la fila de Inicio (ningún agente puede llamarse así: empieza con «+»).
NUEVO_ID = "+nuevo"
GRIS = "#8a8a94"
MAX_COMANDO = 32


#: Los idiomas en que ya está la tarjeta (los del hub de terminal: hub_directo.IDIOMAS_HUB). AG3-a: en la versión 1 el
#: hub va en español para todos, con su línea de aviso; el catálogo inglés ya existe y se prende en la versión 2.
IDIOMAS = ("es",)


def idioma():
    """El idioma de la tarjeta: el de Workspace si la tarjeta ya está en él; si no, español (como el hub)."""
    try:
        import i18n
        code = i18n.lang()
    except Exception:
        return "es"
    return code if code in IDIOMAS else "es"


def _t(clave, **kw):
    """El texto de `clave` en el idioma de la tarjeta (idioma()), con el español de red."""
    try:
        import i18n
        code = idioma()
        s = i18n._load_catalog(code).get(clave)
        if s is None and code != "es":
            s = i18n._load_catalog("es").get(clave)
        if s is None:
            return i18n.t(clave, **kw)
        if kw:
            try:
                return s.format(**kw)
            except Exception:
                return s
        return s
    except Exception:
        return clave


# ── el nombre y su comando ─────────────────────────────────────────────────────
def comando_de(nombre):
    """El comando (y nombre corto) que sale de lo que escribiste: sin acentos, en minúsculas, los espacios como «-»;
    '' si no queda nada válido."""
    t = unicodedata.normalize("NFKD", str(nombre or "")).encode("ascii", "ignore").decode("ascii").lower()
    t = re.sub(r"[\s.]+", "-", t.strip())
    t = re.sub(r"[^a-z0-9_-]", "", t)
    t = re.sub(r"-{2,}", "-", t).strip("-_")[:MAX_COMANDO].strip("-_")
    try:
        import agentsreg
        return t if agentsreg.is_valid_name(t) else ""
    except Exception:
        return t


def _ocupado(comando):
    """¿Ese nombre ya es de un agente (de esta computadora o del registro)?"""
    try:
        import agentsreg
        import agent_admin
        return bool(agentsreg.find(comando) or agent_admin.dispatch.find_agent(comando))
    except Exception:
        return False


_CHOQUES = {}


def choque_comando(v):
    """'' o por qué `v` no puede ser un comando (agent_admin.command_conflict), recordado 5 s: se pregunta en cada
    tecla y mirar el PATH cuesta."""
    import time
    import agent_admin
    try:
        import i18n
        idioma = i18n.lang()
    except Exception:
        idioma = ""
    clave = (v, os.environ.get("PATH", ""), os.path.expanduser("~"), idioma)
    ahora = time.monotonic()
    memo = _CHOQUES.get(clave)
    if memo is None or ahora - memo[0] > 5:
        if len(_CHOQUES) > 64:
            _CHOQUES.clear()
        memo = _CHOQUES[clave] = (ahora, agent_admin.command_conflict(v))
    return memo[1]


def libre(comando, tope=50):
    """El siguiente nombre libre: «nilo» → «nilo-2» (sin agente, sin carpeta y sin programa que lo tape)."""
    import agent_admin
    base = comando[:MAX_COMANDO - 3]
    for n in range(2, tope):
        c = "%s-%d" % (base, n)
        try:
            carpeta = os.path.exists(agent_admin.default_brain_dest(c))
        except Exception:
            carpeta = False
        if not _ocupado(c) and not carpeta and not choque_comando(c):
            return c
    return ""


def ruta_corta(p):
    """~/… en vez de /Users/…/… (las rutas largas ahogan las cajas)."""
    try:
        home = os.path.expanduser("~")
        if p and (p == home or p.startswith(home + os.sep)):
            return "~" + p[len(home):]
    except Exception:
        pass
    return p or ""


def revisar_nombre(nombre, comando=None):
    """Lo que dice el nombre EN VIVO. → {"estado": ""|"ok"|"bad", "clave", "comando", "carpeta", "libre", "agente"}.
    `clave` ∈ vacio · invalido · repetido · programa · carpeta · carpeta_agente · ok. `comando` manda si lo das (la
    pantalla de antes escribe el comando directo)."""
    import agent_admin
    v = comando_de(nombre) if comando is None else str(comando or "").strip().lower()
    out = {"estado": "", "clave": "vacio", "comando": v, "carpeta": "", "libre": "", "agente": None}
    if not v:
        if str(nombre or "").strip():
            out.update(estado="bad", clave="invalido")
        return out
    try:
        import agentsreg
        if not agentsreg.is_valid_name(v):
            out.update(estado="bad", clave="invalido")
            return out
    except Exception:
        pass
    if _ocupado(v):
        out.update(estado="bad", clave="repetido", libre=libre(v))
        return out
    choque = choque_comando(v)
    if choque:
        out.update(estado="bad", clave="programa", texto=choque, libre=libre(v))
        return out
    try:
        destino = agent_admin.default_brain_dest(v)
    except Exception:
        destino = ""
    out["carpeta"] = destino
    if destino and os.path.exists(destino):
        info = radiografia(destino)
        out.update(estado="bad", clave="carpeta_agente" if info.get("veredicto") in ("agente", "incompleto")
                   else "carpeta", libre=libre(v), agente=info)
        return out
    out.update(estado="ok", clave="ok")
    return out


def texto_nombre(r):
    """La frase de revisar_nombre para la persona (en simple, una línea)."""
    c = r.get("clave")
    if c == "vacio":
        return _t("agregar.nombre.vacio")
    if c == "invalido":
        return _t("agregar.nombre.invalido")
    if c == "repetido":
        return _t("agregar.nombre.repetido", n=r["comando"], l=r.get("libre") or "")
    if c == "programa":
        return _t("agregar.nombre.programa", n=r["comando"], l=r.get("libre") or "")
    if c == "carpeta_agente":
        return _t("agregar.nombre.carpeta_agente", r=ruta_corta(r.get("carpeta")))
    if c == "carpeta":
        return _t("agregar.nombre.carpeta", r=ruta_corta(r.get("carpeta")))
    return _t("agregar.nombre.ok", n=r.get("comando") or "")


# ── quién eres (el dueño) ──────────────────────────────────────────────────────
def persona():
    """El nombre corto de quien usa esta computadora: el que ya sabe Workspace (identidad), o el de la cuenta de la
    computadora. '' si nada."""
    try:
        import identidad
        p = identidad.persona()
        if p and p.get("nombre"):
            return p["nombre"]
    except Exception:
        pass
    return nombre_de_la_cuenta(corto=True)


def nombre_de_la_cuenta(corto=False):
    """El nombre de la cuenta de la computadora («Ana», o «ana» con `corto`), para escribirlo ya en el paso «Tú»."""
    nombre = ""
    try:
        import getpass
        nombre = getpass.getuser() or ""
    except Exception:
        nombre = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    if not corto and sys.platform == "darwin":
        try:
            import pwd
            completo = (pwd.getpwnam(nombre).pw_gecos or "").split(",")[0].strip()
            if completo:
                nombre = completo.split()[0]
        except Exception:
            pass
    nombre = nombre.strip()
    if corto:
        import agent_create_params as ACP
        return ACP.slug_dueno(comando_de(nombre) or nombre)
    return nombre[:1].upper() + nombre[1:] if nombre else ""


def fijar_persona(nombre):
    """«Tú» (primer arranque): quien usa esta computadora. → su nombre corto, o '' si no se pudo."""
    try:
        import identidad
        p = identidad.fijar_persona(comando_de(nombre) or nombre, origen="onboarding")
        return (p or {}).get("nombre") or ""
    except Exception:
        return ""


# ── los motores (O5-a) ─────────────────────────────────────────────────────────
def motores(srv=None, verificar=False):
    """Los motores de esta computadora como los da /api/sistema/motores (id, nombre, instalado, listo, sesion, estado…):
    por la página si contesta; si no, la misma función aquí (localhost_sistema.motores, sin pantalla). None si nada."""
    if srv is not None and not getattr(srv, "sin_pagina", False):
        try:
            return srv.get("/api/sistema/motores", **({"verificar": "1"} if verificar else {})).get("motores")
        except Exception:
            pass
    try:
        import localhost_sistema
        return localhost_sistema.motores(verificar=verificar).get("motores")
    except Exception:
        return None


def usable(m):
    return bool(m and m.get("listo")) and m.get("sesion") is not False and m.get("estado") != "sin_sesion"


def elegir_motor(lista, preferido=None):
    """O5-a «Se elige solo»: el preferido si ya está listo; si no, el primero listo; si ninguno, el primero instalado;
    si ninguno, None (la tarjeta ofrece instalar)."""
    lista = [m for m in lista or () if m.get("id") != "stub"]
    if preferido and any(m.get("id") == preferido and usable(m) for m in lista):
        return preferido
    for m in lista:
        if usable(m):
            return m["id"]
    for m in lista:
        if m.get("instalado"):
            return m["id"]
    return None


def nombre_motor(mid):
    try:
        import motores_logica
        return motores_logica.engine_name(mid)
    except Exception:
        return str(mid or "")


def motor_de(nombre):
    """El motor con que piensa el agente `nombre` (su agent.json), o ''."""
    try:
        import agentsreg
        brain = cerebro_de(nombre)
        return str((agentsreg.load_definition(brain) or {}).get("engine") or "") if brain else ""
    except Exception:
        return ""


def falta_su_sesion(motor):
    """¿Al motor `motor` le falta tu sesión (o no está instalado) para que el agente despierte? True / False / None si
    no se pudo saber (entonces no se afirma nada). Pregunta con el comando oficial de cada motor (con su caché)."""
    try:
        import motores_logica
        fila = next((d for d in motores_logica._rows() if d.get("id") == motor), None)
        if fila is not None and not fila.get("binaries_ok"):
            return True
        p = motores_logica._probe(motor)
    except Exception:
        return None
    if p is True:
        return False
    return None if p is None else True


#: Lo que le falta a un motor que no está listo, en simple (el estado de localhost_sistema._motor → frase y chip).
#: «instalado» = no se pudo confirmar su sesión (no que esté mal).
_NO_LISTO = {"instalado": "sin_confirmar", "falta_modelo": "modelo", "revisar_version": "version",
             "bloqueado": "bloqueado", "incompleta": "incompleta"}


def que_le_falta(m):
    """→ la clave corta de lo que le falta a un motor que no está listo (sin_confirmar · modelo · version · bloqueado ·
    incompleta · otro). Para la tarjeta: texto amable, nunca el estado interno."""
    return _NO_LISTO.get(str((m or {}).get("estado") or ""), "otro")


# ── crear (por la página o aquí) ───────────────────────────────────────────────
def _por_la_pagina(srv):
    """¿Se crea por la página prendida? Solo si hay página (el hub sin ella trae `sin_pagina`, AG2) y es de este mismo
    código (una de antes no conoce los campos nuevos). Si no, todo se hace aquí con las mismas funciones."""
    return srv is not None and not getattr(srv, "sin_pagina", False) and not getattr(srv, "vieja", False) \
        and not getattr(srv, "hub_viejo", False)


def _de_error(e):
    """Un ErrorServidor (o algo que se le parece) → {"ok": False, "clave", "texto", "datos", "sin_conexion"}."""
    datos = getattr(e, "datos", None) or {}
    return {"ok": False, "clave": str(datos.get("clave") or ""), "texto": str(getattr(e, "texto", "") or e),
            "datos": datos.get("datos") or {}, "sin_conexion": getattr(e, "status", 0) is None and
            not getattr(e, "tiempo", False)}


def _local_error(r):
    if isinstance(r, dict) and r.get("ok") is False:
        return {"ok": False, "clave": r.get("error") or "", "texto": _t(r.get("error") or "localhost.err.formato",
                                                                        **(r.get("datos") or {})),
                "datos": r.get("datos") or {}}
    return r


def campos_de_crear(comando, visible="", para="", como_habla="", que_si_no="", sobre_ti="", forma=None,
                    color=None, motor="", autonomia=True, revisar_skills=False):
    """Lo que manda la tarjeta (y la página) a /api/front/crear."""
    return {"nombre": comando, "visible": visible, "ayuda": para, "como_habla": como_habla,
            "que_si_no": que_si_no, "sobre_ti": sobre_ti, "forma": forma, "color": color, "motor": motor or "",
            "autonomia": bool(autonomia), "revisar_skills": bool(revisar_skills)}


def crear(campos, srv=None):
    """Arranca la creación. → {"ok": True, "job", "via": "pagina"|"aqui", "sin_sesion": bool} o un error con su
    clave. Si la página no contesta (o es de antes), lo crea aquí con la misma función."""
    cuerpo = {k: v for k, v in campos.items() if v is not None and v != ""}
    if _por_la_pagina(srv):
        try:
            r = srv.post("/api/front/crear", cuerpo)
            return dict(r, via="pagina")
        except Exception as e:
            err = _de_error(e)
            if not err.get("sin_conexion") and getattr(e, "status", None) not in (404, 503):
                return err
    import localhost_front
    r = _local_error(localhost_front.crear_agente(**cuerpo))
    return dict(r, via="aqui") if r.get("ok") else r


def estado(via, srv=None):
    """El job en curso (su vista de la página), por donde se creó."""
    if via == "pagina" and _por_la_pagina(srv):
        try:
            return srv.get("/api/front/crear").get("job")
        except Exception:
            return None
    import localhost_front
    return localhost_front.crear_estado().get("job")


def cancelar(via, srv=None):
    if via == "pagina" and srv is not None:
        try:
            srv.post("/api/front/crear/cancelar", {})
            return
        except Exception:
            pass
    import localhost_front
    localhost_front.crear_cancelar()


def visto(via, srv=None):
    if via == "pagina" and srv is not None:
        try:
            srv.post("/api/front/crear/visto", {})
            return
        except Exception:
            pass
    import localhost_front
    localhost_front.crear_visto()


#: Los 8 pasos del job oficial (agent_admin.CREATE_STEPS) en 4 frases para la persona.
PASOS_HUMANOS = (("carpeta", ("validar", "scaffold")), ("identidad", ("definicion", "registro", "tema")),
                 ("conecto", ("cableado", "launcher")), ("reviso", ("verificacion",)))
#: Los 6 de conectar uno que ya existe (agent_admin.LOAD_STEPS) en las mismas frases (la primera: su carpeta ya existe).
PASOS_HUMANOS_CARGA = (("carpeta_cargar", ("validar",)), ("identidad", ("identidad", "registro")),
                       ("conecto", ("cableado", "launcher")), ("reviso", ("verificacion",)))


def pasos_humanos(job, motor="", cargar=False):
    """[(texto, estado)] con estado ∈ pend · run · ok · fail: los 4 pasos humanos del job de crear (o, con `cargar`, del
    de conectar), de su vista de la página o del job mismo."""
    st = {p.get("key"): p.get("st") for p in (job or {}).get("pasos") or (job or {}).get("steps") or []}
    out = []
    for clave, llaves in (PASOS_HUMANOS_CARGA if cargar else PASOS_HUMANOS):
        e = [st.get(k, "pend") for k in llaves]
        if "fail" in e:
            v = "fail"
        elif all(x in ("ok", "warn", "skip") for x in e):
            v = "ok"
        elif any(x in ("run", "ok", "warn", "skip") for x in e):
            v = "run"
        else:
            v = "pend"
        mid = motor or (job or {}).get("motor") or (job or {}).get("engine") or ""
        out.append((_t("agregar.paso.%s" % clave, m=nombre_motor(mid) if mid else _t("agregar.motor.el_tuyo")), v))
    if (job or {}).get("done") and not (job or {}).get("ok"):
        if not any(v == "fail" for _t_, v in out):          # cancelado o error antes de un paso: el que iba
            for i, (t, v) in enumerate(out):
                if v in ("run", "pend"):
                    out[i] = (t, "fail")
                    break
    return out


def restos():
    """Una creación interrumpida (el proceso murió a medias) → {"snap", "estado", "motivo", "pendiente"} con lo que
    hay de verdad en disco (agent_create_job.assess: creado · sin_carpeta · restos · en_uso), o None."""
    try:
        import agent_create_job
        snap = agent_create_job.stale()
        if not snap:
            return None
        return dict(agent_create_job.assess(snap), snap=snap)
    except Exception:
        return None


def limpiar_restos(r):
    """«Reintentar»: si son restos demostrables de esa creación, a la papelera de Workspace (recuperables) y se
    suelta su aviso; si el agente ya quedó creado o hay algo ajeno, no se toca nada y solo se suelta el aviso.
    → (ok, detalle)."""
    try:
        import agent_create_job
        snap = (r or {}).get("snap")
        if (r or {}).get("estado") in ("restos", "sin_carpeta"):
            return agent_create_job.cleanup(snap)
        agent_create_job.dismiss(snap)
        return True, ""
    except Exception as e:
        return False, str(e)


# ── ya tengo un agente ─────────────────────────────────────────────────────────
def limpiar_ruta(texto, nt=None):
    """La carpeta de lo que pegaste o arrastraste: sin comillas («'…'» o «"…"»), sin los «\\ » de la Mac, con ~ y
    file:// resueltos. Si arrastraste varias, la primera. `nt`: como Windows (por omisión, esta computadora)."""
    nt = (os.name == "nt") if nt is None else nt
    t = str(texto or "").strip().replace("\r", "\n").split("\n")[0].strip()
    if not t:
        return ""
    if t.lower().startswith("file://"):
        u = urlparse(t)
        t = unquote(u.path or "")
        if nt and re.match(r"^/[A-Za-z]:", t):
            t = t[1:]
        if u.netloc and u.netloc != "localhost":           # \\servidor\carpeta
            t = "//" + u.netloc + t
    if t[0] in "'\"" and t[0] in t[1:]:                     # entre comillas (o varias arrastradas: la primera)
        t = t[1:t.index(t[0], 1)]
    if not nt:
        if " /" in t and not os.path.exists(t):
            partes = re.split(r"(?<!\\) (?=/|~)", t)       # «/a\ b /c» = dos arrastradas
            t = partes[0]
        t = re.sub(r"\\(.)", r"\1", t)
    t = os.path.expanduser(t)
    if nt:                                                  # las reglas de Windows, también desde otra máquina
        import ntpath
        t = ntpath.normpath(t)
        return t.rstrip("\\") if len(t) > 3 else t
    import posixpath
    return posixpath.normpath(t) if t else ""


def _incompleto(info, ruta):
    """¿Parece un cerebro a medio sincronizar (Obsidian todavía no termina)? Trae su identidad pero le faltan
    BOOT/ o STATE/, o es una bóveda de Obsidian casi vacía."""
    marcas = dict(info.get("marcas") or ())
    ident = bool(info.get("has_def")) or any(v for k, v in marcas.items() if k.endswith(".md"))
    faltan = [k for k in ("BOOT", "STATE") if not marcas.get(k)]
    if ident and faltan:
        return True
    try:
        nombres = [n for n in os.listdir(ruta) if not n.startswith(".")]
        if os.path.isdir(os.path.join(ruta, ".obsidian")) and not ident and len(nombres) <= 3 and \
                any(n.upper() in ("BOOT", "STATE", "WIKI", "SKILLS") for n in nombres):
            return True
    except OSError:
        pass
    return False


def _adentro(ruta):
    """Si la carpeta no es un agente pero UNA de sus carpetas sí: esa (la de adentro). '' si no."""
    try:
        import agentsreg
        import brain_identity
        hijos = [os.path.join(ruta, n) for n in sorted(os.listdir(ruta)) if not n.startswith(".")]
        for h in hijos[:200]:
            if os.path.isdir(h) and (agentsreg.has_definition(h) or
                                     os.path.isfile(os.path.join(h, brain_identity.identity_doc(h)))):
                return h
    except Exception:
        pass
    return ""


def radiografia(ruta):
    """Qué hay en `ruta`, en simple, ANTES de conectar (solo lee). → agent_admin.inspect_brain + {"veredicto",
    "libre", "adentro", "skills"}. veredicto ∈ vacio · no_existe · agente · incompleto · ya_conectado · choque ·
    no_agente."""
    import agent_admin
    ruta = limpiar_ruta(ruta)
    if not ruta:
        return {"veredicto": "vacio", "folder": "", "exists": False}
    try:
        info = dict(agent_admin.inspect_brain(ruta))
    except Exception:
        info = {"folder": ruta, "exists": False}
    if not info.get("exists"):
        info["veredicto"] = "no_existe"
        return info
    marcas = dict(info.get("marcas") or ())
    es = bool(info.get("has_def")) or bool(info.get("legacy_install")) or \
        any(v for k, v in marcas.items() if k.endswith(".md"))
    if _incompleto(info, info["folder"]):
        info["veredicto"] = "incompleto"
    elif not es:
        info["veredicto"] = "no_agente"
        info["adentro"] = _adentro(info["folder"])
    elif info.get("estado") == "cargado":
        info["veredicto"] = "ya_conectado"
    elif info.get("estado") == "colision":
        info["veredicto"] = "choque"
        info["libre"] = libre(info.get("name") or "agente")
    else:
        info["veredicto"] = "agente"
    try:
        n = 0
        for _r, _d, fs in os.walk(os.path.join(info["folder"], "skills")):
            n += sum(1 for f in fs if f == "SKILL.md")
            if n > 999:
                break
        info["skills"] = n
    except Exception:
        info["skills"] = 0
    return info


def texto_radiografia(info):
    """La frase de radiografia para la persona."""
    v = info.get("veredicto")
    nombre = info.get("display") or (info.get("name") or "").capitalize()
    if v == "no_existe":
        return _t("agregar.carpeta.no_existe", r=ruta_corta(info.get("folder")))
    if v == "no_agente":
        if info.get("adentro"):
            return _t("agregar.carpeta.adentro", r=os.path.basename(info["adentro"]))
        return _t("agregar.carpeta.no_agente")
    if v == "incompleto":
        return _t("agregar.carpeta.incompleto", n=nombre)
    if v == "ya_conectado":
        return _t("agregar.carpeta.ya", n=nombre)
    if v == "choque":
        return _t("agregar.carpeta.choque", n=info.get("name"), l=info.get("libre") or "")
    if v == "agente":
        motor = nombre_motor(info.get("engine")) if info.get("engine") else ""
        return _t("agregar.carpeta.agente", n=nombre, m=motor or _t("agregar.motor.el_tuyo"),
                  k=info.get("skills") or 0)
    return ""


def buscar(protegidas=False):
    """Los cerebros de esta computadora (agentsreg.discover, acotado) con su estado: {"found": [{name, brain, …}],
    "estados": {nombre: nuevo|cargado|otro}, "avisos": [...], "reg": {nombre: carpeta}}. Lo que discover escribe a
    stderr (dos cerebros con el mismo nombre) vuelve como `avisos`."""
    import io
    import agentsreg
    import agent_load_job
    avisos, found = [], []
    with agent_load_job.STDIO_LOCK:
        old = (sys.stdout, sys.stderr, sys.stdin)
        sys.stdout, sys.stderr, sys.stdin = io.StringIO(), io.StringIO(), io.StringIO("")
        try:
            found = agentsreg.discover(protegidas=protegidas) or []
        except Exception:
            found = []
        finally:
            try:
                errtxt = sys.stderr.getvalue()
            except Exception:
                errtxt = ""
            sys.stdout, sys.stderr, sys.stdin = old
    pref = _t("addagent.discover.warn_prefix")
    for ln in errtxt.splitlines():
        ln = ln.strip()
        if ln:
            avisos.append(ln.replace("WORKSPACE · aviso: ", "").replace(pref, ""))
    reg, estados = {}, {}
    try:
        reg = {a["name"]: a["brain"] for a in agentsreg.agents()}
    except Exception:
        pass
    for a in found:
        n = a["name"]
        if n not in reg:
            estados[n] = "nuevo"
        elif os.path.realpath(reg[n]) == os.path.realpath(a["brain"]):
            estados[n] = "cargado"
        else:
            estados[n] = "otro"
    return {"found": found, "estados": estados, "avisos": avisos, "reg": reg, "protegidas": bool(protegidas)}


def es_mac():
    try:
        import agentsreg
        return bool(agentsreg._mac())
    except Exception:
        return sys.platform == "darwin"


def encontrados(protegidas=False):
    """Para la tarjeta y la página: cada cerebro encontrado con su monito y su estado, los nuevos primero."""
    r = buscar(protegidas)
    out = []
    for a in r["found"]:
        n = a["name"]
        info = {}
        try:
            import agentsreg
            info = agentsreg.load_definition(a["brain"]) or {}
        except Exception:
            pass
        try:
            import localhost_front
            forma = localhost_front._forma_por_omision(n)
            color = localhost_front._color_conocido(info.get("color")) or localhost_front.COLORES[
                sum(map(ord, n)) % len(localhost_front.COLORES)]
        except Exception:
            forma, color = "bolita", GRIS
        estado_ = r["estados"].get(n, "nuevo")
        try:
            import agent_admin
            if estado_ == "nuevo" and _incompleto(agent_admin.inspect_brain(a["brain"]), a["brain"]):
                estado_ = "incompleto"
        except Exception:
            pass
        out.append({"nombre": n, "visible": str(info.get("display") or n.capitalize()), "carpeta": a["brain"],
                    "corta": ruta_corta(a["brain"]), "estado": estado_,
                    "motor": str(info.get("engine") or ""), "forma": forma, "color": color})
    orden = {"nuevo": 0, "otro": 1, "incompleto": 2, "cargado": 3}
    out.sort(key=lambda x: (orden.get(x["estado"], 3), x["nombre"]))
    return {"encontrados": out, "avisos": r["avisos"], "protegidas": r["protegidas"], "mac": es_mac()}


def conectar(items, prefs=None, srv=None):
    """Conecta los cerebros `items` [(nombre, carpeta)] con el job de cargar: por la página si contesta; si no,
    aquí. `nombre`: el que quieres que tenga (choque de nombres: uno libre; la carpeta nunca se renombra).
    → {"ok", "job", "via"} o un error con su clave."""
    items = [(str(n or ""), str(c or "")) for n, c in items]
    if _por_la_pagina(srv):
        try:
            cuerpo = {"carpetas": [c for _n, c in items], "nombres": [n for n, _c in items]}
            # Solo lo que el socio eligió: sin preferencias, el agente conserva sus permisos y su revisión de skills
            # (antes iba «autonomia: true» y «revisar_skills: false» siempre, y cargar los guardaba).
            if isinstance(prefs, dict) and prefs.get("autonomy") is not None:
                cuerpo["autonomia"] = prefs.get("autonomy") != "ask"
            if isinstance(prefs, dict) and prefs.get("skill_review") is not None:
                cuerpo["revisar_skills"] = bool(prefs.get("skill_review"))
            r = srv.post("/api/front/cargar", cuerpo)
            return dict(r, via="pagina")
        except Exception as e:
            err = _de_error(e)
            if not err.get("sin_conexion") and getattr(e, "status", None) not in (404, 503):
                return err
    import agent_load_job
    r = agent_load_job.iniciar(items, prefs)
    return dict(r, via="aqui") if r.get("ok") else _local_error(r)


def estado_carga(via, srv=None):
    if via == "pagina" and srv is not None:
        try:
            return srv.get("/api/front/cargar").get("job")
        except Exception:
            return None
    import agent_load_job
    return agent_load_job.vista(agent_load_job.active())


def visto_carga(via, srv=None):
    if via == "pagina" and srv is not None:
        try:
            srv.post("/api/front/cargar/visto", {})
            return
        except Exception:
            pass
    import agent_load_job
    agent_load_job.ack()


# ── la lista de agentes sin la página (para volver a Inicio con el nuevo elegido) ─────────────────────────────
def agentes_aqui():
    """Los agentes con su monito, como /api/front/inicio, calculados aquí (localhost_front.inicio): para cuando la
    página no contesta."""
    try:
        import localhost_front
        cerebros = dict(localhost_front._cerebros())
        filas = localhost_front.inicio().get("agentes") or []
    except Exception:
        return None
    out = []
    for x in filas:
        aid = str(x.get("id") or "")
        if aid:
            out.append({"id": aid, "n": str(x.get("nombre") or aid), "c": x.get("color") or "#ffffff",
                        "f": x.get("forma") or "bolita", "mid": str(x.get("motor") or ""),
                        "brain": cerebros.get(aid) or ""})
    return out


def en_fondo(fn):
    threading.Thread(target=fn, name="agregar", daemon=True).start()


# ── lo que gasta tokens o sale a internet (AG6-a): una vez, DESPUÉS de que el agente existe ───────────────────
def oferta_afinar(motor):
    """¿Se puede afinar con IA con ese motor, y cuánto cuesta (estimado)? → {"ok", "tokens", "nota"}. Sin modo
    headless no se ofrece (sin cambiar a escondidas a otro modelo)."""
    try:
        import agent_personalize
        b, _tools, nota = agent_personalize.pick_backend(motor)
    except Exception as e:
        return {"ok": False, "tokens": None, "nota": str(e)}
    tokens = None
    try:
        import agent_create_job
        tokens = agent_create_job.estimate().get("personalize_tokens")
    except Exception:
        pass
    return {"ok": b is not None, "tokens": tokens, "nota": nota or ""}


def cerebro_de(comando):
    """La carpeta del cerebro de un agente registrado, o ''."""
    try:
        import agentsreg
        return (agentsreg.find(comando) or {}).get("brain") or ""
    except Exception:
        return ""


def afinar(comando, params, progress=None, should_cancel=None):
    """La pasada de personalización (agent_personalize.run) sobre el cerebro ya creado: aditiva, todo o nada; si
    falla, el agente sigue como nació. → su resultado ({"ok", "tokens_est", "note", …})."""
    import agent_personalize
    brain = cerebro_de(comando)
    if not brain:
        return {"ok": False, "note": _t("localhost.err.agente")}
    return agent_personalize.run(brain, dict(params, personalize=True), progress=progress,
                                 should_cancel=should_cancel)


def _params_skills(params):
    import skill_source_preferences
    p = dict(params)
    p["skill_source_config"] = skill_source_preferences.load()
    p["community_query"] = str((params.get("intake") or {}).get("proposito") or params.get("tagline") or "")[:120]
    return p


def buscar_skills(params, should_cancel=None):
    """Las skills de las fuentes permitidas que coinciden con lo que hace (GitHub y skills.sh; 0 tokens; no escribe
    nada). → {"candidates": [...], "errors": [...], "note"}."""
    import agent_skill_sources
    return agent_skill_sources.discover(_params_skills(params), should_cancel=should_cancel)


def instalar_skills(comando, params, elegidas, progress=None, should_cancel=None):
    """Instala las elegidas (revisión estática, atómica, sin sobrescribir). → {"installed", "held", "errors"}."""
    import agent_skill_sources
    brain = cerebro_de(comando)
    if not brain:
        return {"installed": [], "held": [], "errors": [_t("localhost.err.agente")]}
    p = _params_skills(params)
    p["skill_candidates"] = list(elegidas)[:agent_skill_sources.MAX_SELECTED]
    p["approved_community_repos"] = sorted({c["repo"] for c in p["skill_candidates"]
                                            if c.get("discovered_via") == "skills.sh"})
    return agent_skill_sources.run(brain, p, progress=progress, should_cancel=should_cancel)


# ── el primer arranque (la tarjeta con el paso «Tú») ──────────────────────────────────────────────────────────
def ruta_primer_arranque():
    """Donde queda constancia de que el primer arranque ya pasó (el mismo onboarded.json de siempre; env
    WORKSPACE_ONBOARDED la pisa)."""
    p = os.environ.get("WORKSPACE_ONBOARDED", "").strip()
    if p:
        return os.path.expanduser(p)
    import paths
    return os.path.join(paths.state_dir(), "onboarded.json")


def es_primer_arranque():
    """¿Es la primera vez en esta computadora? Sin constancia y sin ningún agente. Un archivo ilegible cuenta como
    que ya pasó (ante la duda, no volver a preguntar)."""
    try:
        if os.path.exists(ruta_primer_arranque()):
            return False
    except Exception:
        return False
    try:
        import agent_state
        return not agent_state.snapshot().registered()
    except Exception:
        return False


def marcar_primer_arranque(motor="", agentes=()):
    """Deja constancia (merge sobre lo que haya): ya no se vuelve a ofrecer. El motor elegido queda como el de los
    agentes nuevos (modelos.default_engine), como hacía el primer arranque de antes."""
    import datetime
    import json
    p = ruta_primer_arranque()
    data = {"version": 1}
    try:
        with open(p, encoding="utf-8") as fh:
            prev = json.load(fh)
        if isinstance(prev, dict):
            data.update(prev)
    except Exception:
        pass
    data.update({"ts": datetime.datetime.now().isoformat(timespec="seconds"), "modo": "tarjeta",
                 "completo": bool(agentes), "agentes": list(agentes), "default_engine": motor or ""})
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        pass
    if motor:
        try:
            import config_engine
            config_engine.set_setting("modelos.default_engine", motor, actor="onboarding")
        except Exception:
            try:
                import settings
                settings.set("modelos.default_engine", motor)
            except Exception:
                pass
