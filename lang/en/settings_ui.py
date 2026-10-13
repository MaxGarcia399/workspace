"""WORKSPACE · lang/en/settings_ui — setting labels and values as the hub
paints them (PERSONALIZATION/CONFIGS pins — settings.pin_label and
settings.pin_value_display). EN translation of lang/es/settings_ui.py; brand
ids (themes, engines) stay verbatim."""

STRINGS = {
    'settings_ui.label.latido.mode': 'Heartbeat mode',
    'settings_ui.label.latido.intensity': 'Heartbeat intensity',
    'settings_ui.label.hooks.skill_review': 'Skill review (SessionEnd)',
    'settings_ui.label.hooks.transcript_backup': 'Transcript backup (Y2b)',
    'settings_ui.label.hooks.memory_flush': 'Memory flush (PreCompact, N2)',
    'settings_ui.label.hooks.security_guidance': 'Security guidance (PostToolUse, N15)',
    'settings_ui.label.hooks.telemetry': 'Live telemetry (Pre/PostToolUse, N-telem)',
    'settings_ui.label.modelos.default_engine': 'Default engine',
    'settings_ui.label.cerebro.dreaming_auto': 'Automatic dreaming',
    'settings_ui.label.agentes.default_agent': 'Default agent',
    'settings_ui.label.agentes.auto_mode': 'Auto-mode in interactive sessions',
    'settings_ui.label.ui.anim': 'Animations',
    'settings_ui.label.ui.autostart': 'Open when the terminal opens',
    'settings_ui.label.ui.lang': 'Language',
    'settings_ui.label.ui.background': 'Independent background',
    'settings_ui.label.ui.brightness': 'Brightness',
    'settings_ui.label.ui.redlight': 'Red light (night mode)',
    'settings_ui.label.ui.titles': 'Big titles',
    'settings_ui.label.ui.theme': 'Hub theme',
    'settings_ui.label.ui.web_theme': 'Dev panel theme (web)',
    'settings_ui.label.ui.split': 'Split terminal',
    'settings_ui.label.ui.split_backend': 'Split terminal backend',
    'settings_ui.label.ui.split_pane': 'Right pane content',
    'settings_ui.label.otros.auto_update': 'Automatic updates',
    'settings_ui.label.otros.update_channel': 'Update channel',
    'settings_ui.label.otros.notify_on_done': 'Notify when done',

    'settings_ui.choice.ui.background.tema': 'theme',
    'settings_ui.choice.ui.background.negro': 'black',
    'settings_ui.choice.ui.background.grafito': 'graphite',
    'settings_ui.choice.ui.background.azul': 'blue',
    'settings_ui.choice.ui.background.verde': 'green',
    'settings_ui.choice.ui.background.violeta': 'violet',
    'settings_ui.choice.ui.background.personalizado': 'custom',
    # layout lanzador
}
