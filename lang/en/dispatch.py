"""EN catalog — opening an agent (dispatch.py): the assigned engine isn't
available and another one is offered."""

STRINGS = {
    "dispatch.engine.no_adapter": "it has no adapter in this Workspace",
    "dispatch.engine.not_installed": "not installed ({bins} not found)",
    "dispatch.engine.down":
        "WORKSPACE: {name} uses {engine}, but that engine isn't available: {why}.",
    "dispatch.engine.none":
        "  No engine is available on this machine — install one from the "
        "hub › Engines.",
    "dispatch.engine.available": "  Available engines: {list}",
    "dispatch.engine.hint":
        "  To open it with another one this time: {agent} --engine <engine>",
    "dispatch.engine.ask": "  Which one should I open it with this time?",
    "dispatch.engine.prompt": "Number and Enter · Enter alone cancels: ",
    "dispatch.engine.make_default":
        "  Make {engine} {name}'s engine on this machine? [y/N] ",
    "dispatch.engine.saved":
        "  ✓ {name} will use {engine} from now on (change it in Agents).",
    "dispatch.engine.save_fail":
        "  Couldn't save it ({err}); opening with {engine} this time anyway.",
    "dispatch.engine.this_time":
        "  Just this time: {name} keeps {engine} as its engine.",
    # cargando.py: centered while an agent's opening is being prepared
    "dispatch.cargando": "Loading…",
}
