"""Lo que ningún motor lee por el hook de Workspace (F7): llaves y secretos (y la ficha, el turno y las fotos del monito
de escritorio: con ellos cualquier agente podría pedirle a su app que mire tu pantalla).

Antes de cada herramienta (momento pre_tool) el lanzador mira su entrada: si va a LEER un archivo de secretos
(`.env`, `*.key`, `*.pem`, una llave SSH privada, `.netrc`, la bóveda de Workspace, un llavero) o a pedirle un
valor al llavero del sistema (`security find-generic-password`, `secret-tool lookup`…), se niega con el motivo.
Las herramientas de escribir o editar no se miran (un agente puede crear su `.env.example`); por la terminal
cuenta cualquier mención de esos archivos. Los patrones (`*.env`) no son lecturas.

Solo stdlib y sin Workspace: corre aunque el harness no esté. Si algo falla aquí, deja pasar (el hook jamás
frena al motor por un error suyo)."""
import json
import os
import re
import shlex

#: Herramientas que escriben o cambian (no leen el archivo para el modelo): no se miran.
_ESCRIBE = re.compile(r"(?i)(write|edit|create|patch|replace|notebook|todo|delete|remove|move|rename|mkdir)")
#: Las claves donde los motores ponen la entrada de la herramienta (y, en Cursor, la ruta o el comando sueltos).
_ENTRADA = ("tool_input", "toolInput", "input", "args", "arguments", "toolArgs", "parameters", "params")
_SUELTAS = ("file_path", "filePath", "path", "command")
_ENV_PERMITIDOS = (".env.example", ".env.sample", ".env.template", ".env.dist", ".env.defaults")
_EXT_LLAVE = (".key", ".pem", ".p12", ".pfx", ".jks", ".keystore", ".keychain", ".keychain-db")
_LLAVES_SSH = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "id_ecdsa_sk", "id_ed25519_sk")
_CREDENCIALES = (".netrc", "_netrc", ".pgpass", ".git-credentials")
#: Del monito de escritorio (<estado>/escritorio/): su ficha, el turno abierto, la carpeta de sus fotos (miradas/) y lo
#: de actuar (A0): tus vetados, tus confianzas, sus ajustes y la bitácora de acciones (acciones/).
_MONITO = ("manos.json", "turno.json", "vetados.json", "confianzas.json", "ajustes.json")
_MONITO_DIR = "/workspace/escritorio/"
MONITO = "la ficha o las fotos de Workspace Compañero"
_LLAVERO = {"security": ("find-generic-password", "find-internet-password", "dump-keychain", "export"),
            "secret-tool": ("lookup", "search"), "keyring": ("get",), "get-storedcredential": ("",)}
_GLOB = re.compile(r"[*?\[\]{}]")
_MAX_TEXTOS, _MAX_TEXTO = 64, 20000
#: Las herramientas que solo listan nombres: un patrón ahí no lee nada (en la terminal o en Grep, sí).
_LISTA = re.compile(r"(?i)^(glob|ls|list|list_dir|list_directory|file_search|find_files)$")
#: Un comodín que alcanza a un archivo de secretos (`cat .env*`, `grep -r KEY --include=*.pem`, Grep con
#: glob «.env*»): lleva una de estas pistas y calza con uno de estos nombres.
_PISTAS = (".env", "id_", ".key", ".pem", ".p12", ".pfx", "netrc", "credential", "keychain", "secrets")
_MUESTRAS = (".env", ".env.local", ".env.production", "server.key", "cert.pem", "id_rsa", "id_ed25519", ".netrc",
             ".git-credentials", "credentials", "secrets.local", "login.keychain-db")


