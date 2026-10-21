#!/usr/bin/env python3
"""WORKSPACE · sin_aprobacion — en el cerebro nada espera a una persona.

Decisión del dueño (2026-10-18), sobre la del 2026-10-16 (sin destilador ni
revisor sin ventana): el proceso de skills, memoria e identidad de un agente no
tiene a nadie en medio. Un cliente no aprueba skills una por una, no diseña a
mano la personalidad del agente ni contesta permisos del motor para tareas de
rutina. El agente aplica directo, lo deja recuperable (nada se borra) y lo
reporta en su línea 🧠.

Una sola función, `actualizar(brain)`, llamada desde TRES puertas (como
memoria_textos y brain_format):
  · la migración automática 202610181200_sin_aprobacion (`workspace update`);
  · cargar un agente (`agent_admin.load`): un cerebro que llega DESPUÉS de la
    actualización (instalación nueva, otra máquina, sync) no pasa por la
    migración, porque los sellos son por máquina;
  · `workspace doctor --fix` (fase 4c).

Qué hace en un cerebro:
  1. Textos. Reemplaza los BLOQUES de líneas que pedían a una persona (aprobar
     skills en skills/_propuestas/, skills «intocables» de un socio, «si dudo,
     pregunto», confirmación para escribir la memoria (N2), diseñar a mano el
     SOUL, ofrecer un monitor que no existe) o un comando que el motor pregunta
     (usage.py, git commit, find | wc -l, memory_index.py) por el texto de la
     plantilla actual. SOLO si cada línea del bloque es IDÉNTICA a la de alguna
     versión de la plantilla (migrations/data/sin_aprobacion_lines.json, que
     gen_sin_aprobacion_lines.py genera del historial; los marcadores {{X}} son
     comodín, como en legacy_template_lines.json). Lo que el dueño editó no se
     toca. Si en un bloque editado queda una línea vieja de la plantilla,
     idéntica, el paquete de arranque avisa al agente que ESA instrucción de
     Workspace ya no aplica (memoria.AVISO_APROBACION, con
     textos_viejos_con_compuertas de aquí); las reglas del dueño se respetan
     y no lo disparan. Los registros históricos (log-recent, brain-version,
     MILESTONES) nunca se tocan.
  2. Sobras de skills/_propuestas/. Su README (la «cuarentena») y `_mejoras/`
     pasan a skills/_archive/ con nombre por CONTENIDO
     (`propuestas-README-<huella>.md`, `propuestas-mejoras-<huella>/`); las
     propuestas que el agente ya resolvió (`status: integrada|archivada` en su
     SKILL.md), a `propuestas-<huella>/<nombre>/`, el nombre que les da
     202610162300_sin_destilado. Lo ya archivado con el mismo contenido (otra
     máquina) no se archiva otra vez.

Respaldo antes de tocar nada en `<estado>/backups/<id>/<agente>-<hash>/`.
Todo corre bajo UN candado por cerebro (candado()): las puertas y el arranque
de sesión que archiva las propuestas resueltas no se pisan. Un texto que no se
puede leer como UTF-8 nunca se reescribe y se reporta (trabajos, log).
Idempotente y determinista (regla 4: un cerebro compartido corre esto en cada
máquina, quizá antes de sincronizarse; lo que se escribe en el cerebro no lleva
fechas ni rutas, así que todas llegan a los mismos bytes). Nunca borra
contenido. Un cerebro dentro del propio Workspace (la plantilla) no se toca.
Stdlib, Python 3.9+, Mac y Windows.
"""
import hashlib
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
MID = "202610181200_sin_aprobacion"
DATA = os.path.join("migrations", "data", "sin_aprobacion_lines.json")
#: Las filas de la identidad (BRAIN.md) también van al CLAUDE.md de un cerebro
#: que todavía no pasó al formato v2 (ahí vive la identidad).
IDENTIDAD, LEGADO = "BRAIN.md", "CLAUDE.md"
PROPUESTAS = ("skills", "_propuestas")
ARCHIVE = ("skills", "_archive")
#: Registros históricos: la historia no se reescribe aunque su línea venga de
#: la plantilla (runbooks/versiones-y-migraciones.md, «Textos dentro de cerebros»).
HISTORIA = frozenset({"STATE/log-recent.md", "STATE/brain-version.md", "STATE/MILESTONES.md"})

