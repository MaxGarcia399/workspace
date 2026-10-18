#!/usr/bin/env python3
"""WORKSPACE · agent_brand — identidad de marca + LISTA de sesiones, SOURCED del cerebro.

Contenido en el cerebro, código en WORKSPACE. Este módulo deriva DOS cosas de lo que
vive (y sincroniza por Obsidian) DENTRO del cerebro, para que SIGAN al socio entre
máquinas:

  • la LISTA de pestañas — de las memorias de sesión `STATE/sessions/<socio>/*.md`
    (frontmatter sesión/workspace/titulo/actualizada/estado), MERGEADA con el
    `.claude/<agente>-workspaces.json` per-máquina (gitignored) que aporta el
    enriquecimiento vivo: id de pestaña, last_opened, conteo de eventos del .jsonl.
  • la IDENTIDAD de marca — de `BOOT/01-IDENTITY.md` (Nombre/Emoji/Color/Rol) y de
    `.workspace/agent.json` (display/color/tagline), para que el banner/dashboard
    genéricos (agentes CARGADOS como Turing) muestren una marca real, no el stub.

Lo consumen los dashboards de los agentes del equipo (zenith/atlas/argus) y el brand
genérico del template. Stdlib puro, falla-suave (jamás crashea al consumidor),
UTF-8 (estos scripts los captura el motor por subprocess).
"""
import datetime
import hashlib
import json
import os
import re
import unicodedata


