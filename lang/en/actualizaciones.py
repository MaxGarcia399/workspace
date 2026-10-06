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
    "actualizaciones.hint.back_menu": "back to menu",
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
    "actualizaciones.note.sync": "sync",
    "actualizaciones.note.offline": "no net",

    # ── phase: live ─────────────────────────────────────────────────────────
    "actualizaciones.live.phase_ok": "{fase}: all good ({n} checks)",
    "actualizaciones.live.step_error": "internal step error: {name}: {msg}",

    # ── repo pull (per-repo result) ─────────────────────────────────────────
    "actualizaciones.pull.sync": "managed by Obsidian Sync (git doesn't apply)",
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
    "actualizaciones.chk.available": "{n} update(s) available — «update everything» brings them",
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
    "actualizaciones.sum.ws_new": "WORKSPACE: +{n} new commit(s)",
    "actualizaciones.sum.more": "… and {n} more",
    "actualizaciones.sum.nothing_new": "nothing new from the harness",
    "actualizaciones.sum.available": "↓ {n} available — pick «update everything» to pull them",
    "actualizaciones.sum.uptodate": "✓ up to date with origin (branch {branch})",
    "actualizaciones.sum.cannot_verify": "couldn't verify ({reason})",
    "actualizaciones.sum.next_pending": "each pending item (right) carries its suggested action; the manual ones also get fixed by talking: run `workspace doctor` in the terminal",
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
}
