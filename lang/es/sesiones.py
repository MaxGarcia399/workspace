"""WORKSPACE · lang/es/sesiones — FUENTE ES de la lista única de pestañas y
archivar (sesiones v2): el aviso del archivo automático, las teclas y filas
del menú de pestañas de cada agente (agent_ui.menu_sesiones) y el comando
`workspace sesiones` (sesiones.py). Traducción en lang/en/sesiones.py."""

STRINGS = {
    # aviso de una línea del archivo automático (sessions_registry.aviso_auto)
    "sesiones.auto.uno": "archivé 1 pestaña sin usar en {dias} días · deshacer: "
                         "`workspace sesiones desarchivar --ultimas`",
    "sesiones.auto.varias": "archivé {n} pestañas sin usar en {dias} días · deshacer: "
                            "`workspace sesiones desarchivar --ultimas`",
    # el mismo aviso DENTRO del menú de pestañas: ahí se deshace con la tecla
    "sesiones.auto.uno_menu": "archivé 1 pestaña sin usar en {dias} días · u para deshacer",
    "sesiones.auto.varias_menu": "archivé {n} pestañas sin usar en {dias} días · u para deshacer",

    # menú de pestañas del agente (agent_ui.menu_sesiones)
    "sesiones.menu.fila": "Archivadas ({n})",
    "sesiones.menu.fila_sub": "las que quitaste del menú",
    "sesiones.menu.titulo": "ARCHIVADAS",
    "sesiones.menu.sub": "archivada {fecha}",
    "sesiones.menu.volver": "← Volver",
    "sesiones.menu.volver_sub": "a tus pestañas",
    "sesiones.menu.archivada": "Archivada «{name}» · u para deshacer",
    "sesiones.menu.no_pude": "No pude archivar «{name}»",
    "sesiones.menu.recuperada": "Recuperé «{name}»",
    "sesiones.menu.recuperadas": "Recuperé {n} pestañas",
    "sesiones.menu.nada": "Nada que deshacer",
    "sesiones.hint.archive": "archiva",
    "sesiones.hint.undo": "deshace",
    "sesiones.hint.restore": "recupera y abre",
    "sesiones.hint.back": "vuelve",

    # `workspace sesiones` (sesiones.py)
    "sesiones.cli.ninguna": "(sin pestañas)",
    "sesiones.cli.ninguna_arch": "(ninguna archivada)",
    "sesiones.cli.cuantas_arch": "{n} archivada(s): workspace sesiones lista --archivadas",
    "sesiones.cli.huerfanas": "{n} solo en esta máquina, sin memoria en el cerebro "
                              "(no se muestran): {nombres}",
    "sesiones.cli.huerfanas_hint": "recupera una con: workspace sesiones desarchivar <nombre>",
    "sesiones.cli.archivada": "✓ archivada «{name}» ({agente}) · deshacer: "
                              "workspace sesiones desarchivar --ultimas",
    "sesiones.cli.ya_archivada": "«{name}» ya estaba archivada",
    "sesiones.cli.desarchivada": "✓ «{name}» volvió a tus pestañas ({agente})",
    "sesiones.cli.ya_activa": "«{name}» ya estaba en tus pestañas",
    "sesiones.cli.recuperadas": "✓ recuperé: {nombres}",
    "sesiones.cli.nada": "nada que deshacer",
    "sesiones.cli.no_existe": "no encuentro la pestaña «{name}»",
    "sesiones.cli.varios": "«{name}» existe en varios agentes ({agentes}): di cuál con --agente",
    "sesiones.cli.no_pude": "no pude cambiar «{name}» (¿el archivo no es UTF-8 o está bloqueado?)",
    "sesiones.cli.sin_agente": "no conozco al agente «{agente}»",
    "sesiones.cli.sin_cerebro": "no encuentro ningún cerebro: abre un agente o usa --agente",
    "sesiones.cli.falta_nombre": "falta el nombre de la pestaña",
    "sesiones.cli.conv.uso": "usa: workspace sesiones conversacion on|off|ver [--agente X]",
    "sesiones.cli.conv.ver_si": "{agente}: la conversación de Claude Code viaja (lo decidió el cerebro)",
    "sesiones.cli.conv.ver_no": "{agente}: la conversación de Claude Code se queda en cada máquina (lo decidió el cerebro)",
    "sesiones.cli.conv.ver_maquina": "{agente}: el cerebro no ha decidido; manda el ajuste de esta máquina (sesiones.llevar_conversacion = {valor})",
    "sesiones.cli.conv.cual": "di de qué agente con --agente (o --cerebro)",
    "sesiones.cli.conv.no_pude": "no pude guardar el permiso en el cerebro de {agente}: {error}",
    "sesiones.cli.conv.on": "en el cerebro de {agente} la conversación de Claude Code viaja (lo ven todos los que usan este cerebro)",
    "sesiones.cli.conv.on_hint": "con Obsidian Sync, prende «Sync all other types» en cada dispositivo; para privacidad, usa un cerebro aparte",
    "sesiones.cli.conv.off": "en el cerebro de {agente} la conversación de Claude Code se queda en cada máquina",
}
