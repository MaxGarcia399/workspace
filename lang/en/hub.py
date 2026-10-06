"""WORKSPACE · lang/en/hub — the HUB: menu, LANGUAGE box and all shared hub
«chrome» of the `clasico`/`centro`/`dia` layouts + the tall window. EN."""

STRINGS = {
    # ── hub menu (front.menu_entries) ───────────────────────────────────────
    "menu.github.label": "GitHub",
    "menu.github.tag": "your repos: local branches + PRs, issues and releases",
    "menu.cal.label": "Calendar",
    "menu.cal.tag": "your day's agenda, editable full-screen",
    "menu.tono.label": "Tone",
    "menu.tono.tag": "the personality dials for your agents",
    "menu.keybinds.label": "Shortcuts",
    "menu.keybinds.tag": "remap the hub's quick keys",
    "menu.updates.label": "Updates",
    "menu.updates.tag": "check · repair · update",
    "menu.add_agent.label": "Add agent",
    "menu.add_agent.tag": "create or load an agent",
    "menu.shell.label": "Normal terminal",
    "menu.shell.tag": "your usual shell · key q",

    # ── hub LANGUAGE box ────────────────────────────────────────────────────
    "hub.idioma.hint": "Enter switches",

    # ── SECTION TITLES (uppercase) ──────────────────────────────────────────
    "hub.section.gods": "AGENTS",
    "hub.section.agents": "AGENTS",
    "hub.section.menu": "MENU",
    "hub.section.personalization": "PERSONALIZATION",
    "hub.section.settings": "THEMES & SETTINGS",
    "hub.section.today": "TODAY",
    "hub.section.tone": "TONE",
    "hub.section.branches": "BRANCHES",
    "hub.section.details": "DETAILS",
    "hub.section.activity": "ACTIVITY",
    "hub.section.monitor_live": "MONITOR · live",
    "hub.section.lang": "IDIOMA · LANGUAGE",
    "hub.section.configs": "SETTINGS",
    "hub.section.calendar": "CALENDAR",
    "hub.section.upcoming": "upcoming",
    # titles with counter/name
    "hub.title.agents_n": "AGENTS · {n}",
    "hub.title.branches_n": "BRANCHES · {n}",
    "hub.title.tone_named": "TONE · {name}",

    # ── subtitle/build ──────────────────────────────────────────────────────
    "hub.build.control_center": "control center",

    # ── empty ───────────────────────────────────────────────────────────────
    "hub.empty.agents": "no agents — MENU ▸ Add agent",

    # ── SETTINGS / pins ─────────────────────────────────────────────────────
    "hub.cfg.enter_changes": "Enter changes",
    "hub.cfg.pick_change": "◄► pick · Enter/space change",
    "hub.cfg.config_edit": "Config ▸ to edit",
    "hub.pin.background": "bg",
    "hub.pin.theme": "theme",
    "hub.pin.layout": "layout",
    "hub.pin.heartbeat": "heartbeat",
    "hub.pin.split": "split",
    "hub.pin.stars": "stars",
    "hub.pin.anim": "anim",

    # ── instrument bar / monitor (centro) ───────────────────────────────────
    "hub.instr.usage5h": "5h use",
    "hub.instr.paused": "PAUSED",
    "hub.instr.cap": "cap",
    "hub.monitor.budget": "budget",
    "hub.monitor.commits": "commits",
    "hub.monitor.peak": "peak",
    "hub.monitor.tile.branches": "branches",
    "hub.monitor.tile.wt": "wt",
    "hub.monitor.tile.queue": "queue",
    "hub.monitor.tile.agents": "agents",
    "hub.act.bus_n": "bus {n}",
    "hub.act.git_n": "git {n}",
    "hub.act.pending": "· pending",

    # ── heartbeat (hb_brief / latido_lines) ─────────────────────────────────
    "hub.hb.brief": "heartbeat {mode} · queue {count} · 5h use {uso}",
    "hub.hb.budget_paused": " · budget paused",
    "hub.hb.queue": "queue {n}",
    "hub.hb.usage5h": "5h use {uso}",
    "hub.hb.paused": "budget paused",

    # ── DETAILS panel (centro) ──────────────────────────────────────────────
    "hub.det.idle_notask": "○ idle · no task published",
    "hub.det.soon": "· soon",
    "hub.det.bus_pending": "bus {n} pending",
    "hub.det.missions": "missions",

    # ── OPERATIONS strip (centro) ───────────────────────────────────────────
    "hub.strip.missions": "missions",
    "hub.strip.energy": "energy",
    "hub.strip.warn_one": "warning",
    "hub.strip.warn_many": "warnings",

    # ── TONE (dia mini-panel): group headers ────────────────────────────────
    "hub.tono.group.manner": "manner",
    "hub.tono.group.form": "form",
    "hub.tono.group.work": "work",

    # ── mini calendar (dia TODAY panel) ─────────────────────────────────────
    "hub.cal.nothing": "nothing",
    "hub.cal.due": "▪ due",
    "hub.cal.allday": "all day",
    "hub.cal.overdue_one": "overdue",
    "hub.cal.overdue_many": "overdue",
    "hub.cal.nothing_more": "nothing more",
    "hub.cal.nothing_today": "nothing this day",
    "hub.cal.add_hint": "start with 18:00 to set a time  ·  "
                        "Enter saves  ·  Esc cancels",
    "hub.cal.more_n": "+{n} more",
    "hub.cal.enter_add": "Enter adds an event here",
    "hub.date.week": "week",
    "hub.date.day": "day",

    # ── selected agent row (_dia_sel_rows) ──────────────────────────────────
    "hub.sel.last": "last",
    "hub.sel.last_when": "last · {when}",
    "hub.sel.no_task": "no task",

    # ── version indicator (front._hub_version_text) ─────────────────────────
    "hub.ver.update_available": "update available",
    "hub.ver.uptodate": "up to date",
    "hub.ver.behind_update": "↓{n} update",
    "hub.ver.ahead_unpushed": "↑{n} unpushed",

    # ── banner strip (front._franja) ────────────────────────────────────────
    # classic banner box (banner/render.py — leak: no "del equipo")
    "hub.banner.head": "WORKSPACE · agent OS",
    "hub.banner.foot": "type an agent's name to enter directly · "
                       "workspace for this menu",

    "hub.franja.tag": "WORKSPACE · agent OS",
    "hub.franja.engine": "engine",
    "hub.franja.engine_suffix": " · no API key · sync",
    "hub.franja.engines_n": "{n} engines",

    # ── hero / hub empty-state (front.build_info_rows) ──────────────────────
    "hub.hero.h.harness": "The harness",
    "hub.hero.k.agents": "agents",
    "hub.hero.k.engine": "engine",
    "hub.hero.soon_paren": "(soon)",
    "hub.hero.engine_default": "claude-code · Anthropic (no API key)",
    "hub.hero.engine_per_agent": "  (per agent — key m)",
    "hub.hero.k.brains": "brains",
    "hub.hero.k.autoclose": "auto-close",
    "hub.hero.v.capture": "active session capture",
    "hub.hero.v.config_first": "set up your first agent",
    "hub.hero.h.setup": "Your setup",
    "hub.hero.k.user": "user",
    "hub.hero.k.machine": "machine",
    "hub.hero.k.base": "base",
    "hub.hero.v.base": "installer + workspace doctor ✓",
    "hub.hero.h.howto": "How to enter",
    "hub.hero.k.menu": "menu",
    "hub.hero.v.menu": "pick an agent below ↓",
    "hub.hero.k.direct": "direct",
    "hub.hero.v.direct": "type its name: {name}",
    "hub.hero.agent_generic": "your-agent",

    # ── classic hub (front._classic_block_lines) ────────────────────────────
    "hub.classic.section_hint": "◄ ► pick",
    "hub.classic.pers_hint": "◄ ► pick · Enter/space change",
    "hub.classic.lang_hint": "◄ ► pick · Enter change",
    "hub.classic.engine_prefix": "engine ▸ ",
    "hub.classic.engine_change": "m changes",

    # ── tall/split window (responsive_ui.vertical_hub) ──────────────────────
    "hub.fullscreen_notice": "Full screen: full experience",
    "hub.fullscreen_rec": "Full screen recommended",
    "hub.menu_header.title": "◆ Where do you go?",
    "hub.menu_header.hint": "↑↓ · Enter · q = normal terminal",

    # ── safe / narrow screen (front._narrow_draw) ───────────────────────────
    "hub.narrow.agents_hint": "m engine · Enter opens · i info",
    "hub.narrow.cfg_hint": "Enter changes · settings available in the menu",
    "hub.narrow.lang_hint": "Enter switches language · Enter cambia el idioma",
    "hub.narrow.cal_hint": "Arrows: day/week · Enter event",
    "hub.narrow.window_title": "WORKSPACE",
    "hub.narrow.too_small": "⚠ Your terminal is {cols} columns; the hub needs "
                            "≥{need}.",
    "hub.narrow.too_small2": "Enlarge or maximize the window so the layout "
                             "doesn't break.",
}
