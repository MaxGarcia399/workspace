#!/usr/bin/env python3
"""WORKSPACE · diag_bundle — `workspace doctor --bundle`: un ZIP de diagnóstico
REDACTADO que un cliente adjunta tal cual a un mensaje de soporte.

Por qué (lección Try Omarchy, `app/diagnostics.go`): cuando algo falla en una
máquina ajena, la conversación de soporte arranca con «¿qué versión, qué SO,
qué dice el doctor?» y termina con el cliente pegando capturas que filtran
su nombre, rutas y a veces un token. Un solo archivo, armado igual siempre,
redactado ANTES de salir de la máquina y con un LEEME que dice qué trae y qué
se tachó (transparencia: el cliente puede abrirlo y verlo todo).

Qué TRAE:
  · doctor-check.txt   salida de `workspace doctor --check` (solo lectura, sin
                       color, sin la sesión de Zenith)
  · sistema.json       versión (VERSION), commit, rama, cambios locales sí/no,
                       SO, arquitectura, Python, idioma, motor default
  · capacidades.json   matriz de capabilities.py por motor instalado
  · agentes.json       nombre, motor efectivo (y su origen), estado — SIN rutas
  · logs/              cola acotada de los logs de Workspace (state_dir/logs)
  · LEEME.txt          qué contiene, qué se tachó (conteo por tipo) y qué NO va

Qué JAMÁS trae (no se lee siquiera): conversaciones/transcripts, secrets.local
ni ningún archivo de secretos, contenido de los cerebros, settings crudos.

Redacción (sobre TODO el texto, antes de escribir el zip): rutas de cerebros →
<cerebro:nombre>, carpeta de Workspace → <workspace>, home → ~ (y la carpeta
personal de cualquier otro usuario, en Mac/Linux/Windows), usuario → <usuario>, equipo →
<equipo>, emails → <email>, tokens/API keys (patrones de secret_scan) →
<secreto:tipo>, IPs → <ip> (loopback se deja: no identifica a nadie).

Dónde queda: en el ESCRITORIO del usuario (el lugar que un cliente encuentra
sin ayuda para adjuntar un archivo; en Windows se pregunta al sistema por la
carpeta real, que puede estar redirigida a OneDrive) o, si no hay escritorio,
en la carpeta actual. `--out DIR` lo pisa. Se imprime la ruta completa.

Falla-suave por pieza: si una sección no se puede armar, el zip lleva una
línea honesta en su lugar («no disponible: …») — el bundle siempre sale.
Cero dependencias (stdlib, Python 3.9+). Mac, Linux y Windows.
"""
import datetime
import getpass
import io
import json
import os
import platform
import re
import socket
import subprocess
import sys
import zipfile

import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import i18n
except Exception:
    i18n = None


def _t(key, es):
    if i18n is None:
        return es
    try:
        s = i18n.t(key)
        return s if s != key else es
    except Exception:
        return es


#: Topes de tamaño (el zip se adjunta a un correo/chat: debe ser chico).
LOG_TAIL_BYTES = 64 * 1024        # por archivo de log
LOG_MAX_FILES = 8
LOG_TOTAL_BYTES = 384 * 1024
DOCTOR_TIMEOUT = 240

#: Nombres que JAMÁS entran aunque aparezcan bajo logs/ (defensa en
#: profundidad: hoy logs/ no los tiene, mañana alguien podría escribirlos ahí).
_NUNCA = re.compile(r"(?i)secret|transcript|conversa|chat|token|credential|\.key$")

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


