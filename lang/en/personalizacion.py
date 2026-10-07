"""WORKSPACE · lang/en/personalizacion — PERSONALIZATION — the THEME section of
CONFIG (config_tui.py): hub theme, independent background, starry sky /
animations, the background options, the theme picker and save confirmations.
EN (translation of lang/es/personalizacion.py). Theme NAMES (mono/cyberpunk/
rose/…) are brand ids and stay verbatim; only the labels around them translate."""

STRINGS = {
    # ── THEME section (title · description · subtitle with the active theme) ──
    "personalizacion.section.title": "THEME",
    "personalizacion.section.desc":
        "hub appearance (the web dev panel uses ui.web_theme)",
    "personalizacion.section.sub_active": "active {name}",

    # ── control labels ──────────────────────────────────────────────────────
    "personalizacion.theme.label": "Hub theme",
    "personalizacion.background.label": "Independent background",
    "personalizacion.background_custom.label": "Custom background color",
    "personalizacion.brightness.label": "Brightness",
    "personalizacion.redlight.label": "Red light (night mode)",
    "personalizacion.autostart.label": "Open when the terminal opens",
    "personalizacion.stars.label": "Starry sky",
    "personalizacion.anim.label": "Animations",

    # ── explanatory text (what each control does) ───────────────────────────
    "personalizacion.theme.help":
        "Visual theme of the hub's HUB/TUI (front.py/banner/config_tui). "
        "Limited to the TUI-ready themes (mono, cyberpunk, rose, durazno, "
        "lavanda, salvia, bruma). The web dev panel has its own theme "
        "(ui.web_theme, all available). env WORKSPACE_THEME always wins.",
    "personalizacion.background.help":
        "Changes the background only; 'theme' restores the active theme's "
        "background.",
    "personalizacion.background_custom.help":
        "Color #RRGGBB; pick 'custom' under Independent background.",
    "personalizacion.brightness.help":
        "How vivid the TUI looks. ◄► adjusts it LIVE: 0 = the theme's palette "
        "as-is; + raises the colors' lightness and saturation (not the "
        "background), − dims them. Works with any theme; text always stays "
        "legible.",
    "personalizacion.redlight.help":
        "RED night mode for late hours. ON remaps the whole palette to a warm "
        "red/amber (lowers blue/green and overall lightness) while keeping "
        "legibility and hierarchy; OFF = the theme's palette as-is. Does "
        "nothing in mono.",
    "personalizacion.autostart.help":
        "ON = every new terminal opens the Workspace menu (rc greeter) in ANY "
        "terminal (iTerm2, VS Code, etc.); OFF = Workspace opens only with the "
        "`workspace` command (default, less invasive). Rewrites the greeter "
        "block in ~/.zshrc. env WORKSPACE_NO_GREETER=1 disables it no matter "
        "what.",
    "personalizacion.stars.help":
        "Static star field of the hub (front.py).",
    "personalizacion.anim.help":
        "Animated hub menu and animated banner (without it: static + picker).",

    # ── background options (the SAVED value stays the raw id) ───────────────
    "personalizacion.background.opt.tema": "theme",
    "personalizacion.background.opt.negro": "black",
    "personalizacion.background.opt.grafito": "graphite",
    "personalizacion.background.opt.azul": "blue",
    "personalizacion.background.opt.verde": "green",
    "personalizacion.background.opt.violeta": "violet",
    "personalizacion.background.opt.personalizado": "custom",

    # ── theme/layout picker (prompt + footer hint) ──────────────────────────
    "personalizacion.pick.what_theme": "theme",
    "personalizacion.pick.what_layout": "layout",
    "personalizacion.pick.prompt": "  pick {what} ›  ",
    "personalizacion.pick.hint":
        "↑↓ or 1-9 to choose · Enter applies & saves · Esc cancels",

    # ── save confirmations ──────────────────────────────────────────────────
    "personalizacion.saved.mark": "» saved",
    "personalizacion.saved.theme":
        "saved: theme → {label} ({id}) — the hub paints it on reopen; "
        "the web panel on refresh",
    "personalizacion.saved.layout":
        "saved: layout → {label} ({id}) — the hub redraws this way on reopen "
        "(workspace)",

    # ── BRIGHTNESS control (slider + live sample + states) ──────────────────
    "personalizacion.brightness.softer": "− dim",
    "personalizacion.brightness.brighter": "vivid +",
    "personalizacion.brightness.preview": "sample",
    "personalizacion.brightness.hint": "◄► adjust brightness · 0 = no change",
    "personalizacion.brightness.use_arrows":
        "use ◄► to raise or lower the brightness",
    "personalizacion.brightness.saved":
        "saved: brightness → {n} — the hub paints it instantly",
    "personalizacion.brightness.at_edge": "brightness at {edge} ({n})",
    "personalizacion.brightness.min": "min",
    "personalizacion.brightness.max": "max",
}
