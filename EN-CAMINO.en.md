# v0.9.2
stage: testing
author: Workspace team
updated: 2026-11-17

Workspace's new face exists and we use it every day. Now we're making it feel like a product: fast, no surprises, and a clear way out when something fails. Your agents, their brains, the 9 engines and skills stay the same.

## What's coming
- [x] **Workspace in your browser, simpler** — A local page with your agents, each with its own character, conversation, tone, to-dos and files. It already works in our development build; now we're polishing it.
  Skills run inside the chat with their progress in view, and whatever the agent asks you is answered right there.
- [x] **Switch engines without losing the conversation** — You stay in the same chat with another engine, and the new engine knows what was said with the previous ones, even when you go back to one you already used.
  While it switches, the page says what's happening and won't let you type halfway.
- [x] **Failures with a way out** — If an engine runs out of credit, hits its limit or loses its session, the page tells you in plain words and offers to continue with another engine or retry.
- [x] **Faster with many agents** — The page no longer asks the server for everything every few seconds: the server tells it only when something changes. With 20 idle agents, server work dropped from 72.9 to 3.7 ms per second.
- [x] **Create an agent with one button** — Give it a name and tell it how it will help you; Workspace builds the rest, with its full brain from minute one.
- [x] **Model, effort and mode from the page** — Each engine offers only what it really has, applied through its official path.
- [x] **Engines up to date** — Workspace checks every new version of the 9 engines before it affects you, and keeps your permissions even if an engine changes its behavior when it updates.
- [ ] **Agent groups** — Several agents in the same conversation, each with its own engine.
- [x] **Deciders takes a break** — It leaves this version while we redesign it. Your history stays saved.

## Log
- 2026-11-17 — Everything in v0.9.2 is now built and merged: the new page, switching engines without losing the conversation, creating agents, model and mode per engine, and engines up to date. It passed two independent reviews and the tests on Mac and Windows; now we're using it before we publish.
- 2026-11-16 — We tested the page end to end with real agents on all 9 engines, including creating a new agent. We found 19 failures and are closing them one by one.
- 2026-11-16 — The page's server now announces changes instead of re-reading everything; with many agents you notice it.
- 2026-11-16 — Switching engines no longer starts from scratch: one browser conversation per agent, with the history of all its engines.
- 2026-11-16 — We reviewed the versions of the 9 engines and started certifying them on their newest versions.
- 2026-11-15 — New direction: the next release focuses on a new, simple face for what already works. Deciders leaves for now.
- 2026-11-11 — Skill review you can watch also makes it into v0.9.2.
- 2026-11-11 — We reordered v0.9.2: it ships on top of v0.9.1 with Deciders, Conversations and the browser page. Everything else, in the next ones.
- 2026-11-11 — On the PC: Connections (add and remove MCPs), skill review on all 9 engines, inviting to a room and Projects in plain sight move forward.
- 2026-11-10 — We finished v0.9.1; it ships together with v0.9.2.
