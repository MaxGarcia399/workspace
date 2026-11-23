# Instalar

## Antes de empezar

Necesitas tres cosas:

1. **Python 3.9 o más nuevo.** En Windows el comando es `python`; en Mac/Linux, `python3`.
2. **Git.**
3. **Al menos un motor** instalado y con tu sesión iniciada: **Claude Code** (`claude`),
   **Codex** (`codex`), **Antigravity** (`agy`), **OpenCode** (`opencode`), **OpenClaw**
   (`openclaw`), **Hermes** (`hermes`), **Kiro** (`kiro-cli`), **GitHub Copilot** (`copilot`) o
   **Cursor** (`cursor-agent`). Si todavía no tienes ninguno, el primer arranque te ayuda a
   instalarlo.

No hace falta `pip install` ni nada más: Workspace no tiene dependencias.

## macOS / Linux

Un comando:

```bash
curl -fsSL https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.sh | bash
```

Lo instala en `~/Workspace`, fuera de tu Escritorio, Documentos y Descargas: así macOS no te
pide permiso para que la terminal entre a esas carpetas. Tus agentes nuevos nacen en
`~/Workspace/Cerebros`. Si ya tenías Workspace en otro lado (por ejemplo, en
`~/Desktop/Workspace`), el mismo comando lo detecta y lo actualiza ahí: no mueve nada. Si ya
tienes una carpeta `~/Workspace` con tus propios archivos, no la toca: te pide elegir otra con
`WORKSPACE_DIR="$HOME/Workspace-app"` delante del comando.

Mientras instala ves cuatro pasos (revisar tu Mac, descargar, preparar el comando y abrir
Workspace). Si a tu Mac le faltan las herramientas de Apple, abre su instalador y espera a que
termine; si se cae el internet, lo vuelve a intentar solo. Para ver todo lo que hace, en
detalle: `curl -fsSL … | bash -s -- --detalle` (lo mismo queda siempre en
`~/.claude/workspace/instalar.log`).

¿Prefieres ver qué corres antes de correrlo? Bien hecho. Haz lo mismo en dos pasos:

```bash
git clone https://github.com/MaxGarcia399/workspace.git ~/Workspace
python3 ~/Workspace/install.py
```

## Windows (PowerShell)

Un comando, en PowerShell:

```powershell
irm https://workspacecli.ai/install.ps1 | iex
```

Es el `setup.ps1` del repo y corre en tu misma ventana (no pide cambiar la política de
scripts). Lo instala en `%LOCALAPPDATA%\Workspace`. Si a tu Windows le falta Git o Python (o
los dos), te ofrece instalarlos con winget (el instalador de Microsoft) y solo lo hace si pulsas Enter.
En dos pasos, si prefieres revisar antes:

```powershell
git clone https://github.com/MaxGarcia399/workspace.git "$env:LOCALAPPDATA\Workspace"
python "$env:LOCALAPPDATA\Workspace\install.py"
```

**No lo instales dentro de OneDrive** (tampoco en un Escritorio o Documentos que OneDrive
sincroniza). El instalador lo rechaza a propósito: la sincronización bloquea archivos y rompe
Workspace. Al terminar, Workspace se abre en la misma ventana y el comando `workspace` ya
funciona ahí (y en PowerShell, cmd.exe y la terminal de VS Code).

## Qué toca el instalador

Solo **tu máquina**: deja el comando `workspace`, conecta los avisos que necesitan los motores
y guarda tu configuración local en `~/.claude/workspace/`. No crea cuentas ni envía nada.

¿Te salió un aviso del sistema (permisos, «posible malware», administrador)? En
[Avisos de tu sistema](avisos.md) está qué es cada uno y qué contestar.

## Siguiente paso

Workspace se abre solo al terminar de instalar, en la misma ventana (en Mac y Linux, desde
entonces, cada terminal nueva lo abre). Si no, escribe `workspace` → [Primer arranque](primer-arranque.md).
