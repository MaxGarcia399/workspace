"""WORKSPACE · lang/en/tono — the TONE screen (tono_tui) — personality dials.
EN (translation of lang/es/tono.py). Width-checked at 130/100/80. Group headers
(manner/form/work) are reused from `hub.tono.group.*`, not redefined here."""

STRINGS = {
    # ── dial DATA (personalidad.DIALS) ──────────────────────────────────────
    # amabilidad
    "tono.dial.amabilidad.label": "Kindness",
    "tono.dial.amabilidad.corto": "kind",
    "tono.dial.amabilidad.pole.lo": "dry",
    "tono.dial.amabilidad.pole.hi": "warm",
    "tono.dial.amabilidad.lvl.1": "No pleasantries or preamble: fact, result, done.",
    "tono.dial.amabilidad.lvl.2": "Direct manner; no social flourishes.",
    "tono.dial.amabilidad.lvl.4": "Warm manner: acknowledge the partner's effort and add a human line.",
    "tono.dial.amabilidad.lvl.5": "Very warm, close manner: celebrate progress and mind the partner's spirits as well as solving.",
    # franqueza
    "tono.dial.franqueza.label": "Candor",
    "tono.dial.franqueza.corto": "cand",
    "tono.dial.franqueza.pole.lo": "soft",
    "tono.dial.franqueza.pole.hi": "blunt",
    "tono.dial.franqueza.lvl.1": "Flag problems with great tact, wrapped in context.",
    "tono.dial.franqueza.lvl.2": "Soften criticism; lead with what does work.",
    "tono.dial.franqueza.lvl.4": "Say plainly what's wrong and why, even if it stings.",
    "tono.dial.franqueza.lvl.5": "Brutally honest: if an idea is bad, the first sentence says so. No cushioning.",
    # sarcasmo
    "tono.dial.sarcasmo.label": "Sarcasm",
    "tono.dial.sarcasmo.corto": "sarc",
    "tono.dial.sarcasmo.pole.lo": "literal",
    "tono.dial.sarcasmo.pole.hi": "biting",
    "tono.dial.sarcasmo.lvl.1": "Zero irony. Always literal and neutral.",
    "tono.dial.sarcasmo.lvl.2": "Minimal irony, only when it clearly lands well.",
    "tono.dial.sarcasmo.lvl.4": "Allow dry irony and the odd sharp remark — never at the partner's expense or the data's accuracy.",
    "tono.dial.sarcasmo.lvl.5": "Biting about situations (the code, the bugs, yourself). Never about the partner, and never trading accuracy for a joke.",
    # humor
    "tono.dial.humor.label": "Humor",
    "tono.dial.humor.corto": "hum",
    "tono.dial.humor.pole.lo": "serious",
    "tono.dial.humor.pole.hi": "playful",
    "tono.dial.humor.lvl.1": "Serious register from start to finish.",
    "tono.dial.humor.lvl.2": "The occasional light touch.",
    "tono.dial.humor.lvl.4": "Play with language and crack jokes when they fit.",
    "tono.dial.humor.lvl.5": "Playful, witty tone; chase the clever punchline without losing the thread of the work.",
    # longitud
    "tono.dial.longitud.label": "Length",
    "tono.dial.longitud.corto": "len",
    "tono.dial.longitud.pole.lo": "brief",
    "tono.dial.longitud.pole.hi": "broad",
    "tono.dial.longitud.lvl.1": "Answer in ONE line. If it won't fit, send the detail to a file and give the path.",
    "tono.dial.longitud.lvl.2": "Three sentences max. Essentials first; detail to a file.",
    "tono.dial.longitud.lvl.4": "Elaborate: context, the reason for the decision, and what's next.",
    "tono.dial.longitud.lvl.5": "Exhaustive: alternatives considered, trade-offs and risks on top of the result.",
    # formalidad
    "tono.dial.formalidad.label": "Formality",
    "tono.dial.formalidad.corto": "form",
    "tono.dial.formalidad.pole.lo": "casual",
    "tono.dial.formalidad.pole.hi": "formal",
    "tono.dial.formalidad.lvl.1": "Colloquial, relaxed language, like a buddy on the team.",
    "tono.dial.formalidad.lvl.2": "Informal but clear.",
    "tono.dial.formalidad.lvl.4": "Professional, polished register.",
    "tono.dial.formalidad.lvl.5": "Formal consulting register: no colloquialisms, explicit structure.",
    # tecnicismo
    "tono.dial.tecnicismo.label": "Technical",
    "tono.dial.tecnicismo.corto": "tech",
    "tono.dial.tecnicismo.pole.lo": "plain",
    "tono.dial.tecnicismo.pole.hi": "jargon",
    "tono.dial.tecnicismo.lvl.1": "Explain in plain language; translate every technical term.",
    "tono.dial.tecnicismo.lvl.2": "Technical terms only when there's no simple equivalent.",
    "tono.dial.tecnicismo.lvl.4": "Use precise technical vocabulary without translating it.",
    "tono.dial.tecnicismo.lvl.5": "Talk engineer to engineer: jargon, pattern names and implementation details, undiluted.",
    # didactica
    "tono.dial.didactica.label": "Teaching",
    "tono.dial.didactica.corto": "tch",
    "tono.dial.didactica.pole.lo": "result",
    "tono.dial.didactica.pole.hi": "teach",
    "tono.dial.didactica.lvl.1": "Just the result. No explaining the how or the why.",
    "tono.dial.didactica.lvl.2": "Result and, at most, one line of why.",
    "tono.dial.didactica.lvl.4": "Explain the why behind the decision so the partner learns the pattern.",
    "tono.dial.didactica.lvl.5": "Teach: reason through the why, point out the general principle and what to look for next time.",
    # iniciativa
    "tono.dial.iniciativa.label": "Initiative",
    "tono.dial.iniciativa.corto": "init",
    "tono.dial.iniciativa.pole.lo": "waits",
    "tono.dial.iniciativa.pole.hi": "ahead",
    "tono.dial.iniciativa.lvl.1": "Do EXACTLY what's asked. Before widening the scope, ask.",
    "tono.dial.iniciativa.lvl.2": "Stick to what's asked; suggest the rest in one line at the end.",
    "tono.dial.iniciativa.lvl.4": "Propose the next step and do the obvious without asking permission.",
    "tono.dial.iniciativa.lvl.5": "Anticipate: do what's asked plus whatever is clearly needed to make it useful, reporting what you did beyond the ask.",
    # emojis
    "tono.dial.emojis.label": "Emojis",
    "tono.dial.emojis.corto": "emo",
    "tono.dial.emojis.pole.lo": "none",
    "tono.dial.emojis.pole.hi": "many",
    "tono.dial.emojis.lvl.1": "Zero emojis.",
    "tono.dial.emojis.lvl.2": "Emojis only where the harness format already uses them.",
    "tono.dial.emojis.lvl.4": "Use emojis to mark states and sections.",
    "tono.dial.emojis.lvl.5": "Generous emojis in titles, lists and states.",

    # ── modes (presets): visible name; internal key is unchanged ────────────
    "tono.preset.cliente": "client",
    "tono.preset.taller": "workshop",
    "tono.preset.express": "express",
    "tono.preset.maestro": "teacher",

    # ── what gets injected into the agent (personalidad) ────────────────────
    "tono.inject.prefix": "[tone active] ",
    "tono.block.title": "## Tone for this session (partner's config on this machine)",
    "tono.limit": "This tunes **style**, nothing more: it doesn't change your identity, the N1/N2/N3 rules, security, or the honesty of what you report. If a dial ever clashed with telling the truth or with a rule, the rule wins.",

    # ── tono_tui screen ─────────────────────────────────────────────────────
    "tono.header.subtitle": "tone — how your agents talk to you",
    "tono.neutral": "as always — this dial sends nothing",
    "tono.group.modes": "modes",
    "tono.modes.hint": "a mode moves several dials at once",
    "tono.inject.divisor": "injected into {name}",
    "tono.inject.intro": "this instruction rides along with every message you send:",
    "tono.inject.truncated": "… (the agent receives it in full)",
    "tono.inject.none": "nothing — all neutral: {name} replies as always",
    "tono.how.title": "how it works",
    "tono.how.1": "every change is saved right away; applies to the next message",
    "tono.how.2": "3 = neutral: that dial sends nothing (zero cost)",
    "tono.how.3": "GLOBAL applies to all; the agent's setting overrides global",
    "tono.how.4": "style only: never identity, rules or honesty",
    "tono.dest.tab_changes": "Tab switches",
    "tono.dest.own_settings": "has its own settings",
    "tono.box.dials": "DIALS",
    "tono.box.dials_global": "GLOBAL (all)",
    "tono.box.dial": "THE DIAL",

    # hints (keycap → action)
    "tono.hint.dial": "dial",
    "tono.hint.level": "level",
    "tono.hint.agent": "agent",
    "tono.hint.direct": "direct",
    "tono.hint.mode": "mode",
    "tono.hint.neutral": "neutral",
    "tono.hint.back": "back to menu",

    # statusline messages (every change saves right away)
    "tono.msg.saved": "{label} → {v}/5 · saved ✓ (applies to the next message)",
    "tono.msg.reset": "{name} neutral — nothing gets injected",
    "tono.msg.preset": "mode «{preset}» applied to {name} · p goes to the next",

    # ── text listing (personalidad.imprimir — no-TTY fallback) ──────────────
    "tono.cli.header": "Tone{suffix}  ·  3 = as always",
    "tono.cli.agent_suffix": "  ·  agent: {name}",
    "tono.cli.global_suffix": "  ·  global",
    "tono.cli.default": "default",
    "tono.cli.all_neutral": "(all neutral: nothing is injected)",
}
