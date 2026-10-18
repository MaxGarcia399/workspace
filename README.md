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
  runs today on **six engines — Claude Code, Codex, Antigravity, OpenCode,
  OpenClaw and Hermes** (each through its own official CLI and your own login);
  others plug in **without reinventing the agent's identity.** Not every engine can do everything yet — the
  [compatibility matrix](manual/en/compatibility.md) says exactly what works where.
- **You stay in control.** Credentials are per-machine and never touch the repo.
  The harness fails soft — a broken piece never takes down your session.

Workspace owns the **ecosystem** (agents, brains, orchestration). It deliberately
does **not** rewrite the inference loop — that is inherited from the engine. The
independence comes from the pluggable engine, not from re-implementing the hard part.

### Features

What a fresh install gives you today:

- **One hub for all your agents** — `workspace` opens a terminal menu to create,
  load and launch agents; each agent also gets its own command. Every section
  shows only the essentials in one centered box, and `i` explains how it works.
- **Brains you own** — each agent's identity, memory, skills and sessions live in
  a folder of Markdown outside Workspace. Readable, editable, portable; updating
  or reinstalling Workspace never touches them.
- **Six engines** — Claude Code, Codex, Antigravity, OpenCode, OpenClaw and Hermes,
  each through its own CLI and your own login; switch an agent's engine from the hub. Claude
  Code is the most integrated ([what works with each](manual/en/compatibility.md)).
  Engines plug in through a documented contract (`engines/CONTRACT.md`).
- **Permissions per brain** — by default an agent reads, creates and edits files
  inside its own brain without asking you; for terminal commands, files outside
  its brain and the network it asks first (Codex runs commands inside its sandbox,
  which only lets it write to its brain and temporary folders, with no network).
  You can turn off that free access per agent in **Agents** (pick the agent and Enter). Nothing ever
  switches off the engine's protections.
- **Skills** — reusable procedures in each brain, looked up when a task needs
  them; when you create an agent you can fetch skills from public sources, and
  they are checked before being added. Skill review is **optional** (off by
  default, on in Agents (Enter on the agent)): when the next session opens, your
  agent reviews the previous one in plain sight; it uses a little of your
  subscription.
- **Doctor and safe updates** — `workspace doctor` checks the essentials and
  repairs what it can (`--bundle` makes a redacted zip to ask for help). Updates
  are automatic, notify-only or off; a new version is tested on your machine
  before it's used, and `workspace update --rollback` takes you back.
- **Workflows** — step-by-step procedures (`workspace wf`). The one meant for you
  today is creating an agent; the others are for developing Workspace itself.
- **The same memory in every engine** — each tab keeps its memory in the brain:
  the agent saves decisions, pending items and facts as it works, and on close
  Workspace tidies them up with plain code. Whichever engine opens that tab next
  starts from the same memory.
- **Users** — **Menu › Users** shows who uses each agent across your machines;
  Workspace records who you are on each one (at install, or with «that's me on
  this PC»).
- **Documentation** — **Menu › Documentation** explains everything Workspace
  does, chapter by chapter, with a simple map, what is happening on your PC
  right now and how to check it yourself.
- **Nothing runs without a window** — no AI process works behind your back: the
  agent saves its memory inside its visible session, and evals against a golden
  set run only when you ask (`workspace eval`, Claude Code).
