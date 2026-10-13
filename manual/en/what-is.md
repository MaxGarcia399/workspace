# What Workspace is

Workspace is a place, inside your terminal, to work with **several AI agents**. Each agent
has three things:

- **Identity** — who it is, how it talks, what it does.
- **Brain** — a folder of plain text (Markdown) files holding what it knows and remembers.
  It's yours: you can open it, read it, edit it, back it up and take it with you.
- **Engine** — the AI program that actually talks to the model: Claude Code, Codex or
  Antigravity, each with **your own account**.

```
Agent = identity + brain + engine
```

## What Workspace does for you

- A **menu (the hub)** to pick an agent and jump in with one key.
- Hands each agent its memory when it starts, so it doesn't start from zero every time.
- Lets you **switch engines** without rebuilding the agent.
- **Checks and repairs itself** (`workspace doctor`) and **updates itself**.
- Tools around it: calendar, agent tone, shortcuts.

## What it does NOT do

- It isn't an AI model and doesn't replace one: it uses the engine you install and pay for.
- It doesn't promise perfect memory, or that a conversation moves intact from one vendor to another.
- It doesn't upload your files to any server of its own (see [Privacy](privacy.md)).

## Status

Workspace is **early**. The core works and has automated tests, but expect rough edges.
What works with each engine and OS is written down, honestly, in
[Compatibility](compatibility.md).
