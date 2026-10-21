# Troubleshooting and help

## The doctor

```bash
workspace doctor
```

Checks **only what Workspace needs to work** and **repairs** what it can:

- git, Python and the program of the engine **your** agents use;
- updates (version, pending or failed adjustments);
- **your agents**: that their folder exists, that their *hooks* point to this install and
  that their command is installed;
- leftovers of a previous install.

It's the same check that runs at the end of `workspace update`. Phases that are already
fine are skipped; running it twice breaks or duplicates nothing. It doesn't check optional
features (voice: [Compatibility](compatibility.md)) or how you organize your brains, and
**having no agents yet is normal**: it isn't a warning.

Look only, changing nothing and without going online:

```bash
workspace doctor --check
```

Each result shows ✓ (fine or repaired), ⚠ (attention) or ✗ (something missing), with the
suggested action.

## Common problems

| Symptom | What to do |
|---|---|
| `workspace` doesn't exist after installing | open a **new terminal**; if it persists, run the installer again |
| The menu looks misaligned | make the window bigger; on Windows use Windows Terminal |
| An agent can't find its brain | `workspace doctor` tells you where it looked and how to point it to the right folder |
| The doctor says an engine's CLI is missing | install its official program and log in ([Engines](engines.md)) |
| You moved or reinstalled Workspace and an agent fails to open | `workspace doctor` points its *hooks* back to this install |
| You installed inside OneDrive | move Workspace out (e.g. `%LOCALAPPDATA%\Workspace`); the doctor detects it |

## Asking for help

Open an *issue* on Workspace's GitHub repository using the **"Report a problem"** template.
It will ask for:

1. Your Workspace **version** and your **operating system**.
2. The **diagnostic bundle**:

   ```bash
   workspace doctor --bundle
   ```

   It leaves `workspace-diagnostico-<date>.zip` on your Desktop (or wherever you say with
   `--out <folder>`) and prints the path. It carries the doctor's report, your version, your
   system, what works with each engine, your agents (name and engine, no paths) and the tail
   of Workspace's logs. It **blanks out** paths, your user name, your computer's name, emails,
   tokens and IPs, and **never** includes conversations, keys or the content of your brains.
   Inside there's a `LEEME.txt` that says exactly what it contains and what was blanked out:
   open it before sending if you want to check.
3. What you did, what you expected and what happened.

**Is it a security problem?** Don't open a public issue: follow [SECURITY.md](../../SECURITY.md).