- **Optional extras** — voice dictation (macOS only, `workspace voice --setup`)
  and a split terminal with a live panel (`workspace split`, needs tmux).

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
agents/         # empty registry (your agents live in their brains)
hooks/          # event listeners (session start/end, …)
workflows/      # declarative multi-step procedures
migrations/     # adjustments an update applies on your machine
manual/         # the user manual (English and Spanish)
install.py      # per-machine installer (writes only to your machine)
doctor.py       # phase-by-phase diagnose / repair
```

Brains do **not** live in this repo — each agent's brain is its own folder that
Workspace references; the agent's definition travels inside it
(`<brain>/.workspace/agent.json`).

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
your own account: **Claude Code** (`claude`), **Codex** (`codex`),
**Antigravity** (`agy`), **OpenCode** (`opencode`), **OpenClaw** (`openclaw`) or
**Hermes** (`hermes`). Claude Code is the most integrated today. On Windows use
`python` (not `python3`). Optional: tmux for the split terminal, macOS for voice
dictation.

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

Change it in the hub (**Updates**, the «automatic» row) or with
`workspace update --auto auto|notify|off`. Whatever you pick, `workspace update`
installs on demand and `workspace update --rollback` takes you back. Your agents,
brains and settings live outside the Workspace folder. When a version needs to
adjust something inside your brains (0.4.0, for example, moves your agents'
identity to `BRAIN.md`), it does it on its own, copies everything to a backup
first and deletes nothing; what you wrote yourself is left alone.
More in [the manual](manual/en/updates.md).

### What's new in v0.4.0

- **Each tab remembers the same thing on any engine.** Your agent saves what
  matters as it works (decisions, pending items, facts) and, when you open the
  tab on that engine or another, it starts from the same memory. Workspace
  tidies it up on its own, with no AI; nothing is deleted.
- **Two new sections.** **Users** shows who uses each agent across your
  machines (rename, merge, «that's me on this PC»). **Documentation** explains
  everything Workspace does, with what is happening on your PC right now.
- **No AI works without a window.** The "distiller" that summarized memory on
  its own is gone; skill review, if you turn it on, happens in your agent's
  session, in plain sight.
- **Nothing waits for your approval.** Your agent keeps its skills, memory and
  identity up to date on its own (it curates its skills once a week and
  completes its personality from what you told it), always recoverable, and
  tells you what it changed.
- **Your brains get a few changes when you update**, always with a backup
  first: your agents' identity moves to `BRAIN.md` (each engine still finds it),
  the memory instructions are brought up to date, and the old proposals tray
  (`STATE/DESTILADO.md`) moves to `STATE/memoria-archivo/`. Nothing is deleted.
- **More private.** Your account tokens and saved keys no longer reach the
  engines or what your agents run; telemetry and «get skills» start off.
- **Fixes.** Windows opens the menu on its own again when you open a terminal;
  `--help` never runs anything; uninstalling with «clean all» moves Workspace's
  OpenClaw and Hermes profiles (with your conversations) to a backup instead of
  deleting them, and only removes the terminal commands Workspace added; an
  engine that isn't installed no longer blocks its agent; closing with the X
  loses nothing; several OpenClaw agents can be open at once; on Windows,
  uninstalling really deletes the Workspace folder.

### What's new in v0.3.3

- **A fix.** The hub no longer shows the "setup unfinished" notice, which
  could stay even after you had finished the first run. To go through it
  again: `workspace onboarding`.

### What's new in v0.3.1

- **A simpler hub.** Every section shows only what you need, in one centered
  box; the explanation and its maps are behind `i`. Agents shows your agents
  with the options of the one you pick below and «+ add agent» at the end;
  Engines checks for real whether you're signed in; Updates shows only what you
  can do right then, including going back to the previous version; Commands
  opens each command's map on the right with `i`.
- **Less clutter.** Shortcuts left the menu (keys `1`–`9` follow your agents'
  order) and Google Calendar is paused while we improve it.

### What's new in v0.3.0

- **You choose how each agent works.** Creating or loading an agent offers two
  switches: reading and writing its own brain without asking (on: it's its main
  job; for everything else it asks you) and automatic skill review (off). Change
  them anytime in **Agents** (pick the agent and Enter).
- **No more blanket permissions for Claude Code agents.** The installer used to let
  every agent run any command without asking. Updating switches your agents to
  "free only inside their brain" on its own. Auto-accept edits is now off by default.
- **Skill review is optional and works with all three engines** — off by default;
  when on, the agent's own engine (Claude Code, Codex or Antigravity) does it in
  the background and uses a little of your subscription.
- **The doctor checks and repairs only the essentials** — your agents, their hooks
  and commands, git/Python/the engine you use, and updates — and fixes hooks that
  point to a Workspace folder that no longer exists.
- **Simpler install, sessions kept for a year** (it was ten): no "Who are you?"
  question, and it asks for the CLI of the engine you'll use. A retention you
  chose yourself is never touched.

Full list: [CHANGELOG.en.md](CHANGELOG.en.md).

### Manual

The user manual lives in [`manual/`](manual/README.md) — short chapters in
[English](manual/en/README.md) and [Spanish](manual/es/README.md): install, first
run, the hub, engines, what works with each engine, commands, themes, updates,
troubleshooting, uninstall and privacy.
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
  sobre **seis motores: Claude Code, Codex, Antigravity, OpenCode, OpenClaw y
  Hermes** (cada uno con su CLI oficial y tu propia sesión); otros se enchufan
  **sin reinventar la identidad del agente.** No todos los motores pueden todo todavía — la
  [matriz de compatibilidad](manual/es/compatibilidad.md) dice qué funciona dónde.
- **Mantienes el control.** Las credenciales son por-máquina y jamás tocan el
  repo. El harness falla-suave — una pieza rota nunca tumba tu sesión.

Workspace es dueño del **ecosistema** (agentes, cerebros, orquestación).
Deliberadamente **no** reescribe el bucle de inferencia — ese se hereda del motor.
La independencia viene del motor enchufable, no de reimplementar la parte difícil.

### Features

Lo que te da una instalación nueva hoy:

- **Un hub para todos tus agentes** — `workspace` abre un menú de terminal para
  crear, cargar y lanzar agentes; cada agente tiene además su propio comando.
  Cada sección muestra solo lo esencial en una caja centrada, y `i` explica cómo
  funciona.
- **Cerebros que son tuyos** — la identidad, memoria, skills y sesiones de cada
  agente viven en una carpeta de Markdown fuera de Workspace. Legibles, editables,
  portables; actualizar o reinstalar Workspace no los toca.
- **Seis motores** — Claude Code, Codex, Antigravity, OpenCode, OpenClaw y Hermes, cada
  uno con su propio CLI y tu propia sesión; cambias el motor de un agente desde el hub. Claude Code es el
  más integrado ([qué funciona con cada uno](manual/es/compatibilidad.md)). Los
  motores se enchufan con un contrato documentado (`engines/CONTRACT.md`).
- **Permisos por cerebro** — de entrada, un agente lee, crea y edita archivos
  dentro de su cerebro sin preguntarte; para comandos de terminal, archivos fuera
  de su cerebro y la red te pregunta antes (Codex corre comandos dentro de su caja,
  que solo le deja escribir en su cerebro y en carpetas temporales, sin red). Ese
  acceso libre se apaga por agente en **Agentes** (elige el agente y Enter). Nada desactiva las
  protecciones del motor.
- **Skills** — procedimientos reutilizables en cada cerebro, que el agente consulta
  cuando una tarea los necesita; al crear un agente puedes traer skills de fuentes
  públicas, revisadas antes de agregarse. La revisión de skills es **opcional**
  (viene apagada, se prende en Agentes (Enter sobre el agente)): al abrir la siguiente
  sesión, tu agente revisa la anterior a la vista; usa un poco de tu suscripción.
- **Doctor y actualizaciones seguras** — `workspace doctor` revisa lo esencial y
  repara lo que puede (`--bundle` arma un zip con tus datos tachados para pedir
  ayuda). Las actualizaciones son automáticas, solo-avisar o apagadas; una versión
  nueva se prueba en tu máquina antes de usarse y `workspace update --rollback` te
  regresa.
- **Workflows** — procedimientos paso a paso (`workspace wf`). El que es para ti hoy
  es crear un agente; los demás son para desarrollar el propio Workspace.
- **La misma memoria en todos los motores** — cada pestaña guarda su memoria en
  el cerebro: el agente anota decisiones, pendientes y datos mientras trabaja, y
  al cerrar Workspace los ordena con código. El motor que abra esa pestaña
  después arranca con la misma memoria.
- **Usuarios** — **Menú › Usuarios** muestra quién usa cada agente en todas tus
  máquinas; Workspace registra quién eres en cada una (al instalar, o con «soy yo
  en esta PC»).
- **Documentación** — **Menú › Documentación** explica todo lo que hace
  Workspace, capítulo por capítulo, con un mapa simple, lo que está pasando ahora
  en tu PC y cómo comprobarlo tú.
- **Nada corre sin ventana** — ningún proceso con IA trabaja a tus espaldas: el
  agente guarda su memoria dentro de su sesión visible, y los evals contra un set
  de referencia corren solo cuando tú lo pides (`workspace eval`, Claude Code).
- **Extras opcionales** — dictado por voz (solo macOS, `workspace voice --setup`)
  y terminal partida con un panel en vivo (`workspace split`, requiere tmux).

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
agents/         # registro vacío (tus agentes viven en sus cerebros)
hooks/          # listeners por evento (inicio/fin de sesión, …)
workflows/      # procedimientos declarativos de varios pasos
migrations/     # ajustes que una actualización aplica en tu máquina
manual/         # el manual de usuario (español e inglés)
install.py      # instalador per-máquina (solo escribe en tu máquina)
doctor.py       # diagnóstico / reparación por fases
```

