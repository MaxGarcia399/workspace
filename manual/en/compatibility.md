# Compatibility: engine × operating system

What works today, with which engine, on which OS. If something isn't listed here as
"works", we don't promise it.

<!-- Source: capabilities.py (states and per-OS rules) + CAPABILITIES in engines/*.py.
Tables verified against the code; tests/test_manual_compat.py recomputes every cell from
capabilities.py and fails if a table goes stale (here or in ../es/compatibilidad.md). -->

## How to check your machine

The tables below are general. What holds **on your computer**, with what you have
installed, comes from the diagnosis — it changes nothing:

```bash
workspace doctor --check
```

Look for the phase **"Capacidades efectivas (OS + motor + dependencias)"** (effective
capabilities). For now the doctor prints this phase in Spanish; each feature gets one of
these states:

| Shown as | Meaning |
|---|---|
| **disponible** (supported) | works here, with what you have |
| **no soportado** (unsupported) | doesn't exist on this OS or this engine (the reason is shown) |
| **falta dependencia** (missing dependency) | would work, but something must be installed (what and how is shown) |
| **sin verificar** (unknown) | Workspace can't check it without running or logging in; it won't make it up |

## By engine

Applies to macOS, Linux and Windows unless noted.

| Feature | Claude Code | Codex | Antigravity |
|---|---|---|---|
| Open the agent from the hub | ✅ | ✅ (wrapped) | ✅ (wrapped) |
| Agent starts with its memory | ✅ automatic | ✅ through an `AGENTS.md` Workspace writes into the brain | ✅ through a `GEMINI.md` Workspace writes into the brain |
| MCP connectors | ✅ | ✅ (Codex's own config) | ✅ |
| Session events (*hooks*: save memory on close, etc.) | ✅ | ❌ | ❌ |
| Resume sessions from Workspace's tabs | ✅ | ✅ | ✅ |
| Live agent status in the hub | ✅ | ❌ | ❌ |
| Windowless tasks (evals, workflows) | ✅ | ✅ | ❌ |

✅ works · ❌ not available · ❔ unknown

If the engine's program isn't installed (or isn't on the PATH), features that depend on it
show up as **falta dependencia** (missing dependency), and the doctor tells you to install its
official program ([Engines](engines.md)).

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
