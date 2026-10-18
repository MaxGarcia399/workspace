"""WORKSPACE · lang/es/settings_ui — etiquetas y valores de los AJUSTES tal
como se pintan en el hub (pins de PERSONALIZACIÓN/CONFIGS — settings.pin_label
y settings.pin_value_display). FUENTE ES = el label del schema (settings.py)
byte-idéntico; el store y los valores guardados NO cambian con el idioma.
Los ids de marca (temas, motores) no se traducen."""

STRINGS = {
    'settings_ui.label.latido.mode': 'Modo del latido',
    'settings_ui.label.latido.intensity': 'Intensidad del latido',
    'settings_ui.label.hooks.skill_review': 'Skill review (SessionEnd)',
    'settings_ui.label.hooks.transcript_backup': 'Backup de transcripts (Y2b)',
    'settings_ui.label.hooks.memory_flush': 'Memory flush (PreCompact, N2)',
    'settings_ui.label.hooks.security_guidance': 'Security guidance (PostToolUse, N15)',
    'settings_ui.label.hooks.telemetry': 'Telemetría en vivo (Pre/PostToolUse, N-telem)',
    'settings_ui.label.modelos.default_engine': 'Motor por default',
    'settings_ui.label.agentes.default_agent': 'Agente por default',
    'settings_ui.label.agentes.auto_mode': 'Auto-mode en sesiones interactivas',
    'settings_ui.label.ui.anim': 'Animaciones',
    'settings_ui.label.ui.autostart': 'Abrir al abrir la terminal',
    'settings_ui.label.ui.lang': 'Idioma',
    'settings_ui.label.ui.background': 'Fondo independiente',
    'settings_ui.label.ui.brightness': 'Brillo',
    'settings_ui.label.ui.redlight': 'Luz roja (modo noche)',
    'settings_ui.label.ui.titles': 'Títulos grandes',
    'settings_ui.label.ui.theme': 'Tema del hub',
    'settings_ui.label.ui.web_theme': 'Tema del dev panel (web)',
    'settings_ui.label.ui.split': 'Terminal partida',
    'settings_ui.label.ui.split_backend': 'Backend de la terminal partida',
    'settings_ui.label.ui.split_pane': 'Contenido del pane derecho',
    'settings_ui.label.otros.auto_update': 'Actualizaciones automáticas',
    'settings_ui.label.otros.update_channel': 'Canal de actualización',
    'settings_ui.label.otros.notify_on_done': 'Notificar al terminar',

    'settings_ui.choice.ui.background.tema': 'tema',
    'settings_ui.choice.ui.background.negro': 'negro',
    'settings_ui.choice.ui.background.grafito': 'grafito',
    'settings_ui.choice.ui.background.azul': 'azul',
    'settings_ui.choice.ui.background.verde': 'verde',
    'settings_ui.choice.ui.background.violeta': 'violeta',
    'settings_ui.choice.ui.background.personalizado': 'personalizado',
    # layout lanzador
}
