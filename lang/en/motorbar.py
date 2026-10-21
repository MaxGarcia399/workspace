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
    'motorbar.hermes.created': "created its «{p}» profile (with your model, without copying your "
                               "keys; your personal Hermes doesn't change)",
    'motorbar.hermes.pending': "Hermes' «{p}» profile doesn't exist yet: it's created without your "
                               "keys when you open the agent; connect the provider in Engines › "
                               "account and provider",
    'motorbar.hermes.no_provider': "Hermes' «{p}» profile has no provider signed in (Workspace "
                                   "doesn't copy your personal Hermes keys)",
    'motorbar.hermes.gate_hint': "  Workspace's Hermes profile has its own provider (Workspace "
                                 "doesn't copy your keys). Without one, Hermes opens its own "
                                 "wizard instead of your agent: connect it in Engines › Hermes › "
                                 "account and provider (provider and model).",
    'motorbar.hermes.skills': "connected your brain's skills; Hermes no longer creates skills in "
                              "its shared profile",
    'motorbar.hermes.skills_foreign': "the profile has a skills: section I don't edit: your "
                                      "brain's skills aren't connected",
    'motorbar.hermes.plan_skills': "  skills      : the profile's built-in ones + your brain's "
                                   "(skills/); Hermes doesn't create skills in the shared profile",
    'motorbar.openclaw.memory_failed': "couldn't turn on loading the long-term memory "
                                       "(STATE/MEMORY.md): OpenClaw opens without it",
    'motorbar.openclaw.memory_restored': "turned loading STATE/MEMORY.md back on "
                                         "(bootstrap-extra-files hook): it's your brain's "
                                         "long-term memory",
    'motorbar.openclaw.memory_added': "added STATE/MEMORY.md to your bootstrap-extra-files hook "
                                      "paths (yours are kept)",
    'motorbar.openclaw.no_agent': "a windowless OpenClaw turn needs to know which agent it "
                                  "belongs to: it never uses OpenClaw's built-in «main» agent, "
                                  "which answers with another identity",
    'motorbar.openclaw.plan_memory': "  memory      : your brain's STATE/MEMORY.md on every turn "
                                     "(official bootstrap-extra-files hook, with the gateway); "
                                     "its semantic search, off",
}
