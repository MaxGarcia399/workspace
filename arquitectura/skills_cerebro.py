#!/usr/bin/env python3
"""WORKSPACE · arquitectura/skills_cerebro — las skills del cerebro en el menú / de cada motor (F7).

Salen del catálogo del cerebro (skill_meta.scan_catalog: las vivas, sin las archivadas ni las de `_propuestas`,
y solo las que esta máquina puede correr) y se arman como una VISTA PLANA `skills/<nombre>/SKILL.md`: un nivel,
como lo piden los plugins de Claude Code y las Agent Skills (el nombre en kebab-case, igual a su carpeta, y una
descripción). Así cada motor las muestra por su vía oficial por sesión:

  · dentro del paquete de ese cerebro (sesion.instalar(cerebro)): Claude Code (`/workspace:<skill>`), Copilot y
    Cursor por su plugin; Kiro por los `skill://` de su perfil;
  · o en una carpeta del proyecto (OpenCode), donde solo se tocan las carpetas con el sello de Workspace.

Son copias con sello (no enlaces: Windows), rehechas cuando cambian; nada se escribe en la config global ni en
skills/ del cerebro, que sigue siendo el único catálogo. Stdlib.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

#: El sello de una copia de Workspace: dice de dónde salió (y solo esas carpetas se rehacen o se quitan).
SELLO = ".workspace-skill.json"
#: Las del paquete (la skill «workspace»): una del cerebro con ese nombre va con su categoría delante.
RESERVADAS = ("workspace",)
MAX_SKILLS = 200
MAX_NOMBRE = 64
MAX_DESCRIPCION = 1024
#: Lo que se copia de cada skill: sin ocultos ni cachés, y con tope (una skill no es un almacén).
MAX_ARCHIVO = 1024 * 1024
MAX_SKILL = 8 * 1024 * 1024
_IGNORAR = ("__pycache__", ".DS_Store")
#: La forma de la copia: cambia cuando cambia lo que Workspace le agrega (skills-cierre: la línea de usar_skill), para que
#: las copias de antes se rehagan aunque las skills del cerebro no hayan cambiado.
VERSION_COPIA = b"skills-cerebro-2"
#: skills-cierre (Fix 3): la primera línea de cada copia. El motor que la use por su propia herramienta de skills (Copilot
#: «Using skill», OpenCode `skill`, Kiro al leerla) lee esto: con usar_skill el socio la ve en la página y el hub. El
#: mismo texto en todas las máquinas (el cerebro se sincroniza): sin «workspace.cmd».
LINEA_USAR = ("> Workspace: si el socio te habla por la página o el hub, actívala primero con usar_skill «%s» (sin esa "
              "herramienta, el comando `workspace pasos usar %s`) para que la vea; si ya te dieron su ejecución, no la "
              "actives otra vez.")
_CLAVE = re.compile(r"^([A-Za-z_][\w-]*):(.*)$")


def kebab(texto):
    """«Revisión de Código» → «revision-de-codigo» (minúsculas, sin acentos, a-z 0-9 y guiones)."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", t)).strip("-")[:MAX_NOMBRE].strip("-")


def _bloques(fm):
    """El frontmatter en bloques [(clave|None, [líneas])]: una clave con sus líneas de continuación."""
    out = []
    for linea in fm.split("\n"):
        m = _CLAVE.match(linea)
        if m and not linea[:1].isspace():
            out.append((m.group(1), [linea]))
        elif out:
            out[-1][1].append(linea)
        else:
            out.append((None, [linea]))
    return out


def _valor(lineas):
    """El valor de un bloque: en línea, o el de sus líneas de continuación (`>` / `|`), en una línea."""
    resto = lineas[0].split(":", 1)[1].strip()
    if resto in ("", ">", "|", ">-", "|-", ">+", "|+"):
        resto = " ".join(x.strip() for x in lineas[1:] if x.strip())
    if len(resto) >= 2 and resto[0] == resto[-1] and resto[0] in "'\"":
        resto = resto[1:-1]
    return resto.strip()


def _partir(texto):
    """(frontmatter o None, cuerpo)."""
    if texto.startswith("---"):
        fin = texto.find("\n---", 3)
        if fin != -1:
            cuerpo = texto[fin + 4:]
            return texto[3:fin].strip("\n"), cuerpo[1:] if cuerpo.startswith("\n") else cuerpo
    return None, texto


def _archivo(d):
    import skill_meta
    return next((os.path.join(d, f) for f in skill_meta.SKILL_FILES if os.path.isfile(os.path.join(d, f))), "")


def _primera_linea(cuerpo):
    for linea in cuerpo.splitlines():
        t = linea.strip().lstrip("#").strip()
        if t and not t.startswith(("---", "<!--", "```")):
            return t
    return ""


