#!/usr/bin/env python3
"""WORKSPACE · identidad — quién eres en ESTA máquina (sesiones v2, frente A).

Por qué existe: la carpeta de tus pestañas (`STATE/sessions/<nombre>/`) se
elegía en cada cerebro con `<cerebro>/.claude/socio.local`. Ese archivo vive en
una carpeta con punto: Obsidian no lo sube (cada máquina tiene el suyo, o
ninguno) e iCloud, Dropbox o git sí (la otra persona hereda el tuyo). Sin él,
Workspace tomaba «la única carpeta» que hubiera, fuera de quien fuera: una
máquina te mostraba las pestañas de otra persona. Y las cédulas (usuarios.py)
son de cada cerebro: unir dos nombres tuyos en uno no los unía en los demás.

Principio rector: lo de la máquina va al estado de Workspace; lo de la
pestaña, al cerebro. Quién eres es de la máquina:

    <state_dir>/identidad.json   (no viaja)
    {"version": 1,
     "persona": {"nombre": "ana-lopez", "alias": ["ana"]},
     "por_cerebro": {"c-<uuid>": "beto", "<realpath del cerebro>": "beto"},
     "origen": "migración: socio.local de 3 de 4 cerebro(s)",
     "no_unir": {"c-<uuid>": ["ana"]}}

  · persona       quién usa esta máquina, con sus otros nombres (alias).
  · por_cerebro   «soy yo en esta PC» (sección Usuarios) cuando en UN cerebro
                  eres otra persona. Se guarda con el id del cerebro y con su
                  ruta real (respaldo si el id cambiara).
  · no_unir       uniones automáticas que deshiciste en un cerebro (copia
                  local; el veto que viaja va en la cédula, `no_unir:`).

Resolución (sessions_registry.socio delega aquí):
  1. el override `por_cerebro`;
  2. la persona, contra las cédulas de ESE cerebro: su nombre siempre; un
     alias SOLO con evidencia de ese cerebro (nombres_validos): que una cédula
     de ese cerebro ya lo junte con tu nombre, o que esta máquina lo haya usado
     ahí (su socio.local, o ids / last_opened locales de pestañas de esa
     carpeta). Un alias aprendido en otro cerebro nunca basta: en un cerebro
     de equipo ese nombre puede ser otra persona;
  3. la carpeta con tu nombre (o la de un alias válido que ya exista); si no
     existe se crea al escribir: eres una persona nueva en ese cerebro;
  4. sin persona en la máquina: '' y sessions_registry usa el orden de antes
     (legado), sin «la única carpeta» si esa carpeta ya es de alguien.

Id del cerebro: `STATE/cerebro.md` (visible, viaja con cualquier sync), con
`id: c-<uuid>` en su frontmatter. No existía ninguno reutilizable: el
`agent.json` vive en `.workspace/` (carpeta con punto, no viaja) y el
frontmatter de BRAIN.md entraría al contexto del agente y rompería las
migraciones que comparan el texto de la plantilla. Se crea solo cuando hace
falta (al guardar un override), para no generar ruido ni choques de sync; si
un choque deja dos ids, todas las máquinas leen el menor.

Unión entre cerebros: si un cerebro tiene dos cédulas separadas que son la
persona (con la misma evidencia de arriba), se unen solas al abrir el agente
(usuarios.al_abrir), con las herramientas de unir de usuarios.py (pestañas a
la canónica, la versión más nueva gana y la otra queda en history/, el perfil
viejo a `_archivo/`), con respaldo en `<state_dir>/backups/identidad/` y una
línea con su deshacer. Guardas: no se une si la cédula a absorber tiene
pestañas marcadas con la cédula de otra persona, ni si alguna de las dos
lleva el veto `no_unir:` (lo deja deshacer, y viaja con el cerebro).
Deshacer usa un manifiesto por archivo: devuelve solo lo que la unión movió o
cambió y conserva todo lo escrito después.

`socio.local` se sigue escribiendo donde se escribía (las versiones viejas lo
leen: expandir → contraer), pero ya no manda.

Cero dependencias (stdlib, 3.9+). Mac, Windows y Linux. Falla-suave en todo lo
que corre al abrir.
"""
import copy
import datetime
import json
import os
import re
import shutil
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import paths as _paths  # noqa: E402  (SSOT del dir de estado)

VERSION = 1
ARCHIVO = "identidad.json"
#: El id del cerebro: un archivo visible (sin punto) que viaja con el cerebro.
ID_REL = ("STATE", "cerebro.md")
ID_RE = re.compile(r"^c-[0-9a-f]{12,32}$")
_ID_LINEA = re.compile(r"(?m)^id:[ \t]*(c-[0-9a-f]{12,32})[ \t]*$")
NOMBRE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")   # = usuarios.NOMBRE_RE
#: El socio genérico que ponen «Crear agente» o «Cargar» sin dueño
#: (install.GENERIC_SOCIO): sin pestañas es un marcador, no una persona.
_GENERICO = "owner"

_ID_TEXTO = """---
id: %s
---
# Este cerebro

Workspace usa este id para reconocer el cerebro en cada máquina aunque su
carpeta cambie de lugar (por ejemplo, para recordar quién eres en él). No lo
edites ni lo borres.
"""


# ── nombres ─────────────────────────────────────────────────────────────────
def _nombre(s):
    """Nombre de usuario saneado ('' si no es válido). Translitera igual que
    la sección Usuarios (usuarios.limpiar_nombre): «José María» → jose-maria,
    nunca «josmara» (antes se borraba lo que no era ASCII)."""
    try:
        import usuarios
        s = usuarios.limpiar_nombre(s)
    except Exception:
        import unicodedata
        s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^a-z0-9_-]+", "-", s.strip().lower()).strip("-_")[:32]
    return s if NOMBRE_RE.match(s) else ""


def _nombres(p):
    """[nombre, alias…] de una persona, sin repetir y en orden."""
    out = []
    for n in [p.get("nombre")] + list(p.get("alias") or []):
        n = _nombre(n)
        if n and n not in out:
            out.append(n)
    return out


# ── el store (state_dir/identidad.json) ─────────────────────────────────────
def ruta(state_dir=None):
    return os.path.join(state_dir or _paths.state_dir(), ARCHIVO)


def _vacio():
    return {"version": VERSION, "persona": {"nombre": "", "alias": []},
            "por_cerebro": {}, "origen": "", "no_unir": {}}


def _normalizar(raw):
    data = _vacio()
    if not isinstance(raw, dict):
        return data
    p = raw.get("persona") if isinstance(raw.get("persona"), dict) else {}
    nombre = _nombre(p.get("nombre"))
    alias = p.get("alias") if isinstance(p.get("alias"), list) else []
    if nombre:
        # el «owner» genérico nunca es un alias: es el marcador de cualquier
        # cerebro sin dueño y uniría a otra persona con la tuya
        data["persona"] = {"nombre": nombre,
                           "alias": [a for a in _nombres({"alias": alias})
                                     if a not in (nombre, _GENERICO)]}
    pc = raw.get("por_cerebro") if isinstance(raw.get("por_cerebro"), dict) else {}
    data["por_cerebro"] = {str(k): _nombre(v) for k, v in pc.items() if k and _nombre(v)}
    nu = raw.get("no_unir") if isinstance(raw.get("no_unir"), dict) else {}
    data["no_unir"] = {str(k): sorted({_nombre(x) for x in v if _nombre(x)})
                       for k, v in nu.items() if k and isinstance(v, list)}
    data["no_unir"] = {k: v for k, v in data["no_unir"].items() if v}
    data["origen"] = str(raw.get("origen") or "")[:200]
    return data


