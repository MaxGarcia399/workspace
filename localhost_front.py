"""WORKSPACE · localhost_front — lo que el front nuevo de la página local necesita y el de antes no tenía.

Un agente = una conversación. El panel del agente lee y cambia:
  · apariencia (forma y color del monito) y nombre visible: preferencias de ESTA computadora
    (`<state_dir>/web/front.json`); no se toca el agent.json del agente;
  · su tono: los mismos diales de `personalidad` (tono.json), con estilos hechos que mueven varios a la vez;
  · sus archivos importantes del cerebro (lista cerrada; STATE/MEMORY.md solo lectura), con respaldo antes de
    guardar y control de cambios (si cambió en disco desde que se abrió, no se pisa);
  · el uso de su motor que no sale de la pantalla (instantánea de usage.json para Claude Code).

Contrato igual que localhost_sistema: {"ok": true, ...} o {"ok": false, "error": <clave i18n>, "status": n}.
Nada de rutas armadas con lo que manda la página: agente y archivo se validan contra listas cerradas.
"""
import hashlib
import json
import os
import re
import threading
import time
import uuid

import paths as _paths

SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
FORMAS = ("bolita", "pico", "cuadrito", "gatito", "fantasma", "nube")
COLORES = ("#ff4fa3", "#3fbf7f", "#3b82f6", "#e7a43a", "#8b5cf6", "#ffffff")
MAX_ARCHIVO = 256 * 1024
MAX_FIJAS = 50
#: Los archivos del cerebro que el panel enseña (ruta relativa al cerebro, nombre para la persona, editable).
ARCHIVOS = (
    ("BRAIN.md", "Quién es", True),
    ("BOOT/00-SOUL.md", "Su forma de ser", True),
    ("BOOT/01-IDENTITY.md", "Su identidad", True),
    ("BOOT/03-RULES.md", "Sus reglas", True),
    ("STATE/PENDIENTES.md", "Sus pendientes", True),
    ("STATE/MEMORY.md", "Lo que recuerda", False),
)
_ARCHIVO = {a[0]: a for a in ARCHIVOS}
#: Estilos de tono: mueven los diales de `personalidad` de golpe. El ejemplo es cómo contestaría a la misma
#: pregunta; la instrucción que de verdad recibe el agente la arma `personalidad` con estos niveles.
PREGUNTA_EJEMPLO = "¿Cómo va el reporte del cliente?"
ESTILOS = (
    ("Al grano", "Socio", "directo, técnico y breve",
     {"franqueza": 5, "sarcasmo": 4, "longitud": 1, "tecnicismo": 5, "didactica": 5, "iniciativa": 5, "emojis": 1},
     "Atrasado: faltan 2 de 4 pasos. Sin el Excel de la tarea 2 no califico costo; ya se lo pedí al cliente."),
    ("Al grano", "Ejecutivo", "solo lo esencial, en viñetas",
     {"amabilidad": 2, "franqueza": 4, "sarcasmo": 1, "longitud": 2, "formalidad": 4, "didactica": 1, "iniciativa": 4, "emojis": 1},
     "• Avance: 50 %\n• Bloqueo: falta el Excel de la tarea 2\n• Entrega: mañana 10:00 si llega hoy"),
    ("Al grano", "Telegrama", "lo mínimo, sin saludos",
     {"amabilidad": 1, "franqueza": 5, "humor": 1, "longitud": 1, "didactica": 1, "emojis": 1},
     "Mitad. Falta Excel tarea 2."),
    ("Al grano", "Formal", "cortés y de usted",
     {"amabilidad": 4, "franqueza": 2, "sarcasmo": 1, "humor": 1, "longitud": 4, "formalidad": 5, "emojis": 1},
     "Estimado socio: el reporte lleva un avance del 50 %. Para concluirlo, requerimos el archivo de la tarea 2. "
     "Quedo atento para entregarlo a la brevedad."),
    ("Cercanos", "Amable", "cálido y paciente",
     {"amabilidad": 5, "franqueza": 2, "sarcasmo": 1, "didactica": 4, "emojis": 2},
     "¡Va bien! Ya tengo la mitad lista. Solo me falta un archivo de la tarea 2; en cuanto me lo pases, lo termino "
     "con calma y te aviso."),
    ("Cercanos", "Cuate", "como un amigo, relajado",
     {"amabilidad": 4, "humor": 4, "formalidad": 1, "tecnicismo": 1, "emojis": 4},
     "¡Qué onda! Va a medias 😅 Me falta el Excel de la tarea 2; pásamelo y lo sacamos hoy mismo 💪"),
    ("Cercanos", "Divertido", "con humor ligero",
     {"sarcasmo": 4, "humor": 5, "longitud": 2, "formalidad": 2, "emojis": 4},
     "Va como tortuga con prisa 🐢: mitad hecho. El Excel de la tarea 2 sigue de vacaciones; mándamelo y lo "
     "cerramos hoy."),
    ("Cercanos", "Coach", "te impulsa y te reta",
     {"amabilidad": 4, "franqueza": 4, "longitud": 2, "didactica": 4, "iniciativa": 5},
     "Vamos a la mitad y el siguiente paso depende de ti: ¿me mandas hoy el Excel de la tarea 2? Si lo hacemos, "
     "mañana lo presentas."),
    ("Para pensar", "Profe", "te explica el porqué",
     {"amabilidad": 4, "longitud": 4, "tecnicismo": 2, "didactica": 5},
     "Vamos en el paso 3 de 4. Te explico: para calificar el costo necesito los precios del Excel de la tarea 2; "
     "sin ellos, la comparación saldría incompleta. En cuanto lo tenga, armo el reporte."),
    ("Para pensar", "Analista", "datos y precisión",
     {"sarcasmo": 1, "humor": 1, "longitud": 4, "formalidad": 4, "tecnicismo": 5, "emojis": 1},
     "Avance 2/4 (50 %). Tareas 1 y 3 calificadas. Tarea 2 sin datos de costo: afecta 1 de 5 criterios. "
     "Cierre estimado: 3 h después de recibir el Excel."),
    ("Para pensar", "Crítico", "cuestiona y ve riesgos",
     {"amabilidad": 2, "franqueza": 5, "sarcasmo": 2, "longitud": 4, "tecnicismo": 4, "iniciativa": 4},
     "Va a la mitad, pero ojo: si comparamos sin el costo de la tarea 2, el reporte favorece al asistente más caro. "
     "Yo no lo entregaría así."),
    ("Para pensar", "Creativo", "propone ideas nuevas",
     {"humor": 4, "longitud": 4, "formalidad": 2, "iniciativa": 5},
     "Va a la mitad, y se me ocurrió algo: en vez de una tabla, lo armo como un torneo donde los asistentes compiten "
     "por criterio. Solo me falta el Excel de la tarea 2."),
)


_LOCK = threading.RLock()        # el servidor atiende en hilos: todo leer-modificar-escribir va por aquí
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f  ‪-‮⁦-⁩]")
_RENGLON = re.compile("[\r\n\t\x00-\x1f\x7f-\x9f  ‪-‮⁦-⁩]")
MAX_RESPALDOS = 20               # por archivo: lo de antes siempre se puede recuperar, sin llenar el disco
USO_VIEJO_S = 20 * 60            # usage.json más viejo que esto ya no es «ahora» (igual que heartbeat)


def _mal(clave, status=400):
    return {"ok": False, "error": clave, "status": status}


class _Ilegible(Exception):
    """El archivo existe pero no se puede leer como texto (binario, carpeta, permisos)."""


class _Grande(Exception):
    """Más grande de lo que la página edita: se rechaza, NUNCA se recorta."""


