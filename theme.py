"""WORKSPACE · tema de color de la terminal por banner/agente.

Cambia el FONDO y el TEXTO de la terminal según el agente activo, vía secuencias OSC
(10=texto, 11=fondo, 12=cursor) — soportadas por Terminal.app, iTerm, Windows Terminal,
WezTerm, etc. Al salir restaura los colores por defecto (OSC 110/111/112).

Las paletas viven en `themes.json` (repo) + `themes.local.json` (perfil per-máquina,
gana por nombre); una entrada puede referenciar un tema del hub ({"theme": "<id>"})
y heredar su paleta semántica (theme_render.py — la fuente única de color).
Cero dependencias (stdlib). No-op silencioso si la terminal no soporta OSC o no hay tty.
"""
import os, json
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)

ROOT = os.path.dirname(os.path.abspath(__file__))


def _themes():
    """themes.json del repo + overlay PERSONAL de themes.local.json
    (~/.claude/workspace/ — per-máquina, gana por nombre mergeando por clave).
    Lo escribe config_engine.set_theme_local; jamás se commitea. Falla-suave."""
    try:
        base = json.load(open(os.path.join(ROOT, "themes.json"), encoding="utf-8"))
        if not isinstance(base, dict):
            base = {}
    except Exception:
        base = {}
    try:
        lp = os.path.join(_paths.state_dir(),
                          "themes.local.json")
        local = json.load(open(lp, encoding="utf-8"))
        if isinstance(local, dict):
            for name, pal in local.items():
                if isinstance(pal, dict):
                    merged = dict(base.get(name) or {})
                    merged.update(pal)
                    base[name] = merged
    except Exception:
        pass
    # Referencia a un tema del HUB: {"theme": "<id>", "bg"…} hereda fondo/
    # tinta/cursor de la paleta de themes/<id>/theme.json (theme_render). El
    # tema referenciado gana mientras exista; bg/fg guardados al lado son la
    # copia para versiones viejas (que ignoran "theme") y el respaldo si el
    # tema del hub desaparece. Sin "theme" = la entrada de siempre, intacta.
    for name, pal in list(base.items()):
        if isinstance(pal, dict) and isinstance(pal.get("theme"), str):
            try:
                import theme_render
                hp = theme_render.hub_palette(pal["theme"].strip().lower())
                o = theme_render.osc(hp) if hp else None
                if o:
                    base[name] = dict(pal, **o)
            except Exception:
                pass
    return base


def _tty():
    # Escribir al terminal REAL (no a stdout, que puede estar redirigido).
    # En Windows "/dev/tty" es "<unidad>:/dev/tty": si existe C:/dev, open()
    # crea un ARCHIVO y el color nunca llega a la consola. CONOUT$ es la consola.
    import sys
    if os.name == "nt":
        try:
            return open("CONOUT$", "w", encoding="utf-8")
        except Exception:
            return sys.stdout
    try:
        return open("/dev/tty", "w")
    except Exception:
        return sys.stdout


BACKGROUND_COLORS = {"negro": "#000000", "grafito": "#181818",
                     "azul": "#0c1424", "verde": "#0c1c16", "violeta": "#1a1024"}


def _is_light(h):
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.5
    except Exception:
        return False


def background_color(theme_bg=None):
    """Fondo elegido aparte (ui.background), o None. Con `theme_bg` (el fondo
    propio del tema) se ignora un fondo OSCURO sobre un tema CLARO (blanco,
    estudio): su tinta es negra y quedaría invisible. Al revés no: un fondo
    claro sobre un tema oscuro se sigue leyendo y es elección del usuario."""
    try:
        import settings, re
        choice = settings.get("ui.background", "tema")
        color = (settings.get("ui.background_custom") if choice == "personalizado"
                 else BACKGROUND_COLORS.get(choice))
        if not (isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
            return None
        if (isinstance(theme_bg, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", theme_bg)
                and _is_light(theme_bg) and not _is_light(color)):
            return None
        return color
    except Exception:
        return None


def apply(name):
    """Aplica el tema `name` (fondo/texto/cursor) vía OSC. No-op si no existe."""
    t = dict(_themes().get(name) or {})
    bg = background_color(t.get("bg"))
    if bg:
        t["bg"] = bg
    seq = ""
    if t.get("bg"):     seq += f"\033]11;{t['bg']}\007"
    if t.get("fg"):     seq += f"\033]10;{t['fg']}\007"
    if t.get("cursor"): seq += f"\033]12;{t['cursor']}\007"
    if not seq:
        return
    try:
        w = _tty(); w.write(seq); w.flush()
    except Exception:
        pass


def apply_colors(t):
    """Aplica colores EXPLÍCITOS {bg,fg,cursor} (hex) vía OSC — para los temas
    del TUI (tuitheme.py): un tema no-default trae su propio fondo/tinta en el
    bloque "tui.osc" de themes/<id>/theme.json. Mismo contrato que apply():
    no-op silencioso si no hay nada que aplicar o no hay tty."""
    t = dict(t or {})
    bg = background_color(t.get("bg"))
    if bg:
        t["bg"] = bg
    seq = ""
    if t.get("bg"):     seq += f"\033]11;{t['bg']}\007"
    if t.get("fg"):     seq += f"\033]10;{t['fg']}\007"
    if t.get("cursor"): seq += f"\033]12;{t['cursor']}\007"
    if not seq:
        return
    try:
        w = _tty(); w.write(seq); w.flush()
    except Exception:
        pass


# Secuencia de reset como string (SSOT): la consume reset() y el greeter del
# shell (sin invocar python). Antes el literal estaba duplicado dentro de reset().
RESET_SEQ = "\033]111\007\033]110\007\033]112\007"


def reset():
    """Restaura fondo/texto/cursor por defecto de la terminal."""
    try:
        w = _tty(); w.write(RESET_SEQ); w.flush()
    except Exception:
        pass


def apply_current():
    """Fondo/tinta/cursor del tema ELEGIDO (ui.theme + ui.background), igual
    que el hub: el bloque tui.osc del tema, o la paleta clásica si no trae.
    Falla-suave: jamás levanta."""
    try:
        import tuitheme
        osc = getattr(tuitheme.palette(), "OSC", None)
    except Exception:
        osc = None
    if osc:
        apply_colors(osc)
    else:
        apply("workspace")


# True mientras el hub corre una sección DENTRO de su proceso (front.py,
# loopback): al salir, la sección deja puesto el tema (el hub sigue en
# pantalla). Fuera del hub (`workspace calendario` desde el shell), la
# sección restaura la terminal al salir.
HOSTED = False


def screen(fn):
    """Decorador para el run() de cada pantalla: aplica el tema y el fondo
    elegidos al entrar, y al salir los deja (dentro del hub) o restaura la
    terminal (desde el shell). Así el tema es global, no solo del hub."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **k):
        apply_current()
        try:
            return fn(*a, **k)
        finally:
            if HOSTED:
                apply_current()
            else:
                reset()
    return wrapper


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        reset()
    elif len(sys.argv) > 1:
        apply(sys.argv[1])
