"""Modo escritorio · lo que el agente hace SIN preguntar en la conversación del monito (decisión del dueño, 21-nov).

En la conversación del monito de escritorio (WORKSPACE_VIA=escritorio) el agente lee lo que hay en tu pantalla, que
escribieron otros. Por eso ahí, sin tarjeta, solo:
  · las manos (contexto_escritorio, leer_ventana, ver_pantalla, senalar: ver y señalar, nunca hacer clic; y encargar:
    proponer un encargo, que solo pasa con tu clic en la tarjeta de la app) y, si la app del monito la prendió,
    `actuar` (A0): pasa sin la tarjeta de Workspace porque la que decide es la de la APP (armada con lo que dice el
    sistema: un OK = una acción y un destino; lo rojo, nunca). Una sola tarjeta, la buena; con dos, el socio
    aprobaría dos veces lo mismo y la confianza por app no serviría;
  · preguntar, mostrar_archivo y memoria_nota (la nota va marcada como del monito) del núcleo, y contar su avance,
    decir en qué está y usar una de sus skills (reportar_avance, tarea_actual, usar_skill: solo cuentan y nombran);
  · leer dentro de su carpeta (su cerebro): Read, Glob, Grep… con la ruta adentro; un comando que solo lee con todas
    sus rutas adentro (`cat BRAIN.md`, `sed -n 1,80p BOOT/00-SOUL.md`, `rg -n x STATE`: así arranca Codex, y antes
    cada agente pedía una tarjeta por leer su propio cerebro), también entubados o encadenados (`cd deliverables &&
    grep -rl x . | head`, `2>/dev/null`); y lo que solo lee del núcleo (memoria_buscar,
    memoria_ver, pendientes, skills_lista, skill_leer).
TODO lo demás (comandos, escribir, internet, otras herramientas, leer fuera de su carpeta) pide la tarjeta de permiso
de la burbuja, aunque el agente o su motor estén en automático. La página y la terminal no cambian.

Lo usan el aviso de antes de cada herramienta (hook.py: Claude Code, con «ask»: su vía oficial para preguntar aunque una
regla lo permita) y la capa de control (control/propias: lo que el motor pregunta por ACP, Codex y OpenCode).
Solo stdlib y sin Workspace (corre aunque el harness no esté). Nunca levanta: ante la duda, pregunta."""
import glob
import os
import re
import shlex

VIA = "escritorio"
#: Las manos del monito (el servidor «escritorio», escritorio/manos_mcp.py).
#: …y encargar (E1): solo PROPONE un encargo a su conversación de trabajo; la app enseña su tarjeta (lo que pediste, el
#: archivo y dónde queda) y nada pasa sin tu clic. Como preguntar: libre.
#: …y `actuar` (A0): solo existe si la app la prende, y su OK es la tarjeta de la app
#: (escritorio/mac/…/Seguridad.swift), no la de Workspace.
MANOS = ("contexto_escritorio", "leer_ventana", "ver_pantalla", "senalar", "encargar", "actuar",
         # ronda 2, carril 6 (manos de trabajo): como actuar, su OK es la ficha de la app del monito (su portero)
         "buscar_archivo", "abrir", "redactar_correo")
