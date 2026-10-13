# The hub and its keys

The **hub** is what you see when you type `workspace`: a box with your agents and, below them,
three entries — **Menu**, **Personalization** and **Language**. Enter goes in; the box title shows
where you are (WORKSPACE › MENU) and Esc goes back. The box always keeps the same size: you can
shrink the window until only the box fits.

**Type to search.** Any letter types into the search at the top and the list filters instantly,
ignoring case and accents. From the start the search also finds what's inside (for example
"theme" → Personalization › theme).

<!-- Factory keys verified against keybinds.py (_AGENTES, _ACCIONES, _MENU_BASE, RESERVADAS,
auto-derived key for Engines) and front.py (lz_key, Tab, arrows).
tests/test_manual_compat.py fails if they change. -->

## Moving and entering

| Key | What it does |
|---|---|
| ↑ ↓ | move through the list |
| Enter | open the selection: an agent launches; an entry with `›` opens; in Personalization it changes the value |
| Esc | clear the search or go back one level |
| letters | search |
| ⌫ | delete the last letter of the search |
| `1` … `9` | with an empty search: point at the agent with that number; the same key again opens it |
| `q` | with an empty search: drop to your normal terminal |

When the window is very small the hub switches to a compact text view with the same actions;
the keys in the tables below also work there.

## On the agent you're pointing at

In the hub: **← →** switch its engine (`‹ engine ›`, saved on this machine) and **Tab** shows one
line with its engine, where its brain lives and what it's doing. In the compact view:

| Key | What it does |
|---|---|
| `m` | switch its **engine** (saved on this machine; the next Enter uses it) |
| `i` | one line with its engine, where its brain lives and what it's doing |

## Menu

The sections under **Menu**. In the hub you open them from Menu › (or by searching); in the
compact view, with their key:

| Key | Section | What for |
|---|---|---|
| `g` | Add agent | create a new agent or load one you already have |
| `b` | Agents | see each agent's settings and brain |
| `u` | Updates | check, repair and update Workspace |
| `v` | Commands | everything you can type in the terminal |
| `k` | Shortcuts | **change any of these keys** |
| `c` | Calendar | your agenda, full-screen and editable |
| `o` | Tone | your agents' personality dials |
| `s` | Engines | each engine's status, what it can do and its connections |

Each key shows next to its section in the menu itself. If a new section arrives in the future,
it gets a free key automatically; you'll see it in the menu and in **Shortcuts**.

## Changing keys

**Shortcuts** (`k`) lists every key and lets you change it. Only your changes are saved, on
this machine; if anything goes wrong, the factory keys come back. A key belongs to one action
only: if it's taken, Shortcuts tells you who uses it. You can't assign `q`, `l`, space, Enter,
Esc, Tab or the arrows, nor the letters `t` `a` `e` `x` `f` `d` `n` `p`, which other screens
use.
