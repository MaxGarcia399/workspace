#!/usr/bin/env python3
"""WORKSPACE · escritorio/frases — lo que el monito dice de lo que hace su agente, en simple (Monito UX, 22-nov).

La primera prueba de verdad del dueño: 36 tarjetas en un turno, y cada una con el comando crudo («Quiere correr un
comando: «cd "/Users/…" && grep -rl …»»). No sabía si darle permiso o no. Aquí, una frase por pedido: QUÉ quiere hacer,
SOBRE QUÉ y, si se sabe, PARA QUÉ. Lo técnico va aparte (`detalle`), para quien abra «Ver detalle».

  permiso(pm, carpeta="", tarea="") → {"texto", "ya", "detalle", "grupo"}
      pm: el permiso de la página ({id, herramienta, detalle, archivo, opciones, que: {clase, comando, ruta, fuera},
      grupo?}); carpeta: su cerebro (para decir las rutas desde ahí); tarea: en qué está (tarea_actual), si se sabe.
      texto «Quiere leer el archivo «Ventas.xlsx» de tu carpeta Descargas.» · ya «Le diste permiso para …» ·
      grupo: lo que ofrece «Sí, y lo demás en …» (permitir_turno) o None.
  hace(nombre, detalle, archivo="", carpeta="") → «Leyendo «README.md»» (lo que está haciendo, para «Haciendo: …»)
  comando(cmd, carpeta="") → «leer «BRAIN.md»» (lo que hace un comando, en infinitivo)
  licencia(raw, carpeta="") → {"texto", "usadas", "ultima"} (lo que el socio dejó pasar en este trabajo)

Puro: stdlib, sin Workspace, nunca levanta (ante la duda, la frase general y el detalle)."""
import json
import os
import re
import shlex
from urllib.parse import urlparse

#: «Sí, y lo demás en esta carpeta (solo este trabajo)»: la decisión que además deja pasar lo del mismo tipo en esa
#: carpeta mientras dure el turno (control/base: la licencia del turno).
DECISION_TURNO = "permitir_turno"
TOPE = 60

#: Las carpetas de su cerebro con su nombre de todos los días.
CARPETAS = {"deliverables": "Entregas", "STATE": "su memoria", "skills": "sus habilidades", "BOOT": "su identidad",
            "wiki": "su wiki"}
#: Las de tu carpeta personal.
CASA = {"Downloads": "tu carpeta Descargas", "Desktop": "tu Escritorio", "Documents": "tu carpeta Documentos",
        "Pictures": "tu carpeta Imágenes", "Movies": "tu carpeta Películas", "Music": "tu carpeta Música"}
TEMPORALES = ("/tmp/", "/private/tmp/", "/var/folders/", "/private/var/folders/")
IMAGEN = re.compile(r"\.(png|jpe?g|gif|webp|svg|heic|bmp|tiff?)$", re.I)

#: Del núcleo de Workspace y de las manos del monito: (lo que pide, lo que está haciendo).
NUCLEO = {
    "reportar_avance": ("contarte cómo va", ""),
    "tarea_actual": ("decirte en qué está", ""),
    "usar_skill": ("usar su habilidad {skill}", "Usando su habilidad {skill}"),
    "skill_leer": ("leer su habilidad {skill}", "Leyendo su habilidad {skill}"),
    "skills_lista": ("ver qué habilidades tiene", "Revisando sus habilidades"),
    "memoria_nota": ("anotar algo en su memoria", "Anotando en su memoria"),
    "memoria_checkpoint": ("guardar en su memoria el resumen de esta plática", "Guardando el resumen en su memoria"),
    "memoria_ver": ("repasar su memoria", "Repasando su memoria"),
    "memoria_buscar": ("buscar en su memoria", "Buscando en su memoria"),
    "pendientes": ("revisar sus pendientes", "Revisando sus pendientes"),
    "preguntar": ("preguntarte algo", "Preguntándote algo"),
    "mostrar_archivo": ("enseñarte un archivo", "Enseñándote un archivo"),
    "personalizar": ("cambiar cómo se ve (su color o su forma)", "Cambiando cómo se ve"),
}
MANOS = {
    "contexto_escritorio": ("saber qué tienes enfrente", "Viendo qué tienes enfrente"),
    "leer_ventana": ("leer tu ventana", "Leyendo tu ventana"),
    "ver_pantalla": ("ver tu pantalla", "Mirando tu pantalla"),
    "senalar": ("señalarte algo en la pantalla", "Señalándote algo"),
    "encargar": ("proponerte un encargo", "Preparando un encargo"),
    "actuar": ("hacer algo en tu Mac (con tu OK)", "Esperando tu OK para hacerlo"),
    # ronda 2 (H-4): las manos de trabajo
    "buscar_archivo": ("buscar un archivo tuyo por su nombre", "Buscando el archivo"),
    "abrir": ("abrir un documento tuyo (con tu OK)", "Esperando tu OK para abrirlo"),
    "redactar_correo": ("prepararte un borrador de correo (no lo envía)", "Preparando el borrador"),
}
#: Lo de adentro del motor que no hace nada fuera de la plática.
INTERNAS = {"ToolSearch": ("preparar sus herramientas", ""), "TodoWrite": ("ordenar sus pasos", "Ordenando sus pasos"),
            "TodoRead": ("repasar sus pasos", ""), "Task": ("pedirle ayuda a un ayudante", "Trabajando con un ayudante"),
            "Agent": ("pedirle ayuda a un ayudante", "Trabajando con un ayudante"),
            "Skill": ("usar una de sus habilidades", "Usando una de sus habilidades")}
