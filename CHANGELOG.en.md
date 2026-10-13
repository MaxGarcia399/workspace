# What's new in Workspace

What changes in each version, told from your side of the screen. You can see
your version with `workspace version` (and at the bottom right of the hub).
Español: [CHANGELOG.md](CHANGELOG.md).

How to read this: every version has a number (`MAJOR.MINOR.PATCH`). A PATCH
change fixes things; a MINOR one brings new features without breaking
anything; a MAJOR one warns you well in advance if something changes shape.

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
