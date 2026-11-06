"""WORKSPACE · memoria_permiso — el comando angosto `workspace-memoria` (uso a
mano) y el retiro de la aprobación que tuvo en GitHub Copilot, Cursor y Kiro.

HASTA 2026-11-05 esos tres motores guardaban la memoria con este comando y
lo aprobaban por su RUTA (Copilot `--allow-tool=shell(<ruta>)`, Cursor
`Shell(<ruta>)` en su config de usuario, Kiro una regex en
`toolsSettings.shell.allowedCommands` de su agente `workspace` global). Una
prueba en vivo en Windows demostró que aprobar una ruta deja colar otro
comando: el motor analiza la línea con gramática de bash y la ejecuta otra
shell (comillas tipográficas en Copilot y Cursor, `${function:<ruta>}=…` en
Kiro 3.0). AHORA la memoria de esos motores es una herramienta MCP
(memoria_mcp), aprobada POR NOMBRE, sin shell. Aquí queda:

  · retirar_aprobaciones(motor): al abrir, quita lo que aprobaba la ruta en
    una versión anterior (la regla de Cursor, el agente global de Kiro). En
    Copilot no hay nada escrito: iba por corrida. Todos los SO.
  · el shim para uso a mano: ya no se instala ni se aprueba en ningún motor
    (pide permiso como cualquier comando). Uno que ya exista sigue sirviendo y
    el desinstalador lo quita (MARCA).
  · corrida_viva: la corrida de Workspace que lanzó al motor (su envoltorio es
    un ancestro de este proceso). La usan el shim y la herramienta MCP para
    escribir SOLO en la pestaña de esa ventana.

Lo que el shim sigue cuidando (auditoría 2026-10-30): NADA del entorno ni de
la carpeta elige el código que corre ni dónde escribe:
  · hornea Python, la ruta de este archivo y el HOME de quien lo escribió;
    fija PATH y quita TMPDIR/TMP/TEMP antes de llamar a Python;
  · `#!/bin/sh -p` donde /bin/sh lo acepta (bash/zsh/ksh: sin -p, bash lee
    SHELLOPTS y funciones exportadas del entorno); dash no lee ninguna;
  · `python -I` (aislado): ni PYTHON*, ni el site-packages del usuario, ni la
    carpeta del script o la actual en sys.path;
  · `main` solo escribe en el cerebro y la pestaña de la CORRIDA VIVA y
    rechaza --brain/--tab/--motor/--engine que apunten a otros. Sin corrida
    viva se niega: `workspace memoria …` sigue funcionando.

En Windows no se instala (retirar_windows quita el de una versión anterior):
el `.cmd` reenviaba `%*` y cmd.exe vuelve a leer lo que escribió el agente.

Cero dependencias (stdlib, 3.9+). Falla-suave: nunca tumba un arranque.
"""
import json
import os
from pathlib import Path
import re
import shlex
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SHIM = "workspace-memoria"
#: PATH del shim: ni Python ni lo que corra adentro se busca en el PATH que el
#: agente le ponga delante.
PATH_FIJO = "/usr/bin:/bin:/usr/sbin:/sbin"
#: Opciones de `workspace memoria` que eligen cerebro, pestaña o motor: el shim
#: solo acepta las de la corrida viva (las demás escribirían en otro lado).
OPCIONES_DE_LA_CORRIDA = ("--brain", "--tab", "--motor", "--engine")
#: Lo único que acepta el comando: los dos que escriben (nota, checkpoint) y
#: los de lectura que piden las instrucciones (status para reconciliar un
#: resumen en conflicto). `compactar` y el resto de `workspace` quedan fuera.
SUBCOMANDOS = ("nota", "checkpoint", "status", "context", "ver", "vigente", "maleta")
#: = install.LAUNCHER_MARK: el desinstalador lo reconoce como suyo y lo borra.
MARCA = "# WORKSPACE · comando"
#: La ruta del shim tiene que poder escribirse TAL CUAL, sin comillas.
_RUTA_LIMPIA = re.compile(r"/[A-Za-z0-9._/+@-]+\Z")

#: Las reglas que Workspace dejó en la config de usuario de Cursor
#: (cli-config.json) hasta 2026-11-05: la vieja por nombre y la de la ruta (de
#: cualquier HOME). Se quitan al abrir Cursor y al desinstalar.
CURSOR_REGLA_VIEJA = "Shell(%s)" % SHIM
#: Cualquier forma de ruta (POSIX o Windows, con / o \\, con o sin .cmd/.exe):
#: el retiro es defensivo aunque en Windows nunca se haya escrito.
_CURSOR_REGLA_RX = re.compile(
    r"Shell\((?:[A-Za-z]:)?[\\/]\S*[\\/]\.local[\\/]bin[\\/]workspace-memoria"
    r"(?:\.cmd|\.exe|\.bat)?\)\Z", re.IGNORECASE)