def cargar(state_dir=None):
    """identidad.json normalizado (vacío si no existe o no se puede leer)."""
    try:
        with open(ruta(state_dir), encoding="utf-8") as fh:
            return _normalizar(json.load(fh))
    except Exception:
        return _vacio()


def _escribir_texto(path, text):
    """Escritura atómica con reintentos (el camino de memoria: el mismo
    reintento ante el «Acceso denegado» de Windows; ver memoria._reemplazar)."""
    try:
        import memoria
        memoria._atomic(path, text)
        return
    except ImportError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def guardar(data, state_dir=None):
    """Escribe identidad.json (normalizado). Para leer-modificar-escribir,
    `_modificar` (con candado)."""
    path = ruta(state_dir)
    _escribir_texto(path, json.dumps(_normalizar(data), ensure_ascii=False, indent=2) + "\n")
    return path


def _modificar(cambio, state_dir=None):
    """Leer → `cambio(data)` → escribir, bajo el candado de identidad.json
    (dos procesos que abren agentes a la vez no se pisan). `cambio` devuelve
    el dict nuevo (o None = sin cambios). → (data, cambió)."""
    from olock import file_lock
    path = ruta(state_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with file_lock(path, timeout=5):
        antes = cargar(state_dir)
        nuevo = cambio(copy.deepcopy(antes))
        if nuevo is None:
            return antes, False
        nuevo = _normalizar(nuevo)
        if nuevo == antes and os.path.isfile(path):
            return antes, False
        guardar(nuevo, state_dir)
        return nuevo, True


def _respaldar_store(state_dir=None):
    """Copia de identidad.json antes de cambiar de persona (nada se pierde)."""
    path = ruta(state_dir)
    if not os.path.isfile(path):
        return ""
    d = os.path.join(state_dir or _paths.state_dir(), "backups", "identidad")
    os.makedirs(d, exist_ok=True)
    dest = _libre(os.path.join(d, "identidad-%s.json" % _sello()))
    shutil.copy2(path, dest)
    return dest


def persona(state_dir=None, data=None):
    """{"nombre", "alias"} de quien usa esta máquina, o None si no se sabe."""
    p = (data or cargar(state_dir))["persona"]
    return dict(p) if p.get("nombre") else None


def fijar_persona(nombre, alias=(), origen="", state_dir=None):
    """Quién usa esta máquina (install --socio, el onboarding, la migración,
    Usuarios cuando la máquina no lo sabía). Si ya es la misma persona (el
    nombre es el suyo o uno de sus alias), solo suma alias. Si es otra, la
    reemplaza (con respaldo del archivo anterior) y conserva los overrides.
    → la persona guardada. ValueError si el nombre no es válido."""
    n = _nombre(nombre)
    if not n:
        raise ValueError("Nombre inválido: usa letras, números y guiones (máx. 32)")
    extra = [a for a in _nombres({"alias": list(alias or ())}) if a != n]

    def cambio(data):
        p = data["persona"]
        if p["nombre"] and n in _nombres(p):
            p["alias"] = [a for a in _nombres({"alias": p["alias"] + extra + [n]})
                          if a != p["nombre"]]
            return data
        if p["nombre"]:
            _respaldar_store(state_dir)
        data["persona"] = {"nombre": n, "alias": extra}
        data["origen"] = str(origen or "")
        return data
    data, _ = _modificar(cambio, state_dir)
    return persona(data=data)


# ── id estable del cerebro (STATE/cerebro.md) ───────────────────────────────
def _id_path(brain):
    return os.path.join(brain, *ID_REL)


def brain_id(brain):
    """Id estable del cerebro ('' si no tiene). Si un choque de sync dejó dos
    ids en el archivo, todas las máquinas leen el MENOR (el mismo en todas)."""
    if not brain:
        return ""
    try:
        with open(_id_path(brain), "rb") as fh:
            texto = fh.read(8192).decode("utf-8", "replace").replace("\r\n", "\n")
    except OSError:
        return ""
    ids = _ID_LINEA.findall(texto)
    return min(ids) if ids else ""


def asegurar_id(brain):
    """El id del cerebro, creándolo si falta. '' si no se pudo (cerebro de solo
    lectura o sin STATE/): quien llama usa la ruta real como respaldo."""
    i = brain_id(brain)
    if i or not brain or not os.path.isdir(os.path.join(brain, "STATE")):
        return i
    try:
        import uuid
        from olock import local_lock
        with local_lock(_id_path(brain), timeout=5):
            i = brain_id(brain)
            if not i:
                _escribir_texto(_id_path(brain), _ID_TEXTO % ("c-" + uuid.uuid4().hex))
        return brain_id(brain)
    except Exception:
        return ""


def _ruta_real(brain):
    return os.path.normcase(os.path.realpath(brain or ""))


def claves(brain, crear=False):
    """Las claves de un cerebro en `por_cerebro`/`no_unir`: su id (si tiene;
    `crear` lo crea) y su ruta real (respaldo)."""
    i = asegurar_id(brain) if crear else brain_id(brain)
    return ([i] if i else []) + [_ruta_real(brain)]


def override(brain, data=None):
    """El «soy yo en esta PC» de este cerebro ('' si no hay)."""
    pc = (data or cargar())["por_cerebro"]
    if not pc:
        return ""
    for k in claves(brain):
        if pc.get(k):
            return pc[k]
    return ""


def fijar_override(brain, nombre, state_dir=None):
    n = _nombre(nombre)
    if not n:
        raise ValueError("Nombre inválido")
    ks = claves(brain, crear=True)

    def cambio(data):
        for k in ks:
            data["por_cerebro"][k] = n
        return data
    _modificar(cambio, state_dir)
    return n


def elegido(brain, nombre, state_dir=None):
    """Usuarios › «soy yo en esta PC» eligió a `nombre` en `brain`:
      · la máquina no sabía quién eres → esa es tu persona (pregunta una vez,
        vale para todos tus cerebros);
      · eres tú (tu persona ya cae en ese usuario aquí) → sin override;
      · es otra persona → override `por_cerebro` solo para este cerebro."""
    n = _nombre(nombre)
    if not n:
        raise ValueError("Nombre inválido")
    p = persona(state_dir)
    if not p:
        c = _en_cedulas(_cedulas(brain), n)
        fijar_persona(n, alias=(c["alias"] if c else ()), origen="usuarios: soy yo en esta PC",
                      state_dir=state_dir)
        quitar_override(brain, state_dir)
    elif en_cerebro(brain, p) == n:
        quitar_override(brain, state_dir)
    else:
        fijar_override(brain, n, state_dir)
    return n


def quitar_override(brain, state_dir=None):
    ks = claves(brain)

    def cambio(data):
        if not any(k in data["por_cerebro"] for k in ks):
            return None
        for k in ks:
            data["por_cerebro"].pop(k, None)
        return data
    return _modificar(cambio, state_dir)[1]


# ── resolver quién eres en un cerebro ───────────────────────────────────────
def _usuarios():
    import usuarios
    return usuarios


def _cedulas(brain):
    try:
        return _usuarios().cedulas(brain)
    except Exception:
        return []


def _en_cedulas(cs, q):
    """La cédula de `q` (nombre, id o alias), con la misma precedencia que
    usuarios.resolver: nombre o id exactos primero, luego alias."""
    for c in cs:
        if q == c["nombre"] or (c["id"] and q == c["id"]):
            return c
    for c in cs:
        if q in c["alias"]:
            return c
    return None


def _carpetas(brain):
    try:
        return _usuarios().carpetas(brain)
    except Exception:
        return []


def leer_socio_local(path):
    """(nombre, ilegible) de un `socio.local`. Se lee con errors="replace"
    (un archivo guardado en ANSI/Latin-1 no tumba nada); si trae bytes que no
    son UTF-8, el nombre NO se usa (ilegible=True): uno recortado («josé» →
    «jos») sería otra persona."""
    try:
        with open(path, "rb") as fh:
            crudo = fh.read(512)
    except OSError:
        return "", False
    texto = crudo.decode("utf-8", "replace")
    if "�" in texto:
        return "", True
    return _nombre(texto), False


def _socio_local(brain):
    """El `socio.local` de ESTE cerebro en ESTA máquina ('' si no hay o no se
    puede leer)."""
    if not brain:
        return ""
    return leer_socio_local(os.path.join(brain, ".claude", "socio.local"))[0]


def _locales(brain):
    """Las pestañas (slugs) de `brain` que ESTA máquina abrió: ids de motor o
    last_opened en su store local (sessions_registry). Falla-suave."""
    try:
        import sessions_registry as reg
        m = (reg._local_load().get("map") or {}).get(reg._brain_key(brain)) or {}
        return {sl for sl, slot in m.items() if isinstance(slot, dict) and any(slot.values())}
    except Exception:
        return set()


def _nombres_de(c):
    return {c["nombre"]} | set(c["alias"])


def nombres_validos(brain, p, cs=None):
    """Los nombres de la persona `p` que valen en `brain`, en su orden: su
    nombre siempre; un alias solo con evidencia de ESE cerebro:
      · del cerebro: una de sus cédulas ya junta ese alias con un nombre
        válido (allá alguien unió o renombró a la persona: `alias: […]`);
      · de esta máquina en ese cerebro: su `socio.local` dice ese nombre (o
        el de una cédula que lo trae), o esta máquina abrió pestañas de esa
        carpeta (ids o last_opened locales).
    Un alias aprendido en OTRO cerebro nunca basta: en un cerebro de equipo
    ese nombre puede ser otra persona. Falla-suave: sin evidencia, solo el
    nombre."""
    todos = _nombres(p)
    if len(todos) < 2 or not brain:
        return todos[:1]
    cs = _cedulas(brain) if cs is None else cs
    validos = todos[:1]
    presentes = set(_carpetas(brain))
    for c in cs:
        presentes |= _nombres_de(c)
    pendientes = [a for a in todos[1:] if a in presentes]
    if not pendientes:                        # ningún alias aparece aquí: nada que decidir
        return validos
    maquina = set()
    sl = _socio_local(brain)
    if sl:
        maquina.add(sl)
        c = _en_cedulas(cs, sl)
        if c:
            maquina |= _nombres_de(c)
    if any(a not in maquina for a in pendientes):
        loc = _locales(brain)
        if loc:
            u = _usuarios()
            for a in pendientes:
                try:
                    if a not in maquina and any(f[:-3] in loc for f in u.pestanas(brain, a)):
                        maquina.add(a)
                except Exception:
                    continue
    cambio = True
    while cambio:
        cambio = False
        for a in pendientes:
            if a in validos:
                continue
            if a in maquina or any(a in _nombres_de(c) and _nombres_de(c) & set(validos)
                                   for c in cs):
                validos.append(a)
                cambio = True
    return [n for n in todos if n in validos]


def en_cerebro(brain, p, cs=None):
    """El nombre con que la persona `p` vive en `brain`: la cédula de uno de
    sus nombres VÁLIDOS ahí (nombres_validos: el suyo y luego los alias con
    evidencia), la carpeta de uno de ellos, o su nombre (la carpeta se crea
    al escribir)."""
    cs = _cedulas(brain) if cs is None else cs
    nombres = nombres_validos(brain, p, cs)
    for n in nombres:
        c = _en_cedulas(cs, n)
        if c:
            return c["nombre"]
    carps = _carpetas(brain)
    for n in nombres:
        if n in carps:
            return n
    return nombres[0] if nombres else ""


def socio(brain, data=None):
    """Quién eres en `brain` según esta máquina ('' si la máquina no lo sabe:
    sessions_registry cae entonces al orden de antes)."""
    if not brain or not os.path.isdir(brain):
        return ""
    data = data or cargar()
    ov = override(brain, data)
    if ov:
        c = _en_cedulas(_cedulas(brain), ov)
        return c["nombre"] if c else ov
    p = data["persona"]
    if not p["nombre"]:
        return ""
    return en_cerebro(brain, p)


def socio_maquina_legado(state_dir=None):
    """El `socio.local` de la MÁQUINA (lo escribía `install --socio`), ''
    si no hay o no se puede leer. Solo para el orden de antes y la migración."""
    return leer_socio_local(os.path.join(state_dir or _paths.state_dir(), "socio.local"))[0]


def es_de_alguien(brain, carpeta):
    """¿La carpeta de sesiones `carpeta` ya es de una persona concreta (tiene
    cédula por nombre o alias)? Lo usa el orden de antes para no tomar la
    carpeta de otra persona como tuya."""
    return _en_cedulas(_cedulas(brain), _nombre(carpeta)) is not None


# ── aprender: los nombres que la persona tiene en cada cerebro ──────────────
def aprender(brain, state_dir=None, seguir=False):
    """La persona suma los nombres que tiene en este cerebro: los alias de su
    cédula (y su nombre aquí) pasan a ser alias suyos. Así unir dos nombres
    tuyos en un cerebro los une en todos. `seguir` (solo tras un renombre o
    una unión que hiciste TÚ en Usuarios): si tu nombre quedó como alias de
    otra cédula, tomas el nombre nuevo. Lo automático nunca cambia el nombre
    (dos cerebros que unieron en sentidos distintos lo harían ir y venir).
    Con override no se aprende (en este cerebro puedes ser otra persona).
    → True si cambió algo."""
    data = cargar(state_dir)
    p = data["persona"]
    if not p["nombre"] or not brain or override(brain, data):
        return False
    cs = _cedulas(brain)
    nombre = en_cerebro(brain, p, cs)
    c = next((x for x in cs if x["nombre"] == nombre and not x["ilegible"]), None)
    if not c:
        return False
    suyo = c["nombre"] if seguir and p["nombre"] in c["alias"] else p["nombre"]
    alias = [a for a in _nombres({"alias": p["alias"] + [p["nombre"], c["nombre"]] + c["alias"]})
             if a not in (suyo, _GENERICO)]
    if suyo == p["nombre"] and set(alias) == set(p["alias"]):
        return False

    def cambio(d):
        if d["persona"]["nombre"] != p["nombre"]:
            return None                       # otro proceso la cambió mientras
        d["persona"] = {"nombre": suyo, "alias": alias}
        return d
    return _modificar(cambio, state_dir)[1]


# ── unión entre cerebros ────────────────────────────────────────────────────
def mias(brain, p=None, cs=None):
    """Las cédulas de `brain` que son la persona: alguno de sus nombres
    VÁLIDOS en ese cerebro (nombres_validos) es el nombre o un alias de la
    cédula."""
    p = p or persona()
    if not p:
        return []
    cs = _cedulas(brain) if cs is None else cs
    validos = set(nombres_validos(brain, p, cs))
    return [c for c in cs if _nombres_de(c) & validos]


def _canonica(brain, cands):
    """La cédula que queda al unir: la de más pestañas (empate: revisión más
    alta, luego el nombre). Solo cuenta lo que hay en el cerebro, nunca lo de
    la máquina: dos máquinas con el mismo cerebro unen en el MISMO sentido
    aunque cada una te conozca por otro nombre."""
    u = _usuarios()
    return min(cands, key=lambda c: (-len(u.pestanas(brain, c["nombre"])),
                                     -c["revision"], c["nombre"]))


def _ajena(brain, origen, destino):
    """La cédula de otra persona que marca alguna pestaña de `origen` ('' si
    ninguna): la guarda de la unión automática."""
    u = _usuarios()
    propias = {"", origen["id"], destino["id"]}
    for f in u.pestanas(brain, origen["nombre"]):
        try:
            with open(os.path.join(brain, "STATE", "sessions", origen["nombre"], f), "rb") as fh:
                cabeza = fh.read(4096).decode("utf-8", "replace").replace("\r\n", "\n")
        except OSError:
            continue
        sid = u._socio_id_de(cabeza)
        if sid not in propias:
            return sid
    return ""


def _sello():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _libre(path):
    if not os.path.lexists(path):
        return path
    root, ext = os.path.splitext(path)
    k = 2
    while os.path.lexists("%s-%d%s" % (root, k, ext)):
        k += 1
    return "%s-%d%s" % (root, k, ext)


def _respaldos_dir(state_dir=None):
    return os.path.join(state_dir or _paths.state_dir(), "backups", "identidad")


# ── el veto que viaja (no_unir: en la cédula) ───────────────────────────────
def _veto(c):
    """Los nombres con que esta cédula NO se une sola: `no_unir:` en su
    frontmatter (lo escribe deshacer; viaja con el cerebro, así la otra
    máquina tampoco vuelve a unir)."""
    v = (c.get("extra") or {}).get("no_unir") or []
    if isinstance(v, str):
        v = [v]
    return {_nombre(x) for x in v if _nombre(x)}


def _vetada(a, b):
    return bool(_veto(a) & _nombres_de(b) or _veto(b) & _nombres_de(a))


def _poner_veto(ruta, nombres):
    """Suma `nombres` al `no_unir:` del perfil `ruta`. Cambia solo ese
    renglón del frontmatter; lo demás queda byte a byte (con su BOM y sus
    saltos de línea). → True si quedó escrito."""
    u = _usuarios()
    texto, forma = u._leer_perfil(ruta)
    if texto is None:
        return False
    renglones, resto = u._frontmatter(texto)
    if renglones is None:
        return False
    actual, out = set(), []
    for clave, bloque in u._bloques(renglones):
        if clave == "no_unir":
            v, _ok = u._valor(bloque)
            actual |= set(v if isinstance(v, list) else ([v] if v else []))
            continue
        out.extend(bloque)
    lista = sorted({_nombre(x) for x in actual | set(nombres) if _nombre(x)})
    out.append("no_unir: [%s]" % ", ".join(lista))
    nuevo = "---\n" + "\n".join(out) + resto
    if forma.get("crlf"):
        nuevo = nuevo.replace("\n", "\r\n")
    u._atomic(ruta, ("﻿" if forma.get("bom") else "") + nuevo)
    return True


# ── fotos por archivo (para deshacer solo lo que hizo la unión) ─────────────
def _sha_archivo(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for trozo in iter(lambda: fh.read(1 << 16), b""):
            h.update(trozo)
    return h.hexdigest()


def _zonas(brain, cands):
    """Lo que una unión puede tocar (relativo al cerebro, con /)."""
    out = []
    for c in cands:
        for rel in ("STATE/sessions/" + c["nombre"],
                    os.path.relpath(c["ruta"], brain).replace(os.sep, "/"),
                    "motores/claude-code/memoria/" + c["nombre"]):
            if rel not in out:
                out.append(rel)
    out.append("STATE/users/_archivo")
    return out


def _foto(brain, zonas):
    """{ruta relativa: sha256} de cada archivo dentro de las `zonas`."""
    out = {}
    for z in zonas:
        p = _abs(brain, z)
        if os.path.isfile(p) and not os.path.islink(p):
            out[z] = _sha_archivo(p)
            continue
        for dp, _dns, fns in os.walk(p):
            for f in fns:
                q = os.path.join(dp, f)
                if os.path.isfile(q) and not os.path.islink(q):
                    out[_rel(brain, q)] = _sha_archivo(q)
    return out


def _rel(brain, path):
    return os.path.relpath(path, brain).replace(os.sep, "/")


def _abs(brain, rel):
    partes = str(rel or "").split("/")
    if not rel or ".." in partes or os.path.isabs(str(rel)):
        raise ValueError("ruta fuera del cerebro: %s" % rel)
    return os.path.join(brain, *partes)


def _leer_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _escribir_bytes(path, datos):
    """Escritura atómica con reintento (atomico, el helper común)."""
    try:
        import atomico
    except ImportError:
        import memoria
        memoria._atomic(path, datos)
        return
    atomico.escribir(path, datos)


def _mover(src, dst):
    """Mueve un archivo sin perderlo jamás: `os.replace` (atómico en el mismo
    disco) con los reintentos de atomico ante los errores pasajeros de
    Windows; entre discos distintos, copia completa y después quita el
    original. Nunca pisa (`dst` no debe existir) y nunca borra `src` si no
    llegó a `dst`."""
    import errno
    import time
    if os.path.lexists(dst):
        raise FileExistsError(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        import atomico
        intentos, pasajero = atomico.intentos_por_defecto(), atomico.pasajero
    except ImportError:
        intentos, pasajero = 3, (lambda e: isinstance(e, PermissionError))
    for k in range(intentos):
        try:
            os.replace(src, dst)
            return dst
        except OSError as e:
            if getattr(e, "errno", None) == errno.EXDEV:
                shutil.copy2(src, dst)
                os.remove(src)
                return dst
            if k < intentos - 1 and pasajero(e):
                time.sleep(0.05 * (k + 1))
                continue
            raise


def _respaldar_union(brain, cands, state_dir=None):
    """Copia ENTERA, archivo por archivo, de lo que la unión va a tocar, fuera
    del cerebro (no viaja ni duplica pestañas en otras máquinas), y su foto
    (sha256 de cada archivo). → (carpeta, manifiesto)."""
    base = re.sub(r"[^A-Za-z0-9]+", "-", os.path.basename(os.path.realpath(brain))).strip("-")
    dest = _libre(os.path.join(_respaldos_dir(state_dir), "%s-%s" % (_sello(), base or "cerebro")))
    os.makedirs(dest)
    zonas = _zonas(brain, cands)
    antes = _foto(brain, zonas)
    for rel in antes:
        dst = os.path.join(dest, "antes", *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(_abs(brain, rel), dst)
    man = {"version": 2, "cerebro": os.path.realpath(brain), "id": brain_id(brain),
           "fecha": datetime.datetime.now().isoformat(timespec="seconds"),
           "unidas": [], "cedulas": {}, "zonas": zonas, "antes": antes,
           "despues": None, "movidas": [], "socio_local": {}}
    _guardar_manifiesto(dest, man)
    return dest, man


def _guardar_manifiesto(dest, man):
    _escribir_texto(os.path.join(dest, "manifiesto.json"),
                    json.dumps(man, ensure_ascii=False, indent=2) + "\n")


class Lote(object):
    """UN respaldo y UN `deshacer` para todo lo que junta una apertura: las
    pestañas de un nombre viejo que usuarios.asegurar pasa a su dueño y la
    unión de cédulas de unir_persona. La foto se toma ANTES del primer
    movimiento (antes asegurar movía primero y la foto de la unión llegaba
    tarde: deshacer devolvía la cédula pero no las pestañas). Perezoso: si
    nada se mueve, no escribe nada."""

    def __init__(self, brain, state_dir=None):
        self.brain, self.state_dir = brain, state_dir
        self.dest, self.man, self.registro = "", None, []

    def abrir(self, cands):
        """Foto y copia de lo que pueden tocar `cands` ([{nombre, ruta}])
        ANTES de tocarlo. Si el lote ya estaba abierto, suma solo lo nuevo."""
        if self.man is None:
            self.dest, self.man = _respaldar_union(self.brain, cands, self.state_dir)
            self.man["socio_local"]["antes"] = _socio_local(self.brain)
            return self
        nuevas = [z for z in _zonas(self.brain, cands) if z not in self.man["zonas"]]
        if nuevas:
            foto = _foto(self.brain, nuevas)
            for rel, sha in foto.items():
                if rel in self.man["antes"]:
                    continue
                dst = os.path.join(self.dest, "antes", *rel.split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(_abs(self.brain, rel), dst)
                self.man["antes"][rel] = sha
            self.man["zonas"] += nuevas
            _guardar_manifiesto(self.dest, self.man)
        return self

    def unida(self, origen, destino, ced_id="", ruta=""):
        """Anota que `origen` pasó a `destino` (una vez por par)."""
        if [origen, destino] not in self.man["unidas"]:
            self.man["unidas"].append([origen, destino])
        if ced_id or origen not in self.man["cedulas"]:
            self.man["cedulas"][origen] = {"id": ced_id, "ruta": ruta}

    def tiene(self, origen, destino):
        return self.man is not None and [origen, destino] in self.man["unidas"]

    def cerrar(self):
        """Guarda el manifiesto con lo que pasó (movimientos y foto de
        después). → la carpeta del respaldo, o '' si no se movió nada."""
        if self.man is None:
            return ""
        self.man["movidas"] = [[_rel(self.brain, a), _rel(self.brain, b)]
                               for a, b in self.registro]
        self.man["despues"] = _foto(self.brain, self.man["zonas"])
        self.man["socio_local"]["despues"] = _socio_local(self.brain)
        _guardar_manifiesto(self.dest, self.man)
        return self.dest


def unir_persona(brain, state_dir=None, lote=None):
    """Si en `brain` hay dos o más cédulas que son la persona de esta máquina
    (mias: solo con evidencia de ESE cerebro), las une en la canónica
    (_canonica). Respaldo y foto de lo que se va a tocar antes de tocarlo;
    guardas de cédulas ajenas y del veto `no_unir:`; nada se borra. `lote`
    (Lote): el de la apertura, si usuarios.asegurar ya movió algo en ella;
    todo queda en el mismo respaldo y se deshace junto.
    → {"unidas": [(origen, destino, n)], "bloqueadas": [(origen, destino,
    motivo)], "respaldo": carpeta o ''}."""
    rep = {"unidas": [], "bloqueadas": [], "respaldo": ""}
    if not brain or not os.path.isdir(os.path.join(brain, "STATE", "users")):
        return rep
    data = cargar(state_dir)
    p = data["persona"]
    if not p["nombre"] or override(brain, data):
        return rep                            # con override este cerebro es de quien elegiste
    vetados = set()
    for k in claves(brain):
        vetados |= set(data["no_unir"].get(k) or [])
    u = _usuarios()
    with u._lock(brain):
        cs = u.cedulas(brain)
        cands = [c for c in mias(brain, p, cs) if not c["ilegible"]]
        if len(cands) < 2:
            return rep
        canon = _canonica(brain, cands)
        van = []
        for o in sorted(cands, key=lambda c: c["nombre"]):
            if o is canon:
                continue
            if o["nombre"] in vetados or _vetada(o, canon):
                rep["bloqueadas"].append((o["nombre"], canon["nombre"], "deshecha"))
                continue
            if not o["entendido"] or not canon["entendido"]:
                rep["bloqueadas"].append((o["nombre"], canon["nombre"], "formato"))
                continue
            ajena = _ajena(brain, o, canon)
            if ajena:
                rep["bloqueadas"].append((o["nombre"], canon["nombre"], "ajena:" + ajena))
                continue
            van.append(o)
        if not van:
            return rep
        if lote is None or lote.brain != brain:
            lote = Lote(brain, state_dir)
        lote.abrir([canon] + van)
        rep["respaldo"] = lote.dest
        try:
            for o in van:
                try:
                    r = u._unir(brain, o["nombre"], canon["nombre"], lote.registro)
                except ValueError as e:
                    rep["bloqueadas"].append((o["nombre"], canon["nombre"], str(e)))
                    continue
                lote.unida(o["nombre"], canon["nombre"], o["id"], _rel(brain, o["ruta"]))
                rep["unidas"].append((o["nombre"], canon["nombre"],
                                      len(r["movidas"]) + len(r["dobles"]) + len(r["iguales"])))
        finally:                              # aunque algo falle a medias: deshacer sabe qué pasó
            lote.cerrar()
    if rep["unidas"]:
        try:
            aprender(brain, state_dir)        # la persona suma los nombres unidos
        except Exception:
            pass
    return rep


def _ultimo_respaldo(state_dir=None):
    d = _respaldos_dir(state_dir)
    try:
        nombres = sorted(os.listdir(d), reverse=True)
    except OSError:
        return ""
    for n in nombres:
        man = _leer_manifiesto(os.path.join(d, n))
        if man and man.get("unidas") and not man.get("deshecho"):
            return os.path.join(d, n)
    return ""


def _leer_manifiesto(carpeta):
    try:
        with open(os.path.join(carpeta, "manifiesto.json"), encoding="utf-8") as fh:
            man = json.load(fh)
        return man if isinstance(man, dict) else None
    except Exception:
        return None


def _reetiquetar(brain, path, man):
    """Una pestaña que vuelve a la carpeta de su usuario de antes recupera su
    `socio`/`socio_id` (la unión los había cambiado al del que quedaba)."""
    partes = _rel(brain, path).split("/")
    if len(partes) != 4 or partes[:2] != ["STATE", "sessions"] or not partes[3].endswith(".md"):
        return
    ced = (man.get("cedulas") or {}).get(partes[2]) or {}
    if not ced.get("id"):
        return
    u = _usuarios()
    try:
        u._reescribir_ficha(path, lambda t: u._con_socio_id(t, ced["id"], partes[2],
                                                            reemplazar=True))
    except Exception:
        pass


def deshacer(respaldo="", state_dir=None):
    """Deshace una unión automática (la última si no se dice cuál) con su
    manifiesto por archivo:
      1. lo que NO cambió desde la unión vuelve a como estaba (lo que la unión
         creó sale al respaldo: su contenido vuelve a su lugar en el paso 3);
      2. lo que la unión movió y TÚ cambiaste después vuelve a su lugar de
         antes CON lo nuevo;
      3. lo de antes que la unión movió o quitó se devuelve; si ese lugar ya
         está ocupado, con sufijo.
    Lo escrito después de la unión (notas, pestañas nuevas) se queda en el
    cerebro. Movimientos atómicos con reintento; nada se borra (lo que sale
    queda en `antes-de-deshacer/` del respaldo). El veto `no_unir:` queda en la
    cédula (viaja: la otra máquina tampoco vuelve a unir) y en esta máquina.
    → el manifiesto. ValueError si no hay nada que deshacer."""
    respaldo = respaldo or _ultimo_respaldo(state_dir)
    man = _leer_manifiesto(respaldo) if respaldo else None
    if not man or not man.get("unidas"):
        raise ValueError("No hay ninguna unión automática que deshacer")
    if man.get("deshecho"):
        raise ValueError("Esa unión ya se deshizo (%s)" % man["deshecho"])
    if man.get("version") != 2:
        raise ValueError("Esa unión es de una versión anterior: su copia completa está en %s"
                         % respaldo)
    brain = man.get("cerebro") or ""
    if not os.path.isdir(brain):
        raise ValueError("No encuentro el cerebro de esa unión: %s" % brain)
    antes = man.get("antes") or {}
    despues = man.get("despues") or {}

    def guardado(rel):
        return os.path.join(respaldo, "antes", *rel.split("/"))
    faltan = [r for r in antes if not os.path.isfile(guardado(r))]
    if faltan:
        raise ValueError("El respaldo está incompleto (%s): no deshago nada" % faltan[0])
    origen_de = {b: a for a, b in man.get("movidas") or []}
    por_sha = {}                              # lo que la unión movió sin anotarlo (memoria)
    for rel, sha in antes.items():
        if rel not in despues:
            por_sha.setdefault(sha, rel)
    for rel, sha in despues.items():
        if rel not in antes and rel not in origen_de and sha in por_sha:
            origen_de[rel] = por_sha[sha]
    aparte = _libre(os.path.join(respaldo, "antes-de-deshacer"))
    res = {"devueltos": [], "conservados": [], "con_sufijo": [], "apartados": []}
    u = _usuarios()
    with u._lock(brain):
        ahora = _foto(brain, man.get("zonas") or [])
        volver = []
        for rel, sha in sorted(ahora.items()):          # 1
            if despues.get(rel) == sha:
                if rel in antes:
                    if antes[rel] != sha:
                        _escribir_bytes(_abs(brain, rel), _leer_bytes(guardado(rel)))
                else:
                    _mover(_abs(brain, rel), os.path.join(aparte, *rel.split("/")))
                    res["apartados"].append(rel)
            elif rel in despues and rel in origen_de:
                volver.append(rel)
            else:
                res["conservados"].append(rel)
        llenos = set()
        for rel in volver:                              # 2
            ori = origen_de[rel]
            dst = _abs(brain, ori)
            if os.path.lexists(dst):
                dst = _libre(dst)
                res["con_sufijo"].append(_rel(brain, dst))
            _mover(_abs(brain, rel), dst)
            llenos.add(ori)
            _reetiquetar(brain, dst, man)
            res["conservados"].append(_rel(brain, dst))
        vaciados = set(volver)
        for rel, sha in sorted(antes.items()):          # 3
            if rel in llenos:
                continue
            dst = _abs(brain, rel)
            if os.path.lexists(dst):
                if os.path.isfile(dst) and _sha_archivo(dst) == sha:
                    continue
                if rel in despues and rel not in vaciados:
                    continue                            # ya resuelto en el paso 1
                dst = _libre(dst)
                res["con_sufijo"].append(_rel(brain, dst))
            elif rel in despues and rel not in vaciados:
                continue                                # lo quitaste tú después de la unión
            _escribir_bytes(dst, _leer_bytes(guardado(rel)))
            res["devueltos"].append(rel)
        sl = man.get("socio_local") or {}
        if sl.get("antes") and sl.get("antes") != sl.get("despues") \
                and _socio_local(brain) == sl.get("despues"):
            try:
                u._atomic(u._socio_local(brain), sl["antes"])
            except OSError:
                pass
        cs = u.cedulas(brain)
        for o, d in man["unidas"]:                      # el veto que viaja
            c = next((x for x in cs if x["nombre"] == o), None)
            try:
                if c:
                    _poner_veto(c["ruta"], [d])
                else:       # un nombre viejo sin cédula propia: en la de destino
                    c = next((x for x in cs if x["nombre"] == d), None)
                    if c:
                        _poner_veto(c["ruta"], [o])
            except (OSError, ValueError):
                pass
    origenes = [o for o, _d in man["unidas"]]
    ks = claves(brain)

    def cambio(data):
        for k in ks:
            data["no_unir"][k] = sorted(set(data["no_unir"].get(k) or []) | set(origenes))
        return data
    _modificar(cambio, state_dir)
    man["deshecho"] = datetime.datetime.now().isoformat(timespec="seconds")
    man["resultado"] = res
    _guardar_manifiesto(respaldo, man)
    return man


def comando(*args):
    """El comando EXACTO para correr este módulo (sirve desde cualquier
    carpeta; en PowerShell una ruta entre comillas necesita `& `)."""
    try:   # con el lanzador instalado, el comando corto (ya ruteado en front.py)
        import shutil
        if shutil.which("workspace"):
            return "workspace identidad" + "".join(" " + a for a in args)
    except Exception:
        pass
    cmd = '"%s" "%s"' % (sys.executable or "python3", os.path.join(_ROOT, "identidad.py"))
    cmd += "".join(" " + a for a in args)
    return ("& " + cmd) if os.name == "nt" else cmd


def al_abrir(brain, lote=None):
    """Lo que corre solo al abrir un agente (desde usuarios.al_abrir): la
    persona aprende los nombres que tiene aquí y sus cédulas duplicadas se
    unen (en el `lote` de la apertura, si lo hay). → [partes del aviso de
    una línea]. Jamás levanta."""
    partes = []
    try:
        aprender(brain)
    except Exception:
        pass
    try:
        rep = unir_persona(brain, lote=lote)
    except Exception:
        return partes
    for origen, destino, n in rep["unidas"]:
        if n:
            partes.append("«%s» y «%s» eran la misma persona (tú, en esta máquina): %d pestaña(s) "
                          "de «%s» pasaron a «%s» y nada se borró · deshacer: %s"
                          % (origen, destino, n, origen, destino, comando("deshacer")))
        else:   # las pestañas ya las movió usuarios (alias): sin repetir el conteo
            partes.append("«%s» y «%s» eran la misma persona (tú, en esta máquina): quedó «%s» "
                          "y nada se borró · deshacer: %s"
                          % (origen, destino, destino, comando("deshacer")))
    return partes


# ── construir la identidad desde lo que ya hay (migración y doctor) ─────────
def _unicos(cerebros):
    out, vistos = [], set()
    for item in cerebros or ():
        b = item[1] if isinstance(item, (tuple, list)) else item
        if not b or not os.path.isdir(b):
            continue
        k = _ruta_real(b)
        if k not in vistos:
            vistos.add(k)
            out.append(b)
    return out


def construir(cerebros, state_dir=None, errores=None):
    """La identidad de esta máquina a partir de lo que ya dice: el
    `socio.local` de cada cerebro registrado, resuelto por SUS cédulas. Los
    votos que comparten algún nombre son la misma persona; gana la que más
    cerebros declaran (empate: la de más pestañas). Sin ningún socio.local:
    el de la máquina (`install --socio`). Si la máquina ya tiene persona,
    esa es la que gana.

    Lo que cada cerebro ya decía NO se pierde: un cerebro cuyo socio.local es
    otra persona (fuera del grupo que gana) recibe un override `por_cerebro`
    con ella; también el «owner» genérico CON pestañas (sin pestañas es solo
    un marcador). Las claves son el id del cerebro si ya lo tiene y su ruta
    real: no se escribe nada en ningún cerebro.

    Un cerebro raro no detiene nada: su error se anota en `errores`
    [(cerebro, motivo)] y se sigue. → dict (persona, origen, por_cerebro y
    `_overrides` [[claves], nombre, cerebro]) o None si nada dice quién eres
    (no se adivina)."""
    u = _usuarios()
    errores = [] if errores is None else errores
    brains = _unicos(cerebros)
    votos, genericos = [], []
    for b in brains:
        try:
            s, ilegible = leer_socio_local(os.path.join(b, ".claude", "socio.local"))
            if ilegible:
                errores.append((b, "su socio.local no está en UTF-8: no lo usé"))
                continue
            if not s:
                continue
            if s == _GENERICO:
                if u.pestanas(b, s):
                    genericos.append(b)
                continue                          # marcador genérico: no es una persona
            c = _en_cedulas(_cedulas(b), s)
            nombre = c["nombre"] if c else s
            nombres = {s, nombre} | set(c["alias"] if c else [])
            votos.append({"cerebro": b, "nombre": nombre,
                          "nombres": {n for n in nombres if _nombre(n)},
                          "pestanas": len(u.pestanas(b, nombre))})
        except Exception as e:
            errores.append((b, "%s: %s" % (type(e).__name__, e)))
    data = _vacio()
    actual = cargar(state_dir)
    if actual["persona"]["nombre"]:
        data["persona"], data["origen"] = actual["persona"], actual["origen"]
        grupo = set(_nombres(actual["persona"]))
    else:
        origen = "migración: socio.local de %d de %d cerebro(s)"
        candidatos = list(votos)
        if not candidatos:
            s = socio_maquina_legado(state_dir)
            if s:
                candidatos = [{"cerebro": "", "nombre": s, "nombres": {s}, "pestanas": 0}]
                origen = "install --socio"
        grupo = set()
        if candidatos:
            grupos = []
            for v in candidatos:
                g = {"votos": [v], "nombres": set(v["nombres"])}
                for otro in [x for x in grupos if x["nombres"] & g["nombres"]]:
                    g["votos"] += otro["votos"]
                    g["nombres"] |= otro["nombres"]
                    grupos.remove(otro)
                grupos.append(g)
            gana = max(grupos, key=lambda g: (len(g["votos"]),
                                              sum(v["pestanas"] for v in g["votos"]),
                                              sorted(g["nombres"])[0]))
            cuenta = {}
            for v in gana["votos"]:
                k, t = cuenta.get(v["nombre"], (0, 0))
                cuenta[v["nombre"]] = (k + 1, t + v["pestanas"])
            nombre = sorted(cuenta, key=lambda n: (-cuenta[n][0], -cuenta[n][1], n))[0]
            alias = set(gana["nombres"])
            for b in brains:                      # sus otros nombres en cualquier cerebro
                try:
                    c = next((x for x in _cedulas(b) if x["nombre"] == nombre), None)
                except Exception:
                    c = None
                if c:
                    alias |= set(c["alias"])
            data["persona"] = _normalizar(
                {"persona": {"nombre": nombre, "alias": sorted(alias - {nombre})}})["persona"]
            data["origen"] = (origen % (len(gana["votos"]), len(candidatos))) if "%" in origen \
                else origen
            grupo = set(gana["nombres"]) | set(_nombres(data["persona"]))
    overrides = [(v["cerebro"], v["nombre"]) for v in votos
                 if v["cerebro"] and not (v["nombres"] & grupo)]
    if _GENERICO not in grupo:
        overrides += [(b, _GENERICO) for b in genericos]
    data["_overrides"] = []
    for b, n in overrides:
        try:
            data["_overrides"].append([claves(b), n, b])
        except Exception as e:
            errores.append((b, "%s: %s" % (type(e).__name__, e)))
    data["por_cerebro"] = {k: n for ks, n, _b in data["_overrides"] for k in ks}
    if not data["persona"]["nombre"] and not data["_overrides"]:
        return None
    return data


def _falta(data, prop):
    """Lo que `prop` (construir) agregaría a `data`: [persona?] + overrides."""
    if not prop:
        return []
    out = []
    if not data["persona"]["nombre"] and prop["persona"]["nombre"]:
        out.append(("persona", prop["persona"]["nombre"], ""))
    for ks, n, b in prop.get("_overrides") or []:
        if not any(k in data["por_cerebro"] for k in ks):
            out.append(("override", n, b))
    return out


def pendiente(prop, state_dir=None):
    """¿Falta algo de `prop` en identidad.json? (needed de la migración)."""
    return bool(_falta(cargar(state_dir), prop))


def aplicar(prop, state_dir=None):
    """Lo que falta de `prop` entra a identidad.json: la persona si no había
    y el override de cada cerebro que no tenga uno. Nunca pisa nada.
    → [(tipo, nombre, cerebro)] de lo agregado."""
    hecho = []

    def cambio(d):
        falta = _falta(d, prop)
        if not falta:
            return None
        if not d["persona"]["nombre"] and prop["persona"]["nombre"]:
            d["persona"], d["origen"] = prop["persona"], prop["origen"]
        for ks, n, _b in prop.get("_overrides") or []:
            if not any(k in d["por_cerebro"] for k in ks):
                for k in ks:
                    d["por_cerebro"][k] = n
        hecho[:] = falta
        return d
    _modificar(cambio, state_dir)
    return hecho


# ── diagnóstico (lo muestra `workspace doctor`) ─────────────────────────────
def diagnostico(cerebros, reparar=False, state_dir=None):
    """Hallazgos de identidad para el doctor: [{"estado": ok|fixed|warn,
    "tipo": …, "kw": {…}}]. `cerebros` = [(agente, ruta)]. Con `reparar`,
    construye la identidad si falta (con los overrides de construir) y une
    las cédulas duplicadas con la misma regla de evidencia que al abrir cada
    agente; sin él no escribe nada. Un cerebro raro se anota y se sigue."""
    out = []
    brains = [(n, b) for n, b in (cerebros or ()) if b and os.path.isdir(b)]
    agente = {_ruta_real(b): n for n, b in brains}
    data = cargar(state_dir)
    if not data["persona"]["nombre"] and reparar:
        errores = []
        prop = construir(brains, state_dir, errores)
        for b, msg in errores:
            out.append({"estado": "warn", "tipo": "error_cerebro",
                        "kw": {"agente": agente.get(_ruta_real(b), b), "error": msg}})
        for tipo, n, b in (aplicar(prop, state_dir) if prop else []):
            if tipo == "persona":
                out.append({"estado": "fixed", "tipo": "persona_creada", "kw": {"nombre": n}})
            else:
                out.append({"estado": "fixed", "tipo": "override",
                            "kw": {"agente": agente.get(_ruta_real(b), b), "nombre": n}})
        data = cargar(state_dir)
    p = data["persona"]
    ids = {}
    for name, b in brains:
        try:
            _diagnostico_cerebro(name, b, p, data, reparar, state_dir, out, ids)
        except Exception as e:
            out.append({"estado": "warn", "tipo": "error_cerebro",
                        "kw": {"agente": name, "error": "%s: %s" % (type(e).__name__, e)}})
    for i, names in sorted(ids.items()):
        if len(names) > 1:
            out.append({"estado": "warn", "tipo": "id_repetido",
                        "kw": {"agentes": ", ".join(sorted(names))}})
    if not any(x["estado"] != "ok" for x in out):
        if p["nombre"]:
            out.append({"estado": "ok", "tipo": "persona",
                        "kw": {"nombre": p["nombre"], "alias": ", ".join(p["alias"])}})
        else:
            out.append({"estado": "ok", "tipo": "sin_persona", "kw": {}})
    return out


def _diagnostico_cerebro(name, b, p, data, reparar, state_dir, out, ids):
    i = brain_id(b)
    if i:
        ids.setdefault(i, []).append(name)
    if not p["nombre"]:
        # sin identidad: solo importa el cerebro que ya tiene usuarios y no
        # sabe cuál eres tú (el orden de antes no adivina la carpeta de otra
        # persona): es lo que el preflight pregunta al abrirlo
        import sessions_registry
        if _carpetas(b) and not sessions_registry._socio_legado(b):
            out.append({"estado": "warn", "tipo": "no_sabe",
                        "kw": {"agente": name, "n": len(_carpetas(b))}})
        return
    if override(b, data):
        return
    cs = _cedulas(b)
    yo = en_cerebro(b, p, cs)
    sl = _socio_local(b)
    if sl:
        c = _en_cedulas(cs, sl)
        sl_nombre = c["nombre"] if c else sl
        if sl_nombre != yo and not (sl == _GENERICO and not _usuarios().pestanas(b, sl)) \
                and sl_nombre not in _nombres(p):
            out.append({"estado": "warn", "tipo": "otra_persona",
                        "kw": {"agente": name, "socio": sl_nombre, "nombre": yo}})
    dup = [c for c in mias(b, p, cs) if not c["ilegible"]]
    if len(dup) < 2:
        return
    canon = _canonica(b, dup)
    vetados = set()
    for k in claves(b):
        vetados |= set(data["no_unir"].get(k) or [])
    if all(o is canon or o["nombre"] in vetados or _vetada(o, canon) for o in dup):
        return                                # separadas a propósito (deshacer)
    if reparar:
        rep = unir_persona(b, state_dir)
        for o, d, n in rep["unidas"]:
            out.append({"estado": "fixed", "tipo": "unidas",
                        "kw": {"agente": name, "origen": o, "destino": d, "n": n,
                               "deshacer": comando("deshacer")}})
        for o, d, motivo in rep["bloqueadas"]:
            if motivo != "deshecha":
                out.append({"estado": "warn", "tipo": "bloqueada",
                            "kw": {"agente": name, "origen": o, "destino": d,
                                   "motivo": motivo}})
    else:
        out.append({"estado": "warn", "tipo": "duplicadas",
                    "kw": {"agente": name,
                           "nombres": ", ".join("«%s»" % c["nombre"]
                                                for c in sorted(dup, key=lambda c: c["nombre"]))}})


# ── CLI ─────────────────────────────────────────────────────────────────────
def _registrados():
    try:
        import migrate
        return migrate.Context().brains()
    except Exception:
        return []


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="identidad",
                                 description="Quién eres en esta máquina (en todos tus cerebros).")
    ap.add_argument("accion", nargs="?", default="ver", choices=("ver", "soy", "deshacer"))
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    try:
        if a.accion == "soy":
            if not a.args:
                raise ValueError("uso: identidad soy <tu-nombre>")
            p = fijar_persona(a.args[0], origen="identidad soy")
            print("✓ en esta máquina eres «%s»" % p["nombre"])
        elif a.accion == "deshacer":
            man = deshacer(a.args[0] if a.args else "")
            print("✓ deshecha la unión de %s en %s (lo que había quedó en el respaldo)"
                  % (", ".join("«%s» → «%s»" % (o, d) for o, d in man["unidas"]), man["cerebro"]))
            res = man.get("resultado") or {}
            print("  volvieron a su lugar: %d archivo(s)" % len(res.get("devueltos") or []))
            if res.get("con_sufijo"):
                print("  no pude dejar en su lugar exacto (ya estaba ocupado), quedaron con "
                      "sufijo: %s" % ", ".join(res["con_sufijo"]))
            if res.get("conservados"):
                print("  lo que cambiaste o escribiste después de la unión se quedó con lo "
                      "nuevo: %s" % ", ".join(res["conservados"]))
        else:
            data = cargar()
            p = data["persona"]
            print("en esta máquina eres: %s" % (("«%s»" % p["nombre"]) if p["nombre"]
                                                 else "(todavía no lo sé)"))
            if p["alias"]:
                print("  también: %s" % ", ".join(p["alias"]))
            for name, b in _registrados():
                print("  %s → %s" % (name, socio(b, data) or "—"))
        return 0
    except (ValueError, OSError) as e:
        print("✗ %s" % e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
