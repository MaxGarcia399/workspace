"""WORKSPACE · lang/es/maquinas — constancia por máquina y avisos de sync
(maquinas.py): la línea del hub, el aviso al abrir un agente, el contexto de
arranque y el doctor (fase 4a).

FUENTE (español): literales EXACTOS del código. Ver `lang/README.md`."""

STRINGS = {
    "maquinas.md.titulo": "# Constancia de esta máquina (Workspace)",
    "maquinas.md.cuerpo": ("Workspace reescribe este archivo solo cuando abres un agente en esta "
                           "máquina. Sirve para avisar si el cerebro deja de llegar entre tus "
                           "máquinas. No lo edites ni lo borres: no guarda nada personal."),
    "maquinas.otra": "Otra máquina",
    "maquinas.hace.momento": "hace un momento",
    "maquinas.hace.min": "hace {n} min",
    "maquinas.hace.h": "hace {n} h",
    "maquinas.hace.dias": "hace {n} días",
    "maquinas.dias": "lunes,martes,miércoles,jueves,viernes,sábado,domingo",
    "maquinas.meses": "ene,feb,mar,abr,may,jun,jul,ago,sep,oct,nov,dic",
    "maquinas.desde.dia": "desde el {dia}",
    "maquinas.desde.fecha": "desde el {d}-{mes}",
    "maquinas.dif.menos": "ve {n} pestaña(s) menos que aquí",
    "maquinas.dif.mas": "ve {n} pestaña(s) más que aquí",
    "maquinas.aviso.cerrado": ("Obsidian está cerrado en esta máquina: este cerebro no se "
                               "sincroniza hasta que lo abras"),
    "maquinas.accion.cerrado": "abre Obsidian con la bóveda de este cerebro",
    "maquinas.aviso.boveda": ("Obsidian está abierto pero sin la bóveda de este cerebro: "
                              "solo sincroniza las bóvedas abiertas"),
    "maquinas.accion.boveda": "en Obsidian, abre la bóveda «{carpeta}» (Abrir otra bóveda)",
    "maquinas.aviso.vieja": "{nombre}: sin noticias {cuando}, y aquí hubo cambios",
    "maquinas.accion.vieja": ("en esa máquina, abre Obsidian con esta bóveda y revisa que "
                              "Sync esté conectado"),
    "maquinas.aviso.conteo": "{nombre} {dif} desde hace más de 1 h: el sync no está llegando",
    "maquinas.accion.conteo": ("revisa Obsidian Sync en las dos máquinas: conectado y con "
                               "la misma bóveda remota"),
    "maquinas.aviso.conflictos": "{n} archivo(s) en conflicto en STATE/sessions/ ({ej})",
    "maquinas.accion.conflictos": "ábrelos y quédate con la versión buena; Workspace no los toca",
    "maquinas.linea": "WORKSPACE · sync: {avisos}",
    "maquinas.resumen.mismas": "mismas {n} pestañas",
    "maquinas.resumen.vista": "{nombre}: vista {hace}",
    "maquinas.resumen.mas": "+{n} máquina(s)",
}
