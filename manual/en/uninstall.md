# Uninstall

```bash
workspace uninstall
```

It shows what it's going to delete and asks you to confirm.

- `workspace uninstall --dry-run` — only shows what it would delete; touches nothing.
- `workspace uninstall --keep-folder` — removes everything from your machine but **keeps the
  Workspace folder**.

## What gets deleted

- The `workspace` command and each agent's command.
- Workspace's local configuration in `~/.claude/workspace/` (settings, shortcuts, chosen
  themes, this machine's state).
- What the installer added to your terminal (PATH and menu-on-open; on Windows, the
  PowerShell profile block).
- The theme it installed inside Claude Code, if it did.
- The Workspace folder (unless `--keep-folder`).

## What is NOT deleted

- **Your agents' brains** (their folders): they're yours and live elsewhere.
- The conversations each engine saved.
- The engines (Claude Code, Codex, Antigravity) or their logins.

## Backup and safeguards

- Before deleting it shows the list **WILL BE DELETED / KEPT / BACKUP**, with each brain by name.
- It offers a **backup** of your settings as a zip on your Desktop (`--no-backup` to skip it).
  The backup **doesn't carry your keys or tokens**: paste them again after reinstalling. If
  the backup fails, nothing is deleted.
- It **refuses to delete** a folder that doesn't look like Workspace (missing its own files),
  your home folder, a drive root or a folder that contains a brain. In that case it deletes
  nothing and tells you why.

Reinstalling is the same command as in [Install](install.md); afterwards, load your agents
again with **Add agent**.
