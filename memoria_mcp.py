#!/usr/bin/env python3
"""WORKSPACE · memoria_mcp — la memoria de la pestaña como HERRAMIENTA MCP
(servidor por stdio), para los motores que preguntan por cada comando de
terminal: GitHub Copilot, Cursor y Kiro.

Por qué (hallazgo en vivo en Windows, 2026-11-05): aprobar la RUTA de un
ejecutable (`workspace-memoria`, memoria_permiso) deja colar otro comando
cuando el motor analiza la línea con una gramática (bash) y la ejecuta otra
shell (PowerShell, zsh): comillas tipográficas en Copilot y Cursor,
`${function:…}` en Kiro 3.0. Una herramienta MCP no pasa por ninguna shell:
el motor la llama con argumentos tipados (JSON) y la aprueba POR SU NOMBRE.
No hay nada que colar.

Herramientas (envoltorio de memoria.py y session_continuity.py, sin duplicar
su lógica):
  · guardar_nota(tipo, texto, cierra?)   = `workspace memoria nota`
  · guardar_resumen(expected_revision, objective, next_step, decision?,
    blocker?, result?)                   = `workspace memoria checkpoint`
  · ver_memoria()                        = `workspace memoria ver` (solo lee)

Dónde escribe: SOLO en la memoria de la pestaña de la ventana que abrió al
motor. Ninguna herramienta acepta cerebro, pestaña ni motor como argumento:
  1. la corrida viva de Workspace cuyo envoltorio es ancestro de este proceso
     (pending_runs, como el shim: memoria_permiso.corrida_viva; en Windows,
     con la foto de procesos de Win32, memoria_permiso._padre_windows). Es lo
     único que sirve en Cursor: le pasa al servidor solo un entorno mínimo
     (HOME, PATH…; VERIFICADO 2026.10.22);
  2. si no hay corrida (un turno sin ventana), el entorno que Workspace pone
     al lanzar y que Copilot le pasa al servidor (VERIFICADO 1.0.105):
     WORKSPACE_BRAIN y WORKSPACE_WS (+ WORKSPACE_ENGINE, WORKSPACE_SOCIO).
     Sin ellos, se niega.

El cableado por motor (registrar el servidor y pre-aprobar SOLO sus
herramientas, con la config documentada de cada fabricante) vive aquí abajo,
en «al abrir un agente»; lo llaman engines/copilot.py, cursor.py y kiro.py
(y engines/antigravity.py desde 2026-11-06: agy aprueba `command(…)` por
prefijo, así que su comando fijo de memoria dejaba pasar texto libre).

Protocolo: JSON-RPC 2.0, un mensaje por línea (transporte stdio de MCP):
initialize, notifications/initialized, ping, tools/list, tools/call. stdout
lleva SOLO el protocolo (cualquier print va a stderr); un error nunca sale
como traceback: va como resultado con isError o como error JSON-RPC.

Cero dependencias (stdlib, 3.9+). Mac, Windows y Linux.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:            # corre con `python -I`: sin la carpeta del script
    sys.path.insert(0, ROOT)

#: Nombre del servidor en la config de cada motor (y en sus reglas de permiso:
#: Copilot `workspace-memoria(guardar_nota)`, Cursor
#: `Mcp(workspace-memoria:guardar_nota)`, Kiro `@workspace-memoria/guardar_nota`).
SERVIDOR = "workspace-memoria"
VERSION = "1"
#: Las herramientas, en el orden en que se listan.
HERRAMIENTAS = ("guardar_nota", "guardar_resumen", "ver_memoria")
#: Versiones del protocolo MCP que este servidor habla (solo usa tools/*,
#: igual en todas). Si el cliente pide otra, se responde la más nueva.
PROTOCOLOS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
#: Tope de una línea de entrada (un mensaje JSON-RPC): nada de lo que aceptan
#: las herramientas se acerca.
MAX_LINEA = 256 * 1024
#: Tope del texto de una nota, ANTES de juntar espacios (memoria la deja en
#: MAX_TEXTO = 400 caracteres en una línea).
MAX_ENTRADA = 4000
#: Campos del resumen = session_continuity.FIELDS (≤600 caracteres cada uno).
CAMPOS_RESUMEN = ("objective", "decision", "blocker", "next_step", "result")
MAX_CAMPO = 600
MAX_CIERRA = 20

INSTRUCCIONES = (
    "Memoria de la pestaña de Workspace. Guarda en el momento, una nota por cosa: "
    "guardar_nota con tipo decision|pendiente|hecho|nota|dato|preferencia. Un pendiente "
    "devuelve su id (P-7); al resolverlo, guardar_nota tipo hecho con cierra [\"P-7\"]. "
    "dato/preferencia valen para todas las pestañas. Al terminar una unidad de trabajo, "
    "guardar_resumen con expected_revision (la que da ver_memoria). Nunca escribas la "
    "memoria a mano en los archivos del cerebro.")


# ── esquema de las herramientas ─────────────────────────────────────────────
def _tipos():
    import memoria
    return list(memoria.TIPOS)


def herramientas():
    """La lista de tools/list."""
    import memoria
    cadena = {"type": "string"}
    return [
        {"name": "guardar_nota",
         "title": "Guardar una nota en la memoria de la pestaña",
         "description": (
             "Guarda UNA nota en la memoria de esta pestaña de Workspace (lo mismo que "
             "`workspace memoria nota`). tipo: decision, pendiente, hecho, nota, dato o "
             "preferencia (dato y preferencia valen para todas las pestañas). Un pendiente o "
             "una decisión devuelven su id (P-3, D-2); para cerrarlos, una nota tipo hecho con "
             "cierra [\"P-3\"]. Una línea de hasta %d caracteres; nunca llaves ni contraseñas."
             % memoria.MAX_TEXTO),
         "inputSchema": {
             "type": "object",
             "properties": {
                 "tipo": {"type": "string", "enum": _tipos(),
                          "description": "Etiqueta de la nota."},
                 "texto": dict(cadena, minLength=1, maxLength=memoria.MAX_TEXTO,
                               description="La nota, en una línea."),
                 "cierra": {"type": "array", "maxItems": MAX_CIERRA,
                            "items": {"type": "string", "pattern": "^[PDpd]-[0-9]{1,6}$"},
                            "description": "Ids que esta nota cierra (P-3, D-2)."},
             },
             "required": ["tipo", "texto"],
             "additionalProperties": False}},
        {"name": "guardar_resumen",
         "title": "Guardar el resumen de la pestaña",
         "description": (
             "Guarda el resumen de esta pestaña (lo mismo que `workspace memoria "
             "checkpoint`): al terminar una unidad de trabajo o antes de cambiar de motor. "
             "expected_revision es la revisión actual del resumen (ver_memoria la dice; 0 si "
             "no hay): si otro chat lo cambió, falla con un conflicto y hay que reconciliar, "
             "nunca pisar. objective y next_step son obligatorios; cada campo, hasta %d "
             "caracteres." % MAX_CAMPO),
         "inputSchema": {
             "type": "object",
             "properties": dict(
                 {"expected_revision": {"type": "integer", "minimum": 0,
                                        "description": "Revisión actual del resumen."}},
                 **{k: dict(cadena, maxLength=MAX_CAMPO) for k in CAMPOS_RESUMEN}),
             "required": ["expected_revision", "objective", "next_step"],
             "additionalProperties": False}},
        {"name": "ver_memoria",
         "title": "Ver la memoria de la pestaña",
         "description": ("Muestra la memoria de esta pestaña (resumen, vigente, notas "
                         "recientes) y la revisión del resumen. Solo lee."),
         "inputSchema": {"type": "object", "properties": {},
                         "additionalProperties": False},
         "annotations": {"readOnlyHint": True}},
    ]


# ── dónde escribe ───────────────────────────────────────────────────────────
class Rechazo(ValueError):
    """Error que se le devuelve al agente tal cual (sin traceback)."""


def contexto(env=None, cadena=None):
    """{brain, tab, engine, socio} de la ventana que abrió al motor: la
    corrida viva (ancestro) y, sin ella, el entorno de Workspace. Rechazo si
    no hay ninguno de los dos."""
    env = os.environ if env is None else env
    try:
        import memoria_permiso
        return memoria_permiso.corrida_viva(cadena)
    except ValueError as e:
        # una corrida viva SIN cerebro o SIN pestaña es una respuesta: no se
        # adivina con el entorno
        if "no encuentro la corrida" not in str(e):
            raise Rechazo(str(e))
    except Exception:
        pass
    brain = _valor(env, "WORKSPACE_BRAIN")
    tab = _valor(env, "WORKSPACE_WS") or _valor(env, "ZENITH_WS")
    if not brain or not os.path.isdir(brain):
        raise Rechazo("solo guarda desde un agente abierto con Workspace (no sé de qué "
                      "cerebro es esta ventana)")
    if not tab:
        raise Rechazo("esta ventana no tiene pestaña de Workspace")
    import memoria
    return {"brain": memoria.raiz_cerebro(brain), "tab": tab,
            "engine": memoria.normalizar_motor(_valor(env, "WORKSPACE_ENGINE")),
            "socio": _valor(env, "WORKSPACE_SOCIO") or None}


def _valor(env, k):
    """Valor de una variable de la pestaña; '' si falta o si es un `${…}` /
    `$NOMBRE` sin expandir (Kiro deja así una variable que no existe en
    `env` de su config, VERIFICADO 2.37.1: el socio salía «${workspace_socio}»)."""
    import re
    v = str(env.get(k) or "").strip()
    return "" if re.fullmatch(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", v) else v


def _fijar(run):
    """El proceso queda con el entorno de la pestaña (el socio decide la
    carpeta de STATE/sessions; memoria lo lee del entorno) y, si es uno de
    los motores de la herramienta, marcado como tal: lo que muestre
    ver_memoria dice «usa la herramienta», no el comando."""
    import memoria
    import memoria_permiso
    memoria_permiso._fijar_entorno(run)
    m = memoria.normalizar_motor(run.get("engine") or "")
    if m in MOTORES:
        os.environ[ENV_ACTIVO] = m


# ── validación ──────────────────────────────────────────────────────────────
def _objeto(args):
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise Rechazo("los argumentos tienen que ser un objeto")
    return args


def _sobrantes(args, permitidos):
    extra = sorted(k for k in args if k not in permitidos)
    if extra:
        raise Rechazo("argumento desconocido: %s (acepta: %s)"
                      % (", ".join(extra), ", ".join(permitidos)))


def _texto(args, k, tope, obligatorio=False):
    v = args.get(k, "")
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise Rechazo("%s tiene que ser texto" % k)
    if "\x00" in v:
        raise Rechazo("%s trae un carácter nulo" % k)
    v = " ".join(v.split())
    if obligatorio and not v:
        raise Rechazo("falta %s" % k)
    if len(v) > tope:
        raise Rechazo("%s es muy largo (%d caracteres; máximo %d): acórtalo o divídelo"
                      % (k, len(v), tope))
    return v


def validar_nota(args):
    import memoria
    args = _objeto(args)
    _sobrantes(args, ("tipo", "texto", "cierra"))
    tipo = args.get("tipo")
    if not isinstance(tipo, str) or tipo.strip().lower() not in memoria.TIPOS:
        raise Rechazo("tipo inválido: %r (usa uno de: %s)" % (tipo, ", ".join(memoria.TIPOS)))
    crudo = args.get("texto")
    if isinstance(crudo, str) and len(crudo) > MAX_ENTRADA:
        raise Rechazo("texto es muy largo (máximo %d caracteres)" % memoria.MAX_TEXTO)
    texto = _texto(args, "texto", memoria.MAX_TEXTO, obligatorio=True)
    cierra = args.get("cierra") or []
    if isinstance(cierra, str):
        cierra = [cierra]
    if not isinstance(cierra, list) or len(cierra) > MAX_CIERRA \
            or not all(isinstance(c, str) for c in cierra):
        raise Rechazo("cierra tiene que ser una lista de ids (P-3, D-2), hasta %d" % MAX_CIERRA)
    import re
    for c in cierra:
        if not re.fullmatch(r"[PDpd]-\d{1,6}", c.strip()):
            raise Rechazo("id para cerrar inválido: %r (ejemplo: P-3)" % c)
    return {"tipo": tipo.strip().lower(), "texto": texto,
            "cierra": [c.strip().upper() for c in cierra]}


def validar_resumen(args):
    args = _objeto(args)
    _sobrantes(args, ("expected_revision",) + CAMPOS_RESUMEN)
    rev = args.get("expected_revision")
    if isinstance(rev, bool) or not isinstance(rev, int):
        if isinstance(rev, float) and rev.is_integer():
            rev = int(rev)
        else:
            raise Rechazo("expected_revision tiene que ser un entero (la revisión actual; "
                          "0 si no hay resumen)")
    if rev < 0:
        raise Rechazo("expected_revision no puede ser negativa")
    campos = {k: _texto(args, k, MAX_CAMPO, obligatorio=k in ("objective", "next_step"))
              for k in CAMPOS_RESUMEN}
    return rev, campos


# ── las herramientas ────────────────────────────────────────────────────────
def guardar_nota(args, run):
    import memoria
    v = validar_nota(args)
    try:
        r = memoria.guardar_nota(run["brain"], run["tab"], v["texto"], tipo=v["tipo"],
                                 motor=run.get("engine") or "", cierra=v["cierra"])
    except (ValueError, OSError, TimeoutError) as e:
        raise Rechazo(str(e))
    extra = (" · " + r["id"]) if r["id"] else ""
    if r["cerro"]:
        extra += " · cerré " + ", ".join(r["cerro"])
    if r["desconocidos"]:
        extra += " · (no estaban abiertos: %s)" % ", ".join(r["desconocidos"])
    return "✓ guardado (%s%s) en %s" % (memoria.ETIQUETA[r["tipo"]], extra, r["ruta"])


def guardar_resumen(args, run):
    import session_continuity as sc
    import memoria
    rev, campos = validar_resumen(args)
    try:
        memoria.ficha_path(run["brain"], run["tab"], crear=True)   # como `nota`: siembra si falta
        cp = sc.write_checkpoint(run["brain"], run["tab"], rev, engine=run.get("engine") or "",
                                 **campos)
    except (ValueError, OSError, TimeoutError) as e:
        msg = str(e)
        if msg.startswith("Conflicto de revisión"):
            msg += (": otro chat cambió el resumen; léelo con ver_memoria, reconcilia y "
                    "guarda con esa revisión (nunca pises)")
        raise Rechazo(msg)
    return "✓ resumen guardado (revisión %s)" % cp["revision"]


def ver_memoria(args, run):
    import memoria
    import session_continuity as sc
    _sobrantes(_objeto(args), ())
    try:
        cp = sc.read_checkpoint(run["brain"], run["tab"])
        rev = cp["revision"] if cp else 0
        texto = memoria.paquete(run["brain"], run["tab"], motor=run.get("engine") or "")
    except (ValueError, OSError, TimeoutError) as e:
        raise Rechazo(str(e))
    cabeza = "expected_revision para guardar_resumen: %d" % rev
    return cabeza + "\n\n" + (texto or "(esta pestaña no tiene memoria todavía)")


_LLAMAR = {"guardar_nota": guardar_nota, "guardar_resumen": guardar_resumen,
           "ver_memoria": ver_memoria}


def llamar(nombre, args, env=None, cadena=None):
    """tools/call → (texto, es_error). Nunca lanza."""
    try:
        run = contexto(env, cadena)
        _fijar(run)
        return _LLAMAR[nombre](args, run), False
    except Rechazo as e:
        return "No se guardó: %s" % e if nombre != "ver_memoria" else str(e), True
    except Exception as e:                       # jamás un traceback al motor
        _log("error en %s: %s: %s" % (nombre, type(e).__name__, e))
        return "Error interno de Workspace (%s). Avísale al socio en una línea." \
            % type(e).__name__, True


# ── al abrir un agente: el cableado por motor ───────────────────────────────
#: Motores que guardan con esta herramienta (los que preguntan por cada
#: comando de terminal). Los demás no cambian (Claude Code: `--settings`;
#: Codex: escribir en el cerebro). Antigravity se sumó el 2026-11-06: su regla
#: `command(…)` compara por prefijo desde la 1.5.1 (ver memoria.ENTRADA_ARCHIVO).
MOTORES = ("copilot", "cursor", "kiro", "antigravity")
#: La corrida en curso dejó la herramienta cableada: = el motor. Lo pone el
#: lanzador antes de armar el bloque de la pestaña y lo heredan el motor y su
#: terminal (memoria.instruccion lo lee para decir «usa la herramienta»).
ENV_ACTIVO = "WORKSPACE_MEMORIA_MCP"
#: Agente propio de Kiro (con el servidor y sus herramientas aprobadas).
KIRO_AGENTE = "workspace"
KIRO_MARCA = "WORKSPACE ·"
#: Lo que el agente de Kiro no escribe (doc «built-in tools»: `deniedPaths`,
#: estilo gitignore; doc «permissions», https://kiro.dev/docs/permissions/:
#: regla `deny`). La config de TODOS los motores, git y Obsidian del cerebro
#: (rutas_protegidas): no solo `.kiro/`. RELATIVAS al cerebro, como el allow:
#: un patrón absoluto en `match` hace que V3 descarte la regla entera.
#: Las de antes (solo `.kiro`) se reconocen como nuestras al rehacer.
KIRO_DENY_V2_ANTES = (".kiro",)
KIRO_DENY_V3_ANTES = ("./.kiro/**",)
#: Lo que el agente de Kiro escribe SIN PREGUNTAR con autonomía «brain» (la de
#: fábrica): todo el cerebro, y nada más. Relativa a la carpeta donde abre Kiro,
#: que es el cerebro (Workspace siempre lo abre ahí). La MISMA forma en las dos
#: líneas: 2.x `toolsSettings.fs_write.allowedPaths` y V3 una regla `allow` de
#: `fs_write` (la doc «migration guide» las da como equivalentes, y `kiro-cli
#: agent upgrade` convierte una en la otra sin tocar el patrón). Es la forma del
#: preset `edit-workspace` de Kiro (doc «permissions»). Sin rutas absolutas: en
#: Windows llevarían `C:` y `\`, y en V3 un patrón `C:/…` hace que Kiro descarte
#: TODA la regla (VERIFICADO 3.1.0 en vivo en la Mac: pregunta). El deny de
#: `.kiro` gana igual (deny > allow en V3; en 2.x `deniedPaths`).
KIRO_ESCRIBE = "./**"
#: Cada deny de Kiro va también con sus letras como clase (`.[kK][iI]…`): en
#: macOS y Windows `.CURSOR/` es `.cursor/`. VERIFICADO 3.1.0 en la Mac
#: (tests/e2e/kiro_permisos.py, casos «mayus_*»): con el chat V2 `.CURSOR/x`
#: se escribía sin preguntar con solo `.cursor`; V3 ya lo negaba.
KIRO_SIN_MAYUSCULAS = True
#: Autonomías con las que el agente escribe en su cerebro sin preguntar
#: (contrato común: engines/_ui.autonomy; «full» de antes se lee «brain»).
KIRO_AUTONOMIAS_LIBRES = ("brain", "full")
#: Estados de _rehacer y _fusionar con los que el archivo quedó como debe.
LISTO = ("ready", "written", "restored")


def _python():
    """El Python que corre el servidor: el mismo que hornea el shim (desde un
    venv, el base; en Windows, install.win_python)."""
    import memoria_permiso
    return memoria_permiso._python()


def servidor(root=None, python=None):
    """{command, args} del servidor: Python aislado (-I: ni PYTHON*, ni el
    site-packages del usuario, ni la carpeta actual) y sin escribir .pyc
    (-B: -I no lo implica; dejaba __pycache__ en la carpeta de Workspace)
    + este archivo."""
    return {"command": python or _python(),
            "args": ["-I", "-B", os.path.join(root or ROOT, "memoria_mcp.py")]}


def _es_nuestro(entrada):
    """¿La entrada de un servidor es la de Workspace (de este árbol o de otro:
    un checkout movido, un worktree)?"""
    if not isinstance(entrada, dict):
        return False
    args = entrada.get("args")
    # "-I" + archivo (antes de -B) o "-I", "-B" + archivo
    if not (isinstance(args, list) and args and args[0] == "-I"
            and args[1:-1] in ([], ["-B"])):
        return False
    return (isinstance(args[-1], str)
            and os.path.basename(args[-1].replace("\\", "/")) == "memoria_mcp.py")


def _respaldo_dir(brain):
    import hashlib
    import time
    import paths
    clave = hashlib.sha256(os.path.normcase(os.path.realpath(str(brain))).encode("utf-8")).hexdigest()[:8]
    return os.path.join(paths.state_dir(), "respaldos", "memoria-mcp",
                        time.strftime("%Y%m%d-%H%M%S") + "-" + clave)


def _respaldar(brain, ruta, rel, avisos):
    """Copia `ruta` (o, si es un enlace, adónde apuntaba) al estado de
    Workspace, fuera del cerebro, y deja un aviso de una línea (si `avisos`
    no es None). → la ruta del respaldo."""
    import shutil
    d = _respaldo_dir(brain)
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, rel.replace("\\", "/").strip("/").replace("/", "__"))
    if os.path.islink(ruta):
        dest += ".enlace.txt"
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(os.readlink(ruta) + "\n")
    else:
        shutil.copy2(ruta, dest)
    if avisos is not None:
        avisos.append("WORKSPACE: %s de tu cerebro no era el de Workspace (¿lo cambió alguien?); "
                      "lo respaldé en %s y lo rehice." % (rel.replace("\\", "/"), dest))
    return dest


# · Enlaces: una ruta del cerebro que lleva a otra parte no se toca ·
#: Etiquetas de reparse de Windows que son enlaces: junction y symlink (un
#: archivo de OneDrive bajo demanda también es reparse, y no es un enlace).
#: Python 3.9 no tiene os.path.isjunction; = skills_aprendidas._REPARSE_ENLACE.
_REPARSE_ENLACE = (0xA0000003, 0xA000000C)


def _enlace(p):
    """¿Enlace simbólico o junction (Windows, también en 3.9)? Si no existe
    (o algo de su ruta no es carpeta), no; ante cualquier otra duda, sí."""
    try:
        if os.path.islink(p):
            return True
        return getattr(os.lstat(p), "st_reparse_tag", 0) in _REPARSE_ENLACE
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True


def _enlace_en_ruta(brain, rel):
    """¿Algún tramo de `rel` DENTRO del cerebro (sus carpetas, como `.agents`
    o `.cursor`, o el archivo) es un enlace o junction? El cerebro mismo puede
    serlo: no cuenta."""
    actual = str(brain)
    for p in rel.replace("\\", "/").split("/"):
        actual = os.path.join(actual, p)
        if _enlace(actual):
            return True
        if not os.path.lexists(actual):
            return False
    return False


def _t(key, es, en=None, **kw):
    """i18n falla-suave (catálogo lang/<code>/motorbar.py → ES/EN inline)."""
    try:
        import workspace_status
        return workspace_status.t(key, es, en, **kw)
    except Exception:
        try:
            return es.format(**kw)
        except Exception:
            return es


#: Avisos de una línea de la config compartida: (clave, ES, EN).
_AVISO = {
    "enlace": ("motorbar.memoria_mcp.enlace",
               "WORKSPACE: {rel} de tu cerebro (o una carpeta de su ruta) es un enlace: no "
               "lo toco y la memoria pedirá permiso.",
               "WORKSPACE: {rel} in your brain (or a folder on its path) is a link: I leave "
               "it alone and memory will ask for permission."),
    "ilegible": ("motorbar.memoria_mcp.ilegible",
                 "WORKSPACE: {rel} de tu cerebro no es un JSON que entienda: no lo toco y la "
                 "memoria pedirá permiso hasta que lo arregles.",
                 "WORKSPACE: {rel} in your brain isn't JSON I can read: I leave it alone and "
                 "memory will ask for permission until you fix it."),
    "ocupado": ("motorbar.memoria_mcp.ocupado",
                "WORKSPACE: donde va {rel} en tu cerebro hay algo que no es un archivo: no lo "
                "toco y la memoria pedirá permiso.",
                "WORKSPACE: where {rel} goes in your brain there's something that isn't a "
                "file: I leave it alone and memory will ask for permission."),
    "escritura": ("motorbar.memoria_mcp.escritura",
                  "WORKSPACE: no pude escribir {rel} en tu cerebro: la memoria pedirá permiso.",
                  "WORKSPACE: couldn't write {rel} in your brain: memory will ask for "
                  "permission."),
    "cursor_sin_deny": ("motorbar.memoria_mcp.cursor_sin_deny",
                        "WORKSPACE: sin {rel}, Cursor no tiene negada la config de los motores, "
                        "git y Obsidian de tu cerebro: revisa ese archivo.",
                        "WORKSPACE: without {rel}, Cursor isn't denied the engines', git's and "
                        "Obsidian's config in your brain: check that file."),
    "restaurada": ("motorbar.memoria_mcp.restaurada",
                   "WORKSPACE: {rel} de tu cerebro: lo de Workspace (`workspace-memoria`) "
                   "estaba cambiado; lo restauré y lo tuyo queda igual (respaldo en {respaldo}).",
                   "WORKSPACE: {rel} in your brain: Workspace's entry (`workspace-memoria`) "
                   "had been changed; I restored it and yours stays as is (backup in "
                   "{respaldo})."),
}


def _avisar(avisos, motivo, rel, **kw):
    if avisos is None:
        return
    clave, es, en = _AVISO[motivo]
    avisos.append(_t(clave, es, en, rel=rel.replace("\\", "/"), **kw))


# · Config COMPARTIDA con el socio: se fusiona, no se rehace ·
# `.agents/mcp_config.json` (agy) y `.cursor/mcp.json` / `.cursor/cli.json`
# (Cursor) son la config de PROYECTO del motor: ahí el socio tiene sus propios
# servidores y reglas. Workspace mete o actualiza SOLO lo suyo (el servidor
# `workspace-memoria`, sus reglas allow y deny) y deja todo lo demás tal cual.
# Si algo no se puede tocar (un enlace en la ruta, un JSON ilegible, una
# carpeta donde va el archivo), no se escribe nada: la memoria pide permiso,
# con un aviso de una línea. El agente no escribe esas carpetas (deny de cada
# motor: `Write(**/.cursor/**)`, `write_file(<cerebro>/.agents)`).
class _NoSeToca(Exception):
    """El archivo no se toca; el mensaje es el motivo (clave de _AVISO)."""


def _forma_nuestra(cur, want):
    """¿`cur` es la entrada que escribe Workspace, solo que con otro Python u
    otra carpeta de Workspace (Python actualizado, checkout movido)? Entonces
    se actualiza sin respaldo ni aviso."""
    import re
    if not _es_nuestro(cur) or set(cur) != set(want):
        return False
    if any(cur[k] != want[k] for k in want if k not in ("command", "args")):
        return False
    cmd = cur.get("command")
    if not isinstance(cmd, str):
        return False
    base = os.path.basename(cmd.replace("\\", "/")).lower()
    if base.endswith(".exe"):
        base = base[:-4]
    return re.fullmatch(r"python[0-9.]*w?", base) is not None


def _con_servidor(want):
    """Fusión de `mcpServers`: `workspace-memoria` = `want`; los demás
    servidores, tal cual y en su orden. → fusion(data) → (nuevo, alterado):
    `alterado` = había una entrada con nuestro nombre que no es una forma
    nuestra (otro comando, otros campos). ValueError si `mcpServers` no es un
    objeto (no se toca)."""
    def fusion(data):
        srv = data.get("mcpServers")
        if srv is None:
            srv = {}
        if not isinstance(srv, dict):
            raise ValueError("mcpServers no es un objeto")
        cur = srv.get(SERVIDOR)
        if cur == want and "mcpServers" in data:
            return data, False
        nuevo = dict(data)
        nuevo["mcpServers"] = dict(srv)
        nuevo["mcpServers"][SERVIDOR] = want
        return nuevo, SERVIDOR in srv and not _forma_nuestra(cur, want)
    return fusion


def _con_reglas(want):
    """Fusión de `permissions` (`.cursor/cli.json`): a cada lista de `want`
    (allow, deny) se le agregan al final las reglas nuestras que falten; las
    del socio quedan tal cual. `want` es un dato opaco (qué se niega lo decide
    quien lo da). → fusion(data) → (nuevo, alterado): `alterado` = faltaba una
    de nuestras reglas allow pero otra seguía (alguien la quitó). ValueError si
    `permissions` o una de sus listas no tiene la forma (no se toca)."""
    def fusion(data):
        perms = data.get("permissions")
        if perms is None:
            perms = {}
        if not isinstance(perms, dict):
            raise ValueError("permissions no es un objeto")
        nuevo_p = dict(perms)
        for clave, nuestras in want.items():
            cur = perms.get(clave)
            if cur is None:
                cur = []
            if not isinstance(cur, list):
                raise ValueError("permissions.%s no es una lista" % clave)
            faltan = [r for r in nuestras if r not in cur]
            if faltan or not isinstance(perms.get(clave), list):
                nuevo_p[clave] = list(cur) + faltan
        if nuevo_p == perms and "permissions" in data:
            return data, False
        allow = list(want.get("allow") or ())
        hay = [r for r in allow if r in (perms.get("allow") or [])]
        nuevo = dict(data)
        nuevo["permissions"] = nuevo_p
        return nuevo, 0 < len(hay) < len(allow)
    return fusion


def _plan_fusion(brain, rel, fusion):
    """Lee `<cerebro>/<rel>` y calcula la fusión, SIN escribir. → (ruta,
    actual, nuevo, alterado, existe). _NoSeToca si no se puede tocar."""
    rel = rel.replace("\\", "/")
    if _enlace_en_ruta(brain, rel):
        raise _NoSeToca("enlace")
    partes = rel.split("/")
    actual = str(brain)
    for p in partes[:-1]:
        actual = os.path.join(actual, p)
        if os.path.lexists(actual) and not os.path.isdir(actual):
            raise _NoSeToca("ocupado")
    path = os.path.join(str(brain), *partes)
    if os.path.lexists(path) and not os.path.isfile(path):
        raise _NoSeToca("ocupado")
    try:
        data, txt = _leer_json(path)
        nuevo, alterado = fusion(data)
    except (OSError, ValueError, UnicodeDecodeError, TypeError):
        raise _NoSeToca("ilegible")
    return path, data, nuevo, alterado, txt is not None


def _fusionar(brain, cambios, avisos=None):
    """Fusiona `cambios` = [(rel, fusion), …] en archivos de config del
    cerebro COMPARTIDOS con el socio: mete o actualiza solo lo nuestro. Si uno
    no se puede tocar, no se escribe ninguno (aviso de una línea). Un archivo
    que ya estaba se reescribe con su mismo modo. Si nuestra entrada estaba
    cambiada, el archivo se respalda fuera del cerebro y se avisa. → 'ready' |
    'written' | 'restored' | 'blocked'."""
    brain = str(brain)
    planes = []
    for rel, fusion in cambios:
        try:
            planes.append((rel, _plan_fusion(brain, rel, fusion)))
        except _NoSeToca as e:
            _avisar(avisos, str(e), rel)
            return "blocked"
    estados = []
    for rel, (path, actual, nuevo, alterado, existe) in planes:
        if existe and nuevo == actual:
            estados.append("ready")
            continue
        try:
            if alterado and existe:
                _avisar(avisos, "restaurada", rel, respaldo=_respaldar(brain, path, rel, None))
            _escribir_json(path, nuevo, None)
        except (OSError, ValueError, TypeError):
            _avisar(avisos, "escritura", rel)
            return "blocked"
        estados.append("restored" if alterado and existe else "written")
    for e in ("restored", "written"):
        if e in estados:
            return e
    return "ready"


def _rehacer(brain, rel, want, avisos=None, nuestros=()):
    """Deja `<cerebro>/<rel>` EXACTAMENTE como `want` (JSON). Solo para un
    archivo que es TODO de Workspace (con nombre propio: el agente
    `.kiro/agents/workspace.json`); la config compartida con el socio se
    fusiona (_fusionar). El agente escribe en su cerebro sin preguntar y
    podría darse permisos ahí: lo que no coincida (otro contenido, JSON roto,
    un enlace en lugar del archivo) se respalda en el estado de Workspace y se
    rehace; el aviso va a `avisos`. Una CARPETA de su ruta que es un enlace
    no se toca (sería del socio, p. ej. compartida): 'blocked' con aviso.
    `nuestros` = otras formas que también escribe Workspace (la otra
    autonomía, la de la versión anterior): esas se rehacen sin respaldo ni
    aviso. → 'ready' | 'written' | 'restored' | 'blocked' (no se pudo)."""
    brain = str(brain)
    partes = rel.replace("\\", "/").split("/")
    rehecho = False
    try:
        actual = brain
        for p in partes[:-1]:              # carpetas: un enlace no se toca
            actual = os.path.join(actual, p)
            if _enlace(actual):
                _avisar(avisos, "enlace", rel)
                return "blocked"
            if os.path.lexists(actual) and not os.path.isdir(actual):
                return "blocked"
        path = os.path.join(brain, *partes)
        if os.path.islink(path):
            _respaldar(brain, path, rel, avisos)
            os.unlink(path)
            rehecho = True
        elif os.path.isdir(path):
            return "blocked"
        elif os.path.exists(path):
            try:
                cur, _txt = _leer_json(path)
            except (ValueError, UnicodeDecodeError):
                cur = None
            if cur == want:
                return "ready"
            if cur is not None and any(cur == n for n in nuestros):
                _escribir_json(path, want, 0o600)
                return "written"
            _respaldar(brain, path, rel, avisos)
            _escribir_json(path, want, 0o600)
            return "restored"
        _escribir_json(path, want, 0o600)
        return "restored" if rehecho else "written"
    except (OSError, ValueError, TypeError):
        return "blocked"


def activo(motor, env=None):
    """¿La corrida en curso de `motor` guarda con la herramienta?"""
    import memoria
    env = os.environ if env is None else env
    m = memoria.normalizar_motor(motor)
    return m in MOTORES and str(env.get(ENV_ACTIVO) or "") == m


def _marcar(motor):
    if motor:
        os.environ[ENV_ACTIVO] = motor
    else:
        os.environ.pop(ENV_ACTIVO, None)


def _leer_json(path):
    """(dict, texto) o ({}, None) si no existe. ValueError si no es un objeto
    JSON (no se toca) u OSError."""
    from motor_statusline import _read
    from pathlib import Path
    return _read(Path(path))


def _escribir_json(path, data, mode=0o600):
    """Escritura atómica. `mode=None`: un archivo que ya estaba conserva SU
    modo (el del socio: antes quedaba 0600 por el temporal); uno nuevo, 0600.
    En Windows no hay modo POSIX que conservar."""
    from motor_statusline import _write
    from pathlib import Path
    if mode is None and os.name != "nt":
        try:
            mode = os.stat(path).st_mode & 0o777
        except OSError:
            mode = None
    _write(Path(path), data, mode)


def _reglas(formato):
    return [formato % t for t in HERRAMIENTAS]


# · GitHub Copilot: config y permiso POR CORRIDA (nada escrito en su config) ·
def copilot_config_path(home=None):
    """Config MCP de Workspace para Copilot (estado de Workspace, fuera del
    cerebro y de ~/.copilot): la lee `--additional-mcp-config=@<archivo>`."""
    import paths
    return os.path.join(paths.state_dir(home), "copilot-mcp.json")


def copilot_config(root=None, python=None):
    """El servidor con SOLO sus herramientas (`tools`). Sin `env`: Copilot le
    pasa al servidor el entorno de la corrida (VERIFICADO 1.0.105), que es el
    de la pestaña; además sus valores expanden `$VAR`."""
    return {"mcpServers": {SERVIDOR: dict(servidor(root, python), type="local",
                                          tools=list(HERRAMIENTAS))}}


def copilot_args(path=None):
    """`--additional-mcp-config=@<archivo>` + `--allow-tool=workspace-memoria(<h>)`
    por herramienta (doc: «SERVER-NAME(tool)»; con `=`: --allow-tool acepta
    varios valores y se comería lo que sigue)."""
    return (["--additional-mcp-config=@" + (path or copilot_config_path())]
            + ["--allow-tool=" + r for r in _reglas(SERVIDOR + "(%s)")])


def preparar_copilot(passthrough=(), root=None, python=None):
    path = copilot_config_path()
    want = copilot_config(root, python)
    try:
        cur, _txt = _leer_json(path)
    except (OSError, ValueError):
        cur = None
    if cur != want:
        _escribir_json(path, want)
    return copilot_args(path)


# · Cursor: servidor y permisos del PROYECTO (.cursor/ del cerebro) ·
#: Doc de Cursor: `.cursor/mcp.json` (servidores) y `.cursor/cli.json` (solo
#: permisos) del proyecto. Regla de permiso: `Mcp(server:tool)`.
CURSOR_REGLA = "Mcp(" + SERVIDOR + ":%s)"


def cursor_paths(brain):
    d = os.path.join(str(brain), ".cursor")
    return os.path.join(d, "mcp.json"), os.path.join(d, "cli.json")


def cursor_reglas():
    return _reglas(CURSOR_REGLA)


#: Lo que el agente NO puede escribir en Cursor: la carpeta `.cursor/` del
#: cerebro (aquí viven el servidor y estos permisos; también sus hooks y
#: reglas) y la config de los DEMÁS motores, git y Obsidian
#: (rutas_protegidas). Doc «permissions»,
#: https://cursor.com/docs/cli/reference/permissions: `Write(pathOrGlob)`, el
#: deny gana. VERIFICADO 2026.10.22 (caja negra): `Write(.cursor/**)` relativa
#: NO bloquea (la herramienta de Cursor escribe con la ruta absoluta);
#: `Write(**/.cursor/**)` sí, y escribir en el resto del cerebro sigue igual.
#: Las demás van con la misma forma (`**/` delante: el archivo viaja con el
#: cerebro a otras máquinas, sin rutas absolutas).
#: LÍMITES (sin verificar: Cursor no se prueba sin cuenta): `Write(**/.git/**)`
#: aplica a TODO el disco, no solo al cerebro (niega también la `.git` de otro
#: repo, del lado seguro); y no se sabe si Cursor compara sin mayúsculas en
#: macOS ni si un punto o espacio al final del nombre esquiva la regla allá.
#: WINDOWS (VERIFICADO 2026-11-06, Windows 11, cursor-agent 2026.11.05, caja
#: negra en su consola con un `.cursor/cli.json` de proyecto): las reglas con
#: `/` NO niegan nada (`Write(**/x/**)`, `Write(x/**)` ni la absoluta con `/`:
#: escribió sin preguntar `.git\x`, `.kiro\agents\x.json`, `.obsidian\x.js`);
#: solo niegan con `\` (`Write(**\x\**)` o la absoluta con `\`: «Write
#: permission denied: …: Blocked by permissions configuration»). Compara con
#: mayúsculas y sin clases `[aA]`, `?` ni llaves `{a,b}` (ninguna negó); una
#: carpeta que YA existe se compara con su nombre real (`.F6\x` negado por
#: `**\.f6\**` si `.f6` existe), y un nombre nuevo, tal cual (`G7.JSON`
#: escrito con `**\g7.json`). Por eso allá van, además de las de `/` (el
#: archivo viaja con el cerebro a Mac/Linux, donde valen esas: quitarlas haría
#: que cada máquina reescriba el archivo de la otra), las de `\` en minúsculas,
#: MAYÚSCULAS y Primera mayúscula. Otra mezcla (`.kIrO`) de una carpeta que
#: aún no existe no se cubre. Un punto final no esquiva: Cursor guarda
#: `f1.json.` y `b1.\x` con el punto (otro archivo, que nadie carga).
def _cursor_variantes(rel):
    """`rel` en minúsculas, MAYÚSCULAS y con la primera letra de cada parte
    en mayúscula (`.claude/settings.json` → `.Claude/Settings.json`), sin
    repetir."""
    def titulo(parte):
        for i, c in enumerate(parte):
            if c.isalpha():
                return parte[:i] + c.upper() + parte[i + 1:]
        return parte
    out = []
    for v in (rel, rel.upper(), "/".join(titulo(p) for p in rel.split("/"))):
        if v not in out:
            out.append(v)
    return out


def _cursor_deny(windows=None):
    """Las reglas `deny` de Cursor (ver arriba). `windows` None = esta
    máquina. Fuera de Windows, las mismas de siempre."""
    import rutas_protegidas as R
    win = (os.name == "nt") if windows is None else bool(windows)
    out = (["Write(**/%s/**)" % d for d in R.CARPETAS]
           + ["Write(**/%s)" % f for f in R.ARCHIVOS + R.EXACTAS])
    if win:
        for d in R.CARPETAS:
            out += ["Write(**\\%s\\**)" % v.replace("/", "\\") for v in _cursor_variantes(d)]
        for f in R.ARCHIVOS + R.EXACTAS:
            out += ["Write(**\\%s)" % v.replace("/", "\\") for v in _cursor_variantes(f)]
    sin_repetir = []
    for r in out:
        if r not in sin_repetir:
            sin_repetir.append(r)
    return tuple(sin_repetir)


CURSOR_DENY = _cursor_deny()
#: La de antes de esta versión (solo `.cursor/`).
CURSOR_DENY_ANTES = ("Write(**/.cursor/**)",)


def cursor_mcp_plantilla(root=None, python=None):
    """`.cursor/mcp.json` TAL CUAL lo deja Workspace. Sin `env`: la
    aprobación de Cursor queda atada a la config YA resuelta (VERIFICADO
    2026.10.22: con `${env:…}` cada pestaña daba otra huella y pedía aprobar
    de nuevo); el servidor sabe su pestaña por la corrida viva."""
    return {"mcpServers": {SERVIDOR: dict(servidor(root, python), type="stdio")}}


def cursor_cli_plantilla():
    """`.cursor/cli.json` TAL CUAL: permitir SOLO las herramientas de memoria
    y negar escribir en `.cursor/` y en la config de los demás motores, git
    y Obsidian (CURSOR_DENY). `deny` va siempre: sin él, Cursor rechaza
    el archivo entero («schema validation failed», VERIFICADO 2026.10.22)."""
    return {"permissions": {"allow": cursor_reglas(), "deny": list(CURSOR_DENY)}}


CURSOR_MCP_REL = ".cursor/mcp.json"
CURSOR_CLI_REL = ".cursor/cli.json"


def _cursor_fusion_mcp(root=None, python=None):
    return (CURSOR_MCP_REL,
            _con_servidor(cursor_mcp_plantilla(root, python)["mcpServers"][SERVIDOR]))


def _cursor_fusion_cli():
    return (CURSOR_CLI_REL, _con_reglas(cursor_cli_plantilla()["permissions"]))


def ensure_cursor_mcp(brain, root=None, python=None, avisos=None):
    """Mete o actualiza NUESTRO servidor en `<cerebro>/.cursor/mcp.json`; los
    del socio quedan (_fusionar). → 'ready' | 'written' | 'restored' | 'blocked'."""
    return _fusionar(brain, [_cursor_fusion_mcp(root, python)], avisos)


def ensure_cursor_permisos(brain, avisos=None):
    """Mete NUESTRAS reglas (allow y deny de cursor_cli_plantilla) en
    `<cerebro>/.cursor/cli.json`; las del socio quedan (ídem)."""
    return _fusionar(brain, [_cursor_fusion_cli()], avisos)


def cursor_aprobar(brain, exe, runner=None, timeout=20):
    """`cursor-agent mcp enable workspace-memoria` en el cerebro: su lista
    local de servidores aprobados (doc: «Add an MCP server to the local
    approved list»). La aprobación queda atada a la config del servidor
    (VERIFICADO 2026.10.22: si cambia el comando o sus argumentos, vuelve a
    pedirla), así que no aprueba lo que alguien escriba después en ese
    mcp.json. No se usa `--approve-mcps`: aprobaría TODOS los servidores,
    también los que un agente haya agregado al cerebro. → bool."""
    import subprocess
    import arbol_procesos   # Windows: al vencer muere el árbol (.cmd → node)
    cmd = [exe, "mcp", "enable", SERVIDOR]
    try:
        if runner is not None:
            r = runner(cmd, cwd=str(brain))
        else:
            env = None
            try:
                import secret_store
                env = secret_store.engine_env()
            except Exception:
                env = None
            kw = {}
            if os.name == "nt":
                kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            else:
                kw["start_new_session"] = True
            r = arbol_procesos.run(cmd, cwd=str(brain), env=env, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace",
                                   timeout=timeout, stdin=subprocess.DEVNULL, **kw)
        return getattr(r, "returncode", 1) == 0
    except Exception:
        return False


def cursor_permisos_sin_herramienta():
    """Lo de `.cursor/cli.json` cuando la herramienta NO quedó: el deny
    (CURSOR_DENY) sin aprobar sus herramientas. `allow` va como lista (vacía
    si no había): Cursor valida el archivo entero."""
    return {"allow": [], "deny": list(CURSOR_DENY)}


def preparar_cursor(brain, exe, root=None, python=None, runner=None, avisos=None):
    """→ True si la herramienta quedó registrada, aprobada y permitida.

    Lo normal: los dos archivos juntos (si uno no se puede tocar, no se
    escribe ninguno). Si `mcp.json` no se puede tocar (un comentario, un
    enlace…), el deny de `cli.json` va POR SU CUENTA, sin aprobar las
    herramientas: el deny no depende de la memoria. Si ni `cli.json` se
    puede, aviso de una línea. Cursor arranca igual que siempre: Workspace
    solo pasa `--trust` (confianza de la carpeta, engines.cursor), jamás
    `--force`/`--yolo`, así que no le agrega autonomía que escriba sin
    preguntar; lo que Cursor haga de fábrica no cambia."""
    if not brain or not os.path.isdir(str(brain)):
        return False
    if _fusionar(brain, [_cursor_fusion_mcp(root, python), _cursor_fusion_cli()],
                 avisos) in LISTO:
        return cursor_aprobar(brain, exe, runner=runner)
    # (sus avisos ya los dio la fusión de arriba: aquí solo si falta el deny)
    if _fusionar(brain, [(CURSOR_CLI_REL, _con_reglas(cursor_permisos_sin_herramienta()))],
                 []) not in LISTO:
        _avisar(avisos, "cursor_sin_deny", CURSOR_CLI_REL)
    return False


def _quitar_lo_nuestro(brain, cambios):
    """Al quitar un agente o desinstalar: saca SOLO lo nuestro de cada
    `(rel, quitar)` (`quitar(data)` → (nuevo, cambio): sin_servidor,
    sin_reglas_cursor). El archivo se borra solo si quedó vacío de verdad
    (esqueleto) y su carpeta solo si quedó vacía; si no, se reescribe con su
    mismo modo. Una ruta con un enlace, o un JSON ilegible, no se toca. →
    [rutas tocadas]."""
    brain = str(brain)
    out, carpetas = [], []
    for rel, quitar in cambios:
        rel = rel.replace("\\", "/")
        path = os.path.join(brain, *rel.split("/"))
        try:
            if _enlace_en_ruta(brain, rel) or not os.path.isfile(path):
                continue
            data, _txt = _leer_json(path)
            new, cambio = quitar(data)
            if not cambio:
                continue
            if esqueleto(new):
                os.remove(path)
                d = os.path.dirname(path)
                if d not in carpetas:
                    carpetas.append(d)
            else:
                _escribir_json(path, new, None)
            out.append(path)
        except (OSError, ValueError, TypeError):
            continue
    for d in carpetas:
        try:
            if not _enlace(d) and os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
        except OSError:
            pass
    return out


def clean_cursor(brain):
    """Quita lo nuestro de `<cerebro>/.cursor/` (servidor y reglas; lo del
    socio queda; un archivo que solo era nuestro se borra, y la carpeta si
    quedó vacía). → [rutas tocadas]."""
    return _quitar_lo_nuestro(brain, ((CURSOR_MCP_REL, sin_servidor),
                                      (CURSOR_CLI_REL, sin_reglas_cursor)))


def sin_servidor(data):
    srv = data.get("mcpServers")
    if not isinstance(srv, dict) or not _es_nuestro(srv.get(SERVIDOR)):
        return data, False
    new = dict(data)
    new["mcpServers"] = {k: v for k, v in srv.items() if k != SERVIDOR}
    return new, True


def sin_reglas_cursor(data):
    perms = data.get("permissions")
    if not isinstance(perms, dict):
        return data, False
    allow, deny = perms.get("allow"), perms.get("deny")
    allow = allow if isinstance(allow, list) else []
    deny = deny if isinstance(deny, list) else []
    nuestras = cursor_cli_plantilla()["permissions"]     # las mismas que mete la fusión
    # + las de la otra plataforma: el cerebro viaja, y una PC con Windows deja
    # las de `\` en un cli.json que luego se limpia en una Mac (y al revés)
    reglas = set(nuestras["allow"])
    negadas = set(nuestras["deny"]) | set(_cursor_deny(True)) | set(_cursor_deny(False))
    if not any(r in reglas for r in allow) and not any(r in negadas for r in deny):
        return data, False
    new = dict(data)
    new["permissions"] = dict(perms, allow=[r for r in allow if r not in reglas],
                              deny=[r for r in deny if r not in negadas])
    return new, True


def esqueleto(data):
    """¿Quedó solo el esqueleto que pusimos nosotros?"""
    for k, v in data.items():
        if k == "mcpServers" and v == {}:
            continue
        if k == "permissions" and isinstance(v, dict) \
                and all(x in ([], None) for x in v.values()):
            continue
        return False
    return True


# · Kiro: su agente `workspace` en el cerebro + `--agent workspace` por corrida ·
def kiro_agente_path(brain):
    """`<cerebro>/.kiro/agents/workspace.json`: agente del PROYECTO (doc de
    Kiro: `.kiro/agents/` del proyecto y `~/.kiro/agents/` globales)."""
    return os.path.join(str(brain), ".kiro", "agents", KIRO_AGENTE + ".json")


def kiro_escribe_sin_preguntar(autonomia):
    """¿El agente escribe en su cerebro sin preguntar? Solo con «brain» (o el
    «full» de antes); «ask» o sin saber → no (como antes de esta versión)."""
    return str(autonomia or "").strip().lower() in KIRO_AUTONOMIAS_LIBRES


def _kiro_denies():
    """(2.x `deniedPaths`, V3 `match` de la regla deny de `fs_write`).

    · Carpeta: 2.x `d` (estilo gitignore: la carpeta y lo de adentro,
      VERIFICADO con `.kiro`) y `d/**`; V3 `./d` («patterns without wildcards
      implicitly match children») y `./d/**` (la forma VERIFICADA con
      `.kiro`).
    · Archivo: `f` y `./f`.
    · Mayúsculas: en macOS y Windows `.KIRO` es `.kiro`. Si Kiro compara la
      ruta tal cual, cada patrón va también con sus letras como clase
      (`.[kK][iI][rR][oO]`; la doc «permissions» acepta clases `[abc]`)."""
    import rutas_protegidas as R
    v2, v3 = [], []
    for d in R.CARPETAS:
        for forma in _kiro_formas(d):
            v2 += [forma, forma + "/**"]
            v3 += ["./" + forma, "./" + forma + "/**"]
    for f in R.ARCHIVOS + R.EXACTAS:
        for forma in _kiro_formas(f):
            v2.append(forma)
            v3.append("./" + forma)
    return _sin_repetir(v2), _sin_repetir(v3)


def _kiro_formas(rel):
    import rutas_protegidas as R
    return [rel, R.sin_mayusculas(rel)] if KIRO_SIN_MAYUSCULAS else [rel]


def _sin_repetir(xs):
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def kiro_agente_config(brain, root=None, python=None, kiro_dir=None, autonomia=None,
                       _negar=None):
    """El agente `workspace`, válido en las DOS líneas de Kiro (doc «agent
    configuration reference», https://kiro.dev/docs/custom-agents/configuration-reference/:
    V3 no usa `allowedTools` ni `toolsSettings`, pero carga el archivo si trae
    `permissions`; 2.x usa sus campos):
      · 2.x (chat V2): `allowedTools` con `@workspace-memoria/<herramienta>`;
      · V3 (de fábrica en 3.x, o `--v3`): `permissions.rules` con la capacidad
        `mcp` y `workspace-memoria/<herramienta>`.
    Ninguna regla de terminal: la memoria ya no va por la terminal. Con
    autonomía «brain» (`autonomia`; la de fábrica), escribir en el cerebro no
    pregunta (KIRO_ESCRIBE: 2.x `allowedPaths`, V3 `allow` de `fs_write`);
    fuera del cerebro pregunta. Con «ask» (o sin saber), pregunta como
    siempre. Y nunca escribe en `.kiro/` del cerebro (donde vive este agente):
    podría darse permisos. VERIFICADO 3.1.0 en vivo (V2 y V3 sin ventana y el
    arranque en un pty: tests/e2e/kiro_permisos.py).
    Los demás campos son los de `kiro-cli agent create --from kiro_default`
    (2.35.2) sin su persona, que competiría con la identidad del cerebro."""
    if kiro_dir is None:
        try:
            from engines import kiro
            kiro_dir = kiro._kiro_dir()
        except Exception:
            kiro_dir = os.path.join(os.path.expanduser("~"), ".kiro")
    b = os.path.abspath(str(brain))
    libre = kiro_escribe_sin_preguntar(autonomia)
    deny_v2, deny_v3 = _negar or _kiro_denies()
    fs_write = {"allowedPaths": [KIRO_ESCRIBE]} if libre else {}
    fs_write["deniedPaths"] = list(deny_v2)
    reglas = [{"capability": "fs_read", "match": ["./**"], "effect": "allow"}]
    if libre:
        reglas.append({"capability": "fs_write", "match": [KIRO_ESCRIBE], "effect": "allow"})
    reglas += [{"capability": "mcp", "match": _reglas(SERVIDOR + "/%s"), "effect": "allow"},
               {"capability": "fs_write", "match": list(deny_v3), "effect": "deny"}]
    return {
        "name": KIRO_AGENTE,
        "description": KIRO_MARCA + " el agente por defecto de Kiro para los cerebros de "
                       "Workspace, con su herramienta de memoria (MCP) aprobada por nombre. Lo "
                       "reescribe Workspace al abrir un agente: no lo edites.",
        "mcpServers": {SERVIDOR: servidor(root, python)},
        "tools": ["*"],
        "allowedTools": _reglas("@" + SERVIDOR + "/%s"),
        "resources": ["file://" + os.path.join(b, "AGENTS.md"),
                      "file://" + os.path.join(b, "README.md"),
                      "skill://" + os.path.join(b, ".kiro", "skills", "*", "SKILL.md"),
                      "skill://" + os.path.join(kiro_dir, "skills", "*", "SKILL.md")],
        # el agente no escribe su propia config, nada de `.kiro/` (agentes,
        # MCP, hooks) ni la config de otro motor, git u Obsidian
        # (rutas_protegidas): 2.x `deniedPaths` (gana al `allowedPaths`) y V3
        # una regla `deny` (gana a cualquier allow). VERIFICADO 3.1.0 (V2 y V3,
        # tests/e2e/kiro_permisos.py).
        "toolsSettings": {"fs_write": fs_write},
        "includeMcpJson": True,
        "model": None,
        "permissions": {"rules": reglas},
    }


def _kiro_es_nuestro(data):
    return isinstance(data, dict) and str(data.get("description") or "").startswith(KIRO_MARCA)


def ensure_kiro_agente(brain, root=None, python=None, avisos=None, autonomia=None):
    """Rehace el agente del cerebro desde la plantilla (lo que no sea eso se
    respalda primero). El de la otra autonomía es nuestro (el socio la cambió
    en Agentes; la de «ask» es también la de la versión anterior): se rehace
    sin respaldo ni aviso. → 'ready' | 'written' | 'restored' | 'blocked'."""
    want = kiro_agente_config(brain, root, python, autonomia=autonomia)
    otra = "ask" if kiro_escribe_sin_preguntar(autonomia) else "brain"
    nuestros = [kiro_agente_config(brain, root, python, autonomia=otra)]
    # la de antes (solo negaba `.kiro`), con las dos autonomías
    antes = (list(KIRO_DENY_V2_ANTES), list(KIRO_DENY_V3_ANTES))
    for a in (autonomia, otra):
        nuestros.append(kiro_agente_config(brain, root, python, autonomia=a, _negar=antes))
    return _rehacer(brain, os.path.join(".kiro", "agents", KIRO_AGENTE + ".json"),
                    want, avisos, nuestros=tuple(nuestros))


def clean_kiro(brain):
    """Borra el agente del cerebro si es nuestro (y las carpetas `.kiro/agents`
    y `.kiro` si quedaron vacías). → [rutas] borradas."""
    path = kiro_agente_path(brain)
    try:
        if _enlace_en_ruta(brain, ".kiro/agents/" + KIRO_AGENTE + ".json") \
                or not os.path.isfile(path):
            return []
        cur, _txt = _leer_json(path)
        if not _kiro_es_nuestro(cur):
            return []
        os.remove(path)
    except (OSError, ValueError):
        return []
    for d in (os.path.dirname(path), os.path.dirname(os.path.dirname(path))):
        try:
            os.rmdir(d)                    # solo si quedó vacía
        except OSError:
            break
    return [path]


#: Opciones con las que el socio elige agente o motor de Kiro: ahí no se pasa
#: `--agent workspace` (su elección gana; la memoria pedirá permiso).
_KIRO_FLAGS_DEL_SOCIO = ("--agent", "--profile", "--v2", "--v3", "--agent-engine",
                         "--legacy-ui", "--classic", "--cloud", "--mode")
#: Líneas de Kiro con las que el agente se verificó (2.x: chat V2; 3.x: V3).
KIRO_LINEAS = (2, 3)


def _kiro_settings(brain=None):
    """chat.* de la config de Kiro: la global y, encima, la del proyecto
    (`<cerebro>/.kiro/settings/cli.json`; doc: `kiro-cli settings` global o
    del workspace)."""
    out = {}
    cands = []
    try:
        from engines import kiro
        cands.append(kiro.settings_path())
    except Exception:
        cands.append(os.path.join(os.path.expanduser("~"), ".kiro", "settings", "cli.json"))
    if brain:
        cands.append(os.path.join(str(brain), ".kiro", "settings", "cli.json"))
    for p in cands:
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                out.update(data)
        except (OSError, ValueError):
            continue
    return out


def kiro_usa_agente(passthrough=(), version=None, settings=None, brain=None):
    """¿Va `--agent workspace`? Con Kiro 2.x y 3.x (el agente sirve en las dos
    líneas) y si el socio no eligió agente ni motor (opción, o
    `chat.defaultAgent` / `chat.agentEngine` en su config)."""
    try:
        if not version or int(version[0]) not in KIRO_LINEAS:
            return False
    except (TypeError, ValueError, IndexError):
        return False
    for a in passthrough or ():
        a = str(a)
        if any(a == f or a.startswith(f + "=") for f in _KIRO_FLAGS_DEL_SOCIO):
            return False
    s = _kiro_settings(brain) if settings is None else settings
    if str(s.get("chat.defaultAgent") or "").strip():
        return False
    eng = str(s.get("chat.agentEngine") or "").strip().lower()
    return eng in ("", "v2", "v3")


def preparar_kiro(brain, passthrough=(), version=None, root=None, python=None, avisos=None,
                  autonomia=None):
    """→ argumentos extra (`--agent workspace`) o [] (el socio eligió, o no se
    pudo escribir: la memoria pedirá permiso, como antes). El agente del
    cerebro se rehace también cuando no se elige, si ya existe: el socio lo
    puede elegir a mano y no debe correr con algo que alguien le cambió.
    `autonomia` = la del agente (engines/_ui.autonomy): con «brain», escribir
    en el cerebro no pregunta."""
    if not brain or not os.path.isdir(str(brain)):
        return []
    usa = kiro_usa_agente(passthrough, version, brain=brain)
    if not usa and not os.path.lexists(kiro_agente_path(brain)):
        return []
    if ensure_kiro_agente(brain, root, python, avisos, autonomia=autonomia) not in LISTO \
            or not usa:
        return []
    return ["--agent", KIRO_AGENTE]


# · Antigravity (agy): servidor en `.agents/` del cerebro + permisos POR CORRIDA ·
# Doc de Google, https://antigravity.google/docs/mcp/ : el CLI carga los
# servidores de `<workspace>/.agents/mcp_config.json` (y del global
# ~/.gemini/config/mcp_config.json, que no se toca) y una herramienta se
# aprueba por nombre con `mcp(server/tool)`. Doc de permisos
# (https://antigravity.google/docs/permissions?tab=cli): deny > ask > allow, y
# `write_file(<carpeta>)` cubre lo que tiene adentro. `agy --help` (1.5.1):
# `--settings` = «Settings for this session only, never saved».
# VERIFICADO en caja negra (agy 1.5.1, --print, cerebro temporal):
#   · el servidor de `.agents/mcp_config.json` arranca como HIJO de agy y hereda
#     su entorno (la corrida viva y WORKSPACE_* le llegan);
#   · `mcp(<servidor>/<herramienta>)` en el `--settings` la corre sin preguntar;
#     otra herramienta del mismo servidor se niega;
#   · `permissions` del `--settings` REEMPLAZA el `permissions` del settings.json
#     global en esa sesión (no se mezclan): por eso la corrida lleva las reglas
#     del socio tal cual + las nuestras;
#   · `deny: write_file(<cerebro>/.agents)` impide que el agente reescriba esa
#     config (y la de hooks que agy lee de ahí), y escribir en el resto del
#     cerebro sigue igual. Va igual para la config de los DEMÁS motores, git
#     y Obsidian (rutas_protegidas): agy escribe en su carpeta sin preguntar
#     de fábrica (doc de permisos: «Workspace writes are allowed»).
#: Config del servidor, relativa al cerebro.
AGY_MCP_REL = ".agents/mcp_config.json"
#: Regla de agy para una herramienta (doc «mcp(server/tool)»).
AGY_REGLA = "mcp(" + SERVIDOR + "/%s)"
#: Opción con la que el socio pasa su propio `--settings`: entonces no va el
#: nuestro (agy toma uno) y la memoria pide permiso.
_AGY_FLAG_SETTINGS = "--settings"


def agy_mcp_path(brain):
    return os.path.join(str(brain), *AGY_MCP_REL.split("/"))


def agy_mcp_plantilla(root=None, python=None):
    """`.agents/mcp_config.json` TAL CUAL lo deja Workspace. Sin `env`: el
    servidor sabe su pestaña por la corrida viva (agy lo lanza como hijo)."""
    return {"mcpServers": {SERVIDOR: servidor(root, python)}}


def agy_reglas():
    return _reglas(AGY_REGLA)


def agy_deny(brain):
    """Lo que el agente no escribe: la carpeta `.agents/` del cerebro y la
    config de los demás motores, git y Obsidian (rutas_protegidas), con la
    ruta real, como las demás reglas de agy de Workspace. Doc
    https://antigravity.google/docs/permissions?tab=cli: `write_file(<carpeta>)`
    cubre lo de adentro; en Windows agy pasa `\\` a `/` y quita la unidad.
    LÍMITE (sin verificar: agy no acepta comodines y no se prueba sin
    cuenta): la ruta va tal cual, en minúsculas; no se sabe si agy compara
    sin mayúsculas (`.KIRO` = `.kiro` en macOS y Windows) ni qué hace con un
    punto o espacio al final del nombre en Windows."""
    import rutas_protegidas as R
    real = os.path.realpath(str(brain))
    orden = [".agents"] + [r for r in R.CARPETAS + R.ARCHIVOS + R.EXACTAS if r != ".agents"]
    return _sin_repetir(["write_file(%s)" % os.path.join(real, *r.split("/")) for r in orden])


def ensure_agy_mcp(brain, root=None, python=None, avisos=None):
    """Mete o actualiza NUESTRO servidor en `<cerebro>/.agents/mcp_config.json`;
    los servidores del socio quedan tal cual (_fusionar). → 'ready' |
    'written' | 'restored' | 'blocked'."""
    return _fusionar(brain, [(AGY_MCP_REL, _con_servidor(
        agy_mcp_plantilla(root, python)["mcpServers"][SERVIDOR]))], avisos)


def agy_settings_path(brain):
    """El `--settings` de la corrida (estado de Workspace, fuera del cerebro y
    de ~/.gemini): uno por cerebro."""
    import hashlib
    import paths
    clave = hashlib.sha256(os.path.normcase(os.path.realpath(str(brain))).encode("utf-8")).hexdigest()[:16]
    return os.path.join(paths.state_dir(), "agy-settings", clave + ".json")


def _agy_global(settings_path=None):
    if settings_path:
        return settings_path
    try:
        from engines import antigravity
        return os.path.join(antigravity._agy_home(), "settings.json")
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli", "settings.json")


def agy_settings(brain, settings_path=None, mcp=True):
    """El `--settings` de la corrida: `permissions` del settings.json global del
    socio TAL CUAL (su `--settings` lo reemplaza en la sesión) + permitir las
    tres herramientas (solo con `mcp`: el servidor quedó registrado) + negar
    escribir `.agents/` y las rutas protegidas (agy_deny, SIEMPRE). Solo lee el
    global (permisos, jamás credenciales: agy las guarda en el llavero del
    sistema). None si el global no se puede leer o su `permissions` no es un
    objeto: no se arma un reemplazo que perdería las reglas del socio."""
    p = _agy_global(settings_path)
    try:
        if os.path.islink(p):
            return None
        if os.path.exists(p) and os.path.getsize(p) > 1024 * 1024:
            return None
        data, _txt = _leer_json(p)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    perms = data.get("permissions", {})
    if not isinstance(perms, dict):
        return None
    perms = dict(perms)
    for clave, nuestras in (("allow", agy_reglas() if mcp else []), ("deny", agy_deny(brain))):
        cur = perms.get(clave)
        if cur is None:
            cur = []
        if not isinstance(cur, list):
            return None
        perms[clave] = list(cur) + [r for r in nuestras if r not in cur]
    return {"permissions": perms}


def _preparar_antigravity(brain, passthrough=(), root=None, python=None, avisos=None,
                          settings_path=None):
    """→ (args, herramienta lista). `args` = `["--settings", <archivo>]` con
    el deny de las rutas protegidas (agy_deny) aunque la herramienta NO haya
    quedado (`.agents` es un enlace, su JSON no se entiende…): entonces va sin
    aprobar sus herramientas y la memoria pide permiso, pero el deny sigue.
    [] solo si no se puede armar ningún `--settings` con el deny: el socio
    pasó el suyo (agy toma uno), su settings.json global no se puede leer
    (un enlace, roto, enorme) o no se pudo escribir el de la corrida. Con []
    el lanzador NO pasa `--mode accept-edits` (engines.antigravity: sin deny,
    que pregunte). Con el `--settings` del socio no se toca
    `.agents/mcp_config.json` (es su corrida); tampoco si su settings.json
    global no se puede leer (no habría corrida que lo use)."""
    if not brain or not os.path.isdir(str(brain)):
        return [], False
    propio = any(str(a) == _AGY_FLAG_SETTINGS or str(a).startswith(_AGY_FLAG_SETTINGS + "=")
                 for a in passthrough or ())
    if propio:
        return [], False
    if agy_settings(brain, settings_path) is None:
        return [], False
    listo = ensure_agy_mcp(brain, root, python, avisos) in LISTO
    data = agy_settings(brain, settings_path, mcp=listo)
    if data is None:
        return [], False
    path = agy_settings_path(brain)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _escribir_json(path, data, 0o600)
    except (OSError, ValueError, TypeError):
        return [], False
    return [_AGY_FLAG_SETTINGS, path], listo


def preparar_antigravity(brain, passthrough=(), root=None, python=None, avisos=None,
                         settings_path=None):
    """→ `["--settings", <archivo>]` de la corrida (con el deny siempre; con la
    herramienta aprobada solo si quedó registrada), o [] (ver
    _preparar_antigravity)."""
    return _preparar_antigravity(brain, passthrough, root, python, avisos, settings_path)[0]


def agy_con_deny(args):
    """¿Los argumentos de preparar("antigravity") llevan nuestro `--settings`
    (y con él, el deny de las rutas protegidas)?"""
    return _AGY_FLAG_SETTINGS in [str(a) for a in args or ()]


def clean_agy(brain):
    """Quita nuestro servidor de `<cerebro>/.agents/mcp_config.json` (los del
    socio quedan; si solo traía el nuestro, se borra, y `.agents/` si quedó
    vacía; un `.agents` que es un enlace no se toca). → [rutas tocadas]."""
    return _quitar_lo_nuestro(brain, ((AGY_MCP_REL, sin_servidor),))


def preparar(motor, brain="", exe="", passthrough=(), version=None, autonomia=None):
    """Al abrir un agente en `motor` (antes del bloque de la pestaña):
    registra la herramienta y aprueba SOLO sus herramientas por la vía
    documentada de ese motor, y retira la aprobación vieja del shim. → los
    argumentos EXTRA para su CLI (Copilot, Kiro) o []. `autonomia` = la del
    agente (Kiro: con «brain», escribir en el cerebro no pregunta). Marca la
    corrida (ENV_ACTIVO) solo si quedó lista. Falla-suave: nunca tumba un arranque
    (sin herramienta, la memoria usa `workspace memoria …` y el motor pide
    permiso)."""
    _marcar("")
    try:
        import memoria_permiso
        memoria_permiso.retirar_aprobaciones(motor)
    except Exception:
        pass
    if motor not in MOTORES:
        return []
    extra, listo, avisos = [], False, []
    try:
        if motor == "copilot":
            extra = preparar_copilot(passthrough)
            listo = True
        elif motor == "cursor":
            listo = preparar_cursor(brain, exe, avisos=avisos)
        elif motor == "kiro":
            extra = preparar_kiro(brain, passthrough, version, avisos=avisos,
                                  autonomia=autonomia)
            listo = bool(extra)
        elif motor == "antigravity":
            extra, listo = _preparar_antigravity(brain, passthrough, avisos=avisos)
    except Exception:
        extra, listo = [], False
    _AVISOS.extend(avisos)
    _marcar(motor if listo else "")
    return extra


#: Avisos de la última preparación (una línea cada uno): el lanzador los
#: imprime DESPUÉS del banner, que limpia la pantalla.
_AVISOS = []


def avisos():
    """Los avisos pendientes (y los olvida)."""
    out = list(_AVISOS)
    del _AVISOS[:]
    return out


def plan_line(motor, brain="", passthrough=(), version=None, autonomia=None):
    """Una línea para el plan de arranque (solo lee)."""
    if motor == "copilot":
        return ("herramienta MCP `%s` por corrida: `%s` (sin terminal; nada escrito en "
                "~/.copilot)" % (SERVIDOR, " ".join(copilot_args())))
    if motor == "cursor":
        mcp, cli = cursor_paths(brain or "<cerebro>")
        return ("herramienta MCP `%s`: servidor en %s, `%s` y `%s` (+%d rutas de la config de "
                "los motores, git y Obsidian) en %s y `cursor-agent mcp enable %s` (aprueba "
                "solo ese servidor); al abrir se agrega solo lo de Workspace y lo tuyo de esos "
                "archivos queda"
                % (SERVIDOR, mcp, "Mcp(%s:…)" % SERVIDOR, CURSOR_DENY[0],
                   len(_cursor_deny(False)) - 1, cli, SERVIDOR))
    if motor == "kiro":
        if kiro_usa_agente(passthrough, version, brain=brain or None):
            escribe = ("escribe en el cerebro sin preguntar (`%s`), fuera pregunta; "
                       % KIRO_ESCRIBE if kiro_escribe_sin_preguntar(autonomia) else
                       "pregunta antes de escribir (autonomía «ask»); ")
            return ("herramienta MCP `%s` con el agente `%s` (%s) por corrida; %sno escribe "
                    "`.kiro/` ni la config de los otros motores, git u Obsidian; se rehace al "
                    "abrir"
                    % (SERVIDOR, KIRO_AGENTE, kiro_agente_path(brain or "<cerebro>"), escribe))
        return ("`workspace memoria …` pidiendo permiso: elegiste agente/motor de Kiro o no es "
                "la línea 2 ni la 3")
    if motor == "antigravity":
        if any(str(a) == _AGY_FLAG_SETTINGS or str(a).startswith(_AGY_FLAG_SETTINGS + "=")
               for a in passthrough or ()):
            return ("`workspace memoria …` pidiendo permiso: pasaste tu propio --settings")
        return ("herramienta MCP `%s`: servidor en %s y, por corrida, `--settings` con `%s` "
                "y `deny %s` (+%d rutas de la config de los motores, git y Obsidian; tus "
                "reglas de agy van tal cual); al abrir se agrega solo nuestro servidor y los "
                "tuyos quedan"
                % (SERVIDOR, agy_mcp_path(brain or "<cerebro>"), AGY_REGLA % "…",
                   agy_deny(brain or "<cerebro>")[0], len(agy_deny(brain or "<cerebro>")) - 1))
    return ""


def solo_de_workspace(brain, carpeta):
    """¿La carpeta `.cursor` o `.kiro` del cerebro trae SOLO lo que escribe
    este módulo (sin nada del socio)? Para que el aviso de «archivos de un
    motor en la raíz» (brain_identity) no salte por la herramienta."""
    raiz = os.path.join(str(brain), carpeta)
    try:
        if carpeta == ".cursor":
            mcp, cli = cursor_paths(brain)
            if set(os.listdir(raiz)) - {"mcp.json", "cli.json"}:
                return False
            for path, quitar in ((mcp, sin_servidor), (cli, sin_reglas_cursor)):
                if os.path.exists(path):
                    data, _txt = _leer_json(path)
                    new, cambio = quitar(data)
                    if not cambio or not esqueleto(new):
                        return False
            return True
        if carpeta == ".kiro":
            if os.listdir(raiz) != ["agents"] \
                    or os.listdir(os.path.join(raiz, "agents")) != [KIRO_AGENTE + ".json"]:
                return False
            data, _txt = _leer_json(kiro_agente_path(brain))
            return _kiro_es_nuestro(data)
    except (OSError, ValueError, TypeError):
        return False
    return False


def limpiar_cerebro(brain):
    """Al quitar un agente (o desinstalar): lo que este módulo escribió en el
    cerebro (`.cursor/`, `.kiro/agents/` y `.agents/mcp_config.json`). → [rutas
    tocadas]."""
    if not brain or not os.path.isdir(str(brain)):
        return []
    return clean_cursor(brain) + clean_kiro(brain) + clean_agy(brain)


# ── JSON-RPC ────────────────────────────────────────────────────────────────
def _log(msg):
    try:
        sys.stderr.write("%s: %s\n" % (SERVIDOR, msg))
        sys.stderr.flush()
    except Exception:
        pass


def _error(mid, code, msg):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": msg}}


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def atender(msg, env=None, cadena=None):
    """Un mensaje JSON-RPC (ya decodificado) → respuesta (dict) o None si es
    una notificación. Nunca lanza."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(msg.get("id") if isinstance(msg, dict) else None, -32600,
                      "Invalid Request")
    metodo = msg.get("method")
    notificacion = "id" not in msg
    mid = msg.get("id")
    if not isinstance(metodo, str):
        # una respuesta del cliente (no le pedimos nada) o basura: se ignora
        return None if notificacion or "result" in msg or "error" in msg else \
            _error(mid, -32600, "Invalid Request")
    if notificacion:
        return None                     # initialized, cancelled, …: nada que responder
    params = msg.get("params")
    if params is not None and not isinstance(params, dict):
        return _error(mid, -32602, "params tiene que ser un objeto")
    params = params or {}
    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        version = pedida if pedida in PROTOCOLOS else PROTOCOLOS[0]
        return _ok(mid, {"protocolVersion": version,
                         "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": {"name": SERVIDOR, "title": "Memoria de Workspace",
                                        "version": VERSION},
                         "instructions": INSTRUCCIONES})
    if metodo == "ping":
        return _ok(mid, {})
    if metodo == "tools/list":
        try:
            return _ok(mid, {"tools": herramientas()})
        except Exception as e:
            _log("tools/list: %s: %s" % (type(e).__name__, e))
            return _error(mid, -32603, "Internal error")
    if metodo == "tools/call":
        nombre = params.get("name")
        if nombre not in _LLAMAR:
            return _error(mid, -32602, "Herramienta desconocida: %r (hay: %s)"
                          % (nombre, ", ".join(HERRAMIENTAS)))
        texto, es_error = llamar(nombre, params.get("arguments"), env, cadena)
        return _ok(mid, {"content": [{"type": "text", "text": texto}], "isError": es_error})
    return _error(mid, -32601, "Method not found: %s" % metodo)