SERVIDORES = {"workspace": "nucleo", "workspace-memoria": "nucleo", "workspace_memoria": "nucleo", "escritorio": "manos"}

GERUNDIO = {"leer": "Leyendo", "buscar": "Buscando", "correr": "Corriendo", "crear": "Creando", "copiar": "Copiando",
            "mover": "Moviendo", "borrar": "Borrando", "cambiar": "Cambiando", "revisar": "Revisando",
            "guardar": "Guardando", "subir": "Subiendo", "bajar": "Bajando", "descargar": "Descargando",
            "mandar": "Mandando", "abrir": "Abriendo", "instalar": "Instalando", "desinstalar": "Desinstalando",
            "escribir": "Escribiendo", "esperar": "Esperando", "cerrar": "Cerrando", "comprimir": "Comprimiendo",
            "descomprimir": "Descomprimiendo", "convertir": "Convirtiendo", "compilar": "Compilando", "usar": "Usando",
            "enseñarte": "Enseñándote", "tomar": "Tomando", "juntar": "Juntando", "empezar": "Empezando",
            "conectarse": "Conectándose", "controlar": "Controlando", "deshacer": "Deshaciendo", "ver": "Viendo",
            "procesar": "Procesando", "anotar": "Anotando", "preguntarte": "Preguntándote", "repasar": "Repasando"}


# ── ayudantes ────────────────────────────────────────────────────────────────
def _q(s, tope=TOPE):
    s = " ".join(str(s or "").split())
    return "«%s»" % (s if len(s) <= tope else s[:tope - 1] + "…")


def _datos(detalle):
    if isinstance(detalle, dict):
        return detalle
    try:
        d = json.loads(detalle)
        return d if isinstance(d, dict) else None
    except (TypeError, ValueError):
        return None


def _campo(detalle, *claves):
    """Un campo de su entrada: del JSON entero o, si la página lo recortó, del texto (`"clave": "valor"`)."""
    d = _datos(detalle)
    for k in claves:
        if d is not None:
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
            continue
        m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % re.escape(k), str(detalle or ""))
        if m:
            try:
                return json.loads('"%s"' % m.group(1)).strip()
            except ValueError:
                return m.group(1).strip()
    return ""


def _humano(s):
    """«front-end/movimiento-pixel-web» → «movimiento pixel web»; «buscar_archivos» → «buscar archivos»."""
    s = str(s or "").strip().rstrip("/").split("/")[-1]
    return re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", s)).strip()


def _dominio(url):
    try:
        h = urlparse(url if "://" in url else "https://" + url).hostname or ""
    except ValueError:
        h = ""
    h = h[4:] if h.startswith("www.") else h
    return h or str(url)[:40]


def _dentro(p, carpeta):
    try:
        base = os.path.realpath(carpeta)
        real = os.path.realpath(p)
        return real == base or real.startswith(base.rstrip(os.sep) + os.sep)
    except (OSError, ValueError, TypeError):
        return False


def _casa():
    return os.path.expanduser("~").rstrip(os.sep)


def _sitio_rel(rel_dir):
    """Una carpeta de su cerebro (relativa) → «su carpeta» o «Entregas › presentacion-clientes»."""
    partes = [x for x in str(rel_dir or "").replace("\\", "/").split("/") if x and x != "."]
    if not partes:
        return "su carpeta"
    partes[0] = CARPETAS.get(partes[0], partes[0])
    if len(partes) > 3:
        partes = partes[:1] + ["…"] + partes[-2:]
    return " › ".join(partes)


def _sitio_fuera(ruta_dir):
    """Una carpeta fuera de su cerebro → «tu carpeta Descargas», «una carpeta temporal de tu Mac»…"""
    p = str(ruta_dir or "")
    casa = _casa()
    if p.startswith("~"):
        p = casa + p[1:]
    pp = p.rstrip("/") + "/"
    tmp = os.environ.get("TMPDIR") or ""
    if not pp.startswith(casa + "/") and (pp.startswith(TEMPORALES) or (tmp and pp.startswith(tmp.rstrip("/") + "/"))):
        return "una carpeta temporal de tu Mac"
    if pp.startswith(casa + "/"):
        partes = [x for x in pp[len(casa) + 1:].split("/") if x]
        if not partes:
            return "tu carpeta personal"
        nombre = CASA.get(partes[0])
        if nombre:
            return nombre + ("" if len(partes) == 1 else " › " + " › ".join(partes[1:][-2:]))
        return "la carpeta %s de tu Mac, fuera de su carpeta" % _q(partes[-1])
    nombre = os.path.basename(p.rstrip("/")) or p
    return "la carpeta %s de tu Mac, fuera de su carpeta" % _q(nombre)


def _es_fuera(ruta, fuera, carpeta):
    """¿La ruta (como la da la página: relativa a su cerebro, o ~/… y entera fuera) está fuera de su cerebro?"""
    r = os.path.expanduser(str(ruta or "").strip())
    if fuera is None and carpeta and os.path.isabs(r):
        return not _dentro(r, carpeta)
    if fuera is None:
        return os.path.isabs(r)
    return bool(fuera)


def _rel(ruta, carpeta):
    r = os.path.expanduser(str(ruta or "").strip())
    if carpeta and os.path.isabs(r):
        return os.path.relpath(os.path.realpath(r), os.path.realpath(carpeta))
    return r


def _donde(ruta, fuera, carpeta):
    """(nombre del archivo, su lugar en simple) de una ruta como la da la página (relativa a su cerebro, o ~/… fuera)."""
    r = str(ruta or "").strip()
    if not r:
        return "", ""
    nombre = os.path.basename(r.rstrip("/\\")) or r
    if _es_fuera(r, fuera, carpeta):
        return nombre, _sitio_fuera(os.path.dirname(r.rstrip("/\\")))
    return nombre, _sitio_rel(os.path.dirname(_rel(r, carpeta).rstrip("/\\")))


