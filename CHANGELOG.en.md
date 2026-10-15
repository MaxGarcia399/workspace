# What's new in Workspace

What changes in each version, told from your side of the screen. You can see
your version with `workspace version` (and at the bottom right of the hub).
Español: [CHANGELOG.md](CHANGELOG.md).

How to read this: every version has a number (`MAJOR.MINOR.PATCH`). A PATCH
change fixes things; a MINOR one brings new features without breaking
anything; a MAJOR one warns you well in advance if something changes shape.

## 0.3.3 — 2026-10-14

**Fixes**
- The hub no longer shows the "setup unfinished" notice. It was based on how
  you left the first run and never refreshed, so it could stay even after you
  had finished it. To go through the first run again: `workspace onboarding`.

## 0.3.2 — 2026-10-14

**Fixes**
- If you already had engines and agents and only peeked at the first run, the
  hub no longer shows the "setup unfinished" notice forever.

## 0.3.1 — 2026-10-14

**A simpler hub: every section in one small box**
- Each section shows only what you need to use it, in a centered box. The
  explanation (how it works, with its maps) is behind the `i` key.
- **Agents:** your agents on top and, below, the options of the one you pick
  (Enter or →; ← or Esc go back). Adding an agent lives right here: the
  «+ add agent» row at the end of the list (or the `a` key); with no agents
  yet, the form opens directly.
- **Creating an agent:** the fields look empty (they used to carry an
  «e.g. …» inside that looked already filled in). The example and the
  explanation of the field you're on go below the form, and if you write a
  lot, you see your whole text there. In **your preferences** every row says
  what it is: yes/no switches, what you picked with «›» to change it, and one
  line below about the selected row; its `i` sums up what you're about to
  create, your usage and how it's born.
- **Engines:** the list on the left and the options on the right. When it
  opens it really checks whether you're signed in to each one: ready · not
  signed in · not installed.
