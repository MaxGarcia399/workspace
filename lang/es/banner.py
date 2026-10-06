"""WORKSPACE · lang/es/banner — el TEMPLATE de banner de agente (brand/agent-banner,
agent-dashboard, agent-statusline). FUENTE ES: cada valor es el literal español
EXACTO que el template mostraba hardcodeado (byte-idéntico por default). La
identidad del agente (display/tagline/emblema/paleta) NO vive aquí — sale de
agent.json/BOOT. Traducción en `lang/en/banner.py`. Ver `lang/README.md`."""

STRINGS = {
    # ── banner (agent-banner.py): encabezados de sección ─────────────────────
    "banner.sec.skills": "Skills",
    "banner.sec.system": "Sistema",
    "banner.sec.domain": "Dominio",
    # etiquetas de fila
    "banner.lbl.categories": "categorías",
    "banner.lbl.base": "base",
    "banner.lbl.memory": "memoria",
    "banner.lbl.loop": "loop",
    "banner.lbl.scope": "alcance",
    # contenido (subtítulos / valores)
    "banner.cats.default": "investigación · meta",
    "banner.base.row1": "skill-creator · skill-improver · skill-curator · reload-brain",
    "banner.base.row2": "deep-research · research-session",
    "banner.sys.memory": "tiers caliente/tibia/fría · core blocks · Dreaming→DESTILADO",
    "banner.sys.loop": "skill loop SIEMPRE activo · bloque 🧠 obligatorio",
    # pie
    "banner.foot": "nacido del template de WORKSPACE",

    # ── dashboard (agent-dashboard.py): picker/greeter de sesiones ───────────
    "banner.dash.sessions_count": "{n} sesión(es) · elige una para continuar o crea una nueva",
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
