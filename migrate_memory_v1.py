#!/usr/bin/env python3
"""WORKSPACE · migrate_memory_v1 — migra UN cerebro a la estructura E1/E2 del
template (memoria por capas).

POR QUÉ: los cerebros actuales tienen destilados planos en
`STATE/sessions/<socio>/destilados/<fecha>-<slug>-<sid8>.md` en vez de la
convención por MES `STATE/sessions/<socio>/<YYYY-MM>/<fecha>-<slug>.md`.
Además faltan STATE/INDEX.md, STATE/log-archive/ y STATE/memoria-archivo/.
Este script migra la estructura a E1/E2 de forma SEGURA.

QUÉ HACE (patrón EXACTO de migrate_chat_identity.py):
  1. Mueve destilados planos → convención por mes (YYYY-MM/).
  2. Crea STATE/INDEX.md si no existe (sembrado desde proyectos detectados).
  3. Crea STATE/log-archive/ si no existe (con README).
  4. Crea STATE/memoria-archivo/ si no existe (con README).
  5. AVISA sobre boot.md legado (si existe) — NO lo borra (decisión humana).

JAMÁS TOCA:
  · BOOT/ ni ningún archivo dentro (identidad inmutable, N3).
  · STATE/MEMORY.md (canónico curado — gate humano).
  · Cualquier path fuera del cerebro declarado (anti-traversal).

SEGURIDAD (patrón migrate_chat_identity.py):
  · DEFAULT = DRY-RUN: imprime exactamente qué haría sin escribir nada.
    Aplicar es una decisión deliberada: --apply.
  · Escritura atómica (tmp + os.replace): jamás pisa un archivo a medias.
  · Anti-traversal: valida que todos los paths destino estén bajo el cerebro.
  · Falla-suave: un archivo podrido se reporta y se salta.
  · Idempotente: re-correr no duplica ni rompe nada.

USO:
    python3 migrate_memory_v1.py --brain "/ruta/al/CEREBRO"        # dry-run
    python3 migrate_memory_v1.py --brain "/ruta/al/CEREBRO" --apply  # aplicar
    python3 migrate_memory_v1.py --brain "/ruta/al/CEREBRO" --stage 1
    python3 migrate_memory_v1.py --brain "/ruta/al/CEREBRO" --stage 2

stdlib puro (3.9+), Mac y Windows.
NO ejecutar sobre cerebros vivos — solo sobre cerebros temporales o tras
confirmación explícita del socio dueño.
"""
import argparse
import datetime
import os
import re
import sys

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── archivos PROHIBIDOS (nunca tocar, sin excepción) ─────────────────────
FORBIDDEN_DIRS = ("BOOT",)
FORBIDDEN_FILES = ("MEMORY.md", "memory.md")

# Patrón de destilado plano: <fecha>-<slug>-<sid8>.md
# Grupo 1: fecha YYYY-MM-DD, Grupo 2: resto (slug + sid8)
# Nota: el sid8 es 8 hex al final antes de .md
_DESTILADO_FLAT_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2})-(.+)-[0-9a-f]{8}\.md$', re.IGNORECASE)

# Patrón de mes para directorio destino: YYYY-MM
_MONTH_RE = re.compile(r'^\d{4}-\d{2}$')

# Líneas del INDEX.md sembrado por defecto
_INDEX_TEMPLATE = """\
# Índice — qué hay y dónde (contrato de retrieval)

<!-- Tope: 100 líneas. 1 línea por entidad/proyecto/decisión VIVA → path.
     Lo mantiene el consolidador (cron, nightly) + humano en sesión.
     Si rebasa 100 líneas: CONSOLIDAR (fusionar/archivar entradas muertas),
     nunca ampliar. Entradas cerradas/muertas → mover a sección Archivo o
     borrar la línea (el contenido NO se borra — sigue en su capa, alcanzable
     por grep o FTS5 en E3). Falla-suave: sin INDEX.md el agente opera como E1. -->

## Proyectos
{proyectos}

## Decisiones vigentes
{decisiones}

## Entidades
{entidades}

## Convenciones
- Append-only STATE + single-writer de canónicos → `wiki/concepts/append-only-state.md` (si existe)
- Sesiones por pestaña/socio → `STATE/sessions/README.md`
- Memoria por capas HOT/WARM/COLD → `BOOT/04-BRAIN-MAP.md`
- Skills: INDEX-LITE (HOT) · README completo (WARM) · skill JIT al detectar tarea → `skills/INDEX-LITE.md`

## Archivo
<!-- Entradas que ya no están activas pero conviene recordar dónde quedaron.
     No borrar: la línea describe dónde vivía algo → path en COLD (memoria-archivo/, log-archive/) -->
*(vacío al nacer)*
"""