- **Updates:** your version, whether a new one is out and only what you can do
  right then: update (when there's a new version), check and repair, check
  only, go back to the previous version (when there's one) and whether it
  updates itself (yes · notify only · off).
- **Commands:** the list by group and, below, how to type the one you pick
  and what it does. `i` opens its map on the right and when it's useful, and
  it changes as you move.
- **The first run** uses the same box: each step in one box with the
  progress on top (engines → appearance → agent), only what you need to
  decide and the main action below; what explains each step is behind `i`.
  Picking an option no longer moves you forward: in every step (Tone too)
  you move on with the «✦ continue» button, and at the end «✦ go to the hub»
  opens the hub (it used to leave you in the terminal).
- **Calendar** stays the same and gains its explanation behind `i`. **Tone**
  is the box with your agents and their dials.

**Out with what wasn't used**
- **Shortcuts** left the menu: keys `1` to `9` always follow the order of
  your agents in the hub.
- **Google Calendar** is paused while we improve it: it doesn't show in the
  calendar or in the first run.

**Fixes**
- Engines no longer loses the keyboard while it checks the sign-ins.
- Section titles no longer have a shadow under them, just like the hub's.

## 0.3.0 — 2026-10-13

**You decide how much each agent can do without asking you**
- When you create or load an agent you choose two things: whether it reads
  and writes its brain without asking you (**yes** to start with: it's its
  main job) and whether you want automatic skill review when each session
  closes (**no** to start with). Without an interactive terminal (a script)
  those values are used; `agent_admin.py` takes `--autonomy brain|ask` and
  `--skill-review`.
- You change both later in **Agents** (pick the agent and Enter),
  agent by agent. If you turn off access to its brain, it asks you before
  creating or editing any file, also inside it. Without opening the hub:
  `agent_admin.py prefs <agent> --autonomy brain|ask
  --skill-review|--no-skill-review`.
- Your answer is saved with the agent (in its `agent.json`, it travels with
  the brain) and each engine applies it its own way.
- With Claude Code, a new agent reads, creates and edits files **inside its
  brain** without asking you; for the terminal, files outside it and the
  network it asks you first. The engine's protections are never switched
  off.
- Before, the installer let every Claude Code agent run any command without
  asking (and included a store integration that wasn't yours). When you
  update, your agents switch on their own to the new setup: free only inside
  their brain (their previous settings are backed up). Running commands
  without asking is no longer an option.
- "Auto-accept edits" on every Claude Code session (`agentes.auto_mode`) is
  now **off** by default: the brain's permissions rule. To get it back:
  `python3 settings.py set agentes.auto_mode on` in Workspace's folder.

**Skill review is optional and works with all three engines**
- It ships **off**. If you turn it on for an agent, when each session closes
  its own engine (Claude Code, Codex or Antigravity) reviews in the
  background what you corrected and improves its skills; new skills stay as
  proposals until you approve them.
- It reads a neutral copy of the session (not the vendor's internal file),
  uses neither the terminal nor the network, never makes closing wait, and
  uses a little of your subscription.
- It reviews the right brain even when the session ends inside a subfolder
  (before, it reviewed that subfolder and ignored what you chose for the
  agent); with Claude Code it no longer stays saved as one more conversation
  of the agent, and its report reaches the review log even when Claude Code
  won't let it write there. Turn it on or off in **Agents** (pick the agent and Enter);
  agents that didn't choose follow the global `hooks.skill_review` setting (`python3 settings.py set
  hooks.skill_review on` in the Workspace folder).

**The doctor now checks and repairs only the essentials**
- `workspace doctor` (and what you see at the end of `workspace update`) now
  checks only the essentials: your agents, their hooks and commands,
  git/Python/the engine you use, and updates. If one of those isn't working,
  it tells you and fixes it.
- No more warnings that had nothing to do with you: internal brain
  conventions (BOOT, INDEX, manifests, banner), GitHub CLI, a team channel,
  autonomous mode, and optional features you don't use (voice, split
  terminal).
- Having no agents yet is normal: it's no longer a warning.
- It now detects and fixes an agent's hooks that point to a Workspace folder
  that no longer exists (for example, after moving or reinstalling).
- Voice is set up whenever you want with `workspace voice --setup`; the
  doctor no longer checks it.

**Out with what you weren't using**
- Letter keys that no longer opened anything (c, o, k, u, g, s, b, v, m, i, l)
  are gone from Shortcuts, the first-run summary and the manual: in the hub
  letters search; the quick keys are `1`–`9` (your agents) and `q`. Shortcuts
  now only changes each agent's digit.
- `workspace versiones` (and `ramas`/`branches`) is gone: it was a git
  branch map for people developing Workspace, not for you.
- The old configuration screen is gone; the hub could no longer open it.
  Your settings stay: theme and background in Personalization, permissions
  and skill review in Agents (Enter on the agent), and any setting with
  `python3 settings.py set <setting> <value>`.
- New agents no longer get a gallery of emblems that nothing showed.
- `workspace foco` (`focus`) is gone: it saved a focus of the day that no
  screen showed. Your agenda and the calendar stay as they were.

**Fixes**
- Creating an agent no longer ends with "⚠ final check 1 placeholder(s)
  left unfilled": the new agent's owner page (BOOT/02-TEAM.md) is now filled
  in.
- If you came from the previous install, an internal agent that was never
  yours had slipped into your list; the doctor checked it and it blocked
  retiring that install's leftovers. An automatic adjustment removes it (with
  a backup) and those leftovers can now be retired with
  `workspace migrar-legado`.
- "Resume session" no longer gives a false warning when another folder has
  the same name as your brain, and it's only checked for Claude Code agents.

**Install and privacy**
- The installer no longer asks "Who are you?".
- It asks for the CLI of the engine you'll use (Claude Code, Codex or
  Antigravity), not always Claude Code.
- Your sessions are kept for **one year** (it was ten). If you had the value
  our installer used to set, it goes down to 365 days; if you chose another
  one, it's left alone.
- New brains no longer come with session folders named after other people.

## 0.2.0 — 2026-10-13

**A new hub: the Launcher**
- The hub is now a single box with your agents and, below them, Menu,
  Personalization and Language. Enter goes in, Esc goes back and the title
  tells you where you are.
- Type to search: the list filters instantly and also finds what's inside
  (for example "theme").
- ← → switch the engine of the agent you're pointing at (`‹ engine ›`); Tab
  shows its details.
- The box always keeps the same size: you can shrink the window until only
  the box fits. The previous hub and its variants are gone.
- Esc takes you back to the hub from every section (Calendar, Tone and
  Updates used to drop you to the terminal) and from an agent's session
  menu, which now shows just its name and its sessions.

**Updates with a safety net, and optional**
- You choose whether Workspace updates itself: **automatic** (as before),
  **notify only** (it tells you a new version is out and you decide) or
  **off**. Change it in Updates (key `a`) or with `workspace update --auto`.
- Before using a new version, Workspace checks that it starts on your
  computer. If it doesn't, it goes back to the one you had and waits until we
  publish a fix. Nothing for you to do.
- If you don't like a new version, `workspace update --rollback` takes you
  back to the previous one. Your agents, brains and settings aren't touched.
- The adjustments a version needs to make on your machine are applied in
  plain sight and recorded. If one fails, Workspace keeps working and
  `workspace doctor` tells you what happened and how to continue.
- `workspace version` shows your version, your last update and these notes.
  The version also shows at the bottom right of the hub.

**Help and diagnosis**
- `workspace doctor --bundle` builds a diagnostic ZIP to ask for help, with
  your personal data blanked out and a README saying what's inside.
- New user manual in `manual/` (Spanish and English), with an honest table of
  what works with each engine on each system and which data leaves your
  computer.
- A template to report problems and a private channel to report security
  issues (`SECURITY.md`).

**Commands**
- Every command accepts its Spanish and English name (`tono`/`tone`,
  `actualizar`/`update`…); every name from before still works.
- The Commands screen searches with `/` and runs the command with Enter (asks
  for confirmation on the delicate ones).
- `workspace commands --json` gives your agents the full list.

**Install, first run and uninstall**
- The installer checks your computer before touching anything (Python, git,
  disk space, cloud folders) and tells you what to fix, without blaming you.
- At the end of the welcome you see the keys that matter (yours, if you
  changed them).
- Uninstall shows what is deleted and what is kept, offers a backup of your
  settings (without your keys) and refuses to delete folders that aren't
  Workspace's.

**Security**
- Closed the open findings of an internal audit: the key vault no longer
  leaves a readable file while saving, the bus never dispatches the same
  message twice, the review of an agent's changes catches more kinds of keys
  and dangerous commands, and a key is never saved under another account.

**Agent tone**
- Tone dials are firmer: Length sets a concrete word budget, rules the shape of the answer and wins when it clashes with another dial. In Codex and Antigravity the tone now comes first in the startup instructions.

**Themes**
- A theme defines one palette, and the colours of the hub, the terminal and
  the theme inside Claude Code all come from it. What you made by hand isn't
  overwritten. Nothing changes on screen unless you pick a new theme.
- New **Blanco** (white) theme: white background with everything else in
  black, the inverse of Mono. Both use just two pure colours, no greys.
- The theme and background you pick in the hub now also colour your agents'
  sessions: the status bar, the banner and the theme inside Claude Code.
  A Claude Code theme you edited by hand is kept.

**Cleanup**
- The product's previous name is gone from screens and texts; Workspace still
  recognises and migrates leftovers of the previous install.
- The hub's GitHub section is temporarily removed while we rework it.

## 0.1.0 — 2026-06-18

- First version: terminal hub, agents with their own brain, swappable engines,
  guided onboarding, a doctor that checks and repairs, and automatic updates.