# ── redacción ───────────────────────────────────────────────────────────────
class Redactor(object):
    """Tacha lo personal de un texto y CUENTA qué tachó (para el LEEME).
    Orden importa: rutas largas (cerebros, Workspace) antes que el home, el
    home antes que el usuario suelto."""

    _EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
    _IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
                       r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
    _IPV6 = re.compile(r"(?<![\w:])(?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{1,4}(?![\w:])"
                       r"|(?<![\w:])(?:[0-9a-f]{1,4}:){1,6}:(?:[0-9a-f]{1,4}"
                       r"(?::[0-9a-f]{1,4}){0,5})?(?![\w:])", re.I)
    _HOMES = re.compile(r"(?i)\b[A-Z]:[\\/]+(?:Users|Documents and Settings)[\\/]+"
                        r"[^\\/\s\"'<>|:*?]+"
                        r"|/(?:Users|home)/[^/\s\"'<>]+")

    def __init__(self, brains=None, extra_paths=None, home=None, users=None,
                 hosts=None):
        self.counts = {}
        self._paths = []
        for name, p in (brains or []):
            self._add_path(p, "<cerebro:%s>" % name, "cerebro")
            # El NOMBRE de la carpeta también delata (el doctor lo cita suelto:
            # cerebro "Mi Empresa - Notas"). Solo si es distintivo (≥4).
            base = os.path.basename(str(p).rstrip("\\/"))
            if len(base) >= 4:
                self._paths.append((re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])"
                                               % re.escape(base), re.I),
                                    "<cerebro:%s>" % name, "cerebro"))
        for p, tag in (extra_paths or []):
            self._add_path(p, tag, "workspace")
        self._add_path(home or os.path.expanduser("~"), "~", "home")
        # Más largos primero: una ruta contenida en otra no la parte en dos.
        self._paths.sort(key=lambda t: -len(t[0].pattern))
        self._words = []
        for w in sorted({u for u in (users or []) if u and len(u) >= 3},
                        key=len, reverse=True):
            self._words.append((re.compile(r"(?i)(?<![A-Za-z0-9])%s(?![A-Za-z0-9])"
                                           % re.escape(w)), "<usuario>", "usuario"))
        for h in sorted({x for x in (hosts or []) if x and len(x) >= 3},
                        key=len, reverse=True):
            self._words.append((re.compile(r"(?i)(?<![A-Za-z0-9])%s(?![A-Za-z0-9])"
                                           % re.escape(h)), "<equipo>", "equipo"))

    def _add_path(self, p, tag, kind):
        if not p or len(str(p)) < 3:
            return
        variants = set()
        for v in (str(p), os.path.normpath(str(p))):
            try:
                variants.add(os.path.realpath(v))
            except Exception:
                pass
            variants.add(v)
        for v in list(variants):
            v = v.rstrip("\\/")
            if len(v) < 3:
                continue
            for form in {v, v.replace("\\", "/"), v.replace("/", "\\"),
                         v.replace("\\", "\\\\")}:
                rx = re.compile(re.escape(form) + r"(?![A-Za-z0-9_\-])",
                                re.I if os.name == "nt" else 0)
                self._paths.append((rx, tag, kind))

    def _sub(self, rx, repl, kind, text):
        new, n = rx.subn(repl, text)
        if n:
            self.counts[kind] = self.counts.get(kind, 0) + n
        return new

    def _secrets(self, text):
        try:
            import secret_scan
            pats = secret_scan.PATTERNS
        except Exception:
            return text
        for cls, rx in pats:
            def rep(m, cls=cls):
                self.counts["secreto"] = self.counts.get("secreto", 0) + 1
                if "secret" in rx.groupindex and m.group("secret"):
                    s, e = m.span("secret")
                    return (m.group(0)[:s - m.start()] + "<secreto:%s>" % cls
                            + m.group(0)[e - m.start():])
                return "<secreto:%s>" % cls
            text = rx.sub(rep, text)
        return text

    def redact(self, text):
        if not text:
            return text or ""
        text = _ANSI.sub("", str(text))
        text = self._secrets(text)                       # antes que nada: tokens
        text = self._sub(self._EMAIL, "<email>", "email", text)
        for rx, tag, kind in self._paths:
            text = self._sub(rx, tag.replace("\\", "\\\\"), kind, text)
        text = self._sub(self._HOMES, "~", "home", text)
        for rx, tag, kind in self._words:
            text = self._sub(rx, tag, kind, text)

        def ip(m):
            if m.group(0).startswith(("127.", "0.0.0.0")):
                return m.group(0)
            self.counts["ip"] = self.counts.get("ip", 0) + 1
            return "<ip>"
        text = self._IPV4.sub(ip, text)
        text = self._sub(self._IPV6, "<ip>", "ip", text)
        return text


