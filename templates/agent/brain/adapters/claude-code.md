# Adapter — Claude Code vía WORKSPACE (runtime primario)

Cómo opera {{AGENT_DISPLAY}} en este runtime:

- **Launcher:** `{{AGENT_NAME}}` (comando en `~/.local/bin/`) o el menú `workspace`. El motor
  (dispatch, hooks, banners) vive en `~/Desktop/WORKSPACE/`; este cerebro es contenido.
- **Sesiones:** el picker (`{{AGENT_NAME}}-dashboard.py --pick`) exporta `WORKSPACE_WS` /
  `{{AGENT_UPPER}}_WS` (la pestaña). Al abrir (también al retomar y tras compactar), el hook de
  inicio me inyecta el paquete de la pestaña (resumen + Vigente + notas nuevas + maleta); al cerrar,
  `hooks/memoria_cierre.py` (código, sin IA) arma la maleta, sube `dato`/`preferencia` a
  `STATE/MEMORY.md` y compacta. Yo guardo con `workspace memoria nota` / `checkpoint`
  (ver `STATE/sessions/README.md`).
- **Memoria propia de Claude Code:** vive en el cerebro, `motores/claude-code/memoria/` (se apaga
  en Ajustes; ver `motores/README.md`).
- **Socio activo:** `.claude/socio.local` (lo escribe Workspace al instalar o con «soy yo en esta
  PC» en Usuarios; nunca a mano).
- **Statusline:** `agents/{{AGENT_NAME}}/brand/{{AGENT_NAME}}-statusline.py` — barras de
  contexto/uso bajo el input. Si no aparece: verificar `scripts.statusline` en `agent.json` y
  re-correr `python3 WORKSPACE/install.py <socio>` (pitfall conocido: sin esa clave no hay error,
  simplemente no sale).
- **File tools nativas** (Read, Grep, Glob) para el cerebro — no `cat`/`find` salvo necesidad.
- **Mantenimiento:** `workspace update` (pull-all + doctor) · `workspace doctor` (diagnóstico por
  fases: revisa y repara lo esencial; no mide mi MEMORY, eso lo cuento yo al leerla).
- **Revisión de skills (opcional):** al cerrar, `WORKSPACE/hooks/skill_review.py` deja la
  revisión pendiente; al abrir la siguiente sesión me la entrega y la hago yo, a la vista
  (cableado en `.claude/settings.local.json`, que es per-máquina y está gitignored).