_LOG_ARCHIVE_README = """\
# log-archive/ — archivo frío de bitácoras (COLD, never-delete)

Rotación de `STATE/log-recent.md` y changelogs de `STATE/brain-version.md`.

## Cuándo va algo aquí

- `log-recent.md` — el cron nocturno rota el contenido cuando supera el tope
  de chars (default ~4k). El archivo de destino sigue la convención `log-YYYY-MM.md`.
- `brain-version.md` — el changelog con entradas >30 días se mueve aquí para
  mantener el archivo HOT dentro del tope de 2.5k chars.
- Legados de boot y otros archivos de identidad deprecados pueden vivir aquí
  con prefijo `legado/` (ej. `legado/boot.md`) — never-delete, solo archivado.

## Convención de nombres

```
log-archive/
  log-YYYY-MM.md          ← rotaciones mensuales de log-recent
  changelog-hasta-YYYY-MM.md  ← overflow del changelog de brain-version
  legado/                 ← archivos de identidad/boot deprecados
```

## Regla madre: nunca borrar

Olvidar = degradar de capa, no destruir. Todo lo que baja aquí es COLD: solo
se accede bajo consulta explícita (grep o FTS5 en E3). Git guarda el historial.
"""

_MEMORIA_ARCHIVO_README = """\
# memoria-archivo — decay de memoria (never-delete)

Cuando un core block de `STATE/MEMORY.md` excede su límite suave (N13), el
excedente se ARCHIVA aquí como `<bloque>-YYYY-MM.md` — lo hace un humano o
consolidación con gate, nunca un pipeline.

El detalle nunca se borra — solo **desciende de tier** (caliente → tibia →
fría). Si un tema retoma relevancia, su contenido puede subir de vuelta a
`MEMORY.md`.

*(vacío al nacer)*
"""


# ── anti-traversal ──────────────────────────────────────────────────────────
def _safe_join(base, *parts):
    """Construye un path y valida que quede DENTRO de `base`. Devuelve None
    si alguna parte contiene '..' o escapa de la raíz."""
    joined = os.path.normpath(os.path.join(base, *parts))
    if not joined.startswith(os.path.normpath(base) + os.sep) and \
            joined != os.path.normpath(base):
        return None
    return joined


def _assert_not_forbidden(rel):
    """Lanza ValueError si `rel` toca BOOT/ o MEMORY.md."""
    parts = rel.replace("\\", "/").split("/")
    if parts[0] in FORBIDDEN_DIRS:
        raise ValueError("BOOT/ está prohibido: %s" % rel)
    if os.path.basename(rel).lower() in FORBIDDEN_FILES:
        raise ValueError("MEMORY.md está prohibido: %s" % rel)


