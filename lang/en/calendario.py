"""WORKSPACE · lang/en/calendario — the CALENDAR editor (calendario_tui). EN.

Translation of lang/es/calendario.py. Months/days come from `common.cal.*`
(not redefined here). Kept short to respect the TUI width rule."""

STRINGS = {
    # ── screen subtitle (shared header) ─────────────────────────────────────
    "cal.subtitle": "calendar",

    # ── box / section titles ────────────────────────────────────────────────
    "cal.box.month_title": "MONTH · {month} {year}",
    "cal.box.day": "DAY",
    "cal.box.upcoming": "UPCOMING",
    "cal.box.overdue": "OVERDUE · {n}",
    "cal.overdue.more": "+{n} more — open the day with ◄► or check off with x",
    "cal.box.trash": "TRASH · {n} events",
    "cal.box.queue": "AGENT QUEUE · {n} ready",
    "cal.box.idea": "IDEA / DESCRIPTION",
    "cal.box.prompt": "PROMPT FOR THE AGENT",
    "cal.box.ficha": "CARD · {date} · {kind}",

    # ── task status (card badge) ────────────────────────────────────────────
    "cal.status.draft": "DRAFT",
    "cal.status.ready": "READY",
    "cal.status.in_progress": "IN PROGRESS",
    "cal.status.blocked": "BLOCKED",
    "cal.status.done": "DONE",

    # ── month-grid legend ───────────────────────────────────────────────────
    "cal.legend.due": "due",
    "cal.legend.overdue": "overdue",
    "cal.legend.done": "done",

    # ── DAY header ──────────────────────────────────────────────────────────
    "cal.day.header": "{dow}, {month} {day}",
    "cal.day.today": "· today",
    "cal.day.none": "no events this day",
    "cal.day.add_hint": "add one here",
    "cal.day.notes_more": "… {n} more — Enter opens the detail",

    # ── MOVE mode ───────────────────────────────────────────────────────────
    "cal.move.title": "Move: {title}",
    "cal.move.dest": "Target: {date}",
    "cal.move.arrows": "Arrows: day · n/p: month · t: today",
    "cal.move.confirm": "Enter moves · Esc cancels",

    # ── trash ───────────────────────────────────────────────────────────────
    "cal.trash.intro": "Deleted items can be restored for 15 days.",
    "cal.trash.empty": "Trash empty",
    "cal.trash.row": "{mark} {date} · {title} · {n}d",

    # ── agent queue ─────────────────────────────────────────────────────────
    "cal.queue.intro": "Only tasks marked READY; high priority, then date.",
    "cal.queue.empty": "No ready tasks; l switches draft to ready.",

    # ── editor mini-calendar (card context) ─────────────────────────────────
    "cal.ctx.day": "DAY · {date}",
    "cal.ctx.none": "No cards; a creates one here",

    # ── text-field placeholders ─────────────────────────────────────────────
    "cal.panel.idea_ph": "Describe what you want to achieve and the context.",
    "cal.panel.prompt_ph": "Say how the agent should work.",

    # ── card (new / edit / detail) ──────────────────────────────────────────
    "cal.ficha.kind_detail": "detail",
    "cal.ficha.kind_new": "new",
    "cal.ficha.kind_edit": "editing",
    "cal.ficha.queue_count": "{n} ready for agents",
    "cal.ficha.title_field": "title · optional time at the start",
    "cal.ficha.result": "Result: {text}",

    # ── key actions (hints) ─────────────────────────────────────────────────
    "cal.hint.day": "day",
    "cal.hint.detail": "detail",
    "cal.hint.add": "add",
    "cal.hint.list": "list",
    "cal.hint.queue": "queue",
    "cal.hint.month": "month",
    "cal.hint.today": "today",
    "cal.hint.trash": "trash",
    "cal.hint.switch": "switch",
    "cal.hint.edit": "edit",
    "cal.hint.done": "done",
    "cal.hint.ready_draft": "ready/draft",
    "cal.hint.delete": "delete",
    "cal.hint.restore": "restore",
    "cal.hint.back": "back",
    "cal.hint.to_draft": "back to draft",
    "cal.hint.text": "text",
    "cal.hint.card": "card",
    "cal.hint.open": "open",
    "cal.hint.new": "new",
    "cal.hint.calendar": "calendar",
    "cal.hint.field": "field",
    "cal.hint.scroll": "scroll",
    "cal.hint.save": "save",
    "cal.hint.newline": "newline",
    "cal.hint.cancel": "cancel",
    "cal.hint.attach": "image",
    "cal.hint.detach": "drop img",

    # ── attached images (Ctrl+V attaches · Ctrl+X removes) ──────────────────
    "cal.img.chip": "img",
    "cal.img.label": "{n} img",
    "cal.img.count": "{n} images",
    "cal.img.attached": "image attached ✓ — the agent will see it",
    "cal.img.removed": "image removed",
    "cal.img.none": "no images in this field",
    "cal.img.none_clip": "no image in the clipboard — paste the file path",
    "cal.img.bad": "not a valid image (png/jpg/gif/webp)",
    "cal.img.classic_head": "Drag the image onto the terminal and paste its path (empty Enter = cancel):",
    "cal.img.classic_cancel": "no image attached",
    "cal.img.need_save": "type a title to attach the image",
    "cal.img.save_fail": "could not attach the image",
    "cal.img.unavailable": "attaching images is not available here",

    # ── statusline messages (S["msg"]) ──────────────────────────────────────
    "cal.msg.g_readonly": "Google event — read-only",
    "cal.msg.g_readonly_edit": "Google event — read-only (edit it there)",
    "cal.msg.g_readonly_delete": "Google event — read-only (delete it there)",
    "cal.msg.g_readonly_move": "Google event — read-only (move it there)",
    "cal.msg.g_no_done": "Google event — not checked off (not a local task)",
    "cal.msg.task_gone": "the task is no longer available",
    "cal.msg.now_ready": "READY for an agent to pick up",
    "cal.msg.now_draft": "DRAFT — out of the queue",
    "cal.msg.ready_fail": "no change: task in progress or save error",
    "cal.msg.save_fail": "couldn't save it",
    "cal.msg.done_ok": "done ✓ — still here, struck through (x revives it)",
    "cal.msg.pending_again": "pending again",
    "cal.msg.prio_high": "HIGH priority — goes first",
    "cal.msg.prio_normal": "normal priority",
    "cal.msg.trashed": "in trash 15 days: {title}",
    "cal.msg.delete_fail": "couldn't delete it",
    "cal.msg.move_cancelled": "move cancelled",
    "cal.msg.moved": "moved to {date}",
    "cal.msg.move_fail": "couldn't move it; the event keeps its date",
    "cal.msg.restored": "restored: {title}",
    "cal.msg.restore_fail": "couldn't restore it",
    "cal.msg.need_title": "type a title; your content stays here",
    "cal.msg.save_lost": "not saved; your fields stay here",
    "cal.msg.saved": "saved; l marks it READY for an agent",
    "cal.msg.cancelled": "cancelled",
    "cal.msg.char_limit": "{n}-character limit; save or trim the text",
    "cal.msg.no_task_mark": "no task to mark",
    "cal.msg.no_move_here": "no event to move here",
    "cal.msg.no_edit_here": "no event to edit on this day",
    "cal.msg.no_done_here": "nothing to check off here",
    "cal.msg.no_delete_here": "nothing to delete here",

    # ── Google Calendar accounts (multi-account view, key g) ─────────────────
    "cal.hint.google": "Google",
    "cal.g.subtitle": "google calendar accounts",
    "cal.g.box": "GOOGLE CALENDAR ACCOUNTS",
    "cal.g.none": "none yet — connect your first calendar with a",
    "cal.g.future": "Coming soon: two-way (OAuth) accounts to edit from here.",
    "cal.g.kind.ical": "iCal · read-only",
    "cal.g.kind.oauth": "two-way",
    # account state
    "cal.g.state.ok": "connected",
    "cal.g.state.error": "invalid URL",
    "cal.g.state.nofetch": "not fetched yet",
    "cal.g.row.events": "{n} events",
    "cal.g.row.env": "from system",
    "cal.g.row.sync": "sync {ago}",
    # CONNECT flow (step by step)
    "cal.g.add.title": "CONNECT A GOOGLE CALENDAR",
    "cal.g.add.steps_head": "To get the secret address in iCal format:",
    "cal.g.add.step1": "1. Open Google Calendar on the web",
    "cal.g.add.step2": "2. Go to Settings (the gear, top right)",
    "cal.g.add.step3": "3. Under «Settings for my calendars» pick the calendar",
    "cal.g.add.step4": "4. Open «Integrate calendar»",
    "cal.g.add.step5": "5. Copy the «Secret address in iCal format»",
    "cal.g.add.name_field": "name (e.g. Work)",
    "cal.g.add.url_field": "secret iCal address · pasted hidden",
    "cal.g.add.url_empty": "paste the URL here — not shown on screen",
    "cal.g.add.url_pasted": "{n} characters pasted",
    # RENAME flow
    "cal.g.rename.title": "RENAME ACCOUNT",
    "cal.g.rename.field": "new name",
    # REMOVE confirmation
    "cal.g.confirm.title": "REMOVE THIS ACCOUNT?",
    "cal.g.confirm.body": "Unlinks «{label}»; its events stop showing.",
    "cal.g.confirm.note": "Deletes nothing in Google; you can reconnect it.",
    # view hints
    "cal.g.hint.add": "connect",
    "cal.g.hint.remove": "remove",
    "cal.g.hint.rename": "rename",
    "cal.g.hint.connect": "connect",
    "cal.g.hint.confirm": "confirm",
    # this view's statusline messages (S["g_msg"])
    "cal.g.msg.connected": "connected ✓ · {n} events",
    "cal.g.msg.not_https": "that's not an https Google URL",
    "cal.g.msg.duplicate": "that account is already linked",
    "cal.g.msg.fetch_failed": "couldn't fetch the calendar (network or revoked URL?)",
    "cal.g.msg.save_failed": "couldn't save it",
    "cal.g.msg.need_url": "paste the iCal address first",
    "cal.g.msg.removed": "unlinked: {label}",
    "cal.g.msg.renamed": "renamed: {label}",
    "cal.g.msg.rename_empty": "the name can't be empty",
    "cal.g.msg.env": "system account (variable {var}) — manage it there",
    "cal.g.msg.none_sel": "no account selected",
}
