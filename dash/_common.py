#!/usr/bin/env python3
"""WORKSPACE · dash/_common — helpers compartidos del framework de secciones.

Prefijo `_` → el autodescrubidor de dash/ lo IGNORA (no genera rutas ni JS).

Expone utilidades que varios módulos de dash/ usan (o usarán):

  slug(text)            ASCII slug sin espacios  (ej. "Mi Tarea" → "mi-tarea")
  inside(base, path)    guard realpath — True si `path` está dentro de `base`
  parse_date(text)      primera fecha válida en texto (ISO · DD/MM · español)
  read_file(path)       lectura falla-suave (devuelve "" en vez de levantar)
  read_frontmatter(text)frontmatter YAML-simple {clave: valor}
  parse_pendientes(text)parser tolerante de PENDIENTES.md → lista de items
  read_pendientes(brain)lee STATE/PENDIENTES.md del cerebro → lista de items
  read_deliverables(brain) → lista de archivos de entregables con metadatos
  read_sessions(brain, socio) → lista de journals de sesión del socio
  read_queue(agent_brain, socio=None) → encargos de research-queue pendientes
  agent_events(brain, agent_name, limit)
                        eventos del rastro N10 para un agente (falla-suave)
  inbox_append(brain, socio, op, titulo, campos, origen)
                        APPEND al inbox del socio (append-only, nunca canónico)
  queue_write(agent_brain, socio, tema, data)
                        archivo nuevo en research-queue (formato _template.md)
  atlas_brain()         resuelve el cerebro de Atlas vía registry (falla-suave)

Falla-suave en TODO: cualquier archivo ausente / brain sin resolver / IO roto
devuelve vacío o None — nunca levanta.

F-2 lo crea; kanban/calendar/capture se migran en F-8 (no antes, para no
colisionar con corridas paralelas F-3/F-5).
"""
import datetime
import os
import re
import unicodedata

# ── constantes internas ────────────────────────────────────────────────────

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_RE_ISO = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
_RE_DMY = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](20\d{2})\b")
_RE_ES = re.compile(
    r"\b(\d{1,2})\s+de\s+([a-záéíóúñ]+)(?:\s+(?:de|del)\s+(20\d{2}))?",
    re.IGNORECASE,
)
_MESES = {
    "enero": 1, "ene": 1, "febrero": 2, "feb": 2, "marzo": 3, "mar": 3,
    "abril": 4, "abr": 4, "mayo": 5, "may": 5, "junio": 6, "jun": 6,
    "julio": 7, "jul": 7, "agosto": 8, "ago": 8, "septiembre": 9,
    "setiembre": 9, "sep": 9, "sept": 9, "octubre": 10, "oct": 10,
    "noviembre": 11, "nov": 11, "diciembre": 12, "dic": 12,
}
_EMOJI_STATUS = [
    ("✅", "done"), ("⏳", "open"), ("⏸", "paused"),
    ("🚫", "skip"), ("🔕", "skip"),
]
_CHECKBOX_RE = re.compile(r"^[-*]\s*\[([ xX])\]\s+(.+)$")
_NOMBRES = ("max", "fer", "mau", "zenith", "atlas", "equipo")


# ═══════════════════════════════════════════════════════════════════════════
# Primitivas básicas
# ═══════════════════════════════════════════════════════════════════════════

def slug(text, maxlen=60):
    """ASCII slug, sin espacios.  "Mi Tarea!" → "mi-tarea"."""
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:maxlen].strip("-") or "item"


def inside(base, path):
    """True si `path` está dentro (o es igual a) `base` tras realpath."""
    b = os.path.realpath(base)
    p = os.path.realpath(path)
    return p == b or p.startswith(b + os.sep)


# ═══════════════════════════════════════════════════════════════════════════
# I/O falla-suave
# ═══════════════════════════════════════════════════════════════════════════

