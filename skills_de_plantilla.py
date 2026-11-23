"""WORKSPACE · skills_de_plantilla — las skills nuevas de la guía llegan a un cerebro que ya existe.

La plantilla las trae para un agente nuevo. Uno que ya estaba no vuelve a
crearse, así que esta función se las copia por las tres puertas de siempre
(la migración, cargar un agente y `workspace doctor`): solo si el archivo no
existe. Una skill que el usuario ya tiene, aunque sea distinta, no se toca.

Si `.workspace/agent.json` existe y no se puede leer (un sync a medias, otra
codificación), ese cerebro se salta: no se copia nada, queda pendiente y se
avisa; el nombre de la carpeta NO sustituye al del agente. Si no existe (cerebro
viejo), se usa el nombre que dé quien llama o el de la carpeta.

Se entrega UNA sola vez por cerebro: al terminar deja `.workspace/guia-agentes.json`
y, con ese sello legible, ya no vuelve a copiar nada. Lo que el usuario borró a
propósito (una skill, el renglón del catálogo) no regresa. Un sello que no se
lee (vacío, JSON roto, carpeta o enlace) no es sello ni cerebro vacío: no se
copia nada y el cerebro queda pendiente.

Lo que SÍ cambia en el cerebro del usuario: `skills/README.md` gana el bloque
de la guía al final si todavía no nombra esas skills, y `skills/INDEX-LITE.md`
(≤300 tokens, siempre cargado) la línea corta de la plantilla, solo si cabe
dejando lugar a la de la bandeja de aprendidas (skills_aprendidas); si no
cabe, INDEX-LITE no se toca. Antes de escribirlos se guarda una copia exacta en
`<estado>/backups/<MID>/<agente>-<hash>/skills/…`; si esa copia no se puede
guardar, no se toca el archivo. Para deshacer: copiar el respaldo encima.

La 0.9.2 le ponía a INDEX-LITE el bloque entero (de 980 a 1270 caracteres en
un cerebro de la plantilla 0.9.0, más de los 1200 de su presupuesto): `acortar`
lo cambia una vez por la línea corta en su lugar, solo si está tal cual, con
respaldo y su propio sello (migración 202611220230 y las otras dos puertas).

Determinista: la fecha del frontmatter es fija, el nombre sale de
`.workspace/agent.json`. Sin fechas de reloj ni rutas de esta máquina, para
que dos equipos que sincronizan el cerebro escriban los mismos bytes.
"""
import hashlib
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
MID = "202611110130_skills_guia_agentes"
FECHA = "2026-11-11"
MARCADOR = "workspace:guia-agentes"
#: El sello del cerebro: la guía se entrega UNA vez. Con él puesto, lo que el
#: usuario quite después (una skill, el renglón del catálogo) no vuelve. Vive en
#: `.workspace/` (viaja con el cerebro, así otra máquina tampoco la repite).
SELLO = ".workspace/guia-agentes.json"
RELS = (
    "skills/meta/configurar-workspace/SKILL.md",
    "skills/meta/personalizar-workspace/SKILL.md",
    "skills/meta/reparar-workspace/SKILL.md",
    "skills/meta/calendario-y-tareas/SKILL.md",
    "skills/meta/memoria-de-la-pestana/SKILL.md",
)
SLUGS = tuple(rel.split("/")[2] for rel in RELS)
BLOQUE = (
    "<!-- workspace:guia-agentes -->\n"
    "Guía de Workspace, si el índice de arriba no las nombra: "
    "`meta/configurar-workspace`, `meta/personalizar-workspace`, "
    "`meta/reparar-workspace`, `meta/calendario-y-tareas`, "
    "`meta/memoria-de-la-pestana`. Conversaciones entre agentes: "
    "`meta/colaborar-por-bus`.\n"
)
#: Lo de INDEX-LITE: la misma línea que trae la plantilla (un cerebro de antes queda igual que uno nuevo), sin el
#: marcador ni el renglón del bus (su fila «meta» ya lo nombra). Nombra las cinco skills: una 0.9.2 que la ve en un
#: cerebro sincronizado la da por anotada y no agrega su bloque largo.
RENGLON_LITE = ("configurar-workspace, personalizar-workspace, reparar-workspace, calendario-y-tareas, "
                "memoria-de-la-pestana.\n")
