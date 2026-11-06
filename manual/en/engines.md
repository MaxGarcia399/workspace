# Agents and engines

## The agent

An agent is an identity with its **brain**: a folder of Markdown files that lives **outside**
the Workspace folder. That's why updating or reinstalling Workspace doesn't touch your agents.
Create or load them from the hub with **Add agent**; look at them with **Agents**.

## The engine

The engine is the AI program that talks to the model. Workspace **sets up and opens your
official engines**: it doesn't rewrite that part, it uses each vendor's official program with
**your account**.

| Engine | Program | Account | How you log in |
|---|---|---|---|
| **Claude Code** | `claude` (Anthropic) | your subscription | run `claude` once and follow the login |
| **Codex** | `codex` (OpenAI) | your ChatGPT subscription | `codex login` |
| **Antigravity** | `agy` (Google) | your Google account | `agy` itself asks you to sign in |
| **OpenCode** | `opencode` (Anomaly, open source) | the provider you connect (OpenRouter, Anthropic, OpenAI…) | `opencode auth login` |
| **OpenClaw** | `openclaw` (OpenClaw Foundation, open source) | the provider and model you pick | Engines › **account and provider** (`openclaw --profile workspace configure --section model`, OpenClaw's official picker) |
| **Hermes** | `hermes` (Nous Research, open source) | the provider and model you pick | Engines › **account and provider** (`hermes --profile workspace model`, Hermes' official picker) |
| **Kiro** | `kiro-cli` (AWS, formerly Amazon Q Developer CLI) | your Kiro account (Builder ID, Identity Center, Google or GitHub) | `kiro-cli login` |
| **GitHub Copilot** | `copilot` (GitHub) | your Copilot subscription | `copilot login` (Engines › **account and provider**) |
| **Cursor** | `cursor-agent` (Anysphere, the company behind Cursor) | your Cursor account | `cursor-agent login` (also in Engines › **account and provider**) |

Workspace **never reads or touches** these programs' credentials: each one handles its own login.
With OpenCode, OpenClaw, Hermes, Kiro and Cursor, you pick the model in its own config; Workspace doesn't change it.

**Trademarks.** Workspace is independent. It is not affiliated with or endorsed by Anthropic,
OpenAI, Google, Anomaly (OpenCode), the OpenClaw Foundation, Nous Research (Hermes), Amazon Web
Services (Kiro), GitHub or Anysphere (Cursor). All trademarks belong to their owners. Each engine
runs with your own account and under its own terms.

**Your account, your provider and each engine's settings are yours.** Workspace has no provider
system, stores no keys and doesn't change your account, provider or model (the little it does
write in GitHub Copilot's, Cursor's and Kiro's settings, for their status bar and for saving
memory, is listed below engine by engine, and uninstalling removes it): in **Engines**, every engine always has
an **account and provider** option that opens that engine's official account, provider and model
picker (`claude auth login`, `codex login`, `agy`, `opencode auth login`,
`openclaw --profile workspace configure --section model`, `hermes --profile workspace model`,
`kiro-cli login`, `copilot login` or `cursor-agent login`). That's where you sign in, switch accounts or connect another provider. The rest of the engine's
configuration stays yours, with its own tools.

**GitHub Copilot** installs from Engines with the official npm package (`@github/copilot`, needs
Node.js 22 or newer) on macOS and Linux, and with WinGet (`GitHub.Copilot`) on Windows. On the Mac,
don't use the Homebrew one (`brew install --cask copilot-cli`): macOS holds that program back and
shows a "copilot can't be opened" warning you can't close. Copilot already reads your brain
without asking; it asks you itself before using the terminal or writing outside the brain. What
Workspace passes and writes:

- **On every launch, writing nothing in Copilot:** Workspace's memory tool
  (`--additional-mcp-config=@~/.claude/workspace/copilot-mcp.json`) and permission to use **only**
  its tools (`--allow-tool=workspace-memoria(guardar_nota)`, `…(guardar_resumen)` and
  `…(ver_memoria)`): your agent saves its notes without Copilot asking, without going through the
  terminal, and only in its own tab's memory; the terminal and everything else still ask. And `--excluded-tools=session_store_sql`
  (turns off Copilot's search over past conversations: it's one store for your whole account and
  one agent could read another's; the tab's memory covers what it gave). If you pass your own
  `--excluded-tools` or `--available-tools`, yours win and Workspace warns you on launch.
- **Writing in its brain without asking** (with "its brain without asking" on, the default),
  also on every launch: `--allow-tool=write(<brain>/**)` with the brain's real path, and
  `--deny-tool` for leaving through `..` and for the brain's Copilot config that runs commands or
  approves tools (`.github/`, `.mcp.json`, `.claude/settings.json` and `settings.local.json`,
  `.claude/skills/`, `.claude/agents/` and `.agents/`): it doesn't write that one, not even by
  asking. Outside the brain it asks you. Off, none of this is passed. If you pass your own Copilot
  permissions (`--allow-tool`, a `write` `--deny-tool`, `--allow-all-tools`, `--yolo` or
  `COPILOT_ALLOW_ALL`), yours win. With parentheses in the brain's path Copilot rejects the rule:
  it asks you, and tells you so on launch.
- **Its status bar:** the `statusLine` in your `~/.copilot/settings.json` (or `$COPILOT_HOME`)
  points to `~/.local/bin/workspace-copilot-statusline`; before the first time it saves a copy of
  the file as `settings.workspace-statusline-backup.json`. A `statusLine` of yours is left alone.
  To remove it: `WORKSPACE_COPILOT_NO_STATUSLINE=1`.
- Uninstalling removes the status bar, that copy and its command. If the tool isn't there (for
  example, if you remove tools with your own `--available-tools`), your agent saves with
  `workspace memoria nota` and Copilot asks you. If you pick "Yes, and don't ask again for `workspace` in
  this directory", Copilot approves **every** `workspace` command in that brain, not just notes.

