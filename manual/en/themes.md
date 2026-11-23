# Themes and appearance

Workspace ships eight color themes for the hub (**bruma**, the default, plus rose, durazno,
lavanda, salvia, cyberpunk, mono and blanco) and lets you pick the background separately.
**Blanco** (white) is the only light one: white background, everything in black. That's why
it ignores a dark background picked separately (it would make the text invisible).

## Changing the theme

- The first run no longer asks: you start with the default theme.
- Any time, in the hub: **Ajustes › Apariencia** (settings › appearance), rows **Tema del hub**
  (hub theme) and **Fondo independiente** (separate background).

<!-- Verified against hub_secciones_r2.py (ajustes_filas: General and Apariencia groups) and
settings.py (ui.theme default "bruma", ui.background, ui.background_custom, pin_label). -->

The **background** can change without changing the theme: negro (black), grafito (graphite),
azul (blue), verde (green) or violeta (violet); **tema** goes back to the active theme's
background, and **personalizado** (custom) uses your own color. You set that color once, from
the Workspace folder (on Windows, `python` instead of `python3`):

```bash
python3 settings.py set ui.background_custom "#1a1b26"
```

Ajustes › Apariencia also has **Brillo** (brightness: livelier or dimmer) and **Luz roja (modo
noche)** (red light, night mode). Ajustes › General has **Abrir al abrir la terminal** (the hub
shows up when you open the terminal) and **Abrir Workspace en el navegador al iniciar** (the
page opens along with the hub, if no other hub is open).

## What changes and what doesn't

- The theme paints **the hub and Workspace's screens**.
- Each agent can have its own terminal colors; yours come back when you leave the agent.
- With Claude Code, an agent can also bring its theme inside Claude Code. With other engines
  only the terminal colors apply.
- Your choices are saved **on this machine** and survive updates.

Something looks misaligned? Make the window bigger; on Windows use **Windows Terminal**.