def _usuarios():
    out = set()
    for fn in (getpass.getuser, lambda: os.environ.get("USERNAME", ""),
               lambda: os.environ.get("USER", ""),
               lambda: os.path.basename(os.path.expanduser("~"))):
        try:
            v = (fn() or "").strip()
            if v:
                out.add(v)
        except Exception:
            pass
    return out


def _equipos():
    out = set()
    for fn in (socket.gethostname, platform.node,
               lambda: os.environ.get("COMPUTERNAME", "")):
        try:
            v = (fn() or "").strip()
            if v:
                out.add(v)
                out.add(v.split(".")[0])
        except Exception:
            pass
    return out


def _cerebros():
    """(nombre, ruta) de TODOS los cerebros que Workspace puede resolver — los
    cargados (agentsreg) y los del registro con su ruta en paths.local.json
    (brain_resolver), que es como los ve el doctor. Si uno se escapa, su ruta
    saldría sin tachar en el zip."""
    out, seen = [], set()

    def add(name, path):
        if path and os.path.normcase(path) not in seen:
            seen.add(os.path.normcase(path))
            out.append((name, path))
    try:
        import agentsreg
        for a in agentsreg.agents():
            add(a["name"], a["brain"])
    except Exception:
        pass
    try:
        import dispatch
        import brain_resolver
        for entry in dispatch.load_registry().get("agents", []):
            try:
                cfg = dispatch.load_agent_cfg(entry)
            except Exception:
                cfg = {}
            try:
                res = brain_resolver.resolve(entry["name"], cfg, entry)
                add(entry["name"], res.path)
            except Exception:
                continue
    except Exception:
        pass
    return out


def default_redactor():
    return Redactor(brains=_cerebros(),
                    extra_paths=[(ROOT, "<workspace>"),
                                 (_paths.state_dir(), "<estado>")],
                    users=_usuarios(), hosts=_equipos())


# ── secciones (cada una falla-suave) ────────────────────────────────────────
def _git(*args):
    try:
        r = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=15)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def sistema():
    try:
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
            version = fh.read().strip()
    except Exception:
        version = ""
    remote = _git("remote", "get-url", "origin")
    remote = re.sub(r"//[^/@]+@", "//", remote)          # jamás credenciales en la URL
    # La CUENTA dueña del fork también identifica: se deja host + nombre del repo.
    remote = re.sub(r"^((?:https?://|git@)[^/:]+[/:])[^/]+/", r"\g<1><cuenta>/", remote)
    try:
        import settings as _st
        motor = _st.get_stored("modelos.default_engine") or ""
    except Exception:
        motor = ""
    return {
        "generado": datetime.datetime.now().isoformat(timespec="seconds"),
        "workspace": {"version": version, "commit": _git("rev-parse", "--short", "HEAD"),
                      "rama": _git("rev-parse", "--abbrev-ref", "HEAD"),
                      "cambios_locales": bool(_git("status", "--porcelain")),
                      "remoto": remote},
        "so": {"sistema": platform.system(), "version": platform.release(),
               "detalle": platform.platform(), "arquitectura": platform.machine()},
        "python": {"version": platform.python_version(),
                   "implementacion": platform.python_implementation(),
                   "ejecutable": sys.executable},
        "terminal": dict([(k, os.environ.get(k)) for k in
                          ("TERM", "TERM_PROGRAM", "COLORTERM") if os.environ.get(k)]
                         + [("windows_terminal", bool(os.environ.get("WT_SESSION")))]),
        "idioma": (i18n.lang() if i18n else ""),
        "motor_default": motor,
    }


def capacidades():
    import capabilities
    import dispatch
    out = {"os": capabilities.current_os(), "general": capabilities.matrix(),
           "por_motor": {}}
    for eid in dispatch.available_engines():
        try:
            out["por_motor"][eid] = capabilities.matrix(eid)
        except Exception as e:
            out["por_motor"][eid] = {"error": "%s: %s" % (type(e).__name__, e)}
    return out


