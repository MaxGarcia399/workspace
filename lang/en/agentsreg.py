"""Agent register/relocate errors (agentsreg.py) — English."""

STRINGS = {
    "agentsreg.err.bad_name": "invalid name: {name} (use lowercase, digits, - or _)",
    "agentsreg.err.no_brain_dir": "the brain folder doesn't exist: {path}",
    "agentsreg.err.not_registered": "no agent '{name}' is registered (for a new one use add)",
    "agentsreg.err.no_dir": "the folder doesn't exist: {path}",
    "agentsreg.err.no_read": "no read permission: {path}",
    "agentsreg.err.other_agent": "{path} declares agent '{other}', not '{name}' (use --force if intended)",
    "agentsreg.err.not_a_brain": "{path} has no .workspace/agent.json and isn't named like the declared brain ({target}) — use --force if intended",
}
