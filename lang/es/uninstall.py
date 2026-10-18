"""WORKSPACE · lang/es/uninstall — desinstalador (uninstall.py): guardas, plan
(qué se borra / qué se conserva) y respaldo.

FUENTE (español): literales EXACTOS de uninstall.py. Ver `lang/README.md`.
"""

STRINGS = {
    "uninstall.ask_backup": "¿Creo el respaldo antes de borrar? [S/n]: ",
    "uninstall.ask_sure": "¿Seguro? escribe 'si' para continuar: ",
    "uninstall.backup_fail": "No pude crear el respaldo ({e}). Nada fue borrado. Para "
                             "seguir sin respaldo: --no-backup.",
    "uninstall.backup_ok": "respaldo creado: {p} (trae tus ajustes y credenciales locales: guárdalo en privado)",
    "uninstall.backup_where": "Tu respaldo: {p}",
    "uninstall.cancelled": "Cancelado. Nada fue borrado.",
    "uninstall.dry_backup": "crearía el respaldo: {p}",
    "uninstall.guard.brain": "contiene el cerebro «{n}» ({b})",
    "uninstall.guard.home": "es tu carpeta personal (o la contiene)",
    "uninstall.guard.no_app": "no es la app de Workspace",
    "uninstall.guard.no_harness": "no tiene los marcadores de Workspace (front.py, "
                                  "dispatch.py, install.py)",
    "uninstall.guard.no_state": "no tiene ningún archivo de estado de Workspace",
    "uninstall.guard.notdir": "no es una carpeta",
    "uninstall.guard.relative": "no es una ruta absoluta",
    "uninstall.guard.root": "es la raíz de un disco",
    "uninstall.hint_folder": "Si es otra carpeta: --workspace <ruta>. Para desinstalar "
                             "sin tocarla: --keep-folder.",
    "uninstall.kept_inside": "conservado: {p}",
    "uninstall.label.state": "estado per-máquina",
    "uninstall.label.state_item": "estado",
    "uninstall.no_root": "no encuentro la carpeta del harness en {p} (nada que borrar "
                         "ahí; usa --workspace <ruta> si está en otro lado)",
    "uninstall.nothing": "Nada fue borrado.",
    "uninstall.plan.app": "app de escritorio: {p}",
    "uninstall.plan.backup": "RESPALDO",
    "uninstall.plan.backup_to": "estado per-máquina → {p} (sin tus claves ni tokens: se vuelven a pegar al reinstalar)",
    "uninstall.plan.brain": "cerebro «{n}»: {b}",
    "uninstall.plan.brains": "tus cerebros (carpetas de agentes), estén donde estén",
    "uninstall.plan.cc_settings": "tu ~/.claude/settings.json (solo se quitan las claves "
                                  "que puso Workspace)",
    "uninstall.plan.delete": "SE BORRA",
    "uninstall.plan.engines": "las conversaciones y logins de cada motor (Claude Code, "
                              "Codex, …) y los propios motores",
    "uninstall.plan.engines_clean": "las conversaciones de los perfiles de Workspace en "
                                    "OpenClaw y Hermes, en una carpeta de respaldo al lado de "
                                    "cada perfil (ver abajo)",
    "uninstall.plan.harness": "carpeta del harness: {p}",
    "uninstall.plan.harness_kept": "carpeta del harness (--keep-folder): {p}",
    "uninstall.plan.keep": "SE CONSERVA (no se toca)",
    "uninstall.plan.no_backup": "sin respaldo (--no-backup)",
    "uninstall.plan.nothing_to_backup": "nada que respaldar (no hay estado)",
    "uninstall.plan.state": "estado per-máquina (ajustes, atajos, agentes registrados): {p}",
    "uninstall.plan.tbackup": "respaldo de transcripts: {p}",
    "uninstall.plan.themes": "temas de Workspace en ~/.claude/themes",
    "uninstall.plan.launchers": "en ~/.local/bin, solo estos (llevan la marca del "
                                "instalador): {n}",
    "uninstall.plan.theme_files": "en ~/.claude/themes, solo estos (los generó Workspace): {n}",
    "uninstall.plan.unix": "comando `workspace` y launchers en ~/.local/bin; bloques de "
                           "Workspace en ~/.zshrc",
    "uninstall.plan.win": "comandos de Workspace en tu $PROFILE de PowerShell",
    "uninstall.refused": "Me niego a borrar {p}: {why}.",
    "uninstall.usage": "uso: python3 uninstall.py [--dry-run] [--keep-folder] [--workspace <ruta>]\n"
                       "                          [--yes|-y] [--backup|--no-backup] [--limpiar-todo]\n"
                       "  Desinstala Workspace de esta máquina; tus cerebros y conversaciones se quedan.\n"
                       "  --dry-run muestra qué borraría, sin tocar nada.\n"
                       "  --limpiar-todo quita también lo que Workspace escribió en cerebros y motores.",
    "uninstall.x.rm_path.1": "borraría {label}: {p}",
    "uninstall.x.rm_path.2": "{dim}no pude borrar {p} ({e}){r}",
    "uninstall.x.strip_zshrc.1": "limpiaría los bloques de WORKSPACE de {rc}",
    "uninstall.x.strip_zshrc.2": "~/.zshrc limpiado (PATH + greeter de WORKSPACE)",
    "uninstall.x.strip_profile_windows.1": "limpiaría los marcadores de WORKSPACE de {prof}",
    "uninstall.x.strip_profile_windows.2": "$PROFILE limpiado (marcadores WORKSPACE): {prof}",
    "uninstall.x.reset_theme.1": "quitaría theme={th} de ~/.claude/settings.json",
    "uninstall.x.reset_theme.2": "theme {th} removido de ~/.claude/settings.json",
    "uninstall.x.restore_retention.1": "restauraría cleanupPeriodDays={prior!r} en {sp}",
    "uninstall.x.restore_retention.2": "cleanupPeriodDays restaurado ({v})",
    "uninstall.x.main.1": "\n  {b}{c}Desinstalador de WORKSPACE{r}  {dim}· {v} · {root}{r}",
    "uninstall.x.main.2": "app de escritorio",
    "uninstall.x.main.3": "{dim}carpeta del harness conservada (--keep-folder): {root}{r}",
    "uninstall.x.main.4": "{dim}aviso: {root} no parece un harness WORKSPACE (sin front.py/dispatch.py/install.py) — NO borro la carpeta. Usa --workspace <ruta> si es otra.{r}",
    "uninstall.x.main.5": "carpeta del harness",
    "uninstall.x.main.6": "\n  {c}Listo.{r} WORKSPACE desinstalado de esta máquina.",
    "uninstall.x.main.7": "  {dim}Los CEREBROS (carpetas de agentes) y los transcripts NO se tocaron.{r}",
    "uninstall.x.main.8": "  {dim}Abre una terminal NUEVA para soltar el PATH/greeter viejos.{r}",
    "uninstall.x.main.9": "  {dim}Si vuelves a instalar Workspace, carga de nuevo cada agente (Agregar agente → cargar su carpeta) para que apunte a la instalación nueva; si restauraste tu respaldo, basta con `workspace doctor`.{r}",
    "uninstall.x.rm_path.4": "quedaron archivos en uso",
    "uninstall.x.rm_path.3": "{label} borrado: {p}",
    "uninstall.x.no_value": "sin valor",
    "uninstall.x.ps_cmds": "comandos PowerShell",
    "uninstall.x.theme": "tema {n}",
    # checkout de git con trabajo sin publicar · sin terminal (B02)
    "uninstall.git.no_git": "no pude comprobar si tiene trabajo sin publicar (git no está instalado)",
    "uninstall.git.fail": "no pude comprobar con git si tiene trabajo sin publicar ({e})",
    "uninstall.git.changes": "{n} cambio(s) sin commit",
    "uninstall.git.commits": "{n} commit(s) sin push",
    "uninstall.git.stashes": "{n} stash(es) guardado(s)",
    "uninstall.plan.harness_git": "carpeta del harness: {p} — es un checkout de git con trabajo "
                                  "sin publicar ({w}); bórrala tú cuando lo hayas guardado",
    "uninstall.x.main.git": "{dim}carpeta del harness conservada: {root} — tiene trabajo de git "
                            "sin publicar ({w}).{r}",
    "uninstall.need_yes": "Sin terminal interactiva no puedo pedirte confirmación. Nada fue "
                          "borrado. Para desinstalar así, añade --yes (y mira antes qué pasaría "
                          "con --dry-run).",
    # --limpiar-todo / --clean-all: cerebros y motores
    "uninstall.clean.ask": "¿Limpio también cerebros y motores? Se quita solo lo que "
                           "Workspace escribió en ellos, con respaldo al lado. Sus perfiles "
                           "de OpenClaw y Hermes, con tus conversaciones de ahí, se mueven a "
                           "una carpeta de respaldo junto a cada uno. El contenido de tus "
                           "cerebros no se toca [s/N]: ",
    "uninstall.clean.title": "TAMBIÉN SE LIMPIA (cerebros y motores: solo lo que escribió "
                             "Workspace)",
    "uninstall.clean.none": "nada: no queda nada de Workspace en tus cerebros ni en los motores",
    "uninstall.clean.brain": "cerebro «{n}»: {p}",
    "uninstall.clean.hooks": "hooks de Workspace ({k})",
    "uninstall.clean.statusline": "barra (statusLine)",
    "uninstall.clean.perms": "permisos de Workspace ({k} reglas)",
    "uninstall.clean.theme": "tema {t}",
    "uninstall.clean.pointer": "cerebro «{n}»: {f} generado por Workspace ({p})",
    "uninstall.clean.codex_trust": "Codex: {p} → confianza de {k} cerebro(s) ([projects.\"…\"])",
    "uninstall.clean.codex_theme": "Codex: tema {p}",
    "uninstall.clean.agy": "Antigravity: {p}",
    "uninstall.clean.agy_trust": "cerebros en trustedWorkspaces ({k})",
    "uninstall.clean.agy_rules": "reglas de archivos del cerebro ({k})",
    "uninstall.clean.agy_memoria": "reglas `workspace memoria …` ({k})",
    "uninstall.clean.agy_project": "Antigravity: proyecto {p}",
    "uninstall.clean.openclaw": "OpenClaw: perfil de Workspace {p} → se aparta (no se borra) "
                                "a {b}, con sus conversaciones y el proveedor que conectaste "
                                "ahí; tu OpenClaw personal no se toca",
    "uninstall.clean.oc_label": "perfil de OpenClaw",
    "uninstall.clean.hermes": "Hermes: perfil de Workspace {p} → se aparta (no se borra) a "
                              "{b}, con sus conversaciones y el proveedor que conectaste ahí; "
                              "tu Hermes personal no se toca",
    "uninstall.clean.moved": "{label} apartado con sus conversaciones (no se borró): {p} → {b}",
    "uninstall.clean.bak_exists": "ya existe {p}",
    "uninstall.clean.bak_missing": "el respaldo no quedó en {p}",
    "uninstall.clean.hm_left": "el perfil sigue ahí; su copia quedó en {b}",
    "uninstall.clean.hm_label": "perfil de Hermes",
    "uninstall.clean.backups": "cada archivo de configuración que cambia queda respaldado al "
                               "lado: <archivo>{b}",
    "uninstall.clean.keep": "SE CONSERVA AL LIMPIAR",
    "uninstall.clean.keep_claude": "el CLAUDE.md de cada cerebro (es el formato del cerebro: "
                                   "por él Claude Code lee BRAIN.md) y todo su contenido",
    "uninstall.clean.kept_user": "se deja (lo editaste o no lo escribió Workspace tal "
                                 "cual): {p}",
    "uninstall.clean.dry": "limpiaría: {what}",
    "uninstall.clean.done": "limpiado: {p} (respaldo: {b})",
    "uninstall.clean.fail": "{dim}no pude limpiar {p} ({e}){r}",
    "uninstall.clean.final": "  {dim}De los cerebros y los motores solo se quitó lo que escribió "
                             "Workspace, con respaldo al lado; el contenido de tus cerebros no "
                             "se tocó.{r}",
    "uninstall.clean.final_moved": "  {dim}Las conversaciones de {p} siguen en {b}{r}",
}
