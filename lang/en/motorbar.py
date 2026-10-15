"""WORKSPACE · lang/en/motorbar — wrapper-engine bars and permissions (Codex ·
Antigravity). Same keys as lang/es/motorbar.py."""
STRINGS = {
    'motorbar.active': 'up {d}',
    'motorbar.agy_no_quota': 'Quota: no data from the provider',
    'motorbar.codex_waiting': 'Quotas: waiting for Codex data',
    'motorbar.context': 'context {pct}%',
    'motorbar.data_ago': 'data {d}',
    'motorbar.dirty': 'changes',
    'motorbar.footer_nodata': 'Workspace · no quota data',
    'motorbar.quota_none': 'no quota data',
    'motorbar.read_ago': 'read {d} ago',
    'motorbar.reset_done': 'window reset',
    'motorbar.reset_unconfirmed': 'reset not yet confirmed',
    'motorbar.resets_in': 'resets in {d}',
    'motorbar.resets_word': 'resets in ',
    'motorbar.used': '{pct}% used',
    'motorbar.weekly': 'Weekly',
    'motorbar.week': 'week',
    'motorbar.mode.accept_edits': 'edits without asking',
    'motorbar.mode.default': 'asks before editing',
    'motorbar.mode.plan': 'plan mode',
    'motorbar.plan.autonomy': 'autonomy    ',
    'motorbar.plan.autonomy_short': 'autonomy',
    'motorbar.plan.footer': 'tmux footer ',
    'motorbar.plan.footer_optin': 'off (opt-in WORKSPACE_CODEX_LIVE_BAR=1; when it runs it hides the '
                                  'native bar: one bar only)',
    'motorbar.codex.ask': 'ask — asks before editing in the brain or running commands (read-only '
                          'sandbox)',
    'motorbar.agy.ask': 'ask — asks before creating or editing, also in the brain; terminal and '
                        'outside files ask first',
    'motorbar.codex.brain': 'brain — edits in the brain without asking; outside the brain, network '
                            'and sensitive steps ask first',
    'motorbar.codex.full': 'full — edits in the brain and runs commands without asking (inside the '
                           'sandbox: outside the brain and network stay blocked)',
    'motorbar.agy.brain': 'brain — edits in the brain without asking; terminal and outside files '
                          'ask first',
    'motorbar.agy.full': "full — edits in the brain and runs commands without asking (the agent's "
                         'agy project); outside the brain it asks',
    'motorbar.agy.access_failed': "couldn't register the brain's access in Antigravity (it will ask "
                                  'before editing it).',
    'motorbar.agy.full_unavailable': "couldn't set up full autonomy in Antigravity: commands will "
                                     'ask for permission.',
    'motorbar.agy.commands_free': 'commands without asking',
    'motorbar.agy.tokens_in_bar': "in Antigravity's bar",
}
