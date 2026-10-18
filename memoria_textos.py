"""WORKSPACE · memoria_textos — los textos de memoria de un cerebro viejo pasan a la memoria v1.

Una sola función, `actualizar(brain)`, llamada desde TRES puertas (igual que
brain_format):
  · la migración automática 202610170100_memoria_v1 (`workspace update`);
  · cargar un agente: un cerebro que llega DESPUÉS de la actualización
    (instalación nueva, otra máquina, sync) no pasa por la migración, porque
    los sellos son por máquina y una instalación nueva las da por hechas;
  · `workspace doctor --fix`.

Qué cambia, SOLO si el texto sigue igual a como lo dejó alguna versión de la
plantilla de Workspace (sha256, con el nombre del agente normalizado):
  · `STATE/sessions/README.md` → la explicación nueva;
  · la sección «2.5 Memoria de sesión» de la identidad (`BRAIN.md`, o
    `CLAUDE.md` si la identidad todavía no se movió) → el texto nuevo.
Esos textos viajan por Obsidian a máquinas que pueden tener la versión
anterior de Workspace, donde `workspace memoria nota` no existe: por eso dicen
qué hacer ahí (una línea fechada al final de `## Historial`, que la versión
nueva lee como nota). Esa alternativa se retira dos versiones después.
Lo personalizado no se toca: para esos cerebros, el paquete que Workspace
inyecta al abrir cada pestaña ya dice cómo guardar y que reemplaza la
instrucción vieja. Respaldo antes de escribir, idempotente, nunca borra.
"""
import hashlib
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
MID = "202610170100_memoria_v1"
README = os.path.join("STATE", "sessions", "README.md")
IDENTIDAD = ("BRAIN.md", "CLAUDE.md")

#: sha256 de cada versión de la plantilla vieja de STATE/sessions/README.md
#: (historial de templates/agent/brain), tal cual y con las líneas que
#: renombra brain_format (el nombre anterior del producto). Solo un README
#: IDÉNTICO a una de ellas se reemplaza: uno con reglas propias no se toca.
README_PLANTILLAS = frozenset({
    "d1ce315bdccdf6b861886c844c6c142a94c43cc877e114f5aa5904f08d9d33dc",   # 47180db
    "a0807dc0a649c8585d7fa809e5f2f0da7956c241d066fdc3bcc53140cce15736",   # 9e5b797, 27dfd65
    "46ca0b0964e7369ebf1f10818e5ede74d452df4e29e0b56f94e9500910e3b8ce",   # cd6bae2
    "0722db90cbb660936f9d92afa229409be6498e154a13a5a7a7b0505114e81fa7",   # 20b49f4
    "c4c41fd1538c51a2a010c03e0982e14e5207232533e34ebadf7b19787bd6fb71",   # 20b49f4 renombrada
    "95685f7deba8f5a44765240a106a9616aa051bd2edf221280b2ebbd031b1e5c0",   # a8f34a2 (la primera)
    "f428040005ec6c0b2e8c41f2e6cb873747c2632c39ec3d43a31220a0d92c1a5d",   # de7dffd (revisión: pestañas no latinas)
    # memoria v1 sin la alternativa para una versión anterior (revisión 0.3.4)
    "0a909608e45bc585aa0de9ba1f3c466518908655f14043f4dc15ce0939997d3b",   # f2d5342
    "4e3ea1636635f8fd55cd1712dff49ebb79839f2d463e0ddbd920a80bfaa015ee",   # 89d368a
})

#: sha256 de cada versión vieja de la sección «2.5» de la identidad (misma
#: regla: tal cual o renombrada, normalizada con norm_25).
P25_PLANTILLAS = frozenset({
    "368c3ff9e95a4ebf11a4e95eaa6b863dfc939163a857b4b617b08202ebdf9638",   # 9e5b797 … 47180db
    "bbd5d365d87045e2e35088036f92c44f4756fc5c27e4ef496002bb6354746b3f",   # 20b49f4, cd6bae2
    "1fe2f6793efac64748570b175fbd729e7f53bd40ec92df222e7a2edf7ce4a6b6",   # a8f34a2 (con viñetas)
    "76b9d62e98b267190645cf1aec714ebe877a5c31b52e27661bd6237d35d365ef",   # f2d5342 (v1 sin alternativa)
})

