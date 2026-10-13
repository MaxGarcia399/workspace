<!-- markdownlint-disable MD033 MD041 -->
<div align="center">

# Workspace

**A sovereign terminal OS for AI agents — built for the individual.**
*Un "sistema operativo" de terminal para agentes de IA — hecho para la persona.*

![License: MIT](https://img.shields.io/badge/license-MIT-black)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-black)
![Dependencies: none](https://img.shields.io/badge/dependencies-stdlib%20only-black)
![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-black)
![Status: early](https://img.shields.io/badge/status-early%20%2F%20upcoming-orange)

**[English](#english) · [Español](#español)**

</div>

---

<a id="english"></a>

## English

### What it is

Workspace runs **multiple AI agents from one terminal** — each with its own
**identity**, its own **brain** (a folder of plain files you keep), and the
**engine** you choose to run it. One place to launch them, keep their context,
and work.

```
Agent = identity + brain + engine + sections
```

### Mission

Workspace is a **platform for you — the individual — to create and to learn as
you go.** Two commitments drive every decision:

- **Transparency, all the way down.** You see what each piece does, why it does
  it, what it changes, and what it costs. No magic, no black boxes, no hidden
  conditions behind vague promises.
- **The individual, not the enterprise.** This is built 100% around a single
  person getting leverage from AI — owning their context and their tools — not
  around seat licenses, admin consoles, or lock-in. If a choice is good for the
  company but bad for the person, the person wins.

### Why it exists

Most AI tooling marries you to one vendor: your context, your history, and your
agents live inside someone else's product. Workspace takes the opposite bet.

- **You own the brain.** Each agent's knowledge lives in plain, legible files you
  keep — portable, inspectable, versionable. Not a vector database you can't read.
- **You choose the engine.** The loop that talks to the model is pluggable. It
  runs today on **Claude Code, Codex and Antigravity** (each through its own
  official CLI and your own login); other engines plug in **without reinventing
  the agent's identity.** Not every engine can do everything yet — the
  [compatibility matrix](manual/en/compatibility.md) says exactly what works where.
- **You stay in control.** Credentials are per-machine and never touch the repo.
  The harness fails soft — a broken piece never takes down your session.

Workspace owns the **ecosystem** (agents, brains, orchestration). It deliberately
does **not** rewrite the inference loop — that is inherited from the engine. The
independence comes from the pluggable engine, not from re-implementing the hard part.

### Features

- **Multi-agent launcher** — a terminal menu to pick and launch any agent, each
  with its own banner, theme, and flow.
- **Per-agent brains** — knowledge as folders of Markdown (identity, memory,
  skills, sessions). Readable, editable, yours.
- **Pluggable engines** — a documented contract (`engines/CONTRACT.md`); adding an
  engine is dropping a file. Claude Code, Codex and Antigravity ship today
  ([what works with each](manual/en/compatibility.md)).
- **Workflows** — declarative, multi-step procedures with a deterministic spine
  (`workflows/`): review code, create an agent, build a feature.
- **Doctor** — a phase-by-phase self-diagnosis and repair (`workspace doctor`).
- **Memory distillation** — background curation of long-term memory from session
  transcripts, with secret/PII gates.
- **Evals** — run an agent against a golden set in a sandbox and track results.
- **Security by tiers** — layered approval (drafts → apply → anything touching
  production); credentials gitignored, never committed; a build-time leak gate.
- **Voice, split terminal, inter-agent bus** — dictation, a side-by-side live
  panel, and a file-based message bus between agents.

> Status: **early / upcoming.** The core works end to end and is covered by a
> test suite; polish, the public roadmap, pricing, and audience are still being
> shaped. Expect rough edges, and surfaces that are scaffolding rather than finished.

### How it works

```
workspace  →  front.py  →  dispatch.py  →  engines/<engine>.launch()
              (menu+CLI)    (resolve brain,    (the loop that talks to
                            load config,        the model — inherited,
                            pick engine)        not rewritten)
```

### Project structure

```
front.py        # the door: menu + CLI (the `workspace` command)
dispatch.py     # <agent> → resolves brain → loads config → starts its engine
engines/        # pluggable engines + CONTRACT.md (the interface)
agents/         # registry + one folder per agent (agent.json)
hooks/          # event listeners (session start/end, …)
workflows/      # declarative multi-step procedures
install.py      # per-machine installer (writes only to your machine)
doctor.py       # phase-by-phase diagnose / repair
```

Brains do **not** live in this repo — each agent's brain is its own folder that
Workspace references.

### Install

One command (macOS / Linux):

```bash
curl -fsSL https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.sh | bash
```

Or clone and run the installer:

```bash
git clone https://github.com/MaxGarcia399/workspace.git ~/Desktop/Workspace
python3 ~/Desktop/Workspace/install.py
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.ps1 -OutFile $env:TEMP\workspace-setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File $env:TEMP\workspace-setup.ps1
```

Or clone and run the installer:

```powershell
git clone https://github.com/MaxGarcia399/workspace.git "$env:LOCALAPPDATA\Workspace"
python "$env:LOCALAPPDATA\Workspace\install.py"
```

On Windows the default location is `%LOCALAPPDATA%\Workspace`. **Do not install
under OneDrive** (a redirected Desktop/Documents counts): both `setup.ps1` and the
installer refuse cloud-synced paths, because sync locks break the harness. The
installer creates `workspace.cmd` in `%USERPROFILE%\.local\bin`, so the command
works in cmd.exe, PowerShell and the VS Code terminal; open a new terminal after
installing.

The installer is **per-machine**: it drops the `workspace` command, wires the
hooks, and writes only to your machine's local config — never to the shared repo.

**Requirements:** Python 3.9+, Git, and at least one engine CLI logged in with
your own account: **Claude Code** (`claude`), **Codex** (`codex`) or
**Antigravity** (`agy`). Claude Code is the most integrated today. On Windows use
`python` (not `python3`).

### Quickstart

```bash
workspace            # open the menu (pick an agent or a tool)
workspace doctor     # diagnose / repair the install
workspace --help     # every command
```

### Updates

Workspace keeps itself up to date, and **you choose how**:

- **Automatic** (the default): when you open an agent, at most once every 6 hours, it
  installs the new version, with a safety net. First it checks that the new
  version starts on your computer. If it doesn't, Workspace goes back to the one you had.
- **Notify only:** once a day it tells you a new version is out; you install
  it with `workspace update` when you want.
- **Off:** it never checks on its own.

Change it in the hub (**Updates** screen, key `a`) or with
`workspace update --auto auto|notify|off`. Whatever you pick, `workspace update`
installs on demand and `workspace update --rollback` takes you back. Updates
only change Workspace's code: your agents, brains and settings stay as they are.
More in [the manual](manual/en/updates.md).

### What's new in v0.2.0

- **A new hub, the Launcher:** one box with your agents and a menu that filters as you type;
  ← → switch an agent's engine. The box keeps its size, so the window can be as small as it.
- **Updates with a safety net, and optional.** Before using a new version,
  Workspace checks that it starts on your computer and goes back by itself if
  it doesn't. You choose whether updates are automatic, notify-only or off.
- **`workspace version`** shows your version and what changed; **`workspace doctor --bundle`**
  builds a diagnostic ZIP with your personal data blanked out.
- **Commands in Spanish and English**, a Commands screen that searches (`/`) and runs, and
  a user manual in `manual/`.
- **A safer install and uninstall:** the installer checks your computer before touching
  anything; uninstalling shows what goes and what stays, and offers a backup.

Full list: [CHANGELOG.en.md](CHANGELOG.en.md).

### Manual

The user manual lives in [`manual/`](manual/README.md) — short chapters in
[English](manual/en/README.md) and [Spanish](manual/es/README.md): install, first
run, the hub, engines, themes, updates, troubleshooting, uninstall and privacy.
What Workspace stands for, in ten lines: [the manifesto](manual/MANIFESTO.md).
Found a security problem? See [SECURITY.md](SECURITY.md) — please don't open a
public issue.

### Design principles

- **Zero dependencies.** Pure Python 3.9 standard library. No `pip install`.
- **Cross-platform, fail-soft.** macOS, Linux, Windows; errors degrade gracefully.
- **Your files, not a black box.** Brains are folders of Markdown you control.
- **Honest about limits.** No promises of perfect memory, universal auto-save, or
  lossless transfer between providers.

### License

[MIT](LICENSE). Copyright (c) 2026 The Workspace Authors.

---

<a id="español"></a>

## Español

### Qué es

Workspace corre **varios agentes de IA desde una terminal** — cada uno con su
**identidad**, su **cerebro** (una carpeta de archivos legibles que tú conservas),
y el **motor** que elijas para ejecutarlo. Un solo lugar para lanzarlos, conservar
su contexto y trabajar.

```
Agente = identidad + cerebro + motor + secciones
```

### Misión

Workspace es una **plataforma para ti —la persona— para crear y aprender sobre la
marcha.** Dos compromisos guían cada decisión:

- **Transparencia hasta el fondo.** Ves qué hace cada pieza, por qué, qué cambia
  y qué cuesta. Sin magia, sin cajas negras, sin condiciones escondidas detrás de
  promesas vagas.
- **El individuo, no la empresa.** Está pensado 100% en una sola persona sacándole
  provecho a la IA —dueña de su contexto y sus herramientas— no en licencias por
  asiento, consolas de admin ni lock-in. Si una decisión es buena para la empresa
  pero mala para la persona, gana la persona.

### Por qué existe

La mayoría de las herramientas de IA te casan con un proveedor: tu contexto, tu
historial y tus agentes viven dentro del producto de alguien más. Workspace
apuesta por lo contrario.

- **Eres dueño del cerebro.** El conocimiento de cada agente vive en archivos
  legibles que conservas — portables, inspeccionables, versionables. No una base
  vectorial que no puedes leer.
- **Eliges el motor.** El bucle que habla con el modelo es enchufable. Hoy corre
  sobre **Claude Code, Codex y Antigravity** (cada uno con su CLI oficial y tu
  propia sesión); otros motores se enchufan **sin reinventar la identidad del
  agente.** No todos los motores pueden todo todavía — la
  [matriz de compatibilidad](manual/es/compatibilidad.md) dice qué funciona dónde.
- **Mantienes el control.** Las credenciales son por-máquina y jamás tocan el
  repo. El harness falla-suave — una pieza rota nunca tumba tu sesión.

Workspace es dueño del **ecosistema** (agentes, cerebros, orquestación).
Deliberadamente **no** reescribe el bucle de inferencia — ese se hereda del motor.
La independencia viene del motor enchufable, no de reimplementar la parte difícil.

### Features

- **Lanzador multi-agente** — un menú de terminal para elegir y lanzar cualquier
  agente, cada uno con su banner, tema y flujo.
- **Cerebros por agente** — el conocimiento como carpetas de Markdown (identidad,
  memoria, skills, sesiones). Legible, editable, tuyo.
- **Motores enchufables** — un contrato documentado (`engines/CONTRACT.md`);
  agregar un motor es soltar un archivo. Claude Code, Codex y Antigravity ya
  vienen incluidos ([qué funciona con cada uno](manual/es/compatibilidad.md)).
- **Workflows** — procedimientos declarativos de varios pasos con un espinazo
  determinista (`workflows/`): revisar código, crear un agente, construir features.
- **Doctor** — autodiagnóstico y reparación por fases (`workspace doctor`).
- **Destilado de memoria** — curación en segundo plano de la memoria de largo
  plazo desde los transcripts, con gates de secretos/PII.
- **Evals** — corre un agente contra un golden set en un sandbox y guarda resultados.
- **Seguridad por tiers** — aprobación por capas (borradores → aplicar → cualquier
  cosa que toque producción); credenciales gitignored, nunca commiteadas; un gate
  de fuga en el build.
- **Voz, terminal partida, bus entre agentes** — dictado, un panel en vivo al
  costado, y un bus de mensajes por archivos entre agentes.

> Estado: **early / upcoming (temprano).** El núcleo funciona end-to-end y está
> cubierto por una suite de tests; el pulido, el roadmap público, el precio y el
> público objetivo aún se están definiendo. Habrá aristas, y partes que son andamio
> más que producto terminado.

### Cómo funciona

```
workspace  →  front.py  →  dispatch.py  →  engines/<motor>.launch()
              (menú+CLI)    (resuelve el       (el bucle que habla con
                            cerebro, carga      el modelo — heredado,
                            config, elige       no reescrito)
                            motor)
```

### Estructura del proyecto

```
front.py        # la puerta: menú + CLI (el comando `workspace`)
dispatch.py     # <agente> → resuelve cerebro → carga config → arranca su motor
engines/        # motores enchufables + CONTRACT.md (la interfaz)
agents/         # registry + una carpeta por agente (agent.json)
hooks/          # listeners por evento (inicio/fin de sesión, …)
workflows/      # procedimientos declarativos de varios pasos
install.py      # instalador per-máquina (solo escribe en tu máquina)
doctor.py       # diagnóstico / reparación por fases
```

Los cerebros **no** viven en este repo — el cerebro de cada agente es su propia
carpeta que Workspace referencia.

### Instalación

Un comando (macOS / Linux):

```bash
curl -fsSL https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.sh | bash
```

O clona y corre el instalador:

```bash
git clone https://github.com/MaxGarcia399/workspace.git ~/Desktop/Workspace
python3 ~/Desktop/Workspace/install.py
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.ps1 -OutFile $env:TEMP\workspace-setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File $env:TEMP\workspace-setup.ps1
```

O clona y corre el instalador:

```powershell
git clone https://github.com/MaxGarcia399/workspace.git "$env:LOCALAPPDATA\Workspace"
python "$env:LOCALAPPDATA\Workspace\install.py"
```

En Windows la ubicación por default es `%LOCALAPPDATA%\Workspace`. **No lo instales
bajo OneDrive** (un Escritorio/Documentos redirigido cuenta): `setup.ps1` y el
instalador rechazan rutas sincronizadas a la nube porque los bloqueos del sync rompen
el harness. El instalador crea `workspace.cmd` en `%USERPROFILE%\.local\bin`, así que
el comando funciona en cmd.exe, PowerShell y la terminal de VS Code; abre una terminal
nueva al terminar.

El instalador es **per-máquina**: deja el comando `workspace`, cablea los hooks y
solo escribe en la config local de tu máquina — nunca en el repo compartido.

**Requisitos:** Python 3.9+, Git, y al menos un CLI de motor con tu propia sesión
iniciada: **Claude Code** (`claude`), **Codex** (`codex`) o **Antigravity** (`agy`).
Hoy Claude Code es el más integrado. En Windows usa `python` (no `python3`).

### Inicio rápido

```bash
workspace            # abre el menú (elige un agente o una herramienta)
workspace doctor     # diagnostica / repara la instalación
workspace --help     # todos los comandos
```

### Actualizaciones

Workspace se mantiene al día solo, y **tú eliges cómo**:

- **Automáticas** (de inicio): al abrir un agente, como mucho una vez cada 6 horas,
  instala la versión nueva, con red de seguridad. Antes comprueba que esa versión
  arranca en tu computadora. Si no arranca, Workspace vuelve a la que tenías.
- **Solo avisar:** una vez al día te dice que hay versión nueva; la instalas con
  `workspace update` cuando quieras.
- **Apagadas:** nunca consulta por su cuenta.

Se cambia en el hub (pantalla **Actualizaciones**, tecla `a`) o con
`workspace update --auto auto|notify|off`. Elijas lo que elijas, `workspace update`
instala cuando lo pides y `workspace update --rollback` te regresa. Una actualización
solo cambia el código de Workspace: tus agentes, cerebros y ajustes se quedan como están.
Más en [el manual](manual/es/actualizaciones.md).

### Novedades de la v0.2.0

- **Un hub nuevo, el Lanzador:** una caja con tus agentes y un menú que se filtra al
  escribir; ← → cambian el motor de un agente. La caja no cambia de tamaño, así que la
  ventana puede ser tan chica como ella.
- **Actualizaciones con red de seguridad, y opcionales.** Antes de usar una versión
  nueva, Workspace comprueba que arranca en tu computadora y, si no, vuelve sola a la
  anterior. Tú eliges si las actualizaciones son automáticas, solo avisan o están apagadas.
- **`workspace version`** muestra tu versión y qué cambió; **`workspace doctor --bundle`**
  arma un ZIP de diagnóstico con tus datos personales tachados.
- **Comandos en español e inglés**, una pantalla Comandos que busca (`/`) y ejecuta, y un
  manual de uso en `manual/`.
- **Instalar y desinstalar más seguros:** el instalador revisa tu computadora antes de
  tocar nada; desinstalar muestra qué se va y qué se queda, y ofrece un respaldo.

Lista completa: [CHANGELOG.md](CHANGELOG.md).

### Manual

El manual de usuario vive en [`manual/`](manual/README.md) — capítulos cortos en
[español](manual/es/README.md) e [inglés](manual/en/README.md): instalar, primer
arranque, el hub, motores, temas, actualizaciones, diagnóstico, desinstalar y
privacidad. Lo que Workspace defiende, en diez líneas: [el manifiesto](manual/MANIFIESTO.md).
¿Encontraste un problema de seguridad? Lee [SECURITY.md](SECURITY.md) — por favor
no abras un issue público.

### Principios de diseño

- **Cero dependencias.** Python 3.9, solo biblioteca estándar. Sin `pip install`.
- **Cross-platform, falla-suave.** macOS, Linux, Windows; los errores degradan con
  gracia.
- **Tus archivos, no una caja negra.** Los cerebros son carpetas de Markdown que
  controlas.
- **Honesto sobre los límites.** Sin promesas de memoria perfecta, guardado
  universal automático, ni transferencia sin pérdida entre proveedores.

### Licencia

[MIT](LICENSE). Copyright (c) 2026 The Workspace Authors.
