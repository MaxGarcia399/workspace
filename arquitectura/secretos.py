#!/usr/bin/env python3
"""WORKSPACE · arquitectura/secretos — lo prohibido de leer (llaves y secretos) donde el aviso no corre.

El bloqueo de siempre vive en el aviso de antes de cada herramienta (paquete/lanzador/prohibidos.py, F7). Por la
página, tres motores no corren avisos: Codex (su app-server: el hilo va «untrusted»), Cursor y Kiro (ACP). Ahí lo
prohibido va por lo OFICIAL de cada motor, siempre en lo de Workspace (la carpeta del agente o el hilo de la página),
nunca en la config global del motor (cierre de la auditoría real del 19-nov; caja negra con un canario):

  · Codex: un perfil de permisos SOLO para el hilo de la página (`config` de thread/start: `default_permissions` y
    `[permissions.<perfil>]`, doc «Permissions» de Codex): extiende el de siempre (:workspace o :read-only) y niega leer
    con `deny` (su sandbox lo cumple: `cat secrets.local` → «Operation not permitted»). Su app-server confirma el perfil
    en `activePermissionProfile`. Con `sandbox` en el mismo pedido se usan los ajustes de antes: no va. En Windows no
    va el perfil (codex_config, 23-nov): allá su sandbox reescribe ACLs y hacía fallar todo comando.
  · Cursor: reglas `Read(…)` en el `.cursor/cli.json` de la carpeta del agente (doc «permissions»; ACP las respeta:
    «Permission denied»). `**/` alcanza también fuera del proyecto. Su deny no admite excepciones: niega todo
    `.env.*`, también `.env.example` (del lado seguro).
  · Kiro: el perfil `workspace-pagina` de la carpeta del agente (`.kiro/agents/`, doc «custom agents» · `permissions`),
    elegido por la página con `_meta.kiro.modeId` en session/new: `fs_read` deny con `exclude` para los `.env` de
    ejemplo. Su `**/` no sale de la carpeta: lo de fuera pregunta, y ese permiso lo contesta la capa de control.
  · Y en la capa de control (todos los motores de la página): un permiso que el motor pide para leer lo prohibido se
    niega solo, con el mismo motivo que el aviso (motivo_permiso).

La lista sale de la del aviso (prohibidos): un archivo `.env` (no los de ejemplo), una llave (`*.key`, `*.pem`…), una
llave SSH privada, credenciales (`.netrc`, `.aws/credentials`…), la bóveda de Workspace y el llavero. Stdlib.
"""
import importlib.util
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

#: El perfil de permisos del hilo de la página de Codex y el agente de la página de Kiro.
PERFIL_CODEX = "workspace-pagina"
AGENTE_KIRO = "workspace-pagina"
_MOD = {}


def prohibidos():
    """El módulo del aviso (paquete/lanzador/prohibidos.py), cargado por su ruta (no se cuela en sys.path)."""
    if "m" not in _MOD:
        ruta = os.path.join(AQUI, "paquete", "lanzador", "prohibidos.py")
        spec = importlib.util.spec_from_file_location("workspace_prohibidos", ruta)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _MOD["m"] = m
    return _MOD["m"]


def nombres():
    """Los nombres de archivo prohibidos, como comodines de nombre (sin carpeta), de la lista del aviso."""
    P = prohibidos()
    return ([".env", ".env.*"] + ["*" + e for e in P._EXT_LLAVE] + list(P._LLAVES_SSH) + list(P._CREDENCIALES)
            + ["secrets.local*"])


def permitidos():
    """Los `.env` de ejemplo que el aviso sí deja leer."""
    return list(prohibidos()._ENV_PERMITIDOS)


def globs():
    """Lo prohibido como comodines relativos («**/…», en cualquier carpeta)."""
    return (["**/" + n for n in nombres()] + ["**/.aws/credentials", "**/workspace/boveda/**",
                                              "**/Library/Keychains/**"] + monito_globs())


#: Lo del monito de escritorio que ningún agente lee: su ficha, el turno abierto, sus fotos y lo de actuar (A0: tus
#: vetados, tus confianzas, sus ajustes y la bitácora de acciones).
MONITO_ARCHIVOS = ("manos.json", "turno.json", "vetados.json", "confianzas.json", "ajustes.json")
MONITO_CARPETAS = ("miradas", "acciones")


def monito_globs():
    """El monito de escritorio: su ficha, el turno abierto y sus fotos (con ellos un agente le pediría a su app que mire),
    y lo de actuar (vetados, confianzas, ajustes y su bitácora)."""
    return (["**/workspace/escritorio/" + n for n in MONITO_ARCHIVOS]
            + ["**/workspace/escritorio/%s/**" % c for c in MONITO_CARPETAS])


def _monito():
    """Lo del monito en esta máquina (rutas exactas), o []."""
    try:
        import paths
        d = os.path.join(os.path.realpath(paths.state_dir()), "escritorio")
    except Exception:
        return []
    return [os.path.join(d, n) for n in MONITO_ARCHIVOS + MONITO_CARPETAS]