#: Frases de los textos viejos de la plantilla que piden a una persona (o un
#: comando que el motor pregunta). Las usan el aviso del paquete de arranque
#: (memoria.paquete) y la verificación del generador de la tabla: una sola
#: lista (regla 5). Ningún texto de la plantilla actual debe contenerlas, y
#: son frases de la plantilla, no palabras sueltas: una nota del dueño que diga
#: «intocable» no dispara el aviso en cada sesión.
COMPUERTAS = re.compile("|".join((
    # skills
    r"cambios a esta lista: solo un socio", r"solo un socio aprueba", r"\(solo un socio\)",
    r"aprueba un humano", r"un humano aprueba", r"nunca directo al catálogo",
    r"intocables? para (?:procesos|curación) automátic", r"si dudo, pregunto",
    r"confirmar antes de reversar", r"proponer el patch al socio", r"status: propuesta",
    r"\|\s*socio>",
    # memoria
    r"modificar archivos no-identity de mi", r"gate humano", r"promover (?:de ahí )?= humano",
    r"staging humano", r"humano en sesión", r"lo hace un humano",
    # identidad
    r"trabajo humano deliberado", r"diseño humano deliberado", r"pendiente de diseño humano",
    r"solo cambia por decisión deliberada",
    # pasos que el motor pregunta o que no existen
    r"ofrecer (?:activar )?(?:un )?monitor", r"usage\.py", r"git add skills/")), re.I)
#: Dónde se buscan: lo que el agente lee al arrancar o al seguir el Skill Loop.
TEXTOS = ("BRAIN.md", "CLAUDE.md", "BOOT/00-SOUL.md", "BOOT/03-RULES.md", "BOOT/04-BRAIN-MAP.md",
          "STATE/MEMORY.md", "STATE/INDEX.md", "STATE/PENDIENTES.md", "skills/README.md",
          "skills/INDEX-LITE.md", "skills/_propuestas/README.md",
          "skills/meta/skill-creator/SKILL.md", "skills/meta/skill-improver/SKILL.md",
          "skills/meta/skill-curator/SKILL.md", "skills/meta/reload-brain/SKILL.md")
_MAX_LECTURA = 256 * 1024
#: Estados con los que el agente da por resuelta una propuesta vieja.
RESUELTAS = frozenset({"integrada", "archivada"})


# ── utilidades ──────────────────────────────────────────────────────────────
def _leer_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _texto(crudo):
    """Texto estricto (regla 2): lo que no es UTF-8 no se interpreta ni se
    reescribe. El BOM se conserva tal cual (reemplazar() lo sabe saltar)."""
    if crudo is None:
        return None
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _dentro(path, root):
    p = os.path.normcase(os.path.realpath(path))
    r = os.path.normcase(os.path.realpath(root))
    return p == r or p.startswith(r + os.sep)


def _listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _es_puntero(crudo):
    try:
        import brain_format
        return brain_format._is_pointer(crudo)
    except Exception:
        return False


# ── la tabla de bloques (generada del historial de la plantilla) ────────────
_TABLAS = {}