def _de(sitio):
    return "de " + sitio


def _en(sitio):
    return "en " + sitio


# ── los comandos ─────────────────────────────────────────────────────────────
_ENVUELTO = re.compile(r"^\s*(?:/usr)?(?:/bin/)?(?:zsh|bash|sh)\s+-l?c\s+(['\"])(.*)\1\s*$", re.S)
_SEPARA = ("&&", "||", ";", "\n")
FILTROS = {"head", "tail", "sort", "uniq", "cut", "tr", "wc", "grep", "egrep", "fgrep", "rg", "sed", "awk", "jq",
           "less", "more", "cat", "column", "nl", "fold", "fmt", "rev", "tac", "paste", "tee"}
LEEN = {"cat", "head", "tail", "less", "more", "nl", "wc", "bat", "strings", "xxd", "hexdump", "od", "md5",
        "shasum", "sha256sum", "md5sum", "jq", "awk", "column", "plutil"}
VEN = {"ls", "tree", "find", "du", "stat", "file", "exa", "eza", "fd"}
BUSCAN = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}
#: Las opciones que traen su valor aparte (para no confundirlo con un archivo).
CON_VALOR = {"head": {"-n", "-c"}, "tail": {"-n", "-c"}, "grep": {"-e", "-f", "-m", "-A", "-B", "-C", "--include",
                                                                  "--exclude", "--exclude-dir"},
             "rg": {"-e", "-f", "-g", "-t", "-T", "-m", "-A", "-B", "-C", "--glob", "--type", "--max-count"},
             "sed": {"-e", "-f"}, "cut": {"-c", "-f", "-d", "-b"}, "sort": {"-k", "-t", "-o"},
             "du": {"-d"}, "find": set(), "python": {"-m", "-c", "-W", "-X"}, "node": {"-e", "-r", "--require"},
             "curl": {"-o", "-X", "-d", "-H", "-F", "-u", "-A", "-e", "-T", "--data", "--header", "--output",
                      "--request", "--upload-file", "--form"},
             "wget": {"-O", "-o", "-P"}, "open": {"-a", "-b"}, "tree": {"-L", "-I", "-P"}}


def _tokens(c):
    lex = shlex.shlex(c, posix=True, punctuation_chars="();<>|&")
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def _posicionales(args, prog):
    """Los argumentos que no son opciones (ni el valor de una opción que lo trae aparte)."""
    out, saltar = [], False
    valor = CON_VALOR.get(re.sub(r"[0-9.]+$", "", prog), set())
    for a in args:
        if saltar:
            saltar = False
            continue
        if a.startswith("-") and a != "-":
            if a in valor:
                saltar = True
            continue
        out.append(a)
    return out


class _Ctx:
    def __init__(self, carpeta):
        self.carpeta = carpeta or ""
        self.cwd = carpeta or ""


def _cosa(tok, ctx, carpeta_si_vacio=False):
    """Un archivo o carpeta de un comando → «nombre» (o «su carpeta», «Entregas»…), dicho desde su cerebro."""
    t = str(tok or "").strip()
    if not t or t in (".", "./"):
        if ctx.cwd and ctx.carpeta and _dentro(ctx.cwd, ctx.carpeta):
            rel = os.path.relpath(os.path.realpath(ctx.cwd), os.path.realpath(ctx.carpeta))
            if rel == ".":
                return "su carpeta"
            partes = rel.split(os.sep)
            return _q(CARPETAS.get(partes[0], partes[0]) if len(partes) == 1 else partes[-1])
        if ctx.cwd and ctx.cwd != ctx.carpeta and os.path.basename(ctx.cwd.rstrip("/")):
            return _q(os.path.basename(ctx.cwd.rstrip("/")))
        return "su carpeta"
    if ctx.carpeta:
        p = os.path.normpath(os.path.join(ctx.cwd or ctx.carpeta, os.path.expanduser(t)))
        if _dentro(p, ctx.carpeta):
            rel = os.path.relpath(os.path.realpath(p), os.path.realpath(ctx.carpeta))
            if rel == ".":
                return "su carpeta"
            partes = rel.split(os.sep)
            if len(partes) == 1 and partes[0] in CARPETAS:
                return _q(CARPETAS[partes[0]])
            return _q(partes[-1])
    if t in ("~", "~/"):
        return "tu carpeta personal"
    if t == "..":
        return "la carpeta de arriba"
    return _q(os.path.basename(t.rstrip("/")) or t)


def _lista(cosas, y="y"):
    cosas = [c for c in cosas if c]
    if not cosas:
        return ""
    if len(cosas) == 1:
        return cosas[0]
    if len(cosas) <= 3:
        return ", ".join(cosas[:-1]) + " " + y + " " + cosas[-1]
    return ", ".join(cosas[:2]) + " y %d más" % (len(cosas) - 2)


def _url_de(args):
    for a in args:
        if re.match(r"^[a-z][a-z0-9+.-]*://", a, re.I) or re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", a):
            return a
    return ""


