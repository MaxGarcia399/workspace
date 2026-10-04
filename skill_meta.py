#!/usr/bin/env python3
"""WORKSPACE · skill_meta — gating de skills por metadata `requires:` (N11).

Robo OpenClaw R7 + `check_fn` de Hermes (convergencia ×2): una skill que
depende de binarios/env/OS que NO existen en esta máquina debe AUTO-OCULTARSE
del catálogo en vez de fallar a media tarea. Clave para el entorno Windows del equipo:
el mismo cerebro corre en Mac y Windows, y el catálogo efectivo es POR MÁQUINA.

Convención de frontmatter (documentada en skills/README.md de cada cerebro):

    ---
    name: mi-skill
    requires:                  # bloque OPCIONAL — sin él, siempre disponible
      bins: [gh, git]          # ejecutables que deben existir en PATH (todos)
      env: [CLOUDFLARE_API_TOKEN]   # env vars presentes y no vacías (todas)
      os: [darwin, windows]    # plataformas donde la skill aplica (alguna)
      config: [~/.wrangler/config.toml]  # rutas que deben existir (todas;
                               # relativas se resuelven contra el cerebro)
    ---

Sub-listas en flow (`[a, b]`) o en bloque (`- a`). Alias de OS aceptados:
darwin/mac/macos/osx · windows/win/win32 · linux.

REGLAS DE SEGURIDAD (defaults seguros — la metadata jamás rompe nada):
- Sin `requires:` → la skill está SIEMPRE disponible (statu quo intacto).
- Frontmatter raro / requires imparseable / error del evaluador → DISPONIBLE
  (fail-open: un bug del gating jamás esconde una skill que sí funciona).
- Valores de `os:` desconocidos se IGNORAN (no son constraint imposible).
- Solo-lectura SIEMPRE: este módulo jamás edita un SKILL.md ni borra nada.
  "Oculta" = se omite del catálogo efectivo que se reporta; el archivo queda.

API:
    parse_requires(text)        # frontmatter YAML → dict normalizado o None
    read_requires(skill_dir)    # requires del SKILL.md/CLAUDE.md/INSTRUCCIONES.md
    evaluate(requires, ...)     # → (disponible: bool, faltantes: [str])
    check_skill(skill_dir)      # → {dir, requires, available, missing}
    scan_catalog(brain)         # catálogo efectivo de <brain>/skills/
    current_os()                # "darwin" | "windows" | "linux"

Los `missing` son etiquetas parseables: `bin:ffmpeg` · `env:FOO` ·
`os:darwin|windows` · `config:ruta`.

CLI:  python3 skill_meta.py <cerebro|carpeta-skills> [--hidden] [--json]

Consumidores: doctor fase 10 (check informativo, jamás ✗) hoy; el catálogo
filtrado que ve el agente al arrancar, mañana. Cero dependencias (stdlib,
3.9+), Mac/Windows/Linux, amputable (C10).
"""
import json
import os
import re
import shutil
import sys

SKILL_FILES = ("SKILL.md", "CLAUDE.md", "INSTRUCCIONES.md")
KNOWN_KEYS = ("bins", "env", "os", "config")
FM_READ_BYTES = 16384            # el frontmatter vive al inicio del archivo

_OS_ALIASES = {
    "darwin": "darwin", "mac": "darwin", "macos": "darwin", "osx": "darwin",
    "windows": "windows", "win": "windows", "win32": "windows",
    "linux": "linux",
}

_KEY_RX = re.compile(r"^([A-Za-z_][\w\-]*):\s*(.*)$")


def current_os():
    """Plataforma actual normalizada al vocabulario de `requires.os`."""
    if sys.platform == "darwin":
        return "darwin"
    if os.name == "nt" or sys.platform.startswith(("win", "cygwin")):
        return "windows"
    return "linux"