#: El bloque que la 0.9.2 agregó a INDEX-LITE (hoy el mismo de README.md): si está tal cual, `acortar` lo cambia por
#: RENGLON_LITE. Es historia: si un día BLOQUE cambia, LARGO_LITE se queda con el texto de la 0.9.2 (lo fija
#: tests/test_skills_guia_agentes_lite.py).
LARGO_LITE = BLOQUE
MID_CORTO = "202611220230_guia_lite_corta"
#: El sello de `acortar`: una vez por cerebro. Si el socio lo deshace (copia el respaldo encima), no vuelve.
SELLO_CORTO = ".workspace/guia-agentes-corta.json"
_LITE = "skills/INDEX-LITE.md"
_CATALOGOS = ("skills/README.md", _LITE)


#: La carpeta de cerebros del usuario dentro de la carpeta de instalación (= paths.BRAINS_DIRNAME; el .gitignore de
#: la entrega la deja fuera). En Mac y Linux, de fábrica Workspace se instala en ~/Workspace y los cerebros nacen en
#: ~/Workspace/Cerebros/<NOMBRE>: son del usuario, no del código.
_CEREBROS = "Cerebros"


def _dentro(brain, root):
    """¿`brain` es parte del código de Workspace (la plantilla, agents/, la raíz)? Un cerebro del usuario en
    <root>/Cerebros/<NOMBRE> NO: sin esto, el cerebro de fábrica de Mac y Linux nunca recibía las skills (23-nov)."""
    b = os.path.normcase(os.path.realpath(brain))
    r = os.path.normcase(os.path.realpath(root))
    if not (b == r or b.startswith(r + os.sep)):
        return False
    return not b.startswith(os.path.join(r, os.path.normcase(_CEREBROS)) + os.sep)


def _aplica(brain):
    """Un cerebro con catálogo de skills. Una carpeta de prueba sin skills/ no."""
    skills = os.path.join(brain, "skills")
    if os.path.islink(skills) or not os.path.isdir(skills):
        return False
    return any(os.path.isfile(os.path.join(brain, rel)) and not os.path.islink(
        os.path.join(brain, rel)) for rel in _CATALOGOS)


def _pasa_por_enlace(brain, rel):
    cur = brain
    for part in rel.split("/"):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            return True
        if not os.path.lexists(cur):
            return False
    return False


AGENTE_JSON = ".workspace/agent.json"
ILEGIBLE = "(ilegible)"
#: Un catálogo al que aún le falta el renglón (sin sello): pendiente a la vista.
RENGLON = "(renglón pendiente)"


def _agente(brain):
    """({name, display}, estado): "ok" | "falta" (no existe: cerebro viejo) |
    "ilegible" (existe y no se lee como un JSON objeto en UTF-8). Ilegible no
    es vacío."""
    path = os.path.join(brain, *AGENTE_JSON.split("/"))
    try:
        with open(path, encoding="utf-8-sig") as fh:   # un BOM (Notepad) no es ilegible
            data = json.load(fh)
    except FileNotFoundError:
        return {}, "falta"
    except (OSError, ValueError, UnicodeDecodeError):
        return {}, "ilegible"
    if not isinstance(data, dict):
        return {}, "ilegible"
    return data, "ok"


def _nombres(brain, name):
    data, _estado = _agente(brain)
    slug = str(data.get("name") or "")
    display = str(data.get("display") or "")
    slug = slug.strip() or (name or "").strip() or os.path.basename(os.path.abspath(brain))
    slug = re.sub(r"[^A-Za-z0-9_-]", "-", slug).strip("-") or "agente"
    display = " ".join(display.split()) or slug
    return slug, display


def _rellenar(texto, slug, display):
    return (texto.replace("{{AGENT_NAME}}", slug)
            .replace("{{AGENT_DISPLAY}}", display)
            .replace("{{AGENT_UPPER}}", slug.upper())
            .replace("{{DATE}}", FECHA))


