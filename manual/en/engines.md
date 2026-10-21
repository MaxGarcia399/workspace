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
| **OpenCode** | `opencode` (open source) | the provider you connect (OpenRouter, Anthropic, OpenAI…) | `opencode auth login` |
| **OpenClaw** | `openclaw` (open source) | the provider and model you pick | Engines › **account and provider** (`openclaw --profile workspace configure --section model`, OpenClaw's official picker) |
| **Hermes** | `hermes` (Nous Research, open source) | the provider and model you pick | Engines › **account and provider** (`hermes --profile workspace model`, Hermes' official picker) |

Workspace **never reads or touches** these programs' credentials: each one handles its own login.
With OpenCode, OpenClaw and Hermes, you pick the model in its own config; Workspace doesn't change it.

**Your account, your provider and each engine's settings are yours.** Workspace has no provider
system, stores no keys and doesn't change engine settings: in **Engines**, every engine always has
an **account and provider** option that opens that engine's official account, provider and model
picker (`claude auth login`, `codex login`, `agy`, `opencode auth login`,
`openclaw --profile workspace configure --section model` or `hermes --profile workspace model`).
That's where you sign in, switch accounts or connect another provider. The rest of the engine's
configuration stays yours, with its own tools.

**Versions.** Workspace always uses the newest version of each engine. In **Engines**, OpenCode,
OpenClaw and Hermes show theirs: **tested** (Workspace already tested it), **newer** (that's
normal: each new version is tested daily and, if something breaks, `workspace update` brings the
fix), **older** or **too old** (update it) or **known bug** (a confirmed problem on your system:
Enter tells you which and what to do, and you can still open the agent). Claude Code, Codex and
Antigravity don't depend on the version.

The only thing Workspace keeps in place is what it needs from your **brain** to work. With
OpenClaw: that it doesn't create files of its own in your brain, that your agent's workspace is
your brain and that it reads your brain's memory. With Hermes: that it doesn't put its own
identity or memory on top of your agent's, and that it uses your brain's skills. It checks this
every time you open the agent; if you changed it from the setup, it puts it back and tells you in
one line.

OpenClaw runs with a **Workspace profile of its own** (separate from any OpenClaw you use
yourself) that works on your same brain without creating extra files. You connect the provider
once and it serves all your agents. You can have **several OpenClaw agents open at once**: when
you open the first one, Workspace starts the OpenClaw service in the background (it takes a few
seconds) and stops it on its own when you close the last one. On every message it reads your
**brain's long-term memory** (`STATE/MEMORY.md`, the same one the other engines use) through its
official hook; its semantic search stays off, because indexing your brain would send your notes
to an outside service. When Workspace asks it something without opening a window (for example,
personalizing an agent), your agent answers, not OpenClaw's built-in agent. If your brain has an
old `MEMORY.md` or `memory/` folder loose in its root, OpenClaw reads them on every message as if
they were your agent's memory: `workspace doctor` tells you and offers to move them aside to
`motores/openclaw/` (it never deletes anything).

Hermes also runs with a **Workspace profile of its own** (`workspace`, in
`~/.hermes/profiles/workspace`): **your personal Hermes doesn't change** (not its config, identity,
memory or history). The first time you open an agent with Hermes, Workspace creates that profile
with your model but **without copying your keys**: connect your provider once in Engines ›
**account and provider**. **You change the provider and the model from Engines** (account and
provider opens Hermes' official picker inside that profile). Worth knowing:

- **The identity is your agent's.** Hermes ships one of its own ("Hermes Agent", by Nous
  Research); in Workspace's profile it's neutral and the identity arrives through the brain's
  `AGENTS.md`, which for Hermes also carries a **copy of your agent's core** (`BRAIN.md`, `BOOT/`
  and your partner profile): it introduces itself with its own character even if the model doesn't
  read files on its own. The copy is rebuilt on every start; what you edit is still the brain. A
  tab that already had a conversation keeps the identity it started with (Hermes stores it); open a
  new tab to see an identity change.
- **Hermes' memory is off in that profile**, and so is its past-conversation search: all your
  agents share the profile, and one could read another's conversations. Each agent's memory and
  history live in its brain. When you **resume** a tab, Hermes gets the tab's up-to-date memory
  with your first message (including what you noted in another engine), and again if someone else
  changes it while the tab is open; what it notes itself isn't repeated to it.
- **It uses your brain's skills** (`skills/`) besides its built-in ones, and no longer creates
  skills in the profile all your agents share. If a skill in your brain has the same name as a
  built-in one, the built-in one wins. Its scheduled tasks stay as in your Hermes.
