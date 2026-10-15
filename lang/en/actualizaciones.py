"""WORKSPACE · lang/en/actualizaciones — UPDATES (actualizaciones_tui) — check/repair/update. EN (translation of lang/es/actualizaciones.py).

Module-frontier note: the doctor PHASE titles and their findings
(label/detail/action) are born in `doctor.py` (the engine, shared with the
classic terminal path) and stay Spanish — they are interpolated as {fase} in a
few keys below, out of this screen's scope.
"""

STRINGS = {
    # ── actions (menu): label · tag · description (3 lines) ─────────────────
    "actualizaciones.act.check.label": "check",
    "actualizaciones.act.check.tag": "read-only",
    "actualizaciones.act.check.d1": "Full harness diagnostic: engines, registered brains, hooks, launchers and prerequisites.",
    "actualizaciones.act.check.d2": "Writes and changes NOTHING — you watch each phase run live, and the health table at the end.",
    "actualizaciones.act.check.d3": "Also checks whether an update is available.",
    "actualizaciones.act.repair.label": "check and repair",
    "actualizaciones.act.repair.tag": "fixes what's broken",
    "actualizaciones.act.repair.d1": "The same diagnostic phases, but REPAIRING whatever it finds: stale hooks, launchers, theme, settings.",
    "actualizaciones.act.repair.d2": "Idempotent: running it twice breaks nothing.",
    "actualizaciones.act.repair.d3": "At the end it tells you whether there's an update to pull.",
    "actualizaciones.act.update.label": "update everything",
    "actualizaciones.act.update.tag": "recommended",
    "actualizaciones.act.update.d1": "Pulls what's new from the harness AND from every registered brain (each repo on its current branch) and repairs at the end.",
    "actualizaciones.act.update.d2": "Safe: dirty repo / no network → warns and moves on to the rest.",
    "actualizaciones.act.update.d3": "At the end: a summary of what arrived and what's still pending.",

    # ── fine print (how it works) ───────────────────────────────────────────
    "actualizaciones.fine.1": "nothing is deleted: it only checks, rewires or pulls commits",
    "actualizaciones.fine.2": "run it whenever you like — it's idempotent",
    "actualizaciones.fine.3": "every step shows live; at the end, a summary and pending items",

    # ── subtitles (screen header) ───────────────────────────────────────────
    "actualizaciones.sub.menu": "updates — check · repair · update",
    "actualizaciones.sub.run": "updates — {label} · in progress",
    "actualizaciones.sub.done": "updates — {label} · result",

    # ── box titles ──────────────────────────────────────────────────────────
    "actualizaciones.box.left": "UPDATES",
    "actualizaciones.box.what": "WHAT IT DOES · {label}",
    "actualizaciones.box.steps": "STEPS · {label}",
    "actualizaciones.box.live": "LIVE",
    "actualizaciones.box.summary": "SUMMARY · {label}",
    "actualizaciones.box.pending_n": "PENDING · {n}",
    "actualizaciones.box.pending": "PENDING",

    # ── section headers (dividers) ──────────────────────────────────────────
    "actualizaciones.sec.state": "status",
    "actualizaciones.sec.on_confirm": "on confirm",
    "actualizaciones.sec.how": "how it works",
    "actualizaciones.sec.progress": "progress",
    "actualizaciones.sec.latest": "latest",
    "actualizaciones.sec.arrived": "what arrived",
    "actualizaciones.sec.update": "update",
    "actualizaciones.sec.next": "next",

    # ── hints (what each key does) ──────────────────────────────────────────
    "actualizaciones.hint.action": "action",
    "actualizaciones.hint.run": "run",
    "actualizaciones.hint.direct": "direct",
    "actualizaciones.hint.auto": "automatic yes/notify/no",
    "actualizaciones.auto.line": "updates {mode} · a changes it",
    "actualizaciones.msg.auto_set": "done: updates {mode}",
    "actualizaciones.msg.auto_env": "WORKSPACE_NO_AUTOUPDATE=1 is set in your terminal and wins: remove it to choose here",
    "actualizaciones.msg.auto_fail": "could not save the setting ({err})",
    "actualizaciones.hint.back_menu": "back",
    "actualizaciones.hint.cancel_run": "cancels after the current step finishes",
    "actualizaciones.hint.scroll_pending": "scroll pending",
    "actualizaciones.hint.enter_q": "Enter or q",

    # ── menu detail (on confirm) ────────────────────────────────────────────
    "actualizaciones.detail.runs_here": "runs right here — you'll see every step live",
    "actualizaciones.detail.equiv": "terminal equivalent: ",

    # ── update check (menu status line) ─────────────────────────────────────
    "actualizaciones.chk.searching": "checking for updates…",
    "actualizaciones.chk.new": "↓ {n} new — «update everything» brings them",
    "actualizaciones.chk.uptodate": "✓ up to date with origin",
    "actualizaciones.chk.branch": "(branch {branch})",
    "actualizaciones.chk.unverified": "unverified: {reason}",

    # ── version ─────────────────────────────────────────────────────────────
    "actualizaciones.ver.unavailable": "version unavailable",

    # ── LIVE view ───────────────────────────────────────────────────────────
    "actualizaciones.live.preparing": "preparing…",
    "actualizaciones.live.starting": "starting…",
    "actualizaciones.run.steps_auto": "the steps run on their own",
    "actualizaciones.steps.before": "↑ {n} step(s) above",
    "actualizaciones.steps.after": "↓ {n} more step(s)",

    # ── plan steps (labels) ─────────────────────────────────────────────────
    "actualizaciones.step.fetch": "fetch {label}",
    "actualizaciones.step.check_update": "check for updates",
    "actualizaciones.repo.brain": "brain {name}",

    # ── worktree notice ─────────────────────────────────────────────────────
    "actualizaciones.aviso.worktree": "WORKSPACE is a git worktree — repair disabled (diagnostics only)",

    # ── step notes (short badge) ────────────────────────────────────────────
    "actualizaciones.note.fixed": "{n} fixed",
    "actualizaciones.note.uptodate": "up to date",
    "actualizaciones.note.sync": "local",
    "actualizaciones.note.offline": "no net",

    # ── phase: live ─────────────────────────────────────────────────────────
    "actualizaciones.live.phase_ok": "{fase}: all good ({n} checks)",
    "actualizaciones.live.step_error": "internal step error: {name}: {msg}",

    # ── repo pull (per-repo result) ─────────────────────────────────────────
    "actualizaciones.pull.sync": "local folder (not updated via git)",
    "actualizaciones.pull.brain_unresolved": "brain not resolved — fix it with «check and repair»",
    "actualizaciones.pull.not_git": "not a git repo (sync install) — no auto-update",
    "actualizaciones.pull.no_remote": "no remote configured — nothing to pull",
    "actualizaciones.pull.dirty": "uncommitted local changes — won't pull over them; commit/save and retry",
    "actualizaciones.pull.no_tracking": "branch '{branch}' doesn't track origin",
    "actualizaciones.pull.offline": "no connection to origin — left as is",
    "actualizaciones.pull.divergent": "divergent history — resolve it by hand (git pull --ff-only)",
    "actualizaciones.pull.failed": "the pull failed",
    "actualizaciones.pull.updated": "updated: +{n} commit(s) → {new} (branch {branch})",
    "actualizaciones.pull.uptodate": "already up to date (branch {branch})",

    # ── final check (check/repair) ──────────────────────────────────────────
    "actualizaciones.chk.available": "a new version is out — «update» brings it",
    "actualizaciones.chk.harness_uptodate": "harness up to date with origin (branch {branch})",
    "actualizaciones.chk.cannot_verify": "couldn't verify updates ({reason})",

    # ── «no update» reasons (interpolated as {reason}) ──────────────────────
    "actualizaciones.reason.not_git": "not a git repo (sync install)",
    "actualizaciones.reason.no_remote": "no remote configured",
    "actualizaciones.reason.branch_undeterminable": "branch undeterminable",
    "actualizaciones.reason.offline": "no connection to origin",
    "actualizaciones.reason.no_data": "no data",

    # ── verdict (result) ────────────────────────────────────────────────────
    "actualizaciones.verdict.error": "✗ something broke: {err}",
    "actualizaciones.verdict.cancelled": "— cancelled; what ran stays applied",
    "actualizaciones.verdict.fails": "✗ {n} item(s) need action",
    "actualizaciones.verdict.warns": "⚠ {n} warning(s) — nothing broken, review them when you can",
    "actualizaciones.verdict.ok": "✓ all in order",

    # ── summary ─────────────────────────────────────────────────────────────
    "actualizaciones.sum.fixed_word": "fixed",
    "actualizaciones.sum.duration": "took {dur} · {n} steps",
    "actualizaciones.sum.ws_new": "{n} changes arrived",
    "actualizaciones.sum.more": "… and {n} more",
    "actualizaciones.sum.nothing_new": "nothing new",
    "actualizaciones.sum.available": "↓ a new version is out — in the menu: «update»",
    "actualizaciones.sum.uptodate": "✓ up to date",
    "actualizaciones.sum.cannot_verify": "couldn't verify ({reason})",
    "actualizaciones.sum.next_pending": "each pending item (right) carries its suggested action; to repair the automatic ones run `workspace doctor` in the terminal",
    "actualizaciones.sum.next_clear": "nothing to do — keep working",

    # ── pending panel ───────────────────────────────────────────────────────
    "actualizaciones.pend.error_cmd": "run `workspace doctor` in the terminal",
    "actualizaciones.pend.none": "✓ none — all green",
    "actualizaciones.pend.more": "… ↓ {n} more line(s)",

    # ── transition messages (footer) ────────────────────────────────────────
    "actualizaciones.msg.cancelling": "cancelling — the current step finishes on its own…",
    "actualizaciones.msg.done_pending": "{label} done — {n} pending item(s) noted",
    "actualizaciones.msg.done_ok": "{label} done ✓",
    "actualizaciones.msg.done_fallback": "done",

    # ── backup submenu (when actualizaciones_tui is unavailable) ─────────────
    "actualizaciones.fallback.header": "Updates",
    "actualizaciones.fallback.q": "— what do you want to do?",
    "actualizaciones.fallback.o1": "Check only",
    "actualizaciones.fallback.o1d": "— diagnosis, touches nothing",
    "actualizaciones.fallback.o2": "Check and repair",
    "actualizaciones.fallback.o2d": "— fixes hooks, launchers, theme…",
    "actualizaciones.fallback.o3": "Update everything",
    "actualizaciones.fallback.o3d": "— pulls what's new + repairs (recommended)",
    "actualizaciones.fallback.back": "Back",
    "actualizaciones.fallback.prompt": "Option [1]:",
    # ── actualizador con red de seguridad (updater.py) ──
    "actualizaciones.pull.updated_version": "updated to v{v} (+{n} change(s))",
    "actualizaciones.pull.rolled_back": "the new version didn't start here: went back to the previous one (nothing for you to do)",
    "actualizaciones.pull.held": "version pinned: the latest didn't start here and there's no newer one yet",
    "actualizaciones.note.new_version": "new version",
    "actualizaciones.live.new_doctor_ok": "check with the new version: all good",
    "actualizaciones.live.new_doctor_warn": "the new version found pending items: run `workspace doctor` to see them",
    "actualizaciones.pull.paused_manual": "you went back to the previous version: the new one stays paused until a newer one",

    # ── rediseño 2026-10-14: la cajita (menú, en curso, resultado, `i`) ─────
    "actualizaciones.o.update": "update",
    "actualizaciones.o.update_to": "update to v{v}",
    "actualizaciones.o.repair": "check and repair",
    "actualizaciones.o.check": "check only",
    "actualizaciones.o.rollback": "go back to v{v}",
    "actualizaciones.o.rollback_confirm": "Enter again: back to v{v} · nothing deleted",
    "actualizaciones.o.recheck": "check again",
    "actualizaciones.o.auto": "automatic",
    "actualizaciones.auto.v.auto": "yes",
    "actualizaciones.auto.v.notify": "notify only",
    "actualizaciones.auto.v.off": "off",
    "actualizaciones.f.version": "version",
    "actualizaciones.f.state": "status",
    "actualizaciones.st.searching": "checking…",
    "actualizaciones.st.new": "new version available",
    "actualizaciones.st.new_v": "new version: v{v}",
    "actualizaciones.st.uptodate": "✓ up to date",
    "actualizaciones.st.unverified": "not verified · {reason}",
    "actualizaciones.st.held": "the new one is paused (you went back)",
    "actualizaciones.k.pick": "pick",
    "actualizaciones.k.apply": "apply",
    "actualizaciones.k.info": "how it works",
    "actualizaciones.k.back": "back",
    "actualizaciones.k.scroll": "scroll",
    "actualizaciones.k.confirm": "confirm",
    "actualizaciones.k.cancel": "cancel",
    "actualizaciones.box.running": "{label} · RUNNING",
    "actualizaciones.box.result": "{label} · RESULT",
    "actualizaciones.sec.pending": "pending",
    "actualizaciones.sec.pending_n": "pending · {n}",
    "actualizaciones.msg.rollback_ok": "done: v{v} is back · Workspace reopens with it when you leave",
    "actualizaciones.msg.rollback_fail": "couldn't go back: {reason}",
    "actualizaciones.msg.rollback_cancel": "cancelled · nothing changed",
    "actualizaciones.info.title": "HOW UPDATES WORK",
    "actualizaciones.info.detail": "detail",
    "actualizaciones.info.h_now": "your version",
    "actualizaciones.info.h_how": "how a new version arrives",
    "actualizaciones.info.n1": "fetches what's new",
    "actualizaciones.info.c1": "only moves forward; never touches your changes",
    "actualizaciones.info.n2": "checks it starts",
    "actualizaciones.info.c2": "here, on your machine",
    "actualizaciones.info.n3": "applies the adjustments",
    "actualizaciones.info.c3": "with a backup",
    "actualizaciones.info.p1": "If the new version doesn't start on your machine, Workspace goes back on its own to the one you had and pins it until we publish a newer one: you're never left unable to use it.",
    "actualizaciones.info.p2": "What changes is the program. Your agents, their brains and your settings aren't touched; if a version needs to adjust something, it does it with a backup and logs it.",
    "actualizaciones.info.h_opts": "the options",
    "actualizaciones.info.o_update": "fetches the new version, then checks and repairs; only shows up when there is one",
    "actualizaciones.info.o_repair": "checks the essentials (agents, hooks, commands, engine) and fixes what's broken; run it whenever you want",
    "actualizaciones.info.o_check": "the same, without changing anything: it only tells you what it found",
    "actualizaciones.info.k_rollback": "go back",
    "actualizaciones.info.o_rollback": "returns to the version you had before the last update and pins it; only shows up when there is one to go back to",
    "actualizaciones.info.o_auto": "yes: updates itself when you open an agent, with the safety net · notify only: tells you a new version is out · off: only when you ask",
    "actualizaciones.info.h_cmds": "the same from the terminal",
    "actualizaciones.info.c_update": "update",
    "actualizaciones.info.c_repair": "check and repair",
    "actualizaciones.info.c_check": "check only",
    "actualizaciones.info.c_rollback": "go back to the previous one",
}
