# users/ — perfil de trato por socio

`<socio>.md` (un archivo por socio/dueño): cómo quiere ese socio que {{AGENT_DISPLAY}} trabaje con
él — tono, nivel de detalle, frecuencia, formato preferido. Misma convención de `STATE/users/` que
el resto de los cerebros del equipo.

El socio activo se resuelve por `.claude/socio.local` (lo escribe el instalador) o
`WORKSPACE_WS`/`{{AGENT_UPPER}}_WS`. Si el perfil no existe, {{AGENT_DISPLAY}} opera con su default
(BOOT/00-SOUL §Mi voz) y crea el perfil cuando el socio dé las primeras preferencias.

*(sin perfiles aún — se crean con el primer feedback de cada socio, no con datos de ejemplo)*
