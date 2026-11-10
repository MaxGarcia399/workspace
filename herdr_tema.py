#!/usr/bin/env python3
"""WORKSPACE · herdr_tema — dentro de herdr, el tema lo manda herdr.

Cuando Workspace corre en un panel de herdr (el multiplexor), herdr ya pinta
su barra de pestañas, su barra lateral y los bordes con SU tema. Si Workspace
además pinta el suyo (otra paleta y, sobre todo, su propio FONDO por OSC
10/11), los dos chocan y todo se ve «raro o incompleto». La regla es la de
un solo dueño: dentro de herdr el dueño del tema es herdr, que está una capa
arriba. Workspace lee el tema elegido en herdr y pinta con esos colores; el
fondo es de herdr o de la terminal (Workspace no lo toca).

Qué hace:
  · dentro_de_herdr(): ¿corre en un panel de herdr? HERDR_PANE_ID o
    HERDR_ENV (las dos las inyecta herdr a cada panel; HERDR_ENV es la que
    usa multiplexer.inside_herdr). HERDR_SOCKET_PATH solo cuenta junto con
    HERDR_BIN_PATH: el usuario puede exportar el socket en su shell para
    manejar herdr desde afuera. HERDR_SESSION sola no cuenta (la exporta el
    lanzador y cualquier script que maneja una sesión desde afuera).
  · seguir(): dentro de herdr, fuera del split PROPIO de Workspace (sesiones
    workspace-split-*, que llevan su config herdr-split.toml sin [theme]: ahí
    el tema sigue siendo el ui.theme del usuario) y con el ajuste
    ui.tema_herdr = «herdr» (el default; «workspace» = el tema propio).
  · tema(): el tema EFECTIVO de herdr, resuelto como lo resuelve herdr 0.9.x:
    config (HERDR_CONFIG_PATH > $XDG_CONFIG_HOME/herdr > %APPDATA%\\herdr >
    ~/.config/herdr) → [theme] name con sus alias → auto_switch (dark_name /
    light_name o la pareja del tema) → [theme.custom] → [ui] accent (el
    acento viejo de herdr, si no hay theme.custom.accent) → [theme.custom.
    dark|light]. Los colores base salen de herdr_paletas.py (generado desde el
    código de herdr, Apache-2.0: licenses/herdr-APACHE-2.0.txt).
  · consultar_fondo(): pregunta UNA vez (al abrir el hub) el fondo REAL por
    OSC 11 — herdr contesta con el de la terminal de afuera —, con timeout
    corto y caché en disco para los procesos que no preguntan (statusline).
    Con fondo real: auto_switch decide por él (no por la apariencia del
    sistema) y, si el tema de herdr es del lado contrario (oscuro sobre una
    terminal clara o al revés), se usa su pareja clara/oscura si existe; si
    no, el contraste se ajusta contra ese fondo. Sin respuesta, como antes.
  · bloque_tui() / semantica(): ese tema convertido a lo que pinta Workspace
    (bloque `tui` de tuitheme y paleta semántica de theme_render).
  · firma(): huella barata para que tuitheme memoice y el hub se REPINTE solo
    cuando cambia el tema de herdr: como mucho un stat de la config cada
    ~0,5 s (AppData en red en Windows) y el bloque ya calculado en disco para
    los procesos cortos (statusline).

SOLO LECTURA de la config de herdr: jamás la escribe ni le habla a su server.
Falla-suave ABSOLUTA: cualquier problema → el tema por defecto de herdr
(catppuccin) o, si ni eso, None (y Workspace pinta lo de siempre).
stdlib puro (3.9+; usa tomllib si existe y un lector mínimo si no).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

AJUSTE = "ui.tema_herdr"
SEGUIR = "herdr"
PROPIO = "workspace"
OPCIONES = (SEGUIR, PROPIO)

SPLIT_PREFIX = "workspace-split-"     # sesiones del split propio (multiplexer)
SPLIT_CONFIG = "herdr-split.toml"     # su config (sin [theme])
_DEFAULT = "catppuccin"
_DEFAULT_CLARO = "catppuccin-latte"
_HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")
_HEX3 = re.compile(r"^#[0-9a-fA-F]{3}$")

# ratatui::Color con nombre (herdr parse_color) → índice ANSI 0-15
# (OJO: en ratatui `white` es Color::White = 15 y `gray` es Color::Gray = 7.)
_NOMBRES = {"black": 0, "red": 1, "green": 2, "yellow": 3, "blue": 4,
            "magenta": 5, "purple": 5, "cyan": 6, "gray": 7, "grey": 7,
            "darkgray": 8, "darkgrey": 8, "lightred": 9, "lightgreen": 10,
            "lightyellow": 11, "lightblue": 12, "lightmagenta": 13,
            "lightcyan": 14, "white": 15}

# xterm por defecto de los 16 básicos: SOLO para derivar mezclas (estrellas,
# brasas, superficies) cuando herdr usa un color de la terminal. El color en
# sí se pinta con su índice, así sale el de la terminal real.
_ANSI16 = ["#000000", "#cd0000", "#00cd00", "#cdcd00", "#0000ee", "#cd00cd",
           "#00cdcd", "#e5e5e5", "#7f7f7f", "#ff0000", "#00ff00", "#ffff00",
           "#5c5cff", "#ff00ff", "#00ffff", "#ffffff"]

CAMPOS = ("accent", "panel_bg", "sidebar_bg", "active_row_bg", "selection_bg",
          "surface0", "surface1", "surface_dim", "overlay0", "overlay1", "text",
          "subtext0", "mauve", "green", "yellow", "red", "blue", "teal", "peach")


def _ttl():
    """Cada cuánto se vuelve a mirar la config (segundos). env
    WORKSPACE_HERDR_TEMA_TTL lo cambia (los tests lo ponen en 0)."""
    try:
        return max(0.0, float(os.environ.get("WORKSPACE_HERDR_TEMA_TTL", "0.5")))
    except ValueError:
        return 0.5


# ── ¿dentro de herdr? ¿seguirlo? ─────────────────────────────────────────────
def dentro_de_herdr(env=None):
    """True si este proceso corre en un panel de herdr."""
    env = os.environ if env is None else env
    try:
        if (env.get("HERDR_PANE_ID") or "").strip():
            return True
        if (env.get("HERDR_ENV") or "").strip() not in ("", "0"):
            return True
        return bool((env.get("HERDR_SOCKET_PATH") or "").strip()
                    and (env.get("HERDR_BIN_PATH") or "").strip())
    except Exception:
        return False


def split_propio(env=None):
    """¿Es el split de Workspace (multiplexer: backend herdr)? Ahí herdr no
    tiene tema propio (su config no trae [theme]) y el tema sigue siendo el
    ui.theme del usuario."""
    env = os.environ if env is None else env
    try:
        if (env.get("HERDR_SESSION") or "").startswith(SPLIT_PREFIX):
            return True
        cfg = (env.get("HERDR_CONFIG_PATH") or "").strip()
        if cfg and os.path.basename(cfg) == SPLIT_CONFIG:
            return not isinstance(leer_config(cfg).get("theme"), dict)
    except Exception:
        return False
    return False


def preferencia(env=None):
    """«herdr» (default) | «workspace». env WORKSPACE_TEMA_HERDR gana (tests y
    para probar sin guardar): herdr/1/on/si → seguir; workspace/0/off/no →
    propio. Falla-suave → «herdr»."""
    env = os.environ if env is None else env
    ov = (env.get("WORKSPACE_TEMA_HERDR") or "").strip().lower()
    if ov in ("herdr", "1", "on", "si", "sí", "true", "yes"):
        return SEGUIR
    if ov in ("workspace", "0", "off", "no", "false"):
        return PROPIO
    try:
        import settings
        v = settings.get(AJUSTE, SEGUIR)
        return v if v in OPCIONES else SEGUIR
    except Exception:
        return SEGUIR


def seguir(env=None):
    """¿Workspace debe pintar con el tema de herdr (y NO pintar fondo)?"""
    try:
        return (dentro_de_herdr(env) and not split_propio(env)
                and preferencia(env) == SEGUIR)
    except Exception:
        return False


# ── la config de herdr (solo lectura) ────────────────────────────────────────
def config_path(env=None):
    """Dónde lee herdr su config (misma precedencia que herdr config_path)."""
    env = os.environ if env is None else env
    p = (env.get("HERDR_CONFIG_PATH") or "").strip()
    if p:
        return p
    xdg = (env.get("XDG_CONFIG_HOME") or "").strip()
    if xdg:
        return os.path.join(xdg, "herdr", "config.toml")
    if os.name == "nt":
        for base in ((env.get("APPDATA") or "").strip(),
                     os.path.join(env.get("USERPROFILE") or "", "AppData", "Roaming")
                     if env.get("USERPROFILE") else ""):
            if base:
                return os.path.join(base, "herdr", "config.toml")
    home = (env.get("HOME") or "").strip() or os.path.expanduser("~")
    return os.path.join(home, ".config", "herdr", "config.toml")


_STAT = {}


def _stat(path):
    """(mtime_ns, tamaño) de la config, o (None, None) si no está. Como mucho
    UN os.stat por archivo cada _ttl() segundos: el hub pinta muchos cuadros
    por segundo y en Windows el AppData puede vivir en red."""
    ahora = time.monotonic()
    viejo = _STAT.get(path)
    if viejo and ahora - viejo[0] < _ttl():
        return viejo[1]
    try:
        st = os.stat(path)
        v = (st.st_mtime_ns, st.st_size)
    except OSError:
        v = (None, None)
    _STAT.clear()                            # una config viva a la vez
    _STAT[path] = (ahora, v)
    return v


def _toml_minimo(texto):
    """Lector TOML MÍNIMO (sin tomllib, Python < 3.11): tablas [a.b], claves
    `k = "texto" | 'texto' | true | false | número`, comentarios #. Lo que no
    entienda lo ignora: un encabezado que no reconozca ([[arreglos]], claves
    con comillas…) deja de asignar claves hasta el siguiente que sí. Solo
    hace falta para [theme…] y [ui]."""
    out = {}
    cur = out
    for crudo in texto.splitlines():
        lin = crudo.strip()
        if not lin or lin.startswith("#"):
            continue
        if lin.startswith("["):
            m = re.match(r"^\[\s*([A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*)\s*\]\s*(#.*)?$", lin)
            cur = out if m else None
            if m:
                for parte in m.group(1).split("."):
                    cur = cur.setdefault(parte, {})
                    if not isinstance(cur, dict):
                        cur = None
                        break
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*=\s*(.+?)\s*$", lin)
        if not m or cur is None:
            continue
        k, v = m.group(1), m.group(2)
        if v[:1] in ('"', "'"):
            q = v[0]
            fin = v.find(q, 1)
            if fin > 0:
                cur[k] = v[1:fin]
            continue
        v = v.split("#", 1)[0].strip()
        if v in ("true", "false"):
            cur[k] = (v == "true")
        else:
            try:
                cur[k] = int(v)
            except ValueError:
                pass
    return out


_CACHE_CFG = {}


def leer_config(path):
    """dict de la config de herdr (solo lectura, cacheada por mtime/tamaño).
    {} si no existe o no se entiende (herdr usa sus defaults en ese caso).
    Acepta el BOM de UTF-8 (PowerShell 5.1, Notepad)."""
    mt, tam = _stat(path)
    if mt is None:
        return {}
    clave = (path, mt, tam)
    if clave in _CACHE_CFG:
        return _CACHE_CFG[clave]
    try:
        with open(path, "rb") as fh:
            crudo = fh.read()
        try:
            import tomllib
            data = tomllib.loads(crudo.decode("utf-8-sig"))
        except ImportError:
            data = _toml_minimo(crudo.decode("utf-8-sig", "replace"))
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    _CACHE_CFG.clear()                       # una config viva a la vez
    _CACHE_CFG[clave] = data
    return data


# ── colores: el mismo parse_color de herdr ───────────────────────────────────
def color(v):
    """Un color de la config de herdr → '#rrggbb' | índice 0-15 | 'reset'.
    Igual que herdr: hex de 6 o 3, rgb(r,g,b), nombres; lo desconocido →
    cian (6), como hace herdr. None si `v` no es texto."""
    if not isinstance(v, str):
        return None
    s = v.strip().lower()
    if s in ("reset", "default", "none", "transparent"):
        return "reset"
    if _HEX6.match(s):
        return s
    if _HEX3.match(s):
        return "#" + "".join(c * 2 for c in s[1:])
    m = re.match(r"^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$", s)
    if m and all(0 <= int(x) <= 255 for x in m.groups()):
        return "#%02x%02x%02x" % tuple(int(x) for x in m.groups())
    return _NOMBRES.get(s, 6)


def _norm(nombre):
    return str(nombre or "").lower().replace(" ", "-").replace("_", "-")


def canonico(nombre):
    """Nombre canónico de un tema de herdr (con sus alias) o None."""
    try:
        import herdr_paletas as HP
        return HP.ALIAS.get(_norm(nombre))
    except Exception:
        return None


# ── el fondo REAL (OSC 11) ───────────────────────────────────────────────────
_FONDO = {"hecho": False, "v": None}
_FONDO_VIGENCIA = 12 * 3600                 # la caché en disco vale medio día


def _cache_dir():
    try:
        import paths
        return os.path.join(paths.state_dir(), "cache")
    except Exception:
        return None


def parse_osc11(datos):
    """Respuesta de OSC 11 (`ESC ] 11 ; rgb:RRRR/GGGG/BBBB` + BEL o ST) →
    '#rrggbb'. Acepta de 1 a 4 dígitos por canal. None si no se entiende."""
    try:
        s = datos.decode("latin-1") if isinstance(datos, bytes) else str(datos)
    except Exception:
        return None
    m = re.search(r"\]11;rgba?:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})", s)
    if not m:
        return None
    canales = []
    for h in m.groups():
        tope = (16 ** len(h)) - 1
        canales.append(int(round(int(h, 16) * 255.0 / tope)))
    return "#%02x%02x%02x" % tuple(canales)


def _preguntar_tty(timeout):
    """Manda OSC 11 a la terminal y lee la respuesta (POSIX). None si no hay
    tty, no contesta a tiempo o algo falla. Restaura el modo de la tty."""
    if os.name == "nt":
        return None                          # ConPTY: sin consulta (como antes)
    import select
    import termios
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return None
    try:
        viejo = termios.tcgetattr(fd)
        nuevo = list(viejo)
        nuevo[3] &= ~(termios.ICANON | termios.ECHO)       # lflag
        termios.tcsetattr(fd, termios.TCSANOW, nuevo)
        try:
            os.write(fd, b"\033]11;?\033\\")
            buf, fin = b"", time.monotonic() + timeout
            while time.monotonic() < fin:
                r, _, _ = select.select([fd], [], [], max(0.0, fin - time.monotonic()))
                if not r:
                    break
                buf += os.read(fd, 256)
                if b"\x07" in buf or b"\033\\" in buf:
                    break
            return parse_osc11(buf)
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, viejo)
    except Exception:
        return None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def consultar_fondo(timeout=0.15, env=None):
    """Pregunta UNA vez por proceso el fondo REAL de la terminal (OSC 11; dentro
    de herdr contesta herdr con el de la terminal de afuera) y lo guarda en
    disco para los procesos que no preguntan. Solo si Workspace sigue a herdr.
    env WORKSPACE_FONDO_REAL=#rrggbb|no lo fija (tests). Devuelve '#rrggbb' o
    None. Jamás levanta."""
    env = os.environ if env is None else env
    if _FONDO["hecho"]:
        return _FONDO["v"]
    _FONDO["hecho"] = True
    ov = (env.get("WORKSPACE_FONDO_REAL") or "").strip().lower()
    if ov:
        _FONDO["v"] = ov if _HEX6.match(ov) else None
        return _FONDO["v"]
    try:
        if not seguir(env):
            return None
        v = _preguntar_tty(timeout)
    except Exception:
        v = None
    _FONDO["v"] = v
    if v:
        d = _cache_dir()
        if d:
            try:
                _guardar_cache(os.path.join(d, "herdr_fondo.json"), {"fondo": v, "t": time.time()})
            except Exception:
                pass
    return v


def _guardar_cache(ruta, datos):
    """Una caché en disco: temporal ÚNICO + os.replace (atomico.escribir), sin
    fsync ni reintentos (si falla, se recalcula). Dos procesos a la vez jamás
    escriben el mismo temporal: con uno de nombre fijo, uno truncaba el del
    otro y la caché quedaba con JSON roto (Greptile 0.9.0, 5). Sin candado: es
    una caché sin leer-cambiar-escribir; gana la última copia, entera."""
    import atomico
    atomico.escribir(ruta, json.dumps(datos), fsync=False, intentos=1)


def fondo_real(env=None):
    """El fondo real conocido: el que preguntó ESTE proceso, o el de la caché
    en disco (vigente medio día) que dejó el hub. None si no se sabe."""
    env = os.environ if env is None else env
    ov = (env.get("WORKSPACE_FONDO_REAL") or "").strip().lower()
    if ov:
        return ov if _HEX6.match(ov) else None
    if _FONDO["hecho"]:
        return _FONDO["v"]
    d = _cache_dir()
    if not d:
        return None
    try:
        with open(os.path.join(d, "herdr_fondo.json"), encoding="utf-8") as fh:
            j = json.load(fh)
        v = str(j.get("fondo") or "").lower()
        if _HEX6.match(v) and time.time() - float(j.get("t", 0)) < _FONDO_VIGENCIA:
            return v
    except Exception:
        pass
    return None


# ── claro/oscuro del sistema (auto_switch sin fondo real) ────────────────────
_AP = {"t": 0.0, "v": None}
_AP_TTL = 10.0


def apariencia_oscura(env=None):
    """True = oscuro, para auto_switch cuando no se sabe el fondo real. herdr
    decide por la terminal; aquí se aproxima con la apariencia del sistema
    (macOS AppleInterfaceStyle, Windows AppsUseLightTheme, GNOME
    color-scheme). Sin poder saber → oscuro. env WORKSPACE_APARIENCIA=claro|
    oscuro la fija (tests). Cacheada 10 s."""
    env = os.environ if env is None else env
    ov = (env.get("WORKSPACE_APARIENCIA") or "").strip().lower()
    if ov in ("claro", "light"):
        return False
    if ov in ("oscuro", "dark"):
        return True
    ahora = time.monotonic()
    if _AP["v"] is not None and ahora - _AP["t"] < _AP_TTL:
        return _AP["v"]
    v = True
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=1.5)
            v = (r.returncode == 0 and "dark" in (r.stdout or "").lower())
        elif os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion"
                                r"\Themes\Personalize") as k:
                v = (winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0)
        else:
            r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface",
                                "color-scheme"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=1.5)
            if r.returncode == 0 and "light" in (r.stdout or ""):
                v = False
    except Exception:
        v = True
    _AP.update(t=ahora, v=v)
    return v


# ── el tema efectivo de herdr ────────────────────────────────────────────────
def _tabla(nombre, respaldo):
    import herdr_paletas as HP
    c = canonico(nombre)
    if c and c in HP.PALETAS:
        return c, dict(HP.PALETAS[c])
    c = canonico(respaldo) or _DEFAULT
    return c, dict(HP.PALETAS.get(c) or HP.PALETAS[_DEFAULT])


def _encima(pal, custom):
    if isinstance(custom, dict):
        for k in CAMPOS:
            c = color(custom.get(k))
            if c is not None:
                pal[k] = c


def _es_oscuro(pal):
    """¿El tema es oscuro? Por su panel_bg; sin hex (tema «terminal») → None."""
    bg = pal.get("panel_bg")
    return (not _claro(bg)) if isinstance(bg, str) and _HEX6.match(bg) else None


def tema(env=None):
    """El tema EFECTIVO de herdr → {nombre, colores, auto, oscuro, fondo,
    pareja, path}, o None si no se pudo resolver nada. Resolución de herdr
    0.9.x (name → auto_switch → custom → [ui] accent → custom.dark|light) más
    el fondo real: con él, auto_switch decide por el fondo y un tema del lado
    contrario cambia a su pareja clara/oscura si existe (`pareja` = True)."""
    try:
        import herdr_paletas as HP
        path = config_path(env)
        cfg = leer_config(path)
        th = cfg.get("theme") if isinstance(cfg.get("theme"), dict) else {}
        ui = cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}
        manual = th.get("name") if isinstance(th.get("name"), str) else _DEFAULT
        her = HP.HERMANOS.get(_norm(manual), (manual, manual))
        auto = bool(th.get("auto_switch") is True)
        custom = th.get("custom") if isinstance(th.get("custom"), dict) else {}
        fondo = fondo_real(env)
        osc_real = (not _claro(fondo)) if fondo else None
        modo = None
        pareja = False
        if auto:
            oscuro = osc_real if osc_real is not None else apariencia_oscura(env)
            if oscuro:
                nombre = th.get("dark_name") if isinstance(th.get("dark_name"), str) else her[0]
                respaldo, modo = _DEFAULT, custom.get("dark")
            else:
                nombre = th.get("light_name") if isinstance(th.get("light_name"), str) else her[1]
                respaldo, modo = _DEFAULT_CLARO, custom.get("light")
            canon, pal = _tabla(nombre, respaldo)
        else:
            canon, pal = _tabla(manual, _DEFAULT)
            lado = _es_oscuro(pal)
            if osc_real is not None and lado is not None and lado != osc_real:
                d, c = HP.HERMANOS.get(canon, (canon, canon))
                otro = d if osc_real else c
                if otro != canon and otro in HP.PALETAS:
                    canon, pal, pareja = otro, dict(HP.PALETAS[otro]), True
        _encima(pal, custom)
        acento = ui.get("accent")
        if (isinstance(acento, str) and acento.strip().lower() != "cyan"
                and color(custom.get("accent")) is None):
            pal["accent"] = color(acento)           # el acento viejo de herdr
        _encima(pal, modo)
        oscuro = osc_real if osc_real is not None else _es_oscuro(pal)
        if oscuro is None:
            oscuro = apariencia_oscura(env) if auto else True
        return {"nombre": canon, "colores": pal, "auto": auto, "oscuro": oscuro,
                "fondo": fondo, "pareja": pareja, "path": path}
    except Exception:
        return None


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _claro(h):
    r, g, b = _rgb(h)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.5


def _aprox(v, oscuro, papel):
    """Hex APROXIMADO de un color de herdr para DERIVAR mezclas: un índice
    ANSI → su xterm por defecto; 'reset' → el fondo o la tinta típicos del
    lado (papel = 'fondo' | 'tinta')."""
    if isinstance(v, str) and _HEX6.match(v):
        return v.lower()
    if isinstance(v, int) and 0 <= v <= 15:
        return _ANSI16[v]
    if papel == "fondo":
        return "#1e1e1e" if oscuro else "#ffffff"
    return "#e5e5e5" if oscuro else "#1e1e1e"


def semantica(t=None, env=None):
    """Paleta SEMÁNTICA (la de theme_render: background, foreground, accent…)
    del tema de herdr, en hex. El fondo es el REAL si se conoce (OSC 11) y si
    no panel_bg (lo más cercano al fondo que herdr pinta); en el tema
    «terminal» se aproxima por el lado. None si no hay tema."""
    t = t or tema(env)
    if not t:
        return None
    c, osc = t["colores"], t["oscuro"]

    def h(k, papel="tinta"):
        return _aprox(c.get(k), osc, papel)
    bg = t.get("fondo") or h("panel_bg", "fondo")
    return {"background": bg, "foreground": h("text"),
            "cursor": h("accent"), "accent": h("accent"), "accent_2": h("mauve"),
            "muted": h("subtext0"), "faint": h("overlay0"),
            "surface": h("surface0", "fondo"), "border": h("surface1", "fondo"),
            "success": h("green"), "warning": h("yellow"), "danger": h("red"),
            "info": h("blue")}


# rol de tuitheme ← campo de herdr (lo que se pinta TAL CUAL, con el color
# exacto de herdr; lo demás — estrellas, brasas, el brillo del wordmark — se
# deriva por mezcla de la paleta semántica).
ROLES = {"text": "text", "accent": "accent", "mid": "mauve", "dim": "subtext0",
         "grey": "overlay0", "dark": "surface1", "inactive": "subtext0",
         "inactive_alt": "surface1", "ok": "green", "err": "red", "bad": "red"}


def _valor_rol(v):
    """Color de herdr → valor de rol de tuitheme: hex tal cual, índice ANSI
    tal cual (lo pinta la terminal) y 'reset' → 'default' (la tinta por
    defecto de la terminal, SGR 39)."""
    if isinstance(v, str) and _HEX6.match(v):
        return v.lower()
    if isinstance(v, int) and 0 <= v <= 255:
        return v
    return "default"


def bloque_tui(t=None, env=None):
    """Bloque `tui` (formato de themes/<id>/theme.json) del tema de herdr,
    SIN `osc`: dentro de herdr Workspace no pinta fondo, tinta ni cursor.
    Los colores de lectura se dejan legibles sobre el fondo (el real si se
    conoce): tinta ≥4.5:1, secundarios ≥3:1. None si no hay tema."""
    t = t or tema(env)
    if not t:
        return None
    sem = semantica(t)
    try:
        import theme_render as TR
        blk = TR.tui(TR.complete(sem)) or {}
    except Exception:
        blk = {}
    roles = dict(blk.get("roles") or {})
    bg = sem["background"]
    for rol, campo in ROLES.items():
        v = _valor_rol(t["colores"].get(campo))
        if isinstance(v, str) and v.startswith("#"):
            try:
                import theme_render as TR
                minimo = TR.TEXT_MIN if rol == "text" else TR.UI_MIN
                v = TR.legible(v, bg, minimo)
            except Exception:
                pass
        roles[rol] = v
    blk["roles"] = roles
    blk.pop("osc", None)
    return blk


def bloque_cacheado(huella):
    """(nombre, bloque) del tema de herdr para la `huella` de firma(), con el
    bloque guardado en disco: un proceso corto (statusline) no vuelve a leer
    ni a renderizar el tema si no cambió. Falla-suave → lo calcula."""
    clave = hashlib.sha1(repr(huella).encode("utf-8")).hexdigest()
    d = _cache_dir()
    ruta = os.path.join(d, "herdr_tema.json") if d else None
    if ruta:
        try:
            with open(ruta, encoding="utf-8") as fh:
                j = json.load(fh)
            if j.get("clave") == clave and isinstance(j.get("bloque"), dict):
                return j.get("nombre") or _DEFAULT, j["bloque"]
        except Exception:
            pass
    t = tema()
    blk = bloque_tui(t) or {}
    nombre = t["nombre"] if t else _DEFAULT
    if ruta:
        try:
            _guardar_cache(ruta, {"clave": clave, "nombre": nombre, "bloque": blk})
        except Exception:
            pass
    return nombre, blk


_FIRMA = {"t": None, "env": None, "v": None}


def firma(env=None):
    """Huella del tema de herdr que se pintaría ahora, o None si Workspace no
    sigue a herdr. Barata y LIMITADA: se recalcula como mucho cada _ttl()
    segundos (un stat de la config, el ajuste, el fondo real y, solo con
    auto_switch, la apariencia cacheada). Cambia → tuitheme re-resuelve y el
    hub se repinta."""
    envd = os.environ if env is None else env
    llave = tuple((envd.get(k) or "") for k in (
        "HERDR_PANE_ID", "HERDR_ENV", "HERDR_SOCKET_PATH", "HERDR_BIN_PATH",
        "HERDR_SESSION", "HERDR_CONFIG_PATH", "WORKSPACE_TEMA_HERDR",
        "WORKSPACE_FONDO_REAL", "WORKSPACE_APARIENCIA"))
    ahora = time.monotonic()
    if (_FIRMA["t"] is not None and _FIRMA["env"] == llave
            and ahora - _FIRMA["t"] < _ttl()):
        return _FIRMA["v"]
    v = _firma(env)
    _FIRMA.update(t=ahora, env=llave, v=v)
    return v


def _firma(env=None):
    if not seguir(env):
        return None
    path = config_path(env)
    mt, tam = _stat(path)
    cfg = leer_config(path)
    th = cfg.get("theme") if isinstance(cfg.get("theme"), dict) else {}
    fondo = fondo_real(env)
    ap = (apariencia_oscura(env) if (th.get("auto_switch") is True and not fondo)
          else None)
    return ("herdr", path, mt, tam, fondo, ap)


def etiqueta(env=None):
    """«herdr · <tema>» para mostrar qué tema manda ahora. '' si no sigue."""
    if not seguir(env):
        return ""
    t = tema(env)
    return "herdr · %s" % (t["nombre"] if t else _DEFAULT)