def _leer(dest):
    """Texto completo (con sus fines de línea tal cual) o None si no existe."""
    try:
        with open(dest, encoding="utf-8", newline="") as f:
            t = f.read(MAX_ARCHIVO + 1)
    except FileNotFoundError:
        return None
    except (UnicodeDecodeError, IsADirectoryError, PermissionError, OSError) as e:
        raise _Ilegible(str(e))
    if len(t) > MAX_ARCHIVO:
        raise _Grande()
    return t


def _escribir_atomico(dest, texto):
    try:
        import atomico                      # reintenta los bloqueos pasajeros de Windows (antivirus, Obsidian)
        atomico.escribir(dest, texto, newline="")
        return True
    except Exception:
        return False


def _secreto(texto):
    try:
        import secret_scan
        return bool(secret_scan.scan_text(texto or ""))
    except Exception:
        return False


def _renglon_ok(t, maximo):
    return isinstance(t, str) and 0 < len(t) <= maximo and not _RENGLON.search(t)


# ── preferencias de esta computadora ─────────────────────────────────────────
def ruta_prefs():
    return os.path.join(_paths.state_dir(), "web", "front.json")


def _vacio():
    return {"schema": 1, "agentes": {}}


def leer_prefs():
    """Jamás levanta: ausente o corrupto → vacío."""
    try:
        with open(ruta_prefs(), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("agentes"), dict):
            return d
    except Exception:
        pass
    return _vacio()


def _guardar_prefs(d):
    return _escribir_atomico(ruta_prefs(), json.dumps(d, ensure_ascii=False, indent=2))


def _prefs_de(prefs, agente):
    v = prefs["agentes"].get(agente)
    return v if isinstance(v, dict) else {}


def _cambiar_prefs(agente, **cambios):
    with _LOCK:
        prefs = leer_prefs()
        actual = dict(_prefs_de(prefs, agente))
        for k, v in cambios.items():
            if v is None:
                actual.pop(k, None)
            else:
                actual[k] = v
        if actual:
            prefs["agentes"][agente] = actual
        else:
            prefs["agentes"].pop(agente, None)
        return _guardar_prefs(prefs)


# ── agentes ──────────────────────────────────────────────────────────────────
def _cerebros():
    try:
        import messages
        return messages.registered_brains()
    except Exception:
        return {}


def _snapshot():
    try:
        import agent_state
        return [a for a in agent_state.snapshot().agents if not a.get("hidden")]
    except Exception:
        return []


def _agente_valido(agente):
    if not isinstance(agente, str) or not SLUG_RE.match(agente):
        return None
    for a in _snapshot():
        if a.get("id") == agente:
            return a
    return None


def _forma_por_omision(agente):
    """Solo del id: agregar o quitar agentes no les cambia la forma a los demás."""
    return FORMAS[int(hashlib.sha1(agente.encode("utf-8")).hexdigest(), 16) % len(FORMAS)]


#: El color que ya trae su agent.json (nombre en español o inglés) → el de la paleta de los monitos.
_COLOR_NOMBRE = {
    "#ff4fa3": ("rosa", "pink", "rojo", "red", "magenta", "fucsia"),
    "#3fbf7f": ("verde", "green", "menta", "mint", "teal", "cian", "cyan"),
    "#3b82f6": ("azul", "blue", "celeste", "navy", "indigo"),
    "#e7a43a": ("amarillo", "yellow", "naranja", "orange", "ambar", "ámbar", "amber", "dorado", "gold", "cafe", "café", "brown"),
    "#8b5cf6": ("morado", "purple", "violeta", "violet", "lila", "lavanda", "lavender"),
    "#ffffff": ("blanco", "white", "gris", "gray", "grey", "plata", "silver", "negro", "black"),
}


def _color_conocido(nombre_color):
    """El color de la paleta que corresponde al de su agent.json, o None si no lo reconoce."""
    n = (nombre_color or "").strip().lower()
    if n in COLORES:
        return n
    for hexa, nombres in _COLOR_NOMBRE.items():
        if n in nombres:
            return hexa
    return None


def inicio():
    """Todo lo que la página necesita para arrancar: los agentes con su monito y sus preferencias.

    El monito de un agente sin elegir se reparte UNA vez (forma y color distintos a los de los demás, su color de
    agent.json si nadie más lo trae) y se guarda: agregar o quitar agentes después no les cambia el suyo."""
    prefs = leer_prefs()
    agentes = _snapshot()
    av_de = {a.get("id"): dict(_prefs_de(prefs, a.get("id")).get("avatar") or {}) for a in agentes}
    usados_c = {v["color"] for v in av_de.values() if v.get("color") in COLORES}
    usados_f = {v["forma"] for v in av_de.values() if v.get("forma") in FORMAS}
    nuevos = {}
    for a in agentes:              # primero, el color que ya trae su agent.json (si nadie lo reclamó)
        av = av_de[a.get("id")]
        if av.get("color") not in COLORES:
            c = _color_conocido(a.get("color"))
            if c and c not in usados_c:
                av["color"] = c
                usados_c.add(c)
                nuevos.setdefault(a.get("id"), {})["color"] = c
    for a in agentes:
        aid, av = a.get("id"), av_de[a.get("id")]
        h = int(hashlib.sha1((aid or "").encode("utf-8")).hexdigest(), 16)
        if av.get("color") not in COLORES:
            libres = [c for c in COLORES[h % len(COLORES):] + COLORES[:h % len(COLORES)] if c not in usados_c]
            av["color"] = libres[0] if libres else COLORES[h % len(COLORES)]
            usados_c.add(av["color"])
            nuevos.setdefault(aid, {})["color"] = av["color"]
        if av.get("forma") not in FORMAS:
            libres = [f for f in FORMAS[h % len(FORMAS):] + FORMAS[:h % len(FORMAS)] if f not in usados_f]
            av["forma"] = libres[0] if libres else _forma_por_omision(aid or "")
            usados_f.add(av["forma"])
            nuevos.setdefault(aid, {})["forma"] = av["forma"]
    if nuevos:
        with _LOCK:
            p2 = leer_prefs()
            for aid, cambio in nuevos.items():
                act = dict(_prefs_de(p2, aid))
                avatar = dict(act.get("avatar") or {})
                for k, v in cambio.items():
                    avatar.setdefault(k, v)
                act["avatar"] = avatar
                p2["agentes"][aid] = act
            _guardar_prefs(p2)
    out = []
    for a in agentes:
        p, av = _prefs_de(prefs, a.get("id")), av_de[a.get("id")]
        out.append({
            "id": a.get("id"), "nombre": p.get("nombre") or a.get("display") or a.get("id"),
            "nombre_original": a.get("display") or a.get("id"), "lema": a.get("tagline") or "",
            "motor": a.get("engine") or "", "status": a.get("status") or "",
            "forma": av["forma"], "color": av["color"],
            "fijas": [x for x in (p.get("fijas") or []) if isinstance(x, str)][:MAX_FIJAS],
            "detenidas": [x for x in (p.get("detenidas") or []) if isinstance(x, str)][-MAX_DETENIDAS:],
        })
    import ajustes_motor                            # los botones de modelo, esfuerzo y modo de cada motor (§6)
    return {"ok": True, "agentes": out, "formas": list(FORMAS), "colores": list(COLORES),
            "ajustes": ajustes_motor.para_pagina(), "guia_vista": prefs.get("guia") == "vista",
            "pagina": _pagina_de(prefs)}


def guia(vista):
    """La guía de la página ya se vio (o, con False, que vuelva a salir sola). Se recuerda aquí, en lo de esta
    computadora, y no en el navegador: la página se sirve en un puerto distinto en cada arranque y para el navegador
    cada puerto es otro sitio, con su recuerdo vacío (la guía salía cada vez)."""
    with _LOCK:
        prefs = leer_prefs()
        if prefs.get("guia") == ("vista" if vista else None):
            return {"ok": True}                     # ya estaba así: no se reescribe el archivo
        if vista:
            prefs["guia"] = "vista"
        else:
            prefs.pop("guia", None)
        if not _guardar_prefs(prefs):
            return _mal("localhost.err.guardar", 500)
    return {"ok": True}


