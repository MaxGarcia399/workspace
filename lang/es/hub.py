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
    "menu.users.label": "Usuarios",
    "menu.users.tag": "quién usa cada agente, en todas tus máquinas",
    "menu.conversaciones.label": "Conversaciones",
    "menu.conversaciones.tag": "lo que tus agentes se dicen entre sí: sigue cada charla y corta cuando quieras",
    "menu.decisores.label": "Decisores",
    "menu.decisores.tag": "qué modelo decide y dónde ayuda",
    "menu.docs.label": "Documentación",
    "menu.docs.tag": "todo lo que hace Workspace, sin letra chica",
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
    "hub.pin.un_color": "un color",
    "hub.pin.tema_herdr": "seguir a herdr",
    "hub.pin.autostart": "auto-abrir",
    "hub.pin.navegador": "navegador al iniciar",
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
    'hub.pin.herdr_manda': '{label} → {val} (guardado; dentro de herdr manda {tema})',
    'hub.pin.saved_rc': '{label} → {val} (guardado · ajusta el rc a mano)',
    'hub.phase.plan': 'plan',
    'hub.phase.exec': 'ejecución',
    'hub.phase.review': 'revisión',
    'hub.phase.done': 'hecho',
    # ventana chica / viewport (responsive_ui)
    'hub.viewport.back': 'q vuelve',
    'hub.viewport.scroll': 'Ctrl+B/F desplaza',
    'hub.size.title': 'AJUSTA EL TAMAÑO DE LA VENTANA',
    # el mínimo real de ESA pantalla (responsive_ui.renderer(min_size=…))
    'hub.size.minimum': 'Mínimo:     {w} columnas × {h} filas',
    'hub.size.yours': 'Tu ventana: {w} columnas × {h} filas',
    'hub.size.enlarge': 'Amplía la ventana o usa pantalla completa.',
    'hub.size.returns': 'La sección vuelve automáticamente al caber.',
    'hub.size.back_hub': 'q / Esc: volver al hub',
    'hub.size.enlarge_short': 'Amplía la ventana',
    'hub.size.min_short': 'mínimo {w} × {h}',
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
    # fila «otra máquina» al pie de la raíz (solo dev: maquinas_dev)
    'hub.lanzador.other_machine': 'Otra máquina',
    # vista estática (ui.anim apagado): la lista en la caja del lanzador
    'hub.static.hint.direct': 'directo',
    'hub.layout.lanzador': 'Lanzador — agentes al centro, mínimo',
    # la fila de Decisores, la última del área de los agentes (hublayout._lz_deci)
    'hub.lanzador.tab.decisores': 'Decisores',
    'hub.deci.badge_new': 'nuevo',
    'hub.deci.setup': 'configurar',
    'hub.deci.off': 'apagado',
    'hub.deci.offline': 'sin conexión',
    'hub.deci.none_ready': 'conecta un modelo en Motores → Modelos de decisión (Enter)',
    'hub.deci.uses_hint': 'elige sus usos en Decisores (Enter)',
    'hub.skills_pend.one': '1 revisión de skills pendiente',
    'hub.skills_pend.of': 'revisión de skills · {q}',
    'hub.skills_pend.waiting': '{q}: la tarea le llega con tu próximo mensaje ahí',
    'hub.skills_pend.why': '{q}: la revisión de {o} no dejó resultado · Enter la hace ahora',
    'hub.skills_pend.do': 'Hacer ahora',
    'hub.skills_pend.fail': 'no pude: {e}',
    'hub.skills_pend.written': 'le escribí la tarea a {q} en su panel',
    'hub.skills_pend.next_msg': '{q} tiene la pestaña abierta: la tarea le llega con tu próximo mensaje ahí',
    'hub.skills_pend.yesterday': 'ayer {h}',
    'hub.deci.own_models': '{n} usos siguen con su propio modelo (Enter: Decisores)',
    'hub.deci.today': 'Decisores hoy: ',
    'hub.skills_pend.many': '{k} revisiones de skills pendientes',
    'hub.skills_pend.gone': 'ya no está pendiente',
    'hub.skills_pend.unreadable': 'no pude leer la entrega anterior: queda pendiente',
    'hub.skills_pend.unrecorded': 'le escribí la tarea a {q}, pero no pude registrar la entrega: la revisión puede repetirse',
    'hub.skills_pend.no_view': 'su vista ya no está: queda pendiente',
    'hub.skills_pend.no_task': 'no pude escribir la tarea: queda pendiente',
    'hub.skills_pend.typed': '{q} tiene algo escrito en su panel: ábrela tú; la revisión sigue pendiente',
    'hub.skills_pend.unsure': '{q} no está quieta o no puedo ver si tiene algo escrito: ábrela tú; la revisión sigue pendiente',
    'hub.skills_pend.herdr': 'herdr no aceptó el texto: ábrela tú; la revisión sigue pendiente',
    'hub.skills_pend.busy': 'otro proceso la está entregando: prueba en un momento',
    'hub.skills_pend.monito': 'es de su conversación de Compañero: la recibe la próxima vez que lo abras en su terminal o en la página',
    'hub.skills_pend.active': 'esta pestaña ya tiene una revisión por terminar: la siguiente espera',
    'hub.skills_pend.other_engine': '{q} está abierta en {m}: la recibe al volver a abrirla (ciérrala y pulsa Hacer ahora)',
    'hub.skills_pend.opening': 'abriendo {q} con la tarea',
    'hub.skills_pend.from_agents': 'ábrela desde Agentes: la tarea le llega al arrancar',
}

STRINGS.update({'hub.skills_pend.unreadable_queue': 'Revisión de skills: no se pudo leer un pendiente; los demás siguen.', 'hub.skills_pend.lock_failed': 'Revisión de skills: no se pudo guardar una revisión porque la cola estaba ocupada.'})

STRINGS.update({'hub.skills_pend.launch_failed': 'Revisión de skills: no se pudo abrir la pestaña; la revisión sigue pendiente.', 'hub.skills_pend.review_now': 'Revisar ahora'})

STRINGS.update({'hub.skills_pend.batch_why': '{q}: revisión acumulada · Enter abre la tanda'})

STRINGS.update({'hub.skills_pend.history': 'resultados · Ver · Deshacer'})
