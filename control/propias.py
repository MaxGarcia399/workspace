"""WORKSPACE · control/propias — ¿este permiso es de una herramienta de Workspace? (B08, cacería 19-nov)

Por ACP (Copilot, Cursor, Kiro, Antigravity, OpenClaw, Hermes) y por el servidor de OpenCode, quien contesta los permisos
del motor es el cliente: la capa de control de Workspace. Las herramientas de los servidores MCP de Workspace (el núcleo,
`workspace`, y la memoria de antes, `workspace-memoria`) van preaprobadas como en la terminal: solo ellas, y por esta vía
oficial del protocolo. Sin esto, cada paso de una skill y cada nota pedían su tarjeta (de 6 a 11 por skill).

Una petición cuenta como de Workspace SOLO si su título es, entero, el nombre de una de esas herramientas en una de las
formas que usan los motores (`@workspace/x` en Kiro, `workspace-x: x` en Cursor, `workspace/x`, `mcp__workspace__x`,
`mcp(workspace/x)`, `workspace_x`…) y, si trae su entrada como objeto, esa entrada no tiene nada que la herramienta no
reciba. Un comando de terminal que solo las MENCIONE nunca pasa: su título es el comando. Nunca levanta (ante la duda,
la tarjeta de siempre)."""
import json
import re

#: Los nombres con que los motores escriben cada servidor de Workspace. Modo escritorio: las manos de ver y señalar del
#: servidor «escritorio» (escritorio/manos_mcp.py), solo en las conversaciones del monito.
_SERVIDORES = (("workspace-memoria", "memoria"), ("workspace_memoria", "memoria"), ("workspace", "nucleo"),
               ("escritorio", "manos"))
#: modo escritorio · las manos libres, como el núcleo (el permiso de verdad es el de la Mac y el monito enseña el
#: ojito): ver y señalar; E1 encargar (solo PROPONE: la app enseña su tarjeta y nada pasa sin tu clic), libre como
#: preguntar; y `actuar` (A0), que pide tu OK con la tarjeta de la APP del monito (armada con lo que dice el sistema),
#: no con la de Workspace. Solo por nombre y con su entrada exacta (lo de más, la tarjeta de siempre).
MANOS_LIBRES = ("contexto_escritorio", "leer_ventana", "ver_pantalla", "senalar", "encargar", "actuar",
                # ronda 2, carril 6 (manos de trabajo): como actuar, su OK es la ficha de la app del monito (su portero)
                "buscar_archivo", "abrir", "redactar_correo")
#: Para las pruebas: otra ruta del servidor de las manos.
MANOS = None
#: Modo escritorio (decisión del dueño, 21-nov): lo libre en la conversación del monito sale de la MISMA lista que usa
#: el aviso de antes de cada herramienta (arquitectura/paquete/lanzador/libres_escritorio.py).
_ESC = {}


def politica_escritorio():
    """El módulo del aviso con lo libre del monito (cargado por su ruta: no se cuela en sys.path)."""
    if "m" not in _ESC:
        import importlib.util
        import os
        ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "arquitectura", "paquete",
                            "lanzador", "libres_escritorio.py")
        spec = importlib.util.spec_from_file_location("workspace_escritorio_libres", ruta)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _ESC["m"] = m
    return _ESC["m"]
_SEPARADORES = ("__", "/", ":", ".", "_", "-")
_PREFIJO = re.compile(r"^(?:mcp\s*[:(]\s*|mcp__|mcp_|@)")
_CACHE = {}


def _herramientas():
    """{"nucleo"|"memoria": {herramienta: {campos de su entrada}}}, de los contratos de los dos servidores."""
    if _CACHE:
        return _CACHE
    out = {"nucleo": {}, "memoria": {}, "manos": {}}
    try:
        from arquitectura import nucleo_mcp
        for h in nucleo_mcp.herramientas():
            out["nucleo"][h["name"]] = set(((h.get("inputSchema") or {}).get("properties") or {}).keys())
    except Exception:
        pass
    try:
        import memoria_mcp
        for h in memoria_mcp.herramientas():
            out["memoria"][h["name"]] = set(((h.get("inputSchema") or {}).get("properties") or {}).keys())
    except Exception:
        pass
    for h in _manos():
        if h.get("name") in MANOS_LIBRES:
            out["manos"][h["name"]] = set(((h.get("inputSchema") or {}).get("properties") or {}).keys())
    if out["nucleo"] or out["memoria"]:
        _CACHE.update(out)
    return out


