"""WORKSPACE · lang/es/banner — el TEMPLATE de banner de agente (brand/agent-banner,
agent-dashboard, agent-statusline). FUENTE ES: cada valor es el literal español
EXACTO que el template mostraba hardcodeado (byte-idéntico por default). La
identidad del agente (display/tagline/emblema/paleta) NO vive aquí — sale de
agent.json/BOOT. Traducción en `lang/en/banner.py`. Ver `lang/README.md`."""

STRINGS = {
    # ── dashboard (agent-dashboard.py): picker/greeter de sesiones ───────────
    "banner.dash.sessions_count": "{n} sesión(es) · cada una recuerda lo suyo, en cualquier motor · elige una o crea una nueva",
    "banner.dash.resume_q": "¿En qué seguimos?",
    "banner.dash.hint": "↑↓ para elegir · Enter para abrir",
    "banner.dash.sub_continue": "continuar",
    "banner.dash.sub_new": "nueva",
    "banner.dash.new_label": "+ Sesión nueva…",
    "banner.dash.new_sub": "crea una sesión con nombre",
    "banner.dash.number_enter": "Número y Enter: ",
    "banner.dash.no_sessions": "(sin sesiones)",
    "banner.dash.name_prompt": "Nombre de la sesión: ",
    "banner.dash.loading": "cargando…",

    # ── statusline (agent-statusline.py): etiquetas de barras y texto ────────
    "banner.status.context": "contexto",
    "banner.status.session_use": "uso sesión",
    "banner.status.weekly_use": "uso semanal",
    "banner.status.resets_in": "se reinicia en ",
    "banner.status.no_data": "— dato tras el 1er mensaje",
    "banner.status.active": "activa ",
    "banner.status.now": "ya",
}