def tabla(root=ROOT):
    """{archivo: [(patrones, nuevas)]}: `patrones` = [(regex, {marcador:
    grupo})] por línea del bloque viejo (brain_format.patron_linea); `nuevas` =
    las líneas que lo reemplazan. El bloque más largo se prueba primero. Una
    fila cuyas líneas nuevas usan un marcador que el bloque viejo no tiene se
    descarta (no se podría rellenar)."""
    clave = os.path.abspath(root)
    if clave in _TABLAS:
        return _TABLAS[clave]
    import brain_format
    try:
        with open(os.path.join(root, DATA), encoding="utf-8") as fh:
            archivos = json.load(fh).get("files") or {}
    except (OSError, ValueError):
        archivos = {}
    out = {}
    for rel, filas in sorted(archivos.items()):
        if rel in HISTORIA or not isinstance(filas, list):
            continue
        lista = []
        for fila in filas:
            if not isinstance(fila, dict):
                continue
            viejas, nuevas = fila.get("old"), fila.get("new")
            if not (isinstance(viejas, list) and viejas and isinstance(nuevas, list)) or \
                    not all(isinstance(x, str) for x in viejas + nuevas):
                continue
            patrones = [brain_format.patron_linea(l) for l in viejas]
            marcas = set().union(*(set(s) for _rx, s in patrones))
            if any(m not in marcas for l in nuevas for m in brain_format._PLACEHOLDER.findall(l)):
                continue
            lista.append((patrones, list(nuevas)))
        lista.sort(key=lambda f: -len(f[0]))
        out[rel] = lista
    _TABLAS[clave] = out
    return out


def _lineas(texto):
    """[(cuerpo, fin_de_línea)] partiendo SOLO por \\n (\\r\\n se conserva)."""
    partes = texto.split("\n")
    out = []
    for k, p in enumerate(partes):
        ultima = k == len(partes) - 1
        if ultima and p == "":
            break
        fin = "" if ultima else "\n"
        if p.endswith("\r") and not ultima:
            p, fin = p[:-1], "\r\n"
        out.append((p, fin))
    return out


def _casar(cuerpos, i, patrones):
    """{marcador: valor} si las líneas desde `i` son el bloque; None si no. El
    mismo marcador en dos líneas del bloque debe valer lo mismo."""
    if i + len(patrones) > len(cuerpos):
        return None
    vals = {}
    for k, (rx, seen) in enumerate(patrones):
        m = rx.match(cuerpos[i + k])
        if not m:
            return None
        for tok, g in seen.items():
            if vals.setdefault(tok, m.group(g)) != m.group(g):
                return None
    return vals


def reemplazar(texto, filas):
    """(texto nuevo, bloques reemplazados). Conserva BOM y finales de línea:
    las líneas nuevas toman el del bloque viejo (\\r\\n si lo usaba)."""
    import brain_format
    bom = "\ufeff" if texto.startswith("\ufeff") else ""
    lineas = _lineas(texto[len(bom):])
    cuerpos = [c for c, _f in lineas]
    out, i, n = [], 0, 0
    while i < len(lineas):
        for patrones, nuevas in filas:
            vals = _casar(cuerpos, i, patrones)
            if vals is None:
                continue
            fines = [f for _c, f in lineas[i:i + len(patrones)]]
            eol = "\r\n" if "\r\n" in fines else "\n"
            for k, nueva in enumerate(nuevas):
                # una sola pasada: un valor que trae «{{X}}» no se vuelve a rellenar
                nueva = brain_format._PLACEHOLDER.sub(lambda m: vals.get(m.group(0), m.group(0)), nueva)
                out.append(nueva + (fines[-1] if k == len(nuevas) - 1 else eol))
            i += len(patrones)
            n += 1
            break
        else:
            out.append(cuerpos[i] + lineas[i][1])
            i += 1
    return bom + "".join(out), n


# ── qué hay que hacer en un cerebro (solo lectura) ──────────────────────────
#: Lo que se dice de un texto que la tabla cubre y no se puede leer.
ILEGIBLE = "(ilegible)"


