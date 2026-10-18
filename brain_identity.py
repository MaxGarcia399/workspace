#!/usr/bin/env python3
"""WORKSPACE · brain_identity — ÚNICA fuente de «cuál es el archivo de identidad
de un cerebro» (formato de cerebro v2, release A).

La identidad del agente vive en un archivo NEUTRAL de motor: `BRAIN.md`. Los
archivos que cada motor lee por su cuenta son PUNTEROS generados hacia ella:
`CLAUDE.md` (Claude Code, con `@BRAIN.md`), `AGENTS.md` (codex/opencode/
openclaw/hermes), `GEMINI.md` (antigravity).

Compatibilidad (release A — nada se migra todavía):
  · cerebro NUEVO (template v2): `BRAIN.md` + `CLAUDE.md` puntero.
  · cerebro VIEJO: solo `CLAUDE.md` con la identidad → se sigue usando tal cual.
  · `identity_doc` explícito en el agent.json siempre gana.

Resolución: identity_doc del agente → `BRAIN.md` si existe → `CLAUDE.md`.
Si lo resuelto es un `CLAUDE.md` PUNTERO (marca de abajo), quien necesite el
CONTENIDO lee el `BRAIN.md` (read_identity lo hace solo).

Núcleo INCRUSTADO (`embed_core`): para motores que solo leen su archivo de
proyecto y no expanden imports (Hermes), el puntero lleva una COPIA GENERADA
del núcleo de identidad. La fuente única sigue siendo cada archivo.

Stdlib puro, falla-suave (jamás levanta por el contenido del cerebro).
"""
import os
import re

IDENTITY_DOC = "BRAIN.md"
LEGACY_IDENTITY_DOC = "CLAUDE.md"

#: Marca del CLAUDE.md puntero generado (identidad neutral). Distinta de las
#: marcas de AGENTS.md/GEMINI.md: esas NO cambian (versiones viejas deben
#: seguir reconociendo sus punteros).
POINTER_MARK = "<!-- WORKSPACE:GENERATED identity-pointer v1 -->"
POINTER_END = "<!-- WORKSPACE:GENERATED identity-pointer end -->"

#: Tope de lectura defensivo para quien necesita el contenido (un archivo de
#: identidad sano mide pocos KB).
_MAX_READ = 512 * 1024


def safe_doc_name(name):
    """Nombre de archivo de identidad aceptable (relativo a la raíz del
    cerebro, sin rutas ni escapes). '' si no lo es."""
    d = str(name or "").strip()
    # Misma regla que tenía engines/codex._identity_doc (compatibilidad exacta).
    if not d or os.path.isabs(d) or "/" in d or "\\" in d or d.startswith(".."):
        return ""
    return d


def identity_doc(brain, cfg=None):
    """Nombre (relativo al cerebro) del archivo de identidad del agente."""
    explicit = safe_doc_name((cfg or {}).get("identity_doc"))
    if explicit:
        return explicit
    if brain and os.path.isfile(os.path.join(str(brain), IDENTITY_DOC)):
        return IDENTITY_DOC
    return LEGACY_IDENTITY_DOC


def identity_path(brain, cfg=None):
    return os.path.join(str(brain or ""), identity_doc(brain, cfg))


def has_identity(brain, cfg=None):
    """¿El cerebro tiene su archivo de identidad (cualquiera de los formatos)?"""
    return bool(brain) and os.path.isfile(identity_path(brain, cfg))


def looks_like_brain_root(path):
    """¿`path` tiene un archivo de identidad de cerebro (v2 o anterior)?"""
    return bool(path) and (os.path.isfile(os.path.join(path, IDENTITY_DOC))
                           or os.path.isfile(os.path.join(path, LEGACY_IDENTITY_DOC)))


def is_identity_pointer(text):
    """¿El texto es un CLAUDE.md puntero generado por Workspace?"""
    return str(text or "").lstrip().startswith(POINTER_MARK)


def _read(path, limit=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit or _MAX_READ)
    except OSError:
        return None


def read_identity(brain, cfg=None, limit=None):
    """CONTENIDO de la identidad del agente, o '' si no hay. Si lo resuelto es
    un CLAUDE.md puntero, sigue al BRAIN.md (quien lee el contenido como texto
    —panel Proyectos, evals— necesita la identidad, no el puntero)."""
    if not brain:
        return ""
    txt = _read(identity_path(brain, cfg), limit)
    if txt is None:
        return ""
    if is_identity_pointer(txt):
        real = _read(os.path.join(str(brain), IDENTITY_DOC), limit)
        return real or ""
    return txt


