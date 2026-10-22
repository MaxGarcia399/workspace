#!/usr/bin/env python3
"""WORKSPACE · skills_aprendidas — el catálogo de lo que el agente guardó solo.

Hermes guarda las skills que crea en la sesión en la bandeja
`skills/aprendidas/` del cerebro de la pestaña (su clave oficial
`skills.create_dir`, ver engines/hermes.py), pero no las anota en el catálogo
del cerebro. Claude Code y Codex entran a las skills por
`skills/INDEX-LITE.md` → `skills/README.md`: sin una fila, no las verían.
OpenClaw sí las ve solo (carga `skills/` del cerebro directo).

Al cerrar CUALQUIER motor (memoria.al_cerrar), sin IA y en milisegundos:

  · README: cada skill viva de `skills/aprendidas/**/SKILL.md` que el
    catálogo no nombre gana una fila en la sección de la bandeja (al final;
    se crea si falta). La sección se reconoce por un marcador exacto: el
    encabezado de Workspace (ENCABEZADO) o el de la categoría con el nombre
    de la carpeta, como las demás del catálogo (`## aprendidas`,
    `## 🧠 aprendidas/ (3) — …`); un título del socio que solo CONTIENE la
    palabra («## Lecciones aprendidas») no es la bandeja y sus tablas no se
    tocan. Una skill ya está si el README tiene su ruta `aprendidas/<…>` en
    cualquier parte (también dentro de un enlace) o su nombre en la sección
    de la bandeja. Solo AGREGA renglones: lo que ya está (el `**Total: N**`
    incluido) no se reescribe. Idempotente.
  · INDEX-LITE (HOT, ≤300 tokens): a lo más UNA línea que apunte a la
    bandeja, solo si el archivo existe, aún no la nombra (su ruta
    `aprendidas/`, la línea de Workspace o una fila de la categoría; no la
    palabra suelta) y cabe en el presupuesto. Las skills no se listan ahí.

Del SKILL.md solo se lee la `description` del frontmatter (el de Hermes y el
del cerebro son distintos: no se reescribe ni se completa); sin ella, la fila
dice «ver su SKILL.md». Salta carpetas `_*`/`.*`, skills archivadas
(`status: archivada`) y enlaces. README e INDEX-LITE se escriben con
candado, atómicos y en su codificación y sus finales de línea (UTF-8 con o
sin BOM, UTF-16 con BOM; en cualquier otra, cada byte del socio se conserva y
lo nuevo va en ANSI); uno que es un enlace no se toca. Falla-suave y con tope
de tiempo: jamás rompe el cierre ni le habla al socio.

Cero dependencias (stdlib, 3.9+). Mac/Windows.
"""
import codecs
import json
import os
import re
import sys
import time
import unicodedata
from urllib.parse import unquote

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#: La bandeja (engines/hermes.SKILLS_CREATE apunta aquí).
BANDEJA = "aprendidas"
TOPE_S = 2.0                 # tope de tiempo de todo el paso
MAX_SKILLS = 500             # tope de skills que se miran por cierre
FM_BYTES = 16384             # el frontmatter vive al inicio del archivo
MAX_DESC = 160               # largo de la descripción en la fila
#: Presupuesto HOT de skills/INDEX-LITE.md (protocols/agent-creation/
#: 02-BRAIN-FORMAT.md: «≤300 tokens»), con la estimación del doctor.
LITE_TOKENS = 300
CHARS_POR_TOKEN = 4

ENCABEZADO = "## aprendidas — las que el agente guardó solo"
NOTA = ("*(Las anota Workspace al cerrar cada sesión, sin tocar lo demás. Para darle a una su "
        "categoría, mueve su carpeta y su fila.)*")
TABLA = ("| Skill | Qué hace |", "|---|---|")
LINEA_LITE = ("**aprendidas:** skills que el agente guardó solo en una sesión; su lista, "
              "en `skills/README.md`.")
SIN_DESC = "ver su SKILL.md"
README_NUEVO = "# Skills — catálogo"