def procesar_linea(linea, env=None, cadena=None):
    """Una línea de stdin (bytes o str) → respuesta (dict) o None."""
    if isinstance(linea, bytes):
        if len(linea) > MAX_LINEA:
            return _error(None, -32600, "mensaje demasiado grande")
        linea = linea.decode("utf-8", "replace")
    linea = linea.strip()
    if not linea:
        return None
    if len(linea) > MAX_LINEA:
        return _error(None, -32600, "mensaje demasiado grande")
    try:
        msg = json.loads(linea)
    except ValueError:
        return _error(None, -32700, "Parse error")
    if isinstance(msg, list):                    # lotes: fuera del protocolo actual
        return _error(None, -32600, "Invalid Request (sin lotes)")
    try:
        return atender(msg, env, cadena)
    except Exception as e:                       # defensa: nunca un traceback
        _log("%s: %s" % (type(e).__name__, e))
        return _error(msg.get("id") if isinstance(msg, dict) else None, -32603,
                      "Internal error")


def servir(entrada=None, salida=None):
    """El bucle stdio: una línea de JSON por mensaje, hasta EOF."""
    entrada = entrada or sys.stdin.buffer
    salida = salida or sys.stdout.buffer
    # Lo que se imprima por error (un print de un módulo) no ensucia el
    # protocolo: stdout de Python apunta a stderr; el protocolo va por `salida`.
    sys.stdout = sys.stderr
    while True:
        try:
            linea = entrada.readline(MAX_LINEA + 1)
        except KeyboardInterrupt:
            return 0
        except Exception:
            return 0
        if not linea:
            return 0
        if len(linea) > MAX_LINEA and not linea.endswith(b"\n"):
            # el resto de esa línea se descarta
            while True:
                resto = entrada.readline(MAX_LINEA + 1)
                if not resto or resto.endswith(b"\n"):
                    break
        resp = procesar_linea(linea)
        if resp is None:
            continue
        try:
            salida.write(json.dumps(resp, ensure_ascii=False).encode("utf-8") + b"\n")
            salida.flush()
        except Exception:
            return 0


def main(argv=None):
    try:
        return servir()
    except KeyboardInterrupt:
        return 0
    except Exception as e:                       # pragma: no cover — defensa
        _log("%s: %s" % (type(e).__name__, e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
