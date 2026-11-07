# Privacy and transparency

## Where your things live

| What | Where | Who sees it |
|---|---|---|
| Workspace's code | its folder (`~/Desktop/Workspace` or `%LOCALAPPDATA%\Workspace`) | it's public |
| Your settings, shortcuts, themes, state | `~/.claude/workspace/` | only your machine |
| Your agents and their memory | each brain's folder | you (and whoever you choose, if you sync it) |
| Your credentials | on this machine; never in the repository | only your machine |

## What leaves your machine

Workspace **has no server of its own** and sends telemetry to no one. This is the complete
list of connections it can make, where to and when.

<!-- List verified against the code shipped to clients (everything make-dist.sh keeps):
urllib, smtplib, socket, webbrowser, git fetch/pull, curl/irm and subprocesses to gh, brew,
npm and winget. If you add a connection, add it here and in ../es/privacidad.md. -->

**Always (you can turn it off):**

| Connection | Where to | When | How to turn it off |
|---|---|---|---|
| Automatic update (`git fetch` / `git pull`) | Workspace's repository on GitHub | when you open an agent, at most once every 6 h (in "notify", once a day and without installing) | `workspace update --auto off` (or the «automatic» row in Updates) |
| Your engine's program | that engine's vendor (Anthropic, OpenAI, Google, AWS, GitHub, Cursor or the one you connect in OpenCode, OpenClaw or Hermes) | while you use the agent; also when Workspace asks it whether you're logged in | it's the official program with your account; governed by that vendor's terms |

**When you ask for it or turn it on:**

| Connection | Where to | When |
|---|---|---|
| `workspace update` and the **Updates** section | GitHub, and the git remote of each brain that has one | when you ask; it also pulls the brains you keep in git |
| `workspace doctor` (without `--check`) | GitHub (`git fetch`) | checks for a new version of Workspace (and of the brains you declared as git) |
| Finding *skills* in **Add agent** | `api.github.com` and `raw.githubusercontent.com` (public repositories from Anthropic and OpenAI, plus any you add); `skills.sh` only if you type a community search | when you reach the new agent's plan, only if you turn it on (off by default; you can turn it on on that same screen). GitHub sees which repositories and files are fetched; your agent's profile is matched on your machine |
| Installing an engine | the official installer: `claude.ai`, `chatgpt.com`, `antigravity.google`, `opencode.ai`, `openclaw.ai`, `hermes-agent.nousresearch.com`, `cli.kiro.dev`, `cursor.com`, npm (OpenCode on Windows; GitHub Copilot on Mac and Linux) or WinGet (GitHub Copilot on Windows) | only when you ask to install it |
| Skill review (when the next session opens) | the vendor of the agent's engine, inside that visible session (like any message) | only for agents where you turned it on (it ships off); the agent reads the copy of the previous session that Workspace saved in the brain when it closed |
| Google Calendar | `calendar.google.com` (iCal link) or Google's APIs (`accounts.google.com`, `oauth2.googleapis.com`, `www.googleapis.com`), read-only | if you connect your calendar; then it refreshes on its own, in the background |
| Mail (`workspace mail`) | the SMTP server you configure | each time you send |
| Voice dictation setup (macOS) | Hugging Face (whisper model) and Homebrew | only with `workspace voice --setup`; dictating is 100% local |
| API providers (advanced) | the endpoint you configure (e.g. OpenAI, OpenRouter, Anthropic, Google, or a local one such as Ollama or LM Studio) | only if you set up a provider with your API key |
| Opening a link | your browser | when you choose to open something (such as an engine's official source) |

## What it records locally

To show you what your agents are doing, Workspace keeps **activity** records in
`~/.claude/workspace/` (which tool, when, how long, whether it worked) — **never the
content** of what the agent reads or writes. They never leave your machine. To turn them off:
`WORKSPACE_NO_TELEMETRY=1`.

When each session closes, Workspace also notes **numbers and names** about it in
`~/.claude/workspace/metricas/`: tokens and model, how long it took, how many tools it used and
how many failed, which skills it read and how many files it wrote. Never the text of the
conversation, and tabs and files are kept as fingerprints, not by name. **Workspace does not
send them**: they stay on this computer, in a folder only your user can open (on a company PC,
the machine's administrator too; on Windows, your user folder's permissions protect it). Sessions
in Claude Code, Codex, OpenCode, OpenClaw, Hermes, Antigravity, GitHub Copilot, Cursor and Kiro
are measured, each with what its engine keeps (Cursor records no times, model or tokens; Kiro
keeps no tokens); for Gemini, for now, only when each session happened and how long it lasted.
Whatever an engine doesn't give is left empty, never zero. `workspace metrics export` builds a totals-only file, without
people, if you decide to share it. `workspace metrics delete --mine` deletes yours. To turn them
off: `workspace metrics off`; `WORKSPACE_NO_METRICAS=1` is the emergency switch, and what you do
meanwhile is never measured. Metrics are never passed to the agent.

## Credentials

Workspace **does not read or copy** your engines' credentials: each official program handles
its own login. Keys you give Workspace itself (for mail, for example) are stored only on this
machine. Before each version is published, an automatic check makes sure no credential or
personal data slips in.

## Why it works this way

Because it's your computer and your work. See [the manifesto](../MANIFESTO.md).