# ── escritura atómica ────────────────────────────────────────────────────────
def _atomic_write(path, text):
    """Escribe `text` en `path` de forma atómica (tmp + os.replace)."""
    tmp = "%s.tmp%d" % (path, os.getpid())
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# ── scanner de destilados planos ─────────────────────────────────────────────
def _scan_flat_destilados(brain):
    """Escanea `STATE/sessions/<socio>/destilados/*.md` y devuelve una lista
    de dicts con info del archivo: {socio, fname, src_path, dst_month, dst_name,
    dst_dir, dst_path} — solo los que tienen el patrón plano antiguo."""
    hits = []
    sessions_dir = _safe_join(brain, "STATE", "sessions")
    if not sessions_dir or not os.path.isdir(sessions_dir):
        return hits
    try:
        socios = sorted(os.listdir(sessions_dir))
    except OSError:
        return hits
    for socio in socios:
        if socio.startswith((".", "_")) or socio in ("README.md",):
            continue
        dest_dir = _safe_join(sessions_dir, socio, "destilados")
        if not dest_dir or not os.path.isdir(dest_dir):
            continue
        try:
            fnames = sorted(os.listdir(dest_dir))
        except OSError:
            continue
        for fname in fnames:
            if not fname.endswith(".md") or fname.startswith((".","_")):
                continue
            m = _DESTILADO_FLAT_RE.match(fname)
            if not m:
                continue
            fecha = m.group(1)           # YYYY-MM-DD
            month = fecha[:7]            # YYYY-MM
            # nombre destino: sin el sid8 (el sid8 es los últimos 8 hex)
            # fname = YYYY-MM-DD-<slug>-<sid8>.md → dst = YYYY-MM-DD-<slug>.md
            base_no_ext = fname[:-3]     # quitar .md
            # quitar los últimos -<8hex>
            m2 = re.match(r'^(.+)-[0-9a-f]{8}$', base_no_ext, re.IGNORECASE)
            dst_name = (m2.group(1) if m2 else base_no_ext) + ".md"

            src = _safe_join(dest_dir, fname)
            dst_dir_path = _safe_join(sessions_dir, socio, month)
            dst = _safe_join(sessions_dir, socio, month, dst_name) if dst_dir_path else None
            if not src or not dst:
                continue
            hits.append({
                "socio": socio,
                "fname": fname,
                "src_path": src,
                "dst_month": month,
                "dst_name": dst_name,
                "dst_dir": dst_dir_path,
                "dst_path": dst,
            })
    return hits


# ── sembrado de INDEX.md ─────────────────────────────────────────────────────
def _scan_projects(brain):
    """Escanea deliverables/, STATE/PENDIENTES.md y wiki/index.md para
    generar líneas del INDEX.md. Falla-suave: errores → lista vacía."""
    proyectos, decisiones, entidades = [], [], []

    # 1. Deliverables activos
    deliv_root = _safe_join(brain, "deliverables")
    if deliv_root and os.path.isdir(deliv_root):
        try:
            for slug in sorted(os.listdir(deliv_root)):
                if slug.startswith((".","_")) or slug == "README.md":
                    continue
                sdir = os.path.join(deliv_root, slug)
                if os.path.isdir(sdir):
                    proyectos.append("- %s → `deliverables/%s/`" % (slug, slug))
        except OSError:
            pass

    # 2. Wiki/index.md — extraer líneas de proyectos/entidades
    wiki_idx = _safe_join(brain, "wiki", "index.md")
    if wiki_idx and os.path.isfile(wiki_idx):
        try:
            txt = open(wiki_idx, encoding="utf-8", errors="replace").read()
            for ln in txt.splitlines():
                ln_s = ln.strip()
                if ln_s.startswith("- ") and ("wiki/" in ln_s or "→" in ln_s):
                    if "agent" in ln_s.lower() or "agente" in ln_s.lower():
                        entidades.append(ln_s)
                    else:
                        proyectos.append(ln_s)
        except OSError:
            pass

    # 3. Relleno por defecto si vacíos
    if not proyectos:
        proyectos = ["*(vacío al nacer — agregar al primer proyecto activo)*"]
    if not decisiones:
        decisiones = ["*(vacío al nacer — agregar en las primeras sesiones con el equipo)*"]
    if not entidades:
        entidades = ["*(vacío al nacer — agregar conforme el agente gana contexto de equipo)*"]

    return proyectos, decisiones, entidades


def _build_index(brain):
    """Genera el contenido de STATE/INDEX.md sembrado con proyectos detectados."""
    proyectos, decisiones, entidades = _scan_projects(brain)
    return _INDEX_TEMPLATE.format(
        proyectos="\n".join(proyectos),
        decisiones="\n".join(decisiones),
        entidades="\n".join(entidades),
    )


