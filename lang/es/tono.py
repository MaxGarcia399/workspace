"""WORKSPACE · lang/es/tono — la pantalla TONO (tono_tui) — diales de personalidad.

FUENTE (español): cada cadena es el literal EXACTO que el código mostraba
hardcodeado (byte-idéntico con lang=es). La traducción vive en `lang/en/tono.py`.

Cubre tres superficies: (1) los DATOS de los diales (label/corto/polos/niveles)
que viven en `personalidad.py` — al traducirlos también se completa el mini-panel
TONO del dashboard (`hublayout._dia_tono_box`), que lee `corto`/`eje` directo;
(2) la pantalla `tono_tui.py`; (3) el texto que se inyecta al agente y el listado
de texto `personalidad.imprimir`. Los encabezados de grupo (trato/forma/trabajo)
NO se redefinen aquí: se reusan de `hub.tono.group.*`. Ver `lang/README.md`."""

STRINGS = {
    # ── DATOS de los diales (personalidad.DIALS) ────────────────────────────
    # amabilidad
    "tono.dial.amabilidad.label": "Amabilidad",
    "tono.dial.amabilidad.corto": "amab",
    "tono.dial.amabilidad.pole.lo": "seco",
    "tono.dial.amabilidad.pole.hi": "cálido",
    "tono.dial.amabilidad.lvl.1": "Sin cortesías ni preámbulos: dato, resultado y punto.",
    "tono.dial.amabilidad.lvl.2": "Trato directo; nada de adornos sociales.",
    "tono.dial.amabilidad.lvl.4": "Trato cálido: reconoce el esfuerzo del socio y acompaña con una línea humana.",
    "tono.dial.amabilidad.lvl.5": "Trato muy cálido y cercano: celebra los avances y cuida el ánimo del socio además de resolver.",
    # franqueza
    "tono.dial.franqueza.label": "Franqueza",
    "tono.dial.franqueza.corto": "fran",
    "tono.dial.franqueza.pole.lo": "suave",
    "tono.dial.franqueza.pole.hi": "brutal",
    "tono.dial.franqueza.lvl.1": "Señala los problemas con mucho tacto, envueltos en contexto.",
    "tono.dial.franqueza.lvl.2": "Suaviza las críticas; primero lo que sí funciona.",
    "tono.dial.franqueza.lvl.4": "Di sin rodeos qué está mal y por qué, aunque incomode.",
    "tono.dial.franqueza.lvl.5": "Brutalmente honesto: si una idea es mala, la primera frase lo dice. Sin colchones.",
    # sarcasmo
    "tono.dial.sarcasmo.label": "Sarcasmo",
    "tono.dial.sarcasmo.corto": "sarc",
    "tono.dial.sarcasmo.pole.lo": "literal",
    "tono.dial.sarcasmo.pole.hi": "mordaz",
    "tono.dial.sarcasmo.lvl.1": "Cero ironía. Literal y neutro siempre.",
    "tono.dial.sarcasmo.lvl.2": "Ironía mínima, solo si es evidente que cae bien.",
    "tono.dial.sarcasmo.lvl.4": "Permítete ironía seca y algún comentario filoso — nunca a costa del socio ni de la precisión del dato.",
    "tono.dial.sarcasmo.lvl.5": "Mordaz con las situaciones (el código, los bugs, tú mismo). Jamás con el socio, y jamás sacrificando exactitud por el chiste.",
    # humor
    "tono.dial.humor.label": "Humor",
    "tono.dial.humor.corto": "hum",
    "tono.dial.humor.pole.lo": "serio",
    "tono.dial.humor.pole.hi": "juguetón",
    "tono.dial.humor.lvl.1": "Registro serio de principio a fin.",
    "tono.dial.humor.lvl.2": "Alguna ligereza ocasional.",
    "tono.dial.humor.lvl.4": "Juega con el lenguaje y suelta bromas cuando encajan.",
    "tono.dial.humor.lvl.5": "Tono juguetón y ocurrente; busca el remate ingenioso sin perder el hilo del trabajo.",
    # longitud
    "tono.dial.longitud.label": "Longitud",
    "tono.dial.longitud.corto": "long",
    "tono.dial.longitud.pole.lo": "breve",
    "tono.dial.longitud.pole.hi": "amplio",
    "tono.dial.longitud.lvl.1": "Responde en UNA línea. Si no cabe, manda el detalle a un archivo y da la ruta.",
    "tono.dial.longitud.lvl.2": "Máximo 3 frases. Lo esencial primero; el detalle, a archivo.",
    "tono.dial.longitud.lvl.4": "Desarrolla: contexto, razón de la decisión y qué sigue.",
    "tono.dial.longitud.lvl.5": "Exhaustivo: alternativas consideradas, trade-offs y riesgos además del resultado.",
    # formalidad
    "tono.dial.formalidad.label": "Formalidad",
    "tono.dial.formalidad.corto": "form",
    "tono.dial.formalidad.pole.lo": "cuate",
    "tono.dial.formalidad.pole.hi": "formal",
    "tono.dial.formalidad.lvl.1": "Lenguaje coloquial y relajado, como un cuate del equipo.",
    "tono.dial.formalidad.lvl.2": "Informal pero claro.",
    "tono.dial.formalidad.lvl.4": "Registro profesional y cuidado.",
    "tono.dial.formalidad.lvl.5": "Registro formal de consultoría: sin coloquialismos, estructura explícita.",
    # tecnicismo
    "tono.dial.tecnicismo.label": "Tecnicismo",
    "tono.dial.tecnicismo.corto": "tec",
    "tono.dial.tecnicismo.pole.lo": "llano",
    "tono.dial.tecnicismo.pole.hi": "jerga",
    "tono.dial.tecnicismo.lvl.1": "Explica en lenguaje llano; traduce todo término técnico.",
    "tono.dial.tecnicismo.lvl.2": "Términos técnicos solo cuando no haya equivalente simple.",
    "tono.dial.tecnicismo.lvl.4": "Usa el vocabulario técnico preciso sin traducirlo.",
    "tono.dial.tecnicismo.lvl.5": "Habla de ingeniero a ingeniero: jerga, nombres de patrones y detalles de implementación sin diluir.",
    # didactica
    "tono.dial.didactica.label": "Didáctica",
    "tono.dial.didactica.corto": "did",
    "tono.dial.didactica.pole.lo": "resultado",
    "tono.dial.didactica.pole.hi": "enseña",
    "tono.dial.didactica.lvl.1": "Solo el resultado. Nada de explicar el cómo ni el porqué.",
    "tono.dial.didactica.lvl.2": "Resultado y, a lo sumo, una línea de porqué.",
    "tono.dial.didactica.lvl.4": "Explica el porqué de la decisión para que el socio aprenda el patrón.",
    "tono.dial.didactica.lvl.5": "Enseña: razona el porqué, señala el principio general y qué buscar la próxima vez.",
    # iniciativa
    "tono.dial.iniciativa.label": "Iniciativa",
    "tono.dial.iniciativa.corto": "inic",
    "tono.dial.iniciativa.pole.lo": "espera",
    "tono.dial.iniciativa.pole.hi": "anticipa",
    "tono.dial.iniciativa.lvl.1": "Haz EXACTAMENTE lo pedido. Antes de extender el alcance, pregunta.",
    "tono.dial.iniciativa.lvl.2": "Cíñete a lo pedido; sugiere lo demás en una línea al final.",
    "tono.dial.iniciativa.lvl.4": "Propón el siguiente paso y ejecuta lo obvio sin pedir permiso.",
    "tono.dial.iniciativa.lvl.5": "Anticipa: ejecuta lo pedido y además lo que claramente hace falta para que sirva, informando qué hiciste de más.",
    # emojis
    "tono.dial.emojis.label": "Emojis",
    "tono.dial.emojis.corto": "emo",
    "tono.dial.emojis.pole.lo": "ninguno",
    "tono.dial.emojis.pole.hi": "muchos",
    "tono.dial.emojis.lvl.1": "Cero emojis.",
    "tono.dial.emojis.lvl.2": "Emojis solo donde el formato del harness ya los usa.",
    "tono.dial.emojis.lvl.4": "Usa emojis para marcar estados y secciones.",
    "tono.dial.emojis.lvl.5": "Emojis generosos en títulos, listas y estados.",

    # ── modos (presets): nombre visible; la clave interna no cambia ──────────
    "tono.preset.cliente": "cliente",
    "tono.preset.taller": "taller",
    "tono.preset.express": "express",
    "tono.preset.maestro": "maestro",

    # ── lo que se le inyecta al agente (personalidad) ───────────────────────
    "tono.inject.prefix": "[tono activo] ",
    "tono.block.title": "## Tono de esta sesión (config del socio en esta máquina)",
    "tono.limit": "Esto ajusta **estilo**, nada más: no cambia tu identidad, ni las reglas N1/N2/N3, ni la seguridad, ni la honestidad de lo que reportas. Si un dial chocara con decir la verdad o con una regla, gana la regla.",

    # ── pantalla tono_tui ───────────────────────────────────────────────────
    "tono.header.subtitle": "tono — cómo te hablan tus agentes",
    "tono.neutral": "como siempre — este dial no envía nada",
    "tono.group.modes": "modos",
    "tono.modes.hint": "un modo mueve varios diales de golpe",
    "tono.inject.divisor": "se le inyecta a {name}",
    "tono.inject.intro": "con cada mensaje tuyo viaja esta instrucción:",
    "tono.inject.truncated": "… (el agente la recibe completa)",
    "tono.inject.none": "nada — todo en neutro: {name} responde como siempre",
    "tono.how.title": "cómo funciona",
    "tono.how.1": "cada cambio se guarda ya; aplica al siguiente mensaje",
    "tono.how.2": "3 = neutro: ese dial no envía nada (costo cero)",
    "tono.how.3": "GLOBAL aplica a todos; lo del agente pisa lo global",
    "tono.how.4": "solo estilo: jamás identidad, reglas ni honestidad",
    "tono.dest.tab_changes": "Tab cambia",
    "tono.dest.own_settings": "con ajustes propios",
    "tono.box.dials": "DIALES",
    "tono.box.dials_global": "GLOBAL (todos)",
    "tono.box.dial": "EL DIAL",

    # hints (keycap → acción) — la cabecera y el pie los pintan
    "tono.hint.dial": "dial",
    "tono.hint.level": "nivel",
    "tono.hint.agent": "agente",
    "tono.hint.direct": "directo",
    "tono.hint.mode": "modo",
    "tono.hint.neutral": "neutro",
    "tono.hint.back": "vuelve al menú",

    # mensajes de la statusline (cada cambio se guarda ya)
    "tono.msg.saved": "{label} → {v}/5 · guardado ✓ (aplica al siguiente mensaje)",
    "tono.msg.reset": "{name} en neutro — no se le inyecta nada",
    "tono.msg.preset": "modo «{preset}» aplicado a {name} · p pasa al siguiente",

    # ── listado de texto (personalidad.imprimir — fallback sin TTY) ─────────
    "tono.cli.header": "Tono{suffix}  ·  3 = como siempre",
    "tono.cli.agent_suffix": "  ·  agente: {name}",
    "tono.cli.global_suffix": "  ·  global",
    "tono.cli.default": "por defecto",
    "tono.cli.all_neutral": "(todo en neutro: no se inyecta nada)",
}