def _plan_textos(brain, root):
    """([(rel, bytes leídos, texto nuevo)], [rel ilegibles]). Los bytes leídos
    sirven para no pisar una edición (o un sync) que llegue entre leer y
    escribir. Un texto que la tabla cubre y no se puede leer como UTF-8
    (permisos, iCloud sin descargar, otro editor lo guardó en ANSI o UTF-16)
    no se interpreta ni se reescribe (regla 2), pero tampoco se calla: va en
    la segunda lista, y trabajos() y actualizar() lo dicen (Greptile,
    2026-10-18: el doctor decía «al día» con las instrucciones viejas ahí)."""
    jobs, ilegibles = [], []
    destinos = []
    for rel, filas in sorted(tabla(root).items()):
        destinos.append((rel, filas))
        if rel == IDENTIDAD:
            destinos.append((LEGADO, filas))
    for rel, filas in destinos:
        p = os.path.join(brain, *rel.split("/"))
        if not filas or os.path.islink(p) or not os.path.isfile(p):
            continue
        crudo = _leer_bytes(p)
        txt = _texto(crudo)
        if txt is None:
            ilegibles.append(rel)
            continue
        if rel == LEGADO and _es_puntero(crudo):
            continue
        nuevo, n = reemplazar(txt, filas)
        if n and nuevo != txt:
            jobs.append((rel, crudo, nuevo))
    return jobs, ilegibles


_SD = []


def _sin_destilado():
    """Las utilidades de archivado de 202610162300_sin_destilado (huella por
    contenido, destino libre, «ya estaba archivado igual»): las mismas, para
    que dos máquinas lleguen al mismo nombre (regla 5)."""
    if not _SD:
        import migrate
        _SD.append(migrate.modulo("202610162300_sin_destilado"))
    if _SD[0] is None:
        raise RuntimeError("no encontré la migración 202610162300_sin_destilado")
    return _SD[0]


def propuesta_resuelta(path):
    """True si el agente ya resolvió esta propuesta vieja: su SKILL.md dice
    `status: integrada` o `status: archivada` en el frontmatter. Ya no espera
    a nadie: hooks/skill_review.py no la vuelve a pedir y aquí se archiva. El
    `status:` lo lee skill_meta.read_status, el mismo lector del catálogo
    (regla 5)."""
    if not os.path.isfile(os.path.join(path, "SKILL.md")):
        return False
    import skill_meta
    return skill_meta.read_status(path) in RESUELTAS


def _plan_archivo(brain, solo_resueltas=False):
    """[(origen, destino|None)] de lo que pasa de skills/_propuestas/ a
    skills/_archive/. destino None = no se pudo leer (se avisa al aplicar).
    `solo_resueltas`: solo las propuestas que el agente ya marcó (lo que hace
    el arranque de sesión, ver archivar_propuestas_resueltas)."""
    props = os.path.join(brain, *PROPUESTAS)
    if os.path.islink(props) or not os.path.isdir(props):
        return []
    sd = _sin_destilado()
    arch = os.path.join(brain, *ARCHIVE)
    jobs = []
    readme = os.path.join(props, "README.md")
    if not solo_resueltas and os.path.isfile(readme) and not os.path.islink(readme):
        previos = [os.path.join(arch, n) for n in _listdir(arch)
                   if n.startswith("propuestas-README-") and n.endswith(".md")
                   and os.path.isfile(os.path.join(arch, n))]
        jobs.append((readme, sd._destino(
            readme, previos, lambda h: os.path.join(arch, "propuestas-README-%s.md" % h))))
    mejoras = os.path.join(props, "_mejoras")
    if not solo_resueltas and os.path.isdir(mejoras) and not os.path.islink(mejoras):
        previos = [os.path.join(arch, n) for n in _listdir(arch)
                   if n.startswith("propuestas-mejoras-") and os.path.isdir(os.path.join(arch, n))]
        jobs.append((mejoras, sd._destino(
            mejoras, previos, lambda h: os.path.join(arch, "propuestas-mejoras-%s" % h))))
    for n in _listdir(props):
        p = os.path.join(props, n)
        if n.startswith(("_", ".")) or os.path.islink(p) or not os.path.isdir(p) \
                or not propuesta_resuelta(p):
            continue
        previos = [os.path.join(arch, d, n) for d in _listdir(arch)
                   if os.path.isdir(os.path.join(arch, d, n))]
        jobs.append((p, sd._destino(
            p, previos, lambda h, n=n: os.path.join(arch, "propuestas-%s" % h, n))))
    return jobs


