# users/ — perfil de trato por socio

`<socio>.md` (un archivo por socio/dueño): cómo quiere ese socio que {{AGENT_DISPLAY}} trabaje con
él — tono, nivel de detalle, frecuencia, formato preferido. Misma convención de `STATE/users/` que
el resto de los cerebros del equipo.

El socio activo de esta máquina lo dice `.claude/socio.local`, que escribe Workspace (al instalar
o con «soy yo en esta PC» en Usuarios), nunca a mano. `WORKSPACE_WS`/`{{AGENT_UPPER}}_WS` es la
pestaña, no el usuario. Workspace crea el perfil (al crear el agente o, si falta, al abrirlo);
{{AGENT_DISPLAY}} llena el cuerpo con las preferencias de trato (~1500 caracteres) y, mientras
esté vacío, opera con su default (BOOT/00-SOUL §Mi voz).

**Cédula (Workspace, 2026-10-17).** Cada perfil empieza con un frontmatter que pone Workspace:
`id` (fijo, nunca cambia), `nombre`, `alias` (nombres anteriores), `creado` y `revision`. Las
pestañas del socio llevan la misma marca (`socio_id`). Crear, renombrar, unir dos usuarios o elegir
«soy yo en esta PC» se hace en la sección **Usuarios** del hub — nunca a mano: así otra máquina que
todavía use un nombre viejo entra sola al usuario correcto. El texto debajo del frontmatter es del
socio y el agente; Workspace no lo toca. Así empieza un perfil:

```markdown
---
id: u-3f9a2c
nombre: ana
alias: []
creado: 2026-10-17
revision: 1
---

# Ana — cómo trabajar conmigo
```

*(sin perfiles aún — los crea Workspace; el cuerpo se llena con el feedback real de cada socio,
no con datos de ejemplo)*