Los cerebros **no** viven en este repo — el cerebro de cada agente es su propia
carpeta que Workspace referencia; la definición del agente viaja dentro de él
(`<cerebro>/.workspace/agent.json`).

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
iniciada: **Claude Code** (`claude`), **Codex** (`codex`), **Antigravity** (`agy`),
**OpenCode** (`opencode`), **OpenClaw** (`openclaw`) o **Hermes** (`hermes`).
Hoy Claude Code es el más integrado. En Windows usa `python` (no `python3`).
Opcional: tmux para la terminal partida, macOS para el dictado por voz.

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

Se cambia en el hub (**Actualizaciones**, fila «automáticas») o con
`workspace update --auto auto|notify|off`. Elijas lo que elijas, `workspace update`
instala cuando lo pides y `workspace update --rollback` te regresa. Tus agentes,
cerebros y ajustes viven fuera de la carpeta de Workspace. Cuando una versión necesita
ajustar algo dentro de tus cerebros (la 0.4.0, por ejemplo, pasa la identidad de tus
agentes a `BRAIN.md`), lo hace sola, antes copia todo a un respaldo y no borra nada; lo
que escribiste tú se deja como está.
Más en [el manual](manual/es/actualizaciones.md).

### Novedades de la v0.4.0

- **Cada pestaña recuerda lo mismo en cualquier motor.** Tu agente guarda lo
  importante mientras trabaja (decisiones, pendientes, hechos) y, al abrir la
  pestaña en ese motor o en otro, arranca con la misma memoria. Workspace la
  ordena solo, sin IA; nada se borra.
