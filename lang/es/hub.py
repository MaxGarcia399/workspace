"""WORKSPACE · lang/es/hub — el HUB (recinto): menú, cuadro IDIOMA y TODO el
«chrome» compartido de los layouts `clasico`/`centro`/`dia` + la ventana alta.

FUENTE ES (texto byte-idéntico al que el harness mostraba hardcodeado). Cubre
`front.py` (recinto clásico), `hublayout.py` (layouts `dia`/`centro` + widgets
compartidos) y `responsive_ui.vertical_hub`. Las pantallas de la Ola 2
REFERENCIAN los `hub.section.*` de aquí (títulos de sección reutilizados). El
título "IDIOMA · LANGUAGE" es bilingüe fijo → mismo valor en es y en. La entrada
«Dev» (__devmap__) NO se traduce (dev-only).
"""

STRINGS = {
    # ── menú del hub (front.menu_entries) ───────────────────────────────────
    "menu.github.label": "GitHub",
    "menu.github.tag": "tus repos: ramas locales + PRs, issues y releases",
    "menu.cal.label": "Calendario",
    "menu.cal.tag": "tu agenda del día, editable a pantalla completa",
    "menu.tono.label": "Tono",
    "menu.tono.tag": "los diales de personalidad de tus agentes",
    "menu.keybinds.label": "Atajos",
    "menu.keybinds.tag": "re-mapea las teclas rápidas del hub",
    "menu.updates.label": "Actualizaciones",
    "menu.updates.tag": "revisar · reparar · actualizar",
    "menu.add_agent.label": "Agregar agente",
    "menu.add_agent.tag": "crear o cargar un agente",
    "menu.shell.label": "Terminal normal",
    "menu.shell.tag": "tu shell de siempre · tecla q",

    # ── cuadro IDIOMA del hub ───────────────────────────────────────────────
    "hub.idioma.hint": "Enter cambia",

    # ── TÍTULOS DE SECCIÓN (mayúsculas — clasico/centro/dia/ventana alta) ────
    #    La Ola 2 reusa estas claves. En `dia` el título se pasa a _dia_caps,
    #    que lo .upper()ea: el render final es idéntico con el literal en mayús.
    "hub.section.gods": "DIOSES",
    "hub.section.agents": "AGENTES",
    "hub.section.menu": "MENÚ",
    "hub.section.personalization": "PERSONALIZACIÓN",
    "hub.section.settings": "TEMAS Y AJUSTES",
    "hub.section.today": "HOY",
    "hub.section.tone": "TONO",
    "hub.section.branches": "RAMAS",
    "hub.section.details": "DETALLES",
    "hub.section.activity": "ACTIVIDAD",
    "hub.section.monitor_live": "MONITOR · vivo",
    "hub.section.lang": "IDIOMA · LANGUAGE",
    "hub.section.configs": "CONFIGS",
    "hub.section.calendar": "CALENDARIO",
    "hub.section.upcoming": "próximos",
    # títulos con contador/nombre
    "hub.title.agents_n": "AGENTES · {n}",
    "hub.title.branches_n": "RAMAS · {n}",
    "hub.title.tone_named": "TONO · {name}",

    # ── subtítulo/build ─────────────────────────────────────────────────────
    "hub.build.control_center": "centro de control",

    # ── vacío ───────────────────────────────────────────────────────────────
    "hub.empty.agents": "sin agentes — MENÚ ▸ Agregar agente",

    # ── CONFIGS / pins ──────────────────────────────────────────────────────
    "hub.cfg.enter_changes": "Enter cambia",
    "hub.cfg.pick_change": "◄► elige · Enter/espacio cambia",
    "hub.cfg.config_edit": "Config ▸ para editar",
    # etiquetas cortas de pins (layout `dia`)
    "hub.pin.background": "fondo",
    "hub.pin.theme": "tema",
    "hub.pin.brightness": "brillo",
    "hub.pin.redlight": "luz roja",
    "hub.pin.autostart": "auto-abrir",
    "hub.pin.layout": "layout",
    "hub.pin.heartbeat": "latido",
    "hub.pin.split": "split",
    "hub.pin.stars": "estrellas",
    "hub.pin.anim": "animación",
    # aviso del toggle de luz roja (tecla `l` del recinto)
    "hub.redlight.on": "luz roja ON — modo noche",
    "hub.redlight.off": "luz roja OFF",
    "hub.redlight.fail": "no pude cambiar la luz roja — queda igual",

    # ── barra de instrumentos / monitor (centro) ────────────────────────────
    "hub.instr.usage5h": "uso 5h",
    "hub.instr.paused": "EN PAUSA",
    "hub.instr.cap": "cap",
    "hub.monitor.budget": "presup",
    "hub.monitor.commits": "commits",
    "hub.monitor.peak": "pico",
    "hub.monitor.tile.branches": "ramas",
    "hub.monitor.tile.wt": "wt",
    "hub.monitor.tile.queue": "cola",
    "hub.monitor.tile.agents": "agentes",
    "hub.act.bus_n": "bus {n}",
    "hub.act.git_n": "git {n}",
    "hub.act.pending": "· pendiente",

    # ── latido (hb_brief / latido_lines) ────────────────────────────────────
    "hub.hb.brief": "latido {mode} · cola {count} · uso 5h {uso}",
    "hub.hb.budget_paused": " · presupuesto en pausa",
    "hub.hb.queue": "cola {n}",
    "hub.hb.usage5h": "uso 5h {uso}",
    "hub.hb.paused": "presupuesto en pausa",

    # ── panel DETALLES (centro) ─────────────────────────────────────────────
    "hub.det.idle_notask": "○ idle · sin tarea publicada",
    "hub.det.soon": "· pronto",
    "hub.det.bus_pending": "bus {n} pendientes",
    "hub.det.missions": "misiones",

    # ── tira de OPERACIONES (centro) ────────────────────────────────────────
    "hub.strip.missions": "misiones",
    "hub.strip.energy": "energia",
    "hub.strip.warn_one": "aviso",
    "hub.strip.warn_many": "avisos",

    # ── TONO (mini-panel del `dia`): encabezados de grupo ───────────────────
    #    Los diales (amab/fran/…) y sus polos (brutal/llano/…) viven en
    #    personalidad.py → los traduce la Ola 2 (pantalla Tono) junto con
    #    tono_tui.py. Aquí sólo los encabezados de grupo del mini-panel.
    "hub.tono.group.manner": "trato",
    "hub.tono.group.form": "forma",
    "hub.tono.group.work": "trabajo",

    # ── calendario mini (panel HOY del `dia`) ───────────────────────────────
    "hub.cal.nothing": "sin nada",
    "hub.cal.due": "▪ vence",
    "hub.cal.allday": "todo el día",
    "hub.cal.overdue_one": "atrasada",
    "hub.cal.overdue_many": "atrasadas",
    "hub.cal.nothing_more": "nada más",
    "hub.cal.nothing_today": "sin nada este día",
    "hub.cal.add_hint": "empieza con 18:00 para ponerle hora  ·  "
                        "Enter guarda  ·  Esc cancela",
    "hub.cal.more_n": "+{n} más",
    "hub.cal.enter_add": "Enter agrega un evento aquí",
    "hub.date.week": "semana",
    "hub.date.day": "día",

    # ── fila del agente seleccionado (_dia_sel_rows) ────────────────────────
    "hub.sel.last": "última",
    "hub.sel.last_when": "última · {when}",
    "hub.sel.no_task": "sin tarea",

    # ── indicador de versión (front._hub_version_text) ──────────────────────
    "hub.ver.update_available": "update disponible",
    "hub.ver.uptodate": "al día",
    "hub.ver.behind_update": "↓{n} update",
    "hub.ver.ahead_unpushed": "↑{n} sin publicar",

    # ── franja del banner (front._franja) ───────────────────────────────────
    # caja del banner clásico (banner/render.py — fuga: sin «del equipo»)
    "hub.banner.head": "WORKSPACE · OS de agentes",
    "hub.banner.foot": "escribe el nombre de un agente para entrar directo · "
                       "workspace para este menú",

    "hub.franja.tag": "WORKSPACE · OS de agentes",
    "hub.franja.engine": "motor",
    "hub.franja.engine_suffix": " · sin API key · sync",
    "hub.franja.engines_n": "{n} motores",

    # ── hero / estado-vacío del hub (front.build_info_rows) ─────────────────
    "hub.hero.h.harness": "El harness",
    "hub.hero.k.agents": "agentes",
    "hub.hero.k.engine": "motor",
    "hub.hero.soon_paren": "(pronto)",
    "hub.hero.engine_default": "claude-code · Anthropic (sin API key)",
    "hub.hero.engine_per_agent": "  (por agente — tecla m)",
    "hub.hero.k.brains": "cerebros",
    "hub.hero.k.autoclose": "cierre auto",
    "hub.hero.v.capture": "captura de sesión activa",
    "hub.hero.v.config_first": "configura tu primer agente",
    "hub.hero.h.setup": "Tu setup",
    "hub.hero.k.user": "usuario",
    "hub.hero.k.machine": "máquina",
    "hub.hero.k.base": "base",
    "hub.hero.v.base": "instalador + workspace doctor ✓",
    "hub.hero.h.howto": "Cómo entrar",
    "hub.hero.k.menu": "menú",
    "hub.hero.v.menu": "elige un agente abajo ↓",
    "hub.hero.k.direct": "directo",
    "hub.hero.v.direct": "escribe su nombre: {name}",
    "hub.hero.agent_generic": "tu-agente",

    # ── recinto clásico (front._classic_block_lines) ────────────────────────
    "hub.classic.section_hint": "◄ ► elegir",
    "hub.classic.pers_hint": "◄ ► elige · Enter/espacio cambia",
    "hub.classic.lang_hint": "◄ ► elige · Enter cambia",
    "hub.classic.engine_prefix": "motor ▸ ",
    "hub.classic.engine_change": "m cambia",

    # ── ventana alta/doble (responsive_ui.vertical_hub) ─────────────────────
    "hub.fullscreen_notice": "Pantalla completa: experiencia completa",
    "hub.fullscreen_rec": "Pantalla completa recomendada",
    "hub.menu_header.title": "◆ ¿A dónde entras?",
    "hub.menu_header.hint": "↑↓ · Enter · q = terminal normal",

    # ── pantalla segura / angosta (front._narrow_draw) ──────────────────────
    "hub.narrow.agents_hint": "m motor · Enter abre · i información",
    "hub.narrow.cfg_hint": "Enter cambia · configuración disponible en el menú",
    "hub.narrow.lang_hint": "Enter cambia el idioma · Enter switches language",
    "hub.narrow.cal_hint": "Flechas: día/semana · Enter evento",
    "hub.narrow.window_title": "WORKSPACE",
    "hub.narrow.too_small": "⚠ Tu terminal mide {cols} columnas; el hub necesita "
                            "≥{need}.",
    "hub.narrow.too_small2": "Agranda o maximiza la ventana para que el diseño "
                             "no se rompa.",
}
