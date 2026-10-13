# Themes and appearance

Workspace ships eight color themes for the hub (**bruma**, the default, plus rose, durazno,
lavanda, salvia, cyberpunk, mono and blanco) and lets you pick the background separately.
**Blanco** (white) is the only light one: white background, everything in black. That's why
it ignores a dark background picked separately (it would make the text invisible).

## Changing the theme

- On the **first run**, the *Appearance* step (repeat it with `workspace onboarding`).
- Any time, in the hub: go into **Personalization ›** (or type "theme"), pick the **theme**
  or **background** row and press Enter to move to the next one. The change is saved right
  away.

<!-- Verified against front.py (cycle_pin), settings.py (ui.theme default "bruma",
ui.background, ui.background_custom, ui.hub_pins) and onboarding_tui.py (appearance step). -->

The **background** can change without changing the theme: negro (black), grafito (graphite),
azul (blue), verde (green) or violeta (violet); **tema** goes back to the active theme's
background, and **personalizado** (custom) uses your own color. You set that color once, from
the Workspace folder (on Windows, `python` instead of `python3`):

```bash
python3 settings.py set ui.background_custom "#1a1b26"
```

Personalization also has **brightness** (livelier or dimmer), **red light** (night
mode) and **auto-open** (the hub shows up when you open the terminal).

## What changes and what doesn't

- The theme paints **the hub and Workspace's screens**.
- Each agent can have its own terminal colors; yours come back when you leave the agent.
- With Claude Code, an agent can also bring its theme inside Claude Code. With other engines
  only the terminal colors apply.
- Your choices are saved **on this machine** and survive updates.

Something looks misaligned? Make the window bigger; on Windows use **Windows Terminal**.
