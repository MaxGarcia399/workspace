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
    "uninstall.plan.harness": "carpeta del harness: {p}",
    "uninstall.plan.harness_kept": "carpeta del harness (--keep-folder): {p}",
    "uninstall.plan.keep": "SE CONSERVA (no se toca)",
    "uninstall.plan.no_backup": "sin respaldo (--no-backup)",
    "uninstall.plan.nothing_to_backup": "nada que respaldar (no hay estado)",
    "uninstall.plan.state": "estado per-máquina (ajustes, atajos, agentes registrados): {p}",
    "uninstall.plan.tbackup": "respaldo de transcripts: {p}",
    "uninstall.plan.themes": "temas de Workspace en ~/.claude/themes",
    "uninstall.plan.unix": "comando `workspace` y launchers en ~/.local/bin; bloques de "
                           "Workspace en ~/.zshrc",
    "uninstall.plan.win": "comandos de Workspace en tu $PROFILE de PowerShell",
    "uninstall.refused": "Me niego a borrar {p}: {why}.",
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
    "uninstall.x.rm_path.3": "{label} borrado: {p}",
    "uninstall.x.no_value": "sin valor",
    "uninstall.x.ps_cmds": "comandos PowerShell",
    "uninstall.x.theme": "tema {n}",
}