#: Nombres que algún motor crea o lee POR SU CUENTA desde la raíz de su
#: workspace y que NO deben estar sueltos en la raíz del cerebro: competirían
#: con la identidad y la memoria comunes (regla de estructura: todos los motores
#: sobre las mismas carpetas; lo propio de un motor va en `motores/<motor>/`).
#: VERIFICADOS (2026-10-15) contra la doc oficial — docs.openclaw.ai
#: (concepts/agent-workspace, concepts/memory) y hermes-agent (context-files:
#: `.hermes.md`/`HERMES.md` y `AGENTS.override.md` le ganan a AGENTS.md) — y
#: contra OpenClaw 2026.5.12 (crea SOUL/IDENTITY/USER/BOOTSTRAP/HEARTBEAT/TOOLS).
#: `.hermes/`: Hermes v0.18.2 guarda ahí los planes de su skill de planes y
#: lee plugins de proyecto (código del binario, 2026-10-15).
RESERVED_ROOT = (
    ("SOUL.md", "openclaw"), ("IDENTITY.md", "openclaw"), ("USER.md", "openclaw"),
    ("BOOTSTRAP.md", "openclaw"), ("BOOT.md", "openclaw"),
    ("HEARTBEAT.md", "openclaw"), ("TOOLS.md", "openclaw"),
    ("DREAMS.md", "openclaw"), ("MEMORY.md", "openclaw"), ("memory", "openclaw"),
    ("HERMES.md", "hermes"), (".hermes.md", "hermes"),
    ("AGENTS.override.md", "hermes"), (".hermes", "hermes"),
)


def reserved_in_root(brain):
    """[(nombre, motor)] de nombres reservados presentes en la raíz del cerebro
    (carpetas con «/» al final). SOLO LECTURA: nunca mueve ni borra."""
    try:
        names = set(os.listdir(str(brain)))
    except OSError:
        return []
    out = []
    for name, motor in RESERVED_ROOT:
        if name in names:
            is_dir = os.path.isdir(os.path.join(str(brain), name))
            out.append((name + ("/" if is_dir else ""), motor))
    return out


# ── núcleo de identidad INCRUSTADO (motores sin imports) ──────────────────
#: Claude Code incrusta la identidad con `@BRAIN.md`. Un motor que solo lee su
#: archivo de proyecto la recibe únicamente si el MODELO obedece «lee
#: BRAIN.md», y un modelo débil no lo hace (Hermes + modelo gratis,
#: 2026-10-15: 0 lecturas, «sin personalidad propia», no sabía quién era su
#: socio). Para esos motores el puntero lleva una copia GENERADA del núcleo:
#: el doc de identidad + BOOT/NN-*.md + STATE/users/<socio>.md (la capa HOT de
#: identidad del formato v2, protocols/agent-creation/02-BRAIN-FORMAT.md; la
#: misma convención BOOT/NN que brain_vitals.boot_files). Lo VIVO de STATE
#: (memoria, pendientes) no entra: cambia a diario y el agente lo lee cuando
#: toca. Tope en caracteres: lo que no cabe se avisa dentro del texto.
EMBED_BUDGET = 36_000
#: Un documento que no cabe entero se recorta solo si queda al menos esto.
_EMBED_MIN_PART = 2_000
_BOOT_NUM = re.compile(r"^\d\d-.+\.md$")


def socio_of(brain):
    """Socio activo: `.claude/socio.local` del cerebro → el de la máquina
    (`socio.local` del directorio de estado). '' si no hay. Solo [a-z0-9_-]."""
    try:
        import paths
        machine = os.path.join(paths.state_dir(), "socio.local")
    except Exception:
        machine = ""
    for p in (os.path.join(str(brain or ""), ".claude", "socio.local"), machine):
        if not p:
            continue
        txt = _read(p, 256)
        s = re.sub(r"[^a-z0-9_-]", "", (txt or "").strip().lower())
        if s:
            try:      # un nombre viejo (alias de la cédula) → el actual
                import usuarios
                return usuarios.resolver(brain, s) or s
            except Exception:
                return s
    return ""


def user_profile_rel(brain, socio=None):
    """`STATE/users/<archivo>.md` del socio, o ''. Exacto primero; si no, el
    ÚNICO perfil cuyo nombre es prefijo del socio o al revés (socio.local
    «maxgarcia» ↔ users/max.md). Ambiguo o ninguno → ''."""
    socio = socio if socio is not None else socio_of(brain)
    udir = os.path.join(str(brain or ""), "STATE", "users")
    try:
        names = [n for n in os.listdir(udir) if n.lower().endswith(".md")
                 and n.lower() != "readme.md" and not n.startswith((".", "_"))
                 and os.path.isfile(os.path.join(udir, n))]
    except OSError:
        return ""
    if not socio:
        return ""
    stems = {n[:-3].lower(): n for n in names}
    if socio in stems:
        return "STATE/users/" + stems[socio]
    hits = [n for s, n in stems.items() if len(s) >= 3
            and (socio.startswith(s) or s.startswith(socio))]
    return "STATE/users/" + hits[0] if len(hits) == 1 else ""


