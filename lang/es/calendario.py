"""WORKSPACE · lang/es/calendario — el editor de CALENDARIO (calendario_tui).

FUENTE (ES): cada cadena es el literal español EXACTO que el harness mostraba
hardcodeado. Meses y días NO se redefinen aquí: salen de `common.cal.*`
(ver `lang/es/common.py`). Traducción en `lang/en/calendario.py`.
Ver `lang/README.md`."""

STRINGS = {
    # ── subtítulo de la pantalla (cabecera compartida) ──────────────────────
    "cal.subtitle": "calendario",

    # ── títulos de caja / sección ───────────────────────────────────────────
    "cal.box.month_title": "MES · {month} {year}",
    "cal.box.day": "DÍA",
    "cal.box.upcoming": "PRÓXIMOS",
    "cal.box.overdue": "ATRASADAS · {n}",
    "cal.overdue.more": "+{n} más — ve al día con ◄► o táchalas con x",
    "cal.box.trash": "PAPELERA · {n} eventos",
    "cal.box.queue": "COLA DE AGENTES · {n} listas",
    "cal.box.idea": "IDEA / DESCRIPCIÓN",
    "cal.box.prompt": "PROMPT PARA EL AGENTE",
    "cal.box.ficha": "FICHA · {date} · {kind}",

    # ── estado de una tarea (etiqueta de ficha) ─────────────────────────────
    "cal.status.draft": "BORRADOR",
    "cal.status.ready": "LISTA",
    "cal.status.in_progress": "EN CURSO",
    "cal.status.blocked": "BLOQUEADA",
    "cal.status.done": "TERMINADA",

    # ── leyenda de la rejilla del mes ───────────────────────────────────────
    "cal.legend.due": "faltan",
    "cal.legend.overdue": "atrasadas",
    "cal.legend.done": "hechas",

    # ── encabezado del DÍA ──────────────────────────────────────────────────
    "cal.day.header": "{dow} {day} de {month}",
    "cal.day.today": "· hoy",
    "cal.day.none": "sin eventos este día",
    "cal.day.add_hint": "agrega uno aquí",
    "cal.day.notes_more": "… {n} más — Enter abre el detalle",

    # ── modo MOVER ──────────────────────────────────────────────────────────
    "cal.move.title": "Mover: {title}",
    "cal.move.dest": "Destino: {date}",
    "cal.move.arrows": "Flechas: día · n/p: mes · t: hoy",
    "cal.move.confirm": "Enter mueve · Esc cancela",

    # ── papelera ────────────────────────────────────────────────────────────
    "cal.trash.intro": "Los borrados se pueden recuperar durante 15 días.",
    "cal.trash.empty": "Papelera vacía",
    "cal.trash.row": "{mark} {date} · {title} · {n}d",

    # ── cola de agentes ─────────────────────────────────────────────────────
    "cal.queue.intro": "Solo tareas marcadas LISTA; prioridad alta, luego fecha.",
    "cal.queue.empty": "Sin tareas listas; l cambia borrador a lista.",

    # ── mini-calendario del editor (contexto de ficha) ──────────────────────
    "cal.ctx.day": "DÍA · {date}",
    "cal.ctx.none": "Sin fichas; a crea una aquí",

    # ── placeholders de los campos de texto ─────────────────────────────────
    "cal.panel.idea_ph": "Describe qué quieres lograr y el contexto.",
    "cal.panel.prompt_ph": "Indica cómo debe trabajar el agente.",

    # ── ficha (alta / edición / detalle) ────────────────────────────────────
    "cal.ficha.kind_detail": "detalle",
    "cal.ficha.kind_new": "nueva",
    "cal.ficha.kind_edit": "edición",
    "cal.ficha.queue_count": "{n} listas para agentes",
    "cal.ficha.title_field": "título · hora opcional al inicio",
    "cal.ficha.result": "Resultado: {text}",

    # ── acciones de teclas (hints) ──────────────────────────────────────────
    "cal.hint.day": "día",
    "cal.hint.detail": "detalle",
    "cal.hint.add": "agrega",
    "cal.hint.list": "lista",
    "cal.hint.queue": "cola",
    "cal.hint.month": "mes",
    "cal.hint.today": "hoy",
    "cal.hint.trash": "papelera",
    "cal.hint.switch": "cambia",
    "cal.hint.edit": "edita",
    "cal.hint.done": "hecha",
    "cal.hint.ready_draft": "lista/borrador",
    "cal.hint.delete": "borra",
    "cal.hint.restore": "restaura",
    "cal.hint.back": "vuelve",
    "cal.hint.to_draft": "devuelve a borrador",
    "cal.hint.text": "texto",
    "cal.hint.card": "ficha",
    "cal.hint.open": "abre",
    "cal.hint.new": "nueva",
    "cal.hint.calendar": "calendario",
    "cal.hint.field": "campo",
    "cal.hint.scroll": "desplaza",
    "cal.hint.save": "guarda",
    "cal.hint.newline": "salto",
    "cal.hint.cancel": "cancela",

    # ── mensajes de la statusline (S["msg"]) ────────────────────────────────
    "cal.msg.g_readonly": "evento de Google — solo lectura",
    "cal.msg.g_readonly_edit": "evento de Google — solo lectura (edítalo allá)",
    "cal.msg.g_readonly_delete": "evento de Google — solo lectura (bórralo allá)",
    "cal.msg.g_readonly_move": "evento de Google — solo lectura (muévelo allá)",
    "cal.msg.g_no_done": "evento de Google — no se tacha (no es tarea local)",
    "cal.msg.task_gone": "la tarea ya no está disponible",
    "cal.msg.now_ready": "LISTA para tomar por un agente",
    "cal.msg.now_draft": "BORRADOR — fuera de la cola",
    "cal.msg.ready_fail": "no se cambió: tarea en curso o error al guardar",
    "cal.msg.save_fail": "no pude guardarlo",
    "cal.msg.done_ok": "hecha ✓ — sigue ahí, tachada (x la revive)",
    "cal.msg.pending_again": "pendiente otra vez",
    "cal.msg.prio_high": "prioridad ALTA — va primero",
    "cal.msg.prio_normal": "prioridad normal",
    "cal.msg.trashed": "en papelera 15 días: {title}",
    "cal.msg.delete_fail": "no pude borrarlo",
    "cal.msg.move_cancelled": "movimiento cancelado",
    "cal.msg.moved": "movido a {date}",
    "cal.msg.move_fail": "no pude moverlo; el evento conserva su fecha",
    "cal.msg.restored": "restaurado: {title}",
    "cal.msg.restore_fail": "no pude restaurarlo",
    "cal.msg.need_title": "escribe un título; el contenido sigue aquí",
    "cal.msg.save_lost": "no se guardó; tus campos siguen aquí",
    "cal.msg.saved": "guardado; l marca LISTA para un agente",
    "cal.msg.cancelled": "cancelado",
    "cal.msg.char_limit": "límite de {n} caracteres; guarda o reduce el texto",
    "cal.msg.no_task_mark": "no hay tarea que marcar",
    "cal.msg.no_move_here": "no hay evento que mover aquí",
    "cal.msg.no_edit_here": "no hay evento que editar en este día",
    "cal.msg.no_done_here": "no hay nada que tachar aquí",
    "cal.msg.no_delete_here": "no hay nada que borrar aquí",
}
