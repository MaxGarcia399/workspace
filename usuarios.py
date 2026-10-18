#!/usr/bin/env python3
"""WORKSPACE · usuarios — quién usa cada agente, con una «cédula» que no cambia
(2026-10-17; diseño: deliverables/workspace-motores/Usuarios_Con_ID_v1.html).

Por qué: la carpeta de un socio (`STATE/sessions/<nombre>/`) se elegía por
máquina con `.claude/socio.local`, que no viaja. El mismo humano quedó como
`max` en una máquina y `maxgarcia` en otra, cada uno con sus pestañas.

La solución: cada usuario tiene una CÉDULA en el frontmatter de su perfil
(`STATE/users/<nombre>.md`, que sí viaja con el cerebro):

    ---
    id: u-7f3a91          ← nunca cambia
    nombre: max           ← se puede cambiar (solo desde Workspace)
    alias: [maxgarcia]    ← nombres anteriores
    creado: 2026-10-16
    revision: 3           ← evita que dos cambios se pisen
    ---

y cada pestaña lleva la marca `socio_id: u-7f3a91`. El nombre de la carpeta es
solo una etiqueta: si una máquina todavía dice el nombre viejo, el alias de la
cédula la lleva al usuario correcto y no se crea nada nuevo.

Todo lo automático (dar cédula a lo que no tiene, marcar pestañas, corregir el
nombre de esta máquina) corre solo al abrir un agente; crear, renombrar, unir
y elegir «quién soy en esta PC» se hacen en la sección Usuarios del hub. Nada
se borra: lo que sobra va a `STATE/users/_archivo/` o a `history/`.

Cero dependencias (stdlib, 3.9+). Mac y Windows.
"""
import datetime
import hashlib
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

NOMBRE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
ID_RE = re.compile(r"^u-[0-9a-f]{6,12}$")
_CAMPOS = ("id", "nombre", "alias", "creado", "revision")


def _users_dir(brain):
    return os.path.join(brain, "STATE", "users")


def _sess_dir(brain):
    return os.path.join(brain, "STATE", "sessions")