#: El agente GLOBAL de Kiro que aprobaba la ruta con una regex
#: (~/.kiro/agents/workspace.json, marcado en su descripción). Ahora el
#: agente vive en el cerebro (memoria_mcp): el global nuestro se borra.
KIRO_AGENTE = "workspace"
KIRO_MARCA = "WORKSPACE ·"


# ── el shim ─────────────────────────────────────────────────────────────────
def _windows():
    """¿Windows? (aparte para probar el camino de Windows en Mac/Linux)."""
    return os.name == "nt"


def _python():
    if os.name == "nt":
        try:
            import install
            return install.win_python()
        except Exception:
            pass
    # Desde un venv, el Python BASE: un venv se borra (el de las pruebas e2e
    # vive en una carpeta temporal) y el shim quedaba apuntando a nada, sin
    # memoria en Copilot, Cursor y Kiro. Workspace solo usa la biblioteca
    # estándar: corre igual con el base.
    if sys.prefix != sys.base_prefix:
        venv = os.path.realpath(sys.prefix) + os.sep
        # ≤3.10 framework de macOS (el /usr/bin/python3 de fábrica): ahí
        # _base_executable es la ruta DEL venv; se descarta (revisión 2026-10-31)
        for base in (getattr(sys, "_base_executable", ""),
                     os.path.join(sys.base_prefix, "bin", "python3")):
            if (base and os.access(base, os.X_OK)
                    and not os.path.realpath(base).startswith(venv)):
                return base
    return sys.executable or "python3"


def shim_path(home=None, cmd=False):
    return Path(home or Path.home()) / ".local" / "bin" / (SHIM + (".cmd" if cmd else ""))


def ruta(home=None):
    """La ruta ABSOLUTA del shim, o '' si no se puede escribir sin comillas
    (HOME con espacios u otros caracteres)."""
    p = str(shim_path(home))
    return p if _RUTA_LIMPIA.match(p) and os.path.normpath(p) == p else ""


def es_regla_cursor(regla):
    """¿Es una regla de Workspace en Cursor (la vieja por nombre o una por
    ruta, de este HOME o de otro)?"""
    return regla == CURSOR_REGLA_VIEJA or bool(_CURSOR_REGLA_RX.match(str(regla)))


_SH = {}


def sh_acepta_p():
    """¿/bin/sh acepta `-p`? bash, zsh y ksh sí (y con -p no leen SHELLOPTS,
    BASHOPTS, ENV ni funciones del entorno); dash no la acepta, pero tampoco
    lee nada de eso. Se pregunta una vez por proceso."""
    if "p" not in _SH:
        ok = False
        if os.name != "nt":
            try:
                import subprocess
                ok = subprocess.run(["/bin/sh", "-p", "-c", "exit 0"], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=10).returncode == 0
            except Exception:
                ok = False
        _SH["p"] = ok
    return _SH["p"]


def shim_posix(root=None, python=None, home=None, sh_p=None):
    """Script sh del shim (macOS/Linux). Hornea Python, este archivo y HOME;
    fija PATH y corre Python aislado (ver el docstring del módulo)."""
    f = os.path.join(root or ROOT, "memoria_permiso.py")
    py = python or _python()
    home = str(home or Path.home())
    p = sh_acepta_p() if sh_p is None else sh_p
    return "\n".join([
        "#!/bin/sh -p" if p else "#!/bin/sh",
        MARCA + " `%s` (memoria de la pestaña; se reescribe al abrir un agente)" % SHIM,
        "# Solo nota, checkpoint, status… y solo en la pestaña de la corrida que lanzó al",
        "# motor (lo valida memoria_permiso.py): los motores aprueban la RUTA de este",
        "# archivo sin aprobar todo `workspace`. Python, rutas, HOME y PATH fijos; -I.",
        "HOME=%s; export HOME" % shlex.quote(home),
        "PATH=%s; export PATH" % PATH_FIJO,
        "unset TMPDIR TMP TEMP",
        "py=%s" % shlex.quote(py),
        "f=%s" % shlex.quote(f),
        'if [ -x "$py" ] && [ -f "$f" ]; then exec "$py" -I "$f" "$@"; fi',
        'echo "%s: no encuentro Workspace ($f). Reabre el agente desde Workspace o usa: '
        'workspace memoria $*" >&2' % SHIM,
        "exit 127", ""])


