"""WORKSPACE · lang/en/uninstall — uninstaller (uninstall.py): guards, plan
(what is deleted / what is kept) and backup."""

STRINGS = {
    "uninstall.ask_backup": "Create the backup before deleting? [Y/n]: ",
    "uninstall.ask_sure": "Sure? type 'yes' to continue: ",
    "uninstall.backup_fail": "Could not create the backup ({e}). Nothing was deleted. "
                             "To continue without one: --no-backup.",
    "uninstall.backup_ok": "backup created: {p} (it holds your settings and local credentials: keep it private)",
    "uninstall.backup_where": "Your backup: {p}",
    "uninstall.cancelled": "Cancelled. Nothing was deleted.",
    "uninstall.dry_backup": "would create the backup: {p}",
    "uninstall.guard.brain": "it contains the brain “{n}” ({b})",
    "uninstall.guard.home": "it is your home folder (or contains it)",
    "uninstall.guard.no_app": "it is not the Workspace app",
    "uninstall.guard.no_harness": "it lacks Workspace's markers (front.py, dispatch.py, "
                                  "install.py)",
    "uninstall.guard.no_state": "it has no Workspace state file",
    "uninstall.guard.notdir": "it is not a folder",
    "uninstall.guard.relative": "it is not an absolute path",
    "uninstall.guard.root": "it is a drive root",
    "uninstall.hint_folder": "If it's another folder: --workspace <path>. To uninstall "
                             "without touching it: --keep-folder.",
    "uninstall.kept_inside": "kept: {p}",
    "uninstall.label.state": "per-machine state",
    "uninstall.label.state_item": "state",
    "uninstall.no_root": "harness folder not found at {p} (nothing to delete there; use "
                         "--workspace <path> if it lives elsewhere)",
    "uninstall.nothing": "Nothing was deleted.",
    "uninstall.plan.app": "desktop app: {p}",
    "uninstall.plan.backup": "BACKUP",
    "uninstall.plan.backup_to": "per-machine state → {p} (without your keys or tokens: paste them again after reinstalling)",
    "uninstall.plan.brain": "brain “{n}”: {b}",
    "uninstall.plan.brains": "your brains (agent folders), wherever they are",
    "uninstall.plan.cc_settings": "your ~/.claude/settings.json (only the keys Workspace "
                                  "added are removed)",
    "uninstall.plan.delete": "WILL BE DELETED",
    "uninstall.plan.engines": "each engine's conversations and logins (Claude Code, "
                              "Codex, …) and the engines themselves",
    "uninstall.plan.engines_clean": "the conversations of Workspace's profiles in OpenClaw "
                                    "and Hermes, in a backup folder next to each profile "
                                    "(see below)",
    "uninstall.plan.harness": "harness folder: {p}",
    "uninstall.plan.harness_kept": "harness folder (--keep-folder): {p}",
    "uninstall.plan.keep": "KEPT (untouched)",
    "uninstall.plan.no_backup": "no backup (--no-backup)",
    "uninstall.plan.nothing_to_backup": "nothing to back up (no state)",
    "uninstall.plan.state": "per-machine state (settings, shortcuts, registered agents): {p}",
    "uninstall.plan.tbackup": "transcripts backup: {p}",
    "uninstall.plan.themes": "Workspace themes in ~/.claude/themes",
    "uninstall.plan.launchers": "in ~/.local/bin, only these (they carry the installer's "
                                "mark): {n}",
    "uninstall.plan.theme_files": "in ~/.claude/themes, only these (Workspace generated "
                                  "them): {n}",
    "uninstall.plan.unix": "the `workspace` command and launchers in ~/.local/bin; "
                           "Workspace blocks in ~/.zshrc",
    "uninstall.plan.win": "Workspace commands in your PowerShell $PROFILE",
    "uninstall.refused": "Refusing to delete {p}: {why}.",
    "uninstall.usage": "usage: python3 uninstall.py [--dry-run] [--keep-folder] [--workspace <path>]\n"
                       "                            [--yes|-y] [--backup|--no-backup] [--clean-all]\n"
                       "  Uninstalls Workspace from this machine; your brains and conversations stay.\n"
                       "  --dry-run shows what it would delete, without touching anything.\n"
                       "  --clean-all also removes what Workspace wrote in brains and engines.",
    "uninstall.x.rm_path.1": "would delete {label}: {p}",
    "uninstall.x.rm_path.2": "{dim}couldn't delete {p} ({e}){r}",
    "uninstall.x.strip_zshrc.1": "would clean the WORKSPACE blocks from {rc}",
    "uninstall.x.strip_zshrc.2": "~/.zshrc cleaned (PATH + WORKSPACE greeter)",
    "uninstall.x.strip_profile_windows.1": "would clean the WORKSPACE markers from {prof}",
    "uninstall.x.strip_profile_windows.2": "$PROFILE cleaned (WORKSPACE markers): {prof}",
    "uninstall.x.reset_theme.1": "would remove theme={th} from ~/.claude/settings.json",
    "uninstall.x.reset_theme.2": "theme {th} removed from ~/.claude/settings.json",
    "uninstall.x.restore_retention.1": "would restore cleanupPeriodDays={prior!r} in {sp}",
    "uninstall.x.restore_retention.2": "cleanupPeriodDays restored ({v})",
    "uninstall.x.main.1": "\n  {b}{c}WORKSPACE uninstaller{r}  {dim}· {v} · {root}{r}",
    "uninstall.x.main.2": "desktop app",
    "uninstall.x.main.3": "{dim}harness folder kept (--keep-folder): {root}{r}",
    "uninstall.x.main.4": "{dim}warning: {root} doesn't look like a WORKSPACE harness (no front.py/dispatch.py/install.py) — I WON'T delete the folder. Use --workspace <path> if it's another one.{r}",
    "uninstall.x.main.5": "harness folder",
    "uninstall.x.main.6": "\n  {c}Done.{r} WORKSPACE uninstalled from this machine.",
    "uninstall.x.main.7": "  {dim}The BRAINS (agent folders) and transcripts were NOT touched.{r}",
    "uninstall.x.main.8": "  {dim}Open a NEW terminal to drop the old PATH/greeter.{r}",
    "uninstall.x.main.9": "  {dim}If you reinstall Workspace, load each agent again (Add agent → load its folder) so it points to the new install; if you restored your backup, `workspace doctor` is enough.{r}",
    "uninstall.x.rm_path.4": "some files are still in use",
    "uninstall.x.rm_path.3": "{label} deleted: {p}",
    "uninstall.x.no_value": "no value",
    "uninstall.x.ps_cmds": "PowerShell commands",
    "uninstall.x.theme": "theme {n}",
    # git checkout with unpublished work · no terminal (B02)
    "uninstall.git.no_git": "couldn't check whether it has unpublished work (git isn't installed)",
    "uninstall.git.fail": "couldn't check with git whether it has unpublished work ({e})",
    "uninstall.git.changes": "{n} uncommitted change(s)",
    "uninstall.git.commits": "{n} unpushed commit(s)",
    "uninstall.git.stashes": "{n} saved stash(es)",
    "uninstall.plan.harness_git": "harness folder: {p} — it's a git checkout with unpublished "
                                  "work ({w}); delete it yourself once you've saved it",
    "uninstall.x.main.git": "{dim}harness folder kept: {root} — it has unpublished git work "
                            "({w}).{r}",
    "uninstall.need_yes": "Without an interactive terminal I can't ask you to confirm. Nothing "
                          "was deleted. To uninstall like this, add --yes (and check first what "
                          "would happen with --dry-run).",
    # --limpiar-todo / --clean-all: brains and engines
    "uninstall.clean.ask": "Also clean brains and engines? Only what Workspace wrote in them "
                           "is removed, with a backup next to it. Its OpenClaw and Hermes "
                           "profiles, with your conversations there, are moved to a backup "
                           "folder next to each one. Your brains' content is untouched [y/N]: ",
    "uninstall.clean.title": "ALSO CLEANED (brains and engines: only what Workspace wrote)",
    "uninstall.clean.none": "nothing: no Workspace leftovers in your brains or engines",
    "uninstall.clean.brain": "brain “{n}”: {p}",
    "uninstall.clean.hooks": "Workspace hooks ({k})",
    "uninstall.clean.statusline": "bar (statusLine)",
    "uninstall.clean.perms": "Workspace permissions ({k} rules)",
    "uninstall.clean.theme": "theme {t}",
    "uninstall.clean.pointer": "brain “{n}”: {f} generated by Workspace ({p})",
    "uninstall.clean.codex_trust": "Codex: {p} → trust for {k} brain(s) ([projects.\"…\"])",
    "uninstall.clean.codex_theme": "Codex: theme {p}",
    "uninstall.clean.agy": "Antigravity: {p}",
    "uninstall.clean.agy_trust": "brains in trustedWorkspaces ({k})",
    "uninstall.clean.agy_rules": "brain file rules ({k})",
    "uninstall.clean.agy_memoria": "`workspace memoria …` rules ({k})",
    "uninstall.clean.agy_project": "Antigravity: project {p}",
    "uninstall.clean.openclaw": "OpenClaw: Workspace's profile {p} → moved aside (not "
                                "deleted) to {b}, with its conversations and the provider you "
                                "connected there; your personal OpenClaw is untouched",
    "uninstall.clean.oc_label": "OpenClaw profile",
    "uninstall.clean.hermes": "Hermes: Workspace's profile {p} → moved aside (not deleted) "
                              "to {b}, with its conversations and the provider you connected "
                              "there; your personal Hermes is untouched",
    "uninstall.clean.moved": "{label} moved aside with its conversations (not deleted): "
                             "{p} → {b}",
    "uninstall.clean.bak_exists": "{p} already exists",
    "uninstall.clean.bak_missing": "the backup did not end up in {p}",
    "uninstall.clean.hm_left": "the profile is still there; its copy is in {b}",
    "uninstall.clean.hm_label": "Hermes profile",
    "uninstall.clean.backups": "every config file that changes is backed up next to it: "
                               "<file>{b}",
    "uninstall.clean.keep": "KEPT WHEN CLEANING",
    "uninstall.clean.keep_claude": "each brain's CLAUDE.md (it is the brain's format: through it "
                                   "Claude Code reads BRAIN.md) and all its content",
    "uninstall.clean.kept_user": "left alone (you edited it or Workspace didn't write "
                                 "it as is): {p}",
    "uninstall.clean.dry": "would clean: {what}",
    "uninstall.clean.done": "cleaned: {p} (backup: {b})",
    "uninstall.clean.fail": "{dim}couldn't clean {p} ({e}){r}",
    "uninstall.clean.final": "  {dim}From the brains and engines only what Workspace wrote was "
                             "removed, with a backup next to it; your brains' content was not "
                             "touched.{r}",
    "uninstall.clean.final_moved": "  {dim}The conversations of {p} are still in {b}{r}",
}