def _paso(palabras, ctx, redir=""):
    """Un comando (sus palabras) → lo que hace, en infinitivo; None si no cuenta (cd, export); '?' si no se sabe."""
    while palabras and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", palabras[0]):
        palabras = palabras[1:]                                  # FOO=1 cmd
    if not palabras:
        return None
    prog = os.path.basename(palabras[0])
    args = palabras[1:]
    pos = _posicionales(args, prog)
    if prog in ("cd", "pushd", "popd"):
        if pos:
            ctx.cwd = os.path.normpath(os.path.join(ctx.cwd or ctx.carpeta or "/", os.path.expanduser(pos[0])))
        return None
    if prog in ("export", "set", "unset", "true", "false", "alias", ":"):
        return None
    if prog == "sudo":
        return "correr algo como administrador de tu Mac"
    if prog in ("bash", "sh", "zsh") and len(args) >= 2 and args[0] in ("-c", "-lc"):
        return _frase_de(args[1], ctx)
    if prog in ("echo", "printf"):
        return ("escribir un texto en %s" % _cosa(redir, ctx)) if redir else _ECO
    if prog == "sed":
        pos = [x for x in pos if x]                              # «sed -i ''» (el de la Mac): sin copia de respaldo
        archivos = pos if any(a in ("-e", "-f") for a in args) else pos[1:]
        if any(a in ("-i", "--in-place") or a.startswith("-i") for a in args):
            return "cambiar " + (_lista([_cosa(x, ctx) for x in archivos]) or "un archivo")
        return "leer " + (_lista([_cosa(x, ctx) for x in archivos]) or "un texto")
    if prog in LEEN:
        archivos = pos[1:] if prog in ("awk", "jq") else pos
        return "leer " + (_lista([_cosa(x, ctx) for x in archivos]) or "un texto")
    if prog in BUSCAN:
        pat = ""
        for i, a in enumerate(args):
            if a in ("-e", "--regexp") and i + 1 < len(args):
                pat = args[i + 1]
        resto = pos if pat else pos[1:]
        pat = pat or (pos[0] if pos else "")
        recursivo = prog in ("rg", "ag", "ack") or any(re.match(r"^-[a-zA-Z]*[rR]", a) or a == "--recursive"
                                                       for a in args)
        donde = _lista([_cosa(x, ctx) for x in resto]) or ("su carpeta" if not ctx.cwd else _cosa(".", ctx)) \
            if (resto or recursivo) else ""
        return "buscar " + (_q(pat, 40) if pat else "algo") + (" en " + donde if donde else "")
    if prog in VEN:
        if prog == "find":
            dirs = []
            for a in args:
                if a.startswith(("-", "(", "!")):
                    break
                dirs.append(a)
            if "-delete" in args:
                return "borrar archivos en " + (_lista([_cosa(x, ctx) for x in dirs]) or "su carpeta")
            if any(a in ("-exec", "-execdir", "-ok") for a in args):
                return "correr algo con cada archivo de " + (_lista([_cosa(x, ctx) for x in dirs]) or "su carpeta")
            pos = dirs
        return "ver qué hay en " + (_lista([_cosa(x, ctx) for x in pos]) or _cosa(".", ctx, True))
    if re.match(r"^python[0-9.]*$", prog) or prog in ("pypy", "pypy3"):
        if "-c" in args:
            return "correr un programa de Python"
        if "-m" in args:
            i = args.index("-m")
            mod = args[i + 1] if i + 1 < len(args) else ""
            if mod == "pip" and "install" in args[i + 2:]:
                return _instalar([x for x in args[i + 2:] if not x.startswith("-") and x != "install"])
            return "correr %s de Python" % _q(mod) if mod else "correr un programa de Python"
        if pos and pos[0] == "-":
            return "correr un programa de Python"                # lo lee de lo que sigue (un «heredoc»)
        return ("correr el programa de Python %s" % _cosa(pos[0], ctx)) if pos else "abrir Python"
    if prog in ("node", "deno", "bun", "ruby", "perl", "php", "swift", "lua", "Rscript"):
        if prog in ("deno", "bun") and pos and pos[0] in ("run", "x"):
            pos = pos[1:]
        if any(a in ("-e", "--eval") for a in args) or not pos:
            return "correr un programa"
        return "correr el programa %s" % _cosa(pos[0], ctx)
    if prog in ("bash", "sh", "zsh", "source", "."):
        return ("correr el programa %s" % _cosa(pos[0], ctx)) if pos else "abrir una terminal"
    if prog == "osascript":
        return "controlar otra app de tu Mac (AppleScript)"
    if prog == "mkdir":
        cs = [_cosa(x, ctx) for x in pos]
        return ("crear la carpeta " if len(cs) == 1 else "crear las carpetas ") + (_lista(cs) or "nueva")
    if prog == "touch":
        return "crear el archivo " + (_lista([_cosa(x, ctx) for x in pos]) or "nuevo")
    if prog in ("cp", "mv", "rsync", "ditto"):
        verbo = "mover" if prog == "mv" else "copiar"
        remoto = any(re.match(r"^[\w.-]+@?[\w.-]*:", x) for x in pos)
        if remoto:
            return "copiar archivos a otra computadora"
        if len(pos) >= 2:
            src = pos[:-1]
            q = _cosa(src[0], ctx) if len(src) == 1 else "%d archivos" % len(src)
            return "%s %s a %s" % (verbo, q, _cosa(pos[-1], ctx))
        return verbo + " un archivo"
    if prog in ("rm", "rmdir", "unlink", "trash", "srm"):
        if prog == "trash":
            return "mandar " + (_lista([_cosa(x, ctx) for x in pos]) or "algo") + " a la Papelera"
        r = any(re.match(r"^-[a-zA-Z]*[rR]", a) or a == "--recursive" for a in args)
        return "borrar " + (_lista([_cosa(x, ctx) for x in pos]) or "un archivo") + (" y lo que tiene" if r else "")
    if prog in ("chmod", "chown", "chgrp", "xattr", "chflags"):
        return "cambiar los permisos de " + (_lista([_cosa(x, ctx) for x in pos[1:] or pos]) or "un archivo")
    if prog == "ln":
        return "crear un acceso a " + (_cosa(pos[0], ctx) if pos else "un archivo")
    if prog == "git":
        sub = pos[0] if pos else ""
        if sub in ("status", "diff", "log", "show", "blame", "branch", "shortlog", "describe", "rev-parse", "ls-files"):
            return "revisar sus cambios con git"
        if sub in ("add", "commit", "tag"):
            return "guardar cambios con git"
        if sub == "push":
            return "subir cambios con git a internet"
        if sub in ("pull", "fetch", "clone"):
            return "bajar cambios con git de internet"
        if sub in ("restore", "checkout", "switch", "reset", "stash", "clean", "rm", "mv"):
            return "cambiar archivos con git"
        if sub in ("merge", "rebase", "cherry-pick"):
            return "juntar cambios con git"
        if sub == "init":
            return "empezar a guardar cambios con git"
        return "usar git"
    if prog in ("curl", "wget", "http", "https", "xh"):
        url = _url_de(pos) or _url_de(args)
        dom = (" (%s)" % _q(_dominio(url))) if url else ""
        manda = any(a in ("-d", "--data", "--data-raw", "--data-binary", "-F", "--form", "-T", "--upload-file") or
                    a.startswith(("--data", "-d")) for a in args) or \
            any(args[i] in ("-X", "--request") and i + 1 < len(args) and args[i + 1].upper() in ("POST", "PUT",
                                                                                             "DELETE", "PATCH")
                for i in range(len(args)))
        return ("mandar datos a internet" if manda else "descargar algo de internet") + dom
    if prog in ("ssh", "scp", "sftp", "telnet", "nc"):
        return "conectarse a otra computadora"
    if prog == "open":
        if "-R" in args:
            return "enseñarte %s en Finder" % (_cosa(pos[0], ctx) if pos else "un archivo")
        for i, a in enumerate(args):
            if a == "-a" and i + 1 < len(args):
                return "abrir %s" % _q(args[i + 1])
        url = _url_de(pos)
        if url and "://" in url and not url.startswith("file:"):
            return "abrir la página %s" % _q(_dominio(url))
        return "abrir " + (_lista([_cosa(x, ctx) for x in pos]) or "algo")
    if prog in ("npm", "pnpm", "yarn", "bun", "pip", "pip3", "brew", "apt", "apt-get", "gem", "cargo", "port",
                "pipx", "uv", "conda", "mas"):
        sub = pos[0] if pos else ""
        if sub in ("install", "i", "add", "ci", "upgrade", "update", "reinstall"):
            return _instalar(pos[1:] if not (prog == "brew" and len(pos) > 1 and pos[1] == "--cask") else pos[2:])
        if sub in ("uninstall", "remove", "rm", "un"):
            return "desinstalar " + (_lista([_q(x) for x in pos[1:]]) or "algo")
        if sub in ("run", "exec", "x", "dlx") and len(pos) > 1:
            return "correr %s del proyecto" % _q(pos[1])
        return "usar %s" % _q(prog)
    if prog in ("npx", "bunx", "pnpx"):
        return "correr %s" % (_q(pos[0]) if pos else "un programa")
    if prog == "date":
        return "ver la hora"
    if prog == "sleep":
        return "esperar un momento"
    if prog in ("which", "whereis", "type") or (prog == "command" and "-v" in args):
        return "ver si tiene %s instalado" % (_lista([_q(x) for x in pos]) or "un programa")
    if prog == "pwd":
        return "ver en qué carpeta está"
    if prog in ("kill", "pkill", "killall"):
        return ("cerrar %s" % _q(pos[0])) if prog == "killall" and pos else "cerrar un programa"
    if prog in ("ps", "top", "lsof", "pgrep"):
        return "ver qué programas están abiertos"
    if prog == "defaults":
        return "leer un ajuste de tu Mac" if (pos[:1] == ["read"]) else "cambiar un ajuste de tu Mac"
    if prog == "tccutil":
        return "cambiar los permisos de privacidad de tu Mac"
    if prog == "screencapture":
        return "tomar una foto de tu pantalla"
    if prog in ("zip", "tar", "gzip", "bzip2", "xz", "7z"):
        if prog == "tar" and args and re.match(r"^-?[a-zA-Z]*x", args[0]):
            return "descomprimir " + (_cosa(pos[0], ctx) if pos else "un archivo")
        return "comprimir " + (_lista([_cosa(x, ctx) for x in pos[1:] or pos]) or "archivos")
    if prog in ("unzip", "gunzip", "bunzip2", "unxz"):
        return "descomprimir " + (_cosa(pos[0], ctx) if pos else "un archivo")
    if prog in ("convert", "magick", "sips", "ffmpeg", "pandoc", "soffice", "libreoffice", "qlmanage", "textutil"):
        return "convertir " + (_cosa(pos[0], ctx) if pos else "un archivo")
    if prog in ("make", "cmake", "xcodebuild", "gcc", "clang", "cc", "go", "javac", "tsc"):
        return "compilar un programa"
    if prog == "docker":
        return "usar Docker"
    if prog == "xargs":
        dentro = [x for x in args if not x.startswith("-")]
        p = _paso(dentro, ctx) if dentro else None
        return (p + " con cada archivo de la lista") if p and p != "?" else "correr algo con cada archivo de la lista"
    if prog in ("sort", "uniq", "cut", "tr", "column", "fold", "rev", "tac", "paste", "basename", "dirname",
                "realpath"):
        return "leer " + (_lista([_cosa(x, ctx) for x in pos]) or "un texto")
    if prog == "tee":
        return "guardar un texto en " + (_lista([_cosa(x, ctx) for x in pos]) or "un archivo")
    return "correr el programa %s" % _q(prog, 40)