def _es_nuestro(path):
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:800]
    except OSError:
        return False
    if path.suffix.lower() == ".cmd":
        return head.startswith("@echo off") and "memoria_permiso.py" in head
    return any(ln.startswith(MARCA) for ln in head.splitlines()[:3])


def _destino(text):
    """Archivo .py al que apunta un shim ya escrito ('' si no se entiende)."""
    m = re.search(r"^f=(.+)$", text or "", re.M)
    if m:
        try:
            return (shlex.split(m.group(1)) or [""])[0]
        except ValueError:
            return ""
    m = re.search(r'-[EI] "([^"]+memoria_permiso\.py)"', text or "")
    return m.group(1) if m else ""


def _desde_worktree(root):
    """¿Corre desde un git worktree secundario (tests, ramas temporales)? Ahí
    `.git` es un archivo (como install.running_from_worktree)."""
    return os.path.isfile(os.path.join(root, ".git"))


def _escribir(path, text, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name + "-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.chmod(tmp, 0o755 if mode is None else mode)
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def retirar_windows(home=None):
    """Windows (no se aprueba nada, ver el docstring): quita el shim de
    una versión anterior (el .cmd y el de Git Bash), solo si es nuestro.
    → rutas quitadas."""
    out = []
    for p in (shim_path(home, cmd=True), shim_path(home)):
        try:
            if not p.is_symlink() and p.is_file() and _es_nuestro(p):
                p.unlink()
                out.append(p)
        except OSError:
            continue
    return out


def ensure_shim(home=None, root=None, python=None):
    """Escribe/actualiza `workspace-memoria` en ~/.local/bin. No pisa un
    archivo con ese nombre que no sea nuestro. Desde un worktree no reemplaza
    uno vivo (apuntaría a un árbol que se borra). En Windows no se instala
    (retira uno viejo). → ruta del shim, o None."""
    if _windows():
        retirar_windows(home)
        return None
    root = root or ROOT
    p = shim_path(home)
    want = shim_posix(root, python, home=home)
    try:
        if p.is_symlink():
            return None
        if p.exists():
            if not _es_nuestro(p):
                return None
            cur = p.read_text(encoding="utf-8", errors="replace")
            vivo = os.path.isfile(_destino(cur))
            if cur != want and not (_desde_worktree(root) and vivo):
                _escribir(p, want)
            elif not os.access(str(p), os.X_OK):
                os.chmod(str(p), 0o755)
        else:
            _escribir(p, want)
        return p
    except OSError:
        return None


# ── retirar la aprobación vieja (Cursor y Kiro) ─────────────────────────────
def cursor_config_path(env=None):
    try:
        from engines.cursor import config_dir
        return Path(config_dir(env)) / "cli-config.json"
    except Exception:
        return Path.home() / ".cursor" / "cli-config.json"


def quitar_regla_cursor(path=None, env=None):
    """Quita de `permissions.allow` de la config de usuario de Cursor las
    reglas del shim que dejó una versión anterior (por nombre o por ruta, de
    cualquier HOME). El resto del archivo queda igual (lectura-modificación-
    escritura atómica, mismo modo). → 'ready' | 'removed' | 'blocked'."""
    from motor_statusline import _read, _write
    path = Path(path or cursor_config_path(env))
    try:
        if path.is_symlink():
            return "blocked"
        data, text = _read(path)
        new, quito = clean_cursor(data)
        if not quito or text is None:
            return "ready"
        _write(path, new, path.stat().st_mode & 0o777)
        return "removed"
    except (OSError, ValueError, TypeError, AttributeError):
        return "blocked"


def clean_cursor(data):
    """(dict nuevo, ¿quitó?) sin las reglas del shim de Workspace."""
    if not isinstance(data, dict):
        return data, False
    perms = data.get("permissions")
    allow = perms.get("allow") if isinstance(perms, dict) else None
    if not isinstance(allow, list) or not any(es_regla_cursor(r) for r in allow):
        return data, False
    new = dict(data)
    new["permissions"] = dict(perms, allow=[r for r in allow if not es_regla_cursor(r)])
    return new, True


def _kiro_dir():
    try:
        from engines import kiro
        return kiro._kiro_dir()
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".kiro")


def kiro_agente_path():
    """El agente GLOBAL de una versión anterior (~/.kiro/agents/workspace.json)."""
    return Path(_kiro_dir()) / "agents" / (KIRO_AGENTE + ".json")