#: Del núcleo, las que no hacen nada fuera de la plática: preguntarte, enseñarte un archivo y anotar; y (Monito UX,
#: 22-nov) contarte cómo va, decir en qué está y usar una de sus skills a la vista: solo cuentan y nombran (lo que la
#: skill haga después pasa por su propia tarjeta). En la prueba del dueño, 6 de 36 tarjetas eran «contarte cómo va».
NUCLEO_LIBRES = ("preguntar", "mostrar_archivo", "memoria_nota", "reportar_avance", "tarea_actual", "usar_skill")
#: Del núcleo, las que solo leen su cerebro (su carpeta).
NUCLEO_LEE = ("memoria_buscar", "memoria_ver", "pendientes", "skills_lista", "skill_leer")
LIBRES_NUCLEO = NUCLEO_LIBRES + NUCLEO_LEE
#: Claude Code: lo que no sale de la conversación (cargar herramientas, su lista de tareas, leer una skill).
INTERNAS_CLAUDE = ("ToolSearch", "TodoWrite", "TodoRead", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "Skill")
#: Claude Code: lo que lee (libre solo con la ruta dentro de su carpeta).
LECTURA_CLAUDE = ("Read", "Glob", "Grep", "LS", "NotebookRead")
#: Cómo llama Claude Code a esos servidores: el núcleo va en el plugin del paquete; las manos, por --mcp-config.
PREFIJOS_NUCLEO = ("mcp__plugin_workspace_workspace__", "mcp__workspace__", "mcp__workspace-memoria__")
PREFIJO_MANOS = "mcp__escritorio__"
MOTIVO = ("En Compañero, Workspace te pregunta antes de todo lo que no es ver, señalar, preguntarte, enseñarte un "
          "archivo, anotar o leer en su carpeta: lo que el agente leyó de tu pantalla lo escribieron otros.")


def es_escritorio(env):
    return str((env or {}).get("WORKSPACE_VIA") or "").strip() == VIA


#: Monito ronda 2 · E8 (22-nov): desde la burbuja un agente lanzó 5 ayudantes en segundo plano y dijo «te aviso». Cada
#: búsqueda de cada ayudante era una tarjeta; a los 12 minutos murieron con un permiso a medias, sin guardar nada, y
#: nadie avisó. En el monito NO hay ayudantes (ni en primer plano ni en segundo): lo largo es un encargo (su
#: conversación de trabajo, con sus permisos dichos una vez, y el monito avisa al terminar) o sigue en la página.
#: La herramienta de ayudantes de cada motor, por su nombre entero (Claude Code: «Agent», antes «Task»; OpenCode y
#: Copilot: «task»; Kiro: «use_subagent»…). Su lista de tareas (TaskCreate, TodoWrite…) no es esto.
AYUDANTES = ("agent", "task", "subagent", "use_subagent", "spawn_agent", "spawn_subagent", "delegate_task",
             "dispatch_agent", "run_subagent")
SIN_AYUDANTES = ("En Compañero no hay ayudantes ni trabajos en segundo plano: no sobreviven a la burbuja y nadie le "
                 "avisaría a tu socio. Si es algo corto, hazlo tú aquí mismo. Si es largo, propónselo con encargar "
                 "(lo hace tu conversación de trabajo y el monito le avisa al terminar) o dile que lo siga en la "
                 "página. No le digas «te aviso» por algo que no dejaste encargado.")


def es_ayudante(nombre):
    """¿Ese nombre de herramienta (el entero, como lo manda el motor) es la de lanzar ayudantes?"""
    n = str(nombre or "").strip().lower().replace("-", "_").replace(" ", "_")
    return n in AYUDANTES


def sin_ayudantes(payload, env):
    """El motivo para NEGAR la herramienta de ayudantes en la conversación del monito, o '' (no es el monito o no es
    esa herramienta). Lo usan el aviso de antes de cada herramienta (hook.py: todos los motores con aviso) y la capa
    de control (control/base). Nunca levanta."""
    try:
        if not es_escritorio(env):
            return ""
        p = payload if isinstance(payload, dict) else {}
        nombre = p.get("tool_name") or p.get("toolName") or p.get("tool") or ""
        if not nombre and isinstance(p.get("toolCall") or p.get("tool_call"), dict):
            nombre = (p.get("toolCall") or p.get("tool_call")).get("name") or ""
        return SIN_AYUDANTES if es_ayudante(nombre) else ""
    except Exception:
        return ""


def dentro(ruta, carpeta, cwd=None):
    """¿`ruta` (relativa a `cwd` o a `carpeta`) cae dentro de `carpeta`? Un enlace que sale, sale."""
    try:
        if not ruta or not carpeta:
            return False
        r = os.path.expanduser(str(ruta))
        if not os.path.isabs(r):
            r = os.path.join(str(cwd or carpeta), r)
        base, real = os.path.realpath(str(carpeta)), os.path.realpath(r)
        return real == base or real.startswith(base.rstrip(os.sep) + os.sep)
    except Exception:
        return False