def indice(cerebro):
    """[{nombre, rel, dir, archivo, descripcion}] de las skills del cerebro que van al menú, en orden.
    `nombre` es único, en kebab-case y sin chocar con las del paquete; `rel` es su ruta en skills/."""
    import skill_meta
    out, usados = [], set(RESERVADAS)
    try:
        catalogo = skill_meta.scan_catalog(str(cerebro))
    except Exception:
        return []
    for r in catalogo:
        if not r.get("available") or len(out) >= MAX_SKILLS:
            continue
        d, archivo = r["dir"], _archivo(r["dir"])
        if not archivo:
            continue
        try:
            with open(archivo, encoding="utf-8", errors="replace") as fh:
                texto = fh.read(skill_meta.FM_READ_BYTES)
        except OSError:
            continue
        fm, cuerpo = _partir(texto)
        campos = {k: _valor(ls) for k, ls in _bloques(fm or "") if k}
        partes = r["name"].split("/")
        base = kebab(campos.get("name")) or kebab(partes[-1])
        if not base:
            continue
        nombre = base
        if nombre in usados and len(partes) > 1:
            nombre = kebab("%s-%s" % (partes[-2], base)) or base
        n = 2
        while nombre in usados:
            nombre = "%s-%d" % (base[:MAX_NOMBRE - 4], n)
            n += 1
        usados.add(nombre)
        desc = campos.get("description") or _primera_linea(cuerpo) or "Skill «%s» del cerebro." % base
        out.append({"nombre": nombre, "rel": r["name"], "dir": d, "archivo": archivo,
                    "descripcion": " ".join(desc.split())[:MAX_DESCRIPCION]})
    return out


def _archivos(d):
    """Los archivos de una skill que se copian (relativos), sin ocultos, cachés ni enlaces, con tope."""
    out, total = [], 0
    for base, ds, fs in os.walk(d):
        ds[:] = sorted(x for x in ds if not x.startswith(".") and x not in _IGNORAR
                       and not os.path.islink(os.path.join(base, x)))
        for f in sorted(fs):
            p = os.path.join(base, f)
            if f.startswith(".") or f in _IGNORAR or f.endswith(".pyc") or os.path.islink(p):
                continue
            try:
                tam = os.path.getsize(p)
            except OSError:
                continue
            if tam > MAX_ARCHIVO or total + tam > MAX_SKILL:
                continue
            total += tam
            out.append(os.path.relpath(p, d))
    return out


def huella(cerebro):
    """Cambia si cambia alguna skill que va al menú (nombres, rutas, tamaños y fechas): barato, sin leer."""
    h = hashlib.sha1(VERSION_COPIA)
    for s in indice(cerebro):
        h.update(("%s|%s\n" % (s["nombre"], s["rel"])).encode("utf-8"))
        for rel in _archivos(s["dir"]):
            try:
                st = os.stat(os.path.join(s["dir"], rel))
            except OSError:
                continue
            h.update(("%s|%d|%d\n" % (rel, st.st_size, st.st_mtime_ns)).encode("utf-8"))
    return h.hexdigest()[:10]


def skill_md(s):
    """El SKILL.md de la copia: el de la skill con `name` = su carpeta y `description` (lo demás, tal cual)."""
    with open(s["archivo"], encoding="utf-8", errors="replace") as fh:
        texto = fh.read()
    fm, cuerpo = _partir(texto)
    resto = [ls for k, ls in _bloques(fm or "") if k not in ("name", "description") and (k or any(
        x.strip() for x in ls))]
    lineas = ["name: %s" % s["nombre"], "description: %s" % json.dumps(s["descripcion"], ensure_ascii=False)]
    lineas += [x for ls in resto for x in ls]
    return "---\n%s\n---\n%s\n\n%s" % ("\n".join(lineas), LINEA_USAR % (s["rel"], s["rel"]), cuerpo.lstrip("\n"))


def escribir(cerebro, destino):
    """La vista plana en `destino` (la carpeta skills/ de un formato del paquete): una carpeta por skill, con su
    SKILL.md normalizado, sus demás archivos y el sello. → [nombres]."""
    hechos = []
    for s in indice(cerebro):
        d = os.path.join(destino, s["nombre"])
        os.makedirs(d, exist_ok=True)
        principal = os.path.relpath(s["archivo"], s["dir"])
        for rel in _archivos(s["dir"]):
            if rel == principal:
                continue
            dst = os.path.join(d, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(s["dir"], rel), dst)
        texto = skill_md(s)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
        with open(os.path.join(d, SELLO), "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"origen": "skills/" + s["rel"],
                       "huella": hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]}, fh, ensure_ascii=False)
            fh.write("\n")
        hechos.append(s["nombre"])
    return hechos


def es_nuestra(d):
    return os.path.isfile(os.path.join(d, SELLO))


def reflejar(origen, destino):
    """Deja en `destino` (una carpeta de skills del proyecto) las de `origen` (la vista plana del paquete): rehace
    las que llevan el sello de Workspace, quita las nuestras que ya no están y NUNCA toca una del socio (si una
    suya se llama igual, gana la suya). → {"puestas": [...], "quitadas": [...], "del_socio": [...]}."""
    r = {"puestas": [], "quitadas": [], "del_socio": []}
    nuevas = sorted(n for n in (os.listdir(origen) if os.path.isdir(origen) else ())
                    if es_nuestra(os.path.join(origen, n)))
    os.makedirs(destino, exist_ok=True)
    for n in sorted(os.listdir(destino)):
        d = os.path.join(destino, n)
        if n not in nuevas and os.path.isdir(d) and es_nuestra(d):
            shutil.rmtree(d, ignore_errors=True)
            r["quitadas"].append(n)
    for n in nuevas:
        d = os.path.join(destino, n)
        if os.path.exists(d) and not es_nuestra(d):
            r["del_socio"].append(n)
            continue
        if os.path.isdir(d):
            shutil.rmtree(d)
        shutil.copytree(os.path.join(origen, n), d)
        r["puestas"].append(n)
    return r