def _kiro_es_nuestro(data):
    return isinstance(data, dict) and str(data.get("description") or "").startswith(KIRO_MARCA)


def clean_kiro_agente(path=None):
    """Ruta del agente global `workspace` si es nuestro (para quitarlo), o None."""
    path = Path(path or kiro_agente_path())
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path if _kiro_es_nuestro(json.loads(path.read_text(encoding="utf-8"))) else None
    except (OSError, ValueError):
        return None


def retirar_aprobaciones(motor, env=None):
    """Al abrir `motor`: quita la aprobación por RUTA del shim que dejó una
    versión anterior (Cursor: su regla en cli-config.json; Kiro: el agente
    global nuestro). Uno del socio no se toca. Falla-suave."""
    try:
        if motor == "cursor":
            quitar_regla_cursor(env=env)
        elif motor == "kiro":
            p = clean_kiro_agente()
            if p is not None:
                p.unlink()
    except Exception:
        pass



# ── la corrida viva: dónde escribe el comando ───────────────────────────────
#: struct kinfo_proc de macOS (64 bits): 648 bytes, p_pid en 40, e_ppid en 560
#: (VERIFICADO 2026-10-30 arm64 contra os.getppid y `ps -o ppid=`).
_KINFO = (648, 40, 560)


def _padre_windows(pid):
    """pid del padre en Windows: la foto de procesos documentada de Win32
    (CreateToolhelp32Snapshot + Process32FirstW/NextW → th32ParentProcessID).
    Windows recicla los pid y el padre anotado puede haber muerto: si el
    «padre» nació DESPUÉS que el hijo, es otro proceso y se corta (0)."""
    import ctypes
    from ctypes import wintypes

    class _PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    k32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PE))
    k32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_PE))
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)                  # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:            # INVALID_HANDLE_VALUE
        return 0
    ppid = 0
    try:
        e = _PE()
        e.dwSize = ctypes.sizeof(_PE)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if int(e.th32ProcessID) == int(pid):
                ppid = int(e.th32ParentProcessID)
                break
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    if ppid <= 0:
        return 0
    import openclaw_gateway as G
    hijo, padre = G._identity(pid)[1], G._identity(ppid)[1]
    if hijo and padre and padre > hijo:
        return 0
    return ppid


def _padre(pid):
    """pid del padre de `pid` (0 si no se sabe). Sin PATH: sysctl en Mac,
    /proc en Linux, la foto de procesos de Win32 en Windows y, si no,
    /bin/ps con su ruta."""
    if pid == os.getpid():
        return os.getppid()
    try:
        if os.name == "nt":
            return _padre_windows(pid)
        if sys.platform == "darwin":
            import ctypes
            import openclaw_gateway as G
            mib = (ctypes.c_int * 4)(1, 14, 1, pid)       # CTL_KERN, KERN_PROC, KERN_PROC_PID
            buf = ctypes.create_string_buffer(1024)
            size = ctypes.c_size_t(1024)
            if G._darwin_libc().sysctl(mib, 4, buf, ctypes.byref(size), None, 0) == 0:
                raw = buf.raw[:size.value]
                if len(raw) == _KINFO[0] and struct.unpack_from("=i", raw, _KINFO[1])[0] == pid:
                    return struct.unpack_from("=i", raw, _KINFO[2])[0]
        elif sys.platform.startswith("linux"):
            with open("/proc/%d/stat" % pid, "rb") as fh:
                raw = fh.read().decode("ascii", "replace")
            return int(raw[raw.rindex(")") + 2:].split()[1])
    except Exception:
        pass
    try:
        import subprocess
        r = subprocess.run(["/bin/ps", "-o", "ppid=", "-p", str(int(pid))], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=5,
                           stdin=subprocess.DEVNULL)
        return int((r.stdout or "").strip() or 0)
    except Exception:
        return 0


def ancestros(pid=None, tope=64):
    """[este proceso, su padre, …] hasta init."""
    out = []
    pid = os.getpid() if pid is None else pid
    while pid and pid > 1 and pid not in out and len(out) < tope:
        out.append(pid)
        pid = _padre(pid)
    return out


