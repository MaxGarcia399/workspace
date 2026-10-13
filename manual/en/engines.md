# Agents and engines

## The agent

An agent is an identity with its **brain**: a folder of Markdown files that lives **outside**
the Workspace folder. That's why updating or reinstalling Workspace doesn't touch your agents.
Create or load them from the hub with **Add agent** (`g`); look at them with **Agents** (`b`).

## The engine

The engine is the AI program that talks to the model. Workspace **does not rewrite** that
part: it uses each vendor's official program, with **your account**.

| Engine | Program | Account | How you log in |
|---|---|---|---|
| **Claude Code** | `claude` (Anthropic) | your subscription | run `claude` once and follow the login |
| **Codex** | `codex` (OpenAI) | your ChatGPT subscription | `codex login` |
| **Antigravity** | `agy` (Google) | your Google account | `agy` itself asks you to sign in |

Workspace **never reads or touches** these programs' credentials: each one handles its own login.

## Choosing and switching engines

- **Default for everyone:** you choose it on the first run (`workspace onboarding`).
- **For one agent:** in the hub, point at it and press `m` to cycle through the installed
  engines. It's saved on this machine.
- **Each engine's status:** the hub's **Engines** section (`j`) — installed or not, logged in or
  not, what it can do.

Switching engines does **not** change the agent's identity or brain. What doesn't travel is
each vendor's internal history: a conversation started on one engine won't show up on another.

## Not every engine can do the same

Claude Code is the most integrated today (memory injected at start, live events, its own
status bar). Codex and Antigravity run wrapped by Workspace, with some features missing. The
exact list, per engine and per OS: [Compatibility](compatibility.md).
