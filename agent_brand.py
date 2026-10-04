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
import json
import os
import re
import unicodedata


# ── helpers de texto ─────────────────────────────────────────────────────────
def slug(s):
    """kebab-case ASCII de un nombre de pestaña (igual que los dashboards)."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


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
    try:
        names = sorted(os.listdir(d))
    except Exception:
        return out
    for fn in names:
        if not fn.endswith(".md") or fn == "README.md":
            continue
        path = os.path.join(d, fn)
        if not os.path.isfile(path):
            continue
        fm = parse_frontmatter(path)
        name = (fm.get("titulo") or fm.get("sesión") or fm.get("sesion")
                or fm.get("slug") or fm.get("tarea") or "").strip()
        if not name:
            if _BACKUP_RE.match(fn):
                continue                # backup date+hash sin título → fuera
            name = fn[:-3]              # nombrada por el archivo (sin frontmatter)
        out.append({
            "slug": slug(fn[:-3]),
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
            val = m.group(2).strip().strip("·").strip()
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
