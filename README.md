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
  runs on Claude Code today; other engines plug in **without reinventing the
  agent's identity.** Switch models — paid, free, or local — without starting over.
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
  engine is dropping a file. Claude Code and Codex ship today.
- **Workflows** — declarative, multi-step procedures with a deterministic spine
  (`workflows/`): review code, create an agent, build a feature.
- **Doctor** — a 15-phase self-diagnosis and repair (`workspace doctor`).
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
doctor.py       # 15-phase diagnose / repair
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

The installer is **per-machine**: it drops the `workspace` command, wires the
hooks, and writes only to your machine's local config — never to the shared repo.

**Requirements:** Python 3, Git, and an engine CLI (today: **Claude Code**,
logged in with your subscription).

### Quickstart

```bash
workspace            # open the menu (pick an agent or a tool)
workspace doctor     # diagnose / repair the install
workspace --help     # every command
```

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
  sobre Claude Code; otros motores se enchufan **sin reinventar la identidad del
  agente.** Cambias de modelo —de pago, gratis o local— sin empezar de cero.
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
  agregar un motor es soltar un archivo. Claude Code y Codex ya vienen incluidos.
- **Workflows** — procedimientos declarativos de varios pasos con un espinazo
  determinista (`workflows/`): revisar código, crear un agente, construir features.
- **Doctor** — autodiagnóstico y reparación en 15 fases (`workspace doctor`).
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
doctor.py       # diagnóstico / reparación en 15 fases
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

El instalador es **per-máquina**: deja el comando `workspace`, cablea los hooks y
solo escribe en la config local de tu máquina — nunca en el repo compartido.

**Requisitos:** Python 3, Git, y un CLI de motor (hoy: **Claude Code**, con sesión
iniciada en tu suscripción).

### Inicio rápido

```bash
workspace            # abre el menú (elige un agente o una herramienta)
workspace doctor     # diagnostica / repara la instalación
workspace --help     # todos los comandos
```

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
