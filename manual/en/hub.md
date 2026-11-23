# The hub and its keys

The **hub** is what you see when you type `workspace`. It opens on **Inicio** (home): at the top,
**Buscar** (search), **Navegador** (browser), **Guía** (guide) and ✕; in the middle, the card of
the chosen agent (its little character, its name and its engine) with **Conversar** (talk) and
**Sesiones** (sessions); at the bottom, a row with the sections. The first time you open it a
short guide shows up; see it again with `?` or with **Guía**.

If you have no agents yet, the hub opens with the card to add the first one.

The hub's screens are in Spanish for now; this chapter gives each label as it appears, with its
meaning.

<!-- Sections and keys verified against hub_inicio.py (SECCIONES, SUBS) and
hub_secciones_r2.py (TECLAS). tests/test_manual_compat.py fails if they change. -->

## Adding an agent

**+ Agregar** (add) opens the card to add an agent: a new one, or one you already have («Ya tengo
un agente», I already have an agent). It is in Inicio, at the foot of the agents list, and in
**Agentes**. `workspace onboarding` opens the hub with that card.

## Sections

From Inicio, Tab reaches the row of sections; ← → changes section, ↓ shows its parts and Enter
opens it. You can also find them by typing their name.

| Section | What's there |
|---|---|
| Agentes | agents: Apariencia (each agent's face and color), Tono (tone), Quién lo usa (who uses it), Tablero (board) and **+ Agregar** |
| Motores | engines: each agent engine and whether it's ready. «Iniciar sesión» (sign in), «Instalar» (install) and «Reparar» (repair) open that engine's official program in the terminal; when it finishes you're back in Motores |
| Skills | your agents' skills |
| Calendario | calendar: your agenda; you add, change, mark or remove events |
| Ajustes | settings: General (the language, among others), Apariencia (theme and background), Permisos (permissions), Usuarios (users), Uso (usage), Actualizaciones (check, repair or update Workspace, with the steps live) and Conexiones (what Workspace connects in each engine) |
| Ayuda | help: Teclas (keys), Comandos (what you type in the terminal), Documentación (this manual) and Novedades (what's new) |

From the terminal you get there directly: `workspace agents` opens Agentes; `workspace tone`,
Agentes › Tono; `workspace calendar`, Calendario; `workspace connections`, Ajustes › Conexiones;
and `workspace commands`, Ayuda › Comandos. With arguments, those commands stay as text
([Commands](commands.md)).

## Keys

The full list, depending on where you are, is in **Ayuda › Teclas** (or F1). The everyday ones:

| Key | What it does |
|---|---|
| Tab | another area (Shift-Tab: the previous one) |
| ↑ ↓ ← → | move inside the area |
| Enter | do what has the focus |
| Esc | go back one level |
| `q` | quit (outside the typing box) |

In Inicio, ← → bring in the next agent and ↑ ↓ change its engine (saved by itself). Enter talks
to it, or does what its engine needs (for example, signing in). The `s` key opens its sessions in
its official program and `n`, the browser version. Other letters search for an agent or a
section; `/` searches even if you type `s`, `n` or `q`.

## The digits

The digits `1` … `9` go straight to that agent, in the order of your agents: the first one is
`1`, the second `2`, and so on. From the tenth on, use the arrows or the search. `q` drops you
to your terminal.

## Workspace in your browser

**Navegador ↗** (at the top of Inicio, or the `n` key) opens your browser on Workspace's local
page, only on this computer, and the hub stays where it was. There is a single page per computer:
if it is already open (from another hub or with `workspace web`), that one is opened again. Close
it with «Apagar» (shut down) on the page; it also shuts down by itself after a day with nobody
using it. To have it open by itself every time you open Workspace in a terminal, turn on
**Abrir Workspace en el navegador al iniciar** (open Workspace in the browser at start) in
Ajustes › General: it only does so when no other hub is open on this computer.

The page is in Spanish. If your language is another one, it tells you so in one line.

## Visible skill review

Off by default. In the skill review settings, choose when the agent reviews: on the next session opening, on close, or with a button. Choose the session engine or a fixed installed engine. The old enabled boolean keeps “on open” until an explicit mode is selected. Hermes and OpenClaw only use the button.

See an estimated token cost before starting. It is approximate, not a bill or an engine spending cap. Each batch contains at most three reviews. Pending sessions from the same tab are read together; reviews older than seven days expire.

With herdr, a tab opens without taking focus: the real chat on the left and observed steps on the right. **Stop** keeps unfinished work pending. An agent report is not proof: the close hook must verify the receiving session's write. The tab closes when finished. Undo only restores files whose writes appear in that session and refuses later edits; new files are archived. Files without sufficient authorship evidence cannot be undone here.

Without herdr, reviews run in the same window, one after another. See the cost first and choose to defer. Ctrl+C stops the batch. You can also use `workspace revision ahora`; `workspace revision ver <batch> [index]` shows changes and `workspace revision deshacer <batch> [index]` restores them (index starts at 0).

Keep this feature off for customers until all nine engines pass the live test.

Undo also requires reconstructing the content after the receiving session wrote it; when that evidence is unavailable, it refuses to restore and explains why.
