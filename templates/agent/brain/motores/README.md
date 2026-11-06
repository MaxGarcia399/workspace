# motores/ — espacio propio de cada motor

Este cerebro es el mismo para todos los motores (Claude Code, Codex, Antigravity, opencode,
OpenClaw…). La identidad vive en `BRAIN.md`; la memoria, las reglas, las skills y el
conocimiento viven en `BOOT/`, `STATE/`, `skills/` y `wiki/`, y todos los motores los comparten.

Si algún día un motor necesita guardar archivos propios **dentro** del cerebro, van aquí, en
una subcarpeta con su nombre: `motores/<motor>/` (por ejemplo `motores/openclaw/`). Nunca sueltos
en la raíz: ahí un archivo con el nombre que un motor busca (`SOUL.md`, `IDENTITY.md`,
`HEARTBEAT.md`, `MEMORY.md`, `HERMES.md`…) competiría con la identidad común.

Quién la usa hoy:

- `motores/claude-code/memoria/<socio>/` — la memoria automática propia de Claude Code, una
  carpeta por persona. Workspace se la indica al abrirlo (`--settings` con `autoMemoryDirectory`,
  solo para esa sesión), así viaja con el cerebro a otras máquinas en vez de quedarse en una. En
  un cerebro compartido, el Claude Code de cada socio carga solo la suya y no confunde de quién
  es. La primera vez en cada máquina se copia aquí la que ya tenía; la original no se toca. Se
  apaga en Ajustes (`cerebro.claude_memoria_en_cerebro`).
- `motores/claude-code/conversaciones/<socio>/` — solo si este cerebro lo permite (viene
  apagado; se prende por cerebro con `workspace sesiones conversacion on`): al cerrar una
  pestaña, su conversación de Claude Code se guarda aquí comprimida para retomarla en tu otra
  máquina, y al abrir solo se trae la tuya. En un cerebro compartido, todos los que lo usan
  pueden ver esas conversaciones: para privacidad, usa un cerebro aparte. No sube si pesa más
  que el tope o si trae algo que parece una llave, y el `.gitignore` la deja fuera de git.
- `motores/openclaw/` — si OpenClaw deja su memoria suelta en la raíz (`MEMORY.md`, `memory/`)
  durante una sesión, Workspace la **mueve** aquí al cerrar (nunca la borra).

Los demás motores no guardan nada propio en el cerebro: usan la memoria de Workspace
(`STATE/sessions/`, ver su README). `workspace doctor` avisa si encuentra alguno de esos nombres
suelto en la raíz y sugiere moverlo aquí.