def _rel(brain, path):
    return os.path.relpath(path, brain).replace(os.sep, "/")


def trabajos(brain, root=ROOT):
    """[rutas relativas] de lo que falta en `brain` (vacío = al día). Solo
    lectura; nunca lanza. Lo ilegible cuenta como pendiente: un texto como
    «<rel> (ilegible)» (no se reescribe nunca: se avisa hasta que el dueño lo
    guarde como UTF-8) y lo que no se pudo revisar de skills/_propuestas/."""
    if not brain or not os.path.isdir(brain) or _dentro(brain, root):
        return []
    jobs, ilegibles = _plan_textos(brain, root)
    out = [rel for rel, _c, _n in jobs] + ["%s %s" % (rel, ILEGIBLE) for rel in ilegibles]
    try:
        out += [_rel(brain, src) for src, _d in _plan_archivo(brain)]
    except Exception:
        out.append("/".join(PROPUESTAS) + "/")
    return out


def pendiente(brain, root=ROOT):
    return bool(trabajos(brain, root))


def textos_con_compuertas(brain):
    """[rutas relativas] de los textos del cerebro que todavía mencionan una
    compuerta (COMPUERTAS), sean de la plantilla o del dueño. Solo lectura,
    tolerante. Lo usan las verificaciones; el aviso del paquete de arranque
    mira solo las líneas viejas de la plantilla (textos_viejos_con_compuertas)."""
    out = []
    for rel in TEXTOS:
        crudo = _leer_bytes(os.path.join(brain, *rel.split("/")))
        if crudo and COMPUERTAS.search(crudo[:_MAX_LECTURA].decode("utf-8", "replace")):
            out.append(rel)
    return out


_VIEJAS = {}


def lineas_viejas(root=ROOT):
    """{archivo: [regex de una línea]} de las líneas VIEJAS de la plantilla de
    Workspace (las `old` de la tabla) que pedían a una persona (COMPUERTAS).
    Los marcadores {{X}} son comodín (brain_format.patron_linea, como en la
    migración); el resto se compara entero y literal. La historia no cuenta."""
    clave = os.path.abspath(root)
    if clave in _VIEJAS:
        return _VIEJAS[clave]
    import brain_format
    try:
        with open(os.path.join(root, DATA), encoding="utf-8") as fh:
            archivos = json.load(fh).get("files") or {}
    except (OSError, ValueError):
        archivos = {}
    out = {}
    for rel, filas in sorted(archivos.items()):
        if rel in HISTORIA or not isinstance(filas, list):
            continue
        filas = [f for f in filas if isinstance(f, dict)]
        nuevas = {l for f in filas for l in (f.get("new") or []) if isinstance(l, str)}
        vistas, rxs = set(), []
        for f in filas:
            for l in f.get("old") or []:
                if isinstance(l, str) and l not in vistas and l not in nuevas \
                        and COMPUERTAS.search(l):
                    vistas.add(l)
                    rxs.append(brain_format.patron_linea(l)[0])
        if rxs:
            out[rel] = rxs
    _VIEJAS[clave] = out
    return out


def textos_viejos_con_compuertas(brain, root=ROOT):
    """[rutas relativas] de los textos del cerebro que todavía traen, EXACTA,
    una línea vieja de la plantilla de Workspace que pedía a una persona
    (lineas_viejas): la migración no la cambió porque el dueño editó algo de su
    bloque. Solo esto dispara el aviso del paquete de arranque
    (memoria.AVISO_APROBACION). Lo que escribió el dueño, aunque hable de
    aprobar o de preguntar, es una regla suya: no lo dispara. Solo lectura,
    tolerante."""
    out = []
    destinos = []
    for rel, rxs in sorted(lineas_viejas(root).items()):
        destinos.append((rel, rxs))
        if rel == IDENTIDAD:
            destinos.append((LEGADO, rxs))
    for rel, rxs in destinos:
        crudo = _leer_bytes(os.path.join(brain, *rel.split("/")))
        if not crudo or (rel == LEGADO and _es_puntero(crudo)):
            continue
        texto = crudo[:_MAX_LECTURA].decode("utf-8", "replace").lstrip("﻿")
        for ln in texto.split("\n"):
            ln = ln[:-1] if ln.endswith("\r") else ln
            if any(rx.match(ln) for rx in rxs):
                out.append(rel)
                break
    return out