# ── lo que la página recuerda de un arranque a otro ──────────────────────────
# El tema, el agente activo, la pestaña que ves de cada agente, «enviar con ⌘↵», el motor por defecto y «Ahora no».
# Vivían en el localStorage del navegador, que es por sitio (con puerto): la página se sirve en un puerto distinto en
# cada arranque y cada arranque empezaba sin nada. Aquí, una lista cerrada con UNA ruta (/api/front/pagina).
MAX_PAGINA_MAPA = 200
_TEMA_CLAVE = re.compile(r"^[a-z_]{1,16}$")
_TEMA_VALOR = re.compile(r"^[A-Za-z0-9#._-]{0,16}$")


def _pag_bool(v):
    return v if type(v) is bool else None


def _pag_slug(v):
    return v if isinstance(v, str) and SLUG_RE.match(v) else None


def _pag_tema(v):
    """El tema tal como lo guarda la página hoy (p, k, x, ver): letras y números cortos, nada más."""
    if not isinstance(v, dict) or not v or len(v) > 8:
        return None
    for k, x in v.items():
        if not (isinstance(k, str) and _TEMA_CLAVE.match(k) and isinstance(x, str) and _TEMA_VALOR.match(x)):
            return None
    return dict(v)


def _pag_mapa(valor_ok):
    """{agente: valor}; vacío = quitarlo."""
    def revisar(v):
        if not isinstance(v, dict) or len(v) > MAX_PAGINA_MAPA:
            return None
        for k, x in v.items():
            if not (isinstance(k, str) and SLUG_RE.match(k) and valor_ok(x)):
                return None
        return dict(v)
    return revisar


#: clave → quien la revisa (→ el valor limpio, o None si no vale).
PAGINA = {
    "tema": _pag_tema,
    "tema_predeterminado": _pag_bool,
    "cmd_enter": _pag_bool,
    "motor_def": _pag_slug,
    "activo": _pag_slug,
    "tabs": _pag_mapa(lambda x: _renglon_ok(x, 120)),
    "luego": _pag_mapa(lambda x: _renglon_ok(x, 40)),
}


def _pagina_de(prefs):
    """Lo guardado, ya revisado: un archivo tocado a mano o roto no le llega a la página."""
    d = prefs.get("pagina")
    out = {}
    if isinstance(d, dict):
        for k, revisar in PAGINA.items():
            if k in d:
                v = revisar(d[k])
                if v is not None and v != {}:
                    out[k] = v
    return out


def pagina(cambios):
    """Anota lo que la página recuerda: {clave: valor} de la lista cerrada; None (o un mapa vacío) lo quita.
    Todo o nada: con una clave desconocida o un valor que no vale, no se anota ninguna."""
    limpio = {}
    for k, v in cambios.items():
        if k not in PAGINA:
            return _mal("localhost.err.formato")
        if v is None:
            limpio[k] = None
            continue
        x = PAGINA[k](v)
        if x is None:
            return _mal("localhost.err.formato")
        limpio[k] = None if x == {} else x
    with _LOCK:
        prefs = leer_prefs()
        antes = _pagina_de(prefs)
        ahora = dict(antes)
        for k, v in limpio.items():
            if v is None:
                ahora.pop(k, None)
            else:
                ahora[k] = v
        if ahora == antes and prefs.get("pagina", {}) == antes:
            return {"ok": True}                     # ya estaba así: no se reescribe el archivo
        if ahora:
            prefs["pagina"] = ahora
        else:
            prefs.pop("pagina", None)
        if not _guardar_prefs(prefs):
            return _mal("localhost.err.guardar", 500)
    return {"ok": True}


def apariencia(agente, forma=None, color=None):
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    if forma is not None and forma not in FORMAS:
        return _mal("localhost.err.formato")
    if color is not None and color not in COLORES:
        return _mal("localhost.err.formato")
    with _LOCK:
        av = dict(_prefs_de(leer_prefs(), agente).get("avatar") or {})
        if forma:
            av["forma"] = forma
        if color:
            av["color"] = color
        if not _cambiar_prefs(agente, avatar=av):
            return _mal("localhost.err.guardar", 500)
    return {"ok": True, "forma": av.get("forma"), "color": av.get("color")}


def nombre(agente, nombre):
    """El nombre con que lo ves en esta computadora (vacío = el suyo). No cambia su identidad."""
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    n = (nombre or "").strip()
    if n and not _renglon_ok(n, 40):
        return _mal("localhost.err.nombre")
    if not _cambiar_prefs(agente, nombre=n or None):
        return _mal("localhost.err.guardar", 500)
    return {"ok": True, "nombre": n}


MAX_DETENIDAS = 100


def prefs(agente, fijas=None, detenidas=None):
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    cambios = {}
    if fijas is not None:
        # los nombres de skill son libres (acentos, ñ): solo largo y sin caracteres de control
        if len(fijas) > MAX_FIJAS or not all(_renglon_ok(s, 80) and "/" not in s for s in fijas):
            return _mal("localhost.err.formato")
        cambios["fijas"] = list(dict.fromkeys(fijas)) or None
    if detenidas is not None:
        if not all(isinstance(s, str) and SLUG_RE.match(s) for s in detenidas):
            return _mal("localhost.err.formato")
        cambios["detenidas"] = list(dict.fromkeys(detenidas))[-MAX_DETENIDAS:] or None
    if cambios and not _cambiar_prefs(agente, **cambios):
        return _mal("localhost.err.guardar", 500)
    return {"ok": True}


# ── tono ─────────────────────────────────────────────────────────────────────
def _instruccion(niveles):
    """Lo mismo que `personalidad.linea()` le inyecta al agente, armado con estos niveles (un dial por renglón)."""
    import personalidad
    t = personalidad.linea_de(niveles)
    pre = personalidad._t("tono.inject.prefix", "[tono activo] ")
    if t.startswith(pre):
        t = t[len(pre):]
    return "\n".join(x.strip() for x in t.split("  ") if x.strip())


def _completo(parcial):
    import personalidad
    return {k: int(parcial.get(k, personalidad.NEUTRO)) for k in personalidad._DIAL_KEYS}


def tono(agente):
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    import personalidad
    act = personalidad.niveles(agente)
    estilos = []
    for grupo, n, desc, niv, ej in ESTILOS:
        completo = _completo(niv)
        estilos.append({"grupo": grupo, "nombre": n, "desc": desc, "niveles": completo, "ejemplo": ej,
                        "instruccion": _instruccion(completo), "huella": [completo[k] for k in personalidad._DIAL_KEYS]})
    actual = next((e["nombre"] for e in estilos if e["niveles"] == act), "")
    diales = [{"key": d["key"], "label": d["label"], "eje": list(d["eje"])} for d in personalidad._dials()]
    return {"ok": True, "niveles": act, "estilo": actual, "estilos": estilos, "diales": diales,
            "pregunta": PREGUNTA_EJEMPLO, "instruccion": _instruccion(act)}


def tono_guardar(agente, niveles):
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    import personalidad
    limpio = {}
    for k, v in (niveles or {}).items():
        if k not in personalidad._DIAL_KEYS or type(v) is not int or not 1 <= v <= 5:
            return _mal("localhost.err.formato")
        limpio[k] = v
    with _LOCK:
        for k, v in limpio.items():
            if not personalidad.set_nivel(k, v, agente):
                return _mal("localhost.err.guardar", 500)
    return tono(agente)


