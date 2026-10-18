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
paste de diagnóstico. Los secretos viven aislados, con permisos estrechos.

Dos clases de secreto, y NINGUNA llega a un motor ni a lo que corra el agente
(revisión 2026-10 — antes se exportaba TODO y cada motor lo heredaba):
  · API keys de provider (lista blanca PROVIDER_KEYS): el hub las CARGA a SU
    env al arrancar (load_into_env) — de ahí las lee connectors._resolve_key —
    y deja la marca WORKSPACE_SECRETS_LOADED con sus NOMBRES. Quien lanza un
    motor las quita (engine_env / strip_from_environ): ni el motor ni el
    agente las ven; cada motor usa el proveedor que el socio configuró en él.
  · Credenciales INTERNAS (tokens OAuth de Google, client_secret, URLs
    privadas del calendario): su dueño las lee de disco con get()
    (google_auth, gcal) y JAMÁS van al entorno, ni siquiera al del hub — el
    entorno lo hereda CADA proceso hijo; un `env` las dejaría en el chat.

INVARIANTES:
  · El VALOR jamás se loguea ni se devuelve por `names()` (solo NOMBRES).
  · Al env del HUB sale SOLO la lista blanca; scrub_env quita las internas
    que un hub de una versión anterior dejó exportadas (sin pisar la URL del
    calendario que el socio fije a propósito en su sistema).
  · Al env de un MOTOR no sale NADA de la bóveda: engine_env /
    strip_from_environ quitan lo marcado, las copias internas y cualquier
    valor idéntico al guardado (tests/test_secretos_no_llegan_al_motor.py y
    tests/test_secret_store_entorno.py).
  · El env REAL del sistema GANA: load_into_env usa setdefault por default
    (una key exportada a mano no se pisa con la del store).
  · Nombres válidos = env-var POSIX en mayúsculas (`^[A-Z][A-Z0-9_]*$`) — un
    nombre raro no se escribe (evita inyección de líneas).
  · Escritura atómica (tmp + os.replace) y chmod 0600 best-effort.

Cero dependencias (stdlib, 3.9+). Mac/Linux/Windows. Amputable: borra el
archivo y el harness sigue — los providers reportan "sin credencial" honesto.
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True

#: Nombre de env-var POSIX en mayúsculas — lo que un provider declara en
#: env_vars. Un nombre fuera de esto NO se persiste (no se cuela una línea
#: arbitraria al archivo).
_NAME_RX = re.compile(r"^[A-Z][A-Z0-9_]*$")

#: LISTA BLANCA — lo ÚNICO de la bóveda que puede salir al entorno (y de ahí a
#: cada motor): las API keys que declaran los providers/*.json de serie
#: (`env_vars`). Todo lo demás que guarde la bóveda es credencial INTERNA de
#: WORKSPACE y jamás se exporta. ¿Provider nuevo con otra key? Agrega aquí su
#: NOMBRE (tests/test_secret_store_entorno.py lo exige).
PROVIDER_KEYS = frozenset((
    "ANTHROPIC_API_KEY",       # providers/anthropic-api.json
    "GEMINI_API_KEY",          # providers/gemini-api.json
    "GOOGLE_API_KEY",          # providers/gemini-api.json (alternativa)
    "OPENAI_API_KEY",          # providers/openai.json
    "OPENROUTER_API_KEY",      # providers/openrouter.json
))

#: Credenciales INTERNAS que nadie lee del entorno (su dueño las lee de la
#: bóveda): en el env solo pueden ser la copia que exportaba un hub viejo, así
#: que scrub_env las quita SIEMPRE — aunque su nombre ya no esté en la bóveda
#: (p. ej. la cuenta de Google que desconectaste).
INTERNAL_NAMES = frozenset((
    "WORKSPACE_GOOGLE_OAUTH_CLIENT",     # google_auth.CLIENT_VAR
    "WORKSPACE_GOOGLE_OAUTH_ACCOUNTS",   # google_auth.ACCOUNTS_VAR
    "WORKSPACE_GCAL_ACCOUNTS",           # gcal.ACCOUNTS_VAR
))

#: Credenciales internas que el SISTEMA puede fijar a propósito por env y
#: entonces mandan sobre la bóveda (gcal: la URL única del calendario). De
#: estas, scrub_env quita solo la COPIA: un valor que la bóveda ya guarda.
ENV_OVERRIDES = frozenset((
    "WORKSPACE_GCAL_ICS_URL",            # gcal.URL_VAR
))


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
    """Exporta a os.environ SOLO las API keys de la lista blanca
    (PROVIDER_KEYS) y devuelve los NOMBRES cargados; las credenciales
    internas se quedan en disco. Por default NO pisa una env ya presente (el
    env real del sistema gana); overwrite=True fuerza. Falla-suave → []. El
    harness llama esto UNA vez al arrancar (front.main) para que
    connectors._resolve_key vea las keys; los motores no: ver engine_env."""
    loaded = []
    try:
        data = _read_raw()
    except Exception:
        return loaded
    for name, val in data.items():
        if name not in PROVIDER_KEYS:
            continue                       # interna: jamás al entorno
        if not overwrite and os.environ.get(name):
            continue
        os.environ[name] = val
        loaded.append(name)
    if loaded:
        # Solo NOMBRES (jamás valores): así el proceso hijo que lanza un motor
        # (dispatch) sabe qué quitar aunque no haya cargado nada él mismo.
        prev = set(loaded_names())
        os.environ[LOADED_ENV] = ",".join(sorted(prev | set(loaded)))
    return sorted(loaded)