**Versions.** Workspace always uses the newest version of each engine. In **Engines**, OpenCode,
OpenClaw, Hermes, Kiro, GitHub Copilot and Cursor show theirs: **tested** (Workspace already tested it), **newer** (that's
normal: each new version is tested daily and, if something breaks, `workspace update` brings the
fix), **older** or **too old** (update it) or **known bug** (a confirmed problem on your system:
Enter tells you which and what to do, and you can still open the agent). Claude Code, Codex and
Antigravity don't depend on the version.

The only thing Workspace keeps in place is what it needs from your **brain** to work. With
OpenClaw: that it doesn't create files of its own in your brain, that your agent's workspace is
your brain and that it reads your brain's memory. With Hermes: that it doesn't put its own
identity or memory on top of your agent's, and that it uses and saves its skills in your brain.
It checks this every time you open the agent; if you changed it from the setup, it puts it back
and tells you in one line.

OpenClaw runs with a **Workspace profile of its own** (separate from any OpenClaw you use
yourself) that works on your same brain without creating extra files. You connect the provider
once and it serves all your agents. You can have **several OpenClaw agents open at once**: when
you open the first one, Workspace starts the OpenClaw service in the background (it takes a few
seconds) and stops it on its own when you close the last one. On every message it reads your
**brain's long-term memory** (`STATE/MEMORY.md`, the same one the other engines use) through its
official hook. Of its own memory, Workspace only turns off what would write into your brain: its
memory search stays on, but it only searches OpenClaw's own memory files, which your brain
doesn't use, and without an embeddings service it searches by keywords (if the agent says it's
"degraded", that's why, and it's normal). Workspace doesn't point it at your brain, because
indexing it would send your notes to an outside service. When Workspace asks it something
without opening a window (for example, personalizing an agent), your agent answers, not
OpenClaw's built-in agent. If your brain has an old `MEMORY.md` or `memory/` folder loose in its
root, OpenClaw reads them on every message as if they were your agent's memory: `workspace
doctor` tells you and offers to move them aside to `motores/openclaw/` (it never deletes
anything).

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
- **Hermes' memory is off in that profile**, and so is its past-conversation search (in the
  terminal and in a Discord bot connected to that profile): all your agents share the profile,
  and one could read another's conversations. Each agent's memory and
  history live in its brain. When a conversation starts or you **resume** it, Hermes gets with
  your first message your **brain's long-term memory** (`STATE/MEMORY.md`, up to 20,000
  characters: if it's longer, the beginning and where the rest is) and the tab's up-to-date memory
  (including what you noted in another engine), and the latter again if someone else changes it
  while the tab is open; what it notes itself isn't repeated to it.
- **It uses your brain's skills** (`skills/`) besides its built-in ones, and **saves the ones it
  learns in your brain**. When it creates a skill (on its own during the conversation or because
  you ask with `/learn`), it lands in `skills/aprendidas/` of the brain of that tab's agent; when
  it improves one that already exists, it changes it right there. Nothing stays in the profile your
  agents share: what one learns, another doesn't see. When each session closes, Workspace adds the
  new ones to the brain's catalog (`skills/README.md`), so **your other engines see and use them
  too**. Its automatic skill review (the one that runs on its own after a long task) is off. A
  Hermes older than 0.21.6 still saves them in its profile: update it. If a skill in your brain has
  the same name as a built-in one, the built-in one wins. Its scheduled tasks stay as in your
  Hermes.
- **Your tone arrives with every message**, through a Workspace hook that adds it (and that
  brings your memory and records which tab owns each conversation). If it's
  the only hook in the profile, Hermes approves it by itself when it opens. If you added hooks of
  your own to that profile, Workspace approves nothing for you: Hermes asks whether you approve
  Workspace's; answer "y". If you say no, the tone and the long-term memory only arrive when the
  session opens and a resumed tab doesn't get the new memory.
- **Hermes can't be sent a startup message.** In a new tab, the agent reads its brain when you
  send the first message.
- If you open two new tabs of the same agent at once and didn't approve the hook, Workspace doesn't
  guess which conversation is whose: it binds neither (you get it back from Hermes' history).

Kiro runs with **your same Kiro account and settings**: Workspace doesn't create a profile for it.
Outside your brain (in `~/.kiro`, or in `KIRO_HOME`) it **writes nothing**: everything goes in
your brain's `workspace` agent (`.kiro/agents/workspace.json`: Kiro's default agent without its
personality, plus the memory tool and the permissions below). Its status bar is its own,
untouched: usage and credits are turned on in `/settings display` inside Kiro. If an earlier
version of Workspace had left its agent in `~/.kiro` or turned those segments on, they're
removed on update (with a copy; `workspace migrate --undo
202611052341_kiro_config_en_el_cerebro` puts the bar back as it was). Worth knowing:

- **Sign in first.** Without a session, Kiro opens its own sign-in in the browser. Workspace offers
  it when you open the agent (`kiro-cli login`) and doesn't open blind if you say no.
- **It opens your brain without asking whether you trust the folder.** Workspace uses Kiro's
  official option that trusts **only** that folder and **only** for that launch; nothing is saved
  in your settings. To make Kiro ask again: `WORKSPACE_KIRO_NO_AUTOTRUST=1`.
- **It reads your brain without asking**, as Kiro does with the folder it opens in, and **writes
  in it without asking** when the agent has "its brain without asking" (the usual; you change it
  in Agents): outside the brain Kiro still asks you and the terminal asks as always. With Kiro 2
  and Kiro 3, every launch picks the `workspace` agent (`--agent workspace`), which Workspace
  keeps in your brain (`.kiro/agents/workspace.json`) with those permissions and its memory tool
  approved by name; your agent saves its notes with it, without going through the terminal and
  without Kiro asking. That agent can't
  write to `.kiro/` (or give itself permissions) and Workspace rebuilds it on every tab launch:
  if someone changed it, it's backed up to `~/.claude/workspace/respaldos/` and you get a note. If you pick Kiro's
  agent or engine yourself (`--agent`, `--v3`, `chat.defaultAgent`…), yours wins and memory asks
  for permission (`workspace memoria nota`).
- **Tabs:** Kiro creates the conversation with the startup message and Workspace binds it to the
  tab on close; when you reopen it, it resumes the same one (`--resume-id`). A conversation can
  only be open in one window at a time (Kiro's rule).
- **On close**, Workspace copies Kiro's conversation (`~/.kiro/sessions/`) for the handoff.
- **Installing on a Mac:** the official installer opens the "Kiro CLI" app once to finish
  installing. If you installed it with Homebrew, open it once yourself; otherwise Workspace tells
  you.
- A `.kiro/` folder at the brain's root would compete with the shared identity: `workspace
  doctor` flags it (unless it only holds Workspace's agent).

Cursor runs with **your Cursor account** (`cursor-agent login`) and the model you pick inside
Cursor. It has no profile of its own: it reads the brain's same `AGENTS.md`. Worth knowing:

- **It trusts your brain for you.** Cursor asks whether you trust each new folder; Workspace opens
  it with `--trust`, which leaves the `.workspace-trusted` mark in `~/.cursor/projects/<folder>/`
  (outside your brain). Only for the brain's folder: when Workspace asks it something without a
  window, it trusts only if it's the brain of one of your agents. To be asked again:
  `WORKSPACE_CURSOR_NO_AUTOTRUST=1`. Uninstalling removes only the marks Workspace left.
- **It reads and edits inside your brain without asking** (Cursor's default); terminal commands
  ask for your approval, except saving memory: your agent saves with Workspace's memory tool,
  without going through the terminal and only in that window's tab. It lives in your brain's
  **project** settings: the server in `.cursor/mcp.json`, permission for its three tools in
  `.cursor/cli.json` (`Mcp(workspace-memoria:guardar_nota)`…) and, on launch,
  `cursor-agent mcp enable workspace-memoria`, which approves **only** that server (if someone
  changes its command, Cursor asks again). Those two files are your project settings: Workspace
  only adds its own part (its server and its rules) and your servers and permissions stay as they
  are. `cli.json` also denies the agent writing to `.cursor/` (`Write(**/.cursor/**)`, so it can't
  give itself permissions). If someone changed Workspace's part, only that is restored on launch,
  with a copy in `~/.claude/workspace/respaldos/` and a one-line note. If `.cursor` is a link or a
  file can't be read, it's left alone: memory asks you for permission and you're told on launch. The rule from an
  earlier version in your `cli-config.json` (`Shell(…/workspace-memoria)`) is removed on launch.
- **Its status bar:** the `statusLine` in that same file points to
  `~/.local/bin/workspace-cursor-statusline` and replaces Cursor's footer row (model, %, folder and
  branch stay in Workspace's). One of yours is left alone; to remove it:
  `WORKSPACE_CURSOR_NO_STATUSLINE=1`. The rest of the file (including your account, `authInfo`)
  stays the same: it's rewritten in one go with the same permissions, and opening copies it to no
  backup. Uninstalling removes the bar and the rule (the uninstaller leaves a copy of the file next
  to it, readable only by you).
- **Cursor also reads the brain's `CLAUDE.md`** and runs the Claude Code *hooks* it finds.
  Workspace's do nothing inside Cursor; yours run as Cursor decides.
- **The tab resumes** with its Cursor conversation (`--resume`). On close, Workspace copies the
  conversation Cursor writes and packs the handoff.
- With the `cursor-cli` Homebrew cask on macOS, the program may not start (the system blocks its
  un-notarized parts). Install it from Engines, which uses Cursor's official installer.

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

With GitHub Copilot it goes on every launch, without writing its settings: on, it writes in its
brain without asking (except its Copilot config, see [GitHub Copilot](#the-engine)); outside
the brain and the terminal it asks you.

With OpenCode, OpenClaw, Hermes, Kiro and Cursor, Workspace **doesn't apply** this switch yet: each asks according to its own
permissions (its config).

**Changing it later:** in the hub, **Agents** → pick the agent → **Enter**. Two switches, per agent, that apply from its next session in Claude Code, Codex, Antigravity and GitHub Copilot:

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
does travel**: its memory belongs to Workspace and is the same on all nine engines.

## Each tab's memory

It works the same on every engine and you don't have to do anything:

- **While you work**, the agent saves what matters right away, with a label: decision, pending,
  done, note, fact or preference (`workspace memoria nota`). Pending items get a number (P-3)
  and are closed once done.
- **On close**, Workspace (no AI) packs the tab's **handoff** ("maleta"): your last requests,
  the last answer and, in Claude Code and Codex, the files it touched. It tidies the log,
  archives old notes and moves your facts and preferences into the agent's memory. Also when you closed the window with the X.
- **On open**, on that engine or another, the agent gets one package: the summary, what is still
  open, the new notes and the handoff if you come from another engine. When due, it updates its
  summary in plain sight, in one short reply.

Everything lives in the brain (`STATE/sessions/<partner>/`), so it also travels to your other
machines. Nothing runs at night or without a window. Claude Code also keeps its own memory
inside the brain, one folder per person (`motores/claude-code/memoria/<partner>/`): in a shared
brain, each person's Claude Code loads only their own. Turn it off in Settings to keep it on the
machine instead. To see it: `workspace memoria ver` (with the tab active).

The tabs you see come from the brain, so they're the same on all your machines. In the tab menu,
`a` archives the highlighted tab (nothing is deleted) and `u` undoes; tabs you don't open for 15
days archive on their own (setting `sesiones.archivar_dias`; 0 turns it off) and «Archived (N)»,
at the end, brings them back. If another machine hasn't synced the brain for days, Workspace
tells you in one line when you open the agent.

## Not every engine can do the same

Each tab's memory is the same on all of them. Claude Code is the most integrated today (live
events, its own status bar, its own memory in the brain). Codex, Antigravity, OpenCode, OpenClaw, Hermes, Kiro, GitHub Copilot and Cursor run wrapped by Workspace, with some features
missing. The
exact list, per engine and per OS: [Compatibility](compatibility.md).
