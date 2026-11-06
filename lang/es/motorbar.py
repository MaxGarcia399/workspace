"""WORKSPACE · lang/es/motorbar — barras y permisos de los motores wrapper
(Codex · Antigravity · Copilot · Cursor): pie opt-in de Codex, statusLine de Antigravity y las
líneas de autonomía. Consumido vía workspace_status.t (catálogo → inline)."""
STRINGS = {
    'motorbar.active': 'activa {d}',
    'motorbar.agy_no_quota': 'Cuota: sin datos del proveedor',
    'motorbar.codex_waiting': 'Cuotas: esperando datos de Codex',
    'motorbar.context': 'contexto {pct}%',
    'motorbar.context_pending': 'contexto tras el 1er mensaje',
    'motorbar.copilot.ai_used': '{n} créditos IA',
    'motorbar.copilot.premium': '{n} solicitudes premium',
    'motorbar.copilot.allow_all': 'todo permitido',
    'motorbar.copilot.ask': 'ask — pregunta antes de crear o editar, también en el cerebro',
    'motorbar.copilot.brain': 'brain — escribe en su cerebro sin preguntar (`write(<cerebro>/**)` por corrida); fuera del cerebro, la terminal y su config de Copilot (.github/, .mcp.json, .claude/settings…) piden permiso o se niegan',
    'motorbar.copilot.socio': 'tus permisos de escritura de Copilot ganan (Workspace no agrega los suyos)',
    'motorbar.copilot.largo': 'la ruta del cerebro es tan larga que las reglas no caben en la línea de comandos de Windows: pregunta antes de escribir, también en el cerebro',
    'motorbar.copilot.ruta': 'la ruta del cerebro lleva caracteres que no caben en la regla de Copilot (paréntesis; en Windows con el lanzador .cmd, también " % ^ ! < > | &): pregunta antes de escribir, también en el cerebro',
    'motorbar.cursor.autorun': 'auto-run',
    'motorbar.data_ago': 'datos {d}',
    'motorbar.dirty': 'cambios',
    'motorbar.footer_nodata': 'Workspace · cuota sin datos',
    'motorbar.quota_none': 'cuota sin datos',
    'motorbar.read_ago': 'lectura hace {d}',
    'motorbar.reset_done': 'ventana reiniciada',
    'motorbar.reset_unconfirmed': 'reinicio pendiente de confirmar',
    'motorbar.resets_in': 'reinicia {d}',
    'motorbar.resets_word': 'reinicia ',
    'motorbar.used': '{pct}% usado',
    'motorbar.weekly': 'Semanal',
    'motorbar.week': 'semana',
    'motorbar.mode.accept_edits': 'edita sin preguntar',
    'motorbar.mode.default': 'pide permiso al editar',
    'motorbar.mode.plan': 'modo plan',
    'motorbar.plan.autonomy': 'autonomía   ',
    'motorbar.plan.autonomy_short': 'autonomía',
    'motorbar.plan.footer': 'pie tmux    ',
    'motorbar.plan.footer_optin': 'apagado (opt-in WORKSPACE_CODEX_LIVE_BAR=1; si corre, apaga la '
                                  'barra nativa: una sola barra)',
    'motorbar.codex.ask': 'ask — pregunta antes de editar en el cerebro o correr comandos (sandbox '
                          'de solo lectura)',
    'motorbar.agy.ask': 'ask — pregunta antes de crear o editar, también en el cerebro; terminal y '
                        'archivos fuera piden permiso',
    'motorbar.codex.brain': 'brain — edita en el cerebro sin preguntar; fuera del cerebro, la red '
                            'y lo sensible piden permiso',
    'motorbar.codex.full': 'full — edita en el cerebro y corre comandos sin preguntar (dentro del '
                           'sandbox: fuera del cerebro y la red, bloqueados)',
    'motorbar.agy.brain': 'brain — edita en el cerebro sin preguntar; terminal y archivos fuera '
                          'piden permiso',
    'motorbar.agy.full': 'full — edita en el cerebro y corre comandos sin preguntar (proyecto de '
                         'agy del agente); fuera del cerebro pide permiso',
    'motorbar.agy.access_failed': 'no pude registrar el acceso del cerebro en Antigravity (pedirá '
                                  'permiso para editarlo).',
    'motorbar.agy.full_unavailable': 'no pude preparar la autonomía completa en Antigravity: los '
                                     'comandos pedirán permiso.',
    'motorbar.agy.sin_deny': 'Antigravity preguntará antes de editar tu cerebro: no pude negarle la config de los motores, git y Obsidian (tu propio --settings, o el settings.json de agy es un enlace o no se puede leer).',
    # la herramienta de memoria y la config de proyecto del socio (memoria_mcp)
    'motorbar.memoria_mcp.cursor_sin_deny': 'WORKSPACE: sin {rel}, Cursor no tiene negada la config de los motores, git y Obsidian de tu cerebro: revisa ese archivo.',
    'motorbar.memoria_mcp.enlace': 'WORKSPACE: {rel} de tu cerebro (o una carpeta de su ruta) es un enlace: no lo toco y la memoria pedirá permiso.',
    'motorbar.memoria_mcp.ilegible': 'WORKSPACE: {rel} de tu cerebro no es un JSON que entienda: no lo toco y la memoria pedirá permiso hasta que lo arregles.',
    'motorbar.memoria_mcp.ocupado': 'WORKSPACE: donde va {rel} en tu cerebro hay algo que no es un archivo: no lo toco y la memoria pedirá permiso.',
    'motorbar.memoria_mcp.escritura': 'WORKSPACE: no pude escribir {rel} en tu cerebro: la memoria pedirá permiso.',
    'motorbar.memoria_mcp.restaurada': 'WORKSPACE: {rel} de tu cerebro: lo de Workspace (`workspace-memoria`) estaba cambiado; lo restauré y lo tuyo queda igual (respaldo en {respaldo}).',
    'motorbar.agy.commands_free': 'comandos sin preguntar',
    'motorbar.agy.acct_full': 'API key o cuenta empresarial: integración completa',
    'motorbar.agy.acct_exp': 'inicio de sesión con Google: experimental (Google no soporta '
                             'envolver agy con planes personales: {u})',
    'motorbar.agy.tokens_in_bar': 'en la barra de Antigravity',
    'motorbar.hermes.created': 'creé su perfil «{p}» (con tu modelo, sin copiar tus llaves; tu '
                               'Hermes personal no cambia)',
    'motorbar.hermes.pending': 'el perfil «{p}» de Hermes aún no existe: se crea sin tus llaves al '
                               'abrir el agente; conecta el proveedor en Motores › cuenta y proveedor',
    'motorbar.hermes.no_provider': 'el perfil «{p}» de Hermes no tiene proveedor con sesión '
                                   '(Workspace no copia las llaves de tu Hermes personal)',
    'motorbar.hermes.gate_hint': '  El perfil de Workspace en Hermes tiene su propio proveedor '
                                 '(Workspace no copia tus llaves). Sin él, Hermes abre su propio '
                                 'asistente en vez de tu agente: conéctalo en Motores › Hermes › '
                                 'cuenta y proveedor (el proveedor y el modelo).',
    'motorbar.hermes.skills': 'conecté las skills de tu cerebro; las que Hermes aprenda se '
                              'guardan en él (skills/aprendidas/), no en su perfil compartido',
    'motorbar.hermes.skills_create': 'las skills que Hermes aprenda ahora se guardan en tu '
                                     'cerebro (skills/aprendidas/), donde las ven tus otros '
                                     'motores',
    'motorbar.hermes.skills_foreign': 'el perfil tiene una sección skills: que no edito: las '
                                      'skills de tu cerebro no se conectan',
    'motorbar.hermes.discord_off': 'apagué en Discord {tools} de Hermes (un bot conectado al '
                                   'perfil compartido podía leer las conversaciones de todos '
                                   'tus agentes)',
    'motorbar.hermes.discord_still': 'no pude apagar {tools} en Discord (no guarda nada: la '
                                     'memoria de Hermes está apagada)',
    'motorbar.hermes.discord_leak': 'no pude apagar {tool} en Discord: un bot de Discord '
                                    'conectado al perfil «{p}» podría leer las conversaciones '
                                    'de tus otros agentes; córrelo a mano: hermes --profile {p} '
                                    'tools disable --platform {plat} {tool}',
    'motorbar.hermes.platforms_off': 'apagué {tools} de Hermes en Discord, Telegram, Slack, '
                                     'WhatsApp y sus demás plataformas (un bot conectado al '
                                     'perfil compartido podía leer las conversaciones de todos '
                                     'tus agentes)',
    'motorbar.hermes.platforms_leak': 'no pude apagar {tool} en las plataformas de mensajería de '
                                      'Hermes (la sección agent: del perfil tiene una forma que '
                                      'no edito): un bot de Telegram, Slack u otra conectado al '
                                      'perfil «{p}» podría leer las conversaciones de tus otros '
                                      'agentes; agrega {tool} y memory a agent.disabled_toolsets '
                                      'en {cfg}',
    'motorbar.hermes.plan_skills': '  skills      : las de fábrica del perfil + las de tu cerebro '
                                   '(skills/); las que Hermes crea van a skills/aprendidas/ de tu '
                                   'cerebro',
    'motorbar.openclaw.memory_failed': 'no pude prender la carga de la memoria larga '
                                       '(STATE/MEMORY.md): OpenClaw abre sin ella',
    'motorbar.openclaw.memory_restored': 'volví a prender la carga de STATE/MEMORY.md (hook '
                                         'bootstrap-extra-files): es la memoria larga de tu '
                                         'cerebro',
    'motorbar.openclaw.memory_added': 'agregué STATE/MEMORY.md a tus rutas del hook '
                                      'bootstrap-extra-files (las tuyas se conservan)',
    'motorbar.openclaw.no_agent': 'OpenClaw sin ventana necesita saber de qué agente es el '
                                  'turno: jamás usa su agente «main» de fábrica, que contesta '
                                  'con otra identidad',
    'motorbar.openclaw.plan_memory': '  memoria     : STATE/MEMORY.md de tu cerebro en cada turno '
                                     '(hook oficial bootstrap-extra-files, con el gateway); lo que '
                                     'su memoria propia escribiría, apagado; su búsqueda de '
                                     'memoria sigue encendida (solo en sus propios archivos)',
}
