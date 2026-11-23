"""WORKSPACE · control/entorno.py — el entorno con el que la capa de control
arranca a un motor (o a su servidor).

Por qué (punto F, prueba real desde la página, 18-nov): el servidor de la
página corre DENTRO de una pestaña de Workspace y sus variables de identidad
(WORKSPACE_WS, ZENITH_WID, CLAUDE_CODE_SESSION_ID…) pasaban tal cual al motor.
El `claude -p` de la página escribió la maleta en la pestaña equivocada.

Aquí: se QUITAN todas las variables de identidad de otra pestaña o de otra
sesión de Claude Code, y se ponen A PROPÓSITO las de la pestaña de la página
(`pestana`): WORKSPACE_WS / WORKSPACE_WID, las del agente (<AGENTE>_WS /
<AGENTE>_WID, como engines/claude_code.session_env_names), WORKSPACE_AGENT_NAME,
WORKSPACE_BRAIN, WORKSPACE_ENGINE y WORKSPACE_SESSION_ENGINE. Lo demás del entorno (PATH, idioma, el
login del motor) queda igual."""
import os
import re

#: Variables de identidad que NUNCA se heredan (nombres exactos).
EXACTAS = {"WORKSPACE_SESSION_ID", "WORKSPACE_SESSION_PID", "CLAUDE_CODE_SESSION_ID",
           "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PID",
           "WORKSPACE_BRAIN", "WORKSPACE_ENGINE", "WORKSPACE_SESSION_ENGINE"}
#: …ni las que empiezan así.
PREFIJOS = ("WORKSPACE_AGENT_", "CLAUDE_CODE_MESSAGING_")
#: …ni las de pestaña de cualquier agente: <AGENTE>_WS y <AGENTE>_WID (WORKSPACE_WS,
#: ZENITH_WID, TURING_WS…), las que escribe el lanzador; también de agentes con «_», «-» o
#: un dígito en el nombre (MI_AGENTE_WS, MI-AGENTE_WID, 2B_WS).
_PESTANA = re.compile(r"^[A-Z0-9][A-Z0-9_-]*_(WS|WID)$")


def es_identidad(nombre):
    return (nombre in EXACTAS or nombre.startswith(PREFIJOS) or bool(_PESTANA.match(nombre)))


def limpio(base=None):
    """El entorno (por defecto, el de este proceso) sin variables de identidad."""
    return {k: v for k, v in (os.environ if base is None else base).items() if not es_identidad(k)}


def de_pestana(pestana, motor=None):
    """Las variables de la pestaña de la página. `pestana`: {"ws": nombre,
    "wid": id, "agente": nombre del agente, "cerebro": ruta, y opcionales
    "session_env"/"wid_env" si el agente usa nombres propios}."""
    p = dict(pestana or {})
    out = {}
    if p.get("ws"):
        out["WORKSPACE_WS"] = str(p["ws"])
    if p.get("wid"):
        out["WORKSPACE_WID"] = str(p["wid"])
    agente = str(p.get("agente") or "").strip()
    if agente:
        out["WORKSPACE_AGENT_NAME"] = agente
        up = agente.upper()
        if p.get("ws"):
            out[p.get("session_env") or up + "_WS"] = str(p["ws"])
        if p.get("wid"):
            out[p.get("wid_env") or up + "_WID"] = str(p["wid"])
    if p.get("cerebro"):
        out["WORKSPACE_BRAIN"] = str(p["cerebro"])
    if motor:                       # como engines.mark_session_engine: las dos con el mismo motor
        out["WORKSPACE_ENGINE"] = motor
        out["WORKSPACE_SESSION_ENGINE"] = motor
    return out


#: Lo que el motor necesita SIEMPRE, aunque se limpie la identidad (punto H): el
#: probador real vio a Kiro por ACP sin TMPDIR ni SHELL no terminar de abrir.
BASICAS = ("HOME", "PATH", "TMPDIR", "SHELL", "USER", "LOGNAME", "LANG")


def _por_defecto(nombre):
    """El valor del sistema para una básica que falta en todos lados."""
    import getpass
    import tempfile
    if nombre == "HOME":
        return os.path.expanduser("~")
    if nombre == "PATH":
        return os.defpath
    if nombre == "TMPDIR":
        return tempfile.gettempdir()
    if nombre == "SHELL":
        try:
            import pwd
            return pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"
        except (ImportError, KeyError, AttributeError):
            return "/bin/sh"
    if nombre in ("USER", "LOGNAME"):
        try:
            return getpass.getuser()
        except Exception:
            return ""
    if nombre == "LANG":
        return "en_US.UTF-8"
    return ""


def con_basicas(env):
    """Completa las básicas que falten: primero del entorno de este proceso y,
    si tampoco están, las del sistema. Lo que ya trae `env` no se toca. En
    Windows no aplica (allá van USERPROFILE, TEMP y compañía)."""
    if os.name == "nt":                                   # pragma: no cover
        return env
    for k in BASICAS:
        if not env.get(k):
            v = os.environ.get(k) or _por_defecto(k)
            if v:
                env[k] = v
    return env


def para_motor(base=None, pestana=None, motor=None):
    """Limpio + las básicas que falten + las de la pestaña de la página."""
    env = con_basicas(limpio(base))
    env.update(de_pestana(pestana, motor))
    return env
