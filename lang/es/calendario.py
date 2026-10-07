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
    "cal.hint.attach": "imagen",
    "cal.hint.detach": "quita img",

    # ── imágenes adjuntas (Ctrl+V adjunta · Ctrl+X quita) ───────────────────
    "cal.img.chip": "img",
    "cal.img.label": "{n} img",
    "cal.img.count": "{n} imágenes",
    "cal.img.attached": "imagen adjuntada ✓ — el agente la verá",
    "cal.img.removed": "imagen quitada",
    "cal.img.none": "no hay imágenes en este campo",
    "cal.img.none_clip": "sin imagen en el portapapeles — pega la ruta del archivo",
    "cal.img.bad": "no es una imagen válida (png/jpg/gif/webp)",
    "cal.img.classic_head": "Arrastra la imagen a la terminal y pega su ruta (Enter vacío = cancelar):",
    "cal.img.classic_cancel": "sin imagen adjuntada",
    "cal.img.need_save": "escribe un título para adjuntar la imagen",
    "cal.img.save_fail": "no pude adjuntar la imagen",
    "cal.img.unavailable": "adjuntar imágenes no está disponible aquí",

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

    # ── cuentas de Google Calendar (vista multi-cuenta, tecla g) ─────────────
    "cal.hint.google": "Google",
    "cal.g.subtitle": "cuentas de google calendar",
    "cal.g.box": "CUENTAS DE GOOGLE CALENDAR",
    "cal.g.none": "ninguna todavía — conecta tu primer calendario con a",
    "cal.g.future": "Pronto: cuentas de dos vías (OAuth) para editar desde aquí.",
    "cal.g.kind.ical": "iCal · solo lectura",
    "cal.g.kind.oauth": "dos vías",
    # estado de una cuenta
    "cal.g.state.ok": "conectado",
    "cal.g.state.error": "URL inválida",
    "cal.g.state.nofetch": "sin bajar aún",
    "cal.g.row.events": "{n} eventos",
    "cal.g.row.env": "del sistema",
    "cal.g.row.sync": "sync {ago}",
    # flujo CONECTAR (paso a paso)
    "cal.g.add.title": "CONECTAR UN CALENDARIO DE GOOGLE",
    "cal.g.add.steps_head": "Para obtener la dirección secreta en formato iCal:",
    "cal.g.add.step1": "1. Abre Google Calendar en la web",
    "cal.g.add.step2": "2. Entra a Configuración (el engrane, arriba a la derecha)",
    "cal.g.add.step3": "3. En «Configuración de mis calendarios» elige el calendario",
    "cal.g.add.step4": "4. Abre «Integrar calendario»",
    "cal.g.add.step5": "5. Copia la «Dirección secreta en formato iCal»",
    "cal.g.add.name_field": "nombre (p. ej. Trabajo)",
    "cal.g.add.url_field": "dirección secreta iCal · se pega oculta",
    "cal.g.add.url_empty": "pega aquí la URL — no se muestra en pantalla",
    "cal.g.add.url_pasted": "{n} caracteres pegados",
    # flujo RENOMBRAR
    "cal.g.rename.title": "RENOMBRAR CUENTA",
    "cal.g.rename.field": "nuevo nombre",
    # confirmación de QUITAR
    "cal.g.confirm.title": "¿QUITAR ESTA CUENTA?",
    "cal.g.confirm.body": "Se desvincula «{label}»; sus eventos dejan de verse.",
    "cal.g.confirm.note": "No borra nada en Google; puedes volver a conectarla.",
    # hints de la vista
    "cal.g.hint.add": "conecta",
    "cal.g.hint.remove": "quita",
    "cal.g.hint.rename": "renombra",
    "cal.g.hint.connect": "conecta",
    "cal.g.hint.confirm": "confirma",
    # mensajes de la statusline de esta vista (S["g_msg"])
    "cal.g.msg.connected": "conectado ✓ · {n} eventos",
    "cal.g.msg.not_https": "eso no es una URL https de Google",
    "cal.g.msg.duplicate": "esa cuenta ya está vinculada",
    "cal.g.msg.fetch_failed": "no pude bajar el calendario (¿red o URL revocada?)",
    "cal.g.msg.save_failed": "no pude guardarla",
    "cal.g.msg.need_url": "pega la dirección iCal primero",
    "cal.g.msg.removed": "desvinculada: {label}",
    "cal.g.msg.renamed": "renombrada: {label}",
    "cal.g.msg.rename_empty": "el nombre no puede ir vacío",
    "cal.g.msg.env": "cuenta del sistema (variable {var}) — gestiónala allá",
    "cal.g.msg.none_sel": "no hay cuenta seleccionada",
}
