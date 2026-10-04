#!/usr/bin/env python3
"""WORKSPACE · memory_blocks — core blocks acotados de MEMORY.md (N13, F2 de
memoria v2 — robo MemGPT/Letta aterrizado a archivos).

⛔ MÓDULO 100% READ-ONLY SOBRE EL CEREBRO. Mide, puntúa y SUGIERE — jamás
escribe, reescribe ni "migra" `STATE/MEMORY.md` (ni nada del cerebro). La
edición de MEMORY.md es humana POR DISEÑO (gate 🔴 de N13, nucleo-plan §1;
misma ley que el chokepoint `dream._write_brain_file` hace cumplir en N1).
Este archivo no contiene NINGUNA escritura: la única salida es stdout.

CONVENCIÓN DE CORE BLOCKS (MemGPT core memory → secciones de MEMORY.md):
La memoria semántica "siempre inyectada" se estructura en bloques etiquetados
y ACOTADOS (límite suave en chars). Un bloque se declara etiquetando el
heading de nivel 2:

    ## [proyectos] Clientes / iniciativas activas

- El bloque abarca hasta el siguiente `## ` (etiquetado o no).
- Varias secciones pueden compartir etiqueta → se SUMAN como un solo bloque
  (permite migrar sin reordenar el archivo: cero movimientos de contenido).
- Un `## Heading` sin etiqueta cuenta aparte como "(sin bloque)" — medido e
  informado, nunca error (la migración puede ser gradual).
- Lo anterior al primer `## ` es el preámbulo (intro del archivo; sin cota).

Bloques estándar del equipo y cotas default (chars; adaptación a equipo de
los `persona`/`human` de MemGPT — calibradas para que la suma quepa en el
presupuesto Y8 de 12k chars/archivo de boot):

    [persona]       2000  identidad operativa del agente, modo de operación
    [equipo]        1500  socios, roles, autoridad
    [empresa]       2500  la empresa: legal, modelo, dominios, marca
    [proyectos]     2500  clientes / iniciativas / deliverables ACTIVOS
    [infra]         2500  runtime, infraestructura, decisiones técnicas vigentes
    [preferencias]  1500  preferencias explícitas de socios + convenciones
    [pendientes]    1000  pendientes de diseño / contexto vivo

Etiquetas fuera de la lista valen (cota default 2000). Cada cerebro puede
recalibrar sus cotas con una línea dentro de un comentario HTML de cabecera:

    <!-- core-block-limits: proyectos=3000 empresa=2000 -->

DECAY / ARCHIVO DEL EXCEDENTE (cuando un bloque excede su cota):
El excedente MENOS RELEVANTE se ARCHIVA — jamás se borra (olvido = degradar
a capa más fría, Modelos_De_Memoria §5.3c): mover el detalle frío a
`STATE/memoria-archivo/<bloque>-YYYY-MM.md` (o destilarlo a `wiki/`) dejando
en el bloque el resumen + puntero. Eso lo hace UN HUMANO (o Atlas en
consolidación CON gate de revisión) — nunca este módulo ni el pipeline
nocturno. Este módulo solo AVISA (vía `workspace doctor` fase 8 o el CLI).

RELEVANCE SCORING DE PROMOCIÓN (criterio para el humano, no automatismo):
Los candidatos que N1 (dream.py) deja en `STATE/DESTILADO.md` + staging
per-máquina traen `final_score` = score del destilador (0-100) + boost de
recall-frequency (recurre en otras sesiones). La promoción a un core block
añade RECENCIA:

    promo_score = final_score + recency_bonus
    recency_bonus = RECENCY_BOOST × max(0, 1 − edad_días/RECENCY_WINDOW_DAYS)

y sugiere a qué bloque iría cada candidato (por `tipo` y keywords). El
ranking ordena la cola de revisión humana — promover sigue siendo copiar a
mano el texto a MEMORY.md y marcar el checkbox en DESTILADO.md (gate 🟡 N1).

CLI (solo lectura, imprime y sale):
    python3 memory_blocks.py --brain "/ruta/al/CEREBRO"             # medición
    python3 memory_blocks.py --brain "/ruta/al/CEREBRO" --suggest   # ranking

Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Falla-suave.
Amputable (C10): borrarlo apaga la medición; el doctor degrada solo.
"""
import argparse
import datetime
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# dream.py (N1) es la fuente del staging de candidatos — import tolerante:
# sin él, la medición de bloques sigue funcionando y --suggest lo reporta.
try:
    import dream
except Exception:
    dream = None