def _manos():
    """Las herramientas del servidor de las manos (escritorio/manos_mcp.herramientas(), su contrato), o []. Solo si el
    archivo existe y se puede importar sin arrancar el servidor (tiene su `if __name__ == "__main__"`)."""
    import os
    ruta = MANOS or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "escritorio",
                                 "manos_mcp.py")
    try:
        with open(ruta, encoding="utf-8") as fh:
            src = fh.read()
        if "def herramientas(" not in src or "__main__" not in src:
            return []
        import importlib.util
        spec = importlib.util.spec_from_file_location("workspace_manos_mcp", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return [h for h in mod.herramientas() if isinstance(h, dict)]
    except Exception:
        return []


def libre_en_escritorio(titulo, detalle=None, kind=None, rutas=(), carpeta=None):
    """Modo escritorio: ¿este permiso pasa sin tarjeta en la conversación del monito? Solo las manos; preguntar,
    mostrar_archivo y memoria_nota; lo del núcleo que solo lee su cerebro; y leer dentro de su carpeta (también con un
    comando que solo lee, todo adentro: `cat BRAIN.md`, como arranca Codex). Lo demás (y ante la duda), la tarjeta de
    la burbuja, aunque su motor esté en automático. Nunca levanta."""
    try:
        E = politica_escritorio()
        h = herramienta(titulo)
        if h:
            libres = E.MANOS if h[0] == "escritorio" else E.LIBRES_NUCLEO
            return h[1] in libres and de_workspace(titulo, detalle)
        from control.base import _texto_comando, que_permiso
        q = que_permiso(titulo, detalle, kind, rutas)
        if q.get("clase") == "comando":
            # el comando ENTERO: que_permiso lo recorta a 500 letras para la tarjeta, y lo que venía después no se
            # revisaba (Monito UX, 22-nov)
            entero = _texto_comando(detalle) or str(q.get("comando") or "")
            if len(entero) >= 500 and not _texto_comando(detalle):
                return False                                     # solo lo tenemos recortado: tarjeta
            return bool(carpeta) and E.comando_que_solo_lee(entero, carpeta, cwd=carpeta)
        return q.get("clase") in ("leer", "buscar") and bool(q.get("ruta")) and E.dentro(q["ruta"], carpeta)
    except Exception:
        return False


def de_nucleo_libre_codex(mensaje):
    """Codex (su elicitación MCP) en el monito: «Allow the workspace MCP server to run tool "x"?» de una de las libres
    del núcleo, y nada más."""
    try:
        m = re.match(r'^Allow the workspace MCP server to run tool "([a-z_]{1,40})"\?$', str(mensaje or "").strip())
        return bool(m) and m.group(1) in politica_escritorio().LIBRES_NUCLEO
    except Exception:
        return False


def de_manos(servidor, mensaje):
    """Codex (su elicitación de servidor MCP, control/codex): «Allow the escritorio MCP server to run tool "x"?» de una
    de las manos libres, y nada más. → True si se aprueba como las de Workspace."""
    m = re.match(r'^Allow the escritorio MCP server to run tool "([a-z_]{1,40})"\?$', str(mensaje or "").strip())
    return str(servidor or "") == "escritorio" and bool(m) and m.group(1) in _herramientas().get("manos", {})


def _entrada(detalle):
    """La entrada como objeto (dict o JSON de un objeto), o None si viene en otra forma (texto, lista de partes)."""
    if isinstance(detalle, dict):
        return detalle
    if isinstance(detalle, str) and detalle.strip().startswith("{"):
        try:
            d = json.loads(detalle)
            return d if isinstance(d, dict) else None
        except ValueError:
            return None
    return None


def herramienta(titulo):
    """(servidor, herramienta) si el título es, entero, una herramienta de Workspace; si no, None."""
    t = str(titulo or "").strip().lower()
    if not t or len(t) > 120 or "\n" in t:
        return None
    parentesis = t.startswith("mcp(")
    t = _PREFIJO.sub("", t, count=1).strip()
    if parentesis:
        if not t.endswith(")"):
            return None
        t = t[:-1].strip()
    tools = _herramientas()
    for nombre, grupo in _SERVIDORES:
        for sep in _SEPARADORES:
            if not t.startswith(nombre + sep):
                continue
            resto = t[len(nombre + sep):].strip()
            if ":" in resto:                                   # Cursor: «workspace-x: x»
                a, b = (p.strip() for p in resto.split(":", 1))
                if a != b:
                    continue
                resto = a
            if resto in tools.get(grupo, {}):
                return nombre, resto
    return None


def de_workspace(titulo, detalle=None):
    """¿El permiso es de una herramienta de Workspace (y nada más)? Ver el docstring del módulo."""
    try:
        h = herramienta(titulo)
        if not h:
            return False
        grupo = "memoria" if "memoria" in h[0] else "manos" if h[0] == "escritorio" else "nucleo"
        campos = _herramientas().get(grupo, {}).get(h[1], set())
        entrada = _de_cursor(_entrada(detalle), h)
        if entrada is False or (entrada is not None and not set(entrada) <= campos):
            return False
        return True
    except Exception:
        return False


#: cable-cursor (reverificación 19-nov, B08 en Cursor): Cursor manda la entrada de una herramienta MCP envuelta,
#: {providerIdentifier, toolName, args} (VERIFICADO 2026.11.19 por ACP: «workspace-reportar_avance: reportar_avance» con
#: {"providerIdentifier": "workspace", "toolName": "reportar_avance", "args": {…}}).
_ENVOLTURA_CURSOR = {"providerIdentifier", "toolName", "args"}


def _de_cursor(entrada, h):
    """La entrada de verdad si viene con la envoltura de Cursor y esa envoltura nombra LA MISMA herramienta que el
    título (servidor y herramienta); False si nombra otra o sus args no son un objeto; si no es esa forma, tal cual."""
    if not isinstance(entrada, dict) or "toolName" not in entrada or not set(entrada) <= _ENVOLTURA_CURSOR:
        return entrada
    if str(entrada.get("providerIdentifier") or "").strip().lower() != h[0] \
            or str(entrada.get("toolName") or "").strip().lower() != h[1]:
        return False
    args = entrada.get("args")
    if args is None:
        return {}
    return args if isinstance(args, dict) else False
