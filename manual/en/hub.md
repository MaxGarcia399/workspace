# The hub and its keys

The **hub** is what you see when you type `workspace`: a box with your agents and, below them,
three entries — **Menu**, **Personalization** and **Language**. Enter goes in; the box title shows
where you are (WORKSPACE › MENU) and Esc goes back. The box always keeps the same size: you can
shrink the window until only the box fits.

**Type to search.** Any letter types into the search at the top and the list filters instantly,
ignoring case and accents. From the start the search also finds what's inside (for example
"theme" → Personalization › theme).

<!-- Keys verified against front.py (_jump_map, lz_key, Tab, arrows).
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

## On the agent you're pointing at

**← →** switch its engine (`‹ engine ›`, saved on this machine; the next Enter uses it) and
**Tab** shows one line with its engine, where its brain lives and what it's doing.

## Menu

The sections under **Menu**. Open them from Menu › or by searching:

| Section | What for |
|---|---|
| Agents | your agents and their options (Enter on one); «+ add agent», at the end of the list, creates or loads a new one |
| Updates | check, repair and update Workspace |
| Commands | everything you can type in the terminal |
| Calendar | your agenda, full-screen and editable |
| Tone | your agents' personality dials |
| Engines | each engine's status, what it can do and its connections |
| Users | who uses each agent: «that's me on this PC», rename, merge two users who are the same person (e.g. the Mac one and the Windows one) and create a new one. Each user has a fixed ID, so renaming never confuses another machine; nothing is deleted |
| Documentation | everything Workspace does, in 13 chapters (opening a tab, closing, what travels, what goes online, what it never does…): each with a map, the real data on this PC for the chosen agent, the file or command that proves it (Enter opens it) and the setting that turns it off |

## The digits

The digits `1` … `9` follow the order of your agents in the hub: the first is `1`, the second `2`,
and so on. From the tenth on, use the arrows or the search. Letters type into the search and
`q` drops to your terminal.
