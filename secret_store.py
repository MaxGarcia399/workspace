#!/usr/bin/env python3
"""WORKSPACE · secret_store — bóveda de secretos PER-MÁQUINA (fuera del repo).

LA REGLA DE ORO (ARCHITECTURE.md § seguridad · espejo de connectors.py y
model_resolver): una credencial (API key / token) JAMÁS se versiona ni se
sincroniza. Los `providers/*.json` y `settings.json` llevan el NOMBRE de la
env-var, nunca el valor. Este módulo es DÓNDE vive el valor: un archivo
per-máquina, gitignoreado (`*.local`), con permisos 0600.

    ~/.claude/workspace/secrets.local        (junto a settings.json)

Formato: líneas `NOMBRE=valor`, una por variable. Sin interpolación de shell,
sin `export`, sin comillas mágicas — el valor es TODO lo que sigue al primer
`=` (así una key con `=` adentro no se parte). Comentarios con `#`.

Por qué NO settings.json: settings.json puede acabar en un backup, un log o un
paste de diagnóstico. Los secretos viven aislados, con permisos estrechos, y
el harness los CARGA al env al arrancar (load_into_env) — de ahí los leen
connectors._resolve_key y el CLI del motor, siempre desde os.environ, nunca
desde disco en caliente.

INVARIANTES:
  · El VALOR jamás se loguea ni se devuelve por `names()` (solo NOMBRES).
  · El env REAL del sistema GANA: load_into_env usa setdefault por default
    (una key exportada a mano no se pisa con la del store).
  · Nombres válidos = env-var POSIX en mayúsculas (`^[A-Z][A-Z0-9_]*$`) — un
    nombre raro no se escribe (evita inyección de líneas).
  · Escritura atómica (tmp + os.replace) y chmod 0600 best-effort.

Cero dependencias (stdlib, 3.9+). Mac/Linux/Windows. Amputable: borra el
archivo y el harness sigue — los providers reportan "sin credencial" honesto.
"""
import os
import re
import sys

sys.dont_write_bytecode = True

#: Nombre de env-var POSIX en mayúsculas — lo que un provider declara en
#: env_vars. Un nombre fuera de esto NO se persiste (no se cuela una línea
#: arbitraria al archivo).
_NAME_RX = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _workspace_dir():
    """Dir per-máquina de WORKSPACE (SSOT en paths.workspace_dir — respeta un HOME
    parchado en tests)."""
    import paths
    return paths.workspace_dir()


def store_path():
    """Ruta de la bóveda. `.local` ⇒ ya cubierto por el `.gitignore` del repo
    y por cualquier `*.local` per-máquina — jamás se versiona ni sincroniza."""
    return os.path.join(_workspace_dir(), "secrets.local")


def valid_name(name):
    """True si `name` es un nombre de env-var persistible."""
    return bool(isinstance(name, str) and _NAME_RX.match(name))


