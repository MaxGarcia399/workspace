#!/usr/bin/env python3
"""WORKSPACE · brain_write — la PUERTA SEGURA para escribir dentro de un cerebro.

Por qué existe (2026-10-16): vivía dentro de `dream.py`, el destilador de
memoria que corría un LLM SIN VENTANA (`claude -p`) y dejaba propuestas para que
un humano las aprobara. El dueño retiró ese diseño (nada de agentes headless en la
máquina del cliente, nada de aprobación humana en el proceso de memoria), pero
la puerta segura la usan otros módulos (skill_loop, skill_audit, brain_cleanup)
y es buena: se queda aquí, sin nada del destilador.

Qué garantiza `_write_brain_file` (sin cambios respecto de dream.py):
  · veta los canónicos que esta puerta no escribe: `MEMORY.md` (cualquier
    carpeta, sin importar mayúsculas) y `BOOT/`. El veto es de ESTA puerta:
    desde memoria v1, `memoria.py` (código sin IA, con candado) escribe solo su
    propia sección «Aprendido en las sesiones» de `STATE/MEMORY.md`;
  · la ruta RESUELTA (realpath: colapsa `..` y enlaces) debe caer DENTRO del
    cerebro — y se re-veta sobre la ruta resuelta;
  · GATE DURO de secretos (secret_scan, N14): con un secreto sin exención NO
    escribe (`SecretWrite`); escapes: `workspace:allow-secret` por línea o
    `WORKSPACE_ALLOW_SECRET=1`;
  · escritura ATÓMICA (tmp único por pid + os.replace); el append es
    leer-concatenar-reemplazar, nunca un archivo a medias.

Más los helpers chicos que esos módulos compartían con dream (lock N8, slug,
socio, codificación del cerebro, fingerprint, bloques con marcadores).
Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Falla-suave en lo
opcional (olock, secret_scan, session_paths son amputables).
"""
import datetime
import hashlib
import os
import re
import sys
import unicodedata

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import session_paths
except Exception:
    session_paths = None
try:
    from olock import file_lock, LockTimeout
except Exception:
    file_lock, LockTimeout = None, None
try:
    import secret_scan
except Exception:
    secret_scan = None

#: Archivos del cerebro que NINGÚN proceso automático escribe, pase lo que pase.
FORBIDDEN_BASENAMES = ("memory.md",)
FORBIDDEN_DIRS = ("BOOT",)


# ── helpers genéricos ──────────────────────────────────────────────────────
def _now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode(
        "ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _brain_enc(brain):
    """<enc> de Claude Code para este cerebro (vía session_paths, única
    fuente de verdad de la codificación)."""
    if session_paths:
        try:
            return os.path.basename(session_paths.session_dir(brain))
        except Exception:
            pass
    real = os.path.realpath(os.path.expanduser(brain))
    return re.sub(r"[^a-zA-Z0-9]", "-", real)


def _socio(brain):
    try:
        s = open(os.path.join(brain, ".claude", "socio.local"),
                 encoding="utf-8").read()
        s = re.sub(r"[^a-z0-9_-]", "", s.strip().lower())
        return s or "equipo"
    except Exception:
        return "equipo"


def _fingerprint(path, prompt_version=""):
    """SHA-256 del archivo + una versión (para que un cambio de criterio
    invalide un «sin cambios»)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    h.update((prompt_version or "").encode("utf-8"))
    return h.hexdigest()


def _lock_timeout():
    """Segundos de espera de un lock N8. WORKSPACE_BRAIN_LOCK_TIMEOUT; se
    respeta el nombre viejo (WORKSPACE_DREAM_LOCK_TIMEOUT) por compatibilidad."""
    for var in ("WORKSPACE_BRAIN_LOCK_TIMEOUT", "WORKSPACE_DREAM_LOCK_TIMEOUT"):
        raw = os.environ.get(var)
        if raw:
            try:
                return float(raw)
            except ValueError:
                break
    return 10.0


def _extract_block(text, begin, end):
    i = text.find(begin)
    j = text.find(end, i + len(begin)) if i >= 0 else -1
    if i < 0 or j < 0:
        return None
    return text[i + len(begin):j].strip("\n")


# ── escrituras al cerebro (chokepoint + secret-scan) ───────────────────────
class ForbiddenWrite(RuntimeError):
    """Intento de escribir un archivo vetado del cerebro (MEMORY.md, BOOT/) o
    fuera de él."""


class SecretWrite(ForbiddenWrite):
    """Gate duro: el contenido trae un secreto sin exención → no se escribe.
    Subclase de ForbiddenWrite: el manejo `except ForbiddenWrite` lo cubre."""


def _vetoed(rel):
    rel = rel.replace("\\", "/")
    return (os.path.basename(rel).lower() in FORBIDDEN_BASENAMES
            or rel.split("/", 1)[0].lower() in tuple(d.lower() for d in FORBIDDEN_DIRS))


def _write_brain_file(brain, relpath, content, append=False):
    """ÚNICO punto por el que los procesos de Workspace escriben dentro de un
    cerebro. Ver el docstring del módulo. Devuelve la ruta escrita."""
    rel_norm = relpath.replace("\\", "/")
    if _vetoed(rel_norm):
        raise ForbiddenWrite("escritura vetada en el cerebro: %s (MEMORY.md y "
                             "BOOT/ no se escriben por esta puerta)" % relpath)
    path = os.path.join(brain, *rel_norm.split("/"))
    real_brain = os.path.realpath(brain)
    real_dest = os.path.realpath(path)
    if not real_dest.startswith(real_brain + os.sep):
        raise ForbiddenWrite("escritura fuera del cerebro: %s" % relpath)
    rel_real = os.path.relpath(real_dest, real_brain).replace("\\", "/")
    if _vetoed(rel_real):
        raise ForbiddenWrite("escritura en zona vetada del cerebro: %s" % relpath)
    _gate_secrets(content, rel_real)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if append:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read() + content
        except FileNotFoundError:
            pass
    tmp = "%s.tmp-%d" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return path


def _gate_secrets(text, where=""):
    """Gate duro sobre lo que va al cerebro: secreto sin exención → SecretWrite.
    Sin secret_scan → pasa (módulo amputable; el doctor sigue vigilando)."""
    if not secret_scan or not text:
        return
    findings = secret_scan.gate_text(text, where=where)
    if not findings:
        return
    raise SecretWrite(secret_scan.block_message(findings, where))
