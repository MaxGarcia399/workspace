"""WORKSPACE · lang/en/sesiones — English for lang/es/sesiones.py (the single
tab list and archiving, sessions v2)."""

STRINGS = {
    "sesiones.auto.uno": "archived 1 tab unused for {dias} days · undo: "
                         "`workspace sesiones desarchivar --ultimas`",
    "sesiones.auto.varias": "archived {n} tabs unused for {dias} days · undo: "
                            "`workspace sesiones desarchivar --ultimas`",
    "sesiones.auto.uno_menu": "archived 1 tab unused for {dias} days · u to undo",
    "sesiones.auto.varias_menu": "archived {n} tabs unused for {dias} days · u to undo",

    "sesiones.menu.fila": "Archived ({n})",
    "sesiones.menu.fila_sub": "the ones you took off the menu",
    "sesiones.menu.titulo": "ARCHIVED",
    "sesiones.menu.sub": "archived {fecha}",
    "sesiones.menu.volver": "← Back",
    "sesiones.menu.volver_sub": "to your tabs",
    "sesiones.menu.archivada": "Archived “{name}” · u to undo",
    "sesiones.menu.no_pude": "Couldn't archive “{name}”",
    "sesiones.menu.recuperada": "Restored “{name}”",
    "sesiones.menu.recuperadas": "Restored {n} tabs",
    "sesiones.menu.nada": "Nothing to undo",
    "sesiones.hint.archive": "archive",
    "sesiones.hint.undo": "undo",
    "sesiones.hint.restore": "restore and open",
    "sesiones.hint.back": "back",

    "sesiones.cli.ninguna": "(no tabs)",
    "sesiones.cli.ninguna_arch": "(none archived)",
    "sesiones.cli.cuantas_arch": "{n} archived: workspace sesiones lista --archivadas",
    "sesiones.cli.huerfanas": "{n} only on this machine, with no memory in the brain "
                              "(not shown): {nombres}",
    "sesiones.cli.huerfanas_hint": "restore one with: workspace sesiones desarchivar <name>",
    "sesiones.cli.archivada": "✓ archived “{name}” ({agente}) · undo: "
                              "workspace sesiones desarchivar --ultimas",
    "sesiones.cli.ya_archivada": "“{name}” was already archived",
    "sesiones.cli.desarchivada": "✓ “{name}” is back in your tabs ({agente})",
    "sesiones.cli.ya_activa": "“{name}” was already in your tabs",
    "sesiones.cli.recuperadas": "✓ restored: {nombres}",
    "sesiones.cli.nada": "nothing to undo",
    "sesiones.cli.no_existe": "I can't find the tab “{name}”",
    "sesiones.cli.varios": "“{name}” exists in several agents ({agentes}): pick one with --agente",
    "sesiones.cli.no_pude": "couldn't change “{name}” (is the file not UTF-8, or locked?)",
    "sesiones.cli.sin_agente": "I don't know the agent “{agente}”",
    "sesiones.cli.sin_cerebro": "I can't find any brain: open an agent or use --agente",
    "sesiones.cli.falta_nombre": "the tab name is missing",
    "sesiones.cli.conv.uso": "usage: workspace sesiones conversacion on|off|ver [--agente X]",
    "sesiones.cli.conv.ver_si": "{agente}: the Claude Code conversation travels (the brain decided)",
    "sesiones.cli.conv.ver_no": "{agente}: the Claude Code conversation stays on each machine (the brain decided)",
    "sesiones.cli.conv.ver_maquina": "{agente}: the brain hasn't decided; this machine's setting applies (sesiones.llevar_conversacion = {valor})",
    "sesiones.cli.conv.cual": "say which agent with --agente (or --cerebro)",
    "sesiones.cli.conv.no_pude": "couldn't save the permission in {agente}'s brain: {error}",
    "sesiones.cli.conv.on": "in {agente}'s brain the Claude Code conversation travels (everyone who uses this brain can see it)",
    "sesiones.cli.conv.on_hint": "with Obsidian Sync, turn on «Sync all other types» on each device; for privacy, use a separate brain",
    "sesiones.cli.conv.off": "in {agente}'s brain the Claude Code conversation stays on each machine",
}
