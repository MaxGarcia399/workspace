---
name: personalizar-workspace
description: "Cómo {{AGENT_DISPLAY}} cambia el tema, el tono y el idioma de Workspace cuando el socio lo pide. El tema y el idioma se cambian en el hub (Ajustes); el tono, también con workspace tono. No inventes un comando de tema que la ayuda no trae."
version: 1.1.0
category: meta
tags: [meta, workspace, tema, tono, idioma]
created: {{DATE}}
created_by: {{AGENT_NAME}}
last_improved: {{DATE}}
used_count: 0
---

# Personalizar Workspace — {{AGENT_DISPLAY}}

El tema y el idioma pintan el hub. El tono es cómo te hablan los agentes.
Ninguno se edita a mano en un JSON.

## Cuándo usarla
- «Pon el tema oscuro», «cambia el fondo», «háblame más corto», «pásalo a inglés».

## Comandos

Tema y fondo, en el hub: **Ajustes › Apariencia**. El idioma: **Ajustes ›
General**. Ahí el socio elige el valor.

No hay un comando `workspace` para el tema ni para el idioma, y desde tu cerebro
no conoces la carpeta de Workspace: no corras ningún script suelto. Dile al socio
dónde cambiarlo (abre `workspace`, entra a Ajustes › Apariencia) y espera a que lo
haga.

Temas que acepta el hub: rose, mono, blanco, cyberpunk, durazno, lavanda, salvia,
bruma. Idioma: `es` o `en`. Fondo: tema, negro, grafito, azul, verde, violeta,
personalizado (con su color). Si `WORKSPACE_LANG` o `WORKSPACE_THEME` están
puestos, ganan sobre lo guardado. Dentro de herdr el tema lo manda herdr.

Tono. En el hub está en **Agentes › Tono**; eso abre también `workspace tono`
sin nada más. Con argumentos es texto (la ayuda de `workspace tono --help`):

`workspace tono ver`

`workspace tono <dial> <1-5>`

`workspace tono preset cliente`

`workspace tono reset`

Diales: amabilidad, franqueza, sarcasmo, humor, longitud, formalidad,
tecnicismo, didactica, iniciativa, emojis. 3 es neutro. Presets: cliente,
express, maestro, taller. Para un solo agente, el nombre va antes del dial:
`workspace tono <agente> <dial> <1-5>`.

## Qué no hacer
- No editar a mano los archivos que Workspace administra (`tono.json`, los
  ajustes guardados, el tema dentro de un motor).
- No tocar llaves en texto plano. El tema no necesita ninguna.
- No publicar. Cambiar el tema no es un release.
- No inventes un comando de tema ni de idioma: no están en la ayuda de workspace.
- Pide confirmación al socio antes de `workspace tono preset <nombre>` y de
  `workspace tono reset`: cambian muchos diales de golpe, y sin nombre de agente
  valen para todos. Lo mismo para `workspace tono <dial> <1-5>` sin agente.

## Cómo comprobar
- `workspace tono ver` muestra ese dial en el número pedido.
- En el hub, Ajustes › Apariencia y Ajustes › General muestran el tema y el
  idioma que el socio eligió.

## Preferencias del equipo
**(sin preferencias registradas)**