# ══════════════════════════════════════════════════════════════════════════
#  Parser (frontmatter YAML mínimo, tolerante — sin dependencia de PyYAML)
# ══════════════════════════════════════════════════════════════════════════
def _frontmatter(text):
    """Bloque entre los `---` iniciales, o None."""
    if not text or not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end]


def _strip_comment(s):
    """Comentario YAML al final de línea (` # …`) fuera. Heurística simple."""
    i = s.find(" #")
    return s[:i] if i != -1 else s


def _clean(s):
    """Quita espacios y comillas envolventes de un escalar."""
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        s = s[1:-1]
    return s.strip()


def _parse_value(rest):
    """Valor inline de una sub-clave → lista de strings.
    `[a, b]` (flow) · `a` (escalar → lista de 1) · vacío → []."""
    rest = _strip_comment(rest).strip()
    if not rest:
        return []
    if rest.startswith("["):
        inner = rest[1:-1] if rest.endswith("]") else rest[1:]
        return [c for c in (_clean(x) for x in inner.split(",")) if c]
    return [c for c in [_clean(rest)] if c]


def parse_requires(text):
    """`requires:` del frontmatter → dict {clave: [valores]} o None.

    None = sin constraints (no hay frontmatter, no hay `requires:`, o el
    bloque es imparseable/vacío). Jamás levanta: cualquier rareza → None
    (fail-open, regla de la serie N: la metadata nunca rompe nada)."""
    try:
        fm = _frontmatter(text)
        if fm is None:
            return None
        lines = fm.splitlines()
        start = None
        for i, ln in enumerate(lines):
            # solo el `requires:` a nivel raíz (columna 0) abre el bloque
            if re.match(r"^requires:\s*(#.*)?$", ln):
                start = i
                break
            if re.match(r"^requires:\s*\S", ln):
                return None     # valor inline raro (`requires: 42`) → fuera
        if start is None:
            return None
        req, cur = {}, None
        for ln in lines[start + 1:]:
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            indent = len(ln) - len(ln.lstrip(" \t"))
            if indent == 0:
                break           # terminó el bloque anidado de requires
            s = _strip_comment(ln.strip()).strip()
            if not s:
                continue
            if s.startswith("- "):           # item de lista en bloque
                if cur is not None:
                    item = _clean(s[2:])
                    if item:
                        req.setdefault(cur, []).append(item)
                continue
            m = _KEY_RX.match(s)
            if m:
                cur = m.group(1).strip().lower()
                req.setdefault(cur, [])
                req[cur] += _parse_value(m.group(2))
                continue
            # línea que no entendemos → tolerancia: se ignora
        req = {k: v for k, v in req.items() if v}
        return req or None
    except Exception:
        return None


def read_requires(skill_dir):
    """`requires` del archivo de instrucciones de la skill (SKILL.md o, en
    kits, CLAUDE.md/INSTRUCCIONES.md). None si no hay archivo/bloque.
    Solo lectura; falla-suave."""
    for name in SKILL_FILES:
        p = os.path.join(str(skill_dir), name)
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read(FM_READ_BYTES)
        except OSError:
            continue
        return parse_requires(text)
    return None


# ══════════════════════════════════════════════════════════════════════════
#  Evaluador
# ══════════════════════════════════════════════════════════════════════════
def _aslist(v):
    """Valor de requires → lista de strings. Escalares no-string (ints,
    bools…) se IGNORAN: metadata rara jamás se vuelve constraint."""
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if isinstance(x, str)]
    if isinstance(v, str):
        return [v]
    return []