- **Dos secciones nuevas.** **Usuarios** muestra quién usa cada agente en todas
  tus máquinas (cambiar nombre, unir, «soy yo en esta PC»). **Documentación**
  explica todo lo que hace Workspace, con lo que está pasando ahora en tu PC.
- **Ninguna IA trabaja sin ventana.** Se retiró el «destilador» que resumía la
  memoria por su cuenta; la revisión de skills, si la enciendes, ocurre en la
  sesión de tu agente, a la vista.
- **Nada espera tu aprobación.** Tu agente mantiene solo sus skills, su memoria
  y su identidad (cura sus skills una vez por semana y completa su personalidad
  con lo que le dijiste), siempre recuperable, y te cuenta qué cambió.
- **Tus cerebros reciben unos cambios al actualizar**, siempre con respaldo
  antes: la identidad de tus agentes pasa a `BRAIN.md` (cada motor la sigue
  encontrando), las instrucciones de memoria se ponen al día y la bandeja vieja
  de propuestas (`STATE/DESTILADO.md`) pasa a `STATE/memoria-archivo/`. Nada se
  borra.
- **Más privado.** Las fichas de tus cuentas y las llaves guardadas ya no llegan
  a los motores ni a lo que ejecutan tus agentes; la telemetría y «obtener
  skills» empiezan apagadas.