def _boveda():
    """La bóveda de Workspace en esta máquina (en su carpeta de estado, paths.state_dir): [archivo*, carpeta], o []."""
    try:
        import paths
        est = os.path.realpath(paths.state_dir())
    except Exception:
        return []
    return [os.path.join(est, "secrets.local") + "*", os.path.join(est, "boveda")]


def rutas_del_home():
    """Lo prohibido que vive en el HOME de esta máquina (rutas exactas, o un comodín al final): las llaves SSH, las
    credenciales, el llavero y la bóveda de Workspace."""
    P = prohibidos()
    return (["~/.ssh/" + n for n in P._LLAVES_SSH] + ["~/" + n for n in P._CREDENCIALES]
            + ["~/.aws/credentials", "~/Library/Keychains"] + _boveda() + _monito())


# ── Codex: el perfil de permisos del hilo de la página ────────────────────
#: El sandbox de antes (`sandbox` del hilo) → el perfil incorporado que lo reemplaza (doc «Permissions»).
BASE_CODEX = {"workspace-write": ":workspace", "read-only": ":read-only"}


def _windows():
    return os.name == "nt"


def codex_config(sandbox, windows=None):
    """El `config` del hilo con el perfil de permisos que niega leer lo prohibido, sobre el perfil incorporado del
    nivel del agente (`sandbox`: workspace-write | read-only). None con otro sandbox (no se inventa uno).

    None en Windows (23-nov, la PC del dueño: «Codex me trae errores»). Allá el sandbox de Codex cumple cada `deny`
    reescribiendo la ACL de esa ruta, y crea una carpeta vacía donde la ruta no existe. Con una sola ruta cuya ACL tu
    usuario no puede tocar (la bóveda creada desde una terminal de administrador), TODO comando falla con
    «helper_unknown_error: apply deny-read ACLs» (Codex 0.166.0, caja negra con el real). Cuando no falla, deja carpetas
    vacías en tu HOME (~/.git-credentials, ~/.aws/credentials, ~/.ssh/id_rsa…) que rompen git, la CLI de AWS y ssh. El
    hilo va entonces con el sandbox del nivel (pagina_v2.hilo_codex). La bóveda sigue cifrada con DPAPI y solo para tu
    usuario (acl_privada), y un permiso que pide leer lo prohibido se sigue negando solo (motivo_permiso)."""
    if _windows() if windows is None else bool(windows):
        return None
    base = BASE_CODEX.get(sandbox)
    if not base:
        return None
    fs = {r: "deny" for r in rutas_del_home()}
    fs[":workspace_roots"] = {g: "deny" for g in globs()}
    return {"default_permissions": PERFIL_CODEX,
            "permissions": {PERFIL_CODEX: {"extends": base, "filesystem": fs}}}


# ── Cursor: reglas del .cursor/cli.json de la carpeta del agente ──────────
def cursor_deny(windows=None):
    """Las reglas `Read(…)` de lo prohibido. En Windows Cursor solo niega con «\\» (memoria_mcp._cursor_deny): ahí
    van también esas."""
    win = (os.name == "nt") if windows is None else bool(windows)
    out = ["Read(%s)" % g for g in globs()]
    if win:
        out += ["Read(%s)" % g.replace("/", "\\") for g in globs()]
    return out


def cursor_todas():
    """Las de las dos formas (para quitarlas al desinstalar: el cerebro viaja entre máquinas)."""
    return set(cursor_deny(False)) | set(cursor_deny(True))


# ── Kiro: el agente de la página ───────────────────────────────────────────
def kiro_reglas():
    """Las reglas V3 (`permissions.rules`) que niegan leer lo prohibido, sin distinguir mayúsculas (Kiro compara la
    ruta tal cual y acepta clases `[aA]`; rutas_protegidas.sin_mayusculas)."""
    import rutas_protegidas as R
    return [{"capability": "fs_read", "match": [R.sin_mayusculas(g) for g in globs()],
             "exclude": [R.sin_mayusculas("**/" + n) for n in permitidos()], "effect": "deny"}]


# ── la capa de control: un permiso que pide leer lo prohibido ──────────────
#: Las clases de permiso que escriben (control/base.que_permiso): no se miran, como en el aviso.
_ESCRIBEN = ("crear", "cambiar", "borrar")


def motivo_permiso(herramienta, detalle, kind=None, rutas=()):
    """Por qué se niega SOLO este permiso ('' = lo decide el socio): lo mismo que el aviso de antes de cada herramienta
    (prohibidos.motivo) sobre lo que pide, de lo estructurado (control/base.que_permiso). Nunca levanta."""
    try:
        from control.base import que_permiso
        q = que_permiso(herramienta, detalle, kind, rutas)
        if q.get("clase") in _ESCRIBEN:
            return ""
        nombre = "Shell" if q.get("clase") == "comando" else "Read"
        entrada = {"detalle": detalle if isinstance(detalle, (dict, list, str)) else str(detalle or ""),
                   "rutas": [str(r) for r in rutas or () if r], "ruta": q.get("ruta") or "",
                   "comando": q.get("comando") or ""}
        if q.get("clase") != "comando":
            entrada["titulo"] = str(herramienta or "")
        return prohibidos().motivo({"tool_name": nombre, "tool_input": entrada})
    except Exception:
        return ""