def agentes():
    """Nombre, motor y estado — nunca la ruta del cerebro ni su contenido."""
    import agent_state
    out = []
    for a in agent_state.snapshot(force=True).agents:
        out.append({"nombre": a.get("name"), "motor": a.get("engine"),
                    "origen_motor": a.get("engine_source"),
                    "estado": a.get("status"), "oculto": bool(a.get("hidden"))})
    return out


def doctor_check():
    """`doctor --check` en un proceso aparte: aislado, solo lectura, sin TTY
    y con tope de tiempo."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8",
               NO_COLOR="1")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "doctor.py"), "--check"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=DOCTOR_TIMEOUT,
                       stdin=subprocess.DEVNULL)
    txt = r.stdout + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
    return txt + "\n[exit %d]\n" % r.returncode


def logs():
    """[(nombre, texto)] — cola de cada log de state_dir/logs, acotada."""
    d = os.path.join(_paths.state_dir(), "logs")
    try:
        names = [n for n in os.listdir(d)
                 if os.path.isfile(os.path.join(d, n)) and not _NUNCA.search(n)]
    except OSError:
        return []
    names.sort(key=lambda n: os.path.getmtime(os.path.join(d, n)), reverse=True)
    out, total = [], 0
    for n in names[:LOG_MAX_FILES]:
        if total >= LOG_TOTAL_BYTES:
            break
        p = os.path.join(d, n)
        try:
            size = os.path.getsize(p)
            take = min(LOG_TAIL_BYTES, LOG_TOTAL_BYTES - total)
            with open(p, "rb") as fh:
                if size > take:
                    fh.seek(size - take)
                raw = fh.read(take)
        except OSError:
            continue
        txt = raw.decode("utf-8", errors="replace")
        if size > take:
            txt = "[… recortado: últimos %d KB de %d KB]\n" % (take // 1024, size // 1024) \
                + txt.split("\n", 1)[-1]
        total += len(raw)
        out.append((n, txt))
    return out


# ── armado ──────────────────────────────────────────────────────────────────
def _leeme(red, incluidos, fallos):
    tachado = red.counts
    nombres = {"cerebro": "rutas de cerebros → <cerebro:nombre>",
               "workspace": "carpetas de Workspace → <workspace>/<estado>",
               "home": "tu carpeta personal → ~",
               "usuario": "tu nombre de usuario → <usuario>",
               "equipo": "el nombre del equipo → <equipo>",
               "email": "correos → <email>",
               "secreto": "tokens / API keys → <secreto:tipo>",
               "ip": "direcciones IP → <ip>"}
    L = ["WORKSPACE · paquete de diagnóstico", "=" * 36, "",
         "Este archivo lo generó `workspace doctor --bundle` en tu máquina. Sirve",
         "para que soporte entienda qué pasa sin pedirte capturas. Puedes abrir",
         "cada archivo y revisarlo antes de enviarlo: no hay nada oculto.", "",
         "QUÉ CONTIENE"]
    desc = {"doctor-check.txt": "salida de `workspace doctor --check` (solo diagnóstico)",
            "sistema.json": "versión, commit y rama de Workspace; SO, arquitectura, Python",
            "capacidades.json": "qué funciones soporta cada motor en este sistema",
            "agentes.json": "tus agentes: nombre, motor y estado (sin rutas)"}
    for n in incluidos:
        if n.startswith("logs/"):
            continue
        L.append("  · %-18s %s" % (n, desc.get(n, "")))
    nlogs = [n for n in incluidos if n.startswith("logs/")]
    if nlogs:
        L.append("  · logs/              últimas líneas de %d log(s) de Workspace "
                 "(máx. %d KB c/u)" % (len(nlogs), LOG_TAIL_BYTES // 1024))
    for n, err in fallos:
        L.append("  · %-18s no disponible (%s)" % (n, err))
    L += ["", "QUÉ SE TACHÓ (antes de crear el zip)"]
    if tachado:
        for k in ("cerebro", "workspace", "home", "usuario", "equipo", "email",
                  "secreto", "ip"):
            if tachado.get(k):
                L.append("  · %s  ×%d" % (nombres[k].ljust(46), tachado[k]))
    else:
        L.append("  · nada que tachar en este caso")
    L += ["", "QUÉ NO VA NUNCA (ni siquiera se lee)",
          "  · tus conversaciones / transcripts con los agentes",
          "  · secrets.local y cualquier archivo de credenciales",
          "  · el contenido de tus cerebros (notas, memoria, skills)",
          "", "Si ves algo que no quieres compartir, bórralo del zip: es tuyo.",
          "", "-" * 36, "",
          "WORKSPACE · diagnostic bundle (EN)",
          "Generated by `workspace doctor --bundle`. Contains the read-only doctor",
          "report, version/OS/Python, per-engine capabilities, agent names with",
          "engine and status (no paths) and bounded log tails. Personal data was",
          "redacted before zipping (home, user, host, emails, tokens, IPs, brain",
          "paths). Never included: conversations, secrets.local, brain contents.", ""]
    return "\n".join(L)


def escritorio():
    """La carpeta Escritorio REAL del usuario, o '' si no hay una usable.
    Windows: se pregunta al sistema (puede estar redirigida a OneDrive)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            # CSIDL_DESKTOPDIRECTORY = 0x10
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0 \
                    and os.path.isdir(buf.value):
                return buf.value
        except Exception:
            pass
    d = os.path.join(os.path.expanduser("~"), "Desktop")
    return d if os.path.isdir(d) else ""