- **Arreglos.** Windows vuelve a abrir el menú solo al abrir la terminal;
  `--help` nunca ejecuta nada; desinstalar con «limpiar todo» mueve los perfiles
  de Workspace en OpenClaw y Hermes (con tus conversaciones) a un respaldo en vez
  de borrarlos, y solo quita los comandos de terminal que puso Workspace; un
  motor que no está instalado ya no bloquea a su agente; cerrar con la X no
  pierde nada; puedes tener varios agentes de OpenClaw abiertos a la vez; en
  Windows, desinstalar ya borra de verdad la carpeta de Workspace.

### Novedades de la v0.3.3

- **Un arreglo.** El hub ya no muestra el aviso de «configuración a medias»,
  que podía seguir ahí aunque ya hubieras terminado el primer arranque. Para
  repasarlo: `workspace onboarding`.

### Novedades de la v0.3.1

- **Un hub más simple.** Cada sección muestra solo lo que necesitas, en una caja
  centrada; la explicación y sus mapas están detrás de `i`. Agentes muestra tus
  agentes con las opciones del elegido debajo y «+ agregar agente» al final;
  Motores verifica de verdad si tienes sesión; Actualizaciones muestra solo
  lo que puedes hacer en ese momento, incluido volver a la versión anterior;
  Comandos abre con `i` el mapa de cada comando a la derecha.
- **Menos ruido.** Atajos salió del menú (las teclas `1`–`9` siguen el orden de
  tus agentes) y Google Calendar queda en pausa mientras lo mejoramos.

### Novedades de la v0.3.0

- **Tú eliges cómo trabaja cada agente.** Crear o cargar un agente te da dos
  interruptores: leer y escribir su cerebro sin preguntar (encendido: es su trabajo
  principal; lo demás te lo pregunta) y la revisión automática de skills (apagada).
  Los cambias cuando quieras en **Agentes** (elige el agente y Enter).
- **Se acabaron los permisos sin límite en los agentes de Claude Code.** El instalador
  dejaba a todo agente correr cualquier comando sin preguntar. Al actualizar, tus agentes
  pasan solos a «libres solo dentro de su cerebro». Auto-aceptar ediciones viene ahora
  apagado.
- **La revisión de skills es opcional y funciona con los tres motores** — viene
  apagada; si la prendes, el propio motor del agente (Claude Code, Codex o Antigravity)
  la hace en segundo plano y usa un poco de tu suscripción.
- **El doctor revisa y repara solo lo esencial** — tus agentes, sus hooks y comandos,
  git/Python/el motor que usas y las actualizaciones — y arregla los hooks que apuntan a
  una carpeta de Workspace que ya no existe.
- **Instalar es más simple y tus sesiones se conservan un año** (antes, diez): ya no
  pregunta «¿Quién eres?» y pide el CLI del motor que vayas a usar. Una retención que tú
  elegiste jamás se toca.

Lista completa: [CHANGELOG.md](CHANGELOG.md).

### Manual

El manual de usuario vive en [`manual/`](manual/README.md) — capítulos cortos en
[español](manual/es/README.md) e [inglés](manual/en/README.md): instalar, primer
arranque, el hub, motores, qué funciona con cada motor, comandos, temas,
actualizaciones, diagnóstico, desinstalar y privacidad. Lo que Workspace defiende, en diez líneas: [el manifiesto](manual/MANIFIESTO.md).
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
