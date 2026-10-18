# Memoria de sesión (por pestaña, por socio)

Un archivo por **sesión/pestaña** y por **socio**: la memoria de cada conversación de trabajo con
{{AGENT_DISPLAY}}, igual en todos los motores (Claude Code, Codex, opencode, OpenClaw, Hermes,
Antigravity). Complementa —no reemplaza— a `STATE/MEMORY.md` (memoria del agente) y
`STATE/log-recent.md` (índice cronológico).

**Reparto del trabajo** (memoria v1): el agente entiende y etiqueta, en su sesión visible; el
código de Workspace ordena, sin IA. Nada corre de noche ni sin ventana, y nadie tiene que
aprobar ni ordenar nada a mano.

## Árbol

```
STATE/sessions/
  README.md                       ← este archivo
  <socio>/<slug>.md               ← el diario de la pestaña: ## Vigente + ## Historial
  <socio>/checkpoints/<slug>.md   ← el resumen (con número de revisión) + history/
  <socio>/maleta/<slug>.md        ← lo último de cada motor, para seguir en otro
  <socio>/archivo/<slug>-AAAA-MM.md  ← notas viejas que salieron del diario (nada se borra)
```

`<slug>` lo calcula Workspace: el nombre de la pestaña en kebab-case ASCII; si trae letras de
otro alfabeto (coreano, chino, cirílico…) lleva además un código corto estable (p. ej.
`tab-23185649`). No lo armes a mano: los comandos de abajo ya escriben en el archivo correcto.

## Cómo guarda el agente

Una línea por cosa, **en el momento**, con su etiqueta:

```
workspace memoria nota --tipo decision "usar el gateway en OpenClaw"
workspace memoria nota --tipo pendiente "probar Hermes"          → responde «P-3»
workspace memoria nota --tipo hecho --cierra P-3 "Hermes probado"
workspace memoria nota --tipo preferencia "abre los HTML en Opera GX"
```

| Etiqueta | Va a |
|---|---|
| `decision`, `pendiente` | **Vigente** (arriba del diario) hasta que se cierre con `--cierra` |
| `hecho`, `nota` | el **Historial**; lo viejo pasa al archivo del mes |
| `dato`, `preferencia` | además, a `STATE/MEMORY.md` (vale en todas las pestañas) |

Al terminar una unidad de trabajo o antes de cambiar de motor, el **resumen**:
`workspace memoria checkpoint --expected-revision <n> --objective … --decision … --blocker …
--next-step … --result …` (≤600 caracteres por campo; si hay conflicto, `workspace memoria status`
y reconciliar, nunca pisar).

**Si `workspace memoria nota` no existe** en la máquina (una versión anterior de Workspace
responde «invalid choice: 'nota'»), el agente agrega al final de `## Historial` una línea fechada
con el mismo formato: `- 2026-10-16 14:02 · codex · decisión: usar el gateway`. Al actualizar,
Workspace la lee como una nota más.

Fuera de ese caso, el agente **no edita** estos archivos a mano: Workspace escribe con candado,
así dos pestañas o dos motores a la vez no se pisan. Ver lo que hay: `workspace memoria ver` · `vigente` · `maleta`.

## Formato del diario

```markdown
---
sesión: <slug>
titulo: <nombre visible de la pestaña>
socio: <socio>
creada: YYYY-MM-DD
actualizada: YYYY-MM-DD
estado: activa | inactiva | archivada
---

# Sesión: <titulo>

## Resumen
[Opcional: 1-3 líneas.]

## Vigente
<!-- Workspace rehace esta lista solo … -->
- P-3 · pendiente (2026-10-16 · codex): probar Hermes
- D-1 · decisión (2026-10-03 · claude-code): usar el gateway

## Historial
- 2026-10-16 14:02 · codex · decisión D-1: usar el gateway
- 2026-10-16 14:05 · codex · pendiente P-3: probar Hermes
```

Las líneas de versiones anteriores (`- YYYY-MM-DD — texto`) se leen como notas y se conservan.

## Qué hace Workspace, solo y sin IA

- **Al abrir** una pestaña, en cualquier motor: el agente recibe un solo paquete — el resumen,
  lo vigente, las notas nuevas desde el resumen, la maleta si la pestaña viene de otro motor y
  cómo guardar. Si toca, le pide en una línea actualizar el resumen («mantenimiento»), y el agente
  lo hace a la vista.
- **Al cerrar** (también si la ventana se cerró con la X, en el siguiente arranque):
  - rehace la **maleta** con el extracto de la conversación (lo último que pidió el socio, la
    última respuesta, los archivos tocados; nada que parezca una llave);
  - sube `dato`/`preferencia` a `STATE/MEMORY.md` (sección «Aprendido en las sesiones»);
  - si el diario pasa de 30 notas u 8 KB, deja Vigente + las 10 más nuevas y mueve el resto,
    completo, a `archivo/`;
  - si `STATE/MEMORY.md` pasa de 200 líneas, o esa sección de 5 000 caracteres, lo más viejo
    de la sección va a `STATE/memoria-archivo/`.
- **Por socio:** solo se toca `STATE/sessions/<socio-activo>/`, nunca el de otro.

Si existen destilados viejos en `<socio>/<YYYY-MM>/` (versiones anteriores), siguen ahí, intactos.
