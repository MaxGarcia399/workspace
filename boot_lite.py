#!/usr/bin/env python3
"""WORKSPACE · boot_lite.py — Generador de digest de boot ≤4k chars (N17).

Diseño (§10-bis.2 Síntesis Robos Harnesses v1):
  - Lee el BOOT/ canónico de un cerebro y produce un digest «lite».
  - BOOT_FILES (convención Zenith 00-SOUL…04-BRAIN-MAP) es PREFERENCIA: si
    ninguno existe, se genera un digest GENÉRICO sobre BOOT/*.md ordenados
    por nombre con cap de tamaño (Atlas/Argus/convenciones alternas — QA
    ALTA-3: antes el digest quedaba vacío y el agente perdía su identidad).
  - El digest es DERIVADO y REGENERABLE: jamás es fuente de verdad.
  - Si BOOT/ cambia → regenerar. Nunca editar el digest a mano.
  - GATE 🔴 READ-ONLY: este módulo JAMÁS escribe ni modifica BOOT/ ni
    STATE/MEMORY.md. Solo lee esos archivos y escribe el digest al destino
    derivado (STATE/boot-lite.md dentro del cerebro, o --out explícito).

CLI:
    python3 boot_lite.py --brain <ruta>            # genera + guarda
    python3 boot_lite.py --brain <ruta> --show     # también imprime a stdout
    python3 boot_lite.py --brain <ruta> --out <p>  # ruta de salida custom
    python3 boot_lite.py --brain <ruta> --dry-run  # mide sin escribir

Stdout siempre: stats (canónico vs lite) y ruta de salida.

Garantías:
  - stdlib puro, cross-platform.
  - Falla suave si BOOT/ no existe (devuelve digest mínimo con advertencia).
  - Encoding UTF-8 explícito.
  - Límite configurable via MAX_CHARS (default 4000).

Consumidor previsto: motor #2 (small/local model). Por ahora standalone.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap
from typing import Optional

# ── Constantes ───────────────────────────────────────────────────────────────

MAX_CHARS = 4_000           # techo del digest
BOOT_FILES = [              # orden canónico de lectura (convención Zenith).
    "00-SOUL.md",           # Es PREFERENCIA, no requisito: si NINGUNO existe
    "01-IDENTITY.md",       # (Atlas usa 00-IDENTITY/01-SCOPE/…), el digest se
    "02-TEAM.md",           # genera GENÉRICO sobre BOOT/*.md ordenados por
    "03-RULES.md",          # nombre (con cap de tamaño) — antes quedaba VACÍO
    "04-BRAIN-MAP.md",      # y el agente respondía sin identidad (QA ALTA-3).
]
DIGEST_FILENAME = "boot-lite.md"   # dentro de STATE/ del cerebro
CANONICAL_PROTECTED = [            # GATE 🔴 — jamás escribir aquí
    "BOOT",
    os.path.join("STATE", "MEMORY.md"),
]

# ── Helpers de lectura (READ-ONLY) ────────────────────────────────────────────

def _read_file(path: str) -> str:
    """Lee un archivo y devuelve su contenido como string. Falla suave."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _boot_dir(brain: str) -> str:
    return os.path.join(brain, "BOOT")




# ── Extractor de secciones ────────────────────────────────────────────────────

