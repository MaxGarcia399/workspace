"""Conserva los colores de terminal de agentes llamados prueba/midas/midas2.

Hasta 0.1.x `themes.json` (en el repo) traía paletas de prueba con esos
nombres. En 0.2.0 salen del repo (no son del producto). Si en esta máquina hay
un agente con alguno de esos nombres y no tiene su propia entrada en
`themes.local.json`, se le copia la paleta que veía, para que nada cambie.
Aditivo: no toca ninguna otra entrada (regla expandir → contraer).
"""

TITLE = {"es": "Conservar los colores de terminal de agentes de prueba",
         "en": "Keep the terminal colours of test agents"}
KIND = "auto"


def _agent_names():
    try:
        import dispatch
        return [str(a.get("name", "")) for a in dispatch.load_registry().get("agents", [])]
    except Exception:
        return []


def needed(ctx):
    import theme_render
    return bool(theme_render.legacy_presets_needed(_agent_names(), ctx.home))


def run(ctx):
    import theme_render
    theme_render.adopt_legacy_presets(_agent_names(), ctx.home)