def _leer(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def _falta(brain, rel):
    """¿Esa skill falta? Sí si no existe o es un archivo vacío (un corte entre
    crear y escribir; no hay nada del usuario que proteger). Una ruta que pasa
    por un enlace no se toca."""
    dest = os.path.join(brain, *rel.split("/"))
    if _pasa_por_enlace(brain, rel):
        return False
    if not os.path.lexists(dest):
        return True
    return os.path.isfile(dest) and not os.path.islink(dest) and os.path.getsize(dest) == 0


def _estado_sello(brain, sello=SELLO):
    """"falta" (no hay archivo) | "ok" (JSON objeto, se lee) | "ilegible".

    Ilegible no es vacío y no es un sello: 0 bytes, JSON roto, carpeta o
    enlace. No se sigue el enlace."""
    path = os.path.join(brain, *sello.split("/"))
    if not os.path.lexists(path):
        return "falta"
    if os.path.islink(path) or not os.path.isfile(path):
        return "ilegible"
    try:
        if os.path.getsize(path) == 0:
            return "ilegible"
        with open(path, encoding="utf-8-sig") as fh:   # un BOM no lo vuelve ilegible
            data = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return "ilegible"
    if not isinstance(data, dict):
        return "ilegible"
    return "ok"


def _sellado(brain):
    """¿Este cerebro ya recibió la guía? Solo un sello que se lee."""
    return _estado_sello(brain) == "ok"


def _faltan(brain):
    return [rel for rel in RELS if _falta(brain, rel)]


def trabajos(brain, root=ROOT):
    """Lo pendiente: rutas de skills que faltan y catálogos sin el renglón
    («<ruta> (renglón pendiente)»). Vacío si el cerebro no aplica, ya está al
    día o ya recibió la guía (sello)."""
    if not brain or not os.path.isdir(brain) or os.path.islink(brain) or _dentro(brain, root):
        return []
    if not _aplica(brain) or _sellado(brain):
        return []
    if _estado_sello(brain) == "ilegible":
        # Pendiente visible. No se listan las skills: copiarlas sería a ciegas.
        marcas = ["%s %s" % (SELLO, ILEGIBLE)]
        if _agente(brain)[1] == "ilegible":
            marcas.append("%s %s" % (AGENTE_JSON, ILEGIBLE))
        return marcas
    faltan = _faltan(brain)
    if faltan and _agente(brain)[1] == "ilegible":
        faltan.append("%s %s" % (AGENTE_JSON, ILEGIBLE))     # pendiente, no se toca
    # sin sello, un catálogo que todavía necesita el renglón también es trabajo: si
    # cambia en cada pasada (un sync constante) no se anota ni se sella, y sin esto
    # nadie lo vería (ni el doctor ni la migración). Un catálogo que no se lee no
    # cuenta (ilegible no es vacío) y uno que ya nombra las skills tampoco.
    for rel in _CATALOGOS:
        if not _pasa_por_enlace(brain, rel) \
                and _plan_anotar(os.path.join(brain, *rel.split("/"))) is not None:
            faltan.append("%s %s" % (rel, RENGLON))
    return faltan


def _sellar(brain, sello=SELLO, datos=None):
    """Deja el sello (atómico, sin pisar uno que ya esté). Contenido fijo: dos
    máquinas escriben los mismos bytes."""
    path = os.path.join(brain, *sello.split("/"))
    if os.path.lexists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(datos or {"id": MID, "skills": list(SLUGS)}, fh, indent=2)
            fh.write("\n")
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
        except OSError:
            if not os.path.lexists(path):
                os.rename(tmp, path)
    finally:
        if os.path.lexists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _escribir_nuevo(path, texto):
    """Publica el archivo COMPLETO o no lo publica: se escribe a un .tmp del
    mismo directorio y se enlaza a su nombre sin reemplazar nada (un corte deja
    a lo más un .tmp, que se borra; nunca un SKILL.md a medias). Un archivo
    vacío sí se reemplaza (no hay nada del usuario ahí). True si quedó escrito."""
    carpeta = os.path.dirname(path)
    os.makedirs(carpeta, exist_ok=True)
    tmp = os.path.join(carpeta, ".%s.tmp-%d" % (os.path.basename(path), os.getpid()))
    try:
        with open(tmp, "wb") as fh:
            fh.write(texto.encode("utf-8"))
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        if os.path.isfile(path) and not os.path.islink(path) and os.path.getsize(path) == 0:
            os.replace(tmp, path)
            return True
        try:
            os.link(tmp, path)                  # no reemplaza: si ya existe, falla
        except FileExistsError:
            return False
        except OSError:                         # sin enlaces duros en ese disco
            if os.path.lexists(path):
                return False
            os.rename(tmp, path)                # el candado del cerebro cubre la carrera
        return True
    finally:
        if os.path.lexists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _leer_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def backup_dir(state_dir, brain, name=None, mid=MID):
    """`<estado>/backups/<MID>/<agente>-<hash de la ruta>`: dos cerebros con el
    mismo nombre no comparten respaldo."""
    real = os.path.realpath(brain)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name or os.path.basename(real)) or "cerebro"
    return os.path.join(state_dir, "backups", mid,
                        "%s-%s" % (safe, hashlib.sha256(real.encode("utf-8")).hexdigest()[:8]))


