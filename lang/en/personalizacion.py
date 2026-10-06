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
}