# ── archivos del cerebro ─────────────────────────────────────────────────────
def _ruta_en_cerebro(agente, ruta):
    """(cerebro real, ruta absoluta) solo si el agente tiene cerebro aquí y la ruta está en la lista cerrada."""
    if ruta not in _ARCHIVO and ruta != RUTA_PEND:
        return None, None
    cerebro = _cerebros().get(agente)
    if not cerebro:
        return None, None
    base = os.path.realpath(cerebro)
    dest = os.path.realpath(os.path.join(base, *ruta.split("/")))
    if not dest.startswith(base + os.sep):
        return None, None
    return base, dest


def _editable(cerebro, ruta):
    """Lo de STATE en un cerebro que se ordena por inbox lo escribe su consolidador, no la página."""
    if not _ARCHIVO[ruta][2]:
        return False
    return not (ruta.startswith("STATE/") and _modo(cerebro) == "inbox")


def _firma(texto):
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16] if texto is not None else ""


def archivos(agente):
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    out = []
    for ruta, nom, editable in ARCHIVOS:
        cerebro, dest = _ruta_en_cerebro(agente, ruta)
        out.append({"ruta": ruta, "nombre": nom, "editable": _editable(cerebro, ruta) if cerebro else editable,
                    "existe": bool(dest and os.path.isfile(dest))})
    return {"ok": True, "archivos": out, "tiene_cerebro": bool(_cerebros().get(agente))}


def archivo(agente, ruta):
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    cerebro, dest = _ruta_en_cerebro(agente, ruta)
    if not dest or ruta not in _ARCHIVO:
        return _mal("localhost.err.archivo", 404)
    try:
        texto = _leer(dest)
    except _Grande:
        return _mal("localhost.err.archivo_largo", 413)
    except _Ilegible:
        return _mal("localhost.err.archivo", 422)
    return {"ok": True, "ruta": ruta, "nombre": _ARCHIVO[ruta][1], "editable": _editable(cerebro, ruta),
            "existe": texto is not None, "texto": texto or "", "firma": _firma(texto)}


def _respaldar(agente, ruta, texto):
    """Copia de lo que había antes de guardar, FUERA del cerebro (no viaja por Sync); se quedan las últimas
    MAX_RESPALDOS por archivo."""
    if texto is None:
        return True
    carpeta = os.path.join(_paths.state_dir(), "web", "respaldos", agente)
    base = ruta.replace("/", "__") + "."
    sello = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]     # dos guardados en el mismo segundo no se pisan
    if not _escribir_atomico(os.path.join(carpeta, base + sello), texto):
        return False
    try:
        viejos = sorted(n for n in os.listdir(carpeta) if n.startswith(base))
        for n in viejos[:-MAX_RESPALDOS]:
            os.remove(os.path.join(carpeta, n))
    except OSError:
        pass
    return True


def archivo_guardar(agente, ruta, texto, firma=""):
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    cerebro, dest = _ruta_en_cerebro(agente, ruta)
    if not dest or ruta not in _ARCHIVO:
        return _mal("localhost.err.archivo", 404)
    if not _editable(cerebro, ruta):
        return _mal("localhost.err.archivo_solo", 403)
    if len(texto) > MAX_ARCHIVO:
        return _mal("localhost.err.archivo_largo", 413)
    if _secreto(texto):
        return _mal("localhost.err.llave")
    with _LOCK:
        try:
            antes = _leer(dest)
        except _Grande:
            return _mal("localhost.err.archivo_largo", 413)
        except _Ilegible:
            return _mal("localhost.err.archivo", 422)
        if _firma(antes) != (firma or ""):
            return _mal("localhost.err.archivo_cambio", 409)
        if antes == texto:
            return {"ok": True, "firma": _firma(texto), "respaldo": False}
        if not _respaldar(agente, ruta, antes):
            return _mal("localhost.err.guardar", 500)
        if not _escribir_atomico(dest, texto):
            return _mal("localhost.err.guardar", 500)
    return {"ok": True, "firma": _firma(texto), "respaldo": antes is not None}


# ── renombrar una skill desde su tarjeta ─────────────────────────────────────
_SKILL_NUEVO = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")      # como se nombran las carpetas de skills


def _devolver(destino, origen, movidos):
    """Deshace un renombre a medias: lo movido vuelve a su carpeta y la reservada se quita."""
    try:
        os.makedirs(origen, exist_ok=True)
        for x in movidos:
            os.rename(os.path.join(destino, x), os.path.join(origen, x))
        os.rmdir(destino)
    except OSError:
        pass


def skill_renombrar(agente, skill, nuevo):
    """Su carpeta y el `name:` de su SKILL.md toman `nuevo`, sin pisar otra skill (ni por nombre ni por carpeta),
    con respaldo del SKILL.md fuera del cerebro; si una fijada se renombra, sigue fijada. Si algo falla, queda
    como estaba."""
    from localhost_web import _frontmatter_skill
    import skill_meta
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    if not isinstance(nuevo, str) or not _SKILL_NUEVO.match(nuevo):
        return _mal("localhost.err.skill_nombre")
    import front_vivo
    oc = front_vivo.ocupado_skill(agente, skill)          # la que corre no cambia de carpeta (pedido del socio)
    if oc:
        return oc
    cerebro = _cerebros().get(agente)
    raiz = os.path.join(os.path.realpath(cerebro), "skills") if cerebro else ""
    if not raiz or not os.path.isdir(raiz):
        return _mal("localhost.err.archivo", 404)

    def nombres_ahora():
        return {_frontmatter_skill(os.path.join(x, "SKILL.md")).get("name") or os.path.basename(x): x
                for x in skill_meta.iter_skill_dirs(raiz)}
    with _LOCK:
        nombres = nombres_ahora()
        d = nombres.get(skill)
        if not d or not os.path.realpath(d).startswith(raiz + os.sep):
            return _mal("localhost.err.archivo", 404)
        if nuevo == skill:
            return {"ok": True, "nombre": nuevo}
        destino = os.path.join(os.path.dirname(d), nuevo)
        if nuevo in nombres or os.path.exists(destino):
            return _mal("localhost.err.skill_choca", 409)
        md = os.path.join(d, "SKILL.md")
        try:
            antes = _leer(md) or ""
        except (_Grande, _Ilegible):
            return _mal("localhost.err.archivo", 422)
        fin = antes.find("\n---", 3) if antes.startswith("---") else -1
        if fin < 0:                                   # sin encabezado: se le pone uno con su nombre
            texto = "---\nname: %s\n---\n\n%s" % (nuevo, antes)
        elif re.search(r"(?m)^name:", antes[:fin]):
            texto = re.sub(r"(?m)^name:.*$", "name: " + nuevo, antes[:fin], count=1) + antes[fin:]
        else:
            texto = antes[:fin] + "\nname: " + nuevo + antes[fin:]
        rel = os.path.relpath(md, os.path.dirname(raiz)).replace(os.sep, "/")
        if not _respaldar(agente, rel, antes):
            return _mal("localhost.err.guardar", 500)
        # justo antes de mover se vuelve a verificar: entre medio pasaron la lectura y el respaldo, y el candado
        # no cubre el sync ni un editor. mkdir falla si la carpeta ya está (os.rename sustituía una vacía).
        if nuevo in nombres_ahora():
            return _mal("localhost.err.skill_choca", 409)
        try:
            os.mkdir(destino)
        except FileExistsError:
            return _mal("localhost.err.skill_choca", 409)
        except OSError:
            return _mal("localhost.err.guardar", 500)
        movidos = []
        try:
            for x in os.listdir(d):
                os.rename(os.path.join(d, x), os.path.join(destino, x))
                movidos.append(x)
            os.rmdir(d)
        except OSError:
            _devolver(destino, d, movidos)
            return _mal("localhost.err.guardar", 500)
        if not _escribir_atomico(os.path.join(destino, "SKILL.md"), texto):
            _devolver(destino, d, movidos)        # sin su name: nuevo la carpeta nueva no sirve: se deshace
            return _mal("localhost.err.guardar", 500)
        fijas = _prefs_de(leer_prefs(), agente).get("fijas") or []
        if skill in fijas:
            _cambiar_prefs(agente, fijas=[nuevo if f == skill else f for f in fijas])
    return {"ok": True, "nombre": nuevo}


