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
- **Split terminal:** if you turn it on and tmux (or herdr) is missing, opening an agent
  tells you so and opens the plain session.

These are optional features: the doctor doesn't check them.

## By engine

Applies to macOS, Linux and Windows unless noted.

| Feature | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Open the agent from the hub | ✅ | ✅ (wrapped) | ✅ (wrapped) |
| Agent starts with its memory | ✅ automatic | ✅ through an `AGENTS.md` Workspace writes into the brain | ✅ through a `GEMINI.md` Workspace writes into the brain |
| MCP connectors | ✅ | ✅ (Codex's own config) | ✅ |
| Session events (*hooks*: save memory on close, etc.) | ✅ | ✅ on open and close only (sent by Workspace) | ✅ on open and close only (sent by Workspace) |
| Resume sessions from Workspace's tabs | ✅ | ✅ | ✅ |
| Live agent status in the hub | ✅ | ❌ | ❌ |
| Windowless tasks (evals, workflows) | ✅ | ✅ | ❌ |

✅ works · ❌ not available · ❔ unknown

If the engine's program isn't installed (or isn't on the PATH), none of this works with it:
`workspace doctor` tells you to install its official program ([Engines](engines.md)).

Codex and Antigravity have hooks of their own too, but Workspace doesn't turn them on: Workspace
already sends the open and close events around the program, and turning them on would send them
twice. That's why those two engines have no per-tool events or live status.

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
| Split terminal (chat + board) | ✅ with tmux or herdr | ✅ with tmux or herdr | ❌ opens the plain session |
| Side panel controls | ✅ inside the split terminal | ✅ inside the split terminal | read-only |

## Current limits

- **"You choose the engine" is only half true today.** All three engines open agents with
  their memory, but Claude Code is more integrated, and part of the local configuration still
  lives in `~/.claude/workspace/` even if you don't use Claude Code.
- **Switching engines doesn't carry conversations over**: the brain travels; each vendor's
  internal history doesn't.