_ENCABEZADO_RE = re.compile(r"(#{1,6})[ \t]+(.*)$")
#: El título de la sección de la bandeja, exacto: el nombre de la carpeta como
#: categoría del catálogo (con su emoji, su conteo `(N)` y su descripción tras
#: un guion, como `## meta (4) — el sistema de skills`). ENCABEZADO cumple.
#: Revisión de la 0.5.1 (P2-6): antes bastaba que el título CONTUVIERA la
#: palabra y las filas caían en la tabla de «## Lecciones aprendidas». Los
#: guiones \x96/\x97 son «–»/«—» de un README en ANSI leído byte a byte.
_SECCION_RE = re.compile(r"[^\w`#]*`?(?:skills/)?%s/?`?(?:[ \t]*\(\d+\))?"
                         r"(?:[ \t]+[—–\x96\x97-][ \t].*|[ \t]*:.*)?[ \t]*" % BANDEJA)
#: INDEX-LITE ya nombra la bandeja: su ruta, la línea de Workspace o una fila
#: de la tabla de categorías cuya primera celda es la carpeta.
_LITE_RE = re.compile(r"(?<![\w.-])%s/|\*\*%s:\*\*|^[ \t]*\|[^\w|`]*`?%s/?`?[ \t]*\|"
                      % (BANDEJA, BANDEJA, BANDEJA), re.M)
_CERCO_RE = re.compile(r"[ \t]{0,3}(```|~~~)")


# ── lectura ─────────────────────────────────────────────────────────────────
#: Etiquetas de reparse de Windows que son enlaces: junction y symlink (un
#: archivo de OneDrive bajo demanda también es reparse, y no es un enlace).
_REPARSE_ENLACE = (0xA0000003, 0xA000000C)


def _enlace(p):
    """¿Enlace simbólico o junction (Windows, también en 3.9)? Si no existe,
    no; ante cualquier otra duda, sí."""
    try:
        if os.path.islink(p):
            return True
        return getattr(os.lstat(p), "st_reparse_tag", 0) in _REPARSE_ENLACE
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _texto(crudo, parcial=False):
    """bytes → (texto, codec, bom). Volver a codificar con el mismo codec da
    los mismos bytes: UTF-8 (con o sin BOM), UTF-16 con BOM; cualquier otra
    cosa se lee como latin-1, que conserva cada byte. `parcial`: los bytes
    son el inicio del archivo (un carácter puede quedar cortado al final)."""
    for bom, codec in ((codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"),
                       (codecs.BOM_UTF16_BE, "utf-16-be")):
        if crudo.startswith(bom):
            try:
                return crudo[len(bom):].decode(codec, "replace" if parcial else "strict"), codec, bom
            except UnicodeDecodeError:
                break
    try:
        return crudo.decode("utf-8"), "utf-8", b""
    except UnicodeDecodeError as exc:
        if parcial and exc.start >= len(crudo) - 3:
            return crudo[:exc.start].decode("utf-8", "replace"), "utf-8", b""
        return crudo.decode("latin-1"), "latin-1", b""


def _a_bytes(texto, codec, bom):
    return bom + texto.encode(codec)


def _nuevo(s, codec):
    """Texto que se AGREGA, listo para convivir con el original: en un
    archivo que no es UTF (leído como latin-1, byte a byte) va en ANSI."""
    if codec == "latin-1":
        return s.encode("cp1252", "replace").decode("latin-1")
    return s


def _sin_comillas(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            out = json.loads(v)
            return out if isinstance(out, str) else v[1:-1]
        except ValueError:
            return v[1:-1]
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return re.sub(r"[ \t]+#.*$", "", v)


def _celda(s):
    """Una celda de tabla: una línea, sin `|`, con tope."""
    s = " ".join("".join(c if c.isprintable() else " " for c in str(s)).split())
    s = s.replace("|", "/")
    return s if len(s) <= MAX_DESC else s[:MAX_DESC - 1].rstrip() + "…"


def descripcion(skill_md):
    """`description` del frontmatter de un SKILL.md (de Hermes o del
    cerebro: solo se lee esa clave) en una línea; SIN_DESC si no hay."""
    try:
        with open(skill_md, "rb") as fh:
            crudo = fh.read(FM_BYTES)
    except OSError:
        return SIN_DESC
    texto, codec, _bom = _texto(crudo, parcial=True)
    if codec == "latin-1":
        texto = crudo.decode("cp1252", "replace")
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lineas or lineas[0].strip() != "---":
        return SIN_DESC
    fin = next((k for k in range(1, len(lineas)) if lineas[k].strip() in ("---", "...")), None)
    if fin is None:
        return SIN_DESC
    for k in range(1, fin):
        m = re.match(r"description[ \t]*:(.*)$", lineas[k])
        if not m:
            continue
        valor, sigue = m.group(1).strip(), []
        for ln in lineas[k + 1:fin]:                         # renglones sangrados = el mismo valor
            if ln[:1] not in (" ", "\t") and ln.strip():
                break
            if ln.strip():
                sigue.append(ln.strip())
        if valor[:1] in ("|", ">"):
            valor = " ".join(sigue)
        else:
            valor = _sin_comillas(" ".join([valor] + sigue))
        return _celda(valor) or SIN_DESC
    return SIN_DESC


def skills(brain, hasta=None):
    """[(rel, skill_md)] de la bandeja del cerebro, ordenadas; `rel` con «/»
    desde skills/aprendidas/. Solo skills vivas: sin carpetas `_*`/`.*`, sin
    enlaces y sin las archivadas en su lugar (`status: archivada`)."""
    import skill_meta
    raiz = os.path.join(str(brain), "skills", BANDEJA)
    out = []
    if not os.path.isdir(raiz):
        return out
    for dirpath, dirnames, filenames in os.walk(raiz):
        if (hasta is not None and time.monotonic() >= hasta) or len(out) >= MAX_SKILLS:
            break
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "_"))
                             and not _enlace(os.path.join(dirpath, d)))
        if dirpath == raiz or "SKILL.md" not in filenames:
            continue
        dirnames[:] = []                                     # sus references/ no son skills
        md = os.path.join(dirpath, "SKILL.md")
        if _enlace(md) or skill_meta.archivada(dirpath):
            continue
        out.append((os.path.relpath(dirpath, raiz).replace(os.sep, "/"), md))
    return sorted(out)