# ── pendientes (STATE/PENDIENTES.md) ─────────────────────────────────────────
# Dos formatos reales: casillas (`- [ ] algo`) y títulos con estado (`### ⏳ Algo` / `### ✅ Algo`).
# Dos modos: si el cerebro ordena su STATE por inbox (tiene STATE/inbox/), la página NO toca el archivo canónico:
# AGREGA el cambio al final del inbox del socio y lo recuerda aquí hasta que el consolidador lo aplique.
RUTA_PEND = "STATE/PENDIENTES.md"
_CASILLA = re.compile(r"^\s*[-*] \[( |x|X)\] (.+?)\s*$")
_TITULO = re.compile(r"^#{2,4}\s*(⏳|✅|⏸️|⏸|☑️|✔️)\s*(.+?)\s*$")
_DETALLE = re.compile(r"^\s*[-*]?\s*(👤|📅)\s*(?:[A-Za-zÁÉÍÓÚáéíóúñ ]+:\s*)?(.+?)\s*$")
POR_APLICAR_DIAS = 7


def _limpio_md(t):
    return re.sub(r"[*`]", "", t).strip()


def _clave(t):
    return re.sub(r"\s+", " ", _limpio_md(t).lower())


def _pid(t, n=0):
    """Id estable: el texto y, si se repite, cuál de los repetidos es."""
    return hashlib.sha1(("%s|%d" % (_clave(t), n)).encode("utf-8")).hexdigest()[:12]


def _items(texto):
    out, actual, vistos = [], None, {}

    def nuevo_id(t):
        k = _clave(t)
        n = vistos.get(k, 0)
        vistos[k] = n + 1
        return _pid(t, n)

    for i, l in enumerate((texto or "").split("\n")):
        m = _CASILLA.match(l)
        if m:
            out.append({"id": nuevo_id(m.group(2)), "texto": _limpio_md(m.group(2)), "hecho": m.group(1) != " ",
                        "pausa": False, "linea": i, "tipo": "casilla"})
            actual = None
            continue
        m = _TITULO.match(l)
        if m:
            actual = {"id": nuevo_id(m.group(2)), "texto": _limpio_md(m.group(2)), "hecho": m.group(1) in ("✅", "☑️", "✔️"),
                      "pausa": m.group(1).startswith("⏸"), "linea": i, "tipo": "titulo"}
            out.append(actual)
            continue
        if l.startswith("#"):
            actual = None
            continue
        m = _DETALLE.match(l)
        if actual and m:
            actual["quien" if m.group(1) == "👤" else "fecha"] = _limpio_md(m.group(2))[:80]
    return out


def _modo(cerebro):
    return "inbox" if os.path.isdir(os.path.join(cerebro, "STATE", "inbox")) else "directo"


def _socio(cerebro):
    """El MISMO socio que usan las pestañas y los hooks (brain_write), para escribir en SU inbox."""
    try:
        import brain_write
        return brain_write._socio(cerebro) or "equipo"
    except Exception:
        return "equipo"


def _vigentes(p):
    vence = time.time() - POR_APLICAR_DIAS * 86400
    marcados = {k: v for k, v in (p.get("por_aplicar") or {}).items() if isinstance(v, dict) and v.get("ts", 0) > vence}
    nuevos = [n for n in (p.get("nuevos") or []) if isinstance(n, dict) and n.get("ts", 0) > vence and isinstance(n.get("texto"), str)]
    return marcados, nuevos


TAB_NAV = "Navegador"                      # la conversación de la página
_ID_CONV = re.compile(r"^P-\d{1,6}$")


def _de_la_conversacion(cerebro):
    """Los pendientes que el agente anotó en la memoria de su conversación de la página («workspace memoria nota
    --tipo pendiente»: P-n, abiertos en Vigente). La página no los enseñaba: había dos «pendientes» y solo veía el
    del archivo (C3-2). Se enseñan los dos juntos, cada uno con su origen (`tipo`)."""
    import memoria
    try:
        ficha = memoria.Ficha(memoria._leer_vista(memoria.ficha_path(cerebro, TAB_NAV)))
        return [{"id": v["id"], "texto": _limpio_md(v.get("texto") or ""), "hecho": False, "pausa": False, "tipo": "conversacion",
                 "fecha": v.get("fecha") or ""} for v in memoria.vigente(ficha)
                if v.get("tipo") == "pendiente" and _ID_CONV.match(str(v.get("id") or ""))]
    except Exception:
        return []


def pendientes_todos():
    """«De todos»: los abiertos de cada agente, para cruzarlos."""
    out = []
    for a in _snapshot():
        d = pendientes(a.get("id"))
        if d.get("ok"):
            out.append({"agente": a.get("id"), "items": [i for i in d["items"] if not i["hecho"] and not i.get("pausa")][:30]})
    return {"ok": True, "agentes": out}


def pendientes(agente):
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    cerebro, dest = _ruta_en_cerebro(agente, RUTA_PEND)
    if not dest:
        return _mal("localhost.err.agente", 404)
    try:
        texto = _leer(dest)
    except _Grande:
        return _mal("localhost.err.archivo_largo", 413)
    except _Ilegible:
        return _mal("localhost.err.archivo", 422)
    items, modo = _items(texto), _modo(cerebro)
    if modo == "inbox":
        with _LOCK:
            p = _prefs_de(leer_prefs(), agente)
            marcados, nuevos = _vigentes(p)
            ya = {it["id"] for it in items}
            for n in nuevos:
                nid = _pid(n["texto"])
                if nid not in ya:
                    items.append({"id": nid, "texto": n["texto"], "hecho": False, "pausa": False, "tipo": "nuevo"})
            for it in items:
                m = marcados.get(it["id"])
                if not m:
                    if it["tipo"] == "nuevo":
                        it["por_aplicar"] = True
                    continue
                if bool(m.get("hecho")) == it["hecho"] and it["tipo"] != "nuevo":
                    marcados.pop(it["id"])          # el consolidador ya lo aplicó: la marca deja de mandar
                else:
                    it["hecho"], it["por_aplicar"] = bool(m.get("hecho")), True
            nuevos = [n for n in nuevos if _pid(n["texto"]) not in {i["id"] for i in items if i["tipo"] != "nuevo"}]
            if marcados != (p.get("por_aplicar") or {}) or len(nuevos) != len(p.get("nuevos") or []):
                _cambiar_prefs(agente, por_aplicar=marcados or None, nuevos=nuevos or None)
    return {"ok": True, "modo": modo, "existe": texto is not None, "items": items + _de_la_conversacion(cerebro),
            "firma": _firma(texto)}


def _al_inbox(cerebro, lineas):
    """AGREGA al final del inbox del socio (una sola escritura que no se pisa con las de los hooks o el agente)."""
    try:
        import atomico
        carpeta = os.path.realpath(os.path.join(cerebro, "STATE", "inbox"))
        if not carpeta.startswith(cerebro + os.sep):
            return False                            # un inbox que apunta fuera del cerebro no se toca
        dest = os.path.join(carpeta, "%s-%s.md" % (_socio(cerebro), time.strftime("%Y-%m-%d")))
        if os.path.islink(dest) or (os.path.exists(dest) and not os.path.realpath(dest).startswith(carpeta + os.sep)):
            return False
        bloque = "\n## %s · página de Workspace · pendientes\n%s\n" % (time.strftime("%Y-%m-%d"), "\n".join("- " + x for x in lineas))
        atomico.anexar(dest, bloque)
        return True
    except Exception:
        return False