def evaluate(requires, env=None, which=None, osname=None, base_dir=None):
    """¿La skill está disponible en ESTA máquina?  → (bool, faltantes).

    `faltantes` son etiquetas parseables (`bin:x`, `env:V`, `os:a|b`,
    `config:ruta`). Inyectables para tests: `env` (mapping), `which`
    (callable), `osname`, `base_dir` (ancla de rutas relativas en config).
    Fail-open: requires vacío/None o error interno → (True, [])."""
    if not requires or not isinstance(requires, dict):
        return True, []
    if env is None:
        env = os.environ
    if which is None:
        which = shutil.which
    if osname is None:
        osname = current_os()
    missing = []
    try:
        oses = []
        for x in _aslist(requires.get("os")):
            norm = _OS_ALIASES.get(x.strip().lower())
            if norm and norm not in oses:
                oses.append(norm)     # valores desconocidos se ignoran
        if oses and osname not in oses:
            missing.append("os:" + "|".join(oses))
        for b in _aslist(requires.get("bins")):
            b = b.strip()
            if b and which(b) is None:
                missing.append("bin:" + b)
        for v in _aslist(requires.get("env")):
            v = v.strip()
            if v and not env.get(v):
                missing.append("env:" + v)
        for c in _aslist(requires.get("config")):
            c = c.strip()
            if not c:
                continue
            p = os.path.expanduser(c)
            if not os.path.isabs(p) and base_dir:
                p = os.path.join(str(base_dir), p)
            if not os.path.exists(p):
                missing.append("config:" + c)
    except Exception:
        return True, []   # un bug del evaluador jamás esconde una skill
    return not missing, missing


# ══════════════════════════════════════════════════════════════════════════
#  Catálogo
# ══════════════════════════════════════════════════════════════════════════
def iter_skill_dirs(skills_root):
    """Carpetas de skill bajo `skills_root` (las que contienen un archivo de
    instrucciones). Salta dot-dirs y `_*` (`_propuestas` no es catálogo).
    No desciende dentro de una skill (sus assets no son sub-skills)."""
    skills_root = str(skills_root)
    for dirpath, dirnames, filenames in os.walk(skills_root):
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith((".", "_")))
        if dirpath != skills_root and any(f in filenames for f in SKILL_FILES):
            dirnames[:] = []
            yield dirpath


def check_skill(skill_dir, base_dir=None):
    """Estado de gating de UNA skill."""
    req = read_requires(skill_dir)
    ok, missing = evaluate(req, base_dir=base_dir or skill_dir)
    return {"dir": str(skill_dir), "requires": req,
            "available": ok, "missing": missing}


def scan_catalog(brain, skills_root=None):
    """Catálogo efectivo de un cerebro: [{name, dir, requires, available,
    missing}] ordenado por nombre. `name` = ruta relativa a skills/ con `/`.
    Sin carpeta skills/ → []. Solo lectura."""
    root = str(skills_root) if skills_root else os.path.join(str(brain), "skills")
    out = []
    if not os.path.isdir(root):
        return out
    for d in iter_skill_dirs(root):
        r = check_skill(d, base_dir=str(brain))
        r["name"] = os.path.relpath(d, root).replace(os.sep, "/")
        out.append(r)
    out.sort(key=lambda r: r["name"])
    return out


# ══════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════
def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if "-h" in args or "--help" in args:
        print(__doc__.split("API:")[0].strip())
        print("\nUso: python3 skill_meta.py <cerebro|carpeta-skills> "
              "[--hidden] [--json]")
        return 2
    only_hidden = "--hidden" in args
    as_json = "--json" in args
    paths = [a for a in args if not a.startswith("-")]
    path = paths[0] if paths else os.getcwd()
    if os.path.isdir(os.path.join(path, "skills")):
        results = scan_catalog(path)
    else:   # le pasaron la carpeta skills/ directa
        results = scan_catalog(os.path.dirname(path) or ".", skills_root=path)
    if only_hidden:
        results = [r for r in results if not r["available"]]
    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0
    hidden = 0
    for r in results:
        if r["available"]:
            tag = " (requires ✓)" if r["requires"] else ""
            print(f"  ✓ {r['name']}{tag}")
        else:
            hidden += 1
            print(f"  ✗ {r['name']} — oculta aquí: falta "
                  + ", ".join(r["missing"]))
    print(f"\n  {len(results)} skill(s) · {hidden} oculta(s) en esta máquina "
          f"({current_os()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
