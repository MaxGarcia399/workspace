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
urllib, smtplib, socket, webbrowser, git fetch/pull, curl/irm and subprocesses to gh, brew
and npm. If you add a connection, add it here and in ../es/privacidad.md. -->

**Always (you can turn it off):**

| Connection | Where to | When | How to turn it off |
|---|---|---|---|
| Automatic update (`git fetch` / `git pull`) | Workspace's repository on GitHub | when you open an agent, at most once every 6 h (in "notify", once a day and without installing) | `workspace update --auto off` (or the «automatic» row in Updates) |
| Your engine's program | that engine's vendor (Anthropic, OpenAI, Google) | while you use the agent; also when Workspace asks it whether you're logged in | it's the official program with your account; governed by that vendor's terms |

**When you ask for it or turn it on:**

| Connection | Where to | When |
|---|---|---|
| `workspace update` and the **Updates** section | GitHub, and the git remote of each brain that has one | when you ask; it also pulls the brains you keep in git |
| `workspace doctor` (without `--check`) | GitHub (`git fetch`) | checks for a new version of Workspace (and of the brains you declared as git) |
| Finding *skills* in **Add agent** | `api.github.com` and `raw.githubusercontent.com` (public repositories from Anthropic and OpenAI, plus any you add); `skills.sh` only if you type a community search | when you reach the new agent's plan, only if you turn it on (off by default; you can turn it on on that same screen). GitHub sees which repositories and files are fetched; your agent's profile is matched on your machine |
| Installing an engine | the official installer: `claude.ai`, `chatgpt.com`, `antigravity.google` or npm | only when you ask to install it |
| Skill review (when the next session opens) | the vendor of the agent's engine, inside that visible session (like any message) | only for agents where you turned it on (it ships off); the agent reads the copy of the previous session that Workspace saved in the brain when it closed |
| Google Calendar | `calendar.google.com` (iCal link) or Google's APIs (`accounts.google.com`, `oauth2.googleapis.com`, `www.googleapis.com`), read-only | if you connect your calendar; then it refreshes on its own, in the background |
| Mail (`workspace mail`) | the SMTP server you configure | each time you send |
| Voice dictation setup (macOS) | Hugging Face (whisper model) and Homebrew | only with `workspace voice --setup`; dictating is 100% local |
| API providers (advanced) | the endpoint you configure (e.g. OpenAI, OpenRouter, Anthropic, Google, or a local one such as Ollama or LM Studio) | only if you set up a provider with your API key |
| Opening a link | your browser | when you choose to open something (such as an engine's official source) |

**Only inside your machine:** `workspace proyectos` opens, by default, a local web panel on `127.0.0.1`;
it can't be opened from another computer.

## What it records locally

To show you what your agents are doing, Workspace keeps **activity** records in
`~/.claude/workspace/` (which tool, when, how long, whether it worked) — **never the
content** of what the agent reads or writes. They never leave your machine. To turn them off:
`WORKSPACE_NO_TELEMETRY=1`.

## Credentials

Workspace **does not read or copy** your engines' credentials: each official program handles
its own login. Keys you give Workspace itself (for mail, for example) are stored only on this
machine. Before each version is published, an automatic check makes sure no credential or
personal data slips in.

## Why it works this way

Because it's your computer and your work. See [the manifesto](../MANIFESTO.md).
