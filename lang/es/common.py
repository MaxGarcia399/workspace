"""WORKSPACE · lang/es/common — cadenas COMPARTIDAS entre pantallas (FUENTE ES).

Lo que varias pantallas del hub reusan: hints de navegación (tecla→acción),
palabras de ESTADO de agente, términos git, antigüedad relativa y los nombres
de meses/días del calendario. Las pantallas de la Ola 2 (tono/calendario/…)
REFERENCIAN estas claves — no las redefinan. Ver `lang/README.md`.
"""

STRINGS = {
    # ── hints de navegación (acción de una tecla) ───────────────────────────
    "common.hint.section": "sección",
    "common.hint.pick": "elige",
    "common.hint.enter": "entra",
    "common.hint.terminal": "terminal",
    "common.hint.move": "mueve",
    "common.hint.jump": "salta",
    "common.hint.quit": "sale",
    "common.hint.engine": "motor",
    "common.hint.info": "información",
    "common.hint.menu": "menú",
    "common.hint.aim_open": "apunta/abre",
    "common.hint.key": "tecla",

    # ── estado de un agente (semáforo + palabra) ────────────────────────────
    "common.status.active": "activo",
    "common.status.in_use": "en uso",
    "common.status.ready": "listo",
    "common.status.soon": "pronto",
    "common.status.idle": "idle",
    "common.status.working": "trabajando",
    "common.status.running": "en curso",

    # ── git (estado del repo, de un vistazo) ────────────────────────────────
    "common.git.clean": "limpio",
    "common.git.dirty_mark": "± sucio",
    "common.git.clean_short": "limpio",
    "common.git.dirty_short": "±sucio",
    "common.git.uptodate": "al día con origin",
    "common.git.vs_origin": "vs origin",

    # ── antigüedad relativa ─────────────────────────────────────────────────
    "common.ago.sec": "hace {n}s",
    "common.ago.min": "hace {n}m",
    "common.ago.hour": "hace {n}h",
    "common.ago.day": "hace {n}d",

    # ── calendario: meses y días (compartido por el mini-calendario del hub
    #    y la pantalla Calendario de la Ola 2) ────────────────────────────────
    "common.cal.month_long.1": "enero",
    "common.cal.month_long.2": "febrero",
    "common.cal.month_long.3": "marzo",
    "common.cal.month_long.4": "abril",
    "common.cal.month_long.5": "mayo",
    "common.cal.month_long.6": "junio",
    "common.cal.month_long.7": "julio",
    "common.cal.month_long.8": "agosto",
    "common.cal.month_long.9": "septiembre",
    "common.cal.month_long.10": "octubre",
    "common.cal.month_long.11": "noviembre",
    "common.cal.month_long.12": "diciembre",
    "common.cal.month_short.1": "ene",
    "common.cal.month_short.2": "feb",
    "common.cal.month_short.3": "mar",
    "common.cal.month_short.4": "abr",
    "common.cal.month_short.5": "may",
    "common.cal.month_short.6": "jun",
    "common.cal.month_short.7": "jul",
    "common.cal.month_short.8": "ago",
    "common.cal.month_short.9": "sep",
    "common.cal.month_short.10": "oct",
    "common.cal.month_short.11": "nov",
    "common.cal.month_short.12": "dic",
    "common.cal.day_long.0": "lunes",
    "common.cal.day_long.1": "martes",
    "common.cal.day_long.2": "miércoles",
    "common.cal.day_long.3": "jueves",
    "common.cal.day_long.4": "viernes",
    "common.cal.day_long.5": "sábado",
    "common.cal.day_long.6": "domingo",
    "common.cal.dow.0": "lu",
    "common.cal.dow.1": "ma",
    "common.cal.dow.2": "mi",
    "common.cal.dow.3": "ju",
    "common.cal.dow.4": "vi",
    "common.cal.dow.5": "sá",
    "common.cal.dow.6": "do",
}
