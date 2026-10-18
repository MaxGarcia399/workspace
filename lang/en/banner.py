"""WORKSPACE · lang/en/banner — the agent banner TEMPLATE (brand/agent-banner,
agent-dashboard, agent-statusline). EN translation of lang/es/banner.py. Only
STATIC chrome is translated here; agent identity (display/tagline/emblem/palette)
comes from agent.json/BOOT and is never in this catalog."""

STRINGS = {
    # ── dashboard (agent-dashboard.py): session picker/greeter ───────────────
    "banner.dash.sessions_count": "{n} session(s) · each one remembers its own, on any engine · pick one or create a new one",
    "banner.dash.resume_q": "Where do we pick up?",
    "banner.dash.hint": "↑↓ to choose · Enter to open",
    "banner.dash.sub_continue": "continue",
    "banner.dash.sub_new": "new",
    "banner.dash.new_label": "+ New session…",
    "banner.dash.new_sub": "create a named session",
    "banner.dash.number_enter": "Number and Enter: ",
    "banner.dash.no_sessions": "(no sessions)",
    "banner.dash.name_prompt": "Session name: ",
    "banner.dash.loading": "loading…",

    # ── statusline (agent-statusline.py): bar labels and text ────────────────
    "banner.status.context": "context",
    "banner.status.session_use": "session use",
    "banner.status.weekly_use": "weekly use",
    "banner.status.resets_in": "resets in ",
    "banner.status.no_data": "— data after 1st message",
    "banner.status.active": "active ",
    "banner.status.now": "now",
}
