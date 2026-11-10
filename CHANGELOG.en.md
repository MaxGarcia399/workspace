# What's new in Workspace

What changes in each version, told from your side of the screen. You can see
your version with `workspace version` (and at the bottom right of the hub).
Español: [CHANGELOG.md](CHANGELOG.md).

How to read this: every version has a number (`MAJOR.MINOR.PATCH`). A PATCH
change fixes things; a MINOR one brings new features without breaking
anything; a MAJOR one warns you well in advance if something changes shape.

## 0.9.0 — 2026-11-09

**New**
- **Deciders, with more models to choose from.** In Engines → Decision models,
  besides Jev, you now have:
  - **OpenRouter**, in the cloud: with a single key you pick among many
    decision models from several brands (Jev by default);
  - **Liquid**, in the cloud: d1.1 (the default) and d1-ultra, each with its
    own price;
  - **Ollama**, on your computer: no key and no cost, and your context never
    leaves your machine. If something is missing, Models tells you the next
    step in one line (open it, update it to 0.35.0 or `ollama pull nimble`).
    The first question after a while may say it is "loading the model"; the
    next one is fast.

  Each key is saved under its own name: connecting your OpenRouter key to
  Deciders doesn't take away the `OPENROUTER_API_KEY` your engines already
  use.
- **Only decision models.** OpenRouter, Liquid and Ollama also have chat
  models: those can't be picked or saved. In Ollama, the chat models you have
  downloaded don't show up in the list (one line says how many there are)
  and, if the one you had saved no longer works, it uses the first decision
  model you have and tells you.
- **You pick the model from a list.** Enter or a click on "model" opens it:
  the current one is marked with ● and each row shows the brand, the price or
  "on this computer". With 10 or more, typing filters. OpenRouter's list has
  the 10 that answered in our tests, and the one that takes longer than the
  uses wait says "slow". On Windows, for now, you choose with the keyboard.
- **"Your key, in plain words."** The help (`i`) in Decision models has a new
  page (Tab switches between "what it is" and "your key"): where your key
  lives on your system, where it travels, who sees it and a tip. When you
  connect, it recommends a key just for Workspace, with a spending cap where
  the provider allows it (OpenRouter), and when you disconnect it tells you
  where to revoke it.
- **Conversations, a new section: what your agents say to each other.** Ask
  an agent in its tab to "open a conversation with … about …": it opens a
  room of up to 6 agents, each in its own tab and on any engine, with a goal
  and with what counts as done.
  - You follow it live, each message in the color of whoever is speaking.
    From there you write (to whoever spoke last, or to whoever you name with
    "@name"), pause, close, archive or delete, and choose how long each reply
    is awaited (15 min to 24 h). If a request expires, you give it 30 more
    minutes, cancel it, or open the tab of whoever is missing. In a small
    window it looks like your phone: the list or the chat. On Windows, for
    now, it works with the keyboard.
  - Everyone reads; only whoever is asked replies. Each agent gets the room's
    goal when it joins and, along with its own messages, what happened in the
    meantime.
  - Tested with all 9 engines (Claude Code, Codex, OpenCode, Cursor, Kiro,
    Copilot, Hermes, OpenClaw and Antigravity), with rooms of four different
    engines and between a Mac and a PC. When agents are on different
    machines, the room travels with your brain, and each message takes as
    long as your sync takes.
  - Claude Code, Cursor and Antigravity keep listening and reply on their
    own. For the others, when a request or a reply arrives, Workspace types a
    line into their herdr pane so they pick it up. It does so only when the
    agent isn't working and you don't have that pane focused, once per
    message, and the hub marks it "◆ notified …". If it couldn't, the hub
    shows "waiting for …" and gives you a "Notify" button. Hermes and
    OpenClaw, for now, are notified only with the button. On Windows, the
    notice carries the command for PowerShell.
  - If your brain is on two machines and the same agent has a tab open on
    each, a room's first request can take up to 2 min to arrive: Workspace
    waits for your sync to tell which of the two took it, so both don't work
    on it.
  - When a tab opens, the agent learns on its own which rooms are waiting for
    it. Agents you create from now on come with the skill that teaches them to
    use rooms; the ones you already had read it from Workspace when a room is
    waiting for them.
  - What another agent asks is a request, not an order from you: anything
    sensitive is confirmed in each agent's own tab.
- **Deciders › Conversations** (off by default). It can mute pure-courtesy
  pings ("thanks", "standing by"), pause a room that goes in circles without
  progress, and suggest to whoever opened a room that they close it when it
  looks done. It never opens, writes or deletes anything, and what it does is
  marked "◆". With Conversations on, Security also reviews messages between
  agents and flags sensitive ones with "⚠": it works well with Jev, but with
  Liquid or OpenRouter it rarely flags anything. With Conversations off it
  reviews nothing in rooms.
- **Single color.** In Personalization, "one color" paints titles and
  accents in the theme's main color. Text and the colors that warn you about
  something stay as they are.
- **If you use Workspace inside herdr,** it follows the theme you chose in
  herdr and no longer paints its own background on top. In Personalization,
  "follow herdr" (yes/no) changes it; that row only appears inside herdr.
- **Deciders, Tone and Calendar now also work well in small windows.**

**A change you'll notice**
- **Your Jev key no longer reaches your agents.** If you only had it as a
  system variable, connect it in Engines → Decision models so your agents can
  keep asking.

**Your keys move to your system keychain**

