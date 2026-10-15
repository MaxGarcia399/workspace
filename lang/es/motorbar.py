"""WORKSPACE · lang/es/motorbar — barras y permisos de los motores wrapper
(Codex · Antigravity): pie opt-in de Codex, statusLine de Antigravity y las
líneas de autonomía. Consumido vía workspace_status.t (catálogo → inline)."""
STRINGS = {
    'motorbar.active': 'activa {d}',
    'motorbar.agy_no_quota': 'Cuota: sin datos del proveedor',
    'motorbar.codex_waiting': 'Cuotas: esperando datos de Codex',
    'motorbar.context': 'contexto {pct}%',
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
    'motorbar.agy.commands_free': 'comandos sin preguntar',
    'motorbar.agy.tokens_in_bar': 'en la barra de Antigravity',
}
