# Your system's notices

Your computer protects you: when a program wants to get into certain folders, install something
for the whole machine or use the microphone, the system asks you. Workspace avoids every notice it
can. The ones that can't be avoided, it tells you about **first**, in one line, so you know what to
answer. This page gathers them all.

For each one: **what shows up**, **why**, **what to answer** and **what happens if you say No**.

## When installing Workspace

| What shows up | Why | What to answer | If you say No |
|---|---|---|---|
| **macOS:** "Possible malware, paste blocked" when you paste the command into Terminal | macOS 26.4+ says it with **any** command you paste into Terminal | If you copied the command from Workspace's page, "Paste anyway" | Nothing is installed; you can try again |
| **macOS:** "The "git" command requires the command line developer tools…" | Workspace downloads and updates itself with git, which comes with Apple's tools | "Install" and "Agree". They're Apple's and free; they take a few minutes | Nothing is installed until you have them |
| **Windows:** "Do you want to allow this app to make changes…?" (Git or Python) | Git (or Python) was missing and its official installer is for the whole PC | "Yes" | Nothing is installed until you have Git |
| **Windows Terminal:** "Warning: you are about to paste text that contains multiple lines" | The Windows command takes two lines | "Paste anyway" | Nothing happens; paste each line |

On Mac and Linux, Workspace installs into `~/Workspace` and your new agents are born in
`~/Workspace/Cerebros`: **outside** Desktop, Documents and Downloads. That way macOS doesn't ask
for folder permissions. If you already had Workspace on your Desktop, it stays there and works the
same.

## When installing or using an engine (Engines)

| What shows up | Why | What to answer | If you say No |
|---|---|---|---|
| **Windows:** administrator permission the first time you use **Codex** | Codex (OpenAI's) sets up its "safe space" with Windows' permission | "Yes". If it's a company PC and you can't, ask your IT team | Codex doesn't start until the permission is given |
| **Windows:** administrator permission when installing **Kiro** | Its official installer installs for the whole PC | "Yes" | Kiro isn't installed |
| **Windows:** administrator permission while another engine installs | Its official installer adds something it needs (for example, Node.js) | "Yes" | That engine isn't installed |
| **Windows:** "The "msstore" source requires that you view the following agreements" (Copilot) | It's Windows' app store | Type `Y` and Enter | Copilot isn't installed |
| **macOS:** "Background item added" (Kiro) | It's part of Kiro | You can leave it; it's turned off in Settings → General → Login Items | Nothing: Kiro keeps working |
| **macOS:** ""copilot" Not Opened" or "Apple could not verify…" | The engine was installed with Homebrew and stayed in quarantine | "Done" (not "Move to Trash") and choose reinstall in Engines | The engine doesn't open until it's reinstalled |
| **macOS:** ""Terminal" was prevented from modifying apps on your Mac" | When repairing or reinstalling an engine that lives in Applications | Settings → Privacy & Security → App Management → turn on your terminal | The repair doesn't finish |
| **macOS:** the keychain asks about "copilot-cli" | It's Copilot reading its own session (happens after updating Node) | Your Mac password and "Always Allow" | Copilot asks you to sign in again |

Workspace tells you the engine's line **before** you confirm the installation.

## Optional features

| What shows up | Why | What to answer | If you say No |
|---|---|---|---|
| **macOS:** ""Terminal" would like to access files in your Desktop / Documents folder" when **discovering brains** | Only if you choose "also Desktop/Documents" (key `e` in Discover): by default it doesn't look there | "Allow" lets it find them | Nothing happens: it looks everywhere else |
| **macOS:** "… your Downloads folder" when **connecting Google** | It reads the Google file you downloaded, which is usually in Downloads | "Allow" | It doesn't connect; you can move the file to another folder and drag it again |
| **Google:** "Google hasn't verified this app" | It's your own app, the one you created in Google Cloud | "Advanced" and then "Go to…" | Google doesn't connect |
| **macOS:** ""Terminal" would like to access the microphone" when **dictating by voice** | To hear you. The audio never leaves your Mac | "OK" | You can't dictate |
| **macOS:** "control "System Events"" and Accessibility, only if you asked dictation to **paste on its own** | To paste the text where your cursor is | "OK" and turn on your terminal in Settings → Privacy & Security → Accessibility | The text is still copied: paste it with ⌘V |
| **macOS:** ""WORKSPACE" wants to control "Terminal"" | The optional desktop app opens Terminal | "OK" | The app doesn't open Terminal; use the `workspace` command |
| **macOS / Windows:** permission for incoming network connections | Only if you open Projects or the panel to your network with `--host` | Allow private networks only | It only works on this computer (the usual) |
| **Linux:** "Unlock the login keyring" | Workspace keeps your keys in your keyring | Your session password | Your keys stay in a file only you can read |
| **Windows:** "Unauthorized changes blocked" | You turned on "Controlled folder access" and Workspace saves your PowerShell commands in Documents | Allow it or not | The commands work the same |

## What Workspace no longer asks

- It doesn't go into your Desktop, Documents or Downloads on its own: not when the hub opens, not
  when repairing an agent that moved.
- The diagnostic bundle (`workspace doctor --bundle`) and the uninstaller's backup go to
  `~/Workspace/Respaldos` and are shown to you in their folder.
- The OpenClaw gateway Workspace starts doesn't announce itself on your network (that's why iTerm2
  or VS Code no longer ask to "find devices on your local network").
- Voice dictation leaves the text copied and only asks for the microphone; it doesn't read what
  you had copied.
- With your Mac's keychain locked, Workspace doesn't open it to check your Copilot session.

Got something that isn't here? Tell us with the [diagnostic bundle](troubleshooting.md).