# ── aplicar ─────────────────────────────────────────────────────────────────
def backup_dir(state_dir, brain, name=None):
    """`<estado>/backups/<MID>/<agente>-<hash de la ruta>`: dos cerebros con el
    mismo nombre (se quitó uno y se cargó otro) no comparten respaldo."""
    real = os.path.realpath(brain)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name or os.path.basename(real)) or "cerebro"
    return os.path.join(state_dir, "backups", MID,
                        "%s-%s" % (safe, hashlib.sha256(real.encode("utf-8")).hexdigest()[:8]))


def _respaldar_bytes(destino, crudo, sd):
    """Guarda `crudo` en `destino` sin pisar un respaldo anterior distinto
    (cada estado previo queda: destino, destino-2…)."""
    if _leer_bytes(destino) == crudo:
        return
    destino = sd._free(destino)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "wb") as fh:
        fh.write(crudo)


def _escribir(path, texto, antes):
    """False si el archivo cambió desde que se leyó (una edición o un sync en
    medio: se deja para la próxima puerta); si no, lo escribe con el guardado
    atómico de las migraciones de cerebro (brain_format._atomic_write: el del
    módulo, regla 1)."""
    if _leer_bytes(path) != antes:
        return False
    import brain_format
    brain_format._atomic_write(path, texto.encode("utf-8"))
    return True


def _avisar_formato_v2(brain, rel, antes, despues, state_dir):
    """Este cambio es de Workspace, no del dueño: el «deshacer» del formato v2
    (brain_format) lo tiene que reconocer como suyo; `despues=None` = lo
    archivó (ya no está en su lugar). Falla-suave."""
    try:
        import brain_format
        brain_format.nota_cambio_de_workspace(brain, rel, antes, despues, state_dir)
    except Exception:
        pass


def candado(brain, timeout=30):
    """El candado entre procesos de UN cerebro para todo lo que este módulo
    escribe: las tres puertas (actualizar, cargar, `doctor --fix`) y el
    arranque de sesión pueden coincidir, y sin él dos corridas se pisaban el
    texto, el respaldo o el destino del archivado (Greptile, 2026-10-18).
    olock.local_lock, como usuarios._lock: su .lock vive en `.claude/locks/`
    del cerebro (Obsidian no lo sube) o en el estado de la máquina. No es
    reentrante: una sola toma por operación."""
    from olock import local_lock
    return local_lock(os.path.join(brain, ".sin-aprobacion"), timeout=timeout)


def _avisar_ilegibles(ilegibles, log):
    for rel in ilegibles:
        if log is not None:
            try:
                log("%s no se puede leer como texto UTF-8 (permisos, o lo guardó otro editor en "
                    "otra codificación): no se tocó. Si todavía pide aprobación, guárdalo como "
                    "UTF-8 y corre `workspace doctor --fix`" % rel)
            except Exception:
                pass


