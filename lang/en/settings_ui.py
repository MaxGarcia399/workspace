"""WORKSPACE · lang/en/settings_ui — setting labels and values as the hub
paints them (PERSONALIZATION/CONFIGS pins — settings.pin_label and
settings.pin_value_display). EN translation of lang/es/settings_ui.py; brand
ids (themes, engines) stay verbatim."""

STRINGS = {
    'settings_ui.label.latido.mode': 'Heartbeat mode',
    'settings_ui.label.latido.intensity': 'Heartbeat intensity',
    'settings_ui.label.hooks.skill_review': 'Skill review (SessionEnd)',
    'settings_ui.label.hooks.transcript_backup': 'Transcript backup (Y2b)',
    'settings_ui.label.hooks.metricas': 'Performance metrics (local log)',
    'settings_ui.label.hooks.memory_flush': 'Memory flush (PreCompact, N2)',
    'settings_ui.label.hooks.security_guidance': 'Security guidance (PostToolUse, N15)',
    'settings_ui.label.hooks.telemetry': 'Live telemetry (Pre/PostToolUse, N-telem)',
    'settings_ui.label.modelos.default_engine': 'Default engine',
    'settings_ui.label.agentes.default_agent': 'Default agent',
    'settings_ui.label.agentes.auto_mode': 'Auto-mode in interactive sessions',
    'settings_ui.label.ui.anim': 'Animations',
    'settings_ui.label.ui.autostart': 'Open when the terminal opens',
    'settings_ui.label.ui.lang': 'Language',
    'settings_ui.label.ui.background': 'Independent background',
    'settings_ui.label.ui.brightness': 'Brightness',
    'settings_ui.label.ui.redlight': 'Red light (night mode)',
    'settings_ui.label.ui.un_color': 'Single color',
    'settings_ui.help.ui.un_color': ('Titles and accents in a single color: the theme\'s main one. '
                                     'Text and colors that signal something stay. '
                                     'Works with every theme, herdr\'s included.'),
    'settings_ui.label.ui.titles': 'Big titles',
    'settings_ui.label.ui.theme': 'Hub theme',
    'settings_ui.label.ui.tema_herdr': 'Follow herdr',
    'settings_ui.help.ui.tema_herdr': ('Inside herdr: yes = Workspace uses herdr\'s theme and paints no background; '
                                       'no = it keeps its own theme there too. Outside herdr nothing changes.'),
    'settings_ui.label.ui.web_theme': 'Dev panel theme (web)',
    'settings_ui.label.ui.split': 'Split terminal',
    'settings_ui.label.ui.split_backend': 'Split terminal backend',
    'settings_ui.label.ui.split_pane': 'Right pane content',
    'settings_ui.label.otros.auto_update': 'Automatic updates',
    'settings_ui.label.otros.update_channel': 'Update channel',
    'settings_ui.label.otros.notify_on_done': 'Notify when done',
    'settings_ui.label.sesiones.archivar_dias': 'Archive unused tabs (days)',
    'settings_ui.label.sesiones.llevar_conversacion': 'Carry the conversation to your other machines',
    'settings_ui.label.sesiones.conversacion_max_mb': 'Size cap for the travelling conversation (MB)',
    'settings_ui.help.sesiones.llevar_conversacion':
        "Each brain decides whether its Claude Code conversation travels with it, for every machine and person who uses it: `workspace sesiones conversacion on|off --agente X`. This setting is this machine's choice for brains that haven't decided. claude-code = when you close a tab, its conversation is saved compressed in the brain (motores/claude-code/conversaciones/<socio>/) and your other machine resumes it with --resume; opening only brings back yours. In a shared brain, everyone who uses it can see those conversations: for privacy, use a separate brain. It isn't uploaded if it's over the cap or contains something that looks like a key, and it never goes to the git mirror. With Obsidian Sync, turn on «Sync all other types» on each device. off (default) = it stays on each machine; the tab still travels with its memory.",

    'settings_ui.choice.ui.background.tema': 'theme',
    'settings_ui.choice.ui.tema_herdr.herdr': 'yes',
    'settings_ui.choice.ui.tema_herdr.workspace': 'no',
    'settings_ui.choice.ui.background.negro': 'black',
    'settings_ui.choice.ui.background.grafito': 'graphite',
    'settings_ui.choice.ui.background.azul': 'blue',
    'settings_ui.choice.ui.background.verde': 'green',
    'settings_ui.choice.ui.background.violeta': 'violet',
    'settings_ui.choice.ui.background.personalizado': 'custom',
    # layout lanzador
}