def _read_raw():
    """{NOMBRE: valor} del archivo. Falla-suave → {}. Tolerante: ignora
    líneas en blanco, comentarios (#) y líneas sin `=` o con nombre inválido."""
    out = {}
    try:
        with open(store_path(), encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n").rstrip("\r")
                s = line.strip()
                if not s or s.startswith("#") or "=" not in line:
                    continue
                name, val = line.split("=", 1)
                name = name.strip()
                if valid_name(name):
                    out[name] = val
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return out


def _write_raw(data):
    """Escribe {NOMBRE: valor} atómico + chmod 0600. Solo nombres válidos y
    valores de una línea (un valor con salto se aplana — jamás rompe el
    formato de líneas). Levanta OSError si el disco falla."""
    d = _workspace_dir()
    os.makedirs(d, exist_ok=True)
    lines = ["# WORKSPACE secrets (per-máquina, NUNCA versionar) — NOMBRE=valor"]
    for name in sorted(data):
        if not valid_name(name):
            continue
        val = str(data[name]).replace("\n", " ").replace("\r", " ")
        lines.append("%s=%s" % (name, val))
    body = "\n".join(lines) + "\n"
    # El tmp nace YA con 0600 (O_CREAT|O_EXCL, modo en el open — no hay
    # ventana world-readable antes del chmod) y con nombre IMPREDECIBLE (otro
    # usuario no puede pre-crearlo ni plantar un symlink: O_EXCL no lo sigue).
    # Si algo falla antes del replace, el tmp se borra: nunca queda un archivo
    # huérfano con secretos en claro (auditoría 2026-07).
    import secrets as _rnd
    tmp = "%s.tmp-%d-%s" % (store_path(), os.getpid(), _rnd.token_hex(8))
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                 | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(body.encode("utf-8"))
        os.replace(tmp, store_path())
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(store_path(), 0o600)
    except OSError:
        pass                       # Windows / FS sin permisos POSIX — best-effort


def _locked():
    """Lock entre procesos del store (olock): set/remove son leer-modificar-
    escribir — sin lock, dos procesos a la vez pierden una escritura."""
    from olock import file_lock
    os.makedirs(_workspace_dir(), exist_ok=True)
    return file_lock(store_path(), timeout=5)


# ── API pública ─────────────────────────────────────────────────────────────
def names():
    """NOMBRES guardados (ordenados). JAMÁS devuelve valores."""
    return sorted(_read_raw().keys())


def has(name):
    """True si el store TIENE ese secreto (no dice nada del valor)."""
    return name in _read_raw()


def get(name):
    """Valor guardado o "" — uso interno / loader. No lo loguees."""
    return _read_raw().get(name, "")


def set_secret(name, value):
    """Guarda/actualiza un secreto. Devuelve {"ok":True,"name":name} o
    {"ok":False,"error":...}. Valida el NOMBRE (env-var mayúsculas) y que el
    valor no sea vacío. El valor jamás aparece en el resultado."""
    if not valid_name(name):
        return {"ok": False, "error": "nombre de env-var inválido: %r "
                "(esperado ^[A-Z][A-Z0-9_]*$)" % name}
    if not isinstance(value, str) or not value.strip():
        return {"ok": False, "error": "valor vacío — no se guarda"}
    try:
        with _locked():
            data = _read_raw()
            data[name] = value.strip()
            _write_raw(data)
    except Exception as e:
        return {"ok": False, "error": "no pude escribir el store (%s: %s)"
                % (type(e).__name__, e)}
    return {"ok": True, "name": name}


def remove(name):
    """Borra un secreto del store. {"ok":True,"name":name,"removed":bool}."""
    try:
        with _locked():
            data = _read_raw()
            removed = name in data
            if removed:
                data.pop(name, None)
                _write_raw(data)
    except Exception as e:
        return {"ok": False, "error": "no pude escribir el store (%s: %s)"
                % (type(e).__name__, e)}
    return {"ok": True, "name": name, "removed": removed}


def load_into_env(overwrite=False):
    """Vuelca el store a os.environ y devuelve los NOMBRES cargados. Por
    default NO pisa una env ya presente (el env real del sistema gana);
    overwrite=True fuerza. Falla-suave → []. El harness llama esto UNA vez al
    arrancar (front.main) para que connectors._resolve_key vea las keys."""
    loaded = []
    try:
        data = _read_raw()
    except Exception:
        return loaded
    for name, val in data.items():
        if not valid_name(name):
            continue
        if not overwrite and os.environ.get(name):
            continue
        os.environ[name] = val
        loaded.append(name)
    return sorted(loaded)


if __name__ == "__main__":
    # inspección rápida (NUNCA imprime valores): python3 secret_store.py
    print("bóveda: %s" % store_path())
    ns = names()
    print("secretos guardados (%d): %s" % (len(ns), ", ".join(ns) or "—"))
