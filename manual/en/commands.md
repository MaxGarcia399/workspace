<!-- ARCHIVO GENERADO con `workspace comandos --markdown --lang en`: no lo edites a mano. tests/test_manual_commands.py vigila que coincida. -->

# Workspace commands

Everything you can type in the terminal. Every command accepts its Spanish and its English name.

## your agents

### `workspace`

Opens the hub: your agents and the menu; type to search.

**When:** To start working.

### `<agent>   (e.g. your agent's name)`

Opens that agent directly, skipping the hub.

**When:** When you already know who you want to talk to.

### `workspace agents [descubrir | reubicar | estado]`

Your agents and their status; descubrir finds brains, reubicar fixes a path.

**When:** If an agent is missing or says its brain cannot be found.

_also: `agentes`_

**Examples:**

    workspace agents descubrir
    workspace agents estado

### `workspace tone`

Adjust how your agents talk to you (dials from 1 to 5).

**When:** If you want shorter, warmer, more technical answers…

_also: `tono`, `personalidad`_

### `workspace onboarding`

Runs the guided setup again (resumes where it stopped).

**When:** If something was left pending at install.

_also: `bienvenida`_

## your day

### `workspace agenda [add | rm]`

Your local agenda: events with date and time.

**When:** To jot something down without opening the calendar.

### `workspace calendar`

Calendar editor: month, add, edit, delete.

**When:** To plan the week or the month.

_also: `calendario`, `cal`_

### `workspace mail --to <email> --subject <subject> [--dry-run]`

Sends an email from the terminal; --dry-run shows it without sending.

**When:** To send a quick notice or summary.

_also: `correo`_

## work

### `workspace eval <agent>`

Tests an agent against its reference question set.

**When:** After changing something important in an agent.

_also: `evaluar`, `evals`_

## this machine

### `workspace update [--check | --rollback | --force | --auto auto|notify|off]`

Updates Workspace and your brains, and repairs what is needed.

**When:** When there is a new version or something stopped working.

_also: `actualizar`, `up`_

**Examples:**

    workspace update --rollback
    workspace update --auto notify

> Asks for confirmation in the Commands screen.

### `workspace version`

Shows your version, your last update and what's new.

**When:** To know what you have, or when asking for help.

_also: `versión`_

### `workspace migrate [--run | --pending | --offer <id> | --decline <id>]`

Shows and applies the adjustments each update brings.

**When:** If the doctor says an adjustment is pending or failed.

_also: `migrar`_

**Examples:**

    workspace migrate --run

### `workspace doctor [--check | --remote | --bundle]`

Checks that everything is fine; without --check it also repairs. --bundle builds a diagnostic ZIP without personal data to ask for help.

**When:** If something looks off. --check only looks, changes nothing.

_also: `doc`_

**Examples:**

    workspace doctor --check
    workspace doctor --bundle

### `workspace repair`

Re-prepares the connections of each brain.

**When:** If an agent opens but does not remember or save.

_also: `reparar`, `fix`_

### `workspace dev-setup`

Checks whether this machine is ready to contribute to Workspace.

**When:** If you are going to code on Workspace.

_also: `configurar-desarrollo`_

### `workspace migrate-legacy [--apply | --retire | --rollback <backup>]`

Migrates or retires the previous Workspace install, with a backup.

**When:** Only if you came from the previous version (under the old name).

_also: `migrar-legado`_

### `workspace uninstall [--dry-run | --no-backup | --keep-folder | --clean-all]`

Uninstalls Workspace from this machine (your brains stay).

**When:** If you will no longer use it here.

_also: `desinstalar`, `remove`_

> Asks for confirmation in the Commands screen.

### `workspace commands [--json | --markdown | --check]`

This list of commands; --json for agents, --markdown for the manual.

**When:** When you want to see or export every command.

_also: `comandos`_

**Examples:**

    workspace commands --json

### `workspace help`

Shows the list of commands in the terminal.

**When:** When you do not remember a command.

_also: `ayuda`, `--help`, `-h`_

### `workspace --banner`

Prints the hub without animation (static, non-interactive view).

**When:** For screenshots or keyboard-less terminals.
