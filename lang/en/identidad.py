"""WORKSPACE · lang/en/identidad — who you are on this machine (identidad.py) in
`workspace doctor` (phase 4d).

Translation of lang/es/identidad.py. See `lang/README.md`.
"""

STRINGS = {
    "doctor.phase.phase_identidad": "4d · Who you are in each brain (this machine's identity)",
    "doctor.phase_identidad.persona": "on this machine you're «{nombre}»",
    "doctor.phase_identidad.persona.detail": "also: {alias} · every brain finds you by your user",
    "doctor.phase_identidad.persona.detail_solo": "every brain finds you by your user",
    "doctor.phase_identidad.persona_creada": "this machine now knows who you are: «{nombre}»",
    "doctor.phase_identidad.persona_creada.detail": "it counts for all your brains · change it with «that's me on this PC» in the Users section",
    "doctor.phase_identidad.sin_persona": "each agent knows who you are, as before",
    "doctor.phase_identidad.sin_persona.detail": "this machine has no identity for all your brains yet: it's saved the first time you pick «that's me on this PC» in Users",
    "doctor.phase_identidad.no_sabe": "[{agente}] doesn't know which of its {n} users you are on this machine",
    "doctor.phase_identidad.no_sabe.detail": "I won't take another person's folder as yours",
    "doctor.phase_identidad.no_sabe.action": "pick «that's me on this PC» in the Users section (it counts for all your brains)",
    "doctor.phase_identidad.otra_persona": "[{agente}] this brain says you're «{socio}» here, but on this machine you're «{nombre}»",
    "doctor.phase_identidad.otra_persona.detail": "Workspace uses «{nombre}»",
    "doctor.phase_identidad.otra_persona.action": "if you're «{socio}» in this brain, pick «that's me on this PC» in the Users section",
    "doctor.phase_identidad.duplicadas": "[{agente}] you have two separate users: {nombres}",
    "doctor.phase_identidad.duplicadas.detail": "they merge on their own when you open the agent (or with `workspace doctor`), with a backup and undo",
    "doctor.phase_identidad.unidas": "[{agente}] «{origen}» and «{destino}» were you: merged",
    "doctor.phase_identidad.unidas.detail": "{n} tab(s) moved to «{destino}» and nothing was deleted · undo: {deshacer}",
    "doctor.phase_identidad.bloqueada": "[{agente}] I didn't merge «{origen}» into «{destino}»",
    "doctor.phase_identidad.bloqueada.detail": "{motivo}",
    "doctor.phase_identidad.bloqueada.action": "if they're the same person, merge them in the Users section",
    "doctor.phase_identidad.motivo.deshecha": "you undid that merge on this machine",
    "doctor.phase_identidad.motivo.formato": "a profile has a format Workspace doesn't understand",
    "doctor.phase_identidad.motivo.ajena": "it has tabs marked with another person's ID ({cedula})",
    "doctor.phase_identidad.id_repetido": "two brains have the same id: {agentes}",
    "doctor.phase_identidad.id_repetido.detail": "one is a copy of the other (STATE/cerebro.md)",
    "doctor.phase_identidad.id_repetido.action": "in the copy, delete STATE/cerebro.md: Workspace gives it a new one when needed",
    "doctor.phase_identidad.override": "[{agente}] here you're still «{nombre}»",
    "doctor.phase_identidad.override.detail": "what this brain already said on this machine · change it with «that's me on this PC» in the Users section",
    "doctor.phase_identidad.error_cerebro": "[{agente}] couldn't check who you are here",
    "doctor.phase_identidad.error_cerebro.detail": "{error}",
    "doctor.phase_identidad.error_cerebro.action": "everything else was checked anyway; run `workspace doctor` again",
    "doctor.phase_identidad.error": "couldn't check who you are in your brains",
}