- **Your tone arrives with every message.** The first time, Hermes asks whether you approve
  Workspace's hook that adds it (and that brings the tab's memory when you resume and records
  which tab owns each conversation); answer "y". If you say no, the tone only arrives when the
  session opens and a resumed tab doesn't get the new memory.
- **Hermes can't be sent a startup message.** In a new tab, the agent reads its brain when you
  send the first message.
- If you open two new tabs of the same agent at once and didn't approve the hook, Workspace doesn't
  guess which conversation is whose: it binds neither (you get it back from Hermes' history).

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

With OpenCode, OpenClaw and Hermes, Workspace **doesn't apply** this switch yet: each asks according to its own
permissions (its config).

**Changing it later:** in the hub, **Agents** → pick the agent → **Enter**. Two switches, per agent, that apply from its next session in Claude Code, Codex and Antigravity:

| Switch | To start with | What it does |
|---|---|---|
| Reads and writes its brain without asking | **yes** | off, it asks before creating or editing each file, also in its brain (`"ask"`) |
| Skill review when the session ends | no | see [Skill review](#skill-review-optional) |

Without opening the hub (or by asking the agent itself), from the Workspace folder:
`python3 agent_admin.py prefs <agent> --autonomy brain|ask --skill-review|--no-skill-review`.

If one of your agents comes from an earlier version that let it run any command without asking
you, updating switches it to this on its own (its previous settings are backed up).

## Skill review (optional)

The other choice: **"Automatic skill review?"**. If you say yes, when each session closes
Workspace saves a view of what happened and, **when the next one opens**, your agent reviews it
in that same session, in plain sight, and improves the skills it used with what you corrected.
New skills are created directly in their category, as it already does during the conversation.
It reports it in one line of the block at the end of its answer.

- It's a second net: the agent already learns during the conversation (it creates or improves
  skills and says so in the block at the end of each answer). The review catches what it missed.
- **Nothing runs without a window or behind your back:** no process is launched at close; your
  agent does the review when you open it, in front of you.
- It reads a neutral copy of the session saved inside your brain, in `.claude/skill-review/`
  (a hidden folder: it isn't synced and stays out of git), and only writes inside `skills/`.
- Very short sessions aren't reviewed, and it's requested at most once every two hours per brain.
- **It uses a little of your subscription** to that engine, in that session.
- It ships off. It's saved per agent (`"skill_review"` in its `agent.json`) and you turn it on
  or off in **Agents** (pick the agent and Enter). For agents that didn't choose, the global `hooks.skill_review`
  setting decides (off); change it from the Workspace folder with
  `python3 settings.py set hooks.skill_review on` (or `off`).

## Choosing and switching engines

- **Default for everyone:** you choose it on the first run (`workspace onboarding`).
- **For one agent:** in the hub, point at it and use ← → to cycle through the installed
  engines. It's saved on this machine.
- **Each engine's status:** the hub's **Engines** section — installed or not, logged in or
  not, what it can do, and **account and provider** to open its official setup.

Switching engines does **not** change the agent's identity or brain. The conversation itself
belongs to each vendor (one started on one engine won't show up on another), but **the tab
does travel**: its memory belongs to Workspace and is the same on all six engines.

## Each tab's memory

It works the same on every engine and you don't have to do anything:

- **While you work**, the agent saves what matters right away, with a label: decision, pending,
  done, note, fact or preference (`workspace memoria nota`). Pending items get a number (P-3)
  and are closed once done.
- **On close**, Workspace (no AI) packs the tab's **handoff** ("maleta"): your last requests,
  the last answer and the files it touched. It tidies the log, archives old notes and moves
  your facts and preferences into the agent's memory. Also when you closed the window with the X.
- **On open**, on that engine or another, the agent gets one package: the summary, what is still
  open, the new notes and the handoff if you come from another engine. When due, it updates its
  summary in plain sight, in one short reply.

Everything lives in the brain (`STATE/sessions/<partner>/`), so it also travels to your other
machines. Nothing runs at night or without a window. Claude Code also keeps its own memory
inside the brain, one folder per person (`motores/claude-code/memoria/<partner>/`): in a shared
brain, each person's Claude Code loads only their own. Turn it off in Settings to keep it on the
machine instead. To see it: `workspace memoria ver` (with the tab active).

## Not every engine can do the same

Each tab's memory is the same on all of them. Claude Code is the most integrated today (live
events, its own status bar, its own memory in the brain). Codex, Antigravity, OpenCode, OpenClaw and Hermes run wrapped by Workspace, with some features
missing. The
exact list, per engine and per OS: [Compatibility](compatibility.md).
