#!/usr/bin/env python3
"""WORKSPACE · brain_vitals — signos vitales de un cerebro (SOLO LECTURA).

POR QUÉ: el costo real de un cerebro tiene DOS monedas distintas que no hay
que confundir:
  · TOKENS — lo que se CARGA en contexto. Solo lo gasta la superficie HOT
    (boot + archivos que se retrievean cada sesión). Un `library/INDEX.md`
    de 120k chars quema ~30k tokens en cada consulta aunque el resto del
    cerebro pese gigas.
  · DISCO/SYNC — junk regenerable (node_modules, dist, caches) que NUNCA se
    carga en contexto: no gasta tokens, pero infla backup/Obsidian Sync.

El chequeo previo (doctor fase 8) solo medía `_boot_files` — por eso NO veía
el mayor costo real de Atlas (`library/INDEX.md`, session-time). Este módulo
cierra ese hoyo con un MANIFIESTO HOT por cerebro y añade el escaneo de junk.

MANIFIESTO HOT (`STATE/hot-manifest.md`, por cerebro):
    - boot <ruta>            → se lee en CADA arranque
    - session <ruta> — nota  → se carga durante la sesión (índices retrieveados)
  El boot estándar (CLAUDE.md + BOOT/NN-*.md + STATE vivo) se auto-detecta;
  el manifiesto declara solo lo EXTRA de ese cerebro. Formato markdown a
  propósito: los cerebros sincronizan por Obsidian Sync (que por default
  puede no llevar .json) y así el socio lo lee/edita como cualquier nota.

REGLAS DURAS:
  · SOLO LECTURA — este módulo JAMÁS escribe, mueve ni borra nada.
    (La limpieza vive aparte, en brain_cleanup.py, opt-in y con cuarentena.)
  · Falla-suave: un archivo/dir podrido se salta y se sigue; nunca lanza
    al caller del doctor.
  · Anti-traversal: rutas del manifiesto relativas al cerebro, sin `..`,
    sin absolutas — una línea inválida se ignora (con nota).
  · Excluir de Obsidian Sync NO se puede hacer por código: el hint siempre
    instruye al socio (Ajustes → Sync → tipos/carpetas excluidas).

USO:
    python3 brain_vitals.py                       # todos los cerebros (dispatch)
    python3 brain_vitals.py --brain "/ruta/al/CEREBRO"

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

MANIFEST_REL = os.path.join("STATE", "hot-manifest.md")
CHARS_PER_TOKEN = 4            # estimación gruesa (la misma del doctor)

# Presupuesto de la superficie HOT COMPLETA (boot + session). El boot solo
# ya tiene su techo en doctor (96k chars); este techo cubre el costo real
# por sesión. Referencia: Atlas medido en ~78k tok/sesión (≈312k chars) es
# el failure mode; un cerebro sano ronda ≤40k tok.
HOT_BUDGET_TOTAL = 160_000     # chars (~40k tokens)

# ── junk (disco/sync — NO tokens) ─────────────────────────────────────────
# Dirs REGENERABLES por nombre exacto (la misma allowlist que usa
# brain_cleanup — aquí solo se REPORTAN, jamás se tocan).
JUNK_DIR_NAMES = ("node_modules", ".next", "dist", "build", ".turbo", ".cache")
JUNK_FILE_SUFFIXES = (".tsbuildinfo", ".bak")
BIG_FILE_BYTES = 25 * 1024 * 1024   # binario "grande" (≥25 MB)
# Subárboles que el escaneo NUNCA recorre (identidad/config — ni para medir):
PRUNE_DIRS = (".git", ".obsidian", "BOOT")
MAX_FINDINGS = 40              # tope de hallazgos por cerebro (fail-soft)

SYNC_HINT = ("agrégalo a .gitignore Y exclúyelo en Obsidian Ajustes→Sync — "
             "el harness NO puede excluirlo de Sync por código")

_MANIFEST_LINE = re.compile(r"^-\s+(boot|session)\s+(.+?)\s*$")


# ══════════════════════════════════════════════════════════════════════════
#  Superficie HOT
# ══════════════════════════════════════════════════════════════════════════
def read_len(p):
    """Chars del archivo (lo que el contexto paga). -1 = ilegible."""
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return len(fh.read())
    except Exception:
        return -1


def boot_files(brain, socio=None):
    """[(rel, path)] de lo que CLAUDE.md manda leer al arranque: CLAUDE.md +
    BOOT/ numerados (NN-*.md) + STATE vivo (brain-version, MEMORY, PENDIENTES,
    MILESTONES, log-recent, users/<socio>). Solo lo que EXISTE en ese cerebro —
    cada agente tiene su propio set (Atlas no tiene PENDIENTES, p. ej.).
    Fuente única: doctor (fase 8) delega aquí."""
    files = [("CLAUDE.md", os.path.join(brain, "CLAUDE.md"))]
    bdir = os.path.join(brain, "BOOT")
    try:
        nums = sorted(x for x in os.listdir(bdir) if re.match(r"^\d\d-.+\.md$", x))
    except Exception:
        nums = []
    files += [(f"BOOT/{x}", os.path.join(bdir, x)) for x in nums]
    state = ["brain-version.md", "MEMORY.md", "PENDIENTES.md", "MILESTONES.md",
             "log-recent.md"] + ([f"users/{socio}.md"] if socio else [])
    files += [(f"STATE/{s}", os.path.join(brain, "STATE", *s.split("/"))) for s in state]
    return [(rel, p) for rel, p in files if os.path.isfile(p)]


def _safe_rel(brain, rel):
    """Ruta del manifiesto validada (anti-traversal). None = inválida.
    Rechaza absolutas, drives de Windows y cualquier `..`; verifica además
    que el realpath del destino caiga BAJO el realpath del cerebro."""
    rel = (rel or "").strip().strip('`"')
    if not rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        return None
    parts = rel.replace("\\", "/").split("/")
    if any(p in ("..", "") for p in parts):
        return None
    full = os.path.join(brain, *parts)
    try:
        real_brain = os.path.realpath(brain)
        real_full = os.path.realpath(full)
        if not (real_full == real_brain
                or real_full.startswith(real_brain + os.sep)):
            return None
    except OSError:
        return None
    return "/".join(parts)


def parse_manifest(brain):
    """Lee STATE/hot-manifest.md → [{"when": "boot"|"session", "rel", "note"}].
    Falla-suave: sin manifiesto → []; línea inválida/traversal → se ignora."""
    path = os.path.join(brain, MANIFEST_REL)
    if not os.path.isfile(path):
        return None                      # None = no hay manifiesto (≠ vacío)
    entries = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except Exception:
        return None
    for ln in text.splitlines():
        m = _MANIFEST_LINE.match(ln.strip())
        if not m:
            continue
        when, rest = m.group(1), m.group(2)
        # nota opcional tras " — " (em-dash) o " -- "
        note = ""
        for sep in (" — ", " -- "):
            if sep in rest:
                rest, note = rest.split(sep, 1)
                break
        rel = _safe_rel(brain, rest)
        if rel is None:
            continue
        entries.append({"when": when, "rel": rel, "note": note.strip()})
    return entries


def measure_hot(brain, socio=None):
    """Mide la superficie HOT real del cerebro (SOLO lee).

    Devuelve dict:
      boot     [(rel, chars)]  auto-boot + manifiesto `boot` (dedup)
      session  [(rel, chars)]  manifiesto `session` (lo que no esté ya en boot)
      manifest bool            ¿existe STATE/hot-manifest.md?
      missing  [rel]           declarados en manifiesto pero inexistentes
      boot_chars / session_chars / total_chars / total_tokens
    """
    brain = os.path.abspath(os.path.expanduser(brain))
    boot = []
    seen = set()
    for rel, p in boot_files(brain, socio):
        n = read_len(p)
        if n >= 0:
            boot.append((rel, n))
            seen.add(rel.replace("\\", "/"))
    entries = parse_manifest(brain)
    session, missing = [], []
    for e in (entries or []):
        rel = e["rel"]
        if rel in seen:
            continue
        p = os.path.join(brain, *rel.split("/"))
        if not os.path.isfile(p):
            missing.append(rel)
            continue
        n = read_len(p)
        if n < 0:
            missing.append(rel)
            continue
        seen.add(rel)
        if e["when"] == "boot":
            boot.append((rel, n))
        else:
            session.append((rel, n))
    boot_chars = sum(n for _, n in boot)
    session_chars = sum(n for _, n in session)
    total = boot_chars + session_chars
    return {"boot": boot, "session": session,
            "manifest": entries is not None, "missing": missing,
            "boot_chars": boot_chars, "session_chars": session_chars,
            "total_chars": total,
            "total_tokens": total // CHARS_PER_TOKEN}


def tokens_k(chars):
    """'12.3k tok' legible a partir de chars."""
    return "%.1fk tok" % (chars / CHARS_PER_TOKEN / 1000.0)


# ══════════════════════════════════════════════════════════════════════════
#  Junk (disco/sync) — WARN-only, jamás toca nada
# ══════════════════════════════════════════════════════════════════════════
def _du(path):
    """Bytes del subárbol (sin seguir symlinks). Falla-suave → lo sumado."""
    total = 0
    try:
        if os.path.isfile(path):
            return os.lstat(path).st_size
        for dirpath, dirs, files in os.walk(path, followlinks=False):
            for name in files:
                try:
                    total += os.lstat(os.path.join(dirpath, name)).st_size
                except OSError:
                    continue
    except Exception:
        pass
    return total


def human(nbytes):
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return ("%d %s" % (nbytes, unit)) if unit == "B" \
                else ("%.1f %s" % (nbytes, unit))
        nbytes /= 1024.0
    return "?"


def scan_junk(brain):
    """Hallazgos de junk bajo el cerebro (SOLO reporta — jamás toca).

    [{"rel", "kind", "bytes"}], kinds:
      regenerable-dir  node_modules/.next/dist/build/.turbo/.cache
      junk-file        *.tsbuildinfo · *.bak
      state-tmp        STATE/tmp/ (scratch que crece — contenido NO regenerable:
                       solo se avisa, la limpieza jamás lo toca)
      big-file         archivo ≥25 MB (fuera de dirs ya marcados)
    No desciende en .git/.obsidian/BOOT ni dentro de un dir ya marcado.
    Fail-soft con tope MAX_FINDINGS."""
    brain = os.path.abspath(os.path.expanduser(brain))
    findings = []

    def add(rel, kind, nbytes):
        findings.append({"rel": rel.replace(os.sep, "/"), "kind": kind,
                         "bytes": nbytes})
        return len(findings) >= MAX_FINDINGS

    try:
        for dirpath, dirs, files in os.walk(brain, followlinks=False):
            rel_dir = os.path.relpath(dirpath, brain)
            if rel_dir == ".":
                rel_dir = ""
            # poda: identidad/config + no re-entrar a junk ya marcado
            pruned = []
            for d in list(dirs):
                if d in PRUNE_DIRS:
                    pruned.append(d)
                elif d in JUNK_DIR_NAMES:
                    full = os.path.join(dirpath, d)
                    if not os.path.islink(full):
                        if add(os.path.join(rel_dir, d), "regenerable-dir",
                               _du(full)):
                            return findings
                    pruned.append(d)
                elif d == "tmp" and rel_dir == "STATE":
                    full = os.path.join(dirpath, d)
                    if add(os.path.join(rel_dir, d), "state-tmp", _du(full)):
                        return findings
                    pruned.append(d)
            for d in pruned:
                dirs.remove(d)
            for name in files:
                full = os.path.join(dirpath, name)
                rel = os.path.join(rel_dir, name)
                try:
                    size = os.lstat(full).st_size
                except OSError:
                    continue
                if name.endswith(JUNK_FILE_SUFFIXES):
                    if add(rel, "junk-file", size):
                        return findings
                elif size >= BIG_FILE_BYTES:
                    if add(rel, "big-file", size):
                        return findings
    except Exception:
        pass                       # fail-soft: lo escaneado hasta aquí
    return findings


def detect_stubs(brains):
    """Stubs de path-pollution: un dir HERMANO cuyo nombre colapsa al del
    cerebro real (espacios fuera, casefold) pero es OTRA ruta — p. ej.
    `X-BRAIN` junto a `X - BRAIN` (sesiones que escribieron a un path mal
    resuelto). [{"brain", "stub"}] — solo detección."""
    out = []
    seen = set()
    for name, brain in brains:
        try:
            brain_abs = os.path.abspath(brain)
            parent = os.path.dirname(brain_abs)
            key = os.path.basename(brain_abs).replace(" ", "").casefold()
            for sib in os.listdir(parent):
                full = os.path.join(parent, sib)
                if full == brain_abs or not os.path.isdir(full):
                    continue
                if sib.replace(" ", "").casefold() == key and full not in seen:
                    seen.add(full)
                    out.append({"brain": brain_abs, "stub": full})
        except OSError:
            continue
    return out


# ══════════════════════════════════════════════════════════════════════════
#  CLI (solo lectura, exit 0 siempre)
# ══════════════════════════════════════════════════════════════════════════
def _discover_brains():
    """[(name, path)] vía dispatch (lo mismo que el doctor). Falla-suave."""
    try:
        import dispatch
        reg = dispatch.load_registry()
        out = []
        for a in reg.get("agents", []):
            try:
                cfg = dispatch.load_agent_cfg(a)
            except Exception:
                cfg = {}
            b = dispatch.resolve_brain(a["name"], cfg)
            if b and os.path.isdir(b):
                out.append((a["name"], b))
        return out
    except Exception:
        return []


def report(brains, out=print):
    for name, brain in brains:
        m = measure_hot(brain)
        out("")
        out("%s — %s" % (name, brain))
        out("  HOT: ~%s total (boot %s · sesión %s)%s"
            % (tokens_k(m["total_chars"]), tokens_k(m["boot_chars"]),
               tokens_k(m["session_chars"]),
               "" if m["manifest"] else "  [sin STATE/hot-manifest.md — "
                                        "solo se mide el boot]"))
        for rel, n in sorted(m["boot"] + m["session"],
                             key=lambda x: -x[1])[:8]:
            out("    %8s  %s" % (tokens_k(n), rel))
        if m["total_chars"] > HOT_BUDGET_TOTAL:
            out("  ⚠ sobre presupuesto HOT (>%dk chars ≈ %s)"
                % (HOT_BUDGET_TOTAL // 1000, tokens_k(HOT_BUDGET_TOTAL)))
        for rel in m["missing"]:
            out("  ⚠ manifiesto declara %s pero no existe" % rel)
        junk = scan_junk(brain)
        for j in junk:
            out("  ⚠ junk [%s] %s — %s → %s"
                % (j["kind"], j["rel"], human(j["bytes"]), SYNC_HINT))
        if not junk:
            out("  junk: limpio")
    for s in detect_stubs(brains):
        out("")
        out("⚠ stub de path-pollution: %s (duplica %s) — revisar qué lo "
            "escribió y fusionar/retirar A MANO" % (s["stub"], s["brain"]))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="brain_vitals.py",
        description="Signos vitales de cerebros: tokens HOT reales "
                    "(manifiesto boot/session) + junk de disco. "
                    "SOLO LECTURA — jamás modifica nada.")
    ap.add_argument("--brain", action="append", default=None,
                    help="ruta de un cerebro (repetible; default: todos "
                         "los del registry vía dispatch)")
    args = ap.parse_args(argv)
    if args.brain:
        brains = [(os.path.basename(os.path.abspath(b)), b)
                  for b in args.brain]
    else:
        brains = _discover_brains()
        if not brains:
            print("sin cerebros resueltos (usa --brain /ruta/al/CEREBRO)")
            return 0
    report(brains)
    return 0


if __name__ == "__main__":
    sys.exit(main())
