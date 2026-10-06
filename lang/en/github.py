"""WORKSPACE · lang/en/github — the GitHub section (github_tui). EN (translation of lang/es/github.py)."""

STRINGS = {
    # ── header + footer/header hints ────────────────────────────────────────
    "github.subtitle": "github — your repos: local branches + PRs · issues · releases",
    "github.box.repos": "REPOS",
    "github.box.detail": "DETAIL · {name}",
    "github.box.connect": "CONNECT",
    "github.hint.focus": "focus",
    "github.hint.open": "open",
    "github.hint.query": "query GitHub",
    "github.hint.connect": "connect",
    "github.hint.disconnect": "disconnect",
    "github.hint.branch": "branch",
    "github.hint.map": "local map",
    "github.hint.back": "back",
    "github.hint.type_manual": "to type it in",
    "github.hint.cancel": "cancel",
    "github.hint.write_target": "owner/name, URL or folder",
    "github.hint.back_selector": "back to selector",
    "github.key.type": "type",

    # ── window (honest ↑/↓ borders) ─────────────────────────────────────────
    "github.more_up": "↑ {n} more above",
    "github.more_down": "↓ {n} more below",

    # ── status line (the session gate) ──────────────────────────────────────
    "github.state.gh": "gh: {acct}",
    "github.state.session_active": "session active",
    "github.state.repos_one": "{n} repo",
    "github.state.repos_many": "{n} repos",
    "github.state.cloud_hint": "cloud only with f — nothing runs on its own",
    "github.state.querying": "querying {repos}…",
    "github.state.no_session": "✗ no GitHub session",
    "github.state.connect_cta": "sign in: gh auth login",
    "github.state.local_still": "local still works: m opens the branch map",
    "github.state.reverify": "r re-checks",

    # ── repo list rows ──────────────────────────────────────────────────────
    "github.repo.no_github": "{name} (no github)",
    "github.repo.querying": "querying…",
    "github.repo.pr_iss": "{pr}PR·{iss}iss",
    "github.repo.only_local": "local only",
    "github.repo.not_queried": "not queried",

    # ── REPOS box: dividers + first-run guide ───────────────────────────────
    "github.div.this_harness": "this harness",
    "github.div.connected": "connected",
    "github.repos.none_yet": "none yet — it's 1 step:",
    "github.repos.pick_detected": "pick a detected local repo",
    "github.repos.or_paste": "(or paste owner/name · also by clicking here)",

    # ── CONNECT box (local repo selector) ───────────────────────────────────
    "github.connect.title": "connect a repo — pick a local one or type it",
    "github.div.detected": "detected local repos",
    "github.connect.scanning": "scanning your disk for repos… (local read only, zero network)",
    "github.connect.none_found": "no git repos found in the common folders — type it below",
    "github.connect.no_origin": "no github origin",
    "github.connect.already": "already",
    "github.div.manual": "by hand",
    "github.connect.manual_row": "type owner/name · a github.com URL · or a folder",
    "github.connect.bullet1": "Enter connects the pick — only noted in your per-machine list (github-repos.json)",
    "github.connect.bullet3": "type any letter and you jump straight to the text field · Esc cancels",

    # ── BY HAND box (text field) ────────────────────────────────────────────
    "github.write.title": "connect a GitHub repo — by hand",
    "github.write.bullet1": "owner/name · a github.com URL · or a cloned local folder",
    "github.write.bullet2": "only noted in your per-machine list (~/.claude/workspace/github-repos.json)",
    "github.write.bullet4": "Enter connects · Esc back to selector",

    # note shared by CONNECT and BY HAND (identical text)
    "github.note.no_clone": "no clone, no network, no tokens stored — gh handles the session",

    # ── DETAIL rows (by type) ───────────────────────────────────────────────
    "github.item.draft_suffix": " ·draft",
    "github.item.here_copy": "your copy is here",
    "github.item.enter_switch": "Enter switches to this branch",
    "github.item.protected": "protected",
    "github.item.draft": "draft",
    "github.item.published": "published",

    # ── DETAIL box ──────────────────────────────────────────────────────────
    "github.det.no_repos": "no repos",
    "github.det.private": "private",
    "github.det.public": "public",
    "github.det.querying": "querying GitHub…",
    "github.det.queried": "queried {ago} — f refreshes",
    "github.det.not_queried_full": "not queried — f brings PRs, issues, branches, commits and releases",
    "github.det.not_queried": "not queried",
    "github.det.local_copy": "local copy · {path}",
    "github.det.no_local": "no local copy — everything opens in the browser",
    "github.det.local_branches": "branches · local copy · {n}",
    "github.det.more_branches": "… and {n} more — m opens the full map",

    "github.div.disconnected": "github disconnected",
    "github.det.off_bullet1": "no session, NO network touched: zero queries from here",
    "github.det.off_bullet2": "gh stores your session in the system keyring — this screen never sees tokens",
    "github.det.off_bullet3": "local stays complete: m opens the branch and worktree map",

    "github.div.no_github": "no github",
    "github.det.nogh1": "this repo has no github.com origin — the cloud doesn't apply",
    "github.det.nogh_switch": "Enter or c on a branch above switches the local copy (clean tree)",
    "github.det.nogh2": "m opens its local branch and worktree map",

    "github.div.will_see": "what you'll see on query",
    "github.det.preview1": "open PRs with their check status (✓ × ●)",
    "github.det.preview2": "open issues · remote branches · recent commits",
    "github.det.preview3": "releases and Actions runs",
    "github.det.preview4": "nothing runs on its own: f queries, with your gh session",

    "github.div.prs": "open reviews · PR",
    "github.div.issues": "open issues",
    "github.div.branches": "remote branches",
    "github.div.commits": "recent commits · {branch}",
    "github.det.default_branch": "default",
    "github.div.releases": "releases",
    "github.div.runs": "actions",
    "github.det.none": "none",
    "github.det.more_open": "… and {n} more — Enter/o opens the repo in the browser",

    "github.div.failed_queries": "failed queries",

    "github.div.actions": "actions",
    "github.det.act_enter_branch": "Enter opens the pick in your browser — and on «branches · local copy» switches to that branch",
    "github.det.act_enter": "Enter opens the pick in your browser — never changes anything",
    "github.det.act_checkout": "c switches the local copy to the picked branch (clean tree, never --force) · m opens its branch map",
    "github.det.act_query": "f queries GitHub again · x disconnects (your list only)",
    "github.det.act_off": "f is off without a session — gh auth login and r",

    # ── x confirmation (disconnect) ─────────────────────────────────────────
    "github.confirm.disconnect": "⚠ disconnect {slug} — Enter confirms · Esc cancels (only leaves your list; nothing is deleted)",

    # ── security gate: auth_check ───────────────────────────────────────────
    "github.auth.no_gh": "GitHub CLI (gh) is not installed — the cloud is off; local stays complete",
    "github.auth.no_session": "no GitHub session — sign in: gh auth login (r re-checks on return)",

    # ── status messages (S["msg"]) ──────────────────────────────────────────
    "github.msg.cancel_norepo": "cancelled — no repo, no connection",
    "github.msg.not_git": "that folder is not a git repository",
    "github.msg.no_origin": "that repo has no github.com origin — connect it with owner/name",
    "github.msg.unparsed": "couldn't parse the repo: use owner/name, a github.com URL or a cloned local folder",
    "github.msg.already_local": "{slug} was already connected — registered its local copy ✓",
    "github.msg.already": "{slug} is already connected",
    "github.msg.write_fail": "couldn't write github-repos.json — nothing changed",
    "github.msg.connected": "{slug} connected ✓ — f queries its status",
    "github.msg.disconnected": "{slug} disconnected ✓ — only left your list; nothing was deleted",

    "github.msg.query_failed": "query failed",
    "github.msg.bad_response": "invalid response",
    "github.msg.no_response": "no response",
    "github.msg.query_prefix": "query: ",

    "github.msg.queried_ok": "{slug} queried ✓",
    "github.msg.queried_fail_one": "{slug} queried — {n} query failed (see detail)",
    "github.msg.queried_fail_many": "{slug} queried — {n} queries failed (see detail)",

    "github.msg.cmd_fail": "`{cmd}` failed: {detail}",

    "github.msg.only_github": "I only open github.com URLs — this isn't one",
    "github.msg.opened": "opened in the browser ✓ — {url}",
    "github.msg.open_fail": "couldn't open the browser: {err}",

    "github.msg.not_branch": "that row is not a branch",
    "github.msg.no_local_clone": "no local copy — Enter opens it in the browser; clone it to switch branches",
    "github.msg.job_running": "a branch switch is in progress — wait for it to finish",
    "github.msg.cant_confirm_clean": "couldn't confirm the local tree is clean — leaving it alone",
    "github.msg.dirty_one": "the local copy has {n} uncommitted change — commit or stash before switching branch",
    "github.msg.dirty_many": "the local copy has {n} uncommitted changes — commit or stash before switching branch",
    "github.msg.already_on": "the local copy is already on {branch}",
    "github.msg.now_on": "the local copy is now on {branch} ✓",
    "github.msg.switching": "switching to {branch}… ({mode} in the background)",

    "github.msg.no_page": "this repo has no GitHub page",

    "github.msg.cancelled": "cancelled",
    "github.msg.nothing_disconnect": "nothing to disconnect",
    "github.msg.cancel_kept": "cancelled — the repo stays in your list",
    "github.msg.no_github_map": "this repo has no GitHub — m opens its local branch map",
    "github.msg.no_session_query": "no GitHub session, I query nothing — run gh auth login then r",
    "github.msg.nothing_to_query": "this repo has no GitHub to query",
    "github.msg.already_querying": "already querying {slug} — one moment",
    "github.msg.querying_bg": "querying {slug} in the background — the screen stays live",
    "github.msg.harness_no_disconnect": "the harness can't be disconnected — it's the base of this screen",
    "github.msg.no_map": "no local copy, no map — a opens the local repo selector (or paste its folder)",
    "github.msg.checkout_hint": "c switches the local copy to a BRANCH — pick one under «branches» (Tab + ↑↓ or click)",
    "github.msg.reloaded_ok": "session and list reloaded ✓ — gh: {acct}",
    "github.msg.reloaded_no": "list reloaded — still no GitHub session",
    "github.msg.no_session_word": "no session",

    # ── no-tty listing ──────────────────────────────────────────────────────
    "github.list.prefix": "github: {status}",
    "github.list.session": "gh session {acct} ✓",
    "github.list.active": "active",
    "github.list.extra": " · {pr} PR · {iss} issues · {ago}",
}