MEMORY_REL = os.path.join("STATE", "MEMORY.md")
ARCHIVE_REL = os.path.join("STATE", "memoria-archivo")

# Cotas suaves default por bloque (chars). La suma (13.5k) ronda el
# presupuesto Y8 por archivo (12k) a propósito: si todos los bloques van al
# tope, el archivo entero ya amerita dieta (doctor.BOOT_BUDGET_FILE avisa).
DEFAULT_BLOCKS = {
    "persona": 2000,
    "equipo": 1500,
    "empresa": 2500,
    "proyectos": 2500,
    "infra": 2500,
    "preferencias": 1500,
    "pendientes": 1000,
}
DEFAULT_BLOCK_LIMIT = 2000        # etiquetas fuera del set estándar

RECENCY_BOOST = 10                # bonus máximo por candidato fresquito
RECENCY_WINDOW_DAYS = 30          # decay lineal hasta 0 en esta ventana
JACCARD_DUP = 0.7                 # colapso de casi-duplicados en el ranking
SUGGEST_TOP_DEFAULT = 15

_BLOCK_RX = re.compile(r"^##\s*\[([^\]\s]+)\]\s*(.*)$")
_PLAIN_H2_RX = re.compile(r"^##\s+(.*)$")
_LIMITS_RX = re.compile(r"core-block-limits:((?:[^>]|>(?!-))*)", re.IGNORECASE)
_PAIR_RX = re.compile(r"([a-záéíóúñü][\w-]*)\s*=\s*(\d+)", re.IGNORECASE)
_WORD_RX = re.compile(r"[a-záéíóúñü0-9]{3,}")

# Sugerencia de bloque destino: primero por `tipo` del candidato (contrato
# del destilador N1), luego por keywords del texto. None = no va a MEMORY.
_TIPO_BLOCK = {
    "preferencia": "preferencias",
    "convencion": "preferencias",
    "skill-candidata": None,      # su destino es el Skill Loop, no MEMORY.md
}
_BLOCK_KEYWORDS = (
    ("proyectos", ("cliente", "proyecto", "entrega", "entregable",
                   "deadline", "deliverable", "propuesta", "fase",
                   "cotización", "cotizacion", "pitch")),
    ("empresa", ("empresa", "legal", "s.c.", "constitución", "constitucion",
                 "dominio", "marca", "notario", "contrato", "factura",
                 "estatutos")),
    ("infra", ("vps", "hermes", "repo", "runtime", "servidor", "infra",
               "harness", "workspace", "sync", "backup", "modelo", "api",
               "hosting", "deploy")),
    ("equipo", ("socio", "socios", "autoridad", "rol", "roles", "consenso",
                "max", "fer", "mau")),
    ("persona", ("agente", "zenith", "atlas", "identidad", "tono",
                 "operación", "operacion")),
)


# ── medición de core blocks (read-only) ────────────────────────────────────
def parse_limit_overrides(text):
    """Cotas recalibradas en el comentario de cabecera del propio MEMORY.md
    (`core-block-limits: bloque=chars …`). Devuelve {label: limit}."""
    m = _LIMITS_RX.search(text or "")
    if not m:
        return {}
    out = {}
    for label, n in _PAIR_RX.findall(m.group(1)):
        try:
            out[label.lower()] = max(0, int(n))
        except ValueError:
            continue
    return out


def measure_text(text):
    """Mide los core blocks de un MEMORY.md (texto). Pura: no toca disco.

    Devuelve {"total", "preamble", "has_blocks", "limits",
              "blocks": {label: {"chars","limit","over","excess","sections"}},
              "loose": [(titulo, chars)]}.
    Secciones repetidas con la misma etiqueta se SUMAN (un solo bloque).
    """
    limits = dict(DEFAULT_BLOCKS)
    limits.update(parse_limit_overrides(text))
    blocks, loose, order = {}, [], []
    preamble = 0
    cur = ("pre", None)          # ("pre",) | ("block", label) | ("loose", idx)
    for line in (text or "").splitlines():
        n = len(line) + 1        # +1 por el salto de línea
        mb = _BLOCK_RX.match(line)
        if mb:
            label = mb.group(1).lower()
            title = (mb.group(2) or "").strip() or label
            b = blocks.setdefault(label, {"chars": 0, "sections": []})
            if label not in order:
                order.append(label)
            b["sections"].append(title)
            b["chars"] += n
            cur = ("block", label)
            continue
        mp = _PLAIN_H2_RX.match(line)
        if mp:
            loose.append([mp.group(1).strip(), n])
            cur = ("loose", len(loose) - 1)
            continue
        if cur[0] == "pre":
            preamble += n
        elif cur[0] == "block":
            blocks[cur[1]]["chars"] += n
        else:
            loose[cur[1]][1] += n
    out_blocks = {}
    for label in order:
        b = blocks[label]
        limit = limits.get(label, DEFAULT_BLOCK_LIMIT)
        out_blocks[label] = {
            "chars": b["chars"], "limit": limit,
            "over": b["chars"] > limit,
            "excess": max(0, b["chars"] - limit),
            "sections": b["sections"],
        }
    return {
        "total": len(text or ""),
        "preamble": preamble,
        "has_blocks": bool(out_blocks),
        "limits": limits,
        "blocks": out_blocks,
        "loose": [tuple(x) for x in loose],
    }