# ── migración principal ──────────────────────────────────────────────────────
def migrate(brain, apply=False, stage=None, log=print):
    """Migra un cerebro a la estructura E1/E2.

    `stage` puede ser None (todo), 1 (solo destilados+dirs) o 2 (todo).
    Devuelve {"moved": [...], "created": [...], "skipped": [...],
              "warnings": [...], "errors": [...]} — en dry-run: mismas
    decisiones, cero escrituras.
    """
    brain = os.path.abspath(os.path.expanduser(brain))
    report = {"moved": [], "created": [], "skipped": [], "warnings": [],
              "errors": []}

    if not os.path.isdir(brain):
        log("cerebro no existe: %s" % brain)
        report["errors"].append("cerebro no existe: %s" % brain)
        return report
    if not os.path.isdir(os.path.join(brain, "STATE")):
        log("no parece un cerebro válido (sin STATE/): %s" % brain)
        report["errors"].append("sin STATE/: %s" % brain)
        return report

    # ── E1 · Paso 1: Mover destilados planos → subdirectorios por mes ────────
    if stage in (None, 1, 2):
        flat = _scan_flat_destilados(brain)
        for item in flat:
            src = item["src_path"]
            dst = item["dst_path"]
            dst_dir = item["dst_dir"]
            fname = item["fname"]
            dst_name = item["dst_name"]
            month = item["dst_month"]
            socio = item["socio"]

            # ¿ya existe el destino? → idempotente: skip
            if os.path.exists(dst):
                log("  ~ ya existe, skip: sessions/%s/%s/%s" % (socio, month, dst_name))
                report["skipped"].append(fname)
                continue

            log("  > mover %s → sessions/%s/%s/%s" % (fname, socio, month, dst_name))
            if apply:
                try:
                    _assert_not_forbidden("STATE/sessions/%s/%s/%s" % (socio, month, dst_name))
                    os.makedirs(dst_dir, exist_ok=True)
                    # copia atómica + borrado del original (no os.rename: puede cruzar FS)
                    with open(src, encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                    _atomic_write(dst, content)
                    os.remove(src)
                    report["moved"].append((fname, "STATE/sessions/%s/%s/%s" % (socio, month, dst_name)))
                except Exception as e:
                    report["errors"].append("%s: %s" % (fname, e))
                    log("  ! error moviendo %s: %s (sigo)" % (fname, e))
            else:
                report["moved"].append((fname, "STATE/sessions/%s/%s/%s" % (socio, month, dst_name)))

    # ── E1 · Paso 2: Crear STATE/log-archive/ si no existe ──────────────────
    if stage in (None, 1, 2):
        log_archive = _safe_join(brain, "STATE", "log-archive")
        if log_archive:
            readme_path = os.path.join(log_archive, "README.md")
            if os.path.isdir(log_archive):
                log("  ~ log-archive/ ya existe")
                report["skipped"].append("STATE/log-archive/")
            else:
                log("  + crear STATE/log-archive/ + README.md")
                if apply:
                    try:
                        os.makedirs(log_archive, exist_ok=True)
                        _atomic_write(readme_path, _LOG_ARCHIVE_README)
                        report["created"].append("STATE/log-archive/README.md")
                    except Exception as e:
                        report["errors"].append("log-archive: %s" % e)
                        log("  ! error creando log-archive/: %s" % e)
                else:
                    report["created"].append("STATE/log-archive/README.md")

    # ── E1 · Paso 3: Crear STATE/memoria-archivo/ si no existe ──────────────
    if stage in (None, 1, 2):
        mem_archivo = _safe_join(brain, "STATE", "memoria-archivo")
        if mem_archivo:
            readme_path = os.path.join(mem_archivo, "README.md")
            if os.path.isdir(mem_archivo):
                log("  ~ memoria-archivo/ ya existe")
                report["skipped"].append("STATE/memoria-archivo/")
            else:
                log("  + crear STATE/memoria-archivo/ + README.md")
                if apply:
                    try:
                        os.makedirs(mem_archivo, exist_ok=True)
                        _atomic_write(readme_path, _MEMORIA_ARCHIVO_README)
                        report["created"].append("STATE/memoria-archivo/README.md")
                    except Exception as e:
                        report["errors"].append("memoria-archivo: %s" % e)
                        log("  ! error creando memoria-archivo/: %s" % e)
                else:
                    report["created"].append("STATE/memoria-archivo/README.md")

    # ── E2 · Paso 4: Crear STATE/INDEX.md si no existe ──────────────────────
    if stage in (None, 2):
        index_path = _safe_join(brain, "STATE", "INDEX.md")
        if index_path:
            if os.path.isfile(index_path):
                log("  ~ STATE/INDEX.md ya existe")
                report["skipped"].append("STATE/INDEX.md")
            else:
                log("  + crear STATE/INDEX.md (sembrado desde proyectos detectados)")
                if apply:
                    try:
                        _assert_not_forbidden("STATE/INDEX.md")
                        content = _build_index(brain)
                        _atomic_write(index_path, content)
                        report["created"].append("STATE/INDEX.md")
                    except Exception as e:
                        report["errors"].append("INDEX.md: %s" % e)
                        log("  ! error creando INDEX.md: %s" % e)
                else:
                    report["created"].append("STATE/INDEX.md")

    # ── Aviso sobre boot.md legado (NUNCA se borra — solo avisar) ────────────
    legacy_boot = _safe_join(brain, "BOOT", "boot.md")
    if legacy_boot and os.path.isfile(legacy_boot):
        msg = ("  ⚠ LEGADO: BOOT/boot.md existe (%d chars) — es un archivo "
               "de identidad obsoleto. Su eliminación es decisión HUMANA (N3): "
               "si ya no aporta al boot, moverlo a STATE/log-archive/legado/ "
               "o borrarlo con consenso. El migrador NO lo toca."
               % _read_len(legacy_boot))
        log(msg)
        report["warnings"].append("BOOT/boot.md legado presente (%d chars)" % _read_len(legacy_boot))

    return report


def _read_len(path):
    try:
        return len(open(path, encoding="utf-8", errors="replace").read())
    except OSError:
        return -1


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="migrate_memory_v1.py",
        description=(
            "Migra un cerebro a la estructura E1/E2 del template de WORKSPACE.\n"
            "DEFAULT = DRY-RUN: imprime el plan completo sin escribir nada.\n"
            "Aplicar requiere --apply deliberado.\n\n"
            "NUNCA toca BOOT/ ni STATE/MEMORY.md (gate humano N3).\n"
            "NUNCA ejecutar sobre cerebros vivos sin confirmación del socio."))
    ap.add_argument("--brain", default="",
                    help="ruta del cerebro a migrar (obligatorio en --apply)")
    ap.add_argument("--apply", action="store_true",
                    help="ESCRIBIR los cambios (sin esto: dry-run)")
    ap.add_argument("--stage", type=int, choices=[1, 2], default=None,
                    help=("etapa de migración: "
                          "1=destilados+dirs (E1), "
                          "2=todo incluyendo INDEX.md (E1+E2, default)"))
    a = ap.parse_args(argv)

    brain = os.path.abspath(os.path.expanduser(a.brain)) if a.brain \
        else os.getcwd()
    mode = "APPLY" if a.apply else "DRY-RUN (no escribe nada — usa --apply)"
    stage_str = ("etapa %d" % a.stage) if a.stage else "todas las etapas"
    print("cerebro: %s" % brain)
    print("modo:    %s" % mode)
    print("etapa:   %s\n" % stage_str)

    rep = migrate(brain, apply=a.apply, stage=a.stage)

    n_moved = len(rep["moved"])
    n_created = len(rep["created"])
    n_warn = len(rep["warnings"])
    n_err = len(rep["errors"])
    total = n_moved + n_created

    verb = "hecho" if a.apply else "haría"
    print("\n%s: %d cambio(s) · %d movido(s) · %d creado(s) · %d saltado(s) "
          "· %d advertencia(s) · %d error(es)" % (
              verb, total, n_moved, n_created,
              len(rep["skipped"]), n_warn, n_err))

    if rep["warnings"]:
        print("\nAdvertencias:")
        for w in rep["warnings"]:
            print("  ⚠ %s" % w)

    if rep["errors"]:
        print("\nErrores:")
        for e in rep["errors"]:
            print("  ✗ %s" % e)

    if not a.apply and total:
        brain_arg = ' --brain "%s"' % a.brain if a.brain else ""
        stage_arg = " --stage %d" % a.stage if a.stage else ""
        print("\npara aplicar de verdad:  python3 migrate_memory_v1.py%s%s --apply"
              % (brain_arg, stage_arg))

    return 0 if not rep["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
