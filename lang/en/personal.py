"""Agenda CLI (personal.py) — English."""

STRINGS = {
    "personal.when.past": "past",
    "personal.when.now": "now",
    "personal.when.in": "in {x}",
    "personal.when.today": "today",
    "personal.when.tomorrow": "tomorrow",
    "personal.agenda.usage_add": "usage: workspace agenda add YYYY-MM-DD \"title\" [--time HH:MM] [--cat reunion|hito|recordatorio|cumple|otro]",
    "personal.agenda.add_fail": "invalid date or empty title — nothing added",
    "personal.agenda.added": "added",
    "personal.agenda.usage_done": "usage: workspace agenda done <id>",
    "personal.agenda.missing": "not found: {id}",
    "personal.agenda.done": "done ✓",
    "personal.agenda.undone": "pending again",
    "personal.agenda.usage_rm": "usage: workspace agenda rm <id> [--hard]",
    "personal.agenda.rm_ok": "done",
    "personal.agenda.rm_some_missing": "some id doesn't exist",
    "personal.agenda.empty": "agenda is empty — add with:  workspace agenda add 2026-09-25 \"Meeting\" --time 18:00",
    "personal.agenda.tag_done": "(done)",
    "personal.agenda.tag_archived": "(archived)",
    "personal.unknown": "personal: unknown command '{cmd}' (agenda)",
}