def build(out_dir=None, doctor_runner=None, redactor=None, now=None):
    """Arma el zip y devuelve (ruta, redactor). `doctor_runner`/`redactor`
    inyectables (tests herméticos). Nunca levanta por una sección rota."""
    red = redactor or default_redactor()
    out_dir = out_dir or escritorio() or os.getcwd()
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    dest = os.path.join(out_dir, "workspace-diagnostico-%s.zip" % stamp)
    piezas, fallos = [], []

    def add(nombre, fn, as_json=False):
        try:
            v = fn()
            txt = json.dumps(v, ensure_ascii=False, indent=2) if as_json else v
            piezas.append((nombre, red.redact(txt)))
        except Exception as e:
            fallos.append((nombre, "%s: %s" % (type(e).__name__, red.redact(str(e))[:160])))

    add("doctor-check.txt", doctor_runner or doctor_check)
    add("sistema.json", sistema, True)
    add("capacidades.json", capacidades, True)
    add("agentes.json", agentes, True)
    try:
        for n, txt in logs():
            piezas.append(("logs/" + red.redact(n), red.redact(txt)))
    except Exception as e:
        fallos.append(("logs/", type(e).__name__))
    leeme = _leeme(red, [n for n, _ in piezas], fallos)
    os.makedirs(out_dir, exist_ok=True)
    tmp = dest + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("LEEME.txt", leeme)
        for n, txt in piezas:
            z.writestr(n, txt)
    os.replace(tmp, dest)
    return dest, red


def main(argv=None):
    """Entrada de `workspace doctor --bundle [--out DIR]`. 0 = zip creado."""
    args = list(sys.argv[1:] if argv is None else argv)
    out = None
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1] if i + 1 < len(args) else None
    print("  " + _t("diag.working", "Armando el paquete de diagnóstico "
                    "(corre el doctor en modo solo lectura; puede tardar un poco)…"))
    try:
        dest, red = build(out_dir=out)
    except Exception as e:
        print("  ✗ " + _t("diag.fail", "No pude crear el paquete ({err}). "
                          "Nada se envió ni se borró.").replace("{err}", str(e)))
        return 1
    n = sum(red.counts.values())
    print("  ✓ " + _t("diag.done", "Listo. Adjunta este archivo a tu mensaje de soporte:"))
    print("    " + dest)
    print("  " + _t("diag.redacted", "Se tacharon {n} dato(s) personales antes de "
                    "crearlo; LEEME.txt dentro del zip dice qué y qué NO va.")
          .replace("{n}", str(n)))
    return 0


if __name__ == "__main__":
    import _utf8
    _utf8.harden()
    sys.exit(main())
