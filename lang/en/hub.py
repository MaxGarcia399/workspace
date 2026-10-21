"""WORKSPACE · lang/en/hub — the HUB: menu, LANGUAGE box and all shared hub
«chrome» of the `clasico`/`centro`/`dia` layouts + the tall window. EN."""

STRINGS = {
    # ── hub menu (front.menu_entries) ───────────────────────────────────────
    "menu.comandos.label": "Commands",
    "menu.comandos.tag": "what you can type in the terminal",
    "menu.cal.label": "Calendar",
    "menu.cal.tag": "your day's agenda, editable full-screen",
    "menu.tono.label": "Tone",
    "menu.tono.tag": "the personality dials for your agents",
    "menu.updates.label": "Updates",
    "menu.updates.tag": "check · repair · update",
    "menu.agents.label": "Agents",
    "menu.agents.tag": "each agent's brain, permissions and skills",
    "menu.users.label": "Users",
    "menu.users.tag": "who uses each agent, on all your machines",
    "menu.docs.label": "Documentation",
    "menu.docs.tag": "everything Workspace does, no fine print",
    "menu.add_agent.label": "Add agent",
    "menu.add_agent.tag": "create or load an agent",
    "menu.shell.label": "Normal terminal",
    "menu.shell.tag": "your usual shell · key q",

    # ── hub LANGUAGE box ────────────────────────────────────────────────────

    # ── SECTION TITLES (uppercase) ──────────────────────────────────────────
    "hub.section.agents": "AGENTS",
    "hub.section.menu": "MENU",
    "hub.section.personalization": "PERSONALIZATION",
    "hub.section.lang": "IDIOMA · LANGUAGE",
    "hub.section.configs": "SETTINGS",
    # titles with counter/name

    # ── subtitle/build ──────────────────────────────────────────────────────

    # ── empty ───────────────────────────────────────────────────────────────

    # ── SETTINGS / pins ─────────────────────────────────────────────────────
    "hub.pin.background": "background",
    "hub.pin.theme": "theme",
    "hub.pin.brightness": "brightness",
    "hub.pin.redlight": "red light",
    "hub.pin.autostart": "autostart",
    "hub.pin.heartbeat": "heartbeat",
    "hub.pin.split": "split",
    "hub.pin.anim": "anim",
    # red light toggle notice (recinto key `l`)

    # ── instrument bar / monitor (centro) ───────────────────────────────────
    "hub.act.bus_n": "bus {n}",
    "hub.act.git_n": "git {n}",

    # ── heartbeat (hb_brief / latido_lines) ─────────────────────────────────
    "hub.hb.queue": "queue {n}",
    "hub.hb.usage5h": "5h use {uso}",
    "hub.hb.paused": "budget paused",

    # ── DETAILS panel (centro) ──────────────────────────────────────────────

    # ── OPERATIONS strip (centro) ───────────────────────────────────────────

    # ── TONE (dia mini-panel): group headers ────────────────────────────────
    "hub.tono.group.manner": "manner",
    "hub.tono.group.form": "form",
    "hub.tono.group.work": "work",

    # ── mini calendar (dia TODAY panel) ─────────────────────────────────────

    # ── selected agent row (_dia_sel_rows) ──────────────────────────────────

    # ── version indicator (front._hub_version_text) ─────────────────────────
    "hub.ver.update_available": "update available",
    "hub.ver.uptodate": "up to date",
    "hub.ver.held": "version pinned",
    "hub.ver.behind_update": "↓{n} update",
    "hub.ver.ahead_unpushed": "↑{n} unpushed",

    # ── banner strip (front._franja) ────────────────────────────────────────
    # classic banner box (banner/render.py — leak: no "del equipo")

    "hub.franja.engines_n": "{n} engines",

    # ── tall/split window (responsive_ui.vertical_hub) ──────────────────────
    "hub.fullscreen_notice": "Full screen: full experience",

    # ── safe / narrow screen (front._narrow_draw) ───────────────────────────

    # ── hub notices + heartbeat (front/_menu_machinery, hublayout) ──
    'hub.agent.gone': '{name} is no longer registered (changed from another window)',
    'hub.agent.info': '{name} ▸ engine {eng} ({orig}) · brain {brain} · {live}',
    'hub.agent.no_live_task': 'no live task',
    'hub.agent.none_go_add': 'no agents — Menu › Agents',
    'hub.agent.not_launched': '{name}: {why} — not launching (check Agents)',
    'hub.agent.not_yet': "{name} isn't available yet.",
    'hub.agent.not_yet_engine': "{name} isn't available yet — no engine to pick.",
    'hub.agent.now_task': 'now: {task}',
    'hub.agent.soon_tag': 'coming soon',
    'hub.engine.agent_default': "agent's default",
    'hub.engine.change_fail': "couldn't change the engine: {err}",
    'hub.engine.changed': "{name}'s engine ▸ {engine}  ({where})",
    'hub.engine.local_override': 'local override',
    'hub.engine.no_selector': 'engine selector unavailable (harnesses.py missing)',
    'hub.engine.saved_local': 'saved per machine',
    'hub.hb.tag.auto': 'the cron launches on its own',
    'hub.hb.tag.manual': 'the cron only notifies, you launch',
    'hub.hb.tag.off': 'heartbeat off',
    'hub.pin.fail': "couldn't change «{label}» — left as is",
    'hub.pin.saved': '{label} → {val} (saved)',
    'hub.pin.saved_rc': '{label} → {val} (saved · adjust your rc by hand)',
    'hub.phase.plan': 'plan',
    'hub.phase.exec': 'exec',
    'hub.phase.review': 'review',
    'hub.phase.done': 'done',
    # small window / viewport (responsive_ui)
    'hub.viewport.back': 'q back',
    'hub.viewport.scroll': 'Ctrl+B/F scrolls',
    'hub.size.title': 'RESIZE THE WINDOW',
    'hub.size.minimum': 'Minimum:     {w} columns × {h} rows',
    'hub.size.yours': 'Your window: {w} columns × {h} rows',
    'hub.size.enlarge': 'Enlarge the window or go full screen.',
    'hub.size.returns': 'The section comes back on its own once it fits.',
    'hub.size.back_hub': 'q / Esc: back to the hub',
    'hub.size.enlarge_short': 'Enlarge the window',
    'hub.size.min_short': 'minimum {w} × {h}',
    'hub.size.back': 'q / Esc: back',
    # ── layout LANZADOR (hublayout.render_lanzador) ──
    'hub.lanzador.root': 'WORKSPACE',
    'hub.lanzador.search_ph': 'search…',
    'hub.lanzador.no_results': 'no results',
    'hub.lanzador.empty': 'no agents — Menu › Agents',
    'hub.lanzador.hint.type_key': 'abc',
    'hub.lanzador.hint.search': 'search',
    'hub.lanzador.hint.erase': 'erase',
    'hub.lanzador.hint.clear': 'clear',
    'hub.lanzador.hint.back2': 'back',
    'hub.lanzador.tab.menu': 'Menu',
    'hub.lanzador.tab.personalization': 'Personalization',
    'hub.lanzador.tab.lang': 'Language',
    # destino directo de la raíz: el mapa de la memoria (docs_tui.run_mapa)
    'hub.lanzador.map': 'Memory map',
    'hub.lanzador.map.tag': 'how your agent remembers, step by step',
    # vista estática (ui.anim apagado): la lista en la caja del lanzador
    'hub.static.hint.direct': 'direct',
    'hub.layout.lanzador': 'Launcher — agents at the center, minimal',
}