def _leer(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().replace("\r\n", "\n")
    except OSError:
        return None


def _atomic(path, text):
    import memoria
    memoria._atomic(path, text)     # mismo camino: reintentos y modo sandbox


def _lock(brain):
    from olock import local_lock
    return local_lock(os.path.join(_users_dir(brain), ".usuarios"), timeout=10)


def _hoy():
    return datetime.date.today().isoformat()


def valido(nombre):
    return bool(NOMBRE_RE.match(str(nombre or "")))


def limpiar_nombre(texto):
    """«Ana María» → «ana-maria» (lo que se puede escribir en la sección)."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9_-]+", "-", s.strip().lower()).strip("-_")
    return s[:32]


# ── la cédula ───────────────────────────────────────────────────────────────
_CLAVE_RE = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*)$")
_ITEM_RE = re.compile(r"^\s*-(?:\s+(.*))?$")


def _frontmatter(text):
    """(renglones del frontmatter, resto desde el `---` de cierre) o (None, text)."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end == -1:
        return None, text
    return text[4:end].split("\n"), text[end:]


def _bloques(renglones):
    """[[clave | None, [renglones]]]: cada clave de primer nivel con sus
    renglones de continuación (indentados o `- item`); None = renglón suelto
    (comentario, vacío)."""
    out = []
    for ln in renglones:
        m = _CLAVE_RE.match(ln)
        if m:
            out.append([m.group(1), [ln]])
        elif out and out[-1][0] and ln.strip() and (ln[:1] in (" ", "\t") or _ITEM_RE.match(ln)):
            out[-1][1].append(ln)
        else:
            out.append([None, [ln]])
    return out


def _valor(renglones):
    """(valor, entendido) de un bloque: `clave: valor`, `clave: [a, b]` o una
    lista de bloque (`clave:` + `  - a`). Otra forma → (None, False)."""
    v = _CLAVE_RE.match(renglones[0]).group(2).strip()
    cont = renglones[1:]
    if not cont:
        if v.startswith("[") and v.endswith("]"):
            return [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()], True
        return v, True
    items = [_ITEM_RE.match(c) for c in cont]
    if v == "" and all(items):
        return [(m.group(1) or "").strip().strip("'\"") for m in items], True
    return None, False


def separar(text):
    """(frontmatter dict | None, cuerpo). Entiende `clave: valor`, listas
    `[a, b]` y listas de bloque; lo que no entiende queda como ''."""
    text = text or ""
    renglones, resto = _frontmatter(text)
    if renglones is None:
        return None, text
    nl = resto.find("\n", 4)
    cuerpo = resto[(nl + 1) if nl != -1 else len(resto):]
    data = {}
    for clave, bloque in _bloques(renglones):
        if clave:
            v, _ok = _valor(bloque)
            data[clave] = "" if v is None else v
    return data, cuerpo


def _no_entendidas(text):
    """Claves del frontmatter con una forma que separar() no entiende."""
    renglones, _resto = _frontmatter(text or "")
    return {c for c, b in _bloques(renglones or []) if c and not _valor(b)[1]}


def _linea(clave, v):
    if isinstance(v, (list, tuple)):
        v = "[" + ", ".join(v) + "]"
    return "%s: %s" % (clave, v)


def _poner_campos(text, valores):
    """`text` con las claves de `valores` en su frontmatter. Solo cambian los
    renglones de esas claves (las que faltan entran junto a las otras de la
    cédula, en su orden); todo lo demás —listas,
    campos desconocidos, comentarios, cuerpo— queda byte a byte. Sin
    frontmatter, uno nuevo arriba del texto entero."""
    renglones, resto = _frontmatter(text)
    if renglones is None:
        return _fm(valores, text)
    bloques = _bloques(renglones)
    presentes = {c for c, _b in bloques if c in valores}
    # las que faltan van en el orden de _CAMPOS: antes de la primera presente
    # que les sigue, o detrás de la última (arriba de todo si no hay ninguna)
    faltan = [k for k in _CAMPOS if k in valores and k not in presentes]
    out, tras_ultima = [], 0
    for clave, bloque in bloques:
        if clave in valores:                   # (repetida: todas, gana la última al leer)
            for k in [k for k in faltan if _CAMPOS.index(k) < _CAMPOS.index(clave)]:
                out.append(_linea(k, valores[k]))
                faltan.remove(k)
            v, _ok = _valor(bloque)
            iguales = v == valores[clave] or (
                not bloque[1:] and _linea(clave, v) == _linea(clave, valores[clave]))
            out.extend(bloque if iguales else [_linea(clave, valores[clave])])
            tras_ultima = len(out)
            continue
        out.extend(bloque)
    out[tras_ultima:tras_ultima] = [_linea(k, valores[k]) for k in faltan]
    return "---\n" + "\n".join(out) + resto


def _fm(data, cuerpo, extra_orden=()):
    lines = ["---"]
    for k in tuple(_CAMPOS) + tuple(k for k in data if k not in _CAMPOS):
        if k not in data:
            continue
        v = data[k]
        if isinstance(v, (list, tuple)):
            v = "[" + ", ".join(v) + "]"
        lines.append("%s: %s" % (k, v))
    lines.append("---")
    return "\n".join(lines) + "\n" + (cuerpo if cuerpo.startswith("\n") else "\n" + cuerpo)


def _leer_perfil(path):
    """(texto, forma) de un perfil, leído ESTRICTO (regla 2): sin BOM y con
    saltos `\\n`; forma = {"bom", "crlf"} para devolverlo igual al guardar.
    (None, "falta") si no existe o no se pudo abrir; (None, "ilegible") si no
    es UTF-8 (jamás se reescribe con «�»)."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None, "falta"
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw[3 if bom else 0:].decode("utf-8")
    except UnicodeDecodeError:
        return None, "ilegible"
    return text.replace("\r\n", "\n"), {"bom": bom, "crlf": b"\r\n" in raw}


def leer_cedula(path):
    """→ dict con id, nombre, alias (lista), creado, revision (int), ruta y
    cuerpo; id '' si el perfil todavía no tiene cédula. `entendido` = sus
    campos de cédula tienen una forma que Workspace sabe reescribir;
    `ilegible` = no es UTF-8 (lo de arriba sale de sus renglones ASCII y
    jamás se reescribe: asegurar() lo aparta)."""
    text, forma = _leer_perfil(path)
    ilegible = forma == "ilegible"
    if ilegible:
        with open(path, "rb") as fh:          # solo para rescatar la cédula (ASCII)
            raw = fh.read()
        text = raw[3 if raw.startswith(b"\xef\xbb\xbf") else 0:].decode("latin-1")
        text = text.replace("\r\n", "\n")
    elif text is None:
        return None
    data, cuerpo = separar(text)
    data = data or {}
    raras = _no_entendidas(text)
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    alias = data.get("alias") or []
    if isinstance(alias, str):
        alias = [alias] if alias else []
    try:
        rev = int(data.get("revision") or 0)
    except ValueError:
        rev = 0
    ced_id = str(data.get("id") or "")
    return {"id": ced_id if ID_RE.match(ced_id) else "",
            "nombre": str(data.get("nombre") or stem).lower(),
            "alias": [a.lower() for a in alias if valido(a.lower())],
            "creado": str(data.get("creado") or ""), "revision": rev,
            "ruta": path, "cuerpo": cuerpo, "extra": {k: v for k, v in data.items()
                                                       if k not in _CAMPOS},
            "texto": None if ilegible else text, "forma": None if ilegible else forma,
            "ilegible": ilegible, "entendido": not ilegible and not (raras & set(_CAMPOS))}


def _guardar_cedula(ced):
    """Escribe la cédula. Un perfil que ya existe cambia SOLO en los renglones
    de la cédula (_poner_campos), con su BOM y sus saltos de línea; uno que
    Workspace no entiende no se escribe jamás (ValueError, _editable).
    `creado` solo se escribe si se conoce: lo automático no pone la fecha del
    día (dos máquinas escribirían bytes distintos en el mismo perfil)."""
    valores = {"id": ced["id"], "nombre": ced["nombre"], "alias": ced["alias"],
               "revision": ced["revision"]}
    if ced.get("creado"):
        valores["creado"] = ced["creado"]
    _editable(ced)
    texto = ced.get("texto")
    if texto is None:                          # perfil nuevo
        data = dict(ced.get("extra") or {})
        data.update(valores)
        _atomic(ced["ruta"], _fm(data, ced["cuerpo"]))
        return
    nuevo = _poner_campos(texto, valores)
    forma = ced.get("forma") or {}
    if forma.get("crlf"):
        nuevo = nuevo.replace("\n", "\r\n")
    _atomic(ced["ruta"], ("\ufeff" if forma.get("bom") else "") + nuevo)


def _editable(ced):
    """ValueError si Workspace no puede reescribir este perfil sin perder algo
    (no es UTF-8, o sus campos de cédula tienen una forma que no entiende).
    Se llama ANTES de mover nada: renombrar/unir no quedan a medias."""
    if ced.get("ilegible") or ced.get("entendido") is False:
        raise ValueError("El perfil de «%s» (%s) tiene un formato que Workspace no entiende: "
                         "no lo toco" % (ced.get("nombre"), os.path.basename(ced["ruta"])))


def _apartar_ilegible(brain, c):
    """Regla 2: el perfil que no es UTF-8 se aparta ENTERO
    (`<nombre>.md.danado-<fecha>`) y en su lugar queda uno legible con la MISMA
    cédula (rescatada de sus renglones ASCII). → nombre del apartado."""
    import datetime as _dt
    ruta = c["ruta"]
    danado = _destino_libre(ruta + ".danado-" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.replace(ruta, danado)
    nuevo = {"id": c["id"], "nombre": c["nombre"], "alias": c["alias"],
             "creado": c["creado"], "revision": c["revision"] + 1, "ruta": ruta, "extra": {},
             "cuerpo": _PERFIL.format(titulo=c["nombre"].capitalize())
             + "\n> El perfil anterior no se pudo leer (no está en UTF-8): quedó entero en "
               "`%s`.\n" % os.path.basename(danado)}
    _guardar_cedula(nuevo)
    return os.path.basename(danado)


def _nuevo_id(usados, nombre=""):
    """Cédula nueva para `nombre`, DETERMINISTA (regla 4): el mismo cerebro vive
    en varias máquinas y cada una le da cédula a lo que no la tiene al abrir el
    agente, a veces antes de sincronizarse. Al azar, cada máquina le daba otra
    al mismo usuario y, tras sincronizar, el perfil quedaba con la de una y sus
    pestañas con la de la otra (QA de cerebros compartidos, 2026-10-18). Si ya
    está en `usados` (otro usuario se llamó así antes), la siguiente de la serie."""
    base = "workspace-usuario:" + str(nombre or "").strip().lower()
    k = 0
    while True:
        semilla = base if k == 0 else "%s:%d" % (base, k)
        i = "u-" + hashlib.sha256(semilla.encode("utf-8")).hexdigest()[:6]
        if i not in usados:
            return i
        k += 1


def cedulas(brain):
    """Los perfiles de STATE/users/ (sin README ni _/.), con o sin cédula."""
    d = _users_dir(brain)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    out = []
    for n in names:
        if not n.lower().endswith(".md") or n.lower() == "readme.md" or n.startswith(("_", ".")):
            continue
        c = leer_cedula(os.path.join(d, n))
        if c:
            out.append(c)
    return out


def carpetas(brain):
    try:
        return sorted(x for x in os.listdir(_sess_dir(brain))
                      if os.path.isdir(os.path.join(_sess_dir(brain), x))
                      and not x.startswith(("_", ".")) and valido(x))
    except OSError:
        return []


def pestanas(brain, nombre):
    d = os.path.join(_sess_dir(brain), nombre)
    try:
        return sorted(f for f in os.listdir(d) if f.endswith(".md") and f != "README.md"
                      and os.path.isfile(os.path.join(d, f)))
    except OSError:
        return []


# ── resolver nombres ────────────────────────────────────────────────────────
def resolver(brain, quien):
    """Nombre ACTUAL del usuario `quien` (su nombre, un alias viejo o su id).
    '' si no hay cédula que lo reconozca."""
    q = str(quien or "").strip().lower()
    if not q or not brain or not os.path.isdir(_users_dir(brain)):
        return ""
    cs = cedulas(brain)
    for c in cs:
        if q == c["nombre"] or (c["id"] and q == c["id"]):
            return c["nombre"]
    for c in cs:
        if q in c["alias"]:
            return c["nombre"]
    return ""


def _socio_local(brain):
    return os.path.join(brain, ".claude", "socio.local")


def socio_actual(brain, arreglar=True):
    """Quién es el socio en esta máquina para este cerebro. Si su
    `.claude/socio.local` todavía dice un nombre viejo (alias), se corrige
    solo al actual (`arreglar`): así el resto de Workspace, que lee ese
    archivo, ya ve el nombre bueno."""
    s = re.sub(r"[^a-z0-9_-]", "", (_leer(_socio_local(brain)) or "").strip().lower())
    if not s:
        return ""
    actual = resolver(brain, s)
    if actual and actual != s and arreglar:
        try:
            _atomic(_socio_local(brain), actual)
        except OSError:
            pass
        return actual
    return actual or s


def elegir(brain, quien):
    """«Soy yo» en esta PC: escribe el nombre actual en .claude/socio.local
    (solo de esta máquina; nunca se escribe a mano)."""
    nombre = resolver(brain, quien) or str(quien or "").lower()
    if not valido(nombre) or (nombre not in carpetas(brain) and not resolver(brain, nombre)):
        raise ValueError("No hay un usuario «%s» en este agente" % quien)
    _atomic(_socio_local(brain), nombre)
    return nombre


# ── lo automático: cédulas y marcas ─────────────────────────────────────────
_PERFIL = ("# {titulo} — cómo trabajar conmigo\n\n"
           "> Perfil creado por Workspace. El agente lo va completando con tus preferencias de trato\n"
           "> (corto, ~1500 caracteres).\n")


def _reescribir_ficha(p, cambio):
    """Reescribe una pestaña con el MISMO candado que usan las notas
    (memoria._lock): si no, una nota guardada mientras tanto se perdía
    (Greptile, 2026-10-17). `cambio(texto) → texto nuevo o None`. Lectura
    estricta: si no se pudo leer, no se escribe. → True si cambió."""
    import memoria
    with memoria._lock(p):
        try:
            text = memoria._leer(p)
        except memoria.Ilegible:             # no es UTF-8: no se toca (regla 2)
            return False
        nuevo = cambio(text) if text else None
        if nuevo is None or nuevo == text:
            return False
        _atomic(p, nuevo)
        return True


def _con_socio_id(text, ced_id, nombre=None, reemplazar=False):
    """El frontmatter con `socio_id` (y `socio: nombre` si se da). Sin
    frontmatter → None. `reemplazar` = cambiar uno que ya exista (al unir)."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    head = text[:end]
    if nombre:
        head = re.sub(r"^socio:.*$", "socio: " + nombre, head, count=1, flags=re.M)
    if re.search(r"^socio_id:", head, re.M):
        if not reemplazar:
            return head + text[end:]
        head = re.sub(r"^socio_id:.*$", "socio_id: " + ced_id, head, count=1, flags=re.M)
    elif re.search(r"^socio:.*$", head, re.M):
        head = re.sub(r"^(socio:.*)$", r"\1\nsocio_id: " + ced_id, head, count=1, flags=re.M)
    else:
        head += "\nsocio_id: " + ced_id
    return head + text[end:]


_SOCIO_ID_RE = re.compile(r"^socio_id:[ \t]*(\S*)", re.M)


def _socio_id_de(text):
    """El `socio_id` del frontmatter de una pestaña ('' si no tiene)."""
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---", 4)
    m = _SOCIO_ID_RE.search(text[:end]) if end != -1 else None
    return m.group(1) if m else ""


def _pestanas_con_cedula(brain, nombre):
    """¿Alguna pestaña de la carpeta `nombre` ya trae `socio_id`? Entonces su
    usuario tiene cédula en algún lado (quizá todavía en camino)."""
    for f in pestanas(brain, nombre):
        try:
            with open(os.path.join(_sess_dir(brain), nombre, f), "rb") as fh:
                cabeza = fh.read(4096).decode("utf-8", "replace").replace("\r\n", "\n")
        except OSError:
            continue
        if _socio_id_de(cabeza):
            return True
    return False


def _bytes(path):
    with open(path, "rb") as fh:
        return fh.read().replace(b"\r\n", b"\n")


def _sin_etiqueta(data):
    """Los renglones de la pestaña sin `socio`/`socio_id` del frontmatter (lo
    único que cambia al renombrar o unir)."""
    lineas = data.decode("utf-8", "replace").split("\n")
    if lineas and lineas[0] == "---" and "---" in lineas[1:]:
        fin = lineas.index("---", 1)
        lineas = [l for k, l in enumerate(lineas)
                  if not (0 < k < fin and re.match(r"socio(?:_id)?:", l))]
    return [l for l in lineas if l.strip()]


def _es_subsecuencia(corta, larga):
    resto = iter(larga)
    return all(any(x == y for y in resto) for x in corta)


def _no_aporta(a, b, historia=()):
    """La copia `a` de una pestaña ya está ENTERA y EN EL MISMO ORDEN dentro de
    `b` (la del usuario que queda) o de UNA de sus copias de `history/`, salvo
    la etiqueta de socio; puede haber algo agregado, como la nota de la unión.
    Es lo que deja una sincronización a medias o un renombre hecho a la vez en
    dos máquinas: la otra ya la movió. Se puede quitar sin perder nada. Si
    cambia el orden, se reparte entre varias copias o trae un renglón propio,
    se une como siempre (Greptile 2026-10-18: comparar conjuntos de renglones
    perdía, por ejemplo, el orden entre un dato y su corrección)."""
    propios = _sin_etiqueta(_bytes(a))
    for p in (b,) + tuple(historia):
        try:
            if _es_subsecuencia(propios, _sin_etiqueta(_bytes(p))):
                return True
        except OSError:
            continue
    return False


def _marcar_pestanas(brain, nombre, ced_id, validas=()):
    """`socio_id` en el frontmatter de cada pestaña del usuario: si falta, o si
    el que tiene no es la cédula de NADIE (`validas` = las de los perfiles). Eso
    lo dejaba la versión con cédulas al azar en un cerebro compartido: la
    sincronización se quedaba con el perfil de una máquina y la pestaña de la
    otra. La cédula de otro usuario que sí existe no se toca."""
    validas = set(validas) | {ced_id}

    def cambio(t):
        actual = _socio_id_de(t)
        return _con_socio_id(t, ced_id, reemplazar=bool(actual) and actual not in validas)
    n = 0
    for f in pestanas(brain, nombre):
        p = os.path.join(_sess_dir(brain), nombre, f)
        try:
            n += bool(_reescribir_ficha(p, cambio))
        except (OSError, TimeoutError):
            continue
    return n


def asegurar(brain):
    """Idempotente y sin preguntar: (1) cada perfil sin cédula recibe una;
    (2) cada carpeta de sesiones sin perfil (y que no sea un nombre viejo de
    nadie) recibe perfil + cédula; (3) las pestañas reciben `socio_id`.
    DETERMINISTA (regla 4): otra máquina con el mismo cerebro escribe los
    mismos bytes, aunque lo haga otro día y antes de sincronizarse.
    → {"cedulas": [nombres], "perfiles": [nombres], "marcadas": n}."""
    rep = {"cedulas": [], "perfiles": [], "marcadas": 0}
    if not os.path.isdir(os.path.join(brain, "STATE")):
        return rep
    with _lock(brain):
        cs = cedulas(brain)
        if _unir_duplicados(brain, cs, rep):
            cs = cedulas(brain)
        usados = {c["id"] for c in cs if c["id"]}
        for c in cs:
            if c["ilegible"]:                  # regla 2: se aparta, con su misma cédula
                if not c["id"]:
                    c["id"] = _nuevo_id(usados, c["nombre"])
                    usados.add(c["id"])
                    rep["cedulas"].append(c["nombre"])
                rep.setdefault("apartados", []).append((c["nombre"], _apartar_ilegible(brain, c)))
                continue
            if not c["id"] and not c["entendido"]:
                rep.setdefault("sin_tocar", []).append(c["nombre"])
                continue
            if not c["id"]:
                c["id"] = _nuevo_id(usados, c["nombre"])
                usados.add(c["id"])
                c["revision"] = max(1, c["revision"])
                _guardar_cedula(c)              # sin «creado: <hoy>» (ver _guardar_cedula)
                rep["cedulas"].append(c["nombre"])
        conocidos = {c["nombre"] for c in cs} | {a for c in cs for a in c["alias"]}
        for nombre in carpetas(brain):
            dueno = next((c for c in cs if nombre in c["alias"] and nombre != c["nombre"]), None)
            if dueno:
                # una máquina con el nombre viejo volvió a crear la carpeta: el
                # alias prueba que es la misma persona → se une sola
                r = _mover_sesiones(brain, nombre, dueno["nombre"])
                rep.setdefault("unidas", []).append((nombre, dueno["nombre"], len(r["movidas"])
                                                     + len(r["dobles"])))
                continue
            if nombre in conocidos:
                continue
            if _pestanas_con_cedula(brain, nombre):
                # sus pestañas ya traen la cédula de alguien: es un usuario que
                # viene en camino (renombrado o unido en otra máquina) y su
                # perfil todavía no llega. Darle otra cédula partiría a la
                # persona en dos; cuando llegue el perfil, todo cuadra solo.
                rep.setdefault("en_camino", []).append(nombre)
                continue
            c = {"id": _nuevo_id(usados, nombre), "nombre": nombre, "alias": [], "creado": "",
                 "revision": 1, "ruta": os.path.join(_users_dir(brain), nombre + ".md"),
                 "cuerpo": _PERFIL.format(titulo=nombre.capitalize()), "extra": {}}
            if os.path.exists(c["ruta"]):
                continue
            usados.add(c["id"])
            _guardar_cedula(c)
            rep["perfiles"].append(nombre)
            cs.append(c)
        for nombre in _carpetas_memoria_claude(brain):
            dueno = next((c for c in cs if nombre in c["alias"] and nombre != c["nombre"]), None)
            if dueno and _mover_memoria_claude(brain, nombre, dueno["nombre"]):
                # un Claude Code abierto en otra máquina siguió escribiendo con el
                # nombre viejo: su memoria pasa a la persona
                rep.setdefault("memoria_unida", []).append((nombre, dueno["nombre"]))
        for c in cs:
            if c["id"] and c["nombre"] in carpetas(brain):
                rep["marcadas"] += _marcar_pestanas(brain, c["nombre"], c["id"], usados)
    return rep


def _unir_duplicados(brain, cs, rep):
    """Dos perfiles con la MISMA cédula = la misma persona renombrada en dos
    máquinas antes de sincronizarse (cada una escribió su nombre nuevo). Se
    unen solos en el de revisión más alta (empate: el nombre menor): las dos
    máquinas eligen el mismo y escriben los mismos bytes (regla 4). Nada se
    borra. → True si unió alguno (hay que releer las cédulas)."""
    por_id = {}
    for c in cs:
        if c["id"] and not c["ilegible"]:
            por_id.setdefault(c["id"], []).append(c)
    unio = False
    for ced_id in sorted(por_id):
        grupo = sorted(por_id[ced_id], key=lambda c: (-c["revision"], c["nombre"]))
        if len(grupo) < 2:
            continue
        if any(c["entendido"] is False for c in grupo):
            rep.setdefault("sin_tocar", []).extend(c["nombre"] for c in grupo[1:])
            continue
        gana, pierden = grupo[0], grupo[1:]
        # PRIMERO la relación de nombres (Greptile 2026-10-18): si algo de
        # abajo falla, el alias ya lleva los nombres viejos al que queda y el
        # perfil que sobra sigue ahí, así que el siguiente intento lo termina.
        # Solo se reescribe si cambia: un reintento no mueve la revisión.
        alias = sorted((set(gana["alias"]) | {p["nombre"] for p in pierden}
                        | {a for p in pierden for a in p["alias"]}) - {gana["nombre"]})
        if alias != gana["alias"]:
            gana["alias"] = alias
            gana["revision"] = max(c["revision"] for c in grupo) + 1
            _guardar_cedula(gana)
        for p in pierden:
            _mover_sesiones(brain, p["nombre"], gana["nombre"])
            _mover_memoria_claude(brain, p["nombre"], gana["nombre"])
            _archivar_perfil(brain, p["ruta"])
            rep.setdefault("duplicadas", []).append((p["nombre"], gana["nombre"]))
        _socio_en_pestanas(brain, gana["nombre"], ced_id)
        if (_leer(_socio_local(brain)) or "").strip().lower() in {p["nombre"] for p in pierden}:
            _atomic(_socio_local(brain), gana["nombre"])
        unio = True
    return unio


def _archivar_perfil(brain, ruta):
    """El perfil que sobra va a `STATE/users/_archivo/`. Si otra máquina ya lo
    archivó con el mismo contenido, no se hace otra copia."""
    arch = os.path.join(_users_dir(brain), "_archivo", os.path.basename(ruta))
    os.makedirs(os.path.dirname(arch), exist_ok=True)
    if os.path.exists(arch) and _bytes(arch) == _bytes(ruta):
        os.remove(ruta)
        return arch
    arch = _destino_libre(arch)
    os.replace(ruta, arch)
    return arch


def al_abrir(brain):
    """Lo que corre solo al abrir un agente: cédulas al día y el nombre de
    esta máquina corregido si quedó uno viejo. → aviso de una línea o ''."""
    try:
        antes = (_leer(_socio_local(brain)) or "").strip().lower()
        rep = asegurar(brain)
        ahora = socio_actual(brain, arreglar=True)
        partes = []
        if antes and ahora and antes != ahora:
            partes.append("en esta PC «%s» ahora se llama «%s»" % (antes, ahora))
        nuevos = rep["cedulas"] + rep["perfiles"]
        if nuevos:
            partes.append("usuario(s) con cédula: %s" % ", ".join(nuevos))
        for viejo, nombre, n in rep.get("unidas") or []:
            partes.append("%d pestaña(s) de «%s» (nombre viejo) pasaron a «%s»" % (n, viejo, nombre))
        for viejo, nombre in rep.get("duplicadas") or []:
            partes.append("«%s» y «%s» eran la misma persona (renombrada en dos máquinas a la vez): "
                          "quedó «%s» y nada se borró" % (viejo, nombre, nombre))
        for nombre, danado in rep.get("apartados") or []:
            partes.append("el perfil de «%s» no se podía leer: quedó entero en STATE/users/%s y "
                          "en su lugar hay uno nuevo con la misma cédula" % (nombre, danado))
        for nombre in rep.get("sin_tocar") or []:
            partes.append("el perfil de «%s» tiene un formato que no entiendo: no le puse cédula "
                          "ni lo toqué" % nombre)
        return ("WORKSPACE · usuarios: " + "; ".join(partes) + " (sección Usuarios)") if partes else ""
    except Exception:
        return ""


# ── acciones de la sección Usuarios ─────────────────────────────────────────
def _buscar(brain, quien):
    nombre = resolver(brain, quien)
    for c in cedulas(brain):
        if c["nombre"] == nombre:
            return c
    raise ValueError("No hay un usuario «%s» en este agente" % quien)


def _ocupado(brain, nombre):
    cs = cedulas(brain)
    return (nombre in carpetas(brain) or any(nombre == c["nombre"] or nombre in c["alias"] for c in cs)
            or os.path.exists(os.path.join(_users_dir(brain), nombre + ".md")))


def crear(brain, nombre, titulo=None):
    nombre = limpiar_nombre(nombre)
    if not valido(nombre):
        raise ValueError("Nombre inválido: usa letras, números y guiones (máx. 32)")
    with _lock(brain):
        if _ocupado(brain, nombre):
            raise ValueError("Ya existe un usuario o un nombre viejo «%s»" % nombre)
        usados = {c["id"] for c in cedulas(brain) if c["id"]}
        c = {"id": _nuevo_id(usados, nombre), "nombre": nombre, "alias": [], "creado": _hoy(),
             "revision": 1, "ruta": os.path.join(_users_dir(brain), nombre + ".md"),
             "cuerpo": _PERFIL.format(titulo=titulo or nombre.capitalize()), "extra": {}}
        _guardar_cedula(c)
        os.makedirs(os.path.join(_sess_dir(brain), nombre), exist_ok=True)
    return c


def _socio_en_pestanas(brain, nombre, ced_id):
    """Tras renombrar o unir: `socio` y `socio_id` de cada pestaña pasan a los
    del usuario que queda (las que vinieron de otro traían su id viejo)."""
    for f in pestanas(brain, nombre):
        _reescribir_ficha(os.path.join(_sess_dir(brain), nombre, f),
                          lambda t: _con_socio_id(t, ced_id, nombre, reemplazar=True))


def renombrar(brain, quien, nuevo, revision=None):
    """El nombre cambia; la cédula (id) no. El nombre viejo queda de alias, la
    carpeta de sesiones y el perfil se mueven, las pestañas se actualizan y,
    si esta máquina usaba el viejo, también. `revision` (opcional) = la que
    se mostró al socio: si otra máquina cambió algo antes, conflicto."""
    nuevo = limpiar_nombre(nuevo)
    if not valido(nuevo):
        raise ValueError("Nombre inválido: usa letras, números y guiones (máx. 32)")
    with _lock(brain):
        c = _buscar(brain, quien)
        viejo = c["nombre"]
        if nuevo == viejo:
            return c
        _editable(c)
        if revision is not None and int(revision) != c["revision"]:
            raise ValueError("Conflicto: «%s» cambió en otra máquina (revisión %d); vuelve a abrir "
                             "la sección" % (viejo, c["revision"]))
        if _ocupado(brain, nuevo) and nuevo not in c["alias"]:
            raise ValueError("Ya existe «%s»: si es la misma persona, usa Unir" % nuevo)
        src = os.path.join(_sess_dir(brain), viejo)
        dst = os.path.join(_sess_dir(brain), nuevo)
        if os.path.isdir(src):
            if os.path.exists(dst):
                raise ValueError("Ya existe la carpeta de «%s»: usa Unir" % nuevo)
            os.replace(src, dst)
        _mover_memoria_claude(brain, viejo, nuevo)
        nueva_ruta = os.path.join(_users_dir(brain), nuevo + ".md")
        if not c["id"]:
            c["id"] = _nuevo_id({x["id"] for x in cedulas(brain) if x["id"]}, viejo)
        c["alias"] = [a for a in c["alias"] if a != nuevo] + [viejo]
        c["nombre"] = nuevo
        c["revision"] += 1
        vieja_ruta, c["ruta"] = c["ruta"], nueva_ruta
        _guardar_cedula(c)
        if os.path.normcase(vieja_ruta) != os.path.normcase(nueva_ruta) and os.path.exists(vieja_ruta):
            os.remove(vieja_ruta)        # ya está reescrita en la ruta nueva
        _socio_en_pestanas(brain, nuevo, c["id"])
        if (_leer(_socio_local(brain)) or "").strip().lower() == viejo:
            _atomic(_socio_local(brain), nuevo)
    return c


def _destino_libre(path):
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    k = 2
    while os.path.exists("%s-%d%s" % (root, k, ext)):
        k += 1
    return "%s-%d%s" % (root, k, ext)


def _fecha_ficha(path):
    data, _ = separar(_leer(path) or "")
    f = str((data or {}).get("actualizada") or "")
    try:
        return (f, os.path.getmtime(path))
    except OSError:
        return (f, 0)


def _nota_en_historial(path, texto):
    """Una línea de nota (formato de memoria v1) dentro de ## Historial."""
    import memoria

    def cambio(t):
        f = memoria.Ficha(t)
        hist = f.lineas("historial") or []
        while hist and not hist[-1].strip():
            hist.pop()
        f.poner("historial", "## Historial", hist + [
            "- %s · workspace · nota: %s" % (memoria._ahora().strftime("%Y-%m-%d %H:%M"), texto)])
        return f.texto()
    _reescribir_ficha(path, cambio)            # error de lectura → no se escribe nada


def _mover_sesiones(brain, origen, destino):
    """Las pestañas de la carpeta `origen` pasan a la de `destino` (sin
    candado: lo toma quien llama). Una pestaña en las dos: se queda la más
    nueva y la otra va ENTERA a `history/`, con una nota que dice dónde."""
    src = os.path.join(_sess_dir(brain), origen)
    dst = os.path.join(_sess_dir(brain), destino)
    rep = {"movidas": [], "dobles": [], "otros": [], "iguales": []}
    if not os.path.isdir(src):
        return rep
    os.makedirs(dst, exist_ok=True)
    import memoria
    for f in sorted(os.listdir(src)):
        a, b = os.path.join(src, f), os.path.join(dst, f)
        if os.path.isfile(a) and f.endswith(".md") and f != "README.md":
            # mover una pestaña con los candados de las notas de origen y destino
            with memoria._lock(a), memoria._lock(b):
                if not os.path.exists(b):
                    os.replace(a, b)
                    rep["movidas"].append(f)
                    continue
                if _no_aporta(a, b, _copias_en_historia(dst, f)):
                    os.remove(a)          # ya está entera en destino: sin copia ni nota
                    rep["iguales"].append(f)
                    continue
                gana_a = _fecha_ficha(a) > _fecha_ficha(b)
                pierde = b if gana_a else a
                guardada = _destino_libre(os.path.join(dst, "history", "%s-de-%s.md" % (
                    os.path.splitext(f)[0], destino if gana_a else origen)))
                os.makedirs(os.path.dirname(guardada), exist_ok=True)
                os.replace(pierde, guardada)
                if gana_a:
                    os.replace(a, b)
            rep["dobles"].append(f)
            _nota_en_historial(b, "se unió con la copia de «%s»; la otra versión quedó entera en "
                                  "history/%s" % (origen if not gana_a else destino,
                                                  os.path.basename(guardada)))
        elif os.path.isdir(a):
            _unir_carpeta(a, os.path.join(dst, f), rep)
        else:
            os.replace(a, _destino_libre(b))
            rep["otros"].append(f)
    try:
        os.rmdir(src)
    except OSError:
        pass
    return rep


def unir(brain, origen, destino):
    """«origen» es la misma persona que «destino» (p. ej. max en otra
    máquina): sus pestañas pasan a destino (ver _mover_sesiones). El nombre de
    origen queda de alias de destino y su perfil va a STATE/users/_archivo/.
    Nada se borra."""
    with _lock(brain):
        o = _buscar(brain, origen)
        d = _buscar(brain, destino)
        if o["nombre"] == d["nombre"]:
            raise ValueError("Es el mismo usuario")
        _editable(d)
        rep = _mover_sesiones(brain, o["nombre"], d["nombre"])
        _mover_memoria_claude(brain, o["nombre"], d["nombre"])
        d["alias"] = sorted(set(d["alias"]) | {o["nombre"]} | set(o["alias"]))
        d["revision"] += 1
        if not d["id"]:
            d["id"] = _nuevo_id({x["id"] for x in cedulas(brain) if x["id"]}, d["nombre"])
        _guardar_cedula(d)
        _archivar_perfil(brain, o["ruta"])
        _socio_en_pestanas(brain, d["nombre"], d["id"])
        if (_leer(_socio_local(brain)) or "").strip().lower() == o["nombre"]:
            _atomic(_socio_local(brain), d["nombre"])
    return rep


def _copias_en_historia(carpeta, f):
    """Las copias de la pestaña `f` que una unión dejó en `history/`
    (`<pestaña>-de-<usuario>[-N].md`)."""
    base, d = os.path.splitext(f)[0] + "-de-", os.path.join(carpeta, "history")
    try:
        return [os.path.join(d, x) for x in sorted(os.listdir(d))
                if x.startswith(base) and x.endswith(".md")]
    except OSError:
        return []


def _carpetas_memoria_claude(brain):
    d = os.path.join(brain, "motores", "claude-code", "memoria")
    try:
        return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)) and valido(x))
    except OSError:
        return []