def _respaldar(destino, crudo):
    """Guarda `crudo` en `destino` sin pisar un respaldo anterior distinto
    (destino, destino-2…). Levanta OSError si no se pudo: quien llama no toca
    el original."""
    n, cand = 1, destino
    while os.path.exists(cand):
        if _leer_bytes(cand) == crudo:
            return cand
        n += 1
        cand = "%s-%d" % (destino, n)
    os.makedirs(os.path.dirname(cand), exist_ok=True)
    with open(cand, "wb") as fh:
        fh.write(crudo)
    return cand


def cabe_en_lite(texto):
    """¿skills/INDEX-LITE.md con este texto sigue dentro de su presupuesto HOT (skills_aprendidas: LITE_TOKENS ×
    CHARS_POR_TOKEN), con lugar para la línea de la bandeja de aprendidas si todavía no la tiene? Cuenta texto, no
    finales de línea (un CRLF de Windows no gasta más). Sin skills_aprendidas, no."""
    try:
        import skills_aprendidas as sa
    except Exception:
        return False
    largo = len(texto.replace("\r\n", "\n"))
    if not sa._LITE_RE.search(sa._normal(texto)):
        largo += len(sa.LINEA_LITE) + 2
    return largo <= sa.LITE_TOKENS * sa.CHARS_POR_TOKEN


def _texto_utf8(path):
    """(bytes, texto) de un archivo normal en UTF-8; None si no existe, es un enlace o no se lee así."""
    if not os.path.isfile(path) or os.path.islink(path):
        return None
    crudo = _leer_bytes(path)
    try:
        return (crudo, crudo.decode("utf-8")) if crudo is not None else None
    except UnicodeDecodeError:
        return None


def _plan_anotar(path):
    """(bytes leídos, bytes nuevos) si el catálogo necesita el renglón; None si
    no (no existe, es un enlace, no se lee como UTF-8, o ya nombra las skills).
    INDEX-LITE recibe RENGLON_LITE y solo si cabe (cabe_en_lite); README.md, el
    bloque entero. Un archivo ilegible no es un archivo vacío: no se toca."""
    leido = _texto_utf8(path)
    if leido is None:
        return None
    crudo, texto = leido
    if MARCADOR in texto or all(slug in texto for slug in SLUGS):
        return None
    lite = os.path.basename(path) == os.path.basename(_LITE)
    nl = "\r\n" if "\r\n" in texto else "\n"
    cuerpo = texto
    if cuerpo and not cuerpo.endswith(("\n", "\r")):
        cuerpo += nl
    nuevo = cuerpo + nl + (RENGLON_LITE if lite else BLOQUE).replace("\n", nl)
    if lite and not cabe_en_lite(nuevo):
        return None
    return crudo, nuevo.encode("utf-8")


def _plan_acortar(path):
    """(bytes leídos, bytes nuevos) si INDEX-LITE tiene, tal cual, el bloque largo de la 0.9.2 (LARGO_LITE en LF o
    CRLF): va RENGLON_LITE en su lugar, con los mismos finales de línea, y lo demás byte por byte igual. None si no
    (no existe, es un enlace, no se lee como UTF-8, o el socio cambió el bloque)."""
    leido = _texto_utf8(path)
    if leido is None:
        return None
    crudo, texto = leido
    for nl in ("\r\n", "\n"):
        largo = LARGO_LITE.replace("\n", nl)
        if largo in texto:
            return crudo, texto.replace(largo, RENGLON_LITE.replace("\n", nl), 1).encode("utf-8")
    return None