#: Los comandos que solo leen (y con qué opciones dejarían de hacerlo: escribir, correr otra cosa, no terminar).
SOLO_LEEN = {"cat": (), "head": (), "tail": ("-f", "-F", "--follow"), "wc": (), "nl": (), "ls": (), "pwd": (),
             "stat": (), "file": ("-C", "--compile"), "tree": ("-o", "-R"), "grep": (), "egrep": (), "fgrep": (),
             "rg": ("--pre", "--pre-glob", "--search-zip", "-z"),
             "find": ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"),
             "sed": ("-i", "--in-place", "-f", "--file"),
             # Monito UX (22-nov): lo que solo ordena, corta o mide lo que lee
             "sort": ("-o", "--output", "--compress-program", "-T", "--temporary-directory"), "cut": (), "uniq": (),
             "du": (), "realpath": ()}
#: Los que no tocan archivos: sus argumentos son texto (no se revisan como rutas).
SIN_ARCHIVOS = ("echo", "printf", "tr", "basename", "dirname", "true", "false")
#: Encadenar (cada tramo tiene que solo leer) y entubar.
_SEPARADORES = ("&&", "||", ";", "|")
#: Redirigir: solo a /dev/null (o juntar la salida de error con la normal).
_A_LA_NADA = (">", ">>", "&>", "&>>", "2>", "2>>")
#: `zsh -lc '…'`, `bash -c "…"`: el comando de adentro (así los manda Codex).
_ENVUELTO = re.compile(r"^\s*(?:/usr)?(?:/bin/)?(?:zsh|bash|sh)\s+-l?c\s+(['\"])(.*)\1\s*$", re.S)
#: Lo que viene después de `$` y la shell lo cambia por otra cosa (una variable, un comando, un número…).
_EXPANDE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_0123456789{(@*#?$!-")
_COMODIN = re.compile(r"[*?\[]")
_PROHIBIDOS = {}


def _prohibido(comando, env=None):
    """El motivo si el comando toca un secreto (el mismo aviso que lo niega en el hook), o ''."""
    try:
        if "m" not in _PROHIBIDOS:
            import importlib.util
            ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prohibidos.py")
            spec = importlib.util.spec_from_file_location("workspace_prohibidos_escritorio", ruta)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            _PROHIBIDOS["m"] = m
        return _PROHIBIDOS["m"].motivo({"tool_name": "Bash", "tool_input": {"command": comando}}, env)
    except Exception:
        return "no se pudo revisar"


def _sin_expansiones(c):
    """¿El comando no trae nada que la shell cambie por otra cosa fuera de comillas simples? (variables, `$(…)`,
    acentos graves, llaves {a,b}, saltos de línea). Ante la duda, no."""
    simple = doble = False
    i = 0
    while i < len(c):
        ch = c[i]
        if ch == "\\" and not simple:
            i += 2
            continue
        if ch == "'" and not doble:
            simple = not simple
        elif ch == '"' and not simple:
            doble = not doble
        elif not simple:
            if ch in "`\n\r":
                return False
            if ch == "$" and i + 1 < len(c) and c[i + 1] in _EXPANDE:
                return False
            if not doble and ch == "{":
                return False
        i += 1
    return not simple and not doble


def _tokens(c):
    lex = shlex.shlex(c, posix=True, punctuation_chars="();<>|&")
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def _ruta_adentro(ruta, carpeta, cwd):
    """Una ruta de un comando: adentro de su carpeta (con un comodín, TODO lo que abriría la shell, también por un
    enlace)."""
    if _COMODIN.search(ruta):
        base = os.path.expanduser(ruta)
        patron = base if os.path.isabs(base) else os.path.join(str(cwd or carpeta), base)
        try:
            hallados = glob.glob(patron)[:500]
        except (OSError, ValueError, re.error):
            return False
        if hallados:
            return all(dentro(h, carpeta) for h in hallados)
    return dentro(ruta, carpeta, cwd=cwd)


_SED_IMPRIME = re.compile(r"^[0-9$,]*[pq]$|^[0-9$,]*$")


def _sed_seguro(guion):
    """Un guion de sed que solo imprime (`1,80p`) o sustituye sin escribir ni correr nada (`s/a/b/g`)."""
    for parte in guion.split(";"):
        p = parte.strip()
        if not p or _SED_IMPRIME.match(p):
            continue
        m = re.match(r"^[0-9$,]*s(.)", p)
        if not m or m.group(1).isalnum() or m.group(1) in " \\\n":
            return False
        d, j, campos = m.group(1), m.end(), 0
        while j < len(p) and campos < 2:
            if p[j] == "\\":
                j += 2
                continue
            if p[j] == d:
                campos += 1
            j += 1
        if campos < 2 or not re.fullmatch(r"[gpiI0-9]*", p[j:]):
            return False
    return True


def _tramo_que_solo_lee(partes, carpeta, cwd):
    """Un comando (sus palabras, sin redirecciones). → (solo lee, la carpeta en que queda: `cd` la cambia)."""
    if not partes:
        return False, cwd
    prog = os.path.basename(partes[0])
    args = partes[1:]
    if prog == "cd":
        if len(args) != 1 or args[0] == "-":
            return False, cwd
        destino = os.path.normpath(os.path.join(str(cwd or carpeta), os.path.expanduser(args[0])))
        if not dentro(destino, carpeta) or not os.path.isdir(destino):
            return False, cwd
        return True, destino
    if prog in SIN_ARCHIVOS:
        return True, cwd
    if prog not in SOLO_LEEN:
        return False, cwd
    malas = SOLO_LEEN[prog]
    guiones, posicionales = [], []
    saltar = False
    for i, x in enumerate(args):
        if saltar:
            saltar = False
            guiones.append(x)
            continue
        op = x.split("=", 1)[0]
        if op in malas or (prog == "find" and op.startswith("-fprint")) or (prog == "sed" and x.startswith("-i")):
            return False, cwd
        # una opción larga abreviada (getopt acepta un prefijo único: `--o=x` es `--output=x`) y un `-` solo (la
        # entrada estándar: `uniq - salida` escribe `salida`): tarjeta
        if x == "-" or (x.startswith("--") and len(op) > 2 and any(m.startswith(op) for m in malas if m.startswith("--"))):
            return False, cwd
        # una opción corta que escribe, pegada a su valor (`sort -oSALIDA`) o entre otras (`sort -ro SALIDA`): la
        # letra en cualquier lugar del grupo. Las de `find` son palabras con un guion: van por nombre, arriba.
        if prog != "find" and x.startswith("-") and not x.startswith("--") and len(x) > 2 and \
                {m[1] for m in malas if len(m) == 2 and m[0] == "-"} & set(x[1:]):
            return False, cwd
        if prog == "sed" and x in ("-e", "--expression"):
            saltar = True
            continue
        if prog == "sed" and x.startswith("-") and x not in ("-n", "-E", "-r", "--quiet", "--silent", "-u"):
            return False, cwd
        if x.startswith("-"):
            if "=" in x and not _ruta_adentro(x.split("=", 1)[1], carpeta, cwd):
                return False, cwd
            continue
        posicionales.append(x)
    if prog == "sed":
        if not guiones:
            if not posicionales:
                return False, cwd
            guiones, posicionales = [posicionales[0]], posicionales[1:]
        if not all(_sed_seguro(g) for g in guiones):
            return False, cwd
    if prog == "uniq" and len(posicionales) > 1:
        return False, cwd                                    # `uniq entrada salida` escribe la salida
    for ruta in posicionales:
        if not _ruta_adentro(ruta, carpeta, cwd):
            return False, cwd
    return True, cwd


def comando_que_solo_lee(comando, carpeta, cwd=None):
    """¿`comando` solo lee, y todo lo que nombra está dentro de `carpeta`? (cat, head, sed -n, rg, ls…, solos,
    entubados con `|` o encadenados con `&&`, `;` y `||`, con `cd` a una carpeta de adentro y la salida de error a
    /dev/null; sin escribir a un archivo, variables ni sustituciones; sin rutas que salgan ni secretos). Monito UX
    (22-nov): antes un `|` entre comillas, un `cd … &&` o un `2>/dev/null` pedían tarjeta. Ante la duda, no: pasa
    por la tarjeta. Nunca levanta."""
    try:
        c = str(comando or "").strip()
        m = _ENVUELTO.match(c)
        if m:
            c = m.group(2).strip()
        if not c or not carpeta or len(c) > 2000 or not _sin_expansiones(c) or _prohibido(c):
            return False
        toks = _tokens(c)
        aqui = cwd or carpeta
        tramo = []
        toks.append(";")
        i = 0
        while i < len(toks):
            t = toks[i]
            if t in _SEPARADORES:
                if not tramo:
                    return False
                ok, aqui = _tramo_que_solo_lee(tramo, carpeta, aqui)
                if not ok:
                    return False
                tramo = []
            elif t in (">", ">>", "&>", "&>>"):
                if i + 1 >= len(toks) or toks[i + 1] != "/dev/null":
                    return False
                if tramo and tramo[-1] in ("1", "2"):
                    tramo.pop()                                # «2>/dev/null»: el 2 es la salida de error
                i += 1
            elif t == ">&":
                if i + 1 >= len(toks) or toks[i + 1] not in ("1", "2") or not tramo or tramo[-1] not in ("1", "2"):
                    return False
                tramo.pop()                                    # «2>&1»
                i += 1
            elif t and set(t) <= set("();<>|&"):
                return False                                   # fondo, subshell, leer de un archivo, >|…
            elif not tramo and "=" in t and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
                return False                                   # FOO=1 cmd: otro entorno
            else:
                tramo.append(t)
            i += 1
        return True
    except Exception:
        return False


def libre_mcp(nombre):
    """¿Es (por su nombre completo de Claude Code) una de las libres del monito?"""
    n = str(nombre or "")
    if n.startswith(PREFIJO_MANOS):
        return n[len(PREFIJO_MANOS):] in MANOS
    for p in PREFIJOS_NUCLEO:
        if n.startswith(p):
            return n[len(p):] in LIBRES_NUCLEO
    return False


def permitidas_claude():
    """Lo que va en --allowedTools de una corrida del monito en Claude Code (en lugar de todo el núcleo)."""
    return (["mcp__plugin_workspace_workspace__%s" % h for h in LIBRES_NUCLEO]
            + ["%s%s" % (PREFIJO_MANOS, h) for h in MANOS])


def claude_pregunta(payload, env):
    """El aviso de antes de cada herramienta en Claude Code: '' si pasa como siempre; si no, el motivo para pedirte
    permiso (el hook contesta «ask»). Solo en la conversación del monito."""
    try:
        if not es_escritorio(env):
            return ""
        p = payload if isinstance(payload, dict) else {}
        nombre = str(p.get("tool_name") or "")
        entrada = p.get("tool_input") if isinstance(p.get("tool_input"), dict) else {}
        if not nombre or libre_mcp(nombre) or nombre in INTERNAS_CLAUDE:
            return ""
        if nombre == "Bash":
            carpeta = (env or {}).get("WORKSPACE_BRAIN") or p.get("cwd") or ""
            if comando_que_solo_lee(entrada.get("command"), carpeta, cwd=p.get("cwd") or carpeta):
                return ""
            return MOTIVO
        if nombre in LECTURA_CLAUDE:
            carpeta = (env or {}).get("WORKSPACE_BRAIN") or p.get("cwd") or ""
            ruta = entrada.get("file_path") or entrada.get("notebook_path") or entrada.get("path") or ""
            patron = str(entrada.get("pattern") or "")
            if not ruta and patron.startswith(("/", "~")):
                ruta = patron                                        # un comodín con su ruta entera
            if not ruta and nombre in ("Glob", "Grep", "LS"):
                ruta = p.get("cwd") or carpeta                       # sin ruta: busca en su carpeta (cwd)
            if dentro(ruta, carpeta, cwd=p.get("cwd")):
                return ""
        return MOTIVO
    except Exception:
        return MOTIVO
