# Guide for agents

What an agent can do for you inside Workspace, and which skill covers it. The
skills ship in the brain template (`skills/meta/`). A brain that already
exists receives them on update, when you load it, or with `workspace doctor`:
the missing ones are copied. A copy still exactly as an earlier version left it
is brought up to date, with a backup; one that you or your agent changed is not
touched.

*[Versión en español](../es/agentes.md)*

## Where each skill lives

| If you ask… | The skill |
|---|---|
| Connect an engine, see a key, check for an update | `skills/meta/configurar-workspace/` |
| Change the theme, the tone, or the language | `skills/meta/personalizar-workspace/` |
| Something will not open: doctor, tabs, hooks, a session still running in the background | `skills/meta/reparar-workspace/` |
| An event or a task | `skills/meta/calendario-y-tareas/` |
| Talk to another agent | `skills/meta/colaborar-por-bus/` |
| Remember something from this tab | `skills/meta/memoria-de-la-pestana/` |

The full command list, generated from the program: [Commands](commands.md).
An agent reads it again with `workspace comandos --json`. A flag that is not
there does not exist.

## What the agent does not do

- It does not hand-edit files Workspace manages (hooks, the agenda, the tab's
  memory, the vault).
- It does not put keys in plain text. `workspace llaves` says where each one
  comes from and never shows the value.
- It does not publish or upload code. An update, unless you asked, is only
  looked at with `workspace actualizar --check`.

## How to tell it worked

`workspace doctor --check` looks and changes nothing. Each skill ends with the
command that confirms the change.
