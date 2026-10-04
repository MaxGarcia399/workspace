# Adapter — Claude Code vía WORKSPACE (runtime primario)

Cómo opera {{AGENT_DISPLAY}} en este runtime:

- **Launcher:** `{{AGENT_NAME}}` (comando en `~/.local/bin/`) o el menú `workspace`. El motor
  (dispatch, hooks, banners) vive en `~/Desktop/WORKSPACE/`; este cerebro es contenido.
- **Sesiones:** el picker (`{{AGENT_NAME}}-dashboard.py --pick`) exporta `WORKSPACE_WS` /
  `{{AGENT_UPPER}}_WS`; los hooks `session_start/end.py` inyectan y capturan la memoria de la
  pestaña (`STATE/sessions/<socio>/<slug>.md`).
- **Socio activo:** `.claude/socio.local` (lo escribe `workspace install <socio>`).
- **Statusline:** `agents/{{AGENT_NAME}}/brand/{{AGENT_NAME}}-statusline.py` — barras de
  contexto/uso bajo el input. Si no aparece: verificar `scripts.statusline` en `agent.json` y
  re-correr `python3 WORKSPACE/install.py <socio>` (pitfall conocido: sin esa clave no hay error,
  simplemente no sale).
- **File tools nativas** (Read, Grep, Glob) para el cerebro — no `cat`/`find` salvo necesidad.
- **Mantenimiento:** `workspace update` (pull-all + doctor) · `workspace doctor` (diagnóstico por
  fases; la fase 8 mide los core blocks de mi MEMORY contra sus cotas).
- **Skill loop automático:** hook `SessionEnd → WORKSPACE/hooks/skill_review.py` (cableado en
  `.claude/settings.local.json`, que es per-máquina y está gitignored).
