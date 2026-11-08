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
| Engines | two boxes: **Agent engines** (each engine's status, what it can do and its connections) and **Decision models**, with the same layout: the list of models and, beside it, their options — connect your key (the only thing to set up; it stays on this PC), test it with one real call (how long it takes, how many tokens it uses and what it cost) and see its context limit (measured) and its approximate price |
| Users | who uses each agent: «that's me on this PC», rename, merge two users who are the same person (e.g. the Mac one and the Windows one) and create a new one. Each user has a fixed ID, so renaming never confuses another machine; nothing is deleted |
| Deciders | which decision model picks among fixed options (Jev in the cloud, or none: out of the box no model is active) and which uses it helps with; models are connected and tested in Engines → Decision models, once (the first one that becomes ready is activated automatically). Uses: Workspace memory, evals, skills and security, plus choose, review, best prompt and split for your agents; each use with its level (off · observe · suggest · decide). Ask to try it by hand, with the context you choose (none, the tab, sessions, memory or the whole brain —if it does not fit, the most relevant parts; if nothing matches, the most recent—; each level shows its tokens and cost beforehand, and `v` lists the sources; if the model says it did not fit, Workspace trims and retries on its own). If something fails, the notice says what happened and what to do, and `d` shows the technical detail. A `.md` with `privado: true` in its frontmatter, or inside a `privado/` folder, is never sent; neither is what belongs to other people in a shared brain (their sessions, profiles, inbox and memory), chats, messages between agents, logs or files whose name starts with `_` inside `deliverables/`, and secrets are removed before anything leaves. History to see what happened, what each decision changed and how many there were today, and grade whether it was right; next to each use's threshold, its latest confidences. Everything starts off: then nothing leaves; each use you turn on with a cloud model sends its question and minimal context. The log stays on this PC |
| Documentation | the memory map (its first row) and everything Workspace does, in 13 chapters (opening a tab, closing, what travels, what goes online, what it never does…): each with a map, the real data on this PC for the chosen agent, the file or command that proves it (Enter opens it) and the setting that turns it off |

## Memory map

It lives in **Documentation** (Menu › Documentation): its first row, or the `m` key from any
chapter, opens the map of how the chosen agent remembers: the real tree of its brain and, step by
step, which files it reads and which it writes, in order and in colors. ← → or the digits `0` …
`7` change the step, ↑ ↓ scrolls if it doesn't fit, Tab switches agent, Enter opens what proves
it and Esc takes you back to the chapters.

## The digits

The digits `1` … `9` follow the order of your agents in the hub: the first is `1`, the second `2`,
and so on. From the tenth on, use the arrows or the search. Letters type into the search and
`q` drops to your terminal.