# ── Los motores NO heredan la bóveda ────────────────────────────────────────
#: Marca en el env con los NOMBRES que load_into_env volcó (separados por
#: coma). Viaja a los procesos hijos del hub; los valores no.
LOADED_ENV = "WORKSPACE_SECRETS_LOADED"


def loaded_names(env=None):
    """NOMBRES que load_into_env puso en el env (`env` o os.environ). Lo que
    el usuario exportó a mano no aparece: eso no lo cargó la bóveda."""
    env = os.environ if env is None else env
    raw = env.get(LOADED_ENV) or ""
    return sorted({n.strip() for n in raw.split(",") if valid_name(n.strip())})


def _stored_texts(data):
    """Todo texto que guarda la bóveda: cada valor y, si es JSON, cada texto
    que lleva adentro (p. ej. la URL de cada cuenta del calendario)."""
    out, stack = set(), list(data.values())
    for val in data.values():
        try:
            stack.append(json.loads(val))
        except ValueError:
            pass                           # valor plano, no JSON
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            out.add(item.strip())
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return out


def scrub_env(env=None):
    """Quita de `env` (default: os.environ) las credenciales INTERNAS que son
    copia de la bóveda. Un hub de una versión anterior las exportaba todas y
    ese entorno sobrevive a los re-exec (actualizar → reabrir el hub, Esc →
    volver al hub): sin esto la fuga seguiría viva en la terminal abierta.
    Quita las INTERNAL_NAMES siempre, todo otro nombre guardado fuera de la
    lista blanca y, de las ENV_OVERRIDES, solo un valor que la bóveda guarda
    —tal cual o dentro de otro secreto: la URL vieja del calendario se MIGRA
    a la lista de cuentas y su nombre sale de la bóveda—. No toca las API
    keys (el hub las necesita; al motor se las quita engine_env), las
    variables que no son credenciales de WORKSPACE ni una URL DISTINTA que el
    socio fijó en su sistema (esa manda). Devuelve los NOMBRES quitados.
    Falla-suave → []."""
    if env is None:
        env = os.environ
    data = _read_raw()
    stored = None
    gone = []
    for name in sorted(set(data) | INTERNAL_NAMES | ENV_OVERRIDES):
        if name in PROVIDER_KEYS or name not in env:
            continue
        if name in ENV_OVERRIDES:
            if stored is None:
                stored = _stored_texts(data)
            val = (env.get(name) or "").strip()
            if not val or val not in stored:
                continue                   # ajuste propio del sistema: manda
        env.pop(name, None)
        gone.append(name)
    return gone


def _strip_for_engine(env):
    """Deja `env` (in situ) sin NADA de la bóveda, para lanzar un motor:
    lo que cargó load_into_env (por la marca) y la marca; las copias internas
    de un hub viejo (scrub_env); y cualquier variable cuyo valor es IDÉNTICO
    al que guarda la bóveda — la copia SIN marca de una API key que exportaba
    un hub de una versión anterior. Lo que el socio exportó a mano con OTRO
    valor se respeta. Devuelve los NOMBRES quitados (ordenados)."""
    gone = set()
    for name in loaded_names(env):
        if name in env:
            env.pop(name, None)
            gone.add(name)
    env.pop(LOADED_ENV, None)
    data = _read_raw()
    gone.update(scrub_env(env))
    for name, val in data.items():
        cur = env.get(name)
        if cur is not None and val.strip() and cur.strip() == val.strip():
            env.pop(name, None)
            gone.add(name)
    return sorted(gone)


def engine_env(env=None):
    """Copia de `env` (u os.environ) SIN nada de la bóveda: es el env que
    recibe un motor. El hub conserva sus valores (connectors los lee de su
    env; el calendario, de la bóveda); el motor y lo que corra el agente, no.
    Falla-suave: si algo falla, al menos sin lo marcado."""
    out = dict(os.environ if env is None else env)
    try:
        _strip_for_engine(out)
    except Exception:
        for name in loaded_names(out):
            out.pop(name, None)
        out.pop(LOADED_ENV, None)
    return out


def strip_from_environ():
    """Quita de os.environ todo lo de la bóveda (como engine_env, in situ).
    Lo llama el lanzador de motores (dispatch) antes de abrir uno. Devuelve
    los NOMBRES quitados. Falla-suave → []."""
    try:
        return _strip_for_engine(os.environ)
    except Exception:
        return []




if __name__ == "__main__":
    # inspección rápida (NUNCA imprime valores): python3 secret_store.py
    print("bóveda: %s" % store_path())
    ns = names()
    print("secretos guardados (%d): %s" % (len(ns), ", ".join(ns) or "—"))