# ── el README ───────────────────────────────────────────────────────────────
def _renglones(texto):
    """Renglones con su salto, cortando SOLO en «\\n»: str.splitlines también
    corta en \\x85, que en un archivo ANSI leído byte a byte es «…»."""
    partes = texto.split("\n")
    return [p + "\n" for p in partes[:-1]] + ([partes[-1]] if partes[-1] else [])


def _normal(s):
    """Para buscar rutas: `/` en vez de `\\`, sin %xx de enlace, NFC, minúsculas."""
    return unicodedata.normalize("NFC", unquote(s).replace("\\", "/")).lower()


def _secciones(lineas):
    """[(inicio, fin)] de cada sección cuyo encabezado ES el de la bandeja
    (_SECCION_RE; los encabezados dentro de un bloque de código no
    cuentan)."""
    heads, cerco = [], None
    for i, ln in enumerate(lineas):
        s = ln.rstrip("\r\n")
        c = _CERCO_RE.match(s)
        if c:
            cerco = None if cerco == c.group(1) else (cerco or c.group(1))
            continue
        m = None if cerco else _ENCABEZADO_RE.match(s)
        if m:
            heads.append((i, len(m.group(1)), bool(_SECCION_RE.fullmatch(m.group(2).strip()))))
    out = []
    for n, (i, nivel, nuestra) in enumerate(heads):
        if nuestra:
            fin = next((j for j, nv, _x in heads[n + 1:] if nv <= nivel), len(lineas))
            out.append((i, fin))
    return out


def _ya_esta(rel, plano, secciones):
    """¿El README ya nombra esta skill? Su ruta `aprendidas/<rel>` en
    cualquier parte, o `<rel>` como ruta o código en una sección de la
    bandeja."""
    r = re.escape(_normal(rel))
    if re.search(r"(?<![\w.-])%s/%s(?![\w.-])" % (BANDEJA, r), plano):
        return True
    suelta = re.compile(r"(?<![\w.-])%s(?=/|`)|`%s(?![\w.-])" % (r, r))
    return any(suelta.search(s) for s in secciones)