#: echo/printf sin guardar nada: solo enseña un texto (no cuenta como paso si hay otros).
_ECO = "enseñar un texto"


def _instalar(paquetes):
    ps = [p for p in paquetes if p and not p.startswith("-")]
    return "instalar " + (_lista([_q(p, 40) for p in ps]) if ps else "lo que pide el proyecto")


def _frase_de(cmd, ctx, solo_el_primero=False):
    """Un comando entero → una frase en infinitivo («leer «BRAIN.md»», «correr 3 pasos: …»); con `solo_el_primero`,
    su primer paso (para «Haciendo: …»)."""
    c = str(cmd or "").strip()
    m = _ENVUELTO.match(c)
    if m:
        c = m.group(2).strip()
    if "<<" in c:
        c = c.split("\n", 1)[0]                              # un «heredoc»: lo de abajo es lo que lee, no otro paso
    if not c or "`" in c or "$(" in c or "<(" in c or len(c) > 4000:
        return "?"
    try:
        toks = _tokens(c)
    except ValueError:
        return "?"
    pasos, tramo, tubo = [], [], []

    def cerrar_tubo():
        if tramo:
            tubo.append(list(tramo))
            tramo[:] = []
        if not tubo:
            return
        frases = []
        for i, t in enumerate(tubo):
            palabras, redir, j = [], "", 0
            while j < len(t):
                x = t[j]
                if x in (">", ">>", "&>", "&>>", ">|"):
                    destino = t[j + 1] if j + 1 < len(t) else ""
                    if destino != "/dev/null":
                        redir = destino
                    if palabras and palabras[-1] in ("1", "2"):
                        palabras.pop()
                    j += 2
                    continue
                if x in ("<", ">&", "<&", "<<", "<<<"):
                    if palabras and palabras[-1] in ("1", "2") and x == ">&":
                        palabras.pop()
                    j += 2
                    continue
                if x in ("(", ")", "&"):
                    j += 1
                    continue
                palabras.append(x)
                j += 1
            prog = os.path.basename(palabras[0]) if palabras else ""
            if i > 0 and prog in FILTROS and not redir and prog != "tee":
                continue                                      # «| head -15»: solo recorta lo de antes
            f = _paso(palabras, ctx, redir)
            if f is None:
                continue
            if redir and f != "?" and not f.startswith("escribir") and "guardar" not in f:
                f += " y guardarlo en %s" % _cosa(redir, ctx)
            frases.append(f)
        tubo[:] = []
        for f in frases:
            if f not in pasos:
                pasos.append(f)

    for t in toks:
        if t in _SEPARA:
            cerrar_tubo()
        elif t == "|":
            tubo.append(list(tramo))
            tramo[:] = []
        else:
            tramo.append(t)
    cerrar_tubo()
    if not pasos:
        return "?"
    if "?" in pasos:
        return "?"
    if len(pasos) > 1:
        pasos = [p for p in pasos if p != _ECO] or pasos
    pasos = _juntar(pasos)
    if len(pasos) == 1 or solo_el_primero:
        return pasos[0]
    if len(pasos) == 2:
        return pasos[0] + " y " + pasos[1]
    return "correr %d pasos: %s, %s y %d más" % (len(pasos), pasos[0], pasos[1], len(pasos) - 2)