def _extract_soul(content: str, budget: int) -> str:
    """00-SOUL: extraer nombre/rol + carácter + reglas de comportamiento clave."""
    if not content.strip():
        return ""
    lines = content.splitlines()
    # Tomamos el primer párrafo (título + descripción del agente) + sección Carácter
    # completa. Truncamos si supera el budget parcial.
    out_lines: list[str] = []
    in_character = False
    char_lines: list[str] = []
    header_lines: list[str] = []
    current_section = "header"

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Carácter"):
            current_section = "character"
            char_lines.append(line)
            in_character = True
            continue
        if stripped.startswith("## ") and in_character:
            # nueva sección después de Carácter → detener
            break
        if current_section == "header":
            header_lines.append(line)
        elif current_section == "character":
            char_lines.append(line)

    # Unir cabecera + carácter
    combined = "\n".join(header_lines).rstrip() + "\n\n" + "\n".join(char_lines).rstrip()
    # Agregar notas clave de autonomía y brevedad (siempre críticas para boot)
    autonomy_note = ""
    brevity_note = ""
    for line in lines:
        if "Autonomía por default" in line or "Autonomy" in line:
            autonomy_note = line.strip()
        if "Brevedad esencial" in line or "Brevity" in line:
            brevity_note = line.strip()

    if autonomy_note or brevity_note:
        notes = "\n\n**Notas clave:**"
        if autonomy_note:
            notes += f"\n- {autonomy_note}"
        if brevity_note:
            notes += f"\n- {brevity_note}"
        combined += notes

    # Recortar si es demasiado largo (presupuesto generoso para SOUL)
    if len(combined) > budget:
        combined = combined[:budget].rsplit("\n", 1)[0] + "\n…[ver 00-SOUL.md]"
    return combined.strip()


def _extract_identity(content: str) -> str:
    """01-IDENTITY: tarjeta completa (es corta, cabe íntegra)."""
    return content.strip()


def _extract_team(content: str, budget: int) -> str:
    """02-TEAM: nombres + roles, sin carpetas off-limits (detail on-demand)."""
    if not content.strip():
        return ""
    lines = content.splitlines()
    out: list[str] = []
    skip_next_offlimits = False
    for line in lines:
        s = line.strip()
        # Saltar líneas de carpetas off-limits (detalle; on-demand)
        if "Carpetas off-limits" in s or "off-limits" in s.lower():
            skip_next_offlimits = True
            continue
        if skip_next_offlimits and s.startswith("-"):
            continue
        skip_next_offlimits = False
        out.append(line)
    text = "\n".join(out).strip()
    if len(text) > budget:
        text = text[:budget].rsplit("\n", 1)[0] + "\n…[ver 02-TEAM.md]"
    return text


def _extract_rules(content: str, budget: int) -> str:
    """03-RULES: tabla de tiers + reglas inmutables (núcleo mínimo de seguridad)."""
    if not content.strip():
        return ""
    lines = content.splitlines()
    out: list[str] = []
    in_target = False
    sections_captured = 0
    target_sections = {"## Seguridad", "## Reglas inmutables", "## Red lines operativas"}

    for line in lines:
        stripped = line.strip()
        is_h2 = stripped.startswith("## ")
        if is_h2:
            if stripped in target_sections or any(stripped.startswith(t) for t in target_sections):
                in_target = True
                sections_captured += 1
                out.append(line)
                continue
            else:
                # Sección no prioritaria: skip (skill loop, sistemas referidos)
                in_target = False
                continue
        if in_target:
            out.append(line)

    text = "\n".join(out).strip()
    if len(text) > budget:
        text = text[:budget].rsplit("\n", 1)[0] + "\n…[ver 03-RULES.md]"
    return text


def _extract_brain_map(content: str, budget: int) -> str:
    """04-BRAIN-MAP: árbol de capas + tabla de STATE/ + tabla de consulta wiki."""
    if not content.strip():
        return ""
    lines = content.splitlines()
    out: list[str] = []
    # Capturar: cabecera + bloque de árbol de capas + tabla STATE/
    # Saltar secciones verbosas de adapters/, skills/ detalle, "cuándo no consultar"
    skip_sections = {
        "## adapters/ — runtime-specific",
        "## skills/ — capacidades operacionales + skill loop",
        "## Cuándo ESCRIBIR al cerebro",
        "## Cuándo NO consultar",
    }
    skip_now = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            skip_now = stripped in skip_sections or any(stripped.startswith(s) for s in skip_sections)
        if not skip_now:
            out.append(line)

    text = "\n".join(out).strip()
    if len(text) > budget:
        text = text[:budget].rsplit("\n", 1)[0] + "\n…[ver 04-BRAIN-MAP.md]"
    return text


# ── Digest GENÉRICO (convención BOOT alterna — Atlas/Argus/futuros) ──────────