def _como_dict(v):
    if isinstance(v, str) and v.strip()[:1] in "{[":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def entrada(payload):
    """La entrada de la herramienta, como la mande su motor (dict, o lo que haya)."""
    p = payload if isinstance(payload, dict) else {}
    for k in _ENTRADA:
        if k in p:
            return _como_dict(p[k])
    for k in ("toolCall", "tool_call"):
        llamada = p.get(k)
        if isinstance(llamada, dict):
            for kk in ("input", "arguments", "args"):
                if kk in llamada:
                    return _como_dict(llamada[kk])
    return {k: p[k] for k in _SUELTAS if isinstance(p.get(k), str)}


def nombre(payload):
    p = payload if isinstance(payload, dict) else {}
    n = p.get("tool_name") or p.get("toolName") or p.get("tool") or ""
    llamada = p.get("toolCall") or p.get("tool_call")
    if not n and isinstance(llamada, dict):
        n = llamada.get("name") or ""
    return str(n)


def _textos(v, out):
    if len(out) >= _MAX_TEXTOS:
        return out
    if isinstance(v, str):
        out.append(v[:_MAX_TEXTO])
    elif isinstance(v, dict):
        for x in v.values():
            _textos(x, out)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _textos(x, out)
    return out


def _ruta(token, home):
    """El motivo si `token` es la ruta de un secreto, o ''."""
    t = token.strip().strip("'\"").lstrip("<>").rstrip(";,)")
    if not t or _GLOB.search(t) or "\n" in t:
        return ""
    if t.startswith("~"):
        t = home + t[1:]
    norm = t.replace("\\", "/").rstrip("/")
    base = norm.rsplit("/", 1)[-1].lower()
    bajo = "/" + norm.lower()
    if base == ".env" or (base.startswith(".env.") and base not in _ENV_PERMITIDOS):
        return "un archivo .env (secretos)"
    if base.endswith(_EXT_LLAVE) or "/library/keychains/" in bajo:
        return "una llave o un llavero (%s)" % base
    if base in _LLAVES_SSH:
        return "una llave SSH privada (%s)" % base
    if base in _CREDENCIALES or bajo.endswith("/.aws/credentials"):
        return "credenciales (%s)" % base
    if base.startswith("secrets.local") or "/workspace/boveda" in bajo:
        return "la bóveda de llaves de Workspace"
    if _MONITO_DIR in bajo + "/" and (base in _MONITO or (bajo + "/").find(_MONITO_DIR + "miradas/") >= 0
                                      or (bajo + "/").find(_MONITO_DIR + "acciones/") >= 0):
        return MONITO
    return ""


def _patron(token):
    """El motivo si `token` es un comodín que alcanza a un archivo de secretos, o ''."""
    import fnmatch
    t = token.strip().strip("'\"").replace("\\", "/").rstrip("/")
    if not _GLOB.search(t):
        return ""
    if _MONITO_DIR in "/" + t.lower() + "/":
        return MONITO
    base = t.rsplit("/", 1)[-1].lower().split("=", 1)[-1]
    if any(p in base for p in _PISTAS) and any(fnmatch.fnmatchcase(m, base) for m in _MUESTRAS):
        return "archivos de secretos con un comodín (%s)" % base
    return ""


def _llavero(tokens):
    nombres = [os.path.basename(x).lower() for x in tokens]
    for i, n in enumerate(nombres):
        if n in _LLAVERO:
            subs = _LLAVERO[n]
            if "" in subs or any(s in nombres[i + 1:i + 3] for s in subs):
                return "pedirle un valor al llavero del sistema (%s)" % n
    return ""


def _tokens(texto):
    try:
        return shlex.split(texto, posix=True)
    except ValueError:
        return texto.split()