_VERBOS_JUNTABLES = ("ver qué hay en ", "leer ", "crear la carpeta ", "borrar ", "abrir ")


def _juntar(pasos):
    """«ver qué hay en «a»» + «ver qué hay en «b»» → «ver qué hay en «a» y «b»» (los mismos verbos, juntos)."""
    out = []
    for p in pasos:
        v = next((x for x in _VERBOS_JUNTABLES if p.startswith(x) and p[len(x):].startswith("«")), None)
        if out and v and out[-1][0] == v and " y " not in p[len(v):] and len(out[-1][1]) < 4:
            out[-1][1].append(p[len(v):])
            continue
        out.append([v, [p[len(v):]] if v else [p]])
    return [(v + _lista(cs)) if v else cs[0] for v, cs in out]


def comando(cmd, carpeta=""):
    """Lo que hace un comando, en infinitivo y sin código: «leer «BRAIN.md»», «buscar «v4» en «Entregas»». '' si no
    se sabe (entonces se dice «correr un comando en tu Mac»)."""
    try:
        f = _frase_de(cmd, _Ctx(carpeta))
    except Exception:
        f = "?"
    return "" if f == "?" else f


def _gerundio(inf):
    """«leer «x»» → «Leyendo «x»»; «ver qué hay en …» → «Mirando qué hay en …»."""
    if not inf:
        return ""
    if inf.startswith("ver qué hay en"):
        return "Mirando" + inf[3:]
    m = re.match(r"^correr (\d+) pasos: (.*)$", inf)
    if m:
        return "Haciendo %s pasos: %s" % (m.group(1), m.group(2))
    palabra, _, resto = inf.partition(" ")
    g = GERUNDIO.get(palabra)
    return (g + (" " + resto if resto else "")) if g else inf[:1].upper() + inf[1:]


