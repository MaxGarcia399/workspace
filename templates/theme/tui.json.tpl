{
  "roles": {
    "text": "{{ foreground }}",
    "hi": "{{ accent_hi }}",
    "accent": "{{ accent }}",
    "mid": "{{ accent_2 }}",
    "dim": "{{ muted }}",
    "dark": "{{ mix border foreground 15% }}",
    "grey": "{{ faint }}",
    "inactive": "{{ muted }}",
    "inactive_alt": "{{ border }}",
    "err": "{{ danger }}",
    "ok": "{{ success }}",
    "bad": "{{ danger }}"
  },
  "stars": {
    "dim": ["{{ mix background foreground 8% }}", "{{ mix background foreground 11% }}",
            "{{ mix background foreground 14% }}", "{{ mix background foreground 10% }}"],
    "mid": ["{{ mix background foreground 22% }}", "{{ mix background foreground 32% }}"],
    "hi": "{{ accent_hi }}"
  },
  "fire": ["{{ background }}", "{{ mix background accent 8% }}",
           "{{ mix background accent 16% }}", "{{ mix background accent 26% }}",
           "{{ mix background accent 36% }}", "{{ mix background accent 48% }}",
           "{{ mix background accent 62% }}", "{{ mix background accent 80% }}",
           "{{ accent }}", "{{ mix accent foreground 30% }}",
           "{{ mix accent foreground 60% }}", "{{ mix accent foreground 85% }}"],
  "ember": ["{{ mix background accent 26% }}", "{{ mix background accent 36% }}",
            "{{ mix background accent 48% }}", "{{ mix background accent 62% }}"],
  "off": "{{ faint }}",
  "osc": {
    "bg": "{{ background }}",
    "fg": "{{ foreground }}",
    "cursor": "{{ cursor }}"
  }
}
