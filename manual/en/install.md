# Install

## Before you start

You need three things:

1. **Python 3.9 or newer.** On Windows the command is `python`; on Mac/Linux, `python3`.
2. **Git.**
3. **At least one engine** installed and logged in with your account: **Claude Code**
   (`claude`), **Codex** (`codex`) or **Antigravity** (`agy`). If you don't have one yet, the
   first run helps you install it.

No `pip install`, nothing else: Workspace has no dependencies.

## macOS / Linux

One command:

```bash
curl -fsSL https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.sh | bash
```

It installs into `~/Desktop/Workspace`. If a folder was already there, it backs it up first.

Prefer to see what you run before running it? Good call. Same thing in two steps:

```bash
git clone https://github.com/MaxGarcia399/workspace.git ~/Desktop/Workspace
python3 ~/Desktop/Workspace/install.py
```

## Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.ps1 -OutFile $env:TEMP\workspace-setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File $env:TEMP\workspace-setup.ps1
```

It installs into `%LOCALAPPDATA%\Workspace`. In two steps, if you'd rather check first:

```powershell
git clone https://github.com/MaxGarcia399/workspace.git "$env:LOCALAPPDATA\Workspace"
python "$env:LOCALAPPDATA\Workspace\install.py"
```

**Don't install it inside OneDrive** (that includes a Desktop or Documents folder that
OneDrive syncs). The installer refuses on purpose: syncing locks files and breaks Workspace.
When it finishes, **open a new terminal** so the `workspace` command shows up (it works in
PowerShell, cmd.exe and the VS Code terminal).

## What the installer touches

Only **your machine**: it adds the `workspace` command, wires the hooks the engines need and
keeps your local settings in `~/.claude/workspace/`. It creates no accounts and sends nothing.

## Next step

Type `workspace` → [First run](first-run.md).
