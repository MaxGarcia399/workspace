# v0.9.2
stage: testing
author: Workspace team
updated: 2026-11-11

We're testing v0.9.2 by hand, on Mac and Windows, before publishing it. It already passed all its automated tests on both. It also brings everything from v0.9.1, which wasn't released separately.

## What's coming
- [x] **Connections** — A new hub section to see which MCP each of your engines has.
  Read-only: it tells you whether the MCP is in the engine, only in Workspace (the engine doesn't read it), unreadable, or not supported by that engine. Also with `workspace conexiones`.
- [x] **Workspace in your browser** — Your agents on a local page, only on this computer.
  A new hub entry (and `workspace web`) opens the page in your browser. Close it with Ctrl+C or "Shut down".
- [x] **Skill review you can watch** — Optional and off by default.
  When you turn it on, the review of what your agent learned runs in a tab you can see, with the engine you choose, a token cap and Undo. A skill only counts as created when Workspace can check who wrote it.
- [x] **Your agents know how to use Workspace** — Five new skills and a manual in Spanish and English.
  Set up, personalize and repair Workspace, calendar and tasks, and tab memory. Your existing brains get them on their own, with a backup.
- [x] **Conversations: leave and come back** — `conversar salir` and `conversar unirse`.
  What someone said in a room always counts, even if your Mac and PC clocks disagree.
- [x] **Deciders tells you what happened next** — From v0.9.1.
  The History separates an opinion from a verified outcome and only says "yes" when there's proof.
- [x] **Fixes** — Honest MCPs, settings that aren't lost, proxy and Windows.
  Workspace no longer overwrites an MCP you added by hand or says "connected" when the engine doesn't read it; it doesn't write over a `settings.local.json` it couldn't read; with the proxy off it says so; and on Windows, skill review closes the engine cleanly.
- [~] **Polish from hands-on testing** — Whatever we find while using it, before publishing.
  We've started with Connections, Workspace in your browser, the agents guide and Conversations.

## Log
- 2026-11-11 — We started polishing Connections, Workspace in your browser, the agents guide and Conversations based on what we saw while using them.
- 2026-11-11 — Connections and Workspace in your browser now show up in the hub. Hands-on testing starts on Mac and Windows.
- 2026-11-11 — v0.9.2 passed all its automated tests on Mac and Windows, with two Greptile reviews.
- 2026-11-10 — We finished v0.9.1; it ships together with v0.9.2.