_TITULO_README = "# Memoria de sesión (por pestaña, por socio)"
_SECCION_25 = re.compile(r"^## 2\.5\b.*$", re.M)
_SIGUIENTE = re.compile(r"^## ", re.M)


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def _sha(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def norm_readme(texto):
    """(texto con el nombre del agente vuelto a los marcadores, nombre visible)
    o (None, "") si no tiene la forma de la plantilla."""
    texto = (texto or "").replace("\r\n", "\n")
    if not texto.startswith(_TITULO_README):
        return None, ""
    m = re.search(r"trabajo con (.+?)\. Complementa", texto, re.S)
    if m:
        norm = texto.replace(m.group(0), "trabajo con {{AGENT_DISPLAY}}. Complementa", 1)
    else:
        # memoria v1: «…de trabajo con\n<nombre>, igual en todos los motores (…)»
        m = re.search(r"trabajo con\n(.+?), igual en todos los motores", texto)
        if not m:
            return None, ""
        norm = texto.replace(m.group(0), "trabajo con\n{{AGENT_DISPLAY}}, igual en todos los motores", 1)
    norm = re.sub(r"`[a-z0-9][a-z0-9_-]*-dashboard\.py`", "`{{AGENT_NAME}}-dashboard.py`", norm)
    norm = re.sub(r"`\.claude/[a-z0-9][a-z0-9_-]*-workspaces\.json`",
                  "`.claude/{{AGENT_NAME}}-workspaces.json`", norm)
    norm = re.sub(r"`([A-Z]+_WS)`/`[A-Z0-9_-]+_WS`", r"`\1`/`{{AGENT_UPPER}}_WS`", norm)
    return norm, " ".join(m.group(1).split())


def seccion_25(texto):
    """(inicio, fin) de la sección «## 2.5 …» hasta el siguiente «## », o None."""
    m = _SECCION_25.search(texto or "")
    if not m:
        return None
    sig = _SIGUIENTE.search(texto, m.end())
    return m.start(), (sig.start() if sig else len(texto))


def norm_25(seccion):
    s = (seccion or "").replace("\r\n", "\n").rstrip()
    return re.sub(r"\(y `[A-Z0-9_-]+_WS`\)", "(y `{{AGENT_UPPER}}_WS`)", s)


def _plantilla(root, rel):
    return _read(os.path.join(root, "templates", "agent", "brain", rel))


def _read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _texto(crudo):
    try:
        return crudo.decode("utf-8").replace("\r\n", "\n") if crudo else None
    except UnicodeDecodeError:
        return None


def _plan(brain, root):
    """[(rel, bytes_leídos, texto_nuevo)]: los bytes leídos sirven para no
    pisar una edición (o un sync) que llegue entre leer y escribir."""
    jobs = []
    crudo = _read_bytes(os.path.join(brain, README))
    norm, display = norm_readme(_texto(crudo))
    nuevo = _plantilla(root, README)
    if norm is not None and nuevo and _sha(norm) in README_PLANTILLAS:
        jobs.append((README, crudo, nuevo.replace("{{AGENT_DISPLAY}}", display or "tu agente")))
    tpl = _plantilla(root, "BRAIN.md") or ""
    span_tpl = seccion_25(tpl)
    if not span_tpl:
        return jobs
    nueva = tpl[span_tpl[0]:span_tpl[1]]
    for rel in IDENTIDAD:
        crudo = _read_bytes(os.path.join(brain, rel))
        lf = _texto(crudo)
        if not lf:
            continue
        span = seccion_25(lf)
        if span and _sha(norm_25(lf[span[0]:span[1]])) in P25_PLANTILLAS:
            jobs.append((rel, crudo, lf[:span[0]] + nueva + lf[span[1]:]))
    return jobs


def trabajos(brain, root=ROOT):
    """[(rel, texto_nuevo)] de lo que hay que cambiar en `brain` (vacío = al día)."""
    return [(rel, nuevo) for rel, _crudo, nuevo in _plan(brain, root)]


def backup_dir(state_dir, brain, name=None):
    """`<estado>/backups/<MID>/<agente>-<hash de la ruta>`: dos cerebros con el
    mismo nombre (se quitó uno y se cargó otro) no comparten respaldo."""
    real = os.path.realpath(brain)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name or os.path.basename(real)) or "cerebro"
    return os.path.join(state_dir, "backups", MID,
                        "%s-%s" % (safe, hashlib.sha256(real.encode("utf-8")).hexdigest()[:8]))


def actualizar(brain, root=ROOT, state_dir=None, name=None, dry_run=False):
    """Aplica `trabajos(brain)` con respaldo en `backup_dir(...)`. Un archivo
    que cambió desde que se leyó se deja para la próxima puerta. Devuelve las
    rutas cambiadas."""
    jobs = _plan(brain, root)
    if not jobs or dry_run:
        return [rel for rel, _c, _n in jobs]
    if state_dir is None:
        import paths
        state_dir = paths.state_dir()
    backup = backup_dir(state_dir, brain, name)
    hechos = []
    for rel, crudo, texto in jobs:
        src = os.path.join(brain, rel)
        if _read_bytes(src) != crudo:
            continue
        bk = os.path.join(backup, rel)
        if not os.path.exists(bk):              # el primero es el original
            os.makedirs(os.path.dirname(bk), exist_ok=True)
            shutil.copy2(src, bk)
        tmp = src + ".tmp-%d" % os.getpid()
        crlf = b"\r\n" in crudo
        with open(tmp, "w", encoding="utf-8", newline="\r\n" if crlf else "\n") as fh:
            fh.write(texto)
        if _read_bytes(src) != crudo:           # llegó una edición mientras tanto
            os.remove(tmp)
            continue
        os.replace(tmp, src)
        hechos.append(rel)
        _avisar_formato_v2(brain, rel, crudo, src, state_dir)
    return hechos


def _avisar_formato_v2(brain, rel, crudo, src, state_dir):
    """Este cambio es de Workspace, no del dueño: el «deshacer» del formato v2
    (brain_format) lo tiene que reconocer como suyo. Falla-suave."""
    try:
        import brain_format
        nuevo = _read_bytes(src)
        if nuevo is not None:
            brain_format.nota_cambio_de_workspace(brain, rel.replace(os.sep, "/"), crudo, nuevo,
                                                  state_dir)
    except Exception:
        pass
