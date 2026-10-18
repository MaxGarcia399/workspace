# Uninstall

```bash
workspace uninstall
```

It shows what it's going to delete and asks you to confirm.

- `workspace uninstall --dry-run` — only shows what it would delete; touches nothing.
- `workspace uninstall --keep-folder` — removes everything from your machine but **keeps the
  Workspace folder**.
- `workspace uninstall --clean-all` (or `--limpiar-todo`; it also asks you) — also cleans your
  brains and the engines. See [Also clean brains and engines](#also-clean-brains-and-engines).

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
- The conversations each engine saved. If you choose to also clean the engines, the ones in
  Workspace's OpenClaw and Hermes profiles are moved to a backup folder (see below).
- The engines (Claude Code, Codex, Antigravity) or their logins.

## Also clean brains and engines

By default, what Workspace wrote in your brains and in the engines stays. If you choose to
clean it, it first shows you the exact list and removes **only what Workspace wrote**:

- In each brain: its hooks, bar, permissions and theme in `.claude/settings.local.json`, and
  the `AGENTS.md`/`GEMINI.md` it generated. `CLAUDE.md` and all the brain's content stay.
- Codex: the trust for your brains in `config.toml` and its `workspace-*` themes.
- Antigravity: your brains, their rules and the bar in its `settings.json`, and its
  `workspace-*` projects.
- OpenClaw and Hermes: Workspace's own profile **is not deleted**. It is moved whole, with
  its conversations and the provider you connected there, to a folder next to it
  (`<profile>.workspace-respaldo-<date>`). If it can't be moved, it stays where it is. Your
  personal OpenClaw and Hermes are not touched.

Every config file that changes is backed up next to it (`<file>.workspace-respaldo-<date>`),
and anything you edited by hand, or that Workspace didn't write as is (for example, a
`workspace-*` theme without its record), is left as it is.

## Backup and safeguards

- Before deleting it shows the list **WILL BE DELETED / KEPT / BACKUP**, with each brain by name.
- It offers a **backup** of your settings as a zip on your Desktop (`--no-backup` to skip it).
  The backup **doesn't carry your keys or tokens**: paste them again after reinstalling. If
  the backup fails, nothing is deleted.
- Without a terminal to ask you (a script or an agent) it deletes nothing, unless you add
  `--yes`.
- If the Workspace folder is a git checkout with unpublished work (uncommitted changes or
  unpushed commits), it **doesn't delete it**: it uninstalls the rest and tells you what's there.
- It **refuses to delete** a folder that doesn't look like Workspace (missing its own files),
  your home folder, a drive root or a folder that contains a brain. In that case it deletes
  nothing and tells you why.

Reinstalling is the same command as in [Install](install.md); afterwards, load your agents
again with **Add agent**.