def _mover_memoria_claude(brain, origen, destino):
    """La memoria de Claude Code (motores/claude-code/memoria/<socio>/) sigue
    a la persona al renombrarla o unirla. Falla-suave: si no se pudo, queda
    entera en la carpeta de origen. → archivos que llegaron a destino."""
    try:
        import memoria
        return memoria.mover_memoria_claude(brain, origen, destino)
    except OSError:
        return 0


def _unir_carpeta(a, b, rep):
    """checkpoints/, maleta/, archivo/, history/…: se mueve todo; lo que choca
    entra con sufijo. En checkpoints gana la revisión más alta. Una copia
    idéntica (otra máquina ya la movió) no se duplica."""
    os.makedirs(b, exist_ok=True)
    for f in sorted(os.listdir(a)):
        x, y = os.path.join(a, f), os.path.join(b, f)
        if os.path.isdir(x):
            _unir_carpeta(x, y, rep)
            continue
        if not os.path.exists(y):
            os.replace(x, y)
            continue
        if _bytes(x) == _bytes(y):
            os.remove(x)
            continue
        if os.path.basename(a) == "maleta" and f.endswith(".md"):
            # una maleta con sufijo nadie la lee: se juntan las secciones por
            # motor (la más nueva de cada uno) en la que abre la pestaña
            import memoria
            memoria.unir_maletas(y, x)
            os.remove(x)
            continue
        if os.path.basename(a) == "checkpoints" and f.endswith(".md"):
            os.makedirs(os.path.join(b, "history"), exist_ok=True)
            if _rev(x) > _rev(y):
                os.replace(y, _destino_libre(os.path.join(b, "history", f)))
                os.replace(x, y)
            else:
                os.replace(x, _destino_libre(os.path.join(b, "history", f)))
            continue
        os.replace(x, _destino_libre(y))
        rep["otros"].append(f)
    try:
        os.rmdir(a)
    except OSError:
        pass