# ── las herramientas MCP ─────────────────────────────────────────────────────
def _mcp(nombre):
    """(servidor, herramienta) de un nombre MCP («mcp__plugin_workspace_workspace__x», «mcp__srv__x», «workspace/x»,
    el mensaje de Codex «Allow the workspace MCP server to run tool "x"?»), o None."""
    n = str(nombre or "").strip()
    m = re.match(r'^Allow the ([\w.-]+) MCP server to run tool "([\w.-]+)"\?$', n)
    if m:
        return m.group(1), m.group(2)
    if n.startswith("mcp__"):
        partes = n[5:].split("__", 1)
        if len(partes) == 2:
            srv = partes[0]
            if srv.startswith("plugin_"):
                srv = srv.split("_")[-1]
            return srv, partes[1]
    m = re.match(r"^@?([\w-]+)[/:]\s*([\w.-]+)$", n)
    if m:
        return m.group(1), m.group(2)
    for srv in SERVIDORES:
        for sep in ("_", "-", "."):
            if n.startswith(srv + sep) and n[len(srv) + 1:] in NUCLEO.keys() | MANOS.keys():
                return srv, n[len(srv) + 1:]
    return None


def _de_mcp(nombre, detalle):
    """(lo que pide, lo que está haciendo) de una herramienta MCP, o None si no es MCP."""
    h = _mcp(nombre)
    if not h:
        return None
    srv, herr = h
    tipo = SERVIDORES.get(srv) or ("nucleo" if herr in NUCLEO and srv.startswith("workspace") else "")
    tabla = NUCLEO if tipo == "nucleo" else MANOS if tipo == "manos" else None
    if tabla is not None and herr in tabla:
        skill = _campo(detalle, "skill", "nombre", "name")
        inf, ger = tabla[herr]
        if "{skill}" in inf:
            if skill:
                inf, ger = inf.format(skill=_q(_humano(skill))), ger.format(skill=_q(_humano(skill)))
            else:
                inf = inf.replace("su habilidad {skill}", "una de sus habilidades")
                ger = ger.replace("su habilidad {skill}", "una de sus habilidades")
        return inf, ger
    if tabla is not None:
        return "usar una de las herramientas de Workspace", "Usando una herramienta de Workspace"
    return ("usar %s de la conexión %s" % (_q(_humano(herr)), _q(srv)),
            "Usando %s de %s" % (_q(_humano(herr)), _q(srv)))


# ── un permiso, en simple ────────────────────────────────────────────────────
_CLASE_DE_NOMBRE = {"read": "leer", "notebookread": "leer", "write": "crear", "edit": "cambiar", "multiedit": "cambiar",
                    "notebookedit": "cambiar", "grep": "buscar", "glob": "buscar", "ls": "buscar", "bash": "comando",
                    "shell": "comando", "comando": "comando", "webfetch": "web", "websearch": "web"}


def _tecnico(pm):
    detalle = pm.get("detalle")
    d = _datos(detalle)
    if d is not None:
        detalle = json.dumps(d, ensure_ascii=False, indent=2)
    q = pm.get("que") if isinstance(pm.get("que"), dict) else {}
    partes = [str(pm.get("herramienta") or "")]
    if q.get("comando") and q["comando"] not in str(detalle or ""):
        partes.append(str(q["comando"]))
    partes.append(str(detalle or ""))
    return "\n".join(x for x in partes if x.strip())[:1500]


def _lo_que_pide(pm, carpeta):
    """El infinitivo de lo que pide («leer el archivo «x» de tu carpeta Descargas»), o '' si no se sabe."""
    herr = str(pm.get("herramienta") or "")
    detalle = pm.get("detalle")
    q = pm.get("que") if isinstance(pm.get("que"), dict) else {}
    mcp = _de_mcp(herr, detalle)
    if mcp:
        return mcp[0]
    if herr in INTERNAS:
        return INTERNAS[herr][0]
    clase = str(q.get("clase") or "") or _CLASE_DE_NOMBRE.get(herr.lower().replace(" ", ""), "")
    if clase in ("", "otra"):
        clase = _CLASE_DE_NOMBRE.get(herr.lower().replace(" ", ""), clase)
    if clase == "comando":
        cmd = q.get("comando") or _campo(detalle, "command", "cmd") or (detalle if isinstance(detalle, str) and
                                                                        _datos(detalle) is None else "")
        return comando(cmd, carpeta) or "correr un comando en tu Mac"
    if clase == "web":
        url = _campo(detalle, "url")
        if url:
            return "abrir la página %s en internet" % _q(_dominio(url))
        consulta = _campo(detalle, "query", "q")
        return ("buscar en internet: %s" % _q(consulta)) if consulta else "usar internet"
    ruta = q.get("ruta") or pm.get("archivo") or _campo(detalle, "file_path", "filePath", "path", "notebook_path")
    if clase == "buscar":
        pat = _campo(detalle, "pattern", "query", "glob")
        if not ruta:
            lugar = "sus archivos"
        elif _es_fuera(ruta, q.get("fuera"), carpeta):
            lugar = _sitio_fuera(ruta)
        else:
            lugar = _sitio_rel(_rel(ruta, carpeta))
        return "buscar %s en %s" % (_q(pat, 40), lugar) if pat else "buscar en " + lugar
    nombre, sitio = _donde(ruta, q.get("fuera"), carpeta)
    if clase in ("leer", "crear", "cambiar", "borrar"):
        if not nombre:
            return {"leer": "leer un archivo", "crear": "crear un archivo", "cambiar": "cambiar un archivo",
                    "borrar": "borrar un archivo"}[clase]
        if clase == "leer":
            que = "ver la imagen" if IMAGEN.search(nombre) else "leer el archivo"
            return "%s %s %s" % (que, _q(nombre), _de(sitio))
        if clase == "crear":
            return "crear el archivo %s %s" % (_q(nombre), _en(sitio))
        if clase == "cambiar":
            return "cambiar el archivo %s %s" % (_q(nombre), _de(sitio))
        return "borrar el archivo %s %s" % (_q(nombre), _de(sitio))
    return ""