It does this on its own, once, when it updates.
- The keys you give Workspace (for example, a decision model's or your Google
  Calendar account's) leave the plain-text file:
  - on macOS they go to your Keychain (the Keychain Access app);
  - on Windows they are encrypted with your account (DPAPI): another account,
    or a copy of the file on another PC, can't open them;
  - on Linux they go to your session's keyring if you have `secret-tool` and
    it is unlocked. If not, they stay in a file only you can read, and it
    tells you in one line.
- First it leaves an encrypted backup, checks that every key reads back and
  only then removes it from the file. If anything fails, everything stays as
  it was. It tells you in one line. To undo it:
  `workspace migrate --undo 202611081500_boveda_al_llavero`. If you go back to
  the previous version with `workspace update --rollback`, Workspace first
  returns them to the file; if the keychain doesn't answer, it doesn't go
  back.
- **The mail password is stored in the keychain too.** If you already had
  it, it moves on its own from `mail.json` (with a backup, and checked before
  it is removed from there), and `mail.json` keeps only your user and the
  server. `workspace keys` shows it too, without the value. To undo it:
  `workspace migrate --undo 202611090000_correo_a_la_boveda`.
- If your hub was open while it updated, whatever uses keys will say "no key"
  until you close it and open it again. Nothing is lost.
- `workspace keys` tells where each key comes from, without showing any, and
  `workspace keys audit` looks for plain-text leftovers.
- Your agents don't receive your keys. On top of that, for engines that have
  rules for it, Workspace denies them opening the vault and, where possible,
  asking the keychain for a key: the table is in Compatibility.
- A variable on your system can no longer send a decision model's key to
  another server: it only counts if it points to this computer or to the
  provider's.
- **What it doesn't cover:** a program running as your same user (for
  example, a script in an agent's terminal) can still ask the keychain for
  it. That's why a key just for Workspace, with a spending cap, is a good
  idea.

**Fewer system notices**
- **On Mac and Linux, a new install goes to `~/Workspace`** and your new
  agents are born in `~/Workspace/Cerebros`: outside Desktop, Documents and
  Downloads, so macOS doesn't ask you for folder permissions. What you
  already had doesn't move: if Workspace lives on your Desktop, the same
  command updates it there. If you already have a `~/Workspace` folder with
  your own things, it leaves it alone. On Windows, Workspace and your agents
  stay where they always were.
- **The diagnostics bundle (`workspace doctor --bundle`) and the uninstaller's
  backup** go to `~/Workspace/Respaldos`, no longer to the Desktop, and it
  shows them to you in their folder. When you uninstall, `Cerebros/` and
  `Respaldos/` are kept.
- **On Mac, Discover no longer goes into Desktop or Documents on its own**
  (that could open two or three permission prompts in a row). If your brains
  are there, press `e` in Discover: the first time it tells you what will
  happen and the second time it searches. The folder where Workspace lives is
  still checked without asking.
- **One line before each notice that can't be avoided.** Before installing
  Codex or Kiro on Windows, or Kiro on Mac, Engines tells you what the system
  is about to ask. When connecting Google, before asking for the file (on Mac,
  from your Downloads folder) and before opening the browser ("Google hasn't
  verified this app"). The manual's new page, **Your system's notices**, puts
  them all together: what shows up, why, what to answer and what happens if
  you say No.
- **The OpenClaw gateway that Workspace turns on no longer announces itself
  on your network** (Bonjour): iTerm2 or VS Code no longer ask to find
  devices on your local network. If you found it from another device through
  Bonjour, that stops working.
- **With your Mac's Keychain locked, Engines no longer asks for your
  password** to check your GitHub Copilot session: it shows that it doesn't
  know.
- **Voice dictation (`workspace voice`) now only copies the text:** a sound
  plays and you paste it. macOS only asks for the microphone, and dictation no
  longer reads what you had copied. **If you had a Shortcut that pasted on
  its own, add `--paste` to it**; if pasting fails, the text is still copied.

**Security fixes (Deciders, since 0.8.0)**
- Context marked private and files reached through a link are no longer sent
  to Jev.
- An invalid answer from the model can no longer apply a decision.
- An https proxy with a password is refused instead of sending it
  unencrypted.
- Deleting a key from the keychain is actually verified, and retried if it
  fails.

**Fixes**
- **Codex:** Workspace commands inside a Codex tab use that tab's identity.
  Before, with another Codex tab open, they could run as the other one, and a
  memory note could be saved to the wrong tab.

## 0.8.1 — 2026-11-07

**New**
- **Deciders shows up in the hub, next to your agents.** Below them sits the
  «◆ Deciders» row, with the active decision model where an agent shows its
  engine (for example, "Jev"). With no model it says "new" for 7 days (from
  the first time your hub shows it) and then "set up"; Enter takes you to
  Engines → Decision models to connect one. With a model, Enter opens
  Deciders and ← → switch the active model among the ready ones and "off"
  (saved the same way as in Deciders → Settings). `0` opens it from the
  hub's start, the way digits 1-9 open your agents. Turning the model on
  doesn't turn on any use: you pick those in Deciders.

**Fixes**
- **A tab no longer reopens an old conversation after Claude Code forks it**
  (for example, when you send the conversation to the background): the tab
  moves to the new conversation and the hub reopens it there. If you use
  `/fork` and keep writing in the original, the tab goes back to it. Tab
  lists show a single row per tab, with the conversation it really opens.
- **Memory tells finished work apart better.** A note told in the past tense
  ("I tested…", "I fixed…", "I installed…") is marked «hecho» (done) with
  more confidence, instead of staying a «nota».
- **Review compares against what you asked for and doesn't believe what the
  deliverable says about itself:** a report that says "all 8 uses are
  verified" with two still pending no longer comes out "complete", and a
  part you asked for that was left pending counts as missing. With long
  reports it can still hesitate: it works best in "suggest".
- **`workspace decidir` tells how long the model took to answer** (`ms`, the
  same number History keeps); before, that value didn't come.

## 0.8.0 — 2026-11-07

**New**
- **Deciders, a new section that comes switched off.** A decision model does
  not chat or write: it picks among fixed options and says how sure it is.
  Today there is one, **Jev** (by TypeSafe, in the cloud). You connect it
  once, in **Engines → Decision models**: paste your TypeSafe key and test it.
  TypeSafe bills its use to your account; in Ask you see beforehand how many
  tokens each question carries (including the fixed part it carries even
  without context) and an approximate cost.
- **Where it can help.** Each use has its level (off · observe · suggest ·
  decide) and all of them start off:
  - in Workspace: the type of a memory note, how a session ended (Evals),
    whether a session deserves a skill and how risky something an agent wrote
    is (Security: in Claude Code, only when the scan already found a risk);
  - for your agents: choosing among options, checking whether a deliverable
    is complete, picking the best of several instructions and splitting work
    between agents. In GitHub Copilot, Cursor, Kiro and Antigravity the agent
    uses the `decidir` tool; in Claude Code, Codex and the rest, the
    `workspace decidir --stdin` command (a JSON on standard input, as its help
    explains), which asks for permission like any other command.
  - "Suggest" only shows the answer; "decide" applies it only when it beats
    your threshold, and never when the model did not say how sure it was. If
    the model fails or takes too long, everything carries on as if Deciders
    did not exist.
- **Three uses with their own rules.**
  - **Security can only raise the risk, never lower it:** in "decide" it only
    applies "alto" (high); "medio" or "bajo" stay a suggestion and the scan's
    warning stays whole. It judges only the code: before asking it, the
    comments and docstrings are removed, so what the file says can't talk it
    into anything.
  - **Review** gets what you asked for separately from what was delivered:
    what the deliverable leaves pending and wasn't in the request doesn't
    count as missing. With long reports it can still hesitate: it works best
    in "suggest".
  - **Skills in "decide"**, when the model is sure (at your threshold or above), no
    longer waits 2 hours between reviews: if it says the session deserves a
    skill, the review arrives (never two within 10 minutes); if it says no, it
    doesn't. Below your threshold, and in "observe" and "suggest", those 2
    hours still rule.
- **You see what it does**, with a use in "suggest" or "decide" ("observe"
  shows nothing):
  - when the decision model steps in, the agent tells you in the chat with a ◆
    block at the end of its reply, one line per intervention: what it did, how
    sure it was and whether it was applied or only suggested. Each line carries
    the name of the model that answered (with Jev: «◆ Jev: table · 87 % ·
    suggested») and reaches the agent with the reminder to show it to you, so
    it doesn't depend on what it remembers from its start;
  - when a note is saved, Memory says so only if it suggests or applies
    another type («◆ Jev: saved the note as hecho · 88 % · applied»); in
    Claude Code, the Security line shows up in the conversation next to the
    warning, and what the agent didn't see in its turn reaches it with your
    next message;
  - when the next session opens, one line says what it thought of the last
    one (Evals and Skills), only once;
  - History says what each decision changed («nota → hecho», «warning →
    high») and how many there were today; next to each use's threshold you
    see its latest confidences;
  - Workspace's status bar adds «◆ Deciders: today 7 · 1 applied» (Claude Code,
    GitHub Copilot, Cursor and Antigravity);
  - in Claude Code, if you change an agent use mid-session, the agent finds
    out with your next message; in the other engines, when another session
    opens.
- **Ask**, to try it by hand with the context you choose: nothing, the tab,
  some sessions, the memory or the whole brain. `v` shows which files would go
  (never their content) and how many were left out. **History** shows what
  was asked and what the model answered, and there you grade whether it was
  right; that log stays on your computer.
- **What leaves your computer, and only with a use turned on:** the question,
  its options and minimal context go to TypeSafe. Keys and passwords are
  removed before anything leaves, and so are tokens (JWTs too). With Memory or
  Brain, your private files
  (`privado: true` or a `privado/` folder), what belongs to other people in a
  shared brain, chats, messages between agents and logs never leave. The
  first time Ask sends brain content, the answer tells you. With everything
  off nothing leaves and your agents see the same as before.
- **Engines now has two cards:** Agent engines (the usual screen) and
  Decision models.
- Turning an agent use on or off changes only Workspace's part of the brain's
  Kiro and Cursor configuration, with no backups or warnings; with everything
  off it stays the same as in 0.7.0.

**Fixes**
- **On Windows, the vault with your keys and Deciders' local files can now
  be read only by your user** (and the system). The vault, with every key you
  give Workspace (mail's, your decision model's…), was already there in 0.7.0
  and inherited the
  `.claude` folder's permissions: on one PC that let another account (the
  Codex sandbox's) read it.
- **On Windows, Ctrl+C inside a hub section no longer closes the hub:** it
  goes back to the menu. Before, the hub closed with an error.
- On Windows, in Deciders, Decision models and the Engines door: Shift-Tab
  goes back one tab, the characters ¿ ¡ « » € arrive even when you type over
  SSH and, without a real console, the screens print their view and finish
  instead of waiting.

## 0.7.0 — 2026-11-06

**New**
- **Workspace starts keeping, on your computer, a record of how your agents
  work.** When each session closes it notes only numbers and names: how long
  it took, tokens and model, the cost when the engine reports it, how many
  tools failed, interruptions and which skills the agent read. Never the text
  of the conversation; tabs and files are kept as fingerprints, not by name.
  **Workspace does not send them to anyone**: they stay in
  `~/.claude/workspace/metricas/`, in a folder only your user can open (on Windows,
  inside your user profile). It is
  the base for the performance section coming later, so that by then there
  will be weeks of history. The sessions you already had are measured little
  by little as new ones close, without making you wait.
  - It measures Claude Code, Codex, OpenCode, OpenClaw, Hermes, Antigravity,
    GitHub Copilot, Cursor and Kiro. Each engine gives what it keeps: Cursor
    records no times, model or tokens, and Kiro keeps no tokens (only its
    credits); whatever an engine doesn't give is left empty, never zero. For
    Gemini it records, for now, only when each session happened and how long
    it lasted.
  - It works the same on Mac and Windows (also with accents or «ñ» in your
    user name).
- **A one-line notice, only once**, in the menu or when opening an agent,
  tells you what is kept and how to see it, turn it off or delete it.
- **`workspace metrics`** (or `workspace metricas`): `status`, `health`,
  `import` (measures this computer's history in one go), `export --json
  <file>` (totals only, without people, in case you decide to share it),
  `delete --mine`, `delete --all` or `delete --before YYYY-MM`, `off` and
  `on`. You can also turn it off in Settings («Performance metrics»). What you
  do while metrics are off is never measured, not even after turning them
  back on. If a file cannot be deleted (on Windows, because another program
  has it open), `delete` tells you which one instead of reporting it as gone.
- **Metrics are never passed to the agent**: it does not see them while it
  works.
- The diagnostic bundle (`workspace doctor --bundle`) includes the metrics
  health, numbers only.

**Fixes**
- **On Windows, Engines now recognizes your GitHub Copilot session.** Copilot
  keeps the account in its config file when there is no keychain, and
  Workspace couldn't read it: it showed «couldn't check» while you were signed
  in. It now only looks at whether there is a user; your token is never used.
- **With GitHub Copilot, the start and the end of each session now run only
  once.** Copilot also fires the start, per-message and closing hooks
  Workspace sets up for Claude Code, so the tone, the tab's memory, the
  conversation backup and the skill review ran twice. Workspace now
  recognizes those repeated calls and does nothing with them.
- **On Windows, with accents or «ñ» in your user name, memory, the backup
  and the other closing steps find your brain and your conversation.**
  They used to read the path with the console's old encoding («JosÃ©»
  instead of «José») and, with some engines, found nothing to save.
- **On Windows, the Antigravity bar and the bar of the agents you create from
  now on no longer come out empty** when the folder has certain accents (for
  example «Á»). The bar of the agents you already had stays as it was.
- **On Windows, Hermes, OpenClaw and OpenCode metrics are no longer lost
  when a brain lives in a long path** (for example in the
  OneDrive Documents folder). Windows refuses paths longer than 260 characters,
  and the numbers file Workspace keeps next to the backup went over that
  limit: the session ended up without tokens or cost. It is now written and
  read anyway, without changing any setting on your Windows.
- **On Windows, two agents closing at the same time no longer erase each
  other's record.** When the closes overlapped, a line could be lost or cut
  in half; now each one is added whole.

## 0.6.0 — 2026-11-06

**New**
- **Three new engines: GitHub Copilot, Cursor and Kiro.** Install them from
  Engines; they open your agents with your account, on the same brain as
  your other engines: they read the same `AGENTS.md`, each tab resumes its
  conversation and, on close, Workspace packs the handoff like with the
  others. Tested live on a Mac and on Windows 11 (Linux is still to be
  tested).
  - **GitHub Copilot** (`copilot`, GitHub's official CLI) runs with your
    subscription and your account's model. In Copilot's settings Workspace
    only writes its bar (with a copy of the file first); the rest goes on
    each launch. One agent doesn't read another's conversations: Copilot's
    session search is one for your whole account and Workspace turns it off
    on each launch (if you pass your own `--excluded-tools`, yours win). It
    installs with npm on Mac and Linux and with WinGet on Windows (on the
    Mac, not the Homebrew one: macOS holds it back and shows a warning that
    won't close). On Windows, Copilot also runs the hooks Workspace sets up
    in your brain, so each hook now carries a PowerShell version too: they're
    rewritten on their own when you update (if not, `workspace doctor` does
    it).
  - **Cursor** (`cursor-agent`) uses the model you pick in Cursor. In its
    settings (`cli-config.json`) Workspace only adds its bar, and on each
    launch it tells Cursor to trust your brain's folder (the mark stays in
    Cursor's folder, not in your brain). On a Mac, install it from Engines:
    the Homebrew package doesn't start. On Windows it boots and uses its
    tools even if you open Workspace from Git Bash. What Workspace assumes
    about Cursor comes from its official docs or from running the program,
    never from its code (Cursor's terms ask for that).
  - **Kiro**, AWS's terminal agent (`kiro-cli`, formerly Amazon Q Developer
    CLI), versions 2 and 3, uses the model you pick in Kiro. On each launch
    it tells Kiro to trust your brain's folder, without saving it, and it
    writes nothing in `~/.kiro`: its agent lives in your brain
    (`.kiro/agents/workspace.json`). If you haven't signed in, it offers that
    before opening. Kiro's bar is its own, untouched: if you want to see your
    usage and credits, turn them on in `/settings display` inside Kiro.
- **Copilot, Cursor, Kiro and Antigravity save memory without asking you,
  and the terminal still asks.** The agent saves with a Workspace **memory
  tool** (MCP: `guardar_nota`, `guardar_resumen` and `ver_memoria`), not a
  terminal command: the engine approves it by name and no terminal reads the
  note's text, so there's no way to sneak another command into it. The tool
  only writes in the tab of the window that opened it: no other brain, no
  other tab. Copilot gets it on each launch (nothing written in its
  settings); Cursor and Antigravity, in your brain's project settings
  (`.cursor/` and `.agents/mcp_config.json`); and Kiro, in your brain's
  `workspace` agent, picked on launch (if you pick another agent in Kiro,
  yours wins). In Antigravity it replaces the memory command Workspace used
  to approve: since its version 1.5.1, Antigravity approves by the start of
  the command, so that permission also ran whatever was written after it.
  That permission is removed on its own when you open the agent, and your
  Antigravity rules are kept as they are; if you pass your own `--settings`,
  yours wins and memory asks you first. If the tool fails, the agent tells
  you instead of writing the memory by hand, and it works even if Workspace
  runs from a Python virtual environment you later delete. Tested live on a
  Mac and, with Copilot, Cursor and Kiro, on Windows 11 (Antigravity on
  Windows is still to be tested).
- **Your tabs are the same on every machine.** Each machine now knows who you
  are across all your brains: you tell it once (or it takes it from what you
  already had) and it never guesses with someone else's folder. The tab list
  comes only from the brain, so what a machine kept on the side (old tests,
  removed tabs) no longer shows up or comes back. If you were two users in a
  brain (an old name and a new one), they merge on their own without deleting
  anything; `workspace identidad deshacer` puts everything back, the tabs
  from your previous name included, and the next launch doesn't merge them
  again.
- **Archive tabs without deleting them.** In the tab menu, `a` archives the
  highlighted tab and `u` undoes; «Archived (N)» at the end brings them back.
  Tabs you don't open for 15 days archive on their own (setting
  `sesiones.archivar_dias`; 0 turns it off), with a one-line notice that
  always shows «u to undo». Archiving travels: the tab leaves the menu on all
  your machines, and opening it brings it back. After updating there are 15
  days of grace before the first automatic archive, and a machine that
  arrives with an out-of-date brain archives nothing. From the terminal too:
  `workspace sesiones lista|archivar|desarchivar`.
- **Workspace tells you when your brain isn't syncing.** Each machine leaves a
  small record in the brain (`STATE/maquinas/`); if another machine has been
  silent for days, Obsidian is closed or there are conflicted files, you get
  one line when opening the agent and in `workspace doctor`.
- **Carry your Claude Code conversation to your other machine (optional, off
  by default).** It's turned on per brain with `workspace sesiones
  conversacion on` (and applies to every machine and person who uses that
  brain): closing a tab saves its conversation compressed in the brain and your
  other machine resumes it as is; opening only brings back yours. In a shared
  brain, everyone who uses it can see those conversations: for privacy, use a
  separate brain. It isn't uploaded if it's over the cap
  (`sesiones.conversacion_max_mb`, 4 MB) or if it contains something that looks
  like a key, and it never goes to git. With Obsidian Sync, turn on «Sync all
  other types» on each device.
- **GitHub Copilot and Kiro write in their agent's brain without asking
  you**, like the other engines, when the agent has "its brain without
  asking" (the default; you change it in Agents). Outside the brain (also in
  a sibling folder with a similar name) they still ask, and the terminal
  asks as always; with the option off, they ask before every file. Nothing
  is written in Copilot's or Kiro's settings: in Copilot it goes on each
  launch (if you pass your own permissions, `--allow-tool`, `--yolo`…, yours
  win) and in Kiro, in your brain's agent. If the brain's path has
  parentheses, Copilot rejects the rule and keeps asking (it tells you on
  launch). Tested live on a Mac; Windows is still to be tested.
- **The agent can't touch the settings of any engine, or of git or Obsidian,
  inside its brain.** Your brain is shared by all your engines, git and
  Obsidian, and each one loads its settings from there on launch (hooks, MCP
  servers, agents, plugins): an engine writing another's could grant itself
  permissions or leave a command that runs later. Now, when the agent writes
  in its brain without asking, none of its engines (Claude Code, Antigravity,
  Copilot, Cursor or Kiro) can write with its file tools in `.git/`,
  `.github/`, `.agents/`, `.cursor/`, `.kiro/`, `.codex/`, `.gemini/`,
  `.vscode/`, `.obsidian/`, `.opencode/`, `opencode.json`, `.mcp.json` or in
  the settings, skills, agents, commands and hooks in `.claude/` (not with
  capital letters either, like `.KIRO/`). It's denied, not asked (in Claude
  Code it used to ask): if you want to change those settings, do it
  yourself. Your notes, skills and documents in the brain are written as
  always, and Workspace still writes its own files there. In Claude Code the
  rule lives in the brain's settings, next to the permission to write in
  it: it also holds if you open it outside Workspace (VS Code, the desktop
  app or plain `claude`), and your existing brains get it on their own when
  you update. If Antigravity can't get it (you pass your own `--settings` or
  its settings file can't be read), it asks before editing and tells you on
  launch. On Windows, with a very long brain path, GitHub Copilot asks
  before writing (the rules wouldn't fit in the command line) and tells you
  on launch. Codex, opencode, OpenClaw and Hermes don't change: they use
  their own protection. Tested live on a Mac; Windows is still to be tested.
- **Your project settings are respected: Workspace only adds its own.** In
  your brain's `.agents/mcp_config.json` (Antigravity) and `.cursor/mcp.json`
  and `.cursor/cli.json` (Cursor), Workspace only puts its memory server and
  its rules: your servers (for example, `github`) and your permissions stay
  as they are, and the file keeps its permissions. If someone changed
  Workspace's part, only that is restored (with a backup) and you get a
  one-line note. If that folder is a link (for example, to your shared
  skills) or the file can't be read, it's left alone: memory asks you for
  permission and you're told on launch. Your `.gitignore` ignores those
  files.
- **Engines says whether Antigravity is full or "experimental".** Google
  doesn't support using Antigravity inside other apps on a consumer plan
  (https://antigravity.google/docs/faq/). With a Gemini API key or a business
  account (Google Cloud project), Engines says "full". If you sign in with your
  Google account, since Antigravity doesn't say whether the plan is personal,
  it says "experimental" and explains why. Everything works the same: it's
  just the notice.
- **Clearer wording about engines.** The README, the manual and the Engines
  help (`i` key) say what Workspace does: it sets up and opens your official
  engines, with your account. They also note that Workspace isn't affiliated
  with the companies behind the engines, and the README map now shows all
  nine. Screens and messages now just say "engine" or "Workspace" instead
  of a technical term.

**Fixes**
- **On Windows, the Antigravity and Cursor bars show up even if your user name
  has spaces** (for example "Ana Lopez"). Before, the terminal cut the
  quotes off the command and the bar didn't appear; now the folder goes by its
  Windows short name. Mac and Linux are unchanged.
- **On Windows, an engine that hangs no longer leaves processes running.** When
  Workspace has to stop an engine that isn't responding (checking your account,
  its version or a windowless turn), it now also closes the programs that
  engine started underneath, instead of waiting forever. Mac and Linux are
  unchanged.
- **The one-line notices when you open an agent now show up** (for example,
  "Workspace updated to v…", and the new ones about merged users, a brain
  not syncing and archived tabs): they appear under the banner, right before
  the chat. Before, the banner cleared the screen and wiped them. Works for
  every engine.
- **A Codex tab resumes again after an abrupt close.** If Workspace was
  killed (a crash or `kill -9`; not closing the window), the engine stayed
  open in the background, and Codex won't resume a conversation while
  another process holds it: reopening the tab started from scratch. Now
  Workspace closes that engine right away, as if you closed the window (it
  gets a few seconds to save), and if that didn't happen, on reopen it first
  closes every engine left running and then resumes. This applies to every
  engine. Mac and Linux; Windows is still to be tested.
- **Claude Code: the handoff is no longer lost if the program closes
  abruptly.** Workspace built it only when the session closed; after a crash
  (a `kill -9`, a frozen machine, a power cut) the tab had no handoff until the
  next normal close. Now it's refreshed at the end of every reply (no AI, and
  you won't notice: it takes milliseconds), so it carries up to the last one.
  The usual close still does the rest.
- **Hermes 0.22.5 works as before again.** Since that version Hermes names
  its conversations differently and Workspace couldn't find them on close:
  the tab started from scratch and the handoff stayed empty. Now it resumes
  each tab and fills its handoff; each tab saves its memory in its own tab
  (Hermes runs every conversation in a single background process, and a note
  from another tab, or another agent, could land in the first one), and a
  `/resume` inside Hermes, after chatting, is respected on close.
- **Removing an agent or uninstalling cleans up what Workspace left in your
  engines, and only that.** Removing an agent from Agents now also removes
  the trust Workspace gave its brain in Codex and Antigravity (until now
  only uninstalling did it) and the memory tool in its brain. Uninstalling
  also removes Copilot's and Cursor's bars with their commands, the copy of
  Copilot's settings and the trust marks Workspace left. Only what Workspace
  wrote is removed, exactly as it wrote it: what you added, other agents
  (even if they share the brain) and your other folders stay; a file or
  folder is deleted only if it's left empty, and edited files keep their
  permissions.
- **On Windows, installing an engine from Engines is no longer blocked by
  Microsoft Defender.** Defender flagged as a trojan the one-line command
  that downloads the installer and runs it at the same time, and nothing got
  installed. Now Workspace first downloads the official installer (HTTPS
  only), runs it as a file in the same terminal and deletes it afterwards;
  if the download fails, it tells you in one line and nothing runs. This
  covers Claude Code, Codex, Antigravity, OpenClaw, Hermes, Kiro and Cursor;
  nothing changes on Mac and Linux. Also, the installer's closing line names
  all nine engines.
- On Windows, saving to the brain no longer fails silently when the antivirus
  or Obsidian has the file open: it retries and, if it can't, it tells you
  (before, a message or a note could be lost).

## 0.5.1 — 2026-10-21

**Fixes**
- **The memory map leaves the hub's front page**, where it got mixed up
  with your agents, and stays in Documentation: open it with its first row
  or the `m` key. It works as always: with the agent chosen there, Tab
  switches agent and Esc takes you back to the chapters.
- **With no agents, the first ↓ on the front page now moves the cursor.**
  Before, it stayed on Menu and you had to press it again.
- **Hermes saves the skills it learns in the brain.** They go to your
  agent's `skills/aprendidas/` instead of its shared profile: one agent no
  longer sees what another learned, and when the session closes Workspace
  adds them to the brain's catalog so your other engines can use them too.
- **Hermes no longer asks you to approve Workspace's hook when it opens.** If
  you have hooks of your own in its profile, it still asks as before.
- **Hermes gets your brain's long-term memory** (`STATE/MEMORY.md`) when a
  conversation starts, like your other engines: it no longer depends on the
  agent deciding to read it. When you resume it, it gets it again only if it
  changed, so it doesn't pile up in the conversation every time you reopen it.
- **From Discord, Telegram, Slack, WhatsApp or any other messaging platform,
  Hermes can no longer search your other agents' conversations.** Workspace
  turns off its conversation search and its own memory there too, as it
  already did in the terminal.
- **Two tabs of the same agent no longer erase each other's memory.** When
  one closes (in OpenClaw, Hermes, Codex or OpenCode), the memory block stays
  while the other one is still open, and the last one to close clears it
  even if it wasn't the one that wrote it.
- **With two tabs of the same agent open at once, each one knows which it
  is.** In Hermes and OpenClaw, the one you opened first no longer thinks
  it's the second one, sees its memory or saves its notes into it.
- **Opening an agent with OpenClaw for the first time no longer fails for
  taking too long.** Workspace prepares its profile in a single step and
  gives it the time it needs; if it still runs over, it tells you in one
  line and reopening it is enough.
- **OpenClaw no longer learns skills on its own.** Its "Skill Workshop" ran a
  weekly review per agent, with no window, and saved what it learned outside
  your brain; Workspace turns it off. Asking it to create a skill still works.
- **OpenClaw recovers the conversation you closed with the X sooner**: when
  you close another tab normally, Workspace saves it. While it saves on
  leaving OpenClaw you see «Saving…» in the middle, instead of a still window.
- **OpenClaw knows who you are and, on Windows, that its terminal is
  PowerShell.** The tab block names the active partner and reminds it to
  separate commands with `;`.
- **When Workspace uses OpenClaw without a window** (for example, to
  personalize an agent), each request goes in its own conversation and no
  longer mixes with your agent's main one; each one starts by telling it who
  it is, so it answers with your agent's name.
- **On Windows, when Workspace uses OpenClaw or OpenCode without a window,
  the engine gets your whole request.** Before, only its first line arrived (when
  personalizing an agent, without the rules or what you typed in the form),
  and quotes in that text could make Windows run part of it as a command.
- **If OpenClaw's backup fails when you leave, the notice stays on screen and
  Workspace tries again** the next time you open the agent. Before, clearing
  «Saving…» also erased the notice and what was in the terminal, and the
  backup wasn't retried.
- **Your agent introduces itself with the name its identity gives.** When
  Workspace uses OpenClaw without a window, the agent answers with the name
  in its `BRAIN.md` («# Soy Ventisca») even if its folder is called
  something else, and an agent you load from its folder takes that name.
  The agents you already have keep theirs.

## 0.5.0 — 2026-10-21

**What's new**
- **«Loading…» when you open an agent.** While Workspace prepares it, before
  the tab menu, you see «Loading…» in the middle of the screen with the
  agent's name, instead of a still screen. In Hermes and OpenClaw it also
  shows after you pick the tab, while the tab is prepared and, in OpenClaw,
  while its gateway starts. It hides no notice: if Workspace has something to
  tell you, it shows up below.
- **The memory map**, on the hub's front page: the «Memory map» row, right
  below your agents, opens it with the agent you were pointing at (Esc takes
  you back to the hub). It's also in Documentation (the first row, or the `m`
  key). It's the chosen agent's real brain tree, as in «Add agent», with what
  lives outside it (this PC and its engine's conversation). Each tab (the
  whole path, open, work, close, resume, each person, the engines and what it
  learns) lights up the files it touches, in order and in colors: what is
  read, what is written and what belongs to each person, with your real user,
  tab and engine session. ← → or the numbers change step; ↑↓ scrolls when it
  does not fit; Tab switches agent; Enter opens what proves it.
- **Hermes and OpenClaw use the same memory and skills as the other engines.**
  Their built-in memory stays off (so no agent reads another's
  conversations); what changes is that they now get your brain's properly:
  - **Hermes, when you resume a tab**, gets the tab's up-to-date memory with
    your first message, including what you noted in another engine, and again
    if someone else changes it while it's open. Before, it kept the memory it
    had when the conversation started. It uses the same hook as the tone, so
    it needs you to have approved it.
  - **Hermes uses your brain's skills** and no longer creates skills in its
    profile, which all your agents share (one agent's showed up in the others).
  - **OpenClaw reads your brain's long-term memory** (`STATE/MEMORY.md`) on
    every message, through its official hook. Its semantic search stays off:
    indexing your brain would send your notes to an outside service.
  - **What Workspace asks OpenClaw without opening a window** (for example,
    personalizing an agent) is answered by your agent, not by OpenClaw's
    built-in agent.

**Fewer things in sight (they are removed in 0.6)**
- **Workflows** (`workspace wf`), the **Proyectos** app (`workspace projects`)
  and the **split terminal** (`workspace split`) no longer show up in the
  help, the Commands screen, the manual or Documentation. If you type the
  command, it still works as before.
- The split terminal no longer opens from the hub even if you had it on:
  your agent opens in the normal window, with the same tabs and
  conversations. Its settings leave Personalization.
- In 0.6 their code is removed: Proyectos and the split terminal go away,
  and Workflows stays only for people who develop Workspace. Your data
  stays: your projects (`~/.claude/workspace/proyectos/`), your workflow
  runs (`~/.claude/workspace/workflows/`) and your settings remain on your
  machine; nothing is deleted.

**Fixes**
- Documentation no longer says that only Claude Code gets your tone with every
  message (Hermes does too) or that the handoff keeps the files touched in every
  engine (only in Claude Code and Codex).
- `workspace doctor` no longer says that a `MEMORY.md` (or a `memory/` folder)
  loose in the brain root "does not affect" anything when the agent uses
  OpenClaw: OpenClaw reads it on every message as if it were the agent's
  memory. It offers to move it aside to `motores/openclaw/` (`workspace migrate
  --offer …`, or "no thanks" with `--decline`); it never deletes anything.
- The manual no longer says that Hermes' profile is created by copying your
  keys: it's created with your model and without your keys, and you connect the
  provider once in Engines › account and provider.
- A rule you wrote yourself that asks for approval or confirmation (for
  example, «If in doubt, I ask before deleting») no longer makes your agent
  hear, when it opens, that «approvals were retired». That notice only shows
  up if your brain still has, word for word, an old Workspace template
  instruction about approving skills or memory, and it tells the agent your
  rules are respected.
- **No text gets lost against the theme background in your agents' chat**
  (some text was almost black on the dark background):
  - Claude Code paints all of its text with the hub theme (tool results,
    "User rejected…" and markers were dark grey), readable in Terminal.app
    too.
  - Hermes, OpenClaw and Claude Code on its automatic theme know whether the
    background Workspace painted is dark or light: with a light terminal
    profile they wrote black on the dark background.
  - In iTerm2 3.5 or newer, the macOS 26 Terminal, Windows Terminal, VS Code
    (Mac and Linux), WezTerm, Ghostty and kitty, the terminal's 16 colors (the
    ones Codex and commands use) come from the theme. Other terminals are left
    alone. Closing the hub gives the terminal its colors back; if you opened
    an agent, it keeps them until you close the tab, as it already did with
    the background.
  - A light custom background with a dark theme (or the other way round) no
    longer leaves the text unreadable: the theme keeps its own background. A
    separate background on a theme without its own background now paints the
    text too, and red light on a light theme keeps the background light,
    tinted red.
  - `workspace doctor --bundle` includes your terminal and the theme each
    engine uses, without any key.

## 0.4.1 — 2026-10-18

**Fixes**
- The **Users** section no longer shows three names that belong to no one.
  Agents created with 0.2.0 or earlier came with three empty example folders,
  and 0.4.0 took them for users. When you open the agent (or the section),
  Workspace removes them on its own: the profile it had created for them goes
  to `STATE/users/_archivo/`, and it never touches anything with tabs,
  preferences or memory, nor whoever uses that machine.

## 0.4.0 — 2026-10-18

**What's new**
- **Each tab remembers the same thing on any engine.** Your agent saves what matters right away, with a label (decision, pending, done…), and when you open the tab —on that engine or another— it gets the summary, what is still open, what is new and a "handoff" with the latest from the other engine. Workspace sorts and archives it on its own, with no AI and nothing for you to do; nothing is deleted.
- New **Users** section in the menu: who uses each agent, «that's me on this PC», rename, and merge two users who are the same person (for example, your Mac one and your PC one). Each user has a fixed ID, so another machine with an old name lands on the right one.
- New **Documentation** section in the menu: everything Workspace does, chapter by chapter, with a simple map, what is happening on your PC right now and how to check it yourself (Enter opens the file).
- No AI process works without an open window: the "distiller" that summarized memory on its own and asked you to approve proposals is gone. If you have skill review turned on, your agent does it when it opens its next session, in plain sight.
- **Your agent keeps its skills, memory and identity up to date on its own.** It doesn't ask you to approve skills or to confirm what it notes down; once a week it curates its skill library by itself, and it completes its personality (`BOOT/00-SOUL.md`) from what you told it when you created it and from your corrections, never from what it reads in documents or pages. Everything stays recoverable and it tells you in the line at the end of its reply.
- If an agent's engine isn't installed, the agent no longer gets stuck: it offers to open it with another engine, just this once or from now on.
- Closing the window with the X no longer loses anything: the tab's memory is sorted on close or, if there wasn't time, the next time you open that agent.
- With OpenClaw you can now have several agents open at once (before, with one open, the others would not open). The first tab takes a few seconds longer to open and, when you close the last one, OpenClaw stops on its own.
- Claude Code keeps its own memory inside the brain, in one folder per person: it travels with you to your other machines and, in a shared brain, each person's Claude Code loads only their own and never mixes up who it belongs to (turn it off in Settings).
- Antigravity saves memory without asking for permission on every note.

**What this version changes in your brains when you update**

It does it on its own, once, in each agent. Before moving or changing anything it copies it to a backup, and nothing is deleted.
- Your agents' identity moves to `BRAIN.md`, a file that belongs to no vendor. Nothing changes in how you use your agents: each engine still comes in through its usual file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`), which now just points to `BRAIN.md`. If an agent had something unusual (for example, you edited its identity a moment ago), it is left as it was and `workspace doctor` tells you. To go back: `workspace migrate --undo 202610151600_brain_identity_neutral`.
- Your agents' memory instructions are brought up to date, no matter which version you created them with; also when the agent arrives later (a fresh install or another machine), as you load it. If you wrote your own memory rules, they are left alone: the agent still gets how to save when the tab opens.
- The tray where the distiller left proposals for you to approve (`STATE/DESTILADO.md`) moves to `STATE/memoria-archivo/`. Proposed skills that were waiting for your approval move to `skills/_archive/` if skill review is off for that agent; if it is on, they stay until its next review, where your agent integrates the useful ones and marks them resolved on its own, and Workspace archives them by itself.
- Nothing in your brains waits for your approval. The skill, memory and identity instructions that asked for a person (approving new skills, "untouchable" skills, confirming before noting something in memory, designing the agent's personality by hand) are brought up to date, and so are the steps that made the engine ask you for permission (recording a skill's use with a command, a `git commit` before curating). Only the lines still exactly as Workspace left them change: what you wrote yourself is left alone, and your agent is told when it opens that those approvals are gone. What was left in `skills/_propuestas/` (its README and `_mejoras/`) moves to `skills/_archive/`.
- Each brain's `.gitignore` adds Workspace's working folders (`.claude/locks/`, `.claude/memoria-entrada/` and `.claude/skill-review/`), including in the brains you already had.
- If one brain can't be updated (for example, a file locked by sync), the others update anyway and that one is retried on its own next time.
- If you share a brain between machines (for example, your Mac and your PC through Obsidian), each one can update its copy before receiving the other's and syncing won't leave archived items twice: the name comes from the content (`DESTILADO-<fingerprint>.md`, `propuestas-<fingerprint>/`), not from the day, and what another machine already archived isn't archived again.

**Privacy and security**
- Your account tokens (for example, Google Calendar) and the keys you saved in Workspace no longer reach the engines or anything your agents run; only the hub uses them.
- A connection that carries a key never sends it to another server, and email checks that it is talking to the right server.
- `GEMINI.md` is left clean on close (no path of your PC and no startup context).
- Local telemetry and «get skills» when creating an agent now come off; turn them on in Settings and during creation.

**Fixes**
- Windows: the Workspace menu opens on its own again when you open a terminal. With Windows' factory settings, PowerShell blocked its startup file and showed "running scripts is disabled on this system". When you update, Workspace adjusts that setting for your user only, to the value Microsoft recommends and without asking for admin rights. If your organization manages your computer and has it locked, it tells you. After updating, open a new terminal.
- On Windows, uninstalling now really deletes the Workspace folder (it used to say «deleted» and leave it) and, if something is still in use, it tells you.
- Asking for help (`--help`) from the installer, the uninstaller or any command shows the help and never runs anything.
- `workspace uninstall --clean-all` (or the question when uninstalling) also cleans your brains and the engines: it removes only what Workspace wrote in them (settings, permissions and generated files), with the exact list first and a backup next to every file that changes; what you edited by hand is left alone. Workspace's OpenClaw and Hermes profiles, with your conversations there, are not deleted: they are moved to a backup folder next to each one.
- Uninstalling only removes the terminal commands and Claude Code themes Workspace added (it recognizes them by their mark) and names them before you confirm. On Windows it also removes its `.cmd` commands, even if its folder isn't called «WORKSPACE».
- Uninstalling without a terminal to ask you (from a script or an agent) no longer deletes anything unless you add `--yes`. And if the Workspace folder is a git checkout with unpublished work (uncommitted changes or unpushed commits), it isn't deleted: the rest is uninstalled and you're told what's there.
- Users no longer rewrites a profile it doesn't understand: it keeps your own lists and fields, recognizes a profile saved with Notepad without changing its ID, and one it can't read is kept whole on the side and replaced by a new one with the same ID.
- Users in a brain shared between machines: every machine gives the same user the same ID (it used to be random and, after syncing, the profile could keep one machine's ID and its tabs the other's). A tab left with an ID that belongs to nobody fixes itself when you open the agent.
- Mac: reinstalling or updating applies what you chose about the terminal opening the hub on its own (Windows already did), and the installer says which one is in place.
- Documentation on Mac: if no app opens a file, it highlights it in Finder and tells you (it used to say «opened» without opening anything).
- Hermes: Workspace's own profile no longer copies your personal Hermes keys (only your model). The first time, connect the provider in Engines › Hermes › account and provider; if you already had the profile, nothing changes.
- No more «(auto close) — session closed without manual capture» notes filling your tabs' memory.
- The "handoff" carries only what you wrote (system notices from Claude Code, Codex and Antigravity used to slip in).
- Tabs named in Korean, Chinese, Russian or another alphabet have their own memory and no longer get mixed up.
- Codex: the conversation stays in its tab even if you open the same brain in two windows.
- Loading a brain no longer changes its owner or hides its sessions. Loading or creating an agent no longer removes your other agents' terminal commands.
- An agent whose name is already a command on your computer is rejected when you create it, and the installer never overwrites a command that isn't its own.
- The calendar is no longer wiped by an odd entry, and a pasted image goes to the open task.
- Antigravity shows up as installed even if its installer didn't add it to the PATH.
- Windows: installing and signing in to Codex and opencode from Engines works; reinstalling respects whether you chose to have the terminal open the hub on its own, and the hub no longer opens inside the engines' hidden terminals.
- Mac: your agents save memory with the Python that ships with the Mac (before, the documented way to save a note failed with it).
- Mac: closing the terminal window lets the engine close its session properly instead of cutting it off.
- opencode 2: Workspace recognizes each tab's conversation when it closes, so the carry-over note includes what happened in opencode and the tab resumes that conversation (before, a format change in opencode kept it from finding it).
- OpenClaw on Mac: after a restart it no longer waits on a process that no longer exists, and it never closes another app by mistake.
- Memory: a section of yours whose title starts with «Vigente» or «Historial» is left alone, and a file with characters that can't be read cleanly is not rewritten: you get a warning.
- `workspace update` tells you when it couldn't update (and exits with an error) instead of finishing as if all went well, and updating re-applies the hook timeouts.
- Ctrl+C while typing a session name cancels without showing an error.
- `workspace doctor` no longer stops to ask you for paths or reinstalls commands for agents that have no brain.

## 0.3.3 — 2026-10-14

**Fixes**
- The hub no longer shows the "setup unfinished" notice. It was based on how
  you left the first run and never refreshed, so it could stay even after you
  had finished it. To go through the first run again: `workspace onboarding`.

## 0.3.2 — 2026-10-14

**Fixes**
- If you already had engines and agents and only peeked at the first run, the
  hub no longer shows the "setup unfinished" notice forever.

## 0.3.1 — 2026-10-14

**A simpler hub: every section in one small box**
- Each section shows only what you need to use it, in a centered box. The
  explanation (how it works, with its maps) is behind the `i` key.
- **Agents:** your agents on top and, below, the options of the one you pick
  (Enter or →; ← or Esc go back). Adding an agent lives right here: the
  «+ add agent» row at the end of the list (or the `a` key); with no agents
  yet, the form opens directly.
- **Creating an agent:** the fields look empty (they used to carry an
  «e.g. …» inside that looked already filled in). The example and the
  explanation of the field you're on go below the form, and if you write a
  lot, you see your whole text there. In **your preferences** every row says
  what it is: yes/no switches, what you picked with «›» to change it, and one
  line below about the selected row; its `i` sums up what you're about to
  create, your usage and how it's born.
- **Engines:** the list on the left and the options on the right. When it
  opens it really checks whether you're signed in to each one: ready · not
  signed in · not installed.
- **Updates:** your version, whether a new one is out and only what you can do
  right then: update (when there's a new version), check and repair, check
  only, go back to the previous version (when there's one) and whether it
  updates itself (yes · notify only · off).
- **Commands:** the list by group and, below, how to type the one you pick
  and what it does. `i` opens its map on the right and when it's useful, and
  it changes as you move.
- **The first run** uses the same box: each step in one box with the
  progress on top (engines → appearance → agent), only what you need to
  decide and the main action below; what explains each step is behind `i`.
  Picking an option no longer moves you forward: in every step (Tone too)
  you move on with the «✦ continue» button, and at the end «✦ go to the hub»
  opens the hub (it used to leave you in the terminal).
- **Calendar** stays the same and gains its explanation behind `i`. **Tone**
  is the box with your agents and their dials.

**Out with what wasn't used**
- **Shortcuts** left the menu: keys `1` to `9` always follow the order of
  your agents in the hub.
- **Google Calendar** is paused while we improve it: it doesn't show in the
  calendar or in the first run.

**Fixes**
- Engines no longer loses the keyboard while it checks the sign-ins.
- Section titles no longer have a shadow under them, just like the hub's.

## 0.3.0 — 2026-10-13

**You decide how much each agent can do without asking you**
- When you create or load an agent you choose two things: whether it reads
  and writes its brain without asking you (**yes** to start with: it's its
  main job) and whether you want automatic skill review when each session
  closes (**no** to start with). Without an interactive terminal (a script)
  those values are used; `agent_admin.py` takes `--autonomy brain|ask` and
  `--skill-review`.
- You change both later in **Agents** (pick the agent and Enter),
  agent by agent. If you turn off access to its brain, it asks you before
  creating or editing any file, also inside it. Without opening the hub:
  `agent_admin.py prefs <agent> --autonomy brain|ask
  --skill-review|--no-skill-review`.
- Your answer is saved with the agent (in its `agent.json`, it travels with
  the brain) and each engine applies it its own way.
- With Claude Code, a new agent reads, creates and edits files **inside its
  brain** without asking you; for the terminal, files outside it and the
  network it asks you first. The engine's protections are never switched
  off.
- Before, the installer let every Claude Code agent run any command without
  asking (and included a store integration that wasn't yours). When you
  update, your agents switch on their own to the new setup: free only inside
  their brain (their previous settings are backed up). Running commands
  without asking is no longer an option.
- "Auto-accept edits" on every Claude Code session (`agentes.auto_mode`) is
  now **off** by default: the brain's permissions rule. To get it back:
  `python3 settings.py set agentes.auto_mode on` in Workspace's folder.

**Skill review is optional and works with all three engines**
- It ships **off**. If you turn it on for an agent, when each session closes
  its own engine (Claude Code, Codex or Antigravity) reviews in the
  background what you corrected and improves its skills; new skills stay as
  proposals until you approve them.
- It reads a neutral copy of the session (not the vendor's internal file),
  uses neither the terminal nor the network, never makes closing wait, and
  uses a little of your subscription.
- It reviews the right brain even when the session ends inside a subfolder
  (before, it reviewed that subfolder and ignored what you chose for the
  agent); with Claude Code it no longer stays saved as one more conversation
  of the agent, and its report reaches the review log even when Claude Code
  won't let it write there. Turn it on or off in **Agents** (pick the agent and Enter);
  agents that didn't choose follow the global `hooks.skill_review` setting (`python3 settings.py set
  hooks.skill_review on` in the Workspace folder).

**The doctor now checks and repairs only the essentials**
- `workspace doctor` (and what you see at the end of `workspace update`) now
  checks only the essentials: your agents, their hooks and commands,
  git/Python/the engine you use, and updates. If one of those isn't working,
  it tells you and fixes it.
- No more warnings that had nothing to do with you: internal brain
  conventions (BOOT, INDEX, manifests, banner), GitHub CLI, a team channel,
  autonomous mode, and optional features you don't use (voice, split
  terminal).
- Having no agents yet is normal: it's no longer a warning.
- It now detects and fixes an agent's hooks that point to a Workspace folder
  that no longer exists (for example, after moving or reinstalling).
- Voice is set up whenever you want with `workspace voice --setup`; the
  doctor no longer checks it.

**Out with what you weren't using**
- Letter keys that no longer opened anything (c, o, k, u, g, s, b, v, m, i, l)
  are gone from Shortcuts, the first-run summary and the manual: in the hub
  letters search; the quick keys are `1`–`9` (your agents) and `q`. Shortcuts
  now only changes each agent's digit.
- `workspace versiones` (and `ramas`/`branches`) is gone: it was a git
  branch map for people developing Workspace, not for you.
- The old configuration screen is gone; the hub could no longer open it.
  Your settings stay: theme and background in Personalization, permissions
  and skill review in Agents (Enter on the agent), and any setting with
  `python3 settings.py set <setting> <value>`.
- New agents no longer get a gallery of emblems that nothing showed.
- `workspace foco` (`focus`) is gone: it saved a focus of the day that no
  screen showed. Your agenda and the calendar stay as they were.

**Fixes**
- Creating an agent no longer ends with "⚠ final check 1 placeholder(s)
  left unfilled": the new agent's owner page (BOOT/02-TEAM.md) is now filled
  in.
- If you came from the previous install, an internal agent that was never
  yours had slipped into your list; the doctor checked it and it blocked
  retiring that install's leftovers. An automatic adjustment removes it (with
  a backup) and those leftovers can now be retired with
  `workspace migrar-legado`.
- "Resume session" no longer gives a false warning when another folder has
  the same name as your brain, and it's only checked for Claude Code agents.

**Install and privacy**
- The installer no longer asks "Who are you?".
- It asks for the CLI of the engine you'll use (Claude Code, Codex or
  Antigravity), not always Claude Code.
- Your sessions are kept for **one year** (it was ten). If you had the value
  our installer used to set, it goes down to 365 days; if you chose another
  one, it's left alone.
- New brains no longer come with session folders named after other people.

## 0.2.0 — 2026-10-13

**A new hub: the Launcher**
- The hub is now a single box with your agents and, below them, Menu,
  Personalization and Language. Enter goes in, Esc goes back and the title
  tells you where you are.
- Type to search: the list filters instantly and also finds what's inside
  (for example "theme").
- ← → switch the engine of the agent you're pointing at (`‹ engine ›`); Tab
  shows its details.
- The box always keeps the same size: you can shrink the window until only
  the box fits. The previous hub and its variants are gone.
- Esc takes you back to the hub from every section (Calendar, Tone and
  Updates used to drop you to the terminal) and from an agent's session
  menu, which now shows just its name and its sessions.

**Updates with a safety net, and optional**
- You choose whether Workspace updates itself: **automatic** (as before),
  **notify only** (it tells you a new version is out and you decide) or
  **off**. Change it in Updates (key `a`) or with `workspace update --auto`.
- Before using a new version, Workspace checks that it starts on your
  computer. If it doesn't, it goes back to the one you had and waits until we
  publish a fix. Nothing for you to do.
- If you don't like a new version, `workspace update --rollback` takes you
  back to the previous one. Your agents, brains and settings aren't touched.
- The adjustments a version needs to make on your machine are applied in
  plain sight and recorded. If one fails, Workspace keeps working and
  `workspace doctor` tells you what happened and how to continue.
- `workspace version` shows your version, your last update and these notes.
  The version also shows at the bottom right of the hub.

**Help and diagnosis**
- `workspace doctor --bundle` builds a diagnostic ZIP to ask for help, with
  your personal data blanked out and a README saying what's inside.
- New user manual in `manual/` (Spanish and English), with an honest table of
  what works with each engine on each system and which data leaves your
  computer.
- A template to report problems and a private channel to report security
  issues (`SECURITY.md`).

**Commands**
- Every command accepts its Spanish and English name (`tono`/`tone`,
  `actualizar`/`update`…); every name from before still works.
- The Commands screen searches with `/` and runs the command with Enter (asks
  for confirmation on the delicate ones).
- `workspace commands --json` gives your agents the full list.

**Install, first run and uninstall**
- The installer checks your computer before touching anything (Python, git,
  disk space, cloud folders) and tells you what to fix, without blaming you.
- At the end of the welcome you see the keys that matter (yours, if you
  changed them).
- Uninstall shows what is deleted and what is kept, offers a backup of your
  settings (without your keys) and refuses to delete folders that aren't
  Workspace's.

**Security**
- Closed the open findings of an internal audit: the key vault no longer
  leaves a readable file while saving, the bus never dispatches the same
  message twice, the review of an agent's changes catches more kinds of keys
  and dangerous commands, and a key is never saved under another account.

**Agent tone**
- Tone dials are firmer: Length sets a concrete word budget, rules the shape of the answer and wins when it clashes with another dial. In Codex and Antigravity the tone now comes first in the startup instructions.

**Themes**
- A theme defines one palette, and the colours of the hub, the terminal and
  the theme inside Claude Code all come from it. What you made by hand isn't
  overwritten. Nothing changes on screen unless you pick a new theme.
- New **Blanco** (white) theme: white background with everything else in
  black, the inverse of Mono. Both use just two pure colours, no greys.
- The theme and background you pick in the hub now also colour your agents'
  sessions: the status bar, the banner and the theme inside Claude Code.
  A Claude Code theme you edited by hand is kept.

**Cleanup**
- The product's previous name is gone from screens and texts; Workspace still
  recognises and migrates leftovers of the previous install.
- The hub's GitHub section is temporarily removed while we rework it.

## 0.1.0 — 2026-06-18

- First version: terminal hub, agents with their own brain, swappable engines,
  guided onboarding, a doctor that checks and repairs, and automatic updates.