def measure(path):
    """Mide el MEMORY.md en `path`. SOLO lectura (modo "r", jamás escribe)."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    m = measure_text(text)
    m["path"] = path
    return m


def overflowing(measurement):
    """[(label, info)] de los bloques que exceden su cota suave."""
    return [(label, b) for label, b in measurement["blocks"].items()
            if b["over"]]


def report_lines(measurement, name=""):
    """Reporte humano de la medición (lista de líneas)."""
    tag = (" de %s" % name) if name else ""
    lines = ["MEMBLOCKS: %s%s — %s chars" % (
        os.path.basename(measurement.get("path") or "MEMORY.md"), tag,
        format(measurement["total"], ","))]
    if not measurement["has_blocks"]:
        lines.append("  (sin core blocks declarados — convención N13: etiqueta"
                     " los headings `## [bloque] Título`; la migración es"
                     " humana)")
        return lines
    for label, b in measurement["blocks"].items():
        mark = "⚠ EXCEDE" if b["over"] else "ok"
        lines.append("  [%s] %s / %s chars · %s%s" % (
            label, format(b["chars"], ","), format(b["limit"], ","), mark,
            " (+%s)" % format(b["excess"], ",") if b["over"] else ""))
    for label, b in overflowing(measurement):
        lines.append("  → el bloque [%s] excede su cota — toca destilar/"
                     "archivar el excedente menos relevante a %s (humano o "
                     "Atlas con gate; el pipeline no toca MEMORY.md)"
                     % (label, ARCHIVE_REL.replace(os.sep, "/")))
    if measurement["loose"]:
        loose = ", ".join("«%s» (%s)" % (t, format(c, ","))
                          for t, c in measurement["loose"])
        lines.append("  (sin bloque): %s — secciones aún sin etiquetar" % loose)
    return lines


# ── relevance scoring de promoción (criterio gated, no automatismo) ───────
def _tokens(text):
    return set(_WORD_RX.findall((text or "").lower()))


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _age_days(ts, now=None):
    """Edad en días de un timestamp ISO del staging; None si no parsea."""
    try:
        t = datetime.datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    now = now or datetime.datetime.now()
    if t.tzinfo is not None:
        t = t.replace(tzinfo=None)
    return max(0.0, (now - t).total_seconds() / 86400.0)


def recency_bonus(ts, now=None):
    """0..RECENCY_BOOST con decay lineal en RECENCY_WINDOW_DAYS. Sin
    timestamp parseable → 0 (lo viejo/desconocido no recibe bonus)."""
    age = _age_days(ts, now)
    if age is None:
        return 0
    return int(round(RECENCY_BOOST * max(0.0, 1.0 - age / RECENCY_WINDOW_DAYS)))


def suggest_block(candidate):
    """A qué core block iría el candidato (sugerencia, no destino forzoso).
    Devuelve la etiqueta, None (no va a MEMORY — p.ej. skill-candidata) o
    "(a criterio)" si no hay señal clara."""
    tipo = str(candidate.get("tipo", "")).lower()
    if tipo in _TIPO_BLOCK:
        return _TIPO_BLOCK[tipo]
    text = ("%s %s" % (candidate.get("texto", ""),
                       candidate.get("razon", ""))).lower()
    best, hits = None, 0
    for label, kws in _BLOCK_KEYWORDS:
        h = sum(1 for k in kws if k in text)
        if h > hits:
            best, hits = label, h
    return best or "(a criterio)"


def staged_candidates(brain):
    """Candidatos del staging N1 de este cerebro (read-only). Sin dream.py
    (módulo amputado) → None."""
    if dream is None:
        return None
    try:
        return dream._load_staged(dream._brain_enc(brain))
    except Exception:
        return None


def promotion_rank(staged, now=None):
    """Ordena candidatos del staging por mérito de promoción a MEMORY.md.

    promo_score = final_score (score N1 + recall) + recency_bonus.
    Casi-duplicados entre sesiones (Jaccard ≥ JACCARD_DUP) se colapsan en
    una entrada (gana la de mayor promo_score; `sessions` los cuenta).
    SOLO produce un ranking informativo — la promoción es humana.
    """
    ranked = []
    for c in staged or []:
        try:
            base = int(c.get("final_score", c.get("score", 0)))
        except (TypeError, ValueError):
            base = 0
        rec = recency_bonus(c.get("ts"), now)
        ranked.append({
            "texto": str(c.get("texto", "")).strip(),
            "tipo": str(c.get("tipo", "hecho")),
            "razon": str(c.get("razon", "")),
            "final_score": base,
            "recency": rec,
            "recall_freq": c.get("recall_freq", 0),
            "promo_score": base + rec,
            "session_id": c.get("session_id", ""),
            "ts": c.get("ts", ""),
            "suggested_block": suggest_block(c),
            "sessions": 1,
        })
    ranked.sort(key=lambda x: -x["promo_score"])
    out = []
    for c in ranked:
        toks = _tokens(c["texto"])
        dup = next((k for k in out
                    if _jaccard(toks, k["_toks"]) >= JACCARD_DUP), None)
        if dup is not None:
            dup["sessions"] += 1
            continue
        c["_toks"] = toks
        out.append(c)
    for c in out:
        del c["_toks"]
    return out


def suggest_lines(brain, top=SUGGEST_TOP_DEFAULT, now=None):
    """Reporte humano del ranking de promoción (lista de líneas)."""
    staged = staged_candidates(brain)
    head = ("MEMBLOCKS: promoción — ranking informativo; promover = humano "
            "(copiar a MEMORY.md + checkbox en DESTILADO.md)")
    if staged is None:
        return [head, "  (sin staging N1: dream.py no disponible o ilegible)"]
    if not staged:
        return [head, "  (staging vacío — corre `python3 dream.py --brain …` "
                      "primero)"]
    lines = [head]
    for c in promotion_rank(staged, now=now)[:max(1, top)]:
        dest = c["suggested_block"]
        dest = ("→ [%s]" % dest if dest and not str(dest).startswith("(")
                else "→ skills/ (Skill Loop, no MEMORY)" if dest is None
                else "→ %s" % dest)
        extra = []
        if c["recall_freq"]:
            extra.append("recall ×%s" % c["recall_freq"])
        if c["recency"]:
            extra.append("recencia +%d" % c["recency"])
        if c["sessions"] > 1:
            extra.append("%d sesiones" % c["sessions"])
        lines.append("  %3d %s · %s %s%s" % (
            c["promo_score"], dest, c["tipo"], c["texto"][:110],
            " (%s)" % ", ".join(extra) if extra else ""))
    return lines


# ── CLI (imprime y sale; jamás escribe) ────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="memory_blocks.py",
        description="N13 — mide los core blocks de STATE/MEMORY.md y rankea "
                    "candidatos de promoción. READ-ONLY: jamás edita el "
                    "cerebro; archivar/promover es trabajo humano (gated).")
    ap.add_argument("--brain", default=os.getcwd(),
                    help="ruta del cerebro (default: cwd)")
    ap.add_argument("--suggest", action="store_true",
                    help="ranking de candidatos del staging N1 (en vez de "
                         "medir bloques)")
    ap.add_argument("--top", type=int, default=SUGGEST_TOP_DEFAULT,
                    help="máx candidatos en --suggest (default %d)"
                         % SUGGEST_TOP_DEFAULT)
    ap.add_argument("--json", action="store_true",
                    help="salida JSON (solo medición)")
    args = ap.parse_args(argv)
    brain = os.path.abspath(os.path.expanduser(args.brain))
    if args.suggest:
        for line in suggest_lines(brain, top=args.top):
            print(line)
        return 0
    path = os.path.join(brain, MEMORY_REL)
    if not os.path.isfile(path):
        print("MEMBLOCKS: ERROR — no existe %s" % path)
        return 2
    try:
        m = measure(path)
    except OSError as e:
        print("MEMBLOCKS: ERROR — ilegible: %s" % e)
        return 2
    if args.json:
        print(json.dumps(m, ensure_ascii=False, indent=1))
        return 0
    for line in report_lines(m, name=os.path.basename(brain)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
