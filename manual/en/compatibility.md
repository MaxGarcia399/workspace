# Compatibility: engine × operating system

What works today, with which engine, on which OS. If something isn't listed here as
"works", we don't promise it.

<!-- Source: capabilities.py (states and per-OS rules) + CAPABILITIES in engines/*.py.
Tables verified against the code; tests/test_manual_compat.py recomputes every cell from
capabilities.py and fails if a table goes stale (here or in ../es/compatibilidad.md). -->

## How to check your machine

The tables below are general. What holds **on your computer**, with what you have installed:

- **Engines:** the hub's **Engines** section tells you whether each one is installed
  and logged in. `workspace doctor` also warns you if the program of an engine one of your
  agents uses is missing.
- **Voice dictation:** `workspace voice --check` tells you what's missing;
  `workspace voice --setup` installs it.

Dictation is optional: the doctor doesn't check it.

## By engine

Applies to macOS, Linux and Windows unless noted.

| Feature | Claude Code | Codex | Antigravity | OpenCode | OpenClaw | Hermes | Kiro | GitHub Copilot | Cursor |
|---|---|---|---|---|---|---|---|---|---|
| Open the agent from the hub | ✅ | ✅ (wrapped) | ✅ (wrapped) | ✅ (wrapped) | ✅ (wrapped, with gateway: several tabs) | ✅ (wrapped) | ✅ (wrapped) | ✅ (wrapped) | ✅ (wrapped) |
| Agent starts with its memory | ✅ automatic | ✅ through an `AGENTS.md` Workspace writes into the brain | ✅ through a `GEMINI.md` Workspace writes into the brain | ✅ through an `AGENTS.md` Workspace writes into the brain | ✅ through the same `AGENTS.md` (OpenClaw profile of its own, no extra files) and, on every message, the brain's `STATE/MEMORY.md` | ✅ through the same `AGENTS.md` (Hermes profile of its own, neutral identity) and, with your first message (also when you resume a tab), the tab's up-to-date memory and the brain's `STATE/MEMORY.md` | ✅ through the same `AGENTS.md` Workspace writes into the brain | ✅ through the same `AGENTS.md` and its own `CLAUDE.md` (which brings in `BRAIN.md`); it reads them again when resuming | ✅ through the same `AGENTS.md` (Cursor also reads the brain's `CLAUDE.md`) |
| MCP connectors | ✅ | ✅ (Codex's own config) | ✅ | ✅ (OpenCode's own config) | ✅ (OpenClaw's own config) | ✅ (Hermes' own config) | ✅ (Kiro's own config) | ✅ (Copilot's own config) | ✅ (Cursor's own config) |
| Session events (*hooks*: save memory on close, etc.) | ✅ | ✅ on open and close only (sent by Workspace) | ✅ on open and close only (sent by Workspace) | ✅ on open and close only (sent by Workspace) | ✅ on open and close only (sent by Workspace) | ✅ on open and close only (sent by Workspace), plus your tone with every message and the tab's memory when you resume | ✅ on open and close only (sent by Workspace) | ✅ on open and close only (sent by Workspace) | ✅ on open and close only (sent by Workspace) |
| Resume sessions from Workspace's tabs | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Live agent status in the hub | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Windowless tasks (evals) | ✅ | ✅ evals with tools¹ | ❌ | ✅ evals with tools¹ | ✅ single turns only¹ | ✅ single turns only¹ | ✅ single turns only, not yet tested with an account¹ | ✅ single turns only¹ | ✅ single turns only, not yet tried with an account¹ |

✅ works · ❌ not available · ❔ unknown

¹ Evals that run without tools need an engine that can turn its own tools off: today only
Claude Code. Codex and OpenCode run the evals that use tools inside the OS sandbox. OpenClaw,
Hermes, Kiro, GitHub Copilot and Cursor can't turn their tools off or run inside that sandbox
yet: Workspace doesn't use them for evals (they still answer single windowless turns; Kiro's
and Cursor's haven't been tested with an account yet).

If the engine's program isn't installed (or isn't on the PATH), none of this works with it:
`workspace doctor` tells you to install its official program ([Engines](engines.md)).

Codex, Antigravity, OpenCode, OpenClaw, Hermes, Kiro and Cursor have hooks of their own too, but Workspace doesn't turn them on:
Workspace already sends the open and close events around the program, and turning them on would
send them twice. The exceptions: one Hermes hook, per message, that adds your tone and, when a
conversation starts or resumes, the tab's memory and the brain's (Hermes approves it by itself
if it's the only hook in the profile; if
you added hooks of your own, it asks you to approve it once), and OpenClaw's official one that
loads the brain's memory. That's why those engines have no per-tool events or live status. With
OpenCode, OpenClaw, Hermes, Kiro and Cursor, the model is the one you pick in its own config: Workspace doesn't change it.

GitHub Copilot has hooks of its own too, and they aren't turned on either. It reads the brain's
`AGENTS.md`, `CLAUDE.md` and `GEMINI.md` together (and follows the `@BRAIN.md` in `CLAUDE.md`), so
your agent arrives with its identity even if the `AGENTS.md` is yours. The model is your Copilot
account's (or the one you pick with `/model`): Workspace doesn't change it. The first time in each
brain, Copilot asks whether you trust that folder; answer "Yes, and remember this folder".

Cursor also runs, on its own, the Claude Code *hooks* it finds (the brain's and the ones in your
`~/.claude/settings.json`). Workspace's do nothing inside Cursor, so events aren't sent twice;
yours run as Cursor decides.

Hermes runs in a Workspace profile of its own (your personal Hermes doesn't change). In that
profile its own memory is off, because all your agents share it: each agent's memory lives in its
brain and reaches it through `AGENTS.md` and, when you resume, through its hook. It uses each
agent's brain skills (`skills/`) besides its built-in ones, and saves the ones it learns in that
same brain (`skills/aprendidas/`), not in the shared profile: when the session closes, Workspace
adds them to the brain's catalog and your other engines see them too. Its scheduled tasks stay as
in your Hermes.

OpenClaw runs in a profile of its own too. Its own memory is off and it reads the brain's
(`STATE/MEMORY.md`) on every message through its official hook, when it runs with the gateway (the
usual case); in single-window mode it opens without it. Its memory search stays on, but it only
searches its own memory files, which the brain doesn't use; Workspace doesn't point it at the
brain: indexing it would send your notes to an outside service. Its skills are the brain's
(`skills/`).

## Permissions by engine

Each agent has an **autonomy** (`"autonomy"` in its `.workspace/agent.json`). If it doesn't say,
it's **brain**. Workspace translates it into what each engine understands and never uses the
modes that skip every permission.

| | Brain (default) | Ask (`"ask"`) |
|---|---|---|
| In all three engines | reads, creates and edits inside its brain without asking; the terminal, files outside the brain and the network ask first | asks before creating or editing, also inside its brain |
| Claude Code | read and edit allowed only in the brain folder | no Workspace rules: asks before editing |
| Codex | `-s workspace-write -a on-request`, with network off | `-s read-only -a on-request`: asks for approval to edit or run anything |
| Antigravity | `--mode accept-edits` and the `write_file(<brain>)` rule | no `--mode`; the rule stays `read_file(<brain>)` |

Change it in **Agents** (pick the agent and Enter) (see [Permissions](engines.md#permissions)).

- In a windowless task, anything that would ask is denied.
- **Codex:** with *brain*, its commands run without asking **inside its sandbox**: they can only
  write to its brain and the system's temporary folders, with no network. Anything that needs to
  leave the sandbox asks you. With *ask*, the sandbox is read-only and it asks for approval before
  editing or running anything.
- **Antigravity:** the `write_file(<brain>)` rule lives in Antigravity's general settings, so any
  Antigravity session can edit that brain without asking.
- Running commands without asking no longer exists. An agent that had it from an earlier
  version (`"full"` in its `agent.json`) switches to *brain* when you update.
- If you pass your own options when opening the engine (`-a` in Codex; `--mode` or `--project`
  in Antigravity), yours win.

## Your keys: which engine can read them

Workspace keeps the keys you give it (for example, a decision model's) in its vault, outside
your brain (see [Privacy](privacy.md#credentials)). No engine gets it through the environment.
On top of that, for the engines that have rules for it, Workspace denies them **reading the
vault** (the file `~/.claude/workspace/secrets.local` and the folder
`~/.claude/workspace/boveda/`) and, where possible, **asking the keychain for a key** (the
`security` and `secret-tool` programs as a whole, with any subcommand: `security -i` too). It
applies with any autonomy.

| Engine | Read the vault | Ask the keychain for a key | How |
|---|---|---|---|
| Claude Code | denied ❔ | denied ❔ | `permissions.deny` with `Read(…)` and `Bash(security …)` in each tab's `--settings` and, with *brain* autonomy, also in the brain's `settings.local.json`. Per its docs it covers its read tools and `cat`/`head`/`tail`, not a script |
| GitHub Copilot | denied ❔ | denied ❔ (macOS and Linux) | `--deny-tool=read(…)` and `--deny-tool=shell(security …)` on every run |
| Cursor | denied ❔ | denied ❔ | `Read(**/…)` and `Shell(security:…)` in the brain's `.cursor/cli.json`; its `Read` does not stop a `cat` in its terminal |
| Kiro | denied ❔ | ❌ | a separate `fs_read` deny rule (V3) and `fs_read.deniedPaths` (2.x) in its agent |
| Antigravity | denied ❔ | denied ❔ | `read_file(…)` and `command(security …)` in the run's `--settings` |
| Codex | ❌ | ❌ | its sandbox can read the whole disk; its permission profiles, which would allow it, are in beta and clash with the sandbox Workspace uses |
| Gemini | ❌ | ❌ | it has no per-path read rule |
| OpenCode | ❌ | ❌ | it has a read rule, but Workspace does not write its configuration |
| OpenClaw | ❌ | ❌ | its policy filters tools by name, not by path |
| Hermes | ❌ | ❌ | its read-deny list is fixed |

❔ The rule follows each engine's official docs, but it was not tested with the program.

**What this does not do.** A program or script running as your same user (for example,
`python -c …` in the agent's terminal) can still ask the keychain for the key or read the file:
the rules stop the agent's file tools and those two programs, not everything.
What the keychain does protect is the disk, backups (Time Machine, File History), sync and the
other users on the machine.

## Status bar and theme by engine

| | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Status bar | Workspace's | Codex's own: model, context, 5-hour and weekly limits, and the project if the brain is a git repository | Antigravity's own and, below it, Workspace's: agent, model, context, mode and quotas |
| Agent name | in the bar | in the window title | in the bar and in the window title |
| Hub theme | a Claude Code theme generated from the palette | a `.tmTheme` theme in `~/.codex/themes/` that colors the bar, code and diffs | recolors the terminal's basic colors while it runs and restores them on exit |
| If you already picked your own | kept | kept (`tui.theme`, `tui.status_line` or `tui.terminal_title` in your `config.toml`) | kept (your `colorScheme` or your own `statusLine`) |

- **Codex shows a single bar.** Workspace also has a two-line footer of its own, with quota
  resets and uptime; it's off and you turn it on with `WORKSPACE_CODEX_LIVE_BAR=1`. It needs tmux
  (macOS and Linux). When it shows up, Codex's bar is hidden so you don't get two.
- **Antigravity:** if your settings had an old Workspace bar, or one pointing at a path that no
  longer exists, it fixes itself when you open an agent. The new one points at
  `~/.local/bin/workspace-agy-statusline`, which finds Workspace even if you move it.
- **Antigravity** only paints with your terminal's basic colors under its `"terminal"` scheme
  (the factory one). If you picked another scheme, Workspace doesn't change it.

## By OS (Workspace features)

| Feature | macOS | Linux | Windows |
|---|---|---|---|
| Voice dictation (local) | ✅ if you install whisper.cpp, its model and ffmpeg or sox | ❌ for now | ❌ for now |

## Current limits

- **"You choose the engine" is only half true today.** Every engine opens agents with the
  same tab memory, but Claude Code is more integrated, and part of the local configuration still
  lives in `~/.claude/workspace/` even if you don't use Claude Code.
- **Switching engines doesn't carry the vendor's conversation over**, but the tab does: its
  memory (summary, open items, notes and the handoff with the other engine's latest) belongs to
  Workspace and loads the same on any engine. See [Engines · Each tab's memory](engines.md).