def core_docs(brain, cfg=None, socio=None):
    """[(rel, ruta)] del núcleo de identidad, en orden de arranque: el doc de
    identidad (BRAIN.md; un CLAUDE.md puntero se sigue a BRAIN.md) →
    BOOT/NN-*.md → STATE/users/<socio>.md. Solo lo que existe."""
    if not brain or not os.path.isdir(str(brain)):
        return []
    brain = str(brain)
    out = []
    doc = identity_doc(brain, cfg)
    txt = _read(os.path.join(brain, doc), 4096)
    if txt is not None and is_identity_pointer(txt):
        doc = IDENTITY_DOC
    if os.path.isfile(os.path.join(brain, doc)):
        out.append((doc, os.path.join(brain, doc)))
    bdir = os.path.join(brain, "BOOT")
    try:
        nums = sorted(x for x in os.listdir(bdir) if _BOOT_NUM.match(x))
    except OSError:
        nums = []
    out += [("BOOT/" + x, os.path.join(bdir, x)) for x in nums
            if os.path.isfile(os.path.join(bdir, x))]
    urel = user_profile_rel(brain, socio)
    if urel:
        out.append((urel, os.path.join(brain, *urel.split("/"))))
    return out


def _strip_frontmatter(text):
    """Quita un bloque YAML inicial (`---` … `---`): metadatos, no identidad."""
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if 0 < end < 4096:
            return text[end + 5:]
    return text


def embed_core(brain, cfg=None, socio=None, budget=EMBED_BUDGET, reject=None):
    """Bloque markdown con la copia del núcleo, para incrustar en un puntero.

    `reject(texto) -> [hallazgos]` (opcional, del motor): un documento con
    hallazgos NO se incrusta (p. ej. el escáner de inyección de Hermes
    bloquearía el archivo ENTERO). Devuelve {"text", "included", "truncated",
    "omitted", "rejected": [(rel, hallazgos)]}; text = '' si no hay nada que
    incrustar. Falla-suave: jamás levanta."""
    res = {"text": "", "included": [], "truncated": "", "omitted": [],
           "rejected": []}
    try:
        docs = core_docs(brain, cfg, socio)
    except Exception:
        docs = []
    parts, left = [], int(budget)
    for i, (rel, path) in enumerate(docs):
        body = _read(path)
        if body is None:
            continue
        body = _strip_frontmatter(body.replace("\r\n", "\n")).strip()
        if not body:
            continue
        if reject is not None:
            try:
                found = list(reject(body) or [])
            except Exception:
                found = []
            if found:
                res["rejected"].append((rel, found))
                continue
        if len(body) > left:
            if left >= _EMBED_MIN_PART:
                cut = body[:left].rsplit("\n", 1)[0]
                parts.append(_embed_part(rel, cut + "\n\n[… recortado por tamaño: "
                                         "el resto está en `%s`; léelo]" % rel))
                res["truncated"] = rel
            else:
                res["omitted"].append(rel)
            res["omitted"] += [r for r, _p in docs[i + 1:]]
            break
        parts.append(_embed_part(rel, body))
        res["included"].append(rel)
        left -= len(body)
    if not parts:
        return res
    lines = ["## Núcleo de identidad (copia generada en cada arranque)", "",
             "Este motor no incrusta archivos por su cuenta: Workspace copia aquí el "
             "núcleo de identidad de este cerebro y YA ESTÁ CARGADO, así que no hace "
             "falta leer estos archivos para arrancar. La fuente única sigue siendo "
             "cada archivo del cerebro (esta copia no se edita: se regenera).", ""]
    lines += parts
    if res["omitted"]:
        lines += ["No incrustados por tamaño (léelos al arrancar, en este orden): "
                  + ", ".join("`%s`" % r for r in res["omitted"]) + ".", ""]
    if res["rejected"]:
        lines += ["No incrustados (léelos al arrancar): "
                  + ", ".join("`%s`" % r for r, _f in res["rejected"]) + ".", ""]
    res["text"] = "\n".join(lines).rstrip() + "\n"
    return res


def _embed_part(rel, body):
    return "===== INICIO %s =====\n%s\n===== FIN %s =====\n" % (rel, body, rel)


def pointer_text(display="", tagline=""):
    """CLAUDE.md puntero del formato v2. El import `@BRAIN.md` va FUERA de
    backticks y bloques de código (Claude Code no expande imports ahí) y en su
    propia línea; la instrucción en texto cubre a motores sin imports. La
    línea de nombre/tagline mantiene algo de identidad para lectores viejos
    del contenido. Debajo de la marca de fin, zona libre del dueño."""
    who = str(display or "").strip()
    tag = str(tagline or "").strip()
    head = "**%s**%s" % (who, (" — " + tag) if tag else "") if who else ""
    lines = [POINTER_MARK,
             "<!-- Archivo GENERADO por Workspace: puntero a la identidad del agente.",
             "     La identidad vive en BRAIN.md (neutral de motor). Lo de abajo de la",
             "     marca de fin es zona libre del dueño. -->",
             ""]
    if head:
        lines += [head, ""]
    lines += ["La identidad de este agente vive en BRAIN.md: léelo completo y síguelo.",
              "",
              "@BRAIN.md",
              "",
              POINTER_END,
              ""]
    return "\n".join(lines)
