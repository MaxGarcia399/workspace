#!/usr/bin/env python3
"""WORKSPACE · memory_blocks — core blocks acotados de MEMORY.md (N13, F2 de
memoria v2 — robo MemGPT/Letta aterrizado a archivos).

⛔ MÓDULO 100% READ-ONLY SOBRE EL CEREBRO. Mide, puntúa y SUGIERE — jamás
escribe, reescribe ni "migra" `STATE/MEMORY.md` (ni nada del cerebro). Las
secciones del socio las edita el agente en su sesión, a la vista; desde memoria
v1 (2026-10-17) el código sin IA de Workspace (`memoria.py`) escribe SOLO su
propia sección «Aprendido en las sesiones» y archiva lo viejo de ella. La puerta
`brain_write._write_brain_file` sigue sin escribir MEMORY.md.
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
en el bloque el resumen + puntero. Este módulo NO lo hace: solo mide y
AVISA (vía `workspace doctor` fase 8 o el CLI). El archivado automático es del
diseño de memoria de Workspace (2026-10-16): código sin IA, sin aprobación.

CLI (solo lectura, imprime y sale):
    python3 memory_blocks.py --brain "/ruta/al/CEREBRO"             # medición
    python3 memory_blocks.py --brain "/ruta/al/CEREBRO" --json      # JSON

Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Falla-suave.
Amputable (C10): borrarlo apaga la medición; el doctor degrada solo.
"""
import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

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

_BLOCK_RX = re.compile(r"^##\s*\[([^\]\s]+)\]\s*(.*)$")
_PLAIN_H2_RX = re.compile(r"^##\s+(.*)$")
_LIMITS_RX = re.compile(r"core-block-limits:((?:[^>]|>(?!-))*)", re.IGNORECASE)
_PAIR_RX = re.compile(r"([a-záéíóúñü][\w-]*)\s*=\s*(\d+)", re.IGNORECASE)

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
        lines.append("  → el bloque [%s] excede su cota — toca archivar el "
                     "excedente menos relevante a %s (lo hace el agente en su "
                     "sesión; Workspace solo archiva su sección «Aprendido en "
                     "las sesiones»)" % (label, ARCHIVE_REL.replace(os.sep, "/")))
    if measurement["loose"]:
        loose = ", ".join("«%s» (%s)" % (t, format(c, ","))
                          for t, c in measurement["loose"])
        lines.append("  (sin bloque): %s — secciones aún sin etiquetar" % loose)
    return lines


# ── CLI (imprime y sale; jamás escribe) ────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="memory_blocks.py",
        description="N13 — mide los core blocks de STATE/MEMORY.md. "
                    "READ-ONLY: jamás edita el cerebro.")
    ap.add_argument("--brain", default=os.getcwd(),
                    help="ruta del cerebro (default: cwd)")
    ap.add_argument("--json", action="store_true",
                    help="salida JSON (solo medición)")
    args = ap.parse_args(argv)
    brain = os.path.abspath(os.path.expanduser(args.brain))
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
