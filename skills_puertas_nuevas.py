"""WORKSPACE · skills_puertas_nuevas — las skills de la guía que ya están en un cerebro mandan a las pantallas nuevas.

Las cuatro skills de la guía (configurar-workspace, personalizar-workspace, reparar-workspace y calendario-y-tareas)
llegaron a los cerebros en la 0.9.2 (skills_de_plantilla) o al crear un agente. Decían «Motores → cuenta y
proveedor», «Personalización», `workspace bienvenida` o «el calendario es la pantalla»: pantallas de antes que ya no
existen. La plantilla nueva (1.1.0) manda a las del hub. Una copia que ya está en un cerebro la recibe aquí, por las
tres puertas de siempre (la migración 202611221218, cargar un agente y `workspace doctor --fix`), como
skills_a_la_vista:

  · Solo si la copia es, byte por byte, una versión anterior de la plantilla con sus marcadores llenos
    (migrations/data/skills_puertas_nuevas.json, que gen_skills_puertas_nuevas.py genera del historial; los
    marcadores {{X}} son comodín, con el mismo valor en cada aparición). La nueva lleva esos mismos valores (el nombre,
    la cara y la fecha de la copia). Una copia que el socio o su agente editaron, aunque sea una letra, no se toca.
    LF o CRLF: la nueva sale con los finales de la copia.
  · Antes de escribir, una copia exacta en `<estado>/backups/<MID>/<agente>-<hash>/skills/meta/<skill>/SKILL.md`; sin
    copia no se toca.
  · Si el archivo cambió mientras tanto (una edición, un sync), no se toca ni se sella: la próxima puerta reintenta.
  · Se entrega UNA vez por cerebro: deja `.workspace/skills-puertas-nuevas.json`. Lo que el socio cambie después no
    se vuelve a tocar.
  · El mismo candado del cerebro que sin_aprobacion, skills_de_plantilla y skills_a_la_vista.

Determinista y sin rutas de esta máquina: dos equipos que sincronizan el cerebro escriben los mismos bytes.
"""
import json
import os
import re

import skills_de_plantilla as SP

ROOT = os.path.dirname(os.path.abspath(__file__))
MID = "202611221218_skills_puertas_nuevas"
SELLO = ".workspace/skills-puertas-nuevas.json"
DATOS = os.path.join("migrations", "data", "skills_puertas_nuevas.json")
RELS = (
    "skills/meta/configurar-workspace/SKILL.md",
    "skills/meta/personalizar-workspace/SKILL.md",
    "skills/meta/reparar-workspace/SKILL.md",
    "skills/meta/calendario-y-tareas/SKILL.md",
)
SLUGS = tuple(rel.split("/")[2] for rel in RELS)
_MARCA = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
_versiones_cache, _patrones = {}, {}


def _versiones(root):
    """{rel: [textos de versiones anteriores, con sus marcadores]} (vacío si el JSON no se lee: entonces nada se toca)."""
    path = os.path.join(root, DATOS)
    if path not in _versiones_cache:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh).get("skills") or {}
            _versiones_cache[path] = {rel: [t.replace("\r\n", "\n") for t in data.get(rel) or ()
                                            if isinstance(t, str) and t] for rel in RELS}
        except (OSError, ValueError, AttributeError):
            _versiones_cache[path] = {}
    return _versiones_cache[path]


def _patron(plantilla):
    """La plantilla como expresión: lo literal, tal cual; cada marcador, un comodín de una línea (la misma en todas sus
    apariciones)."""
    if plantilla in _patrones:
        return _patrones[plantilla]
    partes, vistos, pos = [], set(), 0
    for m in _MARCA.finditer(plantilla):
        partes.append(re.escape(plantilla[pos:m.start()]))
        k = m.group(1)
        partes.append("(?P=%s)" % k if k in vistos else "(?P<%s>[^\r\n]*?)" % k)
        vistos.add(k)
        pos = m.end()
    partes.append(re.escape(plantilla[pos:]))
    _patrones[plantilla] = re.compile("".join(partes))
    return _patrones[plantilla]


def _valores(texto, viejas):
    """Los valores de los marcadores si `texto` es una de las versiones `viejas` llena; None si no es ninguna."""
    for v in viejas:
        m = _patron(v).fullmatch(texto)
        if m:
            return m.groupdict()
    return None


def _rellenar(plantilla, valores):
    """La plantilla con esos valores, en una pasada (un valor que trae «{{X}}» no se vuelve a llenar). None si le falta
    uno."""
    faltan = [k for k in _MARCA.findall(plantilla) if k not in valores]
    if faltan:
        return None
    return _MARCA.sub(lambda m: valores[m.group(1)], plantilla)


def _nueva(root, rel):
    try:
        with open(os.path.join(root, "templates", "agent", "brain", *rel.split("/")), encoding="utf-8",
                  newline="") as fh:
            return fh.read().replace("\r\n", "\n")         # un checkout con CRLF (Windows) no cambia lo que se escribe
    except (OSError, UnicodeDecodeError):
        return None


