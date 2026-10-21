"""Catálogo ES (FUENTE) — arranque de un agente (dispatch.py): el motor
asignado no está disponible y se ofrece abrir con otro."""

STRINGS = {
    "dispatch.engine.no_adapter": "no tiene adaptador en este Workspace",
    "dispatch.engine.not_installed": "no está instalado (falta {bins})",
    "dispatch.engine.down":
        "WORKSPACE: {name} usa {engine}, pero ese motor no está disponible: {why}.",
    "dispatch.engine.none":
        "  No hay ningún motor disponible en esta máquina — instala uno en el "
        "hub › Motores.",
    "dispatch.engine.available": "  Motores disponibles: {list}",
    "dispatch.engine.hint":
        "  Para abrirlo con otro esta vez: {agent} --engine <motor>",
    "dispatch.engine.ask": "  ¿Con cuál lo abro esta vez?",
    "dispatch.engine.prompt": "Número y Enter · Enter solo cancela: ",
    "dispatch.engine.make_default":
        "  ¿Dejar {engine} como el motor de {name} en esta máquina? [s/N] ",
    "dispatch.engine.saved":
        "  ✓ {name} usará {engine} de ahora en adelante (se cambia en Agentes).",
    "dispatch.engine.save_fail":
        "  No pude guardarlo ({err}); se abre igual con {engine} esta vez.",
    "dispatch.engine.this_time":
        "  Solo esta vez: {name} sigue con {engine} como su motor.",
    # cargando.py: al centro mientras se prepara la apertura de un agente
    "dispatch.cargando": "Cargando…",
}
