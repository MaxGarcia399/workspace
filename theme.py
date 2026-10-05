"""WORKSPACE · tema de color de la terminal por banner/agente.

Cambia el FONDO y el TEXTO de la terminal según el agente activo, vía secuencias OSC
(10=texto, 11=fondo, 12=cursor) — soportadas por Terminal.app, iTerm, Windows Terminal,
WezTerm, etc. Al salir restaura los colores por defecto (OSC 110/111/112).

Las paletas viven en `themes.json` (editable por el equipo, se propaga por git).
Cero dependencias (stdlib). No-op silencioso si la terminal no soporta OSC o no hay tty.
"""
import os, json

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
        lp = os.path.join(os.path.expanduser("~"), ".claude", "workspace",
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
    return base


def _tty():
    # Escribir al terminal REAL (no a stdout, que puede estar redirigido).
    try:
        return open("/dev/tty", "w")
    except Exception:
        import sys
        return sys.stdout


BACKGROUND_COLORS = {"negro": "#000000", "grafito": "#181818",
                     "azul": "#0c1424", "verde": "#0c1c16", "violeta": "#1a1024"}


def background_color():
    try:
        import settings, re
        choice = settings.get("ui.background", "tema")
        color = (settings.get("ui.background_custom") if choice == "personalizado"
                 else BACKGROUND_COLORS.get(choice))
        return color if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) else None
    except Exception:
        return None


def apply(name):
    """Aplica el tema `name` (fondo/texto/cursor) vía OSC. No-op si no existe."""
    t = dict(_themes().get(name) or {})
    if background_color():
        t["bg"] = background_color()
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
    if background_color():
        t["bg"] = background_color()
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


def reset():
    """Restaura fondo/texto/cursor por defecto de la terminal."""
    try:
        w = _tty(); w.write("\033]111\007\033]110\007\033]112\007"); w.flush()
    except Exception:
        pass


# Secuencia de reset como string (para el greeter del shell, sin invocar python).
RESET_SEQ = "\033]111\007\033]110\007\033]112\007"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        reset()
    elif len(sys.argv) > 1:
        apply(sys.argv[1])