def read_file(path, limit=120_000):
    """Lee `path` → str (vacío si no existe o falla). Sin levantar."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except Exception:
        return ""


def read_frontmatter(text):
    """Parseo TOLERANTE de frontmatter YAML-plano (clave: valor) en `text`.
    Devuelve dict {clave: valor}; sin frontmatter → {}. Nunca levanta."""
    fm = {}
    try:
        m = re.match(r"^---\s*\n(.*?)\n---", text or "", re.S)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line and not line.strip().startswith("#"):
                    k, v = line.split(":", 1)
                    fm[k.strip().lower()] = v.strip()
    except Exception:
        pass
    return fm


# ═══════════════════════════════════════════════════════════════════════════
# Parseo de fechas tolerante (extraído de calendar.py — misma lógica)
# ═══════════════════════════════════════════════════════════════════════════

def parse_date(text, default_year=None):
    """Primera fecha válida encontrada en `text` → "AAAA-MM-DD" | None.

    Tolerante: ISO (2026-06-07), DD/MM/AAAA, DD-MM-AAAA, DD.MM.AAAA y
    español ("7 de junio de 2026", "7 de junio" → default_year/año actual).
    Fechas inválidas (mes 13, día 32) se ignoran y se sigue buscando.
    Devuelve None para texto vacío, None, o sin fecha reconocible.
    """
    if not text:
        return None
    cands = []
    for m in _RE_ISO.finditer(text):
        cands.append((m.start(), m.group(1), m.group(2), m.group(3)))
    for m in _RE_DMY.finditer(text):
        cands.append((m.start(), m.group(3), m.group(2), m.group(1)))
    for m in _RE_ES.finditer(text):
        mes = _MESES.get(m.group(2).lower())
        if mes:
            y = m.group(3) or str(default_year or datetime.date.today().year)
            cands.append((m.start(), y, str(mes), m.group(1)))
    for _, y, mo, d in sorted(cands, key=lambda c: c[0]):
        try:
            return datetime.date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            continue
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Parser de PENDIENTES.md (extraído y unificado de kanban.py)
# ═══════════════════════════════════════════════════════════════════════════

def _lead_status(s):
    """(estado, posición) si `s` ARRANCA con un emoji de estado (tolerando
    bold/espacios); (None, -1) si no."""
    head = s[:8]
    for ch, st in _EMOJI_STATUS:
        i = head.find(ch)
        if i != -1 and not head[:i].strip(" *-#["):
            return st, i + len(ch)
    return None, -1


def _clean_title(s):
    """Quita emojis de estado, bold, brackets y colas markdown del título."""
    for ch, _ in _EMOJI_STATUS:
        s = s.replace(ch, "")
    s = s.replace("️", "")          # variation selector suelto (⏸️)
    s = s.strip().strip("*_").strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip("[]").strip()


def _after_colon(s):
    if ":" in s:
        s = s.split(":", 1)[1]
    return s.strip(" -*").strip()


def parse_pendientes(text):
    """Parser TOLERANTE de STATE/PENDIENTES.md → lista de dicts.

    Cada item: {title, status, section, who, deadline, origin, context}.
    Reconoce: headings `### ⏳/✅/⏸️ Título`, bullets `⏳ **Título**`,
    checkboxes `- [ ] / - [x]`, y campos 👤/📌/🔗/📅. Ignora code fences y
    blockquotes. Devuelve lo que pudo parsear; nunca levanta.
    """
    items = []
    if not text or not isinstance(text, str):
        return items
    section, cur, fence = "", None, False
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("```"):
            fence = not fence
            continue
        if fence or not s or s.startswith(">"):
            continue
        if s.startswith("##") and not s.startswith("###"):
            section, cur = s.lstrip("#").strip(), None
            continue
        if s.startswith("#") and not s.startswith("###"):
            cur = None
            continue
        low = section.lower()
        if "formato" in low:
            continue
        status = None
        title = ""
        if s.startswith("###"):
            status, _ = _lead_status(s.lstrip("#").strip())
            title = _clean_title(s.lstrip("#"))
        else:
            m = _CHECKBOX_RE.match(s)
            if m:
                status = "done" if m.group(1).lower() == "x" else "open"
                title = _clean_title(m.group(2))
            else:
                st, pos = _lead_status(s)
                if st is not None:
                    status, title = st, _clean_title(s[pos:])
        if title and status != "skip":
            if status is None or status == "open":
                status = ("done" if "complet" in low else
                          "paused" if ("pausa" in low or "standby" in low) else
                          "open")
            cur = {"title": title[:160], "status": status, "section": section,
                   "who": "", "deadline": "", "origin": "", "context": ""}
            items.append(cur)
            continue
        if status == "skip":
            cur = None
            continue
        if cur is None:
            continue
        if "👤" in s:
            cur["who"] = _after_colon(s.split("👤", 1)[1])[:80]
        elif "📅" in s:
            rest = s.split("📅", 1)[1].strip(" :*-")
            m = _DATE_RE.search(rest)
            cur["deadline"] = (m.group(0) if m else parse_date(rest) or rest[:60]).strip()
        elif "🔗" in s:
            cur["origin"] = _after_colon(s.split("🔗", 1)[1])[:120]
        elif "📌" in s:
            cur["context"] = _after_colon(s.split("📌", 1)[1])[:200]
    return items


def read_pendientes(brain):
    """Lee STATE/PENDIENTES.md del cerebro y lo parsea. [] si no existe."""
    if not brain:
        return []
    return parse_pendientes(read_file(os.path.join(brain, "STATE", "PENDIENTES.md")))


# ═══════════════════════════════════════════════════════════════════════════
# Deliverables (extraído de calendar.py — simplificado para Mi Día)
# ═══════════════════════════════════════════════════════════════════════════

def read_deliverables(brain, max_per_project=20):
    """deliverables/<proy>/ → lista de archivos recientes.
    Cada item: {date, title, project, path, source}.
    Salta `_*` (inputs del cliente), README.md, ocultos. Falla-suave."""
    base = os.path.join(brain, "deliverables") if brain else ""
    out = []
    if not base or not os.path.isdir(base):
        return out
    try:
        slugs = sorted(os.listdir(base))
    except OSError:
        return out
    for proj_slug in slugs:
        proj = os.path.join(base, proj_slug)
        if proj_slug.startswith((".", "_")) or not os.path.isdir(proj):
            continue
        files = []
        try:
            for dirpath, dirnames, filenames in os.walk(proj):
                dirnames[:] = [d for d in dirnames if not d.startswith((".", "_"))]
                for f in filenames:
                    if f.startswith((".", "_")) or f == "README.md":
                        continue
                    fp = os.path.join(dirpath, f)
                    try:
                        mt = os.path.getmtime(fp)
                    except OSError:
                        continue
                    files.append((mt, f, os.path.relpath(fp, base)))
        except OSError:
            pass
        files.sort(reverse=True)
        for mt, f, rel in files[:max_per_project]:
            out.append({"date": datetime.date.fromtimestamp(mt).isoformat(),
                        "title": f, "project": proj_slug,
                        "path": rel, "source": "deliverables/" + proj_slug})
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Sessions (journals por socio)
# ═══════════════════════════════════════════════════════════════════════════

def read_sessions(brain, socio):
    """Journals de STATE/sessions/<socio>/ → lista de dicts.
    Cada item: {slug, title, estado, trabajo, actualizada, mtime, path}.
    Ordenado por mtime desc. Falla-suave."""
    d = os.path.join(brain, "STATE", "sessions", socio) if (brain and socio) else ""
    out = []
    if not d or not os.path.isdir(d):
        return out
    try:
        files = os.listdir(d)
    except OSError:
        return out
    for f in files:
        if not f.endswith(".md") or f.startswith("_") or f == "README.md":
            continue
        fp = os.path.join(d, f)
        if not os.path.isfile(fp):
            continue
        try:
            mt = os.path.getmtime(fp)
        except OSError:
            mt = 0
        fm = read_frontmatter(read_file(fp, 3000))
        out.append({
            "slug": f[:-3],
            "title": fm.get("titulo") or f[:-3],
            "estado": fm.get("estado", ""),
            "trabajo": fm.get("trabajo", ""),
            "actualizada": fm.get("actualizada", ""),
            "migrar": fm.get("migrar", ""),
            "mtime": mt,
            "path": fp,
        })
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Research-queue (encargos delegados a agentes)
# ═══════════════════════════════════════════════════════════════════════════

def read_queue(agent_brain, socio=None):
    """research-queue/ del cerebro del agente → lista de encargos.
    Cada item: {file, tema, solicita, estado, prioridad, fecha, mtime}.
    Si `socio` se pasa, filtra por `solicita` que contenga el socio (case-insensitive).
    Salta README.md, archivos `_*`, procesados/. Falla-suave."""
    qdir = os.path.join(agent_brain, "research-queue") if agent_brain else ""
    out = []
    if not qdir or not os.path.isdir(qdir):
        return out
    try:
        files = os.listdir(qdir)
    except OSError:
        return out
    for f in files:
        if (not f.endswith(".md") or f.startswith("_")
                or f.lower() == "readme.md"):
            continue
        fp = os.path.join(qdir, f)
        if not os.path.isfile(fp):
            continue
        fm = read_frontmatter(read_file(fp, 3000))
        if socio:
            solicita = fm.get("solicita", "").lower()
            if socio.lower() not in solicita and "equipo" not in solicita:
                continue
        try:
            mt = os.path.getmtime(fp)
        except OSError:
            mt = 0
        out.append({
            "file": f,
            "tema": fm.get("tema") or f[:-3],
            "solicita": fm.get("solicita", ""),
            "estado": fm.get("estado", "pendiente"),
            "prioridad": fm.get("prioridad", ""),
            "fecha": fm.get("fecha", ""),
            "mtime": mt,
            "path": fp,
        })
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Agentes: brain de Atlas vía registry
# ═══════════════════════════════════════════════════════════════════════════

def atlas_brain():
    """Cerebro de Atlas vía el registry real (igual que dispatch). '' si no
    resuelve en esta máquina — falla-suave."""
    try:
        import sys as _sys
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        from dispatch import find_agent, load_agent_cfg, resolve_brain
        e = find_agent("atlas")
        if e:
            return resolve_brain(e["name"], load_agent_cfg(e)) or ""
    except Exception:
        pass
    return ""


def agent_events(agent_name, agent_brain_path, limit=10):
    """Últimos `limit` eventos del rastro N10 para el agente dado.
    Devuelve lista de records normalizados (falla-suave: [] si no hay rastro)."""
    try:
        import sys as _sys
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in _sys.path:
            _sys.path.insert(0, _root)
        import events as _ev
        trail = _ev.read_events(limit=200)
        if not trail:
            return []
        ab = os.path.realpath(agent_brain_path) if agent_brain_path else ""

        def _match(rec):
            if (rec.get("agent") or "").lower() == (agent_name or "").lower():
                return True
            if ab and os.path.realpath(rec.get("brain") or "") == ab:
                return True
            p = rec.get("payload") or {}
            if ab and os.path.realpath(str(p.get("brain") or "")) == ab:
                return True
            return False

        return [r for r in trail if _match(r)][:limit]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Writers seguros (extraídos de capture.py — los módulos pueden reusarlos
# antes de que F-8 migre kanban/calendar)
# ═══════════════════════════════════════════════════════════════════════════

def inbox_append(brain, socio, op, titulo, campos, origen="dashboard WORKSPACE"):
    """APPEND a STATE/inbox/<socio>-AAAA-MM-DD.md — append-only SIEMPRE.
    `campos` = [(etiqueta, valor)]; vacíos se omiten. None si no pudo."""
    if not brain or not os.path.isdir(brain):
        return None
    who = re.sub(r"[^a-z0-9_-]", "", str(socio or "").lower())
    if not who:
        return None
    idir = os.path.join(brain, "STATE", "inbox")
    hoy = datetime.date.today().isoformat()
    fp = os.path.join(idir, "%s-%s.md" % (who, hoy))
    try:
        os.makedirs(idir, exist_ok=True)
        if not inside(idir, fp):
            return None
        fresh = not os.path.exists(fp)
        lines = ["## Entry — %s: %s" % (op, str(titulo).replace("\n", " ")[:160]),
                 "- op: %s" % op,
                 "- origen: %s" % origen]
        for k, v in campos:
            if v:
                lines.append("- %s: %s" % (k, str(v).replace("\n", " ")))
        with open(fp, "a", encoding="utf-8") as fh:
            if fresh:
                fh.write("# Inbox %s — %s\n" % (who, hoy))
            fh.write("\n" + "\n".join(lines) + "\n")
    except Exception:
        return None
    return fp


def queue_write(agent_brain_path, socio, tema, data=None):
    """Archivo NUEVO en research-queue/ del cerebro del agente.
    Formato de research-queue/_template.md. Nunca sobrescribe (sufijo -N).
    None si no pudo."""
    data = data or {}
    if not agent_brain_path or not os.path.isdir(agent_brain_path):
        return None
    qdir = os.path.join(agent_brain_path, "research-queue")
    try:
        os.makedirs(qdir, exist_ok=True)
    except OSError:
        return None
    hoy = datetime.date.today().isoformat()
    base = "%s-%s" % (hoy, slug(tema))
    fp, n = os.path.join(qdir, base + ".md"), 1
    while os.path.exists(fp):
        n += 1
        fp = os.path.join(qdir, "%s-%d.md" % (base, n))
    if not inside(qdir, fp):
        return None
    prio = data.get("prioridad") if data.get("prioridad") in ("alta", "media", "baja") else "media"
    body = (
        "---\n"
        "tema: %s\n"
        "solicita: %s (vía dashboard WORKSPACE)\n"
        "fecha: %s\n"
        "prioridad: %s\n"
        "estado: pendiente\n"
        "entregable: %s\n"
        "%s"
        "---\n\n"
        "## Tema\n%s\n\n"
        "## Alcance\n%s\n\n"
        "## Entregable esperado\n%s\n\n"
        "## Notas\nCapturado vía dashboard de WORKSPACE (_common.queue_write).\n"
    ) % (
        tema,
        (socio or "equipo").capitalize(),
        hoy, prio,
        data.get("entregable") or "resumen",
        ("deadline: %s\n" % str(data["deadline"]).replace("\n", " ")[:60])
        if data.get("deadline") else "",
        tema,
        data.get("alcance") or "<a criterio del agente>",
        data.get("entregable") or "resumen",
    )
    try:
        with open(fp, "w", encoding="utf-8") as fh:
            fh.write(body)
    except OSError:
        return None
    return fp
