"""WORKSPACE · lang/es/apartar — archivar un agente o quitarlo de Workspace (agente_apartar): los avisos de una línea,
lo que conviene saber antes y los errores. FUENTE ES."""

STRINGS = {
    "apartar.archivado": "Archivé a {n}. Su carpeta y sus sesiones siguen en {p}.",
    "apartar.quitado": "Quité a {n} de Workspace en esta computadora. Su carpeta se queda en {p}.",
    "apartar.volvio": "{n} está de vuelta.",
    "apartar.volvio.sin_carpeta": "Su carpeta todavía no está en esta computadora ({p}): cuando termine de "
                                  "sincronizar, queda listo.",
    "apartar.terminal": "{n} está archivado: tráelo de vuelta en el hub, Agentes › Esta máquina › Archivados (su "
                        "carpeta sigue en {p}).",
    "apartar.y": "y",
    # lo que conviene saber antes (ninguno bloquea)
    "apartar.aviso.actual": "Estás hablando con {n} ahora: la conversación abierta sigue, pero deja de verse en las "
                            "listas.",
    "apartar.aviso.ultimo": "Es tu único agente: el hub queda vacío hasta que lo traigas de vuelta o agregues otro.",
    "apartar.aviso.sesion": "Tiene algo abierto ahora ({s}): no se cierra ni se pierde, solo deja de verse en las "
                            "listas.",
    "apartar.aviso.coordina": "{n} coordina a otros agentes: les manda encargos a {a}. Sin él, esos encargos se quedan "
                              "sin quien los reciba.",
    "apartar.aviso.a_medias": "Su carpeta no está completa en esta computadora (puede que falte sincronizar): no se "
                              "toca.",
    "apartar.sesion.sin_nombre": "una sesión",
    "apartar.job.crear": "se está creando",
    "apartar.job.cargar": "se está conectando",
    # errores
    "apartar.err.guardar": "No pude guardar su ficha: no cambié nada.",
    "apartar.err.archivar": "No pude archivarlo: {e}",
    "apartar.err.no_esta": "No encuentro a {n} entre los archivados.",
    "apartar.err.otro": "Ya hay otro agente llamado {n} en esta computadora: no lo pisé. El archivado sigue guardado.",
    "apartar.err.volver": "No pude traerlo de vuelta: el registro no se dejó escribir.",
}