def _anotar(path, rel, brain, respaldo, plan_de=_plan_anotar):
    """Agrega el renglón de la guía al catálogo (o, con `plan_de=_plan_acortar`,
    acorta el de la 0.9.2), con copia exacta previa en `respaldo` (carpeta del
    agente). Si el archivo cambió mientras tanto (una edición, un sync) no lo
    toca: la próxima puerta lo ve. No reescribe lo demás."""
    plan = plan_de(path)
    if plan is None:
        return False
    crudo, nuevo = plan
    # P3 conocido (0.9.2, anotado para el socio, sin arreglar): si el catálogo cambia
    # DESPUÉS de este respaldo y antes del reemplazo, cada reintento deja otra
    # copia (README.md-2, -3…) aunque al final no escriba. Salida posible: comparar
    # contra el archivo antes de respaldar y otra vez después, o respaldar solo
    # cuando ya se va a reemplazar. Cada copia es chica y no se acumula más rápido
    # que las pasadas del doctor.
    _respaldar(os.path.join(respaldo, *rel.split("/")), crudo)
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        with open(tmp, "wb") as fh:
            fh.write(nuevo)
        if _leer_bytes(path) != crudo:
            return "cambio"            # no se sella: la próxima pasada reintenta el renglón
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    try:                       # el «deshacer» del formato v2 lo reconoce como cambio de Workspace
        import brain_format
        import paths
        brain_format.nota_cambio_de_workspace(brain, rel, crudo, nuevo, paths.state_dir())
    except Exception:
        pass
    return True


def candado(brain, timeout=30):
    """El candado entre procesos de UN cerebro para todo lo que este módulo
    escribe (la migración, cargar un agente y `workspace doctor` pueden
    coincidir, y dos máquinas con el cerebro sincronizado también).

    Es EL MISMO de sin_aprobacion (Greptile 0.9.2, #4): los dos reescriben
    skills/README.md e INDEX-LITE.md, y con candados distintos un doctor y una
    carga de agente podían leer el mismo contenido y pisarse al reemplazarlo.
    No es reentrante: quien llama a los dos (agent_admin.load, el doctor) los
    llama uno DESPUÉS del otro, nunca uno dentro del otro."""
    import sin_aprobacion
    return sin_aprobacion.candado(brain, timeout)


def actualizar(brain, root=ROOT, state_dir=None, name=None, dry_run=False, log=None,
               timeout=30):
    """Copia las skills que faltan y anota el catálogo (con respaldo previo de
    README.md e INDEX-LITE.md). No pisa una skill que ya existe. Devuelve las
    rutas tocadas. Todo corre dentro de UN candado del cerebro: lo que se
    decide se decide con lo que hay AHORA, no con lo que había antes de esperar.
    Levanta OSError si el respaldo no se pudo guardar (el catálogo queda como
    estaba) y olock.LockTimeout si el candado no se libera en `timeout`."""
    if dry_run:
        return trabajos(brain, root)
    if not brain or not os.path.isdir(brain) or os.path.islink(brain) or _dentro(brain, root) \
            or not _aplica(brain):
        return []
    with candado(brain, timeout):
        return _actualizar_con_candado(brain, root, state_dir, name, log)