def _grupo(pm, carpeta):
    g = pm.get("grupo")
    if not isinstance(g, dict) or g.get("clase") != "escribir":
        return None
    sitio = _sitio_rel(g.get("carpeta") or "")
    return {"clase": "escribir", "carpeta": str(g.get("carpeta") or ""), "decision": DECISION_TURNO,
            "texto": "Sí, y lo demás en «%s»" % sitio,
            "nota": "Solo mientras hace este trabajo: crear y cambiar archivos ahí. Lo de otras carpetas te lo sigue "
                    "preguntando."}


def permiso(pm, carpeta="", tarea=""):
    """El permiso que pide su motor, en simple: {"texto", "ya", "detalle", "grupo"} (ver arriba). Nunca levanta."""
    pm = pm if isinstance(pm, dict) else {}
    try:
        inf = _lo_que_pide(pm, carpeta)
    except Exception:
        inf = ""
    inf = inf or "usar una de sus herramientas"
    para = (" para %s" % _q(tarea, 80)) if str(tarea or "").strip() else ""
    try:
        grupo = _grupo(pm, carpeta)
    except Exception:
        grupo = None
    return {"texto": "Quiere %s%s." % (inf, para), "ya": "Le diste permiso para %s." % inf,
            "detalle": _tecnico(pm), "grupo": grupo}


# ── lo que está haciendo ─────────────────────────────────────────────────────
def hace(nombre, detalle="", archivo="", carpeta=""):
    """Lo que está haciendo ahora, para «Haciendo: …» («Leyendo «README.md»»). '' si no hay nada útil que decir."""
    try:
        n = str(nombre or "")
        mcp = _de_mcp(n, detalle)
        if mcp:
            return mcp[1]
        if n == "herramienta MCP":                              # Codex: su detalle es el nombre de la herramienta
            for tabla in (MANOS, NUCLEO):
                if str(detalle or "") in tabla:
                    return tabla[str(detalle)][1]
            return "Usando una de sus herramientas"
        if n in INTERNAS:
            return INTERNAS[n][1]
        k = n.lower().replace(" ", "")
        archivo_ = archivo or _campo(detalle, "file_path", "filePath", "path", "notebook_path")
        nom = os.path.basename(str(archivo_).rstrip("/")) if archivo_ else ""
        if k in ("read", "notebookread"):
            return ("Mirando la imagen %s" if IMAGEN.search(nom) else "Leyendo %s") % _q(nom) if nom else "Leyendo un archivo"
        if k == "write":
            return "Escribiendo %s" % _q(nom) if nom else "Escribiendo un archivo"
        if k in ("edit", "multiedit", "notebookedit"):
            return "Cambiando %s" % _q(nom) if nom else "Cambiando un archivo"
        if k == "grep":
            pat = _campo(detalle, "pattern")
            return "Buscando %s en sus archivos" % _q(pat, 40) if pat else "Buscando en sus archivos"
        if k == "glob":
            return "Buscando archivos"
        if k == "ls":
            return "Mirando sus archivos"
        if k == "webfetch":
            url = _campo(detalle, "url")
            return "Leyendo la página %s" % _q(_dominio(url)) if url else "Leyendo una página de internet"
        if k == "websearch":
            consulta = _campo(detalle, "query")
            return "Buscando en internet %s" % _q(consulta) if consulta else "Buscando en internet"
        if k in ("bash", "shell", "comando", "command", "execute", "exec_command", "local_shell"):
            cmd = _campo(detalle, "command", "cmd")
            if not cmd and isinstance(detalle, str) and _datos(detalle) is None and not detalle.lstrip().startswith("{"):
                cmd = detalle
            try:
                f = _frase_de(cmd, _Ctx(carpeta), solo_el_primero=True)
            except Exception:
                f = "?"
            return _gerundio(f) if f and f != "?" else "Corriendo un comando"
        return "Usando una de sus herramientas" if n else ""
    except Exception:
        return ""


# ── lo que el socio dejó pasar en este trabajo (la licencia del turno) ───────
PASADO = {"crear": "Creó", "cambiar": "Cambió", "leer": "Leyó", "buscar": "Buscó"}


def licencia(raw, carpeta=""):
    """La licencia del turno (control/base.licencia) → {"texto", "usadas", "ultima"}, o None."""
    if not isinstance(raw, dict) or not raw.get("grupos"):
        return None
    sitios = []
    for g in raw["grupos"]:
        c = str(g.get("carpeta") or "")
        rel = os.path.relpath(os.path.realpath(c), os.path.realpath(carpeta)) if carpeta and os.path.isabs(c) else c
        s = _sitio_rel(rel)
        if s not in sitios:
            sitios.append(s)
    usadas = raw.get("usadas") or []
    ultima = ""
    if usadas:
        u = usadas[-1] if isinstance(usadas[-1], dict) else {}
        q = u.get("que") if isinstance(u.get("que"), dict) else {}
        ruta = q.get("ruta") or u.get("archivo") or _campo(u.get("detalle"), "file_path", "path")
        nom = os.path.basename(str(ruta).rstrip("/")) if ruta else ""
        verbo = PASADO.get(str(q.get("clase") or ""), "Hizo")
        ultima = ("%s %s." % (verbo, _q(nom))) if nom else ""
    return {"texto": "crear y cambiar archivos en " + _lista(sitios), "usadas": len(usadas), "ultima": ultima}
