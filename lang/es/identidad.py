"""WORKSPACE · lang/es/identidad — quién eres en esta máquina (identidad.py) en
`workspace doctor` (fase 4d).

FUENTE (español): literales EXACTOS del código. Ver `lang/README.md`.
"""

STRINGS = {
    "doctor.phase.phase_identidad": "4d · Quién eres en cada cerebro (identidad de esta máquina)",
    "doctor.phase_identidad.persona": "en esta máquina eres «{nombre}»",
    "doctor.phase_identidad.persona.detail": "también: {alias} · cada cerebro te encuentra con tu usuario",
    "doctor.phase_identidad.persona.detail_solo": "cada cerebro te encuentra con tu usuario",
    "doctor.phase_identidad.persona_creada": "esta máquina ya sabe quién eres: «{nombre}»",
    "doctor.phase_identidad.persona_creada.detail": "vale para todos tus cerebros · se cambia con «soy yo en esta PC» en la sección Usuarios",
    "doctor.phase_identidad.sin_persona": "cada agente sabe quién eres como antes",
    "doctor.phase_identidad.sin_persona.detail": "esta máquina aún no tiene una identidad para todos tus cerebros: se guarda la primera vez que eliges «soy yo en esta PC» en Usuarios",
    "doctor.phase_identidad.no_sabe": "[{agente}] no sabe cuál de sus {n} usuarios eres en esta máquina",
    "doctor.phase_identidad.no_sabe.detail": "no tomo la carpeta de otra persona como tuya",
    "doctor.phase_identidad.no_sabe.action": "elige «soy yo en esta PC» en la sección Usuarios (vale para todos tus cerebros)",
    "doctor.phase_identidad.otra_persona": "[{agente}] este cerebro dice que aquí eres «{socio}», pero en esta máquina eres «{nombre}»",
    "doctor.phase_identidad.otra_persona.detail": "Workspace usa «{nombre}»",
    "doctor.phase_identidad.otra_persona.action": "si en este cerebro eres «{socio}», elige «soy yo en esta PC» en la sección Usuarios",
    "doctor.phase_identidad.duplicadas": "[{agente}] tienes dos usuarios separados: {nombres}",
    "doctor.phase_identidad.duplicadas.detail": "se unen solos al abrir el agente (o con `workspace doctor`), con respaldo y deshacer",
    "doctor.phase_identidad.unidas": "[{agente}] «{origen}» y «{destino}» eran tú: quedaron unidos",
    "doctor.phase_identidad.unidas.detail": "{n} pestaña(s) pasaron a «{destino}» y nada se borró · deshacer: {deshacer}",
    "doctor.phase_identidad.bloqueada": "[{agente}] no uní «{origen}» con «{destino}»",
    "doctor.phase_identidad.bloqueada.detail": "{motivo}",
    "doctor.phase_identidad.bloqueada.action": "si son la misma persona, únelos en la sección Usuarios",
    "doctor.phase_identidad.motivo.deshecha": "deshiciste esa unión en esta máquina",
    "doctor.phase_identidad.motivo.formato": "un perfil tiene un formato que Workspace no entiende",
    "doctor.phase_identidad.motivo.ajena": "tiene pestañas marcadas con la cédula de otra persona ({cedula})",
    "doctor.phase_identidad.id_repetido": "dos cerebros tienen el mismo id: {agentes}",
    "doctor.phase_identidad.id_repetido.detail": "uno es copia del otro (STATE/cerebro.md)",
    "doctor.phase_identidad.id_repetido.action": "en la copia, borra STATE/cerebro.md: Workspace le da uno nuevo cuando haga falta",
    "doctor.phase_identidad.override": "[{agente}] aquí sigues siendo «{nombre}»",
    "doctor.phase_identidad.override.detail": "lo que ya decía este cerebro en esta máquina · se cambia con «soy yo en esta PC» en la sección Usuarios",
    "doctor.phase_identidad.error_cerebro": "[{agente}] no pude revisar quién eres aquí",
    "doctor.phase_identidad.error_cerebro.detail": "{error}",
    "doctor.phase_identidad.error_cerebro.action": "lo demás se revisó igual; vuelve a correr `workspace doctor`",
    "doctor.phase_identidad.error": "no pude revisar quién eres en tus cerebros",
}