def _boot_md_files(bdir: str) -> list:
    """BOOT/*.md ORDENADOS por nombre (la convención alterna: 00-IDENTITY,
    01-SCOPE, …). Excluye ocultos, `_*` y README. Falla suave: []."""
    try:
        return sorted(f for f in os.listdir(bdir)
                      if f.lower().endswith(".md")
                      and not f.startswith((".", "_"))
                      and f.lower() != "readme.md")
    except OSError:
        return []


# Punteros on-demand candidatos del digest genérico — SOLO se listan los que
# EXISTEN en el cerebro (un cerebro no-Zenith no tiene wiki/index.md y el
# digest no debe apuntar a rutas fantasma).
_POINTER_CANDIDATES = (
    ("STATE/MEMORY.md", "memoria curada largo plazo"),
    ("STATE/PENDIENTES.md", "pendientes activos"),
    ("STATE/queue.md", "cola de trabajo"),
    ("STATE/log.md", "bitácora"),
    ("STATE/brain-version.md", "versión + changelog reciente"),
    ("wiki/index.md", "wiki — drill down on-demand"),
    ("library", "biblioteca"),
    ("skills/README.md", "catálogo de capacidades operacionales"),
)


def _pointers_existing(brain: str) -> str:
    """Sección de punteros on-demand VERIFICADA contra el disco."""
    lines = ["## On-demand (leer cuando la tarea lo requiera)"]
    for rel, desc in _POINTER_CANDIDATES:
        p = os.path.join(brain, *rel.split("/"))
        if os.path.exists(p):
            label = rel + ("/" if os.path.isdir(p) else "")
            lines.append(f"- `{label}` — {desc}")
    if len(lines) == 1:
        lines = []
    lines.append("> NOTA: Este digest es DERIVADO de BOOT/. Si BOOT/ cambia → "
                 "regenerar con\n> `python3 boot_lite.py --brain <ruta>`. "
                 "Nunca editar este archivo a mano.")
    return "\n".join(lines)


