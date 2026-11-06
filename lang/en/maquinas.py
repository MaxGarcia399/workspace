"""WORKSPACE · lang/en/maquinas — per-machine record and sync warnings
(maquinas.py). EN (translation of lang/es/maquinas.py)."""

STRINGS = {
    "maquinas.md.titulo": "# This machine's record (Workspace)",
    "maquinas.md.cuerpo": ("Workspace rewrites this file on its own when you open an agent on "
                           "this machine. It is used to warn you if the brain stops arriving "
                           "between your machines. Don't edit or delete it: it keeps nothing "
                           "personal."),
    "maquinas.otra": "Other machine",
    "maquinas.hace.momento": "just now",
    "maquinas.hace.min": "{n} min ago",
    "maquinas.hace.h": "{n} h ago",
    "maquinas.hace.dias": "{n} days ago",
    "maquinas.dias": "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
    "maquinas.meses": "Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec",
    "maquinas.desde.dia": "since {dia}",
    "maquinas.desde.fecha": "since {mes} {d}",
    "maquinas.dif.menos": "sees {n} fewer tab(s) than here",
    "maquinas.dif.mas": "sees {n} more tab(s) than here",
    "maquinas.aviso.cerrado": ("Obsidian is closed on this machine: this brain won't sync "
                               "until you open it"),
    "maquinas.accion.cerrado": "open Obsidian with this brain's vault",
    "maquinas.aviso.boveda": ("Obsidian is open but without this brain's vault: it only "
                              "syncs open vaults"),
    "maquinas.accion.boveda": "in Obsidian, open the vault «{carpeta}» (Open another vault)",
    "maquinas.aviso.vieja": "{nombre}: no news {cuando}, and there were changes here",
    "maquinas.accion.vieja": ("on that machine, open Obsidian with this vault and check that "
                              "Sync is connected"),
    "maquinas.aviso.conteo": "{nombre} {dif} for more than 1 h: sync isn't arriving",
    "maquinas.accion.conteo": ("check Obsidian Sync on both machines: connected and on the "
                               "same remote vault"),
    "maquinas.aviso.conflictos": "{n} conflicted file(s) in STATE/sessions/ ({ej})",
    "maquinas.accion.conflictos": "open them and keep the right version; Workspace doesn't touch them",
    "maquinas.linea": "WORKSPACE · sync: {avisos}",
    "maquinas.resumen.mismas": "same {n} tabs",
    "maquinas.resumen.vista": "{nombre}: seen {hace}",
    "maquinas.resumen.mas": "+{n} machine(s)",
}