def pendiente(agente, accion, id=None, hecho=None, texto=None):
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    if accion == "marcar" and isinstance(id, str) and _ID_CONV.match(id):
        # uno de su conversación (C3-2): se cierra por la única puerta de esa memoria (guardar_nota con «cierra»)
        if hecho is not True:
            return _mal("localhost.err.formato")
        import memoria
        try:
            memoria.guardar_nota(_cerebros().get(agente), TAB_NAV, "hecho (desde la página)", tipo="hecho", cierra=(id,))
        except Exception:
            return _mal("localhost.err.guardar", 500)
        return pendientes(agente)
    if accion not in ("marcar", "agregar"):
        return _mal("localhost.err.formato")
    cerebro, dest = _ruta_en_cerebro(agente, RUTA_PEND)
    if not dest:
        return _mal("localhost.err.agente", 404)
    t = (texto or "").strip()
    if accion == "agregar":
        if not _renglon_ok(t, 300):
            return _mal("localhost.err.formato")
        if _secreto(t):
            return _mal("localhost.err.llave")
    elif type(hecho) is not bool or not isinstance(id, str):
        return _mal("localhost.err.formato")
    with _LOCK:
        try:
            actual = _leer(dest)
        except _Grande:
            return _mal("localhost.err.archivo_largo", 413)
        except _Ilegible:
            return _mal("localhost.err.archivo", 422)
        items = _items(actual)
        it = next((x for x in items if x["id"] == id), None) if accion == "marcar" else None
        if _modo(cerebro) == "inbox":
            p = _prefs_de(leer_prefs(), agente)
            marcados, nuevos = _vigentes(p)
            if accion == "agregar":
                if not _al_inbox(cerebro, ["Pendiente nuevo: «%s» (lo agregó el socio en la página)." % t]):
                    return _mal("localhost.err.guardar", 500)
                nuevos = (nuevos + [{"texto": t, "ts": time.time()}])[-50:]
                ok = _cambiar_prefs(agente, nuevos=nuevos)
            else:
                nuevo = next((n for n in nuevos if _pid(n["texto"]) == id), None)
                if not it and not nuevo:
                    return _mal("localhost.err.archivo_cambio", 409)
                nombre_p = it["texto"] if it else nuevo["texto"]
                linea = ("Pendiente resuelto: «%s» (lo marcó el socio en la página)." if hecho
                         else "Pendiente reabierto: «%s» (lo desmarcó el socio en la página).") % nombre_p
                if not _al_inbox(cerebro, [linea]):
                    return _mal("localhost.err.guardar", 500)
                marcados[id] = {"hecho": hecho, "ts": time.time()}
                ok = _cambiar_prefs(agente, por_aplicar=marcados)
            if not ok:
                return _mal("localhost.err.guardar", 500)
            r = pendientes(agente)
            r["inbox"] = True
            return r
        # modo directo: el archivo es suyo; respaldo y escritura atómica, conservando sus fines de línea
        if accion == "agregar":
            fin = "\r\n" if actual and "\r\n" in actual else "\n"
            nuevo_txt = ("# Pendientes" + fin + fin if actual is None else actual.rstrip("\r\n") + fin) + "- [ ] " + t + fin
        else:
            if not it:
                return _mal("localhost.err.archivo_cambio", 409)
            lineas = actual.split("\n")
            l = lineas[it["linea"]]
            if it["tipo"] == "casilla":
                lineas[it["linea"]] = re.sub(r"\[( |x|X)\]", "[x]" if hecho else "[ ]", l, count=1)
            else:
                lineas[it["linea"]] = re.sub(r"(⏳|✅|⏸️|⏸|☑️|✔️)", "✅" if hecho else "⏳", l, count=1)
            nuevo_txt = "\n".join(lineas)
        if len(nuevo_txt) > MAX_ARCHIVO:
            return _mal("localhost.err.archivo_largo", 413)
        if not _respaldar(agente, RUTA_PEND, actual) or not _escribir_atomico(dest, nuevo_txt):
            return _mal("localhost.err.guardar", 500)
    return pendientes(agente)