def corrida_viva(cadena=None):
    """La corrida de Workspace que lanzó al motor que corre este comando: la
    anotada en pending_runs (en «running», envoltorio vivo) cuyo envoltorio es
    el ancestro MÁS CERCANO de este proceso. El agente no la puede elegir: ni
    con opciones, ni con variables delante, ni con `cd`. → {brain, tab,
    engine, socio}; ValueError si no hay (o no tiene cerebro o pestaña)."""
    import pending_runs
    cadena = ancestros() if cadena is None else list(cadena)
    por_pid = {}
    for rec in pending_runs.pending():
        try:
            pid = int((rec.get("proc") or {}).get("pid") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if pid in cadena and rec.get("state") == "running":
            por_pid.setdefault(pid, []).append(rec)
    for pid in cadena:
        for rec in sorted(por_pid.get(pid, ()), key=lambda r: float(r.get("started") or 0),
                          reverse=True):
            if not pending_runs.proc_alive(rec):
                continue
            brain, tab = str(rec.get("brain") or ""), str(rec.get("tab") or "")
            if not brain or not os.path.isdir(brain):
                raise ValueError("la corrida de esta ventana no tiene cerebro")
            if not tab:
                raise ValueError("esta ventana no tiene pestaña de Workspace")
            return {"brain": brain, "tab": tab, "engine": str(rec.get("engine") or ""),
                    "socio": rec.get("socio")}
    raise ValueError("solo guarda desde un agente abierto con Workspace (no encuentro la "
                     "corrida de esta ventana)")


def _opcion_de_la_corrida(x):
    """La de OPCIONES_DE_LA_CORRIDA que nombra el argumento `x` (entera,
    abreviada como la acepta argparse, o con `=`), o ''."""
    if not x.startswith("--") or x == "--":
        return ""
    nombre = x.split("=", 1)[0]
    if len(nombre) < 3:
        return ""
    return next((o for o in OPCIONES_DE_LA_CORRIDA if o.startswith(nombre)), "")


def anclar(argv, run):
    """`argv` (sin el subcomando) SIN las opciones de cerebro, pestaña y
    motor: cada una tiene que nombrar la de la corrida viva `run` (la toma
    de ahí _fijar_entorno). ValueError si alguna apunta a otro lado."""
    import memoria
    import sessions_registry as reg
    out, i = [], 0
    while i < len(argv):
        x = str(argv[i])
        o = _opcion_de_la_corrida(x)
        if not o:
            out.append(argv[i])
            i += 1
            continue
        if "=" in x:
            val, i = x.split("=", 1)[1], i + 1
        elif i + 1 < len(argv):
            val, i = str(argv[i + 1]), i + 2
        else:
            raise ValueError("%s sin valor" % o)
        if o == "--brain":
            mia = os.path.realpath(run["brain"])
            ok = bool(val) and os.path.realpath(memoria.raiz_cerebro(val)) == mia
            que = "el cerebro de esta ventana es %s" % run["brain"]
        elif o == "--tab":
            ok = bool(reg._slug(val)) and reg._slug(val) == reg._slug(run["tab"])
            que = "esta ventana es la pestaña «%s»" % run["tab"]
        else:
            ok = memoria.normalizar_motor(val) == memoria.normalizar_motor(run["engine"])
            que = "esta ventana es de %s" % (run["engine"] or "otro motor")
        if not ok:
            raise ValueError("%s %s no es de esta ventana (%s); guarda sin %s" % (o, val, que, o))
    return out


def _fijar_entorno(run):
    """El entorno con el que corre `workspace memoria`: el de la corrida viva,
    no el que el agente haya puesto delante."""
    env = os.environ
    env["WORKSPACE_BRAIN"] = run["brain"]
    env["WORKSPACE_WS"] = run["tab"]
    env.pop("ZENITH_WS", None)
    env.pop("OPENCLAW_SHELL", None)
    if run["engine"]:
        env["WORKSPACE_ENGINE"] = run["engine"]
    else:
        env.pop("WORKSPACE_ENGINE", None)
    socio = run.get("socio")
    if socio:
        env["WORKSPACE_SOCIO"] = str(socio)
    else:                       # corrida sin el dato: socio.local o la única carpeta
        env.pop("WORKSPACE_SOCIO", None)
    try:
        os.chdir(run["brain"])
    except OSError:
        pass


# ── el comando ──────────────────────────────────────────────────────────────
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in SUBCOMANDOS:
        sys.stderr.write("%s: solo %s (lo demás: workspace …)\n"
                         % (SHIM, ", ".join(SUBCOMANDOS)))
        return 2
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    try:
        import _utf8
        _utf8.harden()
    except Exception:
        pass
    try:
        run = corrida_viva()
        resto = anclar(argv[1:], run)
    except ValueError as e:
        sys.stderr.write("%s: %s. Usa `workspace memoria %s …`.\n" % (SHIM, e, argv[0]))
        return 2
    _fijar_entorno(run)
    import memoria
    return memoria.main([argv[0]] + resto)


if __name__ == "__main__":
    raise SystemExit(main())
