# Instalar

## Antes de empezar

Necesitas tres cosas:

1. **Python 3.9 o más nuevo.** En Windows el comando es `python`; en Mac/Linux, `python3`.
2. **Git.**
3. **Al menos un motor** instalado y con tu sesión iniciada: **Claude Code** (`claude`),
   **Codex** (`codex`) o **Antigravity** (`agy`). Si todavía no tienes ninguno, el primer
   arranque te ayuda a instalarlo.

No hace falta `pip install` ni nada más: Workspace no tiene dependencias.

## macOS / Linux

Un comando:

```bash
curl -fsSL https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.sh | bash
```

Lo instala en `~/Desktop/Workspace`. Si ya había una carpeta ahí, la respalda antes.

¿Prefieres ver qué corres antes de correrlo? Bien hecho. Haz lo mismo en dos pasos:

```bash
git clone https://github.com/MaxGarcia399/workspace.git ~/Desktop/Workspace
python3 ~/Desktop/Workspace/install.py
```

## Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.ps1 -OutFile $env:TEMP\workspace-setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File $env:TEMP\workspace-setup.ps1
```

Lo instala en `%LOCALAPPDATA%\Workspace`. En dos pasos, si prefieres revisar antes:

```powershell
git clone https://github.com/MaxGarcia399/workspace.git "$env:LOCALAPPDATA\Workspace"
python "$env:LOCALAPPDATA\Workspace\install.py"
```

**No lo instales dentro de OneDrive** (tampoco en un Escritorio o Documentos que OneDrive
sincroniza). El instalador lo rechaza a propósito: la sincronización bloquea archivos y rompe
Workspace. Al terminar, **abre una terminal nueva** para que el comando `workspace` aparezca
(funciona en PowerShell, cmd.exe y la terminal de VS Code).

## Qué toca el instalador

Solo **tu máquina**: deja el comando `workspace`, conecta los avisos que necesitan los motores
y guarda tu configuración local en `~/.claude/workspace/`. No crea cuentas ni envía nada.

## Siguiente paso

Escribe `workspace` → [Primer arranque](primer-arranque.md).