def _estado_sello(brain):
    """"falta" | "ok" | "ilegible" (vacío, JSON roto, carpeta o enlace: no es un sello)."""
    return SP._estado_sello(brain, SELLO)


def _aplica(brain, root):
    if not brain or not os.path.isdir(brain) or os.path.islink(brain) or SP._dentro(brain, root):
        return False
    return any(os.path.isfile(os.path.join(brain, *rel.split("/"))) for rel in RELS)


def _a_medias(brain):
    """¿`.workspace/` del cerebro está a medias (un sync)? Su agent.json o el sello de la guía no se leen: entonces no
    se toca nada (queda pendiente), como skills_de_plantilla."""
    return SP._agente(brain)[1] == "ilegible" or SP._estado_sello(brain) == "ilegible"


def _plan(brain, rel, root):
    """(bytes leídos, bytes nuevos) si esa copia es una versión anterior intacta; None si no (no existe, enlace, no se
    lee como UTF-8, finales de línea mezclados, editada, o ya es la actual)."""
    if SP._pasa_por_enlace(brain, rel):
        return None
    leido = SP._texto_utf8(os.path.join(brain, *rel.split("/")))
    if leido is None:
        return None
    crudo, texto = leido
    nl = "\n"
    if "\r\n" in texto:
        if "\n" in texto.replace("\r\n", "") or "\r" in texto.replace("\r\n", ""):
            return None                                   # mezclados: alguien la tocó
        nl, texto = "\r\n", texto.replace("\r\n", "\n")
    viejas = _versiones(root).get(rel) or ()
    nueva = _nueva(root, rel)
    if not viejas or not nueva:
        return None
    valores = _valores(texto, viejas)
    if valores is None:
        return None
    hecho = _rellenar(nueva, valores)
    if hecho is None or hecho == texto:
        return None
    return crudo, hecho.replace("\n", nl).encode("utf-8")


def trabajos(brain, root=ROOT):
    """Las copias que todavía mandan a una pantalla de antes ([rel]). Vacío si no aplica, ya está al día o ya se
    entregó."""
    if not _aplica(brain, root) or _estado_sello(brain) != "falta" or _a_medias(brain):
        return []
    return [rel for rel in RELS if _plan(brain, rel, root) is not None]


def backup_dir(state_dir, brain, name=None):
    return SP.backup_dir(state_dir, brain, name, MID)


def _sellar(brain):
    SP._sellar(brain, SELLO, {"id": MID, "skills": list(SLUGS)})


def _escribir(brain, rel, respaldo, root, state_dir):
    """True si escribió; "cambio" si el archivo cambió mientras lo respaldaba; False si no hacía falta."""
    plan = _plan(brain, rel, root)
    if plan is None:
        return False
    crudo, nuevo = plan
    path = os.path.join(brain, *rel.split("/"))
    SP._respaldar(os.path.join(respaldo, *rel.split("/")), crudo)
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        with open(tmp, "wb") as fh:
            fh.write(nuevo)
        if SP._leer_bytes(path) != crudo:
            return "cambio"
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    try:                       # el «deshacer» del formato v2 lo reconoce como cambio de Workspace
        import brain_format
        brain_format.nota_cambio_de_workspace(brain, rel, crudo, nuevo, state_dir)
    except Exception:
        pass
    return True


def actualizar(brain, root=ROOT, state_dir=None, name=None, dry_run=False, log=None, timeout=30):
    """Pone al día las copias intactas (con respaldo) y sella el cerebro. → [rel] escritos. Levanta OSError si el
    respaldo no se pudo guardar (el archivo queda como estaba) y olock.LockTimeout si el candado no se libera."""
    if dry_run:
        return trabajos(brain, root)
    if not _aplica(brain, root):
        return []
    with SP.candado(brain, timeout):
        if _a_medias(brain):
            if log is not None:
                try:
                    log(".workspace/ de este cerebro no se puede leer entero (¿un sync a medias?): no puse al día las "
                        "skills de la guía; queda para la próxima pasada")
                except Exception:
                    pass
            return []
        estado = _estado_sello(brain)
        if estado != "falta":
            if estado == "ilegible" and log is not None:
                try:
                    log("%s no se puede leer (vacío, dañado, carpeta o enlace): no puse al día las skills de la guía. "
                        "Bórralo, o espera a que termine el sync" % SELLO)
                except Exception:
                    pass
            return []
        if state_dir is None:
            import paths
            state_dir = paths.state_dir()
        respaldo = backup_dir(state_dir, brain, name)
        hechos, pospuesto = [], False
        for rel in RELS:
            r = _escribir(brain, rel, respaldo, root, state_dir)
            if r == "cambio":
                pospuesto = True
                if log is not None:
                    try:
                        log("%s cambió mientras lo respaldaba (¿un sync en curso?): reintento en la próxima pasada"
                            % rel)
                    except Exception:
                        pass
            elif r:
                hechos.append(rel)
        if not pospuesto:
            _sellar(brain)
        return hechos
