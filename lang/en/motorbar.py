"""WORKSPACE · lang/en/motorbar — wrapper-engine bars and permissions (Codex ·
Antigravity · Copilot · Cursor). Same keys as lang/es/motorbar.py."""
STRINGS = {
    'motorbar.active': 'up {d}',
    'motorbar.agy_no_quota': 'Quota: no data from the provider',
    'motorbar.codex_waiting': 'Quotas: waiting for Codex data',
    'motorbar.context': 'context {pct}%',
    'motorbar.context_pending': 'context after the first message',
    'motorbar.copilot.ai_used': '{n} AI credits',
    'motorbar.copilot.premium': '{n} premium requests',
    'motorbar.copilot.allow_all': 'all allowed',
    'motorbar.copilot.ask': 'ask — asks before creating or editing, also in the brain',
    'motorbar.copilot.brain': 'brain — writes in its brain without asking (`write(<brain>/**)` per run); outside the brain, the terminal and its Copilot config (.github/, .mcp.json, .claude/settings…) ask or are denied',
    'motorbar.copilot.socio': 'your Copilot write permissions win (Workspace adds none of its own)',
    'motorbar.copilot.largo': "the brain path is so long that the rules don't fit in the Windows command line: it asks before writing, also in the brain",
    'motorbar.copilot.ruta': 'the brain path has characters that do not fit in a Copilot rule (parentheses; on Windows with the .cmd launcher, also " % ^ ! < > | &): it asks before writing, also in the brain',
    'motorbar.cursor.autorun': 'auto-run',
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
    'motorbar.agy.sin_deny': "Antigravity will ask before editing your brain: I couldn't deny it the engines', git's and Obsidian's config (your own --settings, or agy's settings.json is a link or unreadable).",
    # la herramienta de memoria y la config de proyecto del socio (memoria_mcp)
    'motorbar.memoria_mcp.cursor_sin_deny': "WORKSPACE: without {rel}, Cursor isn't denied the engines', git's and Obsidian's config in your brain: check that file.",
    'motorbar.memoria_mcp.enlace': 'WORKSPACE: {rel} in your brain (or a folder on its path) is a link: I leave it alone and memory will ask for permission.',
    'motorbar.memoria_mcp.ilegible': "WORKSPACE: {rel} in your brain isn't JSON I can read: I leave it alone and memory will ask for permission until you fix it.",
    'motorbar.memoria_mcp.ocupado': "WORKSPACE: where {rel} goes in your brain there's something that isn't a file: I leave it alone and memory will ask for permission.",
    'motorbar.memoria_mcp.escritura': "WORKSPACE: couldn't write {rel} in your brain: memory will ask for permission.",
    'motorbar.memoria_mcp.restaurada': "WORKSPACE: {rel} in your brain: Workspace's entry (`workspace-memoria`) had been changed; I restored it and yours stays as is (backup in {respaldo}).",
    'motorbar.agy.commands_free': 'commands without asking',
    'motorbar.agy.acct_full': 'API key or business account: full integration',
    'motorbar.agy.acct_exp': "Google sign-in: experimental (Google doesn't support wrapping "
                             'agy on consumer plans: {u})',
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
    'motorbar.hermes.skills': "connected your brain's skills; the ones Hermes learns are saved "
                              "in it (skills/aprendidas/), not in its shared profile",
    'motorbar.hermes.skills_create': "the skills Hermes learns are now saved in your brain "
                                     "(skills/aprendidas/), where your other engines see them",
    'motorbar.hermes.skills_foreign': "the profile has a skills: section I don't edit: your "
                                      "brain's skills aren't connected",
    'motorbar.hermes.discord_off': "turned off Hermes' {tools} in Discord (a bot connected to "
                                   "the shared profile could read all your agents' "
                                   "conversations)",
    'motorbar.hermes.discord_still': "couldn't turn off {tools} in Discord (it saves nothing: "
                                     "Hermes' memory is off)",
    'motorbar.hermes.discord_leak': "couldn't turn off {tool} in Discord: a Discord bot "
                                    "connected to the «{p}» profile could read your other "
                                    "agents' conversations; run it by hand: hermes --profile "
                                    "{p} tools disable --platform {plat} {tool}",
    'motorbar.hermes.platforms_off': "turned off Hermes' {tools} on Discord, Telegram, Slack, "
                                     "WhatsApp and its other platforms (a bot connected to the "
                                     "shared profile could read all your agents' conversations)",
    'motorbar.hermes.platforms_leak': "couldn't turn off {tool} on Hermes' messaging platforms "
                                      "(the profile's agent: section has a shape I don't edit): a "
                                      "Telegram, Slack or other bot connected to the «{p}» "
                                      "profile could read your other agents' conversations; add "
                                      "{tool} and memory to agent.disabled_toolsets in {cfg}",
    'motorbar.hermes.plan_skills': "  skills      : the profile's built-in ones + your brain's "
                                   "(skills/); the ones Hermes creates go to your brain's "
                                   "skills/aprendidas/",
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
                                     "what its own memory would write, off; its memory search "
                                     "stays on (only over its own files)",
}
