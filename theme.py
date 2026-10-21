"""WORKSPACE · tema de color de la terminal por banner/agente.

Cambia el FONDO y el TEXTO de la terminal según el agente activo, vía secuencias OSC
(10=texto, 11=fondo, 12=cursor) — soportadas por Terminal.app, iTerm, Windows Terminal,
WezTerm, etc. — y, donde la terminal la devuelve, la paleta 0-15 (OSC 4, ver
palette_terminal). Al salir del hub restaura los colores por defecto (OSC
104/110/111/112); tras un motor abierto con exec, la terminal conserva los colores
del tema hasta cerrar la pestaña. Al motor se le dice si el fondo pintado es claro
u oscuro (engine_env).

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


def background_color(theme_bg=None, theme_fg=None):
    """Fondo elegido aparte (ui.background), o None. Con `theme_bg` (el fondo
    propio del tema) solo vale un fondo del MISMO lado — claro u oscuro, con
    la fórmula de Claude Code — y, si se conoce la tinta del tema (`theme_fg`),
    uno sobre el que esa tinta se lee (≥4.5:1). Un fondo oscuro sobre un tema
    claro dejaba su tinta negra invisible; uno claro sobre un tema oscuro (que
    antes pasaba) dejaba tinta clara sobre claro (1.1:1) en el hub, el chat y
    cada motor. Sin tema que comparar (uno sin tui.osc) el fondo vale tal cual:
    tuitheme le pone después una tinta legible."""
    try:
        import settings, re
        choice = settings.get("ui.background", "tema")
        color = (settings.get("ui.background_custom") if choice == "personalizado"
                 else BACKGROUND_COLORS.get(choice))
        if not (isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color)):
            return None
        if (isinstance(theme_bg, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", theme_bg)
                and _is_light(theme_bg) != _is_light(color)):
            return None
        if isinstance(theme_fg, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", theme_fg):
            import theme_render
            if theme_render.contrast(theme_fg, color) < theme_render.TEXT_MIN:
                return None
        return color
    except Exception:
        return None


def apply(name):
    """Aplica el tema `name` (fondo/texto/cursor) vía OSC. No-op si no existe."""
    apply_colors(_themes().get(name) or {})


# Lo último que ESTE proceso pintó en una terminal real ({bg, fg, cursor}), o
# None (nada pintado: sin tty, terminal sin color, tema sin tui.osc, o ya se
# restauró). Lo lee engine_env: al motor solo se le cuenta lo que se pintó.
_PAINTED = None


def _emit(seq):
    """Escribe `seq` a la terminal REAL. True si llegó a una tty. Falla-suave."""
    try:
        w = _tty(); w.write(seq); w.flush()
    except Exception:
        return False
    try:
        return bool(w.isatty())
    except Exception:
        return False


def apply_colors(t):
    """Aplica colores EXPLÍCITOS {bg,fg,cursor} (hex) vía OSC — para los temas
    del TUI (tuitheme.py): un tema no-default trae su propio fondo/tinta en el
    bloque "tui.osc" de themes/<id>/theme.json. Mismo contrato que apply():
    no-op silencioso si no hay nada que aplicar o no hay tty. Con fondo y en
    una terminal que devuelve su paleta (palette_terminal), fija también los
    16 colores ANSI desde el tema (palette_seq). El OSC de tuitheme.palette()
    ya trae resuelto el fondo aparte y la luz roja (RESUELTO): se pinta tal
    cual (antes se le volvía a aplicar el fondo aparte y se perdía el rojo)."""
    global _PAINTED
    resuelto = bool(getattr(t, "RESUELTO", False))
    t = dict(t or {})
    bg = None if resuelto else background_color(t.get("bg"), t.get("fg"))
    if bg:
        t["bg"] = bg
    seq = ""
    if t.get("bg"):     seq += f"\033]11;{t['bg']}\007"
    if t.get("fg"):     seq += f"\033]10;{t['fg']}\007"
    if t.get("cursor"): seq += f"\033]12;{t['cursor']}\007"
    if not seq:
        return
    pal = palette_seq(t) if t.get("bg") and palette_terminal() else ""
    if _emit(seq + pal) and t.get("bg"):
        _PAINTED = {k: t[k] for k in ("bg", "fg", "cursor") if t.get(k)}
        if pal:
            _PAINTED["palette"] = True


# ── paleta ANSI 0-15 ────────────────────────────────────────────────────────
# Bajo el fondo del tema queda la paleta 0-15 del PERFIL, pensada para SU
# fondo: Terminal.app «Basic» (blanco) deja negro 1.2:1, azul 1.4 y rojo 2.0
# sobre bruma; Campbell de Windows Terminal, negro 1.1 y azul 2.1. Codex y toda
# salida ANSI escriben con esos colores. Donde la terminal APLICA OSC 4 Y la
# devuelve al perfil con OSC 104, Workspace fija los 16 desde el tema
# (theme_render.ansi16: ≥3:1, blancos ≥4.5:1); en el resto no se toca nada.
# Verificado (2026-10-20):
#   · iTerm2 ≥ 3.5: OSC 4/104/110-112 en su parser (commit e7a5cdd, 2021,
#     llega en la 3.5.0; la rama 3.4 no lo tiene).
#   · Terminal.app 2.15 (build 470, macOS 26.6): el desensamblado de su
#     emulador maneja OSC 4 y 5, 10-19, 104 (todo o por casilla), 105 y
#     110-117. Builds anteriores: sin verificar → no se toca.
#   · Windows Terminal (WT_SESSION): OSC 4 desde la 1.x; 104/110-112 desde la
#     1.22.11141 / 1.23 (#18767, abril 2025). Una más vieja ignora los resets
#     de TODO (fondo incluido): el tema queda entero y legible hasta cerrar.
#   · WezTerm, Ghostty, kitty: documentados (kitty: vt-parser.c, 4/104).
#   · VS Code (xterm.js): 4, 104, 110-112 en su tabla de secuencias; en
#     Windows pasa por ConPTY → sin verificar → no se toca.
# Fuera: la consola clásica de Windows (conhost: 104 solo en builds muy
# nuevas), multiplexores (tmux, screen, zellij, herdr: la secuencia no llega a
# la terminal de afuera) y cualquier terminal desconocida.
# WORKSPACE_PALETTE=0/1 lo fuerza (pruebas manuales).
def _version_ge(text, want):
    try:
        got = tuple(int(x) for x in str(text).strip().split(".")[:len(want)])
    except ValueError:
        return False
    return bool(got) and got >= tuple(want)


def palette_terminal(env=None):
    """'' si en esta terminal NO se toca la paleta 0-15; si no, su nombre."""
    e = os.environ if env is None else env
    ov = (e.get("WORKSPACE_PALETTE") or "").strip().lower()
    if ov in ("0", "no", "off"):
        return ""
    if ov in ("1", "si", "sí", "on"):
        return "forzada"
    if any(e.get(k) for k in ("TMUX", "STY", "ZELLIJ", "HERDR_ENV")):
        return ""
    if e.get("WT_SESSION"):
        return "windows-terminal"
    if os.name == "nt":
        return ""
    tp = (e.get("TERM_PROGRAM") or "").strip()
    ver = e.get("TERM_PROGRAM_VERSION") or ""
    if tp == "iTerm.app":
        return "iterm2" if _version_ge(ver, (3, 5)) else ""
    if tp == "Apple_Terminal":
        return "terminal.app" if _version_ge(ver, (470,)) else ""
    if tp in ("WezTerm", "ghostty", "vscode"):
        return tp.lower()
    if (e.get("TERM") or "") == "xterm-kitty" or e.get("KITTY_WINDOW_ID"):
        return "kitty"
    return ""


def palette_seq(osc):
    """OSC 4 de las 16 casillas para el fondo/tinta `osc` con la paleta del
    tema del hub (theme_render.ansi16). '' si no se puede armar."""
    try:
        import theme_render
        pal = theme_render.engine_palette(osc=osc)
        if not pal:                                 # tema sin paleta (olympo)
            pal = {k: osc[v] for k, v in (("background", "bg"), ("foreground", "fg"))
                   if osc.get(v)}
        return "".join("\033]4;%d;rgb:%s/%s/%s\007" % (i, h[1:3], h[3:5], h[5:7])
                       for i, h in enumerate(theme_render.ansi16(pal)))
    except Exception:
        return ""


# Secuencia de reset como string (SSOT): la consume reset() y el greeter del
# shell (sin invocar python). Antes el literal estaba duplicado dentro de reset().
# 104 = toda la paleta 0-15 al perfil (la que fija apply_colors).
RESET_SEQ = "\033]104\007\033]111\007\033]110\007\033]112\007"


def reset():
    """Restaura la paleta 0-15 y el fondo/texto/cursor por defecto de la terminal."""
    global _PAINTED
    _PAINTED = None
    try:
        w = _tty(); w.write(RESET_SEQ); w.flush()
    except Exception:
        pass


def engine_vars(bg):
    """Las variables con que cada motor decide si el fondo es claro u oscuro,
    para el fondo `bg` (#rrggbb). {} si `bg` no es un hex.
      · COLORFGBG "15;0" (oscuro) / "0;15" (claro): Claude Code (tema «auto»,
        si su consulta OSC 11 no responde), Hermes y OpenClaw leen el último
        campo — ≤6 u 8 = oscuro, 7 o 15 = claro.
      · OPENCLAW_THEME dark/light: la elección explícita de OpenClaw.
      · HERMES_TUI_BACKGROUND=#rrggbb: la pista de fondo de Hermes (va antes
        que COLORFGBG; su CLI y su TUI la leen). Sin ella, Hermes en
        Terminal.app asume perfil CLARO y escribe #1A1A1A sobre el fondo oscuro.
    Claro/oscuro con la fórmula de Claude Code (_is_light)."""
    import re
    if not (isinstance(bg, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", bg)):
        return {}
    light = _is_light(bg)
    return {"COLORFGBG": "0;15" if light else "15;0",
            "OPENCLAW_THEME": "light" if light else "dark",
            "HERMES_TUI_BACKGROUND": bg.lower()}


def engine_env(env=None):
    """Le dice al motor la verdad sobre el fondo: si este proceso PINTÓ la
    terminal (apply_current/apply_colors), exporta engine_vars de ese fondo a
    `env` (default os.environ, que hereda el motor). Sin nada pintado no toca
    nada: lo que la terminal o el socio exportaron sigue valiendo. Devuelve lo
    exportado ({} si nada). Falla-suave: jamás levanta."""
    try:
        out = engine_vars((_PAINTED or {}).get("bg"))
        if out:
            (os.environ if env is None else env).update(out)
        return out
    except Exception:
        return {}


def apply_current():
    """Fondo/tinta/cursor del tema ELEGIDO (ui.theme + ui.background), igual
    que el hub: el bloque tui.osc del tema; sin OSC (terminal sin color /
    NO_COLOR, o un tema propio sin `tui.osc`) se RESTAURAN los colores de la
    terminal — ya no el negro/crema del recinto viejo («workspace» de
    themes.json). Única fuente: hub, secciones, onboarding y el arranque de
    un agente llaman AQUÍ. Falla-suave: jamás levanta."""
    try:
        import tuitheme
        osc = getattr(tuitheme.palette(), "OSC", None)
    except Exception:
        osc = None
    if osc:
        apply_colors(osc)
    else:
        reset()


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
