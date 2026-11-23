#!/usr/bin/env python3
"""WORKSPACE · arquitectura/nucleo — lo que el núcleo le da a cada sesión (F6).

Tres cosas, por la vía que dice la ficha de cada motor (`nucleo`):

  · El MCP núcleo (`nucleo.mcp`): el servidor `workspace` del paquete (arquitectura/nucleo_mcp.py),
    declarado y preaprobado POR SESIÓN: argumentos, entorno o archivos en el proyecto. Nada en la
    config global del motor.
  · El paquete de la pestaña al abrir (`nucleo.al_abrir`): resumen, lo vigente, notas nuevas y la
    maleta (memoria.paquete, lo mismo que da hoy el arranque). «hook»: lo devuelve el hook de inicio
    (y otra vez al volver de compactar). «mcp»: va en las instrucciones del servidor MCP, para los
    motores donde lo que devuelve el hook no llega al modelo.
  · El tono (`nucleo.tono`): personalidad.bloque del agente en la pieza de sistema del motor, no en
    cada mensaje (D1-a). «argv»: un argumento de la sesión; «archivo»: una regla del proyecto;
    «mcp»: las instrucciones del servidor MCP; «hook»: con el paquete al abrir; «no»: sin vía por
    sesión (sigue lo de hoy).
  · La guía del modo chat (`nucleo.chat`, arquitectura/modo_chat): solo en las sesiones de la página o
    del hub. «argv»: con el tono, en la pieza de sistema (aquí); «mensaje»: la manda la página una vez
    por conexión, antes de tu primer mensaje (pagina_v2).

Cuando el núcleo se encarga en una sesión, el lanzador pone ENV_AL_ABRIR y ENV_TONO en su entorno:
el camino de hoy (el paquete en el hook neutral y en el bloque de la pestaña, el tono por mensaje)
lo ve y no lo repite. Falla-suave: si algo falla, la sesión abre como hoy. Stdlib.
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

#: En el entorno de una sesión con el núcleo: por dónde le llega el paquete al abrir («hook» o «mcp»).
ENV_AL_ABRIR = "WORKSPACE_NUCLEO_AL_ABRIR"
#: En el entorno de una sesión con el núcleo: el tono va en la pieza de sistema («1»).
ENV_TONO = "WORKSPACE_TONO_SISTEMA"
VIAS_AL_ABRIR = ("hook", "mcp")
VIAS_TONO = ("argv", "archivo", "mcp", "hook", "no")
#: Marca de un archivo de tono que escribió Workspace (solo ese se reescribe o se borra).
MARCA_TONO = "workspace: el tono de este agente"
MAX_TONO = 6000

#: «Antes de afirmar algo del pasado, busca» (lo de MemPalace): una línea, en las instrucciones del servidor y en el
#: paquete al abrir (no solo en la skill buscar-memoria).
BUSCAR = ("Antes de afirmar algo del pasado (qué se decidió, se dijo o se hizo), búscalo con memoria_buscar; "
          "si no aparece, dilo así, no lo inventes.")
#: Lo que el servidor MCP le dice al motor de sí mismo (sus instrucciones), antes del tono y del paquete.
MANUAL = (
    "Workspace: la memoria de esta pestaña y las skills del cerebro, por las herramientas de este servidor "
    "(preaprobadas: no piden permiso). Guarda en el momento, una nota por cosa: memoria_nota con tipo "
    "decision|pendiente|hecho|nota|dato|preferencia; un pendiente devuelve su id (P-7) y al resolverlo va "
    "memoria_nota tipo hecho con cierra [\"P-7\"]. Al terminar una unidad de trabajo, memoria_checkpoint con "
    "expected_revision (la que da memoria_ver). pendientes: lo abierto. skills_lista y skill_leer: las skills "
    "del cerebro; usar_skill activa una a la vista del socio (su proceso en la página) y reportar_avance cuenta tu "
    "avance. tarea_actual: en una línea, en qué estás (el socio lo ve en la página). preguntar: le preguntas algo "
    "al socio en su caja de escribir, con opciones (botones) si se elige. mostrar_archivo: le enseñas un archivo de "
    "tu carpeta como tarjeta en la página. personalizar: tu color, tu monito o tu nombre en la página, si él quiere. "
    "Nunca escribas la memoria a mano en los archivos del cerebro.\n" + BUSCAR)


def ficha_nucleo(motor, ficha=None):
    """El bloque `nucleo` de la ficha de `motor` ({} si no hay ficha)."""
    try:
        if ficha is None:
            from arquitectura import contrato
            ficha = contrato.ficha(motor)
        return dict(ficha.get("nucleo") or {})
    except Exception:
        return {}


def via_tono(motor, ficha=None):
    return str((ficha_nucleo(motor, ficha).get("tono") or {}).get("via") or "no")


def tono(brain):
    """El tono del agente dueño de `brain` (personalidad.bloque): '' si todo está en neutro."""
    try:
        import personalidad
        agente = personalidad.agente_de(str(brain)) or None
        return (personalidad.bloque(agente) or "")[:MAX_TONO]
    except Exception:
        return ""


def paquete(brain, tab, motor, source="startup", con_buscar=True):
    """El paquete de la pestaña (memoria.paquete con entregar=True: se le entrega al agente) y, al final, la línea
    BUSCAR (`con_buscar`; no va cuando el paquete viaja en las instrucciones del servidor, que ya la traen)."""
    try:
        import memoria
        texto = memoria.paquete(memoria.raiz_cerebro(str(brain)), tab, motor=motor,
                                retomada=(source == "resume"), entregar=True) or ""
    except Exception:
        return ""
    return texto + "\n" + BUSCAR if (texto and con_buscar) else texto


def al_abrir_por_hook(brain, tab, motor, source="startup", ficha=None):
    """Lo que entrega el hook de inicio (o el de después de compactar) si la ficha lo manda por ahí: el
    tono (vía «hook») y el paquete de la pestaña (vía «hook»). '' si nada va por el hook."""
    n = ficha_nucleo(motor, ficha)
    partes = []
    if (n.get("tono") or {}).get("via") == "hook":
        partes.append(tono(brain))
    if n.get("al_abrir") == "hook" and tab:
        partes.append(paquete(brain, tab, motor, source))
    return "\n\n".join(p for p in partes if p)


def instrucciones(brain, tab, motor, ficha=None):
    """Las instrucciones del servidor MCP: el manual y, si la ficha los manda por aquí, el tono y el
    paquete de la pestaña."""
    n = ficha_nucleo(motor, ficha) if motor else {}
    partes = [MANUAL]
    if brain and (n.get("tono") or {}).get("via") == "mcp":
        partes.append(tono(brain))
    if brain and tab and n.get("al_abrir") == "mcp":
        partes.append(paquete(brain, tab, motor, con_buscar=False))     # el MANUAL ya trae BUSCAR
    return "\n\n".join(p for p in partes if p)


# ── por sesión: lo que el lanzador le suma a la corrida ───────────────────
def poner(valor, valores):
    """Sustituye {clave} en un valor de la ficha. Un texto que es JSON (empieza con { o [) se sustituye
    por dentro y se vuelve a escribir: así una ruta con comillas o barras queda bien escapada."""
    if isinstance(valor, str):
        if valor[:1] in "{[":
            try:
                obj = json.loads(valor)
            except ValueError:
                obj = None
            if isinstance(obj, (dict, list)):
                return json.dumps(poner(obj, valores), ensure_ascii=False, separators=(",", ":"))
        for k, v in valores.items():
            valor = valor.replace("{%s}" % k, str(v))
        return valor
    if isinstance(valor, list):
        return [poner(x, valores) for x in valor]
    if isinstance(valor, dict):
        return {k: poner(v, valores) for k, v in valor.items()}
    return valor


def _dentro(cerebro, ruta):
    base = os.path.realpath(str(cerebro))
    return os.path.realpath(ruta).startswith(base + os.sep)


def _escribir(ruta, texto):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    tmp = "%s.%d.tmp" % (ruta, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)
    os.replace(tmp, ruta)


def _paso(paso, valores, cerebro):
    """Un archivo de la ficha en el proyecto: `copiar` (con `sustituir`), `escribir` + `contenido`, o `fundir`."""
    if "{lanzador}" in json.dumps(paso) and valores.get("paquete"):
        from arquitectura import sesion            # la carpeta fija: la ruta no cambia al actualizar Workspace
        valores.setdefault("lanzador", sesion.lanzador_fijo(valores["paquete"]))
    if "fundir" in paso:
        return _fundir(paso, valores, cerebro)
    if "sumar" in paso:
        return _sumar(paso, valores, cerebro)
    dst = poner(paso.get("a") or paso.get("escribir") or "", valores)
    if not dst or not _dentro(cerebro, dst):
        raise ValueError("la ficha escribe fuera del cerebro: %s" % dst)
    if "copiar" in paso:
        with open(poner(paso["copiar"], valores), encoding="utf-8") as fh:
            texto = fh.read()
    else:
        texto = poner(paso.get("contenido") or "", valores)
    for k, v in (paso.get("sustituir") or {}).items():
        texto = texto.replace(k, poner(v, valores))
    _escribir(dst, texto)


def _fundir(paso, valores, cerebro):
    """`fundir`: las entradas de `clave` (mcpServers) de un JSON del paquete, DENTRO del JSON del proyecto (`a`). Lo
    del socio y lo de otras piezas de Workspace (workspace-memoria) queda tal cual; la nuestra se pone o se actualiza.
    Si el del proyecto no se puede leer (no es JSON, no es un objeto, es un enlace), no se toca: → False."""
    dst = poner(paso.get("a") or "", valores)
    if not dst or not _dentro(cerebro, dst):
        raise ValueError("la ficha escribe fuera del cerebro: %s" % dst)
    clave = paso.get("clave") or "mcpServers"
    barra = {k: str(v).replace("\\", "/") for k, v in valores.items()}
    try:
        with open(poner(paso["fundir"], valores), encoding="utf-8") as fh:
            texto = fh.read()
    except OSError:
        return False                              # un paquete sin ese archivo: nada que sumar (lo demás sigue)
    for k, v in (paso.get("sustituir") or {}).items():
        texto = texto.replace(poner(k, barra), poner(v, barra))
    nuestro = json.loads(texto).get(clave) or {}
    if paso.get("env"):
        # cable-cursor: el entorno de la pestaña para nuestro servidor, con la forma que el motor resuelve al abrirlo
        # (Cursor: `${env:NOMBRE}`, su interpolación documentada). Solo NOMBRES de Workspace, nunca un valor
        nuestro = {n: dict(s, env=dict(s.get("env") or {}, **{k: poner(v, valores) for k, v in paso["env"].items()}))
                   if isinstance(s, dict) else s for n, s in nuestro.items()}
    actual = _leer_del_proyecto(dst)
    if actual is None or not isinstance(actual.get(clave, {}), dict):
        return False
    junto = dict(actual)
    junto[clave] = dict(actual.get(clave) or {}, **nuestro)
    if junto != actual:
        _escribir(dst, json.dumps(junto, ensure_ascii=False, indent=2) + "\n")
    return True


def _leer_del_proyecto(dst):
    """El JSON del proyecto en `dst` ({} si no existe) o None si no se toca (un enlace, no es JSON, no es un
    objeto)."""
    if not os.path.lexists(dst):
        return {}
    if os.path.islink(dst):
        return None
    try:
        with open(dst, encoding="utf-8") as fh:
            actual = json.load(fh)
    except (OSError, ValueError):
        return None
    return actual if isinstance(actual, dict) else None


def _secretos_cursor():
    from arquitectura import secretos
    return secretos.cursor_deny()


#: Listas con nombre que un paso `sumar` de la ficha puede pedir enteras (cierre de la auditoría, 19-nov): las reglas
#: `Read(…)` de lo prohibido de leer en el `.cursor/cli.json` (arquitectura/secretos.cursor_deny; por ACP Cursor no
#: corre el aviso que lo niega).
_LISTAS = {"{secretos:cursor}": _secretos_cursor}


def _sumar(paso, valores, cerebro):
    """`sumar` (cable-cursor): {objeto: {lista: [reglas]}} DENTRO del JSON del proyecto (`a`), p. ej. las
    `permissions.allow` de `.cursor/cli.json`. A cada lista se le agregan al final las nuestras que falten; lo del socio
    y lo de otras piezas de Workspace (las reglas de la memoria) queda tal cual y en su orden. Una lista que falta se
    crea (vacía si no trae nada nuestro: Cursor valida el archivo entero y sin `deny` lo rechaza). Si el archivo no se
    puede leer, o una pieza no tiene esa forma, no se toca: → False."""
    dst = poner(paso.get("a") or "", valores)
    if dst and os.path.islink(dst):
        return False                              # un enlace (del socio) no se toca ni tumba la sesión
    if not dst or not _dentro(cerebro, dst):
        raise ValueError("la ficha escribe fuera del cerebro: %s" % dst)
    actual = _leer_del_proyecto(dst)
    if actual is None:
        return False
    junto = dict(actual)
    for obj, listas in (paso.get("sumar") or {}).items():
        cur = actual.get(obj, {})
        if not isinstance(cur, dict):
            return False
        nuevo = dict(cur)
        for lista, reglas in (listas or {}).items():
            ya = cur.get(lista, [])
            if not isinstance(ya, list):
                return False
            reglas = [x for r in reglas for x in (_LISTAS[r]() if r in _LISTAS else [poner(r, valores)])]
            nuevo[lista] = list(ya) + [r for r in reglas if r not in ya]
        junto[obj] = nuevo
    if junto != actual:
        _escribir(dst, json.dumps(junto, ensure_ascii=False, indent=2) + "\n")
    return True


#: La aprobación por servidor del motor (`nucleo.mcp.aprobar`) la corre esto: (argv, cwd, env) → bool. Las pruebas la
#: cambian (y la suite no corre motores: WORKSPACE_NO_APROBAR_MCP, _testutil).
def _correr_aprobar(argv, cwd, env, timeout=20):
    import subprocess
    try:
        import arbol_procesos                  # Windows: al vencer muere el árbol (.cmd → node)
        kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" \
            else {"start_new_session": True}
        r = arbol_procesos.run(argv, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, stdin=subprocess.DEVNULL, **kw)
        return getattr(r, "returncode", 1) == 0
    except Exception:
        return False


CORRER_APROBAR = _correr_aprobar


def aprobar(motor, cerebro, argv, env, ficha=None):
    """cable-cursor: la aprobación oficial de NUESTRO servidor MCP, solo ese, para esta sesión (`nucleo.mcp.aprobar`
    de la ficha; Cursor: `agent mcp enable workspace`, «Add an MCP server to the local approved list»). Se corre en
    el cerebro con el entorno FINAL de la sesión: el motor ata la aprobación a la config ya resuelta (con los
    `${env:…}` de la pestaña), así que vale para esta pestaña y para nada más (ni para lo que alguien agregue al
    mcp.json). Nunca su «aprobar todos» (`--approve-mcps`). Falla-suave: → True si quedó, False si no (el motor
    pedirá aprobarlo, como siempre), None si la ficha no lo trae."""
    mcp = (ficha_nucleo(motor, ficha).get("mcp") or {})
    pasos = mcp.get("aprobar")
    if not pasos or "no" in mcp or not argv:
        return None
    if os.environ.get("WORKSPACE_NO_APROBAR_MCP") == "1":
        return False
    return bool(CORRER_APROBAR(poner(list(pasos), {"binario": str(argv[0])}), str(cerebro), dict(env)))


#: En `nucleo.mcp.ajustes` (y en el probador): un texto con esto vale por UNO por cada herramienta del MCP núcleo, de su
#: lista real (nucleo_mcp.herramientas, el contrato mcp_nucleo.json). Así ninguna ficha lleva la lista ni su número a mano.
HERRAMIENTA = "{herramienta}"


def herramientas_mcp():
    """Los nombres de las herramientas del MCP núcleo, de su lista real (el contrato)."""
    from arquitectura import nucleo_mcp
    return [h["name"] for h in nucleo_mcp.herramientas()]


def expandir_herramientas(valor, nombres=None):
    """`valor` con cada texto de una lista que lleva {herramienta} abierto en uno por herramienta real del núcleo."""
    if isinstance(valor, dict):
        return {k: expandir_herramientas(v, nombres) for k, v in valor.items()}
    if isinstance(valor, list):
        out = []
        for x in valor:
            if isinstance(x, str) and HERRAMIENTA in x:
                out += [x.replace(HERRAMIENTA, h) for h in (nombres if nombres is not None else herramientas_mcp())]
            else:
                out.append(expandir_herramientas(x, nombres))
        return out
    return valor


def _con_ajustes(n, valores, argv):
    """`nucleo.mcp.ajustes` (la preaprobación del servidor) dentro del `--settings` que YA trae la corrida, y uno solo
    (permisos._con_ajustes). Sin uno, nada: en Antigravity su `permissions` reemplaza el del socio en la sesión, así
    que solo se suma al que arma su lanzador con las reglas del socio. Falla-suave: si no se puede, el argv tal cual
    (sus herramientas pedirán permiso)."""
    mcp = n.get("mcp") or {}
    if not mcp.get("ajustes") or "no" in mcp:
        return argv
    try:
        from arquitectura import permisos
        if permisos._valor_de(argv, "--settings")[0] < 0:
            return argv
        return permisos._con_ajustes(argv, poner(expandir_herramientas(mcp["ajustes"]), valores))
    except Exception:
        return argv


def _archivo_tono(paso, valores, cerebro, texto):
    """El tono como regla del proyecto: se escribe con él, o se borra (si es nuestro) cuando no hay tono."""
    dst = poner(paso.get("escribir") or "", valores)
    if not dst or not _dentro(cerebro, dst):
        raise ValueError("la ficha escribe fuera del cerebro: %s" % dst)
    if texto:
        _escribir(dst, poner(paso.get("contenido") or "", valores))
        return
    try:
        with open(dst, encoding="utf-8") as fh:
            nuestro = MARCA_TONO in fh.read(4096)
        if nuestro:
            os.remove(dst)
    except OSError:
        pass


def _pasa_por_cmd(binario):
    """¿El motor se lanza por un .cmd/.bat de Windows (npm instala así claude, codex…)? Entonces cmd.exe vuelve a
    leer cada argumento: un texto de varias líneas corta los que siguen (el --resume, el --plugin-dir)."""
    if os.name != "nt" or not binario:
        return False
    exe = str(binario[0])
    if not exe.lower().endswith((".cmd", ".bat", ".exe")):
        import shutil
        exe = shutil.which(exe) or exe
    return exe.lower().endswith((".cmd", ".bat"))


def _mcp(n, valores, cerebro, env, archivos=True):
    """Los argumentos del servidor MCP del núcleo (nucleo.mcp de la ficha); el entorno y los archivos (con `archivos`),
    en su sitio. → (argumentos, si hubo MCP)."""
    mcp = n.get("mcp") or {}
    if not mcp or "no" in mcp:
        return [], False
    for k, v in (mcp.get("env") or {}).items():
        env[k] = poner(v, valores)
    for paso in (mcp.get("archivos") or ()) if archivos else ():
        _paso(paso, valores, cerebro)
    return [poner(a, valores) for a in mcp.get("argv") or ()], True


def solo_mcp(motor, cerebro, argv, env, valores, ficha=None):
    """(argv, env, si hubo MCP): solo el servidor MCP del núcleo, sin el paquete al abrir ni el tono (una ficha con
    `sin_nucleo` y `mcp_del_nucleo`: Codex, cuyos hooks esperan la confianza del socio; Antigravity, cuyo paquete al
    abrir sigue en su GEMINI.md). Los argumentos van justo después del binario."""
    n = ficha_nucleo(motor, ficha) or {}
    argv, env = list(argv), dict(env)
    extra, hubo = _mcp(n, valores, cerebro, env)
    return _con_ajustes(n, valores, argv[:1] + extra + argv[1:]), env, hubo


def aplicar(motor, cerebro, argv, env, valores, ficha=None, archivos=True):
    """(argv, env, info) de una sesión con el núcleo, según la ficha: el MCP declarado y preaprobado y el
    tono en su pieza de sistema; en el entorno, ENV_AL_ABRIR y ENV_TONO para que el camino de hoy no lo
    repita. Los argumentos van justo después del binario. Escribe solo dentro de {cerebro}/ (los archivos del MCP,
    salvo `archivos=False`: la página por ACP, que declara el servidor en su sesión). Levanta si la ficha está mal:
    quien llama decide (el lanzador abre como hoy)."""
    n = ficha_nucleo(motor, ficha)
    argv, env = list(argv), dict(env)
    info = {"mcp": False, "tono": "", "al_abrir": ""}
    if not n:
        return argv, env, info
    extra, info["mcp"] = _mcp(n, valores, cerebro, env, archivos=archivos)
    t = n.get("tono") or {}
    via = str(t.get("via") or "no")
    if via in ("argv", "archivo", "mcp", "hook"):
        texto = tono(cerebro)
        if via == "argv":
            texto = "\n\n".join(x for x in (texto, guia_chat(n, env, info["mcp"])) if x)
        if via == "argv" and texto and _pasa_por_cmd(argv[:1]):
            import memoria                     # cmd.exe corta en el primer salto de línea (P2-10)
            texto = memoria.argv_seguro(texto)
        vals = dict(valores, tono=texto)
        if via == "argv" and texto:
            extra += [poner(a, vals) for a in t.get("argv") or ()]
        for paso in (t.get("archivos") or ()) if via == "archivo" else ():
            _archivo_tono(paso, vals, cerebro, texto)
        env[ENV_TONO] = "1"
        info["tono"] = via
    if n.get("al_abrir") in VIAS_AL_ABRIR:
        env[ENV_AL_ABRIR] = n["al_abrir"]
        info["al_abrir"] = n["al_abrir"]
    return _con_ajustes(n, valores, argv[:1] + extra + argv[1:]), env, info


def guia_chat(n, env, con_mcp):
    """modo chat · la guía de chat para la pieza de sistema (vía «argv» de `nucleo.chat`), SOLO en una sesión de la
    página o del hub (WORKSPACE_VIA=pagina, que pone pagina_v2.nucleo_para): la terminal no la recibe. '' si no toca.
    modo escritorio (WORKSPACE_VIA=escritorio): la del monito, con sus manos si la sesión las trae (WORKSPACE_MANOS)."""
    from arquitectura import modo_chat
    if (n.get("chat") or {}).get("via") != "argv" or not modo_chat.en_la_pagina(env):
        return ""
    if modo_chat.canal_de(env) == modo_chat.ESCRITORIO:
        return modo_chat.guia(con_nucleo=bool(con_mcp), canal=modo_chat.ESCRITORIO,
                              manos=str((env or {}).get("WORKSPACE_MANOS") or "") == "1")
    return modo_chat.guia(con_nucleo=bool(con_mcp))


def entrega(motor, env=None):
    """{"al_abrir", "tono"} si el núcleo se encarga en las sesiones de `motor` que abre este Workspace
    (paquete encendido y vía por sesión en su ficha); vacíos si no: el camino de hoy sigue igual. Lo usa
    el bloque de la pestaña, que se arma antes de lanzar (el entorno de la sesión aún no existe)."""
    out = {"al_abrir": "", "tono": ""}
    try:
        from arquitectura import contrato, sesion
        if not sesion.activo(env):
            return out
        f = contrato.ficha(motor)
        s = f.get("sesion") or {}
        if not s or "no" in s or s.get("sin_nucleo"):      # hooks5: solo sus hooks; el núcleo, como hoy
            return out
        n = f.get("nucleo") or {}
        out["al_abrir"] = n.get("al_abrir") if n.get("al_abrir") in VIAS_AL_ABRIR else ""
        via = str((n.get("tono") or {}).get("via") or "no")
        out["tono"] = via if via != "no" else ""
    except Exception:
        pass
    return out
