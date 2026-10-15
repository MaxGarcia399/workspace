"""WORKSPACE · lang/es/hub — el HUB (el lanzador): menú, idioma, pins y el
«chrome» compartido de las pantallas + la ventana alta/compacta.

FUENTE ES (texto byte-idéntico al que el harness mostraba hardcodeado). Cubre
`front.py`, `hublayout.py` (el lanzador + widgets compartidos) y
`responsive_ui.vertical_hub`. Las pantallas de la Ola 2
REFERENCIAN los `hub.section.*` de aquí (títulos de sección reutilizados). El
título "IDIOMA · LANGUAGE" es bilingüe fijo → mismo valor en es y en. La entrada
«Dev» (__devmap__) NO se traduce (dev-only).
"""

STRINGS = {
    # ── menú del hub (front.menu_entries) ───────────────────────────────────
    "menu.comandos.label": "Comandos",
    "menu.comandos.tag": "lo que puedes escribir en la terminal",
    "menu.cal.label": "Calendario",
    "menu.cal.tag": "tu agenda del día, editable a pantalla completa",
    "menu.tono.label": "Tono",
    "menu.tono.tag": "los diales de personalidad de tus agentes",
    "menu.updates.label": "Actualizaciones",
    "menu.updates.tag": "revisar · reparar · actualizar",
    "menu.agents.label": "Agentes",
    "menu.agents.tag": "cerebro, permisos y skills de cada agente",
    "menu.add_agent.label": "Agregar agente",
    "menu.add_agent.tag": "crear o cargar un agente",
    "menu.shell.label": "Terminal normal",
    "menu.shell.tag": "tu shell de siempre · tecla q",

    # ── cuadro IDIOMA del hub ───────────────────────────────────────────────

    # ── TÍTULOS DE SECCIÓN (mayúsculas — clasico/centro/dia/ventana alta) ────
    #    La Ola 2 reusa estas claves. En `dia` el título se pasa a _dia_caps,
    #    que lo .upper()ea: el render final es idéntico con el literal en mayús.
    "hub.section.agents": "AGENTES",
    "hub.section.menu": "MENÚ",
    "hub.section.personalization": "PERSONALIZACIÓN",
    "hub.section.lang": "IDIOMA · LANGUAGE",
    "hub.section.configs": "CONFIGS",
    # títulos con contador/nombre

    # ── subtítulo/build ─────────────────────────────────────────────────────

    # ── vacío ───────────────────────────────────────────────────────────────

    # ── CONFIGS / pins ──────────────────────────────────────────────────────
    # etiquetas cortas de pins (Personalización › del lanzador)
    "hub.pin.background": "fondo",
    "hub.pin.theme": "tema",
    "hub.pin.brightness": "brillo",
    "hub.pin.redlight": "luz roja",
    "hub.pin.autostart": "auto-abrir",
    "hub.pin.heartbeat": "latido",
    "hub.pin.split": "split",
    "hub.pin.anim": "animación",

    # ── barra de instrumentos / monitor (centro) ────────────────────────────
    "hub.act.bus_n": "bus {n}",
    "hub.act.git_n": "git {n}",

    # ── latido (hb_brief / latido_lines) ────────────────────────────────────
    "hub.hb.queue": "cola {n}",
    "hub.hb.usage5h": "uso 5h {uso}",
    "hub.hb.paused": "presupuesto en pausa",

    # ── panel DETALLES (centro) ─────────────────────────────────────────────

    # ── tira de OPERACIONES (centro) ────────────────────────────────────────

    # ── TONO (mini-panel del `dia`): encabezados de grupo ───────────────────
    #    Los diales (amab/fran/…) y sus polos (brutal/llano/…) viven en
    #    personalidad.py → los traduce la Ola 2 (pantalla Tono) junto con
    #    tono_tui.py. Aquí sólo los encabezados de grupo del mini-panel.
    "hub.tono.group.manner": "trato",
    "hub.tono.group.form": "forma",
    "hub.tono.group.work": "trabajo",

    # ── calendario mini (panel HOY del `dia`) ───────────────────────────────

    # ── fila del agente seleccionado (_dia_sel_rows) ────────────────────────

    # ── indicador de versión (front._hub_version_text) ──────────────────────
    "hub.ver.update_available": "update disponible",
    "hub.ver.uptodate": "al día",
    "hub.ver.held": "versión fijada",
    "hub.ver.behind_update": "↓{n} update",
    "hub.ver.ahead_unpushed": "↑{n} sin publicar",

    # ── franja del banner (front._franja) ───────────────────────────────────
    # caja del banner clásico (banner/render.py — fuga: sin «del equipo»)

    "hub.franja.engines_n": "{n} motores",

    # ── ventana alta/doble (responsive_ui.vertical_hub) ─────────────────────
    "hub.fullscreen_notice": "Pantalla completa: experiencia completa",

    # ── avisos del hub + latido (front/_menu_machinery, hublayout) ──
    'hub.agent.gone': '{name} ya no está registrado (cambió desde otra ventana)',
    'hub.agent.info': '{name} ▸ motor {eng} ({orig}) · cerebro {brain} · {live}',
    'hub.agent.no_live_task': 'sin tarea viva',
    'hub.agent.none_go_add': 'sin agentes — Menú › Agentes',
    'hub.agent.not_launched': '{name}: {why} — no se lanza (revisa Agentes)',
    'hub.agent.not_yet': '{name} todavía no está disponible.',
    'hub.agent.not_yet_engine': '{name} todavía no está disponible — sin motor que elegir.',
    'hub.agent.now_task': 'ahora: {task}',
    'hub.agent.soon_tag': 'próximamente',
    'hub.engine.agent_default': 'default del agente',
    'hub.engine.change_fail': 'no pude cambiar el motor: {err}',
    'hub.engine.changed': 'motor de {name} ▸ {engine}  ({where})',
    'hub.engine.local_override': 'override local',
    'hub.engine.no_selector': 'selector de motor no disponible (falta harnesses.py)',
    'hub.engine.saved_local': 'guardado per-máquina',
    'hub.hb.tag.auto': 'el cron lanza solo',
    'hub.hb.tag.manual': 'el cron solo avisa, tú lanzas',
    'hub.hb.tag.off': 'latido apagado',
    'hub.pin.fail': 'no pude cambiar «{label}» — queda igual',
    'hub.pin.saved': '{label} → {val} (guardado)',
    'hub.pin.saved_rc': '{label} → {val} (guardado · ajusta el rc a mano)',
    'hub.phase.plan': 'plan',
    'hub.phase.exec': 'ejecución',
    'hub.phase.review': 'revisión',
    'hub.phase.done': 'hecho',
    # ventana chica / viewport (responsive_ui)
    'hub.viewport.back': 'q vuelve',
    'hub.viewport.scroll': 'Ctrl+B/F desplaza',
    'hub.size.title': 'AJUSTA EL TAMAÑO DE LA VENTANA',
    'hub.size.horizontal': 'Horizontal: 100 columnas × 36 filas',
    'hub.size.vertical': 'Vertical:    72 columnas × 50 filas',
    'hub.size.yours': 'Tu ventana: {w} columnas × {h} filas',
    'hub.size.enlarge': 'Amplía la ventana o usa pantalla completa.',
    'hub.size.returns': 'La sección vuelve automáticamente al caber.',
    'hub.size.back_hub': 'q / Esc: volver al hub',
    'hub.size.enlarge_short': 'Amplía la ventana',
    'hub.size.h_short': '100 × 36 horizontal',
    'hub.size.v_short': '72 × 50 vertical',
    'hub.size.back': 'q / Esc: volver',
    # ── layout LANZADOR (hublayout.render_lanzador) ──
    'hub.lanzador.root': 'WORKSPACE',
    'hub.lanzador.search_ph': 'buscar…',
    'hub.lanzador.no_results': 'sin resultados',
    'hub.lanzador.empty': 'sin agentes — Menú › Agentes',
    'hub.lanzador.hint.type_key': 'abc',
    'hub.lanzador.hint.search': 'busca',
    'hub.lanzador.hint.erase': 'borra',
    'hub.lanzador.hint.clear': 'limpia',
    'hub.lanzador.hint.back2': 'regresa',
    'hub.lanzador.tab.menu': 'Menú',
    'hub.lanzador.tab.personalization': 'Personalización',
    'hub.lanzador.tab.lang': 'Idioma',
    # vista estática (ui.anim apagado): la lista en la caja del lanzador
    'hub.static.hint.direct': 'directo',
    'hub.layout.lanzador': 'Lanzador — agentes al centro, mínimo',
}