# ── uso del motor que no sale de la pantalla ─────────────────────────────────
def uso(agente):
    """Instantánea de usage.json (la escribe la barra de estado de Claude Code); solo si su motor es Claude Code.
    Si no es reciente va con su edad (la página dice «actualizado hace…»). Solo los límites de la CUENTA (ventana de 5 h y semana): el contexto de ese archivo es de la
    última sesión que lo escribió, no de este agente. Lo que ya se renovó no se enseña como si siguiera."""
    a = _agente_valido(agente)
    if not a:
        return _mal("localhost.err.agente", 404)
    motor = a.get("engine") or ""
    if motor != "claude-code":
        return {"ok": True, "motor": motor, "uso": None}
    try:
        with open(os.path.join(_paths.state_dir(), "usage.json"), encoding="utf-8") as f:
            u = json.load(f)
    except Exception:
        return {"ok": True, "motor": motor, "uso": None}
    if not isinstance(u, dict):
        return {"ok": True, "motor": motor, "uso": None}
    ahora = time.time()
    sello = u.get("stamped")
    try:
        edad = max(0, int(ahora - float(sello)))
    except (TypeError, ValueError):
        return {"ok": True, "motor": motor, "uso": None}

    def falta(k):
        try:
            return float(u.get(k)) - ahora
        except (TypeError, ValueError):
            return None

    def pct(k, reinicio):
        v = u.get(k)
        f = falta(reinicio)
        if not isinstance(v, (int, float)) or (f is not None and f <= 0):
            return None                              # ya se renovó: ese porcentaje ya no es de ahora
        return round(float(v))

    def texto(reinicio):
        f = falta(reinicio)
        if f is None or f <= 0:
            return None
        h, m = int(f // 3600), int(f % 3600 // 60)
        return ("%dd %dh" % (h // 24, h % 24)) if h >= 24 else ("%dh %dm" % (h, m) if h else "%dm" % m)

    return {"ok": True, "motor": motor, "uso": {
        "sesion": pct("five_hour_pct", "five_hour_resets_at"), "semana": pct("seven_day_pct", "seven_day_resets_at"),
        "reinicia": texto("five_hour_resets_at"), "reinicia_semana": texto("seven_day_resets_at"), "sello": sello,
        "edad": edad, "viejo": edad > USO_VIEJO_S}}      # viejo = se enseña con «actualizado hace…», no se esconde


# ── abrir un archivo que el agente entregó (la tarjeta del menú de archivo y la de mostrar_archivo) ───
def _lanzar(cmd):
    import subprocess
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True, start_new_session=(os.name != "nt"))


#: Lo que el sistema CORRE al abrirlo (no lo enseña): un programa, un script que abre la terminal, un instalador o un
#: acceso que apunta a otro. «Abrir» de uno de estos lo enseña en su carpeta: el agente lo escribe en su cerebro (dentro
#: de su sandbox) y un clic del socio no lo corre fuera de él.
EJECUTABLES = frozenset((
    ".app", ".command", ".tool", ".terminal", ".sh", ".bash", ".zsh", ".csh", ".ksh", ".fish", ".py", ".pyw", ".pl",
    ".rb", ".php", ".jar", ".pkg", ".mpkg", ".dmg", ".workflow", ".action", ".scpt", ".scptd", ".applescript",
    ".fileloc", ".webloc", ".inetloc", ".url", ".desktop", ".exe", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs",
    ".vbe", ".js", ".jse", ".wsf", ".wsh", ".msi", ".msp", ".lnk", ".scr", ".hta", ".reg", ".cpl", ".appimage", ".run"))


def _ejecutable(dest):
    """¿Abrirlo lo correría? Por su tipo, o un archivo con permiso de ejecución y sin extensión (macOS lo corre en la
    terminal)."""
    ext = os.path.splitext(dest.rstrip("/\\"))[1].lower()
    if ext in EJECUTABLES:
        return True
    return not ext and os.path.isfile(dest) and os.name != "nt" and os.access(dest, os.X_OK)


def abrir(agente, ruta, modo="abrir"):
    """Abre (o enseña en su carpeta) un archivo, SOLO si vive dentro del cerebro de ese agente. Sin shell. Uno que se
    correría al abrirlo (EJECUTABLES) se enseña en su carpeta: → {"ok": True, "revelado": True}."""
    if not _agente_valido(agente):
        return _mal("localhost.err.agente", 404)
    if modo not in ("abrir", "revelar") or not _renglon_ok(ruta, 1000):
        return _mal("localhost.err.formato")
    cerebro = _cerebros().get(agente)
    if not cerebro:
        return _mal("localhost.err.agente", 404)
    base = os.path.realpath(cerebro)
    dest = os.path.realpath(ruta if os.path.isabs(ruta) else os.path.join(base, ruta))
    if not dest.startswith(base + os.sep) or not os.path.exists(dest):
        return _mal("localhost.err.archivo", 404)
    revelado = modo == "abrir" and _ejecutable(dest)
    if revelado:
        modo = "revelar"
    try:
        import sys
        if sys.platform == "darwin":
            _lanzar(["open", "-R", dest] if modo == "revelar" else ["open", dest])
        elif os.name == "nt":
            if modo == "revelar":
                _lanzar(["explorer", "/select,", dest])
            else:
                os.startfile(dest)            # noqa: abre con su programa
        else:
            _lanzar(["xdg-open", os.path.dirname(dest) if modo == "revelar" else dest])
    except Exception:
        return _mal("localhost.err.archivo", 500)
    return {"ok": True, "revelado": True} if revelado else {"ok": True}


# ── crear un agente desde la página (pedido del socio, ronda 2) ──────────────────
# El MISMO job del hub («Agregar agente»): agent_create_job.start → agent_admin.create con su progress y su
# should_cancel. La página solo pone el formulario corto y pinta los pasos.
MAX_AYUDA = 600


def _job_vista(job):
    from pantalla_motor import _limpio
    if not job:
        return None
    casa = os.path.expanduser("~")
    donde = job.get("dest") or ""
    vista = {"nombre": job.get("name"), "pasos": [{"key": s["key"], "label": s["label"], "st": s["st"], "note": _limpio(s.get("note"), 160)}
                                                for s in job.get("steps") or []],
             "done": bool(job.get("done")), "ok": bool(job.get("ok")), "error": _limpio(job.get("error"), 300),
             "cancel": bool(job.get("cancel")),
             "donde": ("~" + donde[len(casa):]) if donde.startswith(casa) else donde}
    if job.get("steps"):                              # las 4 frases para la persona (las mismas de la tarjeta del hub)
        import agregar_logica
        vista["humanos"] = [{"texto": t, "st": st} for t, st in agregar_logica.pasos_humanos(job, job.get("engine"))]
    return vista


def crear_agente(nombre, ayuda="", forma=None, color=None, motor="", visible="", como_habla="", que_si_no="",
                 sobre_ti="", autonomia=True, revisar_skills=False):
    """La tarjeta «Agregar agente» (la del hub y la ventana de la página) → el job oficial. `nombre`: su comando;
    `visible`: como se escribió; `ayuda`: para qué; «A tu medida»: cómo habla, qué sí y qué no, sobre ti y sus dos
    interruptores. Fallas con salida (cada una con su clave): nombre inválido o repetido, carpeta que ya existe, otra
    creación en curso. Un motor sin sesión NO bloquea (advisor, AG2): el agente nace y se dice `sin_sesion` para que
    la tarjeta ofrezca entrar a su cuenta."""
    import agent_admin
    import agent_create_job
    import agent_create_params
    import agentsreg
    nombre = (nombre or "").strip().lower()
    if not agentsreg.is_valid_name(nombre):
        return _mal("localhost.err.crear_nombre")
    if nombre in _cerebros() or agentsreg.find(nombre):
        return _mal("localhost.err.crear_existe", 409)
    textos = (ayuda, como_habla, que_si_no, sobre_ti)
    if any(not isinstance(t, str) or len(t) > MAX_AYUDA or _secreto(t) for t in textos) \
            or not isinstance(visible, str) or (visible and not _renglon_ok(visible, 40)) \
            or (forma is not None and forma not in FORMAS) or (color is not None and color not in COLORES):
        return _mal("localhost.err.formato")
    destino = agent_admin.default_brain_dest(nombre)
    if os.path.exists(destino):
        return dict(_mal("localhost.err.crear_carpeta", 409), datos={"r": _job_vista({"dest": destino})["donde"]})
    motor = motor or "claude-code"
    try:
        import motores_logica
        if motor not in motores_logica.SUPPORTED:
            return _mal("localhost.err.formato")
        sin_sesion = motores_logica._probe(motor) is not True
    except ImportError:
        return _mal("localhost.err.leer", 500)
    actual = agent_create_job.active()
    if actual and not actual.get("done"):
        return _mal("localhost.err.crear_en_curso", 409)
    try:
        import agregar_logica
        dueno = agregar_logica.persona()
    except Exception:
        dueno = ""
    params = agent_create_params.desde_tarjeta(nombre, visible.strip(), ayuda, como_habla, que_si_no, sobre_ti,
                                               motor=motor, autonomia=bool(autonomia),
                                               revisar_skills=bool(revisar_skills), dueno=dueno)
    if forma or color:
        _cambiar_prefs(nombre, avatar={k: v for k, v in (("forma", forma), ("color", color)) if v})
    return {"ok": True, "job": _job_vista(agent_create_job.start(params)), "sin_sesion": bool(sin_sesion),
            "motor": motor}


def crear_estado():
    import agent_create_job
    return {"ok": True, "job": _job_vista(agent_create_job.active())}


# ── archivar un agente o quitarlo de Workspace (agente_apartar): lo mismo que el hub ──
def _apartado(r):
    """El resultado de agente_apartar, como lo espera la página: su aviso de una línea y a quién deshacer."""
    if not isinstance(r, dict) or not r.get("ok"):
        return {"ok": False, "error": str((r or {}).get("error") or "localhost.err.guardar"), "status": 409}
    return {"ok": True, "aviso": r.get("msg") or "", "deshacer": r.get("deshacer") or "",
            "carpeta": r.get("donde") or ""}


def apartados(agente="", hablando=""):
    """Los archivados (para traerlos de vuelta) y, de `agente`, lo que conviene saber antes de archivarlo o quitarlo
    y dónde se queda su carpeta. `hablando` = "1" si la página tiene su conversación abierta."""
    import agente_apartar as AP
    out = {"ok": True, "avisos": [], "carpeta": "",
           "archivados": [{"nombre": x["name"], "visible": x["display"], "carpeta": AP.ruta_corta(x["brain"]),
                           "existe": bool(x["existe"])} for x in AP.archivados()]}
    if agente:
        a = _agente_valido(agente)
        if not a:
            return _mal("localhost.err.agente", 404)
        out["avisos"] = [x["texto"] for x in AP.avisos(a["name"], actual=a["name"] if hablando == "1" else "")]
        out["carpeta"] = AP.ruta_corta(a.get("brain") or "")
    return out


def archivar_agente(agente):
    """«Archivar»: sale de las listas; su carpeta y sus sesiones se quedan (vuelve desde «Archivados»)."""
    a = _agente_valido(agente)
    if not a:
        return _mal("localhost.err.agente", 404)
    import agente_apartar as AP
    return _apartado(AP.archivar(a["name"], expected_brain=a.get("brain") or None))


def quitar_agente(agente):
    """«Quitar de Workspace»: lo desregistra en esta computadora; su carpeta nunca se borra."""
    a = _agente_valido(agente)
    if not a:
        return _mal("localhost.err.agente", 404)
    import agente_apartar as AP
    return _apartado(AP.quitar(a["name"], expected_brain=a.get("brain") or None))


def volver_agente(nombre):
    """«Traer de vuelta» a un archivado y el «Deshacer» de archivar y de quitar."""
    if not isinstance(nombre, str) or not SLUG_RE.match(nombre):
        return _mal("localhost.err.agente", 404)
    import agente_apartar as AP
    r = AP.volver(nombre)
    if not r.get("ok"):
        return {"ok": False, "error": str(r.get("error") or "localhost.err.guardar"), "status": 409}
    return {"ok": True, "aviso": r.get("msg") or "", "agente": r.get("nombre") or nombre}


def crear_cancelar():
    import agent_create_job
    agent_create_job.cancel()
    return {"ok": True}


def crear_visto():
    import agent_create_job
    agent_create_job.ack()
    return {"ok": True}


# ── «Ya tengo un agente» desde la página (AG8-b): lo que encontré, una carpeta pegada y conectarlo ──────────────
#: Lo último que encontró «buscar» (la página elige por su número: no le mandamos rutas del disco).
_ENCONTRADOS = []
MAX_CARGAR = 20


def buscar_agentes(protegidas=False):
    """Los cerebros de esta computadora con su monito y su estado (agregar_logica.encontrados). En Mac, Escritorio,
    Documentos y Descargas solo con `protegidas` (cada una abre un permiso de macOS)."""
    import agregar_logica
    r = agregar_logica.encontrados(protegidas=bool(protegidas))
    with _LOCK:
        _ENCONTRADOS[:] = r["encontrados"]
    return {"ok": True, "protegidas": r["protegidas"], "mac": r["mac"],
            "avisos": [_limpio_corto(a, 200) for a in r["avisos"]][:10],
            "encontrados": [{"i": i, "nombre": e["nombre"], "visible": _limpio_corto(e["visible"], 40),
                             "corta": _limpio_corto(e["corta"], 160), "estado": e["estado"], "forma": e["forma"],
                             "color": e["color"], "motor": e["motor"]}
                            for i, e in enumerate(r["encontrados"][:200])]}


def _limpio_corto(t, n):
    from texto_pagina import _limpio
    return _limpio(t, n)


def carpeta(ruta):
    """Qué hay en la carpeta que pegaste o arrastraste, en simple, antes de conectar (solo lee)."""
    import agregar_logica
    if not isinstance(ruta, str) or len(ruta) > 1000:
        return _mal("localhost.err.formato")
    info = agregar_logica.radiografia(ruta)
    return {"ok": True, "veredicto": info.get("veredicto"), "texto": _limpio_corto(agregar_logica.texto_radiografia(
        info), 300), "nombre": info.get("name") or "", "visible": _limpio_corto(
        info.get("display") or (info.get("name") or "").capitalize(), 40), "libre": info.get("libre") or "",
        "adentro": agregar_logica.ruta_corta(info.get("adentro") or "")}


def cargar_agente(indices=None, ruta="", carpetas=None, nombres=None, autonomia=None, revisar_skills=None):
    """Conecta cerebros que ya existen con el job de cargar (agent_load_job): por su número en lo último que encontró
    `buscar_agentes` (la página), una carpeta pegada (`ruta`) o carpetas con su nombre (el hub). Un nombre que ya
    tiene otro agente se conecta con uno libre; la carpeta jamás se renombra."""
    import agregar_logica
    import agent_load_job
    items = []
    if indices is not None:
        if not isinstance(indices, list) or len(indices) > MAX_CARGAR or \
                not all(isinstance(i, int) and not isinstance(i, bool) for i in indices):
            return _mal("localhost.err.formato")
        with _LOCK:
            lista = list(_ENCONTRADOS)
        for i in indices:
            if not 0 <= i < len(lista):
                return _mal("localhost.err.formato")
            e = lista[i]
            if e["estado"] in ("cargado", "incompleto"):
                continue
            items.append((e["nombre"] if e["estado"] == "nuevo" else (agregar_logica.libre(e["nombre"]) or
                                                                      e["nombre"]), e["carpeta"]))
    elif ruta:
        if not isinstance(ruta, str) or len(ruta) > 1000:
            return _mal("localhost.err.formato")
        info = agregar_logica.radiografia(ruta)
        v = info.get("veredicto")
        if v not in ("agente", "choque"):
            return dict(_mal("localhost.err.cargar_carpeta", 409), datos={"t": agregar_logica.texto_radiografia(info)})
        items.append((info.get("name") if v == "agente" else (info.get("libre") or info.get("name")),
                      info["folder"]))
    elif carpetas is not None:
        nombres = nombres if isinstance(nombres, list) else []
        if not isinstance(carpetas, list) or len(carpetas) > MAX_CARGAR or \
                not all(isinstance(c, str) and 0 < len(c) <= 1000 for c in carpetas) or \
                not all(isinstance(n, str) and len(n) <= 40 for n in nombres):
            return _mal("localhost.err.formato")
        import agentsreg
        for k, c in enumerate(carpetas):
            n = nombres[k] if k < len(nombres) else ""
            if n and not agentsreg.is_valid_name(n):
                return _mal("localhost.err.formato")
            items.append((n, c))
    if not items:
        return _mal("localhost.err.cargar_nada", 409)
    prefs = {}
    if isinstance(autonomia, bool):
        prefs["autonomy"] = "brain" if autonomia else "ask"
    if isinstance(revisar_skills, bool):
        prefs["skill_review"] = revisar_skills
    return agent_load_job.iniciar(items, prefs or None)


def cargar_estado():
    """El job de conectar: sus pasos en las 4 frases de crear (M1) y, al terminar, si a su motor le falta tu sesión
    (M2: lo mismo que dice crear, no «despierta»)."""
    import agent_load_job
    job = agent_load_job.active()
    vista = agent_load_job.vista(job)
    if vista and len(job.get("items") or ()) == 1:
        import agregar_logica
        import agentsreg
        try:
            motor = str((agentsreg.load_definition(job["items"][0][1]) or {}).get("engine") or "")
        except Exception:
            motor = ""
        vista["humanos"] = [{"texto": t, "st": st} for t, st in agregar_logica.pasos_humanos(vista, motor, cargar=True)]
        if vista.get("done") and vista.get("ok") and motor:
            vista["sin_sesion"] = agregar_logica.falta_su_sesion(motor) is True
            vista["motor"] = agregar_logica.nombre_motor(motor)
    return {"ok": True, "job": vista}


def cargar_visto():
    import agent_load_job
    agent_load_job.ack()
    return {"ok": True}


def textos_agregar():
    """Los textos de «Agregar agente» en el idioma de Workspace (lang/*/agregar.py): la ventana de la página los usa
    con su clave, como la tarjeta del hub."""
    try:
        import agregar_logica
        import importlib
        es = importlib.import_module("lang.es.agregar").STRINGS
        # en el idioma de la tarjeta (AG3-a: la página y el hub, en español para todos en la v1)
        return {"ok": True, "textos": {k: agregar_logica._t(k) for k in es}}
    except Exception:
        return {"ok": True, "textos": {}}
