# Desinstalar

```bash
workspace uninstall
```

Te muestra qué va a borrar y te pide confirmación.

- `workspace uninstall --dry-run` — solo enseña qué borraría; no toca nada.
- `workspace uninstall --keep-folder` — quita todo de tu máquina pero **conserva la carpeta**
  de Workspace.

## Qué se borra

- El comando `workspace` y los comandos de cada agente.
- La configuración local de Workspace en `~/.claude/workspace/` (ajustes, atajos, temas
  elegidos, estado de esta máquina).
- Lo que el instalador añadió a tu terminal (PATH y menú al abrir; en Windows, el bloque del
  perfil de PowerShell).
- El tema que instaló dentro de Claude Code, si lo hizo.
- La carpeta de Workspace (salvo `--keep-folder`).

## Qué NO se borra

- **Los cerebros de tus agentes** (sus carpetas): son tuyos y viven aparte.
- Las conversaciones guardadas por cada motor.
- Los motores (Claude Code, Codex, Antigravity) ni sus sesiones.

## Respaldo y protecciones

- Antes de borrar te muestra la lista **SE BORRA / SE CONSERVA / RESPALDO**, con cada cerebro
  por su nombre.
- Te ofrece un **respaldo** de tus ajustes en un zip en el Escritorio (`--no-backup` para no
  hacerlo). El respaldo **no lleva tus claves ni tokens**: al reinstalar las vuelves a pegar.
  Si el respaldo falla, no se borra nada.
- **Se niega a borrar** una carpeta que no parece de Workspace (sin sus archivos propios), tu
  carpeta personal, la raíz del disco o una carpeta que contenga un cerebro. En ese caso no
  borra nada y te dice por qué.

Reinstalar es el mismo comando de [Instalar](instalar.md); después, vuelve a cargar tus
agentes con **Agregar agente**.
