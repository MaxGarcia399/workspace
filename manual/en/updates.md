# Updates

## What happens when Workspace updates

- **On its own, when you open an agent** (if you leave it that way; see
  [Choosing how it updates](#choosing-how-it-updates)). At most once every 6 hours, Workspace
  checks for a new version and installs it with the safety net below. With no internet,
  nothing happens.
- **Whenever you want:**

  ```bash
  workspace update
  ```

  Pulls the new version, also updates the brains you keep in git, and finally runs the
  [doctor](troubleshooting.md), which repairs whatever needs it. If something can't be updated
  (no internet, half-saved changes of yours), it tells you and carries on with the rest.

- **From the hub:** the **Updates** section. It shows your version, whether a new one is out and
  only what you can do right then: **update to vX** (when a new version is out), **check and
  repair**, **check only**, **go back to vX** (when there is a previous version to go back to;
  asks for Enter again) and the **automatic** setting. When it finishes you see what arrived and
  what is pending. The full explanation is behind the `i` key.

## The safety net

Before using a new version, Workspace **checks that it starts on your computer**, with your
Python. If it doesn't:

1. it goes back to the version you had, on its own;
2. it keeps that version **pinned** (it won't retry the same broken version every 6 hours);
3. the pin is released automatically when we publish a newer version.

Nothing for you to do. You'll see one line when opening an agent and "version pinned" at the
bottom right of the hub. To retry anyway: `workspace update --force`.

## What is left alone

Your agents, their brains, your settings, shortcuts and themes live outside the Workspace
folder and are kept. When a version needs to adjust something **inside your brains** (for
example, 0.4.0 moves your agents' identity to `BRAIN.md` and archives the old memory proposals
tray), it does it on its own, **copies everything to a backup first** and deletes nothing; what
you wrote yourself is left alone. Each version tells you in its release notes.

Workspace updates "fast-forward only": if you changed files inside the Workspace folder, it
**won't overwrite them**; the update stops and tells you.

## Adjustments a version brings

Sometimes a version needs to adjust something on your machine (for example, moving a settings
file to its new place). Those adjustments:

- are applied on their own after updating or when the hub opens, **in plain sight** (one line:
  "✓ 1 update adjustment(s) applied.");
- are **recorded**, so each one runs only once;
- if one fails, Workspace **keeps working**, no later adjustment runs until it's resolved, and
  `workspace doctor` tells you what happened;
- big changes are **never applied without asking**: they show up as "optional change
  available" in the doctor; accept them with `workspace migrate --offer <id>` or say "no thanks" with
  `workspace migrate --decline <id>` (they won't be offered again).

To see them: `workspace migrate`.

## Which version you have and what changed

```bash
workspace version
```

Shows your version, when your last update was and what's new in this version. The version also
shows at the bottom right of the hub. The full history is in **`CHANGELOG.en.md`**, in the
Workspace folder.

## Going back

If a new version starts but you don't like it:

```bash
workspace update --rollback
```

In the hub it is the **go back to vX** option in Updates (it only shows up when there is one).
It shows which version you go back to and asks for confirmation. The previous version's
code comes back; your agents, brains and settings are not touched. The new version stays paused until we
publish a newer one. Adjustments the new version already applied are designed so the previous
one keeps working with them.

## Choosing how it updates

Automatic updates are **optional**. There are three modes:

| Mode | What it does | Goes online on its own |
|---|---|---|
| `auto` (default) | when you open an agent it installs the new version, with the safety net | yes, at most every 6 h |
| `notify` | once a day it tells you "a new version is out" and installs nothing | yes, at most once a day |
| `off` | checks nothing | no |

To change it:

- in the hub: **Updates** section, **automatic** row (Enter moves to the next mode: yes · notify
  only · off);
- in the terminal: `workspace update --auto notify` (or `auto`, `off`); with no mode it tells
  you which one you have.

In all three modes, `workspace update` installs when you ask and `workspace update --rollback`
takes you back. With `notify` or `off`, `workspace doctor` respects your choice too: it tells
you a new version exists but doesn't install it.

A version's **adjustments** (above) run in all three modes: they download nothing, they only
adapt your machine to the code you already have.

The environment variable `WORKSPACE_NO_AUTOUPDATE=1` still works and wins over the setting
(same as `off`).