def _rev(path):
    m = re.search(r'"revision":\s*(\d+)', _leer(path) or "")
    return int(m.group(1)) if m else 0


# ── lo que muestra la sección ───────────────────────────────────────────────
def resumen(brain):
    """[{nombre, id, alias, pestanas, yo, revision, parecido}] para la
    sección. `parecido` = otro usuario que probablemente es la misma persona
    (un nombre empieza con el otro y comparten pestañas): se ofrece Unir."""
    yo = socio_actual(brain, arreglar=False)
    cs = cedulas(brain)
    filas = []
    tabs = {c["nombre"]: set(pestanas(brain, c["nombre"])) for c in cs}
    for c in cs:
        par = ""
        for o in cs:
            if o is c or len(o["nombre"]) < 3 or len(c["nombre"]) < 3:
                continue
            if (o["nombre"].startswith(c["nombre"]) or c["nombre"].startswith(o["nombre"])) \
                    and tabs[c["nombre"]] & tabs[o["nombre"]]:
                par = o["nombre"]
                break
        filas.append({"nombre": c["nombre"], "id": c["id"], "alias": c["alias"],
                      "pestanas": len(tabs[c["nombre"]]), "yo": c["nombre"] == yo,
                      "revision": c["revision"], "parecido": par})
    return filas


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="workspace usuarios")
    p.add_argument("accion", choices=("lista", "crear", "renombrar", "unir", "soy", "asegurar"))
    p.add_argument("args", nargs="*")
    p.add_argument("--agente", default="")
    p.add_argument("--brain", default="")
    a = p.parse_args(argv)
    brain = a.brain
    if not brain and a.agente:
        import agentsreg
        info = agentsreg.find(a.agente) or {}
        brain = info.get("brain") or info.get("path") or ""
    if not brain or not os.path.isdir(brain):
        print("✗ indica --agente <nombre> o --brain <ruta>")
        return 1
    try:
        if a.accion == "lista":
            print(json.dumps(resumen(brain), ensure_ascii=False, indent=1))
        elif a.accion == "asegurar":
            print(json.dumps(asegurar(brain), ensure_ascii=False))
        elif a.accion == "crear":
            print("✓ creado: %s" % crear(brain, " ".join(a.args))["nombre"])
        elif a.accion == "renombrar":
            print("✓ ahora se llama: %s" % renombrar(brain, a.args[0], a.args[1])["nombre"])
        elif a.accion == "unir":
            r = unir(brain, a.args[0], a.args[1])
            print("✓ unidos: %d pestaña(s) movida(s), %d en los dos" % (len(r["movidas"]), len(r["dobles"])))
        elif a.accion == "soy":
            print("✓ en esta PC eres: %s" % elegir(brain, a.args[0]))
        return 0
    except (ValueError, IndexError, OSError) as e:
        print("✗ %s" % e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