def _generic_digest(brain: str, bdir: str, fnames: list, max_chars: int,
                    warnings: list) -> dict:
    """Digest sobre BOOT/*.md ordenados (cerebros que no siguen la convención
    Zenith). Misma forma de retorno que generate_digest. READ-ONLY igual."""
    raw = {}
    for fname in fnames:
        content = _read_file(os.path.join(bdir, fname))
        if content.strip():
            raw[fname] = content
    files_found = list(raw)
    canonical_chars = sum(len(v) for v in raw.values())
    warnings = list(warnings)
    warnings.append("BOOT/ no sigue la convención Zenith (00-SOUL…): digest "
                    "genérico sobre %d archivos BOOT/*.md ordenados"
                    % len(files_found))

    # nombre del agente: «- **Nombre:** X» en algún BOOT, si no el primer H1,
    # si no el nombre de la carpeta del cerebro.
    agent_name = os.path.basename(brain.rstrip("/\\"))
    h1 = ""
    for content in raw.values():
        for line in content.splitlines():
            if "**Nombre:**" in line:
                agent_name = line.split("**Nombre:**")[-1].strip()
                h1 = ""                              # el campo explícito manda
                break
            if not h1 and line.startswith("# "):
                h1 = line[2:].strip()
        if "**Nombre:**" in content:
            break
    if h1:
        agent_name = re.sub(r"^soy\s+", "", h1, flags=re.IGNORECASE)

    header = (f"# Boot Lite — {agent_name}\n\n"
              f"> Digest generado por WORKSPACE/boot_lite.py (N17). "
              f"≤{max_chars} chars.\n"
              f"> Canónico: {canonical_chars:,} chars · convención BOOT "
              f"alterna ({len(files_found)} archivos, ordenados por nombre).")
    pointers = _pointers_existing(brain)

    # presupuesto por archivo (cap de tamaño): lo usable repartido parejo.
    overhead = len(header) + len(pointers) + 12 * max(1, len(files_found))
    usable = max(400, max_chars - overhead)
    per = max(300, usable // max(1, len(files_found)))
    sections = [header]
    for fname, content in raw.items():
        body = content.strip()
        if len(body) > per:
            body = body[:per].rsplit("\n", 1)[0].rstrip() \
                + f"\n…[ver BOOT/{fname}]"
        sections.append(f"## {fname}\n\n{body}")
    sections.append(pointers)
    digest = "\n\n---\n\n".join(sections)
    if len(digest) > max_chars:                       # corte duro final
        digest = digest[:max_chars - 20].rsplit("\n", 1)[0]
        digest += "\n…[digest truncado]"

    return {
        "digest": digest,
        "chars": len(digest),
        "canonical_chars": canonical_chars,
        "warnings": warnings,
        "files_found": files_found,
    }


# ── Generador principal ───────────────────────────────────────────────────────

def generate_digest(brain: str, max_chars: int = MAX_CHARS) -> dict:
    """Lee BOOT/ canónico y devuelve el digest lite más metadatos.

    Returns:
        {
          "digest": str,            # texto del digest
          "chars": int,             # largo del digest
          "canonical_chars": int,   # largo total del canónico (BOOT files)
          "warnings": list[str],    # advertencias (ej. archivos faltantes)
          "files_found": list[str], # archivos BOOT leídos
        }
    GATE 🔴: esta función NUNCA escribe a BOOT/ ni a STATE/MEMORY.md.
    """
    bdir = _boot_dir(brain)
    warnings: list[str] = []
    files_found: list[str] = []

    if not os.path.isdir(bdir):
        warnings.append(f"BOOT/ no encontrado en: {bdir}")

    # Leer todos los archivos BOOT (convención Zenith, preferida)
    raw: dict[str, str] = {}
    for fname in BOOT_FILES:
        p = os.path.join(bdir, fname)
        content = _read_file(p)
        raw[fname] = content
        if content:
            files_found.append(fname)
        else:
            warnings.append(f"Archivo no encontrado o vacío: {fname}")

    # NINGÚN archivo canónico → convención BOOT alterna (Atlas: 00-IDENTITY,
    # 01-SCOPE, …): digest GENÉRICO sobre BOOT/*.md ordenados por nombre.
    # Antes el digest quedaba vacío ("0 chars") y el agente respondía sin
    # identidad (QA ALTA-3).
    if not files_found:
        generic = _boot_md_files(bdir)
        if generic:
            return _generic_digest(brain, bdir, generic, max_chars, warnings)

    canonical_chars = sum(len(v) for v in raw.values())

    # ── Budget allocation (max_chars se reparte entre secciones) ──
    # Pesos aproximados: SOUL 30%, IDENTITY 5%, TEAM 15%, RULES 30%, MAP 20%
    # + overhead de encabezado/separadores ~200 chars
    overhead = 220
    usable = max_chars - overhead
    budgets = {
        "00-SOUL.md":    int(usable * 0.30),
        "01-IDENTITY.md": int(usable * 0.05),
        "02-TEAM.md":    int(usable * 0.15),
        "03-RULES.md":   int(usable * 0.30),
        "04-BRAIN-MAP.md": int(usable * 0.20),
    }

    # ── Extraer secciones ──
    soul    = _extract_soul(raw["00-SOUL.md"],     budgets["00-SOUL.md"])
    ident   = _extract_identity(raw["01-IDENTITY.md"])
    team    = _extract_team(raw["02-TEAM.md"],     budgets["02-TEAM.md"])
    rules   = _extract_rules(raw["03-RULES.md"],   budgets["03-RULES.md"])
    bmap    = _extract_brain_map(raw["04-BRAIN-MAP.md"], budgets["04-BRAIN-MAP.md"])

    # ── Nombre del agente (de IDENTITY o fallback al nombre de carpeta) ──
    agent_name = os.path.basename(brain.rstrip("/\\"))
    for line in raw.get("01-IDENTITY.md", "").splitlines():
        if line.startswith("- **Nombre:**"):
            agent_name = line.split("**Nombre:**")[-1].strip()
            break

    # ── Punteros on-demand (siempre presentes, pesan poco) ──
    pointers = textwrap.dedent(f"""\
        ## On-demand (leer cuando la tarea lo requiera)
        - `STATE/MEMORY.md` — memoria curada largo plazo
        - `STATE/PENDIENTES.md` — pendientes activos
        - `STATE/brain-version.md` — versión + changelog reciente
        - `wiki/index.md` → drill down a entities/concepts/projects/sources
        - `adapters/<runtime>.md` — cowork / claude-code / anthropic-sdk / hermes
        - `skills/README.md` → catálogo de capacidades operacionales

        > NOTA: Este digest es DERIVADO de BOOT/. Si BOOT/ cambia → regenerar con
        > `python3 boot_lite.py --brain <ruta>`. Nunca editar este archivo a mano.""")

    # ── Ensamblar digest ──
    sep = "\n\n---\n\n"
    sections = []
    header = f"# Boot Lite — {agent_name}\n\n" \
             f"> Digest generado por WORKSPACE/boot_lite.py (N17). ≤{max_chars} chars.\n" \
             f"> Canónico: {canonical_chars:,} chars · Lite: ~{max_chars:,} chars máx."

    sections.append(header)
    if soul:
        sections.append(f"## Identidad y carácter\n\n{soul}")
    if ident:
        sections.append(f"## Tarjeta\n\n{ident}")
    if team:
        sections.append(f"## Equipo\n\n{team}")
    if rules:
        sections.append(f"## Reglas operativas (resumen)\n\n{rules}")
    if bmap:
        sections.append(f"## Mapa del cerebro\n\n{bmap}")
    sections.append(pointers)

    digest = sep.join(sections)

    # ── Ajuste final: si supera max_chars, recortar secciones de mayor a menor ──
    if len(digest) > max_chars:
        # Recortar primero el brain map, luego rules, luego team
        trim_order = [
            (f"## Mapa del cerebro\n\n{bmap}", bmap, "04-BRAIN-MAP.md"),
            (f"## Reglas operativas (resumen)\n\n{rules}", rules, "03-RULES.md"),
            (f"## Equipo\n\n{team}", team, "02-TEAM.md"),
        ]
        for old_block, section_text, fname in trim_order:
            if len(digest) <= max_chars:
                break
            if not section_text:
                continue
            over = len(digest) - max_chars + 30  # margen
            new_text = section_text[: max(0, len(section_text) - over)].rsplit("\n", 1)[0]
            new_text += f"\n…[ver {fname}]"
            digest = digest.replace(section_text, new_text, 1)

        # Último recurso: corte duro
        if len(digest) > max_chars:
            digest = digest[:max_chars - 20].rsplit("\n", 1)[0]
            digest += "\n…[digest truncado]"

    return {
        "digest": digest,
        "chars": len(digest),
        "canonical_chars": canonical_chars,
        "warnings": warnings,
        "files_found": files_found,
    }


# ── Escritura del digest (destino derivado) ───────────────────────────────────

def _default_out_path(brain: str) -> str:
    """Ruta por defecto: STATE/boot-lite.md dentro del cerebro.

    GATE 🔴: NO dentro de BOOT/ ni sobrescribir MEMORY.md.
    """
    return os.path.join(brain, "STATE", DIGEST_FILENAME)


def write_digest(brain: str, digest: str, out_path: Optional[str] = None) -> str:
    """Escribe el digest al destino derivado. Devuelve la ruta real escrita.

    GATE 🔴 VERIFICACIÓN: aborta si out_path apunta a BOOT/ o a MEMORY canónico.
    """
    dest = out_path or _default_out_path(brain)
    dest = os.path.abspath(dest)

    # ── GATE 🔴: verificar que no estamos escribiendo a zonas protegidas ──
    brain_abs = os.path.abspath(brain)
    boot_abs  = os.path.join(brain_abs, "BOOT")
    mem_abs   = os.path.join(brain_abs, "STATE", "MEMORY.md")

    # Normalizar para comparación cross-platform
    dest_norm = os.path.normcase(dest)
    boot_norm = os.path.normcase(boot_abs)
    mem_norm  = os.path.normcase(mem_abs)

    if dest_norm.startswith(boot_norm + os.sep) or dest_norm == boot_norm:
        raise ValueError(
            f"GATE 🔴 VIOLADO: el digest no puede escribirse dentro de BOOT/.\n"
            f"  Destino rechazado: {dest}"
        )
    if dest_norm == mem_norm:
        raise ValueError(
            f"GATE 🔴 VIOLADO: el digest no puede sobrescribir STATE/MEMORY.md.\n"
            f"  Destino rechazado: {dest}"
        )

    # Crear directorio si no existe (normal para STATE/)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(digest)
    return dest


# ── CLI ───────────────────────────────────────────────────────────────────────

def _resolve_brain_from_cli(brain_arg: Optional[str]) -> str:
    """Resuelve el path del cerebro: argumento CLI → env WORKSPACE_BRAIN → error."""
    if brain_arg:
        return os.path.abspath(os.path.expanduser(brain_arg))
    env = os.environ.get("WORKSPACE_BRAIN", "").strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))
    raise SystemExit(
        "ERROR: Debes especificar el cerebro.\n"
        "  --brain <ruta>  o  export WORKSPACE_BRAIN=<ruta>"
    )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="WORKSPACE boot_lite — genera digest ≤4k chars de BOOT/ canónico (N17)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Ejemplos:
              python3 boot_lite.py --brain ~/Desktop/ZENITH\\ -\\ BRAIN
              python3 boot_lite.py --brain ~/Desktop/ZENITH\\ -\\ BRAIN --show
              python3 boot_lite.py --brain ~/Desktop/ZENITH\\ -\\ BRAIN --dry-run
              python3 boot_lite.py --brain ~/Desktop/ZENITH\\ -\\ BRAIN --out /tmp/boot.md

            El digest se escribe a STATE/boot-lite.md dentro del cerebro (default).
            GATE 🔴: BOOT/ y STATE/MEMORY.md nunca son modificados.
        """),
    )
    parser.add_argument("--brain", metavar="PATH",
                        help="Ruta al cerebro del agente")
    parser.add_argument("--out", metavar="PATH",
                        help="Ruta de salida custom (default: <brain>/STATE/boot-lite.md)")
    parser.add_argument("--show", action="store_true",
                        help="Imprimir el digest a stdout además de guardarlo")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generar y medir, pero NO escribir el archivo")
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS,
                        help=f"Techo de chars del digest (default: {MAX_CHARS})")

    args = parser.parse_args(argv)
    brain = _resolve_brain_from_cli(args.brain)

    result = generate_digest(brain, max_chars=args.max_chars)
    digest  = result["digest"]
    chars   = result["chars"]
    canon   = result["canonical_chars"]
    warnings = result["warnings"]

    # ── Imprimir stats siempre ──
    ratio = (chars / canon * 100) if canon else 0
    print(f"\n  boot_lite — N17")
    print(f"  Brain:     {brain}")
    print(f"  Canónico:  {canon:,} chars  (~{canon // 4:,} tokens aprox.)")
    print(f"  Digest:    {chars:,} chars  (~{chars // 4:,} tokens aprox.)  "
          f"[{ratio:.1f}% del canónico]")
    print(f"  Límite:    {args.max_chars:,} chars  "
          f"{'✓ OK' if chars <= args.max_chars else '⚠ EXCEDE LÍMITE'}")

    if warnings:
        for w in warnings:
            print(f"  ⚠ {w}")

    # ── Escribir o mostrar ──
    if args.dry_run:
        print(f"  dry-run: no se escribió ningún archivo.")
        if args.show:
            print("\n" + "─" * 60 + "\n")
            print(digest)
    else:
        try:
            dest = write_digest(brain, digest, out_path=args.out or None)
            print(f"  Digest escrito → {dest}")
        except ValueError as exc:
            print(f"\n{exc}", file=sys.stderr)
            return 1
        if args.show:
            print("\n" + "─" * 60 + "\n")
            print(digest)

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
