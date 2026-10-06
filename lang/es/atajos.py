"""WORKSPACE · lang/es/atajos — ATAJOS (keybinds_tui) — re-mapear teclas del hub.

FUENTE (español). Cada cadena es el literal EXACTO que keybinds_tui mostraba
hardcodeado → sin `ui.lang` el default queda byte-idéntico. Ver `lang/README.md`.

Frontera de módulo (deliberada):
  · Las LABELS del MENÚ (GitHub/Dev/Calendario/…) NO se definen aquí: vienen de
    `front.menu_entries` ya traducido (keybinds las deriva). Se referencian.
  · Las labels/descripciones de `agente N`, `ciclar motor`, `detalle del agente`
    y las descripciones del menú viven hardcodeadas en `keybinds.py` (fuera de
    mi alcance de edición); aquí se COPIAN byte-idénticas como fuente ES y se
    traducen en `en/atajos.py`. keybinds_tui las surte vía `_t(key, <valor KB>)`,
    así que aunque este catálogo faltara, ES cae al valor de keybinds.py.
  · Los mensajes transitorios de `keybinds.set_key/clear/reset_all` quedan en su
    módulo (español) — no son editables desde aquí.
"""

STRINGS = {
    # ── cabecera compartida ──────────────────────────────────────────────────
    "atajos.sub": "atajos — tus teclas rápidas del hub",

    # ── hints (fila de atajos arriba + pie): descripción de cada tecla ────────
    "atajos.hint.action": "acción",
    "atajos.hint.remap": "re-mapear",
    "atajos.hint.default": "default",
    "atajos.hint.reset_all": "todo a default",
    "atajos.hint.back": "vuelve al menú",
    # hints en modo CAPTURA
    "atajos.cap.newkey": "tecla nueva",
    "atajos.cap.assigned": "queda asignada ya",
    "atajos.cap.cancel": "cancela",

    # ── caja derecha · modo CAPTURA (el prompt de la tecla nueva) ─────────────
    "atajos.cap.prompt": "presiona la tecla nueva…",
    "atajos.cap.for": "para «{label}» (hoy: {k})",
    "atajos.cap.foot": "Esc cancela · se guarda al instante",

    # ── caja derecha · detalle de la acción ──────────────────────────────────
    "atajos.det.custom": "● personalizada",
    "atajos.det.factory": "de fábrica",
    "atajos.det.key": "tecla",
    "atajos.det.default": "default",
    "atajos.det.notecla": "sin tecla — su default «{dflt}» lo tomó otra "
                          "acción; re-mapéala con Enter",
    "atajos.det.how": "cómo funciona",
    "atajos.det.rule1": "Enter re-mapea: la siguiente tecla queda guardada YA "
                        "(per-máquina, no toca a tu equipo)",
    "atajos.det.rule2": "una tecla = una acción: si ya está tomada te digo "
                        "quién la tiene — nada truena",
    "atajos.det.rule3": "reservadas: q · espacio · Enter · Esc · flechas · "
                        "Tab · t a e x f d n p (otras pantallas)",
    "atajos.det.rule4": "r = default de esta acción · R dos veces = todo de "
                        "fábrica",
    "atajos.det.saved_in": "se guarda en {ruta}",

    # ── títulos de las dos cajas ──────────────────────────────────────────────
    "atajos.box.left": "ATAJOS · {grp}",
    "atajos.box.right": "LA TECLA · {label}",

    # ── mensajes transitorios que emite ESTA pantalla ────────────────────────
    "atajos.msg.cancel": "cancelado — {label} sigue en «{k}»",
    "atajos.msg.badkey": "esa no me sirve — un carácter imprimible "
                         "(Enter reintenta)",
    "atajos.msg.reset_confirm": "R otra vez para restaurar TODO a defaults",

    # ── grupos del panel (keybinds.GRUPOS — copia byte-idéntica) ─────────────
    "atajos.group.agents": "agentes",
    "atajos.group.menu": "menú",
    "atajos.group.actions": "acciones rápidas",

    # ── labels de acción (keybinds.py — copia byte-idéntica; las del MENÚ no
    #    van aquí: salen de menu_entries ya traducido) ─────────────────────────
    "atajos.label.agent": "agente {n}",
    "atajos.label.motor": "ciclar motor",
    "atajos.label.info": "detalle del agente",

    # ── descripciones de acción (keybinds.py — copia byte-idéntica) ──────────
    "atajos.desc.agent": "apunta al agente {n} del altar SIN lanzarlo (ahí "
                         "aplican motor/info/Enter); la misma tecla otra vez "
                         "— o Enter — lo lanza",
    "atajos.desc.motor": "cambia el MOTOR del agente apuntado "
                         "(claude-code/codex/…) sin lanzarlo — se guarda "
                         "per-máquina; el siguiente Enter ya usa ese motor",
    "atajos.desc.info": "muestra en una línea el agente apuntado: motor "
                        "efectivo (y su origen), dónde vive su cerebro y su "
                        "tarea viva — sin lanzarlo",

    # ── descripciones del MENÚ (keybinds._MENU_DESCS — copia byte-idéntica;
    #    Dev queda fuera: es dev-only, stripeado del distro, se queda en ES) ──
    "atajos.desc.menu_github": "abre tus repos: mapa local de ramas + "
                               "PRs/issues/releases vía gh",
    "atajos.desc.menu_cal": "abre el editor de agenda a pantalla completa",
    "atajos.desc.menu_tono": "abre los diales de personalidad de tus agentes",
    "atajos.desc.menu_keys": "abre esta pantalla — re-mapea cualquiera de "
                             "estas teclas",
    "atajos.desc.menu_updates": "revisar · reparar · actualizar el harness",
    "atajos.desc.menu_addagent": "crear o cargar un agente nuevo",
}
