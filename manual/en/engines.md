# Agents and engines

## The agent

An agent is an identity with its **brain**: a folder of Markdown files that lives **outside**
the Workspace folder. That's why updating or reinstalling Workspace doesn't touch your agents.
Create or load them from the hub with **Add agent**; look at them with **Agents**.

## The engine

The engine is the AI program that talks to the model. Workspace **does not rewrite** that
part: it uses each vendor's official program, with **your account**.

| Engine | Program | Account | How you log in |
|---|---|---|---|
| **Claude Code** | `claude` (Anthropic) | your subscription | run `claude` once and follow the login |
| **Codex** | `codex` (OpenAI) | your ChatGPT subscription | `codex login` |
| **Antigravity** | `agy` (Google) | your Google account | `agy` itself asks you to sign in |

Workspace **never reads or touches** these programs' credentials: each one handles its own login.

## Permissions

When you create or load an agent you choose whether it **reads and writes its brain without
asking you**: it's on to start with, because that's its main job. The choice is saved with the
agent (`"autonomy"` in its `.workspace/agent.json`, it travels with the brain) and each engine
applies it its own way.

| | Inside its brain | Terminal, files outside, network |
|---|---|---|
| **On** (to start with) | reads, creates and edits without asking you | asks you first |
| **Off** | asks you before creating or editing | asks you first |

In Codex, with access on, commands run without asking **inside its sandbox**, which only lets it write to its
brain and the system's temporary folders, with no network; anything that needs to leave it asks.

With Claude Code it lands in the brain's `.claude/settings.local.json`: rules that let it read and
edit its own folder, and nothing else. No option switches off the engine's protections. Your own rules in that file are kept.

**Changing it later:** in the hub, **Agents** → pick the agent → **Enter**. Two switches, per agent, that apply from its next session in all three engines:

| Switch | To start with | What it does |
|---|---|---|
| Reads and writes its brain without asking | **yes** | off, it asks before creating or editing each file, also in its brain (`"ask"`) |
| Skill review when the session ends | no | see [Skill review](#skill-review-optional) |

Without opening the hub (or by asking the agent itself), from the Workspace folder:
`python3 agent_admin.py prefs <agent> --autonomy brain|ask --skill-review|--no-skill-review`.

If one of your agents comes from an earlier version that let it run any command without asking
you, updating switches it to this on its own (its previous settings are backed up).

## Skill review (optional)

The other choice: **"Automatic skill review when each session closes?"**. If you say yes, when
each session closes the agent's engine (Claude Code, Codex or Antigravity; if that one isn't
there, Claude Code) reads in the background what happened and improves the skills it used with
what you corrected. New skills stay as proposals in `skills/_propuestas/` until you approve them.

- It's a second net: the agent already learns during the conversation (it creates or improves
  skills and says so in the block at the end of each answer). The review at close catches what
  it missed.
- It reads a neutral copy of the session, only writes inside the brain's `skills/` and doesn't
  use the network. In Claude Code and Antigravity it doesn't use the terminal either; in Codex it
  uses it only to read and edit those files, inside its sandbox.
- It never makes closing wait; very short sessions aren't reviewed and it runs at most once every
  two hours per brain.
- **It uses a little of your subscription** to that engine.
- It ships off. It's saved per agent (`"skill_review"` in its `agent.json`) and you turn it on
  or off in **Agents** (pick the agent and Enter). For agents that didn't choose, the global `hooks.skill_review`
  setting decides (off); change it from the Workspace folder with
  `python3 settings.py set hooks.skill_review on` (or `off`).

## Choosing and switching engines

- **Default for everyone:** you choose it on the first run (`workspace onboarding`).
- **For one agent:** in the hub, point at it and use ← → to cycle through the installed
  engines. It's saved on this machine.
- **Each engine's status:** the hub's **Engines** section — installed or not, logged in or
  not, what it can do.

Switching engines does **not** change the agent's identity or brain. What doesn't travel is
each vendor's internal history: a conversation started on one engine won't show up on another.

## Not every engine can do the same

Claude Code is the most integrated today (memory injected at start, live events, its own
status bar). Codex and Antigravity run wrapped by Workspace, with some features missing. The
exact list, per engine and per OS: [Compatibility](compatibility.md).