def _actualizar_con_candado(brain, root, state_dir, name, log=None):
    if _sellado(brain):
        return []
    if _estado_sello(brain) == "ilegible":
        if log is not None:
            try:
                log("%s no se puede leer (vacío, dañado, carpeta o enlace): no es un sello y no "
                    "copié las skills de la guía. Bórralo, o espera a que termine el sync, y corre "
                    "`workspace doctor`" % SELLO)
            except Exception:
                pass
        return []
    pendientes = _faltan(brain)
    if pendientes and _agente(brain)[1] == "ilegible":
        if log is not None:
            try:
                log("%s no se puede leer como JSON en UTF-8: no copié las skills de la guía en este "
                    "cerebro. Guárdalo bien (con Obsidian Sync, espera a que termine) y corre "
                    "`workspace doctor`" % AGENTE_JSON)
            except Exception:
                pass
        return []
    slug, display = _nombres(brain, name)
    hechos = []
    for rel in pendientes:
        origen = os.path.join(root, "templates", "agent", "brain", *rel.split("/"))
        crudo = _leer(origen)
        if not crudo:
            continue
        texto = _rellenar(crudo, slug, display)
        if "{{" in texto:
            continue
        dest = os.path.join(brain, *rel.split("/"))
        if _escribir_nuevo(dest, texto):
            hechos.append(rel)
    if state_dir is None:
        import paths
        state_dir = paths.state_dir()
    respaldo = backup_dir(state_dir, brain, name)
    pospuesto = False
    for rel in _CATALOGOS:
        path = os.path.join(brain, *rel.split("/"))
        if _pasa_por_enlace(brain, rel):
            continue
        marca = _anotar(path, rel, brain, respaldo)
        if marca == "cambio":
            pospuesto = True                    # el catálogo cambió: no sellar
            if log is not None:
                try:
                    log("%s cambió mientras lo respaldaba (¿un sync en curso?): no le añadí el "
                        "renglón de la guía ni sellé el cerebro; reintento en la próxima pasada "
                        "(`workspace doctor`)" % rel)
                except Exception:
                    pass
        elif marca:
            hechos.append(rel)
    if not _faltan(brain) and not pospuesto:    # todo entregado: ya no vuelve
        _sellar(brain)
    return hechos


def _a_medias(brain):
    """¿`.workspace/` está a medias (un sync)? Su agent.json o un sello de la guía no se leen: no se toca nada."""
    return _agente(brain)[1] == "ilegible" or "ilegible" in (_estado_sello(brain), _estado_sello(brain, SELLO_CORTO))


def por_acortar(brain, root=ROOT):
    """¿INDEX-LITE de este cerebro todavía tiene, tal cual, el bloque largo que le puso la 0.9.2?"""
    if not brain or not os.path.isdir(brain) or os.path.islink(brain) or _dentro(brain, root) \
            or not _aplica(brain) or _pasa_por_enlace(brain, _LITE):
        return False
    if _estado_sello(brain, SELLO_CORTO) != "falta" or _a_medias(brain):
        return False
    return _plan_acortar(os.path.join(brain, *_LITE.split("/"))) is not None


def acortar(brain, root=ROOT, state_dir=None, name=None, dry_run=False, log=None, timeout=30):
    """Cambia el bloque largo de la 0.9.2 en INDEX-LITE por RENGLON_LITE en su lugar (solo si está tal cual), con
    respaldo exacto previo en `<estado>/backups/<MID_CORTO>/<agente>-<hash>/skills/INDEX-LITE.md`, y sella el cerebro
    (SELLO_CORTO): una vez. README.md no cambia (no tiene presupuesto). → [rel] escritos. Mismo candado que
    `actualizar`: quien llama a los dos los llama uno DESPUÉS del otro. Levanta OSError si el respaldo no se pudo
    guardar (el archivo queda como estaba) y olock.LockTimeout si el candado no se libera en `timeout`."""
    if not por_acortar(brain, root):
        return []
    if dry_run:
        return [_LITE]
    with candado(brain, timeout):
        if not por_acortar(brain, root):            # lo que hay AHORA, no lo de antes de esperar
            return []
        if state_dir is None:
            import paths
            state_dir = paths.state_dir()
        path = os.path.join(brain, *_LITE.split("/"))
        marca = _anotar(path, _LITE, brain, backup_dir(state_dir, brain, name, MID_CORTO), _plan_acortar)
        if marca == "cambio":
            if log is not None:
                try:
                    log("%s cambió mientras lo respaldaba (¿un sync en curso?): no acorté el renglón de la guía; "
                        "reintento en la próxima pasada (`workspace doctor`)" % _LITE)
                except Exception:
                    pass
            return []
        if not marca:
            return []
        _sellar(brain, SELLO_CORTO, {"id": MID_CORTO, "archivo": _LITE})
        return [_LITE]
