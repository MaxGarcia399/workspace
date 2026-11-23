# Install

## Before you start

You need three things:

1. **Python 3.9 or newer.** On Windows the command is `python`; on Mac/Linux, `python3`.
2. **Git.**
3. **At least one engine** installed and logged in with your account: **Claude Code**
   (`claude`), **Codex** (`codex`), **Antigravity** (`agy`), **OpenCode** (`opencode`),
   **OpenClaw** (`openclaw`), **Hermes** (`hermes`), **Kiro** (`kiro-cli`), **GitHub Copilot**
   (`copilot`) or **Cursor** (`cursor-agent`). If you don't have one yet, the first run helps
   you install it.

No `pip install`, nothing else: Workspace has no dependencies.

## macOS / Linux

One command:

```bash
curl -fsSL https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.sh | bash
```

It installs into `~/Workspace`, outside your Desktop, Documents and Downloads: that way macOS
doesn't ask you to let the terminal into those folders. Your new agents are born in
`~/Workspace/Cerebros`. If you already had Workspace somewhere else (for example, in
`~/Desktop/Workspace`), the same command detects it and updates it there: nothing moves. If you
already have a `~/Workspace` folder with your own files, it leaves it alone: it asks you to pick
another one with `WORKSPACE_DIR="$HOME/Workspace-app"` in front of the command.

While it installs you see four steps (check your Mac, download, set up the command and open
Workspace). If your Mac is missing Apple's command line tools, it opens Apple's installer and
waits for it; if the internet drops, it retries by itself. To see everything it does:
`curl -fsSL … | bash -s -- --detalle` (the same always goes to
`~/.claude/workspace/instalar.log`).

Prefer to see what you run before running it? Good call. Same thing in two steps:

```bash
git clone https://github.com/MaxGarcia399/workspace.git ~/Workspace
python3 ~/Workspace/install.py
```

## Windows (PowerShell)

One command, in PowerShell:

```powershell
irm https://workspacecli.ai/install.ps1 | iex
```

It's the repo's `setup.ps1` and it runs in your same window (no execution-policy change).
It installs into `%LOCALAPPDATA%\Workspace`. If your Windows is missing Git or Python (or both), it
offers to install them with winget (Microsoft's installer) and only does it if you press Enter. In two
steps, if you'd rather check first:

```powershell
git clone https://github.com/MaxGarcia399/workspace.git "$env:LOCALAPPDATA\Workspace"
python "$env:LOCALAPPDATA\Workspace\install.py"
```

**Don't install it inside OneDrive** (that includes a Desktop or Documents folder that
OneDrive syncs). The installer refuses on purpose: syncing locks files and breaks Workspace.
When it finishes, Workspace opens in the same window and the `workspace` command already works
there (and in PowerShell, cmd.exe and the VS Code terminal).

## What the installer touches

Only **your machine**: it adds the `workspace` command, wires the hooks the engines need and
keeps your local settings in `~/.claude/workspace/`. It creates no accounts and sends nothing.

Got a system notice (permissions, "possible malware", administrator)? [Your system's
notices](system-notices.md) says what each one is and what to answer.

## Next step

Workspace opens by itself when the install finishes, in the same window (on Mac and Linux,
from then on every new terminal opens it). If not, type `workspace` → [First run](first-run.md).
