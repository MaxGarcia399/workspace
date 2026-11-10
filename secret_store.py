#!/usr/bin/env python3
"""WORKSPACE · secret_store — bóveda de secretos PER-MÁQUINA (fuera del repo).

LA REGLA DE ORO (ARCHITECTURE.md § seguridad · espejo de connectors.py y
model_resolver): una credencial (API key / token) JAMÁS se versiona ni se
sincroniza. Los `providers/*.json` y `settings.json` llevan el NOMBRE de la
env-var, nunca el valor. Este módulo es DÓNDE vive el valor.

DÓNDE VIVE (fase B, 2026-11-08): en el LLAVERO DEL SISTEMA, detrás de la
misma API de siempre (get/set_secret/remove/names/has: los llamadores no
cambian). Por sistema:

  · macOS: el llavero de inicio de sesión, con `/usr/bin/security` (ruta
    absoluta). Servicio `workspace.<NOMBRE>`, cuenta `<usuario>:<gen>:<i>`.
    El VALOR jamás va en argv: se escribe con `security -i` y el comando por
    la entrada estándar (en `ps` solo se ve `security -i`); se lee con
    `find-generic-password -w`. Va en base64 (`ws2:<partes>:<huella>:…`) y
    en trozos de 2000 caracteres: `security -i` corta la línea en 4096
    bytes (VERIFICADO 2026-11-08 en macOS 26.5 con un llavero temporal).
    NUNCA se actualiza un elemento en su lugar (`-U`): con un elemento ya
    existente, `security` se quedó esperando (un diálogo de autorización,
    VERIFICADO con el llavero temporal). Cada escritura crea elementos NUEVOS
    (otra `gen`), los verifica leyéndolos, cambia el índice y solo entonces
    borra los viejos. Antes de cada llamada se mira, sin diálogo
    (Security.framework `SecKeychainGetStatus`), que el llavero esté
    abierto: cerrado (p. ej. por SSH) = «sin llavero», jamás un diálogo para
    abrirlo. Leer TODA la bóveda es un solo `security -i` (leer_lote). Cada
    llamada tiene tiempo límite; si una se pasa (un diálogo inesperado), el
    llavero descansa 1, 2, 5 y como mucho 15 min (_ESPERAS_S) y se reintenta;
    mientras, un aviso de una línea lo dice (nunca «sin llave» en silencio).
  · Windows: DPAPI de usuario (crypt32 `CryptProtectData`, con
    `CRYPTPROTECT_UI_FORBIDDEN`, por ctypes): el cifrado queda en el índice
    (`v2:dpapi:<base64>`), solo-dueño (acl_privada). Lo descifra solo esta
    cuenta de Windows en esta máquina. disponible() prueba cifrar Y
    descifrar un valor falso (VERIFICADO 2026-11-08 por ssh en la PC).
  · Linux: `secret-tool` (libsecret / Secret Service) si existe, hay sesión
    de D-Bus y la colección por defecto existe y está ABIERTA (se lee su
    propiedad `Locked` por gdbus/busctl: sin diálogo); el valor por la
    entrada estándar. Si no, el archivo 0600 de siempre, con aviso.

ARCHIVOS (todos en el dir de estado, fuera del cerebro: ni Obsidian Sync ni
git los ven):
    ~/.claude/workspace/secrets.local        el de siempre (v1: NOMBRE=valor);
                                             tras migrar, una CARPETA sello
    ~/.claude/workspace/boveda/indice.local  v2: NOMBRE=v2:<dónde>[:<dato>]
    ~/.claude/workspace/boveda/plano.local   ya sellado: lo que quede sin llavero
    ~/.claude/workspace/boveda/estado.json   migración, respaldos, avisos (con candado)
    ~/.claude/workspace/boveda/respaldo-*    respaldo DPAPI (o en claro, solo mientras migra)
El texto plano (`secrets.local` o, ya sellado, `boveda/plano.local`) es el
plan B: sin llavero que funcione, todo se guarda ahí (0600 corregido en cada
escritura), y lo que tenga GANA a lo del índice (es lo más nuevo). Tras
migrar, `secrets.local` queda SELLADO (una carpeta con un LEEME): un hub o
un hook de una versión anterior abierto durante la actualización ve «sin
llave» hasta reiniciar y no puede escribir un archivo a medias que tape lo
del llavero — nada se pierde ni se borra. Volver atrás con `workspace update
--rollback` deshace la migración ANTES (updater.deshacer_para_volver).
Cualquier lectura que no sea «no existe» y precede a una escritura, si
falla, aborta sin escribir (LecturaFallida).

SOLO LA INSTALACIÓN ACTIVA (instalacion_activa: la carpeta que abre el
comando `workspace` —aunque sea un git worktree—; no otro worktree ni una
copia vieja, ni un proceso cuyo código ya cambió en disco) guarda en el
llavero y migra; las demás leen.

MIGRACIÓN (migrar(), sin humano en el loop): la primera vez que hay valores
en texto plano y un llavero que funciona (al arrancar Workspace, en la
migración 202611081500_boveda_al_llavero y en cada escritura), mueve cada
valor al llavero, lo VERIFICA leyéndolo de vuelta por el camino de lectura y
solo entonces sella `secrets.local`. Antes deja un respaldo cifrado con el
mismo llavero (o, si no cupo, 0600 en boveda/ —nunca en el cerebro— que se
borra en cuanto la migración se verifica). Los respaldos cifrados caducan a
los RESPALDO_DIAS si todo se lee bien; las llaves archivadas, a los
ARCHIVADA_DIAS; y quitar o cambiar una llave borra sus copias (respaldos y
archivadas: tokens de Google incluidos). Idempotente, con el candado de la
bóveda (varios hubs abiertos) y falla-suave: si algo falla, todo queda como
estaba y funciona igual que hoy. Deshacer: deshacer() (`workspace migrate
--undo 202611081500_boveda_al_llavero`) vuelve a dejar todo en
`secrets.local` y apaga la migración automática; desinstalar borra lo del
llavero y, si estaba cerrado, lo deja anotado en `llavero-pendiente/` para
la próxima vez.

Dos clases de secreto, y NINGUNA llega a un motor ni a lo que corra el agente
(revisión 2026-10 — antes se exportaba TODO y cada motor lo heredaba):
  · API keys de provider (lista blanca PROVIDER_KEYS): el hub las CARGA a SU
    env al arrancar (load_into_env) — de ahí las lee connectors._resolve_key —
    y deja la marca WORKSPACE_SECRETS_LOADED con sus NOMBRES. Quien lanza un
    motor las quita (engine_env / strip_from_environ): ni el motor ni el
    agente las ven; cada motor usa el proveedor que el socio configuró en él.
  · Credenciales INTERNAS (tokens OAuth de Google, client_secret, URLs
    privadas del calendario): su dueño las lee con get() (google_auth, gcal)
    y JAMÁS van al entorno, ni siquiera al del hub — el entorno lo hereda
    CADA proceso hijo; un `env` las dejaría en el chat.

INVARIANTES:
  · El VALOR jamás se loguea, ni va en argv, ni se devuelve por `names()`
    (solo NOMBRES); en el índice nunca va el valor ni una huella suya (en
    Windows, solo el cifrado de DPAPI).
  · Al env del HUB sale SOLO la lista blanca; scrub_env quita las internas
    que un hub de una versión anterior dejó exportadas (sin pisar la URL del
    calendario que el socio fije a propósito en su sistema).
  · Al env de un MOTOR no sale NADA de la bóveda: engine_env /
    strip_from_environ quitan lo marcado, las copias internas, las variables
    EXCLUSIVAS de Workspace (TYPESAFE_API_KEY, WORKSPACE_DECIDER_*_KEY:
    siempre, aunque el socio las exporte a mano) y cualquier
    valor idéntico al guardado (tests/test_secretos_no_llegan_al_motor.py y
    tests/test_secret_store_entorno.py).
  · Ningún motor la LEE: rutas_protegidas.lectura_negada() (= rutas_sensibles)
    es la regla de lectura denegada que cada motor que lo soporta aplica.
  · Lo que imprime Workspace pasa por sin_valores() / decisions.redact: un
    valor de la bóveda sale como `[secret:stored]`.
  · El env REAL del sistema GANA: load_into_env usa setdefault por default
    (una key exportada a mano no se pisa con la del store).
  · Nombres válidos = env-var POSIX en mayúsculas (`^[A-Z][A-Z0-9_]*$`) — un
    nombre raro no se escribe (evita inyección de líneas).
  · Escritura atómica (tmp + os.replace), 0600 desde que nace; en Windows,
    ACL solo-dueño antes de escribir.

MODO (ajuste `otros.boveda`, modo_guardado): «auto» (de fábrica: el llavero
y, sin él, el archivo 0600 CON un aviso de una línea, nunca en silencio),
«keyring» (solo el llavero: sin él no se guarda nada) o «file» (el archivo;
lo que haya en el llavero vuelve al archivo al arrancar). fuentes() / la CLI
`workspace llaves` dicen de dónde sale cada llave (entorno · llavero ·
archivo) y auditar() / `workspace llaves auditar` busca restos en texto
plano en el dir de estado; ninguno imprime un valor.

Pruebas y emergencia: WORKSPACE_BOVEDA=archivo no toca ningún llavero (la
suite lo pone siempre: tests/_testutil); WORKSPACE_BOVEDA_LLAVERO=<ruta> usa
ese llavero de macOS en vez del de inicio de sesión (las pruebas usan uno
temporal propio).

Cero dependencias (stdlib, 3.9+). Mac/Linux/Windows. Amputable: borra los
archivos y el harness sigue — los providers reportan "sin credencial" honesto.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time

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
    "WORKSPACE_MAIL_PASSWORD",           # CORREO_PASS: la App Password del correo
))

#: La contraseña (App Password) de `workspace mail`: vive en la bóveda con
#: este nombre INTERNO (jamás al entorno del hub ni de un motor); `mail.json`
#: guarda solo lo que no es secreto (usuario, host, puerto). No es
#: WORKSPACE_SMTP_PASS: esa es la variable que el socio puede exportar a mano
#: (manda sobre la bóveda) y scrub_env no debe quitársela.
CORREO_PASS = "WORKSPACE_MAIL_PASSWORD"
#: La migración registrada que saca la contraseña de mail.json (su undo la
#: devuelve; updater.rollback la deshace antes de volver a una versión que la
#: lee de mail.json).
CORREO_MIGRACION_ID = "202611090000_correo_a_la_boveda"

#: Credenciales internas que el SISTEMA puede fijar a propósito por env y
#: entonces mandan sobre la bóveda (gcal: la URL única del calendario). De
#: estas, scrub_env quita solo la COPIA: un valor que la bóveda ya guarda.
ENV_OVERRIDES = frozenset((
    "WORKSPACE_GCAL_ICS_URL",            # gcal.URL_VAR
))

#: Las llaves de los DECISORES (deciders/*.py) se guardan con nombre propio,
#: WORKSPACE_DECIDER_<ID>_KEY — jamás con el estándar del proveedor: con
#: OPENROUTER_API_KEY, _strip_for_engine le quitaría a Hermes, OpenClaw u
#: opencode la que el socio exportó a mano con el mismo valor. Se portan como
#: ENV_OVERRIDES: el decisor las lee del entorno primero (el socio puede
#: fijarla en su sistema y entonces manda), así que scrub_env quita SOLO la
#: copia que la bóveda ya guarda; no son PROVIDER_KEYS (jamás se cargan al
#: entorno del hub: el decisor las lee de disco).
_DECIDER_KEY = re.compile(r"^WORKSPACE_DECIDER_[A-Z0-9_]+_KEY$")

#: La migración registrada (migrations/) que mueve la bóveda al llavero: su id
#: es el que deshace (`workspace migrate --undo <id>`).
MIGRACION_ID = "202611081500_boveda_al_llavero"

#: Pruebas / emergencia: `archivo` = no tocar ningún llavero (la suite lo pone
#: siempre); `llavero` | `dpapi` | `secret-tool` = forzar ese (pruebas).
ENV_MODO = "WORKSPACE_BOVEDA"
#: macOS: la ruta de un llavero propio en vez del de inicio de sesión (las
#: pruebas usan uno temporal; jamás el del socio).
ENV_LLAVERO = "WORKSPACE_BOVEDA_LLAVERO"

#: Texto en lugar de un valor de la bóveda en lo que imprime Workspace (el
#: mismo que pone decisions.redact).
TACHADO = "[secret:stored]"
#: Valores más cortos no se buscan para tacharlos (romperían palabras).
_TACHAR_MIN = 8


def es_llave_de_decisor(name):
    """¿Es el nombre propio de la llave de un decisor?"""
    return bool(isinstance(name, str) and _DECIDER_KEY.match(name))


#: Variables EXCLUSIVAS de Workspace: ningún motor envuelto las usa, así que
#: salen SIEMPRE del entorno de un motor (engine_env / strip_from_environ),
#: estén o no en la bóveda — también las que el socio exportó a mano. Son la
#: llave de Jev (TypeSafe) y las de nombre propio de los decisores
#: (WORKSPACE_DECIDER_<ID>_KEY). Las ESTÁNDAR de un proveedor que un motor sí
#: lee (OPENROUTER_API_KEY, OPENAI_API_KEY, LIQUID_API_KEY —opencode la toma
#: de su catálogo models.dev, proveedor «liquid»—…) NO entran aquí: si el
#: socio las exporta es para sus motores (Greptile 0.8.x, 1).
SOLO_WORKSPACE = frozenset(("TYPESAFE_API_KEY",))


def es_solo_workspace(name):
    """¿Es una variable exclusiva de Workspace (jamás al entorno de un motor)?"""
    return name in SOLO_WORKSPACE or es_llave_de_decisor(name)


def _workspace_dir():
    """Dir per-máquina de WORKSPACE (SSOT en paths.workspace_dir — respeta un HOME
    parchado en tests)."""
    import paths
    return paths.workspace_dir()


def store_path():
    """Ruta del archivo v1 de la bóveda (`NOMBRE=valor`). `.local` ⇒ ya
    cubierto por el `.gitignore` del repo y por cualquier `*.local`
    per-máquina — jamás se versiona ni sincroniza. Con llavero queda sin
    valores (solo un comentario)."""
    return os.path.join(_workspace_dir(), "secrets.local")


def boveda_dir():
    """Carpeta del índice v2, el estado de la migración y los respaldos."""
    return os.path.join(_workspace_dir(), "boveda")


def indice_path():
    """Índice v2: `NOMBRE=v2:<dónde>[:<dato>]` (nunca el valor)."""
    return os.path.join(boveda_dir(), "indice.local")


def _estado_path():
    return os.path.join(boveda_dir(), "estado.json")


def rutas_sensibles():
    """Rutas ABSOLUTAS que ningún motor debe leer: el archivo de la bóveda
    (y sus temporales: `secrets.local*`) y la carpeta boveda/ (índice,
    estado y respaldos). Las aplica cada motor como regla de LECTURA
    denegada (rutas_protegidas.lectura_negada)."""
    return (store_path(), boveda_dir())


def archivos_boveda():
    """Los archivos con nombre fijo dentro de boveda/ (índice, texto plano
    sellado, estado): para los motores cuya regla de negar compara la ruta
    EXACTA (Copilot: «exact or trailing-path-segment match; no glob support
    yet»), además de la carpeta."""
    return tuple(os.path.join(boveda_dir(), n) for n in ("indice.local", "plano.local",
                                                         "estado.json"))


def valid_name(name):
    """True si `name` es un nombre de env-var persistible."""
    return bool(isinstance(name, str) and _NAME_RX.match(name))


def _solo_mio(ruta, forzar=False):
    """Windows: la bóveda solo para tu usuario (y SYSTEM), sin heredar la ACL
    de la carpeta (QA 2026-11-07: `.claude` daba lectura a CodexSandboxUsers).
    En Mac/Linux lo hace el 0600. Falla-suave (acl_privada avisa en el log)."""
    try:
        import acl_privada
        return acl_privada.solo_mio(ruta) if forzar else acl_privada.asegurar(ruta)
    except Exception:
        return False


def _t(key, es, en=None, **kw):
    try:
        import workspace_status
        return workspace_status.t(key, es, en, **kw)
    except Exception:
        try:
            return es.format(**kw) if kw else es
        except Exception:
            return es


# ── archivos (v1, índice v2, estado) ────────────────────────────────────────
class LecturaFallida(OSError):
    """No pude LEER la bóveda (y no es que no exista): quien iba a escribir
    no escribe nada — regla de la casa: nunca escribir tras una lectura
    fallida (un índice ilegible un instante no puede volverse un índice
    vacío que borre las demás llaves)."""


def _leer_lineas(ruta, apretar=False, estricto=False):
    """{NOMBRE: resto} de un archivo `NOMBRE=…`. Solo «no existe» es vacío;
    otro error → {} (lectura suelta) o LecturaFallida con `estricto` (todo
    camino que lee para luego escribir). Tolerante con el contenido: ignora
    líneas en blanco, comentarios (#) y líneas sin `=` o con nombre
    inválido. `apretar`: en Windows, la primera vez en el proceso aprieta su
    ACL (la de antes heredaba la de la carpeta)."""
    out = {}
    if apretar and os.path.isfile(ruta):
        _solo_mio(ruta)
    try:
        with open(ruta, encoding="utf-8") as fh:
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
    except Exception as e:
        if estricto:
            raise LecturaFallida("%s: %s" % (type(e).__name__, ruta))
        return {}
    return out


#: Tras migrar, `secrets.local` deja de ser un archivo: queda una CARPETA con
#: este aviso. Así un hub o un hook de una versión ANTERIOR que siga abierto
#: durante la actualización no puede escribir un `secrets.local` a medias
#: que tape lo del llavero (su escritura falla y lo dice; sus lecturas dan
#: «sin llave» hasta reiniciar): nada se pierde ni se borra. Las llaves que
#: después queden en texto plano (sin llavero) van a `boveda/plano.local`.
_SELLO = "LEEME.txt"


def sellado():
    """¿`secrets.local` ya está sellado (es la carpeta de después de migrar)?"""
    return os.path.isdir(store_path())


def _ruta_plano():
    """El archivo de texto plano que vale hoy: `secrets.local` (el de
    siempre) o, ya sellado, `boveda/plano.local`. Sin `secrets.local` (ni
    archivo ni sello) y con `boveda/plano.local` —un deshacer cortado entre
    quitar el sello y escribir el archivo—, vale ese: lo más nuevo jamás
    queda sin leer (Greptile 0.9.0, 0)."""
    extra = os.path.join(boveda_dir(), "plano.local")
    if sellado():
        return extra
    p = store_path()
    if not os.path.lexists(p) and os.path.isfile(extra):
        return extra
    return p


def _leer_plano(estricto=False):
    """{NOMBRE: valor} del texto plano (v1)."""
    return _leer_lineas(_ruta_plano(), apretar=True, estricto=estricto)


def _leer_indice(estricto=False):
    """{NOMBRE: etiqueta} del índice v2 (solo las líneas `v2:`)."""
    return {n: v.strip() for n, v in _leer_lineas(indice_path(), apretar=True,
                                                   estricto=estricto).items()
            if v.strip().startswith("v2:")}


def _sellar():
    """(bajo el candado) `secrets.local` → la carpeta sello (ver _SELLO). Si
    no se puede, el archivo sin valores de siempre. → True si quedó sellado."""
    p = store_path()
    if os.path.isdir(p):
        return True
    try:
        if os.path.lexists(p):
            os.remove(p)
        os.mkdir(p, 0o700)
        with open(os.path.join(p, _SELLO), "w", encoding="utf-8") as fh:
            fh.write("Workspace: tus llaves viven en el llavero del sistema (indice: "
                     "../boveda/indice.local). Volver al archivo: workspace migrate --undo "
                     + MIGRACION_ID + "\n")
        return True
    except OSError:
        try:
            if not os.path.isdir(p):
                _escribir_privado(p, "# WORKSPACE secrets: las llaves viven en el llavero del "
                                  "sistema. Volver: workspace migrate --undo " + MIGRACION_ID + "\n")
        except OSError:
            pass
        return False


def _desellar():
    """(bajo el candado) Quita la carpeta sello (solo si trae lo nuestro)."""
    p = store_path()
    if not os.path.isdir(p):
        return
    for n in os.listdir(p):
        if n != _SELLO:
            raise LecturaFallida("secrets.local trae algo que no es de Workspace: %s" % n)
    try:
        os.remove(os.path.join(p, _SELLO))
    except FileNotFoundError:
        pass
    os.rmdir(p)


def _escribir_privado(ruta, body):
    """`body` (texto) a `ruta`, atómico y solo para el dueño. El tmp nace YA
    con 0600 (O_CREAT|O_EXCL, modo en el open — no hay ventana
    world-readable antes del chmod) y con nombre IMPREDECIBLE (otro usuario
    no puede pre-crearlo ni plantar un symlink: O_EXCL no lo sigue). Si algo
    falla antes del replace, el tmp se borra: nunca queda un archivo huérfano
    con secretos (auditoría 2026-07). Levanta OSError si el disco falla."""
    d = os.path.dirname(ruta)
    os.makedirs(d, exist_ok=True)
    if os.path.normcase(os.path.abspath(d)) == os.path.normcase(os.path.abspath(boveda_dir())):
        try:
            os.chmod(d, 0o700)             # boveda/: solo el dueño entra
        except OSError:
            pass
    import secrets as _rnd
    tmp = "%s.tmp-%d-%s" % (ruta, os.getpid(), _rnd.token_hex(8))
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                 | getattr(os, "O_BINARY", 0), 0o600)
    try:
        # Windows: la ACL de solo-tú ANTES de escribir (el replace conserva la
        # del tmp); en Mac/Linux ya nació 0600
        _solo_mio(tmp, forzar=True)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body.encode("utf-8"))
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass                       # Windows / FS sin permisos POSIX — best-effort


def _lineas(cabecera, data):
    lines = list(cabecera)
    for name in sorted(data):
        if not valid_name(name):
            continue
        val = str(data[name]).replace("\n", " ").replace("\r", " ")
        lines.append("%s=%s" % (name, val))
    return "\n".join(lines) + "\n"


def _write_raw(data):
    """Escribe el texto plano {NOMBRE: valor} (_ruta_plano): atómico + 0600
    (corregido en CADA escritura). Solo nombres válidos y valores de una
    línea (un valor con salto se aplana — jamás rompe el formato de líneas).
    Ya sellado y sin valores, el archivo se quita. Levanta OSError si el
    disco falla."""
    ruta = _ruta_plano()
    if not data and sellado():
        try:
            os.remove(ruta)
        except FileNotFoundError:
            pass
        return
    cab = ["# WORKSPACE secrets (per-máquina, NUNCA versionar) — NOMBRE=valor"]
    if not data and os.path.exists(indice_path()):
        cab.append("# Las llaves viven en el llavero del sistema (índice: boveda/indice.local). "
                   "Volver a este archivo: workspace migrate --undo " + MIGRACION_ID)
    _escribir_privado(ruta, _lineas(cab, data))


def _escribir_indice(indice):
    if not indice:
        try:
            os.remove(indice_path())
        except FileNotFoundError:
            pass
        return
    _escribir_privado(indice_path(), _lineas(
        ["# WORKSPACE · índice de la bóveda (v2): NOMBRE=v2:<dónde>[:<dato>]. "
         "Sin valores: viven en el llavero del sistema."], indice))


def _estado():
    try:
        with open(_estado_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _estado_poner(_estricto=False, **cambios):
    """Mezcla `cambios` en estado.json (None borra la clave) con su PROPIO
    candado (leer-mezclar-escribir: dos procesos a la vez no se pisan las
    claves). Falla-suave, salvo `_estricto` (la migración: si no puede
    anotar el respaldo, no migra)."""
    try:
        from olock import file_lock
        os.makedirs(boveda_dir(), exist_ok=True)
        with file_lock(_estado_path(), timeout=5 if _estricto else 2):
            try:
                with open(_estado_path(), encoding="utf-8") as fh:
                    d = json.load(fh)
                if not isinstance(d, dict):
                    raise ValueError("no es un objeto")
            except FileNotFoundError:
                d = {}
            except ValueError:
                # ilegible NO es vacío, pero tampoco puede trabar (la vuelta
                # atrás, la migración): se aparta intacto, se avisa y se
                # sigue con uno nuevo (revisor, R4)
                _apartar_ilegible(_estado_path())
                d = {}
            for k, v in cambios.items():
                if v is None:
                    d.pop(k, None)
                else:
                    d[k] = v
            _escribir_privado(_estado_path(), json.dumps(d, ensure_ascii=False, indent=1))
    except Exception:
        if _estricto:
            raise


def _apartar_ilegible(ruta):
    """Un archivo de estado ilegible se aparta —no se pisa ni se borra—:
    <ruta>.ilegible-<fecha>-<azar>, con un aviso de una línea (sin valores).
    Si no se puede apartar, LecturaFallida (entonces no se escribe)."""
    import secrets as _rnd
    dest = "%s.ilegible-%s-%s" % (ruta, time.strftime("%y%m%dT%H%M%S"), _rnd.token_hex(3))
    try:
        os.replace(ruta, dest)
    except OSError as e:
        raise LecturaFallida("%s: %s" % (type(e).__name__, ruta))
    try:
        sys.stderr.write("⚠ Workspace: %s no se podía leer; quedó aparte en %s (no se borró)\n"
                         % (ruta, dest))
    except Exception:
        pass
    return dest


def _locked(timeout=5):
    """Lock entre procesos del store (olock): set/remove/migrar son leer-
    modificar-escribir — sin lock, dos procesos a la vez pierden una
    escritura. No es reentrante: un lock por operación pública."""
    from olock import file_lock
    os.makedirs(_workspace_dir(), exist_ok=True)
    return file_lock(store_path(), timeout=timeout)


# ── los llaveros ────────────────────────────────────────────────────────────
class NoDisponible(Exception):
    """El llavero no está (o no respondió): se usa el archivo."""


#: Cada llamada a un programa del llavero tiene este tope (s): un diálogo
#: inesperado no cuelga a Workspace (y el llavero queda «trabado»).
_TIEMPO = 10
#: Tras un tiempo agotado el llavero descansa un rato y se reintenta: 1, 2, 5
#: y como mucho 15 min si se repite (s). Nunca un día entero por una llamada
#: lenta; y mientras tanto el aviso lo dice (aviso_pendiente).
_ESPERAS_S = (60, 120, 300, 900)
#: Cuántos caracteres de base64 caben en un elemento del llavero de macOS
#: (la línea de `security -i` corta en 4096 bytes; VERIFICADO 2026-11-08).
_TROZO = 2000
_SEC = "/usr/bin/security"
_PREFIJO_SERVICIO = "workspace."
_SECURITY_FW = "/System/Library/Frameworks/Security.framework/Security"
_CF_FW = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
#: SecKeychainGetStatus: kSecUnlockStateStatus.
_ABIERTO = 1
#: Código de salida de `security` cuando el elemento no existe
#: (errSecItemNotFound; VERIFICADO 2026-11-08 con un llavero temporal).
_NO_ESTA = 44


def _trabado():
    """¿El llavero no respondió hace poco? (espera acotada: _ESPERAS_S)."""
    est = _estado()
    t = est.get("trabado")
    try:
        n = max(1, int(est.get("trabado_n") or 1))
        return bool(t) and (time.time() - float(t)) < _ESPERAS_S[min(n, len(_ESPERAS_S)) - 1]
    except (TypeError, ValueError):
        return False


def _correr(argv, entrada=None):
    """(rc, stdout) de un programa del llavero: sin shell; el valor, si va,
    SOLO por la entrada estándar. Tiempo agotado → el llavero descansa un
    rato (_ESPERAS_S, crece si se repite) y NoDisponible; una llamada que
    responde lo destraba."""
    try:
        p = subprocess.run(list(argv), input=entrada,
                           stdin=None if entrada is not None else subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=_TIEMPO)
    except subprocess.TimeoutExpired:
        n = int(_estado().get("trabado_n") or 0) + 1
        _estado_poner(trabado=time.time(), trabado_n=n)
        _TRABA_VISTA[0] = None
        raise NoDisponible("tiempo")
    except OSError as e:
        raise NoDisponible(type(e).__name__)
    if _TRABA_VISTA[0] is not False:
        est = _estado()
        if est.get("trabado"):
            _estado_poner(trabado=None, trabado_n=None)
        _TRABA_VISTA[0] = False
    return p.returncode, p.stdout or b""


#: Ya se miró en este proceso que no hay «trabado» que quitar (para no leer
#: estado.json en cada llamada que responde).
_TRABA_VISTA = [None]


def _cuenta():
    """El usuario de esta cuenta del sistema, solo con caracteres seguros
    para `security -i` (sin comillas ni barras)."""
    u = ""
    try:
        import pwd                          # la cuenta, no $USER (que cambia con sudo/su)
        u = pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        try:
            import getpass
            u = getpass.getuser()
        except Exception:
            u = ""
    u = re.sub(r"[^A-Za-z0-9._-]", "", u or "")
    return u or "workspace"


def _empacar(valor):
    """El valor en base64 con su huella (dentro del llavero, nunca en el
    índice): `ws2:<partes>:<sha16>:<base64>` partido en trozos."""
    b = base64.b64encode(valor.encode("utf-8")).decode("ascii")
    partes = [b[i:i + _TROZO] for i in range(0, len(b), _TROZO)] or [""]
    h = hashlib.sha256(valor.encode("utf-8")).hexdigest()[:16]
    partes[0] = "ws2:%d:%s:%s" % (len(partes), h, partes[0])
    return partes


def _desempacar(partes):
    cab = partes[0].split(":", 3)
    if len(cab) != 4 or cab[0] != "ws2":
        raise NoDisponible("formato")
    valor = base64.b64decode(("".join([cab[3]] + list(partes[1:]))).encode("ascii")).decode("utf-8")
    if hashlib.sha256(valor.encode("utf-8")).hexdigest()[:16] != cab[2]:
        raise NoDisponible("huella")
    return valor


def _gen():
    import secrets as _rnd
    return _rnd.token_hex(4)


def _home_real():
    """¿El HOME de este proceso es el de la cuenta (pwd)? Con un HOME
    prestado (pruebas, una máquina simulada) jamás se toca el llavero REAL
    de la cuenta: sus llaves serían de otra «máquina». Windows: siempre
    (DPAPI guarda el cifrado en el HOME del proceso)."""
    if os.name == "nt":
        return True
    try:
        import pwd
        cuenta = pwd.getpwuid(os.getuid()).pw_dir
        return os.path.realpath(os.path.expanduser("~")) == os.path.realpath(cuenta)
    except Exception:
        return False


class Llavero(object):
    """macOS: el llavero de inicio de sesión (o `ruta`, uno propio: pruebas)
    con /usr/bin/security. Ver la cabecera del módulo."""

    nombre = "llavero"

    def __init__(self, ruta=None):
        self.ruta = ruta or None

    def _kc(self):
        return ' "%s"' % self.ruta if self.ruta else ""

    def disponible(self):
        if not sys.platform == "darwin" or not os.path.exists(_SEC):
            return False
        if self.ruta and ('"' in self.ruta or "\\" in self.ruta or "\n" in self.ruta):
            return False
        if not self.ruta and not _home_real():
            return False                   # HOME prestado: jamás el llavero de la cuenta
        if _trabado():
            return False
        return abierto(self.ruta)

    def _exigir(self):
        if not self.disponible():
            raise NoDisponible("cerrado")

    def _cuentas(self, gen, n):
        return ["%s:%s:%d" % (_cuenta(), gen, i) for i in range(n)]

    def guardar(self, name, valor):
        self._exigir()
        gen, partes = _gen(), _empacar(valor)
        servicio = _PREFIJO_SERVICIO + name
        lineas = "".join('add-generic-password -a "%s" -s "%s" -T "%s" -w "%s"%s\n'
                         % (cta, servicio, _SEC, parte, self._kc())
                         for cta, parte in zip(self._cuentas(gen, len(partes)), partes))
        etiqueta = "v2:llavero:%s:%d" % (gen, len(partes))
        try:
            _correr([_SEC, "-i"], entrada=lineas.encode("ascii"))
            if self.leer(name, etiqueta) != valor:
                raise NoDisponible("verificación")
        except Exception:
            _borrar_etiqueta(name, etiqueta, self)   # si no se puede, queda pendiente
            raise
        return etiqueta

    def _partes(self, etiqueta):
        try:
            _v2, _n, gen, n = etiqueta.split(":")
            return gen, int(n)
        except ValueError:
            raise NoDisponible("etiqueta")

    def leer(self, name, etiqueta):
        gen, n = self._partes(etiqueta)
        self._exigir()
        partes = []
        for cta in self._cuentas(gen, n):
            argv = [_SEC, "find-generic-password", "-a", cta, "-s", _PREFIJO_SERVICIO + name, "-w"]
            if self.ruta:
                argv.append(self.ruta)
            rc, out = _correr(argv)
            if rc != 0:
                raise NoDisponible("rc %d" % rc)
            partes.append(out.decode("ascii", "replace").strip())
        return _desempacar(partes)

    def leer_lote(self, pares):
        """{(NOMBRE, etiqueta): valor} de varias entradas con UN solo `security
        -i` (la bóveda entera en ~20 ms, no un proceso por trozo: los hooks la
        leen para tachar). Si falta alguna (la salida no cuadra), {} y quien
        llama lee una por una. VERIFICADO 2026-11-08: `security -i` sin
        terminal no imprime su «security>»; un elemento que no está no deja
        renglón."""
        self._exigir()
        pedidos = []
        for name, etiqueta in pares:
            gen, n = self._partes(etiqueta)
            for cta in self._cuentas(gen, n):
                pedidos.append((name, etiqueta, cta))
        if not pedidos:
            return {}
        lineas = "".join('find-generic-password -a "%s" -s "%s" -w%s\n'
                         % (cta, _PREFIJO_SERVICIO + name, self._kc()) for name, _e, cta in pedidos)
        _rc, out = _correr([_SEC, "-i"], entrada=lineas.encode("ascii"))
        renglones = out.decode("ascii", "replace").splitlines()
        if len(renglones) != len(pedidos):
            return {}
        partes, res = {}, {}
        for (name, etiqueta, _c), r in zip(pedidos, renglones):
            partes.setdefault((name, etiqueta), []).append(r.strip())
        for k, ps in partes.items():
            try:
                res[k] = _desempacar(ps)
            except Exception:
                return {}
        return res

    def borrar(self, name, etiqueta):
        """→ True solo si los trozos quedaron BORRADOS (o ya no estaban).
        Lo que imprime el borrado NO lo dice: `security` imprime el elemento
        ANTES de intentar borrarlo y «password has been deleted.» pase lo que
        pase (VERIFICADO 2026-11-09 con un llavero temporal de solo lectura:
        -61, rc 195, el elemento sigue ahí). Por eso SIEMPRE se comprueba
        después, trozo por trozo, con `find-generic-password` sin -w/-g (solo
        atributos: no pide el valor ni abre nada): rc 44 = ya no está; si
        sigue, o la respuesta es otra, False. Cerrado o sin respuesta → False:
        quien llama lo deja pendiente (Greptile 0.9.0, 1; revisor, R2)."""
        try:
            gen, n = self._partes(etiqueta)
            if not self.disponible():
                return False
            ctas, servicio = self._cuentas(gen, n), _PREFIJO_SERVICIO + name
            lineas = "".join('delete-generic-password -a "%s" -s "%s"%s\n'
                             % (cta, servicio, self._kc()) for cta in ctas)
            _correr([_SEC, "-i"], entrada=lineas.encode("ascii"))
            for cta in ctas:
                if not self.disponible():
                    return False
                argv = [_SEC, "find-generic-password", "-a", cta, "-s", servicio]
                if self.ruta:
                    argv.append(self.ruta)
                rc, _out = _correr(argv)
                if rc != _NO_ESTA:
                    return False           # sigue ahí (rc 0) o no se pudo saber
            return True
        except Exception:
            return False


_FW = {}


def _framework():
    """Security.framework y CoreFoundation por ctypes (una vez por proceso)."""
    if "sec" not in _FW:
        import ctypes
        sec = ctypes.cdll.LoadLibrary(_SECURITY_FW)
        cf = ctypes.cdll.LoadLibrary(_CF_FW)
        sec.SecKeychainOpen.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        sec.SecKeychainOpen.restype = ctypes.c_int32
        sec.SecKeychainCopyDefault.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        sec.SecKeychainCopyDefault.restype = ctypes.c_int32
        sec.SecKeychainGetStatus.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        sec.SecKeychainGetStatus.restype = ctypes.c_int32
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        _FW.update(sec=sec, cf=cf, ctypes=ctypes)
    return _FW


def abierto(ruta=None):
    """¿El llavero (`ruta` o el de inicio de sesión) está abierto? Solo mira
    su estado (SecKeychainGetStatus): jamás pide nada ni abre un diálogo.
    Falla-suave → False (sin llavero)."""
    try:
        fw = _framework()
        ctypes, sec = fw["ctypes"], fw["sec"]
        ref = ctypes.c_void_p()
        if ruta:
            st = sec.SecKeychainOpen(ruta.encode("utf-8"), ctypes.byref(ref))
        else:
            st = sec.SecKeychainCopyDefault(ctypes.byref(ref))
        if st != 0 or not ref.value:
            return False
        try:
            estado = ctypes.c_uint32(0)
            if sec.SecKeychainGetStatus(ref, ctypes.byref(estado)) != 0:
                return False
            return bool(estado.value & _ABIERTO)
        finally:
            fw["cf"].CFRelease(ref)
    except Exception:
        return False


#: DPAPI: no mostrar nada al usuario (si haría falta, falla).
CRYPTPROTECT_UI_FORBIDDEN = 0x1
#: «Entropía» propia: otro programa que llame a CryptUnprotectData con el
#: blob y sin esto no lo abre (no es un secreto: frena el copiar-pegar).
_ENTROPIA = b"workspace-boveda-v2"


class Dpapi(object):
    """Windows: DPAPI de usuario (crypt32 por ctypes). El cifrado va en el
    índice (`v2:dpapi:<base64>`), que es solo-dueño. `libs` = (crypt32,
    kernel32) — las pruebas pasan un doble."""

    nombre = "dpapi"

    def __init__(self, libs=None):
        self._libs = libs
        self._probado = None

    def libs(self):
        if self._libs is None:
            import ctypes
            self._libs = (ctypes.windll.crypt32, ctypes.windll.kernel32)
        return self._libs

    def disponible(self):
        """¿DPAPI cifra Y descifra en esta sesión? Una prueba de ida y vuelta
        con un valor falso, una vez por proceso (una sesión sin la llave
        maestra del usuario —p. ej. ciertos accesos remotos— cifraría pero no
        descifraría). VERIFICADO 2026-11-08 por `ssh pc-max` (Windows 11,
        llave pública, logon de red con la consola abierta): funciona."""
        if self._libs is None and os.name != "nt":
            return False
        if self._probado is None:
            try:
                self.libs()
                ok = self._llamar(self._llamar(b"workspace-prueba", True), False) == b"workspace-prueba"
            except Exception:
                ok = False
            self._probado = ok
        return self._probado

    def _llamar(self, datos, proteger):
        import ctypes
        crypt32, kernel32 = self.libs()
        entrada_buf = ctypes.create_string_buffer(datos, len(datos))
        entropia_buf = ctypes.create_string_buffer(_ENTROPIA, len(_ENTROPIA))
        entrada = DATA_BLOB(len(datos), ctypes.cast(entrada_buf, ctypes.POINTER(ctypes.c_char)))
        entropia = DATA_BLOB(len(_ENTROPIA), ctypes.cast(entropia_buf, ctypes.POINTER(ctypes.c_char)))
        salida = DATA_BLOB()
        if proteger:
            ok = crypt32.CryptProtectData(ctypes.byref(entrada), ctypes.c_wchar_p("Workspace"),
                                          ctypes.byref(entropia), None, None,
                                          CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(salida))
        else:
            ok = crypt32.CryptUnprotectData(ctypes.byref(entrada), None, ctypes.byref(entropia),
                                            None, None, CRYPTPROTECT_UI_FORBIDDEN,
                                            ctypes.byref(salida))
        if not ok:
            raise NoDisponible("dpapi")
        try:
            return ctypes.string_at(salida.pbData, salida.cbData)
        finally:
            kernel32.LocalFree(salida.pbData)

    def guardar(self, name, valor):
        if not self.disponible():
            raise NoDisponible("dpapi")
        cifrado = self._llamar(valor.encode("utf-8"), True)
        etiqueta = "v2:dpapi:" + base64.b64encode(cifrado).decode("ascii")
        if self.leer(name, etiqueta) != valor:
            raise NoDisponible("verificación")
        return etiqueta

    def leer(self, name, etiqueta):
        if not etiqueta.startswith("v2:dpapi:"):
            raise NoDisponible("etiqueta")
        try:
            blob = base64.b64decode(etiqueta[len("v2:dpapi:"):].encode("ascii"))
        except ValueError:
            raise NoDisponible("etiqueta")
        return self._llamar(blob, False).decode("utf-8")

    def borrar(self, name, etiqueta):
        return True                     # el cifrado vive en el índice: se va con él


def _data_blob():
    import ctypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]
    return _DATA_BLOB


try:
    DATA_BLOB = _data_blob()
except Exception:                         # sin ctypes: no hay DPAPI
    DATA_BLOB = None


class SecretTool(object):
    """Linux: `secret-tool` (libsecret). `cmd` = el programa (las pruebas
    pasan un doble). El valor, por la entrada estándar."""

    nombre = "secret-tool"

    def __init__(self, cmd=None):
        #: un doble de pruebas (no el secret-tool de la cuenta)
        self.doble = cmd is not None
        #: las pruebas dicen si la colección está abierta (si no, D-Bus)
        self.sondeo = None
        if cmd is None:
            import shutil
            exe = shutil.which("secret-tool")
            cmd = [exe] if exe else None
        self.cmd = list(cmd) if cmd else None

    def disponible(self):
        if not self.cmd or _trabado():
            return False
        if not getattr(self, "doble", False) and not _home_real():
            return False                   # HOME prestado: jamás el llavero de la cuenta
        # sin sesión de D-Bus, secret-tool espera hasta el tiempo límite
        if not (os.environ.get("DBUS_SESSION_BUS_ADDRESS")
                or os.path.exists(os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/nonexistent",
                                               "bus"))):
            return False
        return self.coleccion_abierta()

    def coleccion_abierta(self):
        """¿Existe la colección por defecto del Secret Service y está ABIERTA?
        Solo lee su propiedad `Locked` (gdbus o busctl): eso no abre ningún
        diálogo. Bloqueada (GNOME Keyring/KWallet sin desbloquear) o sin
        colección (pediría crear un llavero nuevo) = sin llavero → el archivo
        con aviso; jamás un «Desbloquear llavero» que el socio no pidió. Sin
        gdbus ni busctl, no se puede saber: sin llavero. Caché de 60 s."""
        if self.sondeo is not None:
            return bool(self.sondeo())
        hit = _COLECCION.get("v")
        if hit is not None and time.time() - _COLECCION.get("t", 0) < 60:
            return hit
        import shutil
        ok = False
        objeto = "/org/freedesktop/secrets/aliases/default"
        for argv in (["gdbus", "call", "--session", "--dest", "org.freedesktop.secrets",
                      "--object-path", objeto, "--method", "org.freedesktop.DBus.Properties.Get",
                      "org.freedesktop.Secret.Collection", "Locked"],
                     ["busctl", "--user", "get-property", "org.freedesktop.secrets", objeto,
                      "org.freedesktop.Secret.Collection", "Locked"]):
            exe = shutil.which(argv[0])
            if not exe:
                continue
            try:
                r = subprocess.run([exe] + argv[1:], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
            except Exception:
                break
            txt = (r.stdout or b"").decode("ascii", "replace").lower()
            ok = r.returncode == 0 and "false" in txt and "true" not in txt
            break
        _COLECCION.update(v=ok, t=time.time())
        return ok

    def _attrs(self, name, gen):
        return ["service", _PREFIJO_SERVICIO + name, "account", _cuenta(), "generation", gen]

    def _gen_de(self, etiqueta):
        if not etiqueta.startswith("v2:secret-tool:"):
            raise NoDisponible("etiqueta")
        return etiqueta[len("v2:secret-tool:"):]

    def guardar(self, name, valor):
        if not self.disponible():
            raise NoDisponible("secret-tool")
        gen = _gen()
        etiqueta = "v2:secret-tool:" + gen
        dato = "ws1:" + base64.b64encode(valor.encode("utf-8")).decode("ascii")
        try:
            rc, _out = _correr(self.cmd + ["store", "--label", "Workspace " + name]
                               + self._attrs(name, gen), entrada=dato.encode("ascii"))
            if rc != 0 or self.leer(name, etiqueta) != valor:
                raise NoDisponible("verificación")
        except Exception:
            _borrar_etiqueta(name, etiqueta, self)   # si no se puede, queda pendiente
            raise
        return etiqueta

    def leer(self, name, etiqueta):
        gen = self._gen_de(etiqueta)
        if not self.disponible():
            raise NoDisponible("secret-tool")
        rc, out = _correr(self.cmd + ["lookup"] + self._attrs(name, gen))
        s = out.decode("ascii", "replace").strip()
        if rc != 0 or not s.startswith("ws1:"):
            raise NoDisponible("rc %d" % rc)
        return base64.b64decode(s[4:].encode("ascii")).decode("utf-8")

    def borrar(self, name, etiqueta):
        """→ True si `secret-tool clear` terminó bien (sin coincidencias
        también es 0: ya no estaba). Otro código (colección cerrada, D-Bus) →
        False: quien llama lo deja pendiente (Greptile 0.9.0, 1)."""
        try:
            gen = self._gen_de(etiqueta)
            if not self.disponible():
                return False
            rc, _out = _correr(self.cmd + ["clear"] + self._attrs(name, gen))
            return rc == 0
        except Exception:
            return False


_COLECCION = {}


def _modo():
    return str(os.environ.get(ENV_MODO) or "").strip().lower()


def raiz_instalada():
    """La carpeta de Workspace que abre el comando `workspace` de esta
    cuenta (~/.local/bin/workspace o workspace.cmd), o ''."""
    for n in ("workspace", "workspace.cmd"):
        p = os.path.join(os.path.expanduser("~"), ".local", "bin", n)
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                txt = fh.read(16384)
        except OSError:
            continue
        m = re.search(r'"([^"\r\n]*?)[\\/]front\.py"', txt)
        if m:
            return m.group(1)
    return ""


def _huella_modulo():
    try:
        st = os.stat(os.path.abspath(__file__))
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


#: Cómo estaba este archivo en disco al importarlo: si cambió (se actualizó o
#: se volvió atrás con este proceso abierto), este proceso es VIEJO y no toca
#: el llavero ni migra (p. ej. un hub nuevo que sigue abierto tras
#: `workspace update --rollback` no vuelve a migrar lo que la vuelta atrás
#: devolvió al archivo).
_HUELLA = _huella_modulo()


def codigo_vigente():
    """¿El código de este proceso es el que está en disco ahora?"""
    return _HUELLA is not None and _huella_modulo() == _HUELLA


def misma_carpeta(a, b, rutas=None):
    """¿`a` y `b` son la misma carpeta? Real (enlaces resueltos) y, en
    Windows, sin distinguir `/` de `\\` ni mayúsculas (normcase):
    'C:/x/ws' = 'c:\\X\\WS'. `rutas` = el módulo de rutas (las
    pruebas pasan ntpath para la forma de Windows)."""
    rutas = os.path if rutas is None else rutas
    try:
        return bool(a) and bool(b) and (rutas.normcase(rutas.realpath(a))
                                        == rutas.normcase(rutas.realpath(b)))
    except Exception:
        return False


def instalacion_activa():
    """¿Este código ES la instalación que usa el socio: la carpeta que abre
    su comando `workspace` (raiz_instalada)? Solo ella guarda en el llavero y
    migra. Lo decide SOLO esa comparación: un worktree de desarrollo o una
    copia vieja no son esa carpeta (aunque corran con el HOME real) y no
    mueven las llaves; pero si el comando `workspace` abre un git worktree
    (como en la PC del socio), ese worktree ES la instalación y migra (PC del
    socio, 2026-11-08: la regla «un worktree nunca migra» lo dejaba sin
    llavero). Tampoco un proceso cuyo código ya cambió en disco
    (codigo_vigente). Forzar un llavero (WORKSPACE_BOVEDA=llavero|dpapi|
    secret-tool) es de pruebas: cuenta como activa."""
    if _modo() in ("llavero", "dpapi", "secret-tool"):
        return True
    if not codigo_vigente():
        return False                       # proceso viejo: el código en disco ya es otro
    try:
        return misma_carpeta(raiz_instalada(), os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        return False


#: El ajuste (Config → otros) que elige dónde se guardan las llaves:
#:   auto    el llavero del sistema si está; si no, el archivo 0600 CON un
#:           aviso de una línea (nunca en silencio);
#:   keyring solo el llavero: sin él, guardar una llave FALLA (nada en texto
#:           plano);
#:   file    el archivo 0600 de siempre (lo que haya en el llavero vuelve al
#:           archivo al arrancar).
SETTING = "otros.boveda"
MODOS = ("auto", "keyring", "file")


def modo_guardado():
    """"auto" | "keyring" | "file". WORKSPACE_BOVEDA gana (`archivo` = file;
    `llavero`/`dpapi`/`secret-tool` = keyring); deshacer la migración = file."""
    m = _modo()
    if m == "archivo":
        return "file"
    if m in ("llavero", "dpapi", "secret-tool"):
        return "keyring"
    if _estado().get("desactivado"):
        return "file"
    try:
        import settings
        v = settings.get(SETTING)
    except Exception:
        v = "auto"
    return v if v in MODOS else "auto"


def _desactivado():
    """¿Va todo al archivo? (modo «file», la migración deshecha o una vuelta
    atrás en curso)."""
    return modo_guardado() == "file" or _volviendo()


#: `workspace update --rollback` en curso (updater.rollback): desde ANTES de
#: deshacer lo que la versión anterior no conoce hasta cambiar el código, nada
#: vuelve a migrar (ni la bóveda ni la contraseña del correo) ni se escribe en
#: el llavero: la versión anterior solo lee `secrets.local` y mail.json, y otro
#: hub que arrancara (o guardara una llave) en medio la dejaría sin llaves.
#: Caduca sola a los VUELTA_S: una vuelta atrás cortada no deja el llavero
#: apagado para siempre (Greptile 0.9.0, 2).
VUELTA_S = 1800


def _ruta_vuelta():
    """La barrera es un archivo PROPIO en el dir de estado: fuera de boveda/
    (volver atrás no le crea una bóveda a quien no tiene) y fuera de
    estado.json (si ese está ilegible, la vuelta atrás no se traba) —
    revisor, R4."""
    return os.path.join(_workspace_dir(), "boveda-volviendo.json")


def empezar_vuelta():
    """(updater.rollback, antes de deshacer) Pone la barrera. Levanta si no
    pudo anotarla: sin barrera no se vuelve."""
    _escribir_privado(_ruta_vuelta(), json.dumps({"t": time.time(), "pid": os.getpid()}))


def terminar_vuelta(intentos=5):
    """(updater.rollback, tras cambiar el código o no poder) Quita la barrera,
    con reintentos cortos: en Windows otro proceso puede tenerla abierta un
    instante (al leerla) y, sin reintento, la barrera duraba hasta caducar
    (revisor, R3). → True si ya no está."""
    for k in range(max(1, int(intentos))):
        try:
            os.remove(_ruta_vuelta())
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if k < intentos - 1:
                time.sleep(0.1 * (k + 1))
    return False


def aviso_vuelta():
    """La línea de «se está deshaciendo una actualización»: lo que se dice
    mientras dura la barrera, en vez de «sin llavero» (revisor, R3)."""
    return _t("boveda.aviso.volviendo",
              "⚠ Se está deshaciendo una actualización de Workspace: tu llave quedó en un "
              "archivo que solo tú puedes leer; reintenta en un momento para guardarla en el "
              "llavero.",
              "⚠ A Workspace update is being undone: your key was saved to a file only you can "
              "read; try again in a moment to store it in the keychain.")


def _volviendo():
    """¿Hay una vuelta atrás en curso (y no caducó)? Una barrera ilegible
    sigue contando, por su fecha."""
    p = _ruta_vuelta()
    try:
        with open(p, encoding="utf-8") as fh:
            t = float((json.load(fh) or {}).get("t") or 0)
    except FileNotFoundError:
        return False
    except Exception:
        try:
            t = os.path.getmtime(p)
        except OSError:
            return False
    return bool(t) and abs(time.time() - t) < VUELTA_S


def _fabrica(nombre):
    if nombre == "llavero":
        return Llavero(os.environ.get(ENV_LLAVERO) or None)
    if nombre == "dpapi":
        return Dpapi()
    if nombre == "secret-tool":
        return SecretTool()
    return None


def _backend():
    """El llavero de este sistema para ESCRIBIR, o None (el archivo):
    `WORKSPACE_BOVEDA=archivo`, la migración deshecha o un sistema sin uno."""
    modo = _modo()
    if modo == "archivo":
        return None
    if modo in ("llavero", "dpapi", "secret-tool"):
        return _fabrica(modo)
    if _desactivado():                     # modo «file» (o la migración deshecha)
        return None
    if not instalacion_activa():           # un worktree / una copia que no es la instalada
        return None
    if sys.platform == "darwin":
        return _fabrica("llavero")
    if os.name == "nt":
        return _fabrica("dpapi")
    if sys.platform.startswith("linux"):
        b = _fabrica("secret-tool")
        return b if b.cmd else None
    return None


def _backend_de(etiqueta):
    """El llavero que LEE una etiqueta del índice (aunque la migración se
    haya deshecho), o None con `WORKSPACE_BOVEDA=archivo`."""
    if _modo() == "archivo":
        return None
    for nombre in ("llavero", "dpapi", "secret-tool"):
        if etiqueta.startswith("v2:%s:" % nombre):
            return _fabrica(nombre)
    return None


def sistema():
    """Dónde guarda Workspace las llaves AHORA en esta máquina: "llavero"
    (macOS) | "dpapi" (Windows) | "secret-tool" (Linux) | "archivo"."""
    b = _backend()
    try:
        return b.nombre if b is not None and b.disponible() else "archivo"
    except Exception:
        return "archivo"


# ── leer ────────────────────────────────────────────────────────────────────
#: (NOMBRE, etiqueta) → valor, en memoria del proceso: la etiqueta cambia con
#: cada escritura (otra gen / otro cifrado), así que nunca queda vieja.
_VALORES = {}


def _resolver(name, etiqueta, cache=True):
    """El valor de una entrada del índice. Levanta NoDisponible."""
    clave = (name, etiqueta)
    if cache and clave in _VALORES:
        return _VALORES[clave]
    b = _backend_de(etiqueta)
    if b is None:
        raise NoDisponible("sin llavero")
    v = b.leer(name, etiqueta)
    if len(_VALORES) > 256:
        _VALORES.clear()
    _VALORES[clave] = v
    return v


def _ilegible(name):
    """Una llave del índice que el llavero no entregó: nunca en silencio. Se
    anota (a lo más una vez por hora) para el aviso de una línea
    (aviso_pendiente) y `workspace llaves` la marca «ilegible»."""
    try:
        t = _estado().get("ilegible")
        if not t or time.time() - float(t) > 3600:
            _estado_poner(ilegible=time.time())
    except Exception:
        pass


def _valor(name, plano=None, indice=None):
    plano = _leer_plano() if plano is None else plano
    if name in plano:
        return plano[name]
    indice = _leer_indice() if indice is None else indice
    if name not in indice:
        return ""
    try:
        return _resolver(name, indice[name])
    except Exception:
        _ilegible(name)
        return ""


def _read_raw():
    """{NOMBRE: valor} de TODA la bóveda (lo del archivo gana al índice). Lo
    que el llavero no entrega ahora (cerrado) no aparece (y queda anotado:
    _ilegible). Del llavero de macOS se lee en lote (un solo proceso).
    Falla-suave → {}."""
    try:
        plano, indice = _leer_plano(), _leer_indice()
    except Exception:
        return {}
    out = {}
    faltan = [(n, e) for n, e in indice.items()
              if n not in plano and (n, e) not in _VALORES]
    lote = [(n, e) for n, e in faltan if e.startswith("v2:llavero:")]
    if len(lote) > 1:
        try:
            b = _backend_de(lote[0][1])
            if b is not None and hasattr(b, "leer_lote"):
                for k, v in b.leer_lote(lote).items():
                    _VALORES[k] = v
        except Exception:
            pass
    for name, etiqueta in indice.items():
        if name in plano:
            continue
        try:
            out[name] = _resolver(name, etiqueta)
        except Exception:
            _ilegible(name)
            continue
    out.update(plano)
    return out


# ── API pública ─────────────────────────────────────────────────────────────
def names():
    """NOMBRES guardados (ordenados). JAMÁS devuelve valores."""
    return sorted(set(_leer_indice()) | set(_leer_plano()))


def has(name):
    """True si el store TIENE ese secreto (no dice nada del valor)."""
    return name in _leer_plano() or name in _leer_indice()


def get(name):
    """Valor guardado o "" — uso interno / loader. No lo loguees."""
    return _valor(name)


def set_secret(name, value, _y_luego=None):
    """Guarda/actualiza un secreto. Devuelve {"ok":True,"name":name,
    "donde":"llavero|dpapi|secret-tool|archivo"} o {"ok":False,"error":...}.
    Valida el NOMBRE (env-var mayúsculas) y que el valor no sea vacío. El
    valor jamás aparece en el resultado. Con un llavero que funciona, lo que
    quede en texto plano se migra en la misma pasada; sin él (o si falla),
    va al archivo, como siempre. `_y_luego()` corre bajo el MISMO candado,
    tras guardar (el correo: mail.json junto con su contraseña, sin que
    migrar_correo se meta en medio); si falla, el secreto vuelve a como
    estaba y se devuelve "despues": True (no es una falla del store).
    Candado ocupado ≠ sin llavero: "ocupado": True y no se guarda nada."""
    if not valid_name(name):
        return {"ok": False, "error": "nombre de env-var inválido: %r "
                "(esperado ^[A-Z][A-Z0-9_]*$)" % name}
    if not isinstance(value, str) or not value.strip():
        return {"ok": False, "error": "valor vacío — no se guarda"}
    value = value.strip()
    try:                                     # tomar el candado: cualquier fallo es «ocupado»
        cand = _locked()                     # (LockTimeout, o PermissionError al abrir el
        cand.__enter__()                     # .lock en Windows), nunca «no hay llavero»
    except Exception:
        return {"ok": False, "ocupado": True, "error": "la bóveda está ocupada"}
    try:
        with _ya_tomado(cand):
            tenia = antes = None
            if _y_luego is not None:         # para volver a como estaba si _y_luego falla
                try:
                    plano, indice = _leer_plano(estricto=True), _leer_indice(estricto=True)
                    tenia = name in plano or name in indice
                    antes = _valor(name, plano, indice) if tenia else ""
                except Exception:
                    tenia = None
            donde = _guardar_bajo_candado(name, value)
            if _y_luego is not None:
                try:
                    _y_luego()
                except Exception as e:
                    revertido = False
                    try:
                        if tenia and antes:
                            _guardar_bajo_candado(name, antes)
                            revertido = True
                        elif tenia is False:
                            _quitar_bajo_candado(name)
                            revertido = True
                    except Exception:
                        pass
                    _VALORES.clear()
                    return {"ok": False, "despues": True, "revertido": revertido,
                            "error": "%s: %s" % (type(e).__name__, e)}
    except SinLlavero:
        if _volviendo():                   # no es que falte el llavero: se está volviendo atrás
            return {"ok": False, "error": _t(
                "boveda.err.volviendo", "Se está deshaciendo una actualización de Workspace; "
                "reintenta en un momento (no guardé nada)",
                "A Workspace update is being undone; try again in a moment (nothing was saved)")}
        return {"ok": False, "error": "sin llavero del sistema: con «%s = keyring» no se "
                "guarda en un archivo" % SETTING}
    except Exception as e:
        if isinstance(e, TimeoutError):      # olock.LockTimeout: ocupado, no «sin llavero»
            return {"ok": False, "ocupado": True, "error": "la bóveda está ocupada"}
        return {"ok": False, "error": "no pude escribir el store (%s: %s)"
                % (type(e).__name__, e)}
    out = {"ok": True, "name": name, "donde": donde}
    if donde == "archivo" and _volviendo():
        out["aviso"] = aviso_vuelta()       # no es «sin llavero»: se está volviendo atrás
    elif donde == "archivo" and modo_guardado() == "auto" and _backend_esperado():
        out["aviso"] = aviso_sin_llavero()  # en auto, el archivo NUNCA en silencio
    return out


class SinLlavero(Exception):
    """Modo «keyring» sin un llavero que funcione: no se guarda nada."""


class _ya_tomado(object):
    """`with` sobre un candado YA tomado: solo lo suelta al salir."""

    def __init__(self, cand):
        self.cand = cand

    def __enter__(self):
        return self.cand

    def __exit__(self, *exc):
        return self.cand.__exit__(*exc)


def _guardar_bajo_candado(name, value):
    b = _backend()
    if b is not None:
        try:
            if b.disponible():
                if _leer_plano():
                    _migrar_bajo_candado(b)
                indice = _leer_indice(estricto=True)    # antes de escribir nada
                plano = _leer_plano(estricto=True)
                etiqueta = b.guardar(name, value)
                try:
                    viejo = indice.get(name)
                    indice[name] = etiqueta
                    _escribir_indice(indice)
                except BaseException:
                    _borrar_etiqueta(name, etiqueta, b)  # si no se puede, queda pendiente
                    raise
                if name in plano:
                    plano.pop(name)
                    _write_raw(plano)
                if viejo and viejo != etiqueta:
                    _borrar_etiqueta(name, viejo)
                _purgar_copias(name)
                _limpiar_pendientes()
                return b.nombre
        except OSError:
            raise
        except Exception:
            pass                           # el llavero falló: el archivo, como siempre
    if modo_guardado() == "keyring":
        raise SinLlavero()
    plano = _leer_plano(estricto=True)
    plano[name] = value
    _write_raw(plano)
    _purgar_copias(name)
    return "archivo"


def _backend_esperado():
    """¿Este sistema tiene (o podría tener) un llavero? macOS, Windows y
    Linux (secret-tool): sin él en «auto», el archivo va con aviso."""
    return sys.platform == "darwin" or os.name == "nt" or sys.platform.startswith("linux")


def aviso_sin_llavero():
    """La línea de «sin llavero: va al archivo», por sistema."""
    if sys.platform == "darwin":
        return _t("boveda.aviso.sin_llavero_mac",
                  "⚠ El llavero de macOS no está abierto ahora (¿una sesión por SSH?): tu llave quedó "
                  "en un archivo que solo tú puedes leer y pasará sola al llavero.",
                  "⚠ The macOS Keychain is not open right now (an SSH session?): your key was saved "
                  "to a file only you can read and will move to the Keychain on its own.")
    if os.name == "nt":
        return _t("boveda.aviso.sin_llavero_win",
                  "⚠ Windows no pudo cifrar tu llave (DPAPI): quedó en un archivo que solo tu "
                  "usuario puede leer.",
                  "⚠ Windows could not encrypt your key (DPAPI): it was saved to a file only your "
                  "user can read.")
    return _t("boveda.aviso.linux",
              "⚠ Tus llaves de Workspace siguen en un archivo que solo tú puedes leer; con "
              "secret-tool (libsecret) y tu sesión abierta pasan solas a tu llavero.",
              "⚠ Your Workspace keys are still in a file only you can read; with "
              "secret-tool (libsecret) and your session open they move to your keyring.")


def _borrar_etiqueta(name, etiqueta, b=None):
    """Borra del llavero lo de una etiqueta vieja; si ahora no se puede,
    queda anotado para la próxima (nunca un elemento huérfano a propósito).
    `b`: el llavero que lo acaba de escribir (las limpiezas tras un fallo:
    verificar al guardar, escribir el índice, deshacer una migración —
    Greptile 0.9.0, 1b); si no, el de la etiqueta."""
    b = b if b is not None else _backend_de(etiqueta)
    if b is not None and b.borrar(name, etiqueta):
        return True
    pend = [p for p in (_estado().get("por_borrar") or []) if isinstance(p, list)]
    if [name, etiqueta] not in pend:
        _estado_poner(por_borrar=pend + [[name, etiqueta]])
    return False


def _limpiar_pendientes():
    pend = [p for p in (_estado().get("por_borrar") or []) if isinstance(p, list) and len(p) == 2]
    if not pend:
        return
    quedan = []
    for name, etiqueta in pend:
        b = _backend_de(str(etiqueta))
        if b is None or not b.borrar(str(name), str(etiqueta)):
            quedan.append([name, etiqueta])
    _estado_poner(por_borrar=quedan or None)


#: Al arrancar, lo pendiente de borrar se reintenta en un hilo de FONDO: espera
#: esto (la pantalla ya se pintó), tiene este tope TOTAL y jamás abre un
#: diálogo (un llavero cerrado ni se intenta). Antes corría en front.main
#: antes de la interfaz y cada pendiente podía tardar 10 s (revisor, R5).
_PENDIENTES_ESPERA_S = 1.0
_PENDIENTES_TOPE_S = 20.0
#: El hilo de la última vez (las pruebas lo esperan).
_PENDIENTES_HILO = [None]


def _reintentar_pendientes():
    """(al arrancar) Lo que un borrado no pudo quitar del llavero se reintenta
    aunque no se vuelva a guardar ninguna llave, en un hilo de fondo. Jamás
    levanta ni espera."""
    try:
        if not [p for p in (_estado().get("por_borrar") or []) if isinstance(p, list)]:
            return None
        h = threading.Thread(target=_pendientes_de_fondo, daemon=True, name="boveda-pendientes")
        _PENDIENTES_HILO[0] = h
        h.start()
        return h
    except Exception:
        return None


def _pendientes_de_fondo():
    """El trabajo del hilo: borra lo pendiente SIN el candado de la bóveda
    (una llamada lenta no frena a quien guarda una llave), hasta el tope
    total; un llavero cerrado no se intenta (sin diálogo). Al final quita,
    bajo el candado y sobre la lista de AHORA, solo lo que sí se borró."""
    try:
        if _PENDIENTES_ESPERA_S:
            time.sleep(_PENDIENTES_ESPERA_S)
        pend = [p for p in (_estado().get("por_borrar") or []) if isinstance(p, list) and len(p) == 2]
        fin = time.monotonic() + _PENDIENTES_TOPE_S
        hechos = []
        for name, etiqueta in pend:
            if time.monotonic() >= fin:
                break
            b = _backend_de(str(etiqueta))
            if b is None or not b.disponible():
                continue
            if b.borrar(str(name), str(etiqueta)):
                hechos.append([name, etiqueta])
        if hechos:
            with _locked(timeout=2):
                ahora = [p for p in (_estado().get("por_borrar") or []) if isinstance(p, list)]
                _estado_poner(por_borrar=[p for p in ahora if p not in hechos] or None)
    except Exception:
        pass


def _quitar_bajo_candado(name):
    plano, indice = _leer_plano(estricto=True), _leer_indice(estricto=True)
    removed = name in plano or name in indice
    if name in plano:
        plano.pop(name, None)
        _write_raw(plano)
    if name in indice:
        etiqueta = indice.pop(name)
        _escribir_indice(indice)
        _borrar_etiqueta(name, etiqueta)
        if not indice and not plano and not sellado():
            _write_raw({})
    _purgar_copias(name)                   # desconectar = sin copias viejas en respaldos
    return removed


def remove(name):
    """Borra un secreto del store (archivo, índice y llavero).
    {"ok":True,"name":name,"removed":bool}."""
    try:
        with _locked():
            removed = _quitar_bajo_candado(name)
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
        plano, indice = _leer_plano(), _leer_indice()
    except Exception:
        return loaded
    for name in sorted(set(plano) | set(indice)):
        if name not in PROVIDER_KEYS:
            continue                       # interna: jamás al entorno
        if not overwrite and os.environ.get(name):
            continue
        val = _valor(name, plano, indice)
        if not val:
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


def firma():
    """Lo que cambia cuando cambia algo de la bóveda (para cachés de quien
    la usa, p. ej. decisions.redact): los dos archivos y el modo."""
    out = []
    for p in (store_path(), os.path.join(boveda_dir(), "plano.local"), indice_path()):
        try:
            st = os.stat(p)
            out.append((p, st.st_size, st.st_mtime_ns, getattr(st, "st_ino", 0)))
        except OSError:
            out.append((p, None, None, None))
    return tuple(out) + (_modo(),)


_TEXTOS = {"firma": None, "textos": ()}


def textos_guardados():
    """Los textos de la bóveda (≥ 8 caracteres, del más largo al más corto),
    cacheados por firma(). Jamás se devuelven a nadie fuera de Workspace:
    solo para TACHARLOS de lo que se imprime o se manda. Falla-suave → ()."""
    try:
        f = firma()
        if _TEXTOS["firma"] != f:
            plano, indice = _leer_plano(), _leer_indice()
            data = _read_raw()
            completos = all(n in data for n in set(plano) | set(indice))
            textos = tuple(sorted((v for v in _stored_texts(data) if len(v) >= _TACHAR_MIN),
                                  key=len, reverse=True))
            if not completos:              # el llavero cerrado: reintentar la próxima
                return textos
            _TEXTOS.update(firma=f, textos=textos)
        return _TEXTOS["textos"]
    except Exception:
        return ()


def sin_valores(obj, textos=None):
    """`obj` (texto, o listas/dicts de textos) con cada valor de la bóveda
    cambiado por `[secret:stored]`. Para TODO lo que Workspace imprime o
    anota (la CLI, el Historial, «d detalle», mensajes). Falla-suave: si no
    puede leer la bóveda, devuelve `obj` tal cual."""
    textos = textos_guardados() if textos is None else textos
    if not textos:
        return obj
    if isinstance(obj, str):
        for v in textos:
            if v in obj:
                obj = obj.replace(v, TACHADO)
        return obj
    if isinstance(obj, dict):
        return {sin_valores(k, textos): sin_valores(v, textos) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sin_valores(v, textos) for v in obj]
    if isinstance(obj, tuple):
        return tuple(sin_valores(v, textos) for v in obj)
    return obj


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
    guardados = names()
    stored = None
    gone = []
    for name in sorted(set(guardados) | INTERNAL_NAMES | ENV_OVERRIDES):
        if name in PROVIDER_KEYS or name not in env:
            continue
        if name in ENV_OVERRIDES or es_llave_de_decisor(name):
            if stored is None:
                stored = _stored_texts(_read_raw())
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
    valor se respeta, salvo las variables exclusivas de Workspace
    (SOLO_WORKSPACE, WORKSPACE_DECIDER_*_KEY), que salen siempre. Solo lee del llavero los valores cuyo NOMBRE está en
    `env`. Devuelve los NOMBRES quitados (ordenados)."""
    gone = set()
    for name in [n for n in env if es_solo_workspace(n)]:
        env.pop(name, None)                # exclusivas de Workspace: SIEMPRE fuera
        gone.add(name)
    for name in loaded_names(env):
        if name in env:
            env.pop(name, None)
            gone.add(name)
    env.pop(LOADED_ENV, None)
    gone.update(scrub_env(env))
    plano, indice = _leer_plano(), _leer_indice()
    for name in sorted(set(plano) | set(indice)):
        cur = env.get(name)
        if cur is None:
            continue
        val = _valor(name, plano, indice)
        if val.strip() and cur.strip() == val.strip():
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


# ── migración al llavero, respaldo y deshacer ──────────────────────────────
def migracion_pendiente():
    """¿Hay valores en texto plano y un llavero que funciona? (barato: lee
    el archivo y mira el estado del llavero, sin llamar a nadie)."""
    try:
        if not _leer_plano():
            return False
        b = _backend()
        return bool(b is not None and b.disponible())
    except Exception:
        return False


def migrar(timeout=2):
    """Mueve los valores en texto plano al llavero (ver la cabecera). →
    {"estado": "hecho"|"nada"|"sin_llavero"|"ocupado"|"fallo", "n": int,
    "donde": str}. Jamás levanta; si falla, todo queda como estaba."""
    try:
        if not _leer_plano():
            return {"estado": "nada", "n": 0, "donde": sistema()}
        b = _backend()
        if b is None or not b.disponible():
            return {"estado": "sin_llavero", "n": 0, "donde": "archivo"}
        with _locked(timeout=timeout):
            return _migrar_bajo_candado(b)
    except Exception as e:
        if type(e).__name__ == "LockTimeout":
            return {"estado": "ocupado", "n": 0, "donde": "archivo"}
        return {"estado": "fallo", "n": 0, "donde": "archivo", "error": type(e).__name__}


def _respaldar(b, contenido, sello=None):
    """Respaldo del texto plano ANTES de migrar: cifrado con el mismo llavero
    (macOS/Linux: un elemento más; Windows: el blob de DPAPI en boveda/) o,
    si no se puede, 0600 en boveda/ (nunca en el cerebro; se borra en cuanto
    la migración queda verificada). → su registro (con la fecha: caduca)."""
    sello = sello or time.strftime("%Y%m%d%H%M%S")
    nombre = "RESPALDO_%s_%s" % (sello, _gen())
    try:
        if b is None:
            raise NoDisponible("sin llavero")
        etiqueta = b.guardar(nombre, contenido)
        if b.nombre == "dpapi":
            ruta = os.path.join(boveda_dir(), "respaldo-%s-%s.dpapi" % (sello, _gen()))
            _escribir_privado(ruta, etiqueta + "\n")
            return {"donde": "dpapi", "ruta": ruta, "fecha": sello, "creado": time.time()}
        return {"donde": b.nombre, "nombre": nombre, "etiqueta": etiqueta, "fecha": sello,
                "creado": time.time()}
    except Exception:
        ruta = os.path.join(boveda_dir(), "respaldo-%s-%s.local" % (sello, _gen()))
        _escribir_privado(ruta, contenido)
        return {"donde": "archivo", "ruta": ruta, "fecha": sello, "creado": time.time()}


def _texto_respaldo(reg):
    """El texto de un respaldo, o None si no se puede leer."""
    try:
        donde = reg.get("donde")
        if donde == "archivo":
            with open(reg["ruta"], encoding="utf-8") as fh:
                return fh.read()
        if donde == "dpapi":
            with open(reg["ruta"], encoding="utf-8") as fh:
                etiqueta = fh.read().strip()
            return _resolver("RESPALDO", etiqueta, cache=False)
        return _resolver(reg["nombre"], reg["etiqueta"], cache=False)
    except Exception:
        return None


def _leer_respaldo(reg):
    """{NOMBRE: valor} de un registro de respaldo. Falla-suave → {}."""
    texto = _texto_respaldo(reg)
    out = {}
    for line in (texto or "").splitlines():
        if line.strip().startswith("#") or "=" not in line:
            continue
        n, v = line.split("=", 1)
        if valid_name(n.strip()):
            out[n.strip()] = v
    return out


def _quitar_respaldo(reg):
    try:
        if reg.get("donde") in ("archivo", "dpapi"):
            os.remove(reg["ruta"])
        else:
            _borrar_etiqueta(reg["nombre"], reg["etiqueta"])
    except Exception:
        pass


def _purgar_copias(name):
    """(bajo el candado) Las copias viejas de `name` fuera de su lugar se van:
    las ARCHIVADAS de ese nombre y su renglón en cada RESPALDO (el respaldo
    se reescribe cifrado sin él, o se borra si queda vacío; si no se puede
    reescribir cifrado, se queda como estaba). Así «desconectar» (o cambiarla:
    p. ej. quitar una cuenta de Google, que reescribe sus tokens) no deja la
    llave vieja viva en el llavero. Falla-suave."""
    try:
        est = _estado()
        arch = [a for a in (est.get("archivadas") or []) if isinstance(a, dict)]
        quedan = [a for a in arch if a.get("nombre") != name
                  or not _borrar_etiqueta(name, str(a.get("etiqueta") or ""))]
        if len(quedan) != len(arch):
            _estado_poner(archivadas=quedan or None)
        resp = [r for r in (est.get("respaldos") or []) if isinstance(r, dict)]
        nuevos, cambio = [], False
        for reg in resp:
            texto = _texto_respaldo(reg)
            lineas = (texto or "").splitlines()
            if texto is None or not any("=" in ln and ln.split("=", 1)[0].strip() == name
                                        for ln in lineas):
                nuevos.append(reg)
                continue
            resto = [ln for ln in lineas if not ("=" in ln and ln.split("=", 1)[0].strip() == name)]
            if any("=" in ln and not ln.lstrip().startswith("#") for ln in resto):
                b = _fabrica(reg.get("donde")) if reg.get("donde") != "archivo" else None
                try:
                    nuevo = _respaldar(b, "\n".join(resto) + "\n", sello=reg.get("fecha"))
                except Exception:
                    nuevo = None
                if nuevo is None or (nuevo.get("donde") == "archivo") != (reg.get("donde") == "archivo"):
                    if nuevo is not None:
                        _quitar_respaldo(nuevo)
                    nuevos.append(reg)     # no se pudo reescribir igual de protegido
                    continue
                nuevo["creado"] = reg.get("creado") or time.time()
                nuevos.append(nuevo)
            _quitar_respaldo(reg)
            cambio = True
        if cambio:
            _estado_poner(respaldos=nuevos or None)
    except Exception:
        pass


#: Los respaldos cifrados de la migración caducan a los N días, si en un
#: arranque posterior todas las llaves se leen bien del llavero (la migración
#: quedó confirmada); las llaves archivadas, a los 30. El respaldo en TEXTO
#: PLANO (si el llavero no lo aceptó) se borra en cuanto la migración se
#: verifica.
RESPALDO_DIAS = 7
ARCHIVADA_DIAS = 30


def _podar():
    """(al arrancar, instalación activa) Caducidad de respaldos y archivadas
    (también el respaldo de mail.json, si la contraseña se lee bien). Bajo el
    candado de la bóveda, como toda escritura de esas listas: leerlas fuera y
    reemplazarlas después perdía un respaldo registrado en medio (Greptile
    0.9.0, 3). Ocupada (otro proceso migra o escribe): se poda en otro
    arranque."""
    try:
        with _locked(timeout=0.5):
            _podar_bajo_candado()
    except Exception:
        pass


def _podar_bajo_candado():
    try:
        est = _estado()
        rc = est.get("correo_respaldo")
        if isinstance(rc, dict) and time.time() - float(rc.get("creado") or 0) > RESPALDO_DIAS * 86400 \
                and get(CORREO_PASS):
            _quitar_respaldo(rc)
            _estado_poner(correo_respaldo=None)
        resp = [r for r in (est.get("respaldos") or []) if isinstance(r, dict)]
        arch = [a for a in (est.get("archivadas") or []) if isinstance(a, dict)]
        if not resp and not arch:
            return
        ahora = time.time()
        viejos = [r for r in resp if ahora - float(r.get("creado") or 0) > RESPALDO_DIAS * 86400]
        if viejos:
            plano, indice = _leer_plano(), _leer_indice()
            confirmada = all(_valor(n, plano, indice) for n in indice)
            if confirmada:
                for r in viejos:
                    _quitar_respaldo(r)
                _estado_poner(respaldos=[r for r in resp if r not in viejos] or None)
        vencidas = [a for a in arch if ahora - _epoch(a.get("fecha")) > ARCHIVADA_DIAS * 86400]
        if vencidas:
            quedan = [a for a in arch if a not in vencidas
                      or not _borrar_etiqueta(str(a.get("nombre") or ""), str(a.get("etiqueta") or ""))]
            _estado_poner(archivadas=quedan or None)
    except Exception:
        pass


def _epoch(fecha):
    try:
        return time.mktime(time.strptime(str(fecha), "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return time.time()


def _migrar_bajo_candado(b):
    if _volviendo():                       # `update --rollback` en curso: no se migra
        return {"estado": "ocupado", "n": 0, "donde": "archivo"}
    try:
        plano = _leer_plano(estricto=True)
        viejo = _leer_indice(estricto=True)
    except LecturaFallida as e:
        return {"estado": "fallo", "n": 0, "donde": "archivo", "error": "lectura: %s" % e}
    if not plano:
        return {"estado": "nada", "n": 0, "donde": b.nombre}
    origen = _ruta_plano()
    try:
        with open(origen, encoding="utf-8") as fh:
            contenido = fh.read()
    except OSError:
        return {"estado": "fallo", "n": 0, "donde": "archivo", "error": "lectura"}
    try:
        respaldo = _respaldar(b, contenido)
    except Exception as e:
        return {"estado": "fallo", "n": 0, "donde": "archivo", "error": type(e).__name__}
    nuevos = {}
    escrito = False
    try:
        for name in sorted(plano):
            nuevos[name] = b.guardar(name, plano[name])
        indice = dict(viejo)
        indice.update(nuevos)
        _escribir_indice(indice)
        escrito = True
        # verificar por el MISMO camino de lectura, sin caché
        for name, val in plano.items():
            if _resolver(name, indice[name], cache=False) != val:
                raise NoDisponible("verificación")
        # anotar el respaldo ANTES de vaciar el texto plano: si no se puede,
        # no se migra (un respaldo sin registro no lo encontraría nadie)
        respaldos = [r for r in (_estado().get("respaldos") or []) if isinstance(r, dict)]
        if respaldo.get("donde") != "archivo":
            respaldos.append(respaldo)
        _estado_poner(_estricto=True, version=2, donde=b.nombre,
                      migrado=time.strftime("%Y-%m-%dT%H:%M:%S"),
                      respaldos=respaldos or None, aviso="pendiente", trabado=None)
    except Exception as e:
        if escrito:
            try:
                _escribir_indice(viejo)
            except Exception:
                pass
        for name, etiqueta in nuevos.items():
            _borrar_etiqueta(name, etiqueta, b)  # si no se puede, queda pendiente
        _quitar_respaldo(respaldo)          # nada cambió: el respaldo sobra
        return {"estado": "fallo", "n": 0, "donde": "archivo", "error": type(e).__name__}
    # solo ahora, el texto plano sin valores: `secrets.local` queda SELLADO
    # (ver _SELLO); si ya lo estaba, se quita boveda/plano.local
    if origen == store_path():
        _sellar()
    else:
        _write_raw({})
    if respaldo.get("donde") == "archivo":
        _quitar_respaldo(respaldo)          # verificada: el texto plano no se queda
    # Lo que el índice ya tenía con el mismo nombre NO se borra si era otra
    # llave (o no se puede leer): se ARCHIVA con fecha. El valor que se usa
    # no cambia (el del archivo ya ganaba); la otra queda, cifrada, por si
    # era la buena. Nunca se pierde una credencial que funcionaba.
    archivadas = [a for a in (_estado().get("archivadas") or []) if isinstance(a, dict)]
    n_arch = len(archivadas)
    for name, etiqueta in nuevos.items():
        antes = viejo.get(name)
        if not antes or antes == etiqueta:
            continue
        try:
            igual = _resolver(name, antes, cache=False) == plano[name]
        except Exception:
            igual = False
        if igual:
            _borrar_etiqueta(name, antes)
        else:
            archivadas.append({"nombre": name, "etiqueta": antes,
                               "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")})
    if len(archivadas) != n_arch:
        _estado_poner(archivadas=archivadas)
    return {"estado": "hecho", "n": len(nuevos), "donde": b.nombre}


def _al_archivo():
    """(bajo el candado) TODO al archivo de texto plano de siempre
    (`secrets.local`): cada valor del llavero o, si no se puede, del
    respaldo; si falta alguno, no cambia nada. Después quita el sello y lo de
    Workspace del llavero."""
    plano, indice = _leer_plano(estricto=True), _leer_indice(estricto=True)
    valores, faltan = {}, []
    for name, etiqueta in indice.items():
        if name in plano:
            continue
        try:
            valores[name] = _resolver(name, etiqueta, cache=False)
        except Exception:
            faltan.append(name)
    if faltan:
        for reg in reversed([r for r in (_estado().get("respaldos") or [])
                             if isinstance(r, dict)]):
            resp = _leer_respaldo(reg)
            for name in list(faltan):
                if name in resp:
                    valores[name] = resp[name]
                    faltan.remove(name)
    if faltan:
        return {"ok": False, "n": 0, "faltan": sorted(faltan)}
    valores.update(plano)
    extra = os.path.join(boveda_dir(), "plano.local")
    esperado = {n: str(v).replace("\n", " ").replace("\r", " ")
                for n, v in valores.items() if valid_name(n)}
    estaba_sellada = sellado()
    _desellar()
    # sin sello ni secrets.local, _ruta_plano sigue leyendo plano.local. Si
    # escribir o comprobar falla: se vuelve a sellar SOLO si estaba sellada y
    # no quedó nada en su lugar. Jamás se borra un archivo con llaves: si
    # nunca estuvo sellada, su secrets.local sigue intacto (el temporal no
    # llegó a reemplazarlo) — revisor independiente, R1.
    try:
        _escribir_privado(store_path(), _lineas(
            ["# WORKSPACE secrets (per-máquina, NUNCA versionar) — NOMBRE=valor"], valores))
        if _leer_lineas(store_path(), estricto=True) != esperado:
            raise LecturaFallida("secrets.local no quedó como se escribió")
    except BaseException:
        if estaba_sellada and not os.path.lexists(store_path()):
            _sellar()
        raise
    try:
        os.remove(extra)
    except FileNotFoundError:
        pass
    _escribir_indice({})
    for name, etiqueta in indice.items():
        _borrar_etiqueta(name, etiqueta)
    return {"ok": True, "n": len(valores), "faltan": []}


def deshacer(apagar=True):
    """Vuelve TODO al archivo de texto plano de siempre (`secrets.local`),
    borra lo de Workspace del llavero y, con `apagar` (lo que pide el
    socio), deja el modo en «file» hasta reactivar(). Sin `apagar` (volver a
    una versión anterior: `workspace update --rollback`), la próxima versión
    que conozca el llavero vuelve a migrar sola. Si falta algún valor, no
    cambia nada. → {"ok": bool, "n": int, "faltan": [NOMBRES]}. Los
    respaldos y las llaves archivadas se quedan (cifradas) hasta caducar."""
    try:
        with _locked():
            r = _al_archivo()
            if r["ok"] and apagar:
                _estado_poner(desactivado=True, aviso=None,
                              deshecho=time.strftime("%Y-%m-%dT%H:%M:%S"))
            elif r["ok"]:
                _estado_poner(aviso=None, deshecho=time.strftime("%Y-%m-%dT%H:%M:%S"))
            return r
    except Exception as e:
        return {"ok": False, "n": 0, "faltan": [], "error": type(e).__name__}


def reactivar():
    """Después de deshacer: deja que la bóveda vuelva a migrarse sola."""
    _estado_poner(desactivado=None)
    return migrar()


def al_arrancar():
    """Al arrancar Workspace (front.main), SOLO en la instalación activa
    (instalacion_activa: nunca un worktree ni una copia vieja): con el modo
    «file», devuelve al archivo lo que haya en el llavero; si no, migra lo
    que quede en texto plano (barato si no hay nada: lee un archivo), poda
    respaldos y archivadas vencidos y borra lo que una desinstalación dejó
    pendiente en el llavero. Candado corto: con otro proceso migrando, sigue
    de largo. Jamás levanta ni imprime."""
    try:
        if _modo() == "archivo" or not instalacion_activa():
            return None
        _limpiar_desinstalacion()
        _reintentar_pendientes()           # borrados que antes no se pudieron
        if modo_guardado() == "file":
            if correo_pendiente():
                migrar_correo(timeout=0.5)     # al archivo de la bóveda (0600), no a mail.json
            if _leer_indice():
                with _locked(timeout=0.5):
                    return _al_archivo()
            return None
        r = None
        if migracion_pendiente():
            r = migrar(timeout=0.5)
        if correo_pendiente():
            migrar_correo(timeout=0.5)
        _podar()
        return r
    except Exception:
        return None


# ── el correo (`workspace mail`): la contraseña, a la bóveda ───────────────
def correo_path():
    """`mail.json` del correo (usuario, host, puerto; la contraseña ya no)."""
    return os.path.join(_workspace_dir(), "mail.json")


def _leer_correo(estricto=True):
    """(dict, texto) de mail.json: ({}, None) si no existe. Otro error →
    LecturaFallida con `estricto` (nunca escribir tras una lectura fallida)."""
    p = correo_path()
    try:
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
    except FileNotFoundError:
        return {}, None
    except Exception as e:
        if estricto:
            raise LecturaFallida("%s: %s" % (type(e).__name__, p))
        return {}, None
    try:
        d = json.loads(txt)
    except ValueError:
        if estricto:
            raise LecturaFallida("mail.json no es JSON")
        return {}, txt
    return (d if isinstance(d, dict) else {}), txt


def guardar_correo_config(data):
    """Escribe mail.json SIN la contraseña: atómico, 0600 y, en Windows,
    solo-dueño (no hereda los permisos de la carpeta)."""
    limpio = {k: v for k, v in dict(data or {}).items() if k != "pass"}
    _escribir_privado(correo_path(), json.dumps(limpio, ensure_ascii=False, indent=2) + "\n")
    return correo_path()


def correo_pendiente():
    """¿mail.json todavía trae la contraseña en texto?"""
    try:
        d, _t = _leer_correo(estricto=False)
        return bool(str(d.get("pass") or "").strip())
    except Exception:
        return False


def migrar_correo(timeout=2):
    """Saca la contraseña de mail.json y la pone en la bóveda (CORREO_PASS),
    con la misma filosofía que migrar(): respaldo del mail.json original
    (cifrado si hay llavero; si no, 0600 en boveda/ y se borra al
    verificar), la VERIFICA leyéndola de vuelta y solo entonces reescribe
    mail.json sin ella. Idempotente, con el candado de la bóveda, falla-
    suave: si algo falla, mail.json queda como estaba y el correo funciona
    igual que hoy. → {"estado": "hecho"|"nada"|"fallo"|"ocupado"}."""
    try:
        with _locked(timeout=timeout):
            return _migrar_correo_bajo_candado()
    except Exception as e:
        if type(e).__name__ == "LockTimeout":
            return {"estado": "ocupado"}
        return {"estado": "fallo", "error": type(e).__name__}


def _migrar_correo_bajo_candado():
    if _volviendo():                       # `update --rollback` en curso: no se migra
        return {"estado": "ocupado"}
    try:
        d, txt = _leer_correo(estricto=True)
        plano, indice = _leer_plano(estricto=True), _leer_indice(estricto=True)
    except LecturaFallida as e:
        return {"estado": "fallo", "error": "lectura: %s" % e}
    if txt is None:
        return {"estado": "nada"}
    _solo_mio(correo_path(), forzar=True)  # Windows: solo-dueño aunque no haya qué mover
    pw = str(d.get("pass") or "").strip()
    if not pw:
        return {"estado": "nada"}
    tenia = CORREO_PASS in plano or CORREO_PASS in indice
    antes = _valor(CORREO_PASS, plano, indice) if tenia else ""
    try:
        respaldo = _respaldar(_backend(), txt)
    except Exception as e:
        return {"estado": "fallo", "error": type(e).__name__}
    try:
        _guardar_bajo_candado(CORREO_PASS, pw)
        _VALORES.clear()
        if _valor(CORREO_PASS, _leer_plano(estricto=True), _leer_indice(estricto=True)) != pw:
            raise NoDisponible("verificación")
        guardar_correo_config(d)
    except Exception as e:
        try:                               # todo como estaba
            if tenia and antes:
                _guardar_bajo_candado(CORREO_PASS, antes)
            elif not tenia:
                _quitar_bajo_candado(CORREO_PASS)
        except Exception:
            pass
        _quitar_respaldo(respaldo)
        return {"estado": "fallo", "error": type(e).__name__}
    if respaldo.get("donde") == "archivo":
        _quitar_respaldo(respaldo)          # verificada: el texto plano no se queda
        respaldo = None
    _estado_poner(correo_migrado=time.strftime("%Y-%m-%dT%H:%M:%S"), correo_respaldo=respaldo)
    return {"estado": "hecho"}


def devolver_correo():
    """Deshacer (y `update --rollback` a una versión que la lee de
    mail.json): la contraseña vuelve a mail.json (de la bóveda o, si no se
    puede, del respaldo) y sale de la bóveda. Si no hay de dónde sacarla, no
    cambia nada. → {"ok": bool, "n": int}."""
    try:
        with _locked():
            d, txt = _leer_correo(estricto=True)
            if str(d.get("pass") or "").strip():
                return {"ok": True, "n": 0}        # ya está en mail.json
            pw = get(CORREO_PASS)
            if not pw:
                reg = _estado().get("correo_respaldo")
                try:
                    pw = str(json.loads(_texto_respaldo(reg) or "{}").get("pass") or "") \
                        if isinstance(reg, dict) else ""
                except ValueError:
                    pw = ""
            if not pw:
                if has(CORREO_PASS):
                    return {"ok": False, "n": 0, "faltan": [CORREO_PASS]}
                return {"ok": True, "n": 0}        # nada que devolver
            d["pass"] = pw
            _escribir_privado(correo_path(), json.dumps(d, ensure_ascii=False, indent=2) + "\n")
            _quitar_bajo_candado(CORREO_PASS)
            _estado_poner(correo_migrado=None)
            return {"ok": True, "n": 1}
    except Exception as e:
        return {"ok": False, "n": 0, "error": type(e).__name__}


#: Lo que una desinstalación no pudo borrar del llavero (cerrado, por SSH):
#: sobrevive a la desinstalación (uninstall.STATE_KEEP) y se borra la
#: próxima vez que Workspace arranque con el llavero abierto.
PENDIENTE_DIR = "llavero-pendiente"


def _pendiente_path():
    return os.path.join(_workspace_dir(), PENDIENTE_DIR, "pendientes.json")


def _limpiar_desinstalacion():
    p = _pendiente_path()
    if not os.path.isfile(p):
        return
    try:
        with open(p, encoding="utf-8") as fh:
            pend = [x for x in json.load(fh) if isinstance(x, list) and len(x) == 2]
    except Exception:
        return
    quedan = []
    for name, etiqueta in pend:
        b = _backend_de(str(etiqueta))
        if b is None or not b.disponible() or not b.borrar(str(name), str(etiqueta)):
            quedan.append([name, etiqueta])
    try:
        if quedan:
            _escribir_privado(p, json.dumps(quedan))
        else:
            os.remove(p)
            os.rmdir(os.path.dirname(p))
    except OSError:
        pass


def _todo_lo_del_llavero():
    """[(NOMBRE, etiqueta)] de TODO lo que Workspace dejó en el llavero: el
    índice, los respaldos, los pendientes y lo archivado."""
    out = list(_leer_indice().items())
    est = _estado()
    for reg in est.get("respaldos") or []:
        if isinstance(reg, dict) and reg.get("etiqueta"):
            out.append((str(reg.get("nombre", "")), str(reg["etiqueta"])))
    for p in est.get("por_borrar") or []:
        if isinstance(p, list) and len(p) == 2:
            out.append((str(p[0]), str(p[1])))
    for a in est.get("archivadas") or []:
        if isinstance(a, dict) and a.get("etiqueta"):
            out.append((str(a.get("nombre", "")), str(a["etiqueta"])))
    return [x for x in out if x[1].startswith(("v2:llavero:", "v2:secret-tool:"))]


def olvidar_llavero():
    """Desinstalar: borra del llavero TODO lo de Workspace (cada entrada del
    índice, cada respaldo, lo archivado y lo pendiente); los archivos los
    borra quien desinstala. Lo que no se pudo borrar ahora (el llavero
    cerrado, por SSH) queda anotado en `<estado>/llavero-pendiente/`, que
    sobrevive a la desinstalación, y se borra al volver a arrancar (y
    pendientes_llavero() lo cuenta para la línea del desinstalador). → cuántos
    elementos borró. Falla-suave."""
    n, quedan = 0, []
    try:
        for name, etiqueta in _todo_lo_del_llavero():
            b = _backend_de(etiqueta)
            if b is not None and b.borrar(name, etiqueta):
                n += 1
            else:
                quedan.append([name, etiqueta])
        if quedan:
            _escribir_privado(_pendiente_path(), json.dumps(quedan))
    except Exception:
        pass
    return n


def pendientes_llavero():
    """Cuántos elementos de Workspace quedaron en el llavero sin borrar."""
    try:
        with open(_pendiente_path(), encoding="utf-8") as fh:
            return len(json.load(fh))
    except Exception:
        return 0


_NOMBRE_SISTEMA = {
    "llavero": ("el llavero de macOS (Llaves)", "the macOS Keychain"),
    "dpapi": ("Windows, cifradas con tu cuenta (DPAPI)", "Windows, encrypted with your account (DPAPI)"),
    "secret-tool": ("el llavero de tu sesión (Secret Service)", "your session keyring (Secret Service)"),
}


def aviso_pendiente(marcar=True):
    """El aviso de una línea: tras migrar, UNA vez («ahora viven en el
    llavero…, deshacer: …»); si el llavero no entregó una llave (cerrado,
    sin respuesta), una vez por episodio; y en «auto», si hay llaves en el
    archivo porque no hay llavero ahora, una vez al día. None si no hay nada
    que decir. Con `marcar`, queda mostrado."""
    try:
        est = _estado()
        if est.get("aviso") == "pendiente" and est.get("donde") in _NOMBRE_SISTEMA:
            if marcar:
                _estado_poner(aviso="mostrado")
            es, en = _NOMBRE_SISTEMA[est["donde"]]
            return _t("boveda.aviso.migrada",
                      "✓ Tus llaves de Workspace ahora viven en " + es + ", ya no en un archivo. "
                      "Deshacer: workspace migrate --undo " + MIGRACION_ID,
                      "✓ Your Workspace keys now live in " + en + ", no longer in a file. "
                      "Undo: workspace migrate --undo " + MIGRACION_ID)
        # el llavero no respondió / no entregó una llave: nunca en silencio
        marca = est.get("trabado") or est.get("ilegible")
        if marca and est.get("aviso_ilegible") != marca and _leer_indice():
            if marcar:
                _estado_poner(aviso_ilegible=marca)
            return _t("boveda.aviso.ilegible",
                      "⚠ No pude leer tus llaves del llavero del sistema ahora (cerrado o sin "
                      "respuesta): hasta que responda, lo que las usa dirá «sin llave». Workspace "
                      "reintenta solo; para ver cuáles: workspace llaves",
                      "⚠ I couldn't read your keys from the system keychain right now (locked or "
                      "not responding): until it does, what uses them will say «no key». "
                      "Workspace retries on its own; to see which: workspace keys")
        hoy = time.strftime("%Y-%m-%d")
        if _volviendo():
            return None                    # «sin llavero» mentiría: es una vuelta atrás
        if (modo_guardado() == "auto" and est.get("aviso_archivo") != hoy and _leer_plano()
                and _backend_esperado() and sistema() == "archivo"):
            if marcar:                     # en auto, el archivo NUNCA en silencio (1 vez al día)
                _estado_poner(aviso_archivo=hoy)
            return aviso_sin_llavero()
    except Exception:
        return None
    return None


# ── qué fuente usa cada llave y auditoría (sin valores) ─────────────────────
def _nombres_de_entorno(env):
    """Nombres de llaves que Workspace usa y que pueden venir del entorno."""
    out = set(PROVIDER_KEYS) | set(ENV_OVERRIDES)
    try:
        import decisions
        out |= set(decisions.key_names())
    except Exception:
        pass
    out |= {n for n in env if es_llave_de_decisor(n)}
    return out


def fuentes(env=None, probar=False):
    """[{"nombre", "fuente", "tambien"}] — de dónde sale HOY cada llave:
    "entorno" (exportada en tu sistema: manda), "llavero" | "dpapi" |
    "secret-tool" (el llavero del sistema) o "archivo" (texto plano 0600).
    `tambien` = las otras fuentes que la tienen (tapadas). Con `probar`,
    lee cada una del llavero y marca `ilegible` la que no entrega ahora.
    JAMÁS valores."""
    env = os.environ if env is None else env
    plano, indice = _leer_plano(), _leer_indice()
    cargadas = set(loaded_names(env))

    def del_entorno(n):
        return (n not in INTERNAL_NAMES and n not in cargadas
                and bool(str(env.get(n) or "").strip()))
    nombres = set(plano) | set(indice) | {n for n in _nombres_de_entorno(env) if del_entorno(n)}
    out = []
    for n in sorted(nombres):
        donde = []
        if del_entorno(n):
            donde.append("entorno")
        if n in plano:
            donde.append("archivo")
        if n in indice:
            donde.append(indice[n].split(":")[1] if indice[n].count(":") >= 1 else "llavero")
        f = {"nombre": n, "fuente": donde[0], "tambien": donde[1:]}
        if probar and donde[0] not in ("entorno", "archivo"):
            try:
                _resolver(n, indice[n], cache=False)
            except Exception:
                f["ilegible"] = True       # está en el llavero, pero ahora no se puede leer
        out.append(f)
    if correo_pendiente():
        out.append({"nombre": CORREO_PASS, "fuente": "mail.json", "tambien": []})
    return out


def fuente(name, env=None):
    """De dónde sale HOY la llave `name` (la primera de fuentes()): "entorno"
    | "llavero" | "dpapi" | "secret-tool" | "archivo", o "" si no hay. Sin
    valores."""
    for f in fuentes(env):
        if f["nombre"] == name:
            return f["fuente"]
    return ""


#: Archivos que la auditoría no abre (pesados o binarios).
_AUDITAR_MAX = 2 * 1024 * 1024
_AUDITAR_ARCHIVOS = 20000
#: Tope de lo que la auditoría lee en total (bytes): un dir de estado enorme
#: no la vuelve eterna (lo que quede sin leer, se dice: `"incompleta"`).
_AUDITAR_TOTAL = 200 * 1024 * 1024


def auditar(corregir=True):
    """Busca restos de llaves en TEXTO PLANO en el dir de estado de
    Workspace, sin imprimir valores: el archivo de la bóveda con valores,
    respaldos en texto plano, temporales huérfanos, permisos que no son
    solo-dueño (con `corregir`, los deja 0600/0700) y cualquier otro archivo
    del dir de estado que contenga un valor de la bóveda (un log, una
    copia). → {"limpio": bool, "modo", "sistema", "hallazgos": [{"ruta",
    "que", "nombres"}]} (rutas relativas al dir de estado)."""
    raiz = _workspace_dir()
    hall = []
    incompleta = False

    def rel(p):
        try:
            return os.path.relpath(p, raiz)
        except ValueError:
            return p

    def anota(p, que, nombres=()):
        hall.append({"ruta": rel(p), "que": que, "nombres": sorted(set(nombres))})
    plano = _leer_plano()
    if plano:
        anota(_ruta_plano(), "texto_plano", plano)
    if correo_pendiente():
        anota(correo_path(), "correo_texto_plano", [CORREO_PASS])
    privados = [p for p in (store_path(), indice_path(), _estado_path(), correo_path())
                if os.path.isfile(p)]
    bd = boveda_dir()
    try:
        for n in sorted(os.listdir(bd)):
            p = os.path.join(bd, n)
            if n.startswith("respaldo-") and n.endswith(".local"):
                anota(p, "respaldo_texto_plano", _leer_respaldo({"donde": "archivo", "ruta": p}))
            if os.path.isfile(p):
                privados.append(p)
    except OSError:
        pass
    for d in (raiz, bd):
        try:
            for n in os.listdir(d):
                if ".tmp-" in n and n.split(".tmp-")[0] in ("secrets.local", "indice.local",
                                                              "estado.json"):
                    anota(os.path.join(d, n), "temporal")
        except OSError:
            pass
    if os.name != "nt":
        dirs = [(bd, 0o700)] + ([(store_path(), 0o700)] if sellado() else [])
        for p, modo in [(p, 0o600) for p in privados] + dirs:
            try:
                actual = os.stat(p).st_mode & 0o777
            except OSError:
                continue
            if actual & 0o077:
                que = "permisos_abiertos"
                if corregir:
                    try:
                        os.chmod(p, modo)
                        que = "permisos_corregidos"
                    except OSError:
                        pass
                anota(p, que)
    # cualquier otro archivo con un valor de la bóveda adentro
    data = _read_raw()
    por_texto = {}
    for n, v in data.items():
        for t in _stored_texts({n: v}):
            if len(t) >= _TACHAR_MIN:
                por_texto.setdefault(t, set()).add(n)
    if por_texto:
        saltar = {os.path.normcase(os.path.abspath(p)) for p in (store_path(), _ruta_plano())}
        vistos, leidos = 0, 0
        for dp, dns, fns in os.walk(raiz):
            if vistos > _AUDITAR_ARCHIVOS or leidos > _AUDITAR_TOTAL:
                incompleta = True
                break
            if os.path.normcase(os.path.abspath(dp)) == os.path.normcase(os.path.abspath(bd)):
                dns[:] = []
                continue
            for fn in fns:
                p = os.path.join(dp, fn)
                if os.path.normcase(os.path.abspath(p)) in saltar or ".tmp-" in fn:
                    continue
                vistos += 1
                if vistos > _AUDITAR_ARCHIVOS or leidos > _AUDITAR_TOTAL:
                    incompleta = True
                    break
                try:
                    if os.path.islink(p) or os.path.getsize(p) > _AUDITAR_MAX:
                        continue
                    with open(p, "rb") as fh:
                        crudo = fh.read()
                    leidos += len(crudo)
                    txt = crudo.decode("utf-8", "ignore")
                except OSError:
                    continue
                nombres = set()
                for t, ns in por_texto.items():
                    if t in txt:
                        nombres |= ns
                if nombres:
                    anota(p, "valor_en_otro_archivo", nombres)
    malos = [h for h in hall if h["que"] != "permisos_corregidos"]
    return {"limpio": not malos, "modo": modo_guardado(), "sistema": sistema(),
            "hallazgos": hall, "incompleta": incompleta}


_QUE = {
    "texto_plano": ("llaves en texto plano en el archivo de la bóveda",
                    "keys in plain text in the vault file"),
    "respaldo_texto_plano": ("respaldo de la migración en texto plano (solo tuyo)",
                             "migration backup in plain text (yours only)"),
    "temporal": ("temporal de una escritura que no terminó", "leftover temp file of a write"),
    "permisos_abiertos": ("otros usuarios podrían leerlo", "other users could read it"),
    "permisos_corregidos": ("permisos corregidos a solo-dueño", "permissions fixed to owner-only"),
    "valor_en_otro_archivo": ("un valor de la bóveda aparece en este archivo",
                              "a vault value appears in this file"),
    "correo_texto_plano": ("la contraseña del correo sigue en texto plano en mail.json",
                           "the mail password is still in plain text in mail.json"),
}
_FUENTE = {"entorno": ("tu sistema (variable de entorno)", "your system (environment variable)"),
           "llavero": ("llavero de macOS", "macOS Keychain"),
           "dpapi": ("Windows (DPAPI)", "Windows (DPAPI)"),
           "secret-tool": ("llavero de tu sesión (Secret Service)", "session keyring (Secret Service)"),
           "archivo": ("archivo solo-dueño (texto plano)", "owner-only file (plain text)"),
           "mail.json": ("mail.json (texto plano, aún sin migrar)", "mail.json (plain text, not migrated yet)")}


def _lang_en():
    try:
        import i18n
        return i18n.lang() == "en"
    except Exception:
        return False


def cli(args=None):
    """`workspace llaves [estado | auditar] [--json]` (EN: `keys [status |
    audit]`): de dónde sale cada llave y la auditoría de restos en texto
    plano. NUNCA imprime un valor. rc: 0; auditar con hallazgos → 1."""
    args = list(sys.argv[1:] if args is None else args)
    en = _lang_en()
    como_json = "--json" in args
    pal = [a for a in args if not a.startswith("-")]
    accion = (pal[0] if pal else "estado").lower()
    if accion in ("auditar", "audit"):
        r = auditar()
        if como_json:
            print(json.dumps(r, ensure_ascii=False))
            return 0 if r["limpio"] else 1
        print(("Vault audit" if en else "Auditoría de la bóveda") + " · %s"
              % (_FUENTE.get(r["sistema"], ("", ""))[1 if en else 0] or r["sistema"]))
        if not r["hallazgos"]:
            print("  ✓ " + ("no plain-text leftovers in the state folder" if en
                            else "sin restos en texto plano en el dir de estado"))
        for h in r["hallazgos"]:
            es_, en_ = _QUE.get(h["que"], (h["que"], h["que"]))
            marca = "✓" if h["que"] == "permisos_corregidos" else "⚠"
            print("  %s %s — %s%s" % (marca, h["ruta"], en_ if en else es_,
                                      (" (%s)" % ", ".join(h["nombres"])) if h["nombres"] else ""))
        if r.get("incompleta"):
            print("  · " + ("the state folder is very large: not every file was read" if en
                            else "el dir de estado es muy grande: no se leyó cada archivo"))
        if r["hallazgos"] and any(h["que"] == "texto_plano" for h in r["hallazgos"]):
            print("  · " + ("they move to the system keyring on their own when it is available"
                            if en else "pasan solas al llavero del sistema cuando esté disponible"))
        return 0 if r["limpio"] else 1
    if accion not in ("estado", "status", "ver", "show"):
        print("uso: workspace llaves [estado | auditar] [--json]" if not en
              else "usage: workspace keys [status | audit] [--json]")
        return 2
    fs = fuentes(probar=True)
    if como_json:
        print(json.dumps({"modo": modo_guardado(), "sistema": sistema(), "llaves": fs},
                         ensure_ascii=False))
        return 0
    sis = sistema()
    print(("Keys · mode %s · saving to: %s" if en else "Llaves · modo %s · se guardan en: %s")
          % (modo_guardado(), _FUENTE.get(sis, ("", ""))[1 if en else 0] or sis))
    if not fs:
        print("  · " + ("no keys" if en else "ninguna llave"))
    for f in fs:
        txt = _FUENTE.get(f["fuente"], (f["fuente"], f["fuente"]))[1 if en else 0]
        extra = ""
        if f["tambien"]:
            extra = (" (also in: %s)" if en else " (también en: %s)") % ", ".join(f["tambien"])
        if f.get("ilegible"):
            extra += (" — UNREADABLE right now" if en else " — ILEGIBLE ahora")
        print("  · %-36s %s%s" % (f["nombre"], txt, extra))
    return 0


if __name__ == "__main__":
    # inspección rápida (NUNCA imprime valores): python3 secret_store.py
    #   [estado | auditar] · --migrar · --deshacer · --reactivar
    _args = sys.argv[1:]
    if "--migrar" in _args:
        print(json.dumps(migrar(timeout=5), ensure_ascii=False))
    elif "--deshacer" in _args:
        print(json.dumps(deshacer(), ensure_ascii=False))
    elif "--reactivar" in _args:
        print(json.dumps(reactivar(), ensure_ascii=False))
    else:
        sys.exit(cli(_args))