def motivo(payload, env=None):
    """Por qué se niega esta herramienta ('' = puede seguir). Nunca levanta."""
    try:
        env = os.environ if env is None else env
        herramienta = nombre(payload)
        if _ESCRIBE.search(herramienta):
            return ""
        lista = bool(_LISTA.match(herramienta.strip()))
        home = env.get("HOME") or env.get("USERPROFILE") or os.path.expanduser("~")
        for texto in _textos(entrada(payload), []):
            m = _ruta(texto, home) or ("" if lista else _patron(texto))   # entera (con espacios: «TURING - BRAIN/.env»)
            if m:
                return m
            # «\» de Windows como «/»: en modo posix, shlex se las comía (`type C:\proj\.env`, `Get-Content .\.env`)
            partes = [texto] if " " not in texto.strip() else _tokens(texto.replace("\\", "/"))
            m = _llavero(partes)
            if m:
                return m
            for tk in partes:
                for pieza in re.split(r"[|;&()<>]", tk) + re.split(r"[|;&()<>=]", tk):
                    m = _ruta(pieza, home) or ("" if lista else _patron(pieza))
                    if m:
                        return m
        return ""
    except Exception:
        return ""


#: A1 · lo del monito que ningún agente CAMBIA: sus ajustes («Puede hacer cosas en mi Mac» se prende en el menú del
#: monito, no escribiendo un archivo), sus vetados y confianzas, su ficha, el turno y su bitácora de acciones.
MONITO_CAMBIAR = "lo de Workspace Compañero (sus ajustes, vetados, confianzas, su ficha o su bitácora)"
#: Las claves donde las herramientas de escribir ponen la ruta (y los encabezados de un parche, como el de Codex).
_RUTAS_ESCRIBIR = ("file_path", "filePath", "path", "notebook_path", "target_file", "targetFile", "file", "filename",
                   "destination", "new_path", "old_path", "source", "target")
_PARCHE = re.compile(r"\*\*\* (?:Add|Update|Delete) File: ([^\n]+)|\*\*\* Move to: ([^\n]+)")


def _ruta_monito(token, home):
    """MONITO_CAMBIAR si `token` es la ruta de lo de actuar del monito (<estado>/escritorio/…), o ''."""
    t = str(token or "").strip().strip("'\"")
    if not t or "\n" in t:
        return ""
    if t.startswith("~"):
        t = home + t[1:]
    norm = t.replace("\\", "/").rstrip("/")
    bajo = "/" + norm.lower()
    if _MONITO_DIR not in bajo + "/":
        return ""
    base = norm.rsplit("/", 1)[-1].lower()
    if base in _MONITO or (bajo + "/").find(_MONITO_DIR + "acciones/") >= 0:
        return MONITO_CAMBIAR
    return ""


def motivo_escribir(payload, env=None):
    """Por qué se niega una herramienta que ESCRIBE (Write, Edit, apply_patch…) en lo de actuar del monito ('' = puede
    seguir): «Puede hacer cosas en mi Mac» se prende en su menú, no escribiendo su archivo. Lo demás se escribe como
    siempre. Nunca levanta."""
    try:
        env = os.environ if env is None else env
        if not _ESCRIBE.search(nombre(payload)):
            return ""
        home = env.get("HOME") or env.get("USERPROFILE") or os.path.expanduser("~")
        e = entrada(payload)
        rutas = [e.get(k) for k in _RUTAS_ESCRIBIR] if isinstance(e, dict) else []
        if isinstance(e, str):
            rutas.append(e)
        for texto in _textos(e, []):
            for m in _PARCHE.finditer(texto):
                rutas.append(m.group(1) or m.group(2))
        for r in rutas:
            if isinstance(r, str) and _ruta_monito(r, home):
                return MONITO_CAMBIAR
        return ""
    except Exception:
        return ""


def negar(destino, texto):
    """Lo que se le devuelve al motor para negar (stdout; además sale con 2 y el motivo en stderr, que es lo
    que leen Claude Code, Codex, Copilot, Kiro y los que copian su forma)."""
    if destino == "cursor":
        return {"permission": "deny", "user_message": texto, "agent_message": texto}
    if destino in ("claude", "codex"):
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": texto}}
    if destino == "hermes":                     # su doc de hooks: {"decision": "block", "reason": …} (y exit 2)
        return {"decision": "block", "reason": texto}
    return {}