# ── helpers de texto ─────────────────────────────────────────────────────────
def slug_ascii(s):
    """El slug de siempre: kebab-case ASCII (NFKD, sin acentos). Para nombres
    latinos ES el slug; los demás alfabetos los perdía (ver slug())."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _no_latina(c):
    """¿LETRA de otro alfabeto (coreano, chino, cirílico, griego…) que el slug
    ASCII perdería? No cuentan —su slug de siempre no cambia—: lo que el ASCII
    conserva (é → e, Ａ → a), las latinas sin descomposición (ø, ß, ł), los
    modificadores (ʻ), los números (❶, ٣) ni los signos de unidad o de
    matemáticas (µ, ℵ). Ω cuenta como griega aunque sea el signo de ohm: NFC
    lo convierte en la omega. `c`: un carácter del nombre en NFC."""
    cat = unicodedata.category(c)
    if c.isascii() or cat[0] != "L" or cat == "Lm":
        return False
    if ord(c) <= 0xFF or 0x2100 <= ord(c) <= 0x214F:
        return False
    if any(x.isascii() for x in unicodedata.normalize("NFKD", c)):
        return False
    return not unicodedata.name(c, "").startswith("LATIN")


def slug(s):
    """kebab-case ASCII de un nombre de pestaña (igual que los dashboards).

    Nombre latino → el slug de siempre (slug_ascii), byte a byte. Si trae letras
    de otro alfabeto (coreano, chino, cirílico…) el ASCII las perdía: slug vacío
    o choques («회의 A» y «기획 A» → «a», memoria y resume compartidos). Entonces
    va lo ASCII que sobreviva (o «tab») + un hash corto y ESTABLE del nombre
    normalizado (NFKC, minúsculas, sin puntuación): sin transliterar, igual en
    toda máquina y distinto por nombre."""
    s = s or ""
    base = slug_ascii(s)
    if not any(_no_latina(c) for c in unicodedata.normalize("NFC", s)):
        return base
    u = unicodedata.normalize("NFKC", s).lower()
    clave = re.sub(r"-+", "-", "".join(
        c if unicodedata.category(c)[0] in "LNM" else "-" for c in u)).strip("-")
    if not clave:
        return base
    return "%s-%s" % (base or "tab",
                      hashlib.sha256(clave.encode("utf-8")).hexdigest()[:8])


def parse_frontmatter(path):
    """Frontmatter YAML-lite (claves `k: v` de nivel 0) de un .md. Salta líneas
    indentadas (continuaciones de bloques '>-') y para en el segundo '---'.
    Falla-suave → {}."""
    fm = {}
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except Exception:
        return fm
    if not lines or lines[0].strip() != "---":
        return fm
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if not ln[:1].strip():          # indentada → continuación, no es clave
            continue
        if ":" in ln:
            k, v = ln.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def _epoch(date_str):
    """ISO / 'YYYY-MM-DD' → epoch; vacío/ilegible → 0.0."""
    s = (date_str or "").strip()
    if not s:
        return 0.0
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except Exception:
        pass
    try:
        return datetime.datetime.strptime(s[:10], "%Y-%m-%d").timestamp()
    except Exception:
        return 0.0


# ── sesiones del cerebro (autoritativas para la LISTA) ───────────────────────
# Backup de transcript: `2026-06-27-<hash>.md` (fecha + id, SIN título semántico).
# El nombre de pestaña real nunca empieza por fecha → patrón seguro para descartarlos.
_BACKUP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[-_t]", re.IGNORECASE)


def _fm_name(fm):
    """Nombre de la pestaña según su frontmatter (cualquier esquema)."""
    return (fm.get("titulo") or fm.get("sesión") or fm.get("sesion")
            or fm.get("slug") or fm.get("tarea") or "").strip()


def _sesiones_md(d):
    """[(archivo, ruta, frontmatter, nombre)] de los .md de pestaña de `d`, por
    nombre de archivo. Salta README.md, subdirectorios, los backups date+hash
    sin título y `.md` (sin nombre: residuo del slug vacío de nombres no
    latinos, un archivo OCULTO que compartían todas esas pestañas)."""
    out = []
    try:
        names = sorted(os.listdir(d))
    except Exception:
        return out
    for fn in names:
        if not fn.endswith(".md") or fn in ("README.md", ".md"):
            continue
        path = os.path.join(d, fn)
        if not os.path.isfile(path):
            continue
        fm = parse_frontmatter(path)
        name = _fm_name(fm)
        if not name:
            if _BACKUP_RE.match(fn):
                continue                # backup date+hash sin título → fuera
            name = fn[:-3]              # nombrada por el archivo (sin frontmatter)
        out.append((fn, path, fm, name))
    return out


def _ajena(stem, nombre):
    """Slug de la pestaña de nombre NO latino a la que pertenece un .md que no
    es su archivo: el del slug viejo («회의 A» → a.md) o el nombre que le puso
    el agente cuando no le daban ruta (도시-계획.md; dosi-gyehoek.md con
    `titulo: 도시 계획`). '' para todo lo demás (los latinos no cambian)."""
    sl = slug(nombre)
    return sl if sl and sl != slug_ascii(nombre) and stem != sl else ""


def legacy_session_file(d, name):
    """Compat de LECTURA (nombres no latinos de antes del arreglo): el .md donde
    vivía la memoria de ESTA pestaña con otro nombre de archivo — el slug viejo
    (a.md, que podía compartir con «기획 A») o el que eligió el agente
    (도시-계획.md). Su frontmatter (o su nombre de archivo) debe probar que es
    esta pestaña y tiene que ser UNO solo (si hay varios, ¿cuál?). '' si no."""
    sl = slug(name)
    if not d or not sl or sl == slug_ascii(name):
        return ""                       # nombre latino: su archivo de siempre
    cands = [p for fn, p, _fm, n in _sesiones_md(d) if _ajena(fn[:-3], n) == sl]
    return cands[0] if len(cands) == 1 else ""


def brain_sessions(brain, socio):
    """Sesiones NOMBRADAS del cerebro: `STATE/sessions/<socio>/*.md`. 'Nombrada' = trae
    un nombre real en el frontmatter (cualquier esquema: `titulo`, `sesión`/`sesion`,
    `slug` o `tarea`) o, en su defecto, un nombre de archivo que NO sea un backup
    date+hash. Salta README.md, subdirectorios y los backups date+hash sin título.
    Devuelve dicts ordenados por nombre de archivo: {slug, name, workspace, actualizada,
    estado}. Falla-suave → []."""
    out = []
    if not brain or not socio:
        return out
    d = os.path.join(brain, "STATE", "sessions", socio)
    files = _sesiones_md(d)
    ajenos = {}                         # pestaña no latina → cuántos .md ajenos
    for fn, _p, _fm, name in files:
        a = _ajena(fn[:-3], name)
        if a:
            ajenos[a] = ajenos.get(a, 0) + 1
    for fn, path, fm, name in files:
        sl = slug(fn[:-3])
        a = _ajena(fn[:-3], name)
        if a:
            # .md de una pestaña no latina con otro nombre de archivo: su
            # identidad es la de su nombre. Si ya tiene su archivo y este era el
            # ÚNICO (lo adoptó sessions_registry._seed_md) → no se lista doble.
            if ajenos[a] == 1 and os.path.isfile(os.path.join(d, a + ".md")):
                continue
            sl = a
        out.append({
            "slug": sl,
            "name": name,
            "workspace": (fm.get("workspace") or "").strip(),
            "actualizada": (fm.get("actualizada") or "").strip(),
            "estado": (fm.get("estado") or "").strip(),
        })
    return out


def merged_sessions(brain, socio, workspaces, session_dir=None, last_human=None):
    """Une las sesiones del cerebro (autoritativas — siguen al socio entre máquinas)
    con el workspaces.json per-máquina (enriquecimiento vivo). Reglas:

      • una sesión en el cerebro AUSENTE del workspaces local SIGUE apareciendo
        (id = el workspace del frontmatter si lo trae, o None → 'sin iniciar' local);
      • un workspace local SIN memoria en el cerebro (p. ej. una pestaña recién creada
        que aún no guardó su .md) también se conserva;
      • el match cerebro↔workspace es por id (`workspace` del frontmatter == `id`) y,
        si no, por slug del nombre.

    Devuelve dicts workspace-like (SUPERSET del workspace, + claves `_brain/_slug/
    _estado/_actualizada`) ORDENADOS por interacción humana desc, con fallback a
    `actualizada` del cerebro. `last_human(w)` lo pasa cada dashboard (last_opened →
    mtime .jsonl → created). Falla-suave."""
    ws_list = list(workspaces or [])
    ws_by_id, ws_by_slug = {}, {}
    for i, w in enumerate(ws_list):
        wid = w.get("id")
        if wid and wid not in ws_by_id:
            ws_by_id[wid] = i
        s = slug(w.get("name", ""))
        if s and s not in ws_by_slug:
            ws_by_slug[s] = i

    def _lh(w):
        if not last_human:
            return 0.0
        try:
            return last_human(w) or 0.0
        except Exception:
            return 0.0

    merged, used = [], set()
    for bs in brain_sessions(brain, socio):
        wid = bs.get("workspace")
        idx = ws_by_id.get(wid) if wid else None
        if idx is None:
            idx = ws_by_slug.get(bs["slug"])
        base = dict(ws_list[idx]) if idx is not None else {}
        if idx is not None:
            used.add(idx)
        base["name"] = bs["name"]
        base.setdefault("id", (wid or None))       # del frontmatter o None
        base["_brain"] = True
        base["_slug"] = bs["slug"]
        base["_estado"] = bs["estado"]
        base["_actualizada"] = bs["actualizada"]
        base["_sort"] = max(_lh(base), _epoch(bs["actualizada"]))
        merged.append(base)
    for i, w in enumerate(ws_list):                # workspaces locales sin .md
        if i in used:
            continue
        e = dict(w)
        e["_brain"] = False
        e["_sort"] = _lh(w)
        merged.append(e)
    merged.sort(key=lambda e: e.get("_sort", 0.0), reverse=True)
    return merged


# ── identidad de marca (para banner/dashboard genéricos) ─────────────────────
_PALETTE_KEY = {
    "cian": "cyan", "cyan": "cyan", "celeste": "cyan",
    "azul": "azul", "blue": "azul",
    "verde": "verde", "green": "verde",
    "morado": "morado", "purple": "morado", "violeta": "morado", "violet": "morado",
    "dorado": "dorado", "gold": "dorado", "oro": "dorado", "amarillo": "dorado",
    "coral": "coral", "rojo": "coral", "red": "coral", "rosa": "coral", "pink": "coral",
    "gris": "gris", "gray": "gris", "grey": "gris",
}


def palette_key(color):
    """Normaliza un color (es/en, con paréntesis) a la clave de paleta que entienden
    los banners/dashboards. Default 'gris'."""
    c = (color or "").strip().lower()
    c = c.split()[0] if c else ""               # 'cian (cursor)' → 'cian'
    c = re.sub(r"[^a-záéíóúñ]+", "", c)
    return _PALETTE_KEY.get(c, "gris")


# Paletas de statusline — 7 códigos 256-color por agente en este orden:
# HEAD, MODEL, LBL, VAL, SEP, FILL, EMPT. Fuente ÚNICA: antes vivían duplicadas e
# inline en CADA *-statusline.py del template (la causa de que un cambio de marca
# tuviera que tocarse en N archivos). Presets nombrados abajo (claves de palette_key);
# la paleta TUNED de un agente vive como DATO en su `.workspace/agent.json`
# ("palette": [7 ints]) — NO como código.
PALETTES = {
    "dorado": (178, 179, 143, 222, 238, 136, 234),
    "coral":  (217, 203, 174, 224, 238, 167, 52),
    "verde":  (194, 46, 108, 157, 65, 40, 22),
    "azul":   (153, 75, 67, 117, 238, 32, 17),
    "morado": (183, 135, 139, 189, 238, 97, 234),
    "cyan":   (159, 51, 73, 123, 238, 37, 23),
    "gris":   (252, 250, 245, 255, 238, 243, 234),
}


def theme_colors():
    """Colores de la barra de estado desde el TEMA del hub (ui.theme): el
    tema que elige el socio pinta TODO, también la sesión de cada agente —
    la identidad del agente queda en su NOMBRE, no en un color propio.
    dict de secuencias ANSI, o None si tuitheme no se resuelve (entonces la
    paleta de marca de siempre). Jamás levanta."""
    try:
        import tuitheme
        P = tuitheme.palette()
        return {"HEAD": P.C, "MODEL": P.B, "LBL": P.DIM, "VAL": P.WH,
                "SEP": P.DK, "FILL": P.C, "EMPT": P.INACTIVE,
                "OK": P.OK, "ERR": P.ERR, "WARN": P.B2}
    except Exception:
        return None


def palette(brain, color=None):
    """Los 7 códigos 256-color (HEAD..EMPT) de un agente, como DATO del cerebro.
    Prioridad: paleta CUSTOM en `.workspace/agent.json` ("palette": lista de 7 ints) >
    preset por color nombrado (palette_key) > gris. Falla-suave: dato inválido cae al
    preset/gris. Devuelve SIEMPRE una tupla de 7 enteros."""
    aj = _read_json(os.path.join(brain or "", ".workspace", "agent.json"))
    custom = aj.get("palette")
    if isinstance(custom, (list, tuple)) and len(custom) == 7:
        try:
            return tuple(int(n) for n in custom)
        except (TypeError, ValueError):
            pass
    col = color if _ok(color) else aj.get("color")
    return PALETTES.get(palette_key(col), PALETTES["gris"])


def _ok(v):
    """Un valor usable: no vacío y no un placeholder `{{X}}` sin sustituir."""
    return bool(v) and not str(v).strip().startswith("{{")


def _first(*vals):
    for v in vals:
        if _ok(v):
            return str(v).strip()
    return None


def taglineize(text, limit=64):
    """Tagline CONCISO para el banner/header (P1 · estructural, para CUALQUIER
    agente cargado — no solo Turing). Un tagline corto multi-segmento queda
    ENTERO; un Rol largo multi-cláusula del IDENTITY (`A · B · C · D`) NO se
    vuelca: acumula segmentos separados por ` · ` mientras quepan en `limit`,
    y si el primero solo ya excede, recorta con ellipsis."""
    t = (text or "").strip()
    if not t or len(t) <= limit:
        return t
    parts = [p.strip() for p in t.split(" · ")]
    out = parts[0]
    for p in parts[1:]:
        cand = out + " · " + p
        if len(cand) > limit:
            break
        out = cand
    if len(out) > limit:                       # primer segmento solo ya largo
        out = out[:limit - 1].rstrip() + "…"
    return out


def _read_json(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def parse_identity_md(brain):
    """Extrae campos `**Etiqueta:** valor` de BOOT/01-IDENTITY.md (claves en minúscula).
    Maneja varios campos en una línea ('**Emoji:** ◆ · **Color:** cian'). Falla-suave."""
    out = {}
    try:
        lines = open(os.path.join(brain or "", "BOOT", "01-IDENTITY.md"),
                     encoding="utf-8").read().splitlines()
    except Exception:
        return out
    # Cada `**Etiqueta:** valor` de la línea; el valor corre hasta el siguiente
    # `**` (otro campo en la misma línea, p. ej. '**Emoji:** ◆ · **Color:** cian')
    # o el fin de línea — así NO se traga el campo que le sigue.
    for line in lines:
        for m in re.finditer(r"\*\*\s*([^*:]+?)\s*:\s*\*\*\s*([^*\n]*)", line):
            label = m.group(1).strip().lower()
            # sin comentarios HTML del template («◆ <!-- elegir uno propio -->»
            # se pintaba tal cual en la cabecera del panel)
            val = re.sub(r"<!--.*?-->", "", m.group(2))
            val = val.strip().strip("·").strip()
            if label and val and label not in out:
                out[label] = val
    return out


def resolve_identity(brain, display=None, tagline=None, color=None,
                     scope=None, skills=None):
    """Identidad de marca del agente, SOURCED del cerebro. Prioridad por campo:
    placeholder YA sustituido (si lo pasa el script, no-literal) > `.workspace/agent.json`
    > `BOOT/01-IDENTITY.md` > derivado del nombre de la carpeta. El COLOR prioriza
    IDENTITY.md (la fuente de 'quién soy') sobre agent.json (que puede traer el 'gris'
    por defecto del sembrado). Falla-suave: nunca crashea, siempre devuelve algo usable.

    Devuelve {name, display, upper, emoji, color, palette, tagline, scope, skills}."""
    aj = _read_json(os.path.join(brain or "", ".workspace", "agent.json"))
    md = parse_identity_md(brain)
    folder = ""
    if brain:
        folder = os.path.basename(os.path.normpath(brain))
        folder = re.split(r"[ _-]*brain\b", folder, flags=re.IGNORECASE)[0].strip()

    disp = (_first(display, aj.get("display"), md.get("nombre"))
            or (folder.capitalize() if folder else "Agente"))
    name = (_first(aj.get("name"), md.get("nombre"), folder, disp) or "agente").lower()
    col = _first(color, md.get("color"), aj.get("color")) or "gris"
    tag = taglineize(_first(tagline, aj.get("tagline"),
                            md.get("rol"), md.get("lema")) or "")
    scp = _first(scope, md.get("scope")) or ""
    skl = (_first(skills, md.get("categorías de skills"),
                  md.get("categorias de skills")) or "")
    return {
        "name": name,
        "display": disp,
        "upper": disp.upper(),
        "emoji": md.get("emoji", "") if _ok(md.get("emoji")) else "",
        "color": col,
        "palette": palette_key(col),
        "tagline": tag,
        "scope": scp,
        "skills": skl,
    }


def session_memory(brain, name, limit=1200):
    """Shared current-state selector for native dashboards (lazy: no cycle)."""
    import sessions_registry
    return sessions_registry.tab_memory(brain, name, limit=limit)


def instruccion_memoria():
    """Cómo guardar memoria, en los tableros de marca (fuente única, regla 5).
    Los tableros solo la imprimen cuando Workspace NO inyecta el paquete de la
    pestaña: cuando los corre una versión anterior (la copia del cerebro viaja
    por Obsidian) o un hook viejo. Ahí `workspace memoria nota` puede no
    existir, así que dice qué hacer en ese caso (regla 4, revisión 0.3.4). La
    plantilla trae este mismo texto para un Workspace sin esta función."""
    return ("Guarda memoria con `workspace memoria nota --tipo <decision|pendiente|hecho|nota|dato|"
        "preferencia> 'texto'`, en el momento (cerrar un pendiente: --tipo hecho --cierra P-n), y el "
        "resumen con `workspace memoria checkpoint`. Si en esta máquina `workspace memoria nota` no "
        "existe (Workspace anterior: «invalid choice: 'nota'»), agrega al final de ## Historial del "
        "archivo de la pestaña una línea fechada con el mismo formato: "
        "`- 2026-10-16 14:02 · claude-code · decisión: texto`. Fuera de ese caso, no edites ese "
        "archivo a mano.")


# ── dashboards de marca GUARDADOS EN EL CEREBRO ──────────────────────────────
# El paso `agent.brand` de crear-agente copia la plantilla del dashboard a
# `<cerebro>/brand/<nombre>-dashboard.py` UNA vez y nunca la regenera. Las copias
# de antes del arreglo de nombres no latinos calculan el slug viejo (solo-ASCII):
# en Claude Code una pestaña «도시 계획» no recibe su memoria. Huellas (sha256) de
# las tres funciones afectadas tal como venían en cada versión de la plantilla
# que pudo llegar a un cerebro (2026-06-27 → 2026-10-17); una función con OTRA
# huella la editó alguien → ese archivo no se toca.
_DASH_PLANTILLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates",
                               "agent", "workspace", "brand", "agent-dashboard.py")
_DASH_VIEJAS = {
    "_slug": {"b29ff7ab1910d68dee4716f1c42e9ce3cd9e8a47d75ce31e2e8f55ddaebd282d"},
    "session_body": {"ed11edd1331e651c7edc4007697d8c18add1b5df2d5a43a47daf23830d265519"},
    "render_context": {
        "3991f98b165228f55e4b6c146442e4b64d1fe2be8ab376c7392473cedeff4c62",
        "1eddd18c4977a40b0edcccd5d9ecb61599824c114f697964fc77a8f2e801596f",
        "958f7c7e10065edec194dadd3f8e20a1a8c775542f1befacd73d03ac7e55c7cb",
        "0be181d70dfabe8dd0028c097ed35d3f765c78cf39029f29c205610fb1ac8ce3",
        # memoria v1 (2026-10-17): f2d5342 y 6f21d8c… (agentes creados con esa
        # versión: slug viejo, instrucción nueva)
        "fecb5736bdf20ec5c0fa531d9b26fd0b5c138201078ef15dfa1c943c1eb037e7",
        "62f9c4c703ed7ce7f1f8cf7d821fcfb950a582770b238df0b9c712127a268a62",
    },
}


def _funciones_dash(texto):
    """({nombre: (línea_ini, línea_fin, texto)} de las funciones de _DASH_VIEJAS
    a nivel de módulo, ¿hace `import agent_brand`?). ({}, False) si no es
    Python válido."""
    import ast
    try:
        tree = ast.parse(texto)
    except (SyntaxError, ValueError):
        return {}, False
    lineas = texto.splitlines(keepends=True)
    funcs, importa = {}, False
    for n in tree.body:
        if isinstance(n, ast.Import) and any(a.name == "agent_brand" and not a.asname
                                             for a in n.names):
            importa = True
        elif isinstance(n, ast.FunctionDef) and n.name in _DASH_VIEJAS:
            funcs[n.name] = (n.lineno - 1, n.end_lineno,
                             "".join(lineas[n.lineno - 1:n.end_lineno]))
    return funcs, importa


def _sha(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def refresh_brand_dashboards(brain, dashboard, dry_run=False, backup_dir=None):
    """Pone al día el dashboard de marca que el agente USA (`dashboard`: su
    `scripts.dashboard` ya expandido) si vive DENTRO del cerebro: regenera DESDE
    LA PLANTILLA sus funciones de memoria de pestaña (`_slug`, `session_body`,
    `render_context`), que pasan a usar agent_brand.slug como todo lo demás.
    Solo si las tres vienen tal cual de una versión anterior de la plantilla y
    el archivo importa agent_brand; el resto del archivo no se toca. Las copias
    sueltas que nadie ejecuta no se miran. Respaldo en `backup_dir` antes de
    escribir. Idempotente, falla-suave. Devuelve [(archivo, estado)] si trae la
    función vieja: «actualizado» («por actualizar» en dry_run), «personalizado»
    (editado a mano: no se toca) o «error: …». Al día o ajeno → []."""
    try:
        raiz = os.path.realpath(brain or "")
        path = os.path.realpath(dashboard or "")
        if (not brain or not dashboard or os.path.islink(dashboard)
                or not os.path.normcase(path).startswith(os.path.normcase(raiz) + os.sep)
                or not os.path.isfile(path)):
            return []                             # en el harness, o no existe
        rel = os.path.relpath(path, raiz).replace(os.sep, "/")
        with open(_DASH_PLANTILLA, encoding="utf-8") as fh:
            nuevas, _ = _funciones_dash(fh.read())
        with open(path, encoding="utf-8") as fh:
            texto = fh.read()
    except Exception:
        return []
    if set(nuevas) != set(_DASH_VIEJAS):
        return []                                 # plantilla irreconocible
    funcs, importa = _funciones_dash(texto)
    if _sha(funcs.get("_slug", (0, 0, ""))[2]) not in _DASH_VIEJAS["_slug"]:
        return []                                 # al día, o no es de la plantilla
    viejas = [k for k, (_i, _j, t) in funcs.items() if _sha(t) in _DASH_VIEJAS[k]]
    al_dia = [k for k, (_i, _j, t) in funcs.items() if t == nuevas[k][2]]
    if not importa or len(viejas) + len(al_dia) != len(_DASH_VIEJAS):
        return [(rel, "personalizado")]
    if dry_run:
        return [(rel, "por actualizar")]
    lineas = texto.splitlines(keepends=True)
    for k in sorted(viejas, key=lambda k: funcs[k][0], reverse=True):
        i, j, _t = funcs[k]
        lineas[i:j] = [nuevas[k][2]]
    import shutil
    tmp = "%s.tmp-%d" % (path, os.getpid())
    try:
        if backup_dir:                            # respaldo ANTES de escribir
            dest = os.path.join(backup_dir, _sha(raiz)[:12], os.path.dirname(rel))
            os.makedirs(dest, exist_ok=True)
            shutil.copy2(path, os.path.join(dest, os.path.basename(path)))
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("".join(lineas))
        shutil.copymode(path, tmp)
        os.replace(tmp, path)                     # atómico: nunca a medias
        return [(rel, "actualizado")]
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return [(rel, "error: %s" % type(e).__name__)]
