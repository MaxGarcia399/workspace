"""WORKSPACE · lang/en/atajos — SHORTCUTS (keybinds_tui) — remap hub keys.

EN (translation of lang/es/atajos.py). Same keys as `es` (parity test enforces
it). The MENU labels (GitHub/Dev/Calendar/…) are NOT here: they come from
`front.menu_entries`, already translated. See `lang/README.md`.
"""

STRINGS = {
    # ── shared header ─────────────────────────────────────────────────────────
    "atajos.sub": "shortcuts — your quick hub keys",

    # ── hints (top shortcut row + footer): what each key does ─────────────────
    "atajos.hint.action": "action",
    "atajos.hint.remap": "remap",
    "atajos.hint.default": "default",
    "atajos.hint.reset_all": "all to default",
    "atajos.hint.back": "back to menu",
    # CAPTURE-mode hints
    "atajos.cap.newkey": "new key",
    "atajos.cap.assigned": "assigned instantly",
    "atajos.cap.cancel": "cancels",

    # ── right box · CAPTURE mode (the new-key prompt) ─────────────────────────
    "atajos.cap.prompt": "press the new key…",
    "atajos.cap.for": "for «{label}» (now: {k})",
    "atajos.cap.foot": "Esc cancels · saved instantly",

    # ── right box · action detail ─────────────────────────────────────────────
    "atajos.det.custom": "● customized",
    "atajos.det.factory": "factory default",
    "atajos.det.key": "key",
    "atajos.det.default": "default",
    "atajos.det.notecla": "no key — its default «{dflt}» was taken by another "
                          "action; remap it with Enter",
    "atajos.det.how": "how it works",
    "atajos.det.rule1": "Enter remaps: the next key is saved RIGHT away "
                        "(per-machine, doesn't touch your team)",
    "atajos.det.rule2": "one key = one action: if it's already taken I tell "
                        "you who has it — nothing breaks",
    "atajos.det.rule3": "reserved: q · space · Enter · Esc · arrows · Tab · "
                        "t a e x f d n p (other screens)",
    "atajos.det.rule4": "r = default for this action · R twice = all factory "
                        "defaults",
    "atajos.det.saved_in": "saved in {ruta}",

    # ── titles of the two boxes ───────────────────────────────────────────────
    "atajos.box.left": "SHORTCUTS · {grp}",
    "atajos.box.right": "THE KEY · {label}",

    # ── transient messages this screen emits ──────────────────────────────────
    "atajos.msg.cancel": "cancelled — {label} stays on «{k}»",
    "atajos.msg.badkey": "that one won't work — a printable character "
                         "(Enter retries)",
    "atajos.msg.reset_confirm": "R again to restore ALL to defaults",

    # ── panel groups ──────────────────────────────────────────────────────────
    "atajos.group.agents": "agents",
    "atajos.group.menu": "menu",
    "atajos.group.actions": "quick actions",

    # ── action labels (MENU labels come from menu_entries, not here) ──────────
    "atajos.label.agent": "agent {n}",
    "atajos.label.motor": "cycle engine",
    "atajos.label.info": "agent detail",

    # ── action descriptions ───────────────────────────────────────────────────
    "atajos.desc.agent": "aim at agent {n} on the altar WITHOUT launching it "
                         "(engine/info/Enter apply there); the same key again "
                         "— or Enter — launches it",
    "atajos.desc.motor": "change the ENGINE of the aimed agent "
                         "(claude-code/codex/…) without launching it — saved "
                         "per-machine; the next Enter already uses that engine",
    "atajos.desc.info": "shows the aimed agent in one line: effective engine "
                        "(and its origin), where its brain lives and its live "
                        "task — without launching it",

    # ── MENU descriptions (Dev excluded: dev-only, stays Spanish) ─────────────
    "atajos.desc.menu_github": "open your repos: local branch map + "
                               "PRs/issues/releases via gh",
    "atajos.desc.menu_cal": "open the full-screen agenda editor",
    "atajos.desc.menu_tono": "open the personality dials of your agents",
    "atajos.desc.menu_keys": "open this screen — remap any of these keys",
    "atajos.desc.menu_updates": "check · repair · update the harness",
    "atajos.desc.menu_addagent": "create or load a new agent",
}