def actualizar(brain, root=ROOT, state_dir=None, name=None, dry_run=False, log=None,
               timeout=30):
    """Aplica el plan de `brain` con respaldo previo. Devuelve lo que cambió
    ([rutas relativas]; lo archivado como «origen → destino»). TODO (plan,
    respaldo, escrituras y archivado) corre dentro de UN candado del cerebro
    (candado()): dos puertas a la vez no se pisan; la segunda espera y
    encuentra el trabajo hecho. Un texto ilegible no se toca y se avisa por
    `log(mensaje)`. Lanza si algo no se pudo leer o mover, o si el candado no
    se libera en `timeout` (quien llama avisa; las otras puertas reintentan):
    lo que ya se hizo queda hecho y respaldado."""
    if not brain or not os.path.isdir(brain) or _dentro(brain, root):
        return []
    if dry_run:
        textos, _ilegibles = _plan_textos(brain, root)
        return [rel for rel, _c, _n in textos] + [_rel(brain, s) for s, _d in _plan_archivo(brain)]
    with candado(brain, timeout):
        textos, ilegibles = _plan_textos(brain, root)
        _avisar_ilegibles(ilegibles, log)
        archivos = _plan_archivo(brain)
        if not textos and not archivos:
            return []
        if state_dir is None:
            import paths
            state_dir = paths.state_dir()
        sd = _sin_destilado()
        backup = backup_dir(state_dir, brain, name)
        hechos = []
        for rel, crudo, texto in textos:
            path = os.path.join(brain, *rel.split("/"))
            if _leer_bytes(path) != crudo:
                continue                        # cambió: la próxima puerta lo ve
            _respaldar_bytes(os.path.join(backup, *rel.split("/")), crudo, sd)
            if _escribir(path, texto, crudo):
                hechos.append(rel)
                nuevo = _leer_bytes(path)
                if nuevo is not None:
                    _avisar_formato_v2(brain, rel, crudo, nuevo, state_dir)
        return hechos + _archivar(brain, archivos, backup, sd, state_dir)


def archivar_propuestas_resueltas(brain, state_dir=None, name=None, timeout=1.0, root=ROOT):
    """Lo que hace el arranque de cada sesión (hooks/skill_review.py): las
    propuestas viejas que el agente ya marcó `status: integrada|archivada`
    pasan a skills/_archive/ — la misma lógica (_plan_archivo, _archivar) y el
    MISMO candado que actualizar(). Barato: sin skills/_propuestas/ no hace
    nada. Espera corta: si otro proceso tiene el candado, lanza (LockTimeout)
    y quien llama lo deja para la próxima sesión. → lo archivado."""
    props = os.path.join(brain or "", *PROPUESTAS)
    if not brain or os.path.islink(props) or not os.path.isdir(props) or _dentro(brain, root):
        return []
    with candado(brain, timeout):
        archivos = _plan_archivo(brain, solo_resueltas=True)
        if not archivos:
            return []
        if state_dir is None:
            import paths
            state_dir = paths.state_dir()
        return _archivar(brain, archivos, backup_dir(state_dir, brain, name), _sin_destilado(),
                         state_dir)


def _archivar(brain, archivos, backup, sd, state_dir):
    """Mueve cada (origen, destino) a skills/_archive/ con respaldo previo; lo
    ya archivado igual no se duplica. Se llama con el candado tomado."""
    hechos = []
    for src, dest in archivos:
        rel = _rel(brain, src)
        if dest is None:
            raise OSError("no se pudo leer %s" % rel)
        bk = os.path.join(backup, *rel.split("/"))
        os.makedirs(os.path.dirname(bk), exist_ok=True)
        crudo = None
        if os.path.isdir(src):
            shutil.copytree(src, sd._free(bk))   # cada archivado con su respaldo
        else:
            crudo = _leer_bytes(src)
            if crudo is None:
                raise OSError("no se pudo leer %s" % rel)
            _respaldar_bytes(bk, crudo, sd)
        if os.path.exists(dest) and sd.huella(dest) == sd.huella(src):
            sd._sobra(src, dest)                # ya archivado igual (otra máquina)
        else:
            dest = sd._free(dest)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
        if crudo is not None:                   # el README que renombró el formato v2
            _avisar_formato_v2(brain, rel, crudo, None, state_dir)
        hechos.append("%s → %s" % (rel, _rel(brain, dest)))
    if archivos:
        try:
            os.rmdir(os.path.join(brain, *PROPUESTAS))   # solo si quedó vacía
        except OSError:
            pass
    return hechos
