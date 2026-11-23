#!/usr/bin/env python3
"""WORKSPACE · arquitectura/sesion — el paquete v0 POR SESIÓN, al lanzar un motor (F1).

`para_lanzar(motor, cerebro, pestaña, argv, env)` lo llaman los dos caminos de
arranque de hoy (engines/claude_code.launch y interactive.run_official_cli_interactive)
justo antes de abrir el motor. Con el paquete encendido:

1. Instala el paquete en el estado de esta máquina (generado con arquitectura/generar,
   una carpeta por versión; {{RAIZ}} queda fijado a esa carpeta).
2. Lo carga por la vía por sesión de la ficha (`sesion`): argumentos (p. ej.
   `--plugin-dir`) y, si la ficha lo dice, archivos en la carpeta del proyecto (el
   cerebro) que no llevan rutas de la máquina. Nada en la config global del motor.
   F6: además el bloque `nucleo` de la ficha (arquitectura/nucleo.aplicar): el MCP núcleo
   declarado y preaprobado, el tono en la pieza de sistema y, en el entorno, por dónde va el
   paquete de la pestaña al abrir.
3. Fija el número oficial de la conversación (D3-a): el que el lanzador ya pasa
   (`--session-id`, `--resume`…) o uno nuevo si la ficha sabe crearlo; se guarda en
   la pestaña (registro de eventos) junto al atado de hoy, para compararlos. Si el
   motor no deja fijarlo, lo dice su hook de inicio.

Encendido de fábrica (el sistema nuevo). Se apaga con el ajuste `arquitectura.paquete`
o, para una corrida, con WORKSPACE_PAQUETE=0 (1 lo enciende). Apagado, nada cambia.
Falla-suave: si algo sale mal, el motor abre sin el paquete.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)
import paths as _paths  # noqa: E402
from arquitectura import contrato, generar, nucleo, registro  # noqa: E402

AJUSTE = "arquitectura.paquete"
_VERSIONES_GUARDADAS = 3


def activo(env=None):
    """¿Va el paquete por sesión? WORKSPACE_PAQUETE manda (1/0); si no, el ajuste (ON de fábrica: el sistema
    nuevo; quien lo apagó a mano queda apagado). Sin ajustes legibles, lo de fábrica."""
    env = os.environ if env is None else env
    v = str(env.get("WORKSPACE_PAQUETE") or "").strip()
    if v in ("0", "1"):
        return v == "1"
    try:
        import settings
        return bool(settings.enabled(AJUSTE, default=True))
    except Exception:
        return True


def _huella_fuente():
    """Cambia si cambia la fuente, las fichas, el contrato o el generador."""
    h = hashlib.sha1()
    for base in (generar.FUENTE, contrato.FICHAS):
        for d, ds, fs in os.walk(base):
            ds[:] = sorted(x for x in ds if x != "__pycache__")
            for f in sorted(fs):
                if f.endswith((".pyc", ".DS_Store")):
                    continue
                p = os.path.join(d, f)
                h.update(os.path.relpath(p, AQUI).encode("utf-8"))
                with open(p, "rb") as fh:
                    h.update(fh.read())
    for f in ("generar.py", "momentos.json"):
        with open(os.path.join(AQUI, f), "rb") as fh:
            h.update(fh.read())
    h.update(sys.executable.encode("utf-8"))        # el paquete lleva el Python de esta instalación
    return h.hexdigest()[:10]


def carpeta_paquetes():
    return os.path.join(_paths.state_dir(), "arquitectura", "paquete")


#: F7: el paquete de un cerebro con skills lleva su marca y la huella de sus skills (se rehace si cambian).
_DE_CEREBRO = re.compile(r"-c([0-9a-f]{6})-([0-9a-f]{10})$")
#: Un paquete de cerebro que nadie abrió en tanto tiempo se borra (el cerebro se movió o ya no está).
_CEREBRO_OLVIDADO_S = 30 * 24 * 3600
#: Un paquete usado en este tiempo no se borra aunque haya versiones más nuevas: una sesión abierta lo carga en
#: su sitio (si falta, cada hook sale con 2 y Claude Code bloquea cada herramienta y cada mensaje). Su hook lo
#: marca al abrir y con cada mensaje (lanzador/hook.marcar_en_uso).
_EN_USO_S = 7 * 24 * 3600


def carpeta_de(cerebro=None):
    """(carpeta del paquete de esta versión, ¿lleva las skills de `cerebro`?): la que `instalar(cerebro)` entrega, sin
    armar nada (Conexiones la revisa tal cual la cargan los motores)."""
    from arquitectura import skills_cerebro
    version = "%s-%s" % (generar._version(), _huella_fuente())
    con_skills = bool(cerebro) and bool(skills_cerebro.indice(cerebro))
    if con_skills:
        cid = hashlib.sha1(os.path.realpath(str(cerebro)).encode("utf-8")).hexdigest()[:6]
        version = "%s-c%s-%s" % (version, cid, skills_cerebro.huella(cerebro))
    return os.path.join(carpeta_paquetes(), version), con_skills


def instalar(cerebro=None, rehacer=False):
    """{formato: carpeta} del paquete de esta versión, generado si falta. Las
    versiones viejas se borran, salvo las últimas (un motor abierto la usa).
    F7: con `cerebro` y skills en su catálogo, el paquete de ESE cerebro (sus skills en
    skills/ de cada formato, arquitectura/skills_cerebro); sin skills, el de todos.
    `rehacer` (el arreglo de Conexiones): aunque esté «listo», se arma otra vez al lado y se cambia de golpe. Uno
    instalado que se dañó lo cargan los motores tal cual, y «listo» no lo volvía a armar nunca."""
    final, con_skills = carpeta_de(cerebro)
    base, version = os.path.dirname(final), os.path.basename(final)
    if os.path.isfile(os.path.join(final, ".listo")) and not rehacer:
        try:
            os.utime(final)                          # en uso: no se olvida
        except OSError:
            pass
    else:
        os.makedirs(base, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix=".armando-", dir=base)
        try:
            salidas = generar.armar(os.path.join(tmp, "p"), version=generar._version(),
                                    cerebro=cerebro if con_skills else None)
            for fmt in salidas:
                _fijar_raiz(os.path.join(tmp, "p", fmt), os.path.join(final, fmt))
            open(os.path.join(tmp, "p", ".listo"), "w").close()
            if rehacer and os.path.isdir(final):     # el dañado, a un lado: nunca un hueco donde lo cargan
                os.replace(final, os.path.join(tmp, "viejo"))
            if os.path.isdir(final):                 # uno a medias (sin .listo) no sirve
                shutil.rmtree(final, ignore_errors=True)
            try:
                os.replace(os.path.join(tmp, "p"), final)
            except OSError:
                if rehacer and not os.path.isdir(final):
                    os.replace(os.path.join(tmp, "viejo"), final)
                    raise
                # otro arranque lo dejó listo antes
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        _podar(base, version)
    return {f: os.path.join(final, f) for f in generar.FORMATOS}


def python():
    """El Python de Workspace (el que corre los hooks y el MCP del paquete), con «/»: dentro de un JSON o un YAML
    una «\\» de Windows («C:\\Users…») no es un escape válido y el archivo deja de leerse."""
    return sys.executable.replace("\\", "/")


def _fijar_raiz(armado, destino_final):
    """{{RAIZ}} → la carpeta donde queda instalado ese formato (como al instalar), y {{PY}} → el Python de
    Workspace; los dos con «/» (en Windows, una «\\» dentro de un JSON o un YAML lo deja ilegible). Las skills
    del cerebro (con el sello de Workspace) van tal cual."""
    from arquitectura import skills_cerebro
    raiz, py, ws = destino_final.replace("\\", "/"), python(), RAIZ_REPO.replace("\\", "/")
    for d, ds, fs in os.walk(armado):
        ds[:] = [x for x in ds if not skills_cerebro.es_nuestra(os.path.join(d, x))]
        for f in fs:
            if not f.endswith((".json", ".yaml", ".js")):
                continue
            p = os.path.join(d, f)
            with open(p, encoding="utf-8") as fh:
                t = fh.read()
            if generar.RAIZ in t or generar.PY in t or generar.WS in t:
                # {{WS}}: el Workspace que lo instaló (el plugin de OpenClaw: el gateway no hereda WORKSPACE_ROOT)
                with open(p, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(t.replace(generar.RAIZ, raiz).replace(generar.PY, py).replace(generar.WS, ws))


def _grupo(nombre):
    """El cerebro de un paquete (su marca) o '' si es el de todos."""
    m = _DE_CEREBRO.search(nombre)
    return m.group(1) if m else ""


def _podar(base, actual):
    """Borra las versiones viejas DEL MISMO GRUPO que `actual` (el paquete de todos, o el de un cerebro):
    abrir un cerebro nunca le quita el paquete a otro que tenga un motor abierto. Los de un cerebro que
    nadie abre hace _CEREBRO_OLVIDADO_S también se van."""
    import time
    grupo, ahora = _grupo(actual), time.time()
    viejas = sorted((n for n in os.listdir(base) if n != actual and not n.startswith(".")),
                    key=lambda n: os.path.getmtime(os.path.join(base, n)))
    mias = [n for n in viejas if _grupo(n) == grupo]
    fuera = [n for n in mias[:max(0, len(mias) - (_VERSIONES_GUARDADAS - 1))]
             if ahora - os.path.getmtime(os.path.join(base, n)) > _EN_USO_S]   # una en uso no se borra
    fuera += [n for n in viejas if _grupo(n) not in ("", grupo)
              and ahora - os.path.getmtime(os.path.join(base, n)) > _CEREBRO_OLVIDADO_S]
    for n in fuera:
        shutil.rmtree(os.path.join(base, n), ignore_errors=True)


def carpeta_lanzador():
    """hooks5: la carpeta FIJA del lanzador (no cambia entre versiones del paquete)."""
    return os.path.join(_paths.state_dir(), "arquitectura", "lanzador")


def lanzador_fijo(paquete_dir):
    """hooks5: el lanzador/ de esta versión del paquete, copiado a una carpeta que NO cambia entre versiones
    (carpeta_lanzador). Codex guarda la confianza de sus hooks por huella (D6, `[hooks.state…] trusted_hash`): con
    un comando que no cambia, la que el socio da UNA vez en /hooks sigue valiendo al actualizar Workspace (con la
    carpeta de la versión, cada actualización pedía confiar otra vez). Archivo por archivo, cada uno atómico y
    solo si cambió; la carpeta nunca desaparece (un hook que arranca justo entonces no encuentra un hueco: Python
    sin su script sale con 2, que en un hook antes de herramienta la NIEGA). → la carpeta, con «/»."""
    src, dst = os.path.join(paquete_dir, "lanzador"), carpeta_lanzador()
    os.makedirs(dst, exist_ok=True)
    for base, ds, fs in os.walk(src):
        ds[:] = [d for d in ds if d != "__pycache__"]
        rel = os.path.relpath(base, src)
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in fs:
            if f.endswith((".pyc", ".DS_Store")):
                continue
            with open(os.path.join(base, f), "rb") as fh:
                nuevo = fh.read()
            fin = os.path.join(dst, rel, f)
            try:
                with open(fin, "rb") as fh:
                    if fh.read() == nuevo:
                        continue
            except OSError:
                pass
            tmp = "%s.%d.tmp" % (fin, os.getpid())
            with open(tmp, "wb") as fh:
                fh.write(nuevo)
            os.replace(tmp, fin)
    return dst.replace("\\", "/")


def _copiar_paso(paso, valores, cerebro):
    """Un archivo de la ficha (`sesion.archivos`) en el proyecto: `copiar` → `a`, dentro del cerebro. Con
    `sustituir` (hooks5), el texto con esos reemplazos ({paquete}, {lanzador}…, con «/» como quedan en los
    archivos del paquete) y atómico; sin él, la copia tal cual (un archivo o una carpeta, como OpenCode).
    `sumar` (cable-cursor): reglas al final de las listas de un JSON del proyecto, sin pisar nada (nucleo._sumar)."""
    if "sumar" in paso:
        return nucleo._paso(paso, valores, cerebro)
    if "{lanzador}" in json.dumps(paso):
        valores.setdefault("lanzador", lanzador_fijo(valores["paquete"]))
    dst = _poner(paso["a"], valores)
    if not os.path.realpath(dst).startswith(os.path.realpath(str(cerebro)) + os.sep):
        raise ValueError("la ficha escribe fuera del cerebro: %s" % dst)
    src = _poner(paso["copiar"], valores)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if paso.get("sustituir"):
        barra = {k: str(v).replace("\\", "/") for k, v in valores.items()}
        with open(src, encoding="utf-8") as fh:
            texto = fh.read()
        for k, v in paso["sustituir"].items():
            texto = texto.replace(_poner(k, barra), _poner(v, barra))
        tmp = "%s.%d.tmp" % (dst, os.getpid())
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)
        os.replace(tmp, dst)
        return
    if os.path.isdir(src):
        _copiar_carpeta(src, dst)
        return
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copy2(src, dst)


def _archivos(carpeta):
    """{ruta relativa: bytes} de una carpeta (sin cachés), o None si no existe."""
    if not os.path.isdir(carpeta):
        return None
    out = {}
    for base, ds, fs in os.walk(carpeta):
        ds[:] = [d for d in ds if d != "__pycache__"]
        for f in fs:
            if f.endswith((".pyc", ".DS_Store")):
                continue
            ruta = os.path.join(base, f)
            with open(ruta, "rb") as fh:
                out[os.path.relpath(ruta, carpeta)] = fh.read()
    return out


def _copiar_carpeta(src, dst):
    """Una carpeta del paquete en el proyecto (el plugin de OpenCode o el de OpenClaw): si ya está igual, no se toca;
    si no, se arma al lado y se cambia de golpe. Un motor que la tiene cargada (el gateway de OpenClaw abre su MCP y sus
    avisos desde ahí en cada sesión) nunca la ve a medias ni vacía: con rmtree + copytree, un aviso que arrancaba justo
    entonces no encontraba su lanzador."""
    if _archivos(src) == _archivos(dst):
        return
    padre = os.path.dirname(dst)
    os.makedirs(padre, exist_ok=True)
    # lo temporal, un nivel arriba: dentro de la carpeta de plugins, el motor lo vería como otro plugin
    junto = os.path.dirname(padre)
    nuevo = tempfile.mkdtemp(prefix=".ws-nuevo-", dir=junto)
    viejo = None
    try:
        shutil.rmtree(nuevo)
        shutil.copytree(src, nuevo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        if os.path.isdir(dst):
            viejo = tempfile.mkdtemp(prefix=".ws-viejo-", dir=junto)
            os.rmdir(viejo)
            os.replace(dst, viejo)
        try:
            os.replace(nuevo, dst)
        except OSError:
            if viejo:
                respaldo, viejo = viejo, None
                os.replace(respaldo, dst)
            raise
    finally:
        for d in (nuevo, viejo):
            if d and os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)


def _cablea_hooks_de_hoy(cerebro):
    """¿El cerebro ya corre el hook de hoy por su cuenta (settings de Claude Code)?
    Entonces el paquete NO lo corre otra vez: solo anota el registro."""
    for f in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(str(cerebro), ".claude", f), encoding="utf-8") as fh:
                if "workspace_hook.py" in fh.read():
                    return True
        except OSError:
            continue
    return False


def _poner(texto, valores):
    for k, v in valores.items():
        texto = texto.replace("{%s}" % k, v)
    return texto


def _id_en(argv, flags):
    """(número, flag) que ya trae el argv (`--flag X` o `--flag=X`), o ('', '')."""
    for i, a in enumerate(argv):
        for f in flags:
            if a == f and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                return argv[i + 1], f
            if a.startswith(f + "="):
                return a.split("=", 1)[1], f
    return "", ""


def _sin_id(argv, flags):
    """El argv sin los números que trae (`--flag X` o `--flag=X`, de las flags de la ficha)."""
    out, saltar = [], False
    for i, a in enumerate(argv):
        if saltar:
            saltar = False
            continue
        if a in flags and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            saltar = True
            continue
        if any(a.startswith(f + "=") for f in flags):
            continue
        out.append(a)
    return out


def anotar_log(texto):
    """Una línea en state_dir/logs/numero-oficial.log (lo junta el paquete de diagnóstico). Nunca levanta."""
    try:
        import time
        d = os.path.join(_paths.state_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "numero-oficial.log"), "a", encoding="utf-8") as fh:
            fh.write("%s · %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), texto))
    except Exception:
        pass


def _con_numero_oficial(motor, cerebro, pestana, argv, ident):
    """F5 · (argv, info): si la pestaña ya tiene número oficial en este motor (registro.numero_de), el argv lo
    lleva y ningún otro: lo retoma (`id.retoma`) si el motor ya lo usó, o lo crea con ese número (`id.crea`)
    la primera vez. Lo que había puesto el lanzador (su atado de hoy, o la adivinanza) sale, y se dice en el
    log si era otro. Sin número oficial, o si la ficha no sabe pasarlo: el argv tal cual.

    Si el lanzador ya trae ESE número, su argv se deja (él sabe si el motor lo tiene: retomar o crear). Si trae
    OTRO, se cambia solo cuando el motor ya confirmó el oficial en sus hooks (`visto`): uno que solo se le pasó
    al abrir y nunca dijo no basta para pisar lo que el lanzador sabe (crear un número que el motor ya tiene
    falla)."""
    oficial, visto = registro.numero_de(cerebro, pestana, motor)
    info = {"numero": oficial, "visto": visto, "como": ""}
    flags = tuple(ident.get("flags") or ())
    if not oficial or not flags:
        return argv, info
    antes, _f = _id_en(argv, flags)
    if antes == oficial or (antes and not visto):
        info["como"] = "el del lanzador"
        return argv, info
    flag = ident.get("retoma") if visto else (ident.get("crea") or ident.get("retoma"))
    if not flag:
        return argv, info
    argv = _sin_id(argv, flags)
    argv[1:1] = [flag, oficial]
    info["como"] = flag
    if antes and antes != oficial:
        anotar_log("%s · %s · reabre con su número oficial %s (el lanzador traía %s)" % (motor, pestana, oficial,
                                                                                       antes))
    return argv, info


def _skills_de_la_sesion(via, valores, cerebro):
    """F7: las skills del cerebro en el menú / del motor, por la vía de su ficha (`sesion.skills`):
    «paquete» = ya van en sus skills/; «proyecto» = la vista plana en esa carpeta del cerebro (solo las
    carpetas con el sello de Workspace se rehacen o se quitan; una del socio con el mismo nombre gana).
    → {"via", "skills": [nombres], …lo que hizo reflejar}."""
    from arquitectura import skills_cerebro
    origen = os.path.join(valores["paquete"], "skills")
    nuestras = sorted(n for n in (os.listdir(origen) if os.path.isdir(origen) else ())
                      if skills_cerebro.es_nuestra(os.path.join(origen, n)))
    out = {"via": via.get("via") or "", "skills": nuestras}
    if via.get("via") == "proyecto":
        dst = _poner(via.get("ruta") or "", valores)
        if not dst or not os.path.realpath(dst).startswith(os.path.realpath(str(cerebro)) + os.sep):
            raise ValueError("la ficha pone las skills fuera del cerebro: %s" % dst)
        out.update(skills_cerebro.reflejar(origen, dst))
    return out


def _preparar(ref, cerebro, pestana, argv, env, valores, ficha):
    """cable-hermes: la función «módulo:función» de la ficha (`sesion.preparar`) para lo de la sesión que no cabe en
    argumentos ni archivos del proyecto (el perfil propio del agente, en un motor que guarda todo en su perfil).
    → (argv, env, info). Si levanta, el motor abre como hoy (para_lanzar)."""
    import importlib
    modulo, funcion = ref.split(":", 1)
    return getattr(importlib.import_module(modulo), funcion)(cerebro, pestana, list(argv), dict(env), valores,
                                                            ficha=ficha)


def preparar_proyecto(motor, cerebro, ficha=None, env=None):
    """arq-default: lo que la vía por sesión deja en la carpeta del proyecto (sus archivos y la vista de skills de la
    ficha), sin tocar el argv: para la página, cuyo motor lee el mismo proyecto (Codex por su app-server, OpenCode por
    su servidor, Cursor por ACP). Así da igual qué se abre primero, la terminal o la página. → lo hecho; [] si está
    apagado o el motor no deja nada en el proyecto. Levanta si la ficha escribe fuera del cerebro."""
    if not activo(env):
        return []
    ficha = ficha or contrato.ficha(motor)
    s = ficha.get("sesion") or {}
    via = s.get("skills") or {}
    if not s or "no" in s or not (s.get("archivos") or via.get("via") == "proyecto"):
        return []
    pkg = instalar(cerebro)
    valores = {"paquete": pkg[ficha["paquete"]["formato"]], "cerebro": str(cerebro), "python": python()}
    hecho = []
    if via.get("via") == "proyecto":
        _skills_de_la_sesion(via, valores, cerebro)
        hecho.append("skills")
    for paso in s.get("archivos") or ():
        _copiar_paso(paso, valores, cerebro)
        hecho.append(paso["a"])
    return hecho


def para_lanzar(motor, cerebro, pestana, argv, env, ficha=None, nuevo_id=None):
    """(argv, env, info) para abrir `motor` con el paquete por sesión. Si está
    apagado, el motor no tiene vía por sesión o algo falla: lo de siempre, y
    info["paquete"] = False con el motivo."""
    originales = (list(argv), dict(env))
    argv, env = list(argv), dict(env)
    info = {"paquete": False, "motivo": "", "numero": "", "fuente": "", "nucleo": {}}
    try:
        if not activo(env):
            info["motivo"] = "apagado"
            return argv, env, info
        ficha = ficha or contrato.ficha(motor)
        s = ficha.get("sesion") or {}
        if not s or contrato.sin_via(s):
            info["motivo"] = contrato.sin_via(s) or "la ficha no trae vía por sesión"
            return argv, env, info
        if len(argv) > 1 and argv[1] in (s.get("salvo") or ()):
            info["motivo"] = "subcomando %s" % argv[1]
            return argv, env, info
        pkg = instalar(cerebro)                   # F7: el de este cerebro, con sus skills
        valores = {"paquete": pkg[ficha["paquete"]["formato"]], "cerebro": str(cerebro), "python": python()}
        info["skills"] = _skills_de_la_sesion(s.get("skills") or {}, valores, cerebro)
        for paso in s.get("archivos") or ():
            _copiar_paso(paso, valores, cerebro)
        if s.get("preparar"):                # cable-hermes: el perfil propio del agente (Hermes)
            argv, env, info["perfil"] = _preparar(s["preparar"], cerebro, pestana, argv, env, valores, ficha)
        argv = argv[:1] + [_poner(a, valores) for a in s.get("argv") or ()] + argv[1:]
        # F6: el MCP núcleo preaprobado, el tono en la pieza de sistema y por dónde va el paquete al abrir. hooks5:
        # una ficha con `sin_nucleo` carga solo sus hooks; el núcleo sigue por el camino de hoy (y se dice por qué)
        if s.get("sin_nucleo"):
            info["nucleo"] = {"no": s["sin_nucleo"]}
            if s.get("mcp_del_nucleo"):
                # arq-default: el servidor MCP del núcleo sí va por sesión (el paquete al abrir y el tono, como hoy)
                argv, env, info["nucleo"]["mcp"] = nucleo.solo_mcp(motor, cerebro, argv, env, valores, ficha=ficha)
        else:
            argv, env, info["nucleo"] = nucleo.aplicar(motor, cerebro, argv, env, valores, ficha=ficha)
        # F7: los permisos de la sesión desde la autonomía que eligió el socio (ficha · permisos.niveles)
        from arquitectura import permisos
        argv, env, info["permisos"] = permisos.aplicar(motor, cerebro, argv, env, valores, ficha=ficha)
        ident = s.get("id") or {}
        # F5 (D3-a): con número oficial, la pestaña se reabre con ESE y nada más (lo que trajo el lanzador, fuera)
        if pestana:
            argv, info["oficial"] = _con_numero_oficial(motor, cerebro, pestana, argv, ident)
            # F5: la maleta desde los eventos, antes de que el arranque la lea (también si la última sesión se
            # cortó sin session_end)
            from arquitectura import maleta
            info["maleta"] = maleta.al_abrir(cerebro, pestana, env.get("WORKSPACE_WS") or "")
        numero, flag = _id_en(argv, ident.get("flags") or ())
        fuente = ("fijado" if flag in (ident.get("fija") or ()) else "retomada") if numero else ""
        if not numero and ident.get("crea"):
            numero, fuente = (nuevo_id or (lambda: str(uuid.uuid4())))(), "fijado"
            argv[1:1] = [ident["crea"], numero]
        env["WORKSPACE_PAQUETE"] = "1"
        env["WORKSPACE_BRAIN"] = str(cerebro)
        env.setdefault("WORKSPACE_ROOT", RAIZ_REPO)
        if motor == "claude-code" and not _cablea_hooks_de_hoy(cerebro):
            env["WORKSPACE_PAQUETE_HOOKS"] = "1"
        if pestana and numero:
            registro.conversacion(cerebro, pestana, motor, numero, fuente,
                                  paquete=os.path.basename(os.path.dirname(valores["paquete"])),
                                  ws=env.get("WORKSPACE_WS") or "")
        # cable-cursor: la aprobación de SOLO nuestro servidor MCP, con el entorno ya final (el motor la ata a su config
        # resuelta); en un motor sin `nucleo.mcp.aprobar`, nada
        aprobado = nucleo.aprobar(motor, cerebro, argv, env, ficha=ficha) if not s.get("sin_nucleo") else None
        if aprobado is not None and isinstance(info.get("nucleo"), dict):
            info["nucleo"]["aprobado"] = aprobado
        info.update(paquete=True, numero=numero, fuente=fuente or "hook_inicio")
        return argv, env, info
    except Exception as e:                     # el motor abre como hoy
        info.update(paquete=False, motivo="error: %s" % e)
        return originales[0], originales[1], info
