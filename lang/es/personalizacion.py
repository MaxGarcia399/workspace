"""WORKSPACE · lang/es/personalizacion — PERSONALIZACIÓN — sección TEMA del
CONFIG (config_tui.py): tema del hub, fondo independiente, cielo/animaciones,
las opciones de fondo, el picker de tema y las confirmaciones de guardado.

FUENTE (español): cada valor es el literal EXACTO que config_tui mostraba
hardcodeado, byte-idéntico ⇒ sin `ui.lang` nada cambia. La traducción vive en
`lang/en/personalizacion.py`. OJO: los NOMBRES de tema (mono/cyberpunk/rose/…)
son identificadores de marca y NO se traducen; sí las etiquetas alrededor.
Ver `lang/README.md`."""

STRINGS = {
    # ── sección TEMA (título · descripción · subtítulo con el tema activo) ──
    "personalizacion.section.title": "TEMA",
    "personalizacion.section.desc":
        "apariencia del hub (el dev panel web usa ui.web_theme)",
    "personalizacion.section.sub_active": "activo {name}",

    # ── labels de los controles ─────────────────────────────────────────────
    "personalizacion.theme.label": "Tema del hub",
    "personalizacion.background.label": "Fondo independiente",
    "personalizacion.background_custom.label": "Color de fondo propio",
    "personalizacion.brightness.label": "Brillo",
    "personalizacion.redlight.label": "Luz roja (modo noche)",
    "personalizacion.autostart.label": "Abrir al abrir la terminal",
    "personalizacion.stars.label": "Cielo estrellado",
    "personalizacion.anim.label": "Animaciones",

    # ── textos explicativos (qué hace cada control) ─────────────────────────
    "personalizacion.theme.help":
        "Tema visual del HUB/TUI del recinto (front.py/banner/config_tui). "
        "Acotado a los temas TUI-ready (mono, cyberpunk, rose, durazno, "
        "lavanda, salvia, bruma). El dev panel web tiene su propio tema "
        "(ui.web_theme, todos disponibles). env WORKSPACE_THEME gana siempre.",
    "personalizacion.background.help":
        "Cambia solo el fondo; tema recupera el fondo del tema activo.",
    "personalizacion.background_custom.help":
        "Color #RRGGBB; elige personalizado en Fondo independiente.",
    "personalizacion.brightness.help":
        "Qué tan vivo se ve el TUI. ◄► ajusta EN VIVO: 0 = la paleta del tema "
        "tal cual; + sube luminosidad y saturación de los colores (no del "
        "fondo), − los apaga. Sirve con cualquier tema; el texto siempre queda "
        "legible.",
    "personalizacion.redlight.help":
        "Modo noche en ROJO para madrugadas. ON remapea toda la paleta a un "
        "rojo/ámbar cálido (baja el azul/verde y la luminosidad) conservando "
        "legibilidad y jerarquía; OFF = la paleta del tema tal cual. En mono no "
        "hace nada.",
    "personalizacion.autostart.help":
        "ON = cada terminal nueva abre el menú de Workspace (greeter del rc) en "
        "CUALQUIER terminal (iTerm2, VS Code, etc.); OFF = Workspace solo abre "
        "con el comando `workspace` (default, menos invasivo). Reescribe el "
        "bloque del greeter en ~/.zshrc. env WORKSPACE_NO_GREETER=1 lo desactiva "
        "pase lo que pase.",
    "personalizacion.stars.help":
        "Campo de estrellas estático del recinto (front.py).",
    "personalizacion.anim.help":
        "Menú animado del recinto y banner animado (sin esto: estático + picker).",

    # ── opciones del fondo (el valor GUARDADO sigue siendo el id crudo) ─────
    "personalizacion.background.opt.tema": "tema",
    "personalizacion.background.opt.negro": "negro",
    "personalizacion.background.opt.grafito": "grafito",
    "personalizacion.background.opt.azul": "azul",
    "personalizacion.background.opt.verde": "verde",
    "personalizacion.background.opt.violeta": "violeta",
    "personalizacion.background.opt.personalizado": "personalizado",

    # ── picker de tema/layout (prompt + hint del pie) ───────────────────────
    "personalizacion.pick.what_theme": "tema",
    "personalizacion.pick.what_layout": "layout",
    "personalizacion.pick.prompt": "  elegir {what} ›  ",
    "personalizacion.pick.hint":
        "↑↓ o 1-9 eligen · Enter aplica y guarda · Esc cancela",

    # ── confirmaciones de guardado ──────────────────────────────────────────
    "personalizacion.saved.mark": "» guardado",
    "personalizacion.saved.theme":
        "guardado: tema → {label} ({id}) — el recinto lo pinta al reabrirse; "
        "el panel web al refrescar",
    "personalizacion.saved.layout":
        "guardado: layout → {label} ({id}) — el hub se dibuja así al reabrirse "
        "(workspace)",

    # ── control de BRILLO (slider + muestra en vivo + estados) ──────────────
    "personalizacion.brightness.softer": "− apagado",
    "personalizacion.brightness.brighter": "vivo +",
    "personalizacion.brightness.preview": "muestra",
    "personalizacion.brightness.hint": "◄► ajusta el brillo · 0 = sin cambios",
    "personalizacion.brightness.use_arrows":
        "usa ◄► para subir o bajar el brillo",
    "personalizacion.brightness.saved":
        "guardado: brillo → {n} — el hub lo pinta al instante",
    "personalizacion.brightness.at_edge": "brillo al {edge} ({n})",
    "personalizacion.brightness.min": "mínimo",
    "personalizacion.brightness.max": "máximo",
}
