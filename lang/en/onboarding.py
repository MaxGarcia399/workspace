"""WORKSPACE · lang/en/onboarding — the first-run flow (onboarding_tui). EN."""

STRINGS = {
    "onboarding.subtitle": "first run — get your Workspace ready in 3 steps",

    # stage row (1 engines ── 2 appearance ── 3 agent)
    "onboarding.etapa.motores": "engines",
    "onboarding.etapa.apariencia": "appearance",
    "onboarding.etapa.agente": "agent",

    # divisors shared across steps
    "onboarding.div.tu_eleccion": "your choice",
    "onboarding.div.que_cambia": "what changes",
    "onboarding.continuar": "✦ continue",

    # step 0: language
    "onboarding.idioma.divisor": "language",
    "onboarding.idioma.heading": "Choose your Workspace language.",
    "onboarding.idioma.body": "You can change it anytime from the hub menu "
                              "(“Language”) or in Config. Developer "
                              "screens stay in Spanish.",

    # welcome
    "onboarding.welcome.title_l": "WHAT IS WORKSPACE",
    "onboarding.welcome.title_r": "THE PLAN",
    "onboarding.welcome.p1": "Workspace is a local hub for your AI agents: "
                             "each agent lives in its own brain (a folder of "
                             "files you own) and runs on a CLI engine you "
                             "already have installed — Claude Code, Codex or "
                             "Antigravity.",
    "onboarding.welcome.p2": "Everything happens on your machine: zero "
                             "dependencies, no new accounts, and Workspace "
                             "never sees or stores your credentials (login is "
                             "each CLI's own).",
    "onboarding.welcome.plan_title": "what's next",
    "onboarding.welcome.step1_t": "1 engines",
    "onboarding.welcome.step1_d": "I detect which CLIs you have and you pick "
                                  "which to use",
    "onboarding.welcome.step2_t": "2 appearance",
    "onboarding.welcome.step2_d": "hub theme and background — applied instantly",
    "onboarding.welcome.step3_t": "3 agent",
    "onboarding.welcome.step3_d": "create a new one, load an existing one or "
                                  "scan your disk (and tune its tone)",
    "onboarding.welcome.transparency_title": "transparency",
    "onboarding.welcome.transparency_p": "At the end: a summary of what you "
                                         "chose and where it was saved. You can "
                                         "skip this with q and repeat it "
                                         "anytime with `workspace onboarding`.",

    # step 1: ENGINES
    "onboarding.motores.title_l": "ENGINES DETECTED",
    "onboarding.motores.title_r": "THE ENGINE",
    "onboarding.motores.div_listo": "ready",
    "onboarding.motores.marcados": "{n} engine(s) selected",
    "onboarding.motores.estado": "status",
    "onboarding.motores.div_honesto": "honest",
    "onboarding.motores.honesto_p": "Session status is read from each engine's "
                                    "own CLI; Workspace never stores or sees "
                                    "credentials.",
    "onboarding.motores.default_p": "The selected engines are your working "
                                    "set. “{motor}” becomes the default "
                                    "(modelos.default_engine) for agents that "
                                    "don't declare their own — each agent can "
                                    "set a different one later.",
    "onboarding.motores.none_p": "With no engine selected you can't launch "
                                 "agents. You can continue anyway, install a "
                                 "CLI later and repeat this with "
                                 "`workspace onboarding`.",
    # engine status (full line)
    "onboarding.motores.st.unavailable": "not available in this install",
    "onboarding.motores.st.not_installed": "not installed — {falta} missing "
                                           "from PATH",
    "onboarding.motores.st.cli": "CLI",
    "onboarding.motores.st.checking": "binary ✓ · checking session…",
    "onboarding.motores.st.session_ok": "binary ✓ · session active ✓",
    "onboarding.motores.st.login_needed": "binary ✓ · login needed — {det}",
    "onboarding.motores.st.no_session": "no session",
    # compact status (summary)
    "onboarding.motores.short.not_installed": "not installed",
    "onboarding.motores.short.binary": "binary ✓",
    "onboarding.motores.short.session": "session ✓",
    "onboarding.motores.short.login": "login needed",
    # honest copy per engine: (what it is · how you log in · what changes)
    "onboarding.motor.claude-code.what": "Claude Code — Anthropic's official "
                                         "CLI (the `claude` binary).",
    "onboarding.motor.claude-code.login": "Log in with your subscription: run "
                                          "`claude` once and follow the login.",
    "onboarding.motor.claude-code.changes": "It's the most deeply integrated "
                                            "engine in Workspace: real hooks, "
                                            "memory injected into the agent and "
                                            "harness sessions.",
    "onboarding.motor.codex.what": "Codex — OpenAI's CLI (the `codex` binary), "
                                   "with your ChatGPT subscription.",
    "onboarding.motor.codex.login": "Log in with `codex login` in your "
                                    "terminal.",
    "onboarding.motor.codex.changes": "Workspace wraps it; it never reads or "
                                      "touches your token (~/.codex/).",
    "onboarding.motor.antigravity.what": "Antigravity — Google's `agy` CLI "
                                         "(Gemini).",
    "onboarding.motor.antigravity.login": "The session opens with your Google "
                                          "account from the CLI itself.",
    "onboarding.motor.antigravity.changes": "Workspace wraps it just like the "
                                            "other engines.",

    # step 2: APPEARANCE
    "onboarding.apariencia.title_l": "THEME & BACKGROUND",
    "onboarding.apariencia.title_r": "APPEARANCE",
    "onboarding.apariencia.group.tema": "theme",
    "onboarding.apariencia.group.fondo": "background",
    "onboarding.apariencia.activo": "active",
    "onboarding.apariencia.div_donde": "where it lives",
    "onboarding.apariencia.changes_p1": "The theme paints the whole hub — "
                                        "wordmark, boxes, sliders — and saves "
                                        "instantly: this screen is ALREADY "
                                        "painted with it; that's the preview.",
    "onboarding.apariencia.changes_p2": "The background is an independent "
                                        "axis: it changes only the terminal's "
                                        "background color and pairs with any "
                                        "theme.",
    "onboarding.apariencia.donde_p": "ui.theme and ui.background in "
                                     "~/.claude/workspace/settings.json. More "
                                     "options (custom #RRGGBB color, "
                                     "animations, stars) in Config → THEME.",
    # background labels (the id stays; we translate the visible text)
    "onboarding.fondo.tema": "the active theme's",
    "onboarding.fondo.negro": "pure black",
    "onboarding.fondo.grafito": "graphite",
    "onboarding.fondo.azul": "night blue",
    "onboarding.fondo.verde": "forest green",
    "onboarding.fondo.violeta": "violet",

    # step 3: AGENT (paths come from add_agent_tui.MENU_OPTS)
    "onboarding.agente.title_l": "YOUR FIRST AGENT",
    "onboarding.agente.title_r": "THE PATH",
    "onboarding.agente.div_que_pasa": "what happens",
    "onboarding.agente.div_siguiente": "next step",
    "onboarding.agente.siguiente_p": "The real hub screen (“Add agent”) opens "
                                     "on that path. If a new agent ends up "
                                     "connected, on the way back you'll be able "
                                     "to tune its TONE; then, the summary.",
    "onboarding.agente.crear.label": "create a new agent",
    "onboarding.agente.crear.desc": "An agent from scratch: a short form → you "
                                    "see the BRAIN about to be born and the "
                                    "harness it runs on → it's created LIVE, "
                                    "step by step. It's born self-contained in "
                                    "~/Desktop/<NAME> - BRAIN, usable when "
                                    "done.",
    "onboarding.agente.cargar.label": "load an existing agent",
    "onboarding.agente.cargar.desc": "Connect a brain that already exists (a "
                                     "folder): you see WHAT it brings "
                                     "(identity, brain marks, collisions) "
                                     "before connecting, and the wiring (hooks "
                                     "· statusline · launcher · theme) runs "
                                     "LIVE, step by step.",
    "onboarding.agente.descubrir.label": "discover brains on disk",
    "onboarding.agente.descubrir.desc": "Scans Desktop / Documents / vaults "
                                        "for folders with "
                                        ".workspace/agent.json and lets you "
                                        "connect them — you see which are new "
                                        "and which are already set. A MANUAL "
                                        "action — the harness never connects "
                                        "anything on its own.",
    "onboarding.agente.ninguno.label": "finish without an agent",
    "onboarding.agente.ninguno.desc": "You can also add one anytime from the "
                                      "hub (“Add agent”) — create, load or "
                                      "discover are all still there, "
                                      "identical.",

    # final step: SUMMARY
    "onboarding.resumen.title_l": "WHAT YOU SET",
    "onboarding.resumen.title_r": "WHERE & WHAT'S NEXT",
    "onboarding.resumen.div_motores": "engines",
    "onboarding.resumen.div_apariencia": "appearance",
    "onboarding.resumen.div_agentes": "agents",
    "onboarding.resumen.div_donde": "where it landed",
    "onboarding.resumen.div_adelante": "from here on",
    "onboarding.resumen.default": "default: {engine}",
    "onboarding.resumen.sin_cambio": "no change",
    "onboarding.resumen.ninguno_marcado": "none selected — install a CLI and "
                                          "repeat with `workspace onboarding`",
    "onboarding.resumen.y_mas": "… and {n} more",
    "onboarding.resumen.sin_agentes": "no agents yet — “Add agent” in the hub "
                                      "whenever you like",
    "onboarding.resumen.tono_ok": "tone tuned for {agente} ✓",
    "onboarding.resumen.fila_config": "config (theme, background, engine)",
    "onboarding.resumen.fila_agentes": "registered agents",
    "onboarding.resumen.fila_onboarding": "this onboarding",
    "onboarding.resumen.adelante_p1": "Enter drops you into the hub: there you "
                                      "launch agents, open Config, Tone and "
                                      "“Add agent”.",
    "onboarding.resumen.adelante_p2": "Repeat this flow: "
                                      "`workspace onboarding`.",

    # ephemeral messages (footer, S["msg"])
    "onboarding.msg.default_saved": "default engine: {motor} · saved ✓",
    "onboarding.msg.default_fail": "couldn't save the default ({err}) — "
                                   "unchanged",
    "onboarding.msg.not_installable": "{eid} isn't installed — can't select it",
    "onboarding.msg.applied": "{tipo} “{lbl}” · saved ✓",
    "onboarding.msg.apply_fail": "couldn't apply {tipo} ({err})",

    # footer hints (per view)
    "onboarding.hints.idioma": "↑↓ language · Enter picks · Esc/q skips",
    "onboarding.hints.welcome": "Enter starts · q to the hub (come back with "
                                "`workspace onboarding`)",
    "onboarding.hints.motores": "↑↓ engine · space toggles · Enter continues · "
                                "Esc back · q skips",
    "onboarding.hints.apariencia": "↑↓ option · Enter/space applies (saves "
                                   "now) · Esc back · q skips",
    "onboarding.hints.agente": "↑↓ path · 1-4 direct · Enter opens · Esc back "
                               "· q skips",
    "onboarding.hints.resumen": "Enter — to the hub",
}