def _con_filas(texto, filas, nl, codec):
    """El README con las filas nuevas: solo agrega renglones."""
    lineas = _renglones(texto)
    nuevas = [_nuevo("| `%s/%s/` | %s |" % (BANDEJA, rel, desc), codec) + nl for rel, desc in filas]
    secs = _secciones(lineas)
    if secs:
        i, j = next((s for s in secs if lineas[s[0]].strip() == ENCABEZADO), secs[0])
        tabla = [k for k in range(i + 1, j) if lineas[k].lstrip().startswith("|")]
        if tabla:
            at, bloque = tabla[-1] + 1, nuevas
        else:
            at = max([k + 1 for k in range(i, j) if lineas[k].strip()] or [i + 1])
            bloque = [nl] + [_nuevo(t, codec) + nl for t in TABLA] + nuevas
        if not lineas[at - 1].endswith(("\n", "\r")):       # último renglón sin salto
            lineas[at - 1] += nl
        lineas[at:at] = bloque
        return "".join(lineas)
    cuerpo = texto
    if cuerpo and not cuerpo.endswith(("\n", "\r")):
        cuerpo += nl
    if not cuerpo.strip():
        cuerpo += _nuevo(README_NUEVO, codec) + nl
    seccion = [ENCABEZADO, "", NOTA, ""] + list(TABLA)
    return (cuerpo + nl + "".join(_nuevo(s, codec) + nl for s in seccion) + "".join(nuevas))


def _con_linea_lite(texto, nl, codec):
    """INDEX-LITE con la línea de la bandeja, o None si ya la nombra
    (_LITE_RE) o si no cabe en el presupuesto HOT."""
    if _LITE_RE.search(_normal(texto)):
        return None
    cuerpo = texto if not texto or texto.endswith(("\n", "\r")) else texto + nl
    nuevo = cuerpo + nl + _nuevo(LINEA_LITE, codec) + nl
    if len(nuevo) > LITE_TOKENS * CHARS_POR_TOKEN:
        return None
    return nuevo


def _leer(path):
    """Bytes del archivo; b'' si no existe (otro error se propaga)."""
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except FileNotFoundError:
        return b""


def _escribir(path, datos):
    import memoria
    memoria._atomic(path, datos)


def _candado(path):
    from olock import local_lock
    return local_lock(path, timeout=3)


def _anotar_readme(readme, vivas, hasta):
    if _enlace(readme):
        return []
    with _candado(readme):
        texto, codec, bom = _texto(_leer(readme))
        lineas = _renglones(texto)
        plano = _normal(texto)
        secs = [_normal("".join(lineas[i:j])) for i, j in _secciones(lineas)]
        filas = []
        for rel, md in vivas:
            if time.monotonic() >= hasta:
                break
            if not _ya_esta(rel, plano, secs):
                filas.append((rel, descripcion(md)))
        if not filas:
            return []
        nl = "\r\n" if "\r\n" in texto else "\n"
        _escribir(readme, _a_bytes(_con_filas(texto, filas, nl, codec), codec, bom))
        return ["%s/%s" % (BANDEJA, rel) for rel, _d in filas]


def _anotar_lite(lite):
    if not os.path.isfile(lite) or _enlace(lite):
        return False
    with _candado(lite):
        texto, codec, bom = _texto(_leer(lite))
        nuevo = _con_linea_lite(texto, "\r\n" if "\r\n" in texto else "\n", codec)
        if nuevo is None:
            return False
        _escribir(lite, _a_bytes(nuevo, codec, bom))
        return True


def catalogar(brain, tope_s=TOPE_S):
    """Anota en el catálogo del cerebro las skills nuevas de la bandeja.
    Devuelve las rutas que agregó al README (`aprendidas/<…>`); [] si no
    había nada que anotar o si algo falló (falla-suave: lo que no se pudo
    anotar se anota en el próximo cierre)."""
    hasta = time.monotonic() + max(0.0, float(tope_s))
    raiz = os.path.join(str(brain or ""), "skills")
    try:
        vivas = skills(brain, hasta)
        if not vivas:
            return []
        agregadas = _anotar_readme(os.path.join(raiz, "README.md"), vivas, hasta)
    except Exception:
        return []
    try:
        _anotar_lite(os.path.join(raiz, "INDEX-LITE.md"))
    except Exception:
        pass
    return agregadas
